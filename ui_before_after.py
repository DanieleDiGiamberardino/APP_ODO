"""
ui_before_after.py
==================
Visualizzatore Before/After con slider centrale trascinabile.

Funzionalità:
  - Selezione automatica coppia Pre-op / Post-op dello stesso paziente/dente
  - Selezione manuale di qualsiasi due foto dall'archivio
  - Slider verticale trascinabile che rivela progressivamente l'immagine destra
  - Label overlay "PRIMA" / "DOPO" con posizione dinamica
  - Bottoni: swap lati, zoom fit, salva confronto come JPEG, apri viewer completo
  - Hotkey: frecce sinistra/destra per spostare lo slider di 5%

Apertura:
    from ui_before_after import BeforeAfterFrame   # pannello embedded
    from ui_before_after import BeforeAfterDialog  # finestra standalone
"""

import tkinter as tk
from tkinter import filedialog, messagebox
import customtkinter as ctk
from PIL import Image, ImageDraw, ImageFont
import io
import threading
from pathlib import Path
from typing import Optional
from datetime import date

import database as db

# ---------------------------------------------------------------------------
COLORI = {
    "bg":           "#080c18",
    "card":         "#0f1629",
    "entry_bg":     "#070b14",
    "accent":       "#0f3460",
    "accent_br":    "#e94560",
    "verde":        "#3ecf6e",
    "grigio":       "#6b7a99",
    "chiaro":       "#dce8ff",
    "slider_line":  "#ffffff",
    "label_prima":  "#e94560",
    "label_dopo":   "#3ecf6e",
    "divider":      "#1e2d4a",
}
FONT_SEZ  = ("Segoe UI", 13, "bold")
FONT_NRM  = ("Segoe UI", 11)
FONT_SML  = ("Segoe UI", 10)
FONT_MICRO= ("Segoe UI", 9)

SLIDER_W  = 4    # larghezza linea slider px
HANDLE_R  = 12   # raggio maniglia slider
MIN_CANVAS_W = 400
MIN_CANVAS_H = 320


# ===========================================================================
# CANVAS BEFORE/AFTER
# ===========================================================================

class BeforeAfterCanvas(tk.Canvas):
    """
    Canvas custom che mostra due immagini affiancate con slider divisore.

    Coordinate: lo slider è espresso come percentuale 0.0–1.0 della larghezza.
    """

    def __init__(self, master, **kwargs):
        kwargs.setdefault("bg", COLORI["bg"])
        kwargs.setdefault("highlightthickness", 0)
        kwargs.setdefault("cursor", "sb_h_double_arrow")
        super().__init__(master, **kwargs)

        self._img_prima: Optional[Image.Image] = None   # PIL full-res
        self._img_dopo:  Optional[Image.Image] = None
        self._tk_prima:  Optional[tk.PhotoImage] = None  # anti-GC
        self._tk_dopo:   Optional[tk.PhotoImage] = None
        self._slider_pct: float = 0.5                    # 0.0 → 1.0
        self._dragging   = False
        self._show_labels = True
        self._show_handle = True

        self.bind("<Configure>",       lambda e: self._render())
        self.bind("<ButtonPress-1>",   self._on_press)
        self.bind("<B1-Motion>",       self._on_drag)
        self.bind("<ButtonRelease-1>", self._on_release)

    # ------------------------------------------------------------------
    # Caricamento immagini
    # ------------------------------------------------------------------

    def carica(self, path_prima: Optional[Path], path_dopo: Optional[Path]):
        """Carica le due immagini e ridisegna."""
        def _load(p):
            if p and Path(p).is_file():
                try:
                    return Image.open(p).convert("RGB")
                except Exception:
                    pass
            return None

        self._img_prima = _load(path_prima)
        self._img_dopo  = _load(path_dopo)
        self._slider_pct = 0.5
        self._render()

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def _render(self):
        self.delete("all")
        W = self.winfo_width()
        H = self.winfo_height()
        if W < 10 or H < 10:
            return

        # Placeholder se mancano immagini
        if not self._img_prima and not self._img_dopo:
            self.create_text(W // 2, H // 2,
                             text="Seleziona due foto per il confronto",
                             fill=COLORI["grigio"], font=("Segoe UI", 12),
                             justify="center")
            return

        split_x = int(W * self._slider_pct)

        # --- Immagine PRIMA (sinistra, ritagliata a split_x) ---
        if self._img_prima:
            img_l = self._img_prima.copy()
            img_l.thumbnail((W, H), Image.LANCZOS)
            iw, ih = img_l.size
            ox = (W - iw) // 2
            oy = (H - ih) // 2
            # crop alla colonna split_x
            crop_x = split_x - ox
            if crop_x > 0:
                cropped = img_l.crop((0, 0, min(crop_x, iw), ih))
                self._tk_prima = self._pil_to_tk(cropped)
                self.create_image(ox, oy, image=self._tk_prima, anchor="nw")

        # --- Immagine DOPO (destra, dal split_x in poi) ---
        if self._img_dopo:
            img_r = self._img_dopo.copy()
            img_r.thumbnail((W, H), Image.LANCZOS)
            iw, ih = img_r.size
            ox = (W - iw) // 2
            oy = (H - ih) // 2
            crop_start = split_x - ox
            if crop_start < iw:
                cropped = img_r.crop((max(0, crop_start), 0, iw, ih))
                self._tk_dopo = self._pil_to_tk(cropped)
                paste_x = ox + max(0, crop_start)
                self.create_image(paste_x, oy, image=self._tk_dopo, anchor="nw")

        # --- Linea slider ---
        self.create_line(split_x, 0, split_x, H,
                         fill=COLORI["slider_line"], width=SLIDER_W)

        # --- Maniglia circolare ---
        if self._show_handle:
            cy = H // 2
            r  = HANDLE_R
            self.create_oval(split_x - r, cy - r, split_x + r, cy + r,
                             fill="#ffffff", outline=COLORI["accent"], width=2)
            # Frecce ‹ ›
            self.create_text(split_x, cy,
                             text="◀▶", fill=COLORI["accent"],
                             font=("Segoe UI", 8, "bold"))

        # --- Label PRIMA / DOPO ---
        if self._show_labels:
            pad = 12
            if split_x > 70:
                self.create_text(pad, pad + 6,
                                 text="PRIMA", anchor="nw",
                                 fill=COLORI["label_prima"],
                                 font=("Segoe UI", 11, "bold"))
            if split_x < W - 70:
                self.create_text(W - pad, pad + 6,
                                 text="DOPO", anchor="ne",
                                 fill=COLORI["label_dopo"],
                                 font=("Segoe UI", 11, "bold"))

    @staticmethod
    def _pil_to_tk(img: Image.Image) -> tk.PhotoImage:
        buf = io.BytesIO()
        img.save(buf, format="PPM")
        buf.seek(0)
        return tk.PhotoImage(data=buf.read())

    # ------------------------------------------------------------------
    # Interazione mouse
    # ------------------------------------------------------------------

    def _on_press(self, event):
        self._dragging = True
        self._update_slider(event.x)

    def _on_drag(self, event):
        if self._dragging:
            self._update_slider(event.x)

    def _on_release(self, event):
        self._dragging = False

    def _update_slider(self, x: int):
        W = self.winfo_width()
        if W > 0:
            self._slider_pct = max(0.02, min(0.98, x / W))
            self._render()

    def slider_step(self, delta: float):
        """Sposta lo slider di delta (es. +0.05 o -0.05)."""
        self._slider_pct = max(0.02, min(0.98, self._slider_pct + delta))
        self._render()

    def get_composite(self) -> Optional[Image.Image]:
        """
        Restituisce l'immagine composita attuale (per il salvataggio).
        Unisce le due immagini con la divisione corrente.
        """
        if not self._img_prima or not self._img_dopo:
            return None
        W = max(self._img_prima.width, self._img_dopo.width)
        H = max(self._img_prima.height, self._img_dopo.height)
        out  = Image.new("RGB", (W, H))
        pri  = self._img_prima.resize((W, H), Image.LANCZOS)
        post = self._img_dopo.resize((W, H),  Image.LANCZOS)
        split = int(W * self._slider_pct)
        out.paste(pri.crop((0, 0, split, H)),   (0, 0))
        out.paste(post.crop((split, 0, W, H)),  (split, 0))
        # Linea divisoria
        draw = ImageDraw.Draw(out)
        draw.line([(split, 0), (split, H)], fill="white", width=3)
        return out


# ===========================================================================
# FRAME: BEFORE/AFTER (pannello embedded nella sidebar)
# ===========================================================================

class BeforeAfterFrame(ctk.CTkFrame):
    """
    Pannello completo Before/After da inserire nella navigazione principale.
    """

    def __init__(self, master, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self._row_prima = None
        self._row_dopo  = None
        self._build_ui()

    # ------------------------------------------------------------------

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # ── Barra controlli ───────────────────────────────────────────
        ctrl = ctk.CTkFrame(self, fg_color=COLORI["card"], corner_radius=12)
        ctrl.grid(row=0, column=0, padx=0, pady=(0, 8), sticky="ew")
        ctrl.grid_columnconfigure((1, 3), weight=1)

        ctk.CTkLabel(ctrl, text="🔄  Confronto Before/After",
                     font=FONT_SEZ).grid(
            row=0, column=0, columnspan=6, padx=16, pady=(14, 8), sticky="w")

        # Selezione foto PRIMA
        ctk.CTkLabel(ctrl, text="PRIMA  📷",
                     font=FONT_SML,
                     text_color=COLORI["label_prima"]).grid(
            row=1, column=0, padx=(16, 6), pady=(0, 12))

        self._lbl_prima = ctk.CTkLabel(
            ctrl, text="Nessuna foto selezionata",
            font=FONT_MICRO, text_color=COLORI["grigio"],
            anchor="w", width=220)
        self._lbl_prima.grid(row=1, column=1, padx=(0, 6), pady=(0, 12), sticky="ew")

        ctk.CTkButton(ctrl, text="Scegli…",
                      font=FONT_SML, width=86, height=30,
                      fg_color=COLORI["accent"],
                      command=lambda: self._apri_picker("prima")).grid(
            row=1, column=2, padx=(0, 20), pady=(0, 12))

        # Separatore
        ctk.CTkFrame(ctrl, width=1, height=30,
                     fg_color=COLORI["divider"]).grid(
            row=1, column=3, pady=(0, 12))

        # Selezione foto DOPO
        ctk.CTkLabel(ctrl, text="DOPO  📷",
                     font=FONT_SML,
                     text_color=COLORI["label_dopo"]).grid(
            row=1, column=4, padx=(20, 6), pady=(0, 12))

        self._lbl_dopo = ctk.CTkLabel(
            ctrl, text="Nessuna foto selezionata",
            font=FONT_MICRO, text_color=COLORI["grigio"],
            anchor="w", width=220)
        self._lbl_dopo.grid(row=1, column=5, padx=(0, 6), pady=(0, 12), sticky="ew")

        ctk.CTkButton(ctrl, text="Scegli…",
                      font=FONT_SML, width=86, height=30,
                      fg_color=COLORI["accent"],
                      command=lambda: self._apri_picker("dopo")).grid(
            row=1, column=6, padx=(0, 6), pady=(0, 12))

        # Auto-match e azioni
        btn_row = ctk.CTkFrame(ctrl, fg_color="transparent")
        btn_row.grid(row=2, column=0, columnspan=7,
                     padx=16, pady=(0, 12), sticky="ew")

        ctk.CTkButton(btn_row, text="🔍  Auto Pre-op/Post-op",
                      font=FONT_SML, height=30,
                      fg_color="#1a4a7a",
                      command=self._auto_match).pack(side="left", padx=(0, 6))
        ctk.CTkButton(btn_row, text="⇄  Scambia",
                      font=FONT_SML, height=30,
                      fg_color="transparent", border_width=1,
                      command=self._swap).pack(side="left", padx=(0, 6))
        ctk.CTkButton(btn_row, text="💾  Salva immagine",
                      font=FONT_SML, height=30,
                      fg_color=COLORI["verde"], hover_color="#2a9b52",
                      text_color="#000000",
                      command=self._salva).pack(side="left", padx=(0, 6))

        # Hint slider
        ctk.CTkLabel(btn_row,
                     text="◀ ▶ per spostare lo slider  |  trascina con il mouse",
                     font=("Segoe UI", 8),
                     text_color=COLORI["grigio"]).pack(side="right", padx=(0, 4))

        # ── Canvas Before/After ───────────────────────────────────────
        self._ba = BeforeAfterCanvas(self, width=800, height=480)
        self._ba.grid(row=1, column=0, sticky="nsew")

        # Bind tastiera
        self.bind_all("<Left>",  lambda e: self._ba.slider_step(-0.05))
        self.bind_all("<Right>", lambda e: self._ba.slider_step(+0.05))

    # ------------------------------------------------------------------

    def _apri_picker(self, lato: str):
        """Apre il dialog di selezione foto e aggiorna il lato specificato."""
        picker = FotoPickerBA(self)
        self.wait_window(picker)
        if picker.row_selezionata is not None:
            if lato == "prima":
                self._row_prima = picker.row_selezionata
                self._aggiorna_label(self._lbl_prima, picker.row_selezionata)
            else:
                self._row_dopo = picker.row_selezionata
                self._aggiorna_label(self._lbl_dopo, picker.row_selezionata)
            self._ricarica_canvas()

    def _aggiorna_label(self, lbl: ctk.CTkLabel, r):
        lbl.configure(
            text=f"{r['cognome']} {r['nome']}  |  "
                 f"{r['dente'] or '—'}  {r['fase'] or '—'}  {r['data_scatto'] or '—'}",
            text_color=COLORI["chiaro"])

    def _swap(self):
        self._row_prima, self._row_dopo = self._row_dopo, self._row_prima
        for lbl, row in [(self._lbl_prima, self._row_prima),
                         (self._lbl_dopo,  self._row_dopo)]:
            if row:
                self._aggiorna_label(lbl, row)
            else:
                lbl.configure(text="Nessuna foto selezionata",
                              text_color=COLORI["grigio"])
        self._ricarica_canvas()

    def _ricarica_canvas(self):
        p_prima = db.get_percorso_assoluto(self._row_prima) if self._row_prima else None
        p_dopo  = db.get_percorso_assoluto(self._row_dopo)  if self._row_dopo  else None
        self._ba.carica(p_prima, p_dopo)

    def _auto_match(self):
        """
        Cerca automaticamente la coppia Pre-op / Post-op più recente
        con lo stesso dente e branca.
        """
        dialog = AutoMatchDialog(self, on_match=self._imposta_coppia)

    def _imposta_coppia(self, row_prima, row_dopo):
        self._row_prima = row_prima
        self._row_dopo  = row_dopo
        self._aggiorna_label(self._lbl_prima, row_prima)
        self._aggiorna_label(self._lbl_dopo,  row_dopo)
        self._ricarica_canvas()

    def _salva(self):
        composita = self._ba.get_composite()
        if composita is None:
            messagebox.showwarning("Nessuna immagine",
                                   "Seleziona entrambe le foto prima di salvare.",
                                   parent=self)
            return
        path = filedialog.asksaveasfilename(
            title="Salva confronto",
            defaultextension=".jpg",
            filetypes=[("JPEG", "*.jpg"), ("PNG", "*.png")],
            initialfile=f"confronto_{date.today().isoformat()}.jpg",
        )
        if path:
            composita.save(path, quality=92)
            messagebox.showinfo("Salvato", f"Immagine salvata:\n{path}", parent=self)


# ===========================================================================
# DIALOG: Selezione foto per il confronto
# ===========================================================================

class FotoPickerBA(ctk.CTkToplevel):
    """
    Dialog compatto: cerca paziente → seleziona foto dalla galleria.
    """

    def __init__(self, master):
        super().__init__(master)
        self.title("Seleziona Foto")
        self.geometry("720x500")
        self.resizable(True, True)
        self.grab_set()
        self.row_selezionata = None
        self._thumbs: list = []
        self.after(50, lambda: (self.lift(), self.focus_force(),
                                self.attributes("-topmost", True),
                                self.after(200, lambda: self.attributes("-topmost", False))))
        self._build_ui()

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        # Barra ricerca
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.grid(row=0, column=0, padx=12, pady=(12, 6), sticky="ew")
        top.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(top, text="Paziente:", font=FONT_SML).grid(
            row=0, column=0, padx=(0, 8))
        self._entry = ctk.CTkEntry(top, font=FONT_NRM, height=34,
                                   placeholder_text="Cerca per cognome…")
        self._entry.grid(row=0, column=1, sticky="ew", padx=(0, 8))
        self._entry.bind("<Return>", lambda e: self._cerca())
        ctk.CTkButton(top, text="🔍", width=36, height=34,
                      command=self._cerca).grid(row=0, column=2)

        # Filtro fase
        self._combo_fase = ctk.CTkComboBox(
            top, values=["(tutte)"] + db.FASI,
            font=FONT_NRM, height=34, width=140, state="readonly")
        self._combo_fase.set("(tutte)")
        self._combo_fase.grid(row=0, column=3, padx=(8, 0))

        self._lbl_count = ctk.CTkLabel(self, text="",
                                        font=FONT_MICRO,
                                        text_color=COLORI["grigio"])
        self._lbl_count.grid(row=1, column=0, padx=14, pady=(0, 4), sticky="w")

        # Galleria
        self._scroll = ctk.CTkScrollableFrame(self, fg_color=COLORI["card"],
                                               corner_radius=12)
        self._scroll.grid(row=2, column=0, padx=12, pady=(0, 12), sticky="nsew")
        for c in range(5):
            self._scroll.grid_columnconfigure(c, weight=1)

        ctk.CTkLabel(self._scroll, text="← Cerca un paziente",
                     font=FONT_SML, text_color=COLORI["grigio"]).grid(
            row=0, column=0, columnspan=5, pady=30)

    def _cerca(self):
        testo  = self._entry.get().strip()
        fase_f = self._combo_fase.get()
        fase   = None if fase_f.startswith("(") else fase_f

        pazienti = db.cerca_pazienti(testo)
        paz_id   = None
        if len(pazienti) == 1:
            paz_id = pazienti[0]["id"]

        righe = db.cerca_foto(paziente_id=paz_id, fase=fase)
        # Filtra ulteriormente per nome se multipli
        if testo and not paz_id:
            righe = [r for r in righe
                     if testo.lower() in r["cognome"].lower()
                     or testo.lower() in r["nome"].lower()]

        self._lbl_count.configure(text=f"{len(righe)} foto trovate")
        self._riempie_griglia(list(righe))

    def _riempie_griglia(self, righe: list):
        for w in self._scroll.winfo_children():
            w.destroy()
        self._thumbs.clear()

        if not righe:
            ctk.CTkLabel(self._scroll, text="Nessuna foto trovata.",
                         font=FONT_SML, text_color=COLORI["grigio"]).grid(
                row=0, column=0, columnspan=5, pady=20)
            return

        for idx, r in enumerate(righe):
            row, col = divmod(idx, 5)
            self._mini_card(row, col, r)

    def _mini_card(self, row: int, col: int, r):
        card = ctk.CTkFrame(self._scroll, fg_color=COLORI["entry_bg"],
                            corner_radius=8, cursor="hand2")
        card.grid(row=row, column=col, padx=4, pady=4, sticky="nsew")
        card.grid_columnconfigure(0, weight=1)

        percorso = db.get_percorso_assoluto(r)
        try:
            img = Image.open(percorso)
            img.thumbnail((110, 85), Image.LANCZOS)
            th = ctk.CTkImage(light_image=img, dark_image=img, size=img.size)
        except Exception:
            ph = Image.new("RGB", (110, 85), (30, 35, 55))
            th = ctk.CTkImage(light_image=ph, dark_image=ph, size=(110, 85))
        self._thumbs.append(th)

        lbl_img = ctk.CTkLabel(card, image=th, text="", cursor="hand2")
        lbl_img.grid(row=0, column=0, padx=3, pady=(5, 2))

        # Fase colorata
        fase_col = {"Pre-op": COLORI["label_prima"],
                    "Post-op": COLORI["label_dopo"]}.get(r["fase"] or "", COLORI["grigio"])
        ctk.CTkLabel(card, text=r["fase"] or "—",
                     font=("Segoe UI", 8, "bold"),
                     text_color=fase_col).grid(row=1, column=0)
        ctk.CTkLabel(card, text=f"{r['cognome']} {r['nome']}",
                     font=("Segoe UI", 8),
                     text_color=COLORI["grigio"],
                     wraplength=108).grid(row=2, column=0, pady=(0, 5))

        for w in (card, lbl_img):
            w.bind("<Button-1>", lambda e, rr=r: self._seleziona(rr))
            w.bind("<Enter>",    lambda e, f=card: f.configure(fg_color=COLORI["accent"]))
            w.bind("<Leave>",    lambda e, f=card: f.configure(fg_color=COLORI["entry_bg"]))

    def _seleziona(self, r):
        self.row_selezionata = r
        self.destroy()


# ===========================================================================
# DIALOG: Auto-match Pre-op / Post-op
# ===========================================================================

class AutoMatchDialog(ctk.CTkToplevel):
    """
    Cerca coppie Pre-op / Post-op dello stesso paziente e dente.
    """

    def __init__(self, master, on_match):
        super().__init__(master)
        self.title("Auto-match Pre-op / Post-op")
        self.geometry("640x460")
        self.resizable(True, True)
        self.grab_set()
        self._on_match = on_match
        self._coppie: list = []
        self.after(50, lambda: (self.lift(), self.focus_force(),
                                self.attributes("-topmost", True),
                                self.after(200, lambda: self.attributes("-topmost", False))))
        self._build_ui()
        self._cerca_coppie()

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(self, text="Coppie Pre-op / Post-op trovate",
                     font=FONT_SEZ).grid(
            row=0, column=0, padx=16, pady=(16, 8), sticky="w")

        self._scroll = ctk.CTkScrollableFrame(self, fg_color=COLORI["card"],
                                               corner_radius=12)
        self._scroll.grid(row=1, column=0, padx=12, pady=(0, 12), sticky="nsew")
        self._scroll.grid_columnconfigure(0, weight=1)

    def _cerca_coppie(self):
        """
        Unisce le foto per paziente+dente+branca, poi accoppia Pre-op con Post-op.
        """
        pre  = db.cerca_foto(fase="Pre-op")
        post = db.cerca_foto(fase="Post-op")

        # Indicizza post per (paziente_id, dente, branca)
        idx_post: dict = {}
        for r in post:
            k = (r["paziente_id"], r["dente"] or "", r["branca"] or "")
            idx_post.setdefault(k, []).append(r)

        coppie = []
        for r_pre in pre:
            k = (r_pre["paziente_id"], r_pre["dente"] or "", r_pre["branca"] or "")
            if k in idx_post:
                # Prende il post-op più recente
                r_post = sorted(idx_post[k],
                                key=lambda x: x["data_scatto"] or "", reverse=True)[0]
                coppie.append((r_pre, r_post))

        self._coppie = coppie
        self._riempie(coppie)

    def _riempie(self, coppie: list):
        for w in self._scroll.winfo_children():
            w.destroy()
        if not coppie:
            ctk.CTkLabel(self._scroll,
                         text="Nessuna coppia Pre-op / Post-op trovata\n"
                              "per lo stesso paziente e dente.",
                         font=FONT_SML, text_color=COLORI["grigio"],
                         justify="center").grid(row=0, column=0, pady=30)
            return

        for i, (pre, post) in enumerate(coppie):
            self._riga_coppia(i, pre, post)

    def _riga_coppia(self, idx: int, pre, post):
        riga = ctk.CTkFrame(self._scroll, fg_color=COLORI["entry_bg"],
                            corner_radius=8)
        riga.grid(row=idx, column=0, padx=6, pady=4, sticky="ew")
        riga.grid_columnconfigure(1, weight=1)

        # Thumb prima
        try:
            img_p = Image.open(db.get_percorso_assoluto(pre))
            img_p.thumbnail((72, 56), Image.LANCZOS)
            th_p = ctk.CTkImage(light_image=img_p, dark_image=img_p, size=img_p.size)
        except Exception:
            ph = Image.new("RGB", (72, 56), (30, 35, 55))
            th_p = ctk.CTkImage(light_image=ph, dark_image=ph, size=(72, 56))

        # Thumb dopo
        try:
            img_d = Image.open(db.get_percorso_assoluto(post))
            img_d.thumbnail((72, 56), Image.LANCZOS)
            th_d = ctk.CTkImage(light_image=img_d, dark_image=img_d, size=img_d.size)
        except Exception:
            ph = Image.new("RGB", (72, 56), (30, 35, 55))
            th_d = ctk.CTkImage(light_image=ph, dark_image=ph, size=(72, 56))

        ctk.CTkLabel(riga, image=th_p, text="").grid(
            row=0, column=0, rowspan=2, padx=(8, 4), pady=6)

        info = (f"{pre['cognome']} {pre['nome']}  |  "
                f"🦷 {pre['dente'] or '—'}  "
                f"🏥 {pre['branca'] or '—'}")
        ctk.CTkLabel(riga, text=info,
                     font=FONT_NRM, anchor="w").grid(
            row=0, column=1, sticky="ew", padx=4, pady=(6, 2))
        ctk.CTkLabel(riga,
                     text=f"Pre-op: {pre['data_scatto'] or '—'}   →   "
                          f"Post-op: {post['data_scatto'] or '—'}",
                     font=FONT_MICRO, text_color=COLORI["grigio"],
                     anchor="w").grid(row=1, column=1, sticky="ew", padx=4)

        ctk.CTkLabel(riga, image=th_d, text="").grid(
            row=0, column=2, rowspan=2, padx=(4, 4), pady=6)

        ctk.CTkButton(riga, text="Confronta →",
                      font=FONT_SML, width=100, height=32,
                      fg_color=COLORI["accent_br"],
                      command=lambda p=pre, d=post: self._usa(p, d)).grid(
            row=0, column=3, rowspan=2, padx=(4, 8))

    def _usa(self, pre, post):
        self._on_match(pre, post)
        self.destroy()


__all__ = ["BeforeAfterFrame"]

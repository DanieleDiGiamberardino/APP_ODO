"""
ui_viewer.py
============
Visualizzatore fotografico full-screen con:
  - Zoom in/out con rotella del mouse (fino a 8×)
  - Pan (trascinamento con click sinistro)
  - Fit-to-window / zoom reale (pulsanti)
  - Navigazione prev/next tra i risultati di una galleria
  - Overlay metadati clinici (toggle con tasto M)
  - Tasto ESC per chiudere

Uso:
    from ui_viewer import ViewerFoto
    ViewerFoto(master, foto_rows=lista_rows_db, indice_iniziale=0)

    oppure per aprire una singola foto:
    ViewerFoto(master, foto_rows=[singola_row], indice_iniziale=0)
"""

import tkinter as tk
import customtkinter as ctk
from PIL import Image, ImageDraw, ImageFont
from pathlib import Path
from typing import Optional
import math

import database as db

# ---------------------------------------------------------------------------
# Palette
# ---------------------------------------------------------------------------

COLORI = {
    "sfondo":        "#0a0a14",
    "overlay_bg":    "#000000cc",
    "testo_chiaro":  "#e0e0e0",
    "testo_grigio":  "#9e9e9e",
    "accent":        "#0f3460",
    "accent_bright": "#e94560",
    "verde_ok":      "#4caf50",
    "ctrl_bg":       "#1a1a2e",
    "ctrl_btn":      "#16213e",
}

# Limiti zoom
ZOOM_MIN = 0.1
ZOOM_MAX = 8.0
ZOOM_STEP = 0.15   # delta moltiplicativo per ogni scroll


# ===========================================================================
# FINESTRA VIEWER
# ===========================================================================

class ViewerFoto(ctk.CTkToplevel):
    """
    Finestra di visualizzazione full-screen.

    Args:
        master:          widget Tk padre
        foto_rows:       lista di sqlite3.Row (output di db.cerca_foto)
        indice_iniziale: indice dell'immagine da mostrare all'apertura
    """

    def __init__(self, master, foto_rows: list, indice_iniziale: int = 0):
        super().__init__(master)

        self._righe    = foto_rows
        self._indice   = max(0, min(indice_iniziale, len(foto_rows) - 1))
        self._zoom     = 1.0
        self._offset_x = 0
        self._offset_y = 0
        self._drag_x   = 0
        self._drag_y   = 0
        self._mostra_meta = True

        # Immagine PIL originale (full-res, ricaricata ad ogni navigazione)
        self._pil_originale: Optional[Image.Image] = None
        # PhotoImage per tk.Canvas (riferimento anti-GC)
        self._tk_image: Optional[tk.PhotoImage] = None

        self._build_ui()
        self._carica_immagine(self._indice)
        # Porta la finestra in primo piano — fix "apre in background" su Windows
        self.after(50, self._porta_in_primo_piano)

    def _porta_in_primo_piano(self):
        self.lift()
        self.focus_force()
        self.attributes("-topmost", True)
        self.after(200, lambda: self.attributes("-topmost", False))

        # Tasto ESC per chiudere
        self.bind("<Escape>", lambda e: self.destroy())
        # M per toggle metadati
        self.bind("<m>", lambda e: self._toggle_meta())
        self.bind("<M>", lambda e: self._toggle_meta())
        # Frecce per navigazione
        self.bind("<Left>",  lambda e: self._naviga(-1))
        self.bind("<Right>", lambda e: self._naviga(+1))
        # +/- per zoom da tastiera
        self.bind("<plus>",  lambda e: self._zoom_tastiera(+1))
        self.bind("<minus>", lambda e: self._zoom_tastiera(-1))

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self):
        self.title("DentalPhoto — Visualizzatore")
        self.geometry("1100x780")
        self.minsize(600, 450)
        self.configure(fg_color=COLORI["sfondo"])

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=0)

        # Canvas principale (immagine)
        self._canvas = tk.Canvas(
            self,
            bg=COLORI["sfondo"],
            highlightthickness=0,
            cursor="fleur",
        )
        self._canvas.grid(row=0, column=0, sticky="nsew")

        # Binding mouse sul canvas
        self._canvas.bind("<ButtonPress-1>",   self._drag_start)
        self._canvas.bind("<B1-Motion>",       self._drag_move)
        self._canvas.bind("<MouseWheel>",      self._scroll_zoom)     # Windows/macOS
        self._canvas.bind("<Button-4>",        self._scroll_zoom)     # Linux scroll up
        self._canvas.bind("<Button-5>",        self._scroll_zoom)     # Linux scroll down
        self._canvas.bind("<Configure>",       lambda e: self._ridisegna())

        # Barra controlli in basso
        ctrl = ctk.CTkFrame(self, fg_color=COLORI["ctrl_bg"], height=52, corner_radius=0)
        ctrl.grid(row=1, column=0, sticky="ew")
        ctrl.grid_propagate(False)

        # Navigazione
        self._btn_prev = ctk.CTkButton(
            ctrl, text="◀", width=40, height=36, font=("Segoe UI", 14),
            fg_color=COLORI["ctrl_btn"],
            command=lambda: self._naviga(-1))
        self._btn_prev.pack(side="left", padx=(12, 4), pady=8)

        self._lbl_indice = ctk.CTkLabel(
            ctrl, text="", font=("Segoe UI", 11),
            text_color=COLORI["testo_grigio"], width=80)
        self._lbl_indice.pack(side="left", padx=4)

        self._btn_next = ctk.CTkButton(
            ctrl, text="▶", width=40, height=36, font=("Segoe UI", 14),
            fg_color=COLORI["ctrl_btn"],
            command=lambda: self._naviga(+1))
        self._btn_next.pack(side="left", padx=(4, 16))

        # Separatore
        ctk.CTkFrame(ctrl, width=1, height=32,
                     fg_color=COLORI["accent"]).pack(side="left", padx=8)

        # Zoom
        ctk.CTkButton(ctrl, text="🔍−", width=40, height=36, font=("Segoe UI", 13),
                      fg_color=COLORI["ctrl_btn"],
                      command=lambda: self._zoom_tastiera(-1)).pack(side="left", padx=4)

        self._lbl_zoom = ctk.CTkLabel(ctrl, text="100%", font=("Segoe UI", 11),
                                       text_color=COLORI["testo_chiaro"], width=54)
        self._lbl_zoom.pack(side="left", padx=4)

        ctk.CTkButton(ctrl, text="🔍+", width=40, height=36, font=("Segoe UI", 13),
                      fg_color=COLORI["ctrl_btn"],
                      command=lambda: self._zoom_tastiera(+1)).pack(side="left", padx=4)

        ctk.CTkButton(ctrl, text="Fit", width=40, height=36, font=("Segoe UI", 11),
                      fg_color=COLORI["ctrl_btn"],
                      command=self._zoom_fit).pack(side="left", padx=(8, 4))

        ctk.CTkButton(ctrl, text="1:1", width=40, height=36, font=("Segoe UI", 11),
                      fg_color=COLORI["ctrl_btn"],
                      command=self._zoom_reale).pack(side="left", padx=4)

        # Separatore
        ctk.CTkFrame(ctrl, width=1, height=32,
                     fg_color=COLORI["accent"]).pack(side="left", padx=8)

        # Toggle metadati
        self._btn_meta = ctk.CTkButton(
            ctrl, text="📋 Info", width=70, height=36, font=("Segoe UI", 11),
            fg_color=COLORI["accent"],
            command=self._toggle_meta)
        self._btn_meta.pack(side="left", padx=4)

        # Titolo foto (lato destro)
        self._lbl_titolo = ctk.CTkLabel(
            ctrl, text="", font=("Segoe UI", 10),
            text_color=COLORI["testo_grigio"], anchor="e")
        self._lbl_titolo.pack(side="right", padx=16)

        # ESC hint
        ctk.CTkLabel(ctrl, text="ESC chiudi  |  M meta  |  ← →",
                     font=("Segoe UI", 8),
                     text_color=COLORI["testo_grigio"]).pack(side="right", padx=8)

    # ------------------------------------------------------------------
    # Caricamento e rendering
    # ------------------------------------------------------------------

    def _carica_immagine(self, idx: int):
        """Carica l'immagine al dato indice dal DB e aggiorna il canvas."""
        if not self._righe:
            return

        r = self._righe[idx]
        percorso = db.get_percorso_assoluto(r)

        try:
            self._pil_originale = Image.open(percorso).convert("RGB")
        except Exception:
            # Placeholder errore
            self._pil_originale = Image.new("RGB", (800, 600), (30, 30, 45))
            draw = ImageDraw.Draw(self._pil_originale)
            draw.text((300, 280), "File non disponibile", fill=(150, 150, 150))

        # Calcola zoom fit iniziale
        self._zoom_fit(ridisegna=False)

        # Reset pan al centro
        self._offset_x = 0
        self._offset_y = 0

        # Aggiorna label
        n = len(self._righe)
        self._lbl_indice.configure(text=f"{idx + 1} / {n}")
        self._lbl_titolo.configure(
            text=f"{r['cognome']} {r['nome']}  |  "
                 f"{r['branca'] or '—'} / {r['dente'] or '—'} / {r['fase'] or '—'}")

        # Abilita/disabilita frecce
        self._btn_prev.configure(state="normal" if idx > 0 else "disabled")
        self._btn_next.configure(state="normal" if idx < n - 1 else "disabled")

        self._ridisegna()

    def _ridisegna(self):
        """Ridisegna il canvas con l'immagine corrente a zoom/pan correnti."""
        if self._pil_originale is None:
            return

        cw = self._canvas.winfo_width()
        ch = self._canvas.winfo_height()
        if cw < 10 or ch < 10:
            return

        w_orig, h_orig = self._pil_originale.size
        new_w = max(1, int(w_orig * self._zoom))
        new_h = max(1, int(h_orig * self._zoom))

        # Ridimensiona con Pillow (NEAREST sopra 2× per performance, LANCZOS sotto)
        filtro = Image.NEAREST if self._zoom > 2.0 else Image.LANCZOS
        img_resized = self._pil_originale.resize((new_w, new_h), filtro)

        # Posizione centro + offset pan
        x = cw // 2 + self._offset_x
        y = ch // 2 + self._offset_y

        # Converti in PhotoImage (tk)
        self._tk_image = self._pil_to_tk(img_resized)

        self._canvas.delete("all")
        self._canvas.create_image(x, y, image=self._tk_image, anchor="center")

        # Overlay metadati
        if self._mostra_meta and self._righe:
            self._disegna_overlay(cw, ch)

        # Label zoom
        self._lbl_zoom.configure(text=f"{int(self._zoom * 100)}%")

    @staticmethod
    def _pil_to_tk(img: Image.Image) -> tk.PhotoImage:
        """Converte un'immagine PIL in PhotoImage senza dipendenze extra."""
        import io
        buf = io.BytesIO()
        img.save(buf, format="PPM")
        buf.seek(0)
        return tk.PhotoImage(data=buf.read())

    def _disegna_overlay(self, cw: int, ch: int):
        """Disegna il pannello semitrasparente dei metadati in alto a sinistra."""
        r = self._righe[self._indice]

        righe_meta = [
            f"👤  {r['cognome']} {r['nome']}",
            f"🦷  {r['dente'] or '—'}",
            f"🏥  {r['branca'] or '—'}",
            f"🔬  {r['fase'] or '—'}",
            f"📅  {r['data_scatto'] or '—'}",
        ]
        if r["note"]:
            righe_meta.append(f"📝  {r['note'][:50]}")

        box_w = 260
        line_h = 20
        pad = 10
        box_h = len(righe_meta) * line_h + pad * 2

        x0, y0 = 16, 16
        x1, y1 = x0 + box_w, y0 + box_h

        # Sfondo scuro semitrasparente (stipple per simulare trasparenza su tk)
        self._canvas.create_rectangle(
            x0, y0, x1, y1,
            fill="#000000", stipple="gray50", outline="",
        )
        self._canvas.create_rectangle(
            x0, y0, x1, y1,
            fill="", outline="#0f3460", width=1,
        )

        # Testo righe
        for i, testo in enumerate(righe_meta):
            self._canvas.create_text(
                x0 + pad, y0 + pad + i * line_h,
                text=testo,
                anchor="nw",
                fill="#e0e0e0",
                font=("Segoe UI", 9),
            )

    # ------------------------------------------------------------------
    # Zoom
    # ------------------------------------------------------------------

    def _zoom_fit(self, ridisegna: bool = True):
        """Adatta l'immagine alla finestra."""
        if self._pil_originale is None:
            return
        self.update_idletasks()
        cw = self._canvas.winfo_width()
        ch = self._canvas.winfo_height()
        if cw < 10 or ch < 10:
            self._zoom = 1.0
            return
        w, h = self._pil_originale.size
        self._zoom = min(cw / w, ch / h, 1.0)
        self._offset_x = 0
        self._offset_y = 0
        if ridisegna:
            self._ridisegna()

    def _zoom_reale(self):
        """Zoom 1:1."""
        self._zoom = 1.0
        self._offset_x = 0
        self._offset_y = 0
        self._ridisegna()

    def _zoom_tastiera(self, direzione: int):
        delta = ZOOM_STEP * direzione
        self._zoom = max(ZOOM_MIN, min(ZOOM_MAX, self._zoom + delta))
        self._ridisegna()

    def _scroll_zoom(self, event: tk.Event):
        """Zoom con la rotella del mouse, centrato sul cursore."""
        # Determina la direzione della rotella (Windows/macOS vs Linux)
        if event.num == 4 or event.delta > 0:
            factor = 1 + ZOOM_STEP
        else:
            factor = 1 - ZOOM_STEP

        nuovo_zoom = max(ZOOM_MIN, min(ZOOM_MAX, self._zoom * factor))

        if nuovo_zoom != self._zoom:
            # Zoom verso il cursore: aggiusta l'offset
            cw = self._canvas.winfo_width()
            ch = self._canvas.winfo_height()
            dx = event.x - cw // 2 - self._offset_x
            dy = event.y - ch // 2 - self._offset_y
            scala = nuovo_zoom / self._zoom
            self._offset_x += dx * (1 - scala)
            self._offset_y += dy * (1 - scala)
            self._zoom = nuovo_zoom
            self._ridisegna()

    # ------------------------------------------------------------------
    # Pan
    # ------------------------------------------------------------------

    def _drag_start(self, event: tk.Event):
        self._drag_x = event.x
        self._drag_y = event.y

    def _drag_move(self, event: tk.Event):
        dx = event.x - self._drag_x
        dy = event.y - self._drag_y
        self._offset_x += dx
        self._offset_y += dy
        self._drag_x = event.x
        self._drag_y = event.y
        self._ridisegna()

    # ------------------------------------------------------------------
    # Navigazione
    # ------------------------------------------------------------------

    def _naviga(self, delta: int):
        nuovo = self._indice + delta
        if 0 <= nuovo < len(self._righe):
            self._indice = nuovo
            self._zoom   = 1.0
            self._offset_x = 0
            self._offset_y = 0
            self._carica_immagine(self._indice)

    # ------------------------------------------------------------------
    # Metadati
    # ------------------------------------------------------------------

    def _toggle_meta(self):
        self._mostra_meta = not self._mostra_meta
        col = COLORI["accent_bright"] if self._mostra_meta else COLORI["ctrl_btn"]
        self._btn_meta.configure(fg_color=col)
        self._ridisegna()

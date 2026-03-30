"""
ui_modifica_tag.py
==================
Pannello dedicato alla modifica dei tag clinici di una fotografia.

Layout:
  ┌────────────────────────────────────────────────┐
  │  [Cerca foto]  Barra ricerca per ID o paziente │
  ├──────────────────────┬─────────────────────────┤
  │                      │  PAZIENTE               │
  │   ANTEPRIMA          │  Data scatto            │
  │   IMMAGINE           │  File                   │
  │   (grande)           ├─────────────────────────┤
  │                      │  Dente     ▼            │
  │                      │  Branca    ▼            │
  │                      │  Fase      ▼            │
  │                      │  Note      □            │
  │                      │  [💾 Salva Modifiche]  │
  └──────────────────────┴─────────────────────────┘

Apertura da sidebar o da callback _on_modifica_tag(foto_id).
"""

import customtkinter as ctk
from PIL import Image
from pathlib import Path
from typing import Optional

import database as db

# ---------------------------------------------------------------------------
COLORI = {
    "bg":           "#0d1117",
    "card":         "#16213e",
    "entry_bg":     "#0a0f1e",
    "accent":       "#0f3460",
    "accent_br":    "#e94560",
    "verde":        "#4caf50",
    "grigio":       "#9e9e9e",
    "chiaro":       "#e0e0e0",
    "rosso":        "#f44336",
    "preview_bg":   "#080c18",
    "divider":      "#1e2d4a",
    "tag_saved":    "#0d2b0d",
}

FONT_SEZ   = ("Segoe UI", 13, "bold")
FONT_NRM   = ("Segoe UI", 12)
FONT_SML   = ("Segoe UI", 10)
FONT_MICRO = ("Segoe UI", 9)
FONT_MONO  = ("Consolas", 9)


# ===========================================================================
# FRAME: MODIFICA TAG
# ===========================================================================

class ModificaTagFrame(ctk.CTkFrame):
    """
    Editor completo dei tag clinici di una singola foto.
    Mostra l'immagine in anteprima grande a sinistra e i controlli a destra.
    """

    def __init__(self, master, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self._foto_id: Optional[int] = None
        self._foto_row = None
        self._thumb_ref = None      # anti-GC
        self._build_ui()

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # ── Barra di ricerca / selezione foto ─────────────────────────
        search_card = ctk.CTkFrame(self, fg_color=COLORI["card"], corner_radius=12)
        search_card.grid(row=0, column=0, padx=0, pady=(0, 10), sticky="ew")
        search_card.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(search_card, text="✏️  Seleziona la foto da modificare",
                     font=FONT_SEZ).grid(row=0, column=0, columnspan=4,
                                         padx=20, pady=(14, 10), sticky="w")

        # ID diretto
        ctk.CTkLabel(search_card, text="ID Foto:",
                     font=FONT_SML, text_color=COLORI["grigio"]).grid(
            row=1, column=0, padx=(20, 6), pady=(0, 14), sticky="w")

        self._entry_id = ctk.CTkEntry(
            search_card, placeholder_text="es. 42",
            font=FONT_NRM, height=36, width=120)
        self._entry_id.grid(row=1, column=1, padx=(0, 6), pady=(0, 14), sticky="w")
        self._entry_id.bind("<Return>", lambda e: self._carica_da_id())

        ctk.CTkButton(search_card, text="Carica",
                      font=FONT_NRM, width=90, height=36,
                      command=self._carica_da_id).grid(
            row=1, column=2, padx=(0, 16), pady=(0, 14))

        # Separatore verticale
        ctk.CTkFrame(search_card, width=1, height=36,
                     fg_color=COLORI["divider"]).grid(
            row=1, column=3, padx=6, pady=(0, 14))

        # Ricerca per paziente (combo popolato)
        ctk.CTkLabel(search_card, text="oppure scegli dal paziente:",
                     font=FONT_SML, text_color=COLORI["grigio"]).grid(
            row=1, column=4, padx=(12, 6), pady=(0, 14), sticky="w")

        self._combo_paz_search = ctk.CTkEntry(
            search_card, placeholder_text="Cognome paziente…",
            font=FONT_NRM, height=36, width=200)
        self._combo_paz_search.grid(row=1, column=5, padx=(0, 6), pady=(0, 14), sticky="w")
        self._combo_paz_search.bind("<Return>", lambda e: self._apri_picker_foto())

        ctk.CTkButton(search_card, text="Sfoglia",
                      font=FONT_NRM, width=90, height=36,
                      fg_color=COLORI["accent"],
                      command=self._apri_picker_foto).grid(
            row=1, column=6, padx=(0, 20), pady=(0, 14))

        # Messaggio stato ricerca
        self._lbl_search_stato = ctk.CTkLabel(
            search_card, text="Inserisci un ID o sfoglia le foto di un paziente.",
            font=FONT_MICRO, text_color=COLORI["grigio"])
        self._lbl_search_stato.grid(row=2, column=0, columnspan=7,
                                     padx=20, pady=(0, 12), sticky="w")

        # ── Area principale: immagine + editor ────────────────────────
        main = ctk.CTkFrame(self, fg_color="transparent")
        main.grid(row=1, column=0, sticky="nsew")
        main.grid_columnconfigure(0, weight=3)
        main.grid_columnconfigure(1, weight=2)
        main.grid_rowconfigure(0, weight=1)

        # -- Pannello immagine --
        self._img_card = ctk.CTkFrame(main, fg_color=COLORI["card"],
                                       corner_radius=12)
        self._img_card.grid(row=0, column=0, padx=(0, 8), sticky="nsew")
        self._img_card.grid_columnconfigure(0, weight=1)
        self._img_card.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(self._img_card, text="Anteprima",
                     font=FONT_SML, text_color=COLORI["grigio"]).grid(
            row=0, column=0, padx=16, pady=(12, 4), sticky="w")

        # Placeholder iniziale
        self._img_lbl = ctk.CTkLabel(
            self._img_card,
            text="📷\n\nNessuna foto selezionata\n\nUsa la barra sopra per cercare",
            font=FONT_NRM,
            text_color=COLORI["grigio"],
            fg_color=COLORI["preview_bg"],
            corner_radius=8,
            width=400, height=380,
        )
        self._img_lbl.grid(row=1, column=0, padx=12, pady=(0, 12), sticky="nsew")

        # Meta info sotto l'immagine
        self._meta_bar = ctk.CTkFrame(self._img_card,
                                       fg_color=COLORI["preview_bg"],
                                       corner_radius=8)
        self._meta_bar.grid(row=2, column=0, padx=12, pady=(0, 14), sticky="ew")
        self._meta_bar.grid_columnconfigure((0, 1, 2), weight=1)

        self._lbl_meta_paz  = self._meta_chip(self._meta_bar, "👤 —", 0)
        self._lbl_meta_data = self._meta_chip(self._meta_bar, "📅 —", 1)
        self._lbl_meta_file = self._meta_chip(self._meta_bar, "📁 —", 2)

        # -- Pannello editor tag --
        self._tag_card = ctk.CTkFrame(main, fg_color=COLORI["card"],
                                       corner_radius=12)
        self._tag_card.grid(row=0, column=1, padx=(8, 0), sticky="nsew")
        self._tag_card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(self._tag_card, text="Tag Clinici",
                     font=FONT_SEZ,
                     text_color=COLORI["accent_br"]).grid(
            row=0, column=0, padx=20, pady=(20, 4), sticky="w")

        self._lbl_tag_info = ctk.CTkLabel(
            self._tag_card,
            text="Seleziona una foto per modificarne i tag.",
            font=FONT_MICRO, text_color=COLORI["grigio"], wraplength=300)
        self._lbl_tag_info.grid(row=1, column=0, padx=20, pady=(0, 16), sticky="w")

        # Separatore
        ctk.CTkFrame(self._tag_card, height=1, fg_color=COLORI["divider"]).grid(
            row=2, column=0, padx=16, pady=(0, 16), sticky="ew")

        # Dente
        ctk.CTkLabel(self._tag_card, text="🦷  Dente (FDI)", font=FONT_SML,
                     text_color=COLORI["grigio"]).grid(
            row=3, column=0, padx=20, pady=(0, 3), sticky="w")
        self._combo_dente = ctk.CTkComboBox(
            self._tag_card, values=db.DENTI_FDI,
            font=FONT_NRM, height=38,
            fg_color=COLORI["entry_bg"], state="readonly")
        self._combo_dente.set(db.DENTI_FDI[0])
        self._combo_dente.grid(row=4, column=0, padx=20, pady=(0, 12), sticky="ew")

        # Branca
        ctk.CTkLabel(self._tag_card, text="🏥  Branca", font=FONT_SML,
                     text_color=COLORI["grigio"]).grid(
            row=5, column=0, padx=20, pady=(0, 3), sticky="w")
        self._combo_branca = ctk.CTkComboBox(
            self._tag_card, values=db.BRANCHE,
            font=FONT_NRM, height=38,
            fg_color=COLORI["entry_bg"], state="readonly")
        self._combo_branca.set(db.BRANCHE[0])
        self._combo_branca.grid(row=6, column=0, padx=20, pady=(0, 12), sticky="ew")

        # Fase
        ctk.CTkLabel(self._tag_card, text="🔬  Fase Clinica", font=FONT_SML,
                     text_color=COLORI["grigio"]).grid(
            row=7, column=0, padx=20, pady=(0, 3), sticky="w")
        self._combo_fase = ctk.CTkComboBox(
            self._tag_card, values=db.FASI,
            font=FONT_NRM, height=38,
            fg_color=COLORI["entry_bg"], state="readonly")
        self._combo_fase.set(db.FASI[0])
        self._combo_fase.grid(row=8, column=0, padx=20, pady=(0, 12), sticky="ew")

        # Note
        ctk.CTkLabel(self._tag_card, text="📝  Note cliniche", font=FONT_SML,
                     text_color=COLORI["grigio"]).grid(
            row=9, column=0, padx=20, pady=(0, 3), sticky="w")
        self._txt_note = ctk.CTkTextbox(
            self._tag_card, font=FONT_NRM, height=100,
            fg_color=COLORI["entry_bg"])
        self._txt_note.grid(row=10, column=0, padx=20, pady=(0, 16), sticky="ew")

        # Separatore
        ctk.CTkFrame(self._tag_card, height=1,
                     fg_color=COLORI["divider"]).grid(
            row=11, column=0, padx=16, pady=(0, 14), sticky="ew")

        # Pulsante salva
        self._btn_salva = ctk.CTkButton(
            self._tag_card,
            text="💾  Salva Modifiche",
            font=("Segoe UI", 13, "bold"), height=46,
            state="disabled",
            fg_color=COLORI["verde"], hover_color="#388e3c",
            command=self._salva,
        )
        self._btn_salva.grid(row=12, column=0, padx=20, pady=(0, 8), sticky="ew")

        # Pulsante reset (ripristina valori originali)
        self._btn_reset = ctk.CTkButton(
            self._tag_card,
            text="↩  Ripristina originali",
            font=FONT_SML, height=34,
            state="disabled",
            fg_color="transparent", border_width=1,
            command=self._ripristina,
        )
        self._btn_reset.grid(row=13, column=0, padx=20, pady=(0, 8), sticky="ew")

        # Stato operazione
        self._lbl_stato = ctk.CTkLabel(
            self._tag_card, text="",
            font=FONT_SML, text_color=COLORI["verde"])
        self._lbl_stato.grid(row=14, column=0, padx=20, pady=(0, 20))

    @staticmethod
    def _meta_chip(parent, testo, col):
        lbl = ctk.CTkLabel(parent, text=testo, font=FONT_MICRO,
                           text_color=COLORI["grigio"], anchor="center")
        lbl.grid(row=0, column=col, padx=8, pady=6, sticky="ew")
        return lbl

    # ------------------------------------------------------------------
    # Caricamento foto
    # ------------------------------------------------------------------

    def preimposta_id(self, foto_id: int):
        """API pubblica — chiamata da _goto_modifica in App o da DettaglioFoto."""
        self._entry_id.delete(0, "end")
        self._entry_id.insert(0, str(foto_id))
        self._carica_da_id()

    def _carica_da_id(self):
        raw = self._entry_id.get().strip()
        if not raw.isdigit():
            self._set_stato_search("⚠️  ID non valido — inserisci un numero.", "rosso")
            return
        self._carica_foto(int(raw))

    def _carica_foto(self, foto_id: int):
        r = db.get_foto_by_id(foto_id)
        if r is None:
            self._set_stato_search(f"❌  Nessuna foto con ID {foto_id}.", "rosso")
            return

        self._foto_id  = foto_id
        self._foto_row = r
        self._set_stato_search(
            f"✅  Foto #{foto_id} — {r['cognome']} {r['nome']}  "
            f"|  {r['branca'] or '—'} / {r['dente'] or '—'} / {r['fase'] or '—'}",
            "verde")

        # Aggiorna anteprima immagine
        self._aggiorna_preview(db.get_percorso_assoluto(r))

        # Aggiorna meta chips
        self._lbl_meta_paz.configure(
            text=f"👤  {r['cognome']} {r['nome']}")
        self._lbl_meta_data.configure(
            text=f"📅  {r['data_scatto'] or '—'}")
        self._lbl_meta_file.configure(
            text=f"📁  {Path(r['percorso_file']).name}")

        # Precompila combo/note con valori attuali
        if r["dente"]  and r["dente"]  in db.DENTI_FDI: self._combo_dente.set(r["dente"])
        if r["branca"] and r["branca"] in db.BRANCHE:   self._combo_branca.set(r["branca"])
        if r["fase"]   and r["fase"]   in db.FASI:      self._combo_fase.set(r["fase"])

        self._txt_note.delete("1.0", "end")
        self._txt_note.insert("1.0", r["note"] or "")

        # Info label nel pannello tag
        self._lbl_tag_info.configure(
            text=f"ID #{foto_id} — stai modificando i tag di questa foto.",
            text_color=COLORI["chiaro"])

        self._lbl_stato.configure(text="")
        self._btn_salva.configure(state="normal")
        self._btn_reset.configure(state="normal")

    def _aggiorna_preview(self, percorso: Path):
        """Carica e ridimensiona l'immagine per il pannello di anteprima."""
        try:
            img = Image.open(percorso)
            # Dimensioni dinamiche (usa lo spazio disponibile)
            self.update_idletasks()
            w = max(360, self._img_card.winfo_width() - 32)
            h = max(280, self._img_card.winfo_height() - 130)
            img.thumbnail((w, h), Image.LANCZOS)
            ctkimg = ctk.CTkImage(light_image=img, dark_image=img, size=img.size)
        except Exception:
            placeholder = Image.new("RGB", (400, 300), (30, 30, 50))
            ctkimg = ctk.CTkImage(light_image=placeholder, dark_image=placeholder,
                                  size=(400, 300))

        self._thumb_ref = ctkimg
        self._img_lbl.configure(image=ctkimg, text="",
                                 fg_color=COLORI["preview_bg"])

    # ------------------------------------------------------------------
    # Picker foto (sfoglia per paziente)
    # ------------------------------------------------------------------

    def _apri_picker_foto(self):
        """Apre una finestra di selezione rapida foto filtrata per paziente."""
        testo = self._combo_paz_search.get().strip()
        pazienti = db.cerca_pazienti(testo)
        if not pazienti:
            self._set_stato_search("Nessun paziente trovato.", "rosso")
            return

        picker = FotoPickerDialog(self, pazienti)
        self.wait_window(picker)
        if picker.foto_id_selezionata is not None:
            self._entry_id.delete(0, "end")
            self._entry_id.insert(0, str(picker.foto_id_selezionata))
            self._carica_foto(picker.foto_id_selezionata)

    # ------------------------------------------------------------------
    # Salva / Ripristina
    # ------------------------------------------------------------------

    def _salva(self):
        if self._foto_id is None:
            return
        db.aggiorna_tag_foto(
            foto_id=self._foto_id,
            dente=self._combo_dente.get(),
            branca=self._combo_branca.get(),
            fase=self._combo_fase.get(),
            note=self._txt_note.get("1.0", "end").strip(),
        )
        self._lbl_stato.configure(
            text=f"✅  Foto #{self._foto_id} aggiornata con successo.",
            text_color=COLORI["verde"])
        self._lbl_tag_info.configure(
            text=f"ID #{self._foto_id} — tag salvati.",
            text_color=COLORI["verde"])
        # Feedback visivo temporaneo sul pannello tag
        self._tag_card.configure(fg_color=COLORI["tag_saved"])
        self.after(800, lambda: self._tag_card.configure(fg_color=COLORI["card"]))

    def _ripristina(self):
        """Ricarica i valori originali della foto dal DB."""
        if self._foto_id is not None:
            self._carica_foto(self._foto_id)
            self._lbl_stato.configure(text="↩  Valori ripristinati.",
                                       text_color=COLORI["grigio"])

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _set_stato_search(self, testo: str, tipo: str = "grigio"):
        col = {"verde": COLORI["verde"], "rosso": COLORI["rosso"]}.get(tipo, COLORI["grigio"])
        self._lbl_search_stato.configure(text=testo, text_color=col)


# ===========================================================================
# DIALOG: Selezione foto per paziente
# ===========================================================================

class FotoPickerDialog(ctk.CTkToplevel):
    """
    Finestra modale: mostra la lista dei pazienti trovati → seleziona uno →
    mostra le sue foto come lista → click su una foto → imposta foto_id_selezionata.
    """

    def __init__(self, master, pazienti: list):
        super().__init__(master)
        self.title("Seleziona Foto")
        self.geometry("700x520")
        self.resizable(True, True)
        self.grab_set()
        self.foto_id_selezionata: Optional[int] = None

        self.after(50, lambda: (self.lift(), self.focus_force(),
                                self.attributes("-topmost", True),
                                self.after(200, lambda: self.attributes("-topmost", False))))

        self._pazienti  = pazienti
        self._paz_sel   = None
        self._thumb_refs: list = []
        self._build_ui()

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=2)
        self.grid_rowconfigure(0, weight=1)

        # Lista pazienti
        lp = ctk.CTkScrollableFrame(self, fg_color=COLORI["card"],
                                    corner_radius=12, label_text="Pazienti trovati")
        lp.grid(row=0, column=0, padx=(12, 6), pady=12, sticky="nsew")
        lp.grid_columnconfigure(0, weight=1)

        for i, p in enumerate(self._pazienti):
            n_f = db.conta_foto_per_paziente(p["id"])
            btn = ctk.CTkButton(lp,
                                text=f"{p['cognome']} {p['nome']}  ({n_f} foto)",
                                font=("Segoe UI", 11), height=36, anchor="w",
                                fg_color=COLORI["card"],
                                hover_color=COLORI["accent"],
                                command=lambda pid=p["id"]: self._seleziona_paz(pid))
            btn.grid(row=i, column=0, padx=4, pady=2, sticky="ew")

        # Galleria foto del paziente
        self._galleria = ctk.CTkScrollableFrame(
            self, fg_color=COLORI["card"], corner_radius=12,
            label_text="Foto del paziente — clicca per selezionare")
        self._galleria.grid(row=0, column=1, padx=(6, 12), pady=12, sticky="nsew")
        for c in range(3):
            self._galleria.grid_columnconfigure(c, weight=1)

        ctk.CTkLabel(self._galleria,
                     text="← Seleziona un paziente",
                     font=("Segoe UI", 10), text_color=COLORI["grigio"]).grid(
            row=0, column=0, columnspan=3, pady=30)

    def _seleziona_paz(self, pid: int):
        self._paz_sel = pid
        for w in self._galleria.winfo_children():
            w.destroy()
        self._thumb_refs.clear()

        righe = db.cerca_foto(paziente_id=pid)
        if not righe:
            ctk.CTkLabel(self._galleria, text="Nessuna foto.",
                         font=("Segoe UI", 10),
                         text_color=COLORI["grigio"]).grid(
                row=0, column=0, columnspan=3, pady=20)
            return

        for idx, r in enumerate(righe):
            row, col = divmod(idx, 3)
            self._card_foto(row, col, r)

    def _card_foto(self, row: int, col: int, r):
        card = ctk.CTkFrame(self._galleria, fg_color=COLORI["entry_bg"],
                            corner_radius=8, cursor="hand2")
        card.grid(row=row, column=col, padx=5, pady=5, sticky="nsew")
        card.grid_columnconfigure(0, weight=1)

        percorso = db.get_percorso_assoluto(r)
        try:
            img = Image.open(percorso)
            img.thumbnail((130, 100), Image.LANCZOS)
            th = ctk.CTkImage(light_image=img, dark_image=img, size=img.size)
        except Exception:
            ph = Image.new("RGB", (130, 100), (40, 40, 55))
            th = ctk.CTkImage(light_image=ph, dark_image=ph, size=(130, 100))
        self._thumb_refs.append(th)

        lbl = ctk.CTkLabel(card, image=th, text="", cursor="hand2")
        lbl.grid(row=0, column=0, padx=4, pady=(6, 2))

        ctk.CTkLabel(card, text=f"{r['branca'] or '—'} / {r['fase'] or '—'}",
                     font=("Segoe UI", 8), text_color=COLORI["grigio"]).grid(
            row=1, column=0, padx=4, pady=(0, 2))
        ctk.CTkLabel(card, text=f"ID #{r['id']}  📅 {r['data_scatto'] or '—'}",
                     font=("Segoe UI", 8), text_color=COLORI["accent_br"]).grid(
            row=2, column=0, padx=4, pady=(0, 6))

        for w in (card, lbl):
            w.bind("<Button-1>", lambda e, fid=r["id"]: self._conferma(fid))
            w.bind("<Enter>",    lambda e, f=card: f.configure(fg_color=COLORI["accent"]))
            w.bind("<Leave>",    lambda e, f=card: f.configure(fg_color=COLORI["entry_bg"]))

    def _conferma(self, foto_id: int):
        self.foto_id_selezionata = foto_id
        self.destroy()


__all__ = ["ModificaTagFrame"]

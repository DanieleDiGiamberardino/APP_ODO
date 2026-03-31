# =============================================================================
#  DentalPhoto Pro — ProtocolloFrame
#  Guida l'assistente alla poltrona attraverso una sessione fotografica
#  strutturata, basata su protocolli predefiniti.
#
#  Dipendenze: customtkinter, Pillow (opzionale, per thumbnail future)
#  Importa questo modulo nel tuo main e aggiungilo al tuo frame container.
# =============================================================================

import customtkinter as ctk
from tkinter import filedialog

# ---------------------------------------------------------------------------
# THEME — rimpiazza con il tuo import reale:
#   from config.theme import MODERN_THEME as T
# ---------------------------------------------------------------------------
MODERN_THEME = {
    "bg_main":        "#0F1117",
    "bg_panel":       "#1A1D27",
    "bg_card":        "#1E2130",
    "bg_input":       "#252837",
    "bg_hover":       "#2C3047",
    "accent":         "#4F8EF7",
    "accent_dim":     "#2D5BB5",
    "accent_success": "#34C78A",
    "accent_warning": "#F5A623",
    "accent_danger":  "#E05252",
    "text_primary":   "#EDF0FF",
    "text_secondary": "#8A8FA8",
    "text_disabled":  "#4A4F66",
    "border":         "#2E3250",
    "border_active":  "#4F8EF7",
}
T = MODERN_THEME


# ---------------------------------------------------------------------------
# CONFIGURAZIONE PROTOCOLLI
# Ogni protocollo è un dizionario con:
#   - label:    nome mostrato nell'OptionMenu
#   - cols:     numero di colonne della griglia
#   - shots:    lista ordinata degli slot fotografici
#     Ogni shot: { "id": str, "name": str, "hint": str, "icon": str }
# ---------------------------------------------------------------------------
PROTOCOLS: dict[str, dict] = {

    "Ortodonzia (8 Foto)": {
        "label": "Ortodonzia (8 Foto)",
        "cols":   4,
        "shots": [
            {"id": "ort_01", "name": "Frontale\nRiposo",      "hint": "Labbra chiuse, sguardo dritto",   "icon": "😐"},
            {"id": "ort_02", "name": "Frontale\nSorriso",     "hint": "Sorriso naturale, ampio",         "icon": "😁"},
            {"id": "ort_03", "name": "Profilo Sx\nRiposo",    "hint": "90° sinistro, labbra chiuse",     "icon": "👤"},
            {"id": "ort_04", "name": "Profilo Dx\nRiposo",    "hint": "90° destro, labbra chiuse",       "icon": "👤"},
            {"id": "ort_05", "name": "Occlusale\nSuperiore",  "hint": "Specchio, arcata sup. in vista",  "icon": "🦷"},
            {"id": "ort_06", "name": "Occlusale\nInferiore",  "hint": "Specchio, arcata inf. in vista",  "icon": "🦷"},
            {"id": "ort_07", "name": "Laterale Dx\nIn Occlusione", "hint": "Divaricatore, lato destro",  "icon": "📷"},
            {"id": "ort_08", "name": "Laterale Sx\nIn Occlusione", "hint": "Divaricatore, lato sinistro","icon": "📷"},
        ],
    },

    "Estetica DSD (4 Foto)": {
        "label": "Estetica DSD (4 Foto)",
        "cols":   2,
        "shots": [
            {"id": "dsd_01", "name": "Frontale\nSorriso Full",  "hint": "Sorriso massimo, viso intero",  "icon": "✨"},
            {"id": "dsd_02", "name": "Retracted\nFrontale",     "hint": "Divaricatori, massima apertura","icon": "🔬"},
            {"id": "dsd_03", "name": "Zoom\nDentale 1:1",       "hint": "Solo i 6 anteriori superiori",  "icon": "🔍"},
            {"id": "dsd_04", "name": "Profilo\n¾ Sorriso",      "hint": "45°, sorriso naturale",         "icon": "💎"},
        ],
    },

    "Full Mouth (12 Foto)": {
        "label": "Full Mouth (12 Foto)",
        "cols":   4,
        "shots": [
            {"id": "fm_01",  "name": "Frontale\nRiposo",        "hint": "Labbra chiuse, sguardo dritto",  "icon": "😐"},
            {"id": "fm_02",  "name": "Frontale\nSorriso",       "hint": "Sorriso naturale, ampio",        "icon": "😁"},
            {"id": "fm_03",  "name": "Profilo Sx",              "hint": "90° sinistro",                   "icon": "👤"},
            {"id": "fm_04",  "name": "Profilo Dx",              "hint": "90° destro",                     "icon": "👤"},
            {"id": "fm_05",  "name": "Occlusale Sup.",          "hint": "Specchio arcata superiore",      "icon": "🦷"},
            {"id": "fm_06",  "name": "Occlusale Inf.",          "hint": "Specchio arcata inferiore",      "icon": "🦷"},
            {"id": "fm_07",  "name": "Laterale Dx",             "hint": "Divaricatore, lato destro",      "icon": "📷"},
            {"id": "fm_08",  "name": "Laterale Sx",             "hint": "Divaricatore, lato sinistro",    "icon": "📷"},
            {"id": "fm_09",  "name": "Retracted\nFrontale",     "hint": "Massima apertura frontale",      "icon": "🔬"},
            {"id": "fm_10",  "name": "Zoom\nAnteriori",         "hint": "6 anteriori superiori 1:1",      "icon": "🔍"},
            {"id": "fm_11",  "name": "Dettaglio\nDx",           "hint": "Settore posteriore destro",      "icon": "🔎"},
            {"id": "fm_12",  "name": "Dettaglio\nSx",           "hint": "Settore posteriore sinistro",    "icon": "🔎"},
        ],
    },
}

PROTOCOL_KEYS = list(PROTOCOLS.keys())


# =============================================================================
#  PhotoSlotCard — singola card "dropzone" per uno scatto richiesto
# =============================================================================
class PhotoSlotCard(ctk.CTkFrame):
    """
    Card rettangolare che rappresenta uno slot fotografico nel protocollo.

    Stati:
        EMPTY   → sfondo scuro, icona + nome, bordo tratteggiato simulato
        FILLED  → sfondo con thumbnail, badge ✓ verde in alto a destra
    """

    SLOT_W = 190
    SLOT_H = 155

    def __init__(self, master, shot: dict, slot_index: int, **kwargs):
        super().__init__(
            master,
            width=self.SLOT_W,
            height=self.SLOT_H,
            corner_radius=10,
            fg_color=T["bg_input"],
            border_width=1,
            border_color=T["border"],
            **kwargs,
        )
        self.shot       = shot
        self.slot_index = slot_index
        self.image_path: str | None = None
        self._filled    = False

        self.grid_propagate(False)
        self.pack_propagate(False)

        self._build_empty_state()
        self._bind_hover()

    # ------------------------------------------------------------------
    # BUILD — stato vuoto (dropzone)
    # ------------------------------------------------------------------
    def _build_empty_state(self):
        """Costruisce il layout 'dropzone' con icona e nome richiesto."""
        self._clear_children()

        # Numero progressivo in alto a sinistra
        self._lbl_index = ctk.CTkLabel(
            self,
            text=f"#{self.slot_index + 1:02d}",
            font=ctk.CTkFont(family="SF Pro Display", size=10, weight="bold"),
            text_color=T["text_disabled"],
            fg_color="transparent",
        )
        self._lbl_index.place(x=8, y=7)

        # Contenitore centrale (icona + nome + hint)
        center = ctk.CTkFrame(self, fg_color="transparent")
        center.place(relx=0.5, rely=0.5, anchor="center")

        self._lbl_icon = ctk.CTkLabel(
            center,
            text=self.shot["icon"],
            font=ctk.CTkFont(size=28),
            text_color=T["text_disabled"],
            fg_color="transparent",
        )
        self._lbl_icon.pack(pady=(0, 4))

        self._lbl_name = ctk.CTkLabel(
            center,
            text=self.shot["name"],
            font=ctk.CTkFont(family="SF Pro Display", size=12, weight="bold"),
            text_color=T["text_secondary"],
            fg_color="transparent",
            justify="center",
        )
        self._lbl_name.pack()

        self._lbl_hint = ctk.CTkLabel(
            center,
            text=self.shot["hint"],
            font=ctk.CTkFont(size=9),
            text_color=T["text_disabled"],
            fg_color="transparent",
            justify="center",
            wraplength=160,
        )
        self._lbl_hint.pack(pady=(2, 0))

        # Pulsante "+" in basso — apre filedialog
        self._btn_add = ctk.CTkButton(
            self,
            text="+ Aggiungi",
            width=90,
            height=24,
            corner_radius=6,
            font=ctk.CTkFont(size=10, weight="bold"),
            fg_color=T["bg_hover"],
            hover_color=T["accent_dim"],
            text_color=T["text_secondary"],
            border_width=1,
            border_color=T["border"],
            command=self._pick_image,
        )
        self._btn_add.place(relx=0.5, rely=1.0, anchor="s", y=-10)

    # ------------------------------------------------------------------
    # BUILD — stato riempito
    # ------------------------------------------------------------------
    def _build_filled_state(self, path: str):
        """Mostra il nome file caricato e un badge di completamento."""
        self._clear_children()

        self.configure(
            fg_color=T["bg_hover"],
            border_color=T["accent_success"],
            border_width=2,
        )

        # Badge ✓ in alto a destra
        badge = ctk.CTkLabel(
            self,
            text=" ✓ ",
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color="#FFFFFF",
            fg_color=T["accent_success"],
            corner_radius=4,
        )
        badge.place(relx=1.0, x=-6, y=6, anchor="ne")

        # Numero slot
        ctk.CTkLabel(
            self,
            text=f"#{self.slot_index + 1:02d}",
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color=T["accent_success"],
            fg_color="transparent",
        ).place(x=8, y=7)

        # Icona e nome al centro
        center = ctk.CTkFrame(self, fg_color="transparent")
        center.place(relx=0.5, rely=0.45, anchor="center")

        ctk.CTkLabel(
            center, text="🖼️",
            font=ctk.CTkFont(size=26),
            fg_color="transparent",
        ).pack(pady=(0, 4))

        ctk.CTkLabel(
            center,
            text=self.shot["name"],
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=T["text_primary"],
            fg_color="transparent",
            justify="center",
        ).pack()

        # Nome file troncato in basso
        filename = path.split("/")[-1].split("\\")[-1]
        if len(filename) > 22:
            filename = filename[:19] + "…"

        ctk.CTkLabel(
            self,
            text=filename,
            font=ctk.CTkFont(size=9),
            text_color=T["text_secondary"],
            fg_color="transparent",
        ).place(relx=0.5, rely=1.0, anchor="s", y=-28)

        # Pulsante rimuovi
        ctk.CTkButton(
            self,
            text="✕ Rimuovi",
            width=85,
            height=22,
            corner_radius=6,
            font=ctk.CTkFont(size=9),
            fg_color="transparent",
            hover_color=T["accent_danger"],
            text_color=T["text_disabled"],
            border_width=0,
            command=self._remove_image,
        ).place(relx=0.5, rely=1.0, anchor="s", y=-6)

    # ------------------------------------------------------------------
    # AZIONI
    # ------------------------------------------------------------------
    def _pick_image(self):
        """Apre un file dialog per selezionare un'immagine."""
        path = filedialog.askopenfilename(
            title=f"Seleziona: {self.shot['name'].replace(chr(10), ' ')}",
            filetypes=[
                ("Immagini", "*.jpg *.jpeg *.png *.tiff *.tif *.bmp *.webp"),
                ("Tutti i file", "*.*"),
            ],
        )
        if path:
            self.set_image(path)

    def set_image(self, path: str):
        """Imposta l'immagine (chiamabile anche dall'esterno, es. drag&drop)."""
        self.image_path = path
        self._filled    = True
        self._build_filled_state(path)
        self._notify_parent()

    def _remove_image(self):
        """Rimuove l'immagine e torna allo stato vuoto."""
        self.image_path = None
        self._filled    = False
        self.configure(
            fg_color=T["bg_input"],
            border_color=T["border"],
            border_width=1,
        )
        self._build_empty_state()
        self._notify_parent()

    def _notify_parent(self):
        """Propaga l'aggiornamento al ProtocolloFrame per ricalcolare il progress."""
        parent = self.master
        while parent is not None:
            if hasattr(parent, "_on_slot_changed"):
                parent._on_slot_changed()
                break
            parent = getattr(parent, "master", None)

    # ------------------------------------------------------------------
    # HOVER FX
    # ------------------------------------------------------------------
    def _bind_hover(self):
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)

    def _on_enter(self, _=None):
        if not self._filled:
            self.configure(border_color=T["accent"], border_width=2)

    def _on_leave(self, _=None):
        if not self._filled:
            self.configure(border_color=T["border"], border_width=1)

    # ------------------------------------------------------------------
    # UTILS
    # ------------------------------------------------------------------
    def _clear_children(self):
        for widget in self.winfo_children():
            widget.destroy()

    @property
    def is_filled(self) -> bool:
        return self._filled


# =============================================================================
#  ProtocolloFrame — frame principale della feature
# =============================================================================
class ProtocolloFrame(ctk.CTkFrame):
    """
    Frame principale per la sessione fotografica guidata.

    Layout:
        ┌──────────────┬────────────────────────────────────────┐
        │  Pannello    │                                        │
        │  Controlli   │   Griglia Slot (dinamica)              │
        │  (~250px)    │                                        │
        └──────────────┴────────────────────────────────────────┘
    """

    SIDEBAR_W = 260

    def __init__(self, master, **kwargs):
        super().__init__(master, fg_color=T["bg_main"], **kwargs)

        # Stato interno
        self._selected_protocol_key: str = PROTOCOL_KEYS[0]
        self._slots: list[PhotoSlotCard]  = []

        # Layout radice: 2 colonne
        self.grid_columnconfigure(0, weight=0, minsize=self.SIDEBAR_W)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._build_sidebar()
        self._build_content_area()

        # Carica protocollo di default
        self._load_protocol(self._selected_protocol_key)

    # ==========================================================================
    #  SIDEBAR — colonna sinistra
    # ==========================================================================
    def _build_sidebar(self):
        self._sidebar = ctk.CTkFrame(
            self,
            width=self.SIDEBAR_W,
            fg_color=T["bg_panel"],
            corner_radius=0,
            border_width=1,
            border_color=T["border"],
        )
        self._sidebar.grid(row=0, column=0, sticky="nsew")
        self._sidebar.grid_propagate(False)
        self._sidebar.grid_columnconfigure(0, weight=1)

        # — Logo / Titolo sezione ————————————————————————————————————————
        header = ctk.CTkFrame(self._sidebar, fg_color=T["bg_card"], corner_radius=0)
        header.grid(row=0, column=0, sticky="ew", padx=0, pady=(0, 0))
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            header,
            text="📋  Protocollo",
            font=ctk.CTkFont(family="SF Pro Display", size=15, weight="bold"),
            text_color=T["text_primary"],
            anchor="w",
        ).grid(row=0, column=0, padx=18, pady=(16, 2), sticky="w")

        ctk.CTkLabel(
            header,
            text="Sessione fotografica guidata",
            font=ctk.CTkFont(size=11),
            text_color=T["text_secondary"],
            anchor="w",
        ).grid(row=1, column=0, padx=18, pady=(0, 14), sticky="w")

        # Separatore visivo
        ctk.CTkFrame(
            self._sidebar, height=1, fg_color=T["border"]
        ).grid(row=1, column=0, sticky="ew")

        # Contenuto scrollabile della sidebar
        inner = ctk.CTkScrollableFrame(
            self._sidebar,
            fg_color="transparent",
            scrollbar_button_color=T["border"],
            scrollbar_button_hover_color=T["accent_dim"],
        )
        inner.grid(row=2, column=0, sticky="nsew", padx=0, pady=0)
        self._sidebar.grid_rowconfigure(2, weight=1)
        inner.grid_columnconfigure(0, weight=1)

        pad_x = 16

        # — Sezione Paziente ————————————————————————————————————————————
        self._build_section_title(inner, row=0, text="👤  Paziente")

        self._patient_card = ctk.CTkFrame(
            inner,
            fg_color=T["bg_input"],
            corner_radius=8,
            border_width=1,
            border_color=T["border"],
            height=64,
        )
        self._patient_card.grid(row=1, column=0, sticky="ew", padx=pad_x, pady=(4, 14))
        self._patient_card.grid_propagate(False)
        self._patient_card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            self._patient_card,
            text="Nessun paziente selezionato",
            font=ctk.CTkFont(size=11),
            text_color=T["text_disabled"],
        ).place(relx=0.5, rely=0.35, anchor="center")

        self._btn_select_patient = ctk.CTkButton(
            self._patient_card,
            text="Seleziona →",
            width=100,
            height=20,
            font=ctk.CTkFont(size=10, weight="bold"),
            corner_radius=5,
            fg_color=T["accent_dim"],
            hover_color=T["accent"],
            text_color="#FFFFFF",
            command=self._on_select_patient,
        )
        self._btn_select_patient.place(relx=0.5, rely=0.78, anchor="center")

        # — Sezione Protocollo ——————————————————————————————————————————
        self._build_section_title(inner, row=2, text="🗂️  Tipo di Protocollo")

        self._protocol_var = ctk.StringVar(value=PROTOCOL_KEYS[0])
        self._protocol_menu = ctk.CTkOptionMenu(
            inner,
            values=PROTOCOL_KEYS,
            variable=self._protocol_var,
            font=ctk.CTkFont(size=12),
            dropdown_font=ctk.CTkFont(size=12),
            fg_color=T["bg_input"],
            button_color=T["accent_dim"],
            button_hover_color=T["accent"],
            dropdown_fg_color=T["bg_card"],
            dropdown_hover_color=T["bg_hover"],
            text_color=T["text_primary"],
            dropdown_text_color=T["text_primary"],
            corner_radius=8,
            dynamic_resizing=False,
            width=self.SIDEBAR_W - pad_x * 2,
            command=self._on_protocol_change,
        )
        self._protocol_menu.grid(row=3, column=0, padx=pad_x, pady=(4, 16), sticky="ew")

        # — Progress box ————————————————————————————————————————————————
        self._build_section_title(inner, row=4, text="📊  Avanzamento")

        self._progress_frame = ctk.CTkFrame(
            inner,
            fg_color=T["bg_input"],
            corner_radius=8,
            border_width=1,
            border_color=T["border"],
        )
        self._progress_frame.grid(row=5, column=0, sticky="ew", padx=pad_x, pady=(4, 16))
        self._progress_frame.grid_columnconfigure(0, weight=1)

        self._lbl_progress_count = ctk.CTkLabel(
            self._progress_frame,
            text="0 / 0  foto",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color=T["accent"],
        )
        self._lbl_progress_count.grid(row=0, column=0, pady=(12, 4))

        self._progressbar = ctk.CTkProgressBar(
            self._progress_frame,
            width=self.SIDEBAR_W - pad_x * 2 - 20,
            height=8,
            corner_radius=4,
            fg_color=T["bg_hover"],
            progress_color=T["accent"],
        )
        self._progressbar.set(0)
        self._progressbar.grid(row=1, column=0, padx=10, pady=(0, 8))

        self._lbl_progress_pct = ctk.CTkLabel(
            self._progress_frame,
            text="0% completato",
            font=ctk.CTkFont(size=10),
            text_color=T["text_secondary"],
        )
        self._lbl_progress_pct.grid(row=2, column=0, pady=(0, 12))

        # — Note di sessione ————————————————————————————————————————————
        self._build_section_title(inner, row=6, text="📝  Note Sessione")

        self._txt_notes = ctk.CTkTextbox(
            inner,
            height=80,
            fg_color=T["bg_input"],
            border_width=1,
            border_color=T["border"],
            text_color=T["text_primary"],
            font=ctk.CTkFont(size=11),
            corner_radius=8,
        )
        self._txt_notes.grid(row=7, column=0, sticky="ew", padx=pad_x, pady=(4, 0))
        self._txt_notes.insert("0.0", "Note cliniche aggiuntive…")

        # — Footer sidebar: bottone Salva ————————————————————————————————
        footer = ctk.CTkFrame(
            self._sidebar,
            fg_color=T["bg_card"],
            corner_radius=0,
            border_width=1,
            border_color=T["border"],
        )
        footer.grid(row=3, column=0, sticky="ew")
        footer.grid_columnconfigure(0, weight=1)

        self._btn_save = ctk.CTkButton(
            footer,
            text="💾  Salva Protocollo",
            height=42,
            corner_radius=8,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=T["accent_dim"],
            hover_color=T["accent"],
            text_color="#FFFFFF",
            state="disabled",
            command=self._on_save_protocol,
        )
        self._btn_save.grid(row=0, column=0, padx=16, pady=14, sticky="ew")

    # ==========================================================================
    #  CONTENT AREA — colonna destra
    # ==========================================================================
    def _build_content_area(self):
        self._content = ctk.CTkFrame(
            self,
            fg_color=T["bg_main"],
            corner_radius=0,
        )
        self._content.grid(row=0, column=1, sticky="nsew")
        self._content.grid_rowconfigure(1, weight=1)
        self._content.grid_columnconfigure(0, weight=1)

        # Header content area
        self._content_header = ctk.CTkFrame(
            self._content,
            fg_color=T["bg_panel"],
            corner_radius=0,
            border_width=1,
            border_color=T["border"],
            height=64,
        )
        self._content_header.grid(row=0, column=0, sticky="ew")
        self._content_header.grid_propagate(False)
        self._content_header.grid_columnconfigure(1, weight=1)

        self._lbl_protocol_title = ctk.CTkLabel(
            self._content_header,
            text="",
            font=ctk.CTkFont(size=17, weight="bold"),
            text_color=T["text_primary"],
            anchor="w",
        )
        self._lbl_protocol_title.grid(row=0, column=0, padx=(22, 0), pady=(12, 2), sticky="w")

        self._lbl_protocol_desc = ctk.CTkLabel(
            self._content_header,
            text="",
            font=ctk.CTkFont(size=11),
            text_color=T["text_secondary"],
            anchor="w",
        )
        self._lbl_protocol_desc.grid(row=1, column=0, padx=(22, 0), pady=(0, 10), sticky="w")

        # Badge "slot rimanenti" a destra
        self._lbl_badge = ctk.CTkLabel(
            self._content_header,
            text="",
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color=T["accent"],
            fg_color=T["bg_hover"],
            corner_radius=6,
            padx=10,
            pady=4,
        )
        self._lbl_badge.grid(row=0, column=2, rowspan=2, padx=22, pady=14, sticky="e")

        # Area scrollabile per la griglia degli slot
        self._grid_scroll = ctk.CTkScrollableFrame(
            self._content,
            fg_color=T["bg_main"],
            scrollbar_button_color=T["border"],
            scrollbar_button_hover_color=T["accent_dim"],
        )
        self._grid_scroll.grid(row=1, column=0, sticky="nsew", padx=0, pady=0)

        # Placeholder mostrato quando non c'è un protocollo caricato
        self._placeholder = ctk.CTkLabel(
            self._grid_scroll,
            text="Seleziona un protocollo per iniziare →",
            font=ctk.CTkFont(size=14),
            text_color=T["text_disabled"],
        )

    # ==========================================================================
    #  LOGICA PROTOCOLLO
    # ==========================================================================
    def _load_protocol(self, key: str):
        """Distrugge la griglia corrente e ne costruisce una nuova."""
        self._selected_protocol_key = key
        protocol = PROTOCOLS[key]

        # Rimuovi tutti i widget precedenti dalla griglia
        for widget in self._grid_scroll.winfo_children():
            widget.destroy()
        self._slots.clear()

        # Aggiorna header
        self._lbl_protocol_title.configure(text=f"📋  {protocol['label']}")
        n_shots = len(protocol["shots"])
        self._lbl_protocol_desc.configure(
            text=f"{n_shots} scatti richiesti · Completare la griglia per sbloccare il salvataggio"
        )

        # Costruisci griglia
        cols = protocol["cols"]
        self._grid_scroll.grid_columnconfigure(
            list(range(cols)), weight=1
        )

        for idx, shot in enumerate(protocol["shots"]):
            row_i = idx // cols
            col_i = idx % cols

            slot = PhotoSlotCard(
                self._grid_scroll,
                shot=shot,
                slot_index=idx,
            )
            slot.grid(
                row=row_i,
                column=col_i,
                padx=12,
                pady=12,
                sticky="n",
            )
            self._slots.append(slot)

        # Reset progress
        self._update_progress()

    def _on_slot_changed(self):
        """Callback chiamato da ogni PhotoSlotCard quando cambia stato."""
        self._update_progress()

    def _update_progress(self):
        """Aggiorna progressbar, label e stato del tasto Salva."""
        total  = len(self._slots)
        filled = sum(1 for s in self._slots if s.is_filled)

        pct = filled / total if total > 0 else 0.0

        self._progressbar.set(pct)
        self._lbl_progress_count.configure(text=f"{filled} / {total}  foto")
        self._lbl_progress_pct.configure(
            text=f"{int(pct * 100)}% completato"
        )

        remaining = total - filled
        if remaining == 0:
            self._lbl_badge.configure(
                text="✓  Completato",
                text_color=T["accent_success"],
                fg_color=T["bg_hover"],
            )
            self._progressbar.configure(progress_color=T["accent_success"])
        else:
            self._lbl_badge.configure(
                text=f"{remaining} slot rimanenti",
                text_color=T["accent"],
                fg_color=T["bg_hover"],
            )
            self._progressbar.configure(progress_color=T["accent"])

        # Abilita il tasto Salva solo se tutti gli slot sono pieni
        self._btn_save.configure(
            state="normal" if filled == total and total > 0 else "disabled",
            fg_color=T["accent"] if filled == total else T["accent_dim"],
        )

    # ==========================================================================
    #  EVENT HANDLERS
    # ==========================================================================
    def _on_protocol_change(self, value: str):
        self._load_protocol(value)

    def _on_select_patient(self):
        """
        Placeholder: sostituisci con l'apertura della tua PatientPickerDialog.
        Esempio di signature attesa:
            dialog = PatientPickerDialog(self)
            patient = dialog.get_result()
            if patient:
                self._set_patient(patient)
        """
        # Simulazione visiva per ora
        self._patient_card.configure(border_color=T["accent"])
        ctk.CTkLabel(
            self._patient_card,
            text="👤  Rossi Mario — #00124",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=T["text_primary"],
            fg_color="transparent",
        ).place(relx=0.5, rely=0.35, anchor="center")
        self._btn_select_patient.configure(text="Cambia →")

    def _on_save_protocol(self):
        """
        Placeholder: implementa qui la logica di salvataggio su DB.
        Dati disponibili:
            - self._selected_protocol_key  → chiave del protocollo
            - self._slots                  → lista PhotoSlotCard
            - slot.image_path              → path del file per ogni slot
            - slot.shot["id"]              → id univoco dello scatto
        """
        paths = {s.shot["id"]: s.image_path for s in self._slots}
        notes = self._txt_notes.get("0.0", "end").strip()
        print("[ProtocolloFrame] Salvataggio →", paths)
        print("[ProtocolloFrame] Note →", notes)
        # TODO: chiamare il tuo DAL (Data Access Layer) qui

    # ==========================================================================
    #  HELPERS
    # ==========================================================================
    def _build_section_title(self, parent, row: int, text: str):
        ctk.CTkLabel(
            parent,
            text=text,
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=T["text_secondary"],
            anchor="w",
        ).grid(row=row, column=0, sticky="w", padx=16, pady=(14, 2))


# =============================================================================
#  ENTRY POINT — preview standalone (rimuovi in produzione)
# =============================================================================
if __name__ == "__main__":
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")

    root = ctk.CTk()
    root.title("DentalPhoto Pro — Protocollo Fotografico (preview)")
    root.geometry("1280x780")
    root.configure(fg_color=T["bg_main"])

    frame = ProtocolloFrame(root)
    frame.pack(fill="both", expand=True)

    root.mainloop()

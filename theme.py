"""
theme.py  ·  Modern Premium Theme
Costanti di design e metodo _build_sidebar per App(DnDCTk).
"""

import tkinter as tk
import customtkinter as ctk

# ══════════════════════════════════════════════════════════════════════════════
#  MODERN_THEME  –  Palette sofisticata dark-mode clinica
# ══════════════════════════════════════════════════════════════════════════════
MODERN_THEME: dict[str, str] = {
    # ── Superfici ─────────────────────────────────────────────────────────────
    "bg_root":          "#0b0e17",   # sfondo app:  quasi-nero con sottile velo blu
    "bg_sidebar":       "#0e1220",   # sidebar:     leggermente più caldo del root
    "bg_panel":         "#131929",   # card/panel:  strato +1, percepibile come sollevato
    "bg_panel_alt":     "#192035",   # card hover / righe alternate
    "bg_input":         "#0d1424",   # campi input / dropzone
    "bg_overlay":       "#07090f",   # modali / backdrop scuro

    # ── Accento principale  (teal elettrico) ──────────────────────────────────
    "accent":           "#00d4aa",   # teal vibrante – bottoni attivi, badge
    "accent_dim":       "#00a882",   # teal scuro – pressed / stato attivo sidebar
    "accent_glow":      "#00d4aa22", # teal trasparente – alone / highlight

    # ── Accento secondario (blu ghiaccio) ────────────────────────────────────
    "accent2":          "#4f9cf9",   # blu primario – link, info, selezioni
    "accent2_dim":      "#2d6fd4",

    # ── Testo ─────────────────────────────────────────────────────────────────
    "text_primary":     "#eef2ff",   # bianco panna – titoli, contenuto principale
    "text_secondary":   "#7a90b8",   # grigio-azzurro muted – label, metadati
    "text_disabled":    "#3a4a66",   # quasi invisibile – placeholder, disabilitato
    "text_accent":      "#00d4aa",   # accento su testo – badge, evidenziazioni

    # ── Bordi & Separatori ────────────────────────────────────────────────────
    "border":           "#1e2d4a",   # bordo sottile pannelli
    "border_focus":     "#00d4aa",   # bordo focus / attivo
    "separator":        "#151e30",   # linea divisoria interna

    # ── Feedback semantico ────────────────────────────────────────────────────
    "success":          "#22d3a5",
    "warning":          "#f5a623",
    "danger":           "#f04a5e",
    "info":             "#4f9cf9",

    # ── Sidebar specifica ─────────────────────────────────────────────────────
    "sidebar_btn_idle":    "transparent",
    "sidebar_btn_hover":   "#1a2540",
    "sidebar_btn_active":  "#0f2038",
    "sidebar_indicator":   "#00d4aa",   # striscia sinistra voce attiva
}

# ══════════════════════════════════════════════════════════════════════════════
#  FONT
# ══════════════════════════════════════════════════════════════════════════════
_FAMILY = "Segoe UI"   # fallback: "Helvetica Neue", "SF Pro Display"

FONT_DISPLAY  = ctk.CTkFont(family=_FAMILY, size=22, weight="bold")   # hero title
FONT_TITLE    = ctk.CTkFont(family=_FAMILY, size=15, weight="bold")   # sezione / header card
FONT_SUBTITLE = ctk.CTkFont(family=_FAMILY, size=12, weight="normal") # sottotitolo
FONT_BODY     = ctk.CTkFont(family=_FAMILY, size=12, weight="normal") # corpo testo
FONT_BODY_B   = ctk.CTkFont(family=_FAMILY, size=12, weight="bold")   # corpo enfatizzato
FONT_SMALL    = ctk.CTkFont(family=_FAMILY, size=10, weight="normal") # label, metadati
FONT_SMALL_B  = ctk.CTkFont(family=_FAMILY, size=10, weight="bold")   # badge, chip
FONT_MONO     = ctk.CTkFont(family="Consolas", size=11, weight="normal")  # codici, ID
FONT_NAV      = ctk.CTkFont(family=_FAMILY, size=12, weight="bold")   # voci sidebar
FONT_NAV_SUB  = ctk.CTkFont(family=_FAMILY, size=10, weight="normal") # sotto-voci sidebar


# ══════════════════════════════════════════════════════════════════════════════
#  Dati di navigazione sidebar
# ══════════════════════════════════════════════════════════════════════════════
_NAV_ITEMS: list[dict] = [
    {"key": "dashboard",   "icon": "⬡",  "label": "Dashboard"},
    {"key": "pazienti",    "icon": "👤",  "label": "Pazienti"},
    {"key": "upload",      "icon": "⬆",  "label": "Upload"},
    {"key": "webcam",      "icon": "◉",  "label": "Webcam"},
    {"key": "before_after","icon": "⇌",  "label": "Before / After"},
    {"key": "statistiche", "icon": "⬡",  "label": "Statistiche"},
]

_NAV_BOTTOM: list[dict] = [
    {"key": "impostazioni", "icon": "⚙", "label": "Impostazioni"},
    {"key": "info",         "icon": "?", "label": "Informazioni"},
]


# ══════════════════════════════════════════════════════════════════════════════
#  _SidebarButton  –  voce di navigazione con hover e indicatore attivo
# ══════════════════════════════════════════════════════════════════════════════
class _SidebarButton(tk.Frame):
    """
    Bottone sidebar con:
    - Striscia verticale teal (indicatore voce attiva)
    - Hover fluido tramite bind <Enter>/<Leave>
    - Icona + label su una riga
    """

    _IND_W = 3   # larghezza striscia indicatore in px

    def __init__(
        self,
        master,
        icon: str,
        label: str,
        command=None,
        active: bool = False,
    ):
        super().__init__(master, bg=MODERN_THEME["bg_sidebar"], cursor="hand2")
        self._command = command
        self._active  = active
        self._hovering = False

        self.grid_columnconfigure(1, weight=1)

        # ── striscia indicatore ───────────────────────────────────────────────
        self._indicator = tk.Frame(self, width=self._IND_W, bg=MODERN_THEME["bg_sidebar"])
        self._indicator.grid(row=0, column=0, sticky="ns", padx=(0, 0))

        # ── contenuto ────────────────────────────────────────────────────────
        self._inner = tk.Frame(self, bg=MODERN_THEME["bg_sidebar"])
        self._inner.grid(row=0, column=1, sticky="ew")

        self._lbl_icon = tk.Label(
            self._inner,
            text=icon,
            bg=MODERN_THEME["bg_sidebar"],
            fg=MODERN_THEME["text_secondary"],
            font=(_FAMILY, 13),
            width=2,
            anchor="center",
        )
        self._lbl_icon.pack(side="left", padx=(14, 6), pady=10)

        self._lbl_text = tk.Label(
            self._inner,
            text=label,
            bg=MODERN_THEME["bg_sidebar"],
            fg=MODERN_THEME["text_secondary"],
            font=(_FAMILY, 12, "bold"),
            anchor="w",
        )
        self._lbl_text.pack(side="left", fill="x", expand=True)

        # ── bind ──────────────────────────────────────────────────────────────
        for widget in (self, self._inner, self._lbl_icon, self._lbl_text):
            widget.bind("<Enter>",           self._on_enter)
            widget.bind("<Leave>",           self._on_leave)
            widget.bind("<ButtonPress-1>",   self._on_press)
            widget.bind("<ButtonRelease-1>", self._on_release)

        self._refresh()

    # ── stato ─────────────────────────────────────────────────────────────────
    def set_active(self, active: bool):
        self._active = active
        self._refresh()

    @property
    def is_active(self) -> bool:
        return self._active

    # ── eventi ────────────────────────────────────────────────────────────────
    def _on_enter(self, _event=None):
        self._hovering = True
        self._refresh()

    def _on_leave(self, _event=None):
        self._hovering = False
        self._refresh()

    def _on_press(self, _event=None):
        self._refresh(pressed=True)

    def _on_release(self, _event=None):
        self._refresh()
        if callable(self._command):
            self._command()

    # ── render ────────────────────────────────────────────────────────────────
    def _refresh(self, pressed: bool = False):
        T = MODERN_THEME

        if self._active:
            bg_row  = T["sidebar_btn_active"]
            fg_icon = T["accent"]
            fg_text = T["text_primary"]
            ind_col = T["sidebar_indicator"]
        elif pressed:
            bg_row  = T["sidebar_btn_active"]
            fg_icon = T["accent"]
            fg_text = T["text_primary"]
            ind_col = T["sidebar_btn_active"]
        elif self._hovering:
            bg_row  = T["sidebar_btn_hover"]
            fg_icon = T["accent"]
            fg_text = T["text_primary"]
            ind_col = T["sidebar_btn_hover"]
        else:
            bg_row  = T["bg_sidebar"]
            fg_icon = T["text_secondary"]
            fg_text = T["text_secondary"]
            ind_col = T["bg_sidebar"]

        self.configure(bg=bg_row)
        self._inner.configure(bg=bg_row)
        self._lbl_icon.configure(bg=bg_row, fg=fg_icon)
        self._lbl_text.configure(bg=bg_row, fg=fg_text)
        self._indicator.configure(bg=ind_col)


# ══════════════════════════════════════════════════════════════════════════════
#  Mixin da incollare dentro App(DnDCTk)
# ══════════════════════════════════════════════════════════════════════════════
class _SidebarMixin:
    """
    Incolla questo mixin dentro App(DnDCTk) oppure copia direttamente
    `_build_sidebar` nella tua classe App.

    Presupposti:
        self._nav_buttons : dict[str, _SidebarButton]   inizializzato qui
        self._active_page : str                          inizializzato qui
        self._show_page(key: str)                        da implementare in App
    """

    def _build_sidebar(self):
        T = MODERN_THEME

        # ── contenitore sidebar ───────────────────────────────────────────────
        sidebar = tk.Frame(self, bg=T["bg_sidebar"], width=220)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)

        # ── linea di separazione destra (1px) ────────────────────────────────
        tk.Frame(self, bg=T["border"], width=1).pack(side="left", fill="y")

        # ── logo / brand ──────────────────────────────────────────────────────
        brand = tk.Frame(sidebar, bg=T["bg_sidebar"], height=72)
        brand.pack(fill="x")
        brand.pack_propagate(False)

        tk.Label(
            brand,
            text="◈  DentalPACS",
            bg=T["bg_sidebar"],
            fg=T["accent"],
            font=(_FAMILY, 14, "bold"),
            anchor="w",
            padx=18,
        ).pack(fill="both", expand=True)

        # separatore sottile
        tk.Frame(sidebar, bg=T["separator"], height=1).pack(fill="x", padx=16)

        # ── voce "sezione" ────────────────────────────────────────────────────
        tk.Label(
            sidebar,
            text="NAVIGAZIONE",
            bg=T["bg_sidebar"],
            fg=T["text_disabled"],
            font=(_FAMILY, 9, "bold"),
            anchor="w",
            padx=18,
        ).pack(fill="x", pady=(14, 4))

        # ── inizializza stato ─────────────────────────────────────────────────
        self._nav_buttons: dict[str, _SidebarButton] = {}
        self._active_page: str = _NAV_ITEMS[0]["key"]

        # ── bottoni navigazione principali ────────────────────────────────────
        for item in _NAV_ITEMS:
            key = item["key"]
            btn = _SidebarButton(
                master  = sidebar,
                icon    = item["icon"],
                label   = item["label"],
                command = lambda k=key: self._navigate(k),
                active  = (key == self._active_page),
            )
            btn.pack(fill="x", pady=1)
            self._nav_buttons[key] = btn

        # ── spacer elastico ───────────────────────────────────────────────────
        tk.Frame(sidebar, bg=T["bg_sidebar"]).pack(fill="both", expand=True)

        # separatore superiore al gruppo inferiore
        tk.Frame(sidebar, bg=T["separator"], height=1).pack(fill="x", padx=16)

        # ── bottoni inferiori (impostazioni, info) ────────────────────────────
        for item in _NAV_BOTTOM:
            key = item["key"]
            btn = _SidebarButton(
                master  = sidebar,
                icon    = item["icon"],
                label   = item["label"],
                command = lambda k=key: self._navigate(k),
                active  = False,
            )
            btn.pack(fill="x", pady=1)
            self._nav_buttons[key] = btn

        # ── footer versione ───────────────────────────────────────────────────
        tk.Label(
            sidebar,
            text="v1.0.0  ·  build 2025",
            bg=T["bg_sidebar"],
            fg=T["text_disabled"],
            font=(_FAMILY, 8),
            anchor="w",
            padx=18,
        ).pack(fill="x", pady=(6, 14))

    # ── navigazione ───────────────────────────────────────────────────────────
    def _navigate(self, key: str):
        if key == self._active_page:
            return

        # deseleziona precedente
        if self._active_page in self._nav_buttons:
            self._nav_buttons[self._active_page].set_active(False)

        self._active_page = key

        # seleziona nuovo
        if key in self._nav_buttons:
            self._nav_buttons[key].set_active(True)

        # delega al metodo di routing pagine
        if hasattr(self, "_show_page"):
            self._show_page(key)

import tkinter as tk
import customtkinter as ctk
from tkinterdnd2 import DND_FILES
from PIL import Image, ImageOps, ImageTk
from pathlib import Path
import database as db
from thumbnail_cache import ToastManager


# ══════════════════════════════════════════════════════════════════════════════
#  UploadFrame
# ══════════════════════════════════════════════════════════════════════════════
class UploadFrame(ctk.CTkFrame):
    # ── palette ───────────────────────────────────────────────────────────────
    C_BG        = "#080c18"
    C_PANEL     = "#0f1629"
    C_ACCENT    = "#0f3460"
    C_ACCENT_HO = "#1a4a80"
    C_BORDER    = "#1a2a4a"
    C_TEXT      = "#c0d4f0"
    C_MUTED     = "#4a6080"
    C_SUCCESS   = "#22c55e"
    C_DANGER    = "#e74c3c"

    # ── tag options ───────────────────────────────────────────────────────────
    DENTI  = [str(n) for n in range(11, 49) if n % 10 != 0 and n % 10 <= 8]
    BRANCHE = ["Conservativa", "Endodonzia", "Chirurgia", "Ortodonzia",
               "Parodontologia", "Protesi", "Implantologia", "Igiene"]
    FASI   = ["Pre-trattamento", "Intra-operatorio", "Post-trattamento",
              "Follow-up 1 mese", "Follow-up 3 mesi", "Follow-up 6 mesi", "Follow-up 1 anno"]

    def __init__(self, master, **kwargs):
        kwargs.setdefault("fg_color", self.C_BG)
        kwargs.setdefault("corner_radius", 0)
        super().__init__(master, **kwargs)

        # ── stato interno ─────────────────────────────────────────────────────
        self._paziente_id:   int | None  = None
        self._paziente_info: dict        = {}
        self._file_path:     Path | None = None
        self._pil_img:       Image.Image | None = None
        self._prev_img:      ImageTk.PhotoImage | None = None   # FIX 4 – GC anchor

        self._tag_dente  = tk.StringVar(value="")
        self._tag_branca = tk.StringVar(value="")
        self._tag_fase   = tk.StringVar(value="")
        self._note_text  = tk.StringVar(value="")

        self._build_layout()

    # ══════════════════════════════════════════════════════════════════════════
    #  LAYOUT
    # ══════════════════════════════════════════════════════════════════════════
    def _build_layout(self):
        self.grid_columnconfigure(0, weight=3, minsize=280)
        self.grid_columnconfigure(1, weight=5)
        self.grid_rowconfigure(0, weight=1)

        self._build_left_panel()
        self._build_right_panel()

    # ── colonna sinistra: ricerca paziente ────────────────────────────────────
    def _build_left_panel(self):
        left = ctk.CTkFrame(self, fg_color=self.C_PANEL, corner_radius=12)
        left.grid(row=0, column=0, sticky="nsew", padx=(14, 6), pady=14)
        left.grid_rowconfigure(2, weight=1)
        left.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            left,
            text="👤  Paziente",
            font=ctk.CTkFont("Segoe UI", 14, weight="bold"),
            text_color=self.C_TEXT,
            anchor="w",
        ).grid(row=0, column=0, sticky="ew", padx=14, pady=(14, 6))

        # search bar
        search_row = ctk.CTkFrame(left, fg_color="transparent")
        search_row.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 6))
        search_row.grid_columnconfigure(0, weight=1)

        self._search_entry = ctk.CTkEntry(
            search_row,
            placeholder_text="🔍  Cerca nome, cognome o ID…",
            fg_color="#0a1428",
            border_color=self.C_BORDER,
            text_color=self.C_TEXT,
            font=ctk.CTkFont("Segoe UI", 12),
            height=36,
        )
        self._search_entry.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self._search_entry.bind("<KeyRelease>", self._on_search)

        ctk.CTkButton(
            search_row,
            text="↺",
            width=34, height=36,
            fg_color=self.C_BORDER,
            hover_color=self.C_ACCENT,
            text_color=self.C_MUTED,
            font=ctk.CTkFont("Segoe UI", 14),
            command=self._reset_search,
        ).grid(row=0, column=1)

        # lista risultati
        self._results_scroll = ctk.CTkScrollableFrame(
            left,
            fg_color="#0a1020",
            scrollbar_button_color=self.C_ACCENT,
            scrollbar_button_hover_color=self.C_ACCENT_HO,
            corner_radius=8,
        )
        self._results_scroll.grid(row=2, column=0, sticky="nsew", padx=10, pady=(0, 10))
        self._results_scroll.grid_columnconfigure(0, weight=1)

        # riquadro paziente selezionato
        self._sel_frame = ctk.CTkFrame(left, fg_color="#0a1428", corner_radius=8)
        self._sel_frame.grid(row=3, column=0, sticky="ew", padx=10, pady=(0, 14))
        self._sel_frame.grid_columnconfigure(0, weight=1)

        self._sel_label = ctk.CTkLabel(
            self._sel_frame,
            text="Nessun paziente selezionato",
            text_color=self.C_MUTED,
            font=ctk.CTkFont("Segoe UI", 11),
            anchor="w",
            wraplength=220,
        )
        self._sel_label.grid(row=0, column=0, sticky="ew", padx=10, pady=8)

    # ── colonna destra: dropzone + tag + salva ────────────────────────────────
    def _build_right_panel(self):
        right = ctk.CTkFrame(self, fg_color=self.C_PANEL, corner_radius=12)
        right.grid(row=0, column=1, sticky="nsew", padx=(6, 14), pady=14)
        right.grid_rowconfigure(1, weight=1)
        right.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            right,
            text="📁  Carica Immagine",
            font=ctk.CTkFont("Segoe UI", 14, weight="bold"),
            text_color=self.C_TEXT,
            anchor="w",
        ).grid(row=0, column=0, sticky="ew", padx=14, pady=(14, 6))

        # DropZone canvas
        self._drop_canvas = tk.Canvas(
            right,
            bg="#08101e",
            highlightthickness=2,
            highlightbackground=self.C_BORDER,
            cursor="hand2",
        )
        self._drop_canvas.grid(row=1, column=0, sticky="nsew", padx=14, pady=(0, 8))
        self._draw_drop_hint()

        # FIX 2 – Drag & Drop robusto (strip parentesi graffe Windows)
        self._drop_canvas.drop_target_register(DND_FILES)
        self._drop_canvas.dnd_bind("<<Drop>>", self._on_drop)

        # click per aprire file dialog
        self._drop_canvas.bind("<Button-1>", self._on_canvas_click)

        # FIX 3 – ridisegna preview al resize mantenendo aspect ratio
        self._drop_canvas.bind("<Configure>", self._on_canvas_configure)

        # tag row
        self._build_tag_row(right)

        # note
        self._build_note_row(right)

        # pulsante salva
        self._btn_save = ctk.CTkButton(
            right,
            text="💾  Salva nel Database",
            height=42,
            fg_color=self.C_ACCENT,
            hover_color=self.C_ACCENT_HO,
            text_color="white",
            font=ctk.CTkFont("Segoe UI", 13, weight="bold"),
            corner_radius=9,
            state="disabled",
            command=self._salva,
        )
        self._btn_save.grid(row=4, column=0, sticky="ew", padx=14, pady=(4, 14))

    def _build_tag_row(self, parent):
        tag_frame = ctk.CTkFrame(parent, fg_color="transparent")
        tag_frame.grid(row=2, column=0, sticky="ew", padx=14, pady=(0, 4))
        tag_frame.grid_columnconfigure((0, 1, 2), weight=1)

        _opt_cfg = dict(
            fg_color="#0a1428",
            button_color=self.C_ACCENT,
            button_hover_color=self.C_ACCENT_HO,
            dropdown_fg_color=self.C_PANEL,
            dropdown_hover_color=self.C_ACCENT,
            text_color=self.C_TEXT,
            dropdown_text_color=self.C_TEXT,
            font=ctk.CTkFont("Segoe UI", 12),
            height=34,
            corner_radius=7,
        )

        for col, (lbl, var, vals) in enumerate([
            ("🦷 Dente",   self._tag_dente,  self.DENTI),
            ("🔬 Branca",  self._tag_branca, self.BRANCHE),
            ("📋 Fase",    self._tag_fase,   self.FASI),
        ]):
            cell = ctk.CTkFrame(tag_frame, fg_color="transparent")
            cell.grid(row=0, column=col, sticky="ew", padx=4)
            cell.grid_columnconfigure(0, weight=1)
            ctk.CTkLabel(
                cell, text=lbl,
                text_color=self.C_MUTED,
                font=ctk.CTkFont("Segoe UI", 10),
                anchor="w",
            ).grid(row=0, column=0, sticky="w")
            ctk.CTkOptionMenu(
                cell, variable=var, values=["—"] + vals, **_opt_cfg,
            ).grid(row=1, column=0, sticky="ew")

    def _build_note_row(self, parent):
        note_frame = ctk.CTkFrame(parent, fg_color="transparent")
        note_frame.grid(row=3, column=0, sticky="ew", padx=14, pady=(0, 4))
        note_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            note_frame, text="📝 Note",
            text_color=self.C_MUTED,
            font=ctk.CTkFont("Segoe UI", 10),
            anchor="w",
        ).grid(row=0, column=0, sticky="w")

        self._note_entry = ctk.CTkEntry(
            note_frame,
            textvariable=self._note_text,
            fg_color="#0a1428",
            border_color=self.C_BORDER,
            text_color=self.C_TEXT,
            font=ctk.CTkFont("Segoe UI", 12),
            height=34,
            placeholder_text="Annotazioni cliniche opzionali…",
        )
        self._note_entry.grid(row=1, column=0, sticky="ew")

    # ══════════════════════════════════════════════════════════════════════════
    #  RICERCA PAZIENTE
    # ══════════════════════════════════════════════════════════════════════════
    def _on_search(self, event=None):
        q = self._search_entry.get().strip()
        for w in self._results_scroll.winfo_children():
            w.destroy()
        if not q:
            return
        try:
            rows = db.cerca_pazienti(q)
        except Exception:
            rows = []
        if not rows:
            ctk.CTkLabel(
                self._results_scroll,
                text="Nessun risultato.",
                text_color=self.C_MUTED,
                font=ctk.CTkFont("Segoe UI", 11),
            ).grid(row=0, column=0, pady=14)
            return
        for i, paz in enumerate(rows):
            self._add_result_row(i, paz)

    def _add_result_row(self, idx: int, paz: dict):
        pid  = paz.get("id", "—")
        nome = paz.get("nome", "")
        cogn = paz.get("cognome", "")
        dn   = paz.get("data_nascita", "")

        row = ctk.CTkFrame(
            self._results_scroll,
            fg_color="#111e38",
            corner_radius=6,
            height=38,
        )
        row.grid(row=idx, column=0, sticky="ew", padx=2, pady=2)
        row.grid_propagate(False)
        row.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            row,
            text=f"{cogn} {nome}  |  ID: {pid}  |  {dn}",
            text_color=self.C_TEXT,
            font=ctk.CTkFont("Segoe UI", 11),
            anchor="w",
        ).grid(row=0, column=0, sticky="ew", padx=8, pady=0)

        ctk.CTkButton(
            row,
            text="✔",
            width=30, height=26,
            fg_color=self.C_ACCENT,
            hover_color=self.C_ACCENT_HO,
            text_color="white",
            font=ctk.CTkFont("Segoe UI", 12, weight="bold"),
            command=lambda p=paz: self._select_paziente(p),
        ).grid(row=0, column=1, padx=(0, 6), pady=6)

    def _select_paziente(self, paz: dict):
        self._paziente_id   = paz.get("id")
        self._paziente_info = paz
        nome = paz.get("nome", "")
        cogn = paz.get("cognome", "")
        pid  = paz.get("id", "—")
        self._sel_label.configure(
            text=f"✔  {cogn} {nome}\nID: {pid}",
            text_color=self.C_SUCCESS,
        )
        self._update_save_btn()

    def _reset_search(self):
        self._search_entry.delete(0, "end")
        for w in self._results_scroll.winfo_children():
            w.destroy()

    # ══════════════════════════════════════════════════════════════════════════
    #  DROP ZONE  –  FIX 1, 2, 3, 4
    # ══════════════════════════════════════════════════════════════════════════

    # FIX 2 – pulizia path Windows con parentesi graffe e spazi
    @staticmethod
    def _clean_drop_path(raw: str) -> Path:
        cleaned = raw.strip().strip("{}")
        return Path(cleaned)

    def _on_drop(self, event):
        path = self._clean_drop_path(event.data)
        if path.suffix.lower() not in {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif", ".webp"}:
            ToastManager.show(self, "Formato non supportato.", kind="error")
            return
        self._load_file(path)

    def _on_canvas_click(self, event=None):
        from tkinter import filedialog
        raw = filedialog.askopenfilename(
            title="Seleziona immagine",
            filetypes=[
                ("Immagini", "*.jpg *.jpeg *.png *.bmp *.tiff *.tif *.webp"),
                ("Tutti i file", "*.*"),
            ],
        )
        if raw:
            self._load_file(Path(raw))

    def _load_file(self, path: Path):
        try:
            img = Image.open(path)
            # FIX 1 – EXIF rotation: raddrizza l'immagine se scattata con smartphone
            img = ImageOps.exif_transpose(img)
            img = img.convert("RGB")
        except Exception as exc:
            ToastManager.show(self, f"Impossibile aprire il file:\n{exc}", kind="error")
            return

        self._file_path = path
        self._pil_img   = img

        self._drop_canvas.configure(highlightbackground=self.C_ACCENT)
        self._render_preview()   # FIX 3 / 4
        self._update_save_btn()

    # FIX 3 – ridisegna al resize del canvas
    def _on_canvas_configure(self, event=None):
        if self._pil_img is not None:
            self._render_preview()
        else:
            self._draw_drop_hint()

    # FIX 3 + 4 – preview centrata con aspect ratio corretto + GC anchor
    def _render_preview(self):
        if self._pil_img is None:
            return

        cw = self._drop_canvas.winfo_width()
        ch = self._drop_canvas.winfo_height()
        if cw < 4 or ch < 4:
            return

        img_w, img_h = self._pil_img.size
        scale = min(cw / img_w, ch / img_h)
        new_w = max(1, int(img_w * scale))
        new_h = max(1, int(img_h * scale))

        resized = self._pil_img.resize((new_w, new_h), Image.LANCZOS)

        # FIX 4 – mantieni sempre la reference per il GC
        self._prev_img = ImageTk.PhotoImage(resized)

        self._drop_canvas.delete("all")
        x = cw // 2
        y = ch // 2
        self._drop_canvas.create_image(x, y, image=self._prev_img, anchor="center", tags="preview")

        # nome file in sovrimpressione
        fname = self._file_path.name if self._file_path else ""
        if fname:
            self._drop_canvas.create_rectangle(
                0, ch - 26, cw, ch,
                fill="#06101e", outline="", stipple="gray50",
            )
            self._drop_canvas.create_text(
                cw // 2, ch - 13,
                text=fname,
                fill=self.C_MUTED,
                font=("Segoe UI", 9),
            )

    def _draw_drop_hint(self):
        self._drop_canvas.delete("all")
        cw = self._drop_canvas.winfo_width()  or 300
        ch = self._drop_canvas.winfo_height() or 200
        cx, cy = cw // 2, ch // 2

        # rettangolo tratteggiato simulato con linee
        dash = (6, 4)
        margin = 20
        self._drop_canvas.create_rectangle(
            margin, margin, cw - margin, ch - margin,
            outline=self.C_BORDER, width=2, dash=dash,
        )
        self._drop_canvas.create_text(
            cx, cy - 22,
            text="⬆",
            fill=self.C_ACCENT,
            font=("Segoe UI", 28),
        )
        self._drop_canvas.create_text(
            cx, cy + 16,
            text="Trascina un'immagine qui\noppure clicca per selezionarla",
            fill=self.C_MUTED,
            font=("Segoe UI", 12),
            justify="center",
        )

    # ══════════════════════════════════════════════════════════════════════════
    #  SALVATAGGIO
    # ══════════════════════════════════════════════════════════════════════════
    def _update_save_btn(self):
        ready = (
            self._paziente_id is not None
            and self._file_path is not None
        )
        self._btn_save.configure(state="normal" if ready else "disabled")

    def _salva(self):
        if self._paziente_id is None or self._file_path is None:
            return

        dente  = self._tag_dente.get()
        branca = self._tag_branca.get()
        fase   = self._tag_fase.get()
        note   = self._note_text.get().strip()

        payload = {
            "paziente_id":    self._paziente_id,
            "percorso_file":  str(self._file_path.resolve()),
            "dente":          dente  if dente  not in ("", "—") else None,
            "branca":         branca if branca not in ("", "—") else None,
            "fase":           fase   if fase   not in ("", "—") else None,
            "note":           note   or None,
        }

        try:
            db.salva_foto(**payload)
            ToastManager.show(self, "✔  Immagine salvata con successo!", kind="success")
            self._reset_form()
        except Exception as exc:
            ToastManager.show(self, f"Errore salvataggio:\n{exc}", kind="error")

    def _reset_form(self):
        self._file_path  = None
        self._pil_img    = None
        self._prev_img   = None
        self._tag_dente.set("")
        self._tag_branca.set("")
        self._tag_fase.set("")
        self._note_text.set("")
        self._drop_canvas.configure(highlightbackground=self.C_BORDER)
        self._draw_drop_hint()
        self._update_save_btn()

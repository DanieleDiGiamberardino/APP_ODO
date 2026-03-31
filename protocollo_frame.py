# =============================================================================
#  DentalPhoto Pro — ProtocolloFrame (Versione Corretta e Definitiva)
# =============================================================================

import customtkinter as ctk
from tkinter import filedialog
import database as db

# ---------------------------------------------------------------------------
# TEMA E COLORI (Traduzione sicura)
# ---------------------------------------------------------------------------
from theme import MODERN_THEME as _real_T

T = {
    "bg_main":        _real_T.get("bg_root", "#0b0e17"),
    "bg_panel":       _real_T.get("bg_panel", "#131929"),
    "bg_card":        _real_T.get("bg_panel", "#131929"),
    "bg_input":       _real_T.get("bg_input", "#0d1424"),
    "bg_hover":       _real_T.get("bg_panel_alt", "#192035"),
    "accent":         _real_T.get("accent", "#00d4aa"),
    "accent_dim":     _real_T.get("accent_dim", "#00a882"),
    "accent_success": _real_T.get("success", "#22d3a5"),
    "accent_warning": _real_T.get("warning", "#f5a623"),
    "accent_danger":  _real_T.get("danger", "#f04a5e"),
    "text_primary":   _real_T.get("text_primary", "#eef2ff"),
    "text_secondary": _real_T.get("text_secondary", "#7a90b8"),
    "text_disabled":  _real_T.get("text_disabled", "#3a4a66"),
    "border":         _real_T.get("border", "#1e2d4a"),
    "border_active":  _real_T.get("border_focus", "#00d4aa"),
}

# ---------------------------------------------------------------------------
# CONFIGURAZIONE PROTOCOLLI
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
#  POPUP SELEZIONE PAZIENTE
# =============================================================================
class SelezionaPazienteDialog(ctk.CTkToplevel):
    """Popup per cercare e selezionare un paziente dal database."""
    def __init__(self, master, on_select):
        super().__init__(master)
        self.title("🔍 Cerca Paziente")
        self.geometry("450x550")
        self.on_select = on_select
        self.configure(fg_color=T["bg_main"])
        
        self.attributes("-topmost", True)
        self.grab_set()

        self.entry_cerca = ctk.CTkEntry(self, placeholder_text="Digita cognome o nome...", height=40, fg_color=T["bg_input"])
        self.entry_cerca.pack(padx=20, pady=20, fill="x")
        self.entry_cerca.bind("<KeyRelease>", self._cerca)

        self.scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.scroll.pack(padx=20, pady=(0, 20), fill="both", expand=True)
        self._cerca()

    def _cerca(self, event=None):
        q = self.entry_cerca.get()
        for w in self.scroll.winfo_children(): 
            w.destroy()
            
        try:
            pazienti = db.cerca_pazienti(q)
        except Exception:
            pazienti = []
            
        if not pazienti:
            ctk.CTkLabel(self.scroll, text="Nessun paziente trovato.", text_color=T["text_secondary"]).pack(pady=20)
            
        for p in pazienti[:30]:
            btn = ctk.CTkButton(
                self.scroll,
                text=f"👤 {p['cognome']} {p['nome']}  (ID: {p['id']})",
                anchor="w", height=38,
                fg_color=T["bg_panel"], hover_color=T["accent_dim"],
                command=lambda paz=p: self._scegli(paz)
            )
            btn.pack(fill="x", pady=3)

    def _scegli(self, paz):
        self.on_select(paz)
        self.destroy()


# =============================================================================
#  SINGOLA CARD FOTOGRAFICA (SLOT)
# =============================================================================
class PhotoSlotCard(ctk.CTkFrame):
    SLOT_W = 190
    SLOT_H = 155

    def __init__(self, master, shot: dict, slot_index: int, **kwargs):
        super().__init__(master, width=self.SLOT_W, height=self.SLOT_H, corner_radius=10,
                         fg_color=T["bg_input"], border_width=1, border_color=T["border"], **kwargs)
        self.shot       = shot
        self.slot_index = slot_index
        self.image_path: str | None = None
        self._filled    = False
        
        self.grid_propagate(False)
        self.pack_propagate(False)
        self._build_empty_state()
        self._bind_hover()

    def _build_empty_state(self):
        self._clear_children()
        self._lbl_index = ctk.CTkLabel(self, text=f"#{self.slot_index + 1:02d}", font=("Segoe UI", 10, "bold"), text_color=T["text_disabled"])
        self._lbl_index.place(x=8, y=7)

        center = ctk.CTkFrame(self, fg_color="transparent")
        center.place(relx=0.5, rely=0.5, anchor="center")
        ctk.CTkLabel(center, text=self.shot["icon"], font=("Segoe UI", 28), text_color=T["text_disabled"]).pack(pady=(0, 4))
        ctk.CTkLabel(center, text=self.shot["name"], font=("Segoe UI", 12, "bold"), text_color=T["text_secondary"], justify="center").pack()
        ctk.CTkLabel(center, text=self.shot["hint"], font=("Segoe UI", 9), text_color=T["text_disabled"], justify="center", wraplength=160).pack(pady=(2, 0))

        self._btn_add = ctk.CTkButton(self, text="+ Aggiungi", width=90, height=24, corner_radius=6, font=("Segoe UI", 10, "bold"),
                                      fg_color=T["bg_hover"], hover_color=T["accent_dim"], text_color=T["text_secondary"],
                                      border_width=1, border_color=T["border"], command=self._pick_image)
        self._btn_add.place(relx=0.5, rely=1.0, anchor="s", y=-10)

    def _build_filled_state(self, path: str):
        self._clear_children()
        self.configure(fg_color=T["bg_hover"], border_color=T["accent_success"], border_width=2)
        ctk.CTkLabel(self, text=" ✓ ", font=("Segoe UI", 10, "bold"), text_color="#FFFFFF", fg_color=T["accent_success"], corner_radius=4).place(relx=1.0, x=-6, y=6, anchor="ne")
        ctk.CTkLabel(self, text=f"#{self.slot_index + 1:02d}", font=("Segoe UI", 10, "bold"), text_color=T["accent_success"]).place(x=8, y=7)

        center = ctk.CTkFrame(self, fg_color="transparent")
        center.place(relx=0.5, rely=0.45, anchor="center")
        ctk.CTkLabel(center, text="🖼️", font=("Segoe UI", 26)).pack(pady=(0, 4))
        ctk.CTkLabel(center, text=self.shot["name"], font=("Segoe UI", 12, "bold"), text_color=T["text_primary"], justify="center").pack()

        filename = path.split("/")[-1].split("\\")[-1]
        if len(filename) > 22: filename = filename[:19] + "…"
        ctk.CTkLabel(self, text=filename, font=("Segoe UI", 9), text_color=T["text_secondary"]).place(relx=0.5, rely=1.0, anchor="s", y=-28)

        ctk.CTkButton(self, text="✕ Rimuovi", width=85, height=22, corner_radius=6, font=("Segoe UI", 9), fg_color="transparent",
                      hover_color=T["accent_danger"], text_color=T["text_disabled"], command=self._remove_image).place(relx=0.5, rely=1.0, anchor="s", y=-6)

    def _pick_image(self):
        path = filedialog.askopenfilename(title=f"Seleziona: {self.shot['name'].replace(chr(10), ' ')}",
                                          filetypes=[("Immagini", "*.jpg *.jpeg *.png *.webp"), ("Tutti i file", "*.*")])
        if path: self.set_image(path)

    def set_image(self, path: str):
        self.image_path = path
        self._filled = True
        self._build_filled_state(path)
        self._notify_parent()

    def _remove_image(self):
        self.image_path = None
        self._filled = False
        self.configure(fg_color=T["bg_input"], border_color=T["border"], border_width=1)
        self._build_empty_state()
        self._notify_parent()

    def _notify_parent(self):
        parent = self.master
        while parent is not None:
            if hasattr(parent, "_on_slot_changed"):
                parent._on_slot_changed()
                break
            parent = getattr(parent, "master", None)

    def _bind_hover(self):
        self.bind("<Enter>", lambda e: self.configure(border_color=T["accent"], border_width=2) if not self._filled else None)
        self.bind("<Leave>", lambda e: self.configure(border_color=T["border"], border_width=1) if not self._filled else None)

    def _clear_children(self):
        for widget in self.winfo_children(): widget.destroy()

    @property
    def is_filled(self) -> bool:
        return self._filled


# =============================================================================
#  PROTOCOLLO FRAME PRINCIPALE
# =============================================================================
class ProtocolloFrame(ctk.CTkFrame):
    SIDEBAR_W = 260

    def __init__(self, master, **kwargs):
        super().__init__(master, fg_color=T["bg_main"], **kwargs)

        self._paziente_selezionato = None
        self._selected_protocol_key: str = PROTOCOL_KEYS[0]
        self._slots: list[PhotoSlotCard]  = []

        self.grid_columnconfigure(0, weight=0, minsize=self.SIDEBAR_W)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._build_sidebar()
        self._build_content_area()
        self._load_protocol(self._selected_protocol_key)

    def _build_sidebar(self):
        self._sidebar = ctk.CTkFrame(self, width=self.SIDEBAR_W, fg_color=T["bg_panel"], corner_radius=0, border_width=1, border_color=T["border"])
        self._sidebar.grid(row=0, column=0, sticky="nsew")
        self._sidebar.grid_propagate(False)
        self._sidebar.grid_columnconfigure(0, weight=1)

        header = ctk.CTkFrame(self._sidebar, fg_color=T["bg_card"], corner_radius=0)
        header.grid(row=0, column=0, sticky="ew")
        ctk.CTkLabel(header, text="📋  Protocollo", font=("Segoe UI", 15, "bold"), text_color=T["text_primary"]).grid(row=0, column=0, padx=18, pady=(16, 2), sticky="w")
        ctk.CTkLabel(header, text="Sessione fotografica guidata", font=("Segoe UI", 11), text_color=T["text_secondary"]).grid(row=1, column=0, padx=18, pady=(0, 14), sticky="w")
        ctk.CTkFrame(self._sidebar, height=1, fg_color=T["border"]).grid(row=1, column=0, sticky="ew")

        inner = ctk.CTkScrollableFrame(self._sidebar, fg_color="transparent")
        inner.grid(row=2, column=0, sticky="nsew")
        self._sidebar.grid_rowconfigure(2, weight=1)
        inner.grid_columnconfigure(0, weight=1)

        self._build_section_title(inner, row=0, text="👤  Paziente")
        self._patient_card = ctk.CTkFrame(inner, fg_color=T["bg_input"], corner_radius=8, border_width=1, border_color=T["border"], height=64)
        self._patient_card.grid(row=1, column=0, sticky="ew", padx=16, pady=(4, 14))
        self._patient_card.grid_propagate(False)
        
        ctk.CTkLabel(self._patient_card, text="Nessun paziente", font=("Segoe UI", 11), text_color=T["text_disabled"]).place(relx=0.5, rely=0.35, anchor="center")
        self._btn_select_patient = ctk.CTkButton(self._patient_card, text="Seleziona →", width=100, height=20, font=("Segoe UI", 10, "bold"),
                                                 fg_color=T["accent_dim"], hover_color=T["accent"], command=self._on_select_patient)
        self._btn_select_patient.place(relx=0.5, rely=0.78, anchor="center")

        self._build_section_title(inner, row=2, text="🗂️  Tipo Protocollo")
        self._protocol_var = ctk.StringVar(value=PROTOCOL_KEYS[0])
        self._protocol_menu = ctk.CTkOptionMenu(inner, values=PROTOCOL_KEYS, variable=self._protocol_var, font=("Segoe UI", 12),
                                                fg_color=T["bg_input"], button_color=T["accent_dim"], button_hover_color=T["accent"],
                                                command=self._on_protocol_change)
        self._protocol_menu.grid(row=3, column=0, padx=16, pady=(4, 16), sticky="ew")

        self._build_section_title(inner, row=4, text="📊  Avanzamento")
        self._progress_frame = ctk.CTkFrame(inner, fg_color=T["bg_input"], corner_radius=8, border_width=1, border_color=T["border"])
        self._progress_frame.grid(row=5, column=0, sticky="ew", padx=16, pady=(4, 16))
        self._progress_frame.grid_columnconfigure(0, weight=1)

        self._lbl_progress_count = ctk.CTkLabel(self._progress_frame, text="0 / 0  foto", font=("Segoe UI", 20, "bold"), text_color=T["accent"])
        self._lbl_progress_count.grid(row=0, column=0, pady=(12, 4))
        self._progressbar = ctk.CTkProgressBar(self._progress_frame, height=8, corner_radius=4, fg_color=T["bg_hover"], progress_color=T["accent"])
        self._progressbar.set(0)
        self._progressbar.grid(row=1, column=0, padx=10, pady=(0, 8), sticky="ew")
        self._lbl_progress_pct = ctk.CTkLabel(self._progress_frame, text="0% completato", font=("Segoe UI", 10), text_color=T["text_secondary"])
        self._lbl_progress_pct.grid(row=2, column=0, pady=(0, 12))

        self._build_section_title(inner, row=6, text="📝  Note Sessione")
        self._txt_notes = ctk.CTkTextbox(inner, height=80, fg_color=T["bg_input"], border_width=1, border_color=T["border"], font=("Segoe UI", 11))
        self._txt_notes.grid(row=7, column=0, sticky="ew", padx=16, pady=(4, 0))
        self._txt_notes.insert("0.0", "Note cliniche aggiuntive…")

        footer = ctk.CTkFrame(self._sidebar, fg_color=T["bg_card"], corner_radius=0, border_width=1, border_color=T["border"])
        footer.grid(row=3, column=0, sticky="ew")
        footer.grid_columnconfigure(0, weight=1)
        self._btn_save = ctk.CTkButton(footer, text="💾  Salva Protocollo", height=42, font=("Segoe UI", 13, "bold"),
                                       fg_color=T["accent_dim"], hover_color=T["accent"], state="disabled", command=self._on_save_protocol)
        self._btn_save.grid(row=0, column=0, padx=16, pady=14, sticky="ew")

    def _build_content_area(self):
        self._content = ctk.CTkFrame(self, fg_color=T["bg_main"], corner_radius=0)
        self._content.grid(row=0, column=1, sticky="nsew")
        self._content.grid_rowconfigure(1, weight=1)
        self._content.grid_columnconfigure(0, weight=1)

        self._content_header = ctk.CTkFrame(self._content, fg_color=T["bg_panel"], corner_radius=0, border_width=1, border_color=T["border"], height=64)
        self._content_header.grid(row=0, column=0, sticky="ew")
        self._content_header.grid_propagate(False)
        self._content_header.grid_columnconfigure(1, weight=1)

        self._lbl_protocol_title = ctk.CTkLabel(self._content_header, text="", font=("Segoe UI", 17, "bold"), text_color=T["text_primary"])
        self._lbl_protocol_title.grid(row=0, column=0, padx=(22, 0), pady=(12, 2), sticky="w")
        self._lbl_protocol_desc = ctk.CTkLabel(self._content_header, text="", font=("Segoe UI", 11), text_color=T["text_secondary"])
        self._lbl_protocol_desc.grid(row=1, column=0, padx=(22, 0), pady=(0, 10), sticky="w")

        self._lbl_badge = ctk.CTkLabel(self._content_header, text="", font=("Segoe UI", 10, "bold"), text_color=T["accent"], fg_color=T["bg_hover"], corner_radius=6, padx=10, pady=4)
        self._lbl_badge.grid(row=0, column=2, rowspan=2, padx=22, pady=14, sticky="e")

        self._grid_scroll = ctk.CTkScrollableFrame(self._content, fg_color=T["bg_main"])
        self._grid_scroll.grid(row=1, column=0, sticky="nsew", padx=0, pady=0)

    def _load_protocol(self, key: str):
        self._selected_protocol_key = key
        protocol = PROTOCOLS[key]

        for widget in self._grid_scroll.winfo_children(): widget.destroy()
        self._slots.clear()

        self._lbl_protocol_title.configure(text=f"📋  {protocol['label']}")
        self._lbl_protocol_desc.configure(text=f"{len(protocol['shots'])} scatti richiesti · Completare la griglia per sbloccare il salvataggio")

        cols = protocol["cols"]
        self._grid_scroll.grid_columnconfigure(list(range(cols)), weight=1)

        for idx, shot in enumerate(protocol["shots"]):
            slot = PhotoSlotCard(self._grid_scroll, shot=shot, slot_index=idx)
            slot.grid(row=idx // cols, column=idx % cols, padx=12, pady=12, sticky="n")
            self._slots.append(slot)

        self._update_progress()

    def _on_slot_changed(self):
        self._update_progress()

    def _update_progress(self):
        total = len(self._slots)
        filled = sum(1 for s in self._slots if s.is_filled)
        pct = filled / total if total > 0 else 0.0

        self._progressbar.set(pct)
        self._lbl_progress_count.configure(text=f"{filled} / {total}  foto")
        self._lbl_progress_pct.configure(text=f"{int(pct * 100)}% completato")

        remaining = total - filled
        if remaining == 0:
            self._lbl_badge.configure(text="✓  Completato", text_color=T["accent_success"])
            self._progressbar.configure(progress_color=T["accent_success"])
        else:
            self._lbl_badge.configure(text=f"{remaining} slot rimanenti", text_color=T["accent"])
            self._progressbar.configure(progress_color=T["accent"])

        self._btn_save.configure(state="normal" if filled == total and total > 0 else "disabled",
                                 fg_color=T["accent"] if filled == total else T["accent_dim"])

    def _on_protocol_change(self, value: str):
        self._load_protocol(value)

    def _on_select_patient(self):
        SelezionaPazienteDialog(self, on_select=self._set_patient)

    def _set_patient(self, paz: dict):
        self._paziente_selezionato = paz
        self._patient_card.configure(border_color=T["accent"])
        for widget in self._patient_card.winfo_children():
            if isinstance(widget, ctk.CTkLabel): widget.destroy()
                
        ctk.CTkLabel(self._patient_card, text=f"👤  {paz['cognome']} {paz['nome']} — #{paz['id']}", font=("Segoe UI", 11, "bold"), text_color=T["text_primary"]).place(relx=0.5, rely=0.35, anchor="center")
        self._btn_select_patient.configure(text="Cambia →")

    def _on_save_protocol(self):
        if not self._paziente_selezionato:
            try: self.winfo_toplevel().toast("Devi prima selezionare un Paziente!", "error")
            except: pass
            return

        paz_id = self._paziente_selezionato["id"]
        note_globali = self._txt_notes.get("0.0", "end").strip()
        nome_protocollo = PROTOCOLS[self._selected_protocol_key]["label"]
        salvate = 0
        
        for slot in self._slots:
            if slot.is_filled and slot.image_path:
                nome_scatto = slot.shot["name"].replace('\n', ' ')
                nota_scatto = f"[{nome_protocollo}] {nome_scatto}"
                if note_globali and note_globali != "Note cliniche aggiuntive…":
                    nota_scatto += f" | {note_globali}"

                try:
                    db.upload_foto(paziente_id=paz_id, sorgente_path=slot.image_path, fase=nome_scatto, note=nota_scatto)
                    salvate += 1
                except Exception as e:
                    print(f"Errore salvataggio foto {nome_scatto}: {e}")

        try: self.winfo_toplevel().toast(f"✅ Protocollo completato! {salvate} foto salvate.", "success")
        except: pass
            
        self._load_protocol(self._selected_protocol_key)
        self._txt_notes.delete("0.0", "end")
        self._txt_notes.insert("0.0", "Note cliniche aggiuntive…")

    def _build_section_title(self, parent, row: int, text: str):
        ctk.CTkLabel(parent, text=text, font=("Segoe UI", 11, "bold"), text_color=T["text_secondary"]).grid(row=row, column=0, sticky="w", padx=16, pady=(14, 2))

if __name__ == "__main__":
    ctk.set_appearance_mode("dark")
    root = ctk.CTk()
    root.title("DentalPhoto Pro — Protocollo Fotografico")
    root.geometry("1280x780")
    frame = ProtocolloFrame(root)
    frame.pack(fill="both", expand=True)
    root.mainloop()
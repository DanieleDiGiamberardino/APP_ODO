import json
from pathlib import Path
import tkinter as tk
from tkinter import filedialog
import customtkinter as ctk

import database as db
from theme import MODERN_THEME

def get_config_path() -> Path:
    return db.APP_DIR / "config.json"

def load_config() -> dict:
    """Carica le impostazioni o restituisce i valori di default."""
    p = get_config_path()
    if p.exists():
        try:
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"reflex_path": "", "backup_path": "", "tema": "Dark"}

def save_config(data: dict):
    """Salva le impostazioni su disco."""
    try:
        with open(get_config_path(), "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        print("Errore salvataggio config:", e)

class ImpostazioniFrame(ctk.CTkFrame):
    def __init__(self, master, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self._config = load_config()
        self._build_ui()

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        
        # Pannello centrale
        panel = ctk.CTkFrame(self, fg_color=MODERN_THEME["bg_panel"], corner_radius=12)
        panel.grid(row=0, column=0, sticky="nsew", padx=40, pady=40)
        panel.grid_columnconfigure(1, weight=1)

        # Titolo
        ctk.CTkLabel(
            panel, text="⚙️  Impostazioni Generali", 
            font=("Segoe UI", 22, "bold"), text_color=MODERN_THEME["text_primary"]
        ).grid(row=0, column=0, columnspan=3, padx=24, pady=(24, 20), sticky="w")

        # ── 1. Cartella Auto-Import Reflex ──
        ctk.CTkLabel(
            panel, text="Cartella Reflex (Auto-Import):", 
            font=("Segoe UI", 12), text_color=MODERN_THEME["text_secondary"]
        ).grid(row=1, column=0, padx=24, pady=(10, 5), sticky="w")
        
        self._var_reflex = tk.StringVar(value=self._config.get("reflex_path", ""))
        ctk.CTkEntry(
            panel, textvariable=self._var_reflex, state="readonly", 
            fg_color=MODERN_THEME["bg_input"], border_color=MODERN_THEME["border"], height=36
        ).grid(row=1, column=1, padx=(0, 10), pady=(10, 5), sticky="ew")
        
        ctk.CTkButton(
            panel, text="Sfoglia…", width=80, height=36,
            fg_color=MODERN_THEME["bg_input"], hover_color=MODERN_THEME["sidebar_btn_hover"],
            border_width=1, border_color=MODERN_THEME["border"],
            command=self._sfoglia_reflex
        ).grid(row=1, column=2, padx=(0, 24), pady=(10, 5))

        # ── 2. Cartella Backup ──
        ctk.CTkLabel(
            panel, text="Cartella di Backup:", 
            font=("Segoe UI", 12), text_color=MODERN_THEME["text_secondary"]
        ).grid(row=2, column=0, padx=24, pady=10, sticky="w")
        
        self._var_backup = tk.StringVar(value=self._config.get("backup_path", ""))
        ctk.CTkEntry(
            panel, textvariable=self._var_backup, state="readonly", 
            fg_color=MODERN_THEME["bg_input"], border_color=MODERN_THEME["border"], height=36
        ).grid(row=2, column=1, padx=(0, 10), pady=10, sticky="ew")
        
        ctk.CTkButton(
            panel, text="Sfoglia…", width=80, height=36,
            fg_color=MODERN_THEME["bg_input"], hover_color=MODERN_THEME["sidebar_btn_hover"],
            border_width=1, border_color=MODERN_THEME["border"],
            command=self._sfoglia_backup
        ).grid(row=2, column=2, padx=(0, 24), pady=10)

        # ── 3. Tema Interfaccia ──
        ctk.CTkLabel(
            panel, text="Tema Visivo:", 
            font=("Segoe UI", 12), text_color=MODERN_THEME["text_secondary"]
        ).grid(row=3, column=0, padx=24, pady=10, sticky="w")
        
        self._var_tema = tk.StringVar(value=self._config.get("tema", "Dark"))
        menu_tema = ctk.CTkOptionMenu(
            panel, values=["Dark", "Light", "System"], variable=self._var_tema,
            fg_color=MODERN_THEME["bg_input"], button_color=MODERN_THEME["accent"], height=36,
            command=self._cambia_tema
        )
        menu_tema.grid(row=3, column=1, sticky="w", pady=10)

        # ── Bottone Salva ──
        ctk.CTkButton(
            panel, text="💾  Salva Impostazioni", height=42,
            fg_color=MODERN_THEME["accent"], hover_color=MODERN_THEME["accent_dim"],
            font=("Segoe UI", 13, "bold"),
            command=self._salva_tutto
        ).grid(row=4, column=0, columnspan=3, pady=(30, 24))

    def _sfoglia_reflex(self):
        d = filedialog.askdirectory(title="Seleziona la SD della Reflex o Cartella Condivisa")
        if d: self._var_reflex.set(d)

    def _sfoglia_backup(self):
        d = filedialog.askdirectory(title="Seleziona dove salvare i file .zip")
        if d: self._var_backup.set(d)

    def _cambia_tema(self, scelta: str):
        ctk.set_appearance_mode(scelta.lower())

    def _salva_tutto(self):
        self._config["reflex_path"] = self._var_reflex.get()
        self._config["backup_path"] = self._var_backup.get()
        self._config["tema"] = self._var_tema.get()
        save_config(self._config)
        
        # Notifica visiva tramite il parent principale
        if hasattr(self.winfo_toplevel(), "toast"):
            self.winfo_toplevel().toast("✅ Impostazioni salvate!", "success")
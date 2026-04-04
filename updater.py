"""
updater.py
Controllo aggiornamenti in background con popup CustomTkinter.
"""

import json
import threading
import webbrowser
from urllib import request
from urllib.error import URLError

import customtkinter as ctk

# ── Configura queste costanti ─────────────────────────────────────────────────
CURRENT_VERSION = "3.0"
UPDATE_URL       = "https://gist.githubusercontent.com/DanieleDiGiamberardino/414cf7f887786573279e4790001e6d0e/raw/eb7d9be141f6325cdbac3c7854cf6d836761ca7e/gistfile1.txt"
# ─────────────────────────────────────────────────────────────────────────────
# Formato JSON atteso all'URL:
# {
#   "version": "3.1",
#   "changelog": "- Nuova funzione X\n- Fix bug Y",
#   "download_url": "https://tuosito.com/releases/DentalApp_3.1_setup.exe"
# }


def _version_tupla(v: str) -> tuple:
    """Converte "3.1.2" → (3, 1, 2) per confronto corretto."""
    try:
        return tuple(int(x) for x in v.strip().split("."))
    except ValueError:
        return (0,)


# ---------------------------------------------------------------------------
# Dialog
# ---------------------------------------------------------------------------

class UpdateDialog(ctk.CTkToplevel):
    """Popup modale che annuncia il nuovo aggiornamento disponibile."""

    def __init__(self, master, dati: dict, **kwargs):
        super().__init__(master, **kwargs)

        self._url = dati.get("download_url", "")

        self.title("Aggiornamento Disponibile")
        self.resizable(False, False)
        self.grab_set()
        self.focus_force()
        self.lift()

        WIN_W, WIN_H = 480, 320
        self.geometry(f"{WIN_W}x{WIN_H}")
        self._center(WIN_W, WIN_H)

        self._build_ui(dati)

    def _build_ui(self, dati: dict):
        PAD = 22

        ctk.CTkLabel(
            self, text="🚀  Nuovo aggiornamento disponibile!",
            font=ctk.CTkFont(size=16, weight="bold")
        ).pack(pady=(PAD, 2))

        ctk.CTkLabel(
            self,
            text=f"Versione attuale: {CURRENT_VERSION}   →   Nuova versione: {dati.get('version', '?')}",
            font=ctk.CTkFont(size=12),
            text_color="gray",
        ).pack(pady=(0, PAD))

        # Changelog
        frame = ctk.CTkFrame(self, corner_radius=8)
        frame.pack(fill="both", expand=True, padx=PAD, pady=(0, 16))

        ctk.CTkLabel(
            frame, text="Novità:",
            font=ctk.CTkFont(size=12, weight="bold"),
            anchor="w"
        ).pack(anchor="w", padx=12, pady=(10, 2))

        box = ctk.CTkTextbox(frame, height=110, font=ctk.CTkFont(size=12), wrap="word")
        box.pack(fill="both", expand=True, padx=12, pady=(0, 10))
        box.insert("1.0", dati.get("changelog", "Nessun dettaglio disponibile."))
        box.configure(state="disabled")

        # Bottoni
        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(pady=(0, PAD))

        ctk.CTkButton(
            btn_row, text="Ignora", width=110,
            fg_color="gray40", hover_color="gray30",
            command=self.destroy
        ).pack(side="left", padx=8)

        ctk.CTkButton(
            btn_row, text="⬇  Scarica", width=140,
            font=ctk.CTkFont(weight="bold"),
            command=self._scarica
        ).pack(side="left", padx=8)

    def _scarica(self):
        if self._url:
            webbrowser.open(self._url)
        self.destroy()

    def _center(self, w: int, h: int):
        self.update_idletasks()
        x = (self.winfo_screenwidth()  - w) // 2
        y = (self.winfo_screenheight() - h) // 2
        self.geometry(f"{w}x{h}+{x}+{y}")


# ---------------------------------------------------------------------------
# Check in background
# ---------------------------------------------------------------------------

def controlla_aggiornamenti(parent: ctk.CTk) -> None:
    """
    Avvia il controllo aggiornamenti in un thread daemon.
    Non blocca l'avvio dell'app; il popup appare solo se c'è una versione più recente.
    """
    def _worker():
        try:
            req = request.Request(UPDATE_URL, headers={"User-Agent": "DentalApp-Updater"})
            with request.urlopen(req, timeout=3) as resp:
                dati = json.loads(resp.read().decode("utf-8"))

            versione_remota  = dati.get("version", "0")
            if _version_tupla(versione_remota) > _version_tupla(CURRENT_VERSION):
                parent.after(0, lambda: UpdateDialog(parent, dati))

        except (URLError, json.JSONDecodeError, Exception):
            # Nessun internet o JSON malformato: silenzio totale
            pass

    t = threading.Thread(target=_worker, daemon=True)
    t.start()

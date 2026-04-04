"""
ui_network.py
Finestra modale per configurare la Data Directory (locale o rete LAN).
"""

import sys
from tkinter import filedialog, messagebox

import customtkinter as ctk

from config_manager import get_data_dir, set_data_dir


class NetworkSettingsScreen(ctk.CTkToplevel):
    """
    Modale impostazioni percorso dati.

    Esempio d'uso (da menu o pannello impostazioni):
        NetworkSettingsScreen(parent)
    """

    def __init__(self, master=None, **kwargs):
        super().__init__(master, **kwargs)

        self.title("Impostazioni Rete / Percorso Dati")
        self.resizable(False, False)
        self.grab_set()
        self.focus_force()

        WIN_W, WIN_H = 560, 260
        self.geometry(f"{WIN_W}x{WIN_H}")
        self._center(WIN_W, WIN_H)

        self._dir_var = ctk.StringVar(value=str(get_data_dir()))
        self._build_ui()

    # -----------------------------------------------------------------------
    # UI
    # -----------------------------------------------------------------------

    def _build_ui(self):
        PAD = 24

        ctk.CTkLabel(
            self, text="📁  Percorso Dati Applicazione",
            font=ctk.CTkFont(size=17, weight="bold")
        ).pack(pady=(PAD, 4))

        ctk.CTkLabel(
            self,
            text="Puoi puntare a una cartella di rete (es. Z:\\DentalData o \\\\SERVER\\Dati).\n"
                 "Il database e le foto verranno letti/scritti da quel percorso.",
            font=ctk.CTkFont(size=12),
            text_color="gray",
            wraplength=500,
            justify="center",
        ).pack(pady=(0, PAD))

        # ── Riga percorso ───────────────────────────────────────────────────
        frame = ctk.CTkFrame(self, corner_radius=8)
        frame.pack(fill="x", padx=PAD, pady=(0, 8))

        ctk.CTkLabel(
            frame, text="Cartella attiva:",
            font=ctk.CTkFont(size=12, weight="bold")
        ).pack(anchor="w", padx=12, pady=(10, 2))

        row = ctk.CTkFrame(frame, fg_color="transparent")
        row.pack(fill="x", padx=12, pady=(0, 10))

        ctk.CTkEntry(
            row, textvariable=self._dir_var,
            font=ctk.CTkFont(family="Courier", size=11),
            width=390, state="readonly"
        ).pack(side="left", fill="x", expand=True, padx=(0, 8))

        ctk.CTkButton(
            row, text="Sfoglia…", width=90,
            command=self._sfoglia
        ).pack(side="left")

        # ── Bottoni ─────────────────────────────────────────────────────────
        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(pady=(4, PAD))

        ctk.CTkButton(
            btn_row, text="Annulla", width=120,
            fg_color="gray40", hover_color="gray30",
            command=self.destroy
        ).pack(side="left", padx=8)

        ctk.CTkButton(
            btn_row, text="💾  Salva e Riavvia", width=170,
            font=ctk.CTkFont(weight="bold"),
            command=self._salva_e_riavvia
        ).pack(side="left", padx=8)

    # -----------------------------------------------------------------------
    # Azioni
    # -----------------------------------------------------------------------

    def _sfoglia(self):
        scelta = filedialog.askdirectory(
            title="Seleziona la cartella dati",
            mustexist=True,
            parent=self
        )
        if scelta:
            self._dir_var.set(scelta)

    def _salva_e_riavvia(self):
        nuovo = self._dir_var.get().strip()
        if not nuovo:
            messagebox.showwarning("Attenzione", "Seleziona una cartella valida.", parent=self)
            return

        set_data_dir(nuovo)

        messagebox.showinfo(
            "Riavvio necessario",
            "Il percorso è stato salvato.\n\n"
            "L'applicazione verrà chiusa ora.\n"
            "Riaprila per applicare le modifiche.",
            parent=self
        )
        sys.exit(0)

    # -----------------------------------------------------------------------
    # Helper
    # -----------------------------------------------------------------------

    def _center(self, w: int, h: int):
        self.update_idletasks()
        x = (self.winfo_screenwidth()  - w) // 2
        y = (self.winfo_screenheight() - h) // 2
        self.geometry(f"{w}x{h}+{x}+{y}")


# ---------------------------------------------------------------------------
# Demo standalone
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")
    root = ctk.CTk()
    root.withdraw()
    NetworkSettingsScreen(root)
    root.mainloop()

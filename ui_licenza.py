"""
ui_licenza.py
Schermata di attivazione licenza (CustomTkinter).
Usa: license_manager.get_machine_id(), verifica_licenza(), salva_licenza()
"""

import customtkinter as ctk
from license_manager import get_machine_id, verifica_licenza, salva_licenza


class LicenseScreen(ctk.CTkToplevel):
    """
    Finestra modale di attivazione licenza.
    Passa `on_success` (callable) per ricevere notifica dell'attivazione.

    Esempio d'uso:
        if not licenza_valida():
            screen = LicenseScreen(root, on_success=root.deiconify)
            root.withdraw()
            root.mainloop()
    """

    def __init__(self, master=None, on_success=None, **kwargs):
        super().__init__(master, **kwargs)

        self._on_success = on_success
        self._machine_id = get_machine_id()

        # ── Finestra ────────────────────────────────────────────────────────
        self.title("Attivazione Licenza")
        self.resizable(False, False)
        self.grab_set()          # modale
        self.focus_force()

        WIN_W, WIN_H = 520, 420
        self.geometry(f"{WIN_W}x{WIN_H}")
        self._center_window(WIN_W, WIN_H)

        # Impedisce di chiudere senza licenza valida
        self.protocol("WM_DELETE_WINDOW", self._on_close_attempt)

        self._build_ui()

    # -----------------------------------------------------------------------
    # UI
    # -----------------------------------------------------------------------

    def _build_ui(self):
        PAD = 24

        # Titolo
        ctk.CTkLabel(
            self, text="🔑  Attivazione Prodotto",
            font=ctk.CTkFont(size=18, weight="bold")
        ).pack(pady=(PAD, 4))

        ctk.CTkLabel(
            self,
            text="Invia il tuo Machine ID allo sviluppatore per ricevere il Serial Key.",
            font=ctk.CTkFont(size=12),
            text_color="gray",
            wraplength=460,
        ).pack(pady=(0, PAD))

        # ── Sezione Machine ID ──────────────────────────────────────────────
        frame_mid = ctk.CTkFrame(self, corner_radius=8)
        frame_mid.pack(fill="x", padx=PAD, pady=(0, 16))

        ctk.CTkLabel(
            frame_mid, text="Il tuo Machine ID:",
            font=ctk.CTkFont(size=12, weight="bold")
        ).pack(anchor="w", padx=12, pady=(10, 2))

        row = ctk.CTkFrame(frame_mid, fg_color="transparent")
        row.pack(fill="x", padx=12, pady=(0, 10))

        self._mid_var = ctk.StringVar(value=self._machine_id)
        mid_entry = ctk.CTkEntry(
            row, textvariable=self._mid_var,
            state="readonly", font=ctk.CTkFont(family="Courier", size=11),
            width=380
        )
        mid_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))

        ctk.CTkButton(
            row, text="Copia", width=70,
            command=self._copy_machine_id
        ).pack(side="left")

        # ── Sezione Serial Key ──────────────────────────────────────────────
        frame_sk = ctk.CTkFrame(self, corner_radius=8)
        frame_sk.pack(fill="x", padx=PAD, pady=(0, 16))

        ctk.CTkLabel(
            frame_sk, text="Serial Key:",
            font=ctk.CTkFont(size=12, weight="bold")
        ).pack(anchor="w", padx=12, pady=(10, 2))

        self._serial_var = ctk.StringVar()
        self._serial_entry = ctk.CTkEntry(
            frame_sk, textvariable=self._serial_var,
            placeholder_text="XXXXXX-XXXXXX-XXXXXX-XXXXXX-XXXXXX",
            font=ctk.CTkFont(family="Courier", size=11),
            width=460
        )
        self._serial_entry.pack(padx=12, pady=(0, 10), fill="x")

        # ── Messaggio di stato ──────────────────────────────────────────────
        self._status_label = ctk.CTkLabel(
            self, text="", font=ctk.CTkFont(size=12)
        )
        self._status_label.pack()

        # ── Bottone Attiva ──────────────────────────────────────────────────
        ctk.CTkButton(
            self, text="Attiva Licenza", width=180, height=36,
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._attiva
        ).pack(pady=(8, PAD))

    # -----------------------------------------------------------------------
    # Azioni
    # -----------------------------------------------------------------------

    def _copy_machine_id(self):
        self.clipboard_clear()
        self.clipboard_append(self._machine_id)
        self._set_status("Machine ID copiato negli appunti.", color="gray")

    def _attiva(self):
        serial = self._serial_var.get().strip()
        if not serial:
            self._set_status("⚠  Inserisci un Serial Key.", color="orange")
            return

        if verifica_licenza(serial):
            salva_licenza(serial)
            self._set_status("✅  Licenza attivata con successo!", color="green")
            self.after(1200, self._success)
        else:
            self._set_status("❌  Serial Key non valido per questo hardware.", color="red")
            self._serial_entry.focus_set()

    def _set_status(self, msg: str, color: str = "white"):
        self._status_label.configure(text=msg, text_color=color)

    def _success(self):
        if callable(self._on_success):
            self._on_success()
        self.destroy()

    def _on_close_attempt(self):
            """Chiude l'app se si clicca la X senza attivare la licenza."""
            self.master.destroy()

    # -----------------------------------------------------------------------
    # Helper
    # -----------------------------------------------------------------------

    def _center_window(self, w: int, h: int):
        self.update_idletasks()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        x  = (sw - w) // 2
        y  = (sh - h) // 2
        self.geometry(f"{w}x{h}+{x}+{y}")


# ---------------------------------------------------------------------------
# Demo standalone
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    from license_manager import licenza_valida

    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")

    root = ctk.CTk()
    root.title("App Principale")
    root.geometry("600x400")

    def avvia_app():
        root.deiconify()
        ctk.CTkLabel(root, text="✅ App avviata con licenza valida!",
                     font=ctk.CTkFont(size=16)).pack(expand=True)

    if licenza_valida():
        avvia_app()
    else:
        root.withdraw()
        LicenseScreen(root, on_success=avvia_app)

    root.mainloop()

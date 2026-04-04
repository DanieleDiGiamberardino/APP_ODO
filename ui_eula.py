"""
ui_eula.py
Schermata EULA/Privacy GDPR — mostrata solo al primo avvio.
"""

import sys
import customtkinter as ctk
from config_manager import set_eula_accepted

EULA_TEXT = """\
TERMINI DI SERVIZIO, LICENZA D'USO E INFORMATIVA SULLA PRIVACY (GDPR)
Ultimo aggiornamento: 2025

1. NATURA DEL SOFTWARE
Il presente software ("Applicazione") è uno strumento di ausilio gestionale per studi odontoiatrici. Non costituisce dispositivo medico ai sensi del Regolamento (UE) 2017/745 e non sostituisce in alcun modo il giudizio clinico del professionista sanitario.

2. LIMITAZIONE DI RESPONSABILITÀ
Lo sviluppatore declina ogni responsabilità per danni diretti o indiretti derivanti dall'uso o dal mancato uso dell'Applicazione, inclusi, a titolo esemplificativo e non esaustivo: perdita di dati sanitari, interruzione dell'attività, errori di fatturazione. L'utente utilizza il software sotto la propria ed esclusiva responsabilità.

3. BACKUP E INTEGRITÀ DEI DATI
L'utente è il solo responsabile dell'effettuazione di backup regolari del database e di tutti i dati inseriti nell'Applicazione. Lo sviluppatore non fornisce alcun servizio di recupero dati. Si raccomanda di eseguire backup giornalieri su supporto esterno o cloud sicuro.

4. TRATTAMENTO DEI DATI PERSONALI (GDPR – Reg. UE 2016/679)
I dati dei pazienti inseriti nell'Applicazione sono trattati esclusivamente in locale sul dispositivo dell'utente. Lo sviluppatore non raccoglie, non trasmette e non ha accesso ad alcun dato personale o sanitario. Il titolare del trattamento è il professionista/studio che utilizza il software. È responsabilità del titolare adempiere agli obblighi previsti dal GDPR (informative ai pazienti, misure di sicurezza adeguate, registro dei trattamenti).

5. DATI SANITARI (ART. 9 GDPR)
I dati relativi alla salute costituiscono categorie particolari di dati personali. L'utente si impegna ad adottare misure tecniche e organizzative adeguate alla loro protezione, incluse cifratura del disco, accesso con credenziali, e conservazione sicura dei backup.

6. AGGIORNAMENTI E MANUTENZIONE
Lo sviluppatore si riserva il diritto di rilasciare aggiornamenti. L'uso continuato dell'Applicazione dopo un aggiornamento implica l'accettazione delle eventuali modifiche ai presenti termini.

7. PROPRIETÀ INTELLETTUALE
Il software, il codice sorgente e la documentazione sono proprietà esclusiva dello sviluppatore e sono protetti dalle leggi sul diritto d'autore. È vietata la copia, la distribuzione o la modifica senza autorizzazione scritta.

8. LEGGE APPLICABILE
Il presente accordo è regolato dalla legge italiana. Per qualsiasi controversia è competente in via esclusiva il Foro del luogo di residenza dello sviluppatore.

Cliccando su "Continua" dichiari di aver letto, compreso e accettato integralmente i presenti Termini di Servizio e l'Informativa sulla Privacy.
"""


class EulaScreen(ctk.CTkToplevel):
    """
    Finestra modale EULA. Chiudere con la X termina l'app.

    Esempio d'uso:
        EulaScreen(root, on_accept=root.deiconify)
    """

    def __init__(self, master=None, on_accept=None, **kwargs):
        super().__init__(master, **kwargs)

        self._on_accept = on_accept

        self.title("Termini di Servizio e Privacy – Accettazione obbligatoria")
        self.resizable(False, False)
        self.grab_set()
        self.focus_force()

        WIN_W, WIN_H = 640, 520
        self.geometry(f"{WIN_W}x{WIN_H}")
        self._center(WIN_W, WIN_H)

        # Chiusura con X = uscita dall'app (EULA obbligatoria)
        self.protocol("WM_DELETE_WINDOW", lambda: self.master.destroy())
        
        self._accepted = ctk.BooleanVar(value=False)
        self._build_ui()

    def _build_ui(self):
        PAD = 20

        ctk.CTkLabel(
            self,
            text="📋  Termini di Servizio e Informativa Privacy (GDPR)",
            font=ctk.CTkFont(size=15, weight="bold"),
        ).pack(pady=(PAD, 8))

        ctk.CTkLabel(
            self,
            text="Leggi attentamente prima di utilizzare l'applicazione.",
            font=ctk.CTkFont(size=12),
            text_color="gray",
        ).pack(pady=(0, 10))

        # Textbox scrollabile
        box = ctk.CTkTextbox(
            self,
            font=ctk.CTkFont(size=12),
            wrap="word",
            activate_scrollbars=True,
        )
        box.pack(fill="both", expand=True, padx=PAD, pady=(0, 12))
        box.insert("1.0", EULA_TEXT.strip())
        box.configure(state="disabled")

        # Checkbox accettazione
        chk = ctk.CTkCheckBox(
            self,
            text="Ho letto, compreso e accetto i termini di servizio e la privacy policy.",
            variable=self._accepted,
            font=ctk.CTkFont(size=12),
            command=self._on_checkbox_toggle,
        )
        chk.pack(anchor="w", padx=PAD, pady=(0, 12))

        # Bottone Continua (disabilitato finché checkbox non è spuntata)
        self._btn = ctk.CTkButton(
            self,
            text="Continua  →",
            width=180,
            height=36,
            font=ctk.CTkFont(size=13, weight="bold"),
            state="disabled",
            command=self._continua,
        )
        self._btn.pack(pady=(0, PAD))

    def _on_checkbox_toggle(self):
        self._btn.configure(state="normal" if self._accepted.get() else "disabled")

    def _continua(self):
        set_eula_accepted()
        self.destroy()
        if callable(self._on_accept):
            self._on_accept()

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
    EulaScreen(root, on_accept=lambda: print("EULA accettata."))
    root.mainloop()

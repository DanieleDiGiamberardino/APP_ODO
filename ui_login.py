"""
ui_login.py
===========
Schermata di login e pannello gestione utenti.

LoginScreen:
  - Finestra CTk standalone mostrata prima della App principale
  - Campo username + password (toggle visibilità)
  - Feedback errori inline
  - Credenziali default al primo avvio: admin / admin1234

GestioneUtentiFrame:
  - Pannello sidebar "👥 Utenti" (solo admin)
  - Lista utenti con ruolo e stato
  - Form aggiunta / modifica / cambio password / disattiva / elimina
  - Log accessi con filtro
"""

import tkinter as tk
from tkinter import messagebox
import customtkinter as ctk
from datetime import datetime
from typing import Optional

import auth
from auth import SessioneUtente, RUOLI

# ---------------------------------------------------------------------------
# Palette Login (leggermente diversa per distinguerla dalla app)
# ---------------------------------------------------------------------------

C = {
    "bg":        "#080c18",
    "card":      "#0f1629",
    "border":    "#1e2d4a",
    "accent":    "#0f3460",
    "accent_br": "#e94560",
    "verde":     "#4caf50",
    "grigio":    "#6b7a99",
    "chiaro":    "#e0e8ff",
    "input_bg":  "#0a0f1e",
    "error":     "#f44336",
}

FONT_LOGO  = ("Segoe UI", 32, "bold")
FONT_SUB   = ("Segoe UI", 11)
FONT_LABEL = ("Segoe UI", 10)
FONT_INPUT = ("Segoe UI", 13)
FONT_BTN   = ("Segoe UI", 13, "bold")

# Palette pannello utenti (coerente con il resto della app)
CU = {
    "card":     "#16213e",
    "entry_bg": "#0d1117",
    "accent":   "#0f3460",
    "red":      "#e94560",
    "verde":    "#4caf50",
    "grigio":   "#9e9e9e",
    "chiaro":   "#e0e0e0",
    "arancio":  "#ff9800",
    "divider":  "#1e2d4a",
}
FONT_SEZ  = ("Segoe UI", 13, "bold")
FONT_NRM  = ("Segoe UI", 12)
FONT_SML  = ("Segoe UI", 10)
FONT_MONO = ("Consolas", 9)


# ===========================================================================
# SCHERMATA DI LOGIN
# ===========================================================================

class LoginScreen(ctk.CTk):
    """
    Finestra standalone mostrata all'avvio prima della App principale.
    Blocca l'esecuzione finché il login non ha successo.

    Uso:
        login = LoginScreen()
        login.mainloop()
        if login.login_riuscito:
            app = App()
            app.mainloop()
    """

    def __init__(self):
        super().__init__()
        self.login_riuscito = False
        self.title("DentalPhoto — Accesso")
        self.geometry("460x560")
        self.resizable(False, False)
        self.configure(fg_color=C["bg"])
        # Centra la finestra
        self.update_idletasks()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        x  = (sw - 460) // 2
        y  = (sh - 560) // 2
        self.geometry(f"460x560+{x}+{y}")

        self._tentativi = 0
        self._build_ui()
        self.bind("<Return>", lambda e: self._login())

    # ------------------------------------------------------------------

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # Card centrale
        card = ctk.CTkFrame(self, fg_color=C["card"], corner_radius=20,
                            border_width=1, border_color=C["border"])
        card.grid(row=0, column=0, padx=40, pady=40, sticky="nsew")
        card.grid_columnconfigure(0, weight=1)

        # Logo + titolo
        ctk.CTkLabel(card, text="🦷", font=("Segoe UI", 52)).grid(
            row=0, column=0, pady=(36, 4))
        ctk.CTkLabel(card, text="DentalPhoto",
                     font=FONT_LOGO, text_color=C["chiaro"]).grid(
            row=1, column=0, pady=(0, 4))
        ctk.CTkLabel(card, text="Archivio Fotografie Cliniche",
                     font=FONT_SUB, text_color=C["grigio"]).grid(
            row=2, column=0, pady=(0, 32))

        # Username
        ctk.CTkLabel(card, text="Username", font=FONT_LABEL,
                     text_color=C["grigio"], anchor="w").grid(
            row=3, column=0, padx=40, pady=(0, 4), sticky="w")
        self._entry_user = ctk.CTkEntry(
            card, font=FONT_INPUT, height=44,
            fg_color=C["input_bg"],
            border_color=C["border"],
            placeholder_text="Inserisci username…")
        self._entry_user.grid(row=4, column=0, padx=40, pady=(0, 16), sticky="ew")
        self._entry_user.focus_set()

        # Password
        ctk.CTkLabel(card, text="Password", font=FONT_LABEL,
                     text_color=C["grigio"], anchor="w").grid(
            row=5, column=0, padx=40, pady=(0, 4), sticky="w")

        pwd_frame = ctk.CTkFrame(card, fg_color="transparent")
        pwd_frame.grid(row=6, column=0, padx=40, pady=(0, 8), sticky="ew")
        pwd_frame.grid_columnconfigure(0, weight=1)

        self._entry_pwd = ctk.CTkEntry(
            pwd_frame, font=FONT_INPUT, height=44,
            fg_color=C["input_bg"],
            border_color=C["border"],
            show="●",
            placeholder_text="Password…")
        self._entry_pwd.grid(row=0, column=0, sticky="ew", padx=(0, 6))

        self._pwd_visible = False
        self._btn_eye = ctk.CTkButton(
            pwd_frame, text="👁", width=44, height=44,
            font=("Segoe UI", 16),
            fg_color=C["input_bg"], hover_color=C["border"],
            command=self._toggle_pwd)
        self._btn_eye.grid(row=0, column=1)

        # Messaggio errore
        self._lbl_err = ctk.CTkLabel(
            card, text="", font=FONT_LABEL,
            text_color=C["error"], wraplength=340)
        self._lbl_err.grid(row=7, column=0, padx=40, pady=(0, 4))

        # Pulsante login
        self._btn_login = ctk.CTkButton(
            card,
            text="Accedi",
            font=FONT_BTN, height=48,
            fg_color=C["accent_br"], hover_color="#c73652",
            corner_radius=10,
            command=self._login,
        )
        self._btn_login.grid(row=8, column=0, padx=40, pady=(8, 0), sticky="ew")

        # Hint credenziali default (primo avvio)
        self._lbl_hint = ctk.CTkLabel(
            card,
            text="Primo accesso: admin / admin1234",
            font=("Segoe UI", 9),
            text_color=C["grigio"])
        self._lbl_hint.grid(row=9, column=0, pady=(12, 36))

    # ------------------------------------------------------------------

    def _toggle_pwd(self):
        self._pwd_visible = not self._pwd_visible
        self._entry_pwd.configure(show="" if self._pwd_visible else "●")
        self._btn_eye.configure(text="🙈" if self._pwd_visible else "👁")

    def _login(self):
        username = self._entry_user.get().strip()
        password = self._entry_pwd.get()

        if not username or not password:
            self._set_errore("Inserisci username e password.")
            return

        # Disabilita pulsante durante la verifica
        self._btn_login.configure(state="disabled", text="Verifica…")
        self.update()

        ok, msg = auth.verifica_login(username, password)

        if ok:
            self.login_riuscito = True
            self._lbl_err.configure(
                text=f"✅  Benvenuto, {SessioneUtente.nome_display()}!",
                text_color=C["verde"])
            self.after(400, self.destroy)
        else:
            self._tentativi += 1
            self._btn_login.configure(state="normal", text="Accedi")
            self._set_errore(f"❌  {msg}")
            self._entry_pwd.delete(0, "end")

            # Blocco temporaneo dopo 5 tentativi falliti
            if self._tentativi >= 5:
                self._btn_login.configure(state="disabled", text="⏳ Attendi 10s…")
                self.after(10_000, self._sblocca_btn)

    def _set_errore(self, msg: str):
        self._lbl_err.configure(text=msg, text_color=C["error"])

    def _sblocca_btn(self):
        self._tentativi = 0
        self._btn_login.configure(state="normal", text="Accedi")


# ===========================================================================
# SCHERMATA LOCK (inattività)
# ===========================================================================

class LockScreen(ctk.CTkToplevel):
    """
    Overlay modale che blocca la UI principale dopo inattività.
    L'utente deve reinserire la password per sbloccare.
    """

    def __init__(self, master, on_sblocco):
        super().__init__(master)
        self._on_sblocco = on_sblocco
        self.title("DentalPhoto — Sessione bloccata")
        self.geometry("400x380")
        self.resizable(False, False)
        self.configure(fg_color=C["bg"])
        self.attributes("-topmost", True)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", lambda: None)  # non chiudibile con X
        self._build_ui()
        self.bind("<Return>", lambda e: self._sblocca())

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        card = ctk.CTkFrame(self, fg_color=C["card"], corner_radius=16,
                            border_width=1, border_color=C["border"])
        card.grid(row=0, column=0, padx=24, pady=24, sticky="nsew")
        card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(card, text="🔒", font=("Segoe UI", 40)).grid(
            row=0, column=0, pady=(28, 6))
        ctk.CTkLabel(card, text="Sessione bloccata",
                     font=("Segoe UI", 16, "bold"),
                     text_color=C["chiaro"]).grid(row=1, column=0, pady=(0, 4))
        ctk.CTkLabel(card,
                     text=f"Utente: {SessioneUtente.nome_display()}",
                     font=FONT_LABEL, text_color=C["grigio"]).grid(
            row=2, column=0, pady=(0, 20))

        self._entry_pwd = ctk.CTkEntry(
            card, font=FONT_INPUT, height=42,
            fg_color=C["input_bg"], border_color=C["border"],
            show="●", placeholder_text="Reinserisci la password…")
        self._entry_pwd.grid(row=3, column=0, padx=28, pady=(0, 8), sticky="ew")
        self._entry_pwd.focus_set()

        self._lbl_err = ctk.CTkLabel(card, text="", font=FONT_LABEL,
                                      text_color=C["error"])
        self._lbl_err.grid(row=4, column=0, pady=(0, 8))

        ctk.CTkButton(card, text="🔓  Sblocca",
                      font=FONT_BTN, height=44,
                      fg_color=C["accent"], hover_color="#1a4a7a",
                      command=self._sblocca).grid(
            row=5, column=0, padx=28, pady=(0, 12), sticky="ew")

        ctk.CTkButton(card, text="Logout",
                      font=FONT_LABEL, height=34,
                      fg_color="transparent", border_width=1,
                      text_color=C["grigio"],
                      command=self._logout).grid(
            row=6, column=0, padx=28, pady=(0, 24), sticky="ew")

    def _sblocca(self):
        pwd = self._entry_pwd.get()
        username = SessioneUtente.corrente["username"]
        ok, msg  = auth.verifica_login(username, pwd)
        if ok:
            self.destroy()
            if self._on_sblocco:
                self._on_sblocco()
        else:
            self._lbl_err.configure(text=f"❌  {msg}")
            self._entry_pwd.delete(0, "end")

    def _logout(self):
        SessioneUtente.logout()
        self.destroy()
        if self._on_sblocco:
            self._on_sblocco(logout=True)


# ===========================================================================
# FRAME: GESTIONE UTENTI (solo admin)
# ===========================================================================

class GestioneUtentiFrame(ctk.CTkFrame):
    """
    Pannello di amministrazione utenti.
    Visibile solo agli utenti con ruolo 'admin'.
    """

    def __init__(self, master, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self._utente_sel: Optional[int] = None
        self._build_ui()
        self.aggiorna()

    # ------------------------------------------------------------------

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=2)
        self.grid_columnconfigure(1, weight=3)
        self.grid_rowconfigure(0, weight=1)

        # ── Colonna sinistra: lista utenti ────────────────────────────
        lcard = ctk.CTkFrame(self, fg_color=CU["card"], corner_radius=12)
        lcard.grid(row=0, column=0, padx=(0, 8), sticky="nsew")
        lcard.grid_columnconfigure(0, weight=1)
        lcard.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(lcard, text="👥  Utenti", font=FONT_SEZ).grid(
            row=0, column=0, padx=16, pady=(16, 8), sticky="w")

        self._lista = ctk.CTkScrollableFrame(lcard, fg_color="transparent")
        self._lista.grid(row=1, column=0, padx=8, pady=(0, 8), sticky="nsew")
        self._lista.grid_columnconfigure(0, weight=1)

        ctk.CTkButton(lcard, text="➕  Nuovo Utente",
                      font=FONT_NRM, height=38,
                      fg_color=CU["verde"], hover_color="#388e3c",
                      command=self._nuovo_utente).grid(
            row=2, column=0, padx=12, pady=(0, 14), sticky="ew")

        # ── Colonna destra: editor + log ──────────────────────────────
        rcard = ctk.CTkFrame(self, fg_color="transparent")
        rcard.grid(row=0, column=1, padx=(8, 0), sticky="nsew")
        rcard.grid_columnconfigure(0, weight=1)
        rcard.grid_rowconfigure(0, weight=2)
        rcard.grid_rowconfigure(1, weight=1)

        # Editor
        self._editor = ctk.CTkFrame(rcard, fg_color=CU["card"], corner_radius=12)
        self._editor.grid(row=0, column=0, pady=(0, 8), sticky="nsew")
        self._editor.grid_columnconfigure(0, weight=1)
        self._build_editor()

        # Log accessi
        log_card = ctk.CTkFrame(rcard, fg_color=CU["card"], corner_radius=12)
        log_card.grid(row=1, column=0, sticky="nsew")
        log_card.grid_columnconfigure(0, weight=1)
        log_card.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(log_card, text="📋  Log Accessi (ultimi 50)",
                     font=FONT_SEZ).grid(row=0, column=0, padx=16, pady=(14, 6), sticky="w")

        self._txt_log = ctk.CTkTextbox(log_card, font=FONT_MONO, height=130,
                                        fg_color=CU["entry_bg"])
        self._txt_log.grid(row=1, column=0, padx=12, pady=(0, 14), sticky="nsew")
        self._txt_log.configure(state="disabled")

        ctk.CTkButton(log_card, text="🔄  Aggiorna Log",
                      font=FONT_SML, height=30, width=140,
                      fg_color=CU["accent"],
                      command=self._aggiorna_log).grid(
            row=2, column=0, padx=12, pady=(0, 12), sticky="e")

    def _build_editor(self):
        p = self._editor

        ctk.CTkLabel(p, text="✏️  Modifica Utente",
                     font=FONT_SEZ, text_color=CU["accent"]).grid(
            row=0, column=0, columnspan=2, padx=16, pady=(16, 4), sticky="w")

        self._lbl_editor_info = ctk.CTkLabel(
            p, text="Seleziona un utente dalla lista.",
            font=FONT_SML, text_color=CU["grigio"])
        self._lbl_editor_info.grid(row=1, column=0, columnspan=2,
                                    padx=16, pady=(0, 12), sticky="w")

        ctk.CTkFrame(p, height=1, fg_color=CU["divider"]).grid(
            row=2, column=0, columnspan=2, padx=16, pady=(0, 12), sticky="ew")

        # Nome display
        ctk.CTkLabel(p, text="Nome visualizzato", font=FONT_SML,
                     text_color=CU["grigio"]).grid(row=3, column=0, padx=16, pady=(0,2), sticky="w")
        self._e_nome = ctk.CTkEntry(p, font=FONT_NRM, height=36,
                                     fg_color=CU["entry_bg"])
        self._e_nome.grid(row=4, column=0, columnspan=2, padx=16, pady=(0, 10), sticky="ew")

        # Ruolo
        ctk.CTkLabel(p, text="Ruolo", font=FONT_SML,
                     text_color=CU["grigio"]).grid(row=5, column=0, padx=16, pady=(0,2), sticky="w")
        self._combo_ruolo = ctk.CTkComboBox(p, values=RUOLI,
                                             font=FONT_NRM, height=36,
                                             fg_color=CU["entry_bg"],
                                             state="readonly")
        self._combo_ruolo.set(RUOLI[1])
        self._combo_ruolo.grid(row=6, column=0, columnspan=2, padx=16, pady=(0, 10), sticky="ew")

        # Pulsanti attiva/disattiva + elimina
        btn_row = ctk.CTkFrame(p, fg_color="transparent")
        btn_row.grid(row=7, column=0, columnspan=2, padx=16, pady=(0, 10), sticky="ew")
        btn_row.grid_columnconfigure((0, 1), weight=1)

        self._btn_salva_mod = ctk.CTkButton(
            btn_row, text="💾  Salva",
            font=FONT_NRM, height=38,
            fg_color=CU["verde"], hover_color="#388e3c",
            state="disabled",
            command=self._salva_modifica)
        self._btn_salva_mod.grid(row=0, column=0, padx=(0, 4), sticky="ew")

        self._btn_toggle = ctk.CTkButton(
            btn_row, text="🔴  Disattiva",
            font=FONT_NRM, height=38,
            fg_color=CU["arancio"], hover_color="#e65100",
            state="disabled",
            command=self._toggle_attivo)
        self._btn_toggle.grid(row=0, column=1, padx=(4, 0), sticky="ew")

        ctk.CTkFrame(p, height=1, fg_color=CU["divider"]).grid(
            row=8, column=0, columnspan=2, padx=16, pady=(4, 10), sticky="ew")

        # Cambio password
        ctk.CTkLabel(p, text="Nuova Password", font=FONT_SML,
                     text_color=CU["grigio"]).grid(row=9, column=0, padx=16, pady=(0,2), sticky="w")

        pwd_row = ctk.CTkFrame(p, fg_color="transparent")
        pwd_row.grid(row=10, column=0, columnspan=2, padx=16, pady=(0, 10), sticky="ew")
        pwd_row.grid_columnconfigure(0, weight=1)

        self._e_pwd = ctk.CTkEntry(pwd_row, font=FONT_NRM, height=36,
                                    fg_color=CU["entry_bg"], show="●",
                                    placeholder_text="Lascia vuoto per non cambiare")
        self._e_pwd.grid(row=0, column=0, sticky="ew", padx=(0, 6))

        ctk.CTkButton(pwd_row, text="🔑  Cambia",
                      font=FONT_SML, width=90, height=36,
                      fg_color=CU["accent"],
                      state="normal",
                      command=self._cambia_password).grid(row=0, column=1)

        self._btn_elimina = ctk.CTkButton(
            p, text="🗑  Elimina Utente",
            font=FONT_SML, height=34,
            fg_color="transparent", border_width=1,
            border_color=CU["red"], text_color=CU["red"],
            hover_color="#3a0a0a",
            state="disabled",
            command=self._elimina)
        self._btn_elimina.grid(row=11, column=0, columnspan=2,
                                padx=16, pady=(0, 16), sticky="ew")

        self._lbl_op_stato = ctk.CTkLabel(p, text="", font=FONT_SML,
                                           text_color=CU["verde"])
        self._lbl_op_stato.grid(row=12, column=0, columnspan=2, pady=(0, 10))

    # ------------------------------------------------------------------

    def aggiorna(self):
        self._aggiorna_lista()
        self._aggiorna_log()

    def _aggiorna_lista(self):
        for w in self._lista.winfo_children():
            w.destroy()
        for uid_row in auth.get_tutti_utenti():
            self._riga_utente(uid_row)

    def _riga_utente(self, r):
        attivo = bool(r["attivo"])
        col_bg = CU["entry_bg"] if attivo else "#1a1a1a"
        riga = ctk.CTkFrame(self._lista, fg_color=col_bg, corner_radius=8)
        riga.grid(row=r["id"], column=0, padx=4, pady=2, sticky="ew")
        riga.grid_columnconfigure(1, weight=1)

        # Iniziale avatar
        ctk.CTkLabel(riga,
                     text=(r["nome_display"] or r["username"])[0].upper(),
                     font=("Segoe UI", 13, "bold"),
                     width=34, height=34,
                     fg_color=CU["accent"] if attivo else CU["grigio"],
                     corner_radius=17,
                     text_color="white").grid(row=0, column=0, rowspan=2,
                                              padx=(8, 8), pady=6)

        ctk.CTkLabel(riga, text=r["nome_display"] or r["username"],
                     font=FONT_SML, anchor="w").grid(row=0, column=1, sticky="ew")

        ruolo_col = CU["accent"] if r["ruolo"] == "admin" else CU["grigio"]
        ctk.CTkLabel(riga, text=f"{'🔑' if r['ruolo']=='admin' else '👤'} {r['ruolo']}",
                     font=("Segoe UI", 9),
                     text_color=ruolo_col, anchor="w").grid(row=1, column=1, sticky="ew")

        stato_txt = "attivo" if attivo else "disattivato"
        ctk.CTkLabel(riga, text=f"● {stato_txt}",
                     font=("Segoe UI", 8),
                     text_color=CU["verde"] if attivo else CU["red"]).grid(
            row=0, column=2, rowspan=2, padx=(0, 8))

        for w in (riga,):
            w.bind("<Button-1>", lambda e, rid=r["id"]: self._seleziona(rid))
            w.bind("<Enter>", lambda e, f=riga: f.configure(fg_color=CU["accent"]))
            w.bind("<Leave>", lambda e, f=riga, bg=col_bg: f.configure(fg_color=bg))

    def _seleziona(self, uid: int):
        self._utente_sel = uid
        righe = auth.get_tutti_utenti()
        r = next((x for x in righe if x["id"] == uid), None)
        if r is None:
            return

        self._e_nome.delete(0, "end")
        self._e_nome.insert(0, r["nome_display"] or "")
        self._combo_ruolo.set(r["ruolo"])

        self._lbl_editor_info.configure(
            text=f"@{r['username']}  |  Ultimo login: {r['ultimo_login'] or '—'}",
            text_color=CU["chiaro"])

        attivo = bool(r["attivo"])
        self._btn_toggle.configure(
            text="🔴  Disattiva" if attivo else "🟢  Riattiva",
            fg_color=CU["arancio"] if attivo else CU["verde"])

        for b in (self._btn_salva_mod, self._btn_toggle, self._btn_elimina):
            b.configure(state="normal")

        self._e_pwd.delete(0, "end")
        self._lbl_op_stato.configure(text="")

    def _salva_modifica(self):
        if self._utente_sel is None:
            return
        try:
            auth.aggiorna_utente(
                self._utente_sel,
                nome_display=self._e_nome.get(),
                ruolo=self._combo_ruolo.get(),
            )
            self._lbl_op_stato.configure(
                text="✅  Salvato.", text_color=CU["verde"])
            self._aggiorna_lista()
        except ValueError as e:
            self._lbl_op_stato.configure(text=f"❌  {e}", text_color=CU["red"])

    def _toggle_attivo(self):
        if self._utente_sel is None:
            return
        righe = auth.get_tutti_utenti()
        r = next((x for x in righe if x["id"] == self._utente_sel), None)
        if r:
            auth.aggiorna_utente(self._utente_sel, attivo=not bool(r["attivo"]))
            self._aggiorna_lista()
            self._seleziona(self._utente_sel)

    def _cambia_password(self):
        if self._utente_sel is None:
            messagebox.showwarning("Nessun utente", "Seleziona prima un utente.", parent=self)
            return
        pwd = self._e_pwd.get().strip()
        if not pwd:
            messagebox.showwarning("Password vuota",
                                   "Inserisci la nuova password.", parent=self)
            return
        if len(pwd) < 6:
            messagebox.showwarning("Password troppo corta",
                                   "Minimo 6 caratteri.", parent=self)
            return
        auth.cambia_password(self._utente_sel, pwd)
        self._e_pwd.delete(0, "end")
        self._lbl_op_stato.configure(text="✅  Password aggiornata.", text_color=CU["verde"])

    def _elimina(self):
        if self._utente_sel is None:
            return
        righe = auth.get_tutti_utenti()
        r = next((x for x in righe if x["id"] == self._utente_sel), None)
        nome  = r["nome_display"] or r["username"] if r else "?"
        if not messagebox.askyesno("Elimina utente",
                                    f"Eliminare l'utente «{nome}»?\n"
                                    "Questa azione è irreversibile.",
                                    icon="warning", default=messagebox.NO,
                                    parent=self):
            return
        try:
            auth.elimina_utente(self._utente_sel)
            self._utente_sel = None
            self._lbl_op_stato.configure(text="")
            self._aggiorna_lista()
        except ValueError as e:
            messagebox.showerror("Errore", str(e), parent=self)

    def _nuovo_utente(self):
        NuovoUtenteDialog(self, on_creato=self._aggiorna_lista)

    def _aggiorna_log(self):
        log = auth.get_log_accessi(50)
        self._txt_log.configure(state="normal")
        self._txt_log.delete("1.0", "end")
        for r in log:
            icona = "✅" if r["esito"] == "ok" else "❌"
            ts = r["timestamp"][:16] if r["timestamp"] else "—"
            self._txt_log.insert("end",
                f"{icona}  {ts}  @{r['username'] or '—'}  [{r['esito']}]  {r['ip_host'] or ''}\n")
        self._txt_log.configure(state="disabled")


# ===========================================================================
# DIALOG: Nuovo Utente
# ===========================================================================

class NuovoUtenteDialog(ctk.CTkToplevel):
    def __init__(self, master, on_creato=None):
        super().__init__(master)
        self.title("Nuovo Utente")
        self.geometry("400x380")
        self.resizable(False, False)
        self.grab_set()
        self._on_creato = on_creato
        self.after(50, lambda: (self.lift(), self.focus_force(),
                                self.attributes("-topmost", True),
                                self.after(200, lambda: self.attributes("-topmost", False))))
        self._build_ui()

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(self, text="Crea Nuovo Utente", font=FONT_SEZ).grid(
            row=0, column=0, padx=24, pady=(20, 16), sticky="w")

        for row, (lbl, attr, show) in enumerate([
            ("Username",        "_e_user", ""),
            ("Nome Visualizzato","_e_nome",""),
            ("Password",        "_e_pwd",  "●"),
        ]):
            ctk.CTkLabel(self, text=lbl, font=FONT_SML,
                         text_color=CU["grigio"]).grid(
                row=row*2+1, column=0, padx=24, pady=(0, 2), sticky="w")
            e = ctk.CTkEntry(self, font=FONT_NRM, height=38,
                             fg_color=CU["entry_bg"],
                             show=show)
            e.grid(row=row*2+2, column=0, padx=24, pady=(0, 10), sticky="ew")
            setattr(self, attr, e)

        ctk.CTkLabel(self, text="Ruolo", font=FONT_SML,
                     text_color=CU["grigio"]).grid(
            row=7, column=0, padx=24, pady=(0, 2), sticky="w")
        self._combo = ctk.CTkComboBox(self, values=RUOLI,
                                      font=FONT_NRM, height=38,
                                      fg_color=CU["entry_bg"], state="readonly")
        self._combo.set(RUOLI[1])
        self._combo.grid(row=8, column=0, padx=24, pady=(0, 14), sticky="ew")

        self._lbl_err = ctk.CTkLabel(self, text="", font=FONT_SML,
                                      text_color=CU["red"])
        self._lbl_err.grid(row=9, column=0, padx=24, pady=(0, 4))

        ctk.CTkButton(self, text="➕  Crea Utente",
                      font=FONT_BTN, height=44,
                      fg_color=CU["verde"], hover_color="#388e3c",
                      command=self._crea).grid(
            row=10, column=0, padx=24, pady=(0, 20), sticky="ew")

    def _crea(self):
        username = self._e_user.get().strip()
        nome     = self._e_nome.get().strip()
        pwd      = self._e_pwd.get().strip()
        ruolo    = self._combo.get()

        if not username or not pwd:
            self._lbl_err.configure(text="Username e password obbligatori.")
            return
        if len(pwd) < 6:
            self._lbl_err.configure(text="Password: minimo 6 caratteri.")
            return
        try:
            auth.crea_utente(username, pwd, nome, ruolo)
            if self._on_creato:
                self._on_creato()
            self.destroy()
        except ValueError as e:
            self._lbl_err.configure(text=str(e))


__all__ = ["LoginScreen", "LockScreen", "GestioneUtentiFrame"]

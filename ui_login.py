"""
ui_login.py  — Restyle v2
==========================
Schermata di login ridisegnata con layout split-panel.

  LoginScreen      → finestra standalone, layout a due colonne
  LockScreen       → overlay sessione bloccata (aggiornato)
  GestioneUtentiFrame / NuovoUtenteDialog  → invariati, colori aggiornati
"""

import tkinter as tk
from tkinter import messagebox
import customtkinter as ctk
from typing import Optional
import threading
from ui_network import NetworkSettingsScreen

import auth
from auth import SessioneUtente, RUOLI

# ---------------------------------------------------------------------------
# Design tokens
# ---------------------------------------------------------------------------

T = {
    "bg_app":       "#080c18",
    "bg_panel_l":   "#0b1628",
    "bg_panel_r":   "#080c18",
    "bg_card":      "#0f1a2e",
    "bg_input":     "#111827",
    "txt_primary":  "#e2e8f0",
    "txt_secondary":"#64748b",
    "txt_hint":     "#334155",
    "txt_white":    "#ffffff",
    "accent":       "#2563eb",
    "accent_h":     "#1d4ed8",
    "accent_br":    "#e94560",
    "verde":        "#10b981",
    "arancio":      "#f59e0b",
    "border":       "#1e3a5f",
    "border_light": "#1e2d4a",
    "error":        "#f87171",
    "success":      "#34d399",
}

FL = {
    "brand":  ("Segoe UI", 26, "bold"),
    "title":  ("Segoe UI", 20, "bold"),
    "sub":    ("Segoe UI", 11),
    "label":  ("Segoe UI", 10),
    "input":  ("Segoe UI", 13),
    "btn":    ("Segoe UI", 13, "bold"),
    "small":  ("Segoe UI", 9),
    "badge":  ("Segoe UI", 8, "bold"),
    "mono":   ("Consolas", 9),
}

CU = {
    "card":     "#0f1629",
    "entry_bg": "#0d1117",
    "accent":   "#0f3460",
    "red":      "#e94560",
    "verde":    "#10b981",
    "grigio":   "#64748b",
    "chiaro":   "#e2e8f0",
    "arancio":  "#f59e0b",
    "divider":  "#1e2d4a",
}

FONT_SEZ  = ("Segoe UI", 13, "bold")
FONT_NRM  = ("Segoe UI", 12)
FONT_SML  = ("Segoe UI", 10)
FONT_MONO = ("Consolas", 9)


def _input(parent, placeholder="", show="", height=44):
    return ctk.CTkEntry(
        parent,
        font=FL["input"], height=height,
        placeholder_text=placeholder,
        placeholder_text_color=T["txt_hint"],
        fg_color=T["bg_input"],
        border_color=T["border"],
        border_width=1, corner_radius=8,
        text_color=T["txt_primary"],
        show=show,
    )


# ===========================================================================
# LOGIN SCREEN
# ===========================================================================

class LoginScreen(ctk.CTk):

    _DOTS = ["", "●", "●●", "●●●"]

    def __init__(self):
        super().__init__()
        self.login_riuscito = False
        self.title("DentalPhoto — Accesso")
        self.configure(fg_color=T["bg_app"])
        self.resizable(False, False)
        W, H = 820, 600
        self.update_idletasks()
        x = (self.winfo_screenwidth()  - W) // 2
        y = (self.winfo_screenheight() - H) // 2
        self.geometry(f"{W}x{H}+{x}+{y}")
        self._tentativi  = 0
        self._anim_id    = None
        self._anim_step  = 0
        self._shake_jobs = []
        self._build_ui()
        self.bind("<Return>", lambda e: self._login())
        self.after(100, self._entry_user.focus_set)
        

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=0, minsize=290)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self._build_left()
        self._build_right()

    def _build_left(self):
        lp = ctk.CTkFrame(self, fg_color=T["bg_panel_l"], corner_radius=0, width=290)
        lp.grid(row=0, column=0, sticky="nsew")
        lp.grid_propagate(False)
        lp.grid_columnconfigure(0, weight=1)
        lp.grid_rowconfigure(4, weight=1)

        cvs = tk.Canvas(lp, width=290, height=110,
                        bg=T["bg_panel_l"], highlightthickness=0)
        cvs.grid(row=0, column=0, sticky="ew")
        for cx, cy, r, col in [(260,20,80,T["accent"]),(30,90,60,T["border"]),
                                (180,100,40,T["bg_card"]),(290,80,55,T["accent_br"]),
                                (100,15,35,T["border"])]:
            cvs.create_oval(cx-r, cy-r, cx+r, cy+r, fill=col, outline="")
        cvs.create_line(0, 109, 290, 109, fill=T["border"], width=1)

        ctk.CTkLabel(lp, text="🦷", font=("Segoe UI", 48),
                     fg_color="transparent").grid(row=1, column=0, pady=(0,6))
        ctk.CTkLabel(lp, text="DentalPhoto", font=FL["brand"],
                     text_color=T["txt_white"], fg_color="transparent").grid(row=2, column=0)
        ctk.CTkLabel(lp, text="Archivio fotografico clinico",
                     font=FL["sub"], text_color=T["txt_secondary"],
                     fg_color="transparent").grid(row=3, column=0, pady=(4,0))

        ver = ctk.CTkFrame(lp, fg_color=T["bg_card"], corner_radius=6)
        ver.grid(row=5, column=0, padx=20, pady=20, sticky="ew")
        ctk.CTkLabel(ver, text="v3.0  •  DentalPhoto", font=FL["small"],
                     text_color=T["txt_hint"], fg_color="transparent").pack(pady=6)

    def _build_right(self):
        rp = ctk.CTkFrame(self, fg_color=T["bg_panel_r"], corner_radius=0)
        rp.grid(row=0, column=1, sticky="nsew")
        rp.grid_columnconfigure(0, weight=1)
        rp.grid_rowconfigure(0, weight=1)

        inner = ctk.CTkFrame(rp, fg_color="transparent")
        inner.grid(row=0, column=0, padx=50, pady=40, sticky="nsew")
        inner.grid_columnconfigure(0, weight=1)
        self._inner = inner

        ctk.CTkLabel(inner, text="Bentornato", font=FL["title"],
                     text_color=T["txt_primary"], anchor="w").grid(
            row=0, column=0, sticky="w")
        ctk.CTkLabel(inner, text="Inserisci le tue credenziali per accedere",
                     font=FL["sub"], text_color=T["txt_secondary"], anchor="w").grid(
            row=1, column=0, sticky="w", pady=(2,24))

        # Username
        ctk.CTkLabel(inner, text="USERNAME", font=FL["badge"],
                     text_color=T["txt_secondary"], anchor="w").grid(
            row=2, column=0, sticky="w", pady=(0,4))
        self._entry_user = _input(inner, placeholder="es. admin")
        self._entry_user.grid(row=3, column=0, sticky="ew", pady=(0,16))

        # Password
        ctk.CTkLabel(inner, text="PASSWORD", font=FL["badge"],
                     text_color=T["txt_secondary"], anchor="w").grid(
            row=4, column=0, sticky="w", pady=(0,4))
        pr = ctk.CTkFrame(inner, fg_color="transparent")
        pr.grid(row=5, column=0, sticky="ew", pady=(0,8))
        pr.grid_columnconfigure(0, weight=1)
        self._entry_pwd = _input(pr, placeholder="●●●●●●●●", show="●")
        self._entry_pwd.grid(row=0, column=0, sticky="ew", padx=(0,6))
        self._pwd_visible = False
        self._btn_eye = ctk.CTkButton(
            pr, text="👁", width=44, height=44, font=("Segoe UI", 16),
            fg_color=T["bg_input"], hover_color=T["border"],
            border_width=1, border_color=T["border"], corner_radius=8,
            command=self._toggle_pwd)
        self._btn_eye.grid(row=0, column=1)

        # Errore
        self._lbl_err = ctk.CTkLabel(inner, text="", font=FL["label"],
                                      text_color=T["error"], wraplength=360, anchor="w")
        self._lbl_err.grid(row=6, column=0, sticky="w", pady=(0,12))

        # Pulsante
        self._btn_login = ctk.CTkButton(
            inner, text="Accedi", font=FL["btn"], height=48,
            fg_color=T["accent"], hover_color=T["accent_h"],
            corner_radius=10, command=self._login)
        self._btn_login.grid(row=7, column=0, sticky="ew")

        # Hint
        hint = ctk.CTkFrame(inner, fg_color=T["bg_card"], corner_radius=8,
                             border_width=1, border_color=T["border"])
        hint.grid(row=8, column=0, sticky="ew", pady=(20,0))
        ctk.CTkLabel(hint, text="💡  Primo accesso  →  admin / admin1234",
                     font=FL["small"], text_color=T["txt_secondary"],
                     fg_color="transparent").pack(pady=8, padx=12, anchor="w")
        # Hint (Codice già presente)
        hint = ctk.CTkFrame(inner, fg_color=T["bg_card"], corner_radius=8,
                             border_width=1, border_color=T["border"])
        hint.grid(row=8, column=0, sticky="ew", pady=(20,0))
        ctk.CTkLabel(hint, text="💡  Primo accesso  →  admin / admin1234",
                     font=FL["small"], text_color=T["txt_secondary"],
                     fg_color="transparent").pack(pady=8, padx=12, anchor="w")

        # --------------------------------------------------------
        # INCOLLA QUESTO (Nuovo Bottone Rete)
        # --------------------------------------------------------
        self.btn_rete = ctk.CTkButton(
            inner, 
            text="⚙️ Impostazioni Rete", 
            font=FL["btn"], 
            height=40,
            fg_color="transparent", 
            border_width=1,
            border_color=T["border"],
            text_color=T["txt_secondary"],
            hover_color=T["bg_panel_l"],
            command=lambda: NetworkSettingsScreen(self)
        )
        self.btn_rete.grid(row=9, column=0, sticky="ew", pady=(15,0))

    def _toggle_pwd(self):
        self._pwd_visible = not self._pwd_visible
        self._entry_pwd.configure(show="" if self._pwd_visible else "●")
        self._btn_eye.configure(text="🙈" if self._pwd_visible else "👁")

    def _login(self):
        username = self._entry_user.get().strip()
        password = self._entry_pwd.get()
        if not username or not password:
            self._mostra_errore("Inserisci username e password.")
            return
        self._btn_login.configure(state="disabled")
        self._lbl_err.configure(text="")
        self._avvia_anim()

        def _esegui():
            ok, msg = auth.verifica_login(username, password)
            self.after(0, lambda: self._on_result(ok, msg))

        threading.Thread(target=_esegui, daemon=True).start()

    def _on_result(self, ok, msg):
        self._ferma_anim()
        if ok:
            if SessioneUtente.corrente["richiede_cambio"]:
                self._mostra_cambio_obbligatorio()
                return
        if ok:
            self._btn_login.configure(text="✓  Accesso effettuato",
                                       fg_color=T["verde"], state="disabled")
            self.login_riuscito = True
            self.after(500, self.destroy)
        else:
            self._tentativi += 1
            self._btn_login.configure(state="normal", text="Accedi")
            self._mostra_errore(msg)
            self._entry_pwd.delete(0, "end")
            self._shake()
            if self._tentativi >= 5:
                self._btn_login.configure(state="disabled",
                                           text="⏳  Attendi 10s…",
                                           fg_color=T["arancio"])
                self.after(10_000, self._sblocca_btn)

    def _mostra_errore(self, msg):
        self._lbl_err.configure(text=f"⚠  {msg}")

    def _sblocca_btn(self):
        self._tentativi = 0
        self._btn_login.configure(state="normal", text="Accedi",
                                   fg_color=T["accent"])

    def _avvia_anim(self):
        self._anim_step = 0
        self._cicla_anim()

    def _cicla_anim(self):
        dots = self._DOTS[self._anim_step % len(self._DOTS)]
        self._btn_login.configure(text=f"Verifica{dots}")
        self._anim_step += 1
        self._anim_id = self.after(300, self._cicla_anim)

    def _ferma_anim(self):
        if self._anim_id:
            self.after_cancel(self._anim_id)
            self._anim_id = None

    def _shake(self):
        for j in self._shake_jobs:
            try:
                self.after_cancel(j)
            except Exception:
                pass
        self._shake_jobs.clear()
        base = 50
        for i, dx in enumerate([6, -6, 4, -4, 2, -2, 0]):
            jid = self.after(i * 40,
                             lambda d=dx: self._inner.grid_configure(padx=base+d))
            self._shake_jobs.append(jid)
    def _mostra_cambio_obbligatorio(self):
            nuova_pwd = ctk.CTkInputDialog(text="Al primo accesso è obbligatorio cambiare la password.\nMinimo 6 caratteri:", title="Sicurezza").get_input()
            if nuova_pwd and len(nuova_pwd) >= 6:
                import auth
                auth.cambia_password(SessioneUtente.corrente["id"], nuova_pwd)
                with auth.db.get_connection() as conn:
                    conn.execute("UPDATE utenti SET richiede_cambio = 0 WHERE id = ?", (SessioneUtente.corrente["id"],))
                self.login_riuscito = True
                self.destroy()
            else:
                self._mostra_errore("Password troppo corta. Riprova.")
                self._btn_login.configure(state="normal", text="Accedi")

# ===========================================================================
# LOCK SCREEN
# ===========================================================================

class LockScreen(ctk.CTkToplevel):

    def __init__(self, master, on_sblocco):
        super().__init__(master)
        self._on_sblocco = on_sblocco
        self.title("DentalPhoto — Sessione bloccata")
        self.configure(fg_color=T["bg_app"])
        self.resizable(False, False)
        self.attributes("-topmost", True)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", lambda: None)
        W, H = 400, 410
        self.geometry(f"{W}x{H}")
        self.update_idletasks()
        x = master.winfo_x() + (master.winfo_width()  - W) // 2
        y = master.winfo_y() + (master.winfo_height() - H) // 2
        self.geometry(f"{W}x{H}+{x}+{y}")
        self._build_ui()
        self.bind("<Return>", lambda e: self._sblocca())
        self.after(100, self._entry_pwd.focus_set)

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        card = ctk.CTkFrame(self, fg_color=T["bg_card"], corner_radius=16,
                             border_width=1, border_color=T["border"])
        card.grid(row=0, column=0, padx=28, pady=28, sticky="nsew")
        card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(card, text="🔒", font=("Segoe UI", 44),
                     fg_color="transparent").grid(row=0, column=0, pady=(28,8))
        ctk.CTkLabel(card, text="Sessione bloccata",
                     font=("Segoe UI", 17, "bold"),
                     text_color=T["txt_primary"],
                     fg_color="transparent").grid(row=1, column=0)
        ctk.CTkLabel(card, text=f"Utente: {SessioneUtente.nome_display()}",
                     font=FL["sub"], text_color=T["txt_secondary"],
                     fg_color="transparent").grid(row=2, column=0, pady=(4,20))

        self._entry_pwd = _input(card, placeholder="Reinserisci la password…", show="●")
        self._entry_pwd.grid(row=3, column=0, padx=24, sticky="ew")

        self._lbl_err = ctk.CTkLabel(card, text="", font=FL["label"],
                                      text_color=T["error"], fg_color="transparent")
        self._lbl_err.grid(row=4, column=0, pady=(6,4))

        ctk.CTkButton(card, text="🔓  Sblocca", font=FL["btn"], height=44,
                      fg_color=T["accent"], hover_color=T["accent_h"],
                      corner_radius=10, command=self._sblocca).grid(
            row=5, column=0, padx=24, pady=(8,8), sticky="ew")

        ctk.CTkButton(card, text="Logout e ritorna al login",
                      font=FL["small"], height=32,
                      fg_color="transparent", border_width=1,
                      border_color=T["border"], text_color=T["txt_secondary"],
                      hover_color=T["bg_panel_l"],
                      command=self._logout).grid(
            row=6, column=0, padx=24, pady=(0,24), sticky="ew")

    def _sblocca(self):
        pwd = self._entry_pwd.get()
        username = SessioneUtente.corrente["username"]
        ok, msg = auth.verifica_login(username, pwd)
        if ok:
            self.destroy()
            if self._on_sblocco:
                self._on_sblocco()
        else:
            self._lbl_err.configure(text=f"⚠  {msg}")
            self._entry_pwd.delete(0, "end")

    def _logout(self):
        SessioneUtente.logout()
        self.destroy()
        if self._on_sblocco:
            self._on_sblocco(logout=True)


# ===========================================================================
# GESTIONE UTENTI
# ===========================================================================

class GestioneUtentiFrame(ctk.CTkFrame):

    def __init__(self, master, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self._utente_sel: Optional[int] = None
        self._build_ui()
        self.aggiorna()

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=2)
        self.grid_columnconfigure(1, weight=3)
        self.grid_rowconfigure(0, weight=1)

        lcard = ctk.CTkFrame(self, fg_color=CU["card"], corner_radius=12)
        lcard.grid(row=0, column=0, padx=(0,8), sticky="nsew")
        lcard.grid_columnconfigure(0, weight=1)
        lcard.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(lcard, text="👥  Utenti", font=FONT_SEZ).grid(
            row=0, column=0, padx=16, pady=(16,8), sticky="w")
        self._lista = ctk.CTkScrollableFrame(lcard, fg_color="transparent")
        self._lista.grid(row=1, column=0, padx=8, pady=(0,8), sticky="nsew")
        self._lista.grid_columnconfigure(0, weight=1)
        ctk.CTkButton(lcard, text="➕  Nuovo Utente", font=FONT_NRM, height=38,
                      fg_color=CU["verde"], hover_color="#059669",
                      command=self._nuovo_utente).grid(
            row=2, column=0, padx=12, pady=(0,14), sticky="ew")

        rcard = ctk.CTkFrame(self, fg_color="transparent")
        rcard.grid(row=0, column=1, padx=(8,0), sticky="nsew")
        rcard.grid_columnconfigure(0, weight=1)
        rcard.grid_rowconfigure(0, weight=2)
        rcard.grid_rowconfigure(1, weight=1)

        self._editor = ctk.CTkFrame(rcard, fg_color=CU["card"], corner_radius=12)
        self._editor.grid(row=0, column=0, pady=(0,8), sticky="nsew")
        self._editor.grid_columnconfigure(0, weight=1)
        self._build_editor()

        log_card = ctk.CTkFrame(rcard, fg_color=CU["card"], corner_radius=12)
        log_card.grid(row=1, column=0, sticky="nsew")
        log_card.grid_columnconfigure(0, weight=1)
        log_card.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(log_card, text="📋  Log Accessi (ultimi 50)",
                     font=FONT_SEZ).grid(row=0, column=0, padx=16, pady=(14,6), sticky="w")
        self._txt_log = ctk.CTkTextbox(log_card, font=FONT_MONO, height=130,
                                        fg_color=CU["entry_bg"])
        self._txt_log.grid(row=1, column=0, padx=12, pady=(0,4), sticky="nsew")
        self._txt_log.configure(state="disabled")
        ctk.CTkButton(log_card, text="🔄  Aggiorna Log", font=FONT_SML,
                      height=30, width=140, fg_color=CU["accent"],
                      command=self._aggiorna_log).grid(
            row=2, column=0, padx=12, pady=(0,12), sticky="e")

    def _build_editor(self):
        p = self._editor
        ctk.CTkLabel(p, text="✏️  Modifica Utente", font=FONT_SEZ).grid(
            row=0, column=0, columnspan=2, padx=16, pady=(16,4), sticky="w")
        self._lbl_editor_info = ctk.CTkLabel(p, text="Seleziona un utente dalla lista.",
                                              font=FONT_SML, text_color=CU["grigio"])
        self._lbl_editor_info.grid(row=1, column=0, columnspan=2, padx=16, pady=(0,8), sticky="w")
        ctk.CTkFrame(p, height=1, fg_color=CU["divider"]).grid(
            row=2, column=0, columnspan=2, padx=16, pady=(0,10), sticky="ew")

        ctk.CTkLabel(p, text="Nome visualizzato", font=FONT_SML,
                     text_color=CU["grigio"]).grid(row=3, column=0, padx=16, pady=(0,2), sticky="w")
        self._e_nome = ctk.CTkEntry(p, font=FONT_NRM, height=36, fg_color=CU["entry_bg"])
        self._e_nome.grid(row=4, column=0, columnspan=2, padx=16, pady=(0,10), sticky="ew")

        ctk.CTkLabel(p, text="Ruolo", font=FONT_SML,
                     text_color=CU["grigio"]).grid(row=5, column=0, padx=16, pady=(0,2), sticky="w")
        self._combo_ruolo = ctk.CTkComboBox(p, values=RUOLI, font=FONT_NRM, height=36,
                                             fg_color=CU["entry_bg"], state="readonly")
        self._combo_ruolo.set(RUOLI[1])
        self._combo_ruolo.grid(row=6, column=0, columnspan=2, padx=16, pady=(0,10), sticky="ew")

        br = ctk.CTkFrame(p, fg_color="transparent")
        br.grid(row=7, column=0, columnspan=2, padx=16, pady=(0,10), sticky="ew")
        br.grid_columnconfigure((0,1), weight=1)
        self._btn_salva_mod = ctk.CTkButton(br, text="💾  Salva", font=FONT_NRM, height=38,
                                             fg_color=CU["verde"], hover_color="#059669",
                                             state="disabled", command=self._salva_modifica)
        self._btn_salva_mod.grid(row=0, column=0, padx=(0,4), sticky="ew")
        self._btn_toggle = ctk.CTkButton(br, text="🔴  Disattiva", font=FONT_NRM, height=38,
                                          fg_color=CU["arancio"], hover_color="#d97706",
                                          state="disabled", command=self._toggle_attivo)
        self._btn_toggle.grid(row=0, column=1, padx=(4,0), sticky="ew")

        ctk.CTkFrame(p, height=1, fg_color=CU["divider"]).grid(
            row=8, column=0, columnspan=2, padx=16, pady=(4,10), sticky="ew")

        ctk.CTkLabel(p, text="Nuova Password", font=FONT_SML,
                     text_color=CU["grigio"]).grid(row=9, column=0, padx=16, pady=(0,2), sticky="w")
        pr = ctk.CTkFrame(p, fg_color="transparent")
        pr.grid(row=10, column=0, columnspan=2, padx=16, pady=(0,10), sticky="ew")
        pr.grid_columnconfigure(0, weight=1)
        self._e_pwd = ctk.CTkEntry(pr, font=FONT_NRM, height=36, fg_color=CU["entry_bg"],
                                    show="●", placeholder_text="Lascia vuoto per non cambiare")
        self._e_pwd.grid(row=0, column=0, sticky="ew", padx=(0,6))
        ctk.CTkButton(pr, text="🔑  Cambia", font=FONT_SML, width=90, height=36,
                      fg_color=CU["accent"], command=self._cambia_password).grid(row=0, column=1)

        self._btn_elimina = ctk.CTkButton(p, text="🗑  Elimina Utente", font=FONT_SML,
                                           height=34, fg_color="transparent", border_width=1,
                                           border_color=CU["red"], text_color=CU["red"],
                                           hover_color="#3a0a0a", state="disabled",
                                           command=self._elimina)
        self._btn_elimina.grid(row=11, column=0, columnspan=2, padx=16, pady=(0,8), sticky="ew")
        self._lbl_op_stato = ctk.CTkLabel(p, text="", font=FONT_SML, text_color=CU["verde"])
        self._lbl_op_stato.grid(row=12, column=0, columnspan=2, pady=(0,10))

    def aggiorna(self):
        self._aggiorna_lista()
        self._aggiorna_log()

    def _aggiorna_lista(self):
        for w in self._lista.winfo_children():
            w.destroy()
        for r in auth.get_tutti_utenti():
            self._riga_utente(r)

    def _riga_utente(self, r):
        attivo = bool(r["attivo"])
        col_bg = CU["entry_bg"] if attivo else "#0d0d0d"
        riga = ctk.CTkFrame(self._lista, fg_color=col_bg, corner_radius=8)
        riga.grid(row=r["id"], column=0, padx=4, pady=2, sticky="ew")
        riga.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(riga, text=(r["nome_display"] or r["username"])[0].upper(),
                     font=("Segoe UI", 13, "bold"), width=34, height=34,
                     fg_color=CU["accent"] if attivo else CU["grigio"],
                     corner_radius=17, text_color="white").grid(
            row=0, column=0, rowspan=2, padx=(8,8), pady=6)
        ctk.CTkLabel(riga, text=r["nome_display"] or r["username"],
                     font=FONT_SML, anchor="w").grid(row=0, column=1, sticky="ew")
        ctk.CTkLabel(riga, text=f"{'🔑' if r['ruolo']=='admin' else '👤'} {r['ruolo']}",
                     font=("Segoe UI", 9),
                     text_color=CU["accent"] if r["ruolo"] == "admin" else CU["grigio"],
                     anchor="w").grid(row=1, column=1, sticky="ew")
        ctk.CTkLabel(riga, text="● attivo" if attivo else "● off",
                     font=("Segoe UI", 8),
                     text_color=CU["verde"] if attivo else CU["red"]).grid(
            row=0, column=2, rowspan=2, padx=(0,8))
        riga.bind("<Button-1>", lambda e, rid=r["id"]: self._seleziona(rid))
        riga.bind("<Enter>",    lambda e, f=riga: f.configure(fg_color=CU["accent"]))
        riga.bind("<Leave>",    lambda e, f=riga, bg=col_bg: f.configure(fg_color=bg))

    def _seleziona(self, uid):
        self._utente_sel = uid
        r = next((x for x in auth.get_tutti_utenti() if x["id"] == uid), None)
        if r is None:
            return
        self._e_nome.delete(0, "end")
        self._e_nome.insert(0, r["nome_display"] or "")
        self._combo_ruolo.set(r["ruolo"])
        ultimo = r["ultimo_login"][:16] if r["ultimo_login"] else "—"
        self._lbl_editor_info.configure(
            text=f"@{r['username']}  |  Ultimo login: {ultimo}",
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
            auth.aggiorna_utente(self._utente_sel,
                                 nome_display=self._e_nome.get(),
                                 ruolo=self._combo_ruolo.get())
            self._lbl_op_stato.configure(text="✅  Salvato.", text_color=CU["verde"])
            self._aggiorna_lista()
        except ValueError as e:
            self._lbl_op_stato.configure(text=f"❌  {e}", text_color=CU["red"])

    def _toggle_attivo(self):
        if self._utente_sel is None:
            return
        r = next((x for x in auth.get_tutti_utenti() if x["id"] == self._utente_sel), None)
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
            messagebox.showwarning("Password vuota", "Inserisci la nuova password.", parent=self)
            return
        if len(pwd) < 6:
            messagebox.showwarning("Troppo corta", "Minimo 6 caratteri.", parent=self)
            return
        auth.cambia_password(self._utente_sel, pwd)
        self._e_pwd.delete(0, "end")
        self._lbl_op_stato.configure(text="✅  Password aggiornata.", text_color=CU["verde"])

    def _elimina(self):
        if self._utente_sel is None:
            return
        r = next((x for x in auth.get_tutti_utenti() if x["id"] == self._utente_sel), None)
        nome = r["nome_display"] or r["username"] if r else "?"
        if not messagebox.askyesno("Elimina utente",
                                    f"Eliminare «{nome}»?\nQuesta azione è irreversibile.",
                                    icon="warning", default=messagebox.NO, parent=self):
            return
        try:
            auth.elimina_utente(self._utente_sel)
            self._utente_sel = None
            self._aggiorna_lista()
            self._lbl_op_stato.configure(text="")
        except ValueError as e:
            messagebox.showerror("Errore", str(e), parent=self)

    def _nuovo_utente(self):
        NuovoUtenteDialog(self, on_creato=self._aggiorna_lista)

    def _aggiorna_log(self):
        log = auth.get_log_accessi(50)
        self._txt_log.configure(state="normal")
        self._txt_log.delete("1.0", "end")
        for r in log:
            ico = "✅" if r["esito"] == "ok" else "❌"
            ts  = r["timestamp"][:16] if r["timestamp"] else "—"
            self._txt_log.insert("end",
                f"{ico}  {ts}  @{r['username'] or '—'}  [{r['esito']}]  {r['ip_host'] or ''}\n")
        self._txt_log.configure(state="disabled")


# ===========================================================================
# DIALOG: Nuovo Utente
# ===========================================================================

class NuovoUtenteDialog(ctk.CTkToplevel):

    def __init__(self, master, on_creato=None):
        super().__init__(master)
        self.title("Nuovo Utente")
        self.geometry("400x390")
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
            row=0, column=0, padx=24, pady=(20,16), sticky="w")
        for i, (lbl, attr, show) in enumerate([
            ("Username",          "_e_user", ""),
            ("Nome Visualizzato", "_e_nome", ""),
            ("Password",          "_e_pwd",  "●"),
        ]):
            ctk.CTkLabel(self, text=lbl, font=FONT_SML,
                         text_color=CU["grigio"]).grid(
                row=i*2+1, column=0, padx=24, pady=(0,2), sticky="w")
            e = ctk.CTkEntry(self, font=FONT_NRM, height=38,
                             fg_color=CU["entry_bg"], show=show)
            e.grid(row=i*2+2, column=0, padx=24, pady=(0,10), sticky="ew")
            setattr(self, attr, e)

        ctk.CTkLabel(self, text="Ruolo", font=FONT_SML,
                     text_color=CU["grigio"]).grid(row=7, column=0, padx=24, pady=(0,2), sticky="w")
        self._combo = ctk.CTkComboBox(self, values=RUOLI, font=FONT_NRM, height=38,
                                      fg_color=CU["entry_bg"], state="readonly")
        self._combo.set(RUOLI[1])
        self._combo.grid(row=8, column=0, padx=24, pady=(0,14), sticky="ew")

        self._lbl_err = ctk.CTkLabel(self, text="", font=FONT_SML, text_color=CU["red"])
        self._lbl_err.grid(row=9, column=0, padx=24, pady=(0,4))

        ctk.CTkButton(self, text="➕  Crea Utente", font=("Segoe UI", 13, "bold"),
                      height=44, fg_color=CU["verde"], hover_color="#059669",
                      command=self._crea).grid(row=10, column=0, padx=24, pady=(0,20), sticky="ew")

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

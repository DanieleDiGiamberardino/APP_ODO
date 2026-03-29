"""
ui_email.py
===========
Pannello di invio email con dossier clinico in allegato.
Modificato: Aggiunta opzione sicurezza "None" per test locali (Mailpit/Mailtrap).
"""

import smtplib
import ssl
import configparser
import threading
from email.message import EmailMessage
from email.utils import formatdate
from pathlib import Path
from datetime import date
from typing import Optional
from tkinter import messagebox
import customtkinter as ctk

import database as db
from export_pdf import genera_dossier_pdf

# ---------------------------------------------------------------------------
CONFIG_FILE = db.APP_DIR / "config_email.ini"

COLORI = {
    "card":     "#0f1629",
    "entry_bg": "#070b14",
    "accent":   "#0f3460",
    "red":      "#e94560",
    "verde":    "#3ecf6e",
    "grigio":   "#6b7a99",
    "chiaro":   "#dce8ff",
    "divider":  "#1e2d4a",
    "warn_bg":  "#2a1a00",
}
FONT_SEZ  = ("Segoe UI", 13, "bold")
FONT_NRM  = ("Segoe UI", 12)
FONT_SML  = ("Segoe UI", 10)
FONT_MICRO= ("Segoe UI", 9)
FONT_MONO = ("Consolas", 10)

TEMPLATE_EMAIL = """\
Gentile {nome} {cognome},

in allegato trova il dossier fotografico clinico relativo alla sua cartella presso il nostro studio.

Il documento contiene le fotografie cliniche archiviate con i relativi tag (branca, fase, dente) e le note associate.

Per qualsiasi domanda non esiti a contattarci.

Cordiali saluti,
Studio Dentistico
"""

# AGGIORNATO: Aggiunto preset per test locale
PRESET_SMTP = {
    "Gmail":           {"host": "smtp.gmail.com",         "port": "587", "tls": "STARTTLS"},
    "Outlook/Hotmail": {"host": "smtp-mail.outlook.com",  "port": "587", "tls": "STARTTLS"},
    "Office 365":      {"host": "smtp.office365.com",     "port": "587", "tls": "STARTTLS"},
    "Local (Mailpit)": {"host": "127.0.0.1",              "port": "1025", "tls": "None"},
    "Custom":          {"host": "",                       "port": "587", "tls": "STARTTLS"},
}


# ===========================================================================
# Config email (file .ini)
# ===========================================================================

def _load_config() -> dict:
    cfg = configparser.ConfigParser()
    if CONFIG_FILE.is_file():
        cfg.read(CONFIG_FILE, encoding="utf-8")
    sec = cfg["smtp"] if "smtp" in cfg else {}
    return {
        "host":     sec.get("host",     "smtp.gmail.com"),
        "port":     sec.get("port",     "587"),
        "tls":      sec.get("tls",      "STARTTLS"),
        "username": sec.get("username", ""),
        "password": sec.get("password", ""),
        "mittente": sec.get("mittente", ""),
        "nome_studio": sec.get("nome_studio", "Studio Dentistico"),
    }

def _save_config(dati: dict) -> None:
    cfg = configparser.ConfigParser()
    cfg["smtp"] = dati
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        cfg.write(f)


# ===========================================================================
# Invio email
# ===========================================================================

def invia_email(
    destinatario: str,
    oggetto: str,
    corpo: str,
    allegati: list[Path],
    cfg: dict,
    on_progress: Optional[callable] = None,
) -> None:
    def _log(msg):
        if on_progress:
            on_progress(msg)

    msg = EmailMessage()
    msg["From"]    = f"{cfg['nome_studio']} <{cfg['mittente'] or cfg['username']}>"
    msg["To"]      = destinatario
    msg["Subject"] = oggetto
    msg["Date"]    = formatdate()
    msg.set_content(corpo)

    for path in allegati:
        path = Path(path)
        if not path.is_file():
            _log(f"⚠️  File non trovato: {path.name}")
            continue
        mime_type = "application/pdf" if path.suffix.lower() == ".pdf" else "image/jpeg"
        maintype, subtype = mime_type.split("/")
        with open(path, "rb") as f:
            msg.add_attachment(f.read(), maintype=maintype,
                               subtype=subtype, filename=path.name)
        _log(f"  📎  {path.name}  ({path.stat().st_size // 1024} KB)")

    host = cfg["host"]
    port = int(cfg["port"])
    tls  = cfg.get("tls", "STARTTLS")

    _log(f"Connessione a {host}:{port} ({tls})…")

    # MODIFICATO: Logica di connessione per supportare "None"
    if tls == "SSL/TLS":
        ctx = ssl.create_default_context()
        with smtplib.SMTP_SSL(host, port, context=ctx, timeout=15) as srv:
            srv.login(cfg["username"], cfg["password"])
            srv.send_message(msg)
    
    elif tls == "STARTTLS":
        ctx = ssl.create_default_context()
        with smtplib.SMTP(host, port, timeout=15) as srv:
            srv.ehlo()
            srv.starttls(context=ctx)
            srv.ehlo()
            if cfg["username"] or cfg["password"]:
                srv.login(cfg["username"], cfg["password"])
            srv.send_message(msg)
            
    else:  # "None" - Invio in chiaro (ideale per Mailpit/Smtp4dev)
        with smtplib.SMTP(host, port, timeout=15) as srv:
            srv.ehlo()
            # Login solo se le credenziali sono fornite
            if cfg["username"] or cfg["password"]:
                srv.login(cfg["username"], cfg["password"])
            srv.send_message(msg)

    _log(f"✅  Email inviata a {destinatario}")


def _log_invio(paziente_id: int, destinatario: str, esito: str, note: str = "") -> None:
    with db.get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS email_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                paziente_id INTEGER,
                destinatario TEXT,
                esito       TEXT,
                note        TEXT,
                inviata_il  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )""")
        conn.execute(
            "INSERT INTO email_log (paziente_id, destinatario, esito, note) VALUES (?,?,?,?)",
            (paziente_id, destinatario, esito, note),
        )


# ===========================================================================
# FRAME: Invio Email
# ===========================================================================

class EmailFrame(ctk.CTkFrame):

    def __init__(self, master, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self._paz_id: Optional[int] = None
        self._paz_row = None
        self._pdf_path: Optional[Path] = None
        self._cfg = _load_config()
        self._build_ui()
        self._ricarica_pazienti()

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=2)
        self.grid_rowconfigure(0, weight=1)

        # ── Sinistra ──────────────────────────────────────────────────
        lc = ctk.CTkScrollableFrame(self, fg_color="transparent", label_text="")
        lc.grid(row=0, column=0, padx=(0, 8), sticky="nsew")
        lc.grid_columnconfigure(0, weight=1)

        smtp_card = ctk.CTkFrame(lc, fg_color=COLORI["card"], corner_radius=12)
        smtp_card.grid(row=0, column=0, pady=(0, 10), sticky="ew")
        smtp_card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(smtp_card, text="⚙️  Configurazione SMTP",
                     font=FONT_SEZ).grid(row=0, column=0, padx=16, pady=(14, 6), sticky="w")

        warn = ctk.CTkFrame(smtp_card, fg_color=COLORI["warn_bg"], corner_radius=8)
        warn.grid(row=1, column=0, padx=12, pady=(0, 10), sticky="ew")
        ctk.CTkLabel(warn,
                     text="⚠️  Gmail: usa una App Password (non la password normale).\n"
                          "Account Google → Sicurezza → Verifica in 2 passaggi → App password.",
                     font=("Segoe UI", 8), text_color="#ffb74d",
                     justify="left", wraplength=280).pack(padx=10, pady=8)

        ctk.CTkLabel(smtp_card, text="Provider", font=FONT_MICRO,
                     text_color=COLORI["grigio"]).grid(row=2, column=0, padx=16, pady=(0,2), sticky="w")
        self._combo_preset = ctk.CTkComboBox(
            smtp_card, values=list(PRESET_SMTP.keys()),
            font=FONT_NRM, height=32, fg_color=COLORI["entry_bg"],
            state="readonly", command=self._applica_preset)
        self._combo_preset.set("Custom")
        self._combo_preset.grid(row=3, column=0, padx=16, pady=(0,10), sticky="ew")

        self._e_host = self._campo(smtp_card, "Server SMTP", 4, self._cfg["host"])
        self._e_port = self._campo(smtp_card, "Porta",       6, self._cfg["port"])

        ctk.CTkLabel(smtp_card, text="Sicurezza", font=FONT_MICRO,
                     text_color=COLORI["grigio"]).grid(row=8, column=0, padx=16, pady=(0,2), sticky="w")
        
        # MODIFICATO: Aggiunto "None" alle opzioni della ComboBox
        self._combo_tls = ctk.CTkComboBox(
            smtp_card, values=["None", "STARTTLS", "SSL/TLS"],
            font=FONT_NRM, height=32, fg_color=COLORI["entry_bg"], state="readonly")
        self._combo_tls.set(self._cfg.get("tls", "STARTTLS"))
        self._combo_tls.grid(row=9, column=0, padx=16, pady=(0,10), sticky="ew")

        self._e_user   = self._campo(smtp_card, "Username/Email mittente", 10, self._cfg["username"])
        self._e_pwd    = self._campo(smtp_card, "Password / App Password", 12,
                                     self._cfg["password"], show="●")
        self._e_nome   = self._campo(smtp_card, "Nome Studio (mittente)",   14,
                                     self._cfg.get("nome_studio", "Studio Dentistico"))

        ctk.CTkButton(smtp_card, text="💾  Salva Configurazione",
                      font=FONT_SML, height=34,
                      fg_color=COLORI["accent"],
                      command=self._salva_config).grid(
            row=16, column=0, padx=16, pady=(8, 14), sticky="ew")

        # Card paziente
        paz_card = ctk.CTkFrame(lc, fg_color=COLORI["card"], corner_radius=12)
        paz_card.grid(row=1, column=0, pady=(0, 10), sticky="ew")
        paz_card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(paz_card, text="👤  Seleziona Paziente", font=FONT_SEZ).grid(row=0, column=0, padx=16, pady=(14,6), sticky="w")
        self._entry_cerca = ctk.CTkEntry(paz_card, placeholder_text="🔍 Cerca…", font=FONT_NRM, height=32)
        self._entry_cerca.grid(row=1, column=0, padx=16, pady=(0,6), sticky="ew")
        self._entry_cerca.bind("<KeyRelease>", lambda e: self._ricarica_pazienti())

        self._lista_paz = ctk.CTkScrollableFrame(paz_card, fg_color="transparent", height=160)
        self._lista_paz.grid(row=2, column=0, padx=8, pady=(0,8), sticky="ew")
        self._lista_paz.grid_columnconfigure(0, weight=1)

        self._lbl_paz_sel = ctk.CTkLabel(paz_card, text="Nessun paziente selezionato", font=FONT_MICRO, text_color=COLORI["grigio"])
        self._lbl_paz_sel.grid(row=3, column=0, padx=16, pady=(0,14))

        # ── Destra ────────────────────────────────────────────────────
        rc = ctk.CTkFrame(self, fg_color=COLORI["card"], corner_radius=12)
        rc.grid(row=0, column=1, padx=(8, 0), sticky="nsew")
        rc.grid_columnconfigure(0, weight=1)
        rc.grid_rowconfigure(5, weight=1)

        ctk.CTkLabel(rc, text="📧  Composizione Email", font=FONT_SEZ).grid(row=0, column=0, padx=16, pady=(14,6), sticky="w")
        self._e_dest = self._campo(rc, "Destinatario (email)", 1, "")
        self._e_ogg  = self._campo(rc, "Oggetto", 3, "Dossier fotografico clinico — DentalPhoto")

        all_frame = ctk.CTkFrame(rc, fg_color=COLORI["entry_bg"], corner_radius=8)
        all_frame.grid(row=6, column=0, padx=16, pady=(0,10), sticky="ew")
        self._chk_pdf = ctk.CTkCheckBox(all_frame, text="Genera e allega PDF dossier", font=FONT_SML)
        self._chk_pdf.select()
        self._chk_pdf.grid(row=0, column=0, padx=10, pady=(8,4), sticky="w")
        self._chk_foto = ctk.CTkCheckBox(all_frame, text="Allega foto originali (max 5)", font=FONT_SML)
        self._chk_foto.grid(row=1, column=0, padx=10, pady=(0,8), sticky="w")

        self._txt_corpo = ctk.CTkTextbox(rc, font=FONT_MONO, height=200, fg_color=COLORI["entry_bg"])
        self._txt_corpo.insert("1.0", TEMPLATE_EMAIL)
        self._txt_corpo.grid(row=8, column=0, padx=16, pady=(0,10), sticky="ew")

        self._btn_invia = ctk.CTkButton(rc, text="📤  Invia Email", font=("Segoe UI", 13, "bold"), height=46, fg_color=COLORI["accent"], command=self._invia)
        self._btn_invia.grid(row=10, column=0, padx=16, pady=(0,8), sticky="ew")

        self._progress = ctk.CTkProgressBar(rc, height=6)
        self._progress.set(0)
        self._progress.grid(row=11, column=0, padx=16, pady=(0,4), sticky="ew")

        self._txt_log = ctk.CTkTextbox(rc, font=("Consolas", 8), height=90, fg_color=COLORI["entry_bg"])
        self._txt_log.grid(row=12, column=0, padx=16, pady=(0,16), sticky="ew")
        self._txt_log.configure(state="disabled")

    def _campo(self, parent, lbl, row, val="", show=""):
        ctk.CTkLabel(parent, text=lbl, font=FONT_MICRO, text_color=COLORI["grigio"]).grid(row=row, column=0, padx=16, pady=(0,2), sticky="w")
        e = ctk.CTkEntry(parent, font=FONT_NRM, height=32, fg_color=COLORI["entry_bg"], show=show)
        if val: e.insert(0, val)
        e.grid(row=row+1, column=0, padx=16, pady=(0,6), sticky="ew")
        return e

    def _applica_preset(self, provider: str):
        p = PRESET_SMTP.get(provider, {})
        for attr, key in [("_e_host", "host"), ("_e_port", "port")]:
            w = getattr(self, attr)
            w.delete(0, "end")
            w.insert(0, p.get(key, ""))
        self._combo_tls.set(p.get("tls", "STARTTLS"))

    def _salva_config(self):
        self._cfg = {
            "host":       self._e_host.get().strip(),
            "port":       self._e_port.get().strip(),
            "tls":        self._combo_tls.get(),
            "username":   self._e_user.get().strip(),
            "password":   self._e_pwd.get().strip(),
            "mittente":   self._e_user.get().strip(),
            "nome_studio": self._e_nome.get().strip(),
        }
        _save_config(self._cfg)
        messagebox.showinfo("Salvato", "Configurazione SMTP salvata.", parent=self)

    def _ricarica_pazienti(self, *_):
        righe = db.cerca_pazienti(self._entry_cerca.get())
        for w in self._lista_paz.winfo_children(): w.destroy()
        for i, r in enumerate(righe):
            sel = (r["id"] == self._paz_id)
            ctk.CTkButton(self._lista_paz, text=f"{r['cognome']} {r['nome']}", font=FONT_SML, height=28,
                fg_color=COLORI["accent"] if sel else COLORI["entry_bg"], anchor="w",
                command=lambda rid=r["id"]: self._set_paz(rid)).grid(row=i, column=0, padx=4, pady=2, sticky="ew")

    def _set_paz(self, pid: int):
        self._paz_id  = pid
        self._paz_row = db.get_paziente_by_id(pid)
        r = self._paz_row
        self._lbl_paz_sel.configure(text=f"✅  {r['cognome']} {r['nome']}", text_color=COLORI["verde"])
        if r["email"]:
            self._e_dest.delete(0, "end")
            self._e_dest.insert(0, r["email"])
        self._ricarica_pazienti()

    def _invia(self):
        if not self._paz_id:
            messagebox.showwarning("Paziente mancante", "Seleziona un paziente.", parent=self)
            return
        dest = self._e_dest.get().strip()
        if not dest or "@" not in dest:
            messagebox.showwarning("Destinatario non valido", "Inserisci un indirizzo email valido.", parent=self)
            return
        
        # MODIFICATO: Non bloccare l'invio se mancano credenziali e la sicurezza è "None"
        if self._combo_tls.get() != "None":
            if not self._e_user.get().strip() or not self._e_pwd.get().strip():
                messagebox.showwarning("SMTP non configurato", "Configura le credenziali SMTP prima di inviare.", parent=self)
                return

        self._btn_invia.configure(state="disabled", text="⏳  Invio in corso…")
        self._progress.configure(mode="indeterminate")
        self._progress.start()
        self._log_reset()

        oggetto = self._e_ogg.get().strip()
        corpo   = self._txt_corpo.get("1.0", "end").strip()
        cfg     = dict(self._cfg)
        paz_id  = self._paz_id

        def _job():
            allegati = []
            try:
                if self._chk_pdf.get():
                    self.after(0, self._log, "Generazione PDF dossier…")
                    pdf = genera_dossier_pdf(paz_id, output_dir=db.APP_DIR / "_tmp_email")
                    allegati.append(pdf)

                if self._chk_foto.get():
                    foto_rows = db.cerca_foto(paziente_id=paz_id)[:5]
                    for r in foto_rows: allegati.append(db.get_percorso_assoluto(r))

                invia_email(dest, oggetto, corpo, allegati, cfg,
                            on_progress=lambda m: self.after(0, self._log, m))

                _log_invio(paz_id, dest, "ok")
                self.after(0, self._invio_ok)
            except Exception as exc:
                _log_invio(paz_id, dest, "errore", str(exc))
                self.after(0, self._invio_err, str(exc))
            finally:
                import shutil
                tmp = db.APP_DIR / "_tmp_email"
                if tmp.is_dir(): shutil.rmtree(tmp, ignore_errors=True)

        threading.Thread(target=_job, daemon=True).start()

    def _invio_ok(self):
        self._progress.stop()
        self._progress.configure(mode="determinate")
        self._progress.set(1)
        self._btn_invia.configure(state="normal", text="📤  Invia Email")
        messagebox.showinfo("Inviata", "✅  Email inviata con successo!", parent=self)

    def _invio_err(self, msg: str):
        self._progress.stop()
        self._progress.configure(mode="determinate")
        self._progress.set(0)
        self._btn_invia.configure(state="normal", text="📤  Invia Email")
        self._log(f"❌  Errore: {msg}")
        messagebox.showerror("Errore invio", msg, parent=self)

    def _log(self, testo: str):
        self._txt_log.configure(state="normal")
        self._txt_log.insert("end", testo + "\n")
        self._txt_log.see("end")
        self._txt_log.configure(state="disabled")

    def _log_reset(self):
        self._txt_log.configure(state="normal")
        self._txt_log.delete("1.0", "end")
        self._txt_log.configure(state="disabled")

__all__ = ["EmailFrame"]
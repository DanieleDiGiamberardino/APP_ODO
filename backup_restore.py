"""
backup_restore.py
=================
Funzioni di backup e ripristino dell'intera applicazione.

Backup:
  Crea un archivio ZIP che contiene:
    - dental_app.db
    - tutta la cartella images_storage/

  Il file ZIP viene nominato:
    backup_dentalphoto_AAAA-MM-GG_HHMMSS.zip

Restore:
  Dato un file ZIP di backup:
    1. Verifica che contenga i file attesi
    2. Salva un backup di emergenza del DB corrente
    3. Sovrascrive dental_app.db e images_storage/

Uso standalone:
    from backup_restore import esegui_backup, esegui_restore
"""
import zipfile
import shutil
from pathlib import Path
from datetime import datetime
from typing import Optional, Callable

import database as db


# ---------------------------------------------------------------------------
# BACKUP
# ---------------------------------------------------------------------------

def esegui_backup(
    output_dir: Optional[Path] = None,
    on_progress: Optional[Callable[[str], None]] = None,
) -> Path:
    """
    Crea un archivio ZIP con DB + immagini e lo salva in output_dir.

    Args:
        output_dir:   Cartella di destinazione. Default: APP_DIR.
        on_progress:  Callback opzionale che riceve messaggi di avanzamento.

    Returns:
        Path del file ZIP generato.
    """
    def _log(msg: str):
        if on_progress:
            on_progress(msg)

    output_dir = Path(output_dir) if output_dir else db.APP_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    zip_name  = f"backup_dentalphoto_{timestamp}.zip"
    zip_path  = output_dir / zip_name

    _log(f"Creazione archivio: {zip_name}")

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        # Aggiunge il database
        if db.DB_PATH.exists():
            zf.write(db.DB_PATH, arcname="dental_app.db")
            _log(f"  + {db.DB_PATH.name}  ({db.DB_PATH.stat().st_size // 1024} KB)")
        else:
            _log("  ⚠️  dental_app.db non trovato — saltato")

        # Aggiunge ricorsivamente images_storage/
        n_foto = 0
        if db.IMAGES_DIR.exists():
            for img_path in sorted(db.IMAGES_DIR.rglob("*")):
                if img_path.is_file():
                    # Percorso relativo all'interno dello ZIP
                    arcname = img_path.relative_to(db.APP_DIR).as_posix()
                    zf.write(img_path, arcname=arcname)
                    n_foto += 1
            _log(f"  + images_storage/  ({n_foto} file)")
        else:
            _log("  ℹ️  images_storage/ vuota o assente")

    dimensione_mb = zip_path.stat().st_size / (1024 * 1024)
    _log(f"✅ Backup completato: {zip_name}  ({dimensione_mb:.2f} MB)")

    return zip_path


# ---------------------------------------------------------------------------
# RESTORE
# ---------------------------------------------------------------------------

def esegui_restore(
    zip_path: Path,
    on_progress: Optional[Callable[[str], None]] = None,
) -> None:
    """
    Ripristina DB e immagini da un archivio ZIP di backup.

    ATTENZIONE: sovrascrive il database e le immagini correnti.
    Prima del ripristino viene creato un backup di emergenza automatico.

    Args:
        zip_path:    Path del file ZIP da ripristinare.
        on_progress: Callback opzionale per messaggi di avanzamento.

    Raises:
        ValueError: se il file ZIP non è un backup DentalPhoto valido.
        FileNotFoundError: se zip_path non esiste.
    """
    def _log(msg: str):
        if on_progress:
            on_progress(msg)

    zip_path = Path(zip_path)
    if not zip_path.is_file():
        raise FileNotFoundError(f"File non trovato: {zip_path}")

    # Verifica che sia un backup valido (deve contenere dental_app.db)
    with zipfile.ZipFile(zip_path, "r") as zf:
        nomi_archivio = set(zf.namelist())
    if "dental_app.db" not in nomi_archivio:
        raise ValueError("Il file selezionato non sembra un backup DentalPhoto valido "
                         "(manca dental_app.db).")

    # ── Backup di emergenza automatico ──────────────────────────────────────
    _log("Creazione backup di emergenza del DB corrente…")
    try:
        emergency = esegui_backup(
            output_dir=db.APP_DIR / "backups_emergenza",
            on_progress=lambda m: _log(f"  {m}"),
        )
        _log(f"  Backup di emergenza salvato: {emergency.name}")
    except Exception as exc:
        _log(f"  ⚠️  Impossibile creare backup di emergenza: {exc}")

    # ── Ripristino ────────────────────────────────────────────────────────
    _log(f"Estrazione archivio: {zip_path.name}")

    with zipfile.ZipFile(zip_path, "r") as zf:
        # Ripristina il database
        _log("  Ripristino dental_app.db…")
        zf.extract("dental_app.db", path=db.APP_DIR)

        # Ripristina le immagini
        img_files = [n for n in zf.namelist() if n.startswith("images_storage/")]
        _log(f"  Ripristino {len(img_files)} immagini in images_storage/…")

        # Svuota la cartella images esistente per evitare file orfani
        if db.IMAGES_DIR.exists():
            shutil.rmtree(db.IMAGES_DIR)
        db.IMAGES_DIR.mkdir(parents=True, exist_ok=True)

        for nome in img_files:
            zf.extract(nome, path=db.APP_DIR)

    _log(f"✅ Ripristino completato da {zip_path.name}")
    _log("  ℹ️  Riavvia l'applicazione per applicare le modifiche.")


# ---------------------------------------------------------------------------
# VERIFICA INTEGRITÀ BACKUP
# ---------------------------------------------------------------------------

def verifica_backup(zip_path: Path) -> dict:
    """
    Verifica l'integrità di un archivio ZIP di backup senza estrarlo.

    Returns:
        Dizionario con:
          - 'valido':     bool
          - 'n_immagini': int
          - 'ha_db':      bool
          - 'dimensione': str (human-readable)
          - 'errore':     str o None
    """
    info: dict = {
        "valido":     False,
        "n_immagini": 0,
        "ha_db":      False,
        "dimensione": "—",
        "errore":     None,
    }

    try:
        zip_path = Path(zip_path)
        info["dimensione"] = f"{zip_path.stat().st_size / (1024*1024):.2f} MB"

        with zipfile.ZipFile(zip_path, "r") as zf:
            # Verifica CRC di ogni file
            bad = zf.testzip()
            if bad:
                info["errore"] = f"File corrotto nell'archivio: {bad}"
                return info

            nomi = zf.namelist()
            info["ha_db"]      = "dental_app.db" in nomi
            info["n_immagini"] = sum(1 for n in nomi if n.startswith("images_storage/"))
            info["valido"]     = info["ha_db"]

    except zipfile.BadZipFile:
        info["errore"] = "File ZIP non valido o corrotto."
    except Exception as exc:
        info["errore"] = str(exc)

    return info


# ---------------------------------------------------------------------------
# FRAME UI per Backup/Restore (integrato in App)
# ---------------------------------------------------------------------------

# Importati qui per non circolarizzare
from tkinter import filedialog, messagebox
import customtkinter as ctk
import threading

COLORI_UI = {
    "card_bg":      "#16213e",
    "sfondo_entry": "#0d1117",
    "accent":       "#0f3460",
    "verde_ok":     "#4caf50",
    "rosso_err":    "#f44336",
    "arancio":      "#ff9800",
    "testo_grigio": "#9e9e9e",
    "testo_chiaro": "#e0e0e0",
    "viola":        "#7b1fa2",
}

FONT_SEZIONE = ("Segoe UI", 13, "bold")
FONT_NORMALE = ("Segoe UI", 12)
FONT_PICCOLO = ("Segoe UI", 10)
FONT_MONO    = ("Consolas", 9)


class BackupRestoreFrame(ctk.CTkFrame):
    """
    Pannello di backup e ripristino.

    Struttura:
      Sinistra  → Backup (scelta cartella, avvia, log)
      Destra    → Ripristino (scelta ZIP, verifica, avvia, log)
    """

    def __init__(self, master, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self._build_ui()

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # ── BACKUP ─────────────────────────────────────────────────────
        bcard = ctk.CTkFrame(self, fg_color=COLORI_UI["card_bg"], corner_radius=12)
        bcard.grid(row=0, column=0, padx=(0, 8), pady=0, sticky="nsew")
        bcard.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(bcard, text="💾  Backup",
                     font=FONT_SEZIONE).grid(row=0, column=0, padx=20, pady=(20, 4), sticky="w")
        ctk.CTkLabel(bcard,
                     text="Crea un archivio ZIP con il database\ne tutte le fotografie.",
                     font=FONT_PICCOLO,
                     text_color=COLORI_UI["testo_grigio"],
                     justify="left").grid(row=1, column=0, padx=20, pady=(0, 16), sticky="w")

        # Cartella destinazione
        ctk.CTkLabel(bcard, text="Cartella destinazione",
                     font=FONT_PICCOLO,
                     text_color=COLORI_UI["testo_grigio"]).grid(
            row=2, column=0, padx=20, pady=(0, 2), sticky="w")

        dir_row = ctk.CTkFrame(bcard, fg_color="transparent")
        dir_row.grid(row=3, column=0, padx=20, pady=(0, 14), sticky="ew")
        dir_row.grid_columnconfigure(0, weight=1)

        self._entry_backup_dir = ctk.CTkEntry(
            dir_row, font=FONT_PICCOLO, height=32,
            placeholder_text=str(db.APP_DIR))
        self._entry_backup_dir.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self._entry_backup_dir.insert(0, str(db.APP_DIR))

        ctk.CTkButton(
            dir_row, text="…", width=36, height=32, font=FONT_PICCOLO,
            command=self._scegli_dir_backup,
        ).grid(row=0, column=1)

        # Pulsante backup
        ctk.CTkButton(
            bcard, text="🚀  Avvia Backup",
            font=("Segoe UI", 13, "bold"), height=44,
            fg_color=COLORI_UI["verde_ok"], hover_color="#388e3c",
            command=self._avvia_backup,
        ).grid(row=4, column=0, padx=20, pady=(0, 14), sticky="ew")

        # Log backup
        ctk.CTkLabel(bcard, text="Log",
                     font=FONT_PICCOLO,
                     text_color=COLORI_UI["testo_grigio"]).grid(
            row=5, column=0, padx=20, pady=(0, 2), sticky="w")

        self._txt_backup_log = ctk.CTkTextbox(
            bcard, font=FONT_MONO, height=220,
            fg_color=COLORI_UI["sfondo_entry"])
        self._txt_backup_log.grid(row=6, column=0, padx=20, pady=(0, 20), sticky="ew")
        self._txt_backup_log.configure(state="disabled")

        # Info percorso app
        ctk.CTkLabel(bcard,
                     text=f"📁  App: {db.APP_DIR}",
                     font=("Segoe UI", 8),
                     text_color=COLORI_UI["testo_grigio"],
                     wraplength=340).grid(row=7, column=0, padx=20, pady=(0, 16))

        # ── RESTORE ────────────────────────────────────────────────────
        rcard = ctk.CTkFrame(self, fg_color=COLORI_UI["card_bg"], corner_radius=12)
        rcard.grid(row=0, column=1, padx=(8, 0), pady=0, sticky="nsew")
        rcard.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(rcard, text="📂  Ripristino",
                     font=FONT_SEZIONE).grid(row=0, column=0, padx=20, pady=(20, 4), sticky="w")

        # Avviso
        avviso = ctk.CTkFrame(rcard, fg_color="#3a1b00", corner_radius=8)
        avviso.grid(row=1, column=0, padx=20, pady=(0, 16), sticky="ew")
        ctk.CTkLabel(avviso,
                     text="⚠️  Il ripristino sovrascrive il database e le immagini correnti.\n"
                          "Un backup di emergenza automatico verrà creato prima.",
                     font=FONT_PICCOLO,
                     text_color=COLORI_UI["arancio"],
                     wraplength=340,
                     justify="left").pack(padx=12, pady=10)

        # Selezione file ZIP
        ctk.CTkLabel(rcard, text="File ZIP di backup",
                     font=FONT_PICCOLO,
                     text_color=COLORI_UI["testo_grigio"]).grid(
            row=2, column=0, padx=20, pady=(0, 2), sticky="w")

        zip_row = ctk.CTkFrame(rcard, fg_color="transparent")
        zip_row.grid(row=3, column=0, padx=20, pady=(0, 8), sticky="ew")
        zip_row.grid_columnconfigure(0, weight=1)

        self._entry_zip = ctk.CTkEntry(
            zip_row, font=FONT_PICCOLO, height=32,
            placeholder_text="Seleziona un file .zip…")
        self._entry_zip.grid(row=0, column=0, sticky="ew", padx=(0, 6))

        ctk.CTkButton(
            zip_row, text="…", width=36, height=32, font=FONT_PICCOLO,
            command=self._scegli_zip,
        ).grid(row=0, column=1)

        # Info backup selezionato
        self._lbl_zip_info = ctk.CTkLabel(
            rcard, text="",
            font=FONT_PICCOLO,
            text_color=COLORI_UI["testo_grigio"],
            wraplength=340,
        )
        self._lbl_zip_info.grid(row=4, column=0, padx=20, pady=(0, 8))

        # Pulsanti verifica + ripristino
        btn_row = ctk.CTkFrame(rcard, fg_color="transparent")
        btn_row.grid(row=5, column=0, padx=20, pady=(0, 14), sticky="ew")
        btn_row.grid_columnconfigure(0, weight=1)
        btn_row.grid_columnconfigure(1, weight=1)

        ctk.CTkButton(
            btn_row, text="🔍  Verifica",
            font=FONT_NORMALE, height=38,
            fg_color=COLORI_UI["accent"],
            command=self._verifica_zip,
        ).grid(row=0, column=0, padx=(0, 6), sticky="ew")

        ctk.CTkButton(
            btn_row, text="♻️  Ripristina",
            font=("Segoe UI", 13, "bold"), height=38,
            fg_color=COLORI_UI["rosso_err"], hover_color="#c62828",
            command=self._avvia_restore,
        ).grid(row=0, column=1, sticky="ew")

        # Log restore
        ctk.CTkLabel(rcard, text="Log",
                     font=FONT_PICCOLO,
                     text_color=COLORI_UI["testo_grigio"]).grid(
            row=6, column=0, padx=20, pady=(0, 2), sticky="w")

        self._txt_restore_log = ctk.CTkTextbox(
            rcard, font=FONT_MONO, height=220,
            fg_color=COLORI_UI["sfondo_entry"])
        self._txt_restore_log.grid(row=7, column=0, padx=20, pady=(0, 20), sticky="ew")
        self._txt_restore_log.configure(state="disabled")

    # ------------------------------------------------------------------

    def _scegli_dir_backup(self):
        d = filedialog.askdirectory(title="Cartella backup",
                                    initialdir=str(db.APP_DIR))
        if d:
            self._entry_backup_dir.delete(0, "end")
            self._entry_backup_dir.insert(0, d)

    def _scegli_zip(self):
        path = filedialog.askopenfilename(
            title="Seleziona backup ZIP",
            filetypes=[("ZIP", "*.zip"), ("Tutti", "*.*")],
        )
        if path:
            self._entry_zip.delete(0, "end")
            self._entry_zip.insert(0, path)
            self._lbl_zip_info.configure(text="")

    def _verifica_zip(self):
        zip_path = self._entry_zip.get().strip()
        if not zip_path:
            messagebox.showwarning("File mancante", "Scegli un file ZIP.")
            return
        info = verifica_backup(Path(zip_path))
        if info["errore"]:
            self._lbl_zip_info.configure(
                text=f"❌  {info['errore']}", text_color=COLORI_UI["rosso_err"])
        elif info["valido"]:
            self._lbl_zip_info.configure(
                text=f"✅  Backup valido  |  {info['n_immagini']} immagini  "
                     f"|  {info['dimensione']}",
                text_color=COLORI_UI["verde_ok"],
            )
        else:
            self._lbl_zip_info.configure(
                text="⚠️  File non riconosciuto come backup DentalPhoto.",
                text_color=COLORI_UI["arancio"],
            )

    # ------------------------------------------------------------------
    # Backup con thread
    # ------------------------------------------------------------------

    def _avvia_backup(self):
        output_dir = Path(self._entry_backup_dir.get().strip() or str(db.APP_DIR))
        self._log_reset(self._txt_backup_log)

        def _job():
            try:
                esegui_backup(
                    output_dir=output_dir,
                    on_progress=lambda m: self.after(
                        0, self._log_riga, self._txt_backup_log, m),
                )
            except Exception as exc:
                self.after(0, self._log_riga, self._txt_backup_log,
                           f"❌ Errore: {exc}")

        threading.Thread(target=_job, daemon=True).start()

    # ------------------------------------------------------------------
    # Restore con thread
    # ------------------------------------------------------------------

    def _avvia_restore(self):
        zip_str = self._entry_zip.get().strip()
        if not zip_str:
            messagebox.showwarning("File mancante", "Scegli un file ZIP.")
            return

        conferma = messagebox.askyesno(
            "Conferma ripristino",
            "⚠️  ATTENZIONE\n\n"
            "Il ripristino sovrascriverà TUTTI i dati attuali.\n"
            "Un backup di emergenza verrà creato automaticamente.\n\n"
            "Procedere?",
        )
        if not conferma:
            return

        self._log_reset(self._txt_restore_log)

        def _job():
            try:
                esegui_restore(
                    zip_path=Path(zip_str),
                    on_progress=lambda m: self.after(
                        0, self._log_riga, self._txt_restore_log, m),
                )
            except Exception as exc:
                self.after(0, self._log_riga, self._txt_restore_log,
                           f"❌ Errore: {exc}")

        threading.Thread(target=_job, daemon=True).start()

    # ------------------------------------------------------------------
    # Log helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _log_reset(widget: ctk.CTkTextbox):
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.configure(state="disabled")

    @staticmethod
    def _log_riga(widget: ctk.CTkTextbox, testo: str):
        widget.configure(state="normal")
        widget.insert("end", testo + "\n")
        widget.see("end")
        widget.configure(state="disabled")

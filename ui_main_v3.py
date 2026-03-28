"""
ui_main_v3.py  — Versione finale (Phase 4)
==========================================
Integra tutti i moduli sviluppati nelle fasi precedenti:

  Fase 1  →  database.py
  Fase 2  →  ui_main.py (base)
  Fase 3  →  export_pdf.py, ui_statistiche.py
  Fase 4  →  ui_bulk_import.py, ui_viewer.py, backup_restore.py

Navigazione sidebar:
  📋 Dashboard    → Ricerca avanzata + galleria (viewer zoomabile al click)
  👤 Pazienti     → Anagrafica + form inserimento
  ⬆️ Upload       → Caricamento singola foto con tagging
  📦 Import       → Import massivo multi-file con batch tag     ← NEW
  📊 Statistiche  → Grafici + modifica tag post-upload
  💾 Backup       → Backup ZIP e ripristino                     ← NEW

Pulsante rapido "💾 Backup" in fondo alla sidebar.
"""

import tkinter as tk
from tkinter import filedialog, messagebox
import customtkinter as ctk
from PIL import Image
from datetime import date
import threading
from pathlib import Path
from typing import Optional

import database as db
from auth import SessioneUtente, init_auth_db, PERMESSI
from ui_login import LockScreen, GestioneUtentiFrame
from thumbnail_cache import get_thumbnail, GalleryLoader
from export_pdf import genera_dossier_pdf
from ui_statistiche import StatisticheFrame
from ui_modifica_tag import ModificaTagFrame
from ui_bulk_import import BulkImportFrame
from ui_viewer import ViewerFoto
from backup_restore import BackupRestoreFrame, esegui_backup
from ui_scheda_paziente import SchedaPaziente
from ui_webcam import WebcamFrame
from ui_before_after import BeforeAfterFrame
from ui_email import EmailFrame
from ui_timeline import TimelineFrame

# ---------------------------------------------------------------------------
# Tema
# ---------------------------------------------------------------------------

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

COLORI = {
    "sidebar_bg":    "#080c18",   # quasi-nero profondo
    "sidebar_hover": "#0f1629",
    "accent":        "#0f3460",
    "accent_bright": "#e94560",
    "card_bg":       "#0f1629",   # card più scura
    "testo_chiaro":  "#dce8ff",   # bianco con tinta blu
    "testo_grigio":  "#6b7a99",
    "verde_ok":      "#3ecf6e",
    "sfondo_entry":  "#070b14",
    "pdf_btn":       "#6a1fa2",
    "backup_btn":    "#c94a00",
    "lock_btn":      "#1a4a7a",
    "sidebar_border":"#1e2d4a",
    "nav_active":    "#1a2e50",   # voce nav attiva: sfondo azzurro scuro
    "nav_accent":    "#e94560",   # bordo sinistro voce attiva
}

FONT_TITOLO  = ("Segoe UI", 22, "bold")
FONT_SEZIONE = ("Segoe UI", 13, "bold")
FONT_NORMALE = ("Segoe UI", 12)
FONT_PICCOLO = ("Segoe UI", 10)
FONT_BADGE   = ("Segoe UI", 10, "bold")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _crea_miniatura(percorso: Path, size=(180, 140)) -> Optional[ctk.CTkImage]:
    try:
        img = Image.open(percorso)
        img.thumbnail(size, Image.LANCZOS)
        return ctk.CTkImage(light_image=img, dark_image=img, size=img.size)
    except Exception:
        return None


def _placeholder_image(size=(180, 140)) -> ctk.CTkImage:
    img = Image.new("RGB", size, (40, 40, 55))
    return ctk.CTkImage(light_image=img, dark_image=img, size=size)


def _badge(parent, testo: str, colore: str):
    ctk.CTkLabel(parent, text=testo, font=FONT_BADGE,
                 fg_color=colore, corner_radius=6,
                 text_color="white", padx=6, pady=2).pack(side="left", padx=(0, 4))


def _esporta_pdf_con_feedback(parent_widget, paziente_id: int,
                               filtri: Optional[dict] = None,
                               output_dir: Optional[Path] = None):
    if output_dir is None:
        cartella = filedialog.askdirectory(title="Cartella PDF",
                                           initialdir=str(db.APP_DIR))
        if not cartella:
            return
        output_dir = Path(cartella)

    popup = ctk.CTkToplevel(parent_widget)
    popup.title("Generazione PDF…")
    popup.geometry("320x110")
    popup.resizable(False, False)
    popup.grab_set()
    ctk.CTkLabel(popup, text="⏳  Generazione dossier PDF…",
                 font=FONT_NORMALE).pack(expand=True, pady=16)
    pb = ctk.CTkProgressBar(popup, mode="indeterminate")
    pb.pack(padx=20, fill="x")
    pb.start()
    result: dict = {}

    def _job():
        try:
            result["path"] = genera_dossier_pdf(paziente_id, output_dir, filtri)
        except Exception as exc:
            result["error"] = str(exc)

    def _done():
        popup.destroy()
        if "error" in result:
            messagebox.showerror("Errore PDF", result["error"], parent=parent_widget)
        else:
            messagebox.showinfo("PDF Generato",
                                f"Salvato in:\n{result['path']}", parent=parent_widget)

    threading.Thread(target=lambda: (_job(), parent_widget.after(0, _done)),
                     daemon=True).start()


# ===========================================================================
# FRAME: PAZIENTI
# ===========================================================================

class PazientiFrame(ctk.CTkFrame):
    def __init__(self, master, on_paziente_selezionato=None, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.on_paziente_selezionato = on_paziente_selezionato
        self._build_ui()
        self.aggiorna_lista()

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=2)
        self.grid_rowconfigure(0, weight=1)

        fc = ctk.CTkFrame(self, fg_color=COLORI["card_bg"], corner_radius=12)
        fc.grid(row=0, column=0, padx=(0, 8), sticky="nsew")
        fc.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(fc, text="Nuovo Paziente", font=FONT_SEZIONE).grid(
            row=0, column=0, padx=20, pady=(20, 6), sticky="w")

        self._entry_nome    = self._campo(fc, "Nome *",    2)
        self._entry_cognome = self._campo(fc, "Cognome *", 4)
        self._entry_tel     = self._campo(fc, "Telefono",  6)
        self._entry_note    = self._campo_multi(fc, "Note", 8)

        ctk.CTkButton(fc, text="➕  Salva Paziente", font=FONT_NORMALE, height=40,
                      command=self._salva).grid(row=10, column=0, padx=20, pady=(10, 20), sticky="ew")

        lc = ctk.CTkFrame(self, fg_color=COLORI["card_bg"], corner_radius=12)
        lc.grid(row=0, column=1, padx=(8, 0), sticky="nsew")
        lc.grid_columnconfigure(0, weight=1)
        lc.grid_rowconfigure(2, weight=1)

        ctk.CTkLabel(lc, text="Archivio Pazienti", font=FONT_SEZIONE).grid(
            row=0, column=0, padx=20, pady=(20, 6), sticky="w")

        self._entry_cerca = ctk.CTkEntry(lc, placeholder_text="🔍 Cerca…",
                                          font=FONT_NORMALE, height=36)
        self._entry_cerca.grid(row=1, column=0, padx=20, pady=(0, 10), sticky="ew")
        self._entry_cerca.bind("<KeyRelease>", lambda e: self.aggiorna_lista())

        self._lista = ctk.CTkScrollableFrame(lc, fg_color="transparent")
        self._lista.grid(row=2, column=0, padx=10, pady=(0, 10), sticky="nsew")
        self._lista.grid_columnconfigure(0, weight=1)

    def _campo(self, p, lbl, row):
        ctk.CTkLabel(p, text=lbl, font=FONT_PICCOLO,
                     text_color=COLORI["testo_grigio"]).grid(
            row=row, column=0, padx=20, pady=(8, 0), sticky="w")
        e = ctk.CTkEntry(p, font=FONT_NORMALE, height=34)
        e.grid(row=row + 1, column=0, padx=20, pady=(2, 0), sticky="ew")
        return e

    def _campo_multi(self, p, lbl, row):
        ctk.CTkLabel(p, text=lbl, font=FONT_PICCOLO,
                     text_color=COLORI["testo_grigio"]).grid(
            row=row, column=0, padx=20, pady=(8, 0), sticky="w")
        t = ctk.CTkTextbox(p, font=FONT_NORMALE, height=80)
        t.grid(row=row + 1, column=0, padx=20, pady=(2, 0), sticky="ew")
        return t

    def _salva(self):
        n, c = self._entry_nome.get().strip(), self._entry_cognome.get().strip()
        if not n or not c:
            messagebox.showwarning("Campi obbligatori", "Nome e Cognome richiesti.")
            return
        pid = db.inserisci_paziente(n, c, self._entry_tel.get().strip(),
                                    self._entry_note.get("1.0", "end").strip())
        for w in (self._entry_nome, self._entry_cognome, self._entry_tel):
            w.delete(0, "end")
        self._entry_note.delete("1.0", "end")
        self.aggiorna_lista()
        messagebox.showinfo("Salvato", f"Paziente aggiunto (ID {pid}).")

    def aggiorna_lista(self, *_):
        righe = db.cerca_pazienti(self._entry_cerca.get())
        for w in self._lista.winfo_children():
            w.destroy()
        if not righe:
            ctk.CTkLabel(self._lista, text="Nessun paziente.", font=FONT_PICCOLO,
                         text_color=COLORI["testo_grigio"]).grid(row=0, column=0, pady=20)
            return
        for i, r in enumerate(righe):
            self._riga_paziente(i, r)

    def _riga_paziente(self, idx: int, r):
        """
        Costruisce una riga paziente con:
          - Avatar / iniziale
          - Zona clickabile (nome + telefono) che copre tutto il banner
          - Badge foto
          - Pulsante elimina
        Il binding hover/click viene propagato a TUTTI i widget figli
        in modo che l'intera area risponda al cursore.
        """
        n_foto = db.conta_foto_per_paziente(r["id"])

        riga = ctk.CTkFrame(self._lista, fg_color=COLORI["sfondo_entry"],
                            corner_radius=8, cursor="hand2")
        riga.grid(row=idx, column=0, padx=4, pady=3, sticky="ew")
        # colonna 1 (testo) si espande; colonne 0/2/3 fisse
        riga.grid_columnconfigure(1, weight=1)

        # ── Avatar ────────────────────────────────────────────────────
        avatar = ctk.CTkLabel(
            riga,
            text=r["cognome"][0].upper(),
            font=("Segoe UI", 15, "bold"),
            width=42, height=42,
            fg_color=COLORI["accent"],
            corner_radius=21,
            text_color="white",
            cursor="hand2",
        )
        avatar.grid(row=0, column=0, rowspan=2, padx=(10, 8), pady=8)

        # ── Testo: nome + telefono ────────────────────────────────────
        lbl_nome = ctk.CTkLabel(
            riga,
            text=f"{r['cognome']} {r['nome']}",
            font=FONT_NORMALE,
            anchor="w",
            cursor="hand2",
        )
        lbl_nome.grid(row=0, column=1, sticky="ew", padx=(0, 4), pady=(8, 1))

        lbl_tel = ctk.CTkLabel(
            riga,
            text=f"📞 {r['telefono'] or '—'}",
            font=FONT_PICCOLO,
            text_color=COLORI["testo_grigio"],
            anchor="w",
            cursor="hand2",
        )
        lbl_tel.grid(row=1, column=1, sticky="ew", padx=(0, 4), pady=(0, 8))

        # ── Badge foto ────────────────────────────────────────────────
        bc = COLORI["accent_bright"] if n_foto > 0 else COLORI["testo_grigio"]
        badge = ctk.CTkLabel(
            riga,
            text=f"📷 {n_foto}",
            font=FONT_BADGE,
            fg_color=bc,
            corner_radius=10,
            width=48, height=22,
            text_color="white",
        )
        badge.grid(row=0, column=2, rowspan=2, padx=(4, 6))

        # ── Pulsante scheda clinica ──────────────────────────────────
        btn_scheda = ctk.CTkButton(
            riga,
            text="📋",
            width=32, height=32,
            font=("Segoe UI", 13),
            fg_color=COLORI["accent"],
            hover_color="#1a5276",
            corner_radius=6,
            command=lambda rid=r["id"]: SchedaPaziente(self, rid),
        )
        btn_scheda.grid(row=0, column=3, rowspan=2, padx=(0, 4))

        # ── Pulsante elimina ─────────────────────────────────────────
        btn_del = ctk.CTkButton(
            riga,
            text="🗑",
            width=32, height=32,
            font=("Segoe UI", 13),
            fg_color="transparent",
            hover_color=COLORI["accent_bright"],
            corner_radius=6,
            command=lambda rid=r["id"], nome=f"{r['cognome']} {r['nome']}":
                self._elimina_paziente(rid, nome),
        )
        btn_del.grid(row=0, column=4, rowspan=2, padx=(0, 8))

        # ── Propagazione hover + click a TUTTI i widget figli ─────────
        # Senza questo, cliccare su un CTkLabel non triggera il binding del frame padre.
        widget_clickabili = (riga, avatar, lbl_nome, lbl_tel, badge)
        # btn_scheda and btn_del intentionally excluded — they have their own commands

        def _on_enter(e, f=riga):
            f.configure(fg_color=COLORI["accent"])

        def _on_leave(e, f=riga):
            f.configure(fg_color=COLORI["sfondo_entry"])

        def _on_click(e, rid=r["id"]):
            self._seleziona(rid)

        for w in widget_clickabili:
            w.bind("<Button-1>", _on_click)
            w.bind("<Enter>",    _on_enter)
            w.bind("<Leave>",    _on_leave)

    def _seleziona(self, pid: int):
        if self.on_paziente_selezionato:
            self.on_paziente_selezionato(pid)

    def _elimina_paziente(self, paziente_id: int, nome: str):
        """
        Chiede conferma e cancella il paziente (+ tutte le sue foto via CASCADE).
        Avvisa quante foto verranno eliminate prima di procedere.
        """
        n_foto = db.conta_foto_per_paziente(paziente_id)
        dettaglio = (
            f"Stai per eliminare:\n\n"
            f"  👤  {nome}\n"
            f"  📷  {n_foto} fotografi{'a' if n_foto == 1 else 'e'} collegate\n\n"
            "Questa operazione è irreversibile.\n"
            "I file immagine rimarranno nella cartella images_storage/.\n\n"
            "Continuare?"
        )
        conferma = messagebox.askyesno(
            "Elimina Paziente", dettaglio,
            icon="warning",
            default=messagebox.NO,
        )
        if not conferma:
            return

        db.elimina_paziente(paziente_id)
        self.aggiorna_lista()


# ===========================================================================
# FRAME: UPLOAD
# ===========================================================================

class UploadFrame(ctk.CTkFrame):
    def __init__(self, master, paz_id_init=None, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self._paz_id: Optional[int] = paz_id_init
        self._file: Optional[Path] = None
        self._prev_img = None
        self._build_ui()
        self._ricarica_pazienti()

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=2)
        self.grid_rowconfigure(0, weight=1)

        pc = ctk.CTkFrame(self, fg_color=COLORI["card_bg"], corner_radius=12)
        pc.grid(row=0, column=0, padx=(0, 8), sticky="nsew")
        pc.grid_columnconfigure(0, weight=1)
        pc.grid_rowconfigure(2, weight=1)

        ctk.CTkLabel(pc, text="1 · Paziente", font=FONT_SEZIONE).grid(
            row=0, column=0, padx=20, pady=(20, 8), sticky="w")
        self._cerca = ctk.CTkEntry(pc, placeholder_text="🔍", font=FONT_NORMALE, height=32)
        self._cerca.grid(row=1, column=0, padx=20, pady=(0, 6), sticky="ew")
        self._cerca.bind("<KeyRelease>", lambda e: self._ricarica_pazienti())
        self._lista = ctk.CTkScrollableFrame(pc, fg_color="transparent")
        self._lista.grid(row=2, column=0, padx=8, pady=(0, 8), sticky="nsew")
        self._lista.grid_columnconfigure(0, weight=1)
        self._lbl_sel = ctk.CTkLabel(pc, text="Nessun paziente", font=FONT_PICCOLO,
                                      text_color=COLORI["testo_grigio"])
        self._lbl_sel.grid(row=3, column=0, padx=20, pady=(0, 16))

        uc = ctk.CTkFrame(self, fg_color=COLORI["card_bg"], corner_radius=12)
        uc.grid(row=0, column=1, padx=(8, 0), sticky="nsew")
        uc.grid_columnconfigure(0, weight=1)
        uc.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(uc, text="2 · Carica & Tagga", font=FONT_SEZIONE).grid(
            row=0, column=0, columnspan=2, padx=20, pady=(20, 4), sticky="w")

        self._prev = ctk.CTkLabel(uc,
                                   text="📂  Clicca per scegliere",
                                   font=FONT_PICCOLO, text_color=COLORI["testo_grigio"],
                                   width=320, height=200,
                                   fg_color=COLORI["sfondo_entry"], corner_radius=10)
        self._prev.grid(row=1, column=0, columnspan=2, padx=20, pady=(8, 4), sticky="ew")
        self._prev.bind("<Button-1>", lambda e: self._scegli())

        ctk.CTkButton(uc, text="📂  Scegli Immagine", font=FONT_NORMALE, height=36,
                      command=self._scegli).grid(row=2, column=0, columnspan=2,
                                                  padx=20, pady=(4, 14), sticky="ew")

        self._c_dente  = self._combo_row(uc, "Dente (FDI)", db.DENTI_FDI, 3, 0)
        self._c_branca = self._combo_row(uc, "Branca",      db.BRANCHE,   3, 1)
        self._c_fase   = self._combo_row(uc, "Fase",        db.FASI,      5, 0)

        ctk.CTkLabel(uc, text="Data", font=FONT_PICCOLO,
                     text_color=COLORI["testo_grigio"]).grid(
            row=5, column=1, padx=(6, 20), pady=(0, 2), sticky="w")
        self._data = ctk.CTkEntry(uc, font=FONT_NORMALE, height=34)
        self._data.insert(0, date.today().isoformat())
        self._data.grid(row=6, column=1, padx=(6, 20), pady=(0, 10), sticky="ew")

        ctk.CTkLabel(uc, text="Note", font=FONT_PICCOLO,
                     text_color=COLORI["testo_grigio"]).grid(
            row=7, column=0, columnspan=2, padx=20, pady=(0, 2), sticky="w")
        self._note = ctk.CTkTextbox(uc, font=FONT_NORMALE, height=70)
        self._note.grid(row=8, column=0, columnspan=2, padx=20, pady=(0, 14), sticky="ew")

        self._btn_up = ctk.CTkButton(uc, text="⬆️  Carica",
                                      font=("Segoe UI", 13, "bold"), height=44,
                                      fg_color=COLORI["accent_bright"], hover_color="#c73652",
                                      command=self._carica)
        self._btn_up.grid(row=9, column=0, columnspan=2, padx=20, pady=(0, 20), sticky="ew")

        self._stato = ctk.CTkLabel(uc, text="", font=FONT_PICCOLO,
                                    text_color=COLORI["verde_ok"])
        self._stato.grid(row=10, column=0, columnspan=2, pady=(0, 10))

    def _combo_row(self, parent, lbl, vals, base_row, col):
        px = (20, 6) if col == 0 else (6, 20)
        ctk.CTkLabel(parent, text=lbl, font=FONT_PICCOLO,
                     text_color=COLORI["testo_grigio"]).grid(
            row=base_row, column=col, padx=px, pady=(0, 2), sticky="w")
        c = ctk.CTkComboBox(parent, values=vals, font=FONT_NORMALE, height=34, state="readonly")
        c.set(vals[0])
        c.grid(row=base_row + 1, column=col, padx=px, pady=(0, 10), sticky="ew")
        return c

    def _ricarica_pazienti(self, *_):
        righe = db.cerca_pazienti(self._cerca.get())
        for w in self._lista.winfo_children():
            w.destroy()
        for i, r in enumerate(righe):
            sel = (r["id"] == self._paz_id)
            ctk.CTkButton(self._lista, text=f"{r['cognome']} {r['nome']}",
                          font=FONT_PICCOLO, height=30,
                          fg_color=COLORI["accent"] if sel else COLORI["sfondo_entry"],
                          anchor="w",
                          command=lambda rid=r["id"], rn=f"{r['cognome']} {r['nome']}":
                              self._set_paz(rid, rn)).grid(
                row=i, column=0, padx=4, pady=2, sticky="ew")

    def _set_paz(self, pid, nome):
        self._paz_id = pid
        self._lbl_sel.configure(text=f"✅ {nome}", text_color=COLORI["verde_ok"])
        self._ricarica_pazienti()

    def imposta_paziente(self, pid):
        r = db.get_paziente_by_id(pid)
        if r:
            self._set_paz(pid, f"{r['cognome']} {r['nome']}")

    def _scegli(self):
        path = filedialog.askopenfilename(
            filetypes=[("Immagini", "*.jpg *.jpeg *.png *.bmp *.tiff *.webp")])
        if not path:
            return
        self._file = Path(path)
        thumb = _crea_miniatura(self._file, (320, 200))
        if thumb:
            self._prev_img = thumb
            self._prev.configure(image=thumb, text="")
        else:
            self._prev.configure(text="⚠️ File non leggibile", image=None)

    def _carica(self):
        if not self._paz_id:
            messagebox.showwarning("Paziente mancante", "Seleziona un paziente.")
            return
        if not self._file:
            messagebox.showwarning("File mancante", "Scegli un'immagine.")
            return
        try:
            ds = date.fromisoformat(self._data.get().strip())
        except ValueError:
            messagebox.showwarning("Data non valida", "Formato: AAAA-MM-GG")
            return
        self._btn_up.configure(state="disabled", text="⏳…")

        def _job():
            try:
                fid = db.upload_foto(self._paz_id, self._file, ds,
                                     self._c_dente.get(), self._c_branca.get(),
                                     self._c_fase.get(),
                                     self._note.get("1.0", "end").strip())
                self.after(0, self._ok, fid)
            except Exception as e:
                self.after(0, self._err, str(e))

        threading.Thread(target=_job, daemon=True).start()

    def _ok(self, fid):
        self._btn_up.configure(state="normal", text="⬆️  Carica")
        self._file = None
        self._prev.configure(image=None, text="📂  Clicca per scegliere")
        self._note.delete("1.0", "end")
        self._stato.configure(text=f"✅ ID {fid}", text_color=COLORI["verde_ok"])

    def _err(self, msg):
        self._btn_up.configure(state="normal", text="⬆️  Carica")
        self._stato.configure(text=f"❌ {msg}", text_color=COLORI["accent_bright"])



# ===========================================================================
# FINESTRA MODALE: DETTAGLIO FOTO
# ===========================================================================

class DettaglioFoto(ctk.CTkToplevel):
    """
    Mostra l'immagine a dimensione maggiore con i metadati clinici sul lato.
    Aperta con un singolo click sulla thumbnail in Dashboard.
    Doppio click sulla thumbnail apre invece il ViewerFoto zoomabile.

    Args:
        on_modifica_tag:  callback per aprire la scheda modifica tag
        tutti_risultati:  lista completa dei risultati correnti (per il viewer)
        indice:           indice di questa foto nella lista (per il viewer)
    """

    def __init__(self, master, percorso: Path, row,
                 on_modifica_tag=None, tutti_risultati=None, indice=0):
        super().__init__(master)
        self.title(f"📷  {row['cognome']} {row['nome']}  —  {Path(row['percorso_file']).name}")
        self.geometry("860x580")
        self.resizable(True, True)
        # ── Porta la finestra in primo piano (fix "apre in background") ──
        self.after(50, self._porta_in_primo_piano)

        self._on_modifica_tag   = on_modifica_tag
        self._tutti_risultati   = tutti_risultati or []
        self._indice            = indice
        self._img_ref           = None
        self._build_ui(percorso, row)

    def _porta_in_primo_piano(self):
        """Forza la finestra in cima a tutte le altre."""
        self.lift()
        self.focus_force()
        self.attributes("-topmost", True)
        self.after(200, lambda: self.attributes("-topmost", False))

    def _build_ui(self, percorso: Path, r):
        self.grid_columnconfigure(0, weight=3)
        self.grid_columnconfigure(1, weight=2)
        self.grid_rowconfigure(0, weight=1)

        # ── Immagine ──────────────────────────────────────────────────
        img_frame = ctk.CTkFrame(self, fg_color=COLORI["card_bg"], corner_radius=12)
        img_frame.grid(row=0, column=0, padx=(14, 6), pady=14, sticky="nsew")
        img_frame.grid_columnconfigure(0, weight=1)
        img_frame.grid_rowconfigure(0, weight=1)

        img = _crea_miniatura(percorso, size=(520, 440))
        if img is None:
            img = _placeholder_image((520, 440))
        self._img_ref = img
        ctk.CTkLabel(img_frame, image=img, text="").grid(
            row=0, column=0, padx=10, pady=10, sticky="nsew")

        # Hint doppio click
        ctk.CTkLabel(img_frame,
                     text="Doppio click per aprire il viewer zoomabile",
                     font=("Segoe UI", 8),
                     text_color=COLORI["testo_grigio"]).grid(
            row=1, column=0, pady=(0, 8))
        img_frame.bind("<Double-Button-1>",
                       lambda e: ViewerFoto(self, self._tutti_risultati, self._indice))

        # ── Metadati ──────────────────────────────────────────────────
        meta = ctk.CTkFrame(self, fg_color=COLORI["card_bg"], corner_radius=12)
        meta.grid(row=0, column=1, padx=(6, 14), pady=14, sticky="nsew")
        meta.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(meta, text="Metadati Clinici",
                     font=FONT_SEZIONE).pack(padx=16, pady=(16, 12), anchor="w")

        dati = [
            ("Paziente",  f"{r['cognome']} {r['nome']}"),
            ("Dente",     r["dente"]       or "—"),
            ("Branca",    r["branca"]      or "—"),
            ("Fase",      r["fase"]        or "—"),
            ("Data",      r["data_scatto"] or "—"),
            ("Note",      r["note"]        or "—"),
            ("File",      Path(r["percorso_file"]).name),
            ("ID Foto",   str(r["id"])),
        ]
        for label, valore in dati:
            row_f = ctk.CTkFrame(meta, fg_color="transparent")
            row_f.pack(fill="x", padx=16, pady=2)
            ctk.CTkLabel(row_f, text=label + ":",
                         font=FONT_PICCOLO,
                         text_color=COLORI["testo_grigio"],
                         width=64, anchor="w").pack(side="left")
            ctk.CTkLabel(row_f, text=str(valore),
                         font=FONT_NORMALE, wraplength=210,
                         anchor="w").pack(side="left", padx=(4, 0))

        # ── Pulsanti ──────────────────────────────────────────────────
        ctk.CTkButton(meta,
                      text="🔍  Apri Viewer",
                      font=FONT_NORMALE, height=34,
                      fg_color=COLORI["accent"],
                      command=lambda: ViewerFoto(self, self._tutti_risultati, self._indice),
                      ).pack(padx=16, pady=(14, 4), fill="x")

        if self._on_modifica_tag:
            ctk.CTkButton(meta,
                          text="✏️  Modifica Tag",
                          font=FONT_NORMALE, height=34,
                          fg_color=COLORI["verde_ok"], hover_color="#388e3c",
                          command=lambda: (self.destroy(),
                                          self._on_modifica_tag(r["id"])),
                          ).pack(padx=16, pady=(4, 4), fill="x")

        ctk.CTkButton(meta,
                      text="📄  Esporta PDF",
                      font=FONT_NORMALE, height=34,
                      fg_color=COLORI["pdf_btn"], hover_color="#4a0072",
                      command=lambda: _esporta_pdf_con_feedback(self, r["paziente_id"]),
                      ).pack(padx=16, pady=(4, 4), fill="x")

        ctk.CTkButton(meta,
                      text="Chiudi",
                      font=FONT_NORMALE, height=34,
                      fg_color="transparent", border_width=1,
                      command=self.destroy,
                      ).pack(padx=16, pady=(4, 16), fill="x")

# ===========================================================================
# FRAME: DASHBOARD con viewer integrato
# ===========================================================================

class DashboardFrame(ctk.CTkFrame):
    COLS = 4
    THUMB = (200, 150)

    def __init__(self, master, on_modifica_tag=None, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self._on_modifica_tag = on_modifica_tag
        self._thumbs: list = []
        self._card_labels: dict = {}   # idx → CTkLabel immagine
        self._loader = None
        self._risultati: list = []
        self._build_ui()
        self.esegui_ricerca()

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        fc = ctk.CTkFrame(self, fg_color=COLORI["card_bg"], corner_radius=12)
        fc.grid(row=0, column=0, padx=0, pady=(0, 8), sticky="ew")
        fc.grid_columnconfigure((0, 1, 2, 3, 4), weight=1)

        ctk.CTkLabel(fc, text="🔍  Filtri", font=FONT_SEZIONE).grid(
            row=0, column=0, columnspan=5, padx=20, pady=(16, 8), sticky="w")

        specs = [
            ("Paziente",   "_fp", None),
            ("Dente",      "_fd", ["(tutti)"] + db.DENTI_FDI),
            ("Branca",     "_fb", ["(tutte)"] + db.BRANCHE),
            ("Fase",       "_ff", ["(tutte)"] + db.FASI),
        ]
        for col, (lbl, attr, vals) in enumerate(specs):
            ctk.CTkLabel(fc, text=lbl, font=FONT_PICCOLO,
                         text_color=COLORI["testo_grigio"]).grid(
                row=1, column=col, padx=(20 if col == 0 else 6, 6), pady=(0, 2), sticky="w")
            if vals is None:
                w = ctk.CTkEntry(fc, placeholder_text="Cognome…",
                                 font=FONT_NORMALE, height=32)
            else:
                w = ctk.CTkComboBox(fc, values=vals, font=FONT_NORMALE,
                                    height=32, state="readonly")
                w.set(vals[0])
            w.grid(row=2, column=col, padx=(20 if col == 0 else 6, 6),
                   pady=(0, 12), sticky="ew")
            setattr(self, attr, w)

        br = ctk.CTkFrame(fc, fg_color="transparent")
        br.grid(row=1, column=4, rowspan=2, padx=(6, 20), pady=(0, 12), sticky="s")
        ctk.CTkButton(br, text="Cerca",  font=FONT_PICCOLO, width=72, height=28,
                      command=self.esegui_ricerca).pack(side="left", padx=(0, 3))
        ctk.CTkButton(br, text="Reset",  font=FONT_PICCOLO, width=64, height=28,
                      fg_color="transparent", border_width=1,
                      command=self._reset).pack(side="left", padx=(0, 3))
        ctk.CTkButton(br, text="📄 PDF", font=FONT_PICCOLO, width=68, height=28,
                      fg_color=COLORI["pdf_btn"], hover_color="#4a0072",
                      command=self._pdf).pack(side="left")

        self._lbl_n = ctk.CTkLabel(fc, text="", font=FONT_PICCOLO,
                                    text_color=COLORI["testo_grigio"])
        self._lbl_n.grid(row=3, column=0, columnspan=5, padx=20, pady=(0, 10), sticky="w")

        self._galleria = ctk.CTkScrollableFrame(self, fg_color=COLORI["card_bg"],
                                                corner_radius=12)
        self._galleria.grid(row=1, column=0, sticky="nsew")
        for c in range(self.COLS):
            self._galleria.grid_columnconfigure(c, weight=1)

    def _get(self, w) -> Optional[str]:
        v = w.get().strip()
        return None if (not v or v.startswith("(")) else v

    def _reset(self):
        self._fp.delete(0, "end")
        self._fd.set("(tutti)")
        self._fb.set("(tutte)")
        self._ff.set("(tutte)")
        self.esegui_ricerca()

    def esegui_ricerca(self):
        paz_testo = self._fp.get().strip()
        paz_id = None
        if paz_testo:
            found = db.cerca_pazienti(paz_testo)
            if len(found) == 1:
                paz_id = found[0]["id"]
            elif not found:
                self._svuota()
                self._lbl_n.configure(text="Nessun paziente trovato.")
                return

        self._risultati = list(db.cerca_foto(
            paziente_id=paz_id,
            dente=self._get(self._fd),
            branca=self._get(self._fb),
            fase=self._get(self._ff),
        ))
        n = len(self._risultati)
        self._lbl_n.configure(
            text=f"{n} foto trovata/e." if n else "Nessuna foto trovata.")
        self._ridisegna()

    def _pdf(self):
        if not self._risultati:
            messagebox.showinfo("PDF", "Nessuna foto da esportare.")
            return
        paz_ids = list({r["paziente_id"] for r in self._risultati})
        if len(paz_ids) > 1:
            if not messagebox.askyesno("PDF multipaziente",
                                        f"{len(paz_ids)} pazienti. Generare un PDF per ognuno?"):
                return
        for pid in paz_ids:
            _esporta_pdf_con_feedback(self, pid)

    def _svuota(self):
        # Ferma eventuale loader precedente
        if hasattr(self, "_loader") and self._loader:
            self._loader.stop()
            self._loader = None
        for w in self._galleria.winfo_children():
            w.destroy()
        self._thumbs.clear()
        self._card_labels.clear()

    def _ridisegna(self):
        self._svuota()
        if not self._risultati:
            ctk.CTkLabel(self._galleria, text="Nessuna corrispondenza.",
                         font=FONT_PICCOLO,
                         text_color=COLORI["testo_grigio"]).grid(
                row=0, column=0, columnspan=self.COLS, pady=40)
            return

        # Prima costruisce le card con placeholder
        for idx, r in enumerate(self._risultati):
            self._card(idx // self.COLS, idx % self.COLS, r, idx)

        # Poi carica le miniature in background
        from thumbnail_cache import GalleryLoader
        self._loader = GalleryLoader(
            self._galleria,
            self._risultati,
            size=self.THUMB,
            on_thumbnail_ready=self._aggiorna_thumb,
        )
        self._loader.start()

    def _aggiorna_thumb(self, idx: int, thumb: "ctk.CTkImage"):
        """Riceve la miniatura dal loader e aggiorna il label corrispondente."""
        if idx in self._card_labels:
            try:
                lbl = self._card_labels[idx]
                self._thumbs.append(thumb)   # anti-GC
                lbl.configure(image=thumb)
            except Exception:
                pass

    def _card(self, row, col, r, idx):
        card = ctk.CTkFrame(self._galleria, fg_color=COLORI["sfondo_entry"],
                            corner_radius=10)
        card.grid(row=row, column=col, padx=8, pady=8, sticky="nsew")
        card.grid_columnconfigure(0, weight=1)

        # Placeholder immediato — la vera miniatura arriva dal GalleryLoader
        placeholder = _placeholder_image(self.THUMB)
        self._thumbs.append(placeholder)

        img_lbl = ctk.CTkLabel(card, image=placeholder, text="", cursor="hand2")
        img_lbl.grid(row=0, column=0, padx=6, pady=(8, 4), sticky="ew")
        self._card_labels[idx] = img_lbl   # store per aggiornamento asincrono

        # Click → dettaglio metadati; doppio click → viewer zoomabile
        img_lbl.bind("<Button-1>",
                     lambda e, rr=r, ix=idx: DettaglioFoto(self, db.get_percorso_assoluto(rr), rr,
                                                            on_modifica_tag=self._on_modifica_tag,
                                                            tutti_risultati=self._risultati,
                                                            indice=ix))
        img_lbl.bind("<Double-Button-1>",
                     lambda e, ix=idx: ViewerFoto(self, self._risultati, ix))

        tr = ctk.CTkFrame(card, fg_color="transparent")
        tr.grid(row=1, column=0, padx=6, pady=2, sticky="ew")
        _badge(tr, r["branca"] or "—", COLORI["accent"])
        _badge(tr, r["fase"]   or "—", COLORI["accent_bright"])

        for ri, (ico, val) in enumerate([
            ("🦷", r["dente"] or "—"),
            ("👤", f"{r['cognome']} {r['nome']}"),
            ("📅", r["data_scatto"] or "—"),
        ], start=2):
            ctk.CTkLabel(card, text=f"{ico} {val}", font=FONT_PICCOLO,
                         text_color=COLORI["testo_grigio"],
                         anchor="w").grid(row=ri, column=0, padx=8, pady=1, sticky="w")

        # Badge ID + link modifica
        bottom = ctk.CTkFrame(card, fg_color="transparent")
        bottom.grid(row=5, column=0, padx=8, pady=(0, 8), sticky="ew")
        ctk.CTkLabel(bottom, text=f"ID #{r['id']}", font=("Segoe UI", 8),
                     text_color=COLORI["testo_grigio"]).pack(side="left")
        ctk.CTkButton(bottom, text="✏️", width=28, height=20,
                      font=("Segoe UI", 9),
                      fg_color="transparent",
                      command=lambda rid=r["id"]:
                          self._on_modifica_tag(rid) if self._on_modifica_tag else None
                      ).pack(side="right")


# ===========================================================================
# APPLICAZIONE PRINCIPALE
# ===========================================================================

class App(ctk.CTk):
    VOCI_NAV = [
        ("📋  Dashboard",    "dashboard"),
        ("👤  Pazienti",     "pazienti"),
        ("⬆️  Upload Foto",  "upload"),
        ("📦  Import Massivo","import"),
        ("📊  Statistiche",  "statistiche"),
        ("✏️  Modifica Tag",  "modifica_tag"),
        ("💾  Backup",       "backup"),
        ("📹  Webcam",       "webcam"),
        ("🔄  Before/After", "before_after"),
        ("📧  Email",        "email"),
        ("📅  Timeline",     "timeline"),
        ("👥  Utenti",       "utenti"),     # solo admin
    ]

    def __init__(self):
        super().__init__()
        db.init_db()
        init_auth_db()
        self.title("DentalPhoto — Gestione Fotografie Cliniche")
        self.geometry("1240x780")
        self.minsize(960, 600)
        self._pagina = ""
        self._frames: dict = {}
        self._paz_upload: Optional[int] = None
        self._foto_mod: Optional[int] = None
        self._lock_aperto = False
        self._build_layout()
        self._naviga("dashboard")
        self._avvia_timer_lock()
        # Propaga l'attività a SessioneUtente ad ogni interazione
        self.bind_all("<Motion>",   lambda e: SessioneUtente.registra_attivita())
        self.bind_all("<KeyPress>", lambda e: SessioneUtente.registra_attivita())

    # ------------------------------------------------------------------

    def _build_layout(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        sb = ctk.CTkFrame(self, width=228, corner_radius=0,
                          fg_color=COLORI["sidebar_bg"])
        sb.grid(row=0, column=0, sticky="nsew")
        sb.grid_propagate(False)
        sb.grid_columnconfigure(0, weight=1)
        sb.grid_rowconfigure(10, weight=1)

        # ── Logo ──
        lf = ctk.CTkFrame(sb, fg_color="transparent")
        lf.grid(row=0, column=0, padx=16, pady=(20, 6), sticky="ew")
        ctk.CTkLabel(lf, text="🦷", font=("Segoe UI", 30)).pack()
        ctk.CTkLabel(lf, text="DentalPhoto",
                     font=("Segoe UI", 15, "bold"),
                     text_color=COLORI["testo_chiaro"]).pack()

        # Badge utente loggato
        self._lbl_utente_badge = ctk.CTkLabel(
            sb,
            text=f"👤  {SessioneUtente.nome_display()}",
            font=("Segoe UI", 9),
            fg_color=COLORI["nav_active"],
            corner_radius=8,
            text_color=COLORI["testo_grigio"],
            padx=8, pady=4,
        )
        self._lbl_utente_badge.grid(row=1, column=0, padx=12, pady=(0, 6), sticky="ew")

        ctk.CTkFrame(sb, height=1, fg_color=COLORI["sidebar_border"]).grid(
            row=2, column=0, padx=14, pady=(0, 6), sticky="ew")

        self._nav_btns: dict = {}
        for i, (lbl, key) in enumerate(self.VOCI_NAV, start=3):
            # Nascondi "Utenti" ai non-admin
            if key == "utenti" and not SessioneUtente.is_admin():
                continue
            b = ctk.CTkButton(sb, text=lbl, font=FONT_NORMALE, height=40, anchor="w",
                              fg_color="transparent", hover_color=COLORI["sidebar_hover"],
                              corner_radius=8, border_spacing=10,
                              command=lambda k=key: self._naviga(k))
            b.grid(row=i, column=0, padx=8, pady=2, sticky="ew")
            self._nav_btns[key] = b

        # Bottom bar
        ctk.CTkFrame(sb, height=1, fg_color=COLORI["sidebar_border"]).grid(
            row=14, column=0, padx=14, pady=(0, 6), sticky="ew")

        # Riga bottoni bottom
        bot = ctk.CTkFrame(sb, fg_color="transparent")
        bot.grid(row=15, column=0, padx=8, pady=(0, 4), sticky="ew")
        bot.grid_columnconfigure(0, weight=1)

        ctk.CTkButton(
            bot, text="⚡ Backup",
            font=("Segoe UI", 9, "bold"), height=28,
            fg_color=COLORI["backup_btn"], hover_color="#a33800",
            command=self._backup_rapido,
        ).grid(row=0, column=0, padx=(0, 3), sticky="ew")

        ctk.CTkButton(
            bot, text="🔒",
            font=("Segoe UI", 12), height=28, width=34,
            fg_color=COLORI["lock_btn"], hover_color="#0f2a4a",
            command=self._blocca_sessione,
        ).grid(row=0, column=1)

        ctk.CTkButton(
            bot, text="⏻ Logout",
            font=("Segoe UI", 9), height=28,
            fg_color="transparent", border_width=1,
            border_color=COLORI["sidebar_border"],
            text_color=COLORI["testo_grigio"],
            hover_color=COLORI["sidebar_hover"],
            command=self._logout,
        ).grid(row=1, column=0, columnspan=2, pady=(3, 0), sticky="ew")

        ctk.CTkLabel(sb, text="Tema", font=("Segoe UI", 9),
                     text_color=COLORI["testo_grigio"]).grid(
            row=16, column=0, padx=14, pady=(6, 2), sticky="w")
        ctk.CTkOptionMenu(sb, values=["Dark", "Light", "System"],
                          font=("Segoe UI", 9), height=26,
                          command=lambda t: ctk.set_appearance_mode(t.lower())).grid(
            row=17, column=0, padx=8, pady=(0, 14), sticky="ew")

        # Content area
        self._content = ctk.CTkFrame(self, fg_color="transparent")
        self._content.grid(row=0, column=1, padx=16, pady=16, sticky="nsew")
        self._content.grid_columnconfigure(0, weight=1)
        self._content.grid_rowconfigure(1, weight=1)

        self._lbl_titolo = ctk.CTkLabel(self._content, text="", font=FONT_TITOLO)
        self._lbl_titolo.grid(row=0, column=0, pady=(0, 12), sticky="w")

        self._fc = ctk.CTkFrame(self._content, fg_color="transparent")
        self._fc.grid(row=1, column=0, sticky="nsew")
        self._fc.grid_columnconfigure(0, weight=1)
        self._fc.grid_rowconfigure(0, weight=1)

    # ------------------------------------------------------------------

    def _naviga(self, key: str):
        if key == self._pagina:
            return
        # Controllo permessi: operatori non possono accedere a backup/utenti
        if SessioneUtente.corrente and not SessioneUtente.ha_permesso(key):
            messagebox.showwarning(
                "Accesso negato",
                f"Il tuo ruolo non consente l'accesso a questa sezione.",
                parent=self)
            return
        self._pagina = key
        for k, b in self._nav_btns.items():
            if k == key:
                b.configure(fg_color=COLORI["nav_active"],
                            text_color=COLORI["testo_chiaro"],
                            border_width=0)
            else:
                b.configure(fg_color="transparent",
                            text_color=COLORI["testo_grigio"],
                            border_width=0)

        titoli = {
            "dashboard":   "📋  Dashboard & Ricerca",
            "pazienti":    "👤  Gestione Pazienti",
            "upload":      "⬆️  Upload Fotografia",
            "import":      "📦  Import Massivo",
            "statistiche": "📊  Statistiche Cliniche",
            "modifica_tag": "✏️  Modifica Tag Fotografie",
            "backup":      "💾  Backup & Ripristino",
            "webcam":      "📹  Acquisizione Webcam",
            "utenti":      "👥  Gestione Utenti",
            "before_after": "🔄  Confronto Before/After",
            "email":        "📧  Invio Email Dossier",
            "timeline":    "📅  Timeline Paziente",
        }
        self._lbl_titolo.configure(text=titoli.get(key, ""))

        if key not in self._frames:
            self._frames[key] = self._build_frame(key)

        for f in self._frames.values():
            f.grid_remove()
        self._frames[key].grid(row=0, column=0, sticky="nsew")

        # Aggiornamenti contestuali
        if key == "pazienti":
            self._frames["pazienti"].aggiorna_lista()
        elif key == "dashboard":
            self._frames["dashboard"].esegui_ricerca()
        elif key == "statistiche":
            self._frames["statistiche"].aggiorna_tutto()
        elif key == "modifica_tag":
            if self._foto_mod is not None:
                self._frames["modifica_tag"].preimposta_id(self._foto_mod)
                self._foto_mod = None
        elif key == "upload" and self._paz_upload:
            self._frames["upload"].imposta_paziente(self._paz_upload)
            self._paz_upload = None

    def _build_frame(self, key: str) -> ctk.CTkFrame:
        if key == "dashboard":
            return DashboardFrame(self._fc, on_modifica_tag=self._goto_modifica)
        if key == "pazienti":
            return PazientiFrame(self._fc, on_paziente_selezionato=self._goto_upload)
        if key == "upload":
            return UploadFrame(self._fc)
        if key == "import":
            return BulkImportFrame(self._fc)
        if key == "statistiche":
            return StatisticheFrame(self._fc)
        if key == "backup":
            return BackupRestoreFrame(self._fc)
        if key == "modifica_tag":
            return ModificaTagFrame(self._fc)
        if key == "webcam":
            return WebcamFrame(self._fc)
        if key == "utenti":
            return GestioneUtentiFrame(self._fc)
        if key == "before_after":
            return BeforeAfterFrame(self._fc)
        if key == "email":
            return EmailFrame(self._fc)
        if key == "timeline":
            return TimelineFrame(self._fc)
        raise ValueError(key)

    def _goto_upload(self, pid: int):
        self._paz_upload = pid
        self._naviga("upload")

    def _goto_modifica(self, foto_id: int):
        self._foto_mod = foto_id
        self._naviga("modifica_tag")

    def _avvia_timer_lock(self):
        """Controlla ogni 30s se la sessione è scaduta per inattività."""
        from auth import INATTIVITA_MIN
        if INATTIVITA_MIN > 0 and not self._lock_aperto:
            if SessioneUtente.corrente and SessioneUtente.is_scaduta():
                self._blocca_sessione()
        self.after(30_000, self._avvia_timer_lock)

    def _blocca_sessione(self):
        if self._lock_aperto:
            return
        self._lock_aperto = True
        def on_sblocco(logout=False):
            self._lock_aperto = False
            if logout:
                self._logout()
        LockScreen(self, on_sblocco=on_sblocco)

    def _logout(self):
        SessioneUtente.logout()
        self.destroy()
        # Riavvia il login screen
        import subprocess, sys
        subprocess.Popen([sys.executable, __file__])

    def _backup_rapido(self):
        """Backup immediato nella cartella dell'app senza dialogo."""
        popup = ctk.CTkToplevel(self)
        popup.title("Backup rapido…")
        popup.geometry("300x100")
        popup.resizable(False, False)
        popup.grab_set()
        ctk.CTkLabel(popup, text="⏳  Backup in corso…", font=FONT_NORMALE).pack(expand=True)
        pb = ctk.CTkProgressBar(popup, mode="indeterminate")
        pb.pack(padx=20, fill="x", pady=(0, 16))
        pb.start()
        result: dict = {}

        def _job():
            try:
                result["path"] = esegui_backup(db.APP_DIR / "backups")
            except Exception as e:
                result["err"] = str(e)

        def _done():
            popup.destroy()
            if "err" in result:
                messagebox.showerror("Backup fallito", result["err"])
            else:
                messagebox.showinfo("Backup completato",
                                    f"✅  Salvato in:\n{result['path']}")

        threading.Thread(
            target=lambda: (_job(), self.after(0, _done)),
            daemon=True,
        ).start()


# ===========================================================================
# ENTRY POINT
# ===========================================================================

def _fix_scrollwheel(root):
    """
    Fix per il bug di CTkScrollableFrame su Windows:
    la rotella del mouse non scrolla se il cursore è sopra un widget figlio.
    """
    import platform
    if platform.system() != "Windows":
        return

    def _on_wheel(event):
        widget = event.widget
        # Risale la gerarchia finché trova un CTkScrollableFrame
        w = widget
        while w:
            if isinstance(w, ctk.CTkScrollableFrame):
                # Scrolla il canvas interno
                try:
                    w._parent_canvas.yview_scroll(
                        int(-1 * (event.delta / 120)), "units")
                except Exception:
                    pass
                return
            try:
                w = w.master
            except Exception:
                break

    root.bind_all("<MouseWheel>", _on_wheel, add="+")


if __name__ == "__main__":
    # ── Login screen ────────────────────────────────────────────────
    from ui_login import LoginScreen
    login = LoginScreen()
    login.mainloop()

    if not login.login_riuscito:
        import sys; sys.exit(0)

    # ── App principale ──────────────────────────────────────────────
    app = App()
    _fix_scrollwheel(app)
    app.mainloop()

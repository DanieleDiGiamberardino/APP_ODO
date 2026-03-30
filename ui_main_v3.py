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
import sys
import tkinter as tk
from tkinter import filedialog, messagebox
from watchdog_monitor import CameraWatchdog
import customtkinter as ctk
from PIL import Image, ImageTk, ImageOps
import threading
from pathlib import Path
from typing import Optional
from theme import MODERN_THEME, FONT_TITLE, FONT_BODY, _SidebarMixin

# Drag & Drop — opzionale (richiede: pip install tkinterdnd2)
try:
    from tkinterdnd2 import TkinterDnD, DND_FILES
    _DND_OK = True
except ImportError:
    _DND_OK = False

import database as db
from auth import SessioneUtente, init_auth_db
from ui_login import LockScreen, GestioneUtentiFrame
from thumbnail_cache import GalleryLoader
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

# DEBUG_MODE è True se avvii lo script, False se è un file .exe compilato
DEBUG_MODE = not getattr(sys, 'frozen', False)
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


# ===========================================================================
# TOAST NOTIFICATION SYSTEM
# ===========================================================================

class _ToastWidget(ctk.CTkFrame):
    """Singola notifica toast — viene creata da ToastManager."""

    COLORI_TIPO = {
        "success": ("#1a4d2e", "#3ecf6e"),   # (sfondo, bordo/icona)
        "error":   ("#4d1a1a", "#e94560"),
        "info":    ("#0f2a4a", "#4a9eff"),
        "warning": ("#4d3a0a", "#ffb347"),
    }
    ICONE = {"success": "✅", "error": "❌", "info": "ℹ️", "warning": "⚠️"}

    def __init__(self, master, messaggio: str, tipo: str, durata_ms: int,
                 on_chiudi):
        bg, border = self.COLORI_TIPO.get(tipo, self.COLORI_TIPO["info"])
        super().__init__(master, fg_color=bg, corner_radius=10,
                         border_width=1, border_color=border)
        self._on_chiudi = on_chiudi
        self._dopo_id = None

        inner = ctk.CTkFrame(self, fg_color="transparent")
        inner.pack(padx=12, pady=9)

        ctk.CTkLabel(inner, text=self.ICONE.get(tipo, "ℹ️"),
                     font=("Segoe UI", 13), fg_color="transparent").pack(
            side="left", padx=(0, 6))
        ctk.CTkLabel(inner, text=messaggio,
                     font=("Segoe UI", 11), wraplength=280,
                     justify="left", fg_color="transparent").pack(side="left")

        # Chiudi manuale
        ctk.CTkButton(inner, text="×", width=18, height=18,
                      font=("Segoe UI", 12), fg_color="transparent",
                      hover_color=border,
                      command=self._chiudi).pack(side="left", padx=(8, 0))

        self._dopo_id = self.after(durata_ms, self._chiudi)

    def _chiudi(self):
        if self._dopo_id:
            try:
                self.after_cancel(self._dopo_id)
            except Exception:
                pass
        self._on_chiudi(self)

    def destroy(self):
        if self._dopo_id:
            try:
                self.after_cancel(self._dopo_id)
            except Exception:
                pass
        super().destroy()


class ToastManager:
    """
    Gestore centralisato delle notifiche toast.
    Uso: ToastManager.init(root)  →  poi ToastManager.mostra("testo", "success")
    """
    _root = None
    _toasts: list = []

    @classmethod
    def init(cls, root):
        cls._root = root
        cls._toasts = []

    @classmethod
    def mostra(cls, messaggio: str, tipo: str = "info", durata_ms: int = 3500):
        """
        Mostra una notifica non bloccante.
        tipo: "success" | "error" | "info" | "warning"
        """
        if cls._root is None:
            return
        toast = _ToastWidget(cls._root, messaggio, tipo, durata_ms,
                             cls._rimuovi)
        cls._toasts.append(toast)
        cls._riposiziona()

    @classmethod
    def _rimuovi(cls, toast):
        if toast in cls._toasts:
            cls._toasts.remove(toast)
        try:
            toast.place_forget()
            toast.destroy()
        except Exception:
            pass
        cls._riposiziona()

    @classmethod
    def _riposiziona(cls):
        """Ri-piazza i toast esistenti impilati in basso a destra."""
        cls._toasts = [t for t in cls._toasts
                       if t.winfo_exists() if not t._do_not_track
                       ] if False else [
            t for t in cls._toasts if t.winfo_exists()]
        y_offset = 44   # sopra la status bar
        for toast in reversed(cls._toasts):
            toast.update_idletasks()
            h = toast.winfo_reqheight() or 48
            toast.place(relx=1.0, rely=1.0, x=-14, y=-(y_offset), anchor="se")
            y_offset += h + 6


# ===========================================================================
# RICERCA GLOBALE  Ctrl+K
# ===========================================================================

class SpotlightSearch(ctk.CTkToplevel):
    """
    Popup di ricerca globale stile "command palette".

    Aperto con Ctrl+K dall'App principale.
    Cerca in tempo reale (debounce 200ms) su:
      - pazienti  (cognome / nome)
      - foto      (per paziente + dente + branca)

    Tastiera:
      ↑ / ↓    → naviga i risultati
      Invio    → apre il risultato selezionato
      Esc      → chiude

    Ogni risultato ha un'azione primaria:
      Paziente → naviga a Upload con quel paziente preselezionato
      Foto     → apre DettaglioFoto
    """

    _MAX_RISULTATI = 12
    _DEBOUNCE_MS   = 200

    # Colori interni (coerenti con COLORI della app)
    _C = {
        "bg":      "#0c1424",
        "input":   "#111827",
        "row":     "#0f1a2e",
        "row_sel": "#1a3050",
        "border":  "#1e3a5f",
        "accent":  "#2563eb",
        "testo":   "#e2e8f0",
        "sub":     "#64748b",
        "badge_p": "#0f3460",
        "badge_f": "#1a3a1a",
    }

    def __init__(self, master, on_apri_paziente=None, on_apri_foto=None):
        super().__init__(master)
        self._on_paz  = on_apri_paziente
        self._on_foto = on_apri_foto
        self._risultati: list = []   # lista di dict {tipo, label, sub, id, data}
        self._sel_idx   = -1
        self._db_id     = None       # debounce after-id
        self._row_btns: list = []    # widget righe risultato

        # Finestra
        self.configure(fg_color=self._C["bg"])
        self.overrideredirect(True)     # niente bordi OS
        self.attributes("-topmost", True)
        self.grab_set()

        W, H = 640, 420
        mx = master.winfo_x() + (master.winfo_width()  - W) // 2
        my = master.winfo_y() + (master.winfo_height() - H) // 3
        self.geometry(f"{W}x{H}+{mx}+{my}")

        self._build_ui()

        self.bind("<Escape>",  lambda e: self.destroy())
        self.bind("<Up>",      lambda e: self._muovi(-1))
        self.bind("<Down>",    lambda e: self._muovi(+1))
        self.bind("<Return>",  lambda e: self._apri_sel())
        # Click fuori → chiudi
        self.bind("<FocusOut>", self._on_focus_out)

        self._entry.focus_set()
        self._ricerca()   # mostra subito i risultati vuoti / recenti

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # Bordo esterno
        outer = ctk.CTkFrame(self, fg_color=self._C["bg"],
                              corner_radius=14,
                              border_width=1,
                              border_color=self._C["border"])
        outer.grid(row=0, column=0, rowspan=2, sticky="nsew",
                   padx=0, pady=0)
        outer.grid_columnconfigure(0, weight=1)
        outer.grid_rowconfigure(1, weight=1)

        # ── Barra di ricerca ─────────────────────────────────────────
        top = ctk.CTkFrame(outer, fg_color="transparent")
        top.grid(row=0, column=0, padx=0, pady=0, sticky="ew")
        top.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(top, text="🔍", font=("Segoe UI", 16),
                     fg_color="transparent",
                     text_color=self._C["sub"]).grid(
            row=0, column=0, padx=(18, 0), pady=16)

        self._entry = ctk.CTkEntry(
            top,
            font=("Segoe UI", 15),
            fg_color="transparent",
            border_width=0,
            corner_radius=0,
            placeholder_text="Cerca pazienti, foto…",
            placeholder_text_color=self._C["sub"],
            text_color=self._C["testo"],
            height=52,
        )
        self._entry.grid(row=0, column=1, sticky="ew", padx=(8, 0))
        self._entry.bind("<KeyRelease>", self._on_key)

        # Badge hint
        ctk.CTkLabel(top, text="ESC per chiudere",
                     font=("Segoe UI", 9),
                     fg_color="transparent",
                     text_color=self._C["sub"]).grid(
            row=0, column=2, padx=(0, 16))

        # Separatore
        ctk.CTkFrame(outer, height=1, fg_color=self._C["border"],
                     corner_radius=0).grid(
            row=1, column=0, sticky="ew", padx=0)

        # ── Risultati ────────────────────────────────────────────────
        self._scroll = ctk.CTkScrollableFrame(
            outer,
            fg_color="transparent",
            scrollbar_button_color=self._C["border"],
        )
        self._scroll.grid(row=2, column=0, sticky="nsew",
                          padx=6, pady=(6, 6))
        self._scroll.grid_columnconfigure(0, weight=1)

        # Footer
        footer = ctk.CTkFrame(outer, fg_color="transparent", height=28)
        footer.grid(row=3, column=0, sticky="ew", padx=16, pady=(0, 8))
        ctk.CTkLabel(footer,
                     text="↑↓ naviga   ↵ apri   Esc chiudi",
                     font=("Segoe UI", 9),
                     text_color=self._C["sub"],
                     fg_color="transparent").pack(side="left")
        self._lbl_count = ctk.CTkLabel(footer, text="",
                                        font=("Segoe UI", 9),
                                        text_color=self._C["sub"],
                                        fg_color="transparent")
        self._lbl_count.pack(side="right")

    # ------------------------------------------------------------------
    # Ricerca
    # ------------------------------------------------------------------

    def _on_key(self, event):
        # Frecce gestite dai bind globali
        if event.keysym in ("Up", "Down", "Return", "Escape"):
            return
        if self._db_id:
            try:
                self.after_cancel(self._db_id)
            except Exception:
                pass
        self._db_id = self.after(self._DEBOUNCE_MS, self._ricerca)

    def _ricerca(self):
        q = self._entry.get().strip()
        risultati = []

        def _fetch():
            try:
                # Pazienti
                paz = db.cerca_pazienti(q)[:self._MAX_RISULTATI // 2]
                for r in paz:
                    n_foto = db.conta_foto_per_paziente(r["id"])
                    risultati.append({
                        "tipo":   "paziente",
                        "label":  f"{r['cognome']} {r['nome']}",
                        "sub":    f"📞 {r['telefono'] or '—'}  ·  📷 {n_foto} foto",
                        "id":     r["id"],
                        "data":   r,
                    })
                # Foto (cerca per nome paziente o testo libero)
                foto = db.cerca_foto(
                    paziente_id=None,
                    dente=q or None,
                    branca=None, fase=None
                )[:self._MAX_RISULTATI // 2]
                # Se c'è query, cerca anche per cognome paziente nelle foto
                if q:
                    paz_match = db.cerca_pazienti(q)
                    for p in paz_match[:3]:
                        extra = db.cerca_foto(paziente_id=p["id"])[:3]
                        for f in extra:
                            if not any(x["tipo"] == "foto" and x["id"] == f["id"]
                                       for x in risultati):
                                foto.append(f)

                for f in foto[:self._MAX_RISULTATI // 2]:
                    risultati.append({
                        "tipo":  "foto",
                        "label": f"{f['cognome']} {f['nome']}  —  {f['dente'] or '?'}",
                        "sub":   f"📅 {f['data_scatto'] or '—'}  ·  {f['branca'] or ''}  ·  {f['fase'] or ''}",
                        "id":    f["id"],
                        "data":  f,
                    })

                self.after(0, lambda: self._mostra(risultati))
            except Exception:
                pass

        threading.Thread(target=_fetch, daemon=True).start()

    def _mostra(self, risultati: list):
        self._risultati = risultati
        self._sel_idx   = -1
        self._row_btns.clear()

        for w in self._scroll.winfo_children():
            w.destroy()

        if not risultati:
            ctk.CTkLabel(self._scroll,
                         text="Nessun risultato" if self._entry.get().strip()
                         else "Inizia a digitare…",
                         font=("Segoe UI", 12),
                         text_color=self._C["sub"],
                         fg_color="transparent").grid(
                row=0, column=0, pady=30)
            self._lbl_count.configure(text="")
            return

        sezione_corrente = None
        row_idx = 0
        for i, r in enumerate(risultati):
            # Intestazione sezione
            sez = "👤  Pazienti" if r["tipo"] == "paziente" else "📷  Foto"
            if sez != sezione_corrente:
                sezione_corrente = sez
                ctk.CTkLabel(self._scroll, text=sez,
                             font=("Segoe UI", 9, "bold"),
                             text_color=self._C["sub"],
                             fg_color="transparent",
                             anchor="w").grid(
                    row=row_idx, column=0,
                    padx=10, pady=(10 if row_idx > 0 else 4, 2),
                    sticky="w")
                row_idx += 1

            # Riga risultato
            riga = ctk.CTkFrame(self._scroll,
                                fg_color=self._C["row"],
                                corner_radius=8, cursor="hand2")
            riga.grid(row=row_idx, column=0, padx=4, pady=2, sticky="ew")
            riga.grid_columnconfigure(1, weight=1)

            # Badge tipo
            badge_col = self._C["badge_p"] if r["tipo"] == "paziente" else self._C["badge_f"]
            badge_ico = "👤" if r["tipo"] == "paziente" else "📷"
            ctk.CTkLabel(riga, text=badge_ico,
                         font=("Segoe UI", 14),
                         width=36, height=36,
                         corner_radius=8,
                         fg_color=badge_col).grid(
                row=0, column=0, rowspan=2, padx=(8, 6), pady=8)

            ctk.CTkLabel(riga, text=r["label"],
                         font=("Segoe UI", 12),
                         text_color=self._C["testo"],
                         anchor="w",
                         fg_color="transparent").grid(
                row=0, column=1, sticky="ew", padx=(0, 8), pady=(8, 1))

            ctk.CTkLabel(riga, text=r["sub"],
                         font=("Segoe UI", 10),
                         text_color=self._C["sub"],
                         anchor="w",
                         fg_color="transparent").grid(
                row=1, column=1, sticky="ew", padx=(0, 8), pady=(0, 8))

            # Freccia azione
            ctk.CTkLabel(riga, text="→",
                         font=("Segoe UI", 14),
                         text_color=self._C["sub"],
                         fg_color="transparent").grid(
                row=0, column=2, rowspan=2, padx=(0, 12))

            # Binding click e hover
            idx_cap = i
            for w in riga.winfo_children() + [riga]:
                w.bind("<Button-1>",
                       lambda e, ix=idx_cap: self._apri(ix))
                w.bind("<Enter>",
                       lambda e, f=riga, ix=idx_cap: self._hover(f, ix, True))
                w.bind("<Leave>",
                       lambda e, f=riga, ix=idx_cap: self._hover(f, ix, False))

            self._row_btns.append(riga)
            row_idx += 1

        n = len(risultati)
        self._lbl_count.configure(text=f"{n} risultat{'o' if n == 1 else 'i'}")

    # ------------------------------------------------------------------
    # Navigazione tastiera
    # ------------------------------------------------------------------

    def _muovi(self, delta: int):
        if not self._row_btns:
            return
        # Deseleziona precedente
        if 0 <= self._sel_idx < len(self._row_btns):
            self._row_btns[self._sel_idx].configure(fg_color=self._C["row"])
        self._sel_idx = max(0, min(self._sel_idx + delta,
                                    len(self._row_btns) - 1))
        self._row_btns[self._sel_idx].configure(fg_color=self._C["row_sel"])

    def _hover(self, frame, idx: int, entrata: bool):
        if idx != self._sel_idx:
            frame.configure(
                fg_color=self._C["row_sel"] if entrata else self._C["row"])

    def _apri_sel(self):
        if 0 <= self._sel_idx < len(self._risultati):
            self._apri(self._sel_idx)

    def _apri(self, idx: int):
        if idx >= len(self._risultati):
            return
        r = self._risultati[idx]
        self.destroy()
        if r["tipo"] == "paziente" and self._on_paz:
            self._on_paz(r["id"])
        elif r["tipo"] == "foto" and self._on_foto:
            self._on_foto(r["id"], r["data"])

    def _on_focus_out(self, event):
        # Chiudi solo se il focus va fuori dalla finestra spotlight
        try:
            fw = self.focus_get()
            if fw and str(fw).startswith(str(self)):
                return
        except Exception:
            pass
        self.after(100, self._check_close)

    def _check_close(self):
        try:
            if self.winfo_exists() and self.focus_get() is None:
                self.destroy()
        except Exception:
            pass


def _esporta_pdf_con_feedback(parent_widget, paziente_id: int,
                               filtri: Optional[dict] = None,
                               output_dir: Optional[Path] = None):
    if output_dir is None:
        cartella = filedialog.askdirectory(title="Cartella PDF",
                                           initialdir=str(db.APP_DIR))
        if not cartella:
            return
        output_dir = Path(cartella)

    ToastManager.mostra("⏳  Generazione PDF in corso…", "info", 8000)
    result: dict = {}

    def _job():
        try:
            result["path"] = genera_dossier_pdf(paziente_id, output_dir, filtri)
        except Exception as exc:
            result["error"] = str(exc)

    def _done():
        if "error" in result:
            ToastManager.mostra(f"Errore PDF: {result['error']}", "error", 6000)
        else:
            ToastManager.mostra("📄  PDF generato con successo", "success")

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
        self._debounce_id = None
        self._entry_cerca.bind("<KeyRelease>", self._debounce_ricerca)

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

    def _debounce_ricerca(self, event=None):
        """Ritarda la ricerca di 250ms dopo l'ultima pressione tasto."""
        if self._debounce_id:
            try:
                self.after_cancel(self._debounce_id)
            except Exception:
                pass
        self._debounce_id = self.after(250, self.aggiorna_lista)

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

# ===========================================================================
# FRAME: UPLOAD
# ===========================================================================

class UploadFrame(ctk.CTkFrame):
    # ── palette ───────────────────────────────────────────────────────────────
    C_BG        = "#080c18"
    C_PANEL     = "#0f1629"
    C_ACCENT    = "#0f3460"
    C_ACCENT_HO = "#1a4a80"
    C_BORDER    = "#1a2a4a"
    C_TEXT      = "#c0d4f0"
    C_MUTED     = "#4a6080"
    C_SUCCESS   = "#22c55e"
    C_DANGER    = "#e74c3c"

    # ── tag options ───────────────────────────────────────────────────────────
    DENTI  = [str(n) for n in range(11, 49) if n % 10 != 0 and n % 10 <= 8]
    BRANCHE = db.BRANCHE
    FASI   = db.FASI

    def __init__(self, master, paz_id_init=None, **kwargs):
        kwargs.setdefault("fg_color", self.C_BG)
        kwargs.setdefault("corner_radius", 0)
        super().__init__(master, **kwargs)

        self._paziente_id:   int | None  = paz_id_init
        self._paziente_info: dict        = {}
        self._file_path:     Path | None = None
        self._pil_img:       Image.Image | None = None
        self._prev_img:      ImageTk.PhotoImage | None = None   

        self._tag_dente  = tk.StringVar(value="")
        self._tag_branca = tk.StringVar(value="")
        self._tag_fase   = tk.StringVar(value="")
        self._note_text  = tk.StringVar(value="")

        self._build_layout()
        if paz_id_init:
            self.imposta_paziente(paz_id_init)

    def _build_layout(self):
        self.grid_columnconfigure(0, weight=3, minsize=280)
        self.grid_columnconfigure(1, weight=5)
        self.grid_rowconfigure(0, weight=1)
        self._build_left_panel()
        self._build_right_panel()

    def _build_left_panel(self):
        left = ctk.CTkFrame(self, fg_color=self.C_PANEL, corner_radius=12)
        left.grid(row=0, column=0, sticky="nsew", padx=(14, 6), pady=14)
        left.grid_rowconfigure(2, weight=1)
        left.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(left, text="👤  Paziente", font=ctk.CTkFont("Segoe UI", 14, weight="bold"), text_color=self.C_TEXT, anchor="w").grid(row=0, column=0, sticky="ew", padx=14, pady=(14, 6))

        search_row = ctk.CTkFrame(left, fg_color="transparent")
        search_row.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 6))
        search_row.grid_columnconfigure(0, weight=1)

        self._search_entry = ctk.CTkEntry(search_row, placeholder_text="🔍  Cerca nome, cognome o ID…", fg_color="#0a1428", border_color=self.C_BORDER, text_color=self.C_TEXT, font=ctk.CTkFont("Segoe UI", 12), height=36)
        self._search_entry.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self._search_entry.bind("<KeyRelease>", self._on_search)

        ctk.CTkButton(search_row, text="↺", width=34, height=36, fg_color=self.C_BORDER, hover_color=self.C_ACCENT, text_color=self.C_MUTED, font=ctk.CTkFont("Segoe UI", 14), command=self._reset_search).grid(row=0, column=1)

        self._results_scroll = ctk.CTkScrollableFrame(left, fg_color="#0a1020", scrollbar_button_color=self.C_ACCENT, scrollbar_button_hover_color=self.C_ACCENT_HO, corner_radius=8)
        self._results_scroll.grid(row=2, column=0, sticky="nsew", padx=10, pady=(0, 10))
        self._results_scroll.grid_columnconfigure(0, weight=1)

        self._sel_frame = ctk.CTkFrame(left, fg_color="#0a1428", corner_radius=8)
        self._sel_frame.grid(row=3, column=0, sticky="ew", padx=10, pady=(0, 14))
        self._sel_frame.grid_columnconfigure(0, weight=1)

        self._sel_label = ctk.CTkLabel(self._sel_frame, text="Nessun paziente selezionato", text_color=self.C_MUTED, font=ctk.CTkFont("Segoe UI", 11), anchor="w", wraplength=220)
        self._sel_label.grid(row=0, column=0, sticky="ew", padx=10, pady=8)

    def _build_right_panel(self):
        right = ctk.CTkFrame(self, fg_color=self.C_PANEL, corner_radius=12)
        right.grid(row=0, column=1, sticky="nsew", padx=(6, 14), pady=14)
        right.grid_rowconfigure(1, weight=1)
        right.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(right, text="📁  Carica Immagine", font=ctk.CTkFont("Segoe UI", 14, weight="bold"), text_color=self.C_TEXT, anchor="w").grid(row=0, column=0, sticky="ew", padx=14, pady=(14, 6))

        self._drop_canvas = tk.Canvas(right, bg="#08101e", highlightthickness=2, highlightbackground=self.C_BORDER, cursor="hand2")
        self._drop_canvas.grid(row=1, column=0, sticky="nsew", padx=14, pady=(0, 8))
        self._draw_drop_hint()

        if _DND_OK:
            self._drop_canvas.drop_target_register(DND_FILES)
            self._drop_canvas.dnd_bind("<<Drop>>", self._on_drop)

        self._drop_canvas.bind("<Button-1>", self._on_canvas_click)
        self._drop_canvas.bind("<Configure>", self._on_canvas_configure)

        self._build_tag_row(right)
        self._build_note_row(right)

        self._btn_save = ctk.CTkButton(right, text="💾  Salva nel Database", height=42, fg_color=self.C_ACCENT, hover_color=self.C_ACCENT_HO, text_color="white", font=ctk.CTkFont("Segoe UI", 13, weight="bold"), corner_radius=9, state="disabled", command=self._salva)
        self._btn_save.grid(row=4, column=0, sticky="ew", padx=14, pady=(4, 14))

    def _build_tag_row(self, parent):
        tag_frame = ctk.CTkFrame(parent, fg_color="transparent")
        tag_frame.grid(row=2, column=0, sticky="ew", padx=14, pady=(0, 4))
        tag_frame.grid_columnconfigure((0, 1, 2), weight=1)

        _opt_cfg = dict(fg_color="#0a1428", button_color=self.C_ACCENT, button_hover_color=self.C_ACCENT_HO, dropdown_fg_color=self.C_PANEL, dropdown_hover_color=self.C_ACCENT, text_color=self.C_TEXT, dropdown_text_color=self.C_TEXT, font=ctk.CTkFont("Segoe UI", 12), height=34, corner_radius=7)

        for col, (lbl, var, vals) in enumerate([("🦷 Dente", self._tag_dente, self.DENTI), ("🔬 Branca", self._tag_branca, self.BRANCHE), ("📋 Fase", self._tag_fase, self.FASI)]):
            cell = ctk.CTkFrame(tag_frame, fg_color="transparent")
            cell.grid(row=0, column=col, sticky="ew", padx=4)
            cell.grid_columnconfigure(0, weight=1)
            ctk.CTkLabel(cell, text=lbl, text_color=self.C_MUTED, font=ctk.CTkFont("Segoe UI", 10), anchor="w").grid(row=0, column=0, sticky="w")
            ctk.CTkOptionMenu(cell, variable=var, values=["—"] + vals, **_opt_cfg).grid(row=1, column=0, sticky="ew")

    def _build_note_row(self, parent):
        note_frame = ctk.CTkFrame(parent, fg_color="transparent")
        note_frame.grid(row=3, column=0, sticky="ew", padx=14, pady=(0, 4))
        note_frame.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(note_frame, text="📝 Note", text_color=self.C_MUTED, font=ctk.CTkFont("Segoe UI", 10), anchor="w").grid(row=0, column=0, sticky="w")
        self._note_entry = ctk.CTkEntry(note_frame, textvariable=self._note_text, fg_color="#0a1428", border_color=self.C_BORDER, text_color=self.C_TEXT, font=ctk.CTkFont("Segoe UI", 12), height=34, placeholder_text="Annotazioni cliniche opzionali…")
        self._note_entry.grid(row=1, column=0, sticky="ew")

    def _on_search(self, event=None):
        q = self._search_entry.get().strip()
        for w in self._results_scroll.winfo_children(): w.destroy()
        if not q: return
        try: rows = db.cerca_pazienti(q)
        except Exception: rows = []
        if not rows:
            ctk.CTkLabel(self._results_scroll, text="Nessun risultato.", text_color=self.C_MUTED, font=ctk.CTkFont("Segoe UI", 11)).grid(row=0, column=0, pady=14)
            return
        for i, paz in enumerate(rows):
            self._add_result_row(i, paz)

    def _add_result_row(self, idx: int, paz: dict):
        pid  = paz.get("id", "—")
        nome = paz.get("nome", "")
        cogn = paz.get("cognome", "")
        row = ctk.CTkFrame(self._results_scroll, fg_color="#111e38", corner_radius=6, height=38)
        row.grid(row=idx, column=0, sticky="ew", padx=2, pady=2)
        row.grid_propagate(False)
        row.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(row, text=f"{cogn} {nome}  |  ID: {pid}", text_color=self.C_TEXT, font=ctk.CTkFont("Segoe UI", 11), anchor="w").grid(row=0, column=0, sticky="ew", padx=8, pady=0)
        ctk.CTkButton(row, text="✔", width=30, height=26, fg_color=self.C_ACCENT, hover_color=self.C_ACCENT_HO, text_color="white", font=ctk.CTkFont("Segoe UI", 12, "bold"), command=lambda p=paz: self._select_paziente(p)).grid(row=0, column=1, padx=(0, 6), pady=6)

    def _select_paziente(self, paz: dict):
        self._paziente_id   = paz.get("id")
        self._paziente_info = paz
        nome = paz.get("nome", "")
        cogn = paz.get("cognome", "")
        pid  = paz.get("id", "—")
        self._sel_label.configure(text=f"✔  {cogn} {nome}\nID: {pid}", text_color=self.C_SUCCESS)
        self._update_save_btn()
        
    def imposta_paziente(self, pid: int):
        r = db.get_paziente_by_id(pid)
        if r:
            self._select_paziente(r)

    def _reset_search(self):
        self._search_entry.delete(0, "end")
        for w in self._results_scroll.winfo_children(): w.destroy()

    @staticmethod
    def _clean_drop_path(raw: str) -> Path:
        cleaned = raw.strip().strip("{}")
        return Path(cleaned)

    def _on_drop(self, event):
        path = self._clean_drop_path(event.data)
        if path.suffix.lower() not in {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif", ".webp"}:
            ToastManager.mostra("Formato non supportato.", "error")
            return
        self._carica_file(path)

    def _on_canvas_click(self, event=None):
        from tkinter import filedialog
        raw = filedialog.askopenfilename(title="Seleziona immagine", filetypes=[("Immagini", "*.jpg *.jpeg *.png *.bmp *.tiff *.tif *.webp")])
        if raw:
            self._carica_file(Path(raw))

    def _carica_file(self, path: Path):
        try:
            img = Image.open(path)
            img = ImageOps.exif_transpose(img)
            img = img.convert("RGB")
        except Exception as exc:
            ToastManager.mostra(f"Impossibile aprire il file:\n{exc}", "error")
            return
        self._file_path = path
        self._pil_img   = img
        self._drop_canvas.configure(highlightbackground=self.C_ACCENT)
        self._render_preview()   
        self._update_save_btn()

    def _on_canvas_configure(self, event=None):
        if self._pil_img is not None:
            self._render_preview()
        else:
            self._draw_drop_hint()

    def _render_preview(self):
        if self._pil_img is None: return
        cw = self._drop_canvas.winfo_width()
        ch = self._drop_canvas.winfo_height()
        if cw < 4 or ch < 4: return
        img_w, img_h = self._pil_img.size
        scale = min(cw / img_w, ch / img_h)
        new_w = max(1, int(img_w * scale))
        new_h = max(1, int(img_h * scale))

        resized = self._pil_img.resize((new_w, new_h), Image.LANCZOS)
        self._prev_img = ImageTk.PhotoImage(resized)
        self._drop_canvas.delete("all")
        self._drop_canvas.create_image(cw // 2, ch // 2, image=self._prev_img, anchor="center", tags="preview")

        fname = self._file_path.name if self._file_path else ""
        if fname:
            self._drop_canvas.create_rectangle(0, ch - 26, cw, ch, fill="#06101e", outline="", stipple="gray50")
            self._drop_canvas.create_text(cw // 2, ch - 13, text=fname, fill=self.C_MUTED, font=("Segoe UI", 9))

    def _draw_drop_hint(self):
        self._drop_canvas.delete("all")
        cw = self._drop_canvas.winfo_width()  or 300
        ch = self._drop_canvas.winfo_height() or 200
        self._drop_canvas.create_rectangle(20, 20, cw - 20, ch - 20, outline=self.C_BORDER, width=2, dash=(6, 4))
        self._drop_canvas.create_text(cw // 2, ch // 2 - 22, text="⬆", fill=self.C_ACCENT, font=("Segoe UI", 28))
        self._drop_canvas.create_text(cw // 2, ch // 2 + 16, text="Trascina un'immagine qui\noppure clicca per selezionarla", fill=self.C_MUTED, font=("Segoe UI", 12), justify="center")

    def _update_save_btn(self):
        ready = (self._paziente_id is not None and self._file_path is not None)
        self._btn_save.configure(state="normal" if ready else "disabled", text="💾  Salva nel Database" if ready else "Seleziona Paziente e Immagine")

    def _salva(self):
        if self._paziente_id is None or self._file_path is None: return

        dente  = self._tag_dente.get()
        branca = self._tag_branca.get()
        fase   = self._tag_fase.get()
        note   = self._note_text.get().strip()

        try:
            # FIX: Utilizziamo la vera funzione del database
            fid = db.upload_foto(
                paziente_id=self._paziente_id,
                sorgente_path=self._file_path,
                dente=dente if dente not in ("", "—") else "",
                branca=branca if branca not in ("", "—") else "",
                fase=fase if fase not in ("", "—") else "",
                note=note
            )
            ToastManager.mostra(f"✔  Immagine caricata con ID {fid}", "success")
            self._reset_form()
            # Aggiorna la statusbar
            self.winfo_toplevel()._aggiorna_statusbar()
        except Exception as exc:
            ToastManager.mostra(f"Errore salvataggio:\n{exc}", "error")

    def _reset_form(self):
        self._file_path  = None
        self._pil_img    = None
        self._prev_img   = None
        self._tag_dente.set("—")
        self._tag_branca.set("—")
        self._tag_fase.set("—")
        self._note_text.set("")
        self._drop_canvas.configure(highlightbackground=self.C_BORDER)
        self._draw_drop_hint()
        self._update_save_btn()



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
        self.grid_rowconfigure(2, weight=1)   # galleria occupa row 2

        # ── KPI cards ────────────────────────────────────────────────
        kf = ctk.CTkFrame(self, fg_color="transparent")
        kf.grid(row=0, column=0, padx=0, pady=(0, 8), sticky="ew")
        kf.grid_columnconfigure((0, 1, 2, 3), weight=1)

        self._kpi_labels: dict = {}
        specs_kpi = [
            ("pazienti",       "👤  Pazienti",       COLORI["accent"]),
            ("foto_totali",    "📷  Foto totali",     "#1a4d2e"),
            ("foto_oggi",      "📅  Foto oggi",       "#2a1a4d"),
            ("foto_settimana", "📈  Ultimi 7 giorni", "#4d2a0a"),
        ]
        for col, (chiave, etichetta, colore) in enumerate(specs_kpi):
            card = ctk.CTkFrame(kf, fg_color=colore, corner_radius=10)
            card.grid(row=0, column=col,
                      padx=(0 if col == 0 else 6, 0), sticky="ew")
            card.grid_columnconfigure(0, weight=1)
            ctk.CTkLabel(card, text=etichetta,
                         font=("Segoe UI", 9),
                         text_color="#9aacc8").grid(
                row=0, column=0, padx=14, pady=(10, 2), sticky="w")
            lbl = ctk.CTkLabel(card, text="—",
                               font=("Segoe UI", 22, "bold"),
                               text_color=COLORI["testo_chiaro"])
            lbl.grid(row=1, column=0, padx=14, pady=(0, 10), sticky="w")
            self._kpi_labels[chiave] = lbl

        self._aggiorna_kpi()

        # ── Filtri ───────────────────────────────────────────────────
        fc = ctk.CTkFrame(self, fg_color=COLORI["card_bg"], corner_radius=12)
        fc.grid(row=1, column=0, padx=0, pady=(0, 8), sticky="ew")
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
                w.bind("<Return>", lambda e: self.esegui_ricerca())
                w.bind("<KeyRelease>", self._debounce_dashboard)
            else:
                w = ctk.CTkComboBox(fc, values=vals, font=FONT_NORMALE,
                                    height=32, state="readonly",
                                    command=lambda v: self.esegui_ricerca())
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
        self._galleria.grid(row=2, column=0, sticky="nsew")
        for c in range(self.COLS):
            self._galleria.grid_columnconfigure(c, weight=1)

    def _debounce_dashboard(self, event=None):
        """Attende 400ms di inattività prima di eseguire la ricerca."""
        if hasattr(self, "_db_id") and self._db_id:
            try:
                self.after_cancel(self._db_id)
            except Exception:
                pass
        self._db_id = self.after(400, self.esegui_ricerca)

    def _aggiorna_kpi(self):
        """Carica le KPI dal DB e aggiorna le card. Eseguito in thread per non bloccare."""
        def _fetch():
            try:
                stats = db.kpi_stats()
                self.after(0, lambda: self._applica_kpi(stats))
            except Exception:
                pass
        threading.Thread(target=_fetch, daemon=True).start()

    def _applica_kpi(self, stats: dict):
        mapping = {
            "pazienti":       str(stats.get("pazienti", "—")),
            "foto_totali":    str(stats.get("foto_totali", "—")),
            "foto_oggi":      str(stats.get("foto_oggi", "—")),
            "foto_settimana": str(stats.get("foto_settimana", "—")),
        }
        for chiave, valore in mapping.items():
            if chiave in self._kpi_labels:
                try:
                    self._kpi_labels[chiave].configure(text=valore)
                except Exception:
                    pass

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
        self._aggiorna_kpi()
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
# ===========================================================================
# APPLICAZIONE PRINCIPALE
# ===========================================================================



# ══════════════════════════════════════════════════════════════════════════════
#  APPLICAZIONE PRINCIPALE
# ══════════════════════════════════════════════════════════════════════════════

if _DND_OK:
    class DnDCTk(ctk.CTk, TkinterDnD.DnDWrapper):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.TkdndVersion = TkinterDnD._require(self)
else:
    DnDCTk = ctk.CTk


class App(DnDCTk, _SidebarMixin):
    """
    Applicazione principale.
    Eredita da _SidebarMixin per la sidebar moderna (MODERN_THEME).
    Layout principale usa pack (coerente con sidebar mixin).
    """

    _TITOLI: dict[str, str] = {
        "dashboard":    "📋  Dashboard & Ricerca",
        "pazienti":     "👤  Gestione Pazienti",
        "upload":       "⬆️  Upload Fotografia",
        "import":       "📦  Import Massivo",
        "statistiche":  "📊  Statistiche Cliniche",
        "modifica_tag": "✏️  Modifica Tag Fotografie",
        "backup":       "💾  Backup & Ripristino",
        "webcam":       "📹  Acquisizione Webcam",
        "utenti":       "👥  Gestione Utenti",
        "before_after": "🔄  Confronto Before / After",
        "email":        "📧  Invio Email Dossier",
        "timeline":     "📅  Timeline Paziente",
        "impostazioni": "⚙  Impostazioni",
        "info":         "ℹ  Informazioni",
    }

    def __init__(self):
        super().__init__()
        T = MODERN_THEME

        # ── aspetto finestra ──────────────────────────────────────────────────
        self.configure(fg_color=T["bg_root"])
        self.title("DentalPhoto Pro — Gestione Clinica")
        self.geometry("1380x840")
        self.minsize(1060, 640)

        icon_path = Path(__file__).parent / "Icon_APP.png"
        if icon_path.exists():
            try:
                _ico = ImageTk.PhotoImage(Image.open(icon_path))
                self.wm_iconphoto(False, _ico)
                self._icon_ref = _ico          # GC anchor
            except Exception:
                pass

        # ── stato interno ─────────────────────────────────────────────────────
        self._active_page: str             = ""
        self._frames:      dict            = {}
        self._paz_upload:  int | None      = None
        self._foto_mod:    int | None      = None
        self._lock_aperto: bool            = False
        self._watchdog:    CameraWatchdog | None = None
        self._backup_in_corso: bool        = False

        # ── layout (pack — coerente con il sidebar mixin) ─────────────────────
        #   sidebar (pack left)  |  separatore (pack left)  |  main column (pack fill)
        self._build_sidebar()          # ← da _SidebarMixin, pack(side="left")
        self._build_main_column()      # ← pack(side="left", fill="both", expand=True)

        # ── servizi ───────────────────────────────────────────────────────────
        ToastManager.init(self)
        self._registra_hotkey()
        self._avvia_timer_lock()
        self._avvia_refresh_statusbar()
        self.bind_all("<Motion>",   lambda e: SessioneUtente.registra_attivita())
        self.bind_all("<KeyPress>", lambda e: SessioneUtente.registra_attivita())

        # ── navigazione iniziale ──────────────────────────────────────────────
        self._navigate("dashboard")

    # ══════════════════════════════════════════════════════════════════════════
    #  Layout principale
    # ══════════════════════════════════════════════════════════════════════════

    def _build_main_column(self):
        """Colonna destra: header + area contenuto + statusbar."""
        T = MODERN_THEME
        col = tk.Frame(self, bg=T["bg_root"])
        col.pack(side="left", fill="both", expand=True)

        self._build_header_bar(col)
        self._build_statusbar_modern(col)   # pack bottom prima di content
        self._build_content_area(col)       # fill="both", expand=True

    def _build_header_bar(self, parent):
        """Barra superiore con titolo pagina, watchdog e shortcut hints."""
        T = MODERN_THEME
        bar = tk.Frame(parent, bg=T["bg_sidebar"], height=52)
        bar.pack(side="top", fill="x")
        bar.pack_propagate(False)

        # separatore orizzontale inferiore
        tk.Frame(parent, bg=T["border"], height=1).pack(side="top", fill="x")

        # ── titolo pagina corrente ────────────────────────────────────────────
        self._lbl_titolo = tk.Label(
            bar,
            text="",
            bg=T["bg_sidebar"],
            fg=T["text_primary"],
            font=("Segoe UI", 14, "bold"),
            anchor="w",
        )
        self._lbl_titolo.pack(side="left", padx=20, fill="y")

        # ── bottone Auto-Import Reflex ────────────────────────────────────────
        self._btn_watchdog = ctk.CTkButton(
            bar,
            text="📷  Auto-Import",
            width=148,
            height=32,
            fg_color=T["bg_panel"],
            hover_color=T["bg_panel_alt"],
            text_color=T["text_secondary"],
            border_color=T["border"],
            border_width=1,
            font=ctk.CTkFont("Segoe UI", 11),
            corner_radius=7,
            command=self._toggle_watchdog,
        )
        self._btn_watchdog.pack(side="right", padx=(6, 16), pady=10)

        # ── hint shortcut ─────────────────────────────────────────────────────
        tk.Label(
            bar,
            text="Ctrl+K  Ricerca globale   ·   F5  Aggiorna   ·   Ctrl+B  Backup",
            bg=T["bg_sidebar"],
            fg=T["text_disabled"],
            font=("Segoe UI", 8),
        ).pack(side="right", padx=(0, 12), fill="y")

    def _build_content_area(self, parent):
        """Frame contenitore delle pagine (lazy-loaded)."""
        T = MODERN_THEME
        wrapper = tk.Frame(parent, bg=T["bg_root"])
        wrapper.pack(side="top", fill="both", expand=True,
                     padx=18, pady=(14, 0))
        wrapper.grid_columnconfigure(0, weight=1)
        wrapper.grid_rowconfigure(0, weight=1)

        self._fc = ctk.CTkFrame(wrapper, fg_color="transparent", corner_radius=0)
        self._fc.grid(row=0, column=0, sticky="nsew")
        self._fc.grid_columnconfigure(0, weight=1)
        self._fc.grid_rowconfigure(0, weight=1)

    def _build_statusbar_modern(self, parent):
        """Status bar inferiore con utente, statistiche DB e ultimo backup."""
        T = MODERN_THEME
        # separatore superiore
        tk.Frame(parent, bg=T["separator"], height=1).pack(side="bottom", fill="x")

        sb = tk.Frame(parent, bg=T["bg_sidebar"], height=28)
        sb.pack(side="bottom", fill="x")
        sb.pack_propagate(False)

        self._sb_utente = tk.Label(
            sb, text="", bg=T["bg_sidebar"],
            fg=T["text_secondary"], font=("Segoe UI", 9), anchor="w",
        )
        self._sb_utente.pack(side="left", padx=(14, 0), fill="y")

        self._sb_backup = tk.Label(
            sb, text="", bg=T["bg_sidebar"],
            fg=T["text_secondary"], font=("Segoe UI", 9), anchor="e",
        )
        self._sb_backup.pack(side="right", padx=(0, 14), fill="y")

        self._sb_stats = tk.Label(
            sb, text="", bg=T["bg_sidebar"],
            fg=T["text_disabled"], font=("Segoe UI", 9), anchor="center",
        )
        self._sb_stats.pack(side="left", fill="both", expand=True)

    # ══════════════════════════════════════════════════════════════════════════
    #  _SidebarMixin bridge
    # ══════════════════════════════════════════════════════════════════════════

    def _show_page(self, key: str):
        """
        Chiamato da _SidebarMixin._navigate() dopo aver aggiornato i bottoni.
        Si occupa di: switcher frame, titolo, aggiornamenti contestuali.
        """
        T = MODERN_THEME
        self._lbl_titolo.configure(text=self._TITOLI.get(key, ""))

        # crea il frame se non esiste ancora (lazy init)
        if key not in self._frames:
            try:
                self._frames[key] = self._build_frame(key)
            except ValueError:
                return

        # nasconde tutti, mostra il richiesto
        for f in self._frames.values():
            f.grid_remove()
        self._frames[key].grid(row=0, column=0, sticky="nsew")

        # aggiornamenti contestuali
        if key == "pazienti":
            self._frames["pazienti"].aggiorna_lista()
        elif key == "dashboard":
            self._frames["dashboard"].esegui_ricerca()
        elif key == "statistiche":
            self._frames["statistiche"].aggiorna_tutto()
        elif key == "modifica_tag" and self._foto_mod is not None:
            self._frames["modifica_tag"].preimposta_id(self._foto_mod)
            self._foto_mod = None
        elif key == "webcam":
            self._frames["webcam"].attiva()
        elif key == "upload" and self._paz_upload is not None:
            self._frames["upload"].imposta_paziente(self._paz_upload)
            self._paz_upload = None

        self._aggiorna_statusbar()

    # ══════════════════════════════════════════════════════════════════════════
    #  _naviga  –  entry point pubblico (con pre-checks)
    # ══════════════════════════════════════════════════════════════════════════

    def _naviga(self, key: str):
        """
        Entry point per la navigazione con:
          - Controllo permessi
          - Disattivazione webcam se si lascia quella pagina
        Poi delega a _navigate (mixin) che aggiorna sidebar e chiama _show_page.
        """
        # controllo permessi
        if SessioneUtente.corrente and not SessioneUtente.ha_permesso(key):
            self.toast("Accesso negato: ruolo insufficiente.", "error")
            return

        # spegni la webcam se stiamo navigando via
        if self._active_page == "webcam" and "webcam" in self._frames:
            try:
                self._frames["webcam"].disattiva()
            except Exception:
                pass

        self._navigate(key)     # ← mixin: aggiorna sidebar + chiama _show_page

    # ══════════════════════════════════════════════════════════════════════════
    #  Costruzione frame pagine (lazy)
    # ══════════════════════════════════════════════════════════════════════════

    def _build_frame(self, key: str) -> ctk.CTkFrame:
        match key:
            case "dashboard":
                return DashboardFrame(self._fc, on_modifica_tag=self._goto_modifica)
            case "pazienti":
                return PazientiFrame(self._fc, on_paziente_selezionato=self._goto_upload)
            case "upload":
                return UploadFrame(self._fc)
            case "import":
                return BulkImportFrame(self._fc)
            case "statistiche":
                return StatisticheFrame(self._fc)
            case "modifica_tag":
                return ModificaTagFrame(self._fc)
            case "backup":
                return BackupRestoreFrame(self._fc)
            case "webcam":
                return WebcamFrame(self._fc, on_scatto=self._on_foto_scattata)
            case "utenti":
                return GestioneUtentiFrame(self._fc)
            case "before_after":
                return BeforeAfterFrame(self._fc)
            case "email":
                return EmailFrame(self._fc)
            case "timeline":
                return TimelineFrame(self._fc)
            case _:
                raise ValueError(f"Frame sconosciuto: {key!r}")

    # ══════════════════════════════════════════════════════════════════════════
    #  Callbacks di navigazione interna
    # ══════════════════════════════════════════════════════════════════════════

    def _on_foto_scattata(self, percorso_foto: str):
        self._naviga("upload")
        try:
            self._frames["upload"]._carica_file(Path(percorso_foto))
        except Exception:
            pass
        self.toast("📸 Foto acquisita e pronta per il salvataggio!", "success")

    def _goto_upload(self, pid: int):
        self._paz_upload = pid
        self._naviga("upload")

    def _goto_modifica(self, foto_id: int):
        self._foto_mod = foto_id
        self._naviga("modifica_tag")

    # ══════════════════════════════════════════════════════════════════════════
    #  Hotkey globali
    # ══════════════════════════════════════════════════════════════════════════

    def _registra_hotkey(self):
        VOCI_KEYS = [
            "dashboard", "pazienti", "upload", "import",
            "statistiche", "modifica_tag", "backup", "webcam", "before_after",
        ]
        for i, key in enumerate(VOCI_KEYS, start=1):
            self.bind_all(f"<Control-Key-{i}>",
                          lambda e, k=key: self._naviga(k), add="+")

        self.bind_all("<Control-n>", lambda e: self._naviga("pazienti"), add="+")
        self.bind_all("<Control-N>", lambda e: self._naviga("pazienti"), add="+")
        self.bind_all("<Control-b>", lambda e: self._backup_rapido(),    add="+")
        self.bind_all("<Control-B>", lambda e: self._backup_rapido(),    add="+")
        self.bind_all("<F5>",        lambda e: self._refresh_pagina(),   add="+")
        self.bind_all("<Control-f>", lambda e: self._focus_ricerca(),    add="+")
        self.bind_all("<Control-F>", lambda e: self._focus_ricerca(),    add="+")
        self.bind_all("<Control-k>", lambda e: self._apri_spotlight(),   add="+")
        self.bind_all("<Control-K>", lambda e: self._apri_spotlight(),   add="+")

    def _refresh_pagina(self):
        key = self._active_page
        if key == "dashboard" and "dashboard" in self._frames:
            self._frames["dashboard"].esegui_ricerca()
            self._frames["dashboard"]._aggiorna_kpi()
        elif key == "pazienti" and "pazienti" in self._frames:
            self._frames["pazienti"].aggiorna_lista()
        elif key == "statistiche" and "statistiche" in self._frames:
            self._frames["statistiche"].aggiorna_tutto()
        self._aggiorna_statusbar()
        self.toast("Pagina aggiornata", "info", 1800)

    def _focus_ricerca(self):
        self._naviga("dashboard")
        try:
            self._frames["dashboard"]._fp.focus_set()
        except Exception:
            pass

    def _apri_spotlight(self):
        SpotlightSearch(
            self,
            on_apri_paziente=self._spotlight_apri_paziente,
            on_apri_foto=self._spotlight_apri_foto,
        )

    def _spotlight_apri_paziente(self, pid: int):
        self._goto_upload(pid)
        self.toast("Paziente caricato", "info", 2000)

    def _spotlight_apri_foto(self, foto_id: int, foto_data):
        try:
            percorso = db.get_percorso_assoluto(foto_data)
            DettaglioFoto(self, percorso, foto_data,
                          on_modifica_tag=self._goto_modifica,
                          tutti_risultati=[foto_data], indice=0)
        except Exception as e:
            self.toast(f"Errore apertura foto: {e}", "error")

    # ══════════════════════════════════════════════════════════════════════════
    #  Status bar
    # ══════════════════════════════════════════════════════════════════════════

    def _avvia_refresh_statusbar(self):
        self._aggiorna_statusbar()
        self.after(60_000, self._avvia_refresh_statusbar)

    def _aggiorna_statusbar(self):
        def _fetch():
            try:
                stats   = db.kpi_stats()
                utente  = SessioneUtente.nome_display() if SessioneUtente.corrente else "—"
                self.after(0, lambda: self._applica_statusbar(stats, utente))
            except Exception:
                pass
        threading.Thread(target=_fetch, daemon=True).start()

    def _applica_statusbar(self, stats: dict, utente: str):
        try:
            self._sb_utente.configure(text=f"👤  {utente}")
            self._sb_stats.configure(
                text=(f"Pazienti: {stats['pazienti']}   "
                      f"Foto: {stats['foto_totali']}   "
                      f"Oggi: {stats['foto_oggi']}   "
                      f"DB: {stats['db_size_mb']} MB")
            )
            bk = stats.get("ultimo_backup")
            if bk:
                import datetime
                mtime   = datetime.datetime.fromtimestamp(bk.stat().st_mtime)
                bk_txt  = f"💾  Backup: {mtime.strftime('%d/%m/%Y %H:%M')}"
            else:
                bk_txt  = "💾  Nessun backup"
            self._sb_backup.configure(text=bk_txt)
        except Exception:
            pass

    # ══════════════════════════════════════════════════════════════════════════
    #  Toast shortcut
    # ══════════════════════════════════════════════════════════════════════════

    def toast(self, messaggio: str, tipo: str = "info", durata_ms: int = 3500):
        ToastManager.mostra(messaggio, tipo, durata_ms)

    # ══════════════════════════════════════════════════════════════════════════
    #  Session lock
    # ══════════════════════════════════════════════════════════════════════════

    def _avvia_timer_lock(self):
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
        import subprocess
        subprocess.Popen([sys.executable, __file__])

    # ══════════════════════════════════════════════════════════════════════════
    #  Backup rapido (Ctrl+B)
    # ══════════════════════════════════════════════════════════════════════════

    def _backup_rapido(self):
        if self._backup_in_corso:
            self.toast("Backup già in corso…", "warning")
            return
        self._backup_in_corso = True
        self.toast("⏳  Backup in corso…", "info", 8000)
        result: dict = {}

        def _job():
            try:
                result["path"] = esegui_backup(db.APP_DIR / "backups")
            except Exception as e:
                result["err"] = str(e)

        def _done():
            self._backup_in_corso = False
            if "err" in result:
                self.toast(f"Backup fallito: {result['err']}", "error", 6000)
            else:
                self.toast("✅  Backup salvato con successo", "success")
            self._aggiorna_statusbar()

        threading.Thread(
            target=lambda: (_job(), self.after(0, _done)),
            daemon=True,
        ).start()

    # ══════════════════════════════════════════════════════════════════════════
    #  Auto-Import Reflex (watchdog)
    # ══════════════════════════════════════════════════════════════════════════

    def _toggle_watchdog(self):
        T = MODERN_THEME
        if self._watchdog and self._watchdog.is_running:
            self._watchdog.stop()
            self._btn_watchdog.configure(
                text="📷  Auto-Import",
                fg_color=T["bg_panel"],
                text_color=T["text_secondary"],
            )
            self.toast("Auto-Import Reflex disattivato.", "info")
            return

        cartella = filedialog.askdirectory(
            title="Seleziona la cartella della Reflex / SD Wi-Fi"
        )
        if not cartella:
            return

        try:
            self._watchdog = CameraWatchdog(
                folder_path=cartella,
                on_new_file=self._on_nuova_foto_reflex,
            )
            self._watchdog.start()
            self._btn_watchdog.configure(
                text="📷  IN ASCOLTO…",
                fg_color=MODERN_THEME["success"],
                text_color="#000000",
            )
            self.toast(f"In ascolto su: {Path(cartella).name}", "success")
        except Exception as e:
            self.toast(f"Errore avvio Auto-Import: {e}", "error")

    def _on_nuova_foto_reflex(self, percorso_foto: Path):
        """Chiamata dal thread background del watchdog."""
        self.after(0, lambda p=percorso_foto: self._processa_foto_reflex(p))

    def _processa_foto_reflex(self, percorso_foto: Path):
        """Eseguita nel main thread Tkinter."""
        self._naviga("upload")
        if "upload" in self._frames:
            try:
                self._frames["upload"]._carica_file(percorso_foto)
            except Exception:
                pass
            self.toast("📸 Nuova foto importata dalla Reflex!", "success")


# ===========================================================================
# ENTRY POINT
# ===========================================================================

def _fix_scrollwheel(root):
    """Fix rotella mouse su CTkScrollableFrame (Windows)."""
    import platform
    if platform.system() != "Windows":
        return

    def _on_wheel(event):
        w = event.widget
        while w:
            if isinstance(w, ctk.CTkScrollableFrame):
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
    import database as db
    from auth import init_auth_db, SessioneUtente
    import logging

    logging.basicConfig(
        filename=str(db.APP_DIR / "errori_app.log"),
        level=logging.ERROR,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )

    db.init_db()
    init_auth_db()

    login_successo = False

    if DEBUG_MODE:
        with db.get_connection() as conn:
            admin = conn.execute(
                "SELECT * FROM utenti WHERE username = 'admin'"
            ).fetchone()
            if admin:
                SessioneUtente.login(admin)
                login_successo = True
                print("--- DEBUG MODE: Login bypassato (Admin) ---")
            else:
                from ui_login import LoginScreen
                win_login = LoginScreen()
                win_login.mainloop()
                login_successo = getattr(win_login, "login_riuscito", False)
    else:
        from ui_login import LoginScreen
        win_login = LoginScreen()
        win_login.mainloop()
        login_successo = getattr(win_login, "login_riuscito", False)

    if login_successo:
        app = App()
        _fix_scrollwheel(app)

        def handle_exception(exc_type, exc_value, exc_traceback):
            logging.error("Errore non gestito:",
                          exc_info=(exc_type, exc_value, exc_traceback))

        app.report_callback_exception = handle_exception
        app.mainloop()

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
import os
import tkinter as tk
from tkinter import filedialog, messagebox
import customtkinter as ctk
from PIL import Image
from datetime import date
import threading
import time
from pathlib import Path
from typing import Optional

# Drag & Drop — opzionale (richiede: pip install tkinterdnd2)
try:
    from tkinterdnd2 import TkinterDnD, DND_FILES
    _DND_OK = True
except ImportError:
    _DND_OK = False

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

        # ── Colonna sinistra: selezione paziente ─────────────────────
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

        # ── Colonna destra: carica & tagga ───────────────────────────
        uc = ctk.CTkFrame(self, fg_color=COLORI["card_bg"], corner_radius=12)
        uc.grid(row=0, column=1, padx=(8, 0), sticky="nsew")
        uc.grid_columnconfigure(0, weight=1)
        uc.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(uc, text="2 · Carica & Tagga", font=FONT_SEZIONE).grid(
            row=0, column=0, columnspan=2, padx=20, pady=(20, 4), sticky="w")

        # ── Zona Drop ────────────────────────────────────────────────
        self._drop_zone = ctk.CTkLabel(
            uc,
            text="",
            width=320, height=180,
            fg_color=COLORI["sfondo_entry"],
            corner_radius=12,
        )
        self._drop_zone.grid(row=1, column=0, columnspan=2,
                              padx=20, pady=(8, 0), sticky="ew")
        self._drop_zone.bind("<Button-1>", lambda e: self._scegli())

        # Canvas interno per testo + icona centrati
        self._drop_canvas = tk.Canvas(
            self._drop_zone,
            bg=COLORI["sfondo_entry"],
            highlightthickness=0,
            cursor="hand2",
        )
        self._drop_canvas.place(relwidth=1, relheight=1)
        self._drop_canvas.bind("<Button-1>", lambda e: self._scegli())
        self._drop_canvas.bind("<Configure>", lambda e: self._aggiorna_drop_placeholder())
        self._aggiorna_drop_placeholder()

        # Attiva Drag & Drop se tkinterdnd2 è disponibile
        self._dnd_attivo = False
        if _DND_OK:
            try:
                self._drop_zone.drop_target_register(DND_FILES)
                self._drop_zone.dnd_bind("<<Drop>>",    self._on_drop)
                self._drop_zone.dnd_bind("<<DragEnter>>", self._on_drag_enter)
                self._drop_zone.dnd_bind("<<DragLeave>>", self._on_drag_leave)
                self._drop_canvas.drop_target_register(DND_FILES)
                self._drop_canvas.dnd_bind("<<Drop>>",    self._on_drop)
                self._drop_canvas.dnd_bind("<<DragEnter>>", self._on_drag_enter)
                self._drop_canvas.dnd_bind("<<DragLeave>>", self._on_drag_leave)
                self._dnd_attivo = True
            except Exception:
                pass

        # Pulsante sfoglia alternativo
        ctk.CTkButton(uc, text="📂  Sfoglia…", font=FONT_NORMALE, height=32,
                      fg_color="transparent", border_width=1,
                      border_color=COLORI["sidebar_border"],
                      command=self._scegli).grid(
            row=2, column=0, columnspan=2, padx=20, pady=(6, 14), sticky="ew")

        # ── Tag clinici ───────────────────────────────────────────────
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
        self._note = ctk.CTkTextbox(uc, font=FONT_NORMALE, height=60)
        self._note.grid(row=8, column=0, columnspan=2, padx=20, pady=(0, 10), sticky="ew")

        self._btn_up = ctk.CTkButton(uc, text="⬆️  Carica",
                                      font=("Segoe UI", 13, "bold"), height=44,
                                      fg_color=COLORI["accent_bright"],
                                      hover_color="#c73652",
                                      command=self._carica)
        self._btn_up.grid(row=9, column=0, columnspan=2,
                          padx=20, pady=(0, 12), sticky="ew")

        self._stato = ctk.CTkLabel(uc, text="", font=FONT_PICCOLO,
                                    text_color=COLORI["verde_ok"])
        self._stato.grid(row=10, column=0, columnspan=2, pady=(0, 10))

    # ------------------------------------------------------------------
    # Drop zone helpers
    # ------------------------------------------------------------------

    _FORMATI_OK = {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif", ".webp"}

    def _aggiorna_drop_placeholder(self, evidenzia=False):
        """Ridisegna il contenuto della drop zone (testo + bordo tratteggiato)."""
        try:
            c = self._drop_canvas
            c.delete("all")
            w = c.winfo_width()  or 320
            h = c.winfo_height() or 180

            border_col = "#2563eb" if evidenzia else "#1e3a5f"
            bg_col     = "#111827" if evidenzia else COLORI["sfondo_entry"]
            c.configure(bg=bg_col)

            # Bordo tratteggiato simulato
            dash = (8, 6)
            c.create_rectangle(8, 8, w-8, h-8,
                                outline=border_col, width=2, dash=dash)

            if self._file:
                try:
                    from PIL import ImageTk
                    # Apre l'immagine e la ridimensiona mantenendo le proporzioni
                    img = Image.open(self._file)
                    img.thumbnail((w - 20, h - 20), Image.LANCZOS)
                    
                    # Salva in self._prev_img per evitare che venga eliminata dal Garbage Collector
                    self._prev_img = ImageTk.PhotoImage(img)
                    
                    # Mostra la preview centrata nel canvas
                    c.create_image(w//2, h//2, image=self._prev_img, anchor="center")
                    
                except Exception:
                    # Fallback: se l'immagine non è leggibile mostra il nome del file
                    c.create_text(w//2, h//2 - 12,
                                  text="✅  " + self._file.name[:40],
                                  fill="#10b981", font=("Segoe UI", 11, "bold"),
                                  anchor="center")
                    c.create_text(w//2, h//2 + 14,
                                  text="Clicca per cambiare",
                                  fill=COLORI["testo_grigio"],
                                  font=("Segoe UI", 9), anchor="center")
                                  
            elif evidenzia:
                c.create_text(w//2, h//2 - 8,
                              text="📂  Rilascia qui",
                              fill="#2563eb", font=("Segoe UI", 13, "bold"),
                              anchor="center")
            else:
                c.create_text(w//2, h//2 - 16,
                              text="⬆",
                              fill="#334155", font=("Segoe UI", 28),
                              anchor="center")
                c.create_text(w//2, h//2 + 12,
                              text="Trascina un'immagine qui",
                              fill=COLORI["testo_grigio"],
                              font=("Segoe UI", 11), anchor="center")
                dnd_hint = "o clicca per sfogliare"
                c.create_text(w//2, h//2 + 32,
                              text=dnd_hint,
                              fill="#334155",
                              font=("Segoe UI", 9), anchor="center")
        except Exception:
            pass

    def _on_drag_enter(self, event):
        self._aggiorna_drop_placeholder(evidenzia=True)
        return event.action

    def _on_drag_leave(self, event):
        self._aggiorna_drop_placeholder(evidenzia=False)

    def _on_drop(self, event):
        self._aggiorna_drop_placeholder(evidenzia=False)
        raw = event.data.strip()
        # tkinterdnd2 su Windows restituisce path tra {} se contengono spazi
        if raw.startswith("{") and raw.endswith("}"):
            raw = raw[1:-1]
        # Prende il primo file in caso di drop multiplo
        path = Path(raw.split("} {")[0])
        self._carica_file(path)
        return event.action

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
            filetypes=[("Immagini", "*.jpg *.jpeg *.png *.bmp *.tiff *.tif *.webp")])
        if not path:
            return
        self._carica_file(Path(path))

    def _carica_file(self, path: Path):
        """Carica un file (da dialog o drag & drop) e aggiorna la drop zone."""
        if path.suffix.lower() not in self._FORMATI_OK:
            ToastManager.mostra(f"Formato non supportato: {path.suffix}", "error")
            return
        if not path.exists():
            ToastManager.mostra("File non trovato.", "error")
            return
        self._file = path
        self._aggiorna_drop_placeholder()
        self.after(60, self._aggiorna_drop_placeholder)
        ToastManager.mostra(f"📂  {path.name}", "info", 2500)

    def _carica(self):
        if not self._paz_id:
            ToastManager.mostra("Seleziona un paziente prima di caricare.", "warning")
            return
        if not self._file:
            ToastManager.mostra("Trascina o scegli un'immagine.", "warning")
            return
        try:
            ds = date.fromisoformat(self._data.get().strip())
        except ValueError:
            ToastManager.mostra("Data non valida — formato: AAAA-MM-GG", "error")
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
        self._aggiorna_drop_placeholder()
        self._note.delete("1.0", "end")
        self._stato.configure(text=f"✅  Foto salvata (ID {fid})",
                               text_color=COLORI["verde_ok"])
        ToastManager.mostra(f"✅  Foto caricata con successo (ID {fid})", "success")

    def _err(self, msg):
        self._btn_up.configure(state="normal", text="⬆️  Carica")
        self._stato.configure(text=f"❌ {msg}", text_color=COLORI["accent_bright"])
        ToastManager.mostra(f"Errore upload: {msg}", "error")



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
# ===========================================================================
# APPLICAZIONE PRINCIPALE
# ===========================================================================

# Aggiungi questo blocco:
if _DND_OK:
    class DnDCTk(ctk.CTk, TkinterDnD.DnDWrapper):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.TkdndVersion = TkinterDnD._require(self)
else:
    DnDCTk = ctk.CTk

class App(DnDCTk):
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
        self.title("DentalPhoto — Gestione Fotografie Cliniche")
        self.geometry("1280x800")
        # --- IMPOSTAZIONE ICONA FINESTRA (Runtime) ---
        icon_path = Path(__file__).parent / "Icon_APP.jpg"
        if icon_path.exists():
            try:
                from PIL import Image, ImageTk
                pil_img = Image.open(icon_path)
                tk_icon = ImageTk.PhotoImage(pil_img)
                self.wm_iconphoto(False, tk_icon)
                self._icon_reference = tk_icon
                print("Icona caricata.")
            except Exception as e:
                print(f"Errore icona: {e}")
        self.minsize(960, 600)
        self._pagina = ""
        self._frames: dict = {}
        self._paz_upload: Optional[int] = None
        self._foto_mod: Optional[int] = None
        self._lock_aperto = False
        self._build_layout()
        ToastManager.init(self)
        self._registra_hotkey()
        self._naviga("dashboard")
        self._avvia_timer_lock()
        self._avvia_refresh_statusbar()
        # Propaga l'attività a SessioneUtente ad ogni interazione
        self.bind_all("<Motion>",   lambda e: SessioneUtente.registra_attivita())
        self.bind_all("<KeyPress>", lambda e: SessioneUtente.registra_attivita())

    # ------------------------------------------------------------------

    def _build_layout(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=0)   # status bar — altezza fissa

        sb = ctk.CTkFrame(self, width=228, corner_radius=0,
                          fg_color=COLORI["sidebar_bg"])
        sb.grid(row=0, column=0, sticky="nsew")
        sb.grid_propagate(False)
        sb.grid_columnconfigure(0, weight=1)
        sb.grid_rowconfigure(15, weight=1)  # riga vuota di spaziatura tra nav e bottom bar

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
        self._lbl_utente_badge.grid(row=1, column=0, padx=12, pady=(0, 4), sticky="ew")

        # Pulsante ricerca globale Ctrl+K
        ctk.CTkButton(
            sb,
            text="🔍  Cerca…       Ctrl+K",
            font=("Segoe UI", 9),
            height=26,
            fg_color=COLORI["sfondo_entry"],
            hover_color=COLORI["nav_active"],
            border_width=1,
            border_color=COLORI["sidebar_border"],
            corner_radius=6,
            text_color=COLORI["testo_grigio"],
            anchor="w",
            command=self._apri_spotlight,
        ).grid(row=2, column=0, padx=12, pady=(0, 4), sticky="ew")

        ctk.CTkFrame(sb, height=1, fg_color=COLORI["sidebar_border"]).grid(
            row=3, column=0, padx=14, pady=(0, 6), sticky="ew")

        self._nav_btns: dict = {}
        for i, (lbl, key) in enumerate(self.VOCI_NAV, start=4):
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
            row=16, column=0, padx=14, pady=(0, 6), sticky="ew")

        # Riga bottoni bottom
        bot = ctk.CTkFrame(sb, fg_color="transparent")
        bot.grid(row=17, column=0, padx=8, pady=(0, 4), sticky="ew")
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
            row=18, column=0, padx=14, pady=(6, 2), sticky="w")
        ctk.CTkOptionMenu(sb, values=["Dark", "Light", "System"],
                          font=("Segoe UI", 9), height=26,
                          command=lambda t: ctk.set_appearance_mode(t.lower())).grid(
            row=19, column=0, padx=8, pady=(0, 14), sticky="ew")

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

        # ── Status bar ───────────────────────────────────────────────
        sb_bar = ctk.CTkFrame(self, height=28, corner_radius=0,
                              fg_color=COLORI["sidebar_bg"],
                              border_width=1,
                              border_color=COLORI["sidebar_border"])
        sb_bar.grid(row=1, column=0, columnspan=2, sticky="ew")
        sb_bar.grid_propagate(False)
        sb_bar.grid_columnconfigure(1, weight=1)

        # Sezione sinistra: utente
        self._sb_utente = ctk.CTkLabel(
            sb_bar, text="", font=("Segoe UI", 9),
            text_color=COLORI["testo_grigio"])
        self._sb_utente.grid(row=0, column=0, padx=(12, 0), sticky="w")

        # Separatore
        ctk.CTkFrame(sb_bar, width=1, height=16,
                     fg_color=COLORI["sidebar_border"]).grid(
            row=0, column=1, padx=8, sticky="")

        # Sezione centrale: statistiche
        self._sb_stats = ctk.CTkLabel(
            sb_bar, text="", font=("Segoe UI", 9),
            text_color=COLORI["testo_grigio"])
        self._sb_stats.grid(row=0, column=1, padx=0, sticky="w")

        # Sezione destra: db size + backup
        self._sb_backup = ctk.CTkLabel(
            sb_bar, text="", font=("Segoe UI", 9),
            text_color=COLORI["testo_grigio"])
        self._sb_backup.grid(row=0, column=2, padx=(0, 12), sticky="e")

    # ------------------------------------------------------------------

    def toast(self, messaggio: str, tipo: str = "info", durata_ms: int = 3500):
        """Scorciatoia per mostrare una notifica toast."""
        ToastManager.mostra(messaggio, tipo, durata_ms)

    # ------------------------------------------------------------------
    # Hotkey globali
    # ------------------------------------------------------------------

    def _registra_hotkey(self):
        """
        Registra le scorciatoie da tastiera globali dell'applicazione.

        Ctrl+1…9  → naviga alla voce N della sidebar
        Ctrl+N    → nuovo paziente (apre sezione Pazienti)
        Ctrl+F    → focus sulla ricerca (Dashboard)
        F5        → aggiorna la pagina corrente
        Ctrl+B    → backup rapido
        """
        VOCI = [v[1] for v in self.VOCI_NAV]   # lista chiavi in ordine

        for i, chiave in enumerate(VOCI[:9], start=1):
            self.bind_all(
                f"<Control-Key-{i}>",
                lambda e, k=chiave: self._naviga(k),
                add="+",
            )

        self.bind_all("<Control-n>",
                      lambda e: self._naviga("pazienti"), add="+")
        self.bind_all("<Control-N>",
                      lambda e: self._naviga("pazienti"), add="+")
        self.bind_all("<Control-b>",
                      lambda e: self._backup_rapido(), add="+")
        self.bind_all("<Control-B>",
                      lambda e: self._backup_rapido(), add="+")
        self.bind_all("<F5>",
                      lambda e: self._refresh_pagina(), add="+")
        self.bind_all("<Control-f>",
                      lambda e: self._focus_ricerca(), add="+")
        self.bind_all("<Control-F>",
                      lambda e: self._focus_ricerca(), add="+")
        self.bind_all("<Control-k>",
                      lambda e: self._apri_spotlight(), add="+")
        self.bind_all("<Control-K>",
                      lambda e: self._apri_spotlight(), add="+")

    def _refresh_pagina(self):
        """F5 — aggiorna la sezione corrente."""
        pag = self._pagina
        if pag == "dashboard" and "dashboard" in self._frames:
            self._frames["dashboard"].esegui_ricerca()
            self._frames["dashboard"]._aggiorna_kpi()
        elif pag == "pazienti" and "pazienti" in self._frames:
            self._frames["pazienti"].aggiorna_lista()
        elif pag == "statistiche" and "statistiche" in self._frames:
            self._frames["statistiche"].aggiorna_tutto()
        self._aggiorna_statusbar()
        self.toast("Pagina aggiornata", "info", 1800)

    def _focus_ricerca(self):
        """Ctrl+F — porta il focus sulla ricerca della Dashboard."""
        self._naviga("dashboard")
        try:
            self._frames["dashboard"]._fp.focus_set()
        except Exception:
            pass

    def _apri_spotlight(self):
        """Ctrl+K — apre il popup di ricerca globale."""
        SpotlightSearch(
            self,
            on_apri_paziente=self._spotlight_apri_paziente,
            on_apri_foto=self._spotlight_apri_foto,
        )

    def _spotlight_apri_paziente(self, pid: int):
        """Callback spotlight: naviga a Upload con il paziente preselezionato."""
        self._goto_upload(pid)
        self.toast(f"Paziente caricato", "info", 2000)

    def _spotlight_apri_foto(self, foto_id: int, foto_data):
        """Callback spotlight: apre il DettaglioFoto."""
        try:
            percorso = db.get_percorso_assoluto(foto_data)
            DettaglioFoto(self, percorso, foto_data,
                          on_modifica_tag=self._goto_modifica,
                          tutti_risultati=[foto_data], indice=0)
        except Exception as e:
            self.toast(f"Errore apertura foto: {e}", "error")

    # ------------------------------------------------------------------
    # Status bar
    # ------------------------------------------------------------------

    def _avvia_refresh_statusbar(self):
        """Primo aggiornamento immediato + timer ogni 60s."""
        self._aggiorna_statusbar()
        self.after(60_000, self._avvia_refresh_statusbar)

    def _aggiorna_statusbar(self):
        """Aggiorna i label della status bar con i dati aggiornati dal DB."""
        def _fetch():
            try:
                stats = db.kpi_stats()
                utente = SessioneUtente.nome_display() if SessioneUtente.corrente else "—"
                self.after(0, lambda: self._applica_statusbar(stats, utente))
            except Exception:
                pass
        threading.Thread(target=_fetch, daemon=True).start()

    def _applica_statusbar(self, stats: dict, utente: str):
        try:
            self._sb_utente.configure(
                text=f"👤  {utente}"
            )
            self._sb_stats.configure(
                text=(f"Pazienti: {stats['pazienti']}   "
                      f"Foto: {stats['foto_totali']}   "
                      f"Oggi: {stats['foto_oggi']}   "
                      f"DB: {stats['db_size_mb']} MB")
            )
            bk = stats.get("ultimo_backup")
            if bk:
                import datetime
                mtime = datetime.datetime.fromtimestamp(bk.stat().st_mtime)
                bk_txt = f"💾  Backup: {mtime.strftime('%d/%m/%Y %H:%M')}"
            else:
                bk_txt = "💾  Nessun backup"
            self._sb_backup.configure(text=bk_txt)
        except Exception:
            pass

    # ------------------------------------------------------------------

    def _naviga(self, key: str):
        if key == self._pagina:
            return
        # Controllo permessi: operatori non possono accedere a backup/utenti
        if SessioneUtente.corrente and not SessioneUtente.ha_permesso(key):
            self.toast("Accesso negato: ruolo insufficiente", "error")
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
        self._aggiorna_statusbar()

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
        if hasattr(self, '_backup_in_corso') and self._backup_in_corso:
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
                self.toast(f"✅  Backup salvato con successo", "success")
            self._aggiorna_statusbar()

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
    import database as db
    from auth import init_auth_db, SessioneUtente
    import logging

    # 1. Inizializziamo il Logging (crea un file errori_app.log nella cartella dei dati)
    logging.basicConfig(
        filename=str(db.APP_DIR / "errori_app.log"),
        level=logging.ERROR,
        format="%(asctime)s - %(levelname)s - %(message)s"
    )

    # 2. Inizializziamo i Database (Pazienti e Utenti)
    db.init_db()
    init_auth_db()

    # 3. Gestione dell'accesso
    login_successo = False

    if DEBUG_MODE:
        # Tenta di loggare automaticamente l'admin per velocizzare il debug
        with db.get_connection() as conn:
            admin = conn.execute("SELECT * FROM utenti WHERE username = 'admin'").fetchone()
            if admin:
                SessioneUtente.login(admin)
                login_successo = True
                print("--- DEBUG MODE: Login bypassato (Admin) ---")
            else:
                # Se l'admin non esiste (primo avvio in assoluto), apriamo il login
                from ui_login import LoginScreen
                win_login = LoginScreen()
                win_login.mainloop()
                login_successo = getattr(win_login, 'login_riuscito', False)
    else:
        # Modalità normale per il pubblico
        from ui_login import LoginScreen
        win_login = LoginScreen()
        win_login.mainloop()
        login_successo = getattr(win_login, 'login_riuscito', False)

    # 4. Avvio dell'applicazione principale solo se il login è ok
    if login_successo:
        app = App()
        # Funzione opzionale per sistemare la rotella del mouse su Windows
        if "_fix_scrollwheel" in globals():
            _fix_scrollwheel(app)
        
        # Intercettatore globale di errori per la UI
        def handle_exception(exc_type, exc_value, exc_traceback):
            logging.error("Errore non gestito:", exc_info=(exc_type, exc_value, exc_traceback))
        
        app.report_callback_exception = handle_exception
        app.mainloop()
"""
ui_bulk_import.py
=================
Frame di importazione massiva di fotografie cliniche.

Funzionalità:
  - Selezione multipla di file immagine con il file picker
  - Anteprima della coda di import (lista scrollabile con thumbnail)
  - Assegnazione di tag in batch (stessa Branca/Fase/Dente per tutti i file)
  - Override per singola foto (dente personalizzato per ogni elemento)
  - Barra di avanzamento in tempo reale durante il caricamento
  - Report finale: OK / Errori

Si integra in App come quinta voce di navigazione.
"""

from tkinter import filedialog, messagebox
import customtkinter as ctk
from PIL import Image
from datetime import date
from pathlib import Path
from typing import Optional
import threading

import database as db

# ---------------------------------------------------------------------------
# Palette
# ---------------------------------------------------------------------------

COLORI = {
    "card_bg":       "#16213e",
    "sfondo_entry":  "#0d1117",
    "accent":        "#0f3460",
    "accent_bright": "#e94560",
    "verde_ok":      "#4caf50",
    "arancio_warn":  "#ff9800",
    "testo_chiaro":  "#e0e0e0",
    "testo_grigio":  "#9e9e9e",
    "rosso_err":     "#f44336",
    "bg_ok":         "#1b3a1b",
    "bg_err":        "#3a1b1b",
}

FONT_SEZIONE = ("Segoe UI", 13, "bold")
FONT_NORMALE = ("Segoe UI", 12)
FONT_PICCOLO = ("Segoe UI", 10)
FONT_MONO    = ("Consolas", 9)

# ---------------------------------------------------------------------------
# Dimensione miniatura in coda
# ---------------------------------------------------------------------------

THUMB_CODA = (64, 48)


# ---------------------------------------------------------------------------
# Struttura dati per un elemento della coda
# ---------------------------------------------------------------------------

class ElementoCoda:
    """Rappresenta un file in attesa di importazione."""

    __slots__ = ("path", "dente_override", "stato", "foto_id", "errore")

    def __init__(self, path: Path):
        self.path: Path          = path
        self.dente_override: str = ""   # stringa vuota = usa il tag batch
        self.stato: str          = "attesa"   # attesa | ok | errore
        self.foto_id: Optional[int] = None
        self.errore: str         = ""


# ===========================================================================
# FRAME: IMPORT MASSIVO
# ===========================================================================

class BulkImportFrame(ctk.CTkFrame):
    """
    Layout a tre colonne:
      Sinistra  → selezione paziente
      Centro    → coda file + controlli aggiunta/rimozione
      Destra    → tag batch + pulsante avvia import + log
    """

    def __init__(self, master, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self._coda: list[ElementoCoda] = []
        self._paziente_id: Optional[int] = None
        self._thumb_refs: list = []    # anti-GC
        self._in_corso: bool = False
        self._build_ui()
        self._aggiorna_lista_pazienti()

    # ------------------------------------------------------------------
    # Costruzione UI
    # ------------------------------------------------------------------

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=2)
        self.grid_columnconfigure(2, weight=2)
        self.grid_rowconfigure(0, weight=1)

        # ── colonna sinistra: selezione paziente ──
        pcard = ctk.CTkFrame(self, fg_color=COLORI["card_bg"], corner_radius=12)
        pcard.grid(row=0, column=0, padx=(0, 6), pady=0, sticky="nsew")
        pcard.grid_columnconfigure(0, weight=1)
        pcard.grid_rowconfigure(2, weight=1)

        ctk.CTkLabel(pcard, text="1 · Paziente",
                     font=FONT_SEZIONE).grid(row=0, column=0, padx=16, pady=(16, 8), sticky="w")

        self._cerca_paz = ctk.CTkEntry(pcard, placeholder_text="🔍 Filtra…",
                                       font=FONT_NORMALE, height=32)
        self._cerca_paz.grid(row=1, column=0, padx=16, pady=(0, 6), sticky="ew")
        self._cerca_paz.bind("<KeyRelease>", lambda e: self._aggiorna_lista_pazienti())

        self._lista_paz = ctk.CTkScrollableFrame(pcard, fg_color="transparent")
        self._lista_paz.grid(row=2, column=0, padx=8, pady=(0, 8), sticky="nsew")
        self._lista_paz.grid_columnconfigure(0, weight=1)

        self._lbl_paz = ctk.CTkLabel(pcard, text="Nessun paziente",
                                      font=FONT_PICCOLO,
                                      text_color=COLORI["testo_grigio"],
                                      wraplength=180)
        self._lbl_paz.grid(row=3, column=0, padx=16, pady=(0, 16))

        # ── colonna centrale: coda file ──
        ccard = ctk.CTkFrame(self, fg_color=COLORI["card_bg"], corner_radius=12)
        ccard.grid(row=0, column=1, padx=6, pady=0, sticky="nsew")
        ccard.grid_columnconfigure(0, weight=1)
        ccard.grid_rowconfigure(2, weight=1)

        hdr = ctk.CTkFrame(ccard, fg_color="transparent")
        hdr.grid(row=0, column=0, padx=16, pady=(16, 6), sticky="ew")
        hdr.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(hdr, text="2 · Coda File",
                     font=FONT_SEZIONE).grid(row=0, column=0, sticky="w")

        # Badge contatore
        self._lbl_contatore = ctk.CTkLabel(
            hdr, text="0 file",
            font=FONT_PICCOLO,
            fg_color=COLORI["accent"],
            corner_radius=8, padx=8, pady=2,
            text_color="white",
        )
        self._lbl_contatore.grid(row=0, column=1, padx=(8, 0))

        # Pulsanti add/clear
        btn_row = ctk.CTkFrame(ccard, fg_color="transparent")
        btn_row.grid(row=1, column=0, padx=16, pady=(0, 6), sticky="ew")

        ctk.CTkButton(btn_row, text="➕ Aggiungi File",
                      font=FONT_PICCOLO, height=30, width=130,
                      command=self._aggiungi_file).pack(side="left", padx=(0, 6))
        ctk.CTkButton(btn_row, text="🗑 Svuota",
                      font=FONT_PICCOLO, height=30, width=80,
                      fg_color="transparent", border_width=1,
                      command=self._svuota_coda).pack(side="left")

        # Lista coda scrollabile
        self._scroll_coda = ctk.CTkScrollableFrame(ccard, fg_color="transparent")
        self._scroll_coda.grid(row=2, column=0, padx=8, pady=(0, 8), sticky="nsew")
        self._scroll_coda.grid_columnconfigure(0, weight=1)

        # ── colonna destra: tag batch + avvia ──
        tcard = ctk.CTkFrame(self, fg_color=COLORI["card_bg"], corner_radius=12)
        tcard.grid(row=0, column=2, padx=(6, 0), pady=0, sticky="nsew")
        tcard.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(tcard, text="3 · Tag Batch & Avvia",
                     font=FONT_SEZIONE).grid(row=0, column=0, padx=16, pady=(16, 4), sticky="w")
        ctk.CTkLabel(tcard,
                     text="Questi tag verranno applicati a tutti i file\n"
                          "salvo override dente per singola foto.",
                     font=FONT_PICCOLO,
                     text_color=COLORI["testo_grigio"],
                     wraplength=280).grid(row=1, column=0, padx=16, pady=(0, 12), sticky="w")

        # Dente batch
        ctk.CTkLabel(tcard, text="Dente (FDI)",
                     font=FONT_PICCOLO,
                     text_color=COLORI["testo_grigio"]).grid(
            row=2, column=0, padx=16, pady=(0, 2), sticky="w")
        self._combo_dente = ctk.CTkComboBox(
            tcard, values=db.DENTI_FDI, font=FONT_NORMALE, height=34, state="readonly")
        self._combo_dente.set(db.DENTI_FDI[0])
        self._combo_dente.grid(row=3, column=0, padx=16, pady=(0, 10), sticky="ew")

        # Branca batch
        ctk.CTkLabel(tcard, text="Branca",
                     font=FONT_PICCOLO,
                     text_color=COLORI["testo_grigio"]).grid(
            row=4, column=0, padx=16, pady=(0, 2), sticky="w")
        self._combo_branca = ctk.CTkComboBox(
            tcard, values=db.BRANCHE, font=FONT_NORMALE, height=34, state="readonly")
        self._combo_branca.set(db.BRANCHE[0])
        self._combo_branca.grid(row=5, column=0, padx=16, pady=(0, 10), sticky="ew")

        # Fase batch
        ctk.CTkLabel(tcard, text="Fase Clinica",
                     font=FONT_PICCOLO,
                     text_color=COLORI["testo_grigio"]).grid(
            row=6, column=0, padx=16, pady=(0, 2), sticky="w")
        self._combo_fase = ctk.CTkComboBox(
            tcard, values=db.FASI, font=FONT_NORMALE, height=34, state="readonly")
        self._combo_fase.set(db.FASI[0])
        self._combo_fase.grid(row=7, column=0, padx=16, pady=(0, 10), sticky="ew")

        # Data batch
        ctk.CTkLabel(tcard, text="Data Scatto",
                     font=FONT_PICCOLO,
                     text_color=COLORI["testo_grigio"]).grid(
            row=8, column=0, padx=16, pady=(0, 2), sticky="w")
        self._entry_data = ctk.CTkEntry(tcard, font=FONT_NORMALE, height=34)
        self._entry_data.insert(0, date.today().isoformat())
        self._entry_data.grid(row=9, column=0, padx=16, pady=(0, 10), sticky="ew")

        # Note batch
        ctk.CTkLabel(tcard, text="Note comuni",
                     font=FONT_PICCOLO,
                     text_color=COLORI["testo_grigio"]).grid(
            row=10, column=0, padx=16, pady=(0, 2), sticky="w")
        self._txt_note = ctk.CTkTextbox(tcard, font=FONT_NORMALE, height=60)
        self._txt_note.grid(row=11, column=0, padx=16, pady=(0, 14), sticky="ew")

        # Pulsante avvia
        self._btn_avvia = ctk.CTkButton(
            tcard,
            text="🚀  Avvia Import Massivo",
            font=("Segoe UI", 13, "bold"), height=46,
            fg_color=COLORI["accent_bright"], hover_color="#c73652",
            command=self._avvia_import,
        )
        self._btn_avvia.grid(row=12, column=0, padx=16, pady=(0, 8), sticky="ew")

        # Barra di progresso
        self._progressbar = ctk.CTkProgressBar(tcard, height=8)
        self._progressbar.set(0)
        self._progressbar.grid(row=13, column=0, padx=16, pady=(0, 4), sticky="ew")

        self._lbl_progresso = ctk.CTkLabel(
            tcard, text="", font=FONT_PICCOLO,
            text_color=COLORI["testo_grigio"])
        self._lbl_progresso.grid(row=14, column=0, padx=16, pady=(0, 4))

        # Log risultati
        ctk.CTkLabel(tcard, text="Log",
                     font=FONT_PICCOLO,
                     text_color=COLORI["testo_grigio"]).grid(
            row=15, column=0, padx=16, pady=(8, 2), sticky="w")

        self._txt_log = ctk.CTkTextbox(
            tcard, font=FONT_MONO, height=120,
            fg_color=COLORI["sfondo_entry"],
        )
        self._txt_log.grid(row=16, column=0, padx=16, pady=(0, 16), sticky="ew")
        self._txt_log.configure(state="disabled")

    # ------------------------------------------------------------------
    # Pazienti
    # ------------------------------------------------------------------

    def _aggiorna_lista_pazienti(self, *_):
        righe = db.cerca_pazienti(self._cerca_paz.get())
        for w in self._lista_paz.winfo_children():
            w.destroy()
        for i, r in enumerate(righe):
            sel = (r["id"] == self._paziente_id)
            ctk.CTkButton(
                self._lista_paz,
                text=f"{r['cognome']} {r['nome']}",
                font=FONT_PICCOLO, height=30,
                fg_color=COLORI["accent"] if sel else COLORI["sfondo_entry"],
                anchor="w",
                command=lambda rid=r["id"], rn=f"{r['cognome']} {r['nome']}":
                    self._set_paziente(rid, rn),
            ).grid(row=i, column=0, padx=4, pady=2, sticky="ew")

    def _set_paziente(self, pid: int, nome: str):
        self._paziente_id = pid
        self._lbl_paz.configure(text=f"✅ {nome}", text_color=COLORI["verde_ok"])
        self._aggiorna_lista_pazienti()

    def imposta_paziente(self, paziente_id: int):
        """API pubblica per pre-selezionare il paziente dall'esterno."""
        r = db.get_paziente_by_id(paziente_id)
        if r:
            self._set_paziente(paziente_id, f"{r['cognome']} {r['nome']}")

    # ------------------------------------------------------------------
    # Gestione coda
    # ------------------------------------------------------------------

    def _aggiungi_file(self):
        paths = filedialog.askopenfilenames(
            title="Seleziona immagini (selezione multipla)",
            filetypes=[("Immagini", "*.jpg *.jpeg *.png *.bmp *.tiff *.webp"),
                       ("Tutti i file", "*.*")],
        )
        nuovi = 0
        percorsi_esistenti = {str(e.path) for e in self._coda}
        for p in paths:
            if p not in percorsi_esistenti:
                self._coda.append(ElementoCoda(Path(p)))
                nuovi += 1
        if nuovi > 0:
            self._ridisegna_coda()

    def _rimuovi_da_coda(self, idx: int):
        if 0 <= idx < len(self._coda):
            self._coda.pop(idx)
            self._ridisegna_coda()

    def _svuota_coda(self):
        self._coda.clear()
        self._ridisegna_coda()

    def _ridisegna_coda(self):
        """Ridisegna tutti gli elementi nella lista di coda."""
        for w in self._scroll_coda.winfo_children():
            w.destroy()
        self._thumb_refs.clear()

        n = len(self._coda)
        self._lbl_contatore.configure(
            text=f"{n} file",
            fg_color=COLORI["accent_bright"] if n > 0 else COLORI["accent"],
        )

        if n == 0:
            ctk.CTkLabel(
                self._scroll_coda,
                text="Nessun file in coda.\n\nClicca «Aggiungi File» per iniziare.",
                font=FONT_PICCOLO,
                text_color=COLORI["testo_grigio"],
                justify="center",
            ).grid(row=0, column=0, pady=30)
            return

        for i, elem in enumerate(self._coda):
            self._riga_coda(i, elem)

    def _riga_coda(self, idx: int, elem: ElementoCoda):
        """Disegna la singola riga della coda con thumbnail e campo dente."""
        # Colore di sfondo in base allo stato
        sfondo = {
            "attesa": COLORI["sfondo_entry"],
            "ok":     COLORI["bg_ok"],
            "errore": COLORI["bg_err"],
        }.get(elem.stato, COLORI["sfondo_entry"])

        riga = ctk.CTkFrame(self._scroll_coda, fg_color=sfondo, corner_radius=8)
        riga.grid(row=idx, column=0, padx=4, pady=3, sticky="ew")
        riga.grid_columnconfigure(2, weight=1)

        # Miniatura
        try:
            img = Image.open(elem.path)
            img.thumbnail(THUMB_CODA, Image.LANCZOS)
            ctkimg = ctk.CTkImage(light_image=img, dark_image=img, size=img.size)
        except Exception:
            ctkimg = ctk.CTkImage(
                light_image=Image.new("RGB", THUMB_CODA, (40, 40, 55)),
                dark_image=Image.new("RGB", THUMB_CODA, (40, 40, 55)),
                size=THUMB_CODA,
            )
        self._thumb_refs.append(ctkimg)
        ctk.CTkLabel(riga, image=ctkimg, text="").grid(
            row=0, column=0, rowspan=2, padx=(8, 6), pady=6)

        # Nome file
        nome = elem.path.name
        nome_troncato = nome if len(nome) <= 28 else nome[:25] + "…"
        ctk.CTkLabel(riga, text=nome_troncato,
                     font=FONT_PICCOLO, anchor="w").grid(
            row=0, column=1, columnspan=2, padx=4, pady=(6, 2), sticky="ew")

        # Campo override dente (editabile per singola foto)
        override = ctk.CTkEntry(
            riga,
            placeholder_text="Dente (opzionale override)",
            font=("Segoe UI", 9), height=26,
        )
        if elem.dente_override:
            override.insert(0, elem.dente_override)
        override.grid(row=1, column=1, padx=4, pady=(0, 6), sticky="ew")
        # Salva il valore quando l'utente esce dal campo
        override.bind(
            "<FocusOut>",
            lambda e, el=elem, w=override: setattr(el, "dente_override", w.get().strip()),
        )

        # Stato (icona)
        stato_testo = {"attesa": "⏳", "ok": "✅", "errore": "❌"}.get(elem.stato, "")
        ctk.CTkLabel(riga, text=stato_testo, font=("Segoe UI", 14)).grid(
            row=0, column=3, rowspan=2, padx=(4, 4), pady=6)

        # Pulsante rimozione (solo se non in corso)
        if not self._in_corso:
            ctk.CTkButton(
                riga, text="✕", width=26, height=26, font=("Segoe UI", 10),
                fg_color="transparent", hover_color=COLORI["accent_bright"],
                command=lambda ix=idx: self._rimuovi_da_coda(ix),
            ).grid(row=0, column=4, rowspan=2, padx=(0, 6), pady=6)

        # Messaggio errore (se presente)
        if elem.stato == "errore" and elem.errore:
            ctk.CTkLabel(riga,
                         text=f"  ↳ {elem.errore[:50]}",
                         font=("Segoe UI", 8),
                         text_color=COLORI["rosso_err"],
                         anchor="w").grid(row=2, column=1, columnspan=3, sticky="ew", padx=4, pady=(0, 4))

    # ------------------------------------------------------------------
    # Import
    # ------------------------------------------------------------------

    def _avvia_import(self):
        # Validazioni preliminari
        if self._paziente_id is None:
            messagebox.showwarning("Paziente mancante", "Seleziona un paziente.")
            return
        if not self._coda:
            messagebox.showwarning("Coda vuota", "Aggiungi almeno un file.")
            return

        try:
            data_scatto = date.fromisoformat(self._entry_data.get().strip())
        except ValueError:
            messagebox.showwarning("Data non valida", "Formato atteso: AAAA-MM-GG")
            return

        # Blocca UI durante l'import
        self._in_corso = True
        self._btn_avvia.configure(state="disabled", text="⏳  Importazione in corso…")
        self._progressbar.set(0)
        self._log_reset()

        totale = len(self._coda)
        tag_batch = {
            "branca": self._combo_branca.get(),
            "fase":   self._combo_fase.get(),
            "note":   self._txt_note.get("1.0", "end").strip(),
        }
        dente_batch = self._combo_dente.get()

        def _job():
            ok_count = 0
            err_count = 0

            for i, elem in enumerate(self._coda):
                # Dente: usa override se presente, altrimenti tag batch
                dente_finale = elem.dente_override or dente_batch

                try:
                    fid = db.upload_foto(
                        paziente_id=self._paziente_id,
                        sorgente_path=elem.path,
                        data_scatto=data_scatto,
                        dente=dente_finale,
                        **tag_batch,
                    )
                    elem.stato   = "ok"
                    elem.foto_id = fid
                    ok_count += 1
                    self.after(0, self._log_riga,
                               f"[OK] {elem.path.name} → ID {fid}", "ok")
                except Exception as exc:
                    elem.stato  = "errore"
                    elem.errore = str(exc)
                    err_count += 1
                    self.after(0, self._log_riga,
                               f"[ERR] {elem.path.name}: {exc}", "err")

                # Aggiorna UI dal thread principale
                progresso = (i + 1) / totale
                self.after(0, self._aggiorna_progresso, progresso, i + 1, totale)

            self.after(0, self._import_completato, ok_count, err_count)

        threading.Thread(target=_job, daemon=True).start()

    def _aggiorna_progresso(self, valore: float, corrente: int, totale: int):
        self._progressbar.set(valore)
        self._lbl_progresso.configure(
            text=f"Elaborato {corrente}/{totale} ({int(valore*100)}%)")
        self._ridisegna_coda()   # aggiorna le icone stato

    def _import_completato(self, ok: int, err: int):
        self._in_corso = False
        self._btn_avvia.configure(state="normal", text="🚀  Avvia Import Massivo")
        self._log_riga(
            f"\n─── Completato: {ok} OK  |  {err} errori ───",
            "ok" if err == 0 else "warn",
        )
        self._ridisegna_coda()
        if err == 0:
            messagebox.showinfo("Import completato",
                                f"✅  {ok} fotografie importate con successo.")
        else:
            messagebox.showwarning("Import completato con errori",
                                   f"✅ {ok} ok   ❌ {err} errori.\nControlla il log.")

    # ------------------------------------------------------------------
    # Log
    # ------------------------------------------------------------------

    def _log_reset(self):
        self._txt_log.configure(state="normal")
        self._txt_log.delete("1.0", "end")
        self._txt_log.configure(state="disabled")

    def _log_riga(self, testo: str, tipo: str = ""):
        self._txt_log.configure(state="normal")
        self._txt_log.insert("end", testo + "\n")
        self._txt_log.see("end")
        self._txt_log.configure(state="disabled")

"""
ui_timeline.py
==============
Vista Timeline per paziente — storia fotografica clinica in ordine cronologico.

Layout:
  Sinistra (1/3): lista pazienti con ricerca
  Destra  (2/3):  timeline verticale con foto raggruppate per branca/trattamento

Struttura timeline:
  ┌─────────────────────────────────────────────┐
  │  [Anno · Mese]  ─────────────────────────   │
  │                                             │
  │  🏥 Conservativa                            │
  │  ├── 🔴 Pre-op    2024-01-10   [thumb]      │
  │  ├── 🟡 Intra-op  2024-01-15   [thumb]      │
  │  └── 🟢 Post-op   2024-02-20   [thumb]      │
  │                                             │
  │  🏥 Ortodonzia                              │
  │  └── 🔵 Follow-up 2024-03-01   [thumb]      │
  └─────────────────────────────────────────────┘

Click sulla thumbnail → apre il viewer zoomabile.
"""

import tkinter as tk
from tkinter import messagebox
import customtkinter as ctk
from PIL import Image
from pathlib import Path
from typing import Optional
from itertools import groupby
from datetime import date

import database as db

# ---------------------------------------------------------------------------
COLORI = {
    "bg":           "#080c18",
    "card":         "#0f1629",
    "entry_bg":     "#070b14",
    "accent":       "#0f3460",
    "accent_br":    "#e94560",
    "verde":        "#3ecf6e",
    "grigio":       "#6b7a99",
    "chiaro":       "#dce8ff",
    "divider":      "#1e2d4a",
    "line":         "#1e2d4a",
    "dot_preop":    "#e94560",
    "dot_intraop":  "#ff9800",
    "dot_postop":   "#3ecf6e",
    "dot_followup": "#4c8eff",
    "dot_default":  "#9e9e9e",
    "year_bg":      "#1a2e50",
    "branca_bg":    "#0d1b2a",
}

FONT_SEZ   = ("Segoe UI", 13, "bold")
FONT_NRM   = ("Segoe UI", 12)
FONT_SML   = ("Segoe UI", 10)
FONT_MICRO = ("Segoe UI", 9)
FONT_ANNO  = ("Segoe UI", 11, "bold")
FONT_MESE  = ("Segoe UI", 10)

FASE_COLORI = {
    "Pre-op":    COLORI["dot_preop"],
    "Intra-op":  COLORI["dot_intraop"],
    "Post-op":   COLORI["dot_postop"],
    "Follow-up": COLORI["dot_followup"],
    "Provvisorio":"#9c27b0",
}

THUMB_TL = (100, 76)   # miniatura nella timeline


# ===========================================================================
# FRAME: TIMELINE
# ===========================================================================

class TimelineFrame(ctk.CTkFrame):

    def __init__(self, master, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self._paz_id: Optional[int]   = None
        self._paz_row                 = None
        self._thumb_refs: list        = []
        self._build_ui()
        self._ricarica_pazienti()

    # ------------------------------------------------------------------

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=3)
        self.grid_rowconfigure(0, weight=1)

        # ── Sinistra: lista pazienti ───────────────────────────────────
        lc = ctk.CTkFrame(self, fg_color=COLORI["card"], corner_radius=12)
        lc.grid(row=0, column=0, padx=(0, 8), sticky="nsew")
        lc.grid_columnconfigure(0, weight=1)
        lc.grid_rowconfigure(2, weight=1)

        ctk.CTkLabel(lc, text="👤  Pazienti",
                     font=FONT_SEZ).grid(row=0, column=0, padx=16,
                                         pady=(16, 8), sticky="w")

        self._entry_cerca = ctk.CTkEntry(lc, placeholder_text="🔍 Cerca…",
                                          font=FONT_NRM, height=34)
        self._entry_cerca.grid(row=1, column=0, padx=16, pady=(0, 8), sticky="ew")
        self._entry_cerca.bind("<KeyRelease>", lambda e: self._ricarica_pazienti())

        self._lista = ctk.CTkScrollableFrame(lc, fg_color="transparent")
        self._lista.grid(row=2, column=0, padx=8, pady=(0, 8), sticky="nsew")
        self._lista.grid_columnconfigure(0, weight=1)

        # Filtri
        ctk.CTkLabel(lc, text="Filtro branca", font=FONT_MICRO,
                     text_color=COLORI["grigio"]).grid(
            row=3, column=0, padx=16, pady=(4, 2), sticky="w")
        self._combo_branca = ctk.CTkComboBox(
            lc, values=["(tutte)"] + db.BRANCHE,
            font=FONT_NRM, height=30, state="readonly")
        self._combo_branca.set("(tutte)")
        self._combo_branca.grid(row=4, column=0, padx=16, pady=(0, 8), sticky="ew")
        self._combo_branca.configure(command=lambda _: self._carica_timeline())

        # ── Destra: timeline ──────────────────────────────────────────
        rc = ctk.CTkFrame(self, fg_color=COLORI["card"], corner_radius=12)
        rc.grid(row=0, column=1, padx=(8, 0), sticky="nsew")
        rc.grid_columnconfigure(0, weight=1)
        rc.grid_rowconfigure(1, weight=1)

        # Header timeline
        self._tl_header = ctk.CTkFrame(rc, fg_color="transparent")
        self._tl_header.grid(row=0, column=0, padx=16, pady=(16, 0), sticky="ew")
        self._tl_header.grid_columnconfigure(0, weight=1)

        self._lbl_paz_nome = ctk.CTkLabel(
            self._tl_header, text="Seleziona un paziente",
            font=FONT_SEZ, text_color=COLORI["grigio"])
        self._lbl_paz_nome.grid(row=0, column=0, sticky="w")

        self._lbl_subtitolo = ctk.CTkLabel(
            self._tl_header, text="",
            font=FONT_SML, text_color=COLORI["grigio"])
        self._lbl_subtitolo.grid(row=1, column=0, sticky="w")

        # Legenda fase
        legenda = ctk.CTkFrame(self._tl_header, fg_color="transparent")
        legenda.grid(row=0, column=1, sticky="e")
        for fase, col in FASE_COLORI.items():
            dot = ctk.CTkLabel(legenda, text="●", font=("Segoe UI", 10),
                               text_color=col)
            dot.pack(side="left", padx=(0, 2))
            ctk.CTkLabel(legenda, text=fase, font=("Segoe UI", 8),
                         text_color=COLORI["grigio"]).pack(side="left", padx=(0, 8))

        # Scrollable area timeline
        self._tl_scroll = ctk.CTkScrollableFrame(rc, fg_color="transparent",
                                                  label_text="")
        self._tl_scroll.grid(row=1, column=0, padx=8, pady=(8, 8), sticky="nsew")
        self._tl_scroll.grid_columnconfigure(0, weight=1)

        # Placeholder iniziale
        ctk.CTkLabel(self._tl_scroll,
                     text="📅  La timeline del paziente apparirà qui",
                     font=FONT_NRM, text_color=COLORI["grigio"]).grid(
            row=0, column=0, pady=60)

    # ------------------------------------------------------------------
    # Pazienti
    # ------------------------------------------------------------------

    def _ricarica_pazienti(self, *_):
        righe = db.cerca_pazienti(self._entry_cerca.get())
        for w in self._lista.winfo_children():
            w.destroy()
        for i, r in enumerate(righe):
            n_foto = db.conta_foto_per_paziente(r["id"])
            sel    = (r["id"] == self._paz_id)

            riga = ctk.CTkFrame(self._lista,
                                fg_color=COLORI["accent"] if sel else COLORI["entry_bg"],
                                corner_radius=8, cursor="hand2")
            riga.grid(row=i, column=0, padx=4, pady=2, sticky="ew")
            riga.grid_columnconfigure(0, weight=1)

            ctk.CTkLabel(riga, text=f"{r['cognome']} {r['nome']}",
                         font=FONT_SML, anchor="w").grid(
                row=0, column=0, padx=(10, 4), pady=(6, 1), sticky="ew")
            ctk.CTkLabel(riga, text=f"📷 {n_foto}",
                         font=("Segoe UI", 8),
                         text_color=COLORI["grigio"]).grid(
                row=1, column=0, padx=(10, 4), pady=(0, 6), sticky="w")

            for w in (riga,):
                w.bind("<Button-1>", lambda e, rid=r["id"]: self._seleziona_paz(rid))
                w.bind("<Enter>",    lambda e, f=riga: f.configure(fg_color=COLORI["accent"]))
                w.bind("<Leave>",    lambda e, f=riga, bg=COLORI["accent"] if sel else COLORI["entry_bg"]:
                       f.configure(fg_color=bg))

    def _seleziona_paz(self, pid: int):
        self._paz_id  = pid
        self._paz_row = db.get_paziente_by_id(pid)
        self._ricarica_pazienti()
        self._carica_timeline()

    # ------------------------------------------------------------------
    # Timeline
    # ------------------------------------------------------------------

    def _carica_timeline(self):
        if self._paz_id is None:
            return

        r  = self._paz_row
        bf = self._combo_branca.get()
        branca_filtro = None if bf.startswith("(") else bf

        foto = db.cerca_foto(paziente_id=self._paz_id,
                             branca=branca_filtro,
                             ordine="data_scatto ASC")

        n = len(foto)
        self._lbl_paz_nome.configure(
            text=f"{r['cognome']} {r['nome']}",
            text_color=COLORI["chiaro"])
        self._lbl_subtitolo.configure(
            text=f"{n} fotografi{'a' if n == 1 else 'e'}"
                 + (f"  ·  {branca_filtro}" if branca_filtro else ""))

        # Svuota area
        for w in self._tl_scroll.winfo_children():
            w.destroy()
        self._thumb_refs.clear()

        if not foto:
            ctk.CTkLabel(self._tl_scroll,
                         text="Nessuna fotografia trovata per questo paziente.",
                         font=FONT_SML, text_color=COLORI["grigio"]).grid(
                row=0, column=0, pady=40)
            return

        # Raggruppa per anno → mese → branca
        self._disegna_timeline(list(foto))

    def _disegna_timeline(self, righe: list):
        """
        Organizza le righe in gruppi Anno > Mese > Branca
        e costruisce i widget nella scrollable area.
        """
        from thumbnail_cache import get_thumbnail
        from ui_viewer import ViewerFoto

        # Raggruppa per (anno, mese)
        def anno_mese(r):
            d = r["data_scatto"] or "0000-00"
            parts = d.split("-")
            return (parts[0], parts[1] if len(parts) > 1 else "00")

        tl_row = 0

        for (anno, mese), gruppo_mese in groupby(righe, key=anno_mese):
            gruppo_lista = list(gruppo_mese)

            # Header Anno / Mese
            hdr = ctk.CTkFrame(self._tl_scroll,
                               fg_color=COLORI["year_bg"], corner_radius=10)
            hdr.grid(row=tl_row, column=0, padx=4, pady=(12, 6), sticky="ew")
            mese_nome = ["—","Gen","Feb","Mar","Apr","Mag","Giu",
                         "Lug","Ago","Set","Ott","Nov","Dic"]
            try:
                m_str = mese_nome[int(mese)]
            except Exception:
                m_str = mese
            ctk.CTkLabel(hdr,
                         text=f"📅  {m_str} {anno}",
                         font=FONT_ANNO,
                         text_color=COLORI["chiaro"]).pack(
                side="left", padx=14, pady=8)
            ctk.CTkLabel(hdr,
                         text=f"{len(gruppo_lista)} foto",
                         font=("Segoe UI", 9),
                         text_color=COLORI["grigio"]).pack(side="right", padx=14)
            tl_row += 1

            # Raggruppa per branca all'interno del mese
            def get_branca(r):
                return r["branca"] or "Altro"

            for branca, grp_branca in groupby(
                    sorted(gruppo_lista, key=get_branca), key=get_branca):

                grp_list = list(grp_branca)

                # Header branca
                br_hdr = ctk.CTkFrame(self._tl_scroll,
                                      fg_color=COLORI["branca_bg"],
                                      corner_radius=8)
                br_hdr.grid(row=tl_row, column=0, padx=(24, 4), pady=(4, 2), sticky="ew")
                ctk.CTkLabel(br_hdr, text=f"🏥  {branca}",
                             font=("Segoe UI", 10, "bold"),
                             text_color=COLORI["chiaro"]).pack(
                    side="left", padx=12, pady=6)
                ctk.CTkLabel(br_hdr, text=f"{len(grp_list)} foto",
                             font=("Segoe UI", 8),
                             text_color=COLORI["grigio"]).pack(side="right", padx=12)
                tl_row += 1

                # Righe foto
                for j, r in enumerate(sorted(grp_list,
                                              key=lambda x: x["data_scatto"] or "")):
                    is_last = (j == len(grp_list) - 1)
                    tl_row = self._riga_foto(tl_row, r, is_last, righe)

        # Padding finale
        ctk.CTkFrame(self._tl_scroll, fg_color="transparent", height=20).grid(
            row=tl_row, column=0)

    def _riga_foto(self, row: int, r, is_last: bool, tutti: list) -> int:
        from thumbnail_cache import get_thumbnail
        from ui_viewer import ViewerFoto

        # Container riga
        container = ctk.CTkFrame(self._tl_scroll, fg_color="transparent")
        container.grid(row=row, column=0, padx=(36, 4), pady=1, sticky="ew")
        container.grid_columnconfigure(2, weight=1)

        # Linea verticale e dot
        fase = r["fase"] or ""
        dot_col = FASE_COLORI.get(fase, COLORI["dot_default"])

        # Dot (cerchio colorato)
        dot_frame = ctk.CTkFrame(container, fg_color="transparent", width=24)
        dot_frame.grid(row=0, column=0, sticky="ns", padx=(0, 4))
        dot_frame.grid_propagate(False)

        ctk.CTkLabel(dot_frame, text="●", font=("Segoe UI", 14),
                     text_color=dot_col, width=24).pack(pady=4)

        # Linea verticale (simulata con frame stretto)
        if not is_last:
            ctk.CTkFrame(dot_frame, width=2, height=20,
                         fg_color=COLORI["line"]).pack()

        # Card foto
        card = ctk.CTkFrame(container, fg_color=COLORI["entry_bg"],
                            corner_radius=8, cursor="hand2")
        card.grid(row=0, column=1, sticky="ew", columnspan=2)
        card.grid_columnconfigure(1, weight=1)

        # Thumbnail
        percorso = db.get_percorso_assoluto(r)
        thumb    = get_thumbnail(percorso, THUMB_TL)
        self._thumb_refs.append(thumb)

        img_lbl = ctk.CTkLabel(card, image=thumb, text="", cursor="hand2")
        img_lbl.grid(row=0, column=0, rowspan=3, padx=(8, 10), pady=6)

        # Info
        ctk.CTkLabel(card,
                     text=f"{fase or '—'}  ·  🦷 {r['dente'] or '—'}",
                     font=("Segoe UI", 10, "bold"),
                     text_color=dot_col,
                     anchor="w").grid(row=0, column=1, pady=(6, 1), sticky="ew")

        ctk.CTkLabel(card,
                     text=f"📅  {r['data_scatto'] or '—'}",
                     font=FONT_MICRO, text_color=COLORI["grigio"],
                     anchor="w").grid(row=1, column=1, sticky="ew")

        if r["note"]:
            ctk.CTkLabel(card,
                         text=f"📝  {r['note'][:80]}{'…' if len(r['note'])>80 else ''}",
                         font=FONT_MICRO, text_color=COLORI["grigio"],
                         anchor="w", wraplength=400).grid(
                row=2, column=1, pady=(0, 6), sticky="ew")

        # Click → viewer
        tutti_list = tutti
        idx = tutti_list.index(r) if r in tutti_list else 0
        for w in (card, img_lbl):
            w.bind("<Button-1>",
                   lambda e, ix=idx, tl=tutti_list:
                       ViewerFoto(self, tl, ix))
            w.bind("<Enter>", lambda e, f=card: f.configure(fg_color=COLORI["accent"]))
            w.bind("<Leave>", lambda e, f=card: f.configure(fg_color=COLORI["entry_bg"]))

        return row + 1


__all__ = ["TimelineFrame"]

"""
ui_statistiche.py  (v2 — solo statistiche)
==========================================
Pannello grafici e classifiche. La modifica tag e' stata spostata
nel pannello dedicato ui_modifica_tag.py.

Contenuto:
  - KPI counters (foto totali, pazienti, ultimo scatto)
  - Grafico a barre: Foto per Branca
  - Grafico a barre: Foto per Fase
  - Grafico a barre: Nuove foto ultimi 6 mesi
  - Classifica Top pazienti con barre di avanzamento
"""

import tkinter as tk
import customtkinter as ctk
from typing import Optional
from datetime import date

import database as db

COLORI = {
    "card_bg":      "#16213e",
    "sfondo_entry": "#0d1117",
    "canvas_bg":    "#13132a",
    "accent":       "#0f3460",
    "accent_br":    "#e94560",
    "verde":        "#4caf50",
    "grigio":       "#9e9e9e",
    "chiaro":       "#e0e0e0",
    "bar_colors": [
        "#e94560", "#4c8eff", "#4caf50", "#ff9800",
        "#9c27b0", "#00bcd4", "#f44336", "#3f51b5",
        "#8bc34a", "#ff5722",
    ],
}

FONT_SEZ   = ("Segoe UI", 13, "bold")
FONT_NRM   = ("Segoe UI", 12)
FONT_SML   = ("Segoe UI", 10)
FONT_BADGE = ("Segoe UI", 10, "bold")


class BarChart(tk.Canvas):
    PAD_L = 150; PAD_R = 56; PAD_T = 42; PAD_B = 16
    BAR_H = 24;  BAR_GAP = 10

    def __init__(self, master, data, title="", bar_colors=None, **kwargs):
        n = max(len(data), 1)
        h = self.PAD_T + n * (self.BAR_H + self.BAR_GAP) + self.PAD_B + 16
        kwargs.setdefault("bg", COLORI["canvas_bg"])
        kwargs.setdefault("highlightthickness", 0)
        kwargs["height"] = h
        super().__init__(master, **kwargs)
        self._data = data; self._title = title
        self._colors = bar_colors or COLORI["bar_colors"]
        self.bind("<Configure>", lambda e: self._draw())
        self._draw()

    def aggiorna(self, data):
        self._data = data
        n = max(len(data), 1)
        self.configure(height=self.PAD_T + n*(self.BAR_H+self.BAR_GAP) + self.PAD_B + 16)
        self._draw()

    def _draw(self):
        self.delete("all")
        W = self.winfo_width()
        if W < 80:
            return
        if self._title:
            self.create_text(W//2, 18, text=self._title,
                             fill=COLORI["chiaro"], font=("Segoe UI", 10, "bold"))
        if not self._data:
            self.create_text(W//2, self.PAD_T+24, text="Nessun dato",
                             fill=COLORI["grigio"], font=("Segoe UI", 10))
            return
        vmax = max(v for _, v in self._data) or 1
        aw   = W - self.PAD_L - self.PAD_R
        for i, (lbl, val) in enumerate(self._data):
            y0 = self.PAD_T + i*(self.BAR_H+self.BAR_GAP)
            y1 = y0 + self.BAR_H
            x0 = self.PAD_L
            x1 = x0 + max(4, int(aw * val / vmax))
            col = self._colors[i % len(self._colors)]
            self.create_rectangle(x0, y0, x1, y1, fill=col, outline="")
            if x1-x0 > 8:
                r,g,b = (int(col.lstrip("#")[k:k+2],16) for k in (0,2,4))
                lc = "#{:02x}{:02x}{:02x}".format(min(255,r+60),min(255,g+60),min(255,b+60))
                self.create_rectangle(x0, y0, x1, y0+5, fill=lc, outline="")
            ls = lbl if len(lbl)<=18 else lbl[:16]+"..."
            self.create_text(x0-6, y0+self.BAR_H//2, text=ls, anchor="e",
                             fill=COLORI["chiaro"], font=("Segoe UI", 9))
            self.create_text(x1+6, y0+self.BAR_H//2, text=str(val), anchor="w",
                             fill=col, font=("Segoe UI", 9, "bold"))


class StatisticheFrame(ctk.CTkFrame):

    def __init__(self, master, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self._build_ui()
        self.aggiorna_tutto()

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=3)
        self.grid_columnconfigure(1, weight=2)
        self.grid_rowconfigure(0, weight=1)

        # ── Sinistra: grafici ─────────────────────────────────────────
        sx = ctk.CTkScrollableFrame(self, fg_color="transparent", label_text="")
        sx.grid(row=0, column=0, padx=(0, 8), sticky="nsew")
        sx.grid_columnconfigure(0, weight=1)

        # KPI cards
        kpi = ctk.CTkFrame(sx, fg_color="transparent")
        kpi.grid(row=0, column=0, pady=(0, 10), sticky="ew")
        kpi.grid_columnconfigure((0, 1, 2), weight=1)
        self._kpi_foto     = self._kpi(kpi, "Foto totali",   "—", COLORI["accent_br"], 0)
        self._kpi_pazienti = self._kpi(kpi, "Pazienti",      "—", "#4c8eff",           1)
        self._kpi_ultimo   = self._kpi(kpi, "Ultimo scatto", "—", COLORI["verde"],     2)

        for row_i, (title, attr, extra_colors) in enumerate([
            ("📊  Foto per Branca Clinica", "_chart_branca", None),
            ("🔬  Foto per Fase Clinica",   "_chart_fase",   COLORI["bar_colors"][2:]+COLORI["bar_colors"][:2]),
            ("📅  Nuove Foto – ultimi 6 mesi", "_chart_mesi", ["#4c8eff"]*12),
        ], start=1):
            c = ctk.CTkFrame(sx, fg_color=COLORI["card_bg"], corner_radius=12)
            c.grid(row=row_i, column=0, pady=(0, 10), sticky="ew")
            c.grid_columnconfigure(0, weight=1)
            ctk.CTkLabel(c, text=title, font=FONT_SEZ).grid(
                row=0, column=0, padx=16, pady=(14, 6), sticky="w")
            chart = BarChart(c, data=[], bar_colors=extra_colors)
            chart.grid(row=1, column=0, padx=12, pady=(0, 14), sticky="ew")
            setattr(self, attr, chart)

        # ── Destra: Top pazienti ──────────────────────────────────────
        dx = ctk.CTkScrollableFrame(self, fg_color="transparent", label_text="")
        dx.grid(row=0, column=1, padx=(8, 0), sticky="nsew")
        dx.grid_columnconfigure(0, weight=1)

        ct = ctk.CTkFrame(dx, fg_color=COLORI["card_bg"], corner_radius=12)
        ct.grid(row=0, column=0, sticky="ew")
        ct.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(ct, text="🏆  Top Pazienti per Foto", font=FONT_SEZ).grid(
            row=0, column=0, padx=16, pady=(14, 8), sticky="w")
        self._frame_top = ctk.CTkFrame(ct, fg_color="transparent")
        self._frame_top.grid(row=1, column=0, padx=12, pady=(0, 14), sticky="ew")
        self._frame_top.grid_columnconfigure(0, weight=1)

    def _kpi(self, parent, titolo, valore, colore, col):
        card = ctk.CTkFrame(parent, fg_color=COLORI["card_bg"], corner_radius=12)
        card.grid(row=0, column=col, padx=4, pady=4, sticky="nsew")
        lbl = ctk.CTkLabel(card, text=valore,
                           font=("Segoe UI", 26, "bold"), text_color=colore)
        lbl.pack(padx=16, pady=(14, 2))
        ctk.CTkLabel(card, text=titolo, font=FONT_SML,
                     text_color=COLORI["grigio"]).pack(padx=16, pady=(0, 14))
        return lbl

    def aggiorna_tutto(self):
        self._aggiorna_kpi()
        self._aggiorna_branca()
        self._aggiorna_fase()
        self._aggiorna_mensile()
        self._aggiorna_top_pazienti()

    def _aggiorna_kpi(self):
        with db.get_connection() as conn:
            n_f = conn.execute("SELECT COUNT(*) FROM foto").fetchone()[0]
            n_p = conn.execute("SELECT COUNT(*) FROM pazienti").fetchone()[0]
            lst = conn.execute(
                "SELECT data_scatto FROM foto ORDER BY data_scatto DESC LIMIT 1"
            ).fetchone()
        self._kpi_foto.configure(text=str(n_f))
        self._kpi_pazienti.configure(text=str(n_p))
        self._kpi_ultimo.configure(text=lst[0] if lst else "—")

    def _aggiorna_branca(self):
        righe = db.statistiche_branche()
        self.after(80, lambda: self._chart_branca.aggiorna(
            [(r["branca"], r["totale"]) for r in righe]))

    def _aggiorna_fase(self):
        with db.get_connection() as conn:
            righe = conn.execute(
                "SELECT fase, COUNT(*) n FROM foto WHERE fase IS NOT NULL AND fase!='' "
                "GROUP BY fase ORDER BY n DESC"
            ).fetchall()
        self.after(80, lambda: self._chart_fase.aggiorna(
            [(r["fase"], r["n"]) for r in righe]))

    def _aggiorna_mensile(self):
        oggi = date.today()
        data = []
        for m in range(5, -1, -1):
            anno = oggi.year + (oggi.month - 1 - m) // 12
            mese = ((oggi.month - 1 - m) % 12) + 1
            inizio = date(anno, mese, 1)
            fine   = date(anno + 1, 1, 1) if mese == 12 else date(anno, mese + 1, 1)
            with db.get_connection() as conn:
                n = conn.execute(
                    "SELECT COUNT(*) FROM foto WHERE data_scatto>=? AND data_scatto<?",
                    (inizio.isoformat(), fine.isoformat()),
                ).fetchone()[0]
            data.append((inizio.strftime("%b %Y"), n))
        self.after(80, lambda: self._chart_mesi.aggiorna(data))

    def _aggiorna_top_pazienti(self, top_n: int = 10):
        with db.get_connection() as conn:
            righe = conn.execute(
                "SELECT p.cognome, p.nome, COUNT(f.id) n "
                "FROM pazienti p LEFT JOIN foto f ON f.paziente_id=p.id "
                "GROUP BY p.id ORDER BY n DESC LIMIT ?", (top_n,)
            ).fetchall()
        for w in self._frame_top.winfo_children():
            w.destroy()
        if not righe or righe[0]["n"] == 0:
            ctk.CTkLabel(self._frame_top, text="Nessun dato.", font=FONT_SML,
                         text_color=COLORI["grigio"]).grid(row=0, column=0, pady=12)
            return
        mx = righe[0]["n"]
        for i, r in enumerate(righe):
            n   = r["n"]
            col = COLORI["bar_colors"][i % len(COLORI["bar_colors"])]
            rf  = ctk.CTkFrame(self._frame_top, fg_color="transparent")
            rf.grid(row=i*2, column=0, sticky="ew", pady=(5, 0))
            rf.grid_columnconfigure(0, weight=1)
            ctk.CTkLabel(rf, text=f"{r['cognome']} {r['nome']}",
                         font=FONT_SML, anchor="w").grid(row=0, column=0, sticky="ew")
            ctk.CTkLabel(rf, text=f"{n} 📷", font=FONT_BADGE,
                         text_color=col, anchor="e").grid(row=0, column=1, padx=(6, 0))
            pb = ctk.CTkProgressBar(self._frame_top, height=5,
                                    progress_color=col, fg_color=COLORI["sfondo_entry"])
            pb.grid(row=i*2+1, column=0, sticky="ew", pady=(1, 2))
            pb.set(n / mx)
        self._frame_top.grid_columnconfigure(0, weight=1)


__all__ = ["StatisticheFrame"]

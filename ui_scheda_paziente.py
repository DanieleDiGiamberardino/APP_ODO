"""
ui_scheda_paziente.py
=====================
Scheda clinica completa — anagrafica estesa, allergie strutturate,
anamnesi checklist, dati facoltativi in accordion.

Tab:
  📋 Anagrafica  → identità + contatti + gruppo sanguigno
  🏥 Clinica     → AllergieEditor (tag) + AnamnesIEditor (checklist) + farmaci
  📓 Diario      → note appuntamento
  🖼️ Foto        → galleria filtrata
"""

import tkinter as tk
from tkinter import messagebox
import customtkinter as ctk
from PIL import Image
from datetime import date
from typing import Optional

import database as db

# ─────────────────────────────────────────────────────────────────────────────
# PALETTE / FONT
# ─────────────────────────────────────────────────────────────────────────────
COLORI = {
    "bg":          "#12122a",
    "card":        "#16213e",
    "entry_bg":    "#0d1117",
    "accent":      "#0f3460",
    "accent_br":   "#e94560",
    "verde":       "#4caf50",
    "grigio":      "#9e9e9e",
    "chiaro":      "#e0e0e0",
    "rosso":       "#f44336",
    "arancio":     "#ff9800",
    "diario_bg":   "#0d1b2a",
    "tag_bg":      "#1e2a3a",
    "allergia_bg": "#5c1a1a",
}

FONT_TITOLO = ("Segoe UI", 18, "bold")
FONT_SEZ    = ("Segoe UI", 12, "bold")
FONT_NRM    = ("Segoe UI", 11)
FONT_SML    = ("Segoe UI", 10)
FONT_MICRO  = ("Segoe UI", 9)

GRUPPI_SANG  = ["", "A+", "A−", "B+", "B−", "AB+", "AB−", "0+", "0−"]
SESSI        = ["", "M", "F", "Altro"]
STATI_CIVILI = ["", "Celibe/Nubile", "Coniugato/a",
                "Divorziato/a", "Vedovo/a", "Convivente"]

ALLERGIE_COMUNI = [
    "Penicillina", "Amoxicillina", "Anestetici locali",
    "FANS / Ibuprofene", "Aspirina", "Lattice",
    "Nichel", "Metacrilati", "Codeina", "Sulfamidici",
]

ANAMNESI_ITEMS = [
    ("Diabete",                                 "patologia"),
    ("Ipertensione",                            "patologia"),
    ("Malattie cardiache",                      "patologia"),
    ("Pacemaker / defibrillatore",              "patologia"),
    ("Valvulopatie / endocardite pregressa",    "patologia"),
    ("Coagulopatie / emofilia",                 "patologia"),
    ("Anticoagulanti (Warfarin / NAO)",         "farmaco"),
    ("Antiaggreganti (Aspirina / Clopidogrel)", "farmaco"),
    ("Bifosfonati (orali o EV)",                "farmaco"),
    ("Radioterapia testa-collo",                "patologia"),
    ("HIV / immunodepressione",                 "patologia"),
    ("Epatite B / C / cirrosi",                 "patologia"),
    ("Epilessia",                               "patologia"),
    ("Gravidanza / allattamento",               "patologia"),
    ("Asma / BPCO",                             "patologia"),
    ("Malattie renali croniche",                "patologia"),
    ("Osteoporosi",                             "patologia"),
    ("Ansia / fobia odontoiatrica",             "psicologico"),
]

THUMB_SIZE = (160, 120)


# ─────────────────────────────────────────────────────────────────────────────
# HELPER GENERICI
# ─────────────────────────────────────────────────────────────────────────────

def _campo(parent, label, row, col=0, height=34,
           multi=False, colspan=1, padx_extra=0):
    px = (16 + padx_extra, 8)
    ctk.CTkLabel(parent, text=label, font=FONT_MICRO,
                 text_color=COLORI["grigio"]).grid(
        row=row, column=col, columnspan=colspan,
        padx=px, pady=(8, 1), sticky="w")
    if multi:
        w = ctk.CTkTextbox(parent, font=FONT_NRM, height=height,
                           fg_color=COLORI["entry_bg"])
    else:
        w = ctk.CTkEntry(parent, font=FONT_NRM, height=height,
                         fg_color=COLORI["entry_bg"])
    w.grid(row=row + 1, column=col, columnspan=colspan,
           padx=px, pady=(0, 0), sticky="ew")
    return w


def _set_entry(w, valore):
    v = valore or ""
    if isinstance(w, ctk.CTkTextbox):
        w.delete("1.0", "end")
        w.insert("1.0", v)
    else:
        w.delete(0, "end")
        w.insert(0, v)


def _get_entry(w) -> str:
    if isinstance(w, ctk.CTkTextbox):
        return w.get("1.0", "end").strip()
    return w.get().strip()


def _calcola_eta(s: str) -> str:
    try:
        dn = date.fromisoformat(s)
        oggi = date.today()
        anni = oggi.year - dn.year - (
            (oggi.month, oggi.day) < (dn.month, dn.day))
        return f"{anni} anni"
    except Exception:
        return ""


def _safe(row, key: str) -> str:
    """Legge un campo da sqlite3.Row anche se la colonna non esiste (DB vecchio)."""
    try:
        return row[key] or ""
    except IndexError:
        return ""


# ─────────────────────────────────────────────────────────────────────────────
# WIDGET: AccordionFrame — sezione collassabile
# ─────────────────────────────────────────────────────────────────────────────

class AccordionFrame(ctk.CTkFrame):
    """Header cliccabile che espande/collassa self.inner."""

    def __init__(self, parent, titolo="Dati facoltativi",
                 aperto=False, **kwargs):
        super().__init__(parent, fg_color=COLORI["entry_bg"],
                         corner_radius=8, **kwargs)
        self.grid_columnconfigure(0, weight=1)
        self._aperto = aperto
        self._titolo = titolo

        self._btn = ctk.CTkButton(
            self, text=self._label(),
            font=FONT_SML, height=32,
            fg_color=COLORI["accent"],
            hover_color=COLORI["accent_br"],
            anchor="w",
            command=self._toggle)
        self._btn.grid(row=0, column=0, sticky="ew")

        self.inner = ctk.CTkFrame(self, fg_color="transparent")
        self.inner.grid_columnconfigure((0, 1), weight=1)

        if self._aperto:
            self.inner.grid(row=1, column=0, padx=4, pady=(4, 8), sticky="ew")

    def _label(self):
        return f"  {'▼' if self._aperto else '▶'}  {self._titolo}"

    def _toggle(self):
        self._aperto = not self._aperto
        self._btn.configure(text=self._label())
        if self._aperto:
            self.inner.grid(row=1, column=0, padx=4, pady=(4, 8), sticky="ew")
        else:
            self.inner.grid_remove()


# ─────────────────────────────────────────────────────────────────────────────
# WIDGET: AllergieEditor — tag interattivi
# ─────────────────────────────────────────────────────────────────────────────

class AllergieEditor(ctk.CTkFrame):
    """
    - Quick-tag allergie comuni (toggle ON/OFF)
    - Campo testo libero + Invio per aggiungere
    - Badge rossi rimovibili per ogni allergia attiva
    """

    def __init__(self, parent, **kwargs):
        super().__init__(parent, fg_color=COLORI["entry_bg"],
                         corner_radius=10, **kwargs)
        self._allergie: list[str] = []
        self._quick_btns: dict[str, ctk.CTkButton] = {}
        self._build()

    def _build(self):
        self.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(self,
                     text="Allergie comuni — click per attivare/disattivare:",
                     font=FONT_MICRO,
                     text_color=COLORI["grigio"]).grid(
            row=0, column=0, padx=10, pady=(8, 4), sticky="w")

        qf = ctk.CTkFrame(self, fg_color="transparent")
        qf.grid(row=1, column=0, padx=8, pady=(0, 6), sticky="ew")
        for c in range(5):
            qf.grid_columnconfigure(c, weight=1)

        for i, nome in enumerate(ALLERGIE_COMUNI):
            btn = ctk.CTkButton(
                qf, text=nome, font=("Segoe UI", 9), height=26,
                fg_color=COLORI["tag_bg"],
                hover_color=COLORI["allergia_bg"],
                corner_radius=13,
                command=lambda n=nome: self._toggle(n))
            btn.grid(row=i // 5, column=i % 5, padx=3, pady=2, sticky="ew")
            self._quick_btns[nome] = btn

        ctk.CTkLabel(self,
                     text="Altra allergia (Invio per aggiungere):",
                     font=FONT_MICRO,
                     text_color=COLORI["grigio"]).grid(
            row=2, column=0, padx=10, pady=(6, 2), sticky="w")

        ra = ctk.CTkFrame(self, fg_color="transparent")
        ra.grid(row=3, column=0, padx=8, pady=(0, 6), sticky="ew")
        ra.grid_columnconfigure(0, weight=1)

        self._e_custom = ctk.CTkEntry(
            ra, font=FONT_NRM, height=32,
            placeholder_text="Es. Eritromicina, Metronidazolo…",
            fg_color=COLORI["bg"])
        self._e_custom.grid(row=0, column=0, padx=(0, 6), sticky="ew")
        self._e_custom.bind("<Return>", lambda e: self._aggiungi_custom())

        ctk.CTkButton(ra, text="➕", width=36, height=32,
                      fg_color=COLORI["accent"],
                      command=self._aggiungi_custom).grid(row=0, column=1)

        ctk.CTkLabel(self, text="Allergie registrate:",
                     font=FONT_MICRO,
                     text_color=COLORI["grigio"]).grid(
            row=4, column=0, padx=10, pady=(8, 2), sticky="w")

        self._tags_scroll = ctk.CTkScrollableFrame(
            self, fg_color="transparent",
            height=64, orientation="horizontal")
        self._tags_scroll.grid(row=5, column=0, padx=8, pady=(0, 10), sticky="ew")

    def _toggle(self, nome: str):
        if nome in self._allergie:
            self._allergie.remove(nome)
            self._quick_btns[nome].configure(fg_color=COLORI["tag_bg"])
        else:
            self._allergie.append(nome)
            self._quick_btns[nome].configure(fg_color=COLORI["allergia_bg"])
        self._ridisegna()

    def _aggiungi_custom(self):
        t = self._e_custom.get().strip()
        if t and t not in self._allergie:
            self._allergie.append(t)
            self._ridisegna()
        self._e_custom.delete(0, "end")

    def _rimuovi(self, nome: str):
        if nome in self._allergie:
            self._allergie.remove(nome)
            if nome in self._quick_btns:
                self._quick_btns[nome].configure(fg_color=COLORI["tag_bg"])
            self._ridisegna()

    def _ridisegna(self):
        for w in self._tags_scroll.winfo_children():
            w.destroy()
        if not self._allergie:
            ctk.CTkLabel(self._tags_scroll,
                         text="Nessuna allergia registrata",
                         font=FONT_MICRO,
                         text_color=COLORI["grigio"]).pack(side="left", padx=8)
            return
        for nome in self._allergie:
            f = ctk.CTkFrame(self._tags_scroll,
                             fg_color=COLORI["allergia_bg"], corner_radius=12)
            f.pack(side="left", padx=3, pady=2)
            ctk.CTkLabel(f, text=f"⚠ {nome}",
                         font=("Segoe UI", 9, "bold"),
                         text_color="white", padx=6, pady=2).pack(side="left")
            ctk.CTkButton(f, text="✕", width=20, height=20,
                          font=("Segoe UI", 8),
                          fg_color="transparent",
                          hover_color="#8b0000",
                          command=lambda n=nome: self._rimuovi(n)).pack(
                side="left", padx=(0, 4))

    def get_value(self) -> str:
        return "; ".join(self._allergie)

    def set_value(self, valore: str):
        self._allergie = [a.strip() for a in valore.split(";") if a.strip()]
        for nome, btn in self._quick_btns.items():
            btn.configure(
                fg_color=COLORI["allergia_bg"]
                if nome in self._allergie else COLORI["tag_bg"])
        self._ridisegna()


# ─────────────────────────────────────────────────────────────────────────────
# WIDGET: AnamnesIEditor — checklist + note libere
# ─────────────────────────────────────────────────────────────────────────────

class AnamnesIEditor(ctk.CTkFrame):
    """
    Checklist patologie rilevanti in odontoiatria.
    Colori per categoria: patologia=blu / farmaco=arancio / psicologico=viola.
    """

    _COL_TIPO = {
        "patologia":   "#1a3060",
        "farmaco":     "#5c3a00",
        "psicologico": "#2a1a5c",
    }

    def __init__(self, parent, **kwargs):
        super().__init__(parent, fg_color=COLORI["entry_bg"],
                         corner_radius=10, **kwargs)
        self._vars: dict[str, ctk.BooleanVar] = {}
        self._build()

    def _build(self):
        self.grid_columnconfigure((0, 1), weight=1)

        ctk.CTkLabel(
            self,
            text="Patologie / condizioni rilevanti (spunta quelle presenti):",
            font=FONT_MICRO,
            text_color=COLORI["grigio"]).grid(
            row=0, column=0, columnspan=2, padx=10, pady=(8, 6), sticky="w")

        for i, (label, tipo) in enumerate(ANAMNESI_ITEMS):
            var = ctk.BooleanVar(value=False)
            self._vars[label] = var
            ctk.CTkCheckBox(
                self, text=label, variable=var,
                font=FONT_SML,
                checkbox_width=18, checkbox_height=18,
                fg_color=self._COL_TIPO.get(tipo, COLORI["accent"]),
                hover_color=COLORI["accent_br"],
                text_color=COLORI["chiaro"],
            ).grid(row=1 + i // 2, column=i % 2,
                   padx=(12, 6), pady=3, sticky="w")

        nr = (len(ANAMNESI_ITEMS) + 1) // 2 + 1

        ctk.CTkLabel(self, text="Note anamnestiche libere:",
                     font=FONT_MICRO,
                     text_color=COLORI["grigio"]).grid(
            row=nr, column=0, columnspan=2,
            padx=10, pady=(10, 2), sticky="w")

        self._txt = ctk.CTkTextbox(self, font=FONT_NRM, height=80,
                                    fg_color=COLORI["bg"])
        self._txt.grid(row=nr + 1, column=0, columnspan=2,
                       padx=10, pady=(0, 10), sticky="ew")

    def get_value(self) -> str:
        attive = [l for l, v in self._vars.items() if v.get()]
        parti = []
        if attive:
            parti.append("✓ " + " | ".join(attive))
        libero = self._txt.get("1.0", "end").strip()
        if libero:
            parti.append(libero)
        return "\n".join(parti)

    def set_value(self, valore: str):
        if not valore:
            return
        spuntate: set[str] = set()
        note_libere: list[str] = []
        for riga in valore.split("\n"):
            if riga.startswith("✓ "):
                for v in riga[2:].split(" | "):
                    spuntate.add(v.strip())
            else:
                note_libere.append(riga)
        for label, var in self._vars.items():
            var.set(label in spuntate)
        self._txt.delete("1.0", "end")
        self._txt.insert("1.0", "\n".join(note_libere).strip())


# ─────────────────────────────────────────────────────────────────────────────
# FINESTRA PRINCIPALE
# ─────────────────────────────────────────────────────────────────────────────

class SchedaPaziente(ctk.CTkToplevel):
    """Scheda clinica completa del paziente — finestra modale."""

    def __init__(self, master, paziente_id: int):
        super().__init__(master)
        self._pid = paziente_id
        self._thumb_refs: list = []

        r = db.get_paziente_by_id(paziente_id)
        if r is None:
            self.destroy()
            return

        self.title(f"Scheda — {r['cognome']} {r['nome']}")
        self.geometry("1060x800")
        self.minsize(860, 640)
        self.configure(fg_color=COLORI["bg"])
        self.after(50, self._porta_in_primo_piano)

        try:
            self._build_ui(r)
            self._carica_dati(r)
        except Exception as exc:
            import traceback
            ctk.CTkLabel(self,
                         text=f"⚠ Errore apertura scheda:\n{exc}",
                         font=("Segoe UI", 11),
                         text_color="#f44336",
                         wraplength=700).pack(expand=True, pady=40)
            traceback.print_exc()

    def _porta_in_primo_piano(self):
        self.lift()
        self.focus_force()
        self.attributes("-topmost", True)
        self.after(200, lambda: self.attributes("-topmost", False))

    # ── Layout ────────────────────────────────────────────────────────

    def _build_ui(self, r):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # Header
        hdr = ctk.CTkFrame(self, fg_color=COLORI["accent"],
                           corner_radius=0, height=72)
        hdr.grid(row=0, column=0, sticky="ew")
        hdr.grid_propagate(False)
        hdr.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(hdr,
                     text=r["cognome"][0].upper(),
                     font=("Segoe UI", 28, "bold"),
                     width=56, height=56,
                     fg_color=COLORI["accent_br"],
                     corner_radius=28,
                     text_color="white").grid(
            row=0, column=0, padx=(20, 14), pady=8)

        info = ctk.CTkFrame(hdr, fg_color="transparent")
        info.grid(row=0, column=1, sticky="w")
        ctk.CTkLabel(info,
                     text=f"{r['cognome']} {r['nome']}",
                     font=FONT_TITOLO,
                     text_color="white").pack(anchor="w")
        self._lbl_eta = ctk.CTkLabel(info, text="",
                                      font=FONT_SML,
                                      text_color="#cccccc")
        self._lbl_eta.pack(anchor="w")

        self._lbl_allergie_hdr = ctk.CTkLabel(
            hdr, text="",
            font=("Segoe UI", 9, "bold"),
            fg_color=COLORI["rosso"],
            corner_radius=6, padx=8, pady=3,
            text_color="white")
        self._lbl_allergie_hdr.grid(row=0, column=2, padx=(0, 10))

        ctk.CTkLabel(hdr,
                     text=f"📷 {db.conta_foto_per_paziente(self._pid)} foto",
                     font=FONT_SML,
                     text_color="#cccccc").grid(row=0, column=3, padx=(0, 10))

        self._btn_salva = ctk.CTkButton(
            hdr, text="💾 Salva",
            font=FONT_SML, width=90, height=36,
            fg_color=COLORI["verde"], hover_color="#388e3c",
            command=self._salva)
        self._btn_salva.grid(row=0, column=4, padx=(0, 16))

        # Tabs
        self._tabs = ctk.CTkTabview(
            self, fg_color=COLORI["card"],
            segmented_button_fg_color=COLORI["accent"],
            segmented_button_selected_color=COLORI["accent_br"],
            segmented_button_selected_hover_color="#c73652")
        self._tabs.grid(row=1, column=0, padx=12, pady=12, sticky="nsew")
        self.after(150, lambda: self._tabs.set("📋 Anagrafica"))

        for t in ["📋 Anagrafica", "🏥 Clinica", "📓 Diario", "🖼️ Foto"]:
            self._tabs.add(t)

        self._build_tab_anagrafica(self._tabs.tab("📋 Anagrafica"))
        self._build_tab_clinica(self._tabs.tab("🏥 Clinica"))
        self._build_tab_diario(self._tabs.tab("📓 Diario"))
        self._build_tab_foto(self._tabs.tab("🖼️ Foto"))

    # ── TAB ANAGRAFICA ────────────────────────────────────────────────

    def _build_tab_anagrafica(self, tab):
        tab.grid_columnconfigure((0, 1, 2), weight=1)

        ctk.CTkLabel(tab, text="🪪  Dati Anagrafici", font=FONT_SEZ,
                     text_color=COLORI["accent_br"]).grid(
            row=0, column=0, columnspan=3, padx=16, pady=(14, 4), sticky="w")

        self._e_cognome = _campo(tab, "Cognome *", 1, 0)
        self._e_nome    = _campo(tab, "Nome *",    1, 1)

        ctk.CTkLabel(tab, text="Sesso", font=FONT_MICRO,
                     text_color=COLORI["grigio"]).grid(
            row=1, column=2, padx=16, pady=(8, 1), sticky="w")
        self._combo_sesso = ctk.CTkComboBox(
            tab, values=SESSI, font=FONT_NRM, height=34,
            fg_color=COLORI["entry_bg"], state="readonly")
        self._combo_sesso.grid(row=2, column=2, padx=16, sticky="ew")

        ctk.CTkLabel(tab, text="Data Nascita (AAAA-MM-GG)", font=FONT_MICRO,
                     text_color=COLORI["grigio"]).grid(
            row=3, column=0, padx=16, pady=(8, 1), sticky="w")
        self._e_nascita = ctk.CTkEntry(tab, font=FONT_NRM, height=34,
                                        fg_color=COLORI["entry_bg"])
        self._e_nascita.grid(row=4, column=0, padx=16, sticky="ew")
        self._e_nascita.bind("<FocusOut>",   self._aggiorna_eta)
        self._e_nascita.bind("<KeyRelease>", self._aggiorna_eta)

        self._e_luogo_nascita = _campo(tab, "Luogo di Nascita", 3, 1)
        self._e_cf            = _campo(tab, "Codice Fiscale",   3, 2)

        ctk.CTkLabel(tab, text="📞  Contatti", font=FONT_SEZ,
                     text_color=COLORI["accent_br"]).grid(
            row=5, column=0, columnspan=3, padx=16, pady=(16, 4), sticky="w")

        self._e_tel       = _campo(tab, "Telefono",  6, 0)
        self._e_email     = _campo(tab, "Email",     6, 1)
        self._e_indirizzo = _campo(tab, "Indirizzo", 6, 2)

        ctk.CTkLabel(tab, text="🩸  Altro", font=FONT_SEZ,
                     text_color=COLORI["accent_br"]).grid(
            row=8, column=0, columnspan=3, padx=16, pady=(16, 4), sticky="w")

        ctk.CTkLabel(tab, text="Gruppo Sanguigno", font=FONT_MICRO,
                     text_color=COLORI["grigio"]).grid(
            row=9, column=0, padx=16, pady=(8, 1), sticky="w")
        self._combo_gs = ctk.CTkComboBox(
            tab, values=GRUPPI_SANG, font=FONT_NRM, height=34,
            fg_color=COLORI["entry_bg"], state="readonly")
        self._combo_gs.grid(row=10, column=0, padx=16, sticky="ew")

        self._e_medico   = _campo(tab, "Medico Curante / MMG", 9, 1)
        self._e_note_gen = _campo(tab, "Note generali",        9, 2,
                                   height=68, multi=True)

        # ── Dati facoltativi (accordion) ─────────────────────────────
        self._accordion = AccordionFrame(
            tab,
            titolo="Dati facoltativi — Stato civile & Professione",
            aperto=False)
        self._accordion.grid(row=11, column=0, columnspan=3,
                             padx=12, pady=(16, 8), sticky="ew")

        inn = self._accordion.inner

        ctk.CTkLabel(inn, text="Stato Civile", font=FONT_MICRO,
                     text_color=COLORI["grigio"]).grid(
            row=0, column=0, padx=12, pady=(8, 1), sticky="w")
        self._combo_stato_civile = ctk.CTkComboBox(
            inn, values=STATI_CIVILI, font=FONT_NRM, height=34,
            fg_color=COLORI["entry_bg"], state="readonly")
        self._combo_stato_civile.grid(row=1, column=0,
                                       padx=12, pady=(0, 10), sticky="ew")

        self._e_professione = _campo(inn, "Professione", 0, 1)

    # ── TAB CLINICA ───────────────────────────────────────────────────

    def _build_tab_clinica(self, tab):
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(3, weight=1)

        ctk.CTkLabel(tab, text="⚠️  Allergie e Intolleranze", font=FONT_SEZ,
                     text_color=COLORI["accent_br"]).grid(
            row=0, column=0, padx=16, pady=(14, 4), sticky="w")

        self._allergie_editor = AllergieEditor(tab)
        self._allergie_editor.grid(row=1, column=0, padx=12,
                                    pady=(0, 8), sticky="ew")

        ctk.CTkLabel(tab, text="🩺  Anamnesi Medica e Terapie", font=FONT_SEZ,
                     text_color=COLORI["accent_br"]).grid(
            row=2, column=0, padx=16, pady=(8, 4), sticky="w")

        scroll = ctk.CTkScrollableFrame(tab, fg_color="transparent")
        scroll.grid(row=3, column=0, padx=12, pady=(0, 8), sticky="nsew")
        scroll.grid_columnconfigure(0, weight=1)

        self._anamnesi_editor = AnamnesIEditor(scroll)
        self._anamnesi_editor.grid(row=0, column=0, padx=0,
                                    pady=(0, 8), sticky="ew")

        ctk.CTkLabel(scroll, text="💊  Farmaci / Terapie in Corso",
                     font=FONT_SEZ,
                     text_color=COLORI["accent_br"]).grid(
            row=1, column=0, padx=4, pady=(8, 4), sticky="w")

        self._e_farmaci = ctk.CTkTextbox(scroll, font=FONT_NRM, height=80,
                                          fg_color=COLORI["entry_bg"])
        self._e_farmaci.grid(row=2, column=0, padx=4, pady=(0, 10), sticky="ew")
    # ── TAB DIARIO ────────────────────────────────────────────────────

    def _build_tab_diario(self, tab):
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(1, weight=1)

        form = ctk.CTkFrame(tab, fg_color=COLORI["entry_bg"], corner_radius=10)
        form.grid(row=0, column=0, padx=8, pady=(8, 6), sticky="ew")
        form.grid_columnconfigure(1, weight=1)
        form.grid_columnconfigure(2, weight=2)

        ctk.CTkLabel(form, text="Nuova nota", font=FONT_SEZ).grid(
            row=0, column=0, columnspan=4, padx=14, pady=(10, 6), sticky="w")

        ctk.CTkLabel(form, text="Data", font=FONT_MICRO,
                     text_color=COLORI["grigio"]).grid(
            row=1, column=0, padx=(14, 4), pady=(0, 2), sticky="w")
        self._nota_data = ctk.CTkEntry(form, font=FONT_NRM, height=32, width=130)
        self._nota_data.insert(0, date.today().isoformat())
        self._nota_data.grid(row=2, column=0, padx=(14, 6),
                             pady=(0, 10), sticky="ew")

        ctk.CTkLabel(form, text="Titolo / Trattamento", font=FONT_MICRO,
                     text_color=COLORI["grigio"]).grid(
            row=1, column=1, padx=6, pady=(0, 2), sticky="w")
        self._nota_titolo = ctk.CTkEntry(form, font=FONT_NRM, height=32)
        self._nota_titolo.grid(row=2, column=1, padx=6, pady=(0, 10), sticky="ew")

        ctk.CTkLabel(form, text="Testo", font=FONT_MICRO,
                     text_color=COLORI["grigio"]).grid(
            row=1, column=2, padx=6, pady=(0, 2), sticky="w")
        self._nota_testo = ctk.CTkEntry(
            form, font=FONT_NRM, height=32,
            placeholder_text="Descrizione appuntamento…")
        self._nota_testo.grid(row=2, column=2, padx=6, pady=(0, 10), sticky="ew")

        ctk.CTkButton(form, text="➕ Aggiungi",
                      font=FONT_NRM, width=100, height=32,
                      fg_color=COLORI["verde"], hover_color="#388e3c",
                      command=self._aggiungi_nota).grid(
            row=2, column=3, padx=(6, 14), pady=(0, 10))

        self._diario_scroll = ctk.CTkScrollableFrame(
            tab, fg_color="transparent", label_text="")
        self._diario_scroll.grid(row=1, column=0, padx=8,
                                  pady=(0, 8), sticky="nsew")
        self._diario_scroll.grid_columnconfigure(0, weight=1)

    # ── TAB FOTO ──────────────────────────────────────────────────────

    def _build_tab_foto(self, tab):
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(1, weight=1)

        fr = ctk.CTkFrame(tab, fg_color="transparent")
        fr.grid(row=0, column=0, padx=8, pady=(8, 4), sticky="ew")
        fr.grid_columnconfigure(1, weight=1)
        fr.grid_columnconfigure(2, weight=1)

        ctk.CTkLabel(fr, text="Filtro:", font=FONT_SML).grid(
            row=0, column=0, padx=(0, 8))

        self._f_branca = ctk.CTkComboBox(
            fr, values=["(tutte)"] + db.BRANCHE,
            font=FONT_NRM, height=30, state="readonly")
        self._f_branca.set("(tutte)")
        self._f_branca.grid(row=0, column=1, padx=4, sticky="ew")

        self._f_fase = ctk.CTkComboBox(
            fr, values=["(tutte)"] + db.FASI,
            font=FONT_NRM, height=30, state="readonly")
        self._f_fase.set("(tutte)")
        self._f_fase.grid(row=0, column=2, padx=4, sticky="ew")

        ctk.CTkButton(fr, text="Filtra", font=FONT_SML, width=70, height=30,
                      command=self._carica_foto_tab).grid(row=0, column=3, padx=4)

        self._foto_scroll = ctk.CTkScrollableFrame(
            tab, fg_color="transparent", label_text="")
        self._foto_scroll.grid(row=1, column=0, padx=8,
                                pady=(0, 8), sticky="nsew")
        for c in range(4):
            self._foto_scroll.grid_columnconfigure(c, weight=1)

    # ── CARICAMENTO DATI ──────────────────────────────────────────────

    def _carica_dati(self, r):
        # Anagrafica
        _set_entry(self._e_nome,          r["nome"])
        _set_entry(self._e_cognome,       r["cognome"])
        _set_entry(self._e_nascita,       r["data_nascita"])
        _set_entry(self._e_cf,            r["codice_fiscale"])
        _set_entry(self._e_tel,           r["telefono"])
        _set_entry(self._e_email,         r["email"])
        _set_entry(self._e_indirizzo,     r["indirizzo"])
        _set_entry(self._e_note_gen,      r["note"])
        _set_entry(self._e_medico,        r["medico_curante"])
        _set_entry(self._e_luogo_nascita, _safe(r, "luogo_nascita"))
        _set_entry(self._e_professione,   _safe(r, "professione"))

        gs = r["gruppo_sanguigno"] or ""
        self._combo_gs.set(gs if gs in GRUPPI_SANG else "")

        sesso = _safe(r, "sesso")
        self._combo_sesso.set(sesso if sesso in SESSI else "")

        sc = _safe(r, "stato_civile")
        self._combo_stato_civile.set(sc if sc in STATI_CIVILI else "")

        # Mostra età se data nascita presente
        if r["data_nascita"]:
            self._lbl_eta.configure(text=_calcola_eta(r["data_nascita"]))

        # Se accordion ha dati → aprilo automaticamente
        if _safe(r, "stato_civile") or _safe(r, "professione"):
            if not self._accordion._aperto:
                self._accordion._toggle()

        # Clinica
        allergie_str = r["allergie"] or ""
        self._allergie_editor.set_value(allergie_str)
        self._aggiorna_badge_allergie(allergie_str)
        self._anamnesi_editor.set_value(r["anamnesi"] or "")
        _set_entry(self._e_farmaci, r["farmaci"])

        # Diario + Foto
        self._carica_diario()
        self._carica_foto_tab()

    def _aggiorna_eta(self, _event=None):
        s = self._e_nascita.get().strip()
        self._lbl_eta.configure(
            text=_calcola_eta(s) if len(s) == 10 else "")

    def _aggiorna_badge_allergie(self, s: str):
        if s.strip():
            ante = s[:50] + ("…" if len(s) > 50 else "")
            self._lbl_allergie_hdr.configure(text=f"⚠ {ante}")
        else:
            self._lbl_allergie_hdr.configure(text="")

    # ── SALVATAGGIO ───────────────────────────────────────────────────

    def _salva(self):
        nome    = _get_entry(self._e_nome)
        cognome = _get_entry(self._e_cognome)
        if not nome or not cognome:
            messagebox.showwarning("Campi obbligatori",
                                   "Nome e Cognome sono richiesti.",
                                   parent=self)
            return

        nascita_str = _get_entry(self._e_nascita)
        if nascita_str:
            try:
                date.fromisoformat(nascita_str)
            except ValueError:
                messagebox.showwarning("Data non valida",
                                       "Formato atteso: AAAA-MM-GG",
                                       parent=self)
                return

        allergie_val = self._allergie_editor.get_value()
        anamnesi_val = self._anamnesi_editor.get_value()

        db.aggiorna_paziente(
            self._pid,
            nome=nome,
            cognome=cognome,
            telefono=_get_entry(self._e_tel),
            email=_get_entry(self._e_email),
            indirizzo=_get_entry(self._e_indirizzo),
            data_nascita=nascita_str or None,
            codice_fiscale=_get_entry(self._e_cf),
            gruppo_sanguigno=self._combo_gs.get(),
            note=_get_entry(self._e_note_gen),
            medico_curante=_get_entry(self._e_medico),
            allergie=allergie_val,
            anamnesi=anamnesi_val,
            farmaci=_get_entry(self._e_farmaci),
            sesso=self._combo_sesso.get(),
            stato_civile=self._combo_stato_civile.get(),
            professione=_get_entry(self._e_professione),
            luogo_nascita=_get_entry(self._e_luogo_nascita),
        )

        self.title(f"Scheda — {cognome} {nome}")
        self._aggiorna_badge_allergie(allergie_val)
        self._btn_salva.configure(text="✅ Salvato")
        self.after(1800, lambda: self._btn_salva.configure(text="💾 Salva"))

    # ── DIARIO ────────────────────────────────────────────────────────

    def _aggiungi_nota(self):
        testo  = self._nota_testo.get().strip()
        titolo = self._nota_titolo.get().strip()
        data_s = self._nota_data.get().strip()
        if not testo:
            messagebox.showwarning("Campo vuoto",
                                   "Inserisci il testo della nota.",
                                   parent=self)
            return
        try:
            data_obj = date.fromisoformat(data_s)
        except ValueError:
            messagebox.showwarning("Data non valida",
                                   "Formato: AAAA-MM-GG", parent=self)
            return
        db.aggiungi_nota(self._pid, testo, titolo, data_obj)
        self._nota_testo.delete(0, "end")
        self._nota_titolo.delete(0, "end")
        self._carica_diario()

    def _carica_diario(self):
        for w in self._diario_scroll.winfo_children():
            w.destroy()
        note = db.get_note_paziente(self._pid)
        if not note:
            ctk.CTkLabel(self._diario_scroll,
                         text="Nessuna nota ancora registrata.",
                         font=FONT_SML,
                         text_color=COLORI["grigio"]).grid(
                row=0, column=0, pady=20)
            return
        for i, n in enumerate(note):
            self._card_nota(i, n)

    def _card_nota(self, idx: int, n):
        card = ctk.CTkFrame(self._diario_scroll,
                            fg_color=COLORI["diario_bg"], corner_radius=8)
        card.grid(row=idx, column=0, padx=4, pady=3, sticky="ew")
        card.grid_columnconfigure(1, weight=1)

        barre = [COLORI["accent_br"], COLORI["accent"], COLORI["verde"]]
        ctk.CTkFrame(card, width=4, height=50, corner_radius=2,
                     fg_color=barre[idx % 3]).grid(
            row=0, column=0, rowspan=2, padx=(8, 10), pady=8, sticky="ns")

        ctk.CTkLabel(card,
                     text=f"{n['data']} • {n['titolo'] or 'Appuntamento'}",
                     font=("Segoe UI", 10, "bold"),
                     text_color=COLORI["chiaro"],
                     anchor="w").grid(
            row=0, column=1, sticky="ew", pady=(8, 1), padx=(0, 8))

        ctk.CTkLabel(card,
                     text=n["testo"],
                     font=FONT_MICRO,
                     text_color=COLORI["grigio"],
                     anchor="w",
                     wraplength=700,
                     justify="left").grid(
            row=1, column=1, sticky="ew", pady=(0, 8), padx=(0, 8))

        ctk.CTkButton(card, text="✕", width=28, height=28,
                      font=("Segoe UI", 10),
                      fg_color="transparent",
                      hover_color=COLORI["rosso"],
                      command=lambda nid=n["id"]: self._elimina_nota(nid)).grid(
            row=0, column=2, rowspan=2, padx=(0, 8))

    def _elimina_nota(self, nota_id: int):
        if messagebox.askyesno("Elimina nota",
                               "Eliminare questa nota dal diario?",
                               icon="warning",
                               default=messagebox.NO,
                               parent=self):
            db.elimina_nota(nota_id)
            self._carica_diario()

    # ── GALLERIA FOTO ─────────────────────────────────────────────────

    def _carica_foto_tab(self):
        for w in self._foto_scroll.winfo_children():
            w.destroy()
        self._thumb_refs.clear()

        branca = self._f_branca.get()
        fase   = self._f_fase.get()

        righe = db.cerca_foto(
            paziente_id=self._pid,
            branca=None if branca.startswith("(") else branca,
            fase=None   if fase.startswith("(")   else fase,
        )

        if not righe:
            ctk.CTkLabel(self._foto_scroll,
                         text="Nessuna fotografia trovata per questo paziente.",
                         font=FONT_SML,
                         text_color=COLORI["grigio"]).grid(
                row=0, column=0, columnspan=4, pady=30)
            return

        for idx, r in enumerate(righe):
            self._card_foto(idx // 4, idx % 4, r, idx, list(righe))

    def _card_foto(self, row: int, col: int, r, idx: int, tutti: list):
        from ui_viewer import ViewerFoto

        card = ctk.CTkFrame(self._foto_scroll,
                            fg_color=COLORI["entry_bg"], corner_radius=8)
        card.grid(row=row, column=col, padx=6, pady=6, sticky="nsew")
        card.grid_columnconfigure(0, weight=1)

        percorso = db.get_percorso_assoluto(r)
        try:
            img = Image.open(percorso)
            img.thumbnail(THUMB_SIZE, Image.LANCZOS)
            thumb = ctk.CTkImage(light_image=img, dark_image=img, size=img.size)
        except Exception:
            placeholder = Image.new("RGB", THUMB_SIZE, (40, 40, 55))
            thumb = ctk.CTkImage(light_image=placeholder,
                                 dark_image=placeholder, size=THUMB_SIZE)
        self._thumb_refs.append(thumb)

        img_lbl = ctk.CTkLabel(card, image=thumb, text="", cursor="hand2")
        img_lbl.grid(row=0, column=0, padx=4, pady=(6, 2), sticky="ew")
        img_lbl.bind("<Button-1>",
                     lambda e, ix=idx, t=tutti: ViewerFoto(self, t, ix))

        badge_row = ctk.CTkFrame(card, fg_color="transparent")
        badge_row.grid(row=1, column=0, padx=4, pady=1, sticky="ew")
        for testo, colore in [
            (r["branca"] or "—", COLORI["accent"]),
            (r["fase"]   or "—", COLORI["accent_br"]),
        ]:
            ctk.CTkLabel(badge_row, text=testo,
                         font=("Segoe UI", 8, "bold"),
                         fg_color=colore, corner_radius=4,
                         text_color="white", padx=4, pady=1).pack(
                side="left", padx=(0, 3))

        ctk.CTkLabel(card,
                     text=f"🦷 {r['dente'] or '—'}  📅 {r['data_scatto'] or '—'}",
                     font=FONT_MICRO,
                     text_color=COLORI["grigio"]).grid(
            row=2, column=0, padx=6, pady=(0, 6), sticky="w")
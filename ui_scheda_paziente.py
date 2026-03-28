"""
ui_scheda_paziente.py
=====================
Finestra modale di scheda clinica completa per un paziente.

Struttura a tab (CTkTabview):
  📋 Anagrafica   → dati anagrafici + contatti + gruppo sanguigno
  🏥 Clinica      → anamnesi, allergie, farmaci, medico curante
  📓 Diario       → storico note appuntamento (add / delete)
  🖼️  Fotografie   → galleria filtrata del paziente con apertura viewer

Apertura:
    from ui_scheda_paziente import SchedaPaziente
    SchedaPaziente(master, paziente_id=5)
"""

import tkinter as tk
from tkinter import messagebox
import customtkinter as ctk
from PIL import Image
from datetime import date
from pathlib import Path
from typing import Optional

import database as db

# ---------------------------------------------------------------------------
# Palette / Font (coerenti con il resto dell'app)
# ---------------------------------------------------------------------------

COLORI = {
    "bg":           "#12122a",
    "card":         "#16213e",
    "entry_bg":     "#0d1117",
    "accent":       "#0f3460",
    "accent_br":    "#e94560",
    "verde":        "#4caf50",
    "grigio":       "#9e9e9e",
    "chiaro":       "#e0e0e0",
    "rosso":        "#f44336",
    "arancio":      "#ff9800",
    "diario_bg":    "#0d1b2a",
}

FONT_TITOLO  = ("Segoe UI", 18, "bold")
FONT_SEZ     = ("Segoe UI", 12, "bold")
FONT_NRM     = ("Segoe UI", 11)
FONT_SML     = ("Segoe UI", 10)
FONT_MICRO   = ("Segoe UI", 9)

GRUPPI_SANG  = ["", "A+", "A−", "B+", "B−", "AB+", "AB−", "0+", "0−"]
THUMB_SIZE   = (160, 120)


# ===========================================================================
# HELPER — campo label + entry/textbox
# ===========================================================================

def _campo(parent, label: str, row: int, col: int = 0,
           height: int = 34, multi: bool = False,
           colspan: int = 1, padx_extra: int = 0) -> "ctk.CTkEntry | ctk.CTkTextbox":
    px = (16 + padx_extra, 8)
    ctk.CTkLabel(parent, text=label, font=FONT_MICRO,
                 text_color=COLORI["grigio"]).grid(
        row=row, column=col, columnspan=colspan,
        padx=px, pady=(8, 1), sticky="w")
    if multi:
        w = ctk.CTkTextbox(parent, font=FONT_NRM, height=height,
                           fg_color=COLORI["entry_bg"])
        w.grid(row=row + 1, column=col, columnspan=colspan,
               padx=px, pady=(0, 0), sticky="ew")
    else:
        w = ctk.CTkEntry(parent, font=FONT_NRM, height=height,
                         fg_color=COLORI["entry_bg"])
        w.grid(row=row + 1, column=col, columnspan=colspan,
               padx=px, pady=(0, 0), sticky="ew")
    return w


def _set_entry(w, valore: Optional[str]):
    """Popola un CTkEntry o CTkTextbox con il valore dal DB."""
    v = valore or ""
    if isinstance(w, ctk.CTkTextbox):
        w.delete("1.0", "end")
        w.insert("1.0", v)
    else:
        w.delete(0, "end")
        w.insert(0, v)


def _get_entry(w) -> str:
    """Legge il valore da CTkEntry o CTkTextbox."""
    if isinstance(w, ctk.CTkTextbox):
        return w.get("1.0", "end").strip()
    return w.get().strip()


# ===========================================================================
# FINESTRA PRINCIPALE
# ===========================================================================

class SchedaPaziente(ctk.CTkToplevel):
    """
    Scheda clinica completa del paziente — finestra modale.
    """

    def __init__(self, master, paziente_id: int):
        super().__init__(master)
        self._pid = paziente_id
        self._thumb_refs: list = []   # anti-GC miniature

        r = db.get_paziente_by_id(paziente_id)
        if r is None:
            self.destroy()
            return

        self.title(f"Scheda — {r['cognome']} {r['nome']}")
        self.geometry("980x720")
        self.minsize(820, 600)
        self.configure(fg_color=COLORI["bg"])
        # Porta la finestra in primo piano — fix "apre in background" su Windows
        self.after(50, self._porta_in_primo_piano)
        try:
            self._build_ui(r)
            self._carica_dati(r)
        except Exception as exc:
            import traceback
            ctk.CTkLabel(
            self, text=f"⚠ Errore apertura scheda:\n{exc}",
            font=("Segoe UI", 11), text_color="#f44336", wraplength=700
            ).pack(expand=True, pady=40)
            traceback.print_exc()

    def _porta_in_primo_piano(self):
        self.lift()
        self.focus_force()
        self.attributes("-topmost", True)
        self.after(200, lambda: self.attributes("-topmost", False))

    # ------------------------------------------------------------------
    # Layout principale
    # ------------------------------------------------------------------

    def _build_ui(self, r):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # ── Header ────────────────────────────────────────────────────
        hdr = ctk.CTkFrame(self, fg_color=COLORI["accent"], corner_radius=0, height=70)
        hdr.grid(row=0, column=0, sticky="ew")
        hdr.grid_propagate(False)
        hdr.grid_columnconfigure(1, weight=1)

        # Avatar grande
        ctk.CTkLabel(hdr,
                     text=r["cognome"][0].upper(),
                     font=("Segoe UI", 28, "bold"),
                     width=56, height=56,
                     fg_color=COLORI["accent_br"],
                     corner_radius=28,
                     text_color="white").grid(row=0, column=0, padx=(20, 14), pady=7)

        nome_completo = f"{r['cognome']} {r['nome']}"
        ctk.CTkLabel(hdr, text=nome_completo,
                     font=FONT_TITOLO,
                     text_color="white").grid(row=0, column=1, sticky="w")

        n_foto = db.conta_foto_per_paziente(self._pid)
        ctk.CTkLabel(hdr,
                     text=f"📷 {n_foto} foto",
                     font=FONT_SML,
                     text_color="#cccccc").grid(row=0, column=2, padx=(0, 16))

        # Pulsante salva (sempre visibile nell'header)
        self._btn_salva = ctk.CTkButton(
            hdr, text="💾  Salva",
            font=FONT_SML, width=90, height=36,
            fg_color=COLORI["verde"], hover_color="#388e3c",
            command=self._salva_anagrafica,
        )
        self._btn_salva.grid(row=0, column=3, padx=(0, 16))

        # ── Tab view ──────────────────────────────────────────────────
        self._tabs = ctk.CTkTabview(
            self,
            fg_color=COLORI["card"],
            segmented_button_fg_color=COLORI["accent"],
            segmented_button_selected_color=COLORI["accent_br"],
            segmented_button_selected_hover_color="#c73652",
        )
        self._tabs.grid(row=1, column=0, padx=12, pady=12, sticky="nsew")
        self.after(150,lambda: self._tabs.set("📋 Anagrafica"))  # fix focus su primo tab

        for nome_tab in ["📋 Anagrafica", "🏥 Clinica", "📓 Diario", "🖼️  Foto"]:
            self._tabs.add(nome_tab)

        self._build_tab_anagrafica(self._tabs.tab("📋 Anagrafica"))
        self._build_tab_clinica(self._tabs.tab("🏥 Clinica"))
        self._build_tab_diario(self._tabs.tab("📓 Diario"))
        self._build_tab_foto(self._tabs.tab("🖼️  Foto"))

    # ------------------------------------------------------------------
    # TAB: Anagrafica
    # ------------------------------------------------------------------

    def _build_tab_anagrafica(self, tab):
        tab.grid_columnconfigure((0, 1), weight=1)

        ctk.CTkLabel(tab, text="Dati Anagrafici", font=FONT_SEZ,
                     text_color=COLORI["accent_br"]).grid(
            row=0, column=0, columnspan=2, padx=16, pady=(14, 4), sticky="w")

        # Riga 1: Nome / Cognome
        self._e_nome    = _campo(tab, "Nome *",    1, 0)
        self._e_cognome = _campo(tab, "Cognome *", 1, 1)

        # Riga 2: Data nascita / CF
        self._e_nascita = _campo(tab, "Data Nascita (AAAA-MM-GG)", 3, 0)
        self._e_cf      = _campo(tab, "Codice Fiscale",             3, 1)

        ctk.CTkLabel(tab, text="Contatti", font=FONT_SEZ,
                     text_color=COLORI["accent_br"]).grid(
            row=5, column=0, columnspan=2, padx=16, pady=(16, 4), sticky="w")

        self._e_tel      = _campo(tab, "Telefono",  6, 0)
        self._e_email    = _campo(tab, "Email",     6, 1)
        self._e_indirizzo= _campo(tab, "Indirizzo", 8, 0, colspan=2)

        ctk.CTkLabel(tab, text="Altro", font=FONT_SEZ,
                     text_color=COLORI["accent_br"]).grid(
            row=10, column=0, columnspan=2, padx=16, pady=(16, 4), sticky="w")

        # Gruppo sanguigno (combo) + note generali
        ctk.CTkLabel(tab, text="Gruppo Sanguigno", font=FONT_MICRO,
                     text_color=COLORI["grigio"]).grid(
            row=11, column=0, padx=16, pady=(8, 1), sticky="w")
        self._combo_gs = ctk.CTkComboBox(tab, values=GRUPPI_SANG,
                                          font=FONT_NRM, height=34,
                                          fg_color=COLORI["entry_bg"],
                                          state="readonly")
        self._combo_gs.grid(row=12, column=0, padx=16, pady=(0, 0), sticky="ew")

        self._e_note_gen = _campo(tab, "Note generali", 11, 1,
                                   height=68, multi=True)

    # ------------------------------------------------------------------
    # TAB: Clinica
    # ------------------------------------------------------------------

    def _build_tab_clinica(self, tab):
        tab.grid_columnconfigure((0, 1), weight=1)

        ctk.CTkLabel(tab, text="Informazioni Cliniche", font=FONT_SEZ,
                     text_color=COLORI["accent_br"]).grid(
            row=0, column=0, columnspan=2, padx=16, pady=(14, 4), sticky="w")

        self._e_medico   = _campo(tab, "Medico Curante",   1, 0, colspan=2)
        self._e_allergie = _campo(tab, "Allergie",         3, 0, colspan=2,
                                   height=80, multi=True)
        self._e_anamnesi = _campo(tab, "Anamnesi Patologica Remota", 5, 0,
                                   colspan=2, height=110, multi=True)
        self._e_farmaci  = _campo(tab, "Farmaci / Terapie in Corso", 7, 0,
                                   colspan=2, height=90, multi=True)

        # Badge allergie (visual reminder)
        self._lbl_allert = ctk.CTkLabel(
            tab, text="",
            font=FONT_MICRO,
            fg_color=COLORI["rosso"],
            corner_radius=6, padx=8, pady=3,
            text_color="white",
        )
        self._lbl_allert.grid(row=0, column=1, padx=16, pady=(14, 4), sticky="e")

    # ------------------------------------------------------------------
    # TAB: Diario appuntamenti
    # ------------------------------------------------------------------

    def _build_tab_diario(self, tab):
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(1, weight=1)

        # Form aggiunta nota
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
        self._nota_data.grid(row=2, column=0, padx=(14, 6), pady=(0, 10), sticky="ew")

        ctk.CTkLabel(form, text="Titolo / Trattamento", font=FONT_MICRO,
                     text_color=COLORI["grigio"]).grid(
            row=1, column=1, padx=6, pady=(0, 2), sticky="w")
        self._nota_titolo = ctk.CTkEntry(form, font=FONT_NRM, height=32)
        self._nota_titolo.grid(row=2, column=1, padx=6, pady=(0, 10), sticky="ew")

        ctk.CTkLabel(form, text="Testo", font=FONT_MICRO,
                     text_color=COLORI["grigio"]).grid(
            row=1, column=2, padx=6, pady=(0, 2), sticky="w")
        self._nota_testo = ctk.CTkEntry(form, font=FONT_NRM, height=32,
                                         placeholder_text="Descrizione appuntamento…")
        self._nota_testo.grid(row=2, column=2, padx=6, pady=(0, 10), sticky="ew")

        ctk.CTkButton(form, text="➕ Aggiungi",
                      font=FONT_NRM, width=100, height=32,
                      fg_color=COLORI["verde"], hover_color="#388e3c",
                      command=self._aggiungi_nota).grid(
            row=2, column=3, padx=(6, 14), pady=(0, 10))

        # Lista note scrollabile
        self._diario_scroll = ctk.CTkScrollableFrame(
            tab, fg_color="transparent", label_text="")
        self._diario_scroll.grid(row=1, column=0, padx=8, pady=(0, 8), sticky="nsew")
        self._diario_scroll.grid_columnconfigure(0, weight=1)

    # ------------------------------------------------------------------
    # TAB: Foto
    # ------------------------------------------------------------------

    def _build_tab_foto(self, tab):
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(1, weight=1)

        # Filtro rapido
        filtro_row = ctk.CTkFrame(tab, fg_color="transparent")
        filtro_row.grid(row=0, column=0, padx=8, pady=(8, 4), sticky="ew")
        filtro_row.grid_columnconfigure(1, weight=1)
        filtro_row.grid_columnconfigure(2, weight=1)
        filtro_row.grid_columnconfigure(3, weight=1)

        ctk.CTkLabel(filtro_row, text="Filtro:", font=FONT_SML).grid(
            row=0, column=0, padx=(0, 8))

        self._f_branca = ctk.CTkComboBox(
            filtro_row, values=["(tutte)"] + db.BRANCHE,
            font=FONT_NRM, height=30, state="readonly")
        self._f_branca.set("(tutte)")
        self._f_branca.grid(row=0, column=1, padx=4, sticky="ew")

        self._f_fase = ctk.CTkComboBox(
            filtro_row, values=["(tutte)"] + db.FASI,
            font=FONT_NRM, height=30, state="readonly")
        self._f_fase.set("(tutte)")
        self._f_fase.grid(row=0, column=2, padx=4, sticky="ew")

        ctk.CTkButton(filtro_row, text="Filtra", font=FONT_SML,
                      width=70, height=30,
                      command=self._carica_foto_tab).grid(row=0, column=3, padx=4)

        self._foto_scroll = ctk.CTkScrollableFrame(
            tab, fg_color="transparent", label_text="")
        self._foto_scroll.grid(row=1, column=0, padx=8, pady=(0, 8), sticky="nsew")
        for c in range(4):
            self._foto_scroll.grid_columnconfigure(c, weight=1)

    # ------------------------------------------------------------------
    # Caricamento dati dal DB
    # ------------------------------------------------------------------

    def _carica_dati(self, r):
        """Popola tutti i campi con i valori del record paziente."""
        # Anagrafica
        _set_entry(self._e_nome,      r["nome"])
        _set_entry(self._e_cognome,   r["cognome"])
        _set_entry(self._e_nascita,   r["data_nascita"])
        _set_entry(self._e_cf,        r["codice_fiscale"])
        _set_entry(self._e_tel,       r["telefono"])
        _set_entry(self._e_email,     r["email"])
        _set_entry(self._e_indirizzo, r["indirizzo"])
        _set_entry(self._e_note_gen,  r["note"])

        gs = r["gruppo_sanguigno"] or ""
        self._combo_gs.set(gs if gs in GRUPPI_SANG else "")

        # Clinica
        _set_entry(self._e_medico,   r["medico_curante"])
        _set_entry(self._e_allergie, r["allergie"])
        _set_entry(self._e_anamnesi, r["anamnesi"])
        _set_entry(self._e_farmaci,  r["farmaci"])

        # Badge allergie
        allergie = (r["allergie"] or "").strip()
        if allergie:
            self._lbl_allert.configure(text=f"⚠️  {allergie[:40]}")
        else:
            self._lbl_allert.configure(text="")

        # Diario e foto
        self._carica_diario()
        self._carica_foto_tab()

    # ------------------------------------------------------------------
    # Salvataggio anagrafica + clinica
    # ------------------------------------------------------------------

    def _salva_anagrafica(self):
        nome    = _get_entry(self._e_nome)
        cognome = _get_entry(self._e_cognome)
        if not nome or not cognome:
            messagebox.showwarning("Campi obbligatori", "Nome e Cognome sono richiesti.",
                                   parent=self)
            return

        # Validazione data nascita
        nascita_str = _get_entry(self._e_nascita)
        if nascita_str:
            try:
                date.fromisoformat(nascita_str)
            except ValueError:
                messagebox.showwarning("Data non valida",
                                       "Data Nascita: formato AAAA-MM-GG",
                                       parent=self)
                return

        db.aggiorna_paziente(
            self._pid,
            nome=nome, cognome=cognome,
            telefono=_get_entry(self._e_tel),
            email=_get_entry(self._e_email),
            indirizzo=_get_entry(self._e_indirizzo),
            data_nascita=nascita_str or None,
            codice_fiscale=_get_entry(self._e_cf),
            gruppo_sanguigno=self._combo_gs.get(),
            note=_get_entry(self._e_note_gen),
            medico_curante=_get_entry(self._e_medico),
            allergie=_get_entry(self._e_allergie),
            anamnesi=_get_entry(self._e_anamnesi),
            farmaci=_get_entry(self._e_farmaci),
        )

        # Aggiorna titolo finestra
        self.title(f"Scheda — {cognome} {nome}")

        # Aggiorna badge allergie
        allergie = _get_entry(self._e_allergie)
        self._lbl_allert.configure(
            text=f"⚠️  {allergie[:40]}" if allergie else "")

        self._btn_salva.configure(text="✅  Salvato")
        self.after(1800, lambda: self._btn_salva.configure(text="💾  Salva"))

    # ------------------------------------------------------------------
    # Diario appuntamenti
    # ------------------------------------------------------------------

    def _aggiungi_nota(self):
        testo  = self._nota_testo.get().strip()
        titolo = self._nota_titolo.get().strip()
        data_s = self._nota_data.get().strip()

        if not testo:
            messagebox.showwarning("Campo vuoto", "Inserisci il testo della nota.",
                                   parent=self)
            return
        try:
            data_obj = date.fromisoformat(data_s)
        except ValueError:
            messagebox.showwarning("Data non valida", "Formato: AAAA-MM-GG",
                                   parent=self)
            return

        db.aggiungi_nota(self._pid, testo, titolo, data_obj)
        self._nota_testo.delete(0, "end")
        self._nota_titolo.delete(0, "end")
        self._carica_diario()

    def _carica_diario(self):
        """Ridisegna l'elenco delle note appuntamento."""
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
        """Singola card di nota nel diario."""
        card = ctk.CTkFrame(self._diario_scroll,
                            fg_color=COLORI["diario_bg"], corner_radius=8)
        card.grid(row=idx, column=0, padx=4, pady=3, sticky="ew")
        card.grid_columnconfigure(1, weight=1)

        # Colore barra laterale (alterna)
        colori_barra = [COLORI["accent_br"], COLORI["accent"], COLORI["verde"]]
        barra = ctk.CTkFrame(card, width=4, height=50, corner_radius=2,
                             fg_color=colori_barra[idx % 3])
        barra.grid(row=0, column=0, rowspan=2, padx=(8, 10), pady=8, sticky="ns")

        # Data + titolo
        titolo = n["titolo"] or "Appuntamento"
        ctk.CTkLabel(card,
                     text=f"{n['data']}  •  {titolo}",
                     font=("Segoe UI", 10, "bold"),
                     text_color=COLORI["chiaro"],
                     anchor="w").grid(row=0, column=1, sticky="ew", pady=(8, 1), padx=(0, 8))

        # Testo nota
        ctk.CTkLabel(card,
                     text=n["testo"],
                     font=FONT_MICRO,
                     text_color=COLORI["grigio"],
                     anchor="w",
                     wraplength=700,
                     justify="left").grid(row=1, column=1, sticky="ew",
                                          pady=(0, 8), padx=(0, 8))

        # Pulsante elimina nota
        ctk.CTkButton(card, text="✕", width=28, height=28,
                      font=("Segoe UI", 10),
                      fg_color="transparent", hover_color=COLORI["rosso"],
                      command=lambda nid=n["id"]: self._elimina_nota(nid)).grid(
            row=0, column=2, rowspan=2, padx=(0, 8))

    def _elimina_nota(self, nota_id: int):
        if messagebox.askyesno("Elimina nota",
                               "Eliminare questa nota dal diario?",
                               icon="warning", default=messagebox.NO,
                               parent=self):
            db.elimina_nota(nota_id)
            self._carica_diario()

    # ------------------------------------------------------------------
    # Galleria foto del paziente
    # ------------------------------------------------------------------

    def _carica_foto_tab(self):
        """Carica e mostra le foto del paziente con i filtri attivi."""
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
        """Mini-card foto con thumbnail e badge tag."""
        from ui_viewer import ViewerFoto

        card = ctk.CTkFrame(self._foto_scroll, fg_color=COLORI["entry_bg"],
                            corner_radius=8)
        card.grid(row=row, column=col, padx=6, pady=6, sticky="nsew")
        card.grid_columnconfigure(0, weight=1)

        percorso = db.get_percorso_assoluto(r)
        try:
            img = Image.open(percorso)
            img.thumbnail(THUMB_SIZE, Image.LANCZOS)
            thumb = ctk.CTkImage(light_image=img, dark_image=img, size=img.size)
        except Exception:
            placeholder = Image.new("RGB", THUMB_SIZE, (40, 40, 55))
            thumb = ctk.CTkImage(light_image=placeholder, dark_image=placeholder,
                                 size=THUMB_SIZE)
        self._thumb_refs.append(thumb)

        img_lbl = ctk.CTkLabel(card, image=thumb, text="", cursor="hand2")
        img_lbl.grid(row=0, column=0, padx=4, pady=(6, 2), sticky="ew")
        img_lbl.bind("<Button-1>",
                     lambda e, ix=idx, t=tutti: ViewerFoto(self, t, ix))

        # Tag badges
        badge_row = ctk.CTkFrame(card, fg_color="transparent")
        badge_row.grid(row=1, column=0, padx=4, pady=1, sticky="ew")
        for testo, colore in [
            (r["branca"] or "—", COLORI["accent"]),
            (r["fase"]   or "—", COLORI["accent_br"]),
        ]:
            ctk.CTkLabel(badge_row, text=testo, font=("Segoe UI", 8, "bold"),
                         fg_color=colore, corner_radius=4,
                         text_color="white", padx=4, pady=1).pack(
                side="left", padx=(0, 3))

        ctk.CTkLabel(card,
                     text=f"🦷 {r['dente'] or '—'}  📅 {r['data_scatto'] or '—'}",
                     font=FONT_MICRO,
                     text_color=COLORI["grigio"]).grid(
            row=2, column=0, padx=6, pady=(0, 6), sticky="w")

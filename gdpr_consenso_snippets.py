# =============================================================================
#  DentalPhoto Pro — Consenso Fotografico GDPR
#  Tre snippet pronti all'integrazione, numerati per chiarezza.
# =============================================================================


# ─────────────────────────────────────────────────────────────────────────────
#  SNIPPET 1 — database.py
#  Incolla queste funzioni nel tuo database.py esistente.
# ─────────────────────────────────────────────────────────────────────────────
import sqlite3
from datetime import datetime

DB_PATH = "dentalphoto.db"   # ← adatta al tuo percorso reale


def migra_consenso_privacy() -> None:
    """
    ALTER TABLE sicuro: aggiunge `consenso_privacy` solo se non esiste già.
    Chiamare UNA SOLA VOLTA all'avvio dell'app (prima di aprire qualsiasi frame).
    Non tocca i dati esistenti — i pazienti già presenti ricevono DEFAULT 0.
    """
    with sqlite3.connect(DB_PATH) as conn:
        colonne = {
            row[1]
            for row in conn.execute("PRAGMA table_info(pazienti)")
        }
        if "consenso_privacy" not in colonne:
            conn.execute(
                "ALTER TABLE pazienti "
                "ADD COLUMN consenso_privacy INTEGER NOT NULL DEFAULT 0"
            )
            conn.commit()
            print("[DB] Migrazione: colonna 'consenso_privacy' aggiunta.")
        else:
            print("[DB] Migrazione: colonna già presente, skip.")


def inserisci_paziente(
    nome: str,
    cognome: str,
    telefono: str,
    note: str,
    consenso_privacy: bool = False,   # ← unico parametro aggiunto
) -> int:
    """
    Inserisce un nuovo paziente e ritorna il suo id generato.
    Firma invariata rispetto all'originale, tranne il nuovo parametro opzionale.
    """
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.execute(
            """
            INSERT INTO pazienti (nome, cognome, telefono, note, consenso_privacy)
            VALUES (?, ?, ?, ?, ?)
            """,
            (nome, cognome, telefono, note, int(consenso_privacy)),
        )
        conn.commit()
        return cur.lastrowid


def aggiorna_consenso(paz_id: int, stato: bool) -> None:
    """
    Aggiorna il consenso di un paziente esistente.
    Usare dal badge nella lista per il toggle on-the-fly.
    """
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "UPDATE pazienti SET consenso_privacy = ? WHERE id = ?",
            (int(stato), paz_id),
        )
        conn.commit()


# ─────────────────────────────────────────────────────────────────────────────
#  SNIPPET 2 — PazientiFrame: form di creazione
#  Incolla nel metodo che costruisce il tuo form (es. _build_form).
# ─────────────────────────────────────────────────────────────────────────────
import customtkinter as ctk

ACCENT_GDPR  = "#00d4aa"
ACCENT_MUTED = "#2a4a43"
COLOR_DANGER = "#e05252"

def _build_consenso_switch(parent_frame: ctk.CTkFrame) -> ctk.CTkSwitch:
    """
    Ritorna un CTkSwitch già configurato da aggiungere al form.

    Utilizzo nel tuo _build_form():
        self._switch_consenso = _build_consenso_switch(form_frame)
        self._switch_consenso.grid(row=N, column=0, columnspan=2,
                                   padx=16, pady=(8, 16), sticky="w")

    Al momento del salvataggio:
        consenso = self._switch_consenso.get() == 1
        inserisci_paziente(..., consenso_privacy=consenso)
    """
    container = ctk.CTkFrame(parent_frame, fg_color="transparent")

    switch = ctk.CTkSwitch(
        container,
        text="",
        width=44,
        height=22,
        progress_color=ACCENT_GDPR,
        button_color="#ffffff",
        button_hover_color="#e0e0e0",
        fg_color=ACCENT_MUTED,
        onvalue=1,
        offvalue=0,
    )
    switch.grid(row=0, column=0, padx=(0, 10))

    lbl = ctk.CTkLabel(
        container,
        text="Consenso Acquisito (GDPR)",
        font=ctk.CTkFont(size=12, weight="bold"),
        text_color="#EDF0FF",
    )
    lbl.grid(row=0, column=1)

    sub = ctk.CTkLabel(
        container,
        text="Modulo cartaceo firmato e archiviato",
        font=ctk.CTkFont(size=10),
        text_color="#8A8FA8",
    )
    sub.grid(row=1, column=1, sticky="w", pady=(1, 0))

    return switch   # <-- tieni il riferimento come self._switch_consenso


# ─────────────────────────────────────────────────────────────────────────────
#  SNIPPET 3 — PazientiFrame: riga lista pazienti con badge
#  Sostituisci / arricchisci il metodo che genera le righe della tua lista.
# ─────────────────────────────────────────────────────────────────────────────

def _crea_riga_paziente(
    parent: ctk.CTkFrame,
    paz: dict,                 # {"id": int, "nome": str, "cognome": str,
                               #  "telefono": str, "consenso_privacy": int}
    on_click: callable = None,
) -> ctk.CTkFrame:
    """
    Ritorna una riga-card per la lista pazienti con badge GDPR integrato.

    Utilizzo nel tuo loop di rendering:
        for paz in lista_pazienti:
            riga = _crea_riga_paziente(scroll_frame, paz,
                                       on_click=self._apri_paziente)
            riga.pack(fill="x", padx=8, pady=3)
    """
    ha_consenso = bool(paz.get("consenso_privacy", 0))

    riga = ctk.CTkFrame(
        parent,
        fg_color="#1E2130",
        corner_radius=8,
        border_width=1,
        border_color="#2E3250",
        height=56,
        cursor="hand2",
    )
    riga.pack_propagate(False)
    riga.grid_columnconfigure(1, weight=1)   # colonna nome si espande

    # — Iniziale / Avatar ——————————————————————————————————————————————
    avatar_bg = ACCENT_GDPR if ha_consenso else "#3a2020"
    ctk.CTkLabel(
        riga,
        text=paz["nome"][0].upper(),
        width=36, height=36,
        font=ctk.CTkFont(size=14, weight="bold"),
        text_color="#ffffff",
        fg_color=avatar_bg,
        corner_radius=18,
    ).grid(row=0, column=0, rowspan=2, padx=(10, 0), pady=10, sticky="w")

    # — Nome e telefono ————————————————————————————————————————————————
    ctk.CTkLabel(
        riga,
        text=f"{paz['cognome']} {paz['nome']}",
        font=ctk.CTkFont(size=12, weight="bold"),
        text_color="#EDF0FF",
        anchor="w",
    ).grid(row=0, column=1, padx=12, sticky="sw")

    ctk.CTkLabel(
        riga,
        text=paz.get("telefono", "—"),
        font=ctk.CTkFont(size=10),
        text_color="#8A8FA8",
        anchor="w",
    ).grid(row=1, column=1, padx=12, sticky="nw")

    # — Badge GDPR ————————————————————————————————————————————————————
    if ha_consenso:
        badge_text  = "🛡️  Consenso OK"
        badge_fg    = "#0d3b2e"
        badge_txt_c = ACCENT_GDPR
    else:
        badge_text  = "🔴  Manca consenso"
        badge_fg    = "#3b1010"
        badge_txt_c = COLOR_DANGER

    badge = ctk.CTkLabel(
        riga,
        text=badge_text,
        font=ctk.CTkFont(size=10, weight="bold"),
        text_color=badge_txt_c,
        fg_color=badge_fg,
        corner_radius=5,
        padx=8,
        pady=3,
    )
    badge.grid(row=0, column=2, rowspan=2, padx=(0, 12), sticky="e")

    # — Click handler sull'intera riga ————————————————————————————————
    if on_click:
        _id = paz["id"]
        for widget in (riga, badge):
            widget.bind("<Button-1>", lambda e, i=_id: on_click(i))

    return riga


# ─────────────────────────────────────────────────────────────────────────────
#  AVVIO — nel tuo main.py o App.__init__
#  Aggiungi questa riga PRIMA di istanziare qualsiasi Frame
# ─────────────────────────────────────────────────────────────────────────────
#
#   from database import migra_consenso_privacy
#   migra_consenso_privacy()   # sicuro da chiamare ad ogni avvio


# ─────────────────────────────────────────────────────────────────────────────
#  PREVIEW STANDALONE — rimuovi in produzione
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    ctk.set_appearance_mode("dark")
    root = ctk.CTk()
    root.title("Preview — GDPR Snippets")
    root.geometry("620x420")
    root.configure(fg_color="#0F1117")

    # Preview form switch
    form = ctk.CTkFrame(root, fg_color="#1A1D27", corner_radius=10)
    form.pack(fill="x", padx=20, pady=(20, 8))
    ctk.CTkLabel(form, text="Form Nuovo Paziente",
                 font=ctk.CTkFont(size=13, weight="bold"),
                 text_color="#8A8FA8").pack(anchor="w", padx=16, pady=(12, 6))
    switch = _build_consenso_switch(form)
    switch.pack(anchor="w", padx=16, pady=(0, 14))

    # Preview lista pazienti
    lista = ctk.CTkFrame(root, fg_color="#1A1D27", corner_radius=10)
    lista.pack(fill="x", padx=20, pady=8)
    ctk.CTkLabel(lista, text="Lista Pazienti",
                 font=ctk.CTkFont(size=13, weight="bold"),
                 text_color="#8A8FA8").pack(anchor="w", padx=16, pady=(12, 6))

    pazienti_demo = [
        {"id": 1, "nome": "Mario",    "cognome": "Rossi",    "telefono": "333 111 2222", "consenso_privacy": 1},
        {"id": 2, "nome": "Giulia",   "cognome": "Bianchi",  "telefono": "347 555 8899", "consenso_privacy": 0},
        {"id": 3, "nome": "Roberto",  "cognome": "Verdi",    "telefono": "366 999 0011", "consenso_privacy": 1},
    ]
    for p in pazienti_demo:
        _crea_riga_paziente(lista, p).pack(fill="x", padx=10, pady=3)
    ctk.CTkFrame(lista, height=10, fg_color="transparent").pack()

    root.mainloop()

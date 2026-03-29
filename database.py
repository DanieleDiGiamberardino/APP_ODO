"""
database.py
===========
Modulo centrale per la gestione del database SQLite dell'applicazione
di fotografia clinica odontoiatrica.

Responsabilità:
  - Inizializzazione dello schema (tabelle, vincoli, indici)
  - Funzioni CRUD per Pazienti e Foto
  - Query avanzate con filtri incrociati per la dashboard di ricerca

Dipendenze: solo libreria standard (sqlite3, pathlib, datetime)
"""

import sqlite3
import shutil
import os
import uuid
from pathlib import Path
from datetime import date
from typing import Optional

# ---------------------------------------------------------------------------
# CONFIGURAZIONE PERCORSI
# ---------------------------------------------------------------------------

# Cartella radice dell'applicazione (stessa directory di questo file)
APP_DIR = Path(__file__).parent.resolve()

# File del database SQLite — file singolo, portabile
DB_PATH = APP_DIR / "dental_app.db"

# Cartella dove vengono copiate fisicamente le immagini al momento dell'upload.
# Usare un percorso relativo garantisce che spostare la cartella dell'app
# non rompa i collegamenti alle foto.
IMAGES_DIR = APP_DIR / "images_storage"
IMAGES_DIR.mkdir(exist_ok=True)   # crea la cartella se non esiste già


# ---------------------------------------------------------------------------
# VALORI AMMESSI (usati anche dalla UI per popolare i menù a tendina)
# ---------------------------------------------------------------------------

BRANCHE: list[str] = [
    "Ortodonzia",
    "Implantologia",
    "Conservativa",
    "Endodonzia",
    "Protesi",
    "Chirurgia Orale",
    "Parodontologia",
    "Pedodonzia",
    "Estetica Dentale",
]

FASI: list[str] = [
    "Pre-op",
    "Intra-op",
    "Provvisorio",
    "Post-op",
    "Follow-up",
]

# Denti in numerazione FDI (11-18, 21-28, 31-38, 41-48) + voci generiche
DENTI_FDI: list[str] = (
    ["Arcata Superiore", "Arcata Inferiore", "Arcata Completa"]
    + [f"{q}{n}" for q in (1, 2, 3, 4) for n in range(1, 9)]
)


# ---------------------------------------------------------------------------
# CONNESSIONE AL DATABASE
# ---------------------------------------------------------------------------

def get_connection() -> sqlite3.Connection:
    """
    Apre (o crea) la connessione al file SQLite e la restituisce.

    Imposta:
      - row_factory = sqlite3.Row  → le righe sono accessibili sia per indice
                                     sia per nome di colonna (es. row["nome"])
      - PRAGMA foreign_keys = ON   → attiva il controllo delle chiavi esterne,
                                     disabilitato di default in SQLite
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


# ---------------------------------------------------------------------------
# INIZIALIZZAZIONE SCHEMA
# ---------------------------------------------------------------------------

def init_db() -> None:
    """
    Crea le tabelle nel database se non esistono già (IF NOT EXISTS).
    Sicuro da chiamare a ogni avvio dell'applicazione.

    Schema:
      pazienti          → anagrafica completa del paziente
      foto              → metadati della singola fotografia clinica
      note_appuntamento → diario clinico per appuntamento
    """
    with get_connection() as conn:
        conn.executescript("""
            -- ----------------------------------------------------------------
            -- Tabella PAZIENTI (schema esteso)
            -- ----------------------------------------------------------------
            CREATE TABLE IF NOT EXISTS pazienti (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                nome             TEXT    NOT NULL,
                cognome          TEXT    NOT NULL,
                telefono         TEXT,
                note             TEXT,
                data_nascita     DATE,
                codice_fiscale   TEXT,
                email            TEXT,
                indirizzo        TEXT,
                medico_curante   TEXT,
                allergie         TEXT,
                anamnesi         TEXT,
                farmaci          TEXT,
                gruppo_sanguigno TEXT,
                creato_il        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            -- Indice per velocizzare le ricerche per cognome
            CREATE INDEX IF NOT EXISTS idx_pazienti_cognome
                ON pazienti (cognome COLLATE NOCASE);

            -- ----------------------------------------------------------------
            -- Tabella FOTO
            -- ----------------------------------------------------------------
            CREATE TABLE IF NOT EXISTS foto (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                paziente_id      INTEGER NOT NULL
                                    REFERENCES pazienti(id) ON DELETE CASCADE,
                percorso_file    TEXT    NOT NULL,
                data_scatto      DATE,
                dente            TEXT,
                branca           TEXT,
                fase             TEXT,
                note             TEXT,
                aggiunta_il      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            -- ----------------------------------------------------------------
            -- Tabella NOTE APPUNTAMENTO (diario clinico)
            -- ----------------------------------------------------------------
            CREATE TABLE IF NOT EXISTS note_appuntamento (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                paziente_id INTEGER NOT NULL
                                REFERENCES pazienti(id) ON DELETE CASCADE,
                data        DATE    NOT NULL,
                titolo      TEXT,
                testo       TEXT    NOT NULL,
                creata_il   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            -- Indici foto
            CREATE INDEX IF NOT EXISTS idx_foto_paziente
                ON foto (paziente_id);
            CREATE INDEX IF NOT EXISTS idx_foto_branca
                ON foto (branca COLLATE NOCASE);
            CREATE INDEX IF NOT EXISTS idx_foto_dente
                ON foto (dente COLLATE NOCASE);
            CREATE INDEX IF NOT EXISTS idx_foto_fase
                ON foto (fase COLLATE NOCASE);
            CREATE INDEX IF NOT EXISTS idx_foto_data
                ON foto (data_scatto);

            -- Indice note appuntamento
            CREATE INDEX IF NOT EXISTS idx_note_paziente
                ON note_appuntamento (paziente_id);
        """)

    # ── Migrazione: aggiunge le colonne nuove ai DB già esistenti ─────────────
    # SQLite non supporta IF NOT EXISTS sulle colonne: usiamo try/except per
    # ogni ALTER TABLE — se la colonna esiste già viene ignorata silenziosamente.
    nuove_colonne_pazienti = [
        ("data_nascita",     "DATE"),
        ("codice_fiscale",   "TEXT"),
        ("email",            "TEXT"),
        ("indirizzo",        "TEXT"),
        ("medico_curante",   "TEXT"),
        ("allergie",         "TEXT"),
        ("anamnesi",         "TEXT"),
        ("farmaci",          "TEXT"),
        ("gruppo_sanguigno", "TEXT"),
        ("sesso",            "TEXT"),
        ("stato_civile",     "TEXT"),
        ("professione",      "TEXT"),
        ("luogo_nascita",    "TEXT"),
    ]
    with get_connection() as conn:
        for colonna, tipo in nuove_colonne_pazienti:
            try:
                conn.execute(
                    f"ALTER TABLE pazienti ADD COLUMN {colonna} {tipo}"
                )
            except Exception:
                pass   # colonna già presente → ignora


# ---------------------------------------------------------------------------
# CRUD — PAZIENTI
# ---------------------------------------------------------------------------

def inserisci_paziente(
    nome: str,
    cognome: str,
    telefono: str = "",
    note: str = "",
) -> int:
    """
    Inserisce un nuovo paziente e restituisce il suo ID generato.

    Args:
        nome:     Nome del paziente.
        cognome:  Cognome del paziente.
        telefono: Numero di telefono (opzionale).
        note:     Note libere (opzionale).

    Returns:
        ID intero del record appena creato.
    """
    with get_connection() as conn:
        cur = conn.execute(
            """
            INSERT INTO pazienti (nome, cognome, telefono, note)
            VALUES (?, ?, ?, ?)
            """,
            (nome.strip(), cognome.strip(), telefono.strip(), note.strip()),
        )
        return cur.lastrowid


def cerca_pazienti(testo: str = "") -> list[sqlite3.Row]:
    """
    Ricerca pazienti per nome o cognome (ricerca parziale, case-insensitive).

    Se 'testo' è vuoto, restituisce tutti i pazienti ordinati per cognome.

    Args:
        testo: Stringa di ricerca (può essere nome, cognome o entrambi parzialmente).

    Returns:
        Lista di Row con colonne: id, nome, cognome, telefono, note, creato_il
    """
    pattern = f"%{testo.strip()}%"
    with get_connection() as conn:
        return conn.execute(
            """
            SELECT * FROM pazienti
            WHERE  nome    LIKE ? COLLATE NOCASE
               OR  cognome LIKE ? COLLATE NOCASE
            ORDER  BY cognome COLLATE NOCASE, nome COLLATE NOCASE
            """,
            (pattern, pattern),
        ).fetchall()


def get_paziente_by_id(paziente_id: int) -> Optional[sqlite3.Row]:
    """Restituisce il singolo record paziente dato il suo ID, o None se non esiste."""
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM pazienti WHERE id = ?", (paziente_id,)
        ).fetchone()


def aggiorna_paziente(paziente_id: int, **campi) -> None:
    """
    Aggiorna uno o più campi del paziente.
    Campi ammessi: nome, cognome, telefono, email, indirizzo,
      data_nascita, codice_fiscale, medico_curante,
      allergie, anamnesi, farmaci, gruppo_sanguigno, note
    """
    campi_ammessi = {
        "nome", "cognome", "telefono", "email", "indirizzo",
        "data_nascita", "codice_fiscale", "medico_curante",
        "allergie", "anamnesi", "farmaci", "gruppo_sanguigno", "note",
        "sesso", "stato_civile", "professione", "luogo_nascita",
    }
    set_parts, params = [], []
    for k, v in campi.items():
        if k in campi_ammessi:
            set_parts.append(f"{k} = ?")
            params.append(v.strip() if isinstance(v, str) else v)
    if not set_parts:
        return
    params.append(paziente_id)
    with get_connection() as conn:
        conn.execute(f"UPDATE pazienti SET {', '.join(set_parts)} WHERE id = ?", params)


def elimina_paziente(paziente_id: int) -> None:
    """
    Elimina un paziente e, grazie al CASCADE, tutte le sue foto dal DB.
    I file fisici delle immagini NON vengono eliminati automaticamente:
    usa 'elimina_foto' per rimuovere anche il file dal disco.
    """
    with get_connection() as conn:
        conn.execute("DELETE FROM pazienti WHERE id = ?", (paziente_id,))


# ---------------------------------------------------------------------------
# CRUD — NOTE APPUNTAMENTO (diario clinico)
# ---------------------------------------------------------------------------

def aggiungi_nota(
    paziente_id: int,
    testo: str,
    titolo: str = "",
    data: Optional[date] = None,
) -> int:
    """Inserisce una nota clinica di appuntamento. Restituisce l'ID creato."""
    data_str = (data or date.today()).isoformat()
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO note_appuntamento (paziente_id, data, titolo, testo) VALUES (?,?,?,?)",
            (paziente_id, data_str, titolo.strip(), testo.strip()),
        )
        return cur.lastrowid


def get_note_paziente(paziente_id: int) -> list:
    """Restituisce tutte le note cliniche di un paziente, dalla più recente."""
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM note_appuntamento WHERE paziente_id=? ORDER BY data DESC, creata_il DESC",
            (paziente_id,),
        ).fetchall()


def elimina_nota(nota_id: int) -> None:
    """Rimuove una singola nota appuntamento."""
    with get_connection() as conn:
        conn.execute("DELETE FROM note_appuntamento WHERE id = ?", (nota_id,))


# ---------------------------------------------------------------------------
# CRUD — FOTO
# ---------------------------------------------------------------------------

def upload_foto(
    paziente_id: int,
    sorgente_path: str | Path,
    data_scatto: Optional[date] = None,
    dente: str = "",
    branca: str = "",
    fase: str = "",
    note: str = "",
) -> int:
    """
    Copia fisicamente l'immagine nella cartella di storage dell'app e
    inserisce i metadati nel database.

    Logica di copia (AGGIORNATA PER PRIVACY):
      - Genera un UUID univoco per il nome del file, separando l'identità
        del paziente dal file system per conformità GDPR.
    """
    sorgente_path = Path(sorgente_path)
    if not sorgente_path.is_file():
        raise FileNotFoundError(f"File non trovato: {sorgente_path}")

    if get_paziente_by_id(paziente_id) is None:
        raise ValueError(f"Nessun paziente con ID {paziente_id}")

    # --- NUOVA LOGICA DI ANONIMIZZAZIONE (UUID) ---
    # Estraiamo solo l'estensione originale (es. '.jpg', '.png')
    estensione = sorgente_path.suffix.lower()

    # Generiamo un nome file sicuro, univoco e anonimo
    nome_sicuro = f"{uuid.uuid4().hex}{estensione}"
    dest_path = IMAGES_DIR / nome_sicuro

    # Copiamo il file. Essendo un UUID a 32 caratteri generato casualmente,
    # la probabilità di collisione è nulla, quindi non serve più
    # il ciclo 'while' di controllo duplicati.
    shutil.copy2(sorgente_path, dest_path)

    # Percorso relativo salvato nel DB (portabile su qualunque OS)
    percorso_relativo = dest_path.relative_to(APP_DIR).as_posix()

    data_str = (data_scatto or date.today()).isoformat()

    with get_connection() as conn:
        cur = conn.execute(
            """
            INSERT INTO foto
                (paziente_id, percorso_file, data_scatto, dente, branca, fase, note)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                paziente_id,
                percorso_relativo,
                data_str,
                dente.strip(),
                branca.strip(),
                fase.strip(),
                note.strip(),
            ),
        )
        return cur.lastrowid

def elimina_foto(foto_id: int, elimina_file: bool = False) -> None:
    """
    Rimuove il record foto dal DB.

    Args:
        foto_id:       ID del record da eliminare.
        elimina_file:  Se True, cancella anche il file fisico dal disco.
    """
    with get_connection() as conn:
        row = conn.execute(
            "SELECT percorso_file FROM foto WHERE id = ?", (foto_id,)
        ).fetchone()

        if row and elimina_file:
            file_assoluto = APP_DIR / row["percorso_file"]
            if file_assoluto.is_file():
                file_assoluto.unlink()

        conn.execute("DELETE FROM foto WHERE id = ?", (foto_id,))


def get_percorso_assoluto(foto_row: sqlite3.Row) -> Path:
    """
    Converte il percorso relativo memorizzato nel DB in percorso assoluto.
    Utile per aprire/visualizzare l'immagine con Pillow o il sistema operativo.
    """
    return APP_DIR / foto_row["percorso_file"]


# ---------------------------------------------------------------------------
# QUERY AVANZATE — DASHBOARD DI RICERCA
# ---------------------------------------------------------------------------

def cerca_foto(
    paziente_id:  Optional[int]  = None,
    dente:        Optional[str]  = None,
    branca:       Optional[str]  = None,
    fase:         Optional[str]  = None,
    data_da:      Optional[date] = None,
    data_a:       Optional[date] = None,
    testo_libero: Optional[str]  = None,
    ordine:       str            = "data_scatto DESC",
) -> list[sqlite3.Row]:
    """
    Motore di ricerca con filtri incrociati per la dashboard clinica.

    Questa funzione costruisce la query SQL in modo DINAMICO:
    aggiunge una clausola WHERE solo per i parametri che l'utente ha
    effettivamente specificato (not None / not empty). In questo modo
    qualsiasi combinazione di filtri funziona correttamente, inclusa
    la ricerca con un solo filtro attivo o nessuno (restituisce tutto).

    ESEMPIO D'USO (risponde alla query del brief):
        risultati = cerca_foto(branca="Conservativa", dente="21", fase="Post-op")

    Args:
        paziente_id:  Filtra per paziente specifico (None = tutti i pazienti).
        dente:        Codice FDI esatto o descrizione arcata (es. "21", "Arcata").
                      Usa LIKE internamente per permettere ricerche parziali
                      (es. "1" matcha "11", "12", …, "Arcata Superiore").
        branca:       Specialità clinica (confronto esatto, case-insensitive).
        fase:         Fase clinica (confronto esatto, case-insensitive).
        data_da:      Includi solo foto scattate a partire da questa data.
        data_a:       Includi solo foto scattate fino a questa data.
        testo_libero: Ricerca nelle note della foto (LIKE %…%).
        ordine:       Clausola ORDER BY (default: foto più recenti prima).
                      Valori sicuri: "data_scatto DESC", "data_scatto ASC",
                      "cognome ASC", "id DESC".

    Returns:
        Lista di sqlite3.Row con TUTTE le colonne di 'foto' più
        'nome', 'cognome', 'telefono' del paziente associato.
        Ogni colonna è accessibile per nome: row["branca"], row["nome"], ecc.
    """
    # --- Whitelist delle clausole ORDER BY per prevenire SQL injection ---
    ordini_ammessi = {
        "data_scatto DESC", "data_scatto ASC",
        "cognome ASC",      "cognome DESC",
        "id DESC",          "id ASC",
        "branca ASC",       "fase ASC",
    }
    if ordine not in ordini_ammessi:
        ordine = "data_scatto DESC"

    # Costruiamo la lista dei predicati WHERE e dei parametri in parallelo.
    # Ogni elemento di 'clausole' è una stringa SQL con un segnaposto '?'.
    # Ogni elemento di 'params' è il valore corrispondente.
    clausole: list[str] = []
    params:   list      = []

    # --- Filtro: paziente ---
    if paziente_id is not None:
        clausole.append("f.paziente_id = ?")
        params.append(paziente_id)

    # --- Filtro: dente (ricerca parziale per coprire es. "1" → "11","21"…) ---
    if dente:
        clausole.append("f.dente LIKE ? COLLATE NOCASE")
        params.append(f"%{dente.strip()}%")

    # --- Filtro: branca (confronto esatto, case-insensitive) ---
    if branca:
        clausole.append("f.branca = ? COLLATE NOCASE")
        params.append(branca.strip())

    # --- Filtro: fase (confronto esatto, case-insensitive) ---
    if fase:
        clausole.append("f.fase = ? COLLATE NOCASE")
        params.append(fase.strip())

    # --- Filtro: intervallo date ---
    # data_scatto è salvata come testo ISO (YYYY-MM-DD): il confronto
    # lessicografico coincide con quello cronologico, quindi >= e <= funzionano.
    if data_da:
        clausole.append("f.data_scatto >= ?")
        params.append(data_da.isoformat())
    if data_a:
        clausole.append("f.data_scatto <= ?")
        params.append(data_a.isoformat())

    # --- Filtro: testo libero nelle note ---
    if testo_libero:
        clausole.append("f.note LIKE ? COLLATE NOCASE")
        params.append(f"%{testo_libero.strip()}%")

    # --- Composizione finale della query ---
    where_sql = ("WHERE " + " AND ".join(clausole)) if clausole else ""

    sql = f"""
        SELECT
            f.id,
            f.paziente_id,
            f.percorso_file,
            f.data_scatto,
            f.dente,
            f.branca,
            f.fase,
            f.note,
            f.aggiunta_il,
            p.nome,
            p.cognome,
            p.telefono
        FROM  foto     f
        JOIN  pazienti p ON p.id = f.paziente_id
        {where_sql}
        ORDER BY {ordine}
    """

    with get_connection() as conn:
        return conn.execute(sql, params).fetchall()


def conta_foto_per_paziente(paziente_id: int) -> int:
    """
    Restituisce il numero totale di foto archiviate per un paziente.
    Utile per mostrare un badge/counter nella lista pazienti.
    """
    with get_connection() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM foto WHERE paziente_id = ?",
            (paziente_id,),
        ).fetchone()
        return row["n"] if row else 0


def statistiche_branche() -> list[sqlite3.Row]:
    """
    Restituisce il conteggio delle foto raggruppate per branca clinica.
    Utile per un eventuale pannello statistiche / grafico a torta.

    Returns:
        Lista di Row con colonne: branca, totale
        Ordinata per totale decrescente.
    """
    with get_connection() as conn:
        return conn.execute(
            """
            SELECT   branca,
                     COUNT(*) AS totale
            FROM     foto
            WHERE    branca IS NOT NULL AND branca != ''
            GROUP BY branca
            ORDER BY totale DESC
            """
        ).fetchall()


def get_foto_by_id(foto_id: int) -> Optional[sqlite3.Row]:
    """
    Restituisce il record completo di una singola foto (con dati paziente).
    Utile per la visualizzazione del dettaglio o la modifica dei tag.
    """
    with get_connection() as conn:
        return conn.execute(
            """
            SELECT f.*, p.nome, p.cognome
            FROM   foto f
            JOIN   pazienti p ON p.id = f.paziente_id
            WHERE  f.id = ?
            """,
            (foto_id,),
        ).fetchone()


def aggiorna_tag_foto(
    foto_id: int,
    dente:   Optional[str] = None,
    branca:  Optional[str] = None,
    fase:    Optional[str] = None,
    note:    Optional[str] = None,
) -> None:
    """
    Aggiorna i metadati clinici (tag) di una foto esistente.
    Solo i parametri diversi da None vengono modificati.

    Args:
        foto_id: ID della foto da aggiornare.
        dente:   Nuovo valore dente (None = non modificare).
        branca:  Nuovo valore branca (None = non modificare).
        fase:    Nuovo valore fase (None = non modificare).
        note:    Nuove note (None = non modificare).
    """
    # Costruiamo dinamicamente solo i SET necessari
    set_clausole: list[str] = []
    params: list = []

    if dente  is not None: set_clausole.append("dente  = ?"); params.append(dente.strip())
    if branca is not None: set_clausole.append("branca = ?"); params.append(branca.strip())
    if fase   is not None: set_clausole.append("fase   = ?"); params.append(fase.strip())
    if note   is not None: set_clausole.append("note   = ?"); params.append(note.strip())

    if not set_clausole:
        return  # Nulla da aggiornare

    params.append(foto_id)
    sql = f"UPDATE foto SET {', '.join(set_clausole)} WHERE id = ?"

    with get_connection() as conn:
        conn.execute(sql, params)


# ---------------------------------------------------------------------------
# KPI — statistiche per dashboard e status bar
# ---------------------------------------------------------------------------

def kpi_stats() -> dict:
    """
    Restituisce le statistiche chiave dell'applicazione in un unico dict.
    Usato da KPI cards (dashboard) e status bar.

    Campi restituiti:
      pazienti      → numero totale di pazienti
      foto_totali   → numero totale di foto archiviate
      foto_oggi     → foto scattate/caricate oggi
      foto_settimana→ foto degli ultimi 7 giorni
      db_size_mb    → dimensione del file DB in MB
      ultimo_backup → Path dell'ultimo file .zip in backups/, o None
    """
    from datetime import date, timedelta
    oggi  = date.today().isoformat()
    sette = (date.today() - timedelta(days=7)).isoformat()

    with get_connection() as conn:
        n_paz   = conn.execute("SELECT COUNT(*) FROM pazienti").fetchone()[0]
        n_foto  = conn.execute("SELECT COUNT(*) FROM foto").fetchone()[0]
        n_oggi  = conn.execute(
            "SELECT COUNT(*) FROM foto WHERE date(aggiunta_il) = ?", (oggi,)
        ).fetchone()[0]
        n_sett  = conn.execute(
            "SELECT COUNT(*) FROM foto WHERE date(aggiunta_il) >= ?", (sette,)
        ).fetchone()[0]

    # Dimensione DB
    try:
        db_size_mb = round(DB_PATH.stat().st_size / 1_048_576, 2)
    except Exception:
        db_size_mb = 0.0

    # Ultimo backup
    backup_dir = APP_DIR / "backups"
    ultimo_backup = None
    if backup_dir.exists():
        zips = sorted(backup_dir.glob("*.zip"), key=lambda p: p.stat().st_mtime)
        if zips:
            ultimo_backup = zips[-1]

    return {
        "pazienti":       n_paz,
        "foto_totali":    n_foto,
        "foto_oggi":      n_oggi,
        "foto_settimana": n_sett,
        "db_size_mb":     db_size_mb,
        "ultimo_backup":  ultimo_backup,
    }


# ---------------------------------------------------------------------------
# ENTRY POINT — test rapido dello schema
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    """
    Esegui questo file direttamente per verificare che il DB venga
    creato correttamente e che le query di base funzionino.

        python database.py
    """
    print(f"[DB] Inizializzazione database in: {DB_PATH}")
    init_db()
    print("[DB] Tabelle create / verificate con successo.")

    # --- Demo: inserimento dati di test ---
    pid = inserisci_paziente("Mario", "Rossi", "333-1234567", "Paziente di prova")
    print(f"[DB] Paziente inserito con ID: {pid}")

    # Verifica ricerca paziente
    risultati = cerca_pazienti("rossi")
    print(f"[DB] Ricerca 'rossi' → {len(risultati)} risultato/i")
    for r in risultati:
        print(f"     {r['id']} | {r['cognome']} {r['nome']} | tel: {r['telefono']}")

    # Verifica query foto (vuota per ora)
    foto = cerca_foto(branca="Conservativa", dente="21", fase="Post-op")
    print(f"[DB] Foto Conservativa/21/Post-op → {len(foto)} risultato/i (atteso 0 se DB nuovo)")

    print("[DB] Test completato.")

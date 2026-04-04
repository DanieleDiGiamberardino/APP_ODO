"""
database.py
===========
Modulo centrale per la gestione del database SQLite dell'applicazione
di fotografia clinica odontoiatrica.

Include:
- Salvataggio sicuro nei percorsi di sistema (AppData / Application Support)
- Crittografia dei dati sensibili dei pazienti (GDPR compliance)
"""

import sqlite3
import shutil
import os
import uuid
import platform
from pathlib import Path
from datetime import date
from typing import Optional
from cryptography.fernet import Fernet

# ---------------------------------------------------------------------------
# CONFIGURAZIONE PERCORSI (System-Aware)
# ---------------------------------------------------------------------------



from config_manager import get_data_dir

# ---------------------------------------------------------------------------
# CONFIGURAZIONE PERCORSI (System & Network-Aware)
# ---------------------------------------------------------------------------

APP_DIR = get_data_dir()
APP_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = APP_DIR / "dental_app.db"
IMAGES_DIR = APP_DIR / "images_storage"
IMAGES_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# GESTIONE CHIAVE DI CIFRATURA (GDPR)
# ---------------------------------------------------------------------------
KEY_PATH = APP_DIR / "secret.key"

def _load_or_create_key() -> bytes:
    """Carica la chiave di cifratura o ne crea una nuova se non esiste."""
    if not KEY_PATH.exists():
        key = Fernet.generate_key()
        with open(KEY_PATH, "wb") as key_file:
            key_file.write(key)
    else:
        with open(KEY_PATH, "rb") as key_file:
            key = key_file.read()
    return key

_fernet = Fernet(_load_or_create_key())

def crittografa(testo: str) -> str:
    if not testo: return ""
    return _fernet.encrypt(str(testo).encode("utf-8")).decode("utf-8")

def decrittografa(testo_cifrato: str) -> str:
    if not testo_cifrato: return ""
    try:
        return _fernet.decrypt(testo_cifrato.encode("utf-8")).decode("utf-8")
    except Exception:
        # Fallback se il dato è vecchio e salvato in chiaro
        return str(testo_cifrato)

# ---------------------------------------------------------------------------
# VALORI AMMESSI
# ---------------------------------------------------------------------------

BRANCHE: list[str] = [
    "Ortodonzia", "Implantologia", "Conservativa", "Endodonzia",
    "Protesi", "Chirurgia Orale", "Parodontologia", "Pedodonzia", "Estetica Dentale"
]

FASI: list[str] = [
    "Pre-op", "Intra-op", "Provvisorio", "Post-op", "Follow-up"
]

DENTI_FDI: list[str] = (
    ["Arcata Superiore", "Arcata Inferiore", "Arcata Completa"]
    + [f"{q}{n}" for q in (1, 2, 3, 4) for n in range(1, 9)]
)

# ---------------------------------------------------------------------------
# CONNESSIONE AL DATABASE
# ---------------------------------------------------------------------------

def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def init_db() -> None:
    with get_connection() as conn:
        conn.executescript("""
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

            CREATE TABLE IF NOT EXISTS foto (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                paziente_id      INTEGER NOT NULL REFERENCES pazienti(id) ON DELETE CASCADE,
                percorso_file    TEXT    NOT NULL,
                data_scatto      DATE,
                dente            TEXT,
                branca           TEXT,
                fase             TEXT,
                note             TEXT,
                aggiunta_il      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS note_appuntamento (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                paziente_id INTEGER NOT NULL REFERENCES pazienti(id) ON DELETE CASCADE,
                data        DATE    NOT NULL,
                titolo      TEXT,
                testo       TEXT    NOT NULL,
                creata_il   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            
            CREATE INDEX IF NOT EXISTS idx_foto_paziente ON foto (paziente_id);
            CREATE INDEX IF NOT EXISTS idx_foto_branca ON foto (branca COLLATE NOCASE);
            CREATE INDEX IF NOT EXISTS idx_foto_dente ON foto (dente COLLATE NOCASE);
            CREATE INDEX IF NOT EXISTS idx_foto_fase ON foto (fase COLLATE NOCASE);
            CREATE INDEX IF NOT EXISTS idx_foto_data ON foto (data_scatto);
            CREATE INDEX IF NOT EXISTS idx_note_paziente ON note_appuntamento (paziente_id);
        """)

    nuove_colonne = [
        ("data_nascita", "DATE"), ("codice_fiscale", "TEXT"), ("email", "TEXT"),
        ("indirizzo", "TEXT"), ("medico_curante", "TEXT"), ("allergie", "TEXT"),
        ("anamnesi", "TEXT"), ("farmaci", "TEXT"), ("gruppo_sanguigno", "TEXT"),
        ("sesso", "TEXT"), ("stato_civile", "TEXT"), ("professione", "TEXT"),
        ("luogo_nascita", "TEXT"),("consenso_privacy", "INTEGER DEFAULT 0")
    ]
    with get_connection() as conn:
        for col, tipo in nuove_colonne:
            try:
                conn.execute(f"ALTER TABLE pazienti ADD COLUMN {col} {tipo}")
            except Exception:
                pass

# ---------------------------------------------------------------------------
# CRUD — PAZIENTI
# ---------------------------------------------------------------------------

def inserisci_paziente(nome: str, cognome: str, telefono: str = "", note: str = "", consenso_privacy: bool = False) -> int:
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO pazienti (nome, cognome, telefono, note, consenso_privacy) VALUES (?, ?, ?, ?, ?)",
            (crittografa(nome.strip()), crittografa(cognome.strip()), 
             crittografa(telefono.strip()), crittografa(note.strip()), int(consenso_privacy)),
        )
        return cur.lastrowid
def aggiorna_consenso(paziente_id: int, stato: bool) -> None:
    with get_connection() as conn:
        conn.execute("UPDATE pazienti SET consenso_privacy = ? WHERE id = ?", (int(stato), paziente_id))

def cerca_pazienti(testo: str = "") -> list[dict]:
    testo = testo.strip().lower()
    risultati = []
    with get_connection() as conn:
        tutti = conn.execute("SELECT * FROM pazienti").fetchall()
        
    for r in tutti:
        paz = dict(r)
        paz["nome"] = decrittografa(paz["nome"])
        paz["cognome"] = decrittografa(paz["cognome"])
        paz["telefono"] = decrittografa(paz["telefono"])
        paz["note"] = decrittografa(paz["note"])
        
        if testo:
            if testo not in paz["nome"].lower() and testo not in paz["cognome"].lower():
                continue
        risultati.append(paz)
        
    risultati.sort(key=lambda x: (x["cognome"].lower(), x["nome"].lower()))
    return risultati

def get_paziente_by_id(paziente_id: int) -> Optional[dict]:
    with get_connection() as conn:
        r = conn.execute("SELECT * FROM pazienti WHERE id = ?", (paziente_id,)).fetchone()
    if not r: return None
    paz = dict(r)
    paz["nome"] = decrittografa(paz["nome"])
    paz["cognome"] = decrittografa(paz["cognome"])
    paz["telefono"] = decrittografa(paz["telefono"])
    paz["note"] = decrittografa(paz["note"])
    return paz

def aggiorna_paziente(paziente_id: int, **campi) -> None:
    campi_ammessi = {
        "nome", "cognome", "telefono", "email", "indirizzo",
        "data_nascita", "codice_fiscale", "medico_curante",
        "allergie", "anamnesi", "farmaci", "gruppo_sanguigno", "note",
        "sesso", "stato_civile", "professione", "luogo_nascita",
    }
    campi_da_criptare = {"nome", "cognome", "telefono", "email", "indirizzo", 
                         "codice_fiscale", "medico_curante", "allergie", 
                         "anamnesi", "farmaci", "note"}
    
    set_parts, params = [], []
    for k, v in campi.items():
        if k in campi_ammessi:
            set_parts.append(f"{k} = ?")
            valore = v.strip() if isinstance(v, str) else v
            if k in campi_da_criptare and isinstance(valore, str):
                valore = crittografa(valore)
            params.append(valore)
            
    if not set_parts: return
    params.append(paziente_id)
    with get_connection() as conn:
        conn.execute(f"UPDATE pazienti SET {', '.join(set_parts)} WHERE id = ?", params)

def elimina_paziente(paziente_id: int) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM pazienti WHERE id = ?", (paziente_id,))

# ---------------------------------------------------------------------------
# CRUD — NOTE APPUNTAMENTO
# ---------------------------------------------------------------------------

def aggiungi_nota(paziente_id: int, testo: str, titolo: str = "", data: Optional[date] = None) -> int:
    data_str = (data or date.today()).isoformat()
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO note_appuntamento (paziente_id, data, titolo, testo) VALUES (?,?,?,?)",
            (paziente_id, data_str, crittografa(titolo.strip()), crittografa(testo.strip())),
        )
        return cur.lastrowid

def get_note_paziente(paziente_id: int) -> list:
    with get_connection() as conn:
        righe = conn.execute("SELECT * FROM note_appuntamento WHERE paziente_id=? ORDER BY data DESC", (paziente_id,)).fetchall()
    
    risultati = []
    for r in righe:
        n = dict(r)
        n["titolo"] = decrittografa(n["titolo"])
        n["testo"] = decrittografa(n["testo"])
        risultati.append(n)
    return risultati

def elimina_nota(nota_id: int) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM note_appuntamento WHERE id = ?", (nota_id,))

# ---------------------------------------------------------------------------
# CRUD — FOTO
# ---------------------------------------------------------------------------

def upload_foto(paziente_id: int, sorgente_path: str | Path, data_scatto: Optional[date] = None, 
                dente: str = "", branca: str = "", fase: str = "", note: str = "") -> int:
    sorgente_path = Path(sorgente_path)
    if not sorgente_path.is_file(): raise FileNotFoundError(f"File non trovato: {sorgente_path}")

    estensione = sorgente_path.suffix.lower()
    nome_sicuro = f"{uuid.uuid4().hex}{estensione}"
    dest_path = IMAGES_DIR / nome_sicuro
    shutil.copy2(sorgente_path, dest_path)
    
    percorso_relativo = dest_path.relative_to(APP_DIR).as_posix()
    data_str = (data_scatto or date.today()).isoformat()

    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO foto (paziente_id, percorso_file, data_scatto, dente, branca, fase, note) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (paziente_id, percorso_relativo, data_str, dente.strip(), branca.strip(), fase.strip(), note.strip())
        )
        return cur.lastrowid

def elimina_foto(foto_id: int, elimina_file: bool = False) -> None:
    with get_connection() as conn:
        row = conn.execute("SELECT percorso_file FROM foto WHERE id = ?", (foto_id,)).fetchone()
        if row and elimina_file:
            file_assoluto = APP_DIR / row["percorso_file"]
            if file_assoluto.is_file(): file_assoluto.unlink()
        conn.execute("DELETE FROM foto WHERE id = ?", (foto_id,))

def get_percorso_assoluto(foto_row: dict) -> Path:
    return APP_DIR / foto_row["percorso_file"]

def cerca_foto(paziente_id: Optional[int] = None, dente: Optional[str] = None, branca: Optional[str] = None, 
               fase: Optional[str] = None, data_da: Optional[date] = None, data_a: Optional[date] = None, 
               testo_libero: Optional[str] = None, ordine: str = "data_scatto DESC") -> list[dict]:
    ordini_ammessi = {"data_scatto DESC", "data_scatto ASC", "id DESC", "id ASC", "branca ASC", "fase ASC"}
    if ordine not in ordini_ammessi: ordine = "data_scatto DESC"

    clausole, params = [], []
    if paziente_id is not None:
        clausole.append("f.paziente_id = ?"); params.append(paziente_id)
    if dente:
        clausole.append("f.dente LIKE ? COLLATE NOCASE"); params.append(f"%{dente.strip()}%")
    if branca:
        clausole.append("f.branca = ? COLLATE NOCASE"); params.append(branca.strip())
    if fase:
        clausole.append("f.fase = ? COLLATE NOCASE"); params.append(fase.strip())
    if data_da:
        clausole.append("f.data_scatto >= ?"); params.append(data_da.isoformat())
    if data_a:
        clausole.append("f.data_scatto <= ?"); params.append(data_a.isoformat())
    if testo_libero:
        clausole.append("f.note LIKE ? COLLATE NOCASE"); params.append(f"%{testo_libero.strip()}%")

    where_sql = ("WHERE " + " AND ".join(clausole)) if clausole else ""
    sql = f"""
        SELECT f.*, p.nome, p.cognome, p.telefono
        FROM foto f
        JOIN pazienti p ON p.id = f.paziente_id
        {where_sql}
        ORDER BY {ordine}
    """

    risultati = []
    with get_connection() as conn:
        righe = conn.execute(sql, params).fetchall()
        
    for r in righe:
        foto = dict(r)
        # Decrittografa i dati del paziente associati alla foto
        foto["nome"] = decrittografa(foto["nome"])
        foto["cognome"] = decrittografa(foto["cognome"])
        foto["telefono"] = decrittografa(foto["telefono"])
        risultati.append(foto)
        
    return risultati

def conta_foto_per_paziente(paziente_id: int) -> int:
    with get_connection() as conn:
        row = conn.execute("SELECT COUNT(*) AS n FROM foto WHERE paziente_id = ?", (paziente_id,)).fetchone()
        return row["n"] if row else 0

def statistiche_branche() -> list[dict]:
    with get_connection() as conn:
        return [dict(r) for r in conn.execute("SELECT branca, COUNT(*) AS totale FROM foto WHERE branca IS NOT NULL AND branca != '' GROUP BY branca ORDER BY totale DESC").fetchall()]

def get_foto_by_id(foto_id: int) -> Optional[dict]:
    with get_connection() as conn:
        r = conn.execute("SELECT f.*, p.nome, p.cognome FROM foto f JOIN pazienti p ON p.id = f.paziente_id WHERE f.id = ?", (foto_id,)).fetchone()
    if not r: return None
    foto = dict(r)
    foto["nome"] = decrittografa(foto["nome"])
    foto["cognome"] = decrittografa(foto["cognome"])
    return foto

def aggiorna_tag_foto(foto_id: int, dente: Optional[str] = None, branca: Optional[str] = None, fase: Optional[str] = None, note: Optional[str] = None) -> None:
    set_clausole, params = [], []
    if dente is not None: set_clausole.append("dente = ?"); params.append(dente.strip())
    if branca is not None: set_clausole.append("branca = ?"); params.append(branca.strip())
    if fase is not None: set_clausole.append("fase = ?"); params.append(fase.strip())
    if note is not None: set_clausole.append("note = ?"); params.append(note.strip())

    if not set_clausole: return
    params.append(foto_id)
    with get_connection() as conn:
        conn.execute(f"UPDATE foto SET {', '.join(set_clausole)} WHERE id = ?", params)

def kpi_stats() -> dict:
    from datetime import timedelta
    oggi = date.today().isoformat()
    sette = (date.today() - timedelta(days=7)).isoformat()

    with get_connection() as conn:
        n_paz = conn.execute("SELECT COUNT(*) FROM pazienti").fetchone()[0]
        n_foto = conn.execute("SELECT COUNT(*) FROM foto").fetchone()[0]
        n_oggi = conn.execute("SELECT COUNT(*) FROM foto WHERE date(aggiunta_il) = ?", (oggi,)).fetchone()[0]
        n_sett = conn.execute("SELECT COUNT(*) FROM foto WHERE date(aggiunta_il) >= ?", (sette,)).fetchone()[0]

    try:
        db_size_mb = round(DB_PATH.stat().st_size / 1_048_576, 2)
    except Exception:
        db_size_mb = 0.0

    backup_dir = APP_DIR / "backups"
    ultimo_backup = None
    if backup_dir.exists():
        zips = sorted(backup_dir.glob("*.zip"), key=lambda p: p.stat().st_mtime)
        if zips: ultimo_backup = zips[-1]

    return {
        "pazienti": n_paz, "foto_totali": n_foto, "foto_oggi": n_oggi,
        "foto_settimana": n_sett, "db_size_mb": db_size_mb,
        "ultimo_backup": ultimo_backup
    }
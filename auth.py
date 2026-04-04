"""
auth.py
=======
Modulo di autenticazione e gestione utenti per DentalPhoto.

Funzionalità:
  - Tabella `utenti` nel DB (username, password hash SHA-256+salt, ruolo)
  - Ruoli: "admin" (accesso completo) | "operatore" (lettura + upload, no backup/utenti)
  - Hashing sicuro: PBKDF2-HMAC-SHA256 con salt casuale per utente
  - Sessione corrente: utente loggato conservato in memoria
  - Auto-lock: timer che scatta dopo N minuti di inattività
  - Log accessi nel DB (tabella `log_accessi`)

Uso:
    from auth import SessioneUtente, init_auth_db, verifica_login

    init_auth_db()          # chiamato da App.__init__
    ok, msg = verifica_login("mario", "password123")
    if ok:
        utente = SessioneUtente.corrente
"""

import hashlib
import secrets
import sqlite3
from datetime import datetime, timedelta
from typing import Optional

import database as db

# ---------------------------------------------------------------------------
# Costanti
# ---------------------------------------------------------------------------

RUOLI          = ["admin", "operatore"]
INATTIVITA_MIN = 15      # minuti prima del lock automatico (0 = disabilitato)
ITER_PBKDF2    = 260_000 # iterazioni PBKDF2 (OWASP 2023 raccomanda ≥ 210_000)

# Permessi per ruolo: set di chiavi di navigazione permesse
PERMESSI: dict[str, set] = {
    "admin": {
        "dashboard", "pazienti", "upload", "import",
        "statistiche", "modifica_tag", "backup", "webcam",
        "before_after", "email", "timeline",
        "utenti",    # solo admin può gestire utenti
    },
    "operatore": {
        "dashboard", "pazienti", "upload", "import",
        "statistiche", "modifica_tag", "webcam",
        "before_after", "email", "timeline",
    },
}


# ===========================================================================
# Sessione corrente (singleton in memoria)
# ===========================================================================

class SessioneUtente:
    """
    Singleton che mantiene lo stato della sessione corrente.
    Accedibile globalmente da qualunque modulo.
    """
    corrente:         Optional[sqlite3.Row] = None   # record DB utente
    ultimo_accesso:   Optional[datetime]   = None    # timestamp ultima azione
    _lock_callback    = None    # funzione da chiamare quando scatta il lock

    @classmethod
    def login(cls, utente_row: sqlite3.Row) -> None:
        cls.corrente       = utente_row
        cls.ultimo_accesso = datetime.now()

    @classmethod
    def logout(cls) -> None:
        cls.corrente       = None
        cls.ultimo_accesso = None

    @classmethod
    def registra_attivita(cls) -> None:
        """Aggiorna il timestamp — da chiamare ad ogni interazione UI."""
        if cls.corrente:
            cls.ultimo_accesso = datetime.now()

    @classmethod
    def is_scaduta(cls) -> bool:
        """
        Restituisce True se la sessione è inattiva da più di INATTIVITA_MIN minuti.
        """
        if INATTIVITA_MIN <= 0 or cls.ultimo_accesso is None:
            return False
        delta = datetime.now() - cls.ultimo_accesso
        return delta > timedelta(minutes=INATTIVITA_MIN)

    @classmethod
    def ha_permesso(cls, chiave_nav: str) -> bool:
        """True se l'utente loggato può accedere alla sezione 'chiave_nav'."""
        if cls.corrente is None:
            return False
        ruolo = cls.corrente["ruolo"]
        return chiave_nav in PERMESSI.get(ruolo, set())

    @classmethod
    def is_admin(cls) -> bool:
        return cls.corrente is not None and cls.corrente["ruolo"] == "admin"

    @classmethod
    def nome_display(cls) -> str:
        if cls.corrente is None:
            return "—"
        return cls.corrente["nome_display"] or cls.corrente["username"]


# ===========================================================================
# Hashing password
# ===========================================================================

def _hash_password(password: str, salt: Optional[str] = None) -> tuple[str, str]:
    """
    Calcola PBKDF2-HMAC-SHA256 della password.
    Restituisce (hash_hex, salt_hex).
    Se salt è None ne genera uno nuovo casuale.
    """
    if salt is None:
        salt = secrets.token_hex(32)   # 256 bit di entropia
    dk = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        ITER_PBKDF2,
    )
    return dk.hex(), salt


def _verifica_hash(password: str, hash_memorizzato: str, salt: str) -> bool:
    dk, _ = _hash_password(password, salt)
    return secrets.compare_digest(dk, hash_memorizzato)


# ===========================================================================
# Schema DB — tabelle auth
# ===========================================================================

def init_auth_db() -> None:
    with db.get_connection() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS utenti (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                username     TEXT    NOT NULL UNIQUE,
                nome_display TEXT,
                password_hash TEXT   NOT NULL,
                salt         TEXT    NOT NULL,
                ruolo        TEXT    NOT NULL DEFAULT 'operatore',
                attivo       INTEGER NOT NULL DEFAULT 1,
                richiede_cambio INTEGER NOT NULL DEFAULT 0,
                creato_il    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                ultimo_login  TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS log_accessi (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                username   TEXT,
                timestamp  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                esito      TEXT,
                ip_host    TEXT
            );
        """)

    # --- MIGRAZIONE: Aggiunta colonna se non esiste ---
    try:
        with db.get_connection() as conn:
            conn.execute("ALTER TABLE utenti ADD COLUMN richiede_cambio INTEGER NOT NULL DEFAULT 0")
    except Exception:
        pass

    # --- ADMIN DI DEFAULT ---
    with db.get_connection() as conn:
        n = conn.execute("SELECT COUNT(*) FROM utenti").fetchone()[0]
        if n == 0:
            crea_utente("admin", "admin1234", "Amministratore", "admin")
            # Forziamo il cambio password solo per il primo admin creato
            conn.execute("UPDATE utenti SET richiede_cambio = 1 WHERE username = 'admin'")



# ===========================================================================
# CRUD utenti
# ===========================================================================

def crea_utente(
    username: str,
    password: str,
    nome_display: str = "",
    ruolo: str = "operatore",
) -> int:
    """
    Crea un nuovo utente. Lancia ValueError se username già esistente.
    Restituisce l'ID creato.
    """
    if ruolo not in RUOLI:
        raise ValueError(f"Ruolo non valido: {ruolo}. Valori ammessi: {RUOLI}")
    hash_, salt = _hash_password(password)
    with db.get_connection() as conn:
        try:
            cur = conn.execute(
                "INSERT INTO utenti (username, nome_display, password_hash, salt, ruolo) "
                "VALUES (?, ?, ?, ?, ?)",
                (username.strip().lower(), nome_display.strip(), hash_, salt, ruolo),
            )
            return cur.lastrowid
        except sqlite3.IntegrityError:
            raise ValueError(f"Username «{username}» già esistente.")


def get_tutti_utenti() -> list[sqlite3.Row]:
    """Lista di tutti gli utenti (senza campi sensibili nella query)."""
    with db.get_connection() as conn:
        return conn.execute(
            "SELECT id, username, nome_display, ruolo, attivo, creato_il, ultimo_login "
            "FROM utenti ORDER BY username"
        ).fetchall()


def aggiorna_utente(
    utente_id: int,
    nome_display: Optional[str] = None,
    ruolo: Optional[str] = None,
    attivo: Optional[bool] = None,
) -> None:
    """Aggiorna i campi non-sensibili di un utente."""
    parts, params = [], []
    if nome_display is not None:
        parts.append("nome_display = ?"); params.append(nome_display.strip())
    if ruolo is not None:
        if ruolo not in RUOLI:
            raise ValueError(f"Ruolo non valido: {ruolo}")
        parts.append("ruolo = ?"); params.append(ruolo)
    if attivo is not None:
        parts.append("attivo = ?"); params.append(1 if attivo else 0)
    if not parts:
        return
    params.append(utente_id)
    with db.get_connection() as conn:
        conn.execute(f"UPDATE utenti SET {', '.join(parts)} WHERE id = ?", params)


def cambia_password(utente_id: int, nuova_password: str) -> None:
    """Aggiorna la password di un utente (rigenera salt)."""
    hash_, salt = _hash_password(nuova_password)
    with db.get_connection() as conn:
        conn.execute(
            "UPDATE utenti SET password_hash=?, salt=? WHERE id=?",
            (hash_, salt, utente_id),
        )


def elimina_utente(utente_id: int) -> None:
    """
    Elimina un utente. Non permette di eliminare l'ultimo admin.
    """
    with db.get_connection() as conn:
        admin_count = conn.execute(
            "SELECT COUNT(*) FROM utenti WHERE ruolo='admin' AND attivo=1"
        ).fetchone()[0]
        utente = conn.execute(
            "SELECT ruolo FROM utenti WHERE id=?", (utente_id,)
        ).fetchone()
        if utente and utente["ruolo"] == "admin" and admin_count <= 1:
            raise ValueError("Impossibile eliminare l'unico admin attivo.")
        conn.execute("DELETE FROM utenti WHERE id=?", (utente_id,))


# ===========================================================================
# Verifica login
# ===========================================================================

def verifica_login(username: str, password: str) -> tuple[bool, str]:
    """
    Verifica le credenziali e, se corrette, imposta SessioneUtente.corrente.

    Restituisce (True, "") in caso di successo,
               (False, messaggio_errore) in caso di fallimento.
    """
    username = username.strip().lower()

    with db.get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM utenti WHERE username=?", (username,)
        ).fetchone()

    esito = "fallito"
    msg   = ""

    if row is None:
        msg = "Utente non trovato."
    elif not row["attivo"]:
        msg = "Account disabilitato. Contatta l'amministratore."
    elif not _verifica_hash(password, row["password_hash"], row["salt"]):
        msg = "Password errata."
    else:
        esito = "ok"
        SessioneUtente.login(row)
        # Aggiorna timestamp ultimo login
        with db.get_connection() as conn:
            conn.execute(
                "UPDATE utenti SET ultimo_login=? WHERE id=?",
                (datetime.now().isoformat(), row["id"]),
            )

    # Log accesso
    _log_accesso(row["id"] if row else None, username, esito)

    if esito == "ok":
        return True, ""
    return False, msg


def _log_accesso(utente_id: Optional[int], username: str, esito: str) -> None:
    import socket
    try:
        host = socket.gethostname()
    except Exception:
        host = "—"
    with db.get_connection() as conn:
        conn.execute(
            "INSERT INTO log_accessi (username, esito, ip_host) VALUES (?,?,?)",
            (username, esito, host),
        )


def get_log_accessi(limit: int = 50) -> list[sqlite3.Row]:
    """Ultimi N accessi (successi e fallimenti)."""
    with db.get_connection() as conn:
        return conn.execute(
            "SELECT * FROM log_accessi ORDER BY timestamp DESC LIMIT ?", (limit,)
        ).fetchall()

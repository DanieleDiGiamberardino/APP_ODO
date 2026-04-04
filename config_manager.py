"""
config_manager.py
Gestisce local_settings.json in AppData locale.
DATA_DIR punta al db e alla cartella foto (locale o rete LAN).
"""

import json
import os
import platform
from pathlib import Path

APP_NAME    = "DentalPhoto"
DB_FILENAME = "dental_app.db"


def _get_local_settings_path() -> Path:
    """local_settings.json resta SEMPRE in AppData del singolo PC."""
    system = platform.system()
    if system == "Windows":
        base = Path(os.environ.get("APPDATA", Path.home()))
    elif system == "Darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    folder = base / APP_NAME
    folder.mkdir(parents=True, exist_ok=True)
    return folder / "local_settings.json"


def _get_default_data_dir() -> Path:
    """Percorso AppData locale di default (comportamento originale)."""
    system = platform.system()
    if system == "Windows":
        base = Path(os.environ.get("APPDATA", Path.home()))
    elif system == "Darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    folder = base / APP_NAME
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _load_settings() -> dict:
    path = _get_local_settings_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_settings(data: dict) -> None:
    _get_local_settings_path().write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def get_data_dir() -> Path:
    """
    Ritorna la DATA_DIR attiva:
    - Se non configurata → AppData locale di default.
    - Se configurata → percorso personalizzato (es. Z:\\DentalData o \\\\SERVER\\Data),
      purché esista; altrimenti fallback al default con warning.
    """
    settings  = _load_settings()
    custom    = settings.get("DATA_DIR", "").strip()

    if not custom:
        return _get_default_data_dir()

    custom_path = Path(custom)
    if custom_path.exists() and custom_path.is_dir():
        return custom_path

    # Percorso configurato ma non raggiungibile (rete assente?)
    import warnings
    warnings.warn(
        f"DATA_DIR '{custom}' non raggiungibile. Uso il percorso di default.",
        RuntimeWarning, stacklevel=2
    )
    return _get_default_data_dir()


def set_data_dir(new_path: str | Path) -> None:
    """Salva il nuovo percorso DATA_DIR in local_settings.json."""
    settings = _load_settings()
    settings["DATA_DIR"] = str(new_path).strip()
    _save_settings(settings)


def get_db_path() -> Path:
    """Percorso completo del file SQLite."""
    return get_data_dir() / DB_FILENAME


def get_photos_dir() -> Path:
    """Percorso della sottocartella foto, creata se non esiste."""
    photos = get_data_dir() / "foto"
    photos.mkdir(parents=True, exist_ok=True)
    return photos
    
def has_accepted_eula() -> bool:
    """Ritorna True se l'utente ha già accettato EULA/Privacy."""
    return bool(_load_settings().get("eula_accepted", False))

def set_eula_accepted() -> None:
    """Marca EULA come accettata in local_settings.json."""
    settings = _load_settings()
    settings["eula_accepted"] = True
    _save_settings(settings)

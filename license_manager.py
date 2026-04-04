"""
license_manager.py
Logica di validazione licenza offline basata su HMAC + Machine ID.
"""

import hashlib
import hmac
import json
import os
import platform
import subprocess
import sys
import uuid
from pathlib import Path

# ── CONFIGURA QUESTE DUE COSTANTI ────────────────────────────────────────────
SECRET_KEY = b"oF8bIDALzBU9S8tt6sArNsnDQWlu8hPLHlnyh82WTBchgTNYknYEyA"
APP_NAME   = "DentalPhoto"          # usato per il percorso del file di licenza
# ─────────────────────────────────────────────────────────────────────────────


# ---------------------------------------------------------------------------
# Machine ID
# ---------------------------------------------------------------------------

def _get_mac_address() -> str:
    """Ritorna il MAC address del primo adattatore di rete come stringa hex."""
    mac = uuid.getnode()
    # uuid.getnode() può inventare un MAC se non ne trova uno; controlliamo il bit multicast
    if (mac >> 40) & 1:
        return ""
    return "%012x" % mac


def _get_motherboard_uuid_windows() -> str:
    try:
        out = subprocess.check_output(
            ["wmic", "csproduct", "get", "UUID"],
            stderr=subprocess.DEVNULL, timeout=5
        ).decode(errors="ignore")
        lines = [l.strip() for l in out.splitlines() if l.strip()]
        # lines[0] == "UUID", lines[1] == valore
        if len(lines) >= 2 and lines[1].lower() not in ("", "to be filled by o.e.m."):
            return lines[1]
    except Exception:
        pass
    return ""


def _get_motherboard_uuid_linux() -> str:
    for path in ("/sys/class/dmi/id/product_uuid", "/etc/machine-id"):
        try:
            val = Path(path).read_text(encoding="utf-8").strip()
            if val:
                return val
        except Exception:
            pass
    return ""


def _get_motherboard_uuid_macos() -> str:
    try:
        out = subprocess.check_output(
            ["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"],
            stderr=subprocess.DEVNULL, timeout=5
        ).decode(errors="ignore")
        for line in out.splitlines():
            if "IOPlatformUUID" in line:
                # riga tipo:   "IOPlatformUUID" = "XXXXXXXX-..."
                parts = line.split("=", 1)
                if len(parts) == 2:
                    return parts[1].strip().strip('"')
    except Exception:
        pass
    return ""


def get_machine_id() -> str:
    """
    Ritorna un Machine ID stabile, univoco per hardware, cross-platform.
    È un hash SHA-256 (hex, 64 caratteri) della combinazione di
    identificativi hardware disponibili.
    """
    system = platform.system()

    if system == "Windows":
        hw_id = _get_motherboard_uuid_windows()
    elif system == "Darwin":
        hw_id = _get_motherboard_uuid_macos()
    else:
        hw_id = _get_motherboard_uuid_linux()

    mac = _get_mac_address()

    # Fallback: se non abbiamo niente, usiamo solo il MAC (meno stabile)
    combined = f"{hw_id}|{mac}|{system}"

    return hashlib.sha256(combined.encode()).hexdigest().upper()


# ---------------------------------------------------------------------------
# Verifica licenza
# ---------------------------------------------------------------------------

def _compute_serial(machine_id: str) -> str:
    """Calcola il serial key atteso per un dato Machine ID."""
    sig = hmac.new(SECRET_KEY, machine_id.encode(), hashlib.sha256).hexdigest().upper()
    # Formatta in blocchi da 6 per leggibilità: XXXXXX-XXXXXX-XXXXXX-XXXXXX-XXXXXX
    return "-".join(sig[i:i+6] for i in range(0, 30, 6))


def verifica_licenza(serial_key: str) -> bool:
    """
    Ritorna True se il serial_key è valido per questo hardware.
    Confronto in tempo costante per prevenire timing attacks.
    """
    machine_id = get_machine_id()
    expected   = _compute_serial(machine_id)
    return hmac.compare_digest(
        serial_key.strip().upper(),
        expected
    )


# ---------------------------------------------------------------------------
# Persistenza licenza
# ---------------------------------------------------------------------------

def _get_license_path() -> Path:
    """Percorso del file di licenza nascosto nella cartella dati utente."""
    system = platform.system()
    if system == "Windows":
        base = Path(os.environ.get("APPDATA", Path.home()))
    elif system == "Darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))

    folder = base / APP_NAME
    folder.mkdir(parents=True, exist_ok=True)
    # Nome file volutamente non ovvio
    return folder / ".lic"


def salva_licenza(serial_key: str) -> None:
    """Salva il serial key nel file di licenza locale."""
    data = {"serial": serial_key.strip().upper()}
    _get_license_path().write_text(json.dumps(data), encoding="utf-8")


def carica_licenza() -> str | None:
    """Carica il serial key salvato. Ritorna None se non esiste."""
    path = _get_license_path()
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data.get("serial")
    except Exception:
        return None


def licenza_valida() -> bool:
    """Controlla se esiste una licenza salvata valida per questo hardware."""
    serial = carica_licenza()
    if not serial:
        return False
    return verifica_licenza(serial)

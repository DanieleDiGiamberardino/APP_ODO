# ── Aggiungi in fondo a config_manager.py ────────────────────────────────────

def has_accepted_eula() -> bool:
    """Ritorna True se l'utente ha già accettato EULA/Privacy."""
    return bool(_load_settings().get("eula_accepted", False))


def set_eula_accepted() -> None:
    """Marca EULA come accettata in local_settings.json."""
    settings = _load_settings()
    settings["eula_accepted"] = True
    _save_settings(settings)

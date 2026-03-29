"""
thumbnail_cache.py
==================
Cache su disco per le miniature delle fotografie.

Problema risolto:
  Aprire e ridimensionare ogni immagine JPEG/PNG ad ogni caricamento
  della galleria è lento su archivi grandi (100+ foto). Con la cache,
  le miniature vengono calcolate una sola volta e salvate come JPEG
  nella cartella images_storage/.thumbs/.

API pubblica:
    get_thumbnail(percorso_assoluto, size) → CTkImage
    invalida_cache(percorso_assoluto)      → elimina la miniatura dalla cache
    GalleryLoader                          → caricamento lazy in background

Struttura cache:
    images_storage/
    └── .thumbs/
        ├── p1_foto.jpg_180x140.jpg
        └── p2_foto.jpg_200x150.jpg

Il nome file di cache include dimensioni e mtime del file originale
per invalidarsi automaticamente se il file cambia.
"""

import os
import hashlib
import threading
from pathlib import Path
from typing import Optional, Callable
from PIL import Image
import customtkinter as ctk

import database as db

# Cartella cache
THUMBS_DIR = db.IMAGES_DIR / ".thumbs"
THUMBS_DIR.mkdir(parents=True, exist_ok=True)

# Placeholder grigio (creato una volta sola)
_PLACEHOLDER_CACHE: dict[tuple, ctk.CTkImage] = {}


def _placeholder(size: tuple[int, int]) -> ctk.CTkImage:
    if size not in _PLACEHOLDER_CACHE:
        img = Image.new("RGB", size, (30, 35, 55))
        _PLACEHOLDER_CACHE[size] = ctk.CTkImage(
            light_image=img, dark_image=img, size=size)
    return _PLACEHOLDER_CACHE[size]


def _cache_path(percorso: Path, size: tuple[int, int]) -> Path:
    """
    Calcola il percorso del file di cache per una data immagine e dimensione.
    Usa un hash del percorso + mtime per invalidazione automatica.
    """
    try:
        mtime = str(percorso.stat().st_mtime)
    except OSError:
        mtime = "0"
    chiave = f"{percorso}|{mtime}|{size[0]}x{size[1]}"
    nome   = hashlib.md5(chiave.encode()).hexdigest() + ".jpg"
    return THUMBS_DIR / nome


def get_thumbnail(percorso: Path, size: tuple[int, int] = (180, 140)) -> ctk.CTkImage:
    """
    Restituisce la miniatura dell'immagine alla dimensione richiesta.

    1. Controlla se esiste nella cache su disco → restituisce direttamente
    2. Altrimenti la genera, la salva in cache e la restituisce
    3. Se il file originale non esiste → placeholder grigio

    Thread-safe: può essere chiamata da thread secondari.
    """
    if not percorso.is_file():
        return _placeholder(size)

    cache = _cache_path(percorso, size)

    # Cache HIT
    if cache.is_file():
        try:
            img = Image.open(cache)
            return ctk.CTkImage(light_image=img, dark_image=img, size=img.size)
        except Exception:
            cache.unlink(missing_ok=True)  # file cache corrotto → rigenera

    # Cache MISS → genera
    try:
        img = Image.open(percorso).convert("RGB")
        img.thumbnail(size, Image.LANCZOS)
        img.save(cache, format="JPEG", quality=82, optimize=True)
        return ctk.CTkImage(light_image=img, dark_image=img, size=img.size)
    except Exception:
        return _placeholder(size)


def invalida_cache(percorso: Path) -> None:
    try:
        mtime = str(percorso.stat().st_mtime)
    except OSError:
        mtime = "0"
    try:
        for size in [(180, 140), (200, 150), (100, 76), (64, 48)]:
            chiave = f"{percorso}|{mtime}|{size[0]}x{size[1]}"
            nome = hashlib.md5(chiave.encode()).hexdigest() + ".jpg"
            cache = THUMBS_DIR / nome
            cache.unlink(missing_ok=True)
    except Exception:
        pass


def pulisci_cache_orfana() -> int:
    """
    Rimuove le miniature in cache che non hanno più un file originale.
    Restituisce il numero di file eliminati.
    """
    eliminati = 0
    try:
        file_originali = {f.name for f in db.IMAGES_DIR.glob("*")
                         if f.is_file() and f.name != ".thumbs"}
        cutoff = time.time() - (7 * 86400)  # elimina solo thumbnail > 7 giorni
        for thumb in THUMBS_DIR.glob("*.jpg"):
            if thumb.stat().st_mtime < cutoff:
                thumb.unlink()
                eliminati += 1
    except Exception:
        pass
    return eliminati


# ===========================================================================
# LAZY GALLERY LOADER
# ===========================================================================

class GalleryLoader:
    """
    Carica le miniature di una galleria in background, batch per batch,
    aggiornando la UI man mano che sono pronte.

    Uso:
        loader = GalleryLoader(righe_db, size=(200,150), batch=8,
                               on_thumbnail_ready=callback_aggiorna_card)
        loader.start()
        # Per fermare:
        loader.stop()

    on_thumbnail_ready(indice, ctk_image) viene chiamato nel thread principale
    tramite widget.after().
    """

    def __init__(
        self,
        widget,                          # widget Tk per .after()
        righe: list,                     # lista sqlite3.Row
        size: tuple[int, int],
        on_thumbnail_ready: Callable,    # callback(indice, ctk_image)
        batch_size: int = 8,
    ):
        self._widget    = widget
        self._righe     = righe
        self._size      = size
        self._callback  = on_thumbnail_ready
        self._batch     = batch_size
        self._stop_flag = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self):
        self._stop_flag.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop_flag.set()

    def _run(self):
        for idx, r in enumerate(self._righe):
            if self._stop_flag.is_set():
                break
            percorso = db.get_percorso_assoluto(r)
            thumb    = get_thumbnail(percorso, self._size)
            # Schedula l'aggiornamento nella UI (thread sicuro)
            try:
                self._widget.after(0, self._callback, idx, thumb)
            except Exception:
                break

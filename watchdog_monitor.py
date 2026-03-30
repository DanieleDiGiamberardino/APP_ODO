"""
watchdog_monitor.py
Monitora una cartella in background e notifica la callback quando
una nuova immagine è completamente scritta su disco.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from pathlib import Path
from typing import Callable

from watchdog.events import FileCreatedEvent, FileSystemEventHandler
from watchdog.observers import Observer

# ── configurazione ────────────────────────────────────────────────────────────
log = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS: frozenset[str] = frozenset(
    {".jpg", ".jpeg", ".png", ".bmp", ".raw"}
)

# Parametri della logica anti-file-lock
_POLL_INTERVAL_S:  float = 0.25   # intervallo tra i campionamenti della dimensione
_STABLE_CHECKS:    int   = 3      # N campionamenti consecutivi uguali → file stabile
_POLL_TIMEOUT_S:   float = 30.0   # abbandona dopo questo tempo (file corrotto / errore)
_MAX_QUEUE_SIZE:   int   = 256    # limite coda interna di sicurezza


# ══════════════════════════════════════════════════════════════════════════════
#  _StabilityChecker  –  attende che un file sia completamente scritto
# ══════════════════════════════════════════════════════════════════════════════
class _StabilityChecker:
    """
    Aspetta che la dimensione del file rimanga stabile per N campionamenti
    consecutivi, garantendo che il processo che scrive (Reflex, Windows Copy,
    ecc.) abbia rilasciato il file handle.

    Gira in un thread daemon dedicato per non bloccare né il mainloop né
    il thread dell'Observer di watchdog.
    """

    def __init__(
        self,
        path: Path,
        callback: Callable[[Path], None],
        poll_interval: float = _POLL_INTERVAL_S,
        stable_checks: int   = _STABLE_CHECKS,
        timeout: float       = _POLL_TIMEOUT_S,
    ) -> None:
        self._path          = path
        self._callback      = callback
        self._poll_interval = poll_interval
        self._stable_checks = stable_checks
        self._timeout       = timeout

        t = threading.Thread(target=self._run, name=f"StabilityChecker-{path.name}", daemon=True)
        t.start()

    def _run(self) -> None:
        deadline     = time.monotonic() + self._timeout
        stable_count = 0
        last_size    = -1

        while time.monotonic() < deadline:
            try:
                current_size = os.path.getsize(self._path)
            except OSError:
                # file ancora non accessibile (es. handle esclusivo)
                stable_count = 0
                last_size    = -1
                time.sleep(self._poll_interval)
                continue

            if current_size == last_size and current_size > 0:
                stable_count += 1
            else:
                stable_count = 0

            last_size = current_size

            if stable_count >= self._stable_checks:
                # verifica ulteriore: prova ad aprire in lettura binaria
                if self._is_readable():
                    log.debug("File stabile e leggibile: %s", self._path)
                    try:
                        self._callback(self._path)
                    except Exception:
                        log.exception("Eccezione nella callback per %s", self._path)
                    return

                # il file è stabile ma non ancora rilasciato dal writer
                stable_count = 0

            time.sleep(self._poll_interval)

        log.warning("Timeout raggiunto per %s – file ignorato.", self._path)

    def _is_readable(self) -> bool:
        """Tenta di aprire il file in modalità binaria esclusiva."""
        try:
            with open(self._path, "rb"):
                return True
        except OSError:
            return False


# ══════════════════════════════════════════════════════════════════════════════
#  _ImageEventHandler  –  handler watchdog
# ══════════════════════════════════════════════════════════════════════════════
class _ImageEventHandler(FileSystemEventHandler):
    def __init__(
        self,
        callback: Callable[[Path], None],
        pending_lock: threading.Lock,
        pending_paths: set[str],
    ) -> None:
        super().__init__()
        self._callback      = callback
        self._pending_lock  = pending_lock
        self._pending_paths = pending_paths

    def on_created(self, event: FileCreatedEvent) -> None:
        if event.is_directory:
            return

        path = Path(event.src_path)

        if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            return

        abs_str = str(path.resolve())

        with self._pending_lock:
            if abs_str in self._pending_paths:
                # già in attesa di stabilità
                return
            if len(self._pending_paths) >= _MAX_QUEUE_SIZE:
                log.warning("Coda piena, file ignorato: %s", abs_str)
                return
            self._pending_paths.add(abs_str)

        log.debug("Nuovo file rilevato, avvio StabilityChecker: %s", abs_str)

        def _wrapped_callback(p: Path) -> None:
            with self._pending_lock:
                self._pending_paths.discard(str(p.resolve()))
            self._callback(p)

        _StabilityChecker(path=path, callback=_wrapped_callback)


# ══════════════════════════════════════════════════════════════════════════════
#  CameraWatchdog  –  API pubblica
# ══════════════════════════════════════════════════════════════════════════════
class CameraWatchdog:
    """
    Monitora `folder_path` in un thread daemon separato e chiama
    `on_new_file(percorso_assoluto: Path)` ogni volta che una nuova immagine
    supportata risulta completamente scritta su disco.

    La callback viene invocata dal thread interno del StabilityChecker.
    Chi usa questa classe è responsabile di sincronizzare con il mainloop
    di Tkinter (es. tramite `root.after(0, lambda: ...)`).

    Esempio d'uso:
        def gestisci(path: Path):
            root.after(0, lambda p=path: carica_immagine(p))

        wd = CameraWatchdog("/Volumes/REFLEX/DCIM", on_new_file=gestisci)
        wd.start()
        ...
        wd.stop()
    """

    def __init__(
        self,
        folder_path: str | Path,
        on_new_file: Callable[[Path], None],
        recursive: bool = True,
    ) -> None:
        self._folder   = Path(folder_path).resolve()
        self._callback = on_new_file
        self._recursive = recursive

        self._observer:      Observer | None = None
        self._running_lock   = threading.Lock()
        self._is_running     = False

        # traccia i file attualmente in attesa di stabilità
        self._pending_lock:  threading.Lock = threading.Lock()
        self._pending_paths: set[str]        = set()

        if not self._folder.exists():
            raise FileNotFoundError(
                f"CameraWatchdog: la cartella non esiste → {self._folder}"
            )
        if not self._folder.is_dir():
            raise NotADirectoryError(
                f"CameraWatchdog: il percorso non è una cartella → {self._folder}"
            )

    # ── ciclo di vita ──────────────────────────────────────────────────────────
    def start(self) -> None:
        """Avvia il monitoraggio. Chiamabile una sola volta (usa restart() per riavviare)."""
        with self._running_lock:
            if self._is_running:
                log.warning("CameraWatchdog già avviato.")
                return

            handler = _ImageEventHandler(
                callback      = self._callback,
                pending_lock  = self._pending_lock,
                pending_paths = self._pending_paths,
            )

            self._observer = Observer()
            self._observer.schedule(handler, str(self._folder), recursive=self._recursive)
            self._observer.daemon = True
            self._observer.start()
            self._is_running = True

        log.info("CameraWatchdog avviato → %s (recursive=%s)", self._folder, self._recursive)

    def stop(self) -> None:
        """Ferma il monitoraggio in modo pulito."""
        with self._running_lock:
            if not self._is_running or self._observer is None:
                return
            self._observer.stop()
            self._observer.join(timeout=5.0)
            self._observer = None
            self._is_running = False

        with self._pending_lock:
            self._pending_paths.clear()

        log.info("CameraWatchdog fermato.")

    def restart(self, folder_path: str | Path | None = None) -> None:
        """Ferma e riavvia, opzionalmente su una cartella diversa."""
        self.stop()
        if folder_path is not None:
            new_folder = Path(folder_path).resolve()
            if not new_folder.is_dir():
                raise NotADirectoryError(str(new_folder))
            self._folder = new_folder
        self.start()

    # ── proprietà di sola lettura ──────────────────────────────────────────────
    @property
    def is_running(self) -> bool:
        return self._is_running

    @property
    def watched_folder(self) -> Path:
        return self._folder

    @property
    def pending_count(self) -> int:
        """Numero di file attualmente in attesa di stabilità."""
        with self._pending_lock:
            return len(self._pending_paths)

    # ── context manager ────────────────────────────────────────────────────────
    def __enter__(self) -> "CameraWatchdog":
        self.start()
        return self

    def __exit__(self, *_) -> None:
        self.stop()

    def __repr__(self) -> str:
        status = "running" if self._is_running else "stopped"
        return f"<CameraWatchdog [{status}] folder={self._folder!r}>"

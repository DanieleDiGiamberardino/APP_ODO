"""
grid_overlay.py
Gestore della griglia DSD (Digital Smile Design) basato su Proporzioni Auree.
Perfettamente integrato con lo Smart Cropping di _ImageCanvas.
"""

from __future__ import annotations
import tkinter as tk
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    # Importazione solo per il type-checker; evita dipendenze circolari.
    from ui_before_after import _ImageCanvas

# ══════════════════════════════════════════════════════════════════════════════
#  Costanti visive e Proporzioni
# ══════════════════════════════════════════════════════════════════════════════
_TAG_GRID         = "dsd_grid"
_COLOR_MEDIAN     = "#00e5ff"      # Ciano (Mediana)
_COLOR_HORIZONTAL = "#ffd600"      # Giallo (Piani Orizzontali)
_COLOR_GOLDEN     = "#ff00ff"      # Magenta (Griglia Aurea)
_COLOR_HANDLE     = "#ffffff"
_ALPHA_DASH       = (10, 6)
_HANDLE_RADIUS    = 7
_HIT_TOLERANCE    = 10

# Proporzioni Auree (phi = 1.618...)
PHI = 1.618034
GOLDEN_RATIOS = {
    "central_incisor": PHI,
    "lateral_incisor": 1.0,
    "canine": 1.0 / PHI,
}

# ══════════════════════════════════════════════════════════════════════════════
#  GridOverlayManager
# ══════════════════════════════════════════════════════════════════════════════
class GridOverlayManager:
    """
    Gestore della griglia DSD da agganciare a un'istanza di _ImageCanvas.
    """

    def __init__(self, canvas: "_ImageCanvas") -> None:
        self._canvas = canvas
        self._visible: bool = False

        # Stato normalizzato (0.0 = bordo top/left dell'immagine, 1.0 = bordo bottom/right)
        self.bip_norm = 0.3      # Piano Bipupillare
        self.occ_norm = 0.7      # Piano Occlusale
        self.med_norm = 0.5      # Linea Mediana
        self.golden_w = 0.05     # Larghezza base della proporzione aurea

        self._drag_target: str = ""
        self._bind_events()

    # --------------------------------------------------------------------------
    #  API pubblica
    # --------------------------------------------------------------------------
    def toggle_grid(self) -> bool:
        """Accende/spegne la griglia."""
        self._visible = not self._visible
        if not self._visible:
            self._canvas.delete(_TAG_GRID)
        else:
            self.update_grid_render()
        return self._visible

    @property
    def visible(self) -> bool:
        return self._visible

    def reset(self) -> None:
        """Riporta le linee al centro dell'immagine."""
        self.bip_norm = 0.3
        self.occ_norm = 0.7
        self.med_norm = 0.5
        self.golden_w = 0.05
        if self._visible:
            self.update_grid_render()

    # --------------------------------------------------------------------------
    #  Motore di Rendering e Proiezione
    # --------------------------------------------------------------------------
    def _projection_params(self):
        """Restituisce i parametri attuali di zoom e pan dell'immagine sottostante."""
        c = self._canvas
        state = c._state
        cw = c.winfo_width()
        ch = c.winfo_height()
        
        if cw < 4 or ch < 4 or c._pil_img is None:
            return None
            
        img_w, img_h = c._pil_img.size
        base = min(cw / img_w, ch / img_h)
        s = base * state.scale
        cx = cw / 2 + state.offset_x
        cy = ch / 2 + state.offset_y
        
        return cx, cy, s, img_w, img_h

    def _norm_to_canvas(self, norm_x: float, norm_y: float):
        """Converte coordinate dell'immagine (0.0-1.0) in Pixel effettivi sullo schermo."""
        params = self._projection_params()
        if not params: return 0.0, 0.0
        cx, cy, s, img_w, img_h = params
        px = cx + (norm_x * img_w - img_w / 2) * s
        py = cy + (norm_y * img_h - img_h / 2) * s
        return px, py

    def _canvas_to_norm(self, px: float, py: float):
        """Converte la posizione del Mouse in coordinate immagine (0.0-1.0)."""
        params = self._projection_params()
        if not params: return 0.5, 0.5
        cx, cy, s, img_w, img_h = params
        norm_x = (px - cx) / s / img_w + 0.5
        norm_y = (py - cy) / s / img_h + 0.5
        return norm_x, norm_y

    def update_grid_render(self) -> None:
        """Ridisegna le linee sul canvas senza cancellare la fotografia."""
        if not self._visible: return
        
        params = self._projection_params()
        if not params:
            self._canvas.delete(_TAG_GRID)
            return

        # Cancella SOLO le linee della griglia (salva l'immagine!)
        self._canvas.delete(_TAG_GRID)
        cw, ch = self._canvas.winfo_width(), self._canvas.winfo_height()

        # Calcolo coordinate in pixel
        _, py_bip = self._norm_to_canvas(0, self.bip_norm)
        _, py_occ = self._norm_to_canvas(0, self.occ_norm)
        px_med, _ = self._norm_to_canvas(self.med_norm, 0)

        # 1. PIANI ORIZZONTALI (Bipupillare e Occlusale)
        self._canvas.create_line(0, py_bip, cw, py_bip, fill=_COLOR_HORIZONTAL, dash=_ALPHA_DASH, tags=_TAG_GRID)
        self._draw_handle(cw / 2, py_bip, "Bipupillare", "↕", _COLOR_HORIZONTAL)

        self._canvas.create_line(0, py_occ, cw, py_occ, fill=_COLOR_HORIZONTAL, dash=_ALPHA_DASH, tags=_TAG_GRID)
        self._draw_handle(cw / 2, py_occ, "Occlusale / Incisale", "↕", _COLOR_HORIZONTAL)

        # 2. LINEA MEDIANA (Verticale Centrale)
        self._canvas.create_line(px_med, 0, px_med, ch, fill=_COLOR_MEDIAN, dash=_ALPHA_DASH, tags=_TAG_GRID)
        self._draw_handle(px_med, ch / 4, "Mediana", "↔", _COLOR_MEDIAN)

        # 3. GRIGLIA AUREA (Golden Proportion)
        # Calcoliamo le distanze relative per Centrale, Laterale e Canino
        w_centrale = GOLDEN_RATIOS["central_incisor"] * self.golden_w
        w_laterale = w_centrale + GOLDEN_RATIOS["lateral_incisor"] * self.golden_w
        w_canino   = w_laterale + GOLDEN_RATIOS["canine"] * self.golden_w

        offsets = [
            w_centrale, w_laterale, w_canino,         # Destra
            -w_centrale, -w_laterale, -w_canino       # Sinistra
        ]
        
        # Disegna le 6 linee dei denti
        for off in offsets:
            px_gold, _ = self._norm_to_canvas(self.med_norm + off, 0)
            self._canvas.create_line(px_gold, 0, px_gold, ch, fill=_COLOR_GOLDEN, dash=(4,4), tags=_TAG_GRID)

        # 4. HANDLE AUREO (per fisarmonica)
        # Lo posizioniamo sulla linea dell'incisivo centrale destro
        px_handle_gold, _ = self._norm_to_canvas(self.med_norm + w_centrale, 0)
        self._draw_handle(px_handle_gold, ch / 2, "← Regola Aurea →", "↔", _COLOR_GOLDEN)

    def _draw_handle(self, x: float, y: float, label: str, icon: str, color: str):
        """Disegna un pallino trascinabile con un'etichetta."""
        r = _HANDLE_RADIUS
        # Ombra scura (FIXATA: usato un grigio scuro solido supportato da Tkinter)
        self._canvas.create_oval(x - r - 2, y - r - 2, x + r + 2, y + r + 2, fill="#111928", outline="", tags=_TAG_GRID)
        # Cerchio colorato e icona
        self._canvas.create_oval(x - r, y - r, x + r, y + r, fill=color, outline=_COLOR_HANDLE, tags=_TAG_GRID)
        self._canvas.create_text(x, y, text=icon, fill="#000", font=("Segoe UI", 8, "bold"), tags=_TAG_GRID)
        # Testo
        self._canvas.create_text(x + r + 8, y, text=label, fill=color, font=("Segoe UI", 9, "bold"), anchor="w", tags=_TAG_GRID)

    # --------------------------------------------------------------------------
    #  Interazione e Mouse Event (Drag & Drop)
    # --------------------------------------------------------------------------
    def _hit_test(self, mx: float, my: float) -> str:
        """Capisce quale linea stiamo cliccando."""
        _, py_bip = self._norm_to_canvas(0, self.bip_norm)
        _, py_occ = self._norm_to_canvas(0, self.occ_norm)
        px_med, _ = self._norm_to_canvas(self.med_norm, 0)
        
        # Controlla la posizione dell'handle Aureo
        w_centrale = GOLDEN_RATIOS["central_incisor"] * self.golden_w
        px_gold, _ = self._norm_to_canvas(self.med_norm + w_centrale, 0)

        # Ritorna l'ID se siamo entro la TOLLERANZA (in pixel)
        if abs(mx - px_gold) <= _HIT_TOLERANCE: return "gold" # priorità handle aureo
        if abs(mx - px_med) <= _HIT_TOLERANCE:  return "med"
        if abs(my - py_bip) <= _HIT_TOLERANCE:  return "bip"
        if abs(my - py_occ) <= _HIT_TOLERANCE:  return "occ"
        return ""

    def _bind_events(self) -> None:
        c = self._canvas
        c.bind("<ButtonPress-1>",   self._on_press,   add="+")
        c.bind("<B1-Motion>",       self._on_drag,    add="+")
        c.bind("<ButtonRelease-1>", self._on_release, add="+")
        c.bind("<Motion>",          self._on_motion,  add="+")

    def _on_press(self, event: tk.Event) -> None:
        if not self._visible: return
        self._drag_target = self._hit_test(event.x, event.y)

    def _on_drag(self, event: tk.Event) -> str | None:
        if not self._drag_target: return
        
        # Posizione del mouse in percentuale rispetto all'immagine
        nx, ny = self._canvas_to_norm(event.x, event.y)

        if self._drag_target == "bip":
            self.bip_norm = max(0.0, min(1.0, ny))
        elif self._drag_target == "occ":
            self.occ_norm = max(0.0, min(1.0, ny))
        elif self._drag_target == "med":
            self.med_norm = max(0.0, min(1.0, nx))
        elif self._drag_target == "gold":
            # Calcolo Fisarmonica: Larghezza Aurea = (Distanza Mouse - Mediana) / Rapporto Incisivo
            diff = nx - self.med_norm
            self.golden_w = max(0.01, min(0.3, diff / GOLDEN_RATIOS["central_incisor"]))

        self.update_grid_render()
        
        # FONDAMENTALE: blocca la propagazione dell'evento per impedire il "Pan" dell'immagine!
        return "break"

    def _on_release(self, event: tk.Event) -> None:
        self._drag_target = ""
        self._canvas.configure(cursor="fleur")

    def _on_motion(self, event: tk.Event) -> None:
        if not self._visible: return
        hit = self._hit_test(event.x, event.y)
        
        # Cambia il cursore se siamo sopra una linea trascinabile
        if hit in ("bip", "occ"):
            self._canvas.configure(cursor="sb_v_double_arrow")
        elif hit in ("med", "gold"):
            self._canvas.configure(cursor="sb_h_double_arrow")
        elif not self._drag_target:
            self._canvas.configure(cursor="fleur")
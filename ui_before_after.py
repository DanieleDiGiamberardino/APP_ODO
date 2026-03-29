"""
ui_before_after.py  — Rework v2
================================
Visualizzatore Before/After con slider, zoom, pan e modalità multipla.

Modalità canvas:
  SLIDER     → slider verticale trascinabile (default)
  AFFIANCATO → le due immagini al 50% affiancate
  OVERLAY    → fade blend controllato da slider opacità

Zoom / Pan:
  Rotella mouse  → zoom in / out (0.25x – 8x)
  Tasto 0        → reset zoom e pan
  Trascina (zoom > 1) → pan dell'immagine

Tastiera (foco sul canvas):
  ← →   → sposta slider ±5%
  + -   → zoom
  0     → reset
  S     → swap lati
  M     → cicla modalità

Azioni:
  Auto-match     → coppia Pre-op / Post-op stesso paziente/dente
  Scambia        → inverti i lati
  Salva JPEG     → esporta il composito corrente
  Zoom fit       → adatta al canvas
"""

import io
import threading
import tkinter as tk
from tkinter import filedialog
from datetime import date
from pathlib import Path
from typing import Optional

import customtkinter as ctk
from PIL import Image, ImageDraw, ImageEnhance

import database as db

# ─────────────────────────────────────────────────────────────────────────────
# Design tokens
# ─────────────────────────────────────────────────────────────────────────────

C = {
    "bg":          "#080c18",
    "card":        "#0f1629",
    "card2":       "#111827",
    "entry":       "#070b14",
    "accent":      "#2563eb",
    "accent_h":    "#1d4ed8",
    "prima":       "#e94560",   # rosso PRIMA
    "dopo":        "#10b981",   # verde DOPO
    "grigio":      "#64748b",
    "chiaro":      "#e2e8f0",
    "border":      "#1e2d4a",
    "handle_bg":   "#ffffff",
    "handle_bd":   "#2563eb",
    "overlay_bg":  "#00000099",
}

F = {
    "sez":   ("Segoe UI", 12, "bold"),
    "nrm":   ("Segoe UI", 11),
    "sml":   ("Segoe UI", 10),
    "micro": ("Segoe UI", 9),
    "badge": ("Segoe UI", 8, "bold"),
}

HANDLE_R   = 16     # raggio maniglia slider
SLIDER_W   = 3      # larghezza linea slider
ZOOM_MIN   = 0.25
ZOOM_MAX   = 8.0
ZOOM_STEP  = 1.25

MODE_SLIDER     = "slider"
MODE_AFFIANCATO = "affiancato"
MODE_OVERLAY    = "overlay"


# ─────────────────────────────────────────────────────────────────────────────
# Utility
# ─────────────────────────────────────────────────────────────────────────────

def _pil_to_tk(img: Image.Image) -> tk.PhotoImage:
    buf = io.BytesIO()
    img.save(buf, format="PPM")
    buf.seek(0)
    return tk.PhotoImage(data=buf.read())


def _fit(img: Image.Image, W: int, H: int) -> tuple[Image.Image, int, int]:
    """Ridimensiona img al fit dentro W×H, restituisce (img_ridim, ox, oy)."""
    iw, ih = img.size
    scale = min(W / iw, H / ih)
    nw, nh = max(1, int(iw * scale)), max(1, int(ih * scale))
    resized = img.resize((nw, nh), Image.LANCZOS)
    ox = (W - nw) // 2
    oy = (H - nh) // 2
    return resized, ox, oy


# ─────────────────────────────────────────────────────────────────────────────
# Canvas Before/After — motore di rendering
# ─────────────────────────────────────────────────────────────────────────────

class BeforeAfterCanvas(tk.Canvas):
    """
    Canvas custom con:
      - Tre modalità: slider / affiancato / overlay
      - Zoom + pan via mouse
      - Cache delle immagini scalate (evita resize ad ogni frame)
    """

    def __init__(self, master, **kwargs):
        kwargs.setdefault("bg", C["bg"])
        kwargs.setdefault("highlightthickness", 0)
        super().__init__(master, **kwargs)

        # Immagini sorgente (PIL full-res)
        self._img_prima: Optional[Image.Image] = None
        self._img_dopo:  Optional[Image.Image] = None

        # Cache dimensioni canvas
        self._cw = 0
        self._ch = 0

        # Cache immagini scalate per la canvas size corrente
        self._cache_prima: Optional[Image.Image] = None
        self._cache_dopo:  Optional[Image.Image] = None
        self._cache_size: tuple = (0, 0)

        # Riferimenti anti-GC
        self._tk_refs: list = []

        # Stato slider
        self._slider_pct: float = 0.5
        self._dragging_slider = False

        # Zoom / pan
        self._zoom:   float = 1.0
        self._pan_x:  float = 0.0
        self._pan_y:  float = 0.0
        self._pan_start: Optional[tuple] = None

        # Modalità
        self._mode:    str   = MODE_SLIDER
        self._opacity: float = 0.5   # overlay mode

        # Callback esterna (per aggiornare cursore etc.)
        self.on_slider_move = None

        self._bind_events()

    # ── eventi ───────────────────────────────────────────────────────────────

    def _bind_events(self):
        self.bind("<Configure>",        self._on_configure)
        self.bind("<ButtonPress-1>",    self._on_press)
        self.bind("<B1-Motion>",        self._on_drag)
        self.bind("<ButtonRelease-1>",  self._on_release)
        self.bind("<ButtonPress-2>",    self._on_pan_start)
        self.bind("<B2-Motion>",        self._on_pan)
        self.bind("<ButtonPress-3>",    self._on_pan_start)
        self.bind("<B3-Motion>",        self._on_pan)
        self.bind("<MouseWheel>",       self._on_wheel)
        self.bind("<Button-4>",         lambda e: self._zoom_at(e, +1))
        self.bind("<Button-5>",         lambda e: self._zoom_at(e, -1))
        self.bind("<KeyPress>",         self._on_key)
        self.configure(cursor="crosshair")

    def _on_configure(self, event):
        new_size = (event.width, event.height)
        if new_size != self._cache_size:
            self._cache_prima = None
            self._cache_dopo  = None
            self._cache_size  = new_size
        self._cw = event.width
        self._ch = event.height
        self._render()

    # ── caricamento ──────────────────────────────────────────────────────────

    def carica(self, path_prima: Optional[Path], path_dopo: Optional[Path]):
        def _load(p):
            try:
                if p and Path(p).is_file():
                    return Image.open(p).convert("RGB")
            except Exception:
                pass
            return None

        def _job():
            img_p = _load(path_prima)
            img_d = _load(path_dopo)
            self.after(0, lambda: self._imposta(img_p, img_d))

        threading.Thread(target=_job, daemon=True).start()

    def _imposta(self, img_p, img_d):
        self._img_prima = img_p
        self._img_dopo  = img_d
        self._cache_prima = None
        self._cache_dopo  = None
        self._slider_pct  = 0.5
        self._zoom        = 1.0
        self._pan_x       = 0.0
        self._pan_y       = 0.0
        self._render()

    # ── rendering ────────────────────────────────────────────────────────────

    def _render(self):
        self.delete("all")
        self._tk_refs.clear()

        W, H = self._cw or self.winfo_width(), self._ch or self.winfo_height()
        if W < 10 or H < 10:
            return

        if not self._img_prima and not self._img_dopo:
            self._placeholder(W, H)
            return

        if self._mode == MODE_SLIDER:
            self._render_slider(W, H)
        elif self._mode == MODE_AFFIANCATO:
            self._render_affiancato(W, H)
        else:
            self._render_overlay(W, H)

    def _placeholder(self, W, H):
        self.create_text(W // 2, H // 2 - 18,
                         text="⟵  Seleziona PRIMA",
                         fill=C["prima"], font=("Segoe UI", 12, "bold"))
        self.create_text(W // 2, H // 2 + 6,
                         text="Seleziona DOPO  ⟶",
                         fill=C["dopo"], font=("Segoe UI", 12, "bold"))
        self.create_text(W // 2, H // 2 + 32,
                         text="oppure usa Auto-match",
                         fill=C["grigio"], font=("Segoe UI", 10))

    def _get_cached(self, W, H):
        """Restituisce le due immagini scalate al canvas size (con cache)."""
        if self._cache_size != (W, H):
            self._cache_prima = None
            self._cache_dopo  = None
            self._cache_size  = (W, H)

        if self._img_prima and self._cache_prima is None:
            self._cache_prima, _, _ = _fit(self._img_prima, W, H)
        if self._img_dopo and self._cache_dopo is None:
            self._cache_dopo, _, _ = _fit(self._img_dopo, W, H)

        return self._cache_prima, self._cache_dopo

    def _apply_zoom_pan(self, img: Image.Image, W, H) -> tuple:
        """Applica zoom + pan a un'immagine già fittata nella canvas."""
        if self._zoom == 1.0 and self._pan_x == 0 and self._pan_y == 0:
            iw, ih = img.size
            ox = (W - iw) // 2
            oy = (H - ih) // 2
            return img, ox, oy

        iw, ih = img.size
        nw = max(1, int(iw * self._zoom))
        nh = max(1, int(ih * self._zoom))
        zoomed = img.resize((nw, nh), Image.NEAREST if self._zoom > 2 else Image.LANCZOS)
        ox = int((W - nw) // 2 + self._pan_x)
        oy = int((H - nh) // 2 + self._pan_y)
        return zoomed, ox, oy

    def _draw_img(self, img, ox, oy, clip_left=None, clip_right=None):
        """Disegna un'immagine (opzionalmente ritagliata) sulla canvas."""
        if clip_left is not None or clip_right is not None:
            x0 = max(0, clip_left or 0)
            x1 = min(img.width, (clip_right or img.width))
            if x1 <= x0:
                return
            img = img.crop((x0, 0, x1, img.height))
            ox  = ox + x0
        tk_img = _pil_to_tk(img)
        self._tk_refs.append(tk_img)
        self.create_image(ox, oy, image=tk_img, anchor="nw")

    # Modalità SLIDER
    def _render_slider(self, W, H):
        p, d = self._get_cached(W, H)

        split_x = int(W * self._slider_pct)

        if p:
            pz, ox, oy = self._apply_zoom_pan(p, W, H)
            # clip destra a split_x
            cx1 = split_x - ox
            self._draw_img(pz, ox, oy, clip_right=cx1)

        if d:
            dz, ox, oy = self._apply_zoom_pan(d, W, H)
            # clip sinistra a split_x
            cx0 = split_x - ox
            self._draw_img(dz, ox, oy, clip_left=cx0)

        self._draw_slider_line(split_x, H)
        self._draw_labels(split_x, W)

    # Modalità AFFIANCATO
    def _render_affiancato(self, W, H):
        half = W // 2
        if self._img_prima:
            p, ox, oy = _fit(self._img_prima, half - 2, H)
            tk_p = _pil_to_tk(p)
            self._tk_refs.append(tk_p)
            self.create_image(ox, oy, image=tk_p, anchor="nw")

        if self._img_dopo:
            d, ox, oy = _fit(self._img_dopo, half - 2, H)
            tk_d = _pil_to_tk(d)
            self._tk_refs.append(tk_d)
            self.create_image(half + 2 + ox, oy, image=tk_d, anchor="nw")

        # Linea centrale
        self.create_line(half, 0, half, H, fill=C["border"], width=1, dash=(4, 4))

        # Label fissi
        self._pill_label(8, 8, "PRIMA", C["prima"], anchor="nw")
        self._pill_label(W - 8, 8, "DOPO", C["dopo"], anchor="ne")

    # Modalità OVERLAY
    def _render_overlay(self, W, H):
        if not self._img_prima and not self._img_dopo:
            self._placeholder(W, H)
            return

        p, d = self._get_cached(W, H)

        if p and d:
            # Blend con opacità
            pw, ph = p.size
            dw, dh = d.size
            # Allinea dimensioni
            w, h = max(pw, dw), max(ph, dh)
            pp = Image.new("RGB", (w, h))
            pp.paste(p, ((w - pw) // 2, (h - ph) // 2))
            dd = Image.new("RGB", (w, h))
            dd.paste(d, ((w - dw) // 2, (h - dh) // 2))
            blended = Image.blend(pp, dd, self._opacity)
            ox = (W - w) // 2
            oy = (H - h) // 2
            tk_b = _pil_to_tk(blended)
            self._tk_refs.append(tk_b)
            self.create_image(ox, oy, image=tk_b, anchor="nw")
        elif p:
            img, ox, oy = _fit(p, W, H)
            tk_i = _pil_to_tk(img)
            self._tk_refs.append(tk_i)
            self.create_image(ox, oy, image=tk_i, anchor="nw")
        elif d:
            img, ox, oy = _fit(d, W, H)
            tk_i = _pil_to_tk(img)
            self._tk_refs.append(tk_i)
            self.create_image(ox, oy, image=tk_i, anchor="nw")

        # Indicatore opacità
        pct = int(self._opacity * 100)
        self.create_text(W // 2, H - 16,
                         text=f"PRIMA ←  {100 - pct}% / {pct}%  → DOPO",
                         fill=C["chiaro"], font=("Segoe UI", 9, "bold"))

    # ── decorazioni canvas ────────────────────────────────────────────────────

    def _draw_slider_line(self, x, H):
        # Linea
        self.create_line(x, 0, x, H, fill="#ffffff", width=SLIDER_W)
        # Glow
        self.create_line(x, 0, x, H, fill=C["accent"] + "55",
                         width=SLIDER_W + 4)
        # Maniglia
        cy = H // 2
        r  = HANDLE_R
        self.create_oval(x - r, cy - r, x + r, cy + r,
                         fill=C["handle_bg"],
                         outline=C["handle_bd"], width=2)
        # Frecce dentro la maniglia
        self.create_text(x, cy - 1,
                         text="◀▶",
                         fill=C["accent"],
                         font=("Segoe UI", 8, "bold"))
        # Indicatore %
        pct_txt = f"{int(self._slider_pct * 100)}%"
        self.create_text(x, cy + r + 10,
                         text=pct_txt,
                         fill="#ffffff",
                         font=("Segoe UI", 8))

    def _draw_labels(self, split_x, W):
        if split_x > 60:
            self._pill_label(8, 8, "PRIMA", C["prima"], anchor="nw")
        if split_x < W - 60:
            self._pill_label(W - 8, 8, "DOPO", C["dopo"], anchor="ne")

    def _pill_label(self, x, y, text, color, anchor="nw"):
        """Label con sfondo pill."""
        # Sfondo
        tw = len(text) * 7 + 16
        th = 20
        if anchor == "nw":
            x0, y0 = x, y
        else:
            x0, y0 = x - tw, y
        self.create_rectangle(x0, y0, x0 + tw, y0 + th,
                               fill=color + "cc", outline="", width=0)
        cx = x0 + tw // 2
        cy = y0 + th // 2
        self.create_text(cx, cy,
                         text=text, fill="#ffffff",
                         font=("Segoe UI", 9, "bold"),
                         anchor="center")

    # ── mouse ─────────────────────────────────────────────────────────────────

    def _on_press(self, event):
        self.focus_set()
        if self._mode == MODE_SLIDER:
            self._dragging_slider = True
            self._update_slider(event.x)
        elif self._mode == MODE_OVERLAY:
            self._dragging_slider = True
            self._update_overlay(event.x)

    def _on_drag(self, event):
        if self._dragging_slider:
            if self._mode == MODE_SLIDER:
                self._update_slider(event.x)
            elif self._mode == MODE_OVERLAY:
                self._update_overlay(event.x)

    def _on_release(self, event):
        self._dragging_slider = False

    def _on_pan_start(self, event):
        self._pan_start = (event.x, event.y, self._pan_x, self._pan_y)

    def _on_pan(self, event):
        if self._pan_start and self._zoom > 1.0:
            sx, sy, px0, py0 = self._pan_start
            self._pan_x = px0 + (event.x - sx)
            self._pan_y = py0 + (event.y - sy)
            self._render()

    def _on_wheel(self, event):
        self._zoom_at(event, +1 if event.delta > 0 else -1)

    def _zoom_at(self, event, direction):
        old = self._zoom
        if direction > 0:
            self._zoom = min(ZOOM_MAX, self._zoom * ZOOM_STEP)
        else:
            self._zoom = max(ZOOM_MIN, self._zoom / ZOOM_STEP)
        # Zoom centrato sul cursore
        if self._zoom != old:
            W, H = self._cw, self._ch
            cx = event.x - W // 2
            cy = event.y - H // 2
            ratio = self._zoom / old
            self._pan_x = self._pan_x * ratio + cx * (1 - ratio)
            self._pan_y = self._pan_y * ratio + cy * (1 - ratio)
            self._render()

    def _update_slider(self, x):
        W = self._cw or self.winfo_width()
        if W > 0:
            self._slider_pct = max(0.02, min(0.98, x / W))
            self._render()
            if self.on_slider_move:
                self.on_slider_move(self._slider_pct)

    def _update_overlay(self, x):
        W = self._cw or self.winfo_width()
        if W > 0:
            self._opacity = max(0.0, min(1.0, x / W))
            self._render()

    # ── tastiera ──────────────────────────────────────────────────────────────

    def _on_key(self, event):
        k = event.keysym
        if k == "Left":
            self.slider_step(-0.05)
        elif k == "Right":
            self.slider_step(+0.05)
        elif k in ("plus", "equal"):
            self._zoom = min(ZOOM_MAX, self._zoom * ZOOM_STEP)
            self._render()
        elif k == "minus":
            self._zoom = max(ZOOM_MIN, self._zoom / ZOOM_STEP)
            self._render()
        elif k == "0":
            self.reset_zoom()
        elif k in ("s", "S"):
            if self._swap_callback:
                self._swap_callback()
        elif k in ("m", "M"):
            if self._mode_callback:
                self._mode_callback()

    # Callback per tasti S / M
    _swap_callback = None
    _mode_callback = None

    # ── API pubblica ──────────────────────────────────────────────────────────

    def slider_step(self, delta: float):
        if self._mode == MODE_SLIDER:
            self._slider_pct = max(0.02, min(0.98, self._slider_pct + delta))
        elif self._mode == MODE_OVERLAY:
            self._opacity = max(0.0, min(1.0, self._opacity + delta))
        self._render()

    def set_mode(self, mode: str):
        self._mode = mode
        self._render()

    def set_opacity(self, v: float):
        self._opacity = v
        self._render()

    def reset_zoom(self):
        self._zoom  = 1.0
        self._pan_x = 0.0
        self._pan_y = 0.0
        self._render()

    def get_composite(self) -> Optional[Image.Image]:
        """Immagine composita full-res per il salvataggio."""
        if self._mode == MODE_SLIDER:
            if not self._img_prima or not self._img_dopo:
                return self._img_prima or self._img_dopo
            W = max(self._img_prima.width, self._img_dopo.width)
            H = max(self._img_prima.height, self._img_dopo.height)
            out  = Image.new("RGB", (W, H))
            pri  = self._img_prima.resize((W, H), Image.LANCZOS)
            post = self._img_dopo.resize((W, H), Image.LANCZOS)
            sx   = int(W * self._slider_pct)
            out.paste(pri.crop((0, 0, sx, H)),   (0, 0))
            out.paste(post.crop((sx, 0, W, H)), (sx, 0))
            draw = ImageDraw.Draw(out)
            draw.line([(sx, 0), (sx, H)], fill="white", width=4)
            return out

        elif self._mode == MODE_AFFIANCATO:
            imgs = [i for i in [self._img_prima, self._img_dopo] if i]
            if not imgs:
                return None
            H = max(i.height for i in imgs)
            W = sum(i.width for i in imgs) + 8
            out = Image.new("RGB", (W, H), (20, 20, 40))
            x   = 0
            for img in imgs:
                out.paste(img, (x, (H - img.height) // 2))
                x += img.width + 8
            return out

        elif self._mode == MODE_OVERLAY:
            if self._img_prima and self._img_dopo:
                W = max(self._img_prima.width,  self._img_dopo.width)
                H = max(self._img_prima.height, self._img_dopo.height)
                p = self._img_prima.resize((W, H), Image.LANCZOS)
                d = self._img_dopo.resize((W, H),  Image.LANCZOS)
                return Image.blend(p, d, self._opacity)
            return self._img_prima or self._img_dopo

        return None


# ─────────────────────────────────────────────────────────────────────────────
# BeforeAfterFrame — pannello embedded principale
# ─────────────────────────────────────────────────────────────────────────────

class BeforeAfterFrame(ctk.CTkFrame):

    def __init__(self, master, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self._row_prima = None
        self._row_dopo  = None
        self._mode      = MODE_SLIDER
        self._build_ui()

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self._build_toolbar()
        self._build_canvas_area()

    # ── toolbar ───────────────────────────────────────────────────────────────

    def _build_toolbar(self):
        tb = ctk.CTkFrame(self, fg_color=C["card"], corner_radius=12)
        tb.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        tb.grid_columnconfigure(2, weight=1)

        # ─ Blocco PRIMA ──────────────────────────────────────────────
        prima_block = ctk.CTkFrame(tb, fg_color=C["card2"], corner_radius=8)
        prima_block.grid(row=0, column=0, padx=(12, 6), pady=10, sticky="nsew")

        ctk.CTkLabel(prima_block, text="PRIMA",
                     font=F["badge"], text_color=C["prima"],
                     fg_color="transparent").grid(
            row=0, column=0, columnspan=2, padx=10, pady=(8, 2), sticky="w")

        self._thumb_prima = ctk.CTkLabel(prima_block, text="—",
                                          width=80, height=56,
                                          fg_color=C["entry"], corner_radius=6,
                                          text_color=C["grigio"])
        self._thumb_prima.grid(row=1, column=0, padx=(8, 4), pady=(0, 4))

        info_l = ctk.CTkFrame(prima_block, fg_color="transparent")
        info_l.grid(row=1, column=1, sticky="nsew", padx=(0, 6))
        self._lbl_prima = ctk.CTkLabel(info_l, text="Nessuna foto",
                                        font=F["micro"],
                                        text_color=C["grigio"],
                                        wraplength=160, justify="left",
                                        anchor="nw")
        self._lbl_prima.pack(anchor="nw")
        ctk.CTkButton(info_l, text="Scegli…",
                      font=F["micro"], height=26, width=76,
                      fg_color=C["prima"], hover_color="#c73652",
                      command=lambda: self._apri_picker("prima")).pack(
            anchor="sw", pady=(4, 0))

        # ─ Blocco DOPO ───────────────────────────────────────────────
        dopo_block = ctk.CTkFrame(tb, fg_color=C["card2"], corner_radius=8)
        dopo_block.grid(row=0, column=1, padx=(0, 6), pady=10, sticky="nsew")

        ctk.CTkLabel(dopo_block, text="DOPO",
                     font=F["badge"], text_color=C["dopo"],
                     fg_color="transparent").grid(
            row=0, column=0, columnspan=2, padx=10, pady=(8, 2), sticky="w")

        self._thumb_dopo = ctk.CTkLabel(dopo_block, text="—",
                                         width=80, height=56,
                                         fg_color=C["entry"], corner_radius=6,
                                         text_color=C["grigio"])
        self._thumb_dopo.grid(row=1, column=0, padx=(8, 4), pady=(0, 4))

        info_r = ctk.CTkFrame(dopo_block, fg_color="transparent")
        info_r.grid(row=1, column=1, sticky="nsew", padx=(0, 6))
        self._lbl_dopo = ctk.CTkLabel(info_r, text="Nessuna foto",
                                       font=F["micro"],
                                       text_color=C["grigio"],
                                       wraplength=160, justify="left",
                                       anchor="nw")
        self._lbl_dopo.pack(anchor="nw")
        ctk.CTkButton(info_r, text="Scegli…",
                      font=F["micro"], height=26, width=76,
                      fg_color=C["dopo"], hover_color="#059669",
                      command=lambda: self._apri_picker("dopo")).pack(
            anchor="sw", pady=(4, 0))

        # ─ Azioni centrali ───────────────────────────────────────────
        actions = ctk.CTkFrame(tb, fg_color="transparent")
        actions.grid(row=0, column=2, padx=6, pady=10, sticky="nsew")
        actions.grid_rowconfigure((0, 1), weight=1)

        # Riga 1: Auto-match + Swap + Salva
        r1 = ctk.CTkFrame(actions, fg_color="transparent")
        r1.pack(fill="x", pady=(0, 4))

        ctk.CTkButton(r1, text="⚡  Auto-match",
                      font=F["sml"], height=30,
                      fg_color="#1a3a6a", hover_color="#1e4a8a",
                      command=self._auto_match).pack(side="left", padx=(0, 4))
        ctk.CTkButton(r1, text="⇄ Scambia",
                      font=F["sml"], height=30,
                      fg_color="transparent", border_width=1,
                      border_color=C["border"],
                      command=self._swap).pack(side="left", padx=(0, 4))
        ctk.CTkButton(r1, text="💾 Salva",
                      font=F["sml"], height=30,
                      fg_color="#1a4a2e", hover_color="#1e5a38",
                      command=self._salva).pack(side="left")

        # Riga 2: Modalità + Zoom
        r2 = ctk.CTkFrame(actions, fg_color="transparent")
        r2.pack(fill="x")

        self._mode_btns: dict = {}
        for label, mode, col in [
            ("⟺ Slider",      MODE_SLIDER,     C["accent"]),
            ("▌▐ Affiancato", MODE_AFFIANCATO, "#6b3fa0"),
            ("◑ Overlay",     MODE_OVERLAY,    "#7a4a1a"),
        ]:
            btn = ctk.CTkButton(r2, text=label,
                                font=F["micro"], height=26, width=90,
                                fg_color=col if mode == self._mode
                                         else C["card2"],
                                hover_color=col,
                                command=lambda m=mode: self._set_mode(m))
            btn.pack(side="left", padx=(0, 3))
            self._mode_btns[mode] = btn

        ctk.CTkButton(r2, text="⊙ Reset zoom",
                      font=F["micro"], height=26,
                      fg_color="transparent", border_width=1,
                      border_color=C["border"],
                      command=lambda: self._ba.reset_zoom()).pack(
            side="left", padx=(8, 0))

        # ─ Slider opacità overlay (nascosto di default) ───────────────
        self._opacity_row = ctk.CTkFrame(tb, fg_color="transparent")
        self._opacity_row.grid(row=1, column=0, columnspan=3,
                               padx=12, pady=(0, 8), sticky="ew")
        self._opacity_row.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(self._opacity_row, text="PRIMA",
                     font=F["micro"], text_color=C["prima"],
                     fg_color="transparent").grid(row=0, column=0, padx=(0, 6))
        self._opacity_slider = ctk.CTkSlider(
            self._opacity_row, from_=0, to=1, number_of_steps=100,
            command=self._on_opacity)
        self._opacity_slider.set(0.5)
        self._opacity_slider.grid(row=0, column=1, sticky="ew")
        ctk.CTkLabel(self._opacity_row, text="DOPO",
                     font=F["micro"], text_color=C["dopo"],
                     fg_color="transparent").grid(row=0, column=2, padx=(6, 0))
        self._opacity_row.grid_remove()   # nascosto

        # ─ Hint tastiera ─────────────────────────────────────────────
        ctk.CTkLabel(tb, text="← →  slider   scroll  zoom   0  reset   S  swap   M  modalità",
                     font=("Segoe UI", 8), text_color=C["grigio"],
                     fg_color="transparent").grid(
            row=2, column=0, columnspan=3, pady=(0, 8))

    def _build_canvas_area(self):
        self._ba = BeforeAfterCanvas(self)
        self._ba.grid(row=1, column=0, sticky="nsew")
        self._ba._swap_callback = self._swap
        self._ba._mode_callback = self._cicla_mode

        # bind frecce solo quando il canvas ha il focus
        self.winfo_toplevel().bind("<Left>",
            lambda e: self._ba.slider_step(-0.05), add="+")
        self.winfo_toplevel().bind("<Right>",
            lambda e: self._ba.slider_step(+0.05), add="+")

    # ── azioni ────────────────────────────────────────────────────────────────

    def _apri_picker(self, lato: str):
        picker = FotoPickerBA(self)
        self.wait_window(picker)
        if picker.row_selezionata is not None:
            r = picker.row_selezionata
            if lato == "prima":
                self._row_prima = r
                self._aggiorna_side("prima", r)
            else:
                self._row_dopo = r
                self._aggiorna_side("dopo", r)
            self._ricarica_canvas()

    def _aggiorna_side(self, lato: str, r):
        """Aggiorna label e thumbnail per un lato."""
        lbl  = self._lbl_prima  if lato == "prima" else self._lbl_dopo
        thumb = self._thumb_prima if lato == "prima" else self._thumb_dopo
        col  = C["prima"] if lato == "prima" else C["dopo"]

        info = (f"{r['cognome']} {r['nome']}\n"
                f"🦷 {r['dente'] or '—'}  {r['fase'] or '—'}\n"
                f"📅 {r['data_scatto'] or '—'}")
        lbl.configure(text=info, text_color=C["chiaro"])

        # Thumbnail asincrona
        def _load_thumb():
            try:
                img = Image.open(db.get_percorso_assoluto(r)).convert("RGB")
                img.thumbnail((80, 56), Image.LANCZOS)
                cti = ctk.CTkImage(light_image=img, dark_image=img, size=img.size)
                self.after(0, lambda: thumb.configure(image=cti, text=""))
            except Exception:
                pass
        threading.Thread(target=_load_thumb, daemon=True).start()

    def _swap(self):
        self._row_prima, self._row_dopo = self._row_dopo, self._row_prima
        for lato, row in [("prima", self._row_prima), ("dopo", self._row_dopo)]:
            if row:
                self._aggiorna_side(lato, row)
            else:
                lbl   = self._lbl_prima  if lato == "prima" else self._lbl_dopo
                thumb = self._thumb_prima if lato == "prima" else self._thumb_dopo
                lbl.configure(text="Nessuna foto", text_color=C["grigio"])
                thumb.configure(image=None, text="—")
        self._ricarica_canvas()

    def _ricarica_canvas(self):
        p = db.get_percorso_assoluto(self._row_prima) if self._row_prima else None
        d = db.get_percorso_assoluto(self._row_dopo)  if self._row_dopo  else None
        self._ba.carica(p, d)

    def _set_mode(self, mode: str):
        self._mode = mode
        self._ba.set_mode(mode)
        # Aggiorna aspetto bottoni
        _cols = {
            MODE_SLIDER:     C["accent"],
            MODE_AFFIANCATO: "#6b3fa0",
            MODE_OVERLAY:    "#7a4a1a",
        }
        for m, btn in self._mode_btns.items():
            btn.configure(fg_color=_cols[m] if m == mode else C["card2"])
        # Mostra/nasconde slider opacità
        if mode == MODE_OVERLAY:
            self._opacity_row.grid()
        else:
            self._opacity_row.grid_remove()

    def _cicla_mode(self):
        modes = [MODE_SLIDER, MODE_AFFIANCATO, MODE_OVERLAY]
        idx   = modes.index(self._mode)
        self._set_mode(modes[(idx + 1) % len(modes)])

    def _on_opacity(self, val):
        self._ba.set_opacity(float(val))

    def _auto_match(self):
        AutoMatchDialog(self, on_match=self._imposta_coppia)

    def _imposta_coppia(self, row_prima, row_dopo):
        self._row_prima = row_prima
        self._row_dopo  = row_dopo
        self._aggiorna_side("prima", row_prima)
        self._aggiorna_side("dopo",  row_dopo)
        self._ricarica_canvas()

    def _salva(self):
        composita = self._ba.get_composite()
        if composita is None:
            return
        path = filedialog.asksaveasfilename(
            title="Salva confronto",
            defaultextension=".jpg",
            filetypes=[("JPEG", "*.jpg"), ("PNG", "*.png")],
            initialfile=f"confronto_{date.today().isoformat()}.jpg",
        )
        if path:
            composita.save(path, quality=92)


# ─────────────────────────────────────────────────────────────────────────────
# FotoPickerBA — dialog selezione foto (redesign)
# ─────────────────────────────────────────────────────────────────────────────

class FotoPickerBA(ctk.CTkToplevel):

    COLS = 4

    def __init__(self, master):
        super().__init__(master)
        self.title("Seleziona Foto per il Confronto")
        self.geometry("860x560")
        self.resizable(True, True)
        self.grab_set()
        self.row_selezionata = None
        self._thumbs: list = []
        self._db_id  = None

        self.after(60, lambda: (
            self.lift(), self.focus_force(),
            self.attributes("-topmost", True),
            self.after(200, lambda: self.attributes("-topmost", False)),
        ))
        self._build_ui()
        self._cerca()  # mostra tutte le foto all'apertura

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # ── Barra filtri ──────────────────────────────────────────────
        top = ctk.CTkFrame(self, fg_color=C["card"], corner_radius=10)
        top.grid(row=0, column=0, padx=10, pady=(10, 6), sticky="ew")
        top.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(top, text="🔍", font=("Segoe UI", 14),
                     text_color=C["grigio"],
                     fg_color="transparent").grid(
            row=0, column=0, padx=(12, 4), pady=12)

        self._entry = ctk.CTkEntry(top, font=F["nrm"], height=36,
                                   placeholder_text="Cerca per cognome paziente…",
                                   fg_color=C["entry"], border_color=C["border"])
        self._entry.grid(row=0, column=1, sticky="ew", padx=(0, 8), pady=10)
        self._entry.bind("<KeyRelease>", self._debounce)
        self._entry.bind("<Return>",     lambda e: self._cerca())
        self._entry.focus_set()

        self._combo_fase = ctk.CTkComboBox(
            top, values=["(tutte le fasi)"] + db.FASI,
            font=F["nrm"], height=36, width=160, state="readonly",
            command=lambda v: self._cerca())
        self._combo_fase.set("(tutte le fasi)")
        self._combo_fase.grid(row=0, column=2, padx=(0, 8), pady=10)

        self._combo_branca = ctk.CTkComboBox(
            top, values=["(tutte le branche)"] + db.BRANCHE,
            font=F["nrm"], height=36, width=170, state="readonly",
            command=lambda v: self._cerca())
        self._combo_branca.set("(tutte le branche)")
        self._combo_branca.grid(row=0, column=3, padx=(0, 12), pady=10)

        self._lbl_count = ctk.CTkLabel(top, text="",
                                        font=F["micro"], text_color=C["grigio"],
                                        fg_color="transparent")
        self._lbl_count.grid(row=1, column=0, columnspan=4, padx=12, pady=(0, 8), sticky="w")

        # ── Galleria ──────────────────────────────────────────────────
        self._scroll = ctk.CTkScrollableFrame(self, fg_color=C["card"],
                                               corner_radius=10)
        self._scroll.grid(row=1, column=0, padx=10, pady=(0, 10), sticky="nsew")
        for c in range(self.COLS):
            self._scroll.grid_columnconfigure(c, weight=1)

    def _debounce(self, event=None):
        if self._db_id:
            try:
                self.after_cancel(self._db_id)
            except Exception:
                pass
        self._db_id = self.after(300, self._cerca)

    def _cerca(self):
        testo  = self._entry.get().strip()
        fase_v = self._combo_fase.get()
        brnc_v = self._combo_branca.get()
        fase   = None if fase_v.startswith("(") else fase_v
        branca = None if brnc_v.startswith("(") else brnc_v

        pazienti = db.cerca_pazienti(testo) if testo else []
        paz_id   = pazienti[0]["id"] if len(pazienti) == 1 else None

        righe = list(db.cerca_foto(paziente_id=paz_id, fase=fase, branca=branca))

        # Filtro per cognome se query ma non singolo paziente
        if testo and not paz_id:
            tl = testo.lower()
            righe = [r for r in righe
                     if tl in (r["cognome"] or "").lower()
                     or tl in (r["nome"] or "").lower()]

        self._lbl_count.configure(text=f"{len(righe)} foto trovate")
        self._riempie(righe)

    def _riempie(self, righe: list):
        for w in self._scroll.winfo_children():
            w.destroy()
        self._thumbs.clear()

        if not righe:
            ctk.CTkLabel(self._scroll, text="Nessuna foto trovata.",
                         font=F["sml"], text_color=C["grigio"]).grid(
                row=0, column=0, columnspan=self.COLS, pady=40)
            return

        for idx, r in enumerate(righe):
            row, col = divmod(idx, self.COLS)
            self._card(row, col, r)

    def _card(self, row: int, col: int, r):
        fase_col = {
            "Pre-op":   C["prima"],
            "Post-op":  C["dopo"],
            "Intra-op": "#f59e0b",
        }.get(r["fase"] or "", C["grigio"])

        card = ctk.CTkFrame(self._scroll, fg_color=C["entry"],
                            corner_radius=8, cursor="hand2")
        card.grid(row=row, column=col, padx=5, pady=5, sticky="nsew")
        card.grid_columnconfigure(0, weight=1)

        # Thumbnail
        ph = Image.new("RGB", (130, 96), (20, 28, 50))
        th = ctk.CTkImage(light_image=ph, dark_image=ph, size=(130, 96))
        self._thumbs.append(th)
        lbl_img = ctk.CTkLabel(card, image=th, text="", cursor="hand2")
        lbl_img.grid(row=0, column=0, padx=4, pady=(6, 3), sticky="ew")

        # Carica thumbnail reale in background
        def _load_th(rr=r, lbl=lbl_img):
            try:
                img = Image.open(db.get_percorso_assoluto(rr)).convert("RGB")
                img.thumbnail((130, 96), Image.LANCZOS)
                cti = ctk.CTkImage(light_image=img, dark_image=img, size=img.size)
                self._thumbs.append(cti)
                self.after(0, lambda: lbl.configure(image=cti))
            except Exception:
                pass
        threading.Thread(target=_load_th, daemon=True).start()

        # Badge fase
        ctk.CTkLabel(card, text=r["fase"] or "—",
                     font=F["badge"], text_color=fase_col,
                     fg_color="transparent").grid(row=1, column=0, pady=(0, 1))

        # Info paziente
        ctk.CTkLabel(card,
                     text=f"{r['cognome']} {r['nome']}",
                     font=("Segoe UI", 9, "bold"),
                     text_color=C["chiaro"],
                     fg_color="transparent").grid(row=2, column=0)

        ctk.CTkLabel(card,
                     text=f"🦷 {r['dente'] or '—'}  📅 {r['data_scatto'] or '—'}",
                     font=F["micro"], text_color=C["grigio"],
                     fg_color="transparent").grid(row=3, column=0, pady=(0, 6))

        # Hover + click
        for w in [card, lbl_img]:
            w.bind("<Button-1>", lambda e, rr=r: self._seleziona(rr))
            w.bind("<Enter>",    lambda e, f=card: f.configure(fg_color=C["accent"]))
            w.bind("<Leave>",    lambda e, f=card: f.configure(fg_color=C["entry"]))

    def _seleziona(self, r):
        self.row_selezionata = r
        self.destroy()


# ─────────────────────────────────────────────────────────────────────────────
# AutoMatchDialog
# ─────────────────────────────────────────────────────────────────────────────

class AutoMatchDialog(ctk.CTkToplevel):

    def __init__(self, master, on_match):
        super().__init__(master)
        self.title("Auto-match Pre-op / Post-op")
        self.geometry("700x480")
        self.resizable(True, True)
        self.grab_set()
        self._on_match = on_match
        self._thumbs:  list = []

        self.after(60, lambda: (
            self.lift(), self.focus_force(),
            self.attributes("-topmost", True),
            self.after(200, lambda: self.attributes("-topmost", False)),
        ))
        self._build_ui()
        self._cerca_coppie()

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        header = ctk.CTkFrame(self, fg_color=C["card"], corner_radius=10)
        header.grid(row=0, column=0, padx=10, pady=(10, 6), sticky="ew")
        ctk.CTkLabel(header, text="⚡  Coppie Pre-op / Post-op trovate automaticamente",
                     font=F["sez"], fg_color="transparent").pack(
            side="left", padx=14, pady=12)
        self._lbl_n = ctk.CTkLabel(header, text="",
                                    font=F["micro"], text_color=C["grigio"],
                                    fg_color="transparent")
        self._lbl_n.pack(side="right", padx=14)

        self._scroll = ctk.CTkScrollableFrame(self, fg_color=C["card"],
                                               corner_radius=10)
        self._scroll.grid(row=1, column=0, padx=10, pady=(0, 10), sticky="nsew")
        self._scroll.grid_columnconfigure(0, weight=1)

    def _cerca_coppie(self):
        pre  = list(db.cerca_foto(fase="Pre-op"))
        post = list(db.cerca_foto(fase="Post-op"))

        idx: dict = {}
        for r in post:
            k = (r["paziente_id"], r["dente"] or "", r["branca"] or "")
            idx.setdefault(k, []).append(r)

        coppie = []
        for r_pre in pre:
            k = (r_pre["paziente_id"], r_pre["dente"] or "", r_pre["branca"] or "")
            if k in idx:
                r_post = sorted(idx[k],
                                key=lambda x: x["data_scatto"] or "",
                                reverse=True)[0]
                coppie.append((r_pre, r_post))

        self._lbl_n.configure(text=f"{len(coppie)} copp{'ia' if len(coppie)==1 else 'ie'}")
        self._riempie(coppie)

    def _riempie(self, coppie):
        for w in self._scroll.winfo_children():
            w.destroy()
        self._thumbs.clear()

        if not coppie:
            ctk.CTkLabel(self._scroll,
                         text="Nessuna coppia Pre-op / Post-op trovata.\n"
                              "Assicurati di aver taggato le foto con la fase corretta.",
                         font=F["sml"], text_color=C["grigio"],
                         justify="center").grid(row=0, column=0, pady=40)
            return

        for i, (pre, post) in enumerate(coppie):
            self._riga(i, pre, post)

    def _riga(self, idx, pre, post):
        riga = ctk.CTkFrame(self._scroll, fg_color=C["card2"], corner_radius=8)
        riga.grid(row=idx, column=0, padx=6, pady=4, sticky="ew")
        riga.grid_columnconfigure(2, weight=1)

        # Thumb PRE
        ph = Image.new("RGB", (80, 60), (20, 28, 50))
        th_p = ctk.CTkImage(light_image=ph, dark_image=ph, size=(80, 60))
        self._thumbs.append(th_p)
        lbl_p = ctk.CTkLabel(riga, image=th_p, text="",
                              fg_color=C["entry"], corner_radius=6)
        lbl_p.grid(row=0, column=0, rowspan=2, padx=(10, 4), pady=8)

        # Thumb POST
        th_d = ctk.CTkImage(light_image=ph, dark_image=ph, size=(80, 60))
        self._thumbs.append(th_d)
        lbl_d = ctk.CTkLabel(riga, image=th_d, text="",
                              fg_color=C["entry"], corner_radius=6)
        lbl_d.grid(row=0, column=1, rowspan=2, padx=(0, 8), pady=8)

        # Carica thumbnails
        for rr, lbl in [(pre, lbl_p), (post, lbl_d)]:
            def _th(r=rr, l=lbl):
                try:
                    img = Image.open(db.get_percorso_assoluto(r)).convert("RGB")
                    img.thumbnail((80, 60), Image.LANCZOS)
                    cti = ctk.CTkImage(light_image=img, dark_image=img, size=img.size)
                    self._thumbs.append(cti)
                    self.after(0, lambda ll=l, c=cti: ll.configure(image=c))
                except Exception:
                    pass
            threading.Thread(target=_th, daemon=True).start()

        # Info
        info_txt = (f"{pre['cognome']} {pre['nome']}  ·  "
                    f"🦷 {pre['dente'] or '—'}  ·  🏥 {pre['branca'] or '—'}")
        ctk.CTkLabel(riga, text=info_txt,
                     font=F["nrm"], anchor="w",
                     fg_color="transparent").grid(
            row=0, column=2, sticky="ew", padx=4, pady=(8, 2))

        date_txt = (f"Pre-op: {pre['data_scatto'] or '—'}   →   "
                    f"Post-op: {post['data_scatto'] or '—'}")
        ctk.CTkLabel(riga, text=date_txt,
                     font=F["micro"], text_color=C["grigio"],
                     anchor="w", fg_color="transparent").grid(
            row=1, column=2, sticky="ew", padx=4, pady=(0, 8))

        ctk.CTkButton(riga, text="Confronta →",
                      font=F["sml"], width=110, height=34,
                      fg_color=C["accent"], hover_color=C["accent_h"],
                      command=lambda p=pre, d=post: self._usa(p, d)).grid(
            row=0, column=3, rowspan=2, padx=(0, 10))

    def _usa(self, pre, post):
        self._on_match(pre, post)
        self.destroy()


__all__ = ["BeforeAfterFrame"]

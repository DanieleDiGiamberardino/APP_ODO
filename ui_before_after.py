import tkinter as tk
import customtkinter as ctk
from PIL import Image, ImageTk
import database as db

class _ViewState:
    def __init__(self):
        self.scale: float = 1.0     
        self.offset_x: float = 0.0  
        self.offset_y: float = 0.0

    def reset(self):
        self.scale = 1.0
        self.offset_x = 0.0
        self.offset_y = 0.0

class _ImageCanvas(tk.Canvas):
    SCALE_MIN = 0.02
    SCALE_MAX = 64.0

    def __init__(self, master, label_text: str = "", **kwargs):
        kwargs.setdefault("bg", "#080c18")
        kwargs.setdefault("highlightthickness", 0)
        kwargs.setdefault("cursor", "fleur")
        super().__init__(master, **kwargs)

        self._label_text = label_text
        self._sync_peer: "_ImageCanvas | None" = None
        self._sync_enabled: bool = False

        self._pil_img: Image.Image | None = None
        self._tk_img: ImageTk.PhotoImage | None = None  

        self._state = _ViewState()
        self._pan_last_x = 0
        self._pan_last_y = 0
        self._panning = False
        self._render_pending = False

        self._bind_events()

    def load_image(self, path: str):
        try:
            self._pil_img = Image.open(path).convert("RGB")
        except Exception:
            self._pil_img = Image.new("RGB", (800, 600), "#111928")
        self._state.reset()
        self._schedule_render()

    def set_peer(self, peer: "_ImageCanvas"):
        self._sync_peer = peer

    def set_sync(self, enabled: bool):
        self._sync_enabled = enabled

    def reset_view(self):
        self._state.reset()
        self._schedule_render()

    def apply_delta_zoom(self, factor: float, cursor_x: float, cursor_y: float):
        cw = self.winfo_width()
        ch = self.winfo_height()
        mx = cursor_x - cw / 2
        my = cursor_y - ch / 2
        new_s = self._state.scale * factor
        if not (self.SCALE_MIN <= new_s <= self.SCALE_MAX): return
        self._state.offset_x = mx + (self._state.offset_x - mx) * factor
        self._state.offset_y = my + (self._state.offset_y - my) * factor
        self._state.scale = new_s
        self._schedule_render()

    def apply_delta_pan(self, dx: float, dy: float):
        self._state.offset_x += dx
        self._state.offset_y += dy
        self._schedule_render()

    def _bind_events(self):
        self.bind("<ButtonPress-1>",   self._pan_start)
        self.bind("<B1-Motion>",       self._pan_move)
        self.bind("<ButtonRelease-1>", self._pan_end)
        self.bind("<MouseWheel>",      self._on_wheel)
        self.bind("<Button-4>",        self._on_wheel)
        self.bind("<Button-5>",        self._on_wheel)
        self.bind("<Configure>",       lambda e: self._schedule_render())

    def _pan_start(self, event):
        self._panning = True
        self._pan_last_x = event.x
        self._pan_last_y = event.y

    def _pan_move(self, event):
        if not self._panning: return
        dx = event.x - self._pan_last_x
        dy = event.y - self._pan_last_y
        self._pan_last_x = event.x
        self._pan_last_y = event.y
        self._state.offset_x += dx
        self._state.offset_y += dy
        if self._sync_enabled and self._sync_peer:
            self._sync_peer.apply_delta_pan(dx, dy)
        self._schedule_render()

    def _pan_end(self, event):
        self._panning = False

    def _on_wheel(self, event):
        if   event.num == 4:     delta = 1
        elif event.num == 5:     delta = -1
        else:                    delta = 1 if event.delta > 0 else -1

        factor = 1.13 if delta > 0 else 1 / 1.13
        new_s  = self._state.scale * factor
        if not (self.SCALE_MIN <= new_s <= self.SCALE_MAX): return

        cw = self.winfo_width()
        ch = self.winfo_height()
        mx = event.x - cw / 2
        my = event.y - ch / 2

        self._state.offset_x = mx + (self._state.offset_x - mx) * factor
        self._state.offset_y = my + (self._state.offset_y - my) * factor
        self._state.scale = new_s

        if self._sync_enabled and self._sync_peer:
            pcw = self._sync_peer.winfo_width()
            pch = self._sync_peer.winfo_height()
            self._sync_peer.apply_delta_zoom(factor, pcw / 2 + mx, pch / 2 + my)

        self._schedule_render()

    def _schedule_render(self):
        if not self._render_pending:
            self._render_pending = True
            self.after_idle(self._render)

    def _render(self):
        self._render_pending = False
        cw = self.winfo_width()
        ch = self.winfo_height()
        if cw < 2 or ch < 2: return

        self.delete("all")
        self._draw_watermark(cw, ch)

        if self._pil_img is None:
            self._draw_placeholder(cw, ch)
            return

        img_w, img_h = self._pil_img.size
        base = min(cw / img_w, ch / img_h)
        s = base * self._state.scale          

        # MATEMATICA CORRETTA (Centrata)
        cx = cw / 2 + self._state.offset_x
        cy = ch / 2 + self._state.offset_y

        left = (0 - cx) / s + img_w / 2
        top = (0 - cy) / s + img_h / 2
        right = (cw - cx) / s + img_w / 2
        bottom = (ch - cy) / s + img_h / 2

        crop_left = max(0, int(left))
        crop_top = max(0, int(top))
        crop_right = min(img_w, int(right))
        crop_bottom = min(img_h, int(bottom))

        if crop_right <= crop_left or crop_bottom <= crop_top: return

        fragment = self._pil_img.crop((crop_left, crop_top, crop_right, crop_bottom))
        disp_w = max(1, int((crop_right - crop_left) * s))
        disp_h = max(1, int((crop_bottom - crop_top) * s))

        resized = fragment.resize((disp_w, disp_h), Image.BILINEAR)
        self._tk_img = ImageTk.PhotoImage(resized)   

        draw_x = (crop_left - img_w / 2) * s + cx
        draw_y = (crop_top - img_h / 2) * s + cy

        self.create_image(draw_x, draw_y, image=self._tk_img, anchor="nw", tags="img")
        self._draw_watermark(cw, ch)  

    def _draw_placeholder(self, cw: int, ch: int):
        self.create_rectangle(0, 0, cw, ch, fill="#080c18", outline="")
        self.create_text(cw // 2, ch // 2, text="Nessuna immagine caricata", fill="#1e3050", font=("Segoe UI", 13))

    def _draw_watermark(self, cw: int, ch: int):
        if not self._label_text: return
        pad = 10; tw = 76; th = 22
        self.create_rectangle(pad, pad, pad + tw, pad + th, fill="#06101e", outline="", stipple="gray50")
        self.create_text(pad + tw // 2, pad + th // 2, text=self._label_text, fill="#5090c0", font=("Segoe UI", 10, "bold"))


class _PazientePopup(ctk.CTkToplevel):
    def __init__(self, master, on_select):
        super().__init__(master)
        self.title("Seleziona Paziente")
        self.configure(fg_color="#0f1629")
        self.geometry("540x500")
        self.resizable(False, True)
        self.grab_set()
        self.focus_force()
        self._on_select = on_select
        self._build()
        self._search("")

    def _build(self):
        top = ctk.CTkFrame(self, fg_color="#080c18", corner_radius=0, height=54)
        top.pack(fill="x")
        top.pack_propagate(False)
        self._entry = ctk.CTkEntry(top, placeholder_text="🔍  Cerca per nome, cognome o ID…", fg_color="#0f1629", border_color="#0f3460", text_color="white", font=ctk.CTkFont("Segoe UI", 12), height=34)
        self._entry.pack(fill="x", padx=12, pady=10)
        self._entry.bind("<KeyRelease>", lambda e: self._search(self._entry.get()))
        self._scroll = ctk.CTkScrollableFrame(self, fg_color="#0f1629", scrollbar_button_color="#0f3460", scrollbar_button_hover_color="#1a4a80")
        self._scroll.pack(fill="both", expand=True, padx=4, pady=4)

    def _search(self, q: str):
        try: rows = db.cerca_pazienti(q)
        except Exception: rows = []
        for w in self._scroll.winfo_children(): w.destroy()
        if not rows:
            ctk.CTkLabel(self._scroll, text="Nessun risultato.", text_color="#304060", font=ctk.CTkFont("Segoe UI", 12)).pack(pady=20)
            return
        for paz in rows:
            row = ctk.CTkFrame(self._scroll, fg_color="#111e38", corner_radius=6, height=40)
            row.pack(fill="x", padx=4, pady=2)
            row.pack_propagate(False)
            ctk.CTkLabel(row, text=f"{paz.get('cognome','')} {paz.get('nome','')} | ID: {paz.get('id','—')}", text_color="#c0d4f0", font=ctk.CTkFont("Segoe UI", 12), anchor="w").pack(side="left", padx=10, fill="y")
            ctk.CTkButton(row, text="Seleziona", width=80, height=28, fg_color="#0f3460", hover_color="#1a4a80", text_color="white", font=ctk.CTkFont("Segoe UI", 11), command=lambda p=paz: (self._on_select(p), self.destroy())).pack(side="right", padx=8, pady=6)


class _FotoPopup(ctk.CTkToplevel):
    THUMB = (96, 72)
    COLS  = 4

    def __init__(self, master, paziente_id, titolo: str, on_select):
        super().__init__(master)
        self.title(titolo)
        self.configure(fg_color="#0f1629")
        self.geometry("700x540")
        self.resizable(True, True)
        self.grab_set()
        self.focus_force()
        self._pid = paziente_id
        self._on_select = on_select
        self._refs: list[ImageTk.PhotoImage] = []  
        self._build()
        self._load()

    def _build(self):
        hdr = ctk.CTkFrame(self, fg_color="#080c18", corner_radius=0, height=42)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        ctk.CTkLabel(hdr, text=f"Fotografie  –  Paziente ID {self._pid}", text_color="#80a8d0", font=ctk.CTkFont("Segoe UI", 12, "bold"), anchor="w").pack(side="left", padx=14, fill="y")
        self._scroll = ctk.CTkScrollableFrame(self, fg_color="#0f1629", scrollbar_button_color="#0f3460")
        self._scroll.pack(fill="both", expand=True, padx=4, pady=4)

    def _load(self):
        try: foto_list = db.cerca_foto(paziente_id=self._pid)
        except Exception: foto_list = []
        self._refs.clear()
        for w in self._scroll.winfo_children(): w.destroy()
        if not foto_list:
            ctk.CTkLabel(self._scroll, text="Nessuna foto.", text_color="#304060", font=ctk.CTkFont("Segoe UI", 12)).pack(pady=24)
            return

        for i, foto in enumerate(foto_list):
            r, c = divmod(i, self.COLS)
            self._scroll.grid_columnconfigure(c, weight=1)
            card = ctk.CTkFrame(self._scroll, fg_color="#111e38", corner_radius=8)
            card.grid(row=r, column=c, padx=6, pady=6, sticky="nsew")

            # PERCORSO ASSOLUTO FIX
            path_assoluto = db.get_percorso_assoluto(foto)
            tk_thumb = self._make_thumb(path_assoluto)
            self._refs.append(tk_thumb)

            tk.Label(card, image=tk_thumb, bg="#111e38", cursor="hand2").pack(padx=4, pady=(6, 2))
            ctk.CTkButton(card, text="Usa", height=26, fg_color="#0f3460", hover_color="#1a4a80", text_color="white", font=ctk.CTkFont("Segoe UI", 10, "bold"), command=lambda f=foto: (self._on_select(f), self.destroy())).pack(padx=8, pady=(4, 8), fill="x")

    def _make_thumb(self, path) -> ImageTk.PhotoImage:
        try:
            img = Image.open(path).convert("RGB")
            img.thumbnail(self.THUMB, Image.BILINEAR)
        except Exception:
            img = Image.new("RGB", self.THUMB, "#1a2040")
        return ImageTk.PhotoImage(img)


class BeforeAfterFrame(ctk.CTkFrame):
    def __init__(self, master, **kwargs):
        kwargs.setdefault("fg_color", "#080c18")
        kwargs.setdefault("corner_radius", 0)
        super().__init__(master, **kwargs)
        self._paziente: dict | None = None
        self._sync_var = tk.BooleanVar(value=False)
        self._build_toolbar()
        self._build_canvas_area()
        self._update_zoom_labels()

    def _build_toolbar(self):
        bar = ctk.CTkFrame(self, fg_color="#0f1629", corner_radius=0, height=52)
        bar.pack(fill="x", side="top")
        bar.pack_propagate(False)
        _b = dict(height=34, corner_radius=7, font=ctk.CTkFont("Segoe UI", 12))

        ctk.CTkButton(bar, text="👤  Seleziona Paziente", fg_color="#0f3460", hover_color="#1a4a80", text_color="white", command=self._open_paziente_popup, **_b).pack(side="left", padx=(12, 8), pady=9)
        self._lbl_paz = ctk.CTkLabel(bar, text="Nessun paziente selezionato", text_color="#304860", font=ctk.CTkFont("Segoe UI", 11))
        self._lbl_paz.pack(side="left", padx=4)

        self._btn_after = ctk.CTkButton(bar, text="🖼  Seleziona After", fg_color="#162040", hover_color="#1e3060", text_color="#5080a0", state="disabled", command=lambda: self._open_foto_popup("after"), **_b)
        self._btn_after.pack(side="right", padx=(6, 12), pady=9)
        self._btn_before = ctk.CTkButton(bar, text="🖼  Seleziona Before", fg_color="#162040", hover_color="#1e3060", text_color="#5080a0", state="disabled", command=lambda: self._open_foto_popup("before"), **_b)
        self._btn_before.pack(side="right", padx=6, pady=9)

    def _build_canvas_area(self):
        area = ctk.CTkFrame(self, fg_color="#080c18", corner_radius=0)
        area.pack(fill="both", expand=True, side="top")
        area.grid_rowconfigure(0, weight=1)
        area.grid_columnconfigure(0, weight=1)
        area.grid_columnconfigure(2, weight=1)

        self._canvas_before = _ImageCanvas(area, label_text="BEFORE")
        self._canvas_before.grid(row=0, column=0, sticky="nsew")
        tk.Frame(area, bg="#0f3460", width=2).grid(row=0, column=1, sticky="ns")
        self._canvas_after = _ImageCanvas(area, label_text="AFTER")
        self._canvas_after.grid(row=0, column=2, sticky="nsew")

        self._canvas_before.set_peer(self._canvas_after)
        self._canvas_after.set_peer(self._canvas_before)
        self._build_bottom_bar(area)

    def _build_bottom_bar(self, parent):
        bar = ctk.CTkFrame(parent, fg_color="#0a1020", corner_radius=0, height=44)
        bar.grid(row=1, column=0, columnspan=3, sticky="ew")
        bar.pack_propagate(False)
        bar.grid_columnconfigure((0, 1, 2, 3, 4), weight=1)
        _rb = dict(width=110, height=28, fg_color="#111e38", hover_color="#1a2a4a", text_color="#6080a0", font=ctk.CTkFont("Segoe UI", 11))

        ctk.CTkButton(bar, text="↺  Reset Before", command=self._canvas_before.reset_view, **_rb).grid(row=0, column=0, padx=12, pady=8, sticky="w")
        self._lbl_zoom_b = ctk.CTkLabel(bar, text="100%", text_color="#304060", font=ctk.CTkFont("Segoe UI", 10, "bold"))
        self._lbl_zoom_b.grid(row=0, column=1)

        ctk.CTkCheckBox(bar, text="🔒  Sincronizza Viste", variable=self._sync_var, onvalue=True, offvalue=False, fg_color="#0f3460", hover_color="#1a4a80", checkmark_color="white", text_color="#80b0d8", font=ctk.CTkFont("Segoe UI", 12, "bold"), command=self._on_sync_toggle).grid(row=0, column=2)

        self._lbl_zoom_a = ctk.CTkLabel(bar, text="100%", text_color="#304060", font=ctk.CTkFont("Segoe UI", 10, "bold"))
        self._lbl_zoom_a.grid(row=0, column=3)
        ctk.CTkButton(bar, text="↺  Reset After", command=self._canvas_after.reset_view, **_rb).grid(row=0, column=4, padx=12, pady=8, sticky="e")

    def _open_paziente_popup(self):
        _PazientePopup(self, on_select=self._on_paziente_selected)

    def _on_paziente_selected(self, paz: dict):
        self._paziente = paz
        self._lbl_paz.configure(text=f"👤  {paz.get('cognome', '')} {paz.get('nome', '')}  (ID: {paz.get('id', '—')})", text_color="#80b0d8")
        self._btn_before.configure(state="normal", text_color="#c0d8f0")
        self._btn_after.configure(state="normal",  text_color="#c0d8f0")

    def _open_foto_popup(self, slot: str):
        if not self._paziente: return
        _FotoPopup(self, paziente_id=self._paziente.get("id"), titolo="Seleziona foto BEFORE" if slot == "before" else "Seleziona foto AFTER", on_select=lambda f: self._on_foto_selected(slot, f))

    def _on_foto_selected(self, slot: str, foto: dict):
        # PERCORSO ASSOLUTO FIX
        path = db.get_percorso_assoluto(foto)
        if slot == "before": self._canvas_before.load_image(path)
        else: self._canvas_after.load_image(path)

    def _on_sync_toggle(self):
        enabled = self._sync_var.get()
        self._canvas_before.set_sync(enabled)
        self._canvas_after.set_sync(enabled)

    def _update_zoom_labels(self):
        self._lbl_zoom_b.configure(text=f"{int(self._canvas_before._state.scale * 100)}%")
        self._lbl_zoom_a.configure(text=f"{int(self._canvas_after._state.scale  * 100)}%")
        self.after(200, self._update_zoom_labels)
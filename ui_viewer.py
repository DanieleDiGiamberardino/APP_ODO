import tkinter as tk
import customtkinter as ctk
from PIL import Image, ImageTk
import database as db 


class ViewerFoto(ctk.CTkToplevel):
    def __init__(self, master, risultati: list[dict], indice_iniziale: int):
        super().__init__(master)
        self.risultati = risultati
        self.indice = indice_iniziale

        self.title("Visualizzatore Immagini")
        self.configure(fg_color="#080c18")
        self.attributes("-fullscreen", False)

        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        w = int(sw * 0.92)
        h = int(sh * 0.92)
        x = (sw - w) // 2
        y = (sh - h) // 2
        self.geometry(f"{w}x{h}+{x}+{y}")
        self.resizable(True, True)

        self.grab_set()
        self.focus_force()

        # Stato zoom/pan
        self._scale = 1.0
        self._offset_x = 0.0
        self._offset_y = 0.0
        self._pan_start_x = 0
        self._pan_start_y = 0
        self._panning = False

        # Immagine PIL originale e PhotoImage reference
        self._pil_img: Image.Image | None = None
        self._tk_img: ImageTk.PhotoImage | None = None

        self._build_ui()
        self._load_image()
        self._bind_events()

    # ------------------------------------------------------------------ UI --
    def _build_ui(self):
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # Canvas principale
        self.canvas = tk.Canvas(
            self,
            bg="#080c18",
            highlightthickness=0,
            cursor="fleur",
        )
        self.canvas.grid(row=0, column=0, sticky="nsew")

        # Overlay metadati (frame semitrasparente simulato con Canvas rettangolo)
        self._overlay_frame = tk.Frame(self, bg="#0f1629")
        self._overlay_frame.grid(row=0, column=0, sticky="sew")
        self._overlay_frame.configure(height=64)
        self._overlay_frame.grid_propagate(False)

        self._meta_label = tk.Label(
            self._overlay_frame,
            text="",
            fg="#c8d8f0",
            bg="#0f1629",
            font=("Segoe UI", 11),
            anchor="w",
            padx=16,
        )
        self._meta_label.pack(side="left", fill="both", expand=True)

        # Pulsanti navigazione
        btn_cfg = dict(bg="#0f1629", fg="#c8d8f0", font=("Segoe UI", 22, "bold"),
                       relief="flat", activebackground="#0f3460", activeforeground="white",
                       cursor="hand2", bd=0, padx=12, pady=4)

        self._btn_prev = tk.Button(self._overlay_frame, text="◀", command=self._prev, **btn_cfg)
        self._btn_prev.pack(side="right", padx=4)

        self._btn_next = tk.Button(self._overlay_frame, text="▶", command=self._next, **btn_cfg)
        self._btn_next.pack(side="right", padx=4)

        self._counter_label = tk.Label(
            self._overlay_frame,
            text="",
            fg="#7090b0",
            bg="#0f1629",
            font=("Segoe UI", 10),
            padx=8,
        )
        self._counter_label.pack(side="right")

        btn_close = tk.Button(
            self._overlay_frame,
            text="✕",
            command=self.destroy,
            bg="#0f1629", fg="#c83060",
            font=("Segoe UI", 14, "bold"),
            relief="flat", activebackground="#3a0a18", activeforeground="#ff4070",
            cursor="hand2", bd=0, padx=10, pady=4,
        )
        btn_close.pack(side="right", padx=8)

        btn_reset = tk.Button(
            self._overlay_frame,
            text="⊙",
            command=self._reset_view,
            bg="#0f1629", fg="#50a0d0",
            font=("Segoe UI", 16),
            relief="flat", activebackground="#0f3460", activeforeground="white",
            cursor="hand2", bd=0, padx=8, pady=4,
        )
        btn_reset.pack(side="right", padx=2)

    # ---------------------------------------------------------- Bindings --
    def _bind_events(self):
        self.bind("<Left>", lambda e: self._prev())
        self.bind("<Right>", lambda e: self._next())
        self.bind("<Escape>", lambda e: self.destroy())

        self.canvas.bind("<ButtonPress-1>", self._pan_start)
        self.canvas.bind("<B1-Motion>", self._pan_move)
        self.canvas.bind("<ButtonRelease-1>", self._pan_end)

        # Zoom con rotella – Windows/Linux
        self.canvas.bind("<MouseWheel>", self._on_mousewheel)
        # Linux (Button-4/5)
        self.canvas.bind("<Button-4>", self._on_mousewheel)
        self.canvas.bind("<Button-5>", self._on_mousewheel)

        self.canvas.bind("<Configure>", self._on_resize)

    # ------------------------------------------------------- Navigation --
    def _prev(self):
        if self.risultati:
            self.indice = (self.indice - 1) % len(self.risultati)
            self._load_image()

    def _next(self):
        if self.risultati:
            self.indice = (self.indice + 1) % len(self.risultati)
            self._load_image()

# -------------------------------------------------------- Load image --
    def _load_image(self):
        if not self.risultati:
            return
        item = self.risultati[self.indice]
        
        # Usa la funzione del DB per ottenere il percorso assoluto corretto
        path = db.get_percorso_assoluto(item)
        
        try:
            self._pil_img = Image.open(path)
        except Exception as e:
            print(f"Errore caricamento immagine: {e}") # Utile per debug
            self._pil_img = Image.new("RGB", (800, 600), "#1a2040")

        self._reset_view(render=False)
        self._render()
        self._update_meta(item)

    # --------------------------------------------------------- Metadata --
    def _update_meta(self, item: dict):
        dente = item.get("dente", "—")
        fase = item.get("fase", "—")
        data = item.get("data_scatto", "—")
        id_ = item.get("id", "—")
        text = f"  ID: {id_}   |   Dente: {dente}   |   Fase: {fase}   |   Data: {data}"
        self._meta_label.configure(text=text)
        self._counter_label.configure(
            text=f"{self.indice + 1} / {len(self.risultati)}"
        )

    # -------------------------------------------------------- Reset view --
    def _reset_view(self, render=True):
        self._scale = 1.0
        self._offset_x = 0.0
        self._offset_y = 0.0
        if render:
            self._render()

    # ----------------------------------------------------------- Render --
    # ----------------------------------------------------------- Render --
    def _render(self):
        if self._pil_img is None:
            return
            
        cw = self.canvas.winfo_width() or 1
        ch = self.canvas.winfo_height() or 1

        img_w, img_h = self._pil_img.size

        # Fit-to-canvas base scale
        base_scale = min(cw / img_w, ch / img_h)
        display_scale = base_scale * self._scale

        # Centro dell'immagine sul canvas
        cx = cw / 2 + self._offset_x
        cy = ch / 2 + self._offset_y

        # --- SMART CROPPING (Addio Lag!) ---
        # Calcoliamo quale porzione dell'immagine originale è attualmente visibile nello schermo.
        left = (0 - cx) / display_scale + img_w / 2
        top = (0 - cy) / display_scale + img_h / 2
        right = (cw - cx) / display_scale + img_w / 2
        bottom = (ch - cy) / display_scale + img_h / 2

        # Assicuriamoci di non ritagliare fuori dai bordi reali dell'immagine
        crop_left = max(0, int(left))
        crop_top = max(0, int(top))
        crop_right = min(img_w, int(right))
        crop_bottom = min(img_h, int(bottom))

        self.canvas.delete("img")

        # Se l'immagine è stata trascinata completamente fuori dallo schermo, non disegniamo nulla
        if crop_right <= crop_left or crop_bottom <= crop_top:
            return

        # 1. Ritagliamo SOLO il pezzo di immagine originale che l'utente sta effettivamente guardando
        cropped = self._pil_img.crop((crop_left, crop_top, crop_right, crop_bottom))

        # 2. Calcoliamo quanto deve essere grande questo frammento sul monitor
        target_w = max(1, int((crop_right - crop_left) * display_scale))
        target_h = max(1, int((crop_bottom - crop_top) * display_scale))

        # 3. Ridimensioniamo solo questo piccolo frammento. 
        # Usiamo BILINEAR invece di LANCZOS: la differenza a occhio è nulla, ma è infinitamente più veloce.
        resized = cropped.resize((target_w, target_h), Image.BILINEAR)
        self._tk_img = ImageTk.PhotoImage(resized)

        # 4. Posizioniamo il frammento sul canvas (partendo dall'angolo in alto a sinistra)
        draw_x = (crop_left - img_w / 2) * display_scale + cx
        draw_y = (crop_top - img_h / 2) * display_scale + cy

        self.canvas.create_image(draw_x, draw_y, image=self._tk_img, anchor="nw", tags="img")

    # ------------------------------------------------------------ Zoom --
    def _on_mousewheel(self, event):
        # Determina direzione
        if event.num == 4:
            delta = 1
        elif event.num == 5:
            delta = -1
        else:
            delta = 1 if event.delta > 0 else -1

        zoom_factor = 1.12 if delta > 0 else 1 / 1.12

        # Coordinate del mouse relative al centro canvas
        cw = self.canvas.winfo_width()
        ch = self.canvas.winfo_height()
        mx = event.x - cw / 2
        my = event.y - ch / 2

        # Aggiorna offset in modo che il punto sotto il cursore rimanga fisso
        self._offset_x = mx + (self._offset_x - mx) * zoom_factor
        self._offset_y = my + (self._offset_y - my) * zoom_factor

        self._scale = max(0.05, min(self._scale * zoom_factor, 40.0))
        self._render()

    # ------------------------------------------------------------- Pan --
    def _pan_start(self, event):
        self._panning = True
        self._pan_start_x = event.x
        self._pan_start_y = event.y

    def _pan_move(self, event):
        if not self._panning:
            return
        dx = event.x - self._pan_start_x
        dy = event.y - self._pan_start_y
        self._offset_x += dx
        self._offset_y += dy
        self._pan_start_x = event.x
        self._pan_start_y = event.y
        self._render()

    def _pan_end(self, event):
        self._panning = False

    # ---------------------------------------------------------- Resize --
    def _on_resize(self, event):
        self._render()

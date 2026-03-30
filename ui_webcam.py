import tkinter as tk
import customtkinter as ctk
from PIL import Image, ImageTk
import cv2
import os
import datetime
import threading


class WebcamFrame(ctk.CTkFrame):
    def __init__(self, master, on_scatto=None, **kwargs):
        kwargs.setdefault("fg_color", "#0f1629")
        kwargs.setdefault("corner_radius", 12)
        super().__init__(master, **kwargs)

        self.on_scatto = on_scatto

        self._cap: cv2.VideoCapture | None = None
        self._cam_index = 0
        self._running = False
        self._after_id = None
        self._tk_img: ImageTk.PhotoImage | None = None
        self._last_frame = None          # numpy array BGR – ultimo frame catturato
        self._frame_lock = threading.Lock()

        self._max_cam_index = 4          # prova fino a indice 4
        self._frame_delay_ms = 33        # ~30 fps

        self._build_ui()
        self._start_camera(self._cam_index)

    # ------------------------------------------------------------------ UI --
    def _build_ui(self):
        self.grid_rowconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=0)
        self.grid_columnconfigure(0, weight=1)

        # Area video
        self._canvas = tk.Canvas(
            self,
            bg="#080c18",
            highlightthickness=0,
        )
        self._canvas.grid(row=0, column=0, sticky="nsew", padx=0, pady=0)

        # Label di stato (nessuna cam disponibile / switching)
        self._status_label = ctk.CTkLabel(
            self._canvas,
            text="",
            text_color="#4060a0",
            font=ctk.CTkFont("Segoe UI", 13),
            fg_color="transparent",
        )
        self._status_label.place(relx=0.5, rely=0.5, anchor="center")

        # Barra pulsanti inferiore
        btn_bar = ctk.CTkFrame(self, fg_color="#080c18", corner_radius=0, height=58)
        btn_bar.grid(row=1, column=0, sticky="ew")
        btn_bar.grid_propagate(False)
        btn_bar.grid_columnconfigure((0, 1, 2), weight=1)

        self._btn_scatta = ctk.CTkButton(
            btn_bar,
            text="📸  Scatta",
            command=self._scatta,
            fg_color="#0f3460",
            hover_color="#1a4a80",
            text_color="white",
            font=ctk.CTkFont("Segoe UI", 13, weight="bold"),
            corner_radius=8,
            height=38,
        )
        self._btn_scatta.grid(row=0, column=0, padx=(12, 6), pady=10, sticky="ew")

        self._btn_cambia = ctk.CTkButton(
            btn_bar,
            text="🔄  Cambia Fotocamera",
            command=self._cambia_cam,
            fg_color="#162040",
            hover_color="#1e3060",
            text_color="#80b0d8",
            font=ctk.CTkFont("Segoe UI", 12),
            corner_radius=8,
            height=38,
        )
        self._btn_cambia.grid(row=0, column=1, padx=6, pady=10, sticky="ew")

        self._lbl_cam = ctk.CTkLabel(
            btn_bar,
            text="CAM 0",
            text_color="#304060",
            font=ctk.CTkFont("Segoe UI", 10),
        )
        self._lbl_cam.grid(row=0, column=2, padx=(0, 12), pady=10, sticky="e")

        # Bind resize canvas
        self._canvas.bind("<Configure>", self._on_canvas_resize)

    # ---------------------------------------------------- Camera control --
    def _start_camera(self, index: int):
        self._stop_loop()
        if self._cap is not None:
            self._cap.release()
            self._cap = None

        cap = cv2.VideoCapture(index, cv2.CAP_ANY)
        if cap is None or not cap.isOpened():
            self._show_status(f"⚠  Fotocamera {index} non disponibile")
            return

        self._cap = cap
        self._cam_index = index
        self._running = True
        self._lbl_cam.configure(text=f"CAM {index}")
        self._show_status("")
        self._loop()

    def _stop_loop(self):
        self._running = False
        if self._after_id is not None:
            try:
                self.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None

    def _cambia_cam(self):
        for step in range(1, self._max_cam_index + 2):
            next_idx = (self._cam_index + step) % (self._max_cam_index + 1)
            cap = cv2.VideoCapture(next_idx, cv2.CAP_ANY)
            if cap and cap.isOpened():
                cap.release()
                self._start_camera(next_idx)
                return
        self._show_status("⚠  Nessuna altra fotocamera trovata")

    # -------------------------------------------------------- Frame loop --
    def _loop(self):
        if not self._running or self._cap is None:
            return

        ret, frame = self._cap.read()
        if ret and frame is not None:
            with self._frame_lock:
                self._last_frame = frame.copy()
            self._display_frame(frame)

        self._after_id = self.after(self._frame_delay_ms, self._loop)

    def _display_frame(self, frame):
        cw = self._canvas.winfo_width()
        ch = self._canvas.winfo_height()
        if cw < 2 or ch < 2:
            return

        h, w = frame.shape[:2]
        scale = min(cw / w, ch / h)
        nw, nh = int(w * scale), int(h * scale)

        resized = cv2.resize(frame, (nw, nh), interpolation=cv2.INTER_LINEAR)
        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
        pil_img = Image.fromarray(rgb)
        self._tk_img = ImageTk.PhotoImage(pil_img)

        self._canvas.delete("frame")
        cx = cw // 2
        cy = ch // 2
        self._canvas.create_image(cx, cy, image=self._tk_img, anchor="center", tags="frame")

    # ----------------------------------------------------------- Scatto --
    def _scatta(self):
        with self._frame_lock:
            frame = self._last_frame.copy() if self._last_frame is not None else None

        if frame is None:
            return

        save_dir = os.path.join(os.path.expanduser("~"), "DentalCaptures")
        os.makedirs(save_dir, exist_ok=True)
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        path = os.path.join(save_dir, f"scatto_{ts}.jpg")
        cv2.imwrite(path, frame, [cv2.IMWRITE_JPEG_QUALITY, 95])

        self._flash_effect()

        if callable(self.on_scatto):
            self.after(50, lambda: self.on_scatto(path))

    def _flash_effect(self):
        """Breve flash bianco sul canvas per feedback visivo."""
        self._canvas.create_rectangle(
            0, 0, self._canvas.winfo_width(), self._canvas.winfo_height(),
            fill="white", outline="", tags="flash",
        )
        self.after(80, lambda: self._canvas.delete("flash"))

    # ---------------------------------------------------------- Helpers --
    def _show_status(self, msg: str):
        self._status_label.configure(text=msg)

    def _on_canvas_resize(self, event):
        # Il prossimo frame ridisegnerà automaticamente
        pass

    # --------------------------------------------------- Cleanup on destroy --
    def destroy(self):
        self._stop_loop()
        if self._cap is not None:
            self._cap.release()
            self._cap = None
        super().destroy()

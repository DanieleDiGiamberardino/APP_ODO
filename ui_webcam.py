"""
ui_webcam.py
============
Pannello di acquisizione fotografica diretta da webcam/fotocamera USB.

Funzionalità:
  - Lista di device disponibili (scan automatico)
  - Anteprima live a 30 fps via OpenCV → tk.Canvas
  - Scatto singolo con anteprima freeze e conferma
  - Tagging immediato (paziente, dente, branca, fase, nota)
  - Salvataggio nel DB come upload_foto() standard
  - Hotkey: SPAZIO per scattare, ESC per annullare

Dipendenze: opencv-python-headless (pip install opencv-python-headless)
"""

import tkinter as tk
from tkinter import messagebox
import customtkinter as ctk
from PIL import Image, ImageTk
from datetime import date
from pathlib import Path
from typing import Optional
import threading
import time
import io
import tempfile

import database as db

# ---------------------------------------------------------------------------
# Prova a importare OpenCV — gestione graceful se mancante
# ---------------------------------------------------------------------------
try:
    import cv2
    CV2_OK = True
except ImportError:
    cv2 = None
    CV2_OK = False

# ---------------------------------------------------------------------------
# Palette / Font
# ---------------------------------------------------------------------------

COLORI = {
    "bg":         "#0a0a14",
    "card":       "#16213e",
    "entry_bg":   "#0d1117",
    "accent":     "#0f3460",
    "accent_br":  "#e94560",
    "verde":      "#4caf50",
    "grigio":     "#9e9e9e",
    "chiaro":     "#e0e0e0",
    "rosso":      "#f44336",
    "preview_bg": "#000000",
    "freeze_border": "#e94560",
    "arancio": "#ff9800",
}

FONT_SEZ  = ("Segoe UI", 13, "bold")
FONT_NRM  = ("Segoe UI", 12)
FONT_SML  = ("Segoe UI", 10)
FONT_MICRO= ("Segoe UI", 9)

PREVIEW_W = 640
PREVIEW_H = 480

MAX_DEVICES = 6   # numero massimo di device da scandire


# ---------------------------------------------------------------------------
# Rilevamento dispositivi webcam
# ---------------------------------------------------------------------------

def _scan_dispositivi() -> list[tuple[int, str]]:
    """
    Scansiona gli indici 0..MAX_DEVICES e restituisce quelli aperibili.
    Restituisce lista di (indice, etichetta).
    Non disponibile se cv2 non è installato.
    """
    if not CV2_OK:
        return []
    trovati = []
    for i in range(MAX_DEVICES):
        cap = cv2.VideoCapture(i, cv2.CAP_DSHOW if hasattr(cv2, 'CAP_DSHOW') else 0)
        if cap.isOpened():
            trovati.append((i, f"Camera {i}"))
            cap.release()
    return trovati


# ===========================================================================
# FRAME: ACQUISIZIONE WEBCAM
# ===========================================================================

class WebcamFrame(ctk.CTkFrame):
    """
    Pannello principale webcam.

    Layout:
      Sinistra (2/3) → preview live + controlli camera
      Destra  (1/3)  → selezione paziente + tag + salvataggio
    """

    def __init__(self, master, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)

        self._cap: Optional["cv2.VideoCapture"] = None
        self._live: bool = False          # True = stream attivo
        self._frozen: bool = False        # True = foto scattata, stream in pausa
        self._frame_corrente = None       # ultimo frame OpenCV (BGR)
        self._frame_freeze   = None       # frame congelato allo scatto
        self._tk_img: Optional[ImageTk.PhotoImage] = None
        self._stream_thread: Optional[threading.Thread] = None
        self._paz_id: Optional[int] = None

        self._build_ui()
        self._ricarica_dispositivi()
        self._ricarica_pazienti()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self):

        self.grid_columnconfigure(0, weight=2)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # ── Colonna sinistra: camera ──────────────────────────────────
        cc = ctk.CTkFrame(self, fg_color=COLORI["card"], corner_radius=12)
        cc.grid(row=0, column=0, padx=(0, 8), pady=0, sticky="nsew")
        cc.grid_columnconfigure(0, weight=1)
        cc.grid_rowconfigure(2, weight=1)

        # Header camera
        hdr = ctk.CTkFrame(cc, fg_color="transparent")
        hdr.grid(row=0, column=0, padx=16, pady=(14, 4), sticky="ew")
        hdr.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(hdr, text="📸  Acquisizione Webcam",
                     font=FONT_SEZ).grid(row=0, column=0, sticky="w")

        # Selettore device
        self._combo_device = ctk.CTkComboBox(
            hdr, values=["— nessuna camera —"],
            font=FONT_SML, width=180, height=30, state="readonly")
        self._combo_device.grid(row=0, column=1, padx=(12, 0), sticky="e")

        ctk.CTkButton(hdr, text="🔄", width=32, height=30,
                      font=FONT_SML, fg_color=COLORI["accent"],
                      command=self._ricarica_dispositivi).grid(
            row=0, column=2, padx=(4, 0))

        # Pulsanti avvia/ferma
        ctrl = ctk.CTkFrame(cc, fg_color="transparent")
        ctrl.grid(row=1, column=0, padx=16, pady=(4, 8), sticky="ew")

        self._btn_avvia = ctk.CTkButton(
            ctrl, text="▶  Avvia Camera",
            font=FONT_NRM, height=36, width=160,
            fg_color=COLORI["verde"], hover_color="#388e3c",
            command=self._avvia_camera)
        self._btn_avvia.pack(side="left", padx=(0, 8))

        self._btn_ferma = ctk.CTkButton(
            ctrl, text="⏹  Ferma",
            font=FONT_NRM, height=36, width=100,
            fg_color=COLORI["rosso"], hover_color="#c62828",
            state="disabled",
            command=self._ferma_camera)
        self._btn_ferma.pack(side="left", padx=(0, 16))

        self._lbl_stato_cam = ctk.CTkLabel(
            ctrl, text="Camera non avviata",
            font=FONT_SML, text_color=COLORI["grigio"])
        self._lbl_stato_cam.pack(side="left")

        # Canvas preview
        self._canvas = tk.Canvas(
            cc,
            width=PREVIEW_W, height=PREVIEW_H,
            bg=COLORI["preview_bg"],
            highlightthickness=2,
            highlightbackground=COLORI["accent"],
        )
        self._canvas.grid(row=2, column=0, padx=16, pady=(0, 12), sticky="nsew")
        self._canvas.bind("<Configure>", lambda e: self._aggiorna_canvas_placeholder())
        # Hotkey SPAZIO → scatta
        self._canvas.bind("<space>", lambda e: self._scatta())
        self._canvas.focus_set()

        self._aggiorna_canvas_placeholder()

        # Pulsante scatta (grande, sotto il canvas)
        self._btn_scatta = ctk.CTkButton(
            cc,
            text="📷  SCATTA  (Spazio)",
            font=("Segoe UI", 14, "bold"),
            height=50,
            fg_color=COLORI["accent_br"],
            hover_color="#c73652",
            state="disabled",
            command=self._scatta,
        )
        self._btn_scatta.grid(row=3, column=0, padx=16, pady=(0, 16), sticky="ew")

        # ── Colonna destra: tag + salvataggio ─────────────────────────
        tc = ctk.CTkFrame(self, fg_color=COLORI["card"], corner_radius=12)
        tc.grid(row=0, column=1, padx=(8, 0), pady=0, sticky="nsew")
        tc.grid_columnconfigure(0, weight=1)
        tc.grid_rowconfigure(3, weight=1)

        ctk.CTkLabel(tc, text="1 · Paziente",
                     font=FONT_SEZ).grid(row=0, column=0, padx=16, pady=(16, 6), sticky="w")

        self._cerca_paz = ctk.CTkEntry(tc, placeholder_text="🔍 Filtra…",
                                        font=FONT_NRM, height=32)
        self._cerca_paz.grid(row=1, column=0, padx=16, pady=(0, 6), sticky="ew")
        self._cerca_paz.bind("<KeyRelease>", lambda e: self._ricarica_pazienti())

        self._lista_paz = ctk.CTkScrollableFrame(tc, fg_color="transparent", height=200)
        self._lista_paz.grid(row=2, column=0, padx=8, pady=(0, 4), sticky="ew")
        self._lista_paz.grid_columnconfigure(0, weight=1)

        self._lbl_paz = ctk.CTkLabel(tc, text="Nessun paziente",
                                      font=FONT_SML,
                                      text_color=COLORI["grigio"])
        self._lbl_paz.grid(row=3, column=0, padx=16, pady=(0, 6))

        ctk.CTkLabel(tc, text="2 · Tag Clinici",
                     font=FONT_SEZ).grid(row=4, column=0, padx=16, pady=(8, 4), sticky="w")

        # Dente
        ctk.CTkLabel(tc, text="Dente (FDI)", font=FONT_MICRO,
                     text_color=COLORI["grigio"]).grid(
            row=5, column=0, padx=16, pady=(0, 2), sticky="w")
        self._c_dente = ctk.CTkComboBox(tc, values=db.DENTI_FDI,
                                         font=FONT_NRM, height=32, state="readonly")
        self._c_dente.set(db.DENTI_FDI[0])
        self._c_dente.grid(row=6, column=0, padx=16, pady=(0, 8), sticky="ew")

        # Branca
        ctk.CTkLabel(tc, text="Branca", font=FONT_MICRO,
                     text_color=COLORI["grigio"]).grid(
            row=7, column=0, padx=16, pady=(0, 2), sticky="w")
        self._c_branca = ctk.CTkComboBox(tc, values=db.BRANCHE,
                                          font=FONT_NRM, height=32, state="readonly")
        self._c_branca.set(db.BRANCHE[0])
        self._c_branca.grid(row=8, column=0, padx=16, pady=(0, 8), sticky="ew")

        # Fase
        ctk.CTkLabel(tc, text="Fase", font=FONT_MICRO,
                     text_color=COLORI["grigio"]).grid(
            row=9, column=0, padx=16, pady=(0, 2), sticky="w")
        self._c_fase = ctk.CTkComboBox(tc, values=db.FASI,
                                        font=FONT_NRM, height=32, state="readonly")
        self._c_fase.set(db.FASI[0])
        self._c_fase.grid(row=10, column=0, padx=16, pady=(0, 8), sticky="ew")

        # Note
        ctk.CTkLabel(tc, text="Note", font=FONT_MICRO,
                     text_color=COLORI["grigio"]).grid(
            row=11, column=0, padx=16, pady=(0, 2), sticky="w")
        self._txt_note = ctk.CTkTextbox(tc, font=FONT_NRM, height=60,
                                         fg_color=COLORI["entry_bg"])
        self._txt_note.grid(row=12, column=0, padx=16, pady=(0, 12), sticky="ew")

        # Pulsante salva scatto
        self._btn_salva = ctk.CTkButton(
            tc,
            text="💾  Salva Foto",
            font=("Segoe UI", 13, "bold"), height=46,
            fg_color=COLORI["verde"], hover_color="#388e3c",
            state="disabled",
            command=self._salva_scatto,
        )
        self._btn_salva.grid(row=13, column=0, padx=16, pady=(0, 8), sticky="ew")

        # Annulla scatto
        self._btn_annulla = ctk.CTkButton(
            tc, text="↩  Riprendi Stream",
            font=FONT_SML, height=34,
            fg_color="transparent", border_width=1,
            state="disabled",
            command=self._riprendi_stream,
        )
        self._btn_annulla.grid(row=14, column=0, padx=16, pady=(0, 16), sticky="ew")

        self._lbl_esito = ctk.CTkLabel(tc, text="", font=FONT_SML,
                                        text_color=COLORI["verde"])
        self._lbl_esito.grid(row=15, column=0, pady=(0, 8))

    # ------------------------------------------------------------------
    # Placeholder canvas
    # ------------------------------------------------------------------

    def _aggiorna_canvas_placeholder(self):
        if not self._live and not self._frozen:
            self._canvas.delete("all")
            w = self._canvas.winfo_width() or PREVIEW_W
            h = self._canvas.winfo_height() or PREVIEW_H
            self._canvas.create_text(
                w // 2, h // 2,
                text="📷\nAvvia la camera per visualizzare\nl'anteprima live",
                fill=COLORI["grigio"],
                font=("Segoe UI", 13),
                justify="center",
            )

    # ------------------------------------------------------------------
    # Gestione dispositivi
    # ------------------------------------------------------------------

    def _ricarica_dispositivi(self):
        if not CV2_OK:
            self._combo_device.configure(values=["cv2 non installato"])
            self._combo_device.set("cv2 non installato")
            return

        dispositivi = _scan_dispositivi()
        if dispositivi:
            etichette = [d[1] for d in dispositivi]
            self._combo_device.configure(values=etichette)
            self._combo_device.set(etichette[0])
            self._btn_avvia.configure(state="normal")
        else:
            self._combo_device.configure(values=["Nessuna camera trovata"])
            self._combo_device.set("Nessuna camera trovata")
            self._btn_avvia.configure(state="disabled")

    def _device_selezionato_indice(self) -> int:
        """Ricava l'indice numerico del device dal testo del combo (es. 'Camera 2' → 2)."""
        testo = self._combo_device.get()
        try:
            return int(testo.split()[-1])
        except (ValueError, IndexError):
            return 0

    # ------------------------------------------------------------------
    # Controllo camera
    # ------------------------------------------------------------------

    def _avvia_camera(self):
        if not CV2_OK:
            self.lblstatocam.configure(
                text="⚠ opencv non installato (pip install opencv-python-headless)",
                text_color=COLORI["rosso"]
            )
            return

        idx = self._device_selezionato_indice()
        self._cap = cv2.VideoCapture(idx)
        if not self._cap.isOpened():
            messagebox.showerror("Errore", f"Impossibile aprire camera {idx}.",
                                  parent=self)
            self._cap = None
            return

        # Imposta risoluzione
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH,  1280)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

        self._live    = True
        self._frozen  = False
        self._canvas.configure(highlightbackground=COLORI["verde"])
        self._btn_avvia.configure(state="disabled")
        self._btn_ferma.configure(state="normal")
        self._btn_scatta.configure(state="normal")
        self._lbl_stato_cam.configure(text="🔴  Live", text_color=COLORI["accent_br"])

        # Thread di acquisizione frame
        self._stream_thread = threading.Thread(target=self._loop_stream, daemon=True)
        self._stream_thread.start()

    def _ferma_camera(self):
        self._live   = False
        self._frozen = False
        if self._cap:
            self._cap.release()
            self._cap = None
        self._canvas.configure(highlightbackground=COLORI["accent"])
        self._btn_avvia.configure(state="normal")
        self._btn_ferma.configure(state="disabled")
        self._btn_scatta.configure(state="disabled")
        self._btn_salva.configure(state="disabled")
        self._btn_annulla.configure(state="disabled")
        self._lbl_stato_cam.configure(text="Camera ferma", text_color=COLORI["grigio"])
        self.after(50, self._aggiorna_canvas_placeholder)

    # ------------------------------------------------------------------
    # Loop acquisizione frame (thread)
    # ------------------------------------------------------------------

    def _loop_stream(self):
        """Legge i frame dalla camera e li invia al canvas via after()."""
        while self._live and self._cap and not self._frozen:
            ret, frame = self._cap.read()
            if not ret:
                break
            self._frame_corrente = frame
            self.after(0, self._mostra_frame, frame)
            time.sleep(1 / 30)   # ~30 fps

    def _mostra_frame(self, frame_bgr):
        """Converte frame BGR → RGB → resize → PhotoImage → Canvas."""
        if self._frozen:
            return
        try:
            rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
            pil = Image.fromarray(rgb)
            cw = self._canvas.winfo_width()
            ch = self._canvas.winfo_height()
            if cw > 10 and ch > 10:
                pil.thumbnail((cw, ch), Image.NEAREST)
            self._tk_img = ImageTk.PhotoImage(pil)
            self._canvas.delete("all")
            self._canvas.create_image(
                cw // 2, ch // 2, image=self._tk_img, anchor="center")
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Scatto e conferma
    # ------------------------------------------------------------------

    def _scatta(self):
        """Congela il frame corrente e attiva i controlli di salvataggio."""
        if not self._live or self._frame_corrente is None:
            return

        self._live   = False    # blocca il loop
        self._frozen = True
        self._frame_freeze = self._frame_corrente.copy()

        # Mostra l'ultimo frame congelato con bordo rosso
        rgb = cv2.cvtColor(self._frame_freeze, cv2.COLOR_BGR2RGB)
        pil = Image.fromarray(rgb)
        cw = self._canvas.winfo_width()
        ch = self._canvas.winfo_height()
        if cw > 10 and ch > 10:
            pil.thumbnail((cw, ch), Image.LANCZOS)

        self._tk_img = ImageTk.PhotoImage(pil)
        self._canvas.delete("all")
        self._canvas.create_image(cw // 2, ch // 2, image=self._tk_img, anchor="center")

        # Indicatore "SCATTATA"
        self._canvas.create_rectangle(0, 0, cw, 36, fill="#000000", stipple="gray50",
                                       outline="")
        self._canvas.create_text(cw // 2, 18, text="📷  FOTO SCATTATA — Salva o riprendi",
                                  fill=COLORI["accent_br"], font=("Segoe UI", 11, "bold"))
        self._canvas.configure(highlightbackground=COLORI["freeze_border"])

        self._btn_scatta.configure(state="disabled")
        self._btn_salva.configure(state="normal")
        self._btn_annulla.configure(state="normal")
        self._lbl_stato_cam.configure(text="⏸  Foto congelata", text_color=COLORI["arancio","#ff9800"]
                                       if hasattr(COLORI, "arancio") else "#ff9800")

    def _riprendi_stream(self):
        """Riavvia il live stream dopo uno scatto non salvato."""
        self._frozen = False
        self._frame_freeze = None
        self._live = True
        self._canvas.configure(highlightbackground=COLORI["verde"])
        self._btn_scatta.configure(state="normal")
        self._btn_salva.configure(state="disabled")
        self._btn_annulla.configure(state="disabled")
        self._lbl_stato_cam.configure(text="🔴  Live", text_color=COLORI["accent_br"])
        self._stream_thread = threading.Thread(target=self._loop_stream, daemon=True)
        self._stream_thread.start()

    # ------------------------------------------------------------------
    # Salvataggio
    # ------------------------------------------------------------------

    def _salva_scatto(self):
        """Salva il frame congelato come JPEG in images_storage via db.upload_foto()."""
        if self._frame_freeze is None:
            return
        if self._paz_id is None:
            messagebox.showwarning("Paziente mancante", "Seleziona un paziente.",
                                    parent=self)
            return

        # Salva il frame in un file temporaneo JPEG
        import tempfile, os
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            tmp_path = Path(tmp.name)

        rgb  = cv2.cvtColor(self._frame_freeze, cv2.COLOR_BGR2RGB)
        pil  = Image.fromarray(rgb)
        pil.save(tmp_path, format="JPEG", quality=90)

        try:
            fid = db.upload_foto(
                paziente_id=self._paz_id,
                sorgente_path=tmp_path,
                data_scatto=date.today(),
                dente=self._c_dente.get(),
                branca=self._c_branca.get(),
                fase=self._c_fase.get(),
                note=self._txt_note.get("1.0", "end").strip(),
            )
            self._lbl_esito.configure(
                text=f"✅  Foto salvata  (ID {fid})",
                text_color=COLORI["verde"],
            )
            self._txt_note.delete("1.0", "end")
            # Riprende automaticamente dopo il salvataggio
            self._riprendi_stream()
        except Exception as exc:
            self._lbl_esito.configure(
                text=f"❌  {exc}", text_color=COLORI["rosso"])
        finally:
            try:
                tmp_path.unlink()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Lista pazienti
    # ------------------------------------------------------------------

    def _ricarica_pazienti(self, *_):
        righe = db.cerca_pazienti(self._cerca_paz.get())
        for w in self._lista_paz.winfo_children():
            w.destroy()
        for i, r in enumerate(righe):
            sel = (r["id"] == self._paz_id)
            ctk.CTkButton(
                self._lista_paz,
                text=f"{r['cognome']} {r['nome']}",
                font=FONT_SML, height=28,
                fg_color=COLORI["accent"] if sel else COLORI["entry_bg"],
                anchor="w",
                command=lambda rid=r["id"], rn=f"{r['cognome']} {r['nome']}":
                    self._set_paz(rid, rn),
            ).grid(row=i, column=0, padx=4, pady=2, sticky="ew")

    def _set_paz(self, pid: int, nome: str):
        self._paz_id = pid
        self._lbl_paz.configure(text=f"✅ {nome}", text_color=COLORI["verde"])
        self._ricarica_pazienti()

    def imposta_paziente(self, pid: int):
        """API pubblica per pre-selezionare un paziente."""
        r = db.get_paziente_by_id(pid)
        if r:
            self._set_paz(pid, f"{r['cognome']} {r['nome']}")

    # ------------------------------------------------------------------
    # Cleanup alla distruzione del frame
    # ------------------------------------------------------------------

    def destroy(self):
        self._live = False
        if self._cap:
            self._cap.release()
            self._cap = None
        super().destroy()

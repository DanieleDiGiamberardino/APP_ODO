"""
export_pdf.py
=============
Genera un dossier clinico PDF per un paziente, con intestazione anagrafica,
griglia di foto con metadati e footer con data di stampa.

Libreria: reportlab (pip install reportlab)

Uso standalone:
    from export_pdf import genera_dossier_pdf
    path = genera_dossier_pdf(paziente_id=1)
    # → restituisce il Path del file generato
"""

import io
from pathlib import Path
from datetime import date
from typing import Optional

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm, mm
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    Image as RLImage, HRFlowable, KeepTogether,
)
from PIL import Image as PILImage

import database as db

# ---------------------------------------------------------------------------
# PALETTE COLORI (coerente con la UI)
# ---------------------------------------------------------------------------

C_BLU_SCURO  = colors.HexColor("#0f3460")
C_ROSSO_ACC  = colors.HexColor("#e94560")
C_GRIGIO_CHI = colors.HexColor("#f4f4f8")
C_GRIGIO_SCU = colors.HexColor("#666680")
C_BIANCO     = colors.white
C_NERO       = colors.HexColor("#1a1a2e")

# ---------------------------------------------------------------------------
# STILI TESTO
# ---------------------------------------------------------------------------

_stili = getSampleStyleSheet()

STILE_TITOLO = ParagraphStyle(
    "titolo",
    parent=_stili["Title"],
    fontSize=22,
    textColor=C_BLU_SCURO,
    spaceAfter=2 * mm,
    fontName="Helvetica-Bold",
)

STILE_SOTTOTITOLO = ParagraphStyle(
    "sottotitolo",
    parent=_stili["Normal"],
    fontSize=11,
    textColor=C_GRIGIO_SCU,
    spaceAfter=4 * mm,
    fontName="Helvetica",
)

STILE_SEZIONE = ParagraphStyle(
    "sezione",
    parent=_stili["Heading2"],
    fontSize=13,
    textColor=C_BLU_SCURO,
    spaceBefore=6 * mm,
    spaceAfter=3 * mm,
    fontName="Helvetica-Bold",
    borderPad=2,
)

STILE_META_LABEL = ParagraphStyle(
    "meta_label",
    parent=_stili["Normal"],
    fontSize=7,
    textColor=C_GRIGIO_SCU,
    fontName="Helvetica-Bold",
    leading=10,
)

STILE_META_VALORE = ParagraphStyle(
    "meta_valore",
    parent=_stili["Normal"],
    fontSize=8,
    textColor=C_NERO,
    fontName="Helvetica",
    leading=11,
)

STILE_FOOTER = ParagraphStyle(
    "footer",
    parent=_stili["Normal"],
    fontSize=7,
    textColor=C_GRIGIO_SCU,
    alignment=TA_CENTER,
    fontName="Helvetica",
)

STILE_HEADER_TABELLA = ParagraphStyle(
    "header_tab",
    parent=_stili["Normal"],
    fontSize=8,
    textColor=C_BIANCO,
    fontName="Helvetica-Bold",
    alignment=TA_CENTER,
)

STILE_CELLA = ParagraphStyle(
    "cella",
    parent=_stili["Normal"],
    fontSize=8,
    textColor=C_NERO,
    fontName="Helvetica",
)


# ---------------------------------------------------------------------------
# HELPER: immagine PIL → RLImage (con gestione errori e ridimensionamento)
# ---------------------------------------------------------------------------

def _rl_image(percorso: Path, max_w: float, max_h: float) -> Optional[RLImage]:
    """
    Carica un'immagine con Pillow, la porta a RGB, la bufferizza in memoria
    e la restituisce come RLImage di ReportLab entro i limiti max_w × max_h.

    Restituisce None se il file non è leggibile.
    """
    try:
        with PILImage.open(percorso) as img:
            img = img.convert("RGB")
            w_orig, h_orig = img.size

            # Calcola scala mantenendo le proporzioni
            scala = min(max_w / w_orig, max_h / h_orig, 1.0)
            new_w = int(w_orig * scala)
            new_h = int(h_orig * scala)
            img = img.resize((new_w, new_h), PILImage.LANCZOS)

            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=85)
            buf.seek(0)

            return RLImage(buf, width=new_w, height=new_h)
    except Exception:
        return None


def _placeholder_rl(w: float, h: float) -> Table:
    """
    Restituisce una cella Table grigia come placeholder per immagini mancanti.
    """
    t = Table([["Immagine\nnon disponibile"]], colWidths=[w], rowHeights=[h])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), C_GRIGIO_CHI),
        ("TEXTCOLOR",  (0, 0), (-1, -1), C_GRIGIO_SCU),
        ("ALIGN",      (0, 0), (-1, -1), "CENTER"),
        ("VALIGN",     (0, 0), (-1, -1), "MIDDLE"),
        ("FONTSIZE",   (0, 0), (-1, -1), 7),
        ("FONTNAME",   (0, 0), (-1, -1), "Helvetica"),
        ("BOX",        (0, 0), (-1, -1), 0.5, C_GRIGIO_SCU),
    ]))
    return t


# ---------------------------------------------------------------------------
# SEZIONE: intestazione paziente
# ---------------------------------------------------------------------------

def _sezione_anagrafica(paziente: db.sqlite3.Row, n_foto: int) -> list:
    """Restituisce la lista di flowable per l'intestazione anagrafica."""
    elementi = []

    # Barra intestazione colorata
    barra = Table(
        [[
            Paragraph("🦷  DentalPhoto — Dossier Clinico", STILE_TITOLO),
            Paragraph(
                f"Generato il: {date.today().strftime('%d/%m/%Y')}",
                ParagraphStyle("data", parent=STILE_SOTTOTITOLO, alignment=TA_RIGHT),
            ),
        ]],
        colWidths=["*", 5 * cm],
    )
    barra.setStyle(TableStyle([
        ("BACKGROUND",  (0, 0), (-1, -1), C_BLU_SCURO),
        ("TEXTCOLOR",   (0, 0), (-1, -1), C_BIANCO),
        ("PADDING",     (0, 0), (-1, -1), 10),
        ("VALIGN",      (0, 0), (-1, -1), "MIDDLE"),
        ("ROUNDEDCORNERS", [4]),
    ]))
    elementi.append(barra)
    elementi.append(Spacer(1, 6 * mm))

    # Scheda paziente
    tel = paziente["telefono"] or "—"
    note_paz = paziente["note"] or "—"

    dati_paz = [
        [
            Paragraph("PAZIENTE", STILE_META_LABEL),
            Paragraph("TELEFONO", STILE_META_LABEL),
            Paragraph("FOTOGRAFIE ARCHIVIATE", STILE_META_LABEL),
        ],
        [
            Paragraph(
                f"{paziente['cognome'].upper()} {paziente['nome']}",
                ParagraphStyle("nome_paz", parent=STILE_META_VALORE,
                               fontSize=14, fontName="Helvetica-Bold",
                               textColor=C_BLU_SCURO),
            ),
            Paragraph(tel, STILE_META_VALORE),
            Paragraph(
                str(n_foto),
                ParagraphStyle("n_foto", parent=STILE_META_VALORE,
                               fontSize=14, fontName="Helvetica-Bold",
                               textColor=C_ROSSO_ACC),
            ),
        ],
        [
            Paragraph("NOTE PAZIENTE", STILE_META_LABEL),
            Paragraph(note_paz, STILE_META_VALORE),
            Paragraph("", STILE_META_VALORE),
        ],
    ]

    t_paz = Table(dati_paz, colWidths=["*", 4 * cm, 5 * cm])
    t_paz.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0), C_GRIGIO_CHI),
        ("LINEBELOW",     (0, 0), (-1, 0), 0.5, C_GRIGIO_SCU),
        ("LINEBELOW",     (0, 1), (-1, 1), 0.5, C_GRIGIO_CHI),
        ("PADDING",       (0, 0), (-1, -1), 6),
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
        ("BOX",           (0, 0), (-1, -1), 1, C_BLU_SCURO),
        ("SPAN",          (1, 2), (2, 2)),
    ]))
    elementi.append(t_paz)
    elementi.append(Spacer(1, 8 * mm))

    return elementi


# ---------------------------------------------------------------------------
# SEZIONE: tabella riepilogativa foto
# ---------------------------------------------------------------------------

def _sezione_tabella_riepilogo(foto_rows: list) -> list:
    """
    Genera una tabella testuale compatta con tutti i metadati delle foto
    (senza immagini), utile come indice di riferimento rapido.
    """
    if not foto_rows:
        return []

    elementi = [
        Paragraph("Riepilogo Archivio Fotografico", STILE_SEZIONE),
        HRFlowable(width="100%", thickness=1, color=C_BLU_SCURO, spaceAfter=4 * mm),
    ]

    # Intestazione tabella
    header = [
        Paragraph("#",        STILE_HEADER_TABELLA),
        Paragraph("Data",     STILE_HEADER_TABELLA),
        Paragraph("Dente",    STILE_HEADER_TABELLA),
        Paragraph("Branca",   STILE_HEADER_TABELLA),
        Paragraph("Fase",     STILE_HEADER_TABELLA),
        Paragraph("Note",     STILE_HEADER_TABELLA),
    ]
    dati = [header]

    for i, r in enumerate(foto_rows, start=1):
        riga = [
            Paragraph(str(i),                STILE_CELLA),
            Paragraph(r["data_scatto"] or "—", STILE_CELLA),
            Paragraph(r["dente"]       or "—", STILE_CELLA),
            Paragraph(r["branca"]      or "—", STILE_CELLA),
            Paragraph(r["fase"]        or "—", STILE_CELLA),
            Paragraph((r["note"] or "")[:60] + ("…" if len(r["note"] or "") > 60 else ""),
                      STILE_CELLA),
        ]
        dati.append(riga)

    t = Table(
        dati,
        colWidths=[1 * cm, 2.5 * cm, 2 * cm, 4 * cm, 3 * cm, "*"],
        repeatRows=1,
    )
    t.setStyle(TableStyle([
        # Header
        ("BACKGROUND", (0, 0), (-1, 0), C_BLU_SCURO),
        ("TEXTCOLOR",  (0, 0), (-1, 0), C_BIANCO),
        ("FONTNAME",   (0, 0), (-1, 0), "Helvetica-Bold"),
        # Righe alternate
        *[("BACKGROUND", (0, i), (-1, i), C_GRIGIO_CHI)
          for i in range(2, len(dati), 2)],
        # Bordi
        ("INNERGRID",  (0, 0), (-1, -1), 0.25, colors.HexColor("#cccccc")),
        ("BOX",        (0, 0), (-1, -1), 0.5,  C_BLU_SCURO),
        ("PADDING",    (0, 0), (-1, -1), 4),
        ("VALIGN",     (0, 0), (-1, -1), "TOP"),
    ]))

    elementi.append(t)
    return elementi


# ---------------------------------------------------------------------------
# SEZIONE: galleria fotografica
# ---------------------------------------------------------------------------

def _sezione_galleria(foto_rows: list, foto_per_riga: int = 3) -> list:
    """
    Genera la galleria fotografica: griglia N×3 con immagine + metadati sotto.

    Ogni cella contiene:
      ┌──────────────────┐
      │    Fotografia    │
      ├──────────────────┤
      │ Dente / Branca   │
      │ Fase / Data      │
      │ Note             │
      └──────────────────┘
    """
    if not foto_rows:
        return [Paragraph("Nessuna fotografia da visualizzare.", STILE_SOTTOTITOLO)]

    elementi = [
        Paragraph("Galleria Fotografica", STILE_SEZIONE),
        HRFlowable(width="100%", thickness=1, color=C_BLU_SCURO, spaceAfter=4 * mm),
    ]

    # Larghezza disponibile con 3 colonne (A4 - margini)
    larghezza_pagina = A4[0] - 4 * cm   # 4cm = 2cm margin × 2
    cell_w = larghezza_pagina / foto_per_riga - 3 * mm
    img_h  = cell_w * 0.75              # proporzione 4:3

    # Raggruppa le foto in righe da N
    for i in range(0, len(foto_rows), foto_per_riga):
        blocco = foto_rows[i : i + foto_per_riga]

        # Padding celle vuote per completare l'ultima riga
        while len(blocco) < foto_per_riga:
            blocco.append(None)

        riga_tabella = []
        for r in blocco:
            if r is None:
                riga_tabella.append("")
                continue

            percorso = db.get_percorso_assoluto(r)
            img = _rl_image(percorso, cell_w, img_h)
            img_elem = img if img else _placeholder_rl(cell_w, img_h)

            # Metadati sotto l'immagine
            meta_lines = [
                img_elem,
                Spacer(1, 1 * mm),
                Paragraph(
                    f"<b>Dente:</b> {r['dente'] or '—'} &nbsp;|&nbsp; "
                    f"<b>Fase:</b> {r['fase'] or '—'}",
                    STILE_META_VALORE,
                ),
                Paragraph(
                    f"<b>Branca:</b> {r['branca'] or '—'}",
                    STILE_META_VALORE,
                ),
                Paragraph(
                    f"<b>Data:</b> {r['data_scatto'] or '—'}",
                    STILE_META_VALORE,
                ),
            ]
            if r["note"]:
                meta_lines.append(
                    Paragraph(f"<i>{r['note'][:80]}</i>", STILE_META_LABEL)
                )

            riga_tabella.append(meta_lines)

        griglia = Table(
            [riga_tabella],
            colWidths=[cell_w + 3 * mm] * foto_per_riga,
        )
        griglia.setStyle(TableStyle([
            ("VALIGN",   (0, 0), (-1, -1), "TOP"),
            ("ALIGN",    (0, 0), (-1, -1), "CENTER"),
            ("PADDING",  (0, 0), (-1, -1), 4),
            ("BOX",      (0, 0), (0, 0), 0.5, C_GRIGIO_CHI),
            ("LINEAFTER",(0, 0), (-2, 0), 0.5, C_GRIGIO_CHI),
        ]))
        elementi.append(KeepTogether(griglia))
        elementi.append(Spacer(1, 4 * mm))

    return elementi


# ---------------------------------------------------------------------------
# CALLBACK HEADER / FOOTER (ogni pagina)
# ---------------------------------------------------------------------------

def _costruisci_header_footer(paziente_nome: str):
    """
    Restituisce la funzione onPage per SimpleDocTemplate.
    Viene chiamata per ogni pagina del PDF.
    """
    def _on_page(canvas_obj, doc):
        canvas_obj.saveState()
        w, h = A4

        # Header: linea sottile + nome paziente
        canvas_obj.setStrokeColor(C_BLU_SCURO)
        canvas_obj.setLineWidth(0.5)
        canvas_obj.line(2 * cm, h - 1.8 * cm, w - 2 * cm, h - 1.8 * cm)
        canvas_obj.setFont("Helvetica", 8)
        canvas_obj.setFillColor(C_GRIGIO_SCU)
        canvas_obj.drawString(2 * cm, h - 1.5 * cm, f"DentalPhoto – {paziente_nome}")
        canvas_obj.drawRightString(w - 2 * cm, h - 1.5 * cm, "Dossier Clinico – Riservato")

        # Footer: linea + numero pagina
        canvas_obj.line(2 * cm, 1.5 * cm, w - 2 * cm, 1.5 * cm)
        canvas_obj.drawCentredString(
            w / 2, 1.1 * cm,
            f"Pagina {doc.page}  –  Generato il {date.today().strftime('%d/%m/%Y')}",
        )
        canvas_obj.restoreState()

    return _on_page


# ---------------------------------------------------------------------------
# FUNZIONE PRINCIPALE
# ---------------------------------------------------------------------------

def genera_dossier_pdf(
    paziente_id: int,
    output_dir: Optional[Path] = None,
    filtri: Optional[dict] = None,
) -> Path:
    """
    Genera il dossier PDF clinico per un paziente e lo salva su disco.

    Args:
        paziente_id: ID del paziente nel DB.
        output_dir:  Cartella di destinazione. Default: stessa directory del DB.
        filtri:      Dizionario opzionale di filtri aggiuntivi da passare a
                     db.cerca_foto() (es. {"branca": "Conservativa", "fase": "Post-op"}).
                     Se None, vengono incluse TUTTE le foto del paziente.

    Returns:
        Path assoluto del file PDF generato.

    Raises:
        ValueError: se il paziente_id non esiste nel DB.
    """
    paziente = db.get_paziente_by_id(paziente_id)
    if paziente is None:
        raise ValueError(f"Paziente con ID {paziente_id} non trovato.")

    # Costruisce i filtri per la query foto
    kw = {"paziente_id": paziente_id}
    if filtri:
        kw.update(filtri)

    foto_rows = db.cerca_foto(**kw)
    n_foto    = len(foto_rows)

    # Percorso output
    if output_dir is None:
        output_dir = db.APP_DIR
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    nome_file = (
        f"dossier_{paziente['cognome'].lower()}_{paziente['nome'].lower()}"
        f"_{date.today().isoformat()}.pdf"
    )
    output_path = output_dir / nome_file

    # Costruzione documento ReportLab
    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=2.5 * cm,
        bottomMargin=2.5 * cm,
        title=f"Dossier {paziente['cognome']} {paziente['nome']}",
        author="DentalPhoto",
        subject="Dossier fotografico clinico odontoiatrico",
    )

    nome_completo = f"{paziente['cognome']} {paziente['nome']}"

    # Assembla tutti gli elementi nella storia (lista di flowable)
    storia: list = []
    storia += _sezione_anagrafica(paziente, n_foto)
    storia += _sezione_tabella_riepilogo(foto_rows)
    storia += _sezione_galleria(foto_rows, foto_per_riga=3)

    # Build con callback header/footer
    doc.build(
        storia,
        onFirstPage=_costruisci_header_footer(nome_completo),
        onLaterPages=_costruisci_header_footer(nome_completo),
    )

    return output_path


# ---------------------------------------------------------------------------
# TEST RAPIDO
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    db.init_db()
    pazienti = db.cerca_pazienti()
    if not pazienti:
        print("[PDF] Nessun paziente nel DB. Inseriscine uno prima.")
    else:
        pid = pazienti[0]["id"]
        out = genera_dossier_pdf(pid)
        print(f"[PDF] Dossier generato: {out}")

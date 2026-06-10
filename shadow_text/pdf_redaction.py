from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .engine import RedactionEntry


@dataclass(frozen=True)
class PdfMark:
    tag: str
    value: str
    page_index: int
    x0: float
    y0: float
    x1: float
    y1: float
    font_size: float


def write_redacted_pdf(
    source_path: Path,
    output_path: Path,
    entries: list[RedactionEntry],
    *,
    ocr_tokens: list[dict[str, Any]] | None = None,
) -> list[dict]:
    try:
        import fitz
    except ImportError as exc:
        raise RuntimeError(
            "Per censurare PDF preservando il layout serve PyMuPDF. "
            "Installa le dipendenze con: pip install -r requirements.txt"
        ) from exc

    doc = fitz.open(source_path)
    marks: list[PdfMark] = []
    used_rects: set[tuple[int, int, int, int, int]] = set()

    for entry in entries:
        rect = (
            _find_ocr_rect(entry, ocr_tokens)
            if ocr_tokens
            else _find_next_rect(doc, entry.value, used_rects)
        )
        if rect is None:
            doc.close()
            raise RuntimeError(f"Impossibile localizzare nel PDF il tag {entry.tag}")
        page_index, fitz_rect = rect
        if not ocr_tokens:
            used_rects.add(_rect_key(page_index, fitz_rect))
        marks.append(_mark_from_rect(entry, page_index, fitz_rect))

    for mark in marks:
        page = doc[mark.page_index]
        rect = fitz.Rect(mark.x0, mark.y0, mark.x1, mark.y1)
        page.add_redact_annot(
            rect,
            text=mark.tag,
            fill=(1, 1, 1),
            text_color=(0, 0, 0),
            fontsize=mark.font_size,
        )

    for page in doc:
        page.apply_redactions()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(output_path)
    doc.close()
    return [asdict(mark) for mark in marks]


def write_restored_pdf(redacted_path: Path, output_path: Path, marks: list[dict]) -> None:
    try:
        import fitz
    except ImportError as exc:
        raise RuntimeError(
            "Per ripristinare PDF preservando il layout serve PyMuPDF. "
            "Installa le dipendenze con: pip install -r requirements.txt"
        ) from exc

    doc = fitz.open(redacted_path)
    typed_marks = [PdfMark(**mark) for mark in marks]

    for mark in typed_marks:
        page = doc[mark.page_index]
        rect = fitz.Rect(mark.x0, mark.y0, mark.x1, mark.y1)
        page.add_redact_annot(
            rect,
            text=mark.value,
            fill=(1, 1, 1),
            text_color=(0, 0, 0),
            fontsize=mark.font_size,
        )

    for page in doc:
        page.apply_redactions()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(output_path)
    doc.close()


def _find_next_rect(doc, value: str, used_rects: set[tuple[int, int, int, int, int]]):
    for page_index, page in enumerate(doc):
        rects = page.search_for(value)
        for rect in rects:
            key = _rect_key(page_index, rect)
            if key not in used_rects:
                return page_index, rect
    return None


def _find_ocr_rect(entry: RedactionEntry, ocr_tokens: list[dict[str, Any]] | None):
    if not ocr_tokens:
        return None
    try:
        import fitz
    except ImportError as exc:
        raise RuntimeError("Per redigere PDF OCR serve PyMuPDF.") from exc

    overlapping = [
        token
        for token in ocr_tokens
        if int(token["start"]) < entry.end and int(token["end"]) > entry.start
    ]
    if not overlapping:
        return None
    pages = {int(token["page_index"]) for token in overlapping}
    if len(pages) != 1:
        return None
    page_index = pages.pop()
    return page_index, fitz.Rect(
        min(float(token["x0"]) for token in overlapping),
        min(float(token["y0"]) for token in overlapping),
        max(float(token["x1"]) for token in overlapping),
        max(float(token["y1"]) for token in overlapping),
    )


def _rect_key(page_index: int, rect) -> tuple[int, int, int, int, int]:
    return (
        page_index,
        round(float(rect.x0) * 100),
        round(float(rect.y0) * 100),
        round(float(rect.x1) * 100),
        round(float(rect.y1) * 100),
    )


def _mark_from_rect(entry: RedactionEntry, page_index: int, rect) -> PdfMark:
    height = max(float(rect.y1 - rect.y0), 8.0)
    return PdfMark(
        tag=entry.tag,
        value=entry.value,
        page_index=page_index,
        x0=float(rect.x0),
        y0=float(rect.y0),
        x1=float(rect.x1),
        y1=float(rect.y1),
        font_size=max(min(height * 0.75, 11.0), 6.0),
    )

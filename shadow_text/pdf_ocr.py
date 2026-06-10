from __future__ import annotations

from dataclasses import asdict, dataclass
import os
from pathlib import Path


@dataclass(frozen=True)
class OcrToken:
    text: str
    start: int
    end: int
    page_index: int
    x0: float
    y0: float
    x1: float
    y1: float


def extract_pdf_ocr(path: Path) -> tuple[str, list[dict]]:
    try:
        import fitz
        from PIL import Image
        import pytesseract
        from pytesseract import Output
    except ImportError as exc:
        raise RuntimeError(
            "Il PDF non contiene testo estraibile. Per OCR installa le dipendenze "
            "con: pip install -r requirements.txt e installa Tesseract sul sistema."
        ) from exc

    zoom = float(os.environ.get("SHADOW_TEXT_OCR_ZOOM", "2.0"))
    language = os.environ.get("SHADOW_TEXT_OCR_LANG", "ita+eng")
    document = fitz.open(path)
    tokens: list[OcrToken] = []
    text_parts: list[str] = []
    cursor = 0

    try:
        for page_index, page in enumerate(document):
            pixmap = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
            image = Image.frombytes("RGB", [pixmap.width, pixmap.height], pixmap.samples)
            try:
                data = pytesseract.image_to_data(image, lang=language, output_type=Output.DICT)
            except pytesseract.TesseractNotFoundError as exc:
                raise RuntimeError(
                    "Tesseract non e installato o non e nel PATH. Installa Tesseract "
                    "e poi riavvia Shadow Text."
                ) from exc
            for index, raw_word in enumerate(data.get("text", [])):
                word = str(raw_word).strip()
                if not word:
                    continue
                if text_parts:
                    text_parts.append(" ")
                    cursor += 1
                start = cursor
                text_parts.append(word)
                cursor += len(word)
                tokens.append(
                    OcrToken(
                        text=word,
                        start=start,
                        end=cursor,
                        page_index=page_index,
                        x0=float(data["left"][index]) / zoom,
                        y0=float(data["top"][index]) / zoom,
                        x1=float(data["left"][index] + data["width"][index]) / zoom,
                        y1=float(data["top"][index] + data["height"][index]) / zoom,
                    )
                )
    finally:
        document.close()

    return "".join(text_parts), [asdict(token) for token in tokens]

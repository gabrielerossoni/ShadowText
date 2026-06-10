from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .office_io import OFFICE_SUFFIXES, read_office_text
from .pdf_ocr import extract_pdf_ocr

TEXT_SUFFIXES = {".txt", ".md", ".markdown"}
SUPPORTED_SUFFIXES = TEXT_SUFFIXES | {".pdf"} | OFFICE_SUFFIXES


@dataclass(frozen=True)
class Document:
    text: str
    output_suffix: str
    pdf_ocr_tokens: list[dict[str, Any]] | None = None


def read_document(path: Path, *, all_files: bool = False) -> Document:
    suffix = path.suffix.lower()
    if suffix in TEXT_SUFFIXES or (all_files and suffix != ".pdf"):
        return Document(text=path.read_text(encoding="utf-8"), output_suffix=suffix or ".txt")
    if suffix == ".pdf":
        text = _extract_pdf_text(path)
        if text.strip():
            return Document(text=text, output_suffix=".pdf")
        ocr_text, ocr_tokens = extract_pdf_ocr(path)
        return Document(text=ocr_text, output_suffix=".pdf", pdf_ocr_tokens=ocr_tokens)
    if suffix in OFFICE_SUFFIXES:
        return Document(text=read_office_text(path), output_suffix=suffix)
    raise ValueError(f"Formato non supportato: {path.name}")


def write_document(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def is_supported(path: Path, *, all_files: bool = False) -> bool:
    return path.is_file() and (all_files or path.suffix.lower() in SUPPORTED_SUFFIXES)


def _extract_pdf_text(path: Path) -> str:
    try:
        import fitz
    except ImportError as exc:
        raise RuntimeError(
            "Per leggere PDF serve PyMuPDF. Installa le dipendenze con: "
            "pip install -r requirements.txt"
        ) from exc

    doc = fitz.open(path)
    pages = [page.get_text("text") for page in doc]
    doc.close()
    return "\n\n".join(pages)

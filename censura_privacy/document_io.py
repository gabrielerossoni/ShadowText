from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


TEXT_SUFFIXES = {".txt", ".md", ".markdown"}
SUPPORTED_SUFFIXES = TEXT_SUFFIXES | {".pdf"}


@dataclass(frozen=True)
class Document:
    text: str
    output_suffix: str


def read_document(path: Path, *, all_files: bool = False) -> Document:
    suffix = path.suffix.lower()
    if suffix in TEXT_SUFFIXES or (all_files and suffix != ".pdf"):
        return Document(text=path.read_text(encoding="utf-8"), output_suffix=suffix or ".txt")
    if suffix == ".pdf":
        return Document(text=_extract_pdf_text(path), output_suffix=".pdf")
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

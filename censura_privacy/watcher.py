from __future__ import annotations

import argparse
from datetime import datetime
import json
import sys
import time
from pathlib import Path
from typing import Callable
import importlib.util
import os

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    __package__ = "censura_privacy"

from .audit import write_audit
from .detectors import CombinedDetector, LazyOpfDetector, RegexDetector
from .document_io import is_supported, read_document, write_document
from .engine import (
    build_mapping,
    find_mapping_for_redacted_file,
    load_mapping,
    redact_text,
    restore_text,
    write_mapping,
)
from .memory import add_always_redact, add_never_redact, apply_memory, load_memory
from .pdf_redaction import write_redacted_pdf, write_restored_pdf


PACKAGE_DIR = Path(__file__).resolve().parent
ROOT = Path.cwd().parent if Path.cwd().resolve() == PACKAGE_DIR else Path.cwd()
DEFAULT_CENSURA = ROOT / "Censura"
DEFAULT_DATI = ROOT / "Dati"
DEFAULT_RIUNIONE = ROOT / "Riunione"
DEFAULT_GPU_OVER_MB = -1.0


def process_for_censura(
    path: Path,
    *,
    data_dir: Path,
    detector,
    all_files: bool = False,
    memory_path: Path | None = None,
    fast_pdf: bool = False,
    gpu_over_mb: float = DEFAULT_GPU_OVER_MB,
    logger: Callable[[str], None] | None = None,
) -> Path | None:
    if _is_generated(path) or not is_supported(path, all_files=all_files):
        return None

    document = read_document(path, all_files=all_files)
    memory_path = memory_path or data_dir / "memoria.json"
    memory = load_memory(memory_path)
    active_detector = RegexDetector() if fast_pdf and path.suffix.lower() == ".pdf" else detector
    spans = apply_memory(
        document.text,
        _detect_for_file(active_detector, document.text, path, gpu_over_mb=gpu_over_mb),
        memory,
    )
    redacted, entries = redact_text(document.text, spans)
    _log(logger, f"Dati sensibili trovati: {len(entries)}")
    redacted_path = path.with_name(f"{path.stem}.censurato{document.output_suffix}")
    pdf_marks = []
    if path.suffix.lower() == ".pdf":
        pdf_marks = write_redacted_pdf(path, redacted_path, entries)
    else:
        write_document(redacted_path, redacted)

    mapping = build_mapping(
        source_filename=path.name,
        redacted_filename=redacted_path.name,
        entries=entries,
    )
    if pdf_marks:
        mapping["pdf_marks"] = pdf_marks
    mapping_path = write_mapping(data_dir, mapping)
    archive_path = _archive_original(path, data_dir)
    _log(logger, f"File censurato pronto: {redacted_path.name}")
    write_audit(
        data_dir,
        "censor",
        {
            "source_filename": mapping["source_filename"],
            "redacted_filename": mapping["redacted_filename"],
            "mapping_filename": mapping_path.name,
            "original_archive": str(archive_path.relative_to(data_dir)),
            "entries_count": len(entries),
            "memory_always_redact_count": len(memory.get("always_redact", [])),
            "memory_never_redact_count": len(memory.get("never_redact", [])),
        },
    )
    return redacted_path


def process_for_riunione(
    path: Path,
    *,
    data_dir: Path,
    logger: Callable[[str], None] | None = None,
) -> Path | None:
    if not path.is_file() or ".censurato" not in path.name:
        return None

    mapping_path = find_mapping_for_redacted_file(data_dir, path.name)
    if mapping_path is None:
        raise FileNotFoundError(f"Mapping JSON non trovato per {path.name}")

    mapping = load_mapping(mapping_path)
    restored_name = path.name.replace(".censurato", ".ripristinato", 1)
    restored_path = path.with_name(restored_name)
    if path.suffix.lower() == ".pdf" and mapping.get("pdf_marks"):
        write_restored_pdf(path, restored_path, mapping["pdf_marks"])
    else:
        document = read_document(path, all_files=True)
        restored = restore_text(document.text, mapping)
        write_document(restored_path, restored)
    write_audit(
        data_dir,
        "restore",
        {
            "redacted_filename": path.name,
            "restored_filename": restored_path.name,
            "mapping_filename": mapping_path.name,
        },
    )
    path.unlink()
    _log(logger, f"File ripristinato pronto: {restored_path.name}")
    return restored_path


def watch(
    *,
    censura_dir: Path,
    data_dir: Path,
    riunione_dir: Path,
    detector,
    interval: float,
    all_files: bool,
    fast_pdf: bool,
    gpu_over_mb: float,
) -> None:
    censura_dir.mkdir(parents=True, exist_ok=True)
    data_dir.mkdir(parents=True, exist_ok=True)
    riunione_dir.mkdir(parents=True, exist_ok=True)
    seen: dict[Path, tuple[int, int]] = {}

    _console_log("Watcher attivo")
    _console_log(f"Censura={censura_dir}")
    _console_log(f"Riunione={riunione_dir}")
    while True:
        _scan_censura(censura_dir, data_dir, detector, all_files, fast_pdf, gpu_over_mb, seen)
        _scan_riunione(riunione_dir, data_dir, seen)
        time.sleep(interval)


def build_detector(*, device: str, regex_only: bool):
    if regex_only:
        return RegexDetector()
    return CombinedDetector([RegexDetector(), LazyOpfDetector(default_device=device)])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Censura file in Censura e ripristina file censurati in Riunione."
    )
    parser.add_argument(
        "mode",
        choices=[
            "watch",
            "censor",
            "restore",
            "remember-redact",
            "remember-company",
            "remember-keep",
            "doctor-cuda",
            "show-memory",
        ],
        nargs="?",
        default="watch",
    )
    parser.add_argument("--censura-dir", type=Path, default=DEFAULT_CENSURA)
    parser.add_argument("--dati-dir", type=Path, default=DEFAULT_DATI)
    parser.add_argument("--riunione-dir", type=Path, default=DEFAULT_RIUNIONE)
    parser.add_argument("--file", type=Path, help="File singolo per mode censor/restore")
    parser.add_argument("--device", choices=["cpu", "cuda"], default="cpu")
    parser.add_argument("--gpu-over-mb", type=float, default=DEFAULT_GPU_OVER_MB)
    parser.add_argument("--interval", type=float, default=2.0)
    parser.add_argument("--regex-only", action="store_true")
    parser.add_argument("--fast-pdf", action="store_true")
    parser.add_argument("--all-files", action="store_true")
    parser.add_argument("--text", help="Testo da ricordare per remember-redact/remember-keep")
    parser.add_argument("--label", help="Label OPF da usare con remember-redact")
    args = parser.parse_args(argv)

    memory_path = args.dati_dir / "memoria.json"
    if args.mode == "remember-redact":
        if not args.text or not args.label:
            raise SystemExit("--text e --label sono richiesti con remember-redact")
        add_always_redact(memory_path, text=args.text, label=args.label)
        write_audit(
            args.dati_dir,
            "memory_add",
            {"rule": "always_redact", "text": args.text, "label": args.label},
        )
        print(f"Memorizzato: censura sempre {args.text!r} come {args.label}")
        return 0

    if args.mode == "remember-company":
        if not args.text:
            raise SystemExit("--text e richiesto con remember-company")
        add_always_redact(memory_path, text=args.text, label="company")
        write_audit(
            args.dati_dir,
            "memory_add",
            {"rule": "always_redact", "text": args.text, "label": "company"},
        )
        print(f"Memorizzato: censura sempre azienda {args.text!r}")
        return 0

    if args.mode == "remember-keep":
        if not args.text:
            raise SystemExit("--text e richiesto con remember-keep")
        add_never_redact(memory_path, text=args.text)
        write_audit(
            args.dati_dir,
            "memory_add",
            {"rule": "never_redact", "text": args.text},
        )
        print(f"Memorizzato: non censurare mai {args.text!r}")
        return 0

    if args.mode == "show-memory":
        print(json.dumps(load_memory(memory_path), ensure_ascii=False, indent=2))
        return 0

    if args.mode == "doctor-cuda":
        print(_cuda_diagnostics())
        return 0

    if args.mode == "restore":
        if args.file is None:
            raise SystemExit("--file e richiesto con mode restore")
        process_for_riunione(args.file, data_dir=args.dati_dir)
        return 0

    detector = build_detector(device=args.device, regex_only=args.regex_only)
    if args.mode == "censor":
        if args.file is None:
            raise SystemExit("--file e richiesto con mode censor")
        process_for_censura(
            args.file,
            data_dir=args.dati_dir,
            detector=detector,
            all_files=args.all_files,
            memory_path=memory_path,
            fast_pdf=args.fast_pdf,
            gpu_over_mb=args.gpu_over_mb,
        )
        return 0

    watch(
        censura_dir=args.censura_dir,
        data_dir=args.dati_dir,
        riunione_dir=args.riunione_dir,
        detector=detector,
        interval=args.interval,
        all_files=args.all_files,
        fast_pdf=args.fast_pdf,
        gpu_over_mb=args.gpu_over_mb,
    )
    return 0


def _scan_censura(
    censura_dir: Path,
    data_dir: Path,
    detector,
    all_files: bool,
    fast_pdf: bool,
    gpu_over_mb: float,
    seen,
) -> None:
    for path in censura_dir.iterdir():
        if not _should_process(path, seen):
            continue
        try:
            if _is_generated(path):
                _console_log(
                    f"Ignorato in Censura: {path.name} e gia un file generato; "
                    "se e .censurato spostalo in Riunione."
                )
                continue
            start = time.perf_counter()
            _console_log(f"Censura: {path.name} ({path.stat().st_size} byte)")
            redacted = process_for_censura(
                path,
                data_dir=data_dir,
                detector=detector,
                all_files=all_files,
                fast_pdf=fast_pdf,
                gpu_over_mb=gpu_over_mb,
                logger=_console_log,
            )
            if redacted is not None:
                elapsed = time.perf_counter() - start
                _console_log(f"OK censura: {redacted.name} ({elapsed:.1f}s)")
        except Exception as exc:
            _console_log(f"ERRORE censura {path.name}: {exc}")


def _scan_riunione(riunione_dir: Path, data_dir: Path, seen) -> None:
    for path in riunione_dir.iterdir():
        if not _should_process(path, seen):
            continue
        try:
            if ".censurato" not in path.name:
                _console_log(f"Ignorato in Riunione: {path.name} non e un file .censurato.*")
                continue
            _console_log(f"Ripristino: {path.name} ({path.stat().st_size} byte)")
            restored = process_for_riunione(path, data_dir=data_dir, logger=_console_log)
            if restored is not None:
                _console_log(f"OK ripristino: {restored.name}")
        except Exception as exc:
            _console_log(f"ERRORE ripristino {path.name}: {exc}")


def _should_process(path: Path, seen: dict[Path, tuple[int, int]]) -> bool:
    if not path.is_file():
        return False
    stat = path.stat()
    fingerprint = (stat.st_size, stat.st_mtime_ns)
    if seen.get(path) == fingerprint:
        return False
    seen[path] = fingerprint
    return True


def _is_generated(path: Path) -> bool:
    return ".censurato" in path.name or ".ripristinato" in path.name


def _archive_original(path: Path, data_dir: Path) -> Path:
    archive_dir = data_dir / "Originali"
    archive_dir.mkdir(parents=True, exist_ok=True)
    target = archive_dir / path.name
    if target.exists():
        index = 2
        while True:
            candidate = archive_dir / f"{path.stem}.{index}{path.suffix}"
            if not candidate.exists():
                target = candidate
                break
            index += 1
    path.replace(target)
    return target


def _detect_for_file(detector, text: str, path: Path, *, gpu_over_mb: float) -> list:
    should_try_cuda = gpu_over_mb < 0 or (
        gpu_over_mb > 0 and path.stat().st_size >= gpu_over_mb * 1024 * 1024
    )
    if should_try_cuda:
        if hasattr(detector, "detect_with_device"):
            if gpu_over_mb < 0:
                _console_log(f"Provo GPU/CUDA per {path.name}")
            else:
                _console_log(f"File sopra {gpu_over_mb:g} MB: provo GPU/CUDA per {path.name}")
            return detector.detect_with_device(text, "cuda")
    return detector.detect(text)


def _log(logger: Callable[[str], None] | None, message: str) -> None:
    if logger is not None:
        logger(message)


def _console_log(message: str) -> None:
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] {message}", flush=True)


def _cuda_diagnostics() -> str:
    lines = [f"Python: {sys.executable}"]
    try:
        import torch
    except ImportError as exc:
        lines.append(f"PyTorch: non installato ({exc})")
        return "\n".join(lines)

    lines.append(f"PyTorch: {torch.__version__}")
    lines.append(f"PyTorch CUDA build: {torch.version.cuda}")
    lines.append(f"torch.cuda.is_available(): {torch.cuda.is_available()}")
    lines.append(f"torch.cuda.device_count(): {torch.cuda.device_count()}")
    lines.append(f"triton installed: {importlib.util.find_spec('triton') is not None}")
    lines.append(f"OPF_MOE_TRITON: {os.environ.get('OPF_MOE_TRITON')}")
    if torch.cuda.is_available():
        lines.append(f"GPU 0: {torch.cuda.get_device_name(0)}")
        if os.environ.get("OPF_MOE_TRITON") and importlib.util.find_spec("triton") is None:
            lines.append(
                "Nota: OPF_MOE_TRITON e impostato ma triton non e installato; "
                "il watcher lo disattivera automaticamente prima di usare OPF su CUDA."
            )
    else:
        lines.append(
            "Se nvidia-smi vede la GPU ma qui CUDA e False, installa PyTorch con supporto CUDA."
        )
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())

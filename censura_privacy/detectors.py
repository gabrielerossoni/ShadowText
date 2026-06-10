from __future__ import annotations

import importlib.util
import os
import re
from typing import Callable, Iterable, Protocol

from .engine import Span


class Detector(Protocol):
    def detect(self, text: str) -> list[Span]:
        ...


class RegexDetector:
    PATTERNS = (
        (
            "company",
            re.compile(
                r"\b[A-ZÀ-ÖØ-Þ][\wÀ-ÖØ-öø-ÿ&'.-]+"
                r"(?:\s+[A-ZÀ-ÖØ-Þ][\wÀ-ÖØ-öø-ÿ&'.-]+){0,5}"
                r"\s+(?i:S\.?\s*r\.?\s*l\.?|S\.?\s*p\.?\s*A\.?|SAS|SNC|SRL|SPA|LLC|Ltd\.?|Limited|Inc\.?|Corp\.?|GmbH)"
                r"(?=$|\s|[,.);:])",
            ),
        ),
        ("iban", re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b", re.IGNORECASE)),
        ("private_email", re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)),
        ("private_phone", re.compile(r"(?<!\w)(?:\+?\d[\d .()/-]{7,}\d)(?!\w)")),
        ("private_url", re.compile(r"\bhttps?://[^\s<>()]+", re.IGNORECASE)),
    )

    def detect(self, text: str) -> list[Span]:
        spans: list[Span] = []
        for label, pattern in self.PATTERNS:
            for match in pattern.finditer(text):
                spans.append(
                    Span(
                        label=label,
                        start=match.start(),
                        end=match.end(),
                        text=match.group(0),
                    )
                )
        return spans


class OpfDetector:
    def __init__(self, *, device: str = "cpu") -> None:
        self._device = device
        if device == "cuda":
            self._assert_cuda_available()
            _maybe_disable_triton()
        try:
            from opf import OPF
        except ImportError as exc:
            raise RuntimeError(
                "Il package openai/privacy-filter non e installato. "
                "Installa le dipendenze con: pip install -r requirements.txt"
            ) from exc
        try:
            self._opf = OPF(device=device, output_mode="typed")
        except Exception as exc:
            if device == "cuda" and _is_triton_error(exc) and _maybe_disable_triton():
                self._opf = OPF(device=device, output_mode="typed")
            else:
                raise

    def _assert_cuda_available(self) -> None:
        try:
            import torch
        except ImportError as exc:
            raise RuntimeError("PyTorch non e installato in questo Python") from exc
        if torch.version.cuda is None:
            raise RuntimeError(
                "PyTorch installato e CPU-only: torch.version.cuda = None"
            )
        if not torch.cuda.is_available():
            raise RuntimeError(
                "torch.cuda.is_available() = False "
                f"(torch={torch.__version__}, torch CUDA={torch.version.cuda})"
            )

    def detect(self, text: str) -> list[Span]:
        result = self._opf.redact(text)
        payload = result.to_dict() if hasattr(result, "to_dict") else result
        spans = []
        for item in payload.get("detected_spans", []):
            spans.append(
                Span(
                    label=str(item["label"]),
                    start=int(item["start"]),
                    end=int(item["end"]),
                    text=str(item.get("text", text[int(item["start"]) : int(item["end"])])),
                )
            )
        return spans


class LazyOpfDetector:
    def __init__(self, *, default_device: str = "cpu", fallback_to_cpu: bool = True) -> None:
        self._default_device = default_device
        self._fallback_to_cpu = fallback_to_cpu
        self._detectors: dict[str, OpfDetector] = {}

    def detect(self, text: str) -> list[Span]:
        return self.detect_with_device(text, self._default_device)

    def detect_with_device(self, text: str, device: str) -> list[Span]:
        try:
            detector = self._get_detector(device)
            return detector.detect(text)
        except Exception as exc:
            if device == "cuda" and self._fallback_to_cpu:
                print(f"CUDA non disponibile o non utilizzabile ({exc}); fallback su CPU.")
                detector = self._get_detector("cpu")
                return detector.detect(text)
            raise

    def _get_detector(self, device: str) -> OpfDetector:
        if device not in self._detectors:
            self._detectors[device] = OpfDetector(device=device)
        return self._detectors[device]


class CombinedDetector:
    def __init__(self, detectors: Iterable[Detector]) -> None:
        self._detectors = list(detectors)

    def detect(self, text: str) -> list[Span]:
        spans: list[Span] = []
        for detector in self._detectors:
            spans.extend(detector.detect(text))
        return spans

    def detect_with_device(self, text: str, device: str) -> list[Span]:
        spans: list[Span] = []
        for detector in self._detectors:
            if hasattr(detector, "detect_with_device"):
                spans.extend(detector.detect_with_device(text, device))
            else:
                spans.extend(detector.detect(text))
        return spans


def _maybe_disable_triton(
    find_spec: Callable[[str], object | None] = importlib.util.find_spec,
) -> bool:
    if os.environ.get("OPF_MOE_TRITON") is None:
        return False
    if find_spec("triton") is not None:
        return False
    os.environ.pop("OPF_MOE_TRITON", None)
    print("OPF_MOE_TRITON disattivato: triton non e installato.")
    return True


def _is_triton_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return "triton" in message or "opf_moe_triton" in message

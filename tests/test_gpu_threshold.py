import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from censura_privacy.engine import Span
from censura_privacy.watcher import process_for_censura


class DeviceRecordingDetector:
    def __init__(self) -> None:
        self.devices: list[str | None] = []

    def detect(self, text: str) -> list[Span]:
        self.devices.append(None)
        return []

    def detect_with_device(self, text: str, device: str) -> list[Span]:
        self.devices.append(device)
        return []


class GpuThresholdTests(unittest.TestCase):
    def test_large_file_uses_cuda_with_default_threshold(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data_dir = root / "Dati"
            source = root / "Censura" / "grande.txt"
            source.parent.mkdir()
            source.write_text("A" * (2 * 1024 * 1024), encoding="utf-8")
            detector = DeviceRecordingDetector()

            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                process_for_censura(
                    source,
                    data_dir=data_dir,
                    detector=detector,
                )

            self.assertEqual(detector.devices, ["cuda"])

    def test_large_file_uses_cuda_when_over_threshold(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data_dir = root / "Dati"
            source = root / "Censura" / "grande.txt"
            source.parent.mkdir()
            source.write_text("A" * 2048, encoding="utf-8")
            detector = DeviceRecordingDetector()

            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                process_for_censura(
                    source,
                    data_dir=data_dir,
                    detector=detector,
                    gpu_over_mb=0.001,
                )

            self.assertEqual(detector.devices, ["cuda"])

    def test_small_file_uses_cuda_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data_dir = root / "Dati"
            source = root / "Censura" / "piccolo.txt"
            source.parent.mkdir()
            source.write_text("piccolo", encoding="utf-8")
            detector = DeviceRecordingDetector()

            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                process_for_censura(
                    source,
                    data_dir=data_dir,
                    detector=detector,
                )

            self.assertEqual(detector.devices, ["cuda"])

    def test_gpu_can_be_disabled_with_zero_threshold(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data_dir = root / "Dati"
            source = root / "Censura" / "piccolo.txt"
            source.parent.mkdir()
            source.write_text("piccolo", encoding="utf-8")
            detector = DeviceRecordingDetector()

            process_for_censura(
                source,
                data_dir=data_dir,
                detector=detector,
                gpu_over_mb=0,
            )

            self.assertEqual(detector.devices, [None])


if __name__ == "__main__":
    unittest.main()

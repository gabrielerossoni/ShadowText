import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from shadow_text.watcher import _scan_censura, _scan_riunione


class WatcherLogTests(unittest.TestCase):
    def test_censura_logs_ignored_already_redacted_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data_dir = root / "Dati"
            censura_dir = root / "Censura"
            data_dir.mkdir()
            censura_dir.mkdir()
            (censura_dir / "documento.censurato.pdf").write_bytes(b"%PDF fake")
            output = io.StringIO()

            with contextlib.redirect_stdout(output):
                _scan_censura(
                    censura_dir,
                    data_dir,
                    detector=_FailingDetector(),
                    all_files=False,
                    gpu_over_mb=0,
                    seen={},
                )

            self.assertIn("Ignorato in Censura", output.getvalue())
            self.assertIn("spostalo in Riunione", output.getvalue())
            self.assertNotIn("Dati sensibili trovati", output.getvalue())
            self.assertNotIn("OK censura", output.getvalue())

    def test_riunione_logs_ignored_plain_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data_dir = root / "Dati"
            riunione_dir = root / "Riunione"
            data_dir.mkdir()
            riunione_dir.mkdir()
            (riunione_dir / "documento.pdf").write_bytes(b"%PDF fake")
            output = io.StringIO()

            with contextlib.redirect_stdout(output):
                _scan_riunione(riunione_dir, data_dir, {})

            self.assertIn("Ignorato in Riunione", output.getvalue())
            self.assertIn("non e un file .censurato", output.getvalue())


class _FailingDetector:
    def detect(self, _text):
        raise AssertionError("detector should not be called")


if __name__ == "__main__":
    unittest.main()

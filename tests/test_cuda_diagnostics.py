import contextlib
import io
import os
import unittest

from censura_privacy.detectors import LazyOpfDetector, OpfDetector, _maybe_disable_triton


class CudaDiagnosticsTests(unittest.TestCase):
    def test_cuda_fallback_prints_exception_reason(self):
        original_get_detector = LazyOpfDetector._get_detector

        def fake_get_detector(self, device):
            if device == "cuda":
                raise RuntimeError("Torch CUDA build missing")
            return _NoopDetector()

        try:
            LazyOpfDetector._get_detector = fake_get_detector
            output = io.StringIO()
            detector = LazyOpfDetector(default_device="cuda")

            with contextlib.redirect_stdout(output):
                detector.detect("hello")

            self.assertIn("Torch CUDA build missing", output.getvalue())
            self.assertIn("fallback su CPU", output.getvalue())
        finally:
            LazyOpfDetector._get_detector = original_get_detector

    def test_opf_detector_rejects_cuda_when_torch_has_no_cuda(self):
        original_assert = OpfDetector._assert_cuda_available

        def fake_assert(self):
            raise RuntimeError("torch.cuda.is_available() = False")

        try:
            OpfDetector._assert_cuda_available = fake_assert
            with self.assertRaisesRegex(RuntimeError, "torch.cuda.is_available"):
                OpfDetector(device="cuda")
        finally:
            OpfDetector._assert_cuda_available = original_assert

    def test_triton_env_is_forced_false_when_triton_is_missing(self):
        original_value = os.environ.get("OPF_MOE_TRITON")
        os.environ["OPF_MOE_TRITON"] = "1"
        try:
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                changed = _maybe_disable_triton(lambda _name: None)

            self.assertTrue(changed)
            self.assertEqual(os.environ["OPF_MOE_TRITON"], "0")
        finally:
            if original_value is None:
                os.environ.pop("OPF_MOE_TRITON", None)
            else:
                os.environ["OPF_MOE_TRITON"] = original_value

    def test_triton_env_is_set_false_when_unset_and_triton_is_missing(self):
        original_value = os.environ.get("OPF_MOE_TRITON")
        os.environ.pop("OPF_MOE_TRITON", None)
        try:
            changed = _maybe_disable_triton(lambda _name: None)

            self.assertTrue(changed)
            self.assertEqual(os.environ["OPF_MOE_TRITON"], "0")
        finally:
            if original_value is None:
                os.environ.pop("OPF_MOE_TRITON", None)
            else:
                os.environ["OPF_MOE_TRITON"] = original_value

    def test_triton_env_is_kept_when_triton_exists(self):
        original_value = os.environ.get("OPF_MOE_TRITON")
        os.environ["OPF_MOE_TRITON"] = "1"
        try:
            changed = _maybe_disable_triton(lambda _name: True)

            self.assertFalse(changed)
            self.assertEqual(os.environ["OPF_MOE_TRITON"], "1")
        finally:
            if original_value is None:
                os.environ.pop("OPF_MOE_TRITON", None)
            else:
                os.environ["OPF_MOE_TRITON"] = original_value


class _NoopDetector:
    def detect(self, text):
        return []


if __name__ == "__main__":
    unittest.main()

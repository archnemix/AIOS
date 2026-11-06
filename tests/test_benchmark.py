import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from iso_benchmark.measure import check_context, run_comparison


class FakeClient:
    def __init__(self, truncated=False):
        self.truncated = truncated
        self.calls = 0

    def stream_completion(self, prompt):
        self.calls += 1
        return {"ttft_seconds": self.calls, "wall_seconds": self.calls + 1,
                "prompt_tokens_per_second": 100, "output_tokens_per_second": 10,
                "prompt_tokens": 50, "output_tokens": 32}

    def request(self, path, payload, timeout=120):
        if path == "/tokenize":
            return {"tokens": [42]}
        return {"tokens_evaluated": len(payload["prompt"]), "truncated": self.truncated}


class BenchmarkTests(unittest.TestCase):
    def test_comparison_warms_and_records_three_samples(self):
        host, guest = FakeClient(), FakeClient()
        report = run_comparison(host, guest)
        self.assertEqual(host.calls, 4)
        self.assertEqual(guest.calls, 4)
        self.assertEqual(len(report["samples"]["github_linux"]), 3)
        self.assertEqual(report["medians"]["aios_vm"]["ttft_seconds"], 3)

    def test_context_checks_tokens_and_truncation(self):
        self.assertTrue(check_context(FakeClient(), 8000)["passed"])
        self.assertFalse(check_context(FakeClient(truncated=True), 8000)["passed"])

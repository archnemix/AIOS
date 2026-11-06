import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from iso_benchmark.context import complete, shared_prefix


class Client:
    def __init__(self, truncate=False, reuse=True):
        self.truncate, self.reuse = truncate, reuse

    def request(self, path, payload, timeout=120):
        if path == '/tokenize':
            return {'tokens': [42, 17]}
        n = len(payload['prompt'])
        processed = 16 if payload['cache_prompt'] and self.reuse else n
        return {'tokens_evaluated': n, 'truncated': self.truncate, 'tokens_predicted': 1,
                'timings': {'prompt_n': processed, 'prompt_ms': 1}}


class ContextBenchmarkTests(unittest.TestCase):
    def test_reuse_is_confirmed_by_actual_prompt_work(self):
        result = shared_prefix(Client())
        self.assertEqual(result['cold']['prompt_tokens_processed'], 4112)
        self.assertEqual(result['cached']['prompt_tokens_processed'], 16)

    def test_failure_on_truncation_or_missing_reuse(self):
        with self.assertRaises(RuntimeError):
            complete(Client(truncate=True), [1], False)
        with self.assertRaises(RuntimeError):
            shared_prefix(Client(reuse=False))

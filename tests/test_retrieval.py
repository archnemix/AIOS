import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
spec = importlib.util.spec_from_file_location('retrieval_probe', ROOT / 'scripts/os_tuning/retrieval.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class FakeClient:
    def __init__(self, answer='mango', truncated=False):
        self.answer, self.truncated = answer, truncated

    def request(self, path, payload, timeout=120):
        if path == '/tokenize':
            return {'tokens': [1, 2, 3]}
        return {'content': self.answer, 'tokens_evaluated': len(payload['prompt']),
                'truncated': self.truncated}


class RetrievalTests(unittest.TestCase):
    def test_exact_length_and_word_matching(self):
        self.assertTrue(module.probe(FakeClient('The word is mango.'), 256)['correct'])
        self.assertFalse(module.probe(FakeClient('mangoes'), 256)['correct'])
        self.assertEqual(module.probe(FakeClient(), 12000)['evaluated'], 12000)

    def test_reject_truncated_prompt(self):
        with self.assertRaises(RuntimeError):
            module.probe(FakeClient(truncated=True), 256)

import importlib.util
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
spec = importlib.util.spec_from_file_location('decode_cache', ROOT / 'scripts/os_tuning/decode_cache.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class DecodeCacheTests(unittest.TestCase):
    def test_modes_preserve_explicit_baseline(self):
        modes = dict(module.MODES)
        self.assertEqual(modes['baseline'], [])
        self.assertEqual(modes['q8-key'], ['--cache-type-k', 'q8_0'])
        self.assertIn('--flash-attn', modes['flash-q8'])

    def test_cpu_accounting_is_nonnegative(self):
        self.assertGreaterEqual(module.cpu_seconds(__import__('os').getpid()), 0)

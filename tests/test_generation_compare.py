import importlib.util
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
spec = importlib.util.spec_from_file_location('generation_compare', ROOT / 'scripts/os_tuning/generation_compare.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class GenerationCompareTests(unittest.TestCase):
    def test_profile_counts_fit_guest(self):
        for cpus in (2, 4):
            modes = module.profiles(cpus)
            self.assertEqual(len({name for name, _, _ in modes}), len(modes))
            self.assertTrue(all(1 <= threads <= cpus and poll in (0, 50, 100)
                                for _, threads, poll in modes))
            self.assertTrue(any(threads == cpus and poll == 50 for _, threads, poll in modes))

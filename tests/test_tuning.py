import importlib.util
import pathlib
import unittest

PATH = pathlib.Path(__file__).resolve().parents[1] / 'scripts/tuning/measure.py'
spec = importlib.util.spec_from_file_location('tuning_measure', PATH)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class TuningTests(unittest.TestCase):
    def test_features_are_intersection_across_cpus(self):
        info = 'flags : sse4_2 avx avx2 fma f16c bmi2\n\nflags : avx fma\n'
        self.assertEqual(module.cpu_flags(info), {'avx', 'fma'})
        self.assertEqual(module.cpu_flags(''), set())

    def test_names_do_not_match_substrings(self):
        self.assertNotIn('avx2', module.cpu_flags('flags : avx2extra\n'))

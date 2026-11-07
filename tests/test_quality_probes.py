import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'scripts'))
from os_tuning.quality_probes import PROBES, first_word


class QualityProbeTests(unittest.TestCase):
    def test_first_word_is_case_insensitive_and_handles_punctuation(self):
        self.assertEqual(first_word('  "Paris" is the capital.'), 'paris')
        self.assertEqual(first_word(''), '')
        self.assertEqual(first_word('12 months'), '12')

    def test_probes_are_well_formed(self):
        self.assertEqual(len(PROBES), 10)
        self.assertTrue(all(question and accepted for question, accepted in PROBES))

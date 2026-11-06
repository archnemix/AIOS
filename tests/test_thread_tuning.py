import json
import pathlib
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
PICKER = ROOT / 'os/buildroot/board/aios/rootfs-overlay/usr/libexec/aios-pick-threads'


class TuningPickerTests(unittest.TestCase):
    def pick(self, rows, candidates='1,2,4'):
        with tempfile.TemporaryDirectory() as directory:
            data = pathlib.Path(directory) / 'results.jsonl'
            data.write_text('\n'.join(json.dumps(row) for row in rows) + '\n')
            return subprocess.run([str(PICKER), str(data), candidates], text=True, capture_output=True)

    def test_pick_fastest_only_after_meaningful_gain(self):
        rows = [{'n_threads': 1, 'n_gen': 32, 'n_prompt': 0, 'avg_ts': 100},
                {'n_threads': 2, 'n_gen': 32, 'n_prompt': 0, 'avg_ts': 101},
                {'n_threads': 4, 'n_gen': 32, 'n_prompt': 0, 'avg_ts': 110}]
        self.assertEqual(self.pick(rows).stdout.strip(), '4')
        self.assertEqual(self.pick(rows[:2]).stdout.strip(), '1')

    def test_reject_unrequested_or_invalid_measurements(self):
        rows = [{'n_threads': 999, 'n_gen': 32, 'n_prompt': 0, 'avg_ts': 999},
                {'n_threads': 2, 'n_gen': 8, 'n_prompt': 0, 'avg_ts': 30}]
        self.assertNotEqual(self.pick(rows).returncode, 0)

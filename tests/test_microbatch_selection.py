import pathlib
import subprocess
import unittest

SELECTOR = pathlib.Path(__file__).resolve().parents[1] / 'os/buildroot/board/aios/rootfs-overlay/usr/libexec/aios-select-ubatch'


class MicrobatchSelectionTests(unittest.TestCase):
    def test_measured_iso_profile(self):
        self.assertEqual(subprocess.check_output([str(SELECTOR), 'embedded', 'avx2', '2'], text=True).strip(), '128')

    def test_other_profiles_keep_upstream_default(self):
        for args in (('external', 'avx2', '2'), ('embedded', 'portable', '2'),
                     ('embedded', 'avx2', '1'), ('embedded', 'avx2', '4')):
            with self.subTest(args=args):
                self.assertEqual(subprocess.check_output([str(SELECTOR), *args], text=True).strip(), 'auto')

    def test_requires_all_inputs(self):
        self.assertNotEqual(subprocess.run([str(SELECTOR)], check=False).returncode, 0)

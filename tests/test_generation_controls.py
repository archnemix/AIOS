import pathlib
import subprocess
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


class GenerationControlTests(unittest.TestCase):
    def test_configuration_defaults_and_validated_cases(self):
        config = (ROOT / 'os/buildroot/board/aios/rootfs-overlay/etc/aios/server.conf').read_text()
        init = (ROOT / 'os/buildroot/board/aios/rootfs-overlay/etc/init.d/S95aios').read_text()
        self.assertIn('AIOS_BATCH_THREADS=auto', config)
        self.assertIn('AIOS_POLL=auto', config)
        self.assertIn('1|2|4|8) set -- "$@" --threads-batch', init)
        self.assertIn('0|50|100) set -- "$@" --poll', init)
        subprocess.run(['sh', '-n', str(ROOT / 'os/buildroot/board/aios/rootfs-overlay/etc/init.d/S95aios')], check=True)

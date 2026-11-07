import pathlib
import subprocess
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
OVERLAY = ROOT / 'os/buildroot/board/aios/rootfs-overlay'


class CacheConfigTests(unittest.TestCase):
    def test_cache_is_opt_in_and_validation_is_restricted(self):
        config = (OVERLAY / 'etc/aios/server.conf').read_text()
        init = (OVERLAY / 'etc/init.d/S95aios').read_text()
        self.assertIn('AIOS_CACHE_K=f16', config)
        self.assertIn('aios.k-cache=q8_0) AIOS_CACHE_K=q8_0', init)
        self.assertIn('q8_0) set -- "$@" --cache-type-k q8_0', init)
        self.assertIn('invalid key-cache type', init)
        subprocess.run(['sh', '-n', str(OVERLAY / 'etc/init.d/S95aios')], check=True)

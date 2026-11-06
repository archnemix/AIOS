import pathlib
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
OVERLAY = ROOT / "os/buildroot/board/aios/rootfs-overlay"
VALIDATOR = OVERLAY / "usr/libexec/aios-validate-key"


class KeyValidationTests(unittest.TestCase):
    def validate(self, value):
        with tempfile.TemporaryDirectory() as directory:
            key = pathlib.Path(directory) / "api.key"
            key.write_text(value)
            return subprocess.run([str(VALIDATOR), str(key)], capture_output=True).returncode

    def test_accepts_one_long_url_safe_key(self):
        self.assertEqual(self.validate("a" * 32 + "\n"), 0)

    def test_rejects_keys_that_could_disable_or_weaken_auth(self):
        for key in ("", "\n", "short\n", "a" * 32 + "\n\n", "a" * 31 + "!\n", "a" * 129):
            with self.subTest(key=repr(key)):
                self.assertNotEqual(self.validate(key), 0)

    def test_init_scripts_parse(self):
        for script in (VALIDATOR, OVERLAY / "etc/init.d/S95aios", ROOT / "scripts/build-image.sh"):
            subprocess.run(["sh", "-n", str(script)], check=True)

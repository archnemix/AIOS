import os
import pathlib
import re
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SOURCE = ROOT / "os/buildroot/package/aios-keygen/src/keygen.c"


class KeygenTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        cls.binary = pathlib.Path(cls.directory.name) / "keygen"
        subprocess.run(["cc", "-std=c11", "-D_GNU_SOURCE", "-Wall", "-Wextra", "-Werror",
                        str(SOURCE), "-o", str(cls.binary)], check=True)

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    def test_generates_private_key_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "key"
            args = [str(self.binary), str(path), str(os.getuid())]
            subprocess.run(args, check=True)
            token = path.read_text()
            self.assertRegex(token, r"^[0-9a-f]{64}\n$")
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertNotEqual(subprocess.run(args, capture_output=True).returncode, 0)
            self.assertEqual(path.read_text(), token)

    def test_invalid_uid_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "key"
            result = subprocess.run([str(self.binary), str(path), "bad"], capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(path.exists())

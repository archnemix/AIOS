import os
import pathlib
import subprocess
import tempfile
import unittest

SOURCE = pathlib.Path(__file__).resolve().parents[1] / "os/buildroot/package/aios-hardware/src/hardware.c"


class HardwareProbeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        cls.binary = pathlib.Path(cls.directory.name) / "hardware"
        subprocess.run(["cc", "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror", str(SOURCE),
                        "-o", str(cls.binary)], check=True)

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    def test_threads_respect_affinity(self):
        threads = int(subprocess.check_output([str(self.binary), "--threads"], text=True))
        self.assertGreaterEqual(threads, 1)
        self.assertLessEqual(threads, len(os.sched_getaffinity(0)))
        logical = int(subprocess.check_output([str(self.binary), "--logical"], text=True))
        self.assertGreaterEqual(logical, threads)
        self.assertLessEqual(logical, len(os.sched_getaffinity(0)))

    def test_report_and_invalid_arguments(self):
        report = subprocess.check_output([str(self.binary), "--report"], text=True)
        self.assertIn("Suggested inference threads:", report)
        self.assertNotEqual(subprocess.run([str(self.binary), "bad"], capture_output=True).returncode, 0)

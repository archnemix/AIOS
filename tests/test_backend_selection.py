import pathlib
import subprocess
import tempfile
import unittest

SELECTOR = pathlib.Path(__file__).resolve().parents[1] / "os/buildroot/board/aios/rootfs-overlay/usr/libexec/aios-select-backend"


class SelectionTests(unittest.TestCase):
    def select(self, data):
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "cpuinfo"
            path.write_text(data)
            return subprocess.check_output([str(SELECTOR), str(path)], text=True).strip()

    def test_all_cpus_have_required_features(self):
        self.assertEqual(self.select("flags : sse4_2 avx avx2 fma f16c bmi2\nflags : sse4_2 avx avx2 fma f16c bmi2\n"), "avx2")

    def test_missing_features_or_cpuinfo_use_portable(self):
        for data in ("", "flags : avx2 fma f16c bmi2\n", "flags : sse4_2 avx avx2 fma f16c bmi2\nflags : avx\n"):
            with self.subTest(data=data):
                self.assertEqual(self.select(data), "portable")

    def test_flag_names_are_not_substrings(self):
        self.assertEqual(self.select("flags : sse4_2 avx avx2 fma f16c bmi2extra\n"), "portable")

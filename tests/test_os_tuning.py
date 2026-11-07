import importlib.util
import unittest
from pathlib import Path
from unittest import mock

script = Path(__file__).resolve().parents[1] / 'scripts/os_tuning/native.py'
spec = importlib.util.spec_from_file_location('os_tuning_native', script)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class NativePolicyTests(unittest.TestCase):
    def test_physical_core_fallback_uses_allowed_cpus(self):
        with mock.patch.object(module.Path, 'read_text', side_effect=OSError):
            self.assertEqual(module.physical_cores([3, 5, 7]), [3, 5])

    def test_memory_sampler_handles_disappearing_process(self):
        self.assertEqual(module.memory_sample(-1), {})

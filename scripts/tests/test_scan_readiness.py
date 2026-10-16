"""Exercise bounded startup retries without Docker or application data."""

import subprocess
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from scripts.wait_for_scanner import COMMAND, wait_for_scanner


class ScannerReadinessTests(unittest.TestCase):
    def test_transient_failure_waits_for_actual_health_success(self):
        with (
            patch("scripts.wait_for_scanner.time.monotonic", side_effect=[0, 0, 1, 2]),
            patch("scripts.wait_for_scanner.time.sleep") as sleep,
            patch(
                "scripts.wait_for_scanner.subprocess.run",
                side_effect=[
                    SimpleNamespace(
                        returncode=1, stdout='{"state":"dependency_unavailable"}'
                    ),
                    SimpleNamespace(returncode=0, stdout='{"jobs":[{"state":"ok"}]}'),
                ],
            ) as run,
        ):
            wait_for_scanner(timeout=10)
        self.assertEqual(run.call_count, 2)
        self.assertEqual(run.call_args.args[0], COMMAND)
        sleep.assert_called_once_with(5)

    def test_unready_dependencies_fail_at_deadline(self):
        with (
            patch(
                "scripts.wait_for_scanner.time.monotonic", side_effect=[0, 0, 10, 10]
            ),
            patch(
                "scripts.wait_for_scanner.subprocess.run",
                return_value=SimpleNamespace(returncode=1, stdout=""),
            ),
            self.assertRaisesRegex(RuntimeError, "Quarantine remains enforced"),
        ):
            wait_for_scanner(timeout=10)

    def test_stalled_probe_cannot_extend_deadline(self):
        with (
            patch(
                "scripts.wait_for_scanner.time.monotonic", side_effect=[0, 0, 10, 10]
            ),
            patch(
                "scripts.wait_for_scanner.subprocess.run",
                side_effect=subprocess.TimeoutExpired(COMMAND, 10),
            ) as run,
            self.assertRaisesRegex(RuntimeError, "startup deadline"),
        ):
            wait_for_scanner(timeout=10)
        self.assertEqual(run.call_args.kwargs["timeout"], 10)


if __name__ == "__main__":
    unittest.main()

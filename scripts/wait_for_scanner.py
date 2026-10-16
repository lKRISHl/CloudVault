"""Bounded Compose scan dependency/worker readiness before creating smoke uploads."""

import subprocess
import time

COMMAND = [
    "docker", "compose", "exec", "-T", "scan-worker", "python", "-m",
    "app.jobs.check_jobs", "--job", "scans", "--scanner",
]


def wait_for_scanner(timeout=600):
    deadline = time.monotonic() + timeout
    while (remaining := deadline - time.monotonic()) > 0:
        try:
            result = subprocess.run(
                COMMAND, capture_output=True, text=True, timeout=min(30, remaining),
                check=False,
            )
        except subprocess.TimeoutExpired:
            print("Scan dependency/worker health probe timed out", flush=True)
        else:
            # check_jobs deliberately outputs only safe operator state/counts.
            print(result.stdout.strip() or "Scan worker not ready", flush=True)
            if result.returncode == 0:
                print("Fresh scanner, broker, storage and scan worker are ready", flush=True)
                return
        remaining = deadline - time.monotonic()
        if remaining > 0:
            time.sleep(min(5, remaining))
    raise RuntimeError(
        "Scan dependencies did not become ready within the startup deadline. "
        "Inspect clamav-updater, clamav, scan-worker and job-scheduler logs. "
        "Quarantine remains enforced; do not bypass scans or definition freshness."
    )


if __name__ == "__main__":
    wait_for_scanner()

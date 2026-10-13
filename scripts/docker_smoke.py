"""Verify the local Compose UI/API and an actual S3 object round trip."""

import subprocess
import urllib.request


def main():
    for url in (
        "http://localhost:3000/",
        "http://localhost:3000/api/v1/health",
        "http://localhost:9000/minio/health/live",
        "http://localhost:8025/",
    ):
        with urllib.request.urlopen(url, timeout=15) as response:
            assert response.status == 200, url
        print(f"HTTP OK: {url}")

    # A unique object in the development bucket; trap removes it even on failure.
    subprocess.run(
        [
            "docker",
            "compose",
            "run",
            "--rm",
            "--no-deps",
            "--entrypoint",
            "/bin/sh",
            "minio-setup",
            "-ec",
            (
                "mc alias set local http://minio:9000 minioadmin minioadmin >/dev/null; "
                'key="local/cloudvault/smoke-$(cat /proc/sys/kernel/random/uuid)"; '
                "trap 'mc rm \"$key\" >/dev/null' EXIT; "
                'printf "cloudvault-storage-smoke" | mc pipe "$key" >/dev/null; '
                '[ "$(mc cat "$key")" = "cloudvault-storage-smoke" ]; '
                'echo "S3 upload/download/delete OK"'
            ),
        ],
        check=True,
        timeout=60,
    )


if __name__ == "__main__":
    main()

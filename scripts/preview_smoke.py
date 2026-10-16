"""Check real Docker isolation and render only generated, owned PNG/PDF fixtures."""

import argparse
import base64
import hashlib
import io
import json
import subprocess
import time
from uuid import uuid4

import httpx
from PIL import Image
from upload_smoke import require, verify_email, wait_scan_release


def digest(content):
    return base64.b64encode(hashlib.sha256(content).digest()).decode()


def preview_response(api, fid, values, queued):
    wait_scan_release(api, fid, values.get("version_id"))
    if not queued:
        return api.post(f"/files/{fid}/preview", json=values)
    job = require(
        api.post(
            f"/files/{fid}/preview-jobs",
            json={
                "request_id": str(uuid4()),
                **values,
            },
        ),
        202,
    )
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        response = api.get(f"/files/{fid}/preview-jobs/{job['id']}")
        state = require(response, 200)
        if state["state"] == "ready":
            # Keep the actual authenticated result headers available for assertions.
            return httpx.Response(200, json=state["preview"], headers=response.headers)
        if state["state"] in ("failed", "cancelled"):
            raise RuntimeError("Owned queued preview failed or was cancelled")
        time.sleep(0.5)
    raise RuntimeError("Owned queued preview deadline exceeded")


def api_roundtrips(
    image,
    queued=False,
    video=None,
    base_url="http://localhost:3000",
    inbox_url="http://localhost:8025",
):
    email = f"preview-smoke-{uuid4().hex}@example.com"
    with httpx.Client(base_url=base_url + "/api/v1", timeout=25) as api:
        session = require(
            api.post(
                "/auth/register",
                json={
                    "email": email,
                    "password": uuid4().hex,
                    "full_name": "Preview Smoke",
                    "tenant_name": "Preview Smoke " + uuid4().hex[:8],
                },
            ),
            201,
        )
        api.headers["Authorization"] = "Bearer " + session["access_token"]
        verify_email(api, email, inbox_url)
        fixture = io.BytesIO()
        image.save(fixture, format="PNG")
        first = fixture.getvalue()
        # Misleading declarations must not select the renderer.
        ticket = require(
            api.post(
                "/files/uploads",
                json={
                    "name": "Verified preview.html",
                    "request_id": str(uuid4()),
                    "declared_size_bytes": len(first),
                    "declared_content_type": "text/html",
                    "checksum_sha256": digest(first),
                },
            ),
            201,
        )
        fid = ticket["file"]["id"]
        with httpx.Client(timeout=25) as transfer:
            assert (
                transfer.put(
                    ticket["upload_url"], headers=ticket["headers"], content=first
                ).status_code
                == 200
            )
            completed = require(api.post(f"/files/{fid}/complete"), 200)
            response = preview_response(api, fid, {}, queued)
            result = require(response, 200)
            assert result["kind"] == "image" and result["detected_type"] == "image/png"
            assert result["scan_status"] == "clean"
            assert response.headers["cache-control"] == "no-store"
            assert response.headers["x-content-type-options"] == "nosniff"
            original = result["version_id"]
            fixture = io.BytesIO()
            image.save(
                fixture,
                format="PDF",
                save_all=True,
                append_images=[Image.new("RGB", image.size, "red")],
            )
            second = fixture.getvalue()
            root = f"/files/{fid}/versions"
            ticket = require(
                api.post(
                    root,
                    json={
                        "request_id": str(uuid4()),
                        "base_generation": completed["version_generation"],
                        "declared_size_bytes": len(second),
                        "declared_content_type": "image/png",
                        "checksum_sha256": digest(second),
                    },
                ),
                201,
            )
            assert (
                transfer.put(
                    ticket["upload_url"], headers=ticket["headers"], content=second
                ).status_code
                == 200
            )
            require(api.post(root + f"/{ticket['version']['id']}/complete"), 200)
            result = require(preview_response(api, fid, {"page": 1}, queued), 200)
            assert (
                result["kind"] == "pdf" and result["page"] == 1 and result["pages"] == 2
            )
            assert result["version_number"] == 2
            result = require(
                preview_response(api, fid, {"version_id": original}, queued), 200
            )
            assert result["kind"] == "image" and result["version_number"] == 1
            if video:
                ticket = require(
                    api.post(
                        "/files/uploads",
                        json={
                            "name": "Owned poster.mp4",
                            "request_id": str(uuid4()),
                            "declared_size_bytes": len(video),
                            "declared_content_type": "video/mp4",
                            "checksum_sha256": digest(video),
                        },
                    ),
                    201,
                )
                video_id = ticket["file"]["id"]
                assert (
                    transfer.put(
                        ticket["upload_url"], headers=ticket["headers"], content=video
                    ).status_code
                    == 200
                )
                require(api.post(f"/files/{video_id}/complete"), 200)
                result = require(preview_response(api, video_id, {}, queued), 200)
                assert (
                    result["kind"] == "video" and result["detected_type"] == "video/mp4"
                )
    print("Live API/provider/current PDF/history PNG preview round trips passed")


COMPOSE_ARGUMENTS = []


def docker(*arguments, content=None):
    if arguments[0] == "compose":
        arguments = ("compose", *COMPOSE_ARGUMENTS, *arguments[1:])
    return subprocess.run(
        ["docker", *arguments],
        input=content,
        check=True,
        capture_output=True,
        timeout=30,
    ).stdout


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--queued", action="store_true")
    parser.add_argument("--video", action="store_true")
    parser.add_argument(
        "--phase16-stack",
        action="store_true",
        help="Use the owned disposable acceptance manifest",
    )
    args = parser.parse_args()
    base_url, inbox_url = "http://localhost:3000", "http://localhost:8025"
    if args.phase16_stack:
        import re

        from phase16_stack import MANIFEST, ROOT

        manifest = json.loads(MANIFEST.read_text())
        project = manifest["project"]
        if manifest["root"] != str(ROOT) or not re.fullmatch(
            r"cv-phase16-check-[0-9a-f]{12}", project
        ):
            raise ValueError("Refusing an unowned acceptance stack")
        COMPOSE_ARGUMENTS.extend(
            [
                "-p",
                project,
                "-f",
                str(ROOT / "docker-compose.yml"),
                "-f",
                str(ROOT / "infra/testing/phase16.compose.yml"),
            ]
        )
        base_url, inbox_url = "http://127.0.0.1:43916", "http://127.0.0.1:48916"
    identity = docker("compose", "ps", "-q", "preview-renderer").decode().strip()
    if not identity:
        raise RuntimeError("Preview renderer is not running")
    container = json.loads(docker("inspect", identity))[0]
    host = container["HostConfig"]
    assert host["NetworkMode"] == "none" and host["ReadonlyRootfs"]
    assert "ALL" in [value.upper() for value in host["CapDrop"]]
    assert "no-new-privileges:true" in host["SecurityOpt"]
    assert host["Memory"] == 512 * 1024 * 1024 and host["PidsLimit"] == 32
    assert (
        host["NanoCpus"] == 1_000_000_000 and container["Config"]["User"] == "1000:1000"
    )
    assert not any(
        value.startswith(("S3_", "DATABASE_", "SECRET_", "SMTP_"))
        for value in container["Config"]["Env"]
    )
    assert [
        value["Destination"]
        for value in container["Mounts"]
        if value["Type"] != "tmpfs"
    ] == ["/preview"]
    image = Image.new("RGB", (80, 40), "#2266cc")
    for format, kind in [("PNG", "image"), ("PDF", "pdf")]:
        fixture = io.BytesIO()
        image.save(fixture, format=format)
        output = docker(
            "compose",
            "exec",
            "-T",
            "backend",
            "python",
            "-m",
            "app.jobs.render_preview",
            content=fixture.getvalue(),
        )
        result = json.loads(output)
        assert result["kind"] == kind, result.get("reason")
        png = base64.b64decode(result["image_base64"], validate=True)
        assert len(png) <= 1024 * 1024
        with Image.open(io.BytesIO(png)) as rendered:
            assert rendered.format == "PNG" and max(rendered.size) <= 1600
    print("Docker preview isolation and generated PNG/PDF round trips passed")
    video = None
    if args.video:
        video = docker(
            "compose",
            "exec",
            "-T",
            "preview-renderer",
            "ffmpeg",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=blue:s=80x40:d=1",
            "-c:v",
            "libx264",
            "-threads",
            "1",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "frag_keyframe+empty_moov",
            "-f",
            "mp4",
            "pipe:1",
        )
        result = json.loads(
            docker(
                "compose",
                "exec",
                "-T",
                "backend",
                "python",
                "-m",
                "app.jobs.render_preview",
                content=video,
            )
        )
        assert result["kind"] == "video", result.get("reason")
        assert base64.b64decode(result["image_base64"]).startswith(b"\x89PNG\r\n\x1a\n")
    api_roundtrips(
        image, queued=args.queued, video=video, base_url=base_url, inbox_url=inbox_url
    )


if __name__ == "__main__":
    main()

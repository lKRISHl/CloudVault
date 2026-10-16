import io
import json
import shutil
import subprocess
from types import SimpleNamespace

import pytest
from PIL import Image

from app.previews.video import poster
from app.previews.worker import render

SOURCE = b"\x00\x00\x00\x18ftyp" + b"fixture-contract"


def probe(**changes):
    return {
        "streams": [{"codec_name": "h264", "width": 80, "height": 40, **changes}],
        "format": {"duration": "1.0"},
    }


def fake_tools(monkeypatch, metadata):
    output = io.BytesIO()
    Image.new("RGB", (80, 40), "red").save(output, format="PNG")
    calls = []

    def run(arguments, **kwargs):
        calls.append(arguments)
        assert kwargs["timeout"] <= 5 and kwargs["check"]
        assert arguments[arguments.index("-protocol_whitelist") + 1] == "file,pipe"
        assert arguments[arguments.index("-enable_drefs") + 1] == "0"
        assert arguments[arguments.index("-use_absolute_path") + 1] == "0"
        return SimpleNamespace(
            stdout=json.dumps(metadata).encode() if arguments[0] == "ffprobe" else output.getvalue()
        )

    monkeypatch.setattr(subprocess, "run", run)
    return calls


def test_video_protocol_boundaries_and_static_png_contract(monkeypatch):
    calls = fake_tools(monkeypatch, probe())
    result = render(SOURCE)
    assert result["kind"] == "video" and result["detected_type"] == "video/mp4"
    assert len(calls) == 2 and "-frames:v" in calls[1] and "-an" in calls[1]
    assert result["width"] == 80 and result["height"] == 40
    with pytest.raises(ValueError):
        render(SOURCE, 1)


@pytest.mark.parametrize(
    "metadata",
    [
        probe(width=0),
        probe(width=10000),
        probe(codec_name="av1"),
        {**probe(), "format": {"duration": "nan"}},
        {**probe(), "format": {"duration": "121"}},
        {**probe(), "streams": []},
    ],
)
def test_resource_limits_refuse_before_decoding(monkeypatch, metadata):
    calls = fake_tools(monkeypatch, metadata)
    with pytest.raises(ValueError):
        poster(SOURCE)
    assert len(calls) == 1


@pytest.mark.skipif(
    not shutil.which("ffmpeg") or not shutil.which("ffprobe"),
    reason="Real video tools unavailable; isolated-container decoder verification remains required",
)
def test_real_owned_video_fixture_becomes_static_poster(tmp_path):
    source = tmp_path / "owned.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=blue:s=80x40:d=1",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(source),
        ],
        check=True,
        timeout=10,
    )
    result = render(source.read_bytes())
    assert result["kind"] == "video" and result["detected_type"] == "video/mp4"

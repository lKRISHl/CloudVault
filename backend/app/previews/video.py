"""Static first-frame poster. Called only inside the credential-free native renderer."""

import io
import json
import math
import subprocess
import tempfile
from pathlib import Path


def poster(data):
    from PIL import Image

    mov = data[4:8] == b"ftyp"
    if not mov and not data.startswith(b"\x1aE\xdf\xa3"):
        raise ValueError("video_format")
    with tempfile.TemporaryDirectory(prefix="cv-video-") as directory:
        source = Path(directory) / "source"
        source.write_bytes(data)
        options = [
            "-v",
            "error",
            "-max_alloc",
            "67108864",
            "-protocol_whitelist",
            "file,pipe",
            "-probesize",
            "10485760",
            "-analyzeduration",
            "1000000",
            "-f",
            "mov" if mov else "matroska",
        ]
        if mov:
            options += ["-enable_drefs", "0", "-use_absolute_path", "0"]
        probe = subprocess.run(
            [
                "ffprobe",
                *options,
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=codec_name,width,height:format=duration",
                "-of",
                "json",
                str(source),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=4,
            check=True,
        )
        if len(probe.stdout) > 16384:
            raise ValueError("probe_limit")
        metadata = json.loads(probe.stdout)
        streams = metadata.get("streams", [])
        if len(streams) != 1:
            raise ValueError("video_stream")
        stream = streams[0]
        width, height = stream.get("width", 0), stream.get("height", 0)
        duration = float(metadata.get("format", {}).get("duration", "nan"))
        if (
            stream.get("codec_name") not in ("h264", "vp8", "vp9")
            or not 0 < width <= 4096
            or not 0 < height <= 4096
            or width * height > 8_294_400
            or not math.isfinite(duration)
            or not 0 < duration <= 120
        ):
            raise ValueError("video_limit")
        output = subprocess.run(
            [
                "ffmpeg",
                "-nostdin",
                *options,
                "-threads",
                "1",
                "-i",
                str(source),
                "-map",
                "0:v:0",
                "-frames:v",
                "1",
                "-an",
                "-sn",
                "-dn",
                "-filter_threads",
                "1",
                "-vf",
                "scale=1600:1600:force_original_aspect_ratio=decrease",
                "-threads",
                "1",
                "-c:v",
                "png",
                "-f",
                "image2pipe",
                "pipe:1",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=5,
            check=True,
        )
        if len(output.stdout) > 12 * 1024 * 1024:
            raise ValueError("poster_limit")
        with Image.open(io.BytesIO(output.stdout), formats=["PNG"]) as decoded:
            decoded.load()
            return decoded.convert("RGB"), "video/mp4" if mov else "video/webm"

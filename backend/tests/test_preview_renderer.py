import base64
import io
import json
import struct

import pypdfium2
import pytest
from fastapi import HTTPException
from PIL import Image, PngImagePlugin

from app.previews.worker import render
from app.services.previews import isolated_render, native_type, text_or_unsupported


def image_bytes(format="PNG", size=(80, 40)):
    data = io.BytesIO()
    image = Image.new("RGB", size, "#2266cc")
    info = PngImagePlugin.PngInfo()
    info.add_text("Secret", "must not survive")
    image.save(data, format=format, **({"pnginfo": info} if format == "PNG" else {}))
    return data.getvalue()


@pytest.mark.parametrize("format", ["PNG", "JPEG", "GIF", "WEBP"])
def test_real_images_are_detected_reencoded_bounded_and_metadata_stripped(format):
    source = image_bytes(format)
    result = render(source)
    content = base64.b64decode(result["image_base64"])
    with Image.open(io.BytesIO(content)) as image:
        assert image.format == "PNG" and image.size == (80, 40)
        assert "Secret" not in image.info
    assert result["kind"] == "image" and result["detected_type"] == native_type(source)


def test_real_pdf_pages_render_static_png_with_bounds():
    result = render(image_bytes("PDF"))
    assert result["kind"] == "pdf" and result["pages"] == 1
    assert base64.b64decode(result["image_base64"]).startswith(b"\x89PNG\r\n\x1a\n")
    with pytest.raises(ValueError):
        render(image_bytes("PDF"), 1)


def test_malformed_unknown_oversized_and_decompression_bomb_inputs_fail_closed():
    for source in [b"%PDF-broken", b"\x89PNG\r\n\x1a\ninvalid", b"<svg onload='alert(1)'/>"]:
        with pytest.raises((ValueError, OSError, pypdfium2.PdfiumError)):
            render(source)
    with pytest.raises(ValueError):
        render(b"x" * (10 * 1024 * 1024 + 1))
    with pytest.raises((ValueError, Image.DecompressionBombWarning, Image.DecompressionBombError)):
        render(image_bytes(size=(5000, 4000)))


def test_text_is_not_html_and_control_binary_video_cases_are_explicit():
    source = b'<script>alert("untrusted")</script>'
    result = text_or_unsupported(source)
    assert result.kind == "text" and result.text == source.decode()
    assert text_or_unsupported(b"binary\x00").kind == "unsupported"
    assert text_or_unsupported(b"\xff\xfe").kind == "unsupported"
    assert "\\u202e" in text_or_unsupported("a\u202eb".encode()).text
    assert text_or_unsupported(b"x" * 70000).truncated
    expanded = text_or_unsupported(("\u202e" * 65000).encode())
    assert expanded.truncated and len(expanded.text) == 262144
    assert text_or_unsupported(b"\x00\x00\x00\x18ftypmp42").kind == "unsupported"


@pytest.mark.asyncio
async def test_isolated_protocol_rejects_oversized_active_or_wrong_identity_outputs(monkeypatch):
    import asyncio

    class Writer:
        closed = False

        def write(self, data):
            assert struct.unpack("!II", data[:8]) == (len(source), 0)

        async def drain(self):
            pass

        def close(self):
            self.closed = True

    source = image_bytes()
    valid = render(source)
    outputs = [
        {"kind": "unsupported", "reason": "Renderer busy or resource limit reached"},
        struct.pack("!I", 2 * 1024 * 1024),
        b"\x00\x00",  # Truncated frame.
        {"kind": "text", "text": "<script>active</script>"},
        {**valid, "detected_type": "application/pdf"},
        {**valid, "image_base64": base64.b64encode(b"<svg onload='alert(1)'/>").decode()},
    ]
    for output in outputs:
        writer = Writer()
        reader = asyncio.StreamReader()
        if isinstance(output, dict):
            data = json.dumps(output).encode()
            output = struct.pack("!I", len(data)) + data
        reader.feed_data(output)
        reader.feed_eof()

        async def connect(*args, reader=reader, writer=writer):
            return reader, writer

        monkeypatch.setattr(asyncio, "open_unix_connection", connect, raising=False)
        with pytest.raises(HTTPException) as failure:
            await isolated_render(source, 0)
        assert failure.value.status_code == 503 and writer.closed


@pytest.mark.asyncio
async def test_windows_or_missing_renderer_has_no_host_parsing_fallback(monkeypatch):
    import asyncio

    async def unavailable(*args):
        raise NotImplementedError("Unix socket support unavailable")

    monkeypatch.setattr(asyncio, "open_unix_connection", unavailable, raising=False)
    with pytest.raises(HTTPException) as failure:
        await isolated_render(image_bytes(), 0)
    assert failure.value.status_code == 503

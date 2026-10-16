"""Runs only in the restricted preview container (or directly against test fixtures)."""

import base64
import io
import json
import math
import sys
import warnings

MAX_SOURCE = 10 * 1024 * 1024
MAX_PNG = 1024 * 1024
MAX_PIXELS = 16_000_000
EDGE = 1600


def render(data, page_number=0):
    from PIL import Image, ImageOps

    if len(data) > MAX_SOURCE:
        raise ValueError("source_limit")
    Image.MAX_IMAGE_PIXELS = MAX_PIXELS
    warnings.simplefilter("error", Image.DecompressionBombWarning)
    pdf = page = bitmap = opened = None
    try:
        if data[4:8] == b"ftyp" or data.startswith(b"\x1aE\xdf\xa3"):
            if page_number != 0:
                raise ValueError("page_limit")
            # Script mode deliberately has no application import path or credentials.
            import importlib.util
            from pathlib import Path

            spec = importlib.util.spec_from_file_location(
                "video", Path(__file__).with_name("video.py")
            )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            image, detected = module.poster(data)
            kind, total = "video", 1
        elif data.startswith(b"%PDF-"):
            import pypdfium2 as pdfium

            pdf = pdfium.PdfDocument(data)
            total = len(pdf)
            if not 1 <= total <= 1000 or not 0 <= page_number < min(total, 100):
                raise ValueError("page_limit")
            page = pdf[page_number]
            width, height = page.get_size()
            if not all(math.isfinite(n) and 0 < n <= 100_000 for n in (width, height)):
                raise ValueError("page_size")
            scale = min(2, EDGE / max(width, height))
            bitmap = page.render(scale=scale, draw_annots=False, may_draw_forms=False)
            image = bitmap.to_pil().convert("RGB")
            kind, detected = "pdf", "application/pdf"
        else:
            if page_number != 0:
                raise ValueError("page_limit")
            opened = Image.open(io.BytesIO(data), formats=["PNG", "JPEG", "GIF", "WEBP"])
            detected = {
                "PNG": "image/png",
                "JPEG": "image/jpeg",
                "GIF": "image/gif",
                "WEBP": "image/webp",
            }[opened.format]
            if opened.width * opened.height > MAX_PIXELS:
                raise ValueError("pixel_limit")
            opened.seek(0)
            image = ImageOps.exif_transpose(opened).convert("RGBA")
            kind, total = "image", 1
        image.thumbnail((EDGE, EDGE))
        # Copy pixels into a fresh image: no source EXIF, text, profiles or active PDF data.
        clean = Image.new(image.mode, image.size)
        clean.paste(image)
        for _ in range(3):
            output = io.BytesIO()
            clean.save(output, format="PNG")
            content = output.getvalue()
            if len(content) <= MAX_PNG:
                return {
                    "kind": kind,
                    "detected_type": detected,
                    "image_base64": base64.b64encode(content).decode(),
                    "width": clean.width,
                    "height": clean.height,
                    "page": page_number,
                    "pages": min(total, 100),
                    "truncated": total > 100,
                }
            clean = clean.resize((max(1, clean.width // 2), max(1, clean.height // 2)))
        raise ValueError("output_limit")
    finally:
        if opened is not None:
            opened.close()
        if bitmap:
            bitmap.close()
        if page:
            page.close()
        if pdf:
            pdf.close()


def main():
    try:
        import resource

        resource.setrlimit(resource.RLIMIT_CPU, (5, 5))
        resource.setrlimit(resource.RLIMIT_AS, (384 * 1024 * 1024,) * 2)
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        resource.setrlimit(resource.RLIMIT_NOFILE, (32, 32))
    except ImportError:
        pass  # Direct Windows fixture tests only; production calls require the isolated container.
    try:
        data = sys.stdin.buffer.read(MAX_SOURCE + 1)
        result = render(data, int(sys.argv[1]))
    except Exception:
        result = {
            "kind": "unsupported",
            "reason": "Malformed, encrypted or resource-limited preview",
        }
    sys.stdout.write(json.dumps(result))


if __name__ == "__main__":
    main()

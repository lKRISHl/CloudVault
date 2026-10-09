import re
import secrets


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    slug = slug[:120] or "workspace"
    return slug


def unique_slug(base: str) -> str:
    suffix = secrets.token_hex(3)
    trimmed = slugify(base)[:112]
    return f"{trimmed}-{suffix}"

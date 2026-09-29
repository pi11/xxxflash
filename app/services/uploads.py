"""Storing uploaded games and thumbnails under MEDIA_ROOT."""

import datetime as dt
import io
import secrets
from pathlib import Path

from PIL import Image, UnidentifiedImageError

THUMB_SIZE = (350, 350)


class UploadError(ValueError):
    pass


def _unique(root: Path, rel_dir: str, suffix: str) -> str:
    target_dir = root / rel_dir
    target_dir.mkdir(parents=True, exist_ok=True)
    while True:
        rel = f"{rel_dir}/{secrets.token_hex(8)}{suffix}"
        if not (root / rel).exists():
            return rel


def store_swf(media_root: Path, data: bytes, today: dt.date | None = None) -> str:
    today = today or dt.date.today()
    rel = _unique(media_root, today.strftime("swf/%Y/%m/%d"), ".swf")
    (media_root / rel).write_bytes(data)
    return rel


def store_thumbnail(media_root: Path, data: bytes, today: dt.date | None = None) -> str:
    """Validate the image and save it as a 350x350 RGB JPEG (legacy Flash.save)."""
    try:
        image = Image.open(io.BytesIO(data))
        image.load()
    except (UnidentifiedImageError, OSError) as exc:
        raise UploadError("Неверный формат изображения") from exc
    image = image.convert("RGB").resize(THUMB_SIZE, Image.Resampling.LANCZOS)
    today = today or dt.date.today()
    rel = _unique(media_root, today.strftime("th/%Y/%m"), ".jpg")
    image.save(media_root / rel, "JPEG", quality=85)
    return rel

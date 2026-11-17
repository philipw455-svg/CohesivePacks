"""Finds iPhone photos in the inbox and pairs them front + back."""

from __future__ import annotations

import io
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageOps

PHOTO_TYPES = {".jpg", ".jpeg", ".png", ".heic", ".heif"}
EXIF_IFD = 0x8769
DATETIME_ORIGINAL = 36867

try:  # iPhones save HEIC photos by default. This plug-in lets Pillow read them.
    from pillow_heif import register_heif_opener

    register_heif_opener()
    HEIC_SUPPORTED = True
except ImportError:
    HEIC_SUPPORTED = False


@dataclass
class PhotoPair:
    first: Path
    second: Path


def open_photo(path: Path) -> Image.Image:
    """Opens a photo and turns it upright, the way the iPhone showed it."""
    if path.suffix.lower() in (".heic", ".heif") and not HEIC_SUPPORTED:
        raise SystemExit(
            f"{path.name} is a HEIC photo. Run 'pip install pillow-heif', "
            "or set iPhone Settings > Camera > Formats > Most Compatible."
        )
    with Image.open(path) as img:
        return ImageOps.exif_transpose(img).convert("RGB")


def to_jpeg_bytes(img: Image.Image, max_side: int | None = None, quality: int = 92) -> bytes:
    if max_side and max(img.size) > max_side:
        img = img.copy()
        img.thumbnail((max_side, max_side), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality)
    return buf.getvalue()


def capture_time(path: Path) -> datetime:
    """Returns when the photo was taken. Falls back to the file's save time."""
    try:
        with Image.open(path) as img:
            raw = img.getexif().get_ifd(EXIF_IFD).get(DATETIME_ORIGINAL)
        if raw:
            return datetime.strptime(str(raw).strip(), "%Y:%m:%d %H:%M:%S")
    except Exception:
        pass
    return datetime.fromtimestamp(path.stat().st_mtime)


def find_photos(inbox: Path) -> list[Path]:
    photos = [p for p in inbox.iterdir() if p.is_file() and p.suffix.lower() in PHOTO_TYPES]
    return sorted(photos, key=lambda p: (capture_time(p), p.name))


def pair_photos(photos: list[Path]) -> tuple[list[PhotoPair], Path | None]:
    """Pairs photos in the order you took them: 1+2, 3+4, and so on.

    Returns the pairs and any leftover photo without a partner.
    """
    pairs = [PhotoPair(photos[i], photos[i + 1]) for i in range(0, len(photos) - 1, 2)]
    leftover = photos[-1] if len(photos) % 2 else None
    return pairs, leftover

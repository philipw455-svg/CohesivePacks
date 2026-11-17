"""Turns a raw photo on dark wood into a clean studio shot.

Two editors exist:
- PhotoroomEditor sends the photo to the Photoroom AI service. Photoroom cuts the
  card out of the wood background, places it on a studio background, and adds a
  soft shadow. It does not repaint the card itself, so the card's real condition
  stays visible. eBay requires photos that show the real item.
- LocalEditor runs free on your computer. It only fixes brightness, contrast,
  and sharpness. It keeps the wood background.
"""

from __future__ import annotations

import time
from pathlib import Path

import requests
from PIL import Image, ImageEnhance, ImageOps

from .photos import open_photo, to_jpeg_bytes

PHOTOROOM_URL = "https://image-api.photoroom.com/v2/edit"
# Trading cards are 2.5 x 3.5 inches, a 5:7 shape.
OUTPUT_SIZE = "1600x2240"


class PhotoroomEditor:
    name = "photoroom"

    def __init__(self, api_key: str, background_hex: str = "FFFFFF", session=None):
        self.api_key = api_key
        self.background_hex = background_hex
        self.http = session or requests.Session()

    def edit(self, src: Path, dest: Path) -> Path:
        upload = to_jpeg_bytes(open_photo(src), max_side=4000)
        form = {
            "background.color": self.background_hex,
            "shadow.mode": "ai.soft",
            "padding": "0.08",
            "outputSize": OUTPUT_SIZE,
            "export.format": "jpeg",
        }
        for attempt in range(4):
            resp = self.http.post(
                PHOTOROOM_URL,
                headers={"x-api-key": self.api_key},
                files={"imageFile": (src.stem + ".jpg", upload, "image/jpeg")},
                data=form,
                timeout=120,
            )
            if resp.status_code in (429, 500, 502, 503, 504) and attempt < 3:
                time.sleep(2 ** attempt)
                continue
            if resp.status_code != 200:
                raise RuntimeError(
                    f"Photoroom could not edit {src.name} "
                    f"(status {resp.status_code}): {resp.text[:300]}"
                )
            dest.write_bytes(resp.content)
            return dest
        raise RuntimeError(f"Photoroom kept failing on {src.name}.")


class LocalEditor:
    name = "local"

    def edit(self, src: Path, dest: Path) -> Path:
        img = open_photo(src)
        img = ImageOps.autocontrast(img, cutoff=0.5)
        img = ImageEnhance.Brightness(img).enhance(1.05)
        img = ImageEnhance.Color(img).enhance(1.05)
        img = ImageEnhance.Sharpness(img).enhance(1.3)
        img.thumbnail((2400, 2400), Image.LANCZOS)
        img.save(dest, format="JPEG", quality=92)
        return dest


def make_editor(photoroom_api_key: str, background_hex: str):
    if photoroom_api_key:
        return PhotoroomEditor(photoroom_api_key, background_hex)
    return LocalEditor()

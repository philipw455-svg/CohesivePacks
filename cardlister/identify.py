"""Sends both photos of a card to Claude, which reads the card details."""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from .photos import open_photo, to_jpeg_bytes

MODEL = "claude-opus-5-5"

Condition = Literal["near_mint_or_better", "excellent", "very_good", "poor"]


class CardInfo(BaseModel):
    front_photo: Literal["first", "second"]
    sport: str
    year: str
    manufacturer: str
    set_name: str
    card_number: str
    player: str
    team: str
    parallel: str
    insert_name: str
    serial_number: str
    rookie: bool
    autographed: bool
    memorabilia: bool
    graded: bool
    grader: str
    grade: str
    condition: Condition
    condition_notes: str
    title: str
    search_query: str
    confidence: Literal["high", "medium", "low"]


def _strict_schema() -> dict:
    props = {
        "front_photo": {"type": "string", "enum": ["first", "second"]},
        "sport": {"type": "string"},
        "year": {"type": "string"},
        "manufacturer": {"type": "string"},
        "set_name": {"type": "string"},
        "card_number": {"type": "string"},
        "player": {"type": "string"},
        "team": {"type": "string"},
        "parallel": {"type": "string"},
        "insert_name": {"type": "string"},
        "serial_number": {"type": "string"},
        "rookie": {"type": "boolean"},
        "autographed": {"type": "boolean"},
        "memorabilia": {"type": "boolean"},
        "graded": {"type": "boolean"},
        "grader": {"type": "string"},
        "grade": {"type": "string"},
        "condition": {
            "type": "string",
            "enum": ["near_mint_or_better", "excellent", "very_good", "poor"],
        },
        "condition_notes": {"type": "string"},
        "title": {"type": "string"},
        "search_query": {"type": "string"},
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
    }
    return {
        "type": "object",
        "properties": props,
        "required": list(props),
        "additionalProperties": False,
    }


PROMPT = """You are cataloging a sports trading card for an eBay auction.
Photo 1 and photo 2 show the two sides of ONE card, in unknown order.

Read the card exactly as printed. Use the back for year, set, and card number.
Rules:
- front_photo: which photo shows the front (player image side).
- year: the season as eBay sellers write it, for example "2023" or "2023-24".
- Use an empty string for any field you cannot read or that does not apply.
- parallel: color or refractor name only if the card is a parallel.
- serial_number: like "25/99" only if stamped on the card.
- graded: true only if the card sits in a grading company slab.
- condition: judge corners, edges, surface, and centering you can see.
  Be conservative. List visible flaws in condition_notes.
- title: an eBay title of at most 80 characters, for example
  "2023 Panini Prizm #301 C.J. Stroud Rookie RC Houston Texans".
  Use only facts printed on the card.
- search_query: short eBay search words to find this same card,
  for example "2023 Prizm 301 CJ Stroud". Skip team names.
- confidence: how sure you are about player, year, set, and number."""


def _image_block(path: Path) -> dict:
    data = to_jpeg_bytes(open_photo(path), max_side=1568, quality=88)
    return {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": "image/jpeg",
            "data": base64.standard_b64encode(data).decode("ascii"),
        },
    }


class CardReader:
    def __init__(self, client=None):
        if client is None:
            import anthropic

            client = anthropic.Anthropic()
        self.client = client

    def read(self, first: Path, second: Path) -> CardInfo:
        response = self.client.beta.messages.create(
            model=MODEL,
            max_tokens=16000,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            output_config={
                "effort": "medium",
                "format": {"type": "json_schema", "schema": _strict_schema()},
            },
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Photo 1:"},
                        _image_block(first),
                        {"type": "text", "text": "Photo 2:"},
                        _image_block(second),
                        {"type": "text", "text": PROMPT},
                    ],
                }
            ],
        )
        if response.stop_reason == "refusal":
            raise RuntimeError("Claude declined to read this card.")
        if response.stop_reason == "max_tokens":
            raise RuntimeError("Claude's answer was cut off.")
        text = "".join(b.text for b in response.content if getattr(b, "type", "") == "text")
        info = CardInfo.model_validate(json.loads(text))
        info.title = info.title.strip()[:80]
        return info

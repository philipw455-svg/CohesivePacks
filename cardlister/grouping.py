"""Groups photos into cards: each front photo with its matching back photo.

Claude reads every photo on its own first. The program then matches fronts to
backs by player name, set, and card number. When two backs fit one front, the
photo taken closest in time wins. Any photo without a match counts as a
one-sided card.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .identify import PhotoSide

# A front and back taken more than this many seconds apart cost extra in matching.
NEARBY_SECONDS = 600


@dataclass
class Photo:
    path: Path
    taken: datetime
    side: PhotoSide


@dataclass
class CardGroup:
    front: Path | None
    back: Path | None

    @property
    def photos(self) -> list[Path]:
        return [p for p in (self.front, self.back) if p]


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (text or "").lower())


def _last_name(name: str) -> str:
    words = re.findall(r"[a-z]+", (name or "").lower())
    words = [w for w in words if w not in ("jr", "sr", "ii", "iii", "iv")]
    return words[-1] if words else ""


def _match_cost(front: Photo, back: Photo) -> float | None:
    """Returns a cost for pairing these photos, or None when they cannot match."""
    f, b = front.side, back.side
    if not (_norm(f.player) and _norm(b.player)):
        return None
    if _norm(f.player) != _norm(b.player) and _last_name(f.player) != _last_name(b.player):
        return None
    if _norm(f.card_number) and _norm(b.card_number) and _norm(f.card_number) != _norm(b.card_number):
        return None
    if f.year[:4] and b.year[:4] and f.year[:4] != b.year[:4]:
        return None
    cost = abs((front.taken - back.taken).total_seconds())
    for field in ("manufacturer", "set_name"):
        fv, bv = _norm(getattr(f, field)), _norm(getattr(b, field))
        if fv and bv and fv not in bv and bv not in fv:
            cost += NEARBY_SECONDS
    return cost


def group_photos(photos: list[Photo]) -> list[CardGroup]:
    photos = sorted(photos, key=lambda p: (p.taken, p.path.name))
    fronts = [p for p in photos if p.side.side == "front"]
    backs = [p for p in photos if p.side.side == "back"]

    # Pass 1: match on what is printed on the card.
    options = []
    for fi, f in enumerate(fronts):
        for bi, b in enumerate(backs):
            cost = _match_cost(f, b)
            if cost is not None:
                options.append((cost, fi, bi))
    pairs: dict[int, int] = {}
    used_backs: set[int] = set()
    for cost, fi, bi in sorted(options):
        if fi not in pairs and bi not in used_backs:
            pairs[fi] = bi
            used_backs.add(bi)

    # Pass 2: a back with no readable name right after an unmatched front.
    order = {id(p): i for i, p in enumerate(photos)}
    for fi, f in enumerate(fronts):
        if fi in pairs:
            continue
        nxt = order[id(f)] + 1
        if nxt < len(photos):
            cand = photos[nxt]
            if cand.side.side in ("back", "unknown") and not _norm(cand.side.player):
                if cand.side.side == "back":
                    bi = backs.index(cand)
                    if bi not in used_backs:
                        pairs[fi] = bi
                        used_backs.add(bi)

    groups = [CardGroup(fronts[fi].path, backs[bi].path) for fi, bi in pairs.items()]
    groups += [CardGroup(f.path, None) for fi, f in enumerate(fronts) if fi not in pairs]
    groups += [CardGroup(None, b.path) for bi, b in enumerate(backs) if bi not in used_backs]
    groups += [CardGroup(p.path, None) for p in photos if p.side.side == "unknown"]
    taken = {p.path: p.taken for p in photos}
    return sorted(groups, key=lambda g: min(taken[p] for p in g.photos))

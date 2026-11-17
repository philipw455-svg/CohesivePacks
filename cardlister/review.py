"""Keeps the review sheet: one row per card, which you check before posting."""

from __future__ import annotations

import csv
from pathlib import Path

COLUMNS = [
    "approve", "status", "card_id", "sku", "title", "start_price",
    "quick_sale_value", "store_cash_estimate", "comps_found",
    "player", "year", "manufacturer", "set_name", "card_number", "team", "sport",
    "parallel", "insert_name", "serial_number", "rookie", "autographed", "memorabilia",
    "graded", "grader", "grade", "condition", "condition_notes", "confidence",
    "search_query", "front_photo", "back_photo", "raw_front", "raw_back",
    "listing_id", "listing_url", "error",
]


def read_rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as fh:
        return [dict(r) for r in csv.DictReader(fh)]


def write_rows(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({c: row.get(c, "") for c in COLUMNS})
    tmp.replace(path)


def next_card_number(rows: list[dict]) -> int:
    numbers = [int(r["card_id"]) for r in rows if str(r.get("card_id", "")).isdigit()]
    return max(numbers, default=0) + 1


def is_approved(row: dict) -> bool:
    return str(row.get("approve", "")).strip().lower() in ("yes", "y", "x", "1", "true")


def totals(rows: list[dict]) -> dict:
    def money(key):
        total = 0.0
        for r in rows:
            try:
                total += float(r.get(key) or 0)
            except ValueError:
                pass
        return round(total, 2)

    priced = sum(1 for r in rows if r.get("quick_sale_value"))
    return {
        "cards": len(rows),
        "priced": priced,
        "quick_sale_total": money("quick_sale_value"),
        "store_cash_total": money("store_cash_estimate"),
    }

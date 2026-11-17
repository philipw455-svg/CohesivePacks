"""Finds a card's most recent sold prices with Claude's web search.

Claude searches sold-listing sites such as eBay sold listings and 130point.
Claude reports each sale with a link, so you can check every price yourself.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field

from .identify import MODEL, CardInfo

MAX_CONTINUES = 5

REPORT_TOOL = {
    "name": "report_sales",
    "description": "Report the recent SOLD prices found for the card. Call this exactly once, "
                   "at the end, even when no sales were found.",
    "strict": True,
    "input_schema": {
        "type": "object",
        "properties": {
            "match": {
                "type": "string",
                "enum": ["exact", "close", "none"],
                "description": "exact: same card, parallel, and graded/raw status. "
                               "close: nearest similar card. none: no sales found.",
            },
            "sales": {
                "type": "array",
                "description": "Up to 5 most recent completed sales, newest first.",
                "items": {
                    "type": "object",
                    "properties": {
                        "price_usd": {"type": "number"},
                        "date": {"type": "string", "description": "YYYY-MM-DD if known."},
                        "title": {"type": "string"},
                        "url": {"type": "string"},
                    },
                    "required": ["price_usd", "date", "title", "url"],
                    "additionalProperties": False,
                },
            },
            "notes": {"type": "string"},
        },
        "required": ["match", "sales", "notes"],
        "additionalProperties": False,
    },
}

SEARCH_PROMPT = """Find the most recent SOLD prices for this exact sports card.
Card: {title}
Details: {details}

Rules:
- Use completed sales only, never asking prices of active listings.
- Good sources: eBay sold listings, 130point.com, Card Ladder, Goldin, Fanatics Collect.
- Match the year, set, card number, and parallel.
- The card is {grading}. Skip sales with a different grading status or grade.
- Skip lots and multi-card sales.
- Do not invent prices. Report only sales you saw in search results.
When done, call report_sales once."""


@dataclass
class SalesReport:
    match: str
    sales: list[dict] = field(default_factory=list)
    notes: str = ""

    @property
    def last_sale(self) -> dict | None:
        return self.sales[0] if self.sales else None

    @property
    def typical_price(self) -> float | None:
        """The middle price of the recent sales. Less swayed by one odd sale."""
        prices = [s["price_usd"] for s in self.sales if s.get("price_usd", 0) > 0]
        return round(statistics.median(prices), 2) if prices else None


def _details(info: CardInfo) -> str:
    parts = [
        f"player {info.player}", f"year {info.year}", f"maker {info.manufacturer}",
        f"set {info.set_name}", f"number {info.card_number}",
    ]
    if info.parallel:
        parts.append(f"parallel {info.parallel}")
    if info.insert_name:
        parts.append(f"insert {info.insert_name}")
    if info.serial_number:
        parts.append(f"serial numbered {info.serial_number}")
    if info.rookie:
        parts.append("rookie card")
    if info.autographed:
        parts.append("autographed")
    return ", ".join(p for p in parts if not p.endswith(" "))


class SaleFinder:
    def __init__(self, client, max_searches: int = 5):
        self.client = client
        self.tools = [
            {"type": "web_search_20260209", "name": "web_search", "max_uses": max_searches},
            REPORT_TOOL,
        ]

    def _create(self, messages):
        return self.client.beta.messages.create(
            model=MODEL,
            max_tokens=16000,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            output_config={"effort": "medium"},
            tools=self.tools,
            messages=messages,
        )

    def find(self, info: CardInfo) -> SalesReport:
        grading = f"graded {info.grader} {info.grade}".strip() if info.graded else "raw (ungraded)"
        prompt = SEARCH_PROMPT.format(title=info.title, details=_details(info), grading=grading)
        messages = [{"role": "user", "content": prompt}]
        asked_again = False
        for _ in range(MAX_CONTINUES + 2):
            response = self._create(messages)
            for block in response.content:
                if getattr(block, "type", "") == "tool_use" and block.name == "report_sales":
                    data = dict(block.input)
                    sales = [s for s in data.get("sales", []) if s.get("price_usd", 0) > 0]
                    return SalesReport(data.get("match", "none"), sales, data.get("notes", ""))
            if response.stop_reason == "refusal":
                raise RuntimeError("Claude declined the price search.")
            messages.append({"role": "assistant", "content": response.content})
            if response.stop_reason == "pause_turn":
                continue  # The search is still running. Send the turn back unchanged.
            if asked_again:
                break
            messages.append({"role": "user", "content": "Call report_sales now."})
            asked_again = True
        return SalesReport("none", [], "Claude did not report any sales.")

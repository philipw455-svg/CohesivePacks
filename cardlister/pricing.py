"""Turns eBay listing prices into a quick-sale value and a store cash estimate.

Important limits:
- eBay does not give most developers its sold-price data. So the program looks
  at current Buy It Now listings instead.
- Sellers often ask more than buyers pay. So the program uses the price at the
  bottom quarter of the matching listings as the quick-sale value.
- Store cash uses your STORE_CASH_RATE guess. Shops set their own offers.
"""

from __future__ import annotations

import re
import statistics
from dataclasses import dataclass

SLAB_WORDS = re.compile(r"\b(psa|bgs|sgc|cgc|csg|hga|beckett|graded)\b", re.I)
LOT_WORDS = re.compile(r"\b(lot|lots|set of|you pick|choose|pick your|\d+\s*cards?)\b", re.I)


@dataclass
class PriceEstimate:
    quick_sale: float | None
    comps_used: int
    low: float | None
    median: float | None


def clean_comps(results: list[tuple[str, float]], graded: bool) -> list[float]:
    prices = []
    for title, price in results:
        if LOT_WORDS.search(title):
            continue
        if not graded and SLAB_WORDS.search(title):
            continue
        if price > 0:
            prices.append(price)
    return sorted(prices)


def estimate(prices: list[float]) -> PriceEstimate:
    if not prices:
        return PriceEstimate(None, 0, None, None)
    if len(prices) < 4:
        quick = min(prices)
    else:
        quick = statistics.quantiles(prices, n=4, method="inclusive")[0]
    return PriceEstimate(round(quick, 2), len(prices), prices[0], round(statistics.median(prices), 2))


def store_cash(quick_sale: float | None, rate: float, bulk_threshold: float, bulk_cash: float) -> float:
    if quick_sale is None or quick_sale < bulk_threshold:
        return bulk_cash
    return round(quick_sale * rate, 2)


# eBay keeps about 13.25% of a trading card sale plus a small fee per order.
EBAY_FEE_RATE = 0.1325
EBAY_ORDER_FEE = 0.40
MIN_START = 0.99


def floor_start_price(store_cash: float, fee_rate: float = EBAY_FEE_RATE,
                      order_fee: float = EBAY_ORDER_FEE) -> float:
    """Returns the lowest start price that still pays you the store cash after eBay fees.

    Any winning bid at or above this price leaves you at least what a shop would pay.
    """
    needed = (store_cash + order_fee) / (1 - fee_rate)
    whole_cents = -(-round(needed * 100, 6) // 1)  # round up to the next cent
    return max(MIN_START, whole_cents / 100)


def net_after_fees(price: float, fee_rate: float = EBAY_FEE_RATE,
                   order_fee: float = EBAY_ORDER_FEE) -> float:
    return round(price * (1 - fee_rate) - order_fee, 2)

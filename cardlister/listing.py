"""Builds the eBay listing data for one card."""

from __future__ import annotations

import html

from .ebay import (
    CARD_CATEGORY_ID,
    CARD_CONDITION_DESCRIPTOR,
    CARD_CONDITION_VALUES,
    MARKETPLACE,
    UNGRADED_CONDITION,
)

CONDITION_LABELS = {
    "near_mint_or_better": "Near Mint or Better",
    "excellent": "Excellent",
    "very_good": "Very Good",
    "poor": "Poor",
}


def _yes_no(value) -> str:
    return "Yes" if str(value).strip().lower() in ("true", "yes", "1") else "No"


def aspects(row: dict) -> dict[str, list[str]]:
    pairs = {
        "Sport": row.get("sport"),
        "Player/Athlete": row.get("player"),
        "Season": row.get("year"),
        "Year Manufactured": (row.get("year") or "")[:4],
        "Manufacturer": row.get("manufacturer"),
        "Set": row.get("set_name"),
        "Card Number": row.get("card_number"),
        "Team": row.get("team"),
        "Parallel/Variety": row.get("parallel"),
        "Insert Set": row.get("insert_name"),
        "Print Run": row.get("serial_number"),
        "Autographed": _yes_no(row.get("autographed")),
        "Graded": "No",
        "Type": "Sports Trading Card",
        "Original/Licensed Reprint": "Original",
    }
    if _yes_no(row.get("rookie")) == "Yes":
        pairs["Features"] = "Rookie"
    return {k: [str(v).strip()] for k, v in pairs.items() if v and str(v).strip()}


def description(row: dict, shipping_note: str) -> str:
    lines = [
        f"<h2>{html.escape(row['title'])}</h2>",
        "<ul>",
        f"<li>Condition: Ungraded, {CONDITION_LABELS.get(row['condition'], row['condition'])}</li>",
    ]
    if row.get("condition_notes"):
        lines.append(f"<li>Notes: {html.escape(row['condition_notes'])}</li>")
    lines += [
        "</ul>",
        "<p>The photos show the actual card you will receive, front and back.</p>",
        f"<p>{html.escape(shipping_note)}</p>",
    ]
    return "\n".join(lines)


def inventory_item(row: dict, image_urls: list[str], shipping_note: str) -> dict:
    condition_code = CARD_CONDITION_VALUES[row["condition"]]
    return {
        "availability": {"shipToLocationAvailability": {"quantity": 1}},
        "condition": UNGRADED_CONDITION,
        "conditionDescriptors": [
            {"name": CARD_CONDITION_DESCRIPTOR, "values": [condition_code]}
        ],
        "product": {
            "title": row["title"][:80],
            "description": description(row, shipping_note),
            "aspects": aspects(row),
            "imageUrls": image_urls,
        },
    }


def auction_offer(row: dict, settings) -> dict:
    return {
        "sku": row["sku"],
        "marketplaceId": MARKETPLACE,
        "format": "AUCTION",
        "availableQuantity": 1,
        "categoryId": CARD_CATEGORY_ID,
        "listingDescription": description(row, settings.shipping_note),
        "listingDuration": f"DAYS_{settings.auction_days}",
        "merchantLocationKey": settings.location_key,
        "listingPolicies": {
            "paymentPolicyId": settings.payment_policy_id,
            "returnPolicyId": settings.return_policy_id,
            "fulfillmentPolicyId": settings.fulfillment_policy_id,
        },
        "pricingSummary": {
            "auctionStartPrice": {
                "value": f"{float(row['start_price']):.2f}",
                "currency": "USD",
            }
        },
    }

"""Builds the eBay listing data for one card."""

from __future__ import annotations

import html

from .ebay import (
    CARD_CATEGORY_ID,
    CARD_CONDITION_DESCRIPTOR,
    CARD_CONDITION_VALUES,
    CERT_DESCRIPTOR,
    GRADE_DESCRIPTOR,
    GRADE_VALUES,
    GRADED_CONDITION,
    GRADER_DESCRIPTOR,
    GRADER_VALUES,
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


def is_graded(row: dict) -> bool:
    return _yes_no(row.get("graded")) == "Yes"


def grade_key(row: dict) -> str:
    """Turns '9', 'Mint 9', 'GEM MT 10' or 'Authentic' into eBay's grade key."""
    text = str(row.get("grade", "")).strip().upper()
    if "AUTH" in text:
        return "AUTHENTIC"
    for token in text.replace("MINT", " ").split():
        try:
            number = float(token)
        except ValueError:
            continue
        return f"{number:g}"
    return ""


def grader_key(row: dict) -> str:
    return str(row.get("grader", "")).strip().upper()


def graded_problem(row: dict) -> str:
    """Returns why a graded card cannot be listed, or an empty string."""
    if grader_key(row) not in GRADER_VALUES:
        return f"Unknown grading company '{row.get('grader', '')}'."
    if grade_key(row) not in GRADE_VALUES:
        return f"Unknown grade '{row.get('grade', '')}'."
    return ""


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
        "Graded": "Yes" if is_graded(row) else "No",
        "Professional Grader": row.get("grader") if is_graded(row) else "",
        "Grade": row.get("grade") if is_graded(row) else "",
        "Certification Number": row.get("cert_number") if is_graded(row) else "",
        "Type": "Sports Trading Card",
        "Original/Licensed Reprint": "Original",
    }
    if _yes_no(row.get("rookie")) == "Yes":
        pairs["Features"] = "Rookie"
    return {k: [str(v).strip()] for k, v in pairs.items() if v and str(v).strip()}


def _condition_line(row: dict) -> str:
    if is_graded(row):
        text = f"Graded: {row.get('grader', '')} {row.get('grade', '')}".strip()
        if row.get("cert_number"):
            text += f", certification #{row['cert_number']}"
        return f"<li>{html.escape(text)}</li>"
    label = CONDITION_LABELS.get(row.get("condition", ""), row.get("condition", ""))
    return f"<li>Condition: Ungraded, {html.escape(label)}</li>"


def description(row: dict, shipping_note: str) -> str:
    lines = [
        f"<h2>{html.escape(row['title'])}</h2>",
        "<ul>",
        _condition_line(row),
    ]
    if row.get("condition_notes"):
        lines.append(f"<li>Notes: {html.escape(row['condition_notes'])}</li>")
    lines += [
        "</ul>",
        "<p>The photos show the actual card you will receive, front and back.</p>",
        f"<p>{html.escape(shipping_note)}</p>",
    ]
    return "\n".join(lines)


def condition_fields(row: dict) -> dict:
    if is_graded(row):
        problem = graded_problem(row)
        if problem:
            raise ValueError(problem)
        descriptors = [
            {"name": GRADER_DESCRIPTOR, "values": [GRADER_VALUES[grader_key(row)]]},
            {"name": GRADE_DESCRIPTOR, "values": [GRADE_VALUES[grade_key(row)]]},
        ]
        if row.get("cert_number"):
            descriptors.append({"name": CERT_DESCRIPTOR,
                                "additionalInfo": str(row["cert_number"])[:30]})
        return {"condition": GRADED_CONDITION, "conditionDescriptors": descriptors}
    condition_code = CARD_CONDITION_VALUES[row["condition"]]
    return {
        "condition": UNGRADED_CONDITION,
        "conditionDescriptors": [{"name": CARD_CONDITION_DESCRIPTOR, "values": [condition_code]}],
    }


def inventory_item(row: dict, image_urls: list[str], shipping_note: str) -> dict:
    return {
        "availability": {"shipToLocationAvailability": {"quantity": 1}},
        **condition_fields(row),
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

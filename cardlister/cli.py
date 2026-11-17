"""Commands you type to run the card lister.

  python -m cardlister login      Sign in to your eBay seller account (one time).
  python -m cardlister policies   Show your eBay payment, return, and shipping policy IDs.
  python -m cardlister location   Save your ship-from address on eBay (one time).
  python -m cardlister process    Edit, read, and price every photo pair in the inbox.
  python -m cardlister post       Post approved cards as eBay auctions.
  python -m cardlister summary    Show card counts and money totals.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from . import listing, pricing, review
from .config import Settings, load_settings
from .photos import find_photos, pair_photos


def _seller(s: Settings):
    from .ebay import EbaySeller

    missing = [n for n, v in (("EBAY_APP_ID", s.ebay_app_id), ("EBAY_CERT_ID", s.ebay_cert_id),
                              ("EBAY_RUNAME", s.ebay_runame)) if not v]
    if missing:
        raise SystemExit("Fill in these values in your .env file first: " + ", ".join(missing))
    return EbaySeller(s.ebay_env, s.ebay_app_id, s.ebay_cert_id, s.ebay_runame, s.token_file)


def cmd_login(s: Settings, _args) -> None:
    seller = _seller(s)
    print(f"Signing in to eBay {s.ebay_env}.")
    print("1. Open this address in your web browser:\n")
    print(seller.consent_url() + "\n")
    print("2. Sign in with your eBay seller account and click Agree.")
    print("3. Copy the full address from the browser bar on the page that opens next.")
    pasted = input("4. Paste that address here and press Enter: ")
    seller.finish_login(pasted)
    print("Done. The program saved your sign-in in tokens.json. Keep that file private.")


def cmd_policies(s: Settings, _args) -> None:
    found = _seller(s).list_policies()
    names = {"payment": "EBAY_PAYMENT_POLICY_ID", "return": "EBAY_RETURN_POLICY_ID",
             "fulfillment": "EBAY_FULFILLMENT_POLICY_ID"}
    for kind, items in found.items():
        print(f"\n{kind.title()} policies (copy one ID into {names[kind]}):")
        if not items:
            print("  None found. Create one in eBay Seller Hub > Account > Business policies.")
        for pid, name in items:
            print(f"  {pid}   {name}")


def cmd_location(s: Settings, _args) -> None:
    seller = _seller(s)
    print("Enter the address your cards ship from. Buyers see only the city and state.")
    city = input("City: ").strip()
    state = input("State (two letters, for example TX): ").strip()
    postal = input("ZIP code: ").strip()
    seller.create_location(s.location_key, city, state, postal)
    print(f"Saved ship-from location '{s.location_key}'.")


def _pricing_client(s: Settings):
    if not (s.pricing_app_id and s.pricing_cert_id):
        print("Note: no production keys for price lookups. Prices stay blank.")
        return None
    from .ebay import EbayPricing

    return EbayPricing("production", s.pricing_app_id, s.pricing_cert_id)


def _move(path: Path, folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    shutil.move(str(path), str(folder / path.name))


def cmd_process(s: Settings, args) -> None:
    from .editor import make_editor
    from .identify import CardReader

    if not s.anthropic_api_key:
        raise SystemExit("Fill in ANTHROPIC_API_KEY in your .env file first.")
    s.inbox_dir.mkdir(exist_ok=True)
    photos = find_photos(s.inbox_dir)
    pairs, leftover = pair_photos(photos)
    if leftover:
        print(f"Warning: {leftover.name} has no partner photo. The program skips it.")
    if not pairs:
        print(f"No photo pairs found. Put photos in {s.inbox_dir}")
        return
    if args.limit:
        pairs = pairs[: args.limit]

    import anthropic

    reader = CardReader(anthropic.Anthropic(api_key=s.anthropic_api_key))
    editor = make_editor(s.photoroom_api_key, s.studio_background)
    prices = _pricing_client(s)
    print(f"Found {len(pairs)} cards. Photo editor: {editor.name}.")

    rows = review.read_rows(s.review_csv)
    card_no = review.next_card_number(rows)
    for pair in pairs:
        card_id = f"{card_no:04d}"
        folder = s.output_dir / "cards" / f"card_{card_id}"
        folder.mkdir(parents=True, exist_ok=True)
        print(f"\nCard {card_id}: {pair.first.name} + {pair.second.name}")
        try:
            info = reader.read(pair.first, pair.second)
            front, back = (pair.first, pair.second) if info.front_photo == "first" \
                else (pair.second, pair.first)
            raw_front = folder / ("raw_front" + front.suffix.lower())
            raw_back = folder / ("raw_back" + back.suffix.lower())
            shutil.copy2(front, raw_front)
            shutil.copy2(back, raw_back)
            front_out = editor.edit(front, folder / "front.jpg")
            back_out = editor.edit(back, folder / "back.jpg")

            quick, comps = None, 0
            if prices and info.search_query:
                try:
                    found = prices.search_prices(info.search_query)
                    est = pricing.estimate(pricing.clean_comps(found, info.graded))
                    quick, comps = est.quick_sale, est.comps_used
                except Exception as exc:  # A price failure should not stop the card.
                    print(f"  Price lookup failed: {exc}")
            cash = pricing.store_cash(quick, s.store_cash_rate, s.bulk_threshold,
                                      s.bulk_cash_per_card)

            row = info.model_dump()
            row.update(
                card_id=card_id,
                sku=f"CP-{card_id}",
                start_price=f"{s.start_price:.2f}",
                quick_sale_value="" if quick is None else f"{quick:.2f}",
                store_cash_estimate=f"{cash:.2f}",
                comps_found=comps,
                front_photo=str(front_out),
                back_photo=str(back_out),
                raw_front=str(raw_front),
                raw_back=str(raw_back),
                approve="",
                status="graded: list by hand" if info.graded else "ready",
            )
            rows.append(row)
            _move(pair.first, s.inbox_dir / "done")
            _move(pair.second, s.inbox_dir / "done")
            value = f"${quick:.2f}" if quick is not None else "no price found"
            print(f"  {info.title}  |  quick sale {value}  |  store cash ${cash:.2f}"
                  f"  |  confidence {info.confidence}")
        except Exception as exc:
            print(f"  Failed: {exc}")
            rows.append({"card_id": card_id, "status": "error", "error": str(exc)[:500],
                         "raw_front": str(pair.first), "raw_back": str(pair.second)})
            _move(pair.first, s.inbox_dir / "failed")
            _move(pair.second, s.inbox_dir / "failed")
        review.write_rows(s.review_csv, rows)
        card_no += 1

    print(f"\nReview sheet saved: {s.review_csv}")
    print("Open it, check each card, and type 'yes' in the approve column.")
    _print_totals(rows)


def cmd_post(s: Settings, args) -> None:
    missing = [n for n, v in (("EBAY_PAYMENT_POLICY_ID", s.payment_policy_id),
                              ("EBAY_RETURN_POLICY_ID", s.return_policy_id),
                              ("EBAY_FULFILLMENT_POLICY_ID", s.fulfillment_policy_id)) if not v]
    if missing:
        raise SystemExit("Fill in these values first (run 'policies'): " + ", ".join(missing))
    seller = _seller(s)
    rows = review.read_rows(s.review_csv)
    todo = [r for r in rows if r.get("status") in ("ready", "error") and r.get("sku")
            and (review.is_approved(r) or (args.all_ready and r.get("status") == "ready"))]
    if not todo:
        print("No approved cards to post. Type 'yes' in the approve column first.")
        return
    print(f"Posting {len(todo)} auctions to eBay {s.ebay_env} "
          f"({s.auction_days} days each).")
    for row in todo:
        try:
            urls = [seller.upload_photo(Path(row["front_photo"])),
                    seller.upload_photo(Path(row["back_photo"]))]
            seller.put_inventory_item(row["sku"], listing.inventory_item(row, urls, s.shipping_note))
            offer_id = seller.create_or_update_offer(listing.auction_offer(row, s))
            listing_id = seller.publish_offer(offer_id)
            row.update(status="listed", listing_id=listing_id,
                       listing_url=seller.listing_url(listing_id), error="")
            print(f"  Listed {row['sku']}: {row['listing_url']}")
        except Exception as exc:
            row.update(status="error", error=str(exc)[:500])
            print(f"  Failed {row['sku']}: {exc}")
        review.write_rows(s.review_csv, rows)


def _print_totals(rows: list[dict]) -> None:
    t = review.totals([r for r in rows if r.get("status") != "error"])
    print(f"\nCards: {t['cards']} ({t['priced']} with a price found)")
    print(f"Quick-sale value total:   ${t['quick_sale_total']:.2f}")
    print(f"Store cash estimate total: ${t['store_cash_total']:.2f}")
    print("These totals are rough guesses. See README for how the program makes them.")


def cmd_summary(s: Settings, _args) -> None:
    _print_totals(review.read_rows(s.review_csv))


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="cardlister", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("login")
    sub.add_parser("policies")
    sub.add_parser("location")
    p = sub.add_parser("process")
    p.add_argument("--limit", type=int, default=0, help="Process only this many cards.")
    p = sub.add_parser("post")
    p.add_argument("--all-ready", action="store_true",
                   help="Post every 'ready' card without the approve column.")
    sub.add_parser("summary")
    args = parser.parse_args(argv)
    handlers = {"login": cmd_login, "policies": cmd_policies, "location": cmd_location,
                "process": cmd_process, "post": cmd_post, "summary": cmd_summary}
    try:
        handlers[args.command](load_settings(), args)
    except KeyboardInterrupt:
        sys.exit(1)

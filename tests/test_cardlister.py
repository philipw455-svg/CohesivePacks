import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from PIL import Image

from cardlister import listing, pricing, review
from cardlister.config import load_settings
from cardlister.ebay import EbaySeller
from cardlister.editor import LocalEditor
from cardlister.identify import CardReader
from cardlister.photos import find_photos, pair_photos

CARD_JSON = {
    "front_photo": "second", "sport": "Football", "year": "2023", "manufacturer": "Panini",
    "set_name": "Prizm", "card_number": "301", "player": "C.J. Stroud", "team": "Houston Texans",
    "parallel": "", "insert_name": "", "serial_number": "", "rookie": True,
    "autographed": False, "memorabilia": False, "graded": False, "grader": "", "grade": "",
    "condition": "near_mint_or_better", "condition_notes": "Light edge wear.",
    "title": "2023 Panini Prizm #301 C.J. Stroud Rookie RC Houston Texans " + "x" * 40,
    "search_query": "2023 Prizm 301 CJ Stroud", "confidence": "high",
}


def make_photo(path: Path, color, mtime: float) -> Path:
    Image.new("RGB", (300, 420), color).save(path, "JPEG")
    os.utime(path, (mtime, mtime))
    return path


class FakeClaude:
    def __init__(self, payload, stop_reason="end_turn"):
        self.calls = []
        block = SimpleNamespace(type="text", text=json.dumps(payload))
        resp = SimpleNamespace(content=[block], stop_reason=stop_reason)
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))
        self._resp = resp

    def _create(self, **kw):
        self.calls.append(kw)
        return self._resp


class PhotoTests(unittest.TestCase):
    def test_pairs_in_capture_order_and_reports_leftover(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            now = time.time()
            c = make_photo(d / "IMG_3.jpg", "blue", now + 30)
            a = make_photo(d / "IMG_1.jpg", "red", now + 10)
            b = make_photo(d / "IMG_2.jpg", "green", now + 20)
            pairs, leftover = pair_photos(find_photos(d))
            self.assertEqual((pairs[0].first, pairs[0].second), (a, b))
            self.assertEqual(leftover, c)

    def test_local_editor_writes_jpeg(self):
        with tempfile.TemporaryDirectory() as d:
            src = make_photo(Path(d) / "a.jpg", (60, 40, 30), time.time())
            out = LocalEditor().edit(src, Path(d) / "out.jpg")
            self.assertEqual(Image.open(out).format, "JPEG")


class IdentifyTests(unittest.TestCase):
    def test_reads_card_and_trims_title(self):
        with tempfile.TemporaryDirectory() as d:
            a = make_photo(Path(d) / "a.jpg", "red", time.time())
            b = make_photo(Path(d) / "b.jpg", "blue", time.time())
            fake = FakeClaude(CARD_JSON)
            info = CardReader(fake).read(a, b)
            self.assertEqual(info.player, "C.J. Stroud")
            self.assertLessEqual(len(info.title), 80)
            call = fake.calls[0]
            self.assertEqual(call["model"], "claude-opus-5-5")
            self.assertEqual(call["output_config"]["format"]["type"], "json_schema")
            images = [c for c in call["messages"][0]["content"] if c["type"] == "image"]
            self.assertEqual(len(images), 2)

    def test_refusal_raises(self):
        with tempfile.TemporaryDirectory() as d:
            a = make_photo(Path(d) / "a.jpg", "red", time.time())
            with self.assertRaises(RuntimeError):
                CardReader(FakeClaude(CARD_JSON, "refusal")).read(a, a)


class PricingTests(unittest.TestCase):
    def test_filters_slabs_and_lots(self):
        found = [("2023 Prizm Stroud PSA 10", 300.0), ("Stroud lot 5 cards", 10.0),
                 ("2023 Prizm Stroud RC", 8.0), ("2023 Prizm #301 Stroud", 12.0)]
        self.assertEqual(pricing.clean_comps(found, graded=False), [8.0, 12.0])

    def test_quick_sale_uses_bottom_quarter(self):
        est = pricing.estimate([4.0, 5.0, 6.0, 10.0, 20.0])
        self.assertEqual(est.quick_sale, 5.0)
        self.assertEqual(est.median, 6.0)
        self.assertIsNone(pricing.estimate([]).quick_sale)

    def test_store_cash(self):
        self.assertEqual(pricing.store_cash(20.0, 0.5, 3.0, 0.05), 10.0)
        self.assertEqual(pricing.store_cash(1.0, 0.5, 3.0, 0.05), 0.05)
        self.assertEqual(pricing.store_cash(None, 0.5, 3.0, 0.05), 0.05)


class ListingTests(unittest.TestCase):
    def setUp(self):
        self.row = {k: str(v) for k, v in CARD_JSON.items()}
        self.row.update(sku="CP-0001", start_price="0.99", title="2023 Prizm Stroud RC")

    def test_inventory_item(self):
        item = listing.inventory_item(self.row, ["u1", "u2"], "Ships fast.")
        self.assertEqual(item["condition"], "USED_VERY_GOOD")
        self.assertEqual(item["conditionDescriptors"][0]["values"], ["400010"])
        self.assertEqual(item["product"]["aspects"]["Features"], ["Rookie"])
        self.assertNotIn("Parallel/Variety", item["product"]["aspects"])

    def test_auction_offer(self):
        with mock.patch.dict(os.environ, {"AUCTION_DAYS": "3", "EBAY_PAYMENT_POLICY_ID": "p"}):
            offer = listing.auction_offer(self.row, load_settings())
        self.assertEqual(offer["format"], "AUCTION")
        self.assertEqual(offer["listingDuration"], "DAYS_3")
        self.assertEqual(offer["pricingSummary"]["auctionStartPrice"]["value"], "0.99")


class GradedAndFloorTests(unittest.TestCase):
    def test_graded_psa_card(self):
        row = {k: str(v) for k, v in CARD_JSON.items()}
        row.update(graded="yes", grader="PSA", grade="Mint 9", cert_number="52455911",
                   sku="CP-1", title="t")
        item = listing.inventory_item(row, ["u"], "")
        self.assertEqual(item["condition"], "LIKE_NEW")
        names = {d["name"]: d for d in item["conditionDescriptors"]}
        self.assertEqual(names["27501"]["values"], ["275010"])
        self.assertEqual(names["27502"]["values"], ["275022"])
        self.assertEqual(names["27503"]["additionalInfo"], "52455911")
        self.assertEqual(item["product"]["aspects"]["Grade"], ["Mint 9"])

    def test_cgc_authentic_and_bad_grader(self):
        row = {"graded": "yes", "grader": "CGC", "grade": "Authentic"}
        self.assertEqual(listing.condition_fields(row)["conditionDescriptors"][1]["values"],
                         ["2750219"])
        self.assertTrue(listing.graded_problem({"graded": "yes", "grader": "XYZ", "grade": "9"}))

    def test_floor_start_price_keeps_store_cash(self):
        for cash in (0.05, 2.0, 12.5, 100.0):
            start = pricing.floor_start_price(cash)
            self.assertGreaterEqual(start, 0.99)
            if start > 0.99:
                self.assertGreaterEqual(pricing.net_after_fees(start), cash)
                self.assertLess(pricing.net_after_fees(start - 0.02), cash)


class ImportTests(unittest.TestCase):
    def test_imports_card_list_with_any_photo_ending(self):
        from cardlister import cli, config

        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            inbox = d / "inbox" / "phone"
            inbox.mkdir(parents=True)
            make_photo(inbox / "IMG_1.JPG", "red", time.time())
            make_photo(inbox / "IMG_2.jpeg", "blue", time.time())
            card_list = d / "cards.csv"
            row = {k: str(v) for k, v in CARD_JSON.items()}
            row.update(front_name="IMG_1", back_name="IMG_2", start_price="8.54",
                       title="2023 Prizm Stroud RC", graded="", store_cash_estimate="7.00")
            review.write_rows(card_list, [row])
            orig = config.load_settings

            def patched():
                s = orig()
                s.inbox_dir, s.output_dir, s.photoroom_api_key = d / "inbox", d / "out", ""
                return s

            with mock.patch.object(cli, "load_settings", patched):
                cli.main(["import", str(card_list)])
                cli.main(["import", str(card_list)])  # A second run adds nothing.
            rows = review.read_rows(d / "out" / "review.csv")
            self.assertEqual(len(rows), 1)
            self.assertEqual((rows[0]["status"], rows[0]["start_price"]), ("ready", "8.54"))
            self.assertTrue(Path(rows[0]["front_photo"]).exists())


class ReviewTests(unittest.TestCase):
    def test_round_trip_and_totals(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "review.csv"
            rows = [{"card_id": "0001", "approve": "Yes", "quick_sale_value": "5.00",
                     "store_cash_estimate": "2.50"},
                    {"card_id": "0002", "quick_sale_value": "", "store_cash_estimate": "0.05"}]
            review.write_rows(path, rows)
            back = review.read_rows(path)
            self.assertTrue(review.is_approved(back[0]))
            self.assertFalse(review.is_approved(back[1]))
            self.assertEqual(review.next_card_number(back), 3)
            t = review.totals(back)
            self.assertEqual((t["quick_sale_total"], t["store_cash_total"]), (5.0, 2.55))


class FakeResponse:
    def __init__(self, status, body=None, headers=None):
        self.status_code, self._body = status, body or {}
        self.headers = headers or {}
        self.content = json.dumps(self._body).encode() if body is not None else b""
        self.text = json.dumps(self._body)

    def json(self):
        return self._body


class SellerTests(unittest.TestCase):
    def test_login_refresh_and_publish_flow(self):
        calls = []

        def fake_request(method, url, **kw):
            calls.append((method, url))
            if url.endswith("/identity/v1/oauth2/token"):
                return FakeResponse(200, {"access_token": "AT", "expires_in": 7200,
                                          "refresh_token": "RT"})
            if "create_image_from_file" in url:
                return FakeResponse(201, None, {"Location": "https://x/image/IMG1"})
            if url.endswith("/image/IMG1"):
                return FakeResponse(200, {"imageUrl": "https://i.ebayimg.com/1.jpg"})
            if method == "GET" and url.endswith("/offer"):
                return FakeResponse(200, {"offers": []})
            if method == "POST" and url.endswith("/offer"):
                return FakeResponse(201, {"offerId": "OF1"})
            if url.endswith("/publish"):
                return FakeResponse(200, {"listingId": "123"})
            return FakeResponse(204)

        with tempfile.TemporaryDirectory() as d:
            session = SimpleNamespace(request=fake_request)
            seller = EbaySeller("sandbox", "app", "cert", "ru", Path(d) / "t.json", session)
            self.assertIn("auth.sandbox.ebay.com", seller.consent_url())
            seller.finish_login("https://x/accepted?code=ABC&expires_in=299")
            photo = make_photo(Path(d) / "f.jpg", "red", time.time())
            self.assertEqual(seller.upload_photo(photo), "https://i.ebayimg.com/1.jpg")
            seller.put_inventory_item("CP-1", {})
            offer_id = seller.create_or_update_offer({"sku": "CP-1"})
            self.assertEqual(seller.publish_offer(offer_id), "123")
            self.assertTrue(all("sandbox" in u for _, u in calls))


if __name__ == "__main__":
    unittest.main()


def side(kind, player="", number="", year="", maker="", set_name=""):
    from cardlister.identify import PhotoSide

    return PhotoSide(side=kind, player=player, team="", year=year, manufacturer=maker,
                     set_name=set_name, card_number=number, parallel="")


class GroupingTests(unittest.TestCase):
    def test_matches_fronts_and_backs_in_any_order(self):
        from datetime import datetime, timedelta

        from cardlister.grouping import Photo, group_photos

        t0 = datetime(2026, 11, 1, 12, 0, 0)
        at = lambda sec: t0 + timedelta(seconds=sec)
        photos = [
            Photo(Path("a.jpg"), at(0), side("front", "Patrick Mahomes II", set_name="Prizm")),
            Photo(Path("b.jpg"), at(5), side("front", "Josh Allen")),
            Photo(Path("c.jpg"), at(10), side("back", "Josh Allen", "12", "2022")),
            Photo(Path("d.jpg"), at(15), side("back", "Patrick Mahomes", "1", "2023", "Panini",
                                              "Prizm")),
            Photo(Path("e.jpg"), at(20), side("front", "Josh Allen")),  # a second Allen card
            Photo(Path("f.jpg"), at(25), side("front", "Puka Nacua")),
            Photo(Path("g.jpg"), at(30), side("back", "")),  # back with no name printed
            Photo(Path("h.jpg"), at(40), side("back", "Bijan Robinson", "5")),
        ]
        groups = {(g.front.name if g.front else None, g.back.name if g.back else None)
                  for g in group_photos(photos)}
        self.assertEqual(groups, {("a.jpg", "d.jpg"), ("b.jpg", "c.jpg"), ("e.jpg", None),
                                  ("f.jpg", "g.jpg"), (None, "h.jpg")})

    def test_different_card_numbers_never_match(self):
        from datetime import datetime

        from cardlister.grouping import Photo, group_photos

        now = datetime(2026, 1, 1)
        photos = [Photo(Path("a.jpg"), now, side("front", "Josh Allen", "12")),
                  Photo(Path("b.jpg"), now, side("back", "Josh Allen", "99"))]
        self.assertEqual(len(group_photos(photos)), 2)


class FakeSalesClient:
    """Pauses once, then reports sales through the report_sales tool."""

    def __init__(self):
        self.calls = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **kw):
        self.calls.append(kw)
        if len(self.calls) == 1:
            block = SimpleNamespace(type="server_tool_use", name="web_search")
            return SimpleNamespace(content=[block], stop_reason="pause_turn")
        tool = SimpleNamespace(type="tool_use", name="report_sales", input={
            "match": "exact", "notes": "",
            "sales": [{"price_usd": 12.0, "date": "2026-11-10", "title": "t", "url": "u1"},
                      {"price_usd": 8.0, "date": "2026-11-02", "title": "t", "url": "u2"},
                      {"price_usd": 10.0, "date": "2026-10-28", "title": "t", "url": "u3"}]})
        return SimpleNamespace(content=[tool], stop_reason="tool_use")


class SalesTests(unittest.TestCase):
    def test_resumes_pause_and_reads_report(self):
        from cardlister.identify import CardInfo
        from cardlister.sales import SaleFinder

        client = FakeSalesClient()
        report = SaleFinder(client).find(CardInfo.model_validate(CARD_JSON))
        self.assertEqual(report.last_sale["price_usd"], 12.0)
        self.assertEqual(report.typical_price, 10.0)
        self.assertEqual(len(client.calls), 2)
        self.assertEqual(client.calls[1]["messages"][-1]["role"], "assistant")
        tool_types = [t.get("type", t.get("name")) for t in client.calls[0]["tools"]]
        self.assertIn("web_search_20260209", tool_types)
        self.assertIn("raw (ungraded)", client.calls[0]["messages"][0]["content"])


class ScanTests(unittest.TestCase):
    def test_scan_groups_values_and_leaves_photos(self):
        import csv
        import sys
        import types

        from cardlister import cli, config
        from cardlister.identify import CardReader, PhotoReader

        sides = {"IMG_0.jpg": side("back", "C.J. Stroud", "301"),
                 "IMG_1.jpg": side("front", "C.J. Stroud"),
                 "IMG_2.jpg": side("front", "Bryce Young")}
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "inbox").mkdir()
            for i in range(3):
                make_photo(d / "inbox" / f"IMG_{i}.jpg", "red", time.time() + i)
            orig = config.load_settings

            def patched():
                s = orig()
                s.inbox_dir, s.output_dir = d / "inbox", d / "output"
                return s

            fake_mod = types.ModuleType("anthropic")
            fake_mod.Anthropic = lambda **kw: FakeSalesClient()
            env = {"ANTHROPIC_API_KEY": "x", "STORE_CASH_RATE": "0.5"}
            with mock.patch.dict(sys.modules, {"anthropic": fake_mod}), \
                    mock.patch.dict(os.environ, env), \
                    mock.patch.object(cli, "load_settings", patched), \
                    mock.patch.object(PhotoReader, "read", lambda self, p: sides[p.name]), \
                    mock.patch.object(CardReader, "read",
                                      lambda self, a, b: __import__("cardlister.identify")
                                      .identify.CardInfo.model_validate(CARD_JSON)), \
                    mock.patch.object(CardReader, "read_one",
                                      lambda self, a: __import__("cardlister.identify")
                                      .identify.CardInfo.model_validate(CARD_JSON)):
                cli.main(["scan"])

            with (d / "output" / "values.csv").open(encoding="utf-8-sig") as fh:
                rows = list(csv.DictReader(fh))
            self.assertEqual(len(rows), 2)
            self.assertEqual((rows[0]["front_photo"], rows[0]["back_photo"]),
                             ("IMG_1.jpg", "IMG_0.jpg"))
            self.assertEqual(rows[0]["last_sale_price"], "12.00")
            self.assertEqual(rows[0]["sold_median"], "10.00")
            self.assertEqual(rows[0]["store_cash_estimate"], "5.00")
            self.assertEqual(rows[1]["back_photo"], "")
            self.assertEqual(len(list((d / "inbox").glob("*.jpg"))), 3)


if __name__ == "__main__":
    unittest.main()

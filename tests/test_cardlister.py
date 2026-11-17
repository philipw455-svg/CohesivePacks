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

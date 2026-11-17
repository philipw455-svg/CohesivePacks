"""Talks to eBay: sign-in, price lookups, photo uploads, and auction listings.

Each eBay host and field name here follows eBay's public REST APIs.
Test in the sandbox (EBAY_ENV=sandbox) before you switch to production.
"""

from __future__ import annotations

import base64
import json
import time
import urllib.parse
from pathlib import Path

import requests

HOSTS = {
    "production": {
        "api": "https://api.ebay.com",
        "media": "https://apim.ebay.com",
        "auth": "https://auth.ebay.com",
    },
    "sandbox": {
        "api": "https://api.sandbox.ebay.com",
        "media": "https://apim.sandbox.ebay.com",
        "auth": "https://auth.sandbox.ebay.com",
    },
}

SELL_SCOPES = [
    "https://api.ebay.com/oauth/api_scope",
    "https://api.ebay.com/oauth/api_scope/sell.inventory",
    "https://api.ebay.com/oauth/api_scope/sell.account",
]
PUBLIC_SCOPE = "https://api.ebay.com/oauth/api_scope"

MARKETPLACE = "EBAY_US"
# eBay category "Sports Trading Card Singles".
CARD_CATEGORY_ID = "261328"

# eBay condition codes for ungraded trading cards.
UNGRADED_CONDITION = "USED_VERY_GOOD"  # eBay shows this as "Ungraded" for cards.
CARD_CONDITION_DESCRIPTOR = "40001"
CARD_CONDITION_VALUES = {
    "near_mint_or_better": "400010",
    "excellent": "400011",
    "very_good": "400012",
    "poor": "400013",
}


class EbayError(RuntimeError):
    pass


def _basic_auth(app_id: str, cert_id: str) -> str:
    return "Basic " + base64.b64encode(f"{app_id}:{cert_id}".encode()).decode()


class EbayApp:
    """Base helper that sends requests with retries."""

    def __init__(self, env: str, session=None):
        self.env = env
        self.hosts = HOSTS[env]
        self.http = session or requests.Session()

    def _send(self, method: str, url: str, **kw) -> requests.Response:
        for attempt in range(4):
            resp = self.http.request(method, url, timeout=60, **kw)
            if resp.status_code in (429, 500, 502, 503, 504) and attempt < 3:
                time.sleep(2 ** attempt)
                continue
            return resp
        return resp


class EbayPricing(EbayApp):
    """Searches current eBay listings. This needs only the app keys."""

    def __init__(self, env: str, app_id: str, cert_id: str, session=None):
        super().__init__(env, session)
        self.app_id, self.cert_id = app_id, cert_id
        self._token, self._expires = "", 0.0

    def _app_token(self) -> str:
        if self._token and time.time() < self._expires - 60:
            return self._token
        resp = self._send(
            "POST",
            self.hosts["api"] + "/identity/v1/oauth2/token",
            headers={
                "Authorization": _basic_auth(self.app_id, self.cert_id),
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={"grant_type": "client_credentials", "scope": PUBLIC_SCOPE},
        )
        if resp.status_code != 200:
            raise EbayError(f"eBay rejected the pricing keys: {resp.text[:300]}")
        body = resp.json()
        self._token = body["access_token"]
        self._expires = time.time() + int(body.get("expires_in", 7200))
        return self._token

    def search_prices(self, query: str, limit: int = 50) -> list[tuple[str, float]]:
        """Returns (title, total price) for Buy It Now listings that match."""
        resp = self._send(
            "GET",
            self.hosts["api"] + "/buy/browse/v1/item_summary/search",
            headers={
                "Authorization": "Bearer " + self._app_token(),
                "X-EBAY-C-MARKETPLACE-ID": MARKETPLACE,
            },
            params={
                "q": query,
                "category_ids": CARD_CATEGORY_ID,
                "filter": "buyingOptions:{FIXED_PRICE},priceCurrency:USD",
                "limit": str(limit),
            },
        )
        if resp.status_code != 200:
            raise EbayError(f"eBay price search failed: {resp.text[:300]}")
        results = []
        for item in resp.json().get("itemSummaries", []):
            try:
                price = float(item["price"]["value"])
            except (KeyError, ValueError):
                continue
            ship = 0.0
            for option in item.get("shippingOptions", [])[:1]:
                try:
                    ship = float(option["shippingCost"]["value"])
                except (KeyError, ValueError):
                    pass
            results.append((item.get("title", ""), price + ship))
        return results


class EbaySeller(EbayApp):
    """Acts on your seller account. This needs your one-time sign-in."""

    def __init__(self, env, app_id, cert_id, runame, token_file: Path, session=None):
        super().__init__(env, session)
        self.app_id, self.cert_id, self.runame = app_id, cert_id, runame
        self.token_file = token_file

    # ---- Sign-in ----
    def consent_url(self) -> str:
        query = urllib.parse.urlencode(
            {
                "client_id": self.app_id,
                "redirect_uri": self.runame,
                "response_type": "code",
                "scope": " ".join(SELL_SCOPES),
            }
        )
        return self.hosts["auth"] + "/oauth2/authorize?" + query

    def _token_request(self, data: dict) -> dict:
        resp = self._send(
            "POST",
            self.hosts["api"] + "/identity/v1/oauth2/token",
            headers={
                "Authorization": _basic_auth(self.app_id, self.cert_id),
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data=data,
        )
        if resp.status_code != 200:
            raise EbayError(f"eBay sign-in failed: {resp.text[:300]}")
        return resp.json()

    def finish_login(self, pasted: str) -> None:
        """Takes the address eBay showed after you agreed, or just the code in it."""
        code = pasted.strip()
        if "code=" in code:
            code = urllib.parse.parse_qs(urllib.parse.urlparse(code).query)["code"][0]
        body = self._token_request(
            {"grant_type": "authorization_code", "code": code, "redirect_uri": self.runame}
        )
        self._save_tokens(body)

    def _save_tokens(self, body: dict) -> None:
        stored = self._load_tokens()
        stored[self.env] = {
            "access_token": body["access_token"],
            "access_expires": time.time() + int(body.get("expires_in", 7200)),
            "refresh_token": body.get("refresh_token")
            or stored.get(self.env, {}).get("refresh_token"),
        }
        self.token_file.write_text(json.dumps(stored, indent=2))

    def _load_tokens(self) -> dict:
        if self.token_file.exists():
            return json.loads(self.token_file.read_text())
        return {}

    def _user_token(self) -> str:
        tokens = self._load_tokens().get(self.env)
        if not tokens or not tokens.get("refresh_token"):
            raise EbayError("You have not signed in to eBay yet. Run: python -m cardlister login")
        if time.time() < tokens["access_expires"] - 120:
            return tokens["access_token"]
        body = self._token_request(
            {
                "grant_type": "refresh_token",
                "refresh_token": tokens["refresh_token"],
                "scope": " ".join(SELL_SCOPES),
            }
        )
        self._save_tokens(body)
        return body["access_token"]

    def _call(self, method, path, host="api", json_body=None, ok=(200, 201, 204), **kw):
        headers = {
            "Authorization": "Bearer " + self._user_token(),
            "Accept": "application/json",
            "Content-Language": "en-US",
        }
        if json_body is not None:
            headers["Content-Type"] = "application/json"
            kw["data"] = json.dumps(json_body)
        headers.update(kw.pop("headers", {}))
        resp = self._send(method, self.hosts[host] + path, headers=headers, **kw)
        if resp.status_code not in ok:
            raise EbayError(f"{method} {path} failed ({resp.status_code}): {resp.text[:500]}")
        return resp

    # ---- Account setup ----
    def list_policies(self) -> dict[str, list[tuple[str, str]]]:
        found = {}
        for kind in ("payment", "return", "fulfillment"):
            body = self._call(
                "GET", f"/sell/account/v1/{kind}_policy", params={"marketplace_id": MARKETPLACE}
            ).json()
            found[kind] = [
                (p.get(f"{kind}PolicyId", ""), p.get("name", ""))
                for p in body.get(f"{kind}Policies", [])
            ]
        return found

    def create_location(self, key: str, city: str, state: str, postal: str) -> None:
        self._call(
            "POST",
            f"/sell/inventory/v1/location/{urllib.parse.quote(key)}",
            json_body={
                "location": {
                    "address": {
                        "city": city,
                        "stateOrProvince": state,
                        "postalCode": postal,
                        "country": "US",
                    }
                },
                "locationTypes": ["WAREHOUSE"],
                "name": "Ship-from location",
                "merchantLocationStatus": "ENABLED",
            },
        )

    # ---- Listing ----
    def upload_photo(self, path: Path) -> str:
        """Uploads one photo to eBay's photo host and returns its web address."""
        with path.open("rb") as fh:
            resp = self._call(
                "POST",
                "/commerce/media/v1_beta/image/create_image_from_file",
                host="media",
                files={"image": (path.name, fh, "image/jpeg")},
            )
        body = resp.json() if resp.content else {}
        if body.get("imageUrl"):
            return body["imageUrl"]
        location = resp.headers.get("Location", "")
        if not location:
            raise EbayError(f"eBay did not return an address for {path.name}.")
        image_id = location.rstrip("/").split("/")[-1]
        body = self._call("GET", f"/commerce/media/v1_beta/image/{image_id}", host="media").json()
        return body["imageUrl"]

    def put_inventory_item(self, sku: str, item: dict) -> None:
        self._call("PUT", f"/sell/inventory/v1/inventory_item/{urllib.parse.quote(sku)}",
                   json_body=item)

    def create_or_update_offer(self, offer: dict) -> str:
        existing = self._call(
            "GET", "/sell/inventory/v1/offer", params={"sku": offer["sku"]}, ok=(200, 404)
        )
        offers = existing.json().get("offers", []) if existing.status_code == 200 else []
        if offers:
            offer_id = offers[0]["offerId"]
            self._call("PUT", f"/sell/inventory/v1/offer/{offer_id}", json_body=offer)
            return offer_id
        return self._call("POST", "/sell/inventory/v1/offer", json_body=offer).json()["offerId"]

    def publish_offer(self, offer_id: str) -> str:
        body = self._call("POST", f"/sell/inventory/v1/offer/{offer_id}/publish").json()
        return body["listingId"]

    def listing_url(self, listing_id: str) -> str:
        if self.env == "sandbox":
            return f"https://sandbox.ebay.com/itm/{listing_id}"
        return f"https://www.ebay.com/itm/{listing_id}"

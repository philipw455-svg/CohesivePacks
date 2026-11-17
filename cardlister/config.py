"""Loads settings from the .env file."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_env_file() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(ROOT / ".env")


def _f(name: str, default: str) -> float:
    return float(os.environ.get(name, default) or default)


@dataclass
class Settings:
    ebay_env: str
    ebay_app_id: str
    ebay_cert_id: str
    ebay_dev_id: str
    ebay_runame: str
    pricing_app_id: str
    pricing_cert_id: str
    payment_policy_id: str
    return_policy_id: str
    fulfillment_policy_id: str
    location_key: str
    anthropic_api_key: str
    photoroom_api_key: str
    studio_background: str
    auction_days: int
    start_price: float
    store_cash_rate: float
    bulk_threshold: float
    bulk_cash_per_card: float
    shipping_note: str
    inbox_dir: Path
    output_dir: Path
    token_file: Path

    @property
    def review_csv(self) -> Path:
        return self.output_dir / "review.csv"


def load_settings() -> Settings:
    _load_env_file()
    env = os.environ.get
    ebay_env = (env("EBAY_ENV") or "sandbox").strip().lower()
    if ebay_env not in ("sandbox", "production"):
        raise SystemExit("EBAY_ENV must be 'sandbox' or 'production'.")
    app_id = env("EBAY_APP_ID", "")
    cert_id = env("EBAY_CERT_ID", "")
    pricing_app = env("PRICING_APP_ID", "") or (app_id if ebay_env == "production" else "")
    pricing_cert = env("PRICING_CERT_ID", "") or (cert_id if ebay_env == "production" else "")
    days = int(env("AUCTION_DAYS", "3") or 3)
    if days not in (1, 3, 5, 7, 10):
        raise SystemExit("AUCTION_DAYS must be 1, 3, 5, 7, or 10.")
    return Settings(
        ebay_env=ebay_env,
        ebay_app_id=app_id,
        ebay_cert_id=cert_id,
        ebay_dev_id=env("EBAY_DEV_ID", ""),
        ebay_runame=env("EBAY_RUNAME", ""),
        pricing_app_id=pricing_app,
        pricing_cert_id=pricing_cert,
        payment_policy_id=env("EBAY_PAYMENT_POLICY_ID", ""),
        return_policy_id=env("EBAY_RETURN_POLICY_ID", ""),
        fulfillment_policy_id=env("EBAY_FULFILLMENT_POLICY_ID", ""),
        location_key=env("EBAY_LOCATION_KEY", "home") or "home",
        anthropic_api_key=env("ANTHROPIC_API_KEY", ""),
        photoroom_api_key=env("PHOTOROOM_API_KEY", ""),
        studio_background=(env("STUDIO_BACKGROUND", "FFFFFF") or "FFFFFF").lstrip("#"),
        auction_days=days,
        start_price=_f("START_PRICE", "0.99"),
        store_cash_rate=_f("STORE_CASH_RATE", "0.50"),
        bulk_threshold=_f("BULK_THRESHOLD", "3.00"),
        bulk_cash_per_card=_f("BULK_CASH_PER_CARD", "0.05"),
        shipping_note=env("SHIPPING_NOTE", "Ships in a penny sleeve and top loader."),
        inbox_dir=ROOT / "inbox",
        output_dir=ROOT / "output",
        token_file=ROOT / "tokens.json",
    )

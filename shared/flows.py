"""User journeys through the demo app, shared by the sweep and the repro agent."""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from playwright.sync_api import Page

ROOT = Path(__file__).resolve().parents[1]
REGIONS_FILE = ROOT / "01-region-sweep" / "regions.json"


@dataclass(frozen=True)
class Geo:
    region: str
    city: str
    country: str
    locale: str
    timezone: str


def load_geos(only: list[str] | None = None) -> list[Geo]:
    geos = [Geo(**row) for row in json.loads(REGIONS_FILE.read_text())]
    if only:
        wanted = {r.strip().lower() for r in only}
        geos = [g for g in geos if g.region in wanted]
    return geos


@dataclass
class CheckoutResult:
    region: str
    city: str
    country: str
    served_by: str | None
    load_ms: int
    total: str | None
    ok: bool
    error: str | None
    screenshot: str | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def run_checkout(page: Page, base_url: str, geo: Geo, sku: str = "mug") -> CheckoutResult:
    """Load the shop, buy one item, and report what happened."""
    start = time.monotonic()
    response = page.goto(base_url.rstrip("/") + "/", wait_until="domcontentloaded")
    load_ms = int((time.monotonic() - start) * 1000)
    served_by = response.headers.get("x-served-by-region") if response else None

    page.click(f"[data-testid=buy-{sku}]")
    total = page.inner_text("[data-testid=total]")
    page.click("[data-testid=place-order]")
    page.wait_for_load_state("domcontentloaded")

    if page.locator("[data-testid=order-confirmed]").count():
        return CheckoutResult(
            geo.region, geo.city, geo.country, served_by, load_ms, total, True, None
        )
    error_box = page.locator("[data-testid=checkout-error]")
    error = error_box.inner_text().strip() if error_box.count() else "no confirmation shown"
    return CheckoutResult(
        geo.region, geo.city, geo.country, served_by, load_ms, total, False, " ".join(error.split())
    )

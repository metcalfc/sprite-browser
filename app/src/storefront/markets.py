"""Regional markets: which currency and number format each Fly region shows.

Every price in the catalog is stored in US cents. Each region converts and
formats it for its local market, the way a real storefront might.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal


@dataclass(frozen=True)
class Market:
    region: str
    city: str
    currency: str
    symbol: str
    rate: Decimal  # units of local currency per 1 USD
    decimals: int
    thousands_sep: str
    decimal_sep: str
    symbol_suffix: bool = False


MARKETS: dict[str, Market] = {
    "iad": Market("iad", "Ashburn", "USD", "$", Decimal("1"), 2, ",", "."),
    "lhr": Market("lhr", "London", "GBP", "£", Decimal("0.79"), 2, ",", "."),
    "fra": Market("fra", "Frankfurt", "EUR", "€", Decimal("0.92"), 2, ".", ",", True),
    "gru": Market("gru", "São Paulo", "BRL", "R$ ", Decimal("5.40"), 2, ".", ","),
    "nrt": Market("nrt", "Tokyo", "JPY", "¥", Decimal("150"), 0, ",", "."),
    "syd": Market("syd", "Sydney", "AUD", "A$", Decimal("1.52"), 2, ",", "."),
}

DEFAULT_REGION = "iad"


def market_for(region: str | None) -> Market:
    return MARKETS.get((region or "").lower(), MARKETS[DEFAULT_REGION])


def local_amount(usd_cents: int, market: Market) -> Decimal:
    """Convert US cents to the market's currency, rounded to its decimals."""
    quantum = Decimal(1).scaleb(-market.decimals)
    return (Decimal(usd_cents) / 100 * market.rate).quantize(quantum, rounding=ROUND_HALF_UP)


def format_amount(amount: Decimal, market: Market) -> str:
    """Render an amount the way people in that market expect to read it."""
    whole, _, frac = f"{amount:.{market.decimals}f}".partition(".")
    groups = []
    while len(whole) > 3:
        groups.insert(0, whole[-3:])
        whole = whole[:-3]
    groups.insert(0, whole)
    number = market.thousands_sep.join(groups)
    if frac:
        number = f"{number}{market.decimal_sep}{frac}"
    if market.symbol_suffix:
        return f"{number} {market.symbol}"
    return f"{market.symbol}{number}"


def parse_amount(display: str, market: Market) -> Decimal:
    """Turn a displayed price back into a number.

    PLANTED BUG (see app/README.md): comma decimals were special-cased for EUR
    after a German bug report, but nobody remembered that BRL formats numbers
    the same way. "R$ 102,55" comes back as 10255.
    """
    cleaned = display.replace(market.symbol.strip(), "").replace(" ", "").strip()
    if market.currency == "EUR":
        cleaned = cleaned.replace(".", "").replace(",", ".")
    else:
        cleaned = cleaned.replace(",", "")
    return Decimal(cleaned)

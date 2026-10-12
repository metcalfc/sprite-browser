from __future__ import annotations

import unittest
from decimal import Decimal

import requests

from storefront.markets import MARKETS, format_amount, local_amount, market_for, parse_amount
from tests.server import LiveServer


class Markets(unittest.TestCase):
    def test_formats(self) -> None:
        cases = {
            "iad": "$18.99",
            "lhr": "£15.00",
            "fra": "17,47 €",
            "gru": "R$ 102,55",
            "nrt": "¥2,849",
            "syd": "A$28.86",
        }
        for region, expected in cases.items():
            with self.subTest(region=region):
                m = MARKETS[region]
                self.assertEqual(format_amount(local_amount(1899, m), m), expected)

    def test_thousands(self) -> None:
        fra = MARKETS["fra"]
        self.assertEqual(format_amount(Decimal("1234.50"), fra), "1.234,50 €")

    def test_round_trip_outside_brazil(self) -> None:
        for region in ("iad", "lhr", "fra", "nrt", "syd"):
            with self.subTest(region=region):
                m = MARKETS[region]
                for cents in (899, 1899, 5499, 250000):
                    amount = local_amount(cents, m)
                    self.assertEqual(parse_amount(format_amount(amount, m), m), amount)

    def test_unknown_region_falls_back(self) -> None:
        self.assertEqual(market_for("zzz").region, "iad")
        self.assertEqual(market_for(None).region, "iad")


class App(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = LiveServer().__enter__()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.__exit__(None, None, None)

    def test_region_header_and_label(self) -> None:
        r = requests.get(self.server.url, headers={"fly-prefer-region": "nrt"}, timeout=5)
        self.assertEqual(r.headers["x-served-by-region"], "nrt")
        self.assertIn("Tokyo", r.text)
        self.assertIn("¥", r.text)

    def test_inbox_needs_token(self) -> None:
        r = requests.get(f"{self.server.url}/_inbox", params={"email": "a@b.c"}, timeout=5)
        self.assertEqual(r.status_code, 404)
        r = requests.get(
            f"{self.server.url}/_inbox",
            params={"email": "a@b.c"},
            headers={"x-inbox-token": "wrong"},
            timeout=5,
        )
        self.assertEqual(r.status_code, 404)

    def test_wrong_code_rejected(self) -> None:
        s = requests.Session()
        s.post(
            f"{self.server.url}/signup",
            data={"email": "c@example.com", "password": "longenough"},
            timeout=5,
        )
        r = s.post(
            f"{self.server.url}/verify",
            data={"email": "c@example.com", "code": "not-a-code"},
            timeout=5,
        )
        self.assertEqual(r.status_code, 400)

    def test_onboarding_requires_session(self) -> None:
        r = requests.get(f"{self.server.url}/onboarding", allow_redirects=False, timeout=5)
        self.assertEqual(r.status_code, 303)
        self.assertEqual(r.headers["location"], "/signup")


if __name__ == "__main__":
    unittest.main()

"""The demos depend on two bugs. These tests prove they're still there.

If a test in this file fails, someone fixed a planted bug. That's a good
instinct in a real app, but here it breaks the blog posts. See app/README.md.
"""

from __future__ import annotations

import re
import unittest

import requests

from storefront.markets import MARKETS, local_amount, parse_amount
from tests.server import LiveServer


def checkout(base: str, region: str, sku: str = "mug") -> requests.Response:
    headers = {"fly-prefer-region": region}
    page = requests.get(f"{base}/checkout", params={"sku": sku}, headers=headers, timeout=5)
    match = re.search(r'name="total" value="([^"]+)"', page.text)
    assert match, "checkout form has no total field"
    total = match.group(1).replace("&nbsp;", " ")
    return requests.post(
        f"{base}/checkout", data={"sku": sku, "total": total}, headers=headers, timeout=5
    )


class PlantedBugA(unittest.TestCase):
    """Checkout fails for visitors served from gru, and only gru."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.server = LiveServer().__enter__()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.__exit__(None, None, None)

    def test_brl_parse_is_wrong(self) -> None:
        brl = MARKETS["gru"]
        self.assertNotEqual(parse_amount("R$ 102,55", brl), local_amount(1899, brl))

    def test_checkout_fails_in_gru(self) -> None:
        response = checkout(self.server.url, "gru")
        self.assertEqual(response.status_code, 409)
        self.assertIn("checkout-error", response.text)

    def test_checkout_works_everywhere_else(self) -> None:
        for region in ("iad", "lhr", "fra", "nrt", "syd"):
            with self.subTest(region=region):
                response = checkout(self.server.url, region)
                self.assertEqual(response.status_code, 200, response.text[:200])
                self.assertIn("order-confirmed", response.text)


class PlantedBugB(unittest.TestCase):
    """Onboarding loops silently when the optional display name is blank."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.server = LiveServer(inbox_token="t0ken").__enter__()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.__exit__(None, None, None)

    def signed_up(self, email: str) -> requests.Session:
        s = requests.Session()
        base = self.server.url
        s.post(f"{base}/signup", data={"email": email, "password": "correct-horse"}, timeout=5)
        codes = s.get(
            f"{base}/_inbox", params={"email": email}, headers={"x-inbox-token": "t0ken"}, timeout=5
        ).json()["codes"]
        verified = s.post(f"{base}/verify", data={"email": email, "code": codes[-1]}, timeout=5)
        self.assertTrue(verified.url.endswith("/onboarding"))
        return s

    def test_blank_name_loops_without_error(self) -> None:
        s = self.signed_up("blank@example.com")
        response = s.post(
            f"{self.server.url}/onboarding", data={"display_name": "", "team_size": "3"}, timeout=5
        )
        self.assertTrue(response.url.endswith("/onboarding"))
        self.assertNotIn('class="error"', response.text)
        self.assertIn("(optional)", response.text)

    def test_with_name_reaches_welcome(self) -> None:
        s = self.signed_up("named@example.com")
        response = s.post(
            f"{self.server.url}/onboarding",
            data={"display_name": "Ada", "team_size": "3"},
            timeout=5,
        )
        self.assertTrue(response.url.endswith("/welcome"))
        self.assertIn("all set, Ada", response.text)


if __name__ == "__main__":
    unittest.main()

"""Unit tests for the demo scripts' logic (no browser, no network)."""

from __future__ import annotations

import importlib.util
import sys
import unittest
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType
from typing import Any
from unittest import mock

from shared import anchor_session
from shared.flows import CheckoutResult, load_geos

ROOT = Path(__file__).resolve().parents[1]


def load_script(relative: str) -> ModuleType:
    path = ROOT / relative
    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[path.stem] = module
    spec.loader.exec_module(module)
    return module


repro = load_script("02-repro/repro_agent.py")
first_user = load_script("03-first-user/first_user.py")
grid = load_script("01-region-sweep/grid.py")


class Regions(unittest.TestCase):
    def test_six_regions_with_matching_markets(self) -> None:
        from storefront.markets import MARKETS

        geos = load_geos()
        self.assertEqual({g.region for g in geos}, set(MARKETS))

    def test_subset(self) -> None:
        self.assertEqual([g.region for g in load_geos(["GRU", "fra"])], ["fra", "gru"])


class Repro(unittest.TestCase):
    def test_finds_brazil_in_sample_issue(self) -> None:
        text = (ROOT / "02-repro" / "sample-issue.md").read_text()
        self.assertEqual(repro.geos_in_text(text), ["gru"])

    def test_word_boundaries(self) -> None:
        self.assertEqual(repro.geos_in_text("our framework is broken"), [])
        self.assertEqual(repro.geos_in_text("Broken in Germany and Japan"), ["fra", "nrt"])

    def test_generated_test_compiles(self) -> None:
        geo = load_geos(["gru"])[0]
        source = repro.test_source(geo)
        compile(source, "test_repro_checkout_gru.py", "exec")
        self.assertIn('"fly-prefer-region": "gru"', source)

    def test_report_lists_failures(self) -> None:
        bad = CheckoutResult(
            "gru", "São Paulo", "br", "gru", 120, "R$ 102,55", False, "cart changed"
        )
        good = CheckoutResult("fra", "Frankfurt", "de", "fra", 80, "17,47 €", True, None)
        text = repro.report(
            "Checkout broken in Brazil", None, [(bad, "https://live/x"), (good, None)], []
        )
        self.assertIn("❌ cart changed", text)
        self.assertIn("✅ order confirmed", text)
        self.assertIn("https://live/x", text)


class Grid(unittest.TestCase):
    def test_marks_broken_region(self) -> None:
        rows = [
            CheckoutResult("gru", "São Paulo", "br", "gru", 120, "R$ 102,55", False, "x").to_dict(),
            CheckoutResult("fra", "Frankfurt", "de", "iad", 80, "17,47 €", True, None).to_dict(),
        ]
        html = grid.render_grid(rows, "https://app.fly.dev", "test")
        self.assertIn("Broken in: São Paulo (gru)", html)
        self.assertIn('class="cell bad"', html)
        self.assertIn("expected fra, got iad", html)


class FirstUser(unittest.TestCase):
    def test_issue_body(self) -> None:
        finding = first_user.Finding("s", "t", ["a", "b"], "exp", "act", "work")
        body = finding.issue_body("https://live/y")
        self.assertIn("1. a\n2. b", body)
        self.assertIn("https://live/y", body)


class AnchorSession(unittest.TestCase):
    def test_config(self) -> None:
        body = anchor_session.session_config("br", max_minutes=5, idle_minutes=1, recording=False)
        self.assertEqual(
            body["session"]["proxy"],
            {"type": "anchor_proxy", "active": True, "country_code": "br"},
        )
        self.assertEqual(body["session"]["timeout"], {"max_duration": 5, "idle_timeout": 1})
        self.assertNotIn(
            "proxy",
            anchor_session.session_config(None, max_minutes=1, idle_minutes=1, recording=True)[
                "session"
            ],
        )

    def test_missing_key(self) -> None:
        with mock.patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(anchor_session.MissingKey):
                anchor_session.anchor_key()

    def test_sdk_env_name_accepted(self) -> None:
        with mock.patch.dict("os.environ", {"ANCHORBROWSER_API_KEY": "k"}, clear=True):
            self.assertEqual(anchor_session.anchor_key(), "k")

    def test_session_has_no_cdp_field(self) -> None:
        fields = anchor_session.Session.__dataclass_fields__
        self.assertFalse(any("cdp" in name for name in fields))

    def test_retries_when_rate_limited(self) -> None:
        limited = mock.Mock(status_code=429, headers={"retry-after": "3"})
        created = mock.Mock(status_code=200, headers={})
        created.json.return_value = {
            "data": {"id": "s1", "cdp_url": "wss://x", "live_view_url": "v"}
        }
        with (
            mock.patch.object(anchor_session.requests, "post", side_effect=[limited, created]),
            mock.patch.object(anchor_session.time, "sleep") as sleep,
            mock.patch("sys.stderr"),
        ):
            session_id, _, live_view = anchor_session.start_anchor_session(
                "k", "au", max_minutes=1, idle_minutes=1, recording=False
            )
        self.assertEqual((session_id, live_view), ("s1", "v"))
        sleep.assert_called_once_with(3.0)

    def test_retry_wait_is_bounded(self) -> None:
        self.assertEqual(anchor_session.retry_after_seconds("9999", 0), 60.0)
        self.assertEqual(anchor_session.retry_after_seconds(None, 1), 10.0)
        self.assertEqual(anchor_session.retry_after_seconds("soon", 0), 5.0)

    def test_session_deleted_when_connect_fails(self) -> None:
        ended: list[str] = []

        class FakeChromium:
            def connect_over_cdp(self, url: str) -> Any:
                raise ConnectionError("boom")

        class FakePW:
            chromium = FakeChromium()

        @contextmanager
        def fake_playwright() -> Any:
            yield FakePW()

        with (
            mock.patch.dict("os.environ", {"ANCHOR_API_KEY": "k"}),
            mock.patch.object(anchor_session, "sync_playwright", fake_playwright),
            mock.patch.object(
                anchor_session,
                "start_anchor_session",
                return_value=("sess-1", "wss://secret", "https://live/z"),
            ),
            mock.patch.object(
                anchor_session, "end_anchor_session", lambda key, sid: ended.append(sid)
            ),
            mock.patch("builtins.print") as printed,
        ):
            with self.assertRaises(ConnectionError):
                with anchor_session.browser_session("br"):
                    pass
        self.assertEqual(ended, ["sess-1"])
        output = " ".join(str(c) for c in printed.call_args_list)
        self.assertNotIn("wss://secret", output)
        self.assertIn("https://live/z", output)


if __name__ == "__main__":
    unittest.main()

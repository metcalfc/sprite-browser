"""One browser session per agent run, opened and closed the right way.

Every demo in this repo gets its browser from `browser_session()`. It either
starts an Anchor session in a given country and drives it over CDP, or (with
`local=True`) launches a local Chromium so you can develop without a key.

The rules it enforces, from Anchor's session hygiene notes:
- one session per run, always deleted on the way out (even on errors)
- max_duration and idle_timeout set, so an idle Sprite never holds a browser
- the CDP URL carries your key, so it is never printed, logged, or repr'd;
  show people the live view URL instead
"""

from __future__ import annotations

import os
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

import requests
from playwright.sync_api import Page, sync_playwright

ANCHOR_API = "https://api.anchorbrowser.io/v1"
RATE_LIMIT_RETRIES = 4
RATE_LIMIT_MAX_WAIT = 60.0


class MissingKey(RuntimeError):
    pass


def anchor_key() -> str:
    """The Anchor API key, from ANCHOR_API_KEY or the SDK's ANCHORBROWSER_API_KEY."""
    key = os.environ.get("ANCHOR_API_KEY") or os.environ.get("ANCHORBROWSER_API_KEY")
    if not key:
        raise MissingKey(
            "Set ANCHOR_API_KEY (on a Machine: fly secrets set ANCHOR_API_KEY=...), "
            "or pass --local to use a local Chromium."
        )
    return key


@dataclass
class Session:
    """What a demo gets back. Deliberately has no field holding the CDP URL."""

    page: Page
    country: str | None
    live_view_url: str | None = None
    session_id: str | None = None
    local: bool = False
    notes: dict[str, Any] = field(default_factory=dict)


def session_config(
    country: str | None, *, max_minutes: int, idle_minutes: int, recording: bool
) -> dict[str, Any]:
    """The body for POST /v1/sessions."""
    config: dict[str, Any] = {
        "timeout": {"max_duration": max_minutes, "idle_timeout": idle_minutes},
        "recording": {"active": recording},
    }
    if country:
        config["proxy"] = {"type": "anchor_proxy", "active": True, "country_code": country}
    return {"session": config}


def retry_after_seconds(header: str | None, attempt: int) -> float:
    """How long to wait after a 429: the Retry-After header, else a doubling backoff."""
    try:
        wait = float(header) if header else 5.0 * 2**attempt
    except ValueError:
        wait = 5.0 * 2**attempt
    return min(max(wait, 1.0), RATE_LIMIT_MAX_WAIT)


def start_anchor_session(
    key: str, country: str | None, *, max_minutes: int, idle_minutes: int, recording: bool
) -> tuple[str, str, str | None]:
    """Returns (session_id, cdp_url, live_view_url). Callers must not log cdp_url."""
    body = session_config(
        country, max_minutes=max_minutes, idle_minutes=idle_minutes, recording=recording
    )
    for attempt in range(RATE_LIMIT_RETRIES + 1):
        response = requests.post(
            f"{ANCHOR_API}/sessions",
            headers={"anchor-api-key": key, "content-type": "application/json"},
            json=body,
            timeout=60,
        )
        # Anchor rate-limits session creation; a sweep opens several in a row.
        if response.status_code != 429 or attempt == RATE_LIMIT_RETRIES:
            break
        wait = retry_after_seconds(response.headers.get("retry-after"), attempt)
        print(f"Anchor rate limit hit, retrying in {wait:.0f}s", file=sys.stderr, flush=True)
        time.sleep(wait)
    response.raise_for_status()
    data = response.json()["data"]
    return data["id"], data["cdp_url"], data.get("live_view_url")


def end_anchor_session(key: str, session_id: str) -> None:
    try:
        requests.delete(
            f"{ANCHOR_API}/sessions/{session_id}",
            headers={"anchor-api-key": key},
            timeout=30,
        ).raise_for_status()
    except requests.RequestException as exc:  # never mask the original error
        print(f"warning: could not end Anchor session {session_id}: {exc}", file=sys.stderr)


@contextmanager
def browser_session(
    country: str | None = None,
    *,
    local: bool = False,
    locale: str | None = None,
    timezone: str | None = None,
    extra_headers: dict[str, str] | None = None,
    max_minutes: int = 10,
    idle_minutes: int = 2,
    recording: bool = True,
    label: str = "browser",
) -> Iterator[Session]:
    """Open one browser for one run, and always clean it up.

    `country` is a lowercase ISO code ("br", "de"). With Anchor it picks the
    proxy exit, so the app sees a visitor from that country and Fly routes the
    request to the nearest region. Locally it only sets locale and timezone.
    """
    headers = extra_headers or {}
    with sync_playwright() as pw:
        if local:
            browser = pw.chromium.launch()
            context = browser.new_context(
                locale=locale, timezone_id=timezone, extra_http_headers=headers
            )
            try:
                yield Session(page=context.new_page(), country=country, local=True)
            finally:
                browser.close()
            return

        key = anchor_key()
        session_id, cdp_url, live_view_url = start_anchor_session(
            key,
            country,
            max_minutes=max_minutes,
            idle_minutes=idle_minutes,
            recording=recording,
        )
        try:
            if live_view_url:
                print(f"[{label}] watch live: {live_view_url}", flush=True)
            browser = pw.chromium.connect_over_cdp(cdp_url)
            del cdp_url  # nothing past this point can leak it
            context = browser.contexts[0] if browser.contexts else browser.new_context()
            if headers:
                context.set_extra_http_headers(headers)
            page = context.pages[0] if context.pages else context.new_page()
            try:
                yield Session(
                    page=page,
                    country=country,
                    live_view_url=live_view_url,
                    session_id=session_id,
                )
            finally:
                browser.close()
        finally:
            end_anchor_session(key, session_id)

"""Reproduce a geo bug report from where it happened, and leave a failing test.

    python 02-repro/repro_agent.py --issue 12 --url https://your-app.fly.dev
    python 02-repro/repro_agent.py --issue-file 02-repro/sample-issue.md --url ... --local

This is the tool an agent in a Sprite calls when an issue lands. It:
1. reads the issue (from GitHub with `gh`, or from a file)
2. picks the geos it mentions (falls back to sweeping every region)
3. runs checkout from each one in a browser exiting in that country
4. for each failure, writes a failing Playwright test to e2e/ and a report to
   out/repro/report.md, with the live view link

Then 02-repro/open_pr.sh turns that into a pull request.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from shared.anchor_session import MissingKey, browser_session  # noqa: E402
from shared.flows import ROOT, CheckoutResult, Geo, load_geos, run_checkout  # noqa: E402

# Words an issue might use for each region. Lowercase, matched on word boundaries.
GEO_WORDS: dict[str, list[str]] = {
    "gru": ["brazil", "brasil", "brazilian", "são paulo", "sao paulo", "brl", "gru"],
    "fra": ["germany", "german", "deutschland", "frankfurt", "fra"],
    "lhr": ["uk", "united kingdom", "britain", "british", "london", "lhr"],
    "nrt": ["japan", "japanese", "tokyo", "jpy", "nrt"],
    "syd": ["australia", "australian", "sydney", "aud", "syd"],
    "iad": ["united states", "usa", "virginia", "iad"],
}


def geos_in_text(text: str) -> list[str]:
    lowered = text.lower()
    found = []
    for region, words in GEO_WORDS.items():
        if any(re.search(rf"(?<!\w){re.escape(w)}(?!\w)", lowered) for w in words):
            found.append(region)
    return found


def read_issue(number: str | None, path: str | None) -> tuple[str, str, str | None]:
    """Returns (title, body, url)."""
    if path:
        text = Path(path).read_text()
        title, _, body = text.partition("\n")
        return title.lstrip("# ").strip(), body.strip(), None
    raw = subprocess.run(
        ["gh", "issue", "view", str(number), "--json", "title,body,url"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    data = json.loads(raw)
    return data["title"], data["body"], data["url"]


def test_source(geo: Geo, sku: str = "mug") -> str:
    """A standalone Playwright test that fails until checkout works from this region."""
    return f'''"""Repro: checkout fails for visitors served from {geo.city} ({geo.region}).

Written by 02-repro/repro_agent.py. Fails until the bug is fixed.
Run with: APP_URL=https://your-app.fly.dev make e2e
"""

import os
import unittest

from playwright.sync_api import sync_playwright

APP_URL = os.environ.get("APP_URL", "http://127.0.0.1:8080")


class CheckoutFrom{geo.region.capitalize()}(unittest.TestCase):
    def test_checkout_confirms_order(self) -> None:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            context = browser.new_context(
                locale="{geo.locale}",
                timezone_id="{geo.timezone}",
                extra_http_headers={{"fly-prefer-region": "{geo.region}"}},
            )
            page = context.new_page()
            page.goto(APP_URL + "/checkout?sku={sku}")
            page.click("[data-testid=place-order]")
            confirmed = page.locator("[data-testid=order-confirmed]").count()
            browser.close()
        self.assertEqual(confirmed, 1, "checkout from {geo.region} did not confirm the order")


if __name__ == "__main__":
    unittest.main()
'''


def report(
    title: str, url: str | None, results: list[tuple[CheckoutResult, str | None]], tests: list[Path]
) -> str:
    lines = [f"## Repro: {title}", ""]
    if url:
        lines += [f"Issue: {url}", ""]
    lines += [
        "| Region | City | Served by | Total shown | Result |",
        "| --- | --- | --- | --- | --- |",
    ]
    for result, _ in results:
        verdict = "✅ order confirmed" if result.ok else f"❌ {result.error}"
        cells = [f"`{result.region}`", result.city, f"`{result.served_by}`", result.total, verdict]
        lines.append("| " + " | ".join(str(c) for c in cells) + " |")
    watched = [(r, live) for r, live in results if live and not r.ok]
    if watched:
        lines += ["", "Live view of the failing session(s):"]
        lines += [f"- {r.city}: {live}" for r, live in watched]
    if tests:
        lines += ["", "Failing tests added:"]
        lines += [
            f"- `{t.resolve().relative_to(ROOT) if t.resolve().is_relative_to(ROOT) else t}`"
            for t in tests
        ]
    lines += ["", "_Reproduced by `02-repro/repro_agent.py` from a Sprite._"]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--issue", help="GitHub issue number (uses gh)")
    source.add_argument("--issue-file", help="markdown file with the issue (first line is title)")
    parser.add_argument("--url", default=os.environ.get("APP_URL"), help="app URL (or APP_URL)")
    parser.add_argument("--local", action="store_true", help="use a local Chromium, no key")
    parser.add_argument("--out", default=str(ROOT / "out" / "repro"))
    parser.add_argument("--tests-dir", default=None, help="where to write tests (default: e2e/)")
    args = parser.parse_args(argv)
    if not args.url:
        parser.error("pass --url or set APP_URL")

    title, body, issue_url = read_issue(args.issue, args.issue_file)
    regions = geos_in_text(f"{title}\n{body}")
    geos = load_geos(regions or None)
    print(f"issue: {title}")
    print(f"geos: {', '.join(g.region for g in geos)}" + ("" if regions else " (none named, all)"))

    results: list[tuple[CheckoutResult, str | None]] = []
    for geo in geos:
        headers = {"fly-prefer-region": geo.region} if args.local else {}
        try:
            with browser_session(
                geo.country,
                local=args.local,
                locale=geo.locale,
                timezone=geo.timezone,
                extra_headers=headers,
                max_minutes=5,
                idle_minutes=1,
                label=geo.region,
            ) as session:
                result = run_checkout(session.page, args.url, geo)
                results.append((result, session.live_view_url))
        except MissingKey as exc:
            print(exc, file=sys.stderr)
            return 2
        print(f"{'ok  ' if result.ok else 'FAIL'} {geo.region}: {result.error or 'confirmed'}")

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    tests_dir = Path(args.tests_dir) if args.tests_dir else ROOT / "e2e"

    tests: list[Path] = []
    for result, _ in results:
        if result.ok:
            continue
        geo = next(g for g in geos if g.region == result.region)
        path = tests_dir / f"test_repro_checkout_{geo.region}.py"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(test_source(geo))
        tests.append(path)

    (out_dir / "report.md").write_text(report(title, issue_url, results, tests))
    (out_dir / "issue.json").write_text(json.dumps({"number": args.issue, "title": title}))
    print(f"report: {out_dir / 'report.md'}")
    if tests:
        print("next: 02-repro/open_pr.sh")
        return 0
    print("could not reproduce from the geos in the issue")
    return 3


if __name__ == "__main__":
    sys.exit(main())

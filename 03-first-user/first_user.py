"""Use the app like a first-time user would, and file what goes wrong.

    python 03-first-user/first_user.py --url https://your-app.fly.dev
    python 03-first-user/first_user.py --url http://127.0.0.1:8080 --local

The agent signs up, gets its MFA code from the demo inbox, goes through
onboarding the way a hurried person does (skipping fields marked optional),
and tries to reach the welcome page. Anything that stops it becomes a finding
in out/first-user/, written as a ready-to-file issue. Pass --file-issues to
open them on GitHub with `gh`.

Share the live view link it prints and your team can watch it happen.
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import requests
from playwright.sync_api import Page

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from shared.anchor_session import MissingKey, browser_session  # noqa: E402
from shared.flows import ROOT  # noqa: E402


@dataclass
class Finding:
    slug: str
    title: str
    steps: list[str]
    expected: str
    actual: str
    workaround: str | None = None

    def issue_body(self, live_view_url: str | None) -> str:
        steps = "\n".join(f"{i}. {s}" for i, s in enumerate(self.steps, 1))
        body = (
            f"**Steps**\n\n{steps}\n\n**Expected**\n\n{self.expected}\n\n"
            f"**Actual**\n\n{self.actual}\n"
        )
        if self.workaround:
            body += f"\n**Workaround**\n\n{self.workaround}\n"
        if live_view_url:
            body += f"\n**Watch the session**\n\n{live_view_url}\n"
        return body + "\n_Found by the first-user agent (03-first-user/first_user.py)._\n"


def fetch_code(base: str, email: str, token: str, attempts: int = 10) -> str:
    for _ in range(attempts):
        response = requests.get(
            f"{base}/_inbox", params={"email": email}, headers={"x-inbox-token": token}, timeout=15
        )
        if response.status_code == 404:
            raise SystemExit(
                "The demo inbox is off. Set DEMO_INBOX_TOKEN on the app and pass the same value."
            )
        codes = response.json().get("codes", [])
        if codes:
            return str(codes[-1])
        time.sleep(1)
    raise SystemExit(f"no code arrived for {email}")


def path_of(page: Page) -> str:
    return "/" + page.url.split("://", 1)[-1].split("/", 1)[-1].split("?", 1)[0]


def walk(page: Page, base: str, token: str, step: list[str]) -> list[Finding]:
    """The journey. Appends human-readable steps as it goes."""
    findings: list[Finding] = []
    email = f"first-user+{secrets.token_hex(4)}@example.com"

    page.goto(f"{base}/signup")
    page.fill("#email", email)
    page.fill("#password", secrets.token_urlsafe(12))
    page.click("[data-testid=signup-submit]")
    step.append("Sign up with a new email and password")

    page.wait_for_url("**/verify**")
    page.fill("#code", fetch_code(base, email, token))
    page.click("[data-testid=verify-submit]")
    step.append("Enter the 6-digit code from the signup email")

    page.wait_for_url("**/onboarding")
    page.fill("#team_size", "3")
    page.click("[data-testid=onboarding-submit]")
    step.append(
        "On onboarding, leave Display name (marked optional) blank, set Team size, Continue"
    )
    page.wait_for_load_state("domcontentloaded")

    if path_of(page) != "/welcome":
        has_error = page.locator(".error").count() > 0
        actual = (
            "The page shows an error."
            if has_error
            else "Back on the onboarding page with the form cleared and no error message. "
            "Clicking Continue again does the same thing."
        )
        workaround = None
        page.fill("#display_name", "First User")
        page.fill("#team_size", "3")
        page.click("[data-testid=onboarding-submit]")
        page.wait_for_load_state("domcontentloaded")
        if path_of(page) == "/welcome":
            workaround = "Filling in Display name gets you through, so the field isn't optional."
        findings.append(
            Finding(
                slug="blank-display-name",
                title="Onboarding silently loops when the optional display name is blank",
                steps=list(step),
                expected="Land on the welcome page, or see an error explaining what's missing.",
                actual=actual,
                workaround=workaround,
            )
        )

    if path_of(page) == "/welcome":
        step.append("Reach the welcome page")
    return findings


def file_issue(finding: Finding, body: str) -> str:
    return subprocess.run(
        ["gh", "issue", "create", "--title", finding.title, "--body", body],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--url", default=os.environ.get("APP_URL"), help="app URL (or APP_URL)")
    parser.add_argument("--local", action="store_true", help="use a local Chromium, no key")
    parser.add_argument("--inbox-token", default=os.environ.get("DEMO_INBOX_TOKEN", "dev"))
    parser.add_argument("--file-issues", action="store_true", help="open findings with gh")
    parser.add_argument("--out", default=str(ROOT / "out" / "first-user"))
    parser.add_argument(
        "--expect-finding", help="exit 1 unless this finding slug (and only it) is found"
    )
    args = parser.parse_args(argv)
    if not args.url:
        parser.error("pass --url or set APP_URL")
    base = args.url.rstrip("/")

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    steps: list[str] = []
    try:
        with browser_session(
            "us", local=args.local, max_minutes=10, idle_minutes=2, label="first-user"
        ) as session:
            findings = walk(session.page, base, args.inbox_token, steps)
            session.page.screenshot(path=str(out_dir / "final.png"))
            live = session.live_view_url
    except MissingKey as exc:
        print(exc, file=sys.stderr)
        return 2

    for step in steps:
        print(f"  ✓ {step}")
    for finding in findings:
        body = finding.issue_body(live)
        (out_dir / f"{finding.slug}.md").write_text(f"# {finding.title}\n\n{body}")
        print(f"finding: {finding.title}")
        if args.file_issues:
            print(f"  filed: {file_issue(finding, body)}")
    (out_dir / "findings.json").write_text(json.dumps([asdict(f) for f in findings], indent=2))
    if not findings:
        print("no findings: a stranger got all the way through")

    if args.expect_finding is not None:
        slugs = {f.slug for f in findings}
        if slugs != {args.expect_finding}:
            print(f"expected finding {args.expect_finding!r}, got {sorted(slugs)}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

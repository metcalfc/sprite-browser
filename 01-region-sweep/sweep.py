"""Visit the app from every region it runs in, and check out once from each.

    python 01-region-sweep/sweep.py --url https://your-app.fly.dev
    python 01-region-sweep/sweep.py --url http://127.0.0.1:8080 --local

With Anchor, each region gets a browser whose traffic exits in the matching
country, so Fly routes it to the nearest Machine like a real visitor. With
--local, a local Chromium asks for the region with the fly-prefer-region
header instead.

Writes out/sweep/results.json, a screenshot per region, and out/sweep/grid.html.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from grid import render_grid  # noqa: E402
from shared.anchor_session import MissingKey, browser_session  # noqa: E402
from shared.flows import ROOT, CheckoutResult, Geo, load_geos, run_checkout  # noqa: E402


def sweep_one(geo: Geo, url: str, local: bool, out_dir: Path) -> CheckoutResult:
    headers = {"fly-prefer-region": geo.region} if local else {}
    with browser_session(
        geo.country,
        local=local,
        locale=geo.locale,
        timezone=geo.timezone,
        extra_headers=headers,
        max_minutes=5,
        idle_minutes=1,
        label=geo.region,
    ) as session:
        page = session.page
        page.set_viewport_size({"width": 520, "height": 420})
        result = run_checkout(page, url, geo)
        shot = out_dir / f"{geo.region}.png"
        page.screenshot(path=str(shot))
        result.screenshot = shot.name
        return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--url", default=os.environ.get("APP_URL"), help="app URL (or APP_URL)")
    parser.add_argument("--local", action="store_true", help="use a local Chromium, no key")
    parser.add_argument("--regions", help="comma-separated subset, e.g. gru,fra")
    parser.add_argument("--out", default=str(ROOT / "out" / "sweep"))
    parser.add_argument(
        "--expect-broken",
        help="comma-separated regions that must fail (and only those); exit 1 otherwise",
    )
    args = parser.parse_args(argv)
    if not args.url:
        parser.error("pass --url or set APP_URL")

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    geos = load_geos(args.regions.split(",") if args.regions else None)

    results: list[CheckoutResult] = []
    for geo in geos:
        try:
            result = sweep_one(geo, args.url, args.local, out_dir)
        except MissingKey as exc:
            print(exc, file=sys.stderr)
            return 2
        mark = "ok  " if result.ok else "FAIL"
        print(
            f"{mark} {geo.region} {geo.city:<10} served_by={result.served_by} "
            f"{result.load_ms:>5}ms total={result.total}"
            + (f"  ({result.error})" if result.error else ""),
            flush=True,
        )
        results.append(result)

    rows = [r.to_dict() for r in results]
    (out_dir / "results.json").write_text(json.dumps(rows, indent=2, ensure_ascii=False))
    mode = "local Chromium" if args.local else "Anchor browsers"
    (out_dir / "grid.html").write_text(render_grid(rows, args.url, mode))
    print(f"grid: {out_dir / 'grid.html'}")

    if args.expect_broken is not None:
        expected = {r for r in args.expect_broken.split(",") if r}
        actual = {r.region for r in results if not r.ok}
        if actual != expected:
            print(f"expected broken {sorted(expected)}, got {sorted(actual)}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Render sweep results as one shareable page: a grid of regions, one cell each."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from html import escape
from typing import Any


def cell(row: Mapping[str, Any]) -> str:
    ok = bool(row["ok"])
    served = row.get("served_by") or "?"
    misrouted = served != row["region"]
    status = "Checkout OK" if ok else "Checkout FAILED"
    shot = row.get("screenshot")
    image = f'<img src="{escape(shot)}" alt="{escape(row["city"])} screenshot">' if shot else ""
    route_note = (
        f'<div class="warn">expected {escape(row["region"])}, got {escape(served)}</div>'
        if misrouted
        else ""
    )
    error = f'<div class="err">{escape(row["error"])}</div>' if row.get("error") else ""
    return f"""<article class="cell {"ok" if ok else "bad"}">
  <header><h2>{escape(row["city"])}</h2><code>{escape(row["region"])}</code></header>
  {image}
  <dl>
    <dt>Visitor from</dt><dd>{escape(str(row["country"]).upper())}</dd>
    <dt>Served by</dt><dd><code>{escape(served)}</code></dd>
    <dt>First load</dt><dd>{int(row["load_ms"])} ms</dd>
    <dt>Total shown</dt><dd>{escape(row.get("total") or "?")}</dd>
  </dl>
  {route_note}
  <div class="status">{status}</div>
  {error}
</article>"""


def render_grid(rows: Sequence[Mapping[str, Any]], app_url: str, mode: str) -> str:
    broken = [r for r in rows if not r["ok"]]
    if broken:
        summary = "Broken in: " + ", ".join(f"{r['city']} ({r['region']})" for r in broken)
    else:
        summary = "Checkout works in every region."
    stamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    cells = "\n".join(cell(r) for r in rows)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Region sweep</title>
<style>
  :root {{ --bg:#faf9fd; --card:#fff; --ink:#1b1530; --muted:#6b6585; --line:#e6e2f0;
          --ok:#067647; --okbg:#ecfdf3; --bad:#b42318; --badbg:#fef3f2; }}
  @media (prefers-color-scheme: dark) {{
    :root {{ --bg:#14111f; --card:#1d1930; --ink:#ece9f7; --muted:#a39dbd; --line:#2e2946;
            --ok:#47cd89; --okbg:#0b2a1c; --bad:#f97066; --badbg:#3a1414; }}
  }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; padding:24px 16px; background:var(--bg); color:var(--ink);
         font:15px/1.45 system-ui, sans-serif; }}
  h1 {{ margin:0 0 4px; font-size:22px; }}
  .meta {{ color:var(--muted); margin-bottom:8px; }}
  .summary {{ font-weight:700; margin-bottom:20px; }}
  .grid {{ display:grid; gap:14px; grid-template-columns:repeat(auto-fill, minmax(240px, 1fr)); }}
  .cell {{ background:var(--card); border:2px solid var(--line);
          border-radius:14px; padding:14px; }}
  .cell.bad {{ border-color:var(--bad); background:var(--badbg); }}
  .cell header {{ display:flex; justify-content:space-between; align-items:baseline; }}
  .cell h2 {{ margin:0; font-size:17px; }}
  img {{ width:100%; border-radius:8px; border:1px solid var(--line); margin:10px 0; }}
  dl {{ display:grid; grid-template-columns:auto 1fr; gap:2px 10px; margin:8px 0; }}
  dt {{ color:var(--muted); }} dd {{ margin:0; font-variant-numeric:tabular-nums; }}
  .status {{ font-weight:700; color:var(--ok); }}
  .bad .status {{ color:var(--bad); }}
  .err {{ margin-top:6px; color:var(--bad); }}
  .warn {{ color:var(--muted); font-style:italic; }}
</style></head>
<body>
<h1>Region sweep</h1>
<div class="meta">{escape(app_url)} · {escape(mode)} · {stamp}</div>
<div class="summary">{escape(summary)}</div>
<section class="grid">
{cells}
</section>
</body></html>"""

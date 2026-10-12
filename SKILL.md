---
name: sprite-browser
description: Test this repo's Fly app with a real browser from Anchor, from any country, without installing Chromium in the Sprite. Use when asked to check the app from different regions, reproduce a geo-specific bug, or walk through signup as a new user.
---

# Using a browser from a Sprite

The browser runs in Anchor's cloud. You drive it over CDP from here.

```python
from shared.anchor_session import browser_session

with browser_session("br", label="gru") as session:  # Brazil exit
    session.page.goto(APP_URL)
    print(session.live_view_url)  # safe to share
```

- Country is a lowercase ISO code. Fly routes the request to the nearest region.
- `local=True` uses a local Chromium instead (no key, no geography).
- Never print the CDP URL; `Session` doesn't even hold it.
- One `with` block per run. It sets timeouts and deletes the session.

Ready-made tasks: see AGENTS.md (`sweep.py`, `repro_agent.py`, `first_user.py`).

Anchor's own agent skill covers their full API (auth profiles, agent tasks,
MCP). Get it from Anchor's docs; this file only covers this repo.

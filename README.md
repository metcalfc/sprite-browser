# sprite-browser

**Give your Sprite a browser.** Agents that test a Fly app the way real users
hit it: from six countries at once, through signup and MFA, with a live view
you can share.

A [Sprite](https://fly.io) is your agent's computer. [Anchor](https://anchorbrowser.io)
gives that computer a browser, running in Anchor's cloud and driven over CDP,
so nothing heavy lives in the Sprite. This repo puts the two together around a
small demo storefront deployed to six Fly regions, with two bugs planted in it.

| Demo | What the agent does | Post |
| --- | --- | --- |
| [`01-region-sweep/`](01-region-sweep/) | Opens a browser from each country, hits the nearest Fly region, checks out, builds a screenshot grid. One cell turns red. | Fly: *Reproduce the bug from where it happened* (link TBD) |
| [`02-repro/`](02-repro/) | Reads a "broken in Brazil" issue, reproduces it from Brazil, writes a failing Playwright test, opens a PR. | Same post |
| [`03-first-user/`](03-first-user/) | Signs up, does MFA, skips the optional field like a real person, gets stuck, files the bug. You watch it happen. | Anchor: *Your agent is your first user* (link TBD) |

Everything the agents touch is this repo's own app. No third-party sites.

## Five-minute quickstart (no key, no deploy)

```sh
make setup          # uv sync + local Chromium
make smoke-local    # runs the demo app and all three demos against it
open out/sweep/grid.html
```

Locally there's no geography, so the scripts ask the app to act as each region
with the `fly-prefer-region` header. It's enough to see the shape of things.

## The real thing (Fly + Anchor)

```sh
cd app && fly launch --copy-config --no-deploy && cd ..
fly secrets set DEMO_INBOX_TOKEN=$(openssl rand -hex 16) -a <your-app>
make deploy regions                 # app on Machines in iad lhr fra gru nrt syd

export ANCHOR_API_KEY=...           # inside a Sprite, pass it in at run time
export APP_URL=https://<your-app>.fly.dev
python 01-region-sweep/sweep.py
python 02-repro/repro_agent.py --issue-file 02-repro/sample-issue.md
python 03-first-user/first_user.py --inbox-token <same token>
```

With Anchor, each region gets a browser whose traffic exits in that country,
so Fly's Anycast routing sends it to the nearest Machine, exactly like a
customer there. The scripts print each session's live view link as they go.

## For agents

Read [AGENTS.md](AGENTS.md). It's the runbook an agent in a Sprite follows to
run these demos unattended. [SKILL.md](SKILL.md) is the short version.

## Layout

```
app/                 the demo storefront (and its planted bugs, in app/README.md)
shared/              anchor_session.py (one browser per run, cleaned up), flows.py
01-region-sweep/     sweep.py, regions.json, grid.py
02-repro/            repro_agent.py, open_pr.sh, sample-issue.md
03-first-user/       first_user.py, watch.md
e2e/                 failing tests the repro agent writes land here
tests/               unit tests, including proof the planted bugs still exist
```

## Checks

```sh
make check          # lint (ruff, mypy) + tests + smoke
```

`make smoke` runs the sweep and the first-user agent against `APP_URL` with
real Anchor browsers, and fails unless they find exactly the planted bugs. It
skips itself when `ANCHOR_API_KEY` isn't set, so `make check` works for anyone
who clones the repo.

## Notes

- Session lifecycle uses Anchor's REST API directly (`POST` and `DELETE`
  `/v1/sessions`) so every step is visible in ~40 lines. The `anchorbrowser`
  SDK does the same thing if you'd rather use it.
- `cdp_url` contains your API key. `shared/anchor_session.py` never prints it;
  share `live_view_url` instead.
- Sessions get `max_duration` and `idle_timeout`, and are deleted on exit, so
  an idle Sprite never holds a browser open.

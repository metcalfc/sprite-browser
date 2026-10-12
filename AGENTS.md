# AGENTS.md

You're an agent, probably running in a Sprite. This repo lets you test a Fly
app with a real browser that lives in Anchor's cloud. Here's how to run it
without a human.

## Rules

1. **Only point browsers at this repo's app** (`APP_URL`, or a local server
   you started). Never at third-party sites.
2. **Never print, log, or commit the CDP URL.** It contains the API key.
   Share `live_view_url` instead. Use `shared/anchor_session.py`, which
   already does this.
3. **One session per run, always closed.** `browser_session()` sets timeouts
   and deletes the session on exit, including on errors. Don't open sessions
   any other way.
4. **Don't fix the planted bugs** in `app/`. They're the demo. If you're asked
   to fix one for real, also update `tests/test_planted_bugs.py` and say so.

## Setup

```sh
make setup                       # uv sync + Chromium for local mode
```

You need, from your environment (never hardcode them):
- `ANCHOR_API_KEY`: Anchor key. Without it, add `--local` to any command.
- `APP_URL`: the deployed app, e.g. `https://sprite-browser-demo.fly.dev`.
- `DEMO_INBOX_TOKEN`: matches the app's secret; only for `first_user.py`.
- `gh` authenticated: only for `--issue`, `--file-issues`, and `open_pr.sh`.

## Tasks

### "Check the app from every region"

```sh
python 01-region-sweep/sweep.py
```
Report the summary line and attach `out/sweep/grid.html`. Exit code is 0 even
when regions fail; use `--expect-broken gru` when you need a hard check.

### "Reproduce issue #N"

```sh
python 02-repro/repro_agent.py --issue N
02-repro/open_pr.sh                      # only if it wrote a test to e2e/
```
Exit 3 means it couldn't reproduce from the geos named in the issue. Say so,
include `out/repro/report.md`, and don't open a PR.

### "Try the app as a new user"

```sh
python 03-first-user/first_user.py       # add --file-issues to open them
```
Post the live view link it prints before it finishes so people can watch.
Findings land in `out/first-user/*.md`.

### Before you finish

```sh
make check
```

## Exit codes

| Code | Meaning |
| --- | --- |
| 0 | Ran. Read the output for findings. |
| 1 | An `--expect-*` check didn't match. |
| 2 | No Anchor key. Set one or use `--local`. |
| 3 | (repro) Couldn't reproduce. |

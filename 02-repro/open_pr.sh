#!/usr/bin/env bash
# Turn the repro agent's output into a pull request with the failing test.
#
#   02-repro/open_pr.sh
#
# Needs: gh (authenticated), out/repro/report.md, and new tests in e2e/.
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$root"

report="out/repro/report.md"
if [[ ! -f "$report" ]]; then
  echo "no $report yet; run 02-repro/repro_agent.py first" >&2
  exit 1
fi

if [[ -z "$(git status --porcelain -- e2e/)" ]]; then
  echo "no new tests in e2e/; nothing to propose" >&2
  exit 1
fi

issue="$(python3 -c 'import json;print(json.load(open("out/repro/issue.json")).get("number") or "")')"
title="$(python3 -c 'import json;print(json.load(open("out/repro/issue.json"))["title"])')"
branch="repro/${issue:-geo}-$(date +%Y%m%d-%H%M%S)"

git switch -c "$branch"
git add e2e/
git commit -m "Add failing repro test: ${title}"
git push -u origin "$branch"

body="$(cat "$report")"
if [[ -n "$issue" ]]; then
  body="${body}"$'\n\n'"Refs #${issue}"
fi

gh pr create --title "Repro: ${title}" --body "$body"

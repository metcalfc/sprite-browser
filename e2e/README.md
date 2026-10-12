# e2e

`02-repro/repro_agent.py` writes failing repro tests here, and
`02-repro/open_pr.sh` proposes them in a PR. They're expected to fail until
the bug they describe is fixed.

```sh
APP_URL=https://your-app.fly.dev make e2e
```

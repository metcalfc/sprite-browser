# Hangar Shop (the demo app)

A tiny storefront with a shop, a checkout, and a signup flow with an MFA code.
It exists to be tested by agents, so it has two bugs on purpose.

## Run it locally

```sh
make dev            # http://127.0.0.1:8080
```

Off Fly, the app pretends to be whichever region you ask for with the
`fly-prefer-region` header (the same header Fly's proxy understands):

```sh
curl -s -H 'fly-prefer-region: gru' http://127.0.0.1:8080/ | grep Served
```

## Deploy it to six regions

```sh
cd app
fly launch --copy-config --no-deploy      # pick your own app name
fly secrets set DEMO_INBOX_TOKEN=$(openssl rand -hex 16)
fly deploy
make -C .. regions                        # one Machine in each of iad lhr fra gru nrt syd
```

Every response carries `x-served-by-region` (and `x-served-by-machine` on Fly),
so you can always tell which Machine answered.

The `/_inbox` endpoint returns signup codes for an address, but only when
`DEMO_INBOX_TOKEN` is set and the caller sends it as `x-inbox-token`. It's how
the first-user agent finishes MFA without touching a real mailbox. Don't copy
it into a real app.

---

## Spoilers: the planted bugs

Both bugs are deliberate, deterministic, and covered by tests in
`tests/test_planted_bugs.py`. If one of those tests fails, someone fixed a bug
the demos depend on.

### Bug A: checkout fails for everyone served from São Paulo (`gru`)

Each region shows prices in its local currency and number format. The checkout
form round-trips the **displayed** total, and the server parses it back to
compare against the real price. The parser (`markets.parse_amount`) handles
comma decimals for EUR, because of an old German bug report, but not for BRL.

So `R$ 102,55` parses as `10255`, the totals never match, and Brazilian
customers get "Your cart changed while you were checking out" forever. Every
other region works.

This is what the region sweep (`01-region-sweep/`) finds and the repro agent
(`02-repro/`) turns into a failing test.

### Bug B: onboarding silently loops when the display name is blank

The onboarding form labels "Display name" as optional. The backend requires it,
and when it's missing the handler redirects back to the same page with no
error. A user who skips the optional field is stuck, with no idea why.

This is what the first-user agent (`03-first-user/`) trips over.

"""A tiny storefront with two deliberate bugs, built to be tested by agents.

Run locally:  make dev
Deploy:       see app/README.md
"""

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass, field
from html import escape
from urllib.parse import quote

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from starlette.routing import Route

from storefront.markets import Market, format_amount, local_amount, market_for, parse_amount

CATALOG: dict[str, tuple[str, int]] = {
    "stickers": ("Balloon sticker pack", 899),
    "mug": ("Hangar mug", 1899),
    "hoodie": ("Night shift hoodie", 5499),
}

SESSION_COOKIE = "sb_session"


@dataclass
class User:
    email: str
    password: str
    verified: bool = False
    display_name: str = ""
    team_size: str = ""
    onboarded: bool = False


@dataclass
class Store:
    users: dict[str, User] = field(default_factory=dict)
    inbox: dict[str, list[str]] = field(default_factory=dict)
    sessions: dict[str, str] = field(default_factory=dict)


# In-memory on purpose: one Machine per region keeps the demo simple.
STORE = Store()


def current_region(request: Request) -> str:
    """The region serving this request.

    On Fly, FLY_REGION is set on every Machine. Off Fly (local dev, tests),
    honor the fly-prefer-region header so one process can pretend to be any
    region.
    """
    on_fly = os.environ.get("FLY_REGION")
    if on_fly:
        return on_fly
    return request.headers.get("fly-prefer-region", "iad")


def page(request: Request, title: str, body: str, status: int = 200) -> HTMLResponse:
    region = current_region(request)
    market = market_for(region)
    html = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)} · Hangar Shop</title>
<style>
  :root {{ --ink:#1b1530; --muted:#6b6585; --line:#e6e2f0; --brand:#7c3aed; --bad:#b42318; }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; font:16px/1.5 system-ui, sans-serif; color:var(--ink); background:#faf9fd; }}
  header {{ display:flex; justify-content:space-between; align-items:center;
           padding:14px 20px; border-bottom:1px solid var(--line); background:#fff; }}
  header a {{ color:var(--ink); text-decoration:none; font-weight:700; }}
  .region {{ font-size:13px; color:var(--muted); }}
  main {{ max-width:640px; margin:0 auto; padding:24px 16px; }}
  .card {{ background:#fff; border:1px solid var(--line); border-radius:12px;
          padding:16px; margin-bottom:12px; display:flex; justify-content:space-between;
          align-items:center; gap:12px; }}
  .price {{ font-variant-numeric:tabular-nums; font-weight:600; }}
  button, .btn {{ background:var(--brand); color:#fff; border:0; border-radius:8px;
                 padding:10px 16px; font:inherit; cursor:pointer; text-decoration:none; }}
  label {{ display:block; margin:12px 0 4px; font-weight:600; }}
  .hint {{ font-weight:400; color:var(--muted); }}
  input {{ width:100%; padding:10px; border:1px solid var(--line);
          border-radius:8px; font:inherit; }}
  .error {{ color:var(--bad); font-weight:600; }}
</style></head>
<body>
<header><a href="/">🎈 Hangar Shop</a>
<span class="region" data-testid="region">Served from {escape(region)} ·
{escape(market.city)} · {escape(market.currency)}</span></header>
<main>{body}</main>
</body></html>"""
    response = HTMLResponse(html, status_code=status)
    response.headers["x-served-by-region"] = region
    machine = os.environ.get("FLY_MACHINE_ID")
    if machine:
        response.headers["x-served-by-machine"] = machine
    return response


def price_label(usd_cents: int, market: Market) -> str:
    return format_amount(local_amount(usd_cents, market), market)


# ---------------------------------------------------------------- storefront


async def home(request: Request) -> Response:
    market = market_for(current_region(request))
    cards = "".join(
        f"""<div class="card"><div><div>{escape(name)}</div>
        <div class="price" data-testid="price-{sku}">{escape(price_label(cents, market))}</div>
        </div><a class="btn" data-testid="buy-{sku}" href="/checkout?sku={sku}">Buy</a></div>"""
        for sku, (name, cents) in CATALOG.items()
    )
    return page(request, "Shop", f"<h1>Shop</h1>{cards}")


async def checkout(request: Request) -> Response:
    market = market_for(current_region(request))
    if request.method == "GET":
        sku = request.query_params.get("sku", "mug")
        if sku not in CATALOG:
            return page(request, "Not found", "<p>No such item.</p>", 404)
        name, cents = CATALOG[sku]
        total = price_label(cents, market)
        # The form round-trips the *displayed* total. That's the real bug's root.
        body = f"""<h1>Checkout</h1>
        <div class="card"><div>{escape(name)}</div>
        <div class="price" data-testid="total">{escape(total)}</div></div>
        <form method="post" action="/checkout">
          <input type="hidden" name="sku" value="{sku}">
          <input type="hidden" name="total" value="{escape(total)}">
          <button data-testid="place-order">Place order</button>
        </form>"""
        return page(request, "Checkout", body)

    form = await request.form()
    sku = str(form.get("sku", ""))
    if sku not in CATALOG:
        return page(request, "Not found", "<p>No such item.</p>", 404)
    expected = local_amount(CATALOG[sku][1], market)
    try:
        submitted = parse_amount(str(form.get("total", "")), market)
    except ArithmeticError:
        submitted = None
    if submitted != expected:
        body = """<h1>Checkout</h1>
        <p class="error" data-testid="checkout-error">Your cart changed while you were
        checking out. Please try again.</p><a class="btn" href="/">Back to shop</a>"""
        return page(request, "Checkout failed", body, 409)
    order = secrets.token_hex(3).upper()
    body = f"""<h1 data-testid="order-confirmed">Order confirmed</h1>
    <p>Order #{order}. Thanks for shopping.</p>"""
    return page(request, "Order confirmed", body)


# ---------------------------------------------------------------- accounts


def signed_in_user(request: Request) -> User | None:
    email = STORE.sessions.get(request.cookies.get(SESSION_COOKIE, ""))
    return STORE.users.get(email) if email else None


async def signup(request: Request) -> Response:
    if request.method == "GET":
        body = """<h1>Create your account</h1>
        <form method="post" action="/signup">
          <label for="email">Email</label><input id="email" name="email" type="email" required>
          <label for="password">Password</label>
          <input id="password" name="password" type="password" minlength="8" required>
          <p><button data-testid="signup-submit">Sign up</button></p>
        </form>"""
        return page(request, "Sign up", body)
    form = await request.form()
    email = str(form.get("email", "")).strip().lower()
    password = str(form.get("password", ""))
    if not email or len(password) < 8:
        return page(request, "Sign up", '<p class="error">Email and password required.</p>', 400)
    STORE.users[email] = User(email=email, password=password)
    code = f"{secrets.randbelow(10**6):06d}"
    STORE.inbox.setdefault(email, []).append(code)
    return RedirectResponse(f"/verify?email={quote(email)}", status_code=303)


async def verify(request: Request) -> Response:
    if request.method == "GET":
        email = escape(request.query_params.get("email", ""))
        body = f"""<h1>Check your email</h1>
        <p>We sent a 6-digit code to {email}.</p>
        <form method="post" action="/verify">
          <input type="hidden" name="email" value="{email}">
          <label for="code">Code</label>
          <input id="code" name="code" inputmode="numeric" autocomplete="one-time-code" required>
          <p><button data-testid="verify-submit">Verify</button></p>
        </form>"""
        return page(request, "Verify", body)
    form = await request.form()
    email = str(form.get("email", "")).strip().lower()
    code = str(form.get("code", "")).strip()
    user = STORE.users.get(email)
    if not user or code not in STORE.inbox.get(email, []):
        return page(request, "Verify", '<p class="error">That code didn\'t work.</p>', 400)
    user.verified = True
    token = secrets.token_urlsafe(24)
    STORE.sessions[token] = email
    response = RedirectResponse("/onboarding", status_code=303)
    response.set_cookie(SESSION_COOKIE, token, httponly=True, samesite="lax")
    return response


async def onboarding(request: Request) -> Response:
    user = signed_in_user(request)
    if not user:
        return RedirectResponse("/signup", status_code=303)
    if request.method == "GET":
        body = """<h1>Welcome aboard</h1>
        <form method="post" action="/onboarding">
          <label for="display_name">Display name <span class="hint">(optional)</span></label>
          <input id="display_name" name="display_name">
          <label for="team_size">Team size</label>
          <input id="team_size" name="team_size" required>
          <p><button data-testid="onboarding-submit">Continue</button></p>
        </form>"""
        return page(request, "Onboarding", body)
    form = await request.form()
    display_name = str(form.get("display_name", "")).strip()
    team_size = str(form.get("team_size", "")).strip()
    if not display_name:
        # PLANTED BUG (see app/README.md): the field says optional, the backend
        # requires it, and the validation error is swallowed. Users just land
        # back on this page with no explanation.
        return RedirectResponse("/onboarding", status_code=303)
    user.display_name = display_name
    user.team_size = team_size
    user.onboarded = True
    return RedirectResponse("/welcome", status_code=303)


async def welcome(request: Request) -> Response:
    user = signed_in_user(request)
    if not user or not user.onboarded:
        return RedirectResponse("/onboarding", status_code=303)
    body = f"""<h1 data-testid="welcome">You're all set, {escape(user.display_name)}</h1>
    <p><a class="btn" href="/">Go shopping</a></p>"""
    return page(request, "Welcome", body)


# ---------------------------------------------------------------- test inbox


async def inbox(request: Request) -> Response:
    """Codes sent to an address. Only on when DEMO_INBOX_TOKEN is set.

    This is how the first-user agent gets its MFA code without touching a real
    mailbox. Never enable it on anything but the demo.
    """
    expected = os.environ.get("DEMO_INBOX_TOKEN")
    supplied = request.headers.get("x-inbox-token", "")
    if not expected or not secrets.compare_digest(supplied, expected):
        return JSONResponse({"error": "inbox disabled"}, status_code=404)
    email = request.query_params.get("email", "").strip().lower()
    return JSONResponse({"email": email, "codes": STORE.inbox.get(email, [])})


async def healthz(request: Request) -> Response:
    return JSONResponse({"ok": True, "region": current_region(request)})


app = Starlette(
    routes=[
        Route("/", home),
        Route("/checkout", checkout, methods=["GET", "POST"]),
        Route("/signup", signup, methods=["GET", "POST"]),
        Route("/verify", verify, methods=["GET", "POST"]),
        Route("/onboarding", onboarding, methods=["GET", "POST"]),
        Route("/welcome", welcome),
        Route("/_inbox", inbox),
        Route("/healthz", healthz),
    ]
)

# Fyodor

A **compliant** reselling automation system: it discovers and tracks products,
scores opportunities on real profitability, monitors restocks/prices politely,
alerts you fast, and assists checkout — **within each site's rules**.

> Fyodor is built to make you faster and smarter, not to cheat. It respects
> per-customer limits, never tries to defeat CAPTCHAs/queues/anti-bot systems,
> and hands control back to you whenever a site requires a human. See
> [Compliance](#compliance) before using it.

## What it does

| Capability | Status |
|---|---|
| Watchlist + keyword/UPC/SKU/model fields | ✅ |
| Profitability engine (tax, shipping, fees, ROI, break-even, max-buy, min-resale) | ✅ |
| Market comparison from **sold** data + confidence/sell-through scoring | ✅ |
| Restock/price monitor (Shopify JSON), polite polling w/ jitter + ETag | ✅ |
| BUY / WATCH / SKIP recommendations with reasoning | ✅ |
| Alerts: console, Discord, Telegram, email — deduped + logged | ✅ |
| Inventory, purchase log, sales, PnL/win-rate dashboard | ✅ |
| Checkout assistant (single profile, respects limits, hands off on challenge) | ✅ |
| Risk controls: daily/per-product spend, qty caps, blacklists, manual gates | ✅ |
| Modes: dry-run, paper, alert-only, trusted-source auto-buy | ✅ |
| Web dashboard (FastAPI + Jinja) + JSON API | ✅ |
| SQLite (default) with Postgres upgrade path | ✅ |
| Docker, tests, install/deploy guides | ✅ |

## Architecture

```
fyodor/
  config.py        # YAML config + validation; secrets via env
  monitor.py       # Shopify-style stock/price polling (ETag, jitter)
  limits.py        # per-customer limit parsing + quantity clamping
  fees.py          # marketplace fee models (eBay/Amazon/StockX/GOAT/...)
  profitability.py # net profit, ROI, break-even, max-buy, min-resale
  market.py        # sold-data estimate + confidence + sell-through risk
  recommend.py     # BUY/WATCH/SKIP + risk controls + reasoning
  checkout.py      # Playwright auto-checkout (single profile, hands off)
  notifier.py      # Discord / Telegram / email / console + dedupe
  repository.py    # data access (SQLAlchemy)
  models.py db.py  # ORM + engine/session (SQLite -> Postgres)
  cli.py           # watch / web / login / check / init-db
  web/             # FastAPI dashboard + JSON API + templates
tests/             # unit tests (limits, profitability, recommend, config, repo)
```

The recommendation pipeline: **monitor** detects in-stock → **limits** clamp the
quantity to the store's cap → **market** estimates resale + confidence from sold
data → **profitability** computes net/ROI → **recommend** applies thresholds +
risk controls → **notifier** alerts → **checkout** assists (only if allowed).

## Install

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
# only needed for the checkout assistant:
playwright install chromium

cp config.example.yaml config.yaml      # edit your watchlist + thresholds
cp .env.example .env                    # put secrets here (gitignored)
python -m fyodor init-db
```

## Run

```bash
# Dashboard at http://127.0.0.1:8000
python -m fyodor web

# Watch + score + alert (starts in dry-run per config; no cart touched)
python -m fyodor --config config.yaml watch

# One-shot stock + recommendation pass, no checkout
python -m fyodor --config config.yaml check

# Log in once to the profile the checkout assistant will reuse
python -m fyodor --config config.yaml login
```

### Safety modes (in `config.yaml` under `modes:`)

- **dry_run** — alert + record only, never touches a cart. *Start here.*
- **paper** — simulates purchases into the DB so you can validate end-to-end.
- **alert_only** — discovery + alerts, no checkout machinery at all.
- **auto_buy_sources** — the *only* stores allowed to auto-buy, and only on a
  high-confidence `BUY`. Everything else needs your manual confirmation.

Auto-buy also requires: not low-confidence, under the daily spend cap, and the
quantity is always clamped to the per-customer limit.

## The profit calculator

`/calculator` in the dashboard (or `POST /api/calculate`) computes net profit,
ROI, break-even resale, **minimum acceptable resale**, and **recommended max
buy** for any hypothetical, plus a BUY/WATCH/SKIP verdict. Feed it recent *sold*
prices for a confidence-scored estimate.

```bash
curl -s localhost:8000/api/calculate -H 'content-type: application/json' -d '{
  "buy_price": 100, "quantity": 5, "limit_per_customer": 2,
  "marketplace": "ebay", "sold_prices": [160,162,158,165,159],
  "sales_tax_rate": 0.0825, "shipping_out": 12
}' | python -m json.tool
```

(Note `quantity` comes back clamped to `limit_per_customer`.)

## Deploy

**Docker (dashboard + watcher):**
```bash
docker compose up --build -d        # dashboard on :8000, watcher in dry-run
```
The watcher container is headless and intended for monitoring/scoring/alerts.
Run the **checkout assistant** (`fyodor ... watch` with checkout enabled, or
`login`) on a machine with your logged-in browser profile — not in a headless
container.

**Postgres:** set `FYODOR_DATABASE_URL=postgresql+psycopg://user:pass@host/db`
and `pip install psycopg[binary]`, then `python -m fyodor init-db`.

**Restart-safe:** all state lives in the DB. On restart the watcher re-syncs the
watchlist and resumes; the per-run purchase counter resets by design, so set the
**daily spend cap** as the durable guard against runaway buying across restarts.

## Tests

```bash
pip install pytest && python -m pytest
```

## Connectors (per-platform coverage)

Run `python -m fyodor coverage` (or `GET /api/coverage`) for the live list. Fyodor
uses **official APIs only** — it never scrapes sites that lack an API or forbid
automation; those degrade to a clear "manual only" status instead.

| Platform | Support | Needs |
|---|---|---|
| eBay (resale/sold prices) | ✅ official API | free dev keys; sold-data API needs production approval |
| Best Buy (stock/price) | ✅ official API | free API key |
| Shopify storefronts (many sneaker/collectible/LEGO-reseller/hype sites) | ✅ public JSON | nothing |
| Walmart | ⚙️ scaffold | approved Affiliate/IO creds + request signing |
| Amazon | ⚙️ scaffold | approved PA-API/SP-API creds |
| StockX | ⚙️ scaffold | gated developer API approval |
| Target, GOAT, Mercari, GameStop, LEGO | ⛔ no public API | manual; resale pricing via eBay sold data |
| Facebook Marketplace, OfferUp | ⛔ ToS prohibits automation | manual only |

New official-API connectors are added by implementing `RetailProvider` /
`SoldDataProvider` in `fyodor/providers/` and registering them in
`registry.py` — the framework, auth, and tests (with mocked HTTP) are already in
place. eBay sold data automatically feeds the confidence score for any watched
product that doesn't supply its own `sold_prices`.

## What still needs your setup / keys

- **Resale data connectors.** Sold-price estimation is fed by `sold_prices` in
  config, the calculator, or the `ManualSoldDataProvider`. Live connectors
  (e.g. eBay Marketplace Insights, StockX) need API keys and are added as new
  `SoldDataProvider` implementations — they are intentionally not bundled.
- **Store monitors beyond Shopify JSON.** `monitor.py` targets Shopify-style
  `/products/<handle>.js`. Other retailers should be added via their **official
  APIs / product feeds** where available; only fall back to polite scraping
  where a site's terms allow it.
- **Alert channels.** Put `FYODOR_DISCORD_WEBHOOK`, `FYODOR_TELEGRAM_TOKEN` /
  `FYODOR_TELEGRAM_CHAT_ID`, and SMTP creds in `.env`.
- **Checkout profile.** Run `fyodor login` once and sign in / save your address
  and payment in that browser profile.

## Security notes

- **No card storage.** Fyodor never stores payment details. Checkout reuses a
  local, gitignored browser profile (`browser-profile/`) you log into yourself.
  Keep that directory private; don't run trusted auto-buy on shared machines.
- **Secrets via env / `.env`** (gitignored), never in `config.yaml`.
- `config.yaml`, `state/`, `browser-profile/`, and `.env` are all gitignored.

## Compliance

This project is deliberately built to stay on the right side of the line:

- **Respects per-customer limits.** If a store says "2 per customer", Fyodor
  buys at most 2 — see `limits.clamp_quantity` and its tests.
- **No anti-bot evasion.** It does not solve CAPTCHAs, bypass queues/waiting
  rooms, defeat rate limits, or hide automation. On any such challenge the
  checkout assistant **stops and hands the browser to you**.
- **One account, one profile.** No fake accounts, identity rotation, address
  spoofing, or proxy abuse.
- **Polite polling.** Hard minimum interval + jitter + ETag caching, with
  backoff on HTTP 429.
- **Out of scope by policy.** Tickets and other restricted/licensed goods are
  blacklisted by default; keep them there.

You are responsible for following each site's Terms of Service and the laws in
your jurisdiction. Many retailers prohibit automated checkout outright — prefer
official APIs and manual confirmation, and use trusted auto-buy only where it's
permitted.

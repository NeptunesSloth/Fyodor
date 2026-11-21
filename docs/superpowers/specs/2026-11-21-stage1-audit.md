# Stage 1 hardening: audit

Branch `internet-play-stage1`, written for the owner to read before deciding to merge. Every statement below is something that
was read in the code or run; the command is given where one applies. Stage 1 prepares Fyodor to be exposed to the internet
through a tunnel (the tunnel itself is Stage 2). On a LAN nothing new is asked of the host or the players.

## What Stage 1 changed

Source: `git log --oneline 6f1f23c..ae4c21d~1` (12 commits, tasks 1-8; `git diff --stat 6f1f23c..ae4c21d~1` ends "98 files changed, 3142 insertions(+), 284 deletions(-)"). Task 9 is `ae4c21d` and `87ec8a0`.
All counts below are as of `87ec8a0`; `backend/` and `frontend/` are unchanged by the commit that adds this note, so the commands give the same counts there.

1. **Host secret cookie** (`e4ea325`, `a605d2f`; `backend/app/hostauth.py`). Host-only actions (creating tables, host tools) used
   to be allowed to whoever connected from the loopback address. Behind a tunnel every remote player arrives from loopback, so
   that rule would have made every player the host. The host is now whoever holds a random secret, made new on every server
   start (`secrets.token_urlsafe(32)`), compared with `hmac.compare_digest`, kept in a cookie. The launcher puts it in the
   address of the window it opens (`#host=...`); the page stores it in the cookie and removes it from the address. The secret
   is never printed to the console, and a refusal says how to become the host.

2. **Client address from trusted proxies** (`e69a8e8`; `backend/app/api/deps.py`). One function, `client_address`, now serves
   the rate limits and the logs. `X-Forwarded-For` is believed only when the connecting peer is listed in
   `FYODOR_TRUSTED_PROXIES` (none by default), and then the rightmost entry that is not itself a proxy is the client.

3. **Origin and Host guard** (`6dae48d`; `backend/app/netguard.py`, `net_guard` in `backend/app/main.py`). The outermost check on
   every request refuses a `Host` this server does not answer to (400; the DNS-rebinding defence) and a state-changing request
   (POST, PUT, PATCH, DELETE) the browser marks as cross-site or whose `Origin` is not this server's own (403). The game socket
   checks the `Origin` too. Extra host names are added with `FYODOR_EXTRA_HOSTS`.

4. **Socket first-message authentication** (`bf02641`, `e3e858b`). The game socket takes no seat token in its address. The
   client's first message carries the token; the server waits 5 seconds for it, sends nothing before it succeeds, and every
   failure closes with code 4403 and one reason. Seat links keep their token after the `#`, so it is never sent to a server, and
   the page strips it from the address bar. The old `?token=` form works only with `FYODOR_LEGACY_WS_TOKEN=1`.

5. **Guess limits** (`43fcd84`, `bae2964`; `AttemptLimiter` in `backend/app/netguard.py`). Wrong room codes and passwords count
   against the client address (5 failures per 15 minutes, shared with the host-session endpoint) and wrong passwords against the
   room (30 per 15 minutes). An unknown code and a wrong password answer alike. A right secret is never refused, and a right
   join no longer clears the failures.

6. **Password hashing** (`b871e31`). Room passwords use PBKDF2 at 600,000 rounds; a hash made with fewer rounds is upgraded the
   next time the right password is used.

7. **Socket caps and heartbeat** (`df7424e`, `6df0dbd`). Open game sockets are capped per seat and per client address (24 per
   address, authenticated or not); a seat that connects again replaces and disconnects its older socket. The server pings every
   25 seconds and closes a socket silent for 90 seconds (4408). A frame larger than a message may be is refused as it arrives,
   the limit is in bytes, and pongs are rate-budgeted.

8. **Seat-scoped action ids** (`bd94fe7`). The remembered outcome of a retried action is keyed on the seat as well as the
   client's action id, so one seat can neither collide with nor probe another seat's ids; the bound (512) is per seat.
   Migration 14 recreates the table with an actor column (see risk 5).

9. **Response headers** (`ae4c21d`; the cookie rule in `87ec8a0`). `Strict-Transport-Security: max-age=31536000` is sent only when the request came over
   https, directly or as reported by `X-Forwarded-Proto` from a trusted proxy (same trust rule as the client address; the check
   is the shared `_is_proxy` in `deps.py`). Never `includeSubDomains` or `preload`, because the host may be a shared tunnel
   domain. The header middleware now wraps the Host/Origin guard, so a 400 or 403 refusal carries the headers too. `/docs`,
   `/redoc` and `/openapi.json` are not registered unless `FYODOR_DEV_TOOLS=1`. This is the existing `Settings.dev_tools` flag
   (it already guarded EXPORT RULES SCENARIO; the launcher does not set it). With it off, a request for those paths gets the
   same 404 (`{"detail":"Not Found"}`) as any unknown path. The host cookie's `Secure` flag (`api/host.py`, the only `set_cookie` in `backend/app`: `git grep -n "set_cookie" -- backend/app`) uses the same
   `is_https` decision, so it is set behind a TLS-terminating trusted proxy too.

## Rendering audit

Question: can text typed by a player (names, chat, notes, deck names) be interpreted as HTML or script by the page?

```
$ git grep -n "innerHTML\|dangerouslySetInnerHTML\|insertAdjacentHTML\|document.write" -- frontend/src
(no output; exit status 1 = no matches)
```

No hits for any of the four. Judgement: the page renders user text only as React text nodes.

Further sinks, run for completeness:

```
$ git grep -n "eval(\|new Function\|srcdoc\|outerHTML\|javascript:\|createContextualFragment\|DOMParser\|v-html\|\.html(" -- frontend/src
(no output; exit status 1 = no matches)
```

User-influenced `href` values: `git grep -n "href=\|\.href *=\|window.open\|location.href" -- frontend/src` finds 50 lines (no test file matches:
the same command with `':!*.test.*'` also gives 50). Reading each: every one is a fixed string, a fragment (`#/...`) built from a
server-made id, or a same-origin download, except the last bullet.

- Fixed fragments or constants: `App.tsx:81,83` (the app's own menu table), `Eliminated.tsx:131-133`, `EndGameDialog.tsx:41`,
  `GameNight.tsx:377`, `GameScreen.tsx:102`, `TestEnding.tsx:193`, `TopBar.tsx:50,199` (`window.open("#/stats")`),
  `CardBrowser.tsx:55`, `FriendDecks.tsx:76`, `DeckPicker.tsx:44`, `Home.tsx:94,102,114,136,152`, `PlayPage.tsx:595`,
  `PodStatsPage.tsx:116`, `SessionRecap.tsx:26`, `SettingsPanel.tsx:314,366,621`, `TeachPage.tsx:276`, `Welcome.tsx:69,83`,
  `PersonalDeckImports.tsx:70`, `PhaseDial.tsx:94` (`<textPath href="#pd-label-N">`). Safe.
- Fragments made from server ids: `Eliminated.tsx:332` (`#/decks/` + `encodeURIComponent(deck_id)`), `BulkImportDialog.tsx:127`,
  `DeckLibrary.tsx:257,261,278,279`, `Home.tsx:114,159` (`#/game/<game_id>`). Safe.
- `PracticeBar.tsx:84` and `WatchPip.tsx:56,72`: `back` is `liveHash({of, seat, local})` (`PracticeBar.tsx:33`), a `#/game/<id>`
  fragment (`eliminationHub.test.ts:52`). Safe.
- Same-origin downloads: `RulesHud.tsx:1175` (`/api/games/<id>/rules/scenario`), `PlayPage.tsx:912`, `PodStatsPage.tsx:108`,
  `SettingsPanel.tsx:471,655` (`encodeURIComponent(b.name)`), `TeachPage.tsx:418,436`. Safe.
- `DeckEditor.tsx:369` `href={deck.source.url}`: the one value a client can set to anything (`DeckSource.url` in
  `backend/app/decks/models.py:79` is a free string of up to 300 characters; the server sets it for Archidekt imports, but the
  deck-save API accepts whatever it is sent). A `javascript:` URL here would be clickable. React 19 (`"react": "^19.3.0"`
  in `frontend/package.json`) refuses to run `javascript:` URLs in `href`, and saving a deck is a host action, so this is
  rated low and left unchanged here; see risk 9.

Third-party hosts in the Content-Security-Policy: none. The exact policy (from `backend/app/main.py`):
`default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self' ws: wss:;
object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'`. The only non-`'self'` sources are the schemes
`ws:` and `wss:` (the game socket, which is this same host; they allow a socket to any host, which is why `connect-src` is
the one directive worth tightening in Stage 2), `data:` for inline images, and `'unsafe-inline'` for styles only (no inline or
eval script). Card pictures are served from this server's own image cache, so no card-image host is allowed. The test pins that
every source in the policy is one of those keywords or schemes, with no `unsafe-eval`, no `http:`/`https:`/`*`, and no host name.

## Log audit

Where player-supplied text reaches a log or the console. Command:
`git grep -n "log\.\(info\|warning\|error\|debug\|exception\)\|print(" -- backend/app` gives 110 lines (92 with `':!backend/app/rules'`), as of `87ec8a0`;
a few are false matches such as `fingerprint(`; all read for lines that interpolate request or player data.

| Site | Player text | Result |
|---|---|---|
| `hub.py` `create_lobby` ("Created lobby %s (%s)", `settings.name`) | lobby name | `LobbySettings.name` is passed through `clean_text` by a field validator (`lobby.py`), so control characters are gone before the hub sees it. |
| `hub.py` `create_room` (`session.state.name`) | game name | the request model cleans it with `clean_text(v, 80)` (`games.py`, game name validator). |
| `art_keeper.py` (3 lines, `deck.name`) | deck name | `DeckIn` cleans names with `clean_text(v, 120)` (`decks/models.py`) on every save and import. |
| `games.py` "Could not apply joining player's name: %s" (`exc`) | the joining name inside an error text | the name is cleaned by `clean_text(body.name, 40)` before the action is built. |
| `session.py`/`bot.py` `action.type`, `payload.get("type")` | action type | a validated enumeration, not free text. |
| `hub.py` "Dropping connection %s: %s" | none | connection id and an exception from the socket. |
| `launcher.py` `print(...)` | none from players | start-up text, addresses, file names. |
| Chat and notes | not logged anywhere | no log call reads chat, notes or action payload text. |

Result: no site needed a code change, because every player-text value is cleaned at the boundary by `app/textutil.py`
(`clean_text` removes C0 controls including `\n`, `\r` and `\x1b`, DEL, and bidi overrides). Tests added in
`backend/tests/test_security_headers.py` pin this where the text reaches a log: a lobby made through the API with a name
containing `\n` and `\x1b` writes one log line with no control character, the same through the hub directly, and a `DeckIn`
name is clean. Not tested directly: the art-keeper log line (it needs a deck, a card database and an offline fetch; the value it logs
is the `DeckIn` name above).

Secrets in logs (single-line calls): `git grep -n -i "log\.[a-z]*(.*\(token\|secret\|password\|passwd\|invite\|code\|cookie\)" -- backend/app` gives two
lines, both false matches (`res.status_code` in `cards/downloader.py`; `card_id` in `cards/token_art.py`).
`git grep -n "print(.*\(token\|secret\|password\|cookie\)" -- backend/app` gives no match. Both greps see only the line a call starts on, so wrapped calls were checked too with
`git grep -n -A4 "log\.\(info\|warning\|error\|debug\|exception\)(\|print(" -- backend/app | grep -i "token\|secret\|password\|passwd\|invite\|code\|cookie"`:
it prints 53 lines (as of `87ec8a0`: each log or print call and the four lines after it), all read, all false matches: `status_code=204` (`games.py:543`) and `res.status_code` (`downloader.py:172`); the word "Token" in a message and the lines after it (`token_art.py:88-92`); `host_url(`/`read_host_secret(` building the window address (`launcher.py:217,277`, never printed); the words "invite link" in a console message (`launcher.py:307`); `encode_query` (`discovery.py:323`); `secrets.token_urlsafe`, `code=` and docstrings in `hub.py:395-415,585` (creating rooms, not logging them); and `fingerprint(`/`_fingerprint(`/`sha1` in `app/rules` (`replace.py:297`, `token_creation_replacements.py`, `token_stacks.py`). The word-matches are not values being logged; no logged value was a
token, secret, password, cookie or code. The host secret reaches the launcher
only to build the address of the window it opens (`launcher.py`), not a print or log call. Seat tokens travel in the
`X-Seat-Token` header and the socket's first message (`games.py` `AUTH_DEADLINE` handler says it "never logs what it was sent").
The join code a player tries is not logged (the guess limiter counts, it does not record). Room ids are logged when a room is
created ("Created lobby <id>"); these are the ids of the host's own tables, written to the host's own console and diagnostics, not
the code of a table somebody else is guessing at. The uvicorn access log is uvicorn's default (`uvicorn.config.Config(app='x').access_log` is `True`; `launcher.py` `server_options` passes `log_level` but not `access_log`), so at the default INFO level it records request paths, which contain game ids
but no token (the seat token is a header); only the legacy switch (risk 7) would put a token in a logged address.

## Headers

Evidence: the tests in `backend/tests/test_security_headers.py` (`test_always_sent_headers`, `test_csp_pins`, `test_no_hsts_on_plain_http`,
`test_hsts_on_direct_https`, `test_hsts_when_a_trusted_proxy_says_https`, `test_no_hsts_when_a_stranger_says_https`,
`test_hsts_is_exactly_max_age`, `test_refusals_carry_the_headers_too`). Run with
`.venv/Scripts/python -m pytest -q -rfE -p no:cacheprovider tests/test_security_headers.py`. The values they assert, on a `GET /api/health`
that returns 200:

Over plain http (peer 203.0.113.9, no proxy), status 200:

```
content-type: application/json
vary: Origin
x-content-type-options: nosniff
x-frame-options: DENY
referrer-policy: no-referrer
content-security-policy: default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self' ws: wss:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'
```

Over https (direct `https://` request, or `X-Forwarded-Proto: https` from a trusted proxy), status 200: the same lines (the test asserts `x-content-type-options`, `x-frame-options`, `referrer-policy` and the CSP equal to `app.main.CSP`) plus

```
strict-transport-security: max-age=31536000
```

Not sent: HSTS on plain http, including when a peer that is not a trusted proxy sends `X-Forwarded-Proto: https`; the test
`test_no_hsts_when_a_stranger_says_https` pins it. `X-Content-Type-Options`, `X-Frame-Options: DENY` and `Referrer-Policy:
no-referrer` were already sent before this task (and `frame-ancestors 'none'` is in the CSP); they are now pinned by tests.

## Remaining risks

1. Behind any proxy or tunnel without `FYODOR_TRUSTED_PROXIES`, every remote client shares one address, so the join limit (5 failures per 15 minutes) and the connection cap (24 per address) are shared by all of them; a stranger's wrong guesses can block remote joins for 15 minutes. Stage 2's tunnel port fixes this by reading the provider's client-address header. Until then, do not front Stage 1 with a tunnel without setting trusted proxies.
2. The host secret is in the launcher-opened window's address (`#host=...`) until the page removes it at start-up; the browser's own `browser.log` (Chromium `--enable-logging`, in the host's data folder) records console lines with the page address of the moment, so an error logged before the page clears the address could capture it. The secret is new on every start and the file is on the host's own machine.
3. A seat link (`/#/game/<id>?seat_token=...`) keeps the token after the `#`, so it is never sent to a server, but it sits in the recipient's browser history until the page clears it.
4. A request with neither an `Origin` nor a `Sec-Fetch-Site` header is allowed to change state (needed for the Fyodor-to-Fyodor LAN handoff and scripts); browsers older than about 2019 send neither on some cross-site form posts. Authority still needs a seat token or the host cookie.
5. Migration 14 drops remembered action ids written before the upgrade; a retry that spans the upgrade restart could apply twice.
6. An upgraded room-password hash is written to disk only for started tables (lobby rooms are not saved at all).
7. The legacy socket switch `FYODOR_LEGACY_WS_TOKEN=1` puts the seat token back in the URL; it is off by default and should stay off.
8. `mypy` in this environment is version 2.4.1 and reports 303 errors on this branch as of `87ec8a0` (`.venv/Scripts/python -m mypy app tools 2>&1 | tail -1` gives `Found 303 errors in 15 files`); the controller saw the same count on a master-based checkout. The gate used was "no new errors in touched files", not a clean run.

9. `DeckSource.url` is an unvalidated string shown as a link in the deck editor (`frontend/src/pages/DeckEditor.tsx:369`). React blocks `javascript:` links and saving a deck is host-only, but decks can arrive from other players through LAN deck sharing. A server-side http(s) check is queued to be fixed before merge (not done yet).
10. The art-keeper logs a stored deck's name (`backend/app/cards/art_keeper.py:149-158`). Names are cleaned when a deck is saved or imported, so a deck stored before that cleaning existed is the only uncovered case.

## Open items for Task 10

- Full test-suite summaries.
- `bandit`, `pip-audit`, `npm audit` results.
- The 13-point review gate walk.
- The two-device manual check.
- The security review.

# Stage 1 hardening: audit

Branch `internet-play-stage1`, written for the owner to read before deciding to merge. Every statement below is something that
was read in the code or run; the command is given where one applies. Stage 1 prepares Fyodor to be exposed to the internet
through a tunnel (the tunnel itself is Stage 2). On a LAN nothing new is asked of the host or the players.

## What Stage 1 changed

Source: `git log --oneline 6f1f23c..ae4c21d~1` (12 commits, tasks 1-8; `git diff --stat 6f1f23c..ae4c21d~1` ends "98 files changed, 3142 insertions(+), 284 deletions(-)"). Task 9 is `ae4c21d` and `87ec8a0`.
Counts in this file were re-run at `eac3708` (the last commit that changes `backend/` or `frontend/`; the gate's other commits are `1acd3fc` before it and documents after it); they gave the figures stated, the same as at `87ec8a0` unless a section says otherwise.

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
   address, authenticated or not); a seat whose token is replaced (a reclaim, a kick, leaving the lobby) has its older sockets closed (4403); a fifth socket for the same seat is refused (4429), the four older ones stay. (The wording here earlier, that a seat which connects again replaces its older socket, was wrong: `test_a_fifth_socket_for_one_seat_closes_4429_and_the_first_four_stay` pins the refusal.) The server pings every
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
frontend/src/pages/deckBits.test.ts:130:    for (const bad of ["javascript:alert(1)", ...
frontend/src/pages/deckBits.ts:138:/** A deck source's address is a link only when it is an http(s) address; anything else (javascript:, ...
```

At `87ec8a0` this printed nothing. At `eac3708` the two lines above are the only matches, both added by the deck-link fix: a comment and a test string naming the
scheme that is refused. Neither is a sink.

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
- `DeckEditor.tsx:369` `href={isHttpUrl(deck.source.url) ? ...}`: the one link whose address is not a fixed string. At `87ec8a0` it was
  `href={deck.source.url}` and `DeckSource.url` (`backend/app/decks/models.py`, line 79 then) was a free string of up to 300 characters.
  The deck-save API cannot set it: `DeckIn` has no `source` field (only the stored `Deck` has one). A `DeckSource` is built on three
  paths, listed under risk 9; a `javascript:` URL could only have come from a stored row (an old save or a restored backup). React 19
  (`"react": "^19.3.0"` in `frontend/package.json`) refuses to run `javascript:` URLs in `href`, so it was rated low; it is closed in
  both places now (the model refuses anything but http(s), and the editor links only an address starting `http://` or `https://`).

Third-party hosts in the Content-Security-Policy: none. The exact policy (from `backend/app/main.py`):
`default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self' ws: wss:;
object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'`. The only non-`'self'` sources are the schemes
`ws:` and `wss:` (the game socket, which is this same host; they allow a socket to any host, which is why `connect-src` is
the one directive worth tightening in Stage 2), `data:` for inline images, and `'unsafe-inline'` for styles only (no inline or
eval script). Card pictures are served from this server's own image cache, so no card-image host is allowed. The test pins that
every source in the policy is one of those keywords or schemes, with no `unsafe-eval`, no `http:`/`https:`/`*`, and no host name.

## Log audit

Where player-supplied text reaches a log or the console. Command:
`git grep -n "log\.\(info\|warning\|error\|debug\|exception\)\|print(" -- backend/app` gives 110 lines (92 with `':!backend/app/rules'`), as of `eac3708`;
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
it prints 53 lines (as of `eac3708`: each log or print call and the four lines after it), all read, all false matches: `status_code=204` (`games.py:543`) and `res.status_code` (`downloader.py:172`); the word "Token" in a message and the lines after it (`token_art.py:88-92`); `host_url(`/`read_host_secret(` building the window address (`launcher.py:217,277`, never printed); the words "invite link" in a console message (`launcher.py:307`); `encode_query` (`discovery.py:323`); `secrets.token_urlsafe`, `code=` and docstrings in `hub.py:395-415,585` (creating rooms, not logging them); and `fingerprint(`/`_fingerprint(`/`sha1` in `app/rules` (`replace.py:297`, `token_creation_replacements.py`, `token_stacks.py`). The word-matches are not values being logged; no logged value was a
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

## Gate results

Everything in this section and the next two was run at `eac3708` (the last commit that changes `backend/` or `frontend/`; the commits
after it change documents only). Line numbers in the review-gate walk are as of `eac3708` too. Commands run from `backend/` unless a path says otherwise.

**Commit A, four fixes queued by earlier reviewers (`1acd3fc`).** The `Origin` header must equal its own serialisation
(`scheme://host[:port]`; `http://127.0.0.1:8000#`, `...?`, an empty port, a leading zero, whitespace and tabs are refused, as is `[::1]:` in a
`Host`); `FYODOR_EXTRA_HOSTS` entries are validated at start; the per-seat journal prune is asserted and its test confirmed red when the
`actor = ?` clause is removed (the break was local and not committed); `DeckSource.url` is limited to http(s) (risk 9). One thing
found on the way: `npm run typecheck` failed on the branch before this commit, with 3 errors in `frontend/src/services/gameSocket.test.ts`
(lines 227-229, `number | undefined` passed to `toBeGreaterThan`, added by `df7424e`); fixed in the same commit with non-null assertions
in the test. A case kept on purpose: the old tests expect `HTTP://Play.Example.org` to match `play.example.ORG`, so the strict form is
matched case-insensitively (a browser always sends lower case).

**Fixes after review (`eac3708`).** A JSON deck upload with an id that is not 1 to 12 digits (`"1 2"`, a newline, `javascript:...`) made the new url check
raise inside `import_any`, an unhandled error where the upload used to be accepted; the id from an uploaded file now makes a link only through
`archidekt.valid_deck_id`, otherwise the deck imports with no source id and no url. `SessionBody.secret` is limited to 256 characters: a longer body is a
422 before any compare, and it is **not** counted as a failed attempt (a stranger's malformed request must not spend the host's five-per-15-minutes budget;
`test_host_auth.py::test_an_oversized_secret_is_a_422_that_costs_the_address_nothing`). The import order in `app/api/games.py` is fixed (imports only). The
`Origin` pattern is matched on the raw string, ASCII only and case-insensitively, so the Kelvin sign is not read as `k`. A test now covers the over-limit
message after authentication (point 10).

**ruff.** `.venv/Scripts/ruff check . --output-format concise` ends `Found 10 errors.` and is **not clean**:

| Rule | Count | Where |
|---|---|---|
| I001 import block not sorted | 5 | `app\game\engine.py:3`, `app\game\handlers\dummy.py:98`, `app\game\views.py:9`, `tests\conftest.py:1`, `tests\test_rules_layer_whole_conditions.py:8` |
| SIM102 nested `if` | 3 | `app\rules\costs.py:287`, `app\rules\random_choice_receipts.py:261`, `app\rules\taught.py:266` |
| F841 unused variable | 1 | `tests\test_rules_round5_additional_costs.py:189` |
| SIM300 Yoda condition | 1 | `tests\test_rules_token_batch_one_pile.py:49` |

The same command in a checkout of `master` (`3fde593`, the commit this branch starts from, run with this environment's ruff) gives `Found 11 errors.`. Compared
by rule and file with the line numbers removed, the 10 above are all in master's 11; master's extra one is an I001 in `app\services.py:3`, which this branch's
edit to that file fixed. (Before `eac3708` the branch also had an I001 in `app\api\games.py:3`, introduced by `6df0dbd`; fixed in `eac3708`.) So no ruff error is
new on this branch. The comparison was made on saved outputs of the two runs (not part of the repository).

**mypy.** `.venv/Scripts/python -m mypy app tools 2>&1 | tail -1` gives `Found 303 errors in 15 files (checked 1183 source files)`
with mypy 2.4.1 (`.venv/Scripts/python -m mypy --version`; the project notes name 2.3.1). The same command in the `master` checkout gives
`Found 303 errors in 15 files (checked 1180 source files)`, and the error messages with their line numbers removed are identical (compared as sorted
lists). Per file (`.venv/Scripts/python -m mypy app tools | grep -o "^[^:]*" | sort | uniq -c`, the last line it prints being the total):

```
 1 app\api\games.py        4 app\api\night.py       3 app\api\teach.py       3 app\game\bot.py
12 app\game\factory.py     1 app\game\resolve.py    3 app\multiplayer\hub.py 1 app\rules\casting.py
 1 app\rules\designations.py   265 app\rules\replace.py   4 app\rules\taught.py   1 app\rules\triggers.py
 1 app\rules\view.py       1 app\storage\taught.py  2 tools\soak.py
```

The files this branch touched under `app` and `tools` are listed by `git diff --name-only 6f1f23c..eac3708 -- backend/app backend/tools` (19 files). Two of
the 15 are among them: `app/api/games.py` (1 error) and `app/multiplayer/hub.py` (3). Their errors are `games.py:1272` (an assignment of `str | None` to a `str`) and
`hub.py:736-738` (a `Future` assigned to a variable typed `bool`); `git blame` puts those lines in `8263ed7` and `d695cde`, both ancestors of `6f1f23c`, so
the erroring lines predate this branch (none is on a line this branch added or changed). No file this branch added has a mypy error.

**Frontend.** In `frontend/`: `npm run typecheck && npm test` exits 0, `Test Files  157 passed (157)`, `Tests  1612 passed (1612)`.

**Backend tests.** The full suite takes about an hour and was not run by the author of this section. It can fail on the test described below.

Full suite: run by the controller, the result goes on the next line.

FULL SUITE: pending controller run

What was run: `.venv/Scripts/python -m pytest -q -rfE -p no:cacheprovider -n 6 tests --ignore-glob="tests/test_rules_*"` (about one minute; this environment
prints no final count line, so the result is judged by the exit code and the absence of `FAILED`/`ERROR` lines). At `eac3708` it exited 0 with no `FAILED`.

**An unresolved intermittent failure.** `tests/test_interim_views.py::test_a_long_chain_streams_interim_views_per_viewer_and_stays_one_action` (`assert N >= 3`
on a count of the `interim` messages a seat received) has failed on this branch and its cause is **not known**. Counts on this branch, from the runs I made:
4 runs of the command above, 1 failed (`assert 2 >= 3`, the first run; the `FAILED` line is in a saved output); the file alone with
`.venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_interim_views.py`, 30 runs, 2 failed (`assert 1 >= 3` in the one whose message I kept; the
other showed only `FAILED`). That is 3 failures in 34 runs; the numbers of passing lone runs (8, 10 and 10 in batches, and one earlier) come from my notes of the
runs, and only three outputs were saved, so read the totals as "at least". In a checkout of `master` (`3fde593`, confirmed to import that checkout's `app`) the file passed 8 of 8 lone runs.
`hub.py` and the socket path, which the test drives, changed on this branch, so this may be a regression; it has not been established either way. The test file was
not touched by the branch. Risk 16.

## Security tools

Dev tools installed in the environment only (`.venv/Scripts/python -m pip install bandit pip-audit`: bandit 1.9.4; pip-audit; nothing added to
`pyproject.toml` or any requirements file; `git status` shows no change to them).

**bandit** (`PYTHONUTF8=1 .venv/Scripts/python -m bandit -r app -q`, 201,850 lines scanned, exit 1 because it found issues): 790 findings, **8 High, 27 Medium,
755 Low**. Without `PYTHONUTF8=1` the text report crashes on this Windows console (`UnicodeEncodeError: 'charmap' codec can't encode character '★'`);
that is the tool's report writer, not a finding. To tell which findings are on lines this branch added, each finding's lines were checked with `git blame`
against `git rev-list 6f1f23c..eac3708` (a throwaway script, not kept; the totals were re-run at `eac3708` and are unchanged, only the `games.py` B112 moved from line 1854 to 1869): **one** of the 790 is on such a line (B105 at `app/hostauth.py:16`, below); every other
finding is in code that was there before this branch. Nothing is fixed in a commit by this task; each one is accepted for the reason given.

High (8), each read:

| Id | Where | Answer |
|---|---|---|
| B324 sha1 (7) | `app/rules/effects.py:4206`, `replace.py:297`, `replace.py:505`, `replacements.py:1578`, `taught.py:558`, `taught.py:602`, `unless_pays.py:137` | Accepted: a short digest used as a key or fingerprint of rules data (de-duplication, receipts, a cache key), never to authenticate anything or to resist an attacker; none is on a line this branch added. `usedforsecurity=False` would silence the tool and is left for a rules-engine change. |
| B613 trojansource (1) | `app/textutil.py:8` | Accepted: the line is the regular expression that lists the bidirectional-override characters `clean_text` strips, so the file has to contain them. It is the defence, not the problem. |

Medium (27), each read:

| Id | Where | Answer |
|---|---|---|
| B608 SQL built from strings (19) | `app/api/tools.py:60`, `app/services.py:216`, `app/storage/journal.py:66` | Accepted: the table name comes from a literal tuple in the same file (marked `# noqa: S608 - fixed names`); `journal.py:66` is the `forget` loop over `live_rooms`, `room_journal`, `client_actions`, and the game id is bound as a parameter. |
| | `app/cards/repository.py:137,150,160,166,196,240,290,403,533`, `app/cards/share.py:159,170` | Accepted: the interpolated parts are the module constant `SUMMARY_COLUMNS`, a run of `?` marks sized from a list's length, an `int()`-cast constant, or `WHERE` fragments produced by `compile_query` whose values travel as bound parameters. No request text is placed in the SQL string. |
| | `app/stats/repository.py:218,226,233` | Accepted: the interpolated `_COUNTS` is a class-level constant; ids are bound. |
| | `app/storage/db.py:87`, `app/storage/taught.py:77` | Accepted: `db.py:87` runs the migration scripts that are in the code plus an integer version; `taught.py:77` appends the fixed fragment `, enabled = ?` and binds every value. |
| B610 Django `extra` (4) | `app/decks/service.py:421`, `app/rules/casting.py:4103`, `app/rules/combat.py:223`, `app/rules/trigger_multipliers.py:290` | False positive: `.extra(...)` is a method of this project's own objects (for example `allow.extra(card)`), not Django's query method; Django is not used. |
| B310 `urlopen` (2) | `app/launcher.py:122,243` | Accepted: the address is `http://127.0.0.1:<port>/api/health` built by the launcher for its own server (marked `# noqa: S310`); no outside input. |
| B104 bind all interfaces (1) | `app/launcher.py:268` | Accepted, with the facts stated: binding `0.0.0.0` is the **default** of the launcher, not an opt-in (`args.lan = not args.local` at `launcher.py:266`; only `--local` avoids it, the `--lan` flag does nothing). LAN play is the product's default and needs the server reachable on every interface. What protects that exposure is what this stage built: the Host and Origin guard, the host-secret cookie, seat tokens and the guess and connection limits. The `# noqa: S104 - explicit opt-in for LAN play` comment on that line is therefore stale (risk 17); the code and the comment are not changed in this task. |
| B301 pickle (1) | `app/rules/plan.py:73` | Accepted: `pickle.loads(pickle.dumps(state))` is a deep copy of the game state in memory; it never reads a file or a message. |

Low (755), grouped by rule (not read one by one): B101 `assert` used 706 (in 286 files; no line this branch added to `app` is an `assert`; authority is checked with explicit `HTTPException`s); B105 hard-coded password string 34 (names such as `token` or `password` in rules and parser code; the one on a branch line is `app/hostauth.py:16`,
`SECRET_FILE = "host.secret"`, the name of a file, not a secret); B112 `try/except/continue` 4 (`app/api/games.py:1869`, `app/api/rules.py:60`, `app/multiplayer/hub.py:999`,
`app/rules/view.py:113`, all before this branch); B311 `random` 2 (`app/decks/bot_decks.py:45`, `app/rules/scenario.py:111`: picking a bot deck and a scenario, not tokens); B404 `subprocess` import 3,
B603 `subprocess` call 4, B607 partial executable path 1 (`app/api/shortcut.py`, `app/api/updates.py`, `app/launcher.py`: launching the app and the updater, fixed arguments);
B403 `pickle` import 1 (`app/rules/plan.py:6`, see B301).

**pip-audit** (`PYTHONUTF8=1 .venv/Scripts/pip-audit`, which audits the installed environment, 69 packages, against the public advisory database; exit 1): `Found 12 known
vulnerabilities in 1 package`, all in **`pip 25.0.1`** (six advisories, each listed twice because of an alias: PYSEC-2026-1795 fixed in pip 25.3, PYSEC-2026-1796 in 26.0,
PYSEC-2026-2875 and PYSEC-2026-2876 in 26.1, PYSEC-2026-196 in 26.1.2, PYSEC-2026-3721 in 26.2). No other package, FastAPI, Starlette, uvicorn, pydantic and httpx
included, has a known advisory. It also skipped `fyodor-backend 0.1.0` ("not found on PyPI": it is this project). Answer: **open item**, not fixed by this task. `pip` is
the installer inside the development environment, is not imported by Fyodor and is not part of what a player runs; upgrading it (`python -m pip install --upgrade pip`, to 26.2 or
later) is a one-line change for whoever maintains the environment.

**npm audit** (in `frontend/`, `npm audit`, exit 1): `4 vulnerabilities (2 moderate, 2 high)`, all in development tooling; `npm audit --omit=dev` says `found 0 vulnerabilities`.

| Package | Installed | Severity | Advisory | Answer |
|---|---|---|---|---|
| `vite` | 8.3.1 | high | affected 8.3.0 - 8.3.2: launch-editor flaws (GHSA-698v-4r3x-3vcv, -r825-w8mm-5pxw, -587h-7wmj-h5pm), cross-origin script execution through custom middleware (GHSA-9jrq-w75r-8gcw), reading files outside `server.fs` (GHSA-rq7h-c2jc-7f22, GHSA-vfpm-58rq-9qcg) | **Open item.** These apply to the Vite development server (`npm run dev`), which is not part of what the host runs: the launcher serves the built `frontend/dist` files. `npm audit` reports a fix is available (`fixAvailable: true` in `npm audit --json`); not upgraded here, as instructed, and no version number is claimed. |
| `source-map-js` | 1.2.1 | high | GHSA-68fv-2mgg-jv7q, event-loop denial of service from crafted source-map offsets (affected up to 1.2.1) | **Open item.** A build-time dependency of the CSS tooling; it runs on the developer's machine when building, on files from this repository. `npm audit` reports a fix is available. |
| `vitest` | 5.0.2 | moderate | via `@vitest/mocker` | **Open item.** Test runner only. `npm audit` reports a fix is available. |
| `@vitest/mocker` | 5.0.2 | moderate | GHSA-qxg6-89mg-rqv8 (code injection through unauthenticated manual mock registration), GHSA-xp26-3454-mjgp (Windows path traversal in its redirect allowlist) | **Open item.** Test runner only. |

Nothing from the three tools is in code this branch added, other than the B105 line, which is a file name. No finding needs a code change in Stage 1; the five open
items above are all dependency upgrades, which the gate does not do.

## The 13-point review gate

(File and line numbers in this walk are as of `eac3708`.)

The spec's "Review gate (every stage)" (`docs/superpowers/specs/2026-11-21-internet-play-design.md`), one entry per point. "Suite" means the tests are part of the
full backend run, which the controller has yet to record.

1. **Met.** On a LAN table the seat comes from the token alone: `authorize` (`backend/app/api/games.py:105`) looks it up with `room.seat_for_token` and ignores the `viewer` and `as` fields; with no seat it refuses (403), except for the host's own room token, which gets the spectator view. Tests: `test_games_api.py::test_lan_join_and_private_views` (a seat token sent with `"as": "p2"` still acts as its own seat; no token gets 403 on the view), `test_games_api.py::test_local_games_refuse_remote_clients`, `test_socket_auth.py::test_a_guest_without_a_seat_token_closes_4403`, `::test_wrong_token_closes_4403`, `::test_an_unknown_game_closes_exactly_like_a_bad_token`.
2. **Met, nothing new to filter.** Stage 1 added no new way to read a table: the socket's first message only changes where the token is read, and the view builders are the ones that were there. Tests: `test_socket_auth.py::test_auth_message_with_a_seat_token_receives_the_table`, `::test_nothing_is_sent_and_nobody_is_attached_before_auth`; the existing `test_protocol_privacy.py::test_websocket_frames_never_contain_hidden_identities` and `::test_hidden_hands_libraries_and_searches_do_not_leak`; `test_reconnect.py::test_reconnect_restores_same_seat_hand_and_presence`; `test_socket_caps.py::test_a_spectator_takes_only_the_address_cap`. In the full suite.
3. **Met.** The token-in-URL search `git grep -n "[?&]token=\|[?&]seat_token=" -- backend/app frontend/src ':!*.test.*'` finds three lines: `backend/app/api/games.py:1774`, which builds the seat link `/#/game/<id>?seat_token=<token>` (the token is after the `#`, so it never reaches a server) and two comment lines in `frontend/src/services/seatLink.ts:2,4`. The socket takes no token in its address unless `FYODOR_LEGACY_WS_TOKEN=1` (risk 7). The log searches in "Log audit" were re-run at `eac3708` and give the same counts (110 and 92 call sites, two false matches, no `print` match, 53 lines of the multi-line search, all read). Tests: `test_socket_auth.py::test_token_in_the_query_alone_is_refused_by_default`, `::test_no_token_reaches_a_log_line`, `::test_the_seat_link_keeps_the_token_out_of_the_query_string`, `::test_the_legacy_switch_is_on_only_for_the_exact_value_1`; `frontend/src/services/seatLink.test.ts`.
4. **Met, one note.** Tokens: seat tokens `secrets.token_urlsafe(24)` (`multiplayer/hub.py:565,664`), the room's host token (`hub.py:415`), the host secret `secrets.token_urlsafe(32)` (`hostauth.py:22`), room codes `secrets.choice` (`hub.py:424`). Compared with `hmac.compare_digest` at `hub.py:203,221,223,231` and `hostauth.py:32`. Revocable: `test_reconnect.py::test_seat_link_reassigns_a_seat_and_revokes_the_old_token`, `test_socket_caps.py::test_after_a_reclaim_the_old_tokens_sockets_close_4403_and_only_those`, `::test_a_kicked_player_s_sockets_close_4403`, `::test_a_player_who_leaves_the_lobby_has_their_sockets_closed_4403`. The note: `hub.py:304` (`seat.token == key`, from the baseline, not this branch) compares a seat token with the stored winner key with `==`; it picks which lobby seat goes last and decides no access, so it is not an authority check, but it is the one plain comparison of a token that a search finds.
5. **Met, with a different reading of "required secret".** There is no operator-supplied secret to be missing: the host secret is generated at every start, and if its file cannot be written the server does not start (`Services.__init__` creates it, `services.py:92`, with no handler around it; `test_host_auth.py::test_secret_changes_each_start_and_file_is_private`, `::test_an_older_secret_file_is_replaced_not_reused`). No default secret: bandit's only hard-coded-secret finding on a line of this branch is a file name (`hostauth.py:16`).
6. **Met.** The first socket message is strictly bounded (`MAX_AUTH_FIELD` = 256 at `games.py:1892`, type checks; `test_socket_auth.py::test_wrongly_typed_auth_fields_close_4403`, `::test_first_message_that_is_not_a_json_object_closes_4403`, `::test_a_deeply_nested_frame_after_auth_is_answered_as_malformed`, `::test_oversize_first_message_closes_4403`); `FYODOR_TRUSTED_PROXIES` and `FYODOR_EXTRA_HOSTS` are validated at start (`test_client_address.py`); `DeckSource.url` is validated (risk 9); `SessionBody.secret` (`api/host.py:19`, the body of `POST /api/host/session`), which had no maximum length when this walk was first written, is limited to 256 characters in `eac3708`: a longer body is a 422 before any compare and costs the address nothing (`test_host_auth.py::test_an_oversized_secret_is_a_422_that_costs_the_address_nothing`).
7. **Met.** "Rendering audit" and "Log audit" above, with `test_security_headers.py::test_lobby_name_cannot_forge_a_log_line`, `::test_lobby_name_is_clean_before_it_is_logged`, `::test_deck_name_is_clean_before_the_art_keeper_logs_it`. The `innerHTML`-family search has no match; `javascript:` is now matched twice, both in this gate's new deck-link helper (a comment and a test string), neither a sink.
8. **Met.** `git diff 6f1f23c..eac3708 -- backend/app | grep -n "^+.*except"` gives 12 added `except` lines (none is `except Exception`, a bare `except`, or `suppress`): `games.py` `_is_pong` (`json.loads` failing means "not a pong", then the message goes the normal route), the first-message deadline (`TimeoutError` closes the socket 4403), the first-message parse (`ValueError`/`RecursionError` gives no auth, which closes 4403), the first-message `HTTPException` (closes 4403), the heartbeat loop's `TimeoutError` (the idle check), `(WebSocketDisconnect, WebSocketDisconnected)` (the peer went; the connection ends); `config.py` `_proxies` (re-raised as a start-up error naming the variable); `models.py` `is_http_url` (a malformed port means "not an http address": refused); `hostauth.py` (`FileNotFoundError` means "no secret": nobody is the host); `netguard.py` three times (a malformed Origin or Host is refused; "not an IP address" falls through to the name check, which fails closed). Every one refuses or ends the connection; none grants.
9. **Met, nothing new.** `git diff 6f1f23c..eac3708 -- backend/pyproject.toml frontend/package.json frontend/package-lock.json | wc -l` gives 0: no new dependency, and no new file other than `.py`, `.md`, `.ts`, `.tsx` or `.css` (`git diff --diff-filter=A --name-only 6f1f23c..eac3708` filtered for other types is empty), so no binary was added. For the record, the backend dependencies in `pyproject.toml` are version ranges (`fastapi>=0.115`), not hash-pinned; that is how they were before this branch. bandit and pip-audit were installed in the environment only.
10. **Met.** Tests were written first for the last task (red then green, evidence in the task report); for the earlier tasks each commit holds tests and code together, so the order is the task reports' word and could not be re-checked here. Negative cases: wrong seat, see point 1; replaced token, see point 4 and `test_socket_caps.py::test_a_sweep_spares_a_connection_already_on_the_new_token`; foreign Origin: `test_origin_guard.py::test_a_foreign_origin_post_is_refused_and_changes_nothing`, `::test_socket_with_a_foreign_origin_closes_4403`, `::test_origin_allowed` (parametrised, including the sloppy forms), `::test_a_foreign_host_is_refused_even_for_a_get`; forged `X-Forwarded-For`: `test_client_address.py::test_forged_forwarded_for_does_not_pass_the_lan_gate`, `::test_forged_forwarded_for_from_loopback_does_not_pass_either`, `::test_forged_header_does_not_change_the_join_throttle_key`, `test_host_auth.py::test_forged_forwarded_for_gives_nothing`; repeated action id: `test_action_ids.py::test_rest_one_id_twice_draws_once_and_two_ids_draw_twice`, `::test_socket_one_id_twice_draws_once_and_two_ids_draw_twice`, `::test_a_rejected_action_retried_returns_the_same_rejection_and_logs_once`. **Oversized message:** the first message (`test_socket_auth.py::test_oversize_first_message_closes_4403`), the transport limit (`test_launcher.py::test_the_server_is_built_with_a_frame_limit_just_above_the_message_limit`) and, since `eac3708`, the check after authentication (`games.py:2020`: `test_socket_auth.py::test_a_message_over_the_limit_after_auth_gets_the_too_large_error_and_changes_nothing`: a seated player sends a frame over `MAX_WS_MESSAGE`, gets `{"type":"error","message":"Message too large"}`, nothing is applied, the same socket then takes an action). The TestClient does not enforce uvicorn's frame limit, which is why the transport limit is pinned separately. "Timeout racing an action": not applicable to Stage 1, it belongs to Stage 3's clock.
11. **Pending, and not met as written.** The frontend typecheck and tests pass (above). `ruff` and `mypy` are not clean, and neither is a regression of this branch: `ruff` reports 10 errors, every one of them also in master's 11 by rule and file; `mypy` reports 303 errors in 15 files, the same messages as master, and the only two files with errors that the branch touched have errors on lines that predate it (`git blame`). The full `pytest` run is the controller's, its result goes on the marked line in "Gate results", and the intermittent `tests/test_interim_views.py` failure (above, risk 16) can fail it. `bandit`, `pip-audit` and `npm audit` findings are read and answered above, with five dependency upgrades left open.
12. **Pending.** The independent review (the `security-review` skill and a fresh reviewer) is done by the controller after this commit.
13. **Met, with two notes.** Stage 1 added no second system: it replaced the loopback test with one function, `is_host_request` (`api/deps.py:86`, kept under the old names `is_local_request` and `require_local`), uses one `client_address` for the limits and the logs, and one `AttemptLimiter` class (three instances in `services.py:94-96`) and one `ConnectionCaps` (two instances); a search for `request.client` finds it read only in `deps.py`. Notes: (a) there are two host notions, both older than this branch's check and both compared in constant time: the browser's host cookie decides what only the host computer may do to the server (backups, cards, assets, creating tables), and `Room.is_host` (`hub.py:227`, the room's host token or the host's seat) decides what the host may do inside a table. They answer different questions and were not merged. (b) `_RateLimiter` in `games.py:1873` is the per-connection message-rate budget from before this branch, not a guess limiter.

## Two-device manual check

**NOT DONE — owner's to do.** This needs a host computer, a phone on the same network and a second browser, which the author of this section did not have. Run it before merging; each
line is an action and what you should see.

- [ ] Start Fyodor from its launcher on the host computer. The window the launcher opens shows the Host tools (under the menu in a game) and the *Host a LAN night* page. The address bar does not keep `#host=...` after the page loads.
- [ ] On a phone on the same Wi-Fi, open the host's address (or press **Join** under *Play*), join with the room code and a name, take a seat. It joins without being refused.
- [ ] On another device, open the table by the computer's name instead of its IP address: `http://NAME:8000` and the name the router gives it (`http://NAME.lan:8000`, `.home` or `.localdomain`; `ping -a HOST-IP` on Windows or `nslookup HOST-IP` shows it). Both open the Play page. A name the computer does not have (for example an alias you made up in the router) shows *This address is not one Fyodor answers to. Use http://<IP>:<port>, or add the name to FYODOR_EXTRA_HOSTS.*
- [ ] On the phone, play a land. It appears on the host's screen at once.
- [ ] Lock the phone for a minute (or switch it to another app for a minute), wake it. The table comes back on the same seat with the same hand, with no "Too many connections" and no refusal.
- [ ] On the host computer, open a second browser (or a new private window) and type `http://127.0.0.1:8000` by hand. It can open the Play page and join as a player, but has no Host tools, and where they would be it says to open Fyodor from its launcher (*Open Fyodor from its launcher on the host computer to use host tools.*).
- [ ] In the host's window, open a game's Host tools, **Reclaim / assign seat** for the phone's player, and open the link it gives in another browser. That browser now holds the seat with the same hand; the phone's old tab shows *Your seat is no longer valid here. Join again.*
- [ ] In the host's window open **Settings → Restart**. A new host window opens and still has Host tools; the old window is now a guest (no Host tools).
- [ ] A friend's computer on the same private network (for example Tailscale) opens `http://HOST-PRIVATE-ADDRESS:8000`, joins by the room code and can play a land. (`docs/LAN_PLAY.md` says this should work and that this project has not tested it; this line is that test.)
- [ ] From one device that is not the host, enter a wrong room password five times. The sixth try says *Too many attempts. Try again in a few minutes.* Then, from a different device, join the same table with the right password: it joins.

## Remaining risks

1. Behind any proxy or tunnel without `FYODOR_TRUSTED_PROXIES`, every remote client shares one address, so the join limit (5 failures per 15 minutes) and the connection cap (24 per address) are shared by all of them; a stranger's wrong guesses can block remote joins for 15 minutes. Stage 2's tunnel port fixes this by reading the provider's client-address header. Until then, do not front Stage 1 with a tunnel without setting trusted proxies.
2. The host secret is in the launcher-opened window's address (`#host=...`) until the page removes it at start-up; the browser's own `browser.log` (Chromium `--enable-logging`, in the host's data folder) records console lines with the page address of the moment, so an error logged before the page clears the address could capture it. The secret is new on every start and the file is on the host's own machine.
3. A seat link (`/#/game/<id>?seat_token=...`) keeps the token after the `#`, so it is never sent to a server, but it sits in the recipient's browser history until the page clears it.
4. A request with neither an `Origin` nor a `Sec-Fetch-Site` header is allowed to change state (needed for the Fyodor-to-Fyodor LAN handoff and scripts); browsers older than about 2019 send neither on some cross-site form posts. Authority still needs a seat token or the host cookie.
5. Migration 14 drops remembered action ids written before the upgrade; a retry that spans the upgrade restart could apply twice.
6. An upgraded room-password hash is written to disk only for started tables (lobby rooms are not saved at all).
7. The legacy socket switch `FYODOR_LEGACY_WS_TOKEN=1` puts the seat token back in the URL; it is off by default and should stay off.
8. `mypy` in this environment is version 2.4.1 and reports 303 errors as of `eac3708` (`.venv/Scripts/python -m mypy app tools 2>&1 | tail -1` gives `Found 303 errors in 15 files`); a `master` checkout gives the same 303 in 15 files with the same messages. Two of the 15 files were touched by this branch (`app/api/games.py`, `app/multiplayer/hub.py`; 4 errors), and `git blame` puts every erroring line before the branch. `ruff check .` reports 10 errors, each also in master's 11 (rule and file). The gate used was "no new errors", not a clean run.

9. `DeckSource.url` was an unvalidated string shown as a link in the deck editor. Closed in `1acd3fc` and `eac3708`. The model (`backend/app/decks/models.py`, `is_http_url`) accepts only empty or an absolute http or https address with a host and no whitespace or control character; the editor (`isHttpUrl` in `frontend/src/pages/deckBits.ts`, used at `DeckEditor.tsx:369`) links only such an address and otherwise shows the name as plain text. Three paths build or read a `DeckSource`, and the deck-save API (`DeckIn`) has no source field, so a client cannot supply one by saving:
   - an Archidekt URL import (`service.py:209`): the id comes from `extract_deck_id`, which accepts 1 to 12 digits, and the url is built from it;
   - an uploaded Archidekt JSON (`service.py:217-218`): the id comes from the file, so it is used only if `archidekt.valid_deck_id` says it is 1 to 12 ASCII digits; otherwise the deck imports normally with no source id and no url. (The first version of the fix missed this path: a file with the id `"1 2"` made the new check raise, an unhandled error; found in review, fixed in `eac3708` with tests, including an upload through the HTTP route.)
   - a stored row read back (`repository.py:138`, `DeckSource.from_stored`): an old save or a restored backup may hold a url that would now be refused; the url is dropped (set to none) and the rest of the source kept, so the deck still opens.
   `set_source` (`repository.py:66`) only writes a source that already passed one of these. LAN deck sharing and "bring my decks" send names and card lists only (`backend/app/decks/sharing.py`, `BroughtDeckIn`), so a source link never travels between computers; the statement made here earlier that decks could arrive that way with a url was wrong.
10. The art-keeper logs a stored deck's name (`backend/app/cards/art_keeper.py:149-158`). Names are cleaned when a deck is saved or imported, so a deck stored before that cleaning existed is the only uncovered case.

11. Five dependency upgrades are open and not done by this task (they are the gate's findings, see "Security tools"): `pip` 25.0.1 in the development environment (six advisories, fixed in 26.2 or later), and in `frontend/` `vite` 8.3.1, `source-map-js` 1.2.1, `vitest` 5.0.2 and `@vitest/mocker` 5.0.2 (`npm audit fix`). All are development tools; `npm audit --omit=dev` finds nothing.
12. (Closed in `eac3708`.) `POST /api/host/session` took `secret: str` with no maximum length; it is now limited to 256 characters, a longer body is a 422 and is not counted against the address's five failures.
13. (Closed in `eac3708`.) The branch of the game socket that answers "Message too large" after authentication had no test; `test_socket_auth.py::test_a_message_over_the_limit_after_auth_gets_the_too_large_error_and_changes_nothing` covers it.
14. `hub.py:304` compares a seat token with the stored last-winner key using `==` (code from before this branch). It decides which lobby seat goes last, not who may do anything.
15. The bandit findings are accepted individually in "Security tools" (sha1 used as a fingerprint, SQL assembled from constants, a deep copy by `pickle`); `hashlib.sha1(..., usedforsecurity=False)` would make the first group explicit and is left for a rules-engine change.

16. `tests/test_interim_views.py::test_a_long_chain_streams_interim_views_per_viewer_and_stays_one_action` fails intermittently on this branch, cause not known (3 failures in 34 runs on this branch, 0 in 8 on a `master` checkout; details in "Gate results"). It may be a regression from this branch's changes to `hub.py` and the socket path. Under investigation.
17. Follow-up, not done in this task: the comment `# noqa: S104 - explicit opt-in for LAN play` at `backend/app/launcher.py:268` is stale; the launcher binds all interfaces by default (`launcher.py:259-268`, `args.lan = not args.local`) and the `--lan` flag has no effect.

## Before merging

1. **Unresolved:** an intermittent failure of `tests/test_interim_views.py::test_a_long_chain_streams_interim_views_per_viewer_and_stays_one_action` on this branch (3 of at least 34 runs; the totals are "at least", see "Gate results"), 0 of 8 on a master checkout. `hub.py` and the socket path changed on this branch, so it may be a regression. Under investigation; do not merge until it is explained.

INTERIM VIEWS TEST: investigation result pending

2. **Full backend test suite:** the controller's run; its result goes on the `FULL SUITE:` line in "Gate results", which still reads pending. The test in item 1 can fail that run.
3. **Independent review** (`security-review` skill and a fresh reviewer): pending.
4. **Two-device manual check** (checklist above, including the private-network line): NOT DONE — owner's to do.
5. Open items: the five dependency upgrades (risk 11), and the stale `S104` comment (risk 17). The `ruff` and `mypy` errors listed above are the same as master's.

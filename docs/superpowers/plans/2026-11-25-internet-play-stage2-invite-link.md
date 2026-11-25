# Internet Play Stage 2 (Invite Link) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The host presses **Invite over the internet** on a LAN table and sends friends one HTTPS link; the link reaches only that table, through a Cloudflare quick tunnel on a second, loopback-only port, and nothing changes for a LAN night.

**Architecture:** One uvicorn server listens on two sockets: the LAN port as today and a loopback "tunnel port" that only `cloudflared` connects to. Every request is marked by the local port it arrived on (`scope["server"]`), and the existing single functions (`is_host_request`, `client_address`, `host_ok`, `origin_ok`, `is_https`, the `net_guard` middleware) answer differently for the tunnel port; no route grows its own check. A `TunnelManager` downloads a pinned, hash-checked `cloudflared` on first use, runs it as a child process, and reads the public hostname from its metrics endpoint. Rooms gain `shared` and a 10-character `invite_code`; the tunnel port serves only shared rooms and only the routes a remote player needs.

**Tech Stack:** Python 3.12, FastAPI/Starlette, uvicorn 0.54, httpx (already a dependency), pytest (`backend/`); TypeScript, React, Vite, Vitest (`frontend/`). No new runtime Python or npm dependency. One downloaded binary: `cloudflared`, pinned by version and SHA-256.

**Spec:** `docs/superpowers/specs/2026-11-21-internet-play-design.md` (Stage 2, Goals, Anti-goals, Constraints, Review gate). Also binding: the "Stage 2 must" list and remaining risks of `docs/superpowers/specs/2026-11-21-stage1-audit.md`, and two Stage 1 review findings (NB1 in `.superpowers/sdd/2026-11-21-internet-play-stage1-hardening/final-rereview-report.md`, SR1/F1 in `.../security-review-report.md`). Build on branch `internet-play-stage1` (head `9eb1e71` when this plan was written) or on `master` once Stage 1 is merged; work on a new branch `internet-play-stage2`.

## Provider findings (researched 2026-11-25)

| Fact | Finding | Source |
|---|---|---|
| Account | "You do not need a Cloudflare account or domain." Visitors need none either. | https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/do-more-with-tunnels/trycloudflare/ |
| Intended use | **"Quick Tunnels are for testing and development."** Production should use a named tunnel. try.cloudflare.com: "Made for development loops." | same page; https://try.cloudflare.com |
| Uptime | "Quick Tunnels have no uptime guarantee." "Ends with the process." | same pages |
| Limits | "Each Quick Tunnel supports up to 200 in-flight requests"; more get HTTP 429. No Server-Sent Events (Fyodor uses none). | trycloudflare page |
| Hostname | Random `*.trycloudflare.com`, new every start. cloudflared prints it, and its metrics server answers `GET /quicktunnel` with `{"hostname":"…"}` (`metrics/metrics.go` on cloudflared `master`, read 2026-11-25). Default metrics address `localhost:20241`–`20245`, else random; set with `--metrics`. | https://raw.githubusercontent.com/cloudflare/cloudflared/master/metrics/metrics.go ; https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/monitor-tunnels/metrics/ |
| Config conflict | Quick tunnels are not supported when a `config.yaml` is present in the `.cloudflared` directory. | trycloudflare page (via search summary) |
| WebSockets | "Cloudflare Tunnel has full support for Websockets." **Not stated for quick tunnels specifically: unverified.** | https://developers.cloudflare.com/cloudflare-one/faq/tunnel/ |
| Client IP | "`CF-Connecting-IP` provides the client IP address connecting to Cloudflare to the origin web server." `X-Forwarded-For` gets the client appended; `X-Forwarded-Proto` is overwritten. **Whether a client-supplied `CF-Connecting-IP` is always overwritten is not stated: unverified.** | https://developers.cloudflare.com/fundamentals/reference/http-headers/ |
| Host header to origin | `originRequest.httpHostHeader` defaults to empty; what cloudflared sends then is **not stated: unverified.** | https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/configure-tunnels/cloudflared-parameters/origin-parameters/ |
| Terms | The website terms do not mention quick tunnels; the try.cloudflare.com footer links "Terms of Use" (not resolved to a product-specific text). Cloudflare "reserve[s] the right to modify or discontinue … at any time." No quick-tunnel-specific prohibition found. | https://www.cloudflare.com/website-terms/ |
| Recent change | 2026-10-02: `--allowed-mail` restricts a quick tunnel to verified e-mail addresses (one-time PIN). Not used by this plan (friends would need e-mail PINs; the table password does that job). | https://developers.cloudflare.com/tunnel/changelog/ |
| Release | Latest release `2026.11.2`, published 23 Nov 2026 (two days before this plan). SHA-256 checksums are published as plain text in the release notes under "SHA256 Checksums:" (no separate checksum file or signature was seen). Assets: `cloudflared-windows-amd64.exe`, `cloudflared-darwin-amd64.tgz`, `cloudflared-darwin-arm64.tgz`, `cloudflared-linux-amd64`, `cloudflared-linux-arm64`. | https://github.com/cloudflare/cloudflared/releases/latest |
| Hashes | Read 2026-11-25 through a summarising fetch, **not yet confirmed** (Task 12 confirms each against the release notes and the downloaded file): windows-amd64.exe `555b46c85582461d189cac30d14ad05480d612613801be9f110b8ce08c5b2113`, darwin-amd64.tgz `870dc2094f98befdd993c455234562be4eee51f8fca6e2e356df4579fa7e6766`, darwin-arm64.tgz `8654fbdc9057f3e13e95f7892f417f8643113bee1b91ee2388fd0acb05210d55`, linux-amd64 `56f13335143ec0e22772963290683a84a04114a35ec64cbc794a4d39ff9bb8cf`, linux-arm64 `04a7b7f08bce85d56b26ffe1fdbfbb21a074495a363d16f0783c40e25b5c5281`. | release notes |
| Self-update | cloudflared updates itself unless `--no-autoupdate`; that would replace the pinned binary. | cloudflared CLI help (confirm in Task 1) |

**Verdict: fits, provisionally.** No account, no open port, HTTPS, the client address in a header, and the hostname is machine-readable. Cloudflare's own words are "for testing and development" with "no uptime guarantee": that is positioning, not a prohibition, and the spec's "Risks that remain" already accepts that the provider can limit or drop the service. Three facts are unverified and Task 1 settles them with a stop condition (WebSockets through a quick tunnel, the Host header, overwriting of a forged `CF-Connecting-IP`). The owner reads the "testing and development" line in Task 1 before any code is written. Tailscale Funnel is not planned here; if Task 1 stops, the choice returns to the owner (spec).

## Global Constraints

- A LAN-only night needs no internet, account or certificate, and no new step; with nobody pressing **Invite over the internet**, nothing is downloaded and no process is started.
- One host check (`is_host_request`), one token check (`authorize` / `Room.seat_for_token`), one client-address function (`client_address`), one guess limiter class (`AttemptLimiter`), one Host/Origin guard (`net_guard` + `host_ok`/`origin_ok`). Extend them; no parallel path (spec anti-goal, gate 13).
- Tokens and secrets come from `secrets`, are compared with `hmac.compare_digest`, never appear in a URL query string or a log line. Invite links carry the invite code after `#`, never a seat or host token.
- No new `except Exception`, bare `except` or silent fallback; every refusal fails closed.
- New persisted fields have defaults so old saves and room metadata load (`shared=False`, `invite_code=None`).
- No new runtime dependency (spec). `cloudflared` is downloaded, never bundled; pinned version, SHA-256 pinned in the repo, verified before every launch; `allow_network=False` disables the feature.
- Tunnel port: bound to `127.0.0.1` only, port chosen by the OS; serves shared rooms only; never grants host powers (cookie or room host token); never passes the LAN gate; client address from `CF-Connecting-IP` only, IPv6 grouped per /64.
- Invite code: 10 characters from `CODE_ALPHABET` (`ABCDEFGHJKLMNPQRSTUVWXYZ23456789`). A shared table must have a password.
- LAN discovery never advertises the invite link or invite code.
- `--local` (LAN port on loopback only) still allows **Invite over the internet**: the host pressed it explicitly, and the tunnel port is loopback either way. The launcher's `--local` help text becomes "only this computer can connect (an invite link you start still works)".
- Windows is the main host platform; the PyInstaller bundle (`--collect-submodules app`) must pick up the new package with no build change; the app runs offline.
- Before every commit, from `backend/`: `.venv/Scripts/ruff check . && .venv/Scripts/mypy app tools` (no new errors against the branch base: Stage 1 left 10 ruff and 303 mypy errors). The task's test files pass before its last commit. Full suite `.venv/Scripts/python -m pytest -n 8 -q` at Tasks 8, 11 and 16. Frontend changes: `npm run typecheck && npm test` in `frontend/`.
- Frontend work follows `.claude/skills/fyodor-ui-design/SKILL.md` (game client look, icon + text never colour alone, keyboard reachable, no new dependency).

## Review Focus

1. A remote player whose phone moves from Wi-Fi to mobile data mid-game arrives with a new `CF-Connecting-IP` and the same seat token: they reconnect to the same seat with no 429/4429 and no new join. (Task 8)
2. Four remote tabs opening a 100-card table load card images in a burst against Cloudflare's 200-in-flight cap: images that get a 429 are retried by the page, not shown broken forever. (Task 1 measures; Task 15 adds the retry only if Task 1 saw 429s)
3. The host presses **Stop sharing** while a remote player's action is in flight: the action either applies once or not at all, the remote socket closes 4403 with "The host stopped sharing this table.", and LAN players are untouched. (Task 14)
4. `cloudflared` dies while a table is shared (network drop, killed by antivirus): the top bar stops saying "shared", and the host's invite panel says the link went down and offers to invite again, instead of showing a dead link. (Tasks 13, 14)
5. A second browser on the host computer that opens the tunnel port directly (`http://127.0.0.1:<tunnel port>`) gets a stranger's view (404 for any Host but the invite hostname), never the host's. (Task 9)

---

## File map

| File | Responsibility |
|---|---|
| `backend/app/tunnel/__init__.py` (new) | Package marker; re-exports `TunnelManager`, `TunnelUnavailable` |
| `backend/app/tunnel/pins.py` (new) | Pinned cloudflared version, assets and SHA-256 |
| `backend/app/tunnel/binary.py` (new) | Pick the asset, download, verify, store |
| `backend/app/tunnel/process.py` (new) | Launch cloudflared, read the hostname, kill with Fyodor |
| `backend/app/tunnel/manager.py` (new) | Tunnel state: port, hostname, start/stop, link-down callback |
| `backend/app/api/share.py` (new) | `GET/POST/DELETE /api/games/{id}/share` |
| `backend/app/api/deps.py` | `is_tunnel_request`, tunnel branches of `client_address`, `is_https`, `host_ok`, `origin_ok`, `is_host_request`; `room_host` |
| `backend/app/netguard.py` | `tunnel_route`, `cf_client_key`, `AttemptLimiter.undo_last` |
| `backend/app/main.py` | `net_guard` tunnel branch, `BodyLimit` grants, per-request CSP |
| `backend/app/launcher.py` | Two sockets, `proxy_headers=False` |
| `backend/app/multiplayer/hub.py` | `shared`, `invite_code`, `by_invite_code`, spectator cap, closing a room's tunnel sockets |
| `backend/app/api/games.py` | async join off the threadpool, tunnel join, SR1, `room_host` call sites |
| `backend/app/config.py` | dev-only CORS origins; `legacy_ws_token` removed |
| `backend/app/hostauth.py`, `backend/app/api/host.py` | `__Host-` cookie name |
| `frontend/src/game/InternetInvite.tsx` (new) | The invite panel (lobby and host tools) |
| `frontend/src/services/share.ts` (new) | Share API calls and link building |
| `frontend/src/pages/LobbyScreen.tsx`, `frontend/src/game/HostTools.tsx`, `frontend/src/game/TopBar.tsx`, `frontend/src/pages/lanBits.ts`, `frontend/src/pages/PlayPage.tsx` | Mount the panel, shared indicator, tunnel join asks for the password |
| `docs/LAN_PLAY.md`, `docs/superpowers/specs/2026-11-25-stage2-audit.md` (new) | Docs and gate record |

---

### Task 1: Verify the provider before building (stop condition)

**Files:** Create `docs/superpowers/specs/2026-11-25-stage2-audit.md` (section "Provider verification"). No code in the repository changes. Throwaway scripts live in the scratchpad.

**Interfaces:**
- Produces for later tasks: the confirmed Host header behaviour (Task 9), the confirmed `--config` choice (Task 13), whether 429s appeared under an image burst (Task 15), the owner's acknowledgement line.

- [ ] **Step 1: Owner acknowledgement.** Put the "Intended use" and "Uptime" rows of Provider findings in front of the owner, quoting "Quick Tunnels are for testing and development." Record their answer in the audit file. **Stop** if they decline: the spec returns the provider choice to them (Tailscale Funnel); do not start Task 2.
- [ ] **Step 2: Fetch the try.cloudflare.com footer's Terms of Use link** and record any clause about quick tunnels, automated use or acceptable use, with URL. If it cannot be resolved, write "not resolved" and the URL tried.
- [ ] **Step 3: Run a real quick tunnel.** Download `cloudflared-windows-amd64.exe` 2026.11.2 into a new empty scratch folder, check its SHA-256 against the release notes, run a dev backend (`FYODOR_DEV_TOOLS=1 uvicorn --factory app.main:create_app --port 8000`) and `cloudflared tunnel --no-autoupdate --metrics 127.0.0.1:20299 --url http://127.0.0.1:8000`. Record, for 15 minutes of play from a phone on mobile data (not on the LAN):
  - `curl http://127.0.0.1:20299/quicktunnel` output shape;
  - the request headers the origin receives (log them in a scratch ASGI wrapper, not in Fyodor): `Host`, `Origin`, `CF-Connecting-IP`, `X-Forwarded-For`, `X-Forwarded-Proto`;
  - a browser request that sends its own `CF-Connecting-IP: 1.2.3.4` and `X-Forwarded-For: 1.2.3.4` (use `curl -H`): what arrives;
  - WebSocket upgrade to `/ws/games/<id>` with the `auth` first message, a played land, a 10-minute idle with the 25 s ping;
  - four tabs opening one 100-card table at once: count 429 responses for `/api/images/…`;
  - whether `--config <empty file>` with a quick tunnel starts, and whether a `config.yaml` in `%USERPROFILE%\.cloudflared` breaks the default start;
  - `cloudflared --help` lines for `--no-autoupdate` and `--metrics`.
- [ ] **Step 4: Stop conditions.** Stop and return to the owner if: the WebSocket fails or drops before the 90 s idle close; the origin receives the forged `CF-Connecting-IP` value; the hostname is not available from `/quicktunnel` or stdout. If the origin's `Host` is not the public hostname, do not stop: record it, and Task 9's Host rule changes from "equals the invite hostname" to "equals `127.0.0.1:<tunnel port>`" (Origin is still compared to `https://<invite hostname>`).
- [ ] **Step 5: Commit** the audit file: `Stage 2: provider verification for Cloudflare quick tunnels`.

### Task 2: The host's own seat cannot be removed or taken (SR1)

Skip if already fixed on the base branch: check `git grep -n "host_seat" -- backend/app/api/games.py` shows a `remove_player` refusal in `_check_host_only`, and `claim_seat` in `backend/app/multiplayer/hub.py` refuses a player who has `left`. Say in the task report which half was already there.

**Files:** Modify `backend/app/api/games.py` (`_check_host_only`, line ~146), `backend/app/multiplayer/hub.py` (`claim_seat`, line ~665); Test `backend/tests/test_host_seat_guard.py`

**Interfaces:**
- Produces: `remove_player` with `player == room.host_seat` on a LAN room is a 409 `{"detail": "The host's own seat can't be removed"}` before the action runs. `GameHub.claim_seat` raises `PermissionError("That player has left the table")` for a seat whose game player has `left`, whether chosen or picked as the first free seat (left seats are not "free").

- [ ] **Step 1: Failing tests:** `test_host_cannot_remove_their_own_seat` (LAN table, host seated p1, host token posts `remove_player p1` → 409; `room.seats["p1"].token` unchanged); `test_a_left_seat_cannot_be_claimed` (remove p2 with the host token, then a guest `POST /api/join {"seat":"p2"}` → 409 and no token issued); `test_join_without_a_seat_skips_left_seats` (a 2-seat table with p2 left and p1 taken → 409 "The table is full — join as a spectator"); `test_the_exploit_from_the_review_fails` (the three steps of F1 end with the stranger not being host: `room.is_host(stranger_token)` is False).
- [ ] **Step 2: Run** `.venv/Scripts/python -m pytest tests/test_host_seat_guard.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement** the two refusals.
- [ ] **Step 4: Run** the new file plus `tests/test_games_api.py tests/test_reconnect.py`. Expected: PASS.
- [ ] **Step 5: Commit** `The host's own seat can't be removed, and a seat whose player left can't be claimed`.

### Task 3: One client-address mechanism: uvicorn's proxy headers off

uvicorn 0.54 enables `ProxyHeadersMiddleware` by default and trusts `127.0.0.1,::1` (`uvicorn/config.py:225-228,362-363,543-544`). The launcher does not turn it off, so on the real server a loopback peer's `X-Forwarded-For`/`X-Forwarded-Proto` rewrite `scope["client"]`/`scope["scheme"]` before `client_address` and `is_https` run. Stage 1's forged-header tests ran under TestClient, which skips uvicorn, so this is a Stage 1 gap; behind cloudflared every peer is loopback. Skip only if `server_options` already returns `proxy_headers=False`.

**Files:** Modify `backend/app/launcher.py` (`server_options`, line ~327); Test `backend/tests/test_launcher.py`, `backend/tests/test_client_address.py`

**Interfaces:**
- Produces: `server_options(settings)["proxy_headers"] is False`.

- [ ] **Step 1: Failing tests:** `test_launcher.py::test_uvicorn_does_not_rewrite_the_client_from_headers` asserts `server_options(settings)["proxy_headers"] is False`; and `test_a_real_server_ignores_forwarded_for_from_loopback`: start `uvicorn.Server(uvicorn.Config(app, **server_options(settings)))` on port 0 in a thread (the existing launcher tests show how), add a test-only route to that test's own app, `app.add_api_route("/_peer", lambda r: {"peer": client_address(r)})`, request it over real HTTP with `X-Forwarded-For: 203.0.113.9`, assert `peer == "127.0.0.1"`. Add the Stage 2 must #10 row to `test_client_address.py`'s parametrised table: `(("127.0.0.1",), "127.0.0.1", "203.0.113.9:4711", "127.0.0.1")` (an entry with a port is unparseable and falls back to the proxy: fail-safe).
- [ ] **Step 2: Run, expect FAIL** (the first two; the row passes already and is pinned).
- [ ] **Step 3: Implement:** add `"proxy_headers": False` to `server_options`.
- [ ] **Step 4: Run, expect PASS. Commit** `uvicorn no longer rewrites the client from forwarded headers: Fyodor's client_address is the only one`.

### Task 4: Remove the legacy socket token; development origins only in development

**Files:** Modify `backend/app/config.py` (remove `legacy_ws_token`, change `cors_origins` default and `load_settings`), `backend/app/api/games.py` (delete `_legacy_credentials` and its call at line ~1960), `scripts/dev.sh`, `frontend/vite.config.ts` (comment only), `docs/LAN_PLAY.md` (the env-variable list); Test `backend/tests/test_socket_auth.py`, `backend/tests/test_origin_guard.py`

**Interfaces:**
- Produces: `Settings.cors_origins: tuple[str, ...] = ()`. `load_settings`: `FYODOR_CORS_ORIGINS` when set; else `("http://localhost:5173", "http://127.0.0.1:5173")` when `FYODOR_DEV_TOOLS=1`; else `()`. `Settings.legacy_ws_token` no longer exists; a `?token=` on the socket is ignored and the socket waits for the auth message as for any client.
- `scripts/dev.sh` exports `FYODOR_DEV_TOOLS=1` and `FYODOR_TRUSTED_PROXIES=127.0.0.1` for the backend it starts.

- [ ] **Step 1: Failing tests:** replace the legacy tests in `test_socket_auth.py` with `test_a_token_in_the_query_is_never_credentials` (connect `/ws/games/<id>?token=<valid seat token>`, send nothing, closed 4403 at the deadline; with `FYODOR_LEGACY_WS_TOKEN=1` in the env too). In `test_origin_guard.py`: `test_dev_origins_are_refused_by_default` (`Origin: http://localhost:5173` POST → 403 with default settings), `test_dev_origins_with_dev_tools` (200 path with `FYODOR_DEV_TOOLS=1`), `test_cors_origins_variable_wins`.
- [ ] **Step 2: Run, expect FAIL. Step 3: Implement. Step 4: Run** the two files and `tests/test_security_headers.py`, expect PASS.
- [ ] **Step 5: Commit** `Legacy socket token removed; the Vite dev origins are trusted only in development`.

### Task 5: `__Host-` host cookie over https; `connect-src` without bare schemes

**Files:** Modify `backend/app/hostauth.py`, `backend/app/api/host.py`, `backend/app/api/deps.py` (`is_host_request`), `backend/app/main.py` (`CSP`, `security_headers`); Test `backend/tests/test_host_auth.py`, `backend/tests/test_security_headers.py`

**Interfaces:**
- Produces: `HOST_COOKIE = "fyodor_host"`, `HOST_COOKIE_SECURE = "__Host-fyodor_host"`. `POST /api/host/session` sets `__Host-fyodor_host` (with `Secure; Path=/`, no `Domain`) when `is_https(request)`, else `fyodor_host`. `is_host_request` reads `__Host-fyodor_host` first, then `fyodor_host`.
- `main.csp(host_header: str | None) -> str`: the Stage 1 policy with `connect-src` narrowed to this host: `connect-src 'self' ws://HOST wss://HOST` where `HOST` is the request's `Host` header when `host_ok` accepted it (older Safari and in-app WebViews do not all match `ws:`/`wss:` with `'self'`), and plain `connect-src 'self'` when the Host was refused (the 400 path) or absent. `security_headers` passes `request.headers.get("host")` only when `host_ok(request)`; the bare `ws:`/`wss:` schemes are gone (Stage 2 must #7). `CSP = csp(None)` stays exported for the existing tests.

- [ ] **Step 1: Failing tests:** `test_https_session_sets_the_host_prefixed_cookie` (a TestClient on `https://testserver`: the `set-cookie` starts `__Host-fyodor_host=` and contains `secure` and `path=/` and no `domain=`); `test_either_cookie_name_is_the_host` (set each by hand → `GET /api/host/session` says `host: true`); `test_plain_http_keeps_the_plain_name`. In `test_security_headers.py` change `test_csp_pins` to assert no source is a bare `ws:`/`wss:`, and add `test_connect_src_names_this_host` (`Host: 192.168.1.20:8000` → `connect-src 'self' ws://192.168.1.20:8000 wss://192.168.1.20:8000;`) and `test_refused_host_gets_self_only` (`Host: evil.example` → 400 carrying `connect-src 'self';`, the bad name nowhere in the header).
- [ ] **Step 2: Run, expect FAIL. Step 3: Implement. Step 4: Run, expect PASS. Run the frontend socket tests** (`npx vitest run src/services/gameSocket.test.ts`) to confirm nothing assumed the old policy.
- [ ] **Step 5: Commit** `Host cookie takes the __Host- prefix over https; connect-src names this host instead of any ws:/wss:`.

### Task 6: Password checks off the shared threadpool, counted before hashing

**Files:** Modify `backend/app/netguard.py` (`AttemptLimiter`), `backend/app/services.py`, `backend/app/api/games.py` (`join_game`, line ~561), `backend/app/multiplayer/hub.py` (comment at line ~56); Test `backend/tests/test_join_limits.py`

**Interfaces:**
- Produces: `AttemptLimiter.undo_last(key: str) -> None` removes the newest failure of `key` (no-op without one). `Services.hash_pool: concurrent.futures.ThreadPoolExecutor(max_workers=4, thread_name_prefix="pbkdf2")`, shut down in `Services.close()`.
- `join_game` becomes `async def`. Order: blocked check → `by_address.fail(ip)` (the reservation) → room lookup and `check_password` (or `spend_password_check`) run with `await asyncio.get_running_loop().run_in_executor(services.hash_pool, …)` → on success `by_address.undo_last(ip)`; on failure the reservation stands and the per-room limiter is charged as today. The rename runs as `async with room.lock: rename()` (no `anyio.from_thread`). Responses and status codes are unchanged. What runs where: the hash (`check_password`, `spend_password_check`) on `hash_pool`; `claim_seat` (whose `persist` is one small SQLite write under `app_db_lock`, as the async lobby routes already do on the loop) and the rename on the loop under `room.lock`; `services.handoffs.attach` (card lookups) via `run_in_threadpool`.

- [ ] **Step 1: Failing tests:** `test_undo_last_removes_only_the_newest_failure`; `test_concurrent_wrong_joins_stop_at_five` (40 wrong-password joins from one address started together with `asyncio.gather` on an `httpx.AsyncClient(transport=ASGITransport(app))`: exactly 5 answer 403 and 35 answer 429; monkeypatch `PASSWORD_ROUNDS` small for speed only if the test is slow); `test_other_routes_answer_while_joins_hash` (patch `hub._pbkdf2` to sleep 0.5 s; during 40 joins `GET /api/health` answers within 0.3 s); `test_a_right_join_costs_the_address_nothing` (after 4 wrong, one right, one more wrong is still a 403, not a 429). Keep every existing test in the file green.
- [ ] **Step 2: Run, expect FAIL. Step 3: Implement. Step 4: Run** `tests/test_join_limits.py tests/test_room_password.py tests/test_games_api.py tests/test_lobby.py`, expect PASS.
- [ ] **Step 5: Commit** `Joins count the guess before hashing and hash on a pool of their own`.

### Task 7: At most 32 spectator tokens per room

**Files:** Modify `backend/app/multiplayer/hub.py` (`Room.spectator_tokens`, `claim_seat`, `meta`, `restore`), `backend/app/api/games.py` (`join_game`); Test `backend/tests/test_spectator_cap.py`

**Interfaces:**
- Produces: `MAX_SPECTATORS = 32`. `Room.spectator_tokens: list[str]` (oldest first; `seat_for_token` scans it as before). `GameHub.claim_seat(...)` returns `(viewer, token)` as today and, when a spectator join pushes the count over 32, drops the oldest token, removes its `room.night.queued` entry, and records it in `room.dropped_spectators: list[str]` (memory only). `GameHub.close_dropped_spectators(room) -> Awaitable[None]` closes sockets whose `conn.token` is a dropped token with 4403 "Too many spectators: the earliest one was let go." and clears the list; `join_game` awaits it after `claim_seat`. `meta()` writes the list in order; `restore()` loads a list or an old sorted list alike and keeps the newest 32. `claim_seat` is the only place a spectator token is added today (`git grep -n "spectator_tokens" -- backend/app`: `hub.py` lines 160, 226, 459, 523, 669); re-run the grep and route any new addition through the capped path.

- [ ] **Step 1: Failing tests:** 33 spectator joins leave 32 tokens and the first token gets 403 on `GET /view`; the first spectator's open socket closes 4403 with that reason; metadata with 40 tokens loads 32 (the last 40−32 kept); a save/load round trip keeps the order; seats are untouched by the cap.
- [ ] **Step 2: Run, expect FAIL. Step 3: Implement. Step 4: Run** the new file with `tests/test_reconnect.py tests/test_spectate*.py`, expect PASS.
- [ ] **Step 5: Commit** `Spectator tokens are capped at 32 per room, the earliest let go`.

### Task 8: The tunnel port: a second socket, and who a tunnel request is

**Files:** Create `backend/app/tunnel/__init__.py`, `backend/app/tunnel/manager.py` (state only in this task); Modify `backend/app/launcher.py` (`serve`), `backend/app/services.py`, `backend/app/api/deps.py`, `backend/app/netguard.py`, every `room.is_host(` call site in `backend/app/api/` (15, listed by `git grep -n "\.is_host(" -- backend/app/api`), `backend/app/api/games.py` (`game_socket`), `backend/app/multiplayer/hub.py` (`Connection`); Test `backend/tests/test_tunnel_identity.py`, `backend/tests/conftest.py`

**Interfaces:**
- Produces:
  - `TunnelManager` (in `app/tunnel/manager.py`) with `port: int | None = None` (set by the launcher), `hostname: str | None = None`, `state: Literal["stopped", "starting", "running", "failed"] = "stopped"`, `reason: str | None = None`. Task 13 adds the process. `Services.tunnel = TunnelManager(settings)`.
  - `deps.is_tunnel_request(conn: HTTPConnection) -> bool`: `services.tunnel.port is not None` and `conn.scope.get("server")` is a pair whose port equals it. (`HTTPConnection` is Starlette's base of `Request` and `WebSocket`; widen the signatures of `client_address`, `is_https`, `host_ok`, `origin_ok`, `is_host_request` to it.)
  - `netguard.cf_client_key(value: str | None) -> str`: an IPv4 address as text; an IPv6 address as its /64 network (`"2001:db8:1:2::/64"`); an IPv4-mapped IPv6 as the IPv4; missing or unparseable → `"tunnel:unknown"` (one shared bucket: fails closed).
  - `client_address`: on the tunnel port `cf_client_key(headers["cf-connecting-ip"])`, never `X-Forwarded-For` or the peer; elsewhere unchanged.
  - `is_https`: true on the tunnel port (the edge serves only https to the visitor); elsewhere unchanged.
  - `is_host_request`: false on the tunnel port whatever the cookie.
  - `deps.room_host(room: Room, conn: HTTPConnection, token: str | None) -> bool`: `not is_tunnel_request(conn) and room.is_host(token)`. Every API call site of `room.is_host(...)` calls this instead (`authorize`'s `local and room.is_host(token)` already sits behind `is_host_request`). No call site keeps `room.is_host` directly; `git grep -n "\.is_host(" -- backend/app/api` afterwards lists only `deps.py`.
  - `Connection.tunnel: bool = False`, set in `game_socket` from `is_tunnel_request(websocket)`; `Connection.host` uses `room_host`.
  - Launcher: `serve()` binds `lan = socket.create_server((settings.host, settings.port))` and `tun = socket.create_server(("127.0.0.1", 0))` before `create_app`'s server runs, sets `app.state.services.tunnel.port = tun.getsockname()[1]`, and calls `server.run(sockets=[lan, tun])`; one `uvicorn.Server`, one event loop (two servers would split the `asyncio.Lock`s of the rooms). The tunnel port is never printed. uvicorn's `shutdown` closes the sockets it was handed, so both sockets are created inside `serve()`'s restart loop on every iteration (an in-app Restart gets a new tunnel port; any running tunnel was stopped by `Services.close`). The `--local` help text changes as Global Constraints says. A server not started by the launcher (`uvicorn --factory …`) has `tunnel.port = None` and cannot share.
  - Test fixture in `conftest.py`: `TUNNEL_PORT = 18001`; `tunnel_client(client) -> TestClient`: a second `TestClient(client.app, base_url=f"http://127.0.0.1:{TUNNEL_PORT}")` with `services.tunnel.port = TUNNEL_PORT`, `services.tunnel.hostname = "fyodor-test.trycloudflare.com"`, `state = "running"`, default headers `Host: fyodor-test.trycloudflare.com`, `Origin: https://fyodor-test.trycloudflare.com`, `CF-Connecting-IP: 198.51.100.7`. Later tasks' tunnel tests use it.

- [ ] **Step 1: Failing tests** in `test_tunnel_identity.py`: `test_lan_requests_are_not_tunnel_requests`; `test_a_request_on_the_tunnel_port_is_one`; `test_host_cookie_is_not_host_on_the_tunnel_port` (copy the host's cookie into the tunnel client: `GET /api/host/session` → `{"host": false}`); `test_room_host_token_is_not_host_on_the_tunnel_port` (the host seat token on the tunnel client: `POST /api/games/{id}/host/seat-link` → 403; the same on the LAN client → 200; the socket's lobby view has `is_host: false`); `test_tunnel_client_address_is_cf_connecting_ip` (and `X-Forwarded-For` is ignored there); parametrised `test_cf_client_key` (`"198.51.100.7"`, `"2001:db8:1:2:aaaa::1"` → `"2001:db8:1:2::/64"`, `"::ffff:198.51.100.7"` → `"198.51.100.7"`, `None`/`""`/`"1.2.3.4, 5.6.7.8"`/`"x"` → `"tunnel:unknown"`); `test_lan_port_never_reads_cf_connecting_ip`; `test_two_phones_in_one_ipv6_64_share_a_bucket_but_other_64s_do_not`; Review Focus 1: `test_a_seat_reconnects_from_a_new_address` (seat socket on the tunnel client from `CF-Connecting-IP: 198.51.100.7`, closed, reopened with `203.0.113.40` and the same token: full view arrives, `services.join_limiter_addr` has no key for either address). In `test_launcher.py`: `test_serve_listens_on_a_loopback_tunnel_port` (patch `uvicorn.Server.run` to capture `sockets`: two sockets, the second bound to `127.0.0.1` with a non-zero port equal to `services.tunnel.port`).
- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: Implement** in the order of the Interfaces list; replace the 15 call sites mechanically.
- [ ] **Step 4: Run** the new file, `tests/test_launcher.py tests/test_client_address.py tests/test_host_auth.py tests/test_socket_auth.py tests/test_socket_caps.py`, then the full backend suite. Expected: PASS.
- [ ] **Step 5: Commit** `A loopback tunnel port: its requests are never the host and are counted by CF-Connecting-IP`.

### Task 9: What the tunnel port serves

**Files:** Modify `backend/app/netguard.py`, `backend/app/api/deps.py` (`host_ok`, `origin_ok`), `backend/app/main.py` (`net_guard`, `_same_site_request`), `backend/app/api/games.py` (`list_games`, `game_summary`, `game_socket`), `backend/app/api/health.py`, `backend/app/services.py` (`health`), possibly `frontend/src/pages/Home.tsx`/`Welcome.tsx` (Step 4b); Test `backend/tests/test_tunnel_routes.py`

**Interfaces:**
- Consumes: `is_tunnel_request`, `tunnel_client` fixture (Task 8).
- Produces:
  - `netguard.TUNNEL_ROUTES`: an allowlist of `(methods, compiled fullmatch pattern)` and `netguard.tunnel_route(method: str, path: str) -> tuple[bool, str | None]` (allowed, game id named in the path or None). The list, and nothing else:
    - `GET /`, `GET /assets/.+` (the built page; `_mount_frontend` serves only these);
    - `GET /api/health`, `GET /api/host/session`, `POST /api/join`, `GET /api/games`;
    - `GET /api/cards/(search|autocomplete|glossary|[^/]+|[^/]+/printings)`, `POST /api/cards/batch`, `GET /api/images/.+`, `GET /api/symbols(/[^/]+\.svg)?`, `GET /api/assets/[^/]+/file`, `GET /api/rules/(support|coverage)`;
    - any method on `/api/games/{id}` and `/api/games/{id}/…` **except** the subpaths `save`, `assistant`, `rules/scenario`, `host/.*`, `share`, `lobby/bot`, `bot(/.*)?`;
    - the socket `/ws/games/{id}` (checked in `game_socket`, not the middleware).
    Before writing it, list what the remote pages call: `git grep -n "api\.\(get\|post\|put\|del\)\|fetch(" -- frontend/src/services frontend/src/pages/PlayPage.tsx frontend/src/pages/LobbyScreen.tsx frontend/src/pages/GamePage.tsx frontend/src/game` and add any GET a seated player needs that is missing; every addition gets a line in the task report.
  - `tunnel_serves(services, game_id) -> bool` (in `deps.py`): the room exists and is `shared`, or it is a practice room whose `practice.live` names a shared room. (`Room.shared` is added in Task 11; until then this task adds the field with default `False` and the tests set it.)
  - `net_guard` on the tunnel port, in this order, each refusal a 404 `{"detail": "Not Found"}` unless named: Host must equal `services.tunnel.hostname` exactly (case-insensitive, no port) and the tunnel `state` must be `"running"` — else 404 (a refused Host on the tunnel port says nothing about the server); the route must be in `TUNNEL_ROUTES`; a named game id must pass `tunnel_serves` (else the same 404 body as `_room`'s "Game not found…"); an unsafe method needs `Origin` exactly `https://<hostname>` (no-Origin is refused here: the LAN handoff exemption never applies), else 403 "Cross-site request refused". The LAN port's behaviour is unchanged and never accepts the invite hostname as Host.
  - `game_socket` on the tunnel port: Host and Origin as above and `tunnel_serves(room)`; any failure closes exactly as a bad token does (4403 after the auth deadline path, as `_refuse_socket`).
  - `GET /api/games` on the tunnel port returns `[]`. `GET /api/games/{id}` there returns the summary with `"code": None`.
  - `GET /api/health`: `{"status": "ok", "version": …}` for anyone who is not the host; plus `"tunnel": true` on the tunnel port; the host gets today's full body.
  - LAN gate (Stage 2 must #2): `/api/lan/*` is outside `TUNNEL_ROUTES`, so it is a 404 there before `on_local_network` is reached.

- [ ] **Step 1: Failing tests:** `test_every_route_is_either_allowed_or_404_on_the_tunnel_port` (walk `client.app.routes`; for each `APIRoute` and method, build a path with a shared room's id for `{game_id}` and `x` for other parameters; a route not matched by `tunnel_route` answers 404 on the tunnel client — this is the fail-closed guard for routes added later); `test_the_tunnel_branch_is_what_refuses` (routes public on the LAN today — `GET /api/pod/results`, `GET /api/assets`, `GET /api/lan/nearby`, `GET /api/cards/stats` — answer 200 to a LAN guest and 404 on the tunnel client, so the walk above cannot pass with the guard missing); `test_unshared_room_is_no_such_room` (view, lobby, socket); `test_shared_room_plays` (join with the invite code is Task 11; here seat by `claim_seat` directly, then `GET /view` 200 and a socket action applies); `test_wrong_host_on_the_tunnel_port_is_404` (`Host: 127.0.0.1:18001`, `Host: localhost`, `Host: other.trycloudflare.com`); Review Focus 5: `test_the_host_computer_on_the_tunnel_port_is_a_stranger` (host cookie, `Host: 127.0.0.1:18001` → 404 for `/`, `/api/saves`, `/api/games`); `test_no_origin_post_is_refused_on_the_tunnel_port`; `test_http_origin_is_refused_on_the_tunnel_port` (`Origin: http://fyodor-test.trycloudflare.com`); `test_lan_handoff_routes_404_on_the_tunnel_port` (`/api/lan/handoff`, `/api/lan/handoff/missing`, `/api/lan/decks`, with `CF-Connecting-IP: 192.168.1.5`); `test_games_list_and_summary_hide_codes_on_the_tunnel_port`; `test_health_is_trimmed_for_guests` (LAN guest: exactly `status` and `version`; tunnel: plus `tunnel`; host: has `card_database`); `test_pod_stats_and_assets_list_404_on_the_tunnel_port`; `test_tunnel_port_serves_nothing_when_stopped` (`state = "stopped"` → 404 for `/`); `test_invite_hostname_is_refused_on_the_lan_port` (400).
- [ ] **Step 2: Run, expect FAIL. Step 3: Implement. Step 4: Run** the new file, `tests/test_origin_guard.py tests/test_health.py tests/test_lan_handoff.py`, expect PASS.
- [ ] **Step 4b: Guests and the trimmed health.** `frontend/src/pages/Home.tsx:65,147-158` and `Welcome.tsx:38` read `card_database`, `recovery` and `recovered_tables`. Confirm a guest's Home and Welcome render no "card database missing" or recovery notice when those fields are absent (they are host matters); if one does, gate it on `card_database !== undefined` and add a Vitest case. `npm run typecheck && npm test`.
- [ ] **Step 5: Commit** `The tunnel port serves shared tables and what a remote player needs, nothing else`.

### Task 10: Larger body allowances only for the host or a seat, never on the tunnel port (NB1)

The tunnel-port half is always done. Skip the host/seat half if already fixed on the base branch: check `git grep -n "is_host_request\|host_secret\|seat_for_token" -- backend/app/main.py` shows `BodyLimit` consulting them.

**Files:** Modify `backend/app/main.py` (`BODY_ALLOWANCES`, `body_limit`, `BodyLimit`), `backend/app/api/games.py` (name `LOBBY_JSON_CHARS = 2_000_000` beside `LobbyDeckIn.json` and import it in `main.py`, the re-review's concern 2); Test `backend/tests/test_body_limit.py`

**Interfaces:**
- Produces: each allowance carries who may use it: `Literal["any", "host", "seat"]`. `"any"` for `/api/assets(/[^/]+/file)?` and `/api/lan/handoff` (both stream and stop at their bound: `assets.py` `_body`, `lan.py` `receive_handoff`) and for `/api/lan/handoff/missing` (parsed JSON of at most 2 MB, but reached only by LAN peers: the tunnel port never grants it, and Task 9 makes it a 404 there; NB1 does not name it). `"host"`: `/api/backups/restore`, `/api/update/upload`, `/api/packages/import`, `/api/teach/import`, `/api/(browser-decks|backups)`, `/api/decks(/.*)?`. `"seat"`: the lobby deck routes; granted when the `X-Seat-Token` header holds a seat or spectator token of the room named in the path (`Room.seat_for_token(...) is not None`) or the request is the host's.
- `body_limit(path: str, *, host: bool, seat_ok: Callable[[str], bool], tunnel: bool) -> int`; on the tunnel port it is always `BODY_LIMIT`. `BodyLimit` builds `HTTPConnection(scope)` and asks `is_host_request` and `is_tunnel_request` (the one host check, gate 13). Streaming allowances become `bound + BODY_LIMIT` so the route's own 413 text is the one the user sees (re-review minor 2). `declared.isascii() and declared.isdigit()` (minor 3).

- [ ] **Step 1: Failing tests:** `test_a_guest_gets_256k_on_host_routes` (guest `PUT /api/browser-decks` with `Content-Length: 300000` → 413, no route reached); `test_the_host_keeps_the_large_allowance`; `test_a_stranger_gets_256k_on_lobby_routes` (no token / wrong token / token of another room); `test_a_seat_keeps_the_lobby_allowance`; `test_no_allowance_on_the_tunnel_port` (a seated remote player's 300 KB lobby deck → 413); `test_the_route_speaks_first_for_streamed_uploads` (a 21 MB asset upload by the host → the route's "Images are limited to 20 MB").
- [ ] **Step 2: Run, expect FAIL. Step 3: Implement. Step 4: Run** `tests/test_body_limit.py tests/test_security_headers.py`, expect PASS.
- [ ] **Step 5: Commit** `Large request bodies only for the host or a seat, and never through the tunnel`.

### Task 11: Shared rooms and invite codes

**Files:** Modify `backend/app/multiplayer/hub.py` (`Room`, `_new_code`, `by_code`, `meta`, `restore`, `summary`, `lobby_view`, `_meta`, `GameHub.set_password`), `backend/app/api/games.py` (`join_game`), `backend/app/multiplayer/discovery.py` (assert only); Test `backend/tests/test_shared_rooms.py`

**Interfaces:**
- Produces:
  - `Room.shared: bool = False` (the field exists since Task 9; this task gives it meaning), `Room.invite_code: str | None = None`.
  - `GameHub.new_invite_code(room: Room) -> str`: 10 characters from `CODE_ALPHABET` by `secrets.choice`, unique against every room's `code` and `invite_code`; kept on the room once made (re-sharing reuses it).
  - `GameHub.by_invite_code(code: str) -> Room | None`: strip and upper-case; only rooms with `shared` true, `mode == "lan"`, `practice is None`; compared with `hmac.compare_digest`. `by_code` is unchanged and never matches an invite code.
  - `GameHub.set_password(room: Room, password: str) -> None`: new salt, hash at `PASSWORD_ROUNDS`, under `_password_lock`, then `persist`.
  - `join_game`: on the tunnel port the room comes from `by_invite_code`, on the LAN port from `by_code`. Everything else (limiters, identical failure answer, seat claim) is shared code.
  - `meta()` writes `shared` and `invite_code`; `restore()` reads `invite_code` (absent → None) and sets `shared = False` (closing Fyodor ends the link: spec), so old metadata loads.
  - Views: `_meta` and `lobby_view()["game"]` gain `"shared": room.shared` (public, every viewer); `summary()` too. `code` in views is unchanged (a seated remote player already holds a seat, and the LAN code is accepted only on the LAN port); `invite_code` appears in no view and no summary.
  - Discovery: `lan_tables` is untouched; a test pins that its JSON contains neither `invite_code` nor the code value of a shared room's invite.

- [ ] **Step 1: Failing tests:** `test_invite_code_is_ten_characters_of_the_alphabet` (and unique against 200 rooms); `test_tunnel_join_takes_the_invite_code_only` (the LAN code on the tunnel port → the identical 403 body; the invite code with the password → seat); `test_lan_join_never_takes_an_invite_code`; `test_unshared_rooms_invite_code_is_refused_on_the_tunnel_port`; `test_wrong_password_on_the_tunnel_port_counts_against_cf_address` (5 wrong from `198.51.100.7` → 6th 429; `203.0.113.40` still joins); `test_metadata_without_the_fields_loads` and `test_restore_keeps_the_invite_code_and_is_not_shared`; `test_views_say_shared_and_never_the_invite_code` (walk the JSON of a seated view, a spectator view, the lobby view and `GET /api/games` for the invite code string: absent); `test_discovery_never_advertises_the_invite`; `test_set_password_hashes_at_current_rounds`.
- [ ] **Step 2: Run, expect FAIL. Step 3: Implement. Step 4: Run** the new file, `tests/test_lobby.py tests/test_games_api.py tests/test_lan_discovery.py tests/test_reconnect.py`, then the full backend suite, expect PASS.
- [ ] **Step 5: Commit** `Rooms can be shared, with a 10-character invite code accepted only on the tunnel port`.

### Task 12: The pinned cloudflared binary

**Files:** Create `backend/app/tunnel/pins.py`, `backend/app/tunnel/binary.py`; Test `backend/tests/test_tunnel_binary.py`

**Interfaces:**
- Produces:
  - `pins.CLOUDFLARED_VERSION: str`, `pins.Asset` (frozen dataclass: `name: str`, `sha256: str`, `archive: bool`), `pins.ASSETS: dict[tuple[str, str], Asset]` keyed by `(platform.system().lower(), normalised machine)`: `("windows", "amd64")` and `("windows", "arm64")` → `cloudflared-windows-amd64.exe`; `("darwin", "amd64")` → `cloudflared-darwin-amd64.tgz` (archive); `("darwin", "arm64")` → `cloudflared-darwin-arm64.tgz` (archive); `("linux", "amd64")` → `cloudflared-linux-amd64`; `("linux", "arm64")` → `cloudflared-linux-arm64`. `pins.release_url(asset) -> str` = `f"https://github.com/cloudflare/cloudflared/releases/download/{CLOUDFLARED_VERSION}/{asset.name}"`. Machine normalisation: `x86_64`/`AMD64` → `amd64`, `aarch64`/`ARM64` → `arm64`.
  - `binary.TunnelUnavailable(Exception)` with a user-facing message.
  - `binary.ensure_binary(folder: Path, client: Callable[..., httpx.Client], *, allow_network: bool, system: str | None = None, machine: str | None = None) -> Path`: the verified executable at `folder / f"cloudflared-{VERSION}[.exe]"`. Existing file whose SHA-256 matches → returned without network. Otherwise: `allow_network` false → `TunnelUnavailable("Internet features are turned off on this computer (FYODOR_ALLOW_NETWORK=0).")`; unsupported platform → `TunnelUnavailable("Sharing over the internet isn't available on this kind of computer.")`; download with `follow_redirects=True`, streamed to `<name>.part`, stopped at 150 MB; SHA-256 of the downloaded file (the `.tgz` itself for archives) compared with `hmac.compare_digest` against the pin; mismatch → the `.part` deleted, `TunnelUnavailable("The downloaded tunnel program didn't match the expected checksum, so it wasn't used.")`, nothing executed. Archives: extract only the member named `cloudflared` (no path parts, regular file) with `tarfile` into `.part`, `chmod 0o755`. Then rename into place.
  - `pins.Asset` has a fourth field `binary_sha256: str`: the SHA-256 of the executable itself (equal to `sha256` for the direct `.exe` and Linux binaries; for the two macOS archives, the hash of the `cloudflared` member, obtained in Step 1). Both are pinned in the repo; nothing is recorded at run time.
  - `binary.verify(path: Path, asset: Asset) -> bool`: the file's SHA-256 equals `asset.binary_sha256` (`hmac.compare_digest`). Used after download or extraction and again before every launch (Task 13).

- [ ] **Step 1: Confirm the pins.** Open https://github.com/cloudflare/cloudflared/releases/tag/2026.11.2 (or the release Task 1 chose: the newest one at least 14 days old on the day of this task, for supply-chain caution), copy each of the five hashes from "SHA256 Checksums:" by hand, then download each asset into a new empty scratch folder and run `certutil -hashfile <file> SHA256` (or `sha256sum`). Both must match; write both commands' output into the audit file. For the two macOS `.tgz` assets also extract `cloudflared` by hand (`tar -xzf`) and hash it: that is `binary_sha256`. The values in Provider findings are not trusted.
- [ ] **Step 2: Failing tests** (no network: a fake `httpx.Client` via `httpx.MockTransport`): `test_existing_verified_binary_needs_no_network`; `test_download_is_verified_and_renamed`; `test_a_wrong_hash_leaves_nothing_and_raises` (no `.part`, no executable); `test_allow_network_false_never_downloads` (the transport asserts it is never called); `test_download_stops_at_the_size_cap`; `test_archive_member_with_a_path_is_refused` (`../cloudflared`, `bin/cloudflared`, a symlink member); `test_platform_map` (parametrised over the six keys and an unsupported `("freebsd", "amd64")`); `test_a_replaced_binary_fails_verify` (flip one byte of a verified file: `verify` is False and `ensure_binary` downloads again rather than returning it); `test_pins_are_well_formed` (version matches `^\d{4}\.\d{1,2}\.\d+$`, each hash `^[0-9a-f]{64}$`, every URL starts `https://github.com/cloudflare/cloudflared/releases/download/`).
- [ ] **Step 3: Run, expect FAIL. Step 4: Implement. Step 5: Run, expect PASS.**
- [ ] **Step 6: Commit** `cloudflared is downloaded on first use, pinned by version and SHA-256`.

### Task 13: Running the tunnel

**Files:** Create `backend/app/tunnel/process.py`; Modify `backend/app/tunnel/manager.py`, `backend/app/services.py` (`close`); Test `backend/tests/test_tunnel_process.py`

**Interfaces:**
- Consumes: `ensure_binary`, `verify`, `TunnelUnavailable` (Task 12); `TunnelManager.port` (Task 8).
- Produces:
  - `process.QUICK_HOST = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\.trycloudflare\.com")` (fullmatch, lower-case).
  - `process.command(exe: Path, port: int, metrics_port: int, config: Path) -> list[str]` = `[exe, "tunnel", "--no-autoupdate", "--config", config, "--metrics", f"127.0.0.1:{metrics_port}", "--url", f"http://127.0.0.1:{port}"]` (or Task 1's alternative to `--config`: `HOME`/`USERPROFILE` pointed at `data_dir/tunnel/home` in the child's environment).
  - `process.read_hostname(metrics_port: int, timeout: float = 30.0) -> str`: polls `http://127.0.0.1:{metrics_port}/quicktunnel` every 0.5 s; returns `hostname` only when it fullmatches `QUICK_HOST`; otherwise `TunnelUnavailable("The internet link didn't come up. Check this computer's connection and try again.")` at the timeout.
  - `process.kill_with_parent(proc: subprocess.Popen[bytes]) -> None`: on Windows, a Job object with `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE` (ctypes: `CreateJobObjectW`, `SetInformationJobObject`, `AssignProcessToJobObject`; the handle kept on the manager for the process's life) so the child dies with Fyodor even when Fyodor is killed; elsewhere a no-op (a hard kill of Fyodor on macOS/Linux leaves cloudflared pointing at a closed port: listed in the audit's remaining risks).
  - `TunnelManager.start() -> Awaitable[str]` (async): idempotent: while `running` it returns the hostname; while `starting` a second call awaits the same `asyncio.Future` the first created (a double click or the page's poll never spawns a second process); otherwise `state = "starting"`; on the default executor: `ensure_binary`, `verify` again, pick a free metrics port (bind `127.0.0.1:0`, read, close), `Popen(command(...), stdout=DEVNULL, stderr=DEVNULL, stdin=DEVNULL, creationflags=CREATE_NO_WINDOW on Windows)`, `kill_with_parent`, `read_hostname`; `state = "running"`, `hostname` set. Any `TunnelUnavailable` → process stopped, `state = "failed"`, `reason` = its message, re-raised. Captures the running loop; a watcher thread waits on the process and, if it exits while `running`, sets `state = "failed"`, `reason = "The internet link went down."`, `hostname = None`, and schedules `on_down()` on the loop with `loop.call_soon_threadsafe`.
  - `TunnelManager.stop() -> None`: terminate, wait 5 s, kill; `state = "stopped"`, `hostname = None`; never runs `on_down`.
  - `TunnelManager.on_down: Callable[[], Awaitable[None]] | None` (set by Task 14).
  - `Services.close()` calls `self.tunnel.stop()` first.
  - cloudflared output is not read or logged (it can carry the hostname, which is fine, but nothing reads it).

- [ ] **Step 1: Failing tests** (a stand-in "cloudflared": a small Python script written by the test to `tmp_path`, run as `[sys.executable, script, …]` via a monkeypatched `command`, that serves `/quicktunnel` on the given metrics port and then sleeps): `test_start_reports_the_hostname`; `test_two_starts_at_once_spawn_one_process` (`asyncio.gather(start(), start())`: one `Popen`, both return the hostname); `test_a_hostname_that_is_not_trycloudflare_fails_closed` (`evil.example.com`, `a.trycloudflare.com.evil.com`, empty); `test_start_times_out_when_no_hostname` (timeout monkeypatched to 1 s); `test_a_dying_process_calls_on_down_and_clears_the_hostname` (Review Focus 4); `test_stop_ends_the_process_and_not_on_down`; `test_services_close_stops_the_tunnel`; `test_command_disables_autoupdate_and_pins_metrics_to_loopback`; on Windows only (`pytest.mark.skipif(os.name != "nt")`): `test_the_child_dies_with_the_job` (close the job handle → the child exits within 5 s).
- [ ] **Step 2: Run, expect FAIL. Step 3: Implement. Step 4: Run, expect PASS.**
- [ ] **Step 5: Commit** `The tunnel runs as a child of Fyodor, its hostname read from cloudflared's metrics`.

### Task 14: The share API

**Files:** Create `backend/app/api/share.py`; Modify `backend/app/main.py` (router), `backend/app/multiplayer/hub.py` (`close_tunnel_connections`), `backend/app/services.py` (wire `tunnel.on_down`); Test `backend/tests/test_share_api.py`

**Interfaces:**
- Consumes: `TunnelManager.start/stop/on_down` (Task 13), `new_invite_code`, `set_password`, `Room.shared` (Task 11), `Connection.tunnel` (Task 8).
- Produces:
  - `ShareStatus` JSON: `{"shared": bool, "state": "stopped"|"starting"|"running"|"failed", "reason": str | null, "link": str | null, "has_password": bool, "available": bool}`; `link` = `f"https://{hostname}/#/play?code={invite_code}&join=1"` only while this room is shared and the tunnel is running; `available` false when `allow_network` is off or `tunnel.port` is None.
  - `GET /api/games/{id}/share` → `ShareStatus`; `POST /api/games/{id}/share` body `ShareIn {password: str | None = Field(None, min_length=8, max_length=100)}` → `ShareStatus`; `DELETE /api/games/{id}/share` → `ShareStatus`. All three: `require_host` (the host cookie, so never through the tunnel), room must be `mode == "lan"` and not practice (else 409 "Only a LAN table can be shared"). POST: not `available` → 409 with the reason ("Start Fyodor from its launcher to share over the internet." / the allow_network sentence); no password set and none given → 422 "A table shared over the internet needs a password."; a password given when one is set → 409 "This table already has a password."; then `set_password` if given, `new_invite_code`, `await services.tunnel.start()` (`TunnelUnavailable` → 502 with its message, room not shared), `room.shared = True`, `persist`, broadcast. DELETE: `room.shared = False`, `persist`, `close_tunnel_connections(room, "The host stopped sharing this table.")`, broadcast; when no room is shared any more, `tunnel.stop()`.
  - `GameHub.close_tunnel_connections(room: Room, reason: str) -> Awaitable[int]`: closes every `conn.tunnel` socket of the room with 4403; LAN sockets untouched.
  - `on_down`: for every shared room, `shared = False`, close its tunnel connections with "The internet link went down.", broadcast.
  - Lobby rooms (not persisted) and started rooms behave alike.

- [ ] **Step 1: Failing tests** (`services.tunnel.start` monkeypatched to set `hostname = "fyodor-test.trycloudflare.com"`, `state = "running"`): `test_only_the_host_cookie_shares` (seat token without cookie → 403; through the tunnel client → 404); `test_sharing_needs_a_password` (422, then 200 with `password="correct horse"`, then `has_password` true and the LAN join needs it too); `test_a_short_password_is_422`; `test_share_returns_the_link_with_the_invite_code`; `test_allow_network_off_is_409_and_never_starts`; `test_no_tunnel_port_is_409`; `test_tunnel_unavailable_is_502_and_the_room_stays_unshared`; Review Focus 3: `test_stop_sharing_closes_only_tunnel_sockets` (a LAN socket and a tunnel socket on one shared room; DELETE; the tunnel socket closes 4403 with the reason, the LAN socket gets the next broadcast with `shared: false`; an action sent on the tunnel socket just before the DELETE is applied once or not at all: assert the log has at most one entry for its `client_action_id`); `test_last_unshare_stops_the_tunnel_and_not_before` (two shared rooms); Review Focus 4: `test_link_down_unshares_and_says_so` (call `on_down`: views say `shared: false`, `GET …/share` says `state: "failed"`, reason "The internet link went down."); `test_resharing_reuses_the_invite_code`; `test_practice_and_hot_seat_tables_cannot_be_shared`.
- [ ] **Step 2: Run, expect FAIL. Step 3: Implement. Step 4: Run** the new file plus `tests/test_tunnel_routes.py tests/test_shared_rooms.py`, expect PASS.
- [ ] **Step 5: Commit** `Host tools can share a table over the internet and stop sharing it`.

### Task 15: Invite over the internet (frontend)

Read `.claude/skills/fyodor-ui-design/SKILL.md` first and inspect the lobby's Invite popover and the in-game Host tools running (`/run`) before changing them; build with `frontend-design`, critique with `impeccable`.

**Files:** Create `frontend/src/services/share.ts`, `frontend/src/services/share.test.ts`, `frontend/src/game/InternetInvite.tsx`, `frontend/src/game/internetInvite.test.ts`; Modify `frontend/src/pages/LobbyScreen.tsx` (`InviteControl`), `frontend/src/game/HostTools.tsx`, `frontend/src/game/TopBar.tsx`, `frontend/src/pages/lanBits.ts`, `frontend/src/pages/lanBits.test.ts`, `frontend/src/pages/PlayPage.tsx`, the view and lobby types in `frontend/src/types/`

**Interfaces:**
- Consumes: the share API and `ShareStatus` (Task 14); `shared` in views (Task 11); `tunnel` in `/api/health` (Task 9).
- Produces:
  - `share.ts`: `type ShareStatus` (as Task 14), `getShare(gameId)`, `startShare(gameId, password?: string)`, `stopShare(gameId)`.
  - `InternetInvite({ gameId }: { gameId: string })`: a section titled **Invite over the internet**. States: not available → the reason as text, no button; not shared → one button **Invite over the internet**; pressing it with `has_password` false first shows a password field (8–100 characters, label "Table password (friends need it to join)"); `starting` → "Starting the link… the first time downloads the tunnel program (about 40 MB)."; `running` and shared → the link in a read-only field with **Copy link** (the existing `CopyButton`), the line "Send the password separately.", and **Stop sharing**; `failed` → its reason and **Invite again**. Poll `getShare` every 2 s only while `starting`. Mounted inside the lobby's Invite popover (host only) and as a section of `HostToolsDialog` (LAN tables only). Today `LobbyScreen.tsx:162` renders `InviteControl` only when `lobby.is_host && invite`, and `invite` is null under `--local` (`lanInfo().reachable` false): render the popover for the host whenever `lobby.is_host`, with the LAN link section only when `invite` is non-null.
  - On the tunnel (`health.tunnel` true) the room-code chip (`RoomCode` in `LobbyScreen.tsx` and the in-game code display) is hidden: the LAN code it would show does not work for a friend through the link.
  - TopBar and lobby header: when `shared` is true, a chip with a globe icon and the text "Shared over the internet" (icon + text, keyboard focusable with a title), for every viewer.
  - `lanBits.planInvite(invite, games, held, tunnel: boolean)`: on the tunnel (`tunnel` true) and not `fill`, the plan is `{ kind: "password" }` unless the table is held. `PlayPage` reads `tunnel` from `GET /api/health` once and passes it.
  - Only if Task 1 saw 429s on images: card images retry once after 1 s on a 429 (in the image component that owns `src`), with a test.

- [ ] **Step 1: Failing Vitest tests:** `share.test.ts` (each call's method, path and body; the password is sent only when given); `internetInvite.test.ts` as server renders like `playGuest.test.ts` (no DOM environment): unavailable shows the reason and no button; unshared shows the button; `has_password: false` after pressing shows the field (test the pure state function `inviteStep(status, pressed): "unavailable" | "button" | "password" | "starting" | "link" | "failed"` and render each); running shows the link and "Send the password separately."; `lanBits.test.ts`: tunnel invites always ask for the password; LAN behaviour unchanged; a pure `showInvitePopover(isHost, lanLink)` is true for the host with `lanLink` null (the `--local` case).
- [ ] **Step 2: Run** `npx vitest run src/services/share.test.ts src/game/internetInvite.test.ts src/pages/lanBits.test.ts`, expect FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `npm run typecheck && npm test`, expect PASS. Screenshot the lobby popover and Host tools in each state at 1920×1080 and a phone width; run `impeccable` critique on them and fix findings that fit the tabletop direction.
- [ ] **Step 5: Commit** `Invite over the internet in the lobby and Host tools; shared tables show it in the top bar`.

### Task 16: Stage gate

**Files:** Modify `docs/LAN_PLAY.md` (an "Inviting friends over the internet" section beside option A, the private network: what the host presses, that friends need the link and the password, that Cloudflare sees the traffic and positions quick tunnels "for testing and development" with no uptime guarantee, that closing Fyodor ends the link, `FYODOR_ALLOW_NETWORK=0` turns it off; the env-variable changes from Task 4), `docs/CURRENT_STATE.md` (one batch entry), `docs/superpowers/specs/2026-11-25-stage2-audit.md`

- [ ] **Step 1:** From `backend/`: `.venv/Scripts/ruff check . && .venv/Scripts/mypy app tools && .venv/Scripts/python -m pytest -n 8 -q`; compare ruff and mypy with the base branch's counts (no new errors). From `frontend/`: `npm run typecheck && npm test`. Paste the summaries into the audit file.
- [ ] **Step 2:** `bandit -r app -q`, `pip-audit`, `npm audit`; list each finding on a line this stage added with "fixed in <commit>" or "accepted because …" (the ctypes and `subprocess` lines of `app/tunnel` will be among them).
- [ ] **Step 3:** Walk the spec's 13-point Review gate, one line per point with the test or commit that satisfies it or "not applicable" and why. Point 9 names the cloudflared version, the five hashes, and the two independent checks of Task 12 Step 1. Point 10's "timeout racing an action" is not applicable (Stage 3). Point 13: `git grep -n "\.is_host(" -- backend/app/api` lists only `deps.py`; `git grep -n "cf-connecting-ip" -- backend/app` lists only `deps.py`/`netguard.py`; `git grep -n "proxy_headers" -- backend/app` shows only `False`.
- [ ] **Step 4: Stage 2 must checklist.** One line per item 1–10 of the Stage 1 audit's "Stage 2 must", plus NB1 and SR1, each with its task and test.
- [ ] **Step 5: Manual check through a real tunnel**, recorded line by line: host starts Fyodor from the launcher; in a lobby presses **Invite over the internet**, sets a password, copies the link; a phone on mobile data (not on the Wi-Fi) opens the link, is asked the password, joins, plays a land; the top bar on both says shared; the phone sleeps a minute and comes back to the same seat; the phone switches Wi-Fi→mobile data mid-game and stays seated (Review Focus 1); the phone opens `/api/saves`, `/api/games`, `/api/pod/results` by hand: 404 / `[]`; a LAN player joins by the 6-character code as always; the host presses **Stop sharing**: the phone's table closes with "The host stopped sharing this table.", the LAN player plays on; the host invites again: a new hostname, the same invite code; the host closes Fyodor: the link stops answering; Task Manager shows no `cloudflared` left. Repeat the join on an iPhone (CSP `connect-src 'self'` with `wss:`).
- [ ] **Step 6:** Run the `security-review` skill on the branch and dispatch one fresh reviewer with the spec, the Stage 1 audit's "Stage 2 must", this plan and the diff. Fix or answer every finding.
- [ ] **Step 7: Commit** the docs and audit file. Do not merge until the owner has read the audit file.

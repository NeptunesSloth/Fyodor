# Internet Play Stage 1 (Hardening) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Fyodor server safe to reach from outside the LAN, without changing how a LAN night works.

**Architecture:** Host authority moves from "the peer is loopback" to a host secret held in a cookie, behind the one existing function every route already calls. Client addresses, Origin checks, join limits and socket limits each get one small module that the existing routes call; nothing is duplicated. The WebSocket authenticates in its first message.

**Tech Stack:** Python 3.12, FastAPI/Starlette, pytest (`backend/`); TypeScript, Vite, Vitest (`frontend/`). No new runtime dependency. Dev-only: `bandit`, `pip-audit`.

**Spec:** `docs/superpowers/specs/2026-11-21-internet-play-design.md` (Stage 1 and the Review gate). Stages 2 (invite link) and 3 (turn clock) get their own plans; "shared tables require a password and 10-character codes" belongs to Stage 2.

## Global Constraints

- A LAN-only night needs no internet, account or certificate, and no new step for the host or the players.
- One host check, one token check, one rate limiter: extend `authorize` and `app/api/deps.py`; no parallel path.
- Tokens and secrets come from `secrets`, are compared with `hmac.compare_digest`, never appear in a URL query string or a log line.
- No new `except Exception`, bare `except` or silent fallback; authority checks fail closed.
- New persisted fields have defaults so old saves and old room metadata load.
- Tests are written from the requirement before the code.
- Before every commit, from `backend/`: `.venv/Scripts/ruff check . && .venv/Scripts/mypy app tools`; before the last commit of each task the task's test files pass; the full suite (`.venv/Scripts/python -m pytest -n 8 -q`) passes at Tasks 1, 4 and 10. Frontend changes: `npm run typecheck && npm test` in `frontend/`.
- Work on a branch `internet-play-stage1`, not `master`.

## Review Focus

1. A host who opens Fyodor by typing `http://127.0.0.1:8000` instead of using the launcher has no host cookie: they must be told how to become host, not shown a broken page. (Task 1)
2. A second browser profile or a second device on the host's desk is not the host; host tools must be absent there, with the same message a guest gets. (Task 1)
3. A tab left open across a server restart holds an old host cookie and old seat token; it must fail cleanly and recover on reload, not loop reconnecting. (Tasks 1, 4)
4. A phone that sleeps mid-game and wakes must reconnect and re-authenticate without tripping the join limiter or the per-seat connection cap. (Tasks 5, 7)
5. A player who double-clicks or whose network retries an action must see it applied once. (Task 8)

---

## File map

| File | Responsibility |
|---|---|
| `backend/app/hostauth.py` (new) | Create, store and verify the host secret |
| `backend/app/api/deps.py` | `is_host_request`, `require_host`, `client_address`; old names kept as aliases |
| `backend/app/api/host.py` (new) | `POST /api/host/session`: exchange the secret for the cookie |
| `backend/app/netguard.py` (new) | Origin allowlist check; `AttemptLimiter`; `ConnectionCaps` |
| `backend/app/api/games.py` | Socket first-message auth, caps, heartbeat, action ids; join limiter |
| `backend/app/multiplayer/hub.py` | Password rounds; closing a seat's sockets; recent action ids |
| `backend/app/main.py` | Origin middleware, HSTS, docs off |
| `backend/app/launcher.py` | Open the browser with `#host=<secret>` |
| `backend/tests/conftest.py` | `client` is the host (cookie set); `guest` helper has none |
| `frontend/src/services/hostSession.ts` (new) | Read `#host=`, post it, clear the fragment |
| `frontend/src/services/gameSocket.ts` | Send `auth` first; action ids |
| `frontend/src/pages/GamePage.tsx` | Seat link token from the fragment |

---

### Task 1: Host secret replaces "loopback means host"

**Files:**
- Create: `backend/app/hostauth.py`, `backend/app/api/host.py`, `backend/tests/test_host_auth.py`, `frontend/src/services/hostSession.ts`, `frontend/src/services/hostSession.test.ts`
- Modify: `backend/app/api/deps.py`, `backend/app/main.py`, `backend/app/launcher.py:220-240`, `backend/app/services.py`, `backend/tests/conftest.py`, the frontend entry that boots the app, and every test that simulates a guest with `X-Forwarded-For`

**Interfaces:**
- Produces:
  - `hostauth.HostSecret(path: Path)` with `.value: str` (`secrets.token_urlsafe(32)`, written to `path` on creation, a new value every server start) and `.matches(candidate: str | None) -> bool` (constant-time; `None`/empty is `False`).
  - `Services.host_secret: HostSecret`, file `settings.data_dir / "host.secret"`.
  - `HOST_COOKIE = "fyodor_host"`.
  - `deps.is_host_request(request: Request | WebSocket) -> bool`: true only when the `fyodor_host` cookie matches. The peer address and `X-Forwarded-For` are not read.
  - `deps.require_host(request: Request) -> None`: 403 "Only available on the host computer".
  - `is_local_request = is_host_request` and `require_local = require_host` remain as aliases so the ~100 call sites are untouched.
  - `POST /api/host/session` body `{"secret": str}`: 204 and `Set-Cookie: fyodor_host=<secret>; HttpOnly; SameSite=Strict; Path=/` (plus `Secure` when the request scheme is https) on a match; 403 otherwise. Limited by Task 5's limiter once it exists (add the call in Task 5).
  - Frontend `claimHostSession(): Promise<boolean>`: if `location.hash` has `host=`, POST it, then `history.replaceState` to remove it; returns whether the cookie was set.
  - Test fixtures: `client` carries the host cookie; `guest(client)` returns headers/cookies for a request without it.

- [ ] **Step 1: Write the failing tests** in `backend/tests/test_host_auth.py`:

```python
def test_loopback_without_cookie_is_not_host(settings):
    with TestClient(create_app(settings)) as c:          # peer "testclient" = loopback
        assert c.get("/api/saves").status_code == 403

def test_cookie_makes_host(settings):
    with TestClient(create_app(settings)) as c:
        secret = c.app.state.services.host_secret.value
        assert c.post("/api/host/session", json={"secret": secret}).status_code == 204
        assert c.get("/api/saves").status_code == 200

def test_wrong_secret_refused_and_sets_nothing(settings):
    with TestClient(create_app(settings)) as c:
        r = c.post("/api/host/session", json={"secret": "x" * 43})
        assert r.status_code == 403 and "set-cookie" not in r.headers

def test_forged_forwarded_for_gives_nothing(settings):
    with TestClient(create_app(settings)) as c:
        assert c.get("/api/saves", headers={"X-Forwarded-For": "127.0.0.1"}).status_code == 403

def test_cookie_flags(settings):
    with TestClient(create_app(settings)) as c:
        r = c.post("/api/host/session", json={"secret": c.app.state.services.host_secret.value})
        flags = r.headers["set-cookie"].lower()
        assert "httponly" in flags and "samesite=strict" in flags

def test_secret_changes_each_start_and_file_is_private(settings):
    with TestClient(create_app(settings)) as a:
        first = a.app.state.services.host_secret.value
    with TestClient(create_app(settings)) as b:
        assert b.app.state.services.host_secret.value != first
    assert (settings.data_dir / "host.secret").is_file()
```

- [ ] **Step 2: Run** `.venv/Scripts/python -m pytest tests/test_host_auth.py -q`. Expected: FAIL (no `host_secret`, 404 on the route).
- [ ] **Step 3: Implement `HostSecret`** in `backend/app/hostauth.py`. Write the file with owner-only permissions (`os.open(..., 0o600)`; on Windows the user profile ACL is the protection, state this in the docstring).
- [ ] **Step 4: Implement** `is_host_request`, `require_host`, the aliases, `Services.host_secret`, and `backend/app/api/host.py`; register the router in `main.py`.
- [ ] **Step 5: Update `backend/tests/conftest.py`** so the `client` fixtures claim the host session after creation, and add `guest`. Replace every `X-Forwarded-For` guest simulation in `backend/tests/` (find them with `git grep -n -i "x-forwarded-for" -- backend/tests`) with `guest`. Do not weaken any assertion: a test that expected 403 for a guest still expects 403.
- [ ] **Step 6: Launcher.** `launcher.py` opens `f"{local}/#host={secret}"`, on a normal start, after its in-app restart (`request_restart`, `launcher.py:329`), and on the "already serving, reopen the table" path (`launcher.py:118`; there the secret is read from `host.secret`). The secret is read from the running app's `Services`, or from `host.secret` when the launcher and server are separate processes. It is never printed or logged.
- [ ] **Step 7: Frontend.** Write `hostSession.test.ts` first (hash with `host=abc` posts `{"secret":"abc"}` and clears the hash; no hash posts nothing; a 403 leaves the user a guest), then `hostSession.ts`, and call `claimHostSession()` before the first API request at app boot.
- [ ] **Step 8: Review Focus 1 and 2.** Test: a cookie-less loopback GET of the host-only UI state reports `host: false`; the frontend shows, where host tools would be, "Open Fyodor from its launcher on the host computer to use host tools." Add the backend assertion to `test_host_auth.py` and the copy to the component that renders host tools.
- [ ] **Step 9: Run the full backend suite and the frontend checks.** Expected: all pass.
- [ ] **Step 10: Commit** `Host authority is a host secret in a cookie, not the peer address`.

### Task 2: Client address from trusted proxies only

**Files:** Modify `backend/app/config.py`, `backend/app/api/deps.py`; Test `backend/tests/test_client_address.py`

**Interfaces:**
- Produces: `Settings.trusted_proxies: tuple[str, ...] = ()` from `FYODOR_TRUSTED_PROXIES` (comma-separated IPs or CIDRs); `deps.client_address(request: Request | WebSocket) -> str`: the peer address, unless the peer is in `trusted_proxies`, in which case the rightmost `X-Forwarded-For` entry that is not itself a trusted proxy. Unparseable entries fall back to the peer address. Used for limits and logs only.

- [ ] **Step 1: Failing tests:**

```python
@pytest.mark.parametrize("trusted,peer,xff,expected", [
    ((), "203.0.113.9", "127.0.0.1", "203.0.113.9"),                      # header ignored by default
    (("127.0.0.1",), "127.0.0.1", "198.51.100.7", "198.51.100.7"),
    (("127.0.0.1",), "127.0.0.1", "1.2.3.4, 198.51.100.7", "198.51.100.7"),  # rightmost, not first
    (("127.0.0.1", "10.0.0.0/8"), "127.0.0.1", "198.51.100.7, 10.0.0.2", "198.51.100.7"),
    (("127.0.0.1",), "127.0.0.1", "not-an-ip", "127.0.0.1"),
    (("127.0.0.1",), "127.0.0.1", None, "127.0.0.1"),
])
def test_client_address(trusted, peer, xff, expected): ...
```

- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: Implement** with `ipaddress`; a pure helper `_resolve(peer: str | None, xff: str | None, trusted: tuple[str, ...]) -> str` carries the logic so the test needs no server.
- [ ] **Step 4: Run, expect PASS. Commit** `Client address: X-Forwarded-For only from configured proxies, rightmost entry`.

### Task 3: Origin allowlist on sockets and state-changing requests

**Files:** Create `backend/app/netguard.py`; Modify `backend/app/main.py`, `backend/app/api/games.py` (`game_socket`); Test `backend/tests/test_origin_guard.py`

**Interfaces:**
- Produces: `netguard.origin_allowed(origin: str | None, host_header: str | None, extra: Iterable[str]) -> bool`: true when `origin`'s scheme://host:port equals the request's own `Host` under http or https, or is in `extra` (`settings.cors_origins` plus, in Stage 2, the invite hostname via `Services.extra_origins: set[str]`, created empty here). `None` is `False`.
- HTTP middleware: for `POST`, `PUT`, `PATCH`, `DELETE`, a request whose `Origin` is not allowed gets 403 `{"detail": "Cross-site request refused"}`. Requests with no `Origin` and no `Sec-Fetch-Site` (non-browser clients: the LAN discovery handoff in `app/api/lan.py`, bots, tests) are let through; a request with `Sec-Fetch-Site: cross-site` is refused regardless.
- Host header guard (DNS rebinding): `netguard.host_allowed(host_header: str | None, extra_hosts: Iterable[str]) -> bool` is true only for an IP literal, `localhost`, `socket.gethostname()` (case-insensitive, with or without a port), or a name in `extra_hosts`. Every HTTP request and socket upgrade with a disallowed `Host` gets 400 / close 4400, before anything else runs.
- Socket: `game_socket` closes with code 4403 "Cross-site connection refused" before `accept()` when `origin_allowed` is false. A missing Origin on a socket is refused.

- [ ] **Step 1: Failing tests:** same-origin POST passes; `Origin: https://evil.example` POST is 403 and changes nothing (assert the game list is unchanged); `Sec-Fetch-Site: cross-site` with no Origin is 403; a GET with a foreign Origin still works; socket with a foreign Origin closes 4403; socket with no Origin closes 4403; socket with the test origin connects; a dev origin from `cors_origins` passes; `Host: 192.168.1.20:8000`, `Host: localhost:8000` and the machine's hostname are served; `Host: evil.example` is 400 even for a GET.
- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: Implement.** Update the socket test helper in `backend/tests` to send `Origin: http://testserver`.
- [ ] **Step 4: Run the new tests and `tests/test_games_api.py tests/test_lobby.py tests/test_lan_handoff.py`, expect PASS. Commit** `Origin allowlist on the game socket and state-changing requests`.

### Task 4: Socket authenticates in its first message; no token in a URL

**Files:** Modify `backend/app/api/games.py` (`game_socket`), `frontend/src/services/gameSocket.ts`, `frontend/src/pages/GamePage.tsx`, the host tool that builds the seat link; Test `backend/tests/test_socket_auth.py`, `frontend/src/services/gameSocket.test.ts`

**Interfaces:**
- Protocol: the client connects to `/ws/games/{id}` with no `token` parameter and sends `{"type":"auth","token":<str|null>,"viewer":<str|null>,"deltas":<bool>}` as its first message. The server accepts the upgrade, waits at most `AUTH_DEADLINE = 5.0` seconds, sends nothing before auth succeeds, and closes 4403 on a bad token, a non-auth first message, a message over `MAX_WS_MESSAGE`, or the deadline.
- Compatibility: `?token=` in the query string is still honoured **only** when `FYODOR_LEGACY_WS_TOKEN=1` (default off; `Settings.legacy_ws_token: bool = False`). This replaces the spec's "one release" window with an explicit switch, so nothing is silently accepted.
- Seat links: `…/game/<id>#seat_token=<token>` (fragment). `GamePage.tsx` reads the fragment, stores the token as today, and clears the fragment. `?seat_token=` in the query is no longer generated; it is still read for links already sent, then removed from the address bar.
- Produces for Task 7/8: after auth, `conn.token: str | None` is set on `Connection`.

- [ ] **Step 1: Failing backend tests:** auth message with a valid seat token receives the full table; nothing is received before auth (assert the first server message arrives only after `auth`); wrong token closes 4403; first message `{"type":"action",...}` closes 4403; silence closes 4403 after the deadline (monkeypatch `AUTH_DEADLINE` to 0.05); `?token=` alone closes 4403 by default and works with `legacy_ws_token=True`; the access log line for the upgrade contains no token.
- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: Implement the server side.** Host status still comes from `room.is_host(token)`; `authorize(..., local=is_host_request(websocket), ...)` is unchanged.
- [ ] **Step 4: Frontend tests then code:** `gameSocket` sends `auth` on open before anything else and queues other sends until the first server message; on close code 4403 it stops reconnecting and surfaces "Your seat is no longer valid here. Join again." (Review Focus 3).
- [ ] **Step 5: Seat link** generation and reading as above, with a Vitest case for fragment reading and clearing.
- [ ] **Step 6: Run the full backend suite and frontend checks. Commit** `Game socket authenticates in its first message; seat links use the fragment`.

### Task 5: Limit room-code and password guesses

**Files:** Modify `backend/app/netguard.py`, `backend/app/api/games.py:562-580` (`join_game`), any other route that calls `check_password` or `by_code` (find with `git grep -n "check_password\|by_code(" -- backend/app`), `backend/app/api/host.py`; Test `backend/tests/test_join_limits.py`

**Interfaces:**
- Produces: `netguard.AttemptLimiter(max_failures: int, window: float, clock: Callable[[], float] = time.monotonic)` with `.blocked(key: str) -> bool`, `.fail(key: str) -> None`, `.succeed(key: str) -> None`. In-memory; entries expire after `window`; at most 10,000 keys (oldest dropped).
- `Services.join_limiter_addr = AttemptLimiter(5, 900.0)` keyed by `client_address`; `Services.join_limiter_room = AttemptLimiter(30, 900.0)` keyed by room code (wrong passwords only).
- `join_game`: when blocked, 429 `{"detail": "Too many attempts. Try again in a few minutes."}` with `Retry-After`. An unknown code and a wrong password return the **same** status and body (keep today's message for wrong password; use it for both). Only failures count; a correct join clears the address key.
- `POST /api/host/session` uses `join_limiter_addr` the same way.
- Before writing, confirm with `git grep -n -i "limit\|throttle" -- backend/app/api backend/app/multiplayer` that no join limiter already exists; if one does, extend it instead and say so in the commit.

- [ ] **Step 1: Failing tests:** 5 wrong passwords from one address then the 6th (even with the right password) is 429; another address still joins; after the window (inject the clock) the address joins; unknown code and wrong password give identical status and JSON; 30 wrong passwords spread over 30 addresses block the room for a 31st wrong attempt but a correct password from a fresh address still joins (the room key must not lock out the real pod: `blocked` on the room key applies only after a failure in the same request); reconnecting with a valid seat token never touches the limiter (Review Focus 4).
- [ ] **Step 2: Run, expect FAIL. Step 3: Implement. Step 4: Run, expect PASS.**
- [ ] **Step 5: Commit** `Join and host-session attempts are limited per address and per room`.

### Task 6: Password hashing at 600,000 rounds, old hashes still load

**Files:** Modify `backend/app/multiplayer/hub.py:53-55,127-129,162-166,366-371,400-404,458-463`; Test `backend/tests/test_room_password.py`

**Interfaces:**
- Produces: `PASSWORD_ROUNDS = 600_000`; `Room.password_rounds: int = 120_000` (the default is what old metadata without the field used); `_hash_password(password: str, salt: bytes, rounds: int) -> bytes`; new rooms store 600,000; `check_password` verifies at the stored rounds and, on success with stored rounds below `PASSWORD_ROUNDS`, re-hashes with a new salt at `PASSWORD_ROUNDS`. Room metadata saves and loads `password_rounds`.

- [ ] **Step 1: Failing tests:** a new room stores 600,000; metadata without `password_rounds` loads, verifies the old password, and afterwards stores 600,000 with a different salt; a wrong password does not upgrade; round-trip of metadata keeps the rounds; a room with no password accepts anything, as today.
- [ ] **Step 2: Run, expect FAIL. Step 3: Implement. Step 4: Run with `tests/test_lobby.py tests/test_games_api.py`, expect PASS.**
- [ ] **Step 5: Commit** `Room passwords: PBKDF2 at 600,000 rounds, upgraded on next use`.

### Task 7: Socket caps, heartbeat, and closing a replaced seat

**Files:** Modify `backend/app/netguard.py`, `backend/app/api/games.py` (`game_socket`), `backend/app/multiplayer/hub.py` (where a seat token is reissued: find with `git grep -n "seat.token =" -- backend/app`); Test `backend/tests/test_socket_caps.py`

**Interfaces:**
- Consumes: `conn.token` (Task 4), `client_address` (Task 2).
- Produces: `netguard.ConnectionCaps(per_key: int)` with `.acquire(key: str) -> bool` and `.release(key: str) -> None`. `Services.caps_seat = ConnectionCaps(4)` keyed `"<game_id>:<seat>"`; `Services.caps_addr = ConnectionCaps(24)` keyed by address. Over the cap: close 4429 "Too many connections".
- Heartbeat: the server sends `{"type":"ping"}` every `PING_EVERY = 25.0` s; a connection that sends nothing (any message, including `{"type":"pong"}`) for `IDLE_CLOSE = 90.0` s is closed 4408. The frontend answers `ping` with `pong`.
- `Hub.close_seat_connections(room: Room, player_id: str, reason: str) -> None` is called wherever a seat token is replaced (reclaim / assign seat); the old sockets close 4403.
- `release` runs in the socket's `finally`, so a dropped phone frees its slot.

- [ ] **Step 1: Failing tests:** a 5th socket for one seat closes 4429 and the first four stay open; closing one lets a new one in; after reclaim the old token's sockets are closed 4403 and the new token connects; a silent connection is closed after `IDLE_CLOSE` (monkeypatched small) while one that answers pings stays; the cap is released when a socket drops without a close frame.
- [ ] **Step 2: Run, expect FAIL. Step 3: Implement backend, then the frontend `pong` with a Vitest case. Step 4: Run, expect PASS.**
- [ ] **Step 5: Commit** `Game sockets: per-seat and per-address caps, heartbeat, replaced seats disconnected`.

### Task 8: Action ids are scoped to the seat

**Files:** Modify `backend/app/api/games.py` (the socket `action` message model near line 1775 and the REST action route), `backend/app/multiplayer/hub.py`, `frontend/src/services/gameSocket.ts`; Test `backend/tests/test_action_ids.py`, `frontend/src/services/gameSocket.test.ts`

**Interfaces:**
- This already exists: `client_action_id` on the REST body (`games.py:246`) and `WsAction` (`games.py:1779`), `GameHub.remember_action(room, client_action_id, outcome)` (`hub.py:481`), `Room.client_actions`, and the journal copy. **Extend it; do not add a second mechanism.** Read all of it before changing anything.
- Change: ids become seat-scoped. `remember_action(room, actor: str, client_action_id: str, outcome: str)` and the lookup key on `(actor, client_action_id)`; the journal call and its loader change with it, and a journal written with the old room-scoped keys still loads (old entries are kept under a key no seat can produce, or dropped: say which in the commit).
- The frontend already sends ids (`gameSocket.ts`); confirm it works on a plain-HTTP LAN page, where `crypto.randomUUID` is unavailable, and fix the generator only if it does not.

- [ ] **Step 1: Tests.** First write these against today's code and record which already pass: send `draw` twice with one id over the socket and over REST: the hand grows by one; two different ids draw twice; an action that errors, retried with the same id, returns the same rejection and the log has one entry. Then the failing ones: the same id from two seats applies for each seat; seat B repeating seat A's id learns nothing about A's outcome; a journal saved before this change loads.
- [ ] **Step 2: Run; the seat-scoping tests FAIL. Step 3: Implement. Step 4: Frontend: a resend after reconnect reuses the id of the unacknowledged action (Vitest; add only if not already covered in `gameSocket.test.ts`). Step 5: Run, expect PASS.**
- [ ] **Step 6: Commit** `Action ids are scoped to the seat`.

### Task 9: Response headers and rendering audit

**Files:** Modify `backend/app/main.py:60-70` and the `FastAPI(...)` constructor; Test `backend/tests/test_security_headers.py`; Create `docs/superpowers/specs/2026-11-21-stage1-audit.md`

**Interfaces:**
- `Strict-Transport-Security: max-age=31536000` is set only when the request scheme is https (direct, or `X-Forwarded-Proto: https` from a trusted proxy per Task 2).
- `/docs`, `/redoc` and `/openapi.json` return 404 unless `settings.dev_tools` is true.
- The existing `CSP` constant keeps `default-src 'self'`; the test pins that it contains no `unsafe-eval` and no third-party host.

- [ ] **Step 1: Failing tests** for the three points above (HSTS absent on http, present on https; docs 404 by default and 200 with `dev_tools`; CSP assertions).
- [ ] **Step 2: Run, expect FAIL. Step 3: Implement. Step 4: Run, expect PASS.**
- [ ] **Step 5: Audit, written to the audit file with the commands and their output:** `git grep -n "innerHTML\|dangerouslySetInnerHTML\|insertAdjacentHTML\|document.write" -- frontend/src` (0 hits for the first two on 2026-11-21; record the full result); where player names, chat, deck names and notes are logged on the server, confirm control characters are stripped (`app/textutil.py`), and add a test with a name containing `\n` and `\x1b` if none exists.
- [ ] **Step 6: Commit** `HSTS on https, API docs off outside development, rendering and log audit`.

### Task 10: Stage gate

**Files:** Modify `docs/LAN_PLAY.md` (host tools need the launcher; seat links; the private-network option A for remote friends), `docs/CURRENT_STATE.md` (one batch entry), `docs/superpowers/specs/2026-11-21-stage1-audit.md`

- [ ] **Step 1:** From `backend/`: `.venv/Scripts/ruff check . && .venv/Scripts/mypy app tools && .venv/Scripts/python -m pytest -n 8 -q`. From `frontend/`: `npm run typecheck && npm test`. Paste the summaries into the audit file.
- [ ] **Step 2:** `.venv/Scripts/pip install bandit pip-audit` (dev only, not added to runtime dependencies), then `bandit -r app -q` and `pip-audit`; in `frontend/`, `npm audit`. Every finding is listed in the audit file with "fixed in <commit>" or "accepted because …".
- [ ] **Step 3:** Walk the 13-point Review gate in the spec; write one line per point in the audit file: the test or commit that satisfies it, or "not applicable" with the reason.
- [ ] **Step 4:** Manual check on two devices on the LAN: host opens from the launcher and has host tools; a phone joins by code, plays a land, sleeps, wakes and reconnects; a second browser on the host machine has no host tools; a reclaim link moves the seat and the old tab is told its seat is no longer valid. Record what was seen.
- [ ] **Step 5:** Run the `security-review` skill on the branch and dispatch one fresh reviewer with the spec, this plan and the diff. Fix or answer every finding.
- [ ] **Step 6: Commit** the docs and audit file. Do not merge to `master` until the owner has read the audit file.

# Internet play for a remote pod: hardening, invite link, turn clock

Date: 2026-11-21. Status: draft for approval.

## Intent

Fyodor is a LAN tabletop for a trusted pod. The owner wants the same pod to play when its members are not on one
network, and may later open it to strangers as a public service. The owner asked for as much risk removed as possible.

This design covers three stages, in order. Each ships on its own.

1. **Hardening**: make the server safe to reach from outside the LAN.
2. **Invite link**: the host presses one button and sends friends an HTTPS link.
3. **Turn clock**: an optional, server-owned clock.

## Goals

- A friend on another network joins with a link and a room code, over HTTPS, without installing anything.
- The host's home IP address is not shown to players.
- A remote player can never get host powers, read hidden information, or act for another seat.
- A LAN night works exactly as it does today, with no new step.
- Every stage passes the review gate below before it merges.

## Non-goals

- Accounts, login, matchmaking, a public lobby directory, a central hosted server. These wait for a decision to go
  public and get their own design.
- Protecting players from the host. The host's computer runs the engine and holds every library; that stays true.
- Cryptographic shuffles (commit-reveal, mental poker).

## Anti-goals

- Any change that makes a LAN-only night need internet, an account or a certificate.
- A second authentication or validation path beside the existing one. Extend `authorize` and the hub; do not build a
  parallel system.
- A clock that makes a player lose the game by timing out.

## Constraints

- Project policies in `.claude/skills/fyodor-game-development/SKILL.md` hold: server authoritative, hidden information
  never leaks (including by omission), new state fields have defaults so old saves load, every new behaviour has a
  scenario test, `replay_matches` and a save/load round trip.
- Windows is the main host platform; the app also ships as a PyInstaller bundle and runs offline.
- No new runtime dependency unless it is named here.

## How it works today (verified in the code on 2026-11-21)

- `backend/app/api/deps.py`: `is_local_request` treats a loopback peer as the host computer. When the peer is loopback
  and `X-Forwarded-For` is present it trusts the **first** entry. `is_local_request` / `require_local` are used about
  100 times across 18 files in `backend/app/api/`.
- `backend/app/multiplayer/hub.py`: each room already has a `host_token` (`secrets.token_urlsafe(24)`), seat tokens,
  spectator tokens, constant-time compares, a 6-character room code, and an optional password hashed with
  PBKDF2-HMAC-SHA256 at 120,000 rounds.
- `backend/app/api/games.py` `game_socket`: the token arrives in the WebSocket **query string**; there is no Origin
  check; a message size cap (`MAX_WS_MESSAGE`) and a per-connection rate limiter already exist.
- Seat tokens are kept in browser `localStorage`.
- The server speaks plain HTTP. `launcher.py` binds `0.0.0.0` unless `--local`.
- No rate limit was found on room-code or password attempts. The builder must confirm this before adding one.

## Approaches considered

| | A. Private network (Tailscale/ZeroTier) | B. Built-in invite link (tunnel) | C. Central server |
|---|---|---|---|
| Friends | install software once | click a link | open a website |
| Exposure | pod only | anyone holding the link | the whole internet |
| New code | none beyond hardening | launcher integration | hosting, accounts, moderation |

**Chosen by the owner: hardening, then B, then the turn clock.** A is documented as the no-code option that works as
soon as hardening lands. C is deferred. B was chosen because friends need nothing installed and it gives real HTTPS and
hides the home address; its cost is a dependency on a third-party tunnel service.

## Stage 1: Hardening

### 1.1 Host identity (replaces "loopback means host")

- At startup the server creates a **host secret** (`secrets.token_urlsafe(32)`), kept in memory and in a file in the
  data directory readable only by the current user. The launcher opens the host's browser with the secret in the URL
  **fragment** (`#host=...`, never sent to a server or logged); the page moves it to a cookie and clears the fragment.
- The cookie is `HttpOnly; SameSite=Strict`, plus `Secure` and the `__Host-` prefix when served over HTTPS.
- `is_local_request` becomes `is_host_request`: true only when the host cookie matches (constant-time). The peer address
  is no longer consulted. All existing call sites keep their meaning ("only the host computer") through this one
  function; no call site grows its own check.
- A tunnelled request can never be host by address. The host uses the table through `http://127.0.0.1`, as today.
- `--local` mode keeps working: same secret, same cookie.
- **Open, the owner's to decide:** whether the secret is new on every start (safer; the launcher's in-app restart and
  its "already serving, reopen the table" path must hand the browser the new secret) or kept across restarts
  (friendlier; a long-lived secret on disk). The plan assumes new on every start until the owner says otherwise.
- Recovery for a browser without the cookie (second browser, cleared cookies): open Fyodor from the launcher again.

### 1.2 Forwarded addresses

- `X-Forwarded-For` is ignored unless `FYODOR_TRUSTED_PROXIES` (default empty) lists the peer. When trusted, the
  **rightmost** untrusted entry is the client address. The address is used for rate limiting and logs only, never for
  authority. The dev proxy on port 5173 is covered by setting the variable in development.

### 1.3 Origin and cross-site requests

- WebSocket upgrade and every state-changing REST call check `Origin` against an exact allowlist: the server's own
  origins (loopback, LAN address, the active invite-link hostname) and the configured dev origins. A missing or foreign
  Origin is refused. Non-browser clients (tests, bots) send the expected Origin or use a test override.
- On the LAN port the allowlist is "Origin equals the request's own Host", so any interface address or the computer's
  name works and a DHCP change breaks nothing. To keep DNS-rebinding protection, the `Host` itself must be an IP
  literal, `localhost`, the computer's own hostname, or the active invite hostname; any other Host is refused.
  (Author's call.)

### 1.4 Tokens out of URLs

- The WebSocket authenticates in its **first message** (`{"type":"auth","token":...}`) with a short deadline; nothing is
  sent before it succeeds. The query-string token is accepted for one release on LAN-only tables for old tabs, then
  removed. Invite links carry the room code, never a seat or host token. Reclaim-seat links keep working but put the
  token in the fragment.
- Seat tokens stay in `localStorage` for this design (a seat is not an account; moving to cookies belongs with
  accounts). The mitigation here is a strict Content-Security-Policy and an audit that no user text (names, chat, deck
  names, notes) reaches `innerHTML`.

### 1.5 Brute force and abuse limits

- Room code and password attempts: limited per room **and** per client address (defaults taken from Cockatrice's
  server: 5 failures per 15 minutes per address; the per-room cap is the builder's call). Failures answer the same for
  "no such room" and "wrong password".
- Password hashing: PBKDF2-HMAC-SHA256 at 600,000 rounds (OWASP). Old hashes verify at their stored round count and are
  re-hashed on next success; the round count is stored with the hash so old saves load.
- Tables reachable through the invite link **require** a password. Room codes for those tables are 10 characters.
- Sockets: keep the size cap and message rate limit; add connections per seat and per address, a heartbeat with idle
  close, and close every socket of a seat when its token is replaced.
- Action ids already exist (`client_action_id`, `GameHub.remember_action`: room-scoped, outcome string). Stage 1 makes
  them seat-scoped, so one seat cannot collide with or probe another seat's ids, and confirms a repeat applies
  nothing. No second mechanism.

### 1.6 Response headers

- `Content-Security-Policy` (self only, matching today's "no third-party scripts"), `X-Content-Type-Options: nosniff`,
  `Referrer-Policy: no-referrer`, and `Strict-Transport-Security` on HTTPS responses only. API docs endpoints are off
  outside development.

## Stage 2: Invite link

- **What the host sees:** a table's host tools gain **Invite over the internet**. Pressing it asks for a table password
  if none is set, starts the tunnel, and shows one link to copy, with **Stop sharing**. The top bar shows that the
  table is shared. Stopping, or closing Fyodor, ends the link.
- **How:** the launcher runs a tunnel client as a child process that makes an outbound connection and gives the table a
  public HTTPS hostname. Provider: Cloudflare Tunnel (`cloudflared`) quick tunnel as first choice, because it needs no
  account and no open port. The builder must verify, before building, the provider's current terms and limits for this
  use and that WebSockets work through it; if they do not fit, Tailscale Funnel is the fallback and the choice returns
  to the owner.
- **Supply chain:** the tunnel binary is not bundled blindly. A pinned version is downloaded on first use from the
  provider's official release, verified against a SHA-256 pinned in the repo, and stored in the data directory. No
  download happens unless the host presses the button. `allow_network=False` disables the feature.
- **What is reachable through the tunnel:** only what a remote player needs: the table interface, join, the game
  socket, card data and art. Host-only routes are already closed by 1.1; in addition, requests arriving through the
  tunnel are marked (the tunnel connects to a second local port) and host-only routes refuse them outright, so a stolen
  host cookie is useless from outside.
- **LAN discovery** is unchanged and never advertises the invite link.
- **Sharing is per table (author's call).** The tunnel exposes the whole process, so the tunnel port serves only
  tables marked shared: any other room answers as "no such room" there. Pressing Invite does not replace the table's
  6-character LAN code; it adds a separate 10-character invite code that is the only code accepted on the tunnel
  port. `shared` and the invite code are saved with the room, default off, so old room metadata loads.
- **Client address behind the tunnel (author's call).** Requests on the tunnel port come from the local tunnel
  client, so that port, and only that port, takes the client address from the provider's own header
  (`CF-Connecting-IP` for Cloudflare). Without this, five wrong guesses by anyone would lock out the whole pod. The
  LAN port never reads that header.
- Documented in `docs/LAN_PLAY.md` with option A (private network) beside it.

## Stage 3: Turn clock

Reverses the earlier note in `docs/UI_REFERENCE_STUDY.md` ("Avoid: Turn clocks"), at the owner's request. Off by
default, so pod nights are unchanged.

- **Setting (host, lobby and table settings, saved with the game):** Off / On, a bank per player (default 25 minutes),
  a buffer per decision (default 30 seconds, not charged), and what happens at zero: **Act for the player** (default)
  or **Only show it** (the clock reads 0:00 and nothing is done; for pods that want pressure without enforcement).
- **Who is charged:** only the player the server is waiting on (priority or a pending decision). Nobody is charged
  while the server resolves, during another player's choices, while automation is paused, or while a player is
  disconnected within a grace period (default 2 minutes, host can extend).
- **At zero:** the server acts for the player with the safest legal default: pass priority; decline optional choices;
  take the first legal option where a choice is required; declare no attackers or blockers. It never concedes or
  eliminates. The log says the clock acted. The host can add time or turn the clock off at any moment.
- **After zero:** the bank stays empty; each later decision still gets its full buffer, then the server acts.
- **Several players at once** (mulligans, simultaneous choices): each player the server is waiting on is charged
  independently.
- **Authority:** the server owns the clock and uses its own monotonic time. Client timestamps are ignored. Clients get
  the remaining time and the server's send time and draw the countdown locally. Lag forgiveness is the per-decision
  buffer; no per-move lag model.
- **Privacy:** the clock adds no new waiting. It runs only while the engine already waits on a player, exactly as the
  table already shows who it is waiting on, so it reveals nothing new and changes no pacing. Other players see whose
  clock is running and each bank, never what the decision is.
- **State:** clock fields live in game state with defaults (old saves load with the clock off), survive save/load, and
  are excluded from undo so undoing does not refund time.
- **Sandbox, practice and solo tables:** the clock is not offered.
- **Left to the builder:** the countdown's look (follow `fyodor-ui-design`), exact field names, and where the timer
  task runs, provided a timeout and a player action can never both apply (one lock or queue per game).

## Review gate (every stage)

Drawn from the research (OWASP cheat sheets; studies of AI-written code). A stage merges only when each applies or is
marked not applicable with a reason.

1. Every action checks server-side that this connection holds this seat in this game; no client-supplied player, seat
   or game id is trusted.
2. Hidden information is filtered per viewer on every new path, reconnects and spectators included.
3. No token in a URL query string or a log line.
4. Tokens come from `secrets`, are compared with `hmac.compare_digest`, and can be revoked.
5. No hardcoded or default secret; startup fails if a required secret is missing.
6. Every new payload is validated by a strict schema with bounded lengths and numbers.
7. User text is never rendered as HTML; control characters are stripped before logging.
8. No new `except Exception`, bare `except` or silent fallback; auth and rules checks fail closed.
9. Every new dependency or downloaded binary exists, is the intended one, and is pinned by version and hash.
10. Tests are written from the requirement before the code, and include the negative cases: wrong seat, replaced
    token, foreign Origin, forged `X-Forwarded-For`, oversized message, repeated action id, timeout racing an action.
11. `ruff`, `mypy`, the full `pytest` run and the frontend typecheck and tests pass, run by the reviewer, not taken on
    report. `bandit` and `pip-audit` / `npm audit` findings are read and answered.
12. An independent review of the stage (the `security-review` skill plus a fresh reviewer) before merge.
13. No duplicated system: one host check, one token check, one rate limiter.

## Risks that remain

- The tunnel provider can change terms, limit, or go down; internet play then stops until the fallback is used. LAN
  play is unaffected.
- Anyone holding the link and the password can join; the host's kick and seat tools are the remedy.
- The host sees everything. Unchanged.
- A browser compromise on a player's machine exposes that player's seat token.
- Serving Magic card images to the public is a legal question that grows with a public service; it is out of scope
  here and must be answered before stage C.

## Later (not designed here)

Accounts, matchmaking, a lobby directory, moderation and a central server. Stage 1 keeps the door open: one function
decides "is host", one decides "which seat", so an account can attach to a seat later without a second path.

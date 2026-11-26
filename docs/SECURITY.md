# Security model

Fyodor runs on a trusted home or LAN network and has no accounts, cloud services or telemetry. LAN play never needs the
Internet. The one exception is opt-in: a host who presses **Invite over the internet** shares one table through a Cloudflare
quick tunnel (below and `docs/LAN_PLAY.md`); nothing is downloaded or started until then, and `FYODOR_ALLOW_NETWORK=0` turns it
off. These are the protections in place.

## Network exposure

- By default the server binds to `127.0.0.1`. LAN exposure requires `FYODOR_HOST=0.0.0.0`
  (or `scripts/start.sh --lan`).
- **Hot-seat (local) games** and host-only endpoints (create and close games, saves, the deck library, pod-stat edits,
  packages, diagnostics, asset deletion, LAN info, sharing a table) answer only the host's browser: the window the launcher
  opened, which holds the host secret in its cookie (`app/hostauth.py`). Neither the peer address nor any forwarded header
  makes a request the host's. `X-Forwarded-For` is read only for rate limits and logs, and only from a proxy listed in
  `FYODOR_TRUSTED_PROXIES` (none by default); the web server's own proxy-header handling is off.
- **LAN games** require a seat token. Tokens are random (`secrets.token_urlsafe(24)`),
  compared in constant time, and issued only after a valid room code and optional password.
  Passwords are stored as PBKDF2-SHA256 hashes, checked on a thread pool of their own. Wrong room codes or passwords are
  limited to 5 per client address in 15 minutes (counted before the password is checked; a right password gives the try
  back), and a room that many addresses guessed at wrongly refuses further wrong guesses for a while (the right password
  still gets in on the LAN).
- **Invite over the internet** (opt-in, per table): the tunnel arrives on a port of its own, which serves only a fixed list
  of player routes for the tables the host shared, never host tools or the room listing, and only for the invite's own
  hostname and Origin. A shared table always has a password (8 to 100 characters when set for sharing). Rate limits there
  are keyed by Cloudflare's `CF-Connecting-IP` (an IPv6 address by its /64), read only on that port; once a shared room is
  blocked for wrong guesses, joins through the link are refused before any password is hashed. Large request bodies are
  allowed there only to a seat of the shared table. The `cloudflared` program is pinned by version and SHA-256, checked
  after download and before every start.

- In a LAN game each connection can only act as its own seat. Spectators cannot act.
- Anyone who can reach the server can browse cards. LAN players bring decks through their
  seat in the lobby (parsed on the host as data), not through the host's library.
- Host-only game actions (start, remove player, restart, table playmat, force-close a response
  check, restore a snapshot) are checked on the server against the host's seat.
- Clients can't forge state restores: `restore_state` is accepted only from the server's own
  snapshot and history endpoints.

## Hidden information

- The server builds a separate sanitized view for each connection. It never broadcasts
  the full state and relies on the client to hide cards.
- Hidden cards become placeholders with no printing id, name, note or face. Libraries are
  sent as a count plus only the cards that viewer can see right now (no memory of past sightings).
- Library instance ids are re-keyed on every shuffle, so a known card can't be tracked
  through one.
- Log entries name a card only for viewers who could see it at that moment.
- The all-hands ("open table") view exists only for hot-seat games on one computer. In a LAN
  game the host computer, asking without a seat, gets the spectator view like anyone else.
  The host still stores every game on its disk (saves, autosaves, backups, diagnostics with
  private data), so the pod trusts whoever runs the host, as with any self-hosted table.
- Randomness (shuffles, dice, coins, new ids) comes from `secrets.SystemRandom` on the
  host. Client-supplied resolution data is discarded.
- `tests/test_views.py` and `tests/test_games_api.py` check every viewer's serialized
  view for leaks after every step of mixed game sequences.

## Input handling

- Every REST body and WebSocket message is validated by pydantic models. Game actions are
  a closed discriminated union with bounded sizes, id patterns and `extra="forbid"`.
- WebSocket messages over 64 KB are rejected, and each connection is rate-limited.
- User text (names, notes, chat, deck names, counter names) is normalized, stripped of
  control and bidi-override characters, and length-limited. The frontend renders all
  user text as text, never as HTML.
- Deck text is only parsed as data, with a 200,000-character / 2,000-line limit.
- Save files are decompressed with a size cap, format- and version-checked, then
  validated against the game-state schema before use.

## Files

- Images are served only from `/api/images/{uuid}`. The id must match a strict UUID
  pattern and size/face come from fixed enums, so paths cannot be influenced beyond a
  validated UUID.
- **Custom images (assets)** are identified by their content, not their name or extension.
  Only real PNG, JPEG or WEBP files within 20 MB and 8192×8192 are accepted, checked from the
  magic bytes and header. SVG, GIF, executables and disguised files are rejected. Files are
  stored as `data/assets/<sha256>.<ext>` and served only by opaque asset id; no client-supplied
  path is ever used. LAN players may upload only sleeves and playmats, rate-limited, through
  their seat.
- **Game packages** (`.fyodor.zip`) are read by fixed member names only; nothing is extracted
  by a name taken from the archive. Sizes are bounded before decompression, every image is
  checksum-checked and content-sniffed, macros are re-validated, and the save is migrated and
  validated before anything is written.
- **Custom actions (macros)** are declarative JSON from a closed list of primitives (`extra`
  fields forbidden, at most 20 steps). The server expands them into ordinary actions, and they
  go through the same permission and hidden-information checks. Nothing in a deck, card,
  macro or package is ever executed as code.
- **Diagnostics** are a local download. They contain no hands, libraries, decklists or notes
  unless the host explicitly opts in; nothing is sent anywhere.
- The built frontend is served from its `dist` directory by Starlette's `StaticFiles`,
  which rejects traversal. No other filesystem path is exposed.
- Responses carry `Content-Security-Policy` (same-origin only), `X-Content-Type-Options`,
  `X-Frame-Options: DENY` and `Referrer-Policy: no-referrer`.

## Dependencies

The backend depends on FastAPI, uvicorn, pydantic and httpx. The frontend depends on
React and zustand. Keep them current with `pip install -U -e '.[dev]'` and `npm update`.

# Security model

Fyodor runs on a trusted home or LAN network. It never needs the Internet during play
and has no accounts, cloud services or telemetry. These are the protections in place.

## Network exposure

- By default the server binds to `127.0.0.1`. LAN exposure requires `FYODOR_HOST=0.0.0.0`.
- **Hot-seat (local) games** and host-only endpoints (create/close games, list/load/delete
  saves, LAN info) accept only loopback clients. Requests relayed by the dev proxy are
  judged by their `X-Forwarded-For` address. That header is only trusted when the direct
  peer is loopback.
- **LAN games** require a seat token. Tokens are random (`secrets.token_urlsafe(24)`),
  compared in constant time, and issued only after a valid room code and optional password.
  Passwords are stored as PBKDF2-SHA256 hashes. Failed join attempts are rate-limited to
  10 per minute per client address.
- In a LAN game each connection can only act as its own seat. Spectators cannot act.
- Anyone who can reach the server can browse cards and manage decks. That is intended for
  a shared table; saves and game management remain host-only.

## Hidden information

- The server builds a separate sanitized view for each connection. It never broadcasts
  the full state and relies on the client to hide cards.
- Hidden cards become placeholders with no printing id, name, note or face. Libraries are
  sent as a count plus only the cards that viewer knows.
- Library instance ids are re-keyed on every shuffle, so a known card can't be tracked
  through one.
- Log entries name a card only for viewers who could see it at that moment.
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
- The built frontend is served from its `dist` directory by Starlette's `StaticFiles`,
  which rejects traversal. No other filesystem path is exposed.
- Responses carry `Content-Security-Policy` (same-origin only), `X-Content-Type-Options`,
  `X-Frame-Options: DENY` and `Referrer-Policy: no-referrer`.

## Dependencies

The backend depends on FastAPI, uvicorn, pydantic and httpx. The frontend depends on
React and zustand. Keep them current with `pip install -U -e '.[dev]'` and `npm update`.

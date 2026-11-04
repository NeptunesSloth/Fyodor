# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

One private Commander pod: four friends at game night, **each on their own computer**, connected over the
LAN to one host computer. Most of the time all four know Commander well; the pod occasionally brings in
new players, so the experience must also work for someone still learning the format.

## Product Purpose

Fyodor is an offline-first digital tabletop for **Commander only**. It lets the pod play full Commander
games together without the Internet once the card data is downloaded: zones, cards, counters, life,
commander damage, the stack, turns, logs, undo, saves and LAN play, with a rules engine that automates
normal play for the cards it supports and a manual tabletop for everything else.

Success: four people, four Commander decks, one LAN table, and nothing ever prevents the pod from
finishing a game.

## Positioning

The combination no single existing product offers: **Tabletop Simulator-style physical freedom** on top
of **MTG Arena-level rules automation**, with **Master Duel-style response/priority clarity** and a
**manual override that is always available**. It is private and offline — built for one trusted pod, not
a public platform.

## Operating Context

- Game night at one location: a host computer runs the server; each player joins from their own
  computer over the LAN with a room code. Every new game is a LAN night (a host alone at the table is solo
  testing); hot-seat tables from older saves still load and play.
- Decks come from Moxfield, Archidekt (first-class), MTGGoldfish, Arena or plain text; the pod keeps a
  deck library on the host.
- Card data and images come from Scryfall and are cached locally; cards without cached art render as
  readable text cards, so play never depends on images.
- Long sessions with several games in a row; results are recorded in pod stats.
- The official Comprehensive Rules are fetched and indexed at development time; the running app never
  needs the Internet.

## Capabilities and Constraints

- **Commander only.** Card and mechanic automation counts only Commander-legal cards. No other formats,
  drafts, rankings, matchmaking, accounts, cloud saves or telemetry.
- **The server is authoritative.** Every change is a validated action; each device receives only what its
  player may see. **Hidden information never leaks.**
- **Rules engine:** deterministic and researched from the current Comprehensive Rules; no runtime AI
  judge; card text is never executed. Unsupported behavior falls back to manual play — wrong automation
  is worse than manual. Coverage is reported per card (FULL / PARTIAL / REVIEW / MANUAL).
- **Manual tabletop freedom is never removed:** free positioning, drag and drop between zones, tokens,
  counters, notes, dice, macros, undo/redo and saves with full history.
- **Two renderers:** a 2D table and a three.js 3D table render the same per-viewer state; rules behavior
  never depends on the renderer, and the 2D table remains a first-class fallback.
- **Frontend stack (existing):** React 19, TypeScript, Vite, zustand, three.js; bundled fonts (Inter,
  Cinzel) so everything works offline. Backend: Python/FastAPI with WebSockets and SQLite.
- Terminology follows Magic's official terms (priority, the stack, commander damage, command zone,
  mulligan …).

## Evidence on Hand

- Real play and testing on the pod's own decks; sample deck lists in `docs/sample-decks/`.
- Planning and design records in `docs/` (architecture, rules coverage, automation UX, 3D direction,
  game-night flow, the UI redesign brief).
- No testimonials, external users, benchmarks or press exist; future work must not invent any.

## Product Principles

1. **Never block the game.** Automation helps, but the manual table always lets the pod finish.
2. **Correct or manual.** Automate only what is complete and tested; otherwise hand it to the players.
3. **Privacy is absolute.** Private information reaches only the player allowed to see it.
4. **Fast for veterans, clear for newcomers.** Automation stays quick and unobtrusive for experienced
   players, while prompts and the reason behind a game state stay understandable for a new player.
5. **Offline and reliable.** Game night survives crashes, reconnects and no Internet.

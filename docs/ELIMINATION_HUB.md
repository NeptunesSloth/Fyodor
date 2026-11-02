# The elimination activity hub (core built)

Requested 2026-10-03. Spectator side activities (PiP Practice Table, next-game queue, reactions, damage
sandbox, fake-point predictions) extend this hub later: `SPECTATOR_ACTIVITIES_MILESTONE.md`.

## What is built

- **Hub** (`frontend/src/game/Eliminated.tsx`): after the ELIMINATED moment, Practice table, Opening hands,
  Deck Lab, Keep watching, and links to Pod stats and the Card browser (new tabs, so the live seat stays put).
  The "You're out · Things to do" pill brings the hub back.
- **Spectate:** the eliminated seat keeps its ordinary per-seat view, which shows other players exactly what a
  spectator sees (`tests/test_elimination_hub.py` checks REST and WebSocket payloads).
- **Major public events** (`backend/app/multiplayer/elimination.py`, `Pulse`): "Bob was eliminated." / "conceded." /
  "left the game.", "Final two players remain: …", "Alice wins." (from the recorded result only). Built from public
  facts, each announced once per game, kept in memory (never saved), sent in every view as `game.events`. The live
  table shows them as brief toasts (`MajorNotices.tsx`; the result is left to the result spotlight, your own
  departure to your ELIMINATED moment); the practice pill shows them too.
- **Practice Table** (`backend/app/api/practice.py`, `POST/DELETE /api/games/{id}/practice`): a separate one-seat
  sandbox room built only from the player's own deck (guided opening hand, test cards allowed, rules off), with its
  own seat token. Never listed, joinable by code, journaled, autosaved or recorded in pod stats; no host. Only for a
  player who is out while the game goes on; resumed if they have one. `PracticeBar.tsx` keeps the live seat
  connected, shows the live turn and events, has **Return to live game**, and brings the player back (putting the
  practice table away) when the live game has a result or the pod moves on.
- **Opening Hand Simulator:** Draw 7 / Mulligan / Draw a card / Reset, in the browser.
- **Deck Lab** (`POST /api/games/{id}/deck-lab`): a copy of the deck brought to this game. On the host computer it is
  a new library deck opened in the deck editor; on a guest's computer it is the list, edited in place and saved to that
  browser's My decks. The match deck and its library original are never changed; the next deck is chosen in the lobby.

- **Dice & toys** (`frontend/src/game/TableToys.tsx`, logic in `toys.ts`): a link in the hub and an entry in the
  spectators' "Watching · Things to do" plaque (a `SideActivity`). A **dice tray**: d4, d6, d8, d10, d12, d20 and a coin,
  several at once (3d6 + d20, up to 12 dice), each die and the total shown, the last ten rolls kept in this browser with
  Clear and Reroll; Enter rolls, Esc closes. The dice are the table's own: with the 3D table available it is a small
  three.js tray thrown with the live table's real dice (`table3d/dice.ts`, cannon-es: `table3d/toyTray.ts`, loaded only
  then, disposed on close, drawing nothing once the dice rest, with their own clatter); without WebGL, on low graphics
  or if that fails, it is the drawn dice (`game/DieGlyph.tsx`, as on the 2D table without WebGL).
  Reduced motion and the animation speed apply to both. Two toys: a **random player** over the seated players' public
  names (alphabetical, never seat order, labelled "just for fun": it never sets the turn order) and a **tally**. All
  local: numbers from `crypto.getRandomValues`, nothing sent to the server, the live game's state, log, dice and sounds
  untouched (`toys.test.ts` spies on `fetch` and the game's WebSocket).

Not built yet: a Game Log link, and Deck Lab's compare view; a guest's Deck Lab is a plain list
(the host computer's deck editor shows card types and the mana curve).

**Goal:** a player knocked out early in a Commander game still has something fun or useful to do
while their friends finish. Elimination must **not** mean "you lost, sit in spectator mode until
everyone else finishes". Keep it lightweight. This is **not** a separate giant game mode.

This sits next to the end-of-game scenes (`3D_DIRECTION.md` §7a). After the short **ELIMINATED** scene
there, the eliminated player sees a compact activity hub instead of only Spectate / Leave game.

## Build order

Start with these four; they provide most of the value:

1. Spectate
2. Practice Table
3. Opening Hand Simulator
4. Deck Lab

Then the smaller links: Game Log, Pod Stats, Card Browser, Dice / table toys, Leave Game.

## Primary options

### Spectate

Watch the remaining game: free camera / board inspection, the stack and public game log, life and
commander damage, public zones, and an easy return to the normal spectator view.

**Critical:** reveal nothing hidden from players still in the game (hands, libraries, private
choices). An eliminated player is an ordinary public-information spectator. The server already builds
a per-viewer view (`build_view(state, viewer)` with `SPECTATOR`, `ARCHITECTURE.md`); the eliminated
player must get exactly that public view, never `OMNISCIENT`.

### Practice Table

A **private, local sandbox** with the eliminated player's own deck while the real game continues. It
is not a second network game and must not affect the active game. Features: shuffle, draw,
mulligan, play cards freely, reset the deck, spawn tokens and counters, test opening sequences,
goldfish combos, undo and reset freely. (The existing solo tools in `MACROS_AND_SOLO.md` are a likely
base.)

### Opening Hand Simulator

Extremely fast: **[DRAW 7] [MULLIGAN] [RESET]**. It uses the player's deck and doesn't affect the
ongoing match.

### Deck Lab

Inspect and modify a **copy** of the deck for the next game. It never changes the deck tied to the
running match. Deck Lab only edits and saves deck revisions; **choosing** the deck for the next game
still happens in the lobby, like everyone else's (no separate deck-change screen after the match).
Actions: view the deck list, search cards, change the next-game version, save as a new revision,
inspect the mana curve and card types, compare changes.

## Staying connected to the live game

While the player is in Practice Table or Deck Lab, show a small, unobtrusive live-game indicator
with a **[RETURN TO LIVE GAME]** button. Surface only major public events, without spam, for
example:

- "Player 3 is attacking Player 4"
- "Stack: 2 objects"
- "Player 4 eliminated"
- "Final two players remain"

**When the main game ends** while the player is in another activity, show the normal final result
("PLAYER 3 WINS") with the normal post-game choices: **[REMATCH — SAME DECKS] [RETURN TO LOBBY]
[VIEW FINAL BOARD]** (`3D_DIRECTION.md` §7a, post-game flow). Nobody misses the end of the pod game
because they were practicing. A player who wants another deck changes it after returning to the lobby.

The game-night milestone (`GAME_NIGHT_FLOW.md` §7) builds the return-to-live-game path, the major-event
notifications ("Player 3 eliminated.", "Final two players remain.", "Player 4 wins.") and the result
flow reaching players in a side activity.

## Privacy (extremely important)

Elimination does not grant judge or spectator omniscience. An eliminated player must **not** gain
access to:

- opponents' hands;
- library identities;
- private search results;
- face-down identities;
- private decisions;
- hidden card metadata;
- private WebSocket payloads.

Only normal public information is visible. Add leak tests like the existing per-viewer ones,
including an eliminated seat's connection.

## Architecture

Practice Table, the Opening Hand Simulator and Deck Lab are **isolated from the live authoritative
game state**. They must not:

- add actions to the live game's history;
- change the live game's revision;
- trigger rules events in the live game;
- affect saves of the active match;
- interfere with reconnect or spectator state.

A practice table is its own private state (client-local or a separate server-side session owned by
that player), never part of the live `GameState`. Deck Lab writes a new deck revision, never the
deck snapshot the running game was created from.

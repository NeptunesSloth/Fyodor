# Plan: the elimination activity hub (not started)

Requested 2026-10-03, for later. Nothing here is built yet.

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
still happens in the lobby, like everyone else's (no separate deck-change screen after the match). Actions: view the deck list, search cards, change the next-game version, save as a new
revision, inspect the mana curve and card types, compare changes.

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

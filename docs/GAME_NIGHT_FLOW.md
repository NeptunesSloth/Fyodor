# Milestone plan: game night / match flow (not started)

Requested 2026-10-03. **Build it after the core rules engine and the primary tabletop functionality
are mature.** Nothing here is built yet.

**Goal:** several Commander games with the same pod feel like one continuous game night. Build these
systems together:

1. Persistent pod lobby
2. Turn order: the pod rule (d20 for game 1, then the previous winner goes last)
3. Pre-game intro
4. Group concession / end game
5. Winner spotlight
6. Rematch vote
7. Spectator rejoin

Don't duplicate what exists. Preserve the authoritative server, the privacy model, game history and
pod stats (`POD_STATS.md`).

Related plans: the end-of-game scenes and post-game flow (`3D_DIRECTION.md` §7a) and the elimination
activity hub (`ELIMINATION_HUB.md`). This milestone supersedes the simple Rematch button of §7a with the
rematch vote (6).

**What exists today** (checked 2026-10-03; build on it):

- LAN rooms and a lobby with seats, **Choose deck** and **Ready** (`LAN_PLAY.md`, `api/games.py`).
- A random first player, already chosen on the server with `secrets.randbelow` when the lobby starts
  (`StartIn.first_player = "random"`, `factory.new_game(first_player=…)`), or a seat index.
- Instant-speed concede (wave 3) and recorded results in pod stats, entered by hand
  (`POD_STATS.md`: single/multiple winners, draw, no result).

## 1. Persistent pod lobby

The pod room survives across games. Players never recreate the room, reopen invite links, rejoin
seats, re-enter names or reconfigure everything after a match.

Preserve between games where appropriate: players, seats, player colors, profiles, the lobby host,
selected decks, commanders, deck privacy, the mulligan policy, table preferences and player settings.

After a game the choices are **Rematch — same decks** or **Return to lobby** (decided by the rematch
vote, 6). Returning to the lobby keeps each player's previous deck selected; players change decks with
the **existing** lobby deck-selection flow. There is no second deck-selection interface.

## 2. Turn order: the pod rule (d20, then winner goes last)

Our pod's convention is the **preferred default** for this setup. It becomes a configurable lobby rule
later (other options such as plain random, rotating or host-chosen can sit beside it). While the pod
rule is on, the generic random-first-player logic is **not** used.

**Game 1 of a pod session**

- Every player rolls a **server-authoritative d20**; clients never roll or decide anything themselves.
- The rolls are shown visibly on the table.
- Highest roll goes first; the order follows the rolls from highest to lowest.
- Ties reroll **only among the tied players** (as often as needed) to settle their places.
- The resulting order is the turn order for the first game.

**Every later game**

- The **winner of the previous game goes last** in turn order.
- The other players keep their relative order, unless the host changes it.
- The final order is recorded in the new game's metadata.

Example:

```
Game 1:  A → B → C → D     C wins
Game 2:  A → B → D → C     D wins
Game 3:  A → B → C → D
```

(A game with no winner — a draw or no result — keeps the previous order unless the host changes it;
confirm this before building.)

**UI.** Before each new game, show a compact turn-order preview:

```
TURN ORDER
1. Player A
2. Player B
3. Player D
4. Player C — Previous winner
```

For Game 1, the preview shows the d20 rolls (and any tie rerolls) that set the order.

**Records.** Each game stores its turn order, and for Game 1 the rolls, in its metadata.

**What exists today:** a server-side random first player (`secrets.randbelow`) and a seat-index option.
The pod rule replaces it when enabled; the engine's turn order must follow the recorded order, not
just the seats.

## 3. Pre-game intro

A very short Commander introduction before gameplay, roughly **2–4 seconds**:

```
PLAYER 1  Atraxa, Praetors' Voice
PLAYER 2  Krenko, Mob Boss
PLAYER 3  Muldrotha, the Gravetide
PLAYER 4  Yuriko, the Tiger's Shadow
TURN ORDER  (the preview from section 2)
```

The four commanders are shown around the table, with the real commander art when it is cached
locally. Then it goes straight into opening hands / mulligans. Lightweight, not a cinematic, with a
**Skip** button, and it respects reduced-motion preferences.

## 4. Group concession / end game

Pods often know a game is over before every mechanical action is done.

- **Propose end game**, choosing a proposed winner, or Draw / No winner where that applies.
- The other remaining players see "PLAYER 2 proposes ending the game with Player 4 as winner.
  [AGREE] [DECLINE]".
- Every remaining relevant player must agree. One player can never force a winner through this.
- If anyone declines, the game continues normally.
- If everyone agrees, the result is recorded as an **AGREED RESULT**, kept distinct in game history
  from a result the rules engine determined. The log must never pretend the engine produced it.

## 5. Winner spotlight

When a game ends with a winner, briefly spotlight the winning player and commander, in the spirit of
a simplified TFT end screen (the Victory row of `3D_DIRECTION.md` §7a):

game ends → the table dims slightly → the camera subtly centers toward the winner → the winning
commander card gets a restrained brass/gold emphasis → **VICTORY** → winner name and commander →
the result controls appear.

The dramatic part is 1–3 seconds. No particle storms, explosions, mobile-game reward effects or long
animations. The final battlefield stays visible.

## 6. Rematch vote

After the result scene each player picks **Rematch — same decks** or **Return to lobby**. Responses
show compactly:

```
Player 1 — REMATCH
Player 2 — REMATCH
Player 3 — LOBBY
Player 4 — REMATCH
```

- **Everyone picks Rematch:** start a completely fresh game with the same pod and decks. Reset all
  match-local state: fresh shuffle, fresh RNG, fresh hands, fresh game objects, life, commander damage,
  poison and other resources reset, empty battlefield / graveyard / exile, a cleared stack, decisions,
  effects and history, and a new game/result identifier.
- **Anyone picks Lobby:** the pod returns to the persistent lobby, everyone still connected; deck changes
  happen there.
- The completed game stays in pod stats and history.
- The vote can't hang forever if someone disconnects: the host can eventually return the pod to the
  lobby.

## 7. Spectator rejoin

An eliminated player may leave the live-table view for the side activities of `ELIMINATION_HUB.md`
(Practice Table, Opening Hand Simulator, Deck Lab and the others). They always have **RETURN TO LIVE
GAME**, which puts them straight back into spectator mode.

- They see **public information only**: never opponents' hands, hidden library cards, private choices,
  searches, face-down identities or hidden WebSocket payloads. Eliminated players are spectators, not
  omniscient judges.
- While away from the table they get small public notifications for major events only ("Player 3
  eliminated.", "Final two players remain.", "Player 4 wins."). No constant notifications.
- When the match ends, the result / rematch flow appears even if they are in Practice Table or Deck Lab.

## The complete game-night loop

```
PERSISTENT LOBBY
  → players select decks / ready
  → PRE-GAME COMMANDER INTRO
  → TURN ORDER: d20 rolls (game 1) or the previous winner goes last
  → MULLIGANS
  → COMMANDER GAME
      → players may be eliminated
      → eliminated players spectate or use side activities, RETURN TO LIVE GAME at any time
  → normal victory OR agreed group concession
  → WINNER SPOTLIGHT
  → REMATCH VOTE
      → SAME DECKS: an immediate fresh game
      → RETURN TO LOBBY: players change or keep decks → ready → next game
```

## Pod session and game are different objects

One **pod session** links several **games** (Game 1, Game 2, Game 3 …). Each game keeps its own:

- result and winner (and whether it was an agreed result);
- decks and commanders used;
- turn order (and, for game 1, the d20 rolls);
- elimination order;
- duration and turn count;
- a final board snapshot, if supported.

The pod session holds what persists (section 1). No match-local state carries into the next game.

## Tests

- persistent lobby after a completed game;
- same-deck rematch (every item of match-local state reset, new game id);
- returning to the lobby and changing one player's deck;
- game 1 turn order from server-authoritative d20 rolls (clients can't influence them), shown to everyone;
- d20 ties rerolled only among the tied players;
- later games: the previous winner goes last and the others keep their relative order (the A/B/C/D
  example above);
- a host change to the order, and the order recorded in each game's metadata;
- skipping the pre-game intro;
- a successful unanimous agreed ending, recorded as an agreed result;
- a declined group concession (the game continues);
- winner spotlight state;
- an all-rematch vote;
- a vote where one player returns to the lobby;
- a player disconnecting during the vote (the host can still return the pod to the lobby);
- an eliminated player leaving the spectator view;
- an eliminated player rejoining the spectator view;
- spectator privacy (leak tests on an eliminated seat's connection);
- the match ending while an eliminated player is in Practice Table;
- several games recorded under one pod session.

## Out of scope for this milestone

Plane-themed environments.

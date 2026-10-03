# Milestone plan: game night / match flow (not started)

Requested 2026-10-03. **Build it after the core rules engine and the primary tabletop functionality
are mature.** Nothing here is built yet.

**Goal:** several Commander games with the same pod feel like one continuous game night. Build these
systems together:

1. Persistent pod lobby
2. Random first player
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

## 2. Random first player

Lobby setting **First player:** Random / Rotate from previous game / Host chooses. A new pod defaults to
Random.

- Random uses the server's authoritative RNG; clients never determine it themselves.
- Before the game starts, reveal "PLAYER 3 GOES FIRST" with a very short presentation.
- Store the starting player in the game record.
- Rematches can rotate the first player so everyone gets to start across a game night.

## 3. Pre-game intro

A very short Commander introduction before gameplay, roughly **2–4 seconds**:

```
PLAYER 1  Atraxa, Praetors' Voice
PLAYER 2  Krenko, Mob Boss
PLAYER 3  Muldrotha, the Gravetide
PLAYER 4  Yuriko, the Tiger's Shadow
PLAYER 3 GOES FIRST
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

*The request was cut off at this heading; confirm the details before building.* It presumably covers a
spectator (or an eliminated player, `ELIMINATION_HUB.md`) rejoining the pod for the next game.

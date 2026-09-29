# Pod stats

A small, persistent history of our pod's games: who played, which deck and commanders, who
won. It is **not** a ranking — no ratings, tiers or medals; players are listed by name.

## Recording a result

At the end of a game the host presses **End game** (top bar, or ⋯ → End game):

1. Choose the result type — **Single winner**, **Multiple winners**, **Draw** or **No result** —
   and the winner(s). Nothing is ever detected automatically: concessions, alternate wins,
   house rules and draws are the players' call.
2. Optionally add a note (“Mike killed everyone with 84 Goblins.”).
3. **Confirm result** shows a summary; **Record result** saves it. **Cancel** changes nothing.

A game can be recorded only once (its game id is unique). Loading, saving, closing, leaving,
disconnecting or starting a new game never changes statistics.

| Result | Games | Wins | Losses | Draws |
|---|---|---|---|---|
| Single / multiple winners | +1 for everyone | +1 for each winner | +1 for everyone else | — |
| Draw | +1 for everyone | — | — | +1 for everyone |
| No result | not counted at all | | | |

Win % = wins ÷ games (draws count as games played).

## Corrections

**Pod stats → Game history → Edit result / Delete** (on the host computer). Statistics are
never adjusted by hand: they are recomputed from the recorded results every time, so a
correction (another winner, a draw, no result) or a deletion is always reflected exactly. A
deleted result can be recorded again from the game.

## What is stored

`game_results` + `game_result_players` + `pod_players` in the app database
(`data/app.sqlite`): game id, date, table name, format, turns, duration, result type, notes,
and per player the name, deck (a stable local id — the host library deck id, or deck name +
commanders for decks brought to a lobby), the deck name at the time, the commander(s) and the
outcome. No hands, lists or other private card data.

Deck statistics group games by that stable deck id, so a deck keeps its history even after
its list changes; the most recent name is shown.

## Backup

The stats live in `data/app.sqlite` with your decks and saves; back up that file. **Pod stats →
Export (backup)** (host computer) downloads everything as JSON (`/api/pod/export`).

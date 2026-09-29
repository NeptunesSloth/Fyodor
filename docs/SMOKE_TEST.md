# Smoke test

A manual end-to-end check of the MVP acceptance criteria. It takes about 15 minutes.
The sample decks in `docs/sample-decks/` are ready to paste.

## Setup (online, once)

1. `scripts/setup.sh`
2. `scripts/update-cards.sh`: it reports the imported printing and card counts.
3. Optional: `scripts/update-cards.sh --skip-data --images tokens`
4. `scripts/serve.sh` and open http://127.0.0.1:8000. The home page shows the card database status.

## Offline play (disconnect from the Internet now)

| # | Step | Expected |
|---|---|---|
| 1 | **Decks → Import deck**, paste `krenko-goblins.txt` | Preview shows Commander 1 / Deck 99 and no unresolved cards |
| 2 | Import `atraxa-counters.txt` | Deck library lists both decks with color identity |
| 3 | Optional: `scripts/update-cards.sh --skip-data --images decks` (online) | Cards show art; without it they show text cards |
| 4 | **Play → New game**: Commander, hot-seat, one deck per player, **Start game** | Table opens; both commanders sit in the command zones; libraries hold 99 |
| 5 | Press `D` seven times (or library → *Draw several… 7*) | 7 cards in hand; the log says "drew a card" without naming them for the opponent |
| 6 | Library → *Mulligan* | Hand returns and is reshuffled, 7 new cards, mulligan count 1 |
| 7 | Drag a Mountain onto your battlefield; double-click it | It lands where you dropped it, then rotates (tapped) |
| 8 | Drag a spell onto the **Stack** panel, click **Resolve top** | Instants/sorceries go to the graveyard, permanents to the battlefield |
| 9 | Double-click the commander in the command zone | It goes to the stack and the tax badge shows +2 |
| 10 | Right-click a permanent → *Add counter → +1/+1* twice | A `+2/+2` badge appears |
| 11 | **Tokens** → search "Treasure" → create 3 | Three Treasure tokens appear, marked TOKEN |
| 12 | Right-click a creature → *Create copy* | A COPY appears; tapping it doesn't tap the original |
| 13 | Move cards to graveyard, exile, hand, library top/bottom, command zone (drag or *Move to*) | Each zone's count updates; tokens leaving the battlefield disappear |
| 14 | Opponent panel: click −5 twice; open *Commander damage*, add 21 | Life goes 40 → 30, then drops by another 21; the panel turns red but nobody is declared dead |
| 15 | Library → *Search library*, drag a card to hand, **Done & shuffle** | Browser lists the whole library; the log hides the card from the opponent's view |
| 16 | 🎲 → d20, then Coin | Results appear in the log |
| 17 | *Next step* through combat; right-click → *Attack*; opponent's creature → *Block* | Red/blue outlines and a blocker arrow; markers clear after combat |
| 18 | Tap a card by accident, press `Ctrl+Z` | It untaps; "undid: tap" is logged; `Ctrl+Shift+Z` redoes it |
| 19 | Shuffle, then undo | Library order and ids are restored exactly (automated test: `test_undo_shuffle_restores_previous_library_order`) |
| 20 | **Save** → name it | "Game saved" |
| 21 | Stop the server (Ctrl+C), confirm the network is still off, run `scripts/serve.sh` again | Server starts offline |
| 22 | **Play → Saved games → Load** | The table returns exactly as saved, including hands and library order; undo still works |
| 23 | Keep playing | Everything behaves normally |

## LAN check (optional)

1. `FYODOR_HOST=0.0.0.0 scripts/serve.sh`. On the host, start a game with *Table: LAN*.
2. On a second device open `http://HOST-IP:8000/#/play`, join with the room code.
3. Draw on both devices: each sees the other's hand only as card backs. Browser devtools
   (network tab → WebSocket frames) show no names or ids for the other player's hand or
   library.
4. Reload the second device: it reconnects to the same seat.

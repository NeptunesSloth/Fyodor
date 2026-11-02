# Playing over the LAN

Fyodor is built for a trusted pod on a home network: no accounts, no matchmaking, no cloud.
The host computer runs the server; everyone else opens `http://HOST-IP:PORT` in a browser.

## Setting up a table

1. **Host:** *Play → New game → Table: LAN* (with *Players choose their own decks* on). Pick
   format, seats, deck privacy, mulligan rule and the Response helper, then **Open the table**.
2. **Players:** *Play → Join a LAN game*, enter the room code (and password, if any) and a name.
3. In the lobby, everyone takes a seat, **Choose deck** (the host's library on the host computer
   only; *My decks* remembered in this browser; an Archidekt URL fetched once by the host; a
   pasted list; or a file read in the browser), and presses **Ready**.
4. The host presses **Start game** (or **Start anyway**). Opening hands follow
   [MULLIGAN_RULES.md](MULLIGAN_RULES.md).

**Deck privacy:** *Private* (others see a card count), *Commander only* (default: commander,
colors and deck name), *Public* (full lists). In game, opponents never see a player's deck id,
and with *Private* not even the deck name.

**Deck checks (advisory):** after you choose a deck, the host checks it against Commander's rules:
100 cards, singleton, color identity, commander count and the banned list.

- **Who sees what:** you see the list of findings, and the Ready button becomes **Play anyway**.
  With *Commander only* privacy the other players see only *how many* checks your deck has.
  With *Private* they see nothing, and with *Public* they see the text.
- **Never a blocker:** checks never stop anyone from readying or the host from starting. They
  follow the format if the host changes it.

**Who may change a player's cards:** *Everyone* (default: anyone moves, taps and marks any card, as at a real
table) or *Each player (and the host)*. The host sets it in the lobby (**Table settings**) or at the table
(**⋯ → Host tools → Cards**); it is saved with the game and carries to the next game of the night. A hot-seat game
ignores it. With *Each player*, the server refuses a player's table edits (move, tap, counters, damage, P/T, notes,
delete, flip, face down, attach, control, …) on another player's cards: "Bob's cards: only Bob or the host can change
them at this table." The host can always help, to fix a mistake.

- **Whose cards:** on the battlefield and the stack, the controller's (a creature you stole is yours to tap and move until
  it goes back; its owner gets it back from you or the host). In a hand, library or sideboard, that player's. Anywhere
  else, the owner's, and also the player whose zone holds it (your card in my exile: both of us). An Aura you control stays yours on my creature; I can still move my
  creature, and the Aura follows it.
- **Never limited:** casting, abilities, combat and everything rules automation does (your Murder still puts my creature
  into my graveyard), resolving the stack, phases and turns, mulligans, undo and undo requests, looking (top of library,
  reveals, searches), arrows and pings, chat and dice, life totals, poison and commander damage, table-wide cleanup
  (damage, until-end-of-turn markers, combat). *Delete all tokens* waits until the other players' tokens are theirs to remove.
- **New objects:** tokens, copies and test objects for yourself are fine (copying my card only reads it); for another
  player, they or the host make them. The same goes for drawing, milling or shuffling another player's library.
- The table offers another player's cards only what the setting allows (their card menu says why), and a drag of one
  snaps back with the reason.

## Surviving home-network trouble

Every seat has a **seat token** stored in that browser (`localStorage`). It is the player's
identity at this table, so a refresh, a closed tab, a Wi-Fi drop or a restarted laptop brings
them back to the **same seat, hand, private views and permissions**. Nobody is ever added as a
new player by reconnecting.

* The browser reconnects by itself (backoff up to 10 s) and receives a full, authoritative
  snapshot on every (re)connect.
* Everyone sees each player's presence: **Connected**, **Reconnecting…** (dropped less than 60 s
  ago) or **Disconnected**. A disconnected player's hidden cards stay hidden — views are built
  per seat on the server, whether or not anyone is connected.

### Revisions and resync

Every update the server sends carries a **revision** that only grows. A client ignores anything
older than what it has, and if it notices a gap it asks for a **resync**: the server sends a
fresh snapshot and the client *replaces* its state (the server always wins; nothing is merged).
*⋯ → Resync my view* does the same by hand, and *⋯ → Verify sync* (debug) compares the screen
with a fresh copy from the server and resyncs if they differ.

## Host tools

Under **⋯ → Host tools…** (host only; hidden from everyone else):

| Tool | What it does |
|---|---|
| Force reconnect | Drops that player's connection; their browser reconnects immediately. |
| Reclaim / assign seat | Issues a new seat token and a link. Whoever opens it sits in that seat (same hand); the old token stops working at once. Use it when someone switches devices or a laptop dies. |
| Remove player | For someone who has left for good (only when not connected). Cards they own leave the game; permanents they controlled but didn't own go back to their owners. |
| Resync all clients | Everyone gets a fresh authoritative snapshot. |
| Force pass response | Closes an open response check. |
| Return selected to owner | Stolen permanents go back to their owner's battlefield; owned cards in someone else's zone go to the owner's zone. |
| Unlock selected | Clears the lock on selected objects. |
| Restore lost objects | Brings battlefield objects dragged far off the table back into view. |

Anything deleted by mistake comes back with **Undo**.

# Playing over the LAN

Fyodor is built for a trusted pod on a home network: no accounts, no matchmaking, no cloud.
The host computer runs the server; everyone else opens `http://HOST-IP:PORT` in a browser.

The host computer's name works too: its bare name (`http://DESKTOP-42:8000`), with `.local`, and the full name the home
router gives it (`http://desktop-42.lan:8000`, `.home`, `.localdomain`). Any other name answers *This address is not one
Fyodor answers to*: use the IP address, or add the name to `FYODOR_EXTRA_HOSTS` ([Settings for this](#settings-for-this)).

## Setting up a table

1. **Host:** *Host a LAN night* on the launcher (or *Play*): every new game is a LAN night (hot-seat tables are no longer
   offered; a saved game loads as a LAN night too). With *Decks: Players bring their own*, pick the format (below), seats,
   deck privacy, mulligan rule and automation (Commander starts at Full), then **Open the table**. With *You deal them*,
   give each seat a deck from your library and **Deal and start**: the pod joins with the room code and takes the open
   seats. For solo testing, remove the other seats
   (or just start alone: open seats never hold up the start).
2. **Players:** press **Join** on the table under *Play* (see [Finding a game](#finding-a-game)), or enter the room
   code (and password, if any) and a name under *Join with a code*.
3. In the lobby, everyone takes a seat, **Choose deck** (the host's library on the host computer
   only; *My decks* remembered in this browser; an Archidekt URL fetched once by the host; a
   pasted list; or a file read in the browser), and presses **Ready**.
4. The host presses **Start game** (or **Start anyway**). Opening hands follow
   [MULLIGAN_RULES.md](MULLIGAN_RULES.md).

**Deck privacy:** *Private* (others see a card count), *Commander only* (default: commander,
colors and deck name), *Public* (full lists). In game, opponents never see a player's deck id,
and with *Private* not even the deck name.

**Format:** *Commander* (default) or *Sandbox*. Both play Commander decks at 40 life (editable), with the command zone,
commander damage and tax.

- **Sandbox** is free play, as in Tabletop Simulator: no deck checks, rules automation starts **off** (the manual table:
  everything moved by hand), and test objects are allowed (*More → Solo tools → Spawn a card*). The host can turn the rules
  on at the table: the **Sandbox** tag in the top bar (where the automation level shows) opens the automation settings.
- On the Play page, **Sandbox** is where you test a deck on your own: one seat (yours), the deck you choose, and the
  automation level you pick (Off by default); **Start testing** deals it and puts you at the table at once, with no lobby,
  room code or other seats. Tick **Target dummy** to seat a practice opponent with no deck as well (it never takes a
  turn, the server answers for it, and *Solo tools → Reset dummy* brings it back; see docs/MACROS_AND_SOLO.md). A LAN night's host can also switch its table to Sandbox in the lobby's **Table settings**
  (the lobby then says *Sandbox: free play*; changing it asks everyone to confirm Ready again). The Play page's table
  tiles show *Sandbox*.

**Deck checks (advisory, Commander tables):** after you choose a deck, the host checks it against Commander's rules:
100 cards, singleton, color identity, commander count and the banned list. A Sandbox table checks nothing.

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

## Finding a game

Nobody has to type an address or a code when everyone is on the same network, and players bring their own decks.

- **Browsing the host's address** (`http://HOST-IP:PORT`): *Play → Tables in progress* lists the host's LAN tables, open
  lobbies first. Each has **Join** (while a seat is open; your profile's name and preferred seat are used) and **Watch**. A
  table with a password (the padlock) asks for it right on its tile. *Join with a code* still works for invite links and codes.
- **Running Fyodor on your own computer** (the downloadable app, or `python -m app.launcher`, in LAN or `--local` mode):
  *Play → Games on your network* lists the LAN tables other computers running Fyodor answer with: the host computer's name,
  the table, "In the lobby · 2 of 4 seats taken" or "Turn 6", and a padlock when it has a password. **Join** opens the host's
  Play page in this tab and seats you at once (or asks for the password); **Watch** does the same as a spectator. The
  launcher shows one line when a lobby has a free seat ("Thursday Commander is open on DESKTOP-42 — Join"). The list
  refreshes every few seconds while the page is open.

### Your decks come with you

The norm at game night: you saved your decks on your own Fyodor at home, online; at the table there may be no internet,
only the LAN. You press **Join** and play your deck, nothing else to do.

1. **Saving a deck keeps it playable offline.** Creating, importing or saving a deck while your computer is online downloads
   the art of that deck's own printings in the background (the Decks page shows one quiet line while it runs). Offline, the
   deck waits and is tried again when Fyodor starts and every 15 minutes. *Settings → Card database → Keep deck art for
   offline play* turns it off for small disks (art already cached stays).
2. **Join brings your decks** (never Watch): your Fyodor sends your deck library (up to 60 decks, as plain lists) straight to
   the host's Fyodor over the LAN. The host keeps it in memory only, for your seat only: your seat shows your decks under
   their commanders' art (*Your decks, from YOUR-COMPUTER*), one click to play one, and **Choose deck** opens on them, with
   the host's library and the other sources after them. Choosing one goes through the lobby's usual import (deck checks and
   deck privacy unchanged: the others see your chosen deck only as the privacy setting allows, never your library). Tick
   *Also keep the one I choose in My decks* to remember it in that browser. The library is dropped when you leave the seat or
   the game starts (an unused one after ten minutes); it is never saved or logged.
3. **Cards the host doesn't know.** If your card database is newer than the host's (a new set), your Fyodor asks the host
   which of your decks' printings it lacks and sends just those cards along (Scryfall card data, never database rows, at most
   500). The host checks each one and only adds: it never changes a card it has, and a new printing of a card it knows must
   carry that card's name. The next card-database update replaces them anyway. A card it can't take is named in your
   *Your decks* tab with the reason, and plays as a text proxy.
4. **Art the host doesn't have.** Once you pick a deck (and for the commanders in your list), the host fetches the images it
   lacks for that deck from your Fyodor over the LAN, in the background: real JPEGs only, 3 MB each, 400 per deck. Cards show
   as proxies until then; every screen at the table then looks again (without being told which cards: that would reveal your
   deck). For this your Fyodor must be reachable on the LAN (the default; with `--local` the art stays at home).

**A player with only a browser** (no Fyodor of their own): their *My decks* in that browser are their decks: their seat shows
them first in the same way. **My decks are kept per host address**: they live in the browser's storage for the address you
opened (`http://192.168.1.7:8000` is a different place from `http://192.168.1.9:8000`), so if the host's address changes,
the list looks empty there. *Choose deck → My decks* says so, and **Export My decks** / *Import multiple deck files* (the
export file) carry them to the new address.

### How finding works

A server on the LAN (the default; never with `--local`) answers a small UDP query on port **47474**
(`FYODOR_DISCOVERY_PORT`); asking works whatever address your own server listens on. `FYODOR_DISCOVERY=0` turns finding off
both ways: the computer neither answers nor searches. If the port is taken or there is no network, the server logs it once
and carries on; friends then use the address. Several Fyodor servers on one Linux or macOS computer share the port; on
Windows only the first one answers.

**Firewall:** allow Fyodor (or Python) for *private* networks on the host: TCP on the game port (8000) for playing, UDP 47474
for being found. On a player's computer, the game port lets the host fetch the art of their deck. If a table doesn't show
up, the host's firewall is the usual reason; its address still works.

**Privacy:** an answer contains exactly what any device on the network already sees on the host's Play page: the computer's
name, its game port and Fyodor version, and for each LAN table its name, format, room code, whether it has a password, the
seat counts, the seated players' names and the turn. Never a hot-seat or practice table, a deck, a hand, a token or a password.
The server answers only devices on the local network (private, link-local or this computer), at most five times a second each,
and ignores anything malformed, oversized or of another version. Only the computer running Fyodor can make it search
(another device can't make it broadcast) or send its deck library, and only to an address on the local network. A host takes
deck libraries, card lookups and card data only from devices on the local network, rate-limited and size-capped (2 MB).

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

### The host's window

Host tools, and anything else only the host may do (opening a table, seat links, kicking), work in **the window the launcher
opens for you**, and only there. That window carries a secret that Fyodor makes new each time it starts and keeps in the
browser; no one else has it. A browser pointed at the address by hand (`http://127.0.0.1:8000`, or the host's LAN address),
even on the host computer, is a guest: it can join and play, and the host tools say *Open Fyodor from its launcher on the host
computer to use host tools.*

- **To get host tools back** (the window was closed, or you opened a second browser): start Fyodor from its launcher again. It
  says it is already running and opens a new host window. *Settings → Restart* does the same: it opens a new host window and
  the old one becomes a guest.
- A restart makes a new secret, so a host window from before it is a guest afterwards.

### Seat links

**Reclaim / assign seat** (above) gives a link of the form `http://HOST-IP:PORT/#/game/GAME-ID?seat_token=...`. Send it to the
player (or open it on their device). The token sits after the `#`, so the browser never sends it to the server in an address,
and Fyodor removes it from the address bar as soon as the page opens. Opening it puts that device in the seat and the hand
stays as it was. The seat's old token stops working at once: the old tab, if it is still open, shows *Your seat is no longer
valid here. Join again.* and the player there joins again with the room code if they still want to play. Treat a seat link like
a key to the seat and don't post it where others read it.

## Limits you can run into

A normal night doesn't touch these. They slow down someone guessing a table's **password**; they do not hide the room code:
anyone who can open the host's address sees every LAN table's code on the Play page (that is how *Tables in progress* and
*Games on your network* work). The room code is not a secret. Only a table password keeps a stranger on the network out, so
give the table one when not everyone on the network is in your pod.

- **Wrong room codes or passwords:** five wrong tries from one device in 15 minutes give *Too many attempts. Try again in a
  few minutes.* The message says how long to wait; other devices are not affected, and a player who already holds a seat
  reconnects as usual. A right password still gets in. If a table's password is guessed wrongly many times from many devices,
  that table also slows down new joins for a while, but not the right password.
- **Too many connections:** a seat may have four tabs or windows open at once, and one device 24 connections. A fifth tab for the
  same seat is closed with *Too many connections*: close the tabs you don't need and reload. A phone that went to sleep
  leaves its old connection behind until Fyodor closes it (below), so a player who wakes it and also opens a new tab may
  have to wait a minute or so.
- **A connection that goes quiet** for 90 seconds is closed; the browser reconnects by itself and gets the table back.
- **Messages** much over 64 KB are refused by the table; normal play never comes near that.

## Friends outside your home network

Two ways: an **invite link** from Fyodor itself (below), or a **private network** between the computers (option A).

### Inviting friends over the internet

For a friend who is not on your network, with nothing for them to install: they need only a browser.

1. **Host:** in the table's lobby press **Invite** → **Invite over the internet** (or, at the table, **⋯ → Host tools → Invite
   over the internet**). Only a LAN table can be shared, and only from the window the launcher opened.
2. If the table has no password, type one (8 to 100 characters) and press **Share with this password**: a table shared over the
   internet always has a password, and from then on LAN players need it too. If it already has one, the panel says *This table
   already has a password.* and asks: **Share with it**, or **Set a new password** (8 to 100 characters). A short LAN password is
   easy to guess from the internet, so set a new one unless the old one is long. A new password is needed by everyone who joins
   from then on, LAN players too; players already seated keep their seats.
3. Fyodor starts the link. The first time it downloads Cloudflare's tunnel program, `cloudflared` (about 55 MB on Windows, kept in the
   `tunnel` folder of Fyodor's data folder), checks it against a checksum written into Fyodor, and runs it; a different file is never
   run. A few seconds later the panel shows the link (`https://<random name>.trycloudflare.com/#/play?code=…`). **Copy link** and send
   it to your friends, and **send the password separately**.
4. **Friends** open the link, type the password, and take a seat. The top bar shows **Shared over the internet** (a globe) to everyone
   at the table while the link is up.

What the link reaches: only the tables you shared, and only what a player at them needs. It never lists your other tables, never
gives anyone host tools (even from your own computer), and the LAN room code does not work through it (the link carries its own
10-character invite code). Friends on your LAN keep joining with the room code as always.

**Stop sharing** (same panel) closes the link's players' tables at once (*The host stopped sharing this table.*); LAN players play on.
Pressing **Invite over the internet** again gives a new invite code (an old link no longer opens the table), with the table's password
unless you set a new one. The address (`https://<random name>.trycloudflare.com`) is new only when no other table was being shared: the
link's program keeps running, with the same address, while any table is shared. Closing the table ends its
sharing (and the link, when no other table is shared); closing Fyodor ends the link: an old link stops answering. If the link goes down by itself, the panel says *The internet link went down.*
and offers **Invite again**.

Things to know:

- **Cloudflare carries the traffic.** The link is a Cloudflare *quick tunnel*: no account and no router change, and Cloudflare sees
  the traffic (it serves the https). Cloudflare describes quick tunnels as "for testing and development" with "no uptime guarantee": a
  game night's link can drop or be refused, and Cloudflare can change or end the service. LAN play does not depend on it.
- A quick tunnel handles at most 200 requests in flight; on a busy table a card picture may load a second late.
- Anyone with the link **and** the password can join. Kick and seat tools work as for any player (for a shared table, Host tools'
  **Reclaim / assign seat** also gives the seat's link on the internet address); to cut everyone off, press **Stop sharing**.
- A friend who closes the tab can open the same link again while the table is shared: after the password, the browser that holds
  their seat gets it back (not a second seat).
- Friends over the internet can't upload their own sleeves or playmats (players on your network can); they play with the defaults.

- `FYODOR_ALLOW_NETWORK=0` turns it off: nothing is downloaded and the panel says internet features are turned off. A server started
  without the launcher (for example `uvicorn --factory`) cannot share. With nobody pressing **Invite over the internet**, nothing is
  downloaded and no tunnel runs; `--local` still allows it (the tunnel only talks to this computer).
- On macOS and Linux, if Fyodor is killed outright (not closed), `cloudflared` can be left running; it reaches nothing, and you can end
  it by hand. On Windows it always ends with Fyodor.

### Option A: a private network

What should work, with no change to Fyodor, is a **private network** between the
friends' computers, such as Tailscale. This project has not tested it yet. Install it on the host's computer and on each friend's, then the friends open
`http://HOST-PRIVATE-ADDRESS:PORT` (the host's address on that private network, shown in the Tailscale app) as if it were
the LAN. The game, the room code and the password should work as on a LAN, and nothing is opened to the internet. If the address
is a name rather than a number, the host lists it in `FYODOR_EXTRA_HOSTS` (below); numeric addresses work as they are.
One difference from a LAN: Tailscale's IPv4 addresses (`100.64.0.0/10`, such as `100.101.102.103`) are not private-network
addresses to Fyodor, so a friend joining by one can play but **Join brings your decks** and *Friends' decks* are refused (the
host only takes deck libraries from the local network). A friend can paste a list or pick from *My decks* instead.

**Port-forwarding the host's router to the game port is not recommended.** It puts the table on the open internet,
reachable by anyone who finds the address; use an invite link or a private network instead.

## Settings for this

Environment variables (set them before starting the launcher; the defaults are right for a LAN night):

| Variable | What it does |
|---|---|
| `FYODOR_TRUSTED_PROXIES` | Comma-separated addresses or ranges (`127.0.0.1`, `10.0.0.0/8`) of a reverse proxy or tunnel in front of Fyodor, whose `X-Forwarded-For` is believed when it says who connected. None by default. Leave it unset on a LAN; a bad entry stops Fyodor at start. This is the only place forwarded headers are read (the web server's own proxy-header handling is off), and an invite link never needs it. |
| `FYODOR_EXTRA_HOSTS` | Comma-separated host names (no port, no `http://`, no `/`) Fyodor answers to besides IP addresses, `localhost` and this computer's own names (its name, with `.local`, and its full name on the network). None by default; a bad entry stops Fyodor at start. |
| `FYODOR_CORS_ORIGINS` | Comma-separated origins (`https://host`) besides Fyodor's own that may post and open sockets. None by default (before this release the Vite dev server's origins were trusted on every install). Never consulted for an invite link. |
| `FYODOR_DEV_TOOLS` | `1` turns on the developer tools, including the API pages `/docs`, `/redoc` and `/openapi.json` and the rules test-scenario tools. Off by default (without it those pages are not there). It also trusts the Vite dev server's origins (`http://localhost:5173`, `http://127.0.0.1:5173`) unless `FYODOR_CORS_ORIGINS` is set; `scripts/dev.sh` sets it. |
| `FYODOR_ALLOW_NETWORK` | `0` turns off everything that reaches the internet from this computer, the invite link included (and Archidekt import, artwork caching, card updates). On by default. |

`FYODOR_LEGACY_WS_TOKEN` is gone: a seat token in the game socket's address is never accepted, whatever the environment says.

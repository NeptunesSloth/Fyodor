# Game-night recovery

What happens when something goes wrong during a game night, and what to do. Everything here
works offline; nothing is sent anywhere.

## The host computer crashes, loses power, or Fyodor is restarted

**Nothing is lost and nobody needs to do anything.** Every started table is stored as:

- its room: the room code, the password hash, each seat and its seat token, the host seat;
- a **checkpoint**: the latest autosave (every 10 changes, and when Fyodor shuts down);
- a **journal**: every change since that checkpoint (each resolved action, each undo and redo),
  written to `app.sqlite` before the table is updated for the players.

When Fyodor starts, it rebuilds every table from its checkpoint and replays the journal on top.
Because actions carry their resolved randomness (shuffles, dice, new ids), the rebuilt table is
identical to the one before the crash, including library order and undo history. Players'
browsers still hold their seat tokens, so they reconnect to the same seats on their own; the
log says "Fyodor restarted — the table was restored". The launcher lists the restored tables.

A table that was closed (End game → close) is not brought back. If one table can't be rebuilt,
the others still are, and its autosaves stay in **Saves**.

## A player's connection drops

The player sees "Connection lost — reconnecting…", with how many actions are waiting. Every
action carries a `client_action_id`; actions sent while the connection is down wait in an
outbox for up to 45 seconds and are sent again after reconnecting. The server answers:

| Answer | Meaning |
|---|---|
| `ACCEPTED` | applied now |
| `REJECTED` | refused (with the reason); nothing changed |
| `ALREADY_APPLIED` | this action already reached the table (a retry): it is not applied again |

So a retry never plays a card twice or loses a life point twice. Action ids are remembered per
table (the last 512) and survive a restart.

## Backups — BACKUP FYODOR

Settings → **Backup & restore** → *Back up Fyodor now* saves
`data/backups/fyodor-backup-<date>-<time>.zip` and downloads it. A backup holds decks, saves,
live tables, pod stats, macros, and custom sleeves/playmats. The card database is not included;
it is rebuilt from card data (Settings → **Card database**). The last 12 backups made by hand are kept.

A backup made by hand also carries the **card art your decks use** (the cached images of every
saved deck's printings and the tokens they make, plus the card back and the mana symbols), so a
restore on an offline computer plays them with their art. Only what the decks need, never the
whole image cache: roughly 10 MB per deck. Art stops being added near the 2 GB backup limit.
Automatic backups carry no art (a dozen of them are kept).

**Automatic backups** work like a rotating autosave, so nobody has to remember. Fyodor writes
`fyodor-autobackup-<date>-<time>.zip`:

- at start-up, if there is something to keep and the newest backup is more than a day old;
- every 30 minutes, if anything changed (`FYODOR_AUTO_BACKUP_MINUTES`; `0` turns them off);
- right after each recorded game.

It keeps the newest 8, plus the last one of each day for a week, separately from the ones made
by hand. Settings shows them as *Auto* with the reason, when the last one was made, and any
error. Set `FYODOR_BACKUP_COPY_DIR` to a USB stick or a synced folder and every backup is also
copied there, following the same rotation. A missing folder never stops a backup; Settings
reports it.

**Restore:** pick a listed backup or upload a backup file, then restart Fyodor. The backup is
checked first (only the expected files, a readable database, size limits); nothing in it is
ever executed. At the next start the current database is copied to
`data/backups/app-before-restore-<time>.sqlite` and the backup is swapped in. Card art in the
backup must be named exactly as the image cache names it and be a real JPEG (or a plain SVG for
a symbol), 3 MB at most; anything else is left out. It only fills gaps: art this computer
already has is never replaced.

Backups and restores are only available on the host computer.

**Before a database upgrade** (a new Fyodor version with a schema migration), the database is
copied to `data/backups/app-before-v<N>-<time>.sqlite` automatically.

## Recovery mode (a damaged database)

If `app.sqlite` can't be opened or fails its integrity check, Fyodor moves it (with its WAL
files) to `data/recovery/app-damaged-<time>.sqlite`, starts with a fresh database, and says so
on the launcher with a link to restore a backup. The damaged file is kept for manual rescue
(for example `sqlite3 app-damaged-….sqlite ".recover"`).

## Shutting down

Close the window running Fyodor or press Ctrl+C: every table is autosaved and kept for the next
start. There is no need to end games first.

## Tests

- `backend/tests/test_recovery.py`: a crash mid-game (no final autosave) restores the exact
  table, seat tokens and password; undo reaches back past the crash; closed tables stay closed;
  retried actions are applied once, over REST and WebSocket, before and after a restart.
- `backend/tests/test_backups.py`: backup → change → restore → restart; hostile archives are
  refused; a damaged database starts in recovery mode; the pre-migration copy.
- `backend/tests/test_long_session.py`: 400 mixed actions with undos on a four-player table
  (median ≈ 6 ms per action here), then a crash and an exact recovery.
- `frontend/src/services/gameSocket.test.ts`: the outbox keeps an action through a dropped
  connection and resends it with the same id.
- `frontend/e2e/offline.spec.ts`: the launcher, settings and a 3D game load nothing from
  outside the host.

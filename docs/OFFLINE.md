# Fyodor on a computer with no Internet

The Windows installer carries everything Fyodor needs, so an offline computer needs nothing else:

1. Copy `Fyodor-Setup-<version>.exe` onto a USB stick (one file).
2. On the offline computer, double-click it and click through the installer.
3. Open **Fyodor** from the Start menu or the desktop.

That's all: no browser to update, no download, no Internet, not even on the first start.

## Bringing your decks

Your decks travel in a Fyodor backup file:

1. On the computer that has your decks (with Fyodor, online or not): **Settings → Back up Fyodor now**. It saves a
   `fyodor-backup-….zip` file (to Downloads). Copy it onto the USB stick with the installer.
2. On the offline computer, in Fyodor: **Settings → Restore from a file…**, choose that file, then click
   **Restart Fyodor now**. Your decks, saved games and pod stats are all there.

A restore replaces what the offline computer had (a copy of it is kept). Decks that live on Archidekt or as text
lists: import them into Fyodor on the online computer first (Decks → Import; several at once with the bulk import),
then back up. A deck list can also be pasted in on the offline computer itself: Decks → Import → paste the list.

## What's inside

- **Fyodor's own window.** The installer ships its own Chromium (`browser\` beside `Fyodor.exe`), and Fyodor opens the
  table in it. The computer's own browser is never used, so an old Edge that can't be updated doesn't matter. Fyodor
  keeps this window's settings in its data folder (`%USERPROFILE%\Fyodor\data\window`), apart from any other browser.
  3D works even without a graphics driver (software rendering); a computer that still can't draw 3D gets the 2D table.
- **The card database.** On the first start Fyodor copies the database the installer carries (`seed\cards.sqlite`)
  into its data folder. It is never copied over a database that's already there. To refresh it later, connect once
  and use Settings → Card database, or install a newer Fyodor (the copy happens only when none is there yet).
- **Token pictures.** The installer can carry the art of every token (`seed\images\tokens`), and Fyodor reads it in place, so
  tokens show their art offline. A picture the computer downloaded itself is used first.
- **Other card pictures** are not included: offline, cards are drawn as frames with their name, cost, type and text. Pictures
  already saved on a computer stay there.

Opening Fyodor again while it's running just brings the table back up.

If something still goes wrong while drawing, the page shows what broke and in which browser (with **Copy details**)
instead of a black screen.

Needs Windows 8.1, 10 or 11 (64-bit). On Windows 8.1 the window is Chromium 109, the last Chromium made for it;
on 10 and 11 it is a current Chromium. On anything older the installer says so and stops.

## Building it

`BROWSER_DIR=<unpacked Chromium for Windows> LEGACY_BROWSER_DIR=<unpacked Chromium 109> CARDS_DB=<cards.sqlite> TOKEN_IMAGES=<data>/images/tokens REBUILD=1 SMOKE=1 bash scripts/build-windows-installer.sh`
(token pictures: `python -m tools.update_cards --images tokens` fills `<data>/images/tokens`).
Chromium for Windows: a build from the Chromium snapshots
(`commondatastorage.googleapis.com/chromium-browser-snapshots/Win_x64/<revision>/chrome-win.zip`), with the test and
installer programs and the non-English locales removed. Chromium is open source (BSD licence, see its `LICENSE` notices);
the card data is Scryfall's (see docs/ASSETS.md).

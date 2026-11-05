# Fyodor on a computer with no Internet

The Windows installer carries everything Fyodor needs, so an offline computer needs nothing else:

1. Copy `Fyodor-Setup-<version>.exe` onto a USB stick (one file).
2. On the offline computer, double-click it and click through the installer.
3. Open **Fyodor** from the Start menu or the desktop.

That's all: no browser to update, no download, no Internet, not even on the first start.

## What's inside

- **Fyodor's own window.** The installer ships its own Chromium (`browser\` beside `Fyodor.exe`), and Fyodor opens the
  table in it. The computer's own browser is never used, so an old Edge that can't be updated doesn't matter. Fyodor
  keeps this window's settings in its data folder (`%USERPROFILE%\Fyodor\data\window`), apart from any other browser.
  3D works even without a graphics driver (software rendering); a computer that still can't draw 3D gets the 2D table.
- **The card database.** On the first start Fyodor copies the database the installer carries (`seed\cards.sqlite`)
  into its data folder. It is never copied over a database that's already there. To refresh it later, connect once
  and use Settings → Card database, or install a newer Fyodor (the copy happens only when none is there yet).
- **Card pictures** are not included: offline, cards are drawn as frames with their name, cost, type and text. Pictures
  already saved on a computer stay there.

Opening Fyodor again while it's running just brings the table back up.

If something still goes wrong while drawing, the page shows what broke and in which browser (with **Copy details**)
instead of a black screen.

Needs Windows 10 or 11 (64-bit).

## Building it

`BROWSER_DIR=<unpacked Chromium for Windows> CARDS_DB=<cards.sqlite> REBUILD=1 SMOKE=1 bash scripts/build-windows-installer.sh`.
Chromium for Windows: a build from the Chromium snapshots
(`commondatastorage.googleapis.com/chromium-browser-snapshots/Win_x64/<revision>/chrome-win.zip`), with the test and
installer programs and the non-English locales removed. Chromium is open source (BSD licence, see its `LICENSE` notices);
the card data is Scryfall's (see docs/ASSETS.md).

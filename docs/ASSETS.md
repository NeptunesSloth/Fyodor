# Custom assets: playmats, sleeves and the asset manager

All custom images live in one managed library on the host computer (`data/assets/`, indexed
in `data/app.sqlite`). Everything works offline.

## What's accepted

* **PNG, JPEG, WEBP** only, recognised from the file's *content* (magic bytes and image header),
  never from its name or declared type — SVG, GIF, scripts or renamed files are refused.
* At most **20 MB** and **8192 × 8192** pixels. Dimensions are read from the header without
  decoding pixels or running any external library.
* Files are stored by SHA-256 (`<sha256>.png|jpg|webp`): identical uploads share one file, and
  a file is removed when the last asset using it is deleted.
* Clients refer to assets only by an opaque id. Files are served from
  `/api/assets/<id>/file?v=<sha>` with long-lived immutable caching, so every browser at the
  table fetches an image once over the LAN and keeps it. There is no way to request a path.

## Sleeves (card backs)

*⋯ → Appearance… → Card back*: **Default**, a **local image** (uploaded to the host), or a
**saved** card back. Everyone sees your cards' backs — hand, library, face-down cards — in your
sleeves. The sleeve is only a picture: which card is which stays on the host, and hidden cards
are still sent as anonymous placeholders.

**Default** is the Magic card back. Like the card art it is linked from Scryfall, never shipped: the
host fetches it, with Scryfall's mana symbols, whenever it may go online (`FYODOR_ALLOW_NETWORK`) —
with each card database download or update, at start-up when either is missing, and when a table
asks for a missing one (`backend/app/cards/linked.py`). It serves them to every device at the table
(`/api/images/card-back`, `/api/symbols`). Until then the tables draw their own brown back and
letter circles, and switch to the real ones as soon as the host has them, without a reload.

## Playmats

*⋯ → Appearance… → Your playmat*: pick or upload an image, then adjust it non-destructively
(the file is never modified): **Fill / Fit inside / Stretch**, zoom, move, rotate (0/90/180/270),
opacity, and whether zone outlines are drawn over it. *Use this playmat* puts it under your
battlefield for everyone. The host can also put one mat under **the whole table**.

LAN players may upload card backs and playmats from their own device (with their seat token,
rate-limited); other kinds are added on the host computer.

## Asset manager

*Assets* (top navigation, on the host computer): categories — Playmats, Card backs, Token art,
Counter art, Utility objects, Reference cards, Dice skins, Table presets — with a preview,
name, type, size, dimensions and **Used by** (live tables). **Rename**, **Replace** (tables
using it update immediately), **Duplicate**, **Delete** (warns and lists where it's used; those
tables fall back to the default look).

## Icon credits

The seat buttons' glyphs (`frontend/src/game/seatGlyphs.ts`) are from [game-icons.net](https://game-icons.net), under
[CC BY 3.0](https://creativecommons.org/licenses/by/3.0/):

- anticlockwise-rotation, card-exchange, save-arrow by Delapouite
- crystal-ball, tombstone, semi-closed-eye, swap-bag by Lorc
- card-draw by Faithtoken

They're printed in ink on the table's ivory chits. The paths are unchanged, apart from leaving out each icon's
background square.

The zone wells' glyphs (`frontend/src/game/zoneGlyphs.ts`) are from [game-icons.net](https://game-icons.net) too,
under [CC BY 3.0](https://creativecommons.org/licenses/by/3.0/):

- open-book (the library), tombstone (the graveyard), portal (exile), crown (the command zone and the commander-tax
  coins) by Lorc

They're tooled faintly into an empty well's leather on the 3D table, engraved on the wells' brass nameplates at three
or more seats, and struck on the commander-tax coins. The paths are unchanged, apart from leaving out each icon's
background square.

# Portable game packages and diagnostics

Both tools work only on the host computer (the machine running Fyodor). Nothing is uploaded
anywhere, and neither needs the Internet.

## Game packages (`.fyodor.zip`)

On the Play page, **⇩** next to a saved game downloads a package. It contains:

| File | Contents |
| --- | --- |
| `manifest.json` | format `fyodor-package` v1, save name, and the list of images with their SHA-256 |
| `save.fyodor` | the save itself: state, undo history and named snapshots (versioned save format) |
| `assets/<id>.<png\|jpg\|webp>` | the custom sleeves and playmats the game, or its snapshots, use |
| `macros.json` | your library macros plus the card macros for cards in this game |

**Import package…** (Play page → Saved games) adds it as `<name> (imported)`. Import is
defensive:

- **Size and names:** size and member count are bounded before anything is decompressed.
  Only the expected member names are read. Nothing is extracted to disk by a name taken from
  the archive, so `../` or absolute paths do nothing, and a manifest entry must match
  `assets/<hex id>.<ext>`.
- **Save:** the save is decoded and migrated like any other save and must load before
  anything else is imported.
- **Images:** every image must match its checksum and pass the same content sniffing as an
  upload: real PNG/JPEG/WEBP, with a dimension limit. An image identical to one you already
  have is reused. Otherwise it's added under a fresh id, and the save's references
  (including undo history and snapshots) are remapped.
- **Macros:** they are re-validated as declarative data. Duplicates (same scope, card and
  name) are skipped.

## Diagnostics (Settings → Diagnostics)

**Download diagnostics** saves a JSON file with:

- the app, save-format and database versions, the Python version and platform;
- the network, assistant and autosave settings;
- card-database stats and library counts;
- per-table connection state, revision and history size;
- consistency checks: every card is in exactly one zone, and zones only list known cards;
- the last 200 warnings and errors, kept in memory only.

By default it contains **no hands, libraries, decklists, card names from hidden zones or
notes**. The **Include private information** checkbox is an explicit opt-in: it adds full
table states and decklists, and the file name gets a `-PRIVATE` suffix.

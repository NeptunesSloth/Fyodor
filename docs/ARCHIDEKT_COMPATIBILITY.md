# Archidekt compatibility

Archidekt is the primary external deck ecosystem. A deck maintained on Archidekt should
come into Fyodor with minimal friction. After import it's an ordinary local deck that
works offline forever.

## 1. Supported workflows

| Workflow | Status | Needs Internet |
|---|---|---|
| **Paste an Archidekt URL or deck id** | Supported, via Archidekt's public deck JSON (see §2) | Only during import |
| **Paste Archidekt text export** | Supported | No |
| **Upload an exported file** (`.txt`, `.dek`-style text, or a saved Archidekt deck `.json`) | Supported | No |
| Export back to Archidekt-compatible text | Supported | No |
| Check the Archidekt source for changes (diff, then apply/ignore) | Supported for URL-imported decks | Only while checking |
| Account login / two-way sync | Not implemented. No supported write API. | — |

The import dialog shows only the workflows that work. If Archidekt can't be reached, the
URL tab says so and points to paste/upload. The dialog never shows a dead button.

## 2. Archidekt deck JSON

Investigation (2026-09-28):
- `GET https://archidekt.com/api/decks/{id}/` returns a public deck as JSON without
  authentication. It's the endpoint Archidekt's own web app uses.
- It isn't formally documented, but it has been stable for years and is used by many
  community tools.
- `robots.txt` doesn't disallow `/api/`.
- Private decks return an error.

How Fyodor uses it:
- only when the user explicitly imports or checks a deck: one request, with a
  `User-Agent` identifying Fyodor;
- never during play, never in the background, never scraped HTML;
- if the endpoint changes, URL import fails with a clear message and the text/file
  import paths still work. Parsing is defensive: unknown fields are ignored and every
  field is read with a fallback.

Relevant fields:

| JSON | Meaning | Fyodor |
|---|---|---|
| `name`, `id`, `updatedAt`, `deckFormat` (3 = Commander) | deck metadata | deck name, source link, format |
| `categories[]` `{name, isPremier, includedInDeck}` | deck categories | category list. Premier → commander. `includedInDeck=false` → maybeboard. |
| `cards[].quantity` | copies | quantity |
| `cards[].categories[]` | the card's categories (first one is primary) | stored as `categories` metadata |
| `cards[].modifier` | `Normal` / `Foil` / `Etched` | `finish` |
| `cards[].companion` | companion flag | companion section |
| `cards[].deletedAt` | soft-deleted card | skipped |
| `cards[].card.uid` | **Scryfall printing id** | exact printing |
| `cards[].card.oracleCard.uid` | **Scryfall oracle id** | stable card identity |
| `cards[].card.edition.editioncode`, `card.collectorNumber` | set / number | printing fallback |
| `cards[].card.oracleCard.name` | card name | name fallback |
| `customCards` | user-made cards | imported as unresolved entries (name kept) |

## 3. Text export formats

Archidekt's export produces lines like:

```
1x Sol Ring (cmm) 410 [Ramp]
1x Atraxa, Praetors' Voice (2x2) 190 [Commander{top}]
1x Swords to Plowshares (sta) 10 *F* [Removal,Instant]
1x Opt (eld) 59 [Maybeboard{noDeck}{noPrice}]
2x Pyroblast (ice) 213 [Sideboard{noDeck}]
1x Delver of Secrets // Insectile Aberration (mid) 47 [Cantrips] ^Have,#37d67a^
```

Parsing rules:
- The quantity prefix (`1`, `1x`, `1 x`) is optional. `(SET)` or `[SET]` gives the set,
  followed by an optional collector number (`410`, `CLB-187`, `12a`, `★`).
- `*F*` means foil, `*E*` etched.
- `[A,B]` lists categories. The first category is the primary one. `{flags}` after a
  category are Archidekt category settings:
  - `{top}` marks the commander (premier) category;
  - `{noDeck}` means not in the deck (maybeboard);
  - `{noPrice}` is ignored.
- `^Tag,#color^` is an Archidekt label. It's kept as a tag.
- Plain section headers (`Commander`, `Mainboard`, `Sideboard`, `Maybeboard`) are also
  accepted, for lists copied from elsewhere.

Section mapping (in order):
1. The card is flagged companion, or a category is named Companion → **companion**.
2. The primary category is premier / `{top}` / named Commander → **commander**.
3. A category is named Sideboard → **sideboard**.
4. A category is named Maybeboard/Considering, or carries `{noDeck}` /
   `includedInDeck=false` → **maybeboard**.
5. Otherwise → **main**. The categories are kept as metadata either way.

## 4. Data model

`DeckEntry` gains:

| Field | Purpose |
|---|---|
| `oracle_id` | Stable identity that survives card-DB updates and printing changes |
| `printing_id` | Exact Scryfall printing (already existed) |
| `set_code`, `collector_number` | As requested by the source (already existed) |
| `finish` | `nonfoil` / `foil` / `etched` |
| `categories` | Archidekt categories (ordered; the first is primary) |
| `tags` | Archidekt labels (`^Have^`) |
| `resolution` | `exact` / `set` / `fallback` / `name` / `unresolved`: how the printing was chosen |
| `requested` | What the source asked for (name / set / number / Scryfall id) when it differs from what was resolved |

`Deck` gains:
- `source`: `{kind: "archidekt", id, url, name, updated_at, imported_at}`;
- `source_snapshot`: the normalized entries as imported, for diffing later;
- `categories`: the deck's category list with flags.

The `deck_cards` table gets new columns and `decks` gets new columns, both through
migration 3 of `app.sqlite`. Existing decks keep working.

### Resolution order (never fail a whole deck)

1. Scryfall printing id (JSON import), when it exists locally → **exact**.
2. Set + collector number → **exact**.
3. Set only → **set** (a warning if a number was requested).
4. Oracle id → default printing → **fallback** (with a warning naming the missing printing).
5. Name (normalized, faces, accents) → default printing → **name**.
6. Nothing matches → **unresolved**. The entry is kept with "did you mean" suggestions and
   the deck still imports.

### Surviving card-database updates

- Entries keep `oracle_id` as well as `printing_id`.
- When a deck is loaded and its `printing_id` no longer exists (Scryfall merged or
  removed a printing), the entry re-resolves by oracle id, and then by name.
- Image URLs are never stored in decks. Images are addressed by printing id through
  the local cache.

## 5. Export

`GET /api/decks/{id}/export?format=archidekt` produces:

```
1x Atraxa, Praetors' Voice (2x2) 190 [Commander{top}]
1x Sol Ring (cmm) 410 [Ramp]
1x Swords to Plowshares (sta) 10 *F* [Removal]
2x Pyroblast (ice) 213 [Sideboard{noDeck}]
1x Opt (eld) 59 [Maybeboard{noDeck}{noPrice}]
```

The export preserves quantities, names, printings, finishes, commander, sideboard,
maybeboard and categories. Round trips are tested: export, then parse, gives equal
entries. `format=plain` keeps the section-header format.

## 6. Source link and diff

- URL-imported decks remember their source. **Check source** fetches the current
  Archidekt deck and diffs it against `source_snapshot`, showing:
  - cards added and removed (by oracle id);
  - quantity changes;
  - printing changes;
  - category changes.
- **Apply** merges those remote changes into the local deck. Local-only edits are kept
  where they don't conflict. **Ignore** keeps the local deck and stores the new
  snapshot, so the same changes aren't reported again.
- Nothing is overwritten silently. Normal play never contacts Archidekt.

## 7. Offline guarantee and artwork

- Deck data lives entirely in `app.sqlite`. After import, Archidekt isn't needed.
- **Cache all artwork** (offered after import and on the deck screen):
  - starts a background job that downloads missing images for every printing in the
    deck, plus the tokens those cards create;
  - reports progress, is resumable, and skips images already cached.

## 8. Test fixtures

`backend/tests/fixtures/archidekt/`:
- `commander_export.txt`: a Commander deck with `{top}` commander, custom categories,
  set codes, collector numbers, foil/etched, a DFC, sideboard and maybeboard.
- `constructed_export.txt`: a 60-card deck with a sideboard and multiple printings of
  one card.
- `commander_deck.json`: the shape of the API response, based on real responses, with
  premier/noDeck categories, finishes, a DFC and a missing printing to exercise the
  fallback.

The tests prove that text/JSON → parser → local deck model keeps:
- quantities and sections;
- categories;
- printings, finishes and the commander.

They also prove that export → parse round-trips, and that fallbacks are reported rather
than failing the deck.

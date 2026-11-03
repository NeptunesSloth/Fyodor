# Deck text format

Fyodor reads the plain-text exports of Moxfield, Archidekt, MTGGoldfish, MTG Arena/MTGO,
Deckstats and hand-written lists. Text is never fetched online (only Archidekt links are: see
"Deck links"); names are resolved against the local card database.

## Card lines

| Example | Meaning |
|---|---|
| `1 Sol Ring`, `1x Sol Ring`, `Sol Ring`, `Sol Ring x1` | quantity (defaults to 1) and name |
| `1 Sol Ring (CMM)` / `1 Sol Ring [CMM]` | preferred set |
| `1 Sol Ring (CMM) 410` | exact printing (set + collector number) |
| `1 Sol Ring (CMM) 410 *F*` | Moxfield foil / etched flags (ignored) |
| `1x Sol Ring (cmm) 410 [Ramp,Artifact]` | Archidekt categories (ignored except `Commander`, `Sideboard`, `Maybeboard`, `Companion`) |
| `1 Krenko, Mob Boss *CMDR*` / `# !Commander` | commander markers |
| `SB: 2 Pyroblast` | MWS-style sideboard line |
| `Fire // Ice`, `Fire/Ice`, `Fire` | split / double-faced cards by full or face name |

Names are matched case-insensitively, ignoring accents and curly quotes (`Lim-Dul` finds
`Lim-Dûl`). When a set or collector number isn't found, the card's default printing is used.
Unknown names are kept in the deck (marked unresolved) with "did you mean" suggestions.

## Sections

Headers may be bare, end with `:`, be prefixed with `//` or `#`, or carry a count
(`Creatures (24)`):

- `Commander`, `Companion`
- `Deck`, `Main`, `Mainboard` and type headers (`Creatures`, `Lands`, …) → main deck
- `Sideboard`, `Maybeboard` / `Considering`, `Tokens`
- Arena `About` / `Name <deck name>` blocks set the deck name.

Without any headers, blank-line layout is interpreted:

- a final or first block of 1–2 cards in a ~100-card list → commander
- a trailing block of ≤15 cards after a ≥40-card block → sideboard (MTGGoldfish)

## Deck links

The host fetches one site's decks itself: Archidekt (`https://archidekt.com/decks/<id>/…` or the bare number, once per
import, through `app/decks/archidekt.py`). The other deck sites were checked from a host on 2026-11-03, one plain request
each with a User-Agent naming Fyodor (Archidekt's deck API answered 200 from the same host). None has an export the host may fetch, so a link from one of them is refused before
any network use, online or offline, with the reason and that site's steps (`app/decks/sites.py`, HTTP 422; the table
importer shows the same text as you type, `frontend/src/game/deckLinks.ts`). A link pasted alone into the list box gets
the same answer.

| Site | Export the site offers | What the host got | Fyodor says |
|---|---|---|---|
| Moxfield | none: More → Export builds the text in the browser from Moxfield's API, which needs a key | Cloudflare block page ("Sorry, you have been blocked", 403) on the public deck list | no public export link; More → Export → Copy Plain Text, then paste |
| MTGGoldfish | `/deck/download/<id>` (the deck page's Download menu: Text File (Default), Exact Card Versions, .dek, Moxfield) | robots.txt `Disallow: /deck/download*` for every agent; the download and `/deck/<id>` answer 403 `cf-mitigated: challenge` (JavaScript and cookies), while its home and archetype pages answer 200 | robots.txt and a browser check block programs; Download → Text File (Default), then paste |
| TappedOut | `<deck>?fmt=txt` | every page (home, search, the export) answers 403 `cf-mitigated: challenge`; robots.txt allows the path | a browser check in front of every page; add `?fmt=txt` in your browser, then paste |
| Deckstats | `<deck>?export_txt=1` | every page, robots.txt included, answers 403 `cf-mitigated: challenge` | a browser check in front of every page; add `?export_txt=1` in your browser, then paste |

Fyodor never tries to get around a browser check or a robots.txt rule. If a site later offers a public export the host
may fetch, it can join Archidekt in `import_any` (one fetch, the same timeout and size cap, parsed by this text parser).

## Limits

200,000 characters, 2,000 lines, 999 copies per line. Deck text is only ever parsed as data.

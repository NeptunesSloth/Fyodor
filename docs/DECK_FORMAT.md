# Deck text format

Fyodor reads the plain-text exports of Moxfield, Archidekt, MTGGoldfish, MTG Arena/MTGO,
Deckstats and hand-written lists. Nothing is fetched online; names are resolved against the
local card database.

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

## Limits

200,000 characters, 2,000 lines, 999 copies per line. Deck text is only ever parsed as data.

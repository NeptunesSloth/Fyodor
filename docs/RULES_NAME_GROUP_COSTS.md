# Name groups and alternative nouns in activation costs

Rules source: Comprehensive Rules effective 2026-09-25, stored in
`data/rules/comprehensive_rules/2026-09-25/comprehensive_rules.txt`.

## Rules question and authority

How should an activation enforce a requirement that its payment objects have the same
name or different names, and how should alternatives within a cost's noun phrase be read?

- CR 201.2 and 201.2a: use English names; same-name groups share at least one name.
  A nameless object never has the same name as another object.
- CR 201.2b: every member of a different-names group must have a name, and no pair
  may share a name. A split card can have multiple names (709.4a); face-down objects
  have none (708.2a).
- CR 118.3 and 601.2h, applied through 602.2b: costs must be payable in full;
  no mana, tap, discard, sacrifice, or counter removal is committed for an invalid group.
- CR 701.9a: discarding moves the chosen card from its owner's hand to their graveyard.
- CR 122.1: counters of different kinds are eligible when a cost says only “a counter.”

## Oracle examples and engine changes

`costs.CostComponent.names` records a whole-group constraint for fixed chosen discards
and sacrifices. `cost_payment` checks both availability and the actual selected group,
using the existing `card_names.names_of` helper. Same-name feasibility counts each
object once per name; different-name feasibility searches distinct nonempty name sets.
The ordinary cost decision/resume machinery remains responsible for private selections.

Real Oracle fixtures and gameplay scenarios cover:

- Sphinx of the Chimes: two nonland cards with the same name; draw four.
- Ormos, Archive Keeper: three cards with different names; draw five. Empty-library
  draws still replace each draw with five +1/+1 counters.
- Transmutation Font: sacrifice three artifact tokens with different names; search
  for an artifact and put it onto the battlefield. Its Blood/Clue/Food choices are tested.
- Chandra's Regulator: discard a Mountain card or a red card. Both descriptions use
  existing selector alternatives, and its loyalty-copy trigger is tested with payment
  accepted and declined.
- Soul Diviner: remove a counter from an artifact, creature, land, or planeswalker
  you control. The type list is normalized before splitting comma-separated payments.

## Edge cases, tests, and fallback

Tests reject duplicate names, two differently named nonlands for Sphinx, land payments
for Sphinx, overlapping split names, nameless objects, opponent-controlled permanents,
enchantments for Soul Diviner, and permanents without counters. Invalid selections
are also tested when another legal group is available. Gameplay scenarios verify replay
and save/load state round trips.

Name-group costs and alternate discard descriptions are activation-only: they do not
silently enable optional payments or mana abilities through simpler payment paths.
Unknown qualifiers, random name-constrained discards, and ambiguous plural alternatives
remain unsupported. This change does not automate the entire remaining partial-card pool.

## Validation

- 35 focused scenarios passed, including a private resumable payment prompt.
- 374 selected cost/activation regression tests passed (overlaps the focused scenarios).
- Ruff and mypy passed; mypy checked 346 source files.
- Whole-catalog comparison: exactly the five named cards became FULL; no previously FULL
  cards lost support. Current totals: 27,618 FULL / 4,450 PARTIAL. See `CURRENT_STATE.md`.

# Activated abilities borrowed from the public library top

Rules source: Comprehensive Rules effective 2026-09-25, stored locally.

## Rules question and current authority

Which activated abilities does a permanent gain from its controller's qualifying top card,
and what changes when the card, controller, or source object changes?

- CR 113.10a–c: gaining abilities, including activated abilities defined by another object.
- CR 201.5 and 201.5b: a source's name in its ability refers to that object; gained abilities
  use the gaining object where the source name refers to itself.
- CR 611.3a: a static ability's continuous effect applies while its source has the ability
  and is in the appropriate zone.
- CR 401.5–6: revealing the library top and changes to that top; libraries remain ordered.
- CR 400.7: a card changing zones becomes a new rules object.

## Oracle examples and engine implications

Conspicuous Snoop borrows activated abilities from a Goblin on top of its controller's library;
Skill Borrower borrows from an artifact or creature. Both reveal that top publicly. The parser
recognizes this exact public-top grant and reuses `abilities_of` selectors and lending logic.
Every collection re-reads the current top and controller. Existing lender object indices and
source-name rebinding handle changes without new GameState fields.

Voodoo Doll's counter-defined activation cost reads pin counters on Skill Borrower when its
ability is borrowed. A manual linked loan such as Prototype Portal retains the existing
fallback, and does not obtain a misleading automatic X cost from unrelated exile records.
Unknown top-grant forms and private-top grants retain their fallback.

## Edge cases and deterministic validation

15 focused scenarios passed, with replay and save/load checks: both cards' FULL coverage,
public visibility, changed top, wrong type, empty library, stale ability index, summoning
sickness, controller change, a top card leaving and returning as a new object, Snoop casting
the Goblin, Skill Borrower's mana ability, counter-relative X, and linked-ability fallback.
316 selected borrowed-ability, static, layer, permission, and defined-X regression tests
passed (overlapping the focused suite). Ruff, mypy (348 source files), and whitespace checks
passed. Inventory: exactly two promotions, no lost FULL cards, 27,635 FULL / 4,433 PARTIAL.

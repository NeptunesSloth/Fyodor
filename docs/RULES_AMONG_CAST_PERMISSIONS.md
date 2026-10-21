# Casting spells from among exiled cards

Rules source: Comprehensive Rules effective 2026-09-25, stored locally.

## Rules question and authority

How do temporary permissions distinguish spells from lands, color from type, and one spell
from unrestricted casting across a set of cards?

- CR 601.3: a permission changes where a spell may be cast; ordinary timing and other
  casting restrictions still apply unless explicitly changed.
- CR 609.4b: spending mana as though it were any color/type changes how a cost can be paid,
  not the mana actually spent. “Any color” does not substitute colored mana for required {C}.
- CR 305.2: a spell-only casting permission grants no permission to play a land.
- CR 611.2a and 400.7: the permission has its stated duration and applies to the cards as
  the objects identified by the effect.
- CR 607.2a: linked permissions refer to cards exiled by the linked ability.

## Oracle examples and engine implications

The existing `AMONG_GRANT` grammar now accepts stated durations, singular qualified spells,
and the existing mana-spending modifiers. It emits ordinary `grant_play` data with `play=False`,
a spell filter when specified, an optional one-cast group limit, and the stated spend mode.
It reuses existing object-bound permissions, expiry, filters, and grouped consumption.

- Stolen Strategy: cast the cards exiled from opponents' libraries this turn, spending mana
  as though it were any color. Its permission does not permit playing lands.
- Laughing Jasper Flint: the same shape with “mana of any type”; exiles one card per outlaw,
  including borrowed creatures that its static ability makes Mercenaries.
- Chandra, Hope's Beacon: one instant or sorcery spell total across all five exiled cards,
  through the end of the next turn; neither permanent spells nor lands qualify.
- Serpent's Soul-Jar: each activation costs tapping and 2 life and grants one creature cast
  from the linked exiled cards for that turn. A subsequent paid activation has a new limit.

No new GameState fields or permission types were added. Unknown spell filters, invalid
singular/plural combinations, and unsupported combinations retain their manual fallback.

## Validation

16 focused gameplay scenarios passed, including replay and save/load checks. They cover
colorless costs, land denial, permission expiry, source departure, unauthorized card owners,
three-player theft, borrowed Mercenaries, Chandra's shared limit/duration and first-spell copy,
and Soul-Jar's Elf deaths, non-Elf exclusion, life payments, and repeated paid activations.

294 selected permission and casting regression tests passed (overlaps the focused suite before
the additional Soul-Jar scenario). Ruff and mypy (348 source files) passed. The whole-catalog
comparison found exactly these four promotions and no lost FULL support: 27,633 FULL / 4,435
PARTIAL. See `CURRENT_STATE.md`.

# Emblems granted as a permanent transforms

Research date: 2026-10-19; rules source: stored Comprehensive Rules 2026-09-25.

Sephiroth, One-Winged Angel has:

> Super Nova — As this creature transforms into Sephiroth, One-Winged Angel, you
> get an emblem with "Whenever a creature dies, target opponent loses 1 life and
> you gain 1 life."

This is a static ability, not a "when" or "whenever" triggered ability. It does
not create a stack object that Stifle could counter. CR 113.9 states that static
abilities do not use the stack and cannot be countered.

The [actual default printing's official rulings](https://api.scryfall.com/cards/7cb5acb6-14af-4e17-8e6c-b44122bd81e4/rulings)
were fetched with `curl` and retained at `/tmp/fyodor-sephiroth-rulings.json`.
The rulings dated 2025-06-06 explicitly state that entering with the back face up
is not transforming and does not grant an emblem. They also confirm that a
copy token of a double-faced card has both faces and can transform, and that
simultaneous deaths of Sephiroth and other creatures can trigger its front
ability but cannot transform the departed object.

CR 701.27a-d restricts what can transform; 701.27f prevents a stale activated or
triggered ability from transforming its source again after an intervening
transformation. CR 712.18 preserves object identity and continuous effects during
a transformation. CR 712.13-14 distinguishes entering with a face up from an
actual transformation. CR 114.1-4 governs emblem creation, ownership/control,
and persistence; 113.6p permits emblem abilities to function in the command zone.

The becoming face is examined with continuous effects applied during the
turnover. Its controller receives the emblem immediately, before state-based
actions or triggered abilities are processed. A continuing copy effect or loss
of abilities can therefore suppress the printed back-face ability. The
controller of a spell that causes the transformation does not receive an emblem
in place of the permanent's controller. Turning back to the front grants no
emblem; transforming into the back again grants another. The emblem continues
to function after Sephiroth leaves, and its creature-dies ability includes
Sephiroth's own death.

The general replacement rules in this snapshot explicitly discuss entering and
turning face up (614.1c-e); they do not explicitly list "as transforms into."
Those entry-specific provisions should not be quoted as though they directly
specified this wording. The implementation follows the Oracle instruction as
an atomic part of the actual transformation, rather than creating a triggered
ability or treating entry with the back face up as a transformation.

The engine has two actual transformation paths: `keyword_actions.transform` and
`designations.day_night_sync`. A shared hook belongs after the validated face
turnover and before the transformation event is emitted. The day/night path
must omit it for an entrant that is merely entering with its back face up.
Existing emblem construction and command-zone event watchers can be reused.

The copied-token gameplay case also exposed a shared transformation eligibility
check that excluded every token represented by a card printing. Such a copy
of a DFC has two physical faces under CR 707.8a. The eligibility check now accepts
card-backed DFC tokens while retaining the physical layout and other-face
permanent checks. An ordinary single-faced token and a single-faced Spark Double
copy of Sephiroth remain unable to transform. The Irenicus copy test verifies
that its nonlegendary and flying copy exceptions persist through both turns.

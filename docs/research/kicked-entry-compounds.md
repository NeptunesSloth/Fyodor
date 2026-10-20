# Compound kicker entry effects

Current canonical Ravaging Riftwurm, Voidpouncer, Prison Barricade, and Dralnu's
Pet reuse ordinary kicker payment and entry replacements (CR 702.33e, 614.1c).

The bounded `kicked_entries` parser supports additional time counters, a pair of
counter kinds plus a keyword, and a keyword plus counters sized by a discarded
card's mana value. Every child counter part carries the kicker condition; all
parts pass through the native entry-counter batch and replacement planner.
Riftwurm's three additional counters add to its intrinsic vanishing two.

Entry keyword grants test their payment condition independently of the number
of counters. A kicked Dralnu's Pet gets flying even if a zero-mana-value creature
was discarded or Solemnity prevents its counters. Payment records retain the
exact discarded object's mana value for last known information when it leaves
the graveyard before the spell resolves. Copies inherit this cost-object data.

Prison Barricade's quoted permission remains an ability added in layer 6. The
quoted-ability validator accepts only the native self-only defender permission;
the combat rules read that permission from current abilities, so later ability
removal removes it. It is not saved as a permanent independent rules override.

Canonical tests compare kicked/unkicked casts, intrinsic and additional time
counters, both Voidpouncer counter kinds, zero-value discards, Solemnity,
Doubling Season, and later Humility. A real opponent Reanimate (with Vedalken
Orrery) returns the discarded Phantasmal Image as a five-mana-value Air Elemental
while Pet is pending; Pet correctly retains the original discarded value two.
That nested entry choice is resumed after JSON reload, and histories replay.

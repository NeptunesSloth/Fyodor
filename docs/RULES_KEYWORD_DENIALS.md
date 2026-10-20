# Keyword loss and prohibition

Arcane Lighthouse fixes its affected creatures when its ability resolves (CR 611.2c).
They lose hexproof, its quality variants, and shroud until end of turn, including if
control changes or Lighthouse leaves. New entrants and new incarnations are unaffected.
Existing keyword counters remain and their abilities return after the prohibition ends.

A prohibition wins over later grants (CR 101.2), including static Equipment grants.
Abilities that resolved effects would grant while prohibited are not created for the
affected object; other parts of the effect still happen. `ContinuousEffect.blocked_keywords`
defaults empty for old saves and retains this creation-time restriction per object. This
also covers animation effects and quoted keyword abilities. Static grants resume when
the prohibition expires; a prohibited resolved grant cannot appear later instead.

Twelve focused tests are included in 177 passing selected regressions. Gameplay scenarios
check replay/save-load and cover both hexproof forms, shroud, Equipment, later entrants,
blink, control changes, counters, Blossoming Defense's remaining pump, and Lumbering Falls
animations. Two isolated layer tests additionally check indefinite and quoted grants
across serialization and expiration without introducing invented Oracle fixtures.
Ruff and mypy (352 files) passed. Official rulings are mirrored in
`research/hexproof_targeting_rulings.json`.

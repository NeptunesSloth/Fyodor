# Remaining Spree resolution rules

Sources: current Oracle and Scryfall official ruling feeds for Getaway Glamer
(69689049-a704-4f16-84ee-4d5d915028ec) and One Last Job
(71bfbfae-e7eb-4f80-81c6-9ab6a1bbd39d), accessed 2026-10-19.

Getaway Glamer may target any creature with its second mode. Compare current
power with every other creature only when that instruction resolves (CR
608.2c). Ties qualify. Its first mode resolves before that comparison, so
exiling the greatest-power creature can make the second target qualify.

One Last Job's third-mode creature host is not a target. Choose it during
resolution, after creatures from earlier modes entered. Hexproof/shroud do
not prevent this choice, but enchant/equip restrictions and protection do
(CR 303.4f, 303.4i, 301.5e, 702.16). No legal host leaves the Aura in its
previous zone; Equipment can enter unattached. A returned noncreature Vehicle
cannot be crewed between modes, since nobody gets priority during resolution.
All selected modes retain ordinary target legality and printed order.

Reusable representation: a resolution-only target maximum-stat
condition (the ordinary trailing-if binder binds its object to the selected target); per-entry host_choice selector in the existing suspension-aware
attachment entry pipeline. Neither creates extra targets.

The entry host selector is retained through the existing Aura-entry decision and
validated again on resume. Host choices are mandatory if legal hosts exist, and
are filtered both by attachment legality and the specified controller/creature
selector. This preserves replacement entry choices and simultaneous move data.

# Timing, casting limits, and cost modifiers from emblems

The supported static-rule scanners now include genuine command-zone emblems for
loyalty timing, casting restrictions, and spell-cost modifiers, alongside the
previous spell-keyword and casting-permission kinds. Emblem text validation
accepts exactly these runtime-supported kinds (CR 114).

Teferi, Temporal Archmage grants instant-speed loyalty activation to controlled
planeswalkers. This changes timing, not priority, loyalty costs, or the usual
once-per-turn restriction (CR 606.3). The new all-planeswalker rule checks current
derived type: a planeswalker animated by Sarkhan the Masterless still has its
loyalty abilities but no longer qualifies for this emblem's timing exception.
Existing self-only Teferi and Oath of Teferi behavior remains unchanged.

Narset Transcendent's emblem applies the ordinary noncreature-spell prohibition
to its controller's opponents. Saheeli, Filigree Master's emblem combines the
existing artifact-creature anthem with the native artifact-spell generic cost
reduction. Each rule continues after the planeswalker leaves.

Ten canonical checks cover the real ultimate costs, source departure, opponent
turns, responding with loyalty abilities, once-per-turn limits across multiple
emblems, current control/type, Sarkhan's animation, artifact versus creature
filters, costs, saves and history replay. The previous nine behavioral/coverage
checks and 52 related loyalty regressions passed together; the final ten-case
suite also passed after Narset's separate rebound rule was completed.

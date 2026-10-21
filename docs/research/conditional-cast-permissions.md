# Conditional self casting permissions

Undead Sprinter, Demilich, Sproutback Trudge, Qasali Ambusher, and Lightwheel
Enhancements compile to the existing permission, condition, additional-cost and
paid immediate-cast paths. No new payment solver or callback registry is used.

Undead Sprinter checks the native frozen death history, excluding Zombies, and
attaches its counter only to the original card cast through that permission.
A real Double Major copy receives no permission-consequent entry counter.
Demilich pays the existing four-card atomic exile cost, with the Oracle
instant-and/or-sorcery phrase normalized to the native selector union.

Lightwheel uses the live max-speed condition in the graveyard. Qasali requires
an actual attack on its caster and lands with both basic land subtypes; one
Temple Garden satisfies both. Its conditional free permission also supplies
flash while the condition holds. Normal hand permissions retain native timing.

Sproutback is a graveyard-only end-step watcher. Its exact original graveyard
object enters the native optional paid cast continuation during resolution,
with normal life-gained cost reduction. Declining grants no later permission;
exiling that source before resolution leaves no card to cast. The shared
free-cast pool accepts only the existing exact self_gy resolver.

26 canonical gameplay/coverage tests pass, including a fresh Python process
resuming Demilich's four-of-five cost choice, JSON/history replay, source exile,
copy identity, real deaths, real combat, max-speed boundaries and live timing.
Related native permission/graveyard/speed/copy regressions are running.

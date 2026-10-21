# Targets added by multikicker

Research date: 2026-10-19. Rules source: stored Comprehensive Rules 2026-09-25.

Comet Storm's Oracle text is:

> Multikicker {1} (You may pay an additional {1} any number of times as you cast this spell.)
> Choose any target, then choose another target for each time this spell was kicked.
> Comet Storm deals X damage to each of them.

Strength of the Tajuru has the same targeting structure for creatures, followed
by putting X +1/+1 counters on each of them.

The [actual Comet Storm printing's rulings](https://api.scryfall.com/cards/bb5f586d-6bf0-4590-ad73-2d46b2a45b1a/rulings)
were fetched using `curl` and retained at `/tmp/fyodor-comet-storm-rulings.json`.
The relevant official rulings dated 2010-03-01 state:

- Each target must be different.
- The number of targets is one more than the number of times the spell was
  kicked. X and the number of kicker payments are announced first, then targets
  are chosen, then costs are paid, without a response window between these steps.
- X = 4 with two kicker payments deals four damage to each of three targets and
  costs {6}{R}{R} before other cost modifiers.
- If some targets become illegal, each remaining legal target still receives X
  damage.

CR 702.33c defines multikicker as an additional cost payable any number of times;
702.33d records multiple kicker payments. CR 601.2b-c orders these announcements
before target selection. CR 115.3 and the explicit word "another" require distinct
targets. CR 608.2b rechecks target legality on resolution; if every target is
illegal, the spell does not resolve. CR 707.10 copies X, additional costs, and
targets. Choosing new targets for a stack copy changes targets while preserving
the number chosen for the original spell (707.10c, 115.7).

The parser produces one target group with an initial count of one and a typed
`per_kick_targets` increment. `language.simple` preserves this metadata instead
of collapsing the group to a plain single target. At casting, the shared kicked
target planner materializes an exact count of 1 + the announced kicker count and
removes the increment marker. The stack therefore stores concrete group limits,
which copies and retargeting retain. Existing target validation, simultaneous
damage, counter placement/replacements, cost payment, and replay are reused.

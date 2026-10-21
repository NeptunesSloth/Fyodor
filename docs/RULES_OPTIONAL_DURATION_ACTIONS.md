# Optional actions with scoped durations

Rules source: Comprehensive Rules effective 2026-09-25, stored locally.

## Rules question and authority

Does a duration marker before an optional continuous effect prevent its following
“If you do” consequence from being automated?

- CR 118.12: the action is a resolution-time cost; the consequence checks the choice to pay,
  regardless of what events actually occurred.
- CR 611.2b: a “for as long as” effect does nothing if its duration already ended before
  it would first apply. Ending that duration does not let it restart on a new object.
- CR 509.3g: attacks-and-isn't-blocked triggers fire during declaration of blockers, including
  when nothing blocks; removing blockers later does not create this trigger.
- CR 510.1a: the attacker assigns its power as combat damage unless an applicable effect
  changes that assignment.
- CR 400.7 and 608.2b: source/target zone changes create new objects, and an ability with
  all targets illegal does not resolve.

## Oracle example and implementation

Orcish Squatters may gain control of a target land the defending player controls for as long
as its controller controls Squatters. Choosing the action also suppresses Squatters' combat
damage for the turn. The grammar previously rejected the existing `until` duration marker
when checking whether the optional action could support an “If you do” clause.

The check now unwraps one complete, nonempty scope before classifying its actions. It keeps
all original effects and duration data for resolution. Unknown actions, incomplete scopes,
and empty scopes retain their fallback. No new runtime primitive or GameState field.

## Edge cases and validation

Eight focused scenarios passed with replay and save/load checks: FULL coverage, accepting
and declining, damage assignment, persistence across turns, source departure or control
loss, source return as a new object, target departure/return, and a duration already ended
before resolution. Manual table edits are followed by an engine rules check before asserting
expired control state.

227 selected optional-action and duration regression tests passed (overlaps focused tests).
Ruff, mypy (333 app files), and whitespace checks passed. Whole-catalog comparison found
only Orcish Squatters promoted and no lost FULL support: 27,636 FULL / 4,432 PARTIAL.

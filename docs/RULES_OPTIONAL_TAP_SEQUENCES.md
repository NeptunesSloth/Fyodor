# Optional tap-or-untap sequences

Rules source: Comprehensive Rules effective 2026-09-25, stored locally under
`data/rules/comprehensive_rules/2026-09-25/`.

## Rules question and authority

How should independently optional tap-or-untap instructions retain their targets,
pronoun bindings, and choices inside longer abilities?

- CR 601.2c and 603.3d: spell/ability targets are chosen before resolution choices
  and before any optional payment during resolution.
- CR 608.2b: illegal targets are skipped; if every target is illegal, the spell or
  ability does not resolve.
- CR 608.2c–d: apply instructions in order and make resolution choices when reached.
  Declining one optional instruction does not decline the next instruction.
- CR 701.26a–b: use the existing tap and untap actions. The existing untap choke
  point also handles stun counters (122.1d).
- CR 702.99: cipher encodes the original spell card; combat damage permits casting
  a copy, which chooses its own targets.

## Oracle examples and engine implications

- Hidden Strings and Toils of Night and Day each say “You may tap or untap target
  permanent, then you may tap or untap another target permanent.” The parser emits
  two existing `tap_or_untap` instructions, each independently optional, and two
  mandatory target groups. The second explicitly excludes the first target.
- Vedalken Anatomist first puts a -1/-1 counter on target creature, then optionally
  taps or untaps that creature. The existing pronoun binder now accepts this action.
- Telekinetic Bonds permits payment after a discard trigger, followed by an optional
  tap or untap. Its target is selected when the trigger is put on the stack; payment
  does not force the subsequent optional action.

Changes reuse `tap_or_untap`, target groups, optional payments, and existing resolution
continuations. No new state fields, runtime text execution, or card-name exceptions.
The parser only accepts recognized object references and the complete two-permanent
sequence. Different subjects, unrecognized sequences, or ambiguous pronouns remain
unsupported.

## Scenarios and validation

The focused suite uses real Oracle fixtures and checks replay plus save/load round trips.
It tests independent declines, distinct targets, either target becoming illegal, all targets
becoming illegal, the counter/optional-action sequence, payment accepted or declined,
payment followed by declining the action, and Hidden Strings encoding and casting a copy
with two independently selected targets. It also checks that a creature reduced to zero
toughness remains available for the rest of the resolving ability before state-based actions
(CR 704.4).

19 focused scenarios and 376 selected regression tests passed (overlapping sets); Ruff and
mypy (346 source files) passed. The catalog comparison found exactly the four named
promotions and no lost FULL support: 27,622 FULL / 4,446 PARTIAL. See `CURRENT_STATE.md`.

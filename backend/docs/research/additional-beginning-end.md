# Additional beginning phases and end steps

Current Oracle and official rulings accessed 2026-10-19:
- Sphinx of the Second Sun: https://api.scryfall.com/cards/be2d74cd-76fb-4bca-99b5-07749aef4d06/rulings
- Y'shtola Rhul: https://api.scryfall.com/cards/aef218fa-13a4-4653-95d6-6b3ef1b33a92/rulings
- CR 500.8-9: extra phases/steps go immediately after the designated phase/step;
  the most recently created at the same boundary happens first.

Sphinx triggers at every postcombat main phase, including extra main phases,
and even if nobody attacked. Its additional beginning phase contains actual
untap/upkeep/draw steps. Phasing, untap restrictions, stun/exert and untap
choices apply. There is no untap priority (502.4). Upkeep/draw triggers and the
normal turn-based draw happen. No new main phase follows: continue to the
previously scheduled next phase, ordinarily ending. The active player and turn
number do not change; turn history, spells cast, land/loyalty/once-per-turn
limits and until-next-turn effects persist.

Y'shtola adds an end step only if its first-end-step trigger resolves with a
legal target. Blink happens before the first-step condition. All end-step
triggers fire again in the additional end step; its newly triggered ability
blinks but does not add a third end step. Illegal sole target means no extra
step. Delayed next-end-step triggers created during the first end step fire in
the additional end step. No intervening cleanup: damage and turn-long effects
persist until actual cleanup after the last end step.

Existing engine queue supports extra combats/main phases, but only consumes
at main/combat boundaries. Extend it for real beginning completion and end
step boundaries, preserving latest-created-first ordering and existing combat
queue tags. The normal new-turn operation cannot implement extra untap: it
increments turns, resets history and expires effects. Reuse untap machinery
with an explicit same-turn continuation, including choice suspension, phasing,
restrictions, stun, exert, next-untap effects and Seedborn Muse.

Chronology is also required. delayed._step_due currently compares positions
in PHASES, so it cannot recognize next end step created during an earlier end
step, nor an extra upkeep after main phase. permissions next-end-step has a
similar turn-number adjustment. Introduce saved step-occurrence chronology
with conservative old-save fallback; do not infer chronology from phase names.

Implementation uses a saved monotonic step_serial and per-turn step_counts.
Delayed abilities store created_step; before a step changes, legacy constructor
paths without it are stamped with the outgoing serial. Next-end-step play
permissions store granted_step, so the next actual occurrence ends them even
within the same turn. Old saves without metadata retain their future-step
behavior. The extra untap passes same_turn through both optional-untap and
untap-limit continuations. It avoids next-turn expiry/history/turn-order work.
The first draw-step skip in a two-player first turn applies only to the first
actual draw step, rather than every additional beginning phase that turn.

Canonical regressions cover printed-order queue insertion, actual Phyrexian
Arena/Howling Mine triggers, Hollow Trees' keep-tapped/storage counter choice,
Winter Orb's untap limit, stun and Sandbar Crocodile phasing, Teferi's
Protection duration, a Slaughter Pact due in the added upkeep, Opera Love Song
permission expiry and Getaway Glamer's added-end-step delayed return.

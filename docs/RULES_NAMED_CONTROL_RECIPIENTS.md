# Named control recipients and unblocked batches

Rules source: Comprehensive Rules effective 2026-09-25, stored locally.

## Rules question and current authority

Which player gains control when an effect says “that player,” including after casting,
damage, targeting, an unblocked attack, or an explicit choice?

- CR 608.2c: instructions execute in printed order and references use the identified player.
- CR 608.2h: required source information uses current information or appropriate last known
  information; the effect does not choose a new recipient merely because control changed.
- CR 603.2c and 509.3g: “one or more” is one trigger for the matching unblocked batch,
  during declaration of blockers, not an attack trigger or a later removal of blockers.
- CR 506.4: changing an attacker's controller removes it from combat, without changing the
  player already captured by a trigger.
- CR 400.7: a source leaving and returning is a new object.
- CR 102.2 and 806.1: other players are opponents in supported free-for-all games.
- CR 705.2: only the flipper wins or loses the flip; later conditional instructions use that result.

## Oracle examples and implementation

`gain_control.to` now accepts the previously named player through the same antecedent binder
used by player instructions. It handles prior player targets, explicit choices, and event
players; ambiguous references retain their fallback. Event-player validation includes transfer
recipients. Existing control layers, recording, and object binding do the actual transfer.

Coveted Jewel's opponent-controlled unblocked creature batch captures the attacker once and
draws before transferring and untapping the Jewel. The parser handles its shared-subject
sentence before resolving the final pronoun. Drooling Ogre uses the artifact caster;
Fractured Loyalty uses the targeting spell/ability controller; Crag Saurian uses the damaging
source's controller. Discerning Financier and Goblin Festival choose another player during
resolution, with Festival's choice occurring only after a lost flip.

No new GameState fields. Unsupported choices and unbound or ambiguous recipients remain manual.

## Edge cases, deterministic tests, and coverage

20 focused scenarios passed, all gameplay cases replayed and save/load checked. Cases include
three-player recipient choice and simultaneous combat triggers, multiple unblocked attackers,
a mix of blocked and unblocked attackers, source departure/return, changed attacker control,
Aura departure, both coin outcomes, and unbound-recipient refusal.

443 selected control, combat, event, player-reference, choice, and coin regression tests passed
(overlaps focused suite). Ruff, mypy (348 app/tools files), and whitespace checks passed.
Inventory found exactly the six named promotions and no previously FULL cards lost support:
27,642 FULL / 4,426 PARTIAL. This does not complete all-card automation.

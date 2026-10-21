# Goblin Welder: target dependency and simultaneous moves

Oracle text was checked against
[Scryfall's printing](https://api.scryfall.com/cards/17cd920a-de09-454a-a9da-c84512e3aff1) and
[official rulings](https://api.scryfall.com/cards/17cd920a-de09-454a-a9da-c84512e3aff1/rulings).
The official ruling explicitly requires **both targets to remain legal**. If
either becomes illegal, neither permanent is sacrificed nor returned. This is
an additional restriction beyond CR 608.2b's ordinary partial resolution.

The battlefield artifact may belong to anyone; the second target must be an
artifact card in its current controller's graveyard. A stolen artifact therefore
names its controller's graveyard, rather than its owner's. If that artifact
changes controller before resolution, the graveyard relationship is checked
again. A target that left and returned is a new object (CR 400.7).

The two actions are simultaneous. They are not an exchange keyword action,
and returning the graveyard artifact is not contingent on successfully
sacrificing the battlefield artifact: follow both instructions as far as
possible (CR 609.3). A prohibition against causing a sacrifice can leave the
outgoing artifact in place while the other returns. Grafdigger's Cage can stop
the return of an artifact creature without stopping the sacrifice.

## Existing engine pieces

- Two target groups and explicit `of: 0` can express the relationship using
  `player_relative.bind_what`. The second selector's `zone_owner` is
  `that_player`; the first group's artifact determines that player. The normal
  automatic linker currently recognizes opponent-controlled permanent groups,
  so a Welder parser should provide this dependency explicitly.
- The ordinary resolver removes illegal refs from each group. The new effect
  must require exactly one legal ref in each before doing anything.
- `triggers.sacrificing` records the sacrifice designation, including when a
  replacement sends the artifact elsewhere.
- `attachments.enter` collects entry choices and prohibitions;
  `replacements.entry_plan` computes entry modifications;
  `replacements.move_together` commits same-destination battlefield entries.

## Shared movement gap

The current Move action accepts one destination zone, with per-card controller
overrides only for battlefield entries. `MoveData.destinations` is server-owned
resolution data used by stack resolution, and normal moves do not honor it.
`Plan.do` applies zone replacements against the single `to.zone`, and the normal
resolver discards supplied resolution data. Thus injecting `r.destinations`
would neither implement a reliable mixed move nor preserve replacement rules.

A reusable mixed-destination operation needs to prepare the outgoing zone
replacement and incoming entry choices before moving either target, then
commit one zone event with a complete pre-event capture. Entry replacements
must still see continuous effects of the outgoing artifact (CR 614.12).
Entering and dying triggers must use the correct before/after table:
CR 603.6a and 603.10/603.10a. Simply sacrificing first and then calling
`attachments.enter` produces a different game state and separate event batches.

## Required gameplay checks

- A normal swap for each player's battlefield/graveyard; controller versus owner.
- Mismatched graveyard targets rejected before activation, and insufficient target
  availability reflected by the action menu.
- Either target leaving, blinking, gaining shroud/protection, or changing its
  required type; changing the battlefield artifact's controller.
- Both targets legal with sacrifice prohibited, return prohibited, and replacement
  exile; neither outcome should be treated as a payment for the other.
- Incoming artifact's entry choices and counters checked with outgoing static
  effects still present; all choices made before either object moves.
- Incoming death watcher must not see the outgoing artifact die. Outgoing entry
  watcher must not see the incoming artifact enter. Correct ETB/dies events share
  one simultaneous zone event.
- Activated ability survives its source leaving; source can itself be the target
  artifact if it is an artifact.
- Replay and save/load while targets and entry/replacement choices are pending.

## Implemented shared operation

`simultaneous_moves` now prepares both outcomes before committing a single Move
with optional per-card `routes`. Existing moves retain their original path.
The effect carries the outgoing request through ordinary entry-choice resume
contexts. A 616.1 choice stores candidate replacement snapshots before either
target moves. Graveyard replacements, prohibitions on sacrificing, and
prohibitions on entering affect their respective part independently.

The entry counter plan is frozen on a scratch entry with the outgoing permanent
still present. This preserves both count values (such as Investigator's Journal)
and counter prohibitions (such as Solemnity made an artifact by Mycosynth
Lattice). The actual move captures all outgoing and incoming changes together;
its counter actions then use the already prepared plan.

The generic triggered-ability watcher interval now distinguishes the side of
this shared event. A source entering in the event did not exist for a death,
sacrifice, or other look-back trigger (CR 603.10). A source leaving in the event
is absent for the incoming object's ETB. A card-put-into-graveyard-from-anywhere
trigger still uses the post-event table (CR 603.6c). Gameplay regressions cover
incoming Marionette Master, outgoing Reckless Fireweaver, and incoming The
Gitrog Monster to distinguish these cases.

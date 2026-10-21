# Latest-mill pairs and mandatory repeats

Reserved family: Grindstone and Sphinx's Tutelage, plus the I–III chapter ability
of The Tale of Tamiyo. Tamiyo's IV chapter has a separate unresolved card-copy
casting feature, so supporting this family alone cannot make Tamiyo FULL.

## Rules and existing infrastructure

[Grindstone's official rulings](https://api.scryfall.com/cards/0f15505d-b32f-4b71-8b99-f27bc964c5a8/rulings)
confirm that the process can repeat any number of times and that two colorless
cards do not share a color. Color sets must intersect; merely both being colored
or having two colors in their union is insufficient. Tutelage requires a pair
of nonland cards. Tamiyo requires a shared card type, then draws before repeating.

CR 701.17b mills as many cards as possible from a short library, and milling an
empty library does not itself lose the game. CR 701.17c permits an effect to find
a milled card in another public destination. Replacement and revealed/self-shuffle
cases need deliberate last-known-information treatment rather than assuming all
selected cards arrived in a graveyard.

Bruvac changes the number milled. The condition asks whether two qualifying cards
were milled; in an expanded batch it should detect any qualifying pair, rather
than requiring exactly two cards in the entire batch. Use only the latest
iteration's binding, never all cards milled earlier by the same resolving ability.

`effects.mill` already takes selected-card snapshots before self-shuffle replaces
a move and binds the resulting objects. `context.infos` and `this_way` supply
snapshot access. A reusable predicate can count each distinct color/type once
per qualifying card and succeed if any property occurs on at least two cards.
The nonland qualifier is applied before building these counts.

`loops.py` already parses repeat spans and fixed/conditional repeats. It unrolls
the saved effect list on each iteration and silently stops at CAP=1000. That cap
is not a Magic rule and must not be used to declare this family complete.
`engine.repeat_sequence` is a different shortcut: it refuses random/choice
sequences and explicitly does not infer infinite loops.

## Safe staged implementation

1. Add a typed latest-mill pair predicate with canonical gameplay tests for
   intersections, colorless cards, nonland filtering, type sharing, short and
   empty libraries, and Bruvac-expanded batches. Keep coverage PARTIAL until the
   repeat's mandatory outcomes and continuations are supported.
2. Use a bounded iteration budget only as a resumable checkpoint. At the budget,
   preserve the target, source object, most recent batch binding, process span,
   and remaining resolving instructions in a saved decision. Continuing must
   resume the same ability; reaching a budget must never finish the ability,
   award a win/loss, or present a game choice to stop a mandatory process.
3. Wait for every pending 616.1 zone-replacement choice before testing the batch
   or milling again. Existing `effects.mill` can leave held zone moves in
   `pending_616` and continue; that behavior is insufficient for this predicate.
   Painter + Progenitus + Rest in Peace supplies competing shuffle/exile outcomes
   and tests this boundary. Preserve candidate snapshots and resume all remaining
   instructions after the selected outcomes, rather than reevaluating stale refs.
4. Add explicit draw/adjudication state and finished-game handling separately.
   Current RulesState has `winner` and per-player `lost`, but no draw outcome.
   A draw must not be represented by falsely marking every player as losing.
   Any new optional state field needs safe defaults for old saves and appropriate
   views, handlers, finished checks, and display behavior.

## Mandatory loops and adjudication

The current repository CR numbers shortcut/loop rules **732**, not 727 (727 is
Restarting the Game). CR 732.4 / 104.4b says a mandatory unbreakable loop draws
the game. CR 732.3 requires an involved player to change a choice when a
fragmented loop repeats. CR 732.5 does not require unrelated actions to end a
loop. An optional action is not automatically a mandatory draw.

Do not infer an unbreakable loop from merely observing an equal library size,
a repeated fingerprint, or repeated random outcomes. A shuffle can return to
the same state by chance while a later outcome could still terminate the process.
Competing replacement choices can supply a legal way to change the sequence.

A narrow provable example is Painter with exactly two publicly revealed,
mandatory self-shuffling cards remaining, where every order produces a shared
pair and both cards necessarily return to that same library. More general states
need a saved adjudication flow that distinguishes continue-resolving from a
supported mandatory-draw finding; it must not fabricate a stop choice.

## Gameplay matrix

- First pair matches, next pair does not; repeated matching pairs; different
  nonempty colors; two colorless cards; multicolor overlap; colored land pair.
- Tutelage excludes land cards even when Painter makes them colored; Grindstone
  accepts them. Tamiyo matches card types, independently of colors.
- Bruvac mills four and detects a pair anywhere in that batch.
- Empty/one-card libraries stop without a draw or loss.
- Rest in Peace public exile, Gaea's Blessing queued trigger, self-shuffle, and
  competing 616 choices. Triggers wait until the whole ability finishes.
- Target/source departure and object identity, replay/save/load at replacement
  choices and iteration checkpoints, no priority or mana actions during a pause.
- A library large enough to exceed one processing budget resumes exactly; the
  budget is never a rule-based stopping point.

## Implemented

`mill_pair_repeat.py` owns three typed primitives: mill a fresh batch, test its
shared property, and rewind a fixed instruction span. The saved instruction list
never grows. At 32 repeats, or before approaching the ordinary action budget,
a saved continuation offers only “Continue resolving”; no player receives priority
or an option to stop a mandatory process. Optional replacement decisions retain
their real choices. Empty and short libraries stop normally.

All zone replacement destinations are prepared before any selected card moves or
any shuffle occurs. Prepared mixed routes commit the batch in bulk, preserve
public exile information, and emit genuine mill events for cards reaching the
graveyard. This avoids an earlier shuffle invalidating another card's pending
replacement choice. The latest batch alone supplies the color/type predicate.

Mandatory self-shuffle loops are adjudicated from every possible future batch,
not from observed random results. Every remaining card must have exactly one
mandatory self-shuffle outcome with no rider. A finite dynamic program computes
the largest subset that contains no shared property; if this subset is smaller
than the next mill count, every possible shuffle repeats. This also handles
Bruvac-expanded batches where a pair is guaranteed by the pigeonhole principle.
The server uses hidden state for this proof without publishing names or counts.
An intervening draw normally prevents this proof; a draw prohibited by a stable
draw cap (including Maralen) is inert and permits it. Other unproved states remain
resumable and are never declared draws from an iteration count or repeated order.

`RulesState.draw_reason` is optional and defaults to `None` for old saves. A
proven mandatory loop produces an explicit draw without manufacturing player
losses or a winner. Engine intents, priority and state-based actions respect the
terminal state; views expose a generic outcome, and the HUD displays “Draw”.
Undo/replay/save-load preserve the outcome. Preference changes remain available.

The generic older `loops.py` cap has not been changed by this family; these cards
use the bounded continuation primitive instead. Tamiyo's chapter IV remains a
separate unsupported feature, so the Saga as a whole remains PARTIAL.

Validation: 27 focused scenarios plus 129 related draw/mill, replacement, die-repeat,
and generic-loop regressions passed together (156 tests). Two additional gameplay
checks for the default 32-iteration budget and source departure also passed.
After replacing the generic self-shuffle log with a real public reveal action,
all eight affected mandatory/replacement/randomness checks passed again.
Canonical fixture Oracle text and metadata match the local card database.

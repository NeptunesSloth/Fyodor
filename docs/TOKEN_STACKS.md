# Token stacks in the rules engine

**Problem.** Sixteen token doublers (Adrix and Nev, Twincasters and copies) turned one Goblin into 2^16 = 65,536 tokens. The engine made
65,536 card objects and the server froze. Players chose: **represent huge token counts as one stack object ("Goblin ×65,536") that acts as
that many tokens**.

**Policy** (from `fyodor-game-development`): wrong automation is worse than manual, so the engine *refuses rather than guesses*; the server
stays authoritative; nothing hidden leaks; old saves load.

Rules used (Comprehensive Rules effective 2026-09-25): 109.1 (a token is an object), 110.1 (each token on the battlefield is a permanent),
111.1/111.6 (tokens are subject to everything that affects permanents), 111.7/111.8/704.5d (a token that left the battlefield ceases to
exist), 603.2c (an ability triggers once per occurrence of its event), 611.2c (the affected set of a resolved continuous effect is fixed when
it begins), 616.1 (replacement effects), 704.5j (legend rule), 510.1a/510.2 (combat damage), 119.9/120.3 (life gain and damage results).

## 1. What a stack is

A stack is **one token permanent with `CardInstance.quantity` = N > 1** (the field the sandbox already used for its visual stacks; default 1,
so every old save loads unchanged). It stands for N tokens that are identical in every respect the rules can see: the same token
characteristics, controller, owner, tapped and summoning-sickness state, counters, damage, attacking target, designations and the same
continuous effects (they share one rules object id, so any effect that applies to one applies to all). That identity is what makes "treat
the object as N" exact.

A stack never has anything attached to it and is never attached to anything, is never legendary, never face down, and has no rules text
except a short list of keywords that only ever affect the token itself in combat (flying, haste, vigilance, reach, trample, menace,
defender, first strike, double strike, deathtouch, indestructible, hexproof, shroud) and the foldable triggered abilities of section 9
(Scute Swarm's landfall). Anything else (Treasure's mana ability, a Forest Dryad's intrinsic `{T}: Add {G}`, lifelink, Biowaste Blob's
"Oozes you control get +1/+1") is created as individual tokens, as before. A token copy of a card (707.2) may be a stack when the copied
values pass these tests (section 9): "Scute Swarm ×4,096".

Module: `backend/app/rules/token_stacks.py`.

## 2. When stacks form

Only at creation, in `replace._make_tokens`: one instruction creating **more than `STACK_FROM` (100)** identical tokens of a kind that may
stack (section 1) creates one object with `quantity` = N (`create_token` with `quantity`), **if the board audit (section 4) passes for that
token**. Below the threshold tokens are individual exactly as before.

If the creation is over the threshold but can't stack (the token kind or the board doesn't allow it):

* up to `INDIVIDUAL_LIMIT` tokens are created one object each (slow but exact, today's path);
* above it the action is **refused** with a message that names the reason and says to pause automation and finish by hand. The engine
  never starts making 65,536 objects again, so the server can't freeze.

Stacks are never merged after creation under automation (`merge_tokens` still refuses), so a stack's members always came from one event.

## 3. The exactness gate

The rest of the engine (218k lines, ~850 places that read the battlefield) sees a stack as *one object*. That is right only where reading
one member stands for reading each member. Two mechanisms make sure nothing else ever runs with a stack present:

**a. The audit** (`token_stacks.problems`) decides whether every ability that could *observe* a stack is one the engine handles exactly.
It reads the parsed abilities (`scripts.definitions`, `spell_definition`) of: every other permanent, everything on the stack, emblems,
graveyard and exile cards (public; their abilities that work there), and the rules records that react to future events (delayed
triggers, replacement/prevention/regeneration shields, pending triggers, …). An ability passes if:

* it is **blind** to the stack: none of its selectors matches the stack, and it has no counting, group or object vocabulary that could
  reach it implicitly (a conservative word list over the parsed ability: "each", "all", "any", "count", "token", the stack's types,
  subtypes, name and colors, …), and its keywords are in a short safe list (exalted, annihilator, myriad, convoke … are not); or
* it matches a **whitelisted shape** whose stack handling is implemented and tested (section 5).

An ability already on the stack is read from its rules entry (what it will do), not from its source's text.

Hidden cards (hands, libraries, face-down exile) are never read by the audit: a refusal that depended on them would leak them. See
section 8.

**b. The touch guard** (`Plan._do`): a table step that changes a stack (move, tap, counter, damage, control, attach, face, …) is allowed
only inside code that is known to treat the whole stack as N identical members (`token_stacks.whole(plan)`: state-based actions, the
turn's untap step and cleanup, combat damage and the attack declaration, the whitelisted all-at-once effects, the creation itself) or
after the members it affects were split off. Any other code touching a stack is code that thinks it is one creature: the step raises,
and the whole action is refused (or, for a small stack, retried with the stack spread out, below). Unknown code paths fail loudly instead
of being silently wrong.

**c. Targets at resolution** (`token_stacks.check_targets`): a spell or ability whose target is still a whole stack when it resolves was
targeted past the splitting points (an engine-made pick): it stops like the touch guard.

**When the gate fails** (at the start of an action, for a new object that appears during one, or by the touch guard; `compile_intent`
retries the action once with every stack spread, or refuses it):

* a stack of at most `INDIVIDUAL_LIMIT` is **spread** into individual tokens (the existing `expand_stack` + `adopt`: no event, the tokens
  were already there) and the action runs on individual tokens, exactly as before stacks existed;
* a stack of at most `STACK_FROM` (a part split off, a sandbox stack) is always spread before an action, as before this change;
* a bigger stack can't be spread without freezing the server, so the action is **refused**: "Goblin ×65,536 is a token stack the rules
  engine can't handle with <card> on the battlefield. Pause automation to do this by hand." The sandbox (automation paused) still works
  on the stack: split off N, add/remove, move.

## 4. Rule by rule

| Area | Treatment |
|---|---|
| Counting ("for each creature you control", "the number of Goblins", X counts) | `values` count sums `quantity` (`token_stacks.weight`). Counts read elsewhere (conditions, history, party, devotion, power totals) are not whitelisted: the audit refuses them. Devotion can't see a stack anyway (tokens without a mana cost). |
| Anthems and other static grants to a group (fixed +N/+N, safe keywords, imposed rules like "can't block") | Layers apply per object; every member is the same object, so each member gets it. Whitelisted. |
| Effects on all / each (destroy all, damage to each creature, tap/untap all, +N/+N and keywords until end of turn) | Applied once to the stack object = to every member, simultaneously (as the rules do for "all"). Whitelisted primitives run inside `whole()`. |
| Mass zone change of the stack (wipe, bounce all, exile all) | The stack moves as one, then ceases to exist as a token (111.7, 704.5d). Every member left at once. "Dies" observers are refused by the audit (they would trigger once per member). |
| State-based actions (0 toughness, lethal damage, deathtouch damage, +1/+1 and -1/-1 counters) | Every member is identical, so each member has the same result: the whole stack is put into the graveyard together. Runs inside `whole()`. |
| Legend rule (704.5j) | Legendary tokens never stack. |
| Singling out members (a target, a sacrifice, a choice, one blocker, one blocked attacker, a mana source) | **Split first**: the chosen card id keeps exactly one member and the rest move to a new object (new id and rules object id) that copies every rules record of the stack (`adopt`: control timestamp, entry this turn, card mode, continuous effects that affected it). Then the action runs normally on a single token. Splitting happens at the boundary where the choice enters the engine: intent card ids (targets, attackers' blocks, mana sources, crew, cost choices) and decision answers. An engine-made choice that bypasses those boundaries hits the touch guard instead. |
| Combat: attacking | Declaring a stack as an attacker attacks with all its members, at the same target. To attack with part, split off N first (the table's "Split off…"). An unblocked stack deals `quantity` × its damage (510.1a for each member, all dealt simultaneously, 510.2). The attack's total power record counts every member. |
| Combat: blocks | A blocker blocks one attacker: naming a stack as an attacker that is blocked splits one member off, which is the blocked one (all block lines naming that stack block that one member; to block several members, split them first); naming a stack as a blocker splits one member off, which blocks. |
| Combat: lifelink, toxic, "whenever a creature deals combat damage" | Not exact for a stack (separate life gain events per member, 119.9/120.3f): lifelink and toxic tokens never stack; the observers are refused by the audit. |
| Per-member triggers ("whenever a creature enters / dies / attacks") | 603.2c: N events trigger N times. Refused by the audit (the stack is spread when small, the action refused when big), except the whitelisted *enters* shape below. |
| "Whenever another creature enters, you gain 1 life" (`enters_other`, no target, not optional, only fixed life gain/loss or draw) | 603.2c: N members entering trigger it N times (`triggers._other_enters` asks `token_stacks.member_triggers`). A fixed life gain/loss is **folded** into one trigger "Soul Warden (×1,024)" gaining N times as much, but only while no public ability mentions life (no "whenever you gain life", no "if you would gain life", no "can't gain life" record): N separate life changes and one change of N times as much then end the same. The players don't get priority between the N identical triggers: that is the 732.2a shortcut of letting identical triggers resolve, taken without asking. Otherwise (a life reader, a draw) the N triggers are separate, up to `INDIVIDUAL_LIMIT`; beyond that the action is refused. Measured: 1,024 separate triggers took 431 s in the test kit; folded, under a second. |
| Untap step, cleanup, phasing | Turn-based actions on every permanent: the stack untaps / loses its damage as one. Inside `whole()`. |
| Token ceases to exist (111.7, 111.8) | Unchanged: the stack object leaves and ceases to exist as one. |
| Copying one member | A copy reads copiable values, identical for each member: allowed. |
| Views and privacy | A stack is a public permanent: every viewer gets one object with `quantity`. Nothing about hidden cards is read or reported by the audit. |
| Undo, replay, save/load | Everything is recorded as ordinary steps (`create_token` with `quantity`, `split_stack`, `expand_stack`) and the rules state is synced at the end of each action, so replay rebuilds the same state; `quantity` already saved. |

## 5. Whitelisted shapes

Exactly these parsed shapes may refer to a stack (everything else that refers to one is refused):

* static `grant` to a selector: integer or count power/toughness, safe keywords, no conditions;
* spell/ability effects: `destroy_all`, `no_regen`, `damage` to `each_creature` (integer), `pump`/`grant` of a selector (integer or count
  values, safe keywords), `gain_life`/`lose_life`/`draw`/`create_token` for players with integer or count amounts;
* one-target effects (`damage`, `destroy`, `exile`, `bounce`, `pump`, `grant`, `tap`, `untap` of "target …"): the target is split off;
* activation costs of mana, `{T}` and "Sacrifice a/an/another …" (the sacrificed member is split off);
* token creation replacement effects with a multiplier (Adrix and Nev, Primal Vigor, Parallel Lives) and +1/+1 counter replacements
  (`counters` multiply/add: each member's event is replaced alike);
* "As this enters, … as a copy" (Spark Double): it only applies to its own entry;
* the `enters_other` trigger of section 4;
* (wave TS2) the foldable triggered abilities of section 9, on another permanent or on a stack (their condition must not count the stack,
  and a landfall one needs no stack to be a land); "triggers an additional time" statics for an *entering* cause (603.2d: Ancient
  Greenwarden, Traveling Chocobo, Yarok: `trigger_multipliers.multiply` copies each pending instance, a stack's included); permissions to
  play or cast from the top of a library or a graveyard; "the legend rule doesn't apply" statics; `search` of a library ("put it onto the
  battlefield", Rampant Growth: 701.23, it only finds library cards; new lands are audited as they arrive).

## 6. Limits

`STACK_FROM` = 100, `INDIVIDUAL_LIMIT` = 256 (2^8; the pod's eight-doubler test makes 256 separate Dryads). Measured on the test kit:
128 Forest Dryads made one object each took 3.3 s, so a few hundred objects is the most the engine can make or spread without the table
noticing. A stack of 131,072 is made in well under a second (the test asserts < 2 s for the whole Dragon Fodder cast).

## 7. Client

The 2D and 3D tables already show `quantity` as a ×N badge (`piles.countMark`); it now reads "×65,536". With automation on the token-stack
menu offers "Split one off" and "Split off…" (engine-exact splits; a part of at most 100 becomes separate tokens at the next action) and
"Split into N tokens" only up to `INDIVIDUAL_LIMIT` (`tokenStacks.ENGINE_SPREAD_MAX`); the server refuses a bigger `expand_stack`.

## 8. Not exact, so refused (and what remains)

* Per-member triggers other than the `enters_other` shape and the foldable shapes of section 9 (dies, attacks, leaves, taps, becomes the
  target, "one or more" batch triggers, a landfall that does anything but create tokens…), and folding anything but a fixed life
  gain/loss or the token creations of section 9.
* Choosing several members in one choice (a decision or intent naming a stack once picks one member: split more off first).
* `tap`/`untap` of a group and other mass effects not listed in section 5 (counters on each creature, gain control of all, …).
* Any count outside `values` (conditions such as "if you control seven or more creatures", party, coven, power totals of a group).
* Combat with lifelink/toxic stacks, stacks as blockers of several attackers, banding.
* Delayed triggers that act on a stack ("sacrifice them at the beginning of the next end step").
* Abilities that work from a hidden zone and see the battlefield aren't audited (reading them would leak them). No such Commander card is
  known to interact; the risk is documented rather than guessed away.
* Tokens with abilities (Treasure, Food, Forest Dryad lands) never stack: each activation would need a split; their big creations are
  refused above `INDIVIDUAL_LIMIT`.

## 9. Folded token-making triggers and stacks of token copies (wave TS2)

**Problem.** Scute Swarm ("Landfall — Whenever a land you control enters, create a 1/1 green Insect creature token. If you control six or
more lands, create a token that's a copy of this creature instead.") doubles on every land. Each Swarm's trigger was its own stack object
and its own creation of one token, so a stack never formed, 80 Swarms took ~17 s per land (with Adrix and Nev, Primal Vigor and Traveling
Chocobo: 259 s), and a few hundred were the end of automation.

**What the engine does now** (`token_stacks.py`, block `-- token stack folds (wave TS2) --`; the fold happens in `triggers.flush` before
the controller orders triggers, `token_stacks.fold_pending`):

* **Fold.** When a controller's triggered abilities waiting to go on the stack (603.3b) include several *identical* instances of a
  foldable ability, they go on the stack as ONE ability named "Scute Swarm (×N)". It resolves as the N instances would, one after another
  with every player passing: the 732.2a shortcut the Soul Warden fold (section 4) already takes. Its condition is checked as it resolves
  (603.4 for an intervening "if", 608.2c for "If you control six or more lands, … instead"), and each creation instruction makes N times its
  tokens in one creation event (701.7a), which then goes through the normal token path: replacement effects, then a stack when it is
  more than `STACK_FROM` and the audit allows it. Identical means: the same parsed definition, the same controller, and sources whose
  copiable values (707.2, from a stack, an individual token copy or the card) are the same; a stack's members count once each (603.2c),
  and every instance a trigger multiplier added (603.2d: Ancient Greenwarden, Traveling Chocobo, Yarok) joins the same fold. Several lands
  entering at once (603.2c: one event each) give K·N identical instances; they fold together because the foldable shapes read nothing of
  their event, so the K·N resolutions are interchangeable.
* **Foldable shapes** (`fold_shape`): a triggered ability with trigger landfall, "at the beginning of your upkeep / end step", "at the
  beginning of combat on your turn"; no target; not optional (an optional ability's "you may" is answered for each instance separately:
  Ancient Greenwarden and Traveling Chocobo rulings, "Any choices made on resolution … are also made individually"; answering once for all
  would be a guess, so optional abilities never fold); effects only "create [n] [fixed token]" for you and "create [n] token(s) that's a
  copy of this creature", gated by conditions that are a count of a selector compared to a number ("if you control six or more lands", "if
  you control a commander") or "if you've cast a noncreature spell this turn". Real cards: Scute Swarm, Biowaste Blob ("At the beginning of
  your upkeep, if you control a commander, create a token that's a copy of this creature"), Council of Reeds, Rampaging Baloths.
* **Exactness checks** (`fold_problems`, at fold time and again as the folded ability resolves, `fold_check`):
  * nothing happens between the resolutions that could differ: the tokens it makes are audited with the stack audit (sections 3 and 5) in
    a stricter mode: any observer of the tokens entering or being created is refused except a "whenever another creature enters, you gain
    or lose N life" ability with no life reader (Soul Warden; a draw is refused: something could react to the draw between two
    resolutions); the tokens' own triggered abilities must themselves be foldable; a "whenever one or more tokens enter" or "whenever you
    create tokens" ability (one event instead of N, 603.2c) is refused by the audit's vocabulary;
  * the tokens can't change the condition (608.2c: the N checks must agree): the probe tokens must not match the condition's selector (a
    Scute Swarm that copies a land creature would count itself);
  * legendary tokens fold only when "the legend rule doesn't apply" to them (Council of Reeds' own static): otherwise 704.5j would act
    between resolutions;
  * one creation event of N·k tokens ends as N events of k: the audit lets through only token replacements that *multiply* ("twice that
    many", Adrix and Nev, Primal Vigor, Doubling Season, Parallel Lives: 2·(N·k) = N·(2·k), and several multipliers commute, 616.1f).
    Additive replacements ("those tokens plus an additional Treasure token", Xorn: N·(k+1) ≠ N·k+1), first-time-each-turn ones (Esix,
    Fractal Bloom: only the first of N events) and Chatterfang (its "plus that many Squirrels" is linear, so a fold would be exact, but its
    "Sacrifice X Squirrels" cost chooses several members of a stack: the audit refuses it) keep the triggers separate;
  * nothing public watches triggers or the stack (`_ability_readers`: "triggered ability", "ability", "stack" in a public ability's text,
    e.g. Strict Proctor). Trigger multipliers are read exactly and allowed. A hidden card can't be read (its refusal would leak it):
    a target choice naming a folded ability (Stifle, Strionic Resonator) splits one instance off instead (`single_out_fold`: the targeted
    object keeps one instance, the other N−1 become a new ability object directly above it; they are identical, so which one is named
    doesn't matter). Only while the folded ability is the top of the stack; otherwise the action is refused. An engine-made target that
    names a folded ability is refused as it resolves (`check_targets`);
  * the controller has no other triggered ability to order among them (603.3b: a fold makes the N instances a block). Two groups of
    foldable abilities are folded as two blocks only when neither group's tokens could change the other's condition (`_crossed`).
* **When a fold isn't exact**, the instances stay separate exactly as before; a stack's members then trigger one by one (up to
  `INDIVIDUAL_LIMIT`; beyond that the action is refused). A folded ability that is no longer exact when it resolves (an observer arrived in
  response, or its sources' copiable values diverged, 608.2h) can't be taken apart: resolving it is refused ("Pause automation and resolve
  them by hand").
* **Stacks of token copies.** A token copy (`_copy`, its layer-1 copy effect, 707.2 / 613.2a) may now be a stack. It is judged by its
  copiable values: every ability must be a safe keyword or a foldable triggered ability, and the stack is kept only while its own triggers
  would fold. Copy exceptions (707.9a-c: "except it isn't legendary", "except it's a 1/1") are part of the recipe, so they are exact; an
  exception finished as each copy enters (707.9e "enters with an additional +1/+1 counter", Hulking Metamorph's power) or a double-faced
  original is refused. Legendary copies never stack (704.5j). Splitting (`adopt`) extends the copy effect to the split-off members
  (611.2c), so a member singled out by Giant Growth is still a Scute Swarm with landfall and still folds with the rest.
* **Measured** on the test kit (Rampant Growth each time, six or more lands):

  | Board | before | after |
  |---|---|---|
  | 20 Swarms, one land | 1.9 s | 0.7 s |
  | 80 Swarms, one land | 17.2 s | 5.6 s |
  | 64 → 128 Swarms (all separate objects) | 19.2 s | 5.7 s |
  | 128 → 256 Swarms | 73.5 s | 6.4 s |
  | 1,024 → 2,048; 65,536 → 131,072; 131,072 → 262,144 Swarms | (never reached) | 7.0 s; 7.5 s; 9.0 s |
  | 20 Swarms, Explosive Vegetation (two lands at once: 20 → 60) | 4.7 s | 1.4 s |
  | 80 Swarms, Explosive Vegetation (80 → 240) | 62.5 s | 2.3 s |
  | 20 Swarms + Adrix and Nev + Primal Vigor + Traveling Chocobo (20 → 180) | 15.2 s | 0.5 s |
  | 80 Swarms + the same (80 → 720) | 259 s | 1.8 s |
  | 16 Swarms + the same, four lands (16 → 104,976) | (never reached) | 3.5 s for all four |

  What remains of the time is the separate objects made before any stack formed (a fold of 64 makes 64 tokens: fewer than `STACK_FROM`).

**Not settled, so refused:** optional foldable abilities (a "you may" for each instance); abilities with a target; folding through
additive or first-time token replacements (Xorn, Esix); Chatterfang with a stack (its sacrifice-X cost); a fold whose sources stop being
identical before it resolves (refused rather than taken apart); placing the split-off instances of a folded ability that isn't on top of
the stack.

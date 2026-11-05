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

A stack never has anything attached to it and is never attached to anything, is never legendary, never face down, never a copy, and has
no rules text except a short list of keywords that only ever affect the token itself in combat (flying, haste, vigilance, reach, trample,
menace, defender, first strike, double strike, deathtouch, indestructible, hexproof, shroud). Anything else (Treasure's mana ability, a
Forest Dryad's intrinsic `{T}: Add {G}`, lifelink, a token copy of a card) is created as individual tokens, as before.

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
| Combat: attacking | Declaring a stack as an attacker attacks with all its members, at the same target. To attack with part, the declaration names how many (`AttackDeclaration.count`: the other members are split off inside the same action, `token_stacks.keep`; a part of at most 100 is spread at the next action, still attacking), or split off N first before the declare-attackers step (the table's "Split off…"). An unblocked stack deals `quantity` × its damage (510.1a for each member, all dealt simultaneously, 510.2). The attack's total power record counts every member. |
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
* the `enters_other` trigger of section 4.

## 6. Limits

`STACK_FROM` = 100, `INDIVIDUAL_LIMIT` = 256 (2^8; the pod's eight-doubler test makes 256 separate Dryads). Measured on the test kit:
128 Forest Dryads made one object each took 3.3 s, so a few hundred objects is the most the engine can make or spread without the table
noticing. A stack of 131,072 is made in well under a second (the test asserts < 2 s for the whole Dragon Fodder cast).

## 7. Client

The 2D and 3D tables already show `quantity` as a ×N badge (`piles.countMark`); it now reads "×65,536". With automation on the token-stack
menu offers "Split one off" and "Split off…" (engine-exact splits; a part of at most 100 becomes separate tokens at the next action) and
"Split into N tokens" only up to `INDIVIDUAL_LIMIT` (`tokenStacks.ENGINE_SPREAD_MAX`); the server refuses a bigger `expand_stack`.

Part of a stack: the declare-attackers panel asks how many of a stack attack (all by default) and sends the count. The card menu offers
"Attack with some of the ×N" (per target), "Tap some…"/"Untap some…" and, when the table is run by hand, "Sacrifice some…": each splits
n − k off first (`split_stack` moves `count` to a new card, so the card itself, whose id is known, keeps k) and then acts on the card —
two table actions, two undo steps. The combat lanes show, when a stack attacks, the attacking count and what the unblocked attackers deal
(members × power; display only). The stack list shows consecutive identical abilities as one row ("Scute Swarm — landfall ×400",
`stackGroups.ts`), never grouping a targeted object or the object a decision is about.

## 8. Not exact, so refused (and what remains)

* Per-member triggers other than the `enters_other` shape (dies, attacks, leaves, taps, becomes the target, "one or more" batch
  triggers, landfall…), and folding anything but a fixed life gain/loss.
* Choosing several members in one choice (a decision or intent naming a stack once picks one member: split more off first).
* `tap`/`untap` of a group and other mass effects not listed in section 5 (counters on each creature, gain control of all, …).
* Any count outside `values` (conditions such as "if you control seven or more creatures", party, coven, power totals of a group).
* Combat with lifelink/toxic stacks, stacks as blockers of several attackers, banding.
* Delayed triggers that act on a stack ("sacrifice them at the beginning of the next end step").
* Abilities that work from a hidden zone and see the battlefield aren't audited (reading them would leak them). No such Commander card is
  known to interact; the risk is documented rather than guessed away.
* Tokens with abilities (Treasure, Food, Forest Dryad lands) never stack: each activation would need a split; their big creations are
  refused above `INDIVIDUAL_LIMIT`.

## 9. Big counts by hand (and the token math panel)

When the engine refuses a creation (section 2), the players finish by hand with automation paused, and the table makes one card ×N:

* `create_token` makes at most `MAX_SEPARATE_TOKENS` (100) separate tokens; more is one stack (`stacked`), up to 10^15. With automation on, tokens
  made by hand stay separate objects, so more than 100 is refused with "Pause automation to make them as one card ×N".
* `copy_card` with `stacked: true` makes one token copy standing for `count` copies ("Scute Swarm ×4,096"), keeping the copied card's text;
  only on the battlefield and only with automation paused (with it on, each token copy of a card is its own object). Separate copies: at most
  `MAX_SEPARATE_COPIES` (50). The card menu's "Create copy → Several copies…" sends a stack past 50 (or past the "Collapse identical tokens"
  setting) when automation is paused.
* The table's split/add/remove work on these stacks as on any other; `stack_adjust` now goes up to 10^15.

**Token math** (`frontend/src/game/TokenMathDialog.tsx`, `tokenMath.ts`; Shift+T or the Bag of Extras) works the numbers out before a
big turn: Scute Swarm and other landfall makers one land at a time or all at once (Lumra, Scapeshift: 603.2c, 603.10), landfall trigger
doublers (Ancient Greenwarden, Traveling Chocobo, Yarok: 603.2d), token doublers (616.1), self-copiers (Biowaste Blob, Council of Reeds),
Craterhoof swing totals and a count of the tokens on the board. It reads only the public board (battlefields and graveyards, never a hand
or library) and sends nothing on its own.

* **Put this on the table** (automation off, your own board only): after one confirm listing everything, the projection's new Scute
  Swarms are one `copy_card` of a Scute Swarm you control with `stacked: true`; Insects, other landfall tokens and Chatterfang's Squirrels
  are `create_token` (the card's related token when it lists one, else a plain token from the text), stacked past 100 or the "collapse
  identical tokens" setting. A choice ("Food or Treasure"), mana and counters stay the player's. Self-copiers: "Apply N rounds" copies
  the card as one stack. With automation on, the panel says the engine makes them as the triggers resolve.
* Quick setups: "Lands in graveyard: N — all at once" (Lumra, Splendid Reclamation; the graveyard is public) and Scapeshift (S lands
  sacrificed first, then S enter at once, so the six-lands check sees L − S + S). Copies: Doppelgang X (X × X, each creation doubled),
  Rite of Replication kicked, Biovisionary copies still needed.
* **Board pressure badge** (top bar, `BoardPressure`): shows from 150 battlefield objects, a ×N stack past 100, or 50 triggers waiting;
  a ×N stack is one object standing for N tokens. Clicking it opens Token math.


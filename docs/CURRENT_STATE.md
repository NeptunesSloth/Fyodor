# Current state — handoff for the next session

Written 2026-10-04 at the end of the session that built PR #13 (merged) and PR #14 (open): rules-engine
waves 7R–17D, an independent review of 7R–14A, and eight new engine systems (18A–18H), each with an Opus
head review. Every number here was checked against local runs at that time.

## Current repository state

| | |
|---|---|
| Repository | `NeptunesSloth/Fyodor` |
| `main` | Has PRs #7–#13 (waves 1–14A). |
| Open PR | **#14** (`claude/beautiful-ramanujan-l9pev4`, draft): the Fable review of 7R–14A, sweeps 15A–17D, Class cards (16A), prevention (17A), and systems 18A–18H with their Opus reviews. CI was green on every pushed head checked. |
| Pending | `claude/review-facedown-ids`: an Opus review of a privacy fix (face-down cards get a new id after they were seen). Merge it into #14 once green. |
| Agent branches | `claude/wip-*`, `claude/wave1[0-7]*`, `claude/sys18*`, `claude/review-*`: all merged into #14 (except the pending one above); safe to delete once #14 is merged. |

## Last known test status (PR #14 head `db05477`, all eight systems merged)

| Check | Status |
|---|---|
| Backend pytest (full, `-n 4`) | 6,686 passed. |
| ruff / mypy (`app tools`, 276 files) | Clean. |
| Frontend tsc / vitest | Clean; 64 tests passed. |
| GitHub CI | Green on the pushed heads through 17D; check the newest head. |

The repo's pytest `addopts` includes `-q`; pass no extra `-q` or the "N passed" summary line is suppressed.
`test_rules_statics.py::test_full_board_derive_is_fast` can fail under heavy load; rerun it alone.

## Current Commander coverage

Data: Scryfall snapshot 2026-10-03, Comprehensive Rules 2026-09-25. Per-card diff tool: compare dumps of
`coverage.of_card_data(...).level` for every Commander-legal card (this session kept one in its scratchpad).

| | `main` before PR #13 | PR #13 (merged) | Now (PR #14 head) |
|---|---|---|---|
| FULL | 19,506 (60.8%) | 20,653 | **22,896 (71.4%)** |

Only two cards lost FULL in the whole session, both on purpose: Hatchery Spider ("where X is" read the cast
X inside a selector) and Alpine Houndmaster ("a card named A and/or a card named B" was read as one name).

## What PRs #13 and #14 added

- **Waves 7R–14A (PR #13):** reviews of waves 7–9, then reanimation, `static_other`, "if you do", transform,
  keyword meanings, trigger grammar, hand disruption and name searches, small clusters, event triggers and
  intervening ifs, counters/clash/detain/suspect/dice, keyword batches, "where X is", per-opponent targets,
  control/land types, emblems, multi-block, cast-a-copy and prepared, phasing, untap limits, attacker damage
  division (510.1c).
- **Independent review of 7R–14A (PR #14):** five areas; fixes include the last player winning past "can't
  win" (104.2a), a hand-content log leak after private looks, priority returning to the caster after a cast
  trigger (117.3c), phasing/blocking bugs, Room/prepared copies, back-face mana value.
- **Sweeps 15A–17D:** the long tail of `static_other`, `trigger_other`, "if you do", activated/counters/X,
  keywords (training, evolve, mentor, myriad, backup, spectacle, surge, blitz, warp, bestow, riot, ninjutsu,
  embalm, aftermath, fuse, awaken, dredge as an optional replacement), Class levels (716), prevention riders
  and redirection, mana for/with restrictions, waterbend, teamwork, cipher, conspire, -1/-1 counter and mill
  triggers.
- **Systems 18A–18H** (each Opus-reviewed; the reviews fixed 51 bugs, including four hidden-information leaks):
  hidden exile and face-down objects (foretell, morph/disguise/manifest/cloak, piles); mana provenance and
  spending restrictions (Cavern of Souls, Opal Palace, K'rrik); opening-hand actions and voting; mutate and
  meld (merged permanents, rule 730); casting extras (overload, entwine, splice, prototype, disturb,
  harmonize, jump-start, encore, craft, emerge, casualty, melee, provoke, reconfigure, recover, enlist,
  assist, amplify, miracle); copying abilities, borrowed abilities and granter references; Rooms and
  Sylvan Library's private draw record; controlling another player (723, Mindslaver, Opposition Agent).

## What PR #12 added

Each wave has its own test file `backend/tests/test_rules_wave<N><x>_*.py`, and its code is marked
`wave <N><X>` (`grep -rn "wave 7C" backend/app`). All scenarios use real Oracle text with replay and
save/load checks.

- **Wave 5** (catch-all families split out in `gap_rank`): mana riders and tap-for-mana triggers, stack
  interaction (change target, Mana Drain), combat rules (attack costs 508.1d, extra combats), trigger
  multipliers / trigger words / put-back, cast limits / protection grants / player shields, type-setting
  statics and entry forms, paid X and enter costs (Mox Diamond), counters. **5R review** demoted
  Panharmonicon, Ancient Greenwarden, Yarok, Virtue of Knowledge and Naban (whether "create a token"
  triggers are multiplied is unsettled: `trigger_multipliers.ENTERING = False`), and fixed token-kind
  batching, a reflexive-trigger renumbering crash, X in the cast log and derive performance.
- **Wave 6**: next-untap / bounce forms / turn grants (6A), damage history and prevention wordings (6B),
  Roles / decayed / token and pump grammar (6C), trigger conditions including 603.8 state triggers and
  "exiled with" (6D), either-costs / exert / keyword triggers (6E), each-may and removed mana (6F).
  **6R review** fixed: "[A] and [B] your opponents control enter tapped" also tapped the controller's own
  permanents (Thalia, Heretic Cathar; Frozen Aether; Kismet; Blind Obedience); each-may payments were not
  simultaneous (now `pay_deferred`, 101.4); Voyager Staff and Hide on the Ceiling were wrongly refused; two
  rules-bearing prefixes were read as flavor words.
- **Wave 7**: cast-timing restrictions (7A, `cast_timing.py`); activation conditions, any-player
  abilities, adapt (7B); counters, second pass: shield counters, counter-put triggers with `Event.group`,
  power-up, "enters with your choice of counter", suspend self-exile (7C); turn watches "whenever … this
  turn" and "when you next cast" (7D); activated abilities, second pass: creature lands, snow mana, coin
  flips, choice grants, attach abilities, switching P/T, block effects (7E); the untap-step choice and "for
  as long as ~ remains tapped" (7F).
- **Wave 8**: modular, partner with, extra turns (a LIFO queue, `extra_turns.py`), split second, one-shot
  extra land plays (8A); superlative conditions (`extremes.py`), scry/surveil events, Dark Confidant,
  per-player life loss (8B); objects a payment used (`pay_objects.py`), mill and exile-from-hand
  payments, a choice of counter (8C); enter counters conditioned on this turn's history, the Rings,
  attached-count pumps, half-life loss (8D).
- **System 18H (controlling another player, CR 723)**: `app/game/control.py` (who decides, `acting_as` routes an
  intent's seat; `can_see` shares what the controlled player sees, never a sideboard, only while controlling),
  `rules/player_control.py` (Mindslaver, Worst Fears, Emrakul "next turn" effects: pending until that player's
  turn begins, latest wins; Opposition Agent: the search decision's `decider`, found cards exiled + playable,
  any-color mana). Manual: Word of Command, Cruel Entertainment, Secret of Bloodbending (a combat phase),
  Dominion Bracelet / Cosmic Cube (other unread wordings), Sorin Markov's -3. Review: control is bound to the turn
  number it began on (a turn passed by hand ends it) and starts before that turn's untap choices; a departed
  controller/decider hands choices back (800.4a); a controlled player may only concede (`session.CONTROLLED_MAY`:
  table tools, card automation and undo wait); Opposition Agent also covers Gifts-style and own-library name searches.
- **Wave 9A**: discover, "where X is" keyword actions (bolster, amass, connive, endure), "the amount of
  mana spent to cast", "creatures that died under your control this turn".

## Top remaining rules gaps

`python -m tools.gap_rank --db ../data/cards.sqlite --top 15` on the PR #14 head (FULL 22,896, PARTIAL
9,172). "Sole" = non-FULL cards whose every unsupported line is in that family (an upper bound). Most of what
remains is wordings that appear on one or two cards; the sweeps reached roughly the top 60–75% of each big
family by EDHREC rank.

| # | Family | Missing lines | Sole | Sole commanders | Examples (by EDHREC rank) |
|---|---|---|---|---|---|
| 1 | static_other | 3007 | 1404 | 150 | Chaos Warp, Rakdos Charm, Birgi, God of Storytelling // Harnfel, Horn of Bounty, Valakut Awakening // Valakut Stoneforge |
| 2 | trigger_other | 1514 | 1034 | 274 | Guardian Project, Forgotten Ancient, Kutzil, Malamet Exemplar, Selvala, Heart of the Wilds |
| 3 | if_you_do | 1001 | 744 | 167 | Saw in Half, Bloodchief Ascension, Etali, Primal Conqueror // Etali, Primal Sickness, Tainted Pact |
| 4 | counters | 669 | 437 | 116 | Spark Double, Tezzeret, Cruel Captain, Laelia, the Blade Reforged, Unstoppable Slasher |
| 5 | activated_other | 516 | 401 | 64 | Talon Gates of Madara, Emry, Lurker of the Loch, Haywire Mite, Field of Ruin |
| 6 | this_turn_state | 411 | 320 | 60 | Veil of Summer, Conduit of Worlds, Combat Celebrant, Hunter's Insight |
| 7 | x_value | 480 | 300 | 57 | Torment of Hailfire, Crackle with Power, Steel Hellkite, Skyclave Apparition |
| 8 | attached_events | 343 | 277 | 10 | Commander's Plate, Kaya's Ghostform, Blade of Selves, Illusionist's Bracers |
| 9 | damage_sized | 337 | 242 | 32 | Descent into Avernus, Myr Battlesphere, Combustible Gearhulk, Wheel of Misfortune |
| 10 | as_long_as_static | 346 | 236 | 34 | Promise of Loyalty, The Reality Chip, Conqueror's Flail, Cloud, Midgar Mercenary |
| 11 | instead | 342 | 228 | 44 | Academy Manufactor, Incubation Druid, Innkeeper's Talent, Whip of Erebos |
| 12 | reanimation | 281 | 150 | 22 | Sevinne's Reclamation, Agadeem's Awakening // Agadeem, the Undercrypt, Haven of the Spirit Dragon, Mantle of the Ancients |
| 13 | ability_word | 261 | 146 | 30 | Tireless Provisioner, Shifting Woodland, Springheart Nantuko, Augur of Autumn |
| 14 | free_cast | 212 | 125 | 45 | Tibalt's Trickery, Urza, Lord High Artificer, Expressive Iteration, Muldrotha, the Gravetide |
| 15 | tutor | 150 | 103 | 4 | Sword of Hearth and Home, Scapeshift, Defense of the Heart, Moonsilver Key |

## Known shipped limitations and open items

Still manual on purpose (each has its reason in code, mostly `coverage.REFUSED`, refusal checks in
`scripts.define` or module docstrings):

- **Reflexive triggers** reading the sacrificed object anywhere other than its power, toughness or
  mana value (Surtland Flinger's "was a Giant", Minsc & Boo), several sacrificed objects, mandatory
  forms (Tip the Scales).
- **Chosen selectors**: Roaming Throne, Cloud Key's chosen card type, protection from the chosen color;
  a trigger whose source left the battlefield matches nothing for "the chosen type".
- Lim-Dûl's Vault, Djinn of Wishes, Protean Hulk. (Sylvan Library: wave 18G, `drawn_toll.py`; the per-card "drawn this turn"
  record is `TurnLog.drawn`, private. Jandor's Ring's "discard the last card you drew this turn" cost can use it, not done.)
- **Copies**: cast-a-copy only as "[exile a card and] copy it / that card [N times]. You may cast the copy without paying its
  mana cost" (wave 13C, 707.12: `copying.copy_cards` + `permissions.FREE_COPY`; the copy is made in the card's own zone;
  a non-free "You may cast the copy", "cast the copy by paying …" and copies of imprinted / "exiled with" cards stay manual),
  Prepared (wave 13C, 722): `rules.prepared` (object -> its exiled copy, face 1), "enters prepared" / "becomes prepared" /
  "isn't prepared", the copy is cast for its normal cost (cast_grant "prepared") and unprepares the permanent; a prepared
  token or copy of a permanent is not prepared (no tracked prepare spell). Also left: "each other object it could target" (Zada), Garth One-Eye / Magar,
  linked abilities (707.7), melded and reversible sources.
- **Mana**: restricted mana added by spells (Geosurge, Karn), "that spell can't be countered" riders,
  restrictions on costs rather than spells, Mana Drain, exhaust mana abilities. Snow mana `{S}` (wave 7E) is paid only by tapping a snow
  source during payment; snow mana already in the pool never pays it.
  A mana ability whose cost a cost modifier changes (Gloom on a white enchantment) is left to the
  player. An enchanted land whose own {T} ability restricts spending is left to the player while
  enchanted.
- **Replacements** (wave 22C): counter putters ("If you / an opponent would put …": Vorinclex, Lae'zel, Pir; the
  putter is `by`, 122.6a; poison "given" by infect/toxic, 120.3b, is left to the players with a note: UNVERIFIED
  whether giving is putting), "reveal ~ and shuffle it into its owner's library instead" (Blightsteel, Nexus of Fate),
  "exile instead" with a rider (Kalitas token, Head of the Hunt reflexive trigger, life), "If it would leave the
  battlefield, exile it instead" (Whip of Erebos family), and the 616.1 choice between differing graveyard
  replacements (the card stays put and its controller is asked before priority: `pending_616`). Still manual:
  life-loss replacements (no choke point yet), Academy Manufactor and Divine Visitation (token replaced by another:
  ordering with the "plus a Food" statics is unsettled), count-level draw replacements (Alms Collector), exile with
  counters / linked exile (Dauthi, Valgavoth, Darkness Crystal), Loading Zone ("creature, Spacecraft, or Planet").
- **Costs**: K'rrik and Dream Halls (per-mana payment), Suppression Field (crew and unearth skip the
  cost-modifier path), activation costs that depend on a target, "Remove X counters from among …",
  comma-listed sacrifice choices.
- **Modal**: "choose X/up to X", "choose two at random", modes with "you may", target groups or
  divisions, restriction lines after modes.
- **"Unless pays"**: "each opponent … unless they pay" (simultaneous edicts), "unless any player
  pays", choice of costs, "counter that spell or ability" triggered by targeting.
- **Keywords**: devour, graft, sunburst, amplify, dredge and level up (in progress on
  `claude/wip-wave9d`), airbend, waterbend, non-mana morph costs, warp, max speed, the dungeon Arena room,
  attack costs not weighed by goad, annihilator and myriad as granted keywords, ward Auras
  (702.16n), land-type-setting Auras (305.7).
- **X**: Torment of Hailfire (repeated per-opponent choices), "investigate X times", "up to X target"
  in triggers, delayed triggers (107.3n) don't receive X.
- **Battles**: a defeated Siege is cast transformed by hand.
- **Transform** (wave 11A, 701.27 / 712): "transform ~ / this creature" (the source only), "exile ~, then return it to the battlefield
  transformed", "return it … [tapped and] transformed" and Saga III turn the face over (`keyword_actions.transform`,
  `RulesState.transformed` for 701.27f, `Move.back_ids` for 712.14a). Not read: "transform it / target …", delayed "transform",
  "transforms into" triggers (701.27e), disturb, craft, modal and meld cards, casting a card transformed, copies of a back face (MV 0).
- **Merged and melded permanents** (wave 18D, 702.140 / 730 mutate, 701.42 / 712.4 / 712.21 meld; `app/game/merging.py`, `app/rules/merged.py`):
  one permanent is one `CardInstance` (the shell: its id is the object's identity) whose card fields are the topmost component's and
  whose `merged` lists every card / token (`MergedPart`, topmost first; `melded` for a meld pair, the shell then wearing the combined
  back face). `characteristics.merged_of` adds every component's abilities (a lower card's own name is read as the permanent's) and sums
  a melded permanent's front-face mana values; `ops.move_card` breaks the pile up when the permanent leaves the battlefield (a token
  component ceases to exist; the commander is the card the shell becomes for a move to hand / library / command zone so 903.9b-c work
  as for any commander, `Move.rest_zone`). "Mutate {cost}" is an alternative cost (tag "mutate", offered only with a non-Human creature
  you own that is `merged.mergeable`), the spell targets it, resolves into `Merge` after an over / under decision (illegal target:
  creature spell, 702.140b), emits the "mutated" event ("Whenever this creature mutates"), and "the number of times this creature has
  mutated" is the pile size minus one. Meld: "exile them, then meld them into X" (condition "you both own and control ~ and a creature
  named Y", names carried as `meldname:<hex>` through the grammar) is the `meld` primitive: both cards exiled, then one `Meld` step
  and the normal entry path. Refused (manual): mutating onto a face-down, double-faced, flip, copy, melded or copied-over permanent or
  with a token / copy spell, a second commander in one pile, copies of a merged or melded permanent or of a mutating spell,
  "cast from your graveyard using its mutate ability" (Brokkos), Mishra, Claimed by Gix (enters tapped and attacking), The Meld Hound,
  Pollywog Symbiote, Surgeon General Commander ("augment"). A pile leaving is one permanent leaving (one leave / dies
  trigger); each other card gets its own zone-change event "from the battlefield" with no old object (`rules_state._diff`), so
  "put into a graveyard from anywhere" sees every card, and `merged.pieces` / `triggers.pile_refs` make "return it", blink, "exile
  until" and exiled-with find all of them (730.3c). Put on top / bottom of its owner's library by `to_library`, the owner orders the
  cards (730.3a); in a graveyard (and among several cards ordered together) the order is the pile's.
- **Ability-word flavor prefixes**: the deny list of rules-bearing "Name —" prefixes in
  `oracle.word_prefix` is maintained by hand; add new mechanics to it.

Known approximations (correct in normal play; listed so nobody is surprised):

- **Shield counters** (7C, 122.1c): other prevention applies first and the shield takes what is left; one
  counter is removed per simultaneous damage batch.
- **"Blocks this creature if able"** (7E): the requirement check is lenient when the blocker has a
  competing requirement (509.1c's maximum-requirements rule is not solved there).
- **Untap step choice** (7F): "you may choose not to untap" is a real decision during the untap step, with
  no priority (502.4). A skipped untap step no longer removes stun counters.
- **Split second** (8A): while a split-second spell is on the stack, the existing auto-pass may pass for a
  player who could still take a special action (turning a face-down creature up, 116.2). Not yet reviewed.
- **Partner with** (8A): the enters trigger follows CR 702.124j (search and reveal) rather than the shorter
  current Oracle reminder text.
- **Coin flips** (7E): heads counts as a win (the call doesn't change the odds, 705.2); the result is
  recorded on the table step, so replay and saves reproduce it.
- **"Each player may pay"** (6F, fixed in 6R): choices are made in turn order, then all payments happen at
  once (101.4). The older `designations.each_unless` still pays as each player chooses; this only matters
  for non-mana costs.
- **State triggers** (6D, 603.8) are re-checked when the table produces events, not when an effect ends
  during cleanup.
- **"Can't win the game"** (`win_game`) reads only printed text on the battlefield.

- **Cards cast by hand** (moved to the stack manually): X, converge, kicks and every "mana was spent"
  condition read as 0 or false. Since wave 4R the log says so and asks the table to adjust by hand.
  A spell moved onto and off the stack by hand between two engine actions isn't seen by "first spell
  each turn" or the spells-cast count.
- **Elvish Refueler**: while it's on the battlefield the engine never blocks a second exhaust
  activation; the player is trusted.
- **Conditions on an attached object** (wave 4B) read its characteristics without other statics'
  layer 4–6 grants.
- **"Loses all abilities"** (wave 4L) now also removes static abilities (Lignify ruling). Its
  interaction with Humility-style layer dependencies was not tested further.
- **"Whenever you discard"** triggers don't see madness discards (the turn history counts them).
- **Face-down masking** replaces a face-down card's name in log lines, prompts and option labels. It is
  tied to the cards each text refers to; `rules_view.stats` skips face-down creatures, so even their
  controller doesn't see a pumped face-down creature's real P/T (cosmetic).
- **Kept mana** (106.4) is spent last automatically instead of asking the player.
- **Firebending** keeps as much {R} as it added, as if the player spent other red first.
- **Ring-bearer** after control changes hands and back within one resolution stays the bearer.
- **Stun counters** don't stop paying {Q} untap costs.
- **Palace Jailer** whose controller left the game: the exiled card stays exiled (rule not settled).
- **"Entered this turn"** freezes only types and subtypes as the permanent entered.
- **Total/different-name target limits** are checked when targets are chosen, not again on resolution.
- From before: 800.4j simplified (the leaver's turn ends at once), 800.4a reanimated permanents
  returned instead of exiled, 610.3d for ordinary departures returns one source at a time, 701.21a
  in the echo/"sacrifice unless you pay" path, 903.9b without a remembered answer, "before attackers
  are declared" modelled conservatively, the do-once "may" memory key shared by same-named triggers,
  Karador/Kess fixtures using simplified wording.

## Rules and architecture decisions to preserve

- **Commander-only** card automation scope; coverage is measured over Commander-legal cards.
- The stored **current Comprehensive Rules are authoritative.** Never rely on remembered rules
  (use the `mtg-rules-research` skill).
- **No LLM as a runtime rules judge.** Card text is never executed; scripts are declarative data.
- **Unsupported behavior falls back to manual.** Wrong automation is worse than manual: refuse
  rather than guess. A card is **FULL** only with complete, tested behavior.
- The **rules engine is authoritative**; the renderer is not. Manual moves stay available.
- **Hidden information must never leak.** This includes leaks by omission: a question skipped only
  when the hidden answer is "nothing" tells the table that (wave 4R, Snarl lands).
- Work reusable gaps ranked by data. **Do not chase cards one by one.**
- An independent rules review comes before merging risky subsystems.
- 3D polish, plane themes, decorative toys, the command palette and final screenshots are
  **late-stage work**.
- Security: validate WebSocket messages and file imports, no path traversal, no telemetry, no need
  for Internet access during games.

## Next session start instructions

1. Start from PR #14 (`claude/beautiful-ramanujan-l9pev4`; the face-down id fix is merged, 6,698 tests); check CI.
2. Set up: `cd backend && python3 -m venv .venv && .venv/bin/pip install -e '.[dev]' 'mypy==2.3.1'
   pytest-xdist`; the card DB with `scripts/update-cards.sh --images none`; `cd frontend && npm ci`.
3. Read this file and `.claude/skills/fyodor-game-development/SKILL.md`.
4. Open items the reviews named (each small): the opening-hand step should not block game start on an
   unexpected rules error (wrap `resolve._opening_steps`); squad/replicate/offspring still count as "kicked";
   madness grants its cast before its trigger resolves (fixed for miracle only); borrowed abilities don't
   include abilities the lender has only from other effects (613.8); the controller's own stops drive the
   controlled player's priority; `RulesState.unlocked`/`foretold` keep stale entries. Face-down ids (18R review): an open decision whose
   `source_id` was the old card shows the new id; turning an exiled face-up card face down in place keeps its id;
   the older face-down `shuffle` renaming in `handlers/zones.py` rewrites only `copy_of`, not rules state.
5. Still manual on purpose: unsettled rulings (a copied Room spell's door 709.5d, Hellrider-style damage
   after leaving combat, "lands enter untapped"), Attractions (per-printing lights aren't in the data),
   Bolas's Citadel, Garth One-Eye/Magar, Chrome Mox, Word of Command.
6. Then continue the long-tail sweeps from a fresh `gap_rank` (mostly single-card wordings now), one family
   per agent, each with a coverage diff, and an Opus head review for any new system.

## Usage control

- This session ran five agents at a time for hours; nearly all usage came from subagents working at more
  than 150k context. Give agents smaller scopes (one family, two to four wordings) so they finish before
  their context grows, and run fewer in parallel when limits matter.
- Targeted tests while implementing; full verification at integration checkpoints. The full backend suite
  takes 2–6 minutes with `-n 8`, depending on load.

## Rooms (wave 18G)
CR 709.5: a Room is a split card with one shared type line. `RulesState.unlocked` (object -> unlocked doors, 1 left / 2 right) is the
designation; `characteristics._room` is the card with both doors (the right door's abilities carry `section=2`), `copying.with_level`
narrows it to the doors that count (a locked half has no name, mana cost or text; on the stack only the cast half), and
`scripts.definitions` drops a locked door's abilities. Casting a half unlocks it as the Room enters (`rooms.entered`; the cast face is
kept on the stack object); the unlock cost is the `unlock_door` special action (`rooms.unlock_action`); "When you unlock this door" is a
`designation` event (`counter="unlocked"`) read by `designations.facts`. Not done: "fully unlocks" / "lock" wordings (no Commander
card), and the Room cards with other blockers: Smoky Lounge // Misty Salon (restricted trigger mana), Central Elevator // Promising
Stairs, Dollmaker's Shop // Porcelain Gallery, Secret Arcade // Dusty Parlor, Charred Foyer, Cramped Vents, Greenhouse, Walk-In
Closet, Polluted Cistern, Experimental Lab. Attractions (CR 717) are not built: the lit-up numbers are per printing and not in the
card data, and the supplementary Attraction deck needs deck-building support.

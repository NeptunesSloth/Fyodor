# Current state — handoff for the next session

Written 2026-10-10 at the end of the session that built PR #15: rules-engine waves 19–29 on top of PR #14
(now merged). Every wave and engine track had an Opus head review before it was merged. Every number here was
checked against local runs at that time.

## Current repository state

| | |
|---|---|
| Repository | `NeptunesSloth/Fyodor` |
| `main` | Has PRs #7–#14 (waves 1–18). |
| Open PR | **#15** (`claude/beautiful-ramanujan-l9pev4`, draft): waves 19–29, each reviewed. |
| GitHub CI | Since 2026-10-10 01:30 UTC every job fails within 2–3 s without a runner (`runner_id: 0`, no steps run), on every head. This is an Actions account or runner problem (minutes, spending limit or outage), not the code; a comment on PR #15 says so. Verify locally until it is fixed. |
| Agent branches | `claude/wave19*`–`claude/wave29*`, `claude/review-wave*`, `claude/wip-*`: all merged into #15; safe to delete once #15 is merged. |

## Last known test status (PR #15 head, wave 29 merged)

| Check | Status |
|---|---|
| Backend pytest (full, `-n 2`) | Final run on the wave 29 head in progress at the time of writing; the run before 29D merged had 9,119 passed and 2 failing tests, both fixed since. |
| ruff / mypy (`app tools`) | Clean. |
| Frontend tsc / vitest | Clean on wave 29B (no frontend change in wave 29). |
| Browser end-to-end (Playwright, production build) | 20 passed locally on `fef8b49` (wave 28); not rerun since (no frontend change in wave 29). |

The repo's pytest `addopts` includes `-q`; pass no extra `-q` or the "N passed" summary line is suppressed.
Run the suite in the background with a long timeout: it takes about 10 minutes with `-n 2`.

## Current Commander coverage

Data: Scryfall snapshot 2026-10-03, Comprehensive Rules 2026-09-25. Per-card diff: dump
`coverage.of_card_data(...).level` for every Commander-legal card at two heads and compare. A dump taken
from a worktree must put that worktree's `backend` first on `sys.path`, or it silently measures the main
checkout.

| | `main` before PR #13 | PR #14 (merged) | Now (PR #15 head) |
|---|---|---|---|
| FULL | 19,506 (60.8%) | 22,896 (71.4%) | **24,902 (77.7%)** |

No card that was FULL on `main` lost FULL in PR #15. Per wave: 19 +346, 20 +224, 21 +114, 22A–F +275,
23 +231, 24 +170, 25 +325, 26 +217, 27 +32, 28 +52, 29 +20. Wording sweeps stopped paying off at wave 27;
waves 28–29 built engine features and fixed what the reviews found.

## What PR #15 added

The PR description lists every wave. In short:

- **Waves 19–21:** long-tail wording sweeps.
- **22A–22F engine tracks:** layers (Blood Moon, Humility, Opalescence), prohibitions and card names,
  replacements and the 616.1 order prompt, linked objects, event history, casting costs.
  `tools/inventory.py` and `docs/AUTOMATION_INVENTORY.md` list every blocker per non-FULL card.
- **Waves 23–26:** player filters, villainous choice, Pacts, value grammar, exploit, crew and saddle, gift,
  copy exceptions, speed, soulbond, dice, loops, counter kinds, flip cards, airbend, Adventures and MDFC
  faces from exile, join forces, eminence, "<group> target player controls", opponent-library searches,
  paid X, forage, collect evidence, paired fights.
- **Wave 27:** the last wording sweep (+32).
- **Wave 28 (engine):**
  - playing a card during resolution, lands included (608.2g);
  - draw replacements and one life-loss choke point (`replace.lose_life`);
  - abilities granted to spells, and hand-activated abilities named on the stack;
  - chosen-cost mana abilities during payment prompts (`Rules.payment_outer`);
  - "where X is" values read from the trigger event.
- **Wave 29 (correctness):**
  - priority hints 50× faster (`read_pass.py`);
  - layer derivation state made thread-local; two games derived at once used to corrupt each other;
  - face-aware cascade, discover and suspend;
  - no 20-target caps;
  - Mad Wizard's Lair reveals only cards actually drawn;
  - hideaway (702.75) and "your life total can't change".

The head reviews found and fixed about 130 real bugs across the PR, each with a regression test.

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

`python -m tools.gap_rank --top 15` on the PR #15 head (FULL 24,902, PARTIAL 7,166; commanders FULL 2,143).
"Sole" = non-FULL cards whose every unsupported line is in that family (an upper bound). What remains is
mostly wordings that appear on one or two cards each; `tools/inventory.py` lists every blocker per card.

| # | Family | Missing lines | Sole | Sole commanders | Examples (by EDHREC rank) |
|---|---|---|---|---|---|
| 1 | static_other | 2360 | 1068 | 106 | Chaos Warp, Dawn's Truce, Birgi, God of Storytelling // Harnfel, Horn of Bounty, Valakut Awakening // Valakut Stoneforge |
| 2 | trigger_other | 1214 | 843 | 220 | Guardian Project, Forgotten Ancient, Kutzil, Malamet Exemplar, Selvala, Heart of the Wilds |
| 3 | if_you_do | 807 | 633 | 148 | Saw in Half, Bloodchief Ascension, Etali, Primal Conqueror // Etali, Primal Sickness, Tainted Pact |
| 4 | counters | 481 | 316 | 92 | The Darkness Crystal, Tezzeret, Cruel Captain, Phelia, Exuberant Shepherd, Parting Gust |
| 5 | activated_other | 398 | 315 | 49 | Arcane Lighthouse, The Black Gate, Mount Doom, Secret Tunnel |
| 6 | this_turn_state | 359 | 283 | 55 | Veil of Summer, Conduit of Worlds, Combat Celebrant, Hunter's Insight |
| 7 | damage_sized | 283 | 212 | 31 | Descent into Avernus, Myr Battlesphere, Combustible Gearhulk, Wheel of Misfortune |
| 8 | attached_events | 254 | 206 | 7 | Commander's Plate, Gift of Immortality, Witness Protection, Ghoulish Impetus |
| 9 | x_value | 336 | 199 | 44 | Torment of Hailfire, Crackle with Power, Steel Hellkite, Shark Typhoon |
| 10 | instead | 263 | 181 | 30 | Academy Manufactor, Incubation Druid, Aven Mindcensor, Twinning Staff |
| 11 | as_long_as_static | 254 | 176 | 29 | Promise of Loyalty, The Reality Chip, Conqueror's Flail, Cloud, Midgar Mercenary |
| 12 | reanimation | 219 | 118 | 17 | Sevinne's Reclamation, Agadeem's Awakening // Agadeem, the Undercrypt, Haven of the Spirit Dragon, Tergrid, God of Fright // Tergrid's Lantern |
| 13 | free_cast | 185 | 112 | 36 | Tibalt's Trickery, Urza, Lord High Artificer, Expressive Iteration, Muldrotha, the Gravetide |
| 14 | ability_word | 160 | 92 | 20 | Springheart Nantuko, Augur of Autumn, Ob Nixilis, the Fallen, Thunderfoot Baloth |
| 15 | activation_cost | 102 | 75 | 28 | Priest of Forgotten Gods, Kozilek, the Great Distortion, Chainer, Nightmare Adept, Jaxis, the Troublemaker |

## Known shipped limitations and open items

Still manual on purpose (each has its reason in code, mostly `coverage.REFUSED`, refusal checks in
`scripts.define` or module docstrings):

- **Reflexive triggers** reading the sacrificed object anywhere other than its power, toughness or
  mana value (Surtland Flinger's "was a Giant", Minsc & Boo), several sacrificed objects, mandatory
  forms (Tip the Scales).
- **Chosen selectors**: Roaming Throne, Cloud Key's chosen card type, protection from the chosen color;
  a trigger whose source left the battlefield matches nothing for "the chosen type".
- Lim-Dûl's Vault, Protean Hulk. (Sylvan Library: wave 18G, `drawn_toll.py`; the per-card "drawn this turn"
  record is `TurnLog.drawn`, private. Jandor's Ring's "discard the last card you drew this turn" cost can use it, not done.
  Djinn of Wishes was manual only for want of playing a land mid-resolution, no unsettled ruling: wave 28A plays a card as an
  effect resolves, `permissions.free_cast` "play", 608.2g / 305.2a-b / 305.3 / 712.12.)
- Granted casts (wave 29B, `granted_casts.py`): the "cast it?" choice of cascade, discover, ripple, suspend and rebound offers every half / face
  that is a spell ("yes" = first half / front, "yes@1" = Adventure / second half / back face; `RulesState.free_cast_faces` is the one
  `casting.cast_free` takes). Each is checked on its own against the cascade ("resulting spell's mana value is less", 702.85a) / discover
  ("N or less", 701.57a) value and the cast prohibitions (601.3); the card in exile keeps the combined / front / creature mana value that
  stops cascade (709.4b, 712.8a, 715.4). With no way left to cast it the question is skipped and the declined outcome happens. Ripple's "same
  name" is one name in common (201.2a, 709.4a). A declined cascade card lands at a random place among the cards put on the bottom before the
  question (702.85a: all of them in a random order). A suspended modal double-faced card's land face is played ("play it", 702.62a; 305.2a-b,
  305.3), the only one of these that plays rather than casts.
  Review 29B: a half / face that can't be cast for a public reason (`casting.free_cast_problem`: no legal target 601.2c, no mode 700.2a,
  205.4e, a mandatory additional cost that can't be paid) isn't offered (its answer was a dead end: the free cast's target choice couldn't be
  cancelled); a cost part read from the hand and mana aren't checked ahead (hidden; hand-activated mana). A free cast begun as an effect
  resolves is recorded (`RulesState.free_cast_then` with `granted`): cancelled at a target (now allowed, `casting._announcing`) or at its
  payment, the card goes where a card not cast goes (bottom / hand / exile / graveyard) instead of staying in exile with its grant.
  Known gap: the order of cards put on the bottom "in a random order" is readable from the log (one move line per card, as before 29B).
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
- **Replacements: draws, life, mill** (wave 28B): a draw replaced by its own instructions ("If you would draw a card, instead look at the top
  three … / exile the top two … / you draw two cards and lose 1 life": `draw_bodies.py`, run once the draws before it have happened, 121.6b;
  `then` None sites log it for the players), "you may … instead" (optional, like Dredge), "The next time you would draw a card this turn"
  records (Words of Worship / Wilding / Waste; spent by the first draw they replace), count-level draws (121.2a: Quantum Riddler, Alms Collector),
  "while you have no cards in hand / N or less life" conditions, and a life-loss choke point (`replace.lose_life`: effects, payments of life — 119.4,
  118.11 — and the life damage causes, 120.3a: Bloodletter of Aclazotz) plus mill counts (`replace.mill_counts`: Bruvac, The Water Crystal).
  Still manual: "first time you would draw each turn" (Reed Richards, Scion of Halaster), Island Sanctuary (skip + attack restriction), draws
  that need a player choice from another player (Zur's Weirding, Breathstealer's Crypt, Chains of Mephistopheles), library-of-another-player
  bodies (Shared Fate, Uba Mask), "put into a pile" bodies (Parallel Thoughts, Mangara's Tome), Abundance, Archmage Ascension, Words of War /
  Wind (targets, "each player returns"), Aladdin's Lamp / Ring of Ma'rûf (X, outside the game), Plagiarize (a targeted record).
  Review 28B: a mana ability's "Draw a card." and "deals 1 damage to you" go through the draw and life-loss replacements (a mana ability
  can't pause: a body there is left to the players); Alms Collector's "each draw a card" are one-card instructions Quantum Riddler may still
  change; one call's life gains are simultaneous for Phial (702.15e). Paying life under Bloodletter: no ruling names it — 119.4 (paying life is
  losing it; affordability is the cost's amount), 118.11 (a cost's actions may be modified) and the Invigorate ruling (2020-08-07: a cost
  whose action a replacement changes can still be paid) decide it: the payment is doubled. The two known gaps (a mana ability's damage not seen
  by damage replacement / prevention; Mad Wizard's Lair revealing cards a "draw two instead" drew) are closed in wave 29C (below).
- **Silent caps, leaks and restrictions** (wave 29C, the open items of the wave 27 / 28 reviews): casts and activations take up to
  `actions.MAX_TARGETS` = 250 targets (601.2c; it was 20, so "up to X target …, where X is …" and "any number of target …" were clamped): one
  limit shared by the intents, target counts, division (601.2d), Choose amounts and the parser; "up to X" over it says so in the prompt, an
  exact "X target …" over it is refused; arrows come in chunks of 20 (`Plan.target_arrows`). A player may pay all their life (119.4: the Phyrexian
  auto-payer stopped at life = payment); life other costs of the same spell pay is reserved first (`Plan.reserved_life`), and several "Pay 1
  life" mana sources can't take more than the life total. "Draw N cards and reveal them" reveals only cards drawn without a replacement
  (121.6c, 614.11b and the Sindbad / Fa'adiyah Seer / Pact Weapon / Jace, Mirror Mage rulings: "even if the draw is replaced by another
  draw": Phial of Galadriel, Blood Scrivener, Thought Reflection — `TurnLog.drawn_replaced`). Review 29C: when a replacement changed the
  NUMBER the instruction draws (121.2a / 616.1g: Quantum Riddler, Alms Collector — `TurnLog.drawn_counted`) it is UNSETTLED whether "them"
  covers those cards (614.11b read literally: none; 121.2a's "the instruction is modified": all; no ruling) — Mad Wizard's Lair hands the
  reveal and the free cast to the players (a manual_resolution decision), revealing and offering nothing. "If you do" after a draw (review
  29C, 118.12 / 118.11: the player chose to draw "regardless of what events actually occurred"; the Psychic Vortex and Notion Thief rulings)
  holds once the draw was started, whether a replacement took it (Underrealm Lich, Notion Thief) or the library was empty; a declined
  "may draw" binds nothing. Intents carry MAX_TARGETS per target group (× `MAX_GROUPS` = 10 in all: "target creature … each of X target
  creatures" has X + 1); the engine's target arrows stop at 190 on the table (it refuses the 201st). A mana ability's "deals 1 damage to you" is a damage
  event of `replace.damage_outcome` (`casting.mana_ability_damage`): replacement / prevention / shields apply; two effects whose order matters
  are logged for the players (a mana ability can't pause, 605.3a). Caps removed: convoke / improvise / delve lists in the tap-mana prompt
  (the table clicks only listed helpers), "pay any amount of {E}" (60 → 250, said in the prompt), untap-lock lists (250 → all) and
  may-stay-tapped candidates (50 → all). Still bounded, loudly: multikicker count ≤ 20, X ≤ 1000, one choice answers with ≤ 250 options.
- **Replacements** (wave 22C): counter putters ("If you / an opponent would put …": Vorinclex, Lae'zel, Pir; the
  putter is `by`, 122.6a; review 22C: counters "given" are put — 122.6, 701.34a — so infect/toxic poison is put by the
  source's controller, 120.3b/g, and "target player gets N" by the effect's controller), "reveal ~ and shuffle it into its owner's library instead" (Blightsteel, Nexus of Fate),
  "exile instead" with a rider (Kalitas token, Head of the Hunt reflexive trigger, life), "If it would leave the
  battlefield, exile it instead" (Whip of Erebos family), and the 616.1 choice between differing graveyard
  replacements (the card stays put and its controller is asked before priority: `pending_616`). Still manual:
  Academy Manufactor and Divine Visitation (token replaced by another:
  ordering with the "plus a Food" statics is unsettled), exile with
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
- **"Loses all abilities"** (wave 4L) now also removes static abilities (Lignify ruling).
- **Group layers** (wave 22A, `group_layers.py`): group statics of layers 4-6 (Blood Moon, Humility, Opalescence,
  March of the Machines, Lattice-style colors, legendary) are solved against the table: 613.6 members per effect,
  613.8 dependencies (subject changes, 305.7 ability loss), loops in timestamp order. Not modelled: dependencies
  between per-object effects (resolved spells, Auras) and these statics beyond timestamps, 613.8a(c) for CDAs;
  conditions on a group static are read as it is solved (counts of types it leaves alone only). Manual: Titania's
  Song (leaves-the-battlefield duration), Yixlid Jailer (graveyard), Planar Nexus, Ghostly Flame, named/renamed Auras.
  Review 22A: layer-6 "lose all abilities" statics also wait for one that takes their source's ability (613.8, Dress Down +
  Sludge Monster); a lost "*" CDA leaves 0 (208.5); entry replacements, enter-as-copy and group statics are read from the
  permanent as it would exist on the battlefield (614.12: Blood Moon + shock lands / Vesuva, Humility + Walking Ballista).
  Still not modelled: 614.12 for the entering permanent's own statics (Opalescence entering doesn't see itself — correct —
  but e.g. its own layer-4 statics on itself as it enters).
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

1. Start from PR #15 (`claude/beautiful-ramanujan-l9pev4`). GitHub CI has had no runners since 2026-10-10;
   check whether that is fixed before trusting a red check, and verify locally (backend ruff, mypy, full
   pytest; frontend `npm run typecheck`, `npx vitest run`; `npx playwright test` after `npm run build`).
2. Set up: `cd backend && python3 -m venv .venv && .venv/bin/pip install -e '.[dev]' 'mypy==2.3.1'
   pytest-xdist`; the card DB with `scripts/update-cards.sh --images none`; `cd frontend && npm ci`.
3. Read this file, `.claude/skills/fyodor-game-development/SKILL.md` and `docs/AUTOMATION_INVENTORY.md`.
4. Follow-ups the wave 27–29 reviews named, most important first:
   - **Hidden information:** "put the rest on the bottom in a random order" outside cascade and discover
     (`rest_looked`, `rest_exiled`) still logs one move per card, so the new library order is readable.
     Cascade and discover already use one batched move (`effects.bottom_at_random`); reuse it.
   - **"If you do" (118.12):** the draw check now follows the player's choice. Exile, bounce and counter
     checks still look at the result instead; research each against 118.12 and the rulings before changing.
   - **Sacrificing the spell's own target while paying for it** (Ashnod's Altar mid-cast) is not offered;
     the prompt explains it. Supporting it needs target re-checks after a replayed announcement.
   - **Mana-ability damage with a prevention add-on** (Deflecting Palm) runs the add-on even though a mana
     ability can't pause.
   - **Hint and castable checks** (`can_pay`) don't know source or additional life costs; the cast is
     refused with a message instead.
   - **Sync endpoints** `game_summary` and `/rules/scenario` still read tables on the threadpool (derivation
     state is now thread-local, so they no longer corrupt each other).
   - **Free casts:** Ripple's "any order" puts the declined card last. In auto payment mode, a cost that
     can't be paid is refused at the target answer (Cancel works).
   - The older items from PR #14 below (opening-hand errors, squad/replicate as "kicked", madness timing,
     613.8 borrowed abilities, stale `RulesState` entries, face-down id details).
5. Still manual on purpose: unsettled rulings (Hellrider-style damage after leaving combat, a copied Room
   spell's door, "lands enter untapped", "first time you would draw each turn", whether a permanent counts
   itself for "enters with a counter for each <group>", Mad Wizard's Lair under a count-changing draw
   replacement, Bloodletter's doubled life payments follow 119.4/118.11 with no ruling found), Attractions,
   banding, outside-the-game, voting and piles, Phyrexian Unlife-style 704.5a statics.
6. Coverage gains now come from engine features, not wording sweeps (wave 27 gained 32 cards in four
   tracks). Pick features from a fresh `gap_rank` and `tools/inventory.py`, one per agent, each with a
   coverage diff, a dump of every Commander-legal card's parsed definition at base and head (verify every
   changed card), and an Opus head review.

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

## Counter kinds, suspend granted, flip cards, hone counters (wave 24C)
- `counter_kinds.py` (122.1, 608.2d): "for each kind of counter on target permanent [or player], give … another counter of that kind", "put another
  … or remove one", "choose a counter on …, give …", "remove any number of counters" (the controller says how many of each kind, kind by kind;
  `counter_moves` asks the same for "move any number of counters"). Gives are puts through the counter choke point. `target permanent or player`
  is a target selector now. Not read: "each other creature" after "choose a kind of counter on a creature" (Contractual Safeguard: other than what),
  "any number of counters" from a group of sources, "suspended card" targets (Clockspinning, Jhoira's Timebug).
- `suspend_grants.py` (702.62b): "exile it with N time counters on it. If it doesn't have suspend, it gains suspend" is the exile, the counters and
  joining `RulesState.suspended` (a card that left exile or lost its last time counter is dropped at the next upkeep, `triggers._suspend`).
  Not read: counters equal to a mana value chosen from a hand (The Eleventh Doctor), a cost exiling a card from a hand (Jhoira of the Ghitu),
  Soothsayer / Venture Forth ("the rest on the bottom in a random order").
- Flip cards (CR 710): `keyword_actions.flip` turns a layout-flip card's permanent upside down (`CardInstance.flipped`, the Kamigawa rotation the manual Flip button toggles; one-way, forgotten off the battlefield: `ops` resets it);
  `characteristics._of` reads the alternative face while it is flipped, and `_from_card_data` keeps the front's mana cost, mana value and colors (710.1c). Copying a flip card stays by hand
  (`copying.supported_source`). Flip cards with other blockers: Nezumi Graverobber, Nezumi Shortfang, Kitsune Mystic, Homura, Sasaya, Erayo.
- "enters with" under a negated cast condition ("if you didn't cast it from your hand", "unless you've cast another red spell this turn") reads
  the same condition grammar; a negated mana test stays refused (a spell cast by hand has no known payment).
- Hone counters (122.1j): +1/+0 to the creature the Equipment is attached to (`layers._hone`, layer 7c).
- "[mandatory counters]. When you do, …" is a reflexive trigger (603.12) that waits for the counters really being put (Solemnity stops it).
- Forecast (702.57a): "Forecast — {cost}, Reveal this card from your hand: …" is an activated ability from the hand (`costs.REVEAL_SELF`, `from_hand`),
  your upkeep only and once each turn (`restrictions.parse`); the reveal is shown in the log and ends at once (`cost_payment.pay`). The hand menu offers it
  (`rulesMenu.ts`). Not read: a forecast cost tapping creatures (Sky Hussar), Paladin of Prahv's "whenever target creature deals damage this turn".
- Not built (left for later): the Adversary cycle ("pay … any number of
  times"), cast-trigger riders ("that creature enters with an additional +1/+1 counter": Torgal, Kumano, Fenrir), enters-as-copy with counters (Spark Double).

## Spell grants and hand abilities (wave 28C)
- `spell_grants.py` (113.6, 604.1, 613.1f): a static "Instant and sorcery spells you control have lifelink / deathtouch / split second" (Radiant
  Scrollwielder, Soulfire Grand Master, Heartflame Duelist, Firesong and Sunspeaker (red), Pestilent Spirit, Samut) gives the keyword to the spells
  on the stack its controller controls, read afresh each time the spell is derived (`layers._derive`, like `zone_grants`): it ends when the source
  leaves. "Noble creatures you control and Lesson spells you control have lifelink" (Lo and Li) is the ordinary creature grant plus `spell_grants`.
  Lifelink and deathtouch apply to the damage the spell deals (`effects._ability_source` reads the spell's keywords on the stack, 702.15b / 702.2b);
  `split_second.on_stack` reads the spell with its grants (702.61a). "Spells you cast have …" for other keywords stays in `cast_limits`.
- "The next [noncreature] spell you cast this turn has improvise / convoke / affinity for artifacts / cascade / storm" (Archway of Innovation, Wand of
  the Worldsoul, Flockchaser Phantom, Saheeli the Gifted, Don & Raph, Dark Apostle, Sloppity Bilepiper, Smoldering Stagecoach, Crackling Spellslinger,
  Storm, Force of Nature) is `RulesState.next_spell_grants` (`NextSpellGrant`): read while the next matching spell is cast (`cast_limits.granted_helpers`
  / `granted_affinities` / `granted_instances`), used up by `history.note_cast`, ended in cleanup. A grant naming a kind of spell waits for one.
  Not read: Shadow the Hedgehog's split second "if mana from an artifact was spent" (a payment condition), TARDIS's "and you may planeswalk".
- Hidden-zone abilities (602.2a, 701.20a): `casting._create_ability` reveals a card activated from the hand for the moment the ability is created,
  so cycling, channel, transmute, ninjutsu and every other ability from the hand name their source on the stack; the rest of the hand stays hidden.
  Review 28C: ninjutsu's card stays revealed from the announcement (`keep`, 702.49b) instead of being revealed, hidden and revealed again.
  Wave 29B: a face-down creature spell given cascade or ripple by an effect (Sloppity Bilepiper, Maelstrom Nexus, Thrumming Stone) has it (708.2
  limits only its own abilities; 613.1f, 601.2a): its mana value is 0 and it has no name (708.2a), so cascade exiles the whole library and finds
  nothing and ripple matches no name (201.2a). A storm grant to a face-down spell is refused (no printed card gives a creature spell storm).

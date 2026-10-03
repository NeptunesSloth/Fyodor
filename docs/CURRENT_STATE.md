# Current state — handoff for the next session

Written 2026-10-03 at the end of the session that built PR #12 (waves 5–8 and part of wave 9 of the rules
engine). Every fact here was checked against git, CI and local runs at that time. Where something was not
verified, the text says so.

## Current repository state

| | |
|---|---|
| Repository | `NeptunesSloth/Fyodor` |
| `main` | Has PRs #7–#11 (rules engine waves 1–4). |
| Open PR | **#12** (`claude/dazzling-heisenberg-h6juen`, draft): waves 5, 6, 7, 8 and 9A, with the wave 5 and wave 6 reviews. **Not ready to merge yet**: the wave 7 and wave 8 reviews are not done (see "Next session start instructions"). |
| Unfinished agent branches (pushed, **not merged, not verified**) | `claude/wip-wave7r` (wave 7 review, partly done), `claude/wip-wave9b`, `claude/wip-wave9c`, `claude/wip-wave9d`. All stopped at a usage limit; the last commit on each is a snapshot of uncommitted work. |
| Merged agent branches | `claude/wip-wave5*`, `wave6*`, `wave7a`–`7f`, `wave8a`–`8d`, `wave9a`: all merged into #12; safe to delete once #12 is merged. |
| Agent worktrees | Local to this session's container and gone with it. |

## Last known test status (PR #12 head, wave 9A merged)

| Check | Status |
|---|---|
| Backend pytest (full, `-n 8`) | Passed locally: 4,723 tests. |
| ruff / mypy (`app tools`, 234 files) | Passed locally. |
| Frontend tsc / vitest | No wave in PR #12 touched the frontend. |
| Playwright (20 specs) | Passed locally after waves 7C/7F were merged, and in GitHub CI on `9f0cfd7` (all of wave 8). One failure on `cbd835b` (`offline.spec.ts`: the 3D table not visible after create-game) did not reproduce locally or on any later CI run. |
| GitHub CI | Green on `9f0cfd7`. Check the newer head (9A and this file) before relying on it. |

`test_rules_statics.py::test_full_board_derive_is_fast` (500 ms) can fail under heavy load (several agents
running full suites at once); rerun it alone.

## Current Commander coverage

Data: Scryfall snapshot 2026-09-30, Comprehensive Rules 2026-09-25.

| | After PR #11 (`main`) | Now (PR #12 head) |
|---|---|---|
| Commander-legal cards | 32,068 | 32,068 |
| FULL | 16,927 (52.8%) | **19,506 (60.8%)** |
| PARTIAL | 15,141 | 12,562 |
| Possible commanders FULL | 1,113 | **1,456** |

Progression in PR #12: wave 5 with its review → 17,850; wave 6 → about 18,960; wave 7 → 19,167; wave 8 →
19,470; wave 9A → 19,506. Each wave compared every card before and after: no card dropped from FULL except
the deliberate wave 5 review demotions below. Reproduce with `python -m tools.gap_rank --db
../data/cards.sqlite` (first line) or `tools.commander_coverage --out <dir>`; `data/reports` were **not**
regenerated.

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
- **Wave 9A**: discover, "where X is" keyword actions (bolster, amass, connive, endure), "the amount of
  mana spent to cast", "creatures that died under your control this turn".

## Top remaining rules gaps

`python -m tools.gap_rank --db ../data/cards.sqlite --top 15` on the wave 9A head. "Sole" = non-FULL cards
whose every unsupported line is in that family (an upper bound). Use `--ngrams <family>` to see the
phrases shared inside the catch-all families.

| # | Family | Missing | Sole | Sole commanders | Examples |
|---|---|---|---|---|---|
| 1 | static_other | 4,572 | 2,105 | 183 | Chaos Warp, Rakdos Charm, Birgi |
| 2 | trigger_other | 2,091 | 1,351 | 334 | Guardian Project, Forgotten Ancient, Necropotence |
| 3 | if_you_do | 1,156 | 811 | 167 | Ripples of Undeath, Saw in Half, Bloodchief Ascension |
| 4 | activated_other | 794 | 559 | 83 | Command Beacon, Emry, Haywire Mite |
| 5 | counters | 824 | 492 | 132 | Spark Double, Opal Palace, Slip Out the Back |
| 6 | attached_events | 458 | 343 | 8 | Trailblazer's Boots, Blade of Selves |
| 7 | this_turn_state | 469 | 340 | 63 | Sylvan Library, Veil of Summer |
| 8 | x_value | 581 | 331 | 65 | Torment of Hailfire, Crackle with Power |
| 9 | damage_sized | 423 | 277 | 33 | Descent into Avernus, Myr Battlesphere (9B in progress) |
| 10 | as_long_as_static | 425 | 269 | 36 | Promise of Loyalty, Conqueror's Flail (9B in progress) |
| 11 | instead | 390 | 235 | 44 | Academy Manufactor, Bloodletter of Aclazotz (9C in progress) |
| 12 | ability_word | 352 | 211 | 31 | Tireless Provisioner, Puresteel Paladin (9C in progress) |
| 13 | reanimation | 361 | 177 | 26 | Sevinne's Reclamation, Haven of the Spirit Dragon |
| 14 | activation_cost | 201 | 138 | 35 | Arena of Glory, Walking Ballista |
| 15 | free_cast | 233 | 121 | 42 | Tibalt's Trickery, Urza, Muldrotha |

Ideas noted but not done: copies with exceptions that enter with counters (Spark Double), mana provenance
("if this mana is spent to cast a creature spell, it enters with a counter"; also needed for complete snow
mana), "you put -1/-1 counters" (several putters in one damage step), a lose-the-game primitive (Final
Fortune), voting, land-type-setting effects (305.7).

## Known shipped limitations and open items

Still manual on purpose (each has its reason in code, mostly `coverage.REFUSED`, refusal checks in
`scripts.define` or module docstrings):

- **Reflexive triggers** reading the sacrificed object anywhere other than its power, toughness or
  mana value (Surtland Flinger's "was a Giant", Minsc & Boo), several sacrificed objects, mandatory
  forms (Tip the Scales).
- **Chosen selectors**: Roaming Throne, Cloud Key's chosen card type, protection from the chosen color;
  a trigger whose source left the battlefield matches nothing for "the chosen type".
- **Sylvan Library** (per-card "drawn this turn" is hidden information), Lim-Dûl's Vault, Djinn of
  Wishes, Protean Hulk.
- **Copies**: cast-a-copy (707.12), "each other object it could target" (Zada), Garth One-Eye / Magar,
  linked abilities (707.7), melded and reversible sources.
- **Mana**: restricted mana added by spells (Geosurge, Karn), "that spell can't be countered" riders,
  restrictions on costs rather than spells, Mana Drain, exhaust mana abilities. Snow mana `{S}` (wave 7E) is paid only by tapping a snow
  source during payment; snow mana already in the pool never pays it.
  A mana ability whose cost a cost modifier changes (Gloom on a white enchantment) is left to the
  player. An enchanted land whose own {T} ability restricts spending is left to the player while
  enchanted.
- **Replacements**: life-loss replacements (no choke point yet), "shuffle into its library instead"
  (Blightsteel, Progenitus), Academy Manufactor, Vorinclex-style counter replacements, count-level
  draw replacements (Alms Collector), Kalitas against another "exile instead", Level/Class/Room lines.
- **Costs**: K'rrik and Dream Halls (per-mana payment), Suppression Field (crew and unearth skip the
  cost-modifier path), activation costs that depend on a target, "Remove X counters from among …",
  comma-listed sacrifice choices, Room cards' cost lines (locked doors aren't modelled).
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

1. Start a fresh session on `claude/dazzling-heisenberg-h6juen` (PR #12) and check CI on its head.
2. Set up: `cd backend && python3 -m venv .venv && .venv/bin/pip install -e '.[dev]' 'mypy==2.3.1'
   pytest-xdist`; the card DB with `scripts/update-cards.sh --images none`; `cd frontend && npm ci`.
3. Read this file and `.claude/skills/fyodor-game-development/SKILL.md` (policies, setup, wave workflow).
4. **Finish the unfinished branches.** Each one is a snapshot taken at a usage limit. Verify everything
   (ruff, mypy, full pytest, a per-card coverage diff) before merging:
   - `claude/wip-wave7r`, the wave 7 review. It had fixed cast timing in extra combats and without a
     declare-blockers step, made power-up keep X, and refused Wight; the rest of its checklist is undone.
     Wave 7 risk points: shield-counter ordering, `Event.group` in saves and replay, the power-up cost
     reduction (118.7), the untap-step rework and stun counters, snow `{S}`, coin flips, the lenient
     must-block check, choice grants, about 30 surprise promotions that were not scenario-tested.
   - `claude/wip-wave9b` (sized damage and as-long-as statics: exile-for-as-long-as permissions, excess
     damage), `claude/wip-wave9c` (instead / ability words: parley, token and mana replacements, opus,
     adventure permanents; marked WIP by its agent), `claude/wip-wave9d` (graft, sunburst, devour, level up).
5. **Review waves 8 and 9 independently.** Risk points: extra-turn edge cases (skipped turns, players who
   left, a save mid-queue); split second against special actions in the auto-pass; partner-with's reveal;
   `pay_objects` binding "that creature" to the paid object; mill as a payment with a short library; 8B's
   scry events and the Dark Confidant `resolve_it` disambiguation; discover's free cast and bottom order;
   "mana spent to cast" on cards cast by hand; surprise promotions such as Wormfang Manta, Magosi, Twice
   Upon a Time and Commence the Endgame.
6. Then wave 10 on the biggest families from a fresh `gap_rank`, then a final **independent review of all of
   PR #12 and of the engine's core premise** (layers, replacements, triggers, priority and the stack,
   privacy, save and replay) by the strongest available model, a coverage run, an update of this file,
   and mark PR #12 ready.
7. On usage limits: commit each agent worktree's work as WIP, push it to `claude/wip-*`, resume with
   `SendMessage`. Keep `.claude/worktrees/` in `.git/info/exclude`.

## Usage control

- This session ran five agents at a time for hours; nearly all usage came from subagents working at more
  than 150k context. Give agents smaller scopes (one family, two to four wordings) so they finish before
  their context grows, and run fewer in parallel when limits matter.
- Targeted tests while implementing; full verification at integration checkpoints. The full backend suite
  takes 2–6 minutes with `-n 8`, depending on load.

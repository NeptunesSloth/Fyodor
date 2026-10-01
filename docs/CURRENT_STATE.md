# Current state — handoff for the next session

Written 2026-10-01 at the end of the session that built PRs #8, #9 and #10 (wave 1, wave 2 and
wave 3 of the rules engine). Every fact here was checked against git, CI and local runs at that
time. Where something was not verified, the text says so.

## Current repository state

| | |
|---|---|
| Repository | `NeptunesSloth/Fyodor` |
| `main` | Has PRs #7 (review 5 fixes + skills), #8 (wave 1: modal abilities, conditionals) and #9 (wave 2: quoted grants, replacement effects stage 2, copy system). |
| Open PR | **#10** (`claude/serene-faraday-f8knp9`): wave 3, below. Marked ready for review at the end of this session; merge it when CI is green. |
| Other branches | `claude/wip-*` backup branches from this session: safe to delete once #10 is merged (deleting them through the session proxy failed; delete them on GitHub). `claude/sharp-curie-nOXLF` is an unrelated old branch; ignore it. |
| Agent worktrees | Local to this session's container and **gone** with it. Everything worth keeping is merged into PR #10. |

## Last known test status (PR #10 head)

| Check | Status |
|---|---|
| Backend pytest (full, `-n 8` with pytest-xdist) | Passed locally on the final head: all 2,944 tests (exit 0). |
| ruff (`backend`) / mypy (`app`, 148 files) | Passed locally. |
| Frontend tsc / vitest (61) / build | Passed locally. |
| Playwright (20 specs) | Passed locally (full suite, `CI=1`). The old flake in `e2e/automation.spec.ts` ("drew 8 cards without finding an Island") is **fixed**: the play page gives player 1 the newest deck, and when the test's two imports landed in different seconds that was Bob's Goblins deck. The test now preselects its deck with `?deck=<id>`. |
| GitHub CI | Green on `3f1f87f` (the last head before the review merge and this file). Check the final head before merging. |

## Current Commander coverage

Data: Scryfall snapshot 2026-09-30, Comprehensive Rules 2026-09-25.

| | Before PR #8 (`main` after #7) | Now (PR #10 head) |
|---|---|---|
| Commander-legal cards | 32,068 | 32,068 |
| FULL | 12,643 (39.4%) | **15,515 (48.4%)** |
| PARTIAL | 19,425 | 16,553 |
| Possible commanders FULL (of 3,501) | 677 | **956** |

To reproduce: build the card database with `scripts/update-cards.sh --images none`, then run
`python -m tools.commander_coverage --db ../data/cards.sqlite --out <dir>` from `backend/` (use
`--out` to keep the committed `data/reports` untouched; they were **not** regenerated).

## What PRs #8–#10 added

Everything below is in the engine with real-card tests (replay and save/load checked); the test
files are named after each area (`tests/test_rules_*.py`). Code blocks are marked with their wave tag
(`wave 1A` … `wave 3R5`) so `grep` finds them.

- **PR #8 (wave 1):** modal triggered/activated abilities (603.3c, 700.2: modes chosen as the ability
  goes on the stack, "that hasn't been chosen", modes with targets); conditional and "instead"
  clauses (conditions.py).
- **PR #9 (wave 2):** temporary quoted grants with durations; replacement effects stage 2
  (doubling, 616.1 ordering loop in `replace.py` choke points: tokens, counters, draws, life gain,
  damage); the copy system (707: copy spells/abilities with new targets, token copies, clones,
  storm).
- **PR #10 (wave 3):**
  - Top gap families: mana abilities and rituals, reanimation, tutors, sized amounts, look at the
    top N, cast-free permissions, costs (additional/alternative/X), gain/exchange control (layer 2).
  - Instant-speed **concede** (frontend RulesHud + intent).
  - All 15 listed rules simplifications fixed, among them: token copies through the 616.1 loop,
    "enters as a copy" bound to the entering object, simultaneous entries (614.12a/b, 603.6a),
    prevent-all by source object, battles and Sieges (`battles.py`), free casts paying additional
    costs, stored "this turn"/"until your next turn" cost modifiers.
  - Sagas (`sagas.py`: lore counters, chapters, read ahead, 714.4 sacrifice) and triggers on the
    enchanted/equipped permanent (603.10a look-back).
  - Player counters (poison, energy incl. {E} costs, experience, rad), monarch, initiative,
    dungeons (all four), the Ring tempts you, day/night (`designations.py`).
  - Goad, face-down (manifest, manifest dread, cloak, disguise, morph/megamorph; `facedown.py`, with
    708 name masking), stun counters, earthbend, firebending, incubate.
  - Previously refused forms, by area: cast-how records (zone, main phase, mana spent: adamant,
    addendum), "entered this turn"/celebration, party, reflexive "When you do" triggers, random
    modes, "choose both instead"; source-of-your-choice shields, unpreventable damage, redirection
    (614.9), skips (614.10), "can't gain life" (614.17), extra different tokens, flashback granted to
    graveyard cards, trailing-duration impulse permissions; magecraft / "copy that spell", copies of
    DFCs, spend restrictions, altar-style mana costs, kept mana, "choose a color"; free casts during
    a resolution (608.2g), Fact or Fiction piles, Thassa's Oracle, tapped-and-attacking puts;
    ability-word activated abilities, self-return triggers from the graveyard (113.6m), finality
    counters, transmute, Gamble/random discard, Gifts, Birthing Pod, "life lost this way", excess
    damage.
  - A final independent review (Opus) fixed: Cryptic Pursuit reading a dead face-down creature as
    the 2/2 (708.9), Palace Jailer's return made immediate (610.3), stale `coverage.REFUSED` entries;
    and added regression tests for the merge seams (firebending + kept mana, Saga lore + rad at
    main 1, primitive probe wrappers, mid-resolution free cast across save/load and concede).

## Top remaining rules gaps

From `gap_rank.py` on the final head (one family per regex; "sole" = non-FULL cards whose every
unsupported line is in that family, an upper bound). The script lived in this session's scratchpad
and is **gone** with the container; rebuild it if needed (it is ~300 lines: load Commander-legal
cards, ask `coverage` for unsupported lines, bucket them by regex families).

| # | Family | Missing | Sole | Examples |
|---|---|---|---|---|
| 1 | "If you do" / "this way" outcomes not yet read | 1,466 | 1,131 | Victimize, Windfall, Sylvan Library |
| 2 | Conditional statics ("as long as …", "if you control …") | 530 | 368 | Anger, Beastmaster Ascension, Puresteel Paladin |
| 3 | Reanimation / recursion, other wordings | 476 | 339 | Sevinne's Reclamation, Whip of Erebos, channel lands |
| 4 | Damage sized by a count, power or X | 397 | 280 | Chandra's Ignition, Descent into Avernus |
| 5 | "This turn" game-state conditions (raid, morbid, "if you created a token this turn") | 363 | 257 | Idol of Oblivion, Minas Tirith |
| 6 | Ability-word conditions (metalcraft, delirium, revolt …) on lines still refused | 314 | 232 | Mox Opal, Shifting Woodland |
| 7 | "If …, … instead" (kicked and others) | 301 | 207 | Tear Asunder, Rite of Replication |
| 8 | "Unless [player] pays" | 247 | 204 | Rhystic Study, Esper Sentinel, Mystic Remora |
| 9 | Activation-cost parts the cost grammar doesn't read | 239 | 160 | War Room, Grim Hireling, Devoted Druid |
| 10 | Face-down, other wordings (exile face down, look at it) | 219 | 158 | Ugin the Ineffable, Scroll Rack |
| 11 | Tutors, other wordings (X-sized, wishes) | 198 | 148 | Green Sun's Zenith, Wishclaw Talisman |
| 12 | Cost changers ("cost {N} less/more", chosen type) | 241 | 146 | Urza's Incubator, Defense Grid |
| 13 | Free casts, other wordings | 246 | 145 | Urza Lord High Artificer, Tibalt's Trickery |
| 14 | Saga chapters with grants/transform/modes | 169 | 145 | Urza's Saga, Fable of the Mirror-Breaker |
| 15 | Look at top N and distribute | 186 | 143 | Expressive Iteration, Gonti |
| 16 | Token copies, other wordings / populate | 206 | 141 | Helm of the Host, Second Harvest |
| 17 | Attached-permanent events, other wordings | 184 | 136 | Wild Growth, Curse of Opulence |
| 18 | "Attach it to target creature" on entry (Equipment/Aura) | 185 | 134 | Embercleave, Hammer of Nazahn |
| 19 | Control changes, other durations | 161 | 116 | Treasure Nabber, Seize the Spotlight |
| 20 | Transform / meld / convert | 233 | 113 | Westvale Abbey, Growing Rites of Itlimoc |
| 21 | "Can't be countered / sacrificed / targeted" restrictions | 159 | 112 | Veil of Summer, Destiny Spinner |
| 22 | Self cost reduction ("costs {X} less for each …") | 153 | 109 | Blasphemous Act, Ghalta |
| 23 | Alternative costs ("rather than pay": Force of Will) | 155 | 107 | Force of Will, Snuff Out |
| 24 | Copy keywords (myriad, encore, squad, casualty, replicate, offspring) | 150 | 107 | Coruscation Mage |
| 25 | Player counters, other wordings | 125 | 105 | Guide of Souls, Skrelv's Hive |

## Known shipped limitations and open items

Still manual on purpose (each has its reason in code, mostly `coverage.REFUSED` or module docstrings):

- **Reflexive triggers reading the sacrificed object** ("When you do, … that creature's power":
  Surtland Flinger, Heart-Piercer Manticore): needs the sacrificed object's LKI threaded into the
  reflexive body.
- **Black Vise / The Rack**: "the chosen player's upkeep" needs the remembered choice as a player id
  (stored only as a display name).
- **Chosen type / chosen name selectors** during resolution (Bloodline Bidding, From the Rubble,
  Urza's Incubator), Sylvan Library (drawn-this-turn tracking), Lim-Dûl's Vault, Djinn of Wishes
  (playing a land mid-resolution), total-MV-limited non-target choices (Protean Hulk).
- **Copies**: cast-a-copy (707.12), "each other object it could target" (Zada), Garth One-Eye /
  Magar, linked abilities (707.7), melded and reversible sources, Double Vision.
- **Mana**: restricted mana added to the pool by spells (Geosurge, Karn), "that spell can't be
  countered" riders, restrictions on costs rather than spells, Mana Drain, snow mana and mana-source
  conditions.
- **Replacements**: life-loss replacements (no choke point yet), paying life as a replaceable event
  (119.4, unverified), Vorinclex-style "if you would put counters", count-level draw replacements
  (Alms Collector), Kalitas against another "exile instead", Level/Class/Room lines, one-shot
  redirection (Gideon's Sacrifice), radiance, X-target grants.
- **Modal**: "choose X/up to X", "choose two at random", modes with "you may", target groups or
  divisions, restriction lines after modes.
- **Keywords**: airbend, waterbend, non-mana morph costs, the dungeon Arena room (goad on a chosen
  creature), attack costs (Ghostly Prison) are not weighed by goad.
- **Battles**: a defeated Siege is cast transformed by hand; cost increases on activated abilities
  with no mana in their cost are not applied.
- **Triggers sized by X** (Fblthp-style): triggers don't receive the X the permanent was cast with.
- **Ability-word flavor prefixes**: the deny list of rules-bearing "Name —" prefixes in
  `oracle.word_prefix` is maintained by hand; add new mechanics to it.

Known approximations (correct in normal play; listed so nobody is surprised):

- **Face-down masking** is a text substitution by card name: in logs, every same-named public card
  (e.g. basic lands when a Mountain is face down) shows as "a face-down card". It over-masks; it does
  not leak. `rules_view.stats` skips face-down creatures, so even their controller doesn't see a
  pumped face-down creature's real P/T (cosmetic).
- **Kept mana** (106.4) is spent last automatically instead of asking the player.
- **Firebending** keeps as much {R} as it added, as if the player spent other red first.
- **Ring-bearer** after control changes hands and back within one resolution stays the bearer
  (checked at SBA time; 701.54a says it stops).
- **Stun counters** don't stop paying {Q} untap costs.
- **Palace Jailer** whose controller left the game: the exiled card stays exiled (rule not settled).
- **Mid-resolution free cast** when the resolving ability's controller leaves during the cast is only
  tested for the caster conceding.
- **Cards cast by hand** (moved to the stack manually): every "mana was spent" condition is false.
- **"Entered this turn"** freezes only types and subtypes as the permanent entered.
- **Total/different-name target limits** are checked when targets are chosen, not again on
  resolution (no ruling found either way).
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
- **Hidden information must never leak.**
- Work reusable gaps ranked by data. **Do not chase cards one by one.**
- An independent rules review comes before merging risky subsystems.
- 3D polish, plane themes, decorative toys, the command palette and final screenshots are
  **late-stage work**.
- Security: validate WebSocket messages and file imports, no path traversal, no telemetry, no need
  for Internet access during games.

## Next session start instructions

1. Start a **fresh session** from `main`. If PR #10 is still open, check its CI and merge it first.
2. Set up the backend: `cd backend && python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'
   'mypy==2.3.1' pytest-xdist`. For coverage, build the card DB (`scripts/update-cards.sh --images
   none`).
3. Read this file, `docs/ARCHITECTURE.md`, `docs/RULES_COVERAGE.md`, `docs/AUTOMATION_UX.md`.
4. Rebuild a gap ranking and pick from the table above. The biggest reusable families are the
   remaining "if you do / this way" outcomes, conditional statics, "unless pays", and "this turn"
   conditions.
5. Workflow that worked this session: a queue of independent families, one agent each in its own
   worktree with marked code blocks (`# -- <area> (wave N) --`) to keep merges mechanical; the lead
   merges each branch as it lands (ruff, mypy, full pytest before every push); one independent
   reviewer at the end that fixes what it finds.
6. **Push every agent branch you intend to keep** (or merge it into the PR branch) before a session
   can end.

## Usage control

- Fresh session per major PR; Opus for implementation of risky subsystems and for review.
- Narrow agent scopes; don't reread the whole repository or the Comprehensive Rules.
- Targeted tests while implementing; full verification at integration checkpoints. The full
  backend suite takes about 3 minutes with `-n 8` locally.

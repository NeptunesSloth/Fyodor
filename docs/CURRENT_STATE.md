# Current state — handoff for the next session

Written 2026-10-03 at the end of the session that built PR #11 (wave 4 of the rules engine). Every
fact here was checked against git, CI and local runs at that time. Where something was not
verified, the text says so.

## Current repository state

| | |
|---|---|
| Repository | `NeptunesSloth/Fyodor` |
| `main` | Has PRs #7–#10 (review 5 fixes, waves 1–3 of the rules engine). |
| Open PR | **#11** (`claude/dazzling-heisenberg-h6juen`): wave 4, below. Marked ready for review at the end of this session; merge it when CI is green. |
| Other branches | `claude/wip-wave4a` … `claude/wip-wave4m`, `claude/wip-wave4r`: the agent branches of this session, all merged into #11. Safe to delete once #11 is merged. `claude/sharp-curie-nOXLF` is an unrelated old branch; ignore it. |
| Agent worktrees | Local to this session's container and gone with it. Everything worth keeping is merged into PR #11. |

## Last known test status (PR #11 head)

| Check | Status |
|---|---|
| Backend pytest (full, `-n 8` with pytest-xdist) | Passed locally on the final head: all 3,579 tests (exit 0), including the fixes for the three Codex review findings. |
| ruff (`backend`) / mypy (`app tools`, 178 files) | Passed locally. |
| Frontend tsc / vitest (61) | Passed locally after wave 4I (the only wave that touched the frontend). |
| Playwright (17 spec files) | Passed in GitHub CI on `551e636` (all waves merged, before the review merge). Not run locally this session. |
| GitHub CI | Green on `551e636`. Check the final head (review merge and this file) before merging. |

`test_rules_statics.py::test_full_board_derive_is_fast` (a 500 ms timing limit) can fail when the
machine is heavily loaded, for example with several agents running full suites at once. Alone it
takes about 45 ms.

## Current Commander coverage

Data: Scryfall snapshot 2026-09-30, Comprehensive Rules 2026-09-25.

| | Before PR #8 | After PR #10 (`main`) | Now (PR #11 head) |
|---|---|---|---|
| Commander-legal cards | 32,068 | 32,068 | 32,068 |
| FULL | 12,643 (39.4%) | 15,515 (48.4%) | **16,927 (52.8%)** |
| PARTIAL | 19,425 | 16,553 | 15,141 |
| Possible commanders FULL (of 3,501) | 677 | 956 | **1,113** |

To reproduce: build the card database with `scripts/update-cards.sh --images none`, then from
`backend/` run `python -m tools.commander_coverage --db ../data/cards.sqlite --out <dir>` (use
`--out` to keep the committed `data/reports` untouched; they were **not** regenerated).

## What PR #11 (wave 4) added

Everything below is in the engine with real-card tests (replay and save/load checked). Each wave has
its own test file, `backend/tests/test_rules_wave4<x>_*.py`, and its code is marked `wave 4X` so
`grep` finds it. Shared files were changed only in small marked blocks; new logic lives in new
modules where possible.

- **Gap ranking tool** (`backend/tools/gap_rank.py`, now committed): buckets every unsupported line
  into regex families and counts sole blockers. `--family <name>` lists a family's cards.
- **4A "If you do" / "this way"** (`this_way.py`, `reveal_lands.py`): counts and conditions on what an
  earlier instruction actually did ("for each creature destroyed this way", Windfall's greatest
  number discarded, "If a creature is destroyed this way"), per-controller token batches
  (Terastodon), counterspells with their own destination (Memory Lapse), the Snarl lands, discarding a
  hand, "tap any number of …", and "You may A. If you do, B" where B has its own target.
- **4B conditional statics** (`static_conditions.py`): "as long as …" on the attached object,
  devotion (the Theros gods, with layer 4 type removal), counters on the source, monstrous/renowned,
  life against the starting total, opponents' states; statics that work from the graveyard (Anger,
  Wonder, Brawn); "You may cast this card from your graveyard as long as …"; "If you control two or
  more other lands, this land enters tapped".
- **4C "unless [player] pays"** (`unless_pays.py`): Rhystic Study, Mystic Remora, Esper Sentinel;
  costs sized at resolution, energy, counterspell riders ("If that spell is countered this way, exile
  it instead", "If they do"), "first <kind> spell each turn" cast triggers.
- **4D "this turn" game state** (`history.py`, `TurnLog`): a per-turn history (casts, tokens, deaths,
  life gained/lost, attackers, discards, sacrifices, damage, crimes, resolution counts) behind
  intervening-if triggers, "Activate only if", statics and values. Raid, morbid, Idol of Oblivion,
  Minas Tirith, "the second time this ability has resolved this turn". Also reads "…, if C, you may
  X" triggers (Land Tax).
- **4E damage sized by a count** (`sized_damage.py`): amounts per recipient player (Price of
  Progress, Heartless Hidetsugu), creatures dealing damage to themselves (Justice Strike), Chandra's
  Ignition as one damage event, counters on the subject with last known information.
- **4F ability words**: ability words stripped on mana abilities with "Activate only if" (Mox
  Opal), digits in trigger prefixes (descend), "corrupted"; channel ("Discard this card" as a cost
  from hand), exhaust, converge.
- **4G kicked / "instead"** (`kicked_instead.py`): targets that depend on the kicker (Tear Asunder,
  Jilt), short "instead" restatements (Burst Lightning, Rite of Replication), kicked add-ons, mana
  abilities with "add … instead", planeswalker types in selectors.
- **4H activation-cost parts**: removing or putting counters, X-sized parts (sacrifice X, tap X,
  exile X from graveyard), discard your hand, mill, exile from library, half your life, War Room's
  color-identity life, collect evidence, forage, compound and either-or sacrifices, exert, boast.
- **4I cost changers and alternative costs** (`cost_changes.py`, `alt_costs.py`): the 601.2f total
  (one alternative cost, then additions, then reductions with the 118.7 floors), locked once payment
  starts; "This ability costs {N} less" (the Kamigawa channel lands), self reductions (Blasphemous
  Act, Ghalta), permanents changing other spells' costs (Defense Grid, Urza's Incubator, Thalia),
  alternative costs (Force of Will, Snuff Out, Daze, Jodah) with a frontend menu entry, Defilers.
- **4J leftovers** (`chosen.py`, `hand_size.py`, `land_plays.py`, `graveyard_exile.py`): reflexive
  "When you do" triggers reading the sacrificed object; "the chosen player" stored as a player id
  (Black Vise, The Rack); chosen creature type / color selectors (Patchwork Banner, Plague
  Engineer); the cast X for a permanent's own enters trigger (fixed Meathook Massacre and Gadwick,
  which were FULL with X = 0; Fblthp); no maximum hand size, additional land plays, graveyard exile
  (Bojuka Bog), Mana Vault, Smothering Tithe.
- **4K effects sized by X or a count** (`x_spells.py`): Craterhoof-style pumps fixed on resolution,
  "pay X life" additional costs (Toxic Deluge), "X target …", X/X tokens, enters with X counters,
  spells that shuffle themselves (the Zeniths), one X shared by both halves of a sentence.
- **4L attached permanents** (`attached_types.py`, `attached_mana.py`, `attached_players.py`):
  granted protection/ward/toxic, "loses all abilities" with type/color/base P/T setting, extra mana
  from enchanted lands (Wild Growth), sharing Curses (Curse of Opulence), "can't attack you",
  regenerate enchanted creature; fixed `Equipped creature has "{T}: …"` being read as an activated
  ability.
- **4M recursion and tutors** (`recursion.py`): spells that move themselves, Myriad Landscape's
  shared land type, and/or searches, sized "up to X" searches, mana value comparisons, Fabled
  Passage's untap, "return all A and B cards", effects on what was just returned.
- **4R independent review** fixed: counter-unless and ward offering PAY to a player who can't pay
  (118.3); hand casts missing from "first spell each turn"; Snarl lands leaking an empty match by
  skipping the question; mana abilities ignoring cost increases (now left to the player); Birgi's
  boast permission never matching the real card's name; a log note when a spell cast by hand reads
  X, converge or kicks as 0; cost lock-in missing on cycling and transmute; a layer cache-key
  slowdown. It read ~80 promoted cards' parsed definitions and demoted none.

## Top remaining rules gaps

From `python -m tools.gap_rank --db ../data/cards.sqlite --top 25` on the final head. "Sole" = non-FULL
cards whose every unsupported line is in that family (an upper bound). A line goes to the first family
whose regex matches; `static_other`, `trigger_other` and `activated_other` are catch-alls, so look
inside them with `--family` before choosing work.

| # | Family | Missing | Sole | Examples |
|---|---|---|---|---|
| 1 | static_other (catch-all) | 5,813 | 2,805 | Chaos Warp, Arcane Denial, Swan Song |
| 2 | trigger_other (catch-all) | 3,108 | 2,084 | The One Ring, Mystic Sanctuary, Orcish Bowmasters |
| 3 | activated_other (catch-all) | 1,245 | 918 | Path of Ancestry, Command Beacon, The Great Henge |
| 4 | "If you do" / "this way", still unread | 1,295 | 893 | Mox Diamond, Braids, Living Death |
| 5 | Counters, other wordings | 1,238 | 745 | Inspiring Call, The Ozolith, Spark Double |
| 6 | "This turn" game state, still unread | 554 | 391 | Sylvan Library, Veil of Summer, Combat Celebrant |
| 7 | Attached-permanent lines, other wordings | 516 | 374 | The Reaver Cleaver, Blade of Selves |
| 8 | X values, other wordings | 631 | 351 | Torment of Hailfire, Sphere of Safety |
| 9 | Damage sized, other wordings | 456 | 298 | Descent into Avernus, Myr Battlesphere |
| 10 | Conditional statics, other wordings | 450 | 254 | Promise of Loyalty, Conqueror's Flail |
| 11 | Ability-word lines | 392 | 240 | Tireless Provisioner, Puresteel Paladin |
| 12 | "Instead", other wordings | 393 | 230 | Academy Manufactor, Bloodletter of Aclazotz, Blightsteel Colossus |
| 13 | Reanimation, other wordings | 380 | 181 | Sevinne's Reclamation, Agadeem's Awakening |
| 14 | Activation-cost parts | 246 | 161 | Arena of Glory, Walking Ballista |
| 15 | Free casts, other wordings | 250 | 126 | Mystic Forge, Tibalt's Trickery, Urza |
| 16 | Tutors, other wordings | 183 | 109 | Scapeshift, Defense of the Heart |
| 17 | "Unless pays", other wordings | 123 | 99 | Volatile Stormdrake, Unsettled Mariner |
| 18 | Transform / meld | 243 | 86 | Westvale Abbey, Bloodline Keeper |
| 19 | Token copies / populate | 132 | 79 | Second Harvest, Mechanized Production |
| 20 | Saga chapters | 163 | 76 | There and Back Again |
| 21 | Control changes, other durations | 109 | 72 | Treasure Nabber, Seize the Spotlight |
| 22 | Chosen type, other uses | 137 | 70 | Roaming Throne, Kindred Discovery |
| 23 | Cost changers, other wordings | 124 | 60 | Inquisitive Glimmer, Thryx |
| 24 | "Attach it to target creature" on entry | 74 | 57 | Embercleave, Mithril Coat |
| 25 | Look at top N | 88 | 56 | Herald's Horn, Loot |

Reusable ideas seen during wave 4 but not done: a life-loss replacement choke point (Bloodletter,
Plague Drone), a zone-move replacement that can pause for the 616.1 choice (Blightsteel, Progenitus
against Rest in Peace), "When you cast this spell" triggers (Hydroid Krasis, Genesis Hydra), snow mana
(needs the mana pool to record each mana's source), voting, granted triggered abilities on other
permanents (Tabernacle, Kataki), simultaneous searches and edicts by several players (701.23i, 101.4).

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
  restrictions on costs rather than spells, Mana Drain, snow mana `{S}`, exhaust mana abilities.
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
- **Keywords**: airbend, waterbend, non-mana morph costs, warp, max speed, the dungeon Arena room,
  attack costs not weighed by goad, annihilator and myriad as granted keywords, ward Auras
  (702.16n), land-type-setting Auras (305.7).
- **X**: Torment of Hailfire (repeated per-opponent choices), "investigate X times", "up to X target"
  in triggers, delayed triggers (107.3n) don't receive X.
- **Battles**: a defeated Siege is cast transformed by hand.
- **Ability-word flavor prefixes**: the deny list of rules-bearing "Name —" prefixes in
  `oracle.word_prefix` is maintained by hand; add new mechanics to it.

Known approximations (correct in normal play; listed so nobody is surprised):

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

1. Start a **fresh session** from `main`. If PR #11 is still open, check its CI and merge it first.
2. Set up the backend: `cd backend && python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'
   'mypy==2.3.1' pytest-xdist`. For coverage and gap ranking, build the card DB
   (`scripts/update-cards.sh --images none`). For frontend checks, `cd frontend && npm ci`.
3. Read this file, `docs/ARCHITECTURE.md`, `docs/RULES_COVERAGE.md`, `docs/AUTOMATION_UX.md`.
4. Run `python -m tools.gap_rank --db ../data/cards.sqlite` and pick from it. The named families
   are now mostly long tails; the biggest remaining work is inside the catch-all families
   (`--family static_other --family trigger_other --limit 200`): split them into new regex families
   in `gap_rank.FAMILIES` first, then rank again. Also consider the reusable ideas listed under the
   gap table.
5. Workflow that worked: one agent per family in its own worktree, a shared brief file, code in
   marked blocks (`# -- <area> (wave N) --`), the lead merges each branch as it lands (ruff, mypy,
   full pytest before every push), then one independent reviewer that fixes what it finds.
   Agents in worktrees must run with `PYTHONPATH=$PWD` (the venv is an editable install of the main
   checkout).
6. Usage limits stopped agents twice this session. When that happens, commit each agent worktree's
   uncommitted work as WIP, push it to `claude/wip-*`, and resume the agent with `SendMessage` after the
   reset. Add `.claude/worktrees/` to `.git/info/exclude` so the stop hook doesn't flag agent
   worktrees as untracked files.

## Usage control

- Fresh session per major PR; Opus for implementation of risky subsystems and for review.
- Narrow agent scopes; don't reread the whole repository or the Comprehensive Rules.
- Targeted tests while implementing; full verification at integration checkpoints. The full
  backend suite takes about 3–4 minutes with `-n 8` locally.
- Four parallel agents each running full suites load the machine enough to trip the timing test;
  rerun it alone before treating it as a regression.

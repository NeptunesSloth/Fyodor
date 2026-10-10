# Automation inventory: missing engine capabilities, 2026-10-05

This replaces "sweep the next regex family" planning with a capability plan. Measured on
`claude/beautiful-ramanujan-l9pev4` at `db89621` (Scryfall snapshot 2026-10-03, CR 2026-09-25).
No engine code changed. The numbers come from `backend/tools/inventory.py` plus two scratch analyses
described in [Method](#method).

## 1. Counts

```bash
cd backend && python -m tools.inventory --db ../data/cards.sqlite --out /tmp/inventory.json -j 3
```

| | |
|---|---|
| Commander-legal cards | 32,068 |
| **FULL** | **23,466 (73.2%)** |
| PARTIAL | 8,602 (no REVIEW or MANUAL cards at this head) |
| Possible commanders | 3,501; **1,906 FULL (54.4%)** |
| Ability lines (text, keyword and mana lines over all faces) | 61,704 |
| Lines automated | 50,318 (81.55%) |
| Lines the grammar classifies (a definition exists) but doesn't automate | 572 (0.93%) |
| Lines with no definition | 10,814 (17.53%) |
| **Oracle-text classification rate** (automated + classified) | **82.47%** |
| "Collateral" spell lines (automated alone, held back only by another line of the same spell) | 554 |

Non-FULL cards by number of **blocking** lines (collateral lines not counted): 1 line: **6,863** ·
2: 1,295 · 3: 307 · 4: 107 · 5: 26 · 6: 4. So 80% of the non-FULL cards are one line away from FULL.

### Single-blocker cards by `gap_rank` family (every blocking line in one family; sole commanders in brackets)

static_other 1,362 (140) · trigger_other 1,000 (253) · if_you_do 732 (162) · counters 392 (108) ·
activated_other 374 (58) · this_turn_state 320 (58) · x_value 284 (49) · attached_events 253 (10) ·
damage_sized 244 (33) · instead 228 (44) · as_long_as_static 222 (31) · ability_word 170 (28) ·
reanimation 150 (21) · free_cast 124 (42) · tutor 86 (4) · activation_cost 83 (28) ·
cost_self_reduction 83 (7) · unless_pays 80 (3) · control_change 66 (9) · death_trigger 65 (20) ·
cost_alt 65 (14) · cost_changer 63 (16) · chosen_type 61 (7) · enter_as_copy_other 52 (14) ·
token_copy 47 (13) · saga 46 (2) · look_top 36 (5) · cast_restriction 35 (4) · kicked_instead 32 (1) ·
transform 31 (8) · player_counters 22 · cant_restrictions 20 · attack_restriction 20 · banding 20 ·
attach_on_entry 19 · battle 18 · sneak 17 · copy_keywords 15 · cumulative upkeep 15 · face_down 14 · … (7,113 in all).

### Multi-blocker family combinations (top 30)

| Families | Cards | | Families | Cards |
|---|---|---|---|---|
| static_other + trigger_other | 134 | | static_other + this_turn_state | 17 |
| if_you_do + static_other | 49 | | counters + static_other + trigger_other | 16 |
| if_you_do + transform | 35 | | if_you_do + trigger_other | 15 |
| chosen_type + static_other | 34 | | as_long_as_static + static_other | 15 |
| ability_word + start your engines! | 32 | | death_trigger + static_other | 15 |
| instead + static_other | 29 | | saddle + trigger_other | 15 |
| counters + static_other | 27 | | activated_other + trigger_other | 15 |
| reanimation + static_other | 26 | | cost_changer + static_other | 13 |
| activated_other + static_other | 25 | | as_long_as_static + trigger_other | 13 |
| static_other + x_value | 25 | | counters + if_you_do | 12 |
| damage_sized + static_other | 24 | | attached_events + static_other | 11 |
| as_long_as_static + soulbond | 24 | | trigger_other + x_value | 11 |
| free_cast + static_other | 18 | | counters + trigger_other | 11 |
| kicker + kicked_instead | 18 | | counters + x_value | 10 |
| | | | cleave + static_other | 10 |
| | | | station + static_other + trigger_other | 9 |

Most combinations are one wording split over two lines: a modal trigger header plus its bullets
(static_other + trigger_other), the werewolf "if no spells were cast last turn, transform" pair
(if_you_do + transform), the speed mechanic (ability_word "Max speed" + "Start your engines!"),
soulbond pairs, kicker plus its "if kicked" line.

## Method

1. **Inventory** (`tools/inventory.py`, committed): per card the level, commander flag, line counts and
   *every* unsupported line with its `gap_rank` family, its refusal reason (`coverage.refusal`),
   whether the grammar produced a definition ("parsed") and whether it is collateral.
2. **Culprit sentence** (scratch): for each of the 10,302 blocking text lines, the line's sentences are
   fed to coverage as prefixes of a test card until one fails; that sentence is the culprit (3,388
   lines have several sentences; 1,530 of them parse when cut out, i.e. they fail only in their card's
   context and keep the whole line).
3. **Capability clustering** (scratch): about 850 blocking lines were read by hand (two random samples
   of 260 and 240 lines weighted by family size, then 40–70 per large cluster); from them an ordered
   rule list maps each culprit sentence to the engine capability it needs, bucket A (engine), B
   (parser / script over existing machinery) or C (keep manual). Then targeted probes (one regex per
   capability) measured each item in section 3.

"**Sole**" = non-FULL cards whose every blocking culprit falls in the cluster (an *upper bound*: a
sentence can need two capabilities). "**Near**" = cards where the cluster covers all blocking lines
but one ("would become sole-blocker" once one other fix lands). Clusters overlap across probes; don't
add the rows.

## 2. Capability clusters (culprit-sentence clustering, all 8,602 non-FULL cards)

| Cluster | Bucket | Lines | Sole | Sole cmdrs | Near (2 clusters) | Examples |
|---|---|---|---|---|---|---|
| Event history beyond TurnLog | A | 904 | 676 | 155 | 154 | Sevinne's Reclamation, Veil of Summer, Conduit of Worlds |
| Casting / cost permissions and riders | A | 603 | 398 | 84 | 172 | Bolas's Citadel, The Reality Chip, Muldrotha |
| Linked objects / resolution memory | A | 535 | 376 | 54 | 119 | Tibalt's Trickery, Eldritch Evolution, Expressive Iteration |
| Event replacements and prevention | A | 276 | 209 | 25 | 54 | Academy Manufactor, Bloodletter of Aclazotz, Aven Mindcensor |
| Per-player iteration and player choices | A | 210 | 170 | 10 | 32 | Plaguecrafter, Liliana Dreadhorde General, Priest of Forgotten Gods |
| Dynamic values (greatest, totals, colors) | A | 178 | 129 | 28 | 34 | Saw in Half, Soul Shatter, Peer into the Abyss |
| Modal forms (one mode's wording) | B* | 735 | 126 | 0 | 132 | Akroma's Will, Rakdos Charm, Archdruid's Charm |
| Chosen value used as a filter | A | 212 | 125 | 11 | 33 | Roaming Throne, Utopia Sprawl, Cloud Key |
| Delayed triggers / later-turn durations | A | 155 | 122 | 25 | 25 | Arcane Denial, Pact of Negation, Teferi Time Raveler |
| Choose a card name | A | 149 | 109 | 9 | 11 | Demonic Consultation, Phyrexian Revoker, Pithing Needle |
| Zone-change replacements, regeneration | A | 128 | 101 | 16 | 20 | Whip of Erebos, Blightsteel Colossus, Nexus of Fate |
| Abilities on the stack as objects | A | 98 | 84 | 13 | 12 | Thousand-Year Storm, Illusionist's Bracers, Kira |
| Combat structure | A | 99 | 77 | 14 | 17 | Nowhere to Run, Echoing Assault, Detection Tower |
| Cost prohibitions / mana-spending permissions | A | 85 | 61 | 18 | 22 | Chromatic Orrery, Drana and Linvala, Yasharn |
| Repeat / "until" loops | A | 73 | 60 | 13 | 12 | Etali Primal Conqueror, Ad Nauseam, Cultivator Colossus |
| Mana abilities beyond tap-for-mana | A | 80 | 50 | 9 | 23 | Food Chain, Urza's Workshop, Kozilek's Unsealing |
| Game-result / life prohibitions | A | 60 | 42 | 5 | 15 | Teferi's Protection, Angel's Grace, Everybody Lives! |
| Type setting, group animation (layer 4) | A | 53 | 41 | 11 | 9 | Blood Moon, Starfield of Nyx, Spark Double |
| Counter prohibitions / replacements | A | 59 | 40 | 7 | 14 | Innkeeper's Talent, Vorinclex, Solemnity |
| Color setting (layer 5) | A | 32 | 29 | 3 | 3 | Painter's Servant, Kruphix, Horizon Stone |
| Zone / casting-source prohibitions | A | 25 | 17 | 4 | 7 | Grafdigger's Cage, Ashiok Dream Render, Soulless Jailer |
| Group "lose all abilities" (layer 6) | A | 10 | 7 | 0 | 3 | Humility, Dress Down, Poppet Stitcher |
| Other static / spell wordings | B | 1,317 | 878 | 90 | 359 | Deflecting Swat, Commander's Plate, Birgi |
| Trigger events not read | B | 1,124 | 755 | 197 | 301 | Syr Konrad, Kutzil, Mangara the Diplomat |
| Sized amounts / value grammar | B | 820 | 647 | 113 | 143 | Valakut Awakening, Torment of Hailfire, Shared Animosity |
| Counter wordings | B | 844 | 628 | 156 | 138 | Forgotten Ancient, Incubation Druid, Midnight Clock |
| Conditions / ability words | B | 574 | 437 | 61 | 119 | Chaos Warp, Tireless Provisioner, Guardian Project |
| Activated abilities | B | 511 | 388 | 61 | 94 | Path of Ancestry, Lion's Eye Diamond, Talon Gates |
| Conditional sequencing ("if you do") | B | 240 | 188 | 48 | 47 | Springheart Nantuko, Brudiclad, Y'shtola Rhul |
| Keyword mechanics | B | 491 | 121 | 14 | 295 | The Eternity Elevator (station), Adagia, Junk Winder |
| Attractions, stickers, Un-cards | C | 114 | 78 | 5 | 11 | "Lifetime" Pass Holder, _____ Goblin |
| Banding | C | 50 | 44 | 1 | 3 | Tolaria, Baton of Morale, Soraya |
| Outside the game | C | 21 | 17 | 0 | 4 | Karn the Great Creator, Spawnsire of Ulamog |
| Draft-matters text | C | 45 | 15 | 0 | 12 | Canal Dredger, Paliano, Deal Broker |
| Secret / random choices | C | 16 | 12 | 3 | 4 | Wheel of Misfortune, Prisoner's Dilemma |
| Text changing (layer 3) | C | 14 | 12 | 0 | 1 | Exchange of Words, Artificial Evolution |
| Directions / nearest opponent | C | 7 | 5 | 2 | 0 | Aminatou, Mystic Barrier, Pramikon |
| Companion | C | 9 | 3 | 3 | 6 | Lutri, Keruga, Zirda |

*Modal spells are carried out already (700.2, `modal_abilities`, `SUPPORTED_MODAL_*`); Rakdos Charm and
Archdruid's Charm fail on one mode's wording ("exile target player's graveyard", "each creature deals 1
damage to its controller"), so the bullets are collateral of one mode. An inventory refinement worth
doing: test each mode alone (the culprit pass cannot, bullets don't stand alone).

### Targeted probes (one wording group each; sole / near / sole commanders)

| Probe | Sole | Near | Cmdr | | Probe | Sole | Near | Cmdr |
|---|---|---|---|---|---|---|---|---|
| "where X is" / "equal to the number" | 456 | 90 | 107 | | prevention shields ("prevent the next N") | 98 | 18 | 4 |
| "… this way" (resolution memory) | 343 | 59 | 52 | | mana spent ("{S}/colors/amount spent") | 69 | 13 | 12 |
| exiled with / the exiled card | 169 | 90 | 27 | | "whenever you attack" / attacks a player | 59 | 19 | 36 |
| copies with exceptions / "becomes a copy" | 108 | 16 | 38 | | dice result tables, "whenever you roll" | 56 | 7 | 6 |
| delayed "next end step / next upkeep" | 101 | 11 | 20 | | "choose a card name" | 55 | 5 | 3 |
| per-player iteration | 100 | 16 | 4 | | costs less/more "if it targets" | 52 | 1 | 1 |
| repeat / "until" loops | 99 | 14 | 21 | | regeneration wordings | 43 | 3 | 3 |
| "until ~ leaves" / "for as long as" | 86 | 21 | 13 | | "until your next turn" | 39 | 14 | 9 |
| cost permissions (spend as though, life for mana) | 84 | 21 | 21 | | static grants to cards in other zones | 36 | 4 | 17 |
| animate a group (layer 4 + 7b) | 79 | 12 | 5 | | speed ("Start your engines!", max speed) | 35 | 3 | 5 |
| becomes target / counter an ability | 30 + 60 | 11 | 14 | | "as though it had flash if …" | 31 | 8 | 1 |
| werewolves: "spells cast last turn" | 30 | 1 | 0 | | cast provenance ("wasn't cast", "cast from …") | 31 | 13 | 11 |
| soulbond | 27 | 0 | 1 | | gift ("if the gift was promised") | 26 | 1 | 0 |
| exploit | 24 | 0 | 3 | | first time each turn | 19 | 1 | 7 |

## 3. The specific systems asked about

| System | Exists today | Missing | Cards (sole / near) |
|---|---|---|---|
| **Blood Moon** (Magus of the Moon, Harbinger of the Seas, Zhao, Celestial Dawn's land half) | `type_statics.py` adds land types (Urborg, Yavimaya, Dryad) in layer 4 with 613.8 re-finding of subjects; `attached_types` sets an *enchanted* land's types. | A group static that **sets** a basic land type (305.7: the land loses its other land types and every ability from its rules text, keeps the intrinsic mana ability of the new type); "nonbasic" selector; dependency with Urborg (613.8a). `with_gained_mana` already notes SET types are not read. | 5 / 1 (+ Melting "no longer snow") |
| **Humility / Dress Down / Overwhelming Splendor** | Resolved effects "lose all abilities" (layer 6, `_wipe_key`) and Aura/Equipment statics (`attached_types`, Lignify). Layer 7b static base P/T for groups exists. | A **group static** "lose all abilities" (613.1f) whose own removal must not remove itself before it applies; statics table must drop the statics of objects that lost their abilities (currently only for wipes on the object from resolved effects / its own Aura); timestamp vs dependency with Opalescence (613.8a: Opalescence's layer-4 effect changes what Humility applies to, so Humility waits). | Lose-all probe 44 / 10 (incl. one-shot "loses all abilities until end of turn" riders on triggers, ~20 of them B-level once the static exists). |
| **Opalescence / March of the Machines / Titania's Song / Starfield of Nyx / Ensoul Artifact** | `type_statics._ARE_ALSO` adds types to groups ("Artifacts you control are Foods"); 7a CDAs for the object's own P/T. | Group animation: "Each other non-Aura enchantment is a creature … and has base power and base toughness each equal to its mana value" = layer 4 + a **per-object 7b value** (mana value of each affected object). Plus 613.8 dependency with Humility. | animate-group probe 79 / 12 (overlaps "becomes an artifact creature until end of turn" activated forms) |
| **Mycosynth Lattice / Painter's Servant / Encroaching Mycosynth / Leyline of Singularity** | Maskwood Nexus's "same is true for … cards that aren't on the battlefield" path (`type_statics.MASKWOOD`), layer 5 for resolved effects and attached statics. | Layer-5 group statics ("are colorless", "are the chosen color in addition") in **all zones** (spells, cards in hand/library/graveyard: 611.3, the characteristics read by "nonblack" filters and protection); "all nonland permanents are legendary" (205.4 supertype in layer 4); "spend mana as though it were mana of any color" (cost track). | colour 29 sole; misc type statics 93 sole / 23 near |
| **Grafdigger's Cage / Soulless Jailer / Containment Priest / Ashiok Dream Render / Experimental Frenzy** | Nothing for "can't enter"; `cast_limits.py` / `permissions.py` restrict casting by timing and count; refused: "entered from your library" (provenance not recorded). | A **prohibition layer (614.17)**: "X can't enter the battlefield from Z" checked at every move to the battlefield, "can't cast spells from Z", "can't search" ; and **object provenance**: was it cast, from which zone was it cast / did it enter (`wasn't cast` is a replacement 614.1 for Containment Priest). | zone/cast prohibitions 29 / 10 sole/near; provenance 31 / 13 |
| **Solemnity / Tatterkite / Melira's Keepers; Vorinclex, Pir, Innkeeper's Talent, Loading Zone** | Counter primitives and counter triggers; no choke point that lets something forbid or modify "put counters". | One **counter-placement choke point** (122.6 events): prohibitions (614.17: "can't have counters put on it", players can't get counters) and replacements ("twice that many", "that many plus one") with 616.1 ordering among several. | 12–14 sole / 1–2 near |
| **"Choose a card name"** (Pithing Needle, Phyrexian Revoker, Meddling Mage, Nevermore, Runed Halo, Cabal Therapy, Demonic Consultation) | `name_search.py` for printed names; REFUSED pattern "choose a card name". | A name prompt over the Oracle name list with 201.4 rules (split halves 709.4a, back faces 201.4d, "nonland card name" 201.4a), stored as a per-object public choice (like `chosen.py` players); selectors "with the chosen name"; then the uses: activation prohibition (602.5 / 614.17), cast prohibition, cost increase, protection from a name. | 55 sole (choose-name wordings), 94 incl. other "named" lines |
| **"Can't pay life / sacrifice"** (Yasharn, Angel of Jubilation, Karn's Sylex; Sigarda / Tajuru "can't cause you to sacrifice") | `cant_gain.py` (119.7) is the model: an event that can't happen. Costs paid in `cost_payment.py`. | A cost-legality check (601.2f/602.2: a cost that can't be paid can't be begun, 119.4) in the cost payment path, and a sacrifice-cause filter on "each player sacrifices" effects (614.17). | 7 sole / 5 near |
| **"Can't lose / win the game", "damage can't be prevented"** | `win_game.py`: "can't win" is read only from printed battlefield text; game result via `replace._win`. | A game-result prohibition read at the SBA/lose choke point (104.3, 704.5a with 614.17) incl. resolved "until end of turn" forms (Angel's Grace) and Teferi's Protection's composite. | 16 / 6 |

## 4. Ranked engine tracks (bucket A)

Expected unlock = sole upper bound × a realism factor from the samples (roughly 0.5–0.7: the rest
also needs a wording fix). Complexity S/M/L; rules risk low/med/high.

| # | Track | Sole (upper) | Expected FULL | Cx | Risk | CR | Notes |
|---|---|---|---|---|---|---|---|
| 1 | **Resolution memory & linked objects**: "… this way" objects and quantities, the sacrificed / discarded / revealed / exiled card, exiled-with across abilities, "until ~ leaves", "for as long as" | 343 + 169 + 86 (overlap) ≈ 450 | 250–300 | L | med | 406.6, 607.2a, 608.2c, 610.3, 611.2b | Builds on `this_way.py`, `exiled_with.py`, `context.py`, `delayed.py`. |
| 2 | **Event history & batched triggers**: spells cast last turn (werewolves), first time each turn, mana spent ({S}/colors/amount), cast provenance and zone entered from, "whenever you attack", batched combat damage, attacked players | ~280 across probes | 170–220 | M | med | 500.4, 603.2c, 603.4, 506.2, 510.3a, 601.2h | `history.py` / `TurnLog` / `mana_units.py`; new fields need save defaults. |
| 3 | **Casting & cost permissions**: costs "if it targets", flash "if …", "spend mana as though", "pay life rather than", optional additional costs (behold, collect evidence), static grants to cards in other zones ("cards in your graveyard have sneak/encore") | ~240 | 150–180 | M | med | 601.2b, 601.2f, 609.4b, 113.6, 702.x | `cost_changes.py`, `permissions.py`, `alt_costs.py`, `graveyard_grants.py`. |
| 4 | **Replacement & prevention completeness**: prevention shields ("next N", "next time a source of your choice"), redirection, draw/token/life/counter replacements, zone-change "instead" (Blightsteel shuffle, Dauthi), regeneration wordings, 616.1 ordering | ~300 | 160–200 | L | high | 614, 615.7, 616.1, 701.19, 122.6 | `replace*.py`, `regeneration.py`, `source_shields.py`. Wrong ordering is silent; needs the head review. |
| 5 | **Prohibitions & named cards** (614.17 "can't"): card-name choice, can't enter / cast from, counters, pay life / sacrifice, lose / win, draw / cycle / search | ~200 | 120–150 | M | med | 614.17, 201.4, 602.5, 119.4, 104.3 | New `prohibitions.py`, `card_names.py`. |
| 6 | **Layers 4–6 statics & dependencies**: type setting (305.7), group animation with per-object P/T, group lose-all, colorless / legendary / chosen-color statics in all zones, 613.8 for type and ability dependencies | ~190 | 100–130 | L | high | 305.7, 613.1d-f, 613.4b, 613.7, 613.8a-b | `layers.py`, `type_statics.py`, `attached_types.py`. Humility + Opalescence is a CR example; test every published ordering. |
| 7 | Copy effects with exceptions ("becomes a copy … except", tokens that are copies with changes, Spark Double) | 108 | 60–80 | M | med | 707.9, 707.2, 613.2 | `copying.py`; overlaps track 1. |
| 8 | Per-player iteration & player choices ("for each opponent … that player controls", each player chooses then, votes, villainous choice) | 100 + 23 | 70–90 | M | low-med | 101.4, 800.4 | `per_opponent.py`, `voting.py`, `each_may.py`. |
| 9 | Stack objects (abilities as targets, "becomes the target of", counter target activated/triggered ability, copy that ability) | 90 | 50–60 | M | med | 113.7, 115.1, 701.6a, 707.10 | `stack_interaction.py`. |
| 10 | Delayed triggers & later-turn durations ("until your next turn, whenever", "next turn's upkeep" with unread payloads) | 101 + 39 | 50–70 | S-M | low | 603.7, 611.2a | `delayed.py`; mostly payload wordings. |
| 11 | Loops and repeats ("repeat this process", "until … for each player") | 99 | 40–60 | M | med | 608.2c | `this_way` + `looking.py`. |
| 12 | Dice results tables, "whenever you roll" | 56 | 40 | S | low | 706 | `dice.py`. |
| 13 | Speed (Start your engines!, max speed) and soulbond pairing | 35 + 27 | 55 | S each | low | 702.179, 702.95 | New small modules. |
| 14 | Dynamic extremes / totals ("greatest power among", "total power", "number of colors") | 129 | 60 | M | low | 107.3, 700.x | `extremes.py`, `values.py`. |

## 5. B bucket: parser and script work over existing machinery

Each is a long tail of wordings; sweep by EDHREC rank with the culprit list, two to four wordings per
agent, every promotion reviewed.

1. Value grammar ("where X is …", "equal to the number of …", "that much"): 456 sole, 107 commanders.
2. Counter wordings (enters with counters "for each", "if …", move/remove forms): ~628.
3. Trigger events (taps, returned to hand, phases in, exploit, transforms, "is turned face up", Aura
   attached): ~755 (many small groups; `trigger_words.py`, `events.py`).
4. Conditions and ability words (gift, kicker riders, ferocious/threshold "instead", "if you control"):
   ~437.
5. Activated abilities with unread effects: ~388.
6. "If you do / when you do / otherwise" sequencing: ~188.
7. Keyword mechanics with existing machinery: kicker variants, station levels, saddle, sneak, gift,
   bargain, job select, cleave, hideaway, cumulative upkeep, exploit, spree, tiered, evoke/impending
   leftovers: 121 sole but **295 near** (they unblock other fixes).
8. Modal spells: find the failing mode (add per-mode testing to the inventory first).
9. Battles: casting a defeated Siege transformed (310.12b, 712.11a): 18 sole / 12 near; the dungeon's
   Undercity Arena room: 14 / 7.

## 6. C bucket: keep manual

| Group | Cards | Why |
|---|---|---|
| Attractions, stickers, Un-cards | ~80 | Lit-up numbers per printing aren't in the data; sticker sheets need deck building (717). |
| Banding / "bands with other" | 44 | 702.22 damage-assignment ordering by the defending player is a whole combat subsystem for ~20 cards nobody plays. |
| Outside the game (wishes, Karn) | 17 | Commander has no sideboard; "outside the game" depends on table agreement (903 / tournament rules). |
| Draft-matters text | 15 | Draft information doesn't exist in a Commander game; the cards' printed effects depend on it. |
| Secret / random-with-hidden-result choices | 12 | Need hidden-choice reveal flows; low value, leak risk. |
| Text changing (layer 3) | 12 | 612 text replacement over parsed scripts: would re-parse rewritten Oracle text at runtime. |
| Directions / nearest opponent | 5 | Seating and direction aren't modelled. |
| Companion | 3 | Deck-building restriction (702.139a), outside the game. |
| Already deliberate (CURRENT_STATE) | — | Unsettled rulings (Panharmonicon vs "create a token", copied Room door, Hellrider after leaving combat), Bolas's Citadel, Garth One-Eye, Chrome Mox, Word of Command, Lim-Dûl's Vault, Protean Hulk. (Djinn of Wishes: automated in wave 28A; it lacked only playing a land mid-resolution.) |

## 7. Six parallel implementation tracks

Ownership rule: each track owns the files listed and creates its own new modules; shared registries
(`effects.PRIMITIVES`, `coverage.SUPPORTED*`, `scripts.py` grammar hooks) get one small marked block
per track (`# -- <track> (wave 22X) --`) and only appended entries. Tests in
`tests/test_rules_wave22<x>_<area>.py`. Each track starts with a `levels.py` base dump and ends with
the diff, spot-checks 10+ gained cards, and goes to an Opus review before merge.

| Track | Scope | Owns | CR | Test plan |
|---|---|---|---|---|
| **22A Layers** | Blood Moon type setting, group lose-all (Humility, Dress Down), group animation with per-object 7b (Opalescence, March, Titania's Song), colorless/legendary/chosen-color statics in every zone, 613.8 dependencies for types and abilities | `layers.py`, `type_statics.py`, `attached_types.py`, `characteristics.py`, statics' layer-4/5 parsers in `statics.py` | 305.7, 613.1d-f, 613.4b, 613.7, 613.8 | Blood Moon + Urborg both orders; Humility + Opalescence both timestamps (CR example); Lattice + Painter's Servant protection; derive perf test |
| **22B Prohibitions & names** | 614.17 checks at move, cast, activate, counter placement, cost payment, game loss; card-name choice and "with the chosen name" selectors | new `prohibitions.py`, new `card_names.py`, `chosen.py`, `cant_gain.py`, `win_game.py`, `game_result.py`, `selectors.py` (chosen-name suffix only) | 614.17, 201.4, 709.4a, 602.5, 119.4, 104.3, 704.5a | Cage vs reanimation and tutors to battlefield; Needle on mana vs non-mana; Meddling Mage split halves; Solemnity + persist; Angel's Grace at 0 life; hidden-info test for "look at hand then name" |
| **22C Replacements & prevention** | Counter replacements (Vorinclex, Pir, Innkeeper), draw / token / life replacements, zone-change "instead" (shuffle into library, Dauthi), prevention shields and redirection, regeneration wordings, 616.1 order prompt | `replace.py`, `replacements.py`, `replace_grammar.py`, `regeneration.py`, `source_shields.py`, `mana_replace.py` | 614, 615, 616.1, 701.19, 122.6 | Two counter replacements ordered both ways; Blightsteel to graveyard from library vs battlefield; prevention shield split across simultaneous damage; Containment Priest stays with 22B |
| **22D Resolution memory & linked objects** | "this way" objects/quantities, the sacrificed/discarded/revealed card, exiled-with across abilities, "until ~ leaves" / "for as long as", copies with exceptions | `this_way.py`, `exiled_with.py`, `context.py`, `delayed.py`, `copying.py`, `pay_objects.py` | 406.6, 607.2a, 608.2c, 610.3, 611.2b, 707.9 | Skyclave Apparition token X after blink; Eldritch Evolution sacrificed MV with LKI; Twinflame + exile at end step; save/load mid-duration |
| **22E History & triggers** | TurnLog additions: spells cast last turn, first-time-each-turn, mana spent by color/amount/source, cast provenance and entered-from zone, attacked players; batched "whenever you attack" / "one or more … deal combat damage"; becomes-target triggers | `history.py`, `app/game/rules_state.py` (TurnLog fields only, with defaults), `events.py`, `triggers.py`, `trigger_words.py`, `mana_units.py` | 500.4, 603.2c, 603.4, 506.2, 510.3a, 601.2h, 115.1 | Werewolf transform with 0/2 spells last turn; Kira first-target only; old saves load; replay determinism |
| **22F Casting & costs** | Costs "if it targets", flash "if …", spend-as-though / life-for-mana permissions, optional additional costs, static grants to cards in other zones, Damping Sphere per-spell counts | `cost_changes.py`, `permissions.py`, `alt_costs.py`, `cost_payment.py`, `graveyard_grants.py`, `casting.py` (cost determination only; 22B owns the legality hook) | 601.2b, 601.2f, 113.6, 609.4b | Cost computed after targets (601.2f order); Terror of the Peaks life payment; Chromatic Orrery any-color; Ninja Teen sneak from graveyard; illegal target cancels cast and returns paid costs |

Not in this round (next): per-player iteration (track 8), stack objects (9), loops (11), dice and
speed/soulbond (12–13, small: good warm-up tasks for single agents), and the B-bucket sweeps, which
should follow each engine track that unblocks them (B "near" counts).

## Caveats

- Sole/near counts are upper bounds from regex clustering of the culprit sentence; a culprit can need
  two capabilities, and ~15% of multi-sentence lines fail only in context (whole line kept).
- `gap_rank` and `inventory` agree (FULL 23,466); single-blocker family counts differ slightly from
  `gap_rank` because `inventory` ignores collateral spell lines.
- The scratch scripts (`inv_culprit.py`, `inv_caps.py`, `inv_rx.py`) are in the planning session's
  scratchpad; promote the culprit pass into `tools/inventory.py --culprits` if it proves useful (it
  takes ~25 minutes with 3 processes on a loaded machine).

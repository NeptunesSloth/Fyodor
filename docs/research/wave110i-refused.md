# Wave 110I refused / deferred

- Sheltered Valley: replacement sacrifices others before it enters; an ETB-trigger stand-in changes timing (leaves-battlefield triggers, 614.12). Needs an "instead sacrifice, then put onto battlefield" replacement.
- Torrent of Lava: "as long as it is on the stack, each creature has {T}: prevent..." (static on the stack granting activated abilities); first line alone reads.
- Spoils of War: X fixed "as you cast this spell" with a non-X cost; only as_cast_values42 (greatest power) exists, no general foundation (7 cards share it).
- Glimpse the Cosmos: conditional graveyard cast (needs a Giant) plus exile-instead rider; escape.GY_COST has neither.
- Skyblade's Boon: activate from battlefield or graveyard; graveyard activation exists only for self-exile costs (casting.py ~5448).
- Cuombajj Witches: second target chosen by an opponent.
- Hipparion: pay-to-block restriction not modelled.
- Bioessence Hydra: "one or more loyalty counters put on planeswalkers" is one trigger per batch (603.2c); counters_put events are per object, so a proliferate over two planeswalkers would trigger twice (Hardened Scales etc. differ).
- Dodecapod: entering "with two +1/+1 counters" via the discard replacement needs an enters-with carrier on the replaced move; counters after entry would differ (614.12).
- Skyblade's Boon: "Activate only if on the battlefield or in your graveyard" needs a graveyard activation flag on a non-cost ability (casting.activate_ability only reads cost.from_graveyard).
- Phylactery Lich: "As ~ enters, put a counter on an artifact" read as an ETB trigger would let the state trigger sacrifice it first.
- Merieke Ri Berit: needs a persistent delayed trigger bound to the controlled creature (leaves/untaps); no such watch exists.
- Fasting: "you may skip your draw step instead" needs an optional-skip decision at step start (skips.py has only unconditional skips).
- Torrent of Lava, Dark Intimations, Aeon Engine, Hero of Bretagard, Aegis of the Legion, Grifter's Blade: stack-granted ability / Bolas-cast trigger / turn-order reversal / exile-from-hand batch / mentor event / equipment enters-attached choice: each a separate foundation.
- Cuombajj Witches: second target chosen by an opponent for an any-target damage; delegated_target_announcements only supports one creature target on activated abilities.
- Evershrike: Aura "attached to it" with mana value X limit after a graveyard return; two missing foundations.
- Tainted Specter: "discards a card unless they put a card from hand on top of library" (no unless-put-on-library payer).
- Heart of Bogardan / Balduvian Fallen: need cumulative-upkeep paid/unpaid events and mana spent on it; deferred.
- Curse of Inertia / Become the Pilot / Awesome Presence: attacker-chosen target, conditional unblockable, block tax not modelled.
- Shifty Doppelganger: delayed sacrifice then "return this card" (the exiled-as-cost source) not modelled.
- Etched Slith: removing a counter from an opponent (player counter kinds) not modelled.
- Arsenal Thresher: "reveal any number of other artifact cards" as it enters needs a second amplify-like entry choice (amplify.py is keyword-only); one card.
- Stardew Valley, Necrotic Plague, Curse of Leeches, Arcee: another player's choice of recipient / opponent-chosen target / attach-on-transform / counted-targets cast trigger; not built.
- Noctis / Meandering Towershell: "tapped and attacking at the beginning of the declare attackers step" needs delayed triggers at the declare attackers step (engine has none, combat.start_declare_attackers) and an after-declaration order (508.1/508.2).
- Quicksilver Fountain: three gaps (flood-counter-conditional Island static, "if all lands are Islands" condition, land chosen by the upkeep player).
- Lodestone Bauble: targets in one player's graveyard plus "that player draws" (two player roles) not modelled.
- Smelting Vat: "total mana value <= sacrificed artifact's" pick constraint not modelled. Aphetto Dredging: creature type chosen during targeting.

## Session 7: foundations built, these earlier refusals are now FULL
- Hipparion (block tax by attacker power, combat_rules.pair_tax), Fasting (optional draw-step skip, wave110i_cards.ask_skip), Smelting Vat (total_mv as a value), Lodestone Bauble (one graveyard, owner draws), Noctis (delayed trigger at declare attackers step, 507.1/508.8), Balduvian Fallen / Heart of Bogardan (cumulative upkeep paid / unpaid), Sheltered Valley (devour-style mandatory same-name sacrifice).
- Lodestone Bauble: zero targets (115.6) are allowed; that resolution goes to manual play (s9).

## Session 8
Moved to FULL: Arsenal Thresher (devour.py REV), Arcee (cast_targets110i value), Shifty Doppelganger, Evershrike, Raiding Party, Tainted Specter (wave110i_cards.py).
- Spoils of War: "an opponent's graveyard" (which opponent, multiplayer) is unsettled, and X is both cost and text-defined (107.3c).
- Torrent of Lava: abilities granted to every creature only while the spell is on the stack; no stack-presence static.
- Hero of Bretagard: needs "exiled by a spell or ability you control" as an event source, joined to a hand-exile batch.
- Stardew Valley: "another player of your choice may gain control": who decides the "may" is unsettled.
- Quicksilver Fountain: "target ... land they control of their choice": who picks the target is unsettled.
- Aphetto Dredging: when the creature type is chosen (before or after targets) is unsettled.
- Frankenstein's Monster: +2/+0 and +0/+2 counters, and "put into the graveyard instead of the battlefield", are not modelled.
- Firestorm Phoenix, Providence, False Dawn, Reflecting Mirror (X defined by the target spell's mana value), Curse of Leeches (attach on transform), Tunnel of Love: foundations missing.

## Session 9
- Curse of Leeches: "as this permanent transforms, attach it to a player" needs a decision inside the synchronous day/night flip (designations.py sync); no suspendable hook.
- Hero of Bretagard: second trigger half (a spell or ability you control exiles permanents) is a separate event kind; one ability, two triggers not modelled.
- Firestorm Phoenix: needs a per-object "can't play it" plus timed reveal on the new hand object (rider has no ref to the moved card).
- False Dawn: colored-mana replacement for a turn (no mana-type replacement foundation). Reflecting Mirror: X fixed to twice the target spell's mana value. Arcum's Whistle, Torrent of Lava, Spoils of War: unchanged (see Session 8).

## Session 10
- Done (no longer refused): Curse of Leeches (decision at the flip, before SBA), Hero of Bretagard (exiled110i event), Firestorm Phoenix, False Dawn, Reflecting Mirror, C.A.M.P. (+ Darksteel Garrison, Fortify), Tunnel of Love.
- Spoils of War: "an opponent's graveyard" in a multiplayer game has no CR rule or ruling saying which opponent (X defined as you cast); not guessed.
- Torrent of Lava: spell on the stack grants every creature an activated ability (no stack-zone static source); still a foundation, not rules-unsettled.
- Arcum's Whistle: needs "that player may pay {X}" for another player, forced attack, and an end-step "didn't attack this turn" check; foundation work.

## Session 11
- Done: Nick Fury (DFC transform said last), Arcum's Whistle (Nettling Imp machinery + optional {X} payment), Wee Champion, Goblin Airbrusher (place-a-sticker event with kind), _____ Balls of Fire, Make a _____ Splash (sticker put on itself, letters in name stickers), Wolf in _____ Clothing (reflexive, X vowels), Pin Collection (cost_cap X, free placement, equipped creature has the stickers' abilities), Steamflogger Boss (701.45a: assemble is outside the CR and no Contraption deck exists in Commander, so the replacement never applies), Ore-Rich Stalactite // Cosmium Catalyst (random craft material, free cast). False Dawn: the additional mana of triggered mana abilities (Wild Growth) is recolored at the mana-add choke point (609.4b).
- Torrent of Lava: still two foundations: a source-specific "prevent the next 1 damage ... by Torrent of Lava" shield (RulesState.prevention is per recipient, any source) and an ability granted to every creature while the spell is on the stack (layers statics are battlefield-only).
- Spoils of War: unchanged (which opponent's graveyard: no CR rule or ruling).
- Pyretic Hunter, Lurking Automaton, Cogwork Grinder, Aether Searcher: draft-matters (905.2b, 607.2e). In a Commander game nothing was drafted, so nothing is noted/removed: X would be 0 and the Searcher finds nothing. Not promoted: no official ruling text in the repo for "nothing noted"; lead decision (inert draft lines + X = 0 is the only reading).

## Session 12
- Done: Pyretic Hunter, Lurking Automaton, Cogwork Grinder (draft_only.py: X is 0, lead decision), Aether Searcher (wave110f DRAFT_NOTHING entry), Ob Nixilis of the Black Oath (designations.emblem_text_ok allows the activated emblem cost).
- Torrent of Lava: still two foundations (stack-granted ability to every creature, source-specific prevention shield); not small.
- Spoils of War: unchanged (which opponent's graveyard).
- Spinneret and Spiderling: "deals 4 or more damage" with no recipient: events.py excludes a threshold without recipient (one event, many recipients: no ruling on summing); exile_damage_choices49 is unregistered.

## Session 13 (todo_from_n leftovers)
- Acidic Dagger / Glyph of Delusion: "Activate only before blockers are declared" outside combat (main phase 2, other turns) has no ruling; Glyph needs "creature that target Wall blocked this turn" history. Not built.
- Merseine: activation cost is the enchanted creature's mana cost, activated only by that creature's controller; needs host-cost placeholder that cannot become a free cost if state is missing. Foundation not built.
- Retriever Phoenix: Learn is rewritten to discard/draw text in scripts.py (no learn event); a "would learn" replacement needs a real learn event first. Not built.
- Chorus of the Conclave, Land Equilibrium, Ogre Battlecaster: unchanged from wave110n notes.

## s14: the 29 cards of wave110n-refused.md, split

Done (FULL now): Fleshwrither, Monastery Raid, Coffin Queen, Necrotic Plague (wave 110I s13); Grip of Amnesia, Reversal of Fortune, Overburden, Agrus Kos Spirit of Justice (lead merge); Guardian Archon, Wayta Trainer Prodigy (trigger multiplier cause "dealt", Scryfall ruling), Medomai's Prophecy (delayed trigger, ruling), Radiant Performer and Agrus Kos Eternal Soldier (ability spread, wave110e_once.radiate / stack_extension103), Glyph of Delusion, Acidic Dagger (rulings), Spoils of War (ruling 2008-08-01, not in the 29).

Unsettled ruling (leave): Spinneret and Spiderling ("deals 4 or more damage" with damage split over recipients: no CR rule and no Scryfall ruling), Land Equilibrium (agent C), Phylactery Lich (agent C).

Missing foundation (work): Zilortha (ruling exists: lethal by power in SBA 704.5g, combat 510.1c, trample, excess damage; touches sba.py:138, combat.lethal, this_way, replace excess), The Dominion Bracelet (control-another-player turn plus named-permanent exile cost), Megatron (excess-damage-to-controller replacement plus convert), Yavimaya Bloomsage // Channel (mana-ability grant mid-payment), Monument to Perfection, Animate Artifact (layer dependency), Torrent Elemental, Dark Intimations, Merseine, Voltaic Visionary, Chorus of the Conclave, Ogre Battlecaster, Retriever Phoenix, the sticker and Smuggler Captain cards (agent C owns the last 15 lines of lead/todo_from_n.txt).
- Spinneret and Spiderling (s15 recheck): "Whenever ~ deals 4 or more damage" has no recipient; Scryfall rulings (2025-09-19) only cover timing/spider count, CR 120 has no rule on summing damage dealt to several recipients in one event (combat damage split among blockers). No CR rule, no ruling, no close analogy: stays refused. Single-recipient case is settled (events.py `min`), the multi-recipient split is not.

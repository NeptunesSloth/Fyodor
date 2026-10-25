# Wave 100: researched and refused cards

Cards the wave 100 workers (A–P) researched but left PARTIAL, with the missing foundation or the unsettled rules question. Use this list before
picking a card up again: build the named foundation first, or find the ruling that settles it. "Pre-existing base failures" are tests that
already failed on `main` at 8d7b541b and were left as they were (several read the legacy `players[].mana` field; mana now lives in `mana_units`).



## 100E xdamage
- Midnight Arsonist: mana-ability check sees only activated "mana" kind (Gauntlet of Power, Doubling Cube misclassified).
- Ob Nixilis of the Black Oath: emblems can't hold activated abilities (emblem_text_ok).
- Selective Snare: no cast-time creature-type choice restricting targets.
- Nahiri's Sacrifice: no additional cost "sacrifice … with mana value X" when X not in mana cost.
- Spoils of War: X fixed from opponent graveyard at cast + opponent choice.
- Lava Burst: no "can't be dealt instead" damage flag.
- Shriekwood Devourer: ruling vs 608.2h LKI conflict, uncertain.
- Party Dude: no "one or more of your opponents are attacked" trigger (508.3b).
- Rampaging Raptor: no "battle that player protects" selector.
- Squall: no intervening P/T-equals-chosen-number condition.
- Avacyn's Judgment: divide total depends on madness paid; divide_total lacks cast info.
- Power Surge: no untapped-lands-at-turn-start snapshot.
- Printlifter Ooze, Crowd-Control Warden: token enters with X counters + face-up replacement.
- Dire Flail // Dire Blunderbuss: cost "an artifact other than ‹granter›".
- Sword of the Ages: compound sacrifice cost + total power sacrificed.
- Spry and Mighty: choose-exactly-two + power difference value.
- Phyrexian Ingester: linked exiled card P/T bonus.
- Kusari-Gama: "deals damage to a blocking creature" trigger.
- The Sea Devils: delayed trigger with target.
- Pandemonium: another player chooses trigger target.
- Diseased Vermin: "opponent previously dealt damage by it" history.
- Soul Immolation: mandatory blight X cost with cap.
- Waterbender's Restoration, Crashing Wave, Katara: waterbend cost.
- Outmaneuver: mandatory "assign as though not blocked".
- Kodama of the Center Tree: soulshift X.
- Numa: optional {X}{X} payment.
- Gelatinous Cube: target "exiled with ~" from exile to graveyard.
- Bargaining Table: opponent chosen on announcement before X.
- Need foundations: Idris, Incinerator of the Guilty, Imodane, Scarlet Spider, Another Round, Megatron, Abaddon, Reckless Crew, Magma Pummeler, Kosei, Donna Noble, Heart of Bogardan, Aurora Awakener, Sin Prodder, Hankyu, Arcum's Whistle, Dack Fayden, Battletide Alchemist, Auspicious Starrix, Descent into Madness, Reflecting Mirror.
- Pre-existing base failures seen: wave42d [Breeches, the Blastmaker]; wave41b test_brigid_adds_one_color_for_each_other_creature; wave43c test_cumulative_upkeep_add_mana_is_paid_by_adding_it; wave16b test_aftermath_half_only_from_the_graveyard_then_exiled; test_rules_casting: test_summoning_sick_creatures_cannot_tap_for_mana, test_sol_ring_commander_tax_and_mana_pools_empty, test_any_color_sources_ask_which_color.

## 100F attached
- Mind Whip, Admiral Beckett Brass: held prototypes (wrap-up doc).
- Vampiric Embrace: no ruling on "that creature" counter referent.
- Scythe of the Wretched: equipped creature + victim die together look-back (603.10a).
- Aspect of Wolf: two dynamic values X/Y in layer 7c.
- Curse of Conformity: group "lose all creature types" layer 4.
- Infantry Shield: "mobilize X, where X is its power".
- Call for Aid: player-level "can't attack that player this turn"; can't-be-sacrificed scope.
- Sorin −6: selector "other than that creature or ~".
- Hold for Ransom, Heliod's Punishment: granted ability refers to granting Aura.
- Bound by Moonsilver: "can't transform".
- Frozen in Ice, Blossombind: "can't become untapped" (~30 untap call sites).
- Cocoon: enchanted creature LKI after Aura sacrificed.
- Earthbind: Aura gains static ability.
- Curse of Bounty: per-attacking-opponent untap.
- Curse of Surveillance: count Curses attached to player + multi target players.
- Aegis of the Legion, Neglected Heirloom: mentor / transform trigger events.
- Bronze Cudgels: resolutions-this-turn count.
- One with the Kami: "modified" via departed creature's Aura LKI.
- Lithoform Blight: land type removal vs 305.7.
- Traveler's Cloak: landwalk of chosen type.
- ~40 not attempted: Aura tokens, copy effects, stickers, emblems, opponent-chosen targets.
- Pre-existing base failures: wave35d_as_long_as test_the_refused_conditional_statics_stay_manual [Warmonger's Chariot, Grond]; 44 in mana_producer_native46 + mana_persistent_replacements48; wave4k_x_sized (Chainer's Torment; Sanctum Weaver); wave5e_cast_limits refused_effects[Defending player can't cast spells this turn.]; wave33d_turn_state (Powerstone).

## 100A trigger
- Bladegriff Prototype: other opponent chooses when damaged one left; engine drops trigger.
- Saproling Infestation: "kicks a spell" count w/ multikicker unsettled.
- Overburden, Nature's Wrath: who "puts" creature onto battlefield unsettled.
- Teferi's Imp: phases-out look-back watcher.
- Dragon Broodmother: token creation skips devour entry choice.
- Veiled Crocodile: state trigger mid-resolution.
- Steamcore Scholar: disjunctive discard-cost selector.
- Suppressor Skyguard: prevention "this combat".
- Rigo, Oath of Kaya: trigger per attacked planeswalker.
- Ramses: attacker types as declared.
- Wall of Dust: restriction limited to future turn.
- Psychogenic Probe, Widespread Panic: shuffle cause not recorded; partial shuffles.
- Arashin War Beast: "recipient was blocking".
- Crack in Time: multi trigger incl. step trigger.
- Twisted Sewer-Witch: one Role per Rat (create_role one host).
- Firemane Angel, Quakebringer: battlefield+graveyard upkeep trigger.
- Wormfang Drake, Wormfang Crab: payment-exiled card link (607.2a).
- Invasion of Fiora: "since your last turn" history.
- Knights of the Black Rose: monarch at turn start.
- Jolly Gerbils: gift event. Golgari Brownscale: graveyard-to-hand event. Multani's Presence: countered event. Serene Master: power exchange.
- Rebellion of the Flamekin: can reuse clash event + clash_won100a.
- Pre-existing base failure: wave5e_cast_limits test_refused_effects[Defending player can't cast spells this turn.].

## 100C static_spell
- Mathemagics: 2^X draw loop unbounded with infinite mana; needs cap design.
- Needle Drop: any-target group filtered by damage history.
- V.A.T.S.: "equal toughness" relation recheck unsure.
- Rivals' Duel: "share no creature types" relation. Bioshift: same-controller across two target groups.
- Cut Short: "planeswalker activated this turn" not tracked/verified.
- Premature Burial: "since your last turn ended" history.
- Sphinx's Decree: cast-limit "during that player's next turn".
- Taunt: forced attack aimed at you. You Look Upon the Tarrasque: lure limited to opponents' creatures.
- Due Respect: turn-long enter-tapped replacement. Don't Move: "whenever a creature becomes tapped" delayed watch.
- Diminishing Returns: "draws up to seven". Grip of Amnesia: counter-unless non-mana cost.
- Kaervek's Spite: "discard your hand" spell additional cost. Taste of Paradise, Primitive Justice: pay X any number of times additional cost.
- Water Whip: waterbend additional cost. Rapid Fire: granted Rampage 2 never triggers.
- Thermal Flux: remove snow supertype. Serene Remembrance: shuffle one library twice.
- Brilliance Unleashed: "it's a 3/3 Robot artifact creature" semantics unsure. Fatal Lore: opponent-chosen mode.
- Sideswipe: 115.7c change any targets. Endless Swarm, Eternal Dominion: epic.
- Supper for Spiders: "They are Food artifacts" timing.
- Binding rename gotcha: refs inside a "union:" string are not renamed with l0_ prefix.

## 100D static_perm
- 13 Attractions (Information Booth, Concession Stand, Clown Extruder, Bumper Cars, Merry-Go-Round, Ferris Wheel, Costume Shop, Roller Coaster, Drop Tower, Fortune Teller, Bounce Chamber, Kiddie Coaster, Spinny Ride): no Attraction deck / roll to visit.
- Coalition Flag, Coalition Honor Guard, Standard Bearer: Flagbearer targeting obligation (601.2c).
- Necratog, Zombie Scavengers: graveyard_order policy (hidden zone readers).
- Wood Elemental, Dracoplasm, Sutured Ghoul, Dauntless Bodyguard: multi-object entering choice + link.
- Archangel of Strife, Pramikon, Captive Audience: per-player/direction/controller choice as enters.
- Displaced Dinosaurs: entry characteristics of another permanent + 614.12 order.
- Uphill Battle: "played" land detection in entry replacement.
- Indulge // Excess: aftermath from graveyard broken on base (wave16b test).
- Catch // Release: close-to-five distinct-type sacrifice.
- Coward // Killer, Hustle // Bustle, Discovery // Dispersal: time travel, turn face up choice, greatest-MV return.
- Planeswalkers: Teferi x2 (emblem; can't phase in), Karn x2 (pay any mana; restart game), Rowan Kenrith, Dovin Baan, Vraska the Unseen, Garruk x2, Calix, Aminatou, Xenagos -6, Nicol Bolas Dragon-God.
- Combat damage assignment variants: Butcher Orgg, Cunning Giant, Defensive Formation, Invasion Plans, Zilortha, Ogre Enforcer, Tapestry Warden.
- Costs: Squandered Resources (LKI land mana), Celestial Dawn, Drought, Brutal Suppression, Tectonic Split, Benevolent River Spirit (waterbend), Lunar Hatchling, Nethergoyf (escape shapes), Fleshwrither, Arcanum Wings, Ashling, Falkenrath Gorger (granted evoke/madness), Fblthp, Leonin Arbiter, Damping Engine (pay-to-ignore), Ward of Bones.
- Statics: Yixlid Jailer, Titania's Song, Umbra Mystic, Twins of Discord, Soulflayer, Ghostly Flame, Katabatic Winds, Tsabo's Web, Arboria, Cephalid Snitch, Goblin Flectomancer (115.7a), The Master Multiplied, The Valeyard.
- Triggers: Ghyrson Starn, Aboleth Spawn, Tzaangor Shaman, Khârn, Ms. Marvel, Grell Philosopher, Hawkeye, Starlight Spectacular, Averna, Bell Borca, Saheeli's Lattice.
- Known simplification: Enhanced Surveillance always looks at +2 (may not offered).
- Pre-existing base failures: player_protection (current_damage_source_controller_differs, copied_discard_damage_ability); wave22b test_comply_stops; replacements2 (no_replaceable_event_bypasses_the_choke_points, wordings_that_stay_manual); wave19a oath_of_nissa; wave16b aftermath; wave30d crypt_ghast_adds_only_for_a_swamp.

## 100I activated + costs
- Fractured Powerstone (planar die); Brutal Hordechief (choose another player's blocks).
- Arena, Magus of the Arena, Cuombajj Witches, Diaochan: opponent-chosen target. Rakdos Augermage: choose_from_hand chooser always controller.
- Simic Guildmage: same controller across two target groups. Tidal Control, Bullseye, Ion Storm: either/or costs.
- Night Soil (single graveyard cost), Illuminated Folio (reveal sharing color), Jandor's Ring (last card drawn), Back from the Brink (pay its mana cost), Rune-Brand Juggler ("suspected" cost vocab).
- Spatial Binding (can't phase out), Orcish Farmer (until controller's next untap step), The Moment (phased out until ~ leaves).
- Skyblade's Boon (battlefield-or-graveyard activation zone), Torrent Elemental (exile-only activation zone).
- Arcum's Sleigh (defending player for activator multiplayer), Kongming's Contraptions (attacked this step), Lodestone Bauble (non-target player chosen with zero targets).
- Grim Captain's Locker, Confession Dial (grants to graveyard cards), Crown of the Ages (Aura move to chosen host).
- Errant, Meletis Charlatan, Quicksilver Dragon (spell copy/retarget qualifiers). Sorrow's Path, General Jarkeld, Balduvian Warlord, Tidal Flats (combat rearrangement).
- Apocalypse Chime, Golgothian Sylex (set data); Tenth District Hero (name change); Balduvian Shaman (text change).
- Too large: Mechtitan, Book of Vile Darkness, Helm of Kaldra, Capitoline Triad, Zemo, Jetfire, Flamewar, Pyxis, Beamtown Bullies, Niko, Noctis, Smelting Vat, Monument, Aeon Engine, Frodo, Iron Man Armor, Symbiote Spider-Man, Requiem Monolith, Splintering Wind, Bone Shaman, Soul Sculptor, Autumn Willow, Benthic Explorers, Keeper of the Dead, Jester's Mask, Mirror of Fate, Grimoire Thief, Phyrexian Splicer, Room lock/unlock.
- Costs: Charred Foyer (Room door alt cost), Tezzeret (first artifact ability), Liesa (commander tax as life), Skyseer's Chariot, Obsidian Charmaw, Cleansing, Hipparion, Heart of Kiran, Advancing the Spirit, Chancellor of the Annex, Marshland Bloodcaster, Frenzied Saddlebrute.
- Free-cast set not attempted: Kefnet, Urianger, Elminster, Lightstall, Master of Predicaments, Dominion Bracelet, Portent, Heirloom Epic, Mavinda, Strict Proctor, Eye of Duskmantle, Draugr, Haldan, Magar, Panglacial, Ore-Rich, Uldaros, Bloodthirsty, Skyway Robber, Hama, Uvilda, Sanar, Kylox, Memory Vampire, Swindler's Scheme, Shaman's Trance, Amped Raptor.
- Thermal Flux: foundation now exists (layers remove_supertypes).
- Pre-existing base failures: wave51b Chrome Mox x2 + Pit of Offerings (old players[].mana field); sunforger test_free_x_spell; wave20c test_omnath_reads.

## 100J counters
- Rumbling Ruin: group can't-block by power checked at layer 6 before counters/pumps; ruling needs current power.
- Bioessence Hydra: loyalty counters on several walkers at once, one vs many triggers (Hardened Scales).
- Etched Slith: reflexive per +1/+1 counter put (Doubling Season); engine fires once.
- Kraven the Hunter: 603.10a look-back of greatest power among that player's creatures.
- Growing Dread: turned_face_up event lacks who turned it.
- Master Biomancer: "enters as a Mutant" from static.
- Silumgar Scavenger: what it exploited at resolution. Tizerus Charger: entering counter choice limited to escaping.
- Phylactery Lich: "As ~ enters, put counter on artifact you control". Shimatsu: devour-like non-keyword.
- Font of Agonies: pay-life event. Tourach's Chant, Thelon's Chant: "a player puts a Forest/Swamp onto battlefield" event.
- Neerdiv: activating ability of graveyard card event. Overseer of Vault 76: remove counters from among permanents cost.
- Thelon of Havenwood: exile Fungus card from a graveyard cost. Nivmagus Elemental: exile a spell you control cost.
- Minthara: dynamic ward {X}. Tale of Katara and Toph: granted first-time-each-turn trigger.
- Mindbender Spores: granted conditional doesn't untap. Gutter Grime: token P/T reading source counters.
- Green Dragon: turn-long damage watch from ETB. Resplendent Marshal: shares type with exiled card. Cannibalize: same-controller target pair. Livio, Etrata: counters on exiled cards.
- Need foundations: Firebender Ascension, Yes Man, Millennium Calendar, Master Chef, Tyvar, The War Doctor, Capricopian, Last Night Together, Harold and Bob, Experimental Lab, Venture Forth, Hero of Bretagard, Rinoa, Primal Adversary, Spectral Adversary, Regna's Sanction, Mairsil, The Master, Bomb Squad, Churning Reservoir, Love on the Battlefield, Magnetic Web, Turf War, Blue Loyal Raptor, Rasputin, Spark Rupture, Agent Maria Hill, Rock Hydra, Wiitigo, Cycle of Life.
- Pre-existing base failures: wave52b_small test_frontier_siege_khans[Khans-2], test_mana_echoes[0-1],[2-3].
- Test note: manual "move" actions don't fire ETB/dies triggers; use real casts/Murder.

## 100G zones (98 left PARTIAL; one line each in worker report)
- Scarlet Witch, Etrata, Old-Growth Troll, Yarus, Silver Wyvern/Torchling/Rebound/Muck Drubb (change target), Gollum (opponent guess), Blink, Hunted by The Family (villainous), Night Shift of the Living Dead (planar die), Echo Chamber/Mausoleum Turnkey (opponent picks target), Cathedral Membrane, Lumbering Laundry (look at face-down: hidden info), Hibernation's End (paid cumulative upkeep event), Ghostly Dancers (Room unlock), Superior Spider-Man/Hulking Metamorph/Aurora Shifter/Essence of the Wild (copy w/ exceptions), Corruption of Towashi/Huntmaster (transform event), Alpine Moon, Puca's Covenant, Faces of the Past/Martyr's Bond/Reins of the Vinesteed (LKI subtypes not kept), Scrap Welder/Sidisi/Fabrication Foundry (X tied to target), Rise of Sozin/Ran and Shaw (firebending), Hatchery Sliver/Djinn Illuminatus/Ian Chesterton/Threefold Signal (granted replicate), Zndrsplt's Judgment, Bane, Caves of Androzani, Voltaic Visionary, Arcee, Reap, Emrakul the World Anew, Garth One-Eye, Faceless One/Clara Oswald/Prismatic Piper (pregame color), Endless Whispers, Urborg Panther/Templar Knight, Jötun Grunt, Day of the Moon, Necrotic Plague, Shelob, Nick Fury, March from Velis Vel, Leyline of Transformation, Twilight Diviner, Clive, Ugin's Mastery, Oath of Lieges, Turtles Forever/Raven's Warning (outside game), Immerwolf (can't transform), Thrill-Kill Disciple (squad discard cost), Behemoth of Vault 0, Summon: Brynhildr, Aphetto Dredging, Zinnia (granted offspring), Coffin Queen, First Tyrannic War I, Roar of Jukai (splice), Lucius, Mishra Claimed by Gix (attack meld), Corpse Dance/Shallow Grave (manual by design), Invasion of the Giants II, Havengul Laboratory, Homura (flip), Liberated Livestock, Tatsumasa, Bound // Determined, Seraph, Selective Adaptation, Panoptic Projektor, Smuggler Captain, Oracle en-Vec, Vodalian War Machine, Thijarian Witness.
- Engine gap: LKI doesn't store layer 4/5 type info. Pre-existing hidden-info concern: REVEAL_FROM_HAND.
- Pre-existing base failures: wave37b Mistmoon Griffin; wave53c rest_of_list_stays_manual[Galea]; wave50j Pia Nalaar; review30_random_bottom x2.

## 100L unfinity (Attraction deck + tickets built; stickers refused)
- ~45 sticker cards: card data lacks sheets' name/art stickers (Scryfall only ability + P/T stickers); also needs Stickers deck section, 123.2a random 3 of 10+ sheets, name text changes, layer 6 grants for 96 sticker texts, 7b P/T, 123.5 persistence, ticket payment, UI.
- Monitor Monitor (rerolls 706.2b), Myra the Magnificent (cast copy of card 707.12 + midway delayed trigger), Ferris Wheel (phase out until roll), Bounce Chamber, Drop Tower, Swinging Ship, Tunnel of Love not attempted.

## 100K aslongas + instead
- Sea Gate Stormcaller (copy next spell delayed), Dralnu/Wolverine (damage timing), Nefarious Lich, Rain of Gore (life gain cause), Golden Throne/Exquisite Archangel/Lich's Mirror (lose-game replacement w/ simultaneous SBA), Wheel of Sun and Moon, Liege of the Tangle, Ray of Frost/Animate Artifact (condition on own layered types), Manor Gargoyle, Common Cause/Escaped Shapeshifter, War Historian (battle-attack history), Desert Were-Worm, Zariel, Maddening Imp/Norritt/Nettling Imp (deferred didn't-attack), Harmonious/Crackling Emergence (destruction replacement), Dog Umbra (granted umbra armor), Evil's Thrall, Welcome to the Fold (madness X), Back for Seconds/Garland/Merieke/Infernal Denizen/Rootwater Matriarch/Preacher/Old Man of the Sea/Vislor/War Games/Giant Oyster/Dread Wight/Peace Talks (durations/choices), Reed Richards/Scion of Halaster (first-draw replacement), Ugin's Nexus, Dodecapod/Library of Leng/Nephalia Academy (discard replacements), Ashiok (pay-life replacement), Firestorm Phoenix/Pulmonic Sliver/Heat Wave/Dearly Departed/Retriever Phoenix, Zabaz (modular source), Ravenous Slime (LKI power), Freyalise's Winds (616.1 choice), Sheltering Prayers, Wall of Shadows, Guardian Beast, Guile/Don't Blink/Land Equilibrium/Sheltered Valley/Storm Herald/Ogre Battlecaster/Kylox's Voltstrider/Soul Echo/Yidaro, Kitesail Larcenist/Exchange of Words/Assimilation Aegis/Blade of Shared Souls/Eriette/Immortal Obligation/Thranduil's Decree/Taster of Wares/Zara/Wall of Stolen Identity/Volrath's Shapeshifter/Ultima/Tovolar/Phasing of Zhalfir/Pandorica/Braided Net/Zygon/Spider-Woman/Dimensional Breach/Temporal Aperture/Welcome to Jurassic Park ("for as long as" / copy / text exchange machinery).
- Pre-existing base failures: wave38b Mu Yanling + Lita.

## 100H turnstate (62 left PARTIAL)
- Guardian Angel, Lathiel (divide up to), Bamboozling Beeble, Season of the Witch, Kaito Dancing Shadow, Tempt with Mayhem, Stolen Uniform, End-Blaze Epiphany, Hurkyl, Sen Triplets, Toggo, Apple of Eden, Repeated Reverberation, Rip Spawn Hunter (second main trigger), Dalkovan Encampment, Havengul Lich, Selvala's Stampede/Expropriate/Fateful Tempest (council), Eye for an Eye, Touch of Moonglove, Overclocked Electromancer (excess damage), Lolth, Long List of the Ents (noted types), Whispersteel Dagger, Melira (poison cap), Pygmy Hippo, Mystic Reflection, Sidequest Play Blitzball, Soulfire Grand Master, World at War, Mindstorm Crown (hand size at turn start), Alania, Elemental Expressionist, Biomancer's Familiar, War Barge, Medomai's Prophecy, Osseous Sticktwister, Zevlor, Backdraft, Genesis of the Daleks, Acidic Dagger, Krovikan Vampire, Runesword, Autumn's Veil, Archaic's Agony, Optimus Prime, Cosmic Intervention, Winter Cynical Opportunist, Slicer, Oblivious Bookworm, Kill-Suit Cultist, Gather Specimens, Kjeldoran Guard, North Star, Whippoorwill, Silhouette, Glyph of Delusion, Thirsting Axe, Battlefield Scrounger.
- Pre-existing base failures: wave4d test_river_of_tears_after_playing_a_land.

## 100B ifyoudo (~140 not started: copy/loop/guess/cast-from-elsewhere)
- Catastrophe, Black Panther, Inquisitor Eisenhorn, Arsenal Thresher, Pharika's Spawn, Saw, Lazav, Lamplight Phoenix, Chandra Chill of Compliance (surveil this-way binding), Lotus Vale/Scorched Ruins (enter_cost one object), Mariposa, Nahiri's Lithoforming, Corrosion, Desertion (stack to battlefield), Rebellion of the Flamekin (clash trigger), Gluttonous Hellkite, Puppet Master, Grime Gorger, Zimone's Experiment, Avatar Destiny, Synthetic Destiny, Empty the Laboratory, Choice of Damnations (no upper limit), Ulamog's Despoiler, Thief of Blood, Sin, Shifty Doppelganger, Kain, Tainted Specter, Invasion of Tarkir, Specter of Mortality, Time Reaper.
- Pre-existing base failures: wave29a_hints (many); wave9d joraga_treespeaker.

## 100M multi part 1
- See the Unwritten (ferocious put two: one allowed?), Gix's Command (non-target up-to-one chooser in modes), Cleansing Meditation, Glen Elendra's Answer, Decree of Annihilation (simultaneous exile across zones), Elderscale Wurm (replace floor op n=7), Grab the Reins + Aerith Rescue Mission (mode-text rewrite hook in scripts.modal_definition, ~2 lines), Kitsune Ace, Moment of Reckoning ("Choose up to four"), Doomsday Confluence ("Choose X"), What Must Be Done, Sunder the Gateway, Infernal Offering, Yuna's Decision, Plunge into Darkness, Convert to Slime, Contractual Safeguard, Geth's Summons, Starnheim Unleashed.
- Pre-existing base failures: wave46a test_obosh_counts_the_x_of_a_spell_on_the_stack; wave43b_mana 6 tests (Utopia Sprawl, Caged Sun, Gauntlet of Power).
- Lesson: fingerprint snap lazily imports worktree code; snapshot from a frozen copy if editing concurrently.

## 100P otherchooser
- Drafted, untested (patch a draft patch that was not kept): Hollow Specter, Vizkopa Confessor, Devastating Mastery, Deliver Unto Evil, Covenant of Minds, Choice of Damnations (need keep_two100p, choose_number100p).
- Captive Audience, Xantcha, Pendant of Prosperity, Abby: enters-under-chosen-controller replacement on every entry path.
- Fatal Lore, Library of Lat-Nam, Misfortune: 700.2e opponent picks mode during casting (casting.choose_modes asks only actor).
- Extrapolate the Impossible: no-op in Commander per 903.11 (cheap). Turtles Forever: library-only under 903.11, "exactly four" unresearched.
- Not attempted: Gollum, Liar's Pendulum, Master of Predicaments, Seventh Doctor, Echo Chamber, Necrotic Plague, Wormfang Crab, Khârn, Soul Echo, Oracle en-Vec, Master of the Wild Hunt, Bend or Break, Raiding Party, Mist of Stagnation, Loxodon Peacekeeper, Sphinx Ambassador, Callous Oppressor, Fell Beast's Shriek.
- Pre-existing base failure: wave18c_pregame_vote test_chancellor_of_the_tangle_adds_mana (old mana field).

## 100N multi part 2
- Light Up the Night (flashback cost remove X loyalty), Voltage Surge (additional cost paid mapping), Bite Down on Crime (evidence cost reduction timing), Hulk's Thunderclap (behold), Cobra Trap/Summoning Trap (destroyed-by-opponent / countered-by-opponent turn facts), Avenge (their last turn history), Ravager Wurm (non-mana activated ability selector), Compel Brutality, Psychic Rebuttal, Life of Toshiro Umezawa (saga modes "Choose one"), Glimpse the Cosmos, Liquid Fire, Rock Jockey, Spinning Darkness (graveyard order).
- Pre-existing base failures: refused_copy_mana test_restriction_grammar; wave31d_spell_copies test_unread_wordings_stay_manual x2; player_protection x3.

## 100O retarget
- Parnesse ("that spell" copy vs original unsettled), Shiko and Narset (targets condition on countered spell LKI), Emissary of Grudges ("as enters" secret choice), Reflecting Mirror (X from target spell), Barroom Brawl (opponent to your left), Leori.
- Not attempted: Psychic Battle, Lightning Storm, Chef's Kiss, Gandalf, Alania, Bill Potts, Codie, Finale of Promise, Ulalek, Enigma Jewel, Rowan Kenrith.
- Pre-existing base failure: exile_cast_outcomes45 test_extract_actual_zero_or_more[5].

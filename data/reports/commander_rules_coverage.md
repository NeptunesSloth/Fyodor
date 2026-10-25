# Commander rules coverage

Card data: Scryfall `2026-10-23T21:05:45.137+00:00` · Comprehensive Rules 2026-09-25 · rules engine v2 · generated 2026-10-25 06:32

Only cards that are **legal in Commander today** count. Banned cards (83) are COMMANDER_BANNED and excluded.

## Commander coverage

Commander-legal cards: **32068**

| Level | Cards | Share |
|---|---|---|
| FULL | 30775 | 96.0% |
| PARTIAL | 1293 | 4.0% |
| REVIEW | 0 | 0.0% |
| MANUAL | 0 | 0.0% |

Possible commanders (CR 903.3/903.3a, incl. Backgrounds): **3502** — FULL 3244, PARTIAL 258, REVIEW 0, MANUAL 0

## Pod coverage

No pod decks in the inventory yet (`python -m tools.rules_inventory`); the queue below is ranked by Commander-legal cards unlocked.

## Coverage quality

- Ability features (lines, keywords, play/cast/combat) across Commander-legal cards: 113146
- Automated: 111347 (98.4%) · unrecognized clauses: 1799
- Oracle text classified (automated, or sorted into a concrete missing capability): 99.9% · unclassified clauses: 146
- Distinct missing-capability clusters: 1182

## Missing capabilities by category

| Category | Cards affected | Clauses |
|---|---|---|
| MISSING EFFECT | 682 | 827 |
| MISSING SELECTOR | 230 | 244 |
| MISSING TRIGGER EVENT | 138 | 141 |
| UNSUPPORTED ORACLE PATTERN | 120 | 146 |
| MISSING REPLACEMENT PATTERN | 119 | 124 |
| MISSING CONTINUOUS EFFECT | 111 | 116 |
| MISSING RESTRICTION | 66 | 70 |
| MISSING COST / PERMISSION RULE | 64 | 64 |
| MISSING MECHANIC | 31 | 32 |
| MISSING COST | 29 | 29 |
| MANA ABILITY WORDING | 6 | 6 |

## Highest-payoff clusters

Ranked by pod cards, pod commanders, possible commanders affected, cards it alone would unlock, then all Commander cards needing it.

| # | Category | Cluster | Commanders | Only missing piece for | Commander cards | Examples |
|---|---|---|---|---|---|---|
| 1 | MISSING EFFECT | if ~ … | 7 | 9 | 16 | Reservoir Kraken, Tenth District Hero, Kytheon, Hero of Akros // Gideon, Battle-Forged |
| 2 | MISSING EFFECT | draw n … | 6 | 9 | 25 | Spirit Water Revival, Volo, Itinerant Scholar, False Dawn |
| 3 | MISSING EFFECT | choose n … | 6 | 4 | 40 | Gix's Command, Nexus Mentality, Command Performance |
| 4 | MISSING EFFECT | pay {m} … | 5 | 7 | 10 | Ezio Auditore da Firenze, Vraska, the Silencer, Tilonalli's Summoner |
| 5 | MISSING REPLACEMENT PATTERN | As ~ enters, … | 4 | 10 | 31 | Tyrannical Pitlord, Deification, Bitter Feud |
| 6 | MISSING EFFECT | return it to the … | 4 | 3 | 5 | Yarus, Roar of the Old Gods, Missy, Bronzehide Lion |
| 7 | MISSING EFFECT | gain control of target … | 3 | 6 | 9 | Sorin of House Markov // Sorin, Ravenous Neonate, Coveted Falcon, Rootwater Matriarch |
| 8 | MISSING EFFECT | choose target … | 3 | 5 | 8 | Plague Reaver, Sen Triplets, Jeska, Thrice Reborn |
| 9 | MISSING EFFECT | look at the top … | 3 | 3 | 6 | Scarlet Witch, Chaotic Avenger, Gollum, Scheming Guide, Omnath, Locus of All |
| 10 | UNSUPPORTED ORACLE PATTERN | As ~ enters, … | 3 | 1 | 3 | The Mimeoplasm, Deadpool, Trading Card, Pramikon, Sky Rampart |
| 11 | MISSING MECHANIC | firebending | 3 | 0 | 4 | The Rise of Sozin // Fire Lord Sozin, Avatar Aang // Aang, Master of Elements, Ozai, the Phoenix King |
| 12 | MISSING SELECTOR | target | 2 | 13 | 19 | Meddle, Kaervek's Torch, Quicksilver Dragon |
| 13 | MISSING EFFECT | you get {m} … | 2 | 10 | 16 | Amped Raptor, Wheel of Potential, Lineprancers |
| 14 | MISSING EFFECT | put a ±n/±n counter(s) … | 2 | 7 | 8 | Lazav, Familiar Stranger, Silumgar Scavenger, Capricopian |
| 15 | MISSING EFFECT | exile cards from the … | 2 | 4 | 5 | Venture Forth, Illuna, Apex of Wishes, Demonlord Belzenlok |
| 16 | MISSING CONTINUOUS EFFECT | You may have ~ enter as … | 2 | 3 | 3 | The Master, Formed Anew, Hulking Metamorph, The Fourteenth Doctor |
| 17 | MISSING EFFECT | reveal cards from the … | 2 | 3 | 3 | Sanar, Innovative First-Year, Aurora Awakener, Dack Fayden, Helping Hand |
| 18 | MISSING SELECTOR | target creature card with mana value | 2 | 2 | 3 | Gelatinous Cube, Shelob, Dread Weaver, Sidisi, Regent of the Mire |
| 19 | MISSING EFFECT | create ~ … | 2 | 2 | 2 | Stangg, Stangg, Echo Warrior |
| 20 | MISSING REPLACEMENT PATTERN | If damage would be dealt to ~, … | 2 | 2 | 2 | Dralnu, Lich Lord, Wolverine, Fierce Fighter |
| 21 | MISSING SELECTOR | target instant or sorcery card with | 2 | 2 | 2 | Soundwave, Sonic Spy // Soundwave, Superior Captain, Myra the Magnificent |
| 22 | UNSUPPORTED ORACLE PATTERN | If ~ is your commander, … | 2 | 2 | 2 | Faceless One, The Prismatic Piper |
| 23 | UNSUPPORTED ORACLE PATTERN | You may reveal the first card … | 2 | 2 | 2 | God-Eternal Kefnet, Inquisitor Eisenhorn |
| 24 | MISSING EFFECT | exile ~ … | 2 | 1 | 11 | Spirit Water Revival, All Hallow's Eve, Teferi's Reproach |
| 25 | UNSUPPORTED ORACLE PATTERN | ~ enters under the control of … | 2 | 1 | 4 | Captive Audience, Xantcha, Sleeper Agent, Abby, Merciless Soldier |
| 26 | MISSING EFFECT | target opponent gains control … | 2 | 1 | 3 | Jon Irenicus, Shattered One, Yes Man, Personal Securitron, Chaos Lord |
| 27 | MISSING CONTINUOUS EFFECT | Each creature you control has “…” | 2 | 1 | 2 | Tyvar the Bellicose, Tazri, Stalwart Survivor |
| 28 | MISSING CONTINUOUS EFFECT | ~ has all activated and triggered … | 2 | 1 | 2 | Idris, Soul of the TARDIS, Koh, the Face Stealer |
| 29 | MISSING CONTINUOUS EFFECT | ~'s power is equal to the … | 2 | 0 | 3 | Roxi, Publicist to the Stars, Bell Borca, Spectral Sergeant, Sutured Ghoul |
| 30 | MISSING EFFECT | exile the top card … | 2 | 0 | 3 | Evelyn, the Covetous, Kianne, Dean of Substance // Imbraham, Dean of Theory, Fires of Mount Doom |
| 31 | MISSING EFFECT | mill n … | 2 | 0 | 2 | Tazri, Stalwart Survivor, Estrid, the Masked |
| 32 | MISSING REPLACEMENT PATTERN | If you would lose unspent mana, … | 2 | 0 | 2 | Omnath, Locus of All, Ozai, the Phoenix King |
| 33 | MISSING EFFECT | until end of turn … | 1 | 12 | 17 | Vincent's Limit Break, Lumbering Laundry, Idol of Endurance |
| 34 | MISSING EFFECT | ~ deals n … | 1 | 9 | 19 | Quakebringer, Splintering Wind, Power Surge |
| 35 | MISSING SELECTOR | target creatures | 1 | 8 | 19 | Lathiel, the Bounteous Dawn, Hunted by The Family, Bounty of the Hunt |
| 36 | MISSING EFFECT | put n … | 1 | 6 | 8 | Ashiok, Nightmare Weaver, Nick Fury, Agent of S.H.I.E.L.D., Next of Kin |
| 37 | MISSING EFFECT | reveal the top n … | 1 | 5 | 6 | Sword-Point Diplomacy, Smelting Vat, See the Unwritten |
| 38 | MISSING EFFECT | you get an emblem … | 1 | 4 | 7 | Ob Nixilis of the Black Oath, Teferi, Who Slows the Sunset, Gideon of the Trials |
| 39 | MISSING EFFECT | exile up to n … | 1 | 4 | 4 | Mysterious Limousine, Chaotic Transformation, Don & Leo, Problem Solvers |
| 40 | MISSING EFFECT | reveal the top card … | 1 | 3 | 4 | Jadzi, Oracle of Arcavios // Journey to the Oracle, Deceiver of Form, Sin Prodder |
| 41 | MISSING EFFECT | for each player … | 1 | 3 | 3 | Zndrsplt's Judgment, Regna's Sanction, Vaevictis Asmadi, the Dire |
| 42 | MISSING SELECTOR | target instant or sorcery card in | 1 | 3 | 3 | Magar of the Magic Strings, Filigree Racer, Songcrafter Mage |
| 43 | MISSING SELECTOR | target room | 1 | 3 | 3 | Marina Vendrell, Ghostly Keybearer, Keys to the House |
| 44 | MISSING EFFECT | choose an opponent … | 1 | 3 | 2 | Faramir, Prince of Ithilien, Infernal Offering |
| 45 | MISSING COST / PERMISSION RULE | As an additional cost to cast … | 1 | 2 | 32 | Deadly Cover-Up, Spirit Water Revival, Fix What's Broken |
| 46 | MISSING EFFECT | target creature you control … | 1 | 2 | 5 | Wayta, Trainer Prodigy, Touch of Moonglove, Bite Down on Crime |
| 47 | MISSING EFFECT | exile target … | 1 | 2 | 4 | Tawnos's Coffin, Lukka, Coppercoat Outcast, Kaya, Spirits' Justice |
| 48 | MISSING EFFECT | exile any number of … | 1 | 2 | 3 | Another Round, Tetravus, Winter, Cynical Opportunist |
| 49 | MISSING EFFECT | have ~ … | 1 | 2 | 3 | The Irencrag, Johan, Gurzigost |
| 50 | MISSING SELECTOR | target players | 1 | 2 | 3 | Kozilek, the Broken Reality, Officious Interrogation, Memory Vampire |
| 51 | MISSING COST / PERMISSION RULE | You may play lands and cast … | 1 | 2 | 2 | Haldan, Avid Arcanist, Eye of Duskmantle |
| 52 | MISSING EFFECT | create a n/n blue … | 1 | 2 | 2 | Mysterio, Master of Illusion, Tatsumasa, the Dragon's Fang |
| 53 | MISSING EFFECT | exile it … | 1 | 2 | 2 | The Master, Gallifrey's End, Meandering Towershell |
| 54 | MISSING EFFECT | exile n … | 1 | 2 | 2 | Kefka, Dancing Mad, Specter of Mortality |
| 55 | MISSING EFFECT | if it was n … | 1 | 2 | 2 | Old-Growth Troll, Harold and Bob, First Numens |
| 56 | MISSING EFFECT | put ~ … | 1 | 2 | 2 | The Spot, Living Portal, Torrent Elemental |
| 57 | MISSING EFFECT | return n … | 1 | 2 | 2 | Kaito, Dancing Shadow, Rinoa, Angel Wing |
| 58 | MISSING EFFECT | return that card to … | 1 | 2 | 2 | Shirei, Shizo's Caretaker, Puppet Master |
| 59 | MISSING EFFECT | sacrifice any number of … | 1 | 2 | 2 | Kylox, Visionary Inventor, Hew the Entwood |
| 60 | MISSING EFFECT | tap target … | 1 | 2 | 2 | Spider-Woman, Secret Agent, Custodi Peacekeeper |
| 61 | MISSING SELECTOR | target creature they control | 1 | 2 | 2 | Echo Chamber, Cloak and Dagger, Entwined |
| 62 | MISSING SELECTOR | target creatures controlled by different players | 1 | 2 | 2 | Lagrella, the Magpie, Chaos Mutation |
| 63 | MISSING SELECTOR | target instant or sorcery card | 1 | 2 | 2 | Mavinda, Students' Advocate, Ogre Battlecaster |
| 64 | MISSING SELECTOR | target nonlegendary creature | 1 | 2 | 2 | Niko, Light of Hope, Mystic Reflection |
| 65 | MISSING SELECTOR | target opponent mills N card(s) | 1 | 2 | 2 | Hama, the Bloodbender, Helm of Obedience |
| 66 | MISSING EFFECT | exile the top n … | 1 | 1 | 4 | Kianne, Dean of Substance // Imbraham, Dean of Theory, Lukka, Coppercoat Outcast, Monastery Raid |
| 67 | MISSING EFFECT | if you control n … | 1 | 1 | 3 | Tovolar, Dire Overlord // Tovolar, the Midnight Scourge, See the Unwritten, Desert Warfare |
| 68 | MISSING EFFECT | up to n … | 1 | 1 | 3 | Kytheon, Hero of Akros // Gideon, Battle-Forged, Oko, Lorwyn Liege // Oko, Shadowmoor Scion, Boros Battleshaper |
| 69 | MISSING EFFECT | you choose which creatures … | 1 | 1 | 3 | Odric, Master Tactician, Master Warcraft, Melee |
| 70 | MISSING COST / PERMISSION RULE | Once each turn, … | 1 | 1 | 2 | Evelyn, the Covetous, Charred Foyer // Warped Space |
| 71 | MISSING EFFECT | each player gains control … | 1 | 1 | 2 | Inniaz, the Gale Force, Herald of Leshrac |
| 72 | MISSING EFFECT | for each opponent … | 1 | 1 | 2 | Decoy Gambit, Nihiloor |
| 73 | MISSING EFFECT | you and target … | 1 | 1 | 2 | Guardian Archon, Malik, Grim Manipulator |
| 74 | MISSING REPLACEMENT PATTERN | If ~ would die, … | 1 | 1 | 2 | Firestorm Phoenix, Darigaaz Reincarnated |
| 75 | MISSING SELECTOR | target creature card in your graveyard | 1 | 1 | 2 | Desdemona, Freedom's Edge, Rescue from the Underworld |
| 76 | MISSING SELECTOR | target player's next turn | 1 | 1 | 2 | Rowan Kenrith, Taunt |
| 77 | MISSING TRIGGER EVENT | Whenever N or more cards are put into exile from your hand or a spell or ability you control exiles N or more permanents from the battlefield | 1 | 1 | 2 | Ranar the Ever-Watchful, Hero of Bretagard |
| 78 | MISSING TRIGGER EVENT | Whenever a source an opponent controls deals damage to you or N permanent(s)(s) you control | 1 | 1 | 2 | Flameblade Angel, Elesh Norn // The Argent Etchings |
| 79 | MISSING CONTINUOUS EFFECT | As long as ~ is enchanted, … | 1 | 1 | 1 | Kosei, Penitent Warlord |
| 80 | MISSING CONTINUOUS EFFECT | Creature spells you cast gain offspring … | 1 | 1 | 1 | Zinnia, Valley's Voice |

## Largest clusters (Commander cards affected)

| # | Category | Cluster | Commander cards | Only missing piece for | Commanders | Examples |
|---|---|---|---|---|---|---|
| 1 | MISSING EFFECT | choose n … | 40 | 4 | 6 | Gix's Command, Nexus Mentality, Command Performance |
| 2 | MISSING COST / PERMISSION RULE | As an additional cost to cast … | 32 | 2 | 1 | Deadly Cover-Up, Spirit Water Revival, Fix What's Broken |
| 3 | MISSING REPLACEMENT PATTERN | As ~ enters, … | 31 | 10 | 4 | Tyrannical Pitlord, Deification, Bitter Feud |
| 4 | MISSING EFFECT | draw n … | 25 | 9 | 6 | Spirit Water Revival, Volo, Itinerant Scholar, False Dawn |
| 5 | MISSING EFFECT | cast ~ … | 23 | 0 | 1 | Siren's Call, Camouflage, Mirror Match |
| 6 | MISSING SELECTOR | target | 19 | 13 | 2 | Meddle, Kaervek's Torch, Quicksilver Dragon |
| 7 | MISSING EFFECT | ~ deals n … | 19 | 9 | 1 | Quakebringer, Splintering Wind, Power Surge |
| 8 | MISSING SELECTOR | target creatures | 19 | 8 | 1 | Lathiel, the Bounteous Dawn, Hunted by The Family, Bounty of the Hunt |
| 9 | MISSING EFFECT | until end of turn … | 17 | 12 | 1 | Vincent's Limit Break, Lumbering Laundry, Idol of Endurance |
| 10 | MISSING EFFECT | if ~ … | 16 | 9 | 7 | Reservoir Kraken, Tenth District Hero, Kytheon, Hero of Akros // Gideon, Battle-Forged |
| 11 | MISSING EFFECT | you get {m} … | 16 | 10 | 2 | Amped Raptor, Wheel of Potential, Lineprancers |
| 12 | MISSING EFFECT | exile ~ … | 11 | 1 | 2 | Spirit Water Revival, All Hallow's Eve, Teferi's Reproach |
| 13 | MISSING EFFECT | put a name sticker … | 11 | 4 | 0 | Baaallerina, Sword-Swallowing Seraph, _____ _____ _____ Trespasser |
| 14 | MISSING EFFECT | pay {m} … | 10 | 7 | 5 | Ezio Auditore da Firenze, Vraska, the Silencer, Tilonalli's Summoner |
| 15 | MISSING EFFECT | gain control of target … | 9 | 6 | 3 | Sorin of House Markov // Sorin, Ravenous Neonate, Coveted Falcon, Rootwater Matriarch |
| 16 | MISSING EFFECT | choose target … | 8 | 5 | 3 | Plague Reaver, Sen Triplets, Jeska, Thrice Reborn |
| 17 | MISSING EFFECT | put a ±n/±n counter(s) … | 8 | 7 | 2 | Lazav, Familiar Stranger, Silumgar Scavenger, Capricopian |
| 18 | MISSING EFFECT | put n … | 8 | 6 | 1 | Ashiok, Nightmare Weaver, Nick Fury, Agent of S.H.I.E.L.D., Next of Kin |
| 19 | MISSING EFFECT | you get an emblem … | 7 | 4 | 1 | Ob Nixilis of the Black Oath, Teferi, Who Slows the Sunset, Gideon of the Trials |
| 20 | MISSING EFFECT | if there are n … | 7 | 3 | 0 | Convert to Slime, Happily Ever After, Osseous Sticktwister |
| 21 | MISSING EFFECT | choose up to n … | 7 | 1 | 0 | Teferi, Who Slows the Sunset, Mirror of Fate, Temporal Firestorm |
| 22 | MISSING EFFECT | look at the top … | 6 | 3 | 3 | Scarlet Witch, Chaotic Avenger, Gollum, Scheming Guide, Omnath, Locus of All |
| 23 | MISSING EFFECT | reveal the top n … | 6 | 5 | 1 | Sword-Point Diplomacy, Smelting Vat, See the Unwritten |
| 24 | MISSING EFFECT | create n … | 6 | 2 | 0 | Reckless Crew, Nacatl War-Pride, Cobra Trap |
| 25 | MISSING EFFECT | return it to the … | 5 | 3 | 4 | Yarus, Roar of the Old Gods, Missy, Bronzehide Lion |
| 26 | MISSING EFFECT | exile cards from the … | 5 | 4 | 2 | Venture Forth, Illuna, Apex of Wishes, Demonlord Belzenlok |
| 27 | MISSING EFFECT | target creature you control … | 5 | 2 | 1 | Wayta, Trainer Prodigy, Touch of Moonglove, Bite Down on Crime |
| 28 | MISSING EFFECT | sacrifice n … | 5 | 5 | 0 | Nahiri's Lithoforming, Empty the Laboratory, Saw |
| 29 | MISSING EFFECT | return ~ … | 5 | 4 | 0 | Aetherplasm, Reins of the Vinesteed, Evershrike |
| 30 | MISSING SELECTOR | target creature of an opponent's choice | 5 | 4 | 0 | Evangelize, Preacher, Arena |
| 31 | MISSING EFFECT | destroy target … | 5 | 1 | 0 | Break the Ice, Regicide, Primitive Justice |
| 32 | MISSING EFFECT | search your library for … | 5 | 1 | 0 | Kasmina, Enigma Sage, Central Elevator // Promising Stairs, Celestial Reunion |
| 33 | MISSING EFFECT | surveil n … | 5 | 1 | 0 | Chandra, Chill of Compliance, Kaya, Spirits' Justice, Central Elevator // Promising Stairs |
| 34 | MISSING EFFECT | epic … | 5 | 0 | 0 | Eternal Dominion, Neverending Torment, Undying Flames |
| 35 | MISSING MECHANIC | firebending | 4 | 0 | 3 | The Rise of Sozin // Fire Lord Sozin, Avatar Aang // Aang, Master of Elements, Ozai, the Phoenix King |
| 36 | UNSUPPORTED ORACLE PATTERN | ~ enters under the control of … | 4 | 1 | 2 | Captive Audience, Xantcha, Sleeper Agent, Abby, Merciless Soldier |
| 37 | MISSING EFFECT | exile up to n … | 4 | 4 | 1 | Mysterious Limousine, Chaotic Transformation, Don & Leo, Problem Solvers |
| 38 | MISSING EFFECT | reveal the top card … | 4 | 3 | 1 | Jadzi, Oracle of Arcavios // Journey to the Oracle, Deceiver of Form, Sin Prodder |
| 39 | MISSING EFFECT | exile target … | 4 | 2 | 1 | Tawnos's Coffin, Lukka, Coppercoat Outcast, Kaya, Spirits' Justice |
| 40 | MISSING EFFECT | exile the top n … | 4 | 1 | 1 | Kianne, Dean of Substance // Imbraham, Dean of Theory, Lukka, Coppercoat Outcast, Monastery Raid |
| 41 | MISSING EFFECT | that player may pay … | 4 | 4 | 0 | Power Leak, Mind Whip, Fraying Line |
| 42 | MISSING CONTINUOUS EFFECT | Equipped creature gets ±N/±N and has … | 4 | 2 | 0 | Dire Flail // Dire Blunderbuss, Pin Collection, Spy Kit |
| 43 | MISSING SELECTOR | target aura attached | 4 | 2 | 0 | Enchantment Alteration, Kitsune Mystic // Autumn-Tail, Kitsune Sage, Simic Guildmage |
| 44 | MISSING EFFECT | create a n/n green … | 4 | 1 | 0 | Slime Against Humanity, Viral Spawning, Printlifter Ooze |
| 45 | MISSING EFFECT | if n … | 4 | 1 | 0 | Extraordinary Journey, Krovikan Vampire, Hot Pursuit |
| 46 | MISSING MECHANIC | cumulative upkeep | 4 | 1 | 0 | Jötun Grunt, Thought Lash, Karplusan Minotaur |
| 47 | MISSING EFFECT | an opponent chooses n … | 4 | 0 | 0 | Fatal Lore, Library of Lat-Nam, Misfortune |
| 48 | UNSUPPORTED ORACLE PATTERN | As ~ enters, … | 3 | 1 | 3 | The Mimeoplasm, Deadpool, Trading Card, Pramikon, Sky Rampart |
| 49 | MISSING CONTINUOUS EFFECT | You may have ~ enter as … | 3 | 3 | 2 | The Master, Formed Anew, Hulking Metamorph, The Fourteenth Doctor |
| 50 | MISSING EFFECT | reveal cards from the … | 3 | 3 | 2 | Sanar, Innovative First-Year, Aurora Awakener, Dack Fayden, Helping Hand |

## Top Commander features to implement next

Ranked by pod cards, pod commanders, cards for which it is the only missing piece, then Commander cards needing it.

| # | Feature | Kind | Pod cards | Commander cards | Only missing piece for | Examples |
|---|---|---|---|---|---|---|
| 1 | template:When ~ enters, you get {M}, then you may put a sticker on a nonland permanent you own. | triggered | 0 | 9 | 7 | Aerialephant, Minotaur de Force, Stiltstrider |
| 2 | template:−N: You get an emblem with “…” | loyalty | 0 | 6 | 4 | Ob Nixilis of the Black Oath, Dack Fayden, Karn, Living Legacy |
| 3 | mana:ability | engine | 0 | 6 | 3 | Benthic Explorers, Ice Cauldron, Jeweled Amulet |
| 4 | template:While an opponent is choosing targets as part of casting a spell they control or activating an ability they control, that player must choose at least N Flagbearer on the battlefield if able. | static | 0 | 3 | 3 | Coalition Flag, Coalition Honor Guard, Standard Bearer |
| 5 | template:Equipped creature has “…” | continuous | 0 | 3 | 2 | Toralf, God of Fury // Toralf's Hammer, Razor Boomerang, Shuriken |
| 6 | template:Enchanted creature has “…” | continuous | 0 | 2 | 2 | Animal Friend, Bewitching Leechcraft |
| 7 | template:Equipped creature gets ±N/±N and has “…” | continuous | 0 | 2 | 2 | Dire Flail // Dire Blunderbuss, The Dominion Bracelet |
| 8 | template:If enchanted land would be destroyed, instead sacrifice ~ and that land gains indestructible until end of turn. | replacement | 0 | 2 | 2 | Crackling Emergence, Harmonious Emergence |
| 9 | template:If ~ is your commander, choose a color before the game begins. ~ is the chosen color. | static | 0 | 2 | 2 | Faceless One, The Prismatic Piper |
| 10 | template:If ~ would enter, sacrifice N untapped lands instead. If you do, put ~ onto the battlefield. If you don't, put it into its owner's graveyard. | replacement | 0 | 2 | 2 | Lotus Vale, Scorched Ruins |
| 11 | template:Return the top creature card of your graveyard to the battlefield. That creature gains haste until end of turn. Exile it at the beginning of the next end step. | spell_effect | 0 | 2 | 2 | Corpse Dance, Shallow Grave |
| 12 | template:{M}, {M}: Tap target creature you control and target creature of an opponent's choice they control. Those creatures fight each other. | activated | 0 | 2 | 2 | Arena, Magus of the Arena |
| 13 | template:~ enters with N ±N/±N counter(s) on it, where N is the highest number you noted for cards named ~. | replacement | 0 | 2 | 2 | Pyretic Hunter, Lurking Automaton |
| 14 | template:As an additional cost to cast ~, waterbend {M}. | additional_cost | 0 | 5 | 1 | Foggy Swamp Visions, Waterbender's Restoration, Benevolent River Spirit |
| 15 | keyword:cumulative upkeep | keyword | 0 | 4 | 1 | Jötun Grunt, Thought Lash, Karplusan Minotaur |
| 16 | template:~ enters under the control of an opponent of your choice. | static | 0 | 4 | 1 | Captive Audience, Xantcha, Sleeper Agent, Abby, Merciless Soldier |
| 17 | keyword:splice | keyword | 0 | 3 | 1 | Fell Beast's Shriek, Roar of Jukai, Overblaze |
| 18 | template:Each creature you control has “…” | continuous | 0 | 2 | 1 | Tyvar the Bellicose, Tazri, Stalwart Survivor |
| 19 | engine:planar_roll_payment | engine | 0 | 1 | 1 | Night Shift of the Living Dead |
| 20 | keyword:flashback | keyword | 0 | 1 | 1 | Light Up the Night |
| 21 | template:+N: Surveil N. If you put a noncreature, nonland card into your graveyard this way, put that card into your hand. | loyalty | 0 | 1 | 1 | Chandra, Chill of Compliance |
| 22 | template:+N: Until your next turn, whenever N creature(s) deals combat damage to ~, destroy that creature. | loyalty | 0 | 1 | 1 | Vraska the Unseen |
| 23 | template:A player who controls more permanents than each other player can't play lands or cast artifact, creature, or enchantment spells. That player may sacrifice N permanent(s) of their choice for that player to ignore this effect until end of turn. | restriction | 0 | 1 | 1 | Damping Engine |
| 24 | template:Aberrant Tinkering — When ~ enters and at the beginning of your upkeep, each Horror you control gains all activated abilities of target artifact an opponent controls until end of turn. You may spend blue mana as though it were mana of any color to activate those abilities. | triggered | 0 | 1 | 1 | Grell Philosopher |
| 25 | template:Activated abilities of nontoken Rebels cost an additional “…” to activate. | static | 0 | 1 | 1 | Brutal Suppression |
| 26 | template:Activated abilities of sources with the chosen name cost {M} more to activate. | cost_modifier | 0 | 1 | 1 | Skyseer's Chariot |
| 27 | template:After the second main phase this turn, there's an additional combat phase followed by an additional main phase. At the beginning of that combat, untap all creatures that attacked this turn. | spell_effect | 0 | 1 | 1 | World at War |
| 28 | template:After you roll a die, you may remove a ±N/±N counter(s) from ~. If you do, increase or decrease the result by N. | static | 0 | 1 | 1 | Xenosquirrels |
| 29 | template:All Slivers have “…” | replacement | 0 | 1 | 1 | Pulmonic Sliver |
| 30 | template:All creatures can attack your opponents and planeswalkers your opponents control as though those creatures had haste. | static | 0 | 1 | 1 | Frenzied Saddlebrute |
| 31 | template:Arcane Life-support — If you would lose the game, instead exile ~ and your life total becomes N. | replacement | 0 | 1 | 1 | The Golden Throne |
| 32 | template:Armour of Shrieking Souls — When ~ dies, exile it and choose target creature an opponent controls. When that creature leaves the battlefield, return ~ from exile to the battlefield under its owner's control. | triggered | 0 | 1 | 1 | Lucius the Eternal |
| 33 | template:As a historic permanent you control enters, it becomes a N/N Dinosaur creature in addition to its other types. | static | 0 | 1 | 1 | Displaced Dinosaurs |
| 34 | template:As an additional cost to cast creature spells, you may pay any amount of mana. If you do, that creature enters with that many additional ±N/±N counter(s) on it. | replacement | 0 | 1 | 1 | Chorus of the Conclave |
| 35 | template:As an additional cost to cast ~, sacrifice half the lands you control, rounded up. | additional_cost | 0 | 1 | 1 | Tectonic Split |
| 36 | template:As long as an opponent controls N creature(s) with flying not named ~, ~ has flying. The same is true for first strike, trample, and protection from any color. | continuous | 0 | 1 | 1 | Escaped Shapeshifter |
| 37 | template:As long as another player controls enchanted creature, it can't attack or block. Otherwise, ~ has umbra armor. | restriction | 0 | 1 | 1 | Dog Umbra |
| 38 | template:As long as enchanted artifact isn't N creature(s), it's an artifact creature with power and toughness each equal to its mana value. | static | 0 | 1 | 1 | Animate Artifact |
| 39 | template:As long as enchanted creature is red, it loses all abilities. | continuous | 0 | 1 | 1 | Ray of Frost |
| 40 | template:As long as the top card of your graveyard is N creature(s) card, ~ has the full text of that card and has the text “…” | continuous | 0 | 1 | 1 | Volrath's Shapeshifter |
| 41 | template:As long as ~ is enchanted, equipped, and has N counter(s) on it, ~ has “…” | continuous | 0 | 1 | 1 | Kosei, Penitent Warlord |
| 42 | template:As long as ~ is in your graveyard, each Human creature you control enters with an additional ±N/±N counter(s) on it. | replacement | 0 | 1 | 1 | Dearly Departed |
| 43 | template:As long as ~ is in your graveyard, if you would learn, you may instead return ~ to the battlefield. | replacement | 0 | 1 | 1 | Retriever Phoenix |
| 44 | template:As long as ~ is untapped, noncreature artifacts you control can't be enchanted, they have indestructible, and other players can't gain control of them. This effect doesn't remove Auras already attached to those artifacts. | restriction | 0 | 1 | 1 | Guardian Beast |
| 45 | template:As you cascade, you may put N land(s) card from among the exiled cards onto the battlefield tapped. | static | 0 | 1 | 1 | Averna, the Chaos Bloom |
| 46 | template:As ~ enters or is turned face up, put N ±N/±N counter(s) on it, where N is the number of other creatures you control. | replacement | 0 | 1 | 1 | Crowd-Control Warden |
| 47 | template:As ~ enters or is turned face up, you may choose another creature on the battlefield. If you do, until ~ is turned face down, it becomes a copy of that creature, except it has “…” | replacement | 0 | 1 | 1 | Vesuvan Shapeshifter |
| 48 | template:As ~ enters, choose N creature(s) you control it could be attached to. If you do, it enters attached to that creature. | replacement | 0 | 1 | 1 | Grifter's Blade |
| 49 | template:As ~ enters, discard any number of creature cards. It enters with a flying counter on it if N card(s) discarded this way has flying. The same is true for first strike, double strike, deathtouch, hexproof, haste, indestructible, lifelink, menace, reach, trample, and vigilance. | replacement | 0 | 1 | 1 | Indominus Rex, Alpha |
| 50 | template:As ~ enters, exile N creature(s) cards from your graveyard. If you can't, put ~ into its owner's graveyard instead of onto the battlefield. For each creature card exiled this way, ~ enters with a ±N/±N, ±N/±N, or ±N/±N counter(s) on it. | replacement | 0 | 1 | 1 | Frankenstein's Monster |
| 51 | template:As ~ enters, put a phylactery counter on an artifact you control. | replacement | 0 | 1 | 1 | Phylactery Lich |
| 52 | template:As ~ enters, remove all counters from all permanents. ~ enters with a ±N/±N counter(s) on it for each counter removed this way. | replacement | 0 | 1 | 1 | Thief of Blood |
| 53 | template:As ~ enters, remove all counters from any number of artifacts, creatures, and enchantments. ~ enters with N ±N/±N counter(s) on it, where N is twice the number of counters removed this way. | replacement | 0 | 1 | 1 | Sin, Unending Cataclysm |
| 54 | template:As ~ enters, sacrifice any number of creatures. ~'s power becomes the total power of those creatures and its toughness becomes their total toughness. | replacement | 0 | 1 | 1 | Dracoplasm |
| 55 | template:As ~ enters, sacrifice any number of permanents. ~ enters with that many ±N/±N counter(s) on it. | replacement | 0 | 1 | 1 | Shimatsu the Bloodcloaked |
| 56 | template:As ~ enters, you may exile N creature(s) cards from graveyards. If you do, it enters as a copy of N of those cards with a number of additional ±N/±N counter(s) on it equal to the power of the other card. | static | 0 | 1 | 1 | The Mimeoplasm |
| 57 | template:As ~ enters, you may put N card(s) your opponents own from exile into their owners' graveyards. If you do, ~ enters with N ±N/±N counter(s) on it. | replacement | 0 | 1 | 1 | Ulamog's Despoiler |
| 58 | template:As ~ enters, you may reveal any number of other artifact cards from your hand. ~ enters with a ±N/±N counter(s) on it for each card revealed this way. | replacement | 0 | 1 | 1 | Arsenal Thresher |
| 59 | template:As ~ is turned face up, you may attach it to N creature(s). | static | 0 | 1 | 1 | Gift of Doom |
| 60 | template:As ~ transforms into ~, attach it to a player. | static | 0 | 1 | 1 | Curse of Leeches // Leeching Lurker |

## Coverage by card type

| Type | FULL | PARTIAL | REVIEW | MANUAL |
|---|---|---|---|---|
| Land | 1197 | 15 | 0 | 0 |
| Creature | 17314 | 607 | 0 | 0 |
| Enchantment | 3422 | 225 | 0 | 0 |
| Instant | 3628 | 126 | 0 | 0 |
| Sorcery | 3405 | 163 | 0 | 0 |
| Artifact | 3404 | 189 | 0 | 0 |
| Planeswalker | 270 | 41 | 0 | 0 |
| Battle | 28 | 8 | 0 | 0 |

## Rules features in the pool (ability lines)

triggered 14947, keyword 14550, spell_effect 8905, activated 7691, continuous 4094, static 2138, mana_ability 2042, replacement 1965, restriction 1461, loyalty 882, prevention 318, additional_cost 307, cost_modifier 278, characteristic_defining 247, permission 232, alternative_cost 179

# Commander rules coverage

Card data: Scryfall `2026-09-28T21:01:54.353+00:00` · Comprehensive Rules 2026-09-25 · rules engine v2 · generated 2026-09-29 19:49

Only cards that are **legal in Commander today** count. Banned cards (83) are COMMANDER_BANNED and excluded.

## Commander coverage

Commander-legal cards: **32116**

| Level | Cards | Share |
|---|---|---|
| FULL | 7768 | 24.2% |
| PARTIAL | 24300 | 75.7% |
| REVIEW | 0 | 0.0% |
| MANUAL | 48 | 0.1% |

Possible commanders (CR 903.3/903.3a, incl. Backgrounds): **3501** — FULL 269, PARTIAL 3232, REVIEW 0, MANUAL 0

## Pod coverage

No pod decks in the inventory yet (`python -m tools.rules_inventory`); the queue below is ranked by Commander-legal cards unlocked.

## Coverage quality

- Ability features (lines, keywords, play/cast/combat) across Commander-legal cards: 113346
- Automated: 77748 (68.6%) · unrecognized clauses: 35598
- Oracle text classified (automated, or sorted into a concrete missing capability): 97.1% · unclassified clauses: 3269
- Distinct missing-capability clusters: 9313

## Missing capabilities by category

| Category | Cards affected | Clauses |
|---|---|---|
| MISSING EFFECT | 11381 | 13628 |
| MISSING TRIGGER EVENT | 3845 | 4034 |
| MISSING SELECTOR | 3764 | 3990 |
| MISSING CONTINUOUS EFFECT | 2824 | 3001 |
| UNSUPPORTED ORACLE PATTERN | 2480 | 3269 |
| MISSING MECHANIC | 2002 | 2065 |
| MISSING COST | 1761 | 1841 |
| MISSING REPLACEMENT PATTERN | 1399 | 1438 |
| MISSING RESTRICTION | 962 | 1008 |
| MISSING COST / PERMISSION RULE | 935 | 955 |
| MANA ABILITY WORDING | 367 | 369 |

## Highest-payoff clusters

Ranked by pod cards, pod commanders, possible commanders affected, cards it alone would unlock, then all Commander cards needing it.

| # | Category | Cluster | Commanders | Only missing piece for | Commander cards | Examples |
|---|---|---|---|---|---|---|
| 1 | MISSING EFFECT | pay {m} … | 65 | 179 | 256 | Labyrinth Adversary, Minion Reflector, Giant's Amulet |
| 2 | MISSING EFFECT | draw n … | 61 | 190 | 591 | Errand-Rider of Gondor, Heal, Grip of Amnesia |
| 3 | MISSING EFFECT | put a ±n/±n counter(s) … | 58 | 137 | 215 | Yorvo, Lord of Garenbrig, Gollum, Silent Slinker // Meager Meal, Ent-Draught Basin |
| 4 | MISSING EFFECT | choose n … | 58 | 46 | 548 | Road of Return, Saheeli's Artistry, Eldrazi Confluence |
| 5 | MISSING MECHANIC | ward | 47 | 10 | 97 | Tyranid Harridan, Grey Host Reinforcements, Kwia Vigorbloom |
| 6 | UNSUPPORTED ORACLE PATTERN | planeswalker | 35 | 0 | 311 | Tamiyo, Compleated Sage, Jace, the Perfected Mind, Huatli, Dinosaur Knight |
| 7 | MISSING EFFECT | look at the top … | 34 | 122 | 198 | Harald, King of Skemfar, Lantern of Revealing, Ponder |
| 8 | MISSING EFFECT | create n … | 32 | 122 | 245 | Summon the School, Cogwork Assembler, Endless Evil |
| 9 | MISSING CONTINUOUS EFFECT | ~ gets ±N/±N for each … | 32 | 54 | 115 | Nim Lasher, Benalish Honor Guard, Anya, Merciless Angel |
| 10 | MISSING SELECTOR | target | 29 | 198 | 364 | Cinder Elemental, Archangel of Wrath, Granger Guildmage |
| 11 | MISSING CONTINUOUS EFFECT | ~'s power and toughness are each … | 28 | 59 | 127 | Eluge, the Shoreless Sea, Flora Colossus, Revenant |
| 12 | MISSING EFFECT | exile the top card … | 28 | 37 | 92 | Moonring Mirror, Mezzio Mugger, Etali, Primal Storm |
| 13 | MISSING TRIGGER EVENT | When ~ enters | 26 | 10 | 26 | Kiora of Fire and Ashes, Sharuum the Hegemon, Phage the Untouchable |
| 14 | MISSING SELECTOR | target creature card | 24 | 115 | 181 | Hua Tuo, Honored Physician, Puppeteer Clique, Metamorphosis Fanatic |
| 15 | MISSING EFFECT | put n … | 23 | 74 | 139 | Black Sun's Zenith, Breaking // Entering, Mind Raker |
| 16 | MISSING EFFECT | transform ~ … | 23 | 15 | 57 | Ulvenwald Captive // Ulvenwald Abomination, Seraph of New Capenna // Seraph of New Phyrexia, Sun-Blessed Guardian // Furnace-Blessed Conqueror |
| 17 | UNSUPPORTED ORACLE PATTERN | As long as your devotion to … | 22 | 5 | 22 | Phenax, God of Deception, Erebos, God of the Dead, Thassa, Deep-Dwelling |
| 18 | UNSUPPORTED ORACLE PATTERN | You may look at the top … | 22 | 2 | 45 | One with the Multiverse, The Lunar Whale, Cemetery Illuminator |
| 19 | MISSING CONTINUOUS EFFECT | During your turn, … | 21 | 35 | 74 | Pompous Gadabout, Long-Lost Lances, Fresh-Faced Recruit |
| 20 | MISSING TRIGGER EVENT | Whenever ~ attacks | 21 | 10 | 21 | Durnan of the Yawning Portal, Acererak the Archlich, Edgar Markov |
| 21 | MISSING EFFECT | ~ deals n … | 19 | 225 | 376 | Deem Worthy, End-Blaze Epiphany, Harvest Pyre |
| 22 | MISSING SELECTOR | target creatures | 19 | 166 | 309 | Ravenous Gigantotherium, Fire Covenant, Amazing Acrobatics |
| 23 | MISSING EFFECT | until end of turn … | 19 | 138 | 217 | Divergent Growth, Doorman, Strength of Will |
| 24 | UNSUPPORTED ORACLE PATTERN | ~ costs {M} less to cast … | 19 | 36 | 71 | Bedlam Reveler, Gargantuan Leech, Hamza, Guardian of Arashin |
| 25 | MISSING EFFECT | if n … | 19 | 28 | 54 | Hot Pursuit, Kotis, Sibsig Champion, Zombie Ogre |
| 26 | MISSING TRIGGER EVENT | When you cast ~ | 18 | 22 | 80 | Empyrial Storm, The Fourteenth Doctor, Ulamog, the Ceaseless Hunger |
| 27 | MISSING EFFECT | mill n … | 17 | 57 | 98 | Sparring Dummy, Beluna Grandsquall // Seek Thrills, Cache Grab |
| 28 | MISSING EFFECT | discard n … | 17 | 39 | 79 | Keldon Raider, Witch's Mark, Seasoned Pyromancer |
| 29 | MISSING CONTINUOUS EFFECT | Commander creatures you own have “…” | 17 | 17 | 17 | Dungeon Delver, Noble Heritage, Acolyte of Bahamut |
| 30 | MISSING EFFECT | exile ~ … | 17 | 10 | 57 | Stenn, Paranoid Partisan, Woodland Guidance, Teferi's Protection |
| 31 | MISSING COST | {M}, Sacrifice another creature | 16 | 32 | 51 | Sanguine Spy, Skyclave Shadowcat, Phyrexian Warhorse |
| 32 | MISSING EFFECT | search your library for … | 15 | 153 | 255 | Safewright Quest, Thunderherd Migration, Squadron Hawk |
| 33 | MISSING CONTINUOUS EFFECT | ~'s power is equal to the … | 15 | 27 | 67 | Uurg, Spawn of Turg, Snow Villiers, Nethergoyf |
| 34 | UNSUPPORTED ORACLE PATTERN | As ~ enters, … | 15 | 1 | 19 | Stenn, Paranoid Partisan, Arachne, Psionic Weaver, Pramikon, Sky Rampart |
| 35 | UNSUPPORTED ORACLE PATTERN | More Than Meets the Eye {M} | 15 | 0 | 15 | Optimus Prime, Hero // Optimus Prime, Autobot Leader, Megatron, Tyrant // Megatron, Destructive Force, Jetfire, Ingenious Scientist // Jetfire, Air Guardian |
| 36 | MISSING COST | {M}, {M}, Discard N card(s) | 14 | 69 | 79 | Arc Mage, Sparkspitter, Instigator |
| 37 | MISSING EFFECT | create a n/n white … | 14 | 30 | 66 | Kaya, Spirits' Justice, Empyrial Storm, Archangel Elspeth |
| 38 | MISSING TRIGGER EVENT | Whenever you cast your second spell each turn | 14 | 22 | 34 | Sunstar Lightsmith, Wanda's Vision, Kraum, Violent Cacophony |
| 39 | MISSING MECHANIC | sneak | 14 | 11 | 27 | Turncoat Kunoichi, Michelangelo, Improviser, Donatello's Technique |
| 40 | MISSING MECHANIC | firebending | 14 | 5 | 22 | Fire Sages, Loyal Fire Sage, Jeong Jeong, the Deserter |
| 41 | MISSING MECHANIC | partner | 14 | 4 | 24 | Lore Weaver, Blaring Captain, Rory Williams |
| 42 | UNSUPPORTED ORACLE PATTERN | • Put a ±N/±N counter(s) on … | 14 | 0 | 38 | Bejeweled Warg, Trusty Retriever, Inspired Inventor |
| 43 | MISSING EFFECT | if ~ … | 13 | 55 | 114 | Warden of the First Tree, Blinkmoth Urn, Mad Dog |
| 44 | MISSING EFFECT | create a n/n black … | 13 | 26 | 54 | Queen Brahne, Grist, the Hunger Tide, Mysidian Elder |
| 45 | MISSING EFFECT | create a n/n red … | 13 | 23 | 58 | Prosperity Tycoon, Ertha Jo, Frontier Mentor, Nesting Dragon |
| 46 | MISSING COST | {M}, Sacrifice an artifact | 13 | 20 | 32 | Embraal Gear-Smasher, Orcish Mechanics, Lobelia, Defender of Bag End |
| 47 | UNSUPPORTED ORACLE PATTERN | Living metal | 13 | 0 | 13 | Optimus Prime, Hero // Optimus Prime, Autobot Leader, Megatron, Tyrant // Megatron, Destructive Force, Jetfire, Ingenious Scientist // Jetfire, Air Guardian |
| 48 | MISSING COST | {M}, Sacrifice N creature(s) | 12 | 56 | 75 | Ruthless Knave, Tymaret, the Murder King, Starved Rusalka |
| 49 | MISSING RESTRICTION | ~ can't be blocked by creatures … | 12 | 26 | 56 | Lydia Frye, Pompous Gadabout, Ghost of Ramirez DePietro |
| 50 | MISSING SELECTOR | target equipment | 12 | 16 | 25 | Stolen Uniform, Shagrat, Loot Bearer, Thor, God of Thunder |
| 51 | UNSUPPORTED ORACLE PATTERN | Power-up — {M}: Put N ±N/±N … | 12 | 12 | 19 | Thanos, the Mad Titan, Shang-Chi, Martial Mentor, Hulk, Gamma Goliath |
| 52 | MISSING EFFECT | create a n/n green … | 11 | 40 | 92 | Rhonas's Last Stand, Kasmina, Enigma Sage, Choco-Comet |
| 53 | MISSING EFFECT | add {m} … | 11 | 36 | 64 | Akki Rockspeaker, Brightstone Ritual, Infernal Plunge |
| 54 | MISSING SELECTOR | target instant or sorcery card | 11 | 17 | 38 | Ogre Battlecaster, Impulsivity, Kishla Trawlers |
| 55 | MISSING EFFECT | exile up to n … | 11 | 15 | 27 | Salvation Swan, Liminal Hold, S.H.I.E.L.D. Flying Car |
| 56 | MISSING TRIGGER EVENT | Whenever you cast a historic spell | 11 | 15 | 19 | Serra Disciple, Cabal Paladin, Glóin, Dwarf Emissary |
| 57 | MISSING COST / PERMISSION RULE | You may cast ~ from your … | 11 | 10 | 27 | Marang River Prowler, Quilled Greatwurm, Gravecrawler |
| 58 | MISSING EFFECT | earthbend n … | 11 | 10 | 27 | Earth Village Ruffians, Bumi, Unleashed, Badgermole |
| 59 | MISSING COST / PERMISSION RULE | Once during each of your turns, … | 11 | 7 | 15 | Kotis, Sibsig Champion, One with the Multiverse, Jacob Hauken, Inspector // Hauken's Insight |
| 60 | MISSING EFFECT | if you've cast a … | 11 | 5 | 12 | H.E.R.B.I.E., Lovable Robot, Invisible Woman, Alicia Masters, Skilled Sculptor |
| 61 | MISSING EFFECT | target creature you control … | 10 | 121 | 179 | Blessed Defiance, Hard-Hitting Question, Crowd of True Believers |
| 62 | MISSING COST | {M}, Discard N card(s) | 10 | 46 | 79 | Viashino Lashclaw, Haunted Dead, Junk Golem |
| 63 | MISSING EFFECT | exile the top n … | 10 | 19 | 54 | Duplicity, Crossover Collaboration, Ral, Monsoon Mage // Ral, Leyline Prodigy |
| 64 | MISSING RESTRICTION | ~ can't attack or block unless … | 10 | 13 | 23 | Sab-Sunen, Luxa Embodied, Relic Golem, Hollow Warrior |
| 65 | MISSING EFFECT | another target … | 10 | 12 | 23 | Hemosymbic Mite, Bazaar Krovod, Syr Faren, the Hengehammer |
| 66 | MISSING EFFECT | return it to the … | 10 | 9 | 22 | Bronzehide Lion, Optimus Prime, Hero // Optimus Prime, Autobot Leader, Yedora, Grave Gardener |
| 67 | MISSING TRIGGER EVENT | Whenever ~ deals combat damage to a player | 10 | 1 | 10 | Phage the Untouchable, Ezio Auditore da Firenze, Daxos of Meletis |
| 68 | MISSING EFFECT | return ~ … | 9 | 61 | 90 | Dragon Fangs, Dragon Scales, Eternal Dragon |
| 69 | MISSING EFFECT | choose target … | 9 | 60 | 74 | Arcbond, Deglamer, Wreck Hunter |
| 70 | MISSING EFFECT | gain control of target … | 9 | 52 | 81 | Sauron, the Lidless Eye, New Blood, Unwilling Recruit |
| 71 | MISSING EFFECT | if you control n … | 9 | 48 | 73 | Discourtesy Clerk, Boundary Lands Ranger, Psemilla, Meletian Poet |
| 72 | MISSING EFFECT | reveal the top card … | 9 | 31 | 45 | Counterbalance, Sorin, Grim Nemesis, Sapling of Colfenor |
| 73 | MISSING CONTINUOUS EFFECT | You have no maximum hand size | 9 | 7 | 23 | Nyssa of Traken, Curiosity Crafter, Wizard Class |
| 74 | MISSING EFFECT | double the number of … | 9 | 7 | 19 | Primordial Hydra, The Millennium Calendar, Paradox Zone |
| 75 | UNSUPPORTED ORACLE PATTERN | Web-slinging {M} | 9 | 4 | 9 | Scarlet Spider, Ben Reilly, Arachne, Psionic Weaver, Spider-Man, Brooklyn Visionary |
| 76 | MISSING CONTINUOUS EFFECT | ~ has indestructible as long as … | 9 | 2 | 12 | Crew Captain, War Historian, Havi, the All-Father |
| 77 | MISSING MECHANIC | companion | 9 | 1 | 9 | Lutri, the Spellchaser, Gyruda, Doom of Depths, Lurrus of the Dream-Den |
| 78 | UNSUPPORTED ORACLE PATTERN | • ~ deals N damage to … | 9 | 0 | 18 | Arbalest Engineers, Tectonic Giant, Umaro, Raging Yeti |
| 79 | UNSUPPORTED ORACLE PATTERN | Storied | 9 | 0 | 9 | Balin, Loremaster, Dáin, Lord of the Iron Hills, Ori, Keeper of Songs |
| 80 | MISSING EFFECT | reveal the top n … | 8 | 53 | 72 | Green Sun's Twilight, Benefaction of Rhonas, Karn, Scion of Urza |

## Largest clusters (Commander cards affected)

| # | Category | Cluster | Commander cards | Only missing piece for | Commanders | Examples |
|---|---|---|---|---|---|---|
| 1 | MISSING EFFECT | draw n … | 591 | 190 | 61 | Errand-Rider of Gondor, Heal, Grip of Amnesia |
| 2 | MISSING EFFECT | choose n … | 548 | 46 | 58 | Road of Return, Saheeli's Artistry, Eldrazi Confluence |
| 3 | MISSING EFFECT | ~ deals n … | 376 | 225 | 19 | Deem Worthy, End-Blaze Epiphany, Harvest Pyre |
| 4 | MISSING SELECTOR | target | 364 | 198 | 29 | Cinder Elemental, Archangel of Wrath, Granger Guildmage |
| 5 | MISSING COST / PERMISSION RULE | As an additional cost to cast … | 312 | 34 | 6 | Thunderherd Migration, Mind Extraction, Harvest Pyre |
| 6 | UNSUPPORTED ORACLE PATTERN | planeswalker | 311 | 0 | 35 | Tamiyo, Compleated Sage, Jace, the Perfected Mind, Huatli, Dinosaur Knight |
| 7 | MISSING SELECTOR | target creatures | 309 | 166 | 19 | Ravenous Gigantotherium, Fire Covenant, Amazing Acrobatics |
| 8 | MISSING EFFECT | pay {m} … | 256 | 179 | 65 | Labyrinth Adversary, Minion Reflector, Giant's Amulet |
| 9 | MISSING EFFECT | search your library for … | 255 | 153 | 15 | Safewright Quest, Thunderherd Migration, Squadron Hawk |
| 10 | MISSING EFFECT | create n … | 245 | 122 | 32 | Summon the School, Cogwork Assembler, Endless Evil |
| 11 | MISSING REPLACEMENT PATTERN | As ~ enters, … | 237 | 47 | 4 | Kindred Discovery, Utopia Sprawl, Game Trail |
| 12 | MISSING EFFECT | destroy target … | 231 | 131 | 7 | Kalitas, Bloodchief of Ghet, Misfortune's Gain, Raze |
| 13 | MISSING MECHANIC | kicker | 224 | 0 | 7 | Strength of Night, Goblin Barrage, Archangel of Wrath |
| 14 | MISSING EFFECT | until end of turn … | 217 | 138 | 19 | Divergent Growth, Doorman, Strength of Will |
| 15 | MISSING EFFECT | put a ±n/±n counter(s) … | 215 | 137 | 58 | Yorvo, Lord of Garenbrig, Gollum, Silent Slinker // Meager Meal, Ent-Draught Basin |
| 16 | MISSING EFFECT | look at the top … | 198 | 122 | 34 | Harald, King of Skemfar, Lantern of Revealing, Ponder |
| 17 | MISSING EFFECT | target creature gets ±n/±n … | 190 | 106 | 2 | Stern Marshal, Spontaneous Flight, Rig for War |
| 18 | MISSING SELECTOR | target creature card | 181 | 115 | 24 | Hua Tuo, Honored Physician, Puppeteer Clique, Metamorphosis Fanatic |
| 19 | MISSING EFFECT | target creature you control … | 179 | 121 | 10 | Blessed Defiance, Hard-Hitting Question, Crowd of True Believers |
| 20 | MISSING EFFECT | put n … | 139 | 74 | 23 | Black Sun's Zenith, Breaking // Entering, Mind Raker |
| 21 | MISSING CONTINUOUS EFFECT | ~'s power and toughness are each … | 127 | 59 | 28 | Eluge, the Shoreless Sea, Flora Colossus, Revenant |
| 22 | MISSING EFFECT | exile target … | 121 | 77 | 3 | Astarion's Thirst, Deadly Rollick, Tawnos's Coffin |
| 23 | MISSING CONTINUOUS EFFECT | ~ gets ±N/±N for each … | 115 | 54 | 32 | Nim Lasher, Benalish Honor Guard, Anya, Merciless Angel |
| 24 | MISSING EFFECT | if ~ … | 114 | 55 | 13 | Warden of the First Tree, Blinkmoth Urn, Mad Dog |
| 25 | MISSING EFFECT | you gain n … | 108 | 61 | 7 | Shu Farmer, Essence Pulse, Ajani Resolute |
| 26 | MANA ABILITY WORDING | {M}, … | 108 | 74 | 6 | Saltcrusted Steppe, Cabal Stronghold, Interplanar Beacon |
| 27 | MISSING SELECTOR | target player or planeswalker | 101 | 62 | 3 | Goblin Barrage, Scorching Missile, Consuming Sinkhole |
| 28 | MISSING EFFECT | mill n … | 98 | 57 | 17 | Sparring Dummy, Beluna Grandsquall // Seek Thrills, Cache Grab |
| 29 | MISSING CONTINUOUS EFFECT | ~ gets ±N/±N as long as … | 98 | 89 | 1 | Sulam Djinn, Zanam Djinn, Isleback Spawn |
| 30 | MISSING MECHANIC | ward | 97 | 10 | 47 | Tyranid Harridan, Grey Host Reinforcements, Kwia Vigorbloom |
| 31 | MISSING EFFECT | exile the top card … | 92 | 37 | 28 | Moonring Mirror, Mezzio Mugger, Etali, Primal Storm |
| 32 | MISSING EFFECT | create a n/n green … | 92 | 40 | 11 | Rhonas's Last Stand, Kasmina, Enigma Sage, Choco-Comet |
| 33 | MISSING EFFECT | return ~ … | 90 | 61 | 9 | Dragon Fangs, Dragon Scales, Eternal Dragon |
| 34 | MISSING SELECTOR | target card | 90 | 49 | 4 | Funeral Pyre, Barkform Harvester, Carrion Locust |
| 35 | MISSING EFFECT | return target … | 84 | 46 | 1 | Surging Aether, Perilous Voyage, Geistwave |
| 36 | MISSING EFFECT | gain control of target … | 81 | 52 | 9 | Sauron, the Lidless Eye, New Blood, Unwilling Recruit |
| 37 | MISSING TRIGGER EVENT | When you cast ~ | 80 | 22 | 18 | Empyrial Storm, The Fourteenth Doctor, Ulamog, the Ceaseless Hunger |
| 38 | MISSING EFFECT | discard n … | 79 | 39 | 17 | Keldon Raider, Witch's Mark, Seasoned Pyromancer |
| 39 | MISSING COST | {M}, {M}, Discard N card(s) | 79 | 69 | 14 | Arc Mage, Sparkspitter, Instigator |
| 40 | MISSING COST | {M}, Discard N card(s) | 79 | 46 | 10 | Viashino Lashclaw, Haunted Dead, Junk Golem |
| 41 | MISSING EFFECT | it deals n … | 78 | 60 | 3 | Goblin Chainwhirler, Festering Evil, Unsparing Boltcaster |
| 42 | MISSING COST | {M}, Sacrifice N creature(s) | 75 | 56 | 12 | Ruthless Knave, Tymaret, the Murder King, Starved Rusalka |
| 43 | MISSING CONTINUOUS EFFECT | During your turn, … | 74 | 35 | 21 | Pompous Gadabout, Long-Lost Lances, Fresh-Faced Recruit |
| 44 | MISSING EFFECT | choose target … | 74 | 60 | 9 | Arcbond, Deglamer, Wreck Hunter |
| 45 | MISSING EFFECT | tap target … | 74 | 43 | 3 | Spider-Woman, Secret Agent, Guardian of Tazeem, Gilded Scuttler |
| 46 | MISSING EFFECT | if you control n … | 73 | 48 | 9 | Discourtesy Clerk, Boundary Lands Ranger, Psemilla, Meletian Poet |
| 47 | MISSING EFFECT | reveal the top n … | 72 | 53 | 8 | Green Sun's Twilight, Benefaction of Rhonas, Karn, Scion of Urza |
| 48 | UNSUPPORTED ORACLE PATTERN | ~ costs {M} less to cast … | 71 | 36 | 19 | Bedlam Reveler, Gargantuan Leech, Hamza, Guardian of Arashin |
| 49 | MISSING CONTINUOUS EFFECT | ~'s power is equal to the … | 67 | 27 | 15 | Uurg, Spawn of Turg, Snow Villiers, Nethergoyf |
| 50 | MISSING EFFECT | create a n/n white … | 66 | 30 | 14 | Kaya, Spirits' Justice, Empyrial Storm, Archangel Elspeth |

## Top Commander features to implement next

Ranked by pod cards, pod commanders, cards for which it is the only missing piece, then Commander cards needing it.

| # | Feature | Kind | Pod cards | Commander cards | Only missing piece for | Examples |
|---|---|---|---|---|---|---|
| 1 | mana:ability | engine | 0 | 367 | 233 | Saltcrusted Steppe, Flywheel Racer, The Emperor of Palamecia // The Lord Master of Hell |
| 2 | template:Enchanted creature has “…” | continuous | 0 | 34 | 28 | Ghostly Touch, Immobilizing Ink, Sunbond |
| 3 | template:Enchanted creature gets ±N/±N and has “…” | continuous | 0 | 25 | 21 | Arcane Teachings, Lunarch Mantle, Deviant Glee |
| 4 | template:Commander creatures you own have “…” | continuous | 0 | 21 | 21 | Dungeon Delver, Scion of Halaster, Noble Heritage |
| 5 | keyword:banding | keyword | 0 | 24 | 19 | Nalathni Dragon, Mishra's War Machine, Kjeldoran Escort |
| 6 | keyword:foretell | keyword | 0 | 51 | 18 | The Foretold Soldier, Rise of the Dread Marn, Green Slime |
| 7 | keyword:bestow | keyword | 0 | 42 | 18 | Leafcrown Dryad, Baleful Eidolon, Observant Alseid |
| 8 | template:Equipped creature has “…” | continuous | 0 | 24 | 16 | Field-Tested Frying Pan, Sorcerer's Wand, Fishing Pole |
| 9 | keyword:enchant | keyword | 0 | 67 | 15 | Utopia Sprawl, One with the Stars, Corrupted Roots |
| 10 | keyword:splice | keyword | 0 | 30 | 15 | Evermind, Horobi's Whisper, Desperate Ritual |
| 11 | template:Equipped creature gets ±N/±N and has “…” | continuous | 0 | 25 | 15 | Giant's Amulet, Iconic Shield, Candlestick |
| 12 | keyword:equip | keyword | 0 | 49 | 14 | Bloodthorn Flail, Strong Back, Team Pennant |
| 13 | template:~ enters prepared. | static | 0 | 40 | 14 | Adventurous Eater // Have a Bite, Maelstrom Artisan // Rocket Volley, Fatehold Chronologist // Peer Review |
| 14 | template:{M}: Return ~ from your graveyard to your hand. | activated | 0 | 22 | 14 | The Sound of Drums, Merchant of Many Hats, Convenient Target |
| 15 | template:~ can't be blocked by creatures with power N or less. | restriction | 0 | 32 | 13 | Glinting Creeper, Dread Linnorm // Scale Deflection, Chomping Kavu |
| 16 | keyword:encore | keyword | 0 | 26 | 13 | Impulsivity, Sliver Gravemother, Belonging |
| 17 | keyword:backup | keyword | 0 | 25 | 13 | Saiba Cryptomancer, Chomping Kavu, Consuming Aetherborn |
| 18 | template:Modular N | static | 0 | 23 | 13 | Arcbound Whelp, Arcbound Javelineer, Arcbound Hybrid |
| 19 | template:When ~ enters, attach it to target creature you control. | triggered | 0 | 30 | 12 | Maul of the Skyclaves, Meltstrider's Gear, Bramble Armor |
| 20 | keyword:myriad | keyword | 0 | 23 | 12 | The Master, Multiplied, Sumala Rumblers, Conclave Evangelist |
| 21 | template:All Slivers have “…” | continuous | 0 | 12 | 12 | Magma Sliver, Basal Sliver, Mesmeric Sliver |
| 22 | keyword:warp | keyword | 0 | 31 | 11 | Starbreach Whale, Knight Luminary, Loading Zone |
| 23 | keyword:overload | keyword | 0 | 27 | 11 | Mizzium Skin, Corporeal Projection, Mind Rake |
| 24 | keyword:sneak | keyword | 0 | 27 | 11 | Turncoat Kunoichi, Michelangelo, Improviser, Donatello's Technique |
| 25 | keyword:unleash | keyword | 0 | 15 | 11 | Rakdos Drake, Grim Roustabout, Chaos Imps |
| 26 | template:When ~ enters, you may discard N card(s). If you do, draw N card(s). | triggered | 0 | 15 | 11 | Keldon Raider, Bitter Reunion, Viashino Racketeer |
| 27 | template:Enchanted land has “…” | continuous | 0 | 12 | 11 | Chamber of Manipulation, Discreet Retreat, Farmstead |
| 28 | keyword:ward | keyword | 0 | 97 | 10 | Tyranid Harridan, Grey Host Reinforcements, Kwia Vigorbloom |
| 29 | keyword:ninjutsu | keyword | 0 | 35 | 10 | Higure, the Still Wind, Moonblade Shinobi, Mist-Syndicate Naga |
| 30 | keyword:entwine | keyword | 0 | 32 | 10 | Road of Return, Rain of Rust, Blinding Beam |
| 31 | keyword:offspring | keyword | 0 | 20 | 10 | Splash Lasher, Rust-Shield Rampager, Prosperous Bandit |
| 32 | template:Scavenge {M} | static | 0 | 14 | 10 | Terrus Wurm, Deadbridge Goliath, Dodgy Jalopy |
| 33 | keyword:rampage | keyword | 0 | 12 | 10 | Craw Giant, Balduvian War-Makers, Varchild's War-Riders |
| 34 | template:Threshold — ~ gets ±N/±N as long as there are N or more cards in your graveyard. | continuous | 0 | 12 | 10 | Krosan Beast, Nimble Mongoose, Anurid Barkripper |
| 35 | template:~ enters tapped unless you control N or fewer other lands. | replacement | 0 | 11 | 10 | Concealed Courtyard, Inspiring Vantage, Blackcleave Cliffs |
| 36 | template:~ enters tapped unless a player has N or less life. | replacement | 0 | 10 | 10 | Abandoned Campground, Raucous Carnival, Strangled Cemetery |
| 37 | template:~ enters tapped unless you control N or more basic lands. | replacement | 0 | 10 | 10 | Sodden Verdure, Smoldering Marsh, Vernal Fen |
| 38 | template:~ enters tapped unless you control N or more other lands. | replacement | 0 | 10 | 10 | Rockfall Vale, Stormcarved Coast, Sundown Pass |
| 39 | template:~ enters tapped unless you control a planeswalker. | replacement | 0 | 10 | 10 | Theorix Annex, Stingerquill Annex, Konstrari Annex |
| 40 | template:~ enters tapped unless you have N or more opponents. | replacement | 0 | 10 | 10 | Spire Garden, Sea of Clouds, Bountiful Promenade |
| 41 | keyword:disguise | keyword | 0 | 43 | 9 | Boltbender, Nightdrinker Moroii, Concealed Weapon |
| 42 | keyword:cumulative upkeep | keyword | 0 | 23 | 9 | Varchild's War-Riders, Aboroth, Inner Sanctum |
| 43 | keyword:living weapon | keyword | 0 | 19 | 9 | Nettlecyst, Lashwrithe, Skinwing |
| 44 | keyword:mentor | keyword | 0 | 19 | 9 | Hammer Dropper, Legion Warboss, Tributary Instructor |
| 45 | keyword:prototype | keyword | 0 | 19 | 9 | Goring Warplow, Combat Thresher, Woodcaller Automaton |
| 46 | keyword:extort | keyword | 0 | 17 | 9 | Syndicate Heavy, Tithe Drinker, Kingpin's Pet |
| 47 | keyword:fading | keyword | 0 | 17 | 9 | Parallax Wave, Phyrexian Prowler, Skyshroud Ridgeback |
| 48 | keyword:retrace | keyword | 0 | 17 | 9 | Flame Jab, Monstrify, Waves of Aggression |
| 49 | template:Prevent all combat damage that would be dealt this turn. | prevention | 0 | 14 | 9 | Jaheira's Respite, Fog, Darkness |
| 50 | template:{M}, Sacrifice ~: It deals N damage to any target. | activated | 0 | 12 | 9 | Fireforger's Puzzleknot, Lightning Spear, Pyrite Spellbomb |
| 51 | keyword:evolve | keyword | 0 | 22 | 8 | Adaptive Snapjaw, Shambleshark, Tyranid Prime |
| 52 | keyword:vanishing | keyword | 0 | 20 | 8 | Soultether Golem, Deadly Grub, Reality Acid |
| 53 | template:~'s power and toughness are each equal to the number of lands you control. | characteristic_defining | 0 | 17 | 8 | Flora Colossus, Rubblehulk, Harmonious Grovestrider |
| 54 | keyword:embalm | keyword | 0 | 15 | 8 | Heart-Piercer Manticore, Angel of Sanctions, Anointer Priest |
| 55 | keyword:umbra armor | keyword | 0 | 15 | 8 | Felidar Umbra, Drake Umbra, Hyena Umbra |
| 56 | template:Graft N | static | 0 | 13 | 8 | Cytoplast Manipulator, Sporeback Troll, Vigean Hydropon |
| 57 | template:Whenever ~ deals combat damage to a player, that player discards N card(s). | triggered | 0 | 12 | 8 | Chilling Apparition, Banshee of the Dread Choir, Silent Specter |
| 58 | template:~ can block an additional creature each combat. | static | 0 | 12 | 8 | Selesnya Sagittars, Tangleclaw Werewolf // Fibrous Entangler, Tangleclaw Werewolf // Fibrous Entangler |
| 59 | template:{M}, {M}, Sacrifice ~: It deals N damage to target creature. | activated | 0 | 11 | 8 | Vial of Dragonfire, Flamecast Wheel, Mouth of Ronom |
| 60 | template:Threshold — As long as there are N or more cards in your graveyard, ~ has “…” | continuous | 0 | 9 | 8 | Cephalid Sage, Hunting Grounds, Centaur Chieftain |

## Coverage by card type

| Type | FULL | PARTIAL | REVIEW | MANUAL |
|---|---|---|---|---|
| Creature | 4810 | 13111 | 0 | 0 |
| Artifact | 793 | 2800 | 0 | 0 |
| Enchantment | 513 | 3134 | 0 | 0 |
| Sorcery | 680 | 2888 | 0 | 0 |
| Instant | 928 | 2826 | 0 | 0 |
| Land | 497 | 715 | 0 | 0 |
| Planeswalker | 0 | 311 | 0 | 0 |
| Battle | 0 | 36 | 0 | 0 |

## Rules features in the pool (ability lines)

triggered 14909, keyword 14115, spell_effect 9123, activated 7358, continuous 4014, static 3069, mana_ability 2038, replacement 1966, restriction 1474, loyalty 882, prevention 320, additional_cost 307, cost_modifier 261, characteristic_defining 247, permission 207, alternative_cost 180

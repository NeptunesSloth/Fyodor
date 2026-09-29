# Commander rules coverage

Card data: Scryfall `2026-09-28T21:01:54.353+00:00` · Comprehensive Rules 2026-09-25 · rules engine v2 · generated 2026-09-29 20:12

Only cards that are **legal in Commander today** count. Banned cards (83) are COMMANDER_BANNED and excluded.

## Commander coverage

Commander-legal cards: **32116**

| Level | Cards | Share |
|---|---|---|
| FULL | 7908 | 24.6% |
| PARTIAL | 24160 | 75.2% |
| REVIEW | 0 | 0.0% |
| MANUAL | 48 | 0.1% |

Possible commanders (CR 903.3/903.3a, incl. Backgrounds): **3501** — FULL 286, PARTIAL 3215, REVIEW 0, MANUAL 0

## Pod coverage

No pod decks in the inventory yet (`python -m tools.rules_inventory`); the queue below is ranked by Commander-legal cards unlocked.

## Coverage quality

- Ability features (lines, keywords, play/cast/combat) across Commander-legal cards: 113346
- Automated: 78487 (69.2%) · unrecognized clauses: 34859
- Oracle text classified (automated, or sorted into a concrete missing capability): 97.4% · unclassified clauses: 2952
- Distinct missing-capability clusters: 9154

## Missing capabilities by category

| Category | Cards affected | Clauses |
|---|---|---|
| MISSING EFFECT | 11541 | 13615 |
| MISSING SELECTOR | 3767 | 3981 |
| MISSING TRIGGER EVENT | 3465 | 3640 |
| MISSING CONTINUOUS EFFECT | 2824 | 3001 |
| UNSUPPORTED ORACLE PATTERN | 2183 | 2952 |
| MISSING MECHANIC | 2002 | 2065 |
| MISSING COST | 1761 | 1841 |
| MISSING REPLACEMENT PATTERN | 1397 | 1436 |
| MISSING RESTRICTION | 958 | 1004 |
| MISSING COST / PERMISSION RULE | 935 | 955 |
| MANA ABILITY WORDING | 367 | 369 |

## Highest-payoff clusters

Ranked by pod cards, pod commanders, possible commanders affected, cards it alone would unlock, then all Commander cards needing it.

| # | Category | Cluster | Commanders | Only missing piece for | Commander cards | Examples |
|---|---|---|---|---|---|---|
| 1 | MISSING EFFECT | pay {m} … | 65 | 186 | 263 | Labyrinth Adversary, Minion Reflector, Giant's Amulet |
| 2 | MISSING EFFECT | choose n … | 61 | 47 | 553 | Road of Return, Saheeli's Artistry, Eldrazi Confluence |
| 3 | MISSING EFFECT | draw n … | 58 | 191 | 573 | Errand-Rider of Gondor, Heal, Grip of Amnesia |
| 4 | MISSING EFFECT | put a ±n/±n counter(s) … | 54 | 128 | 196 | Yorvo, Lord of Garenbrig, Gollum, Silent Slinker // Meager Meal, Ent-Draught Basin |
| 5 | MISSING MECHANIC | ward | 47 | 10 | 97 | Tyranid Harridan, Grey Host Reinforcements, Kwia Vigorbloom |
| 6 | MISSING EFFECT | look at the top … | 38 | 144 | 207 | Harald, King of Skemfar, Lantern of Revealing, Ponder |
| 7 | MISSING CONTINUOUS EFFECT | ~ gets ±N/±N for each … | 32 | 54 | 115 | Nim Lasher, Benalish Honor Guard, Anya, Merciless Angel |
| 8 | MISSING SELECTOR | target | 31 | 198 | 350 | Cinder Elemental, Archangel of Wrath, Granger Guildmage |
| 9 | MISSING EFFECT | create n … | 31 | 127 | 239 | Summon the School, Cogwork Assembler, Endless Evil |
| 10 | MISSING EFFECT | exile the top card … | 30 | 37 | 94 | Moonring Mirror, Mezzio Mugger, Etali, Primal Storm |
| 11 | MISSING CONTINUOUS EFFECT | ~'s power and toughness are each … | 28 | 59 | 127 | Eluge, the Shoreless Sea, Flora Colossus, Revenant |
| 12 | MISSING SELECTOR | target creature card | 24 | 117 | 182 | Hua Tuo, Honored Physician, Puppeteer Clique, Metamorphosis Fanatic |
| 13 | MISSING EFFECT | if n … | 24 | 55 | 92 | Airdrop Aeronauts, Hot Pursuit, Kotis, Sibsig Champion |
| 14 | MISSING EFFECT | put n … | 23 | 81 | 139 | Black Sun's Zenith, Breaking // Entering, Mind Raker |
| 15 | MISSING EFFECT | transform ~ … | 23 | 15 | 57 | Ulvenwald Captive // Ulvenwald Abomination, Seraph of New Capenna // Seraph of New Phyrexia, Sun-Blessed Guardian // Furnace-Blessed Conqueror |
| 16 | UNSUPPORTED ORACLE PATTERN | As long as your devotion to … | 22 | 5 | 22 | Phenax, God of Deception, Erebos, God of the Dead, Thassa, Deep-Dwelling |
| 17 | UNSUPPORTED ORACLE PATTERN | You may look at the top … | 22 | 2 | 45 | One with the Multiverse, The Lunar Whale, Cemetery Illuminator |
| 18 | MISSING CONTINUOUS EFFECT | During your turn, … | 21 | 36 | 74 | Pompous Gadabout, Long-Lost Lances, Fresh-Faced Recruit |
| 19 | MISSING SELECTOR | target creatures | 19 | 170 | 311 | Ravenous Gigantotherium, Fire Covenant, Amazing Acrobatics |
| 20 | MISSING EFFECT | until end of turn … | 19 | 141 | 218 | Divergent Growth, Doorman, Strength of Will |
| 21 | UNSUPPORTED ORACLE PATTERN | ~ costs {M} less to cast … | 19 | 36 | 71 | Bedlam Reveler, Gargantuan Leech, Hamza, Guardian of Arashin |
| 22 | MISSING EFFECT | ~ deals n … | 18 | 224 | 358 | Deem Worthy, End-Blaze Epiphany, Harvest Pyre |
| 23 | MISSING EFFECT | mill n … | 18 | 58 | 100 | Sparring Dummy, Beluna Grandsquall // Seek Thrills, Cache Grab |
| 24 | MISSING TRIGGER EVENT | When you cast ~ | 18 | 22 | 80 | Empyrial Storm, The Fourteenth Doctor, Ulamog, the Ceaseless Hunger |
| 25 | MISSING EFFECT | discard n … | 17 | 39 | 78 | Keldon Raider, Witch's Mark, Seasoned Pyromancer |
| 26 | MISSING CONTINUOUS EFFECT | Commander creatures you own have “…” | 17 | 17 | 17 | Dungeon Delver, Noble Heritage, Acolyte of Bahamut |
| 27 | MISSING EFFECT | exile ~ … | 17 | 11 | 57 | Stenn, Paranoid Partisan, Woodland Guidance, Teferi's Protection |
| 28 | MISSING EFFECT | if ~ … | 16 | 64 | 126 | Warden of the First Tree, Blinkmoth Urn, Mad Dog |
| 29 | MISSING COST | {M}, Sacrifice another creature | 16 | 32 | 51 | Sanguine Spy, Skyclave Shadowcat, Phyrexian Warhorse |
| 30 | MISSING CONTINUOUS EFFECT | ~'s power is equal to the … | 15 | 27 | 67 | Uurg, Spawn of Turg, Snow Villiers, Nethergoyf |
| 31 | UNSUPPORTED ORACLE PATTERN | As ~ enters, … | 15 | 1 | 19 | Stenn, Paranoid Partisan, Arachne, Psionic Weaver, Pramikon, Sky Rampart |
| 32 | UNSUPPORTED ORACLE PATTERN | More Than Meets the Eye {M} | 15 | 0 | 15 | Optimus Prime, Hero // Optimus Prime, Autobot Leader, Megatron, Tyrant // Megatron, Destructive Force, Jetfire, Ingenious Scientist // Jetfire, Air Guardian |
| 33 | MISSING EFFECT | search your library for … | 14 | 157 | 252 | Safewright Quest, Thunderherd Migration, Squadron Hawk |
| 34 | MISSING COST | {M}, {M}, Discard N card(s) | 14 | 69 | 79 | Arc Mage, Sparkspitter, Instigator |
| 35 | MISSING EFFECT | create a n/n white … | 14 | 32 | 60 | Empyrial Storm, Drag the Canal, Ajani Resolute |
| 36 | MISSING EFFECT | create a n/n red … | 14 | 24 | 55 | Prosperity Tycoon, Ertha Jo, Frontier Mentor, Nesting Dragon |
| 37 | MISSING TRIGGER EVENT | Whenever you cast your second spell each turn | 14 | 22 | 34 | Sunstar Lightsmith, Wanda's Vision, Kraum, Violent Cacophony |
| 38 | MISSING MECHANIC | sneak | 14 | 11 | 27 | Turncoat Kunoichi, Michelangelo, Improviser, Donatello's Technique |
| 39 | MISSING MECHANIC | firebending | 14 | 5 | 22 | Fire Sages, Loyal Fire Sage, Jeong Jeong, the Deserter |
| 40 | MISSING MECHANIC | partner | 14 | 4 | 24 | Lore Weaver, Blaring Captain, Rory Williams |
| 41 | UNSUPPORTED ORACLE PATTERN | • Put a ±N/±N counter(s) on … | 14 | 0 | 38 | Bejeweled Warg, Trusty Retriever, Inspired Inventor |
| 42 | MISSING EFFECT | create a n/n black … | 13 | 26 | 46 | Queen Brahne, Grist, the Hunger Tide, Mysidian Elder |
| 43 | MISSING COST | {M}, Sacrifice an artifact | 13 | 20 | 32 | Embraal Gear-Smasher, Orcish Mechanics, Lobelia, Defender of Bag End |
| 44 | UNSUPPORTED ORACLE PATTERN | Living metal | 13 | 0 | 13 | Optimus Prime, Hero // Optimus Prime, Autobot Leader, Megatron, Tyrant // Megatron, Destructive Force, Jetfire, Ingenious Scientist // Jetfire, Air Guardian |
| 45 | MISSING COST | {M}, Sacrifice N creature(s) | 12 | 56 | 75 | Ruthless Knave, Tymaret, the Murder King, Starved Rusalka |
| 46 | MISSING RESTRICTION | ~ can't be blocked by creatures … | 12 | 26 | 56 | Lydia Frye, Pompous Gadabout, Ghost of Ramirez DePietro |
| 47 | MISSING SELECTOR | target equipment | 12 | 16 | 25 | Stolen Uniform, Shagrat, Loot Bearer, Thor, God of Thunder |
| 48 | UNSUPPORTED ORACLE PATTERN | Power-up — {M}: Put N ±N/±N … | 12 | 12 | 19 | Thanos, the Mad Titan, Shang-Chi, Martial Mentor, Hulk, Gamma Goliath |
| 49 | MISSING EFFECT | add {m} … | 11 | 39 | 64 | Akki Rockspeaker, Brightstone Ritual, Infernal Plunge |
| 50 | MISSING SELECTOR | target instant or sorcery card | 11 | 17 | 38 | Ogre Battlecaster, Impulsivity, Kishla Trawlers |
| 51 | MISSING EFFECT | exile up to n … | 11 | 16 | 27 | Salvation Swan, Liminal Hold, S.H.I.E.L.D. Flying Car |
| 52 | MISSING TRIGGER EVENT | Whenever you cast a historic spell | 11 | 15 | 19 | Serra Disciple, Cabal Paladin, Glóin, Dwarf Emissary |
| 53 | MISSING EFFECT | another target … | 11 | 13 | 23 | Hemosymbic Mite, Syr Faren, the Hengehammer, Pippin, Guard of the Citadel |
| 54 | MISSING COST / PERMISSION RULE | You may cast ~ from your … | 11 | 10 | 27 | Marang River Prowler, Quilled Greatwurm, Gravecrawler |
| 55 | MISSING EFFECT | earthbend n … | 11 | 10 | 27 | Earth Village Ruffians, Bumi, Unleashed, Badgermole |
| 56 | MISSING COST / PERMISSION RULE | Once during each of your turns, … | 11 | 7 | 15 | Kotis, Sibsig Champion, One with the Multiverse, Jacob Hauken, Inspector // Hauken's Insight |
| 57 | MISSING EFFECT | if you've cast a … | 11 | 5 | 12 | H.E.R.B.I.E., Lovable Robot, Invisible Woman, Alicia Masters, Skilled Sculptor |
| 58 | MISSING EFFECT | target creature you control … | 10 | 122 | 180 | Blessed Defiance, Hard-Hitting Question, Crowd of True Believers |
| 59 | MISSING EFFECT | if you control n … | 10 | 65 | 99 | Dawnhart Wardens, Lumengrid Drake, Discourtesy Clerk |
| 60 | MISSING COST | {M}, Discard N card(s) | 10 | 46 | 79 | Viashino Lashclaw, Haunted Dead, Junk Golem |
| 61 | MISSING EFFECT | create a n/n green … | 10 | 41 | 83 | Rhonas's Last Stand, Kasmina, Enigma Sage, Choco-Comet |
| 62 | MISSING SELECTOR | target creature card with mana value | 10 | 24 | 38 | General Leo Cristophe, Yathan Roadwatcher, Balduvian Atrocity |
| 63 | MISSING EFFECT | exile the top n … | 10 | 19 | 54 | Duplicity, Crossover Collaboration, Ral, Monsoon Mage // Ral, Leyline Prodigy |
| 64 | MISSING RESTRICTION | ~ can't attack or block unless … | 10 | 13 | 23 | Sab-Sunen, Luxa Embodied, Relic Golem, Hollow Warrior |
| 65 | MISSING EFFECT | return it to the … | 10 | 9 | 22 | Bronzehide Lion, Optimus Prime, Hero // Optimus Prime, Autobot Leader, Yedora, Grave Gardener |
| 66 | MISSING EFFECT | choose target … | 9 | 65 | 79 | Arcbond, Deglamer, Wreck Hunter |
| 67 | MISSING EFFECT | gain control of target … | 9 | 53 | 81 | Sauron, the Lidless Eye, New Blood, Unwilling Recruit |
| 68 | MISSING EFFECT | reveal the top card … | 9 | 33 | 47 | Counterbalance, Sorin, Grim Nemesis, Sapling of Colfenor |
| 69 | MISSING EFFECT | sacrifice another creature … | 9 | 14 | 25 | Rhovanion Rampager, Brawl-Bash Ogre, Ragefire Hellkite |
| 70 | MISSING CONTINUOUS EFFECT | You have no maximum hand size | 9 | 7 | 23 | Nyssa of Traken, Curiosity Crafter, Wizard Class |
| 71 | MISSING EFFECT | double the number of … | 9 | 7 | 19 | Primordial Hydra, The Millennium Calendar, Paradox Zone |
| 72 | UNSUPPORTED ORACLE PATTERN | Web-slinging {M} | 9 | 4 | 9 | Scarlet Spider, Ben Reilly, Arachne, Psionic Weaver, Spider-Man, Brooklyn Visionary |
| 73 | MISSING CONTINUOUS EFFECT | ~ has indestructible as long as … | 9 | 2 | 12 | Crew Captain, War Historian, Havi, the All-Father |
| 74 | MISSING TRIGGER EVENT | When ~ enters | 9 | 2 | 9 | Niv-Mizzet Reborn, Lobelia Sackville-Baggins, Drizzt Do'Urden |
| 75 | MISSING MECHANIC | companion | 9 | 1 | 9 | Lutri, the Spellchaser, Gyruda, Doom of Depths, Lurrus of the Dream-Den |
| 76 | UNSUPPORTED ORACLE PATTERN | • ~ deals N damage to … | 9 | 0 | 18 | Arbalest Engineers, Tectonic Giant, Umaro, Raging Yeti |
| 77 | UNSUPPORTED ORACLE PATTERN | Storied | 9 | 0 | 9 | Balin, Loremaster, Dáin, Lord of the Iron Hills, Ori, Keeper of Songs |
| 78 | MISSING EFFECT | return ~ … | 8 | 60 | 89 | Dragon Fangs, Dragon Scales, Eternal Dragon |
| 79 | MISSING EFFECT | reveal the top n … | 8 | 53 | 72 | Green Sun's Twilight, Benefaction of Rhonas, Karn, Scion of Urza |
| 80 | MISSING COST | {M}, Discard ~ | 8 | 33 | 57 | Jiwari, the Earth Aflame, Favor of Jukai, Radiant Solar |

## Largest clusters (Commander cards affected)

| # | Category | Cluster | Commander cards | Only missing piece for | Commanders | Examples |
|---|---|---|---|---|---|---|
| 1 | MISSING EFFECT | draw n … | 573 | 191 | 58 | Errand-Rider of Gondor, Heal, Grip of Amnesia |
| 2 | MISSING EFFECT | choose n … | 553 | 47 | 61 | Road of Return, Saheeli's Artistry, Eldrazi Confluence |
| 3 | MISSING EFFECT | ~ deals n … | 358 | 224 | 18 | Deem Worthy, End-Blaze Epiphany, Harvest Pyre |
| 4 | MISSING SELECTOR | target | 350 | 198 | 31 | Cinder Elemental, Archangel of Wrath, Granger Guildmage |
| 5 | MISSING COST / PERMISSION RULE | As an additional cost to cast … | 312 | 34 | 6 | Thunderherd Migration, Mind Extraction, Harvest Pyre |
| 6 | MISSING SELECTOR | target creatures | 311 | 170 | 19 | Ravenous Gigantotherium, Fire Covenant, Amazing Acrobatics |
| 7 | MISSING EFFECT | pay {m} … | 263 | 186 | 65 | Labyrinth Adversary, Minion Reflector, Giant's Amulet |
| 8 | MISSING EFFECT | search your library for … | 252 | 157 | 14 | Safewright Quest, Thunderherd Migration, Squadron Hawk |
| 9 | MISSING EFFECT | create n … | 239 | 127 | 31 | Summon the School, Cogwork Assembler, Endless Evil |
| 10 | MISSING REPLACEMENT PATTERN | As ~ enters, … | 237 | 47 | 4 | Kindred Discovery, Utopia Sprawl, Game Trail |
| 11 | MISSING MECHANIC | kicker | 224 | 0 | 7 | Strength of Night, Goblin Barrage, Archangel of Wrath |
| 12 | MISSING EFFECT | destroy target … | 219 | 132 | 5 | Kalitas, Bloodchief of Ghet, Misfortune's Gain, Raze |
| 13 | MISSING EFFECT | until end of turn … | 218 | 141 | 19 | Divergent Growth, Doorman, Strength of Will |
| 14 | MISSING EFFECT | look at the top … | 207 | 144 | 38 | Harald, King of Skemfar, Lantern of Revealing, Ponder |
| 15 | MISSING EFFECT | put a ±n/±n counter(s) … | 196 | 128 | 54 | Yorvo, Lord of Garenbrig, Gollum, Silent Slinker // Meager Meal, Ent-Draught Basin |
| 16 | MISSING EFFECT | target creature gets ±n/±n … | 183 | 104 | 2 | Stern Marshal, Spontaneous Flight, Rig for War |
| 17 | MISSING SELECTOR | target creature card | 182 | 117 | 24 | Hua Tuo, Honored Physician, Puppeteer Clique, Metamorphosis Fanatic |
| 18 | MISSING EFFECT | target creature you control … | 180 | 122 | 10 | Blessed Defiance, Hard-Hitting Question, Crowd of True Believers |
| 19 | MISSING EFFECT | put n … | 139 | 81 | 23 | Black Sun's Zenith, Breaking // Entering, Mind Raker |
| 20 | MISSING CONTINUOUS EFFECT | ~'s power and toughness are each … | 127 | 59 | 28 | Eluge, the Shoreless Sea, Flora Colossus, Revenant |
| 21 | MISSING EFFECT | if ~ … | 126 | 64 | 16 | Warden of the First Tree, Blinkmoth Urn, Mad Dog |
| 22 | MISSING CONTINUOUS EFFECT | ~ gets ±N/±N for each … | 115 | 54 | 32 | Nim Lasher, Benalish Honor Guard, Anya, Merciless Angel |
| 23 | MISSING EFFECT | exile target … | 115 | 78 | 4 | Astarion's Thirst, Deadly Rollick, Tawnos's Coffin |
| 24 | MANA ABILITY WORDING | {M}, … | 108 | 74 | 6 | Saltcrusted Steppe, Cabal Stronghold, Interplanar Beacon |
| 25 | MISSING SELECTOR | target player or planeswalker | 101 | 65 | 3 | Goblin Barrage, Scorching Missile, Consuming Sinkhole |
| 26 | MISSING EFFECT | mill n … | 100 | 58 | 18 | Sparring Dummy, Beluna Grandsquall // Seek Thrills, Cache Grab |
| 27 | MISSING EFFECT | if you control n … | 99 | 65 | 10 | Dawnhart Wardens, Lumengrid Drake, Discourtesy Clerk |
| 28 | MISSING CONTINUOUS EFFECT | ~ gets ±N/±N as long as … | 98 | 89 | 1 | Sulam Djinn, Zanam Djinn, Isleback Spawn |
| 29 | MISSING MECHANIC | ward | 97 | 10 | 47 | Tyranid Harridan, Grey Host Reinforcements, Kwia Vigorbloom |
| 30 | MISSING EFFECT | exile the top card … | 94 | 37 | 30 | Moonring Mirror, Mezzio Mugger, Etali, Primal Storm |
| 31 | MISSING EFFECT | you gain n … | 93 | 63 | 7 | Shu Farmer, Essence Pulse, Smitten Swordmaster // Curry Favor |
| 32 | MISSING EFFECT | if n … | 92 | 55 | 24 | Airdrop Aeronauts, Hot Pursuit, Kotis, Sibsig Champion |
| 33 | MISSING SELECTOR | target card | 91 | 49 | 5 | Funeral Pyre, Barkform Harvester, Carrion Locust |
| 34 | MISSING EFFECT | return ~ … | 89 | 60 | 8 | Dragon Fangs, Dragon Scales, Eternal Dragon |
| 35 | MISSING EFFECT | create a n/n green … | 83 | 41 | 10 | Rhonas's Last Stand, Kasmina, Enigma Sage, Choco-Comet |
| 36 | MISSING EFFECT | return target … | 82 | 46 | 1 | Surging Aether, Perilous Voyage, Geistwave |
| 37 | MISSING EFFECT | gain control of target … | 81 | 53 | 9 | Sauron, the Lidless Eye, New Blood, Unwilling Recruit |
| 38 | MISSING TRIGGER EVENT | When you cast ~ | 80 | 22 | 18 | Empyrial Storm, The Fourteenth Doctor, Ulamog, the Ceaseless Hunger |
| 39 | MISSING COST | {M}, {M}, Discard N card(s) | 79 | 69 | 14 | Arc Mage, Sparkspitter, Instigator |
| 40 | MISSING COST | {M}, Discard N card(s) | 79 | 46 | 10 | Viashino Lashclaw, Haunted Dead, Junk Golem |
| 41 | MISSING EFFECT | choose target … | 79 | 65 | 9 | Arcbond, Deglamer, Wreck Hunter |
| 42 | MISSING EFFECT | discard n … | 78 | 39 | 17 | Keldon Raider, Witch's Mark, Seasoned Pyromancer |
| 43 | MISSING EFFECT | it deals n … | 78 | 61 | 3 | Goblin Chainwhirler, Festering Evil, Unsparing Boltcaster |
| 44 | MISSING COST | {M}, Sacrifice N creature(s) | 75 | 56 | 12 | Ruthless Knave, Tymaret, the Murder King, Starved Rusalka |
| 45 | MISSING EFFECT | tap target … | 75 | 43 | 4 | Spider-Woman, Secret Agent, Guardian of Tazeem, Gilded Scuttler |
| 46 | MISSING CONTINUOUS EFFECT | During your turn, … | 74 | 36 | 21 | Pompous Gadabout, Long-Lost Lances, Fresh-Faced Recruit |
| 47 | MISSING EFFECT | if there are n … | 74 | 27 | 6 | Locked in the Cemetery, Sanguine Spy, Extricator of Sin // Extricator of Flesh |
| 48 | MISSING EFFECT | reveal the top n … | 72 | 53 | 8 | Green Sun's Twilight, Benefaction of Rhonas, Karn, Scion of Urza |
| 49 | UNSUPPORTED ORACLE PATTERN | ~ costs {M} less to cast … | 71 | 36 | 19 | Bedlam Reveler, Gargantuan Leech, Hamza, Guardian of Arashin |
| 50 | MISSING CONTINUOUS EFFECT | ~'s power is equal to the … | 67 | 27 | 15 | Uurg, Spawn of Turg, Snow Villiers, Nethergoyf |

## Top Commander features to implement next

Ranked by pod cards, pod commanders, cards for which it is the only missing piece, then Commander cards needing it.

| # | Feature | Kind | Pod cards | Commander cards | Only missing piece for | Examples |
|---|---|---|---|---|---|---|
| 1 | mana:ability | engine | 0 | 367 | 233 | Saltcrusted Steppe, Flywheel Racer, The Emperor of Palamecia // The Lord Master of Hell |
| 2 | template:Enchanted creature has “…” | continuous | 0 | 34 | 28 | Ghostly Touch, Immobilizing Ink, Sunbond |
| 3 | template:Commander creatures you own have “…” | continuous | 0 | 21 | 21 | Dungeon Delver, Scion of Halaster, Noble Heritage |
| 4 | template:Enchanted creature gets ±N/±N and has “…” | continuous | 0 | 25 | 20 | Arcane Teachings, Lunarch Mantle, Deviant Glee |
| 5 | keyword:banding | keyword | 0 | 24 | 19 | Nalathni Dragon, Mishra's War Machine, Kjeldoran Escort |
| 6 | keyword:foretell | keyword | 0 | 51 | 18 | The Foretold Soldier, Rise of the Dread Marn, Green Slime |
| 7 | keyword:bestow | keyword | 0 | 42 | 18 | Leafcrown Dryad, Baleful Eidolon, Observant Alseid |
| 8 | template:Equipped creature has “…” | continuous | 0 | 24 | 16 | Field-Tested Frying Pan, Sorcerer's Wand, Fishing Pole |
| 9 | keyword:enchant | keyword | 0 | 67 | 15 | Utopia Sprawl, One with the Stars, Corrupted Roots |
| 10 | template:~ enters prepared. | static | 0 | 40 | 15 | Adventurous Eater // Have a Bite, Maelstrom Artisan // Rocket Volley, Fatehold Chronologist // Peer Review |
| 11 | keyword:splice | keyword | 0 | 30 | 15 | Evermind, Horobi's Whisper, Desperate Ritual |
| 12 | template:Equipped creature gets ±N/±N and has “…” | continuous | 0 | 25 | 15 | Giant's Amulet, Iconic Shield, Candlestick |
| 13 | keyword:equip | keyword | 0 | 49 | 14 | Bloodthorn Flail, Strong Back, Team Pennant |
| 14 | template:{M}: Return ~ from your graveyard to your hand. | activated | 0 | 22 | 14 | The Sound of Drums, Merchant of Many Hats, Convenient Target |
| 15 | template:~ can't be blocked by creatures with power N or less. | restriction | 0 | 32 | 13 | Glinting Creeper, Dread Linnorm // Scale Deflection, Chomping Kavu |
| 16 | keyword:encore | keyword | 0 | 26 | 13 | Impulsivity, Sliver Gravemother, Belonging |
| 17 | keyword:backup | keyword | 0 | 25 | 13 | Saiba Cryptomancer, Chomping Kavu, Consuming Aetherborn |
| 18 | template:Modular N | static | 0 | 23 | 13 | Arcbound Whelp, Arcbound Javelineer, Arcbound Hybrid |
| 19 | template:When ~ enters, attach it to target creature you control. | triggered | 0 | 30 | 12 | Maul of the Skyclaves, Meltstrider's Gear, Bramble Armor |
| 20 | keyword:overload | keyword | 0 | 27 | 12 | Mizzium Skin, Corporeal Projection, Mind Rake |
| 21 | keyword:myriad | keyword | 0 | 23 | 12 | The Master, Multiplied, Sumala Rumblers, Conclave Evangelist |
| 22 | template:All Slivers have “…” | continuous | 0 | 12 | 12 | Magma Sliver, Basal Sliver, Mesmeric Sliver |
| 23 | keyword:warp | keyword | 0 | 31 | 11 | Starbreach Whale, Knight Luminary, Loading Zone |
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
| 34 | template:~ enters tapped unless you control N or fewer other lands. | replacement | 0 | 11 | 10 | Concealed Courtyard, Inspiring Vantage, Blackcleave Cliffs |
| 35 | template:~ enters tapped unless a player has N or less life. | replacement | 0 | 10 | 10 | Abandoned Campground, Raucous Carnival, Strangled Cemetery |
| 36 | template:~ enters tapped unless you control N or more basic lands. | replacement | 0 | 10 | 10 | Sodden Verdure, Smoldering Marsh, Vernal Fen |
| 37 | template:~ enters tapped unless you control N or more other lands. | replacement | 0 | 10 | 10 | Rockfall Vale, Stormcarved Coast, Sundown Pass |
| 38 | template:~ enters tapped unless you control a planeswalker. | replacement | 0 | 10 | 10 | Theorix Annex, Stingerquill Annex, Konstrari Annex |
| 39 | template:~ enters tapped unless you have N or more opponents. | replacement | 0 | 10 | 10 | Spire Garden, Sea of Clouds, Bountiful Promenade |
| 40 | keyword:disguise | keyword | 0 | 43 | 9 | Boltbender, Nightdrinker Moroii, Concealed Weapon |
| 41 | keyword:cumulative upkeep | keyword | 0 | 23 | 9 | Varchild's War-Riders, Aboroth, Inner Sanctum |
| 42 | template:When ~ is put into a graveyard from the battlefield, return it to its owner's hand. | triggered | 0 | 20 | 9 | Spine of Ish Sah, Slow Motion, Fiery Mantle |
| 43 | keyword:living weapon | keyword | 0 | 19 | 9 | Nettlecyst, Lashwrithe, Skinwing |
| 44 | keyword:mentor | keyword | 0 | 19 | 9 | Hammer Dropper, Legion Warboss, Tributary Instructor |
| 45 | keyword:prototype | keyword | 0 | 19 | 9 | Goring Warplow, Combat Thresher, Woodcaller Automaton |
| 46 | keyword:extort | keyword | 0 | 17 | 9 | Syndicate Heavy, Tithe Drinker, Kingpin's Pet |
| 47 | keyword:fading | keyword | 0 | 17 | 9 | Parallax Wave, Phyrexian Prowler, Skyshroud Ridgeback |
| 48 | keyword:retrace | keyword | 0 | 17 | 9 | Flame Jab, Monstrify, Waves of Aggression |
| 49 | template:Prevent all combat damage that would be dealt this turn. | prevention | 0 | 14 | 9 | Jaheira's Respite, Fog, Darkness |
| 50 | template:Threshold — ~ gets ±N/±N as long as there are N or more cards in your graveyard. | continuous | 0 | 12 | 9 | Krosan Beast, Nimble Mongoose, Anurid Barkripper |
| 51 | template:{M}, Sacrifice ~: It deals N damage to any target. | activated | 0 | 12 | 9 | Fireforger's Puzzleknot, Lightning Spear, Pyrite Spellbomb |
| 52 | keyword:evolve | keyword | 0 | 22 | 8 | Adaptive Snapjaw, Shambleshark, Tyranid Prime |
| 53 | keyword:vanishing | keyword | 0 | 20 | 8 | Soultether Golem, Deadly Grub, Reality Acid |
| 54 | template:~'s power and toughness are each equal to the number of lands you control. | characteristic_defining | 0 | 17 | 8 | Flora Colossus, Rubblehulk, Harmonious Grovestrider |
| 55 | keyword:embalm | keyword | 0 | 15 | 8 | Heart-Piercer Manticore, Angel of Sanctions, Anointer Priest |
| 56 | keyword:umbra armor | keyword | 0 | 15 | 8 | Felidar Umbra, Drake Umbra, Hyena Umbra |
| 57 | template:Graft N | static | 0 | 13 | 8 | Cytoplast Manipulator, Sporeback Troll, Vigean Hydropon |
| 58 | template:Whenever ~ deals combat damage to a player, that player discards N card(s). | triggered | 0 | 12 | 8 | Chilling Apparition, Banshee of the Dread Choir, Silent Specter |
| 59 | template:~ can block an additional creature each combat. | static | 0 | 12 | 8 | Selesnya Sagittars, Tangleclaw Werewolf // Fibrous Entangler, Tangleclaw Werewolf // Fibrous Entangler |
| 60 | template:{M}, {M}, Sacrifice ~: It deals N damage to target creature. | activated | 0 | 11 | 8 | Vial of Dragonfire, Flamecast Wheel, Mouth of Ronom |

## Coverage by card type

| Type | FULL | PARTIAL | REVIEW | MANUAL |
|---|---|---|---|---|
| Creature | 4899 | 13022 | 0 | 0 |
| Artifact | 797 | 2796 | 0 | 0 |
| Enchantment | 522 | 3125 | 0 | 0 |
| Sorcery | 704 | 2864 | 0 | 0 |
| Instant | 949 | 2805 | 0 | 0 |
| Land | 497 | 715 | 0 | 0 |
| Planeswalker | 5 | 306 | 0 | 0 |
| Battle | 0 | 36 | 0 | 0 |

## Rules features in the pool (ability lines)

triggered 14909, keyword 14115, spell_effect 9123, activated 7358, continuous 4014, static 3069, mana_ability 2038, replacement 1966, restriction 1474, loyalty 882, prevention 320, additional_cost 307, cost_modifier 261, characteristic_defining 247, permission 207, alternative_cost 180

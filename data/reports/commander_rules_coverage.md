# Commander rules coverage

Card data: Scryfall `2026-09-28T21:01:54.353+00:00` · Comprehensive Rules 2026-09-25 · rules engine v2 · generated 2026-09-29 22:32

Only cards that are **legal in Commander today** count. Banned cards (83) are COMMANDER_BANNED and excluded.

## Commander coverage

Commander-legal cards: **32116**

| Level | Cards | Share |
|---|---|---|
| FULL | 9648 | 30.0% |
| PARTIAL | 22420 | 69.8% |
| REVIEW | 0 | 0.0% |
| MANUAL | 48 | 0.1% |

Possible commanders (CR 903.3/903.3a, incl. Backgrounds): **3501** — FULL 405, PARTIAL 3096, REVIEW 0, MANUAL 0

## Pod coverage

No pod decks in the inventory yet (`python -m tools.rules_inventory`); the queue below is ranked by Commander-legal cards unlocked.

## Coverage quality

- Ability features (lines, keywords, play/cast/combat) across Commander-legal cards: 113346
- Automated: 81244 (71.7%) · unrecognized clauses: 32102
- Oracle text classified (automated, or sorted into a concrete missing capability): 97.4% · unclassified clauses: 2936
- Distinct missing-capability clusters: 8653

## Missing capabilities by category

| Category | Cards affected | Clauses |
|---|---|---|
| MISSING EFFECT | 11330 | 13349 |
| MISSING SELECTOR | 3535 | 3736 |
| MISSING TRIGGER EVENT | 3465 | 3640 |
| MISSING CONTINUOUS EFFECT | 2204 | 2328 |
| UNSUPPORTED ORACLE PATTERN | 2167 | 2936 |
| MISSING MECHANIC | 1816 | 1878 |
| MISSING REPLACEMENT PATTERN | 1362 | 1401 |
| MISSING RESTRICTION | 938 | 984 |
| MISSING COST / PERMISSION RULE | 935 | 955 |
| MISSING COST | 512 | 526 |
| MANA ABILITY WORDING | 367 | 369 |

## Highest-payoff clusters

Ranked by pod cards, pod commanders, possible commanders affected, cards it alone would unlock, then all Commander cards needing it.

| # | Category | Cluster | Commanders | Only missing piece for | Commander cards | Examples |
|---|---|---|---|---|---|---|
| 1 | MISSING EFFECT | choose n … | 65 | 49 | 555 | Road of Return, Saheeli's Artistry, Dawnbringer Cleric |
| 2 | MISSING EFFECT | draw n … | 61 | 211 | 580 | Errand-Rider of Gondor, Krovikan Sorcerer, Heal |
| 3 | MISSING EFFECT | put a ±n/±n counter(s) … | 53 | 140 | 202 | Greta, Sweettooth Scourge, Yorvo, Lord of Garenbrig, Ent-Draught Basin |
| 4 | MISSING EFFECT | pay {m} … | 53 | 108 | 166 | Labyrinth Adversary, Minion Reflector, Giant's Amulet |
| 5 | MISSING MECHANIC | ward | 47 | 11 | 97 | Tyranid Harridan, Grey Host Reinforcements, Kwia Vigorbloom |
| 6 | MISSING EFFECT | look at the top … | 38 | 153 | 211 | Harald, King of Skemfar, Lantern of Revealing, Puresight Merrow |
| 7 | MISSING EFFECT | create n … | 36 | 149 | 253 | Summon the School, Cogwork Assembler, Endless Evil |
| 8 | MISSING SELECTOR | target | 34 | 194 | 327 | Cinder Elemental, Archangel of Wrath, Chain of Plasma |
| 9 | MISSING EFFECT | exile the top card … | 33 | 47 | 106 | Moonring Mirror, Professional Face-Breaker, Mezzio Mugger |
| 10 | MISSING CONTINUOUS EFFECT | ~ gets ±N/±N for each … | 32 | 58 | 115 | Nim Lasher, Benalish Honor Guard, Anya, Merciless Angel |
| 11 | MISSING EFFECT | put n … | 28 | 92 | 148 | Black Sun's Zenith, Breaking // Entering, Mind Raker |
| 12 | MISSING CONTINUOUS EFFECT | ~'s power and toughness are each … | 28 | 65 | 127 | Eluge, the Shoreless Sea, Flora Colossus, Revenant |
| 13 | MISSING SELECTOR | target creature card | 25 | 116 | 174 | Hua Tuo, Honored Physician, Puppeteer Clique, Metamorphosis Fanatic |
| 14 | MISSING EFFECT | if n … | 24 | 60 | 92 | Airdrop Aeronauts, Hot Pursuit, Kotis, Sibsig Champion |
| 15 | MISSING EFFECT | until end of turn … | 23 | 154 | 227 | Divergent Growth, Doorman, Strength of Will |
| 16 | MISSING EFFECT | transform ~ … | 23 | 22 | 65 | Ulvenwald Captive // Ulvenwald Abomination, Westvale Abbey // Ormendahl, Profane Prince, Seraph of New Capenna // Seraph of New Phyrexia |
| 17 | UNSUPPORTED ORACLE PATTERN | As long as your devotion to … | 22 | 7 | 22 | Phenax, God of Deception, Erebos, God of the Dead, Thassa, Deep-Dwelling |
| 18 | UNSUPPORTED ORACLE PATTERN | You may look at the top … | 22 | 2 | 45 | One with the Multiverse, The Lunar Whale, Cemetery Illuminator |
| 19 | MISSING EFFECT | exile ~ … | 20 | 13 | 61 | Stenn, Paranoid Partisan, Woodland Guidance, Teferi's Protection |
| 20 | UNSUPPORTED ORACLE PATTERN | ~ costs {M} less to cast … | 19 | 37 | 71 | Bedlam Reveler, Gargantuan Leech, Hamza, Guardian of Arashin |
| 21 | MISSING EFFECT | mill n … | 18 | 62 | 102 | Sparring Dummy, Beluna Grandsquall // Seek Thrills, Cache Grab |
| 22 | MISSING TRIGGER EVENT | When you cast ~ | 18 | 28 | 80 | Empyrial Storm, The Fourteenth Doctor, Ulamog, the Ceaseless Hunger |
| 23 | MISSING EFFECT | search your library for … | 16 | 168 | 259 | Safewright Quest, Thunderherd Migration, Squadron Hawk |
| 24 | MISSING EFFECT | if ~ … | 16 | 71 | 126 | Warden of the First Tree, Blinkmoth Urn, Mad Dog |
| 25 | MISSING CONTINUOUS EFFECT | Commander creatures you own have “…” | 16 | 16 | 16 | Dungeon Delver, Noble Heritage, Acolyte of Bahamut |
| 26 | MISSING EFFECT | ~ deals n … | 15 | 196 | 308 | Deem Worthy, End-Blaze Epiphany, Harvest Pyre |
| 27 | MISSING EFFECT | create a n/n red … | 15 | 31 | 58 | Prosperity Tycoon, Ertha Jo, Frontier Mentor, Nesting Dragon |
| 28 | MISSING CONTINUOUS EFFECT | ~'s power is equal to the … | 15 | 29 | 67 | Uurg, Spawn of Turg, Snow Villiers, Nethergoyf |
| 29 | UNSUPPORTED ORACLE PATTERN | As ~ enters, … | 15 | 1 | 19 | Stenn, Paranoid Partisan, Arachne, Psionic Weaver, Pramikon, Sky Rampart |
| 30 | UNSUPPORTED ORACLE PATTERN | More Than Meets the Eye {M} | 15 | 0 | 15 | Optimus Prime, Hero // Optimus Prime, Autobot Leader, Megatron, Tyrant // Megatron, Destructive Force, Jetfire, Ingenious Scientist // Jetfire, Air Guardian |
| 31 | MISSING EFFECT | return ~ … | 14 | 84 | 126 | Summon the School, Dragon Fangs, Haunted Dead |
| 32 | MISSING EFFECT | create a n/n white … | 14 | 35 | 62 | Empyrial Storm, Drag the Canal, Ajani Resolute |
| 33 | MISSING EFFECT | create a n/n black … | 14 | 35 | 55 | Queen Brahne, Grist, the Hunger Tide, Mysidian Elder |
| 34 | MISSING TRIGGER EVENT | Whenever you cast your second spell each turn | 14 | 22 | 34 | Sunstar Lightsmith, Wanda's Vision, Kraum, Violent Cacophony |
| 35 | MISSING MECHANIC | sneak | 14 | 12 | 27 | Turncoat Kunoichi, Michelangelo, Improviser, Donatello's Technique |
| 36 | MISSING MECHANIC | partner | 14 | 5 | 24 | Lore Weaver, Blaring Captain, Rory Williams |
| 37 | MISSING MECHANIC | firebending | 14 | 5 | 22 | Fire Sages, Loyal Fire Sage, Jeong Jeong, the Deserter |
| 38 | UNSUPPORTED ORACLE PATTERN | • Put a ±N/±N counter(s) on … | 14 | 0 | 38 | Bejeweled Warg, Trusty Retriever, Inspired Inventor |
| 39 | UNSUPPORTED ORACLE PATTERN | Living metal | 13 | 0 | 13 | Optimus Prime, Hero // Optimus Prime, Autobot Leader, Megatron, Tyrant // Megatron, Destructive Force, Jetfire, Ingenious Scientist // Jetfire, Air Guardian |
| 40 | MISSING RESTRICTION | ~ can't be blocked by creatures … | 12 | 27 | 56 | Lydia Frye, Pompous Gadabout, Ghost of Ramirez DePietro |
| 41 | MISSING SELECTOR | target equipment | 12 | 17 | 25 | Stolen Uniform, Shagrat, Loot Bearer, Thor, God of Thunder |
| 42 | UNSUPPORTED ORACLE PATTERN | Power-up — {M}: Put N ±N/±N … | 12 | 12 | 19 | Thanos, the Mad Titan, Shang-Chi, Martial Mentor, Hulk, Gamma Goliath |
| 43 | MISSING EFFECT | add {m} … | 11 | 40 | 65 | Akki Rockspeaker, Brightstone Ritual, Infernal Plunge |
| 44 | MISSING EFFECT | exile the top n … | 11 | 20 | 57 | Duplicity, Memorial Vault, Crossover Collaboration |
| 45 | MISSING TRIGGER EVENT | Whenever you cast a historic spell | 11 | 15 | 19 | Serra Disciple, Cabal Paladin, Glóin, Dwarf Emissary |
| 46 | MISSING EFFECT | earthbend n … | 11 | 14 | 27 | Earth Village Ruffians, Bumi, Unleashed, Badgermole |
| 47 | MISSING EFFECT | another target … | 11 | 13 | 23 | Hemosymbic Mite, Syr Faren, the Hengehammer, Pippin, Guard of the Citadel |
| 48 | MISSING COST / PERMISSION RULE | You may cast ~ from your … | 11 | 10 | 27 | Marang River Prowler, Quilled Greatwurm, Gravecrawler |
| 49 | MISSING COST / PERMISSION RULE | Once during each of your turns, … | 11 | 7 | 15 | Kotis, Sibsig Champion, One with the Multiverse, Jacob Hauken, Inspector // Hauken's Insight |
| 50 | MISSING EFFECT | if you've cast a … | 11 | 5 | 12 | H.E.R.B.I.E., Lovable Robot, Invisible Woman, Alicia Masters, Skilled Sculptor |
| 51 | MISSING EFFECT | target creature you control … | 10 | 124 | 178 | Blessed Defiance, Hard-Hitting Question, Crowd of True Believers |
| 52 | MISSING EFFECT | gain control of target … | 10 | 58 | 85 | Sauron, the Lidless Eye, New Blood, Unwilling Recruit |
| 53 | MISSING SELECTOR | target creature card with mana value | 10 | 25 | 39 | General Leo Cristophe, Yathan Roadwatcher, Lazotep Quarry |
| 54 | MISSING SELECTOR | target instant or sorcery card | 10 | 20 | 35 | Ogre Battlecaster, Flood of Recollection, Impulsivity |
| 55 | MISSING RESTRICTION | ~ can't attack or block unless … | 10 | 16 | 23 | Sab-Sunen, Luxa Embodied, Relic Golem, Hollow Warrior |
| 56 | MISSING EFFECT | return it to the … | 10 | 10 | 22 | Bronzehide Lion, Optimus Prime, Hero // Optimus Prime, Autobot Leader, Yedora, Grave Gardener |
| 57 | MISSING SELECTOR | target creatures | 9 | 106 | 208 | Ravenous Gigantotherium, Fire Covenant, Amazing Acrobatics |
| 58 | MISSING EFFECT | choose target … | 9 | 69 | 82 | Arcbond, Deglamer, Wreck Hunter |
| 59 | MISSING EFFECT | reveal the top n … | 9 | 55 | 74 | Green Sun's Twilight, Benefaction of Rhonas, Karn, Scion of Urza |
| 60 | MISSING EFFECT | create a n/n green … | 9 | 46 | 83 | Rhonas's Last Stand, Choco-Comet, Fractal Harness |
| 61 | MISSING EFFECT | reveal the top card … | 9 | 33 | 47 | Counterbalance, Sorin, Grim Nemesis, Sapling of Colfenor |
| 62 | MISSING EFFECT | reveal cards from the … | 9 | 25 | 31 | Treasure Hunt, Hei Bai, Forest Guardian, Hermit Druid |
| 63 | MISSING EFFECT | exile up to n … | 9 | 15 | 24 | Salvation Swan, Liminal Hold, S.H.I.E.L.D. Flying Car |
| 64 | MISSING EFFECT | double the number of … | 9 | 10 | 21 | Primordial Hydra, The Millennium Calendar, Paradox Zone |
| 65 | MISSING CONTINUOUS EFFECT | You have no maximum hand size | 9 | 7 | 23 | Nyssa of Traken, Curiosity Crafter, Wizard Class |
| 66 | MISSING CONTINUOUS EFFECT | During your turn, … | 9 | 7 | 18 | Long-Lost Lances, Miriam, Herd Whisperer, Yuna, Hope of Spira |
| 67 | UNSUPPORTED ORACLE PATTERN | Web-slinging {M} | 9 | 4 | 9 | Scarlet Spider, Ben Reilly, Arachne, Psionic Weaver, Spider-Man, Brooklyn Visionary |
| 68 | MISSING TRIGGER EVENT | When ~ enters | 9 | 2 | 9 | Niv-Mizzet Reborn, Lobelia Sackville-Baggins, Drizzt Do'Urden |
| 69 | MISSING MECHANIC | companion | 9 | 1 | 9 | Lutri, the Spellchaser, Gyruda, Doom of Depths, Lurrus of the Dream-Den |
| 70 | UNSUPPORTED ORACLE PATTERN | • ~ deals N damage to … | 9 | 0 | 18 | Arbalest Engineers, Tectonic Giant, Umaro, Raging Yeti |
| 71 | UNSUPPORTED ORACLE PATTERN | Storied | 9 | 0 | 9 | Balin, Loremaster, Dáin, Lord of the Iron Hills, Ori, Keeper of Songs |
| 72 | MISSING EFFECT | if you control n … | 8 | 43 | 67 | Dawnhart Wardens, Boundary Lands Ranger, Dispatch |
| 73 | MISSING COST | {M}, Discard ~ | 8 | 33 | 57 | Jiwari, the Earth Aflame, Favor of Jukai, Radiant Solar |
| 74 | MISSING SELECTOR | target creature defending player controls | 8 | 27 | 34 | Fear of Falling, Impetuous Devils, Fiend Binder |
| 75 | MISSING TRIGGER EVENT | Whenever N creature(s)(s) you control attacks alone | 8 | 19 | 22 | Finest Hour, Black Panther, Claws of Bast, Agents of S.H.I.E.L.D. |
| 76 | MISSING REPLACEMENT PATTERN | ~ enters with a ±N/±N counter(s) on … | 8 | 16 | 37 | Callous Sell-Sword // Burn Together, Avatar of the Resolute, The Duke, Rebel Sentry |
| 77 | MISSING EFFECT | up to n … | 8 | 15 | 33 | Wasp, Shrinking Savior, Restless Vinestalk, Kaito, Dancing Shadow |
| 78 | MISSING EFFECT | discard your hand … | 8 | 15 | 31 | Pyretic Charge, Bedlam Reveler, Balin, Loremaster |
| 79 | MISSING EFFECT | discard n … | 8 | 13 | 26 | Witch's Mark, Seasoned Pyromancer, Party Thrasher |
| 80 | MISSING EFFECT | exile it … | 8 | 13 | 22 | Eye of the Storm, Myrkul, Lord of Bones, Brenard, Ginger Sculptor |

## Largest clusters (Commander cards affected)

| # | Category | Cluster | Commander cards | Only missing piece for | Commanders | Examples |
|---|---|---|---|---|---|---|
| 1 | MISSING EFFECT | draw n … | 580 | 211 | 61 | Errand-Rider of Gondor, Krovikan Sorcerer, Heal |
| 2 | MISSING EFFECT | choose n … | 555 | 49 | 65 | Road of Return, Saheeli's Artistry, Dawnbringer Cleric |
| 3 | MISSING SELECTOR | target | 327 | 194 | 34 | Cinder Elemental, Archangel of Wrath, Chain of Plasma |
| 4 | MISSING COST / PERMISSION RULE | As an additional cost to cast … | 312 | 35 | 6 | Thunderherd Migration, Mind Extraction, Harvest Pyre |
| 5 | MISSING EFFECT | ~ deals n … | 308 | 196 | 15 | Deem Worthy, End-Blaze Epiphany, Harvest Pyre |
| 6 | MISSING EFFECT | search your library for … | 259 | 168 | 16 | Safewright Quest, Thunderherd Migration, Squadron Hawk |
| 7 | MISSING EFFECT | create n … | 253 | 149 | 36 | Summon the School, Cogwork Assembler, Endless Evil |
| 8 | MISSING REPLACEMENT PATTERN | As ~ enters, … | 237 | 47 | 4 | Kindred Discovery, Utopia Sprawl, Game Trail |
| 9 | MISSING EFFECT | until end of turn … | 227 | 154 | 23 | Divergent Growth, Doorman, Strength of Will |
| 10 | MISSING EFFECT | look at the top … | 211 | 153 | 38 | Harald, King of Skemfar, Lantern of Revealing, Puresight Merrow |
| 11 | MISSING SELECTOR | target creatures | 208 | 106 | 9 | Ravenous Gigantotherium, Fire Covenant, Amazing Acrobatics |
| 12 | MISSING EFFECT | put a ±n/±n counter(s) … | 202 | 140 | 53 | Greta, Sweettooth Scourge, Yorvo, Lord of Garenbrig, Ent-Draught Basin |
| 13 | MISSING EFFECT | destroy target … | 195 | 117 | 4 | Kalitas, Bloodchief of Ghet, Raze, Unliving Psychopath |
| 14 | MISSING EFFECT | target creature you control … | 178 | 124 | 10 | Blessed Defiance, Hard-Hitting Question, Crowd of True Believers |
| 15 | MISSING SELECTOR | target creature card | 174 | 116 | 25 | Hua Tuo, Honored Physician, Puppeteer Clique, Metamorphosis Fanatic |
| 16 | MISSING EFFECT | target creature gets ±n/±n … | 170 | 100 | 3 | Stern Marshal, Spontaneous Flight, Rig for War |
| 17 | MISSING EFFECT | pay {m} … | 166 | 108 | 53 | Labyrinth Adversary, Minion Reflector, Giant's Amulet |
| 18 | MISSING EFFECT | put n … | 148 | 92 | 28 | Black Sun's Zenith, Breaking // Entering, Mind Raker |
| 19 | MISSING CONTINUOUS EFFECT | ~'s power and toughness are each … | 127 | 65 | 28 | Eluge, the Shoreless Sea, Flora Colossus, Revenant |
| 20 | MISSING EFFECT | if ~ … | 126 | 71 | 16 | Warden of the First Tree, Blinkmoth Urn, Mad Dog |
| 21 | MISSING EFFECT | return ~ … | 126 | 84 | 14 | Summon the School, Dragon Fangs, Haunted Dead |
| 22 | MISSING CONTINUOUS EFFECT | ~ gets ±N/±N for each … | 115 | 58 | 32 | Nim Lasher, Benalish Honor Guard, Anya, Merciless Angel |
| 23 | MISSING SELECTOR | target player or planeswalker | 110 | 78 | 5 | Goblin Barrage, Scorching Missile, Consuming Sinkhole |
| 24 | MANA ABILITY WORDING | {M}, … | 108 | 78 | 6 | Saltcrusted Steppe, Cabal Stronghold, Interplanar Beacon |
| 25 | MISSING EFFECT | exile the top card … | 106 | 47 | 33 | Moonring Mirror, Professional Face-Breaker, Mezzio Mugger |
| 26 | MISSING EFFECT | mill n … | 102 | 62 | 18 | Sparring Dummy, Beluna Grandsquall // Seek Thrills, Cache Grab |
| 27 | MISSING EFFECT | exile target … | 102 | 68 | 5 | Astarion's Thirst, Deadly Rollick, Tawnos's Coffin |
| 28 | MISSING MECHANIC | ward | 97 | 11 | 47 | Tyranid Harridan, Grey Host Reinforcements, Kwia Vigorbloom |
| 29 | MISSING EFFECT | if n … | 92 | 60 | 24 | Airdrop Aeronauts, Hot Pursuit, Kotis, Sibsig Champion |
| 30 | MISSING EFFECT | you gain n … | 91 | 65 | 7 | Shu Farmer, Essence Pulse, Smitten Swordmaster // Curry Favor |
| 31 | MISSING EFFECT | gain control of target … | 85 | 58 | 10 | Sauron, the Lidless Eye, New Blood, Unwilling Recruit |
| 32 | MISSING EFFECT | create a n/n green … | 83 | 46 | 9 | Rhonas's Last Stand, Choco-Comet, Fractal Harness |
| 33 | MISSING EFFECT | choose target … | 82 | 69 | 9 | Arcbond, Deglamer, Wreck Hunter |
| 34 | MISSING TRIGGER EVENT | When you cast ~ | 80 | 28 | 18 | Empyrial Storm, The Fourteenth Doctor, Ulamog, the Ceaseless Hunger |
| 35 | MISSING SELECTOR | target opponent reveals their hand | 79 | 53 | 1 | Gix's Caress, Mindclaw Shaman, Grief |
| 36 | MISSING SELECTOR | target card | 76 | 44 | 3 | Barkform Harvester, Carrion Locust, Heritage Reclamation |
| 37 | MISSING EFFECT | reveal the top n … | 74 | 55 | 9 | Green Sun's Twilight, Benefaction of Rhonas, Karn, Scion of Urza |
| 38 | MISSING EFFECT | if there are n … | 74 | 30 | 6 | Locked in the Cemetery, Sanguine Spy, Extricator of Sin // Extricator of Flesh |
| 39 | MISSING EFFECT | return target … | 73 | 43 | 1 | Surging Aether, Perilous Voyage, Geistwave |
| 40 | MISSING EFFECT | tap target … | 72 | 42 | 4 | Spider-Woman, Secret Agent, Guardian of Tazeem, Gilded Scuttler |
| 41 | MISSING EFFECT | cast ~ … | 72 | 0 | 1 | Twice Upon a Time // Unlikely Meeting, Defiant Stand, Asinine Antics |
| 42 | UNSUPPORTED ORACLE PATTERN | ~ costs {M} less to cast … | 71 | 37 | 19 | Bedlam Reveler, Gargantuan Leech, Hamza, Guardian of Arashin |
| 43 | MISSING EFFECT | it deals n … | 70 | 56 | 3 | Goblin Chainwhirler, Festering Evil, Unsparing Boltcaster |
| 44 | MISSING CONTINUOUS EFFECT | ~'s power is equal to the … | 67 | 29 | 15 | Uurg, Spawn of Turg, Snow Villiers, Nethergoyf |
| 45 | MISSING EFFECT | if you control n … | 67 | 43 | 8 | Dawnhart Wardens, Boundary Lands Ranger, Dispatch |
| 46 | MISSING EFFECT | transform ~ … | 65 | 22 | 23 | Ulvenwald Captive // Ulvenwald Abomination, Westvale Abbey // Ormendahl, Profane Prince, Seraph of New Capenna // Seraph of New Phyrexia |
| 47 | MISSING EFFECT | add {m} … | 65 | 40 | 11 | Akki Rockspeaker, Brightstone Ritual, Infernal Plunge |
| 48 | MISSING EFFECT | create a n/n colorless … | 65 | 37 | 7 | Karn, Scion of Urza, Stalactite Dagger, Serpent Generator |
| 49 | MANA ABILITY WORDING | {M}: Add N mana of any … | 65 | 36 | 2 | Flywheel Racer, Pit of Offerings, Helga, Skittish Seer |
| 50 | MISSING EFFECT | create a n/n white … | 62 | 35 | 14 | Empyrial Storm, Drag the Canal, Ajani Resolute |

## Top Commander features to implement next

Ranked by pod cards, pod commanders, cards for which it is the only missing piece, then Commander cards needing it.

| # | Feature | Kind | Pod cards | Commander cards | Only missing piece for | Examples |
|---|---|---|---|---|---|---|
| 1 | mana:ability | engine | 0 | 367 | 241 | Saltcrusted Steppe, Flywheel Racer, The Emperor of Palamecia // The Lord Master of Hell |
| 2 | template:Enchanted creature has “…” | continuous | 0 | 28 | 22 | Ghostly Touch, Mark of Sakiko, Unquenchable Fury |
| 3 | template:~ enters prepared. | static | 0 | 40 | 21 | Adventurous Eater // Have a Bite, Maelstrom Artisan // Rocket Volley, Fatehold Chronologist // Peer Review |
| 4 | keyword:bestow | keyword | 0 | 42 | 20 | Leafcrown Dryad, Baleful Eidolon, Observant Alseid |
| 5 | keyword:foretell | keyword | 0 | 51 | 19 | The Foretold Soldier, Rise of the Dread Marn, Green Slime |
| 6 | keyword:banding | keyword | 0 | 24 | 19 | Nalathni Dragon, Mishra's War Machine, Kjeldoran Escort |
| 7 | template:Commander creatures you own have “…” | continuous | 0 | 19 | 19 | Dungeon Delver, Scion of Halaster, Noble Heritage |
| 8 | keyword:enchant | keyword | 0 | 67 | 16 | Utopia Sprawl, One with the Stars, Corrupted Roots |
| 9 | keyword:equip | keyword | 0 | 49 | 16 | Bloodthorn Flail, Strong Back, Team Pennant |
| 10 | keyword:splice | keyword | 0 | 30 | 16 | Evermind, Horobi's Whisper, Desperate Ritual |
| 11 | template:When ~ enters, attach it to target creature you control. | triggered | 0 | 30 | 16 | Maul of the Skyclaves, Meltstrider's Gear, Bramble Armor |
| 12 | template:Equipped creature has “…” | continuous | 0 | 24 | 16 | Field-Tested Frying Pan, Sorcerer's Wand, Fishing Pole |
| 13 | keyword:warp | keyword | 0 | 31 | 15 | Starbreach Whale, Knight Luminary, Loading Zone |
| 14 | template:Modular N | static | 0 | 23 | 15 | Arcbound Whelp, Arcbound Javelineer, Arcbound Hybrid |
| 15 | keyword:backup | keyword | 0 | 25 | 14 | Saiba Cryptomancer, Chomping Kavu, Consuming Aetherborn |
| 16 | template:{M}: Return ~ from your graveyard to your hand. | activated | 0 | 22 | 14 | The Sound of Drums, Merchant of Many Hats, Convenient Target |
| 17 | template:~ can't be blocked by creatures with power N or less. | restriction | 0 | 32 | 13 | Glinting Creeper, Dread Linnorm // Scale Deflection, Chomping Kavu |
| 18 | keyword:encore | keyword | 0 | 26 | 13 | Impulsivity, Sliver Gravemother, Belonging |
| 19 | template:−N: You get an emblem with “…” | loyalty | 0 | 64 | 12 | Zariel, Archduke of Avernus, Elspeth, Sun's Champion, Teferi, Temporal Archmage |
| 20 | keyword:overload | keyword | 0 | 27 | 12 | Mizzium Skin, Corporeal Projection, Mind Rake |
| 21 | keyword:sneak | keyword | 0 | 27 | 12 | Turncoat Kunoichi, Michelangelo, Improviser, Donatello's Technique |
| 22 | keyword:myriad | keyword | 0 | 23 | 12 | The Master, Multiplied, Sumala Rumblers, Conclave Evangelist |
| 23 | template:When ~ is put into a graveyard from the battlefield, return it to its owner's hand. | triggered | 0 | 20 | 12 | Spine of Ish Sah, Slow Motion, Fiery Mantle |
| 24 | keyword:unleash | keyword | 0 | 15 | 12 | Rakdos Drake, Grim Roustabout, Chaos Imps |
| 25 | template:All Slivers have “…” | continuous | 0 | 12 | 12 | Magma Sliver, Basal Sliver, Mesmeric Sliver |
| 26 | keyword:ward | keyword | 0 | 97 | 11 | Tyranid Harridan, Grey Host Reinforcements, Kwia Vigorbloom |
| 27 | keyword:disguise | keyword | 0 | 43 | 11 | Boltbender, Nightdrinker Moroii, Concealed Weapon |
| 28 | keyword:ninjutsu | keyword | 0 | 35 | 11 | Higure, the Still Wind, Moonblade Shinobi, Mist-Syndicate Naga |
| 29 | keyword:entwine | keyword | 0 | 32 | 11 | Road of Return, Rain of Rust, Blinding Beam |
| 30 | template:Equipped creature gets ±N/±N and has “…” | continuous | 0 | 18 | 11 | Giant's Amulet, Dire Flail // Dire Blunderbuss, Citizen's Crowbar |
| 31 | keyword:umbra armor | keyword | 0 | 15 | 11 | Felidar Umbra, Drake Umbra, Hyena Umbra |
| 32 | keyword:offspring | keyword | 0 | 20 | 10 | Splash Lasher, Rust-Shield Rampager, Prosperous Bandit |
| 33 | keyword:mentor | keyword | 0 | 19 | 10 | Hammer Dropper, Legion Warboss, Tributary Instructor |
| 34 | keyword:prototype | keyword | 0 | 19 | 10 | Goring Warplow, Combat Thresher, Woodcaller Automaton |
| 35 | template:Scavenge {M} | static | 0 | 14 | 10 | Terrus Wurm, Deadbridge Goliath, Dodgy Jalopy |
| 36 | keyword:rampage | keyword | 0 | 12 | 10 | Craw Giant, Balduvian War-Makers, Varchild's War-Riders |
| 37 | template:{M}, Sacrifice ~: It deals N damage to any target. | activated | 0 | 12 | 10 | Fireforger's Puzzleknot, Lightning Spear, Pyrite Spellbomb |
| 38 | template:Enchanted land has “…” | continuous | 0 | 11 | 10 | Chamber of Manipulation, Discreet Retreat, Farmstead |
| 39 | template:~ enters tapped unless you control N or fewer other lands. | replacement | 0 | 11 | 10 | Concealed Courtyard, Inspiring Vantage, Blackcleave Cliffs |
| 40 | template:~ enters tapped unless a player has N or less life. | replacement | 0 | 10 | 10 | Abandoned Campground, Raucous Carnival, Strangled Cemetery |
| 41 | template:~ enters tapped unless you control N or more basic lands. | replacement | 0 | 10 | 10 | Sodden Verdure, Smoldering Marsh, Vernal Fen |
| 42 | template:~ enters tapped unless you control N or more other lands. | replacement | 0 | 10 | 10 | Rockfall Vale, Stormcarved Coast, Sundown Pass |
| 43 | template:~ enters tapped unless you control a planeswalker. | replacement | 0 | 10 | 10 | Theorix Annex, Stingerquill Annex, Konstrari Annex |
| 44 | template:~ enters tapped unless you have N or more opponents. | replacement | 0 | 10 | 10 | Spire Garden, Sea of Clouds, Bountiful Promenade |
| 45 | template:You control enchanted creature. | static | 0 | 28 | 9 | Spirit Away, Illusory Gains, Biting Tether |
| 46 | keyword:cumulative upkeep | keyword | 0 | 23 | 9 | Varchild's War-Riders, Aboroth, Inner Sanctum |
| 47 | keyword:living weapon | keyword | 0 | 19 | 9 | Nettlecyst, Lashwrithe, Skinwing |
| 48 | keyword:extort | keyword | 0 | 17 | 9 | Syndicate Heavy, Tithe Drinker, Kingpin's Pet |
| 49 | keyword:fading | keyword | 0 | 17 | 9 | Parallax Wave, Phyrexian Prowler, Skyshroud Ridgeback |
| 50 | keyword:retrace | keyword | 0 | 17 | 9 | Flame Jab, Monstrify, Waves of Aggression |
| 51 | template:Prevent all combat damage that would be dealt this turn. | prevention | 0 | 14 | 9 | Jaheira's Respite, Fog, Darkness |
| 52 | template:{M}, {M}, Sacrifice ~: It deals N damage to target creature. | activated | 0 | 11 | 9 | Vial of Dragonfire, Flamecast Wheel, Mouth of Ronom |
| 53 | keyword:kicker | keyword | 0 | 37 | 8 | Goblin Barrage, Archangel of Wrath, Anavolver |
| 54 | keyword:evolve | keyword | 0 | 22 | 8 | Adaptive Snapjaw, Shambleshark, Tyranid Prime |
| 55 | keyword:vanishing | keyword | 0 | 20 | 8 | Soultether Golem, Deadly Grub, Reality Acid |
| 56 | keyword:replicate | keyword | 0 | 19 | 8 | Consign to Memory, Psionic Ritual, Lose Focus |
| 57 | template:~'s power and toughness are each equal to the number of lands you control. | characteristic_defining | 0 | 17 | 8 | Flora Colossus, Rubblehulk, Harmonious Grovestrider |
| 58 | keyword:embalm | keyword | 0 | 15 | 8 | Heart-Piercer Manticore, Angel of Sanctions, Anointer Priest |
| 59 | template:Graft N | static | 0 | 13 | 8 | Cytoplast Manipulator, Sporeback Troll, Vigean Hydropon |
| 60 | keyword:enlist | keyword | 0 | 12 | 8 | Keldon Flamesage, Benalish Faithbonder, Aradesh, the Founder |

## Coverage by card type

| Type | FULL | PARTIAL | REVIEW | MANUAL |
|---|---|---|---|---|
| Creature | 6031 | 11890 | 0 | 0 |
| Artifact | 960 | 2633 | 0 | 0 |
| Enchantment | 748 | 2899 | 0 | 0 |
| Sorcery | 828 | 2740 | 0 | 0 |
| Instant | 1099 | 2655 | 0 | 0 |
| Land | 525 | 687 | 0 | 0 |
| Planeswalker | 12 | 299 | 0 | 0 |
| Battle | 0 | 36 | 0 | 0 |

## Rules features in the pool (ability lines)

triggered 14909, keyword 14134, spell_effect 9120, activated 7358, continuous 4014, static 3053, mana_ability 2038, replacement 1966, restriction 1474, loyalty 882, prevention 320, additional_cost 307, cost_modifier 261, characteristic_defining 247, permission 207, alternative_cost 180

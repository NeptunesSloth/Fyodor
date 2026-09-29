# Commander rules coverage

Card data: Scryfall `2026-09-28T21:01:54.353+00:00` · Comprehensive Rules 2026-09-25 · rules engine v2 · generated 2026-09-29 22:53

Only cards that are **legal in Commander today** count. Banned cards (83) are COMMANDER_BANNED and excluded.

## Commander coverage

Commander-legal cards: **32068**

| Level | Cards | Share |
|---|---|---|
| FULL | 10304 | 32.1% |
| PARTIAL | 21764 | 67.9% |
| REVIEW | 0 | 0.0% |
| MANUAL | 0 | 0.0% |

Possible commanders (CR 903.3/903.3a, incl. Backgrounds): **3501** — FULL 478, PARTIAL 3023, REVIEW 0, MANUAL 0

## Pod coverage

No pod decks in the inventory yet (`python -m tools.rules_inventory`); the queue below is ranked by Commander-legal cards unlocked.

## Coverage quality

- Ability features (lines, keywords, play/cast/combat) across Commander-legal cards: 113154
- Automated: 82360 (72.8%) · unrecognized clauses: 30794
- Oracle text classified (automated, or sorted into a concrete missing capability): 97.6% · unclassified clauses: 2687
- Distinct missing-capability clusters: 8339

## Missing capabilities by category

| Category | Cards affected | Clauses |
|---|---|---|
| MISSING EFFECT | 11625 | 13657 |
| MISSING SELECTOR | 3501 | 3706 |
| MISSING TRIGGER EVENT | 2403 | 2515 |
| MISSING CONTINUOUS EFFECT | 2169 | 2293 |
| UNSUPPORTED ORACLE PATTERN | 2031 | 2687 |
| MISSING MECHANIC | 1816 | 1878 |
| MISSING REPLACEMENT PATTERN | 1362 | 1401 |
| MISSING RESTRICTION | 937 | 983 |
| MISSING COST / PERMISSION RULE | 800 | 810 |
| MISSING COST | 485 | 498 |
| MANA ABILITY WORDING | 364 | 366 |

## Highest-payoff clusters

Ranked by pod cards, pod commanders, possible commanders affected, cards it alone would unlock, then all Commander cards needing it.

| # | Category | Cluster | Commanders | Only missing piece for | Commander cards | Examples |
|---|---|---|---|---|---|---|
| 1 | MISSING EFFECT | draw n … | 66 | 224 | 590 | Errand-Rider of Gondor, Krovikan Sorcerer, Heal |
| 2 | MISSING EFFECT | choose n … | 65 | 50 | 561 | Road of Return, Saheeli's Artistry, Dawnbringer Cleric |
| 3 | MISSING EFFECT | put a ±n/±n counter(s) … | 61 | 160 | 231 | Greta, Sweettooth Scourge, Yorvo, Lord of Garenbrig, Ent-Draught Basin |
| 4 | MISSING EFFECT | pay {m} … | 56 | 120 | 177 | Labyrinth Adversary, Minion Reflector, Giant's Amulet |
| 5 | MISSING MECHANIC | ward | 47 | 13 | 97 | Tyranid Harridan, Grey Host Reinforcements, Kwia Vigorbloom |
| 6 | MISSING EFFECT | look at the top … | 39 | 160 | 217 | Harald, King of Skemfar, Lantern of Revealing, Puresight Merrow |
| 7 | MISSING EFFECT | create n … | 39 | 157 | 258 | Summon the School, Cogwork Assembler, Endless Evil |
| 8 | MISSING SELECTOR | target | 36 | 204 | 331 | Cinder Elemental, Archangel of Wrath, Chain of Plasma |
| 9 | MISSING CONTINUOUS EFFECT | ~ gets ±N/±N for each … | 32 | 58 | 115 | Nim Lasher, Benalish Honor Guard, Anya, Merciless Angel |
| 10 | MISSING EFFECT | put n … | 28 | 97 | 150 | Black Sun's Zenith, Breaking // Entering, Mind Raker |
| 11 | MISSING CONTINUOUS EFFECT | ~'s power and toughness are each … | 28 | 68 | 127 | Eluge, the Shoreless Sea, Flora Colossus, Revenant |
| 12 | MISSING EFFECT | exile the top card … | 26 | 30 | 66 | Moonring Mirror, Mezzio Mugger, Etali, Primal Storm |
| 13 | MISSING SELECTOR | target creature card | 25 | 117 | 174 | Hua Tuo, Honored Physician, Puppeteer Clique, Metamorphosis Fanatic |
| 14 | MISSING EFFECT | if n … | 24 | 60 | 92 | Airdrop Aeronauts, Hot Pursuit, Kotis, Sibsig Champion |
| 15 | MISSING EFFECT | until end of turn … | 23 | 158 | 227 | Divergent Growth, Doorman, Strength of Will |
| 16 | MISSING EFFECT | transform ~ … | 23 | 26 | 70 | Ulvenwald Captive // Ulvenwald Abomination, Westvale Abbey // Ormendahl, Profane Prince, Seraph of New Capenna // Seraph of New Phyrexia |
| 17 | UNSUPPORTED ORACLE PATTERN | As long as your devotion to … | 22 | 7 | 22 | Phenax, God of Deception, Erebos, God of the Dead, Thassa, Deep-Dwelling |
| 18 | MISSING EFFECT | exile ~ … | 20 | 13 | 61 | Stenn, Paranoid Partisan, Woodland Guidance, Teferi's Protection |
| 19 | MISSING EFFECT | if ~ … | 19 | 74 | 130 | Warden of the First Tree, Hixus, Prison Warden, Blinkmoth Urn |
| 20 | MISSING EFFECT | mill n … | 18 | 65 | 101 | Sparring Dummy, Loafing Giant, Beluna Grandsquall // Seek Thrills |
| 21 | MISSING TRIGGER EVENT | When you cast ~ | 18 | 30 | 80 | Empyrial Storm, The Fourteenth Doctor, Ulamog, the Ceaseless Hunger |
| 22 | MISSING EFFECT | create a n/n red … | 17 | 35 | 61 | Prosperity Tycoon, Ertha Jo, Frontier Mentor, Nesting Dragon |
| 23 | MISSING EFFECT | search your library for … | 16 | 172 | 263 | Safewright Quest, Thunderherd Migration, Squadron Hawk |
| 24 | MISSING EFFECT | create a n/n black … | 16 | 39 | 60 | Queen Brahne, Grist, the Hunger Tide, Mysidian Elder |
| 25 | MISSING CONTINUOUS EFFECT | Commander creatures you own have “…” | 16 | 16 | 16 | Dungeon Delver, Noble Heritage, Acolyte of Bahamut |
| 26 | MISSING CONTINUOUS EFFECT | ~'s power is equal to the … | 15 | 30 | 67 | Uurg, Spawn of Turg, Snow Villiers, Nethergoyf |
| 27 | UNSUPPORTED ORACLE PATTERN | As ~ enters, … | 15 | 1 | 19 | Stenn, Paranoid Partisan, Arachne, Psionic Weaver, Pramikon, Sky Rampart |
| 28 | UNSUPPORTED ORACLE PATTERN | More Than Meets the Eye {M} | 15 | 0 | 15 | Optimus Prime, Hero // Optimus Prime, Autobot Leader, Megatron, Tyrant // Megatron, Destructive Force, Jetfire, Ingenious Scientist // Jetfire, Air Guardian |
| 29 | MISSING EFFECT | ~ deals n … | 14 | 210 | 318 | Deem Worthy, End-Blaze Epiphany, Harvest Pyre |
| 30 | MISSING EFFECT | return ~ … | 14 | 88 | 130 | Summon the School, Dragon Fangs, Haunted Dead |
| 31 | MISSING EFFECT | create a n/n white … | 14 | 40 | 65 | Empyrial Storm, Drag the Canal, Ajani Resolute |
| 32 | UNSUPPORTED ORACLE PATTERN | ~ costs {M} less to cast … | 14 | 26 | 47 | Bedlam Reveler, Gargantuan Leech, Cryptic Serpent |
| 33 | MISSING MECHANIC | sneak | 14 | 12 | 27 | Turncoat Kunoichi, Michelangelo, Improviser, Donatello's Technique |
| 34 | MISSING MECHANIC | firebending | 14 | 8 | 22 | Fire Sages, Loyal Fire Sage, Jeong Jeong, the Deserter |
| 35 | MISSING MECHANIC | partner | 14 | 5 | 24 | Lore Weaver, Blaring Captain, Rory Williams |
| 36 | UNSUPPORTED ORACLE PATTERN | • Put a ±N/±N counter(s) on … | 14 | 0 | 38 | Bejeweled Warg, Trusty Retriever, Inspired Inventor |
| 37 | MISSING EFFECT | add {m} … | 13 | 42 | 70 | Waste Not, Akki Rockspeaker, Brightstone Ritual |
| 38 | UNSUPPORTED ORACLE PATTERN | Living metal | 13 | 0 | 13 | Optimus Prime, Hero // Optimus Prime, Autobot Leader, Megatron, Tyrant // Megatron, Destructive Force, Jetfire, Ingenious Scientist // Jetfire, Air Guardian |
| 39 | MISSING RESTRICTION | ~ can't be blocked by creatures … | 12 | 28 | 56 | Lydia Frye, Pompous Gadabout, Ghost of Ramirez DePietro |
| 40 | MISSING SELECTOR | target equipment | 12 | 18 | 26 | Stolen Uniform, Shagrat, Loot Bearer, Thor, God of Thunder |
| 41 | UNSUPPORTED ORACLE PATTERN | Power-up — {M}: Put N ±N/±N … | 12 | 12 | 19 | Thanos, the Mad Titan, Shang-Chi, Martial Mentor, Hulk, Gamma Goliath |
| 42 | MISSING EFFECT | target creature you control … | 11 | 124 | 179 | Blessed Defiance, Hard-Hitting Question, Crowd of True Believers |
| 43 | MISSING TRIGGER EVENT | Whenever you cast a historic spell | 11 | 15 | 19 | Serra Disciple, Cabal Paladin, Glóin, Dwarf Emissary |
| 44 | MISSING EFFECT | earthbend n … | 11 | 14 | 27 | Earth Village Ruffians, Bumi, Unleashed, Badgermole |
| 45 | MISSING EFFECT | another target … | 11 | 14 | 23 | Hemosymbic Mite, Syr Faren, the Hengehammer, Pippin, Guard of the Citadel |
| 46 | MISSING EFFECT | if you've cast a … | 11 | 5 | 12 | H.E.R.B.I.E., Lovable Robot, Invisible Woman, Alicia Masters, Skilled Sculptor |
| 47 | MISSING EFFECT | gain control of target … | 10 | 58 | 85 | Sauron, the Lidless Eye, New Blood, Unwilling Recruit |
| 48 | MISSING EFFECT | reveal the top card … | 10 | 36 | 48 | Rashmi, Eternities Crafter, Counterbalance, Sorin, Grim Nemesis |
| 49 | MISSING SELECTOR | target creature card with mana value | 10 | 26 | 39 | General Leo Cristophe, Yathan Roadwatcher, Lazotep Quarry |
| 50 | MISSING SELECTOR | target instant or sorcery card | 10 | 20 | 35 | Ogre Battlecaster, Flood of Recollection, Impulsivity |
| 51 | MISSING EFFECT | exile the top n … | 10 | 18 | 47 | Duplicity, Memorial Vault, Crossover Collaboration |
| 52 | MISSING RESTRICTION | ~ can't attack or block unless … | 10 | 16 | 23 | Sab-Sunen, Luxa Embodied, Relic Golem, Hollow Warrior |
| 53 | MISSING EFFECT | return it to the … | 10 | 11 | 23 | Bronzehide Lion, Optimus Prime, Hero // Optimus Prime, Autobot Leader, Yedora, Grave Gardener |
| 54 | MISSING COST / PERMISSION RULE | You may cast ~ from your … | 10 | 10 | 25 | Marang River Prowler, Quilled Greatwurm, Gravecrawler |
| 55 | MISSING COST / PERMISSION RULE | Once during each of your turns, … | 10 | 8 | 14 | Kotis, Sibsig Champion, One with the Multiverse, Jacob Hauken, Inspector // Hauken's Insight |
| 56 | MISSING SELECTOR | target creatures | 9 | 107 | 207 | Ravenous Gigantotherium, Fire Covenant, Amazing Acrobatics |
| 57 | MISSING EFFECT | choose target … | 9 | 71 | 83 | Arcbond, Deglamer, Wreck Hunter |
| 58 | MISSING EFFECT | you gain n … | 9 | 68 | 94 | Belladonna Took, Shu Farmer, Essence Pulse |
| 59 | MISSING EFFECT | reveal the top n … | 9 | 57 | 75 | Green Sun's Twilight, Benefaction of Rhonas, Karn, Scion of Urza |
| 60 | MISSING EFFECT | create a n/n green … | 9 | 47 | 84 | Rhonas's Last Stand, Choco-Comet, Fractal Harness |
| 61 | MISSING EFFECT | reveal cards from the … | 9 | 26 | 32 | Treasure Hunt, Hei Bai, Forest Guardian, Hermit Druid |
| 62 | MISSING EFFECT | exile up to n … | 9 | 17 | 26 | Salvation Swan, Liminal Hold, S.H.I.E.L.D. Flying Car |
| 63 | MISSING EFFECT | double the number of … | 9 | 12 | 24 | Fractal Harness, Primordial Hydra, The Millennium Calendar |
| 64 | MISSING CONTINUOUS EFFECT | You have no maximum hand size | 9 | 8 | 23 | Nyssa of Traken, Curiosity Crafter, Wizard Class |
| 65 | UNSUPPORTED ORACLE PATTERN | Web-slinging {M} | 9 | 4 | 9 | Scarlet Spider, Ben Reilly, Arachne, Psionic Weaver, Spider-Man, Brooklyn Visionary |
| 66 | MISSING TRIGGER EVENT | When ~ enters | 9 | 2 | 9 | Niv-Mizzet Reborn, Lobelia Sackville-Baggins, Drizzt Do'Urden |
| 67 | MISSING MECHANIC | companion | 9 | 1 | 9 | Lutri, the Spellchaser, Gyruda, Doom of Depths, Lurrus of the Dream-Den |
| 68 | UNSUPPORTED ORACLE PATTERN | • ~ deals N damage to … | 9 | 0 | 18 | Arbalest Engineers, Tectonic Giant, Umaro, Raging Yeti |
| 69 | UNSUPPORTED ORACLE PATTERN | Storied | 9 | 0 | 9 | Balin, Loremaster, Dáin, Lord of the Iron Hills, Ori, Keeper of Songs |
| 70 | MISSING EFFECT | if you control n … | 8 | 40 | 64 | Dawnhart Wardens, Boundary Lands Ranger, Dispatch |
| 71 | MISSING COST | {M}, Discard ~ | 8 | 34 | 57 | Jiwari, the Earth Aflame, Favor of Jukai, Radiant Solar |
| 72 | MISSING REPLACEMENT PATTERN | ~ enters with a ±N/±N counter(s) on … | 8 | 17 | 37 | Callous Sell-Sword // Burn Together, Avatar of the Resolute, The Duke, Rebel Sentry |
| 73 | MISSING EFFECT | you draw n … | 8 | 17 | 34 | Fang, Fearless l'Cie, Live Fast, Greed's Gambit |
| 74 | MISSING EFFECT | up to n … | 8 | 15 | 33 | Wasp, Shrinking Savior, Restless Vinestalk, Kaito, Dancing Shadow |
| 75 | MISSING EFFECT | discard your hand … | 8 | 15 | 31 | Pyretic Charge, Bedlam Reveler, Balin, Loremaster |
| 76 | MISSING EFFECT | discard n … | 8 | 13 | 26 | Witch's Mark, Seasoned Pyromancer, Party Thrasher |
| 77 | MISSING EFFECT | create a treasure token … | 8 | 8 | 19 | Beza, the Bounding Spring, Boxing Ring, Mahadi, Emporium Master |
| 78 | UNSUPPORTED ORACLE PATTERN | Mayhem {M} | 8 | 7 | 11 | Swarm, Being of Bees, Chameleon, Master of Disguise, Spider-Islanders |
| 79 | MISSING CONTINUOUS EFFECT | During your turn, … | 8 | 6 | 17 | Long-Lost Lances, Miriam, Herd Whisperer, Yuna, Hope of Spira |
| 80 | UNSUPPORTED ORACLE PATTERN | You may play an additional land … | 8 | 5 | 17 | Exploration, Icetill Explorer, Case of the Locked Hothouse |

## Largest clusters (Commander cards affected)

| # | Category | Cluster | Commander cards | Only missing piece for | Commanders | Examples |
|---|---|---|---|---|---|---|
| 1 | MISSING EFFECT | draw n … | 590 | 224 | 66 | Errand-Rider of Gondor, Krovikan Sorcerer, Heal |
| 2 | MISSING EFFECT | choose n … | 561 | 50 | 65 | Road of Return, Saheeli's Artistry, Dawnbringer Cleric |
| 3 | MISSING SELECTOR | target | 331 | 204 | 36 | Cinder Elemental, Archangel of Wrath, Chain of Plasma |
| 4 | MISSING EFFECT | ~ deals n … | 318 | 210 | 14 | Deem Worthy, End-Blaze Epiphany, Harvest Pyre |
| 5 | MISSING COST / PERMISSION RULE | As an additional cost to cast … | 312 | 36 | 6 | Thunderherd Migration, Mind Extraction, Harvest Pyre |
| 6 | MISSING EFFECT | search your library for … | 263 | 172 | 16 | Safewright Quest, Thunderherd Migration, Squadron Hawk |
| 7 | MISSING EFFECT | create n … | 258 | 157 | 39 | Summon the School, Cogwork Assembler, Endless Evil |
| 8 | MISSING REPLACEMENT PATTERN | As ~ enters, … | 237 | 47 | 4 | Kindred Discovery, Utopia Sprawl, Game Trail |
| 9 | MISSING EFFECT | put a ±n/±n counter(s) … | 231 | 160 | 61 | Greta, Sweettooth Scourge, Yorvo, Lord of Garenbrig, Ent-Draught Basin |
| 10 | MISSING EFFECT | until end of turn … | 227 | 158 | 23 | Divergent Growth, Doorman, Strength of Will |
| 11 | MISSING EFFECT | look at the top … | 217 | 160 | 39 | Harald, King of Skemfar, Lantern of Revealing, Puresight Merrow |
| 12 | MISSING SELECTOR | target creatures | 207 | 107 | 9 | Ravenous Gigantotherium, Fire Covenant, Amazing Acrobatics |
| 13 | MISSING EFFECT | destroy target … | 189 | 114 | 4 | Kalitas, Bloodchief of Ghet, Raze, Unliving Psychopath |
| 14 | MISSING EFFECT | target creature you control … | 179 | 124 | 11 | Blessed Defiance, Hard-Hitting Question, Crowd of True Believers |
| 15 | MISSING EFFECT | pay {m} … | 177 | 120 | 56 | Labyrinth Adversary, Minion Reflector, Giant's Amulet |
| 16 | MISSING SELECTOR | target creature card | 174 | 117 | 25 | Hua Tuo, Honored Physician, Puppeteer Clique, Metamorphosis Fanatic |
| 17 | MISSING EFFECT | target creature gets ±n/±n … | 170 | 102 | 4 | Stern Marshal, Spontaneous Flight, Rig for War |
| 18 | MISSING EFFECT | put n … | 150 | 97 | 28 | Black Sun's Zenith, Breaking // Entering, Mind Raker |
| 19 | MISSING EFFECT | if ~ … | 130 | 74 | 19 | Warden of the First Tree, Hixus, Prison Warden, Blinkmoth Urn |
| 20 | MISSING EFFECT | return ~ … | 130 | 88 | 14 | Summon the School, Dragon Fangs, Haunted Dead |
| 21 | MISSING CONTINUOUS EFFECT | ~'s power and toughness are each … | 127 | 68 | 28 | Eluge, the Shoreless Sea, Flora Colossus, Revenant |
| 22 | MISSING CONTINUOUS EFFECT | ~ gets ±N/±N for each … | 115 | 58 | 32 | Nim Lasher, Benalish Honor Guard, Anya, Merciless Angel |
| 23 | MISSING SELECTOR | target player or planeswalker | 111 | 79 | 5 | Goblin Barrage, Scorching Missile, Consuming Sinkhole |
| 24 | MANA ABILITY WORDING | {M}, … | 108 | 78 | 6 | Saltcrusted Steppe, Cabal Stronghold, Interplanar Beacon |
| 25 | MISSING EFFECT | mill n … | 101 | 65 | 18 | Sparring Dummy, Loafing Giant, Beluna Grandsquall // Seek Thrills |
| 26 | MISSING EFFECT | exile target … | 100 | 67 | 5 | Astarion's Thirst, Deadly Rollick, Tawnos's Coffin |
| 27 | MISSING MECHANIC | ward | 97 | 13 | 47 | Tyranid Harridan, Grey Host Reinforcements, Kwia Vigorbloom |
| 28 | MISSING EFFECT | you gain n … | 94 | 68 | 9 | Belladonna Took, Shu Farmer, Essence Pulse |
| 29 | MISSING EFFECT | if n … | 92 | 60 | 24 | Airdrop Aeronauts, Hot Pursuit, Kotis, Sibsig Champion |
| 30 | MISSING EFFECT | gain control of target … | 85 | 58 | 10 | Sauron, the Lidless Eye, New Blood, Unwilling Recruit |
| 31 | MISSING EFFECT | create a n/n green … | 84 | 47 | 9 | Rhonas's Last Stand, Choco-Comet, Fractal Harness |
| 32 | MISSING EFFECT | choose target … | 83 | 71 | 9 | Arcbond, Deglamer, Wreck Hunter |
| 33 | MISSING TRIGGER EVENT | When you cast ~ | 80 | 30 | 18 | Empyrial Storm, The Fourteenth Doctor, Ulamog, the Ceaseless Hunger |
| 34 | MISSING SELECTOR | target opponent reveals their hand | 79 | 53 | 1 | Gix's Caress, Mindclaw Shaman, Grief |
| 35 | MISSING EFFECT | tap target … | 78 | 45 | 4 | Spider-Woman, Secret Agent, Guardian of Tazeem, Gilded Scuttler |
| 36 | MISSING EFFECT | if there are n … | 76 | 32 | 6 | Locked in the Cemetery, Sanguine Spy, Extricator of Sin // Extricator of Flesh |
| 37 | MISSING SELECTOR | target card | 76 | 44 | 3 | Barkform Harvester, Carrion Locust, Heritage Reclamation |
| 38 | MISSING EFFECT | reveal the top n … | 75 | 57 | 9 | Green Sun's Twilight, Benefaction of Rhonas, Karn, Scion of Urza |
| 39 | MISSING EFFECT | it deals n … | 75 | 60 | 3 | Goblin Chainwhirler, Festering Evil, Unsparing Boltcaster |
| 40 | MISSING EFFECT | return target … | 72 | 44 | 1 | Surging Aether, Perilous Voyage, Geistwave |
| 41 | MISSING EFFECT | cast ~ … | 72 | 0 | 1 | Twice Upon a Time // Unlikely Meeting, Defiant Stand, Asinine Antics |
| 42 | MISSING EFFECT | transform ~ … | 70 | 26 | 23 | Ulvenwald Captive // Ulvenwald Abomination, Westvale Abbey // Ormendahl, Profane Prince, Seraph of New Capenna // Seraph of New Phyrexia |
| 43 | MISSING EFFECT | add {m} … | 70 | 42 | 13 | Waste Not, Akki Rockspeaker, Brightstone Ritual |
| 44 | MISSING CONTINUOUS EFFECT | ~'s power is equal to the … | 67 | 30 | 15 | Uurg, Spawn of Turg, Snow Villiers, Nethergoyf |
| 45 | MISSING EFFECT | create a n/n colorless … | 67 | 40 | 7 | Karn, Scion of Urza, Stalactite Dagger, Serpent Generator |
| 46 | MISSING EFFECT | exile the top card … | 66 | 30 | 26 | Moonring Mirror, Mezzio Mugger, Etali, Primal Storm |
| 47 | MISSING EFFECT | create a n/n white … | 65 | 40 | 14 | Empyrial Storm, Drag the Canal, Ajani Resolute |
| 48 | MANA ABILITY WORDING | {M}: Add N mana of any … | 65 | 37 | 2 | Flywheel Racer, Pit of Offerings, Helga, Skittish Seer |
| 49 | MISSING EFFECT | if you control n … | 64 | 40 | 8 | Dawnhart Wardens, Boundary Lands Ranger, Dispatch |
| 50 | MISSING EFFECT | exile ~ … | 61 | 13 | 20 | Stenn, Paranoid Partisan, Woodland Guidance, Teferi's Protection |

## Top Commander features to implement next

Ranked by pod cards, pod commanders, cards for which it is the only missing piece, then Commander cards needing it.

| # | Feature | Kind | Pod cards | Commander cards | Only missing piece for | Examples |
|---|---|---|---|---|---|---|
| 1 | mana:ability | engine | 0 | 364 | 248 | Saltcrusted Steppe, Flywheel Racer, The Emperor of Palamecia // The Lord Master of Hell |
| 2 | keyword:foretell | keyword | 0 | 51 | 21 | The Foretold Soldier, Rise of the Dread Marn, Green Slime |
| 3 | template:~ enters prepared. | static | 0 | 40 | 21 | Adventurous Eater // Have a Bite, Maelstrom Artisan // Rocket Volley, Fatehold Chronologist // Peer Review |
| 4 | template:Enchanted creature has “…” | continuous | 0 | 26 | 21 | Ghostly Touch, Mark of Sakiko, Unquenchable Fury |
| 5 | keyword:enchant | keyword | 0 | 67 | 20 | Utopia Sprawl, One with the Stars, Corrupted Roots |
| 6 | keyword:bestow | keyword | 0 | 42 | 20 | Leafcrown Dryad, Baleful Eidolon, Observant Alseid |
| 7 | template:When ~ enters, attach it to target creature you control. | triggered | 0 | 30 | 19 | Maul of the Skyclaves, Meltstrider's Gear, Bramble Armor |
| 8 | keyword:banding | keyword | 0 | 24 | 19 | Nalathni Dragon, Mishra's War Machine, Kjeldoran Escort |
| 9 | template:Commander creatures you own have “…” | continuous | 0 | 19 | 19 | Dungeon Delver, Scion of Halaster, Noble Heritage |
| 10 | keyword:equip | keyword | 0 | 49 | 17 | Bloodthorn Flail, Strong Back, Team Pennant |
| 11 | keyword:backup | keyword | 0 | 25 | 17 | Saiba Cryptomancer, Chomping Kavu, Consuming Aetherborn |
| 12 | keyword:splice | keyword | 0 | 30 | 16 | Evermind, Horobi's Whisper, Desperate Ritual |
| 13 | template:Equipped creature has “…” | continuous | 0 | 24 | 16 | Field-Tested Frying Pan, Sorcerer's Wand, Fishing Pole |
| 14 | keyword:warp | keyword | 0 | 31 | 15 | Starbreach Whale, Knight Luminary, Loading Zone |
| 15 | template:Modular N | static | 0 | 23 | 15 | Arcbound Whelp, Arcbound Javelineer, Arcbound Hybrid |
| 16 | template:~ can't be blocked by creatures with power N or less. | restriction | 0 | 32 | 14 | Glinting Creeper, Dread Linnorm // Scale Deflection, Chomping Kavu |
| 17 | keyword:myriad | keyword | 0 | 23 | 14 | The Master, Multiplied, Sumala Rumblers, Conclave Evangelist |
| 18 | template:{M}: Return ~ from your graveyard to your hand. | activated | 0 | 22 | 14 | The Sound of Drums, Merchant of Many Hats, Convenient Target |
| 19 | keyword:ward | keyword | 0 | 97 | 13 | Tyranid Harridan, Grey Host Reinforcements, Kwia Vigorbloom |
| 20 | keyword:encore | keyword | 0 | 26 | 13 | Impulsivity, Sliver Gravemother, Belonging |
| 21 | template:−N: You get an emblem with “…” | loyalty | 0 | 64 | 12 | Zariel, Archduke of Avernus, Elspeth, Sun's Champion, Teferi, Temporal Archmage |
| 22 | keyword:ninjutsu | keyword | 0 | 35 | 12 | Higure, the Still Wind, Moonblade Shinobi, Mist-Syndicate Naga |
| 23 | keyword:overload | keyword | 0 | 27 | 12 | Mizzium Skin, Corporeal Projection, Mind Rake |
| 24 | keyword:sneak | keyword | 0 | 27 | 12 | Turncoat Kunoichi, Michelangelo, Improviser, Donatello's Technique |
| 25 | keyword:unleash | keyword | 0 | 15 | 12 | Rakdos Drake, Grim Roustabout, Chaos Imps |
| 26 | keyword:disguise | keyword | 0 | 43 | 11 | Boltbender, Nightdrinker Moroii, Concealed Weapon |
| 27 | keyword:entwine | keyword | 0 | 32 | 11 | Road of Return, Rain of Rust, Blinding Beam |
| 28 | template:{M}: Adapt N. | activated | 0 | 22 | 11 | Zegana, Utopian Speaker, Temperamental Oozewagg, Evolution Witness |
| 29 | keyword:offspring | keyword | 0 | 20 | 11 | Splash Lasher, Rust-Shield Rampager, Prosperous Bandit |
| 30 | keyword:living weapon | keyword | 0 | 19 | 11 | Nettlecyst, Lashwrithe, Skinwing |
| 31 | keyword:umbra armor | keyword | 0 | 15 | 11 | Felidar Umbra, Drake Umbra, Hyena Umbra |
| 32 | template:All Slivers have “…” | continuous | 0 | 11 | 11 | Magma Sliver, Basal Sliver, Mesmeric Sliver |
| 33 | keyword:evolve | keyword | 0 | 22 | 10 | Adaptive Snapjaw, Shambleshark, Tyranid Prime |
| 34 | keyword:mentor | keyword | 0 | 19 | 10 | Hammer Dropper, Legion Warboss, Tributary Instructor |
| 35 | keyword:prototype | keyword | 0 | 19 | 10 | Goring Warplow, Combat Thresher, Woodcaller Automaton |
| 36 | keyword:retrace | keyword | 0 | 17 | 10 | Flame Jab, Monstrify, Waves of Aggression |
| 37 | keyword:embalm | keyword | 0 | 15 | 10 | Heart-Piercer Manticore, Angel of Sanctions, Anointer Priest |
| 38 | template:Scavenge {M} | static | 0 | 14 | 10 | Terrus Wurm, Deadbridge Goliath, Dodgy Jalopy |
| 39 | keyword:rampage | keyword | 0 | 12 | 10 | Craw Giant, Balduvian War-Makers, Varchild's War-Riders |
| 40 | template:{M}, Sacrifice ~: It deals N damage to any target. | activated | 0 | 12 | 10 | Fireforger's Puzzleknot, Lightning Spear, Pyrite Spellbomb |
| 41 | template:Enchanted land has “…” | continuous | 0 | 11 | 10 | Chamber of Manipulation, Discreet Retreat, Farmstead |
| 42 | template:~ enters tapped unless you control N or fewer other lands. | replacement | 0 | 11 | 10 | Concealed Courtyard, Inspiring Vantage, Blackcleave Cliffs |
| 43 | template:~ enters tapped unless a player has N or less life. | replacement | 0 | 10 | 10 | Abandoned Campground, Raucous Carnival, Strangled Cemetery |
| 44 | template:~ enters tapped unless you control N or more basic lands. | replacement | 0 | 10 | 10 | Sodden Verdure, Smoldering Marsh, Vernal Fen |
| 45 | template:~ enters tapped unless you control N or more other lands. | replacement | 0 | 10 | 10 | Rockfall Vale, Stormcarved Coast, Sundown Pass |
| 46 | template:~ enters tapped unless you control a planeswalker. | replacement | 0 | 10 | 10 | Theorix Annex, Stingerquill Annex, Konstrari Annex |
| 47 | template:~ enters tapped unless you have N or more opponents. | replacement | 0 | 10 | 10 | Spire Garden, Sea of Clouds, Bountiful Promenade |
| 48 | template:You control enchanted creature. | static | 0 | 28 | 9 | Spirit Away, Illusory Gains, Biting Tether |
| 49 | keyword:cumulative upkeep | keyword | 0 | 23 | 9 | Varchild's War-Riders, Aboroth, Inner Sanctum |
| 50 | keyword:vanishing | keyword | 0 | 20 | 9 | Soultether Golem, Deadly Grub, Reality Acid |
| 51 | keyword:extort | keyword | 0 | 17 | 9 | Syndicate Heavy, Tithe Drinker, Kingpin's Pet |
| 52 | keyword:fading | keyword | 0 | 17 | 9 | Parallax Wave, Phyrexian Prowler, Skyshroud Ridgeback |
| 53 | template:Prevent all combat damage that would be dealt this turn. | prevention | 0 | 14 | 9 | Jaheira's Respite, Fog, Darkness |
| 54 | template:{M}, {M}, Sacrifice ~: It deals N damage to target creature. | activated | 0 | 11 | 9 | Vial of Dragonfire, Flamecast Wheel, Mouth of Ronom |
| 55 | keyword:kicker | keyword | 0 | 37 | 8 | Goblin Barrage, Archangel of Wrath, Anavolver |
| 56 | keyword:plot | keyword | 0 | 33 | 8 | Unscrupulous Contractor, Pyretic Charge, Freestrider Commando |
| 57 | template:You have no maximum hand size. | continuous | 0 | 23 | 8 | Nyssa of Traken, Curiosity Crafter, Wizard Class |
| 58 | keyword:firebending | keyword | 0 | 22 | 8 | Fire Sages, Loyal Fire Sage, Jeong Jeong, the Deserter |
| 59 | keyword:replicate | keyword | 0 | 19 | 8 | Consign to Memory, Psionic Ritual, Lose Focus |
| 60 | template:~'s power and toughness are each equal to the number of lands you control. | characteristic_defining | 0 | 17 | 8 | Flora Colossus, Rubblehulk, Harmonious Grovestrider |

## Coverage by card type

| Type | FULL | PARTIAL | REVIEW | MANUAL |
|---|---|---|---|---|
| Creature | 6476 | 11445 | 0 | 0 |
| Artifact | 1034 | 2559 | 0 | 0 |
| Enchantment | 857 | 2790 | 0 | 0 |
| Sorcery | 846 | 2722 | 0 | 0 |
| Instant | 1137 | 2617 | 0 | 0 |
| Land | 528 | 684 | 0 | 0 |
| Planeswalker | 12 | 299 | 0 | 0 |
| Battle | 0 | 36 | 0 | 0 |

## Rules features in the pool (ability lines)

triggered 14909, keyword 14139, spell_effect 9115, activated 7339, continuous 3999, static 2899, mana_ability 2035, replacement 1966, restriction 1474, loyalty 882, prevention 320, additional_cost 307, cost_modifier 261, characteristic_defining 247, permission 206, alternative_cost 180

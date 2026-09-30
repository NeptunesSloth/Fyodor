# Commander rules coverage

Card data: Scryfall `2026-09-28T21:01:54.353+00:00` · Comprehensive Rules 2026-09-25 · rules engine v2 · generated 2026-09-30 08:21

Only cards that are **legal in Commander today** count. Banned cards (83) are COMMANDER_BANNED and excluded.

## Commander coverage

Commander-legal cards: **32068**

| Level | Cards | Share |
|---|---|---|
| FULL | 11181 | 34.9% |
| PARTIAL | 20887 | 65.1% |
| REVIEW | 0 | 0.0% |
| MANUAL | 0 | 0.0% |

Possible commanders (CR 903.3/903.3a, incl. Backgrounds): **3501** — FULL 551, PARTIAL 2950, REVIEW 0, MANUAL 0

## Pod coverage

No pod decks in the inventory yet (`python -m tools.rules_inventory`); the queue below is ranked by Commander-legal cards unlocked.

## Coverage quality

- Ability features (lines, keywords, play/cast/combat) across Commander-legal cards: 113154
- Automated: 83733 (74.0%) · unrecognized clauses: 29421
- Oracle text classified (automated, or sorted into a concrete missing capability): 97.7% · unclassified clauses: 2630
- Distinct missing-capability clusters: 8196

## Missing capabilities by category

| Category | Cards affected | Clauses |
|---|---|---|
| MISSING EFFECT | 10976 | 12873 |
| MISSING SELECTOR | 3275 | 3469 |
| MISSING TRIGGER EVENT | 2403 | 2515 |
| MISSING CONTINUOUS EFFECT | 2167 | 2290 |
| UNSUPPORTED ORACLE PATTERN | 1978 | 2630 |
| MISSING MECHANIC | 1816 | 1878 |
| MISSING REPLACEMENT PATTERN | 1360 | 1399 |
| MISSING COST / PERMISSION RULE | 800 | 810 |
| MISSING RESTRICTION | 659 | 693 |
| MISSING COST | 485 | 498 |
| MANA ABILITY WORDING | 364 | 366 |

## Highest-payoff clusters

Ranked by pod cards, pod commanders, possible commanders affected, cards it alone would unlock, then all Commander cards needing it.

| # | Category | Cluster | Commanders | Only missing piece for | Commander cards | Examples |
|---|---|---|---|---|---|---|
| 1 | MISSING EFFECT | draw n … | 66 | 220 | 549 | Errand-Rider of Gondor, Krovikan Sorcerer, Grip of Amnesia |
| 2 | MISSING EFFECT | choose n … | 65 | 50 | 540 | Road of Return, Saheeli's Artistry, Dawnbringer Cleric |
| 3 | MISSING EFFECT | put a ±n/±n counter(s) … | 61 | 161 | 230 | Greta, Sweettooth Scourge, Yorvo, Lord of Garenbrig, Ent-Draught Basin |
| 4 | MISSING EFFECT | pay {m} … | 54 | 112 | 168 | Labyrinth Adversary, Minion Reflector, Giant's Amulet |
| 5 | MISSING MECHANIC | ward | 47 | 16 | 97 | Tyranid Harridan, Grey Host Reinforcements, Kwia Vigorbloom |
| 6 | MISSING SELECTOR | target | 36 | 197 | 319 | Cinder Elemental, Archangel of Wrath, Chain of Plasma |
| 7 | MISSING EFFECT | look at the top … | 33 | 139 | 185 | Harald, King of Skemfar, Lantern of Revealing, Puresight Merrow |
| 8 | MISSING CONTINUOUS EFFECT | ~ gets ±N/±N for each … | 32 | 59 | 115 | Nim Lasher, Benalish Honor Guard, Anya, Merciless Angel |
| 9 | MISSING EFFECT | put n … | 28 | 100 | 149 | Black Sun's Zenith, Breaking // Entering, Mind Raker |
| 10 | MISSING CONTINUOUS EFFECT | ~'s power and toughness are each … | 28 | 68 | 127 | Eluge, the Shoreless Sea, Flora Colossus, Revenant |
| 11 | MISSING EFFECT | create n … | 27 | 119 | 201 | Summon the School, Cogwork Assembler, Endless Evil |
| 12 | MISSING SELECTOR | target creature card | 25 | 111 | 165 | Hua Tuo, Honored Physician, Puppeteer Clique, Metamorphosis Fanatic |
| 13 | MISSING EFFECT | exile the top card … | 25 | 31 | 59 | Mezzio Mugger, Etali, Primal Storm, Chandra, Torch of Defiance |
| 14 | MISSING EFFECT | if n … | 24 | 61 | 92 | Airdrop Aeronauts, Hot Pursuit, Kotis, Sibsig Champion |
| 15 | MISSING EFFECT | until end of turn … | 23 | 162 | 227 | Divergent Growth, Doorman, Strength of Will |
| 16 | MISSING EFFECT | transform ~ … | 23 | 28 | 70 | Ulvenwald Captive // Ulvenwald Abomination, Westvale Abbey // Ormendahl, Profane Prince, Seraph of New Capenna // Seraph of New Phyrexia |
| 17 | UNSUPPORTED ORACLE PATTERN | As long as your devotion to … | 22 | 7 | 22 | Phenax, God of Deception, Erebos, God of the Dead, Thassa, Deep-Dwelling |
| 18 | MISSING EFFECT | if ~ … | 19 | 77 | 130 | Warden of the First Tree, Hixus, Prison Warden, Blinkmoth Urn |
| 19 | MISSING EFFECT | mill n … | 18 | 67 | 101 | Sparring Dummy, Loafing Giant, Beluna Grandsquall // Seek Thrills |
| 20 | MISSING TRIGGER EVENT | When you cast ~ | 18 | 30 | 80 | Empyrial Storm, The Fourteenth Doctor, Ulamog, the Ceaseless Hunger |
| 21 | MISSING EFFECT | exile ~ … | 17 | 9 | 55 | Woodland Guidance, Teferi's Protection, Vorinclex // The Grand Evolution |
| 22 | MISSING EFFECT | search your library for … | 16 | 172 | 260 | Safewright Quest, Thunderherd Migration, Squadron Hawk |
| 23 | MISSING CONTINUOUS EFFECT | Commander creatures you own have “…” | 16 | 16 | 16 | Dungeon Delver, Noble Heritage, Acolyte of Bahamut |
| 24 | MISSING CONTINUOUS EFFECT | ~'s power is equal to the … | 15 | 31 | 67 | Uurg, Spawn of Turg, Snow Villiers, Nethergoyf |
| 25 | UNSUPPORTED ORACLE PATTERN | As ~ enters, … | 15 | 1 | 19 | Stenn, Paranoid Partisan, Arachne, Psionic Weaver, Pramikon, Sky Rampart |
| 26 | UNSUPPORTED ORACLE PATTERN | More Than Meets the Eye {M} | 15 | 0 | 15 | Optimus Prime, Hero // Optimus Prime, Autobot Leader, Megatron, Tyrant // Megatron, Destructive Force, Jetfire, Ingenious Scientist // Jetfire, Air Guardian |
| 27 | MISSING EFFECT | ~ deals n … | 14 | 208 | 315 | Deem Worthy, End-Blaze Epiphany, Harvest Pyre |
| 28 | MISSING EFFECT | return ~ … | 14 | 90 | 130 | Summon the School, Dragon Fangs, Haunted Dead |
| 29 | UNSUPPORTED ORACLE PATTERN | ~ costs {M} less to cast … | 14 | 28 | 47 | Bedlam Reveler, Gargantuan Leech, Cryptic Serpent |
| 30 | MISSING MECHANIC | sneak | 14 | 12 | 27 | Turncoat Kunoichi, Michelangelo, Improviser, Donatello's Technique |
| 31 | MISSING MECHANIC | firebending | 14 | 8 | 22 | Fire Sages, Loyal Fire Sage, Jeong Jeong, the Deserter |
| 32 | MISSING MECHANIC | partner | 14 | 6 | 24 | Lore Weaver, Blaring Captain, Rory Williams |
| 33 | UNSUPPORTED ORACLE PATTERN | • Put a ±N/±N counter(s) on … | 14 | 0 | 38 | Bejeweled Warg, Trusty Retriever, Inspired Inventor |
| 34 | MISSING EFFECT | add {m} … | 13 | 42 | 70 | Waste Not, Akki Rockspeaker, Brightstone Ritual |
| 35 | UNSUPPORTED ORACLE PATTERN | Living metal | 13 | 0 | 13 | Optimus Prime, Hero // Optimus Prime, Autobot Leader, Megatron, Tyrant // Megatron, Destructive Force, Jetfire, Ingenious Scientist // Jetfire, Air Guardian |
| 36 | MISSING SELECTOR | target equipment | 12 | 19 | 26 | Stolen Uniform, Shagrat, Loot Bearer, Thor, God of Thunder |
| 37 | UNSUPPORTED ORACLE PATTERN | Power-up — {M}: Put N ±N/±N … | 12 | 12 | 19 | Thanos, the Mad Titan, Shang-Chi, Martial Mentor, Hulk, Gamma Goliath |
| 38 | MISSING EFFECT | create a n/n white … | 11 | 33 | 54 | Empyrial Storm, Drag the Canal, Experimental Synthesizer |
| 39 | MISSING EFFECT | create a n/n red … | 11 | 25 | 45 | Prosperity Tycoon, Ertha Jo, Frontier Mentor, Nesting Dragon |
| 40 | MISSING TRIGGER EVENT | Whenever you cast a historic spell | 11 | 15 | 19 | Serra Disciple, Cabal Paladin, Glóin, Dwarf Emissary |
| 41 | MISSING EFFECT | earthbend n … | 11 | 14 | 27 | Earth Village Ruffians, Bumi, Unleashed, Badgermole |
| 42 | MISSING EFFECT | if you've cast a … | 11 | 5 | 12 | H.E.R.B.I.E., Lovable Robot, Invisible Woman, Alicia Masters, Skilled Sculptor |
| 43 | MISSING EFFECT | gain control of target … | 10 | 58 | 85 | Sauron, the Lidless Eye, New Blood, Unwilling Recruit |
| 44 | MISSING EFFECT | reveal the top card … | 10 | 36 | 48 | Rashmi, Eternities Crafter, Counterbalance, Sorin, Grim Nemesis |
| 45 | MISSING SELECTOR | target creature card with mana value | 10 | 26 | 38 | General Leo Cristophe, Yathan Roadwatcher, Lazotep Quarry |
| 46 | MISSING SELECTOR | target instant or sorcery card | 10 | 18 | 30 | Ogre Battlecaster, Flood of Recollection, Impulsivity |
| 47 | MISSING EFFECT | another target … | 10 | 13 | 21 | Hemosymbic Mite, Syr Faren, the Hengehammer, Pippin, Guard of the Citadel |
| 48 | MISSING COST / PERMISSION RULE | You may cast ~ from your … | 10 | 12 | 25 | Marang River Prowler, Quilled Greatwurm, Gravecrawler |
| 49 | MISSING EFFECT | return it to the … | 10 | 11 | 23 | Bronzehide Lion, Optimus Prime, Hero // Optimus Prime, Autobot Leader, Yedora, Grave Gardener |
| 50 | MISSING COST / PERMISSION RULE | Once during each of your turns, … | 10 | 8 | 14 | Kotis, Sibsig Champion, One with the Multiverse, Jacob Hauken, Inspector // Hauken's Insight |
| 51 | MISSING EFFECT | target creature you control … | 9 | 117 | 170 | Hard-Hitting Question, Crowd of True Believers, Rabid Gnaw |
| 52 | MISSING SELECTOR | target creatures | 9 | 104 | 203 | Ravenous Gigantotherium, Fire Covenant, Amazing Acrobatics |
| 53 | MISSING EFFECT | choose target … | 9 | 71 | 83 | Arcbond, Deglamer, Wreck Hunter |
| 54 | MISSING EFFECT | you gain n … | 9 | 65 | 89 | Belladonna Took, Shu Farmer, Essence Pulse |
| 55 | MISSING EFFECT | exile the top n … | 9 | 17 | 41 | Memorial Vault, Crossover Collaboration, Ral, Monsoon Mage // Ral, Leyline Prodigy |
| 56 | MISSING EFFECT | double the number of … | 9 | 12 | 24 | Fractal Harness, Primordial Hydra, The Millennium Calendar |
| 57 | MISSING CONTINUOUS EFFECT | You have no maximum hand size | 9 | 9 | 23 | Nyssa of Traken, Curiosity Crafter, Wizard Class |
| 58 | UNSUPPORTED ORACLE PATTERN | Web-slinging {M} | 9 | 4 | 9 | Scarlet Spider, Ben Reilly, Arachne, Psionic Weaver, Spider-Man, Brooklyn Visionary |
| 59 | MISSING TRIGGER EVENT | When ~ enters | 9 | 2 | 9 | Niv-Mizzet Reborn, Lobelia Sackville-Baggins, Drizzt Do'Urden |
| 60 | MISSING MECHANIC | companion | 9 | 1 | 9 | Lutri, the Spellchaser, Gyruda, Doom of Depths, Lurrus of the Dream-Den |
| 61 | UNSUPPORTED ORACLE PATTERN | • ~ deals N damage to … | 9 | 0 | 18 | Arbalest Engineers, Tectonic Giant, Umaro, Raging Yeti |
| 62 | UNSUPPORTED ORACLE PATTERN | Storied | 9 | 0 | 9 | Balin, Loremaster, Dáin, Lord of the Iron Hills, Ori, Keeper of Songs |
| 63 | MISSING COST | {M}, Discard ~ | 8 | 37 | 57 | Jiwari, the Earth Aflame, Favor of Jukai, Radiant Solar |
| 64 | MISSING REPLACEMENT PATTERN | ~ enters with a ±N/±N counter(s) on … | 8 | 18 | 37 | Callous Sell-Sword // Burn Together, Avatar of the Resolute, The Duke, Rebel Sentry |
| 65 | MISSING EFFECT | you draw n … | 8 | 17 | 31 | Fang, Fearless l'Cie, Live Fast, Greed's Gambit |
| 66 | MISSING EFFECT | discard your hand … | 8 | 15 | 31 | Pyretic Charge, Bedlam Reveler, Balin, Loremaster |
| 67 | MISSING EFFECT | discard n … | 8 | 14 | 26 | Witch's Mark, Seasoned Pyromancer, Party Thrasher |
| 68 | MISSING EFFECT | exile up to n … | 8 | 13 | 20 | Salvation Swan, Flickering Hound, Earth Kingdom Jailer |
| 69 | UNSUPPORTED ORACLE PATTERN | Mayhem {M} | 8 | 7 | 11 | Swarm, Being of Bees, Chameleon, Master of Disguise, Spider-Islanders |
| 70 | MISSING CONTINUOUS EFFECT | During your turn, … | 8 | 6 | 17 | Long-Lost Lances, Miriam, Herd Whisperer, Yuna, Hope of Spira |
| 71 | UNSUPPORTED ORACLE PATTERN | You may play an additional land … | 8 | 6 | 17 | Exploration, Icetill Explorer, Case of the Locked Hothouse |
| 72 | MISSING EFFECT | you get an experience … | 8 | 0 | 8 | Meren of Clan Nel Toth, Katara, Waterbending Master, Ezuri, Claw of Progress |
| 73 | MISSING EFFECT | if you control n … | 7 | 39 | 63 | Dawnhart Wardens, Boundary Lands Ranger, Dispatch |
| 74 | MISSING SELECTOR | target artifact or creature | 7 | 30 | 49 | Tamiyo, Compleated Sage, Starke of Rath, Mind Transfer Protocol |
| 75 | MISSING EFFECT | each opponent loses n … | 7 | 28 | 40 | Subversion, Faerie Bladecrafter, Scholar of Athreos |
| 76 | MISSING EFFECT | if you cast it … | 7 | 24 | 38 | Weftwalking, Marina Vendrell's Grimoire, Bringer of the Last Gift |
| 77 | MANA ABILITY WORDING | {M}: Add {M}. Spend this mana … | 7 | 23 | 27 | Guidelight Optimizer, Karfell Harbinger, Soldevi Machinist |
| 78 | MISSING EFFECT | create a n/n black … | 7 | 20 | 34 | Grist, the Hunger Tide, Ghoulcaller's Accomplice, Grist, Voracious Larva // Grist, the Plague Swarm |
| 79 | MISSING TRIGGER EVENT | Magecraft — Whenever you cast or copy an instant or sorcery spell | 7 | 20 | 29 | Zaffai, Thunder Conductor, Karok Wrangler, Extus, Oriq Overlord // Awaken the Blood Avatar |
| 80 | MISSING EFFECT | for each opponent … | 7 | 19 | 37 | Bronzebeak Foragers, Nihiloor, Frenzied Gorespawn |

## Largest clusters (Commander cards affected)

| # | Category | Cluster | Commander cards | Only missing piece for | Commanders | Examples |
|---|---|---|---|---|---|---|
| 1 | MISSING EFFECT | draw n … | 549 | 220 | 66 | Errand-Rider of Gondor, Krovikan Sorcerer, Grip of Amnesia |
| 2 | MISSING EFFECT | choose n … | 540 | 50 | 65 | Road of Return, Saheeli's Artistry, Dawnbringer Cleric |
| 3 | MISSING SELECTOR | target | 319 | 197 | 36 | Cinder Elemental, Archangel of Wrath, Chain of Plasma |
| 4 | MISSING EFFECT | ~ deals n … | 315 | 208 | 14 | Deem Worthy, End-Blaze Epiphany, Harvest Pyre |
| 5 | MISSING COST / PERMISSION RULE | As an additional cost to cast … | 312 | 37 | 6 | Thunderherd Migration, Mind Extraction, Harvest Pyre |
| 6 | MISSING EFFECT | search your library for … | 260 | 172 | 16 | Safewright Quest, Thunderherd Migration, Squadron Hawk |
| 7 | MISSING REPLACEMENT PATTERN | As ~ enters, … | 237 | 47 | 4 | Kindred Discovery, Utopia Sprawl, Game Trail |
| 8 | MISSING EFFECT | put a ±n/±n counter(s) … | 230 | 161 | 61 | Greta, Sweettooth Scourge, Yorvo, Lord of Garenbrig, Ent-Draught Basin |
| 9 | MISSING EFFECT | until end of turn … | 227 | 162 | 23 | Divergent Growth, Doorman, Strength of Will |
| 10 | MISSING SELECTOR | target creatures | 203 | 104 | 9 | Ravenous Gigantotherium, Fire Covenant, Amazing Acrobatics |
| 11 | MISSING EFFECT | create n … | 201 | 119 | 27 | Summon the School, Cogwork Assembler, Endless Evil |
| 12 | MISSING EFFECT | look at the top … | 185 | 139 | 33 | Harald, King of Skemfar, Lantern of Revealing, Puresight Merrow |
| 13 | MISSING EFFECT | destroy target … | 185 | 111 | 4 | Kalitas, Bloodchief of Ghet, Raze, Unliving Psychopath |
| 14 | MISSING EFFECT | target creature you control … | 170 | 117 | 9 | Hard-Hitting Question, Crowd of True Believers, Rabid Gnaw |
| 15 | MISSING EFFECT | pay {m} … | 168 | 112 | 54 | Labyrinth Adversary, Minion Reflector, Giant's Amulet |
| 16 | MISSING SELECTOR | target creature card | 165 | 111 | 25 | Hua Tuo, Honored Physician, Puppeteer Clique, Metamorphosis Fanatic |
| 17 | MISSING EFFECT | target creature gets ±n/±n … | 159 | 100 | 4 | Stern Marshal, Spontaneous Flight, Rig for War |
| 18 | MISSING EFFECT | put n … | 149 | 100 | 28 | Black Sun's Zenith, Breaking // Entering, Mind Raker |
| 19 | MISSING EFFECT | if ~ … | 130 | 77 | 19 | Warden of the First Tree, Hixus, Prison Warden, Blinkmoth Urn |
| 20 | MISSING EFFECT | return ~ … | 130 | 90 | 14 | Summon the School, Dragon Fangs, Haunted Dead |
| 21 | MISSING CONTINUOUS EFFECT | ~'s power and toughness are each … | 127 | 68 | 28 | Eluge, the Shoreless Sea, Flora Colossus, Revenant |
| 22 | MISSING CONTINUOUS EFFECT | ~ gets ±N/±N for each … | 115 | 59 | 32 | Nim Lasher, Benalish Honor Guard, Anya, Merciless Angel |
| 23 | MISSING SELECTOR | target player or planeswalker | 111 | 79 | 5 | Goblin Barrage, Scorching Missile, Consuming Sinkhole |
| 24 | MANA ABILITY WORDING | {M}, … | 108 | 78 | 6 | Saltcrusted Steppe, Cabal Stronghold, Interplanar Beacon |
| 25 | MISSING EFFECT | mill n … | 101 | 67 | 18 | Sparring Dummy, Loafing Giant, Beluna Grandsquall // Seek Thrills |
| 26 | MISSING MECHANIC | ward | 97 | 16 | 47 | Tyranid Harridan, Grey Host Reinforcements, Kwia Vigorbloom |
| 27 | MISSING EFFECT | if n … | 92 | 61 | 24 | Airdrop Aeronauts, Hot Pursuit, Kotis, Sibsig Champion |
| 28 | MISSING EFFECT | exile target … | 92 | 61 | 5 | Astarion's Thirst, Deadly Rollick, Tawnos's Coffin |
| 29 | MISSING EFFECT | you gain n … | 89 | 65 | 9 | Belladonna Took, Shu Farmer, Essence Pulse |
| 30 | MISSING EFFECT | gain control of target … | 85 | 58 | 10 | Sauron, the Lidless Eye, New Blood, Unwilling Recruit |
| 31 | MISSING EFFECT | choose target … | 83 | 71 | 9 | Arcbond, Deglamer, Wreck Hunter |
| 32 | MISSING TRIGGER EVENT | When you cast ~ | 80 | 30 | 18 | Empyrial Storm, The Fourteenth Doctor, Ulamog, the Ceaseless Hunger |
| 33 | MISSING EFFECT | tap target … | 77 | 45 | 4 | Spider-Woman, Secret Agent, Guardian of Tazeem, Gilded Scuttler |
| 34 | MISSING EFFECT | if there are n … | 76 | 32 | 6 | Locked in the Cemetery, Sanguine Spy, Extricator of Sin // Extricator of Flesh |
| 35 | MISSING EFFECT | it deals n … | 75 | 60 | 3 | Goblin Chainwhirler, Festering Evil, Unsparing Boltcaster |
| 36 | MISSING EFFECT | cast ~ … | 72 | 0 | 1 | Twice Upon a Time // Unlikely Meeting, Defiant Stand, Asinine Antics |
| 37 | MISSING EFFECT | transform ~ … | 70 | 28 | 23 | Ulvenwald Captive // Ulvenwald Abomination, Westvale Abbey // Ormendahl, Profane Prince, Seraph of New Capenna // Seraph of New Phyrexia |
| 38 | MISSING EFFECT | add {m} … | 70 | 42 | 13 | Waste Not, Akki Rockspeaker, Brightstone Ritual |
| 39 | MISSING EFFECT | return target … | 69 | 42 | 1 | Surging Aether, Perilous Voyage, Geistwave |
| 40 | MISSING CONTINUOUS EFFECT | ~'s power is equal to the … | 67 | 31 | 15 | Uurg, Spawn of Turg, Snow Villiers, Nethergoyf |
| 41 | MISSING EFFECT | create a n/n green … | 65 | 33 | 6 | Rhonas's Last Stand, Fractal Harness, Baloth Cage Trap |
| 42 | MANA ABILITY WORDING | {M}: Add N mana of any … | 65 | 37 | 2 | Flywheel Racer, Pit of Offerings, Helga, Skittish Seer |
| 43 | MISSING EFFECT | if you control n … | 63 | 39 | 7 | Dawnhart Wardens, Boundary Lands Ranger, Dispatch |
| 44 | MISSING EFFECT | you get an emblem … | 60 | 16 | 4 | Zariel, Archduke of Avernus, Elspeth, Sun's Champion, Teferi, Temporal Archmage |
| 45 | MISSING EFFECT | exile the top card … | 59 | 31 | 25 | Mezzio Mugger, Etali, Primal Storm, Chandra, Torch of Defiance |
| 46 | MISSING REPLACEMENT PATTERN | Prevent all damage that would be dealt … | 59 | 38 | 6 | Comeuppance, Gideon's Intervention, Ethereal Haze |
| 47 | MISSING COST | {M}, Discard ~ | 57 | 37 | 8 | Jiwari, the Earth Aflame, Favor of Jukai, Radiant Solar |
| 48 | MISSING REPLACEMENT PATTERN | Prevent all combat damage that would be … | 57 | 41 | 2 | Candletrap, Armored Transport, Sandskin |
| 49 | MISSING EFFECT | exile ~ … | 55 | 9 | 17 | Woodland Guidance, Teferi's Protection, Vorinclex // The Grand Evolution |
| 50 | MISSING EFFECT | create a n/n white … | 54 | 33 | 11 | Empyrial Storm, Drag the Canal, Experimental Synthesizer |

## Top Commander features to implement next

Ranked by pod cards, pod commanders, cards for which it is the only missing piece, then Commander cards needing it.

| # | Feature | Kind | Pod cards | Commander cards | Only missing piece for | Examples |
|---|---|---|---|---|---|---|
| 1 | mana:ability | engine | 0 | 364 | 253 | Saltcrusted Steppe, Flywheel Racer, The Emperor of Palamecia // The Lord Master of Hell |
| 2 | keyword:bestow | keyword | 0 | 42 | 25 | Leafcrown Dryad, Baleful Eidolon, Observant Alseid |
| 3 | template:~ enters prepared. | static | 0 | 40 | 24 | Adventurous Eater // Have a Bite, Maelstrom Artisan // Rocket Volley, Fatehold Chronologist // Peer Review |
| 4 | keyword:foretell | keyword | 0 | 51 | 21 | The Foretold Soldier, Rise of the Dread Marn, Green Slime |
| 5 | template:Enchanted creature has “…” | continuous | 0 | 25 | 21 | Ghostly Touch, Mark of Sakiko, Unquenchable Fury |
| 6 | keyword:enchant | keyword | 0 | 67 | 20 | Utopia Sprawl, One with the Stars, Corrupted Roots |
| 7 | template:When ~ enters, attach it to target creature you control. | triggered | 0 | 30 | 19 | Maul of the Skyclaves, Meltstrider's Gear, Bramble Armor |
| 8 | keyword:banding | keyword | 0 | 24 | 19 | Nalathni Dragon, Mishra's War Machine, Kjeldoran Escort |
| 9 | template:Commander creatures you own have “…” | continuous | 0 | 19 | 19 | Dungeon Delver, Scion of Halaster, Noble Heritage |
| 10 | keyword:equip | keyword | 0 | 49 | 18 | Bloodthorn Flail, Strong Back, Team Pennant |
| 11 | keyword:backup | keyword | 0 | 25 | 18 | Saiba Cryptomancer, Chomping Kavu, Consuming Aetherborn |
| 12 | keyword:warp | keyword | 0 | 31 | 17 | Starbreach Whale, Knight Luminary, Loading Zone |
| 13 | template:Equipped creature has “…” | continuous | 0 | 24 | 17 | Field-Tested Frying Pan, Sorcerer's Wand, Fishing Pole |
| 14 | keyword:ward | keyword | 0 | 97 | 16 | Tyranid Harridan, Grey Host Reinforcements, Kwia Vigorbloom |
| 15 | keyword:splice | keyword | 0 | 30 | 16 | Evermind, Horobi's Whisper, Desperate Ritual |
| 16 | template:Modular N | static | 0 | 23 | 16 | Arcbound Whelp, Arcbound Javelineer, Arcbound Hybrid |
| 17 | template:−N: You get an emblem with “…” | loyalty | 0 | 64 | 15 | Zariel, Archduke of Avernus, Elspeth, Sun's Champion, Teferi, Temporal Archmage |
| 18 | keyword:encore | keyword | 0 | 26 | 15 | Impulsivity, Sliver Gravemother, Belonging |
| 19 | keyword:myriad | keyword | 0 | 23 | 14 | The Master, Multiplied, Sumala Rumblers, Conclave Evangelist |
| 20 | template:{M}: Return ~ from your graveyard to your hand. | activated | 0 | 22 | 14 | The Sound of Drums, Merchant of Many Hats, Convenient Target |
| 21 | keyword:entwine | keyword | 0 | 32 | 13 | Road of Return, Rain of Rust, Blinding Beam |
| 22 | keyword:ninjutsu | keyword | 0 | 35 | 12 | Higure, the Still Wind, Moonblade Shinobi, Mist-Syndicate Naga |
| 23 | keyword:overload | keyword | 0 | 27 | 12 | Mizzium Skin, Corporeal Projection, Mind Rake |
| 24 | keyword:sneak | keyword | 0 | 27 | 12 | Turncoat Kunoichi, Michelangelo, Improviser, Donatello's Technique |
| 25 | keyword:offspring | keyword | 0 | 20 | 12 | Splash Lasher, Rust-Shield Rampager, Prosperous Bandit |
| 26 | keyword:unleash | keyword | 0 | 15 | 12 | Rakdos Drake, Grim Roustabout, Chaos Imps |
| 27 | keyword:disguise | keyword | 0 | 43 | 11 | Boltbender, Nightdrinker Moroii, Concealed Weapon |
| 28 | template:{M}: Adapt N. | activated | 0 | 22 | 11 | Zegana, Utopian Speaker, Temperamental Oozewagg, Evolution Witness |
| 29 | keyword:living weapon | keyword | 0 | 19 | 11 | Nettlecyst, Lashwrithe, Skinwing |
| 30 | keyword:mentor | keyword | 0 | 19 | 11 | Hammer Dropper, Legion Warboss, Tributary Instructor |
| 31 | keyword:retrace | keyword | 0 | 17 | 11 | Flame Jab, Monstrify, Waves of Aggression |
| 32 | keyword:umbra armor | keyword | 0 | 15 | 11 | Felidar Umbra, Drake Umbra, Hyena Umbra |
| 33 | keyword:rampage | keyword | 0 | 12 | 11 | Craw Giant, Balduvian War-Makers, Varchild's War-Riders |
| 34 | template:Enchanted land has “…” | continuous | 0 | 12 | 11 | Chamber of Manipulation, Discreet Retreat, Farmstead |
| 35 | template:All Slivers have “…” | continuous | 0 | 11 | 11 | Magma Sliver, Basal Sliver, Mesmeric Sliver |
| 36 | keyword:evolve | keyword | 0 | 22 | 10 | Adaptive Snapjaw, Shambleshark, Tyranid Prime |
| 37 | keyword:prototype | keyword | 0 | 19 | 10 | Goring Warplow, Combat Thresher, Woodcaller Automaton |
| 38 | keyword:embalm | keyword | 0 | 15 | 10 | Heart-Piercer Manticore, Angel of Sanctions, Anointer Priest |
| 39 | template:Scavenge {M} | static | 0 | 14 | 10 | Terrus Wurm, Deadbridge Goliath, Dodgy Jalopy |
| 40 | keyword:battle cry | keyword | 0 | 13 | 10 | Goblin Wardriver, Hero of Bladehold, Iraxxa, Empress of Mars |
| 41 | template:{M}, Sacrifice ~: It deals N damage to any target. | activated | 0 | 12 | 10 | Fireforger's Puzzleknot, Lightning Spear, Pyrite Spellbomb |
| 42 | template:~ enters tapped unless you control N or fewer other lands. | replacement | 0 | 11 | 10 | Concealed Courtyard, Inspiring Vantage, Blackcleave Cliffs |
| 43 | template:~ enters tapped unless a player has N or less life. | replacement | 0 | 10 | 10 | Abandoned Campground, Raucous Carnival, Strangled Cemetery |
| 44 | template:~ enters tapped unless you control N or more basic lands. | replacement | 0 | 10 | 10 | Sodden Verdure, Smoldering Marsh, Vernal Fen |
| 45 | template:~ enters tapped unless you control N or more other lands. | replacement | 0 | 10 | 10 | Rockfall Vale, Stormcarved Coast, Sundown Pass |
| 46 | template:~ enters tapped unless you control a planeswalker. | replacement | 0 | 10 | 10 | Theorix Annex, Stingerquill Annex, Konstrari Annex |
| 47 | template:~ enters tapped unless you have N or more opponents. | replacement | 0 | 10 | 10 | Spire Garden, Sea of Clouds, Bountiful Promenade |
| 48 | keyword:plot | keyword | 0 | 33 | 9 | Unscrupulous Contractor, Pyretic Charge, Freestrider Commando |
| 49 | template:You control enchanted creature. | static | 0 | 28 | 9 | Spirit Away, Illusory Gains, Biting Tether |
| 50 | keyword:cumulative upkeep | keyword | 0 | 23 | 9 | Varchild's War-Riders, Aboroth, Inner Sanctum |
| 51 | template:You have no maximum hand size. | continuous | 0 | 23 | 9 | Nyssa of Traken, Curiosity Crafter, Wizard Class |
| 52 | keyword:vanishing | keyword | 0 | 20 | 9 | Soultether Golem, Deadly Grub, Reality Acid |
| 53 | keyword:replicate | keyword | 0 | 19 | 9 | Consign to Memory, Psionic Ritual, Lose Focus |
| 54 | keyword:extort | keyword | 0 | 17 | 9 | Syndicate Heavy, Tithe Drinker, Kingpin's Pet |
| 55 | keyword:fading | keyword | 0 | 17 | 9 | Parallax Wave, Phyrexian Prowler, Skyshroud Ridgeback |
| 56 | keyword:blitz | keyword | 0 | 16 | 9 | Mezzio Mugger, Workshop Warchief, Riveteers Decoy |
| 57 | template:Prevent all combat damage that would be dealt this turn. | prevention | 0 | 14 | 9 | Jaheira's Respite, Fog, Darkness |
| 58 | keyword:enlist | keyword | 0 | 12 | 9 | Keldon Flamesage, Benalish Faithbonder, Aradesh, the Founder |
| 59 | template:{M}, {M}, Sacrifice ~: It deals N damage to target creature. | activated | 0 | 11 | 9 | Vial of Dragonfire, Flamecast Wheel, Mouth of Ronom |
| 60 | keyword:kicker | keyword | 0 | 37 | 8 | Goblin Barrage, Archangel of Wrath, Anavolver |

## Coverage by card type

| Type | FULL | PARTIAL | REVIEW | MANUAL |
|---|---|---|---|---|
| Creature | 6946 | 10975 | 0 | 0 |
| Artifact | 1119 | 2474 | 0 | 0 |
| Enchantment | 951 | 2696 | 0 | 0 |
| Sorcery | 994 | 2574 | 0 | 0 |
| Instant | 1249 | 2505 | 0 | 0 |
| Land | 541 | 671 | 0 | 0 |
| Planeswalker | 18 | 293 | 0 | 0 |
| Battle | 0 | 36 | 0 | 0 |

## Rules features in the pool (ability lines)

triggered 14909, keyword 14139, spell_effect 9115, activated 7339, continuous 3999, static 2899, mana_ability 2035, replacement 1966, restriction 1474, loyalty 882, prevention 320, additional_cost 307, cost_modifier 261, characteristic_defining 247, permission 206, alternative_cost 180

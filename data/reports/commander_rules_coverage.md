# Commander rules coverage

Card data: Scryfall `2026-09-28T21:01:54.353+00:00` · Comprehensive Rules 2026-09-25 · rules engine v2 · generated 2026-09-29 22:54

Only cards that are **legal in Commander today** count. Banned cards (83) are COMMANDER_BANNED and excluded.

## Commander coverage

Commander-legal cards: **32116**

| Level | Cards | Share |
|---|---|---|
| FULL | 9876 | 30.8% |
| PARTIAL | 22192 | 69.1% |
| REVIEW | 0 | 0.0% |
| MANUAL | 48 | 0.1% |

Possible commanders (CR 903.3/903.3a, incl. Backgrounds): **3501** — FULL 426, PARTIAL 3075, REVIEW 0, MANUAL 0

## Pod coverage

No pod decks in the inventory yet (`python -m tools.rules_inventory`); the queue below is ranked by Commander-legal cards unlocked.

## Coverage quality

- Ability features (lines, keywords, play/cast/combat) across Commander-legal cards: 113346
- Automated: 81732 (72.1%) · unrecognized clauses: 31614
- Oracle text classified (automated, or sorted into a concrete missing capability): 97.5% · unclassified clauses: 2841
- Distinct missing-capability clusters: 8542

## Missing capabilities by category

| Category | Cards affected | Clauses |
|---|---|---|
| MISSING EFFECT | 11242 | 13220 |
| MISSING SELECTOR | 3474 | 3674 |
| MISSING TRIGGER EVENT | 3437 | 3607 |
| MISSING CONTINUOUS EFFECT | 2189 | 2313 |
| UNSUPPORTED ORACLE PATTERN | 2079 | 2841 |
| MISSING MECHANIC | 1816 | 1878 |
| MISSING REPLACEMENT PATTERN | 1362 | 1401 |
| MISSING RESTRICTION | 937 | 983 |
| MISSING COST / PERMISSION RULE | 801 | 811 |
| MISSING COST | 504 | 517 |
| MANA ABILITY WORDING | 367 | 369 |

## Highest-payoff clusters

Ranked by pod cards, pod commanders, possible commanders affected, cards it alone would unlock, then all Commander cards needing it.

| # | Category | Cluster | Commanders | Only missing piece for | Commander cards | Examples |
|---|---|---|---|---|---|---|
| 1 | MISSING EFFECT | choose n … | 65 | 49 | 552 | Road of Return, Saheeli's Artistry, Dawnbringer Cleric |
| 2 | MISSING EFFECT | draw n … | 62 | 211 | 577 | Errand-Rider of Gondor, Krovikan Sorcerer, Heal |
| 3 | MISSING EFFECT | put a ±n/±n counter(s) … | 55 | 140 | 203 | Greta, Sweettooth Scourge, Yorvo, Lord of Garenbrig, Ent-Draught Basin |
| 4 | MISSING EFFECT | pay {m} … | 53 | 109 | 166 | Labyrinth Adversary, Minion Reflector, Giant's Amulet |
| 5 | MISSING MECHANIC | ward | 47 | 11 | 97 | Tyranid Harridan, Grey Host Reinforcements, Kwia Vigorbloom |
| 6 | MISSING EFFECT | look at the top … | 38 | 153 | 211 | Harald, King of Skemfar, Lantern of Revealing, Puresight Merrow |
| 7 | MISSING EFFECT | create n … | 37 | 152 | 253 | Summon the School, Cogwork Assembler, Endless Evil |
| 8 | MISSING SELECTOR | target | 34 | 194 | 324 | Cinder Elemental, Archangel of Wrath, Chain of Plasma |
| 9 | MISSING CONTINUOUS EFFECT | ~ gets ±N/±N for each … | 32 | 58 | 115 | Nim Lasher, Benalish Honor Guard, Anya, Merciless Angel |
| 10 | MISSING EFFECT | put n … | 28 | 93 | 148 | Black Sun's Zenith, Breaking // Entering, Mind Raker |
| 11 | MISSING CONTINUOUS EFFECT | ~'s power and toughness are each … | 28 | 66 | 127 | Eluge, the Shoreless Sea, Flora Colossus, Revenant |
| 12 | MISSING SELECTOR | target creature card | 25 | 116 | 174 | Hua Tuo, Honored Physician, Puppeteer Clique, Metamorphosis Fanatic |
| 13 | MISSING EFFECT | if n … | 24 | 60 | 92 | Airdrop Aeronauts, Hot Pursuit, Kotis, Sibsig Champion |
| 14 | MISSING EFFECT | exile the top card … | 24 | 26 | 62 | Moonring Mirror, Mezzio Mugger, Etali, Primal Storm |
| 15 | MISSING EFFECT | until end of turn … | 23 | 157 | 227 | Divergent Growth, Doorman, Strength of Will |
| 16 | MISSING EFFECT | transform ~ … | 23 | 22 | 66 | Ulvenwald Captive // Ulvenwald Abomination, Westvale Abbey // Ormendahl, Profane Prince, Seraph of New Capenna // Seraph of New Phyrexia |
| 17 | UNSUPPORTED ORACLE PATTERN | As long as your devotion to … | 22 | 7 | 22 | Phenax, God of Deception, Erebos, God of the Dead, Thassa, Deep-Dwelling |
| 18 | MISSING EFFECT | exile ~ … | 20 | 13 | 61 | Stenn, Paranoid Partisan, Woodland Guidance, Teferi's Protection |
| 19 | MISSING EFFECT | mill n … | 18 | 62 | 100 | Sparring Dummy, Beluna Grandsquall // Seek Thrills, Cache Grab |
| 20 | MISSING TRIGGER EVENT | When you cast ~ | 18 | 28 | 80 | Empyrial Storm, The Fourteenth Doctor, Ulamog, the Ceaseless Hunger |
| 21 | MISSING EFFECT | search your library for … | 16 | 169 | 259 | Safewright Quest, Thunderherd Migration, Squadron Hawk |
| 22 | MISSING EFFECT | if ~ … | 16 | 71 | 126 | Warden of the First Tree, Blinkmoth Urn, Mad Dog |
| 23 | MISSING CONTINUOUS EFFECT | Commander creatures you own have “…” | 16 | 16 | 16 | Dungeon Delver, Noble Heritage, Acolyte of Bahamut |
| 24 | MISSING EFFECT | ~ deals n … | 15 | 196 | 302 | Deem Worthy, End-Blaze Epiphany, Harvest Pyre |
| 25 | MISSING EFFECT | create a n/n black … | 15 | 37 | 56 | Queen Brahne, Grist, the Hunger Tide, Mysidian Elder |
| 26 | MISSING EFFECT | create a n/n red … | 15 | 32 | 58 | Prosperity Tycoon, Ertha Jo, Frontier Mentor, Nesting Dragon |
| 27 | MISSING CONTINUOUS EFFECT | ~'s power is equal to the … | 15 | 30 | 67 | Uurg, Spawn of Turg, Snow Villiers, Nethergoyf |
| 28 | UNSUPPORTED ORACLE PATTERN | As ~ enters, … | 15 | 1 | 19 | Stenn, Paranoid Partisan, Arachne, Psionic Weaver, Pramikon, Sky Rampart |
| 29 | UNSUPPORTED ORACLE PATTERN | More Than Meets the Eye {M} | 15 | 0 | 15 | Optimus Prime, Hero // Optimus Prime, Autobot Leader, Megatron, Tyrant // Megatron, Destructive Force, Jetfire, Ingenious Scientist // Jetfire, Air Guardian |
| 30 | MISSING EFFECT | return ~ … | 14 | 86 | 128 | Summon the School, Dragon Fangs, Haunted Dead |
| 31 | MISSING EFFECT | create a n/n white … | 14 | 36 | 62 | Empyrial Storm, Drag the Canal, Ajani Resolute |
| 32 | UNSUPPORTED ORACLE PATTERN | ~ costs {M} less to cast … | 14 | 26 | 47 | Bedlam Reveler, Gargantuan Leech, Cryptic Serpent |
| 33 | MISSING TRIGGER EVENT | Whenever you cast your second spell each turn | 14 | 22 | 34 | Sunstar Lightsmith, Wanda's Vision, Kraum, Violent Cacophony |
| 34 | MISSING MECHANIC | sneak | 14 | 12 | 27 | Turncoat Kunoichi, Michelangelo, Improviser, Donatello's Technique |
| 35 | MISSING MECHANIC | firebending | 14 | 7 | 22 | Fire Sages, Loyal Fire Sage, Jeong Jeong, the Deserter |
| 36 | MISSING MECHANIC | partner | 14 | 5 | 24 | Lore Weaver, Blaring Captain, Rory Williams |
| 37 | UNSUPPORTED ORACLE PATTERN | • Put a ±N/±N counter(s) on … | 14 | 0 | 38 | Bejeweled Warg, Trusty Retriever, Inspired Inventor |
| 38 | UNSUPPORTED ORACLE PATTERN | Living metal | 13 | 0 | 13 | Optimus Prime, Hero // Optimus Prime, Autobot Leader, Megatron, Tyrant // Megatron, Destructive Force, Jetfire, Ingenious Scientist // Jetfire, Air Guardian |
| 39 | MISSING RESTRICTION | ~ can't be blocked by creatures … | 12 | 27 | 56 | Lydia Frye, Pompous Gadabout, Ghost of Ramirez DePietro |
| 40 | MISSING SELECTOR | target equipment | 12 | 17 | 25 | Stolen Uniform, Shagrat, Loot Bearer, Thor, God of Thunder |
| 41 | UNSUPPORTED ORACLE PATTERN | Power-up — {M}: Put N ±N/±N … | 12 | 12 | 19 | Thanos, the Mad Titan, Shang-Chi, Martial Mentor, Hulk, Gamma Goliath |
| 42 | MISSING EFFECT | add {m} … | 11 | 40 | 65 | Akki Rockspeaker, Brightstone Ritual, Infernal Plunge |
| 43 | MISSING TRIGGER EVENT | Whenever you cast a historic spell | 11 | 15 | 19 | Serra Disciple, Cabal Paladin, Glóin, Dwarf Emissary |
| 44 | MISSING EFFECT | earthbend n … | 11 | 14 | 27 | Earth Village Ruffians, Bumi, Unleashed, Badgermole |
| 45 | MISSING EFFECT | another target … | 11 | 14 | 23 | Hemosymbic Mite, Syr Faren, the Hengehammer, Pippin, Guard of the Citadel |
| 46 | MISSING EFFECT | if you've cast a … | 11 | 5 | 12 | H.E.R.B.I.E., Lovable Robot, Invisible Woman, Alicia Masters, Skilled Sculptor |
| 47 | MISSING EFFECT | target creature you control … | 10 | 124 | 178 | Blessed Defiance, Hard-Hitting Question, Crowd of True Believers |
| 48 | MISSING EFFECT | gain control of target … | 10 | 58 | 85 | Sauron, the Lidless Eye, New Blood, Unwilling Recruit |
| 49 | MISSING SELECTOR | target creature card with mana value | 10 | 25 | 39 | General Leo Cristophe, Yathan Roadwatcher, Lazotep Quarry |
| 50 | MISSING SELECTOR | target instant or sorcery card | 10 | 20 | 35 | Ogre Battlecaster, Flood of Recollection, Impulsivity |
| 51 | MISSING RESTRICTION | ~ can't attack or block unless … | 10 | 16 | 23 | Sab-Sunen, Luxa Embodied, Relic Golem, Hollow Warrior |
| 52 | MISSING COST / PERMISSION RULE | You may cast ~ from your … | 10 | 10 | 25 | Marang River Prowler, Quilled Greatwurm, Gravecrawler |
| 53 | MISSING EFFECT | return it to the … | 10 | 10 | 22 | Bronzehide Lion, Optimus Prime, Hero // Optimus Prime, Autobot Leader, Yedora, Grave Gardener |
| 54 | MISSING COST / PERMISSION RULE | Once during each of your turns, … | 10 | 8 | 14 | Kotis, Sibsig Champion, One with the Multiverse, Jacob Hauken, Inspector // Hauken's Insight |
| 55 | MISSING SELECTOR | target creatures | 9 | 107 | 207 | Ravenous Gigantotherium, Fire Covenant, Amazing Acrobatics |
| 56 | MISSING EFFECT | choose target … | 9 | 69 | 82 | Arcbond, Deglamer, Wreck Hunter |
| 57 | MISSING EFFECT | reveal the top n … | 9 | 56 | 74 | Green Sun's Twilight, Benefaction of Rhonas, Karn, Scion of Urza |
| 58 | MISSING EFFECT | create a n/n green … | 9 | 47 | 83 | Rhonas's Last Stand, Choco-Comet, Fractal Harness |
| 59 | MISSING EFFECT | reveal the top card … | 9 | 35 | 47 | Counterbalance, Sorin, Grim Nemesis, Sapling of Colfenor |
| 60 | MISSING EFFECT | reveal cards from the … | 9 | 25 | 31 | Treasure Hunt, Hei Bai, Forest Guardian, Hermit Druid |
| 61 | MISSING EFFECT | exile the top n … | 9 | 17 | 45 | Duplicity, Memorial Vault, Crossover Collaboration |
| 62 | MISSING EFFECT | exile up to n … | 9 | 15 | 23 | Salvation Swan, Liminal Hold, S.H.I.E.L.D. Flying Car |
| 63 | MISSING EFFECT | double the number of … | 9 | 10 | 21 | Primordial Hydra, The Millennium Calendar, Paradox Zone |
| 64 | MISSING CONTINUOUS EFFECT | You have no maximum hand size | 9 | 8 | 23 | Nyssa of Traken, Curiosity Crafter, Wizard Class |
| 65 | UNSUPPORTED ORACLE PATTERN | Web-slinging {M} | 9 | 4 | 9 | Scarlet Spider, Ben Reilly, Arachne, Psionic Weaver, Spider-Man, Brooklyn Visionary |
| 66 | MISSING TRIGGER EVENT | When ~ enters | 9 | 2 | 9 | Niv-Mizzet Reborn, Lobelia Sackville-Baggins, Drizzt Do'Urden |
| 67 | MISSING MECHANIC | companion | 9 | 1 | 9 | Lutri, the Spellchaser, Gyruda, Doom of Depths, Lurrus of the Dream-Den |
| 68 | UNSUPPORTED ORACLE PATTERN | • ~ deals N damage to … | 9 | 0 | 18 | Arbalest Engineers, Tectonic Giant, Umaro, Raging Yeti |
| 69 | UNSUPPORTED ORACLE PATTERN | Storied | 9 | 0 | 9 | Balin, Loremaster, Dáin, Lord of the Iron Hills, Ori, Keeper of Songs |
| 70 | MISSING EFFECT | you gain n … | 8 | 66 | 92 | Belladonna Took, Shu Farmer, Essence Pulse |
| 71 | MISSING EFFECT | if you control n … | 8 | 41 | 64 | Dawnhart Wardens, Boundary Lands Ranger, Dispatch |
| 72 | MISSING COST | {M}, Discard ~ | 8 | 33 | 57 | Jiwari, the Earth Aflame, Favor of Jukai, Radiant Solar |
| 73 | MISSING TRIGGER EVENT | Whenever N creature(s)(s) you control attacks alone | 8 | 19 | 22 | Finest Hour, Black Panther, Claws of Bast, Agents of S.H.I.E.L.D. |
| 74 | MISSING REPLACEMENT PATTERN | ~ enters with a ±N/±N counter(s) on … | 8 | 16 | 37 | Callous Sell-Sword // Burn Together, Avatar of the Resolute, The Duke, Rebel Sentry |
| 75 | MISSING EFFECT | up to n … | 8 | 15 | 33 | Wasp, Shrinking Savior, Restless Vinestalk, Kaito, Dancing Shadow |
| 76 | MISSING EFFECT | discard your hand … | 8 | 15 | 31 | Pyretic Charge, Bedlam Reveler, Balin, Loremaster |
| 77 | MISSING EFFECT | discard n … | 8 | 13 | 26 | Witch's Mark, Seasoned Pyromancer, Party Thrasher |
| 78 | MISSING EFFECT | exile it … | 8 | 13 | 22 | Eye of the Storm, Myrkul, Lord of Bones, Brenard, Ginger Sculptor |
| 79 | MISSING EFFECT | create a treasure token … | 8 | 8 | 18 | Beza, the Bounding Spring, Boxing Ring, Mahadi, Emporium Master |
| 80 | MISSING EFFECT | sacrifice another creature … | 8 | 8 | 16 | Rhovanion Rampager, Killmonger, Scourge of Wakanda, Kethek, Crucible Goliath |

## Largest clusters (Commander cards affected)

| # | Category | Cluster | Commander cards | Only missing piece for | Commanders | Examples |
|---|---|---|---|---|---|---|
| 1 | MISSING EFFECT | draw n … | 577 | 211 | 62 | Errand-Rider of Gondor, Krovikan Sorcerer, Heal |
| 2 | MISSING EFFECT | choose n … | 552 | 49 | 65 | Road of Return, Saheeli's Artistry, Dawnbringer Cleric |
| 3 | MISSING SELECTOR | target | 324 | 194 | 34 | Cinder Elemental, Archangel of Wrath, Chain of Plasma |
| 4 | MISSING COST / PERMISSION RULE | As an additional cost to cast … | 312 | 36 | 6 | Thunderherd Migration, Mind Extraction, Harvest Pyre |
| 5 | MISSING EFFECT | ~ deals n … | 302 | 196 | 15 | Deem Worthy, End-Blaze Epiphany, Harvest Pyre |
| 6 | MISSING EFFECT | search your library for … | 259 | 169 | 16 | Safewright Quest, Thunderherd Migration, Squadron Hawk |
| 7 | MISSING EFFECT | create n … | 253 | 152 | 37 | Summon the School, Cogwork Assembler, Endless Evil |
| 8 | MISSING REPLACEMENT PATTERN | As ~ enters, … | 237 | 47 | 4 | Kindred Discovery, Utopia Sprawl, Game Trail |
| 9 | MISSING EFFECT | until end of turn … | 227 | 157 | 23 | Divergent Growth, Doorman, Strength of Will |
| 10 | MISSING EFFECT | look at the top … | 211 | 153 | 38 | Harald, King of Skemfar, Lantern of Revealing, Puresight Merrow |
| 11 | MISSING SELECTOR | target creatures | 207 | 107 | 9 | Ravenous Gigantotherium, Fire Covenant, Amazing Acrobatics |
| 12 | MISSING EFFECT | put a ±n/±n counter(s) … | 203 | 140 | 55 | Greta, Sweettooth Scourge, Yorvo, Lord of Garenbrig, Ent-Draught Basin |
| 13 | MISSING EFFECT | destroy target … | 187 | 112 | 4 | Kalitas, Bloodchief of Ghet, Raze, Unliving Psychopath |
| 14 | MISSING EFFECT | target creature you control … | 178 | 124 | 10 | Blessed Defiance, Hard-Hitting Question, Crowd of True Believers |
| 15 | MISSING SELECTOR | target creature card | 174 | 116 | 25 | Hua Tuo, Honored Physician, Puppeteer Clique, Metamorphosis Fanatic |
| 16 | MISSING EFFECT | target creature gets ±n/±n … | 169 | 100 | 3 | Stern Marshal, Spontaneous Flight, Rig for War |
| 17 | MISSING EFFECT | pay {m} … | 166 | 109 | 53 | Labyrinth Adversary, Minion Reflector, Giant's Amulet |
| 18 | MISSING EFFECT | put n … | 148 | 93 | 28 | Black Sun's Zenith, Breaking // Entering, Mind Raker |
| 19 | MISSING EFFECT | return ~ … | 128 | 86 | 14 | Summon the School, Dragon Fangs, Haunted Dead |
| 20 | MISSING CONTINUOUS EFFECT | ~'s power and toughness are each … | 127 | 66 | 28 | Eluge, the Shoreless Sea, Flora Colossus, Revenant |
| 21 | MISSING EFFECT | if ~ … | 126 | 71 | 16 | Warden of the First Tree, Blinkmoth Urn, Mad Dog |
| 22 | MISSING CONTINUOUS EFFECT | ~ gets ±N/±N for each … | 115 | 58 | 32 | Nim Lasher, Benalish Honor Guard, Anya, Merciless Angel |
| 23 | MISSING SELECTOR | target player or planeswalker | 110 | 78 | 5 | Goblin Barrage, Scorching Missile, Consuming Sinkhole |
| 24 | MANA ABILITY WORDING | {M}, … | 108 | 78 | 6 | Saltcrusted Steppe, Cabal Stronghold, Interplanar Beacon |
| 25 | MISSING EFFECT | mill n … | 100 | 62 | 18 | Sparring Dummy, Beluna Grandsquall // Seek Thrills, Cache Grab |
| 26 | MISSING EFFECT | exile target … | 99 | 66 | 5 | Astarion's Thirst, Deadly Rollick, Tawnos's Coffin |
| 27 | MISSING MECHANIC | ward | 97 | 11 | 47 | Tyranid Harridan, Grey Host Reinforcements, Kwia Vigorbloom |
| 28 | MISSING EFFECT | if n … | 92 | 60 | 24 | Airdrop Aeronauts, Hot Pursuit, Kotis, Sibsig Champion |
| 29 | MISSING EFFECT | you gain n … | 92 | 66 | 8 | Belladonna Took, Shu Farmer, Essence Pulse |
| 30 | MISSING EFFECT | gain control of target … | 85 | 58 | 10 | Sauron, the Lidless Eye, New Blood, Unwilling Recruit |
| 31 | MISSING EFFECT | create a n/n green … | 83 | 47 | 9 | Rhonas's Last Stand, Choco-Comet, Fractal Harness |
| 32 | MISSING EFFECT | choose target … | 82 | 69 | 9 | Arcbond, Deglamer, Wreck Hunter |
| 33 | MISSING TRIGGER EVENT | When you cast ~ | 80 | 28 | 18 | Empyrial Storm, The Fourteenth Doctor, Ulamog, the Ceaseless Hunger |
| 34 | MISSING SELECTOR | target opponent reveals their hand | 79 | 53 | 1 | Gix's Caress, Mindclaw Shaman, Grief |
| 35 | MISSING SELECTOR | target card | 76 | 44 | 3 | Barkform Harvester, Carrion Locust, Heritage Reclamation |
| 36 | MISSING EFFECT | reveal the top n … | 74 | 56 | 9 | Green Sun's Twilight, Benefaction of Rhonas, Karn, Scion of Urza |
| 37 | MISSING EFFECT | if there are n … | 74 | 31 | 6 | Locked in the Cemetery, Sanguine Spy, Extricator of Sin // Extricator of Flesh |
| 38 | MISSING EFFECT | tap target … | 73 | 42 | 4 | Spider-Woman, Secret Agent, Guardian of Tazeem, Gilded Scuttler |
| 39 | MISSING EFFECT | cast ~ … | 72 | 0 | 1 | Twice Upon a Time // Unlikely Meeting, Defiant Stand, Asinine Antics |
| 40 | MISSING EFFECT | return target … | 71 | 43 | 1 | Surging Aether, Perilous Voyage, Geistwave |
| 41 | MISSING EFFECT | it deals n … | 70 | 56 | 3 | Goblin Chainwhirler, Festering Evil, Unsparing Boltcaster |
| 42 | MISSING CONTINUOUS EFFECT | ~'s power is equal to the … | 67 | 30 | 15 | Uurg, Spawn of Turg, Snow Villiers, Nethergoyf |
| 43 | MISSING EFFECT | transform ~ … | 66 | 22 | 23 | Ulvenwald Captive // Ulvenwald Abomination, Westvale Abbey // Ormendahl, Profane Prince, Seraph of New Capenna // Seraph of New Phyrexia |
| 44 | MISSING EFFECT | add {m} … | 65 | 40 | 11 | Akki Rockspeaker, Brightstone Ritual, Infernal Plunge |
| 45 | MANA ABILITY WORDING | {M}: Add N mana of any … | 65 | 37 | 2 | Flywheel Racer, Pit of Offerings, Helga, Skittish Seer |
| 46 | MISSING EFFECT | if you control n … | 64 | 41 | 8 | Dawnhart Wardens, Boundary Lands Ranger, Dispatch |
| 47 | MISSING EFFECT | create a n/n colorless … | 64 | 37 | 7 | Karn, Scion of Urza, Stalactite Dagger, Serpent Generator |
| 48 | MISSING EFFECT | exile the top card … | 62 | 26 | 24 | Moonring Mirror, Mezzio Mugger, Etali, Primal Storm |
| 49 | MISSING EFFECT | create a n/n white … | 62 | 36 | 14 | Empyrial Storm, Drag the Canal, Ajani Resolute |
| 50 | MISSING EFFECT | exile ~ … | 61 | 13 | 20 | Stenn, Paranoid Partisan, Woodland Guidance, Teferi's Protection |

## Top Commander features to implement next

Ranked by pod cards, pod commanders, cards for which it is the only missing piece, then Commander cards needing it.

| # | Feature | Kind | Pod cards | Commander cards | Only missing piece for | Examples |
|---|---|---|---|---|---|---|
| 1 | mana:ability | engine | 0 | 367 | 246 | Saltcrusted Steppe, Flywheel Racer, The Emperor of Palamecia // The Lord Master of Hell |
| 2 | template:~ enters prepared. | static | 0 | 40 | 21 | Adventurous Eater // Have a Bite, Maelstrom Artisan // Rocket Volley, Fatehold Chronologist // Peer Review |
| 3 | template:Enchanted creature has “…” | continuous | 0 | 26 | 21 | Ghostly Touch, Mark of Sakiko, Unquenchable Fury |
| 4 | keyword:bestow | keyword | 0 | 42 | 20 | Leafcrown Dryad, Baleful Eidolon, Observant Alseid |
| 5 | keyword:foretell | keyword | 0 | 51 | 19 | The Foretold Soldier, Rise of the Dread Marn, Green Slime |
| 6 | keyword:banding | keyword | 0 | 24 | 19 | Nalathni Dragon, Mishra's War Machine, Kjeldoran Escort |
| 7 | template:Commander creatures you own have “…” | continuous | 0 | 19 | 19 | Dungeon Delver, Scion of Halaster, Noble Heritage |
| 8 | keyword:equip | keyword | 0 | 49 | 17 | Bloodthorn Flail, Strong Back, Team Pennant |
| 9 | template:When ~ enters, attach it to target creature you control. | triggered | 0 | 30 | 17 | Maul of the Skyclaves, Meltstrider's Gear, Bramble Armor |
| 10 | keyword:enchant | keyword | 0 | 67 | 16 | Utopia Sprawl, One with the Stars, Corrupted Roots |
| 11 | keyword:splice | keyword | 0 | 30 | 16 | Evermind, Horobi's Whisper, Desperate Ritual |
| 12 | template:Equipped creature has “…” | continuous | 0 | 24 | 16 | Field-Tested Frying Pan, Sorcerer's Wand, Fishing Pole |
| 13 | keyword:warp | keyword | 0 | 31 | 15 | Starbreach Whale, Knight Luminary, Loading Zone |
| 14 | template:Modular N | static | 0 | 23 | 15 | Arcbound Whelp, Arcbound Javelineer, Arcbound Hybrid |
| 15 | keyword:backup | keyword | 0 | 25 | 14 | Saiba Cryptomancer, Chomping Kavu, Consuming Aetherborn |
| 16 | template:{M}: Return ~ from your graveyard to your hand. | activated | 0 | 22 | 14 | The Sound of Drums, Merchant of Many Hats, Convenient Target |
| 17 | template:~ can't be blocked by creatures with power N or less. | restriction | 0 | 32 | 13 | Glinting Creeper, Dread Linnorm // Scale Deflection, Chomping Kavu |
| 18 | keyword:encore | keyword | 0 | 26 | 13 | Impulsivity, Sliver Gravemother, Belonging |
| 19 | keyword:myriad | keyword | 0 | 23 | 13 | The Master, Multiplied, Sumala Rumblers, Conclave Evangelist |
| 20 | template:−N: You get an emblem with “…” | loyalty | 0 | 64 | 12 | Zariel, Archduke of Avernus, Elspeth, Sun's Champion, Teferi, Temporal Archmage |
| 21 | keyword:overload | keyword | 0 | 27 | 12 | Mizzium Skin, Corporeal Projection, Mind Rake |
| 22 | keyword:sneak | keyword | 0 | 27 | 12 | Turncoat Kunoichi, Michelangelo, Improviser, Donatello's Technique |
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
| 35 | keyword:retrace | keyword | 0 | 17 | 10 | Flame Jab, Monstrify, Waves of Aggression |
| 36 | template:Scavenge {M} | static | 0 | 14 | 10 | Terrus Wurm, Deadbridge Goliath, Dodgy Jalopy |
| 37 | keyword:rampage | keyword | 0 | 12 | 10 | Craw Giant, Balduvian War-Makers, Varchild's War-Riders |
| 38 | template:{M}, Sacrifice ~: It deals N damage to any target. | activated | 0 | 12 | 10 | Fireforger's Puzzleknot, Lightning Spear, Pyrite Spellbomb |
| 39 | template:Enchanted land has “…” | continuous | 0 | 11 | 10 | Chamber of Manipulation, Discreet Retreat, Farmstead |
| 40 | template:~ enters tapped unless you control N or fewer other lands. | replacement | 0 | 11 | 10 | Concealed Courtyard, Inspiring Vantage, Blackcleave Cliffs |
| 41 | template:~ enters tapped unless a player has N or less life. | replacement | 0 | 10 | 10 | Abandoned Campground, Raucous Carnival, Strangled Cemetery |
| 42 | template:~ enters tapped unless you control N or more basic lands. | replacement | 0 | 10 | 10 | Sodden Verdure, Smoldering Marsh, Vernal Fen |
| 43 | template:~ enters tapped unless you control N or more other lands. | replacement | 0 | 10 | 10 | Rockfall Vale, Stormcarved Coast, Sundown Pass |
| 44 | template:~ enters tapped unless you control a planeswalker. | replacement | 0 | 10 | 10 | Theorix Annex, Stingerquill Annex, Konstrari Annex |
| 45 | template:~ enters tapped unless you have N or more opponents. | replacement | 0 | 10 | 10 | Spire Garden, Sea of Clouds, Bountiful Promenade |
| 46 | template:You control enchanted creature. | static | 0 | 28 | 9 | Spirit Away, Illusory Gains, Biting Tether |
| 47 | keyword:cumulative upkeep | keyword | 0 | 23 | 9 | Varchild's War-Riders, Aboroth, Inner Sanctum |
| 48 | keyword:living weapon | keyword | 0 | 19 | 9 | Nettlecyst, Lashwrithe, Skinwing |
| 49 | keyword:extort | keyword | 0 | 17 | 9 | Syndicate Heavy, Tithe Drinker, Kingpin's Pet |
| 50 | keyword:fading | keyword | 0 | 17 | 9 | Parallax Wave, Phyrexian Prowler, Skyshroud Ridgeback |
| 51 | keyword:embalm | keyword | 0 | 15 | 9 | Heart-Piercer Manticore, Angel of Sanctions, Anointer Priest |
| 52 | template:Prevent all combat damage that would be dealt this turn. | prevention | 0 | 14 | 9 | Jaheira's Respite, Fog, Darkness |
| 53 | template:{M}, {M}, Sacrifice ~: It deals N damage to target creature. | activated | 0 | 11 | 9 | Vial of Dragonfire, Flamecast Wheel, Mouth of Ronom |
| 54 | keyword:kicker | keyword | 0 | 37 | 8 | Goblin Barrage, Archangel of Wrath, Anavolver |
| 55 | keyword:plot | keyword | 0 | 33 | 8 | Unscrupulous Contractor, Pyretic Charge, Freestrider Commando |
| 56 | template:You have no maximum hand size. | continuous | 0 | 23 | 8 | Nyssa of Traken, Curiosity Crafter, Wizard Class |
| 57 | keyword:evolve | keyword | 0 | 22 | 8 | Adaptive Snapjaw, Shambleshark, Tyranid Prime |
| 58 | keyword:vanishing | keyword | 0 | 20 | 8 | Soultether Golem, Deadly Grub, Reality Acid |
| 59 | keyword:replicate | keyword | 0 | 19 | 8 | Consign to Memory, Psionic Ritual, Lose Focus |
| 60 | template:~'s power and toughness are each equal to the number of lands you control. | characteristic_defining | 0 | 17 | 8 | Flora Colossus, Rubblehulk, Harmonious Grovestrider |

## Coverage by card type

| Type | FULL | PARTIAL | REVIEW | MANUAL |
|---|---|---|---|---|
| Creature | 6165 | 11756 | 0 | 0 |
| Artifact | 1000 | 2593 | 0 | 0 |
| Enchantment | 767 | 2880 | 0 | 0 |
| Sorcery | 846 | 2722 | 0 | 0 |
| Instant | 1134 | 2620 | 0 | 0 |
| Land | 528 | 684 | 0 | 0 |
| Planeswalker | 12 | 299 | 0 | 0 |
| Battle | 0 | 36 | 0 | 0 |

## Rules features in the pool (ability lines)

triggered 14909, keyword 14139, spell_effect 9115, activated 7358, continuous 4014, static 3053, mana_ability 2038, replacement 1966, restriction 1474, loyalty 882, prevention 320, additional_cost 307, cost_modifier 261, characteristic_defining 247, permission 207, alternative_cost 180

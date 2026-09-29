# Commander rules coverage

Card data: Scryfall `2026-09-28T21:01:54.353+00:00` · Comprehensive Rules 2026-09-25 · rules engine v2 · generated 2026-09-29 22:43

Only cards that are **legal in Commander today** count. Banned cards (83) are COMMANDER_BANNED and excluded.

## Commander coverage

Commander-legal cards: **32116**

| Level | Cards | Share |
|---|---|---|
| FULL | 10066 | 31.3% |
| PARTIAL | 22002 | 68.5% |
| REVIEW | 0 | 0.0% |
| MANUAL | 48 | 0.1% |

Possible commanders (CR 903.3/903.3a, incl. Backgrounds): **3501** — FULL 457, PARTIAL 3044, REVIEW 0, MANUAL 0

## Pod coverage

No pod decks in the inventory yet (`python -m tools.rules_inventory`); the queue below is ranked by Commander-legal cards unlocked.

## Coverage quality

- Ability features (lines, keywords, play/cast/combat) across Commander-legal cards: 113346
- Automated: 81871 (72.2%) · unrecognized clauses: 31475
- Oracle text classified (automated, or sorted into a concrete missing capability): 97.4% · unclassified clauses: 2936
- Distinct missing-capability clusters: 8503

## Missing capabilities by category

| Category | Cards affected | Clauses |
|---|---|---|
| MISSING EFFECT | 11727 | 13804 |
| MISSING SELECTOR | 3568 | 3774 |
| MISSING TRIGGER EVENT | 2410 | 2524 |
| MISSING CONTINUOUS EFFECT | 2200 | 2324 |
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
| 1 | MISSING EFFECT | draw n … | 66 | 224 | 595 | Errand-Rider of Gondor, Krovikan Sorcerer, Heal |
| 2 | MISSING EFFECT | choose n … | 65 | 50 | 564 | Road of Return, Saheeli's Artistry, Dawnbringer Cleric |
| 3 | MISSING EFFECT | put a ±n/±n counter(s) … | 61 | 161 | 232 | Greta, Sweettooth Scourge, Yorvo, Lord of Garenbrig, Ent-Draught Basin |
| 4 | MISSING EFFECT | pay {m} … | 56 | 119 | 177 | Labyrinth Adversary, Minion Reflector, Giant's Amulet |
| 5 | MISSING MECHANIC | ward | 47 | 13 | 97 | Tyranid Harridan, Grey Host Reinforcements, Kwia Vigorbloom |
| 6 | MISSING EFFECT | look at the top … | 39 | 160 | 217 | Harald, King of Skemfar, Lantern of Revealing, Puresight Merrow |
| 7 | MISSING EFFECT | create n … | 38 | 154 | 258 | Summon the School, Cogwork Assembler, Endless Evil |
| 8 | MISSING SELECTOR | target | 36 | 204 | 334 | Cinder Elemental, Archangel of Wrath, Chain of Plasma |
| 9 | MISSING EFFECT | exile the top card … | 36 | 54 | 115 | Moonring Mirror, Professional Face-Breaker, Mezzio Mugger |
| 10 | MISSING CONTINUOUS EFFECT | ~ gets ±N/±N for each … | 32 | 58 | 115 | Nim Lasher, Benalish Honor Guard, Anya, Merciless Angel |
| 11 | MISSING EFFECT | put n … | 28 | 96 | 150 | Black Sun's Zenith, Breaking // Entering, Mind Raker |
| 12 | MISSING CONTINUOUS EFFECT | ~'s power and toughness are each … | 28 | 67 | 127 | Eluge, the Shoreless Sea, Flora Colossus, Revenant |
| 13 | MISSING SELECTOR | target creature card | 25 | 117 | 174 | Hua Tuo, Honored Physician, Puppeteer Clique, Metamorphosis Fanatic |
| 14 | MISSING EFFECT | if n … | 24 | 60 | 92 | Airdrop Aeronauts, Hot Pursuit, Kotis, Sibsig Champion |
| 15 | MISSING EFFECT | until end of turn … | 23 | 155 | 227 | Divergent Growth, Doorman, Strength of Will |
| 16 | MISSING EFFECT | transform ~ … | 23 | 25 | 69 | Ulvenwald Captive // Ulvenwald Abomination, Westvale Abbey // Ormendahl, Profane Prince, Seraph of New Capenna // Seraph of New Phyrexia |
| 17 | UNSUPPORTED ORACLE PATTERN | As long as your devotion to … | 22 | 7 | 22 | Phenax, God of Deception, Erebos, God of the Dead, Thassa, Deep-Dwelling |
| 18 | UNSUPPORTED ORACLE PATTERN | You may look at the top … | 22 | 2 | 45 | One with the Multiverse, The Lunar Whale, Cemetery Illuminator |
| 19 | MISSING EFFECT | exile ~ … | 20 | 13 | 61 | Stenn, Paranoid Partisan, Woodland Guidance, Teferi's Protection |
| 20 | MISSING EFFECT | if ~ … | 19 | 74 | 130 | Warden of the First Tree, Hixus, Prison Warden, Blinkmoth Urn |
| 21 | UNSUPPORTED ORACLE PATTERN | ~ costs {M} less to cast … | 19 | 39 | 71 | Bedlam Reveler, Gargantuan Leech, Hamza, Guardian of Arashin |
| 22 | MISSING EFFECT | mill n … | 18 | 66 | 103 | Sparring Dummy, Loafing Giant, Beluna Grandsquall // Seek Thrills |
| 23 | MISSING TRIGGER EVENT | When you cast ~ | 18 | 30 | 80 | Empyrial Storm, The Fourteenth Doctor, Ulamog, the Ceaseless Hunger |
| 24 | MISSING EFFECT | create a n/n red … | 17 | 34 | 61 | Prosperity Tycoon, Ertha Jo, Frontier Mentor, Nesting Dragon |
| 25 | MISSING EFFECT | search your library for … | 16 | 171 | 263 | Safewright Quest, Thunderherd Migration, Squadron Hawk |
| 26 | MISSING EFFECT | create a n/n black … | 16 | 38 | 60 | Queen Brahne, Grist, the Hunger Tide, Mysidian Elder |
| 27 | MISSING CONTINUOUS EFFECT | Commander creatures you own have “…” | 16 | 16 | 16 | Dungeon Delver, Noble Heritage, Acolyte of Bahamut |
| 28 | MISSING CONTINUOUS EFFECT | ~'s power is equal to the … | 15 | 29 | 67 | Uurg, Spawn of Turg, Snow Villiers, Nethergoyf |
| 29 | UNSUPPORTED ORACLE PATTERN | As ~ enters, … | 15 | 1 | 19 | Stenn, Paranoid Partisan, Arachne, Psionic Weaver, Pramikon, Sky Rampart |
| 30 | UNSUPPORTED ORACLE PATTERN | More Than Meets the Eye {M} | 15 | 0 | 15 | Optimus Prime, Hero // Optimus Prime, Autobot Leader, Megatron, Tyrant // Megatron, Destructive Force, Jetfire, Ingenious Scientist // Jetfire, Air Guardian |
| 31 | MISSING EFFECT | ~ deals n … | 14 | 210 | 324 | Deem Worthy, End-Blaze Epiphany, Harvest Pyre |
| 32 | MISSING EFFECT | return ~ … | 14 | 86 | 128 | Summon the School, Dragon Fangs, Haunted Dead |
| 33 | MISSING EFFECT | create a n/n white … | 14 | 39 | 65 | Empyrial Storm, Drag the Canal, Ajani Resolute |
| 34 | MISSING MECHANIC | sneak | 14 | 12 | 27 | Turncoat Kunoichi, Michelangelo, Improviser, Donatello's Technique |
| 35 | MISSING MECHANIC | firebending | 14 | 6 | 22 | Fire Sages, Loyal Fire Sage, Jeong Jeong, the Deserter |
| 36 | MISSING MECHANIC | partner | 14 | 5 | 24 | Lore Weaver, Blaring Captain, Rory Williams |
| 37 | UNSUPPORTED ORACLE PATTERN | • Put a ±N/±N counter(s) on … | 14 | 0 | 38 | Bejeweled Warg, Trusty Retriever, Inspired Inventor |
| 38 | MISSING EFFECT | add {m} … | 13 | 42 | 70 | Waste Not, Akki Rockspeaker, Brightstone Ritual |
| 39 | UNSUPPORTED ORACLE PATTERN | Living metal | 13 | 0 | 13 | Optimus Prime, Hero // Optimus Prime, Autobot Leader, Megatron, Tyrant // Megatron, Destructive Force, Jetfire, Ingenious Scientist // Jetfire, Air Guardian |
| 40 | MISSING RESTRICTION | ~ can't be blocked by creatures … | 12 | 28 | 56 | Lydia Frye, Pompous Gadabout, Ghost of Ramirez DePietro |
| 41 | MISSING EFFECT | exile the top n … | 12 | 21 | 59 | Duplicity, Memorial Vault, Crossover Collaboration |
| 42 | MISSING SELECTOR | target equipment | 12 | 18 | 26 | Stolen Uniform, Shagrat, Loot Bearer, Thor, God of Thunder |
| 43 | UNSUPPORTED ORACLE PATTERN | Power-up — {M}: Put N ±N/±N … | 12 | 12 | 19 | Thanos, the Mad Titan, Shang-Chi, Martial Mentor, Hulk, Gamma Goliath |
| 44 | MISSING EFFECT | target creature you control … | 11 | 124 | 179 | Blessed Defiance, Hard-Hitting Question, Crowd of True Believers |
| 45 | MISSING TRIGGER EVENT | Whenever you cast a historic spell | 11 | 15 | 19 | Serra Disciple, Cabal Paladin, Glóin, Dwarf Emissary |
| 46 | MISSING EFFECT | earthbend n … | 11 | 14 | 27 | Earth Village Ruffians, Bumi, Unleashed, Badgermole |
| 47 | MISSING EFFECT | another target … | 11 | 14 | 23 | Hemosymbic Mite, Syr Faren, the Hengehammer, Pippin, Guard of the Citadel |
| 48 | MISSING COST / PERMISSION RULE | You may cast ~ from your … | 11 | 10 | 27 | Marang River Prowler, Quilled Greatwurm, Gravecrawler |
| 49 | MISSING COST / PERMISSION RULE | Once during each of your turns, … | 11 | 7 | 15 | Kotis, Sibsig Champion, One with the Multiverse, Jacob Hauken, Inspector // Hauken's Insight |
| 50 | MISSING EFFECT | if you've cast a … | 11 | 5 | 12 | H.E.R.B.I.E., Lovable Robot, Invisible Woman, Alicia Masters, Skilled Sculptor |
| 51 | MISSING EFFECT | gain control of target … | 10 | 58 | 85 | Sauron, the Lidless Eye, New Blood, Unwilling Recruit |
| 52 | MISSING EFFECT | reveal the top card … | 10 | 34 | 48 | Rashmi, Eternities Crafter, Counterbalance, Sorin, Grim Nemesis |
| 53 | MISSING SELECTOR | target creature card with mana value | 10 | 26 | 39 | General Leo Cristophe, Yathan Roadwatcher, Lazotep Quarry |
| 54 | MISSING SELECTOR | target instant or sorcery card | 10 | 20 | 35 | Ogre Battlecaster, Flood of Recollection, Impulsivity |
| 55 | MISSING RESTRICTION | ~ can't attack or block unless … | 10 | 16 | 23 | Sab-Sunen, Luxa Embodied, Relic Golem, Hollow Warrior |
| 56 | MISSING EFFECT | return it to the … | 10 | 11 | 23 | Bronzehide Lion, Optimus Prime, Hero // Optimus Prime, Autobot Leader, Yedora, Grave Gardener |
| 57 | MISSING SELECTOR | target creatures | 9 | 106 | 208 | Ravenous Gigantotherium, Fire Covenant, Amazing Acrobatics |
| 58 | MISSING EFFECT | choose target … | 9 | 71 | 83 | Arcbond, Deglamer, Wreck Hunter |
| 59 | MISSING EFFECT | you gain n … | 9 | 68 | 94 | Belladonna Took, Shu Farmer, Essence Pulse |
| 60 | MISSING EFFECT | reveal the top n … | 9 | 56 | 75 | Green Sun's Twilight, Benefaction of Rhonas, Karn, Scion of Urza |
| 61 | MISSING EFFECT | create a n/n green … | 9 | 46 | 84 | Rhonas's Last Stand, Choco-Comet, Fractal Harness |
| 62 | MISSING EFFECT | reveal cards from the … | 9 | 26 | 32 | Treasure Hunt, Hei Bai, Forest Guardian, Hermit Druid |
| 63 | MISSING EFFECT | exile up to n … | 9 | 17 | 27 | Salvation Swan, Liminal Hold, S.H.I.E.L.D. Flying Car |
| 64 | MISSING EFFECT | double the number of … | 9 | 12 | 24 | Fractal Harness, Primordial Hydra, The Millennium Calendar |
| 65 | MISSING CONTINUOUS EFFECT | You have no maximum hand size | 9 | 8 | 23 | Nyssa of Traken, Curiosity Crafter, Wizard Class |
| 66 | MISSING CONTINUOUS EFFECT | During your turn, … | 9 | 7 | 18 | Long-Lost Lances, Miriam, Herd Whisperer, Yuna, Hope of Spira |
| 67 | UNSUPPORTED ORACLE PATTERN | Web-slinging {M} | 9 | 4 | 9 | Scarlet Spider, Ben Reilly, Arachne, Psionic Weaver, Spider-Man, Brooklyn Visionary |
| 68 | MISSING TRIGGER EVENT | When ~ enters | 9 | 2 | 9 | Niv-Mizzet Reborn, Lobelia Sackville-Baggins, Drizzt Do'Urden |
| 69 | MISSING MECHANIC | companion | 9 | 1 | 9 | Lutri, the Spellchaser, Gyruda, Doom of Depths, Lurrus of the Dream-Den |
| 70 | UNSUPPORTED ORACLE PATTERN | • ~ deals N damage to … | 9 | 0 | 18 | Arbalest Engineers, Tectonic Giant, Umaro, Raging Yeti |
| 71 | UNSUPPORTED ORACLE PATTERN | Storied | 9 | 0 | 9 | Balin, Loremaster, Dáin, Lord of the Iron Hills, Ori, Keeper of Songs |
| 72 | MISSING EFFECT | if you control n … | 8 | 42 | 67 | Dawnhart Wardens, Boundary Lands Ranger, Dispatch |
| 73 | MISSING COST | {M}, Discard ~ | 8 | 34 | 57 | Jiwari, the Earth Aflame, Favor of Jukai, Radiant Solar |
| 74 | MISSING SELECTOR | target creature defending player controls | 8 | 31 | 41 | Fear of Falling, Impetuous Devils, Fiend Binder |
| 75 | MISSING REPLACEMENT PATTERN | ~ enters with a ±N/±N counter(s) on … | 8 | 17 | 37 | Callous Sell-Sword // Burn Together, Avatar of the Resolute, The Duke, Rebel Sentry |
| 76 | MISSING EFFECT | you draw n … | 8 | 17 | 35 | Fang, Fearless l'Cie, Live Fast, Greed's Gambit |
| 77 | MISSING EFFECT | up to n … | 8 | 15 | 33 | Wasp, Shrinking Savior, Restless Vinestalk, Kaito, Dancing Shadow |
| 78 | MISSING EFFECT | discard your hand … | 8 | 15 | 31 | Pyretic Charge, Bedlam Reveler, Balin, Loremaster |
| 79 | MISSING EFFECT | discard n … | 8 | 13 | 26 | Witch's Mark, Seasoned Pyromancer, Party Thrasher |
| 80 | MISSING EFFECT | create a treasure token … | 8 | 8 | 19 | Beza, the Bounding Spring, Boxing Ring, Mahadi, Emporium Master |

## Largest clusters (Commander cards affected)

| # | Category | Cluster | Commander cards | Only missing piece for | Commanders | Examples |
|---|---|---|---|---|---|---|
| 1 | MISSING EFFECT | draw n … | 595 | 224 | 66 | Errand-Rider of Gondor, Krovikan Sorcerer, Heal |
| 2 | MISSING EFFECT | choose n … | 564 | 50 | 65 | Road of Return, Saheeli's Artistry, Dawnbringer Cleric |
| 3 | MISSING SELECTOR | target | 334 | 204 | 36 | Cinder Elemental, Archangel of Wrath, Chain of Plasma |
| 4 | MISSING EFFECT | ~ deals n … | 324 | 210 | 14 | Deem Worthy, End-Blaze Epiphany, Harvest Pyre |
| 5 | MISSING COST / PERMISSION RULE | As an additional cost to cast … | 312 | 35 | 6 | Thunderherd Migration, Mind Extraction, Harvest Pyre |
| 6 | MISSING EFFECT | search your library for … | 263 | 171 | 16 | Safewright Quest, Thunderherd Migration, Squadron Hawk |
| 7 | MISSING EFFECT | create n … | 258 | 154 | 38 | Summon the School, Cogwork Assembler, Endless Evil |
| 8 | MISSING REPLACEMENT PATTERN | As ~ enters, … | 237 | 47 | 4 | Kindred Discovery, Utopia Sprawl, Game Trail |
| 9 | MISSING EFFECT | put a ±n/±n counter(s) … | 232 | 161 | 61 | Greta, Sweettooth Scourge, Yorvo, Lord of Garenbrig, Ent-Draught Basin |
| 10 | MISSING EFFECT | until end of turn … | 227 | 155 | 23 | Divergent Growth, Doorman, Strength of Will |
| 11 | MISSING EFFECT | look at the top … | 217 | 160 | 39 | Harald, King of Skemfar, Lantern of Revealing, Puresight Merrow |
| 12 | MISSING SELECTOR | target creatures | 208 | 106 | 9 | Ravenous Gigantotherium, Fire Covenant, Amazing Acrobatics |
| 13 | MISSING EFFECT | destroy target … | 197 | 119 | 4 | Kalitas, Bloodchief of Ghet, Raze, Unliving Psychopath |
| 14 | MISSING EFFECT | target creature you control … | 179 | 124 | 11 | Blessed Defiance, Hard-Hitting Question, Crowd of True Believers |
| 15 | MISSING EFFECT | pay {m} … | 177 | 119 | 56 | Labyrinth Adversary, Minion Reflector, Giant's Amulet |
| 16 | MISSING SELECTOR | target creature card | 174 | 117 | 25 | Hua Tuo, Honored Physician, Puppeteer Clique, Metamorphosis Fanatic |
| 17 | MISSING EFFECT | target creature gets ±n/±n … | 171 | 102 | 4 | Stern Marshal, Spontaneous Flight, Rig for War |
| 18 | MISSING EFFECT | put n … | 150 | 96 | 28 | Black Sun's Zenith, Breaking // Entering, Mind Raker |
| 19 | MISSING EFFECT | if ~ … | 130 | 74 | 19 | Warden of the First Tree, Hixus, Prison Warden, Blinkmoth Urn |
| 20 | MISSING EFFECT | return ~ … | 128 | 86 | 14 | Summon the School, Dragon Fangs, Haunted Dead |
| 21 | MISSING CONTINUOUS EFFECT | ~'s power and toughness are each … | 127 | 67 | 28 | Eluge, the Shoreless Sea, Flora Colossus, Revenant |
| 22 | MISSING EFFECT | exile the top card … | 115 | 54 | 36 | Moonring Mirror, Professional Face-Breaker, Mezzio Mugger |
| 23 | MISSING CONTINUOUS EFFECT | ~ gets ±N/±N for each … | 115 | 58 | 32 | Nim Lasher, Benalish Honor Guard, Anya, Merciless Angel |
| 24 | MISSING SELECTOR | target player or planeswalker | 111 | 79 | 5 | Goblin Barrage, Scorching Missile, Consuming Sinkhole |
| 25 | MANA ABILITY WORDING | {M}, … | 108 | 78 | 6 | Saltcrusted Steppe, Cabal Stronghold, Interplanar Beacon |
| 26 | MISSING EFFECT | mill n … | 103 | 66 | 18 | Sparring Dummy, Loafing Giant, Beluna Grandsquall // Seek Thrills |
| 27 | MISSING EFFECT | exile target … | 103 | 69 | 5 | Astarion's Thirst, Deadly Rollick, Tawnos's Coffin |
| 28 | MISSING MECHANIC | ward | 97 | 13 | 47 | Tyranid Harridan, Grey Host Reinforcements, Kwia Vigorbloom |
| 29 | MISSING EFFECT | you gain n … | 94 | 68 | 9 | Belladonna Took, Shu Farmer, Essence Pulse |
| 30 | MISSING EFFECT | if n … | 92 | 60 | 24 | Airdrop Aeronauts, Hot Pursuit, Kotis, Sibsig Champion |
| 31 | MISSING EFFECT | gain control of target … | 85 | 58 | 10 | Sauron, the Lidless Eye, New Blood, Unwilling Recruit |
| 32 | MISSING EFFECT | create a n/n green … | 84 | 46 | 9 | Rhonas's Last Stand, Choco-Comet, Fractal Harness |
| 33 | MISSING EFFECT | choose target … | 83 | 71 | 9 | Arcbond, Deglamer, Wreck Hunter |
| 34 | MISSING TRIGGER EVENT | When you cast ~ | 80 | 30 | 18 | Empyrial Storm, The Fourteenth Doctor, Ulamog, the Ceaseless Hunger |
| 35 | MISSING SELECTOR | target opponent reveals their hand | 79 | 53 | 1 | Gix's Caress, Mindclaw Shaman, Grief |
| 36 | MISSING EFFECT | tap target … | 78 | 45 | 4 | Spider-Woman, Secret Agent, Guardian of Tazeem, Gilded Scuttler |
| 37 | MISSING EFFECT | if there are n … | 76 | 31 | 6 | Locked in the Cemetery, Sanguine Spy, Extricator of Sin // Extricator of Flesh |
| 38 | MISSING SELECTOR | target card | 76 | 44 | 3 | Barkform Harvester, Carrion Locust, Heritage Reclamation |
| 39 | MISSING EFFECT | reveal the top n … | 75 | 56 | 9 | Green Sun's Twilight, Benefaction of Rhonas, Karn, Scion of Urza |
| 40 | MISSING EFFECT | it deals n … | 75 | 60 | 3 | Goblin Chainwhirler, Festering Evil, Unsparing Boltcaster |
| 41 | MISSING EFFECT | return target … | 74 | 44 | 1 | Surging Aether, Perilous Voyage, Geistwave |
| 42 | MISSING EFFECT | cast ~ … | 72 | 0 | 1 | Twice Upon a Time // Unlikely Meeting, Defiant Stand, Asinine Antics |
| 43 | UNSUPPORTED ORACLE PATTERN | ~ costs {M} less to cast … | 71 | 39 | 19 | Bedlam Reveler, Gargantuan Leech, Hamza, Guardian of Arashin |
| 44 | MISSING EFFECT | add {m} … | 70 | 42 | 13 | Waste Not, Akki Rockspeaker, Brightstone Ritual |
| 45 | MISSING EFFECT | transform ~ … | 69 | 25 | 23 | Ulvenwald Captive // Ulvenwald Abomination, Westvale Abbey // Ormendahl, Profane Prince, Seraph of New Capenna // Seraph of New Phyrexia |
| 46 | MISSING EFFECT | create a n/n colorless … | 68 | 40 | 7 | Karn, Scion of Urza, Stalactite Dagger, Serpent Generator |
| 47 | MISSING CONTINUOUS EFFECT | ~'s power is equal to the … | 67 | 29 | 15 | Uurg, Spawn of Turg, Snow Villiers, Nethergoyf |
| 48 | MISSING EFFECT | if you control n … | 67 | 42 | 8 | Dawnhart Wardens, Boundary Lands Ranger, Dispatch |
| 49 | MISSING EFFECT | create a n/n white … | 65 | 39 | 14 | Empyrial Storm, Drag the Canal, Ajani Resolute |
| 50 | MANA ABILITY WORDING | {M}: Add N mana of any … | 65 | 36 | 2 | Flywheel Racer, Pit of Offerings, Helga, Skittish Seer |

## Top Commander features to implement next

Ranked by pod cards, pod commanders, cards for which it is the only missing piece, then Commander cards needing it.

| # | Feature | Kind | Pod cards | Commander cards | Only missing piece for | Examples |
|---|---|---|---|---|---|---|
| 1 | mana:ability | engine | 0 | 367 | 242 | Saltcrusted Steppe, Flywheel Racer, The Emperor of Palamecia // The Lord Master of Hell |
| 2 | template:Enchanted creature has “…” | continuous | 0 | 28 | 22 | Ghostly Touch, Mark of Sakiko, Unquenchable Fury |
| 3 | keyword:foretell | keyword | 0 | 51 | 21 | The Foretold Soldier, Rise of the Dread Marn, Green Slime |
| 4 | template:~ enters prepared. | static | 0 | 40 | 21 | Adventurous Eater // Have a Bite, Maelstrom Artisan // Rocket Volley, Fatehold Chronologist // Peer Review |
| 5 | keyword:enchant | keyword | 0 | 67 | 20 | Utopia Sprawl, One with the Stars, Corrupted Roots |
| 6 | keyword:bestow | keyword | 0 | 42 | 20 | Leafcrown Dryad, Baleful Eidolon, Observant Alseid |
| 7 | keyword:banding | keyword | 0 | 24 | 19 | Nalathni Dragon, Mishra's War Machine, Kjeldoran Escort |
| 8 | template:Commander creatures you own have “…” | continuous | 0 | 19 | 19 | Dungeon Delver, Scion of Halaster, Noble Heritage |
| 9 | template:When ~ enters, attach it to target creature you control. | triggered | 0 | 30 | 17 | Maul of the Skyclaves, Meltstrider's Gear, Bramble Armor |
| 10 | keyword:backup | keyword | 0 | 25 | 17 | Saiba Cryptomancer, Chomping Kavu, Consuming Aetherborn |
| 11 | keyword:equip | keyword | 0 | 49 | 16 | Bloodthorn Flail, Strong Back, Team Pennant |
| 12 | keyword:splice | keyword | 0 | 30 | 16 | Evermind, Horobi's Whisper, Desperate Ritual |
| 13 | template:Equipped creature has “…” | continuous | 0 | 24 | 16 | Field-Tested Frying Pan, Sorcerer's Wand, Fishing Pole |
| 14 | keyword:warp | keyword | 0 | 31 | 15 | Starbreach Whale, Knight Luminary, Loading Zone |
| 15 | template:Modular N | static | 0 | 23 | 15 | Arcbound Whelp, Arcbound Javelineer, Arcbound Hybrid |
| 16 | template:~ can't be blocked by creatures with power N or less. | restriction | 0 | 32 | 14 | Glinting Creeper, Dread Linnorm // Scale Deflection, Chomping Kavu |
| 17 | template:{M}: Return ~ from your graveyard to your hand. | activated | 0 | 22 | 14 | The Sound of Drums, Merchant of Many Hats, Convenient Target |
| 18 | keyword:ward | keyword | 0 | 97 | 13 | Tyranid Harridan, Grey Host Reinforcements, Kwia Vigorbloom |
| 19 | keyword:encore | keyword | 0 | 26 | 13 | Impulsivity, Sliver Gravemother, Belonging |
| 20 | keyword:myriad | keyword | 0 | 23 | 13 | The Master, Multiplied, Sumala Rumblers, Conclave Evangelist |
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
| 36 | keyword:embalm | keyword | 0 | 15 | 10 | Heart-Piercer Manticore, Angel of Sanctions, Anointer Priest |
| 37 | template:Scavenge {M} | static | 0 | 14 | 10 | Terrus Wurm, Deadbridge Goliath, Dodgy Jalopy |
| 38 | keyword:rampage | keyword | 0 | 12 | 10 | Craw Giant, Balduvian War-Makers, Varchild's War-Riders |
| 39 | template:{M}, Sacrifice ~: It deals N damage to any target. | activated | 0 | 12 | 10 | Fireforger's Puzzleknot, Lightning Spear, Pyrite Spellbomb |
| 40 | template:Enchanted land has “…” | continuous | 0 | 11 | 10 | Chamber of Manipulation, Discreet Retreat, Farmstead |
| 41 | template:~ enters tapped unless you control N or fewer other lands. | replacement | 0 | 11 | 10 | Concealed Courtyard, Inspiring Vantage, Blackcleave Cliffs |
| 42 | template:~ enters tapped unless a player has N or less life. | replacement | 0 | 10 | 10 | Abandoned Campground, Raucous Carnival, Strangled Cemetery |
| 43 | template:~ enters tapped unless you control N or more basic lands. | replacement | 0 | 10 | 10 | Sodden Verdure, Smoldering Marsh, Vernal Fen |
| 44 | template:~ enters tapped unless you control N or more other lands. | replacement | 0 | 10 | 10 | Rockfall Vale, Stormcarved Coast, Sundown Pass |
| 45 | template:~ enters tapped unless you control a planeswalker. | replacement | 0 | 10 | 10 | Theorix Annex, Stingerquill Annex, Konstrari Annex |
| 46 | template:~ enters tapped unless you have N or more opponents. | replacement | 0 | 10 | 10 | Spire Garden, Sea of Clouds, Bountiful Promenade |
| 47 | template:You control enchanted creature. | static | 0 | 28 | 9 | Spirit Away, Illusory Gains, Biting Tether |
| 48 | keyword:cumulative upkeep | keyword | 0 | 23 | 9 | Varchild's War-Riders, Aboroth, Inner Sanctum |
| 49 | keyword:vanishing | keyword | 0 | 20 | 9 | Soultether Golem, Deadly Grub, Reality Acid |
| 50 | keyword:extort | keyword | 0 | 17 | 9 | Syndicate Heavy, Tithe Drinker, Kingpin's Pet |
| 51 | keyword:fading | keyword | 0 | 17 | 9 | Parallax Wave, Phyrexian Prowler, Skyshroud Ridgeback |
| 52 | keyword:retrace | keyword | 0 | 17 | 9 | Flame Jab, Monstrify, Waves of Aggression |
| 53 | template:Prevent all combat damage that would be dealt this turn. | prevention | 0 | 14 | 9 | Jaheira's Respite, Fog, Darkness |
| 54 | template:{M}, {M}, Sacrifice ~: It deals N damage to target creature. | activated | 0 | 11 | 9 | Vial of Dragonfire, Flamecast Wheel, Mouth of Ronom |
| 55 | keyword:kicker | keyword | 0 | 37 | 8 | Goblin Barrage, Archangel of Wrath, Anavolver |
| 56 | template:You have no maximum hand size. | continuous | 0 | 23 | 8 | Nyssa of Traken, Curiosity Crafter, Wizard Class |
| 57 | keyword:replicate | keyword | 0 | 19 | 8 | Consign to Memory, Psionic Ritual, Lose Focus |
| 58 | template:~'s power and toughness are each equal to the number of lands you control. | characteristic_defining | 0 | 17 | 8 | Flora Colossus, Rubblehulk, Harmonious Grovestrider |
| 59 | template:Equipped creature gets ±N/±N and has “…” | continuous | 0 | 14 | 8 | Giant's Amulet, Dire Flail // Dire Blunderbuss, Citizen's Crowbar |
| 60 | keyword:battle cry | keyword | 0 | 13 | 8 | Goblin Wardriver, Hero of Bladehold, Iraxxa, Empress of Mars |

## Coverage by card type

| Type | FULL | PARTIAL | REVIEW | MANUAL |
|---|---|---|---|---|
| Creature | 6339 | 11582 | 0 | 0 |
| Artifact | 989 | 2604 | 0 | 0 |
| Enchantment | 836 | 2811 | 0 | 0 |
| Sorcery | 828 | 2740 | 0 | 0 |
| Instant | 1102 | 2652 | 0 | 0 |
| Land | 525 | 687 | 0 | 0 |
| Planeswalker | 12 | 299 | 0 | 0 |
| Battle | 0 | 36 | 0 | 0 |

## Rules features in the pool (ability lines)

triggered 14909, keyword 14134, spell_effect 9120, activated 7358, continuous 4014, static 3053, mana_ability 2038, replacement 1966, restriction 1474, loyalty 882, prevention 320, additional_cost 307, cost_modifier 261, characteristic_defining 247, permission 207, alternative_cost 180

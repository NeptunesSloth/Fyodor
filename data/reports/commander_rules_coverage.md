# Commander rules coverage

Card data: Scryfall `2026-09-28T21:01:54.353+00:00` · Comprehensive Rules 2026-09-25 · rules engine v2 · generated 2026-09-29 22:39

Only cards that are **legal in Commander today** count. Banned cards (83) are COMMANDER_BANNED and excluded.

## Commander coverage

Commander-legal cards: **32116**

| Level | Cards | Share |
|---|---|---|
| FULL | 9073 | 28.3% |
| PARTIAL | 22995 | 71.6% |
| REVIEW | 0 | 0.0% |
| MANUAL | 48 | 0.1% |

Possible commanders (CR 903.3/903.3a, incl. Backgrounds): **3501** — FULL 369, PARTIAL 3132, REVIEW 0, MANUAL 0

## Pod coverage

No pod decks in the inventory yet (`python -m tools.rules_inventory`); the queue below is ranked by Commander-legal cards unlocked.

## Coverage quality

- Ability features (lines, keywords, play/cast/combat) across Commander-legal cards: 113346
- Automated: 80410 (70.9%) · unrecognized clauses: 32936
- Oracle text classified (automated, or sorted into a concrete missing capability): 97.4% · unclassified clauses: 2936
- Distinct missing-capability clusters: 8874

## Missing capabilities by category

| Category | Cards affected | Clauses |
|---|---|---|
| MISSING EFFECT | 11401 | 13442 |
| MISSING SELECTOR | 3600 | 3807 |
| MISSING TRIGGER EVENT | 3465 | 3640 |
| MISSING CONTINUOUS EFFECT | 2815 | 2992 |
| UNSUPPORTED ORACLE PATTERN | 2167 | 2936 |
| MISSING MECHANIC | 1816 | 1878 |
| MISSING REPLACEMENT PATTERN | 1362 | 1401 |
| MISSING RESTRICTION | 944 | 990 |
| MISSING COST / PERMISSION RULE | 935 | 955 |
| MISSING COST | 512 | 526 |
| MANA ABILITY WORDING | 367 | 369 |

## Highest-payoff clusters

Ranked by pod cards, pod commanders, possible commanders affected, cards it alone would unlock, then all Commander cards needing it.

| # | Category | Cluster | Commanders | Only missing piece for | Commander cards | Examples |
|---|---|---|---|---|---|---|
| 1 | MISSING EFFECT | pay {m} … | 65 | 189 | 263 | Labyrinth Adversary, Minion Reflector, Giant's Amulet |
| 2 | MISSING EFFECT | choose n … | 65 | 49 | 561 | Road of Return, Saheeli's Artistry, Eldrazi Confluence |
| 3 | MISSING EFFECT | draw n … | 61 | 208 | 578 | Errand-Rider of Gondor, Krovikan Sorcerer, Heal |
| 4 | MISSING EFFECT | put a ±n/±n counter(s) … | 58 | 146 | 214 | Greta, Sweettooth Scourge, Yorvo, Lord of Garenbrig, Ent-Draught Basin |
| 5 | MISSING MECHANIC | ward | 47 | 11 | 97 | Tyranid Harridan, Grey Host Reinforcements, Kwia Vigorbloom |
| 6 | MISSING EFFECT | look at the top … | 38 | 151 | 211 | Harald, King of Skemfar, Lantern of Revealing, Puresight Merrow |
| 7 | MISSING SELECTOR | target | 35 | 201 | 339 | Cinder Elemental, Archangel of Wrath, Chain of Plasma |
| 8 | MISSING EFFECT | exile the top card … | 33 | 47 | 106 | Moonring Mirror, Professional Face-Breaker, Mezzio Mugger |
| 9 | MISSING CONTINUOUS EFFECT | ~ gets ±N/±N for each … | 32 | 57 | 115 | Nim Lasher, Benalish Honor Guard, Anya, Merciless Angel |
| 10 | MISSING EFFECT | put n … | 28 | 93 | 149 | Black Sun's Zenith, Breaking // Entering, Mind Raker |
| 11 | MISSING CONTINUOUS EFFECT | ~'s power and toughness are each … | 28 | 62 | 127 | Eluge, the Shoreless Sea, Flora Colossus, Revenant |
| 12 | MISSING SELECTOR | target creature card | 26 | 122 | 182 | Hua Tuo, Honored Physician, Puppeteer Clique, Metamorphosis Fanatic |
| 13 | MISSING EFFECT | create n … | 24 | 113 | 202 | Summon the School, Cogwork Assembler, Endless Evil |
| 14 | MISSING EFFECT | if n … | 24 | 60 | 92 | Airdrop Aeronauts, Hot Pursuit, Kotis, Sibsig Champion |
| 15 | MISSING EFFECT | until end of turn … | 23 | 152 | 227 | Divergent Growth, Doorman, Strength of Will |
| 16 | MISSING EFFECT | transform ~ … | 23 | 21 | 65 | Ulvenwald Captive // Ulvenwald Abomination, Westvale Abbey // Ormendahl, Profane Prince, Seraph of New Capenna // Seraph of New Phyrexia |
| 17 | UNSUPPORTED ORACLE PATTERN | As long as your devotion to … | 22 | 5 | 22 | Phenax, God of Deception, Erebos, God of the Dead, Thassa, Deep-Dwelling |
| 18 | UNSUPPORTED ORACLE PATTERN | You may look at the top … | 22 | 2 | 45 | One with the Multiverse, The Lunar Whale, Cemetery Illuminator |
| 19 | MISSING CONTINUOUS EFFECT | During your turn, … | 21 | 38 | 74 | Pompous Gadabout, Long-Lost Lances, Fresh-Faced Recruit |
| 20 | MISSING EFFECT | exile ~ … | 20 | 15 | 63 | Stenn, Paranoid Partisan, Woodland Guidance, Teferi's Protection |
| 21 | UNSUPPORTED ORACLE PATTERN | ~ costs {M} less to cast … | 19 | 36 | 71 | Bedlam Reveler, Gargantuan Leech, Hamza, Guardian of Arashin |
| 22 | MISSING EFFECT | mill n … | 18 | 63 | 102 | Sparring Dummy, Beluna Grandsquall // Seek Thrills, Cache Grab |
| 23 | MISSING TRIGGER EVENT | When you cast ~ | 18 | 27 | 80 | Empyrial Storm, The Fourteenth Doctor, Ulamog, the Ceaseless Hunger |
| 24 | MISSING EFFECT | discard n … | 17 | 45 | 78 | Keldon Raider, Witch's Mark, Seasoned Pyromancer |
| 25 | MISSING EFFECT | ~ deals n … | 16 | 205 | 319 | Deem Worthy, End-Blaze Epiphany, Harvest Pyre |
| 26 | MISSING EFFECT | search your library for … | 16 | 165 | 257 | Safewright Quest, Thunderherd Migration, Squadron Hawk |
| 27 | MISSING EFFECT | if ~ … | 16 | 70 | 126 | Warden of the First Tree, Blinkmoth Urn, Mad Dog |
| 28 | MISSING CONTINUOUS EFFECT | Commander creatures you own have “…” | 16 | 16 | 16 | Dungeon Delver, Noble Heritage, Acolyte of Bahamut |
| 29 | MISSING CONTINUOUS EFFECT | ~'s power is equal to the … | 15 | 29 | 67 | Uurg, Spawn of Turg, Snow Villiers, Nethergoyf |
| 30 | UNSUPPORTED ORACLE PATTERN | As ~ enters, … | 15 | 1 | 19 | Stenn, Paranoid Partisan, Arachne, Psionic Weaver, Pramikon, Sky Rampart |
| 31 | UNSUPPORTED ORACLE PATTERN | More Than Meets the Eye {M} | 15 | 0 | 15 | Optimus Prime, Hero // Optimus Prime, Autobot Leader, Megatron, Tyrant // Megatron, Destructive Force, Jetfire, Ingenious Scientist // Jetfire, Air Guardian |
| 32 | MISSING EFFECT | return ~ … | 14 | 81 | 126 | Summon the School, Dragon Fangs, Haunted Dead |
| 33 | MISSING TRIGGER EVENT | Whenever you cast your second spell each turn | 14 | 22 | 34 | Sunstar Lightsmith, Wanda's Vision, Kraum, Violent Cacophony |
| 34 | MISSING MECHANIC | sneak | 14 | 11 | 27 | Turncoat Kunoichi, Michelangelo, Improviser, Donatello's Technique |
| 35 | MISSING MECHANIC | partner | 14 | 6 | 24 | Lore Weaver, Blaring Captain, Rory Williams |
| 36 | MISSING MECHANIC | firebending | 14 | 5 | 22 | Fire Sages, Loyal Fire Sage, Jeong Jeong, the Deserter |
| 37 | UNSUPPORTED ORACLE PATTERN | • Put a ±N/±N counter(s) on … | 14 | 0 | 38 | Bejeweled Warg, Trusty Retriever, Inspired Inventor |
| 38 | MISSING EFFECT | create a n/n red … | 13 | 23 | 49 | Prosperity Tycoon, Ertha Jo, Frontier Mentor, Nesting Dragon |
| 39 | UNSUPPORTED ORACLE PATTERN | Living metal | 13 | 0 | 13 | Optimus Prime, Hero // Optimus Prime, Autobot Leader, Megatron, Tyrant // Megatron, Destructive Force, Jetfire, Ingenious Scientist // Jetfire, Air Guardian |
| 40 | MISSING EFFECT | create a n/n white … | 12 | 29 | 54 | Empyrial Storm, Drag the Canal, Experimental Synthesizer |
| 41 | MISSING RESTRICTION | ~ can't be blocked by creatures … | 12 | 26 | 56 | Lydia Frye, Pompous Gadabout, Ghost of Ramirez DePietro |
| 42 | MISSING SELECTOR | target equipment | 12 | 17 | 25 | Stolen Uniform, Shagrat, Loot Bearer, Thor, God of Thunder |
| 43 | UNSUPPORTED ORACLE PATTERN | Power-up — {M}: Put N ±N/±N … | 12 | 12 | 19 | Thanos, the Mad Titan, Shang-Chi, Martial Mentor, Hulk, Gamma Goliath |
| 44 | MISSING EFFECT | add {m} … | 11 | 40 | 65 | Akki Rockspeaker, Brightstone Ritual, Infernal Plunge |
| 45 | MISSING EFFECT | exile the top n … | 11 | 20 | 57 | Duplicity, Memorial Vault, Crossover Collaboration |
| 46 | MISSING SELECTOR | target instant or sorcery card | 11 | 20 | 36 | Ogre Battlecaster, Flood of Recollection, Impulsivity |
| 47 | MISSING EFFECT | exile up to n … | 11 | 16 | 27 | Salvation Swan, Liminal Hold, S.H.I.E.L.D. Flying Car |
| 48 | MISSING TRIGGER EVENT | Whenever you cast a historic spell | 11 | 15 | 19 | Serra Disciple, Cabal Paladin, Glóin, Dwarf Emissary |
| 49 | MISSING EFFECT | another target … | 11 | 13 | 23 | Hemosymbic Mite, Syr Faren, the Hengehammer, Pippin, Guard of the Citadel |
| 50 | MISSING COST / PERMISSION RULE | You may cast ~ from your … | 11 | 11 | 27 | Marang River Prowler, Quilled Greatwurm, Gravecrawler |
| 51 | MISSING EFFECT | earthbend n … | 11 | 10 | 27 | Earth Village Ruffians, Bumi, Unleashed, Badgermole |
| 52 | MISSING COST / PERMISSION RULE | Once during each of your turns, … | 11 | 7 | 15 | Kotis, Sibsig Champion, One with the Multiverse, Jacob Hauken, Inspector // Hauken's Insight |
| 53 | MISSING EFFECT | if you've cast a … | 11 | 5 | 12 | H.E.R.B.I.E., Lovable Robot, Invisible Woman, Alicia Masters, Skilled Sculptor |
| 54 | MISSING EFFECT | gain control of target … | 10 | 58 | 85 | Sauron, the Lidless Eye, New Blood, Unwilling Recruit |
| 55 | MISSING SELECTOR | target creature card with mana value | 10 | 26 | 39 | General Leo Cristophe, Yathan Roadwatcher, Lazotep Quarry |
| 56 | MISSING RESTRICTION | ~ can't attack or block unless … | 10 | 16 | 23 | Sab-Sunen, Luxa Embodied, Relic Golem, Hollow Warrior |
| 57 | MISSING EFFECT | return it to the … | 10 | 9 | 22 | Bronzehide Lion, Optimus Prime, Hero // Optimus Prime, Autobot Leader, Yedora, Grave Gardener |
| 58 | MISSING SELECTOR | target creatures | 9 | 105 | 208 | Ravenous Gigantotherium, Fire Covenant, Amazing Acrobatics |
| 59 | MISSING EFFECT | choose target … | 9 | 68 | 82 | Arcbond, Deglamer, Wreck Hunter |
| 60 | MISSING EFFECT | reveal the top n … | 9 | 55 | 74 | Green Sun's Twilight, Benefaction of Rhonas, Karn, Scion of Urza |
| 61 | MISSING EFFECT | reveal the top card … | 9 | 33 | 47 | Counterbalance, Sorin, Grim Nemesis, Sapling of Colfenor |
| 62 | MISSING EFFECT | reveal cards from the … | 9 | 24 | 31 | Treasure Hunt, Hei Bai, Forest Guardian, Hermit Druid |
| 63 | MISSING EFFECT | sacrifice another creature … | 9 | 16 | 25 | Rhovanion Rampager, Brawl-Bash Ogre, Ragefire Hellkite |
| 64 | MISSING EFFECT | double the number of … | 9 | 10 | 21 | Primordial Hydra, The Millennium Calendar, Paradox Zone |
| 65 | MISSING CONTINUOUS EFFECT | You have no maximum hand size | 9 | 7 | 23 | Nyssa of Traken, Curiosity Crafter, Wizard Class |
| 66 | UNSUPPORTED ORACLE PATTERN | Web-slinging {M} | 9 | 4 | 9 | Scarlet Spider, Ben Reilly, Arachne, Psionic Weaver, Spider-Man, Brooklyn Visionary |
| 67 | MISSING CONTINUOUS EFFECT | ~ has indestructible as long as … | 9 | 2 | 12 | Crew Captain, War Historian, Havi, the All-Father |
| 68 | MISSING TRIGGER EVENT | When ~ enters | 9 | 2 | 9 | Niv-Mizzet Reborn, Lobelia Sackville-Baggins, Drizzt Do'Urden |
| 69 | MISSING MECHANIC | companion | 9 | 1 | 9 | Lutri, the Spellchaser, Gyruda, Doom of Depths, Lurrus of the Dream-Den |
| 70 | UNSUPPORTED ORACLE PATTERN | • ~ deals N damage to … | 9 | 0 | 18 | Arbalest Engineers, Tectonic Giant, Umaro, Raging Yeti |
| 71 | UNSUPPORTED ORACLE PATTERN | Storied | 9 | 0 | 9 | Balin, Loremaster, Dáin, Lord of the Iron Hills, Ori, Keeper of Songs |
| 72 | MISSING EFFECT | target creature you control … | 8 | 123 | 176 | Blessed Defiance, Hard-Hitting Question, Crowd of True Believers |
| 73 | MISSING COST | {M}, Discard ~ | 8 | 33 | 57 | Jiwari, the Earth Aflame, Favor of Jukai, Radiant Solar |
| 74 | MISSING EFFECT | create a n/n colorless … | 8 | 29 | 54 | Karn, Scion of Urza, Serpent Generator, Command the Stage |
| 75 | MISSING SELECTOR | target creature defending player controls | 8 | 28 | 34 | Fear of Falling, Impetuous Devils, Fiend Binder |
| 76 | MISSING TRIGGER EVENT | Whenever N creature(s)(s) you control attacks alone | 8 | 19 | 22 | Finest Hour, Black Panther, Claws of Bast, Agents of S.H.I.E.L.D. |
| 77 | MISSING REPLACEMENT PATTERN | ~ enters with a ±N/±N counter(s) on … | 8 | 17 | 37 | Callous Sell-Sword // Burn Together, Avatar of the Resolute, The Duke, Rebel Sentry |
| 78 | MISSING EFFECT | up to n … | 8 | 15 | 33 | Wasp, Shrinking Savior, Restless Vinestalk, Kaito, Dancing Shadow |
| 79 | MISSING EFFECT | discard your hand … | 8 | 14 | 31 | Pyretic Charge, Bedlam Reveler, Balin, Loremaster |
| 80 | MISSING EFFECT | exile it … | 8 | 13 | 23 | Eye of the Storm, Myrkul, Lord of Bones, Brenard, Ginger Sculptor |

## Largest clusters (Commander cards affected)

| # | Category | Cluster | Commander cards | Only missing piece for | Commanders | Examples |
|---|---|---|---|---|---|---|
| 1 | MISSING EFFECT | draw n … | 578 | 208 | 61 | Errand-Rider of Gondor, Krovikan Sorcerer, Heal |
| 2 | MISSING EFFECT | choose n … | 561 | 49 | 65 | Road of Return, Saheeli's Artistry, Eldrazi Confluence |
| 3 | MISSING SELECTOR | target | 339 | 201 | 35 | Cinder Elemental, Archangel of Wrath, Chain of Plasma |
| 4 | MISSING EFFECT | ~ deals n … | 319 | 205 | 16 | Deem Worthy, End-Blaze Epiphany, Harvest Pyre |
| 5 | MISSING COST / PERMISSION RULE | As an additional cost to cast … | 312 | 35 | 6 | Thunderherd Migration, Mind Extraction, Harvest Pyre |
| 6 | MISSING EFFECT | pay {m} … | 263 | 189 | 65 | Labyrinth Adversary, Minion Reflector, Giant's Amulet |
| 7 | MISSING EFFECT | search your library for … | 257 | 165 | 16 | Safewright Quest, Thunderherd Migration, Squadron Hawk |
| 8 | MISSING REPLACEMENT PATTERN | As ~ enters, … | 237 | 47 | 4 | Kindred Discovery, Utopia Sprawl, Game Trail |
| 9 | MISSING EFFECT | until end of turn … | 227 | 152 | 23 | Divergent Growth, Doorman, Strength of Will |
| 10 | MISSING EFFECT | destroy target … | 222 | 138 | 4 | Kalitas, Bloodchief of Ghet, Misfortune's Gain, Raze |
| 11 | MISSING EFFECT | put a ±n/±n counter(s) … | 214 | 146 | 58 | Greta, Sweettooth Scourge, Yorvo, Lord of Garenbrig, Ent-Draught Basin |
| 12 | MISSING EFFECT | look at the top … | 211 | 151 | 38 | Harald, King of Skemfar, Lantern of Revealing, Puresight Merrow |
| 13 | MISSING SELECTOR | target creatures | 208 | 105 | 9 | Ravenous Gigantotherium, Fire Covenant, Amazing Acrobatics |
| 14 | MISSING EFFECT | create n … | 202 | 113 | 24 | Summon the School, Cogwork Assembler, Endless Evil |
| 15 | MISSING SELECTOR | target creature card | 182 | 122 | 26 | Hua Tuo, Honored Physician, Puppeteer Clique, Metamorphosis Fanatic |
| 16 | MISSING EFFECT | target creature you control … | 176 | 123 | 8 | Blessed Defiance, Hard-Hitting Question, Crowd of True Believers |
| 17 | MISSING EFFECT | target creature gets ±n/±n … | 169 | 100 | 3 | Stern Marshal, Spontaneous Flight, Rig for War |
| 18 | MISSING EFFECT | put n … | 149 | 93 | 28 | Black Sun's Zenith, Breaking // Entering, Mind Raker |
| 19 | MISSING CONTINUOUS EFFECT | ~'s power and toughness are each … | 127 | 62 | 28 | Eluge, the Shoreless Sea, Flora Colossus, Revenant |
| 20 | MISSING EFFECT | if ~ … | 126 | 70 | 16 | Warden of the First Tree, Blinkmoth Urn, Mad Dog |
| 21 | MISSING EFFECT | return ~ … | 126 | 81 | 14 | Summon the School, Dragon Fangs, Haunted Dead |
| 22 | MISSING EFFECT | exile target … | 117 | 79 | 5 | Astarion's Thirst, Deadly Rollick, Tawnos's Coffin |
| 23 | MISSING CONTINUOUS EFFECT | ~ gets ±N/±N for each … | 115 | 57 | 32 | Nim Lasher, Benalish Honor Guard, Anya, Merciless Angel |
| 24 | MISSING SELECTOR | target player or planeswalker | 110 | 76 | 5 | Goblin Barrage, Scorching Missile, Consuming Sinkhole |
| 25 | MANA ABILITY WORDING | {M}, … | 108 | 76 | 6 | Saltcrusted Steppe, Cabal Stronghold, Interplanar Beacon |
| 26 | MISSING EFFECT | exile the top card … | 106 | 47 | 33 | Moonring Mirror, Professional Face-Breaker, Mezzio Mugger |
| 27 | MISSING EFFECT | mill n … | 102 | 63 | 18 | Sparring Dummy, Beluna Grandsquall // Seek Thrills, Cache Grab |
| 28 | MISSING CONTINUOUS EFFECT | ~ gets ±N/±N as long as … | 98 | 90 | 1 | Sulam Djinn, Zanam Djinn, Isleback Spawn |
| 29 | MISSING MECHANIC | ward | 97 | 11 | 47 | Tyranid Harridan, Grey Host Reinforcements, Kwia Vigorbloom |
| 30 | MISSING EFFECT | if n … | 92 | 60 | 24 | Airdrop Aeronauts, Hot Pursuit, Kotis, Sibsig Champion |
| 31 | MISSING EFFECT | you gain n … | 89 | 62 | 7 | Shu Farmer, Essence Pulse, Smitten Swordmaster // Curry Favor |
| 32 | MISSING EFFECT | gain control of target … | 85 | 58 | 10 | Sauron, the Lidless Eye, New Blood, Unwilling Recruit |
| 33 | MISSING EFFECT | choose target … | 82 | 68 | 9 | Arcbond, Deglamer, Wreck Hunter |
| 34 | MISSING TRIGGER EVENT | When you cast ~ | 80 | 27 | 18 | Empyrial Storm, The Fourteenth Doctor, Ulamog, the Ceaseless Hunger |
| 35 | MISSING SELECTOR | target opponent reveals their hand | 79 | 53 | 1 | Gix's Caress, Mindclaw Shaman, Grief |
| 36 | MISSING EFFECT | discard n … | 78 | 45 | 17 | Keldon Raider, Witch's Mark, Seasoned Pyromancer |
| 37 | MISSING EFFECT | tap target … | 76 | 45 | 4 | Spider-Woman, Secret Agent, Guardian of Tazeem, Gilded Scuttler |
| 38 | MISSING SELECTOR | target card | 75 | 42 | 3 | Funeral Pyre, Barkform Harvester, Carrion Locust |
| 39 | MISSING CONTINUOUS EFFECT | During your turn, … | 74 | 38 | 21 | Pompous Gadabout, Long-Lost Lances, Fresh-Faced Recruit |
| 40 | MISSING EFFECT | reveal the top n … | 74 | 55 | 9 | Green Sun's Twilight, Benefaction of Rhonas, Karn, Scion of Urza |
| 41 | MISSING EFFECT | if there are n … | 74 | 30 | 6 | Locked in the Cemetery, Sanguine Spy, Extricator of Sin // Extricator of Flesh |
| 42 | MISSING EFFECT | return target … | 74 | 45 | 1 | Surging Aether, Perilous Voyage, Geistwave |
| 43 | MISSING EFFECT | it deals n … | 72 | 58 | 3 | Goblin Chainwhirler, Festering Evil, Unsparing Boltcaster |
| 44 | UNSUPPORTED ORACLE PATTERN | ~ costs {M} less to cast … | 71 | 36 | 19 | Bedlam Reveler, Gargantuan Leech, Hamza, Guardian of Arashin |
| 45 | MISSING EFFECT | create a n/n green … | 70 | 34 | 7 | Rhonas's Last Stand, Kasmina, Enigma Sage, Fractal Harness |
| 46 | MISSING CONTINUOUS EFFECT | ~'s power is equal to the … | 67 | 29 | 15 | Uurg, Spawn of Turg, Snow Villiers, Nethergoyf |
| 47 | MISSING EFFECT | if you control n … | 66 | 41 | 7 | Dawnhart Wardens, Boundary Lands Ranger, Dispatch |
| 48 | MISSING EFFECT | transform ~ … | 65 | 21 | 23 | Ulvenwald Captive // Ulvenwald Abomination, Westvale Abbey // Ormendahl, Profane Prince, Seraph of New Capenna // Seraph of New Phyrexia |
| 49 | MISSING EFFECT | add {m} … | 65 | 40 | 11 | Akki Rockspeaker, Brightstone Ritual, Infernal Plunge |
| 50 | MANA ABILITY WORDING | {M}: Add N mana of any … | 65 | 36 | 2 | Flywheel Racer, Pit of Offerings, Helga, Skittish Seer |

## Top Commander features to implement next

Ranked by pod cards, pod commanders, cards for which it is the only missing piece, then Commander cards needing it.

| # | Feature | Kind | Pod cards | Commander cards | Only missing piece for | Examples |
|---|---|---|---|---|---|---|
| 1 | mana:ability | engine | 0 | 367 | 238 | Saltcrusted Steppe, Flywheel Racer, The Emperor of Palamecia // The Lord Master of Hell |
| 2 | template:Enchanted creature has “…” | continuous | 0 | 28 | 23 | Ghostly Touch, Mark of Sakiko, Unquenchable Fury |
| 3 | template:Enchanted creature gets ±N/±N and has “…” | continuous | 0 | 25 | 20 | Arcane Teachings, Lunarch Mantle, Deviant Glee |
| 4 | template:Commander creatures you own have “…” | continuous | 0 | 20 | 20 | Dungeon Delver, Scion of Halaster, Noble Heritage |
| 5 | template:~ enters prepared. | static | 0 | 40 | 19 | Adventurous Eater // Have a Bite, Maelstrom Artisan // Rocket Volley, Fatehold Chronologist // Peer Review |
| 6 | keyword:banding | keyword | 0 | 24 | 19 | Nalathni Dragon, Mishra's War Machine, Kjeldoran Escort |
| 7 | keyword:foretell | keyword | 0 | 51 | 18 | The Foretold Soldier, Rise of the Dread Marn, Green Slime |
| 8 | keyword:bestow | keyword | 0 | 42 | 18 | Leafcrown Dryad, Baleful Eidolon, Observant Alseid |
| 9 | keyword:splice | keyword | 0 | 30 | 16 | Evermind, Horobi's Whisper, Desperate Ritual |
| 10 | template:Equipped creature has “…” | continuous | 0 | 24 | 16 | Field-Tested Frying Pan, Sorcerer's Wand, Fishing Pole |
| 11 | keyword:enchant | keyword | 0 | 67 | 15 | Utopia Sprawl, One with the Stars, Corrupted Roots |
| 12 | template:Equipped creature gets ±N/±N and has “…” | continuous | 0 | 25 | 15 | Giant's Amulet, Iconic Shield, Candlestick |
| 13 | template:Modular N | static | 0 | 23 | 15 | Arcbound Whelp, Arcbound Javelineer, Arcbound Hybrid |
| 14 | keyword:equip | keyword | 0 | 49 | 14 | Bloodthorn Flail, Strong Back, Team Pennant |
| 15 | keyword:warp | keyword | 0 | 31 | 14 | Starbreach Whale, Knight Luminary, Loading Zone |
| 16 | keyword:encore | keyword | 0 | 26 | 14 | Impulsivity, Sliver Gravemother, Belonging |
| 17 | template:{M}: Return ~ from your graveyard to your hand. | activated | 0 | 22 | 14 | The Sound of Drums, Merchant of Many Hats, Convenient Target |
| 18 | template:~ can't be blocked by creatures with power N or less. | restriction | 0 | 32 | 13 | Glinting Creeper, Dread Linnorm // Scale Deflection, Chomping Kavu |
| 19 | keyword:backup | keyword | 0 | 25 | 13 | Saiba Cryptomancer, Chomping Kavu, Consuming Aetherborn |
| 20 | template:−N: You get an emblem with “…” | loyalty | 0 | 64 | 12 | Zariel, Archduke of Avernus, Elspeth, Sun's Champion, Teferi, Temporal Archmage |
| 21 | template:When ~ enters, attach it to target creature you control. | triggered | 0 | 30 | 12 | Maul of the Skyclaves, Meltstrider's Gear, Bramble Armor |
| 22 | keyword:overload | keyword | 0 | 27 | 12 | Mizzium Skin, Corporeal Projection, Mind Rake |
| 23 | keyword:myriad | keyword | 0 | 23 | 12 | The Master, Multiplied, Sumala Rumblers, Conclave Evangelist |
| 24 | template:When ~ enters, you may discard N card(s). If you do, draw N card(s). | triggered | 0 | 15 | 12 | Keldon Raider, Bitter Reunion, Viashino Racketeer |
| 25 | template:All Slivers have “…” | continuous | 0 | 12 | 12 | Magma Sliver, Basal Sliver, Mesmeric Sliver |
| 26 | keyword:ward | keyword | 0 | 97 | 11 | Tyranid Harridan, Grey Host Reinforcements, Kwia Vigorbloom |
| 27 | keyword:ninjutsu | keyword | 0 | 35 | 11 | Higure, the Still Wind, Moonblade Shinobi, Mist-Syndicate Naga |
| 28 | keyword:sneak | keyword | 0 | 27 | 11 | Turncoat Kunoichi, Michelangelo, Improviser, Donatello's Technique |
| 29 | keyword:unleash | keyword | 0 | 15 | 11 | Rakdos Drake, Grim Roustabout, Chaos Imps |
| 30 | keyword:disguise | keyword | 0 | 43 | 10 | Boltbender, Nightdrinker Moroii, Concealed Weapon |
| 31 | keyword:entwine | keyword | 0 | 32 | 10 | Road of Return, Rain of Rust, Blinding Beam |
| 32 | keyword:offspring | keyword | 0 | 20 | 10 | Splash Lasher, Rust-Shield Rampager, Prosperous Bandit |
| 33 | keyword:mentor | keyword | 0 | 19 | 10 | Hammer Dropper, Legion Warboss, Tributary Instructor |
| 34 | keyword:retrace | keyword | 0 | 17 | 10 | Flame Jab, Monstrify, Waves of Aggression |
| 35 | template:Scavenge {M} | static | 0 | 14 | 10 | Terrus Wurm, Deadbridge Goliath, Dodgy Jalopy |
| 36 | keyword:rampage | keyword | 0 | 12 | 10 | Craw Giant, Balduvian War-Makers, Varchild's War-Riders |
| 37 | template:Threshold — ~ gets ±N/±N as long as there are N or more cards in your graveyard. | continuous | 0 | 12 | 10 | Krosan Beast, Nimble Mongoose, Anurid Barkripper |
| 38 | template:{M}, Sacrifice ~: It deals N damage to any target. | activated | 0 | 12 | 10 | Fireforger's Puzzleknot, Lightning Spear, Pyrite Spellbomb |
| 39 | template:Enchanted land has “…” | continuous | 0 | 11 | 10 | Chamber of Manipulation, Discreet Retreat, Farmstead |
| 40 | template:~ enters tapped unless you control N or fewer other lands. | replacement | 0 | 11 | 10 | Concealed Courtyard, Inspiring Vantage, Blackcleave Cliffs |
| 41 | template:~ enters tapped unless a player has N or less life. | replacement | 0 | 10 | 10 | Abandoned Campground, Raucous Carnival, Strangled Cemetery |
| 42 | template:~ enters tapped unless you control N or more basic lands. | replacement | 0 | 10 | 10 | Sodden Verdure, Smoldering Marsh, Vernal Fen |
| 43 | template:~ enters tapped unless you control N or more other lands. | replacement | 0 | 10 | 10 | Rockfall Vale, Stormcarved Coast, Sundown Pass |
| 44 | template:~ enters tapped unless you control a planeswalker. | replacement | 0 | 10 | 10 | Theorix Annex, Stingerquill Annex, Konstrari Annex |
| 45 | template:~ enters tapped unless you have N or more opponents. | replacement | 0 | 10 | 10 | Spire Garden, Sea of Clouds, Bountiful Promenade |
| 46 | keyword:cumulative upkeep | keyword | 0 | 23 | 9 | Varchild's War-Riders, Aboroth, Inner Sanctum |
| 47 | template:When ~ is put into a graveyard from the battlefield, return it to its owner's hand. | triggered | 0 | 20 | 9 | Spine of Ish Sah, Slow Motion, Fiery Mantle |
| 48 | keyword:living weapon | keyword | 0 | 19 | 9 | Nettlecyst, Lashwrithe, Skinwing |
| 49 | keyword:prototype | keyword | 0 | 19 | 9 | Goring Warplow, Combat Thresher, Woodcaller Automaton |
| 50 | keyword:extort | keyword | 0 | 17 | 9 | Syndicate Heavy, Tithe Drinker, Kingpin's Pet |
| 51 | keyword:fading | keyword | 0 | 17 | 9 | Parallax Wave, Phyrexian Prowler, Skyshroud Ridgeback |
| 52 | template:During your turn, ~ has first strike. | continuous | 0 | 17 | 9 | Fresh-Faced Recruit, Duelist of Deep Faith, Null Group Biological Assets |
| 53 | template:Prevent all combat damage that would be dealt this turn. | prevention | 0 | 14 | 9 | Jaheira's Respite, Fog, Darkness |
| 54 | template:{M}, {M}, Sacrifice ~: It deals N damage to target creature. | activated | 0 | 11 | 9 | Vial of Dragonfire, Flamecast Wheel, Mouth of Ronom |
| 55 | keyword:plot | keyword | 0 | 33 | 8 | Unscrupulous Contractor, Pyretic Charge, Freestrider Commando |
| 56 | template:You control enchanted creature. | static | 0 | 28 | 8 | Spirit Away, Illusory Gains, Biting Tether |
| 57 | keyword:evolve | keyword | 0 | 22 | 8 | Adaptive Snapjaw, Shambleshark, Tyranid Prime |
| 58 | keyword:vanishing | keyword | 0 | 20 | 8 | Soultether Golem, Deadly Grub, Reality Acid |
| 59 | template:~'s power and toughness are each equal to the number of lands you control. | characteristic_defining | 0 | 17 | 8 | Flora Colossus, Rubblehulk, Harmonious Grovestrider |
| 60 | keyword:blitz | keyword | 0 | 16 | 8 | Mezzio Mugger, Workshop Warchief, Riveteers Decoy |

## Coverage by card type

| Type | FULL | PARTIAL | REVIEW | MANUAL |
|---|---|---|---|---|
| Creature | 5654 | 12267 | 0 | 0 |
| Artifact | 886 | 2707 | 0 | 0 |
| Enchantment | 627 | 3020 | 0 | 0 |
| Sorcery | 826 | 2742 | 0 | 0 |
| Instant | 1070 | 2684 | 0 | 0 |
| Land | 521 | 691 | 0 | 0 |
| Planeswalker | 10 | 301 | 0 | 0 |
| Battle | 0 | 36 | 0 | 0 |

## Rules features in the pool (ability lines)

triggered 14909, keyword 14134, spell_effect 9120, activated 7358, continuous 4014, static 3053, mana_ability 2038, replacement 1966, restriction 1474, loyalty 882, prevention 320, additional_cost 307, cost_modifier 261, characteristic_defining 247, permission 207, alternative_cost 180

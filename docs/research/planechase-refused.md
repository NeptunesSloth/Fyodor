# Planechase: refused lines (one line each: card — line — reason)

- New Player's Journey (punk) — chaos: "you gain life equal to the number of years you've played Magic" — a fact outside the game; no rules object to read (wave B).
- Artist Alley (punk) — chaos: "An opponent or player outside the game chooses a nonland card with their favorite art" — a person outside the game and a taste judgment (wave B).
- Clamilton Estate (punk) — chaos: "until you exile a wordy nonland card" — "wordy" has no rules definition (wave B).
- Windmill Farm (punk) — chaos: "Spin this plane until the arrow lands on a permanent … rotated at least 360 degrees" — a physical dexterity action (wave B).
- Shrinking Plane (punk) — chaos: "Completely unfold this plane" — a physical card manipulation with no rules meaning (wave B).
- Mojave Desert (punk) — chaos: "lands that player controls" — "that player" has no antecedent in the ability; the count is undefined (wave B).
- Sorin's Remastered Manor (punk) — chaos: "target spooky creature … bites" — "spooky" has no rules definition (wave B).
- Elvish Impersonation Contest (punk) — chaos: "target Elvish Impersonators becomes a 6/6" — a playtest joke target (no layer/duration given) (wave B).
- Pin Collector's Booth (punk) — chaos: "the total number of pins attached to you and creatures you control" — physical pins, not game objects (wave B).
- The Pro Tour (punk) — chaos: "differently named Standard-legal cards" — format legality is outside the game (wave B).
- Multiversal High Council (punk) — chaos: "for each universe … from that Universe" — "universe" has no rules definition (wave B).

## Statics (wave A: app/rules/planar_statics.py)

- Talon Gates — "Any time you could cast a sorcery, you may exile a nonland card from your hand with X time counters on it …" — a suspend-like special action granting suspend (702.62); one card (wave A).
- The Command Zone — "If an ability of your commander would trigger during your turn, that ability triggers an additional time." — commander-only, turn-limited trigger doubling: unsettled with trigger_multipliers' rulings (wave A).
- Deceptive Divination — "Change the text of each sorcery spell and sorcery card not on the stack …" — text-changing effects (612) have no grammar (wave A).
- Windriddle Palaces — "You may play lands and cast spells from the top of any player's library." — a play permission over other players' libraries; one card (its reveal line is read, wave A).
- Stroopwafel Cafe (punk) — statics: "may play cards from the top of their library" / "The top card of each player's library is a Food artifact" — characteristics given to a hidden library card; no grammar or settled meaning (wave A).
- Finally! Left-Handed Magic Cards (punk) — statics: base power/toughness equal to printed toughness/power — a swap from printed values, no layer-7b grammar for it; one card (wave A).
- Imaginary Friends (Plane) (punk) — static: "cast spells as though they were other cards legal in this game's format" — refers to cards outside the game (wave A).
- Mad Labs (punk) — static: "a copy of a [permanent] … [number] +1/+1 counters" — bracketed placeholders, no rules meaning (wave A).
- Multiversal High Council (punk) — statics: "Universes Beyond spells" / "each different Universe" — "Universe" has no rules definition (wave A).
- Two Streams Facility (punk) — statics: "players who last chose green anchor / red waterfall" — the choice it reads is not defined by the card's other lines in rules terms (wave A).
- The Food Court (punk) — static: "Artifacts are Foods in addition to their other types" (no period: a playtest text) — not read; refused until printed Oracle wording settles (wave A).
- Clamilton Estate (punk) — replacement: "If a wordy permanent entering …" — "wordy" has no rules definition (wave A).
- Year-End Review (punk) — planar rule: each player chooses among creatures in several zones … — undefined outcome of the comparison; no grammar (wave A).
- No Way Out (punk) — "You can never leave — If a player would planeswalk while this plane has dread counters, chaos ensues instead." — a planeswalk replacement (701.31) with no grammar; its other lines need grammar too (wave A).

## Planeswalk to / away / encounter (wave C: app/rules/planar_walk.py)

- Royal Booster (punk) — encounter: "open a Magic: The Gathering booster pack … Those cards become the booster deck" — product outside the game (wave C).
- Unknown Event (punk) — encounter: "Each player opens a Magic the Gathering booster pack" — product outside the game (wave C).
- Pin Trading (punk) — encounter: "draw a card for each pin you are wearing" — physical pins, not game objects (wave C).
- Mad Labs (punk) — encounter: players choose words that fill "[permanent]" / "[number]" placeholders, then "reveal and resolve the following ability with those words" — text built at the table, no rules meaning (wave C).
- The Pro Tour (punk) — "Draft—When you planeswalk here, each player opens a booster pack, drafts a card …" — product outside the game (wave C).
- Shrinking Plane (punk) — "fold this plane in half … the number of times it's been folded" — physical card manipulation (wave C).
- High and Dry Black Market (punk) — "chooses up to 5 ♦ worth of modes" — "♦ worth" has no rules definition (wave C).
- Black Lotus Lounge (punk) — "create a Black Lotus artifact token" — no such predefined token (111.10) and no definition on the card (wave C).
- Ghirapur Grand Prix (punk) — "all players start their engines!" / "the highest speed among players" — start your engines! is a keyword of a permanent (702.179), not an instruction; no rules meaning for players starting it (wave C).
- Furnace Layer (opca) — "select target player at random" — a target chosen at random (601.2c / 115) with no settled engine procedure (who chooses, illegal targets re-rolled?); refused until a ruling settles it (wave C).

## Wave E1 (app/rules/planar_more.py)

Promoted from the lists above (each with a test in tests/test_rules_planechase_more.py): Horizon Boughs, Edge of Malacol, Naya, Lake Silencio,
Naktamun, Sea of Sand, Prahv, TARDIS Bay, The Doctor's Tomb, Skybreen (line 2), Singing Towers of Darillium (line 1; its chaos line is wave E2's),
Amy's Home, Enigma Ridges, Unyaro, We Hope You Like Squirrels. Bowie Base One's "the player to your left" now reads the seats (``Plan.left``, 103.1),
not the turn order.

- Event Horizon (punk) — "Nonbasic lands are Wastes." — Wastes is a card name, not a land type (205.3i lists the basic land types; Wastes has none), and no ruling exists (Scryfall lists none for the card): whether the lands lose their types/abilities, gain {T}: Add {C}, or change name has no settled meaning (wave E1).
- Omenpath Instability (punk) — "an Entropy enchantment token … an Omenpath enchantment token" — "Entropy" and "Omenpath" are not enchantment subtypes (205.3h) and no name is given, so the tokens' characteristics (111.4) are undefined; the token abilities themselves parse ("Chaos ensues", "Planeswalk") (wave E1).
- Circus of the Sun (punk) — "Whenever one or more creatures you control with flying deal combat damage to a player, you may return it to your hand. If you do, draw cards equal to its power." — "it" has no single antecedent in a "one or more" batch trigger (603.2c) (wave E1).


## Wave E2 (app/rules/planar_events.py, app/rules/planar_chaos.py)

Promoted (each with a test in tests/test_rules_planechase_events.py): Goldmeadow, The Dark Barony, Mirrored Depths, Ten Wizards Mountain,
The Drum, Mining Facility, Pompeii (planar die roll / blank events), Valor's Reach (102.4: "your team" is "you"), Izzet Steam Maze, Mondassian
Colony Ship, Stensia, Gardens of Tranquil Repose, Ketria, Bad Wolf Bay, The Dining Car, Nyx, Hotel of Fears, City of the Daleks, Jund,
Li'l Giri Saves the Day; chaos lines of Glimmervoid Basin, Grand Ossuary, The Food Court and Stroopwafel Cafe ("Chaos: …" read as a chaos
ability). Judgement calls: a blank roll that Chaotic Aether makes a chaos roll is no blank roll for Pompeii (Chaotic Aether's text: it "is a
{CHAOS} roll"); Hotel of Fears' "sacrifice another creature" is another than the target creature (the plane is no creature).

- Grand Ossuary (opca) — "its controller distributes … among any number of target creatures they control" — who chooses the targets and the
  division (the ability's controller, the planar controller, 601.2c-d / 603.3d, or the dead creature's controller, as the wording says) is
  not settled offline (no ruling at hand); refused until a ruling settles it (wave E2).
- Event Horizon (punk) — its chaos modes: the Oracle splitter already keeps "choose one —" and its bullets as one modal ability
  (modal_abilities); the third mode "You may return …" is refused because modal abilities don't read a "you may" mode (wave E2).
- Bicycle Rack (punk) — "Chaos: … have "This creature gets +1/+1 for each card you've discarded this turn."" — the matcher reads "Chaos:"
  now; the quoted per-creature discard count has no grammar (wave E2).
- Shrinking Plane (punk) — "Completely unfold this plane" — undefined action (wave E2).

Not done in wave E2 (open): Kharasha Foothills ("for each other opponent, you may create … tapped and attacking that opponent"), Ood Sphere
(convoke grant; "can't become tapped unless they're being declared as attackers" has no rule), The Doctor's Childhood Barn (phase out, can't
phase in while face up), The Moonbase (per-opponent graveyard targets put face down), Glen Elendra (exchange with a creature of "that player"),
Glimmervoid Basin line 1 (copy for each other legal target of any kind), The Matrix of Time line 3 (cast/play "from among cards exiled with ~"
event), Singing Towers of Darillium chaos line, Two Streams Facility (depends on the green anchor / red waterfall choice record), Deceptive
Divination chaos line ("two target players each search"), the graveyard/spell keyword grants of the "other" family (Grixis unearth, Otaria
flashback, Strixhaven demonstrate, Trail of the Mage-Rings rebound, The Caldaia blitz).

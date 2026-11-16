# Planechase: refused lines (one line each: card — line — reason)

The wave G1 playtest planes ("punk") are listed once each in the wave G1 section at the end (their earlier wave B / A / C / E1 / E2 entries are
merged there). The sections below keep the other planes' entries (No Way Out, Two Streams Facility and the Secret Lair "pssc" planes included).

## Statics (wave A: app/rules/planar_statics.py)

- Deceptive Divination — "Change the text of each sorcery spell and sorcery card not on the stack …" — text-changing effects (612) have no grammar (wave A).
- Finally! Left-Handed Magic Cards (punk) — statics: base power/toughness equal to printed toughness/power — a swap from printed values, no layer-7b grammar for it; one card (wave A).
- Imaginary Friends (Plane) (punk) — static: "cast spells as though they were other cards legal in this game's format" — refers to cards outside the game (wave A).
- Two Streams Facility (punk) — statics: "players who last chose green anchor / red waterfall" — the choice it reads is not defined by the card's other lines in rules terms (wave A).
- No Way Out (punk) — "You can never leave — If a player would planeswalk while this plane has dread counters, chaos ensues instead." — a planeswalk replacement (701.31) with no grammar; its other lines need grammar too (wave A).

## Planeswalk to / away / encounter (wave C: app/rules/planar_walk.py)

(Its entries were all playtest planes: see wave G1.)

## Wave E1 (app/rules/planar_more.py)

Promoted from the lists above (each with a test in tests/test_rules_planechase_more.py): Horizon Boughs, Edge of Malacol, Naya, Lake Silencio,
Naktamun, Sea of Sand, Prahv, TARDIS Bay, The Doctor's Tomb, Skybreen (line 2), Singing Towers of Darillium (line 1; its chaos line is wave E2's),
Amy's Home, Enigma Ridges, Unyaro, We Hope You Like Squirrels. Bowie Base One's "the player to your left" now reads the seats (``Plan.left``, 103.1),
not the turn order.

## Wave E2 (app/rules/planar_events.py, app/rules/planar_chaos.py)

Promoted (each with a test in tests/test_rules_planechase_events.py): Goldmeadow, The Dark Barony, Mirrored Depths, Ten Wizards Mountain,
The Drum, Mining Facility, Pompeii (planar die roll / blank events), Valor's Reach (102.4: "your team" is "you"), Izzet Steam Maze, Mondassian
Colony Ship, Stensia, Gardens of Tranquil Repose, Ketria, Bad Wolf Bay, The Dining Car, Nyx, Hotel of Fears, City of the Daleks, Jund,
Li'l Giri Saves the Day; chaos lines of Glimmervoid Basin, Grand Ossuary, The Food Court and Stroopwafel Cafe ("Chaos: …" read as a chaos
ability). Judgement calls: a blank roll that Chaotic Aether makes a chaos roll is no blank roll for Pompeii (Chaotic Aether's text: it "is a
{CHAOS} roll"); Hotel of Fears' "sacrifice another creature" is another than the target creature (the plane is no creature).

Not done in wave E2 (open): Kharasha Foothills ("for each other opponent, you may create … tapped and attacking that opponent"), Ood Sphere
(convoke grant; "can't become tapped unless they're being declared as attackers" has no rule), The Doctor's Childhood Barn (phase out, can't
phase in while face up), The Moonbase (per-opponent graveyard targets put face down), Glen Elendra (exchange with a creature of "that player"),
Glimmervoid Basin line 1 (copy for each other legal target of any kind), The Matrix of Time line 3 (cast/play "from among cards exiled with ~"
event), Singing Towers of Darillium chaos line, Two Streams Facility (depends on the green anchor / red waterfall choice record), Deceptive
Divination chaos line ("two target players each search"), the graveyard/spell keyword grants of the "other" family (Grixis unearth, Otaria
flashback, Strixhaven demonstrate, Trail of the Mage-Rings rebound, The Caldaia blitz). (Kharasha Foothills, Glen Elendra, Glimmervoid Basin line 1
and those keyword grants: done in wave F1, below.)

## Wave F1 (app/rules/planar_more2.py)

Promoted (each with a test in tests/test_rules_planechase_more2.py): Grixis, Otaria, Strixhaven, Trail of the Mage-Rings, The Caldaia, The Golden City
of Orazca (ascend on a plane: a static, ruling 2023-04-14), Ghirapur, New New York, Talon Gates (the special action, ruling 2012-06-01), Windriddle
Palaces, Glimmervoid Basin, Glen Elendra, Furnace Layer, Grand Ossuary, Kharasha Foothills. Lifted refusals: Talon Gates and Windriddle Palaces (wave A:
"one card" only — now one-card handling), Furnace Layer (wave C: settled by the Scab-Clan Giant ruling 2013-04-15 — the table picks among the legal
targets as the ability goes on the stack — and Furnace Layer's 2012-06-01 ruling — you can be selected), Grand Ossuary (wave E2: settled by its
2012-06-01 ruling — "You choose the number of target creatures and declare how you are distributing the counters as you put the first ability on the
stack": the ability's controller, 601.2c-d; the creatures are the dead creature's controller's).

## Wave F2 (app/rules/planar_more3.py; tests/test_rules_planechase_more3.py)

Promoted: Caught in a Parallel Universe, Human—Time Lord Meta-Crisis, Morphic Tide (Warp World's procedure with planeswalkers, ruling
2012-06-01), The Moonbase, The Doctor's Childhood Barn (ruling 2023-10-13: no phase-in while it is face up; the planeswalk's delayed trigger),
Ood Sphere (convoke for every player's noncreature spells; Red-Eye: ruling 2023-10-13 — not tapped by effects or for costs), Singing Towers of
Darillium (chaos), Two Streams Facility, The Matrix of Time (line 3: the cast / land play of a card linked to the plane, 607.2a), Math is for
Blockers (Plane), sAnS mERcY (its case is flavor; plane types now read in any case). Lifted refusal: Two Streams Facility (wave A) — the
choice is defined by its first ability (each player's last choice, recorded for the plane object).

Refused (exact reasons):
- Finally! Left-Handed Magic Cards (pssc) — "base power is equal to its printed toughness" / "base toughness is equal to its printed power" —
  undefined for most of the creatures it applies to: a token has no printed values (111.4), a noncreature permanent that became a creature
  (an animated land, a crewed Vehicle's own P/T aside) has none, a face-down creature's printed values are hidden (708.2, 708.10), and a printed
  "*" is a characteristic-defining ability, not a number (604.3); and "draw a card from the bottom of your library" has no rule (121.1: a draw
  takes the top card; no ruling).
- Imaginary Friends (Plane) (pssc) — "Players may cast spells as though they were other cards legal in this game's format with the same type
  and mana cost" — no rule says what a spell cast "as though it were another card" is (601.3 lets a permission change when / from where a
  spell is cast, not what object it is), and "cards legal in this game's format" is the whole card pool outside the game; the chaos line casts
  "only as another card following this plane's first ability", so it falls with it.
- No Way Out (punk) — "No Way Out enters with three dread counters." — a plane never enters (it is turned face up in the command zone,
  701.31b / 901; "enters" is the battlefield's, 603.6a / 614.1c), so by the rules it never has dread counters and "You can never leave"
  never applies; the intended reading (counters as it is turned face up) is not in the text and no ruling exists ("Whenever Chaos ensures"
  is a playtest typo too).

Not done in wave F2 (defined, open): Deceptive Divination (612.1-2 define it, but the engine's text changes reach only the battlefield and the
stack, and a card-type word changed in the type line of cards in hands, libraries, graveyards and exile — "each sorcery … card not on the stack"
— has no layer-3 support there), Happy Yargle Day! ("It becomes a copy of Yargle, Glutton of Urborg" — a copy of a card outside the game
(Garth One-Eye's copy recipe exists only for "create a copy"), and the chaos line's random choice among five named cards, copied and cast).
(Both done in wave G2: app/rules/planar_more4.py.)

## Wave G1 — the playtest planes (app/rules/planar_playtest.py; tests/test_rules_planechase_playtest.py)

Promoted to FULL: Shy Town, Jalira's Show (the reflexive "When you do" only after a creature was destroyed, 603.12), Pursued by Something
("cast it" is mandatory), The Bean, Tarnation, Raiders' Allegiance (point counters are player counters, 122.1; all tied at 0 when nobody has
one), Bicycle Rack (lifted: the quoted static is granted until end of turn), City Hall, The Windy City (an alternative cost of {2} for the
owner, 118.9, the permission following the exiled object, 400.7h). Lines read on cards that stay PARTIAL: Welcome to Valley (chaos), Sorin's
Remastered Manor (line 1: "at the beginning your upkeep", sic), Circus of the Sun (line 1: "or" — the same two trigger events, 603.2), Black Lotus
Lounge (chaos), Game Knights Live (chaos), Mojave Desert (line 1, with its Snake), The Command Zone (lines 1 and 3: the commander tax back to 0,
903.8), Ghirapur Grand Prix (line 3: 702.179f — no speed counts as 0). Reminder text has no rules meaning (207.2a): a term defined only there
stays undefined.

Refused (one entry per card; the lines not named here are read, or listed as open below):
- Artist Alley — chaos: "An opponent or player outside the game chooses a nonland card with their favorite art" — the chooser may be a person
  outside the game (no player, 102.1) and the criterion is a taste; "Then you may cast that spell" hangs on that choice.
- Black Lotus Lounge — line 1: "create a Black Lotus artifact token" — no such predefined token (111.10) and no characteristics given ("Black
  Lotus" is no artifact type, 205.3g; 111.4).
- Circus of the Sun — line 2: "Whenever one or more creatures you control with flying deal combat damage to a player, you may return it …" —
  "it" has no single antecedent in a "one or more" batch trigger (603.2c).
- Clamilton Estate — both lines: "wordy" has no rules definition (its definition, "four or more lines of rules text", is reminder text, 207.2a).
- Elvish Impersonation Contest — line 1: "create an Elvish Impersonators token" — no predefined token (111.10): its characteristics are only in
  reminder text (207.2a); line 2: "target Elvish Impersonators becomes a 6/6" — a card name used as a target kind, falling with line 1.
- Event Horizon — line 1: "Nonbasic lands are Wastes." — Wastes is a card name, not a land type (205.3i), and no ruling exists: whether the
  lands lose their types/abilities, gain {T}: Add {C}, or change name has no settled meaning.
- Ghirapur Grand Prix — line 1: "all players start their engines!" — start your engines! is a static keyword of a permanent (702.179a), not an
  instruction; "it starts at 1" is reminder text (207.2a).
- High Noon At Thunder Junction — line 1: "any of their opponents may say "DRAW!". The first opponent to do so clashes with that player" — a
  real-time race to speak first; no rule orders it (101.4 orders simultaneous choices, not who is "first"), and the clash and the tokens hang on it.
- High and Dry Black Market — all lines: "up to 5 ♦ worth of modes" / "♦ — …" — ♦ has no rules definition (700.2h defines pawprint modes only).
- Mad Labs — both lines: players choose words that fill "[permanent]" / "[number]" / "[keyword]" placeholders, then "reveal and resolve the
  following ability with those words" — text built at the table, no rules meaning.
- Mojave Desert — chaos: "lands that player controls" — "that player" has no antecedent in the ability; the count is undefined.
- Multiversal High Council — all lines: "Universes Beyond spells" / "each different Universe" / "for each universe … from that Universe" — a
  product line, not a characteristic (no rules definition).
- New Player's Journey — line 2: "a card from Foundations or a core set (including Alpha!)" — set membership and "core set" are product
  categories outside the rules (the expansion symbol, 206.1, has no rules function); line 3: "the number of years you've played Magic" — a fact
  outside the game ("Then planeswalk" is part of the same ability).
- Omenpath Instability — "an Entropy enchantment token … an Omenpath enchantment token" — "Entropy" and "Omenpath" are not enchantment types
  (205.3h) and no name is given, so the tokens' name and subtypes (111.4) are undefined.
- Pin Collector's Booth — line 1: "create a Pin token … It's an Pin Aura enchantment" — "Pin" is not an enchantment type (205.3h): the token's
  name and subtypes are undefined, as Omenpath's; line 2: "the total number of pins attached to you" — physical pins, not game objects.
- Pin Trading — "draw a card for each pin you are wearing" — physical pins, not game objects.
- Preston's Stage — line 1: "performs a magic trick" / "a Hat token" — no rules definition (both are defined only in reminder text, 207.2a;
  Hat is no artifact type, 205.3g).
- Probability Flux — its only line is a static "Until your next turn, if a player would roll …" with no encounter ability: a phenomenon's
  abilities work only while it is face up and one with no pending trigger leaves at once (312.7, 704.6f), so the effect never applies as
  written; "ignore one" doesn't say which roll or who chooses.
- Royal Booster — "open a Magic: The Gathering booster pack … Those cards become the booster deck" — a product outside the game.
- Shrinking Plane — both lines: "fold this plane in half … the number of times it's been folded" / "Completely unfold this plane" — physical
  card manipulation.
- Sorin's Remastered Manor — lines 2 and 3: "Spooky creatures you control …" / "target spooky creature … bites" — "spooky" has no rules
  definition (its reminder text, "or it could be a horror movie monster", is outside the game).
- Stroopwafel Cafe — line 2: "The top card of each player's library is a Food artifact" — card types given to a hidden library card with no
  "in addition" (whether it keeps its own is unsaid; the reminder's activation from the library has no rule, 207.2a).
- Team-Up! — "each player wins the game if the players to their left and right are eliminated" — "eliminated" is no rules term, and once a
  neighbour leaves the game the seat to that side is the next player (800.4a), so "the players to their left and right" is undefined.
- The Food Court — line 1: "Artifacts are Foods in addition to their other types" — the subtype alone gives no ability (205.3g; Food's ability
  is a predefined token's, 111.10b) but its reminder text says they have it: the text and the reminder disagree, no ruling.
- The Pro Tour — line 1: "each player opens a booster pack, drafts a card …" — a product outside the game; line 2: "differently named
  Standard-legal cards" — format legality is outside the game.
- The Sphere — line 1: "round both its power and toughness up to the nearest 5" — no layer (613.4) or duration for "round": whether it sets
  or modifies them is unsaid; line 2: "Amass Fans 5" — Fan is not a creature type (205.3m), so the Army's subtype (701.47a) is undefined.
- Unknown Event — "Each player opens a Magic the Gathering booster pack" — a product outside the game.
- Welcome to Valley — line 1: "Whenever you cast an animal spell" — "animal" is a real-world category, not a creature type (205.3m).
- Windmill Farm — line 1: "a Tulip Petal artifact token" — "Tulip Petal" is not an artifact type (205.3g): the token's name and subtypes are
  undefined (111.4), as Omenpath's; line 2: "Spin this plane until the arrow lands on a permanent … rotated at least 360 degrees" — physical.
- Year-End Review — "Those cards become promoted to commander" — a commander is chosen before the game starts (903.3); no rule makes a card a
  commander mid-game, and "Then planeswalk away" falls with it.

Not done in wave G1 (defined, open): Event Horizon's chaos modes ("choose one —"; modal_abilities reads neither a planar trigger header nor a
"you may" mode), Game Knights Live line 1 (one ability with two trigger events — casting or attacking with "their commander" — then the
player's choice and a Knight type until a player planeswalks away from it), The Command Zone line 2 (603.2d; the trigger multiplier collector
reads permanents only, and "your commander" includes one in the command zone), The Food Court line 2 (an activated mana ability of the planar
object: no collector activates the face-up plane's abilities; 901.6: the planar controller controls it), Stroopwafel Cafe line 1 (401.5 and a
601.3 permission for every player: the engine's top-of-library permissions are their controller's only).

## Wave G2 — Deceptive Divination, Happy Yargle Day! and robustness (app/rules/planar_more4.py; tests/test_rules_planechase_more4.py)

Done: Deceptive Divination (612.1-2, 613.1c: a layer-3 change in every zone, ``layers._derive`` and the prospective spell, 601.3; nothing is
logged or shown, hidden cards' views carry no characteristics), Happy Yargle Day! (a layer-1 copy of the card database's Yargle with "it isn't
legendary", 707.9b, no duration, 611.2a; the chaos pick from the table's entropy source, recorded on the ``copy_card`` action, then the free
cast of the copy, 707.12). Grammar: a modal ability's mode that opens "You may …" is the mode's own optional instruction (608.2d; ``may_rest``
over that mode's effects only) — Commander FULL unchanged (32086); no Commander card's definitions change (the 16 Commander-legal cards with a
"• You may" mode were already read another way). Event Horizon stays refused for "Nonbasic lands are Wastes." (above); its chaos modes are read
now, but the planar collector (planar.ability_ok) still lists its "mode" lines as unread.

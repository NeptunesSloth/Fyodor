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

- Horizon Boughs — "All permanents untap during each player's untap step." — the only native wording (Seedborn Muse's `untap_other_steps`) is keyed to "each other player" than the source's controller, and the planar controller is the active player (311.5), so a rewrite would untap nothing; new untap-step grammar (502.3) for one card (wave A).
- Edge of Malacol — "If a creature you control would untap during your untap step, put two +1/+1 counters on it instead." — no grammar replaces the untap event (614.1, 502.3); one card (wave A).
- Naya — "You may play any number of lands on each of your turns." — unlimited land plays (305.2) have no grammar (Fastbond's identical line is unread too) (wave A).
- Lake Silencio — "Still Point in Time — All spells have split second." — no grammar grants split second (702.61) to spells on the stack; one card (wave A).
- Naktamun — "Each creature card in your graveyard has embalm. Its embalm cost is equal to its mana cost." — embalm (702.128) is not a zone_grants keyword; widening that grammar for one card was not done (wave A).
- Sea of Sand — "Players reveal each card they draw." — no static reveals draws (701.20); its two draw triggers need grammar too (wave A).
- Event Horizon — "Nonbasic lands are Wastes." — Wastes is a card name, not a land type (205.3i); no settled rules meaning (wave A).
- Prahv — "If you cast a spell this turn, you can't attack with creatures." / "If you attacked with creatures this turn, you can't cast spells." — turn-history attack/cast restrictions with no grammar; one card (wave A).
- TARDIS Bay — "The first spell you cast during each of your turns with mana value 2 or greater has cascade." — a conditional cascade grant to a spell (702.85) has no grammar (wave A).
- Talon Gates — "Any time you could cast a sorcery, you may exile a nonland card from your hand with X time counters on it …" — a suspend-like special action granting suspend (702.62); one card (wave A).
- The Doctor's Tomb — "If a creature would die, instead exile it and that creature's controller loses 2 life." — a die replacement with a rider for another player; no grammar (wave A).
- The Command Zone — "If an ability of your commander would trigger during your turn, that ability triggers an additional time." — commander-only, turn-limited trigger doubling: unsettled with trigger_multipliers' rulings (wave A).
- Deceptive Divination — "Change the text of each sorcery spell and sorcery card not on the stack …" — text-changing effects (612) have no grammar (wave A).
- Skybreen — "Spells that share a card type with the top card of a library can't be cast." — a cast restriction keyed to every library's revealed top card; one card (its reveal line is read, wave A).
- Windriddle Palaces — "You may play lands and cast spells from the top of any player's library." — a play permission over other players' libraries; one card (its reveal line is read, wave A).
- Singing Towers of Darillium — "Each nonland card in your hand without foretell has foretell …" — not claimed: what a card foretold under the plane may do after a planeswalk (the grant gone, 702.143) is untested; the card is PARTIAL on its chaos line anyway (wave A).
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
- Amy's Home (who) — "exile a nonland card from your hand with … time counters … If it doesn't have suspend, it gains suspend" — a suspend grant to an exiled card (702.62) with no grammar; refused as wave A refused Talon Gates (wave C).
- Furnace Layer (opca) — "select target player at random" — a target chosen at random (601.2c / 115) with no settled engine procedure (who chooses, illegal targets re-rolled?); refused until a ruling settles it (wave C).

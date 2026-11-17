# Mystery Booster Commander Edition (mbc): refused cards (one line each: card — reason)

Waves MBC-A/B/C (app/rules/mbc_a.py, mbc_b.py, mbc_c.py; tests/test_rules_mbc_{a,b,c}.py) automated 40 of the 52 Commander-legal cards
that were not FULL (coverage 2026-11-16: FULL 32086 → 32126 of 32138; possible commanders 3521 → 3560 of 3563). The 12 left are below.

## Acorn-stamped cards: not Commander-legal, not automated (10)

The local card data (Scryfall bulk 2026-11-06) still marks these mbc printings "legal". Current Scryfall data gives them the acorn security
stamp and `legalities.commander = "not_legal"`. Acorn cards are not sanctioned (like Unfinity's acorn cards; see
app/rules/commander.py `_inferred_legality`), and several use Alchemy-only mechanics that have no paper rules: conjure, perpetually, and the
"Power Nine" outside the game. The pod plays Commander only, so these are left as they are. A refreshed card database drops them from the
Commander-legal count by itself.

- Oracle of the Alpha: acorn (Arena printing); conjures the Power Nine (digital-only conjure).
- Perforator Crocodile: acorn (Arena printing); conjures Stab Wound onto the battlefield.
- Case of the Lost Witness: acorn (Arena printing); conjures Fblthp, the Lost.
- Pearl Collector: acorn; conjures Mox Pearl; "perpetually gains lifelink" (digital-only).
- Ruby Collector: acorn; conjures Mox Ruby.
- Sapphire Collector: acorn; conjures Mox Sapphire.
- Emerald Collector: acorn; conjures Mox Emerald.
- Jet Collector: acorn; conjures Mox Jet.
- Euru, Acorn Scrounger: acorn; conjures Chitterspitter.
- Overcooked: acorn; conjures Food Fight.

## Oval-stamped (Commander-legal) cards refused (2)

- Miss Highwater: "… For as long as they have a contract counter, when they lose the game, for each artifact and creature they controlled …".
  This needs a delayed trigger that fires when a player loses the game, outlives its source, and then copies objects that left the game with that
  player (800.4a) from last known information. The engine's delayed triggers only watch objects and steps, and its token copies come from
  objects still in the game. The whole paragraph is one ability, so automating only the discard/draw half would leave the card half-done
  without gaining coverage.
- Chira, All In: "Whenever you discard one or more cards at random, select one or more targets at random, choose one or more modes at random,
  flip one or more coins, or roll one or more dice, …". Coin flips and die rolls are events. Random discards, random targets and random modes
  are picked at about 35 separate sampling sites in 24 modules, and they share no event. Wiring up a few of them would silently miss the rest.

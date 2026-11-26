# Mystery Booster Commander Edition (mbc): refused cards (one line each: card — reason)

Waves MBC-A/B/C (app/rules/mbc_a.py, mbc_b.py, mbc_c.py; tests/test_rules_mbc_{a,b,c}.py) automated 40 of the 52 Commander-legal cards
that were not FULL (coverage 2026-11-16: FULL 32086 → 32126 of 32138; possible commanders 3521 → 3560 of 3563). Wave MBC-D
(app/rules/mbc_d.py) automated the last two oval-stamped ones (below). The 10 left are the acorn-stamped cards.

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

## Oval-stamped (Commander-legal) cards: none left

The two oval-stamped cards once refused here are automated since wave MBC-D (app/rules/mbc_d.py; tests/test_rules_mbc_d.py; coverage FULL
32126 → 32128):

- Miss Highwater: a player leaving the game is now one event, emitted where the engine carries out 800.4a (app/rules/leave.py, for a loss by a
  state-based action, by an effect, or a concession), with snapshots of every permanent that player controlled taken before anything left with
  them (app/rules/left_game.py). Delayed triggers can wait for it ("when they lose the game", "for as long as they have a contract counter"),
  outlive their source, and copy those objects from their copiable values as they last existed.
- Chira, All In: every random pick of the rules engine now goes through one helper (app/rules/randomness.py) that draws exactly as before
  and records one `random_choice` event (who made it, which kind: discard, target, mode, coin, die, or another kind no card asks about yet);
  die rolls and coin flips are noted the same way, and so is the planar die (706.7, 901.9d). Shuffles, the table's own dice and coins, and the
  opening picks are left out on purpose (randomness.py says why).

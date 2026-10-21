# Revealed information and later consequences

Batch 34 implements eleven previously partial canonical cards: Trepanation Blade, Goblin Charbelcher, Calibrated Blast, Yuna's Whistle, Cerebral Eruption, Sanity Grinding, Naya Soulbeast, Game Preserve, Impromptu Raid, Thought Dissector, and Candles of Leng.

`reveal_snapshots.py` captures revealed characteristics and quantities before subsequent moves or choices. It reuses the native mandatory reveal adapter, exact-object cleanup, damage, draw, mill, ordered/random placement, reflexive triggers, original-spell entry recipes, simultaneous entry, and delayed sacrifice. No new resolution callback or parallel card engine is introduced.

Calibrated Blast and Yuna's Whistle choose targets for a separate reflexive triggered ability, after the revealed cards have moved; the immutable revealed mana value survives a fresh-process save/resume. No qualifying card means no trigger. Sanity Grinding counts blue symbols, including hybrid, Phyrexian, and split-card mana costs, rather than mana value or blue cards. Cerebral Eruption damages the opponent and their creatures in one native simultaneous group, and a revealed land returns the original spell.

Trepanation Blade uses the original attacking creature and defending player. Charbelcher excludes the revealed land from its count and checks the actual Mountain subtype. Both preserve native damage/pump and private placement. Candles uses the native replaceable draw in its otherwise branch. Thought Dissector stops at X or the first artifact, enters under its controller, and sacrifices the original source even if the found artifact cannot enter.

Game Preserve reveals each live player's top card before one owner-controlled entry batch. Naya's cast trigger places a counter recipe on the original spell object; spell copies do not cast. Raid grants permanent haste to actual arrivals and schedules an exact-object sacrifice at the next end step, rather than extending the grant to failed entries or later incarnations.

Canonical data and official Wizards rulings were reviewed from the local imported database and `/tmp/fyodor-reveal-snapshots34-rulings.json`. Positive native gameplay, replay/privacy, cold choices, and boundary proofs are in `test_rules_reveal_snapshots.py`, with separate cast and entry edge modules. The batch inventory and shared checks are tracked in `docs/CURRENT_STATE.md`; parsing alone is not treated as a completed promotion.

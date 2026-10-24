# Stored player costs66 — root review candidate

Exact two cards: Academy Loremaster and Tax Collector. Native modal selection strips Tax/Arrest labels and uses existing ETB trigger/target semantics. Exact Tax text produces existing opponent-caster stored +1 generic modifier until its controller’s next turn. Arrest reuses native detain unchanged.

Academy’s exact body composes native optional draw binding and guards both draw and tax on accepting. Its +2 generic stored modifier is bound to the actual draw-step player, never the trigger controller; effect expires at end of turn and survives source departure. Native CostModifier records/lifecycle remain unchanged. The recipient bridge is currently emitted only for that exact end-of-turn sentence. Will Kenrith is held separately: its target-player discount lasts until the original controller’s next turn, so rebinding controller would give the wrong expiry and is not used.

Proof: consolidated native9 PASS incl2 fresh subprocess saves at pending native choices; stronger recipient boundary4 PASS (includes a repeated Academy cold) verifies another player casts native Lightning Bolt for R during the taxed player’s same turn. Related37 PASS, scoped mypy3 PASS, configured Ruff3+native test PASS. Whole card proofs include actual Tax cast, actual Bolt source-removal response, tax expiry/own-caster exclusion, actual Arrest target plus mana-ability refusal/expiry, opponent Yes/No extra-draw choice, correct recipient payment and source removal.

No live app or tests installed by this agent. Root reviews the three-file owned patch and runs production/frozen admission before counting promotions.

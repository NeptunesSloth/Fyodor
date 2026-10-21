# Fixed counter alternatives: Sigurd and Plague Boiler

Native resolution-time choices reuse the ordinary put/remove counter effects and existing pick-one continuation. The printed fixed counter kind and native recipient remain in the resolving context. Counter availability and put/remove prohibitions are read when the instruction resolves. A forced single possible instruction executes directly; when neither instruction is possible nothing happens. Choosing removal with no corresponding counter is forbidden (Plague Boiler, official ruling2005-10-01).

The change adds no casting, mana, decision-schema, or engine callbacks. Actual mana payment, counter replacements, source/target object identity, and replay remain native. A blinked successor receives no counters from the old object's ability.

Complete native production checks:22 cases, including3 genuine fresh-process saved-game cases. They exercise both printed cards, both paid counter alternatives, forced branches and impossibilities, actual Solemnity/Doubling Season, resolution-time state changes, boiler upkeep/state/sacrifice/destroy behavior, removal after its state trigger, source departure, and Sigurd's attacking/once-per-turn/new-controller gates, actual vigilance/trample/lifelink and lore-counter trigger. Both complete database canonical cards are FULL against checkpoint49 PARTIAL. Scoped types3 and owned Ruff pass.

Related counter/Saga/boast/parser suites:120 pass, with one existing stale Asmodeus expected-PARTIAL assertion. The unchanged live baseline reproduces that failure; checkpoint49 already records Asmodeus FULL and linked-return-family.md documents that earlier implementation. That assertion is left unchanged and is not a promotion or regression in this batch.

Canonical native scenarios: backend/tests/test_rules_counter_alternatives50.py. Actual database metadata: backend/tests/fixtures/counter_alternatives50_cards.json. Full Sigurd5 and Plague Boiler3 official rulings were read. Session evidence and the exact2-card admission manifest are in /tmp/counter50-admission-manifest.json. Full catalog regression audit remains the parent checkpoint's responsibility.

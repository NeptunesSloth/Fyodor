# Counter-removal triggers and suspended cards

Implemented against the repository's Comprehensive Rules dated 2026-09-25 and the canonical Oracle data in `tests/fixtures/counter_removal_trigger_cards.json`.

CR 603.2c distinguishes "a counter" from "one or more counters": removing two counters causes two singular triggers, each carrying amount one, but one grouped trigger carrying amount two. The native negative-counter event records the actual number removed, the remover and the permanent or suspended card's object identity. Removing zero counters causes no event. Counter-removal triggers continue to use the normal trigger ordering, multiplier and stack machinery.

The five direct cards are Chandra, Fire Artisan; Protean Hydra; Watcher of Hours; Riftmarked Knight; and Veiling Oddity. Explicit "you remove" is attributed to the player who performs the instruction, not automatically the suspended card's owner. Chandra's loyalty cost and planeswalker damage each remove loyalty through the same event path. Hydra creates one delayed trigger per counter actually removed; each future placement uses the normal counter replacement pipeline and the old object's identity.

A suspended card's last-counter trigger is independent of the effect that removed the counter (CR 702.62). Public exile objects with counters, and native suspended cards, now participate in counter-difference tracking. The old special emissions in the suspend upkeep and time-travel paths are removed so they do not duplicate those events or cast offers. Native last-counter detection checks exact object identity, exile, the suspended registry and the event's resulting counter count. Declining the suspend cast does not cancel a separate printed last-counter trigger.

Timecrafting and Fury Charm exercise real multi-counter removal. Their targets use the existing structured selector union: the battlefield permanent branch is separate from the suspended-card-in-exile branch. An arbitrary exiled card, an exiled card with no suspend, and a card whose last counter is gone are not suspended targets (CR 702.62b). Target legality remains checked at resolution.

The tests cover actual casting and mana costs, loyalty costs, damage prevention, singular versus grouped removal, opponent attribution, upkeep removal without duplicate events, last-counter casting and declining, delayed placements under Doubling Season, departed and recast objects, later creatures under Veiling Oddity's turn-wide restriction, expiry, history replay, JSON saves, and a saved surveil decision resumed in a fresh Python process.

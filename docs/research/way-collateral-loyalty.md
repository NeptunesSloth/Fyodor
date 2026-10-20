# Way of the Pyromancer, Cryomancer, and Healer collateral validation

These actual canonical cards are legendary enchantments, not Auras and not grants to nonplaneswalker creatures. Each empowers Jace on entry and grants a loyalty ability to planeswalkers its controller controls. The fixture is fetched from the card database with full Oracle metadata. Tests cast the enchantments normally and use the actual blue Jace planeswalker token created by the native empower action.

Pyromancer empowers 2 and grants `[+1]: Add {R}`. The loyalty cost is paid immediately, but this is a normal loyalty ability using the stack, not a mana ability. It obeys timing and once-per-turn rules. The activated ability still resolves if Pyromancer leaves; the static grant itself disappears, while the planeswalker's loyalty-use history remains.

Cryomancer empowers 5 and grants `[-3]: When you next cast an instant or sorcery spell this turn, copy that spell. You may choose new targets for the copy.` A real Lightning Bolt deals six damage with its copy, including after Cryomancer leaves. A second Bolt deals only three, proving the next-spell watch was consumed rather than persisting.

Healer empowers 5 and grants `[-2]: Create a 2/2 colorless Wizard Soldier creature token named Cadet. Surveil 1.` At exactly two loyalty, paying the cost causes the Jace token to die through the normal planeswalker state-based action, and the independent activated ability still creates the Cadet and surveils. An ordinary creature is unaffected and receives none of these grants.

All three grants reject combat-phase activation and enforce one loyalty activation per permanent per turn. The static grant applies to another controlled Jace Beleren but excludes an opponent's planeswalker and a controlled nonplaneswalker creature. Removing the source removes that grant without removing the planeswalker's existing counters. Each scenario checks history reconstruction and JSON save/load shape. Ten canonical gameplay cases pass; no application code changed for this validation.

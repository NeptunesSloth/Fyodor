# Current combat-pair predicates

The native static-rule and combat-legality pipeline now covers Spectral Grasp, Serpent of Yawning Depths, Godhunter Octopus, Kraken of the Straits, Ironclaw Curse, and Graxiplon. Restrictions are checked against current derived characteristics when a declaration is made (CR 508.1c and 509.1b). Native requirement optimizers use the same legality functions; their treatment of costs and locked declarations is unchanged.

Spectral Grasp uses its Aura controller for “you,” even when the enchanted creature has a different controller. Its attached rule uses the existing native controller binding. Serpent's two lists are native subtype selectors; a valid complete rule containing a comma-separated selector is kept together before splitting a compound predicate.

Godhunter's defender condition is a native union of two independently valid permanent selectors. An Enchantment controlled by the defending player or an enchanted permanent controlled by that player satisfies it. The player controlling an Aura need not control its enchanted permanent. Native defender lookup handles attacks on players, planeswalkers, and battles.

Kraken's rule stores a selector and a controller binding, rather than a cached Island count. It compares each blocker's current power with the current count. Ironclaw compares the attacker's current power with its host's current toughness; it does not use the Aura's controller or printed toughness. Graxiplon reuses the native maximum-shared-creature-type count among all creatures controlled by the actual defending player. The creatures declaring blocks need not belong to that shared group, and changeling works through native current creature types (CR 702.73a).

Printed source abilities and external direct rules retain their existing layer behavior. Removing a printed source ability removes its restriction. Removing the enchanted creature's abilities does not remove an Aura's direct blocking restriction. Native saved state, replay, exact-object payment frames, and callback registration are reused without new action or state fields.

Canonical metadata is copied from the imported Oracle database snapshot of 2026-10-18. Rules references use the pinned 2026-09-25 Comprehensive Rules at `data/rules/comprehensive_rules/2026-09-25/comprehensive_rules.txt`.

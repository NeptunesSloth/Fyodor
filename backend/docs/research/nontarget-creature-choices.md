# Resolution-time creature choices

Eleven canonical cards compose the existing public `player_chooses` continuation and exact-object bindings: Duneblast, Highcliff Felidar, Sigarda's Vanguard, Sigardian Zealot, Celestial Judgment, Gruesome Menagerie, Dawnbreak Reclaimer, Azra Oddsmaker, Gideon's Sacrifice, Kamiz, Obscura Oculus, and Winnowing.

The shared policies compare current derived powers, validate pairwise distinct powers, and select one creature from every power partition. These choices happen during resolution and do not target. Zero is allowed for “any number” and “up to one”; mandatory selections choose as much as possible. All choices complete before the native batch destroys, sacrifices, or returns cards. The global rest pool includes opponents' creatures. Winnowing uses current creature subtypes, including changeling, and explicitly spares each chosen creature even when it has no creature types.

Dawnbreak retains the owner of the first chosen graveyard card as the second chooser. If no opponent has any eligible card, the controller chooses an opponent to choose from the controller's graveyard, as required by its 2015-11-04 ruling. Each exact original graveyard object is returned only if still present. Kamiz binds its first attacker before connive and reads that original object's current power or last known information afterward. Its counter can change which other attackers have lesser power.

Gideon's Sacrifice uses the native damage-redirection replacement engine and an exact destination object; source identity, prevention ordering, current recipient types, and source departure retain their ordinary native behavior.

Wizards rulings retrieved from Scryfall confirm non-target selection, simultaneous destruction/return, independent power partitions, the empty-opponent-graveyard fallback, and conniving after a creature leaves. Tests include all eleven positive effects, negative/zero derived powers, optional zero selections, exact old/new object boundaries, and four fresh-process resumes covering public selection, private connive, and simultaneous-entry replacement ordering.

Ghouls' Night Out, Cultural Exchange, and Ascent of the Worthy are excluded from this implementation: prospective entry characteristics, atomic exchanges of groups, and a different redirection duration respectively require separate verification.

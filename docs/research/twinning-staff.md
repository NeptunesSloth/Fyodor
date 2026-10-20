# Twinning Staff — replace a spell-copying event

Sources: [Oracle](https://api.scryfall.com/cards/named?exact=Twinning+Staff), [official rulings](https://api.scryfall.com/cards/5cdcc324-1427-453c-9940-c21f5d04c997/rulings), checked 2026-10-19; Comprehensive Rules 2026-09-25, 614.1a (replacement), 614.5 (one application to an event), 707.10 (spell and ability copies), 707.10c–d (new and prescribed targets).

The printed replacement modifies a nonempty event that copies a spell, adding one copy per applicable Staff. Storm making N copies therefore makes N+1, not 2N. A zero-copy event does not qualify. Copying a card (such as Isochron Scepter), or copying an activated or triggered ability, does not qualify.

Official rulings require the additional copy to be insertable before, after, or between the original copies. Its controller may choose new targets even when the original copies have prescribed targets and cannot be retargeted. Original target restrictions remain in force. Modes, X, additional/alternative costs, and copiable exceptions remain those of the copied spell.

The typed replacement is evaluated once for the copying batch and stored with the saved copy job. The batch records original and additional copies separately, allowing insertion choices and preserving distinct target permissions. The special copy-for-each path must apply the replacement once to its entire set of original copies and resume correctly after an additional copy's target choices.

Gameplay validation includes same-controller Zada and opponent-controlled Mirrorwing Dragon: the player copying the spell determines which Staff replacement applies, even when another player controls the triggering creature. Tests also inspect the actual stack order for additional copies inserted before, between, and after prescribed copies.

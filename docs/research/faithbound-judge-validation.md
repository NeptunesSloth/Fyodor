# Faithbound Judge / Sinner's Judgment collateral promotion

Canonical two-face metadata and actual casting validate the promotion produced by explicit enchanted-player references. No production changes were required.

Front-face scenarios cast Faithbound Judge normally, advance through actual controller upkeeps to one, two and three judgment counters, reject an attack with defender at two, accept an attack at three while defender remains a keyword, verify vigilance leaves it untapped, and verify the upkeep counter cap at three. Another scenario destroys the front normally into the graveyard, then actually pays its disturb cost to cast Sinner's Judgment attached to a chosen player.

Back-face scenarios actually disturb-cast the Curse from the graveyard, verify it ticks on its controller's upkeep rather than its enchanted player's upkeep, then verify the third counter loses only the enchanted player. Changing Aura control changes whose upkeep triggers it. Changing its attachment while an upkeep trigger waits uses the current enchanted player at resolution. Destroying the Aura in response applies its own exile-instead replacement; the pending ability uses its exact source's last-known counters and enchanted player. With two counters on departure, adding a counter fails and the player does not lose; with three on departure, the trailing condition still holds and the last-enchanted player loses.

All scenarios replay and round-trip through JSON save/load. The tests use the ordinary native front, disturb, attachment, upkeep, counters, combat, replacement and game-loss mechanisms; there is no card-specific production override.

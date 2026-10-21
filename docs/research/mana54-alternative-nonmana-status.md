# Selected-spell alternative nonmana payments (mana54)

This family automates Disrupting Shoal, Blazing Shoal, Sickening Shoal, Nourishing Shoal, Foil, and Dream Halls using existing native alternative-cost and payment components. No classifier exceptions or test-only adapters are used.

The Shoals retain announced X while filtering the chosen hand payment by actual color and mana value; X in a card still in hand counts as zero. Disrupting Shoal can target any spell and compares its mana value only on resolution, using the native stack mana-value helper so the target’s own announced X counts. Foil pays two distinct discard components: an Island card and another card. Dream Halls grants every player a discard alternative whose color filter reads the actual spell, including red spells while Dream Halls itself is blue; colorless spells have no matching color. Additional spell taxes remain payable.

Native whole-card coverage includes six actual cold-process saved-game payments, wrong-color and wrong-mana-value atomic refusal, same-Island reuse refusal, an opponent using Dream Halls, hand X versus stack X, and Thalia’s additional tax. All official Scryfall rulings were read before implementation. Detailed evidence and final counts are in `/tmp/fyodor-mana54-production-admission-manifest.json`.

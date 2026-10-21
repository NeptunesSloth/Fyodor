# Urza’s Workshop

Urza’s Workshop’s metalcraft activation uses the existing artifact-count restriction and count-based mana ability. The missing piece was the canonical possessive land subtype `Urza's`: it must not be singularized to `Urza'`. Both straight and typographic apostrophes now normalize to the canonical subtype.

The count selects Urza’s lands the ability’s controller currently controls. A land with several subtypes counts once, the Workshop counts itself, and an artifact whose name begins with Urza’s is not a qualifying land. Changing control and replacing land types changes the count. Artifact lands and Treasure tokens satisfy metalcraft; losing the third artifact disables the second ability. The ordinary one-colorless ability remains available.

The canonical fixture copies all Oracle metadata from the local card database. Eleven gameplay cases exercise those boundaries, actual Spreading Seas, actual Brass’s Bounty, and automatic payment with Workshop as the only available mana source. Every case checks replay and JSON save/load. The focused eleven cases and all 162 selected selector, mana-rider, ability-word, and nonbasic-land regression cases pass. Two older tests needed aggregate mana-pool assertions because known-source mana is represented by ManaUnit records.

The Scryfall rulings endpoint for card `1e01c1e2-f657-4a24-b8b0-561911c4e754` has no card-specific rulings. This change reuses the existing mana gate, payment, and count machinery; it introduces no payment or casting changes.

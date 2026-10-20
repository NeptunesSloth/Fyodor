# Display of Power: multiple targeted spell copies

Oracle: “This spell can't be copied. Copy any number of target instant and/or sorcery spells. You may choose new targets for the copies.”

Zero targets are legal. Every chosen target is an instant or sorcery spell on the stack; either player's spells and spell copies qualify. Illegal targets are skipped, and the spell does not resolve if every announced target became illegal (CR 608.2b). The no-copy ability operates on the stack (CR 113.6g) and copying an uncopyable target does nothing without preventing other targets from being copied.

CR 707.10 and 707.10c define placing copies on the stack and making their target decisions. Each copy is controlled by the player who copies it, and copies are not cast. The controller chooses their relative order (CR 405.3 and the official Display ruling). Native copy jobs now have an explicit, saved choose_source_order flag for this plural instruction: before making each copy, choose its source from the remaining batches. This is more general than ordering whole source batches, since Twinning Staff's extra copies can interleave across different original spells. Existing replacement-kind ordering and native retarget decisions remain inside the selected source's next copy; the source-ready state persists through those pauses and is cleared after creation. Earlier copies are available when choosing targets for later copies, including counterspell copies.

The shared no-copy predicate already enforces the raw Oracle ability. Its static coverage marker now also accepts a spell-kind ability, since instant/sorcery Oracle lines are classified as spell abilities by the printed-card parser. No new payment path is involved. The predicate also limits self-referential “this spell” no-copy text to the stack: copying the card from a graveyard or exile is legal. An actual Mizzix’s Mastery gameplay regression covers that distinction.

Official rulings: https://api.scryfall.com/cards/295b8595-5b4e-4fc8-8249-486d36e15f67/rulings . They confirm arbitrary copy order, at most one copy per distinct target, and that the first ability functions only on the stack.

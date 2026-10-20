# Grouped counter values

Six canonical single-gap cards share native group selection and scalar effects:
Sovereign Okinec Ahau, Phyresis Outbreak, Vraska, Regal Gorgon, Aku Djinn,
Parallax Inhibitor, and Zar Ojanen, Scion of Efrava.

Sovereign freezes each current power-minus-base-power difference before the
single counter-placement instruction reaches replacements. Base power includes
layer 7b setters; counters and ordinary pumps contribute only to current power.
Native counter replacements receive the simultaneous original placement batch.

Phyresis Outbreak places poison counters first, including replacements and
prevention. It then freezes current creature membership, each creature's current
controller, and that player's poison count into native effects lasting until end
of turn. Later changes do not resize these effects.

Zar reads current basic land types and current creature toughness once when its
trigger resolves, using a strict less-than comparison. Vraska counts creature
cards in its controller's graveyard, Aku includes every opponent's creatures,
and Parallax selects current fading abilities rather than printed text, existing
fade counters, or vanishing. These instructions do not target.

Tests use canonical spells and abilities, actual attack/upkeep/loyalty/payment
paths, replacement and prevention effects, modified base/current stats, current
control, native replay, and a fresh-process saved replacement choice.

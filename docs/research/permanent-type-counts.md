# Distinct permanent types in a graveyard

Research date: 2026-10-19; rules source: stored Comprehensive Rules 2026-09-25.

Matzalantli, the Great Door's second ability has the activation restriction:

> Activate only if there are four or more permanent types among cards in your
> graveyard. (Artifact, battle, creature, enchantment, land, and planeswalker are
> permanent types.)

CR 110.4 identifies exactly these six permanent types. "Permanent types" is not
synonymous with all card types under 205.2a. Instant, sorcery, and kindred do not
add to the count. A Kindred Enchantment contributes enchantment; a Kindred
Instant contributes none. A card with several permanent types contributes each
of them, but repeated instances of a type count once. Great Furnace and Eidolon
of Blossoms together provide artifact, land, enchantment, and creature: four
permanent types in two cards.

Cards in a graveyard use their characteristics in that zone. For a DFC, this
normally means the front face (712.8a), so a battle's creature back face does not
supply an extra creature type. Current control of Matzalantli determines whose
graveyard the activation restriction checks.

The restriction is checked when activating the ability (602.2b), not as an
intervening-if condition on resolution. Removing the graveyard in response does
not undo a legal activation. The transformed permanent remains tapped, retains
its identity, and is not a new land entering the battlefield (712.18).

The Core's mana ability instead counts permanent **cards**, under CR 110.4a,
rather than distinct permanent types. Two multi-type permanent cards provide
two mana even if those cards provided four types for the transformation.

[Official rulings for the actual default printing](https://api.scryfall.com/cards/5e03b08d-f0f1-40e8-af48-1622430bab38/rulings)
were fetched with `curl` to `/tmp/fyodor-matzalantli-rulings.json`. The rulings
of 2023-11-10 confirm that transforming Matzalantli neither makes it leave the
battlefield nor untaps it, and that The Core's activated ability is a mana
ability that does not use the stack and cannot be responded to.

The bounded shared extension is a `permanent_types` variant of the existing
`distinct` value. It intersects each selected card's current types with the
existing six-type constant, using the existing selector and zone semantics.
The generic graveyard type-count condition can then accept "permanent types"
alongside "card types" and "mana values"; the ordinary activation-restriction
pipeline handles the remaining ability.

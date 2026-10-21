# Abundance: land/nonland draw replacement

Oracle text is preserved with canonical metadata in `backend/tests/fixtures/abundance_cards.json`:

> If you would draw a card, you may instead choose land or nonland and reveal cards from the top of your library until you reveal a card of the chosen kind. Put that card into your hand and put all other cards revealed this way on the bottom of your library in any order.

The optional draw replacement remains in the existing CR 616 replacement planner. A typed body chooses land/nonland, reveals through the first matching card, moves that card to hand without drawing it, then asks for the rest's private bottom order. A card type predicate is evaluated on cards in the library, without battlefield-only selector restrictions. The optional replacement can apply with an empty library (121.6a/614.11); replacing the draw prevents the empty-library draw-loss event (704.5b). If no card matches, the whole library is revealed and put on the bottom in the chosen order, with no card entering hand.

`pick_looked(require_found=True)` distinguishes a failed reveal-until from an ordinary one-card look: its historical one-card fallback must not take a nonmatching card. Other callers retain their existing behavior.

Draws in an instruction are separate, and this body finishes before the planner handles the next draw (121.2/121.6b). Native continuation data preserves pending multi-player draws in APNAP order. Applied-replacement tracking prevents the same effect from replacing its own resulting event repeatedly (614.5). Replacement bodies never emit a draw for cards they put in hand (121.5), so Sylvan Library cannot demand life or return those cards.

Revealed card identities are public while revealed. The ordering decision and resulting library order are private; an unrevealed tail stays hidden. Both the land/nonland choice and ordering use the existing saved decision context and ordinary recorded actions, so replay does not rerun the search or repeat a draw.

Mana-ability draw riders require the separately coordinated persistent continuation work in casting. A replacement choice cannot merely pause while the original caller goes on spending mana, applying more riders, or finishing a spell. The ordinary draw body does not claim to solve that casting requirement on its own.

Pinned CR 605.1a excludes abilities whose own cost or effect moves cards to/from a library, ignoring replacement effects for classification. A printed “Add mana. Draw a card.” source is therefore an ordinary activated ability. Low-level mana-rider continuation tests use an explicit structured-rider injection fixture below classification, rather than claiming such Oracle text is a legal mana ability. Canonical Chromatic Sphere/Chromatic Egg are tested as ordinary stack abilities by their owning classification scope.

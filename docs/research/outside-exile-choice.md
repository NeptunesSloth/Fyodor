# Karn, the Great Creator

Current Oracle text retrieved from Scryfall on 2026-10-19. CR 903.11 forbids
ordinary outside-game card imports in Commander, including from a saved
personal collection. It leaves Karn's alternative choice of a face-up artifact
card the controller owns in exile available. Choosing that card does not target.

An exact combined-language parser preserves the existing format guard, then
delegates the exile choice to the native optional card-choice/return operation.
Other formats retain the existing manual fallback for outside-game selection.
The selector checks card status, ownership, artifact type, exile zone and
face-up status. No collection cards are created or exposed.

Five focused tests cover no available exile card, acceptance, declining,
opponent ownership, nonartifacts, face-down exile, and collection privacy,
including history replay and save/load.

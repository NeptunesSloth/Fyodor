# Exile creatures, then compensate their controllers with searched lands

Research prepared during the seventh inventory freeze and implemented after release. Scope: Winds of Abandon and Settle the Wreckage, with native Path to Exile as a regression reference.

Official Oracle/rulings, checked 2026-10-19:

- https://api.scryfall.com/cards/3bb17913-fe4d-4acd-9b75-71f5a90f898b/rulings
- https://api.scryfall.com/cards/9cbd346e-098a-4cf6-a72f-468376fd2e8f/rulings

Winds overload has no targets and can exile opposing creatures with hexproof/protection. Normal casting targets one opposing creature. Settle targets a player, so individual attacking creatures' hexproof/protection does not stop exile. Count exiled creature permanents using battlefield last known information: tokens, animated noncreature cards and commanders still count even if they cease to exist or later move from exile. The refund belongs to the previous controller, not the owner.

Existing `this_way.by_controller` already groups actual exiled objects by their battlefield controllers and handles vanished tokens using departure records. The existing spell/overload and target-player-controlled selectors parse the exile prefixes correctly.

Winds then has affected players search privately, puts all found lands onto the battlefield tapped, and has those players shuffle. Searches must be collected before the simultaneous entry event; immediately entering each player's lands while later players are still choosing would violate instruction order. Native search already supports stated-quality failure to find, Mindcensor, Opposition Agent's controller/permission/exile handling, and normal private decisions.

Implemented reusable hook: an explicit deferred-entry search field. Inside native `_finish_search`, after Opposition Agent handling, collect would-enter entries with original library OIDs into the resolving context rather than entering immediately. Still record an accepted search even when no card is found. A final generic instruction commits the collected entries through one existing `attachments.enter` batch, then runs the required shuffles. No temporary move to hand or setaside, and no synthetic unsupported destination string.

Winds requires all affected players' final shuffles, including a player whose mandatory search was prohibited. Settle's search is optional; only choosing to search causes a shuffle, including searching for zero cards if no attackers were exiled, and finding nothing. If prohibited, optional search is not offered. This distinction needs separate typed flags rather than deriving participation from whether a land was found.

Canonical fixtures and gameplay tests are provided in `backend/tests/fixtures/exile_land_compensation_cards.json`. Planned validation includes normal/overloaded casting and alternate-cost restrictions; player versus creature targeting; LKI ownership/control; tokens and animated land creatures; zero attackers; partial/failed finds; simultaneous entry after all private choices; exact shuffle participation; Mindcensor, Ashiok and Opposition Agent; replay/save-load while collecting each player's selection.


Winds' per-creature wording causes one native one-card search per exiled creature, whereas Settle causes one search for the total number of cards. Actual Ob Nixilis, Unshackled gameplay proves three search triggers for Winds versus one for Settle with three exiled attackers. Found cards are reserved by exact original library OID and excluded from later searches via the existing selector predicate, while remaining in their library until the simultaneous put. Consequently Aven Mindcensor restricts each search to the same top four positions; later searches cannot refind a reserved card or see a fifth card just because another was found. Opposition Agent's immediate exile of a found card still follows native behavior.

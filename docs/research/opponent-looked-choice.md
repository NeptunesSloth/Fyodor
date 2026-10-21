# Opponent selection from inspected cards

Canonical family: Murmurs from Beyond, Animal Magnetism, Thran Tome, Karn, Scion of Urza, Phyrexian Grimoire and Guided Passage. All fixture fields come from the canonical Oracle database.

The native pick_looked effect now accepts an optional chooser reference. It changes only the decision recipient. The original effect controller still determines selection semantics, hand destinations, battlefield entry controller and any subsequent choices (CR 608.2c–d). Non-targeted 'an opponent' uses the existing choose_opponent binding; explicit target opponents retain ordinary targeting and resolution legality. Exact inspected object identities, native contexts, decision persistence and normal replacement/movement hooks are retained.

Animal Magnetism uses native attachments.enter: an opponent selects the creature card, but if that card is Clone, the original spell controller makes its copy-as-it-enters choice. The rest is put into the original controller's graveyard. A revealed set containing no creatures results in no chosen card and all the cards go to the graveyard.

Thran Tome's last instruction draws two cards normally, rather than putting the unchosen inspected cards into hand. Draw prohibitions/replacements and library exhaustion therefore retain their normal meanings. Explicit bound reveal cleanup hides cards that remain in the library after draws were prohibited. Murmurs instead puts the unchosen cards into hand without drawing them. Both use ordinary graveyard move replacements for the selected card.

Karn's +1 uses a native moved binding for the card exiled with a silver counter. Its −1 uses the existing ownership/counter/zone selector in a non-targeted native return choice. Any Karn can recover a card its current controller owns that has a silver counter in exile; it is not linked to the old Karn object. The existing −2 Construct ability remains native and is covered by an actual cast/loyalty/token scenario.

Phyrexian Grimoire seeds the ordinary inspected-card context with the top two cards of the controller's graveyard, exact object IDs and looked_zone=graveyard. The top is the last graveyard entry. Empty and one-card graveyards obey the normal 'as much as possible' rule (609.3), without searching or publicly revealing an already-public graveyard.

Guided Passage reveals the entire library, then the chosen opponent selects from three disjoint categories: creature, land, and noncreature/nonland. Missing categories are skipped. The selected cards enter the original controller's hand and the library shuffles once at the end. Native library-shuffle events and reveal cleanup apply normally.

Gameplay tests cold-restore JSON and replay history at decisions. Integration checks that cards revealed in a pending opponent selection are public in REST and WebSocket snapshots, then become hidden when put into the controller's hand. Other tests cover original-controller nested entry decisions, source destruction, actual draw prohibition, graveyard replacement, Karn ownership/control and source reentry, empty/small inspected sets and Guided Passage's category/shuffle boundaries.

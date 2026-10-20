# Turntimber Symbiosis

Canonical 10-card fixture: backend/tests/fixtures/turntimber_symbiosis_cards.json (all metadata plus complete MDFC faces copied from current local database).

Oracle front: Look at the top seven cards of your library. You may put a creature card from among them onto the battlefield. If that card has mana value 3 or less, it enters with three additional +1/+1 counters on it. Put the rest on the bottom of your library in a random order.

Implementation: scripts rider immediately following native pick_looked to battlefield, annotate counter='+1/+1', counter_n=3, counter_if=selector card with MV<=3. The typed rider accepts a decimal mana-value threshold and named counter amount, with exact subject and destination guards. _picked entry construction now uses the same counter_if gate return_card already implements. Supply counters as entry metadata, never a later put_counters effect: CR122.6 and614.1c. Preserve native copy/replacement ordering in attachments.enter.

Boundary: MV is evaluated for card chosen in library. X counts as zero off stack (Walking Ballista enters3 rather than dying); 3 qualifies,4 does not. Doubling Season changes3 to6, Solemnity prevents all counters. Priest redirects uncast creature to exile without ETB or entry counters. Cage prohibits entry and leaves chosen card in library; native pick consumes it from looked list before attempted entry, so verify rest-bottom instruction excludes chosen card even if it never moved. The actual Cage gameplay case verifies this.

Privacy: native look_top is private; native pick_looked deliberately emits empty chooser prompt when looked cards exist but none match. Test opponent redacted views and no leaked names, both declining valid creature and no creatures. Rest uses native bottom_random + recorded shuffle; deterministic replay, not assertion of one random order.

Canonical MDFC land needs both pay3life untapped and decline tapped, G mana, land play counts. Whole-card FULL only after both faces checked. Actual front cast must use front face and pay4GGG; no cast/mana edits.

Fourteen canonical gameplay cases pass, including replay and JSON save/load at the private choice. Tests: MV2 Grizzly Bears and MV3 Centaur Courser get3; MV4 Chupacabra gets0 and actual ETB target; X Ballista gets3 before SBA; DS6; Solemnity0; Priestexile; Cage stays library; optional decline; allnoncreatures; fewerthan7; MDFC back pay/decline; replay+JSON before hidden choice and after. Replacement/private pauses roundtrip too.

Official Scryfall endpoint fetches by both named and local printing ID returned HTTP400 in this environment. No card-specific rulings asserted from failed requests. CR122.6/614.1c,107.3g,701 look/random native machinery guide semantics.

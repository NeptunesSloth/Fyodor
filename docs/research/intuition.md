# Intuition: exact library search and opponent split

Oracle: “Search your library for three cards and reveal them. Target opponent chooses one. Put that card into your hand and the rest into your graveyard. Then shuffle.”

The targeted opponent is announced while casting. Scryfall's official ruling explicitly confirms this: https://api.scryfall.com/cards/c99f6785-e5a1-4fdc-9fb5-e1a372e7e848/rulings . If the sole target is illegal on resolution, the spell does not search, reveal, or shuffle (CR 608.2b).

CR 701.23d requires finding the exact quantity, or as many as possible, when no quality is specified. Intuition therefore differs from Gifts Ungiven: duplicate names are legal, declining to find is illegal, and a library of two cards produces a two-card opponent choice with one card going to hand. One available card goes directly to hand. The search is private, then all found cards are revealed before the opponent chooses. The remaining library is shuffled even if empty or the search finds nothing.

Implementation: extend the existing typed Gifts search/split continuation in refused_zones.py with explicit exact-count, different-names, and chosen-card-destination flags. Keep existing Gifts defaults and native search-controller/search-depth/prohibition handling. No separate special-case engine is necessary. Gameplay tests round-trip both paused decisions and verify announcements, exact counts, duplicate names, short libraries, reveal visibility, target illegality, search controls, and the shuffle event.

Implemented after the eighth checkpoint release. Eleven actual Oracle gameplay cases pass, including public reveal without revealing unrelated hand cards, Mindcensor, Opposition Agent, Stranglehold, target illegality, short libraries, and exact duplicate-name searches. All 61 related refused-zones and search-control regressions pass. Shuffle remaps hidden library identifiers; assertions intentionally check remaining card names/counts rather than obsolete IDs.

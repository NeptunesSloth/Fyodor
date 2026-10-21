# Revealed cards with two staged choices

This batch36 extension automates Bounty of Skemfar, Green Sun's Twilight, and Wakanda Forever! using native library reveal, exact looked-card references, card choices, entry replacements, entry counters, and cleanup. It does not stage library cards through a player's hand before entry.

Green Sun's Twilight requires choosing at least one matching card when any exists. A creature and a land are different chosen cards; a creature land can fulfill either category but cannot be chosen twice. Native distinct-kind matching validates the two-card choice. When X is at least five, a single subsequent destination choice applies to every chosen card: both go onto the battlefield or both go into the hand. The native choose-only looked-card staging binds original library objects without moving them; a queued native return-card instruction performs the actual move. This preserves paused entry continuations and normal entry replacements.

Bounty of Skemfar makes two optional choices in order: one land enters tapped, then one Elf goes to the hand. Wakanda Forever! similarly makes an optional permanent entry with its indestructible counter before entry, then an optional permanent hand choice. A chosen card that fails to enter, such as a creature prohibited by Grafdigger's Cage, remains among the revealed cards and can be chosen by the second instruction. The restore-between-picks step retains only original library object IDs (CR400.7); leaving the library and returning does not make a new incarnation eligible.

Unchosen cards use native random-bottom placement or graveyard movement, preserving public reveal and normal hidden-library cleanup. Indestructible counters use native entry metadata before the permanent enters (CR122.6), including applicable counter replacements. Green's mandatory card choice is a native saved decision and later moves use native effects; no custom entry or replacement engine is introduced.

Canonical fixtures and gameplay tests are in `backend/tests/test_rules_revealed_two_stage_picks.py` and its separate JSON fixture. Proofs include both Green destinations, minimum/maximum and distinct-kind constraints, absent matches, Bounty's tapped entry and separate Elf choice, Wakanda's doubled entry counter and prohibited-entry fallback, exact object identity after a library departure, and two fresh-process replay/save continuations.

Official Oracle rulings were retrieved from Scryfall and preserved during development in `/tmp/fyodor-qualified-look36-rulings.json`. Green Sun's Twilight's ruling explicitly requires all chosen cards to share the destination. Public card references:

- https://scryfall.com/search?q=%21%22Green+Sun%27s+Twilight%22
- https://scryfall.com/search?q=%21%22Bounty+of+Skemfar%22
- https://scryfall.com/search?q=%21%22Wakanda+Forever%21%22

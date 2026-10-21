# Search instructions with entry counters

Neoform's current Oracle instruction searches for exact mana value equal to one
plus the sacrificed creature's mana value, then puts the found creature onto the
battlefield with an additional +1/+1 counter. The native additional-cost payment
record already retains sacrificed last-known characteristics and the tutor already
reads that value. The missing clause was the instructed entry counter.

The bounded grammar recursively reads the ordinary native search, requires one
battlefield destination and no split destination, and adds native entry-counter
metadata. The existing search entry path passes that metadata to attachments.enter,
so counters are part of entry (CR 122.6), including entry replacements and counter
replacement/prevention. It never adds counters after the creature enters.

Six canonical gameplay/save/replay cases pass: exact sacrificed value plus one,
optional fail-to-find without refund, and ordinary/Doubling Season/Solemnity/
Containment Priest entry outcomes. Wider native tutor regressions run separately.

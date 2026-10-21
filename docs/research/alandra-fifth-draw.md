# Alandra: fifth draw and one self/group pump

The draw-event grammar now accepts fourth and fifth ordinals using its existing ordinal map and per-player/per-turn draw history. Alandra's first ability continues to use the same second-card mechanism. Batched draws generate the fifth-card trigger once while the entire drawing spell finishes before triggers are stacked.

The ordinary pump grammar accepts a self reference followed by a controlled permanent group. It builds the existing deduplicated union recipient reference and executes one ordinary pump instruction. The hand-size value is therefore evaluated once, and a source that is also a Drake receives the bonus once. This does not add arbitrary mixed-target unions or a new runtime primitive.

The union independently preserves its two meanings: self refers to the original source object, while the controlled group uses current characteristics and the pending ability's controller at resolution. A departed source still pumps Drakes. A blinked source is not the old self reference, but its new object can independently qualify as a controlled Drake. Recipients are fixed when the resolving pump applies; later group entrants are not retroactively affected.

Canonical gameplay tests cover fourth/fifth/sixth draw timing, multiple-card draws crossing fifth, both controller-selected orderings of second-card Drake creation and fifth-card pump from one Opportunity, current hand size, current group/controller and type changes, source departure/blink, Maskwood Nexus deduplication, opponent draw isolation, and end-of-turn expiry. All scenarios check history replay and JSON save/load, including the simultaneous-trigger order decision.

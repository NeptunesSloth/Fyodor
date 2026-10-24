# Reserved exile counter access family85

Canonical four: Draugr Necromancer, Haldan Avid Arcanist, Evelyn the Covetous, Lara Croft Tomb Raider. This is a scout, not a FULL admission.

Lara's native permission is a dynamic exile-zone selector for discovery counters until end of turn. It must include old discovery-counter cards from any source, and cards which gain discovery counters later in the turn; freezing only the just-exiled card is incorrect. Native permission filter and zone_owner:any can express this. A target that becomes illegal makes the entire ability fail; choosing zero targets still creates the permission.

Draugr's ice counters do not imply any provenance restriction, but casting is restricted by opponent ownership and the spending exception is only mana from snow sources. Current mana allocation has producer facts and snow provenance, but the permission spend enum lacks this exception. General any-color would be incorrect. Hold until allocator supports exact restricted source substitutions with actual-source proofs.

Haldan requires exact exiling-player provenance on the current exile object; Evelyn requires original exiling ability controller, not merely who moved the card or current Evelyn controller. The existing exiled_with links track a particular source object and cannot substitute for either predicate. Evelyn also requires native once-per-turn use accounting keyed to the actual current static authority; a new source incarnation is a new ability. Do not implement either by source-linked access or invented counters alone.

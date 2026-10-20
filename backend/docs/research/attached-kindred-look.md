# Call to the Kindred

The canonical Oracle fixture is copied into `attached_kindred_look_cards.json` from the batch's canonical qualified-look fixture. The official 2011-01-22 ruling confirms that a creature needs to share only one creature type with the enchanted creature; it need not share every type.

The printed upkeep ability uses the normal optional-trigger decision before any library cards are inspected. On acceptance, `attached_kindred_look` composes native exact top-five inspection, an optional creature selection, battlefield entry, and private bottom ordering. No selected card is revealed merely because the player looked at it.

The native trigger pipeline captures an exact host reference. At resolution, the leaf prefers the exact source Aura's current enchanted creature. If the Aura left, its snapshot identifies its former host; if host departure detached the Aura before its own state-based graveyard move, native unattached-event receipts preserve the exact Aura and host object identities. The host's current or last battlefield characteristics determine its creature types, filtered against the creature-type vocabulary. A returned new incarnation does not replace the old host reference.

The native entry pipeline handles replacement effects. Containment Priest redirects the selected creature to exile and that new object is excluded from the remaining library cards. If Grafdigger's Cage prevents entry and the selected object remains unchanged in its library, the leaf restores it to the native looked-at set so it is included among the rest to be ordered at the bottom.

The focused scenarios include an actual Aura cast and natural upkeep trigger, optional decline before looking, declining a creature after looking, exact private bottom ordering, fresh-session continuation, host death before resolution, current creature-type changes, source departure, host blink identity, and REST/WebSocket privacy.

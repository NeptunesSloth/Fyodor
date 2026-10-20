# Avatar's Wrath: the complement of an optional target

Current Oracle text checked on 2026-10-19:
https://api.scryfall.com/cards/named?exact=Avatar%27s%20Wrath

The optional target is selected when casting, before costs (601.2c). The remaining
creatures are airbent without being targeted (115.6, 608.2c, 701.65), so hexproof
does not protect a creature from that part. Choosing zero targets airbends all
creatures. If the sole chosen target becomes illegal, the entire spell fails to
resolve (608.2b), including its later cast restriction and self-exile instruction.

The descriptor stores the excluded group as a target reference, independently of
the resolution bindings used by other exclusion effects. It participates in
ordinary target renumbering when spell lines or modes are combined. Airbending
continues through the existing exile/owner-permission primitive. Existing cast
restrictions implement the subsequent lock until the caster's next turn.

Seven gameplay cases cover zero/one targets, untargeted hexproof creatures, illegal
hexproof targeting, lost targets, announcement timing, the opponent's exile-cast
lock and its expiry, with replay and save/load checks. Fixtures retain real Oracle
metadata. Related airbend and card-layout regressions are checked separately.

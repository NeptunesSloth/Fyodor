# Mana abilities that create delayed effects

Chocobo Camp, Yuna, Grand Summoner, Solar Array, Brass Infiniscope, and Rainbow Vale use the existing delayed-trigger, spell-rider, and control-choice machinery. Mana production stays immediate. Deferred library movement occurs only when the later triggered ability resolves, consistent with CR 605.1a.

The mana-ability descriptor stores a typed delayed-effects payload. Activation captures the source object and controller before creating native watches. Brass Infiniscope reads the triggering spell's announced X, including when that spell is countered; its saved draw continuation preserves that value. Rainbow Vale follows the original object, so blinking or phasing it out prevents the transfer. The original activating player makes the opponent choice even after control changes.

Solar Array grants Sunburst as a noncopiable ability on the spell, which carries through resolution. Entry replacements use prospective characteristics and timestamps: an earlier Humility does not erase a later grant, while a later Humility does. Artifact creatures receive +1/+1 counters; other artifacts receive charge counters. A spell copy does not acquire the original's continuous grant.

Yuna's death trigger reads all counter kinds from the departed permanent's last known information and preserves the native optional target and intervening condition.

Validation: 25 canonical gameplay cases cover all five cards, X=0 through larger announced values, rounding, both Solar timestamp orders, spell copying, departed sources, original-object changes, counter-kind aggregation, replay, save/load, and a fresh-process paused draw continuation. Independent review found a native counter-commit limit for a legitimate transfer above 1000 counters; that shared limit requires correction before treating the large-count path as verified.

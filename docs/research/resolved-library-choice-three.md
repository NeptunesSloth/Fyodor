# Three resolved library and parity choices

Abundant Harvest, Vexing Arcanix, and Zimone's Hypothesis compose existing native effects. The parser is a pure leaf; it introduces no state schema, payment behavior, or new decision callbacks.

Harvest uses the existing land/nonland choice and reveal-until handler, takes the found card only when present, and returns the rest in a random order. This preserves Abundance's separate ordered-bottom instruction. When no card of the chosen kind exists, all revealed cards return and no card is drawn.

Arcanix uses the existing Petra Sphinx name choice and top-card reference. Its otherwise branch contains both the graveyard move and two damage, so a correct guess skips both. With an empty library the condition is false, the move does nothing, and two damage still happens. The targeted player chooses the name; the original artifact remains the damage source.

Zimone's optional counter is an up-to-one resolved choice among any creatures, including an opponent's hexproof creature. It introduces no target. The odd/even choice and bounce remain mandatory after declining the counter. Native current power, parity, owner routing, and counter replacements apply before the bounce.

Canonical gameplay covers all three cards, both found kinds, absent kind, correct/wrong names, empty library, optional counter accepted/declined, opponent hexproof, and mandatory bounce despite declining. Each card additionally resumes its saved choice in an independent Python process and replays the native action history.

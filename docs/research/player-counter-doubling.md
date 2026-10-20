# Aetheric Amplifier

The printed mana ability and modal sorcery restriction were already supported. The missing second mode now doubles every positive counter kind the original ability controller has, using the normal counter replacement pipeline (701.10e, 122.6). Speed is explicitly excluded because it is a player resource rather than a counter (702.179).

The primitive batches counter additions and preserves its original continuation when the affected player chooses replacement order. Counter prohibitions and additions from Vorinclex or Lae'zel apply normally. Doubling Season does not multiply counters given to players. Poison reaching ten invokes normal state-based actions.

Tests cover both modal choices, four mana plus tapping, sorcery timing, all original mana colors, mixed counter kinds, speed, zero counters, source control changes, native replacements and prohibitions, poison loss, replay and JSON saves. A new Python process loads a saved modal ability and resolves it with separate replacement choices for two kinds of player counters.

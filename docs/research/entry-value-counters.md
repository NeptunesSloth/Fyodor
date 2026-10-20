# Entry counter values and choices

Five current canonical cards now reuse native entry replacements:

- Sheriff of Safe Passage gets one plus the other creatures already controlled.
  The official ruling excludes simultaneous arrivals; native value evaluation
  uses the entry batch's existing newcomer exclusion.
- Thought Sponge uses the greatest draw total of one opponent, including an
  opponent who left the game. Its official ruling requires retaining those
  players' native turn-history counts, rather than using the existing sum of
  current opponents' draws.
- Slumbering Trudge uses max(0, 3−X) stun counters and enters tapped only for
  X≤2. Its entry plan reads announced stack X, including copied spells; uncast
  entry uses zero. Nullable non-X stack values are zero.
- Canker Abomination chooses an opponent before entry, then counts that saved
  player's creatures. The normal entry-choice continuation binds an explicit
  player selector and normal counter batch; no target or intervening priority.
- Murktide Regent counts instant/sorcery objects used for delve. CostContribution
  retains the paid object's card types before exile. These cost-object traits
  survive spell copying (707.10) and subsequent movement (607.2q, 608.2h);
  reanimation has no such payment. Legacy missing snapshots explicitly request
  manual entry counters instead of fabricating old characteristics.

Canonical gameplay tests include departed-player draw history, Living Death's
simultaneous arrivals, all X thresholds, actual pre-entry opponent selection
after JSON reload, actual delve including non-spell cards, Pull from Eternity
moving a paid card before resolution, Double Major copying original paid-cost
objects, uncast entries, and complete history replay. Current Scryfall rulings
were fetched independently for all five cards during implementation.

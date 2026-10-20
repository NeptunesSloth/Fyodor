# Steel Hellkite — damage history destruction

Sources: [Oracle and official rulings](https://api.scryfall.com/cards/548cbc66-d915-4b94-86da-4c909a1ce645/rulings), checked 2026-10-19; Comprehensive Rules 2026-09-25, 120.8 (zero damage), 400.7 (new objects), 602.5b (activation restriction), 608.2h (information at resolution), 701.8 (destroy).

The last ability destroys nonland permanents of exactly the announced mana value controlled by any player dealt combat damage by this particular source object during this turn. It does not target. The official rulings explicitly permit activation without prior damage and specify current control and current battlefield membership, including permanents that entered after the damage. X=0 includes ordinary tokens and other permanents without a mana cost. Actual damage history excludes prevented and zero damage.

Implementation: `damage_controller_destruction` parses a permanent selector and a source-damage predicate into typed effect data. It reads the activated ability's captured source object identity, binds X from the resolving ability, and delegates simultaneous destruction to the ordinary rules pipeline. This retains indestructible, regeneration, replacement handling, and replayable actions. Ordinary once-per-turn activation restrictions already enforce this ability's printed restriction.

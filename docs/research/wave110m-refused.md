# Wave 110M — cards left PARTIAL (73/79 of cloud_m.txt are FULL)

One line each: what is missing and why it was not guessed.

- Snowblind: Y = min(X, "enchanted creature's toughness minus 1"). CR 613 does not settle whether that toughness is read before or after the other layer-7 effects (including this one's own -X); no ruling in `data/rules`. Refused rather than guess.
- Shaman's Trance: "as though those cards were in your graveyard" must make flashback/escape/Underworld Breach-style graveyard permissions (and "from your graveyard" restrictions) treat another player's graveyard as yours. The engine keys every graveyard permission to the holder's own graveyard; making that substitution global is not done, and a partial version would mis-handle those permissions.
- Panglacial Wurm: casting a card from the library in the middle of a search needs a priority/cast window inside resolving search (CR 701.23 plus 117.1 mid-resolution casting, ruling 2018-xx "cast it while the search resolves"). The resolution loop has no such pause; not faked.
- North Star: "for one spell this turn" needs an opt-in marker chosen at cast time that is applied to that spell's payment only; the cast flow has no per-spell payment-rule choice. Not built; mana-as-any-type stays manual.
- Grell Philosopher: built in wave 110J (last cards): abilities collected at resolution (611.2c; rulings 2004-10-04 "collecting abilities" / 2022-06-10), tests/test_rules_wave110j_last.py.
- Magar of the Magic Strings: face-down permanent with a noted card name, plus copy-and-cast of the noted name from a later combat-damage trigger; the noted-name store across a face-down object is not built.

Known limits of promoted cards: Bloodcaster's life offers do not cover X spells.

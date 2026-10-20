# Attack destinations and independent requirements

Canonical Oracle text comes from `data/cards.sqlite`. The rules reference is the
pinned 2026-09-25 Comprehensive Rules, especially 508.1c–d, 611.2c, 608.2h and
701.15c–d.

508.1d maximizes the **number of requirements**, including separate requirements
that happen to use identical words. In an actual three-player game, Bident of
Thassa makes both Bears attack if able; Incite independently makes one of them
attack. Silent Arbiter allows only one attacker. The twice-required Bear must be
chosen. Previously, the derived set `{'must_attack'}` lost this distinction and
accepted the other Bear.

`attack_requirements.instances` retains continuous-effect/static origins as
auxiliary imposed markers. Plain rule markers remain available for existing
legality checks and old saves. Printed abilities contribute separately. Old
untagged save data conservatively retains its one known imposed requirement;
multiplicity already discarded by an older engine cannot be reconstructed.
Goad remains keyed by the goading player, because 701.15d explicitly says repeated
goad by the same player adds no further requirements. All three declaration
scoring paths share the same additive score; their existing bounded dynamic
programming, restrictions, group completion and optional-cost treatment remain.

The shared destination leaf supports these actual cards:

* Ravener and Dulcet Sirens: independently targeted creature and opponent.
* Public Enemy: all creatures read the enchanted creature's current controller.
* Galactus, Devourer of Worlds: current opposing life totals, tied maxima and the
  current controller's named-creature exception. Literal comma titles survive
  self-name normalization.
* Ursine Monstrosity: mill, one native random-opponent binding, the combat-only
  destination and native snapshot pump/indestructible.
* Silver Surfer, Galactus's Herald: the actual damaged player's binding and the
  native end-of-next-turn expiry.
* The Brothers' War: two distinct target players, reciprocal destinations and
  dynamic creature groups until the original controller's next turn.
* Gideon Jura: a continuous rule beginning during the targeted opponent's actual
  next turn, with the original planeswalker object's identity as destination.
* Trench Behemoth: a continuous rule beginning at the named controller's actual
  next combat phase, and ending with that combat. The target creature is an
  exact object; the named controller is determined when the ability resolves.
* Furygale Flocking: native token creation and replacement continuations, with
  each created group bound to its opponent and separately granted temporary haste.

Future turn/combat windows are typed metadata on continuous effects. Read-only
views do not consume them. Native turn/phase beginnings activate them before
beginning-of-phase triggers, so no invented, counterable delayed trigger changes
the rules. Extra combats consume exactly the first relevant actual combat;
leaving the source after resolution does not cancel the resulting effect.

Illegal destinations never become legal through a requirement. A target player
who is also the creature's controller cannot be attacked. An old planeswalker
object does not mean its blinked replacement. Tapped creatures, Pacifism and
other restrictions still apply. Attack costs remain voluntary under 508.1d.

`tests/test_rules_attack_destinations34.py` exercises the actual cards through
casting, activation, Saga chapters, landfall, combat damage and declaration,
including replay/JSON persistence and a fresh-process pending target choice.

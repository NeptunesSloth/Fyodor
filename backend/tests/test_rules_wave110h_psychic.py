"""Wave 110H: Psychic Battle (CR 601.2c, 603.3d, 115.7a, 202.3, 701.20a, real Oracle text).

* Psychic Battle: when a player puts a spell or ability with targets on the stack, each player reveals their top card; the single greatest mana value may change
  the targets (each to another legal target, or none); a tie, or declining, leaves them; a change doesn't trigger it again.
"""
from __future__ import annotations

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from tests.fixtures.cards import fixture_cards
from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import real
from tests.wave9c_kit import build, card_named, check, mana, put, to_hand

PB = ("Whenever a player chooses one or more targets, each player reveals the top card of their library. The player who reveals the card with the greatest mana value may "
      "change the target or targets. If two or more cards are tied for greatest, the target or targets remain unchanged. Changing targets this way doesn't trigger abilities "
      "of permanents named Psychic Battle.")
EXTRA = [
    real("Psychic Battle", "{3}{U}{U}", 5, "Enchantment", PB, None, "U"),
    real("Test Zap", "{R}", 1, "Instant", "Test Zap deals 1 damage to target creature.", None, "R"),
    real("Test Giant", "{3}", 3, "Creature — Giant", "", ("4", "4"), ""),
    real("Test Ogre", "{2}", 2, "Creature — Ogre", "", ("3", "3"), ""),
]


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def test_full(cards):
    assert coverage.of_card_data(cards.resolve("Psychic Battle")).level == "FULL"


def _setup(cards, top1, top2):
    s = build(cards, ["Psychic Battle", "Test Zap", "Test Giant", "Grizzly Bears"], ["Test Giant", "Test Ogre", "Grizzly Bears"], forests=3, islands=3)
    put(s, "Psychic Battle")
    mine = put(s, "Test Giant")
    theirs = put(s, "Test Ogre", "p2")
    for pid, name in (("p1", top1), ("p2", top2)):
        if name:
            c = card_named(s, name, pid)
            act(s, pid, type="move", card_ids=[c.id], to={"player": pid, "zone": "library"}, position="top")
    return s, mine, theirs


def _zap(s, target):
    to_hand(s, "Test Zap")
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Test Zap").id, targets=[target.id])


def _dmg(s, c):
    return s.state.cards[c.id].damage


@pytest.mark.parametrize(("top1", "top2", "change", "moved"), [
    ("Forest", "Test Giant", True, True),    # p2 reveals the greater mana value and changes the target
    ("Forest", "Test Giant", False, False),  # ... or declines
    ("Grizzly Bears", "Island", True, True),  # p1 (the caster) reveals the greater
    ("Grizzly Bears", "Grizzly Bears", True, False),  # tied: unchanged
    ("Forest", "Island", True, False),  # tied at zero
])
def test_change(cards, top1, top2, change, moved):
    s, mine, theirs = _setup(cards, top1, top2)
    _zap(s, theirs)
    seen = []
    for _ in range(40):
        d = s.state.rules.decision
        if d is not None:
            seen.append(d.player)
            ids = [o.id for o in d.options]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[mine.id if change and mine.id in ids else "keep" if "keep" in ids else ids[0]])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    assert (_dmg(s, theirs), _dmg(s, mine)) == ((0, 1) if moved else (1, 0))
    assert bool(seen) == (moved or not change and top1 != top2)  # asked only when one player shows the greatest value
    check(s)

"""Wave 110H: Feather, Radiant Arbiter (CR 707.10d, 601.2c, 118.1, 608.2c, real Oracle text).

* Feather: the cast trigger lets the controller choose any number of other creatures (of any controller) the spell could target, pay {2} for each, and only
  then copy the spell for each of them, each copy targeting that creature; not paying (or choosing none) makes no copy.
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
from tests.wave9c_kit import build, check, mana, put, to_hand

FEATHER = ("Flying, lifelink\nWhenever you cast a noncreature spell that targets only Feather, you may choose any number of other creatures that spell could target and pay {2} "
           "for each of those creatures. If you do, for each of those creatures, copy that spell. The copy targets that creature. (Copies of permanent spells become tokens.)")
EXTRA = [
    real("Feather, Radiant Arbiter", "{1}{W}{W}", 3, "Legendary Creature — Angel", FEATHER, ("3", "4"), "W"),
    real("Test Zap", "{R}", 1, "Instant", "Test Zap deals 1 damage to target creature.", None, "R"),
    real("Test Giant", "{3}", 3, "Creature — Giant", "", ("4", "4"), ""),
]


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def test_full(cards):
    assert coverage.of_card_data(cards.resolve("Feather, Radiant Arbiter")).level == "FULL"


def _run(s, pick, pay):
    """Cast Zap at Feather, then answer: the creatures chosen (names), whether {2} each is paid."""
    for _ in range(20):
        d = s.state.rules.decision
        if d is not None:
            if d.kind == "choose_cards":
                ids = [o.id for o in d.options if s.state.cards[o.card_id].name in pick]
                act(s, d.player, type="choose", decision_id=d.id, option_ids=ids)
            elif {"pay", "decline"} <= {o.id for o in d.options}:
                act(s, d.player, type="choose", decision_id=d.id, option_ids=["pay" if pay else "decline"])
            else:  # the order the copies go on the stack (707.10d)
                act(s, d.player, type="choose", decision_id=d.id, option_ids=[d.options[0].id])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return


@pytest.mark.parametrize(("pick", "pay", "hurt"), [
    ({"Grizzly Bears", "Test Giant"}, True, {"Feather": 1, "Grizzly Bears": 1, "Test Giant": 1}),  # a copy for each, {4} paid
    ({"Test Giant"}, True, {"Feather": 1, "Grizzly Bears": 0, "Test Giant": 1}),  # only the opponent's creature
    ({"Grizzly Bears", "Test Giant"}, False, {"Feather": 1, "Grizzly Bears": 0, "Test Giant": 0}),  # the payment is declined: no copy
    (set(), True, {"Feather": 1, "Grizzly Bears": 0, "Test Giant": 0}),  # none chosen
])
def test_feather_copies_for_each_creature_paid_for(cards, pick, pay, hurt):
    s = build(cards, ["Feather, Radiant Arbiter", "Grizzly Bears", "Test Zap"], ["Test Giant"])
    feather, bears = put(s, "Feather, Radiant Arbiter"), put(s, "Grizzly Bears")
    giant = next(c for c in s.state.cards.values() if c.name == "Test Giant")
    act(s, "p2", type="move", card_ids=[giant.id], to={"zone": "battlefield"})
    mana(s, "p1", R=1, C=4)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Test Zap").id, targets=[feather.id])
    _run(s, pick, pay)
    got = {"Feather": s.state.cards[feather.id].damage, "Grizzly Bears": s.state.cards[bears.id].damage, "Test Giant": s.state.cards[giant.id].damage}
    assert got == hurt
    check(s)
    if pick and pay:
        assert s.state.players["p1"].mana.get("C", 0) == 4 - 2 * len(pick)  # {2} for each chosen creature, no more

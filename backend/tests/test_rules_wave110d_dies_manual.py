"""Wave 110D: the old "stay manual" cards of wave 35b (now FULL by waves 110B/G/K), checked against their Oracle text.

* Whippoorwill: 701.19c the target can't be regenerated (even by a shield made earlier); 615.12 damage to it can't be prevented; exile if it dies.
* Runesword: 611.2a +2/+0 only for the targeted attacker; 701.19c / 614.1a a creature it damaged is exiled instead of dying.
* Touch of Moonglove: +1/+0 and deathtouch (702.2); 603.7c only creatures that creature damaged make their controller lose 2.
"""
from __future__ import annotations

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from tests.fixtures.cards import fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditionals import until
from tests.test_rules_wave12a_counters_keywords import real
from tests.test_rules_wave110g_s9 import answer
from tests.wave9c_kit import build
from tests.wave110b_kit import cast, check, mana, put

EXTRA = [
    real("Whippoorwill", "{G}", 1, "Creature — Bird", "{G}{G}, {T}: Target creature can't be regenerated this turn. Damage that would be dealt to that creature this turn can't be "
         "prevented or dealt instead to another permanent or player. When the creature dies this turn, exile the creature.", ("1", "1"), "G"),
    real("Drudge Skeletons", "{1}{B}", 2, "Creature — Skeleton", "{B}: Regenerate this creature. (The next time this creature would be destroyed this turn, instead tap it, remove it from combat, and heal all damage on it.)", ("1", "1"), "B"),
    real("Mending Hands", "{W}", 1, "Instant", "Prevent the next 4 damage that would be dealt to any target this turn.", None, "W"),
    real("Hill Giant", "{3}{R}", 4, "Creature — Giant", "", ("3", "3"), "R"),
]


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


@pytest.mark.parametrize("name", ["Whippoorwill", "Touch of Moonglove", "Runesword", "Heroic Sacrifice", "End-Blaze Epiphany"])
def test_full(cards, name):
    from tests.test_rules_wave35b_dies_this_turn import DATA

    c = next(c for c in DATA if c["name"] == name)
    from tests.test_rules_scripts import ch

    assert coverage.of_characteristics(ch(c["name"], c["type_line"], c["oracle_text"])).level == "FULL"


def _whip(cards, victim, whip, shield):
    """p1's ``victim`` has ``shield`` (regeneration or Mending Hands) up; Whippoorwill's ability is used on it or not; then Bolt (3 damage) hits it."""
    s = build(cards, ["Whippoorwill", "Drudge Skeletons", "Hill Giant", "Mending Hands", "Lightning Bolt"])
    bird, target = put(s, "Whippoorwill"), put(s, victim)
    until(s, lambda s: s.state.turn.number == 3 and s.state.turn.phase == "main1" and s.state.rules.decision is None)  # past summoning sickness
    if shield == "regenerate":
        mana(s, "p1", B=1)
        act(s, "p1", type="activate_ability", card_id=target.id, ability=0)
        answer(s)
    else:
        mana(s, "p1", W=1)
        cast(s, "Mending Hands", [target.id])
        answer(s)
    if whip:
        mana(s, "p1", G=2)
        act(s, "p1", type="activate_ability", card_id=bird.id, ability=0, targets=[target.id])
        answer(s)
    mana(s, "p1", R=1)
    cast(s, "Lightning Bolt", [target.id])
    answer(s)
    return s, target


@pytest.mark.parametrize(("whip", "zone"), [(True, "p1:exile"), (False, "p1:battlefield")])
def test_whippoorwill_stops_regeneration(cards, whip, zone):
    s, target = _whip(cards, "Drudge Skeletons", whip, "regenerate")
    assert s.state.cards[target.id].zone == zone
    check(s)


@pytest.mark.parametrize(("whip", "zone"), [(True, "p1:exile"), (False, "p1:battlefield")])
def test_whippoorwill_stops_prevention(cards, whip, zone):
    s, target = _whip(cards, "Hill Giant", whip, "prevent")  # Mending Hands would absorb Bolt's 3 damage
    assert s.state.cards[target.id].zone == zone
    check(s)


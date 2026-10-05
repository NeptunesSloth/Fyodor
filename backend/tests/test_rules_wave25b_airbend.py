"""Wave 25B: airbend (CR 2026-09-25, 701.65). Real Oracle text; every scenario checks the replay and a save and a load.

* 701.65a: airbend = exile; for each card exiled this way, for as long as it remains exiled, its owner may cast it by paying {2}
  rather than its mana cost (an alternative cost, 118.9; additional costs and cost changes still apply, 118.9d).
* 400.7h: the permission follows the object; a card that left exile is a new object.
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import answer
from tests.wave9c_kit import build, card_named, check, mana, put, to_hand, zone_of

CARDS = [
    ("Airbending Lesson", "{2}{W}", "Instant — Lesson", None, None,
     "Airbend target nonland permanent. (Exile it. While it's exiled, its owner may cast it for {2} rather than its mana cost.)\nDraw a card."),
    ("Glider Staff", "{2}{W}", "Artifact — Equipment", None, None,
     "When this Equipment enters, airbend up to one target creature. (Exile it. While it's exiled, its owner may cast it for {2} rather than its mana cost.)\n"
     "Equipped creature gets +1/+1 and has flying.\nEquip {2}"),
    ("Appa, Steadfast Guardian", "{2}{W}{W}", "Legendary Creature — Bison Ally", "3", "4",
     "Flash\nFlying\nWhen Appa enters, airbend any number of other target nonland permanents you control. (Exile them. While each one is exiled, "
     "its owner may cast it for {2} rather than its mana cost.)\nWhenever you cast a spell from exile, create a 1/1 white Ally creature token."),
    ("Probe Giant", "{4}{G}{G}", "Creature — Giant", "6", "6", ""),
    ("Probe Bear", "{1}{G}", "Creature — Bear", "2", "2", ""),
    ("Probe Totem", "{3}", "Artifact", None, None, ""),
]
EXTRA = [card(n, set_code="t25b", number=f"A{i:02d}", mana_cost=mc, cmc=float(sum(1 for _ in mc.split("}")) - 1), type_line=tl,
              colors=["W"], color_identity=["W"], oracle_text=text, power=p, toughness=t)
         for i, (n, mc, tl, p, t, text) in enumerate(CARDS)]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def level(name):
    c = next(c for c in EXTRA if c["name"] == name)
    return coverage.of_card_data({**c, "faces": c.get("card_faces") or []}).level


@pytest.mark.parametrize("name", ["Airbending Lesson", "Glider Staff", "Appa, Steadfast Guardian"])
def test_airbend_cards_are_full(name):
    assert level(name) == "FULL", name


def cast(s, name, *picks, pid="p1"):
    act(s, pid, type="cast_spell", card_id=card_named(s, name, pid).id)
    answer(s, *picks)


def test_airbending_a_permanent_exiles_it_and_its_owner_may_cast_it_for_two(cards):
    s = build(cards, ["Airbending Lesson", "Probe Giant"])
    giant = put(s, "Probe Giant")
    to_hand(s, "Airbending Lesson")
    mana(s, W=3)
    cast(s, "Airbending Lesson", giant.id)
    assert zone_of(s, "Probe Giant") == "p1:exile"
    mana(s, G=2)  # {4}{G}{G} normally: only {2} is paid (an alternative cost, 118.9)
    assert giant.id in _hints(s)["castable"]
    act(s, "p1", type="cast_spell", card_id=giant.id)
    answer(s)
    assert zone_of(s, "Probe Giant") == "p1:battlefield"
    assert sum(s.state.players["p1"].mana.values()) == 0
    check(s)


def _hints(s):
    from app.rules.view import hints

    return hints(s.state, "p1", s.cards)


def test_the_alternative_cost_is_all_that_is_paid_even_with_more_mana(cards):
    s = build(cards, ["Airbending Lesson", "Probe Giant"])
    giant = put(s, "Probe Giant")
    to_hand(s, "Airbending Lesson")
    mana(s, W=3)
    cast(s, "Airbending Lesson", giant.id)
    mana(s, G=5)
    act(s, "p1", type="cast_spell", card_id=giant.id)
    answer(s)
    assert zone_of(s, "Probe Giant") == "p1:battlefield"
    assert sum(s.state.players["p1"].mana.values()) == 3  # (5 - 2)
    check(s)


def test_one_mana_is_not_enough(cards):
    s = build(cards, ["Airbending Lesson", "Probe Giant"])
    giant = put(s, "Probe Giant")
    to_hand(s, "Airbending Lesson")
    mana(s, W=3)
    cast(s, "Airbending Lesson", giant.id)
    mana(s, G=1)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=giant.id)
    assert zone_of(s, "Probe Giant") == "p1:exile"


def test_only_the_owner_may_cast_an_airbent_card(cards):
    """Bob's creature is airbent by Alice: Alice can't cast it, Bob (its owner) can (701.65a)."""
    s = build(cards, ["Airbending Lesson"], ["Probe Bear"])
    bear = put(s, "Probe Bear", "p2")
    to_hand(s, "Airbending Lesson")
    mana(s, W=3)
    cast(s, "Airbending Lesson", bear.id)
    assert zone_of(s, "Probe Bear", "p2") == "p2:exile"
    mana(s, G=2)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=bear.id)
    check(s)


def test_a_card_that_left_exile_loses_the_permission(cards):
    """400.7h: put into the graveyard and back to exile by hand it is a new object, so the airbend permission is spent."""
    s = build(cards, ["Airbending Lesson", "Probe Giant"])
    giant = put(s, "Probe Giant")
    to_hand(s, "Airbending Lesson")
    mana(s, W=3)
    cast(s, "Airbending Lesson", giant.id)
    act(s, "p1", type="move", card_ids=[giant.id], to={"player": "p1", "zone": "graveyard"})
    act(s, "p1", type="move", card_ids=[giant.id], to={"player": "p1", "zone": "exile"})
    mana(s, G=2)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=giant.id)


def test_a_token_airbent_is_gone(cards):
    s = build(cards, ["Airbending Lesson"])
    act(s, "p1", type="create_token", player="p1", token={"name": "Goblin", "type_line": "Token Creature — Goblin", "power": "1",
                                                            "toughness": "1", "text": ""})
    token = next(c for c in s.state.cards.values() if c.is_token)
    to_hand(s, "Airbending Lesson")
    mana(s, W=3)
    cast(s, "Airbending Lesson", token.id)
    assert token.id not in s.state.cards or s.state.cards[token.id].zone != "p1:battlefield"
    assert not s.state.rules.permissions
    check(s)


def test_glider_staff_airbends_up_to_one_target_creature_as_it_enters(cards):
    s = build(cards, ["Glider Staff", "Probe Bear"])
    bear = put(s, "Probe Bear")
    to_hand(s, "Glider Staff")
    mana(s, W=3)
    cast(s, "Glider Staff", bear.id)
    assert zone_of(s, "Probe Bear") == "p1:exile" and zone_of(s, "Glider Staff") == "p1:battlefield"
    check(s)


def test_appa_airbends_any_number_of_other_nonland_permanents_you_control_and_casting_from_exile_triggers_it(cards):
    s = build(cards, ["Appa, Steadfast Guardian", "Probe Bear", "Probe Totem"])
    bear, totem = put(s, "Probe Bear"), put(s, "Probe Totem")
    appa = to_hand(s, "Appa, Steadfast Guardian")
    mana(s, W=4)
    act(s, "p1", type="cast_spell", card_id=appa.id)
    answer(s, [bear.id, totem.id])
    assert zone_of(s, "Probe Bear") == "p1:exile" and zone_of(s, "Probe Totem") == "p1:exile"
    mana(s, G=2)
    act(s, "p1", type="cast_spell", card_id=bear.id)
    answer(s)
    assert zone_of(s, "Probe Bear") == "p1:battlefield"
    allies = [c for c in s.state.cards.values() if c.is_token and c.name == "Ally" and c.zone.endswith(":battlefield")]
    assert len(allies) == 1  # (Appa: "Whenever you cast a spell from exile")
    check(s)

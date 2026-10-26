"""Wave 110A: Celestial Reunion: the optional additional cost chooses a creature type and beholds two creatures of it (601.2b, 701.4a); the tutored creature
card enters the battlefield instead of the hand only when the cost was paid and the revealed card is of the chosen type (608.2c)."""

import pytest

from app.game.errors import ActionError
from app.rules import coverage
from tests.wave110c_kit import act, answer, build, check, make_db, mana, put, real, to_hand

EXTRA = [real("Celestial Reunion", "{X}{G}", 1, "Sorcery",
              "As an additional cost to cast this spell, you may choose a creature type and behold two creatures of that type.\n"
              "Search your library for a creature card with mana value X or less, reveal it, put it into your hand, then shuffle. If this spell's additional cost "
              "was paid and the revealed card is the chosen type, put that card onto the battlefield instead of putting it into your hand.", None, "G")]


@pytest.fixture()
def card_db(settings):
    return make_db(settings, EXTRA)


def test_full(cards):
    assert coverage.of_card_data(cards.resolve("Celestial Reunion")).level == "FULL"


def _reunion(cards, found, paid=True, kind="Elf", x=2):
    s = build(cards, ["Celestial Reunion", "Llanowar Elves", "Llanowar Elves", "Elvish Visionary", "Grizzly Bears"])
    one = put(s, "Llanowar Elves")
    two = put(s, "Elvish Visionary")
    spell = to_hand(s, "Celestial Reunion")
    mana(s, "p1", G=1 + x)
    extra = {"optional_costs": [f"{spell.id}:behold_type110a"], "pick110e": kind, "cost_choices": [{"component": 0, "cards": [one.id, two.id]}]} if paid else {}
    act(s, "p1", type="cast_spell", card_id=spell.id, x_value=x, **extra)
    answer(s)
    return s, found


def _where(s, name):
    return {c.zone for c in s.state.cards.values() if c.name == name and c.owner == "p1" and c.zone != "p1:library"}


def test_chosen_type_found_enters_the_battlefield(cards):
    s, _ = _reunion(cards, "Llanowar Elves")  # (the first pick is the Elf in the library; two Elves are already beheld)
    assert "p1:battlefield" in _where(s, "Llanowar Elves") and len([c for c in s.state.cards.values() if c.name == "Llanowar Elves" and c.zone == "p1:battlefield"]) == 2
    check(s)


def test_other_type_found_goes_to_hand(cards):
    s = build(cards, ["Celestial Reunion", "Llanowar Elves", "Elvish Visionary", "Grizzly Bears"])
    one, two, spell = put(s, "Llanowar Elves"), put(s, "Elvish Visionary"), to_hand(s, "Celestial Reunion")
    mana(s, "p1", G=3)
    act(s, "p1", type="cast_spell", card_id=spell.id, x_value=2, optional_costs=[f"{spell.id}:behold_type110a"], pick110e="Elf",
        cost_choices=[{"component": 0, "cards": [one.id, two.id]}])
    answer(s, [next(c.id for c in s.state.cards.values() if c.name == "Grizzly Bears" and c.zone == "p1:library")])
    assert _where(s, "Grizzly Bears") == {"p1:hand"}
    check(s)


def test_unpaid_goes_to_hand_even_if_of_the_type(cards):
    s = build(cards, ["Celestial Reunion", "Llanowar Elves"])
    spell = to_hand(s, "Celestial Reunion")
    mana(s, "p1", G=2)
    act(s, "p1", type="cast_spell", card_id=spell.id, x_value=1)
    answer(s)
    assert _where(s, "Llanowar Elves") == {"p1:hand"}
    check(s)


def test_needs_two_creatures_of_the_chosen_type(cards):
    s = build(cards, ["Celestial Reunion", "Llanowar Elves", "Grizzly Bears"])
    one, bear, spell = put(s, "Llanowar Elves"), put(s, "Grizzly Bears"), to_hand(s, "Celestial Reunion")
    mana(s, "p1", G=2)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=spell.id, x_value=1, optional_costs=[f"{spell.id}:behold_type110a"], pick110e="Elf",
            cost_choices=[{"component": 0, "cards": [one.id, bear.id]}])


def test_the_caster_is_asked_for_the_type(cards):
    s = build(cards, ["Celestial Reunion", "Llanowar Elves", "Llanowar Elves", "Elvish Visionary"])
    one, two, spell = put(s, "Llanowar Elves"), put(s, "Elvish Visionary"), to_hand(s, "Celestial Reunion")
    mana(s, "p1", G=2)
    act(s, "p1", type="cast_spell", card_id=spell.id, x_value=1, optional_costs=[f"{spell.id}:behold_type110a"], cost_choices=[{"component": 0, "cards": [one.id, two.id]}])
    d = s.state.rules.decision
    assert d.kind == "choose_one" and "Elf" in {o.id for o in d.options}
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["Elf"])
    answer(s)
    assert len([c for c in s.state.cards.values() if c.name == "Llanowar Elves" and c.zone == "p1:battlefield"]) == 2
    check(s)

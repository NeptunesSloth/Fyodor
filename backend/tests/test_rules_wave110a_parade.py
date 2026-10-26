"""Wave 110A: Starlight Spectacular: you choose your creatures one at a time (101.4); each gets +1/+1 until end of turn per creature chosen before it (611.2c)."""

import pytest

from app.rules import coverage
from tests.test_rules_wave34b_activated import to_phase
from tests.wave9c_kit import pt
from tests.wave110c_kit import answer, build, check, make_db, put, real

EXTRA = [real("Starlight Spectacular", "{2}{W}{W}", 4, "Enchantment",
              "Parade! — At the beginning of combat on your turn, choose creatures you control one at a time until each creature you control has been chosen. "
              "Each of those creatures gets +1/+1 until end of turn for each creature chosen before it. (Places everyone! The first creature in line gets +0/+0.)", None, "W")]


@pytest.fixture()
def card_db(settings):
    return make_db(settings, EXTRA)


def test_full(cards):
    assert coverage.of_card_data(cards.resolve("Starlight Spectacular")).level == "FULL"


def _table(cards, names):
    s = build(cards, ["Starlight Spectacular", *names])
    put(s, "Starlight Spectacular")
    return s, [put(s, n) for n in names]


def test_order_gives_growing_bonus(cards):
    s, (a, b, c) = _table(cards, ["Grizzly Bears", "Benalish Hero", "Llanowar Elves"])
    base = {x.id: pt(s, x.name) for x in (a, b, c)}
    to_phase(s, "begin_combat", 1)
    answer(s, c.id, a.id)  # Dragon first, Bears second, the Giant is left (no choice)
    for bonus, x in enumerate((c, a, b)):
        w, h = base[x.id]
        assert pt(s, x.name) == (w + bonus, h + bonus)
    check(s)


def test_two_creatures_second_gets_one(cards):
    s, (a, b) = _table(cards, ["Grizzly Bears", "Benalish Hero"])
    base = {x.name: pt(s, x.name) for x in (a, b)}
    to_phase(s, "begin_combat", 1)
    answer(s, b.id)
    assert pt(s, "Benalish Hero") == base["Benalish Hero"]
    assert pt(s, "Grizzly Bears") == (base["Grizzly Bears"][0] + 1, base["Grizzly Bears"][1] + 1)
    check(s)

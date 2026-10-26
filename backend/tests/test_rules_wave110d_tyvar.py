"""Wave 110D: Tyvar the Bellicose, real Oracle text (tests/fixtures/wave110d_cards.json).

* 605.3b, 106.12a: a mana ability resolves as it is activated; "Whenever a mana ability of this creature resolves" sees how much mana it produced.
* 603.2h: "This ability triggers only once each turn" (per creature, each has its own copy).
"""

from __future__ import annotations

from tests.wave110d_kit import (  # noqa: F401
    activate,
    build,
    card_db,
    cast_on,
    check,
    full,
    hand_new,
    mana,
    now,
    put_new,
    settle,
    to_phase,
)

NAME = "Tyvar the Bellicose"


def test_full():
    assert full(NAME)


def _board(cards, extra=()):
    s = build(cards, [NAME, "Llanowar Elves", "Priest of Titania", "Grizzly Bears", *extra], ["Grizzly Bears"])
    put_new(s, NAME)
    out = s, put_new(s, "Llanowar Elves"), put_new(s, "Priest of Titania"), put_new(s, "Grizzly Bears")
    to_phase(s, "main1", turn=3)  # (no longer summoning sick)
    return out


def counters(s, c):
    return now(s, c).counters.get("+1/+1", 0)


def test_counters_equal_the_mana_produced(cards):
    s, elf, priest, bears = _board(cards)
    activate(s, elf, "{T}: Add")
    activate(s, priest, "{T}: Add")
    assert (counters(s, elf), counters(s, priest), counters(s, bears)) == (1, 3, 0)  # the Priest adds {G} for each Elf: three (Tyvar is an Elf too)
    check(s)


def test_paying_a_cost_with_it_triggers_too(cards):
    s, elf, priest, bears = _board(cards, ["Lightning Bolt"])
    cast_on(s, "Lightning Bolt", "p2")  # (paid from its own mana)
    check(s)

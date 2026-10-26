"""Wave 110H session 7: one-card builds on real Oracle text (each scenario checks replay and a save/load round trip).

* Stitcher Geralf: each player mills three (701.17); up to two creature cards among those milled are exiled; the Zombie is as big as their total power (608.2c, 107.1b).
"""
from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import real
from tests.test_rules_wave110h_s5 import answer
from tests.test_rules_wave30m_durations import to_phase
from tests.wave9c_kit import build, card_named, check, mana, put

EXTRA = [
    real("Stitcher Geralf", "{2}{U}", 3, "Legendary Creature — Human Wizard",
         "{2}{U}, {T}: Each player mills three cards. Exile up to two creature cards put into graveyards this way. Create an X/X blue Zombie creature token, "
         "where X is the total power of the cards exiled this way.", ("3", "4"), "U"),
    real("Hill Giant", "{3}{R}", 4, "Creature — Giant", "", ("3", "3"), "R"),
    real("Grizzly Bears", "{1}{G}", 2, "Creature — Bear", "", ("2", "2"), "G"),
    real("Runeclaw Bear", "{1}{G}", 2, "Creature — Bear", "", ("2", "2"), "G"),
    real("Sol Ring", "{1}", 1, "Artifact", "{T}: Add {C}{C}.", None, ""),
]
NAMES = [c["name"] for c in EXTRA]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database
    from tests.fixtures.cards import fixture_cards

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.mark.parametrize("name", NAMES)
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def top(s, name, pid):
    act(s, pid, type="move", card_ids=[card_named(s, name, pid).id], to={"zone": "library"}, position="top")


def geralf(cards, mine, theirs):
    s = build(cards, ["Stitcher Geralf", "Hill Giant", "Grizzly Bears", "Runeclaw Bear", "Sol Ring"], ["Hill Giant", "Grizzly Bears"])
    g = put(s, "Stitcher Geralf")
    to_phase(s, "main1", 3)  # (summoning sickness is over on the controller's next turn)
    for n in reversed(mine):
        top(s, n, "p1")
    for n in reversed(theirs):
        top(s, n, "p2")
    mana(s, U=1, C=2)
    act(s, "p1", type="activate_ability", card_id=g.id, ability=0)
    return s


def zombies(s):
    return [c for c in s.state.cards.values() if c.is_token and c.name == "Zombie"]


def test_geralf_exiles_two_milled_creatures_total_power(cards):
    """Pick one of each side: 3 + 2 power, a 5/5 Zombie; the other milled creature stays in its graveyard, the noncreature is not offered."""
    s = geralf(cards, ["Hill Giant", "Sol Ring", "Runeclaw Bear"], ["Grizzly Bears", "Hill Giant", "Island"])
    d = s.state.rules.decision
    assert d is not None and len(d.options) == 4 and d.max_choices == 2 and d.min_choices == 0
    mine = card_named(s, "Hill Giant", "p1")
    theirs = card_named(s, "Grizzly Bears", "p2")
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[mine.id, theirs.id])
    answer(s)
    assert s.state.cards[mine.id].zone == "p1:exile" and s.state.cards[theirs.id].zone == "p2:exile"
    (z,) = zombies(s)
    assert s.state.cards[z.id].zone == "p1:battlefield"
    from app.rules.plan import Plan
    assert Plan(s.state, "p1", s.cards, None).ch(z).pt == (5, 5)
    assert card_named(s, "Runeclaw Bear", "p1").zone == "p1:graveyard"
    check(s)


def test_geralf_none_exiled_makes_a_dying_zombie(cards):
    """Choosing none: X is 0 (107.1b), the 0/0 Zombie is created and put into the graveyard by state-based actions; the milled cards stay."""
    s = geralf(cards, ["Hill Giant", "Grizzly Bears", "Sol Ring"], ["Island", "Island", "Island"])
    d = s.state.rules.decision
    assert d is not None
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[])
    answer(s)
    assert not zombies(s) or all(s.state.cards[z.id].zone != "p1:battlefield" for z in zombies(s))
    assert card_named(s, "Hill Giant", "p1").zone == "p1:graveyard"
    check(s)

"""Wave 110D: Volcanic Offering, real Oracle text. Every scenario checks the replay and a save and a load.

* 115.1, 601.2c: the caster announces the own targets; for each "of an opponent's choice" target the caster picks the opponent (when several), who picks.
* 115.3: two instances of "target" are two groups. 701.8: destroy the lands. 120.3: 7 damage to each creature.
"""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import real
from tests.test_rules_wave110d_three import three
from tests.wave9c_kit import build, check, mana, put, to_hand
from tests.wave110d_kit import card_db as _kit_db  # noqa: F401
from tests.wave110d_kit import now, settle

EXTRA = [real("Volcanic Offering", "{4}{R}", 5, "Instant",
              "Destroy target nonbasic land you don't control and target nonbasic land of an opponent's choice you don't control.\n"
              "Volcanic Offering deals 7 damage to target creature you don't control and 7 damage to target creature of an opponent's choice you don't control.",
              None, "R")]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database
    from tests.fixtures.cards import fixture_cards

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def test_full(cards):
    assert coverage.of_card_data(cards.resolve("Volcanic Offering")).level == "FULL"


def cast(s):
    vo = to_hand(s, "Volcanic Offering")
    mana(s, "p1", R=1, C=4)
    act(s, "p1", type="cast_spell", card_id=vo.id, sources=[])
    return vo


def pick(s, player, option):
    d = s.state.rules.decision
    assert d is not None and d.player == player, (d and (d.player, d.prompt))
    assert option in {o.id for o in d.options}, ([o.id for o in d.options], option)
    act(s, player, type="choose", decision_id=d.id, option_ids=[option])
    return d


def test_two_players(cards):
    s = build(cards, ["Volcanic Offering"], ["Command Tower", "Command Tower", "Grizzly Bears", "Grizzly Bears"])
    towers = [c for c in s.state.cards.values() if c.name == "Command Tower" and c.owner == "p2"]
    bears = [c for c in s.state.cards.values() if c.name == "Grizzly Bears" and c.owner == "p2"]
    for c in (*towers, *bears):
        act(s, "p2", type="move", card_ids=[c.id], to={"player": "p2", "zone": "battlefield"})
    cast(s)
    d = s.state.rules.decision  # my own targets first: the first land, then the first creature
    pick(s, "p1", towers[0].id)
    pick(s, "p1", bears[0].id)
    d = pick(s, "p2", towers[1].id)  # the lone opponent chooses the second land, no question about which opponent
    assert "opponent" not in d.prompt
    pick(s, "p2", bears[1].id)
    settle(s)
    assert [now(s, c).zone for c in towers] == ["p2:graveyard"] * 2 and [now(s, c).zone for c in bears] == ["p2:graveyard"] * 2
    check(s)


def test_three_players_each_group_asks_which_opponent(cards):
    s = three(cards, ["Volcanic Offering"], ["Command Tower", "Grizzly Bears"], ["Command Tower", "Llanowar Elves"])
    t2, t3 = (next(c for c in s.state.cards.values() if c.name == "Command Tower" and c.owner == p) for p in ("p2", "p3"))
    b, e = (next(c for c in s.state.cards.values() if c.name == n and c.owner == p) for n, p in (("Grizzly Bears", "p2"), ("Llanowar Elves", "p3")))
    for c in (t2, t3, b, e):
        act(s, c.owner, type="move", card_ids=[c.id], to={"player": c.owner, "zone": "battlefield"})
    cast(s)
    pick(s, "p1", t2.id)  # own land: p2's
    pick(s, "p1", e.id)  # own creature: p3's Elves
    d = pick(s, "p1", "p3")  # land of an opponent's choice: p3 picks
    assert "target 2" in d.prompt
    pick(s, "p3", t3.id)  # (their own land: any nonbasic land the caster doesn't control)
    pick(s, "p1", "p2")  # creature of an opponent's choice: p2 picks
    pick(s, "p2", b.id)
    settle(s)
    assert {now(s, c).zone for c in (t2, t3)} == {"p2:graveyard", "p3:graveyard"} and {now(s, c).zone for c in (b, e)} == {"p2:graveyard", "p3:graveyard"}
    check(s)


def test_opponent_may_pick_the_same_land_again(cards):
    """115.3: the two lands are two instances of "target": the opponent may choose the land already targeted."""
    s = build(cards, ["Volcanic Offering"], ["Command Tower", "Grizzly Bears"])
    t = next(c for c in s.state.cards.values() if c.name == "Command Tower" and c.owner == "p2")
    b = put(s, "Grizzly Bears", "p2")
    act(s, "p2", type="move", card_ids=[t.id], to={"player": "p2", "zone": "battlefield"})
    cast(s)
    pick(s, "p1", t.id)
    pick(s, "p1", b.id)
    pick(s, "p2", t.id)
    pick(s, "p2", b.id)
    settle(s)
    assert now(s, t).zone == "p2:graveyard" and now(s, b).zone == "p2:graveyard"
    check(s)


def test_no_nonbasic_land_cannot_be_cast(cards):
    from app.game.errors import ActionError

    s = build(cards, ["Volcanic Offering"], ["Grizzly Bears"])
    put(s, "Grizzly Bears", "p2")
    vo = to_hand(s, "Volcanic Offering")
    mana(s, "p1", R=1, C=4)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=vo.id, sources=[])

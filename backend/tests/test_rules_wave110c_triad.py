"""Wave 110C: The Capitoline Triad: exile any number of historic cards with total mana value 30 or greater (601.2h, 118.3; not collecting evidence), then an emblem
(114.1, 114.5: it stays) gives creatures base power and toughness 9/9 (613.4b)."""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import coverage
from tests.game_helpers import act
from tests.wave9c_kit import pt
from tests.wave110c_kit import build, check, make_db, put, real, to_hand

TRIAD = ("Those Who Came Before — This spell costs {1} less to cast for each historic card in your graveyard. (Artifacts, legendaries, and Sagas are historic.)\n"
         "Exile any number of historic cards from your graveyard with total mana value 30 or greater: You get an emblem with \"Creatures you control have base power and "
         "toughness 9/9.\"")
EXTRA = [real("The Capitoline Triad", "{10}", 10, "Legendary Creature — God Artificer", TRIAD, ("7", "7"), "")]
EXTRA += [real(f"Big Relic {n}", "{10}", 10, "Artifact", "", None, "") for n in "ABC"]
EXTRA += [real(n, "{9}{G}", 10, "Creature — Bear", "", ("5", "5"), "G") for n in ("Big Bear", "Grave Bear")]


@pytest.fixture()
def card_db(settings):
    return make_db(settings, EXTRA)


def test_full(cards):
    assert coverage.of_card_data(cards.resolve("The Capitoline Triad")).level == "FULL"


def _grave(s, names):
    cs = [to_hand(s, n) for n in names]
    act(s, "p1", type="move", card_ids=[c.id for c in cs], to={"player": "p1", "zone": "graveyard"})
    return cs


def test_exile_historic_cards_with_total_mana_value_30(cards):
    s = build(cards, ["The Capitoline Triad", "Big Relic A", "Big Relic B", "Big Relic C", "Big Bear", "Grave Bear"])
    triad = put(s, "The Capitoline Triad")
    put(s, "Big Bear")
    relics = _grave(s, ["Big Relic A", "Big Relic B", "Big Relic C"])
    bear = _grave(s, ["Grave Bear"])[0]
    act(s, "p1", type="activate_ability", card_id=triad.id, ability=1)
    d = s.state.rules.decision
    assert d is not None and {o.id for o in d.options} == {c.id for c in relics}  # the non-historic Bear isn't offered
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[c.id for c in relics])
    while s.state.rules.stack or s.state.rules.decision:
        act(s, s.state.rules.priority, type="pass_priority")
    assert all(s.state.cards[c.id].zone == "p1:exile" for c in relics) and s.state.cards[bear.id].zone == "p1:graveyard"
    assert pt(s, "Big Bear") == (9, 9) and pt(s, "The Capitoline Triad") == (9, 9)
    check(s)


def test_twenty_historic_mana_value_is_not_enough(cards):
    """118.3: total mana value 20 can't pay for 30."""
    s = build(cards, ["The Capitoline Triad", "Big Relic A", "Big Relic B"])
    triad = put(s, "The Capitoline Triad")
    _grave(s, ["Big Relic A", "Big Relic B"])
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=triad.id, ability=1)

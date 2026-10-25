"""Wave 110B: single cards read from an exact wording (real Oracle text, tests/fixtures/wave110b_cards.json); each scenario checks replay and save/load.

* Prince of Thralls: 118.12 "unless that opponent pays 3 life": the opponent whose permanent went to the graveyard chooses.
* Oath of Lim-Dul: 120.3/603.2 one "sacrifice a permanent … unless you discard a card" for each 1 life lost, each with its own choice (608.2c).
"""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.wave110b_kit import build, check, drive, mana, put, repository, to_hand


@pytest.fixture()
def cards(settings):
    yield from repository(settings)


@pytest.mark.parametrize("name", ["Prince of Thralls", "Oath of Lim-Dûl"])
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


@pytest.mark.parametrize("pays", [False, True])
def test_prince_takes_the_permanent_unless_its_controller_pays_3_life(cards, pays):
    s = build(cards, ["Prince of Thralls", "Lightning Bolt"], ["Grizzly Bears"])
    put(s, "Prince of Thralls")
    bears = put(s, "Grizzly Bears", "p2")
    mana(s, "p1", R=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Lightning Bolt").id, targets=[bears.id])
    drive(s, lambda d: [next((o.id for o in d.options if o.label.startswith("Pay") == pays), d.options[0].id)])
    assert s.state.players["p2"].life == (37 if pays else 40)
    assert s.state.cards[bears.id].zone == ("p2:graveyard" if pays else "p1:battlefield")
    check(s)


@pytest.mark.parametrize("discards", [0, 1, 3])
def test_oath_asks_once_per_life_lost(cards, discards):
    """Lightning Bolt: 3 damage is 3 life lost, so three separate sacrifice-unless-discard choices; each discard saves one permanent."""
    s = build(cards, ["Oath of Lim-Dûl", "Forest", "Forest", "Forest", "Lightning Bolt"], [])
    put(s, "Oath of Lim-Dûl")
    forests = [c.id for c in s.state.cards.values() if c.name == "Forest" and c.zone == "p1:library"]
    act(s, "p1", type="move", card_ids=forests[:3], to={"player": "p1", "zone": "battlefield"})
    hand = forests[3:3 + discards]
    for f in hand:
        act(s, "p1", type="move", card_ids=[f], to={"player": "p1", "zone": "hand"})
    mana(s, "p1", R=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Lightning Bolt").id, targets=["p1"])
    def answer(d):
        return [next((o.id for o in d.options if o.id in hand), d.options[0].id)]

    drive(s, answer)
    lands = [c for c in s.state.zones["p1:battlefield"] if s.state.cards[c].name == "Forest"]
    assert len(lands) == discards
    check(s)

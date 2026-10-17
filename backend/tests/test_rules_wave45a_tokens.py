"""Wave 45A: "for each token you control that entered this turn, create a token that's a copy of it" (CR 2026-09-25), real Oracle text
(tests/fixtures/wave45a_cards.json, from data/cards.sqlite). Every scenario checks the replay and a save and a load.

* 111.10, 707.2, 702.131: "At the beginning of your end step, if you gained life this turn, create a 1/1 white Cat creature token. Then if you have the city's
  blessing, for each token you control that entered this turn, create a token that's a copy of it." (Ocelot Pride [1098]) - the Cat just made is one of them, and
  its being the tenth permanent gives the blessing before the check (ruling 2024-06-07); a token that came in on an earlier turn is not copied.
"""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_wave34b_activated import activate, settle, stops, to_phase
from tests.wave9c_kit import build, card_named, check, mana, put, to_hand
from tests.wave45a_kit import cast, open_cards


@pytest.fixture()
def cards(settings):
    yield from open_cards(settings)


def test_ocelot_pride_is_full(cards):
    assert coverage.of_card_data(cards.resolve("Ocelot Pride")).level == "FULL"


def cats(s):
    return [c for c in s.state.zones["p1:battlefield"] if s.state.cards[c].name == "Cat"]


def pride_table(cards, lands):
    s = build(cards, ["Ocelot Pride", "Revitalize"], [], forests=30)
    stops(s)  # (both players get priority at every step)
    put(s, "Ocelot Pride")
    for c in [c for c in s.state.zones["p1:library"] if s.state.cards[c].name == "Forest"][:lands]:
        act(s, "p1", type="move", card_ids=[c], to={"player": "p1", "zone": "battlefield"})
    return s


def gain_life(s):
    to_hand(s, "Revitalize")
    mana(s, W=1, C=1)
    cast(s, "Revitalize")


def test_ocelot_pride_with_the_citys_blessing_copies_the_cat_it_just_made(cards):
    s = pride_table(cards, 8)  # nine permanents: the Cat is the tenth
    gain_life(s)
    to_phase(s, "end")
    settle(s)
    assert len(cats(s)) == 2 and s.state.players["p1"].city_blessing
    check(s)


def test_ocelot_pride_without_the_blessing_makes_one_cat(cards):
    s = pride_table(cards, 3)
    gain_life(s)
    to_phase(s, "end")
    settle(s)
    assert len(cats(s)) == 1 and not s.state.players["p1"].city_blessing
    check(s)


def test_ocelot_pride_does_nothing_when_you_gained_no_life(cards):
    s = pride_table(cards, 8)
    to_phase(s, "end")
    settle(s)
    assert not cats(s)
    check(s)


def test_ocelot_pride_does_not_copy_a_token_from_an_earlier_turn(cards):
    s = pride_table(cards, 8)
    act(s, "p1", type="create_token", player="p1", token={"name": "Spirit", "power": "1", "toughness": "1", "type_line": "Token Creature — Spirit"})
    to_phase(s, "main1", turn=s.state.turn.number + 2)  # Alice's next turn: the Spirit has been there since the turn began
    gain_life(s)
    to_phase(s, "end")
    settle(s)
    assert len(cats(s)) == 2  # the Cat and its copy; the Spirit that entered last turn is not copied
    assert sum(1 for c in s.state.zones["p1:battlefield"] if s.state.cards[c].name == "Spirit") == 1
    check(s)


# ---- Westvale Abbey [1500] -------------------------------------------------------------------------------------------------------------------------------
def test_westvale_abbey_transforms_and_untaps_itself_after_sacrificing_five_creatures(cards):
    # 701.28: "{5}, {T}, Sacrifice five creatures: Transform this land, then untap it." - "it" is the same permanent (a transformed permanent is not a new object)
    s = build(cards, ["Westvale Abbey // Ormendahl, Profane Prince"], [])
    abbey = put(s, "Westvale Abbey // Ormendahl, Profane Prince")
    for i in range(5):
        act(s, "p1", type="create_token", player="p1", token={"name": f"Walker {i}", "power": "1", "toughness": "1", "type_line": "Token Creature — Spirit"})
    mana(s, C=5)
    activate(s, "p1", abbey, "Sacrifice five creatures")
    settle(s)
    now = s.state.cards[abbey.id]
    assert now.face == 1 and not now.tapped and now.zone == "p1:battlefield"
    assert not [c for c in s.state.zones["p1:battlefield"] if s.state.cards[c].name.startswith("Walker")]
    check(s)

"""Wave 50I: more modal cards that were not FULL because of one mode or the header (CR 2026-09-25), real Oracle text
(tests/fixtures/wave50i_cards.json, from data/cards.sqlite). Every scenario checks the replay and a save and a load.

* 701.23 / 608.2c: "Search your library for a creature or land card and reveal it. Put it onto the battlefield tapped if it's a land card. Otherwise,
  put it into your hand." (Archdruid's Charm): the card found goes where its kind says.
* 700.2a / 608.2b: "Destroy target creature with mana value less than or equal to the number of cards in its controller's graveyard." (Drown in the Loch).
* 118.12a / 107.3a: "Counter target spell unless its controller pays twice {X}." (Thassa's Intervention).
* 700.2d / ruling 2024-07-26: the Seasons, "Choose up to five {P} worth of modes. You may choose the same mode more than once.": the pawprints only bound the
  choice; each time a mode is chosen it has its own target; the modes are followed in the order written.
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from tests.game_helpers import act
from tests.test_rules_wave33b_modal import settle
from tests.test_rules_wave50i_modal_modes import cards, until_decision  # noqa: F401
from tests.wave9c_kit import build, card_named, check, life, mana, put, reloaded, to_hand, zone_of

# --- Archdruid's Charm: the destination depends on the kind of card found ---------------------------------------------------------------


@pytest.mark.parametrize(("pick", "land"), [("Forest", True), ("Grizzly Bears", False)])
def test_archdruid_s_charm_search_puts_a_land_onto_the_battlefield_tapped_and_a_creature_into_the_hand(cards, pick, land):
    s = build(cards, ["Archdruid's Charm", "Grizzly Bears"], forests=30)
    to_hand(s, "Archdruid's Charm")
    mana(s, G=3)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Archdruid's Charm").id, modes=[0])
    d = until_decision(s)
    assert d is not None and {o.label for o in d.options} == {"Forest", "Grizzly Bears"}  # (a creature or land card)
    found = next(o.card_id for o in d.options if o.label == pick)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[found])
    settle(s)
    c = s.state.cards[found]
    assert (c.zone, c.tapped) == (("p1:battlefield", True) if land else ("p1:hand", False))
    check(s)
    check(reloaded(s))


# --- Drown in the Loch: mana value against the cards in its controller's graveyard --------------------------------------------------------


def test_drown_in_the_loch_destroys_only_a_creature_within_its_controller_s_graveyard_count(cards):
    s = build(cards, ["Drown in the Loch"], ["Grizzly Bears"], forests=30)
    bears = put(s, "Grizzly Bears", "p2")  # mana value 2
    to_hand(s, "Drown in the Loch")
    mana(s, U=1, B=1)
    spell = card_named(s, "Drown in the Loch")
    act(s, "p2", type="move", card_ids=[s.state.zones["p2:library"][0]], to={"player": "p2", "zone": "graveyard"})
    with pytest.raises(ActionError, match="legal target"):
        act(s, "p1", type="cast_spell", card_id=spell.id, modes=[1], targets=[bears.id])  # one card in their graveyard: 2 > 1
    act(s, "p2", type="move", card_ids=[s.state.zones["p2:library"][0]], to={"player": "p2", "zone": "graveyard"})
    act(s, "p1", type="cast_spell", card_id=spell.id, modes=[1], targets=[bears.id])  # two cards: 2 <= 2
    settle(s)
    assert zone_of(s, "Grizzly Bears", "p2") == "p2:graveyard"
    check(s)
    check(reloaded(s))


# --- Thassa's Intervention: "unless its controller pays twice {X}" --------------------------------------------------------------------------


@pytest.mark.parametrize("paid", [True, False])
def test_thassa_s_intervention_counter_unless_its_controller_pays_twice_x(cards, paid):
    s = build(cards, ["Lightning Bolt"], ["Thassa's Intervention"], forests=30)
    bolt, counter = to_hand(s, "Lightning Bolt"), to_hand(s, "Thassa's Intervention", "p2")
    act(s, "p2", type="set_prefs", response="on")
    mana(s, "p2", U=2, C=1)
    mana(s, R=1, C=2)  # (what Alice has left to pay with)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])
    if s.state.rules.priority == "p1":
        act(s, "p1", type="pass_priority")
    act(s, "p2", type="cast_spell", card_id=counter.id, modes=[1], targets=[bolt.id], x_value=1)
    d = until_decision(s)
    assert d is not None and d.player == "p1" and [o.id for o in d.options] == ["pay", "decline"] and "{2}" in d.options[0].label  # (twice X = 1)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["pay" if paid else "decline"])
    settle(s)
    assert (life(s, "p2"), zone_of(s, "Lightning Bolt")) == ((37, "p1:graveyard") if paid else (40, "p1:graveyard"))
    check(s)
    check(reloaded(s))


# --- the Seasons: "Choose up to five {P} worth of modes. You may choose the same mode more than once." ------------------------------------


def test_season_of_loss_modes_up_to_five_pawprints_and_the_same_mode_twice(cards):
    s = build(cards, ["Season of Loss", "Grizzly Bears", "Young Wolf"], ["Grizzly Bears"], forests=30)
    put(s, "Grizzly Bears")
    put(s, "Young Wolf")
    put(s, "Grizzly Bears", "p2")
    to_hand(s, "Season of Loss")
    mana(s, B=2, G=3)
    spell = card_named(s, "Season of Loss")
    with pytest.raises(ActionError, match="more than 5 pawprints"):
        act(s, "p1", type="cast_spell", card_id=spell.id, modes=[2, 2])  # three and three
    act(s, "p1", type="cast_spell", card_id=spell.id, modes=[0, 0, 2])  # one, one and three: five
    settle(s)
    assert life(s, "p2") == 40 - 2  # (both of Alice's creature cards went to her graveyard: X = 2)
    assert zone_of(s, "Grizzly Bears", "p2") == "p2:graveyard"
    check(s)
    check(reloaded(s))


def test_season_of_the_burrow_chooses_a_target_each_time_a_mode_is_chosen(cards):
    s = build(cards, ["Season of the Burrow"], ["Grizzly Bears", "Young Wolf"], forests=30)
    a, b = put(s, "Grizzly Bears", "p2"), put(s, "Young Wolf", "p2")
    to_hand(s, "Season of the Burrow")
    mana(s, W=2, G=3)
    hand = len(s.state.zones["p2:hand"])
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Season of the Burrow").id, modes=[1, 1], targets=[a.id, b.id])
    settle(s)
    assert zone_of(s, "Grizzly Bears", "p2") == zone_of(s, "Young Wolf", "p2") == "p2:exile" and len(s.state.zones["p2:hand"]) == hand + 2
    check(s)
    check(reloaded(s))


def test_season_of_weaving_copies_a_creature_after_drawing(cards):
    s = build(cards, ["Season of Weaving", "Grizzly Bears"], forests=30)
    put(s, "Grizzly Bears")
    to_hand(s, "Season of Weaving")
    mana(s, U=2, G=4)
    hand = len(s.state.zones["p1:hand"])
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Season of Weaving").id, modes=[0, 0, 1])
    for _ in range(10):
        d = until_decision(s)
        if d is None:
            break
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[d.options[0].id])  # (the creature to copy)
    assert len(s.state.zones["p1:hand"]) == hand - 1 + 2  # (the Season left the hand; two cards drawn)
    assert sum(c.name == "Grizzly Bears" and c.zone == "p1:battlefield" for c in s.state.cards.values()) == 2
    check(s)
    check(reloaded(s))

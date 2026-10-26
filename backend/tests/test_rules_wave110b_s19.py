"""Wave 110B session 19: single cards (real Oracle text in tests/fixtures/wave110b_cards.json).

* Genesis of the Daleks: 701.55a a targeted opponent faces a villainous choice; option one destroys the Daleks and the opponents lose life equal to the total power of
  the Daleks that died this turn (608.2h, as they last existed), option two destroys the non-Daleks. 714.2 chapter IV after three Dalek makers.
* Dr. Eggman: 701.55a the opponent discards, or its controller may put a Construct, Robot or Vehicle card from their hand onto the battlefield (they may also decline, 603.5).
* Market Gnome: 702.167a, 603.10a exiled from the battlefield as a craft cost is paid (its own or another card's materials), not when it is exiled otherwise.
"""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_wave30m_durations import to_phase
from tests.wave110b_kit import build, card_named, cast, check, drive, life, mana, put, repository, to_hand, zone_of

IDOL = "Idol of the Deep King // Sovereign's Macuahuitl"


@pytest.fixture()
def cards(settings):
    yield from repository(settings)


@pytest.mark.parametrize("name", ["Genesis of the Daleks", "Dr. Eggman", "Market Gnome"])
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def choice(option):
    """Answer the villainous choice with ``option`` ("a" or "b"); anything else takes the first option."""
    return lambda d: [option] if d.kind == "choose_one" and "villainous" in d.prompt else None


def genesis_to_chapter_four(cards, bears=False):
    s = build(cards, ["Genesis of the Daleks"], ["Grizzly Bears"] if bears else [], forests=30, islands=40)
    mana(s, B=2, C=4)
    cast(s, "Genesis of the Daleks")
    for turn in (3, 5):
        to_phase(s, "main1", turn=turn)
    if bears:
        put(s, "Grizzly Bears", "p2")
    to_phase(s, "main2", turn=6)
    return s


@pytest.mark.parametrize(("option", "opp_life", "daleks_left"), [("a", 40 - 18, 0), ("b", 40, 6)])
def test_genesis_chapter_four_villainous_choice(cards, option, opp_life, daleks_left):
    s = genesis_to_chapter_four(cards, bears=True)
    assert sum(1 for c in s.state.cards.values() if c.name == "Dalek" and c.zone == "p1:battlefield") == 6  # 1 + 2 + 3 tokens (chapters I-III)
    for _ in range(10):  # on to Alice's next precombat main phase: the chapter IV trigger asks Bob
        if s.state.rules.decision is not None:
            break
        act(s, s.state.rules.priority, type="pass_priority")
    drive(s, choice(option))
    assert life(s, "p2") == opp_life
    assert sum(1 for c in s.state.cards.values() if c.name == "Dalek" and c.zone == "p1:battlefield") == daleks_left
    assert zone_of(s, "Grizzly Bears", "p2") == ("p2:battlefield" if option == "a" else "p2:graveyard")
    check(s)


@pytest.mark.parametrize(("option", "discarded", "copter_on_table"), [("a", True, False), ("b", False, True), ("c", False, False)])
def test_dr_eggman_end_step(cards, option, discarded, copter_on_table):
    s = build(cards, ["Dr. Eggman", "Smuggler's Copter"], ["Grizzly Bears"], forests=30)
    put(s, "Dr. Eggman")
    to_hand(s, "Smuggler's Copter")
    to_hand(s, "Grizzly Bears", "p2")
    to_phase(s, "main2", turn=1)
    for _ in range(6):
        if s.state.rules.decision is not None:
            break
        act(s, s.state.rules.priority, type="pass_priority")

    def answer(d):
        if d.kind == "choose_one" and "villainous" in d.prompt:
            return ["a" if option == "a" else "b"]
        if d.kind == "choose_cards":  # "you may put …": the card, or nothing (603.5)
            return [d.options[0].id] if option == "b" else []
        return None

    for _ in range(40):  # (drive() reads an empty answer as the first option: the decline is sent by hand)
        d = s.state.rules.decision
        if d is None:
            break
        ids = answer(d)
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][:1] if ids is None else ids)
    assert (zone_of(s, "Grizzly Bears", "p2") == "p2:graveyard") is discarded
    assert (zone_of(s, "Smuggler's Copter") == "p1:battlefield") is copter_on_table
    check(s)


@pytest.mark.parametrize("craft", [True, False])
def test_market_gnome_only_when_exiled_for_a_craft_cost(cards, craft):
    s = build(cards, ["Market Gnome", IDOL], [], forests=30)
    gnome = put(s, "Market Gnome")
    idol = put(s, IDOL)
    hand0, life0 = sum(1 for c in s.state.cards.values() if c.zone == "p1:hand"), life(s, "p1")
    if craft:
        mana(s, R=1, C=2)
        act(s, "p1", type="activate_ability", card_id=idol.id, ability=2, cost_choices=[{"component": 2, "cards": [gnome.id]}])
    else:
        act(s, "p1", type="move", card_ids=[gnome.id], to={"zone": "exile"})
    drive(s)
    assert zone_of(s, "Market Gnome") == "p1:exile"
    assert (life(s, "p1") == life0 + 1) is craft and (sum(1 for c in s.state.cards.values() if c.zone == "p1:hand") == hand0 + 1) is craft
    check(s)

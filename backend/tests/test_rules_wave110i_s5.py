"""Wave 110I (session 5): real Oracle text (tests/fixtures/wave110i_s5_cards.json, from data/cards.sqlite); each scenario checks replay and save/load.

* Neglected Heirloom: transforms when the creature it equips transforms (701.28, 603.2).
* Thranduil's Decree: a countered permanent spell is exiled and castable free while it stays there; any other spell goes to the graveyard (608.2c, 110.4).
* The War Games: every token made is goaded by the Saga's controller (701.15a) for as long as the Saga remains on the battlefield (611.2b).
* Nezumi Shortfang: the "if" asks about the one target opponent's hand after the discard (608.2c); Stabwhisker loses 1 life per card under three (710).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.game.errors import ActionError
from app.rules import coverage
from tests.fixtures.cards import card
from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import real
from tests.test_rules_wave34b_activated import activate, attach, to_phase
from tests.wave9c_kit import card_named, check, life, mana, put, to_hand
from tests.wave52a_kit import build_n
from tests.wave110a_kit import next_turn
from tests.wave110c_kit import answer, cast, make_db

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave110i_s5_cards.json").read_text())
EXTRA = [card(c["name"], set_code="w110i", number=f"S{i:03d}", **{k: v for k, v in c.items() if k != "name"}) for i, c in enumerate(DATA)]
EXTRA.append(real("Naturalize", "{1}{G}", 2, "Instant", "Destroy target artifact or enchantment.", None, "G"))
HEIRLOOM, SCHOLAR = "Neglected Heirloom // Ashmouth Blade", "Civilized Scholar // Homicidal Brute"
SHORTFANG = "Nezumi Shortfang // Stabwhisker the Odious"


@pytest.fixture()
def card_db(settings):
    return make_db(settings, EXTRA)


@pytest.mark.parametrize("name", [c["name"] for c in DATA])
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def set_hand(s, n):
    """Bob's hand is exactly n cards (the top of his library, one move each)."""
    for h in list(s.state.zones["p2:hand"]):
        act(s, "p2", type="move", card_ids=[h], to={"zone": "graveyard"})
    for cid in list(s.state.zones["p2:library"])[:n]:
        act(s, "p2", type="move", card_ids=[cid], to={"player": "p2", "zone": "hand"})


@pytest.mark.parametrize("hand", [1, 2])
def test_shortfang_flips_only_when_the_hand_is_empty_after_the_discard(cards, hand):
    s = build_n(cards, [SHORTFANG], islands=40)
    sf = put(s, SHORTFANG)
    next_turn(s)
    set_hand(s, hand)
    mana(s, B=1, C=1)
    activate(s, "p1", s.state.cards[sf.id], "discards")
    answer(s)
    assert s.state.cards[sf.id].flipped is (hand == 1)
    check(s)


@pytest.mark.parametrize("hand,lost", [(0, 3), (1, 2), (2, 1), (3, 0), (5, 0)])
def test_stabwhisker_drains_one_per_card_under_three(cards, hand, lost):
    s = build_n(cards, [SHORTFANG], islands=40)
    sf = put(s, SHORTFANG)
    next_turn(s)
    set_hand(s, 1)
    mana(s, B=1, C=1)
    activate(s, "p1", s.state.cards[sf.id], "discards")
    answer(s)
    assert s.state.cards[sf.id].flipped
    set_hand(s, hand)
    to_phase(s, "main1", turn=s.state.turn.number + 1)
    assert life(s, "p2") == 40 - lost and life(s, "p1") == 40
    check(s)


@pytest.mark.parametrize("equipped", [True, False])
def test_neglected_heirloom_transforms_with_its_equipped_creature(cards, equipped):
    s = build_n(cards, [HEIRLOOM, SCHOLAR, "Grizzly Bears"], islands=40)
    gear, scholar = put(s, HEIRLOOM), put(s, SCHOLAR)
    if equipped:
        attach(s, gear, scholar)
    next_turn(s)
    bears = to_hand(s, "Grizzly Bears")
    activate(s, "p1", s.state.cards[scholar.id], "Draw")
    answer(s, bears.id)  # discard the creature card: it untaps and transforms (701.28)
    assert s.state.cards[scholar.id].face == 1
    assert s.state.cards[gear.id].face == (1 if equipped else 0)
    check(s)


@pytest.mark.parametrize("spell,exiled", [("Grizzly Bears", True), ("Lightning Bolt", False)])
def test_thranduils_decree_exiles_only_a_countered_permanent_spell(cards, spell, exiled):
    s = build_n(cards, ["Thranduil's Decree", spell], islands=40)
    first, decree = to_hand(s, spell), to_hand(s, "Thranduil's Decree")
    mana(s, G=1, U=4, R=1, C=2)
    act(s, "p1", type="set_prefs", hold_priority=True)
    act(s, "p1", type="cast_spell", card_id=first.id, **({"targets": ["p2"]} if spell == "Lightning Bolt" else {}))
    act(s, "p1", type="cast_spell", card_id=decree.id, targets=[first.id])
    answer(s, *(["yes"] * exiled))  # (the free cast is a "may")
    assert s.state.cards[first.id].zone == ("p1:exile" if exiled else "p1:graveyard")
    if exiled:
        act(s, "p1", type="cast_spell", card_id=first.id, free=True)
        answer(s)
        assert s.state.cards[first.id].zone == "p1:battlefield"
    else:
        with pytest.raises(ActionError):
            act(s, "p1", type="cast_spell", card_id=first.id, targets=["p2"], free=True)
    check(s)


@pytest.mark.parametrize("leaves", [False, True])
def test_the_war_games_tokens_stay_goaded_only_while_the_saga_remains(cards, leaves):
    from app.rules.keyword_actions import goaded_by
    from app.rules.plan import Plan

    s = build_n(cards, ["The War Games", "Naturalize"], islands=40)
    mana(s, W=3, C=4)
    cast(s, "The War Games")
    answer(s)
    saga = card_named(s, "The War Games")
    warriors = [c for c in s.state.cards.values() if c.name == "Warrior" and c.zone.endswith(":battlefield")]
    assert sorted(c.controller for c in warriors) == ["p1"] * 3 + ["p2"] * 3
    if leaves:
        mana(s, G=1, C=1)
        cast(s, "Naturalize", [saga.id])
        answer(s)
    plan = Plan(s.state, "p1", cards, None)
    assert all(goaded_by(plan.ch(c)) == (set() if leaves else {"p1"}) for c in warriors)
    check(s)

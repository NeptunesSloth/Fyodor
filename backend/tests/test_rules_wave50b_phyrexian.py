"""Wave 50B: Phyrexian mana is the payer's choice (CR 2026-09-25), real Oracle text (tests/fixtures/wave50b_phyrexian_cards.json, from data/cards.sqlite).
Every scenario checks the replay and a save and a load.

* 107.4f: "A Phyrexian mana symbol represents a cost that can be paid either with one mana of its color or by paying 2 life."
* 601.2b: "If a cost that will be paid as the spell is being cast includes Phyrexian mana symbols, the player announces whether they intend to pay 2 life
  or a corresponding colored mana cost for each of those symbols." The solver used to pay life only where mana fell short; now the payer is asked
  whenever more than one way can be paid (and an ability's cost, 602.2b, likewise).
* 702.150a: a compleated planeswalker enters with two fewer loyalty counters for each Phyrexian symbol paid with life.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.importer import build_database
from app.game.errors import ActionError
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditionals import creature, settle
from tests.wave9c_kit import build, card_named, check, life, mana, put, reloaded, to_hand

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave50b_phyrexian_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="t50b", number=f"P{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]


@pytest.fixture()
def card_db(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def pending(s):
    d = s.state.rules.decision
    assert d is not None, "nothing was asked"
    return d


def pick(s, option):
    d = pending(s)
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[option])


def pool(s, pid="p1"):
    return {k: v for k, v in s.state.players[pid].mana.items() if v}


def loyalty(s, name):
    return s.state.cards[card_named(s, name).id].counters.get("loyalty", 0)


def test_dismember_asks_for_each_symbol(cards):
    s = build(cards, ["Dismember"])
    spell = to_hand(s, "Dismember")
    victim = creature(s, "p2", "Bob Bear")
    mana(s, B=2, C=1)
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=[victim.id])
    d = pending(s)
    assert d.kind == "choose_one" and d.player == "p1"
    assert [o.label for o in d.options] == ["{B/P}: {B}, {B/P}: {B}", "{B/P}: 2 life, {B/P}: {B}", "{B/P}: 2 life, {B/P}: 2 life"]
    assert s.state.cards[spell.id].zone == "p1:hand" and life(s) == 40 and pool(s) == {"B": 2, "C": 1}  # (nothing moved while asked)
    check(s)  # the question survives the replay and a save and a load
    s = reloaded(s)
    pick(s, "0")  # mana for both
    settle(s)
    assert life(s) == 40 and pool(s) == {} and victim.id not in s.state.cards  # (the 2/2 token died)
    check(s)


@pytest.mark.parametrize(("option", "left_life", "left_pool"), [("1", 38, {"B": 1}), ("2", 36, {"B": 2})])
def test_dismember_paid_with_life_where_the_payer_chooses_it(cards, option, left_life, left_pool):
    s = build(cards, ["Dismember"])
    spell = to_hand(s, "Dismember")
    victim = creature(s, "p2", "Bob Bear")
    mana(s, B=2, C=1)
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=[victim.id])
    pick(s, option)
    settle(s)
    assert life(s) == left_life and pool(s) == left_pool  # the mana the payer did not choose to spend stays in the pool
    assert victim.id not in s.state.cards  # (the 2/2 token died)
    check(s)


def test_the_only_way_to_pay_is_not_asked(cards):
    s = build(cards, ["Gut Shot"])
    shot = to_hand(s, "Gut Shot")
    act(s, "p1", type="cast_spell", card_id=shot.id, targets=["p2"])  # no mana: 2 life, nothing to choose
    assert s.state.rules.decision is None and life(s) == 38
    s = build(cards, ["Gut Shot"])
    shot = to_hand(s, "Gut Shot")
    mana(s, R=1)
    act(s, "p1", type="set_life", player="p1", value=1)  # one life can't pay 2: mana is the only way
    act(s, "p1", type="cast_spell", card_id=shot.id, targets=["p2"])
    assert s.state.rules.decision is None and life(s) == 1 and pool(s) == {}
    check(s)


def test_cancelling_the_question_pays_nothing(cards):
    s = build(cards, ["Gut Shot"])
    shot = to_hand(s, "Gut Shot")
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=shot.id, targets=["p2"])
    pick(s, "cancel")
    assert s.state.rules.decision is None and s.state.cards[shot.id].zone == "p1:hand" and life(s) == 40 and pool(s) == {"R": 1}
    check(s)


def test_the_announcement_can_be_given_up_front_and_is_checked(cards):
    s = build(cards, ["Dismember"])
    spell = to_hand(s, "Dismember")
    victim = creature(s, "p2", "Bob Bear")
    mana(s, B=2, C=1)
    for bad in (["R"], ["B", "B", "B"]):  # not symbols of the cost
        with pytest.raises(ActionError, match="Phyrexian"):
            act(s, "p1", type="cast_spell", card_id=spell.id, targets=[victim.id], life_symbols=bad)
    assert s.state.cards[spell.id].zone == "p1:hand" and life(s) == 40 and pool(s) == {"B": 2, "C": 1}
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=[victim.id], life_symbols=["B"])
    assert s.state.rules.decision is None and life(s) == 38 and pool(s) == {"B": 1}
    check(s)
    s = build(cards, ["Gut Shot"])
    shot = to_hand(s, "Gut Shot")
    act(s, "p1", type="set_life", player="p1", value=1)
    with pytest.raises(ActionError, match="can't be paid"):
        act(s, "p1", type="cast_spell", card_id=shot.id, targets=["p2"], life_symbols=["R"])  # 119.4: one life can't pay 2
    assert life(s) == 1 and s.state.cards[shot.id].zone == "p1:hand"


def test_ajani_loyalty_follows_the_life_choice(cards):
    # {1}{G}{G/W/P}{W}: with {1}{G}{G}{W} in the pool both ways can be paid (compleated, 702.150a: two fewer loyalty counters for 2 life)
    for option, counters, left in (("0", 4, 40), ("1", 2, 38)):
        s = build(cards, ["Ajani, Sleeper Agent"])
        spell = to_hand(s, "Ajani, Sleeper Agent")
        mana(s, G=2, W=1, C=1)
        act(s, "p1", type="cast_spell", card_id=spell.id)
        assert [o.label for o in pending(s).options] == ["{G/W/P}: {G} or {W}", "{G/W/P}: 2 life"]
        pick(s, option)
        settle(s)
        assert loyalty(s, "Ajani, Sleeper Agent") == counters and life(s) == left
        check(s)
        s = reloaded(s)
        assert loyalty(s, "Ajani, Sleeper Agent") == counters  # the counters are on the permanent


def test_an_ability_cost_asks_too(cards):
    s = build(cards, ["Mutagenic Growth"], ["Spellskite"])
    act(s, "p2", type="set_prefs", response="on")  # (Bob gets priority to respond)
    skite = put(s, "Spellskite", "p2")
    growth = to_hand(s, "Mutagenic Growth")
    own = creature(s, "p1", "Own Bear")
    mana(s, G=1)
    act(s, "p1", type="cast_spell", card_id=growth.id, targets=[own.id], life_symbols=[])
    if s.state.rules.priority == "p1":
        act(s, "p1", type="pass_priority")  # Bob may respond
    mana(s, "p2", U=1)
    act(s, "p2", type="activate_ability", card_id=skite.id, ability=0, targets=[growth.id])
    d = pending(s)
    assert d.player == "p2" and [o.label for o in d.options] == ["{U/P}: {U}", "{U/P}: 2 life"]
    assert s.state.cards[growth.id].zone == "stack" and pool(s, "p2") == {"U": 1}
    check(s)
    pick(s, "1")
    assert life(s, "p2") == 38 and pool(s, "p2") == {"U": 1}  # 2 life paid, the {U} stays
    check(s)


def test_a_player_who_taps_their_own_mana_is_asked_before_the_tap_prompt(cards):
    for option, tapped in (("0", True), ("1", False)):
        s = build(cards, ["Mutagenic Growth"])
        for prefs in s.state.rules.prefs.values():
            prefs.payment = "self"
        growth = to_hand(s, "Mutagenic Growth")
        forest = put(s, "Forest")
        victim = creature(s, "p1", "Own Bear")
        act(s, "p1", type="cast_spell", card_id=growth.id, targets=[victim.id])
        assert [o.label for o in pending(s).options] == ["{G/P}: {G}", "{G/P}: 2 life"]
        pick(s, option)
        if tapped:  # mana: the "tap your mana" prompt opens for {G}; life: nothing to tap
            assert pending(s).display["kind"] == "tap_mana" and pending(s).display["cost"] == "{G}"
            act(s, "p1", type="activate_ability", card_id=forest.id, ability=0)
        assert s.state.cards[growth.id].zone in ("stack", "p1:graveyard") and s.state.cards[forest.id].tapped is tapped
        assert life(s) == (40 if tapped else 38)
        check(s)


@pytest.mark.parametrize("mode", ["ask", "manual"])
def test_the_announced_cost_is_what_the_payment_prompts_show(cards, mode):
    s = build(cards, ["Mutagenic Growth"])
    for prefs in s.state.rules.prefs.values():
        prefs.payment = mode
    growth = to_hand(s, "Mutagenic Growth")
    forest = put(s, "Forest")
    victim = creature(s, "p1", "Own Bear")
    act(s, "p1", type="cast_spell", card_id=growth.id, targets=[victim.id])
    pick(s, "0")  # {G} rather than 2 life
    d = pending(s)
    assert d.resume["cost"] == "{G}"  # the cost asked for is the announced one, not {G/P}
    if mode == "ask":
        assert d.resume["step"] == "payment" and d.display["suggested"] == [forest.id]
        pick(s, "pay")
    else:
        assert d.resume["step"] == "payment_sources"
        pick(s, forest.id)
    assert s.state.cards[forest.id].tapped and life(s) == 40
    check(s)

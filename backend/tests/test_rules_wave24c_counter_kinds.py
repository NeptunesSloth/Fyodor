"""Wave 24C: counter kinds (CR 122.1, 122.5, 122.6, 122.8, 608.2d) — "for each kind of counter on …", "choose a counter on …" and "any number
of counters" (app/rules/counter_kinds.py, counter_moves.py).

Every scenario uses real Oracle text (tests/fixtures/wave24c_cards.json, from data/cards.sqlite), checks that replaying the recorded history
reproduces the table and that a save/load round trip keeps it."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditionals import counters, settle, token_of
from tests.test_rules_wave7b_activation import ability_index
from tests.wave9c_kit import build, check, mana, put, to_hand

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave24c_cards.json").read_text("utf-8"))
EXTRA = [card(c["name"], set_code="t24c", number=f"C{i:02d}", **{k: v for k, v in c.items() if k != "name"}) for i, c in enumerate(DATA)]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def answer(s, *picks, limit=30):
    """Resolve the stack; decisions are answered from ``picks`` in turn (else with their first option)."""
    picks = list(picks)
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None:
            pick = picks.pop(0) if picks else None
            ids = [pick] if isinstance(pick, str) else pick or [o.id for o in d.options][: max(1, d.min_choices)]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=ids)
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            assert not picks, f"unused answers {picks}"
            return
    raise AssertionError("the stack never emptied")


def unready(s, *cs):
    for c in cs:
        s.state.rules.controlled_since[c.id].turn = 0


@pytest.mark.parametrize("name", [c["name"] for c in DATA])
def test_the_promoted_cards_are_full(name):
    c = next(c for c in EXTRA if c["name"] == name)
    assert coverage.of_card_data({**c, "faces": c.get("card_faces") or []}).level == "FULL", name


def test_the_unread_forms_stay_manual():
    from tests.test_rules_scripts import ch

    for text in (  # a counter kind named for each of two groups, a kind chosen on a creature then given to "each other creature"
        "Choose a kind of counter on a creature you control. Put a counter of that kind on each other creature you control.",
        "{T}: For each kind of counter on target permanent or player, give that permanent or player two counters of that kind.",
    ):
        assert coverage.of_characteristics(ch("T", "Artifact", text)).level != "FULL"


# -- "for each kind of counter on …, give … another counter of that kind" -------------------------------------------------------------
def test_powerful_broker_gives_one_more_of_every_kind(cards):
    s = build(cards, ["Powerful Broker"], [])
    broker = put(s, "Powerful Broker")
    unready(s, broker)
    bear = token_of(s, "p2", "Bob Bear", "Creature — Bear", "2/2")
    act(s, "p1", type="counter", card_ids=[bear.id], kind="+1/+1", delta=2)
    act(s, "p1", type="counter", card_ids=[bear.id], kind="charge", delta=1)
    act(s, "p1", type="activate_ability", card_id=broker.id, ability=ability_index(s, broker, "For each kind"), targets=[bear.id], target_counts=[1])
    answer(s)
    assert (counters(s, bear), counters(s, bear, "charge")) == (3, 2)  # one more of each kind it had, not of kinds it lacked
    assert counters(s, bear, "flying") == 0
    check(s)


def test_the_kinds_are_read_as_it_resolves_a_player_is_a_target(cards):
    s = build(cards, ["Powerful Broker"], [])
    broker = put(s, "Powerful Broker")
    unready(s, broker)
    act(s, "p2", type="set_resource", player="p2", key="poison", value=2)
    act(s, "p1", type="activate_ability", card_id=broker.id, ability=ability_index(s, broker, "For each kind"), targets=["p2"], target_counts=[1])
    answer(s)
    assert s.state.players["p2"].resources["poison"] == 3  # 122.1c: poison is a kind of counter too
    check(s)


def test_a_target_with_no_counters_gets_nothing(cards):
    s = build(cards, ["Powerful Broker"], [])
    broker = put(s, "Powerful Broker")
    unready(s, broker)
    bear = token_of(s, "p2", "Bob Bear", "Creature — Bear", "2/2")
    act(s, "p1", type="activate_ability", card_id=broker.id, ability=ability_index(s, broker, "For each kind"), targets=[bear.id], target_counts=[1])
    answer(s)
    assert s.state.cards[bear.id].counters == {} or not any(s.state.cards[bear.id].counters.values())
    check(s)


def test_maulfist_revolutionary_triggers_on_entering(cards):
    s = build(cards, ["Maulfist Revolutionary"], [])
    bear = token_of(s, "p1", "Mine", "Creature — Bear", "2/2")
    act(s, "p1", type="counter", card_ids=[bear.id], kind="+1/+1", delta=1)
    c = to_hand(s, "Maulfist Revolutionary")
    mana(s, "p1", G=3)
    act(s, "p1", type="cast_spell", card_id=c.id)
    answer(s, bear.id)
    assert counters(s, bear) == 2
    check(s)


# -- the counter choke point: Hardened Scales makes the +1/+1 put one larger (122.6, 614.1) ----------------------------------------------
def test_the_gives_go_through_the_counter_choke_point(cards):
    s = build(cards, ["Powerful Broker", "Hardened Scales"], [])
    broker = put(s, "Powerful Broker")
    put(s, "Hardened Scales")
    unready(s, broker)
    bear = token_of(s, "p1", "Mine", "Creature — Bear", "2/2")
    act(s, "p1", type="counter", card_ids=[bear.id], kind="+1/+1", delta=1)
    act(s, "p1", type="counter", card_ids=[bear.id], kind="charge", delta=1)
    act(s, "p1", type="activate_ability", card_id=broker.id, ability=ability_index(s, broker, "For each kind"), targets=[bear.id], target_counts=[1])
    answer(s)
    assert (counters(s, bear), counters(s, bear, "charge")) == (3, 2)  # one more +1/+1 plus Hardened Scales' one; the charge counter just one
    check(s)


# -- "put another counter of that kind on it or remove one from it": per kind, the controller chooses -------------------------------------
def test_dramatists_puppet_chooses_per_kind(cards):
    s = build(cards, ["Dramatist's Puppet"], [])
    bear = token_of(s, "p2", "Bob Bear", "Creature — Bear", "2/2")
    act(s, "p1", type="counter", card_ids=[bear.id], kind="+1/+1", delta=1)
    act(s, "p1", type="counter", card_ids=[bear.id], kind="charge", delta=2)
    puppet = to_hand(s, "Dramatist's Puppet")
    mana(s, "p1", C=4)
    act(s, "p1", type="cast_spell", card_id=puppet.id)
    answer(s, bear.id, "put", "remove")  # +1/+1 first (kinds in order), then charge
    assert (counters(s, bear), counters(s, bear, "charge")) == (2, 1)
    check(s)


# -- "choose a counter on …, give … another counter of that kind" ---------------------------------------------------------------------
def test_animation_module_gives_the_chosen_kind(cards):
    s = build(cards, ["Animation Module"], [])
    mod = put(s, "Animation Module")
    bear = token_of(s, "p2", "Bob Bear", "Creature — Bear", "2/2")
    act(s, "p1", type="counter", card_ids=[bear.id], kind="+1/+1", delta=1)
    act(s, "p1", type="counter", card_ids=[bear.id], kind="charge", delta=1)
    mana(s, "p1", C=3)
    act(s, "p1", type="activate_ability", card_id=mod.id, ability=ability_index(s, mod, "Choose a counter"), targets=[bear.id], target_counts=[1])
    answer(s, "charge")
    assert (counters(s, bear), counters(s, bear, "charge")) == (1, 2)
    check(s)


def test_one_kind_is_taken_without_asking(cards):
    s = build(cards, ["Animation Module"], [])
    mod = put(s, "Animation Module")
    bear = token_of(s, "p2", "Bob Bear", "Creature — Bear", "2/2")
    act(s, "p1", type="counter", card_ids=[bear.id], kind="charge", delta=1)
    mana(s, "p1", C=3)
    act(s, "p1", type="activate_ability", card_id=mod.id, ability=ability_index(s, mod, "Choose a counter"), targets=[bear.id], target_counts=[1])
    settle(s)
    assert counters(s, bear, "charge") == 2 and s.state.rules.decision is None
    check(s)


# -- "any number of counters": how many of each kind --------------------------------------------------------------------------------
def test_rhys_removes_any_number_of_each_kind(cards):
    s = build(cards, ["Rhys, the Evermore"], [])
    rhys = put(s, "Rhys, the Evermore")
    unready(s, rhys)
    bear = token_of(s, "p1", "Mine", "Creature — Bear", "2/2")
    act(s, "p1", type="counter", card_ids=[bear.id], kind="+1/+1", delta=3)
    act(s, "p1", type="counter", card_ids=[bear.id], kind="charge", delta=2)
    mana(s, "p1", W=1)
    act(s, "p1", type="activate_ability", card_id=rhys.id, ability=ability_index(s, rhys, "Remove any number"), targets=[bear.id], target_counts=[1])
    answer(s, "2", "2")  # two +1/+1 (of three), both charge counters
    assert (counters(s, bear), counters(s, bear, "charge")) == (1, 0)
    check(s)


def test_resourceful_defense_moves_the_chosen_numbers(cards):
    s = build(cards, ["Resourceful Defense"], [])
    d = put(s, "Resourceful Defense")
    a = token_of(s, "p1", "Mine A", "Creature — Bear", "2/2")
    b = token_of(s, "p1", "Mine B", "Creature — Bear", "2/2")
    act(s, "p1", type="counter", card_ids=[a.id], kind="+1/+1", delta=2)
    act(s, "p1", type="counter", card_ids=[a.id], kind="charge", delta=1)
    mana(s, "p1", W=1, C=4)
    act(s, "p1", type="activate_ability", card_id=d.id, ability=ability_index(s, d, "Move any number"), targets=[a.id, b.id], target_counts=[1, 1])
    answer(s, "1", "1")
    assert (counters(s, a), counters(s, a, "charge"), counters(s, b), counters(s, b, "charge")) == (1, 0, 1, 1)
    check(s)


# -- "Choose a counter on a permanent you control. Put a counter of that kind on target permanent you control if it doesn't have one" -----
def test_aven_courier_gives_a_kind_the_target_lacks(cards):
    s = build(cards, ["Aven Courier"], [])
    courier = put(s, "Aven Courier")
    a = token_of(s, "p1", "Mine A", "Creature — Bear", "2/2")
    b = token_of(s, "p1", "Mine B", "Creature — Bear", "2/2")
    act(s, "p1", type="counter", card_ids=[a.id], kind="charge", delta=1)
    unready(s, courier)
    from tests.test_rules_wave23c_values import attack

    attack(s, courier)
    answer(s, b.id)
    assert counters(s, b, "charge") == 1 and counters(s, a, "charge") == 1
    check(s)

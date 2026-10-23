"""Canonical upkeep player choice retains source controller targeting authority."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditionals import until
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_linked_return_family import cold_choose
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

NAMES = ["Magus of the Abyss", "The Abyss"]


@pytest.fixture()
def cards(settings):
    base = {c["name"]: c for c in fixture_cards()}
    for i, c in enumerate(
        json.loads((Path(__file__).parent / "fixtures/upkeep_target_choice65_cards.json").read_text())
    ):
        base[c["name"]] = card(
            c["name"], set_code="utc", number=str(i), **{k: v for k, v in c.items() if k != "name"}
        )
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(
    cards,
    name,
    other=(
        "Grizzly Bears",
        "Llanowar Elves",
        "Slippery Bogle",
        "Darksteel Myr",
        "Knight of Glory",
        "Sapling of Colfenor",
    ),
):
    s = table(cards, [name, "Grizzly Bears"], other, ["Grizzly Bears"])
    src = put(s, name, "battlefield")
    return s, src


def upkeep(s):
    to_phase(s, "upkeep", turn=2)
    until(s, lambda s: s.state.rules.decision is not None)
    return s.state.rules.decision


@pytest.mark.parametrize("name", NAMES)
def test_full_native_definition(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


@pytest.mark.parametrize("name", NAMES)
def test_opponent_choice_keeps_controller_and_exact_legal_options_cold(cards, name, tmp_path):
    s, src = setup(cards, name)
    bear = put(s, "Grizzly Bears", "battlefield", "p2")
    elf = put(s, "Llanowar Elves", "battlefield", "p2")
    hidden = put(s, "Slippery Bogle", "battlefield", "p2")
    artifact = put(s, "Darksteel Myr", "battlefield", "p2")
    protected = put(s, "Knight of Glory", "battlefield", "p2")
    indestructible = put(s, "Sapling of Colfenor", "battlefield", "p2")
    own = put(s, "Grizzly Bears", "battlefield")
    d = upkeep(s)
    assert d.player == "p2" and d.resume["step"] == "trigger_target"
    assert {o.id for o in d.options} == {bear.id, elf.id, indestructible.id}
    with pytest.raises(ActionError):
        act(s, "p1", type="choose", decision_id=d.id, option_ids=[bear.id])
    with pytest.raises(ActionError):
        act(s, "p2", type="choose", decision_id=d.id, option_ids=[hidden.id])
    roundtrip(s)
    s = cold_choose(s, cards, tmp_path, [bear.id])
    entries = [e for e in s.state.rules.stack.values() if e.source_card == src.id]
    assert len(entries) == 1 and entries[0].controller == "p1" and entries[0].targets[0].id == bear.id
    settle(s)
    assert s.state.cards[bear.id].zone == "p2:graveyard"
    for c in [elf, hidden, artifact, protected, indestructible]:
        assert s.state.cards[c.id].zone == "p2:battlefield"
    assert s.state.cards[own.id].zone == "p1:battlefield"
    roundtrip(s)


@pytest.mark.parametrize("name", NAMES)
def test_indestructible_is_a_legal_target_but_survives(cards, name):
    s, src = setup(cards, name)
    target = put(s, "Sapling of Colfenor", "battlefield", "p2")
    d = upkeep(s)
    assert target.id in [o.id for o in d.options]
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[target.id])
    settle(s)
    assert s.state.cards[target.id].zone == "p2:battlefield"
    roundtrip(s)


@pytest.mark.parametrize("name", NAMES)
def test_no_legal_target_drops_trigger_without_manual_decision(cards, name):
    s, src = setup(cards, name)
    put(s, "Slippery Bogle", "battlefield", "p2")
    put(s, "Darksteel Myr", "battlefield", "p2")
    to_phase(s, "upkeep", turn=2)
    settle(s)
    assert not s.state.rules.decision and not s.state.rules.stack and not s.state.rules.pending_triggers
    roundtrip(s)


@pytest.mark.parametrize("name", NAMES)
@pytest.mark.parametrize("leave_target", [False, True])
def test_source_departure_preserves_trigger_and_target_new_object_is_illegal(cards, name, leave_target):
    s, src = setup(cards, name)
    target = put(s, "Grizzly Bears", "battlefield", "p2")
    d = upkeep(s)
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[target.id])
    act(s, "p1", type="move", card_ids=[src.id], to={"player": "p1", "zone": "graveyard"})
    if leave_target:
        act(s, "p2", type="move", card_ids=[target.id], to={"player": "p2", "zone": "exile"})
        act(s, "p2", type="move", card_ids=[target.id], to={"player": "p2", "zone": "battlefield"})
    settle(s)
    assert s.state.cards[target.id].zone == ("p2:battlefield" if leave_target else "p2:graveyard")
    roundtrip(s)




@pytest.mark.parametrize("name", NAMES)
def test_no_regeneration_after_opponent_chooses(cards, name):
    from tests.test_rules_bandmate_references import mana, wait_priority

    s, src = setup(cards, name, other=["Twisted Abomination"])
    target = put(s, "Twisted Abomination", "battlefield", "p2")
    d = upkeep(s)
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[target.id])
    mana(s, "p2", B=1)
    wait_priority(s, "p2")
    act(s, "p2", type="activate_ability", card_id=target.id, ability=0)
    settle(s)
    assert s.state.cards[target.id].zone == "p2:graveyard"
    assert s.state.rules.decision is None
    roundtrip(s)


@pytest.mark.parametrize("name", NAMES)
def test_own_upkeep_target_and_magus_can_choose_itself(cards, name):
    s, src = setup(cards, name)
    own = put(s, "Grizzly Bears", "battlefield")
    to_phase(s, "upkeep", turn=4)
    until(s, lambda s: s.state.rules.decision is not None)
    d = s.state.rules.decision
    assert d.player == "p1"
    target = src if name == "Magus of the Abyss" else own
    assert target.id in [o.id for o in d.options]
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[target.id])
    settle(s)
    assert s.state.cards[target.id].zone == "p1:graveyard"
    roundtrip(s)


def test_magus_native_cast_pays_cost_then_enters_as_creature(cards):
    from tests.test_rules_bandmate_references import mana, wait_priority

    s = table(cards, ["Magus of the Abyss"], [], [])
    source = put(s, "Magus of the Abyss", "hand")
    mana(s, C=3, B=1)
    wait_priority(s, "p1")
    act(s, "p1", type="cast_spell", card_id=source.id)
    assert s.state.cards[source.id].zone == "stack"
    settle(s)
    assert s.state.cards[source.id].zone == "p1:battlefield"
    roundtrip(s)


def test_world_source_now_has_native_world_foundation(cards):
    assert coverage.of_card_data(cards.resolve("The Abyss")).level == "FULL"


@pytest.mark.parametrize('new_controller', ['p1', 'p3'])
def test_target_changing_controller_fails_bound_upkeep_player_legality(cards, new_controller):
    s, source = setup(cards, 'Magus of the Abyss')
    target = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    d = upkeep(s)
    act(s, 'p2', type='choose', decision_id=d.id, option_ids=[target.id])
    act(s, 'p1', type='set_controller', card_ids=[target.id], player=new_controller)
    settle(s)
    assert s.state.cards[target.id].zone.endswith(':battlefield')
    assert s.state.cards[source.id].zone == 'p1:battlefield'
    roundtrip(s)


@pytest.mark.parametrize('new_controller', ['p2', 'p3'])
def test_source_changing_controller_does_not_change_original_trigger_authority(cards, new_controller):
    s, source = setup(cards, 'Magus of the Abyss')
    target = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    d = upkeep(s)
    act(s, 'p2', type='choose', decision_id=d.id, option_ids=[target.id])
    act(s, 'p1', type='set_controller', card_ids=[source.id], player=new_controller)
    entry = next(e for e in s.state.rules.stack.values() if e.source_card == source.id)
    assert entry.controller == 'p1'
    settle(s)
    assert s.state.cards[target.id].zone == 'p2:graveyard'
    roundtrip(s)


def test_two_sources_keep_separate_controllers_while_active_player_chooses_both(cards):
    name = 'Magus of the Abyss'
    s = table(cards, [name], [name], ['Grizzly Bears'])
    first = put(s, name, 'battlefield')
    to_phase(s, 'main1', turn=2)
    second = put(s, name, 'battlefield', 'p2')
    target = put(s, 'Grizzly Bears', 'battlefield', 'p3')
    to_phase(s, 'upkeep', turn=3)
    for _ in range(2):
        until(s, lambda s: s.state.rules.decision is not None)
        d = s.state.rules.decision
        assert d.player == 'p3'
        act(s, 'p3', type='choose', decision_id=d.id, option_ids=[target.id])
    entries = [e for e in s.state.rules.stack.values() if e.source_card in [first.id, second.id]]
    assert {e.controller for e in entries} == {'p1', 'p2'}
    settle(s)
    assert s.state.cards[target.id].zone == 'p3:graveyard'
    roundtrip(s)


def test_own_hexproof_is_legal_for_own_source_controller(cards):
    s = table(cards, ['Magus of the Abyss', 'Slippery Bogle'], [], [])
    source = put(s, 'Magus of the Abyss', 'battlefield')
    target = put(s, 'Slippery Bogle', 'battlefield')
    to_phase(s, 'upkeep', turn=4)
    until(s, lambda s: s.state.rules.decision is not None)
    d = s.state.rules.decision
    assert d.player == 'p1' and target.id in [o.id for o in d.options]
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[target.id])
    settle(s)
    assert s.state.cards[target.id].zone == 'p1:graveyard'
    assert s.state.cards[source.id].zone == 'p1:battlefield'
    roundtrip(s)


def test_native_magus_four_three_body_fights_real_blocker(cards):
    from tests.test_rules_conditional_prevention import attack, damage

    s = table(cards, ['Magus of the Abyss', 'Grizzly Bears'], ['Grizzly Bears'], [])
    source = put(s, 'Magus of the Abyss', 'battlefield')
    victim = put(s, 'Grizzly Bears', 'battlefield')
    to_phase(s, 'upkeep', turn=4)
    until(s, lambda s: s.state.rules.decision is not None)
    d = s.state.rules.decision
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[victim.id])
    settle(s)
    blocker = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    attack(s, [source], target='p2', turn=4)
    to_phase(s, 'declare_blockers')
    act(s, 'p2', type='declare_blockers', blocks=[{'blocker_id': blocker.id, 'attacker_id': source.id}])
    damage(s)
    assert s.state.cards[blocker.id].zone == 'p2:graveyard'
    assert s.state.cards[source.id].zone == 'p1:battlefield'
    assert s.state.cards[source.id].damage == 2
    roundtrip(s)

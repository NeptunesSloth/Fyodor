"""CR 120, 614, 616: dynamic damage floors and damage-source history."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/red_source_damage_floor_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


NAME = 'Ojer Axonil, Deepest Might // Temple of Power'


def setup(cards, *, face=0):
    from tests.game_helpers import act
    from tests.test_rules_designations import put
    from tests.test_rules_shared_damage_choices import table
    s = table(cards, [NAME, 'Shock', 'Shock', 'Lightning Bolt', 'Giant Growth', 'Grizzly Bears',
                      'Torbran, Thane of Red Fell', 'Furnace of Rath', 'Murder', 'Spear Spewer', 'Earthquake',
                      'Psionic Blast', 'Thoughtlace', 'Chaoslace', 'Prodigal Pyromancer'], ['Grizzly Bears', 'Glacial Chasm'])
    source = put(s, NAME, 'battlefield')
    if face:
        act(s, 'p1', type='set_face', card_id=source.id, face=1)
    return s, source


def cast(s, name, target):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import settle
    card = next(c for c in s.state.cards.values() if c.name == name and c.owner == 'p1'
                and c.zone not in ('stack', 'p1:graveyard', 'p1:exile'))
    act(s, 'p1', type='move', card_ids=[card.id], to={'player': 'p1', 'zone': 'hand'})
    mana(s, R=5, G=5, B=5, U=5)
    act(s, 'p1', type='cast_spell', card_id=card.id, targets=[target])
    settle(s)
    return card


def test_full(cards):
    assert coverage.of_card_data(cards.resolve(NAME)).level == 'FULL'


@pytest.mark.parametrize('boost', [False, True])
def test_red_noncombat_damage_uses_current_ojer_power(cards, boost):
    from tests.test_rules_designations import roundtrip
    s, source = setup(cards)
    if boost:
        cast(s, 'Giant Growth', source.id)
    cast(s, 'Shock', 'p2')
    assert s.state.players['p2'].life == (33 if boost else 36)
    roundtrip(s)


@pytest.mark.parametrize('recipient', ['p1', 'permanent'])
def test_floor_applies_only_to_opponent_players(cards, recipient):
    from tests.test_rules_designations import put, roundtrip
    s, _ = setup(cards)
    target = put(s, 'Grizzly Bears', 'battlefield', 'p2').id if recipient == 'permanent' else recipient
    cast(s, 'Shock', target)
    assert s.state.players['p1'].life == (38 if recipient == 'p1' else 40)
    assert s.state.players['p2'].life == 40
    roundtrip(s)


@pytest.mark.parametrize('first', ['Ojer Axonil', 'Torbran'])
def test_affected_opponent_chooses_replacement_order(cards, first):
    from tests.game_helpers import act
    from tests.test_rules_designations import put, roundtrip, settle
    s, _ = setup(cards)
    put(s, 'Torbran, Thane of Red Fell', 'battlefield')
    cast(s, 'Shock', 'p2')
    d = s.state.rules.decision
    assert d is not None and d.player == 'p2' and d.resume['step'] == 'replace_order'
    roundtrip(s)
    chosen = next(o.id for o in d.options if first in o.label.split(' first')[0])
    act(s, 'p2', type='choose', decision_id=d.id, option_ids=[chosen])
    settle(s)
    assert s.state.players['p2'].life == (34 if first == 'Ojer Axonil' else 36)
    roundtrip(s)


def test_temple_aggregates_multiple_red_sources_and_permanent_recipients(cards):
    from tests.game_helpers import act
    from tests.test_rules_designations import put, roundtrip, settle
    from tests.test_rules_wave7b_activation import ability_index
    s, source = setup(cards, face=1)
    victim = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    cast(s, 'Shock', victim.id)
    cast(s, 'Shock', 'p2')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=ability_index(s, source, 'Transform this land'))
    settle(s)
    assert s.state.cards[source.id].face == 0
    roundtrip(s)


@pytest.mark.parametrize('first', ['Ojer Axonil', 'Furnace of Rath'])
def test_furnace_order_can_make_floor_inapplicable(cards, first):
    from tests.game_helpers import act
    from tests.test_rules_designations import put, roundtrip, settle
    s, _ = setup(cards)
    put(s, 'Furnace of Rath', 'battlefield')
    cast(s, 'Shock', 'p2')
    d = s.state.rules.decision
    assert d is not None and d.player == 'p2' and d.resume['step'] == 'replace_order'
    roundtrip(s)
    chosen = next(o.id for o in d.options if first in o.label.split(' first')[0])
    act(s, 'p2', type='choose', decision_id=d.id, option_ids=[chosen])
    settle(s)
    assert s.state.players['p2'].life == (32 if first == 'Ojer Axonil' else 36)
    roundtrip(s)


def test_nonred_spell_is_not_raised_to_ojer_power(cards):
    from tests.test_rules_designations import roundtrip
    s, source = setup(cards)
    cast(s, 'Giant Growth', source.id)
    cast(s, 'Psionic Blast', 'p2')
    assert s.state.players['p2'].life == 36
    assert s.state.players['p1'].life == 38
    roundtrip(s)


def test_red_zero_damage_is_not_raised_and_creates_no_damage_history(cards):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import put, roundtrip, settle
    s, _ = setup(cards)
    spell = put(s, 'Earthquake', 'hand')
    mana(s, R=1)
    act(s, 'p1', type='cast_spell', card_id=spell.id, x_value=0)
    settle(s)
    assert all(p.life == 40 for p in s.state.players.values())
    assert not any(f.kind in ('damage', 'damaged') and f.amount > 0 for f in s.state.rules.turn_log.facts)
    roundtrip(s)


def test_prevented_red_damage_does_not_unlock_temple(cards):
    from app.game.errors import ActionError
    from tests.game_helpers import act
    from tests.test_rules_designations import put, roundtrip
    from tests.test_rules_wave7b_activation import ability_index
    s, source = setup(cards, face=1)
    put(s, 'Glacial Chasm', 'battlefield', 'p2')
    cast(s, 'Lightning Bolt', 'p2')
    cast(s, 'Shock', 'p2')
    assert s.state.players['p2'].life == 40
    with pytest.raises(ActionError):
        act(s, 'p1', type='activate_ability', card_id=source.id, ability=ability_index(s, source, 'Transform this land'))
    roundtrip(s)


def test_actual_death_returns_temple_and_later_red_damage_unlocks_transform(cards):
    from tests.game_helpers import act
    from tests.test_rules_designations import roundtrip, settle
    from tests.test_rules_wave7b_activation import ability_index
    s, source = setup(cards)
    cast(s, 'Murder', source.id)
    assert s.state.cards[source.id].zone == 'p1:battlefield'
    assert s.state.cards[source.id].face == 1 and s.state.cards[source.id].tapped
    cast(s, 'Lightning Bolt', 'p2')
    cast(s, 'Shock', 'p2')
    act(s, 'p1', type='tap', card_ids=[source.id], tapped=False)
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=ability_index(s, source, 'Transform this land'))
    settle(s)
    assert s.state.cards[source.id].face == 0
    roundtrip(s)


@pytest.mark.parametrize('later_change', ['color', 'controller', 'departure'])
def test_temple_reads_source_color_and_controller_when_damage_was_dealt(cards, later_change):
    from tests.game_helpers import act
    from tests.test_rules_designations import put, roundtrip, settle
    from tests.test_rules_wave7b_activation import ability_index
    from tests.test_rules_wave30m_durations import to_phase
    s, source = setup(cards, face=1)
    pinger = put(s, 'Prodigal Pyromancer', 'battlefield')
    to_phase(s, 'main1', turn=4)
    act(s, 'p1', type='activate_ability', card_id=pinger.id, ability=ability_index(s, pinger, 'deals 1 damage'), targets=['p2'])
    settle(s)
    if later_change == 'color':
        cast(s, 'Thoughtlace', pinger.id)
    elif later_change == 'controller':
        act(s, 'p1', type='set_controller', card_ids=[pinger.id], player='p2')
    else:
        cast(s, 'Murder', pinger.id)
    cast(s, 'Lightning Bolt', 'p2')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=ability_index(s, source, 'Transform this land'))
    settle(s)
    assert s.state.cards[source.id].face == 0
    roundtrip(s)


@pytest.mark.parametrize('missing', ['threshold', 'red', 'this_turn'])
def test_temple_requires_enough_red_damage_this_turn_before_paying(cards, missing):
    from app.game.errors import ActionError
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import roundtrip
    from tests.test_rules_wave7b_activation import ability_index
    from tests.test_rules_wave30m_durations import to_phase
    s, source = setup(cards, face=1)
    cast(s, 'Psionic Blast' if missing == 'red' else 'Lightning Bolt', 'p2')
    if missing == 'this_turn':
        cast(s, 'Shock', 'p2')
        to_phase(s, 'main1', turn=4)
        mana(s, R=3)
    before = s.state.model_dump(mode='json')
    with pytest.raises(ActionError):
        act(s, 'p1', type='activate_ability', card_id=source.id, ability=ability_index(s, source, 'Transform this land'))
    assert s.state.model_dump(mode='json') == before
    roundtrip(s)


def test_temple_does_not_retroactively_count_newly_controlled_source_damage(cards):
    from app.game.errors import ActionError
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import wait_priority
    from tests.test_rules_designations import put, roundtrip, settle
    from tests.test_rules_wave7b_activation import ability_index
    from tests.test_rules_wave30m_durations import to_phase
    s, source = setup(cards, face=1)
    pinger = put(s, 'Prodigal Pyromancer', 'battlefield')
    act(s, 'p1', type='set_controller', card_ids=[pinger.id], player='p2')
    to_phase(s, 'main1', turn=4)
    wait_priority(s, 'p2')
    act(s, 'p2', type='activate_ability', card_id=pinger.id, ability=ability_index(s, pinger, 'deals 1 damage'), targets=['p1'])
    settle(s)
    act(s, 'p1', type='set_controller', card_ids=[pinger.id], player='p1')
    cast(s, 'Lightning Bolt', 'p2')
    with pytest.raises(ActionError):
        act(s, 'p1', type='activate_ability', card_id=source.id, ability=ability_index(s, source, 'Transform this land'))
    roundtrip(s)


def test_temple_does_not_count_combat_damage_as_noncombat(cards):
    from app.game.errors import ActionError
    from tests.game_helpers import act
    from tests.test_rules_banding import block, declare_only, until_block
    from tests.test_rules_designations import put, roundtrip
    from tests.test_rules_wave7b_activation import ability_index
    from tests.test_rules_wave30m_durations import to_phase
    s, source = setup(cards, face=1)
    pinger = put(s, 'Prodigal Pyromancer', 'battlefield')
    put(s, 'Grizzly Bears', 'battlefield', 'p2')
    declare_only(s, [pinger], [])
    until_block(s)
    block(s, [])
    to_phase(s, 'main2', turn=4)
    assert s.state.players['p2'].life == 39
    cast(s, 'Lightning Bolt', 'p2')
    with pytest.raises(ActionError):
        act(s, 'p1', type='activate_ability', card_id=source.id, ability=ability_index(s, source, 'Transform this land'))
    roundtrip(s)


def test_front_face_does_not_raise_red_combat_damage(cards):
    from tests.test_rules_banding import block, declare_only, until_block
    from tests.test_rules_designations import put, roundtrip
    from tests.test_rules_wave30m_durations import to_phase
    s, _ = setup(cards)
    pinger = put(s, 'Prodigal Pyromancer', 'battlefield')
    put(s, 'Grizzly Bears', 'battlefield', 'p2')
    declare_only(s, [pinger], [])
    until_block(s)
    block(s, [])
    to_phase(s, 'main2', turn=4)
    assert s.state.players['p2'].life == 39
    roundtrip(s)


def test_floor_neither_reduces_larger_damage_nor_boosts_another_players_source(cards):
    from tests.game_helpers import act
    from tests.test_rules_designations import roundtrip
    s, source = setup(cards)
    act(s, 'p1', type='set_counter', card_id=source.id, kind='-1/-1', value=2)
    cast(s, 'Lightning Bolt', 'p2')
    assert s.state.players['p2'].life == 37
    act(s, 'p1', type='set_counter', card_id=source.id, kind='-1/-1', value=0)
    act(s, 'p1', type='set_controller', card_ids=[source.id], player='p2')
    cast(s, 'Shock', 'p3')
    assert s.state.players['p3'].life == 38
    roundtrip(s)

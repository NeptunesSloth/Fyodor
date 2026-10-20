"""CR 702.29 / 602.2b: non-mana cycling costs and typed searches."""
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
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/expanded_cycling_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()



@pytest.mark.parametrize('name', ['Street Wraith', 'Edge of Autumn', "Sojourner's Companion", 'Fluctuator', 'Suppression Field'])
def test_expanded_cycling_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


@pytest.mark.parametrize('life', [1, 3, 40])
def test_street_wraith_pays_life_and_discards_as_a_cost_or_refuses_before_paying(cards, life):
    from app.game.errors import ActionError
    from tests.game_helpers import act
    from tests.test_rules_designations import put, roundtrip, settle
    from tests.test_rules_shared_damage_choices import table
    from tests.test_rules_wave7b_activation import ability_index

    s = table(cards, ['Street Wraith'], [], [])
    source = put(s, 'Street Wraith', 'hand')
    act(s, 'p1', type='set_life', player='p1', value=life)
    before = len(s.state.zones['p1:hand'])
    if life < 2:
        with pytest.raises(ActionError, match='life'):
            act(s, 'p1', type='activate_ability', card_id=source.id, ability=ability_index(s, source, 'Cycling'))
        assert s.state.cards[source.id].zone == 'p1:hand'
        assert s.state.players['p1'].life == life
    else:
        act(s, 'p1', type='activate_ability', card_id=source.id, ability=ability_index(s, source, 'Cycling'))
        assert s.state.cards[source.id].zone == 'p1:graveyard' and s.state.players['p1'].life == life - 2
        roundtrip(s)
        settle(s)
        assert len(s.state.zones['p1:hand']) == before
    roundtrip(s)


@pytest.mark.parametrize('has_land', [False, True])
def test_edge_of_autumn_cycles_at_instant_speed_by_sacrificing_a_land(cards, has_land):
    from app.game.errors import ActionError
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import wait_priority
    from tests.test_rules_designations import put, roundtrip, settle
    from tests.test_rules_shared_damage_choices import table
    from tests.test_rules_wave7b_activation import ability_index
    from tests.test_rules_wave30m_durations import to_phase

    s = table(cards, ['Edge of Autumn'], [], [])
    source = put(s, 'Edge of Autumn', 'hand')
    land = put(s, 'Forest', 'battlefield') if has_land else None
    to_phase(s, 'main1', turn=2)
    wait_priority(s, 'p1')
    if not has_land:
        with pytest.raises(ActionError):
            act(s, 'p1', type='activate_ability', card_id=source.id, ability=ability_index(s, source, 'Cycling'))
        assert s.state.cards[source.id].zone == 'p1:hand'
    else:
        act(s, 'p1', type='activate_ability', card_id=source.id, ability=ability_index(s, source, 'Cycling'),
            cost_choices=[{'component': 0, 'cards': [land.id]}])
        assert s.state.cards[source.id].zone == 'p1:graveyard' and s.state.cards[land.id].zone == 'p1:graveyard'
        roundtrip(s)
        settle(s)
    roundtrip(s)


@pytest.mark.parametrize('lands', [4, 5])
def test_edge_of_autumn_only_searches_when_its_land_count_condition_holds_on_resolution(cards, lands):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import put, roundtrip, settle
    from tests.test_rules_shared_damage_choices import table

    s = table(cards, ['Edge of Autumn'], [], [])
    ids = [c.id for c in s.state.cards.values() if c.owner == 'p1' and c.name == 'Forest'][:lands]
    act(s, 'p1', type='move', card_ids=ids, to={'player': 'p1', 'zone': 'battlefield'})
    source = put(s, 'Edge of Autumn', 'hand')
    mana(s, C=1, G=1)
    act(s, 'p1', type='cast_spell', card_id=source.id)
    settle(s)
    d = s.state.rules.decision
    if lands == 4:
        assert d and d.options
        selected = d.options[0].id
        act(s, d.player, type='choose', decision_id=d.id, option_ids=[selected])
        settle(s)
        assert s.state.cards[selected].zone == 'p1:battlefield' and s.state.cards[selected].tapped
    else:
        assert not d
    assert len([c for c in s.state.cards.values() if c.zone == 'p1:battlefield' and c.name == 'Forest']) == lands + (lands == 4)
    roundtrip(s)


def test_artifact_landcycling_searches_for_cards_that_are_both_an_artifact_and_a_land(cards):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import put, roundtrip, settle
    from tests.test_rules_shared_damage_choices import table
    from tests.test_rules_wave7b_activation import ability_index

    s = table(cards, ["Sojourner's Companion", 'Darksteel Citadel', 'Great Furnace', 'Sol Ring'], [], [])
    source = put(s, "Sojourner's Companion", 'hand')
    mana(s, C=2)
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=ability_index(s, source, 'landcycling'))
    settle(s)
    d = s.state.rules.decision
    assert d and {s.state.cards[o.id].name for o in d.options} == {'Darksteel Citadel', 'Great Furnace'}
    roundtrip(s)
    chosen = d.options[0].id
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[chosen])
    settle(s)
    assert s.state.cards[chosen].zone == 'p1:hand' and s.state.cards[source.id].zone == 'p1:graveyard'
    roundtrip(s)


@pytest.mark.parametrize('source_name', ['Street Wraith', 'Edge of Autumn'])
def test_stabilizer_also_blocks_nonmana_cycling_before_costs_are_paid(cards, source_name):
    from app.game.errors import ActionError
    from tests.game_helpers import act
    from tests.test_rules_designations import put, roundtrip
    from tests.test_rules_shared_damage_choices import table
    from tests.test_rules_wave7b_activation import ability_index

    s = table(cards, [source_name, 'Stabilizer'], [], [])
    source = put(s, source_name, 'hand')
    land = put(s, 'Forest', 'battlefield')
    put(s, 'Stabilizer', 'battlefield')
    with pytest.raises(ActionError, match="can't cycle"):
        act(s, 'p1', type='activate_ability', card_id=source.id, ability=ability_index(s, source, 'Cycling'))
    assert s.state.players['p1'].life == 40 and s.state.cards[land.id].zone == 'p1:battlefield'
    assert s.state.cards[source.id].zone == 'p1:hand'
    roundtrip(s)


@pytest.mark.parametrize('pay_original', [False, True])
def test_gavi_can_replace_a_nonmana_cycling_cost_and_only_the_first_cycle_is_eligible(cards, pay_original):
    from app.game.errors import ActionError
    from tests.game_helpers import act
    from tests.test_rules_designations import put, roundtrip, settle
    from tests.test_rules_shared_damage_choices import table
    from tests.test_rules_wave7b_activation import ability_index

    s = table(cards, ['Gavi, Nest Warden', 'Street Wraith', 'Street Wraith'], [], [])
    put(s, 'Gavi, Nest Warden', 'battlefield')
    wraiths = [c for c in s.state.cards.values() if c.owner == 'p1' and c.name == 'Street Wraith']
    act(s, 'p1', type='move', card_ids=[c.id for c in wraiths], to={'player': 'p1', 'zone': 'hand'})
    act(s, 'p1', type='set_life', player='p1', value=40 if pay_original else 1)
    index = ability_index(s, wraiths[0], 'Cycling')
    act(s, 'p1', type='activate_ability', card_id=wraiths[0].id, ability=index)
    if pay_original:
        d = s.state.rules.decision
        assert d and {o.id for o in d.options} == {'either:0', 'either:1'}
        roundtrip(s)
        act(s, d.player, type='choose', decision_id=d.id, option_ids=['either:0'])
    settle(s)
    assert s.state.players['p1'].life == (38 if pay_original else 1)
    assert s.state.cards[wraiths[0].id].zone == 'p1:graveyard'
    roundtrip(s)
    if pay_original:
        act(s, 'p1', type='activate_ability', card_id=wraiths[1].id, ability=index)
        settle(s)
        assert s.state.players['p1'].life == 36
    else:
        with pytest.raises(ActionError, match='life'):
            act(s, 'p1', type='activate_ability', card_id=wraiths[1].id, ability=index)
        assert s.state.cards[wraiths[1].id].zone == 'p1:hand'
    roundtrip(s)


@pytest.mark.parametrize('name', ['Remote Isle', "Sojourner's Companion"])
def test_fluctuator_reduces_cycling_and_typecycling_generic_costs_to_zero(cards, name):
    from tests.game_helpers import act
    from tests.test_rules_designations import put, roundtrip, settle
    from tests.test_rules_shared_damage_choices import table
    from tests.test_rules_wave7b_activation import ability_index

    s = table(cards, ['Fluctuator', name, 'Darksteel Citadel'], [], [])
    put(s, 'Fluctuator', 'battlefield')
    source = put(s, name, 'hand')
    act(s, 'p1', type='activate_ability', card_id=source.id,
        ability=ability_index(s, source, 'Cycling' if name == 'Remote Isle' else 'landcycling'))
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    settle(s)
    d = s.state.rules.decision
    if d:
        assert name == "Sojourner's Companion"
        act(s, d.player, type='choose', decision_id=d.id, option_ids=[d.options[0].id])
        settle(s)
    roundtrip(s)


def test_fluctuator_does_not_reduce_colored_cycling_costs_or_unrelated_abilities(cards):
    from app.game.errors import ActionError
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import put, roundtrip, settle
    from tests.test_rules_shared_damage_choices import table
    from tests.test_rules_wave7b_activation import ability_index

    s = table(cards, ['Fluctuator', 'Lonely Sandbar', 'Dimir House Guard', 'Mind Stone'], [], [])
    put(s, 'Fluctuator', 'battlefield')
    sandbar = put(s, 'Lonely Sandbar', 'hand')
    guard = put(s, 'Dimir House Guard', 'hand')
    stone = put(s, 'Mind Stone', 'battlefield')
    # A separate mana source would make the otherwise-unpayable unrelated cost payable.
    act(s, 'p1', type='tap', card_ids=[stone.id], tapped=True)
    mana(s, B=2)
    with pytest.raises(ActionError):
        act(s, 'p1', type='activate_ability', card_id=guard.id, ability=ability_index(s, guard, 'Transmute'))
    with pytest.raises(ActionError):
        act(s, 'p1', type='activate_ability', card_id=sandbar.id, ability=ability_index(s, sandbar, 'Cycling'))
    mana(s, U=1)
    act(s, 'p1', type='activate_ability', card_id=sandbar.id, ability=ability_index(s, sandbar, 'Cycling'))
    settle(s)
    assert s.state.cards[sandbar.id].zone == 'p1:graveyard'
    roundtrip(s)


@pytest.mark.parametrize('name', ['Remote Isle', 'Street Wraith'])
def test_fluctuator_and_a_generic_cost_increase_are_applied_before_payment(cards, name):
    from app.game.errors import ActionError
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import put, roundtrip, settle
    from tests.test_rules_shared_damage_choices import table
    from tests.test_rules_wave7b_activation import ability_index

    s = table(cards, ['Fluctuator', 'Suppression Field', name], [], [])
    put(s, 'Fluctuator', 'battlefield')
    put(s, 'Suppression Field', 'battlefield')
    source = put(s, name, 'hand')
    if name == 'Remote Isle':
        with pytest.raises(ActionError):
            act(s, 'p1', type='activate_ability', card_id=source.id, ability=ability_index(s, source, 'Cycling'))
        mana(s, C=2)
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=ability_index(s, source, 'Cycling'))
    settle(s)
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    assert s.state.players['p1'].life == (38 if name == 'Street Wraith' else 40)
    roundtrip(s)


def test_suppression_field_taxes_loyalty_abilities_but_not_mana_abilities(cards):
    from app.game.errors import ActionError
    from tests.game_helpers import act
    from tests.test_rules_designations import put, roundtrip, settle
    from tests.test_rules_shared_damage_choices import table

    s = table(cards, ['Suppression Field', 'Jace Beleren', 'Sol Ring'], [], [])
    put(s, 'Suppression Field', 'battlefield')
    jace = put(s, 'Jace Beleren', 'battlefield')
    act(s, 'p1', type='set_counter', card_id=jace.id, kind='loyalty', value=3)
    with pytest.raises(ActionError):
        act(s, 'p1', type='activate_ability', card_id=jace.id, ability=0)
    assert s.state.cards[jace.id].counters['loyalty'] == 3
    ring = put(s, 'Sol Ring', 'battlefield')
    act(s, 'p1', type='activate_ability', card_id=ring.id, ability=0)
    assert s.state.cards[ring.id].tapped and not s.state.zones.get('stack')
    before = len(s.state.zones['p1:hand'])
    act(s, 'p1', type='activate_ability', card_id=jace.id, ability=0)
    assert s.state.cards[jace.id].counters['loyalty'] == 5
    roundtrip(s)
    settle(s)
    assert len(s.state.zones['p1:hand']) == before + 1
    roundtrip(s)


@pytest.mark.parametrize('name', ['Street Wraith', 'Edge of Autumn'])
def test_nonmana_cycling_emits_one_cycle_event_for_triggered_abilities(cards, name):
    from tests.game_helpers import act
    from tests.test_rules_designations import put, roundtrip, settle
    from tests.test_rules_shared_damage_choices import table
    from tests.test_rules_wave7b_activation import ability_index

    s = table(cards, [name, 'Drannith Stinger'], [], [])
    put(s, 'Drannith Stinger', 'battlefield')
    source = put(s, name, 'hand')
    put(s, 'Forest', 'battlefield')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=ability_index(s, source, 'Cycling'))
    settle(s)
    assert s.state.players['p2'].life == 39 and s.state.players['p3'].life == 39
    roundtrip(s)


def test_countering_a_nonmana_cycling_ability_does_not_refund_its_cost(cards):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana, wait_priority
    from tests.test_rules_designations import put, roundtrip, settle
    from tests.test_rules_shared_damage_choices import table
    from tests.test_rules_wave7b_activation import ability_index

    s = table(cards, ['Street Wraith'], ['Stifle'], [])
    source = put(s, 'Street Wraith', 'hand')
    before = len(s.state.zones['p1:hand'])
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=ability_index(s, source, 'Cycling'))
    sid = next(sid for sid, entry in s.state.rules.stack.items() if entry.source_card == source.id)
    wait_priority(s, 'p2')
    spell = put(s, 'Stifle', 'hand', 'p2')
    mana(s, 'p2', U=1)
    act(s, 'p2', type='cast_spell', card_id=spell.id, targets=[sid])
    roundtrip(s)
    settle(s)
    assert s.state.players['p1'].life == 38 and s.state.cards[source.id].zone == 'p1:graveyard'
    assert len(s.state.zones['p1:hand']) == before - 1
    roundtrip(s)


def test_street_wraith_obeys_a_prohibition_on_paying_life_to_activate_abilities(cards):
    from app.game.errors import ActionError
    from tests.game_helpers import act
    from tests.test_rules_designations import put, roundtrip
    from tests.test_rules_shared_damage_choices import table
    from tests.test_rules_wave7b_activation import ability_index

    s = table(cards, ['Street Wraith', 'Angel of Jubilation'], [], [])
    put(s, 'Angel of Jubilation', 'battlefield')
    source = put(s, 'Street Wraith', 'hand')
    with pytest.raises(ActionError):
        act(s, 'p1', type='activate_ability', card_id=source.id, ability=ability_index(s, source, 'Cycling'))
    assert s.state.players['p1'].life == 40 and s.state.cards[source.id].zone == 'p1:hand'
    roundtrip(s)

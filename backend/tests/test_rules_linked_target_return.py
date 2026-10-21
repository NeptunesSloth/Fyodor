"""CR 607.2b, 400.7, 614.12: targeted linked-exile returns with additional entry counters."""
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
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/linked_target_return_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()



NAME = 'The Darkness Crystal'


def test_full(cards):
    assert coverage.of_card_data(cards.resolve(NAME)).level == 'FULL'


def setup(cards, creature='Grizzly Bears'):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana, wait_priority
    from tests.test_rules_designations import put, settle
    from tests.test_rules_shared_damage_choices import table
    from tests.test_rules_wave30m_durations import to_phase
    s = table(cards, [NAME, 'Murder', 'Sol Ring', 'Ghostly Flicker', 'Solemnity', 'Vorinclex, Monstrous Raider', 'Hardened Scales', 'Lithoform Engine', 'Reroute'],
        [creature, 'Llanowar Elves', 'Disenchant', 'Pull from Eternity', 'Cremate'])
    source = put(s, NAME, 'battlefield')
    if creature == 'Spike Feeder':
        to_phase(s, 'main1', turn=2)
        target = put(s, creature, 'hand', 'p2')
        mana(s, 'p2', G=3)
        act(s, 'p2', type='cast_spell', card_id=target.id)
        settle(s)
    else:
        target = put(s, creature, 'battlefield', 'p2')
    wait_priority(s, 'p1')
    kill(s, target)
    assert s.state.cards[target.id].zone == 'p2:exile'
    assert s.state.players['p1'].life == 42
    return s, source, target


def kill(s, target):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import put, settle
    spell = put(s, 'Murder', 'hand')
    mana(s, B=3)
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[target.id])
    settle(s)


def activate(s, source, target):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana, wait_priority
    from tests.test_rules_wave7b_activation import ability_index
    wait_priority(s, 'p1')
    mana(s, B=6)
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=ability_index(s, source, 'Put target creature card'), targets=[target.id])


@pytest.mark.parametrize(('creature', 'count'), [('Grizzly Bears', 2), ('Spike Feeder', 4), ('Corpsejack Menace', 2)])
def test_returns_tapped_under_activators_control_with_additional_entry_counters(cards, creature, count):
    from tests.test_rules_designations import roundtrip, settle
    s, source, target = setup(cards, creature)
    activate(s, source, target)
    settle(s)
    card = s.state.cards[target.id]
    assert card.zone == 'p1:battlefield' and card.controller == 'p1' and card.owner == 'p2'
    assert card.tapped and card.counters['+1/+1'] == count
    assert s.state.cards[source.id].tapped
    roundtrip(s)


@pytest.mark.parametrize(('modifier', 'count'), [('Solemnity', 0), ('Vorinclex, Monstrous Raider', 4), ('Hardened Scales', 3)])
def test_return_counters_pass_through_entry_replacements(cards, modifier, count):
    from tests.test_rules_designations import put, roundtrip, settle
    s, source, target = setup(cards)
    put(s, modifier, 'battlefield')
    activate(s, source, target)
    settle(s)
    assert s.state.cards[target.id].zone == 'p1:battlefield'
    assert s.state.cards[target.id].counters.get('+1/+1', 0) == count
    roundtrip(s)


def blink_source(s, source):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana, wait_priority
    from tests.test_rules_designations import put
    wait_priority(s, 'p1')
    ring = put(s, 'Sol Ring', 'battlefield')
    spell = put(s, 'Ghostly Flicker', 'hand')
    mana(s, U=3)
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[source.id, ring.id], target_counts=[2])


def test_ability_uses_original_source_link_after_source_blinks(cards):
    from tests.game_helpers import act
    from tests.test_rules_designations import roundtrip, settle
    s, source, target = setup(cards)
    act(s, 'p1', type='set_prefs', hold_priority=True)
    activate(s, source, target)
    blink_source(s, source)
    settle(s)
    assert s.state.cards[target.id].zone == 'p1:battlefield'
    assert s.state.cards[target.id].counters['+1/+1'] == 2
    assert not s.state.cards[source.id].tapped
    roundtrip(s)


def test_new_source_object_cannot_target_old_linked_exiles(cards):
    from app.game.errors import ActionError
    from tests.test_rules_designations import roundtrip, settle
    s, source, target = setup(cards)
    blink_source(s, source)
    settle(s)
    with pytest.raises(ActionError, match='legal target'):
        activate(s, source, target)
    assert s.state.cards[target.id].zone == 'p2:exile'
    assert not s.state.cards[source.id].tapped
    roundtrip(s)


def test_unlinked_exiled_creature_is_not_a_legal_target(cards):
    from app.game.errors import ActionError
    from tests.test_rules_designations import put, roundtrip
    s, source, target = setup(cards)
    unrelated = put(s, 'Llanowar Elves', 'exile', 'p2')
    with pytest.raises(ActionError, match='legal target'):
        activate(s, source, unrelated)
    assert s.state.cards[target.id].zone == 'p2:exile'
    assert not s.state.cards[source.id].tapped
    roundtrip(s)


def test_source_destroyed_in_response_does_not_break_linked_target(cards):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana, wait_priority
    from tests.test_rules_designations import put, roundtrip, settle
    s, source, target = setup(cards)
    act(s, 'p1', type='set_prefs', hold_priority=True)
    activate(s, source, target)
    wait_priority(s, 'p2')
    spell = put(s, 'Disenchant', 'hand', 'p2')
    mana(s, 'p2', W=2)
    act(s, 'p2', type='cast_spell', card_id=spell.id, targets=[source.id])
    settle(s)
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    assert s.state.cards[target.id].zone == 'p1:battlefield'
    assert s.state.cards[target.id].counters['+1/+1'] == 2
    roundtrip(s)


def test_target_leaves_exile_before_ability_resolves(cards):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana, wait_priority
    from tests.test_rules_designations import put, roundtrip, settle
    s, source, target = setup(cards)
    act(s, 'p1', type='set_prefs', hold_priority=True)
    activate(s, source, target)
    wait_priority(s, 'p2')
    spell = put(s, 'Pull from Eternity', 'hand', 'p2')
    mana(s, 'p2', W=1)
    act(s, 'p2', type='cast_spell', card_id=spell.id, targets=[target.id])
    settle(s)
    assert s.state.cards[target.id].zone == 'p2:graveyard'
    assert not s.state.cards[target.id].counters
    assert s.state.cards[source.id].tapped
    roundtrip(s)


def test_target_leaves_exile_and_returns_is_new_object(cards):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana, wait_priority
    from tests.test_rules_designations import put, roundtrip, settle
    s, source, target = setup(cards)
    act(s, 'p1', type='set_prefs', hold_priority=True)
    activate(s, source, target)
    wait_priority(s, 'p2')
    spell = put(s, 'Pull from Eternity', 'hand', 'p2')
    mana(s, 'p2', W=1)
    act(s, 'p2', type='cast_spell', card_id=spell.id, targets=[target.id])
    for _ in range(10):
        if s.state.cards[target.id].zone == 'p2:graveyard':
            break
        act(s, s.state.rules.priority, type='pass_priority')
    assert s.state.cards[target.id].zone == 'p2:graveyard'
    wait_priority(s, 'p2')
    exile = put(s, 'Cremate', 'hand', 'p2')
    mana(s, 'p2', B=1)
    act(s, 'p2', type='cast_spell', card_id=exile.id, targets=[target.id])
    settle(s)
    assert s.state.cards[target.id].zone == 'p2:exile'
    assert not s.state.cards[target.id].counters
    roundtrip(s)


def test_copy_can_retarget_original_linked_cards_after_source_blinks(cards):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana, wait_priority
    from tests.test_rules_designations import put, roundtrip, settle
    from tests.test_rules_wave7b_activation import ability_index
    s, source, first = setup(cards)
    second = put(s, 'Llanowar Elves', 'battlefield', 'p2')
    wait_priority(s, 'p1')
    kill(s, second)
    copier = put(s, 'Lithoform Engine', 'battlefield')
    act(s, 'p1', type='set_prefs', hold_priority=True)
    activate(s, source, first)
    original = s.state.zones['stack'][-1]
    mana(s, C=2)
    act(s, 'p1', type='activate_ability', card_id=copier.id,
        ability=ability_index(s, copier, 'Copy target activated'), targets=[original])
    blink_source(s, source)
    settle(s)
    d = s.state.rules.decision
    assert d is not None and d.prompt.startswith('Copy of The Darkness Crystal')
    assert second.id in {o.id for o in d.options}
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[second.id])
    settle(s)
    for target in [first, second]:
        assert s.state.cards[target.id].zone == 'p1:battlefield'
        assert s.state.cards[target.id].counters['+1/+1'] == 2
    roundtrip(s)


def test_pull_from_eternity_is_full(cards):
    assert coverage.of_card_data(cards.resolve('Pull from Eternity')).level == 'FULL'


@pytest.mark.parametrize('name', ['Grizzly Bears', 'Murder', 'Sol Ring'])
def test_face_up_exiled_card_returns_to_owners_graveyard(cards, name):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import put, roundtrip, settle
    from tests.test_rules_shared_damage_choices import table
    s = table(cards, ['Pull from Eternity'], [name])
    target = put(s, name, 'exile', 'p2')
    spell = put(s, 'Pull from Eternity', 'hand')
    mana(s, W=1)
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[target.id])
    settle(s)
    assert s.state.cards[target.id].zone == 'p2:graveyard'
    roundtrip(s)


def test_pull_from_eternity_cannot_target_face_down_exile(cards):
    from app.game.errors import ActionError
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import put, roundtrip
    from tests.test_rules_shared_damage_choices import table
    s = table(cards, ['Pull from Eternity'], ['Grizzly Bears'])
    target = put(s, 'Grizzly Bears', 'exile', 'p2')
    act(s, 'p2', type='face_down', card_ids=[target.id], face_down=True)
    spell = put(s, 'Pull from Eternity', 'hand')
    mana(s, W=1)
    with pytest.raises(ActionError, match='legal target'):
        act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[target.id])
    assert s.state.cards[target.id].zone == 'p2:exile'
    roundtrip(s)


def test_black_spell_reduction_does_not_reduce_crystals_activated_cost(cards):
    from app.game.errors import ActionError
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana, wait_priority
    from tests.test_rules_designations import roundtrip
    from tests.test_rules_wave7b_activation import ability_index
    s, source, target = setup(cards)
    wait_priority(s, 'p1')
    mana(s, B=5 - sum(s.state.players['p1'].mana.values()))
    assert sum(s.state.players['p1'].mana.values()) == 5
    with pytest.raises(ActionError):
        act(s, 'p1', type='activate_ability', card_id=source.id,
            ability=ability_index(s, source, 'Put target creature card'), targets=[target.id])
    assert not s.state.cards[source.id].tapped
    assert s.state.cards[target.id].zone == 'p2:exile'
    roundtrip(s)


def test_entry_counter_replacement_choice_survives_replay_before_entry(cards):
    from tests.game_helpers import act
    from tests.test_rules_designations import put, roundtrip, settle
    s, source, target = setup(cards)
    put(s, 'Vorinclex, Monstrous Raider', 'battlefield')
    put(s, 'Hardened Scales', 'battlefield')
    activate(s, source, target)
    settle(s)
    d = s.state.rules.decision
    assert d is not None and d.resume.get('step') == 'enter_choice'
    assert s.state.cards[target.id].zone == 'p2:exile'
    roundtrip(s)
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[d.options[0].id])
    settle(s)
    assert s.state.cards[target.id].zone == 'p1:battlefield'
    assert s.state.cards[target.id].counters['+1/+1'] in (5, 6)
    assert s.state.cards[target.id].tapped
    roundtrip(s)


def test_redirected_activation_uses_original_link_after_crystal_blinked(cards):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana, wait_priority
    from tests.test_rules_designations import put, roundtrip, settle
    s, source, first = setup(cards)
    second = put(s, 'Llanowar Elves', 'battlefield', 'p2')
    wait_priority(s, 'p1')
    kill(s, second)
    act(s, 'p1', type='set_prefs', hold_priority=True)
    activate(s, source, first)
    original = s.state.zones['stack'][-1]
    old = s.state.rules.object_id(source.id)
    blink_source(s, source)
    for _ in range(10):
        if s.state.rules.object_id(source.id) != old:
            break
        act(s, s.state.rules.priority, type='pass_priority')
    assert s.state.rules.object_id(source.id) != old
    wait_priority(s, 'p1')
    redirect = put(s, 'Reroute', 'hand')
    mana(s, R=2)
    act(s, 'p1', type='cast_spell', card_id=redirect.id, targets=[original])
    settle(s)
    assert s.state.rules.decision is None  # The only different legal target is chosen automatically.
    assert s.state.cards[first.id].zone == 'p2:exile'
    assert s.state.cards[second.id].zone == 'p1:battlefield'
    assert s.state.cards[second.id].counters['+1/+1'] == 2
    roundtrip(s)

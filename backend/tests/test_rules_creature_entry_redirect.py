"""CR 111.2, 608.2h: conditional attached copy and actual creation fallback."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/creature_entry_redirect_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()




@pytest.mark.parametrize('name', ['Containment Priest', 'Hallowed Moonlight'])
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


def moonlight(s):
    c = put(s, 'Hallowed Moonlight', 'hand')
    mana(s, C=1, W=1)
    act(s, 'p1', type='cast_spell', card_id=c.id)
    settle(s)


def test_priest_allows_actual_cast_but_exiles_reanimation(cards):
    s = table(cards, ['Containment Priest', 'Grizzly Bears', 'Reanimate'])
    put(s, 'Containment Priest', 'battlefield')
    bear = put(s, 'Grizzly Bears', 'hand')
    mana(s, C=1, G=1)
    act(s, 'p1', type='cast_spell', card_id=bear.id)
    settle(s)
    assert s.state.cards[bear.id].zone == 'p1:battlefield'
    act(s, 'p1', type='move', card_ids=[bear.id], to={'player': 'p1', 'zone': 'graveyard'})
    reanimate = put(s, 'Reanimate', 'hand')
    mana(s, B=1)
    act(s, 'p1', type='cast_spell', card_id=reanimate.id, targets=[bear.id])
    settle(s)
    assert s.state.cards[bear.id].zone == 'p1:exile'
    roundtrip(s)


def test_priest_does_not_exile_self_or_tokens(cards):
    s = table(cards, ['Containment Priest', 'Raise the Alarm'])
    priest = put(s, 'Containment Priest', 'battlefield')
    assert s.state.cards[priest.id].zone == 'p1:battlefield'
    spell = put(s, 'Raise the Alarm', 'hand')
    mana(s, C=1, W=1)
    act(s, 'p1', type='cast_spell', card_id=spell.id)
    settle(s)
    assert len([c for c in s.state.cards.values() if c.is_token and c.name == 'Soldier']) == 2
    roundtrip(s)


def test_moonlight_tokens_never_enter(cards):
    s = table(cards, ['Hallowed Moonlight', 'Raise the Alarm'])
    moonlight(s)
    before = len(s.state.rules.turn_log.entered)
    spell = put(s, 'Raise the Alarm', 'hand')
    mana(s, C=1, W=1)
    act(s, 'p1', type='cast_spell', card_id=spell.id)
    settle(s)
    assert not [c for c in s.state.cards.values() if c.is_token and c.name == 'Soldier']
    assert len(s.state.rules.turn_log.entered) == before
    roundtrip(s)


def test_actual_free_cast_is_cast(cards):
    s = table(cards, ['Containment Priest', 'Omniscience', 'Grizzly Bears'])
    put(s, 'Containment Priest', 'battlefield')
    put(s, 'Omniscience', 'battlefield')
    bear = put(s, 'Grizzly Bears', 'hand')
    act(s, 'p1', type='cast_spell', card_id=bear.id, free=True)
    settle(s)
    assert s.state.cards[bear.id].zone == 'p1:battlefield'
    paid = s.state.rules.payments[s.state.rules.object_id(bear.id)]
    assert paid.cast_from == 'hand' and not sum(paid.mana_spent.values())
    roundtrip(s)


def test_actual_blink_does_not_preserve_cast_exemption(cards):
    s = table(cards, ['Containment Priest', 'Grizzly Bears', 'Ephemerate'])
    bear = put(s, 'Grizzly Bears', 'hand')
    mana(s, C=1, G=1)
    act(s, 'p1', type='cast_spell', card_id=bear.id)
    settle(s)
    put(s, 'Containment Priest', 'battlefield')
    blink = put(s, 'Ephemerate', 'hand')
    mana(s, W=1)
    act(s, 'p1', type='cast_spell', card_id=blink.id, targets=[bear.id])
    settle(s)
    assert s.state.cards[bear.id].zone == 'p1:exile'
    roundtrip(s)


@pytest.mark.parametrize('name,modifier,exiled', [('Sol Ring', 'March of the Machines', True),
                                                ('Heliod, Sun-Crowned', None, False)])
def test_entering_derived_type_not_printed_type(cards, name, modifier, exiled):
    s = table(cards, ['Containment Priest', name, 'Refurbish', 'Reanimate', *([modifier] if modifier else [])])
    put(s, 'Containment Priest', 'battlefield')
    if modifier:
        put(s, modifier, 'battlefield')
    incoming = put(s, name, 'graveyard')
    spell = put(s, 'Refurbish' if name == 'Sol Ring' else 'Reanimate', 'hand')
    mana(s, C=3, W=1, B=1)
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[incoming.id])
    settle(s)
    assert s.state.cards[incoming.id].zone == ('p1:exile' if exiled else 'p1:battlefield')
    roundtrip(s)


def test_simultaneous_priest_and_creature_do_not_interfere(cards):
    s = table(cards, ['Containment Priest', 'Grizzly Bears', 'Living Death'])
    priest = put(s, 'Containment Priest', 'graveyard')
    bear = put(s, 'Grizzly Bears', 'graveyard')
    spell = put(s, 'Living Death', 'hand')
    mana(s, C=3, B=2)
    act(s, 'p1', type='cast_spell', card_id=spell.id)
    settle(s)
    assert all(s.state.cards[c.id].zone == 'p1:battlefield' for c in [priest, bear])
    roundtrip(s)


def test_moonlight_visitation_creation_replacement_precedes_entry(cards):
    s = table(cards, ['Hallowed Moonlight', 'Raise the Alarm', 'Divine Visitation'])
    put(s, 'Divine Visitation', 'battlefield')
    moonlight(s)
    spell = put(s, 'Raise the Alarm', 'hand')
    mana(s, C=1, W=1)
    before = len(s.state.rules.turn_log.entered)
    act(s, 'p1', type='cast_spell', card_id=spell.id)
    settle(s)
    assert not [c for c in s.state.cards.values() if c.is_token]
    assert len(s.state.rules.turn_log.entered) == before
    roundtrip(s)


@pytest.mark.parametrize('guard,remaining', [('Hallowed Moonlight', 0), ('Containment Priest', 1)])
def test_copied_creature_spell_was_not_cast_but_is_token(cards, guard, remaining):
    s = table(cards, [guard, 'Grizzly Bears', 'Double Major'])
    if guard == 'Hallowed Moonlight':
        moonlight(s)
    else:
        put(s, guard, 'battlefield')
    bear = put(s, 'Grizzly Bears', 'hand')
    act(s, 'p1', type='set_prefs', hold_priority=True)
    mana(s, C=1, G=2, U=1)
    act(s, 'p1', type='cast_spell', card_id=bear.id)
    spell = put(s, 'Double Major', 'hand')
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[bear.id])
    settle(s)
    assert s.state.cards[bear.id].zone == 'p1:battlefield'
    assert len([c for c in s.state.cards.values() if c.is_token and c.name == 'Grizzly Bears']) == remaining
    roundtrip(s)


def test_moonlight_expiration_restores_token_entry(cards):
    from tests.test_rules_wave30m_durations import to_phase

    s = table(cards, ['Hallowed Moonlight', 'Raise the Alarm'])
    moonlight(s)
    to_phase(s, 'main1', turn=2)
    from tests.test_rules_bandmate_references import wait_priority

    wait_priority(s, 'p1')
    spell = put(s, 'Raise the Alarm', 'hand')
    mana(s, C=1, W=1)
    act(s, 'p1', type='cast_spell', card_id=spell.id)
    settle(s)
    assert len([c for c in s.state.cards.values() if c.is_token and c.name == 'Soldier']) == 2
    roundtrip(s)


def test_priest_removed_before_reanimation_does_not_apply(cards):
    s = table(cards, ['Containment Priest', 'Grizzly Bears', 'Reanimate'])
    priest = put(s, 'Containment Priest', 'battlefield')
    bear = put(s, 'Grizzly Bears', 'graveyard')
    act(s, 'p1', type='move', card_ids=[priest.id], to={'player': 'p1', 'zone': 'exile'})
    spell = put(s, 'Reanimate', 'hand')
    mana(s, B=1)
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[bear.id])
    settle(s)
    assert s.state.cards[bear.id].zone == 'p1:battlefield'
    roundtrip(s)


def test_priest_flash_before_reanimation_resolves(cards):
    from tests.test_rules_bandmate_references import wait_priority

    s = table(cards, ['Grizzly Bears', 'Reanimate'], ['Containment Priest'])
    bear = put(s, 'Grizzly Bears', 'graveyard')
    spell = put(s, 'Reanimate', 'hand')
    mana(s, B=1)
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[bear.id])
    wait_priority(s, 'p2')
    priest = put(s, 'Containment Priest', 'hand', 'p2')
    act(s, 'p2', type='add_mana', player='p2', mana={'C': 1, 'W': 1})
    act(s, 'p2', type='cast_spell', card_id=priest.id)
    settle(s)
    assert s.state.cards[priest.id].zone == 'p2:battlefield'
    assert s.state.cards[bear.id].zone == 'p1:exile'
    roundtrip(s)


@pytest.mark.parametrize('extra,exiled', [(False, False), (True, True)])
def test_incoming_heliod_counts_own_devotion_for_controller_not_owner(cards, extra, exiled):
    s = table(cards, ['Containment Priest', 'Leyline of Sanctity', 'Authority of the Consuls', 'Reanimate'], ['Heliod, Sun-Crowned'])
    put(s, 'Containment Priest', 'battlefield')  # W
    put(s, 'Leyline of Sanctity', 'battlefield')  # WW
    if extra:
        put(s, 'Authority of the Consuls', 'battlefield')  # W
    incoming = put(s, 'Heliod, Sun-Crowned', 'graveyard', 'p2')  # incoming W is the fifth or fourth
    spell = put(s, 'Reanimate', 'hand')
    mana(s, B=1)
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[incoming.id])
    settle(s)
    assert s.state.cards[incoming.id].zone == ('p2:exile' if exiled else 'p1:battlefield')
    if not exiled:
        assert s.state.cards[incoming.id].owner == 'p2' and s.state.cards[incoming.id].controller == 'p1'
    roundtrip(s)


def test_moonlight_exiled_copy_is_created_so_nantuko_has_no_fallback(cards):
    s = table(cards, ['Springheart Nantuko', 'Grizzly Bears', 'Forest', 'Hallowed Moonlight'])
    host = put(s, 'Grizzly Bears', 'battlefield')
    source = put(s, 'Springheart Nantuko', 'hand')
    mana(s, C=1, G=1)
    act(s, 'p1', type='cast_spell', card_id=source.id, targets=[host.id], alt_cost=f'{source.id}:0')
    settle(s)
    moonlight(s)
    land = put(s, 'Forest', 'hand')
    mana(s, C=1, G=1)
    act(s, 'p1', type='play_land', card_id=land.id)
    settle(s)
    d = s.state.rules.decision
    assert d is not None
    roundtrip(s)
    act(s, d.player, type='choose', decision_id=d.id, option_ids=['pay'])
    settle(s)
    # Both would cease to exist; inspect actual creation log to distinguish no
    # fallback from an incorrectly created-and-also-exiled fallback Insect.
    log = json.dumps([e.model_dump(mode='json') for e in s.state.log])
    assert 'Grizzly Bears token' in log and 'Insect token' not in log
    assert not [c for c in s.state.cards.values() if c.is_token]
    roundtrip(s)


def test_copy_as_entry_precedes_creature_exile_replacement(cards):
    s = table(cards, ['Containment Priest', 'Phyrexian Metamorph', 'Sol Ring', 'Refurbish'])
    put(s, 'Containment Priest', 'battlefield')
    ring = put(s, 'Sol Ring', 'battlefield')
    incoming = put(s, 'Phyrexian Metamorph', 'graveyard')
    spell = put(s, 'Refurbish', 'hand')
    mana(s, C=3, W=1)
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[incoming.id])
    settle(s)
    d = s.state.rules.decision
    assert d is not None and any(o.id == ring.id for o in d.options)
    roundtrip(s)
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[ring.id])
    settle(s)
    assert s.state.cards[incoming.id].zone == 'p1:battlefield'
    from tests.test_rules_wave6c_tokens_pumps import chars

    assert 'Creature' not in chars(s, s.state.cards[incoming.id]).types
    roundtrip(s)


def test_priest_losing_ability_does_not_replace_entry(cards):
    s = table(cards, ['Containment Priest', 'Humility', 'Grizzly Bears', 'Reanimate'])
    put(s, 'Containment Priest', 'battlefield')
    put(s, 'Humility', 'battlefield')
    bear = put(s, 'Grizzly Bears', 'graveyard')
    spell = put(s, 'Reanimate', 'hand')
    mana(s, B=1)
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[bear.id])
    settle(s)
    assert s.state.cards[bear.id].zone == 'p1:battlefield'
    roundtrip(s)

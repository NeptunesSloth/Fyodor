"""Exact stolen-card permissions and owner-qualified permanent entry."""
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
from tests.test_rules_bandmate_references import mana
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

NAME = 'Brainstealer Dragon'


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    data = json.loads((Path(__file__).parent / 'fixtures/brainstealer_dragon_cards.json').read_text())
    for i, c in enumerate(data):
        base[c['name']] = card(c['name'], set_code='sec', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()







def library(s, pid, names):
    for cid in list(s.state.zones[f'{pid}:library']):
        act(s, 'p1', type='move', card_ids=[cid], to={'player': pid, 'zone': 'graveyard'})
    out = []
    for name in names:
        c = next(c for c in s.state.cards.values() if c.owner == pid and c.name == name and c.id not in out)
        act(s, 'p1', type='move', card_ids=[c.id], to={'player': pid, 'zone': 'library'}, position='bottom')
        out.append(c.id)
    return out


def setup(cards, stolen='Grizzly Bears', other='Mind Stone', empty_other=False):
    names = [NAME, 'Grizzly Bears', 'Lightning Bolt', 'Forest', 'Island', 'Sol Ring', 'Mind Stone', 'Disenchant',
             'Counterspell', 'Oblivion Ring', 'Containment Priest', 'Valki, God of Lies // Tibalt, Cosmic Impostor',
             'Reanimate', 'Spatial Contortion', 'Birgi, God of Storytelling // Harnfel, Horn of Bounty']
    s = table(cards, names, names, names)
    source = put(s, NAME, 'hand')
    mana(s, C=5, B=2)
    act(s, 'p1', type='cast_spell', card_id=source.id)
    settle(s)
    top2 = library(s, 'p2', [stolen, 'Forest' if stolen != 'Forest' else 'Island'])
    top3 = library(s, 'p3', [other, 'Island' if other != 'Island' else 'Forest'])
    if empty_other:
        act(s, 'p1', type='move', card_ids=top3, to={'player': 'p3', 'zone': 'graveyard'})
    to_phase(s, 'end', turn=1)
    settle(s)
    assert s.state.cards[top2[0]].zone == 'p2:exile'
    assert s.state.cards[top3[0]].zone == ('p3:graveyard' if empty_other else 'p3:exile')
    roundtrip(s)
    return s, source, top2[0], top3[0]


def test_full(cards):
    assert coverage.of_card_data(cards.resolve(NAME)).level == 'FULL'


def test_actual_paid_wrong_color_spell_and_artifact_entry_charge_correct_owners(cards):
    s, source, stolen, other = setup(cards)
    mana(s, U=2)
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=stolen)
    to_phase(s, 'main1', turn=4)
    settle(s)
    mana(s, U=4)
    act(s, 'p1', type='cast_spell', card_id=stolen)
    settle(s)
    assert s.state.cards[stolen].controller == 'p1' and s.state.cards[stolen].owner == 'p2'
    assert s.state.players['p2'].life == 38 and s.state.players['p1'].life == 40
    act(s, 'p1', type='cast_spell', card_id=other)
    settle(s)
    assert s.state.players['p3'].life == 38
    from tests.game_helpers import mana_pool

    assert not mana_pool(s)
    roundtrip(s)


def test_color_flexibility_does_not_pay_required_colorless_symbol(cards):
    s, source, stolen, other = setup(cards, stolen='Spatial Contortion')
    mana(s, U=2)
    before = s.state.model_dump(mode='json')
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=stolen, targets=[source.id])
    assert s.state.model_dump(mode='json') == before
    mana(s, C=1)
    act(s, 'p1', type='cast_spell', card_id=stolen, targets=[source.id])
    settle(s)
    assert s.state.cards[stolen].zone == 'p2:graveyard'
    assert s.state.players['p2'].life == 40
    roundtrip(s)


def test_stolen_land_uses_normal_land_play_and_causes_no_life_loss(cards):
    s, source, stolen, other = setup(cards, stolen='Forest', other='Island')
    to_phase(s, 'main1', turn=4)
    settle(s)
    act(s, 'p1', type='play_land', card_id=stolen)
    before = s.state.model_dump(mode='json')
    with pytest.raises(ActionError):
        act(s, 'p1', type='play_land', card_id=other)
    assert s.state.model_dump(mode='json') == before
    assert s.state.cards[stolen].controller == 'p1' and s.state.players['p2'].life == 40
    roundtrip(s)


def test_exile_new_incarnation_loses_permission(cards):
    s, source, stolen, other = setup(cards, stolen='Spatial Contortion')
    act(s, 'p1', type='move', card_ids=[stolen], to={'player': 'p2', 'zone': 'graveyard'})
    act(s, 'p1', type='move', card_ids=[stolen], to={'player': 'p2', 'zone': 'exile'})
    mana(s, C=1, U=1)
    before = s.state.model_dump(mode='json')
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=stolen, targets=[source.id])
    assert s.state.model_dump(mode='json') == before
    roundtrip(s)


def test_unrelated_reanimation_opponent_owned_entry_charges_owner_and_spell_caster(cards):
    s, source, stolen, other = setup(cards, stolen='Forest')
    target = put(s, 'Grizzly Bears', 'graveyard', 'p2')
    to_phase(s, 'main1', turn=4)
    settle(s)
    reanimate = put(s, 'Reanimate', 'hand')
    mana(s, B=1)
    act(s, 'p1', type='cast_spell', card_id=reanimate.id, targets=[target.id])
    settle(s)
    assert s.state.cards[target.id].controller == 'p1' and s.state.cards[target.id].owner == 'p2'
    assert s.state.players['p1'].life == s.state.players['p2'].life == 38
    roundtrip(s)


def test_stolen_modal_back_face_entry_uses_actual_permanent_mana_value(cards):
    s, source, stolen, other = setup(cards, stolen='Birgi, God of Storytelling // Harnfel, Horn of Bounty')
    to_phase(s, 'main1', turn=4)
    settle(s)
    mana(s, U=5)
    act(s, 'p1', type='cast_spell', card_id=stolen, face=1)
    settle(s)
    assert s.state.cards[stolen].zone == 'p1:battlefield' and s.state.cards[stolen].face == 1
    assert s.state.players['p2'].life == 35 and s.state.players['p1'].life == 40
    roundtrip(s)


def test_existing_control_change_is_not_an_entry_and_prior_permission_stays_original_player(cards):
    s, source, stolen, other = setup(cards)
    act(s, 'p1', type='set_controller', card_ids=[source.id], player='p3')
    assert s.state.players['p1'].life == s.state.players['p2'].life == s.state.players['p3'].life == 40
    to_phase(s, 'main1', turn=4)
    settle(s)
    mana(s, U=2)
    act(s, 'p1', type='cast_spell', card_id=stolen)
    settle(s)
    assert s.state.cards[stolen].zone == 'p1:battlefield'
    assert s.state.players['p2'].life == 40  # Dragon now watches entrants controlled by p3.
    roundtrip(s)


def test_actual_source_exile_does_not_expire_prior_play_permission(cards):
    s, source, stolen, other = setup(cards)
    to_phase(s, 'main1', turn=4)
    settle(s)
    ring = put(s, 'Oblivion Ring', 'hand')
    mana(s, C=2, W=1)
    act(s, 'p1', type='cast_spell', card_id=ring.id)
    settle(s)
    d = s.state.rules.decision
    assert d is not None and source.id in {o.id for o in d.options}
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[source.id])
    settle(s)
    assert s.state.cards[source.id].zone == 'p1:exile'
    mana(s, U=2)
    act(s, 'p1', type='cast_spell', card_id=stolen)
    settle(s)
    assert s.state.cards[stolen].zone == 'p1:battlefield' and s.state.players['p2'].life == 40
    roundtrip(s)


def test_opponent_owned_dragon_reanimated_sees_its_own_entry(cards):
    s = table(cards, ['Reanimate'], [NAME])
    dragon = put(s, NAME, 'graveyard', 'p2')
    spell = put(s, 'Reanimate', 'hand')
    mana(s, B=1)
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[dragon.id])
    settle(s)
    assert s.state.cards[dragon.id].controller == 'p1'
    assert s.state.players['p1'].life == s.state.players['p2'].life == 33
    roundtrip(s)


def test_empty_opponent_library_contributes_no_card_or_permission(cards):
    s, source, stolen, other = setup(cards, empty_other=True)
    assert any(p.card == stolen for p in s.state.rules.permissions)
    assert not any(p.card == other for p in s.state.rules.permissions)
    assert not s.state.zones['p3:library']
    roundtrip(s)


def test_entering_opponent_owned_artifact_leaving_in_response_preserves_owner_and_mana_value(cards):
    s, source, stolen, other = setup(cards)
    to_phase(s, 'main1', turn=4)
    settle(s)
    act(s, 'p1', type='set_prefs', hold_priority=True)
    mana(s, U=2)
    act(s, 'p1', type='cast_spell', card_id=other)
    for _ in range(20):
        if s.state.cards[other].zone != 'stack':
            break
        act(s, s.state.rules.priority, type='pass_priority')
    assert s.state.cards[other].zone == 'p1:battlefield'
    destroy = put(s, 'Disenchant', 'hand')
    mana(s, C=1, W=1)
    act(s, 'p1', type='cast_spell', card_id=destroy.id, targets=[other])
    settle(s)
    assert s.state.cards[other].zone == 'p3:graveyard'
    assert s.state.players['p3'].life == 38 and s.state.players['p1'].life == 40
    roundtrip(s)

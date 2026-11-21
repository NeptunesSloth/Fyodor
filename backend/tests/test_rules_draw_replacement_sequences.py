"""Actual Oracle draw records, frozen choices and native replacement continuations."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import coverage
from tests.conftest import claim_host
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana
from tests.test_rules_controller_tutors import answer
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_look import settle
from tests.test_rules_ordered_tutor_continuations import cast
from tests.test_rules_qualified_attached_tutors import cold
from tests.test_rules_refused_look import stack_library
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave4h_activation_costs import ability
from tests.test_rules_wave30m_durations import to_phase

DATA = Path(__file__).parent / 'fixtures/draw_replacement_sequence_cards.json'
RECORDS = [c['name'] for c in json.loads(DATA.read_text())[:15] if c['name'] not in ('Scion of Halaster', 'Reed Richards, Smartest Man')]


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads(DATA.read_text())):
        base[c['name']] = card(c['name'], set_code='drs', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards):
    ns = [c['name'] for c in json.loads(DATA.read_text())]
    ns += ['Forest', 'Island', 'Swamp', 'Treasure Cruise', 'Opt', 'Grizzly Bears']
    s = table(cards, ns, ns, ns)
    to_phase(s, 'main1', turn=1)
    return s


def activate(s, source, x=None, targets=()):
    mana(s, C=30, U=10, B=10, R=10, G=10, W=10)
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=ability(s, source, '{'), x_value=x, targets=list(targets))
    settle(s)


def draw(s):
    cast(s, 'Treasure Cruise')


@pytest.mark.parametrize('name', RECORDS)
def test_canonical_records_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


def test_words_war_frozen_target_survives_source_departure_and_only_replaces_one_draw(cards):
    s = setup(cards)
    source = put(s, 'Words of War', 'battlefield')
    activate(s, source, targets=['p2'])
    put(s, 'Words of War', 'graveyard')
    cold(s, cards)
    before = len(s.state.zones['p1:hand'])
    stack_library(s, ['Forest', 'Island', 'Swamp'])
    draw(s)
    assert s.state.players['p2'].life == 38
    assert len(s.state.zones['p1:hand']) == before + 2
    roundtrip(s)


def test_ring_commander_policy_consumes_draw_without_collection_fallback(cards):
    s = setup(cards)
    source = put(s, "Ring of Ma'rûf", 'battlefield')
    activate(s, source)
    assert s.state.cards[source.id].zone == 'p1:exile'
    cold(s, cards)
    before = len(s.state.zones['p1:hand'])
    draw(s)
    assert s.state.rules.decision is None
    assert len(s.state.zones['p1:hand']) == before + 2
    roundtrip(s)


def test_lamp_freezes_x_and_cold_private_pick_then_draws_chosen_top(cards):
    s = setup(cards)
    source = put(s, "Aladdin's Lamp", 'battlefield')
    with pytest.raises(ActionError):
        activate(s, source, x=0)
    activate(s, source, x=3)
    stack_library(s, ['Forest', 'Island', 'Swamp'])
    draw(s)
    decision = s.state.rules.decision
    assert decision is not None and decision.player == 'p1'
    assert len(decision.options) == 3
    cold(s, cards)
    chosen = next(o.id for o in s.state.rules.decision.options if o.card_id and s.state.cards[o.card_id].name == 'Swamp')
    answer(s, [chosen])
    assert any(s.state.cards[c].name == 'Swamp' for c in s.state.zones['p1:hand'])
    roundtrip(s)


@pytest.mark.parametrize('pay', [True, False])
def test_crypt_own_inner_draw_is_revealed_and_only_creature_discarded_unless_paid(cards, pay):
    s = setup(cards)
    put(s, "Breathstealer's Crypt", 'battlefield', 'p2')
    stack_library(s, ['Grizzly Bears', 'Forest', 'Island'])
    before = s.state.players['p1'].life
    draw(s)
    d = s.state.rules.decision
    assert d is not None and d.player == 'p1' and d.resume['step'] == 'pay_or_sacrifice'
    assert 'Grizzly Bears' in json.dumps(s.view('p2'))
    cold(s, cards)
    answer(s, ['pay' if pay else 'decline'])
    assert s.state.players['p1'].life == before - (3 if pay else 0)
    bears = next(c for c in s.state.cards.values() if c.owner == 'p1' and c.name == 'Grizzly Bears')
    assert bears.zone == ('p1:hand' if pay else 'p1:graveyard')
    roundtrip(s)


def test_chains_actual_discard_then_draw_and_empty_hand_mill(cards):
    s = setup(cards)
    put(s, 'Chains of Mephistopheles', 'battlefield', 'p2')
    stack_library(s, ['Forest', 'Island', 'Swamp'])
    draw(s)
    while s.state.rules.decision is not None:
        d = s.state.rules.decision
        assert d.player == 'p1' and d.resume['step'] == 'discard'
        cold(s, cards)
        answer(s, [d.options[0].id])
    assert s.state.rules.turn_log.drew.get('p1') == 4
    roundtrip(s)


def test_words_wind_actual_each_player_choice_preserves_controller_authority(cards):
    s = setup(cards)
    source = put(s, 'Words of Wind', 'battlefield')
    other = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    activate(s, source)
    draw(s)
    while s.state.rules.decision is not None:
        d = s.state.rules.decision
        cold(s, cards)
        answer(s, [d.options[0].id])
    assert s.state.cards[source.id].zone == 'p1:hand'
    assert s.state.cards[other.id].zone == 'p2:hand'
    assert s.state.rules.turn_log.drew.get('p1') == 3
    roundtrip(s)


def test_uba_actual_exile_grants_play_and_crypt_does_not_reveal_substituted_draw(cards):
    s = setup(cards)
    put(s, 'Uba Mask', 'battlefield')
    before = s.state.rules.turn_log.drew.get('p1', 0)
    stack_library(s, ['Forest', 'Island', 'Swamp'])
    draw(s)
    assert s.state.rules.turn_log.drew.get('p1', 0) == before
    assert len([p for p in s.state.rules.permissions if p.player == 'p1']) == 3
    cold(s, cards)
    forest = next(c for c in s.state.cards.values() if c.owner == 'p1' and c.name == 'Forest')
    assert forest.zone == 'p1:exile'
    act(s, 'p1', type='play_land', card_id=forest.id)
    assert s.state.cards[forest.id].zone == 'p1:battlefield'
    roundtrip(s)


def test_shared_fate_opponent_library_choice_and_retained_private_look(cards):
    s = setup(cards)
    put(s, 'Shared Fate', 'battlefield')
    stack_library(s, ['Grizzly Bears', 'Forest', 'Island'], pid='p2')
    draw(s)
    for _ in range(3):
        d = s.state.rules.decision
        assert d is not None and d.resume['step'] == 'draw_exile_library'
        cold(s, cards)
        answer(s, ['p2'])
    assert len([p for p in s.state.rules.permissions if p.player == 'p1']) == 3
    assert 'Grizzly Bears' in json.dumps(s.view('p1'))
    put(s, 'Shared Fate', 'graveyard')
    assert 'Grizzly Bears' in json.dumps(s.view('p1'))
    roundtrip(s)


def test_plagiarize_actual_target_drawer_and_controller_receive_different_hand_packets(cards):
    s = setup(cards)
    cast(s, 'Plagiarize', targets=['p2'])
    source = put(s, 'Opt', 'hand', 'p2')
    act(s, 'p2', type='add_mana', player='p2', mana={'U': 1})
    act(s, 'p1', type='pass_priority')
    act(s, 'p2', type='cast_spell', card_id=source.id)
    settle(s)
    if s.state.rules.decision is not None:
        answer(s, [])
    assert s.state.rules.turn_log.drew.get('p1') == 2
    assert s.state.rules.turn_log.drew.get('p2', 0) == 0
    roundtrip(s)


def test_urabrask_opponent_upkeep_record_is_for_opponent_and_survives_source_departure(cards):
    s = setup(cards)
    put(s, 'Urabrask, Heretic Praetor', 'battlefield')
    stack_library(s, ['Grizzly Bears', 'Island'], pid='p2')
    to_phase(s, 'upkeep', turn=2)
    settle(s)
    assert any(r.get('match', {}).get('player') == 'p2' for r in s.state.rules.replacements)
    put(s, 'Urabrask, Heretic Praetor', 'graveyard')
    cold(s, cards)
    to_phase(s, 'main1', turn=2)
    assert s.state.rules.turn_log.drew.get('p2', 0) == 0
    assert any(p.player == 'p2' and p.until == 'end_of_turn' for p in s.state.rules.permissions)
    roundtrip(s)


def test_archmage_six_quests_actual_optional_search_replaces_each_draw(cards):
    s = setup(cards)
    source = put(s, 'Archmage Ascension', 'battlefield')
    act(s, 'p1', type='set_counter', card_id=source.id, kind='quest', value=6)
    before = s.state.rules.turn_log.drew.get('p1', 0)
    draw(s)
    for _ in range(3):
        d = s.state.rules.decision
        assert d is not None
        assert 'replace' in d.resume['step']
        choice = next(o.id for o in d.options if 'Archmage' in o.label)
        cold(s, cards)
        answer(s, [choice])
        d = s.state.rules.decision
        assert d is not None and d.resume['step'] == 'search'
        answer(s, [d.options[0].id])
    assert s.state.rules.turn_log.drew.get('p1', 0) == before
    roundtrip(s)


@pytest.mark.parametrize('pay', [True, False])
def test_weirding_public_top_and_native_other_player_life_payment(cards, pay):
    s = setup(cards)
    put(s, "Zur's Weirding", 'battlefield')
    stack_library(s, ['Grizzly Bears', 'Forest', 'Island'])
    draw(s)
    for _i in range(3):
        d = s.state.rules.decision
        assert d is not None and d.player == 'p2'
        cold(s, cards)
        answer(s, ['pay' if pay else 'decline'])
        if not pay:
            assert s.state.rules.decision.player == 'p3'
            answer(s, ['decline'])
    assert s.state.players['p2'].life == (34 if pay else 40)
    assert s.state.rules.turn_log.drew.get('p1') == (1 if pay else 4)
    roundtrip(s)


def test_shared_fate_static_play_and_retained_look_rest_ws_history(cards, settings):
    from fastapi.testclient import TestClient

    from app.main import create_app

    s = setup(cards)
    put(s, 'Shared Fate', 'battlefield')
    stack_library(s, ['Grizzly Bears', 'Forest', 'Island'], pid='p2')
    draw(s)
    for _ in range(3):
        answer(s, ['p2'])
    with TestClient(create_app(settings)) as client:
        claim_host(client)
        deck = client.post('/api/decks', json={'text': 'Commander\n1 Krenko, Mob Boss\nDeck\n20 Forest'}).json()['id']
        game = client.post('/api/games', json={'mode': 'lan', 'players': [{'name': 'Alice', 'deck_id': deck}, {'name': 'Bob', 'deck_id': deck}]}).json()
        gid = game['game']['id']
        token = client.post('/api/join', json={'code': game['game']['code'], 'spectate': True}).json()['token']
        client.app.state.services.hub.get(gid).game = s
        for departed in (False, True):
            if departed:
                put(s, 'Shared Fate', 'graveyard')
            response = client.get(f'/api/games/{gid}/view', headers={'X-Seat-Token': token})
            assert response.status_code == 200
            with client.websocket_connect(f'/ws/games/{gid}?token={token}') as ws:
                frame = ws.receive_json()
            history = client.get(f'/api/games/{gid}/history', headers={'X-Seat-Token': token})
            for raw in (response.text, json.dumps(frame), history.text):
                assert 'drawn_applied' not in raw and 'Grizzly Bears' not in raw
            assert 'Grizzly Bears' in json.dumps(s.view('p1'))
    roundtrip(s)



def test_sanctuary_optional_draw_step_skip_survives_source_and_expires_next_own_turn(cards):
    import random

    from app.rules import combat
    from app.rules.plan import Plan

    s = setup(cards)
    put(s, 'Island Sanctuary', 'battlefield')
    ground = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    flying = put(s, 'Shivan Dragon', 'battlefield', 'p2')
    islandwalk = put(s, 'River Boa', 'battlefield', 'p2')
    to_phase(s, 'draw', turn=4)
    d = s.state.rules.decision
    assert d is not None
    choice = next(o.id for o in d.options if 'Island Sanctuary' in o.label)
    cold(s, cards)
    answer(s, [choice])
    put(s, 'Island Sanctuary', 'graveyard')
    plan = Plan(s.state, 'p1', cards, random.Random(1))
    assert combat.attack_forbidden(plan, plan.ch(plan.state.cards[ground.id]), 'p1')
    assert not combat.attack_forbidden(plan, plan.ch(plan.state.cards[flying.id]), 'p1')
    assert not combat.attack_forbidden(plan, plan.ch(plan.state.cards[islandwalk.id]), 'p1')
    assert not combat.attack_forbidden(plan, plan.ch(plan.state.cards[ground.id]), 'p3')
    to_phase(s, 'upkeep', turn=7)
    plan = Plan(s.state, 'p1', cards, random.Random(1))
    assert not combat.attack_forbidden(plan, plan.ch(plan.state.cards[ground.id]), 'p1')
    roundtrip(s)


def test_archmage_end_step_quest_requires_actual_two_draws_and_rechecks(cards):
    s = setup(cards)
    source = put(s, 'Archmage Ascension', 'battlefield')
    draw(s)
    to_phase(s, 'end', turn=1)
    settle(s)
    if s.state.rules.decision is not None:
        answer(s, ['yes'])
    assert s.state.cards[source.id].counters.get('quest') == 1
    roundtrip(s)


def test_crypt_inner_count_replacement_does_not_reveal_or_charge_substituted_cards(cards):
    s = setup(cards)
    put(s, "Breathstealer's Crypt", 'battlefield', 'p2')
    put(s, 'Phial of Galadriel', 'battlefield')
    for cid in list(s.state.zones['p1:hand']):
        act(s, 'p1', type='move', card_ids=[cid], to={'player': 'p1', 'zone': 'graveyard'})
    stack_library(s, ['Grizzly Bears', 'Forest', 'Island', 'Swamp'])
    draw(s)
    while s.state.rules.decision is not None:
        d = s.state.rules.decision
        assert d.resume['step'] != 'pay_or_sacrifice'
        selected = next((o.id for o in d.options if "Breathstealer" in o.label), d.options[0].id)
        cold(s, cards)
        answer(s, [selected])
    assert s.state.players['p1'].life == 40
    assert not any(p.get('name') == 'Grizzly Bears' for p in s.view('p2')['cards'].values())
    roundtrip(s)


def test_urabrask_own_upkeep_independent_exile_and_play_line(cards):
    s = setup(cards)
    put(s, 'Urabrask, Heretic Praetor', 'battlefield')
    to_phase(s, 'upkeep', turn=4)
    settle(s)
    assert any(p.player == 'p1' and p.until == 'end_of_turn' for p in s.state.rules.permissions)
    roundtrip(s)


def test_shared_fate_actual_foreign_land_owner_and_source_reentry_does_not_restore_authority(cards):
    s = setup(cards)
    put(s, 'Shared Fate', 'battlefield')
    stack_library(s, ['Forest', 'Island', 'Grizzly Bears'], pid='p2')
    draw(s)
    for _ in range(3):
        answer(s, ['p2'])
    forest = next(c for c in s.state.cards.values() if c.name == 'Forest' and c.owner == 'p2')
    act(s, 'p1', type='play_land', card_id=forest.id)
    assert s.state.cards[forest.id].controller == 'p1' and s.state.cards[forest.id].owner == 'p2'
    creature = next(c for c in s.state.cards.values() if c.name == 'Grizzly Bears' and c.owner == 'p2')
    put(s, 'Shared Fate', 'graveyard')
    mana(s, G=1, C=1)
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=creature.id)
    put(s, 'Shared Fate', 'battlefield')
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=creature.id)
    roundtrip(s)


def test_uba_actual_normal_cost_spell_and_source_leaving_revokes_other_exiled_cards(cards):
    s = setup(cards)
    put(s, 'Uba Mask', 'battlefield')
    stack_library(s, ['Grizzly Bears', 'Forest', 'Island'])
    draw(s)
    creature = next(c for c in s.state.cards.values() if c.owner == 'p1' and c.name == 'Grizzly Bears')
    mana(s, G=1, C=1)
    act(s, 'p1', type='cast_spell', card_id=creature.id)
    settle(s)
    assert s.state.cards[creature.id].zone == 'p1:battlefield'
    land = next(c for c in s.state.cards.values() if c.name == 'Forest' and c.owner == 'p1' and c.zone == 'p1:exile')
    put(s, 'Uba Mask', 'graveyard')
    with pytest.raises(ActionError):
        act(s, 'p1', type='play_land', card_id=land.id)
    roundtrip(s)


# (Reed Richards, Smartest Man: wave 110J, tests/test_rules_wave110j_last.py; Scion of Halaster: tests/test_rules_wave110c_scion.py)


def test_face_down_foreign_land_rest_authority_type_privacy_and_land_limit(cards, settings):
    from fastapi.testclient import TestClient

    from app.main import create_app

    s = setup(cards)
    put(s, 'Shared Fate', 'battlefield')
    stack_library(s, ['Forest', 'Grizzly Bears', 'Island'], pid='p2')
    draw(s)
    for _ in range(3):
        answer(s, ['p2'])
    cold(s, cards)
    forest = next(c for c in s.state.cards.values() if c.owner == 'p2' and c.name == 'Forest')
    creature = next(c for c in s.state.cards.values() if c.owner == 'p2' and c.name == 'Grizzly Bears')
    island = next(c for c in s.state.cards.values() if c.owner == 'p2' and c.name == 'Island' and c.face_down)
    assert forest.face_down and creature.face_down
    with TestClient(create_app(settings)) as client:
        claim_host(client)
        room = client.app.state.services.hub.create_room(s, mode='lan')
        room.seats['p1'].token = 'drawer-token'
        room.seats['p3'].token = 'unauthorized-token'
        errors = []
        before = s.state.model_dump(mode='json')
        for cid in (forest.id, creature.id):
            response = client.post(f'/api/games/{room.id}/actions', headers={'X-Seat-Token': 'unauthorized-token'},
                                   json={'action': {'type': 'play_land', 'card_id': cid}})
            assert response.status_code == 409
            errors.append(response.json())
        assert errors[0] == errors[1]
        assert 'authorized' in json.dumps(errors)
        assert s.state.model_dump(mode='json') == before
        response = client.post(f'/api/games/{room.id}/actions', headers={'X-Seat-Token': 'drawer-token'},
                               json={'action': {'type': 'play_land', 'card_id': forest.id}})
        assert response.status_code == 200, response.text
        assert s.state.cards[forest.id].zone == 'p1:battlefield' and not s.state.cards[forest.id].face_down
        assert s.state.cards[forest.id].owner == 'p2' and s.state.cards[forest.id].controller == 'p1'
        with client.websocket_connect(f'/ws/games/{room.id}?token=unauthorized-token') as ws:
            raw = json.dumps(ws.receive_json())
        assert 'Grizzly Bears' not in raw and 'drawn_applied' not in raw
        response = client.post(f'/api/games/{room.id}/actions', headers={'X-Seat-Token': 'drawer-token'},
                               json={'action': {'type': 'play_land', 'card_id': island.id}})
        assert response.status_code == 409 and 'already played' in response.text
    roundtrip(s)


def test_weirding_empty_library_still_allows_other_player_to_pay_and_prevent_draw_loss(cards):
    s = setup(cards)
    put(s, "Zur's Weirding", 'battlefield')
    library = list(s.state.zones['p1:library'])
    act(s, 'p1', type='move', card_ids=library, to={'player': 'p1', 'zone': 'exile'})
    draw(s)
    for _ in range(3):
        d = s.state.rules.decision
        assert d is not None and d.player == 'p2'
        cold(s, cards)
        answer(s, ['pay'])
    assert 'p1' not in s.state.rules.lost and 'p1' not in s.state.rules.drew_from_empty
    assert s.state.players['p2'].life == 34
    roundtrip(s)


def test_words_war_departed_target_new_object_is_not_damaged_but_draw_is_replaced(cards):
    s = setup(cards)
    source = put(s, 'Words of War', 'battlefield')
    target = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    activate(s, source, targets=[target.id])
    put(s, 'Grizzly Bears', 'graveyard', 'p2')
    target = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    cold(s, cards)
    draw(s)
    assert s.state.cards[target.id].damage == 0
    assert s.state.rules.turn_log.drew.get('p1') == 3
    roundtrip(s)


@pytest.mark.parametrize('mode', ['lamp', 'weirding'])
def test_private_lamp_packet_and_public_weirding_top_rest_ws(cards, settings, mode):
    from fastapi.testclient import TestClient

    from app.main import create_app

    s = setup(cards)
    if mode == 'lamp':
        source = put(s, "Aladdin's Lamp", 'battlefield')
        activate(s, source, x=3)
    else:
        put(s, "Zur's Weirding", 'battlefield')
    stack_library(s, ['Grizzly Bears', 'Forest', 'Island'])
    draw(s)
    cold(s, cards)
    with TestClient(create_app(settings)) as client:
        claim_host(client)
        room = client.app.state.services.hub.create_room(s, mode='lan')
        room.seats['p2'].token = 'observer-token'
        response = client.get(f'/api/games/{room.id}/view', headers={'X-Seat-Token': 'observer-token'})
        assert response.status_code == 200
        with client.websocket_connect(f'/ws/games/{room.id}?token=observer-token') as ws:
            frame = ws.receive_json()
        for raw in (response.text, json.dumps(frame)):
            assert ('Grizzly Bears' in raw) == (mode == 'weirding')
            assert 'drawn_applied' not in raw
        if mode == 'lamp':
            assert 'options' not in response.json()['rules']['decision']
        else:
            assert response.json()['rules']['decision']['player'] == 'p2'
    roundtrip(s)

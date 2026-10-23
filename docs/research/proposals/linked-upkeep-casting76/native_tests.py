"""Real Ian exile producers and Kaya loyalty/emblem authorities keep their native scopes."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import casting, coverage, designations
from app.rules.plan import Plan
from tests import test_rules_exile_cast_outcomes45_foundation as gameplay
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana, wait_priority
from tests.test_rules_controller_tutors import answer
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_look import settle
from tests.test_rules_ordered_tutor_continuations import cast
from tests.test_rules_refused_look import stack_library
from tests.test_rules_wave4h_activation_costs import ability
from tests.test_rules_wave30m_durations import to_phase

DATA = json.loads((Path(__file__).parent / 'fixtures/linked_upkeep_casting76_cards.json').read_text())
IAN, KAYA = 'Ian Malcolm, Chaotician', 'Kaya the Inexorable'
DOG = 'Isamaru, Hound of Konda'


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for filename in ['exile_outcomes42_cards.json', 'exile_cast_outcomes45_cards.json',
                     'fight_exile_receipts65_cards.json', 'top_library_authorities69_cards.json',
                     'pooled_casting_authorities71_cards.json']:
        for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures' / filename).read_text())):
            base[c['name']] = card(c['name'], set_code='lc76', number=str(i), **{k: v for k, v in c.items() if k not in {'name', 'set_code'}})
    for i, c in enumerate(DATA):
        base[c['name']] = card(c['name'], set_code='lc76', number='a' + str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards):
    return gameplay.setup(cards, *[c['name'] for c in DATA], 'Lightning Bolt', 'Disperse', 'Counterspell', 'Sol Ring', 'Forest',
                          'Jacob Hauken, Inspector // Hauken\'s Insight')


def exile_draw(s, pid, name):
    draw = put(s, 'Divination', 'hand', pid=pid)
    top = stack_library(s, ['Forest', 'Sol Ring', name], pid=pid)
    mana(s, pid=pid, C=2, U=1)
    wait_priority(s, pid)
    act(s, pid, type='cast_spell', card_id=draw.id)
    settle(s)
    assert s.state.cards[top[2]].zone == pid + ':exile'
    return top[2]


def emblem(s):
    source = cast(s, KAYA)
    act(s, 'p1', type='set_counter', card_id=source.id, kind='loyalty', value=7)
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=ability(s, source, '−7'))
    settle(s)
    assert source.zone == 'p1:graveyard'
    assert any(designations.emblem_card(c) and c.controller == 'p1' for c in s.state.cards.values())
    return source


@pytest.mark.parametrize('name', [IAN, KAYA])
def test_canonical_whole76(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


def test_ian_real_second_draw_links_foreign_spells_one_per_active_players_turn(cards):
    s = setup(cards)
    source = cast(s, IAN)
    to_phase(s, 'main1', turn=2)
    settle(s)
    bear = exile_draw(s, 'p2', 'Grizzly Bears')
    to_phase(s, 'main1', turn=3)
    settle(s)
    bolt = exile_draw(s, 'p3', 'Lightning Bolt')
    to_phase(s, 'main1', turn=4)
    settle(s)
    act(s, 'p1', type='clear_mana')
    mana(s, C=2)
    assert casting.castable(s.state, 'p1', s.state.cards[bear], cards)
    act(s, 'p1', type='cast_spell', card_id=bear)
    settle(s)
    assert s.state.cards[bear].zone == 'p1:battlefield' and s.state.cards[bear].owner == 'p2'
    mana(s, C=1)
    before = s.state.model_dump(mode='json')
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=bolt, targets=['p2'])
    assert s.state.model_dump(mode='json') == before
    act(s, 'p1', type='set_controller', card_ids=[source.id], player='p2')
    before = s.state.model_dump(mode='json')
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=bolt, targets=['p2'])
    assert s.state.model_dump(mode='json') == before
    to_phase(s, 'main1', turn=5)
    settle(s)
    act(s, 'p2', type='clear_mana')
    mana(s, pid='p2', C=1)
    wait_priority(s, 'p2')
    life = s.state.players['p1'].life
    act(s, 'p2', type='cast_spell', card_id=bolt, targets=['p1'])
    settle(s)
    assert s.state.players['p1'].life == life - 3 and s.state.cards[bolt].zone == 'p3:graveyard'
    roundtrip(s)


@pytest.mark.parametrize('zone', ['hand', 'graveyard', 'exile'])
def test_actual_kaya_minus_seven_creates_native_upkeep_emblem_pool_in_each_zone(cards, zone):
    s = setup(cards)
    emblem(s)
    target = put(s, DOG, zone)
    nonlegend = put(s, 'Grizzly Bears', zone)
    land = put(s, 'Flagstones of Trokair', zone)
    foreign = put(s, DOG, 'exile', pid='p2')
    to_phase(s, 'upkeep', turn=4)
    settle(s)
    d = s.state.rules.decision
    assert d and d.kind == 'choose_cards'
    offered = {o.id for o in d.options}
    target = next(c for c in s.state.cards.values() if c.name == DOG and c.owner == 'p1')
    nonlegend = next(c for c in s.state.cards.values() if c.name == 'Grizzly Bears' and c.owner == 'p1')
    land = next(c for c in s.state.cards.values() if c.name == 'Flagstones of Trokair' and c.owner == 'p1')
    foreign = next(c for c in s.state.cards.values() if c.name == DOG and c.owner == 'p2')
    assert target.id in offered and not {nonlegend.id, land.id, foreign.id} & offered
    answer(s, [target.id])
    settle(s)
    target = next(c for c in s.state.cards.values() if c.name == DOG and c.owner == 'p1')
    assert target.zone == 'p1:battlefield'
    assert s.state.rules.payments[s.state.rules.object_id(target.id)].alternative == 'free'
    roundtrip(s)


def test_native_kaya_ghostform_survives_counter_removal_and_source_departure(cards):
    s = setup(cards)
    source = cast(s, KAYA)
    host = put(s, 'Grizzly Bears', 'battlefield')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=ability(s, source, '+1'), targets=[host.id], target_counts=[1])
    settle(s)
    assert host.counters.get('ghostform') == 1
    act(s, 'p1', type='set_counter', card_id=host.id, kind='ghostform', value=0)
    cast(s, 'Disperse', targets=[source.id])
    cast(s, 'Lightning Bolt', targets=[host.id])
    assert source.zone == 'p1:hand' and host.zone == 'p1:hand'
    spirits = [c for c in s.state.cards.values() if c.is_token and 'Spirit' in Plan(s.state, 'p1', cards, None).ch(c).subtypes]
    assert len(spirits) == 1 and Plan(s.state, 'p1', cards, None).ch(spirits[0]).pt == (1, 1)
    assert 'flying' in Plan(s.state, 'p1', cards, None).ch(spirits[0]).keywords
    roundtrip(s)


def test_actual_kaya_minus_three_pays_loyalty_and_exiles_the_original_foreign_nonland(cards):
    s = setup(cards)
    source = cast(s, KAYA)
    target = put(s, 'Sol Ring', 'battlefield', pid='p2')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=ability(s, source, '−3'), targets=[target.id])
    settle(s)
    assert source.counters['loyalty'] == 2 and target.zone == 'p2:exile'
    roundtrip(s)


def test_two_native_ghostform_instances_return_once_but_create_two_spirits(cards):
    s = setup(cards)
    source = cast(s, KAYA)
    host = put(s, 'Grizzly Bears', 'battlefield')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=ability(s, source, '+1'), targets=[host.id], target_counts=[1])
    settle(s)
    to_phase(s, 'main1', turn=4)
    settle(s)
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=ability(s, source, '+1'), targets=[host.id], target_counts=[1])
    settle(s)
    cast(s, 'Lightning Bolt', targets=[host.id])
    assert host.zone == 'p1:hand'
    spirits = [c for c in s.state.cards.values() if c.is_token and 'Spirit' in Plan(s.state, 'p1', cards, None).ch(c).subtypes]
    assert len(spirits) == 2
    roundtrip(s)


def test_ian_owner_and_active_turn_limits_do_not_turn_into_instant_authority(cards):
    s = setup(cards)
    cast(s, IAN)
    to_phase(s, 'main1', turn=2)
    settle(s)
    bolt = exile_draw(s, 'p2', 'Lightning Bolt')
    act(s, 'p1', type='clear_mana')
    mana(s, C=1)
    wait_priority(s, 'p1')
    before = s.state.model_dump(mode='json')
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=bolt, targets=['p2'])
    assert s.state.model_dump(mode='json') == before
    mana(s, pid='p2', C=1)
    wait_priority(s, 'p2')
    before = s.state.model_dump(mode='json')
    with pytest.raises(ActionError):
        act(s, 'p2', type='cast_spell', card_id=bolt, targets=['p1'])
    assert s.state.model_dump(mode='json') == before
    roundtrip(s)


def test_ian_new_incarnation_has_no_access_to_the_original_linked_pool(cards):
    s = setup(cards)
    source = cast(s, IAN)
    to_phase(s, 'main1', turn=2)
    settle(s)
    foreign = exile_draw(s, 'p2', 'Grizzly Bears')
    to_phase(s, 'main1', turn=4)
    settle(s)
    cast(s, 'Disperse', targets=[source.id])
    source = cast(s, IAN)
    act(s, 'p1', type='clear_mana')
    mana(s, C=2)
    assert not casting.castable(s.state, 'p1', s.state.cards[foreign], cards)
    before = s.state.model_dump(mode='json')
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=foreign)
    assert s.state.model_dump(mode='json') == before
    roundtrip(s)


def test_ian_any_type_mana_does_not_invent_snow_source_provenance(cards):
    s = setup(cards)
    cast(s, IAN)
    to_phase(s, 'main1', turn=2)
    settle(s)
    golem = exile_draw(s, 'p2', 'Icehide Golem')
    to_phase(s, 'main1', turn=4)
    settle(s)
    act(s, 'p1', type='clear_mana')
    mana(s, C=1)
    assert not casting.castable(s.state, 'p1', s.state.cards[golem], cards)
    before = s.state.model_dump(mode='json')
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=golem)
    assert s.state.model_dump(mode='json') == before
    land = put(s, 'Snow-Covered Island', 'battlefield')
    act(s, 'p1', type='activate_ability', card_id=land.id, ability=0)
    act(s, 'p1', type='cast_spell', card_id=golem)
    settle(s)
    assert s.state.cards[golem].zone == 'p1:battlefield'
    roundtrip(s)


def test_kaya_hidden_hand_without_an_eligible_legendary_still_gets_a_private_choice(cards):
    s = setup(cards)
    emblem(s)
    # Remove public alternatives and private legendary cards, not ordinary hand cards.
    legends = [c.id for c in s.state.cards.values() if c.owner == 'p1'
               and c.zone.endswith((':hand', ':graveyard', ':exile'))
               and 'Legendary' in Plan(s.state, 'p1', cards, None).ch(c).supertypes]
    if legends:
        act(s, 'p1', type='move', card_ids=legends, to={'player': 'p1', 'zone': 'library'})
    hand = put(s, 'Grizzly Bears', 'hand')
    to_phase(s, 'upkeep', turn=4)
    settle(s)
    d = s.state.rules.decision
    assert d and d.kind == 'choose_cards' and not d.options
    # Whether any private hand card qualified is not publicly disclosed.
    assert s.view('p1')['rules']['decision']['options'] == []
    other = s.view('p2')['rules']['decision']
    assert 'options' not in other and other['source_id'] is None
    hidden = json.dumps(s.view('p2'))
    hand = next(c for c in s.state.cards.values() if c.name == 'Grizzly Bears' and c.owner == 'p1')
    assert hand.id not in hidden
    answer(s, [])
    assert s.state.rules.decision is None
    roundtrip(s)


def test_kaya_emblem_can_cast_an_owned_facedown_legendary_that_jacob_allows_looking_at(cards):
    from app.game.visibility import can_see

    s = setup(cards)
    jacob = cast(s, "Jacob Hauken, Inspector // Hauken's Insight")
    cast(s, 'Expedite', targets=[jacob.id])
    put(s, DOG, 'hand')
    act(s, 'p1', type='clear_mana')
    act(s, 'p1', type='activate_ability', card_id=jacob.id, ability=ability(s, jacob, '{T}:'))
    settle(s)
    target = next(c for c in s.state.cards.values() if c.name == DOG and c.owner == 'p1')
    answer(s, [target.id])
    settle(s)
    jacob = next(c for c in s.state.cards.values() if c.name.startswith('Jacob Hauken') and c.owner == 'p1')
    assert jacob.face == 0  # Its front provides looking, not an independent cast permission.
    target = next(c for c in s.state.cards.values() if c.name == DOG and c.owner == 'p1')
    assert target.face_down and can_see(s.state, target, 'p1') and not can_see(s.state, target, 'p2')
    emblem(s)
    to_phase(s, 'upkeep', turn=4)
    settle(s)
    target = next(c for c in s.state.cards.values() if c.name == DOG and c.owner == 'p1')
    d = s.state.rules.decision
    assert d and target.id in {o.id for o in d.options}
    answer(s, [target.id])
    settle(s)
    target = next(c for c in s.state.cards.values() if c.name == DOG and c.owner == 'p1')
    assert target.zone == 'p1:battlefield' and not target.face_down
    roundtrip(s)


def test_kaya_emblem_cannot_use_known_but_unlookable_facedown_legendary_exiled_by_gonti(cards):
    from app.game.visibility import can_see

    s = setup(cards)
    emblem(s)
    to_phase(s, 'main1', turn=2)
    settle(s)
    stack_library(s, [DOG, 'Forest', 'Sol Ring', 'Grizzly Bears'])
    gonti = put(s, 'Gonti, Lord of Luxury', 'hand', pid='p2')
    mana(s, pid='p2', C=2, B=2)
    wait_priority(s, 'p2')
    act(s, 'p2', type='cast_spell', card_id=gonti.id)
    settle(s)
    d = s.state.rules.decision
    assert d and 'p1' in {o.id for o in d.options}
    answer(s, ['p1'])
    target = next(c for c in s.state.cards.values() if c.name == DOG and c.owner == 'p1')
    answer(s, [target.id])
    settle(s)
    target = next(c for c in s.state.cards.values() if c.name == DOG and c.owner == 'p1')
    assert target.face_down and can_see(s.state, target, 'p2') and not can_see(s.state, target, 'p1')
    to_phase(s, 'upkeep', turn=4)
    settle(s)
    target = next(c for c in s.state.cards.values() if c.name == DOG and c.owner == 'p1')
    d = s.state.rules.decision
    assert d and target.id not in {o.id for o in d.options}
    assert not any(DOG in o['label'] for o in s.view('p1')['rules']['decision']['options'])
    answer(s, [])
    roundtrip(s)


@pytest.mark.parametrize('mode', ['ian', 'kaya_choice'])
def test_genuine_fresh_process_restores_native_link_and_emblem_choice76(cards, tmp_path, mode):
    import os
    import subprocess
    import sys

    s = setup(cards)
    if mode == 'ian':
        cast(s, IAN)
        to_phase(s, 'main1', turn=2)
        settle(s)
        selected = exile_draw(s, 'p2', 'Grizzly Bears')
        to_phase(s, 'main1', turn=4)
        settle(s)
        act(s, 'p1', type='clear_mana')
        mana(s, C=2)
    else:
        emblem(s)
        put(s, DOG, 'hand')
        to_phase(s, 'upkeep', turn=4)
        settle(s)
        selected = next(c.id for c in s.state.cards.values() if c.name == DOG and c.owner == 'p1')
        assert s.state.rules.decision
    saved = tmp_path / 'linked76.json'
    saved.write_text(s.state.model_dump_json())
    code = r'''
import sys
from pathlib import Path
from app.cards.repository import CardRepository
from app.cards.images import ImageStore
from app.game.state import GameState
from app.game.session import GameSession
from app.rules import casting,designations
from tests.test_rules_library_look import settle
from tests.test_rules_designations import roundtrip
from tests.test_rules_controller_tutors import answer
from tests.game_helpers import act
r=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=r)
mode,selected=sys.argv[3:]
if mode=='ian':
 assert casting.castable(s.state,'p1',s.state.cards[selected],r)
 act(s,'p1',type='cast_spell',card_id=selected)
 settle(s)
 assert s.state.cards[selected].owner=='p2'
else:
 assert any(designations.emblem_card(c) for c in s.state.cards.values())
 assert selected in {o.id for o in s.state.rules.decision.options}
 answer(s,[selected]);settle(s)
assert s.state.cards[selected].zone=='p1:battlefield'
roundtrip(s)
r.close()
'''
    backend = Path(__file__).resolve().parents[1]
    result = subprocess.run([sys.executable, '-c', code, str(saved), str(cards.db_path), mode, selected],
                            cwd=backend, env={**os.environ, 'PYTHONPATH': str(backend)},
                            capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stdout + result.stderr

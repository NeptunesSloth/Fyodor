"""Real Ian exile producers and Kaya loyalty/emblem authorities keep their native scopes."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import casting, coverage
from app.rules.plan import Plan
from tests import test_rules_exile_cast_outcomes45_foundation as gameplay
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana, wait_priority
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_look import settle
from tests.test_rules_ordered_tutor_continuations import cast
from tests.test_rules_refused_look import stack_library
from tests.test_rules_wave4h_activation_costs import ability
from tests.test_rules_wave30m_durations import to_phase

DATA = json.loads((Path(__file__).parent / 'fixtures/graveyard_windows80_cards.json').read_text())
CLASS, CASE = 'Advanced Reconstruction', 'Case of the Uneaten Feast'
NAMES = [CLASS, CASE]
BIRGI = 'Birgi, God of Storytelling // Harnfel, Horn of Bounty'
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
    return gameplay.setup(cards, *[c['name'] for c in DATA], 'Lightning Bolt', 'Disperse', 'Counterspell', 'Sol Ring', 'Forest', 'Rest in Peace',
                          'Jacob Hauken, Inspector // Hauken\'s Insight')




@pytest.mark.parametrize('name', NAMES)
def test_whole_canonical80(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


def solved_case(s):
    source = cast(s, CASE)
    cast(s, 'Healing Salve', modes=[0], targets=['p1'])
    cast(s, 'Grizzly Bears')
    cast(s, 'Rivaz of the Claw')
    to_phase(s, 'end', turn=1)
    settle(s)
    assert 'Solved' in source.choices
    to_phase(s, 'main1', turn=4)
    settle(s)
    return source


def test_case_is_solved_by_actual_life_gain_and_sacrifice_grants_only_current_creature_objects80(cards):
    s = setup(cards)
    source = solved_case(s)
    bear = put(s, 'Grizzly Bears', 'graveyard')
    rivaz = put(s, 'Rivaz of the Claw', 'graveyard')
    noncreature = put(s, 'Giant Growth', 'graveyard')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=ability(s, source, 'Solved'))
    settle(s)
    assert source.zone == 'p1:graveyard'
    mana(s, C=2, G=1, B=1, R=1)
    assert casting.castable(s.state, 'p1', bear, cards) and casting.castable(s.state, 'p1', rivaz, cards)
    assert not casting.castable(s.state, 'p1', noncreature, cards)
    late = put(s, 'Elvish Mystic', 'graveyard')
    assert not casting.castable(s.state, 'p1', late, cards)
    mana(s, C=2, G=1, B=1, R=1)
    act(s, 'p1', type='cast_spell', card_id=bear.id)
    settle(s)
    act(s, 'p1', type='cast_spell', card_id=rivaz.id)
    settle(s)
    assert bear.zone == rivaz.zone == 'p1:battlefield'
    roundtrip(s)


def test_case_current_front_creature_can_cast_its_noncreature_reverse_spell80(cards):
    s = setup(cards)
    source = solved_case(s)
    target = put(s, BIRGI, 'graveyard')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=ability(s, source, 'Solved'))
    settle(s)
    act(s, 'p1', type='clear_mana')
    mana(s, C=4, R=1)
    act(s, 'p1', type='cast_spell', card_id=target.id, face=1)
    settle(s)
    assert target.zone == 'p1:battlefield' and target.face == 1
    assert Plan(s.state, 'p1', cards, None).ch(target).types == frozenset({'Artifact'})
    roundtrip(s)


def test_advanced_actual_first_main_mills_then_random_exile_allows_ordinary_spell80(cards):
    s = setup(cards)
    cast(s, CLASS)
    to_phase(s, 'upkeep', turn=4)
    settle(s)
    top = stack_library(s, ['Forest', 'Divination'])
    to_phase(s, 'main1', turn=4)
    settle(s)
    target = s.state.cards[top[1]]
    assert target.zone == 'p1:exile'
    act(s, 'p1', type='clear_mana')
    mana(s, C=2, U=1)
    assert casting.castable(s.state, 'p1', target, cards)
    before = len(s.state.zones['p1:hand'])
    act(s, 'p1', type='cast_spell', card_id=target.id)
    settle(s)
    assert target.zone == 'p1:graveyard' and len(s.state.zones['p1:hand']) == before + 2
    roundtrip(s)


def test_unsolved_case_cannot_activate_and_its_sacrifice_cost_is_atomic80(cards):
    s = setup(cards)
    source = cast(s, CASE)
    assert 'Solved' not in source.choices
    before = s.state.model_dump(mode='json')
    with pytest.raises(ActionError):
        act(s, 'p1', type='activate_ability', card_id=source.id, ability=2)
    assert s.state.model_dump(mode='json') == before and source.zone == 'p1:battlefield'


def test_case_window_expires_and_does_not_recover_a_countered_new_graveyard_object80(cards):
    s = setup(cards)
    source = solved_case(s)
    target = put(s, 'Rivaz of the Claw', 'graveyard')
    unused = put(s, 'Llanowar Elves', 'graveyard')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=ability(s, source, 'Solved'))
    settle(s)
    mana(s, C=1, B=1, R=1, G=1)
    old = s.state.rules.object_id(target.id)
    act(s, 'p1', type='cast_spell', card_id=target.id)
    counter = put(s, 'Counterspell', 'hand', pid='p2')
    mana(s, pid='p2', U=2)
    wait_priority(s, 'p2')
    act(s, 'p2', type='cast_spell', card_id=counter.id, targets=[target.id])
    settle(s)
    assert target.zone == 'p1:graveyard' and s.state.rules.object_id(target.id) != old
    mana(s, C=1, B=1, R=1)
    assert not casting.castable(s.state, 'p1', target, cards)
    assert casting.castable(s.state, 'p1', unused, cards)
    to_phase(s, 'main1', turn=7)
    settle(s)
    mana(s, G=1)
    assert not casting.castable(s.state, 'p1', unused, cards)
    roundtrip(s)


def test_advanced_actual_land_play_obeys_normal_one_land_per_turn80(cards):
    s = setup(cards)
    cast(s, CLASS)
    to_phase(s, 'upkeep', turn=4)
    settle(s)
    top = stack_library(s, ['Giant Growth', 'Forest'])
    to_phase(s, 'main1', turn=4)
    settle(s)
    target = s.state.cards[top[1]]
    assert target.zone == 'p1:exile'
    act(s, 'p1', type='play_land', card_id=target.id)
    assert target.zone == 'p1:battlefield'
    other = next(c for c in s.state.cards.values() if c.name == 'Forest' and c.owner == 'p1'
                 and c.zone == 'p1:library')
    act(s, 'p1', type='move', card_ids=[other.id], to={'player': 'p1', 'zone': 'hand'})
    before = s.state.model_dump(mode='json')
    with pytest.raises(ActionError):
        act(s, 'p1', type='play_land', card_id=other.id)
    assert s.state.model_dump(mode='json') == before
    roundtrip(s)


def test_advanced_real_class_levels_damage_on_graveyard_exit_and_reduce_nonhand_spell80(cards):
    from tests.test_rules_wave16a_class import bar, level

    s = setup(cards)
    source = cast(s, CLASS)
    act(s, 'p1', type='clear_mana')
    mana(s, C=2, R=2)
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=bar(s, source, 2))
    settle(s)
    assert level(s, source) == 2
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=bar(s, source, 3))
    settle(s)
    assert level(s, source) == 3
    life = {p: s.state.players[p].life for p in ['p2', 'p3']}
    to_phase(s, 'upkeep', turn=4)
    settle(s)
    top = stack_library(s, ['Forest', 'Divination'])
    to_phase(s, 'main1', turn=4)
    settle(s)
    target = s.state.cards[top[1]]
    assert target.zone == 'p1:exile'
    assert all(s.state.players[p].life == life[p] - 2 for p in life)
    act(s, 'p1', type='clear_mana')
    mana(s, U=1)
    assert casting.castable(s.state, 'p1', target, cards)
    act(s, 'p1', type='cast_spell', card_id=target.id)
    settle(s)
    assert target.zone == 'p1:graveyard' and not s.state.players['p1'].mana
    roundtrip(s)


def test_advanced_mill_replaced_with_exile_does_not_invent_a_graveyard_exile_receipt80(cards):
    s = setup(cards)
    cast(s, CLASS)
    cast(s, 'Rest in Peace')
    to_phase(s, 'upkeep', turn=4)
    settle(s)
    top = stack_library(s, ['Forest', 'Divination'])
    to_phase(s, 'main1', turn=4)
    settle(s)
    target = s.state.cards[top[1]]
    assert target.zone == 'p1:exile' and not s.state.zones.get('p1:graveyard')
    mana(s, C=2, U=1)
    assert not casting.castable(s.state, 'p1', target, cards)
    assert not s.state.rules.decision
    roundtrip(s)


def test_advanced_level_two_observes_actual_multi_card_evidence_cost_as_one_exit_batch80(cards):
    from tests.test_rules_wave16a_class import bar

    s = setup(cards)
    source = cast(s, CLASS)
    researcher = cast(s, 'Forensic Researcher')
    mana(s, C=1, R=1)
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=bar(s, source, 2))
    settle(s)
    to_phase(s, 'main1', turn=4)
    settle(s)
    evidence = [put(s, n, 'graveyard') for n in ['Divination', 'Rivaz of the Claw']]
    target = put(s, 'Grizzly Bears', 'battlefield', pid='p2')
    life = {p: s.state.players[p].life for p in ['p2', 'p3']}
    act(s, 'p1', type='activate_ability', card_id=researcher.id,
        ability=ability(s, researcher, '{T}, Collect evidence'), targets=[target.id],
        cost_choices=[{'component': 1, 'cards': [c.id for c in evidence]}])
    settle(s)
    assert all(s.state.cards[c.id].zone == 'p1:exile' for c in evidence)
    assert all(s.state.players[p].life == life[p] - 2 for p in life) and target.tapped
    roundtrip(s)


def test_advanced_random_choice_uses_only_own_current_graveyard_and_expires80(cards):
    s = setup(cards)
    cast(s, CLASS)
    own = put(s, 'Divination', 'graveyard')
    foreign = put(s, 'Grizzly Bears', 'graveyard', pid='p2')
    to_phase(s, 'upkeep', turn=4)
    settle(s)
    top = stack_library(s, ['Giant Growth', 'Forest'])
    to_phase(s, 'main1', turn=4)
    settle(s)
    choices = [s.state.cards[own.id], s.state.cards[top[1]]]
    exiled = [c for c in choices if c.zone == 'p1:exile']
    assert len(exiled) == 1 and foreign.zone == 'p2:graveyard'
    target = exiled[0]
    to_phase(s, 'main1', turn=7)
    settle(s)
    mana(s, C=2, U=1)
    if target.name == 'Divination':
        assert not casting.castable(s.state, 'p1', target, cards)
    else:
        before = s.state.model_dump(mode='json')
        with pytest.raises(ActionError):
            act(s, 'p1', type='play_land', card_id=target.id)
        assert s.state.model_dump(mode='json') == before
    roundtrip(s)


@pytest.mark.parametrize('mode', ['case_mdfc', 'class_exile'])
def test_genuine_fresh_process_restores_exact_finite_graveyard_window80(cards, tmp_path, mode):
    import os
    import subprocess
    import sys

    s = setup(cards)
    if mode == 'case_mdfc':
        source = solved_case(s)
        target = put(s, BIRGI, 'graveyard')
        act(s, 'p1', type='activate_ability', card_id=source.id, ability=ability(s, source, 'Solved'))
        settle(s)
        act(s, 'p1', type='clear_mana')
        mana(s, C=4, R=1)
    else:
        cast(s, CLASS)
        to_phase(s, 'upkeep', turn=4)
        settle(s)
        ids = stack_library(s, ['Forest', 'Divination'])
        to_phase(s, 'main1', turn=4)
        settle(s)
        target = s.state.cards[ids[1]]
        act(s, 'p1', type='clear_mana')
        mana(s, C=2, U=1)
    saved = tmp_path / 'window80.json'
    saved.write_text(s.state.model_dump_json())
    code = r'''
import sys
from pathlib import Path
from app.cards.repository import CardRepository
from app.cards.images import ImageStore
from app.game.state import GameState
from app.game.session import GameSession
from app.rules import casting
from tests.test_rules_library_look import settle
from tests.test_rules_designations import roundtrip
from tests.game_helpers import act
r=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=r)
cid,mode=sys.argv[3:]
if mode=='case_mdfc':
 act(s,'p1',type='cast_spell',card_id=cid,face=1);settle(s)
 assert s.state.cards[cid].zone=='p1:battlefield' and s.state.cards[cid].face==1
else:
 assert casting.castable(s.state,'p1',s.state.cards[cid],r)
 before=len(s.state.zones['p1:hand'])
 act(s,'p1',type='cast_spell',card_id=cid);settle(s)
 assert s.state.cards[cid].zone=='p1:graveyard' and len(s.state.zones['p1:hand'])==before+2
roundtrip(s)
r.close()
'''
    backend = Path(__file__).resolve().parents[1]
    result = subprocess.run([sys.executable, '-c', code, str(saved), str(cards.db_path), target.id, mode],
                            cwd=backend, env={**os.environ, 'PYTHONPATH': str(backend)},
                            capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stdout + result.stderr


def test_case_grants_actual_current_graveyard_ability_and_native_expiry80(cards):
    s = setup(cards)
    source = solved_case(s)
    target = put(s, 'Grizzly Bears', 'graveyard')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=ability(s, source, 'Solved'))
    settle(s)
    quote = 'You may cast this card from your graveyard.'
    assert any(a.text == quote for a in Plan(s.state, 'p1', cards, None).ch(target).abilities)
    assert not any(p.card == target.id for p in s.state.rules.permissions)
    effect = next(e for e in s.state.rules.effects if s.state.rules.object_id(target.id) in e.affected
                  and quote in e.add_abilities and e.ability_zone == 'graveyard')
    mana(s, C=1, G=1)
    assert casting.castable(s.state, 'p1', target, cards)
    assert effect.duration == 'end_of_turn'
    to_phase(s, 'main1', turn=7)
    settle(s)
    mana(s, C=1, G=1)
    assert not any(a.text == quote for a in Plan(s.state, 'p1', cards, None).ch(target).abilities)
    assert not casting.castable(s.state, 'p1', target, cards)
    roundtrip(s)

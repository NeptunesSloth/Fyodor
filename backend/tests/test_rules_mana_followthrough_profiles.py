"""Live canonical mana gates and isolated, unregistered follow-through prototypes."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_activated_copy_family import answer
from tests.test_rules_bandmate_references import wait_priority
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    data = json.loads((Path(__file__).parent / 'fixtures/mana_followthrough_profiles_cards.json').read_text())
    for i, c in enumerate(data):
        base[c['name']] = card(c['name'], set_code='mfp42', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()



@pytest.mark.parametrize('zone,name', [('graveyard', 'Opt'), ('exile', 'Think Twice')])
def test_schemes_native_target_union_returns_then_adds_mana(cards, zone, name):
    s = table(cards, ["Sorceress's Schemes", 'Think Twice', 'Opt', 'Forest'], ['Opt'], [])
    to_phase(s, 'main1', 4)
    target = put(s, name, zone)
    spell = put(s, "Sorceress's Schemes", 'hand')
    wait_priority(s, 'p1')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 3, 'R': 1})
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[target.id], sources=[])
    answer(s)
    assert s.state.cards[target.id].zone == 'p1:hand'
    p = s.state.players['p1']
    assert p.mana.get('R', 0) + sum(u.sym == 'R' for u in p.mana_units) == 1
    roundtrip(s)


@pytest.mark.parametrize('accept', [False, True])
def test_crowd_actual_opponent_first_main_choice_adds_to_that_player(cards, accept):
    s = table(cards, ['Cheering Crowd'], [], [])
    to_phase(s, 'main1', 4)
    source = put(s, 'Cheering Crowd', 'battlefield')
    to_phase(s, 'main1', 5)
    from tests.test_rules_library_look import settle

    settle(s)
    d = s.state.rules.decision
    assert d is not None and d.player == 'p2'
    ids = [o.id for o in d.options]
    assert 'pay' in ids and 'decline' in ids
    act(s, 'p2', type='choose', decision_id=d.id, option_ids=['pay' if accept else 'decline'])
    answer(s, optional=False)
    assert s.state.cards[source.id].counters.get('+1/+1', 0) == int(accept)
    p = s.state.players['p2']
    assert p.mana.get('C', 0) + sum(u.sym == 'C' for u in p.mana_units) == int(accept)
    roundtrip(s)


@pytest.mark.parametrize('first_use', ['land', 'spell', 'own_land_limit', 'new_incarnation', 'expire'])
def test_ozai_native_one_total_free_spell_or_land_packet_and_normal_land_limit(cards, first_use):
    from app.game.errors import ActionError

    s = table(cards, ['Fire Lord Ozai'], ['Opt'], ['Forest'])
    to_phase(s, 'main1', 4)
    source = put(s, 'Fire Lord Ozai', 'battlefield')
    opt = put(s, 'Opt', 'hand', 'p2')
    forest = put(s, 'Forest', 'hand', 'p3')
    for card_now in [opt, forest]:
        act(s, card_now.owner, type='move', card_ids=[card_now.id],
            to={'player': card_now.owner, 'zone': 'library'}, index=0)
    wait_priority(s, 'p1')
    if first_use == 'own_land_limit':
        own = put(s, 'Forest', 'hand')
        act(s, 'p1', type='play_land', card_id=own.id)
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 6})
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=1)
    answer(s)
    assert s.state.cards[opt.id].zone == 'p2:exile' and s.state.cards[forest.id].zone == 'p3:exile'
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'exile'})
    wait_priority(s, 'p1')
    if first_use == 'expire':
        to_phase(s, 'main1', 5)
        wait_priority(s, 'p1')
        with pytest.raises(ActionError):
            act(s, 'p1', type='cast_spell', card_id=opt.id, free=True, sources=[])
    elif first_use == 'new_incarnation':
        act(s, 'p1', type='move', card_ids=[opt.id], to={'player': 'p2', 'zone': 'graveyard'})
        act(s, 'p1', type='move', card_ids=[opt.id], to={'player': 'p2', 'zone': 'exile'})
        with pytest.raises(ActionError):
            act(s, 'p1', type='cast_spell', card_id=opt.id, free=True, sources=[])
        act(s, 'p1', type='play_land', card_id=forest.id)
        assert s.state.cards[forest.id].zone == 'p1:battlefield'
    elif first_use == 'land':
        act(s, 'p1', type='play_land', card_id=forest.id)
        assert s.state.cards[forest.id].zone == 'p1:battlefield'
        with pytest.raises(ActionError):
            act(s, 'p1', type='cast_spell', card_id=opt.id, free=True, sources=[])
    else:
        if first_use == 'own_land_limit':
            with pytest.raises(ActionError):
                act(s, 'p1', type='play_land', card_id=forest.id)
        act(s, 'p1', type='cast_spell', card_id=opt.id, free=True, sources=[])
        answer(s)
        assert s.state.cards[opt.id].zone == 'p2:graveyard'
        wait_priority(s, 'p1')
        with pytest.raises(ActionError):
            act(s, 'p1', type='play_land', card_id=forest.id)
    roundtrip(s)


def test_hydro_actual_end_step_form_taps_immediately_and_expires_before_next_turn(cards):
    from app.rules.plan import Plan

    s = table(cards, ['Hydro-Man, Fluid Felon', 'Opt'], [], [])
    to_phase(s, 'main1', 4)
    source = put(s, 'Hydro-Man, Fluid Felon', 'battlefield')
    to_phase(s, 'end', 4)
    answer(s)
    ch = Plan(s.state, 'p1', cards, None).ch(s.state.cards[source.id])
    assert ch.is_land and not ch.is_creature
    assert not s.state.cards[source.id].tapped
    wait_priority(s, 'p1')
    index = next(a.index for a in ch.abilities if a.kind == 'mana')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=index)
    p = s.state.players['p1']
    assert p.mana.get('U', 0) + sum(u.sym == 'U' for u in p.mana_units) == 1
    to_phase(s, 'main1', 7)
    ch = Plan(s.state, 'p1', cards, None).ch(s.state.cards[source.id])
    assert ch.is_creature and not ch.is_land
    roundtrip(s)


@pytest.mark.parametrize('zone,name,owner', [('graveyard', 'Forest', 'p1'), ('exile', 'Opt', 'p1'), ('exile', 'Think Twice', 'p2')])
def test_schemes_target_union_rejects_wrong_type_keyword_or_owner(cards, zone, name, owner):
    from app.game.errors import ActionError

    names = ["Sorceress's Schemes", 'Think Twice', 'Opt', 'Forest']
    s = table(cards, names, names, [])
    to_phase(s, 'main1', 4)
    target = put(s, name, zone, owner)
    spell = put(s, "Sorceress's Schemes", 'hand')
    wait_priority(s, 'p1')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 3, 'R': 1})
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[target.id], sources=[])
    assert s.state.cards[spell.id].zone == 'p1:hand'
    assert s.state.cards[target.id].zone == f'{owner}:{zone}'


def test_schemes_flashback_actual_body_then_exiles_and_illegal_target_suppresses_mana(cards):
    s = table(cards, ["Sorceress's Schemes", 'Opt'], [], [])
    to_phase(s, 'main1', 4)
    target = put(s, 'Opt', 'graveyard')
    spell = put(s, "Sorceress's Schemes", 'graveyard')
    wait_priority(s, 'p1')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 4, 'R': 1})
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[target.id], sources=[])
    act(s, 'p1', type='move', card_ids=[target.id], to={'player': 'p1', 'zone': 'exile'})
    answer(s)
    assert s.state.cards[spell.id].zone == 'p1:exile'
    p = s.state.players['p1']
    assert p.mana.get('R', 0) + sum(u.sym == 'R' for u in p.mana_units) == 0
    roundtrip(s)


def test_yue_actual_death_returns_as_tapped_blue_legendary_moon_with_scry_and_mana(cards):
    from app.rules.plan import Plan

    s = table(cards, ['Princess Yue', 'Opt'], [], [])
    to_phase(s, 'main1', 4)
    source = put(s, 'Princess Yue', 'battlefield')
    act(s, 'p1', type='set_damage', card_ids=[source.id], delta=10)
    wait_priority(s, 'p1')
    act(s, 'p1', type='pass_priority')
    answer(s)
    ch = Plan(s.state, 'p1', cards, None).ch(s.state.cards[source.id])
    assert ch.name == 'Moon' and ch.is_land and not ch.is_creature, (s.state.cards[source.id].zone, s.state.cards[source.id].entry_characteristics, s.state.rules.effects)
    assert 'Legendary' in ch.supertypes and ch.colors == frozenset({'U'})
    assert any(a.text == '{T}: Scry 2.' for a in ch.abilities)
    assert s.state.cards[source.id].tapped
    act(s, 'p1', type='tap', card_ids=[source.id], tapped=False)
    wait_priority(s, 'p1')
    act(s, 'p1', type='activate_ability', card_id=source.id,
        ability=next(a.index for a in ch.abilities if a.kind == 'mana'))
    p = s.state.players['p1']
    assert p.mana.get('C', 0) + sum(u.sym == 'C' for u in p.mana_units) == 1
    roundtrip(s)


@pytest.mark.parametrize('replacement', ['none', 'doubled', 'season', 'prevented', 'departed'])
def test_crowd_counter_cost_uses_all_current_counters_and_native_replacements(cards, replacement):
    from tests.test_rules_library_look import settle

    names = ['Cheering Crowd', 'Solemnity', 'Doubling Season', 'Winding Constrictor']
    s = table(cards, names, [], [])
    to_phase(s, 'main1', 4)
    source = put(s, 'Cheering Crowd', 'battlefield')
    act(s, 'p1', type='counter', card_ids=[source.id], kind='charge', delta=2)
    if replacement != 'none' and replacement != 'departed':
        put(s, 'Winding Constrictor' if replacement == 'doubled' else 'Doubling Season' if replacement == 'season' else 'Solemnity', 'battlefield')
    to_phase(s, 'main1', 5)
    if replacement == 'departed':
        act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'graveyard'})
    settle(s)
    d = s.state.rules.decision
    if d is not None:
        assert d.player == 'p2'
        ids = [o.id for o in d.options]
        act(s, d.player, type='choose', decision_id=d.id, option_ids=['pay' if 'pay' in ids else ids[0]])
    answer(s, optional=False)
    p = s.state.players['p2']
    expected = 4 if replacement == 'doubled' else 3 if replacement in ('none', 'season') else 0
    assert p.mana.get('C', 0) + sum(u.sym == 'C' for u in p.mana_units) == expected
    roundtrip(s)


def test_yue_noncopiable_moon_name_types_not_copied_and_land_death_does_not_return(cards):
    from app.rules import scripts
    from app.rules.plan import Plan

    names = ['Princess Yue', 'Mirage Mirror', 'Strip Mine', 'Opt']
    s = table(cards, names, [], [])
    to_phase(s, 'main1', 4)
    source = put(s, 'Princess Yue', 'battlefield')
    act(s, 'p1', type='set_damage', card_ids=[source.id], delta=10)
    wait_priority(s, 'p1')
    act(s, 'p1', type='pass_priority')
    answer(s)
    ch = Plan(s.state, 'p1', cards, None).ch(s.state.cards[source.id])
    assert ch.name == 'Moon'
    assert scripts.define(ch.abilities[0], ch) is not None  # 201.5 survives noncopiable name change.
    mirror = put(s, 'Mirage Mirror', 'battlefield')
    wait_priority(s, 'p1')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 2})
    act(s, 'p1', type='activate_ability', card_id=mirror.id, ability=0, targets=[source.id])
    answer(s)
    copy = Plan(s.state, 'p1', cards, None).ch(s.state.cards[mirror.id])
    assert copy.name == 'Princess Yue' and copy.is_creature and not copy.is_land
    assert s.state.cards[source.id].zone == s.state.cards[mirror.id].zone == 'p1:battlefield'
    mine = put(s, 'Strip Mine', 'battlefield')
    wait_priority(s, 'p1')
    act(s, 'p1', type='activate_ability', card_id=mine.id, ability=1, targets=[source.id])
    answer(s)
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    roundtrip(s)


def test_hydro_blue_cast_intervening_if_is_current_creature_and_land_duration_is_frozen_player(cards):
    from app.rules.plan import Plan

    s = table(cards, ['Hydro-Man, Fluid Felon', 'Opt'], [], [])
    to_phase(s, 'main1', 4)
    source = put(s, 'Hydro-Man, Fluid Felon', 'battlefield')
    to_phase(s, 'end', 4)
    answer(s)
    for expected_land in (True, False):
        if not expected_land:
            to_phase(s, 'main1', 7)
        spell = put(s, 'Opt', 'hand')
        wait_priority(s, 'p1')
        act(s, 'p1', type='add_mana', player='p1', mana={'U': 1})
        act(s, 'p1', type='cast_spell', card_id=spell.id, sources=[])
        answer(s)
        ch = Plan(s.state, 'p1', cards, None).ch(s.state.cards[source.id])
        assert ch.is_land == expected_land
        if not expected_land:
            assert ch.pt == (3, 3)
        else:
            assert not any(e.power == 1 and s.state.rules.object_id(source.id) in e.affected for e in s.state.rules.effects)
    roundtrip(s)


@pytest.mark.parametrize('family', ['schemes', 'crowd', 'hydro', 'yue'])
def test_staged_followthrough_native_state_resumes_in_fresh_process(cards, tmp_path, family):
    import subprocess
    import sys

    from tests.test_rules_library_look import settle

    names = ["Sorceress's Schemes", 'Think Twice', 'Opt', 'Cheering Crowd', 'Hydro-Man, Fluid Felon', 'Princess Yue']
    s = table(cards, names, [], [])
    to_phase(s, 'main1', 4)
    if family == 'schemes':
        target = put(s, 'Think Twice', 'exile')
        spell = put(s, "Sorceress's Schemes", 'hand')
        wait_priority(s, 'p1')
        act(s, 'p1', type='add_mana', player='p1', mana={'C': 3, 'R': 1})
        act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[target.id], sources=[])
    elif family == 'crowd':
        put(s, 'Cheering Crowd', 'battlefield')
        to_phase(s, 'main1', 5)
        settle(s)
        assert s.state.rules.decision.player == 'p2'
    elif family == 'hydro':
        put(s, 'Hydro-Man, Fluid Felon', 'battlefield')
        to_phase(s, 'end', 4)
        answer(s)
    else:
        source = put(s, 'Princess Yue', 'battlefield')
        act(s, 'p1', type='set_damage', card_ids=[source.id], delta=10)
        wait_priority(s, 'p1')
        act(s, 'p1', type='pass_priority')
        answer(s)
    path = tmp_path / 'followthrough-cold.json'
    path.write_text(s.state.model_dump_json())
    code = r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from app.rules.plan import Plan
path, database, family = sys.argv[1:]
repo=CardRepository(Path(database),ImageStore(Path(database).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(path).read_text()),cards=repo)
s.view('p3')
from tests.test_rules_activated_copy_family import answer
from tests.test_rules_bandmate_references import wait_priority
if family=='hydro':
    source=next(c for c in s.state.cards.values() if c.name=='Hydro-Man, Fluid Felon' and c.zone=='p1:battlefield')
    ch=Plan(s.state,'p1',repo,None).ch(source)
    assert ch.is_land and not ch.is_creature
    wait_priority(s,'p1')
    s.perform('p1',{'type':'activate_ability','card_id':source.id,'ability':next(a.index for a in ch.abilities if a.kind=='mana')})
else:
    answer(s)
if family=='yue':
    source=next(c for c in s.state.cards.values() if c.name=='Princess Yue' and c.zone=='p1:battlefield')
    ch=Plan(s.state,'p1',repo,None).ch(source)
    assert ch.name=='Moon' and ch.is_land and not ch.is_creature
elif family=='schemes':
    assert any(c.name=='Think Twice' and c.zone=='p1:hand' for c in s.state.cards.values())
if family!='yue':
    p=s.state.players['p2' if family=='crowd' else 'p1']
    color={'crowd':'C','schemes':'R','hydro':'U'}[family]
    assert p.mana.get(color,0)+sum(u.sym==color for u in p.mana_units)==1
assert GameState.model_validate_json(s.state.model_dump_json())==s.state
'''
    result = subprocess.run([sys.executable, '-c', code, str(path), str(cards.db_path), family],
        capture_output=True, text=True, cwd=Path(__file__).resolve().parents[1], timeout=120)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize('name', ["Sorceress's Schemes", 'Cheering Crowd', 'Hydro-Man, Fluid Felon', 'Princess Yue'])
def test_staged_first_four_whole_printed_cards_are_fully_parsed(cards, name):
    from app.rules import coverage

    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


def test_yue_actual_land_entry_is_not_exiled_by_priest_and_retains_native_scry(cards):
    from app.rules.plan import Plan
    from tests.test_rules_library_look import settle

    names = ['Princess Yue', 'Containment Priest', 'Opt', 'Think Twice']
    s = table(cards, names, names, [])
    to_phase(s, 'main1', 4)
    source = put(s, 'Princess Yue', 'battlefield')
    put(s, 'Containment Priest', 'battlefield', 'p2')
    act(s, 'p1', type='set_damage', card_ids=[source.id], delta=10)
    wait_priority(s, 'p1')
    act(s, 'p1', type='pass_priority')
    answer(s)
    assert s.state.cards[source.id].zone == 'p1:battlefield'
    assert Plan(s.state, 'p1', cards, None).ch(s.state.cards[source.id]).name == 'Moon'
    to_phase(s, 'main1', 7)
    wait_priority(s, 'p1')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=1)
    settle(s)
    assert s.state.rules.decision is not None
    answer(s)
    assert s.state.cards[source.id].tapped
    roundtrip(s)


def test_hydro_land_duration_ends_on_original_controllers_next_turn_after_control_change(cards):
    from app.rules.plan import Plan

    s = table(cards, ['Hydro-Man, Fluid Felon'], [], [])
    to_phase(s, 'main1', 4)
    source = put(s, 'Hydro-Man, Fluid Felon', 'battlefield')
    to_phase(s, 'end', 4)
    answer(s)
    original = {e.id for e in s.state.rules.effects if e.duration == 'next_turn'}
    act(s, 'p1', type='set_controller', card_ids=[source.id], player='p2')
    to_phase(s, 'main1', 5)
    assert Plan(s.state, 'p2', cards, None).ch(s.state.cards[source.id]).is_land
    to_phase(s, 'upkeep', 7)
    assert not original.intersection(e.id for e in s.state.rules.effects)
    # Its new controller's end step created an independent later duration.
    assert Plan(s.state, 'p2', cards, None).ch(s.state.cards[source.id]).is_land
    to_phase(s, 'upkeep', 8)
    assert not Plan(s.state, 'p2', cards, None).ch(s.state.cards[source.id]).is_land
    roundtrip(s)


def test_yue_two_actual_moon_entries_use_native_legend_rule_and_keep_front_name_separate(cards):
    from app.rules.plan import Plan
    from tests.test_rules_library_look import settle

    s = table(cards, ['Princess Yue', 'Princess Yue'], [], [])
    to_phase(s, 'main1', 4)
    copies = [c.id for c in s.state.cards.values() if c.name == 'Princess Yue' and c.owner == 'p1']
    for cid in copies:
        act(s, 'p1', type='move', card_ids=[cid], to={'player': 'p1', 'zone': 'battlefield'})
        if cid == copies[1]:
            assert s.state.cards[copies[0]].zone == 'p1:battlefield'
            assert Plan(s.state, 'p1', cards, None).ch(s.state.cards[cid]).name == 'Princess Yue'
        act(s, 'p1', type='set_damage', card_ids=[cid], delta=10)
        wait_priority(s, 'p1')
        act(s, 'p1', type='pass_priority')
        settle(s)
        if cid == copies[0]:
            answer(s)
        else:
            d = s.state.rules.decision
            assert d is not None and d.resume['step'] == 'legend_rule'
            assert all(Plan(s.state, 'p1', cards, None).ch(s.state.cards[c]).name == 'Moon' for c in copies)
            act(s, 'p1', type='choose', decision_id=d.id, option_ids=[copies[0]])
            answer(s)
    assert s.state.cards[copies[0]].zone == 'p1:battlefield'
    assert s.state.cards[copies[1]].zone == 'p1:graveyard'
    roundtrip(s)


@pytest.fixture()
def noted(monkeypatch):
    from app.rules import effects, mana_noted_profiles, scripts
    from app.rules import mana as M

    original = scripts.define
    original_mana = M.parse_mana_ability
    monkeypatch.setattr(scripts, 'define', lambda ability, ch:
        mana_noted_profiles.definition(ability, ch) or original(ability, ch))
    monkeypatch.setattr(M, 'parse_mana_ability', lambda text, identity=M.COLORS, *, card_name='':
        mana_noted_profiles.parse_mana(text, identity, card_name) or original_mana(text, identity, card_name=card_name))
    for key, fn in mana_noted_profiles.PRIMITIVES.items():
        monkeypatch.setitem(effects.PRIMITIVES, key, fn)
    for key, fn in mana_noted_profiles.RESUME.items():
        monkeypatch.setitem(effects.RESUME, key, fn)



@pytest.mark.parametrize('accept,multiply,zero', [(False, False, False), (True, False, False),
    (True, True, False), (True, False, True)])
def test_ozai_native_attack_sacrifice_last_power_and_combat_only_kept_mana(cards, accept, multiply, zero):
    from tests.test_rules_banding import attack_step
    from tests.test_rules_library_look import settle

    sacrifice_name = 'Wall of Omens' if zero else 'Grizzly Bears'
    s = table(cards, ['Fire Lord Ozai', sacrifice_name, 'Mountain', 'Nyxbloom Ancient'], [], [])
    to_phase(s, 'main1', 4)
    source = put(s, 'Fire Lord Ozai', 'battlefield')
    bear = put(s, sacrifice_name, 'battlefield')
    mountain = put(s, 'Mountain', 'battlefield')
    if multiply:
        put(s, 'Nyxbloom Ancient', 'battlefield')
    if not zero:
        act(s, 'p1', type='counter', card_ids=[bear.id], kind='+1/+1', delta=3)
    to_phase(s, 'main1', 7)
    attack_step(s)
    act(s, 'p1', type='add_mana', player='p1', mana={'R': 3})
    act(s, 'p1', type='declare_attackers', attackers=[{'card_id': source.id, 'target': 'p2'}])
    wait_priority(s, 'p1')
    act(s, 'p1', type='activate_ability', card_id=mountain.id, ability=0)
    assert sum(u.sym == 'R' for u in s.state.players['p1'].mana_units) == (3 if multiply else 1)
    settle(s)
    d = s.state.rules.decision
    assert d is not None and {'pay', 'decline'} <= {o.id for o in d.options}
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=['pay' if accept else 'decline'])
    if accept:
        d = s.state.rules.decision
        if d is not None:
            assert any(o.card_id == bear.id for o in d.options)
            assert all(o.card_id != source.id for o in d.options)
            act(s, 'p1', type='choose', decision_id=d.id, option_ids=[bear.id])
    answer(s)
    to_phase(s, 'declare_blockers', 7)
    p = s.state.players['p1']
    # Nyxbloom triples the earlier Mountain output; the attack trigger isn't a tap for mana.
    assert p.mana.get('R', 0) + sum(u.sym == 'R' for u in p.mana_units) == (5 if accept and not zero else 0)
    assert s.state.cards[bear.id].zone == ('p1:graveyard' if accept else 'p1:battlefield')
    to_phase(s, 'main2', 7)
    assert not s.state.players['p1'].mana and not s.state.players['p1'].mana_units
    roundtrip(s)


@pytest.mark.parametrize('family', ['sacrifice', 'packet'])
def test_ozai_true_cold_native_cost_receipt_or_one_play_authority(cards, tmp_path, family):
    import subprocess
    import sys

    from tests.test_rules_banding import attack_step
    from tests.test_rules_library_look import settle

    s = table(cards, ['Fire Lord Ozai', 'Grizzly Bears'], ['Opt'], ['Forest'])
    to_phase(s, 'main1', 4)
    source = put(s, 'Fire Lord Ozai', 'battlefield')
    if family == 'sacrifice':
        bear = put(s, 'Grizzly Bears', 'battlefield')
        act(s, 'p1', type='counter', card_ids=[bear.id], kind='+1/+1', delta=3)
        to_phase(s, 'main1', 7)
        attack_step(s)
        act(s, 'p1', type='declare_attackers', attackers=[{'card_id': source.id, 'target': 'p2'}])
        settle(s)
        assert s.state.rules.decision is not None
    else:
        for name, owner in [('Opt', 'p2'), ('Forest', 'p3')]:
            card_now = put(s, name, 'hand', owner)
            act(s, owner, type='move', card_ids=[card_now.id], to={'player': owner, 'zone': 'library'}, index=0)
        wait_priority(s, 'p1')
        act(s, 'p1', type='add_mana', player='p1', mana={'C': 6})
        act(s, 'p1', type='activate_ability', card_id=source.id, ability=1)
        answer(s)
        act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'exile'})
    path = tmp_path / 'ozai-cold.json'
    path.write_text(s.state.model_dump_json())
    code = r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.game.session import GameSession
from app.game.state import GameState
from tests.test_rules_activated_copy_family import answer
from tests.test_rules_bandmate_references import wait_priority
from tests.test_rules_wave30m_durations import to_phase
path,database,family=sys.argv[1:]
repo=CardRepository(Path(database),ImageStore(Path(database).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(path).read_text()),cards=repo)
s.view('p3')
if family=='sacrifice':
    d=s.state.rules.decision
    s.perform(d.player,{'type':'choose','decision_id':d.id,'option_ids':['pay']})
    answer(s)
    assert s.state.players['p1'].mana.get('R',0)+sum(u.sym=='R' for u in s.state.players['p1'].mana_units)==5
    to_phase(s,'main2',7)
    assert not s.state.players['p1'].mana
else:
    opt=next(c for c in s.state.cards.values() if c.name=='Opt' and c.owner=='p2')
    land=next(c for c in s.state.cards.values() if c.name=='Forest' and c.owner=='p3')
    wait_priority(s,'p1')
    s.perform('p1',{'type':'cast_spell','card_id':opt.id,'free':True,'sources':[]})
    answer(s)
    assert s.state.cards[opt.id].zone=='p2:graveyard'
    wait_priority(s,'p1')
    try:
        s.perform('p1',{'type':'play_land','card_id':land.id})
    except ActionError:
        pass
    else:
        raise AssertionError('One-play permission was reused for a land')
assert GameState.model_validate_json(s.state.model_dump_json())==s.state
'''
    result = subprocess.run([sys.executable, '-c', code, str(path), str(cards.db_path), family],
        capture_output=True, text=True, cwd=Path(__file__).resolve().parents[1], timeout=120)
    assert result.returncode == 0, result.stderr


def test_ozai_cannot_sacrifice_itself_or_opponents_only_other_creature(cards):
    from tests.test_rules_banding import attack_step
    from tests.test_rules_library_look import settle

    s = table(cards, ['Fire Lord Ozai'], ['Grizzly Bears'], [])
    to_phase(s, 'main1', 4)
    source = put(s, 'Fire Lord Ozai', 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    to_phase(s, 'main1', 7)
    attack_step(s)
    act(s, 'p1', type='add_mana', player='p1', mana={'R': 3})
    act(s, 'p1', type='declare_attackers', attackers=[{'card_id': source.id, 'target': 'p2'}])
    settle(s)
    assert s.state.rules.decision is None
    to_phase(s, 'declare_blockers', 7)
    assert s.state.cards[source.id].zone == 'p1:battlefield' and s.state.cards[bear.id].zone == 'p2:battlefield'
    assert not s.state.players['p1'].mana and not s.state.players['p1'].mana_units
    assert not s.state.rules.kept_mana
    roundtrip(s)



def test_esper_native_all_chapters_paid_anytype_cast_and_deferred_graveyard_batch(cards):
    from app.rules.plan import Plan
    from tests.test_rules_library_look import settle

    name = 'Summon: Esper Valigarmanda'
    s = table(cards, [name, 'Opt'], ['Think Twice'], ['Lightning Bolt'])
    to_phase(s, 'main1', 4)
    first = put(s, 'Opt', 'graveyard')
    second = put(s, 'Think Twice', 'graveyard', 'p2')
    third = put(s, 'Lightning Bolt', 'graveyard', 'p3')
    source = put(s, name, 'hand')
    wait_priority(s, 'p1')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 3, 'R': 1})
    act(s, 'p1', type='cast_spell', card_id=source.id, sources=[])
    settle(s)
    for target in [first, second, third]:
        d = s.state.rules.decision
        assert d is not None and d.player == 'p1' and d.resume['step'] == 'esper_graveyard_choice'
        assert all(s.state.cards[c.id].zone.endswith(':graveyard') for c in [first, second, third])
        act(s, 'p1', type='choose', decision_id=d.id, option_ids=[target.id])
    answer(s)
    assert all(s.state.cards[c.id].zone.endswith(':exile') for c in [first, second, third])
    assert {'flying', 'haste'} <= Plan(s.state, 'p1', cards, None).ch(s.state.cards[source.id]).keywords
    for turn, cast_card in [(7, first), (10, second), (13, third)]:
        to_phase(s, 'main1', turn)
        settle(s)
        d = s.state.rules.decision
        assert d is not None and d.resume['step'] == 'free_cast_pick' and d.resume['e']['paid']
        option = next(o.id for o in d.options if o.card_id == cast_card.id or o.id == cast_card.id)
        act(s, 'p1', type='choose', decision_id=d.id, option_ids=[option])
        answer(s)
        assert s.state.cards[cast_card.id].zone == f'{cast_card.owner}:graveyard'
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    roundtrip(s)


@pytest.mark.parametrize('chapter', [3, 4])
def test_esper_sourcegone_chapter_uses_departure_lore_and_original_link(cards, chapter):
    from tests.test_rules_library_look import settle

    name = 'Summon: Esper Valigarmanda'
    s = table(cards, [name], ['Opt'], [])
    to_phase(s, 'main1', 4)
    opt = put(s, 'Opt', 'graveyard', 'p2')
    source = put(s, name, 'hand')
    wait_priority(s, 'p1')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 3, 'R': 1})
    act(s, 'p1', type='cast_spell', card_id=source.id, sources=[])
    answer(s)
    for turn in range(7, 3 * chapter + 2, 3):
        to_phase(s, 'main1', turn)
        if turn == 3 * chapter + 1:
            break
        settle(s)
        d = s.state.rules.decision
        assert d is not None and d.resume['step'] == 'free_cast_pick'
        act(s, 'p1', type='choose', decision_id=d.id, option_ids=[])
        answer(s)
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'exile'})
    settle(s)
    d = s.state.rules.decision
    assert d is not None and d.player == 'p1' and any(o.card_id == opt.id for o in d.options)
    p = s.state.players['p1']
    assert p.mana.get('R', 0) + sum(u.sym == 'R' for u in p.mana_units) == chapter
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[next(o.id for o in d.options if o.card_id == opt.id)])
    answer(s)
    assert s.state.cards[opt.id].zone == 'p2:graveyard'
    roundtrip(s)


@pytest.mark.parametrize('family', ['choice', 'payment'])
def test_esper_true_cold_native_graveyard_choice_and_paid_anytype_payment(cards, tmp_path, family):
    import subprocess
    import sys

    from tests.test_rules_library_look import settle

    name = 'Summon: Esper Valigarmanda'
    spell_name = 'Capsize' if family == 'payment' else 'Opt'
    s = table(cards, [name, 'Think Twice'], [spell_name], [])
    to_phase(s, 'main1', 4)
    put(s, 'Think Twice', 'graveyard')
    opt = put(s, spell_name, 'graveyard', 'p2')
    if family == 'payment':
        put(s, 'Forest', 'battlefield')
    source = put(s, name, 'hand')
    wait_priority(s, 'p1')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 3, 'R': 1})
    act(s, 'p1', type='cast_spell', card_id=source.id, sources=[])
    settle(s)
    assert s.state.rules.decision.resume['step'] == 'esper_graveyard_choice'
    if family == 'payment':
        answer(s)
        to_phase(s, 'main1', 7)
        settle(s)
        act(s, 'p1', type='set_prefs', payment='self')
        d = s.state.rules.decision
        act(s, 'p1', type='choose', decision_id=d.id, option_ids=[next(o.id for o in d.options if o.card_id == opt.id)])
        for _ in range(8):
            d = s.state.rules.decision
            assert d is not None
            if d.resume['step'] == 'pay_mana':
                break
            options = [o for o in d.options if o.card_id == source.id or o.id == source.id]
            act(s, d.player, type='choose', decision_id=d.id,
                option_ids=[(options or d.options)[0].id])
        assert s.state.rules.decision.resume['step'] == 'pay_mana'
    path = tmp_path / 'esper-cold.json'
    path.write_text(s.state.model_dump_json())
    code = r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.test_rules_activated_copy_family import answer
from tests.test_rules_library_look import settle
from tests.test_rules_wave30m_durations import to_phase
path,database,family=sys.argv[1:]
repo=CardRepository(Path(database),ImageStore(Path(database).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(path).read_text()),cards=repo)
s.view('p3')
opt=next(c for c in s.state.cards.values() if c.name==('Capsize' if family=='payment' else 'Opt'))
if family=='choice':
    answer(s)
    assert s.state.cards[opt.id].zone=='p2:exile'
    to_phase(s,'main1',7)
    settle(s)
    d=s.state.rules.decision
    s.perform('p1',{'type':'choose','decision_id':d.id,'option_ids':[next(o.id for o in d.options if o.card_id==opt.id)]})
else:
    d=s.state.rules.decision
    assert d.resume['step']=='pay_mana'
    assert sum(s.state.players['p1'].mana.values())+len(s.state.players['p1'].mana_units)==2
    land=next(c for c in s.state.cards.values() if c.name=='Forest' and c.zone=='p1:battlefield')
    s.perform('p1',{'type':'activate_ability','card_id':land.id,'ability':0})
    d=s.state.rules.decision
    if d is not None:
        assert d.resume['step']=='pay_mana' and any(o.id=='pay' for o in d.options)
        s.perform('p1',{'type':'choose','decision_id':d.id,'option_ids':['pay']})
answer(s)
assert s.state.cards[opt.id].zone=='p2:graveyard'
assert GameState.model_validate_json(s.state.model_dump_json())==s.state
'''
    result = subprocess.run([sys.executable, '-c', code, str(path), str(cards.db_path), family],
        capture_output=True, text=True, cwd=Path(__file__).resolve().parents[1], timeout=120)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize('packet', ['empty', 'new_incarnation', 'mdfc'])
def test_esper_empty_exact_packet_and_land_back_face_do_not_extend_authority(cards, packet):
    from app.game.errors import ActionError
    from tests.test_rules_library_look import settle

    name = 'Summon: Esper Valigarmanda'
    candidate_name = 'Spikefield Hazard // Spikefield Cave' if packet == 'mdfc' else 'Opt'
    s = table(cards, [name, candidate_name], [], [])
    to_phase(s, 'main1', 4)
    candidate = put(s, candidate_name, 'graveyard' if packet != 'empty' else 'hand')
    source = put(s, name, 'hand')
    wait_priority(s, 'p1')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 3, 'R': 1})
    act(s, 'p1', type='cast_spell', card_id=source.id, sources=[])
    answer(s)
    if packet == 'new_incarnation':
        act(s, 'p1', type='move', card_ids=[candidate.id], to={'player': 'p1', 'zone': 'graveyard'})
        act(s, 'p1', type='move', card_ids=[candidate.id], to={'player': 'p1', 'zone': 'exile'})
    to_phase(s, 'main1', 7)
    settle(s)
    d = s.state.rules.decision
    if packet == 'mdfc':
        assert d is not None and d.resume['step'] == 'free_cast_pick'
        assert all(o.card_id == candidate.id and not o.id.endswith('@1') for o in d.options)
        act(s, 'p1', type='choose', decision_id=d.id, option_ids=[])
        answer(s)
    else:
        assert d is None
    p = s.state.players['p1']
    assert p.mana.get('R', 0) + sum(u.sym == 'R' for u in p.mana_units) == 2
    if packet in ('empty', 'new_incarnation'):
        wait_priority(s, 'p1')
        with pytest.raises(ActionError):
            act(s, 'p1', type='cast_spell', card_id=candidate.id, sources=[])
    roundtrip(s)


def test_esper_paid_resolution_cast_pays_actual_mandatory_discard_cost(cards):
    from tests.test_rules_library_look import settle

    name = 'Summon: Esper Valigarmanda'
    s = table(cards, [name, 'Opt'], ['Cathartic Reunion'], [])
    to_phase(s, 'main1', 4)
    spell = put(s, 'Cathartic Reunion', 'graveyard', 'p2')
    source = put(s, name, 'hand')
    wait_priority(s, 'p1')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 3, 'R': 1})
    act(s, 'p1', type='cast_spell', card_id=source.id, sources=[])
    answer(s)
    opt = put(s, 'Opt', 'hand')
    forest = put(s, 'Forest', 'hand')
    to_phase(s, 'main1', 7)
    settle(s)
    d = s.state.rules.decision
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[next(o.id for o in d.options if o.card_id == spell.id)])
    d = s.state.rules.decision
    assert d is not None and len([o for o in d.options if o.card_id in (opt.id, forest.id)]) == 2
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[opt.id, forest.id])
    answer(s)
    assert s.state.cards[opt.id].zone == s.state.cards[forest.id].zone == 'p1:graveyard'
    assert s.state.cards[spell.id].zone == 'p2:graveyard'
    roundtrip(s)


def test_esper_paid_resolution_cast_announces_nonzero_x_and_pays_it(cards):
    from tests.test_rules_library_look import settle

    name = 'Summon: Esper Valigarmanda'
    s = table(cards, [name], ['Blaze'], [])
    to_phase(s, 'main1', 4)
    spell = put(s, 'Blaze', 'graveyard', 'p2')
    source = put(s, name, 'hand')
    wait_priority(s, 'p1')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 3, 'R': 1})
    act(s, 'p1', type='cast_spell', card_id=source.id, sources=[])
    answer(s)
    to_phase(s, 'main1', 7)
    settle(s)
    d = s.state.rules.decision
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[next(o.id for o in d.options if o.card_id == spell.id)])
    d = s.state.rules.decision
    assert d is not None and d.resume['step'] == 'free_x' and any(o.id == 'x:1' for o in d.options)
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=['x:1'])
    d = s.state.rules.decision
    assert d is not None and any(o.id == 'p3' for o in d.options)
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=['p3'])
    assert any(p.card == spell.id and p.x == 1 and p.mana_spent == {'R': 2} for p in s.state.rules.payments.values()), [
        p.model_dump() for p in s.state.rules.payments.values() if p.card == spell.id]
    answer(s)
    assert s.state.players['p3'].life == 39
    roundtrip(s)


def test_esper_actual_countered_chapter_adds_no_mana_and_opens_no_cast_window(cards):
    from tests.test_rules_library_look import settle

    name = 'Summon: Esper Valigarmanda'
    s = table(cards, [name, 'Stifle'], ['Opt'], [])
    to_phase(s, 'main1', 4)
    opt = put(s, 'Opt', 'graveyard', 'p2')
    source = put(s, name, 'hand')
    wait_priority(s, 'p1')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 3, 'R': 1})
    act(s, 'p1', type='cast_spell', card_id=source.id, sources=[])
    answer(s)
    to_phase(s, 'main1', 7)
    settle(s)
    d = s.state.rules.decision
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[])
    answer(s)
    to_phase(s, 'main1', 10)
    target = s.state.zones['stack'][-1]
    stifle = put(s, 'Stifle', 'hand')
    wait_priority(s, 'p1')
    act(s, 'p1', type='add_mana', player='p1', mana={'U': 1})
    act(s, 'p1', type='cast_spell', card_id=stifle.id, targets=[target], sources=[])
    answer(s)
    assert s.state.cards[opt.id].zone == 'p2:exile'
    assert not s.state.players['p1'].mana and not s.state.players['p1'].mana_units
    assert s.state.rules.decision is None
    roundtrip(s)



def test_ojer_native_death_returns_tapped_back_and_mana_removes_time(cards):
    from app.game.errors import ActionError
    from app.rules.plan import Plan

    name = 'Ojer Pakpatiq, Deepest Epoch // Temple of Cyclical Time'
    s = table(cards, [name], [], [])
    to_phase(s, 'main1', 4)
    source = put(s, name, 'battlefield')
    act(s, 'p1', type='set_damage', card_ids=[source.id], delta=10)
    wait_priority(s, 'p1')
    act(s, 'p1', type='pass_priority')
    answer(s)
    card_now = s.state.cards[source.id]
    assert card_now.face == 1 and card_now.tapped and card_now.counters.get('time') == 3
    act(s, 'p1', type='tap', card_ids=[source.id], tapped=False)
    wait_priority(s, 'p1')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 2, 'U': 1})
    ch = Plan(s.state, 'p1', cards, None).ch(s.state.cards[source.id])
    with pytest.raises(ActionError):
        act(s, 'p1', type='activate_ability', card_id=source.id,
            ability=next(a.index for a in ch.abilities if a.kind == 'activated'))
    assert not s.state.cards[source.id].tapped and s.state.cards[source.id].counters.get('time') == 3
    assert s.state.players['p1'].mana == {'C': 2, 'U': 1}
    for left in [2, 1, 0, 0]:
        if s.state.cards[source.id].tapped:
            act(s, 'p1', type='tap', card_ids=[source.id], tapped=False)
        wait_priority(s, 'p1')
        ch = Plan(s.state, 'p1', cards, None).ch(s.state.cards[source.id])
        act(s, 'p1', type='activate_ability', card_id=source.id, ability=next(a.index for a in ch.abilities if a.kind == 'mana'))
        assert s.state.cards[source.id].counters.get('time', 0) == left
    assert s.state.players['p1'].mana.get('U', 0) + sum(u.sym == 'U' for u in s.state.players['p1'].mana_units) == 5
    act(s, 'p1', type='tap', card_ids=[source.id], tapped=False)
    wait_priority(s, 'p1')
    ch = Plan(s.state, 'p1', cards, None).ch(s.state.cards[source.id])
    index = next(a.index for a in ch.abilities if a.kind == 'activated')
    from app.rules import scripts
    assert scripts.define(next(a for a in ch.abilities if a.index == index), ch) is not None, ch.abilities
    to_phase(s, 'main1', 5)
    wait_priority(s, 'p1')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 2, 'U': 1})
    with pytest.raises(ActionError):
        act(s, 'p1', type='activate_ability', card_id=source.id, ability=index)
    assert s.state.cards[source.id].face == 1 and not s.state.cards[source.id].tapped
    to_phase(s, 'main1', 7)
    wait_priority(s, 'p1')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 2, 'U': 1})
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=index)
    answer(s)
    assert s.state.cards[source.id].face == 0
    roundtrip(s)


def test_ojer_actual_instant_from_hand_rebounds_after_source_leaves(cards, tmp_path):
    import subprocess
    import sys

    from app.rules import scripts
    from app.rules.plan import Plan
    name = 'Ojer Pakpatiq, Deepest Epoch // Temple of Cyclical Time'
    s = table(cards, [name, 'Opt'], [], [])
    to_phase(s, 'main1', 4)
    source = put(s, name, 'battlefield')
    ch = Plan(s.state, 'p1', cards, None).ch(s.state.cards[source.id])
    assert all(scripts.define(a, ch) is not None for a in ch.abilities if a.kind == 'triggered'), ch.abilities
    opt = put(s, 'Opt', 'hand')
    wait_priority(s, 'p1')
    act(s, 'p1', type='add_mana', player='p1', mana={'U': 1})
    act(s, 'p1', type='cast_spell', card_id=opt.id, sources=[])
    assert len(s.state.zones.get('stack', [])) == 2, (s.state.zones.get('stack'), [scripts.define(a, ch) for a in ch.abilities if a.kind == 'triggered'])
    for _ in range(12):
        if 'rebound' in Plan(s.state, 'p1', cards, None).ch(s.state.cards[opt.id]).keywords:
            break
        d = s.state.rules.decision
        if d is not None:
            assert d.kind == 'order', d
            act(s, d.player, type='choose', decision_id=d.id, option_ids=[o.id for o in d.options])
        else:
            act(s, s.state.rules.priority, type='pass_priority')
    assert 'rebound' in Plan(s.state, 'p1', cards, None).ch(s.state.cards[opt.id]).keywords
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'exile'})
    path = tmp_path / 'ojer-rebound-cold.json'
    path.write_text(s.state.model_dump_json())
    code = r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.test_rules_activated_copy_family import answer
from tests.test_rules_wave30m_durations import to_phase
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
s.view('p3')
answer(s)
opt=next(c for c in s.state.cards.values() if c.name=='Opt')
assert opt.zone=='p1:exile'
to_phase(s,'upkeep',7)
answer(s)
assert s.state.cards[opt.id].zone=='p1:graveyard'
'''
    result = subprocess.run([sys.executable, '-c', code, str(path), str(cards.db_path)],
        capture_output=True, text=True, cwd=Path(__file__).resolve().parents[1], timeout=120)
    assert result.returncode == 0, result.stderr
    answer(s)
    assert s.state.cards[opt.id].zone == 'p1:exile'
    to_phase(s, 'upkeep', 7)
    answer(s)
    assert s.state.cards[opt.id].zone == 'p1:graveyard'
    roundtrip(s)


@pytest.mark.parametrize('name,zone,mana', [('Think Twice', 'graveyard', {'C': 2, 'U': 1}),
    ("Sorceress's Schemes", 'hand', {'C': 3, 'R': 1})])
def test_ojer_rebound_excludes_nonhand_instant_and_hand_sorcery(cards, name, zone, mana):
    source_name = 'Ojer Pakpatiq, Deepest Epoch // Temple of Cyclical Time'
    s = table(cards, [source_name, name, 'Opt'], [], [])
    to_phase(s, 'main1', 4)
    put(s, source_name, 'battlefield')
    spell = put(s, name, zone)
    target = put(s, 'Opt', 'graveyard')
    wait_priority(s, 'p1')
    act(s, 'p1', type='add_mana', player='p1', mana=mana)
    act(s, 'p1', type='cast_spell', card_id=spell.id, sources=[],
        **({'targets': [target.id]} if name == "Sorceress's Schemes" else {}))
    assert len(s.state.zones.get('stack', [])) == 1
    answer(s)
    assert not s.state.rules.rebounding
    roundtrip(s)


@pytest.mark.parametrize('secondary', ['Twincast', 'Counterspell'])
def test_ojer_native_spell_copy_does_not_inherit_grant_and_countered_spell_does_not_rebound(cards, secondary):
    from app.rules.plan import Plan

    name = 'Ojer Pakpatiq, Deepest Epoch // Temple of Cyclical Time'
    s = table(cards, [name, 'Opt', secondary], [], [])
    to_phase(s, 'main1', 4)
    put(s, name, 'battlefield')
    opt = put(s, 'Opt', 'hand')
    spell = put(s, secondary, 'hand')
    wait_priority(s, 'p1')
    act(s, 'p1', type='add_mana', player='p1', mana={'U': 3})
    act(s, 'p1', type='cast_spell', card_id=opt.id, sources=[])
    for _ in range(12):
        if 'rebound' in Plan(s.state, 'p1', cards, None).ch(s.state.cards[opt.id]).keywords:
            break
        act(s, s.state.rules.priority, type='pass_priority')
    wait_priority(s, 'p1')
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[opt.id], sources=[])
    if secondary == 'Twincast':
        for _ in range(30):
            copies = [c for c in s.state.cards.values() if c.zone == 'stack' and c.stack_info is not None and 'Copy' in c.stack_info.tags]
            if copies:
                assert all('rebound' not in Plan(s.state, 'p1', cards, None).ch(c).keywords for c in copies)
                break
            d = s.state.rules.decision
            if d is not None:
                act(s, d.player, type='choose', decision_id=d.id, option_ids=[o.id for o in d.options][:max(1, d.min_choices)])
            else:
                act(s, s.state.rules.priority, type='pass_priority')
        else:
            raise AssertionError('Twincast did not create its native spell copy')
    answer(s)
    assert s.state.cards[opt.id].zone == ('p1:exile' if secondary == 'Twincast' else 'p1:graveyard')
    assert set(s.state.rules.rebound_objects) == ({opt.id, spell.id} if secondary == 'Twincast' else {spell.id})
    roundtrip(s)


def test_ojer_nondoublefaced_native_copy_dies_without_returning(cards):
    from tests.test_rules_named_literal_receipts42 import sakashima

    name = 'Ojer Pakpatiq, Deepest Epoch // Temple of Cyclical Time'
    s = table(cards, [name, 'Sakashima the Impostor'], [], [])
    to_phase(s, 'main1', 4)
    source = put(s, name, 'battlefield')
    copy = sakashima(s, source)
    act(s, 'p1', type='set_damage', card_ids=[copy.id], delta=10)
    wait_priority(s, 'p1')
    act(s, 'p1', type='pass_priority')
    answer(s)
    assert s.state.cards[copy.id].zone == 'p1:graveyard'
    roundtrip(s)


def test_ice_input_notes_actual_multitype_payment_and_sourcegone_permission_persists(cards, noted):
    from tests.test_rules_library_look import settle

    s = table(cards, ['Ice Cauldron', 'Opt', 'Forest'], [], [])
    to_phase(s, 'main1', 4)
    source = put(s, 'Ice Cauldron', 'battlefield')
    spell = put(s, 'Opt', 'hand')
    original = s.state.rules.object_id(source.id)
    wait_priority(s, 'p1')
    act(s, 'p1', type='add_mana', player='p1', mana={'G': 1, 'R': 1, 'U': 1})
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=0, x_value=3)
    settle(s)
    d = s.state.rules.decision
    assert d is not None and d.resume['step'] == 'return_choice'
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[spell.id])
    answer(s)
    note = s.state.rules.noted_mana[original]
    assert note.mana == {'G': 1, 'R': 1, 'U': 1}
    assert note.last_exiled[0].object_id == s.state.rules.object_id(spell.id)
    assert s.state.cards[source.id].counters.get('charge') == 1
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'graveyard'})
    wait_priority(s, 'p1')
    act(s, 'p1', type='add_mana', player='p1', mana={'U': 1})
    act(s, 'p1', type='cast_spell', card_id=spell.id, sources=[])
    answer(s)
    assert s.state.cards[spell.id].zone == 'p1:graveyard'
    roundtrip(s)


def ice_charge(s, source, spell, *, mana=None, x=1):
    from tests.test_rules_library_look import settle

    wait_priority(s, 'p1')
    if mana:
        act(s, 'p1', type='add_mana', player='p1', mana=mana)
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=0, x_value=x)
    settle(s)
    d = s.state.rules.decision
    assert d is not None and d.resume['step'] == 'return_choice'
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[spell.id] if spell else [])
    answer(s)


@pytest.mark.parametrize('new_incarnation', [False, True])
def test_ice_actual_output_pays_original_exile_after_source_departure_but_never_new_incarnation(cards, noted, new_incarnation):
    from app.game.errors import ActionError

    s = table(cards, ['Ice Cauldron', 'Opt'], [], [])
    to_phase(s, 'main1', 4)
    source = put(s, 'Ice Cauldron', 'battlefield')
    spell = put(s, 'Opt', 'hand')
    ice_charge(s, source, spell, mana={'U': 1})
    to_phase(s, 'main1', 7)
    wait_priority(s, 'p1')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=1)
    assert sum(u.sym == 'U' for u in s.state.players['p1'].mana_units) == 1
    old = s.state.rules.object_id(spell.id)
    if new_incarnation:
        act(s, 'p1', type='move', card_ids=[spell.id], to={'player': 'p1', 'zone': 'hand'})
        act(s, 'p1', type='tap', card_ids=[source.id], tapped=False)
        ice_charge(s, source, spell, x=0)
        assert s.state.rules.object_id(spell.id) != old
        wait_priority(s, 'p1')
        with pytest.raises(ActionError):
            act(s, 'p1', type='cast_spell', card_id=spell.id, sources=[])
        assert s.state.cards[spell.id].zone == 'p1:exile'
        act(s, 'p1', type='add_mana', player='p1', mana={'U': 1})
    else:
        act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'graveyard'})
    wait_priority(s, 'p1')
    act(s, 'p1', type='cast_spell', card_id=spell.id, sources=[])
    answer(s)
    assert s.state.cards[spell.id].zone == 'p1:graveyard'
    assert sum(u.sym == 'U' for u in s.state.players['p1'].mana_units) == int(new_incarnation)
    roundtrip(s)


def test_ice_later_decline_keeps_last_actual_exile_but_zero_actual_note_replaces_vector(cards, noted):
    s = table(cards, ['Ice Cauldron', 'Opt'], [], [])
    to_phase(s, 'main1', 4)
    source = put(s, 'Ice Cauldron', 'battlefield')
    spell = put(s, 'Opt', 'hand')
    oid = s.state.rules.object_id(source.id)
    ice_charge(s, source, spell, mana={'G': 1})
    old = s.state.rules.noted_mana[oid].last_exiled
    to_phase(s, 'main1', 7)
    wait_priority(s, 'p1')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=1)
    act(s, 'p1', type='tap', card_ids=[source.id], tapped=False)
    ice_charge(s, source, None, x=0)
    note = s.state.rules.noted_mana[oid]
    assert note.mana == {} and note.last_exiled == old
    act(s, 'p1', type='tap', card_ids=[source.id], tapped=False)
    wait_priority(s, 'p1')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=1)
    assert sum(u.sym == 'G' for u in s.state.players['p1'].mana_units) == 1
    roundtrip(s)


def test_ice_exact_stored_mana_pays_native_buyback_additional_cost(cards, noted):
    s = table(cards, ['Ice Cauldron', 'Capsize', 'Forest'], [], [])
    to_phase(s, 'main1', 4)
    source = put(s, 'Ice Cauldron', 'battlefield')
    spell = put(s, 'Capsize', 'hand')
    target = put(s, 'Forest', 'battlefield')
    ice_charge(s, source, spell, mana={'C': 4, 'U': 2}, x=6)
    to_phase(s, 'main1', 7)
    wait_priority(s, 'p1')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=1)
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[target.id], buyback=True, sources=[])
    answer(s)
    assert s.state.cards[spell.id].zone == s.state.cards[target.id].zone == 'p1:hand'
    p = s.state.players['p1']
    assert not p.mana and not p.mana_units
    roundtrip(s)


def test_ice_restricted_units_cannot_pay_tax_on_an_unrelated_native_foundry_freecast(cards, noted):
    from app.game.errors import ActionError
    from tests.test_rules_library_look import settle

    names = ['Ice Cauldron', "Forger's Foundry", 'Opt', 'Opt']
    s = table(cards, names, ['Thalia, Guardian of Thraben'], [])
    to_phase(s, 'main1', 4)
    source = put(s, 'Ice Cauldron', 'battlefield')
    foundry = put(s, "Forger's Foundry", 'battlefield')
    spells = [c.id for c in s.state.cards.values() if c.owner == 'p1' and c.name == 'Opt']
    act(s, 'p1', type='move', card_ids=[spells[0]], to={'player': 'p1', 'zone': 'hand'})
    ice_charge(s, source, s.state.cards[spells[0]], mana={'U': 1})
    to_phase(s, 'main1', 7)
    wait_priority(s, 'p1')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=1)
    act(s, 'p1', type='activate_ability', card_id=foundry.id, ability=0)
    act(s, 'p1', type='move', card_ids=[spells[1]], to={'player': 'p1', 'zone': 'hand'})
    act(s, 'p1', type='cast_spell', card_id=spells[1], sources=[])
    answer(s)
    assert s.state.cards[spells[1]].zone == 'p1:exile'
    put(s, 'Thalia, Guardian of Thraben', 'battlefield', 'p2')
    act(s, 'p1', type='tap', card_ids=[foundry.id], tapped=False)
    wait_priority(s, 'p1')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 3, 'U': 2})
    act(s, 'p1', type='activate_ability', card_id=foundry.id, ability=1)
    settle(s)
    d = s.state.rules.decision
    if d is not None and any(o.card_id == spells[1] for o in d.options):
        option = next(o.id for o in d.options if o.card_id == spells[1])
        with pytest.raises(ActionError):
            act(s, d.player, type='choose', decision_id=d.id, option_ids=[option])
    assert s.state.cards[spells[1]].zone == 'p1:exile'
    p = s.state.players['p1']
    assert sum(u.sym == 'U' for u in p.mana_units) == 1
    roundtrip(s)


@pytest.mark.parametrize('modifier,x,mana', [('reduced', 6, {'C': 2, 'R': 2}), ('taxed', 0, {'W': 1, 'U': 1})])
def test_ice_notes_actual_activation_payment_after_reduction_and_tax_not_announced_x(cards, noted, modifier, x, mana):
    s = table(cards, ['Ice Cauldron', 'Opt', 'Zirda, the Dawnwaker', 'Suppression Field'], [], [])
    to_phase(s, 'main1', 4)
    source = put(s, 'Ice Cauldron', 'battlefield')
    put(s, 'Zirda, the Dawnwaker' if modifier == 'reduced' else 'Suppression Field', 'battlefield')
    spell = put(s, 'Opt', 'hand')
    ice_charge(s, source, spell, mana=mana, x=x)
    assert s.state.rules.noted_mana[s.state.rules.object_id(source.id)].mana == mana
    roundtrip(s)


def test_ice_countered_input_never_exiles_or_notes_and_charge_gate_rejects_new_input(cards, noted):
    from app.game.errors import ActionError

    s = table(cards, ['Ice Cauldron', 'Opt'], ['Stifle'], [])
    to_phase(s, 'main1', 4)
    source = put(s, 'Ice Cauldron', 'battlefield')
    spell = put(s, 'Opt', 'hand')
    oid = s.state.rules.object_id(source.id)
    wait_priority(s, 'p1')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=0, x_value=0)
    target = s.state.zones['stack'][-1]
    stifle = put(s, 'Stifle', 'hand', 'p2')
    wait_priority(s, 'p2')
    act(s, 'p2', type='add_mana', player='p2', mana={'U': 1})
    act(s, 'p2', type='cast_spell', card_id=stifle.id, targets=[target], sources=[])
    answer(s)
    assert s.state.cards[spell.id].zone == 'p1:hand'
    assert not s.state.cards[source.id].counters and s.state.rules.noted_mana[oid] is None
    act(s, 'p1', type='tap', card_ids=[source.id], tapped=False)
    ice_charge(s, source, spell, x=0)
    act(s, 'p1', type='tap', card_ids=[source.id], tapped=False)
    wait_priority(s, 'p1')
    with pytest.raises(ActionError):
        act(s, 'p1', type='activate_ability', card_id=source.id, ability=0, x_value=0)
    roundtrip(s)


def test_ice_copy_input_exiles_its_own_choice_but_notes_actual_zero_payment(cards, noted):
    from tests.test_rules_library_look import settle

    s = table(cards, ['Ice Cauldron', 'Opt', 'Think Twice', 'Rings of Brighthearth'], [], [])
    to_phase(s, 'main1', 4)
    source = put(s, 'Ice Cauldron', 'battlefield')
    put(s, 'Rings of Brighthearth', 'battlefield')
    spell = put(s, 'Opt', 'hand')
    put(s, 'Think Twice', 'hand')
    oid = s.state.rules.object_id(source.id)
    wait_priority(s, 'p1')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 3})
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=0, x_value=1)
    settle(s)
    d = s.state.rules.decision
    assert d is not None and any(o.id == 'pay' for o in d.options)
    act(s, d.player, type='choose', decision_id=d.id, option_ids=['pay'])
    settle(s)
    d = s.state.rules.decision
    assert d is not None and d.resume['step'] == 'return_choice'
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[spell.id])
    assert s.state.rules.noted_mana[oid].mana == {}
    settle(s)
    d = s.state.rules.decision
    assert d is not None and d.resume['step'] == 'return_choice'
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[])
    answer(s)
    note = s.state.rules.noted_mana[oid]
    assert note.mana == {'C': 1}
    assert note.last_exiled[0].card == spell.id
    assert s.state.cards[source.id].counters['charge'] == 2
    roundtrip(s)


@pytest.mark.parametrize('legacy', [False, True])
def test_ice_external_counter_without_note_is_known_zero_but_legacy_unknown_not_invented(cards, noted, legacy):
    from app.game.session import GameSession
    from app.game.state import GameState

    s = table(cards, ['Ice Cauldron'], [], [])
    to_phase(s, 'main1', 4)
    source = put(s, 'Ice Cauldron', 'battlefield')
    act(s, 'p1', type='counter', card_ids=[source.id], kind='charge', delta=1)
    if legacy:
        saved = s.state.model_dump(mode='json')
        saved['rules'].pop('noted_mana')
        s = GameSession(GameState.model_validate(saved), cards=cards)
    wait_priority(s, 'p1')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=1)
    if legacy:
        d = s.state.rules.decision
        assert d is not None and d.resume['step'] == 'unknown_noted_mana'
        act(s, d.player, type='choose', decision_id=d.id, option_ids=['done'])
    else:
        assert s.state.rules.decision is None
    assert not s.state.players['p1'].mana and not s.state.players['p1'].mana_units
    assert s.state.cards[source.id].counters.get('charge', 0) == 0
    roundtrip(s)


@pytest.mark.parametrize('family', ['input', 'payment'])
def test_ice_native_note_and_restricted_payment_resume_in_true_cold_process(cards, noted, tmp_path, family):
    import subprocess
    import sys

    from tests.test_rules_library_look import settle

    s = table(cards, ['Ice Cauldron', 'Opt'], [], [])
    to_phase(s, 'main1', 4)
    source = put(s, 'Ice Cauldron', 'battlefield')
    spell = put(s, 'Opt', 'hand')
    if family == 'input':
        wait_priority(s, 'p1')
        act(s, 'p1', type='add_mana', player='p1', mana={'U': 1})
        act(s, 'p1', type='activate_ability', card_id=source.id, ability=0, x_value=1)
        settle(s)
        assert s.state.rules.decision.resume['step'] == 'return_choice'
    else:
        ice_charge(s, source, spell, mana={'U': 1})
        to_phase(s, 'main1', 7)
        act(s, 'p1', type='set_prefs', payment='self')
        wait_priority(s, 'p1')
        act(s, 'p1', type='cast_spell', card_id=spell.id)
        assert s.state.rules.decision.resume['step'] == 'pay_mana'
    path = tmp_path / 'ice-cold.json'
    path.write_text(s.state.model_dump_json())
    code = r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from app.rules import effects, scripts, mana as M, mana_noted_profiles as n
original=scripts.define
scripts.define=lambda ability,ch:n.definition(ability,ch) or original(ability,ch)
original_mana=M.parse_mana_ability
M.parse_mana_ability=lambda text,identity=M.COLORS,*,card_name='':n.parse_mana(text,identity,card_name) or original_mana(text,identity,card_name=card_name)
effects.PRIMITIVES.update(n.PRIMITIVES)
effects.RESUME.update(n.RESUME)
path,database,family=sys.argv[1:]
repo=CardRepository(Path(database),ImageStore(Path(database).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(path).read_text()),cards=repo)
s.view('p3')
from tests.test_rules_activated_copy_family import answer
from tests.test_rules_bandmate_references import wait_priority
from tests.test_rules_wave30m_durations import to_phase
source=next(c for c in s.state.cards.values() if c.name=='Ice Cauldron' and c.zone=='p1:battlefield')
spell=next(c for c in s.state.cards.values() if c.name=='Opt' and c.owner=='p1')
if family=='input':
    d=s.state.rules.decision
    s.perform(d.player,{'type':'choose','decision_id':d.id,'option_ids':[spell.id]})
    answer(s)
    note=s.state.rules.noted_mana[s.state.rules.object_id(source.id)]
    assert note.mana=={'U':1} and note.last_exiled[0].object_id==s.state.rules.object_id(spell.id)
    to_phase(s,'main1',7)
    wait_priority(s,'p1')
    s.perform('p1',{'type':'activate_ability','card_id':source.id,'ability':1})
    s.perform('p1',{'type':'cast_spell','card_id':spell.id,'sources':[]})
else:
    d=s.state.rules.decision
    assert d.resume['step']=='pay_mana'
    s.perform('p1',{'type':'activate_ability','card_id':source.id,'ability':1})
    d=s.state.rules.decision
    if d is not None:
        assert d.resume['step']=='pay_mana'
        assert any(o.id=='pay' for o in d.options)
        s.perform(d.player,{'type':'choose','decision_id':d.id,'option_ids':['pay']})
    else:
        assert s.state.cards[spell.id].zone=='stack'
answer(s)
assert s.state.cards[spell.id].zone=='p1:graveyard'
assert not s.state.players['p1'].mana_units
assert GameState.model_validate_json(s.state.model_dump_json())==s.state
'''
    result = subprocess.run([sys.executable, '-c', code, str(path), str(cards.db_path), family],
        capture_output=True, text=True, cwd=Path(__file__).resolve().parents[1], timeout=120)
    assert result.returncode == 0, result.stderr


def test_huatli_native_front_transform_all_chapters_and_persistent_static_grant(cards, tmp_path):
    import subprocess
    import sys

    from app.rules.plan import Plan
    from tests.test_rules_library_look import settle

    name = 'Huatli, Poet of Unity // Roar of the Fifth People'
    s = table(cards, [name, 'Colossal Dreadmaw', 'Grizzly Bears'], [], [])
    to_phase(s, 'main1', 4)
    source = put(s, name, 'hand')
    wait_priority(s, 'p1')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 2, 'G': 1})
    act(s, 'p1', type='cast_spell', card_id=source.id, sources=[])
    answer(s)
    assert any(c.name == 'Forest' and c.zone == 'p1:hand' for c in s.state.cards.values())
    wait_priority(s, 'p1')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 3, 'R': 2})
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=1)
    answer(s)
    assert s.state.cards[source.id].face == 1
    dinosaurs = [c for c in s.state.cards.values() if c.is_token and c.name == 'Dinosaur' and c.zone == 'p1:battlefield']
    assert len(dinosaurs) == 2
    to_phase(s, 'main1', 7)
    answer(s)
    late = put(s, 'Grizzly Bears', 'battlefield')
    assert any(a.kind == 'mana' for a in Plan(s.state, 'p1', cards, None).ch(s.state.cards[late.id]).abilities)
    path = tmp_path / 'huatli-grant-cold.json'
    path.write_text(s.state.model_dump_json())
    code = r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from app.rules.plan import Plan
from tests.test_rules_activated_copy_family import answer
from tests.test_rules_bandmate_references import wait_priority
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
s.view('p3')
bear=next(c for c in s.state.cards.values() if c.name=='Dinosaur' and c.zone=='p1:battlefield')
ch=Plan(s.state,'p1',repo,None).ch(bear)
wait_priority(s,'p1')
s.perform('p1',{'type':'activate_ability','card_id':bear.id,'ability':next(a.index for a in ch.abilities if a.kind=='mana')})
assert s.state.rules.decision is not None
s=GameSession(GameState.model_validate_json(s.state.model_dump_json()),cards=repo)
answer(s)
p=s.state.players['p1']
assert sum(p.mana.values())+len(p.mana_units)==1
'''
    result = subprocess.run([sys.executable, '-c', code, str(path), str(cards.db_path)],
        capture_output=True, text=True, cwd=Path(__file__).resolve().parents[1], timeout=120)
    assert result.returncode == 0, result.stderr
    act(s, 'p1', type='counter', card_ids=[source.id], kind='lore', delta=-2)
    ch = Plan(s.state, 'p1', cards, None).ch(s.state.cards[dinosaurs[0].id])
    index = next(a.index for a in ch.abilities if a.kind == 'mana')
    wait_priority(s, 'p1')
    act(s, 'p1', type='activate_ability', card_id=dinosaurs[0].id, ability=index)
    answer(s)
    p = s.state.players['p1']
    assert sum(p.mana.values()) + len(p.mana_units) == 1
    act(s, 'p1', type='counter', card_ids=[source.id], kind='lore', delta=2)
    to_phase(s, 'main1', 10)
    answer(s)
    assert any(c.name == 'Colossal Dreadmaw' and c.zone == 'p1:hand' for c in s.state.cards.values())
    to_phase(s, 'main1', 13)
    settle(s)
    answer(s)
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    for dinosaur in dinosaurs:
        ch = Plan(s.state, 'p1', cards, None).ch(s.state.cards[dinosaur.id])
        assert {'double strike', 'trample'} <= ch.keywords
        assert not any(a.kind == 'mana' for a in ch.abilities)
    roundtrip(s)


def test_huatli_resolved_grant_survives_later_song_but_not_source_blink(cards):
    from app.rules.plan import Plan

    name = 'Huatli, Poet of Unity // Roar of the Fifth People'
    s = table(cards, [name, 'Grizzly Bears', 'Song of the Dryads'], [], [])
    to_phase(s, 'main1', 4)
    source = put(s, name, 'battlefield')
    wait_priority(s, 'p1')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 3, 'R': 2})
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=1)
    answer(s)
    to_phase(s, 'main1', 7)
    answer(s)
    bear = put(s, 'Grizzly Bears', 'battlefield')
    assert any(a.kind == 'mana' for a in Plan(s.state, 'p1', cards, None).ch(s.state.cards[bear.id]).abilities)
    song = put(s, 'Song of the Dryads', 'hand')
    wait_priority(s, 'p1')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 2, 'G': 1})
    act(s, 'p1', type='cast_spell', card_id=song.id, targets=[source.id], sources=[])
    answer(s)
    assert Plan(s.state, 'p1', cards, None).ch(s.state.cards[source.id]).is_land
    assert any(a.kind == 'mana' for a in Plan(s.state, 'p1', cards, None).ch(s.state.cards[bear.id]).abilities)
    roundtrip(s)
    act(s, 'p1', type='set_controller', card_ids=[bear.id], player='p2')
    assert not any(a.kind == 'mana' for a in Plan(s.state, 'p1', cards, None).ch(s.state.cards[bear.id]).abilities)
    act(s, 'p1', type='set_controller', card_ids=[source.id], player='p2')
    assert any(a.kind == 'mana' for a in Plan(s.state, 'p1', cards, None).ch(s.state.cards[bear.id]).abilities)
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'exile'})
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'battlefield'})
    answer(s)
    assert not any(a.kind == 'mana' for a in Plan(s.state, 'p1', cards, None).ch(s.state.cards[bear.id]).abilities)
    roundtrip(s)


@pytest.mark.parametrize('wipe_first', [False, True])
def test_huatli_resolved_grant_and_real_dress_down_timestamp_order(cards, wipe_first):
    from app.rules.plan import Plan

    name = 'Huatli, Poet of Unity // Roar of the Fifth People'
    s = table(cards, [name, 'Grizzly Bears', 'Opalescence', 'Dress Down'], [], [])
    to_phase(s, 'main1', 4)
    source = put(s, name, 'battlefield')
    put(s, 'Opalescence', 'battlefield')
    wait_priority(s, 'p1')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 3, 'R': 2})
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=1)
    answer(s)
    to_phase(s, 'main1', 7)
    assert s.state.zones.get('stack')
    if not wipe_first:
        answer(s)
    dress = put(s, 'Dress Down', 'hand')
    wait_priority(s, 'p1')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 1, 'U': 1})
    act(s, 'p1', type='cast_spell', card_id=dress.id, sources=[])
    answer(s)
    bear = put(s, 'Grizzly Bears', 'battlefield')
    assert any(a.kind == 'mana' for a in Plan(s.state, 'p1', cards, None).ch(s.state.cards[bear.id]).abilities) == wipe_first
    roundtrip(s)



@pytest.mark.parametrize('return_again', [False, True])
def test_yue_death_return_requires_original_graveyard_incarnation(cards, return_again):
    from tests.test_rules_library_look import settle

    s = table(cards, ['Princess Yue'], [], [])
    to_phase(s, 'main1', 4)
    source = put(s, 'Princess Yue', 'battlefield')
    act(s, 'p1', type='set_damage', card_ids=[source.id], delta=10)
    wait_priority(s, 'p1')
    act(s, 'p1', type='pass_priority')
    assert s.state.cards[source.id].zone == 'p1:graveyard' and s.state.zones.get('stack')
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'exile'})
    if return_again:
        act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'graveyard'})
    settle(s)
    answer(s)
    assert s.state.cards[source.id].zone == ('p1:graveyard' if return_again else 'p1:exile')
    roundtrip(s)

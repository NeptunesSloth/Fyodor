"""Plargg and Nassari: cross-owner original exiled objects and two spells during resolution."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import context, coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditionals import settle, until
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

NAME = 'Plargg and Nassari'


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/plargg_nassari_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='plg', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards, tops=(('Forest', 'Grizzly Bears'), ('Island', 'Lightning Bolt'), ('Island', 'Opt')), extra=()):
    s = table(cards, [NAME, *tops[0], *extra], tops[1], tops[2])
    source = put(s, NAME, 'battlefield')
    to_phase(s, 'main1', turn=3)
    selected = {}
    for pid, names in zip(['p1', 'p2', 'p3'], tops, strict=True):
        chosen = []
        for name in names:
            chosen.append(next(c.id for c in s.state.cards.values() if c.name == name and c.owner == pid and c.id not in chosen))
        for cid in reversed(chosen):
            act(s, pid, type='move', card_ids=[cid], to={'player': pid, 'zone': 'library'}, position='top')
        selected[pid] = chosen
    to_phase(s, 'upkeep', turn=4)
    return s, source, selected


def pick_opponent(s, pid='p3'):
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.resume.get('step') == 'plargg_opponent')
    d = s.state.rules.decision
    assert d.player == 'p1' and {o.id for o in d.options} == {'p2', 'p3'}
    roundtrip(s)
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[pid])
    assert s.state.rules.decision.player == pid
    assert s.state.rules.decision.resume['step'] == 'plargg_exclude'


def choose(s, ids):
    d = s.state.rules.decision
    assert d is not None
    roundtrip(s)
    act(s, d.player, type='choose', decision_id=d.id, option_ids=ids)


def exclude(s, cid):
    choose(s, [cid])
    d = s.state.rules.decision
    assert d is not None and d.player == 'p1' and d.resume['step'] == 'free_cast_pick'
    return d


def test_plargg_is_full(cards):
    assert coverage.of_card_data(cards.resolve(NAME)).level == 'FULL'


def test_controller_chooses_opponent_then_only_nonland_can_be_excluded(cards):
    s, _, selected = setup(cards)
    pick_opponent(s)
    assert {o.id for o in s.state.rules.decision.options} == {selected[p][-1] for p in selected}
    for pid, ids in selected.items():
        assert all(s.state.cards[cid].zone == f'{pid}:exile' for cid in ids)
        assert all(s.view('p2')['cards'][cid]['name'] == s.state.cards[cid].name for cid in ids)
    ordered = [event.card for event in s.state.rules.events if event.kind == 'zone_change' and not event.manual
               and (event.to_zone or '').endswith(':exile') and event.card in {c for ids in selected.values() for c in ids}]
    assert ordered == [c for pid in ['p1', 'p2', 'p3'] for c in selected[pid]]
    d = exclude(s, selected['p1'][-1])
    bound = context.refs(d.resume['ctx'])['plargg_available']['objects']
    assert {r['card'] for r in bound} == {c for ids in selected.values() for c in ids} - {selected['p1'][-1]}
    assert {o.card_id for o in d.options} == {selected['p2'][-1], selected['p3'][-1]}
    choose(s, [])
    settle(s)
    assert all(s.state.cards[cid].zone.endswith(':exile') for ids in selected.values() for cid in ids)
    roundtrip(s)


def test_casts_two_opponents_spells_before_either_resolves_and_preserves_ownership(cards):
    s, _, selected = setup(cards)
    pick_opponent(s)
    exclude(s, selected['p1'][-1])
    bolt, opt = selected['p2'][-1], selected['p3'][-1]
    choose(s, [bolt])
    assert s.state.rules.decision.resume['step'] == 'cast_target'
    choose(s, ['p2'])
    assert s.state.rules.decision.resume['step'] == 'free_cast_pick'
    assert s.state.cards[bolt].zone == 'stack' and s.state.players['p2'].life == 40
    choose(s, [opt])
    settle(s)
    assert s.state.players['p2'].life == 37
    assert s.state.cards[bolt].zone == 'p2:graveyard' and s.state.cards[opt].zone == 'p3:graveyard'
    assert s.state.cards[bolt].owner == 'p2' and s.state.cards[opt].owner == 'p3'
    assert not s.state.rules.free_casts and s.state.rules.free_cast_then is None
    roundtrip(s)


@pytest.mark.parametrize('accept', [False, True])
def test_one_or_zero_spells_are_legal_choices(cards, accept):
    s, _, selected = setup(cards)
    pick_opponent(s)
    exclude(s, selected['p2'][-1])
    if accept:
        choose(s, [selected['p1'][-1]])
    choose(s, [])
    settle(s)
    assert s.state.cards[selected['p1'][-1]].zone == ('p1:battlefield' if accept else 'p1:exile')
    assert s.state.cards[selected['p3'][-1]].zone == 'p3:exile'
    roundtrip(s)


def test_source_leaving_or_changing_control_does_not_change_existing_caster(cards):
    s, source, selected = setup(cards)
    pick_opponent(s)
    act(s, 'p1', type='set_controller', card_ids=[source.id], player='p2')
    act(s, 'p2', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'graveyard'})
    exclude(s, selected['p2'][-1])
    choose(s, [selected['p1'][-1]])
    choose(s, [])
    settle(s)
    assert s.state.cards[selected['p1'][-1]].zone == 'p1:battlefield'
    roundtrip(s)


@pytest.mark.parametrize('top,option', [('Valki, God of Lies // Tibalt, Cosmic Impostor', '@1'),
                                      ('Bonecrusher Giant // Stomp', '@1'), ('Endless One', '')])
def test_native_faces_adventure_and_free_x_zero(cards, top, option):
    s, _, selected = setup(cards, tops=(('Forest', top), ('Island', 'Grizzly Bears'), ('Island', 'Opt')))
    pick_opponent(s)
    d = exclude(s, selected['p2'][-1])
    cid = selected['p1'][-1]
    assert any(o.id == cid + option for o in d.options)
    choose(s, [cid + option])
    if option and 'Bonecrusher' in top:
        assert s.state.rules.decision.resume['step'] == 'cast_target'
        choose(s, ['p2'])
    if s.state.rules.decision and s.state.rules.decision.resume.get('step') == 'free_cast_pick':
        choose(s, [])
    settle(s)
    assert s.state.cards[cid].zone == ('p1:battlefield' if 'Valki' in top else 'p1:exile' if 'Bonecrusher' in top else 'p1:graveyard')
    if 'Valki' in top:
        assert s.state.cards[cid].face == 1
    if 'Bonecrusher' in top:
        assert s.state.players['p2'].life == 38
    roundtrip(s)


def test_cancelling_target_choice_leaves_card_exiled_without_stranding_resolution(cards):
    s, _, selected = setup(cards)
    pick_opponent(s)
    exclude(s, selected['p1'][-1])
    choose(s, [selected['p2'][-1]])
    assert s.state.rules.decision.resume['step'] == 'cast_target'
    choose(s, ['cancel'])
    settle(s)
    assert s.state.cards[selected['p2'][-1]].zone == 'p2:exile'
    assert s.state.rules.free_cast_then is None and not s.state.rules.free_casts
    assert not s.state.zones.get('stack')
    roundtrip(s)


def test_empty_or_all_land_libraries_exile_without_draw_or_loss(cards):
    s, _, _ = setup(cards, tops=((), (), ()))
    settle(s)
    assert all(not s.state.zones.get(f'{pid}:library') for pid in ['p1', 'p2', 'p3'])
    assert not s.state.rules.lost
    assert not s.state.rules.decision
    roundtrip(s)


def test_second_free_spell_can_counter_the_first_before_either_resolves(cards):
    s, _, selected = setup(cards, tops=(('Forest', 'Grizzly Bears'), ('Island', 'Counterspell'), ('Island', 'Opt')))
    pick_opponent(s)
    exclude(s, selected['p3'][-1])
    bear, counter = selected['p1'][-1], selected['p2'][-1]
    choose(s, [bear])
    assert s.state.cards[bear].zone == 'stack'
    choose(s, [counter])
    assert s.state.rules.decision.resume['step'] == 'cast_target'
    choose(s, [bear])
    settle(s)
    assert s.state.cards[bear].zone == 'p1:graveyard'
    assert s.state.cards[counter].zone == 'p2:graveyard'
    assert s.state.rules.spells_this_turn('p1', 4) == 2
    roundtrip(s)


def test_rule_of_law_removes_the_second_cast_opportunity(cards):
    s, _, selected = setup(cards, extra=['Rule of Law'])
    put(s, 'Rule of Law', 'battlefield')
    pick_opponent(s)
    exclude(s, selected['p2'][-1])
    choose(s, [selected['p1'][-1]])
    settle(s)
    assert s.state.cards[selected['p1'][-1]].zone == 'p1:battlefield'
    assert s.state.cards[selected['p3'][-1]].zone == 'p3:exile'
    assert s.state.rules.spells_this_turn('p1', 4) == 1
    roundtrip(s)


def test_opponents_drannith_forbids_all_exile_casts_without_stranding_ability(cards):
    s, _, selected = setup(cards, extra=['Drannith Magistrate'])
    magistrate = put(s, 'Drannith Magistrate', 'battlefield')
    act(s, 'p1', type='set_controller', card_ids=[magistrate.id], player='p2')
    pick_opponent(s)
    choose(s, [selected['p1'][-1]])
    settle(s)
    assert all(s.state.cards[cid].zone.endswith(':exile') for ids in selected.values() for cid in ids)
    assert not s.state.rules.free_casts and s.state.rules.free_cast_then is None
    roundtrip(s)


def test_unpayable_mandatory_additional_cost_is_not_offered(cards):
    s, _, selected = setup(cards, tops=(('Forest', 'Skaab Ruinator'), ('Island', 'Grizzly Bears'), ('Island', 'Opt')))
    pick_opponent(s)
    d = exclude(s, selected['p2'][-1])
    assert selected['p1'][-1] not in {o.card_id for o in d.options}
    choose(s, [])
    settle(s)
    assert s.state.cards[selected['p1'][-1]].zone == 'p1:exile'
    roundtrip(s)


def test_excluding_a_departed_original_object_reasks_and_never_excludes_replacement(cards):
    s, _, selected = setup(cards)
    pick_opponent(s)
    old = selected['p3'][-1]
    for zone in ['hand', 'exile']:
        act(s, 'p3', type='move', card_ids=[old], to={'player': 'p3', 'zone': zone})
    choose(s, [old])
    assert s.state.rules.decision.player == 'p3'
    assert old not in {o.card_id for o in s.state.rules.decision.options}
    d = exclude(s, selected['p1'][-1])
    assert old not in {o.card_id for o in d.options}
    choose(s, [])
    settle(s)
    roundtrip(s)


def test_free_cast_revalidates_original_exiled_object_after_saved_choice(cards):
    s, _, selected = setup(cards)
    pick_opponent(s)
    exclude(s, selected['p1'][-1])
    old = selected['p3'][-1]
    for zone in ['hand', 'exile']:
        act(s, 'p3', type='move', card_ids=[old], to={'player': 'p3', 'zone': zone})
    choose(s, [old])
    assert s.state.rules.decision.resume['step'] == 'free_cast_pick'
    assert old not in {o.card_id for o in s.state.rules.decision.options}
    choose(s, [])
    settle(s)
    assert s.state.cards[old].zone == 'p3:exile'
    roundtrip(s)


def test_opponent_departing_before_selection_falls_back_to_remaining_opponent(cards):
    s, _, selected = setup(cards)
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.resume.get('step') == 'plargg_opponent')
    act(s, 'p1', type='remove_player', player='p3')
    choose(s, ['p3'])
    assert s.state.rules.decision.player == 'p2' and s.state.rules.decision.resume['step'] == 'plargg_exclude'
    exclude(s, selected['p1'][-1])
    choose(s, [])
    settle(s)
    roundtrip(s)


def test_four_players_offer_three_other_spells_but_allow_only_two_casts(cards):
    from app.game.factory import PlayerSetup, new_game
    from app.game.session import GameSession
    from tests.game_helpers import deck, enable

    spells = [['Plargg and Nassari', 'Grizzly Bears'], ['Lightning Bolt'], ['Opt'], ['Ancestral Vision']]
    seats = [PlayerSetup(f'Player {i}', cards=deck(cards, 'Krenko, Mob Boss', [*((1, n) for n in names), (20, 'Forest')]))
             for i, names in enumerate(spells, 1)]
    s = GameSession(enable(new_game(seats, shuffle=False)), cards=cards)
    act(s, 'p1', type='pass_priority')
    for pid in s.state.players:
        act(s, pid, type='set_prefs', response='on')
    put(s, NAME, 'battlefield')
    to_phase(s, 'main1', turn=4)
    selected = {}
    for pid, name in zip(['p1', 'p2', 'p3', 'p4'], ['Grizzly Bears', 'Lightning Bolt', 'Opt', 'Ancestral Vision'], strict=True):
        candidate = next(c for c in s.state.cards.values() if c.owner == pid and c.name == name)
        selected[pid] = candidate.id
        act(s, pid, type='move', card_ids=[candidate.id], to={'player': pid, 'zone': 'library'}, position='top')
    to_phase(s, 'upkeep', turn=5)
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.resume.get('step') == 'plargg_opponent')
    choose(s, ['p4'])
    d = exclude(s, selected['p1'])
    assert {o.card_id for o in d.options} == set(selected.values()) - {selected['p1']}
    choose(s, [selected['p3']])
    assert s.state.rules.decision.resume['step'] == 'free_cast_pick'
    choose(s, [selected['p4']])
    assert s.state.rules.decision.resume['step'] == 'cast_target'
    choose(s, ['p1'])
    assert not s.state.rules.decision
    settle(s)
    assert s.state.rules.spells_this_turn('p1', 5) == 2
    assert s.state.cards[selected['p2']].zone == 'p2:exile'
    assert s.state.cards[selected['p3']].zone == 'p3:graveyard'
    assert s.state.cards[selected['p4']].zone == 'p4:graveyard'
    roundtrip(s)


@pytest.mark.parametrize('stage', ['opponent', 'exclude', 'cast'])
def test_saved_opponent_and_exclusion_and_cross_owner_cast_choices_resume_cold(cards, tmp_path, stage):
    import subprocess
    import sys

    s, _, selected = setup(cards)
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.resume.get('step') == 'plargg_opponent')
    if stage != 'opponent':
        choose(s, ['p3'])
    if stage == 'cast':
        exclude(s, selected['p1'][-1])
    saved = tmp_path / f'plargg-{stage}.json'
    saved.write_text(s.state.model_dump_json())
    script = r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
saved, database, excluded, spell = sys.argv[1:]
repo = CardRepository(Path(database), ImageStore(Path(database).parent / 'images'))
s = GameSession(GameState.model_validate_json(Path(saved).read_text()), cards=repo)
def choose(ids):
    d=s.state.rules.decision
    s.perform(d.player, {'type':'choose','decision_id':d.id,'option_ids':ids})
if s.state.rules.decision.resume['step']=='plargg_opponent':
    choose(['p3'])
if s.state.rules.decision.resume['step']=='plargg_exclude':
    choose([excluded])
assert s.state.rules.decision.resume['step']=='free_cast_pick'
choose([spell])
assert s.state.rules.decision.resume['step']=='free_cast_pick'
choose([])
for _ in range(80):
    d=s.state.rules.decision
    if d is not None:
        choose([o.id for o in d.options][:max(1,d.min_choices)])
    elif s.state.zones.get('stack'):
        s.perform(s.state.rules.priority, {'type':'pass_priority'})
    else:
        break
else:
    raise AssertionError('did not settle')
assert s.state.cards[spell].zone=='p3:graveyard'
assert s.state.cards[excluded].zone=='p1:exile'
assert not s.state.rules.free_casts and s.state.rules.free_cast_then is None
assert s.history.rebuild().model_dump(mode='json')==s.state.model_dump(mode='json')
repo.close()
'''
    result = subprocess.run([sys.executable, '-c', script, str(saved), str(cards.db_path), selected['p1'][-1], selected['p3'][-1]],
                            cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr

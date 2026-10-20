"""Cumulative exile thresholds reset per opponent; Dream's free casts retain normal timing."""
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
from tests.test_rules_bandmate_references import mana, wait_priority
from tests.test_rules_conditionals import settle
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

INVOKE = 'Invoke Calamity'
ROD = 'Rod of Absorption'


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/total_mv_casts_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='emt', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()



def choose(s, ids):
    d = s.state.rules.decision
    assert d is not None
    roundtrip(s)
    act(s, d.player, type='choose', decision_id=d.id, option_ids=ids)


def pick(s, cid, *, contains=None):
    d = s.state.rules.decision
    assert d is not None and d.resume['step'] == 'free_cast_pick'
    option = next(o for o in d.options if o.card_id == cid and (contains is None or contains in o.label))
    choose(s, [option.id])


def own(s, name, zone='hand', used=()):
    obj = next(c for c in s.state.cards.values() if c.name == name and c.owner == 'p1' and c.id not in used)
    act(s, 'p1', type='move', card_ids=[obj.id], to={'player': 'p1', 'zone': zone})
    return obj.id


def invoke(cards, spells=('Cancel', 'Cancel', 'Opt'), grave=(), creatures=()):
    from tests.test_rules_conditionals import until

    s = table(cards, [INVOKE, *spells, *creatures], ['Lightning Bolt', 'Counterspell'], [])
    act(s, 'p1', type='set_prefs', hold_priority=True)
    placed = []
    for name in creatures:
        placed.append(own(s, name, 'battlefield', used=placed))
    chosen = []
    for i, name in enumerate(spells):
        chosen.append(own(s, name, 'graveyard' if i in grave else 'hand', used=chosen))
    source = own(s, INVOKE)
    mana(s, C=1, R=4)
    act(s, 'p1', type='cast_spell', card_id=source)
    until(s, lambda s: s.state.rules.decision is not None)
    assert s.state.rules.decision.resume['step'] == 'free_cast_pick'
    return s, source, chosen


@pytest.mark.parametrize('name', [INVOKE, ROD])
def test_canonical_budget_cards_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


def test_invoke_two_actual_spells_total_exactly_six_and_second_targets_first(cards):
    s, source, spells = invoke(cards, grave=(1,))
    pick(s, spells[0])
    choose(s, [source])
    assert s.state.rules.decision.resume['step'] == 'free_cast_pick'
    assert s.state.rules.decision.resume['ctx']['free_cast_budget'] == 3
    assert s.state.cards[spells[0]].zone == 'stack'
    pick(s, spells[1])
    choose(s, [spells[0]])
    assert s.state.rules.decision is None
    assert s.state.cards[source].zone == 'p1:exile'
    assert s.state.zones['stack'] == [spells[0], spells[1]]
    settle(s)
    assert all(s.state.cards[c].zone == 'p1:exile' for c in [source, *spells[:2]])
    assert s.state.cards[spells[2]].zone == 'p1:hand'
    roundtrip(s)


def test_invoke_stops_after_two_even_when_budget_remains(cards):
    s, source, spells = invoke(cards, ('Opt', 'Opt', 'Cancel'))
    pick(s, spells[0])
    pick(s, spells[1])
    assert s.state.rules.decision is None and len(s.state.zones['stack']) == 2
    assert s.state.cards[source].zone == 'p1:exile'
    settle(s)
    assert s.state.cards[spells[2]].zone == 'p1:hand'
    roundtrip(s)


def test_invoke_decline_zero_casts_still_exiles_source(cards):
    s, source, spells = invoke(cards)
    choose(s, [])
    assert not s.state.zones['stack'] and s.state.cards[source].zone == 'p1:exile'
    assert s.state.rules.free_cast_then is None and not s.state.rules.free_casts
    assert all(s.state.cards[c].zone == 'p1:hand' for c in spells)
    roundtrip(s)


def rod(cards, spells=('Opt', 'Lightning Bolt'), extra=()):

    s = table(cards, [ROD, *spells, *extra], ['Opt', 'Lightning Bolt'], [])
    act(s, 'p1', type='set_prefs', hold_priority=True)
    source = put(s, ROD, 'battlefield')
    chosen = []
    for name in spells:
        cid = own(s, name, used=chosen)
        chosen.append(cid)
        mana(s, U=1, R=1)
        act(s, 'p1', type='cast_spell', card_id=cid, **({'targets': ['p2']} if name == 'Lightning Bolt' else {}))
        settle(s)
        assert s.state.cards[cid].zone == 'p1:exile'
    return s, source, chosen


def activate_rod(s, source, x, pid='p1'):
    from tests.test_rules_conditionals import until
    from tests.test_rules_wave7b_activation import ability_index

    wait_priority(s, pid)
    mana(s, pid=pid, C=x)
    act(s, pid, type='activate_ability', card_id=source.id, ability=ability_index(s, s.state.cards[source.id], 'You may cast'), x_value=x)
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    until(s, lambda s: s.state.rules.decision is not None)
    assert s.state.rules.decision.resume['step'] == 'free_cast_pick'


def test_rod_actual_capture_and_saved_x_budget_after_sacrificing_source(cards):
    s, source, spells = rod(cards)
    activate_rod(s, source, 1)
    pick(s, spells[0])
    assert s.state.rules.decision is None
    assert s.state.cards[spells[1]].zone == 'p1:exile'
    settle(s)
    assert s.state.cards[spells[0]].zone == 'p1:graveyard'
    roundtrip(s)


def test_remaining_budget_filters_actual_spell_faces(cards):
    s, source, spells = invoke(cards, ('Concentrate', 'Cancel', 'Fire // Ice', 'Demon of Catastrophes'), creatures=('Grizzly Bears',))
    first = {o.card_id for o in s.state.rules.decision.options}
    assert spells[3] not in first
    pick(s, spells[0])
    d = s.state.rules.decision
    assert d.resume['ctx']['free_cast_budget'] == 2
    assert spells[1] not in {o.card_id for o in d.options}
    assert spells[2] in {o.card_id for o in d.options}
    pick(s, spells[2], contains='Ice')
    choose(s, [next(c.id for c in s.state.cards.values() if c.name == 'Grizzly Bears')])
    assert s.state.rules.decision is None and s.state.cards[source].zone == 'p1:exile'
    settle(s)
    assert all(s.state.cards[c].zone == 'p1:exile' for c in [spells[0], spells[2]])
    roundtrip(s)


def test_second_spell_can_gain_a_legal_target_from_first_spell(cards):
    s, source, spells = invoke(cards, ('Counterspell', 'Spell Snare'))
    assert spells[1] not in {o.card_id for o in s.state.rules.decision.options}
    pick(s, spells[0])
    choose(s, [source])
    assert spells[1] in {o.card_id for o in s.state.rules.decision.options}
    pick(s, spells[1])
    choose(s, [spells[0]])
    settle(s)
    assert all(s.state.cards[c].zone == 'p1:exile' for c in spells)
    roundtrip(s)


def test_adventure_face_is_chosen_by_spell_type_and_its_own_mana_value(cards):
    s, source, spells = invoke(cards, ('Concentrate', 'Bonecrusher Giant // Stomp'))
    pick(s, spells[0])
    options = [o for o in s.state.rules.decision.options if o.card_id == spells[1]]
    assert options and all('Stomp' in o.label for o in options)
    pick(s, spells[1])
    choose(s, ['p2'])
    settle(s)
    assert s.state.players['p2'].life == 38
    assert s.state.cards[spells[1]].zone == 'p1:exile'
    roundtrip(s)


def test_additional_sacrifice_cost_is_paid_and_only_completed_spell_charges(cards):
    s, source, spells = invoke(cards, ('Fling', 'Opt'), creatures=('Grizzly Bears', 'Grizzly Bears'))
    bear = next(c for c in s.state.cards.values() if c.name == 'Grizzly Bears')
    pick(s, spells[0])
    choose(s, ['p2'])
    d = s.state.rules.decision
    assert d.resume['step'] == 'ability_cost'
    assert d.resume['intent']['card_id'] == spells[0]
    choose(s, [bear.id])
    d = s.state.rules.decision
    assert d.resume['step'] == 'free_cast_pick' and d.resume['ctx']['free_cast_budget'] == 4
    choose(s, [])
    settle(s)
    assert s.state.cards[bear.id].zone == 'p1:graveyard' and s.state.players['p2'].life == 38
    roundtrip(s)


def test_cancelled_target_announcement_does_not_cast_or_apply_exile_rider(cards):
    s, source, spells = invoke(cards, ('Lightning Bolt', 'Opt'))
    pick(s, spells[0])
    choose(s, ['cancel'])
    assert s.state.cards[spells[0]].zone == 'p1:hand'
    assert s.state.cards[source].zone == 'p1:exile'
    assert s.state.rules.free_cast_then is None and not s.state.rules.free_casts
    roundtrip(s)


def test_rod_captures_opponents_spell_and_casts_it_with_original_owner(cards):
    s, source, spells = rod(cards, ())
    bolt = put(s, 'Lightning Bolt', 'hand', 'p2')
    mana(s, pid='p2', R=1)
    wait_priority(s, 'p2')
    act(s, 'p2', type='cast_spell', card_id=bolt.id, targets=['p3'])
    settle(s)
    assert s.state.cards[bolt.id].zone == 'p2:exile'
    activate_rod(s, source, 1)
    pick(s, bolt.id)
    choose(s, ['p2'])
    settle(s)
    assert s.state.cards[bolt.id].zone == 'p2:graveyard'
    assert s.state.players['p2'].life == s.state.players['p3'].life == 37
    roundtrip(s)


def test_rod_x_zero_can_cast_zero_value_no_mana_cost_spell(cards):
    s, source, _ = rod(cards, (), extra=('As Foretold', 'Ancestral Vision'))
    put(s, 'As Foretold', 'battlefield')
    vision = own(s, 'Ancestral Vision')
    offers = s.view('p1')['rules']['hints']['alt_castable'][vision]
    act(s, 'p1', type='cast_spell', card_id=vision, alt_cost=offers[0]['id'], targets=['p1'])
    settle(s)
    assert s.state.cards[vision].zone == 'p1:exile'
    activate_rod(s, source, 0)
    pick(s, vision)
    choose(s, ['p1'])
    assert s.state.rules.decision is None
    settle(s)
    assert s.state.cards[vision].zone == 'p1:graveyard'
    roundtrip(s)


def conflict(cards, kind='rods'):
    from tests.test_rules_conditionals import until

    s = table(cards, [ROD, ROD, 'Feather, the Redeemed', 'Shelter', 'Grizzly Bears', 'Lightning Bolt', 'Rest in Peace'], [], [])
    act(s, 'p1', type='set_prefs', hold_priority=True)
    first = put(s, ROD, 'battlefield')
    sources = {'rod': first.id}
    if kind == 'rods':
        sources['second'] = own(s, ROD, 'battlefield', used=(first.id,))
    elif kind == 'feather':
        sources['feather'] = put(s, 'Feather, the Redeemed', 'battlefield').id
    else:
        put(s, 'Rest in Peace', 'battlefield')
        settle(s)
    name = 'Shelter' if kind == 'feather' else 'Lightning Bolt'
    spell = own(s, name)
    target = put(s, 'Grizzly Bears', 'battlefield').id if kind == 'feather' else 'p2'
    mana(s, C=1, W=1, R=1)
    act(s, 'p1', type='cast_spell', card_id=spell, targets=[target])
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.resume['step'] == 'zone_replace_order')
    d = s.state.rules.decision
    assert d.player == 'p1' and len(d.options) == 2
    return s, sources, spell


def test_two_rods_spell_controller_chooses_exact_linked_source(cards):
    s, sources, spell = conflict(cards)
    d = s.state.rules.decision
    assert {o.card_id for o in d.options} == set(sources.values())
    choose(s, [next(o.id for o in d.options if o.card_id == sources['second'])])
    assert s.state.cards[spell].zone == 'p1:exile'
    assert s.state.rules.exiled_with == {s.state.rules.object_id(sources['second']): [s.state.rules.object_id(spell)]}
    roundtrip(s)


@pytest.mark.parametrize('selected', ['rod', 'feather'])
def test_rod_feather_only_chosen_link_or_delayed_return_occurs(cards, selected):
    s, sources, spell = conflict(cards, 'feather')
    d = s.state.rules.decision
    choose(s, [next(o.id for o in d.options if o.card_id == sources[selected])])
    assert s.state.cards[spell].zone == 'p1:exile'
    assert len(s.state.rules.delayed) == (1 if selected == 'feather' else 0)
    assert bool(s.state.rules.exiled_with) == (selected == 'rod')
    to_phase(s, 'end', turn=1)
    settle(s)
    assert s.state.cards[spell].zone == ('p1:hand' if selected == 'feather' else 'p1:exile')
    assert not s.state.rules.delayed
    roundtrip(s)


def test_rest_in_peace_can_replace_resolved_departure_without_linking_to_rod(cards):
    s, _, spell = conflict(cards, 'rip')
    d = s.state.rules.decision
    choose(s, [next(o.id for o in d.options if 'Rest in Peace' in o.label)])
    assert s.state.cards[spell].zone == 'p1:exile' and not s.state.rules.exiled_with
    roundtrip(s)


@pytest.mark.parametrize('selected', ['rod', 'feather'])
def test_cold_pending_616_resumes_exact_selected_link_and_single_rider(cards, tmp_path, selected):
    import subprocess
    import sys

    s, sources, spell = conflict(cards, 'feather')
    d = s.state.rules.decision
    option = next(o.id for o in d.options if o.card_id == sources[selected])
    saved = tmp_path / f'rod-616-{selected}.json'
    saved.write_text(s.state.model_dump_json())
    script = r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
saved, db, option, spell, selected, rod = sys.argv[1:]
repo=CardRepository(Path(db),ImageStore(Path(db).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(saved).read_text()),cards=repo)
d=s.state.rules.decision
assert d.resume['step']=='zone_replace_order'
s.perform(d.player,{'type':'choose','decision_id':d.id,'option_ids':[option]})
assert s.state.cards[spell].zone=='p1:exile'
assert len(s.state.rules.delayed)==(1 if selected=='feather' else 0)
if selected=='rod':
    assert s.state.rules.exiled_with=={s.state.rules.object_id(rod):[s.state.rules.object_id(spell)]}
else:
    assert not s.state.rules.exiled_with
assert not s.state.rules.pending_616
assert s.history.rebuild().model_dump(mode='json')==s.state.model_dump(mode='json')
repo.close()
'''
    result = subprocess.run([sys.executable, '-c', script, str(saved), str(cards.db_path), option, spell, selected, sources['rod']],
                            cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize('x,face_name', [(2, 'Stomp'), (3, 'Bonecrusher Giant')])
def test_rod_budget_uses_actual_adventure_or_creature_spell_face(cards, x, face_name):
    s, source, _ = rod(cards, (), extra=('Bonecrusher Giant // Stomp',))
    giant = own(s, 'Bonecrusher Giant // Stomp')
    mana(s, C=1, R=1)
    act(s, 'p1', type='cast_spell', card_id=giant, face=1, targets=['p2'])
    settle(s)
    assert s.state.cards[giant].zone == 'p1:exile'
    activate_rod(s, source, x)
    options = [o for o in s.state.rules.decision.options if o.card_id == giant]
    if x == 2:
        assert all('Stomp' in o.label for o in options)
    pick(s, giant, contains=face_name)
    if x == 2:
        choose(s, ['p2'])
    settle(s)
    assert s.state.cards[giant].zone == ('p1:battlefield' if x == 3 else 'p1:exile')
    roundtrip(s)


def test_rod_announced_x_is_frozen_when_cast_spell_has_its_own_x_zero(cards):
    s, source, _ = rod(cards, ('Lightning Bolt',), extra=('Shatterskull Smashing // Shatterskull, the Hammer Pass',))
    smash = own(s, 'Shatterskull Smashing // Shatterskull, the Hammer Pass')
    mana(s, R=2)
    act(s, 'p1', type='cast_spell', card_id=smash, x_value=0, targets=[])
    settle(s)
    assert s.state.cards[smash].zone == 'p1:exile'
    activate_rod(s, source, 3)
    pick(s, smash)
    d = s.state.rules.decision
    assert d.resume['step'] == 'free_cast_pick' and d.resume['ctx']['free_cast_budget'] == 1
    choose(s, [])
    settle(s)
    roundtrip(s)


def test_stale_original_link_cannot_cast_returned_exile_object(cards):
    from tests.test_rules_wave7b_activation import ability_index

    s, source, spells = rod(cards, ('Lightning Bolt',))
    act(s, 'p1', type='move', card_ids=spells, to={'player': 'p1', 'zone': 'hand'})
    act(s, 'p1', type='move', card_ids=spells, to={'player': 'p1', 'zone': 'exile'})
    mana(s, C=1)
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=ability_index(s, s.state.cards[source.id], 'You may cast'), x_value=1)
    settle(s)
    assert s.state.cards[spells[0]].zone == 'p1:exile' and not s.state.zones['stack']
    assert s.state.rules.free_cast_then is None
    roundtrip(s)


def test_source_control_change_uses_saved_activating_controller_with_old_links(cards):
    s, source, spells = rod(cards, ('Lightning Bolt',))
    act(s, 'p1', type='set_controller', card_ids=[source.id], player='p2')
    activate_rod(s, source, 1, 'p2')
    assert s.state.rules.decision.player == 'p2'
    pick(s, spells[0])
    choose(s, ['p3'])
    assert s.state.cards[spells[0]].controller == 'p2'
    settle(s)
    assert s.state.cards[spells[0]].zone == 'p1:graveyard'
    assert s.state.players['p3'].life == 37
    roundtrip(s)


def test_rod_cancel_retries_with_same_budget_and_no_cast_charged(cards):
    s, source, spells = rod(cards)
    activate_rod(s, source, 2)
    pick(s, spells[1])
    choose(s, ['cancel'])
    d = s.state.rules.decision
    assert d.resume['step'] == 'free_cast_pick' and d.resume['ctx']['free_cast_budget'] == 2
    assert not d.resume['ctx']['free_cast_done']
    pick(s, spells[0])
    assert s.state.rules.decision.resume['ctx']['free_cast_budget'] == 1
    choose(s, [])
    settle(s)
    assert s.state.cards[spells[1]].zone == 'p1:exile'
    assert s.state.cards[spells[0]].zone == 'p1:graveyard'
    roundtrip(s)


def test_countered_spell_is_not_captured_by_rod(cards):
    s, source, _ = rod(cards, (), extra=('Lightning Bolt', 'Counterspell'))
    bolt = own(s, 'Lightning Bolt')
    counter = own(s, 'Counterspell')
    mana(s, R=1, U=2)
    act(s, 'p1', type='cast_spell', card_id=bolt, targets=['p2'])
    act(s, 'p1', type='cast_spell', card_id=counter, targets=[bolt])
    settle(s)
    assert s.state.cards[bolt].zone == 'p1:graveyard'
    assert s.state.cards[counter].zone == 'p1:exile'
    assert s.state.rules.exiled_with[s.state.rules.object_id(source.id)] == [s.state.rules.object_id(counter)]
    roundtrip(s)


def test_rod_spell_cast_prohibition_leaves_linked_cards_exiled(cards):
    from tests.test_rules_wave7b_activation import ability_index

    s, source, spells = rod(cards, ('Opt',), extra=('Rule of Law',))
    put(s, 'Rule of Law', 'battlefield')
    mana(s, C=1)
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=ability_index(s, s.state.cards[source.id], 'You may cast'), x_value=1)
    settle(s)
    assert s.state.cards[spells[0]].zone == 'p1:exile'
    assert s.state.rules.free_cast_then is None and not s.state.rules.free_casts
    roundtrip(s)


@pytest.mark.parametrize('stage', ['first_target', 'second_choice'])
def test_cold_budget_continuation_preserves_actual_spent_value_and_cleanup(cards, tmp_path, stage):
    import subprocess
    import sys

    s, source, spells = invoke(cards, ('Cancel', 'Cancel', 'Concentrate'))
    pick(s, spells[0])
    if stage == 'second_choice':
        choose(s, [source])
        assert s.state.rules.decision.resume['ctx']['free_cast_budget'] == 3
    saved = tmp_path / f'budget-{stage}.json'
    saved.write_text(s.state.model_dump_json())
    script = r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
saved, db, source, first, second, over = sys.argv[1:]
repo=CardRepository(Path(db),ImageStore(Path(db).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(saved).read_text()),cards=repo)
def choose(ids):
    d=s.state.rules.decision
    s.perform(d.player,{'type':'choose','decision_id':d.id,'option_ids':ids})
if s.state.rules.decision.resume['step']=='cast_target':
    choose([source])
d=s.state.rules.decision
assert d.resume['step']=='free_cast_pick'
assert d.resume['ctx']['free_cast_budget']==3
assert over not in {o.card_id for o in d.options}
choose([next(o.id for o in d.options if o.card_id==second)])
choose([first])
assert s.state.rules.decision is None and s.state.cards[source].zone=='p1:exile'
assert s.state.zones['stack']==[first,second]
for _ in range(80):
    if not s.state.zones.get('stack'):break
    s.perform(s.state.rules.priority,{'type':'pass_priority'})
else:raise AssertionError('did not settle')
assert all(s.state.cards[c].zone=='p1:exile' for c in [source,first,second])
assert s.state.cards[over].zone=='p1:hand'
assert s.state.rules.free_cast_then is None and not s.state.rules.free_casts
assert s.history.rebuild().model_dump(mode='json')==s.state.model_dump(mode='json')
repo.close()
'''
    result = subprocess.run([sys.executable, '-c', script, str(saved), str(cards.db_path), source, *spells],
                            cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr


def test_chosen_feather_rider_survives_token_source_leaving_and_ceasing(cards):
    from tests.test_rules_conditionals import until

    s = table(cards, [ROD, 'Grizzly Bears', 'Shelter'], ['Feather, the Redeemed'], [])
    act(s, 'p1', type='set_prefs', hold_priority=True)
    put(s, ROD, 'battlefield')
    original = put(s, 'Feather, the Redeemed', 'battlefield', 'p2')
    act(s, 'p1', type='copy_card', card_id=original.id)
    token = next(c for c in s.state.cards.values() if c.name == 'Feather, the Redeemed' and c.is_token)
    bear = put(s, 'Grizzly Bears', 'battlefield')
    shelter = own(s, 'Shelter')
    mana(s, C=1, W=1)
    act(s, 'p1', type='cast_spell', card_id=shelter, targets=[bear.id])
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.resume['step'] == 'zone_replace_order')
    option = next(o.id for o in s.state.rules.decision.options if o.card_id == token.id)
    act(s, 'p1', type='move', card_ids=[token.id], to={'player': 'p1', 'zone': 'graveyard'})
    assert token.id not in s.state.cards
    choose(s, [option])
    assert len(s.state.rules.delayed) == 1 and not s.state.rules.exiled_with
    to_phase(s, 'end', turn=1)
    settle(s)
    assert s.state.cards[shelter].zone == 'p1:hand'
    assert not s.state.rules.delayed
    roundtrip(s)

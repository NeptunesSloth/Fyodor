"""Exiled-card permissions retain their exact beneficiary, object, costs and duration."""
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
from tests.game_helpers import act, mana_pool
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_player_protection import answer, priority
from tests.test_rules_source_quality_protection import ch, spell
from tests.test_rules_wave7b_activation import ability_index
from tests.test_rules_wave30m_durations import stops, three, to_phase
from tests.test_rules_wave31d_spell_copies import hold

DATA = Path(__file__).parent / 'fixtures/exile_permission_sequence_cards.json'
NAMES = [c['name'] for c in json.loads(DATA.read_text())][:14]


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads(DATA.read_text())):
        base[c['name']] = card(c['name'], set_code='eps', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards):
    names = [c['name'] for c in json.loads(DATA.read_text())] + ['Grizzly Bears', 'Sol Ring', 'Lightning Bolt', 'Forest', 'Giant Spider']
    s = three(cards, names, names, names)
    hold(s)
    return s


def top(s, name, player='p1'):
    c = put(s, name, 'library', player)
    act(s, 'p1', type='move', card_ids=[c.id], to={'player': player, 'zone': 'library'}, position='top')
    return c


def activate(s, source, needle, mana=None):
    priority(s, 'p1')
    if mana:
        act(s, 'p1', type='add_mana', player='p1', mana=mana)
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=ability_index(s, source, needle))
    settle(s)


def upkeep(s):
    stops(s, 'upkeep', 'main1')
    to_phase(s, 'upkeep', turn=4)
    settle(s)


def attack(s, source):
    put(s, 'Fervor', 'battlefield')
    stops(s, 'declare_attackers', 'main2')
    to_phase(s, 'declare_attackers')
    act(s, 'p1', type='declare_attackers', attackers=[{'card_id': source.id, 'target': 'p2'}])
    settle(s)


@pytest.mark.parametrize('name', NAMES)
def test_actual_canonical_fourteen_full(cards, name):
    result = coverage.of_card_data(cards.resolve(name))
    assert result.level == 'FULL', result.manual_parts


@pytest.mark.parametrize('owner,tax', [('p1', 0), ('p2', 2)])
def test_soul_partition_grants_owner_play_with_opponent_only_tax(cards, owner, tax):
    s = setup(cards)
    bear = put(s, 'Grizzly Bears', 'battlefield', owner)
    spell(s, 'Soul Partition', {'W': 1, 'C': 1}, [bear.id])
    p = next(p for p in s.state.rules.permissions if p.card == bear.id)
    assert p.player == owner and p.play and p.generic_extra == tax and p.until == 'permanent'
    assert s.state.cards[bear.id].zone == f'{owner}:exile'
    roundtrip(s)


def test_suspend_aggression_two_actual_objects_owners_get_distinct_turn_clocks(cards):
    s = setup(cards)
    bear = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    own = top(s, 'Sol Ring')
    spell(s, 'Suspend Aggression', {'R': 1, 'W': 1, 'C': 1}, [bear.id])
    grants = {p.card: p for p in s.state.rules.permissions}
    assert grants[bear.id].player == 'p2' and grants[own.id].player == 'p1'
    assert grants[bear.id].until == grants[own.id].until == 'end_of_next_turn'
    roundtrip(s)


def test_author_exiles_opponents_graveyards_then_selects_only_nonland(cards):
    s = setup(cards)
    bear = put(s, 'Grizzly Bears', 'graveyard', 'p2')
    land = put(s, 'Forest', 'graveyard', 'p3')
    ours = put(s, 'Sol Ring', 'graveyard')
    spell(s, 'Author of Shadows', {'B': 1, 'C': 4})
    d = s.state.rules.decision
    assert d is not None and {o.id for o in d.options} == {bear.id}
    answer(s, [bear.id])
    p = next(p for p in s.state.rules.permissions if p.card == bear.id)
    assert p.player == 'p1' and p.cast and not p.play and p.spend == 'color'
    assert s.state.cards[land.id].zone == 'p3:exile' and s.state.cards[ours.id].zone == 'p1:graveyard'
    roundtrip(s)


def test_chandra_mana_then_selects_only_one_actual_exiled_card(cards):
    s = setup(cards)
    source = spell(s, 'Chandra, Flameshaper', {'R': 2, 'C': 5})
    top(s, 'Sol Ring')
    before = list(s.state.zones['p1:library'])[:3]
    activate(s, source, 'Add {R}{R}{R}')
    d = s.state.rules.decision
    assert d is not None and {o.id for o in d.options} == set(before)
    assert mana_pool(s, 'p1').get('R', 0) == 3
    answer(s, [before[1]])
    assert [p.card for p in s.state.rules.permissions] == [before[1]]
    roundtrip(s)


def test_vivien_must_choose_any_card_face_down_and_retains_private_look(cards):
    s = setup(cards)
    source = spell(s, 'Vivien, Champion of the Wilds', {'G': 1, 'C': 2})
    noncreature = top(s, 'Sol Ring')
    activate(s, source, 'Look at the top three')
    d = s.state.rules.decision
    assert d is not None and d.min_choices == 1 and noncreature.id in {o.id for o in d.options}
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[noncreature.id])
    d = s.state.rules.decision
    assert d is not None and d.kind == 'order'
    answer(s, [o.id for o in reversed(d.options)])
    assert s.state.cards[noncreature.id].face_down
    from app.game.visibility import can_see
    assert can_see(s.state, s.state.cards[noncreature.id], 'p1')
    assert not can_see(s.state, s.state.cards[noncreature.id], 'p2')
    p = next(p for p in s.state.rules.permissions if p.card == noncreature.id)
    assert p.cast and not p.play and p.filter
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'exile'})
    assert can_see(s.state, s.state.cards[noncreature.id], 'p1')
    roundtrip(s)


def test_nahiri_equipped_attacker_grants_paid_play_and_free_equipment_spell(cards):
    s = setup(cards)
    put(s, 'Nahiri, Forged in Fury', 'battlefield')
    host = put(s, 'Grizzly Bears', 'battlefield')
    equipment = put(s, 'Shadowspear', 'battlefield')
    act(s, 'p1', type='attach', card_ids=[equipment.id], to=host.id)
    exiled = top(s, 'Sol Ring')
    attack(s, host)
    grants = [p for p in s.state.rules.permissions if p.card == exiled.id]
    assert len(grants) == 2 and sum(p.free for p in grants) == 1
    assert next(p for p in grants if p.free).filter and not next(p for p in grants if p.free).play
    assert next(p for p in grants if not p.free).play
    roundtrip(s)


def test_riveteers_first_mode_opponent_chooses_maximum_creature_or_planeswalker(cards):
    s = setup(cards)
    small = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    big = put(s, 'Giant Spider', 'battlefield', 'p2')
    equal = put(s, 'Rashmi and Ragavan', 'battlefield', 'p2')
    spell(s, 'Riveteers Charm', {'B': 1, 'R': 1, 'G': 1}, ['p2'], modes=[0])
    d = s.state.rules.decision
    assert d is not None and d.player == 'p2' and {o.id for o in d.options} == {big.id, equal.id}
    answer(s, [big.id])
    assert s.state.cards[small.id].zone == 'p2:battlefield' and s.state.cards[big.id].zone == 'p2:graveyard'
    roundtrip(s)


def test_shadow_urchin_counts_total_counters_on_dead_object(cards):
    s = setup(cards)
    put(s, 'Shadow Urchin', 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    act(s, 'p1', type='set_counter', card_id=bear.id, kind='charge', value=2)
    act(s, 'p1', type='set_counter', card_id=bear.id, kind='storage', value=1)
    before = list(s.state.zones['p1:library'])[:3]
    spell(s, 'Lightning Bolt', {'R': 1}, [bear.id], player='p2')
    assert all(s.state.cards[c].zone == 'p1:exile' for c in before)
    assert {p.card for p in s.state.rules.permissions} == set(before)
    roundtrip(s)


def test_tavern_brawler_commander_trigger_freezes_exiled_card_mana_value(cards):
    s = setup(cards)
    put(s, 'Tavern Brawler', 'battlefield')
    commander = put(s, 'Krenko, Mob Boss', 'battlefield')
    exiled = top(s, 'Sol Ring')
    upkeep(s)
    assert ch(s, commander).pt == (4, 3)
    assert any(p.card == exiled.id and p.player == 'p1' for p in s.state.rules.permissions)
    roundtrip(s)


def test_redcap_optional_sacrifice_gates_counter_exile_and_play_permission(cards):
    s = setup(cards)
    source = put(s, 'Redcap Gutter-Dweller', 'battlefield')
    sacrifice = put(s, 'Grizzly Bears', 'battlefield')
    put(s, 'Ornithopter', 'battlefield')
    exiled = top(s, 'Sol Ring')
    upkeep(s)
    answer(s, ['pay'])
    answer(s, [sacrifice.id])
    assert s.state.cards[sacrifice.id].zone == 'p1:graveyard'
    assert s.state.cards[source.id].counters.get('+1/+1') == 1
    assert any(p.card == exiled.id for p in s.state.rules.permissions)
    roundtrip(s)


@pytest.mark.parametrize('accept', [False, True])
def test_synth_optional_energy_acceptance_controls_card_permission(cards, accept):
    s = setup(cards)
    source = put(s, 'Synth Eradicator', 'battlefield')
    exiled = top(s, 'Sol Ring')
    attack(s, source)
    d = s.state.rules.decision
    assert d is not None and d.resume['step'] == 'permission_optional_energy'
    answer(s, ['yes' if accept else 'no'])
    assert bool([p for p in s.state.rules.permissions if p.card == exiled.id]) is not accept
    assert s.state.players['p1'].resources.get('energy', 0) == (2 if accept else 0)
    roundtrip(s)


def test_ardent_optional_graveyard_bottom_then_two_exile_grants(cards):
    s = setup(cards)
    source = put(s, 'Ardent Dustspeaker', 'battlefield')
    payment = put(s, 'Lightning Bolt', 'graveyard')
    before = list(s.state.zones['p1:library'])[:2]
    attack(s, source)
    answer(s, [payment.id])
    assert s.state.zones['p1:library'][-1] == payment.id
    assert {p.card for p in s.state.rules.permissions} == set(before)
    roundtrip(s)


def test_court_paid_card_permission_and_monarch_one_free_linked_grant(cards):
    s = setup(cards)
    source = put(s, 'Court of Locthwain', 'battlefield')
    act(s, 'p1', type='set_monarch', player='p1')
    upkeep(s)
    exiled = top(s, 'Grizzly Bears', 'p2')
    answer(s, ['p2'])
    grants = [p for p in s.state.rules.permissions if p.card == exiled.id]
    assert len(grants) == 2 and next(p for p in grants if p.free).left == 1
    assert next(p for p in grants if not p.free).spend == 'type'
    assert source.id in s.state.cards
    roundtrip(s)


def test_rashmi_first_spell_creates_treasure_before_native_free_cast_threshold(cards):
    s = setup(cards)
    put(s, 'Rashmi and Ragavan', 'battlefield')
    put(s, 'Sol Ring', 'battlefield')
    bolt = top(s, 'Lightning Bolt', 'p2')
    spell(s, 'Grizzly Bears', {'G': 1, 'C': 1})
    answer(s, ['p2'])
    d = s.state.rules.decision
    assert d is not None and any(o.card_id == bolt.id for o in d.options)
    answer(s, [next(o.id for o in d.options if o.card_id == bolt.id)])
    answer(s, ['p3'])
    assert s.state.players['p3'].life == 37
    assert not any(p.card == bolt.id for p in s.state.rules.permissions)
    roundtrip(s)


def test_synth_accepted_energy_replaced_to_zero_does_not_grant_play(cards):
    s = setup(cards)
    source = put(s, 'Synth Eradicator', 'battlefield')
    put(s, 'Vorinclex, Monstrous Raider', 'battlefield', 'p2')
    put(s, 'Vorinclex, Monstrous Raider', 'battlefield', 'p3')
    exiled = top(s, 'Sol Ring')
    attack(s, source)
    answer(s, ['yes'])
    for _ in range(4):
        d = s.state.rules.decision
        if d is None:
            break
        assert d.player == 'p1' and 'counter' in d.resume['step']
        answer(s, [d.options[0].id])
    assert s.state.players['p1'].resources.get('energy', 0) == 0
    assert not any(p.card == exiled.id for p in s.state.rules.permissions)
    roundtrip(s)


def test_shadow_urchin_counts_pre_sba_opposing_counters_on_dying_creature(cards):
    s = setup(cards)
    put(s, 'Shadow Urchin', 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    act(s, 'p1', type='set_counter', card_id=bear.id, kind='+1/+1', value=1)
    before = list(s.state.zones['p1:library'])[:4]
    act(s, 'p1', type='set_counter', card_id=bear.id, kind='-1/-1', value=3)
    act(s, s.state.rules.priority, type='pass_priority')
    settle(s)
    assert s.state.cards[bear.id].zone == 'p1:graveyard'
    assert {p.card for p in s.state.rules.permissions} == set(before)
    roundtrip(s)


@pytest.mark.parametrize('kind', ['energy', 'bottom', 'private_pick'])
def test_permission_sequence_new_decisions_resume_in_fresh_process(cards, tmp_path, kind):
    import subprocess
    import sys

    from app.game.visibility import can_see

    s = setup(cards)
    if kind == 'private_pick':
        source = spell(s, 'Vivien, Champion of the Wilds', {'G': 1, 'C': 2})
        selected = top(s, 'Sol Ring')
        activate(s, source, 'Look at the top three')
    elif kind == 'bottom':
        source = put(s, 'Ardent Dustspeaker', 'battlefield')
        selected = put(s, 'Lightning Bolt', 'graveyard')
        attack(s, source)
    else:
        source = put(s, 'Synth Eradicator', 'battlefield')
        selected = top(s, 'Sol Ring')
        attack(s, source)
    d = s.state.rules.decision
    assert d is not None
    assert kind != 'private_pick' or not can_see(s.state, s.state.cards[selected.id], 'p2')
    path = tmp_path / f'{kind}.json'
    path.write_text(s.state.model_dump_json())
    code = r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.game.session import GameSession
from app.game.state import GameState
from app.game.visibility import can_see
path, database, selected, kind = sys.argv[1:]
repo = CardRepository(Path(database), ImageStore(Path(database).parent / 'images'))
s = GameSession(GameState.model_validate_json(Path(path).read_text()), cards=repo)
s.view('p2')
printing = s.state.cards[selected].card_id
d = s.state.rules.decision
assert d is not None
s.perform(d.player, {'type': 'choose', 'decision_id': d.id, 'option_ids': ['yes' if kind == 'energy' else selected]})
for _ in range(20):
    d = s.state.rules.decision
    if d is not None:
        assert d.kind == 'order'
        s.perform(d.player, {'type': 'choose', 'decision_id': d.id, 'option_ids': [o.id for o in reversed(d.options)]})
    elif s.state.zones.get('stack'):
        s.perform(s.state.rules.priority, {'type': 'pass_priority'})
    else:
        break
else:
    raise AssertionError('sequence did not resolve')
if kind == 'energy':
    assert s.state.players['p1'].resources.get('energy', 0) == 2
    assert not any(p.card == selected for p in s.state.rules.permissions)
elif kind == 'bottom':
    assert s.state.zones['p1:library'][-1] == selected
    assert len(s.state.rules.permissions) == 2
else:
    selected = next(p.card for p in s.state.rules.permissions if p.filter and s.state.cards[p.card].card_id == printing)
    assert s.state.cards[selected].face_down and can_see(s.state, s.state.cards[selected], 'p1')
    assert not can_see(s.state, s.state.cards[selected], 'p2')
    assert any(p.card == selected and p.filter for p in s.state.rules.permissions)
assert s.history.rebuild() == s.state
assert GameState.model_validate_json(s.state.model_dump_json()) == s.state
repo.close()
'''
    result = subprocess.run([sys.executable, '-c', code, str(path), str(cards.db_path), selected.id, kind],
                            capture_output=True, text=True, cwd=Path(__file__).resolve().parents[1], timeout=60)
    assert result.returncode == 0, result.stderr


def test_vivien_exiled_creature_casts_after_vivien_leaves(cards):
    s = setup(cards)
    source = spell(s, 'Vivien, Champion of the Wilds', {'G': 1, 'C': 2})
    bear = top(s, 'Grizzly Bears')
    activate(s, source, 'Look at the top three')
    answer(s, [bear.id])
    selected = next(p.card for p in s.state.rules.permissions if p.filter)
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'exile'})
    priority(s, 'p1')
    act(s, 'p1', type='add_mana', player='p1', mana={'G': 1, 'C': 1})
    act(s, 'p1', type='cast_spell', card_id=selected)
    settle(s)
    assert s.state.cards[selected].zone == 'p1:battlefield' and not s.state.cards[selected].face_down
    roundtrip(s)


def test_nahiri_actual_free_equipment_cast_after_attack(cards):
    s = setup(cards)
    put(s, 'Nahiri, Forged in Fury', 'battlefield')
    host = put(s, 'Grizzly Bears', 'battlefield')
    attached = put(s, 'Shadowspear', 'battlefield', 'p2')
    act(s, 'p2', type='attach', card_ids=[attached.id], to=host.id)
    equipment = top(s, 'Shadowspear')
    attack(s, host)
    to_phase(s, 'main2')
    priority(s, 'p1')
    act(s, 'p1', type='cast_spell', card_id=equipment.id, free=True)
    settle(s)
    assert s.state.cards[equipment.id].zone == 'p1:battlefield'
    assert not any(mana_pool(s, 'p1').values())
    roundtrip(s)


def test_court_one_free_permission_group_spans_prior_and_new_exiles(cards):
    from app.rules import permissions
    from app.rules.plan import Plan

    s = setup(cards)
    put(s, 'Court of Locthwain', 'battlefield')
    act(s, 'p1', type='set_monarch', player='p1')
    upkeep(s)
    first = top(s, 'Sol Ring', 'p2')
    answer(s, ['p2'])
    to_phase(s, 'upkeep', turn=7)
    settle(s)
    second = top(s, 'Shadowspear', 'p2')
    answer(s, ['p2'])
    free = [p for p in s.state.rules.permissions if p.free]
    assert {p.card for p in free} == {first.id, second.id}
    assert len({p.group for p in free}) == 1 and all(p.left == 1 for p in free)
    to_phase(s, 'main1', turn=7)
    priority(s, 'p1')
    act(s, 'p1', type='cast_spell', card_id=first.id, free=True)
    settle(s)
    assert s.state.cards[first.id].zone == 'p1:battlefield'
    plan = Plan(s.state, 'p1', cards, None)
    assert not any(g.free for g in permissions.grants(s.state, 'p1', s.state.cards[second.id], plan.ch(s.state.cards[second.id]), cards))
    roundtrip(s)


def test_vivien_noncreature_cannot_be_cast_with_her_filtered_permission(cards):
    s = setup(cards)
    source = spell(s, 'Vivien, Champion of the Wilds', {'G': 1, 'C': 2})
    ring = top(s, 'Sol Ring')
    activate(s, source, 'Look at the top three')
    answer(s, [ring.id])
    selected = next(p.card for p in s.state.rules.permissions if p.filter)
    priority(s, 'p1')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 1})
    with pytest.raises(ActionError, match="cast|permission|zone"):
        act(s, 'p1', type='cast_spell', card_id=selected)
    assert s.state.cards[selected].zone == 'p1:exile'
    roundtrip(s)


def test_rashmi_strict_equal_threshold_falls_back_to_real_paid_cast(cards):
    s = setup(cards)
    put(s, 'Rashmi and Ragavan', 'battlefield')
    bolt = top(s, 'Lightning Bolt', 'p2')
    spell(s, 'Grizzly Bears', {'G': 1, 'C': 1})
    answer(s, ['p2'])
    assert s.state.rules.decision is None
    p = next(p for p in s.state.rules.permissions if p.card == bolt.id)
    assert p.player == 'p1' and not p.free and p.cast and not p.play
    priority(s, 'p1')
    act(s, 'p1', type='add_mana', player='p1', mana={'R': 1})
    act(s, 'p1', type='cast_spell', card_id=bolt.id, targets=['p3'])
    settle(s)
    assert s.state.players['p3'].life == 37 and s.state.cards[bolt.id].zone == 'p2:graveyard'
    roundtrip(s)


def test_redcap_decline_does_not_exile_or_put_counter(cards):
    s = setup(cards)
    source = put(s, 'Redcap Gutter-Dweller', 'battlefield')
    put(s, 'Grizzly Bears', 'battlefield')
    upkeep(s)
    before = list(s.state.zones['p1:library'])
    answer(s, ['decline'])
    assert s.state.zones['p1:library'] == before
    assert not s.state.cards[source.id].counters.get('+1/+1')
    assert not s.state.rules.permissions
    roundtrip(s)


def test_suspend_aggression_illegal_only_target_does_not_exile_own_top(cards):
    s = setup(cards)
    target = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    own = top(s, 'Sol Ring')
    spell(s, 'Suspend Aggression', {'R': 1, 'W': 1, 'C': 1}, [target.id], finish=False)
    act(s, 'p1', type='move', card_ids=[target.id], to={'player': 'p2', 'zone': 'hand'})
    settle(s)
    assert s.state.cards[own.id].zone == 'p1:library'
    assert not s.state.rules.permissions
    roundtrip(s)


def test_riveteers_impulse_mode_grants_all_three_until_next_end_step(cards):
    s = setup(cards)
    put(s, 'Riveteers Charm', 'hand')
    before = list(s.state.zones['p1:library'])[:3]
    spell(s, 'Riveteers Charm', {'B': 1, 'R': 1, 'G': 1}, modes=[1])
    assert {p.card for p in s.state.rules.permissions} == set(before)
    assert all(p.until == 'next_end_step' for p in s.state.rules.permissions)
    roundtrip(s)


def test_riveteers_graveyard_mode_exiles_only_target_players_zone(cards):
    s = setup(cards)
    enemy = put(s, 'Grizzly Bears', 'graveyard', 'p2')
    ours = put(s, 'Sol Ring', 'graveyard')
    spell(s, 'Riveteers Charm', {'B': 1, 'R': 1, 'G': 1}, ['p2'], modes=[2])
    assert s.state.cards[enemy.id].zone == 'p2:exile' and s.state.cards[ours.id].zone == 'p1:graveyard'
    roundtrip(s)


def test_counter_count_pronoun_requires_counter_qualified_death_antecedent():
    from app.rules import scripts
    from tests.test_rules_scripts import ch as make_characteristics

    # Grammar refusal, deliberately not a fixture or a claimed canonical card.
    text = 'Whenever a creature you control dies, exile that many cards from the top of your library. Until your next end step, you may play those cards.'
    definition = scripts.definitions(make_characteristics('Ambiguous count grammar', 'Enchantment', text))
    assert not definition

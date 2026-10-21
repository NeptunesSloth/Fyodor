"""A named player's zones remain distinct from the spell's chooser/controller."""
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
from tests.test_rules_source_quality_protection import spell
from tests.test_rules_wave7b_activation import ability_index
from tests.test_rules_wave30m_durations import stops, three, to_phase
from tests.test_rules_wave31d_spell_copies import hold

DATA = Path(__file__).parent / 'fixtures/foreign_player_zone_cards.json'
NAMES = [c['name'] for c in json.loads(DATA.read_text())][:13]


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads(DATA.read_text())):
        base[c['name']] = card(c['name'], set_code='fpz', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards):
    names = NAMES + ['Grizzly Bears', 'Grizzly Bears', 'Sol Ring', 'Fervor', 'Think Twice', 'Swamp', 'Lightning Bolt', 'Forest', 'Leyline of Sanctity', 'Tangled Florahedron // Tangled Vale', 'Rest in Peace']
    s = three(cards, names, names, names)
    hold(s)
    return s


@pytest.mark.parametrize('name', NAMES[:3] + NAMES[4:7] + NAMES[8:11])
def test_canonical_first_layer_full(cards, name):
    result = coverage.of_card_data(cards.resolve(name))
    assert result.level == 'FULL', result.manual_parts


def test_quiet_speculation_searches_other_library_into_other_graveyard(cards):
    s = setup(cards)
    flashback = put(s, 'Think Twice', 'library', 'p2')
    own_before = list(s.state.zones['p1:library'])
    source = spell(s, 'Quiet Speculation', {'U': 1, 'C': 1}, ['p2'])
    d = s.state.rules.decision
    assert d is not None and d.player == 'p1'
    assert flashback.id in {o.id for o in d.options}
    assert all(o.label == 'Think Twice' for o in d.options)
    answer(s, [flashback.id])
    assert s.state.cards[flashback.id].zone == 'p2:graveyard'
    assert s.state.zones['p1:library'] == own_before
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    roundtrip(s)


def test_spoils_foreign_union_count_once_and_one_gain(cards):
    s = setup(cards)
    put(s, 'Grizzly Bears', 'graveyard', 'p2')
    put(s, 'Sol Ring', 'graveyard', 'p2')
    put(s, 'Forest', 'graveyard', 'p2')
    put(s, 'Grizzly Bears', 'graveyard', 'p3')
    spell(s, 'Spoils of Evil', {'B': 1, 'C': 2}, ['p2'])
    assert mana_pool(s, 'p1').get('C', 0) == 2
    assert s.state.players['p1'].life == 42
    roundtrip(s)


def test_guiding_spirit_reads_current_graveyard_top_not_any_creature(cards):
    s = setup(cards)
    spirit = put(s, 'Guiding Spirit', 'battlefield')
    put(s, 'Fervor', 'battlefield')
    bear = put(s, 'Grizzly Bears', 'graveyard', 'p2')
    priority(s, 'p1')
    act(s, 'p1', type='activate_ability', card_id=spirit.id, ability=ability_index(s, spirit, 'top card'), targets=['p2'])
    settle(s)
    assert s.state.cards[bear.id].zone == 'p2:library' and s.state.zones['p2:library'][0] == bear.id
    roundtrip(s)


def test_nightmare_incursion_uses_own_swamps_and_target_library(cards):
    s = setup(cards)
    put(s, 'Swamp', 'battlefield')
    put(s, 'Swamp', 'battlefield', 'p2')
    victim = put(s, 'Grizzly Bears', 'library', 'p2')
    put(s, 'Nightmare Incursion', 'hand')
    before = list(s.state.zones['p1:library'])
    spell(s, 'Nightmare Incursion', {'B': 1, 'C': 5}, ['p2'])
    d = s.state.rules.decision
    assert d is not None and d.min_choices == 0 and d.max_choices == 1
    answer(s, [victim.id])
    assert s.state.cards[victim.id].zone == 'p2:exile'
    assert s.state.zones['p1:library'] == before
    roundtrip(s)


def test_suffer_the_past_targets_player_and_that_players_cards(cards):
    s = setup(cards)
    bear = put(s, 'Grizzly Bears', 'graveyard', 'p2')
    spell(s, 'Suffer the Past', {'B': 1, 'C': 1}, ['p2', bear.id], x_value=1, target_counts=[1, 1])
    assert s.state.cards[bear.id].zone == 'p2:exile'
    assert s.state.players['p2'].life == 39 and s.state.players['p1'].life == 41
    roundtrip(s)


@pytest.mark.parametrize('name', [NAMES[3], NAMES[7], NAMES[11], NAMES[12]])
def test_canonical_remaining_layer_full(cards, name):
    result = coverage.of_card_data(cards.resolve(name))
    assert result.level == 'FULL', result.manual_parts


def test_agonizing_private_choose_then_owner_orders_library(cards):
    s = setup(cards)
    bear = put(s, 'Grizzly Bears', 'hand', 'p2')
    ring = put(s, 'Sol Ring', 'hand', 'p2')
    spell(s, 'Agonizing Memories', {'B': 2, 'C': 2}, ['p2'])
    d = s.state.rules.decision
    assert d is not None and d.player == 'p1' and not s.view('p3')['rules']['decision'].get('options')
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[bear.id, ring.id])
    d = s.state.rules.decision
    assert d is not None and d.player == 'p2', (s.state.cards[bear.id].zone, s.state.cards[ring.id].zone, [x.model_dump() for x in s.state.log[-6:]])
    answer(s, [ring.id, bear.id])
    assert s.state.zones['p2:library'][:2] == [ring.id, bear.id]
    roundtrip(s)


def test_drafna_targets_foreign_artifacts_and_orders_top(cards):
    s = setup(cards)
    ring = put(s, 'Sol Ring', 'graveyard', 'p2')
    spell(s, "Drafna's Restoration", {'U': 1}, ['p2', ring.id], target_counts=[1, 1])
    assert s.state.zones['p2:library'][0] == ring.id
    roundtrip(s)


def test_knowledge_exploitation_search_optional_foreign_library_cast(cards):
    s = setup(cards)
    bolt = put(s, 'Lightning Bolt', 'library', 'p2')
    source = put(s, 'Knowledge Exploitation', 'hand')
    before = list(s.state.zones['p1:library'])
    spell(s, 'Knowledge Exploitation', {'U': 2, 'C': 5}, ['p2'])
    answer(s, [bolt.id])
    d = s.state.rules.decision
    assert d is not None, s.state.log[-3:]
    # The native free-cast card picker then asks native spell targets.
    answer(s, [next(o.id for o in d.options if o.card_id == bolt.id)])
    d = s.state.rules.decision
    assert d is not None
    answer(s, ['p3'])
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    assert s.state.players['p3'].life == 37
    assert s.state.zones['p1:library'] == before
    assert s.state.cards[bolt.id].zone == 'p2:graveyard'
    roundtrip(s)


def test_spellbinder_owner_permission_survives_source_and_charges_two(cards):
    s = setup(cards)
    bear = put(s, 'Grizzly Bears', 'hand', 'p2')
    source = spell(s, 'Elite Spellbinder', {'W': 1, 'C': 2})
    answer(s, ['p2'])
    answer(s, [bear.id])
    assert s.state.cards[bear.id].zone == 'p2:exile'
    p = next(p for p in s.state.rules.permissions if p.card == bear.id)
    assert p.player == 'p2' and p.play and p.cast and p.generic_extra == 2
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'exile'})
    priority(s, 'p2')
    act(s, 'p2', type='add_mana', player='p2', mana={'G': 1, 'C': 3})
    # Main-phase timing still belongs to p2, so inspect native permission now;
    # actual p2 casting is covered after advancing their own turn below.
    from app.rules import permissions
    from app.rules.plan import Plan
    plan = Plan(s.state, 'p2', cards, None)
    assert any(g.generic_extra == 2 for g in permissions.grants(s.state, 'p2', s.state.cards[bear.id], plan.ch(s.state.cards[bear.id]), cards))
    roundtrip(s)


def test_haunting_excludes_basic_lands_and_searches_only_exiled_names(cards):
    s = setup(cards)
    grave = put(s, 'Grizzly Bears', 'graveyard', 'p2')
    basic = put(s, 'Forest', 'graveyard', 'p2')
    copy = next(c for c in s.state.cards.values() if c.name == 'Grizzly Bears' and c.owner == 'p2' and c.id != grave.id)
    act(s, 'p1', type='move', card_ids=[copy.id], to={'player': 'p2', 'zone': 'library'})
    spell(s, 'Haunting Echoes', {'B': 2, 'C': 3}, ['p2'])
    d = s.state.rules.decision
    assert d is not None and copy.id in {o.id for o in d.options}, (d.resume if d else None, [(c.id,c.name,c.zone) for c in s.state.cards.values() if c.name == 'Grizzly Bears'])
    assert d.min_choices == 0
    answer(s, [copy.id])
    assert s.state.cards[grave.id].zone == 'p2:exile' and s.state.cards[basic.id].zone == 'p2:graveyard'
    assert s.state.cards[copy.id].zone.endswith(':exile')
    roundtrip(s)


def test_grinning_totem_mandatory_find_and_next_upkeep_permission(cards):
    s = setup(cards)
    totem = put(s, 'Grinning Totem', 'battlefield')
    bear = put(s, 'Grizzly Bears', 'library', 'p2')
    priority(s, 'p1')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 2})
    act(s, 'p1', type='activate_ability', card_id=totem.id, ability=ability_index(s, totem, 'Search'), targets=['p2'])
    settle(s)
    d = s.state.rules.decision
    assert d is not None and d.min_choices == d.max_choices == 1
    answer(s, [bear.id])
    assert s.state.cards[totem.id].zone == 'p1:graveyard'
    p = next(p for p in s.state.rules.permissions if p.card == bear.id)
    assert p.player == 'p1' and p.until == 'next_upkeep'
    assert s.state.rules.delayed
    roundtrip(s)


def test_cruel_calculations_counts_library_to_graveyard_only_even_after_departure(cards):
    s = setup(cards)
    bear = put(s, 'Grizzly Bears', 'library', 'p2')
    act(s, 'p1', type='move', card_ids=[bear.id], to={'player': 'p2', 'zone': 'graveyard'})
    act(s, 'p1', type='move', card_ids=[bear.id], to={'player': 'p2', 'zone': 'exile'})
    ring = put(s, 'Sol Ring', 'hand', 'p2')
    act(s, 'p1', type='move', card_ids=[ring.id], to={'player': 'p2', 'zone': 'graveyard'})
    put(s, 'Cruel Calculations', 'hand')
    before = len(s.state.zones['p1:library'])
    spell(s, 'Cruel Calculations', {'U': 1, 'C': 2}, ['p2'])
    assert len(s.state.zones['p1:library']) == before - 1
    roundtrip(s)


def test_prisoners_selects_one_of_actual_three_exiled_and_grants_only_that_card(cards):
    s = setup(cards)
    before = list(s.state.zones['p2:library'])[:3]
    spell(s, 'You Find Some Prisoners', {'R': 1, 'C': 1}, ['p2'], modes=[1])
    d = s.state.rules.decision
    assert d is not None and {o.id for o in d.options} == set(before)
    assert all(s.state.cards[c].zone == 'p2:exile' for c in before)
    answer(s, [before[1]])
    granted = [p for p in s.state.rules.permissions if p.card in before]
    assert len(granted) == 1 and granted[0].card == before[1]
    assert granted[0].spend == 'color' and granted[0].until == 'end_of_next_turn'
    roundtrip(s)


def test_suffer_illegal_player_does_not_prevent_legal_cards_or_controller_gain(cards):
    s = setup(cards)
    bear = put(s, 'Grizzly Bears', 'graveyard', 'p2')
    spell(s, 'Suffer the Past', {'B': 1, 'C': 1}, ['p2', bear.id], x_value=1, target_counts=[1, 1], finish=False)
    put(s, 'Leyline of Sanctity', 'battlefield', 'p2')
    settle(s)
    assert s.state.cards[bear.id].zone == 'p2:exile'
    assert s.state.players['p2'].life == 40 and s.state.players['p1'].life == 41
    roundtrip(s)


def test_suffer_zero_x_still_targets_player_and_rejects_other_players_graveyard(cards):
    s = setup(cards)
    wrong = put(s, 'Grizzly Bears', 'graveyard', 'p3')
    with pytest.raises(ActionError, match='legal target|target'):
        spell(s, 'Suffer the Past', {'B': 1, 'C': 1}, ['p2', wrong.id], x_value=1, target_counts=[1, 1])
    spell(s, 'Suffer the Past', {'B': 1}, ['p2'], x_value=0, target_counts=[1, 0])
    assert s.state.players['p1'].life == s.state.players['p2'].life == 40
    roundtrip(s)


def test_grinning_permission_lasts_to_next_upkeep_then_returns(cards):
    s = setup(cards)
    totem = put(s, 'Grinning Totem', 'battlefield')
    bear = put(s, 'Grizzly Bears', 'library', 'p2')
    priority(s, 'p1')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 2})
    act(s, 'p1', type='activate_ability', card_id=totem.id, ability=ability_index(s, totem, 'Search'), targets=['p2'])
    settle(s)
    answer(s, [bear.id])
    stops(s, 'end', 'upkeep', 'main1')
    to_phase(s, 'end', turn=3)
    assert any(p.card == bear.id for p in s.state.rules.permissions)
    to_phase(s, 'upkeep', turn=4)
    assert not any(p.card == bear.id for p in s.state.rules.permissions)
    assert s.state.cards[bear.id].zone == 'p2:exile'
    settle(s)
    assert s.state.cards[bear.id].zone == 'p2:graveyard'
    roundtrip(s)


def bind_spellbinder(s, name):
    target = put(s, name, 'hand', 'p2')
    source = spell(s, 'Elite Spellbinder', {'W': 1, 'C': 2})
    answer(s, ['p2'])
    answer(s, [target.id])
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'exile'})
    stops(s, 'main1')
    to_phase(s, 'main1', turn=2)
    settle(s)
    return s.state.cards[target.id]


def test_spellbinder_actual_owner_cast_pays_printed_cost_plus_two(cards):
    s = setup(cards)
    bear = bind_spellbinder(s, 'Grizzly Bears')
    priority(s, 'p2')
    act(s, 'p2', type='add_mana', player='p2', mana={'G': 1, 'C': 3})
    act(s, 'p2', type='cast_spell', card_id=bear.id)
    settle(s)
    assert s.state.cards[bear.id].zone == 'p2:battlefield'
    assert not any(mana_pool(s, 'p2').values())
    roundtrip(s)


def test_spellbinder_nonland_front_owner_may_play_land_back_without_tax(cards):
    s = setup(cards)
    mdfc = bind_spellbinder(s, 'Tangled Florahedron // Tangled Vale')
    priority(s, 'p2')
    act(s, 'p2', type='play_land', card_id=mdfc.id, face=1)
    assert s.state.cards[mdfc.id].zone == 'p2:battlefield' and s.state.cards[mdfc.id].tapped
    roundtrip(s)


@pytest.mark.parametrize('kind', ['exile_choice', 'owner_permission', 'foreign_library_cast'])
def test_foreign_zone_decisions_resume_in_fresh_process(cards, tmp_path, kind):
    import subprocess
    import sys

    s = setup(cards)
    if kind == 'exile_choice':
        spell(s, 'You Find Some Prisoners', {'R': 1, 'C': 1}, ['p2'], modes=[1])
        d = s.state.rules.decision
        assert d is not None and d.resume['step'] == 'foreign_choose_exiled'
        chosen = d.options[0].id
    elif kind == 'owner_permission':
        chosen = put(s, 'Grizzly Bears', 'hand', 'p2').id
        spell(s, 'Elite Spellbinder', {'W': 1, 'C': 2})
        answer(s, ['p2'])
    else:
        chosen = put(s, 'Lightning Bolt', 'library', 'p2').id
        spell(s, 'Knowledge Exploitation', {'U': 2, 'C': 5}, ['p2'])
    path = tmp_path / f'{kind}.json'
    path.write_text(s.state.model_dump_json())
    code = r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
path, database, chosen, kind = sys.argv[1:]
repo = CardRepository(Path(database), ImageStore(Path(database).parent / 'images'))
s = GameSession(GameState.model_validate_json(Path(path).read_text()), cards=repo)
s.view('p3')
d = s.state.rules.decision
s.perform(d.player, {'type': 'choose', 'decision_id': d.id, 'option_ids': [chosen]})
if kind == 'foreign_library_cast':
    d = s.state.rules.decision
    o = next(o.id for o in d.options if o.card_id == chosen)
    s.perform(d.player, {'type': 'choose', 'decision_id': d.id, 'option_ids': [o]})
    d = s.state.rules.decision
    s.perform(d.player, {'type': 'choose', 'decision_id': d.id, 'option_ids': ['p3']})
for _ in range(20):
    if not s.state.zones.get('stack'):
        break
    assert s.state.rules.decision is None
    s.perform(s.state.rules.priority, {'type': 'pass_priority'})
else:
    raise AssertionError('stack did not resolve')
if kind == 'foreign_library_cast':
    assert s.state.players['p3'].life == 37
    assert s.state.cards[chosen].zone == 'p2:graveyard'
else:
    p = next(p for p in s.state.rules.permissions if p.card == chosen)
    assert p.player == ('p2' if kind == 'owner_permission' else 'p1')
    assert p.generic_extra == (2 if kind == 'owner_permission' else 0)
assert s.history.rebuild() == s.state
assert GameState.model_validate_json(s.state.model_dump_json()) == s.state
repo.close()
'''
    result = subprocess.run([sys.executable, '-c', code, str(path), str(cards.db_path), chosen, kind],
                            capture_output=True, text=True, cwd=Path(__file__).resolve().parents[1], timeout=60)
    assert result.returncode == 0, result.stderr


def test_guiding_spirit_does_not_skip_a_noncreature_top_card(cards):
    s = setup(cards)
    spirit = put(s, 'Guiding Spirit', 'battlefield')
    put(s, 'Fervor', 'battlefield')
    bear = put(s, 'Grizzly Bears', 'graveyard', 'p2')
    ring = put(s, 'Sol Ring', 'graveyard', 'p2')
    priority(s, 'p1')
    act(s, 'p1', type='activate_ability', card_id=spirit.id, ability=ability_index(s, spirit, 'top card'), targets=['p2'])
    settle(s)
    assert s.state.cards[bear.id].zone == s.state.cards[ring.id].zone == 'p2:graveyard'
    roundtrip(s)


def test_haunting_search_may_fail_to_find_all_matching_cards(cards):
    s = setup(cards)
    grave = put(s, 'Grizzly Bears', 'graveyard', 'p2')
    library_printings = sorted(s.state.cards[c].card_id for c in s.state.zones['p2:library'])
    spell(s, 'Haunting Echoes', {'B': 2, 'C': 3}, ['p2'])
    d = s.state.rules.decision
    assert d is not None and d.options and d.min_choices == 0
    answer(s, [])
    assert s.state.cards[grave.id].zone == 'p2:exile'
    assert sorted(s.state.cards[c].card_id for c in s.state.zones['p2:library']) == library_printings
    roundtrip(s)


def test_grinning_actually_cast_foreign_card_does_not_return_it_next_upkeep(cards):
    s = setup(cards)
    totem = put(s, 'Grinning Totem', 'battlefield')
    bear = put(s, 'Grizzly Bears', 'library', 'p2')
    priority(s, 'p1')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 2})
    act(s, 'p1', type='activate_ability', card_id=totem.id, ability=ability_index(s, totem, 'Search'), targets=['p2'])
    settle(s)
    answer(s, [bear.id])
    priority(s, 'p1')
    act(s, 'p1', type='add_mana', player='p1', mana={'G': 1, 'C': 1})
    act(s, 'p1', type='cast_spell', card_id=bear.id)
    settle(s)
    assert s.state.cards[bear.id].zone == 'p1:battlefield'
    stops(s, 'upkeep', 'main1')
    to_phase(s, 'upkeep', turn=4)
    settle(s)
    assert s.state.cards[bear.id].zone == 'p1:battlefield'
    roundtrip(s)

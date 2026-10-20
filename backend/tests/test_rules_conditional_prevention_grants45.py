"""Exact compound prevention and grant statics through native production consumers."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import conditional_prevention_grants45 as leaf
from app.rules import coverage, layers, replace
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_damage_redirection import attack, cast, damage
from tests.test_rules_designations import put, settle
from tests.test_rules_prevention_unpreventable44 import DATA as BASE_DATA
from tests.test_rules_prevention_unpreventable44 import NAMES as BASE_NAMES
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave6c_tokens_pumps import chars
from tests.test_rules_wave30m_durations import to_phase

DATA = [*BASE_DATA, *json.loads((Path(__file__).parent / 'fixtures/conditional_prevention_grants45_cards.json').read_text())]
for filename, name in [('static_type_forms38_cards.json', 'Enchanted Evening'), ('layer_dependency_graph42_cards.json', 'Fervor'), ('defender_relative36_cards.json', 'Clever Concealment'), ('named_artifact_count_cards.json', 'Copy Enchantment'), ('layer_dependency_graph42_cards.json', 'Stifle')]:
    DATA.append(next(r for r in json.loads((Path(__file__).parent / 'fixtures' / filename).read_text()) if r['name'] == name))


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, row in enumerate(DATA):
        base[row['name']] = card(row['name'], set_code='p45', number=str(i), **{k: v for k, v in row.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


@pytest.mark.parametrize('factory', [leaf._woolly, leaf._armament])
@pytest.mark.parametrize('change', ['missing', 'empty', 'keyword', 'predicate', 'source'])
def test_full_compound_validator_rejects_any_changed_branch(factory, change):
    d = copy.deepcopy(factory())
    assert leaf.supported(d)
    if change == 'missing':
        del d['also']
    elif change == 'empty':
        d['also'] = []
    elif change == 'keyword':
        d['also'][0]['keywords'] = ['flying']
    elif change == 'predicate':
        d['also'][0]['conditions'] = []
    else:
        d['match']['source'] = {}
    assert not leaf.supported(d) and leaf.layer6_grant(d) is None
    if change != 'missing':
        assert coverage.stage2_supported(d) is False


def test_existing_also_collector_preserves_native_source_controller_timestamp(cards):
    s = table(cards, ['Woolly Razorback', 'Grizzly Bears', 'Forest'])
    holder = cast(s, 'Woolly Razorback')
    p = Plan(s.state, 'p1', cards, None)
    assert s.state.cards[holder.id].counters['ice'] == 3
    candidates = [c for c in replace.static_candidates(p, 'damage') if c.source_card == holder.id]
    assert len(candidates) == 1 and candidates[0].match['combat']
    assert 'defender' in chars(s, holder).keywords
    grant, = (st for st in layers.statics(s.state, p.info) if st.source == holder.id)
    assert grant.controller == holder.controller
    assert grant.seq == layers.timestamp(s.state, holder.id)
    assert grant.definition == leaf.layer6_grant(leaf._woolly())
    native = leaf.layer6_grant(leaf._woolly())
    assert native is not None and native['keywords'] == ['defender']


def game(cards):
    names = [*BASE_NAMES, 'Woolly Razorback', 'Armament of Nyx', 'Enchanted Evening', 'Fervor']
    return table(cards, names, names, names)


@pytest.mark.parametrize('ice', [1, 2, 3])
def test_woolly_actual_block_removes_ice_before_current_combat_damage(cards, ice):
    s = game(cards)
    holder = cast(s, 'Woolly Razorback')
    attacker = put(s, 'Centaur Courser', 'battlefield', 'p2')
    act(s, 'p1', type='counter', card_ids=[holder.id], kind='ice', delta=ice - 3)
    attack(s, [attacker], pid='p2', target='p1', turn=2)
    to_phase(s, 'declare_blockers')
    act(s, 'p1', type='declare_blockers', blocks=[{'blocker_id': holder.id, 'attacker_id': attacker.id}])
    settle(s)
    assert s.state.cards[holder.id].counters.get('ice', 0) == ice - 1
    damage(s)
    assert s.state.cards[holder.id].damage == 3
    assert ('defender' in chars(s, holder).keywords) == (ice > 1)
    assert s.state.cards[attacker.id].zone == ('p2:graveyard' if ice == 1 else 'p2:battlefield')
    if ice > 1:
        assert s.state.cards[attacker.id].damage == 0


@pytest.mark.parametrize('enchantment', [False, True])
def test_armament_actual_aura_source_prevents_or_grants_double_strike(cards, enchantment):
    s = game(cards)
    attacker = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    aura = cast(s, 'Armament of Nyx', [attacker.id])
    if enchantment:
        put(s, 'Enchanted Evening', 'battlefield')
    assert s.state.cards[aura.id].attached_to == attacker.id
    assert ('double strike' in chars(s, attacker).keywords) == enchantment
    p = Plan(s.state, 'p1', cards, None)
    extra, = (st for st in layers.statics(s.state, p.info) if st.source == aura.id)
    assert extra.controller == 'p1' and extra.seq == layers.timestamp(s.state, aura.id)
    assert extra.definition == leaf.layer6_grant(leaf._armament())
    attack(s, [attacker], pid='p2', target='p1', turn=2)
    damage(s)
    if enchantment:
        assert s.state.players['p1'].life == 38
        to_phase(s, 'end_combat')
    assert s.state.players['p1'].life == (36 if enchantment else 40)


def test_armament_source_prevention_survives_enchanted_creature_ability_loss(cards):
    s = game(cards)
    attacker = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    aura = cast(s, 'Armament of Nyx', [attacker.id])
    cast(s, 'Turn to Frog', [attacker.id])
    assert s.state.cards[aura.id].attached_to == attacker.id
    attack(s, [attacker], pid='p2', target='p1', turn=2)
    damage(s)
    assert s.state.players['p1'].life == 40


@pytest.mark.parametrize('change', ['type', 'departure', 'control'])
def test_armament_reads_current_attachment_type_and_source(cards, change):
    s = game(cards)
    attacker = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    aura = cast(s, 'Armament of Nyx', [attacker.id])
    evening = put(s, 'Enchanted Evening', 'battlefield')
    assert 'double strike' in chars(s, attacker).keywords
    if change == 'type':
        act(s, 'p1', type='move', card_ids=[evening.id], to={'player': 'p1', 'zone': 'hand'})
    elif change == 'departure':
        act(s, 'p1', type='move', card_ids=[aura.id], to={'player': 'p1', 'zone': 'hand'})
    else:
        act(s, 'p1', type='set_controller', card_ids=[aura.id], player='p3')
        act(s, 'p1', type='move', card_ids=[evening.id], to={'player': 'p1', 'zone': 'hand'})
    assert 'double strike' not in chars(s, attacker).keywords
    attack(s, [attacker], pid='p2', target='p1', turn=2)
    damage(s)
    assert s.state.players['p1'].life == (38 if change == 'departure' else 40)


def test_woolly_native_ability_loss_removes_both_branches_and_expiry_restores_them(cards):
    from app.rules.combat import attack_problem
    s = game(cards)
    holder = cast(s, 'Woolly Razorback')
    to_phase(s, 'main1', turn=4)
    assert 'defender' in attack_problem(s.state, s.state.cards[holder.id], chars(s, holder)).lower()
    cast(s, 'Turn to Frog', [holder.id], pid='p3')
    assert 'defender' not in chars(s, holder).keywords
    attack(s, [holder], pid='p1', target='p2', turn=4)
    damage(s)
    assert s.state.players['p2'].life == 39
    to_phase(s, 'main1', turn=5)
    assert 'defender' in chars(s, holder).keywords
    p = Plan(s.state, 'p1', cards, None)
    assert any(c.source_card == holder.id for c in replace.static_candidates(p, 'damage'))


def test_armament_current_reattachment_moves_prevention_without_freezing_old_creature(cards):
    s = game(cards)
    first = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    second = put(s, 'Centaur Courser', 'battlefield', 'p2')
    aura = cast(s, 'Armament of Nyx', [first.id])
    act(s, 'p1', type='attach', card_ids=[aura.id], to=second.id)
    attack(s, [first, second], pid='p2', target='p1', turn=2)
    damage(s)
    assert s.state.players['p1'].life == 38


@pytest.mark.parametrize('kind', ['woolly', 'armament'])
def test_compound_prevention_does_not_stop_unpreventable_damage(cards, kind):
    s = game(cards)
    if kind == 'woolly':
        holder = cast(s, 'Woolly Razorback')
        attacker = put(s, 'Centaur Courser', 'battlefield', 'p2')
    else:
        attacker = put(s, 'Grizzly Bears', 'battlefield', 'p2')
        cast(s, 'Armament of Nyx', [attacker.id])
    to_phase(s, 'main1', turn=2)
    cast(s, 'Skullcrack', ['p3'], pid='p2')
    attack(s, [attacker], pid='p2', target='p1', turn=2)
    if kind == 'woolly':
        to_phase(s, 'declare_blockers')
        act(s, 'p1', type='declare_blockers', blocks=[{'blocker_id': holder.id, 'attacker_id': attacker.id}])
        settle(s)
    damage(s)
    if kind == 'woolly':
        assert s.state.cards[attacker.id].zone == 'p2:graveyard'
        assert s.state.cards[holder.id].counters['ice'] == 2
    else:
        assert s.state.players['p1'].life == 38


@pytest.mark.parametrize('kind', ['woolly', 'armament'])
def test_compound_native_cold_rebuilds_same_source_and_current_conditions(cards, tmp_path, kind):
    import subprocess
    import sys
    s = game(cards)
    if kind == 'woolly':
        holder = cast(s, 'Woolly Razorback')
        attacker = put(s, 'Centaur Courser', 'battlefield', 'p2')
        evening = ''
    else:
        attacker = put(s, 'Grizzly Bears', 'battlefield', 'p2')
        holder = cast(s, 'Armament of Nyx', [attacker.id])
        evening = put(s, 'Enchanted Evening', 'battlefield').id
    to_phase(s, 'main1', turn=2)
    saved = tmp_path / 'compound-before-combat.json'
    saved.write_text(s.state.model_dump_json())
    code = r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from app.rules import layers
from app.rules.plan import Plan
from tests.game_helpers import act
from tests.test_rules_damage_redirection import attack,damage
from tests.test_rules_designations import settle,roundtrip
from tests.test_rules_wave30m_durations import to_phase
from tests.test_rules_wave6c_tokens_pumps import chars
saved,db,kind,holder,attacker,evening=sys.argv[1:]
repo=CardRepository(Path(db),ImageStore(Path(db).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(saved).read_text()),cards=repo)
p=Plan(s.state,'p1',repo,None)
st,=(x for x in layers.statics(s.state,p.info) if x.source==holder)
assert st.controller=='p1' and st.seq==layers.timestamp(s.state,holder)
if kind=='armament':
 assert 'double strike' in chars(s,s.state.cards[attacker]).keywords
 act(s,'p1',type='move',card_ids=[evening],to={'player':'p1','zone':'hand'})
 assert 'double strike' not in chars(s,s.state.cards[attacker]).keywords
attack(s,[s.state.cards[attacker]],pid='p2',target='p1',turn=2)
if kind=='woolly':
 to_phase(s,'declare_blockers')
 act(s,'p1',type='declare_blockers',blocks=[{'blocker_id':holder,'attacker_id':attacker}])
 settle(s)
damage(s)
assert s.state.players['p1'].life==40
if kind=='woolly':
 assert s.state.cards[holder].counters['ice']==2 and s.state.cards[holder].damage==3
 assert s.state.cards[attacker].damage==0 and s.state.cards[attacker].zone=='p2:battlefield'
roundtrip(s)
settle(s)
assert s.state.players['p1'].life==40
repo.close()
'''
    result = subprocess.run([sys.executable, '-c', code, str(saved), str(cards.db_path), kind, holder.id, attacker.id, evening],
                            cwd=Path(__file__).parent.parent, capture_output=True, text=True, timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize('name', ['Woolly Razorback', 'Armament of Nyx'])
def test_full_canonical_compound_coverage_requires_both_supported_consumers(cards, name):
    result = coverage.of_card_data(cards.resolve(name))
    assert result.level == 'FULL', result.manual_parts

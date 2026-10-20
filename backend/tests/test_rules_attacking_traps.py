"""Current attackers, rather than attack history, enable Trap alternative costs."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import alt_costs, coverage
from app.rules import characteristics as chars
from app.rules.plan import Plan
from app.rules.sba import power
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_banding import attack_step
from tests.test_rules_bandmate_references import mana, wait_priority
from tests.test_rules_conditionals import settle
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_shared_damage_choices import table

NAMES = ['Nemesis Trap', 'Lethargy Trap', 'Arrow Volley Trap', 'Pitfall Trap', 'Slingbow Trap']


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/attacking_trap_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='atr', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards, name, specs=('G',), nontarget=()):
    s = table(cards, [name, 'Unsummon', 'Counterspell'], [], [])
    act(s, 'p1', type='set_prefs', hold_priority=True)
    spell = put(s, name, 'hand')
    creatures = []
    for i, spec in enumerate((*specs, *nontarget)):
        act(s, 'p1', type='create_token', player='p1', token={
            'name': f'Scout{i}', 'type_line': 'Token Creature — Scout', 'power': '4', 'toughness': '4',
            'colors': [spec[:1]], 'text': 'Haste' + ('\nFlying' if 'f' in spec else '')})
        creatures.append(next(c for c in s.state.cards.values() if c.name == f'Scout{i}'))
    attack_step(s)
    act(s, 'p1', type='declare_attackers', attackers=[{'card_id': c.id, 'target': 'p2' if i % 2 == 0 else 'p3'}
                                                   for i, c in enumerate(creatures[:len(specs)])])
    return s, spell, creatures


def offers(s, spell):
    return alt_costs.offers(s.state, 'p1', spell, chars.of(spell, s.cards), s.cards)


@pytest.mark.parametrize('name', NAMES)
def test_canonical_traps_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


@pytest.mark.parametrize('name,specs,eligible', [
    ('Lethargy Trap', ('G', 'G'), False), ('Lethargy Trap', ('G', 'G', 'G'), True),
    ('Lethargy Trap', ('G',) * 4, True), ('Arrow Volley Trap', ('G',) * 3, False),
    ('Arrow Volley Trap', ('G',) * 4, True), ('Arrow Volley Trap', ('G',) * 5, True),
    ('Pitfall Trap', ('G',), True), ('Pitfall Trap', ('G', 'G'), False),
    ('Nemesis Trap', ('G',), False), ('Nemesis Trap', ('W', 'G'), True),
    ('Slingbow Trap', ('B', 'Gf'), False), ('Slingbow Trap', ('Bf',), True),
])
def test_current_attacking_filters_and_thresholds(cards, name, specs, eligible):
    s, spell, _ = setup(cards, name, specs)
    assert bool(offers(s, spell)) == eligible
    roundtrip(s)


@pytest.mark.parametrize('name,specs,pool', [
    ('Nemesis Trap', ('W', 'G'), {'B': 2}), ('Lethargy Trap', ('G',) * 3, {'U': 1}),
    ('Arrow Volley Trap', ('G',) * 4, {'W': 1, 'C': 1}),
    ('Pitfall Trap', ('G',), {'W': 1}), ('Slingbow Trap', ('Bf', 'Gf'), {'G': 1}),
])
def test_native_alternative_cost_and_actual_effect(cards, name, specs, pool):
    s, spell, creatures = setup(cards, name, specs)
    mana(s, **pool)
    option = offers(s, spell)[0]
    target = creatures[-1]
    args = {'targets': [target.id]} if name != 'Lethargy Trap' else {}
    if name == 'Arrow Volley Trap':
        args = {'targets': [creatures[0].id, target.id], 'target_counts': [2], 'division': [1, 4]}
    act(s, 'p1', type='cast_spell', card_id=spell.id, alt_cost=option.key, **args)
    assert s.state.rules.payments[s.state.rules.object_id(spell.id)].alternative == 'alternative'
    roundtrip(s)
    settle(s)
    if name in ('Pitfall Trap', 'Slingbow Trap'):
        assert target.id not in s.state.cards or not s.state.cards[target.id].zone.endswith(':battlefield')
    elif name == 'Nemesis Trap':
        assert target.id not in s.state.cards or not s.state.cards[target.id].zone.endswith(':battlefield')
        assert any(c.name == target.name and c.id != target.id and c.zone.endswith(':battlefield') for c in s.state.cards.values())
    elif name == 'Lethargy Trap':
        assert all(power(s.state.cards[c.id], Plan.view(s.state, 'p1', s.cards).ch(s.state.cards[c.id])) == 1
                   for c in creatures)
    else:
        assert s.state.cards[creatures[0].id].damage == 1
        assert target.id not in s.state.cards or not s.state.cards[target.id].zone.endswith(':battlefield')
    roundtrip(s)


def test_ineligible_alternative_cast_is_atomic(cards):
    s, spell, creatures = setup(cards, 'Pitfall Trap', ('G', 'G'))
    mana(s, W=1)
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[creatures[0].id], alt_cost=f'{spell.id}:0')
    assert s.state.model_dump_json() == before


def test_nonattacking_white_creature_does_not_enable_nemesis(cards):
    s, spell, _ = setup(cards, 'Nemesis Trap', ('G',), ('W',))
    assert not offers(s, spell)


def test_condition_changes_when_an_attacker_leaves_before_announcement(cards):
    s, spell, creatures = setup(cards, 'Pitfall Trap', ('G', 'G'))
    assert not offers(s, spell)
    mana(s, U=1, W=1)
    bounce = put(s, 'Unsummon', 'hand')
    act(s, 'p1', type='cast_spell', card_id=bounce.id, targets=[creatures[1].id])
    settle(s)
    assert len(offers(s, spell)) == 1
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[creatures[0].id], alt_cost=offers(s, spell)[0].key)
    settle(s)
    assert creatures[0].id not in s.state.cards
    roundtrip(s)


def test_normal_mana_cost_still_available_when_alternative_condition_is_false(cards):
    s, spell, creatures = setup(cards, 'Pitfall Trap', ('G', 'G'))
    mana(s, C=2, W=1)
    assert not offers(s, spell)
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[creatures[0].id])
    settle(s)
    assert creatures[0].id not in s.state.cards
    roundtrip(s)


def test_arrow_volley_keeps_illegal_targets_share(cards):
    s, spell, creatures = setup(cards, 'Arrow Volley Trap', ('G',) * 4)
    mana(s, C=1, W=1, U=1)
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[creatures[0].id, creatures[1].id],
        target_counts=[2], division=[1, 4], alt_cost=offers(s, spell)[0].key)
    bounce = put(s, 'Unsummon', 'hand')
    act(s, 'p1', type='cast_spell', card_id=bounce.id, targets=[creatures[1].id])
    settle(s)
    assert s.state.cards[creatures[0].id].damage == 1
    roundtrip(s)


def test_nemesis_copy_exiles_at_the_next_end_step(cards):
    from tests.test_rules_wave30m_durations import to_phase

    s, spell, creatures = setup(cards, 'Nemesis Trap', ('W', 'G'))
    mana(s, B=2)
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[creatures[1].id], alt_cost=offers(s, spell)[0].key)
    settle(s)
    copy = next(c for c in s.state.cards.values() if c.name == creatures[1].name and c.id != creatures[1].id)
    assert copy.zone == 'p1:battlefield'
    to_phase(s, 'end', turn=4)
    settle(s)
    assert copy.id not in s.state.cards
    roundtrip(s)


def test_paid_alternative_cost_survives_cold_save_and_native_counter(cards, tmp_path):
    s, spell, creatures = setup(cards, 'Pitfall Trap', ('G',))
    mana(s, W=1, U=2)
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[creatures[0].id], alt_cost=offers(s, spell)[0].key)
    saved = tmp_path / 'trap.json'
    saved.write_text(s.state.model_dump_json())
    code = r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
saved,db,spell,attacker=sys.argv[1:]
repo=CardRepository(Path(db),ImageStore(Path(db).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(saved).read_text()),cards=repo)
assert s.state.rules.payments[s.state.rules.object_id(spell)].alternative=='alternative'
for _ in range(12):
 if not s.state.zones.get('stack'):break
 s.perform(s.state.rules.priority,{'type':'pass_priority'})
assert attacker not in s.state.cards
assert s.history.rebuild().model_dump(mode='json')==s.state.model_dump(mode='json')
repo.close()
'''
    result = subprocess.run([sys.executable, '-c', code, str(saved), str(cards.db_path), spell.id, creatures[0].id],
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    counter = put(s, 'Counterspell', 'hand')
    wait_priority(s, 'p1')
    act(s, 'p1', type='cast_spell', card_id=counter.id, targets=[spell.id])
    settle(s)
    assert s.state.cards[spell.id].zone == 'p1:graveyard'
    assert creatures[0].id in s.state.cards
    roundtrip(s)

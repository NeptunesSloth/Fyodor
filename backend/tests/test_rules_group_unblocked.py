"""CR 510.1c: optional per-creature assignment from group static permissions."""
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
from tests.test_rules_banding import attacks, block
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave6c_tokens_pumps import chars
from tests.test_rules_wave30m_durations import to_phase


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/group_unblocked_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()




INVASION = 'Invasion of Ikoria // Zilortha, Apex of Ikoria'


def setup(cards, *, source=INVASION, attackers=('Grizzly Bears',), wall_toughness=10):
    s = table(cards, [INVASION, 'Siege Behemoth', 'Indomitable Might', 'Ruxa, Patient Professor',
                     'Grizzly Bears', 'Elite Vanguard', 'Colossal Dreadmaw', 'Mirran Crusader', 'Humility'])
    to_phase(s, 'main1', turn=1)
    if source == INVASION:
        src = put(s, source, 'hand')
        act(s, 'p1', type='set_face', card_id=src.id, face=1)
        act(s, 'p1', type='move', card_ids=[src.id], to={'player': 'p1', 'zone': 'battlefield'})
        act(s, 'p1', type='set_face', card_id=src.id, face=1)
    else:
        src = put(s, source, 'battlefield')
    army = [put(s, name, 'battlefield') for name in attackers]
    if source == 'Indomitable Might':
        act(s, 'p1', type='attach', card_ids=[src.id], to=army[0].id)
    walls = []
    for i in range(len(army)):
        before = set(s.state.cards)
        act(s, 'p2', type='create_token', player='p2', token={'name': f'Wall {i}', 'type_line': 'Token Creature — Wall',
                                                         'power': '0', 'toughness': str(wall_toughness)})
        walls.append(next(c for cid, c in s.state.cards.items() if cid not in before))
    return s, src, army, walls


def start_combat(s, army, walls, *, source=None):
    pairs = [(c, 'p2') for c in army]
    if source is not None:
        pairs.append((source, 'p3'))
    attacks(s, pairs)
    block(s, list(zip(walls, army, strict=True)))


def finish_combat(s, *, answers=()):
    seen = []
    for _ in range(100):
        if s.state.turn.phase == 'main2':
            roundtrip(s)
            return seen
        d = s.state.rules.decision
        if d is None:
            act(s, s.state.rules.priority, type='pass_priority')
        elif d.resume.get('step') == 'assign_unblocked':
            seen.append(d.resume['creature'])
            assert s.view(d.player)['rules']['decision'].get('options') is not None
            for pid in s.state.players:
                if pid != d.player:
                    assert 'options' not in s.view(pid)['rules']['decision']
            roundtrip(s)
            answer = answers[len(seen) - 1] if len(answers) >= len(seen) else 'yes'
            act(s, d.player, type='choose', decision_id=d.id, option_ids=[answer])
        elif d.kind == 'declare_blockers':
            act(s, d.player, type='declare_blockers', blocks=[])
        elif d.kind == 'divide':
            need = d.resume.get('lethal') or []
            amounts = [*need, d.resume['total'] - sum(need)] if d.resume.get('free') is not None else [d.resume['total'], *([0] * (len(d.options) - 1))]
            act(s, d.player, type='choose', decision_id=d.id, amounts=amounts)
        else:
            act(s, d.player, type='choose', decision_id=d.id, option_ids=[o.id for o in d.options][:max(1, d.min_choices)])
    raise AssertionError('combat did not finish')


@pytest.mark.parametrize('name', [INVASION, 'Siege Behemoth', 'Indomitable Might'])
def test_group_permissions_promote_cards(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


@pytest.mark.parametrize('answer,damage', [('yes', 2), ('no', 0)])
def test_zilortha_optional_assignment_to_defender_or_blocker(cards, answer, damage):
    s, _, army, walls = setup(cards)
    start_combat(s, army, walls)
    assert finish_combat(s, answers=[answer]) == [army[0].id]
    assert s.state.players['p2'].life == 40 - damage
    assert s.state.cards[walls[0].id].damage == (0 if answer == 'yes' else 2)


def test_nonhuman_filter_excludes_human_with_other_subtype_and_choices_are_individual(cards):
    s, _, army, walls = setup(cards, attackers=('Grizzly Bears', 'Elite Vanguard', 'Colossal Dreadmaw'))
    start_combat(s, army, walls)
    assert finish_combat(s, answers=['yes', 'no']) == [army[0].id, army[2].id]
    assert s.state.players['p2'].life == 38
    assert [s.state.cards[w.id].damage for w in walls] == [0, 2, 6]


def test_removing_source_before_assignment_removes_permission(cards):
    s, source, army, walls = setup(cards)
    start_combat(s, army, walls)
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'graveyard'})
    assert finish_combat(s) == []
    assert s.state.players['p2'].life == 40
    assert s.state.cards[walls[0].id].damage == 2


def test_changing_source_controller_before_assignment_removes_its_old_controller_permission(cards):
    s, source, army, walls = setup(cards)
    start_combat(s, army, walls)
    act(s, 'p1', type='set_controller', card_ids=[source.id], player='p2')
    assert finish_combat(s) == []
    assert s.state.players['p2'].life == 40


@pytest.mark.parametrize('attacking', [False, True])
def test_siege_behemoth_only_while_attacking(cards, attacking):
    s, source, army, walls = setup(cards, source='Siege Behemoth')
    start_combat(s, army, walls, source=source if attacking else None)
    assert finish_combat(s) == ([army[0].id] if attacking else [])
    assert s.state.players['p2'].life == (38 if attacking else 40)


@pytest.mark.parametrize('answer,damage', [('yes', 6), ('no', 4)])
def test_declining_option_preserves_normal_trample_assignment(cards, answer, damage):
    s, _, army, walls = setup(cards, attackers=('Colossal Dreadmaw',), wall_toughness=2)
    start_combat(s, army, walls)
    assert finish_combat(s, answers=[answer]) == [army[0].id]
    assert s.state.players['p2'].life == 40 - damage


def test_aura_allows_its_hosts_controller_to_choose(cards):
    s, source, army, walls = setup(cards, source='Indomitable Might')
    act(s, 'p1', type='set_controller', card_ids=[source.id], player='p2')
    start_combat(s, army, walls)
    assert finish_combat(s) == [army[0].id]
    assert s.state.players['p2'].life == 35
    assert s.state.cards[walls[0].id].damage == 0


def test_group_permission_does_not_add_abilities(cards):
    s, _, army, walls = setup(cards, source='Ruxa, Patient Professor')
    assert not chars(s, army[0]).abilities
    start_combat(s, army, walls)
    assert finish_combat(s) == [army[0].id]
    assert not chars(s, army[0]).abilities
    # Ruxa's separate +1/+1 with-no-abilities layer gap remains partial.
    assert coverage.of_card_data(cards.resolve('Ruxa, Patient Professor')).level == 'PARTIAL'


def test_double_strike_asks_again_and_can_change_answer_in_second_damage_step(cards):
    s, source, army, walls = setup(cards, source='Siege Behemoth', attackers=('Mirran Crusader',))
    start_combat(s, army, walls, source=source)
    assert finish_combat(s, answers=['yes', 'no']) == [army[0].id, army[0].id]
    assert s.state.players['p2'].life == 38
    assert s.state.cards[walls[0].id].damage == 2


def test_losing_source_abilities_before_damage_removes_group_permission(cards):
    s, _, army, walls = setup(cards)
    start_combat(s, army, walls)
    humility = put(s, 'Humility', 'battlefield')
    assert humility.id in s.state.cards
    assert finish_combat(s) == []
    assert s.state.players['p2'].life == 40

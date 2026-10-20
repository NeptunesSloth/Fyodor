"""CR 702.29c/f, 614.1: cycling permissions and graveyard replacements."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/blink_search_together_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()



def test_sword_is_full(cards):
    assert coverage.of_card_data(cards.resolve('Sword of Hearth and Home')).level == 'FULL'


def setup_damage_trigger(cards, target_name='Tireless Tracker', token=False, stolen=False):
    from tests.game_helpers import act
    from tests.test_rules_banding import declare_only
    from tests.test_rules_designations import put
    from tests.test_rules_shared_damage_choices import table

    s = table(cards, ['Sword of Hearth and Home', 'Grizzly Bears', target_name], [], [])
    bearer = put(s, 'Grizzly Bears', 'battlefield')
    if token:
        act(s, 'p1', type='create_token', player='p1', token={'name': 'Bear', 'type_line': 'Token Creature — Bear', 'power': '2', 'toughness': '2', 'colors': ['G']})
        target = next(c for c in s.state.cards.values() if c.is_token)
    else:
        target = put(s, target_name, 'battlefield')
    if stolen:
        act(s, 'p1', type='set_controller', card_ids=[target.id], player='p2')
    sword = put(s, 'Sword of Hearth and Home', 'battlefield')
    act(s, 'p1', type='attach', card_ids=[sword.id], to=bearer.id)
    act(s, 'p1', type='counter', card_ids=[target.id], kind='+1/+1', delta=1)
    declare_only(s, [bearer], [])
    for _ in range(80):
        d = s.state.rules.decision
        if d:
            if d.kind == 'declare_blockers':
                act(s, d.player, type='declare_blockers', blocks=[])
            else:
                return s, bearer, target, sword
        else:
            act(s, s.state.rules.priority, type='pass_priority')
    raise AssertionError('no Sword trigger target choice')


def answer(s, ids):
    from tests.game_helpers import act
    from tests.test_rules_designations import roundtrip

    d = s.state.rules.decision
    assert d
    roundtrip(s)
    act(s, d.player, type='choose', decision_id=d.id, option_ids=ids)


@pytest.mark.parametrize('blink', [False, True])
@pytest.mark.parametrize('find_land', [False, True])
def test_sword_returns_creature_and_found_land_together(cards, blink, find_land):
    from tests.test_rules_designations import roundtrip, settle

    s, _, target, _ = setup_damage_trigger(cards)
    d = s.state.rules.decision
    assert d and d.min_choices == 0
    answer(s, [target.id] if blink else [])
    settle(s)
    d = s.state.rules.decision
    assert d and d.prompt.startswith('Search')
    land = next(o.id for o in d.options if s.state.cards[o.id].name == 'Forest')
    if blink:
        assert s.state.cards[target.id].zone == 'p1:exile'
    answer(s, [land] if find_land else [])
    settle(s)
    assert s.state.cards[target.id].zone == 'p1:battlefield'
    assert s.state.cards[target.id].counters.get('+1/+1', 0) == (0 if blink else 1)
    if find_land:
        assert s.state.cards[land].zone == 'p1:battlefield'
    clues = [c for c in s.state.cards.values() if c.is_token and c.name == 'Clue']
    assert len(clues) == int(find_land)
    if blink and find_land:
        moves = [step for a in s.history.actions if isinstance(getattr(a, "r", None), list) for step in a.r
                 if step.get('type') == 'move' and step.get('to', {}).get('zone') == 'battlefield']
        assert any({target.id, land} <= set(step['card_ids']) for step in moves)
    roundtrip(s)


def test_blinked_owned_creature_returns_under_your_control_from_opponents_control(cards):
    from tests.test_rules_designations import roundtrip, settle

    s, _, target, _ = setup_damage_trigger(cards, stolen=True)
    assert s.state.cards[target.id].controller == 'p2'
    d = s.state.rules.decision
    assert d and target.id in {o.id for o in d.options}
    answer(s, [target.id])
    settle(s)
    d = s.state.rules.decision
    assert d
    land = d.options[0].id
    answer(s, [land])
    settle(s)
    assert s.state.cards[target.id].controller == 'p1'
    assert s.state.cards[target.id].zone == 'p1:battlefield'
    assert any(c.is_token and c.name == 'Clue' for c in s.state.cards.values())
    roundtrip(s)


def test_exiled_token_does_not_return_but_search_still_puts_land_onto_battlefield(cards):
    from tests.test_rules_designations import roundtrip, settle

    s, _, target, _ = setup_damage_trigger(cards, token=True)
    answer(s, [target.id])
    settle(s)
    d = s.state.rules.decision
    assert d
    land = d.options[0].id
    answer(s, [land])
    settle(s)
    assert target.id not in s.state.cards
    assert s.state.cards[land].zone == 'p1:battlefield'
    assert not any(c.is_token for c in s.state.cards.values())
    roundtrip(s)


def test_target_departure_makes_trigger_fail_to_resolve_without_search(cards):
    from tests.game_helpers import act
    from tests.test_rules_designations import roundtrip, settle

    s, _, target, _ = setup_damage_trigger(cards)
    answer(s, [target.id])
    act(s, 'p1', type='move', card_ids=[target.id], to={'player': 'p1', 'zone': 'graveyard'})
    before = len(s.state.zones['p1:library'])
    settle(s)
    assert s.state.rules.decision is None
    assert len(s.state.zones['p1:library']) == before
    assert s.state.cards[target.id].zone == 'p1:graveyard'
    roundtrip(s)

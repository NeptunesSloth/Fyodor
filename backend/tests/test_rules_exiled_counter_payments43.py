"""Actual Mari death/exile and combat-trigger counter payment."""
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
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_linked_aggregates import cast
from tests.test_rules_shared_damage_choices import table


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/exiled_counter_payments43_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='ecp', number=str(i), **{k: v for k, v in c.items() if k not in ('name', 'set_code')})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards):
    names = ['Mari, the Killing Quill', 'Grizzly Bears', 'Lightning Bolt', 'Llanowar Elves']
    s = table(cards, names, names, names)
    mari = put(s, names[0], 'hand')
    cast(s, mari)
    settle(s)
    victim = put(s, 'Grizzly Bears', 'battlefield', pid='p2')
    bolt = put(s, 'Lightning Bolt', 'hand')
    cast(s, bolt, targets=[victim.id])
    settle(s)
    assert s.state.cards[victim.id].zone == 'p2:exile'
    assert s.state.cards[victim.id].counters == {'hit': 1}
    return s, mari, victim


def attack(s, source):
    from tests.test_rules_wave5c_combat import declare, to_attack
    from tests.test_rules_wave30m_durations import to_phase

    to_phase(s, 'main1', turn=4)
    to_attack(s, number=4)
    declare(s, (source, 'p2'))
    for _ in range(40):
        d = s.state.rules.decision
        if d is not None and d.kind == 'declare_blockers':
            act(s, d.player, type='declare_blockers', blocks=[])
        elif d is not None:
            return
        else:
            act(s, s.state.rules.priority, type='pass_priority')
    raise AssertionError('No Mari payment trigger')


def test_full_canonical(cards):
    assert coverage.of_card_data(cards.resolve('Mari, the Killing Quill')).level == 'FULL'


@pytest.mark.parametrize('pay', [False, True])
def test_actual_death_exile_hit_and_optional_combat_payment(cards, pay):
    from app.rules.plan import Plan

    s, mari, victim = setup(cards)
    assert 'deathtouch' in Plan(s.state, 'p1', cards, None).ch(s.state.cards[mari.id]).keywords
    attack(s, mari)
    d = s.state.rules.decision
    assert d is not None
    before = len(s.state.zones.get('p1:hand', []))
    act(s, d.player, type='choose', decision_id=d.id, option_ids=['pay' if pay else 'decline'])
    if pay:
        d = s.state.rules.decision
        assert d is not None and {o.card_id for o in d.options} == {victim.id}
        act(s, d.player, type='choose', decision_id=d.id, option_ids=[victim.id])
    settle(s)
    assert s.state.cards[victim.id].counters.get('hit', 0) == (0 if pay else 1)
    assert len(s.state.zones.get('p1:hand', [])) == before + int(pay)
    assert len([c for c in s.state.cards.values() if c.is_token and c.name == 'Treasure']) == (2 if pay else 0)
    roundtrip(s)


def test_actual_hit_cost_uses_any_damaged_player_card_but_not_other_owner(cards):
    s, mari, victim = setup(cards)
    unrelated = put(s, 'Llanowar Elves', 'exile', pid='p2')
    wrong = put(s, 'Llanowar Elves', 'exile', pid='p3')
    for obj in [unrelated, wrong]:
        act(s, 'p1', type='counter', card_ids=[obj.id], kind='hit', delta=1)
    attack(s, mari)
    d = s.state.rules.decision
    act(s, d.player, type='choose', decision_id=d.id, option_ids=['pay'])
    d = s.state.rules.decision
    assert {o.card_id for o in d.options} == {victim.id, unrelated.id}
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[unrelated.id])
    settle(s)
    assert s.state.cards[victim.id].counters == {'hit': 1}
    assert not s.state.cards[unrelated.id].counters
    assert s.state.cards[wrong.id].counters == {'hit': 1}
    roundtrip(s)


def test_actual_hit_payment_choice_true_cold(cards, tmp_path):
    import subprocess
    import sys

    s, mari, victim = setup(cards)
    attack(s, mari)
    d = s.state.rules.decision
    act(s, d.player, type='choose', decision_id=d.id, option_ids=['pay'])
    assert s.state.rules.decision is not None
    saved = tmp_path / 'mari43.json'
    saved.write_text(s.state.model_dump_json())
    script = r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
saved, db, victim = sys.argv[1:]
repo = CardRepository(Path(db), ImageStore(Path(db).parent / 'images'))
s = GameSession(GameState.model_validate_json(Path(saved).read_text()), cards=repo)
d = s.state.rules.decision
assert d is not None
before = len(s.state.zones.get('p1:hand', []))
s.perform(d.player, {'type':'choose','decision_id':d.id,'option_ids':[victim]})
assert not s.state.cards[victim].counters
assert len(s.state.zones.get('p1:hand', [])) == before + 1
assert len([c for c in s.state.cards.values() if c.is_token and c.name == 'Treasure']) == 2
assert s.history.rebuild().model_dump(mode='json') == s.state.model_dump(mode='json')
repo.close()
'''
    result = subprocess.run([sys.executable, '-c', script, str(saved), str(cards.db_path), victim.id],
                            cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr


def test_actual_grant_covers_three_tribes_and_only_own_creatures(cards):
    from app.rules.plan import Plan

    names = ['Mari, the Killing Quill', 'Rathi Intimidator', 'Goblin Tunneler', 'Grizzly Bears']
    s = table(cards, names, names, names)
    source = put(s, names[0], 'hand')
    cast(s, source)
    settle(s)
    mercenary = put(s, 'Rathi Intimidator', 'battlefield')
    rogue = put(s, 'Goblin Tunneler', 'battlefield')
    wrong_controller = put(s, 'Goblin Tunneler', 'battlefield', pid='p2')
    wrong_type = put(s, 'Grizzly Bears', 'battlefield')
    p = Plan(s.state, 'p1', cards, None)
    for c in [source, mercenary, rogue]:
        ch = p.ch(p.state.cards[c.id])
        assert 'deathtouch' in ch.keywords
        assert any('hit counter' in a.text and a.kind == 'triggered' for a in ch.abilities)
    for c in [wrong_controller, wrong_type]:
        ch = p.ch(p.state.cards[c.id])
        assert 'deathtouch' not in ch.keywords
        assert not any('hit counter' in a.text and a.kind == 'triggered' for a in ch.abilities)
    roundtrip(s)

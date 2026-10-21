"""Combat quantities and while conditions retain their distinct evaluation times."""
import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage, sba
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana
from tests.test_rules_declaration_requirements33 import start
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_look import settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

DATA = json.loads((Path(__file__).parent / 'fixtures/trigger_combat_counts50_cards.json').read_text())


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(DATA):
        base[c['name']] = card(c['name'], number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards, name):
    names = [c['name'] for c in DATA] + ['Grizzly Bears', 'Murder', 'Lightning Bolt']
    s = table(cards, names, names, names)
    start(s)
    act(s, 'p1', type='set_prefs', hold_priority=True)
    source = put(s, name, 'hand')
    mana(s, C=3, G=1, R=1)
    act(s, 'p1', type='cast_spell', card_id=source.id, sources=[])
    settle(s)
    return s, source


def pt(s, card):
    ch = Plan(s.state, 'p1', s.cards, None).ch(card)
    return sba.power(card, ch), sba.toughness(card, ch)


def attack(s, pairs, turn=7, pid='p1'):
    to_phase(s, 'declare_attackers', turn=turn)
    act(s, pid, type='declare_attackers', attackers=[{'card_id': c.id, 'target': p} for c, p in pairs])
    if (d := s.state.rules.decision) is not None and d.resume.get('step') == 'order_triggers':
        act(s, d.player, type='choose', decision_id=d.id, option_ids=[o.id for o in d.options])


@pytest.mark.parametrize('name', ['Aurochs', 'Burning Sun Cavalry'])
def test_complete_canonical(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


@pytest.mark.parametrize('others', [0, 1, 2])
def test_aurochs_counts_other_attacking_subtypes_not_card_names(cards, others):
    s, source = setup(cards, 'Aurochs')
    bull = put(s, 'Bull Aurochs', 'battlefield')
    foreign = put(s, 'Aurochs', 'battlefield', 'p2')
    act(s, 'p1', type='set_controller', card_ids=[foreign.id], player='p1')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    pairs = [(source, 'p2'), (bear, 'p2')]
    pairs += [(c, 'p2') for c in [bull, foreign][:others]]
    attack(s, pairs)
    assert pt(s, source) == (2, 3)  # The bonus does not affect attack legality.
    settle(s)
    assert pt(s, source) == (2 + others, 3)
    roundtrip(s)


def test_aurochs_count_is_read_when_ability_resolves(cards):
    s, source = setup(cards, 'Aurochs')
    bull = put(s, 'Bull Aurochs', 'battlefield')
    attack(s, [(source, 'p2'), (bull, 'p2')])
    bolt = put(s, 'Lightning Bolt', 'hand')
    mana(s, R=1)
    act(s, 'p1', type='cast_spell', card_id=bolt.id, targets=[bull.id], sources=[])
    settle(s)
    assert bull.zone == 'p1:graveyard' and pt(s, source) == (2, 3)


def test_aurochs_native_trample_uses_bonus_and_expires_at_cleanup(cards):
    s, source = setup(cards, 'Aurochs')
    bull = put(s, 'Bull Aurochs', 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    attack(s, [(source, 'p2'), (bull, 'p3')])
    settle(s)
    assert pt(s, source) == (3, 3)
    life = s.state.players['p2'].life
    to_phase(s, 'declare_blockers', turn=7)
    act(s, 'p2', type='declare_blockers', blocks=[{'blocker_id': bear.id, 'attacker_id': source.id}])
    for _ in range(60):
        d = s.state.rules.decision
        if d is not None and d.kind == 'divide':
            break
        if d is not None and d.kind == 'declare_blockers':
            act(s, d.player, type='declare_blockers', blocks=[])
        else:
            assert d is None
            act(s, s.state.rules.priority, type='pass_priority')
    assert d is not None and d.kind == 'divide'
    act(s, d.player, type='choose', decision_id=d.id,
        amounts=[2 if o.card_id == bear.id or o.id == bear.id else 1 for o in d.options])
    to_phase(s, 'end_combat', turn=7)
    assert bear.zone == 'p2:graveyard' and s.state.players['p2'].life == life - 1
    to_phase(s, 'main1', turn=8)
    assert pt(s, source) == (2, 3)
    roundtrip(s)


@pytest.mark.parametrize('owner,bonus', [('p1', 1), ('p2', 0), (None, 0)])
def test_cavalry_attack_while_condition_names_ability_controller(cards, owner, bonus):
    s, source = setup(cards, 'Burning Sun Cavalry')
    if owner:
        put(s, 'Colossal Dreadmaw', 'battlefield', owner)
    attack(s, [(source, 'p2')])
    settle(s)
    assert pt(s, source) == (2 + bonus, 2 + bonus)
    roundtrip(s)


@pytest.mark.parametrize('had_dinosaur', [True, False])
def test_cavalry_condition_is_checked_at_event_only(cards, had_dinosaur):
    s, source = setup(cards, 'Burning Sun Cavalry')
    dinosaur = put(s, 'Colossal Dreadmaw', 'battlefield') if had_dinosaur else None
    attack(s, [(source, 'p2')])
    if dinosaur:
        spell = put(s, 'Murder', 'hand')
        mana(s, C=1, B=2)
        act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[dinosaur.id], sources=[])
    else:
        put(s, 'Colossal Dreadmaw', 'battlefield')
    settle(s)
    assert pt(s, source) == ((3, 3) if had_dinosaur else (2, 2))


@pytest.mark.parametrize('has_dinosaur', [True, False])
def test_cavalry_native_block_event(cards, has_dinosaur):
    s, source = setup(cards, 'Burning Sun Cavalry')
    if has_dinosaur:
        put(s, 'Colossal Dreadmaw', 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    attack(s, [(bear, 'p1')], turn=5, pid='p2')
    to_phase(s, 'declare_blockers', turn=5)
    act(s, 'p1', type='declare_blockers', blocks=[{'blocker_id': source.id, 'attacker_id': bear.id}])
    settle(s)
    assert pt(s, source) == ((3, 3) if has_dinosaur else (2, 2))
    roundtrip(s)


@pytest.mark.parametrize('name', ['Aurochs', 'Burning Sun Cavalry'])
def test_native_combat_pending_ability_survives_cold_control_change(cards, tmp_path, name):
    import os
    import subprocess
    import sys

    import app

    s, source = setup(cards, name)
    if name == 'Aurochs':
        bull = put(s, 'Bull Aurochs', 'battlefield')
        attack(s, [(source, 'p2'), (bull, 'p2')])
    else:
        dinosaur = put(s, 'Colossal Dreadmaw', 'battlefield')
        attack(s, [(source, 'p2')])
        spell = put(s, 'Murder', 'hand')
        mana(s, C=1, B=2)
        act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[dinosaur.id], sources=[])
    act(s, 'p1', type='set_controller', card_ids=[source.id], player='p2')
    saved = tmp_path / 'combat-count.json'
    saved.write_text(s.state.model_dump_json())
    code = r"""
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from app.rules import sba
from app.rules.plan import Plan
from tests.test_rules_library_look import settle
from tests.test_rules_designations import roundtrip
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
settle(s)
c=s.state.cards[sys.argv[3]]
ch=Plan(s.state,'p1',repo,None).ch(c)
assert c.controller=='p2'
assert (sba.power(c,ch),sba.toughness(c,ch))==(3,3)
roundtrip(s)
"""
    result = subprocess.run(
        [sys.executable, '-c', code, str(saved), str(cards.db_path), source.id],
        cwd=Path(app.__file__).resolve().parents[1],
        env={**os.environ, 'PYTHONPATH': str(Path(__file__).resolve().parents[1])},
        capture_output=True, text=True, timeout=90,
    )
    assert result.returncode == 0, result.stdout + result.stderr

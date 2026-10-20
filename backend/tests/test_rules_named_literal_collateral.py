"""Actual canonical gameplay for named-literal collateral promotions."""
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
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana, wait_priority
from tests.test_rules_conditionals import settle, until
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

NAMES = ['Deathpact Angel', 'Bubbling Cauldron']


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/named_literal_collateral_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='lor', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()




@pytest.mark.parametrize('name', NAMES)
def test_actual_named_literal_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


def setup(cards, name):
    support = ['Grizzly Bears', 'Festering Newt', 'Murder', 'Clone', 'Word of Seizing', 'Platinum Emperion']
    s = table(cards, [name, name, *support], support, support)
    for p in ['p1', 'p2', 'p3']:
        act(s, p, type='set_prefs', hold_priority=True)
    return s, put(s, name, 'battlefield')


def kill(s, source):
    murder = put(s, 'Murder', 'hand')
    mana(s, C=1, B=2)
    wait_priority(s, 'p1')
    act(s, 'p1', type='cast_spell', card_id=murder.id, targets=[source.id])
    settle(s)
    return next(c for c in s.state.cards.values() if c.is_token and c.name == 'Cleric')


def test_deathpact_actual_death_creates_quoted_cleric_and_returns_named_angel(cards):
    s, angel = setup(cards, 'Deathpact Angel')
    wrong = put(s, 'Grizzly Bears', 'graveyard')
    token = kill(s, angel)
    assert s.state.cards[angel.id].zone == 'p1:graveyard'
    mana(s, C=3, W=1, B=2)
    with pytest.raises(ActionError):  # its real tap cost respects summoning sickness
        act(s, 'p1', type='activate_ability', card_id=token.id, ability=0)
    to_phase(s, 'main1', turn=4)
    mana(s, C=3, W=1, B=2)
    wait_priority(s, 'p1')
    act(s, 'p1', type='activate_ability', card_id=token.id, ability=0)
    settle(s)
    assert s.state.cards[angel.id].zone == 'p1:battlefield'
    assert s.state.cards[wrong.id].zone == 'p1:graveyard'
    assert not any(c.is_token and c.name == 'Cleric' and c.zone.endswith(':battlefield') for c in s.state.cards.values())
    roundtrip(s)


def test_deathpact_stolen_angel_cleric_uses_controller_graveyard_not_owner(cards):
    s, angel = setup(cards, 'Deathpact Angel')
    steal = put(s, 'Word of Seizing', 'hand', pid='p2')
    mana(s, 'p2', C=3, R=2)
    wait_priority(s, 'p2')
    act(s, 'p2', type='cast_spell', card_id=steal.id, targets=[angel.id])
    settle(s)
    token = kill(s, angel)
    assert token.controller == 'p2' and s.state.cards[angel.id].zone == 'p1:graveyard'
    to_phase(s, 'main1', turn=4)
    mana(s, 'p2', C=3, W=1, B=2)
    wait_priority(s, 'p2')
    act(s, 'p2', type='activate_ability', card_id=token.id, ability=0)
    settle(s)
    assert s.state.cards[angel.id].zone == 'p1:graveyard'
    roundtrip(s)


def test_deathpact_cleric_pending_named_choice_fresh_process(cards, tmp_path):
    import subprocess
    import sys

    from app.game.session import GameSession
    from app.game.state import GameState

    s, angel = setup(cards, 'Deathpact Angel')
    token = kill(s, angel)
    another = next(c for c in s.state.cards.values() if c.owner == 'p1' and c.name == 'Deathpact Angel' and c.id != angel.id)
    act(s, 'p1', type='move', card_ids=[another.id], to={'player': 'p1', 'zone': 'graveyard'})
    wrong = put(s, 'Grizzly Bears', 'graveyard')
    to_phase(s, 'main1', turn=4)
    mana(s, C=3, W=1, B=2)
    act(s, 'p1', type='activate_ability', card_id=token.id, ability=0)
    until(s, lambda s: s.state.rules.decision is not None)
    d = s.state.rules.decision
    assert {o.card_id for o in d.options} == {angel.id, another.id}
    original = tmp_path / 'original.json'
    restored = tmp_path / 'restored.json'
    original.write_text(s.state.model_dump_json())
    code = '''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
repo=CardRepository(Path(sys.argv[1]),ImageStore(Path(sys.argv[2])))
s=GameSession(GameState.model_validate_json(Path(sys.argv[3]).read_text()),cards=repo)
d=s.state.rules.decision
s.perform(d.player,{'type':'choose','decision_id':d.id,'option_ids':[sys.argv[5]]})
Path(sys.argv[4]).write_text(s.state.model_dump_json())
'''
    result = subprocess.run([sys.executable, '-c', code, str(cards.db_path), str(tmp_path / 'images'),
                             str(original), str(restored), another.id], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    s = GameSession(GameState.model_validate_json(restored.read_text()), cards=cards)
    settle(s)
    assert s.state.cards[another.id].zone == 'p1:battlefield'
    assert s.state.cards[angel.id].zone == 'p1:graveyard' and s.state.cards[wrong.id].zone == 'p1:graveyard'
    roundtrip(s)


@pytest.mark.parametrize('locked', [False, True])
def test_cauldron_named_cost_rejects_other_creature_and_gains_actual_life_lost(cards, locked):
    s, source = setup(cards, 'Bubbling Cauldron')
    newt = put(s, 'Festering Newt', 'battlefield')
    wrong = put(s, 'Grizzly Bears', 'battlefield')
    if locked:
        put(s, 'Platinum Emperion', 'battlefield', pid='p3')
    mana(s, C=1)
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s, 'p1', type='activate_ability', card_id=source.id, ability=1,
            cost_choices=[{'component': 2, 'cards': [wrong.id]}])
    assert s.state.model_dump_json() == before
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=1,
        cost_choices=[{'component': 2, 'cards': [newt.id]}])
    settle(s)
    assert s.state.cards[newt.id].zone == 'p1:graveyard'
    assert s.state.cards[wrong.id].zone == 'p1:battlefield'
    assert s.state.players['p2'].life == 36
    assert s.state.players['p3'].life == (40 if locked else 36)
    assert s.state.players['p1'].life == (44 if locked else 48)
    roundtrip(s)

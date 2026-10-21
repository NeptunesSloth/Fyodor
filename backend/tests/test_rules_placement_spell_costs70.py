"""Exact counter-placement casting costs retain native payment authority."""
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
from tests.test_rules_declaration_requirements33 import start
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_look import settle
from tests.test_rules_shared_damage_choices import table

SOURCES = ['Lethal Sting', 'Scarscale Ritual']
DATA = json.loads((Path(__file__).parent / 'fixtures/placement_spell_costs70_cards.json').read_text())
NAMES = [c['name'] for c in DATA] + ['Grizzly Bears', 'Llanowar Elves', 'Colossal Dreadmaw', 'Counterspell', 'Nest of Scarabs', 'Vizier of Remedies', 'Melira, Sylvok Outcast']


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


def setup(cards):
    s = table(cards, NAMES, NAMES, NAMES)
    start(s)
    act(s, 'p1', type='set_prefs', hold_priority=True)
    return s


def prepare(s, name):
    source = put(s, name, 'hand')
    victim = put(s, 'Colossal Dreadmaw', 'battlefield', 'p2')
    mana(s, **({'C': 2, 'B': 1} if name == 'Lethal Sting' else {'C': 1, 'B': 1}))
    args = {'type': 'cast_spell', 'card_id': source.id, 'sources': []}
    if name == 'Lethal Sting':
        args['targets'] = [victim.id]
    return source, victim, args


@pytest.mark.parametrize('name', SOURCES)
def test_whole_canonicals(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


@pytest.mark.parametrize('name', SOURCES)
def test_paid_counter_cost_before_native_spell_body(cards, name):
    s = setup(cards)
    host = put(s, 'Grizzly Bears', 'battlefield')
    source, victim, args = prepare(s, name)
    hand_before = len(s.state.zones['p1:hand'])
    act(s, 'p1', **args, cost_choices=[{'component': 0, 'cards': [host.id]}])
    assert host.counters == {'-1/-1': 1} and source.zone == 'stack'
    assert not s.state.players['p1'].mana
    settle(s)
    assert source.zone == 'p1:graveyard' and host.zone == 'p1:battlefield'
    if name == 'Lethal Sting':
        assert victim.zone == 'p2:graveyard'
    else:
        assert len(s.state.zones['p1:hand']) == hand_before + 1
    roundtrip(s)


@pytest.mark.parametrize('name', SOURCES)
def test_no_own_creature_makes_cost_unpayable_atomically(cards, name):
    s = setup(cards)
    source, victim, args = prepare(s, name)
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s, 'p1', **args, cost_choices=[{'component': 0, 'cards': [victim.id]}])
    assert s.state.model_dump_json() == before and source.zone == 'p1:hand'
    roundtrip(s)


@pytest.mark.parametrize('name', SOURCES)
def test_prohibited_counter_cannot_pay_cost(cards, name):
    s = setup(cards)
    host = put(s, 'Grizzly Bears', 'battlefield')
    put(s, 'Solemnity', 'battlefield')
    source, victim, args = prepare(s, name)
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s, 'p1', **args, cost_choices=[{'component': 0, 'cards': [host.id]}])
    assert s.state.model_dump_json() == before and source.zone == 'p1:hand'
    roundtrip(s)


@pytest.mark.parametrize('name', SOURCES)
def test_lethal_cost_is_paid_and_state_actions_happen_before_resolution(cards, name):
    s = setup(cards)
    host = put(s, 'Llanowar Elves', 'battlefield')
    source, victim, args = prepare(s, name)
    act(s, 'p1', **args, cost_choices=[{'component': 0, 'cards': [host.id]}])
    assert host.zone == 'p1:graveyard' and source.zone == 'stack'
    settle(s)
    assert source.zone == 'p1:graveyard'
    if name == 'Lethal Sting':
        assert victim.zone == 'p2:graveyard'
    roundtrip(s)


def test_doubling_season_does_not_double_a_cost(cards):
    s = setup(cards)
    host = put(s, 'Grizzly Bears', 'battlefield')
    put(s, 'Doubling Season', 'battlefield')
    source, victim, args = prepare(s, 'Lethal Sting')
    act(s, 'p1', **args, cost_choices=[{'component': 0, 'cards': [host.id]}])
    settle(s)
    assert host.zone == 'p1:battlefield' and host.counters == {'-1/-1': 1}
    assert victim.zone == 'p2:graveyard' and source.zone == 'p1:graveyard'
    roundtrip(s)


def test_countered_spell_does_not_refund_paid_counter(cards):
    s = setup(cards)
    host = put(s, 'Grizzly Bears', 'battlefield')
    source, victim, args = prepare(s, 'Scarscale Ritual')
    hand_before = len(s.state.zones['p1:hand'])
    act(s, 'p1', **args, cost_choices=[{'component': 0, 'cards': [host.id]}])
    wait_priority(s, 'p2')
    counter = put(s, 'Counterspell', 'hand', 'p2')
    mana(s, pid='p2', U=2)
    act(s, 'p2', type='cast_spell', card_id=counter.id, targets=[source.id], sources=[])
    settle(s)
    assert source.zone == 'p1:graveyard' and host.counters == {'-1/-1': 1}
    assert len(s.state.zones['p1:hand']) == hand_before - 1
    roundtrip(s)


def test_destroy_target_that_died_paying_cost_uses_native_fizzle(cards):
    s = setup(cards)
    host = put(s, 'Llanowar Elves', 'battlefield')
    source, victim, args = prepare(s, 'Lethal Sting')
    args['targets'] = [host.id]
    act(s, 'p1', **args, cost_choices=[{'component': 0, 'cards': [host.id]}])
    assert host.zone == 'p1:graveyard' and source.zone == 'stack'
    settle(s)
    assert source.zone == 'p1:graveyard' and victim.zone == 'p2:battlefield'
    roundtrip(s)


@pytest.mark.parametrize('name', SOURCES)
def test_true_cold_paid_counter_cost_stays_paid(cards, tmp_path, name):
    import subprocess
    import sys

    s = setup(cards)
    host = put(s, 'Grizzly Bears', 'battlefield')
    source, victim, args = prepare(s, name)
    act(s, 'p1', **args, cost_choices=[{'component': 0, 'cards': [host.id]}])
    assert source.zone == 'stack' and host.counters == {'-1/-1': 1}
    saved = tmp_path / 'placement-cost70.json'
    saved.write_text(s.state.model_dump_json())
    code = r"""
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.test_rules_library_look import settle
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
before=len(s.state.zones['p1:hand'])
settle(s)
assert s.state.cards[sys.argv[3]].zone=='p1:graveyard'
assert s.state.cards[sys.argv[4]].counters=={'-1/-1':1}
assert s.state.cards[sys.argv[4]].zone=='p1:battlefield'
assert not s.state.players['p1'].mana
if sys.argv[6]=='Lethal Sting':
 assert s.state.cards[sys.argv[5]].zone=='p2:graveyard'
else:
 assert len(s.state.zones['p1:hand'])==before+2
assert s.state.rules.decision is None
GameState.model_validate_json(s.state.model_dump_json())
"""
    result = subprocess.run([sys.executable, '-c', code, str(saved), str(cards.db_path), source.id, host.id, victim.id, name],
                            capture_output=True, text=True, timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize('name', SOURCES)
def test_native_paid_counter_event_triggers_nest_even_when_payer_dies(cards, name):
    s = setup(cards)
    nest = put(s, 'Nest of Scarabs', 'battlefield')
    host = put(s, 'Llanowar Elves', 'battlefield')
    source, victim, args = prepare(s, name)
    act(s, 'p1', **args, cost_choices=[{'component': 0, 'cards': [host.id]}])
    assert host.zone == 'p1:graveyard' and source.zone == 'stack'
    settle(s)
    insects = [c for c in s.state.cards.values() if c.is_token and c.name == 'Insect' and c.zone == 'p1:battlefield']
    assert len(insects) == 1 and nest.zone == 'p1:battlefield'
    roundtrip(s)


@pytest.mark.parametrize('name', SOURCES)
def test_vizier_replacement_reduces_cost_counter_to_zero_but_cost_is_paid(cards, name):
    s = setup(cards)
    put(s, 'Vizier of Remedies', 'battlefield')
    put(s, 'Nest of Scarabs', 'battlefield')
    host = put(s, 'Llanowar Elves', 'battlefield')
    source, victim, args = prepare(s, name)
    hand_before = len(s.state.zones['p1:hand'])
    act(s, 'p1', **args, cost_choices=[{'component': 0, 'cards': [host.id]}])
    assert source.zone == 'stack' and not host.counters and host.zone == 'p1:battlefield'
    settle(s)
    assert source.zone == 'p1:graveyard' and not host.counters
    assert not any(c.is_token and c.name == 'Insect' for c in s.state.cards.values())
    if name == 'Lethal Sting':
        assert victim.zone == 'p2:graveyard'
    else:
        assert len(s.state.zones['p1:hand']) == hand_before + 1
    roundtrip(s)


def test_melira_forbids_payment_even_with_vizier_reducing_to_zero(cards):
    s = setup(cards)
    put(s, 'Vizier of Remedies', 'battlefield')
    put(s, 'Melira, Sylvok Outcast', 'battlefield')
    host = put(s, 'Grizzly Bears', 'battlefield')
    source, victim, args = prepare(s, 'Lethal Sting')
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s, 'p1', **args, cost_choices=[{'component': 0, 'cards': [host.id]}])
    assert s.state.model_dump_json() == before and source.zone == 'p1:hand'
    roundtrip(s)

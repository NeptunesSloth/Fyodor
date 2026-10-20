"""Legally announced activations finish payment without declaring their targets again."""
import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_player_protection import priority
from tests.test_rules_wave30m_durations import three
from tests.test_rules_wave31d_spell_copies import hold


@pytest.fixture()
def cards(settings):
    data = json.loads((Path(__file__).parent / 'fixtures/activation_announcement_cards.json').read_text())
    existing = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(data):
        existing[c['name']] = card(c['name'], set_code='coi', number=str(i), **{k: v for k, v in c.items() if k not in ('name', 'set_code')})
    settings.ensure_dirs()
    build_database(existing.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards):
    names = [c['name'] for c in json.loads((Path(__file__).parent / 'fixtures/activation_announcement_cards.json').read_text())]
    s = three(cards, names, names, names)
    hold(s)
    return s



def plasma_payment(s):
    from tests.test_rules_coin_outcomes import attack_ready
    from tests.test_rules_wave30m_durations import to_phase

    equipment = put(s, 'Plasma Caster', 'battlefield')
    host = put(s, 'Grizzly Bears', 'battlefield')
    blocker = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    altar = put(s, "Ashnod's Altar", 'battlefield')
    ironworks = put(s, 'Krark-Clan Ironworks', 'battlefield')
    put(s, 'Suppression Field', 'battlefield')
    act(s, 'p1', type='attach', card_ids=[equipment.id], to=host.id)
    attack_ready(s, host)
    to_phase(s, 'declare_blockers', turn=4)
    act(s, 'p2', type='declare_blockers', blocks=[{'blocker_id': blocker.id, 'attacker_id': host.id}])
    priority(s, 'p1')
    hold(s)
    act(s, 'p1', type='set_prefs', payment='self')
    act(s, 'p1', type='activate_ability', card_id=equipment.id, ability=2, targets=[blocker.id])
    assert s.state.rules.decision.resume['step'] == 'pay_mana'
    assert s.state.rules.decision.resume['paid_then']['stage'] == 'activation_announced'
    return equipment, host, blocker, altar, ironworks


@pytest.mark.parametrize('sacrificed', ['host', 'equipment'])
def test_canonical_plasma_pays_tax_after_original_host_or_source_is_sacrificed(cards, monkeypatch, sacrificed):
    s = setup(cards)
    equipment, host, blocker, altar, ironworks = plasma_payment(s)
    old_source = s.state.rules.object_id(equipment.id)
    original_host = s.state.rules.object_id(host.id)
    monkeypatch.setattr('app.game.resolve._rng_int', lambda rng, lo, hi: 0 if sacrificed == 'equipment' else (_ for _ in ()).throw(AssertionError('Illegal sole target must fizzle before the coin')))
    chosen = host if sacrificed == 'host' else equipment
    mana_source = altar if sacrificed == 'host' else ironworks
    act(s, 'p1', type='activate_ability', card_id=mana_source.id, ability=0,
        cost_choices=[{'component': 0, 'cards': [chosen.id]}])
    assert s.state.cards[chosen.id].zone == 'p1:graveyard'
    assert s.state.rules.decision is None
    entry = s.state.rules.stack[s.state.zones['stack'][-1]]
    assert entry.source_object == old_source
    assert original_host in entry.target_spec['what']
    assert s.state.players['p1'].resources.get('energy', 0) == 0
    settle(s)
    assert s.state.cards[blocker.id].zone == 'p2:battlefield'
    assert s.state.cards[blocker.id].damage == (1 if sacrificed == 'equipment' else 0)
    roundtrip(s)


@pytest.mark.parametrize('sacrificed', ['source', 'target'])
def test_ordinary_announced_activation_keeps_source_lki_and_original_target_oid(cards, sacrificed):
    s = setup(cards)
    source = put(s, 'Shivan Hellkite', 'battlefield')
    victim = put(s, 'Grizzly Bears', 'battlefield')
    altar = put(s, "Ashnod's Altar", 'battlefield')
    priority(s, 'p1')
    act(s, 'p1', type='set_prefs', payment='self')
    act(s, 'p1', type='add_mana', player='p1', mana={'R': 1})
    old_source = s.state.rules.object_id(source.id)
    old_target = s.state.rules.object_id(victim.id)
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=1,
        targets=['p2'] if sacrificed == 'source' else [victim.id])
    assert s.state.rules.decision.resume['step'] == 'pay_mana'
    chosen = source if sacrificed == 'source' else victim
    act(s, 'p1', type='activate_ability', card_id=altar.id, ability=0,
        cost_choices=[{'component': 0, 'cards': [chosen.id]}])
    entry = s.state.rules.stack[s.state.zones['stack'][-1]]
    assert entry.source_object == old_source
    if sacrificed == 'target':
        assert entry.targets[0].object_id == old_target
    settle(s)
    assert s.state.players['p2'].life == (39 if sacrificed == 'source' else 40)
    assert s.state.cards[chosen.id].zone == 'p1:graveyard'
    roundtrip(s)


@pytest.mark.parametrize('sacrificed', ['host', 'equipment'])
def test_native_activation_announcement_payment_resumes_in_fresh_process(cards, tmp_path, sacrificed):
    import subprocess
    import sys

    s = setup(cards)
    equipment, host, blocker, altar, ironworks = plasma_payment(s)
    chosen = host if sacrificed == 'host' else equipment
    mana_source = altar if sacrificed == 'host' else ironworks
    path = tmp_path / (sacrificed + '.json')
    path.write_text(s.state.model_dump_json())
    code = r'''
import importlib, sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
path, database, source, chosen, blocker, kind = sys.argv[1:]
repo = CardRepository(Path(database), ImageStore(Path(database).parent / 'images'))
s = GameSession(GameState.model_validate_json(Path(path).read_text()), cards=repo)
view = s.view('p3')
assert 'paid_then' not in str(view) and 'paid_purpose' not in str(view)
def roll(rng, lo, hi):
    if kind == 'host':
        raise AssertionError('The sole illegal target must fizzle before a coin')
    return 0
importlib.import_module('app.game.resolve')._rng_int = roll
s.perform('p1', {'type': 'activate_ability', 'card_id': source, 'ability': 0, 'cost_choices': [{'component': 0, 'cards': [chosen]}]})
assert s.state.rules.decision is None
assert s.state.cards[chosen].zone == 'p1:graveyard'
for _ in range(60):
    if not s.state.zones.get('stack'):
        break
    assert s.state.rules.decision is None
    s.perform(s.state.rules.priority, {'type': 'pass_priority'})
assert s.state.cards[blocker].zone == 'p2:battlefield'
assert s.state.cards[blocker].damage == (0 if kind == 'host' else 1)
assert s.state.players['p1'].resources.get('energy', 0) == 0
assert s.history.rebuild() == s.state
assert GameState.model_validate_json(s.state.model_dump_json()) == s.state
repo.close()
'''
    result = subprocess.run([sys.executable, '-c', code, str(path), str(cards.db_path), mana_source.id, chosen.id, blocker.id, sacrificed],
                            capture_output=True, text=True, cwd=Path(__file__).resolve().parents[1], timeout=120)
    assert result.returncode == 0, result.stderr


def test_cancel_before_mana_keeps_nonmana_costs_and_stack_untouched(cards):
    s = setup(cards)
    equipment, host, blocker, _, _ = plasma_payment(s)
    d = s.state.rules.decision
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=['cancel'])
    assert s.state.rules.decision is None and not s.state.zones.get('stack')
    assert s.state.players['p1'].resources.get('energy') == 2
    assert s.state.cards[equipment.id].attached_to == host.id
    assert s.state.cards[blocker.id].damage == 0
    roundtrip(s)

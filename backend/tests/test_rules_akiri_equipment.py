"""Akiri's equipped attack aggregation and untargeted Equipment removal."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_designations import pick, put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave5c_combat import declare, to_attack
from tests.test_rules_wave30m_durations import to_phase

NAME = 'Akiri, Fearless Voyager'


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/akiri_equipment_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='aki', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards, foreign=False):
    s = table(cards, [NAME, 'Grizzly Bears', 'Hill Giant', 'Bonesplitter', 'Lightning Greaves'],
              ['Bonesplitter', 'Jace Beleren'])
    source = put(s, NAME, 'battlefield')
    host = put(s, 'Grizzly Bears', 'battlefield')
    equipment = put(s, 'Bonesplitter', 'battlefield', 'p2' if foreign else 'p1')
    act(s, equipment.controller, type='attach', card_ids=[equipment.id], to=host.id)
    return s, source, host, equipment


def activate(s, source):
    act(s, 'p1', type='add_mana', player='p1', mana={'W': 1})
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=1)
    settle(s)


def test_full(cards):
    assert coverage.of_card_data(cards.resolve(NAME)).level == 'FULL'


@pytest.mark.parametrize('foreign', [False, True])
def test_unattach_foreign_or_owned_equipment_and_expire(cards, foreign):
    s, source, host, equipment = setup(cards, foreign)
    activate(s, source)
    roundtrip(s)
    pick(s, [equipment.id])
    settle(s)
    assert s.state.cards[equipment.id].attached_to is None
    assert s.state.cards[host.id].tapped
    assert 'indestructible' in Plan(s.state, 'p1', cards, None).ch(s.state.cards[host.id]).keywords
    roundtrip(s)
    to_phase(s, 'main1', turn=2)
    assert 'indestructible' not in Plan(s.state, 'p1', cards, None).ch(s.state.cards[host.id]).keywords


def test_decline_does_not_unattach_or_tap(cards):
    s, source, host, equipment = setup(cards)
    activate(s, source)
    pick(s, [])
    settle(s)
    assert s.state.cards[equipment.id].attached_to == host.id
    assert not s.state.cards[host.id].tapped
    roundtrip(s)


def test_source_gone_shroud_and_tapped_host(cards):
    s, source, host, equipment = setup(cards)
    greaves = put(s, 'Lightning Greaves', 'battlefield')
    act(s, 'p1', type='attach', card_ids=[greaves.id], to=host.id)
    act(s, 'p1', type='tap', card_ids=[host.id], tapped=True)
    act(s, 'p1', type='add_mana', player='p1', mana={'W': 1})
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=1)
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'graveyard'})
    settle(s)
    pick(s, [equipment.id])
    settle(s)
    assert 'indestructible' in Plan(s.state, 'p1', cards, None).ch(s.state.cards[host.id]).keywords
    assert s.state.cards[greaves.id].attached_to == host.id
    roundtrip(s)


@pytest.mark.parametrize('split', [False, True])
def test_draw_once_per_attacked_player(cards, split):
    s, source, host, equipment = setup(cards)
    giant = put(s, 'Hill Giant', 'battlefield')
    greaves = put(s, 'Lightning Greaves', 'battlefield')
    act(s, 'p1', type='attach', card_ids=[greaves.id], to=giant.id)
    to_attack(s, 4)
    before = len(s.state.zones['p1:hand'])
    declare(s, (host, 'p2'), (giant, 'p3' if split else 'p2'))
    settle(s)
    assert len(s.state.zones['p1:hand']) == before + (2 if split else 1)
    roundtrip(s)


def test_attacking_planeswalker_does_not_draw(cards):
    s, source, host, equipment = setup(cards)
    jace = put(s, 'Jace Beleren', 'battlefield', 'p2')
    act(s, 'p2', type='set_counter', card_id=jace.id, kind='loyalty', value=3)
    to_attack(s, 4)
    before = len(s.state.zones['p1:hand'])
    declare(s, (host, jace.id))
    settle(s)
    assert len(s.state.zones['p1:hand']) == before
    roundtrip(s)


def test_attack_qualification_is_snapshotted(cards):
    s, source, host, equipment = setup(cards)
    to_attack(s, 4)
    before = len(s.state.zones['p1:hand'])
    declare(s, (host, 'p2'))
    act(s, 'p1', type='detach', card_ids=[equipment.id])
    settle(s)
    assert len(s.state.zones['p1:hand']) == before + 1
    roundtrip(s)


def test_no_equipment_finishes_without_choice(cards):
    s, source, host, equipment = setup(cards)
    act(s, 'p1', type='detach', card_ids=[equipment.id])
    activate(s, source)
    assert s.state.rules.decision is None
    assert not s.state.cards[host.id].tapped
    roundtrip(s)


def test_unattached_germ_dies_despite_indestructible(cards):
    s = table(cards, [NAME, 'Batterskull'])
    source = put(s, NAME, 'battlefield')
    equipment = put(s, 'Batterskull', 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 5})
    act(s, 'p1', type='cast_spell', card_id=equipment.id)
    settle(s)
    host = s.state.cards[s.state.cards[equipment.id].attached_to]
    assert 'Germ' in Plan(s.state, 'p1', cards, None).ch(host).subtypes
    activate(s, source)
    pick(s, [equipment.id])
    settle(s)
    assert s.state.cards[equipment.id].attached_to is None
    assert host.id not in s.state.cards or not s.state.cards[host.id].zone.endswith(':battlefield')
    roundtrip(s)


def test_saved_equipment_choice_in_fresh_process(cards, tmp_path):
    import subprocess
    import sys

    s, source, host, equipment = setup(cards)
    activate(s, source)
    saved = tmp_path / 'akiri.json'
    saved.write_text(s.state.model_dump_json())
    script = r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from app.rules.plan import Plan
saved, database, host, equipment = sys.argv[1:]
repo = CardRepository(Path(database), ImageStore(Path(database).parent / 'images'))
s = GameSession(GameState.model_validate_json(Path(saved).read_text()), cards=repo)
d = s.state.rules.decision
s.perform(d.player, {'type':'choose','decision_id':d.id,'option_ids':[equipment]})
assert s.state.cards[equipment].attached_to is None
assert s.state.cards[host].tapped
assert 'indestructible' in Plan(s.state, 'p1', repo, None).ch(s.state.cards[host]).keywords
assert s.history.rebuild().model_dump(mode='json') == s.state.model_dump(mode='json')
repo.close()
'''
    result = subprocess.run([sys.executable, '-c', script, str(saved), str(cards.db_path), host.id, equipment.id],
                            cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr

"""CR 508.1, 603.3, 608.2: declared attack recipients persist through resolution."""
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
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/attack_declared_defenders_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


NAME = 'Firemane Commando'


def setup(cards):
    from tests.test_rules_designations import put
    from tests.test_rules_shared_damage_choices import table
    from tests.test_rules_wave30m_durations import to_phase

    s = table(cards, [NAME, 'Jace Beleren'], ['Grizzly Bears', 'Runeclaw Bear'], [])
    source = put(s, NAME, 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    other = put(s, 'Runeclaw Bear', 'battlefield', 'p2')
    pw = put(s, 'Jace Beleren', 'battlefield')
    from tests.game_helpers import act
    act(s, 'p1', type='set_counter', card_id=pw.id, kind='loyalty', value=3)
    to_phase(s, 'main1', turn=5)
    return s, source, bear, other, pw


def declare(s, pairs):
    from tests.game_helpers import act
    from tests.test_rules_conditionals import until

    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == 'declare_attackers')
    act(s, 'p2', type='declare_attackers', attackers=[{'card_id': c.id, 'target': t} for c, t in pairs])


def test_firemane_is_full(cards):
    assert coverage.of_card_data(cards.resolve(NAME)).level == 'FULL'


@pytest.mark.parametrize('dest,draws', [('p3', True), ('p1', False), ('planeswalker', True)])
def test_draw_depends_on_direct_declared_player_not_planeswalker(cards, dest, draws):
    from tests.test_rules_conditionals import settle
    from tests.test_rules_designations import roundtrip

    s, _, bear, other, pw = setup(cards)
    before = len(s.state.zones['p2:hand'])
    declare(s, [(bear, pw.id if dest == 'planeswalker' else dest), (other, 'p3')])
    settle(s)
    assert len(s.state.zones['p2:hand']) == before + int(draws)
    roundtrip(s)


def test_one_attacker_does_not_trigger(cards):
    from tests.test_rules_conditionals import settle

    s, _, bear, _, _ = setup(cards)
    before = len(s.state.zones['p2:hand'])
    declare(s, [(bear, 'p3')])
    settle(s)
    assert len(s.state.zones['p2:hand']) == before


@pytest.mark.parametrize('dest,draws', [('p3', True), ('p1', False)])
def test_departed_attackers_and_source_do_not_change_declared_recipients(cards, dest, draws):
    from tests.game_helpers import act
    from tests.test_rules_conditionals import settle
    from tests.test_rules_designations import roundtrip

    s, source, bear, other, _ = setup(cards)
    before = len(s.state.zones['p2:hand'])
    declare(s, [(bear, dest), (other, 'p3')])
    roundtrip(s)
    act(s, 'p1', type='move', card_ids=[source.id, bear.id, other.id], to={'player': 'p1', 'zone': 'exile'})
    settle(s)
    assert len(s.state.zones['p2:hand']) == before + int(draws)
    roundtrip(s)


@pytest.mark.parametrize('dest,draws', [('p3', True), ('p1', False)])
def test_trigger_controller_is_fixed_before_source_changes_control(cards, dest, draws):
    from tests.game_helpers import act
    from tests.test_rules_conditionals import settle
    from tests.test_rules_designations import roundtrip

    s, source, bear, other, _ = setup(cards)
    before = len(s.state.zones['p2:hand'])
    declare(s, [(bear, dest), (other, 'p3')])
    act(s, 'p1', type='set_controller', card_ids=[source.id], player='p2')
    settle(s)
    assert len(s.state.zones['p2:hand']) == before + int(draws)
    roundtrip(s)

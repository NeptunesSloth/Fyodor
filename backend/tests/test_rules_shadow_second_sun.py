"""CR 500.8: enchanted player gets the additional beginning, independent of Aura controller."""
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
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/shadow_second_sun_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


NAME = 'Shadow of the Second Sun'


def setup(cards):
    from tests.game_helpers import act
    from tests.test_rules_designations import put
    from tests.test_rules_shared_damage_choices import table
    from tests.test_rules_wave30m_durations import to_phase

    s = table(cards, [NAME], ['Sol Ring', 'Phyrexian Arena'], [])
    source = put(s, NAME, 'battlefield')
    act(s, 'p1', type='attach', card_ids=[source.id], to='p2')
    to_phase(s, 'main1', turn=4)
    rock = put(s, 'Sol Ring', 'battlefield', 'p2')
    put(s, 'Phyrexian Arena', 'battlefield', 'p2')
    return s, source, rock


def test_shadow_is_full(cards):
    assert coverage.of_card_data(cards.resolve(NAME)).level == 'FULL'


def test_aura_controllers_postcombat_does_not_add_beginning(cards):
    from tests.test_rules_conditionals import settle
    from tests.test_rules_designations import roundtrip
    from tests.test_rules_wave30m_durations import to_phase

    s, _, _ = setup(cards)
    to_phase(s, 'main2', turn=4)
    settle(s)
    assert not s.state.rules.extra_phases
    roundtrip(s)


@pytest.mark.parametrize('source_leaves', [False, True])
def test_enchanted_player_gets_saved_beginning_even_after_aura_leaves(cards, source_leaves):
    from tests.game_helpers import act
    from tests.test_rules_conditionals import settle
    from tests.test_rules_designations import roundtrip
    from tests.test_rules_wave30m_durations import to_phase

    s, source, rock = setup(cards)
    to_phase(s, 'main2', turn=5)
    settle(s)
    assert source.controller == 'p1' and source.attached_player == 'p2'
    assert s.state.rules.extra_phases == ['untap', 'end']
    act(s, 'p2', type='tap', card_ids=[rock.id], tapped=True)
    before = {p: len(s.state.zones[f'{p}:hand']) for p in ['p1', 'p2']}
    life = s.state.players['p2'].life
    if source_leaves:
        act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'exile'})
    roundtrip(s)
    to_phase(s, 'end', turn=5)
    settle(s)
    assert not s.state.cards[rock.id].tapped
    assert len(s.state.zones['p2:hand']) == before['p2'] + 2
    assert len(s.state.zones['p1:hand']) == before['p1']
    assert s.state.players['p2'].life == life - 1
    assert s.state.turn.number == 5 and s.state.turn.active_player == 'p2'
    roundtrip(s)

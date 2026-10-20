"""CR 702.29f: cycling prohibitions include typecycling and all players."""
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
from tests.test_rules_bandmate_references import mana, wait_priority
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/cycling_prohibitions_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()



def test_stabilizer_is_full(cards):
    assert coverage.of_card_data(cards.resolve('Stabilizer')).level == 'FULL'


@pytest.mark.parametrize('pid', ['p1', 'p2', 'p3'])
@pytest.mark.parametrize('name', ['Remote Isle', 'Ash Barrens'])
def test_stabilizer_prevents_cycling_without_discard_or_payment_for_every_player(cards, pid, name):
    from app.game.errors import ActionError
    from tests.test_rules_wave7b_activation import ability_index

    s = table(cards, ['Stabilizer', name], [name], [name])
    source = put(s, 'Stabilizer', 'battlefield')
    cycling_card = put(s, name, 'hand', pid)
    wait_priority(s, pid)
    mana(s, pid, C=2)
    index = ability_index(s, cycling_card, 'Cycling' if name == 'Remote Isle' else 'cycling')
    with pytest.raises(ActionError, match="can't cycle"):
        act(s, pid, type='activate_ability', card_id=cycling_card.id, ability=index)
    assert s.state.cards[cycling_card.id].zone == f'{pid}:hand' and not s.state.zones.get('stack')
    roundtrip(s)
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'graveyard'})
    act(s, pid, type='activate_ability', card_id=cycling_card.id, ability=index)
    assert s.state.cards[cycling_card.id].zone == f'{pid}:graveyard'
    settle(s)
    d = s.state.rules.decision
    if d:
        act(s, d.player, type='choose', decision_id=d.id, option_ids=[d.options[0].id])
        settle(s)
    roundtrip(s)


def test_stabilizer_does_not_stop_transmute_or_other_activated_abilities(cards):
    from tests.test_rules_wave7b_activation import ability_index

    s = table(cards, ['Stabilizer', 'Dimir House Guard', 'Sol Ring'], [], [])
    put(s, 'Stabilizer', 'battlefield')
    ring = put(s, 'Sol Ring', 'battlefield')
    guard = put(s, 'Dimir House Guard', 'hand')
    act(s, 'p1', type='activate_ability', card_id=ring.id, ability=0)
    assert s.state.cards[ring.id].tapped
    mana(s, B=2)
    act(s, 'p1', type='activate_ability', card_id=guard.id, ability=ability_index(s, guard, 'Transmute'))
    settle(s)
    d = s.state.rules.decision
    if d:
        act(s, d.player, type='choose', decision_id=d.id, option_ids=[])
        settle(s)
    assert s.state.cards[guard.id].zone == 'p1:graveyard'
    roundtrip(s)


def test_an_already_activated_cycle_resolves_after_stabilizer_enters(cards):
    from tests.test_rules_wave7b_activation import ability_index

    s = table(cards, ['Stabilizer', 'Remote Isle'], [], [])
    cycling_card = put(s, 'Remote Isle', 'hand')
    mana(s, C=2)
    act(s, 'p1', type='activate_ability', card_id=cycling_card.id, ability=ability_index(s, cycling_card, 'Cycling'))
    put(s, 'Stabilizer', 'battlefield')
    before = len(s.state.zones['p1:hand'])
    settle(s)
    assert len(s.state.zones['p1:hand']) == before + 1
    roundtrip(s)

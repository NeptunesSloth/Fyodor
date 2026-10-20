"""CR 115.6, 608.2b/c, 701.65: protect an optional target, airbend the complement."""
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
from tests.test_rules_conditionals import until_asked
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

NAME = "Avatar's Wrath"


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    data = json.loads((Path(__file__).parent / 'fixtures/chosen_airbend_complement_cards.json').read_text())
    for i, c in enumerate(data):
        base[c['name']] = card(c['name'], set_code='cac', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards):
    s = table(cards, [NAME, 'Grizzly Bears'], ['Llanowar Elves', 'Slippery Bogle', 'Swords to Plowshares'])
    source = put(s, NAME, 'hand')
    protected = put(s, 'Grizzly Bears', 'battlefield')
    victims = [put(s, n, 'battlefield', 'p2') for n in ['Llanowar Elves', 'Slippery Bogle']]
    mana(s, W=4)
    return s, source, protected, victims


def cast(s, source, protected=()):
    act(s, 'p1', type='cast_spell', card_id=source.id,
        targets=[c.id for c in protected], target_counts=[len(protected)])


def test_full(cards):
    assert coverage.of_card_data(cards.resolve(NAME)).level == 'FULL'


@pytest.mark.parametrize('keep', [False, True])
def test_optional_target_and_untargeted_hexproof_complement(cards, keep):
    s, source, protected, victims = setup(cards)
    cast(s, source, [protected] if keep else [])
    settle(s)
    assert s.state.cards[source.id].zone == 'p1:exile'
    assert s.state.cards[protected.id].zone == ('p1:battlefield' if keep else 'p1:exile')
    assert all(s.state.cards[c.id].zone == 'p2:exile' for c in victims)
    assert {p.card for p in s.state.rules.permissions if p.alt_mana == '{2}'} == {
        c.id for c in victims + ([] if keep else [protected])}
    roundtrip(s)


def test_opponents_hexproof_cannot_be_protected_by_targeting(cards):
    s, source, _, victims = setup(cards)
    with pytest.raises(ActionError):
        cast(s, source, [victims[1]])
    assert s.state.cards[source.id].zone == 'p1:hand'
    assert all(s.state.cards[c.id].zone == 'p2:battlefield' for c in victims)
    roundtrip(s)


def test_losing_the_only_target_stops_all_instructions(cards):
    s, source, protected, victims = setup(cards)
    act(s, 'p1', type='set_prefs', hold_priority=True)
    cast(s, source, [protected])
    wait_priority(s, 'p2')
    removal = put(s, 'Swords to Plowshares', 'hand', 'p2')
    mana(s, 'p2', W=1)
    act(s, 'p2', type='cast_spell', card_id=removal.id, targets=[protected.id])
    settle(s)
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    assert all(s.state.cards[c.id].zone == 'p2:battlefield' for c in victims)
    assert not any(p.alt_mana == '{2}' for p in s.state.rules.permissions)
    roundtrip(s)


def test_airbend_permission_waits_until_opponents_cast_lock_expires(cards):
    s, source, protected, victims = setup(cards)
    cast(s, source, [protected])
    settle(s)
    to_phase(s, 'main1', turn=2)
    mana(s, 'p2', C=2)
    with pytest.raises(ActionError):
        act(s, 'p2', type='cast_spell', card_id=victims[0].id)
    assert s.state.cards[victims[0].id].zone == 'p2:exile'
    to_phase(s, 'main1', turn=5)
    mana(s, 'p2', C=2)
    act(s, 'p2', type='cast_spell', card_id=victims[0].id)
    settle(s)
    assert s.state.cards[victims[0].id].zone == 'p2:battlefield'
    roundtrip(s)


def test_protected_target_is_announced_before_costs(cards):
    s, source, _, _ = setup(cards)
    act(s, 'p1', type='cast_spell', card_id=source.id)
    d = until_asked(s)
    assert d is not None and d.min_choices == 0 and d.max_choices == 1
    assert s.state.cards[source.id].zone == 'p1:hand'
    roundtrip(s)

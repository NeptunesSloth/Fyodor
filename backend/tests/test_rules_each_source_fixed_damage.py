"""CR 120.3, 508.3a, 608.2h: each matching permanent deals fixed damage."""
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
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/each_source_fixed_damage_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()



NAME = 'Sarkhan the Masterless'


def test_sarkhan_is_full(cards):
    assert coverage.of_card_data(cards.resolve(NAME)).level == 'FULL'


def setup(cards, *, dragons=2, lifelink=False):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_conditionals import settle
    from tests.test_rules_designations import put
    from tests.test_rules_shared_damage_choices import table
    from tests.test_rules_wave7b_activation import ability_index

    s = table(cards, [NAME, 'Shivan Dragon', 'Dragon Whelp', 'Basilisk Collar', 'Murder'],
              ['Shivan Dragon', 'Grizzly Bears', 'Murder'], ['Shivan Dragon'])
    source = put(s, NAME, 'battlefield')
    act(s, 'p1', type='set_counter', card_id=source.id, kind='loyalty', value=5)
    sources = [put(s, n, 'battlefield') for n in ['Shivan Dragon', 'Dragon Whelp'][:dragons]]
    put(s, 'Shivan Dragon', 'battlefield', pid='p3')
    attacker = put(s, 'Shivan Dragon', 'battlefield', pid='p2')
    if lifelink:
        collar = put(s, 'Basilisk Collar', 'battlefield')
        mana(s, C=2)
        act(s, 'p1', type='activate_ability', card_id=collar.id, ability=ability_index(s, collar, 'Equip {2}'), targets=[sources[0].id])
        settle(s)
    return s, source, sources, attacker


def attack(s, source, attackers, *, defender='p1'):
    from tests.game_helpers import act
    from tests.test_rules_wave30m_durations import to_phase

    to_phase(s, 'declare_attackers', turn=2)
    act(s, 'p2', type='declare_attackers', attackers=[{'card_id': a.id, 'target': source.id if defender == 'walker' else defender} for a in attackers])


@pytest.mark.parametrize('dragons', [0, 1, 2])
@pytest.mark.parametrize('defender', ['p1', 'walker', 'p3'])
def test_trigger_counts_current_own_sources_for_player_and_planeswalker_attacks(cards, dragons, defender):
    from tests.test_rules_conditionals import settle
    from tests.test_rules_designations import roundtrip

    s, source, _, attacker = setup(cards, dragons=dragons)
    attack(s, source, [attacker], defender=defender)
    settle(s)
    assert s.state.cards[attacker.id].damage == (dragons if defender != 'p3' else 0)
    roundtrip(s)


def test_each_dragon_is_actual_damage_source_with_its_own_lifelink(cards):
    from tests.test_rules_conditionals import settle
    from tests.test_rules_designations import roundtrip

    s, source, _, attacker = setup(cards, lifelink=True)
    life = s.state.players['p1'].life
    attack(s, source, [attacker])
    settle(s)
    assert s.state.cards[attacker.id].zone == 'p2:graveyard'  # the collared Dragon has deathtouch
    assert s.state.players['p1'].life == life + 1
    roundtrip(s)


def test_leaving_source_is_excluded_when_the_attack_trigger_resolves(cards):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana, wait_priority
    from tests.test_rules_conditionals import settle
    from tests.test_rules_designations import put, roundtrip

    s, source, dragons, attacker = setup(cards)
    attack(s, source, [attacker])
    wait_priority(s, 'p1')
    murder = put(s, 'Murder', 'hand')
    mana(s, C=1, B=2)
    act(s, 'p1', type='cast_spell', card_id=murder.id, targets=[dragons[0].id])
    roundtrip(s)
    settle(s)
    assert s.state.cards[dragons[0].id].zone == 'p1:graveyard'
    assert s.state.cards[attacker.id].damage == 1
    roundtrip(s)


def test_each_attacker_triggers_separately_and_damage_precedes_blockers(cards):
    from tests.test_rules_conditionals import settle
    from tests.test_rules_designations import put, roundtrip

    s, source, _, attacker = setup(cards)
    bear = put(s, 'Grizzly Bears', 'battlefield', pid='p2')
    attack(s, source, [attacker, bear])
    settle(s)
    assert s.state.cards[attacker.id].damage == 2
    assert s.state.cards[bear.id].zone == 'p2:graveyard'
    roundtrip(s)

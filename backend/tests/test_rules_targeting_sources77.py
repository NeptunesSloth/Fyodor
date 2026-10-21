"""Native saddle payment, designation, contributors and frozen counter cohorts."""
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
from tests.test_rules_bandmate_references import mana
from tests.test_rules_declaration_requirements33 import start
from tests.test_rules_designations import put
from tests.test_rules_library_look import settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave6c_tokens_pumps import chars

NAMES = ['Professor Hojo', 'Leyline of Combustion', 'Mirror-Shield Hoplite']
DATA = json.loads((Path(__file__).parent / 'fixtures/targeting_sources77_cards.json').read_text())


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



@pytest.mark.parametrize('name', NAMES)
def test_canonical_whole_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


def setup(cards, name):
    names = [c['name'] for c in DATA] + ['Grizzly Bears', 'Llanowar Elves']
    s = table(cards, names, names, names)
    source = put(s, name, 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    elf = put(s, 'Llanowar Elves', 'battlefield')
    start(s)
    act(s, 'p1', type='set_prefs', hold_priority=True)
    return s, source, bear, elf


def test_hojo_reduced_first_equip_and_once_draw(cards):
    s, source, bear, elf = setup(cards, 'Professor Hojo')
    dagger = put(s, 'Silver-Inlaid Dagger', 'battlefield')
    before = len(s.state.zones['p1:hand'])
    act(s, 'p1', type='activate_ability', card_id=dagger.id, ability=2, targets=[bear.id], sources=[])
    settle(s)
    assert len(s.state.zones['p1:hand']) == before + 1
    mana(s, C=2)
    act(s, 'p1', type='activate_ability', card_id=dagger.id, ability=2, targets=[elf.id], sources=[])
    settle(s)
    assert len(s.state.zones['p1:hand']) == before + 1
    assert dagger.attached_to == elf.id


def test_hojo_spell_target_negative(cards):
    from tests.test_rules_trigger_upkeep_comparison75 import cast
    s, source, bear, elf = setup(cards, 'Professor Hojo')
    before = len(s.state.zones['p1:hand'])
    cast(s, 'Giant Growth', {'G':1}, [bear.id])
    # The spell is moved into hand from the deck by the helper, then spent.
    assert len(s.state.zones['p1:hand']) == before


def test_leyline_mixed_player_permanent_targets_aggregate_once(cards):
    from tests.test_rules_trigger_upkeep_comparison75 import cast
    s, source, bear, elf = setup(cards, 'Leyline of Combustion')
    cast(s, 'Electrolyze', {'C':1, 'U':1, 'R':1}, ['p1', bear.id], pid='p2', target_counts=[2], division=[1,1])
    assert s.state.players['p2'].life == 38
    assert s.state.players['p1'].life == 39


def test_hoplite_actual_backup_copies_and_grants_keywords(cards):
    from tests.test_rules_trigger_upkeep_comparison75 import cast
    s, source, bear, elf = setup(cards, 'Mirror-Shield Hoplite')
    cast(s, 'Boon-Bringer Valkyrie', {'C':3, 'W':2})
    d = s.state.rules.decision
    assert d is not None
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[bear.id])
    settle(s)
    d = s.state.rules.decision
    assert d is not None
    # Keep the original backup target for the copy.
    act(s, d.player, type='choose', decision_id=d.id, option_ids=['keep'])
    settle(s)
    assert bear.counters.get('+1/+1',0) == 2
    assert {'flying','first strike','lifelink'} <= chars(s, bear).keywords

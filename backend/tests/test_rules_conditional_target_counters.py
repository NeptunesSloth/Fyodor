"""CR 115.1c, 608.2b/c: announced commander target, independent counter conditions."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, deck, enable
from tests.test_rules_bandmate_references import mana, wait_priority
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_wave30m_durations import to_phase


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    data = json.loads((Path(__file__).parent / 'fixtures/conditional_target_counter_cards.json').read_text())
    for i, c in enumerate(data):
        base[c['name']] = card(c['name'], set_code='ctc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards, commander='Krenko, Mob Boss'):
    a = deck(cards, commander, [(1, 'Forge of Heroes'), (1, 'Grizzly Bears'), (20, 'Forest')])
    b = deck(cards, 'Atraxa, Praetors\' Voice', [(1, 'Swords to Plowshares'), (1, 'Song of the Dryads'), (20, 'Island')])
    s = GameSession(enable(new_game([PlayerSetup('Alice', cards=a), PlayerSetup('Bob', cards=b)], shuffle=False)), cards=cards)
    act(s, 'p1', type='pass_priority')
    for pid in ['p1', 'p2']:
        act(s, pid, type='set_prefs', response='on')
    to_phase(s, 'main1')
    source = put(s, 'Forge of Heroes', 'battlefield')
    return s, source


def enter_commander(s, name='Krenko, Mob Boss'):
    c = next(c for c in s.state.cards.values() if c.name == name)
    mana(s, C=2, R=2)
    act(s, 'p1', type='cast_spell', card_id=c.id)
    settle(s)
    return s.state.cards[c.id]


def activate(s, source, target):
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=1, targets=[target.id])


def test_forge_is_full(cards):
    assert coverage.of_card_data(cards.resolve('Forge of Heroes')).level == 'FULL'


@pytest.mark.parametrize('name,kind,before', [('Krenko, Mob Boss', '+1/+1', 0), ('Daretti, Scrap Savant', 'loyalty', 3)])
def test_new_commander_gets_only_matching_counter(cards, name, kind, before):
    s, source = setup(cards, name)
    target = enter_commander(s, name)
    assert target.counters.get(kind, 0) == before
    activate(s, source, target)
    assert s.state.cards[source.id].tapped
    assert not target.counters.get('+1/+1' if kind == 'loyalty' else 'loyalty', 0)
    settle(s)
    assert s.state.cards[target.id].counters[kind] == before + 1
    assert not s.state.cards[target.id].counters.get('+1/+1' if kind == 'loyalty' else 'loyalty', 0)
    roundtrip(s)


def test_noncommander_rejected_without_paying_tap(cards):
    s, source = setup(cards)
    target = put(s, 'Grizzly Bears', 'battlefield')
    with pytest.raises(ActionError):
        activate(s, source, target)
    assert not s.state.cards[source.id].tapped
    roundtrip(s)


def test_last_turns_commander_is_not_legal(cards):
    s, source = setup(cards)
    target = enter_commander(s)
    to_phase(s, 'main1', turn=2)
    wait_priority(s, 'p1')
    with pytest.raises(ActionError):
        activate(s, source, target)
    assert not s.state.cards[source.id].tapped
    roundtrip(s)


def test_removed_target_fizzles_without_counters_on_exiled_card(cards):
    s, source = setup(cards)
    target = enter_commander(s)
    activate(s, source, target)
    wait_priority(s, 'p2')
    removal = put(s, 'Swords to Plowshares', 'hand', 'p2')
    mana(s, 'p2', W=1)
    act(s, 'p2', type='cast_spell', card_id=removal.id, targets=[target.id])
    settle(s)
    # Commander-zone replacement is a separate optional choice; either destination
    # is a new object and cannot receive the announced battlefield counters.
    assert not s.state.cards[target.id].zone.endswith(':battlefield')
    assert not s.state.cards[target.id].counters
    roundtrip(s)


def test_target_remains_legal_as_land_but_neither_counter_condition_matches(cards):
    from app.rules.plan import Plan

    s, source = setup(cards)
    to_phase(s, 'main1', turn=2)
    opponent = next(c for c in s.state.cards.values() if c.name == "Atraxa, Praetors' Voice")
    mana(s, 'p2', G=1, W=1, U=1, B=1)
    act(s, 'p2', type='cast_spell', card_id=opponent.id)
    settle(s)
    aura = put(s, 'Song of the Dryads', 'hand', 'p2')
    mana(s, 'p2', G=1, C=2)
    act(s, 'p2', type='cast_spell', card_id=aura.id, targets=[opponent.id])
    settle(s)
    wait_priority(s, 'p1')
    activate(s, source, opponent)
    settle(s)
    assert Plan.view(s.state, 'p1', s.cards).ch(s.state.cards[opponent.id]).types == frozenset({'Land'})
    assert not s.state.cards[opponent.id].counters
    roundtrip(s)

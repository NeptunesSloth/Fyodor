"""CR 101.4, 118.12: each eligible player chooses before shared damage costs are paid."""
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
from tests.test_rules_designations import put, roundtrip, settle


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/shared_damage_choices_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()



@pytest.mark.parametrize('name', ['Browbeat', 'Book Burning', 'Breaking Point', 'Vexing Devil', 'Longhorn Firebeast'])
def test_shared_damage_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


def table(cards, a=(), b=(), c=()):
    from tests.test_rules_wave30m_durations import three

    s = three(cards, a, b, c)
    for pid in ['p1', 'p2', 'p3']:
        act(s, pid, type='set_prefs', response='on')
    return s


def cast(s, name, targets=()):
    source = put(s, name, 'hand')
    mana = {'Browbeat': {'C': 2, 'R': 1}, 'Book Burning': {'C': 1, 'R': 1},
            'Breaking Point': {'C': 1, 'R': 2}, 'Vexing Devil': {'R': 1},
            'Longhorn Firebeast': {'C': 2, 'R': 1}}[name]
    act(s, 'p1', type='add_mana', player='p1', mana=mana)
    act(s, 'p1', type='cast_spell', card_id=source.id, targets=list(targets))
    settle(s)
    return source


def answer(s, order, accepted):
    for pid in order:
        d = s.state.rules.decision
        assert d is not None and d.player == pid and d.resume['step'] == 'shared_damage_choice'
        assert all(p.life == 40 for p in s.state.players.values())
        roundtrip(s)
        act(s, pid, type='choose', decision_id=d.id, option_ids=['pay' if pid in accepted else 'decline'])
        settle(s)
    assert s.state.rules.decision is None
    roundtrip(s)


@pytest.mark.parametrize('accepted', [[], ['p1'], ['p2'], ['p1', 'p2', 'p3']])
def test_browbeat_offers_every_player_and_draws_only_if_everyone_declines(cards, accepted):
    s = table(cards, ['Browbeat'])
    before = len(s.state.zones['p3:hand'])
    cast(s, 'Browbeat', ['p3'])
    answer(s, ['p1', 'p2', 'p3'], accepted)
    assert len(s.state.zones['p3:hand']) == before + (0 if accepted else 3)
    assert {pid: p.life for pid, p in s.state.players.items()} == {
        pid: 40 - (5 if pid in accepted else 0) for pid in ['p1', 'p2', 'p3']}


@pytest.mark.parametrize('accepted', [[], ['p2'], ['p1', 'p2', 'p3']])
def test_book_burning_mills_only_if_no_player_accepts_damage(cards, accepted):
    s = table(cards, ['Book Burning'])
    before = len(s.state.zones['p3:library'])
    cast(s, 'Book Burning', ['p3'])
    answer(s, ['p1', 'p2', 'p3'], accepted)
    assert len(s.state.zones['p3:library']) == before - (0 if accepted else 6)
    assert len(s.state.zones['p3:graveyard']) == (0 if accepted else 6)
    assert all(p.life == 40 - (6 if pid in accepted else 0) for pid, p in s.state.players.items())


@pytest.mark.parametrize('name,damage', [('Vexing Devil', 4), ('Longhorn Firebeast', 5)])
@pytest.mark.parametrize('accepted', [[], ['p2'], ['p2', 'p3']])
def test_enter_trigger_offers_all_opponents_and_sacrifices_if_any_accept(cards, name, damage, accepted):
    s = table(cards, [name])
    source = cast(s, name)
    answer(s, ['p2', 'p3'], accepted)
    assert source.id in s.state.zones['p1:graveyard' if accepted else 'p1:battlefield']
    assert all(p.life == 40 - (damage if pid in accepted else 0) for pid, p in s.state.players.items())


def test_preventing_all_damage_does_not_undo_the_choice(cards):
    s = table(cards, ['Browbeat'], ['Solitary Confinement'])
    put(s, 'Solitary Confinement', 'battlefield', 'p2')
    before = len(s.state.zones['p3:hand'])
    cast(s, 'Browbeat', ['p3'])
    answer(s, ['p1', 'p2', 'p3'], ['p2'])
    assert s.state.players['p2'].life == 40
    assert len(s.state.zones['p3:hand']) == before


def test_players_cannot_activate_mana_abilities_during_shared_choices(cards):
    s = table(cards, ['Browbeat'], ['Sol Ring'])
    ring = put(s, 'Sol Ring', 'battlefield', 'p2')
    cast(s, 'Browbeat', ['p3'])
    d = s.state.rules.decision
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=['pay'])
    before = s.state.model_dump(mode='json')
    with pytest.raises(ActionError):
        act(s, 'p2', type='activate_ability', card_id=ring.id, ability=0)
    assert s.state.model_dump(mode='json') == before
    for pid in ['p2', 'p3']:
        d = s.state.rules.decision
        act(s, pid, type='choose', decision_id=d.id, option_ids=['decline'])
    settle(s)
    assert s.state.players['p1'].life == 35
    roundtrip(s)


@pytest.mark.parametrize('accepted', [[], ['p2']])
def test_breaking_point_destruction_cannot_be_regenerated(cards, accepted):
    s = table(cards, ['Breaking Point', 'Drudge Skeletons'], c=['Grizzly Bears'])
    skeleton = put(s, 'Drudge Skeletons', 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield', 'p3')
    act(s, 'p1', type='add_mana', player='p1', mana={'B': 1})
    act(s, 'p1', type='activate_ability', card_id=skeleton.id, ability=0)
    settle(s)
    cast(s, 'Breaking Point')
    answer(s, ['p1', 'p2', 'p3'], accepted)
    assert skeleton.id in s.state.zones['p1:battlefield' if accepted else 'p1:graveyard']
    assert bear.id in s.state.zones['p3:battlefield' if accepted else 'p3:graveyard']
    assert s.state.players['p2'].life == (34 if accepted else 40)


@pytest.mark.parametrize('returned', [False, True])
def test_devil_trigger_uses_departed_source_without_sacrificing_a_new_object(cards, returned):
    s = table(cards, ['Vexing Devil'])
    source = put(s, 'Vexing Devil', 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana={'R': 1})
    act(s, 'p1', type='cast_spell', card_id=source.id, targets=[])
    for _ in range(10):
        if source.id in s.state.zones['p1:battlefield']:
            break
        act(s, s.state.rules.priority, type='pass_priority')
    assert source.id in s.state.zones['p1:battlefield'] and s.state.zones['stack']
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'graveyard'})
    if returned:
        act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'battlefield'})
    settle(s)
    answer(s, ['p2', 'p3'], ['p2'])
    assert s.state.players['p2'].life == 36
    assert source.id in s.state.zones['p1:battlefield' if returned else 'p1:graveyard']
    roundtrip(s)


def test_shared_choices_use_active_player_first_in_multiplayer(cards):
    from tests.test_rules_wave30m_durations import to_phase

    s = table(cards, b=['Browbeat'])
    to_phase(s, 'main1', turn=2)
    source = put(s, 'Browbeat', 'hand', 'p2')
    act(s, 'p2', type='add_mana', player='p2', mana={'C': 2, 'R': 1})
    act(s, 'p2', type='cast_spell', card_id=source.id, targets=['p1'])
    settle(s)
    answer(s, ['p2', 'p3', 'p1'], ['p3'])
    assert s.state.players['p3'].life == 35
    roundtrip(s)


def test_unknown_shared_damage_continuations_stay_manual():
    from app.rules import scripts

    assert scripts.parse_effects('Any player may have ~ deal 5 damage to them. If no one does, frobnicate the battlefield.') is None
    assert scripts.parse_effects('Any player may have it deal 5 damage to them. If no one does, draw a card.') is None

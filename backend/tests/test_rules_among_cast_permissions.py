"""CR 601.3, 609.4b, 611.2a: typed, limited casting permissions over exiled cards."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import coverage
from app.rules.mana_units import visible_pool
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_designations import build, put, roundtrip, settle


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/among_cast_permissions_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='acp', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


@pytest.mark.parametrize('name', ['Stolen Strategy', 'Laughing Jasper Flint', "Chandra, Hope's Beacon"])
def test_among_cast_permission_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


def theft(cards, name, spell_name):
    from tests.test_rules_designations import pick
    from tests.test_rules_permissions import put as place
    from tests.test_rules_wave34b_activated import stops, to_phase

    s = build(cards, [name], bob=((1, spell_name), (1, 'Grizzly Bears'), (10, 'Island')))
    source = put(s, name, 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield', pid='p2')
    stops(s)
    to_phase(s, 'end', turn=2)
    spell = place(s, spell_name, 'library', pid='p2', position='top')
    to_phase(s, 'upkeep', turn=3)
    settle(s)
    if s.state.rules.decision is not None:
        pick(s, ['p2'])
        settle(s)
    assert s.state.cards[spell.id].zone == 'p2:exile'
    assert len(s.state.zones['p2:exile']) == 1
    to_phase(s, 'main1', turn=3)
    roundtrip(s)
    return s, source, s.state.cards[spell.id], bear


@pytest.mark.parametrize('name,allowed', [('Stolen Strategy', False), ('Laughing Jasper Flint', True)])
def test_any_color_and_any_type_are_different_for_colorless_costs(cards, name, allowed):
    from app.rules import casting

    s, _, spell, bear = theft(cards, name, 'Spatial Contortion')
    act(s, 'p1', type='add_mana', player='p1', mana={'W': 2})
    assert bool(casting.castable(s.state, 'p1', s.state.cards[spell.id], cards)) == allowed
    if allowed:
        act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[bear.id])
        settle(s)
        assert s.state.cards[bear.id].zone == 'p2:graveyard'
    else:
        before = s.state.model_dump(mode='json')
        with pytest.raises(ActionError):
            act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[bear.id])
        assert before == s.state.model_dump(mode='json')
    roundtrip(s)


@pytest.mark.parametrize('name', ['Stolen Strategy', 'Laughing Jasper Flint'])
def test_cast_permission_does_not_allow_playing_exiled_lands(cards, name):
    s, _, land, _ = theft(cards, name, 'Forest')
    with pytest.raises(ActionError):
        act(s, 'p1', type='play_land', card_id=land.id)
    roundtrip(s)


@pytest.mark.parametrize('name', ['Stolen Strategy', 'Laughing Jasper Flint'])
def test_temporary_permission_survives_source_leaving_but_is_only_for_its_controller(cards, name):
    from app.rules import casting

    s, source, spell, _ = theft(cards, name, 'Lightning Bolt')
    act(s, 'p2', type='add_mana', player='p2', mana={'R': 1})
    assert not casting.castable(s.state, 'p2', s.state.cards[spell.id], cards, check_priority=False)
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'graveyard'})
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 1})
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=['p2'])
    settle(s)
    assert s.state.players['p2'].life == 37 and s.state.cards[spell.id].zone == 'p2:graveyard'
    roundtrip(s)


@pytest.mark.parametrize('name', ['Stolen Strategy', 'Laughing Jasper Flint'])
def test_end_of_turn_permission_expires(cards, name):
    from app.rules import casting
    from tests.test_rules_wave34b_activated import to_phase

    s, _, spell, _ = theft(cards, name, 'Lightning Bolt')
    to_phase(s, 'main1', turn=4)
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 1, 'R': 1})
    assert not casting.castable(s.state, 'p1', s.state.cards[spell.id], cards, check_priority=False)
    assert not any(p.card == spell.id for p in s.state.rules.permissions)
    roundtrip(s)


def chandra_exile(cards):
    from tests.test_rules_permissions import put as place
    from tests.test_rules_wave34b_activated import stops

    names = ['Dark Ritual', 'Harmonize', 'Lightning Bolt', 'Sol Ring', 'Forest']
    s = build(cards, ["Chandra, Hope's Beacon", *names])
    source = put(s, "Chandra, Hope's Beacon", 'battlefield')
    act(s, 'p1', type='set_counter', card_id=source.id, kind='loyalty', value=5)
    stops(s)
    exiled = {}
    for name in reversed(names):
        exiled[name] = place(s, name, 'library', position='top').id
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=2)
    settle(s)
    assert all(s.state.cards[c].zone == 'p1:exile' for c in exiled.values())
    assert s.state.cards[source.id].counters['loyalty'] == 6
    roundtrip(s)
    return s, source, exiled


def test_chandra_grants_one_instant_or_sorcery_across_all_five_cards(cards):
    s, _, exiled = chandra_exile(cards)
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 1, 'B': 1, 'G': 2})
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=exiled['Sol Ring'])
    with pytest.raises(ActionError):
        act(s, 'p1', type='play_land', card_id=exiled['Forest'])
    act(s, 'p1', type='cast_spell', card_id=exiled['Dark Ritual'])
    settle(s)
    # Chandra's existing first-spell trigger copies the Ritual; copies aren't cast.
    assert visible_pool(s.state, 'p1').get('B', 0) == 6
    before = s.state.model_dump(mode='json')
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=exiled['Harmonize'])
    assert before == s.state.model_dump(mode='json')
    roundtrip(s)


def test_chandra_permission_lasts_through_the_next_turn_and_expires_after_it(cards):
    from app.rules import casting
    from tests.test_rules_wave34b_activated import to_phase

    s, _, exiled = chandra_exile(cards)
    to_phase(s, 'main1', turn=3)
    act(s, 'p1', type='add_mana', player='p1', mana={'B': 1})
    act(s, 'p1', type='cast_spell', card_id=exiled['Dark Ritual'])
    settle(s)
    assert visible_pool(s.state, 'p1').get('B', 0) == 6
    to_phase(s, 'main1', turn=4)
    act(s, 'p1', type='add_mana', player='p1', mana={'R': 1})
    assert not casting.castable(s.state, 'p1', s.state.cards[exiled['Lightning Bolt']], cards, check_priority=False)
    assert not any(p.card in exiled.values() for p in s.state.rules.permissions)
    roundtrip(s)


def test_flint_counts_a_borrowed_creature_as_an_outlaw_once(cards):
    from tests.test_rules_designations import pick
    from tests.test_rules_permissions import put as place
    from tests.test_rules_wave34b_activated import stops, to_phase

    s = build(cards, ['Laughing Jasper Flint'], bob=((1, 'Lightning Bolt'), (1, 'Forest'), (1, 'Grizzly Bears'), (10, 'Island')))
    put(s, 'Laughing Jasper Flint', 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield', pid='p2')
    act(s, 'p1', type='set_controller', card_ids=[bear.id], player='p1')
    stops(s)
    to_phase(s, 'end', turn=2)
    forest = place(s, 'Forest', 'library', pid='p2', position='top')
    bolt = place(s, 'Lightning Bolt', 'library', pid='p2', position='top')
    to_phase(s, 'upkeep', turn=3)
    settle(s)
    if s.state.rules.decision:
        pick(s, ['p2'])
        settle(s)
    assert set(s.state.zones['p2:exile']) == {forest.id, bolt.id}
    assert len([p for p in s.state.rules.permissions if p.card in (forest.id, bolt.id)]) == 2
    roundtrip(s)


def test_stolen_strategy_grants_casting_cards_from_multiple_opponents(cards):
    from app.game.factory import PlayerSetup, new_game
    from app.game.session import GameSession
    from tests.game_helpers import deck, enable
    from tests.test_rules_permissions import put as place
    from tests.test_rules_wave34b_activated import stops, to_phase

    lists = [deck(cards, 'Krenko, Mob Boss', [(1, 'Stolen Strategy'), (12, 'Forest')]),
             deck(cards, 'Krenko, Mob Boss', [(1, 'Lightning Bolt'), (12, 'Island')]),
             deck(cards, 'Krenko, Mob Boss', [(1, 'Dark Ritual'), (12, 'Island')])]
    s = GameSession(enable(new_game([PlayerSetup(n, cards=d) for n, d in zip(['A', 'B', 'C'], lists, strict=True)], shuffle=False)), cards=cards)
    act(s, 'p1', type='pass_priority')
    put(s, 'Stolen Strategy', 'battlefield')
    stops(s)
    to_phase(s, 'end', turn=3)
    bolt = place(s, 'Lightning Bolt', 'library', pid='p2', position='top')
    ritual = place(s, 'Dark Ritual', 'library', pid='p3', position='top')
    to_phase(s, 'upkeep', turn=4)
    settle(s)
    to_phase(s, 'main1', turn=4)
    assert s.state.cards[bolt.id].zone == 'p2:exile' and s.state.cards[ritual.id].zone == 'p3:exile'
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 1})
    act(s, 'p1', type='cast_spell', card_id=ritual.id)
    settle(s)
    act(s, 'p1', type='cast_spell', card_id=bolt.id, targets=['p2'])
    settle(s)
    assert s.state.players['p2'].life == 37
    assert s.state.cards[ritual.id].zone == 'p3:graveyard' and s.state.cards[bolt.id].zone == 'p2:graveyard'
    roundtrip(s)


def test_soul_jar_links_dead_elves_and_grants_one_cast_per_paid_activation(cards):
    assert coverage.of_card_data(cards.resolve("Serpent's Soul-Jar")).level == 'FULL'
    s = build(cards, ["Serpent's Soul-Jar", 'Llanowar Elves', 'Elvish Mystic', 'Grizzly Bears', 'Day of Judgment'])
    jar = put(s, "Serpent's Soul-Jar", 'battlefield')
    elf = put(s, 'Llanowar Elves', 'battlefield')
    mystic = put(s, 'Elvish Mystic', 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    wrath = put(s, 'Day of Judgment', 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 2, 'W': 2})
    act(s, 'p1', type='cast_spell', card_id=wrath.id)
    settle(s)
    assert s.state.cards[elf.id].zone == s.state.cards[mystic.id].zone == 'p1:exile'
    assert s.state.cards[bear.id].zone == 'p1:graveyard'
    act(s, 'p1', type='activate_ability', card_id=jar.id, ability=1)
    settle(s)
    assert s.state.cards[jar.id].tapped and s.state.players['p1'].life == 38
    roundtrip(s)
    act(s, 'p1', type='add_mana', player='p1', mana={'G': 2, 'C': 2})
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=bear.id)
    act(s, 'p1', type='cast_spell', card_id=elf.id)
    settle(s)
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=mystic.id)
    act(s, 'p1', type='tap', card_ids=[jar.id], tapped=False)
    act(s, 'p1', type='activate_ability', card_id=jar.id, ability=1)
    settle(s)
    act(s, 'p1', type='cast_spell', card_id=mystic.id)
    settle(s)
    assert s.state.cards[elf.id].zone == s.state.cards[mystic.id].zone == 'p1:battlefield'
    assert s.state.players['p1'].life == 36
    roundtrip(s)

"""CR 113.6c, 613.1d/613.4b: Grist's own nonbattlefield characteristics."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import commander, coverage
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana, wait_priority
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table

NAME = 'Grist, the Hunger Tide'


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    data = json.loads((Path(__file__).parent / 'fixtures/outside_battlefield_self_cards.json').read_text())
    for i, c in enumerate(data):
        base[c['name']] = card(c['name'], set_code='obs', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def ch(s, c):
    return Plan.view(s.state, 'p1', s.cards).ch(s.state.cards[c.id])


def test_full_and_commander_eligibility(cards):
    c = cards.resolve(NAME)
    assert coverage.of_card_data(c).level == 'FULL'
    assert commander.can_be_commander(c)


def test_actual_commander_cast_enters_as_planeswalker_with_loyalty(cards):
    from app.game.factory import PlayerSetup, new_game
    from app.game.session import GameSession
    from tests.game_helpers import deck, enable

    s = GameSession(enable(new_game([
        PlayerSetup('Alice', cards=deck(cards, NAME, [(20, 'Forest')])),
        PlayerSetup('Bob', cards=deck(cards, 'Krenko, Mob Boss', [(20, 'Forest')]))], shuffle=False)), cards=cards)
    act(s, 'p1', type='pass_priority')
    for pid in ['p1', 'p2']:
        act(s, pid, type='set_prefs', response='on')
    target = next(c for c in s.state.cards.values() if c.name == NAME)
    assert target.zone == 'p1:command' and target.commander_key
    mana(s, C=1, G=1, B=1)
    act(s, 'p1', type='cast_spell', card_id=target.id)
    assert ch(s, target).types == {'Creature', 'Planeswalker'}
    settle(s)
    assert s.state.cards[target.id].zone == 'p1:battlefield'
    assert ch(s, target).types == {'Planeswalker'}
    assert s.state.cards[target.id].counters['loyalty'] == 3
    roundtrip(s)


@pytest.mark.parametrize('zone', ['hand', 'library', 'graveyard', 'exile', 'command'])
def test_nonbattlefield_zone_has_both_card_types_and_one_one(cards, zone):
    s = table(cards, [NAME])
    target = put(s, NAME, zone)
    now = ch(s, target)
    assert now.types == {'Planeswalker', 'Creature'}
    assert now.subtypes == {'Grist', 'Insect'}
    assert now.pt == (1, 1) and now.base_pt == (1, 1)
    roundtrip(s)


def test_actual_cast_is_creature_spell_then_only_planeswalker_on_battlefield(cards):
    s = table(cards, [NAME])
    target = put(s, NAME, 'hand')
    mana(s, C=1, B=1, G=1)
    act(s, 'p1', type='cast_spell', card_id=target.id)
    assert ch(s, target).types == {'Planeswalker', 'Creature'}
    assert ch(s, target).pt == (1, 1)
    settle(s)
    now = ch(s, target)
    assert now.types == {'Planeswalker'} and now.subtypes == {'Grist'}
    assert now.pt is None and s.state.cards[target.id].counters['loyalty'] == 3
    roundtrip(s)


def test_creature_counterspell_can_counter_grist(cards):
    s = table(cards, [NAME], ['Essence Scatter'])
    target = put(s, NAME, 'hand')
    mana(s, C=1, B=1, G=1)
    act(s, 'p1', type='cast_spell', card_id=target.id)
    wait_priority(s, 'p2')
    counter = put(s, 'Essence Scatter', 'hand', 'p2')
    mana(s, 'p2', C=1, U=1)
    act(s, 'p2', type='cast_spell', card_id=counter.id, targets=[target.id])
    settle(s)
    assert s.state.cards[target.id].zone == 'p1:graveyard'
    assert ch(s, target).types == {'Creature', 'Planeswalker'}
    roundtrip(s)


def test_reanimate_creature_card_enters_as_planeswalker(cards):
    s = table(cards, [NAME, 'Reanimate'])
    target = put(s, NAME, 'graveyard')
    spell = put(s, 'Reanimate', 'hand')
    mana(s, B=1)
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[target.id])
    settle(s)
    assert s.state.cards[target.id].zone == 'p1:battlefield'
    assert ch(s, target).types == {'Planeswalker'}
    assert s.state.cards[target.id].counters['loyalty'] == 3
    assert s.state.players['p1'].life == 37
    roundtrip(s)


def test_face_down_exile_lacks_own_nonbattlefield_ability(cards):
    s = table(cards, [NAME])
    target = put(s, NAME, 'exile')
    act(s, 'p1', type='face_down', card_ids=[target.id], face_down=True)
    target = next(c for c in s.state.cards.values() if c.card_id == target.card_id and c.zone == 'p1:exile')
    assert 'Planeswalker' not in ch(s, target).types
    assert not ch(s, target).abilities
    roundtrip(s)


def test_green_sun_zenith_finds_creature_card_that_enters_as_planeswalker(cards):
    s = table(cards, [NAME, "Green Sun's Zenith"])
    target = put(s, NAME, 'library')
    spell = put(s, "Green Sun's Zenith", 'hand')
    mana(s, C=3, G=1)
    act(s, 'p1', type='cast_spell', card_id=spell.id, x_value=3)
    settle(s)
    d = s.state.rules.decision
    assert d is not None and target.id in {o.id for o in d.options}, (ch(s, target), d)
    roundtrip(s)
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[target.id])
    settle(s)
    assert ch(s, target).types == {'Planeswalker'}
    assert s.state.cards[target.id].counters['loyalty'] == 3
    roundtrip(s)


def test_entry_replacements_see_future_noncreature_planeswalker(cards):
    s = table(cards, [NAME, 'Reanimate', 'Containment Priest', 'Hallowed Moonlight'])
    put(s, 'Containment Priest', 'battlefield')
    moonlight = put(s, 'Hallowed Moonlight', 'hand')
    mana(s, C=1, W=1)
    act(s, 'p1', type='cast_spell', card_id=moonlight.id)
    settle(s)
    target = put(s, NAME, 'graveyard')
    spell = put(s, 'Reanimate', 'hand')
    mana(s, B=1)
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[target.id])
    settle(s)
    assert s.state.cards[target.id].zone == 'p1:battlefield'
    assert ch(s, target).types == {'Planeswalker'}
    assert s.state.cards[target.id].counters['loyalty'] == 3
    roundtrip(s)


def test_double_major_targets_creature_spell_but_copy_enters_as_planeswalker(cards):
    s = table(cards, [NAME, 'Double Major'])
    target = put(s, NAME, 'hand')
    copy_spell = put(s, 'Double Major', 'hand')
    act(s, 'p1', type='set_prefs', hold_priority=True)
    mana(s, C=1, B=1, G=2, U=1)
    act(s, 'p1', type='cast_spell', card_id=target.id)
    act(s, 'p1', type='cast_spell', card_id=copy_spell.id, targets=[target.id])
    settle(s)
    walkers = [c for c in s.state.cards.values() if c.zone.endswith(':battlefield') and ch(s, c).name == NAME]
    assert len(walkers) == 2
    assert all(ch(s, c).types == {'Planeswalker'} and c.counters['loyalty'] == 3 for c in walkers)
    assert len([c for c in walkers if c.is_token]) == 1
    roundtrip(s)


def test_creature_only_mana_pays_for_the_prospective_creature_spell(cards):
    from tests.game_helpers import mana_pool

    s = table(cards, [NAME, 'Castle Garenbrig'])
    target = put(s, NAME, 'hand')
    castle = put(s, 'Castle Garenbrig', 'battlefield')
    mana(s, C=2, G=2, B=1)
    ability = next(a for a in ch(s, castle).abilities if 'Add six' in a.text)
    act(s, 'p1', type='activate_ability', card_id=castle.id, ability=ability.index)
    assert mana_pool(s, 'p1') == {'B': 1}
    assert len([u for u in s.state.players['p1'].mana_units if u.sym == 'G' and u.only]) == 6
    act(s, 'p1', type='cast_spell', card_id=target.id)
    settle(s)
    assert ch(s, target).types == {'Planeswalker'}
    assert mana_pool(s, 'p1') == {}
    assert len([u for u in s.state.players['p1'].mana_units if u.sym == 'G' and u.only]) == 4
    roundtrip(s)


def test_own_type_addition_applies_before_other_creature_card_statics(cards):
    from app.rules.creature_types import CREATURE_TYPES

    s = table(cards, [NAME, 'Maskwood Nexus'])
    put(s, 'Maskwood Nexus', 'battlefield')
    target = put(s, NAME, 'library')
    assert ch(s, target).subtypes >= CREATURE_TYPES
    assert 'Grist' in ch(s, target).subtypes
    roundtrip(s)


def test_creature_card_graveyard_triggers_read_its_nonbattlefield_type(cards):
    s = table(cards, [NAME, 'Syr Konrad, the Grim', 'Reanimate'])
    source = put(s, 'Syr Konrad, the Grim', 'battlefield')
    target = put(s, NAME, 'library')
    act(s, 'p1', type='move', card_ids=[target.id], to={'player': 'p1', 'zone': 'library'}, position='top')
    mana(s, C=1, B=1)
    ability = next(a for a in ch(s, source).abilities if a.cost == '{1}{B}')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=ability.index)
    settle(s)
    assert s.state.cards[target.id].zone == 'p1:graveyard'
    assert all(s.state.players[p].life == 39 for p in ['p2', 'p3'])
    roundtrip(s)
    spell = put(s, 'Reanimate', 'hand')
    mana(s, B=1)
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[target.id])
    settle(s)
    assert ch(s, target).types == {'Planeswalker'}
    assert all(s.state.players[p].life == 38 for p in ['p2', 'p3'])
    roundtrip(s)


def test_reanimated_konrad_does_not_see_its_own_lookback_event(cards):
    s = table(cards, ['Syr Konrad, the Grim', 'Reanimate'])
    target = put(s, 'Syr Konrad, the Grim', 'graveyard')
    spell = put(s, 'Reanimate', 'hand')
    mana(s, B=1)
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[target.id])
    settle(s)
    assert s.state.cards[target.id].zone == 'p1:battlefield'
    assert all(s.state.players[p].life == 40 for p in ['p2', 'p3'])
    assert s.state.players['p1'].life == 35
    roundtrip(s)

"""CR 305.1, 603.2h: actual land plays and once-performed optional search."""
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
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/land_entered_not_played_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


NAME = 'Deep Gnome Terramancer'


def setup(cards, source_zone='battlefield', turn=5):
    from tests.test_rules_designations import put
    from tests.test_rules_shared_damage_choices import table
    from tests.test_rules_wave30m_durations import to_phase

    s = table(cards, [NAME, 'Plains', 'Plains', 'Reanimate', 'Ephemerate', 'Flooded Strand'],
              ['Flooded Strand', 'Marsh Flats', 'Plains', 'Plains', 'Plains', 'Dryad Arbor', 'Reanimate', 'Ashiok, Dream Render', 'Djinn of Wishes', 'Scapeshift', 'Forest', 'Island'], [NAME, 'Plains'])
    gnome = put(s, NAME, source_zone)
    to_phase(s, 'main1', turn=turn)
    return s, gnome


def own_plains(s):
    return [c for c in s.state.cards.values() if c.name == 'Plains' and c.zone == 'p1:battlefield']


def fetch(s, name='Flooded Strand', pid='p2', settle_all=True):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import wait_priority
    from tests.test_rules_conditionals import settle
    from tests.test_rules_designations import put
    from tests.test_rules_wave7b_activation import ability_index

    land = put(s, name, 'battlefield', pid)
    wait_priority(s, pid)
    act(s, pid, type='activate_ability', card_id=land.id, ability=ability_index(s, land, 'Search'))
    if settle_all:
        settle(s)
    return land


def test_terramancer_is_full(cards):
    assert coverage.of_card_data(cards.resolve(NAME)).level == 'FULL'


@pytest.mark.parametrize('name', ['Plains', 'Dryad Arbor'])
def test_played_land_including_creature_land_does_not_trigger(cards, name):
    from tests.game_helpers import act
    from tests.test_rules_conditionals import settle
    from tests.test_rules_designations import put, roundtrip

    s, _ = setup(cards)
    land = put(s, name, 'hand', 'p2')
    act(s, 'p2', type='play_land', card_id=land.id)
    settle(s)
    assert not own_plains(s)
    assert not s.state.rules.ability_uses
    roundtrip(s)


def test_native_fetch_triggers_private_plains_tutor_once_each_turn(cards):
    from tests.test_rules_designations import roundtrip

    s, _ = setup(cards)
    fetch(s)
    assert len(own_plains(s)) == 1 and own_plains(s)[0].tapped
    uses = dict(s.state.rules.ability_uses)
    assert uses
    roundtrip(s)
    fetch(s, 'Marsh Flats')
    assert len(own_plains(s)) == 1
    assert s.state.rules.ability_uses == uses
    roundtrip(s)


def test_your_own_unplayed_land_does_not_trigger(cards):
    from tests.test_rules_designations import roundtrip

    s, _ = setup(cards)
    fetch(s, pid='p1')
    assert len(own_plains(s)) == 1
    assert not s.state.rules.ability_uses
    roundtrip(s)


def test_reanimated_creature_land_was_not_played(cards):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_conditionals import settle
    from tests.test_rules_designations import put, roundtrip

    s, _ = setup(cards)
    arbor = put(s, 'Dryad Arbor', 'graveyard', 'p2')
    spell = put(s, 'Reanimate', 'hand', 'p2')
    mana(s, pid='p2', B=1)
    act(s, 'p2', type='cast_spell', card_id=spell.id, targets=[arbor.id])
    settle(s)
    assert s.state.cards[arbor.id].zone == 'p2:battlefield'
    assert len(own_plains(s)) == 1
    roundtrip(s)


def test_reanimated_source_does_not_watch_an_earlier_land_entry(cards):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana, wait_priority
    from tests.test_rules_conditionals import settle
    from tests.test_rules_designations import put, roundtrip

    s, gnome = setup(cards, source_zone='graveyard', turn=4)
    fetch(s)
    wait_priority(s, 'p1')
    spell = put(s, 'Reanimate', 'hand')
    mana(s, B=1)
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[gnome.id])
    settle(s)
    assert s.state.cards[gnome.id].zone == 'p1:battlefield'
    assert not own_plains(s)
    assert not s.state.rules.ability_uses
    roundtrip(s)


def optional_search(s):
    from tests.test_rules_conditionals import until

    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.player == 'p1'
          and {'yes', 'no'} <= {o.id for o in s.state.rules.decision.options})
    return s.state.rules.decision


def test_declining_search_leaves_once_action_available_for_later_fetch(cards):
    from tests.game_helpers import act
    from tests.test_rules_conditionals import settle
    from tests.test_rules_designations import roundtrip

    s, _ = setup(cards)
    fetch(s, settle_all=False)
    d = optional_search(s)
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=['no'])
    settle(s)
    assert not own_plains(s) and not s.state.rules.ability_uses
    roundtrip(s)
    fetch(s, 'Marsh Flats')
    assert len(own_plains(s)) == 1 and s.state.rules.ability_uses
    roundtrip(s)


def test_failed_find_still_counts_search_as_performed(cards):
    from tests.game_helpers import act
    from tests.test_rules_conditionals import settle, until
    from tests.test_rules_designations import roundtrip

    s, _ = setup(cards)
    fetch(s, settle_all=False)
    d = optional_search(s)
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=['yes'])
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.player == 'p1'
          and s.state.rules.decision.resume.get('step') == 'search')
    d = s.state.rules.decision
    assert d.options  # Declining to find is allowed even with a matching Plains.
    roundtrip(s)
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[])
    settle(s)
    assert not own_plains(s) and s.state.rules.ability_uses
    before = dict(s.state.rules.ability_uses)
    fetch(s, 'Marsh Flats')
    assert not own_plains(s) and s.state.rules.ability_uses == before
    roundtrip(s)


def test_forbidden_search_does_not_consume_once_action_and_can_retry_after_removal(cards):
    from tests.game_helpers import act
    from tests.test_rules_designations import put, roundtrip

    s, _ = setup(cards)
    ashiok = put(s, 'Ashiok, Dream Render', 'battlefield', 'p2')
    act(s, 'p2', type='set_counter', card_id=ashiok.id, kind='loyalty', value=5)
    fetch(s)
    assert not own_plains(s) and not s.state.rules.ability_uses
    roundtrip(s)
    act(s, 'p2', type='move', card_ids=[ashiok.id], to={'player': 'p2', 'zone': 'exile'})
    fetch(s, 'Marsh Flats')
    assert len(own_plains(s)) == 1 and s.state.rules.ability_uses
    roundtrip(s)


def test_two_terramancers_resolve_in_apnap_and_each_searches_only_once(cards):
    from tests.test_rules_designations import put, roundtrip

    s, _ = setup(cards)
    put(s, NAME, 'battlefield', 'p3')
    fetch(s, settle_all=False)
    from tests.game_helpers import act

    order = []
    for _ in range(80):
        d = s.state.rules.decision
        if d is not None:
            if {'yes', 'no'} <= {o.id for o in d.options}:
                order.append(d.player)
            act(s, d.player, type='choose', decision_id=d.id, option_ids=[o.id for o in d.options][:max(1, d.min_choices)])
        elif s.state.zones.get('stack'):
            act(s, s.state.rules.priority, type='pass_priority')
        else:
            break
    assert order[:2] == ['p1', 'p3']
    assert len(own_plains(s)) == 1
    assert len([c for c in s.state.cards.values() if c.name == 'Plains' and c.zone == 'p3:battlefield']) == 1
    assert len([k for k in s.state.rules.ability_uses if k.endswith(':t5')]) == 2
    assert not s.state.zones.get('stack')
    roundtrip(s)


def test_land_played_by_djinn_effect_is_marked_per_object_without_marker_bleed(cards):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_conditionals import settle, until
    from tests.test_rules_designations import put, roundtrip
    from tests.test_rules_wave7b_activation import ability_index

    s, _ = setup(cards)
    djinn = put(s, 'Djinn of Wishes', 'battlefield', 'p2')
    act(s, 'p2', type='set_counter', card_id=djinn.id, kind='wish', value=1)
    land = put(s, 'Plains', 'library', 'p2')
    act(s, 'p2', type='move', card_ids=[land.id], to={'player': 'p2', 'zone': 'library'}, position='top')
    mana(s, pid='p2', C=2, U=2)
    act(s, 'p2', type='activate_ability', card_id=djinn.id, ability=ability_index(s, djinn, 'Reveal'))
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.resume.get('step') == 'free_cast_pick')
    d = s.state.rules.decision
    choice = next(o.id for o in d.options if 'Plains' in o.label)
    roundtrip(s)
    act(s, 'p2', type='choose', decision_id=d.id, option_ids=[choice])
    settle(s)
    assert s.state.cards[land.id].zone == 'p2:battlefield'
    assert s.state.rules.lands_this_turn('p2', 5) == 1
    assert not own_plains(s) and not s.state.rules.ability_uses
    roundtrip(s)
    fetch(s)
    assert len(own_plains(s)) == 1  # A different entering land was not played.
    roundtrip(s)


def test_simultaneous_scapeshift_lands_make_one_aggregate_trigger(cards):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_conditionals import settle, until
    from tests.test_rules_designations import put, roundtrip

    s, _ = setup(cards)
    lands = [put(s, n, 'battlefield', 'p2') for n in ['Forest', 'Island']]
    spell = put(s, 'Scapeshift', 'hand', 'p2')
    mana(s, pid='p2', C=2, G=2)
    act(s, 'p2', type='cast_spell', card_id=spell.id)
    until(s, lambda s: s.state.rules.decision is not None and {c.id for c in lands} <= {o.id for o in s.state.rules.decision.options})
    d = s.state.rules.decision
    act(s, 'p2', type='choose', decision_id=d.id, option_ids=[c.id for c in lands])
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.player == 'p2'
          and s.state.rules.decision.resume.get('step') == 'search')
    d = s.state.rules.decision
    assert d.max_choices == 2
    roundtrip(s)
    act(s, 'p2', type='choose', decision_id=d.id, option_ids=[o.id for o in d.options][:2])
    triggers = [cid for cid in s.state.zones.get('stack', []) if s.state.cards[cid].ability is not None and s.state.cards[cid].name == NAME]
    assert len(triggers) == 1
    settle(s)
    assert len(own_plains(s)) == 1
    roundtrip(s)

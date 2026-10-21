"""CR 608.2d, 701.13, 202.3: opponent choices and milled-card mana values."""
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
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/cast_mana_total_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()



def test_full(cards):
    assert coverage.of_card_data(cards.resolve('Call Forth the Tempest')).level == 'FULL'


def setup(cards):
    from tests.game_helpers import act
    from tests.test_rules_designations import put
    from tests.test_rules_shared_damage_choices import table

    names = [c['name'] for c in json.loads((Path(__file__).parent / 'fixtures/cast_mana_total_cards.json').read_text())]
    s = table(cards, names, names, ['Darksteel Myr'])
    source = put(s, 'Call Forth the Tempest', 'hand')
    witnesses = [put(s, 'Darksteel Myr', 'battlefield', pid) for pid in ['p1', 'p2', 'p3']]
    library = list(s.state.zones.get('p1:library', []))
    if library:
        act(s, 'p1', type='move', card_ids=library, to={'player': 'p1', 'zone': 'exile'})
    return s, source, witnesses


def cast(s, name, *, targets=(), pool=None, pid='p1', x=None):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana, wait_priority
    from tests.test_rules_designations import put

    source = put(s, name, 'hand', pid)
    wait_priority(s, pid)
    mana(s, pid, **(pool or {}))
    act(s, pid, type='cast_spell', card_id=source.id, targets=list(targets), **({'x_value': x} if x is not None else {}))
    return source


def tempest(s, source, cascades=(), *, cast_cascades=True):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana, wait_priority
    from tests.test_rules_designations import roundtrip, settle

    wait_priority(s, 'p1')
    chosen = []
    for name in cascades:
        chosen.append(next(c.id for c in s.state.cards.values() if c.owner == 'p1' and c.name == name and c.id not in chosen))
    if chosen:
        act(s, 'p1', type='move', card_ids=chosen, to={'player': 'p1', 'zone': 'library'}, index=0)
    mana(s, C=5, R=3)
    act(s, 'p1', type='cast_spell', card_id=source.id)
    settle(s)
    while (d := s.state.rules.decision) is not None:
        roundtrip(s)
        assert d.resume['step'] == 'suspend_cast'
        act(s, d.player, type='choose', decision_id=d.id, option_ids=['yes' if cast_cascades else 'no'])
        settle(s)
    roundtrip(s)


def damage(s, witnesses):
    return [s.state.cards[c.id].damage for c in witnesses]


@pytest.mark.parametrize('name,pool,x,total', [('Lightning Bolt', {'R': 1}, None, 1),
    ('Walking Ballista', {'C': 6}, 3, 6), ('Ornithopter', {}, None, 0)])
def test_sums_mana_values_as_cast_and_excludes_the_current_tempest(cards, name, pool, x, total):
    from tests.test_rules_designations import settle

    s, source, witnesses = setup(cards)
    cast(s, name, pool=pool, x=x, targets=['p2'] if name == 'Lightning Bolt' else [])
    settle(s)
    tempest(s, source)
    assert damage(s, witnesses) == [0, total, total]


def test_no_other_casts_means_no_damage(cards):
    s, source, witnesses = setup(cards)
    tempest(s, source)
    assert damage(s, witnesses) == [0, 0, 0]


@pytest.mark.parametrize('accepted,total', [(True, 1), (False, 0)])
def test_cascaded_spells_count_only_if_actually_cast(cards, accepted, total):
    s, source, witnesses = setup(cards)
    tempest(s, source, cascades=['Sol Ring', 'Ornithopter'], cast_cascades=accepted)
    assert damage(s, witnesses) == [0, total, total]


def test_opponents_casts_do_not_count(cards):
    from tests.test_rules_designations import settle

    s, source, witnesses = setup(cards)
    cast(s, 'Lightning Bolt', pid='p2', pool={'R': 1}, targets=['p1'])
    settle(s)
    tempest(s, source)
    assert damage(s, witnesses) == [0, 0, 0]


def test_countered_spells_still_count_and_opponents_counterspell_does_not(cards):
    from tests.test_rules_designations import settle

    s, source, witnesses = setup(cards)
    ring = cast(s, 'Sol Ring', pool={'C': 1})
    cast(s, 'Counterspell', pid='p2', pool={'U': 2}, targets=[ring.id])
    settle(s)
    assert s.state.cards[ring.id].zone == 'p1:graveyard'
    tempest(s, source)
    assert damage(s, witnesses) == [0, 1, 1]


def test_uncast_spell_copy_is_excluded_from_the_total(cards):
    from tests.game_helpers import act
    from tests.test_rules_designations import settle

    s, source, witnesses = setup(cards)
    act(s, 'p1', type='set_prefs', hold_priority=True)
    bolt = cast(s, 'Lightning Bolt', pool={'R': 1}, targets=['p2'])
    cast(s, 'Reverberate', pool={'R': 2}, targets=[bolt.id])
    from tests.test_rules_conditionals import settle as choose_all
    choose_all(s)
    settle(s)
    tempest(s, source)
    assert damage(s, witnesses) == [0, 3, 3]  # Bolt 1 + Reverberate 2, without the uncast Bolt copy.


def test_cost_reduction_does_not_reduce_the_recorded_mana_value(cards):
    from tests.test_rules_designations import settle

    s, source, witnesses = setup(cards)
    cast(s, 'Blasphemous Act', pool={'C': 5, 'R': 1})
    settle(s)
    assert damage(s, witnesses) == [13, 13, 13]
    tempest(s, source)
    assert damage(s, witnesses) == [13, 22, 22]


def test_recasting_the_same_physical_tempest_counts_its_previous_object(cards):
    from tests.test_rules_designations import settle

    s, source, witnesses = setup(cards)
    tempest(s, source)
    cast(s, 'Regrowth', pool={'C': 1, 'G': 1}, targets=[source.id])
    settle(s)
    tempest(s, source)
    assert damage(s, witnesses) == [0, 10, 10]  # Earlier Tempest 8 + Regrowth 2.


def test_copy_of_tempest_counts_the_original_cast_but_original_excludes_itself(cards):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_conditionals import settle as choose_all
    from tests.test_rules_designations import roundtrip

    s, source, witnesses = setup(cards)
    act(s, 'p1', type='set_prefs', hold_priority=True)
    mana(s, C=5, R=3)
    act(s, 'p1', type='cast_spell', card_id=source.id)
    for _ in range(30):
        d = s.state.rules.decision
        if d is not None:
            assert d.kind == 'order'
            act(s, d.player, type='choose', decision_id=d.id, option_ids=[o.id for o in d.options])
        elif len(s.state.zones.get('stack', [])) == 1:
            break
        else:
            act(s, s.state.rules.priority, type='pass_priority')
    assert s.state.zones['stack'] == [source.id]
    cast(s, 'Reverberate', pool={'R': 2}, targets=[source.id])
    choose_all(s)
    assert damage(s, witnesses) == [0, 12, 12]  # Copy 8+2, original 2.
    roundtrip(s)


def test_cast_history_and_damage_reset_on_a_new_turn(cards):
    from tests.game_helpers import act
    from tests.test_rules_designations import roundtrip, settle
    from tests.test_rules_wave30m_durations import to_phase

    s, source, witnesses = setup(cards)
    cast(s, 'Lightning Bolt', pool={'R': 1}, targets=['p2'])
    settle(s)
    tempest(s, source)
    assert damage(s, witnesses) == [0, 1, 1]
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'hand'})
    lands = [c.id for c in s.state.cards.values() if c.owner == 'p1' and c.name == 'Forest']
    act(s, 'p1', type='move', card_ids=lands, to={'player': 'p1', 'zone': 'library'})
    to_phase(s, 'main1', turn=4)
    assert damage(s, witnesses) == [0, 0, 0]
    act(s, 'p1', type='move', card_ids=list(s.state.zones['p1:library']), to={'player': 'p1', 'zone': 'exile'})
    tempest(s, source)
    assert damage(s, witnesses) == [0, 0, 0]
    roundtrip(s)

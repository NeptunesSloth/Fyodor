"""CR 608.2h, 601.2f: maximum per-player permanent counts."""
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
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/player_max_count_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()



DRAGON = 'Cavern-Hoard Dragon'
JOURNAL = "Investigator's Journal"


@pytest.mark.parametrize('name', [DRAGON, JOURNAL])
def test_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


def tokens(s, pid, count, *, artifact=False):
    from tests.game_helpers import act

    for _ in range(count):
        act(s, pid, type='create_token', player=pid,
            token={'name': 'Servo' if artifact else 'Soldier',
                   'type_line': 'Artifact Creature — Servo' if artifact else 'Creature — Soldier', 'power': '1', 'toughness': '1'})


def setup(cards):
    from tests.test_rules_shared_damage_choices import table

    return table(cards, [DRAGON, JOURNAL, 'Sphere of Resistance', 'Solemnity', 'Vorinclex, Monstrous Raider', 'Ornithopter', 'Open the Vaults'], [], [])


@pytest.mark.parametrize('counts', [(7, 0, 0), (0, 2, 3), (0, 3, 3), (1, 9, 1)])
def test_dragon_discount_is_opponents_maximum_not_sum_or_your_own_count(cards, counts):
    from app.rules.casting import spell_cost
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_conditionals import settle
    from tests.test_rules_designations import put, roundtrip
    from tests.test_rules_wave6c_tokens_pumps import chars

    s = setup(cards)
    for pid, count in zip(['p1', 'p2', 'p3'], counts, strict=True):
        tokens(s, pid, count, artifact=True)
    spell = put(s, DRAGON, 'hand')
    generic = max(0, 7-max(counts[1:]))
    due = spell_cost(s.state, spell, chars(s, spell), info=s.cards)
    assert due.generic == generic and due.colored == ('R', 'R')
    mana(s, C=generic, R=2)
    act(s, 'p1', type='cast_spell', card_id=spell.id)
    settle(s)
    assert s.state.cards[spell.id].zone == 'p1:battlefield'
    assert {'flying', 'trample', 'haste'} <= chars(s, spell).keywords
    assert not any(s.state.players['p1'].mana.values())
    roundtrip(s)


@pytest.mark.parametrize('counts', [(0, 0, 0), (1, 3, 2), (4, 2, 1)])
def test_journal_entry_counts_the_largest_player_board_including_your_own(cards, counts):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_conditionals import settle
    from tests.test_rules_designations import put, roundtrip

    s = setup(cards)
    for pid, count in zip(['p1', 'p2', 'p3'], counts, strict=True):
        tokens(s, pid, count)
    spell = put(s, JOURNAL, 'hand')
    mana(s, C=2)
    act(s, 'p1', type='cast_spell', card_id=spell.id)
    settle(s)
    assert s.state.cards[spell.id].counters.get('suspect', 0) == max(counts)
    roundtrip(s)


@pytest.mark.parametrize('modifier,expected', [('Solemnity', 0), ('Vorinclex, Monstrous Raider', 6)])
def test_journal_counter_replacements_apply_after_the_maximum_is_computed(cards, modifier, expected):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_conditionals import settle
    from tests.test_rules_designations import put, roundtrip

    s = setup(cards)
    tokens(s, 'p2', 3)
    put(s, modifier, 'battlefield')
    spell = put(s, JOURNAL, 'hand')
    mana(s, C=2)
    act(s, 'p1', type='cast_spell', card_id=spell.id)
    settle(s)
    assert s.state.cards[spell.id].counters.get('suspect', 0) == expected
    roundtrip(s)


def test_journal_counter_is_an_entry_value_and_pays_real_draw_ability(cards):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana, wait_priority
    from tests.test_rules_conditionals import settle
    from tests.test_rules_designations import put, roundtrip
    from tests.test_rules_wave7b_activation import ability_index

    s = setup(cards)
    tokens(s, 'p2', 3)
    spell = put(s, JOURNAL, 'hand')
    mana(s, C=2)
    act(s, 'p1', type='cast_spell', card_id=spell.id)
    settle(s)
    tokens(s, 'p1', 5)
    assert s.state.cards[spell.id].counters['suspect'] == 3
    wait_priority(s, 'p1')
    hand = len(s.state.zones['p1:hand'])
    mana(s, C=2)
    act(s, 'p1', type='activate_ability', card_id=spell.id, ability=ability_index(s, spell, 'Remove a suspect'))
    settle(s)
    assert s.state.cards[spell.id].counters['suspect'] == 2 and s.state.cards[spell.id].tapped
    assert len(s.state.zones['p1:hand']) == hand+1
    roundtrip(s)


def test_simultaneous_new_creature_is_not_counted_before_journal_enters(cards):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_conditionals import settle
    from tests.test_rules_designations import put, roundtrip

    s = setup(cards)
    journal = put(s, JOURNAL, 'graveyard')
    thopter = put(s, 'Ornithopter', 'graveyard')
    spell = put(s, 'Open the Vaults', 'hand')
    mana(s, C=4, W=2)
    act(s, 'p1', type='cast_spell', card_id=spell.id)
    settle(s)
    assert s.state.cards[journal.id].zone == 'p1:battlefield'
    assert s.state.cards[thopter.id].zone == 'p1:battlefield'
    assert s.state.cards[journal.id].counters.get('suspect', 0) == 0
    roundtrip(s)

"""CR 208.4b: compare either base stat, ignoring modifying effects and counters."""
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
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/base_power_or_toughness_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()



@pytest.mark.parametrize('name', ['Sword of the Squeak', 'Angelic Aberration'])
def test_base_power_or_toughness_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


def derived(s, c):
    from app.rules.plan import Plan

    return Plan(s.state, 'p1', s.cards, None).ch(s.state.cards[c.id])


@pytest.mark.parametrize('modifications', [False, True])
def test_sword_counts_either_base_stat_once_and_ignores_modifiers_and_opponents(cards, modifications):
    from tests.test_rules_wave5j_token_copies import token

    names = ['Sword of the Squeak', 'Grizzly Bears', 'Llanowar Elves', 'Prodigal Pyromancer', 'Blood Artist',
             'Ornithopter', 'Glorious Anthem', 'Fists of the Anvil']
    s = table(cards, names, ['Llanowar Elves'])
    sword = put(s, 'Sword of the Squeak', 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    elf = put(s, 'Llanowar Elves', 'battlefield')
    put(s, 'Prodigal Pyromancer', 'battlefield')
    put(s, 'Blood Artist', 'battlefield')  # 0/1 qualifies by toughness.
    put(s, 'Ornithopter', 'battlefield')  # 0/2 does not qualify for exactly one.
    put(s, 'Llanowar Elves', 'battlefield', 'p2')
    if modifications:
        put(s, 'Glorious Anthem', 'battlefield')
        act(s, 'p1', type='set_counter', card_id=elf.id, kind='+1/+1', value=9)
        fist = put(s, 'Fists of the Anvil', 'hand')
        act(s, 'p1', type='add_mana', player='p1', mana={'C': 1, 'R': 1})
        act(s, 'p1', type='cast_spell', card_id=fist.id, targets=[elf.id])
        settle(s)
        assert derived(s, elf).base_pt == (1, 1) and derived(s, elf).pt != (1, 1)
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 2})
    act(s, 'p1', type='activate_ability', card_id=sword.id, ability=2, targets=[bear.id])
    settle(s)
    assert s.state.cards[sword.id].attached_to == bear.id
    assert derived(s, bear).pt == ((6, 6) if modifications else (5, 5))
    roundtrip(s)
    token(s, 'p1', 'Soldier', pt='1/1', type_line='Token Creature — Soldier')
    assert derived(s, bear).pt == ((7, 7) if modifications else (6, 6))
    roundtrip(s)
    act(s, 'p1', type='move', card_ids=[elf.id], to={'player': 'p1', 'zone': 'graveyard'})
    assert derived(s, bear).pt == ((6, 6) if modifications else (5, 5))
    roundtrip(s)


@pytest.mark.parametrize('attach', [False, True])
def test_sword_can_attach_when_a_qualifying_creature_enters(cards, attach):
    s = table(cards, ['Sword of the Squeak', 'Typhoid Rats'])
    sword = put(s, 'Sword of the Squeak', 'battlefield')
    rat = put(s, 'Typhoid Rats', 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana={'B': 1})
    act(s, 'p1', type='cast_spell', card_id=rat.id, targets=[])
    settle(s)
    d = s.state.rules.decision
    assert d is not None and d.player == 'p1'
    roundtrip(s)
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=['yes' if attach else 'no'])
    settle(s)
    assert s.state.cards[sword.id].attached_to == (rat.id if attach else None)
    assert derived(s, rat).pt == ((2, 2) if attach else (1, 1))
    roundtrip(s)


@pytest.mark.parametrize('n', [0, 1, 3])
@pytest.mark.parametrize('exile', [False, True])
def test_aberration_sacrifices_by_either_base_stat_and_creates_one_token_per_creature(cards, n, exile):
    from tests.test_rules_wave5j_token_copies import tokens

    names = ['Angelic Aberration', 'Llanowar Elves', 'Prodigal Pyromancer', 'Ornithopter', 'Grizzly Bears',
             'Glorious Anthem', 'Castle']
    s = table(cards, names, ['Llanowar Elves', 'Rest in Peace'])
    selected = [put(s, name, 'battlefield') for name in ['Llanowar Elves', 'Prodigal Pyromancer', 'Ornithopter']]
    bear = put(s, 'Grizzly Bears', 'battlefield')
    other = put(s, 'Llanowar Elves', 'battlefield', 'p2')
    put(s, 'Glorious Anthem', 'battlefield')
    put(s, 'Castle', 'battlefield')
    if exile:
        put(s, 'Rest in Peace', 'battlefield', 'p2')
    source = put(s, 'Angelic Aberration', 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 5, 'W': 1})
    act(s, 'p1', type='cast_spell', card_id=source.id, targets=[])
    settle(s)
    d = s.state.rules.decision
    assert d is not None and d.resume['step'] == 'sacrifice_choice'
    assert {o.id for o in d.options} == {c.id for c in selected}
    assert source.id not in {o.id for o in d.options}
    roundtrip(s)
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[c.id for c in selected[:n]])
    settle(s)
    made = [c for c in tokens(s) if c.name == 'Eldrazi Angel']
    assert len(made) == n
    assert all(derived(s, c).base_pt == (4, 4) and {'flying', 'vigilance'} <= derived(s, c).keywords for c in made)
    assert derived(s, source).colors == frozenset()
    assert bear.id in s.state.zones['p1:battlefield'] and other.id in s.state.zones['p2:battlefield']
    for c in selected[:n]:
        assert c.id in s.state.zones['p1:exile' if exile else 'p1:graveyard']
    roundtrip(s)


def test_aberration_reads_base_values_set_by_an_aura(cards):
    from tests.test_rules_wave5j_token_copies import tokens

    s = table(cards, ['Angelic Aberration', 'Grizzly Bears', 'Lignify'])
    bear = put(s, 'Grizzly Bears', 'battlefield')
    aura = put(s, 'Lignify', 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 1, 'G': 1})
    act(s, 'p1', type='cast_spell', card_id=aura.id, targets=[bear.id])
    settle(s)
    assert derived(s, bear).base_pt == (0, 4)
    source = put(s, 'Angelic Aberration', 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 5, 'W': 1})
    act(s, 'p1', type='cast_spell', card_id=source.id, targets=[])
    settle(s)
    d = s.state.rules.decision
    assert d is not None and {o.id for o in d.options} == {bear.id}
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[bear.id])
    settle(s)
    assert len([c for c in tokens(s) if c.name == 'Eldrazi Angel']) == 1
    roundtrip(s)


def test_aberration_with_no_eligible_creatures_creates_no_tokens_and_asks_no_choice(cards):
    from tests.test_rules_wave5j_token_copies import tokens

    s = table(cards, ['Angelic Aberration', 'Grizzly Bears'])
    put(s, 'Grizzly Bears', 'battlefield')
    source = put(s, 'Angelic Aberration', 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 5, 'W': 1})
    act(s, 'p1', type='cast_spell', card_id=source.id, targets=[])
    settle(s)
    assert s.state.rules.decision is None
    assert not tokens(s)
    roundtrip(s)

"""CR 702.22 / 608.2h: current and last known bandmates."""
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
from tests.test_rules_banding import attacks, block, damage_choice, declare_only, divide, until_block
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/bandmate_references_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()



@pytest.mark.parametrize('name', ['Icatian Skirmishers', "Urza's Engine", 'Camel', 'Battering Ram'])
def test_bandmate_reference_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


def keyword(s, c, word):
    from app.rules.plan import Plan

    return word in Plan(s.state, 'p1', s.cards, None).ch(s.state.cards[c.id]).keywords


@pytest.mark.parametrize('banded', [False, True])
def test_skirmishers_grant_first_strike_to_their_bandmates_until_end_of_turn(cards, banded):
    from tests.test_rules_wave30m_durations import to_phase

    s = table(cards, ['Icatian Skirmishers', 'Grizzly Bears', 'Llanowar Elves'], ['Gigantosaurus'])
    source = put(s, 'Icatian Skirmishers', 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    elf = put(s, 'Llanowar Elves', 'battlefield')
    put(s, 'Gigantosaurus', 'battlefield', 'p2')
    declare_only(s, [source, bear, elf], [[source, bear]] if banded else [])
    assert not keyword(s, bear, 'first strike')
    roundtrip(s)
    settle(s)
    assert keyword(s, bear, 'first strike') == banded
    assert keyword(s, source, 'first strike') and not keyword(s, elf, 'first strike')
    roundtrip(s)
    to_phase(s, 'main1', turn=5)
    assert not keyword(s, bear, 'first strike') and keyword(s, source, 'first strike')
    roundtrip(s)


@pytest.mark.parametrize('departure', ['graveyard', 'return', 'remove_marker'])
def test_source_departure_uses_last_known_membership_but_a_present_source_uses_its_current_band(cards, departure):
    s = table(cards, ['Icatian Skirmishers', 'Grizzly Bears'], ['Gigantosaurus'])
    source = put(s, 'Icatian Skirmishers', 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    put(s, 'Gigantosaurus', 'battlefield', 'p2')
    declare_only(s, [source, bear], [[source, bear]])
    if departure == 'remove_marker':
        act(s, 'p1', type='attack', card_ids=[source.id], target=None)
    else:
        act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'graveyard'})
        if departure == 'return':
            act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'battlefield'})
    roundtrip(s)
    settle(s)
    assert keyword(s, bear, 'first strike') == (departure != 'remove_marker')
    roundtrip(s)


def test_a_bandmate_that_leaves_and_returns_does_not_receive_the_grant(cards):
    s = table(cards, ['Icatian Skirmishers', 'Grizzly Bears'], ['Gigantosaurus'])
    source = put(s, 'Icatian Skirmishers', 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    put(s, 'Gigantosaurus', 'battlefield', 'p2')
    declare_only(s, [source, bear], [[source, bear]])
    act(s, 'p1', type='move', card_ids=[bear.id], to={'player': 'p1', 'zone': 'graveyard'})
    act(s, 'p1', type='move', card_ids=[bear.id], to={'player': 'p1', 'zone': 'battlefield'})
    settle(s)
    assert not keyword(s, bear, 'first strike')
    roundtrip(s)


@pytest.mark.parametrize('banded', [False, True])
@pytest.mark.parametrize('source_leaves', [False, True])
def test_engine_grants_trample_only_to_its_bandmates_even_if_the_source_leaves(cards, banded, source_leaves):
    from tests.test_rules_wave30m_durations import to_phase

    s = table(cards, ["Urza's Engine", 'Grizzly Bears'], ['Gigantosaurus'])
    engine = put(s, "Urza's Engine", 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    put(s, 'Gigantosaurus', 'battlefield', 'p2')
    to_phase(s, 'main1', turn=4)
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 3})
    act(s, 'p1', type='activate_ability', card_id=engine.id, ability=1)
    settle(s)
    assert keyword(s, engine, 'banding')
    declare_only(s, [engine, bear], [[engine, bear]] if banded else [])
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 3})
    act(s, 'p1', type='activate_ability', card_id=engine.id, ability=2)
    if source_leaves:
        act(s, 'p1', type='move', card_ids=[engine.id], to={'player': 'p1', 'zone': 'graveyard'})
    roundtrip(s)
    settle(s)
    assert keyword(s, bear, 'trample') == banded
    roundtrip(s)


def test_engine_activation_before_attacking_has_no_bandmates_to_grant_trample(cards):
    s = table(cards, ["Urza's Engine", 'Grizzly Bears'])
    engine = put(s, "Urza's Engine", 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 3})
    act(s, 'p1', type='activate_ability', card_id=engine.id, ability=2)
    settle(s)
    assert not keyword(s, bear, 'trample')
    assert sum(s.state.players['p1'].mana.values()) == 0
    roundtrip(s)


def test_unbound_bandmate_pronouns_stay_manual():
    from app.rules import scripts

    assert scripts.parse_effects('All creatures banded with it gain first strike until end of turn.') is None
    assert scripts.parse_effects('Destroy target creature. All creatures banded with it gain first strike until end of turn.') is None


def mana(s, pid='p1', **pool):
    act(s, pid, type='add_mana', player=pid, mana=pool)


def wait_priority(s, pid):
    for _ in range(6):
        if s.state.rules.priority == pid:
            return
        assert s.state.rules.decision is None
        act(s, s.state.rules.priority, type='pass_priority')
    raise AssertionError('did not reach priority')


@pytest.mark.parametrize('recipient', ['camel', 'bandmate', 'unbanded'])
@pytest.mark.parametrize('desert_leaves', [False, True])
def test_camel_prevents_desert_damage_to_itself_and_its_band_but_not_other_attackers(cards, recipient, desert_leaves):
    from tests.test_rules_wave30m_durations import to_phase

    s = table(cards, ['Camel', 'Grizzly Bears', 'Llanowar Elves'], ['Desert', 'Grizzly Bears'])
    camel = put(s, 'Camel', 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    elf = put(s, 'Llanowar Elves', 'battlefield')
    desert = put(s, 'Desert', 'battlefield', 'p2')
    put(s, 'Grizzly Bears', 'battlefield', 'p2')
    attacks(s, [(c, 'p2') for c in [camel, bear, elf]], [[camel, bear]])
    block(s, [])
    to_phase(s, 'end_combat', turn=4)
    wait_priority(s, 'p2')
    target = {'camel': camel, 'bandmate': bear, 'unbanded': elf}[recipient]
    act(s, 'p2', type='activate_ability', card_id=desert.id, ability=1, targets=[target.id])
    if desert_leaves:
        act(s, 'p2', type='move', card_ids=[desert.id], to={'player': 'p2', 'zone': 'graveyard'})
    roundtrip(s)
    settle(s)
    if recipient == 'unbanded':
        assert elf.id in s.state.zones['p1:graveyard']
    else:
        assert target.id in s.state.zones['p1:battlefield'] and s.state.cards[target.id].damage == 0
    roundtrip(s)


@pytest.mark.parametrize('attacking', [False, True])
def test_camel_requires_attacking_and_prevents_noncombat_damage_from_an_animated_desert(cards, attacking):
    s = table(cards, ['Camel', 'Grizzly Bears', 'Desert', 'Natural Affinity', "Soul's Fire"], ['Gigantosaurus'])
    camel = put(s, 'Camel', 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    desert = put(s, 'Desert', 'battlefield')
    put(s, 'Gigantosaurus', 'battlefield', 'p2')
    if attacking:
        declare_only(s, [camel, bear], [[camel, bear]])
    affinity = put(s, 'Natural Affinity', 'hand')
    mana(s, C=2, G=1)
    act(s, 'p1', type='cast_spell', card_id=affinity.id, targets=[])
    settle(s)
    spell = put(s, "Soul's Fire", 'hand')
    mana(s, C=2, R=1)
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[desert.id, camel.id], target_counts=[1, 1])
    roundtrip(s)
    settle(s)
    assert camel.id in s.state.zones['p1:battlefield' if attacking else 'p1:graveyard']
    if attacking:
        assert s.state.cards[camel.id].damage == 0
    roundtrip(s)


def test_camel_also_prevents_animated_deserts_combat_damage(cards):
    s = table(cards, ['Camel', 'Grizzly Bears', 'Natural Affinity'], ['Desert'])
    camel = put(s, 'Camel', 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    desert = put(s, 'Desert', 'battlefield', 'p2')
    declare_only(s, [camel, bear], [[camel, bear]])
    affinity = put(s, 'Natural Affinity', 'hand')
    mana(s, C=2, G=1)
    act(s, 'p1', type='cast_spell', card_id=affinity.id, targets=[])
    settle(s)
    until_block(s)
    block(s, [(desert, bear)])
    assert damage_choice(s).player == 'p1'
    divide(s, {camel.id: 2})
    assert desert.id in s.state.zones['p2:graveyard']
    assert camel.id in s.state.zones['p1:battlefield'] and s.state.cards[camel.id].damage == 0
    assert bear.id in s.state.zones['p1:battlefield'] and s.state.cards[bear.id].damage == 0
    roundtrip(s)


def test_camel_does_not_prevent_damage_from_other_sources(cards):
    s = table(cards, ['Camel', 'Grizzly Bears', 'Lightning Bolt'], ['Gigantosaurus'])
    camel = put(s, 'Camel', 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    put(s, 'Gigantosaurus', 'battlefield', 'p2')
    declare_only(s, [camel, bear], [[camel, bear]])
    bolt = put(s, 'Lightning Bolt', 'hand')
    mana(s, R=1)
    act(s, 'p1', type='cast_spell', card_id=bolt.id, targets=[camel.id])
    settle(s)
    assert camel.id in s.state.zones['p1:graveyard']
    roundtrip(s)


def test_camel_cannot_prevent_unpreventable_desert_damage(cards):
    from tests.test_rules_wave30m_durations import to_phase

    s = table(cards, ['Camel', 'Skullcrack'], ['Desert', 'Grizzly Bears'])
    camel = put(s, 'Camel', 'battlefield')
    desert = put(s, 'Desert', 'battlefield', 'p2')
    put(s, 'Grizzly Bears', 'battlefield', 'p2')
    attacks(s, [(camel, 'p2')])
    block(s, [])
    to_phase(s, 'end_combat', turn=4)
    skullcrack = put(s, 'Skullcrack', 'hand')
    mana(s, C=1, R=1)
    act(s, 'p1', type='cast_spell', card_id=skullcrack.id, targets=['p3'])
    settle(s)
    wait_priority(s, 'p2')
    act(s, 'p2', type='activate_ability', card_id=desert.id, ability=1, targets=[camel.id])
    settle(s)
    assert camel.id in s.state.zones['p1:graveyard']
    roundtrip(s)


def test_camel_leaving_ends_its_static_prevention(cards):
    from tests.test_rules_wave30m_durations import to_phase

    s = table(cards, ['Camel', 'Grizzly Bears'], ['Desert', 'Grizzly Bears'])
    camel = put(s, 'Camel', 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    desert = put(s, 'Desert', 'battlefield', 'p2')
    put(s, 'Grizzly Bears', 'battlefield', 'p2')
    attacks(s, [(camel, 'p2'), (bear, 'p2')], [[camel, bear]])
    block(s, [])
    act(s, 'p1', type='move', card_ids=[camel.id], to={'player': 'p1', 'zone': 'graveyard'})
    to_phase(s, 'end_combat', turn=4)
    wait_priority(s, 'p2')
    act(s, 'p2', type='activate_ability', card_id=desert.id, ability=1, targets=[bear.id])
    settle(s)
    assert s.state.cards[bear.id].damage == 1
    roundtrip(s)


@pytest.mark.parametrize('indestructible', [False, True])
@pytest.mark.parametrize('banded', [False, True])
def test_battering_ram_destroys_its_wall_blocker_at_end_of_combat(cards, indestructible, banded):
    from tests.test_rules_wave30m_durations import to_phase

    s = table(cards, ['Battering Ram', 'Grizzly Bears', 'Withstand Death'], ['Wall of Omens'])
    ram = put(s, 'Battering Ram', 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    wall = put(s, 'Wall of Omens', 'battlefield', 'p2')
    attacks(s, [(c, 'p2') for c in [ram, bear]], [[ram, bear]] if banded else [])
    assert keyword(s, ram, 'banding')
    block(s, [(wall, bear if banded else ram)])
    if indestructible:
        spell = put(s, 'Withstand Death', 'hand')
        mana(s, G=1)
        act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[wall.id])
    settle(s)
    assert wall.id in s.state.zones['p2:battlefield']
    roundtrip(s)
    to_phase(s, 'end_combat', turn=4)
    settle(s)
    assert wall.id in s.state.zones['p2:battlefield' if indestructible else 'p2:graveyard']
    to_phase(s, 'main2', turn=4)
    assert not keyword(s, ram, 'banding')
    roundtrip(s)

"""CR 701.21a / 608.2h: counted sacrifices followed by draws or returns."""
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
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/sacrifice_count_sequences_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()



@pytest.mark.parametrize('name', ['Pitiless Carnage', 'Malevolent Witchkite', "Lich-Knights' Conquest"])
def test_sacrifice_count_sequence_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


def cast(s, name):
    source = put(s, name, 'hand')
    mana = {'Pitiless Carnage': {'C': 3, 'B': 1}, 'Malevolent Witchkite': {'C': 4, 'B': 2},
            "Lich-Knights' Conquest": {'C': 4, 'B': 1}}[name]
    act(s, 'p1', type='add_mana', player='p1', mana=mana)
    act(s, 'p1', type='cast_spell', card_id=source.id, targets=[])
    settle(s)
    return source


def choose_sacrifices(s, selected):
    d = s.state.rules.decision
    assert d is not None and d.player == 'p1' and d.resume['step'] == 'sacrifice_choice'
    assert d.min_choices == 0
    roundtrip(s)
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[c.id for c in selected])
    settle(s)
    roundtrip(s)


@pytest.mark.parametrize('name', ['Pitiless Carnage', 'Malevolent Witchkite'])
@pytest.mark.parametrize('n', [0, 1, 3])
@pytest.mark.parametrize('exile', [False, True])
def test_draws_count_actual_sacrifices_once_even_with_tokens_and_replaced_destinations(cards, name, n, exile):
    from tests.test_rules_wave5j_token_copies import token

    s = table(cards, [name, 'Sol Ring', 'Glorious Anthem', 'Ornithopter', 'Grizzly Bears'],
              ['Rest in Peace', 'Sol Ring'])
    ring = put(s, 'Sol Ring', 'battlefield')
    anthem = put(s, 'Glorious Anthem', 'battlefield')
    orni = put(s, 'Ornithopter', 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    theirs = put(s, 'Sol Ring', 'battlefield', 'p2')
    made = token(s, 'p1', 'Bear')
    if exile:
        put(s, 'Rest in Peace', 'battlefield', 'p2')
    cast(s, name)
    d = s.state.rules.decision
    offered = {o.id for o in d.options}
    assert {ring.id, anthem.id, orni.id, made.id} <= offered and theirs.id not in offered
    assert (bear.id in offered) == (name == 'Pitiless Carnage')
    before = len(s.state.zones['p1:hand'])
    selected = [ring, orni, made][:n]  # An artifact creature counts once, and a ceased token counts too.
    choose_sacrifices(s, selected)
    assert len(s.state.zones['p1:hand']) == before + n
    for c in selected:
        if c.is_token:
            assert c.id not in s.state.cards
        else:
            assert c.id in s.state.zones['p1:exile' if exile else 'p1:graveyard']
    assert bear.id in s.state.zones['p1:battlefield'] and theirs.id in s.state.zones['p2:battlefield']
    roundtrip(s)


@pytest.mark.parametrize('n', [0, 1, 2, 3, 4])
def test_conquest_chooses_after_sacrifice_and_can_return_a_creature_just_sacrificed(cards, n):
    from tests.test_rules_wave5j_token_copies import token

    name = "Lich-Knights' Conquest"
    s = table(cards, [name, 'Sol Ring', 'Glorious Anthem', 'Ornithopter', 'Grizzly Bears',
                      'Sakura-Tribe Elder', 'Llanowar Elves'])
    ring = put(s, 'Sol Ring', 'battlefield')
    anthem = put(s, 'Glorious Anthem', 'battlefield')
    orni = put(s, 'Ornithopter', 'battlefield')
    elf = put(s, 'Llanowar Elves', 'battlefield')
    made = token(s, 'p1', 'Bear')
    bear = put(s, 'Grizzly Bears', 'graveyard')
    elder = put(s, 'Sakura-Tribe Elder', 'graveyard')
    cast(s, name)
    assert elf.id not in {o.id for o in s.state.rules.decision.options}
    selected = [orni, ring, anthem, made][:n]
    choose_sacrifices(s, selected)
    expected = [orni, bear, elder][:min(n, 3)] if n else []
    if n in [1, 2]:
        d = s.state.rules.decision
        assert d is not None and d.resume['step'] == 'return_choice'
        assert d.min_choices == d.max_choices == n
        assert orni.id in {o.id for o in d.options}
        roundtrip(s)
        act(s, 'p1', type='choose', decision_id=d.id, option_ids=[c.id for c in expected])
        settle(s)
    else:
        assert s.state.rules.decision is None
    for c in expected:
        assert c.id in s.state.zones['p1:battlefield']
    if n == 0:
        assert bear.id in s.state.zones['p1:graveyard'] and elder.id in s.state.zones['p1:graveyard']
    assert elf.id in s.state.zones['p1:battlefield']
    roundtrip(s)


def test_sacrificed_creatures_see_each_other_die_simultaneously_before_draw_triggers_resolve(cards):
    s = table(cards, ['Pitiless Carnage', 'Blood Artist', 'Grizzly Bears', 'Sakura-Tribe Elder'])
    artist = put(s, 'Blood Artist', 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    elder = put(s, 'Sakura-Tribe Elder', 'battlefield')
    cast(s, 'Pitiless Carnage')
    before = len(s.state.zones['p1:hand'])
    choose_sacrifices(s, [artist, bear, elder])
    assert len(s.state.zones['p1:hand']) == before + 3
    for _ in range(3):
        d = s.state.rules.decision
        assert d is not None and 'p2' in {o.id for o in d.options}
        act(s, d.player, type='choose', decision_id=d.id, option_ids=['p2'])
        settle(s)
    assert s.state.players['p1'].life == 43 and s.state.players['p2'].life == 37
    assert s.state.rules.decision is None
    roundtrip(s)


def test_pitiless_carnage_can_be_plotted_and_cast_free_on_a_later_turn(cards):
    from tests.test_rules_wave30m_durations import to_phase

    s = table(cards, ['Pitiless Carnage', 'Sol Ring'])
    ring = put(s, 'Sol Ring', 'battlefield')
    spell = put(s, 'Pitiless Carnage', 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 1, 'B': 2})
    act(s, 'p1', type='activate_ability', card_id=spell.id, ability=1)
    assert spell.id in s.state.zones['p1:exile']
    roundtrip(s)
    to_phase(s, 'main1', turn=4)
    act(s, 'p1', type='cast_spell', card_id=spell.id, free=True, targets=[])
    settle(s)
    before = len(s.state.zones['p1:hand'])
    choose_sacrifices(s, [ring])
    assert len(s.state.zones['p1:hand']) == before + 1
    roundtrip(s)

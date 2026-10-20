"""CR 601.2c / 202.3: different mana-value reanimation targets within X."""
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
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/distinct_mana_reanimation_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()



def test_agadeem_is_full(cards):
    assert coverage.of_card_data(cards.resolve("Agadeem's Awakening // Agadeem, the Undercrypt")).level == 'FULL'


NAME = "Agadeem's Awakening // Agadeem, the Undercrypt"


def setup_graveyard(cards):
    from tests.test_rules_designations import put
    from tests.test_rules_shared_damage_choices import table

    s = table(cards, [NAME, 'Ornithopter', 'Walking Ballista', 'Llanowar Elves', 'Grizzly Bears', 'Elvish Visionary', 'Hill Giant'], ['Grizzly Bears'], [])
    source = put(s, NAME, 'hand')
    dead = {name: put(s, name, 'graveyard') for name in ['Ornithopter', 'Walking Ballista', 'Llanowar Elves', 'Grizzly Bears', 'Elvish Visionary', 'Hill Giant']}
    other = put(s, 'Grizzly Bears', 'graveyard', 'p2')
    return s, source, dead, other


def test_returns_distinct_values_up_to_x_in_one_battlefield_event(cards):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import roundtrip, settle

    s, source, dead, _ = setup_graveyard(cards)
    selected = [dead[n].id for n in ['Ornithopter', 'Llanowar Elves', 'Grizzly Bears']]
    mana(s, B=6)
    act(s, 'p1', type='cast_spell', card_id=source.id, x_value=3, targets=selected, target_counts=[3])
    roundtrip(s)
    settle(s)
    assert all(s.state.cards[cid].zone == 'p1:battlefield' for cid in selected)
    moves = [step for a in s.history.actions if isinstance(getattr(a, 'r', None), list) for step in a.r
             if step.get('type') == 'move' and step.get('to', {}).get('zone') == 'battlefield']
    assert any(set(selected) <= set(step['card_ids']) for step in moves)
    assert s.state.cards[dead['Hill Giant'].id].zone == 'p1:graveyard'
    roundtrip(s)


@pytest.mark.parametrize('names,x', [(['Grizzly Bears', 'Elvish Visionary'], 3),
                                    (['Ornithopter', 'Walking Ballista'], 0),
                                    (['Hill Giant'], 3)])
def test_rejects_repeated_mana_values_and_values_above_x_before_paying(cards, names, x):
    from app.game.errors import ActionError
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import roundtrip

    s, source, dead, _ = setup_graveyard(cards)
    mana(s, B=x + 3)
    before = dict(s.state.players['p1'].mana)
    selected = [dead[n].id for n in names]
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=source.id, x_value=x, targets=selected, target_counts=[len(selected)])
    assert s.state.cards[source.id].zone == 'p1:hand'
    assert s.state.players['p1'].mana == before
    roundtrip(s)


@pytest.mark.parametrize('selected', [False, True])
def test_x_zero_allows_no_targets_or_a_zero_mana_value_creature(cards, selected):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import roundtrip, settle

    s, source, dead, _ = setup_graveyard(cards)
    mana(s, B=3)
    targets = [dead['Ornithopter'].id] if selected else []
    act(s, 'p1', type='cast_spell', card_id=source.id, x_value=0, targets=targets, target_counts=[len(targets)])
    settle(s)
    assert s.state.cards[dead['Ornithopter'].id].zone == ('p1:battlefield' if selected else 'p1:graveyard')
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    roundtrip(s)


def test_only_own_graveyard_is_eligible(cards):
    from app.game.errors import ActionError
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import roundtrip

    s, source, _, other = setup_graveyard(cards)
    mana(s, B=6)
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=source.id, x_value=3, targets=[other.id], target_counts=[1])
    roundtrip(s)


def test_remaining_legal_targets_return_when_another_leaves_graveyard(cards):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import roundtrip, settle

    s, source, dead, _ = setup_graveyard(cards)
    elf, bear = dead['Llanowar Elves'], dead['Grizzly Bears']
    mana(s, B=5)
    act(s, 'p1', type='cast_spell', card_id=source.id, x_value=2, targets=[elf.id, bear.id], target_counts=[2])
    act(s, 'p1', type='move', card_ids=[elf.id], to={'player': 'p1', 'zone': 'exile'})
    settle(s)
    assert s.state.cards[elf.id].zone == 'p1:exile'
    assert s.state.cards[bear.id].zone == 'p1:battlefield'
    roundtrip(s)


def test_x_cost_creature_has_zero_mana_value_in_graveyard_and_enters_without_paid_x(cards):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import roundtrip, settle

    s, source, dead, _ = setup_graveyard(cards)
    ballista = dead['Walking Ballista']
    mana(s, B=6)
    act(s, 'p1', type='cast_spell', card_id=source.id, x_value=3, targets=[ballista.id], target_counts=[1])
    settle(s)
    # It entered as a 0/0 with no counters, and the state-based action put it back.
    assert s.state.cards[ballista.id].zone == 'p1:graveyard'
    assert not s.state.cards[ballista.id].counters
    roundtrip(s)


@pytest.mark.parametrize('pay', [False, True])
def test_modal_land_face_still_offers_life_or_tapped_entry(cards, pay):
    from tests.game_helpers import act
    from tests.test_rules_designations import put, roundtrip, settle
    from tests.test_rules_shared_damage_choices import table

    s = table(cards, [NAME], [], [])
    source = put(s, NAME, 'hand')
    act(s, 'p1', type='play_land', card_id=source.id, face=1, pay_life=pay)
    settle(s)
    assert s.state.cards[source.id].zone == 'p1:battlefield'
    assert s.state.cards[source.id].tapped == (not pay)
    assert s.state.players['p1'].life == (37 if pay else 40)
    roundtrip(s)

"""CR 110.4, 608.2d/h: shared permanent types and optional return choices."""
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
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/shared_permanent_return_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()



NAME = 'Cloudstone Curio'


def test_curio_is_full(cards):
    assert coverage.of_card_data(cards.resolve(NAME)).level == 'FULL'


def setup_enter(cards, name='Grizzly Bears', *, stop_before_trigger=False):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import put, settle
    from tests.test_rules_shared_damage_choices import table

    s = table(cards, [NAME, name, 'Llanowar Elves', 'Sol Ring', 'Propaganda', 'Island'], ['Grizzly Bears'])
    curio = put(s, NAME, 'battlefield')
    available = {n: put(s, n, 'battlefield') for n in ['Llanowar Elves', 'Propaganda', 'Island', 'Forest']}
    # The Ring is the entering artifact for that scenario; otherwise it is another available type.
    if name != 'Sol Ring':
        available['Sol Ring'] = put(s, 'Sol Ring', 'battlefield')
    other = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    entering = put(s, name, 'hand')
    if name in {'Island', 'Darksteel Citadel'}:
        act(s, 'p1', type='play_land', card_id=entering.id)
    else:
        mana(s, G=4)
        act(s, 'p1', type='cast_spell', card_id=entering.id)
    if stop_before_trigger:
        for _ in range(10):
            if s.state.cards[entering.id].zone == 'p1:battlefield':
                break
            assert s.state.rules.decision is None
            act(s, s.state.rules.priority, type='pass_priority')
        assert s.state.cards[entering.id].zone == 'p1:battlefield'
    else:
        settle(s)
    return s, curio, entering, available, other


@pytest.mark.parametrize('name,allowed', [('Grizzly Bears', {'Llanowar Elves'}),
                                         ('Courser of Kruphix', {'Llanowar Elves', 'Propaganda'})])
@pytest.mark.parametrize('decline', [False, True])
def test_one_optional_nontargeted_return_with_branch_union_and_opponent_exclusion(cards, name, allowed, decline):
    from tests.game_helpers import act
    from tests.test_rules_designations import roundtrip, settle

    s, _, entering, available, other = setup_enter(cards, name)
    d = s.state.rules.decision
    assert d and d.min_choices == 0 and d.max_choices == 1
    assert {s.state.cards[o.card_id].name for o in d.options} == allowed
    assert entering.id not in {o.id for o in d.options} and other.id not in {o.id for o in d.options}
    picked = available['Llanowar Elves']
    roundtrip(s)
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[] if decline else [picked.id])
    settle(s)
    assert s.state.cards[picked.id].zone == ('p1:battlefield' if decline else 'p1:hand')
    roundtrip(s)


@pytest.mark.parametrize('name', ['Sol Ring', 'Darksteel Citadel'])
def test_artifacts_including_artifact_lands_do_not_trigger(cards, name):
    from tests.test_rules_designations import roundtrip

    s, _, _, _, _ = setup_enter(cards, name)
    assert s.state.rules.decision is None
    roundtrip(s)


@pytest.mark.parametrize('change', ['leave', 'blink', 'curio_leaves'])
def test_event_last_known_types_and_another_object_identity(cards, change):
    from tests.game_helpers import act
    from tests.test_rules_designations import roundtrip, settle

    s, curio, entering, available, _ = setup_enter(cards, stop_before_trigger=True)
    departing = curio if change == 'curio_leaves' else entering
    act(s, 'p1', type='move', card_ids=[departing.id], to={'player': 'p1', 'zone': 'graveyard'})
    if change == 'blink':
        act(s, 'p1', type='move', card_ids=[entering.id], to={'player': 'p1', 'zone': 'battlefield'})
    settle(s)
    d = s.state.rules.decision
    assert d and available['Llanowar Elves'].id in {o.id for o in d.options}
    assert (entering.id in {o.id for o in d.options}) == (change == 'blink')
    roundtrip(s)
    act(s, 'p1', type='choose', decision_id=d.id,
        option_ids=[entering.id if change == 'blink' else available['Llanowar Elves'].id])
    settle(s)
    assert s.state.cards[entering.id if change == 'blink' else available['Llanowar Elves'].id].zone == 'p1:hand'
    roundtrip(s)


def test_land_entry_can_return_another_land(cards):
    from tests.game_helpers import act
    from tests.test_rules_designations import roundtrip, settle

    s, _, entering, available, _ = setup_enter(cards, 'Island')
    d = s.state.rules.decision
    assert d and {o.id for o in d.options} == {available['Forest'].id}
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[available['Forest'].id])
    settle(s)
    assert s.state.cards[available['Forest'].id].zone == 'p1:hand'
    assert s.state.cards[entering.id].zone == 'p1:battlefield'
    roundtrip(s)


@pytest.mark.parametrize('change', ['blink', 'control'])
def test_stale_choice_does_not_return_a_new_object_or_opponents_permanent(cards, change):
    from tests.game_helpers import act
    from tests.test_rules_designations import roundtrip, settle

    s, _, _, available, _ = setup_enter(cards)
    d = s.state.rules.decision
    assert d
    elf = available['Llanowar Elves']
    if change == 'blink':
        act(s, 'p1', type='move', card_ids=[elf.id], to={'player': 'p1', 'zone': 'graveyard'})
        act(s, 'p1', type='move', card_ids=[elf.id], to={'player': 'p1', 'zone': 'battlefield'})
    else:
        act(s, 'p1', type='set_controller', card_ids=[elf.id], player='p2')
    roundtrip(s)
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[elf.id])
    settle(s)
    assert s.state.cards[elf.id].zone == ('p1:battlefield' if change == 'blink' else 'p2:battlefield')
    roundtrip(s)

"""CR 608.2b–d: optional tap/untap instructions in a sequence."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_designations import build, put, roundtrip, settle


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/optional_tap_sequences_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='ots', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


@pytest.mark.parametrize('name', ['Toils of Night and Day', 'Hidden Strings', 'Vedalken Anatomist', 'Telekinetic Bonds'])
def test_real_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


@pytest.mark.parametrize('first,second', [('tap', 'untap'), ('none', 'tap'), ('tap', 'none')])
def test_toils_has_two_independent_optional_choices(cards, first, second):
    from tests.test_rules_designations import pick

    s = build(cards, ['Toils of Night and Day', 'Sol Ring', 'Grizzly Bears'])
    ring = put(s, 'Sol Ring', 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    act(s, 'p1', type='tap', card_ids=[bear.id], tapped=True)
    spell = put(s, 'Toils of Night and Day', 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 2, 'U': 1})
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[ring.id, bear.id], target_counts=[1, 1])
    settle(s)
    d = s.state.rules.decision
    assert d is not None and {o.id for o in d.options} == {'tap', 'untap', 'none'}
    pick(s, [first])
    roundtrip(s)
    d = s.state.rules.decision
    assert d is not None and {o.id for o in d.options} == {'tap', 'untap', 'none'}
    pick(s, [second])
    settle(s)
    assert s.state.cards[ring.id].tapped == (first == 'tap')
    assert s.state.cards[bear.id].tapped == (second != 'untap')
    roundtrip(s)


def test_toils_requires_a_different_second_target(cards):
    s = build(cards, ['Toils of Night and Day', 'Sol Ring'])
    ring = put(s, 'Sol Ring', 'battlefield')
    spell = put(s, 'Toils of Night and Day', 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 2, 'U': 1})
    before = s.state.model_dump(mode='json')
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[ring.id, ring.id], target_counts=[1, 1])
    assert before == s.state.model_dump(mode='json')
    roundtrip(s)


@pytest.mark.parametrize('choice', ['tap', 'untap', 'none'])
def test_anatomist_refers_to_the_creature_that_received_the_counter(cards, choice):
    from tests.test_rules_designations import pick
    from tests.test_rules_wave34b_activated import next_turn

    s = build(cards, ['Vedalken Anatomist', 'Grizzly Bears'])
    source = put(s, 'Vedalken Anatomist', 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    next_turn(s)
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 2, 'U': 1})
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=0, targets=[bear.id])
    settle(s)
    assert s.state.cards[bear.id].counters.get('-1/-1') == 1
    d = s.state.rules.decision
    assert d is not None
    if d.kind == 'confirm':
        pick(s, ['no' if choice == 'none' else 'yes'])
        settle(s)
        if choice != 'none':
            pick(s, [choice])
    else:
        pick(s, [choice])
    settle(s)
    assert s.state.cards[bear.id].tapped == (choice == 'tap')
    roundtrip(s)


@pytest.mark.parametrize('pay,choice', [(False, None), (True, 'tap'), (True, 'none')])
def test_bonds_chooses_target_before_optional_payment(cards, pay, choice):
    from tests.test_rules_designations import pick
    from tests.test_rules_wave31d_spell_copies import hold

    s = build(cards, ['Telekinetic Bonds', 'Thrill of Possibility', 'Sol Ring', 'Lightning Bolt'])
    put(s, 'Telekinetic Bonds', 'battlefield')
    ring = put(s, 'Sol Ring', 'battlefield')
    spell = put(s, 'Thrill of Possibility', 'hand')
    payment = put(s, 'Lightning Bolt', 'hand')
    hold(s)
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 2, 'R': 1, 'U': 1})
    act(s, 'p1', type='cast_spell', card_id=spell.id, cost_choices=[{'component': 0, 'cards': [payment.id]}])
    d = s.state.rules.decision
    assert d is not None and 'choose a target' in d.prompt and any(o.id == ring.id for o in d.options)
    pick(s, [ring.id])
    roundtrip(s)
    settle(s)
    d = s.state.rules.decision
    assert d is not None and {o.id for o in d.options} == {'pay', 'decline'}
    pick(s, ['pay' if pay else 'decline'])
    settle(s)
    if pay:
        d = s.state.rules.decision
        assert d is not None and {o.id for o in d.options} == {'tap', 'untap', 'none'}
        pick(s, [choice])
        settle(s)
    assert s.state.cards[ring.id].tapped == (choice == 'tap')
    assert s.state.players['p1'].mana.get('U', 0) == (0 if pay else 1)
    roundtrip(s)


@pytest.mark.parametrize('gone', [0, 1, 2])
def test_illegal_targets_are_skipped_independently(cards, gone):
    from tests.test_rules_designations import pick
    from tests.test_rules_wave31d_spell_copies import hold

    s = build(cards, ['Toils of Night and Day', 'Sol Ring', 'Grizzly Bears'])
    ring = put(s, 'Sol Ring', 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    spell = put(s, 'Toils of Night and Day', 'hand')
    hold(s)
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 2, 'U': 1})
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[ring.id, bear.id], target_counts=[1, 1])
    ids = [ring.id] if gone == 0 else [bear.id] if gone == 1 else [ring.id, bear.id]
    act(s, 'p1', type='move', card_ids=ids, to={'player': 'p1', 'zone': 'exile'})
    settle(s)
    if gone != 2:
        d = s.state.rules.decision
        assert d is not None and {o.id for o in d.options} == {'tap', 'untap', 'none'}
        pick(s, ['tap'])
        settle(s)
        survivor = bear.id if gone == 0 else ring.id
        assert s.state.cards[survivor].tapped
    assert s.state.rules.decision is None
    assert s.state.cards[spell.id].zone == 'p1:graveyard'
    roundtrip(s)


def test_hidden_strings_encodes_and_recasts_with_two_targets(cards):
    from tests.test_rules_designations import pick
    from tests.test_rules_wave34b_activated import next_turn

    s = build(cards, ['Hidden Strings', 'Sol Ring', 'Grizzly Bears'])
    ring = put(s, 'Sol Ring', 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    next_turn(s)
    spell = put(s, 'Hidden Strings', 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 1, 'U': 1})
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[ring.id, bear.id], target_counts=[1, 1])
    settle(s)
    pick(s, ['tap'])
    pick(s, ['none'])
    settle(s)
    d = s.state.rules.decision
    assert d is not None and any(o.id == bear.id for o in d.options)
    pick(s, [bear.id])
    settle(s)
    assert s.state.cards[spell.id].zone == 'p1:exile' and s.state.cards[ring.id].tapped
    roundtrip(s)
    act(s, 'p1', type='pass_priority')
    act(s, 'p1', type='declare_attackers', attackers=[{'card_id': bear.id, 'target': 'p2'}])
    tap_choices = 0
    target_choices = 0
    for _ in range(60):
        d = s.state.rules.decision
        if d is None:
            if s.state.turn.phase == 'main2' and not s.state.zones.get('stack'):
                break
            act(s, s.state.rules.priority, type='pass_priority')
            continue
        ids = [o.id for o in d.options]
        if 'untap' in ids and 'tap' in ids:
            pick(s, ['untap' if tap_choices == 0 else 'none'])
            tap_choices += 1
        elif ring.id in ids and 'target' in d.prompt.lower():
            pick(s, [ring.id])
            target_choices += 1
        elif bear.id in ids and 'target' in d.prompt.lower():
            pick(s, [bear.id])
            target_choices += 1
        else:
            pick(s, ['yes'] if 'yes' in ids else ids[:1])
    assert tap_choices == 2 and target_choices == 2
    assert not s.state.cards[ring.id].tapped and s.state.players['p2'].life == 38
    assert s.state.cards[spell.id].zone == 'p1:exile'
    roundtrip(s)


def test_anatomist_finishes_its_choices_before_zero_toughness_state_actions(cards):
    from tests.test_rules_designations import pick
    from tests.test_rules_wave34b_activated import next_turn

    s = build(cards, ['Vedalken Anatomist', 'Llanowar Elves'])
    source = put(s, 'Vedalken Anatomist', 'battlefield')
    elf = put(s, 'Llanowar Elves', 'battlefield')
    next_turn(s)
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 2, 'U': 1})
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=0, targets=[elf.id])
    settle(s)
    assert s.state.rules.decision is not None
    assert s.state.cards[elf.id].zone == 'p1:battlefield'
    roundtrip(s)
    pick(s, ['tap'])
    settle(s)
    assert s.state.cards[elf.id].zone == 'p1:graveyard'
    roundtrip(s)

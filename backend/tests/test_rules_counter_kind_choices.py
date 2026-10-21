"""Printed counter-kind alternatives use real entry and resolution choices."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_remaining_talents import pay
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave7b_activation import ability_index

NAMES = ['Reluctant Role Model', 'Elspeth Resplendent', 'Invoke the Ancients', 'Denry Klin, Editor in Chief']


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/counter_kind_choice_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='ckc', number=str(i), **{k:v for k,v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def game(cards):
    return table(cards, [*NAMES, 'Grizzly Bears', 'Doubling Season', 'Hardened Scales', 'Solemnity', 'All Will Be One'],
                 ['Vorinclex, Monstrous Raider', 'Shock', 'Disenchant'], ['Grizzly Bears'])


def cast(s, name):
    obj = put(s, name, 'hand')
    pay(s, 'p1', name)
    act(s, 'p1', type='cast_spell', card_id=obj.id, sources=[])
    settle(s)
    return obj


def choose(s, kind):
    d = s.state.rules.decision
    assert d and kind in {o.id for o in d.options}, (d.kind if d else None, d.prompt if d else None)
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[kind])
    settle(s)


@pytest.mark.parametrize('name', NAMES)
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


@pytest.mark.parametrize('kind', ['+1/+1', 'first strike', 'vigilance'])
def test_denry_actual_entry_choice(cards, kind):
    s = game(cards)
    source = cast(s, 'Denry Klin, Editor in Chief')
    roundtrip(s)
    choose(s, kind)
    assert s.state.cards[source.id].zone == 'p1:battlefield'
    assert s.state.cards[source.id].counters == {kind:2}  # Denry's own nontoken entry also triggers its copying ability.
    roundtrip(s)


def test_invoke_each_token_has_independent_choice_including_doubled_tokens(cards):
    s = game(cards)
    put(s, 'Doubling Season', 'battlefield')
    cast(s, 'Invoke the Ancients')
    for kind in ['reach', 'vigilance', 'trample', 'reach']:
        roundtrip(s)
        choose(s, kind)
    tokens = [c for c in s.state.cards.values() if c.is_token and c.zone == 'p1:battlefield']
    assert len(tokens) == 4
    assert sorted(tuple(c.counters.items()) for c in tokens) == sorted([(('reach',2),), (('vigilance',2),), (('trample',2),), (('reach',2),)])
    assert all(Plan(s.state, 'p1', cards, None).ch(c).pt == (4,5) for c in tokens)
    roundtrip(s)


@pytest.mark.parametrize('kind', ['flying', 'first strike', 'lifelink', 'vigilance'])
def test_elspeth_fixed_and_chosen_counter_are_one_native_placement(cards, kind):
    s = game(cards)
    walker = cast(s, 'Elspeth Resplendent')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    act(s, 'p1', type='activate_ability', card_id=walker.id, ability=ability_index(s, walker, 'Choose up to one'),
        targets=[bear.id], target_counts=[1])
    settle(s)
    roundtrip(s)
    choose(s, kind)
    assert s.state.cards[walker.id].counters['loyalty'] == 6
    assert s.state.cards[bear.id].counters == {'+1/+1':1, kind:1}
    events = [e for e in s.state.rules.events if e.kind == 'counters' and e.card == bear.id and not e.manual]
    assert len(events) == 2 and events[0].group and events[0].group == events[1].group
    roundtrip(s)


@pytest.mark.parametrize('kind', ['flying', 'lifelink', '+1/+1'])
def test_role_model_survival_checks_tapped_and_offers_printed_kinds(cards, kind):
    from tests.test_rules_wave30m_durations import to_phase
    s = game(cards)
    source = cast(s, 'Reluctant Role Model')
    act(s, 'p1', type='tap', card_ids=[source.id], tapped=True)
    to_phase(s, 'main2')
    settle(s)
    choose(s, kind)
    assert s.state.cards[source.id].counters == {kind:1}
    roundtrip(s)


def test_role_model_untapped_survival_does_not_trigger(cards):
    from tests.test_rules_wave30m_durations import to_phase
    s = game(cards)
    source = cast(s, 'Reluctant Role Model')
    to_phase(s, 'main2')
    settle(s)
    assert s.state.rules.decision is None
    assert not s.state.cards[source.id].counters
    roundtrip(s)


def test_denry_nontoken_entry_copies_current_counters_through_replacements(cards):
    s = game(cards)
    put(s, 'Doubling Season', 'battlefield')
    source = cast(s, 'Denry Klin, Editor in Chief')
    choose(s, 'vigilance')
    assert s.state.cards[source.id].counters == {'vigilance':6}  # enters with2, own ETB adds another4.
    bear = cast(s, 'Grizzly Bears')
    assert s.state.cards[bear.id].counters == {'vigilance':12}
    # Token creatures do not copy Denry's counters.
    act(s, 'p1', type='create_token', player='p1', token={'name':'Test', 'power':'1', 'toughness':'1', 'type_line':'Token Creature', 'colors':[]})
    settle(s)
    tokens = [c for c in s.state.cards.values() if c.is_token]
    assert all(not c.counters for c in tokens)
    roundtrip(s)


def test_elspeth_zero_target_pays_loyalty_without_counter_choice(cards):
    s = game(cards)
    walker = cast(s, 'Elspeth Resplendent')
    act(s, 'p1', type='activate_ability', card_id=walker.id, ability=ability_index(s, walker, 'Choose up to one'),
        targets=[], target_counts=[0])
    settle(s)
    d = s.state.rules.decision
    if d is not None:
        assert d.min_choices == 0
        act(s, d.player, type='choose', decision_id=d.id, option_ids=[])
        settle(s)
    assert s.state.rules.decision is None
    assert s.state.cards[walker.id].counters['loyalty'] == 6
    roundtrip(s)


def test_elspeth_pending_kind_choice_does_not_follow_new_target_object(cards):
    s = game(cards)
    walker = cast(s, 'Elspeth Resplendent')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    act(s, 'p1', type='activate_ability', card_id=walker.id, ability=ability_index(s, walker, 'Choose up to one'),
        targets=[bear.id], target_counts=[1])
    settle(s)
    act(s, 'p1', type='move', card_ids=[bear.id], to={'player':'p1', 'zone':'exile'})
    act(s, 'p1', type='move', card_ids=[bear.id], to={'player':'p1', 'zone':'battlefield'})
    choose(s, 'flying')
    assert not s.state.cards[bear.id].counters
    roundtrip(s)


def test_elspeth_minus_three_enters_with_shield_before_damage(cards):
    from tests.test_rules_abundance import set_library
    from tests.test_rules_bandmate_references import wait_priority
    s = game(cards)
    walker = cast(s, 'Elspeth Resplendent')
    set_library(s, ['Grizzly Bears', 'Reluctant Role Model', 'Invoke the Ancients', 'Denry Klin, Editor in Chief',
                    'Doubling Season', 'Hardened Scales', 'Solemnity'])
    act(s, 'p1', type='activate_ability', card_id=walker.id, ability=ability_index(s, walker, 'Look at the top seven'))
    settle(s)
    d = s.state.rules.decision
    bear = next(c for c in s.state.cards.values() if c.name == 'Grizzly Bears' and c.owner == 'p1')
    assert d and bear.id in {o.id for o in d.options}
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[bear.id])
    settle(s)
    assert s.state.cards[bear.id].zone == 'p1:battlefield'
    assert s.state.cards[bear.id].counters == {'shield':1}
    assert s.state.cards[walker.id].counters['loyalty'] == 2
    spell = put(s, 'Shock', 'hand', pid='p2')
    pay(s, 'p2', 'Shock')
    wait_priority(s, 'p2')
    act(s, 'p2', type='cast_spell', card_id=spell.id, targets=[bear.id], sources=[])
    settle(s)
    assert s.state.cards[bear.id].zone == 'p1:battlefield' and s.state.cards[bear.id].damage == 0
    assert not s.state.cards[bear.id].counters
    roundtrip(s)


def test_chosen_kind_is_not_asked_again_during_counter_replacement_order(cards):
    s = game(cards)
    walker = cast(s, 'Elspeth Resplendent')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    put(s, 'Doubling Season', 'battlefield')
    put(s, 'Vorinclex, Monstrous Raider', 'battlefield', pid='p2')
    act(s, 'p1', type='activate_ability', card_id=walker.id, ability=ability_index(s, walker, 'Choose up to one'),
        targets=[bear.id], target_counts=[1])
    settle(s)
    d = s.state.rules.decision
    assert d and 'flying' in {o.id for o in d.options}
    act(s, d.player, type='choose', decision_id=d.id, option_ids=['flying'])
    orders = 0
    for _ in range(15):
        settle(s)
        d = s.state.rules.decision
        if d is None:
            break
        assert (d.resume or {}).get('step') != 'counter_kind_choice'
        assert 'replacement' in d.prompt.lower() or 'apply' in d.prompt.lower(), (d.kind, d.prompt)
        roundtrip(s)
        option = next((o for o in d.options if 'Doubling Season' in o.label), d.options[0])
        act(s, d.player, type='choose', decision_id=d.id, option_ids=[option.id])
        orders += 1
    assert orders > 0
    assert s.state.cards[bear.id].counters == {'+1/+1':1, 'flying':1}
    roundtrip(s)


def test_invoke_saved_counter_choice_resumes_in_fresh_process(cards, tmp_path):
    import subprocess
    import sys
    s = game(cards)
    cast(s, 'Invoke the Ancients')
    assert s.state.rules.decision and (s.state.rules.decision.resume or {}).get('step') == 'counter_kind_choice'
    saved = tmp_path / 'invoke.json'
    saved.write_text(s.state.model_dump_json())
    code = r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
state_path, database = sys.argv[1:]
repo = CardRepository(Path(database), ImageStore(Path(database).parent / 'images'))
s = GameSession(GameState.model_validate_json(Path(state_path).read_text()), cards=repo)
for kind in ['reach','trample']:
    d = s.state.rules.decision
    assert d.resume['step'] == 'counter_kind_choice'
    s.perform(d.player, {'type':'choose','decision_id':d.id,'option_ids':[kind]})
tokens = [c for c in s.state.cards.values() if c.is_token and c.zone == 'p1:battlefield']
assert sorted(tuple(c.counters.items()) for c in tokens) == [(('reach',1),),(('trample',1),)]
assert s.history.rebuild().model_dump(mode='json') == s.state.model_dump(mode='json')
assert GameState.model_validate_json(s.state.model_dump_json()).model_dump(mode='json') == s.state.model_dump(mode='json')
repo.close()
'''
    result = subprocess.run([sys.executable, '-c', code, str(saved), str(cards.db_path)],
                            cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr


def test_denry_entry_trigger_keeps_source_counters_when_denry_dies_before_resolution(cards):
    from tests.test_rules_bandmate_references import wait_priority
    s = game(cards)
    source = cast(s, 'Denry Klin, Editor in Chief')
    choose(s, 'first strike')
    bear = put(s, 'Grizzly Bears', 'hand')
    pay(s, 'p1', 'Grizzly Bears')
    act(s, 'p1', type='cast_spell', card_id=bear.id, sources=[])
    for _ in range(20):
        if s.state.cards[bear.id].zone == 'p1:battlefield':
            break
        act(s, s.state.rules.priority, type='pass_priority')
    assert any(e.source_card == source.id for e in s.state.rules.stack.values())
    shock = put(s, 'Shock', 'hand', pid='p2')
    pay(s, 'p2', 'Shock')
    wait_priority(s, 'p2')
    act(s, 'p2', type='cast_spell', card_id=shock.id, targets=[source.id], sources=[])
    settle(s)
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    assert s.state.cards[bear.id].counters == {'first strike':2}
    roundtrip(s)


def test_denry_cannot_receive_counters_under_solemnity(cards):
    s = game(cards)
    put(s, 'Solemnity', 'battlefield')
    source = cast(s, 'Denry Klin, Editor in Chief')
    choose(s, 'vigilance')
    assert s.state.cards[source.id].zone == 'p1:battlefield'
    assert not s.state.cards[source.id].counters
    assert s.state.rules.decision is None
    roundtrip(s)


def test_role_model_death_trigger_transfers_its_chosen_keyword_counter(cards):
    from tests.test_rules_bandmate_references import wait_priority
    from tests.test_rules_wave30m_durations import to_phase
    s = game(cards)
    source = cast(s, 'Reluctant Role Model')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    act(s, 'p1', type='tap', card_ids=[source.id], tapped=True)
    to_phase(s, 'main2')
    settle(s)
    choose(s, 'flying')
    shock = put(s, 'Shock', 'hand', pid='p2')
    pay(s, 'p2', 'Shock')
    wait_priority(s, 'p2')
    act(s, 'p2', type='cast_spell', card_id=shock.id, targets=[source.id], sources=[])
    settle(s)
    choose(s, bear.id)
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    assert s.state.cards[bear.id].counters == {'flying':1}
    roundtrip(s)

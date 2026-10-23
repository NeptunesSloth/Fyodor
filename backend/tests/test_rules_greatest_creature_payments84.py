"""Tariff uses actual current greatest mana value and colored payment cost."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from app.rules.mana_units import visible_pool
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_bandmate_references import wait_priority
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_look import settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

DATA = json.loads((Path(__file__).parent / 'fixtures/tariff84_cards.json').read_text())
ALL = [c['name'] for c in DATA] + ['Grizzly Bears', 'Llanowar Elves', 'Sol Ring', 'Forest']


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(DATA):
        base[c['name']] = card(c['name'], number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def game(cards):
    s = table(cards, ALL, ALL, ALL)
    to_phase(s, 'main1', 1)
    return s


def choose(s, ids):
    d = s.state.rules.decision
    assert d is not None
    act(s, d.player, type='choose', decision_id=d.id, option_ids=ids)
    settle(s)


def cast(s, name):
    c = put(s, name, 'hand')
    wait_priority(s, 'p1')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 1, 'W': 1})
    act(s, 'p1', type='cast_spell', card_id=c.id, targets=[], sources=[])
    settle(s)
    return c


def test_whole_tariff(cards):
    assert coverage.of_card_data(cards.resolve('Tariff')).level == 'FULL'


def test_highest_creatures_pay_actual_colored_cost_not_mana_value(cards):
    s = game(cards)
    bear = put(s, 'Grizzly Bears', 'battlefield')
    tiny = put(s, 'Ornithopter', 'battlefield')
    elves = put(s, 'Llanowar Elves', 'battlefield', 'p2')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 1, 'G': 1})
    act(s, 'p2', type='add_mana', player='p2', mana={'G': 1})
    cast(s, 'Tariff')
    assert s.state.rules.decision.player == 'p1'
    choose(s, ['pay'])
    assert s.state.rules.decision.player == 'p2'
    assert visible_pool(s.state, 'p1') == {}
    choose(s, ['decline'])
    assert s.state.cards[bear.id].zone == s.state.cards[tiny.id].zone == 'p1:battlefield'
    assert s.state.cards[elves.id].zone == 'p2:graveyard'
    roundtrip(s)


def test_equal_mana_value_player_chooses_exact_creature_not_arbitrary_physical_id(cards):
    s = game(cards)
    bear = put(s, 'Grizzly Bears', 'battlefield')
    other = put(s, 'Runeclaw Bear', 'battlefield')
    cast(s, 'Tariff')
    d = s.state.rules.decision
    assert d.player == 'p1' and d.resume['step'] == 'greatest_creature84'
    assert {o.id for o in d.options} == {bear.id, other.id}
    choose(s, [other.id])
    assert s.state.cards[other.id].zone == 'p1:graveyard' and s.state.cards[bear.id].zone == 'p1:battlefield'


def test_all_declined_sacrifices_wait_for_remaining_player_and_share_one_batch(cards):
    s = game(cards)
    bear = put(s, 'Grizzly Bears', 'battlefield')
    other = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 1, 'G': 1})
    act(s, 'p2', type='add_mana', player='p2', mana={'C': 1, 'G': 1})
    cast(s, 'Tariff')
    choose(s, ['decline'])
    assert s.state.cards[bear.id].zone == 'p1:battlefield' and s.state.rules.decision.player == 'p2'
    choose(s, ['decline'])
    assert s.state.cards[bear.id].zone == 'p1:graveyard' and s.state.cards[other.id].zone == 'p2:graveyard'
    moved = [e for e in s.state.rules.events if e.kind == 'zone_change' and e.card in {bear.id, other.id}]
    assert len(moved) == 2 and len({e.batch for e in moved}) == 1
    roundtrip(s)


def test_generic_mana_value_cannot_replace_required_color(cards):
    s = game(cards)
    bear = put(s, 'Grizzly Bears', 'battlefield')
    elves = put(s, 'Llanowar Elves', 'battlefield', 'p2')
    act(s, 'p1', type='add_mana', player='p1', mana={'W': 2})
    act(s, 'p2', type='add_mana', player='p2', mana={'G': 1})
    cast(s, 'Tariff')
    assert s.state.rules.decision.player == 'p2'
    assert s.state.cards[bear.id].zone == 'p1:battlefield'
    choose(s, ['pay'])
    assert s.state.cards[bear.id].zone == 'p1:graveyard' and s.state.cards[elves.id].zone == 'p2:battlefield'
    assert visible_pool(s.state, 'p1') == {'W': 2}


def test_zero_printed_cost_is_payable_but_absent_token_cost_is_not(cards):
    s = game(cards)
    cast(s, 'Raise the Alarm')
    tokens = [c for c in s.state.cards.values() if c.zone == 'p1:battlefield' and c.token]
    assert len(tokens) == 2
    ornithopter = put(s, 'Ornithopter', 'battlefield', 'p2')
    cast(s, 'Tariff')
    d = s.state.rules.decision
    assert {o.id for o in d.options} == {c.id for c in tokens}
    chosen = tokens[0].id
    choose(s, [chosen])
    assert s.state.rules.decision.player == 'p2'
    assert s.state.cards[chosen].zone == 'p1:battlefield'
    choose(s, ['pay'])
    assert chosen not in s.state.cards or s.state.cards[chosen].zone != 'p1:battlefield'
    assert s.state.cards[ornithopter.id].zone == 'p2:battlefield'
    assert sum(c.zone == 'p1:battlefield' and c.is_token for c in s.state.cards.values()) == 1
    roundtrip(s)


def test_native_mana_ability_may_sacrifice_chosen_original_during_offer_without_second_sacrifice(cards):
    s = game(cards)
    bear = put(s, 'Grizzly Bears', 'battlefield')
    ornithopter = put(s, 'Ornithopter', 'battlefield', 'p2')
    altar = put(s, "Ashnod's Altar", 'battlefield', 'p2')
    act(s, 'p2', type='set_prefs', payment='self')
    cast(s, 'Tariff')
    assert s.state.rules.decision.player == 'p2'
    assert s.state.cards[bear.id].zone == 'p1:battlefield'
    act(s, 'p2', type='activate_ability', card_id=altar.id, ability=0,
        sources=[], cost_choices=[{'component': 0, 'cards': [ornithopter.id]}])
    assert s.state.cards[ornithopter.id].zone == 'p2:graveyard'
    choose(s, ['pay'])
    assert s.state.cards[bear.id].zone == 'p1:graveyard'
    events = [e for e in s.state.rules.events if e.kind == 'sacrificed' and e.card == ornithopter.id]
    assert len(events) == 1
    assert visible_pool(s.state, 'p2') == {'C': 2}
    roundtrip(s)


def test_opponent_cannot_force_sigarda_sacrifice_when_actual_colored_cost_cannot_be_paid(cards):
    s = game(cards)
    sigarda = put(s, 'Sigarda, Host of Herons', 'battlefield', 'p2')
    bear = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    cast(s, 'Tariff')
    assert s.state.rules.decision is None
    assert s.state.cards[sigarda.id].zone == s.state.cards[bear.id].zone == 'p2:battlefield'
    roundtrip(s)


def test_true_cold_apnap_tariff_offer_preserves_earlier_decline_and_original_creature(cards, tmp_path):
    import os
    import subprocess
    import sys

    import app

    s = game(cards)
    earlier = put(s, 'Grizzly Bears', 'battlefield')
    later = put(s, 'Llanowar Elves', 'battlefield', 'p2')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 1, 'G': 1})
    act(s, 'p2', type='add_mana', player='p2', mana={'G': 1})
    cast(s, 'Tariff')
    choose(s, ['decline'])
    assert s.state.rules.decision.player == 'p2'
    assert s.state.cards[earlier.id].zone == 'p1:battlefield'
    saved = tmp_path / 'tariff.json'
    saved.write_text(s.state.model_dump_json())
    backend = Path(app.__file__).resolve().parents[1]
    code = r'''
import sys
from pathlib import Path
from app.cards.repository import CardRepository
from app.cards.images import ImageStore
from app.game.session import GameSession
from app.game.state import GameState
from tests.game_helpers import act
from tests.test_rules_library_look import settle
from tests.test_rules_designations import roundtrip
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
earlier,later=sys.argv[3:]
d=s.state.rules.decision
assert d and d.player=='p2'
assert s.state.cards[earlier].zone=='p1:battlefield'
act(s,d.player,type='choose',decision_id=d.id,option_ids=['pay'])
settle(s)
assert s.state.cards[earlier].zone=='p1:graveyard'
assert s.state.cards[later].zone=='p2:battlefield'
assert not s.state.rules.decision and not s.state.players['p2'].mana
roundtrip(s)
repo.close()
'''
    result = subprocess.run([sys.executable, '-c', code, str(saved), str(cards.db_path), earlier.id, later.id],
                            cwd=backend, env={**os.environ, 'PYTHONPATH': str(backend) + os.pathsep + os.environ.get('PYTHONPATH', '')},
                            capture_output=True, text=True, timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr


def test_zero_floating_mana_nonzero_tariff_offer_allows_native_altar_activation_and_atomic_early_pay_rejection(cards):
    from app.game.errors import ActionError

    s = game(cards)
    creature = put(s, 'Myr Retriever', 'battlefield', 'p2')
    altar = put(s, "Ashnod's Altar", 'battlefield', 'p2')
    cast(s, 'Tariff')
    d = s.state.rules.decision
    assert d and d.player == 'p2' and d.resume['step'] == 'pay_or_sacrifice'
    before = s.state.model_dump(mode='json')
    with pytest.raises(ActionError, match='Activate your mana abilities first'):
        act(s, 'p2', type='choose', decision_id=d.id, option_ids=['pay'])
    assert s.state.model_dump(mode='json') == before
    act(s, 'p2', type='activate_ability', card_id=altar.id, ability=0, sources=[],
        cost_choices=[{'component': 0, 'cards': [creature.id]}])
    choose(s, ['pay'])
    assert visible_pool(s.state, 'p2') == {}
    assert s.state.cards[creature.id].zone == 'p2:graveyard'
    assert s.state.rules.decision is None or s.state.rules.decision.resume['step'] == 'trigger_target'
    assert sum(e.kind == 'sacrificed' and e.card == creature.id for e in s.state.rules.events) == 1
    roundtrip(s)


def test_native_activation_sacrifice_prohibition_does_not_create_false_payment_window(cards):
    from app.rules import manual_choice_mana85
    from app.rules.plan import Plan

    s = game(cards)
    angel = put(s, 'Angel of Jubilation', 'battlefield', 'p2')
    put(s, "Ashnod's Altar", 'battlefield', 'p2')
    assert not manual_choice_mana85.available(Plan(s.state, 'p2', s.cards, None), 'p2')
    cast(s, 'Tariff')
    assert s.state.rules.decision is None or s.state.rules.decision.resume['step'] == 'trigger_target'
    assert s.state.cards[angel.id].zone == 'p2:graveyard'
    roundtrip(s)


def test_creature_spell_only_food_chain_mana_cannot_open_resolution_payment_window(cards):
    from app.rules import manual_choice_mana85
    from app.rules.plan import Plan

    s = game(cards)
    creature = put(s, 'Myr Retriever', 'battlefield', 'p2')
    put(s, 'Food Chain', 'battlefield', 'p2')
    assert not manual_choice_mana85.available(Plan(s.state, 'p2', s.cards, None), 'p2')
    cast(s, 'Tariff')
    # Myr Retriever has a genuine optional death trigger; its presence is distinct
    # from a resolution payment window.
    assert s.state.rules.decision is None or s.state.rules.decision.resume['step'] == 'trigger_target'
    assert s.state.cards[creature.id].zone == 'p2:graveyard'
    roundtrip(s)

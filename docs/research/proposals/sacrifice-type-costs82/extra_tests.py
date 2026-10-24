"""Actual changed-type/token sacrifices and saved cost-lock boundaries."""
import os
import subprocess
import sys

from tests.game_helpers import act
from tests.test_rules_activated_copy_family import answer
from tests.test_rules_bandmate_references import wait_priority
from tests.test_rules_designations import put
from tests.test_rules_sacrifice_type_costs82 import cards as _cards
from tests.test_rules_sacrifice_type_costs82 import cast, sac, setup
from tests.test_rules_wave30m_durations import to_phase

cards = _cards


def test_actual_artifact_creature_token_counts_two_without_token_type(cards):
    s, c = setup(cards)
    turbine = put(s, 'Myr Turbine', 'battlefield')
    wait_priority(s, 'p1')
    act(s, 'p1', type='activate_ability', card_id=turbine.id, ability=0, sources=[])
    answer(s)
    token = next(q for q in s.state.cards.values() if q.name == 'Myr' and q.token and q.zone == 'p1:battlefield')
    sac(s, token)
    cast(s, c, 3)


def test_actual_liquimetal_added_type_is_frozen_at_sacrifice(cards):
    s, c = setup(cards)
    target = put(s, 'Grizzly Bears', 'battlefield')
    coating = put(s, 'Liquimetal Coating', 'battlefield')
    wait_priority(s, 'p1')
    act(s, 'p1', type='activate_ability', card_id=coating.id, ability=0, targets=[target.id], sources=[])
    answer(s)
    sac(s, target)
    cast(s, c, 3)


def test_actual_prior_turn_sacrifices_expire(cards):
    s, c = setup(cards)
    sac(s, put(s, 'Gingerbrute', 'battlefield'))
    to_phase(s, 'main1', 7)
    cast(s, c, 5)


def test_true_cold_locked_price_keeps_original_receipts(cards, tmp_path):
    s, c = setup(cards)
    sac(s, put(s, 'Bitterblossom', 'battlefield'))
    wait_priority(s, 'p1')
    act(s, 'p1', type='set_prefs', payment='self')
    act(s, 'p1', type='add_mana', player='p1', mana={'B': 1, 'R': 1, 'G': 1})
    act(s, 'p1', type='cast_spell', card_id=c.id, sources=None, targets=[])
    assert s.state.rules.decision.resume['cost'] == '{3}{B}{R}{G}'
    saved = tmp_path / 'cost82.json'
    saved.write_text(s.state.model_dump_json())
    code = '''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.game_helpers import act
saved,database,cid=sys.argv[1:]
repo=CardRepository(Path(database),ImageStore(Path(database).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(saved).read_text()),cards=repo)
s.view('p1');s.view('p2')
d=s.state.rules.decision
assert d.resume['cost']=='{3}{B}{R}{G}'
act(s,'p1',type='add_mana',player='p1',mana={'C':3})
d=s.state.rules.decision
if d: act(s,'p1',type='choose',decision_id=d.id,option_ids=['pay'])
assert s.state.cards[cid].zone=='stack'
assert s.state.rules.payments[s.state.rules.object_id(cid)].total_cost=='{3}{B}{R}{G}'
assert sum(s.state.players['p1'].mana.values())==0
GameState.model_validate_json(s.state.model_dump_json())
'''
    run = subprocess.run([sys.executable, '-c', code, str(saved), str(cards.db_path), c.id], capture_output=True, text=True, env=os.environ.copy())
    assert run.returncode == 0, run.stdout + run.stderr


def test_five_distinct_card_types_reduce_only_generic_mana(cards):
    s, c = setup(cards)
    for name in ['Gingerbrute', 'Bitterblossom', 'Forest']:
        sac(s, put(s, name, 'battlefield'))
    cast(s, c, 0)


def test_actual_altar_sacrifice_during_payment_does_not_reprice_locked_total(cards):
    s, c = setup(cards)
    sac(s, put(s, 'Bitterblossom', 'battlefield'))
    altar = put(s, "Ashnod's Altar", 'battlefield')
    target = put(s, 'Gingerbrute', 'battlefield')
    wait_priority(s, 'p1')
    act(s, 'p1', type='set_prefs', payment='self')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 1, 'B': 1, 'R': 1, 'G': 1})
    act(s, 'p1', type='cast_spell', card_id=c.id, sources=None, targets=[])
    assert s.state.rules.decision.resume['cost'] == '{3}{B}{R}{G}'
    act(s, 'p1', type='activate_ability', card_id=altar.id, ability=0, sources=[],
        cost_choices=[{'component': 0, 'cards': [target.id]}])
    d = s.state.rules.decision
    if d:
        act(s, 'p1', type='choose', decision_id=d.id, option_ids=['pay'])
    assert s.state.cards[c.id].zone == 'stack'
    assert s.state.rules.payments[s.state.rules.object_id(c.id)].total_cost == '{3}{B}{R}{G}'
    assert sum(s.state.players['p1'].mana.values()) == 0

"""Saved flying receipts and mana-window draw threshold changes."""
import json
import os
import subprocess
import sys

from app.rules.plan import Plan
from tests.game_helpers import act
from tests.test_rules_bandmate_references import wait_priority
from tests.test_rules_colored_activation_costs83 import NAMES, activate, setup, spell
from tests.test_rules_colored_activation_costs83 import cards as _cards
from tests.test_rules_designations import put
from tests.test_rules_wave30m_durations import to_phase

cards = _cards


def cold(cards, s, tmp_path, extra, code, legacy=False):
    saved = tmp_path / 'colored83.json'
    data = s.state.model_dump(mode='json')
    if legacy:
        for entry in data['rules']['turn_log']['entered']:
            entry.pop('keywords83', None)
    saved.write_text(json.dumps(data))
    prefix = '''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from app.game.errors import ActionError
from app.rules.plan import Plan
from tests.game_helpers import act
from tests.test_rules_colored_activation_costs83 import activate, spell
saved,database,*args=sys.argv[1:]
repo=CardRepository(Path(database),ImageStore(Path(database).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(saved).read_text()),cards=repo)
s.view('p1');s.view('p2')
'''
    run = subprocess.run([sys.executable, '-c', prefix + code, str(saved), str(cards.db_path), *extra], capture_output=True, text=True, env=os.environ.copy())
    assert run.returncode == 0, run.stdout + run.stderr


def test_true_cold_flyer_lost_flying_uses_entry_receipt(cards, tmp_path):
    s, source = setup(cards, NAMES[0])
    flyer = spell(s, 'Ornithopter')
    spell(s, 'Turn to Frog', {'C': 1, 'U': 1}, [flyer.id])
    cold(cards, s, tmp_path, [source.id, flyer.id], '''
source,flyer=map(s.state.cards.__getitem__,args)
assert 'flying' not in Plan(s.state,'p1',repo,None).ch(flyer).keywords
activate(s,source,{},'{0}')
''')


def test_true_cold_unknown_entries_guard_only_drone_positive_native_entry_restores_it(cards, tmp_path):
    s, source = setup(cards, NAMES[0])
    spell(s, 'Ornithopter')
    wait_priority(s, 'p1')
    cold(cards, s, tmp_path, [source.id], '''
source=s.state.cards[args[0]]
index=next(a.index for a in Plan(s.state,'p1',repo,None).ch(source).abilities if a.kind=='activated')
before=s.state.model_dump_json()
try:
 act(s,'p1',type='activate_ability',card_id=source.id,ability=index,sources=[])
except ActionError as error:
 assert 'entry-time flying history' in str(error)
else: raise AssertionError('unknown history was silently priced')
assert s.state.model_dump_json()==before
spell(s,'Ornithopter')
activate(s,source,{},'{0}')
''', legacy=True)


def test_actual_previous_turn_draws_do_not_discount_kami(cards):
    s, source = setup(cards, NAMES[1])
    spell(s, 'Divination', {'C': 2, 'U': 1})
    to_phase(s, 'main1', 7)
    assert s.state.rules.turn_log.drew['p1'] == 1
    activate(s, source, {'C': 4, 'B': 1}, '{4}{B}')


def test_true_cold_actual_swamp_keeps_locked_kami_cost_and_sphere_cannot_draw_while_paying(cards, tmp_path):
    s, source = setup(cards, NAMES[1])
    spell(s, 'Opt', {'U': 1})
    sphere = put(s, 'Chromatic Sphere', 'battlefield')
    swamp = put(s, 'Swamp', 'battlefield')
    wait_priority(s, 'p1')
    act(s, 'p1', type='set_prefs', payment='self')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 4})
    index = next(a.index for a in Plan(s.state, 'p1', cards, None).ch(source).abilities if a.kind == 'activated')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=index, sources=None)
    assert s.state.rules.decision.resume['cost'] == '{4}{B}'
    cold(cards, s, tmp_path, [sphere.id, swamp.id], '''
sphere,swamp=map(s.state.cards.__getitem__,args)
index=next(a.index for a in Plan(s.state,'p1',repo,None).ch(sphere).abilities if a.kind=='activated')
before=s.state.model_dump_json()
try:
 act(s,'p1',type='activate_ability',card_id=sphere.id,ability=index,mana_choice='B',sources=[])
except ActionError as error:
 assert 'only tap for mana' in str(error)
else: raise AssertionError('nonmana Sphere activated during payment')
assert s.state.model_dump_json()==before
assert s.state.rules.turn_log.drew['p1']==2
act(s,'p1',type='activate_ability',card_id=swamp.id,ability=0,sources=[])
d=s.state.rules.decision
if d: act(s,'p1',type='choose',decision_id=d.id,option_ids=['pay'])
ability=next(c for c in s.state.cards.values() if c.zone=='stack' and c.ability is not None)
assert s.state.rules.payments[s.state.rules.object_id(ability.id)].mana_spent=={'C':4,'B':1}
assert sum(s.state.players['p1'].mana.values())==0
''')


def test_departed_flyer_entry_still_qualifies(cards):
    s, source = setup(cards, NAMES[0])
    flyer = spell(s, 'Ornithopter')
    old = s.state.rules.object_id(flyer.id)
    spell(s, 'Unsummon', {'U': 1}, [flyer.id])
    assert s.state.cards[flyer.id].zone == 'p1:hand'
    assert s.state.rules.object_id(flyer.id) != old
    activate(s, source, {}, '{0}')


def test_actual_layered_entry_without_flying_is_not_retroactive_after_sphere_leaves(cards):
    s, source = setup(cards, NAMES[0])
    sphere = spell(s, 'Gravity Sphere', {'C': 2, 'R': 1})
    flyer = spell(s, 'Ornithopter')
    entry = next(e for e in s.state.rules.turn_log.entered if e.card == flyer.id)
    assert entry.keywords83 is not None and 'flying' not in entry.keywords83
    spell(s, 'Naturalize', {'C': 1, 'G': 1}, [sphere.id])
    assert 'flying' in Plan(s.state, 'p1', cards, None).ch(s.state.cards[flyer.id]).keywords
    activate(s, source, {'C': 1, 'U': 1}, '{1}{U}')

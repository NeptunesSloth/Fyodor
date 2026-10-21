"""Fresh Python process continuations exercise production eager callback registration."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from tests import test_rules_exile_packet_continuations_staged as gameplay
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana
from tests.test_rules_controller_tutors import answer
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_look import settle
from tests.test_rules_ordered_tutor_continuations import cast
from tests.test_rules_refused_look import stack_library
from tests.test_rules_wave4h_activation_costs import ability
from tests.test_rules_wave30m_durations import to_phase

cards = gameplay.cards


def fresh_action(s, cards, path, actor, payload):
    from app.game.session import GameSession
    from app.game.state import GameState

    path.write_text(s.state.model_dump_json())
    code = '''
import json,sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
def settle(s):
    for _ in range(60):
        decision=s.state.rules.decision
        if decision is not None:
            if decision.kind == 'order' and decision.resume.get('step') != 'order_library':
                s.perform(decision.player,{'type':'choose','decision_id':decision.id,'option_ids':[o.id for o in decision.options]})
            else:
                return
        elif s.state.zones.get('stack'):
            s.perform(s.state.rules.priority,{'type':'pass_priority'})
        else:
            return
path=Path(sys.argv[1])
repo=CardRepository(Path(sys.argv[2]), ImageStore(path.parent/'cold-images'))
s=GameSession(GameState.model_validate_json(path.read_text()),cards=repo)
s.perform(sys.argv[3],json.loads(sys.argv[4]))
settle(s)
path.write_text(s.state.model_dump_json())
repo.close()
'''
    result = subprocess.run([sys.executable, '-c', code, str(path), str(cards.db_path), actor, json.dumps(payload)],
                            cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    return GameSession(GameState.model_validate_json(path.read_text()), cards=cards)


@pytest.mark.parametrize('mode', ['stolen', 'nivix', 'chandra', 'burning', 'arvinox',
                                 'meeting', 'magus', 'augury', 'muse', 'bre', 'chest',
                                 'gonti', 'curse', 'mezzio', 'triad', 'strago', 'crab', 'rampage', 'liara'])
def test_actual_packet_continuation_resumes_in_fresh_process(cards, tmp_path, mode):
    s = gameplay.setup(cards)
    destination = 'p1:battlefield'
    if mode == 'stolen':
        top = stack_library(s, ['Grizzly Bears'], pid='p2')
        cast(s, 'Stolen Goods', targets=['p2'])
        cid = top[0]
        payload = {'type': 'cast_spell', 'card_id': cid, 'free': True}
    elif mode == 'nivix':
        source = put(s, 'Nivix, Aerie of the Firemind', 'battlefield')
        cid = stack_library(s, ['Lightning Bolt'])[0]
        mana(s, C=2, U=1, R=2)
        act(s, 'p1', type='activate_ability', card_id=source.id, ability=ability(s, source, '{2}'))
        settle(s)
        payload = {'type': 'cast_spell', 'card_id': cid, 'targets': ['p2']}
        destination = 'p1:graveyard'
    elif mode == 'chandra':
        source = put(s, 'Chandra, Heart of Fire', 'battlefield')
        cid = stack_library(s, ['Forest'])[0]
        act(s, 'p1', type='activate_ability', card_id=source.id, ability=0)
        settle(s)
        payload = {'type': 'play_land', 'card_id': cid}
    elif mode == 'burning':
        cid = stack_library(s, ['Forest'])[0]
        cast(s, 'Burning Curiosity')
        payload = {'type': 'play_land', 'card_id': cid}
    elif mode == 'arvinox':
        source = put(s, 'Arvinox, the Mind Flail', 'battlefield')
        card = put(s, 'Grizzly Bears', 'library', 'p2')
        act(s, 'p1', type='move', card_ids=[card.id], to={'player': 'p2', 'zone': 'library'}, position='bottom')
        to_phase(s, 'end', turn=1)
        settle(s)
        cid = next(p.card for p in s.state.rules.permissions if p.player == 'p1' and s.state.cards[p.card].name == 'Grizzly Bears')
        act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'graveyard'})
        to_phase(s, 'main1', turn=4)
        mana(s, W=2)
        payload = {'type': 'cast_spell', 'card_id': cid}
    elif mode == 'meeting':
        cid = stack_library(s, ['Rhox War Monk'])[0]
        source = put(s, 'Meeting of the Five', 'hand')
        mana(s, C=3, W=1, U=1, B=1, R=1, G=1)
        act(s, 'p1', type='cast_spell', card_id=source.id)
        settle(s)
        payload = {'type': 'cast_spell', 'card_id': cid}
    elif mode == 'magus':
        source = put(s, 'Magus of the Mind', 'battlefield')
        to_phase(s, 'main1', turn=4)
        library = list(s.state.zones['p1:library'])
        act(s, 'p1', type='move', card_ids=library, to={'player': 'p1', 'zone': 'exile'})
        stack_library(s, ['Memnite'])
        mana(s, U=1)
        act(s, 'p1', type='activate_ability', card_id=source.id, ability=ability(s, source, '{U}'))
        settle(s)
        cid = next(p.card for p in s.state.rules.permissions if p.free)
        payload = {'type': 'cast_spell', 'card_id': cid, 'free': True}
    elif mode == 'augury':
        cid = stack_library(s, ['Forest'])[0]
        cast(s, "Aminatou's Augury")
        d = s.state.rules.decision
        assert d is not None
        payload = {'type': 'choose', 'decision_id': d.id, 'option_ids': [next(o.id for o in d.options if o.card_id == cid)]}
    elif mode == 'muse':
        cid = stack_library(s, ['Lightning Bolt'])[0]
        cast(s, 'Muse Vortex', x_value=1)
        d = s.state.rules.decision
        assert d is not None
        payload = {'type': 'choose', 'decision_id': d.id, 'option_ids': [next(o.id for o in d.options if o.card_id == cid)]}
        destination = 'p1:graveyard'
    elif mode == 'bre':
        put(s, 'Bre of Clan Stoutarm', 'battlefield')
        act(s, 'p1', type='life', player='p1', delta=1)
        cid = stack_library(s, ['Lightning Bolt'])[0]
        to_phase(s, 'end', turn=1)
        settle(s)
        d = s.state.rules.decision
        assert d is not None
        payload = {'type': 'choose', 'decision_id': d.id, 'option_ids': []}
        destination = 'p1:hand'
    elif mode == 'chest':
        host = put(s, 'Grizzly Bears', 'battlefield', 'p2')
        cid = stack_library(s, ['Lightning Bolt'], pid='p2')[0]
        cast(s, "Dead Man's Chest", targets=[host.id])
        cast(s, 'Murder', targets=[host.id])
        mana(s, G=1, C=1)
        payload = {'type': 'cast_spell', 'card_id': cid, 'targets': ['p2']}
        destination = 'p2:graveyard'
    elif mode in ('gonti', 'curse', 'mezzio', 'liara'):
        if mode == 'curse':
            cast(s, 'Curse of Hospitality', targets=['p2'])
        else:
            put(s, {'gonti': 'Gonti, Night Minister', 'mezzio': 'Mezzio Mugger',
                    'liara': 'Commander Liara Portyr'}[mode], 'battlefield')
        attacker = put(s, 'Grizzly Bears', 'battlefield') if mode != 'mezzio' else next(
            c for c in s.state.cards.values() if c.name == 'Mezzio Mugger' and c.zone == 'p1:battlefield')
        to_phase(s, 'declare_attackers', turn=4)
        foreign = mode in ('gonti', 'curse')
        cid = stack_library(s, ['Grizzly Bears' if foreign else 'Memnite'], pid='p2' if foreign else 'p1')[0]
        act(s, 'p1', type='declare_attackers', attackers=[{'card_id': attacker.id, 'target': 'p2'}])
        to_phase(s, 'main2', turn=4)
        settle(s)
        if mode == 'gonti':
            cid = next(p.card for p in s.state.rules.permissions if p.player == 'p1'
                       and s.state.cards[p.card].name == 'Grizzly Bears'
                       and s.state.cards[p.card].owner == 'p2')
        mana(s, G=1, C=1)
        payload = {'type': 'cast_spell', 'card_id': cid}
    elif mode == 'triad':
        put(s, 'Triple Triad', 'battlefield')
        to_phase(s, 'end', turn=3)
        cid = stack_library(s, ['Grizzly Bears'])[0]
        to_phase(s, 'main1', turn=4)
        settle(s)
        payload = {'type': 'cast_spell', 'card_id': cid, 'free': True}
    elif mode == 'strago':
        source = put(s, 'Strago and Relm', 'battlefield')
        to_phase(s, 'main1', turn=4)
        cid = stack_library(s, ['Grizzly Bears'], pid='p2')[0]
        mana(s, C=2, R=1)
        act(s, 'p1', type='activate_ability', card_id=source.id, ability=ability(s, source, 'Sketch and Lore'), targets=['p2'])
        settle(s)
        d = s.state.rules.decision
        payload = {'type': 'choose', 'decision_id': d.id, 'option_ids': [next(o.id for o in d.options if o.card_id == cid)]}
    elif mode == 'crab':
        cid = stack_library(s, ['Grizzly Bears'], pid='p2')[0]
        cast(s, 'Crabomination')
        answer(s, ['p2'])
        d = s.state.rules.decision
        payload = {'type': 'choose', 'decision_id': d.id, 'option_ids': [next(o.id for o in d.options if o.card_id == cid)]}
    else:
        put(s, 'Memnite', 'battlefield', 'p2')
        cid = stack_library(s, ['Grizzly Bears'])[0]
        cast(s, "Anzrag's Rampage")
        d = s.state.rules.decision
        payload = {'type': 'choose', 'decision_id': d.id, 'option_ids': [next(o.id for o in d.options if o.card_id == cid)]}
    s = fresh_action(s, cards, tmp_path / (mode + '.json'), 'p1', payload)
    if mode == 'muse':
        answer(s, ['p2'])
    assert s.state.cards[cid].zone == destination
    roundtrip(s)

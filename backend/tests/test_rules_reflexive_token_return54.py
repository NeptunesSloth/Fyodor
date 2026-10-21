"""A reflexive return keeps the created token and the returned Equipment identities separate."""
from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_placements import settle
from tests.test_rules_reflexive_mill54 import cards as cards
from tests.test_rules_reflexive_mill54 import cast, chosen
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

NAMES=['Forum Filibuster','Ratonhnhaké꞉ton']


def setup(cards,name,object_name,*,march=False):
    names=[*NAMES,'Bonesplitter','Pacifism','Grizzly Bears','Forest','Daybreak Coronet','March of the Machines']
    s=table(cards,names,names,names)
    to_phase(s,'main1',1)
    attachment=put(s,object_name,'graveyard')
    source=cast(s,name)
    if march:
        cast(s,'March of the Machines')
    if name=='Forum Filibuster':
        to_phase(s,'upkeep',4)
        settle(s)
    else:
        from tests.test_rules_conditional_prevention import attack, damage
        attack(s,[source],turn=4)
        damage(s)
    d=s.state.rules.decision
    assert d is not None and attachment.id in [o.id for o in d.options]
    token=next(c for c in s.state.cards.values() if c.is_token and c.zone=='p1:battlefield')
    return s,source,attachment,token


@pytest.mark.parametrize('name',NAMES)
def test_canonical_complete(cards,name):
    assert coverage.of_card_data(cards.resolve(name)).level=='FULL'


@pytest.mark.parametrize('name,object_name',[('Forum Filibuster','Bonesplitter'),('Forum Filibuster','Pacifism'),('Ratonhnhaké꞉ton','Bonesplitter')])
def test_actual_token_then_reflexive_return_attaches_new_permanent_to_exact_token(cards,name,object_name):
    s,source,attachment,token=setup(cards,name,object_name)
    chosen(s,attachment.id)
    assert attachment.zone=='p1:battlefield' and attachment.attached_to==token.id
    assert source.zone=='p1:battlefield'
    roundtrip(s)


@pytest.mark.parametrize('name,object_name',[('Forum Filibuster','Bonesplitter'),('Forum Filibuster','Pacifism'),('Ratonhnhaké꞉ton','Bonesplitter')])
def test_original_token_gone_equipment_returns_unattached_aura_stays_in_graveyard(cards,name,object_name):
    s,source,attachment,token=setup(cards,name,object_name)
    act(s,'p1',type='set_prefs',hold_priority=True)
    d=s.state.rules.decision
    act(s,d.player,type='choose',decision_id=d.id,option_ids=[attachment.id])
    act(s,'p1',type='move',card_ids=[token.id],to={'player':'p1','zone':'exile'})
    settle(s)
    assert attachment.zone==('p1:graveyard' if object_name=='Pacifism' else 'p1:battlefield')
    assert not attachment.attached_to
    roundtrip(s)


@pytest.mark.parametrize('name',NAMES)
def test_true_cold_pending_reflexive_token_and_new_returned_permanent(cards,tmp_path,name):
    import subprocess
    import sys
    from pathlib import Path
    s,source,attachment,token=setup(cards,name,'Bonesplitter')
    saved=tmp_path/'pending-token.json'
    saved.write_text(s.state.model_dump_json())
    code=r"""
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.game_helpers import act
from tests.test_rules_designations import roundtrip
from tests.test_rules_library_placements import settle
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
attachment,token=sys.argv[3:5]
d=s.state.rules.decision
act(s,d.player,type='choose',decision_id=d.id,option_ids=[attachment])
settle(s)
assert s.state.cards[attachment].zone=='p1:battlefield'
assert s.state.cards[attachment].attached_to==token
roundtrip(s)
repo.close()
"""
    result=subprocess.run([sys.executable,'-c',code,str(saved),str(cards.db_path),attachment.id,token.id],cwd=Path(__file__).resolve().parents[1],capture_output=True,text=True,timeout=90)
    assert result.returncode==0,result.stdout+result.stderr


def test_forum_printed_token_flies_and_cannot_be_blocked_by_ground_creature(cards):
    from app.game.errors import ActionError
    from tests.test_rules_conditional_prevention import attack, damage
    s,source,attachment,token=setup(cards,'Forum Filibuster','Bonesplitter')
    chosen(s,attachment.id)
    blocker=put(s,'Grizzly Bears','battlefield','p2')
    attack(s,[token],turn=7)
    to_phase(s,'declare_blockers')
    before=s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s,'p2',type='declare_blockers',blocks=[{'blocker_id':blocker.id,'attacker_id':token.id}])
    assert s.state.model_dump_json()==before
    act(s,'p2',type='declare_blockers',blocks=[])
    life=s.state.players['p2'].life
    damage(s)
    assert s.state.players['p2'].life==life-4
    roundtrip(s)


def test_raton_hexproof_prevents_opponents_target_before_damage_then_expires_after_actual_hit(cards):
    from app.game.errors import ActionError
    from tests.test_rules_bandmate_references import wait_priority
    from tests.test_rules_conditional_prevention import attack, damage
    names=[*NAMES,'Bonesplitter','Pacifism','Grizzly Bears','Lightning Bolt','Forest']
    s=table(cards,names,names,names)
    to_phase(s,'main1',1)
    attachment=put(s,'Bonesplitter','graveyard')
    source=cast(s,'Ratonhnhaké꞉ton')
    bolt=put(s,'Lightning Bolt','hand','p2')
    wait_priority(s,'p2')
    act(s,'p2',type='add_mana',player='p2',mana={'R':1})
    before=s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s,'p2',type='cast_spell',card_id=bolt.id,targets=[source.id],sources=[])
    assert s.state.model_dump_json()==before
    blocker=put(s,'Grizzly Bears','battlefield','p2')
    attack(s,[source],turn=4)
    to_phase(s,'declare_blockers')
    before=s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s,'p2',type='declare_blockers',blocks=[{'blocker_id':blocker.id,'attacker_id':source.id}])
    assert s.state.model_dump_json()==before
    act(s,'p2',type='declare_blockers',blocks=[])
    damage(s)
    chosen(s,attachment.id)
    assert s.state.players['p2'].life==37
    wait_priority(s,'p2')
    act(s,'p2',type='add_mana',player='p2',mana={'R':1})
    act(s,'p2',type='cast_spell',card_id=bolt.id,targets=[source.id],sources=[])
    settle(s)
    assert source.zone=='p1:graveyard'
    roundtrip(s)


def test_forum_may_choose_no_return_target_but_still_creates_token(cards):
    s,source,attachment,token=setup(cards,'Forum Filibuster','Bonesplitter')
    d=s.state.rules.decision
    act(s,d.player,type='choose',decision_id=d.id,option_ids=[])
    settle(s)
    assert token.zone=='p1:battlefield' and attachment.zone=='p1:graveyard'
    roundtrip(s)


def test_forum_aura_with_unsatisfied_enchant_restriction_stays_in_graveyard(cards):
    s,source,attachment,token=setup(cards,'Forum Filibuster','Daybreak Coronet')
    chosen(s,attachment.id)
    assert token.zone=='p1:battlefield' and attachment.zone=='p1:graveyard'
    assert not attachment.attached_to
    roundtrip(s)


def test_raton_returned_equipment_that_is_creature_enters_but_does_not_attach(cards):
    s,source,attachment,token=setup(cards,'Ratonhnhaké꞉ton','Bonesplitter',march=True)
    chosen(s,attachment.id)
    assert attachment.zone=='p1:battlefield' and not attachment.attached_to
    assert token.zone=='p1:battlefield'
    roundtrip(s)

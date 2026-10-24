"""Actual stack spells gain native abilities with exact object and duration lifetimes."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from app.rules.plan import Plan
from tests import test_rules_exile_cast_outcomes45_foundation as gameplay
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana
from tests.test_rules_designations import put
from tests.test_rules_library_look import settle
from tests.test_rules_ordered_tutor_continuations import cast
from tests.test_rules_wave30m_durations import to_phase

DATA = json.loads((Path(__file__).parent / 'fixtures/flagbearer86_cards.json').read_text())
BEARER, FLAG, GUARD = [r['name'] for r in DATA[:3]]


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for filename in ['exile_outcomes42_cards.json', 'exile_cast_outcomes45_cards.json',
                     'fight_exile_receipts65_cards.json', 'top_library_authorities69_cards.json',
                     'pooled_casting_authorities71_cards.json']:
        for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures' / filename).read_text())):
            base[c['name']] = card(c['name'], set_code='lc76', number=str(i), **{k: v for k, v in c.items() if k not in {'name', 'set_code'}})
    for i, c in enumerate(DATA):
        base[c['name']] = card(c['name'], set_code='lc76', number='a' + str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards):
    return gameplay.setup(cards, *[c['name'] for c in DATA], 'Lightning Bolt', 'Disperse', 'Counterspell', 'Sol Ring', 'Forest')



def p2_turn(s):
    to_phase(s,'main1',turn=2)
    mana(s,pid='p2',C=50,W=20,U=20,B=20,R=20,G=20)


def foreign_cast(s,name,**kwargs):
    c=put(s,name,'hand',pid='p2')
    act(s,'p2',type='cast_spell',card_id=c.id,**kwargs)
    settle(s)
    return c


@pytest.mark.parametrize('name',[BEARER,GUARD,FLAG])
def test_actual_printed_flagbearer_forces_opponent_spell_choice86(cards,name):
    from app.game.errors import ActionError

    s=setup(cards)
    if name==FLAG:
        host=put(s,'Grizzly Bears','battlefield')
        cast(s,FLAG,targets=[host.id])
    else:
        host=cast(s,name)
    assert 'Flagbearer' in Plan(s.state,'p1',cards,None).ch(s.state.cards[host.id]).subtypes
    assert coverage.of_card_data(cards.resolve(name)).level=='FULL'
    p2_turn(s)
    spell=put(s,'Lightning Bolt','hand',pid='p2')
    before=s.state.model_dump(mode='json')
    with pytest.raises(ActionError):
        act(s,'p2',type='cast_spell',card_id=spell.id,targets=['p1'])
    assert s.state.model_dump(mode='json')==before
    act(s,'p2',type='cast_spell',card_id=spell.id,targets=[host.id])
    settle(s)
    assert s.state.cards[host.id].zone=='p1:graveyard' if name!=GUARD else s.state.cards[host.id].damage==3


def test_flagbearer_does_not_force_own_controller86(cards):
    s=setup(cards)
    cast(s,BEARER)
    cast(s,'Lightning Bolt',targets=['p2'])
    assert s.state.players['p2'].life==37


def test_flagbearer_no_legal_foreign_target_for_own_creature_pump86(cards):
    s=setup(cards)
    flag=cast(s,BEARER)
    p2_turn(s)
    bear=put(s,'Grizzly Bears','battlefield',pid='p2')
    foreign_cast(s,"Ranger's Guile",targets=[bear.id])
    assert 'hexproof' in Plan(s.state,'p2',cards,None).ch(s.state.cards[bear.id]).keywords
    assert s.state.cards[flag.id].zone=='p1:battlefield'


def test_actual_hexproof_makes_flagbearer_unavailable86(cards):
    s=setup(cards)
    flag=cast(s,BEARER)
    cast(s,"Ranger's Guile",targets=[flag.id])
    # Instant speed during the same turn keeps real end-of-turn hexproof active.
    from tests.test_rules_bandmate_references import wait_priority
    wait_priority(s,'p2')
    mana(s,pid='p2',R=1)
    foreign_cast(s,'Lightning Bolt',targets=['p1'])
    assert s.state.players['p1'].life==37


def test_actual_dress_down_removes_creature_requirement_but_aura_remains86(cards):
    s=setup(cards)
    flag=cast(s,BEARER)
    cast(s,'Dress Down')
    from tests.test_rules_bandmate_references import wait_priority
    wait_priority(s,'p2')
    mana(s,pid='p2',R=1)
    foreign_cast(s,'Lightning Bolt',targets=['p1'])
    assert s.state.players['p1'].life==37
    assert 'Flagbearer' in Plan(s.state,'p1',cards,None).ch(s.state.cards[flag.id]).subtypes


def test_any_players_legal_flagbearer_satisfies_requirement86(cards):
    s=setup(cards)
    cast(s,BEARER)
    p2_turn(s)
    own=foreign_cast(s,GUARD)
    foreign_cast(s,'Lightning Bolt',targets=[own.id])
    assert s.state.cards[own.id].damage==3


def test_opponent_triggered_ability_is_exempt86(cards):
    s=setup(cards)
    flag=cast(s,GUARD)
    bear=put(s,'Grizzly Bears','battlefield')
    p2_turn(s)
    foreign_cast(s,'Flametongue Kavu')
    from tests.test_rules_controller_tutors import answer
    assert s.state.rules.decision
    answer(s,[bear.id])
    assert s.state.cards[bear.id].zone=='p1:graveyard'
    assert s.state.cards[flag.id].damage==0


def test_actual_activated_ability_must_target_legal_flagbearer86(cards):
    from app.game.errors import ActionError
    from tests.test_rules_wave4h_activation_costs import ability

    s=setup(cards)
    flag=cast(s,GUARD)
    pyro=put(s,'Prodigal Pyromancer','battlefield',pid='p2')
    p2_turn(s)
    before=s.state.model_dump(mode='json')
    index=ability(s,pyro,'{T}:')
    with pytest.raises(ActionError):
        act(s,'p2',type='activate_ability',card_id=pyro.id,ability=index,targets=['p1'])
    assert s.state.model_dump(mode='json')==before
    act(s,'p2',type='activate_ability',card_id=pyro.id,ability=index,targets=[flag.id])
    settle(s)
    assert s.state.cards[flag.id].damage==1


def test_tapped_only_target_rule_does_not_force_untapped_flagbearer86(cards):
    from tests.test_rules_wave4h_activation_costs import ability

    s=setup(cards)
    flag=cast(s,GUARD)
    assassin=put(s,'Royal Assassin','battlefield',pid='p2')
    bear=put(s,'Grizzly Bears','battlefield')
    p2_turn(s)
    act(s,'p1',type='tap',card_ids=[bear.id],tapped=True)
    act(s,'p2',type='activate_ability',card_id=assassin.id,ability=ability(s,assassin,'{T}:'),targets=[bear.id])
    settle(s)
    assert s.state.cards[bear.id].zone=='p1:graveyard'
    assert s.state.cards[flag.id].zone=='p1:battlefield'


def test_real_divided_damage_keeps_announced_count_and_requires_one_flagbearer86(cards):
    from app.game.errors import ActionError

    s=setup(cards)
    flag=cast(s,GUARD)
    bear1=put(s,'Grizzly Bears','battlefield')
    bear2=put(s,'Grizzly Bears','battlefield',pid='p3')
    p2_turn(s)
    spell=put(s,'Arc Lightning','hand',pid='p2')
    with pytest.raises(ActionError):
        act(s,'p2',type='cast_spell',card_id=spell.id,targets=[bear1.id,bear2.id],target_counts=[2],division=[1,2])
    act(s,'p2',type='cast_spell',card_id=spell.id,targets=[flag.id,bear1.id],target_counts=[2],division=[1,2])
    settle(s)
    assert s.state.cards[flag.id].damage==1
    assert s.state.cards[bear1.id].zone=='p1:graveyard'


def test_real_multiple_target_groups_need_only_one_flagbearer86(cards):
    from app.game.errors import ActionError

    s=setup(cards)
    flag=cast(s,GUARD)
    bear=put(s,'Grizzly Bears','battlefield')
    p2_turn(s)
    spell=put(s,'Common Bond','hand',pid='p2')
    with pytest.raises(ActionError):
        act(s,'p2',type='cast_spell',card_id=spell.id,targets=[bear.id,bear.id],target_counts=[1,1])
    act(s,'p2',type='cast_spell',card_id=spell.id,targets=[flag.id,bear.id],target_counts=[1,1])
    settle(s)
    assert s.state.cards[flag.id].counters.get('+1/+1')==1
    assert s.state.cards[bear.id].counters.get('+1/+1')==1


def test_full_native_shared_type_feasibility_cannot_force_impossible_group86(cards):
    s=setup(cards)
    flag=cast(s,GUARD)
    bear1=put(s,'Grizzly Bears','battlefield')
    bear2=put(s,'Grizzly Bears','battlefield',pid='p3')
    p2_turn(s)
    foreign_cast(s,'Shared Kin Probe86',targets=[bear1.id,bear2.id],target_counts=[2])
    assert s.state.cards[bear1.id].tapped and s.state.cards[bear2.id].tapped
    assert not s.state.cards[flag.id].tapped


def test_full_native_shared_type_feasibility_finds_two_target_replacement86(cards):
    from app.game.errors import ActionError

    s=setup(cards)
    flag=cast(s,GUARD)
    bear1=put(s,'Grizzly Bears','battlefield')
    bear2=put(s,'Grizzly Bears','battlefield',pid='p3')
    human=put(s,'Royal Assassin','battlefield',pid='p3')
    p2_turn(s)
    spell=put(s,'Shared Kin Probe86','hand',pid='p2')
    with pytest.raises(ActionError):
        act(s,'p2',type='cast_spell',card_id=spell.id,targets=[bear1.id,bear2.id],target_counts=[2])
    act(s,'p2',type='cast_spell',card_id=spell.id,targets=[flag.id,human.id],target_counts=[2])
    settle(s)
    assert s.state.cards[flag.id].tapped and s.state.cards[human.id].tapped


def test_zero_optional_target_count_is_announced_before_target_identities86(cards):
    s=setup(cards)
    flag=cast(s,GUARD)
    p2_turn(s)
    foreign_cast(s,'Optional Targets Probe86',targets=[],target_counts=[0])
    assert not s.state.cards[flag.id].tapped


def test_actual_mogg_controller_forced_but_delegated_noncontroller_exempt86(cards,monkeypatch):
    from tests.test_rules_controller_tutors import answer
    from tests.test_rules_random_choice_receipts41 import faces

    s=setup(cards)
    flag=cast(s,GUARD)
    foreign_flag=put(s,GUARD,'battlefield',pid='p3')
    victim=put(s,'Grizzly Bears','battlefield',pid='p3')
    mogg=put(s,'Mogg Assassin','battlefield',pid='p2')
    p2_turn(s)
    act(s,'p2',type='activate_ability',card_id=mogg.id,ability=0)
    d=s.state.rules.decision
    assert d.player=='p2'
    assert {o.id for o in d.options}=={flag.id,foreign_flag.id}
    answer(s,[flag.id])
    d=s.state.rules.decision
    assert d.player=='p1' and victim.id in {o.id for o in d.options}
    faces(monkeypatch,[0])
    answer(s,[victim.id])
    assert s.state.cards[victim.id].zone=='p3:graveyard'
    assert s.state.cards[flag.id].zone=='p1:battlefield'


def test_native_redirect_new_target_choice_is_exempt86(cards):
    from tests.test_rules_bandmate_references import wait_priority
    from tests.test_rules_controller_tutors import answer

    s=setup(cards)
    flag=cast(s,GUARD)
    victim=put(s,'Grizzly Bears','battlefield',pid='p3')
    p2_turn(s)
    bolt=put(s,'Lightning Bolt','hand',pid='p2')
    act(s,'p2',type='cast_spell',card_id=bolt.id,targets=[flag.id])
    wait_priority(s,'p1')
    cast(s,'Redirect',targets=[bolt.id])
    assert s.state.rules.decision
    answer(s,[victim.id])
    assert s.state.cards[victim.id].zone=='p3:graveyard'
    assert s.state.cards[flag.id].damage==0


def test_actual_random_target_activation_samples_only_required_legal_flagbearers86(cards,monkeypatch):
    s=setup(cards)
    flag=cast(s,GUARD)
    pilot=put(s,'Goblin Test Pilot','battlefield',pid='p2')
    p2_turn(s)
    pools=[]
    import secrets
    def pick(self,pool):
        pools.append(list(pool))
        return list(pool)[0]
    monkeypatch.setattr(secrets.SystemRandom,'choice',pick)
    act(s,'p2',type='activate_ability',card_id=pilot.id,ability=1)
    settle(s)
    assert pools==[[flag.id]]
    assert s.state.cards[flag.id].damage==2


@pytest.mark.parametrize('mode',[0,2])
def test_actual_modal_spell_only_chosen_mode_determines_flagbearer_eligibility86(cards,mode):
    from app.game.errors import ActionError

    s=setup(cards)
    flag=cast(s,GUARD)
    bear=put(s,'Grizzly Bears','battlefield',pid='p3')
    p2_turn(s)
    spell=put(s,'Boros Charm','hand',pid='p2')
    if mode==0:
        act(s,'p2',type='cast_spell',card_id=spell.id,modes=[mode],targets=['p1'])
        settle(s)
        assert s.state.players['p1'].life==36
    else:
        with pytest.raises(ActionError):
            act(s,'p2',type='cast_spell',card_id=spell.id,modes=[mode],targets=[bear.id])
        act(s,'p2',type='cast_spell',card_id=spell.id,modes=[mode],targets=[flag.id])
        settle(s)
        assert 'double strike' in Plan(s.state,'p2',cards,None).ch(s.state.cards[flag.id]).keywords


def test_aura_flagbearer_requirement_survives_creature_dress_down86(cards):
    from app.game.errors import ActionError
    from tests.test_rules_bandmate_references import wait_priority

    s=setup(cards)
    host=put(s,'Grizzly Bears','battlefield')
    cast(s,FLAG,targets=[host.id])
    cast(s,'Dress Down')
    wait_priority(s,'p2')
    mana(s,pid='p2',R=1)
    spell=put(s,'Lightning Bolt','hand',pid='p2')
    with pytest.raises(ActionError):
        act(s,'p2',type='cast_spell',card_id=spell.id,targets=['p1'])
    act(s,'p2',type='cast_spell',card_id=spell.id,targets=[host.id])
    settle(s)
    assert s.state.cards[host.id].zone=='p1:graveyard'


@pytest.mark.parametrize('mode',['single','shared_group'])
def test_genuine_cold_flagbearer_current_requirement_and_full_group_legality86(cards,tmp_path,mode):
    import os
    import subprocess
    import sys

    s=setup(cards)
    flag=cast(s,GUARD)
    bear1=put(s,'Grizzly Bears','battlefield')
    bear2=put(s,'Grizzly Bears','battlefield',pid='p3')
    human=put(s,'Royal Assassin','battlefield',pid='p3')
    p2_turn(s)
    spell=put(s,'Lightning Bolt' if mode=='single' else 'Shared Kin Probe86','hand',pid='p2')
    saved=tmp_path/'flag86.json'
    saved.write_text(s.state.model_dump_json())
    ids=json.dumps([flag.id,bear1.id,bear2.id,human.id,spell.id])
    code=r'''
import sys,json
from pathlib import Path
from app.cards.repository import CardRepository
from app.cards.images import ImageStore
from app.game.state import GameState
from app.game.session import GameSession
from app.game.errors import ActionError
from tests.game_helpers import act
from tests.test_rules_library_look import settle
from tests.test_rules_controller_tutors import answer
from tests.test_rules_designations import roundtrip
r=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=r)
mode=sys.argv[3]
flag,b1,b2,human,spell=json.loads(sys.argv[4])
if mode=='single':
 act(s,'p2',type='cast_spell',card_id=spell)
 d=s.state.rules.decision
 assert d.player=='p2' and {o.id for o in d.options}=={flag}
 answer(s,[flag])
 assert s.state.cards[flag].damage==3
 assert s.state.players['p1'].life==40
else:
 before=s.state.model_dump(mode='json')
 try:act(s,'p2',type='cast_spell',card_id=spell,targets=[b1,b2],target_counts=[2])
 except ActionError:pass
 else:raise AssertionError('ignored feasible mandatory Flagbearer target assignment')
 assert s.state.model_dump(mode='json')==before
 act(s,'p2',type='cast_spell',card_id=spell,targets=[flag,human],target_counts=[2])
 settle(s)
 assert s.state.cards[flag].tapped and s.state.cards[human].tapped
roundtrip(s)
r.close()
'''
    backend=Path(__file__).resolve().parents[1]
    result=subprocess.run([sys.executable,'-c',code,str(saved),str(cards.db_path),mode,ids],cwd=backend,
                          env={**os.environ,'PYTHONPATH':str(backend)},capture_output=True,text=True,timeout=240)
    assert result.returncode==0,result.stdout+result.stderr

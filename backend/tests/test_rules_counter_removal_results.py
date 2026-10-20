"""Actual removed-counter quantities survive choices and feed native spell effects."""
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
from tests.game_helpers import act, mana_pool
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_remaining_talents import pay
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave7b_activation import ability_index

NAMES=['Aether Snap','Give // Take','Hex Parasite','Mutated Cultist','Price of Betrayal']


@pytest.fixture()
def cards(settings):
    base={c['name']:c for c in fixture_cards()}
    for i,c in enumerate(json.loads((Path(__file__).parent/'fixtures/counter_removal_results_cards.json').read_text())):
        base[c['name']]=card(c['name'],set_code='crr',number=str(i),**{k:v for k,v in c.items() if k!='name'})
    settings.ensure_dirs()
    build_database(base.values(),settings.cards_db_path)
    repo=CardRepository(settings.cards_db_path,ImageStore(settings.images_dir))
    yield repo
    repo.close()


def game(cards):
    ns=[*NAMES,'Grizzly Bears','Sol Ring','Forest','Jace Beleren','Doubling Season','Hardened Scales','Shalai, Voice of Plenty','Protean Hydra','Shock','Abundance','Reverberate','Necrotic Ooze']
    return table(cards,ns,ns,ns)


def cast(s,name,targets=None,*,pool=None,finish=True,**kwargs):
    c=put(s,name,'hand')
    if pool is None:
        pay(s,'p1',name)
    else:
        act(s,'p1',type='add_mana',mana=pool)
    act(s,'p1',type='cast_spell',card_id=c.id,sources=[],targets=targets or [],**kwargs)
    if finish:
        settle(s)
    return c


def counter(s,c,kind,n):
    act(s,'p1',type='set_counter',card_id=c.id,kind=kind,value=n)


def resource(s,p,kind,n):
    act(s,'p1',type='set_resource',player=p,key=kind,value=n)


def number(s,n):
    d=s.state.rules.decision
    assert d and d.resume['step']=='counter_amounts', (d.kind if d else None,d.prompt if d else None)
    act(s,d.player,type='choose',decision_id=d.id,name=str(n))
    settle(s)


def choose(s,value):
    d=s.state.rules.decision
    assert d and value in {o.id for o in d.options}, (d.kind if d else None,d.prompt if d else None,value)
    act(s,d.player,type='choose',decision_id=d.id,option_ids=[value])
    settle(s)


@pytest.mark.parametrize('name',NAMES)
def test_full(cards,name):
    assert coverage.of_card_data(cards.resolve(name)).level=='FULL'


def test_price_player_mixed_counters_respects_total_and_never_changes_speed(cards):
    s=game(cards)
    for k,n in [('energy',3),('experience',2),('poison',4),('rad',2),('speed',3)]:
        resource(s,'p2',k,n)
    cast(s,'Price of Betrayal',['p2'])
    number(s,2)
    roundtrip(s)
    number(s,1)
    number(s,2)
    assert s.state.rules.decision is None
    assert s.state.players['p2'].resources=={'poison':2,'energy':1,'experience':1,'rad':2,'speed':3}
    roundtrip(s)


def test_price_permanent_mixed_kinds_and_typed_zero(cards):
    s=game(cards)
    a=put(s,'Sol Ring','battlefield','p2')
    counter(s,a,'charge',3)
    counter(s,a,'stun',4)
    cast(s,'Price of Betrayal',[a.id])
    number(s,0)
    number(s,4)
    assert s.state.cards[a.id].counters=={'charge':3}
    roundtrip(s)


def parasite(s,target,x,*,life=False):
    source=put(s,'Hex Parasite','battlefield')
    act(s,'p1',type='add_mana',mana={'C':x,**({} if life else {'B':1})})
    act(s,'p1',type='activate_ability',card_id=source.id,ability=ability_index(s,source,'Remove up to X'),
        targets=[target.id],x_value=x,sources=[],life_symbols=['B'] if life else [])
    settle(s)
    return source


def test_hex_parasite_pumps_actual_removed_not_announced_x_and_expires(cards):
    from tests.test_rules_wave30m_durations import to_phase
    s=game(cards)
    a=put(s,'Sol Ring','battlefield','p2')
    counter(s,a,'charge',2)
    counter(s,a,'stun',3)
    source=parasite(s,a,4)
    number(s,1)
    number(s,2)
    assert s.state.cards[a.id].counters=={'charge':1,'stun':1}
    assert Plan(s.state,'p1',s.cards,None).ch(s.state.cards[source.id]).pt==(4,1)
    to_phase(s,'upkeep',turn=2)
    assert Plan(s.state,'p1',s.cards,None).ch(s.state.cards[source.id]).pt==(1,1)
    roundtrip(s)


def test_hex_parasite_phyrexian_life_payment_and_zero_removal(cards):
    s=game(cards)
    a=put(s,'Sol Ring','battlefield','p2')
    counter(s,a,'charge',2)
    life=s.state.players['p1'].life
    source=parasite(s,a,3,life=True)
    number(s,0)
    assert s.state.players['p1'].life==life-2
    assert Plan(s.state,'p1',s.cards,None).ch(s.state.cards[source.id]).pt==(1,1)
    assert s.state.cards[a.id].counters=={'charge':2}
    roundtrip(s)


@pytest.mark.parametrize('fused',[False,True])
def test_take_draws_actual_counters_including_fused_give_and_native_doubling(cards,fused):
    s=game(cards)
    a=put(s,'Grizzly Bears','battlefield')
    counter(s,a,'+1/+1',2)
    put(s,'Doubling Season','battlefield')
    before=len(s.state.zones['p1:hand'])
    if fused:
        cast(s,'Give // Take',[a.id,a.id],pool={'G':1,'U':1,'C':4},fuse=True,target_counts=[1,1])
    else:
        cast(s,'Give // Take',[a.id],pool={'U':1,'C':2},face=1)
    assert not s.state.cards[a.id].counters
    assert len(s.state.zones['p1:hand'])==before+(8 if fused else 2)
    roundtrip(s)


def test_aether_snap_removes_all_permanent_kinds_then_exiles_tokens_only(cards):
    s=game(cards)
    a=put(s,'Grizzly Bears','battlefield')
    b=put(s,'Forest','battlefield','p2')
    counter(s,a,'+1/+1',2)
    counter(s,b,'charge',3)
    resource(s,'p2','energy',4)
    act(s,'p1',type='create_token',player='p1',token={'name':'Test Token','power':'1','toughness':'1','type_line':'Token Creature','colors':[]})
    token=next(c for c in s.state.cards.values() if c.is_token and c.zone=='p1:battlefield')
    counter(s,token,'stun',2)
    cast(s,'Aether Snap')
    assert not s.state.cards[a.id].counters and not s.state.cards[b.id].counters
    assert not [c for c in s.state.cards.values() if c.is_token and c.zone.endswith(':battlefield')]
    assert s.state.players['p2'].resources['energy']==4
    roundtrip(s)


def test_cultist_player_removes_all_counter_kinds_leaves_speed_and_discount_consumed_once(cards):
    s=game(cards)
    resource(s,'p2','energy',2)
    resource(s,'p2','poison',1)
    resource(s,'p2','speed',3)
    cast(s,'Mutated Cultist')
    choose(s,'p2')
    assert s.state.players['p2'].resources['energy']==0
    assert s.state.players['p2'].resources['poison']==0
    assert s.state.players['p2'].resources['speed']==3
    assert len(s.state.rules.next_spell_grants)==1
    assert s.state.rules.next_spell_grants[0].amount==3
    cast(s,'Grizzly Bears',pool={'G':1})
    assert not s.state.rules.next_spell_grants
    assert mana_pool(s)=={}
    roundtrip(s)


def test_price_target_union_excludes_self_land_enchantment_and_hexproof_player(cards):
    from app.game.errors import ActionError
    s=game(cards)
    land=put(s,'Forest','battlefield','p2')
    enchantment=put(s,'Abundance','battlefield','p2')
    put(s,'Shalai, Voice of Plenty','battlefield','p2')
    spell=put(s,'Price of Betrayal','hand')
    act(s,'p1',type='add_mana',mana={'B':1})
    before=s.state.model_dump(mode='json')
    for target in ['p1','p2',land.id,enchantment.id]:
        with pytest.raises(ActionError):
            act(s,'p1',type='cast_spell',card_id=spell.id,sources=[],targets=[target])
        assert s.state.model_dump(mode='json')==before
    roundtrip(s)


def test_parasite_changed_target_object_cannot_feed_pump(cards):
    s=game(cards)
    a=put(s,'Sol Ring','battlefield','p2')
    counter(s,a,'charge',3)
    source=parasite(s,a,3)
    put(s,'Sol Ring','hand','p2')
    put(s,'Sol Ring','battlefield','p2')
    counter(s,a,'charge',5)
    number(s,2)
    assert s.state.cards[a.id].counters=={'charge':5}
    assert Plan(s.state,'p1',s.cards,None).ch(s.state.cards[source.id]).pt==(1,1)
    roundtrip(s)


def test_parasite_changed_source_object_does_not_get_old_ability_pump(cards):
    s=game(cards)
    a=put(s,'Sol Ring','battlefield','p2')
    counter(s,a,'charge',3)
    source=parasite(s,a,3)
    put(s,'Hex Parasite','hand')
    put(s,'Hex Parasite','battlefield')
    number(s,2)
    assert s.state.cards[a.id].counters=={'charge':1}
    assert Plan(s.state,'p1',s.cards,None).ch(s.state.cards[source.id]).pt==(1,1)
    roundtrip(s)


def test_borrowed_parasite_ability_pumps_actual_necrotic_ooze_source(cards):
    s=game(cards)
    lender=put(s,'Hex Parasite','graveyard')
    source=put(s,'Necrotic Ooze','battlefield')
    target=put(s,'Sol Ring','battlefield','p2')
    counter(s,target,'charge',3)
    act(s,'p1',type='add_mana',mana={'C':2,'B':1})
    act(s,'p1',type='activate_ability',card_id=source.id,ability=ability_index(s,source,'Remove up to X'),targets=[target.id],x_value=2,sources=[])
    settle(s)
    number(s,2)
    assert Plan(s.state,'p1',s.cards,None).ch(s.state.cards[source.id]).pt==(6,3)
    assert Plan(s.state,'p1',s.cards,None).ch(s.state.cards[lender.id]).pt==(1,1)
    roundtrip(s)


def test_cultist_optional_zero_target_and_source_gone_preserves_discount(cards):
    s=game(cards)
    resource(s,'p2','energy',2)
    source=cast(s,'Mutated Cultist')
    put(s,'Mutated Cultist','exile')
    choose(s,'p2')
    assert s.state.cards[source.id].zone=='p1:exile'
    assert s.state.rules.next_spell_grants[0].amount==2
    cast(s,'Grizzly Bears',pool={'G':1})
    assert not s.state.rules.next_spell_grants
    roundtrip(s)


def test_cultist_no_target_gives_no_effective_discount(cards):
    s=game(cards)
    cast(s,'Mutated Cultist')
    d=s.state.rules.decision
    assert d and d.min_choices==0
    act(s,d.player,type='choose',decision_id=d.id,option_ids=[])
    settle(s)
    assert not [g for g in s.state.rules.next_spell_grants if g.amount]
    roundtrip(s)


def test_aether_snap_native_removed_triggers_survive_source_dying_after_spell(cards):
    s=game(cards)
    source=cast(s,'Protean Hydra',pool={'G':1,'C':2},x_value=2)
    cast(s,'Aether Snap')
    assert s.state.cards[source.id].zone=='p1:graveyard'
    assert len(s.state.rules.delayed)==2
    roundtrip(s)


def test_aether_snap_loaded_high_counter_state_does_not_truncate_all(cards):
    from app.game.session import GameSession
    from app.game.state import GameState
    s=game(cards)
    ring=put(s,'Sol Ring','battlefield','p2')
    saved=s.state.model_dump(mode='json')
    saved['cards'][ring.id]['counters']={'charge':2000003,'stun':2001}
    s=GameSession(GameState.model_validate(saved),cards=cards)
    cast(s,'Aether Snap')
    assert not s.state.cards[ring.id].counters
    roundtrip(s)


def test_saved_second_kind_amount_resumes_in_fresh_process_with_actual_pump(cards,tmp_path):
    import subprocess
    import sys
    s=game(cards)
    target=put(s,'Sol Ring','battlefield','p2')
    counter(s,target,'charge',3)
    counter(s,target,'stun',4)
    source=parasite(s,target,4)
    number(s,1)
    saved=tmp_path/'counter-amounts.json'
    saved.write_text(s.state.model_dump_json())
    code=r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from app.rules.plan import Plan
save,db,target,source=sys.argv[1:]
repo=CardRepository(Path(db),ImageStore(Path(db).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(save).read_text()),cards=repo)
d=s.state.rules.decision
assert d.resume['step']=='counter_amounts'
s.perform(d.player,{'type':'choose','decision_id':d.id,'name':'2'})
assert s.state.cards[target].counters=={'charge':2,'stun':2}
assert Plan(s.state,'p1',repo,None).ch(s.state.cards[source]).pt==(4,1)
assert s.history.rebuild().model_dump(mode='json')==s.state.model_dump(mode='json')
repo.close()
'''
    result=subprocess.run([sys.executable,'-c',code,str(saved),str(cards.db_path),target.id,source.id],
                          cwd=Path(__file__).resolve().parents[1],capture_output=True,text=True,timeout=60)
    assert result.returncode==0,result.stderr


def test_take_draw_replacement_resumes_without_removing_or_drawing_twice(cards):
    from tests.test_rules_abundance import set_library
    s=game(cards)
    target=put(s,'Grizzly Bears','battlefield')
    counter(s,target,'+1/+1',2)
    put(s,'Abundance','battlefield')
    library=set_library(s,['Forest','Shock','Sol Ring'])
    before=s.state.rules.turn_log.drew.get('p1',0)
    cast(s,'Give // Take',[target.id],pool={'U':1,'C':2},face=1)
    assert not s.state.cards[target.id].counters
    roundtrip(s)
    d=s.state.rules.decision
    assert d and 'decline' in {o.id for o in d.options}
    choose(s,next(o.id for o in d.options if o.id!='decline'))
    choose(s,'land')
    roundtrip(s)
    choose(s,'decline')
    assert s.state.cards[library[0]].zone=='p1:hand'
    assert s.state.cards[library[1]].zone=='p1:hand'
    assert s.state.rules.turn_log.drew.get('p1',0)==before+1
    assert not s.state.cards[target.id].counters
    roundtrip(s)


def test_hex_large_typed_amount_and_invalid_answer_are_bounded_by_actual_x(cards):
    from app.game.errors import ActionError
    s=game(cards)
    target=put(s,'Sol Ring','battlefield','p2')
    counter(s,target,'charge',100)
    source=parasite(s,target,73)
    before=s.state.model_dump(mode='json')
    with pytest.raises(ActionError):
        number(s,74)
    assert s.state.model_dump(mode='json')==before
    number(s,73)
    assert s.state.cards[target.id].counters=={'charge':27}
    assert Plan(s.state,'p1',s.cards,None).ch(s.state.cards[source.id]).pt==(74,1)
    roundtrip(s)


def test_cultist_discount_expires_at_end_of_turn(cards):
    from tests.test_rules_wave30m_durations import to_phase
    s=game(cards)
    resource(s,'p2','energy',3)
    cast(s,'Mutated Cultist')
    choose(s,'p2')
    to_phase(s,'main1',turn=4)
    bear=put(s,'Grizzly Bears','hand')
    act(s,'p1',type='add_mana',mana={'G':1})
    from app.game.errors import ActionError
    before=s.state.model_dump(mode='json')
    with pytest.raises(ActionError,match="can't pay"):
        act(s,'p1',type='cast_spell',card_id=bear.id,sources=[])
    assert s.state.model_dump(mode='json')==before
    act(s,'p1',type='add_mana',mana={'C':1})
    act(s,'p1',type='cast_spell',card_id=bear.id,sources=[])
    settle(s)
    assert s.state.cards[bear.id].zone=='p1:battlefield'
    roundtrip(s)

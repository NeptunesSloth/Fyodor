"""Canonical effect recipes read the actual direct sacrifice cost LKI."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_bandmate_references import wait_priority
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_mana_delayed_effects import answer, cast
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase


@pytest.fixture()
def cards(settings):
    base={c['name']:c for c in fixture_cards()}
    for i,c in enumerate(json.loads((Path(__file__).parent/'fixtures/paid_sacrifice_effect_cards.json').read_text())):
        base[c['name']]=card(c['name'],set_code='nac',number=str(i),**{k:v for k,v in c.items() if k!='name'})
    settings.ensure_dirs()
    build_database(base.values(),settings.cards_db_path)
    repo=CardRepository(settings.cards_db_path,ImageStore(settings.images_dir))
    yield repo
    repo.close()


def game(cards):
    names=[c['name'] for c in json.loads((Path(__file__).parent/'fixtures/paid_sacrifice_effect_cards.json').read_text())]
    s=table(cards,names,names,names)
    for p in ('p1','p2','p3'):
        act(s,p,type='set_prefs',hold_priority=True)
    to_phase(s,'main1',4)
    return s


NAMES=['Soulblast','Soldevi Adnate','Pyre of Heroes','Anchor to Reality','Baba Lysaga, Night Witch','Desperate Plea','Adipose Offspring','Tormented Thoughts','Sanguine Praetor','Mind Extraction','Endemic Plague','Eye of Yawgmoth','Freyalise Supplicant','Fiery Bombardment','Agency Coroner']
POOL={'W':10,'U':10,'B':10,'R':10,'G':10,'C':10}


def cost_choice(s,source,sacrifices,spell=False):
    from app.rules import costs, scripts
    from app.rules.plan import Plan
    ch=Plan(s.state,'p1',s.cards,None).ch(s.state.cards[source.id])
    cost=costs.spell_additional_cost(ch.abilities) if spell else scripts.parse_ability_cost(ch.abilities[0].cost,card_name=ch.name)
    assert cost is not None
    index=next(i for i,c in enumerate(cost.components) if c.kind==costs.SACRIFICE and c.selector)
    return [{'component':index,'cards':[c.id for c in sacrifices]}]


def activated(s,name,sacrifices,targets=()):
    source=put(s,name,'battlefield')
    # Sources that are creatures need a previous turn of control.
    to_phase(s,'main1',7)
    wait_priority(s,'p1')
    act(s,'p1',type='add_mana',player='p1',mana=POOL)
    act(s,'p1',type='activate_ability',card_id=source.id,ability=0,targets=list(targets),sources=[],
        cost_choices=cost_choice(s,source,sacrifices))
    return source


def cast_paid(s,name,sacrifice,targets=(),**kw):
    source=put(s,name,'hand')
    choices=cost_choice(s,source,[sacrifice],spell=True)
    return cast(s,name,POOL,targets,cost_choices=choices,**kw)


@pytest.mark.parametrize('name',NAMES)
def test_full(cards,name):
    assert coverage.of_card_data(cards.resolve(name)).level=='FULL'


@pytest.mark.parametrize('name,sacrifice,n',[
    ('Tormented Thoughts','Trained Armodon',3),
    ('Freyalise Supplicant','Woolly Thoctar',2),
    ('Fiery Bombardment','Furnace Whelp',2),
])
def test_scalar_positive_actual_cost(cards,name,sacrifice,n):
    s=game(cards)
    victim=put(s,sacrifice,'battlefield')
    if name=='Tormented Thoughts':
        for card_name in ['Forest','Sol Ring','Storm Crow','Giant Growth']:
            put(s,card_name,'hand',pid='p2')
    before=len(s.state.zones['p2:hand'])
    if name=='Tormented Thoughts':
        cast_paid(s,name,victim,['p2'])
    else:
        activated(s,name,[victim],['p2'])
    assert s.state.cards[victim.id].zone=='p1:graveyard'
    roundtrip(s)
    answer(s)
    if name=='Tormented Thoughts':
        assert len(s.state.zones['p2:hand'])==before-n
    else:
        assert s.state.players['p2'].life==40-n
    roundtrip(s)


@pytest.mark.parametrize('name',['Sanguine Praetor','Endemic Plague'])
def test_destroy_selector_uses_sacrificed_original(cards,name):
    s=game(cards)
    victim=put(s,'Grizzly Bears','battlefield')
    destroyed=put(s,'Grizzly Bears','battlefield',pid='p2')
    survivor=put(s,'Trained Armodon','battlefield',pid='p2')
    if name=='Sanguine Praetor':
        activated(s,name,[victim])
    else:
        cast_paid(s,name,victim)
    answer(s)
    assert s.state.cards[destroyed.id].zone=='p2:graveyard'
    assert s.state.cards[survivor.id].zone=='p2:battlefield'
    roundtrip(s)


def test_mind_extraction_matches_any_paid_color_not_land_identity(cards):
    s=game(cards)
    victim=put(s,'Woolly Thoctar','battlefield')
    act(s,'p2',type='move',card_ids=list(s.state.zones['p2:hand']),to={'player':'p2','zone':'exile'})
    red=put(s,'Lightning Bolt','hand',pid='p2')
    green=put(s,'Giant Growth','hand',pid='p2')
    blue=put(s,'Storm Crow','hand',pid='p2')
    land=put(s,'Forest','hand',pid='p2')
    cast_paid(s,'Mind Extraction',victim,['p2'])
    answer(s)
    assert s.state.cards[red.id].zone==s.state.cards[green.id].zone=='p2:graveyard'
    assert s.state.cards[blue.id].zone==s.state.cards[land.id].zone=='p2:hand'
    roundtrip(s)


def test_eye_reveals_power_picks_one_exiles_rest(cards):
    s=game(cards)
    victim=put(s,'Grizzly Bears','battlefield')
    activated(s,'Eye of Yawgmoth',[victim])
    before=set(s.state.zones['p1:hand'])
    top=set(s.state.zones['p1:library'][:2])
    answer(s)
    assert len(set(s.state.zones['p1:hand'])-before)==1
    assert len([c for c in top if s.state.cards[c].zone=='p1:exile'])==1
    roundtrip(s)


def test_baba_distinct_card_types_in_direct_cost(cards):
    from tests.test_rules_mana_delayed_effects import drawn
    s=game(cards)
    land=put(s,'Dryad Arbor','battlefield')
    artifact=put(s,'Sol Ring','battlefield')
    activated(s,'Baba Lysaga, Night Witch',[land,artifact])
    before=drawn(s)
    answer(s)
    assert s.state.players['p2'].life==37 and s.state.players['p3'].life==37
    assert s.state.players['p1'].life==43 and drawn(s)==before+3
    roundtrip(s)


def test_pyre_native_search_combines_type_and_mana_value(cards):
    s=game(cards)
    victim=put(s,'Myr Sire','battlefield')
    activated(s,'Pyre of Heroes',[victim])
    found=put(s,'Alloy Myr','library')
    settle(s)
    d=s.state.rules.decision
    assert d is not None and found.id in {o.id for o in d.options}
    roundtrip(s)
    act(s,d.player,type='choose',decision_id=d.id,option_ids=[found.id])
    answer(s)
    assert s.state.cards[found.id].zone=='p1:battlefield'
    roundtrip(s)


def test_anchor_search_found_permanent_compared_to_cost_lki(cards):
    s=game(cards)
    victim=put(s,'Furnace Whelp','battlefield')
    found=put(s,'Bonesplitter','library')
    cast_paid(s,'Anchor to Reality',victim)
    settle(s)
    d=s.state.rules.decision
    assert d is not None and found.id in {o.id for o in d.options}
    act(s,d.player,type='choose',decision_id=d.id,option_ids=[found.id])
    settle(s)
    d=s.state.rules.decision
    assert s.state.cards[found.id].zone=='p1:battlefield'
    assert d is not None and d.prompt.startswith('Scry 2')
    roundtrip(s)
    answer(s)
    roundtrip(s)


def test_desperate_plea_both_modes_keep_conditional_return_and_destroy(cards):
    s=game(cards)
    victim=put(s,'Woolly Thoctar','battlefield')
    returned=put(s,'Trained Armodon','graveyard')
    destroyed=put(s,'Grizzly Bears','battlefield',pid='p2')
    cast_paid(s,'Desperate Plea',victim,[returned.id,destroyed.id],modes=[0,1],target_counts=[1,1])
    answer(s)
    assert s.state.cards[returned.id].zone=='p1:battlefield'
    assert s.state.cards[destroyed.id].zone=='p2:graveyard'
    roundtrip(s)


@pytest.mark.parametrize('emerged',[True,False])
def test_adipose_actual_emerge_cost_uses_paid_toughness(cards,emerged):
    from app.rules.plan import Plan
    s=game(cards)
    victim=put(s,'Trained Armodon','battlefield')
    source=put(s,'Adipose Offspring','hand')
    cast(s,'Adipose Offspring',POOL,**({'alt_cost':f'{source.id}:0','cost_choices':[{'component':0,'cards':[victim.id]}]} if emerged else {}))
    answer(s)
    aliens=[c for c in s.state.cards.values() if c.is_token and c.zone=='p1:battlefield' and 'Alien' in Plan(s.state,'p1',s.cards,None).ch(c).subtypes]
    assert len(aliens)==(3 if emerged else 1)
    roundtrip(s)


@pytest.mark.parametrize('suspected',[True,False])
def test_agency_coroner_uses_departed_suspected_designation(cards,suspected):
    from tests.test_rules_mana_delayed_effects import drawn
    s=game(cards)
    victim=put(s,'Repeat Offender','battlefield')
    if suspected:
        wait_priority(s,'p1')
        act(s,'p1',type='add_mana',player='p1',mana={'B':1,'C':2})
        act(s,'p1',type='activate_ability',card_id=victim.id,ability=0,sources=[],targets=[])
        answer(s)
    activated(s,'Agency Coroner',[victim])
    before=drawn(s)
    roundtrip(s)
    answer(s)
    assert drawn(s)==before+(2 if suspected else 1)
    roundtrip(s)


def test_soulblast_sacrifices_every_creature_and_sums_original_power(cards):
    s=game(cards)
    a=put(s,'Grizzly Bears','battlefield')
    b=put(s,'Trained Armodon','battlefield')
    source=put(s,'Soulblast','hand')
    choices=cost_choice(s,source,[a,b],spell=True)
    cast(s,'Soulblast',POOL,['p2'],cost_choices=choices)
    assert s.state.cards[a.id].zone==s.state.cards[b.id].zone=='p1:graveyard'
    roundtrip(s)
    answer(s)
    assert s.state.players['p2'].life==35
    roundtrip(s)


def test_soulblast_empty_creature_set_is_payable(cards):
    s=game(cards)
    cast(s,'Soulblast',POOL,['p2'])
    answer(s)
    assert s.state.players['p2'].life==40
    roundtrip(s)


def test_soulblast_cannot_announce_only_some_of_mandatory_sacrifices(cards):
    from app.game.errors import ActionError
    s=game(cards)
    a=put(s,'Grizzly Bears','battlefield')
    b=put(s,'Trained Armodon','battlefield')
    source=put(s,'Soulblast','hand')
    with pytest.raises(ActionError):
        cast(s,'Soulblast',POOL,['p2'],cost_choices=cost_choice(s,source,[a],spell=True))
    assert s.state.cards[a.id].zone==s.state.cards[b.id].zone=='p1:battlefield'
    assert s.state.cards[source.id].zone=='p1:hand'
    roundtrip(s)


def test_eye_fresh_process_resumes_native_pick_after_paid_lki(cards,tmp_path):
    import subprocess
    import sys
    s=game(cards)
    victim=put(s,'Grizzly Bears','battlefield')
    activated(s,'Eye of Yawgmoth',[victim])
    settle(s)
    d=s.state.rules.decision
    assert d is not None and len(d.options)>=2
    roundtrip(s)
    saved=tmp_path/'eye-paid-pick.json'
    saved.write_text(s.state.model_dump_json())
    code=r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.test_rules_mana_delayed_effects import answer
save,db=sys.argv[1:]
r=CardRepository(Path(db),ImageStore(Path(db).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(save).read_text()),cards=r)
before=set(s.state.zones['p1:hand'])
exile=len(s.state.zones.get('p1:exile',[]))
answer(s)
assert len(set(s.state.zones['p1:hand'])-before)==1
assert len(s.state.zones['p1:exile'])==exile+1
assert s.history.rebuild().model_dump(mode='json')==s.state.model_dump(mode='json')
r.close()
'''
    result=subprocess.run([sys.executable,'-c',code,str(saved),str(cards.db_path)],
                          cwd=Path(__file__).resolve().parents[1],capture_output=True,text=True,timeout=60)
    assert result.returncode==0,result.stderr


def test_adipose_spell_copy_keeps_emerge_decision_and_original_cost_lki(cards):
    from app.rules.plan import Plan
    s=game(cards)
    victim=put(s,'Trained Armodon','battlefield')
    source=put(s,'Adipose Offspring','hand')
    original=cast(s,'Adipose Offspring',POOL,alt_cost=f'{source.id}:0',cost_choices=[{'component':0,'cards':[victim.id]}])
    cast(s,'Double Major',{'G':1,'U':1},[original.id])
    roundtrip(s)
    answer(s)
    aliens=[c for c in s.state.cards.values() if c.is_token and c.zone=='p1:battlefield'
            and Plan(s.state,'p1',s.cards,None).ch(c).name=='Alien']
    assert len(aliens)==6
    assert s.state.cards[victim.id].zone=='p1:graveyard'
    roundtrip(s)


def test_soulblast_prohibition_rejects_all_cost_atomically(cards):
    from app.game.errors import ActionError
    s=game(cards)
    angel=put(s,'Angel of Jubilation','battlefield')
    bear=put(s,'Grizzly Bears','battlefield')
    source=put(s,'Soulblast','hand')
    with pytest.raises(ActionError):
        cast(s,'Soulblast',POOL,['p2'])
    assert s.state.cards[angel.id].zone==s.state.cards[bear.id].zone=='p1:battlefield'
    assert s.state.cards[source.id].zone=='p1:hand'
    roundtrip(s)


def test_soulblast_sums_negative_power_before_clamping_damage(cards):
    s=game(cards)
    a=put(s,'Grizzly Bears','battlefield')
    b=put(s,'Trained Armodon','battlefield')
    cast(s,'Dizzy Spell',{'U':1},[a.id])
    answer(s)
    source=put(s,'Soulblast','hand')
    cast(s,'Soulblast',POOL,['p2'],cost_choices=cost_choice(s,source,[a,b],spell=True))
    answer(s)
    assert s.state.players['p2'].life==38  # -1 + 3, not max(0,-1)+3
    roundtrip(s)


def test_cost_lki_survives_physical_card_return_to_hidden_library(cards):
    s=game(cards)
    victim=put(s,'Trained Armodon','battlefield')
    for name in ['Forest','Sol Ring','Storm Crow','Giant Growth','Myr Sire','Bonesplitter','Alloy Myr']:
        put(s,name,'hand',pid='p2')
    cast(s,'Giant Growth',{'G':1},[victim.id])
    answer(s)
    before=len(s.state.zones['p2:hand'])
    cast_paid(s,'Tormented Thoughts',victim,['p2'])
    cast(s,'Reclaim',{'G':1},[victim.id])
    answer(s)
    assert s.state.cards[victim.id].zone=='p1:library'
    assert len(s.state.zones['p2:hand'])==before-6
    roundtrip(s)


def test_anchor_uses_entered_copy_mana_value_instead_of_library_snapshot(cards):
    s=game(cards)
    victim=put(s,'Furnace Whelp','battlefield')
    donor=put(s,'Giant Adephage','battlefield',pid='p2')
    found=put(s,'Imposter Mech','library')
    cast_paid(s,'Anchor to Reality',victim)
    settle(s)
    d=s.state.rules.decision
    act(s,d.player,type='choose',decision_id=d.id,option_ids=[found.id])
    settle(s)
    d=s.state.rules.decision
    assert d is not None
    options=[o.id for o in d.options if donor.id in o.id]
    assert options
    act(s,d.player,type='choose',decision_id=d.id,option_ids=[options[0]])
    settle(s)
    assert s.state.rules.decision is None  # copied MV7 is not less than sacrificed MV4
    assert s.state.cards[found.id].zone=='p1:battlefield'
    roundtrip(s)


@pytest.mark.parametrize('victim_name,mv',[('Repeat Offender',2),('Alloy Myr',3)])
def test_soldevi_actual_mana_uses_selected_black_or_artifact_creature(cards,victim_name,mv):
    from tests.game_helpers import mana_pool
    s=game(cards)
    source=put(s,'Soldevi Adnate','battlefield')
    to_phase(s,'main1',7)
    victim=put(s,victim_name,'battlefield')
    wait_priority(s,'p1')
    act(s,'p1',type='activate_ability',card_id=source.id,ability=0,sources=[],targets=[],
        cost_choices=[{'component':0,'cards':[victim.id]}])
    assert mana_pool(s,'p1').get('B',0)==mv
    assert s.state.cards[source.id].tapped and s.state.cards[victim.id].zone=='p1:graveyard'
    assert not s.state.zones.get('stack',[])
    roundtrip(s)


@pytest.mark.parametrize('victim_name,pid',[('Sol Ring','p1'),('Grizzly Bears','p1'),('Repeat Offender','p2')])
def test_soldevi_rejects_noncreature_wrong_quality_or_opponent_cost(cards,victim_name,pid):
    from app.game.errors import ActionError
    from tests.game_helpers import mana_pool
    s=game(cards)
    source=put(s,'Soldevi Adnate','battlefield')
    to_phase(s,'main1',7)
    victim=put(s,victim_name,'battlefield',pid=pid)
    wait_priority(s,'p1')
    with pytest.raises(ActionError):
        act(s,'p1',type='activate_ability',card_id=source.id,ability=0,sources=[],targets=[],
            cost_choices=[{'component':0,'cards':[victim.id]}])
    assert not s.state.cards[source.id].tapped and s.state.cards[victim.id].zone==pid+':battlefield'
    assert mana_pool(s,'p1').get('B',0)==0
    roundtrip(s)


def test_soldevi_pending_actual_sacrifice_choice_cold_resume(cards,tmp_path):
    import subprocess
    import sys
    s=game(cards)
    source=put(s,'Soldevi Adnate','battlefield')
    to_phase(s,'main1',7)
    victim=put(s,'Alloy Myr','battlefield')
    invalid=put(s,'Sol Ring','battlefield')
    wait_priority(s,'p1')
    act(s,'p1',type='activate_ability',card_id=source.id,ability=0,sources=[],targets=[])
    d=s.state.rules.decision
    assert d is not None and victim.id in {o.id for o in d.options} and invalid.id not in {o.id for o in d.options}
    assert not s.state.cards[source.id].tapped and s.state.cards[victim.id].zone=='p1:battlefield'
    roundtrip(s)
    saved=tmp_path/'soldevi-cost-choice.json'
    saved.write_text(s.state.model_dump_json())
    code=r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.game_helpers import mana_pool
save,db,source,victim=sys.argv[1:]
r=CardRepository(Path(db),ImageStore(Path(db).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(save).read_text()),cards=r)
d=s.state.rules.decision
s.perform(d.player,{'type':'choose','decision_id':d.id,'option_ids':[victim]})
assert s.state.rules.decision is None and not s.state.zones.get('stack',[])
assert s.state.cards[source].tapped and s.state.cards[victim].zone=='p1:graveyard'
assert mana_pool(s,'p1').get('B',0)==3
assert s.history.rebuild().model_dump(mode='json')==s.state.model_dump(mode='json')
r.close()
'''
    result=subprocess.run([sys.executable,'-c',code,str(saved),str(cards.db_path),source.id,victim.id],
                          cwd=Path(__file__).resolve().parents[1],capture_output=True,text=True,timeout=60)
    assert result.returncode==0,result.stderr

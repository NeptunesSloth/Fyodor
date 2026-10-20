"""Canonical native targets, costs, actual movements and variable life instructions."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from tests.fixtures.cards import card, fixture_cards
from tests.test_rules_conditional_prevention import cast, choose
from tests.test_rules_declaration_requirements33 import start
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_shared_damage_choices import table

DATA = json.loads((Path(__file__).parent / 'fixtures/life_card41_cards.json').read_text())


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(DATA):
        base[c['name']] = card(c['name'], set_code='lc41', number=str(i), **{k:v for k,v in c.items() if k!='name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def game(cards):
    names=[c['name'] for c in DATA]+['Grizzly Bears',"Atraxa, Praetors' Voice",'Llanowar Elves','Darksteel Myr','Holy Strength','Lightning Bolt','Sol Ring','Fervor','Platinum Emperion','Counterspell','Swords to Plowshares','Forest']
    s=table(cards,names,names,names)
    start(s)
    put(s,'Fervor','battlefield')
    return s


@pytest.mark.parametrize('kicked',[False,True])
def test_restoration_native_kicker_life_and_self_exile(cards,kicked):
    s=game(cards)
    target=put(s,'Atraxa, Praetors\' Voice','graveyard')
    spell=cast(s,"Sheoldred's Restoration",[target.id],kicker=int(kicked))
    assert target.zone=='p1:battlefield'
    assert s.state.players['p1'].life==40+(4 if kicked else -4)
    assert spell.zone=='p1:exile'
    roundtrip(s)


@pytest.mark.parametrize('pay',[False,True])
def test_vortex_actual_opponent_life_payment(cards,pay):
    s=game(cards)
    target=put(s,'Grizzly Bears','battlefield','p2')
    cast(s,'Essence Vortex',[target.id])
    d=s.state.rules.decision
    assert d and d.player=='p2'
    chosen=next(o.id for o in d.options if ('pay' in o.id.lower())==pay)
    choose(s,[chosen])
    assert target.zone==('p2:battlefield' if pay else 'p2:graveyard')
    assert s.state.players['p2'].life==(38 if pay else 40)
    roundtrip(s)


def test_orzhov_destroy_indestructible_still_loses_life(cards):
    s=game(cards)
    target=put(s,'Darksteel Myr','battlefield','p2')
    cast(s,'Orzhov Charm',[target.id],modes=[1])
    assert target.zone=='p2:battlefield'
    assert s.state.players['p1'].life==39
    roundtrip(s)


def test_orzhov_reanimate_low_mv_native_mode(cards):
    s=game(cards)
    target=put(s,'Llanowar Elves','graveyard')
    cast(s,'Orzhov Charm',[target.id],modes=[2])
    assert target.zone=='p1:battlefield'
    assert s.state.players['p1'].life==40
    roundtrip(s)


def test_kaya_first_actual_exile_and_creature_receipt(cards):

    s=game(cards)
    bear=put(s,'Grizzly Bears','graveyard','p2')
    bolt=put(s,'Lightning Bolt','graveyard','p2')
    kaya=cast(s,'Kaya, Orzhov Usurper')
    from tests.game_helpers import act
    act(s,'p1',type='activate_ability',card_id=kaya.id,ability=0,targets=[bear.id,bolt.id],target_counts=[2],sources=[])
    from tests.test_rules_designations import settle
    settle(s)
    assert bear.zone==bolt.zone=='p2:exile'
    assert s.state.players['p1'].life==42
    assert kaya.counters['loyalty']==4
    roundtrip(s)


def test_kaya_last_nominal_count_not_actual_damage(cards):
    from tests.game_helpers import act
    from tests.test_rules_conditional_prevention import activate

    s=game(cards)
    put(s,'Grizzly Bears','exile','p2')
    put(s,'Lightning Bolt','exile','p2')
    put(s,'Sol Ring','exile','p1')
    put(s,'Furnace of Rath','battlefield')
    kaya=cast(s,'Kaya, Orzhov Usurper')
    act(s,'p1',type='counter',card_ids=[kaya.id],kind='loyalty',delta=2)
    activate(s,kaya,'−5:', ['p2'])
    assert s.state.players['p1'].life==42
    assert s.state.players['p2'].life==36
    roundtrip(s)


def test_orzhov_bounce_auras_controlled_by_you(cards):
    s=game(cards)
    bear=put(s,'Grizzly Bears','battlefield')
    aura=cast(s,'Holy Strength',[bear.id])
    cast(s,'Orzhov Charm',[bear.id],modes=[0])
    assert bear.zone==aura.zone=='p1:hand'
    roundtrip(s)


def test_pact_equipped_life_zero_only_weapon_controller(cards):
    from tests.game_helpers import act
    from tests.test_rules_conditional_prevention import activate

    s=game(cards)
    bear=put(s,'Grizzly Bears','battlefield')
    weapon=cast(s,'Pact Weapon')
    put(s,'Lightning Bolt','hand')
    activate(s,weapon,'Equip—',[bear.id],resolve=False)
    if s.state.rules.decision:
        d=s.state.rules.decision
        choose(s,[next(o.id for o in d.options if 'Lightning Bolt' in o.label)])
    from tests.test_rules_designations import settle
    settle(s)
    assert weapon.attached_to==bear.id
    act(s,'p1',type='life',player='p1',delta=-40)
    # A real cast causes the native state-based check with the equipped restriction active.
    cast(s,'Sol Ring')
    assert 'p1' not in s.state.rules.lost
    assert s.state.players['p1'].life==0
    roundtrip(s)


def test_elixir_actual_nonlands_shuffled_and_exile_cost(cards):
    from tests.game_helpers import act
    from tests.test_rules_conditional_prevention import activate

    s=game(cards)
    land=put(s,'Forest','graveyard')
    bear=put(s,'Grizzly Bears','graveyard')
    bolt=put(s,'Lightning Bolt','graveyard')
    source=cast(s,'Elixir')
    assert source.tapped
    act(s,'p1',type='tap',card_ids=[source.id],tapped=False)
    activate(s,source,'{5}',[])
    assert source.zone=='p1:exile'
    assert land.zone=='p1:graveyard'
    assert bear.zone==bolt.zone=='p1:library'
    assert s.state.players['p1'].life==42
    roundtrip(s)


def test_niv_pairs_frozen_distinct_exactly_two_color_permanents(cards):
    from tests.test_rules_conditional_prevention import attack
    from tests.test_rules_designations import pick, settle
    from tests.test_rules_wave30m_durations import to_phase

    s=game(cards)
    source=put(s,'Niv-Mizzet, Guildpact','battlefield')
    put(s,'Black Panther, Wakandan King','battlefield')
    put(s,'Kaya, Orzhov Usurper','battlefield')
    # Native loyalty is initialized by a real cast, so use another stable two-color permanent instead.
    kaya=next(c for c in s.state.cards.values() if c.name=='Kaya, Orzhov Usurper' and c.owner=='p1')
    from tests.game_helpers import act
    act(s,'p1',type='counter',card_ids=[kaya.id],kind='loyalty',delta=3)
    put(s,"Atraxa, Praetors' Voice",'battlefield')
    from tests.test_rules_wave30m_durations import stops
    stops(s,'declare_attackers','combat_damage')
    attack(s,[source],turn=4)
    to_phase(s,'combat_damage',turn=4)
    settle(s)
    pick(s,['p2'])
    settle(s)
    pick(s,['p2'])
    settle(s)
    assert s.state.rules.decision is None
    assert s.state.players['p1'].life==42
    assert s.state.players['p2'].life==32
    roundtrip(s)


@pytest.mark.parametrize('mode,entwine,toughness,expected',[(0,0,4,40),(1,0,2,38),(0,1,4,36)])
def test_shriveling_rot_real_watch_modes_and_entwine(cards,mode,entwine,toughness,expected):
    s=game(cards)
    name="Rumbling Baloth" if toughness==4 else 'Grizzly Bears'
    target=put(s,name,'battlefield','p2')
    cast(s,'Shriveling Rot',modes=[0,1] if entwine else [mode],kicker=entwine)
    cast(s,'Lightning Bolt',[target.id])
    assert target.zone=='p2:graveyard'
    assert s.state.players['p2'].life==expected
    roundtrip(s)


def test_vortex_unpayable_life_destroys_without_payment(cards):
    s=game(cards)
    target=put(s,'Grizzly Bears','battlefield','p2')
    put(s,'Platinum Emperion','battlefield','p2')
    cast(s,'Essence Vortex',[target.id])
    if s.state.rules.decision:
        choose(s,['decline'])
    assert target.zone=='p2:graveyard'
    assert s.state.players['p2'].life==40
    roundtrip(s)


def test_vortex_true_fresh_process_payment(tmp_path,cards):
    import subprocess
    import sys

    s=game(cards)
    target=put(s,'Grizzly Bears','battlefield','p2')
    cast(s,'Essence Vortex',[target.id])
    assert s.state.rules.decision and s.state.rules.decision.player=='p2'
    path=tmp_path/'state.json'
    path.write_text(s.state.model_dump_json())
    code=r'''
import sys
from pathlib import Path
from app.cards.repository import CardRepository
from app.cards.images import ImageStore
from app.game.state import GameState
from app.game.session import GameSession
from tests.test_rules_designations import pick,settle,roundtrip
r=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=r)
assert s.state.rules.decision.player=='p2'
pick(s,['pay']);settle(s)
assert s.state.players['p2'].life==38
assert s.state.cards[sys.argv[3]].zone=='p2:battlefield'
roundtrip(s)
'''
    subprocess.run([sys.executable,'-c',code,str(path),str(cards.db_path),target.id],check=True,capture_output=True,text=True)


def equip_weapon(s):
    from tests.test_rules_conditional_prevention import activate
    from tests.test_rules_designations import settle

    bear=put(s,'Grizzly Bears','battlefield')
    weapon=cast(s,'Pact Weapon')
    discard=put(s,'Lightning Bolt','hand')
    activate(s,weapon,'Equip—',[bear.id],resolve=False)
    if s.state.rules.decision:
        choose(s,[discard.id])
    settle(s)
    assert weapon.attached_to==bear.id
    return weapon,bear


@pytest.mark.parametrize('replaced',[False,True])
def test_pact_actual_original_draw_receipt_and_attack_host(cards,replaced):
    from tests.game_helpers import act
    from tests.test_rules_conditional_prevention import attack
    from tests.test_rules_wave6c_tokens_pumps import chars

    s=game(cards)
    _,bear=equip_weapon(s)
    if replaced:
        put(s,'Thought Reflection','battlefield')
    top=put(s,'Elixir','hand')
    act(s,'p1',type='move',card_ids=[top.id],to={'player':'p1','zone':'library'},position='top')
    before=len(s.state.zones['p1:hand'])
    attack(s,[bear],turn=4)
    assert top.zone=='p1:hand'
    assert len(s.state.zones['p1:hand'])==before+(2 if replaced else 1)
    assert s.state.players['p1'].life==(40 if replaced else 39)
    assert chars(s,bear).pt[0]==(2 if replaced else 3), (s.state.turn.phase,s.state.turn.number,[e.model_dump() for e in s.state.rules.effects])
    roundtrip(s)


def test_vortex_no_regeneration_and_normal_optional_decline(cards):
    s=game(cards)
    bear=put(s,'Grizzly Bears','battlefield','p2')
    cast(s,'Regenerate',[bear.id])
    cast(s,'Essence Vortex',[bear.id])
    choose(s,['decline'])
    assert bear.zone=='p2:graveyard'
    roundtrip(s)


def test_restoration_illegal_target_fizzles_self_exile_and_life(cards):
    from tests.test_rules_designations import settle

    s=game(cards)
    bear=put(s,'Grizzly Bears','graveyard')
    from tests.game_helpers import act
    act(s,'p1',type='set_prefs',hold_priority=True)
    spell=cast(s,"Sheoldred's Restoration",[bear.id],kicker=1,resolve=False)
    # Native response exiles the actual graveyard incarnation before resolution.
    cast(s,'Noxious Revival',[bear.id])
    settle(s)
    assert bear.zone=='p1:library'
    assert s.state.players['p1'].life==40
    assert spell.zone=='p1:graveyard'
    roundtrip(s)


def test_pact_source_destroyed_original_attacker_still_receives_bonus(cards):
    from tests.game_helpers import act
    from tests.test_rules_wave6c_tokens_pumps import chars
    from tests.test_rules_wave30m_durations import to_phase

    s=game(cards)
    weapon,bear=equip_weapon(s)
    top=put(s,'Elixir','hand')
    act(s,'p1',type='move',card_ids=[top.id],to={'player':'p1','zone':'library'},position='top')
    to_phase(s,'declare_attackers',turn=4)
    act(s,'p1',type='declare_attackers',attackers=[{'card_id':bear.id,'target':'p2'}])
    cast(s,'Disenchant',[weapon.id])
    assert weapon.zone=='p1:graveyard'
    assert top.zone=='p1:hand'
    assert s.state.players['p1'].life==39
    assert chars(s,bear).pt[0]==3
    roundtrip(s)


def test_kaya_minus_one_nonland_mv_and_no_creature_gain(cards):
    from tests.test_rules_conditional_prevention import activate

    s=game(cards)
    target=put(s,'Sol Ring','battlefield','p2')
    kaya=cast(s,'Kaya, Orzhov Usurper')
    activate(s,kaya,'−1:',[target.id])
    assert target.zone=='p2:exile'
    assert kaya.counters['loyalty']==2
    assert s.state.players['p1'].life==40
    roundtrip(s)


@pytest.mark.parametrize('count',[0,1])
def test_kaya_first_noncreatures_and_zero_targets_no_life(cards,count):
    from tests.game_helpers import act
    from tests.test_rules_designations import settle

    s=game(cards)
    bolt=put(s,'Lightning Bolt','graveyard','p2')
    kaya=cast(s,'Kaya, Orzhov Usurper')
    act(s,'p1',type='activate_ability',card_id=kaya.id,ability=0,targets=[bolt.id] if count else [],target_counts=[count],sources=[])
    settle(s)
    assert bolt.zone==('p2:exile' if count else 'p2:graveyard')
    assert s.state.players['p1'].life==40
    roundtrip(s)


@pytest.mark.parametrize('accept',[False,True])
def test_archfiend_actual_mixed_madness_life_payment(cards,accept):
    from tests.test_rules_designations import settle

    s=game(cards)
    source=put(s,'Shadowgrange Archfiend','hand')
    cast(s,"Nahiri's Wrath",[],x_value=1,target_counts=[0],cost_choices=[{'component':0,'cards':[source.id]}])
    assert source.zone=='p1:exile'
    d=s.state.rules.decision
    assert d and 'Madness' in d.prompt
    choose(s,['yes' if accept else 'no'])
    settle(s)
    assert s.state.rules.decision is None
    assert source.zone==('p1:battlefield' if accept else 'p1:graveyard')
    assert s.state.players['p1'].life==(32 if accept else 40)
    roundtrip(s)


def test_archfiend_greatest_actual_sacrificed_power_not_sum(cards):
    s=game(cards)
    bear=put(s,'Grizzly Bears','battlefield','p2')
    baloth=put(s,'Rumbling Baloth','battlefield','p2')
    elf=put(s,'Llanowar Elves','battlefield','p3')
    cast(s,'Shadowgrange Archfiend')
    while s.state.rules.decision:
        d=s.state.rules.decision
        choose(s,[baloth.id if d.player=='p2' else elf.id])
    assert baloth.zone=='p2:graveyard'
    assert elf.zone=='p3:graveyard'
    assert bear.zone=='p2:battlefield'
    assert s.state.players['p1'].life==44
    roundtrip(s)


def test_archfiend_life_prohibition_madness_has_no_pay_option(cards):
    s=game(cards)
    put(s,'Platinum Emperion','battlefield')
    source=put(s,'Shadowgrange Archfiend','hand')
    cast(s,"Nahiri's Wrath",[],x_value=1,target_counts=[0],cost_choices=[{'component':0,'cards':[source.id]}])
    d=s.state.rules.decision
    assert d and {o.id for o in d.options}=={'no'}
    choose(s,['no'])
    assert source.zone=='p1:graveyard'
    assert s.state.players['p1'].life==40
    roundtrip(s)


@pytest.mark.parametrize('stage',['madness','pact','elixir'])
def test_native_variable_life_continuation_fresh_process(tmp_path,cards,stage):
    import subprocess
    import sys

    from tests.game_helpers import act
    from tests.test_rules_conditional_prevention import activate, attack

    s=game(cards)
    ids={}
    if stage=='madness':
        source=put(s,'Shadowgrange Archfiend','hand')
        cast(s,"Nahiri's Wrath",[],x_value=1,target_counts=[0],cost_choices=[{'component':0,'cards':[source.id]}])
        ids={'source':source.id}
    elif stage=='pact':
        _,bear=equip_weapon(s)
        put(s,'Abundance','battlefield')
        top=put(s,'Elixir','hand')
        act(s,'p1',type='move',card_ids=[top.id],to={'player':'p1','zone':'library'},position='top')
        attack(s,[bear],turn=4)
        ids={'bear':bear.id,'top':top.id}
    else:
        put(s,'Grizzly Bears','graveyard')
        put(s,'Lightning Bolt','graveyard')
        put(s,"Alhammarret's Archive",'battlefield')
        put(s,'Angel of Vitality','battlefield')
        source=cast(s,'Elixir')
        act(s,'p1',type='tap',card_ids=[source.id],tapped=False)
        activate(s,source,'{5}',[])
        ids={'source':source.id}
    d=s.state.rules.decision
    assert d,stage
    path=tmp_path/'state.json'
    path.write_text(s.state.model_dump_json())
    code=r'''
import sys,json
from pathlib import Path
from app.cards.repository import CardRepository
from app.cards.images import ImageStore
from app.game.state import GameState
from app.game.session import GameSession
from app.rules.plan import Plan
from tests.test_rules_designations import pick,settle,roundtrip
r=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=r)
stage=sys.argv[3];ids=json.loads(sys.argv[4])
assert s.state.rules.decision
if stage=='madness':
 pick(s,['yes']);settle(s)
 assert s.state.players['p1'].life==32
 assert s.state.cards[ids['source']].zone=='p1:battlefield'
 records=[p for p in s.state.rules.payments.values()if p.card==ids['source']and p.cast_from=='exile']
 assert records and records[-1].life==8 and sum(records[-1].mana_spent.values())==3
elif stage=='pact':
 pick(s,['decline']);settle(s)
 assert s.state.players['p1'].life==39
 assert s.state.cards[ids['top']].zone=='p1:hand'
 assert Plan(s.state,'p1',r,None).ch(s.state.cards[ids['bear']]).pt==(3,3)
else:
 d=s.state.rules.decision
 pick(s,[next(o.id for o in d.options if 'Angel of Vitality' in o.label)]);settle(s)
 assert s.state.players['p1'].life==46
 assert s.state.cards[ids['source']].zone=='p1:exile'
roundtrip(s)
'''
    result=subprocess.run([sys.executable,'-c',code,str(path),str(cards.db_path),stage,json.dumps(ids)],capture_output=True,text=True)
    assert result.returncode==0,result.stdout+result.stderr


def test_niv_hexproof_multicolor_and_flying_native(cards):
    from app.game.errors import ActionError
    from tests.game_helpers import act
    from tests.test_rules_conditional_prevention import attack
    from tests.test_rules_wave30m_durations import to_phase

    s=game(cards)
    niv=put(s,'Niv-Mizzet, Guildpact','battlefield')
    bear=put(s,'Grizzly Bears','battlefield','p2')
    attack(s,[niv],turn=4)
    to_phase(s,'declare_blockers',turn=4)
    with pytest.raises(ActionError):
        act(s,'p2',type='declare_blockers',blocks=[{'blocker_id':bear.id,'attacker_id':niv.id}])
    act(s,'p2',type='declare_blockers',blocks=[])
    with pytest.raises(ActionError):
        cast(s,'Terminate',[niv.id],pid='p2')
    cast(s,'Murder',[niv.id],pid='p2')
    assert niv.zone=='p1:graveyard'
    roundtrip(s)


def test_orzhov_foreign_controlled_aura_is_not_returned(cards):
    from tests.test_rules_wave30m_durations import to_phase

    s=game(cards)
    bear=put(s,'Grizzly Bears','battlefield')
    mine=cast(s,'Holy Strength',[bear.id])
    to_phase(s,'main1',turn=5)
    theirs=cast(s,'Holy Strength',[bear.id],pid='p2')
    cast(s,'Orzhov Charm',[bear.id],modes=[0])
    assert bear.zone==mine.zone=='p1:hand'
    assert theirs.zone=='p2:graveyard'
    roundtrip(s)

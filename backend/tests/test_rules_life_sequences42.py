"""Canonical native life sequences and durable saved continuations."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from tests.fixtures.cards import card, fixture_cards
from tests.test_rules_conditional_prevention import cast
from tests.test_rules_declaration_requirements33 import start
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave6c_tokens_pumps import chars

DATA = json.loads((Path(__file__).parent / 'fixtures/life_sequences42_cards.json').read_text())


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(DATA):
        base[c['name']] = card(c['name'], number=str(i), **{k:v for k,v in c.items() if k!='name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def game(cards):
    names = [c['name'] for c in DATA]
    s = table(cards, names, names, names)
    start(s)
    return s


def test_tenacity_exact_current_creatures_untap_and_lifelink(cards):
    s = game(cards)
    own = put(s, 'Grizzly Bears', 'battlefield')
    enemy = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    own.tapped = True
    enemy.tapped = True
    cast(s, 'Tenacity')
    assert not own.tapped and enemy.tapped
    assert chars(s, own).pt == (3,3)
    assert chars(s, enemy).pt == (2,2)
    assert 'lifelink' in chars(s, own).keywords
    assert 'lifelink' not in chars(s, enemy).keywords
    later = put(s, 'Angel of Vitality', 'battlefield')
    assert 'lifelink' not in chars(s, later).keywords
    roundtrip(s)


@pytest.mark.parametrize('multiplier', [False, True])
def test_floorboards_normal_tokens_and_nominal_life_independent(cards, multiplier):
    s = game(cards)
    if multiplier:
        put(s, "Alhammarret's Archive", 'battlefield')
    before = set(s.state.zones['p1:battlefield'])
    cast(s, 'From Under the Floorboards')
    new = [s.state.cards[cid] for cid in s.state.zones['p1:battlefield'] if cid not in before]
    assert len(new) == 3
    assert all(c.tapped and chars(s,c).pt == (2,2) for c in new)
    assert s.state.players['p1'].life == (46 if multiplier else 43)
    roundtrip(s)


@pytest.mark.parametrize('life', [5,6])
def test_courageous_zero_target_fateful_hour_allows_gain(cards,life):
    from app.rules import game_result, life_lock
    from app.rules.plan import Plan

    s = game(cards)
    s.state.players['p1'].life = life
    before = len(s.state.zones['p1:hand'])
    cast(s, 'Courageous Resolve', [], target_counts=[0])
    assert len(s.state.zones['p1:hand']) == before + 1
    p = Plan(s.state,'p1',cards,None)
    assert bool(life_lock.why_not(p,'p1','lose')) == (life == 5)
    assert life_lock.why_not(p,'p1','gain') is None
    assert game_result.cannot_lose(p,'p1') == (life == 5)
    assert game_result.cannot_win(p,'p2') == (life == 5)
    cast(s,'Healing Salve',['p1'],modes=[0])
    assert s.state.players['p1'].life == life + 3
    cast(s,'Lightning Bolt',['p1'])
    assert s.state.players['p1'].life == (8 if life == 5 else 6)
    roundtrip(s)


def test_courageous_sole_illegal_target_fizzles_draw_and_hour(cards):
    from app.rules import life_lock
    from app.rules.plan import Plan
    from tests.game_helpers import act
    from tests.test_rules_designations import settle

    s = game(cards)
    own = put(s,'Grizzly Bears','battlefield')
    s.state.players['p1'].life = 5
    act(s,'p1',type='set_prefs',hold_priority=True)
    cast(s,'Courageous Resolve',[own.id],target_counts=[1],resolve=False)
    cast(s,'Murder',[own.id],resolve=False)
    before = len(s.state.zones['p1:hand'])
    act(s,'p1',type='set_prefs',hold_priority=False)
    settle(s)
    assert own.zone == 'p1:graveyard'
    assert len(s.state.zones['p1:hand']) == before
    assert life_lock.why_not(Plan(s.state,'p1',cards,None),'p1','lose') is None
    roundtrip(s)


@pytest.mark.parametrize('x', [0,2])
def test_floorboards_actual_madness_announced_x(cards,x):
    from tests.test_rules_conditional_prevention import choose

    s = game(cards)
    spell = put(s,'From Under the Floorboards','hand')
    cast(s,"Nahiri's Wrath",[],x_value=1,target_counts=[0],cost_choices=[{'component':0,'cards':[spell.id]}])
    assert s.state.rules.decision and 'Madness' in s.state.rules.decision.prompt
    choose(s,['yes'])
    d=s.state.rules.decision
    assert d and any(o.id == f'x:{x}' for o in d.options)
    choose(s,[f'x:{x}'])
    assert s.state.rules.decision is None
    tokens = [c for c in s.state.cards.values() if c.zone=='p1:battlefield' and c.token]
    assert len(tokens) == x
    assert all(c.tapped and chars(s,c).pt==(2,2) for c in tokens)
    assert s.state.players['p1'].life == 40 + x
    assert spell.zone == 'p1:graveyard'
    roundtrip(s)


@pytest.mark.parametrize('double', [False,True])
def test_false_cure_real_gain_then_normal_loss_trigger(cards,double):
    s=game(cards)
    if double:
        put(s,"Alhammarret's Archive",'battlefield')
    cast(s,'False Cure')
    cast(s,'Healing Salve',['p1'],modes=[0])
    assert s.state.players['p1'].life == (34 if double else 37)
    cast(s,'Healing Salve',['p2'],modes=[0])
    assert s.state.players['p2'].life == 37
    roundtrip(s)


@pytest.mark.parametrize('first,second', [(False,True),(True,False),(True,True),(False,False)])
def test_talus_two_independent_optional_instructions(cards,first,second):
    from tests.test_rules_conditional_prevention import choose

    s=game(cards)
    paladin=cast(s,'Talus Paladin')
    assert s.state.rules.decision
    choose(s,['pay' if first else 'decline'])
    assert s.state.rules.decision
    choose(s,['pay' if second else 'decline'])
    assert s.state.rules.decision is None
    assert ('lifelink' in chars(s,paladin).keywords)==first
    assert paladin.counters.get('+1/+1',0)==int(second)
    later=put(s,'Hada Freeblade','battlefield')
    assert 'lifelink' not in chars(s,later).keywords
    roundtrip(s)


def test_lich_tomb_actual_life_loss_sacrifices_exact_amount(cards):
    from tests.test_rules_conditional_prevention import choose

    s=game(cards)
    tomb=put(s,"Lich's Tomb",'battlefield')
    bear=put(s,'Grizzly Bears','battlefield')
    forest=put(s,'Forest','battlefield')
    cast(s,'Lightning Bolt',['p1'])
    d=s.state.rules.decision
    if d:
        choose(s,[tomb.id,bear.id,forest.id])
    assert all(c.zone=='p1:graveyard' for c in [tomb,bear,forest])
    assert s.state.players['p1'].life==37
    roundtrip(s)


def test_tenacity_native_combat_lifelink_and_cleanup(cards):
    from tests.test_rules_conditional_prevention import attack, damage
    from tests.test_rules_wave30m_durations import to_phase

    s=game(cards)
    put(s,'Fervor','battlefield')
    bear=put(s,'Grizzly Bears','battlefield')
    cast(s,'Tenacity')
    attack(s,[bear])
    damage(s)
    assert s.state.players['p1'].life==43
    assert s.state.players['p2'].life==37
    to_phase(s,'main1',turn=5)
    assert chars(s,bear).pt==(2,2)
    assert 'lifelink' not in chars(s,bear).keywords
    roundtrip(s)


@pytest.mark.parametrize('kicked', [False,True])
def test_expel_announced_kicker_target_and_frozen_mana_value(cards,kicked):
    s=game(cards)
    victim=put(s,'Rumbling Baloth' if kicked else 'Grizzly Bears','battlefield','p2')
    cast(s,'Expel the Unworthy',[victim.id],kicker=int(kicked),target_counts=[0,1] if kicked else [1,0])
    assert victim.zone=='p2:exile'
    assert s.state.players['p2'].life==(44 if kicked else 42)
    roundtrip(s)


def test_courageous_hour_checked_after_replaced_draw(cards):
    from app.rules import life_lock
    from app.rules.plan import Plan
    from tests.test_rules_conditional_prevention import activate

    s=game(cards)
    worship=put(s,'Words of Worship','battlefield')
    s.state.players['p1'].life=5
    activate(s,worship,'next time')
    cast(s,'Courageous Resolve',[],target_counts=[0])
    assert s.state.players['p1'].life==10
    assert life_lock.why_not(Plan(s.state,'p1',cards,None),'p1','lose') is None
    roundtrip(s)


def test_tomb_stops_only_zero_life_until_sacrificed(cards):
    from tests.game_helpers import act

    s=game(cards)
    act(s,'p1',type='set_life',player='p1',value=1)
    tomb=put(s,"Lich's Tomb",'battlefield')
    put(s,'Grizzly Bears','battlefield')
    put(s,'Forest','battlefield')
    cast(s,'Lightning Bolt',['p1'])
    assert 'p1' in s.state.rules.lost
    assert tomb.zone!='p1:battlefield'
    roundtrip(s)


def test_tomb_does_not_stop_poison_loss(cards):
    s=game(cards)
    put(s,"Lich's Tomb",'battlefield')
    s.state.players['p1'].resources['poison']=10
    cast(s,'Lightning Bolt',['p3'],pid='p2')
    assert 'p1' in s.state.rules.lost
    roundtrip(s)


def test_archon_monarch_damage_result_not_global_life_lock(cards):
    s=game(cards)
    archon=cast(s,'Archon of Coronation')
    assert s.state.table.monarch=='p1'
    cast(s,'Lightning Bolt',['p1'],pid='p2')
    assert s.state.players['p1'].life==40
    cast(s,'Sign in Blood',['p1'])
    assert s.state.players['p1'].life==38
    assert archon.zone=='p1:battlefield'
    roundtrip(s)


def test_archon_actual_combat_damage_steals_monarch_then_stops_lock(cards):
    from tests.test_rules_conditional_prevention import attack, damage

    s=game(cards)
    put(s,'Fervor','battlefield','p2')
    bear=put(s,'Grizzly Bears','battlefield','p2')
    cast(s,'Archon of Coronation')
    assert s.state.table.monarch=='p1'
    attack(s,[bear],pid='p2',target='p1',turn=5)
    damage(s)
    assert s.state.players['p1'].life==40
    assert s.state.table.monarch=='p2'
    cast(s,'Lightning Bolt',['p1'],pid='p2')
    assert s.state.players['p1'].life==37
    roundtrip(s)


@pytest.mark.parametrize('infect',[False,True])
def test_archon_keeps_damage_lifelink_commander_and_infect_results(cards,infect):
    from tests.test_rules_conditional_prevention import attack, damage

    s=game(cards)
    put(s,'Fervor','battlefield','p2')
    attacker=put(s,'Glistener Elf' if infect else "Atraxa, Praetors' Voice",'battlefield','p2')
    cast(s,'Archon of Coronation')
    attack(s,[attacker],pid='p2',target='p1',turn=5)
    damage(s)
    assert s.state.players['p1'].life==40
    assert s.state.table.monarch=='p2'
    if infect:
        assert s.state.players['p1'].resources['poison']==1
    else:
        assert sum(s.state.players['p1'].commander_damage.values())==4
        assert s.state.players['p2'].life==44
    roundtrip(s)


@pytest.mark.parametrize('loser',['p2','p3'])
def test_curse_actual_enchanted_casts_and_frozen_player_loss(cards,loser):
    from tests.game_helpers import act
    from tests.test_rules_designations import settle

    s=game(cards)
    curse=cast(s,'Curse of Vengeance',['p2'])
    cast(s,'Lightning Bolt',['p3'],pid='p2')
    cast(s,'Lightning Bolt',['p3'],pid='p2')
    assert curse.counters.get('spite')==2
    before=len(s.state.zones['p1:hand'])
    act(s,loser,type='concede')
    settle(s)
    assert s.state.players['p1'].life==(42 if loser=='p2' else 40)
    assert len(s.state.zones['p1:hand'])==before+(2 if loser=='p2' else 0)
    roundtrip(s)


@pytest.mark.parametrize('kicked',[False,True])
def test_vigorous_charge_real_kicker_and_original_damage_watch(cards,kicked):
    from tests.test_rules_conditional_prevention import attack, damage

    s=game(cards)
    put(s,'Fervor','battlefield')
    bear=put(s,'Grizzly Bears','battlefield')
    spell=cast(s,'Vigorous Charge',[bear.id],kicker=int(kicked))
    assert spell.zone=='p1:graveyard'
    assert 'trample' in chars(s,bear).keywords
    attack(s,[bear])
    damage(s)
    assert s.state.players['p1'].life==(42 if kicked else 40)
    assert s.state.players['p2'].life==38
    roundtrip(s)


@pytest.mark.parametrize('blink',[False,True])
def test_vigorous_original_spell_and_creature_incarnations(cards,blink):
    from tests.test_rules_conditional_prevention import attack, damage

    s=game(cards)
    put(s,'Fervor','battlefield')
    bear=put(s,'Grizzly Bears','battlefield')
    cast(s,'Vigorous Charge',[bear.id],kicker=1)
    if blink:
        cast(s,'Cloudshift',[bear.id])
    else:
        cast(s,'Vigorous Charge',[bear.id],kicker=0)
    attack(s,[bear])
    damage(s)
    assert s.state.players['p1'].life==(40 if blink else 42)
    assert s.state.players['p2'].life==38
    roundtrip(s)


def test_mornsong_both_static_parts_and_source_departure(cards):
    s=game(cards)
    aria=cast(s,'Mornsong Aria')
    cast(s,'Healing Salve',['p1'],modes=[0])
    assert s.state.players['p1'].life==40
    before=len(s.state.zones['p1:hand'])
    cast(s,'Sign in Blood',['p1'])
    assert s.state.players['p1'].life==38
    assert len(s.state.zones['p1:hand'])==before
    cast(s,'Naturalize',[aria.id])
    cast(s,'Healing Salve',['p1'],modes=[0])
    assert s.state.players['p1'].life==41
    before=len(s.state.zones['p1:hand'])
    cast(s,'Sign in Blood',['p1'])
    assert len(s.state.zones['p1:hand'])==before+2
    roundtrip(s)


def test_mornsong_draw_step_search_is_not_drawing(cards):
    from tests.test_rules_conditional_prevention import choose
    from tests.test_rules_designations import settle
    from tests.test_rules_wave30m_durations import to_phase

    s=game(cards)
    cast(s,'Mornsong Aria')
    before=len(s.state.zones['p2:hand'])
    to_phase(s,'draw',turn=5)
    settle(s)
    d=s.state.rules.decision
    assert d and d.player=='p2'
    assert s.state.players['p2'].life==37
    choose(s,[d.options[0].id])
    assert len(s.state.zones['p2:hand'])==before+1
    assert s.state.rules.turn_log.drew.get('p2',0)==0
    roundtrip(s)


@pytest.mark.parametrize('double',[False,True])
def test_heroic_food_and_actual_gain_target_cap(cards,double):
    from tests.test_rules_conditional_prevention import activate, choose

    s=game(cards)
    own=[put(s,name,'battlefield') for name in ['Grizzly Bears','Rumbling Baloth','Glistener Elf','Llanowar Elves']]
    enemy=put(s,'Grizzly Bears','battlefield','p2')
    if double:
        put(s,"Alhammarret's Archive",'battlefield')
    cast(s,'Heroic Feast')
    foods=[c for c in s.state.cards.values() if c.zone=='p1:battlefield' and c.token and 'Food' in chars(s,c).subtypes]
    assert len(foods)==1
    activate(s,foods[0],'{2}')
    d=s.state.rules.decision
    assert d and d.min_choices==0 and d.max_choices==min(4,6 if double else 3)
    assert enemy.id not in {o.id for o in d.options}
    choose(s,[own[0].id,own[1].id])
    assert all(c.counters.get('+1/+1',0)==int(i<2) for i,c in enumerate(own))
    assert s.state.players['p1'].life==(46 if double else 43)
    assert foods[0].id not in s.state.cards or s.state.cards[foods[0].id].zone!='p1:battlefield'
    roundtrip(s)


def test_sengir_native_turn_start_value_not_current_life(cards):
    from tests.game_helpers import act
    from tests.test_rules_designations import settle

    s=game(cards)
    source=cast(s,'Sengir, the Dark Baron')
    assert s.state.turn.starting_life['p2']==40
    cast(s,'Lightning Bolt',['p2'])
    assert s.state.players['p2'].life==37
    act(s,'p2',type='concede')
    settle(s)
    assert s.state.players['p1'].life==80
    assert source.zone=='p1:battlefield'
    roundtrip(s)


def test_sengir_actual_next_turn_snapshot_and_other_creature_death(cards):
    from tests.game_helpers import act
    from tests.test_rules_designations import settle
    from tests.test_rules_wave30m_durations import to_phase

    s=game(cards)
    source=cast(s,'Sengir, the Dark Baron')
    bear=put(s,'Grizzly Bears','battlefield','p2')
    cast(s,'Lightning Bolt',[bear.id])
    assert source.counters.get('+1/+1')==2
    cast(s,'Lightning Bolt',['p2'])
    to_phase(s,'main1',turn=5)
    assert s.state.turn.starting_life['p2']==37
    cast(s,'Lightning Bolt',['p2'],pid='p2')
    assert s.state.players['p2'].life==34
    act(s,'p2',type='concede')
    settle(s)
    assert s.state.players['p1'].life==77
    roundtrip(s)


def test_sengir_legacy_unknown_is_explicit_not_invented(cards):
    from app.game.session import GameSession
    from app.game.state import GameState
    from tests.game_helpers import act
    from tests.test_rules_conditional_prevention import choose
    from tests.test_rules_designations import settle

    s=game(cards)
    cast(s,'Sengir, the Dark Baron')
    raw=s.state.model_dump(mode='json')
    raw['turn'].pop('starting_life')
    raw['rules']['turn_log'].pop('starting_life')
    legacy=GameState.model_validate(raw)
    assert legacy.turn.starting_life is None
    assert GameState.model_validate_json(legacy.model_dump_json()).turn.starting_life is None
    s=GameSession(legacy,cards=cards)
    act(s,'p2',type='concede')
    settle(s)
    assert s.state.rules.decision and s.state.rules.decision.kind=='manual_resolution'
    assert s.state.players['p1'].life==40
    choose(s,['done'])
    assert s.state.rules.decision is None
    assert s.state.players['p1'].life==40
    roundtrip(s)


@pytest.mark.parametrize('stage',['talus','floorboards','courageous','madness','mornsong','heroic','sengir'])
def test_saved_native_sequence_fresh_process(tmp_path,cards,stage):
    import subprocess
    import sys

    from tests.game_helpers import act
    from tests.test_rules_conditional_prevention import activate, choose
    from tests.test_rules_designations import settle
    from tests.test_rules_wave30m_durations import to_phase

    s=game(cards)
    if stage=='talus':
        source=cast(s,'Talus Paladin')
    elif stage=='sengir':
        source=cast(s,'Sengir, the Dark Baron')
        cast(s,'Lightning Bolt',['p2'])
        act(s,'p1',type='set_prefs',hold_priority=True)
        act(s,'p2',type='concede')
        assert s.state.zones['stack']
    elif stage=='mornsong':
        source=cast(s,'Mornsong Aria')
        to_phase(s,'draw',turn=5)
        settle(s)
    elif stage=='heroic':
        put(s,'Grizzly Bears','battlefield')
        put(s,'Llanowar Elves','battlefield')
        source=cast(s,'Heroic Feast')
        cast(s,'Healing Salve',['p1'],modes=[0])
    elif stage=='madness':
        source=put(s,'From Under the Floorboards','hand')
        cast(s,"Nahiri's Wrath",[],x_value=1,target_counts=[0],cost_choices=[{'component':0,'cards':[source.id]}])
        choose(s,['yes'])
        assert s.state.rules.decision and any(o.id=='x:2' for o in s.state.rules.decision.options)
    elif stage=='floorboards':
        put(s,'Angel of Vitality','battlefield')
        put(s,"Alhammarret's Archive",'battlefield')
        source=cast(s,'From Under the Floorboards')
    else:
        worship=put(s,'Words of Worship','battlefield')
        put(s,'Angel of Vitality','battlefield')
        put(s,"Alhammarret's Archive",'battlefield')
        s.state.players['p1'].life=5
        activate(s,worship,'next time')
        source=cast(s,'Courageous Resolve',[],target_counts=[0])
    assert s.state.rules.decision or (stage=='sengir' and s.state.zones['stack']),stage
    saved=tmp_path/'state.json'
    saved.write_text(s.state.model_dump_json())
    code=r'''
import sys
from pathlib import Path
from app.cards.repository import CardRepository
from app.cards.images import ImageStore
from app.game.session import GameSession
from app.game.state import GameState
from app.rules import life_lock
from app.rules.plan import Plan
from tests.test_rules_designations import pick,settle,roundtrip
r=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=r)
stage=sys.argv[3];source=sys.argv[4]
assert s.state.rules.decision or (stage=='sengir' and s.state.zones['stack'])
if stage=='sengir':
 assert any(e.event and e.event.kind=='lose_game' and e.event.turn_start_life==40 for e in s.state.rules.stack.values())
 settle(s)
 assert s.state.players['p1'].life==80
elif stage=='talus':
 pick(s,['decline']);settle(s)
 assert s.state.rules.decision
 pick(s,['pay']);settle(s)
 c=s.state.cards[source]
 assert c.counters.get('+1/+1')==1
 assert 'lifelink' not in Plan(s.state,'p1',r,None).ch(c).keywords
elif stage=='mornsong':
 before=len(s.state.zones['p2:hand'])
 d=s.state.rules.decision
 assert d.player=='p2'
 pick(s,[d.options[0].id]);settle(s)
 assert s.state.players['p2'].life==37
 assert len(s.state.zones['p2:hand'])==before+1
 assert s.state.rules.turn_log.drew.get('p2',0)==0
elif stage=='heroic':
 d=s.state.rules.decision
 selected=d.options[0].id
 others=[o.id for o in d.options[1:]]
 pick(s,[selected]);settle(s)
 assert s.state.cards[selected].counters.get('+1/+1')==1
 assert all(s.state.cards[cid].counters.get('+1/+1',0)==0 for cid in others)
elif stage=='madness':
 pick(s,['x:2'])
 records=[p for p in s.state.rules.payments.values() if p.card==source and p.alternative=='madness']
 assert records and sum(records[-1].mana_spent.values())==4
 assert records[-1].x==2
 settle(s)
 tokens=[c for c in s.state.cards.values() if c.zone=='p1:battlefield' and c.token]
 assert len(tokens)==2
 assert s.state.players['p1'].life==42
else:
 while s.state.rules.decision:
  d=s.state.rules.decision
  pick(s,[d.options[0].id]);settle(s)
 if stage=='floorboards':
  tokens=[c for c in s.state.cards.values() if c.zone=='p1:battlefield' and c.token]
  assert len(tokens)==3,len(tokens)
  assert s.state.players['p1'].life in (47,48)
 else:
  assert s.state.players['p1'].life>=16
  assert life_lock.why_not(Plan(s.state,'p1',r,None),'p1','lose') is None
roundtrip(s)
'''
    result=subprocess.run([sys.executable,'-c',code,str(saved),str(cards.db_path),stage,source.id],capture_output=True,text=True)
    assert result.returncode==0,result.stdout+result.stderr


@pytest.mark.parametrize('gift_self', [False, True])
@pytest.mark.parametrize('cold', [False, True])
def test_blim_real_combat_transfer_and_frozen_per_player_counts(cards, gift_self, cold, tmp_path):
    from tests.game_helpers import act
    from tests.test_rules_conditional_prevention import attack, choose, damage

    s = game(cards)
    put(s, 'Fervor', 'battlefield')
    blim = cast(s, 'Blim, Comedic Genius')
    gift = blim if gift_self else put(s, 'Sol Ring', 'battlefield')
    foreign = put(s, 'Forest', 'battlefield', 'p3')
    act(s, 'p1', type='set_controller', card_ids=[foreign.id], player='p1')
    for pid in ('p1', 'p2'):
        put(s, 'Grizzly Bears', 'hand', pid)
        put(s, 'Llanowar Elves', 'hand', pid)
    attack(s, [blim])
    damage(s)
    d = s.state.rules.decision
    assert d and any(o.id == gift.id for o in d.options)
    choose(s, [gift.id])
    assert gift.controller == 'p2' and gift.owner == 'p1'
    assert s.state.players['p1'].life == 39
    assert s.state.players['p2'].life == 35
    assert s.state.players['p3'].life == 40
    hands = {p: set(s.state.zones[p + ':hand']) for p in ('p1', 'p2')}
    first = s.state.rules.decision
    assert first and first.player == 'p1' and first.min_choices == first.max_choices == 1
    choose(s, [first.options[0].id])
    assert set(s.state.zones['p1:hand']) == hands['p1']
    second = s.state.rules.decision
    assert second and second.player == 'p2' and second.min_choices == second.max_choices == 1
    if cold:
        import subprocess
        import sys

        saved = tmp_path / 'blim.json'
        saved.write_text(s.state.model_dump_json())
        code = r'''
import sys
from pathlib import Path
from app.cards.repository import CardRepository
from app.cards.images import ImageStore
from app.game.session import GameSession
from app.game.state import GameState
from tests.test_rules_conditional_prevention import choose
from tests.test_rules_designations import roundtrip
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
d=s.state.rules.decision
assert d and d.player=='p2' and d.min_choices==d.max_choices==1
assert d.resume['counts']=={'p1':1,'p2':1,'p3':0}
before={p:len(s.state.zones[p+':hand']) for p in ('p1','p2')}
choose(s,[d.options[0].id])
assert all(len(s.state.zones[p+':hand'])==before[p]-1 for p in before)
assert s.state.players['p1'].life==39 and s.state.players['p2'].life==35
roundtrip(s)
'''
        result = subprocess.run([sys.executable, '-c', code, str(saved), str(cards.db_path)], capture_output=True, text=True)
        assert result.returncode == 0, result.stdout + result.stderr
        return
    choose(s, [second.options[0].id])
    assert len(s.state.zones['p1:hand']) == len(hands['p1']) - 1
    assert len(s.state.zones['p2:hand']) == len(hands['p2']) - 1
    roundtrip(s)

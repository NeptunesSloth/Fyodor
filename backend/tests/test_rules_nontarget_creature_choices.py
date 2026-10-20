"""Canonical non-target creature choices reuse native public choices and effects."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import casting, coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana, wait_priority
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_remaining_talents import pay
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave6c_tokens_pumps import chars
from tests.test_rules_wave30m_durations import to_phase

NAMES=['Duneblast', 'Highcliff Felidar', "Sigarda's Vanguard", 'Sigardian Zealot', 'Celestial Judgment', 'Gruesome Menagerie', 'Dawnbreak Reclaimer', 'Azra Oddsmaker', "Gideon's Sacrifice", 'Kamiz, Obscura Oculus', 'Winnowing']
EXTRA=['Servant of the Scale','Doubling Season','Centaur Courser','Grizzly Bears', 'Llanowar Elves', 'Siege Mastodon', 'Sol Ring', 'Shock', 'Lightning Bolt', 'Counterspell', 'Doom Blade', 'Abundance', 'Forest', 'Island', 'Hardened Scales', 'Memnite', 'Fervor', 'Shivan Dragon', 'Soul Warden', 'Raise the Alarm', 'Giant Growth', 'Invisible Stalker', 'Adaptive Automaton', 'Changeling Outcast', 'Reverberate', 'Narset, Parter of Veils', 'Disenchant', 'Solemnity', 'Darksteel Myr', 'Wrath of God', 'Inspiring Cleric', 'Elvish Mystic']

@pytest.fixture()
def cards(settings):
    base={c['name']:c for c in fixture_cards()}
    for i,c in enumerate(json.loads((Path(__file__).parent/'fixtures/nontarget_creature_choices_cards.json').read_text())):
        base[c['name']]=card(c['name'],set_code='scf',number=str(i),**{k:v for k,v in c.items() if k!='name'})
    settings.ensure_dirs()
    build_database(base.values(),settings.cards_db_path)
    repo=CardRepository(settings.cards_db_path,ImageStore(settings.images_dir))
    yield repo
    repo.close()


def game(cards):
    ns=[*NAMES,*EXTRA]
    return table(cards,ns,ns,ns)


def suspend(s,name,pid='p1'):
    source=put(s,name,'hand',pid)
    ch=chars(s,source)
    ab=next(a.index for a in ch.abilities if 'suspend' in a.keywords)
    n,cost=casting.suspend_info(ch,ab)
    from app.rules import mana as M
    parsed=M.parse_cost(cost)
    pool={'C':parsed.generic}
    for color in parsed.colored:
        pool[color]=pool.get(color,0)+1
    mana(s,pid=pid,**pool)
    wait_priority(s,pid)
    act(s,pid,type='activate_ability',card_id=source.id,ability=ab,sources=[])
    assert s.state.cards[source.id].zone==f'{pid}:exile'
    assert s.state.cards[source.id].counters.get('time')==n
    return source


def choose(s,value):
    d=s.state.rules.decision
    assert d and value in {o.id for o in d.options},(d,value)
    act(s,d.player,type='choose',decision_id=d.id,option_ids=[value])
    settle(s)


def cast(s,name,target=None,pid='p1',**kwargs):
    source=put(s,name,'hand',pid)
    pay(s,pid,name)
    wait_priority(s,pid)
    act(s,pid,type='cast_spell',card_id=source.id,targets=[target] if target else [],sources=[],**kwargs)
    settle(s)
    return source


@pytest.mark.parametrize('name',NAMES)
def test_canonical_full(cards,name):
    result=coverage.of_card_data(cards.resolve(name))
    assert result.level=='FULL', result.manual_parts


def answer(s,ids):
    d=s.state.rules.decision
    assert d
    act(s,d.player,type='choose',decision_id=d.id,option_ids=ids)
    settle(s)


@pytest.mark.parametrize('spare',[False,True])
def test_duneblast_resolution_choice_is_global_optional_and_not_targeted(cards,spare):
    s=game(cards)
    bear=put(s,'Grizzly Bears','battlefield')
    stalker=put(s,'Invisible Stalker','battlefield','p2')
    cast(s,'Duneblast')
    d=s.state.rules.decision
    assert d and d.resume['step']=='player_chooses'
    assert stalker.id in {o.id for o in d.options}
    answer(s,[stalker.id] if spare else [])
    assert s.state.cards[bear.id].zone=='p1:graveyard'
    assert s.state.cards[stalker.id].zone==('p2:battlefield' if spare else 'p2:graveyard')
    roundtrip(s)


def test_highcliff_controller_selects_tied_greatest_opponent_creatures(cards):
    s=game(cards)
    bear=put(s,'Grizzly Bears','battlefield','p2')
    big=put(s,'Siege Mastodon','battlefield','p2')
    elf=put(s,'Llanowar Elves','battlefield','p3')
    stalker=put(s,'Invisible Stalker','battlefield','p3')
    cast(s,'Highcliff Felidar')
    d=s.state.rules.decision
    assert d and d.player=='p1'
    assert {o.id for o in d.options}=={elf.id,stalker.id}
    assert s.state.cards[big.id].zone=='p2:battlefield'
    answer(s,[stalker.id])
    assert s.state.cards[big.id].zone=='p2:graveyard'
    assert s.state.cards[stalker.id].zone=='p3:graveyard'
    assert s.state.cards[bear.id].zone=='p2:battlefield'
    roundtrip(s)


def test_sigarda_chooses_global_distinct_powers_and_rejects_duplicate_power(cards):
    from app.game.errors import ActionError
    s=game(cards)
    bear=put(s,'Grizzly Bears','battlefield')
    other=put(s,'Grizzly Bears','battlefield','p2')
    elf=put(s,'Llanowar Elves','battlefield','p2')
    cast(s,"Sigarda's Vanguard")
    d=s.state.rules.decision
    assert d
    with pytest.raises(ActionError,match='different powers'):
        act(s,d.player,type='choose',decision_id=d.id,option_ids=[bear.id,other.id])
    answer(s,[bear.id,elf.id])
    assert 'double strike' in chars(s,s.state.cards[bear.id]).keywords
    assert 'double strike' in chars(s,s.state.cards[elf.id]).keywords
    assert 'double strike' not in chars(s,s.state.cards[other.id]).keywords
    roundtrip(s)


def test_sigardian_source_power_pumps_only_distinct_power_selection(cards):
    s=game(cards)
    bear=put(s,'Grizzly Bears','battlefield')
    source=cast(s,'Sigardian Zealot')
    to_phase(s,'begin_combat')
    settle(s)
    answer(s,[source.id,bear.id])
    assert chars(s,s.state.cards[bear.id]).pt==(5,5)
    assert chars(s,s.state.cards[source.id]).pt==(6,6)
    assert 'vigilance' in chars(s,s.state.cards[bear.id]).keywords
    roundtrip(s)


def test_celestial_judgment_one_per_power_then_simultaneous_destroy(cards):
    s=game(cards)
    bear=put(s,'Grizzly Bears','battlefield')
    other=put(s,'Grizzly Bears','battlefield','p2')
    elf=put(s,'Llanowar Elves','battlefield','p3')
    stalker=put(s,'Invisible Stalker','battlefield','p2')
    cast(s,'Celestial Judgment')
    answer(s,[stalker.id])
    assert s.state.cards[elf.id].zone=='p3:battlefield'
    answer(s,[bear.id])
    assert s.state.cards[elf.id].zone=='p3:graveyard'
    assert s.state.cards[other.id].zone=='p2:graveyard'
    assert s.state.cards[stalker.id].zone=='p2:battlefield'
    assert s.state.cards[bear.id].zone=='p1:battlefield'
    roundtrip(s)


def test_gruesome_menagerie_native_simultaneous_return_sees_other_entries(cards):
    s=game(cards)
    warden=put(s,'Soul Warden','graveyard')
    bear=put(s,'Grizzly Bears','graveyard')
    third=put(s,'Centaur Courser','graveyard')
    cast(s,'Gruesome Menagerie')
    assert all(s.state.cards[c.id].zone=='p1:battlefield' for c in [warden,bear,third])
    assert s.state.players['p1'].life==42
    roundtrip(s)


def test_dawnbreak_opponent_chooses_own_graveyard_then_optional_simultaneous_return(cards):
    s=game(cards)
    cast(s,'Dawnbreak Reclaimer')
    their=put(s,'Centaur Courser','graveyard','p2')
    own=put(s,'Grizzly Bears','graveyard')
    other=put(s,'Llanowar Elves','graveyard')
    to_phase(s,'end')
    settle(s)
    d=s.state.rules.decision
    assert d and d.player=='p2'
    assert {o.id for o in d.options}=={own.id,other.id}
    answer(s,[own.id])
    choose(s,'pay')
    assert s.state.cards[own.id].zone=='p1:battlefield'
    assert s.state.cards[their.id].zone=='p2:battlefield'
    assert s.state.cards[other.id].zone=='p1:graveyard'
    roundtrip(s)


def test_dawnbreak_empty_opponent_graveyards_still_returns_own_creature(cards):
    s=game(cards)
    cast(s,'Dawnbreak Reclaimer')
    own=put(s,'Grizzly Bears','graveyard')
    to_phase(s,'end')
    settle(s)
    choose(s,'p3')
    choose(s,'pay')
    assert s.state.cards[own.id].zone=='p1:battlefield'
    roundtrip(s)


def test_azra_discard_then_nontarget_choice_creates_repeated_draw_watch(cards):
    s=game(cards)
    source=cast(s,'Azra Oddsmaker')
    bear=put(s,'Grizzly Bears','battlefield')
    discard=put(s,'Shock','hand')
    to_phase(s,'begin_combat',turn=4)
    settle(s)
    choose(s,'pay')
    d=s.state.rules.decision
    assert d
    answer(s,[discard.id])
    answer(s,[bear.id])
    to_phase(s,'declare_attackers')
    drawn=s.state.rules.turn_log.drew.get('p1',0)
    act(s,'p1',type='declare_attackers',attackers=[{'card_id':bear.id,'target':'p3'}])
    to_phase(s,'combat_damage')
    settle(s)
    assert s.state.rules.turn_log.drew.get('p1',0)==drawn+2
    assert s.state.cards[discard.id].zone=='p1:graveyard'
    assert s.state.cards[source.id].zone=='p1:battlefield'
    roundtrip(s)


def test_gideon_chosen_creature_redirects_then_departure_stops_redirect(cards):
    s=game(cards)
    bear=put(s,'Grizzly Bears','battlefield')
    cast(s,"Gideon's Sacrifice")
    cast(s,'Shock','p1',pid='p2')
    assert s.state.players['p1'].life==40
    assert s.state.cards[bear.id].zone=='p1:graveyard'
    cast(s,'Shock','p1',pid='p2')
    assert s.state.players['p1'].life==38
    roundtrip(s)


def test_kamiz_connive_changes_power_before_non_target_lesser_power_choice(cards):
    s=game(cards)
    cast(s,'Kamiz, Obscura Oculus')
    bear=put(s,'Grizzly Bears','battlefield')
    other=put(s,'Adaptive Automaton','battlefield')
    to_phase(s,'declare_attackers',turn=4)
    discard=put(s,'Shock','hand')
    act(s,'p1',type='declare_attackers',attackers=[{'card_id':bear.id,'target':'p2'},{'card_id':other.id,'target':'p3'}])
    settle(s)
    answer(s,[bear.id])
    answer(s,[discard.id])
    assert s.state.cards[bear.id].counters.get('+1/+1')==1
    assert 'double strike' in chars(s,s.state.cards[other.id]).keywords
    assert 'double strike' not in chars(s,s.state.cards[bear.id]).keywords
    roundtrip(s)


def test_winnowing_controller_choices_spare_only_shared_types_with_changeling(cards):
    s=game(cards)
    bear=put(s,'Grizzly Bears','battlefield')
    elf=put(s,'Llanowar Elves','battlefield')
    centaur=put(s,'Centaur Courser','battlefield','p2')
    otherbear=put(s,'Grizzly Bears','battlefield','p2')
    changeling=put(s,'Changeling Outcast','battlefield','p3')
    otherelf=put(s,'Elvish Mystic','battlefield','p3')
    cast(s,'Winnowing')
    for selected in [bear,centaur,changeling]:
        d=s.state.rules.decision
        assert d and d.player=='p1'
        answer(s,[selected.id])
    assert s.state.cards[elf.id].zone=='p1:graveyard'
    assert s.state.cards[otherbear.id].zone=='p2:graveyard'
    assert all(s.state.cards[c.id].zone.endswith(':battlefield') for c in [bear,centaur,changeling,otherelf])
    roundtrip(s)


def test_distinct_power_choices_use_current_zero_negative_values_and_allow_empty(cards):
    s=game(cards)
    bear=put(s,'Grizzly Bears','battlefield')
    elf=put(s,'Llanowar Elves','battlefield','p2')
    act(s,'p1',type='set_counter',card_id=bear.id,kind='-1/-0',value=2)
    act(s,'p2',type='set_counter',card_id=elf.id,kind='-1/-0',value=2)
    source=cast(s,"Sigarda's Vanguard")
    answer(s,[bear.id,elf.id])
    assert chars(s,s.state.cards[bear.id]).pt[0]==0
    assert chars(s,s.state.cards[elf.id]).pt[0]==-1
    assert all('double strike' in chars(s,s.state.cards[c.id]).keywords for c in [bear,elf])
    act(s,'p1',type='move',card_ids=[source.id],to={'player':'p1','zone':'hand'})
    pay(s,'p1',"Sigarda's Vanguard")
    wait_priority(s,'p1')
    act(s,'p1',type='cast_spell',card_id=source.id,sources=[])
    settle(s)
    answer(s,[])
    assert s.state.rules.decision is None
    roundtrip(s)


def test_dawnbreak_original_opponent_graveyard_object_cannot_rejoin_return(cards):
    s=game(cards)
    cast(s,'Dawnbreak Reclaimer')
    their=put(s,'Grizzly Bears','graveyard','p2')
    own=put(s,'Llanowar Elves','graveyard')
    to_phase(s,'end')
    settle(s)
    d=s.state.rules.decision
    assert d and {o.id for o in d.options}=={'pay','decline'}
    act(s,'p2',type='move',card_ids=[their.id],to={'player':'p2','zone':'hand'})
    act(s,'p2',type='move',card_ids=[their.id],to={'player':'p2','zone':'graveyard'})
    choose(s,'pay')
    assert s.state.cards[own.id].zone=='p1:battlefield'
    assert s.state.cards[their.id].zone=='p2:graveyard'
    roundtrip(s)


def test_kamiz_uses_original_attacker_lki_after_departure_during_connive(cards):
    s=game(cards)
    cast(s,'Kamiz, Obscura Oculus')
    bear=put(s,'Grizzly Bears','battlefield')
    other=put(s,'Adaptive Automaton','battlefield')
    act(s,'p1',type='set_counter',card_id=bear.id,kind='+1/+1',value=2)
    to_phase(s,'declare_attackers',turn=4)
    discard=put(s,'Shock','hand')
    act(s,'p1',type='declare_attackers',attackers=[{'card_id':bear.id,'target':'p2'},{'card_id':other.id,'target':'p3'}])
    settle(s)
    answer(s,[bear.id])
    assert s.state.rules.decision
    act(s,'p1',type='move',card_ids=[bear.id],to={'player':'p1','zone':'graveyard'})
    act(s,'p1',type='move',card_ids=[bear.id],to={'player':'p1','zone':'battlefield'})
    answer(s,[discard.id])
    assert 'double strike' in chars(s,s.state.cards[other.id]).keywords
    assert s.state.cards[bear.id].counters.get('+1/+1',0)==0
    roundtrip(s)


@pytest.mark.parametrize('stage',['partition','reclaimer','connive','entry'])
def test_native_choices_and_simultaneous_entry_resume_in_fresh_process(cards,tmp_path,stage):
    import subprocess
    import sys
    s=game(cards)
    expected=[]
    if stage=='partition':
        bear=put(s,'Grizzly Bears','battlefield')
        put(s,'Grizzly Bears','battlefield','p2')
        put(s,'Llanowar Elves','battlefield','p3')
        stalker=put(s,'Invisible Stalker','battlefield','p2')
        cast(s,'Celestial Judgment')
        picks=[stalker.id,bear.id]
        expected=[bear.id,stalker.id]
    elif stage=='reclaimer':
        cast(s,'Dawnbreak Reclaimer')
        their=put(s,'Centaur Courser','graveyard','p2')
        own=put(s,'Grizzly Bears','graveyard')
        put(s,'Llanowar Elves','graveyard')
        to_phase(s,'end')
        settle(s)
        picks=[own.id]
        expected=[own.id,their.id]
    elif stage=='connive':
        cast(s,'Kamiz, Obscura Oculus')
        bear=put(s,'Grizzly Bears','battlefield')
        other=put(s,'Adaptive Automaton','battlefield')
        to_phase(s,'declare_attackers',turn=4)
        discard=put(s,'Shock','hand')
        act(s,'p1',type='declare_attackers',attackers=[{'card_id':bear.id,'target':'p2'},{'card_id':other.id,'target':'p3'}])
        settle(s)
        answer(s,[bear.id])
        picks=[discard.id]
        expected=[other.id]
    else:
        put(s,'Hardened Scales','battlefield')
        put(s,'Doubling Season','battlefield')
        servant=put(s,'Servant of the Scale','graveyard')
        bear=put(s,'Grizzly Bears','graveyard')
        third=put(s,'Centaur Courser','graveyard')
        cast(s,'Gruesome Menagerie')
        picks=[]
        expected=[servant.id,bear.id,third.id]
    assert s.state.rules.decision
    saved=tmp_path/f'{stage}.json'
    saved.write_text(s.state.model_dump_json())
    code=r'''
import json,sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.test_rules_wave6c_tokens_pumps import chars
save,db,picks,expected,stage=sys.argv[1:]
picks,expected=json.loads(picks),json.loads(expected)
repo=CardRepository(Path(db),ImageStore(Path(db).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(save).read_text()),cards=repo)
for _ in range(60):
 d=s.state.rules.decision
 if d:
  options={o.id for o in d.options}
  chosen=next((p for p in picks if p in options),None)
  if chosen is None:chosen='pay' if 'pay' in options else d.options[0].id
  s.perform(d.player,{'type':'choose','decision_id':d.id,'option_ids':[chosen]})
 elif s.state.zones['stack']:
  s.perform(s.state.rules.priority,{'type':'pass_priority'})
 else:break
else:raise AssertionError('did not finish')
assert all(s.state.cards[cid].zone.endswith(':battlefield') for cid in expected)
if stage=='connive':assert 'double strike' in chars(s,s.state.cards[expected[0]]).keywords
if stage=='entry':assert s.state.cards[expected[0]].counters['+1/+1'] in (3,4)
assert s.history.rebuild().model_dump(mode='json')==s.state.model_dump(mode='json')
repo.close()
'''
    result=subprocess.run([sys.executable,'-c',code,str(saved),str(cards.db_path),json.dumps(picks),json.dumps(expected),stage],cwd=Path(__file__).resolve().parents[1],capture_output=True,text=True,timeout=60)
    assert result.returncode==0,result.stderr

"""Canonical among-permanent counter quantities remain independent and replayable."""
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
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_remaining_talents import pay
from tests.test_rules_shared_damage_choices import table

NAMES = ['Slippery Bogbonder','Aetherborn Marauder','Galloping Lizrog',"Eventide's Shadow",'Sensational Spider-Man','Garnet, Princess of Alexandria']


@pytest.fixture()
def cards(settings):
    base = {c['name']:c for c in fixture_cards()}
    for i,c in enumerate(json.loads((Path(__file__).parent/'fixtures/counter_group_choice_cards.json').read_text())):
        base[c['name']] = card(c['name'],set_code='gcq',number=str(i),**{k:v for k,v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(),settings.cards_db_path)
    repo=CardRepository(settings.cards_db_path,ImageStore(settings.images_dir))
    yield repo
    repo.close()


def game(cards):
    names=[*NAMES,'Grizzly Bears','Doubling Season','Solemnity','Hardened Scales','Vorinclex, Monstrous Raider','The Birth of Meletis','The Akroan War','Shock']
    return table(cards,names,names,['Grizzly Bears'])


def counter(s,c,k,n):
    act(s,'p1',type='set_counter',card_id=c.id,kind=k,value=n)


def cast(s,name,target=None):
    c=put(s,name,'hand')
    pay(s,'p1',name)
    act(s,'p1',type='cast_spell',card_id=c.id,sources=[])
    settle(s)
    if target is not None:
        d=s.state.rules.decision
        assert d and d.kind in ('targets','choose_one'), (d.kind if d else None,d.prompt if d else None)
        act(s,d.player,type='choose',decision_id=d.id,option_ids=[target.id])
        settle(s)
    return c


def number(s,n):
    d=s.state.rules.decision
    assert d and d.resume['step']=='choose_group_counters', (d.kind if d else None,d.prompt if d else None)
    act(s,d.player,type='choose',decision_id=d.id,name=str(n))
    settle(s)


@pytest.mark.parametrize('name',NAMES)
def test_full(cards,name):
    assert coverage.of_card_data(cards.resolve(name)).level=='FULL'


def test_marauder_chooses_same_kind_independently_per_permanent(cards):
    s=game(cards)
    a=put(s,'Grizzly Bears','battlefield')
    counter(s,a,'+1/+1',3)
    b=put(s,'The Birth of Meletis','battlefield')
    counter(s,b,'+1/+1',4)
    source=cast(s,'Aetherborn Marauder')
    roundtrip(s)
    number(s,1)
    roundtrip(s)
    number(s,3)
    assert s.state.cards[a.id].counters['+1/+1']==2
    assert s.state.cards[b.id].counters['+1/+1']==1
    assert s.state.cards[source.id].counters['+1/+1']==4
    roundtrip(s)


def test_lizrog_counts_actual_selected_removals_and_doubles_native_put(cards):
    s=game(cards)
    a=put(s,'Grizzly Bears','battlefield')
    b=put(s,'Slippery Bogbonder','battlefield')
    counter(s,a,'+1/+1',4)
    counter(s,b,'+1/+1',2)
    put(s,'Doubling Season','battlefield')
    source=cast(s,'Galloping Lizrog')
    number(s,3)
    number(s,1)
    assert s.state.cards[source.id].counters['+1/+1']==16
    assert s.state.cards[a.id].counters['+1/+1']==1
    assert s.state.cards[b.id].counters['+1/+1']==1
    roundtrip(s)


def test_eventide_mixed_opponent_counters_actual_draw_and_loss(cards):
    s=game(cards)
    a=put(s,'Grizzly Bears','battlefield')
    b=put(s,'Slippery Bogbonder','battlefield','p2')
    counter(s,a,'+1/+1',3)
    counter(s,b,'stun',2)
    before=len([c for c in s.state.cards.values() if c.zone=='p1:hand'])
    life=s.state.players['p1'].life
    cast(s,"Eventide's Shadow")
    number(s,1)
    number(s,2)
    assert s.state.cards[a.id].counters['+1/+1']==2
    assert not s.state.cards[b.id].counters
    assert s.state.players['p1'].life==life-3
    assert len([c for c in s.state.cards.values() if c.zone=='p1:hand'])==before+3
    roundtrip(s)


def test_bogbonder_moves_chosen_kinds_from_chosen_sources_not_destination(cards):
    s=game(cards)
    a=put(s,'Grizzly Bears','battlefield')
    b=put(s,'Galloping Lizrog','battlefield')
    target=put(s,'Sensational Spider-Man','battlefield')
    counter(s,a,'+1/+1',2)
    counter(s,b,'stun',3)
    counter(s,target,'stun',4)
    cast(s,'Slippery Bogbonder',target)
    assert s.state.cards[target.id].counters['hexproof']==1
    number(s,1)
    number(s,2)
    assert s.state.cards[a.id].counters['+1/+1']==1
    assert s.state.cards[b.id].counters['stun']==1
    assert s.state.cards[target.id].counters=={'stun':6,'hexproof':1,'+1/+1':1}
    roundtrip(s)


def test_move_is_impossible_under_solemnity_but_removal_is_allowed(cards):
    s=game(cards)
    a=put(s,'Grizzly Bears','battlefield')
    counter(s,a,'+1/+1',3)
    put(s,'Solemnity','battlefield')
    source=cast(s,'Aetherborn Marauder')
    assert s.state.rules.decision is None
    assert s.state.cards[a.id].counters['+1/+1']==3
    assert not s.state.cards[source.id].counters
    cast(s,'Galloping Lizrog')
    number(s,2)
    assert s.state.cards[a.id].counters['+1/+1']==1
    assert not [c for c in s.state.cards.values() if c.name=='Galloping Lizrog' and c.zone=='p1:battlefield' and c.counters]
    roundtrip(s)


def test_zero_selection_draws_and_loses_nothing(cards):
    s=game(cards)
    a=put(s,'Grizzly Bears','battlefield')
    counter(s,a,'+1/+1',2)
    life=s.state.players['p1'].life
    hand=len(s.state.zones['p1:hand'])
    cast(s,"Eventide's Shadow")
    number(s,0)
    assert s.state.players['p1'].life==life
    assert len(s.state.zones['p1:hand'])==hand
    assert s.state.cards[a.id].counters['+1/+1']==2
    roundtrip(s)


def attack(s,c):
    from tests.test_rules_wave30m_durations import to_phase
    to_phase(s,'declare_attackers',turn=4)
    act(s,'p1',type='declare_attackers',attackers=[{'card_id':c.id,'target':'p2'}])
    settle(s)


def test_spider_caps_total_across_permanents_and_draws_actual_three(cards):
    s=game(cards)
    spider=put(s,'Sensational Spider-Man','battlefield')
    a=put(s,'Grizzly Bears','battlefield')
    b=put(s,'Galloping Lizrog','battlefield','p2')
    counter(s,a,'stun',2)
    counter(s,b,'stun',2)
    attack(s,spider)
    d=s.state.rules.decision
    assert d and d.kind in ('targets','choose_one')
    act(s,d.player,type='choose',decision_id=d.id,option_ids=[b.id])
    settle(s)
    assert s.state.cards[b.id].tapped and s.state.cards[b.id].counters['stun']==3
    before=len(s.state.zones['p1:hand'])
    number(s,2)
    roundtrip(s)
    number(s,1)
    assert not s.state.cards[a.id].counters
    assert s.state.cards[b.id].counters['stun']==2
    assert len(s.state.zones['p1:hand'])==before+3
    roundtrip(s)


def test_garnet_removes_at_most_one_lore_from_each_chosen_saga(cards):
    s=game(cards)
    garnet=put(s,'Garnet, Princess of Alexandria','battlefield')
    from tests.test_rules_wave30m_durations import to_phase
    to_phase(s,'declare_attackers',turn=4)
    a=put(s,'The Birth of Meletis','battlefield')
    b=put(s,'The Akroan War','battlefield')
    counter(s,a,'lore',2)
    counter(s,b,'lore',2)
    act(s,'p1',type='declare_attackers',attackers=[{'card_id':garnet.id,'target':'p2'}])
    settle(s)
    number(s,1)
    number(s,0)
    assert s.state.cards[a.id].counters['lore']==1
    assert s.state.cards[b.id].counters['lore']==2
    assert s.state.cards[garnet.id].counters['+1/+1']==1
    roundtrip(s)


def test_typed_amount_above_old_option_cap_and_invalid_answer_atomic(cards):
    from app.game.errors import ActionError
    s=game(cards)
    a=put(s,'Grizzly Bears','battlefield')
    counter(s,a,'+1/+1',100)
    source=cast(s,'Aetherborn Marauder')
    before=s.state.model_dump(mode='json')
    with pytest.raises(ActionError):
        number(s,101)
    assert s.state.model_dump(mode='json')==before
    number(s,73)
    assert s.state.cards[a.id].counters['+1/+1']==27
    assert s.state.cards[source.id].counters['+1/+1']==73
    roundtrip(s)


def test_saved_second_source_choice_resumes_in_fresh_process(cards,tmp_path):
    import subprocess
    import sys
    s=game(cards)
    a=put(s,'Grizzly Bears','battlefield')
    b=put(s,'Slippery Bogbonder','battlefield')
    counter(s,a,'+1/+1',3)
    counter(s,b,'+1/+1',4)
    source=cast(s,'Aetherborn Marauder')
    number(s,1)
    saved=tmp_path/'counter_choices.json'
    saved.write_text(s.state.model_dump_json())
    code=r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
save,database,a,b,source=sys.argv[1:]
repo=CardRepository(Path(database),ImageStore(Path(database).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(save).read_text()),cards=repo)
d=s.state.rules.decision
assert d.resume['step']=='choose_group_counters'
s.perform(d.player,{'type':'choose','decision_id':d.id,'name':'3'})
assert s.state.cards[a].counters['+1/+1']==2
assert s.state.cards[b].counters['+1/+1']==1
assert s.state.cards[source].counters['+1/+1']==4
assert s.history.rebuild().model_dump(mode='json')==s.state.model_dump(mode='json')
repo.close()
'''
    result=subprocess.run([sys.executable,'-c',code,str(saved),str(cards.db_path),a.id,b.id,source.id],
                          cwd=Path(__file__).resolve().parents[1],capture_output=True,text=True,timeout=60)
    assert result.returncode==0,result.stderr


def test_changed_source_object_is_excluded_even_if_new_object_has_counters(cards):
    s=game(cards)
    a=put(s,'Grizzly Bears','battlefield')
    counter(s,a,'+1/+1',3)
    source=cast(s,'Aetherborn Marauder')
    put(s,'Grizzly Bears','hand')
    put(s,'Grizzly Bears','battlefield')
    counter(s,a,'+1/+1',5)
    number(s,2)
    assert s.state.cards[a.id].counters['+1/+1']==5
    assert not s.state.cards[source.id].counters
    roundtrip(s)


def test_removed_destination_does_not_remove_any_chosen_source_counters(cards):
    s=game(cards)
    a=put(s,'Grizzly Bears','battlefield')
    counter(s,a,'+1/+1',3)
    source=cast(s,'Aetherborn Marauder')
    put(s,'Aetherborn Marauder','hand')
    number(s,2)
    assert s.state.cards[a.id].counters['+1/+1']==3
    assert not s.state.cards[source.id].counters
    roundtrip(s)


def test_move_native_counter_replacement_order_pauses_without_removing_twice(cards):
    s=game(cards)
    a=put(s,'Grizzly Bears','battlefield')
    counter(s,a,'+1/+1',3)
    put(s,'Doubling Season','battlefield')
    put(s,'Hardened Scales','battlefield')
    source=cast(s,'Aetherborn Marauder')
    number(s,2)
    assert s.state.cards[a.id].counters['+1/+1']==1
    d=s.state.rules.decision
    assert d and d.resume['step']=='replace_order'
    roundtrip(s)
    while s.state.rules.decision:
        d=s.state.rules.decision
        assert d.resume['step']=='replace_order'
        act(s,d.player,type='choose',decision_id=d.id,option_ids=[d.options[0].id])
        settle(s)
    assert s.state.cards[a.id].counters['+1/+1']==1
    assert s.state.cards[source.id].counters['+1/+1'] in (5,6)
    roundtrip(s)

from tests.test_rules_top_library_authorities69 import cards,setup,cast,put,stack_library,act,settle,roundtrip
from app.rules.plan import Plan
from app.rules.cost_payment import counter_tokens


def test_falco_remove_counter_then_sacrifice_same_creature_for_casualty(cards):
    s=setup(cards);cast(s,'Falco Spara, Pactweaver')
    bear=put(s,'Grizzly Bears','battlefield')
    act(s,'p1',type='set_counter',card_id=bear.id,kind='+1/+1',value=1)
    target=put(s,'Grizzly Bears','battlefield',pid='p2')
    top=stack_library(s,["Light 'Em Up",'Forest'])
    token=next(iter(counter_tokens(Plan(s.state,'p1',cards,None),[bear.id])))
    act(s,'p1',type='cast_spell',card_id=top[0],targets=[target.id],optional_costs=[top[0]+':casualty'],
        cost_choices=[{'component':0,'cards':[token]},{'component':1,'cards':[bear.id]}])
    settle(s)
    assert s.state.cards[bear.id].zone=='p1:graveyard'
    assert not s.state.cards[bear.id].counters
    roundtrip(s)

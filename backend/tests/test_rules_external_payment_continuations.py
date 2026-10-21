"""Special-action and assist tails wait for interruptible mana-source riders."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.payment_rider_injection import inject_mana_draw_rider
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase


@pytest.fixture()
def injected_draw_rider(monkeypatch):
    inject_mana_draw_rider(monkeypatch, {'Payment Test Spring'})


@pytest.fixture()
def cards(settings):
    base={c['name']:c for c in fixture_cards()}
    raw=json.loads((Path(__file__).parent/'fixtures/external_payment_continuations_cards.json').read_text())
    for i,c in enumerate(raw):
        base[c['name']]=card(c['name'],set_code='epc',number=str(i),**{k:v for k,v in c.items() if k!='name'})
    settings.ensure_dirs()
    build_database(base.values(),settings.cards_db_path)
    repo=CardRepository(settings.cards_db_path,ImageStore(settings.images_dir))
    yield repo
    repo.close()


ROOM='Grand Entryway // Elegant Rotunda'


def setup(cards):
    # Only Payment Test Spring is synthetic; its draw rider is explicitly injected below classification.
    names=[c['name'] for c in json.loads((Path(__file__).parent/'fixtures/external_payment_continuations_cards.json').read_text())]
    return table(cards,names,names,names)


def mana(s,pid='p1',**amount):
    act(s,pid,type='add_mana',player=pid,mana=amount)


def paused_draw(s,pid='p1',replace_draw=False):
    d=s.state.rules.decision
    assert d is not None and d.player==pid and 'decline' in {o.id for o in d.options}
    roundtrip(s)
    choice=next(o.id for o in d.options if o.id!='decline') if replace_draw else 'decline'
    act(s,pid,type='choose',decision_id=d.id,option_ids=[choice])
    if replace_draw:
        d=s.state.rules.decision
        assert {o.id for o in d.options}=={'land','nonland'}
        roundtrip(s)
        act(s,pid,type='choose',decision_id=d.id,option_ids=['land'])
        d=s.state.rules.decision
        if d is not None and d.kind=='order':
            roundtrip(s)
            act(s,pid,type='choose',decision_id=d.id,option_ids=[o.id for o in d.options])
    settle(s)


@pytest.mark.parametrize('paused',[False,'decline','replace'])
def test_room_unlock_terminal_runs_once_after_mana_rider(cards,paused,injected_draw_rider):
    s=setup(cards)
    room=put(s,ROOM,'battlefield')
    if paused:
        spring=put(s,'Payment Test Spring','battlefield')
        put(s,'Abundance','battlefield')
        mana(s,C=1)
    else:
        mana(s,C=1,W=1)
    act(s,'p1',type='unlock_door',card_id=room.id,door=1)
    oid=s.state.rules.object_id(room.id)
    if paused:
        assert not s.state.rules.unlocked.get(oid)
        assert s.state.cards[spring.id].tapped
        paused_draw(s,replace_draw=paused=='replace')
    settle(s)
    assert s.state.rules.unlocked[oid]==[1]
    assert len([c for c in s.state.cards.values() if c.name=='Glimmer' and c.zone=='p1:battlefield'])==1
    roundtrip(s)


@pytest.mark.parametrize('paused',[False,'decline','replace'])
def test_licid_end_terminal_waits_for_mana_rider(cards,paused,injected_draw_rider):
    s=setup(cards)
    licid=put(s,'Calming Licid','battlefield')
    host=put(s,'Grizzly Bears','battlefield')
    to_phase(s,'main1',turn=4)
    mana(s,W=1)
    act(s,'p1',type='activate_ability',card_id=licid.id,ability=0,targets=[host.id])
    settle(s)
    assert s.state.cards[licid.id].attached_to==host.id
    if paused:
        spring=put(s,'Payment Test Spring','battlefield')
        put(s,'Abundance','battlefield')
    else:
        mana(s,W=1)
    act(s,'p1',type='end_effect',card_id=licid.id)
    if paused:
        assert s.state.cards[licid.id].attached_to==host.id
        assert s.state.cards[spring.id].tapped
        paused_draw(s,replace_draw=paused=='replace')
    assert Plan(s.state,'p1',s.cards,None).ch(s.state.cards[licid.id]).is_creature
    assert s.state.cards[licid.id].attached_to is None
    assert not [e for e in s.state.rules.effects if e.end_cost]
    roundtrip(s)


@pytest.mark.parametrize('paused',[False,'decline','replace'])
def test_assist_helper_payment_resumes_caster_once(cards,paused,injected_draw_rider):
    s=setup(cards)
    spell=put(s,'Huddle Up','hand')
    mana(s,U=1,C=1)
    if paused:
        spring=put(s,'Payment Test Spring','battlefield',pid='p2')
        put(s,'Abundance','battlefield',pid='p2')
    else:
        mana(s,'p2',C=1)
    before={p:len(s.state.zones[p+':hand']) for p in ['p1','p2','p3']}
    act(s,'p1',type='cast_spell',card_id=spell.id,targets=['p1','p3'],target_counts=[2],assist='p2',assist_amount=1)
    if paused:
        assert s.state.cards[spring.id].tapped
        assert len(s.state.zones['p3:hand'])==before['p3']
        paused_draw(s,'p2',replace_draw=paused=='replace')
    settle(s)
    assert s.state.cards[spell.id].zone=='p1:graveyard'
    assert len(s.state.zones['p1:hand'])==before['p1']
    assert len(s.state.zones['p3:hand'])==before['p3']+1
    assert len(s.state.zones['p2:hand'])==before['p2']+int(bool(paused))
    roundtrip(s)

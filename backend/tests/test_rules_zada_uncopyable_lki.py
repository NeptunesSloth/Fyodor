"""Zada obeys a spell's copy prohibition, including last-known stack text."""
import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_bandmate_references import wait_priority
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table


@pytest.fixture()
def cards(settings):
    base={c['name']:c for c in fixture_cards()}
    for filename in ['spell_copy_replacement_cards.json','see_double_cards.json','nalfeshnee_cards.json']:
        for i,c in enumerate(json.loads((Path(__file__).parent/'fixtures'/filename).read_text())):
            base[c['name']]=card(c['name'],set_code=filename[:3],number=str(i),**{k:v for k,v in c.items() if k!='name'})
    settings.ensure_dirs()
    build_database(base.values(),settings.cards_db_path)
    repo=CardRepository(settings.cards_db_path,ImageStore(settings.images_dir))
    yield repo
    repo.close()

@pytest.mark.parametrize('countered',[False,True])
def test_zada_cannot_copy_see_double(cards,countered):
    s=table(cards,['Zada, Hedron Grinder','Grizzly Bears','See Double'],['Counterspell'],[])
    for p in ('p1','p2','p3'):
        act(s,p,type='set_prefs',hold_priority=True)
    zada=put(s,'Zada, Hedron Grinder','battlefield')
    put(s,'Grizzly Bears','battlefield')
    original=put(s,'See Double','hand')
    act(s,'p1',type='add_mana',player='p1',mana={'C':2,'U':2})
    act(s,'p1',type='cast_spell',card_id=original.id,modes=[1],targets=[zada.id])
    if countered:
        wait_priority(s,'p2')
        counter=put(s,'Counterspell','hand',pid='p2')
        act(s,'p2',type='add_mana',player='p2',mana={'U':2})
        act(s,'p2',type='cast_spell',card_id=counter.id,targets=[original.id])
    roundtrip(s)
    settle(s)
    if not countered:
        decision=s.state.rules.decision
        assert decision is not None and decision.resume['step']=='legend_rule'
        roundtrip(s)
        act(s,decision.player,type='choose',decision_id=decision.id,option_ids=[zada.id])
        settle(s)
    assert s.state.rules.decision is None
    assert not [c for c in s.state.cards.values() if c.is_token and c.name=='Grizzly Bears']
    roundtrip(s)

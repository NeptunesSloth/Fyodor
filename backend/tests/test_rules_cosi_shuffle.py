"""Private library inspection preserves owner, viewer and chooser across native continuations."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.state import GameState
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana, wait_priority
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_shared_damage_choices import table


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    data = json.loads((Path(__file__).parent / 'fixtures/cosi_shuffle_cards.json').read_text())
    for i, c in enumerate(data):
        base[c['name']] = card(c['name'], set_code='sec', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


COSI = "Cosi's Trickster"


def settle(s):
    for _ in range(60):
        d=s.state.rules.decision
        if d is not None:
            if d.kind == 'order' and d.resume.get('step') != 'order_library':
                act(s,d.player,type='choose',decision_id=d.id,option_ids=[o.id for o in d.options])
            else:
                return
        elif s.state.zones.get('stack'):
            act(s,s.state.rules.priority,type='pass_priority')
        else:
            return


def answer(s, ids):
    d = s.state.rules.decision
    assert d is not None
    roundtrip(s)
    s.state = GameState.model_validate(s.state.model_dump(mode='json'))
    act(s, d.player, type='choose', decision_id=d.id, option_ids=ids)
    settle(s)



def test_canonical_full(cards):
    assert coverage.of_card_data(cards.resolve(COSI)).level == 'FULL'


@pytest.mark.parametrize('accept',[True,False])
def test_opponent_native_shuffle_optional_counter(cards,accept):
    s=table(cards,[COSI],["Feldon's Cane"],[])
    source=put(s,COSI,'battlefield')
    cane=put(s,"Feldon's Cane",'battlefield',pid='p2')
    wait_priority(s,'p2')
    act(s,'p2',type='activate_ability',card_id=cane.id,ability=0)
    settle(s)
    d=s.state.rules.decision
    assert d is not None and d.player=='p1' and d.kind=='confirm'
    answer(s,['yes' if accept else 'no'])
    assert s.state.cards[source.id].counters.get('+1/+1',0)==int(accept)
    assert s.state.rules.decision is None
    roundtrip(s)


def test_own_native_shuffle_does_not_trigger(cards):
    s=table(cards,[COSI,"Feldon's Cane"],[],[])
    source=put(s,COSI,'battlefield')
    cane=put(s,"Feldon's Cane",'battlefield')
    act(s,'p1',type='activate_ability',card_id=cane.id,ability=0)
    settle(s)
    assert s.state.rules.decision is None
    assert not s.state.cards[source.id].counters
    roundtrip(s)


def test_each_opponent_shuffle_triggers_independently(cards):
    s=table(cards,[COSI],["Feldon's Cane"],["Feldon's Cane"])
    source=put(s,COSI,'battlefield')
    for pid in ['p2','p3']:
        cane=put(s,"Feldon's Cane",'battlefield',pid=pid)
        wait_priority(s,pid)
        act(s,pid,type='activate_ability',card_id=cane.id,ability=0)
        settle(s)
        answer(s,['yes'])
    assert s.state.cards[source.id].counters['+1/+1']==2
    roundtrip(s)


def test_source_control_determines_opponents_not_owner(cards):
    s=table(cards,[COSI,"Feldon's Cane"],[],[])
    source=put(s,COSI,'battlefield')
    act(s,'p1',type='set_controller',card_ids=[source.id],player='p2')
    cane=put(s,"Feldon's Cane",'battlefield')
    act(s,'p1',type='activate_ability',card_id=cane.id,ability=0)
    settle(s)
    assert s.state.rules.decision.player=='p2'
    answer(s,['yes'])
    assert s.state.cards[source.id].counters['+1/+1']==1
    roundtrip(s)


def test_trigger_does_not_put_counter_on_departed_source(cards):
    s=table(cards,[COSI],["Feldon's Cane"],['Lightning Bolt'])
    source=put(s,COSI,'battlefield')
    cane=put(s,"Feldon's Cane",'battlefield',pid='p2')
    wait_priority(s,'p2')
    act(s,'p2',type='activate_ability',card_id=cane.id,ability=0)
    for _ in range(20):
        if any(c.ability is not None and c.ability.source_id==source.id for c in s.state.cards.values() if c.zone=='stack'):
            break
        act(s,s.state.rules.priority,type='pass_priority')
    else:
        pytest.fail('Cosi trigger did not reach stack')
    wait_priority(s,'p3')
    bolt=put(s,'Lightning Bolt','hand',pid='p3')
    mana(s,pid='p3',R=1)
    act(s,'p3',type='cast_spell',card_id=bolt.id,targets=[source.id])
    settle(s)
    assert s.state.cards[source.id].zone=='p1:graveyard'
    if s.state.rules.decision is not None:
        answer(s,['yes'])
    assert not s.state.cards[source.id].counters
    assert s.state.rules.decision is None
    roundtrip(s)

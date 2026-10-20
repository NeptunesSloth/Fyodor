"""Actual LKI, declined costs, and exhausted reveal-through outcomes."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_designations import pick, put, roundtrip, settle
from tests.test_rules_reveal_consequences import DATA, attack, cast, mana
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave6c_tokens_pumps import chars
from tests.test_rules_wave30m_durations import to_phase


@pytest.fixture()
def cards(settings):
    base={c['name']:c for c in fixture_cards()}
    extra=json.loads((Path(__file__).parent/'fixtures/reveal_consequences_edges_cards.json').read_text())
    for i,c in enumerate([*DATA,*extra]):
        base[c['name']]=card(c['name'],set_code='rce',number=str(i),**{k:v for k,v in c.items() if k!='name'})
    settings.ensure_dirs()
    build_database(base.values(),settings.cards_db_path)
    repo=CardRepository(settings.cards_db_path,ImageStore(settings.images_dir))
    yield repo
    repo.close()


def clear_library(s,pid='p1'):
    ids=list(s.state.zones[f'{pid}:library'])
    if ids:
        act(s,pid,type='move',card_ids=ids,to={'player':pid,'zone':'graveyard'})


def test_heirloom_uses_all_creature_types_granted_before_actual_death(cards):
    s=table(cards,['Heirloom Blade','Grizzly Bears','Wings of Velis Vel','Llanowar Elves','Sol Ring'],['Murder'])
    blade=put(s,'Heirloom Blade','battlefield')
    bear=put(s,'Grizzly Bears','battlefield')
    mana(s)
    act(s,'p1',type='activate_ability',card_id=blade.id,ability=2,targets=[bear.id])
    settle(s)
    clear_library(s)
    found=put(s,'Llanowar Elves','library')
    ring=put(s,'Sol Ring','library')
    cast(s,'Wings of Velis Vel',[bear.id])
    assert 'Elf' in chars(s,s.state.cards[bear.id]).subtypes
    cast(s,'Murder',[bear.id],'p2')
    pick(s,['yes'])
    settle(s)
    assert s.state.cards[found.id].zone=='p1:hand'
    assert s.state.cards[ring.id].zone=='p1:library'
    assert not s.state.cards[ring.id].revealed_to
    assert not s.state.cards[found.id].revealed_to
    roundtrip(s)


def revealed_since(s,index):
    def visit(value):
        if isinstance(value,dict):
            return value.get('type')=='reveal' or any(visit(v) for v in value.values())
        if isinstance(value,list):
            return any(visit(v) for v in value)
        return False
    return any(visit(a.model_dump(mode='json')) for a in s.history.actions[index:])


@pytest.mark.parametrize('barred',[False,True])
def test_fury_declined_or_sacrifice_barred_never_reveals(cards,barred):
    s=table(cards,["Descendants' Fury",'Grizzly Bears','Runeclaw Bear','Fervor','Assault Suit'])
    put(s,"Descendants' Fury",'battlefield')
    found=put(s,'Runeclaw Bear','library')
    bear=attack(s,'Grizzly Bears')
    if barred:
        suit=put(s,'Assault Suit','battlefield')
        act(s,'p1',type='attach',card_ids=[suit.id],to=bear.id)
    before=len(s.history.actions)
    to_phase(s,'combat_damage')
    settle(s)
    if s.state.rules.decision:
        d=s.state.rules.decision
        if barred:
            assert bear.id not in {o.id for o in d.options}
        pick(s,[])
        settle(s)
    assert s.state.cards[bear.id].zone=='p1:battlefield'
    assert s.state.cards[found.id].zone=='p1:library'
    assert not revealed_since(s,before)
    roundtrip(s)


@pytest.mark.parametrize('empty',[False,True])
def test_amplifire_no_creature_reveal_gives_zero_base_toughness_and_dies(cards,empty):
    s=table(cards,['Amplifire','Sol Ring','Forest'])
    source=put(s,'Amplifire','battlefield')
    to_phase(s,'upkeep',turn=4)
    clear_library(s)
    shown=[] if empty else [put(s,'Sol Ring','library'),put(s,'Forest','library')]
    settle(s)
    assert s.state.cards[source.id].zone=='p1:graveyard'
    assert all(s.state.cards[c.id].zone=='p1:library' and not s.state.cards[c.id].revealed_to for c in shown)
    assert s.state.rules.decision is None
    roundtrip(s)

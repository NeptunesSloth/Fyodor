"""Original cast targets, native stack copies, and once loyalty-copy watches."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_bandmate_references import wait_priority
from tests.test_rules_designations import pick, roundtrip
from tests.test_rules_library_placements import settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

DATA = json.loads((Path(__file__).parent / 'fixtures/stack_events102_cards.json').read_text()) + json.loads((Path(__file__).parent / 'fixtures/copy_controllers105_cards.json').read_text())
NAMES = ['Tempt with Mayhem','Meletis Charlatan','Psychic Rebuttal']

@pytest.fixture
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(DATA):
        base[c['name']] = card(c['name'], set_code='s102', number=str(i), **{k: v for k, v in c.items() if k not in ('name', 'set_code', 'number')})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards):
    ns = [c['name'] for c in DATA if c['name'] not in ('Krenko, Mob Boss', "Atraxa, Praetors' Voice")]
    ns += ['Grizzly Bears', 'Grizzly Bears', 'Murder']
    s = table(cards, ns, ns, ns)
    to_phase(s, 'main1', 1)
    return s


def put(s, name, zone='battlefield', pid='p1'):
    found = [c for c in s.state.cards.values() if c.owner == pid and c.name == name]
    c = next((c for c in found if c.zone != f'{pid}:{zone}'), found[0])
    act(s, pid, type='move', card_ids=[c.id], to={'player': pid, 'zone': zone})
    return s.state.cards[c.id]


def cast(s, name, targets=(), pid='p1', **extra):
    found = [c for c in s.state.cards.values() if c.owner == pid and c.name == name and not c.zone.endswith((':battlefield', ':graveyard'))]
    c = next((c for c in found if c.zone == f'{pid}:hand'), found[0])
    act(s, pid, type='move', card_ids=[c.id], to={'player': pid, 'zone': 'hand'})
    wait_priority(s, pid)
    act(s, pid, type='add_mana', player=pid, mana={c: 20 for c in ['C','W','U','B','R','G']})
    act(s, pid, type='cast_spell', card_id=c.id, sources=[], targets=list(targets), **extra)
    return c


def finish(s, prefer=()):
    for _ in range(60):
        settle(s)
        d = s.state.rules.decision
        if d is None:
            return
        ids = [o.id for o in d.options]
        wanted = [x for x in [*prefer, 'yes', 'copy', 'keep'] if x in ids]
        pick(s, wanted[:1] if wanted else ids[:max(1,d.min_choices)])
    raise AssertionError('did not finish')


def pt(s, card):
    return Plan.view(s.state, 'p1', s.cards).ch(s.state.cards[card.id]).pt


@pytest.mark.parametrize('name',NAMES)
def test_whole105(cards,name):
    assert coverage.of_card_data(cards.resolve(name)).level=='FULL'


@pytest.mark.parametrize('accept',[False,True])
def test_tempt_each_copy_controller_and_actual_totals(cards,accept):
    s=setup(cards)
    to_phase(s,'main1',2)
    original=cast(s,'Divination',pid='p2')
    cast(s,'Tempt with Mayhem',[original.id])
    before={p:len(s.state.zones[p+':hand']) for p in ['p1','p2','p3']}
    finish(s,prefer=['yes' if accept else 'no'])
    expected={'p1':6 if accept else 2,'p2':4 if accept else 2,'p3':2 if accept else 0}
    assert all(len(s.state.zones[p+':hand'])==n+expected[p] for p,n in before.items()), {p:len(s.state.zones[p+':hand'])-n for p,n in before.items()}
    roundtrip(s)


def test_tempt_next_opponent_sees_previous_copy_on_stack(cards):
    from tests.test_rules_copy import copies
    s=setup(cards)
    to_phase(s,'main1',2)
    original=cast(s,'Divination',pid='p2')
    cast(s,'Tempt with Mayhem',[original.id])
    settle(s)
    assert s.state.rules.decision.player=='p2'
    pick(s,['yes'])
    settle(s)
    assert s.state.rules.decision.player=='p3'
    assert len(copies(s))==1 and s.state.cards[copies(s)[0]].controller=='p2'
    pick(s,['no'])
    finish(s)
    roundtrip(s)


def test_charlatan_original_controller_draws_and_pays_once(cards):
    s=setup(cards)
    source=put(s,'Meletis Charlatan')
    to_phase(s,'main1',5)
    original=cast(s,'Divination',pid='p2')
    wait_priority(s,'p1')
    act(s,'p1',type='add_mana',player='p1',mana={'U':1,'C':2})
    before={p:len(s.state.zones[p+':hand']) for p in ['p1','p2','p3']}
    act(s,'p1',type='activate_ability',card_id=source.id,ability=0,sources=[],targets=[original.id])
    finish(s)
    assert s.state.cards[source.id].tapped
    assert len(s.state.zones['p2:hand'])==before['p2']+4
    assert len(s.state.zones['p1:hand'])==before['p1']
    roundtrip(s)


@pytest.mark.parametrize('mastery',[False,True])
def test_rebuttal_only_actual_countered_and_mastery(cards,mastery):
    s=setup(cards)
    if mastery:
        put(s,'Lightning Bolt','graveyard')
        put(s,'Counterspell','graveyard')
    original=cast(s,'Lightning Bolt',['p1'],pid='p2')
    cast(s,'Psychic Rebuttal',[original.id])
    finish(s)
    assert s.state.players['p1'].life==(37 if mastery else 40)
    assert s.state.cards[original.id].zone=='p2:graveyard'
    roundtrip(s)


def test_rebuttal_does_not_copy_uncounterable_spell(cards):
    s=setup(cards)
    put(s,'Lightning Bolt','graveyard')
    put(s,'Counterspell','graveyard')
    original=cast(s,"Urza's Rage",['p1'],pid='p2')
    cast(s,'Psychic Rebuttal',[original.id])
    finish(s)
    assert s.state.players['p1'].life==37
    assert s.state.cards[original.id].zone=='p2:graveyard'
    roundtrip(s)


def test_tempt_native_copy_replacement_applies_once_to_whole_final_batch(cards):
    s=setup(cards)
    put(s,'Twinning Staff')
    to_phase(s,'main1',2)
    original=cast(s,'Divination',pid='p2')
    cast(s,'Tempt with Mayhem',[original.id])
    before=len(s.state.zones['p1:hand'])
    finish(s)
    assert len(s.state.zones['p1:hand'])==before+8
    roundtrip(s)


def test_rebuttal_may_decline_after_actual_counter(cards):
    s=setup(cards)
    put(s,'Lightning Bolt','graveyard')
    put(s,'Counterspell','graveyard')
    original=cast(s,'Lightning Bolt',['p1'],pid='p2')
    cast(s,'Psychic Rebuttal',[original.id])
    finish(s,prefer=['no'])
    assert s.state.players['p1'].life==40
    roundtrip(s)


def test_cold_tempt_previous_actual_copy_outcome_and_next_opponent(cards,tmp_path):
    from tests.test_rules_stack_events102 import cold
    s=setup(cards)
    to_phase(s,'main1',2)
    original=cast(s,'Divination',pid='p2')
    cast(s,'Tempt with Mayhem',[original.id])
    settle(s)
    pick(s,['yes'])
    settle(s)
    assert s.state.rules.decision.player=='p3'
    cold(s,tmp_path,"before={p:len(s.state.zones[p+':hand']) for p in ['p1','p2','p3']}; finish(s); assert all(len(s.state.zones[p+':hand'])==before[p]+n for p,n in {'p1':6,'p2':4,'p3':2}.items())")


def test_cold_rebuttal_after_counter_before_optional_copy(cards,tmp_path):
    from tests.test_rules_stack_events102 import cold
    s=setup(cards)
    put(s,'Lightning Bolt','graveyard')
    put(s,'Counterspell','graveyard')
    original=cast(s,'Lightning Bolt',['p1'],pid='p2')
    cast(s,'Psychic Rebuttal',[original.id])
    settle(s)
    assert s.state.cards[original.id].zone=='p2:graveyard'
    assert s.state.rules.decision is not None
    cold(s,tmp_path,"finish(s); assert s.state.players['p1'].life==37")


def test_tempt_accepted_offer_cannot_override_cannot_be_copied(cards):
    s=setup(cards)
    act(s,'p2',type='set_prefs',hold_priority=True)
    original=cast(s,'Lightning Bolt',['p1'],pid='p2')
    forbidden=cast(s,'Display of Power',[original.id],pid='p2',target_counts=[1])
    cast(s,'Tempt with Mayhem',[forbidden.id])
    finish(s)
    assert s.state.players['p1'].life==34
    assert s.state.rules.decision is None
    roundtrip(s)

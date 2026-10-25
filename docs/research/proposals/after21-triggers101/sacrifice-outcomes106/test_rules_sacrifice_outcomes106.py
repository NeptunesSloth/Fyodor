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

DATA = json.loads((Path(__file__).parent / 'fixtures/stack_events102_cards.json').read_text()) + json.loads((Path(__file__).parent / 'fixtures/sacrifice_outcomes106_cards.json').read_text())
NAMES = ['Tevesh Szat, Doom of Fools','Eddie Brock // Venom, Lethal Protector','Saw',"Nahiri's Lithoforming",'Hew the Entwood']

@pytest.fixture
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(DATA):
        fields = {k: v for k, v in c.items() if k not in ('name', 'set_code', 'number')}
        if c.get('faces'):
            fields['card_faces'] = c['faces']
        base[c['name']] = card(c['name'], set_code='s106', number=str(i), **fields)
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
def test_whole106(cards,name):
    assert coverage.of_card_data(cards.resolve(name)).level=='FULL'


def activate(s,source,index,targets=()):
    wait_priority(s,'p1')
    act(s,'p1',type='add_mana',player='p1',mana={c:20 for c in ['C','W','U','B','R','G']})
    act(s,'p1',type='activate_ability',card_id=source.id,ability=index,sources=[],targets=list(targets))


@pytest.mark.parametrize('commander',[False,True])
def test_tevesh_actual_optional_sacrifice_and_commander_lki(cards,commander):
    s=setup(cards)
    source=cast(s,'Tevesh Szat, Doom of Fools')
    finish(s)
    victim=put(s,'Krenko, Mob Boss' if commander else 'Grizzly Bears')
    activate(s,source,1)
    before=len(s.state.zones['p1:hand'])
    finish(s,prefer=[victim.id])
    assert len(s.state.zones['p1:hand'])==before+(3 if commander else 2)
    assert s.state.cards[source.id].counters['loyalty']==5
    assert not s.state.cards[victim.id].zone.endswith(':battlefield')
    roundtrip(s)


def test_tevesh_commander_draw_instructions_stay_separate_under_alms_collector(cards):
    s=setup(cards)
    source=cast(s,'Tevesh Szat, Doom of Fools')
    finish(s)
    victim=put(s,'Krenko, Mob Boss')
    put(s,'Alms Collector',pid='p2')
    activate(s,source,1)
    before={p:len(s.state.zones[p+':hand']) for p in ['p1','p2']}
    finish(s,prefer=[victim.id])
    assert len(s.state.zones['p1:hand'])==before['p1']+2
    assert len(s.state.zones['p2:hand'])==before['p2']+1
    roundtrip(s)


def test_tevesh_decline_and_forbidden_sacrifice_draw_nothing(cards):
    s=setup(cards)
    source=cast(s,'Tevesh Szat, Doom of Fools')
    finish(s)
    activate(s,source,1)
    before=len(s.state.zones['p1:hand'])
    finish(s)
    assert len(s.state.zones['p1:hand'])==before
    roundtrip(s)


def test_nahiri_actual_count_but_announced_x_land_permissions(cards):
    from app.rules import land_plays
    s=setup(cards)
    land=put(s,'Forest')
    cast(s,"Nahiri's Lithoforming",x_value=3)
    before=len(s.state.zones['p1:hand'])
    finish(s)
    assert len(s.state.zones['p1:hand'])==before+1
    assert s.state.cards[land.id].zone=='p1:graveyard'
    assert land_plays.one_shot(s.state,'p1')==3
    hand=put(s,'Forest','hand')
    wait_priority(s,'p1')
    act(s,'p1',type='play_land',card_id=hand.id)
    assert s.state.cards[hand.id].tapped
    roundtrip(s)


def test_nahiri_sacrifice_replaced_to_exile_still_draws(cards):
    s=setup(cards)
    put(s,'Rest in Peace')
    land=put(s,'Forest')
    cast(s,"Nahiri's Lithoforming",x_value=1)
    before=len(s.state.zones['p1:hand'])
    finish(s)
    assert len(s.state.zones['p1:hand'])==before+1
    assert s.state.cards[land.id].zone=='p1:exile'
    roundtrip(s)


def test_venom_real_transform_and_attack_sacrifice_mv_then_put_permanent(cards):
    from tests.test_rules_wave30p_combat import attack
    s=setup(cards)
    source=cast(s,'Eddie Brock // Venom, Lethal Protector')
    finish(s)
    activate(s,source,1)
    finish(s)
    victim=put(s,'Grizzly Bears')
    prize=next(c for c in s.state.cards.values() if c.owner=='p1' and c.name=='Grizzly Bears' and c.id!=victim.id)
    act(s,'p1',type='move',card_ids=[prize.id],to={'player':'p1','zone':'hand'})
    to_phase(s,'declare_attackers',1)
    attack(s,(source,'p2'))
    settle(s)
    before=len(s.state.zones['p1:hand'])
    finish(s,prefer=[victim.id,prize.id])
    assert s.state.cards[victim.id].zone=='p1:graveyard'
    assert s.state.cards[prize.id].zone=='p1:battlefield'
    assert len(s.state.zones['p1:hand'])==before+1
    roundtrip(s)


def test_saw_actual_equipping_attack_excludes_attacker_and_equipment(cards):
    from tests.test_rules_wave30p_combat import attack
    s=setup(cards)
    source=cast(s,'Saw')
    finish(s)
    attacker=put(s,'Grizzly Bears')
    victim=put(s,'Grizzly Bears')
    to_phase(s,'main1',4)
    activate(s,source,2,[attacker.id])
    finish(s)
    to_phase(s,'declare_attackers',4)
    attack(s,(attacker,'p2'))
    settle(s)
    d=s.state.rules.decision
    assert d is not None
    assert {source.id,attacker.id}.isdisjoint(o.card_id for o in d.options)
    before=len(s.state.zones['p1:hand'])
    finish(s,prefer=[victim.id])
    assert s.state.cards[victim.id].zone=='p1:graveyard'
    assert len(s.state.zones['p1:hand'])==before+1
    roundtrip(s)


def test_hew_nonlands_enter_before_tapped_lands_and_zero_is_allowed(cards):
    s=setup(cards)
    first=put(s,'Forest')
    second=put(s,'Forest')
    rover=put(s,'Hedron Rover','hand')
    land=next(c for c in s.state.cards.values() if c.owner=='p1' and c.name=='Forest' and c.id not in (first.id,second.id))
    act(s,'p1',type='move',card_ids=[land.id],to={'player':'p1','zone':'library'},position='top')
    act(s,'p1',type='move',card_ids=[rover.id],to={'player':'p1','zone':'library'},position='top')
    cast(s,'Hew the Entwood')
    settle(s)
    pick(s,[first.id,second.id])
    settle(s)
    d=s.state.rules.decision
    assert d is not None
    chosen=[o.id for o in d.options]
    assert len(chosen)==2
    pick(s,chosen)
    finish(s)
    actual=next(c for c in s.state.cards.values() if c.name=='Hedron Rover' and c.zone=='p1:battlefield')
    assert pt(s,actual)==(4,4)
    assert any(c.name=='Forest' and c.zone=='p1:battlefield' and c.tapped for c in s.state.cards.values())
    roundtrip(s)


def test_tevesh_ultimate_native_minus_ten_source_dies_before_control_and_command_entry(cards):
    s=setup(cards)
    source=cast(s,'Tevesh Szat, Doom of Fools')
    finish(s)
    old=put(s,"Atraxa, Praetors' Voice",pid='p2')
    act(s,'p1',type='counter',card_ids=[source.id],kind='loyalty',delta=6)
    activate(s,source,2)
    finish(s,prefer=[old.id])
    assert s.state.cards[source.id].zone=='p1:graveyard'
    assert s.state.cards[old.id].zone=='p1:battlefield' and s.state.cards[old.id].controller=='p1'
    commander=next(c for c in s.state.cards.values() if c.owner=='p1' and c.name=='Krenko, Mob Boss')
    assert commander.zone=='p1:battlefield'
    roundtrip(s)


def test_tevesh_sacrifice_forbidden_by_actual_assault_suit(cards):
    s=setup(cards)
    source=cast(s,'Tevesh Szat, Doom of Fools')
    finish(s)
    suit=cast(s,'Assault Suit')
    finish(s)
    victim=put(s,'Grizzly Bears')
    activate(s,suit,2,[victim.id])
    finish(s)
    activate(s,source,1)
    before=len(s.state.zones['p1:hand'])
    finish(s)
    assert len(s.state.zones['p1:hand'])==before
    assert s.state.cards[victim.id].zone=='p1:battlefield'
    roundtrip(s)


def test_tevesh_can_decline_even_with_eligible_creature(cards):
    s=setup(cards)
    source=cast(s,'Tevesh Szat, Doom of Fools')
    finish(s)
    victim=put(s,'Grizzly Bears')
    activate(s,source,1)
    settle(s)
    before=len(s.state.zones['p1:hand'])
    pick(s,[])
    finish(s)
    assert len(s.state.zones['p1:hand'])==before
    assert s.state.cards[victim.id].zone=='p1:battlefield'
    roundtrip(s)


def test_hew_may_sacrifice_zero(cards):
    s=setup(cards)
    land=put(s,'Forest')
    cast(s,'Hew the Entwood')
    settle(s)
    before=len(s.state.zones['p1:library'])
    pick(s,[])
    finish(s)
    assert s.state.cards[land.id].zone=='p1:battlefield'
    assert len(s.state.zones['p1:library'])==before
    roundtrip(s)


def test_cold_tevesh_commander_offer_retains_native_lki_bonus(cards,tmp_path):
    from tests.test_rules_stack_events102 import cold
    s=setup(cards)
    source=cast(s,'Tevesh Szat, Doom of Fools')
    finish(s)
    put(s,'Krenko, Mob Boss')
    activate(s,source,1)
    settle(s)
    cold(s,tmp_path,"before=len(s.state.zones['p1:hand']); finish(s); assert len(s.state.zones['p1:hand'])==before+3")


def test_cold_nahiri_land_permission_and_entry_tapped_expire(cards,tmp_path):
    from tests.test_rules_stack_events102 import cold
    s=setup(cards)
    put(s,'Forest')
    cast(s,"Nahiri's Lithoforming",x_value=2)
    finish(s)
    cold(s,tmp_path,"""from app.rules import land_plays
assert land_plays.one_shot(s.state,'p1')==2
land=next(c for c in s.state.cards.values() if c.owner=='p1' and c.name=='Forest' and c.zone!='p1:battlefield')
act(s,'p1',type='move',card_ids=[land.id],to={'player':'p1','zone':'hand'})
wait_priority(s,'p1'); act(s,'p1',type='play_land',card_id=land.id); assert s.state.cards[land.id].tapped
to_phase(s,'main1',4); assert land_plays.one_shot(s.state,'p1')==0
land=next(c for c in s.state.cards.values() if c.owner=='p1' and c.name=='Forest' and c.zone!='p1:battlefield')
act(s,'p1',type='move',card_ids=[land.id],to={'player':'p1','zone':'hand'})
wait_priority(s,'p1'); act(s,'p1',type='play_land',card_id=land.id); assert not s.state.cards[land.id].tapped
""")


def test_cold_hew_selected_library_objects_enter_in_two_phases(cards,tmp_path):
    from tests.test_rules_stack_events102 import cold
    s=setup(cards)
    first=put(s,'Forest')
    second=put(s,'Forest')
    rover=put(s,'Hedron Rover','hand')
    land=next(c for c in s.state.cards.values() if c.owner=='p1' and c.name=='Forest' and c.id not in (first.id,second.id))
    act(s,'p1',type='move',card_ids=[land.id],to={'player':'p1','zone':'library'},position='top')
    act(s,'p1',type='move',card_ids=[rover.id],to={'player':'p1','zone':'library'},position='top')
    cast(s,'Hew the Entwood')
    settle(s)
    pick(s,[first.id,second.id])
    settle(s)
    cold(s,tmp_path,"pick(s,[o.id for o in s.state.rules.decision.options]); finish(s); rover=next(c for c in s.state.cards.values() if c.name=='Hedron Rover' and c.zone=='p1:battlefield'); assert pt(s,rover)==(4,4); assert any(c.name=='Forest' and c.zone=='p1:battlefield' and c.tapped for c in s.state.cards.values())")

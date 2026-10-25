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

OLD_DATA = json.loads((Path(__file__).parent / 'fixtures/stack_events102_cards.json').read_text())
DATA = OLD_DATA + json.loads((Path(__file__).parent / 'fixtures/stack_extension103_cards.json').read_text())
NAMES = [c['name'] for c in DATA if c['name'] in ('Precursor Golem','Ink-Treader Nephilim','Bill Potts','Flamehold Grappler','Ancestral Communion','Social Snub','Banish into Fable')]


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


def test_initial_only_social(cards):
    s = setup(cards)
    bear = put(s, 'Grizzly Bears')
    cast(s, 'Social Snub')
    cast(s,'Murder',[bear.id],pid='p2')
    life = s.state.players['p2'].life
    finish(s)
    assert s.state.players['p2'].life == life - 2
    roundtrip(s)


def test_no_initial_social(cards):
    s = setup(cards)
    cast(s, 'Social Snub')
    put(s, 'Grizzly Bears')
    life = s.state.players['p2'].life
    finish(s)
    assert s.state.players['p2'].life == life - 1
    roundtrip(s)


def test_grappler_next_once(cards):
    s = setup(cards)
    cast(s, 'Flamehold Grappler')
    finish(s)
    cast(s, 'Divination')
    before = len(s.state.zones['p1:hand'])
    finish(s)
    assert len(s.state.zones['p1:hand']) == before + 4
    roundtrip(s)


@pytest.mark.parametrize('name', NAMES)
def test_whole103(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


def test_precursor_all_players_golems(cards):
    s = setup(cards)
    golem = cast(s, 'Precursor Golem')
    finish(s)
    others = [c for c in s.state.cards.values() if c.controller == 'p1' and c.is_token and 'Golem' in Plan.view(s.state, 'p1', s.cards).ch(c).subtypes]
    assert len(others) == 2
    cast(s, 'Giant Growth', [golem.id])
    finish(s)
    assert pt(s, golem) == (6, 6)
    assert all(pt(s,c) == (6,6) for c in others)
    roundtrip(s)


def test_ink_treader_all_creatures(cards):
    s = setup(cards)
    ink = put(s, 'Ink-Treader Nephilim')
    b1 = put(s,'Grizzly Bears')
    b2 = put(s,'Grizzly Bears',pid='p2')
    cast(s,'Giant Growth',[ink.id])
    finish(s)
    assert pt(s,ink) == (6,6)
    assert pt(s,b1) == pt(s,b2) == (5,5)
    roundtrip(s)


def test_bill_cast_once(cards):
    s = setup(cards)
    bill = put(s,'Bill Potts')
    cast(s,'Giant Growth',[bill.id])
    finish(s)
    assert pt(s,bill) == (8,10)
    cast(s,'Giant Growth',[bill.id],pid='p2')
    finish(s)
    assert pt(s,bill) == (11,13)
    roundtrip(s)


def test_communion_initial_only(cards):
    s = setup(cards)
    cmd = put(s,'Krenko, Mob Boss')
    bear = put(s,'Grizzly Bears','graveyard')
    other = put(s,'Grizzly Bears','graveyard')
    cast(s,'Ancestral Communion',[bear.id])
    cast(s,'Murder',[cmd.id],pid='p2')
    finish(s,prefer=[other.id])
    assert s.state.cards[bear.id].zone == s.state.cards[other.id].zone == 'p1:hand'
    roundtrip(s)


def test_banish_conditions_at_resolution(cards):
    s = setup(cards)
    bear = put(s,'Grizzly Bears',pid='p2')
    other = put(s,'Grizzly Bears',pid='p3')
    cast(s,'Banish into Fable',[bear.id])
    put(s,'Precursor Golem')
    finish(s,prefer=[other.id])
    assert s.state.cards[bear.id].zone == 'p2:hand'
    assert s.state.cards[other.id].zone == 'p3:hand'
    knights = [c for c in s.state.cards.values() if c.controller == 'p1' and c.is_token and c.name == 'Knight']
    assert len(knights) == 2
    roundtrip(s)


def test_nephilim_original_controller_eligibility_copy_controller_differs(cards):
    s = setup(cards)
    ink = put(s,'Ink-Treader Nephilim')
    own = put(s,'Grizzly Bears')
    caster = put(s,'Grizzly Bears',pid='p2')
    third = put(s,'Grizzly Bears',pid='p3')
    cast(s,'Public Execution',[ink.id],pid='p2')
    finish(s)
    assert s.state.cards[own.id].zone.endswith(':battlefield')
    assert s.state.cards[caster.id].zone.endswith(':battlefield')
    assert s.state.cards[third.id].zone == 'p3:graveyard'
    assert s.state.cards[ink.id].zone == 'p1:graveyard'
    roundtrip(s)


def test_bill_actual_activation_once_shared_with_cast(cards):
    s = setup(cards)
    bill = put(s,'Bill Potts')
    source = put(s,'Prodigal Pyromancer')
    to_phase(s,'main1',4)
    wait_priority(s,'p1')
    act(s,'p1',type='activate_ability',card_id=source.id,ability=0,targets=[bill.id])
    finish(s)
    assert s.state.cards[bill.id].damage == 2
    cast(s,'Giant Growth',[bill.id])
    finish(s)
    assert pt(s,bill) == (5,7)
    roundtrip(s)


def test_cold_next_spell_watch(cards,tmp_path):
    from tests.test_rules_stack_events102 import cold
    s = setup(cards)
    cast(s,'Flamehold Grappler')
    finish(s)
    cold(s,tmp_path,"cast(s,'Divination'); before=len(s.state.zones['p1:hand']); finish(s); assert len(s.state.zones['p1:hand'])==before+4")


def test_cold_initial_social_trigger(cards,tmp_path):
    from tests.test_rules_stack_events102 import cold
    s = setup(cards)
    bear = put(s,'Grizzly Bears')
    cast(s,'Social Snub')
    cast(s,'Murder',[bear.id],pid='p2')
    cold(s,tmp_path,"before=s.state.players['p2'].life; finish(s); assert s.state.players['p2'].life==before-2")


def test_banish_single_artifact_enchantment_copies_twice(cards):
    s = setup(cards)
    put(s,'Bident of Thassa')
    bear = put(s,'Grizzly Bears',pid='p2')
    second = put(s,'Grizzly Bears',pid='p3')
    third = put(s,'Grizzly Bears')
    cast(s,'Banish into Fable',[bear.id])
    from tests.test_rules_copy import copies
    for _ in range(30):
        if len(copies(s)) == 2:
            break
        d = s.state.rules.decision
        if d is not None:
            ids = [o.id for o in d.options]
            choice = next((x for x in [second.id,'yes','copy','keep'] if x in ids), ids[0])
            pick(s,[choice])
        else:
            act(s,s.state.rules.priority,type='pass_priority')
    assert len(copies(s)) == 2
    finish(s,prefer=[second.id,third.id])
    # Both copy instructions run for one artifact enchantment; each resolved
    # target gives a Knight. Choosing the same target twice makes one fizzle.
    assert len([c for c in s.state.cards.values() if c.name=='Knight' and c.is_token]) == 2
    roundtrip(s)


def test_communion_no_commander_at_cast(cards):
    s = setup(cards)
    bear = put(s,'Grizzly Bears','graveyard')
    other = put(s,'Grizzly Bears','graveyard')
    cast(s,'Ancestral Communion',[bear.id])
    put(s,'Krenko, Mob Boss')
    finish(s,prefer=[other.id])
    assert s.state.cards[bear.id].zone=='p1:hand'
    assert s.state.cards[other.id].zone=='p1:graveyard'
    roundtrip(s)


def test_banish_cast_from_graveyard_does_not_trigger(cards):
    s=setup(cards)
    put(s,'Precursor Golem')
    bear=put(s,'Grizzly Bears',pid='p2')
    cast(s,"Yawgmoth's Will")
    finish(s)
    source=put(s,'Banish into Fable','graveyard')
    wait_priority(s,'p1')
    act(s,'p1',type='cast_spell',card_id=source.id,sources=[],targets=[bear.id])
    finish(s)
    assert len([c for c in s.state.cards.values() if c.name=='Knight' and c.is_token])==1
    assert s.state.cards[source.id].zone=='p1:exile'
    roundtrip(s)

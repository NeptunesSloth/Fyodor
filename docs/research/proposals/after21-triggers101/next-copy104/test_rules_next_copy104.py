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

DATA = json.loads((Path(__file__).parent / 'fixtures/stack_events102_cards.json').read_text()) + json.loads((Path(__file__).parent / 'fixtures/next_copy104_cards.json').read_text())
NAMES = ['Tzaangor Shaman','Sea Gate Stormcaller','Repeated Reverberation']

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


@pytest.mark.parametrize('name', NAMES)
def test_whole104(cards,name):
    assert coverage.of_card_data(cards.resolve(name)).level=='FULL'


@pytest.mark.parametrize('kicked',[False,True])
def test_sea_gate_real_kicker_and_nonmatching_spells(cards,kicked):
    s=setup(cards)
    cast(s,'Sea Gate Stormcaller',kicker=1 if kicked else 0)
    finish(s)
    cast(s,'Divination')
    before=len(s.state.zones['p1:hand'])
    finish(s)
    assert len(s.state.zones['p1:hand'])==before+2
    cast(s,'Giant Growth',[next(c.id for c in s.state.cards.values() if c.name=='Sea Gate Stormcaller' and c.zone=='p1:battlefield')])
    finish(s)
    source=next(c for c in s.state.cards.values() if c.name=='Sea Gate Stormcaller' and c.zone=='p1:battlefield')
    assert pt(s,source)==((11,10) if kicked else (8,7))
    roundtrip(s)


def test_repeated_nontarget_draw_three_times(cards):
    s=setup(cards)
    cast(s,'Repeated Reverberation')
    finish(s)
    cast(s,'Divination')
    before=len(s.state.zones['p1:hand'])
    finish(s)
    assert len(s.state.zones['p1:hand'])==before+6
    roundtrip(s)


def test_shaman_actual_combat_installs_copy_watch(cards):
    from tests.test_rules_wave30p_combat import attack
    s=setup(cards)
    shaman=put(s,'Tzaangor Shaman')
    to_phase(s,'declare_attackers',4)
    attack(s,(shaman,'p2'))
    to_phase(s,'main2',4)
    finish(s)
    assert s.state.players['p2'].life==37
    cast(s,'Divination')
    before=len(s.state.zones['p1:hand'])
    finish(s)
    assert len(s.state.zones['p1:hand'])==before+4
    roundtrip(s)


def test_repeated_actual_loyalty_copies_do_not_pay_loyalty(cards):
    s=setup(cards)
    source=cast(s,'Jace Beleren')
    finish(s)
    cast(s,'Repeated Reverberation')
    finish(s)
    before={p:len(s.state.zones[p+':hand']) for p in ['p1','p2','p3']}
    wait_priority(s,'p1')
    act(s,'p1',type='activate_ability',card_id=source.id,ability=0,sources=[])
    finish(s)
    assert s.state.cards[source.id].counters['loyalty']==5
    assert all(len(s.state.zones[p+':hand'])==n+3 for p,n in before.items())
    roundtrip(s)


def test_cold_repeated_preserves_either_watch(cards,tmp_path):
    from tests.test_rules_stack_events102 import cold
    s=setup(cards)
    cast(s,'Repeated Reverberation')
    finish(s)
    cold(s,tmp_path,"cast(s,'Divination'); before=len(s.state.zones['p1:hand']); finish(s); assert len(s.state.zones['p1:hand'])==before+6")


def test_cold_kicked_watch_and_countered_original(cards,tmp_path):
    from tests.test_rules_stack_events102 import cold
    s=setup(cards)
    source=cast(s,'Sea Gate Stormcaller',kicker=1)
    finish(s)
    spell=cast(s,'Giant Growth',[source.id])
    cast(s,'Counterspell',[spell.id],pid='p2')
    cold(s,tmp_path,"finish(s); source=next(c for c in s.state.cards.values() if c.name=='Sea Gate Stormcaller' and c.zone=='p1:battlefield'); assert pt(s,source)==(8,7)")

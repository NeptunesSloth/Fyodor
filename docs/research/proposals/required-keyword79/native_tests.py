"""Real Ian exile producers and Kaya loyalty/emblem authorities keep their native scopes."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import alt_costs, casting, coverage
from app.rules.plan import Plan
from tests import test_rules_exile_cast_outcomes45_foundation as gameplay
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana, wait_priority
from tests.test_rules_controller_tutors import answer
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_look import settle
from tests.test_rules_ordered_tutor_continuations import cast
from tests.test_rules_wave30m_durations import to_phase

DATA = json.loads((Path(__file__).parent / 'fixtures/required_keyword79_cards.json').read_text())
SABIN, UNDERDOG, CULLER, PHOENIX = 'Sabin, Master Monk', 'Tenacious Underdog', 'Timeline Culler', "Detective's Phoenix"
NAMES = [SABIN, UNDERDOG, CULLER, PHOENIX]
DOG = 'Isamaru, Hound of Konda'


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for filename in ['exile_outcomes42_cards.json', 'exile_cast_outcomes45_cards.json',
                     'fight_exile_receipts65_cards.json', 'top_library_authorities69_cards.json',
                     'pooled_casting_authorities71_cards.json']:
        for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures' / filename).read_text())):
            base[c['name']] = card(c['name'], set_code='lc76', number=str(i), **{k: v for k, v in c.items() if k not in {'name', 'set_code'}})
    for i, c in enumerate(DATA):
        base[c['name']] = card(c['name'], set_code='lc76', number='a' + str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards):
    return gameplay.setup(cards, *[c['name'] for c in DATA], 'Lightning Bolt', 'Disperse', 'Counterspell', 'Sol Ring', 'Forest',
                          'Jacob Hauken, Inspector // Hauken\'s Insight')




def key(s, source, tag):
    return next(o.key for o in alt_costs.offers(s.state, 'p1', source, Plan(s.state, 'p1', s.cards, None).ch(source), s.cards) if o.tag == tag)


@pytest.mark.parametrize('name', NAMES)
def test_whole_canonical79(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


@pytest.mark.parametrize('name', NAMES)
def test_own_graveyard_permission_never_allows_an_unselected_ordinary_cast79(cards, name):
    s = setup(cards)
    source = put(s, name, 'graveyard')
    mana(s, C=20, W=20, U=20, B=20, R=20, G=20)
    assert not casting.castable(s.state, 'p1', source, cards)
    before = s.state.model_dump(mode='json')
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=source.id)
    assert s.state.model_dump(mode='json') == before


@pytest.mark.parametrize('name', [SABIN, UNDERDOG])
def test_native_selected_blitz_pays_actual_extra_cost_and_sacrifices_with_draw79(cards, name):
    s = setup(cards)
    source = put(s, name, 'graveyard')
    cost = put(s, 'Giant Growth', 'hand')
    life = s.state.players['p1'].life
    act(s, 'p1', type='clear_mana')
    mana(s, C=2, **({'R': 2} if name == SABIN else {'B': 2}))
    kw = {'cost_choices': [{'component': 0, 'cards': [cost.id]}]} if name == SABIN else {}
    act(s, 'p1', type='cast_spell', card_id=source.id, alt_cost=key(s, source, 'blitz'), **kw)
    settle(s)
    assert s.state.cards[source.id].zone == 'p1:battlefield'
    assert s.state.rules.payments[s.state.rules.object_id(source.id)].alternative == 'blitz'
    assert s.state.players['p1'].life == life - (2 if name == UNDERDOG else 0)
    if name == SABIN:
        assert s.state.cards[cost.id].zone == 'p1:graveyard'
    assert 'haste' in Plan(s.state, 'p1', cards, None).ch(s.state.cards[source.id]).keywords
    before = len(s.state.zones['p1:hand'])
    to_phase(s, 'end', turn=1)
    settle(s)
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    assert len(s.state.zones['p1:hand']) == before + 1
    roundtrip(s)


def test_selected_culler_warp_pays_life_and_retains_native_later_turn_exile_permission79(cards):
    s = setup(cards)
    source = put(s, CULLER, 'graveyard')
    life = s.state.players['p1'].life
    act(s, 'p1', type='clear_mana')
    mana(s, B=1)
    act(s, 'p1', type='cast_spell', card_id=source.id, alt_cost=key(s, source, 'warp'))
    settle(s)
    assert s.state.cards[source.id].zone == 'p1:battlefield' and s.state.players['p1'].life == life - 2
    assert s.state.rules.payments[s.state.rules.object_id(source.id)].alternative == 'warp'
    to_phase(s, 'end', turn=1)
    settle(s)
    assert s.state.cards[source.id].zone == 'p1:exile'
    assert not casting.castable(s.state, 'p1', s.state.cards[source.id], cards)
    to_phase(s, 'main1', turn=4)
    settle(s)
    act(s, 'p1', type='clear_mana')
    mana(s, B=2)
    assert casting.castable(s.state, 'p1', s.state.cards[source.id], cards)
    act(s, 'p1', type='cast_spell', card_id=source.id)
    settle(s)
    assert s.state.cards[source.id].zone == 'p1:battlefield'
    assert s.state.players['p1'].life == life - 2
    to_phase(s, 'end', turn=4)
    settle(s)
    assert s.state.cards[source.id].zone == 'p1:battlefield'
    roundtrip(s)


def test_selected_phoenix_bestow_collects_real_evidence_and_retains_native_unattachment79(cards):
    s = setup(cards)
    source = put(s, PHOENIX, 'graveyard')
    evidence = [put(s, n, 'graveyard') for n in ['Divination', UNDERDOG, 'Giant Growth']]
    host = put(s, 'Grizzly Bears', 'battlefield')
    act(s, 'p1', type='clear_mana')
    mana(s, R=1)
    act(s, 'p1', type='cast_spell', card_id=source.id, alt_cost=key(s, source, 'bestow'), targets=[host.id],
        cost_choices=[{'component': 0, 'cards': [c.id for c in evidence]}])
    settle(s)
    source = s.state.cards[source.id]
    assert source.zone == 'p1:battlefield' and source.attached_to == host.id
    assert all(s.state.cards[c.id].zone == 'p1:exile' for c in evidence)
    assert s.state.rules.payments[s.state.rules.object_id(source.id)].alternative == 'bestow'
    ch = Plan(s.state, 'p1', cards, None).ch(host)
    assert ch.pt == (4, 4) and {'flying', 'haste'} <= ch.keywords
    cast(s, 'Disperse', targets=[host.id])
    ch = Plan(s.state, 'p1', cards, None).ch(s.state.cards[source.id])
    assert ch.is_creature and ch.pt == (2, 2) and not s.state.cards[source.id].attached_to
    roundtrip(s)


def test_bestow_evidence_cannot_exile_the_spell_itself_as_part_of_its_own_cost79(cards):
    s = setup(cards)
    source = put(s, PHOENIX, 'graveyard')
    other = put(s, 'Divination', 'graveyard')
    host = put(s, 'Grizzly Bears', 'battlefield')
    mana(s, R=1)
    before = s.state.model_dump(mode='json')
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=source.id, alt_cost=key(s, source, 'bestow'), targets=[host.id],
            cost_choices=[{'component': 0, 'cards': [source.id, other.id]}])
    assert s.state.model_dump(mode='json') == before


@pytest.mark.parametrize('name', NAMES)
def test_independent_muldrotha_permission_can_still_cast_each_card_normally79(cards, name):
    s = setup(cards)
    cast(s, 'Muldrotha, the Gravetide')
    source = put(s, name, 'graveyard')
    mana(s, C=10, W=10, U=10, B=10, R=10, G=10)
    assert casting.castable(s.state, 'p1', source, cards)
    act(s, 'p1', type='cast_spell', card_id=source.id)
    settle(s)
    if s.state.rules.decision is not None:
        d = s.state.rules.decision
        assert d.resume['step'] == 'slot'
        answer(s, [next(o.id for o in d.options if o.label == 'Creature')])
    source = s.state.cards[source.id]
    assert source.zone == 'p1:battlefield'
    assert s.state.rules.payments[s.state.rules.object_id(source.id)].alternative is None
    assert any(':permission:' in k and k.endswith(':Creature') for k in s.state.rules.once_per_turn)
    roundtrip(s)


@pytest.mark.parametrize('name', [SABIN, UNDERDOG, CULLER])
def test_missing_nonmana_keyword_cost_prevents_the_entire_selected_cast79(cards, name):
    s = setup(cards)
    source = put(s, name, 'graveyard')
    if name == SABIN:
        hand = list(s.state.zones.get('p1:hand', []))
        if hand:
            act(s, 'p1', type='move', card_ids=hand, to={'player': 'p1', 'zone': 'library'})
    else:
        act(s, 'p1', type='set_life', player='p1', value=1)
    mana(s, C=20, R=20, B=20)
    tag = 'warp' if name == CULLER else 'blitz'
    before = s.state.model_dump(mode='json')
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=source.id, alt_cost=key(s, source, tag))
    assert s.state.model_dump(mode='json') == before
    assert not casting.alt_castable(s.state, 'p1', source, cards)


@pytest.mark.parametrize('name', [UNDERDOG, PHOENIX])
def test_own_selected_keyword_authority_does_not_consume_independent_muldrotha_slot79(cards, name):
    s = setup(cards)
    cast(s, 'Muldrotha, the Gravetide')
    source = put(s, name, 'graveyard')
    extra = {}
    if name == PHOENIX:
        evidence = [put(s, n, 'graveyard') for n in ['Divination', SABIN]]
        host = put(s, 'Grizzly Bears', 'battlefield')
        extra = {'targets': [host.id], 'cost_choices': [{'component': 0, 'cards': [c.id for c in evidence]}]}
    mana(s, C=2, R=1, B=2)
    before = {k: v for k, v in s.state.rules.once_per_turn.items() if ':permission:' in k}
    act(s, 'p1', type='cast_spell', card_id=source.id, alt_cost=key(s, source, 'bestow' if name == PHOENIX else 'blitz'), **extra)
    settle(s)
    assert source.zone == 'p1:battlefield'
    assert {k: v for k, v in s.state.rules.once_per_turn.items() if ':permission:' in k} == before
    other = put(s, 'Rivaz of the Claw', 'graveyard')
    mana(s, C=1, B=1, R=1)
    act(s, 'p1', type='cast_spell', card_id=other.id)
    settle(s)
    assert other.zone == 'p1:battlefield'
    roundtrip(s)


@pytest.mark.parametrize('name', NAMES)
def test_unrelated_fist_alternative_cannot_substitute_for_the_required_graveyard_keyword79(cards, name):
    s = setup(cards)
    cast(s, 'Fist of Suns')
    source = put(s, name, 'graveyard')
    mana(s, C=20, W=20, U=20, B=20, R=20, G=20)
    ordinary = next(o for o in alt_costs.offers(s.state, 'p1', source, Plan(s.state, 'p1', cards, None).ch(source), cards)
                    if o.tag not in {'blitz', 'warp', 'bestow'})
    assert ordinary.key not in {o['id'] for o in casting.alt_castable(s.state, 'p1', source, cards)}
    before = s.state.model_dump(mode='json')
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=source.id, alt_cost=ordinary.key)
    assert s.state.model_dump(mode='json') == before


@pytest.mark.parametrize('name,tag', [(UNDERDOG, 'blitz'), (CULLER, 'warp'), (PHOENIX, 'bestow')])
def test_genuine_fresh_process_restores_selected_keyword_authority_and_actual_cost79(cards, tmp_path, name, tag):
    import os
    import subprocess
    import sys

    s = setup(cards)
    source = put(s, name, 'graveyard')
    extra = {}
    evidence_ids = []
    if name == PHOENIX:
        evidence_ids = [put(s, n, 'graveyard').id for n in ['Divination', SABIN]]
        host = put(s, 'Grizzly Bears', 'battlefield')
        extra = {'targets': [host.id], 'cost_choices': [{'component': 0, 'cards': evidence_ids}]}
    act(s, 'p1', type='clear_mana')
    mana(s, **({'C': 2, 'B': 2} if name == UNDERDOG else {'B': 1} if name == CULLER else {'R': 1}))
    saved = tmp_path / 'required79.json'
    saved.write_text(s.state.model_dump_json())
    code = r'''
import sys,json
from pathlib import Path
from app.cards.repository import CardRepository
from app.cards.images import ImageStore
from app.game.state import GameState
from app.game.session import GameSession
from app.rules import casting
from tests.test_rules_required_keyword79 import key
from tests.test_rules_library_look import settle
from tests.test_rules_designations import roundtrip
from tests.game_helpers import act
r=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=r)
cid,tag,extra,evidence=sys.argv[3:]
source=s.state.cards[cid]
assert not casting.castable(s.state,'p1',source,r)
alternative=key(s,source,tag)
assert alternative in {o['id'] for o in casting.alt_castable(s.state,'p1',source,r)}
life=s.state.players['p1'].life
act(s,'p1',type='cast_spell',card_id=cid,alt_cost=alternative,**json.loads(extra));settle(s)
assert s.state.cards[cid].zone=='p1:battlefield'
assert s.state.rules.payments[s.state.rules.object_id(cid)].alternative==tag
if tag in ('blitz','warp'):assert s.state.players['p1'].life==life-2
else:
 assert s.state.cards[cid].attached_to
 assert all(s.state.cards[c].zone=='p1:exile' for c in json.loads(evidence))
roundtrip(s)
r.close()
'''
    backend = Path(__file__).resolve().parents[1]
    result = subprocess.run([sys.executable, '-c', code, str(saved), str(cards.db_path), source.id, tag,
                             json.dumps(extra), json.dumps(evidence_ids)], cwd=backend,
                            env={**os.environ, 'PYTHONPATH': str(backend)}, capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize('name', [UNDERDOG, PHOENIX])
def test_selected_graveyard_authority_needs_actual_flash_to_be_an_instant_response79(cards, name):
    s = setup(cards)
    source = put(s, name, 'graveyard')
    extra = {}
    if name == PHOENIX:
        evidence = [put(s, n, 'graveyard') for n in ['Divination', SABIN]]
        host = put(s, 'Grizzly Bears', 'battlefield')
        extra = {'targets': [host.id], 'cost_choices': [{'component': 0, 'cards': [c.id for c in evidence]}]}
    hand = list(s.state.zones.get('p1:hand', []))
    if hand:
        act(s, 'p1', type='move', card_ids=hand, to={'player': 'p1', 'zone': 'library'})
    to_phase(s, 'main1', turn=2)
    settle(s)
    act(s, 'p1', type='clear_mana')
    mana(s, C=2, B=2, R=1)
    wait_priority(s, 'p1')
    assert not casting.has_responses(s.state, 'p1', cards)
    assert not casting.alt_castable(s.state, 'p1', source, cards)
    put(s, 'Leyline of Anticipation', 'battlefield')
    assert casting.has_responses(s.state, 'p1', cards)
    tag = 'bestow' if name == PHOENIX else 'blitz'
    assert key(s, source, tag) in {o['id'] for o in casting.alt_castable(s.state, 'p1', source, cards)}
    act(s, 'p1', type='cast_spell', card_id=source.id, alt_cost=key(s, source, tag), **extra)
    settle(s)
    assert source.zone == 'p1:battlefield'
    roundtrip(s)

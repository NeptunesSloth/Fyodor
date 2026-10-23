"""Real Ian exile producers and Kaya loyalty/emblem authorities keep their native scopes."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import casting, coverage
from tests import test_rules_exile_cast_outcomes45_foundation as gameplay
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana, wait_priority
from tests.test_rules_controller_tutors import answer
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_look import settle
from tests.test_rules_ordered_tutor_continuations import cast
from tests.test_rules_wave30m_durations import to_phase

DATA = json.loads((Path(__file__).parent / 'fixtures/linked_owner_cast77_cards.json').read_text())
QUELLER = 'Spell Queller'
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
                          'Jacob Hauken, Inspector // Hauken\'s Insight', 'Spell Queller')



def pending_offer(cards):
    s = setup(cards)
    target = put(s, 'Divination', 'hand')
    mana(s, C=2, U=1)
    act(s, 'p1', type='cast_spell', card_id=target.id)
    queller = put(s, QUELLER, 'hand', pid='p2')
    mana(s, pid='p2', C=1, W=1, U=1)
    wait_priority(s, 'p2')
    act(s, 'p2', type='cast_spell', card_id=queller.id)
    settle(s)
    assert s.state.rules.decision
    answer(s, [target.id])
    settle(s)
    target = next(c for c in s.state.cards.values() if c.name == 'Divination' and c.owner == 'p1')
    queller = next(c for c in s.state.cards.values() if c.name == QUELLER and c.zone.endswith(':battlefield'))
    assert target.zone == 'p1:exile'
    assert queller.zone == 'p2:battlefield', (queller.zone, s.state.rules.decision, [(x.kind,x.source) for x in s.state.rules.stack])
    to_phase(s, 'main1', turn=2)
    settle(s)
    wait_priority(s, 'p1')
    # Actual bounce creates the leaves trigger, independent of its original controller.
    cast(s, 'Disperse', targets=[queller.id])
    d = s.state.rules.decision
    assert d and d.player == 'p1' and target.id in {o.id for o in d.options}
    act(s, 'p1', type='clear_mana')
    return s, target


@pytest.mark.parametrize('choose', [True, False])
def test_native_queller_exiles_and_owner_casts_sorcery_during_opponents_turn(cards, choose):
    s, target = pending_offer(cards)
    if not choose:
        answer(s, [])
        settle(s)
        assert s.state.cards[target.id].zone == 'p1:exile'
        assert not casting.castable(s.state, 'p1', s.state.cards[target.id], cards)
        roundtrip(s)
        return
    hand_before = len(s.state.zones.get('p1:hand', []))
    answer(s, [target.id])
    settle(s)
    target = next(c for c in s.state.cards.values() if c.name == 'Divination' and c.owner == 'p1')
    assert target.zone == 'p1:graveyard'
    assert len(s.state.zones.get('p1:hand', [])) == hand_before + 2
    assert not s.state.players['p1'].mana
    roundtrip(s)


def test_queller_departure_before_enter_trigger_leaves_later_exile_without_an_offer(cards):
    s = setup(cards)
    target = put(s, 'Divination', 'hand')
    mana(s, C=2, U=1)
    act(s, 'p1', type='cast_spell', card_id=target.id)
    queller = put(s, QUELLER, 'hand', pid='p2')
    mana(s, pid='p2', C=1, W=1, U=1)
    wait_priority(s, 'p2')
    act(s, 'p2', type='cast_spell', card_id=queller.id)
    settle(s)
    d = s.state.rules.decision
    assert d
    act(s, d.decider or d.player, type='choose', decision_id=d.id, option_ids=[target.id])
    queller = next(c for c in s.state.cards.values() if c.name == QUELLER and c.owner == 'p2' and c.zone.endswith(':battlefield'))
    wait_priority(s, 'p1')
    cast(s, 'Disperse', targets=[queller.id])
    settle(s)
    target = next(c for c in s.state.cards.values() if c.name == 'Divination' and c.owner == 'p1')
    assert target.zone == 'p1:exile' and not s.state.rules.decision
    assert not casting.castable(s.state, 'p1', target, cards)
    roundtrip(s)


def test_canonical_whole77(cards):
    assert coverage.of_card_data(cards.resolve(QUELLER)).level == 'FULL'


@pytest.mark.parametrize('choose', [True, False])
def test_fresh_process_keeps_original_owner_and_immediate_window77(cards, tmp_path, choose):
    import os
    import subprocess
    import sys

    s, target = pending_offer(cards)
    saved = tmp_path / 'queller.json'
    saved.write_text(s.state.model_dump_json())
    code = r'''
import sys
from pathlib import Path
from app.cards.repository import CardRepository
from app.cards.images import ImageStore
from app.game.state import GameState
from app.game.session import GameSession
from app.rules import casting
from tests.test_rules_controller_tutors import answer
from tests.test_rules_designations import roundtrip
r=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=r)
cid,choose=sys.argv[3:]
assert s.state.rules.decision.player=='p1'
assert cid in {o.id for o in s.state.rules.decision.options}
before=len(s.state.zones.get('p1:hand',[]))
answer(s,[cid] if choose=='True' else [])
if choose=='True':
 assert s.state.cards[cid].zone=='p1:graveyard'
 assert len(s.state.zones.get('p1:hand',[]))==before+2
 assert not s.state.players['p1'].mana
else:
 assert s.state.cards[cid].zone=='p1:exile'
 assert not casting.castable(s.state,'p1',s.state.cards[cid],r)
roundtrip(s)
r.close()
'''
    backend = Path(__file__).resolve().parents[1]
    result = subprocess.run([sys.executable, '-c', code, str(saved), str(cards.db_path), target.id, str(choose)],
                            cwd=backend, env={**os.environ, 'PYTHONPATH': str(backend)},
                            capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize('x', [2, 3])
def test_real_queller_target_uses_announced_x_in_stack_mana_value77(cards, x):
    s = setup(cards)
    target = put(s, 'Hydroid Krasis', 'hand')
    mana(s, C=x, U=1, G=1)
    act(s, 'p1', type='cast_spell', card_id=target.id, x_value=x)
    # Let the actual cast trigger resolve while preserving the underlying creature spell.
    for _ in range(12):
        if not any(e.kind == 'trigger' for e in s.state.rules.stack.values()):
            break
        act(s, s.state.rules.priority, type='pass_priority')
    else:
        raise AssertionError('Krasis cast trigger did not resolve')
    queller = put(s, QUELLER, 'hand', pid='p2')
    mana(s, pid='p2', C=1, W=1, U=1)
    wait_priority(s, 'p2')
    act(s, 'p2', type='cast_spell', card_id=queller.id)
    settle(s)
    if x == 2:
        d = s.state.rules.decision
        assert d and target.id in {o.id for o in d.options}
        answer(s, [target.id])
        assert s.state.cards[target.id].zone == 'p1:exile'
    else:
        assert s.state.rules.decision is None
        assert s.state.cards[target.id].zone == 'p1:battlefield'
    roundtrip(s)


def test_queller_free_recast_still_cannot_pay_a_missing_mandatory_sacrifice77(cards):
    s = setup(cards)
    host = put(s, 'Grizzly Bears', 'battlefield')
    victim = put(s, 'Grizzly Bears', 'battlefield', pid='p3')
    spell = put(s, 'Bone Splinters', 'hand')
    mana(s, B=1)
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[victim.id],
        cost_choices=[{'component': 0, 'cards': [host.id]}])
    queller = put(s, QUELLER, 'hand', pid='p2')
    mana(s, pid='p2', C=1, W=1, U=1)
    wait_priority(s, 'p2')
    act(s, 'p2', type='cast_spell', card_id=queller.id)
    settle(s)
    answer(s, [spell.id])
    queller = next(c for c in s.state.cards.values() if c.name == QUELLER and c.owner == 'p2' and c.zone.endswith(':battlefield'))
    cast(s, 'Disperse', targets=[queller.id])
    # No eligible public spell can be offered: the original paid sacrifice cannot pay again.
    assert not s.state.rules.decision
    assert s.state.cards[spell.id].zone == 'p1:exile'
    assert s.state.cards[host.id].zone == 'p1:graveyard'
    assert s.state.cards[victim.id].zone == 'p3:battlefield'
    roundtrip(s)

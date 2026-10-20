"""Canonical actual-tap receipts, native energy payment and saved choices."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_linked_aggregates import cast
from tests.test_rules_shared_damage_choices import table


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/tap_energy_outcomes43_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='ter', number=str(i), **{('card_faces' if k == 'faces' else k): v for k, v in c.items() if k not in ('name', 'set_code')})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards, energy=2, barrier=False):
    names = ['Suppression Ray // Orderly Plaza', 'Grizzly Bears', 'Llanowar Elves', 'Pili-Pala', 'Solemnity']
    s = table(cards, names, names, names)
    source = put(s, 'Suppression Ray // Orderly Plaza', 'hand')
    old = put(s, 'Grizzly Bears', 'battlefield', pid='p2')
    fresh = put(s, 'Llanowar Elves', 'battlefield', pid='p2')
    other = put(s, 'Pili-Pala', 'battlefield', pid='p2')
    act(s, 'p1', type='tap', card_ids=[old.id], tapped=True)
    if energy:
        act(s, 'p1', type='resource', player='p1', key='energy', delta=energy)
    if barrier:
        put(s, 'Solemnity', 'battlefield')
    cast(s, source, targets=['p2'])
    settle(s)
    return s, source, old, fresh, other


def amount(s, n):
    d = s.state.rules.decision
    assert d is not None
    act(s, d.player, type='choose', decision_id=d.id, name=str(n))
    settle(s)


def test_full_canonical(cards):
    assert coverage.of_card_data(cards.resolve('Suppression Ray // Orderly Plaza')).level == 'FULL'


def test_actual_only_newly_tapped_are_offered_and_up_to_not_forced(cards):
    s, _, old, fresh, other = setup(cards)
    amount(s, 2)
    d = s.state.rules.decision
    assert d is not None and d.min_choices == 0 and d.max_choices == 2
    assert {o.card_id for o in d.options} == {fresh.id, other.id}
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[fresh.id])
    settle(s)
    assert s.state.players['p1'].resources['energy'] == 0
    assert s.state.cards[fresh.id].counters == {'stun': 1}
    assert not s.state.cards[old.id].counters and not s.state.cards[other.id].counters
    assert all(s.state.cards[c.id].tapped for c in [old, fresh, other])
    roundtrip(s)


@pytest.mark.parametrize('energy', [0, 2])
def test_actual_zero_payment_keeps_energy_and_no_stun(cards, energy):
    s, _, old, fresh, other = setup(cards, energy)
    if energy:
        amount(s, 0)
    assert s.state.rules.decision is None
    assert s.state.players['p1'].resources.get('energy', 0) == energy
    assert all(s.state.cards[c.id].tapped and not s.state.cards[c.id].counters for c in [old, fresh, other])
    roundtrip(s)


def test_actual_energy_paid_even_if_counter_placement_prohibited(cards):
    s, _, _, fresh, other = setup(cards, barrier=True)
    amount(s, 2)
    d = s.state.rules.decision
    assert d is not None
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[fresh.id, other.id])
    settle(s)
    assert s.state.players['p1'].resources['energy'] == 0
    assert not s.state.cards[fresh.id].counters and not s.state.cards[other.id].counters
    roundtrip(s)


def test_actual_orderly_plaza_land_face_enters_tapped_and_makes_mana(cards):
    from tests.test_rules_bandmate_references import wait_priority

    names = ['Suppression Ray // Orderly Plaza']
    s = table(cards, names, names, names)
    source = put(s, names[0], 'hand')
    wait_priority(s, 'p1')
    act(s, 'p1', type='play_land', card_id=source.id, face=1)
    assert s.state.cards[source.id].tapped and s.state.cards[source.id].face == 1
    act(s, 'p1', type='tap', card_ids=[source.id], tapped=False)
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=1)
    d = s.state.rules.decision
    if d is not None:
        act(s, d.player, type='choose', decision_id=d.id, option_ids=[d.options[0].id])
    assert s.state.cards[source.id].tapped
    assert sum(s.state.players['p1'].mana.get(k, 0) for k in ['W', 'U']) + sum(u.sym in ('W', 'U') for u in s.state.players['p1'].mana_units) == 1
    roundtrip(s)


def test_actual_saved_tap_and_payment_choices_true_cold(cards, tmp_path):
    import subprocess
    import sys

    s, _, old, fresh, other = setup(cards)
    amount(s, 2)
    assert s.state.rules.decision is not None
    saved = tmp_path / 'tap43.json'
    saved.write_text(s.state.model_dump_json())
    script = r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
saved, db, old, fresh, other = sys.argv[1:]
repo = CardRepository(Path(db), ImageStore(Path(db).parent / 'images'))
s = GameSession(GameState.model_validate_json(Path(saved).read_text()), cards=repo)
d = s.state.rules.decision
assert d is not None and {o.card_id for o in d.options} == {fresh, other}
s.perform(d.player, {'type':'choose','decision_id':d.id,'option_ids':[other]})
assert s.state.players['p1'].resources['energy'] == 0
assert s.state.cards[other].counters == {'stun':1}
assert not s.state.cards[old].counters and not s.state.cards[fresh].counters
assert s.history.rebuild().model_dump(mode='json') == s.state.model_dump(mode='json')
repo.close()
'''
    result = subprocess.run([sys.executable, '-c', script, str(saved), str(cards.db_path), old.id, fresh.id, other.id],
                            cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr


def test_actual_energy_overpayment_rejects_without_consuming_anything(cards):
    from app.game.errors import ActionError

    s, _, _, _, _ = setup(cards)
    before = s.state.model_dump(mode='json')
    with pytest.raises(ActionError):
        amount(s, 3)
    assert s.state.model_dump(mode='json') == before


def test_actual_paid_energy_does_not_force_any_recipient(cards):
    s, _, old, fresh, other = setup(cards)
    amount(s, 2)
    d = s.state.rules.decision
    assert d is not None
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[])
    settle(s)
    assert s.state.players['p1'].resources['energy'] == 0
    assert all(not s.state.cards[c.id].counters for c in [old, fresh, other])
    roundtrip(s)

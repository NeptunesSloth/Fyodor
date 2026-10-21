"""Historical Ring choices and committed kinds use native target and counter authority."""
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
from tests.test_rules_bandmate_references import mana, wait_priority
from tests.test_rules_counter_event_comparisons50 import resolve_only
from tests.test_rules_declaration_requirements33 import start
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_look import settle
from tests.test_rules_shared_damage_choices import table

SOURCE = 'Aragorn, Company Leader'
DATA = json.loads((Path(__file__).parent / 'fixtures/ring_counter_packets67_cards.json').read_text())
NAMES = [c['name'] for c in DATA] + ['Grizzly Bears']


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(DATA):
        base[c['name']] = card(c['name'], number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards):
    s = table(cards, NAMES, NAMES, NAMES)
    start(s)
    act(s, 'p1', type='set_prefs', hold_priority=True)
    source = put(s, SOURCE, 'hand')
    mana(s, C=1, G=1, W=1)
    act(s, 'p1', type='cast_spell', card_id=source.id, sources=[])
    settle(s)
    assert source.zone == 'p1:battlefield' and not s.state.players['p1'].mana
    ours = put(s, 'Grizzly Bears', 'battlefield')
    theirs = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    return s, source, ours, theirs


def answer(s, ids):
    d = s.state.rules.decision
    assert d is not None
    act(s, d.player, type='choose', decision_id=d.id, option_ids=ids)
    settle(s)


def gift(s, source, pid='p1'):
    wait_priority(s, pid)
    spell = put(s, 'Gift of the Viper', 'hand', pid)
    mana(s, pid=pid, G=1)
    act(s, pid, type='cast_spell', card_id=spell.id, targets=[source.id], sources=[])
    settle(s)
    return spell


def tempt(s, bearer):
    wait_priority(s, 'p1')
    spell = put(s, 'Birthday Escape', 'hand')
    mana(s, U=1)
    act(s, 'p1', type='cast_spell', card_id=spell.id, sources=[])
    settle(s)
    answer(s, [bearer.id])
    return spell


def test_whole_canonical_supported(cards):
    assert coverage.of_card_data(cards.resolve(SOURCE)).level == 'FULL'


@pytest.mark.parametrize('kind', ['first strike', 'vigilance', 'deathtouch', 'lifelink'])
def test_paid_ring_tempt_selects_keyword_and_distributes_that_kind(cards, kind):
    s, source, ours, theirs = setup(cards)
    tempt(s, ours)
    answer(s, [kind])
    answer(s, [theirs.id])
    assert source.counters == theirs.counters == {kind: 1}
    assert not ours.counters
    roundtrip(s)


def test_choosing_aragorn_does_not_trigger_its_first_ability(cards):
    s, source, ours, theirs = setup(cards)
    tempt(s, source)
    assert not source.counters and not s.state.zones['stack'] and s.state.rules.decision is None
    roundtrip(s)


@pytest.mark.parametrize('owner,expected', [('p1', 2), ('p2', 1)])
def test_each_actual_kind_is_one_counter_before_recipient_replacement(cards, owner, expected):
    s, source, ours, theirs = setup(cards)
    put(s, 'Doubling Season', 'battlefield')
    gift(s, source)
    target = ours if owner == 'p1' else theirs
    answer(s, [target.id])
    kinds = ['+1/+1', 'reach', 'deathtouch']
    assert source.counters == {kind: 2 for kind in kinds}
    assert target.counters == {kind: expected for kind in kinds}
    roundtrip(s)


def test_optional_other_target_can_be_omitted(cards):
    s, source, ours, theirs = setup(cards)
    gift(s, source)
    answer(s, [])
    assert source.counters == {'+1/+1': 1, 'reach': 1, 'deathtouch': 1}
    assert not ours.counters and not theirs.counters
    roundtrip(s)


def test_opponent_putting_counters_on_aragorn_does_not_trigger(cards):
    s, source, ours, theirs = setup(cards)
    gift(s, source, 'p2')
    assert source.counters == {'+1/+1': 1, 'reach': 1, 'deathtouch': 1}
    assert s.state.rules.decision is None and not s.state.zones['stack']
    roundtrip(s)


def test_no_committed_counter_packet_when_solemnity_prevents_placement(cards):
    s, source, ours, theirs = setup(cards)
    put(s, 'Solemnity', 'battlefield')
    gift(s, source)
    assert not source.counters and not ours.counters and not theirs.counters
    assert s.state.rules.decision is None and not s.state.zones['stack']
    roundtrip(s)


def test_same_ring_bearer_chosen_again_still_triggers(cards):
    s, source, ours, theirs = setup(cards)
    spell = tempt(s, ours)
    answer(s, ['vigilance'])
    answer(s, [theirs.id])
    act(s, 'p1', type='move', card_ids=[spell.id], to={'player': 'p1', 'zone': 'hand'})
    tempt(s, ours)
    answer(s, ['vigilance'])
    answer(s, [theirs.id])
    assert source.counters == theirs.counters == {'vigilance': 2}
    roundtrip(s)


def test_source_blink_does_not_replace_retained_original_counter_packet(cards):
    s, source, ours, theirs = setup(cards)
    gift(s, source)
    d = s.state.rules.decision
    assert d is not None
    assert source.id not in {o.id for o in d.options}
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[theirs.id])
    old_oid = s.state.rules.object_id(source.id)
    wait_priority(s, 'p1')
    blink = put(s, 'Flicker of Fate', 'hand')
    mana(s, C=1, W=1)
    act(s, 'p1', type='cast_spell', card_id=blink.id, targets=[source.id], sources=[])
    resolve_only(s, blink)
    assert s.state.rules.object_id(source.id) != old_oid and not source.counters
    settle(s)
    assert theirs.counters == {'+1/+1': 1, 'reach': 1, 'deathtouch': 1}
    assert not source.counters
    roundtrip(s)


def test_copied_old_ability_may_target_new_source_incarnation(cards):
    s, source, ours, theirs = setup(cards)
    gift(s, source)
    d = s.state.rules.decision
    assert d is not None
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[theirs.id])
    original = s.state.zones['stack'][0]
    wait_priority(s, 'p1')
    blink = put(s, 'Flicker of Fate', 'hand')
    mana(s, C=1, W=1)
    act(s, 'p1', type='cast_spell', card_id=blink.id, targets=[source.id], sources=[])
    resolve_only(s, blink)
    copy = put(s, 'Virtue of Knowledge // Vantress Visions', 'hand')
    mana(s, C=1, U=1)
    act(s, 'p1', type='cast_spell', card_id=copy.id, face=1, targets=[original], sources=[])
    settle(s)
    answer(s, [source.id])  # The original source object is gone; this is now "other".
    answer(s, [])  # The new source's own counter trigger need not target another creature.
    assert source.counters == theirs.counters == {'+1/+1': 1, 'reach': 1, 'deathtouch': 1}
    roundtrip(s)


def test_true_cold_queued_target_choice_uses_each_kind_once(cards, tmp_path):
    import subprocess
    import sys

    s, source, ours, theirs = setup(cards)
    put(s, 'Doubling Season', 'battlefield')
    gift(s, source)
    assert s.state.rules.decision is not None
    saved = tmp_path / 'ring67.json'
    saved.write_text(s.state.model_dump_json())
    code = r"""
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.game_helpers import act
from tests.test_rules_library_look import settle
from tests.test_rules_designations import roundtrip
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
d=s.state.rules.decision
assert d and d.player=='p1'
act(s,'p1',type='choose',decision_id=d.id,option_ids=[sys.argv[4]])
settle(s)
assert s.state.cards[sys.argv[3]].counters=={'+1/+1':2,'reach':2,'deathtouch':2}
assert s.state.cards[sys.argv[4]].counters=={'+1/+1':1,'reach':1,'deathtouch':1}
roundtrip(s)
"""
    result = subprocess.run([sys.executable, '-c', code, str(saved), str(cards.db_path), source.id, theirs.id],
                            capture_output=True, text=True, timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr

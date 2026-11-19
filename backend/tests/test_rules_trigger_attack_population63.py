"""Charging Hooligan reads the current global attacking population on resolution."""
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
from tests.test_rules_declaration_requirements33 import start
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_look import settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave6c_tokens_pumps import chars
from tests.test_rules_wave30m_durations import to_phase
from tests.test_rules_wave30p_combat import attack

NAME = 'Charging Hooligan'
DATA = json.loads((Path(__file__).parent / 'fixtures/trigger_attack_population63_cards.json').read_text())


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


def cast(s, name, pool, targets=(), *, pid='p1', resolve=True, **kwargs):
    wait_priority(s, pid)
    c = put(s, name, 'hand', pid)
    mana(s, pid=pid, **pool)
    act(s, pid, type='cast_spell', card_id=c.id, targets=list(targets), **kwargs)
    if resolve:
        settle(s)
    return c


def setup(cards, support=None, *, amoeboid=False, type_chooser=False):
    deck = [c['name'] for c in DATA] + ['Grizzly Bears']
    s = table(cards, deck, deck, deck)
    other = put(s, support, 'battlefield') if support else None
    shifter = (put(s, 'Universal Automaton', 'battlefield') if amoeboid else
               put(s, 'Unnatural Selection', 'battlefield') if type_chooser else None)
    start(s)
    act(s, 'p1', type='set_prefs', hold_priority=True)
    source = cast(s, NAME, {'C': 3, 'R': 1})
    assert source.zone == 'p1:battlefield'
    to_phase(s, 'declare_attackers', turn=7)
    attack(s, (source, 'p2'), *((other, 'p3'),) if other else ())
    return s, source, other, shifter


def check(s, source, power, trample):
    assert chars(s, source).pt == (power, 3)
    assert ('trample' in chars(s, source).keywords) == trample
    roundtrip(s)


def test_whole_actual_canonical(cards):
    assert coverage.of_card_data(cards.resolve(NAME)).level == 'FULL'


@pytest.mark.parametrize('support,expected,rat', [(None, 4, False), ('Grizzly Bears', 5, False),
                                               ('Typhoid Rats', 5, True), ('Universal Automaton', 5, True)])
def test_paid_cast_native_attack_counts_self_and_all_other_attackers(cards, support, expected, rat):
    s, source, _, _ = setup(cards, support)
    settle(s)
    check(s, source, expected, rat)


def test_nonattacking_changeling_rat_does_not_grant_trample(cards):
    s, source, _, shifter = setup(cards, amoeboid=True)
    assert shifter.attacking is None and 'Rat' in chars(s, shifter).subtypes
    settle(s)
    check(s, source, 4, False)


@pytest.mark.parametrize('rat', [False, True])
def test_departed_attacker_is_not_counted_and_departed_rat_does_not_grant(cards, rat):
    s, source, other, _ = setup(cards, 'Typhoid Rats' if rat else 'Grizzly Bears')
    cast(s, 'Unsummon', {'U': 1}, [other.id])
    assert other.zone == 'p1:hand'
    check(s, source, 4, False)


def test_rat_can_appear_during_response_before_the_separate_rat_check(cards):
    s, source, bear, shifter = setup(cards, 'Grizzly Bears', type_chooser=True)
    wait_priority(s, 'p1')
    mana(s, C=1)
    ability = next(a for a in chars(s, shifter).abilities if a.kind == 'activated')
    act(s, 'p1', type='activate_ability', card_id=shifter.id, ability=ability.index, targets=[bear.id])
    settle(s)
    d = s.state.rules.decision
    assert d is not None
    act(s, d.player, type='choose', decision_id=d.id, option_ids=['Rat'])
    settle(s)
    assert 'Rat' in chars(s, bear).subtypes
    check(s, source, 5, True)


def test_attacking_rat_can_lose_its_type_without_leaving_combat(cards):
    s, source, rat, shifter = setup(cards, 'Typhoid Rats', type_chooser=True)
    wait_priority(s, 'p1')
    mana(s, C=1)
    ability = next(a for a in chars(s, shifter).abilities if a.kind == 'activated')
    act(s, 'p1', type='activate_ability', card_id=shifter.id, ability=ability.index, targets=[rat.id])
    settle(s)
    d = s.state.rules.decision
    assert d is not None
    act(s, d.player, type='choose', decision_id=d.id, option_ids=['Bear'])
    settle(s)
    assert rat.attacking is not None and 'Rat' not in chars(s, rat).subtypes
    check(s, source, 5, False)


@pytest.mark.parametrize('create_first', [False, True])
def test_actual_garrison_attackers_added_before_or_after_count(cards, create_first):
    s, source, garrison, _ = setup(cards, 'Hanweir Garrison')
    d = s.state.rules.decision
    assert d is not None and d.kind == 'order'
    options = {o.label.split(' — ')[0]: o.id for o in d.options}  # (labels read "Name — ability text")
    order = [NAME, 'Hanweir Garrison'] if create_first else ['Hanweir Garrison', NAME]
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[options[n] for n in order])
    settle(s)
    while (d := s.state.rules.decision) is not None and d.resume.get('step') == 'token_attack':
        act(s, d.player, type='choose', decision_id=d.id, option_ids=['p2'])
        settle(s)
    tokens = [c for c in s.state.cards.values() if c.is_token and c.zone == 'p1:battlefield' and c.attacking is not None]
    assert len(tokens) == 2 and garrison.attacking is not None
    check(s, source, 7 if create_first else 5, False)


def test_nonactive_player_copy_counts_opponents_attackers_and_rat(cards):
    from tests.test_rules_counter_event_comparisons50 import resolve_only

    s, source, rat, _ = setup(cards, 'Typhoid Rats')
    original = next(sid for sid, entry in s.state.rules.stack.items() if entry.source_card == source.id)
    favor = cast(s, 'Return the Favor', {'C': 1, 'R': 2}, [original], pid='p2', resolve=False, modes=[0])
    resolve_only(s, favor)
    assert any(entry.controller == 'p2' and entry.source_card == source.id for entry in s.state.rules.stack.values())
    cast(s, 'Stifle', {'U': 1}, [original], pid='p3')
    assert original not in s.state.rules.stack and rat.attacking is not None
    check(s, source, 5, True)


def test_blink_successor_gets_neither_old_bonus_nor_trample(cards):
    s, source, _, _ = setup(cards, 'Typhoid Rats')
    old = s.state.rules.object_id(source.id)
    cast(s, 'Cloudshift', {'W': 1}, [source.id])
    assert s.state.rules.object_id(source.id) != old and source.attacking is None
    check(s, source, 3, False)


def test_cleanup_removes_both_current_count_bonus_and_trample(cards):
    s, source, _, _ = setup(cards, 'Typhoid Rats')
    settle(s)
    check(s, source, 5, True)
    to_phase(s, 'main1', turn=8)
    check(s, source, 3, False)


def test_true_cold_pending_current_attack_population(cards, tmp_path):
    import subprocess
    import sys

    s, source, rat, _ = setup(cards, 'Typhoid Rats')
    saved = tmp_path / 'population63.json'
    saved.write_text(s.state.model_dump_json())
    code = r"""
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.test_rules_library_look import settle
from tests.test_rules_trigger_attack_population63 import check
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
source,rat=[s.state.cards[x] for x in sys.argv[3:5]]
assert s.state.zones['stack'] and rat.attacking is not None
settle(s)
check(s,source,5,True)
"""
    result = subprocess.run([sys.executable, '-c', code, str(saved), str(cards.db_path), source.id, rat.id],
                            capture_output=True, text=True, timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr

"""Professor Onyx repeats one simultaneous private discard operation seven times."""
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
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_wave30m_durations import three
from tests.test_rules_wave31d_spell_copies import hold

DATA = Path(__file__).parent / 'fixtures/professor_onyx_cards.json'


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads(DATA.read_text())):
        base[c['name']] = card(c['name'], set_code='pox', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards, *, extras=(), opponents=()):
    s = three(cards, ['Professor Onyx', *extras], opponents, opponents)
    hold(s)
    for p in ['p2', 'p3']:
        act(s, p, type='draw', count=7)
    source = put(s, 'Professor Onyx', 'battlefield')
    act(s, 'p1', type='counter', card_ids=[source.id], kind='loyalty', delta=8)
    return s, source


def ultimate(s, source):
    ability = next(a.index for a in Plan(s.state, s.state.cards[source.id].controller, s.cards, None).ch(source).abilities if a.kind == 'loyalty' and a.cost in ('−8', '-8'))
    act(s, s.state.cards[source.id].controller, type='activate_ability', card_id=source.id, ability=ability)
    settle(s)


def answer(s, ids):
    d = s.state.rules.decision
    assert d is not None
    act(s, d.player, type='choose', decision_id=d.id, option_ids=ids)
    settle(s)


def decline(s):
    d = s.state.rules.decision
    assert d is not None and 'decline' in {o.id for o in d.options}, d
    answer(s, ['decline'])


def pay(s, cid=None):
    d = s.state.rules.decision
    assert d is not None
    if 'pay' in {o.id for o in d.options}:
        answer(s, ['pay'])
    d = s.state.rules.decision
    if d is not None and cid in {o.id for o in d.options}:
        answer(s, [cid])


def finish_declining(s):
    count = 0
    while s.state.rules.decision is not None:
        assert count < 30
        decline(s)
        count += 1
    settle(s)
    return count


def test_real_oracle_card_is_fully_supported(cards):
    result = coverage.of_card_data(cards.resolve('Professor Onyx'))
    assert result.level == 'FULL', result.manual_parts


def test_every_opponent_declines_seven_rounds_for_twenty_one_life_each(cards):
    s, source = setup(cards)
    before = {p: s.state.players[p].life for p in ['p2', 'p3']}
    ultimate(s, source)
    players = []
    while s.state.rules.decision is not None:
        players.append(s.state.rules.decision.player)
        decline(s)
    assert players == ['p2', 'p3'] * 7
    assert all(s.state.players[p].life == before[p] - 21 for p in before)
    roundtrip(s)


def test_empty_hands_still_lose_life_in_each_of_seven_rounds(cards):
    s, source = setup(cards)
    for p in ['p2', 'p3']:
        act(s, p, type='move', card_ids=list(s.state.zones[p + ':hand']), to={'player': p, 'zone': 'library'})
    ultimate(s, source)
    assert s.state.rules.decision is None
    assert all(s.state.players[p].life == 19 for p in ['p2', 'p3'])
    roundtrip(s)


def test_first_round_discards_wait_until_all_opponents_choose_and_are_one_batch(cards):
    from app.rules.view import decision_view

    s, source = setup(cards)
    ultimate(s, source)
    a = s.state.zones['p2:hand'][0]
    b = s.state.zones['p3:hand'][0]
    pay(s, a)
    assert s.state.cards[a].zone == 'p2:hand'
    d = s.state.rules.decision
    assert d.player == 'p3'
    assert a not in json.dumps(decision_view(s.state, d, 'p3'))
    pay(s, b)
    assert s.state.cards[a].zone == 'p2:graveyard' and s.state.cards[b].zone == 'p3:graveyard'
    events = [e for e in s.state.rules.events if e.kind == 'zone_change' and e.card in (a, b)]
    assert len(events) == 2 and len({e.batch for e in events}) == 1
    assert s.state.players['p2'].life == 40 and s.state.players['p3'].life == 40
    assert s.state.rules.decision.player == 'p2'
    finish_declining(s)
    assert s.state.players['p2'].life == 22 and s.state.players['p3'].life == 22
    roundtrip(s)


def test_one_payment_only_protects_that_opponent_in_that_round(cards):
    s, source = setup(cards)
    ultimate(s, source)
    pay(s, s.state.zones['p2:hand'][0])
    decline(s)
    assert s.state.players['p2'].life == 40 and s.state.players['p3'].life == 37
    finish_declining(s)
    assert s.state.players['p2'].life == 22 and s.state.players['p3'].life == 19
    roundtrip(s)


def test_source_is_gone_before_ultimate_and_process_continues_independently(cards):
    s, source = setup(cards)
    ultimate(s, source)
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    finish_declining(s)
    assert s.state.players['p2'].life == 19 and s.state.players['p3'].life == 19
    roundtrip(s)


def test_discard_triggers_wait_until_the_entire_ultimate_finishes(cards):
    s, source = setup(cards, extras=['Megrim'])
    put(s, 'Megrim', 'battlefield')
    ultimate(s, source)
    pay(s, s.state.zones['p2:hand'][0])
    pay(s, s.state.zones['p3:hand'][0])
    assert s.state.players['p2'].life == 40 and s.state.players['p3'].life == 40
    assert s.state.rules.decision.player == 'p2'
    finish_declining(s)
    assert s.state.players['p2'].life == 20 and s.state.players['p3'].life == 20
    roundtrip(s)


def test_simultaneous_discard_can_put_baloth_onto_battlefield_instead(cards):
    s, source = setup(cards, opponents=['Obstinate Baloth'])
    baloth = put(s, 'Obstinate Baloth', 'hand', 'p2')
    ultimate(s, source)
    pay(s, baloth.id)
    other = next(c for c in s.state.zones['p3:hand'] if s.state.cards[c].name == 'Island')
    pay(s, other)
    assert s.state.cards[baloth.id].zone == 'p2:battlefield'
    assert s.state.cards[other].zone == 'p3:graveyard'
    events = [e for e in s.state.rules.events if e.kind == 'zone_change' and e.card in (baloth.id, other)]
    assert len(events) == 2 and len({e.batch for e in events}) == 1
    assert s.state.players['p2'].life == 40  # Baloth ETB has not resolved yet.
    finish_declining(s)
    assert s.state.players['p2'].life == 26 and s.state.players['p3'].life == 22
    roundtrip(s)


@pytest.mark.parametrize('replacement', ['Obstinate Baloth', 'Rest in Peace'])
def test_zone_replacement_choices_finish_before_next_round_without_reselecting_held_card(cards, replacement):
    s, source = setup(cards, extras=['Rest in Peace'], opponents=['Obstinate Baloth'])
    put(s, 'Rest in Peace', 'battlefield')
    baloth = put(s, 'Obstinate Baloth', 'hand', 'p2')
    ultimate(s, source)
    pay(s, baloth.id)
    other = next(c for c in s.state.zones['p3:hand'] if s.state.cards[c].name == 'Island')
    pay(s, other)
    d = s.state.rules.decision
    assert d.resume['step'] == 'grouped_discard_replace'
    assert s.state.cards[baloth.id].zone == 'p2:hand' and s.state.cards[other].zone == 'p3:hand'
    option = next(o.id for o in d.options if o.label == replacement)
    roundtrip(s)
    answer(s, [option])
    assert s.state.cards[baloth.id].zone == ('p2:battlefield' if replacement == 'Obstinate Baloth' else 'p2:exile')
    assert s.state.cards[other].zone == 'p3:exile'
    assert s.state.rules.decision.player == 'p2'
    assert baloth.id not in {o.id for o in s.state.rules.decision.options}
    finish_declining(s)
    assert s.state.players['p2'].life == (26 if replacement == 'Obstinate Baloth' else 22)
    assert s.state.players['p3'].life == 22
    roundtrip(s)


def test_players_at_zero_life_finish_all_rounds_before_state_based_elimination(cards):
    s, source = setup(cards)
    act(s, 'p1', type='life', player='p2', delta=-37)
    ultimate(s, source)
    decline(s)
    decline(s)
    assert s.state.players['p2'].life == 0 and 'p2' not in s.state.rules.lost
    assert s.state.rules.decision.player == 'p2'
    finish_declining(s)
    assert s.state.players['p2'].life == -18 and 'p2' in s.state.rules.lost
    roundtrip(s)


def test_all_seven_rounds_can_be_paid_without_life_loss(cards):
    s, source = setup(cards)
    ultimate(s, source)
    for _ in range(7):
        for player in ['p2', 'p3']:
            assert s.state.rules.decision.player == player
            pay(s, s.state.zones[player + ':hand'][0])
    assert s.state.rules.decision is None
    assert all(s.state.players[p].life == 40 and not s.state.zones[p + ':hand'] for p in ['p2', 'p3'])
    roundtrip(s)


def test_control_changed_source_uses_current_controller_and_apnap_rotation(cards):
    from tests.test_rules_wave30m_durations import to_phase

    s, source = setup(cards)
    act(s, 'p1', type='draw', count=7)
    act(s, 'p1', type='set_controller', card_ids=[source.id], player='p2')
    to_phase(s, 'main1', turn=2)
    ultimate(s, source)
    players = []
    while s.state.rules.decision is not None:
        players.append(s.state.rules.decision.player)
        decline(s)
    assert players == ['p3', 'p1'] * 7
    assert s.state.players['p2'].life == 40
    assert s.state.players['p1'].life == 19 and s.state.players['p3'].life == 19
    roundtrip(s)


@pytest.mark.parametrize('replacement', ['Madness', 'Rest in Peace'])
def test_madness_or_exile_replacement_is_chosen_before_commit_and_trigger_waits(cards, replacement):
    s, source = setup(cards, extras=['Rest in Peace'], opponents=['Fiery Temper'])
    put(s, 'Rest in Peace', 'battlefield')
    temper = put(s, 'Fiery Temper', 'hand', 'p2')
    ultimate(s, source)
    pay(s, temper.id)
    other = next(c for c in s.state.zones['p3:hand'] if s.state.cards[c].name == 'Island')
    pay(s, other)
    d = s.state.rules.decision
    assert d.resume['step'] == 'grouped_discard_replace'
    answer(s, [next(o.id for o in d.options if o.label == replacement)])
    assert s.state.cards[temper.id].zone == 'p2:exile'
    assert s.state.rules.decision.player == 'p2' and s.state.rules.decision.resume['step'] != 'suspend_cast'
    for _ in range(12):
        decline(s)
    if replacement == 'Madness':
        assert s.state.rules.decision.resume['step'] == 'suspend_cast'
        answer(s, ['no'])
    assert s.state.rules.decision is None
    assert temper.id not in s.state.rules.free_casts
    assert s.state.players['p2'].life == 22 and s.state.players['p3'].life == 22
    roundtrip(s)


@pytest.mark.parametrize('stage', ['private', 'replacement'])
def test_ultimate_continues_in_a_fresh_process_from_private_or_replacement_choices(cards, tmp_path, stage):
    import subprocess
    import sys

    s, source = setup(cards, extras=['Rest in Peace'] if stage == 'replacement' else (),
                      opponents=['Obstinate Baloth'] if stage == 'replacement' else ())
    if stage == 'replacement':
        put(s, 'Rest in Peace', 'battlefield')
        first = put(s, 'Obstinate Baloth', 'hand', 'p2').id
    else:
        first = s.state.zones['p2:hand'][0]
    ultimate(s, source)
    pay(s, first)
    if stage == 'replacement':
        other = next(c for c in s.state.zones['p3:hand'] if s.state.cards[c].name == 'Island')
        pay(s, other)
        d = s.state.rules.decision
        assert d.resume['step'] == 'grouped_discard_replace'
        option = next(o.id for o in d.options if o.label == 'Rest in Peace')
    else:
        assert s.state.rules.decision.player == 'p3'
        assert s.state.cards[first].zone == 'p2:hand'
        option = 'decline'
    roundtrip(s)
    saved = tmp_path / 'onyx.json'
    saved.write_text(s.state.model_dump_json())
    code = r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
path, database, option, stage, first = sys.argv[1:]
repo = CardRepository(Path(database), ImageStore(Path(database).parent / 'images'))
s = GameSession(GameState.model_validate_json(Path(path).read_text()), cards=repo)
d = s.state.rules.decision
s.perform(d.player, {'type': 'choose', 'decision_id': d.id, 'option_ids': [option]})
for _ in range(40):
    d = s.state.rules.decision
    if d is not None:
        assert 'decline' in {o.id for o in d.options}
        s.perform(d.player, {'type': 'choose', 'decision_id': d.id, 'option_ids': ['decline']})
    elif s.state.zones.get('stack'):
        s.perform(s.state.rules.priority, {'type': 'pass_priority'})
    else:
        break
assert s.state.players['p2'].life == 22
assert s.state.players['p3'].life == (22 if stage == 'replacement' else 19)
assert s.state.cards[first].zone == ('p2:exile' if stage == 'replacement' else 'p2:graveyard')
assert not s.state.rules.pending_616
assert s.history.rebuild() == s.state
assert GameState.model_validate_json(s.state.model_dump_json()) == s.state
repo.close()
'''
    result = subprocess.run([sys.executable, '-c', code, str(saved), str(cards.db_path), option, stage, first],
                            capture_output=True, text=True, cwd=Path(__file__).resolve().parents[1], timeout=60)
    assert result.returncode == 0, result.stderr

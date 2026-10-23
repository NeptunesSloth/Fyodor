"""Native permanent offers defer every outcome until all APNAP choices finish."""
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
from tests.test_rules_bandmate_references import wait_priority
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_look import settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

DATA = json.loads((Path(__file__).parent / 'fixtures/lore89_cards.json').read_text())
ALL = [c['name'] for c in DATA] + ['Grizzly Bears', 'Llanowar Elves', 'Sol Ring', 'Forest', 'Island']


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


def game(cards):
    s = table(cards, ALL, ALL, ALL)
    to_phase(s, 'main1', 1)
    return s


def choose(s, ids):
    d = s.state.rules.decision
    assert d is not None
    act(s, d.player, type='choose', decision_id=d.id, option_ids=ids)
    settle(s)



@pytest.mark.parametrize('name', ['Forgotten Lore', 'Shrouded Lore'])
def test_whole(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


def test_choice_decline_native_return(cards):
    s = game(cards)
    first = put(s, 'Grizzly Bears', 'graveyard')
    second = put(s, 'Forest', 'graveyard')
    source = put(s, 'Forgotten Lore', 'hand')
    wait_priority(s, 'p1')
    act(s, 'p1', type='add_mana', player='p1', mana={'G': 1})
    act(s, 'p1', type='cast_spell', card_id=source.id, targets=['p2'], sources=[])
    settle(s)
    assert s.state.rules.decision.player == 'p2'
    choose(s, [first.id])
    assert s.state.cards[first.id].zone == 'p1:hand'
    assert s.state.cards[second.id].zone == 'p1:graveyard'


def cast_lore(s, name='Forgotten Lore', mana=3):
    source = put(s, name, 'hand')
    wait_priority(s, 'p1')
    act(s, 'p1', type='add_mana', player='p1', mana={'G' if name == 'Forgotten Lore' else 'B': mana})
    act(s, 'p1', type='cast_spell', card_id=source.id, targets=['p2'], sources=[])
    settle(s)
    return source


@pytest.mark.parametrize('name', ['Forgotten Lore', 'Shrouded Lore'])
def test_actual_repeat_excludes_previous_and_returns_only_last(cards, name):
    s = game(cards)
    first = put(s, 'Grizzly Bears', 'graveyard')
    second = put(s, 'Forest', 'graveyard')
    cast_lore(s, name, mana=2)
    choose(s, [first.id])
    assert s.state.rules.decision.player == 'p1'
    choose(s, ['pay'])
    assert s.state.rules.decision.player == 'p2'
    assert {o.id for o in s.state.rules.decision.options} == {second.id}
    choose(s, [second.id])
    assert s.state.cards[first.id].zone == 'p1:graveyard'
    assert s.state.cards[second.id].zone == 'p1:hand'
    assert s.state.players['p1'].mana == {}
    roundtrip(s)


def test_exhausted_choices_still_offer_each_payment_keep_last(cards):
    s = game(cards)
    first = put(s, 'Grizzly Bears', 'graveyard')
    cast_lore(s, mana=4)
    choose(s, [first.id])
    for _ in range(2):
        assert s.state.rules.decision.player == 'p1'
        choose(s, ['pay'])
        assert s.state.rules.decision.player == 'p1'
        assert s.state.cards[first.id].zone == 'p1:graveyard'
    choose(s, ['decline'])
    assert s.state.cards[first.id].zone == 'p1:hand'
    assert s.state.players['p1'].mana == {'G': 1}
    roundtrip(s)


def test_empty_graveyard_payment_then_decline_is_legal(cards):
    s = game(cards)
    cast_lore(s, mana=3)
    assert s.state.rules.decision.player == 'p1'
    choose(s, ['pay'])
    assert s.state.rules.decision.player == 'p1'
    choose(s, ['decline'])
    assert s.state.players['p1'].mana == {'G': 1}
    roundtrip(s)


def test_real_manual_mana_sacrifice_adds_current_graveyard_candidate(cards):
    from app.game.errors import ActionError

    s = game(cards)
    first = put(s, 'Forest', 'graveyard')
    creature = put(s, 'Grizzly Bears', 'battlefield')
    altar = put(s, 'Phyrexian Altar', 'battlefield')
    cast_lore(s, mana=1)
    choose(s, [first.id])
    d = s.state.rules.decision
    assert d and d.player == 'p1'
    before = s.state.model_dump(mode='json')
    with pytest.raises(ActionError):
        act(s, 'p1', type='choose', decision_id=d.id, option_ids=['pay'])
    assert s.state.model_dump(mode='json') == before
    act(s, 'p1', type='activate_ability', card_id=altar.id, ability=0, mana_choice='G', sources=[],
        cost_choices=[{'component': 0, 'cards': [creature.id]}])
    assert s.state.cards[creature.id].zone == 'p1:graveyard'
    choose(s, ['pay'])
    assert s.state.rules.decision.player == 'p2'
    assert {o.id for o in s.state.rules.decision.options} == {creature.id}
    choose(s, [creature.id])
    assert s.state.cards[creature.id].zone == 'p1:hand'
    assert s.state.cards[first.id].zone == 'p1:graveyard'
    roundtrip(s)


def test_no_legal_mana_sacrifice_does_not_offer_impossible_payment(cards):
    s = game(cards)
    first = put(s, 'Forest', 'graveyard')
    put(s, 'Grizzly Bears', 'battlefield')
    put(s, 'Phyrexian Altar', 'battlefield')
    put(s, 'Angel of Jubilation', 'battlefield')
    cast_lore(s, mana=1)
    choose(s, [first.id])
    assert s.state.rules.decision is None
    assert s.state.cards[first.id].zone == 'p1:hand'


def test_separate_lore_spell_does_not_remember_prior_choices(cards):
    s = game(cards)
    first = put(s, 'Grizzly Bears', 'graveyard')
    second = put(s, 'Forest', 'graveyard')
    cast_lore(s, mana=2)
    choose(s, [first.id])
    choose(s, ['pay'])
    choose(s, [second.id])
    cast_lore(s, 'Shrouded Lore', mana=1)
    assert first.id in {o.id for o in s.state.rules.decision.options}
    choose(s, [first.id])
    assert s.state.cards[first.id].zone == 'p1:hand'
    roundtrip(s)


@pytest.mark.parametrize('command', [False, True])
def test_native_commander_hand_replacement_after_final_choice(cards, command):
    s = game(cards)
    commander = put(s, 'Krenko, Mob Boss', 'graveyard')
    act(s, s.state.rules.priority, type='pass_priority')
    settle(s)
    if s.state.rules.decision:
        choose(s, ['no'])
    assert s.state.cards[commander.id].zone == 'p1:graveyard'
    to_phase(s, 'main2', 1)
    cast_lore(s, mana=1)
    if s.state.rules.decision.resume['step'] == 'lore_choose89':
        choose(s, [commander.id])
    d = s.state.rules.decision
    assert d and d.player == 'p1' and d.resume['step'] == 'commander_first'
    assert s.state.cards[commander.id].zone == 'p1:graveyard'
    choose(s, ['yes' if command else 'no'])
    assert s.state.cards[commander.id].zone == ('p1:command' if command else 'p1:hand')
    roundtrip(s)


@pytest.mark.parametrize('stage', ['opponent_choice', 'payment', 'replacement_player'])
def test_true_cold_native_repeat_packet(cards, tmp_path, stage):
    import os
    import subprocess
    import sys

    import app

    s = game_four(cards) if stage == 'replacement_player' else game(cards)
    first = put(s, 'Grizzly Bears', 'graveyard')
    second = put(s, 'Forest', 'graveyard')
    cast_lore(s, mana=3)
    if stage in {'payment', 'replacement_player'}:
        choose(s, [first.id])
    if stage == 'replacement_player':
        act(s, 'p2', type='concede')
        choose(s, ['pay'])
    saved = tmp_path / 'lore89.json'
    saved.write_text(s.state.model_dump_json())
    backend = Path(app.__file__).resolve().parents[1]
    code = r'''
import sys
from pathlib import Path
from app.cards.repository import CardRepository
from app.cards.images import ImageStore
from app.game.session import GameSession
from app.game.state import GameState
from tests.game_helpers import act
from tests.test_rules_library_look import settle
from tests.test_rules_designations import roundtrip
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
stage,first,second=sys.argv[3:]
def choose(ids):
 d=s.state.rules.decision
 assert d
 act(s,d.player,type='choose',decision_id=d.id,option_ids=ids)
 settle(s)
if stage=='replacement_player':
 assert s.state.rules.decision.resume['step']=='lore_player89'
 assert {o.id for o in s.state.rules.decision.options}=={'p3','p4'}
 choose(['p4'])
 assert s.state.rules.decision.player=='p4'
else:
 if stage=='opponent_choice':
  assert s.state.rules.decision.player=='p2'
  choose([first])
 assert s.state.rules.decision.player=='p1'
 choose(['pay'])
 assert s.state.rules.decision.player=='p2'
assert {o.id for o in s.state.rules.decision.options}=={second}
choose([second])
choose(['decline'])
assert s.state.cards[first].zone=='p1:graveyard' and s.state.cards[second].zone=='p1:hand'
assert s.state.players['p1'].mana=={'G':1}
roundtrip(s)
repo.close()
'''
    result = subprocess.run([sys.executable, '-c', code, str(saved), str(cards.db_path), stage, first.id, second.id],
                            cwd=backend, env={**os.environ, 'PYTHONPATH': str(backend) + os.pathsep + os.environ.get('PYTHONPATH', '')},
                            capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stdout + result.stderr


def test_departed_opponent_during_payment_redirects_repeat_choice(cards):
    s = game(cards)
    first = put(s, 'Grizzly Bears', 'graveyard')
    second = put(s, 'Forest', 'graveyard')
    cast_lore(s, mana=3)
    choose(s, [first.id])
    act(s, 'p2', type='concede')
    choose(s, ['pay'])
    assert s.state.rules.decision.player == 'p3'
    choose(s, [second.id])
    choose(s, ['decline'])
    assert s.state.cards[first.id].zone == 'p1:graveyard'
    assert s.state.cards[second.id].zone == 'p1:hand'
    roundtrip(s)


def test_departed_original_chooser_during_open_card_choice_reroutes(cards):
    s = game(cards)
    first = put(s, 'Grizzly Bears', 'graveyard')
    put(s, 'Forest', 'graveyard')
    cast_lore(s, mana=1)
    act(s, 'p2', type='concede')
    assert s.state.rules.decision.player == 'p3'
    choose(s, [first.id])
    assert s.state.cards[first.id].zone == 'p1:hand'
    roundtrip(s)


def game_four(cards):
    from app.game.factory import PlayerSetup, new_game
    from app.game.session import GameSession
    from tests.game_helpers import deck, enable

    decks = [deck(cards, 'Krenko, Mob Boss' if i == 0 else "Atraxa, Praetors' Voice", [(1, n) for n in ALL] + [(20, 'Forest')]) for i in range(4)]
    s = GameSession(enable(new_game([PlayerSetup(str(i), cards=d) for i, d in enumerate(decks)], shuffle=False)), cards=cards)
    act(s, 'p1', type='pass_priority')
    for pid in s.state.players:
        act(s, pid, type='set_prefs', response='on')
    to_phase(s, 'main1', 1)
    return s


@pytest.mark.parametrize('replacement_leaves', [False, True])
def test_controller_chooses_another_opponent_for_departed_opponent(cards, replacement_leaves):
    s = game_four(cards)
    first = put(s, 'Grizzly Bears', 'graveyard')
    second = put(s, 'Forest', 'graveyard')
    cast_lore(s, mana=3)
    choose(s, [first.id])
    act(s, 'p2', type='concede')
    choose(s, ['pay'])
    d = s.state.rules.decision
    assert d.player == 'p1' and d.resume['step'] == 'lore_player89'
    assert {o.id for o in d.options} == {'p3', 'p4'}
    choose(s, ['p4'])
    assert s.state.rules.decision.player == 'p4'
    if replacement_leaves:
        act(s, 'p4', type='concede')
        assert s.state.rules.decision.player == 'p3'
    choose(s, [second.id])
    choose(s, ['decline'])
    assert s.state.cards[second.id].zone == 'p1:hand'
    roundtrip(s)

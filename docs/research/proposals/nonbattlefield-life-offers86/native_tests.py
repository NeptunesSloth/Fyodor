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

DATA = json.loads((Path(__file__).parent / 'fixtures/nonbattlefield_life86_cards.json').read_text())
ALL = [c['name'] for c in DATA] + ['Grizzly Bears', 'Llanowar Elves', 'Sol Ring', 'Forest', 'Lightning Bolt', 'Island', 'Mountain']


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



def cast(s, name, targets=()):
    c = put(s, name, 'hand')
    wait_priority(s, 'p1')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 5, 'B': 2, 'R': 2})
    act(s, 'p1', type='cast_spell', card_id=c.id, targets=list(targets), sources=[])
    settle(s)
    return c


@pytest.mark.parametrize('name', ['Moonlight Bargain', 'Sirocco'])
def test_whole_sources(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


def test_moonlight_private_original_top_five_two_life_each_and_then_hand(cards):
    from tests.test_rules_refused_look import stack_library

    s = game(cards)
    top = stack_library(s, ['Forest', 'Grizzly Bears', 'Lightning Bolt', 'Island', 'Mountain'])
    cast(s, 'Moonlight Bargain')
    d = s.state.rules.decision
    assert d.player == 'p1' and {o.id for o in d.options} == set(top)
    assert s.state.players['p1'].life == 40
    for pid in ['p2', 'p3']:
        assert not any(cid in json.dumps(s.view(pid)['rules']['decision']) for cid in top)
    keep = top[:2]
    choose(s, keep)
    assert s.state.players['p1'].life == 36
    assert all(s.state.cards[c].zone == 'p1:hand' for c in keep)
    assert all(s.state.cards[c].zone == 'p1:graveyard' for c in top[2:])
    roundtrip(s)


def test_sirocco_reveals_entire_hand_but_only_blue_instants_have_life_offers(cards):
    from app.game.visibility import ALL

    s = game(cards)
    blue = put(s, 'Opt', 'hand', 'p2')
    other = put(s, 'Counterspell', 'hand', 'p2')
    red = put(s, 'Lightning Bolt', 'hand', 'p2')
    creature = put(s, 'Grizzly Bears', 'hand', 'p2')
    cast(s, 'Sirocco', ['p2'])
    d = s.state.rules.decision
    assert d.player == 'p2' and {o.id for o in d.options} == {blue.id, other.id}
    assert all(ALL in s.state.cards[c.id].revealed_to for c in [blue, other, red, creature])
    choose(s, [blue.id])
    assert s.state.players['p2'].life == 36 and s.state.players['p1'].life == 40
    assert s.state.cards[other.id].zone == 'p2:graveyard'
    assert all(s.state.cards[c.id].zone == 'p2:hand' for c in [blue, red, creature])
    assert all(ALL not in s.state.cards[c.id].revealed_to for c in [blue, red, creature])
    roundtrip(s)


@pytest.mark.parametrize('route', ['exile', 'library:shuffle'])
def test_moonlight_prepares_competing_colossus_routes_before_life_and_retains_paid_originals_across_shuffle(cards, route):
    from tests.test_rules_refused_look import stack_library

    s = game(cards)
    put(s, 'Rest in Peace', 'battlefield', 'p3')
    top = stack_library(s, ['Forest', 'Grizzly Bears', 'Darksteel Colossus', 'Island', 'Mountain'])
    keep = top[:2]
    cast(s, 'Moonlight Bargain')
    choose(s, keep)
    d = s.state.rules.decision
    assert d.resume['step'] == 'life_route86' and s.state.players['p1'].life == 40
    assert all(s.state.cards[c].zone == 'p1:library' for c in top)
    answer = next(o.id for o in d.options if route in o.label)
    choose(s, [answer])
    assert s.state.players['p1'].life == 36
    assert all(s.state.cards[c].zone == 'p1:hand' for c in keep)
    assert all(s.state.cards[c].zone == 'p1:exile' for c in top[3:])
    colossi = [c for c in s.state.cards.values() if c.owner == 'p1' and c.name == 'Darksteel Colossus']
    assert len(colossi) == 1 and colossi[0].zone == ('p1:exile' if route == 'exile' else 'p1:library')
    assert not s.state.rules.decision
    roundtrip(s)


@pytest.mark.parametrize('command', [False, True])
def test_moonlight_original_paid_commander_replacement_is_chosen_before_life_and_hand_move(cards, command):
    from tests.test_rules_refused_look import stack_library

    s = game(cards)
    top = stack_library(s, ['Commander Eesha', 'Forest', 'Grizzly Bears', 'Island', 'Mountain'])
    act(s, 'p1', type='set_commander', card_id=top[0])
    cast(s, 'Moonlight Bargain')
    choose(s, [top[0]])
    d = s.state.rules.decision
    assert d.resume['step'] == 'life_command86' and s.state.players['p1'].life == 40
    assert s.state.cards[top[0]].zone == 'p1:library'
    choose(s, ['yes' if command else 'no'])
    assert s.state.players['p1'].life == 38
    assert s.state.cards[top[0]].zone == ('p1:command' if command else 'p1:hand')
    assert all(s.state.cards[c].zone == 'p1:graveyard' for c in top[1:])
    roundtrip(s)


@pytest.mark.parametrize('madness', [False, True])
def test_sirocco_madness_competes_with_rest_in_peace_before_any_life_payment(cards, madness):
    s = game(cards)
    put(s, 'Rest in Peace', 'battlefield', 'p3')
    paid = put(s, 'Opt', 'hand', 'p2')
    discarded = put(s, 'Obsessive Search', 'hand', 'p2')
    act(s, 'p2', type='add_mana', player='p2', mana={'U': 1})
    cast(s, 'Sirocco', ['p2'])
    choose(s, [paid.id])
    d = s.state.rules.decision
    assert d.resume['step'] == 'life_route86' and s.state.players['p2'].life == 40
    assert s.state.cards[paid.id].zone == s.state.cards[discarded.id].zone == 'p2:hand'
    answer = next(o.id for o in d.options if ('Madness' in o.label) == madness)
    choose(s, [answer])
    assert s.state.players['p2'].life == 36
    assert s.state.cards[paid.id].zone == 'p2:hand'
    assert s.state.cards[discarded.id].zone == 'p2:exile'
    if madness:
        assert s.state.rules.decision.resume['step'] == 'suspend_cast'
        assert 'Madness' in s.state.rules.decision.prompt
        hand_before = len(s.state.zones['p2:hand'])
        choose(s, ['yes'])
        assert len(s.state.zones['p2:hand']) == hand_before + 1
        assert s.state.cards[discarded.id].zone == 'p2:exile'
    else:
        assert not s.state.rules.decision and discarded.id not in s.state.rules.free_casts
    roundtrip(s)


@pytest.mark.parametrize('mode', ['moonlight', 'sirocco'])
def test_true_cold_original_card_life_packet_waits_for_replacement_then_completes_native_result(cards, tmp_path, mode):
    import os
    import subprocess
    import sys

    import app
    from tests.test_rules_refused_look import stack_library

    s = game(cards)
    put(s, 'Rest in Peace', 'battlefield', 'p3')
    if mode == 'moonlight':
        top = stack_library(s, ['Forest', 'Grizzly Bears', 'Darksteel Colossus', 'Island', 'Mountain'])
        keep, moved = top[:2], top[2]
        cast(s, 'Moonlight Bargain')
        choose(s, keep)
    else:
        keep = [put(s, 'Opt', 'hand', 'p2').id]
        moved = put(s, 'Obsessive Search', 'hand', 'p2').id
        act(s, 'p2', type='add_mana', player='p2', mana={'U': 1})
        cast(s, 'Sirocco', ['p2'])
        choose(s, keep)
    assert s.state.rules.decision.resume['step'] == 'life_route86'
    assert all(p.life == 40 for p in s.state.players.values())
    saved = tmp_path / 'life86.json'
    saved.write_text(s.state.model_dump_json())
    backend = Path(app.__file__).resolve().parents[1]
    code = r'''
import sys,json
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
mode,moved=sys.argv[3:5];keep=json.loads(sys.argv[5])
payer='p1' if mode=='moonlight' else 'p2'
d=s.state.rules.decision
assert d and d.resume['step']=='life_route86' and s.state.players[payer].life==40
answer=next(o.id for o in d.options if ('library:shuffle' if mode=='moonlight' else 'Madness') in o.label)
act(s,d.player,type='choose',decision_id=d.id,option_ids=[answer]);settle(s)
assert s.state.players[payer].life==36
assert all(s.state.cards[c].zone==payer+':hand' for c in keep)
if mode=='moonlight':
 assert any(c.owner=='p1' and c.name=='Darksteel Colossus' and c.zone=='p1:library' for c in s.state.cards.values())
 assert not s.state.rules.decision
else:
 assert s.state.cards[moved].zone=='p2:exile'
 d=s.state.rules.decision
 assert d and d.resume['step']=='suspend_cast' and 'Madness' in d.prompt
 before=len(s.state.zones['p2:hand'])
 act(s,d.player,type='choose',decision_id=d.id,option_ids=['yes']);settle(s)
 assert len(s.state.zones['p2:hand'])==before+1
 assert s.state.cards[moved].zone=='p2:exile'
roundtrip(s)
repo.close()
'''
    result = subprocess.run([sys.executable, '-c', code, str(saved), str(cards.db_path), mode, moved, json.dumps(keep)],
                            cwd=backend, env={**os.environ, 'PYTHONPATH': str(backend) + os.pathsep + os.environ.get('PYTHONPATH', '')},
                            capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stdout + result.stderr


def test_moonlight_positive_locked_life_and_aggregate_overpayment_reject_atomically(cards):
    from app.game.errors import ActionError
    from tests.test_rules_refused_look import stack_library

    s = game(cards)
    put(s, 'Platinum Emperion', 'battlefield')
    top = stack_library(s, ['Forest', 'Grizzly Bears', 'Lightning Bolt', 'Island', 'Mountain'])
    cast(s, 'Moonlight Bargain')
    before = s.state.model_dump(mode='json')
    with pytest.raises(ActionError):
        choose(s, [top[0]])
    assert s.state.model_dump(mode='json') == before
    choose(s, [])
    assert s.state.players['p1'].life == 40
    assert all(s.state.cards[c].zone == 'p1:graveyard' for c in top)
    roundtrip(s)


def test_sirocco_aggregate_four_life_per_card_cannot_exceed_original_payer_life(cards):
    from app.game.errors import ActionError

    s = game(cards)
    act(s, 'p2', type='set_life', player='p2', value=6)
    a = put(s, 'Opt', 'hand', 'p2')
    b = put(s, 'Counterspell', 'hand', 'p2')
    cast(s, 'Sirocco', ['p2'])
    before = s.state.model_dump(mode='json')
    with pytest.raises(ActionError):
        choose(s, [a.id, b.id])
    assert s.state.model_dump(mode='json') == before
    choose(s, [a.id])
    assert s.state.players['p2'].life == 2
    assert s.state.cards[a.id].zone == 'p2:hand' and s.state.cards[b.id].zone == 'p2:graveyard'
    roundtrip(s)


def test_sirocco_real_tamiyo_discard_ban_leaves_unpaid_blue_card_and_does_not_create_madness_trigger(cards):
    s = game(cards)
    tamiyo = put(s, 'Tamiyo, Collector of Tales', 'battlefield', 'p2')
    act(s, 'p2', type='counter', card_ids=[tamiyo.id], kind='loyalty', delta=5)
    blue = put(s, 'Obsessive Search', 'hand', 'p2')
    cast(s, 'Sirocco', ['p2'])
    choose(s, [])
    assert s.state.players['p2'].life == 40 and s.state.cards[blue.id].zone == 'p2:hand'
    assert not s.state.rules.decision and blue.id not in s.state.rules.free_casts
    roundtrip(s)


def test_sirocco_self_target_still_reveals_entire_hand_to_every_opponent(cards):
    from app.game.visibility import ALL

    s = game(cards)
    blue = put(s, 'Opt', 'hand')
    red = put(s, 'Lightning Bolt', 'hand')
    cast(s, 'Sirocco', ['p1'])
    assert s.state.rules.decision.player == 'p1'
    assert ALL in s.state.cards[blue.id].revealed_to and ALL in s.state.cards[red.id].revealed_to
    choose(s, [blue.id])
    assert s.state.players['p1'].life == 36
    assert s.state.cards[blue.id].zone == s.state.cards[red.id].zone == 'p1:hand'
    assert ALL not in s.state.cards[blue.id].revealed_to and ALL not in s.state.cards[red.id].revealed_to
    roundtrip(s)


@pytest.mark.parametrize('replacement', ['graveyard', 'rest_in_peace', 'madness'])
def test_sirocco_actual_waste_not_sees_exactly_one_discard_even_when_replaced(cards, replacement):
    s = game(cards)
    put(s, 'Waste Not', 'battlefield')
    if replacement == 'rest_in_peace':
        put(s, 'Rest in Peace', 'battlefield', 'p3')
    blue = put(s, 'Opt' if replacement == 'graveyard' else 'Obsessive Search', 'hand', 'p2')
    cast(s, 'Sirocco', ['p2'])
    before = len(s.state.zones['p1:hand'])
    choose(s, [])
    if replacement == 'rest_in_peace':
        d = s.state.rules.decision
        assert d.resume['step'] == 'life_route86'
        choose(s, [next(o.id for o in d.options if 'Rest in Peace' in o.label)])
    if replacement == 'madness':
        assert 'Madness' in s.state.rules.decision.prompt
        choose(s, ['no'])
    assert len(s.state.zones['p1:hand']) == before + 1
    assert s.state.cards[blue.id].zone == ('p2:exile' if replacement == 'rest_in_peace' else 'p2:graveyard')
    assert s.state.players['p2'].life == 40
    assert not s.state.rules.decision
    roundtrip(s)

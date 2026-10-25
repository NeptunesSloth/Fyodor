"""Actual library packets, simultaneous entries and original saved choices."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from app.rules import alt_costs, coverage
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, deck, enable
from tests.test_rules_bandmate_references import wait_priority
from tests.test_rules_designations import put
from tests.test_rules_wave30m_durations import to_phase

DATA = json.loads((Path(__file__).parent / 'fixtures/library_packets101_cards.json').read_text())
PRIMARY = ['Auspicious Starrix', 'Illuna, Apex of Wishes', 'Empty the Laboratory', 'Aurora Awakener', 'Demonlord Belzenlok', 'Venture Forth', 'Improvisation Capstone']


@pytest.fixture
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(DATA):
        extra = {k: v for k, v in c.items() if k not in {'name', 'set_code', 'number', 'id'}}
        base[c['name']] = card(c['name'], set_code='lp101', number=str(i), **extra)
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards):
    names = [c['name'] for c in DATA]
    mine = deck(cards, 'Krenko, Mob Boss', [(2, n) for n in names] + [(60, 'Forest')])
    other = deck(cards, 'Atraxa, Praetors\' Voice', [(30, 'Island')])
    s = GameSession(enable(new_game([PlayerSetup('Alice', cards=mine), PlayerSetup('Bob', cards=other)], shuffle=False)), cards=cards)
    to_phase(s, 'main1', 1)
    act(s, 'p1', type='add_mana', player='p1', mana={c: 50 for c in ['C', 'W', 'U', 'B', 'R', 'G']})
    return s


def advance(s, stop=None):
    for _ in range(120):
        d = s.state.rules.decision
        if d is not None:
            if stop and stop(d):
                return
            options = [o.id for o in d.options]
            preferred = next((v for v in ['no', 'decline', 'done', 'over'] if v in options), None)
            chosen = [preferred] if preferred is not None and d.max_choices else options[:d.min_choices]
            if d.min_choices == 0:
                chosen = []
            act(s, d.player, type='choose', decision_id=d.id, option_ids=chosen)
        elif s.state.zones.get('stack'):
            act(s, s.state.rules.priority, type='pass_priority')
        else:
            return
    raise AssertionError('Resolution did not settle')


def top(s, names):
    ids = [put(s, n, 'hand').id for n in names]
    for cid in reversed(ids):
        act(s, 'p1', type='move', card_ids=[cid], to={'player': 'p1', 'zone': 'library'}, position='top')
    return ids


def cast(s, name, **kwargs):
    source = put(s, name, 'hand')
    wait_priority(s, 'p1')
    act(s, 'p1', type='cast_spell', card_id=source.id, sources=[], **kwargs)
    return source


def mutate(s, name, host, *, under=False, stop=None):
    source = put(s, name, 'hand')
    wait_priority(s, 'p1')
    ch = Plan.view(s.state, 'p1', s.cards).ch(source)
    offer = next(o for o in alt_costs.offers(s.state, 'p1', source, ch, s.cards) if o.tag == 'mutate')
    act(s, 'p1', type='cast_spell', card_id=source.id, alt_cost=offer.key, targets=[host.id], sources=[])
    advance(s, stop=lambda d: d.resume.get('step') == 'mutate_choice')
    d = s.state.rules.decision
    assert d is not None
    act(s, d.player, type='choose', decision_id=d.id, option_ids=['under' if under else 'over'])
    advance(s, stop=stop)
    return s.state.cards[host.id]


def cold(s, tmp_path, extra, code):
    path = tmp_path / 'saved101.json'
    path.write_text(s.state.model_dump_json())
    body = '''import json,sys
from pathlib import Path
from app.cards.repository import CardRepository
from app.cards.images import ImageStore
from app.game.session import GameSession
from app.game.state import GameState
from tests.game_helpers import act
from tests.test_rules_library_packets101 import advance
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
extra=json.loads(sys.argv[3])
''' + code + '\nrepo.close()\n'
    r = subprocess.run([sys.executable, '-c', body, str(path), str(s.cards.db_path), json.dumps(extra)], capture_output=True, text=True, timeout=90)
    assert r.returncode == 0, r.stdout + r.stderr


@pytest.mark.parametrize('name', PRIMARY)
def test_whole_canonical_coverage101(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


def test_actual_starrix_mutations_count_original_history_and_leave_nonpermanents_exiled(cards):
    s = setup(cards)
    host = put(s, 'Grizzly Bears', 'battlefield')
    first = top(s, ['Lightning Bolt', 'Island', 'Hill Giant'])
    host = mutate(s, 'Auspicious Starrix', host)
    assert s.state.cards[first[0]].zone == 'p1:exile'
    assert s.state.cards[first[1]].zone == 'p1:battlefield'
    assert s.state.cards[first[2]].zone == 'p1:library'
    second = top(s, ['Lightning Bolt', 'Forest', 'Island', 'Hill Giant'])
    mutate(s, 'Cloudpiercer', host, under=True)
    assert s.state.cards[second[0]].zone == 'p1:exile'
    assert all(s.state.cards[c].zone == 'p1:battlefield' for c in second[1:3])
    assert s.state.cards[second[3]].zone == 'p1:library'


@pytest.mark.parametrize('destination', ['hand', 'battlefield'])
def test_actual_illuna_forced_destination_and_land_exclusion(cards, destination):
    s = setup(cards)
    host = put(s, 'Grizzly Bears', 'battlefield')
    ids = top(s, ['Forest', 'Lightning Bolt', 'Hill Giant', 'Island'])
    mutate(s, 'Illuna, Apex of Wishes', host, stop=lambda d: d.resume.get('step') == 'packet_destination101')
    d = s.state.rules.decision
    assert d is not None
    assert all(s.state.cards[c].zone == 'p1:exile' for c in ids[:3])
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[destination])
    advance(s)
    assert s.state.cards[ids[2]].zone == 'p1:' + destination
    assert s.state.cards[ids[0]].zone == 'p1:exile' and s.state.cards[ids[1]].zone == 'p1:exile'
    assert s.state.cards[ids[3]].zone == 'p1:library'


def test_empty_lab_actual_paid_x_zombies_enter_simultaneously(cards):
    s = setup(cards)
    old = [c.id for c in s.state.cards.values() if c.owner == 'p1' and c.name == 'Walking Corpse'][:2]
    act(s, 'p1', type='move', card_ids=old, to={'player': 'p1', 'zone': 'battlefield'})
    ids = top(s, ['Lightning Bolt', 'Champion of the Perished', 'Island', 'Diregraf Ghoul', 'Forest'])
    source = cast(s, 'Empty the Laboratory', x_value=2)
    advance(s)
    assert all(s.state.cards[c].zone == 'p1:graveyard' for c in old)
    assert all(s.state.cards[c].zone == 'p1:battlefield' for c in [ids[1], ids[3]])
    assert s.state.cards[ids[1]].counters.get('+1/+1') == 1
    assert s.state.cards[ids[3]].tapped
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    assert s.state.zones['p1:library'][-2:] != ids[:2]


def test_aurora_locks_colors_before_new_permanents_enter_and_optional_pick(cards):
    s = setup(cards)
    put(s, 'Walking Corpse', 'battlefield')
    ids = top(s, ['Lightning Bolt', 'Forest', 'Hill Giant', 'Demonic Vigor'])
    cast(s, 'Aurora Awakener')
    advance(s, stop=lambda d: d.resume.get('step') == 'pick_looked')
    d = s.state.rules.decision
    assert d is not None and {o.id for o in d.options} == {ids[1], ids[2]}
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[ids[2]])
    advance(s)
    assert s.state.cards[ids[2]].zone == 'p1:battlefield'
    assert s.state.zones['p1:library'][-2:] and s.state.zones['p1:library'][0] == ids[3]


def test_true_cold_illuna_original_exile_destination(cards, tmp_path):
    s = setup(cards)
    host = put(s, 'Grizzly Bears', 'battlefield')
    ids = top(s, ['Forest', 'Hill Giant', 'Island'])
    mutate(s, 'Illuna, Apex of Wishes', host, stop=lambda d: d.resume.get('step') == 'packet_destination101')
    cold(s, tmp_path, ids, '''d=s.state.rules.decision
act(s,d.player,type='choose',decision_id=d.id,option_ids=['hand']);advance(s)
assert s.state.cards[extra[0]].zone=='p1:exile'
assert s.state.cards[extra[1]].zone=='p1:hand'
assert s.state.cards[extra[2]].zone=='p1:library'
''')


def test_belzenlok_native_repeats_and_stops_low_mana_value_then_one_damage_event(cards):
    s = setup(cards)
    ids = top(s, ['Forest', 'Aurora Awakener', 'Island', 'Hill Giant', 'Lightning Bolt', 'Walking Corpse'])
    source = cast(s, 'Demonlord Belzenlok')
    advance(s)
    assert all(s.state.cards[cid].zone == 'p1:hand' for cid in [ids[1], ids[3], ids[4]])
    assert all(s.state.cards[cid].zone == 'p1:exile' for cid in [ids[0], ids[2]])
    assert s.state.cards[ids[5]].zone == 'p1:library'
    assert s.state.players['p1'].life == 37
    from app.rules import history
    damages = [f for f in history.log_for(Plan.view(s.state, 'p1', cards)).facts if f.kind == 'damage' and f.object_id == Plan.view(s.state, 'p1', cards).oid(source)]
    assert len(damages) == 1 and damages[0].amount == 3


def test_venture_forth_actual_self_exile_and_printed_suspend_registration(cards):
    s = setup(cards)
    ids = top(s, ['Lightning Bolt', 'Hill Giant', 'Island', 'Walking Corpse'])
    source = cast(s, 'Venture Forth')
    advance(s)
    assert s.state.cards[ids[2]].zone == 'p1:battlefield'
    assert s.state.cards[ids[0]].zone == 'p1:library' and s.state.cards[ids[1]].zone == 'p1:library'
    assert s.state.zones['p1:library'][0] == ids[3]
    assert s.state.cards[source.id].zone == 'p1:exile'
    assert s.state.cards[source.id].counters.get('time') == 3
    assert source.id in s.state.rules.suspended


def test_capstone_native_total_mana_value_and_multiple_free_creature_casts(cards):
    s = setup(cards)
    ids = top(s, ['Forest', 'Grizzly Bears', 'Walking Corpse', 'Hill Giant'])
    source = cast(s, 'Improvisation Capstone')
    advance(s, stop=lambda d: d.resume.get('step') == 'free_cast_pick')
    d = s.state.rules.decision
    assert d is not None and {o.card_id for o in d.options if o.card_id} == set(ids[1:3])
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[ids[1]])
    advance(s, stop=lambda d: d.resume.get('step') == 'free_cast_pick')
    d = s.state.rules.decision
    assert d is not None and any(o.card_id == ids[2] for o in d.options)
    assert s.state.cards[ids[1]].zone == 'stack' and s.state.cards[source.id].zone == 'stack'
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[ids[2]])
    advance(s)
    assert all(s.state.cards[c].zone == 'p1:battlefield' for c in ids[1:3])
    assert s.state.cards[ids[0]].zone == 'p1:exile'
    assert s.state.cards[ids[3]].zone == 'p1:library'


def test_empty_lab_uses_actual_sacrifices_when_fewer_than_announced_x(cards):
    s = setup(cards)
    old = put(s, 'Walking Corpse', 'battlefield')
    ids = top(s, ['Lightning Bolt', 'Champion of the Perished', 'Island', 'Diregraf Ghoul'])
    cast(s, 'Empty the Laboratory', x_value=2)
    advance(s)
    assert s.state.cards[old.id].zone == 'p1:graveyard'
    assert s.state.cards[ids[1]].zone == 'p1:battlefield'
    assert s.state.cards[ids[3]].zone == 'p1:library'
    assert s.state.zones['p1:library'][0] == ids[2]


def test_genuine_cold_aurora_original_revealed_choices_and_locked_count(cards, tmp_path):
    s = setup(cards)
    put(s, 'Walking Corpse', 'battlefield')
    ids = top(s, ['Lightning Bolt', 'Forest', 'Hill Giant', 'Demonic Vigor'])
    cast(s, 'Aurora Awakener')
    advance(s, stop=lambda d: d.resume.get('step') == 'pick_looked')
    cold(s, tmp_path, ids, '''d=s.state.rules.decision
assert {o.id for o in d.options}==set(extra[1:3])
act(s,d.player,type='choose',decision_id=d.id,option_ids=[extra[2]]);advance(s)
assert s.state.cards[extra[2]].zone=='p1:battlefield'
assert s.state.zones['p1:library'][0]==extra[3]
''')


def test_genuine_cold_capstone_remembers_first_cast_and_offers_remaining_original(cards, tmp_path):
    s = setup(cards)
    ids = top(s, ['Forest', 'Grizzly Bears', 'Walking Corpse', 'Hill Giant'])
    cast(s, 'Improvisation Capstone')
    advance(s, stop=lambda d: d.resume.get('step') == 'free_cast_pick')
    d = s.state.rules.decision
    assert d is not None
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[ids[1]])
    advance(s, stop=lambda d: d.resume.get('step') == 'free_cast_pick')
    cold(s, tmp_path, ids, '''d=s.state.rules.decision
assert {o.card_id for o in d.options if o.card_id}=={extra[2]}
assert s.state.cards[extra[1]].zone=='stack'
act(s,d.player,type='choose',decision_id=d.id,option_ids=[extra[2]]);advance(s)
assert all(s.state.cards[c].zone=='p1:battlefield' for c in extra[1:3])
assert s.state.cards[extra[0]].zone=='p1:exile'
assert s.state.cards[extra[3]].zone=='p1:library'
''')


@pytest.mark.parametrize('answer', ['yes', 'no'])
def test_belzenlok_native_commander_to_hand_replacement101(cards, answer):
    s = setup(cards)
    ids = top(s, ['Forest', 'Krenko, Mob Boss', 'Lightning Bolt', 'Hill Giant'])
    cast(s, 'Demonlord Belzenlok')
    advance(s, stop=lambda d: any('command' in o.label.lower() for o in d.options))
    d = s.state.rules.decision
    assert d is not None, 'Expected native903.9b hand replacement choice'
    assert s.state.players['p1'].life == 40
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[answer])
    advance(s)
    assert s.state.cards[ids[1]].zone == 'p1:' + ('command' if answer == 'yes' else 'hand')
    assert s.state.players['p1'].life == (39 if answer == 'yes' else 38)
    assert s.state.cards[ids[3]].zone == 'p1:library'


@pytest.mark.parametrize('answer', ['yes', 'no'])
def test_genuine_cold_belzenlok_commander_before_hand_then_remaining_packet101(cards, tmp_path, answer):
    s = setup(cards)
    ids = top(s, ['Forest', 'Krenko, Mob Boss', 'Lightning Bolt', 'Hill Giant'])
    cast(s, 'Demonlord Belzenlok')
    advance(s, stop=lambda d: d.resume.get('step') == 'commander_first')
    assert s.state.rules.decision is not None
    assert s.state.players['p1'].life == 40 and s.state.cards[ids[2]].zone == 'p1:library'
    cold(s, tmp_path, {'ids': ids, 'answer': answer}, '''d=s.state.rules.decision
assert d.resume['step']=='commander_first'
act(s,d.player,type='choose',decision_id=d.id,option_ids=[extra['answer']]);advance(s)
ids=extra['ids']
assert s.state.cards[ids[1]].zone=='p1:'+('command' if extra['answer']=='yes' else 'hand')
assert s.state.cards[ids[2]].zone=='p1:hand'
assert s.state.cards[ids[3]].zone=='p1:library'
assert s.state.players['p1'].life==(39 if extra['answer']=='yes' else 38)
''')

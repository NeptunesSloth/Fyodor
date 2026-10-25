"""Actual mandatory upkeep attempts, partial outcomes, and original controller choices."""
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

DATA = json.loads((Path(__file__).parent / 'fixtures/upkeep_sacrifice101_cards.json').read_text())
NAMES = ['Doom Foretold', 'Infernal Denizen', 'Cocoon']


@pytest.fixture
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(DATA):
        base[c['name']] = card(c['name'], set_code='u101', number=str(i), **{k: v for k, v in c.items() if k not in ('name', 'set_code', 'number')})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards):
    names = [*dict.fromkeys(c['name'] for c in DATA if c['name'] not in ('Krenko, Mob Boss', "Atraxa, Praetors' Voice")), 'Swamp', 'Swamp']
    s = table(cards, names, names, names)
    to_phase(s, 'main1', 1)
    return s


def put(s, name, pid='p1', zone='battlefield'):
    found = [c for c in s.state.cards.values() if c.owner == pid and c.name == name]
    c = next((c for c in found if c.zone != f'{pid}:{zone}'), found[0])
    act(s, pid, type='move', card_ids=[c.id], to={'player': pid, 'zone': zone})
    return s.state.cards[c.id]


def cast(s, name, targets=(), mana=None):
    c = put(s, name, zone='hand')
    wait_priority(s, 'p1')
    act(s, 'p1', type='add_mana', player='p1', mana=mana or {'C': 10, 'W': 4, 'U': 4, 'B': 4, 'R': 4, 'G': 4})
    act(s, 'p1', type='cast_spell', card_id=c.id, sources=[], targets=list(targets))
    settle(s)
    return c


def resolve_choices(s, chosen=()):
    for _ in range(30):
        settle(s)
        d = s.state.rules.decision
        if d is None:
            return
        ids = [o.id for o in d.options]
        selected = next(([c] for c in chosen if c in ids), ids[:d.min_choices])
        pick(s, selected)
    raise AssertionError('never resolved')


@pytest.mark.parametrize('name', NAMES)
def test_whole_cards101(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


@pytest.mark.parametrize('rip', [False, True])
def test_doom_mandatory_sacrifice_actual_outcome_not_graveyard_destination(cards, rip):
    s = setup(cards)
    source = cast(s, 'Doom Foretold')
    bear = put(s, 'Grizzly Bears', 'p2')
    if rip:
        put(s, 'Rest in Peace')
    before = (s.state.players['p1'].life, s.state.players['p2'].life, len(s.state.zones['p1:hand']))
    to_phase(s, 'upkeep', 2)
    resolve_choices(s)
    assert s.state.cards[bear.id].zone == ('p2:exile' if rip else 'p2:graveyard')
    assert s.state.cards[source.id].zone == 'p1:battlefield'
    assert (s.state.players['p1'].life, s.state.players['p2'].life, len(s.state.zones['p1:hand'])) == before
    roundtrip(s)


@pytest.mark.parametrize('protected', [False, True])
def test_doom_impossible_sacrifice_keeps_all_consequences_and_original_payer(cards, protected):
    s = setup(cards)
    source = cast(s, 'Doom Foretold')
    if protected:
        sigarda = put(s, 'Sigarda, Host of Herons', 'p2')
    before = {p: s.state.players[p].life for p in ['p1', 'p2']}
    hand = len(s.state.zones['p1:hand'])
    to_phase(s, 'upkeep', 2)
    resolve_choices(s)
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    assert s.state.players['p1'].life == before['p1'] + 2 and s.state.players['p2'].life == before['p2'] - 2
    assert len(s.state.zones['p1:hand']) == hand + 1
    knights = [c for c in s.state.cards.values() if c.zone == 'p1:battlefield' and c.name == 'Knight']
    assert len(knights) == 1 and 'vigilance' in Plan.view(s.state, 'p1', cards).ch(knights[0]).keywords
    if protected:
        assert s.state.cards[sigarda.id].zone == 'p2:battlefield'
    roundtrip(s)


@pytest.mark.parametrize('number', [0, 1, 2])
def test_denizen_mandatory_partial_swamps_and_opponents_optional_choice(cards, number):
    s = setup(cards)
    source = put(s, 'Infernal Denizen')
    bear = put(s, 'Grizzly Bears')
    swamps = [put(s, 'Swamp') for _ in range(number)]
    to_phase(s, 'upkeep', 4)
    settle(s)
    if number == 2:
        assert s.state.rules.decision is None
        assert not s.state.cards[source.id].tapped
        assert s.state.cards[bear.id].controller == 'p1'
    else:
        assert s.state.cards[source.id].tapped
        assert s.state.rules.decision.player == 'p1'
        pick(s, ['p2'])
        settle(s)
        assert s.state.rules.decision.player == 'p2'
        pick(s, [bear.id])
        settle(s)
        assert s.state.cards[bear.id].controller == 'p2'
    assert all(s.state.cards[c.id].zone == 'p1:graveyard' for c in swamps)
    roundtrip(s)


@pytest.mark.parametrize('remaining', [0, 1])
def test_cocoon_actual_counter_removed_and_original_host_flying_after_aura_leaves(cards, remaining):
    s = setup(cards)
    bear = put(s, 'Grizzly Bears')
    source = cast(s, 'Cocoon', [bear.id], {'G': 1})
    assert s.state.cards[source.id].counters['pupa'] == 3 and s.state.cards[bear.id].tapped
    act(s, 'p1', type='set_counter', card_id=source.id, kind='pupa', value=remaining)
    to_phase(s, 'upkeep', 4)
    resolve_choices(s)
    ch = Plan.view(s.state, 'p1', cards).ch(s.state.cards[bear.id])
    if remaining:
        assert s.state.cards[source.id].zone == 'p1:battlefield' and s.state.cards[source.id].counters.get('pupa', 0) == 0
        assert 'flying' not in ch.keywords
    else:
        assert s.state.cards[source.id].zone == 'p1:graveyard'
        assert s.state.cards[bear.id].counters.get('+1/+1') == 1 and 'flying' in ch.keywords
    roundtrip(s)


def cold(s, tmp_path, body):
    import subprocess
    import sys

    saved = tmp_path / 'upkeep101.json'
    saved.write_text(s.state.model_dump_json())
    code = '''import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.game_helpers import act
from tests.test_rules_designations import pick,roundtrip
from tests.test_rules_library_placements import settle
from tests.test_rules_upkeep_sacrifice101 import cast,resolve_choices
from tests.test_rules_wave30m_durations import to_phase
from app.rules.plan import Plan
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
'''+body+'\nroundtrip(s);repo.close()\n'
    result = subprocess.run([sys.executable, '-c', code, str(saved), str(s.cards.db_path)],
                            cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr


def test_doom_actual_response_control_change_and_cold_original_payer(cards, tmp_path):
    s = setup(cards)
    source = cast(s, 'Doom Foretold')
    put(s, 'Sigarda, Host of Herons', 'p2')
    to_phase(s, 'upkeep', 2)
    word = put(s, 'Word of Seizing', 'p3', 'hand')
    wait_priority(s, 'p3')
    act(s, 'p3', type='add_mana', player='p3', mana={'C': 3, 'R': 2})
    act(s, 'p3', type='cast_spell', card_id=word.id, sources=[], targets=[source.id])
    while len(s.state.zones.get('stack', [])) > 1:
        assert s.state.rules.decision is None
        act(s, s.state.rules.priority, type='pass_priority')
    assert s.state.cards[source.id].controller == 'p3'
    assert s.state.zones.get('stack')
    hand = len(s.state.zones['p1:hand'])
    cold(s, tmp_path, f'''resolve_choices(s)
assert s.state.players['p1'].life==42 and s.state.players['p2'].life==38
assert len(s.state.zones['p1:hand'])=={hand + 1}
assert s.state.cards[{source.id!r}].zone.endswith(':battlefield') and s.state.cards[{source.id!r}].controller=='p3'
assert any(c.name=='Knight' and c.controller=='p1' and c.zone.endswith(':battlefield') for c in s.state.cards.values())''')


def test_denizen_cold_choice_source_duration_ends_after_actual_murder(cards, tmp_path):
    s = setup(cards)
    source = put(s, 'Infernal Denizen')
    bear = put(s, 'Grizzly Bears')
    to_phase(s, 'upkeep', 4)
    settle(s)
    pick(s, ['p2'])
    settle(s)
    assert s.state.rules.decision.player == 'p2'
    cold(s, tmp_path, f'''pick(s,[{bear.id!r}]);settle(s)
assert s.state.cards[{bear.id!r}].controller=='p2'
cast(s,'Murder',[{source.id!r}])
assert s.state.cards[{source.id!r}].zone=='p1:graveyard'
assert s.state.cards[{bear.id!r}].controller=='p1' ''')


def test_denizen_optional_opponent_may_decline(cards):
    s = setup(cards)
    source = put(s, 'Infernal Denizen')
    to_phase(s, 'upkeep', 4)
    settle(s)
    pick(s, ['p3'])
    settle(s)
    assert s.state.rules.decision.player == 'p3'
    pick(s, [])
    settle(s)
    assert s.state.cards[source.id].controller == 'p1'
    roundtrip(s)


def test_denizen_two_native_sacrifices_replaced_into_exile_still_satisfy(cards):
    s = setup(cards)
    source = put(s, 'Infernal Denizen')
    put(s, 'Rest in Peace')
    swamps = [put(s, 'Swamp'), put(s, 'Swamp')]
    to_phase(s, 'upkeep', 4)
    resolve_choices(s)
    assert all(s.state.cards[c.id].zone == 'p1:exile' for c in swamps)
    assert not s.state.cards[source.id].tapped and s.state.cards[source.id].controller == 'p1'
    roundtrip(s)


def test_cocoon_cold_original_host_flying_is_permanent(cards, tmp_path):
    s = setup(cards)
    bear = put(s, 'Grizzly Bears')
    source = cast(s, 'Cocoon', [bear.id], {'G': 1})
    act(s, 'p1', type='set_counter', card_id=source.id, kind='pupa', value=0)
    to_phase(s, 'upkeep', 4)
    cold(s, tmp_path, f'''resolve_choices(s)
assert s.state.cards[{source.id!r}].zone=='p1:graveyard'
assert s.state.cards[{bear.id!r}].counters.get('+1/+1')==1
to_phase(s,'upkeep',5)
assert 'flying' in Plan.view(s.state,'p1',repo).ch(s.state.cards[{bear.id!r}]).keywords''')


def test_cocoon_cannot_put_counters_still_gives_flying(cards):
    s = setup(cards)
    put(s, 'Solemnity')
    bear = put(s, 'Grizzly Bears')
    source = cast(s, 'Cocoon', [bear.id], {'G': 1})
    assert s.state.cards[source.id].counters.get('pupa', 0) == 0
    to_phase(s, 'upkeep', 4)
    resolve_choices(s)
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    assert s.state.cards[bear.id].counters.get('+1/+1', 0) == 0
    assert 'flying' in Plan.view(s.state, 'p1', cards).ch(s.state.cards[bear.id]).keywords
    roundtrip(s)

"""Native graveyard upkeep identity and intervening creature-count proofs."""
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
from tests.test_rules_declaration_requirements33 import start
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_look import settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_trigger_library_win53 import cast
from tests.test_rules_wave30m_durations import to_phase

NAME = 'Spreading Plague'
DATA = json.loads((Path(__file__).parent / 'fixtures/trigger_shared_colors61_cards.json').read_text())


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


NAMES = [c['name'] for c in DATA] + ['Raise the Alarm']


def setup(cards, preloads=()):
    s = table(cards, NAMES + ['Island'] * 8, NAMES, NAMES)
    start(s)
    act(s, 'p1', type='set_prefs', hold_priority=True)
    existing = [put(s, name, 'battlefield', pid) for name, pid in preloads]
    source = cast(s, NAME, {'C': 4, 'B': 1})
    assert all(c.zone.endswith(':battlefield') for c in existing)
    return s, source, existing


def pending(cards, preloads=(), name='Elvish Mystic', pool=None):
    from tests.test_rules_counter_event_comparisons50 import resolve_only

    s, source, existing = setup(cards, preloads)
    entering = cast(s, name, pool or {'G': 1}, resolve=False)
    resolve_only(s, entering)
    assert entering.zone == 'p1:battlefield'
    assert s.state.zones['stack']
    return s, source, existing, entering


def test_whole_canonical(cards):
    assert coverage.of_card_data(cards.resolve(NAME)).level == 'FULL'


def test_native_global_colors_self_exclusion_and_colorless(cards):
    s, source, old, entering = pending(cards, [('Grizzly Bears', 'p1'), ('Grizzly Bears', 'p2'), ('Ornithopter', 'p3')])
    settle(s)
    assert [c.zone for c in old] == ['p1:graveyard', 'p2:graveyard', 'p3:battlefield']
    assert entering.zone == source.zone == 'p1:battlefield'
    roundtrip(s)


def test_native_multicolor_entering_destroys_each_color_once(cards):
    s, source, old, entering = pending(cards, [('Grizzly Bears', 'p2'), ('Watchwolf', 'p3')],
                                       name='Watchwolf', pool={'G': 1, 'W': 1})
    settle(s)
    assert all(c.zone.endswith(':graveyard') for c in old)
    assert entering.zone == source.zone == 'p1:battlefield'
    roundtrip(s)


def test_native_colorless_entering_shares_no_color(cards):
    s, source, old, entering = pending(cards, [('Grizzly Bears', 'p2'), ('Ornithopter', 'p3')],
                                       name='Ornithopter', pool={'C': 0})
    settle(s)
    assert all(c.zone.endswith(':battlefield') for c in old)
    assert entering.zone == source.zone == 'p1:battlefield'
    roundtrip(s)


@pytest.mark.parametrize('mode', ['entering_dies', 'source_dies', 'entering_colorless', 'other_colorless'])
def test_native_response_current_colors_and_departure_lki(cards, mode):
    s, source, old, entering = pending(cards, [('Grizzly Bears', 'p2')])
    bear = old[0]
    if mode == 'entering_dies':
        cast(s, 'Lightning Bolt', {'R': 1}, [entering.id])
        assert entering.zone == 'p1:graveyard' and bear.zone == 'p2:graveyard'
    elif mode == 'source_dies':
        cast(s, 'Naturalize', {'C': 1, 'G': 1}, [source.id])
        assert source.zone == 'p1:graveyard' and bear.zone == 'p2:graveyard'
    else:
        cast(s, 'Moonlace', {'U': 1}, [(entering if mode == 'entering_colorless' else bear).id])
        assert entering.zone == 'p1:battlefield' and bear.zone == 'p2:battlefield'
    roundtrip(s)


def test_native_noncreature_entry_does_not_trigger(cards):
    s, source, old = setup(cards, [('Grizzly Bears', 'p2')])
    cast(s, 'Eldrazi Monument', {'C': 5})
    assert old[0].zone == 'p2:battlefield' and not s.state.zones.get('stack')
    roundtrip(s)


def test_native_indestructible_same_color_survives(cards):
    s, source, old = setup(cards, [('Grizzly Bears', 'p1'), ('Grizzly Bears', 'p2')])
    cast(s, 'Eldrazi Monument', {'C': 5})
    cast(s, 'Elvish Mystic', {'G': 1})
    assert old[0].zone == 'p1:battlefield' and old[1].zone == 'p2:graveyard'
    roundtrip(s)


def test_native_regeneration_shield_cannot_save_shared_creature(cards):
    from tests.test_rules_bandmate_references import mana, wait_priority

    s, source, old = setup(cards, [('River Boa', 'p1')])
    boa = old[0]
    wait_priority(s, 'p1')
    mana(s, G=1)
    act(s, 'p1', type='activate_ability', card_id=boa.id, ability=1, sources=[], targets=[])
    settle(s)
    assert s.state.rules.regen_shields
    cast(s, 'Elvish Mystic', {'G': 1})
    assert boa.zone == 'p1:graveyard'
    roundtrip(s)


def test_native_blinked_entering_successor_is_other_for_original_trigger(cards):
    s, source, old, entering = pending(cards)
    island = put(s, 'Island', 'battlefield')
    original = s.state.rules.object_id(entering.id)
    from tests.test_rules_bandmate_references import mana, wait_priority

    flicker = put(s, 'Ghostly Flicker', 'hand')
    wait_priority(s, 'p1')
    mana(s, C=2, U=1)
    act(s, 'p1', type='cast_spell', card_id=flicker.id, sources=[], targets=[entering.id, island.id], target_counts=[2])
    settle(s)
    assert s.state.rules.object_id(entering.id) != original
    assert entering.zone == 'p1:graveyard' and source.zone == 'p1:battlefield'
    roundtrip(s)


@pytest.mark.parametrize('mode', ['lki', 'colorless'])
def test_true_cold_native_current_or_last_known_colors(cards, tmp_path, mode):
    import subprocess
    import sys

    import app

    s, source, old, entering = pending(cards, [('Grizzly Bears', 'p2')])
    saved = tmp_path / 'plague61.json'
    saved.write_text(s.state.model_dump_json())
    code = r'''
import sys
from pathlib import Path
from app.cards.repository import CardRepository
from app.cards.images import ImageStore
from app.game.session import GameSession
from app.game.state import GameState
from tests.test_rules_trigger_library_win53 import cast
from tests.test_rules_designations import roundtrip
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
if sys.argv[5]=='lki':
    cast(s,'Lightning Bolt',{'R':1},[sys.argv[3]])
else:
    cast(s,'Moonlace',{'U':1},[sys.argv[3]])
assert s.state.cards[sys.argv[4]].zone==('p2:graveyard' if sys.argv[5]=='lki' else 'p2:battlefield')
roundtrip(s)
'''
    result = subprocess.run([sys.executable, '-c', code, str(saved), str(cards.db_path), entering.id, old[0].id, mode],
                            cwd=Path(app.__file__).resolve().parents[1], capture_output=True, text=True, timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr


def test_native_opponent_creature_entry_also_destroys_matching_creatures(cards):
    s, source, old = setup(cards, [('Grizzly Bears', 'p1')])
    to_phase(s, 'main1', turn=5)
    entering = cast(s, 'Elvish Mystic', {'G': 1}, pid='p2')
    assert entering.zone == 'p2:battlefield' and old[0].zone == 'p1:graveyard'
    assert source.zone == 'p1:battlefield'
    roundtrip(s)


def test_native_simultaneous_tokens_trigger_separately_and_use_ceased_token_lki(cards):
    s, source, old = setup(cards)
    before = len(s.state.rules.turn_log.entered)
    cast(s, 'Raise the Alarm', {'C': 1, 'W': 1})
    assert len(s.state.rules.turn_log.entered) == before + 2
    soldiers = [c for c in s.state.cards.values() if c.token and c.zone.endswith(':battlefield')]
    assert not soldiers and source.zone == 'p1:battlefield'
    assert s.state.rules.decision is None and not s.state.zones.get('stack')
    roundtrip(s)


@pytest.mark.parametrize('cold', [False, True])
def test_native_no_regeneration_still_allows_umbra_replacement_choice_and_resume(cards, tmp_path, cold):
    s, source, old = setup(cards, [('Grizzly Bears', 'p1')])
    bear = old[0]
    hyena = cast(s, 'Hyena Umbra', {'W': 1}, [bear.id])
    spider = cast(s, 'Spider Umbra', {'G': 1}, [bear.id])
    cast(s, 'Elvish Mystic', {'G': 1})
    d = s.state.rules.decision
    assert d is not None and 'destruction replacement' in d.prompt
    chosen = next(o.id for o in d.options if 'Hyena Umbra' in o.label)
    if not cold:
        act(s, d.player, type='choose', decision_id=d.id, option_ids=[chosen])
        settle(s)
        assert hyena.zone == 'p1:graveyard' and spider.zone == bear.zone == 'p1:battlefield'
        roundtrip(s)
        return
    import subprocess
    import sys

    import app

    saved = tmp_path / 'plague61-replace.json'
    saved.write_text(s.state.model_dump_json())
    code = r'''
import sys
from pathlib import Path
from app.cards.repository import CardRepository
from app.cards.images import ImageStore
from app.game.session import GameSession
from app.game.state import GameState
from tests.test_rules_library_look import settle
from tests.test_rules_designations import roundtrip
from tests.game_helpers import act
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
d=s.state.rules.decision
chosen=next(o.id for o in d.options if 'Hyena Umbra' in o.label)
act(s,d.player,type='choose',decision_id=d.id,option_ids=[chosen])
settle(s)
assert s.state.cards[sys.argv[3]].zone=='p1:graveyard'
assert s.state.cards[sys.argv[4]].zone==s.state.cards[sys.argv[5]].zone=='p1:battlefield'
assert s.state.rules.decision is None and not s.state.zones.get('stack')
roundtrip(s)
'''
    result = subprocess.run([sys.executable, '-c', code, str(saved), str(cards.db_path), hyena.id, spider.id, bear.id],
                            cwd=Path(app.__file__).resolve().parents[1], capture_output=True, text=True, timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr

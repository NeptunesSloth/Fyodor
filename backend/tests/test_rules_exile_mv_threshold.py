"""Cumulative exile thresholds reset per opponent; Dream's free casts retain normal timing."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana, wait_priority
from tests.test_rules_conditionals import settle
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

TASHA = "Tasha's Hideous Laughter"
DREAM = 'Dream Harvest'


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/exile_mv_threshold_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='emt', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards, name=DREAM, tops=(('Forest', 'Grizzly Bears', 'Fire // Ice'), ('Island', 'Emrakul, the Aeons Torn'))):
    s = table(cards, [name], tops[0], tops[1])
    selected = {}
    for pid, names in zip(['p2', 'p3'], tops, strict=True):
        selected[pid] = []
        for n in names:
            selected[pid].append(next(c.id for c in s.state.cards.values() if c.owner == pid and c.name == n and c.id not in selected[pid]))
        for cid in reversed(selected[pid]):
            act(s, pid, type='move', card_ids=[cid], to={'player': pid, 'zone': 'library'}, position='top')
    own = list(s.state.zones['p1:library'])
    source = put(s, name, 'hand')
    mana(s, C=10, U=3, B=3)
    act(s, 'p1', type='cast_spell', card_id=source.id)
    settle(s)
    return s, selected, own


@pytest.mark.parametrize('name', [TASHA, DREAM])
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


def test_dream_resets_threshold_and_split_sums_halves_and_leaves_own_library(cards):
    s, selected, own = setup(cards)
    assert all(s.state.cards[cid].zone == f'{pid}:exile' for pid, ids in selected.items() for cid in ids)
    assert list(s.state.zones['p1:library']) == own
    assert len(s.state.rules.permissions) == 5
    assert all(p.free and p.player == 'p1' and p.until == 'end_of_turn' for p in s.state.rules.permissions)
    roundtrip(s)


def test_tasha_empty_and_all_zero_libraries_do_not_draw_or_grant(cards):
    s, selected, _ = setup(cards, TASHA, (('Forest', 'Endless One'), ()))
    assert all(s.state.cards[c].zone.endswith(':exile') for c in selected['p2'])
    assert s.state.zones['p2:library'] == [] and s.state.zones['p3:library'] == []
    assert not s.state.rules.permissions
    assert s.state.players['p2'].life == 40
    roundtrip(s)


def test_tasha_total_twenty_resets_for_next_opponent(cards):
    s, selected, _ = setup(cards, TASHA, (('Emrakul, the Aeons Torn', 'Fire // Ice', 'Opt', 'Lightning Bolt'), ('Emrakul, the Aeons Torn', 'Fire // Ice', 'Opt', 'Lightning Bolt')))
    for pid, ids in selected.items():
        assert all(s.state.cards[c].zone == f'{pid}:exile' for c in ids[:3])
        assert s.state.cards[ids[3]].zone == f'{pid}:library'
    roundtrip(s)


def test_dream_native_cross_owner_cast_and_sorcery_timing(cards):
    s, selected, _ = setup(cards, tops=(('Grizzly Bears', 'Fire // Ice'), ('Emrakul, the Aeons Torn',)))
    bear = selected['p2'][0]
    wait_priority(s, 'p1')
    act(s, 'p1', type='cast_spell', card_id=bear, free=True)
    assert s.state.cards[bear].zone == 'stack'
    settle(s)
    assert s.state.cards[bear].zone == 'p1:battlefield' and s.state.cards[bear].owner == 'p2'
    to_phase(s, 'upkeep', turn=2)
    wait_priority(s, 'p1')
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=selected['p3'][0], free=True)
    assert not s.state.rules.permissions
    roundtrip(s)


def test_dream_land_is_exiled_and_permitted_but_cannot_be_played(cards):
    s, selected, _ = setup(cards)
    with pytest.raises(ActionError):
        act(s, 'p1', type='play_land', card_id=selected['p2'][0])
    roundtrip(s)


def test_dream_free_creature_still_cannot_cast_at_end_step(cards):
    s, selected, _ = setup(cards)
    to_phase(s, 'end', turn=1)
    wait_priority(s, 'p1')
    assert s.state.rules.permissions
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=selected['p2'][1], free=True)
    roundtrip(s)


def test_dream_original_exile_reference_excludes_returned_object(cards):
    s, selected, _ = setup(cards)
    cid = selected['p2'][1]
    act(s, 'p2', type='move', card_ids=[cid], to={'player': 'p2', 'zone': 'hand'})
    act(s, 'p2', type='move', card_ids=[cid], to={'player': 'p2', 'zone': 'exile'})
    wait_priority(s, 'p1')
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=cid, free=True)
    roundtrip(s)


def test_dream_saved_permission_survives_source_sorcery_departure(cards):
    from app.game.session import GameSession
    from app.game.state import GameState

    s, selected, _ = setup(cards)
    source = next(c for c in s.state.cards.values() if c.name == DREAM)
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'exile'})
    s = GameSession(GameState.model_validate_json(s.state.model_dump_json()), cards=cards)
    wait_priority(s, 'p1')
    act(s, 'p1', type='cast_spell', card_id=selected['p2'][1], free=True)
    settle(s)
    assert s.state.cards[selected['p2'][1]].zone == 'p1:battlefield'
    roundtrip(s)


def test_dream_mdfc_front_value_and_x_zero_count_toward_scan(cards):
    s, selected, _ = setup(cards, tops=(('Endless One', 'Valki, God of Lies // Tibalt, Cosmic Impostor', 'Grizzly Bears', 'Opt', 'Lightning Bolt'), ('Emrakul, the Aeons Torn',)))
    ids = selected['p2']
    assert all(s.state.cards[c].zone == 'p2:exile' for c in ids[:4])
    assert s.state.cards[ids[4]].zone == 'p2:library'
    wait_priority(s, 'p1')
    act(s, 'p1', type='cast_spell', card_id=ids[0], free=True, x_value=0)
    settle(s)
    assert s.state.cards[ids[0]].zone == 'p2:graveyard'
    roundtrip(s)


def test_dream_free_instant_normal_timing_and_no_mana_cost(cards):
    from tests.game_helpers import mana_pool

    s, selected, _ = setup(cards, tops=(('Lightning Bolt', 'Fire // Ice'), ('Emrakul, the Aeons Torn',)))
    to_phase(s, 'end', turn=1)
    wait_priority(s, 'p1')
    before = mana_pool(s)
    act(s, 'p1', type='cast_spell', card_id=selected['p2'][0], targets=['p3'], free=True)
    settle(s)
    assert s.state.players['p3'].life == 37
    assert s.state.cards[selected['p2'][0]].zone == 'p2:graveyard'
    assert mana_pool(s) == before
    roundtrip(s)


def test_dream_does_not_waive_mandatory_additional_cost(cards):
    s, selected, _ = setup(cards, tops=(('Fling', 'Fire // Ice'), ('Emrakul, the Aeons Torn',)))
    wait_priority(s, 'p1')
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=selected['p2'][0], targets=['p3'], free=True)
    assert s.state.cards[selected['p2'][0]].zone == 'p2:exile'
    roundtrip(s)


def test_dream_free_mdfc_can_cast_back_face_despite_small_front_value(cards):
    s, selected, _ = setup(cards, tops=(('Valki, God of Lies // Tibalt, Cosmic Impostor', 'Fire // Ice'), ('Emrakul, the Aeons Torn',)))
    wait_priority(s, 'p1')
    act(s, 'p1', type='cast_spell', card_id=selected['p2'][0], face=1, free=True)
    settle(s)
    tibalt = s.state.cards[selected['p2'][0]]
    assert tibalt.zone == 'p1:battlefield' and tibalt.face == 1 and tibalt.counters['loyalty'] == 5
    roundtrip(s)


def test_dream_cold_saved_permissions_use_native_cast_and_history(cards, tmp_path):
    import subprocess
    import sys

    s, selected, _ = setup(cards)
    saved = tmp_path / 'threshold.json'
    saved.write_text(s.state.model_dump_json())
    script = r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
saved, db, spell = sys.argv[1:]
repo = CardRepository(Path(db), ImageStore(Path(db).parent / 'images'))
s = GameSession(GameState.model_validate_json(Path(saved).read_text()), cards=repo)
s.perform('p1', {'type':'cast_spell','card_id':spell,'free':True})
for _ in range(60):
    if not s.state.zones.get('stack'): break
    s.perform(s.state.rules.priority, {'type':'pass_priority'})
else: raise AssertionError('did not resolve')
assert s.state.cards[spell].zone=='p1:battlefield'
assert s.state.cards[spell].owner=='p2'
assert s.history.rebuild().model_dump(mode='json')==s.state.model_dump(mode='json')
repo.close()
'''
    result = subprocess.run([sys.executable, '-c', script, str(saved), str(cards.db_path), selected['p2'][1]],
                            cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr


def test_dream_scans_past_one_hundred_zero_value_cards(cards):
    s, selected, _ = setup(cards, tops=((*(('Forest',) * 105), 'Emrakul, the Aeons Torn', 'Opt'), ('Emrakul, the Aeons Torn',)))
    ids = selected['p2']
    assert all(s.state.cards[c].zone == 'p2:exile' for c in ids[:-1])
    assert s.state.cards[ids[-1]].zone == 'p2:library'
    assert len(s.state.rules.permissions) == 107
    roundtrip(s)

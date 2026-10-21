"""Canonical Void Maw links death replacements to an exact reusable exile cost."""
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
from tests.test_rules_player_protection import priority
from tests.test_rules_source_quality_protection import spell
from tests.test_rules_wave30m_durations import three
from tests.test_rules_wave31d_spell_copies import hold


@pytest.fixture()
def cards(settings):
    data = json.loads((Path(__file__).parent / 'fixtures/name_event_receipts_cards.json').read_text())
    extra = [card(c['name'], set_code='vma', number=str(i), **{k: v for k, v in c.items() if k not in ('name', 'set_code')}) for i, c in enumerate(data)]
    settings.ensure_dirs()
    build_database([*fixture_cards(), *extra], settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def test_core_event_receipts_full(cards):
    for name in ('Search the City', "Minamo's Meddling", 'Cemetery Gatekeeper', 'Cemetery Protector'):
        result = coverage.of_card_data(cards.resolve(name))
        assert result.level == 'FULL', (name, result.manual_parts)


def setup(cards):
    names = ['Search the City', "Minamo's Meddling", 'Cemetery Gatekeeper', 'Cemetery Protector',
             'Glacial Ray', 'Dampen Thought', 'Lake of the Dead', 'Valakut Awakening // Valakut Stoneforge', 'Forest', 'Lightning Bolt', 'Veil of Summer', 'Twincast']
    s = three(cards, names, names, names)
    hold(s)
    return s


def choose(s, ids):
    d = s.state.rules.decision
    assert d is not None
    act(s, d.player, type='choose', decision_id=d.id, option_ids=ids)
    settle(s)


@pytest.mark.parametrize('name', ['Cemetery Gatekeeper', 'Cemetery Protector'])
def test_cemetery_landplay_uses_linked_types_even_if_entry_is_diverted(cards, name):
    s = setup(cards)
    land = put(s, 'Forest', 'graveyard')
    if name == 'Cemetery Gatekeeper':
        spell(s, name, {'R': 1, 'C': 1})
    else:
        spell(s, name, {'W': 2, 'C': 2})
    choose(s, [land.id])
    vale = put(s, 'Lake of the Dead', 'hand')
    before = s.state.players['p1'].life
    act(s, 'p1', type='play_land', card_id=vale.id)
    settle(s)
    assert s.state.cards[vale.id].zone == 'p1:graveyard'
    if name == 'Cemetery Gatekeeper':
        assert s.state.players['p1'].life == before - 2
    else:
        assert any(c.is_token and c.name == 'Human' and c.zone == 'p1:battlefield' for c in s.state.cards.values())
    roundtrip(s)


def test_minamo_discards_matching_cards_spliced_on_actual_spell(cards):
    s = setup(cards)
    ray = put(s, 'Glacial Ray', 'hand', 'p2')
    dampen = put(s, 'Dampen Thought', 'hand', 'p2')
    priority(s, 'p2')
    act(s, 'p2', type='add_mana', player='p2', mana={'R': 1, 'U': 1, 'C': 2})
    act(s, 'p2', type='cast_spell', card_id=ray.id, splice=[dampen.id], targets=['p3', 'p3'], target_counts=[1, 1])
    assert s.state.rules.payments[s.state.rules.object_id(ray.id)].spliced_names == ['Dampen Thought']
    priority(s, 'p1')
    counter = put(s, "Minamo's Meddling", 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana={'U': 2, 'C': 2})
    act(s, 'p1', type='cast_spell', card_id=counter.id, targets=[ray.id])
    settle(s)
    assert s.state.cards[ray.id].zone == s.state.cards[dampen.id].zone == 'p2:graveyard'
    assert s.state.players['p3'].life == 40
    roundtrip(s)


@pytest.mark.parametrize('edge', ['take', 'decline', 'source_blinks', 'linked_card_removed'])
def test_search_city_last_match_returns_card_sacrifices_and_grants_extra_turn(cards, edge):
    s = setup(cards)
    forests = [c for c in s.state.cards.values() if c.owner == 'p1' and c.name == 'Forest']
    for c in forests[:5]:
        act(s, 'p1', type='move', card_ids=[c.id], to={'player': 'p1', 'zone': 'library'}, position='top')
    source = spell(s, 'Search the City', {'U': 1, 'C': 4})
    exiled = [c for c in s.state.cards.values() if c.owner == 'p1' and c.name == 'Forest' and c.zone == 'p1:exile']
    assert len(exiled) == 5
    for c in exiled[1:]:
        act(s, 'p1', type='move', card_ids=[c.id], to={'player': 'p1', 'zone': 'graveyard'})
    land = next(c for c in forests if s.state.cards[c.id].zone != 'p1:exile')
    act(s, 'p1', type='move', card_ids=[land.id], to={'player': 'p1', 'zone': 'hand'})
    act(s, 'p1', type='play_land', card_id=land.id)
    settle(s)
    if edge == 'source_blinks':
        act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'hand'})
        act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'battlefield'})
    if edge == 'linked_card_removed':
        act(s, 'p1', type='move', card_ids=[exiled[0].id], to={'player': 'p1', 'zone': 'graveyard'})
    choose(s, [] if edge in ('decline', 'linked_card_removed') else [exiled[0].id])
    if edge in ('take', 'linked_card_removed'):
        assert s.state.cards[source.id].zone == 'p1:graveyard'
        assert s.state.rules.extra_turns[-1]['player'] == 'p1'
    else:
        assert s.state.cards[source.id].zone == 'p1:battlefield'
        assert not s.state.rules.extra_turns
    if edge in ('take', 'source_blinks'):
        assert s.state.cards[exiled[0].id].zone == 'p1:hand'
    roundtrip(s)


def spliced_ray(s):
    ray = put(s, 'Glacial Ray', 'hand', 'p2')
    dampen = put(s, 'Dampen Thought', 'hand', 'p2')
    priority(s, 'p2')
    act(s, 'p2', type='add_mana', player='p2', mana={'R': 1, 'U': 1, 'C': 2})
    act(s, 'p2', type='cast_spell', card_id=ray.id, splice=[dampen.id], targets=['p3', 'p3'], target_counts=[1, 1])
    return ray, dampen


@pytest.mark.parametrize('edge', ['uncounterable', 'copy', 'spliced_card_left_hand'])
def test_minamo_follows_public_receipt_when_counter_fails_or_target_is_copy(cards, edge):
    s = setup(cards)
    if edge == 'uncounterable':
        spell(s, 'Veil of Summer', {'G': 1}, player='p2')
    ray, dampen = spliced_ray(s)
    target = ray.id
    if edge == 'copy':
        priority(s, 'p1')
        twin = put(s, 'Twincast', 'hand')
        act(s, 'p1', type='add_mana', player='p1', mana={'U': 2})
        act(s, 'p1', type='cast_spell', card_id=twin.id, targets=[ray.id])
        for _ in range(12):
            if s.state.cards[twin.id].zone != 'stack':
                break
            d = s.state.rules.decision
            if d is not None:
                keep = next(o.id for o in d.options if o.id in ('keep', 'same'))
                act(s, d.player, type='choose', decision_id=d.id, option_ids=[keep])
            else:
                act(s, s.state.rules.priority, type='pass_priority')
        copies = [c for c in s.state.cards.values() if c.is_token and c.zone == 'stack']
        assert len(copies) == 1
        target = copies[0].id
        copy_victim = put(s, 'Dampen Thought', 'hand')
        assert s.state.rules.payments[s.state.rules.object_id(target)].spliced_names == ['Dampen Thought']
    if edge == 'spliced_card_left_hand':
        act(s, 'p2', type='move', card_ids=[dampen.id], to={'player': 'p2', 'zone': 'exile'})
    priority(s, 'p1')
    counter = put(s, "Minamo's Meddling", 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana={'U': 2, 'C': 2})
    act(s, 'p1', type='cast_spell', card_id=counter.id, targets=[target])
    settle(s)
    assert s.state.cards[dampen.id].zone == ('p2:exile' if edge == 'spliced_card_left_hand' else 'p2:hand' if edge == 'copy' else 'p2:graveyard')
    if edge == 'copy':
        assert s.state.cards[copy_victim.id].zone == 'p1:graveyard'
    assert s.state.players['p3'].life == (38 if edge in ('uncounterable', 'copy') else 40)
    roundtrip(s)


@pytest.mark.parametrize('kind', ['city', 'splice_legacy'])
def test_public_name_receipt_continuations_resume_in_fresh_process(cards, tmp_path, kind):
    import subprocess
    import sys

    s = setup(cards)
    if kind == 'city':
        forests = [c for c in s.state.cards.values() if c.owner == 'p1' and c.name == 'Forest']
        for c in forests[:5]:
            act(s, 'p1', type='move', card_ids=[c.id], to={'player': 'p1', 'zone': 'library'}, position='top')
        source = spell(s, 'Search the City', {'U': 1, 'C': 4})
        selected = next(c for c in s.state.cards.values() if c.zone == 'p1:exile')
        land = next(c for c in forests if s.state.cards[c.id].zone != 'p1:exile')
        act(s, 'p1', type='move', card_ids=[land.id], to={'player': 'p1', 'zone': 'hand'})
        act(s, 'p1', type='play_land', card_id=land.id)
        settle(s)
        expected = selected.id
    else:
        from app.game.session import GameSession
        from app.game.state import GameState
        ray, dampen = spliced_ray(s)
        data = s.state.model_dump(mode='json')
        for receipt in data['rules']['payments'].values():
            receipt.pop('spliced_names', None)
        s = GameSession(GameState.model_validate(data), cards=cards)
        priority(s, 'p1')
        source = put(s, "Minamo's Meddling", 'hand')
        act(s, 'p1', type='add_mana', player='p1', mana={'U': 2, 'C': 2})
        act(s, 'p1', type='cast_spell', card_id=source.id, targets=[ray.id])
        settle(s)
        assert s.state.rules.decision.player == 'p2'
        expected = dampen.id
    path = tmp_path / (kind + '.json')
    path.write_text(s.state.model_dump_json())
    code = r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
path, database, kind, selected = sys.argv[1:]
repo = CardRepository(Path(database), ImageStore(Path(database).parent / 'images'))
s = GameSession(GameState.model_validate_json(Path(path).read_text()), cards=repo)
s.view('p3')
d = s.state.rules.decision
s.perform(d.player, {'type': 'choose', 'decision_id': d.id, 'option_ids': [selected] if kind == 'city' else [],
                     **({'name': 'Dampen Thought'} if kind != 'city' else {})})
for _ in range(50):
    if not s.state.zones.get('stack'):
        break
    assert s.state.rules.decision is None
    s.perform(s.state.rules.priority, {'type': 'pass_priority'})
assert s.state.cards[selected].zone == ('p1:hand' if kind == 'city' else 'p2:graveyard')
assert s.state.players['p3'].life == 40
assert s.history.rebuild() == s.state
assert GameState.model_validate_json(s.state.model_dump_json()) == s.state
repo.close()
'''
    result = subprocess.run([sys.executable, '-c', code, str(path), str(cards.db_path), kind, expected],
                            capture_output=True, text=True, cwd=Path(__file__).resolve().parents[1], timeout=60)
    assert result.returncode == 0, result.stderr

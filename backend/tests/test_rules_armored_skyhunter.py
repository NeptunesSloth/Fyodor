"""Armored Skyhunter: private look, actual entry, optional non-target attachment, random rest."""
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
from tests.test_rules_conditionals import settle, until
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave5c_combat import declare, to_attack
from tests.test_rules_wave30m_durations import to_phase

NAME = 'Armored Skyhunter'


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/armored_skyhunter_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='ash', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards, top=('Bonesplitter', 'Rancor', 'Sol Ring', 'Forest', 'Forest', 'Forest'), extra=()):
    s = table(cards, [NAME, 'Grizzly Bears', *[n for n in top if n != 'Forest'], *extra], ['Slippery Bogle'], [])
    source = put(s, NAME, 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    enemy = put(s, 'Slippery Bogle', 'battlefield', 'p2')
    to_phase(s, 'main1', turn=4)
    selected = []
    for name in top:
        selected.append(next(c.id for c in s.state.cards.values() if c.name == name and c.owner == 'p1' and c.id not in selected))
    for cid in reversed(selected):
        act(s, 'p1', type='move', card_ids=[cid], to={'player': 'p1', 'zone': 'library'}, position='top')
    to_attack(s, 4)
    declare(s, (source, 'p2'))
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.resume.get('step') == 'armored_skyhunter')
    return s, source, bear, enemy, selected


def answer(s, chosen):
    d = s.state.rules.decision
    assert d is not None
    roundtrip(s)
    act(s, d.player, type='choose', decision_id=d.id, option_ids=chosen)


def test_skyhunter_is_full(cards):
    assert coverage.of_card_data(cards.resolve(NAME)).level == 'FULL'


@pytest.mark.parametrize('attach', [True, False])
def test_equipment_may_attach_to_another_controlled_creature_or_stay_unattached(cards, attach):
    s, _, bear, _, selected = setup(cards)
    before = list(s.state.zones['p1:library'])
    answer(s, [selected[0]])
    d = s.state.rules.decision
    assert d is not None and d.resume['step'] == 'armored_skyhunter_attach'
    assert s.state.cards[selected[0]].zone == 'p1:battlefield'
    answer(s, [bear.id if attach else 'no'])
    settle(s)
    assert s.state.cards[selected[0]].attached_to == (bear.id if attach else None)
    assert s.state.zones['p1:library'][:-5] == before[6:]
    assert set(s.state.zones['p1:library'][-5:]) == set(selected[1:])
    roundtrip(s)


def test_declining_card_randomizes_all_six_without_revealing_the_rest(cards):
    s, _, _, _, selected = setup(cards)
    assert {o.card_id for o in s.state.rules.decision.options} == set(selected[:2])
    assert s.view('p2')['rules']['decision']['kind'] == 'waiting'
    answer(s, [])
    settle(s)
    assert set(s.state.zones['p1:library'][-6:]) == set(selected)
    roundtrip(s)


def test_aura_enters_attached_to_opponents_hexproof_creature_without_targeting(cards):
    s, _, _, enemy, selected = setup(cards)
    answer(s, [selected[1]])
    assert s.state.rules.decision.resume['step'] == 'aura_enters'
    assert any(o.id == enemy.id for o in s.state.rules.decision.options)
    answer(s, [enemy.id])
    settle(s)
    assert s.state.cards[selected[1]].attached_to == enemy.id
    assert s.state.cards[selected[1]].zone == 'p1:battlefield'
    roundtrip(s)


def test_equipment_that_becomes_a_creature_cannot_attach(cards):
    s, _, _, _, selected = setup(cards, extra=['March of the Machines'])
    put(s, 'March of the Machines', 'battlefield')
    answer(s, [selected[0]])
    settle(s)
    assert s.state.cards[selected[0]].zone == 'p1:battlefield'
    assert s.state.cards[selected[0]].attached_to is None
    roundtrip(s)


def test_no_aura_host_leaves_card_in_library_for_random_bottom(cards):
    s, source, bear, enemy, selected = setup(cards)
    for pid, c in [('p1', source), ('p1', bear), ('p2', enemy)]:
        act(s, pid, type='move', card_ids=[c.id], to={'player': pid, 'zone': 'graveyard'})
    answer(s, [selected[1]])
    settle(s)
    assert s.state.cards[selected[1]].zone == 'p1:library'
    assert set(s.state.zones['p1:library'][-6:]) == set(selected)
    roundtrip(s)


def test_creature_equipment_barred_by_cage_remains_in_random_rest(cards):
    s, _, _, _, selected = setup(cards, top=('Lion Sash', 'Forest', 'Forest', 'Forest', 'Forest', 'Forest'), extra=["Grafdigger's Cage"])
    put(s, "Grafdigger's Cage", 'battlefield')
    answer(s, [selected[0]])
    settle(s)
    assert s.state.cards[selected[0]].zone == 'p1:library'
    assert set(s.state.zones['p1:library'][-6:]) == set(selected)
    roundtrip(s)


def test_source_leaving_does_not_prevent_equipping_another_creature(cards):
    s, source, bear, _, selected = setup(cards)
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'graveyard'})
    answer(s, [selected[0]])
    answer(s, [bear.id])
    settle(s)
    assert s.state.cards[selected[0]].attached_to == bear.id
    roundtrip(s)


def test_look_and_attachment_choices_survive_actual_saved_session_reload(cards):
    from app.game.session import GameSession
    from app.game.state import GameState

    s, _, bear, _, selected = setup(cards)
    s = GameSession(GameState.model_validate_json(s.state.model_dump_json()), cards=cards)
    # Replay checks apply to the original history; this branch proves actual saved
    # continuation execution, rather than only checking JSON shape equality.
    d = s.state.rules.decision
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[selected[0]])
    assert s.state.rules.decision.resume['step'] == 'armored_skyhunter_attach'
    s = GameSession(GameState.model_validate_json(s.state.model_dump_json()), cards=cards)
    d = s.state.rules.decision
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[bear.id])
    settle(s)
    assert s.state.cards[selected[0]].attached_to == bear.id
    assert set(s.state.zones['p1:library'][-5:]) == set(selected[1:])


def test_empty_library_does_not_open_or_close_nonexistent_look(cards):
    s = table(cards, [NAME], [], [])
    source = put(s, NAME, 'battlefield')
    to_phase(s, 'main1', turn=4)
    act(s, 'p1', type='move', card_ids=list(s.state.zones['p1:library']), to={'player': 'p1', 'zone': 'graveyard'})
    to_attack(s, 4)
    declare(s, (source, 'p2'))
    settle(s)
    assert not s.state.zones['p1:library']
    assert 'p1' not in s.state.rules.lost
    assert not s.state.views
    roundtrip(s)


def test_no_eligible_card_randomizes_six_without_selection(cards):
    s = table(cards, [NAME], [], [])
    source = put(s, NAME, 'battlefield')
    to_phase(s, 'main1', turn=4)
    before = list(s.state.zones['p1:library'])
    to_attack(s, 4)
    declare(s, (source, 'p2'))
    settle(s)
    assert s.state.zones['p1:library'][:-6] == before[6:]
    assert set(s.state.zones['p1:library'][-6:]) == set(before[:6])
    assert not s.state.views
    roundtrip(s)


@pytest.mark.parametrize('stage', ['pick', 'attach'])
def test_native_saved_choices_resume_in_fresh_process_without_warming_module(cards, tmp_path, stage):
    import subprocess
    import sys

    s, _, bear, _, selected = setup(cards)
    if stage == 'attach':
        answer(s, [selected[0]])
    saved = tmp_path / f'skyhunter-{stage}.json'
    saved.write_text(s.state.model_dump_json())
    script = r'''
import json, sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
saved, database, equipment, host, rest_json = sys.argv[1:]
repo = CardRepository(Path(database), ImageStore(Path(database).parent / 'images'))
s = GameSession(GameState.model_validate_json(Path(saved).read_text()), cards=repo)
d = s.state.rules.decision
if d.resume['step'] == 'armored_skyhunter':
    s.perform('p1', {'type':'choose','decision_id':d.id,'option_ids':[equipment]})
d = s.state.rules.decision
assert d.resume['step'] == 'armored_skyhunter_attach'
s.perform('p1', {'type':'choose','decision_id':d.id,'option_ids':[host]})
assert s.state.cards[equipment].attached_to == host
assert set(s.state.zones['p1:library'][-5:]) == set(json.loads(rest_json))
assert not s.state.views
assert s.history.rebuild().model_dump(mode='json') == s.state.model_dump(mode='json')
repo.close()
'''
    result = subprocess.run([sys.executable, '-c', script, str(saved), str(cards.db_path), selected[0], bear.id,
                             json.dumps(selected[1:])], cwd=Path(__file__).resolve().parents[1],
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr

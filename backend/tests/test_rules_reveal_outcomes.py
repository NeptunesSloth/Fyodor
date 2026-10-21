"""Canonical reveal-through outcomes, owner authority, and snapshot quantities."""
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
from tests.test_rules_designations import pick, put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table

DATA = json.loads((Path(__file__).parent / 'fixtures/reveal_outcomes_cards.json').read_text())


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(DATA):
        base[c['name']] = card(c['name'], set_code='rvo', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


@pytest.mark.parametrize('name', [c['name'] for c in DATA[:12]])
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


def mana(s):
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 60, 'U': 3, 'B': 3, 'R': 3, 'G': 3})


def cast(s, name, targets=(), x=None):
    c = put(s, name, 'hand')
    mana(s)
    act(s, 'p1', type='cast_spell', card_id=c.id, targets=list(targets), **({'x_value': x} if x is not None else {}))
    settle(s)
    return c


def test_funeral_reveals_through_four_lands_not_just_last_found(cards):
    s = table(cards, ['Mind Funeral'], ['Grizzly Bears'])
    bear = put(s, 'Grizzly Bears', 'library', 'p2')
    cast(s, 'Mind Funeral', ['p2'])
    assert len(s.state.zones['p2:graveyard']) == 5
    assert s.state.cards[bear.id].zone == 'p2:graveyard'
    assert sum(s.state.cards[c].name == 'Island' for c in s.state.zones['p2:graveyard']) == 4
    roundtrip(s)


def test_grind_each_opponent_and_zero_rejected(cards):
    s = table(cards, ['Mind Grind'], ['Grizzly Bears'])
    bear = put(s, 'Grizzly Bears', 'library', 'p2')
    source = put(s, 'Mind Grind', 'hand')
    mana(s)
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=source.id, x_value=0)
    assert s.state.model_dump_json() == before
    act(s, 'p1', type='cast_spell', card_id=source.id, x_value=2)
    settle(s)
    assert len(s.state.zones['p2:graveyard']) == 3
    assert len(s.state.zones['p3:graveyard']) == 2
    assert s.state.cards[bear.id].zone == 'p2:graveyard'
    roundtrip(s)


def test_fathom_puts_all_three_nonlands_in_hand(cards):
    s = table(cards, ['Fathom Trawl', 'Sol Ring', 'Grizzly Bears', 'Llanowar Elves'])
    ids = [put(s, n, 'library').id for n in ['Sol Ring', 'Grizzly Bears', 'Llanowar Elves']]
    cast(s, 'Fathom Trawl')
    assert all(s.state.cards[c].zone == 'p1:hand' for c in ids)
    roundtrip(s)


def test_madcap_includes_found_card_in_damage(cards):
    s = table(cards, ['Madcap Experiment', 'Sol Ring'])
    ring = put(s, 'Sol Ring', 'library')
    put(s, 'Forest', 'library')
    cast(s, 'Madcap Experiment')
    assert s.state.cards[ring.id].zone == 'p1:battlefield'
    assert s.state.players['p1'].life == 38
    roundtrip(s)


def test_reshapers_actual_paid_sacrifice_and_reveal_damage(cards):
    s = table(cards, ['Audacious Reshapers', 'Sol Ring', 'Mana Vault', 'Thousand-Year Elixir'])
    source = put(s, 'Audacious Reshapers', 'battlefield')
    put(s, 'Thousand-Year Elixir', 'battlefield')
    cost = put(s, 'Sol Ring', 'battlefield')
    found = put(s, 'Mana Vault', 'library')
    put(s, 'Forest', 'library')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=0)
    d = s.state.rules.decision
    assert d is not None and cost.id in {o.id for o in d.options}
    pick(s, [cost.id])
    settle(s)
    assert s.state.cards[cost.id].zone == 'p1:graveyard'
    assert s.state.cards[found.id].zone == 'p1:battlefield'
    assert s.state.players['p1'].life == 38
    roundtrip(s)


def test_telemin_p2_library_card_enters_under_p1(cards):
    s = table(cards, ['Telemin Performance'], ['Grizzly Bears', 'Sol Ring'])
    bear = put(s, 'Grizzly Bears', 'library', 'p2')
    ring = put(s, 'Sol Ring', 'library', 'p2')
    cast(s, 'Telemin Performance', ['p2'])
    assert s.state.cards[ring.id].zone == 'p2:graveyard'
    assert s.state.cards[bear.id].zone == 'p1:battlefield'
    assert s.state.cards[bear.id].controller == 'p1'
    assert s.state.cards[bear.id].owner == 'p2'
    roundtrip(s)


def test_shape_sacrifice_revealer_keeps_library_owner_control(cards):
    s = table(cards, ['Shape Anew'], ['Sol Ring', 'Mana Vault'])
    ring = put(s, 'Sol Ring', 'battlefield', 'p2')
    vault = put(s, 'Mana Vault', 'library', 'p2')
    cast(s, 'Shape Anew', [ring.id])
    assert s.state.cards[ring.id].zone == 'p2:graveyard'
    assert s.state.cards[vault.id].zone == 'p2:battlefield'
    roundtrip(s)


def test_proteus_uses_creature_controller_library(cards):
    s = table(cards, ['Proteus Staff'], ['Grizzly Bears', 'Llanowar Elves'])
    source = put(s, 'Proteus Staff', 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    elf = put(s, 'Llanowar Elves', 'library', 'p2')
    mana(s)
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=0, targets=[bear.id])
    settle(s)
    assert s.state.cards[bear.id].zone == 'p2:library'
    assert s.state.cards[elf.id].zone == 'p2:battlefield'
    roundtrip(s)


def test_erratic_uses_revealed_mv_before_bottom_order(cards):
    s = table(cards, ['Erratic Mutation', 'Sol Ring'], ['Grizzly Bears'])
    bear = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    put(s, 'Sol Ring', 'library')
    cast(s, 'Erratic Mutation', [bear.id])
    from app.rules.plan import Plan
    plan = Plan(s.state, 'p1', cards, None)
    assert plan.ch(s.state.cards[bear.id]).pt == (3, 1)
    roundtrip(s)


def test_stomping_remembers_name_after_bottom(cards):
    s = table(cards, ['Stomping Slabs', 'Stomping Slabs'])
    sources = [c for c in s.state.cards.values() if c.name == 'Stomping Slabs']
    act(s, 'p1', type='move', card_ids=[sources[1].id], to={'player': 'p1', 'zone': 'library'}, position='top')
    act(s, 'p1', type='move', card_ids=[sources[0].id], to={'player': 'p1', 'zone': 'hand'})
    mana(s)
    act(s, 'p1', type='cast_spell', card_id=sources[0].id, targets=['p2'])
    settle(s)
    assert s.state.players['p2'].life == 33
    roundtrip(s)


def test_clear_each_player_lands_enter_tapped(cards):
    s = table(cards, ['Clear the Land', 'Sol Ring'], ['Grizzly Bears'])
    ring = put(s, 'Sol Ring', 'library')
    bear = put(s, 'Grizzly Bears', 'library', 'p2')
    cast(s, 'Clear the Land')
    assert s.state.cards[ring.id].zone == 'p1:exile'
    assert s.state.cards[bear.id].zone == 'p2:exile'
    for pid, count in [('p1', 4), ('p2', 4), ('p3', 5)]:
        lands = [s.state.cards[c] for c in s.state.zones[f'{pid}:battlefield']]
        assert len(lands) == count
        assert all(c.tapped for c in lands)
    roundtrip(s)


def test_genesis_x_cast_trigger_native_pick_then_original_enters(cards):
    s = table(cards, ['Genesis Hydra', 'Sol Ring'])
    ring = put(s, 'Sol Ring', 'library')
    source = cast(s, 'Genesis Hydra', x=2)
    d = s.state.rules.decision
    assert d is not None and ring.id in {o.id for o in d.options}
    pick(s, [ring.id])
    settle(s)
    assert s.state.cards[ring.id].zone == 'p1:battlefield'
    assert s.state.cards[source.id].counters.get('+1/+1') == 2
    roundtrip(s)


def test_telemin_finds_library_grist_current_creature_characteristic(cards):
    s = table(cards, ['Telemin Performance'], ['Grist, the Hunger Tide'])
    grist = put(s, 'Grist, the Hunger Tide', 'library', 'p2')
    cast(s, 'Telemin Performance', ['p2'])
    assert s.state.cards[grist.id].zone == 'p1:battlefield'
    assert s.state.cards[grist.id].counters.get('loyalty') == 3
    roundtrip(s)


def test_telemin_no_creature_reveals_entire_library_to_graveyard(cards):
    s = table(cards, ['Telemin Performance'])
    n = len(s.state.zones['p2:library'])
    cast(s, 'Telemin Performance', ['p2'])
    assert not s.state.zones['p2:library']
    assert len(s.state.zones['p2:graveyard']) == n
    assert not s.state.rules.decision
    roundtrip(s)


def test_madcap_failed_creature_artifact_entry_still_counts_revealed(cards):
    s = table(cards, ['Madcap Experiment', 'Solemn Simulacrum', "Grafdigger's Cage"])
    put(s, "Grafdigger's Cage", 'battlefield')
    found = put(s, 'Solemn Simulacrum', 'library')
    put(s, 'Forest', 'library')
    cast(s, 'Madcap Experiment')
    assert s.state.cards[found.id].zone == 'p1:library'
    assert s.state.players['p1'].life == 38
    roundtrip(s)


def test_genesis_cast_trigger_retains_x_after_original_countered(cards):
    s = table(cards, ['Genesis Hydra', 'Sol Ring', 'Counterspell'])
    ring = put(s, 'Sol Ring', 'library')
    source = put(s, 'Genesis Hydra', 'hand')
    counter = put(s, 'Counterspell', 'hand')
    mana(s)
    act(s, 'p1', type='set_prefs', hold_priority=True)
    act(s, 'p1', type='cast_spell', card_id=source.id, x_value=2)
    act(s, 'p1', type='cast_spell', card_id=counter.id, targets=[source.id])
    settle(s)
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    d = s.state.rules.decision
    assert d is not None and ring.id in {o.id for o in d.options}
    pick(s, [ring.id])
    settle(s)
    assert s.state.cards[ring.id].zone == 'p1:battlefield'
    roundtrip(s)


def test_madcap_no_artifact_still_deals_full_reveal_count(cards):
    s = table(cards, ['Madcap Experiment'])
    source = put(s, 'Madcap Experiment', 'hand')
    count = len(s.state.zones['p1:library'])
    mana(s)
    act(s, 'p1', type='cast_spell', card_id=source.id)
    settle(s)
    assert s.state.players['p1'].life == 40 - count
    assert len(s.state.zones['p1:library']) == count
    assert not s.state.zones['p1:battlefield']
    roundtrip(s)


def test_stomping_wrong_name_does_not_damage(cards):
    s = table(cards, ['Stomping Slabs', 'Sol Ring'])
    put(s, 'Sol Ring', 'library')
    cast(s, 'Stomping Slabs', ['p2'])
    assert s.state.players['p2'].life == 40
    roundtrip(s)


def test_grind_library_exhaustion_does_not_try_to_draw(cards):
    s = table(cards, ['Mind Grind'])
    sizes = {p: len(s.state.zones[f'{p}:library']) for p in ['p2', 'p3']}
    cast(s, 'Mind Grind', x=30)
    for pid in ['p2', 'p3']:
        assert not s.state.zones[f'{pid}:library']
        assert len(s.state.zones[f'{pid}:graveyard']) == sizes[pid]
    roundtrip(s)


def cold_answer(s, cards, tmp_path, ids):
    import subprocess
    import sys

    from app.game.session import GameSession
    from app.game.state import GameState

    original, restored = tmp_path / 'original.json', tmp_path / 'restored.json'
    original.write_text(s.state.model_dump_json())
    code = r'''
import json,sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
repo=CardRepository(Path(sys.argv[1]),ImageStore(Path(sys.argv[1]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[2]).read_text()),cards=repo)
s.view('p3')
d=s.state.rules.decision
assert d is not None
s.perform(d.player,{'type':'choose','decision_id':d.id,'option_ids':json.loads(sys.argv[4])})
for _ in range(40):
    d=s.state.rules.decision
    if d is not None and d.kind=='order':
        s.perform(d.player,{'type':'choose','decision_id':d.id,'option_ids':[o.id for o in d.options]})
    elif d is not None:
        raise AssertionError(d)
    elif s.state.zones['stack']:
        s.perform(s.state.rules.priority,{'type':'pass_priority'})
    else:
        break
else:
    raise AssertionError('did not finish')
assert s.history.rebuild()==s.state
assert GameState.model_validate_json(s.state.model_dump_json())==s.state
Path(sys.argv[3]).write_text(s.state.model_dump_json())
repo.close()
'''
    result = subprocess.run([sys.executable, '-c', code, str(cards.db_path), str(original), str(restored), json.dumps(ids)],
                            capture_output=True, text=True, cwd=Path(__file__).resolve().parents[1], timeout=90)
    assert result.returncode == 0, result.stderr
    return GameSession(GameState.model_validate_json(restored.read_text()), cards=cards)


def test_cold_stomping_order_preserves_verdict_and_target_damage(cards, tmp_path):
    s = table(cards, ['Stomping Slabs', 'Stomping Slabs'])
    sources = [c for c in s.state.cards.values() if c.name == 'Stomping Slabs']
    act(s, 'p1', type='move', card_ids=[sources[1].id], to={'player': 'p1', 'zone': 'library'}, position='top')
    act(s, 'p1', type='move', card_ids=[sources[0].id], to={'player': 'p1', 'zone': 'hand'})
    mana(s)
    act(s, 'p1', type='cast_spell', card_id=sources[0].id, targets=['p2'])
    # Do not use settle: it deliberately answers ordering decisions.
    for _ in range(20):
        if s.state.rules.decision is not None:
            break
        act(s, s.state.rules.priority, type='pass_priority')
    d = s.state.rules.decision
    assert d is not None and d.kind == 'order'
    s = cold_answer(s, cards, tmp_path, [o.id for o in d.options])
    assert s.state.players['p2'].life == 33
    assert all(not s.state.cards[c].revealed_to for c in s.state.zones['p1:library'])
    roundtrip(s)


def test_cold_genesis_optional_pick_resumes_original_spell(cards, tmp_path):
    s = table(cards, ['Genesis Hydra', 'Sol Ring'])
    ring = put(s, 'Sol Ring', 'library')
    source = cast(s, 'Genesis Hydra', x=2)
    s = cold_answer(s, cards, tmp_path, [ring.id])
    assert s.state.cards[source.id].counters.get('+1/+1') == 2
    assert s.state.cards[ring.id].zone == 'p1:battlefield'
    roundtrip(s)


def test_cold_telemin_native_clone_entry_choice(cards, tmp_path):
    s = table(cards, ['Telemin Performance'], ['Clone'], ['Grizzly Bears'])
    clone = put(s, 'Clone', 'library', 'p2')
    bear = put(s, 'Grizzly Bears', 'battlefield', 'p3')
    cast(s, 'Telemin Performance', ['p2'])
    d = s.state.rules.decision
    assert d is not None
    answer = next(o.id for o in d.options if o.card_id == bear.id or o.id == bear.id)
    s = cold_answer(s, cards, tmp_path, [answer])
    from app.rules.plan import Plan
    assert s.state.cards[clone.id].zone == 'p1:battlefield'
    assert s.state.cards[clone.id].owner == 'p2'
    assert Plan(s.state, 'p1', cards, None).ch(s.state.cards[clone.id]).name == 'Grizzly Bears'
    roundtrip(s)


def test_proteus_stolen_target_uses_controller_library_not_owner(cards):
    s = table(cards, ['Proteus Staff', 'Control Magic', 'Grizzly Bears'], ['Llanowar Elves'])
    source = put(s, 'Proteus Staff', 'battlefield')
    elf = put(s, 'Llanowar Elves', 'battlefield', 'p2')
    bear = put(s, 'Grizzly Bears', 'library')
    cast(s, 'Control Magic', [elf.id])
    assert s.state.cards[elf.id].controller == 'p1'
    mana(s)
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=0, targets=[elf.id])
    settle(s)
    assert s.state.cards[elf.id].zone == 'p2:library'
    assert s.state.cards[bear.id].zone == 'p1:battlefield'
    roundtrip(s)


def test_clear_cage_blocks_dryad_only_other_lands_enter(cards):
    s = table(cards, ['Clear the Land', "Grafdigger's Cage"], ['Dryad Arbor'])
    put(s, "Grafdigger's Cage", 'battlefield')
    dryad = put(s, 'Dryad Arbor', 'library', 'p2')
    cast(s, 'Clear the Land')
    assert s.state.cards[dryad.id].zone == 'p2:library'
    assert len(s.state.zones['p2:battlefield']) == 4
    assert not s.state.cards[dryad.id].revealed_to
    roundtrip(s)


def test_stomping_order_hidden_before_damage_replacement_choice(cards):
    s = table(cards, ['Stomping Slabs', 'Stomping Slabs', 'Torbran, Thane of Red Fell', 'Fiery Emancipation'])
    put(s, 'Torbran, Thane of Red Fell', 'battlefield')
    put(s, 'Fiery Emancipation', 'battlefield')
    sources = [c for c in s.state.cards.values() if c.name == 'Stomping Slabs']
    act(s, 'p1', type='move', card_ids=[sources[1].id], to={'player': 'p1', 'zone': 'library'}, position='top')
    act(s, 'p1', type='move', card_ids=[sources[0].id], to={'player': 'p1', 'zone': 'hand'})
    mana(s)
    act(s, 'p1', type='cast_spell', card_id=sources[0].id, targets=['p2'])
    for _ in range(20):
        if s.state.rules.decision is not None:
            break
        act(s, s.state.rules.priority, type='pass_priority')
    d = s.state.rules.decision
    assert d is not None and d.kind == 'order'
    pick(s, [o.id for o in d.options])
    d = s.state.rules.decision
    assert d is not None and d.kind != 'order'
    assert all(not s.state.cards[c].revealed_to for c in s.state.zones['p1:library'])
    # Finish both affected player's replacement choices natively.
    for _ in range(12):
        d = s.state.rules.decision
        if d is None:
            break
        pick(s, [d.options[0].id])
    settle(s)
    assert s.state.players['p2'].life in (13, 17)
    roundtrip(s)

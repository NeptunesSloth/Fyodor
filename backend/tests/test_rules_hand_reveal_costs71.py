"""Every other player pays one shared nominal life-gain event as a real alternative cost."""

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
from tests.test_rules_activated_copy_family import answer
from tests.test_rules_bandmate_references import wait_priority
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

NAMES = ["Land Grant"]
DATA = json.loads((Path(__file__).parent / "fixtures/hand_reveal_costs71_cards.json").read_text())


@pytest.fixture
def cards(settings):
    base = {c["name"]: c for c in fixture_cards()}
    for i, c in enumerate(DATA):
        base[c["name"]] = card(c["name"], number=str(i), **{k: v for k, v in c.items() if k != "name"})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards, land=False):
    ns = [c["name"] for c in DATA]
    s = table(cards, ns, ns, ns)
    for pid in ["p1", "p2", "p3"]:
        act(s, pid, type="set_prefs", hold_priority=True, response="on")
    to_phase(s, "main1", 4)
    for cid in list(s.state.zones.get("p1:hand", [])):
        act(s, "p1", type="move", card_ids=[cid], to={"zone":"library", "player":"p1"})
    source = put(s, "Land Grant", "hand")
    other = put(s, "Lightning Bolt", "hand")
    if land:
        put(s, "Forest", "hand")
    return s, source, other


def alt(s, source):
    wait_priority(s, "p1")
    return act(s, "p1", type="cast_spell", card_id=source.id, alt_cost=f"{source.id}:0", sources=[])


def test_canonical(cards):
    assert coverage.of_card_data(cards.resolve("Land Grant")).level == "FULL"


def test_actual_cost_reveals_only_remaining_hand_until_stack_departure(cards):
    s, source, other = setup(cards)
    alt(s, source)
    assert source.zone == "stack"
    assert other.revealed_to
    record = s.state.rules.payments[s.state.rules.object_id(source.id)]
    assert record.revealed == [other.id]
    roundtrip(s)
    answer(s)
    assert source.zone == "p1:graveyard"
    assert not s.state.cards[other.id].revealed_to


def test_land_in_hand_blocks_alternative_atomically(cards):
    s, source, _ = setup(cards, True)
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        alt(s, source)
    assert s.state.model_dump_json() == before


def test_normal_mana_cost_does_not_disclose_hand(cards):
    s, source, other = setup(cards, True)
    act(s, 'p1', type='add_mana', player='p1', mana={'C':1, 'G':1})
    wait_priority(s, 'p1')
    act(s, 'p1', type='cast_spell', card_id=source.id, sources=[])
    assert not other.revealed_to
    assert not s.state.rules.payments[s.state.rules.object_id(source.id)].revealed
    answer(s)


def test_real_tax_requires_mana_and_failed_payment_does_not_reveal(cards):
    s, source, other = setup(cards)
    put(s, 'Sphere of Resistance', 'battlefield', pid='p2')
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        alt(s, source)
    assert s.state.model_dump_json() == before
    assert not other.revealed_to
    act(s, 'p1', type='add_mana', player='p1', mana={'C':1})
    alt(s, source)
    assert other.revealed_to
    assert s.state.players['p1'].mana.get('C',0) == 0
    answer(s)


def test_countered_spell_restores_previous_private_hand_visibility(cards):
    s, source, other = setup(cards)
    alt(s, source)
    counter = put(s, 'Counterspell', 'hand', pid='p2')
    act(s, 'p2', type='add_mana', player='p2', mana={'U':2})
    wait_priority(s, 'p2')
    act(s, 'p2', type='cast_spell', card_id=counter.id, targets=[source.id], sources=[])
    assert '*' in other.revealed_to
    answer(s)
    assert source.zone == 'p1:graveyard'
    assert not s.state.cards[other.id].revealed_to
    assert not s.state.rules.revealed_activation_costs


def test_prior_public_card_stays_public_after_resolution(cards):
    s, source, other = setup(cards)
    act(s, 'p1', type='reveal', card_ids=[other.id])
    alt(s, source)
    answer(s)
    assert '*' in s.state.cards[other.id].revealed_to
    assert not s.state.rules.revealed_activation_costs


def test_empty_remaining_hand_is_valid_reveal_cost(cards):
    s, source, other = setup(cards)
    act(s, 'p1', type='move', card_ids=[other.id], to={'zone':'library', 'player':'p1'})
    alt(s, source)
    assert s.state.rules.payments[s.state.rules.object_id(source.id)].revealed == []
    answer(s)
    assert source.zone == 'p1:graveyard'


def test_forest_subtype_tutor_can_find_savannah(cards):
    s, source, _ = setup(cards)
    dual = put(s, 'Savannah', 'library')
    alt(s, source)
    for _ in range(20):
        d = s.state.rules.decision
        if d:
            ids = [o.id for o in d.options]
            pick = dual.id if dual.id in ids else 'done' if 'done' in ids else ids[0]
            act(s, d.player, type='choose', decision_id=d.id, option_ids=[pick])
        elif s.state.zones.get('stack'):
            act(s, s.state.rules.priority, type='pass_priority')
        else:
            break
    assert dual.zone == 'p1:hand'
    assert source.zone == 'p1:graveyard'


def test_real_cold_stack_reveal_survives_and_cleans_up(cards, tmp_path):
    import os
    import subprocess
    import sys
    s, source, other = setup(cards)
    alt(s, source)
    path = tmp_path/'save.json'
    path.write_text(s.state.model_dump_json())
    code = '''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.test_rules_activated_copy_family import answer
path, database, source, other = sys.argv[1:]
repo = CardRepository(Path(database), ImageStore(Path(database).parent/'images'))
s = GameSession(GameState.model_validate_json(Path(path).read_text()), cards=repo)
s.view('p3')
assert s.state.cards[source].zone == 'stack'
assert '*' in s.state.cards[other].revealed_to
assert s.state.rules.revealed_activation_costs
answer(s)
assert s.state.cards[source].zone == 'p1:graveyard'
assert not s.state.cards[other].revealed_to
assert not s.state.rules.revealed_activation_costs
GameState.model_validate_json(s.state.model_dump_json())
'''
    result = subprocess.run([sys.executable,'-c',code,str(path),str(cards.db_path),source.id,other.id], capture_output=True,text=True,env=os.environ.copy())
    assert result.returncode == 0, result.stdout+result.stderr


def test_actual_optional_search_can_fail_to_find_with_forest_present(cards):
    s, source, other = setup(cards)
    forest = put(s, 'Forest', 'library')
    alt(s, source)
    for _ in range(20):
        d = s.state.rules.decision
        if d:
            ids = [o.id for o in d.options]
            act(s, d.player, type='choose', decision_id=d.id,
                option_ids=[] if d.min_choices == 0 else [ids[0]])
        elif s.state.zones.get('stack'):
            act(s, s.state.rules.priority, type='pass_priority')
        else:
            break
    assert forest.zone == 'p1:library'
    assert source.zone == 'p1:graveyard'
    assert s.state.zones['p1:hand'] == [other.id]

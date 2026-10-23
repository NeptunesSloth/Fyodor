"""The discounted caster and original ability controller's next turn are separate identities."""

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import coverage
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_activated_copy_family import answer
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

DATA = json.loads((Path(__file__).parent / "fixtures/target_duration_costs69_cards.json").read_text())


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


def setup(cards):
    names = [c["name"] for c in DATA]
    s = table(cards, names, names, names)
    for p in ("p1", "p2", "p3"):
        act(s, p, type="set_prefs", hold_priority=True, response="on")
    to_phase(s, "main1", 4)
    source = put(s, "Will Kenrith", "hand")
    act(s, "p1", type="add_mana", player="p1", mana={"C": 4, "U": 2})
    act(s, "p1", type="cast_spell", card_id=source.id, sources=[])
    answer(s)
    assert source.zone == "p1:battlefield" and source.counters["loyalty"] == 4
    return s, source


def activate(s, source, index, targets=(), counts=None):
    args = {
        "type": "activate_ability",
        "card_id": source.id,
        "ability": index,
        "targets": list(targets),
        "sources": [],
    }
    if counts is not None:
        args["target_counts"] = counts
    act(s, source.controller, **args)
    answer(s)


def test_whole_will_is_full(cards):
    assert coverage.of_card_data(cards.resolve("Will Kenrith")).level == "FULL"


def test_discount_survives_beneficiary_turn_and_source_departure_but_not_original_next_turn(cards):
    s, source = setup(cards)
    before = len(s.state.zones["p2:hand"])
    activate(s, source, 1, ["p2"])
    assert len(s.state.zones["p2:hand"]) == before + 2
    m = s.state.rules.cost_modifiers[-1]
    assert m.controller == "p2" and m.until_player == "p1" and m.delta == -2
    act(s, "p1", type="move", card_ids=[source.id], to={"zone": "graveyard", "player": "p1"})
    to_phase(s, "main1", 5)
    spell = put(s, "Divination", "hand", pid="p2")
    act(s, "p2", type="add_mana", player="p2", mana={"U": 1})
    act(s, "p2", type="cast_spell", card_id=spell.id, sources=[])
    answer(s)
    assert spell.zone == "p2:graveyard"
    to_phase(s, "main1", 7)
    bolt = put(s, "Divination", "hand", pid="p2")
    act(s, "p2", type="add_mana", player="p2", mana={"U": 1})
    # A sorcery can be tested on p2's next real main phase after the expiry.
    to_phase(s, "main1", 8)
    act(s, "p2", type="add_mana", player="p2", mana={"U": 1})
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s, "p2", type="cast_spell", card_id=bolt.id, sources=[])
    assert s.state.model_dump_json() == before
    act(s, "p2", type="add_mana", player="p2", mana={"C": 2})
    act(s, "p2", type="cast_spell", card_id=bolt.id, sources=[])
    answer(s)
    assert not s.state.rules.cost_modifiers
    roundtrip(s)


def test_discount_filters_spell_types_colored_mana_and_actual_recipient(cards):
    s, source = setup(cards)
    activate(s, source, 1, ["p2"])
    to_phase(s, "main1", 5)
    ring = put(s, "Sol Ring", "hand", pid="p2")
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s, "p2", type="cast_spell", card_id=ring.id, sources=[])
    assert s.state.model_dump_json() == before
    act(s, "p2", type="add_mana", player="p2", mana={"C": 1})
    act(s, "p2", type="cast_spell", card_id=ring.id, sources=[])
    answer(s)
    jace = put(s, "Jace Beleren", "hand", pid="p2")
    act(s, "p2", type="add_mana", player="p2", mana={"U": 1})
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s, "p2", type="cast_spell", card_id=jace.id, sources=[])
    assert s.state.model_dump_json() == before
    act(s, "p2", type="add_mana", player="p2", mana={"U": 1})
    act(s, "p2", type="cast_spell", card_id=jace.id, sources=[])
    answer(s)
    assert jace.zone == "p2:battlefield"
    other = put(s, "Divination", "hand", pid="p3")
    to_phase(s, "main1", 6)
    act(s, "p3", type="add_mana", player="p3", mana={"U": 1})
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s, "p3", type="cast_spell", card_id=other.id, sources=[])
    assert s.state.model_dump_json() == before
    roundtrip(s)


def test_plus_two_native_two_targets_lose_abilities_and_restore_on_original_next_turn(cards):
    s, source = setup(cards)
    one = put(s, "Llanowar Elves", "battlefield")
    two = put(s, "Grizzly Bears", "battlefield", pid="p2")
    activate(s, source, 0, [one.id, two.id], [2])
    assert source.counters["loyalty"] == 6
    for c in [one, two]:
        ch = Plan(s.state, "p1", cards, None).ch(c)
        assert ch.pt == (0, 3) and not ch.abilities
    to_phase(s, "main1", 5)
    assert Plan(s.state, "p1", cards, None).ch(one).pt == (0, 3)
    to_phase(s, "main1", 7)
    assert Plan(s.state, "p1", cards, None).ch(one).pt == (1, 1)
    assert Plan(s.state, "p1", cards, None).ch(two).pt == (2, 2)
    roundtrip(s)


def test_minus_eight_native_emblem_still_copies_actual_spell_after_will_dies(cards):
    s, source = setup(cards)
    act(s, "p1", type="counter", card_ids=[source.id], kind="loyalty", delta=4)
    activate(s, source, 2, ["p1"])
    assert source.zone == "p1:graveyard"
    bolt = put(s, "Lightning Bolt", "hand")
    act(s, "p1", type="add_mana", player="p1", mana={"R": 1})
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"], sources=[])
    answer(s)
    assert s.state.players["p2"].life == 34
    roundtrip(s)


def test_plus_two_zero_targets_uses_native_optional_target_group(cards):
    s, source = setup(cards)
    activate(s, source, 0, [], [0])
    assert source.counters["loyalty"] == 6
    assert not s.state.rules.effects
    roundtrip(s)


def test_original_controller_is_captured_before_source_control_changes(cards):
    s, source = setup(cards)
    act(s, "p1", type="activate_ability", card_id=source.id, ability=1, targets=["p2"], sources=[])
    act(s, "p1", type="set_controller", card_ids=[source.id], player="p3")
    answer(s)
    modifier = s.state.rules.cost_modifiers[-1]
    assert modifier.controller == "p2" and modifier.until_player == "p1"
    to_phase(s, "main1", 5)
    spell = put(s, "Divination", "hand", pid="p2")
    act(s, "p2", type="add_mana", player="p2", mana={"U": 1})
    act(s, "p2", type="cast_spell", card_id=spell.id, sources=[])
    answer(s)
    roundtrip(s)


def test_draw_replacement_changes_draw_recipient_not_discount_beneficiary(cards):
    s, source = setup(cards)
    put(s, "Notion Thief", "battlefield", pid="p3")
    before = {pid: len(s.state.zones[pid + ":hand"]) for pid in ["p2", "p3"]}
    activate(s, source, 1, ["p2"])
    assert len(s.state.zones["p2:hand"]) == before["p2"]
    assert len(s.state.zones["p3:hand"]) == before["p3"] + 2
    modifier = s.state.rules.cost_modifiers[-1]
    assert modifier.controller == "p2" and modifier.until_player == "p1"
    roundtrip(s)


def test_discount_expires_at_departed_original_controllers_would_be_turn(cards):
    s, source = setup(cards)
    activate(s, source, 1, ["p2"])
    act(s, "p1", type="concede")
    to_phase(s, "main1", 5)
    spell = put(s, "Divination", "hand", pid="p2")
    act(s, "p2", type="add_mana", player="p2", mana={"U": 1})
    act(s, "p2", type="cast_spell", card_id=spell.id, sources=[])
    answer(s)
    to_phase(s, "main1", 8)
    assert not s.state.rules.cost_modifiers
    spell = put(s, "Divination", "hand", pid="p2")
    act(s, "p2", type="add_mana", player="p2", mana={"U": 1})
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s, "p2", type="cast_spell", card_id=spell.id, sources=[])
    assert s.state.model_dump_json() == before
    roundtrip(s)


@pytest.mark.parametrize("mode", ["discount", "two_targets"])
def test_true_cold_target_player_duration_and_target_group(cards, tmp_path, mode):
    import subprocess
    import sys

    from app.rules import target_duration_costs69

    s, source = setup(cards)
    one = put(s, "Llanowar Elves", "battlefield")
    two = put(s, "Grizzly Bears", "battlefield", pid="p2")
    if mode == "discount":
        activate(s, source, 1, ["p2"])
    else:
        activate(s, source, 0, [one.id, two.id], [2])
    saved = tmp_path / "saved.json"
    saved.write_text(s.state.model_dump_json())
    code = r"""
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from app.rules.plan import Plan
from tests.game_helpers import act
from tests.test_rules_designations import put,roundtrip
from tests.test_rules_activated_copy_family import answer
from tests.test_rules_wave30m_durations import to_phase
r=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=r)
mode,one,two,source=sys.argv[3:]
to_phase(s,'main1',5)
if mode=='discount':
 m=s.state.rules.cost_modifiers[-1]
 assert m.controller=='p2' and m.until_player=='p1'
 spell=put(s,'Divination','hand',pid='p2')
 act(s,'p2',type='add_mana',player='p2',mana={'U':1})
 act(s,'p2',type='cast_spell',card_id=spell.id,sources=[])
 answer(s)
 assert spell.zone=='p2:graveyard'
else:
 assert Plan(s.state,'p1',r,None).ch(s.state.cards[one]).pt==(0,3)
to_phase(s,'main1',7)
if mode=='discount':assert not s.state.rules.cost_modifiers
else:
 assert Plan(s.state,'p1',r,None).ch(s.state.cards[one]).pt==(1,1)
 assert Plan(s.state,'p1',r,None).ch(s.state.cards[two]).pt==(2,2)
roundtrip(s)
r.close()
"""
    result = subprocess.run(
        [sys.executable, "-c", code, str(saved), str(cards.db_path), mode, one.id, two.id, source.id],
        cwd=Path(target_duration_costs69.__file__).resolve().parents[2],
        capture_output=True,
        text=True,
        timeout=150,
    )
    assert result.returncode == 0, result.stdout + result.stderr

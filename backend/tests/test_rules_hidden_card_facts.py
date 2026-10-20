"""Actual Oracle costs and discard instructions retain the right card incarnations."""

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
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_mana_delayed_effects import answer, cast, drawn
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

DATA = Path(__file__).parent / "fixtures/hidden_card_facts_cards.json"
NAMES = [c["name"] for c in json.loads(DATA.read_text())][:16]
POOL = {c: 20 for c in "WUBRGC"}


@pytest.fixture()
def cards(settings):
    base = {c["name"]: c for c in fixture_cards()}
    for i, c in enumerate(json.loads(DATA.read_text())):
        base[c["name"]] = card(
            c["name"], set_code="hcf", number=str(i), **{k: v for k, v in c.items() if k != "name"}
        )
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def game(cards):
    names = [c["name"] for c in json.loads(DATA.read_text())]
    s = table(cards, names, names, names)
    for pid in ("p1", "p2", "p3"):
        act(s, pid, type="set_prefs", hold_priority=True)
    to_phase(s, "main1", 4)
    return s


def choose(s, ids):
    d = s.state.rules.decision
    assert d is not None
    act(s, d.player, type="choose", decision_id=d.id, option_ids=ids)


def cast_cost(s, name, paid, targets=(), **kw):
    return cast(s, name, POOL, targets, cost_choices=[{"component": 0, "cards": [c.id for c in paid]}], **kw)


@pytest.mark.parametrize("name", NAMES)
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


@pytest.mark.parametrize("name", ["Disaster Radius", "Induce Despair"])
def test_reveal_actual_mv(cards, name):
    s = game(cards)
    reveal = put(s, "Trained Armodon", "hand")
    victim = put(s, "Darksteel Colossus", "battlefield", pid="p2")
    own = put(s, "Grizzly Bears", "battlefield")
    cast_cost(s, name, [reveal], [victim.id] if name == "Induce Despair" else [])
    assert s.state.cards[reveal.id].zone == "p1:hand"
    roundtrip(s)
    answer(s)
    p = Plan(s.state, "p1", s.cards, None)
    if name == "Disaster Radius":
        assert s.state.cards[victim.id].damage == 3
        assert s.state.cards[own.id].damage == 0
    else:
        assert p.ch(s.state.cards[victim.id]).pt == (8, 8)


def test_soul_thrull_counter(cards):
    s = game(cards)
    thrull = put(s, "Basal Thrull", "battlefield")
    dead = put(s, "Grizzly Bears", "graveyard")
    cast_cost(s, "Soul Exchange", [thrull], [dead.id])
    roundtrip(s)
    answer(s)
    assert s.state.cards[thrull.id].zone == "p1:exile"
    assert s.state.cards[dead.id].zone == "p1:battlefield"
    assert s.state.cards[dead.id].counters.get("+2/+2") == 1


@pytest.mark.parametrize("discard,n", [("Woolly Thoctar", 4), ("Forest", 2)])
def test_stormscale_paid_colors(cards, discard, n):
    s = game(cards)
    source = put(s, "Stormscale Anarch", "battlefield")
    for cid in list(s.state.zones["p1:hand"]):
        act(s, "p1", type="move", card_ids=[cid], to={"player": "p1", "zone": "library"})
    victim = put(s, discard, "hand")
    wait_priority(s, "p1")
    act(s, "p1", type="add_mana", player="p1", mana=POOL)
    act(s, "p1", type="activate_ability", card_id=source.id, ability=0, targets=["p2"], sources=[])
    assert s.state.cards[victim.id].zone == "p1:graveyard"
    roundtrip(s)
    answer(s)
    assert s.state.players["p2"].life == 40 - n


def test_devourer_actual_cost_and_state_trigger(cards):
    s = game(cards)
    source = put(s, "Phyrexian Devourer", "battlefield")
    top = put(s, "Trained Armodon", "library")
    act(s, "p1", type="move", card_ids=[top.id], to={"player": "p1", "zone": "library"}, position="top")
    wait_priority(s, "p1")
    act(s, "p1", type="activate_ability", card_id=source.id, ability=1, sources=[])
    roundtrip(s)
    answer(s)
    assert s.state.cards[source.id].counters.get("+1/+1") == 3
    assert s.state.cards[source.id].zone == "p1:battlefield"
    top = put(s, "Darksteel Colossus", "library")
    act(s, "p1", type="move", card_ids=[top.id], to={"player": "p1", "zone": "library"}, position="top")
    wait_priority(s, "p1")
    act(s, "p1", type="activate_ability", card_id=source.id, ability=1, sources=[])
    answer(s)
    assert s.state.cards[source.id].zone == "p1:graveyard"


def test_nahiri_same_total_each_target(cards):
    s = game(cards)
    a = put(s, "Trained Armodon", "hand")
    b = put(s, "Sol Ring", "hand")
    one = put(s, "Darksteel Colossus", "battlefield", pid="p2")
    two = put(s, "Blightsteel Colossus", "battlefield", pid="p3")
    cast_cost(s, "Nahiri's Wrath", [a, b], [one.id, two.id], x_value=2, target_counts=[2])
    roundtrip(s)
    answer(s)
    assert s.state.cards[one.id].damage == 4
    assert s.state.cards[two.id].damage == 4


def test_curie_copies_old_battlefield_recipe(cards):
    s = game(cards)
    source = put(s, "Curie, Emergent Intelligence", "battlefield")
    donor = put(s, "Ornithopter", "battlefield")
    act(s, "p1", type="counter", card_ids=[donor.id], kind="+1/+1", delta=5)
    wait_priority(s, "p1")
    act(s, "p1", type="add_mana", player="p1", mana=POOL)
    act(
        s,
        "p1",
        type="activate_ability",
        card_id=source.id,
        ability=1,
        sources=[],
        cost_choices=[{"component": 1, "cards": [donor.id]}],
    )
    roundtrip(s)
    answer(s)
    ch = Plan(s.state, "p1", s.cards, None).ch(s.state.cards[source.id])
    assert ch.name == "Ornithopter" and ch.pt == (0, 2)
    assert any("draw cards equal to its base power" in a.text for a in ch.abilities)


def test_recall_returns_actual_discarded_card(cards):
    s = game(cards)
    c = put(s, "Trained Armodon", "hand")
    cast(s, "Recall", POOL, x_value=1)
    settle(s)
    roundtrip(s)
    choose(s, [c.id])
    settle(s)
    if s.state.rules.decision:
        assert c.id in {o.id for o in s.state.rules.decision.options}
        choose(s, [c.id])
        settle(s)
    roundtrip(s)
    assert s.state.cards[c.id].zone == "p1:hand"
    assert any(c.name == "Recall" and c.zone == "p1:exile" for c in s.state.cards.values())


def test_last_rites_caster_chooses_nonlands(cards):
    s = game(cards)
    c = put(s, "Forest", "hand")
    theirs = put(s, "Trained Armodon", "hand", pid="p2")
    land = put(s, "Forest", "hand", pid="p2")
    cast(s, "Last Rites", POOL, ["p2"])
    settle(s)
    choose(s, [c.id])
    settle(s)
    roundtrip(s)
    d = s.state.rules.decision
    assert (
        d.player == "p1"
        and theirs.id in {o.id for o in d.options}
        and land.id not in {o.id for o in d.options}
    )
    choose(s, [theirs.id])
    settle(s)
    assert s.state.cards[theirs.id].zone == "p2:graveyard" and s.state.cards[land.id].zone == "p2:hand"


def test_mind_roots_only_actual_discarded_land(cards):
    s = game(cards)
    for cid in list(s.state.zones["p2:hand"]):
        act(s, "p2", type="move", card_ids=[cid], to={"player": "p2", "zone": "library"})
    land = put(s, "Forest", "hand", pid="p2")
    creature = put(s, "Trained Armodon", "hand", pid="p2")
    old = put(s, "Mountain", "graveyard", pid="p2")
    cast(s, "Mind Roots", POOL, ["p2"])
    settle(s)
    roundtrip(s)
    d = s.state.rules.decision
    assert {o.id for o in d.options} == {land.id}
    choose(s, [land.id])
    settle(s)
    assert s.state.cards[land.id].zone == "p1:battlefield" and s.state.cards[land.id].tapped
    assert s.state.cards[old.id].zone == "p2:graveyard" and s.state.cards[creature.id].zone == "p2:graveyard"


def test_rites_random_number_and_pump(cards):
    s = game(cards)
    bear = put(s, "Grizzly Bears", "battlefield")
    put(s, "Forest", "hand")
    put(s, "Mountain", "hand")
    cast(s, "Rites of Initiation", POOL)
    settle(s)
    roundtrip(s)
    d = s.state.rules.decision
    assert d.options[0].id == "__number__"
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[], name="2")
    settle(s)
    assert Plan(s.state, "p1", s.cards, None).ch(s.state.cards[bear.id]).pt == (4, 2)
    roundtrip(s)


def test_tamiyo_chapter_two_investigates_twice(cards):
    s = game(cards)
    cast(s, "Tamiyo Meets the Story Circle", POOL)
    answer(s)
    c = put(s, "Forest", "hand")
    to_phase(s, "main1", 7)
    settle(s)
    roundtrip(s)
    choose(s, [c.id])
    answer(s)
    p = Plan(s.state, "p1", s.cards, None)
    clues = [c for c in s.state.cards.values() if c.zone == "p1:battlefield" and "Clue" in p.ch(c).subtypes]
    assert len(clues) == 2


def test_creeping_dread_shared_card_type(cards):
    s = game(cards)
    put(s, "Creeping Dread", "battlefield")
    for pid in ("p1", "p2", "p3"):
        for cid in list(s.state.zones[pid + ":hand"]):
            act(s, pid, type="move", card_ids=[cid], to={"player": pid, "zone": "library"})
    mine = put(s, "Trained Armodon", "hand")
    same = put(s, "Storm Crow", "hand", pid="p2")
    different = put(s, "Forest", "hand", pid="p3")
    to_phase(s, "upkeep", 7)
    answer(s)
    roundtrip(s)
    assert all(s.state.cards[c.id].zone.endswith(":graveyard") for c in [mine, same, different])
    assert s.state.players["p2"].life == 37 and s.state.players["p3"].life == 40


def test_pitchstone_optional_sacrifice_returns_exact_discard(cards):
    s = game(cards)
    wall = put(s, "Pitchstone Wall", "battlefield")
    c = put(s, "Trained Armodon", "hand")
    cast(s, "Recall", POOL, x_value=1)
    settle(s)
    choose(s, [c.id])
    settle(s)
    # Finish Recall without returning this card, leaving it for the Wall trigger.
    d = s.state.rules.decision
    choices = [o.id for o in d.options if o.id != c.id]
    if choices:
        choose(s, choices[:1])
    else:
        choose(s, [c.id])
    answer(s)
    roundtrip(s)
    assert s.state.cards[wall.id].zone == "p1:graveyard"
    assert s.state.cards[c.id].zone == "p1:hand"


def test_mishra_discard_mode_uses_actual_count(cards):
    s = game(cards)
    c = put(s, "Forest", "hand", pid="p2")
    bear = put(s, "Darksteel Colossus", "battlefield", pid="p2")
    before = drawn(s, "p2")
    cast(s, "Mishra's Command", POOL, ["p2", bear.id], x_value=2, modes=[0, 1], target_counts=[1, 1])
    settle(s)
    roundtrip(s)
    assert s.state.rules.decision.player == "p2"
    choose(s, [c.id])
    answer(s)
    assert drawn(s, "p2") == before + 1 and s.state.cards[bear.id].damage == 2


def test_howler_discard_count_native_target_pump(cards):
    s = game(cards)
    put(s, "Captain Howler, Sea Scourge", "battlefield")
    bear = put(s, "Grizzly Bears", "battlefield")
    c = put(s, "Forest", "hand")
    d = put(s, "Mountain", "hand")
    cast(s, "Recall", POOL, x_value=2)
    settle(s)
    choose(s, [c.id, d.id])
    settle(s)
    # Native Recall return choices precede the waiting discard trigger.
    while s.state.rules.decision and s.state.rules.decision.kind == "choose_cards":
        dec = s.state.rules.decision
        choose(s, [o.id for o in dec.options][: dec.min_choices])
        settle(s)
    dec = s.state.rules.decision
    assert dec is not None and bear.id in {o.id for o in dec.options}
    choose(s, [bear.id])
    answer(s)
    roundtrip(s)
    assert Plan(s.state, "p1", s.cards, None).ch(s.state.cards[bear.id]).pt == (6, 2)


def test_curie_actual_combat_draws_base_not_counters(cards):
    s = game(cards)
    source = put(s, "Curie, Emergent Intelligence", "battlefield")
    act(s, "p1", type="counter", card_ids=[source.id], kind="+1/+1", delta=3)
    to_phase(s, "declare_attackers", 7)
    before = drawn(s)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": source.id, "target": "p2"}])
    to_phase(s, "main2", 7)
    answer(s)
    roundtrip(s)
    assert s.state.players["p2"].life == 36
    assert drawn(s) == before + 1


def test_stormscale_insufficient_mana_does_not_discard(cards):
    from app.game.errors import ActionError

    s = game(cards)
    source = put(s, "Stormscale Anarch", "battlefield")
    put(s, "Woolly Thoctar", "hand")
    before = s.state.model_dump(mode="json")
    wait_priority(s, "p1")
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=source.id, ability=0, targets=["p2"], sources=[])
    assert s.state.model_dump(mode="json") == before


def test_pitchstone_actual_cost_discard_returns_card(cards):
    s = game(cards)
    wall = put(s, "Pitchstone Wall", "battlefield")
    c = put(s, "Trained Armodon", "hand")
    cast_cost(s, "Nahiri's Wrath", [c], [], x_value=1, target_counts=[0])
    answer(s)
    roundtrip(s)
    assert s.state.cards[wall.id].zone == "p1:graveyard" and s.state.cards[c.id].zone == "p1:hand"


def test_nahiri_zero_cost_cards_is_real_zero_not_legacy(cards):
    s = game(cards)
    spell = cast_cost(s, "Nahiri's Wrath", [], [], x_value=0, target_counts=[0])
    paid = s.state.rules.payments[Plan(s.state, "p1", s.cards, None).oid(spell.id)]
    assert paid.discarded_facts == []
    answer(s)
    roundtrip(s)
    assert s.state.rules.decision is None


def test_howler_actual_ward_combined_cost(cards):
    s = game(cards)
    source = put(s, "Captain Howler, Sea Scourge", "battlefield")
    cast(s, "Lightning Bolt", POOL, [source.id], pid="p2")
    answer(s)
    roundtrip(s)
    assert s.state.players["p2"].life == 38 and s.state.cards[source.id].damage == 3


def test_paid_reveal_fresh_process_and_legacy_fallback(cards, tmp_path):
    import subprocess
    import sys

    s = game(cards)
    reveal = put(s, "Trained Armodon", "hand")
    victim = put(s, "Darksteel Colossus", "battlefield", pid="p2")
    spell = cast_cost(s, "Disaster Radius", [reveal])
    saved = tmp_path / "reveal.json"
    saved.write_text(s.state.model_dump_json())
    code = """
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.test_rules_mana_delayed_effects import answer
save,db,victim=sys.argv[1:]
r=CardRepository(Path(db),ImageStore(Path(db).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(save).read_text()),cards=r)
answer(s)
assert s.state.cards[victim].damage==3
assert s.history.rebuild().model_dump(mode='json')==s.state.model_dump(mode='json')
r.close()
"""
    result = subprocess.run(
        [sys.executable, "-c", code, str(saved), str(cards.db_path), victim.id],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert result.returncode == 0, result.stderr
    receipt = s.state.rules.payments[Plan(s.state, "p1", s.cards, None).oid(spell.id)]
    receipt.revealed_facts = None
    from app.game.session import GameSession
    from app.game.state import GameState

    old = GameSession(GameState.model_validate_json(s.state.model_dump_json()), cards=cards)
    settle(old)
    d = old.state.rules.decision
    assert d is not None and d.kind == "manual_resolution"
    assert "older save" in d.prompt
    choose(old, ["done"])
    roundtrip(old)


def test_discard_choose_hand_chain_fresh_process(cards, tmp_path):
    import subprocess
    import sys

    s = game(cards)
    mine = put(s, "Forest", "hand")
    theirs = put(s, "Trained Armodon", "hand", pid="p2")
    cast(s, "Last Rites", POOL, ["p2"])
    settle(s)
    choose(s, [mine.id])
    settle(s)
    assert s.state.rules.decision.player == "p1"
    saved = tmp_path / "rites.json"
    saved.write_text(s.state.model_dump_json())
    code = """
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.game_helpers import act
from tests.test_rules_designations import settle
save,db,victim=sys.argv[1:]
r=CardRepository(Path(db),ImageStore(Path(db).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(save).read_text()),cards=r)
d=s.state.rules.decision
act(s,d.player,type='choose',decision_id=d.id,option_ids=[victim])
settle(s)
assert s.state.cards[victim].zone=='p2:graveyard'
assert s.history.rebuild().model_dump(mode='json')==s.state.model_dump(mode='json')
r.close()
"""
    result = subprocess.run(
        [sys.executable, "-c", code, str(saved), str(cards.db_path), theirs.id],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert result.returncode == 0, result.stderr


def next_decision(s):
    for _ in range(50):
        if s.state.rules.decision is not None or not s.state.zones.get("stack"):
            return s.state.rules.decision
        act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("No decision reached")


def madness_before_wall(cards, accept=False):
    s = game(cards)
    wall = put(s, "Pitchstone Wall", "battlefield")
    root = put(s, "Basking Rootwalla", "hand")
    cast_cost(s, "Nahiri's Wrath", [root], [], x_value=1, target_counts=[0])
    d = next_decision(s)
    assert d is not None and d.kind == "order"
    choose(s, [o.id for o in sorted(d.options, key=lambda o: 0 if "Pitchstone" in o.label else 1)])
    d = next_decision(s)
    assert d is not None and "Madness" in d.prompt
    choose(s, ["yes" if accept else "no"])
    return s, wall, root


def test_wall_follows_declined_madness_public_transition(cards):
    s, wall, root = madness_before_wall(cards)
    assert s.state.cards[root.id].zone == "p1:graveyard"
    roundtrip(s)
    answer(s)
    assert s.state.cards[wall.id].zone == "p1:graveyard"
    assert s.state.cards[root.id].zone == "p1:hand"
    roundtrip(s)


def test_wall_does_not_follow_cast_madness_spell(cards):
    s, wall, root = madness_before_wall(cards, accept=True)
    answer(s)
    assert s.state.cards[wall.id].zone == "p1:graveyard"
    assert s.state.cards[root.id].zone == "p1:battlefield"
    roundtrip(s)


def test_wall_does_not_follow_new_graveyard_incarnation(cards):
    s, wall, root = madness_before_wall(cards)
    declined_oid = Plan(s.state, "p1", s.cards, None).oid(root.id)
    reclaim = cast(s, "Reclaim", POOL, [root.id])
    # Resolve only the response, leaving the Wall trigger on the stack.
    for _ in range(20):
        if s.state.cards[reclaim.id].zone != "stack":
            break
        assert s.state.rules.decision is None
        act(s, s.state.rules.priority, type="pass_priority")
    assert s.state.cards[root.id].zone == "p1:library"
    scour = cast(s, "Thought Scour", POOL, ["p1"])
    for _ in range(20):
        if s.state.cards[scour.id].zone != "stack":
            break
        assert s.state.rules.decision is None
        act(s, s.state.rules.priority, type="pass_priority")
    assert s.state.cards[root.id].zone == "p1:graveyard"
    assert Plan(s.state, "p1", s.cards, None).oid(root.id) != declined_oid
    answer(s)
    assert s.state.cards[wall.id].zone == "p1:graveyard"
    assert s.state.cards[root.id].zone == "p1:graveyard"
    roundtrip(s)


def test_wall_declined_madness_mapping_fresh_process(cards, tmp_path):
    import subprocess
    import sys

    s, wall, root = madness_before_wall(cards)
    d = next_decision(s)
    assert d is not None and "Pitchstone Wall" in d.prompt
    saved = tmp_path / "wall.json"
    saved.write_text(s.state.model_dump_json())
    code = """
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.test_rules_mana_delayed_effects import answer
save,db,wall,root=sys.argv[1:]
r=CardRepository(Path(db),ImageStore(Path(db).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(save).read_text()),cards=r)
answer(s)
assert s.state.cards[wall].zone=='p1:graveyard'
assert s.state.cards[root].zone=='p1:hand'
assert s.history.rebuild().model_dump(mode='json')==s.state.model_dump(mode='json')
r.close()
"""
    result = subprocess.run(
        [sys.executable, "-c", code, str(saved), str(cards.db_path), wall.id, root.id],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert result.returncode == 0, result.stderr

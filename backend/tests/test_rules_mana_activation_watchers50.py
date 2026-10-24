from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.rules import casting, coverage
from app.rules.plan import Plan
from tests.game_helpers import act, mana_pool
from tests.test_rules_activated_copy_family import answer
from tests.test_rules_bandmate_references import wait_priority
from tests.test_rules_designations import put
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase


@pytest.fixture
def cards():
    r = CardRepository(
        Path(__file__).resolve().parents[2] / "data/cards.sqlite",
        ImageStore(Path(__file__).resolve().parents[2] / "data/images"),
    )
    yield r
    r.close()


@pytest.mark.parametrize(
    "name", ["Elrond, Moon-Reader", "Avalanche of Sector 7", "Ceaseless Searblades", "Sarkhan's Whelp"]
)
def test_canonical_whole_card_coverage(cards, name):
    result = coverage.of_card_data(cards.resolve(name))
    assert result.level == "FULL", result




def native_setup(cards, watcher, extra):
    s = table(cards, [watcher, *extra], [], [])
    w = put(s, watcher, "battlefield")
    to_phase(s, "main1", 4)
    wait_priority(s, "p1")
    act(s, "p1", type="set_prefs", hold_priority=True, auto_resolve_own_triggers="off")
    return s, w


def cast_fireblood(s, cards):
    source = put(s, "Sarkhan, Fireblood", "hand")
    act(s, "p1", type="add_mana", player="p1", mana={"C": 1, "R": 2})
    act(s, "p1", type="cast_spell", card_id=source.id, sources=[])
    answer(s)
    wait_priority(s, "p1")
    assert s.state.cards[source.id].counters.get("loyalty") == 3
    return s.state.cards[source.id]


def activate_mana(s, cards, source, pid="p1"):
    index = next(i for i, ab in casting.mana_abilities(s.state, source, cards))
    act(s, pid, type="activate_ability", card_id=source.id, ability=index)


def test_ceaseless_actual_elemental_mana_activation_uses_stack_for_trigger_only(cards):
    s, w = native_setup(cards, "Ceaseless Searblades", ["Leafkin Druid"])
    source = put(s, "Leafkin Druid", "battlefield")
    to_phase(s, "main1", 7)
    wait_priority(s, "p1")
    before = Plan(s.state, "p1", cards, None).ch(w).pt
    activate_mana(s, cards, source)
    assert mana_pool(s, "p1").get("G") == 1
    assert not any(e.kind == "activated" for e in s.state.rules.stack.values())
    answer(s)
    assert Plan(s.state, "p1", cards, None).ch(w).pt == (before[0] + 1, before[1])


def test_elrond_actual_creature_mana_triggers_once_and_artifact_does_not(cards):
    s, w = native_setup(cards, "Elrond, Moon-Reader", ["Llanowar Elves", "Elvish Mystic", "Sol Ring"])
    elf = put(s, "Llanowar Elves", "battlefield")
    mystic = put(s, "Elvish Mystic", "battlefield")
    ring = put(s, "Sol Ring", "battlefield")
    to_phase(s, "main1", 7)
    wait_priority(s, "p1")
    def count():
        return sum(c.zone == "p1:hand" for c in s.state.cards.values())
    n = count()
    activate_mana(s, cards, ring)
    answer(s)
    assert count() == n
    activate_mana(s, cards, elf)
    answer(s)
    assert count() == n + 1
    activate_mana(s, cards, mystic)
    answer(s)
    assert count() == n + 1


def test_avalanche_actual_opponent_artifact_mana_activation_deals_one(cards):
    s = table(cards, ["Avalanche of Sector 7"], ["Sol Ring"], [])
    w = put(s, "Avalanche of Sector 7", "battlefield")
    source = put(s, "Sol Ring", "battlefield", pid="p2")
    to_phase(s, "main1", 4)
    wait_priority(s, "p2")
    act(s, "p2", type="set_prefs", hold_priority=True, auto_resolve_own_triggers="off")
    assert Plan(s.state, "p1", cards, None).ch(w).pt[0] == 1
    n = s.state.players["p2"].life
    activate_mana(s, cards, source, pid="p2")
    assert mana_pool(s, "p2").get("C") == 2
    answer(s)
    assert s.state.players["p2"].life == n - 1


def test_whelp_actual_sarkhan_loyalty_activation_deals_to_chosen_target(cards):
    s, w = native_setup(cards, "Sarkhan's Whelp", ["Sarkhan, Fireblood"])
    source = cast_fireblood(s, cards)
    abilities = Plan(s.state, "p1", cards, None).ch(source).abilities
    index = next(a.index for a in abilities if a.kind == "loyalty" and "Add" in a.text)
    act(s, "p1", type="activate_ability", card_id=source.id, ability=index)
    for _ in range(10):
        d = s.state.rules.decision
        if d is None:
            break
        options = {o.id for o in d.options}
        chosen = ["p2"] if "p2" in options else [d.options[0].id]
        act(s, d.player, type="choose", decision_id=d.id, option_ids=chosen)
    answer(s)
    assert s.state.players["p2"].life == 39


@pytest.mark.parametrize("watcher", ["Elrond, Moon-Reader", "Ceaseless Searblades"])
def test_creature_mana_activation_source_sacrificed_uses_exact_battlefield_lki(cards, watcher):
    s, w = native_setup(cards, watcher, ["Generator Servant"])
    source = put(s, "Generator Servant", "battlefield")
    to_phase(s, "main1", 7)
    wait_priority(s, "p1")
    hand = sum(c.zone == "p1:hand" for c in s.state.cards.values())
    pt = Plan(s.state, "p1", cards, None).ch(w).pt
    activate_mana(s, cards, source)
    assert s.state.cards[source.id].zone == "p1:graveyard"
    assert (
        s.state.players["p1"].mana.get("C", 0) + sum(u.sym == "C" for u in s.state.players["p1"].mana_units)
        == 2
    )
    answer(s)
    if watcher.startswith("Elrond"):
        assert sum(c.zone == "p1:hand" for c in s.state.cards.values()) == hand + 1
    else:
        assert Plan(s.state, "p1", cards, None).ch(w).pt == (pt[0] + 1, pt[1])


def test_ceaseless_hand_elemental_landcycling_does_not_count_as_elemental_permanent(cards):
    s, w = native_setup(cards, "Ceaseless Searblades", ["Igneous Pouncer"])
    source = put(s, "Igneous Pouncer", "hand")
    index = next(
        a.index for a in Plan(s.state, "p1", cards, None).ch(source).abilities if "cycling" in a.text.lower()
    )
    before = Plan(s.state, "p1", cards, None).ch(w).pt
    act(s, "p1", type="add_mana", player="p1", mana={"C": 2})
    act(s, "p1", type="activate_ability", card_id=source.id, ability=index)
    answer(s)
    assert Plan(s.state, "p1", cards, None).ch(w).pt == before


@pytest.mark.parametrize("count", [0, 1, 2])
def test_elrond_actual_second_ability_exiles_selected_other_nonlands_until_next_end(cards, count):
    s, w = native_setup(cards, "Elrond, Moon-Reader", ["Sol Ring", "Arcane Signet"])
    targets = [put(s, n, "battlefield") for n in ["Sol Ring", "Arcane Signet"]][:count]
    refs = [s.state.rules.object_id(c.id) for c in targets]
    index = next(a.index for a in Plan(s.state, "p1", cards, None).ch(w).abilities if a.kind == "activated")
    act(s, "p1", type="add_mana", player="p1", mana={"C": 5, "U": 2})
    act(
        s,
        "p1",
        type="activate_ability",
        card_id=w.id,
        ability=index,
        targets=[c.id for c in targets],
        target_counts=[count],
        sources=[],
    )
    answer(s)
    assert all(s.state.cards[c.id].zone == "p1:exile" for c in targets)
    to_phase(s, "end", 4)
    answer(s)
    assert all(s.state.cards[c.id].zone == "p1:battlefield" for c in targets)
    assert all(s.state.rules.object_id(c.id) != oid for c, oid in zip(targets, refs, strict=False))


@pytest.mark.parametrize("watcher", ["Elrond, Moon-Reader", "Ceaseless Searblades"])
def test_true_cold_pending_mana_activation_trigger_keeps_exact_source_incarnation(cards, tmp_path, watcher):
    import subprocess
    import sys

    s, w = native_setup(cards, watcher, ["Leafkin Druid"])
    source = put(s, "Leafkin Druid", "battlefield")
    to_phase(s, "main1", 7)
    wait_priority(s, "p1")
    before = sum(c.zone == "p1:hand" for c in s.state.cards.values())
    pt = Plan(s.state, "p1", cards, None).ch(w).pt
    activate_mana(s, cards, source)
    assert any(e.kind == "trigger" for e in s.state.rules.stack.values())
    oid = s.state.rules.object_id(w.id)
    act(s, "p1", type="move", card_ids=[w.id], to={"player": "p1", "zone": "graveyard"})
    act(s, "p1", type="move", card_ids=[w.id], to={"player": "p1", "zone": "battlefield"})
    assert s.state.rules.object_id(w.id) != oid
    saved = tmp_path / "activation.json"
    saved.write_text(s.state.model_dump_json())
    code = r"""
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.state import GameState
from app.game.session import GameSession
from app.rules.plan import Plan
from tests.test_rules_activated_copy_family import answer
repo=CardRepository(Path.cwd().parent/'data/cards.sqlite',ImageStore(Path.cwd().parent/'data/images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
s.view('p3')
answer(s)
w=s.state.cards[sys.argv[2]]
if w.name.startswith('Elrond'):
 assert sum(c.zone=='p1:hand' for c in s.state.cards.values())==int(sys.argv[3])+1
else:
 assert Plan(s.state,'p1',repo,None).ch(w).pt==(int(sys.argv[4]),int(sys.argv[5]))
assert GameState.model_validate_json(s.state.model_dump_json())==s.state
"""
    run = subprocess.run(
        [sys.executable, "-c", code, str(saved), w.id, str(before), str(pt[0]), str(pt[1])],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert run.returncode == 0, run.stderr


@pytest.mark.parametrize("bad", ["self", "land", "opponent"])
def test_elrond_second_ability_illegal_target_refuses_atomically(cards, bad):
    from app.game.errors import ActionError

    s = table(cards, ["Elrond, Moon-Reader", "Plains"], ["Sol Ring"], [])
    w = put(s, "Elrond, Moon-Reader", "battlefield")
    land = put(s, "Plains", "battlefield")
    other = put(s, "Sol Ring", "battlefield", pid="p2")
    to_phase(s, "main1", 4)
    wait_priority(s, "p1")
    index = next(a.index for a in Plan(s.state, "p1", cards, None).ch(w).abilities if a.kind == "activated")
    act(s, "p1", type="add_mana", player="p1", mana={"C": 5, "U": 2})
    target = {"self": w, "land": land, "opponent": other}[bad]
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(
            s,
            "p1",
            type="activate_ability",
            card_id=w.id,
            ability=index,
            targets=[target.id],
            target_counts=[1],
            sources=[],
        )
    assert s.state.model_dump_json() == before


@pytest.mark.parametrize("kind", ["own_artifact", "opponent_creature"])
def test_avalanche_activation_negatives(cards, kind):
    s = table(cards, ["Avalanche of Sector 7", "Sol Ring"], ["Llanowar Elves"], [])
    put(s, "Avalanche of Sector 7", "battlefield")
    own = put(s, "Sol Ring", "battlefield")
    other = put(s, "Llanowar Elves", "battlefield", pid="p2")
    to_phase(s, "main1", 7)
    pid = "p1" if kind == "own_artifact" else "p2"
    wait_priority(s, pid)
    act(s, pid, type="set_prefs", hold_priority=True)
    before = {p: v.life for p, v in s.state.players.items()}
    activate_mana(s, cards, own if kind == "own_artifact" else other, pid=pid)
    answer(s)
    assert {p: v.life for p, v in s.state.players.items()} == before


def test_avalanche_sacrificed_opponent_artifact_uses_lki_controller(cards):
    s = table(cards, ["Avalanche of Sector 7"], ["Lotus Petal"], [])
    put(s, "Avalanche of Sector 7", "battlefield")
    source = put(s, "Lotus Petal", "battlefield", pid="p2")
    to_phase(s, "main1", 4)
    wait_priority(s, "p2")
    act(s, "p2", type="set_prefs", hold_priority=True)
    activate_mana(s, cards, source, pid="p2")
    answer(s)
    assert s.state.cards[source.id].zone == "p2:graveyard"
    assert s.state.players["p2"].life == 39


@pytest.mark.parametrize("zone", ["hand", "graveyard", "exile", "battlefield"])
def test_avalanche_power_cda_counts_all_opponents_artifacts_in_every_zone(cards, zone):
    s = table(cards, ["Avalanche of Sector 7", "Sol Ring"], ["Arcane Signet"], ["Ornithopter"])
    w = put(s, "Avalanche of Sector 7", zone)
    put(s, "Sol Ring", "battlefield")
    a = put(s, "Arcane Signet", "battlefield", pid="p2")
    b = put(s, "Ornithopter", "battlefield", pid="p3")
    assert Plan(s.state, "p1", cards, None).ch(w).pt[0] == 2
    act(s, "p1", type="set_controller", card_ids=[a.id], player="p1")
    assert Plan(s.state, "p1", cards, None).ch(w).pt[0] == 1
    act(s, "p1", type="move", card_ids=[b.id], to={"player": "p3", "zone": "graveyard"})
    assert Plan(s.state, "p1", cards, None).ch(w).pt[0] == 0


@pytest.mark.parametrize(
    "watcher,reason", [("Avalanche of Sector 7", "menace"), ("Sarkhan's Whelp", "flying")]
)
def test_printed_evasion_refuses_ground_single_blocker(cards, watcher, reason):
    from app.game.errors import ActionError

    s = table(cards, [watcher], ["Grizzly Bears", "Sol Ring"], [])
    w = put(s, watcher, "battlefield")
    guard = put(s, "Grizzly Bears", "battlefield", pid="p2")
    put(s, "Sol Ring", "battlefield", pid="p2")
    to_phase(s, "declare_attackers", 4)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": w.id, "target": "p2"}])
    to_phase(s, "declare_blockers", 4)
    with pytest.raises(ActionError, match=reason):
        act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": guard.id, "attacker_id": w.id}])


def test_elrond_once_gate_resets_next_turn_and_noncreature_does_not_consume_it(cards):
    s, w = native_setup(cards, "Elrond, Moon-Reader", ["Llanowar Elves", "Sol Ring"])
    elf = put(s, "Llanowar Elves", "battlefield")
    ring = put(s, "Sol Ring", "battlefield")
    to_phase(s, "main1", 7)
    wait_priority(s, "p1")
    def count():
        return sum(c.zone == "p1:hand" for c in s.state.cards.values())
    n = count()
    activate_mana(s, cards, ring)
    answer(s)
    assert count() == n
    activate_mana(s, cards, elf)
    answer(s)
    assert count() == n + 1
    to_phase(s, "main1", 10)
    wait_priority(s, "p1")
    n = count()
    activate_mana(s, cards, elf)
    answer(s)
    assert count() == n + 1


def test_ceaseless_bonus_expires_at_turn_cleanup(cards):
    s, w = native_setup(cards, "Ceaseless Searblades", ["Leafkin Druid"])
    source = put(s, "Leafkin Druid", "battlefield")
    to_phase(s, "main1", 7)
    wait_priority(s, "p1")
    pt = Plan(s.state, "p1", cards, None).ch(w).pt
    activate_mana(s, cards, source)
    answer(s)
    assert Plan(s.state, "p1", cards, None).ch(w).pt == (pt[0] + 1, pt[1])
    to_phase(s, "main1", 8)
    assert Plan(s.state, "p1", cards, None).ch(w).pt == pt


def test_true_cold_elrond_delayed_return_survives_source_departure(cards, tmp_path):
    import subprocess
    import sys

    s, w = native_setup(cards, "Elrond, Moon-Reader", ["Sol Ring", "Arcane Signet"])
    targets = [put(s, n, "battlefield") for n in ["Sol Ring", "Arcane Signet"]]
    index = next(a.index for a in Plan(s.state, "p1", cards, None).ch(w).abilities if a.kind == "activated")
    act(s, "p1", type="add_mana", player="p1", mana={"C": 5, "U": 2})
    act(
        s,
        "p1",
        type="activate_ability",
        card_id=w.id,
        ability=index,
        targets=[c.id for c in targets],
        target_counts=[2],
        sources=[],
    )
    answer(s)
    assert all(s.state.cards[c.id].zone == "p1:exile" for c in targets)
    act(s, "p1", type="move", card_ids=[w.id], to={"player": "p1", "zone": "graveyard"})
    saved = tmp_path / "delayed.json"
    saved.write_text(s.state.model_dump_json())
    code = r"""
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.state import GameState
from app.game.session import GameSession
from tests.test_rules_wave30m_durations import to_phase
from tests.test_rules_activated_copy_family import answer
repo=CardRepository(Path.cwd().parent/'data/cards.sqlite',ImageStore(Path.cwd().parent/'data/images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
s.view('p3')
to_phase(s,'end',4);answer(s)
assert all(s.state.cards[c].zone=='p1:battlefield' for c in sys.argv[2:])
assert GameState.model_validate_json(s.state.model_dump_json())==s.state
"""
    run = subprocess.run(
        [sys.executable, "-c", code, str(saved), *[c.id for c in targets]],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert run.returncode == 0, run.stderr


def test_elrond_exiled_token_ceases_and_is_not_returned(cards):
    s, w = native_setup(cards, "Elrond, Moon-Reader", [])
    act(
        s,
        "p1",
        type="create_token",
        player="p1",
        token={
            "name": "Blink Witness",
            "type_line": "Token Creature — Bear",
            "power": "2",
            "toughness": "2",
            "text": "",
        },
    )
    token = next(c for c in s.state.cards.values() if c.name == "Blink Witness")
    index = next(a.index for a in Plan(s.state, "p1", cards, None).ch(w).abilities if a.kind == "activated")
    act(s, "p1", type="add_mana", player="p1", mana={"C": 5, "U": 2})
    act(
        s,
        "p1",
        type="activate_ability",
        card_id=w.id,
        ability=index,
        targets=[token.id],
        target_counts=[1],
        sources=[],
    )
    answer(s)
    assert token.id not in s.state.cards
    to_phase(s, "end", 4)
    answer(s)
    assert token.id not in s.state.cards


def test_whelp_actual_sarkhan_gained_mana_ability_triggers_without_stack_ability(cards):
    s, w = native_setup(
        cards,
        "Sarkhan's Whelp",
        ["Sarkhan, Fireblood", "Liquimetal Torque", "March of the Machines", "Cryptolith Rite"],
    )
    source = cast_fireblood(s, cards)
    torque = put(s, "Liquimetal Torque", "battlefield")
    put(s, "March of the Machines", "battlefield")
    put(s, "Cryptolith Rite", "battlefield")
    to_phase(s, "main1", 7)
    wait_priority(s, "p1")
    index = next(
        a.index
        for a in Plan(s.state, "p1", cards, None).ch(torque).abilities
        if a.kind == "activated" and "becomes an artifact" in a.text
    )
    act(s, "p1", type="activate_ability", card_id=torque.id, ability=index, targets=[source.id])
    answer(s)
    wait_priority(s, "p1")
    ch = Plan(s.state, "p1", cards, None).ch(source)
    assert {"Artifact", "Creature", "Planeswalker"} <= ch.types and "Sarkhan" in ch.subtypes
    activate_mana(s, cards, source)
    assert not any(e.kind == "activated" for e in s.state.rules.stack.values())
    for _ in range(10):
        d = s.state.rules.decision
        if d is None:
            break
        options = {o.id for o in d.options}
        chosen = ["p2"] if "p2" in options else [d.options[0].id]
        act(s, d.player, type="choose", decision_id=d.id, option_ids=chosen)
    answer(s)
    assert s.state.players["p2"].life == 39


@pytest.mark.parametrize("watcher", ["Avalanche of Sector 7", "Sarkhan's Whelp"])
def test_true_cold_pending_damage_activation_trigger_survives_watcher_departure(cards, tmp_path, watcher):
    import subprocess
    import sys

    s = table(cards, [watcher, "Sarkhan, Fireblood"], ["Sol Ring"], [])
    w = put(s, watcher, "battlefield")
    if watcher.startswith("Avalanche"):
        source = put(s, "Sol Ring", "battlefield", pid="p2")
        pid = "p2"
    else:
        source = None
        pid = "p1"
    to_phase(s, "main1", 4)
    wait_priority(s, pid)
    if source is None:
        source = cast_fireblood(s, cards)
    act(s, pid, type="set_prefs", hold_priority=True, auto_resolve_own_triggers="off")
    if pid == "p2":
        activate_mana(s, cards, source, pid=pid)
    else:
        index = next(
            a.index
            for a in Plan(s.state, pid, cards, None).ch(source).abilities
            if a.kind == "loyalty" and "Add" in a.text
        )
        act(s, pid, type="activate_ability", card_id=source.id, ability=index)
        for _ in range(10):
            d = s.state.rules.decision
            if d is None:
                break
            options = {o.id for o in d.options}
            act(
                s,
                d.player,
                type="choose",
                decision_id=d.id,
                option_ids=["p2"] if "p2" in options else [d.options[0].id],
            )
    assert any(e.kind == "trigger" for e in s.state.rules.stack.values())
    act(s, "p1", type="move", card_ids=[w.id], to={"player": "p1", "zone": "graveyard"})
    saved = tmp_path / "damage.json"
    saved.write_text(s.state.model_dump_json())
    code = r"""
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.state import GameState
from app.game.session import GameSession
from tests.test_rules_activated_copy_family import answer
repo=CardRepository(Path.cwd().parent/'data/cards.sqlite',ImageStore(Path.cwd().parent/'data/images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
s.view('p3');answer(s)
assert s.state.players['p2'].life==39
assert GameState.model_validate_json(s.state.model_dump_json())==s.state
"""
    run = subprocess.run(
        [sys.executable, "-c", code, str(saved)],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert run.returncode == 0, run.stderr


@pytest.mark.parametrize("watcher,pid", [("Elrond, Moon-Reader", "p2"), ("Ceaseless Searblades", "p1")])
def test_creature_activation_wrong_actor_or_type_does_not_trigger(cards, watcher, pid):
    s = table(cards, [watcher, "Llanowar Elves"], ["Llanowar Elves"], [])
    w = put(s, watcher, "battlefield")
    source = put(s, "Llanowar Elves", "battlefield", pid=pid)
    to_phase(s, "main1", 4)
    wait_priority(s, pid)
    def count():
        return sum(c.zone == "p1:hand" for c in s.state.cards.values())
    n = count()
    pt = Plan(s.state, "p1", cards, None).ch(w).pt
    activate_mana(s, cards, source, pid=pid)
    answer(s)
    assert count() == n and Plan(s.state, "p1", cards, None).ch(w).pt == pt


def test_whelp_unrelated_planeswalker_activation_does_not_trigger(cards):
    s, w = native_setup(cards, "Sarkhan's Whelp", ["Jace Beleren"])
    source = put(s, "Jace Beleren", "hand")
    act(s, "p1", type="add_mana", player="p1", mana={"C": 1, "U": 2})
    act(s, "p1", type="cast_spell", card_id=source.id, sources=[])
    answer(s)
    wait_priority(s, "p1")
    index = next(
        a.index
        for a in Plan(s.state, "p1", cards, None).ch(source).abilities
        if a.kind == "loyalty" and "Each player draws" in a.text
    )
    act(s, "p1", type="activate_ability", card_id=source.id, ability=index)
    answer(s)
    assert all(p.life == 40 for p in s.state.players.values())


def test_elrond_native_spark_double_copy_has_independent_once_each_turn_gate(cards):
    from tests.test_rules_designations import settle

    s, w = native_setup(cards, "Elrond, Moon-Reader", ["Llanowar Elves", "Elvish Mystic", "Spark Double"])
    elf = put(s, "Llanowar Elves", "battlefield")
    mystic = put(s, "Elvish Mystic", "battlefield")
    copy = put(s, "Spark Double", "hand")
    act(s, "p1", type="add_mana", player="p1", mana={"C": 3, "U": 1})
    act(s, "p1", type="cast_spell", card_id=copy.id, sources=[])
    settle(s)
    d = s.state.rules.decision
    assert d is not None
    chosen = next(o.id for o in d.options if w.id in o.id)
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[chosen])
    answer(s)
    assert Plan(s.state, "p1", cards, None).ch(copy).name == "Elrond, Moon-Reader"
    assert s.state.cards[w.id].zone == "p1:battlefield"
    to_phase(s, "main1", 7)
    wait_priority(s, "p1")
    def count():
        return sum(c.zone == "p1:hand" for c in s.state.cards.values())
    n = count()
    activate_mana(s, cards, elf)
    answer(s)
    assert count() == n + 2
    activate_mana(s, cards, mystic)
    answer(s)
    assert count() == n + 2


@pytest.mark.parametrize("payment", ["auto", "self"])
def test_elrond_mana_activation_during_spell_payment_waits_until_costs_complete(cards, payment):
    s, w = native_setup(cards, "Elrond, Moon-Reader", ["Llanowar Elves", "Sol Ring", "Grizzly Bears"])
    elf = put(s, "Llanowar Elves", "battlefield")
    ring = put(s, "Sol Ring", "battlefield")
    spell = put(s, "Grizzly Bears", "hand")
    to_phase(s, "main1", 7)
    wait_priority(s, "p1")
    act(
        s,
        "p1",
        type="set_prefs",
        **({"payment": "self"} if payment == "self" else {}),
        hold_priority=True,
        auto_resolve_own_triggers="off",
    )
    def hand():
        return sum(c.zone == "p1:hand" for c in s.state.cards.values())
    def library():
        return sum(c.zone == "p1:library" for c in s.state.cards.values())
    n = hand()
    lib = library()
    act(s, "p1", type="cast_spell", card_id=spell.id)
    if payment == "self":
        assert s.state.rules.decision is not None
        activate_mana(s, cards, elf)
        assert library() == lib
        activate_mana(s, cards, ring)
        if s.state.cards[spell.id].zone == "p1:hand":
            d = s.state.rules.decision
            act(s, d.player, type="choose", decision_id=d.id, option_ids=["pay"])
    assert s.state.cards[spell.id].zone == "stack"
    assert library() == lib and hand() == n - 1
    assert s.state.rules.payments[s.state.rules.object_id(spell.id)].mana_spent == {"C": 1, "G": 1}
    answer(s)
    assert hand() == n and library() == lib - 1
    assert s.state.cards[spell.id].zone == "p1:battlefield"

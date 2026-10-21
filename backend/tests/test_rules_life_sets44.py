import pytest

from app.rules.plan import Plan
from tests.game_helpers import act
from tests.test_rules_conditional_prevention import cast
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_mixed_life44 import cards as cards
from tests.test_rules_shared_damage_choices import table

NAMES = [
    "Biorhythm",
    "Profane Transfusion",
    "Alhammarret's Archive",
    "Cleric Class",
    "Platinum Angel",
    "Platinum Emperion",
    "Grizzly Bears",
    "Llanowar Elves",
    "Blossoming Calm",
    "Gilded Light",
    "Jinnie Fay, Jetmir's Second",
]


def game(cards):
    return table(cards, NAMES, NAMES, NAMES)


def token(s):
    return next(
        c for c in s.state.cards.values() if c.token and c.name == "Horror" and c.zone == "p1:battlefield"
    )


def test_biorhythm_actual_mixed_counts_simultaneous_packet(cards):
    s = game(cards)
    for n in ["Grizzly Bears", "Llanowar Elves"]:
        put(s, n, "battlefield")
    put(s, "Grizzly Bears", "battlefield", "p2")
    put(s, "Platinum Angel", "battlefield", "p3")
    act(s, "p1", type="set_life", player="p1", value=1)
    cast(s, "Biorhythm")
    assert [s.state.players[p].life for p in ("p1", "p2", "p3")] == [2, 1, 1]
    events = [e for e in s.state.rules.events if e.kind in ("life_gain", "life_loss") and e.amount in (1, 39)]
    assert len({e.batch for e in events[-3:]}) == 1
    roundtrip(s)


def test_biorhythm_freezes_counts_before_replacement_question(cards):
    s = game(cards)
    for n in ["Grizzly Bears", "Llanowar Elves", "Alhammarret's Archive", "Cleric Class"]:
        put(s, n, "battlefield")
    put(s, "Grizzly Bears", "battlefield", "p2")
    put(s, "Platinum Angel", "battlefield", "p3")
    act(s, "p1", type="set_life", player="p1", value=1)
    cast(s, "Biorhythm")
    d = s.state.rules.decision
    assert d and d.resume["site"] == "life_changes44"
    assert [s.state.players[p].life for p in ("p1", "p2", "p3")] == [1, 40, 40]
    assert d.resume["request"]["changes"] == [["p1", 1], ["p2", -39], ["p3", -39]]
    act(s, d.player, type="choose", decision_id=d.id, option_ids=["yes"])
    settle(s)
    assert [s.state.players[p].life for p in ("p1", "p2", "p3")] == [4, 1, 1]
    roundtrip(s)


def test_profane_actual_post_exchange_size(cards):
    s = game(cards)
    put(s, "Alhammarret's Archive", "battlefield")
    act(s, "p1", type="set_life", player="p1", value=10)
    act(s, "p1", type="set_life", player="p2", value=17)
    cast(s, "Profane Transfusion", targets=["p1", "p2"], target_counts=[2])
    assert [s.state.players[p].life for p in ("p1", "p2")] == [24, 10]
    horror = token(s)
    ch = Plan(s.state, "p1", cards, None).ch(horror)
    assert (
        ch.pt == (14, 14)
        and ch.types == frozenset({"Artifact", "Creature"})
        and ch.subtypes == frozenset({"Horror"})
        and not ch.colors
    )
    roundtrip(s)


def test_profane_prohibited_exchange_still_uses_unchanged_difference(cards):
    s = game(cards)
    put(s, "Platinum Emperion", "battlefield")
    act(s, "p1", type="set_life", player="p1", value=10)
    act(s, "p1", type="set_life", player="p2", value=17)
    cast(s, "Profane Transfusion", targets=["p1", "p2"], target_counts=[2])
    assert [s.state.players[p].life for p in ("p1", "p2")] == [10, 17]
    assert Plan(s.state, "p1", cards, None).ch(token(s)).pt == (7, 7)
    roundtrip(s)


def test_biorhythm_zero_creatures_causes_native_loss_only_after_other_totals_set(cards):
    s = game(cards)
    put(s, "Grizzly Bears", "battlefield")
    put(s, "Llanowar Elves", "battlefield", "p3")
    cast(s, "Biorhythm")
    assert s.state.players["p2"].life == 0 and s.state.rules.lost.get("p2") == "0 or less life"
    assert "p1" not in s.state.rules.lost and "p3" not in s.state.rules.lost
    assert [s.state.players[p].life for p in ("p1", "p3")] == [1, 1]
    roundtrip(s)


def test_profane_targets_two_other_players_and_creator_stays_same(cards):
    s = game(cards)
    act(s, "p1", type="set_life", player="p2", value=10)
    act(s, "p1", type="set_life", player="p3", value=17)
    cast(s, "Profane Transfusion", targets=["p2", "p3"], target_counts=[2])
    assert [s.state.players[p].life for p in ("p1", "p2", "p3")] == [40, 17, 10]
    assert Plan(s.state, "p1", cards, None).ch(token(s)).pt == (7, 7)
    roundtrip(s)


def test_profane_signed_totals_use_signed_exchange_and_absolute_difference(cards):
    s = game(cards)
    put(s, "Platinum Angel", "battlefield")
    put(s, "Platinum Angel", "battlefield", "p2")
    act(s, "p1", type="set_life", player="p1", value=-2)
    act(s, "p1", type="set_life", player="p2", value=5)
    cast(s, "Profane Transfusion", targets=["p1", "p2"], target_counts=[2])
    assert [s.state.players[p].life for p in ("p1", "p2")] == [5, -2]
    assert Plan(s.state, "p1", cards, None).ch(token(s)).pt == (7, 7)
    roundtrip(s)


def test_profane_equal_life_still_creates_native_zero_zero_and_triggers_entry(cards):
    s = game(cards)
    # Actual Soul Warden must observe the 0/0 before the next state-based action.
    # It is part of the selected canonical fixture.
    # Add its physical card through normal initial deck setup.
    s = table(cards, [*NAMES, "Soul Warden"], NAMES, NAMES)
    put(s, "Soul Warden", "battlefield")
    act(s, "p1", type="set_life", player="p1", value=17)
    act(s, "p1", type="set_life", player="p2", value=17)
    cast(s, "Profane Transfusion", targets=["p1", "p2"], target_counts=[2])
    assert s.state.players["p1"].life == 18 and s.state.players["p2"].life == 17
    assert not any(
        c.token and c.name == "Horror" and c.zone.endswith(":battlefield") for c in s.state.cards.values()
    )
    roundtrip(s)


@pytest.mark.parametrize("both_illegal", [False, True])
def test_profane_initial_illegal_target_does_not_supply_life_info_or_create_token(cards, both_illegal):
    s = game(cards)
    act(s, "p1", type="set_life", player="p1", value=10)
    act(s, "p1", type="set_life", player="p2", value=17)
    cast(s, "Profane Transfusion", targets=["p1", "p2"], target_counts=[2], resolve=False)
    cast(s, "Blossoming Calm", pid="p2", resolve=False)
    if both_illegal:
        cast(s, "Gilded Light", pid="p1", resolve=False)
    settle(s)
    assert s.state.players["p1"].life == 10 and s.state.players["p2"].life == 19
    assert not any(c.token and c.name == "Horror" for c in s.state.cards.values())
    roundtrip(s)


def test_biorhythm_counts_current_creatures_tokens_and_excludes_phased_permanents(cards):
    s = game(cards)
    elf = put(s, "Llanowar Elves", "battlefield")
    phased = put(s, "Grizzly Bears", "battlefield")
    act(s, "p1", type="phase_shift", card_ids=[phased.id])
    act(
        s,
        "p1",
        type="create_token",
        token={"name": "Squirrel", "type_line": "Token Creature — Squirrel", "power": "1", "toughness": "1"},
    )
    put(s, "Grizzly Bears", "battlefield", "p2")
    act(s, "p1", type="set_controller", card_ids=[elf.id], player="p2")
    put(s, "Platinum Angel", "battlefield", "p3")
    cast(s, "Biorhythm")
    assert [s.state.players[p].life for p in ("p1", "p2", "p3")] == [1, 2, 1]
    assert s.state.cards[phased.id].zone == "p1:phased"
    roundtrip(s)


def test_biorhythm_player_life_lock_does_not_cancel_other_players_changes(cards):
    s = game(cards)
    put(s, "Platinum Emperion", "battlefield")
    put(s, "Grizzly Bears", "battlefield", "p2")
    put(s, "Llanowar Elves", "battlefield", "p3")
    act(s, "p1", type="set_life", player="p1", value=10)
    cast(s, "Biorhythm")
    assert [s.state.players[p].life for p in ("p1", "p2", "p3")] == [10, 1, 1]
    roundtrip(s)


@pytest.mark.parametrize("name", ["Biorhythm", "Profane Transfusion"])
def test_whole_canonical_printed_gate(cards, name):
    from app.rules import coverage

    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def test_profane_token_choice_keeps_frozen_post_exchange_size(cards):
    s = game(cards)
    put(s, "Jinnie Fay, Jetmir's Second", "battlefield")
    act(s, "p1", type="set_life", player="p1", value=10)
    act(s, "p1", type="set_life", player="p2", value=17)
    cast(s, "Profane Transfusion", targets=["p1", "p2"], target_counts=[2])
    d = s.state.rules.decision
    assert d
    assert [s.state.players[p].life for p in ("p1", "p2")] == [17, 10]
    act(s, "p1", type="set_life", player="p2", value=100)
    for _ in range(5):
        d = s.state.rules.decision
        if d is None:
            break
        option = next(
            (
                o.id
                for o in d.options
                if "horror" in o.label.lower() or "decline" in o.label.lower() or o.id == "no"
            ),
            None,
        )
        assert option is not None, [(o.id, o.label) for o in d.options]
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[option])
    settle(s)
    assert Plan(s.state, "p1", cards, None).ch(token(s)).pt == (7, 7)
    roundtrip(s)


@pytest.mark.parametrize("stage", ["biorhythm", "profane_life", "profane_token"])
def test_native_fresh_process_pending_life_or_token_choice(cards, tmp_path, stage):
    import subprocess
    import sys

    s = game(cards)
    if stage == "biorhythm":
        for name in ["Grizzly Bears", "Llanowar Elves", "Alhammarret's Archive", "Cleric Class"]:
            put(s, name, "battlefield")
        put(s, "Grizzly Bears", "battlefield", "p2")
        put(s, "Platinum Angel", "battlefield", "p3")
        act(s, "p1", type="set_life", player="p1", value=1)
        cast(s, "Biorhythm")
        assert [s.state.players[p].life for p in ("p1", "p2", "p3")] == [1, 40, 40]
    else:
        if stage == "profane_life":
            put(s, "Alhammarret's Archive", "battlefield")
            put(s, "Cleric Class", "battlefield")
        else:
            put(s, "Jinnie Fay, Jetmir's Second", "battlefield")
        act(s, "p1", type="set_life", player="p1", value=10)
        act(s, "p1", type="set_life", player="p2", value=17)
        cast(s, "Profane Transfusion", targets=["p1", "p2"], target_counts=[2])
        if stage == "profane_token":
            act(s, "p1", type="set_life", player="p2", value=100)
    assert s.state.rules.decision
    saved = tmp_path / "saved.json"
    saved.write_text(s.state.model_dump_json())
    code = r"""
import sys
from pathlib import Path
from app.cards.repository import CardRepository
from app.cards.images import ImageStore
from app.game.session import GameSession
from app.game.state import GameState
from app.rules.plan import Plan
from tests.test_rules_conditional_prevention import choose
from tests.test_rules_designations import settle,roundtrip
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
stage=sys.argv[3]
for _ in range(10):
 d=s.state.rules.decision
 if d is None:break
 desired='decline' if stage=='profane_token' else 'archive'
 option=next((o.id for o in d.options if desired in o.label.lower()),None)
 assert option is not None,[(o.id,o.label) for o in d.options]
 choose(s,[option])
settle(s)
assert s.state.rules.decision is None
if stage=='biorhythm':
 assert [s.state.players[p].life for p in ('p1','p2','p3')]==[4,1,1]
else:
 expected=(25,10,15) if stage=='profane_life' else (17,100,7)
 assert [s.state.players[p].life for p in ('p1','p2')]==list(expected[:2])
 tokens=[c for c in s.state.cards.values() if c.token and c.name=='Horror' and c.zone=='p1:battlefield']
 assert len(tokens)==1 and Plan(s.state,'p1',repo,None).ch(tokens[0]).pt==(expected[2],expected[2])
roundtrip(s)
"""
    result = subprocess.run(
        [sys.executable, "-c", code, str(saved), str(cards.db_path), stage], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stdout + result.stderr

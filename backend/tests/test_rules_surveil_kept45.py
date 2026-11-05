"""Surveil must return each remaining original card to top after replacements."""

import random

import pytest

from tests.game_helpers import act
from tests.test_rules_conditional_prevention import cast, choose
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_life_sequences44 import cards as cards
from tests.test_rules_life_sequences44 import game


def test_actual_curate_graveyard_shuffle_still_returns_remaining_card_to_top(cards, monkeypatch):
    import app.game.session as sessions

    original = sessions.resolve
    rng = random.Random(0)

    def resolve(*args, **kwargs):
        return original(*args, **{**kwargs, "rng": rng})  # (the session passes its own source too: this one replaces it)

    monkeypatch.setattr(sessions, "resolve", resolve)
    s = game(cards, ["Curate", "Progenitus"])
    source = put(s, "Curate", "hand")
    progenitus = put(s, "Progenitus", "hand")
    kept = put(s, "Healing Salve", "hand")
    act(
        s,
        "p1",
        type="move",
        card_ids=[progenitus.id, kept.id],
        to={"player": "p1", "zone": "library"},
        position="top",
    )
    cast(s, source.name)
    d = s.state.rules.decision
    assert d and {o.id for o in d.options} == {progenitus.id, kept.id}
    choose(s, [progenitus.id])
    assert progenitus.zone == "p1:library"
    assert kept.zone == "p1:hand"
    roundtrip(s)


@pytest.mark.parametrize("outcome", ["exile", "library:shuffle"])
def test_native_surveil_waits_for_actual_zone_replacement_before_drawing(cards, outcome):
    s = game(cards, ["Curate", "Progenitus", "Rest in Peace"])
    cast(s, "Rest in Peace")
    put(s, "Curate", "hand")
    progenitus = put(s, "Progenitus", "hand")
    kept = put(s, "Healing Salve", "hand")
    act(
        s,
        "p1",
        type="move",
        card_ids=[progenitus.id, kept.id],
        to={"player": "p1", "zone": "library"},
        position="top",
    )
    cast(s, "Curate")
    before = len(s.state.zones["p1:hand"])
    choose(s, [progenitus.id])
    d = s.state.rules.decision
    assert d and d.resume["step"] == "zone_replace_order"
    assert kept.zone == "p1:library" and len(s.state.zones["p1:hand"]) == before
    chosen = next(o.id for o in d.options if o.id.startswith(outcome))
    choose(s, [chosen])
    assert kept.zone == "p1:hand" and not s.state.rules.decision
    assert progenitus.zone == ("p1:exile" if outcome == "exile" else "p1:library")
    roundtrip(s)


@pytest.mark.parametrize("outcome", ["exile", "library:shuffle"])
def test_true_cold_at_native_surveil_zone_choice(cards, tmp_path, outcome):
    import subprocess
    import sys

    s = game(cards, ["Curate", "Progenitus", "Rest in Peace"])
    cast(s, "Rest in Peace")
    put(s, "Curate", "hand")
    progenitus = put(s, "Progenitus", "hand")
    kept = put(s, "Healing Salve", "hand")
    act(
        s,
        "p1",
        type="move",
        card_ids=[progenitus.id, kept.id],
        to={"player": "p1", "zone": "library"},
        position="top",
    )
    cast(s, "Curate")
    choose(s, [progenitus.id])
    assert s.state.rules.decision and kept.zone == "p1:library"
    saved = tmp_path / "curate.json"
    saved.write_text(s.state.model_dump_json())
    code = r"""
import sys
from pathlib import Path
from app.cards.repository import CardRepository
from app.cards.images import ImageStore
from app.game.session import GameSession
from app.game.state import GameState
from tests.test_rules_conditional_prevention import choose
from tests.test_rules_designations import roundtrip
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
kept=s.state.cards[sys.argv[3]]
d=s.state.rules.decision
option=next(o.id for o in d.options if o.id.startswith(sys.argv[4]))
choose(s,[option])
assert kept.zone=='p1:hand' and not s.state.rules.decision
roundtrip(s)
"""
    result = subprocess.run(
        [sys.executable, "-c", code, str(saved), str(cards.db_path), kept.id, outcome],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_actual_curate_waits_for_graveyard_order_before_following_draw(cards):
    s = game(cards, ["Curate"])
    act(s, "p1", type="set_prefs", ask_graveyard_order=True)
    cast(s, "Curate")
    d = s.state.rules.decision
    before = len(s.state.zones["p1:hand"])
    selected = [o.id for o in d.options]
    act(s, d.player, type="choose", decision_id=d.id, option_ids=selected)
    d = s.state.rules.decision
    assert d and d.resume["step"] == "look_gy_order45"
    assert len(s.state.zones["p1:hand"]) == before
    order = [o.id for o in reversed(d.options)]
    choose(s, order)
    assert len(s.state.zones["p1:hand"]) == before + 1 and not s.state.rules.decision
    assert [c for c in s.state.zones["p1:graveyard"] if c in selected] == list(reversed(order))
    roundtrip(s)


def test_true_cold_graveyard_order_finishes_before_following_draw(cards, tmp_path):
    import subprocess
    import sys

    s = game(cards, ["Curate"])
    act(s, "p1", type="set_prefs", ask_graveyard_order=True)
    cast(s, "Curate")
    d = s.state.rules.decision
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options])
    assert s.state.rules.decision.resume["step"] == "look_gy_order45"
    before = len(s.state.zones["p1:hand"])
    saved = tmp_path / "curate-order.json"
    saved.write_text(s.state.model_dump_json())
    code = r"""
import sys
from pathlib import Path
from app.cards.repository import CardRepository
from app.cards.images import ImageStore
from app.game.session import GameSession
from app.game.state import GameState
from tests.test_rules_conditional_prevention import choose
from tests.test_rules_designations import roundtrip
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
d=s.state.rules.decision
choose(s,[o.id for o in reversed(d.options)])
assert len(s.state.zones['p1:hand'])==int(sys.argv[3])+1 and not s.state.rules.decision
roundtrip(s)
"""
    result = subprocess.run(
        [sys.executable, "-c", code, str(saved), str(cards.db_path), str(before)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_instruction_retention_large_library_then_unrelated_shuffle_rekeys_normally(cards):
    from tests.test_rules_conditional_prevention import activate

    s = game(cards, ["Doom Whisperer", "Progenitus", *["Forest"] * 260])
    source = cast(s, "Doom Whisperer")
    progenitus = put(s, "Progenitus", "hand")
    kept = put(s, "Healing Salve", "hand")
    act(
        s,
        "p1",
        type="move",
        card_ids=[progenitus.id, kept.id],
        to={"player": "p1", "zone": "library"},
        position="top",
    )
    assert len(s.state.zones["p1:library"]) > 250
    old = set(s.state.zones["p1:library"])
    old_id = kept.id
    old_oid = s.state.rules.object_id(old_id)
    activate(s, source, "Surveil 2")
    choose(s, [progenitus.id])
    assert s.state.zones["p1:library"][0] == old_id == kept.id
    assert s.state.rules.object_id(old_id) == old_oid
    assert old & set(s.state.zones["p1:library"]) == {old_id}
    assert s.state.players["p1"].life == 38
    roundtrip(s)
    act(
        s,
        "p1",
        type="shuffle",
        player="p1",
        zone="library",
        r={"perm": [], "new_ids": [], "retained_indices": [0]},
    )
    assert old_id not in s.state.cards and kept.id != old_id
    roundtrip(s)


def test_actual_surveil_two_selected_cards_move_before_replacement_shuffle(cards, monkeypatch):
    import app.game.session as sessions

    original = sessions.resolve
    rng = random.Random(0)  # a fixed shuffle: Curate's draw must not take the freshly shuffled-in Progenitus (1 in 25)

    def resolve(*args, **kwargs):
        return original(*args, **{**kwargs, "rng": rng})

    monkeypatch.setattr(sessions, "resolve", resolve)
    s = game(cards, ["Curate", "Progenitus"])
    put(s, "Curate", "hand")
    progenitus = put(s, "Progenitus", "hand")
    other = put(s, "Healing Salve", "hand")
    act(
        s,
        "p1",
        type="move",
        card_ids=[progenitus.id, other.id],
        to={"player": "p1", "zone": "library"},
        position="top",
    )
    cast(s, "Curate")
    choose(s, [progenitus.id, other.id])
    assert other.zone == "p1:graveyard"
    assert progenitus.zone == "p1:library"
    assert not s.state.rules.decision
    roundtrip(s)


@pytest.mark.parametrize("second_outcome", ["exile", "library:shuffle"])
def test_actual_surveil_two_progenitus_replacement_choices_survive_first_shuffle(cards, second_outcome):
    s = game(cards, ["Curate", "Progenitus", "Progenitus", "Rest in Peace"])
    cast(s, "Rest in Peace")
    put(s, "Curate", "hand")
    pair = [c for c in s.state.cards.values() if c.owner == "p1" and c.name == "Progenitus"]
    assert len(pair) == 2
    act(
        s,
        "p1",
        type="move",
        card_ids=[c.id for c in pair],
        to={"player": "p1", "zone": "library"},
        position="top",
    )
    cast(s, "Curate")
    choose(s, [c.id for c in pair])
    d = s.state.rules.decision
    assert d and d.resume["step"] == "zone_replace_order"
    choose(s, [next(o.id for o in d.options if o.id.startswith("library:shuffle"))])
    d = s.state.rules.decision
    assert d and d.resume["step"] == "zone_replace_order"
    roundtrip(s)
    d = s.state.rules.decision
    hand = list(s.state.zones["p1:hand"])
    choose(s, [next(o.id for o in d.options if o.id.startswith(second_outcome))])
    # (Curate then draws from the library just shuffled: the drawn card may be one of the pair, by chance)
    drawn = [x for x in s.state.zones["p1:hand"] if x not in hand]
    assert len(drawn) == 1
    assert sorted("p1:library" if c.id in drawn else c.zone for c in pair) == sorted(
        ["p1:library", "p1:exile" if second_outcome == "exile" else "p1:library"]
    )
    assert not s.state.rules.decision
    roundtrip(s)


@pytest.mark.parametrize("second_outcome", ["exile", "library:shuffle"])
def test_true_cold_between_two_native_surveil_replacement_choices(cards, tmp_path, second_outcome):
    import subprocess
    import sys

    s = game(cards, ["Curate", "Progenitus", "Progenitus", "Rest in Peace"])
    cast(s, "Rest in Peace")
    put(s, "Curate", "hand")
    pair = [c for c in s.state.cards.values() if c.owner == "p1" and c.name == "Progenitus"]
    act(
        s,
        "p1",
        type="move",
        card_ids=[c.id for c in pair],
        to={"player": "p1", "zone": "library"},
        position="top",
    )
    cast(s, "Curate")
    choose(s, [c.id for c in pair])
    d = s.state.rules.decision
    choose(s, [next(o.id for o in d.options if o.id.startswith("library:shuffle"))])
    saved = tmp_path / "surveil-two.json"
    saved.write_text(s.state.model_dump_json())
    code = r"""
import sys
from pathlib import Path
from app.cards.repository import CardRepository
from app.cards.images import ImageStore
from app.game.session import GameSession
from app.game.state import GameState
from tests.test_rules_conditional_prevention import choose
from tests.test_rules_designations import roundtrip
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
d=s.state.rules.decision
assert d and d.resume['step']=='zone_replace_order'
hand=list(s.state.zones['p1:hand'])
choose(s,[next(o.id for o in d.options if o.id.startswith(sys.argv[3]))])
drawn=[x for x in s.state.zones['p1:hand'] if x not in hand]
assert len(drawn)==1
pair=[c for c in s.state.cards.values() if c.owner=='p1' and c.name=='Progenitus']
assert sorted('p1:library' if c.id in drawn else c.zone for c in pair)==sorted(['p1:library','p1:exile' if sys.argv[3]=='exile' else 'p1:library'])
assert not s.state.rules.decision
roundtrip(s)
"""
    result = subprocess.run(
        [sys.executable, "-c", code, str(saved), str(cards.db_path), second_outcome],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr

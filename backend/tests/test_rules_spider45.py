"""Canonical Spider death choice is a life-gain cost, independent of final life."""

import pytest

from tests.test_rules_conditional_prevention import cast, choose
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_life_sequences44 import cards as cards
from tests.test_rules_life_sequences44 import game


def spider(s):
    source = cast(s, "Skyfisher Spider")
    if s.state.rules.decision:
        d = s.state.rules.decision
        choose(s, ["no"] if any(o.id == "no" for o in d.options) else [])
    assert not s.state.rules.decision
    return source


@pytest.mark.parametrize("accepted", [False, True])
def test_actual_spider_death_gain_choice_and_native_exile(cards, accepted):
    s = game(cards, ["Skyfisher Spider", "Murder"])
    source = spider(s)
    other = put(s, "Grizzly Bears", "graveyard")
    cast(s, "Murder", [source.id], pid="p2")
    d = s.state.rules.decision
    assert d and d.resume["step"] == "spider_life_cost45" and d.resume["amount"] == 2
    choose(s, ["yes" if accepted else "no"])
    assert s.state.players["p1"].life == (42 if accepted else 40)
    assert source.zone == ("p1:exile" if accepted else "p1:graveyard")
    assert other.zone == "p1:graveyard"
    roundtrip(s)


def test_actual_spider_gain_replaced_by_loss_still_pays_and_exiles(cards):
    s = game(cards, ["Skyfisher Spider", "Murder", "Tainted Remedy"])
    put(s, "Tainted Remedy", "battlefield", "p2")
    source = spider(s)
    cast(s, "Murder", [source.id], pid="p2")
    choose(s, ["yes"])
    assert s.state.players["p1"].life == 39 and source.zone == "p1:exile"
    roundtrip(s)


def test_actual_spider_cannot_gain_cost_is_not_offered(cards):
    s = game(cards, ["Skyfisher Spider", "Murder", "Erebos, God of the Dead"])
    put(s, "Erebos, God of the Dead", "battlefield", "p2")
    source = spider(s)
    cast(s, "Murder", [source.id], pid="p2")
    assert not s.state.rules.decision
    assert s.state.players["p1"].life == 40 and source.zone == "p1:graveyard"
    roundtrip(s)


def test_spider_borrowed_source_dies_to_owners_gy_is_not_exiled_from_foreign_gy(cards):
    from tests.game_helpers import act

    s = game(cards, ["Skyfisher Spider", "Murder"])
    source = spider(s)
    act(s, "p1", type="set_controller", card_ids=[source.id], player="p2")
    other = put(s, "Grizzly Bears", "graveyard", "p2")
    cast(s, "Murder", [source.id], pid="p2")
    d = s.state.rules.decision
    assert d and d.player == "p2" and d.resume["amount"] == 1
    choose(s, ["yes"])
    assert source.zone == "p1:graveyard" and other.zone == "p2:graveyard"
    assert s.state.players["p2"].life == 41
    roundtrip(s)


def test_spider_original_gy_card_returned_before_trigger_can_accept_gain_zero(cards):
    from tests.game_helpers import act
    from tests.test_rules_designations import settle

    s = game(cards, ["Skyfisher Spider", "Murder", "Noxious Revival"])
    source = spider(s)
    act(s, "p2", type="set_prefs", hold_priority=True)
    cast(s, "Murder", [source.id], pid="p2", resolve=False)
    for _ in range(12):
        if source.zone == "p1:graveyard":
            break
        act(s, s.state.rules.priority, type="pass_priority")
    assert source.zone == "p1:graveyard"
    cast(s, "Noxious Revival", [source.id], resolve=False)
    settle(s)
    d = s.state.rules.decision
    assert d and d.resume["amount"] == 0
    choose(s, ["yes"])
    assert source.zone == "p1:library" and s.state.players["p1"].life == 40
    roundtrip(s)


@pytest.mark.parametrize("accepted", [False, True])
def test_spider_death_choice_true_cold(cards, tmp_path, accepted):
    import subprocess
    import sys

    s = game(cards, ["Skyfisher Spider", "Murder"])
    source = spider(s)
    cast(s, "Murder", [source.id], pid="p2")
    assert s.state.rules.decision.resume["step"] == "spider_life_cost45"
    saved = tmp_path / "spider.json"
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
source=s.state.cards[sys.argv[3]]
accepted=sys.argv[4]=='yes'
choose(s,[sys.argv[4]])
assert s.state.players['p1'].life==(41 if accepted else 40)
assert source.zone==('p1:exile' if accepted else 'p1:graveyard')
roundtrip(s)
"""
    result = subprocess.run(
        [sys.executable, "-c", code, str(saved), str(cards.db_path), source.id, "yes" if accepted else "no"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_spider_whole_canonical_coverage(cards):
    from app.rules import coverage

    assert coverage.of_card_data(cards.resolve("Skyfisher Spider")).level == "FULL"


def test_spider_actual_etb_sacrifice_precedes_reflexive_target_selection(cards):
    s = game(cards, ["Skyfisher Spider"])
    victim = put(s, "Grizzly Bears", "battlefield")
    target = put(s, "Sol Ring", "battlefield", "p2")
    source = cast(s, "Skyfisher Spider")
    d = s.state.rules.decision
    assert d and target.id not in {o.id for o in d.options}
    if victim.id not in {o.id for o in d.options}:
        pay = next(o.id for o in d.options if o.label.lower() in ("yes", "pay") or o.id == "pay")
        choose(s, [pay])
        d = s.state.rules.decision
    if victim.zone != "p1:graveyard":
        assert d and victim.id in {o.id for o in d.options}
        choose(s, [victim.id])
    assert victim.zone == "p1:graveyard" and source.zone == "p1:battlefield"
    d = s.state.rules.decision
    assert d and target.id in {o.id for o in d.options}
    choose(s, [target.id])
    assert target.zone == "p2:graveyard"
    roundtrip(s)


def test_spider_accepted_life_cost_true_cold_during_native_gain_replacement(cards, tmp_path):
    import subprocess
    import sys

    s = game(cards, ["Skyfisher Spider", "Murder", "Alhammarret's Archive", "Cleric Class"])
    cast(s, "Alhammarret's Archive")
    cast(s, "Cleric Class")
    source = spider(s)
    cast(s, "Murder", [source.id], pid="p2")
    choose(s, ["yes"])
    d = s.state.rules.decision
    assert d and any("Cleric Class" in o.label for o in d.options)
    assert source.zone == "p1:graveyard" and s.state.players["p1"].life == 40
    saved = tmp_path / "spider-gain.json"
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
choose(s,[next(o.id for o in d.options if 'Cleric Class' in o.label)])
assert not s.state.rules.decision
assert s.state.players['p1'].life==44 and s.state.cards[sys.argv[3]].zone=='p1:exile'
roundtrip(s)
"""
    result = subprocess.run(
        [sys.executable, "-c", code, str(saved), str(cards.db_path), source.id],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr

"""Native cost-lock, alternative-zone and actual fresh-process receipts."""

import subprocess
import sys
from pathlib import Path

import pytest

from app.game.errors import ActionError
from tests.game_helpers import act, mana_pool
from tests.test_rules_bandmate_references import wait_priority
from tests.test_rules_cost_statics101 import cards as cards
from tests.test_rules_cost_statics101 import cast, chariot, command_session, into_command, setup
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_wave30m_durations import to_phase


def cold(s, tmp_path, body):
    saved = tmp_path / "cost101.json"
    saved.write_text(s.state.model_dump_json())
    code = (
        """import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.game_helpers import act,mana_pool
from tests.test_rules_designations import settle,roundtrip
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
"""
        + body
        + "\nrepo.close()\n"
    )
    import app

    result = subprocess.run(
        [sys.executable, "-c", code, str(saved), str(s.cards.db_path)],
        cwd=Path(app.__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_actual_automatic_named_mana_tax_cannot_self_fund_but_pays_before_production(cards):
    s = setup(cards)
    chariot(s, "Dreamstone Hedron")
    hedron = put(s, "Dreamstone Hedron", "battlefield")
    bear = put(s, "Grizzly Bears", "hand")
    act(s, "p1", type="add_mana", player="p1", mana={"G": 1})
    before = s.state.model_dump(mode="json")
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=bear.id, sources=[hedron.id])
    assert before == s.state.model_dump(mode="json") and not hedron.tapped
    to_phase(s, "main1", 7)
    engine = put(s, "Wurmcoil Engine", "hand")
    act(s, "p1", type="add_mana", player="p1", mana={"C": 5})
    act(s, "p1", type="cast_spell", card_id=engine.id, sources=[hedron.id])
    assert hedron.tapped and mana_pool(s, "p1") == {}
    record = s.state.rules.payments[s.state.rules.object_id(engine.id)]
    assert record.mana_spent == {"C": 6}
    settle(s)
    assert engine.zone == "p1:battlefield"
    roundtrip(s)


def test_myth_discount_applies_in_hand_without_incrementing_command_cast_count(cards):
    s = setup(cards)
    put(s, "Myth Unbound", "battlefield")
    commander = next(c for c in s.state.cards.values() if c.owner == "p1" and c.commander_key)
    act(s, "p1", type="add_mana", player="p1", mana={"C": 2, "R": 2})
    wait_priority(s, "p1")
    act(s, "p1", type="cast_spell", card_id=commander.id, sources=[])
    settle(s)
    cast(s, "Unsummon", {"U": 1}, [commander.id], pid="p2")
    settle(s)
    d = s.state.rules.decision
    assert d
    option = next(o.id for o in d.options if "hand" in o.label.lower() or o.id == "no")
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[option])
    settle(s)
    assert commander.zone == "p1:hand"
    wait_priority(s, "p1")
    act(s, "p1", type="add_mana", player="p1", mana={"C": 1, "R": 2})
    wait_priority(s, "p1")
    act(s, "p1", type="cast_spell", card_id=commander.id, sources=[])
    assert mana_pool(s, "p1") == {} and s.state.players["p1"].commander_casts[commander.commander_key] == 1
    settle(s)
    roundtrip(s)


def test_liesa_life_tax_is_mandatory_and_myth_only_reduces_mana(cards):
    s = command_session(cards)
    put(s, "Myth Unbound", "battlefield")
    commander = next(c for c in s.state.cards.values() if c.owner == "p1" and c.commander_key)
    act(s, "p1", type="add_mana", player="p1", mana={"C": 2, "W": 2, "B": 1})
    wait_priority(s, "p1")
    act(s, "p1", type="cast_spell", card_id=commander.id, sources=[])
    settle(s)
    into_command(s, commander)
    wait_priority(s, "p1")
    act(s, "p1", type="set_life", player="p1", value=1)
    act(s, "p1", type="add_mana", player="p1", mana={"C": 20, "W": 2, "B": 1})
    before = s.state.model_dump(mode="json")
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=commander.id, sources=[])
    assert before == s.state.model_dump(mode="json")
    act(s, "p1", type="set_life", player="p1", value=10)
    wait_priority(s, "p1")
    act(s, "p1", type="cast_spell", card_id=commander.id, sources=[])
    record = s.state.rules.payments[s.state.rules.object_id(commander.id)]
    assert record.life == 2 and record.mana_spent == {"C": 1, "W": 2, "B": 1}
    assert s.state.players["p1"].life == 8
    settle(s)
    roundtrip(s)


def test_true_cold_named_mana_ability_tax(cards, tmp_path):
    s = setup(cards)
    chariot(s)
    ring = put(s, "Sol Ring", "battlefield")
    act(s, "p1", type="add_mana", player="p1", mana={"C": 2})
    cold(
        s,
        tmp_path,
        f"act(s,'p1',type='activate_ability',card_id={ring.id!r},ability=0,sources=[])\nassert s.state.cards[{ring.id!r}].tapped and mana_pool(s,'p1')=={{'C':2}}\nroundtrip(s)",
    )


def test_true_cold_command_count_and_life_cost(cards, tmp_path):
    s = command_session(cards)
    commander = next(c for c in s.state.cards.values() if c.owner == "p1" and c.commander_key)
    act(s, "p1", type="add_mana", player="p1", mana={"C": 2, "W": 2, "B": 1})
    wait_priority(s, "p1")
    act(s, "p1", type="cast_spell", card_id=commander.id, sources=[])
    settle(s)
    into_command(s, commander)
    wait_priority(s, "p1")
    act(s, "p1", type="add_mana", player="p1", mana={"C": 2, "W": 2, "B": 1})
    cold(
        s,
        tmp_path,
        f"act(s,'p1',type='cast_spell',card_id={commander.id!r},sources=[])\nassert s.state.players['p1'].life==38\nassert s.state.rules.payments[s.state.rules.object_id({commander.id!r})].life==2\nsettle(s);roundtrip(s)",
    )


@pytest.mark.parametrize("wipe", [False, True])
def test_myth_command_from_graveyard_uses_current_watcher_not_simultaneous_lki(cards, wipe):
    s = setup(cards)
    myth = put(s, "Myth Unbound", "battlefield")
    commander = next(c for c in s.state.cards.values() if c.owner == "p1" and c.commander_key)
    wait_priority(s, "p1")
    act(s, "p1", type="add_mana", player="p1", mana={"C": 2, "R": 2})
    act(s, "p1", type="cast_spell", card_id=commander.id, sources=[])
    settle(s)
    before = len(s.state.zones["p1:hand"])
    if wipe:
        cast(s, "Planar Cleansing", {"C": 3, "W": 3})
    else:
        cast(s, "Murder", {"C": 1, "B": 2}, [commander.id])
    settle(s)
    d = s.state.rules.decision
    assert d and d.player == "p1"
    option = next(
        (o.id for o in d.options if "command" in o.label.lower() or "command" in o.id.lower()), "yes"
    )
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[option])
    settle(s)
    assert commander.zone == "p1:command"
    assert myth.zone == ("p1:graveyard" if wipe else "p1:battlefield")
    assert len(s.state.zones["p1:hand"]) == before + (0 if wipe else 1)
    roundtrip(s)

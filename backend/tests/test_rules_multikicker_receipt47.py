"""Large colored costs preserve native payment details and saved SELF decisions."""

import pytest

from tests import test_rules_exile_cast_outcomes45_foundation as gameplay
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_look import settle

cards = gameplay.cards


def receipt(s, card_id, count):
    records = [r for r in s.state.rules.payments.values() if r.card == card_id]
    assert len(records) == 1
    record = records[0]
    assert record.total_cost == f"{{{count + 1}}}" + "{G}" * (count + 1)
    assert record.mana_spent == {"G": count + 1, "C": count + 1}
    assert s.state.cards[card_id].zone == "p1:battlefield"
    assert s.state.cards[card_id].counters.get("+1/+1", 0) == count
    assert not s.state.players["p1"].mana
    roundtrip(s)


@pytest.mark.parametrize("count", [67, 1000])
def test_colored_multikicker_retains_full_payment_receipt(cards, count):
    s = gameplay.setup(cards, "Gnarlid Pack")
    spell = put(s, "Gnarlid Pack", "hand")
    remaining = count + 1
    while remaining:
        amount = min(100, remaining)
        mana(s, G=amount, C=amount)
        remaining -= amount
    action = act(s, "p1", type="cast_spell", card_id=spell.id, kicker=count)
    assert any(len(step.get("label", "")) > 200 for step in action.r)
    settle(s)
    receipt(s, spell.id, count)


def test_large_self_payment_survives_fresh_process_with_full_cost(cards, tmp_path):
    import subprocess
    import sys

    s = gameplay.setup(cards, "Gnarlid Pack")
    spell = put(s, "Gnarlid Pack", "hand")
    act(s, "p1", type="set_prefs", payment="self")
    act(s, "p1", type="cast_spell", card_id=spell.id, kicker=1000)
    decision = s.state.rules.decision
    assert decision and decision.resume["step"] == "pay_mana"
    assert len(decision.prompt) <= 300
    saved = tmp_path / "large-payment.json"
    saved.write_text(s.state.model_dump_json())
    code = r"""
import sys
from pathlib import Path
from app.cards.repository import CardRepository
from app.cards.images import ImageStore
from app.game.session import GameSession
from app.game.state import GameState
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana
from tests.test_rules_library_look import settle
from tests.test_rules_multikicker_receipt47 import receipt
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
for _ in range(10):
    mana(s,G=100,C=100)
mana(s,G=1,C=1)
d=s.state.rules.decision
act(s,d.player,type='choose',decision_id=d.id,option_ids=['pay'])
settle(s)
receipt(s,sys.argv[3],1000)
"""
    result = subprocess.run(
        [sys.executable, "-c", code, str(saved), str(cards.db_path), spell.id],
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert result.returncode == 0, result.stdout + result.stderr

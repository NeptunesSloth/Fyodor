"""Wave 50B: Strong, the Brutish Thespian's "gain life rather than lose life from radiation" next to the other "would lose life" replacements (CR 2026-09-25), real Oracle text
(tests/fixtures/wave44c_cards.json and tests/fixtures/wave50b_bloodletter_cards.json, from data/cards.sqlite).

* 616.1: the affected player orders the replacement effects that would apply to one event. The only other "would lose life" replacement the engine reads that could meet a
  radiation loss is Bloodletter of Aclazotz ("If an opponent would lose life during your turn, they lose twice that much life instead."); radiation's ability is controlled by,
  and its loss is the loss of, the active player (728.1), so Bloodletter's controller would have to be that player's opponent during that player's own turn: it never is.
  No order can ever be asked, so none is modelled (ponytail: the gain is applied after the other replacements; add the choice with the first card that can meet it).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from tests.fixtures.cards import card, fixture_cards
from tests.test_rules_wave34b_activated import settle
from tests.test_rules_wave44c_statics import radiation
from tests.wave9c_kit import build, check, put
from tests.wave44c_kit import EXTRA as EXTRA44
from tests.wave44c_kit import life

BLOODLETTER = json.loads((Path(__file__).parent / "fixtures" / "wave50b_bloodletter_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="t50o", number=f"O{i:02d}", **{k: v for k, v in c.items() if k != "name"}) for i, c in enumerate(BLOODLETTER) if c["name"] not in KNOWN]


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA44, *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def test_an_opponents_bloodletter_does_not_meet_strongs_radiation_gain(cards):
    s = build(cards, ["Strong, the Brutish Thespian", "Hill Giant", "Grizzly Bears", "Shivan Dragon", "Goblin Piker"], ["Bloodletter of Aclazotz"])
    put(s, "Strong, the Brutish Thespian")
    put(s, "Bloodletter of Aclazotz", "p2")
    settle(s)
    radiation(s, "p1")
    assert life(s, "p1") == 43 and s.state.players["p1"].resources.get("rad", 0) == 0  # three nonland cards: gain 3, not lose 6 (not Bob's turn) and not asked an order
    assert s.state.rules.decision is None
    check(s)

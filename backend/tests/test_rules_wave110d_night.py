"""Wave 110D: Last Night Together, real Oracle text (tests/fixtures/wave110d_cards.json). Every scenario checks the replay and a save and a load.

* 500.8: "After this main phase, there is an additional combat phase." comes before the turn's own combat.
* 508.1a: "Only the chosen creatures can attack during that combat phase." — the two targets only, and only in that added phase.
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from tests.game_helpers import act
from tests.wave9c_kit import build
from tests.wave110d_kit import card_db, check, cost, full, mana, now, put_new, settle, to_hand, to_phase  # noqa: F401


def test_last_night_together_is_full():
    assert full("Last Night Together")


def test_only_the_chosen_creatures_attack_in_the_extra_combat_only(cards):
    s = build(cards, ["Last Night Together", "Grizzly Bears", "Grizzly Bears", "Grizzly Bears"])
    a, b, c = (put_new(s, "Grizzly Bears") for _ in range(3))
    to_phase(s, "main1", turn=3)
    spell = to_hand(s, "Last Night Together")
    mana(s, **cost("Last Night Together"))
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=[a.id, b.id], target_counts=[2])
    settle(s)
    assert now(s, a).counters.get("+1/+1") == 2
    to_phase(s, "declare_attackers", turn=3)
    with pytest.raises(ActionError):
        act(s, "p1", type="declare_attackers", attackers=[{"card_id": c.id, "target": "p2"}])
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": a.id, "target": "p2"}, {"card_id": b.id, "target": "p2"}])
    check(s)

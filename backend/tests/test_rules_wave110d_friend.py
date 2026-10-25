"""Wave 110D: Animal Friend, real Oracle text (tests/fixtures/wave110d_cards.json). Every scenario checks the replay and a save and a load.

* 113.10, 608.2h: "Whenever this creature attacks, create a 1/1 green Squirrel creature token. Put a +1/+1 counter on that token for each Aura and Equipment
  attached to this creature other than Animal Friend." — the Aura itself is not counted; an Equipment on the creature is.
"""

from __future__ import annotations

import pytest

from tests.game_helpers import act
from tests.wave9c_kit import build
from tests.wave110d_kit import activate, card_db, cast_on, check, full, mana, now, put_new, settle, to_phase  # noqa: F401


def test_animal_friend_is_full():
    assert full("Animal Friend")


@pytest.mark.parametrize("equipped", [False, True])
def test_squirrel_counters_count_the_other_attachments(cards, equipped):
    s = build(cards, ["Animal Friend", "Grizzly Bears", "Bonesplitter"])
    bears = put_new(s, "Grizzly Bears")
    to_phase(s, "main1", turn=3)
    cast_on(s, "Animal Friend", bears)
    assert now(s, next(c for c in s.state.cards.values() if c.name == "Animal Friend")).attached_to == bears.id
    if equipped:
        sword = put_new(s, "Bonesplitter")
        mana(s, C=1)
        activate(s, sword, "Equip {1}", targets=[bears.id])
        assert now(s, sword).attached_to == bears.id
    to_phase(s, "declare_attackers", turn=3)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": bears.id, "target": "p2"}])
    settle(s)
    squirrels = [c for c in s.state.cards.values() if c.name == "Squirrel" and c.zone.endswith(":battlefield")]
    assert len(squirrels) == 1 and squirrels[0].counters.get("+1/+1", 0) == int(equipped)
    check(s)

"""Found by tools/soak.py (gaps4: Disa the Restless against Ian Malcolm, seed 6201), real Oracle text (tests/fixtures/soak_cards.json);
every scenario checks the replay and a save and a load.

- Long River's Pull ("Counter target creature spell. If the gift was promised, instead counter target spell.") was offered with no spell on
  the stack (only a triggered ability): its targets depend on the gift (a kicker-like choice, 702.33g), and the castability hint left those
  to the cast. It is offered only while one of the two casts has a legal target (601.2c).
- Brand ("Gain control of all permanents you own.") with 25 permanents failed the whole cast: the log line named every permanent, and a log
  line names at most 20 cards.
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules.view import hints
from tests.game_helpers import act
from tests.soak_kit import cards  # noqa: F401 - the fixture
from tests.test_rules_attachments import token
from tests.test_rules_conditionals import settle
from tests.wave9c_kit import build, check, mana, to_hand


def offered(s, cid, pid="p1"):
    h = hints(s.state, pid, s.cards)
    return cid in h["castable"], [o["id"] for o in h.get("optional_costs", {}).get(cid, [])]


def test_long_rivers_pull_needs_a_spell_it_could_counter(cards):  # noqa: F811
    """No spell on the stack: neither cast has a target, so it isn't offered (nor its gift), and both casts are refused. A creature spell:
    offered, and the plain cast counters it. A noncreature spell: offered for the gift's "counter target spell"."""
    s = build(cards, mine=["Long River's Pull", "Llanowar Elves", "Sol Ring"])
    pull = to_hand(s, "Long River's Pull")
    elves = to_hand(s, "Llanowar Elves")
    ring = to_hand(s, "Sol Ring")
    mana(s, U=2, G=1)
    assert offered(s, pull.id) == (False, [])
    for extra in ({}, {"optional_costs": [f"{pull.id}:gift"], "gift_to": "p2"}):
        with pytest.raises(ActionError, match="no legal target"):
            act(s, "p1", type="cast_spell", card_id=pull.id, **extra)
    act(s, "p1", type="set_prefs", hold_priority=True)
    act(s, "p1", type="cast_spell", card_id=elves.id)
    assert offered(s, pull.id) == (True, [f"{pull.id}:gift"])
    act(s, "p1", type="cast_spell", card_id=pull.id, targets=[elves.id], target_counts=[1, 0])
    settle(s)
    assert s.state.cards[elves.id].zone == "p1:graveyard" and s.state.cards[pull.id].zone == "p1:graveyard"
    # a noncreature spell: only the gift's "counter target spell" can take it
    act(s, "p1", type="move", card_ids=[pull.id], to={"zone": "hand"})
    mana(s, U=2, C=1)
    act(s, "p1", type="cast_spell", card_id=ring.id)
    assert ring.id in s.state.zones["stack"]
    assert offered(s, pull.id) == (True, [f"{pull.id}:gift"])
    act(s, "p1", type="cast_spell", card_id=pull.id, optional_costs=[f"{pull.id}:gift"], gift_to="p2", targets=[ring.id], target_counts=[0, 1])
    settle(s)
    assert s.state.cards[ring.id].zone == "p1:graveyard"
    check(s)


def test_brand_takes_back_more_than_twenty_permanents(cards):  # noqa: F811
    """Bob controls 24 of Alice's tokens (and she has her commander out): Brand takes them all back. Its log line keeps the first 20 cards it
    names, instead of failing the cast."""
    s = build(cards, mine=["Brand"])
    toks = [token(s, "p1", f"Goblin {i}", "1/1") for i in range(24)]
    act(s, "p1", type="set_controller", card_ids=[t.id for t in toks], player="p2")
    assert all(s.state.cards[t.id].controller == "p2" for t in toks)
    brand = to_hand(s, "Brand")
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=brand.id)
    settle(s)
    assert all(s.state.cards[t.id].controller == "p1" for t in toks)
    line = next(e for e in reversed(s.state.log) if "gains control of" in (e.parts[0].t or ""))
    assert sum(1 for p in line.parts if p.t is None) == 20 and len(line.parts[0].t) <= 500
    check(s)

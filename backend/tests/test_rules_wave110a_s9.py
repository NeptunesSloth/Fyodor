"""Wave 110A session 9: real Oracle text cards (tests/fixtures/wave110a_cards.json), each scenario checks replay and save/load.

* Dovin Baan - +1: 611.2b "until your next turn" -3/-0 and 602.5 no activated abilities; -7 emblem: 502.3 untap limit for opponents.
"""

# ruff: noqa: F403, F405
from __future__ import annotations

from app.game.errors import ActionError
from tests.wave110a_kit import *

DOVIN = "Dovin Baan"


@pytest.fixture()
def cards(settings):
    yield from open_repo(settings)


test_full = full_test([DOVIN])


def _dovin(cards, ability):
    s = build(cards, [DOVIN, "Grizzly Bears"], ["Grizzly Bears"])
    d = put(s, DOVIN)
    bears = put(s, "Grizzly Bears", "p2")
    act(s, "p1", type="counter", card_ids=[d.id], kind="loyalty", delta=6)
    next_turn(s)
    stops(s)
    act(s, "p1", type="activate_ability", card_id=d.id, ability=ability, **({"targets": [bears.id], "target_counts": [1]} if ability == 0 else {}))
    answer(s)
    return s, d, bears


def test_dovin_plus_one_shrinks_and_locks_the_creature_until_your_next_turn(cards):
    s, d, bears = _dovin(cards, 0)
    assert pt(s, "Grizzly Bears", "p2") == (-1, 2)
    to_phase(s, "end")
    assert pt(s, "Grizzly Bears", "p2") == (-1, 2)  # 611.2b: still shrunk after this turn's end
    check(s)



def _untap_question(s, turn):
    for _ in range(200):
        d = s.state.rules.decision
        if d is None:
            if s.state.turn.number > turn:
                return None
            act(s, s.state.rules.priority, type="pass_priority")
        elif (d.resume or {}).get("step") == "untap_limit":
            return d
        elif d.kind == "declare_attackers":
            act(s, d.player, type="declare_attackers", attackers=[])
        elif d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
        else:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
    raise AssertionError("never settled")


@pytest.mark.parametrize("who", ["p2", "p1"])
def test_dovin_emblem_limits_only_the_opponents_untaps_to_two_permanents(cards, who):
    """502.3: the emblem's controller (Alice) is not limited; an opponent untaps only two of three tapped permanents, their choice."""
    s = build(cards, [DOVIN, "Grizzly Bears", "Hill Giant", "Ornithopter"], ["Grizzly Bears", "Hill Giant", "Ornithopter"])
    d = put(s, DOVIN)
    act(s, "p1", type="counter", card_ids=[d.id], kind="loyalty", delta=7)
    next_turn(s)
    stops(s)
    act(s, "p1", type="activate_ability", card_id=d.id, ability=2)
    answer(s)
    mine = [put(s, n, who) for n in ("Grizzly Bears", "Hill Giant", "Ornithopter")]
    act(s, who, type="tap", card_ids=[c.id for c in mine], tapped=True)
    turn = s.state.turn.number
    q = _untap_question(s, turn + (1 if who == "p2" else 2))
    if who == "p1":
        assert q is None and not any(s.state.cards[c.id].tapped for c in mine)
    else:
        assert q.player == "p2" and q.min_choices == q.max_choices == 2 and len(q.options) == 3
        act(s, "p2", type="choose", decision_id=q.id, option_ids=[o.id for o in q.options[:2]])
        assert sum(s.state.cards[c.id].tapped for c in mine) == 1
    check(s)

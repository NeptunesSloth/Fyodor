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


WARD = "Ward of Bones"
test_full_ward = full_test([WARD])


@pytest.mark.parametrize("mine,theirs,barred", [(0, 1, True), (1, 1, False), (1, 0, False)])
def test_ward_of_bones_bars_creature_spells_only_while_the_opponent_has_more_creatures(cards, mine, theirs, barred):
    """601.3: an opponent with more creatures than Ward's controller can't cast a creature spell; with as many or fewer, they can."""
    s = build(cards, [WARD, "Grizzly Bears"], ["Grizzly Bears", "Hill Giant"])
    put(s, WARD)
    if mine:
        put(s, "Grizzly Bears")
    if theirs:
        put(s, "Hill Giant", "p2")
    stops(s)
    to_phase(s, "main2", turn=2)
    to_hand(s, "Grizzly Bears", "p2")
    fund(s, "{1}{G}", "p2")
    if barred:
        with pytest.raises(ActionError, match="Ward of Bones"):
            act(s, "p2", type="cast_spell", card_id=card_named(s, "Grizzly Bears", "p2").id, targets=[])
    else:
        cast(s, "Grizzly Bears", pid="p2")
        answer(s)
        assert zone_of(s, "Grizzly Bears", "p2") == "p2:battlefield"
    check(s)


@pytest.mark.parametrize("mine,theirs,barred", [(0, 1, True), (1, 1, False)])
def test_ward_of_bones_bars_land_plays_only_while_the_opponent_has_more_lands(cards, mine, theirs, barred):
    """305.1: an opponent with more lands than Ward's controller can't play a land; with as many, they can."""
    s = build(cards, [WARD, "Forest"], ["Forest", "Island"])
    put(s, WARD)
    if mine:
        put(s, "Forest")
    if theirs:
        put(s, "Forest", "p2")
    stops(s)
    to_phase(s, "main1", turn=2)
    f = to_hand(s, "Island", "p2")
    if barred:
        with pytest.raises(ActionError, match="Ward of Bones"):
            act(s, "p2", type="play_land", card_id=f.id)
    else:
        act(s, "p2", type="play_land", card_id=f.id)
        assert zone_of(s, "Island", "p2") == "p2:battlefield"
    check(s)

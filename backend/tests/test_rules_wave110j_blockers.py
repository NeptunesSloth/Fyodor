"""Wave 110J: Balduvian Warlord and Sorrow's Path, real Oracle text (tests/fixtures/wave110j_cards.json). Every scenario ends with replay + save/load.

* 506.4 / 509.1h: a creature removed from combat leaves it; an attacker it blocked stays blocked unless the Warlord's own words make it unblocked
  (nobody else was ever declared as its blocker). Effect-made blocks: the chosen attacker must be attacking the blocker's controller (506.3e).
* Sorrow's Path swaps two blockers only if each could block everything the other blocks (509.1a, 509.1b): the flier-blocker case changes nothing.
"""

from __future__ import annotations

from tests.game_helpers import act
from tests.wave9c_kit import build, life, pt
from tests.wave110j_kit import EXTRA, card_db, check, now, put_new, settle, to_phase  # noqa: F401

WARLORD, PATH = "Balduvian Warlord", "Sorrow's Path"


def test_full(cards):
    from app.rules import coverage

    for n in (WARLORD, PATH):
        assert coverage.of_card_data(cards.resolve(n)).level == "FULL"


def _blocked(s, attackers, blocks, mine):
    """Turn 3: p1's ``attackers`` attack p2, p2 declares ``blocks`` [(blocker, attacker)], then p1 holds priority in the declare blockers step."""
    act(s, "p1", type="set_stops", own=["declare_blockers"])
    to_phase(s, "declare_attackers", turn=3)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": c.id, "target": "p2"} for c in attackers])
    for _ in range(12):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_blockers":
            break
        act(s, s.state.rules.priority, type="pass_priority")
    act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": b.id, "attacker_id": a.id} for b, a in blocks])
    assert s.state.turn.phase == "declare_blockers" and s.state.rules.priority == "p1"


def _warlord(cards, second_blocker):
    s = build(cards, [WARLORD, "Hill Giant", "Hill Giant"], ["Grizzly Bears", "Grizzly Bears"], forests=30, islands=30)
    w = put_new(s, WARLORD)
    giants = [c for c in s.state.cards.values() if c.name == "Hill Giant" and c.owner == "p1" and c.zone.endswith(":library")][:2]
    for g in giants:
        act(s, "p1", type="move", card_ids=[g.id], to={"player": "p1", "zone": "battlefield"})
    bears = [put_new(s, "Grizzly Bears", "p2") for _ in range(2)]
    return s, w, giants, bears


def test_warlord_moves_the_block_and_unblocks_what_nobody_else_blocked(cards):
    s, w, (g1, g2), (b1, _b2) = _warlord(cards, False)
    _blocked(s, [g1, g2], [(b1, g1)], w)
    act(s, "p1", type="activate_ability", card_id=w.id, ability=0, targets=[b1.id])
    settle(s, answers=[g2.id])
    assert now(s, b1).blocks(g2.id) and not now(s, b1).blocks(g1.id)
    assert g1.id not in s.state.rules.blocked and g2.id in s.state.rules.blocked  # g1 is unblocked again; g2 is now blocked
    assert now(s, w).tapped
    act(s, "p1", type="pass_priority")
    assert s.state.turn.phase != "declare_blockers"  # combat damage has been dealt
    assert life(s, "p2") == 37 and now(s, b1).zone.endswith(":graveyard")  # g1 unblocked: 3 damage to p2; g2 killed the bears
    check(s)


def test_warlord_leaves_an_attacker_blocked_when_another_creature_blocked_it(cards):
    s, w, (g1, g2), (b1, b2) = _warlord(cards, True)
    _blocked(s, [g1, g2], [(b1, g1), (b2, g1)], w)
    act(s, "p1", type="activate_ability", card_id=w.id, ability=0, targets=[b1.id])
    settle(s, answers=[g2.id])
    assert g1.id in s.state.rules.blocked and now(s, b2).blocks(g1.id) and now(s, b1).blocks(g2.id)
    act(s, "p1", type="pass_priority")
    assert s.state.turn.phase != "declare_blockers"  # combat damage has been dealt
    assert life(s, "p2") == 40  # both attackers stayed blocked
    check(s)


def test_path_swaps_two_blockers(cards):
    s = build(cards, [PATH, "Hill Giant", "Hill Giant"], ["Grizzly Bears", "Hill Giant"], forests=30, islands=30)
    p = put_new(s, PATH)
    g1, g2 = [c for c in s.state.cards.values() if c.name == "Hill Giant" and c.owner == "p1" and c.zone.endswith(":library")][:2]
    for g in (g1, g2):
        act(s, "p1", type="move", card_ids=[g.id], to={"player": "p1", "zone": "battlefield"})
    b1, b2 = put_new(s, "Grizzly Bears", "p2"), put_new(s, "Hill Giant", "p2")
    _blocked(s, [g1, g2], [(b1, g1), (b2, g2)], p)
    act(s, "p1", type="activate_ability", card_id=p.id, ability=0, targets=[b1.id, b2.id], target_counts=[1, 1])
    settle(s)
    assert now(s, b1).blocks(g2.id) and not now(s, b1).blocks(g1.id) and now(s, b2).blocks(g1.id) and not now(s, b2).blocks(g2.id)
    check(s)


def test_path_changes_nothing_if_one_could_not_block(cards):
    """A ground blocker can't block the flier the other one blocks: neither is removed from combat."""
    s = build(cards, [PATH, "Air Elemental", "Hill Giant"], ["Air Elemental", "Grizzly Bears"], forests=30, islands=30)
    p = put_new(s, PATH)
    drake, giant = put_new(s, "Air Elemental"), put_new(s, "Hill Giant")  # (Path's own trigger deals 2 damage to each creature its controller has)
    b1, b2 = put_new(s, "Air Elemental", "p2"), put_new(s, "Grizzly Bears", "p2")
    _blocked(s, [drake, giant], [(b1, drake), (b2, giant)], p)
    act(s, "p1", type="activate_ability", card_id=p.id, ability=0, targets=[b1.id, b2.id], target_counts=[1, 1])
    settle(s)
    assert now(s, b1).blocks(drake.id) and now(s, b2).blocks(giant.id) and not now(s, b1).blocks(giant.id)
    check(s)


# -- Magnetic Web ------------------------------------------------------------------------------------------------------------------------------------
WEB = "Magnetic Web"


def _magnet(s, *cards):
    for c in cards:
        act(s, "p1", type="counter", card_ids=[c.id], kind="magnet", delta=1)


def _web_table(cards):
    s = build(cards, [WEB, "Hill Giant", "Grizzly Bears", "Llanowar Elves"], ["Grizzly Bears", "Grizzly Bears"], forests=30, islands=30)
    put_new(s, WEB)
    mine = [put_new(s, n) for n in ("Hill Giant", "Grizzly Bears", "Llanowar Elves")]
    theirs = [put_new(s, "Grizzly Bears", "p2") for _ in range(2)]
    return s, mine, theirs


def test_web_is_full(cards):
    from app.rules import coverage

    assert coverage.of_card_data(cards.resolve(WEB)).level == "FULL"


def test_web_if_a_magnet_creature_attacks_all_of_them_must(cards):
    """508.1d: a lone magnet attacker is refused; all magnet creatures (or none) may attack; a creature with no counter is free."""
    import pytest

    from app.game.errors import ActionError

    s, (giant, bears, elves), _ = _web_table(cards)
    _magnet(s, giant, bears)
    to_phase(s, "declare_attackers", turn=3)
    with pytest.raises(ActionError):
        act(s, "p1", type="declare_attackers", attackers=[{"card_id": giant.id, "target": "p2"}])
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": elves.id, "target": "p2"}])  # no magnet attacks: nothing required
    assert now(s, elves).attacking is not None and now(s, giant).attacking is None
    check(s)


def test_web_all_magnet_creatures_attack_and_must_be_blocked_by_all_magnet_creatures(cards):
    import pytest

    from app.game.errors import ActionError
    from app.rules.plan import Plan

    s, (giant, bears, _elves), (d, e) = _web_table(cards)
    _magnet(s, giant, bears, d)
    to_phase(s, "declare_attackers", turn=3)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": c.id, "target": "p2"} for c in (giant, bears)])
    for _ in range(12):
        dec = s.state.rules.decision
        if dec is not None and dec.kind == "declare_blockers":
            break
        act(s, s.state.rules.priority, type="pass_priority")
    imposed = Plan(s.state, "p2", s.cards, None).ch(s.state.cards[d.id]).imposed
    assert {f"must_block_obj:{s.state.rules.object_id(c.id)}" for c in (giant, bears)} <= set(imposed)  # one trigger per magnet attacker
    assert not [r for r in Plan(s.state, "p2", s.cards, None).ch(s.state.cards[e.id]).imposed if r.startswith("must_block_obj")]
    with pytest.raises(ActionError):
        act(s, "p2", type="declare_blockers", blocks=[])  # the magnet creature blocks if able
    act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": d.id, "attacker_id": giant.id}])
    assert now(s, d).zone.endswith(":graveyard") and life(s, "p2") == 38  # it blocked the Giant (and died); the Bears were unblocked
    check(s)


def test_warlord_re_block_triggers_whenever_blocks(cards):
    """509.3a: removed from combat then made to block by an effect, the creature was not blocking at that time, so "whenever this creature blocks" triggers again."""
    s = build(cards, [WARLORD, "Hill Giant", "Hill Giant"], ["Giant Badger"], forests=30, islands=30)
    w = put_new(s, WARLORD)
    g1, g2 = [c for c in s.state.cards.values() if c.name == "Hill Giant" and c.owner == "p1" and c.zone.endswith(":library")][:2]
    for g in (g1, g2):
        act(s, "p1", type="move", card_ids=[g.id], to={"player": "p1", "zone": "battlefield"})
    b = put_new(s, "Giant Badger", "p2")
    _blocked(s, [g1, g2], [(b, g1)], w)
    settle(s)
    assert pt(s, "Giant Badger", "p2") == (4, 4)  # declared as a blocker: +2/+2 (509.3a)
    act(s, "p1", type="activate_ability", card_id=w.id, ability=0, targets=[b.id])
    settle(s, answers=[g2.id])
    assert now(s, b).blocks(g2.id) and pt(s, "Giant Badger", "p2") == (6, 6)  # blocks again by an effect: triggers again
    check(s)

"""Wave 110E session 7: untested branches of Mirror Match and Coward.

* Mirror Match: 508.5 / 509.4 an attacker of a planeswalker the caster controls gets a blocking copy too; 509.3d each copy that is put onto the
  battlefield blocking triggers "becomes blocked by a creature" of its original; "blocks" abilities do not (509.3b).
* Coward: 509.1b the target cannot be declared as a blocker.
"""
from __future__ import annotations

import pytest

import tests.test_rules_wave110e_cards as base
import tests.test_rules_wave110e_s6  # noqa: F401  (registers the cards)
from app.game.errors import ActionError
from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import real
from tests.test_rules_wave110e_cards import card_db  # noqa: F401  (the fixture)

TARDIS = real("Start the TARDIS", "{1}{U}", 2, "Instant",
              "Surveil 2, then draw a card. You may planeswalk. (To surveil 2, look at the top two cards of your library, then put any number of them into your graveyard and the rest on top of your library in any order.)\n"
              "Jump-start (You may cast this card from your graveyard by discarding a card in addition to paying its other costs. Then exile this card.)", None, "U")
GAMBIT = real("Decoy Gambit", "{1}{1}{U}", 3, "Instant",
              "For each opponent, choose up to one target creature that player controls, then return that creature to its owner's hand unless its controller has you draw a card.", None, "U")
WALKER = real("Test Walker", "{2}", 2, "Planeswalker — Test", "+1: You gain 1 life.", None, "")
base.EXTRA.extend([WALKER, TARDIS, GAMBIT])


def _setup(cards, mm=True):
    from tests.wave53c_kit import sandbox

    return sandbox(cards, p2=("Mirror Match", "Test Walker") if mm else ("Coward", "Test Walker"))


def _cast_mirror(s):
    from tests.wave53c_kit import in_play, pool, priority_to, settle

    mm = in_play(s, "Mirror Match", "p2")
    act(s, "p2", type="move", card_ids=[mm.id], to={"zone": "hand"})
    pool(s, "p2", U=2, C=4)
    priority_to(s, "p2")
    act(s, "p2", type="cast_spell", card_id=mm.id)
    settle(s)


@pytest.mark.parametrize("at_walker", [False, True])
def test_mirror_match_copies_attackers_of_a_planeswalker_you_control(cards, at_walker):
    """508.5: an attacker of Bob's planeswalker is "attacking a planeswalker you control": copied; with 0 blockers declared, the walker is not hurt."""
    from tests.test_rules_conditionals import creature
    from tests.test_rules_group_unblocked import finish_combat
    from tests.wave53c_kit import combat_step, in_play, swing

    s = _setup(cards)
    pw = in_play(s, "Test Walker", "p2")
    act(s, "p2", type="move", card_ids=[pw.id], to={"zone": "battlefield"})
    act(s, "p2", type="set_counter", card_id=pw.id, kind="loyalty", value=5)
    a = creature(s, "p1", "Aaa", "3/9")
    creature(s, "p2", "Guard", "0/9")
    combat_step(s)
    swing(s, [a], [], target=pw.id if at_walker else "p2", before=None)
    _cast_mirror(s)
    copies = [c for c in s.state.cards.values() if c.name == "Aaa" and c.controller == "p2" and c.zone == "p2:battlefield"]
    assert len(copies) == 1 and copies[0].blocking is not None
    finish_combat(s)
    assert s.state.players["p2"].life == 40 and s.state.cards[pw.id].counters.get("loyalty") == 5
    from tests.wave9c_kit import check
    check(s)


def test_mirror_match_ignores_attackers_of_a_third_player(cards):
    """Attackers that attack neither Bob nor his planeswalkers are not copied."""
    from tests.test_rules_conditionals import creature, sandbox
    from tests.wave53c_kit import combat_step, swing

    s = sandbox(cards, p2=("Mirror Match",), players=3)
    a = creature(s, "p1", "Aaa", "3/9")
    creature(s, "p3", "Guard", "0/9")
    combat_step(s)
    swing(s, [a], [], opp="p3", before=None)
    _cast_mirror(s)
    assert not [c for c in s.state.cards.values() if c.name == "Aaa" and c.controller == "p2"]


def test_mirror_match_copy_putting_onto_battlefield_blocking_triggers_becomes_blocked_by_a_creature(cards):
    """509.3d: the original's "becomes blocked by a creature" triggers once for the copy put onto the battlefield blocking it."""
    from tests.test_rules_conditionals import creature
    from tests.test_rules_group_unblocked import finish_combat
    from tests.wave53c_kit import combat_step, swing

    s = _setup(cards)
    a = creature(s, "p1", "Aaa", "3/9", text="Whenever Aaa becomes blocked by a creature, you gain 1 life.\nWhenever Aaa blocks a creature, you gain 10 life.")
    creature(s, "p2", "Guard", "0/9")
    combat_step(s)
    swing(s, [a], [], before=None)
    life = s.state.players["p1"].life
    _cast_mirror(s)
    assert s.state.players["p1"].life == life + 1  # (the copy's own "blocks" ability does not trigger, 509.3b)
    finish_combat(s)


def test_coward_target_cannot_be_declared_as_a_blocker(cards):
    """509.1b: a creature that can't block is not a legal blocker."""
    from tests.test_rules_conditionals import creature
    from tests.wave53c_kit import combat_step, in_play, pool, priority_to, settle

    s = _setup(cards, mm=False)
    a = creature(s, "p1", "Aaa", "3/3")
    guard = creature(s, "p2", "Guard", "0/9")
    combat_step(s)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": a.id, "target": "p2"}])
    cw = in_play(s, "Coward", "p2")
    act(s, "p2", type="move", card_ids=[cw.id], to={"zone": "hand"})
    pool(s, "p2", R=1, C=1)
    priority_to(s, "p2")
    act(s, "p2", type="cast_spell", card_id=cw.id, targets=[guard.id])
    settle(s)
    for _ in range(12):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_blockers":
            with pytest.raises(ActionError):
                act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": guard.id, "attacker_id": a.id}])
            act(s, "p2", type="declare_blockers", blocks=[])
            return
        if d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][:1])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("no blockers asked")


def _answer(s, picks):
    """Resolve everything; ``picks`` maps a player to the option id ("pay" = Yes) they choose, else the first option."""
    for _ in range(40):
        d = s.state.rules.decision
        if d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[picks.get(d.player, d.options[0].id)])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return


def _gambit(cards, p2_draw, p3_draw):
    """Decoy Gambit with one creature of each opponent; each controller answers whether the caster draws (608.2c, 608.2d)."""
    from tests.game_helpers import turn_on
    from tests.test_rules_conditionals import creature, sandbox
    from tests.wave53c_kit import in_play, pool, priority_to

    s = sandbox(cards, "Decoy Gambit", players=3)
    turn_on(s)
    a, b = creature(s, "p2", "Aaa", "1/1"), creature(s, "p3", "Bbb", "1/1")
    g = in_play(s, "Decoy Gambit", "p1")
    act(s, "p1", type="move", card_ids=[g.id], to={"zone": "hand"})
    pool(s, "p1", U=1, C=2)
    priority_to(s, "p1")
    act(s, "p1", type="cast_spell", card_id=g.id, targets=[a.id, b.id], target_counts=[1, 1])
    _answer(s, {"p2": "pay" if p2_draw else "decline", "p3": "pay" if p3_draw else "decline"})
    return s, a, b, sum(1 for entry in s.state.log if entry.phase != "draw" and any("drew" in (p.t or "") for p in entry.parts))


@pytest.mark.parametrize("p2_draw,p3_draw", [(True, False), (False, True), (True, True), (False, False)])
def test_decoy_gambit_each_controller_chooses_between_the_draw_and_the_bounce(cards, p2_draw, p3_draw):
    """608.2c: each chosen creature returns unless its own controller has the caster draw; one draw per such answer."""
    from tests.wave9c_kit import check

    s, a, b, drawn = _gambit(cards, p2_draw, p3_draw)
    alive = lambda c: c.id in s.state.cards and s.state.cards[c.id].zone.endswith(":battlefield")  # noqa: E731  (a bounced token ceases to exist, 111.7)
    assert (alive(a), alive(b)) == (p2_draw, p3_draw), drawn
    assert drawn == p2_draw + p3_draw
    check(s)


def test_start_the_tardis_surveils_then_draws_and_planeswalking_does_nothing(cards):
    """701.31a: no Planechase game, so "you may planeswalk" is nothing; 701.25 surveil 2 then 121.2 draw."""
    from tests.test_rules_wave110e_cards import answer, cast
    from tests.wave9c_kit import build, check, mana

    s = build(cards, ["Start the TARDIS"], forests=30, islands=30)
    mana(s, U=1, C=3)
    hand = len(s.state.zones["p1:hand"])
    cast(s, "Start the TARDIS")
    answer(s)
    assert len(s.state.zones["p1:hand"]) == hand + 1  # (the card was cast from a hand it was put in: +1 -1 +1)
    check(s)

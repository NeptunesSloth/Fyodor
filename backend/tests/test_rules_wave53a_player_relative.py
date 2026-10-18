"""Wave 53A: player-relative selectors (CR 2026-09-25), real Oracle text (tests/fixtures/wave53a_cards.json, from data/cards.sqlite). Every scenario checks the replay
and a save and a load.

* 115.1, 115.3, 601.2c: each word "target" is its own group, chosen in order - "another target creature that player controls" is chosen after the first creature,
  among the creatures of the player who controls it (Mutiny, Breaking of the Fellowship); "target player skips ... Tap up to five target permanents that player
  controls" among that player's permanents (Yosei, the Morning Star).
* 608.2b, 608.2h: a target that stops being "controlled by that player" is illegal as the spell resolves; the player is the one the earlier target had (last known
  information if it left).
* 608.2c: "Destroy target creature an opponent controls. Each other creature that player controls gets -2/-0" - the second instruction is about the controller of the
  target, as it was (Public Execution); "each other" is other than the target (Flames of the Raze-Boar).
* 707.10c / 115.7d: a copy that chooses a new first target re-binds "that player" for the second.
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import coverage, designations
from app.rules.plan import Plan
from tests.game_helpers import act
from tests.test_rules_conditionals import settle
from tests.test_rules_wave34b_activated import attack, stops, to_phase
from tests.wave9c_kit import card_named, check, mana, pt, put, to_hand, zone_of
from tests.wave53a_kit import alice_next, open_repo, table

BEARS, GIANT, ANGEL = "Grizzly Bears", "Hill Giant", "Serra Angel"


@pytest.fixture()
def cards(settings):
    yield from open_repo(settings)


@pytest.mark.parametrize("name", ["Mutiny", "Breaking of the Fellowship", "Yosei, the Morning Star", "Public Execution", "Flames of the Raze-Boar", "Mark for Death"])
def test_the_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


def three(cards, alice=(), bob=(), carol=()):
    s = table(cards, [*alice, BEARS], [*bob, BEARS, GIANT], [*carol, BEARS, GIANT])
    return s


# -- Mutiny --------------------------------------------------------------------------------------------------------------------------
def test_mutiny_a_creature_of_the_same_player_takes_the_damage(cards):
    s = three(cards, ["Mutiny"])
    giant, bears = put(s, GIANT, "p2"), put(s, BEARS, "p2")
    to_hand(s, "Mutiny")
    mana(s, "p1", R=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Mutiny").id, targets=[giant.id, bears.id], target_counts=[1, 1])
    settle(s)
    assert zone_of(s, BEARS, "p2") == "p2:graveyard" and zone_of(s, GIANT, "p2") == "p2:battlefield"  # 3 damage from Bob's own Giant
    check(s)


def test_mutiny_the_second_target_is_not_another_players_creature(cards):
    s = three(cards, ["Mutiny"])
    giant, theirs, carols, mine = put(s, GIANT, "p2"), put(s, BEARS, "p2"), put(s, BEARS, "p3"), put(s, BEARS)
    to_hand(s, "Mutiny")
    mana(s, "p1", R=1)
    for wrong in (carols, mine, giant):  # Carol's, Alice's own, or the first target again (115.3: "another")
        with pytest.raises(ActionError):
            act(s, "p1", type="cast_spell", card_id=card_named(s, "Mutiny").id, targets=[giant.id, wrong.id], target_counts=[1, 1])
    assert zone_of(s, "Mutiny") == "p1:hand"
    # asked for the second target after the first, only Bob's other creature is offered
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Mutiny").id, targets=[giant.id], target_counts=[1])
    d = s.state.rules.decision
    assert d is not None and [o.id for o in d.options] == [theirs.id]
    check(s)


def test_mutiny_follows_the_controller_of_the_first_target_even_when_it_is_another_opponent(cards):
    s = three(cards, ["Mutiny"])
    giant, carols = put(s, GIANT, "p3"), put(s, BEARS, "p3")
    put(s, BEARS, "p2")
    to_hand(s, "Mutiny")
    mana(s, "p1", R=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Mutiny").id, targets=[giant.id, carols.id], target_counts=[1, 1])
    settle(s)
    assert s.state.cards[carols.id].zone == "p3:graveyard" and zone_of(s, BEARS, "p2") == "p2:battlefield"
    check(s)


def test_mutiny_with_no_second_creature_cannot_be_cast_at_a_lone_creature(cards):
    s = three(cards, ["Mutiny"])
    giant = put(s, GIANT, "p2")
    put(s, BEARS, "p3")  # Carol's creature isn't Bob's
    to_hand(s, "Mutiny")
    mana(s, "p1", R=1)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=card_named(s, "Mutiny").id, targets=[giant.id], target_counts=[1])
        settle(s)
    check(s)


def test_mutiny_cast_free_needs_two_creatures_of_one_player(cards):
    """601.2c: a spell cast for free (cast_free) with no way to choose its second target is not offered (casting.free_cast_problem)."""
    from app.rules import characteristics as chars
    from app.rules.casting import free_cast_problem
    from app.rules.plan import Plan

    s = three(cards, ["Mutiny"])
    put(s, GIANT, "p2")
    put(s, BEARS, "p3")  # two creatures, two players
    mutiny = card_named(s, "Mutiny")
    plan = Plan(s.state, "p1", s.cards, None)
    ch = chars.of(mutiny, plan.info)
    assert free_cast_problem(plan, "p1", mutiny, ch) == "Mutiny has no legal target"
    put(s, BEARS, "p2")
    assert free_cast_problem(Plan(s.state, "p1", s.cards, None), "p1", mutiny, ch) is None


def test_breaking_of_the_fellowship_also_tempts_with_the_ring(cards):
    s = three(cards, ["Breaking of the Fellowship", BEARS])
    giant, bears = put(s, GIANT, "p2"), put(s, BEARS, "p2")
    mine = put(s, BEARS)
    to_hand(s, "Breaking of the Fellowship")
    mana(s, "p1", R=1, C=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Breaking of the Fellowship").id, targets=[giant.id, bears.id], target_counts=[1, 1])
    settle(s)
    assert zone_of(s, BEARS, "p2") == "p2:graveyard" and s.state.cards[mine.id].zone == "p1:battlefield"
    assert designations._bearer_card(Plan(s.state, "p1", s.cards, None), "p1").id == mine.id  # The Ring tempts you: her only creature is the Ring-bearer
    check(s)


# -- Yosei, the Morning Star ----------------------------------------------------------------------------------------------------------
def test_yosei_taps_permanents_of_the_player_it_made_skip_the_untap_step(cards):
    s = three(cards, ["Yosei, the Morning Star", "Murder"])
    yosei = put(s, "Yosei, the Morning Star")
    theirs, carols = put(s, GIANT, "p2"), put(s, GIANT, "p3")
    to_hand(s, "Murder")
    mana(s, "p1", B=2, C=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Murder").id, targets=[yosei.id])
    for _ in range(4):  # Murder resolves, Yosei dies and its trigger asks for its targets
        if s.state.rules.decision is None:
            act(s, s.state.rules.priority, type="pass_priority")
    d = s.state.rules.decision
    assert d is not None and {o.id for o in d.options} >= {"p2", "p3"}
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["p2"])
    d = s.state.rules.decision
    assert d is not None and [o.id for o in d.options] == [theirs.id]  # Bob's permanents only: Carol's Giant is not offered
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[theirs.id])
    settle(s)
    assert s.state.cards[theirs.id].tapped and not s.state.cards[carols.id].tapped
    check(s)


# -- Public Execution / Flames of the Raze-Boar / Mark for Death ------------------------------------------------------------------------
def test_public_execution_weakens_the_other_creatures_of_the_players_it_destroyed_from(cards):
    s = three(cards, ["Public Execution"], [ANGEL], [ANGEL])
    angel = put(s, ANGEL, "p2")
    put(s, BEARS, "p2"), put(s, ANGEL, "p3"), put(s, BEARS)
    to_hand(s, "Public Execution")
    mana(s, "p1", B=1, C=5)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Public Execution").id, targets=[angel.id])
    settle(s)
    assert s.state.cards[angel.id].zone == "p2:graveyard"
    assert pt(s, BEARS, "p2") == (0, 2)  # -2/-0: Bob's other creature
    assert pt(s, ANGEL, "p3") == (4, 4) and pt(s, BEARS) == (2, 2)  # Carol's and Alice's are not Bob's
    check(s)


def test_flames_of_the_raze_boar_hurts_the_others_only_with_a_power_four_creature(cards):
    s = three(cards, ["Flames of the Raze-Boar", ANGEL])
    victim, bears = put(s, GIANT, "p2"), put(s, BEARS, "p2")
    put(s, BEARS, "p3")
    to_hand(s, "Flames of the Raze-Boar")
    mana(s, "p1", R=1, C=5)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Flames of the Raze-Boar").id, targets=[victim.id])
    settle(s)
    assert s.state.cards[victim.id].zone == "p2:graveyard" and s.state.cards[bears.id].zone == "p2:battlefield"  # no creature of Alice's with power 4 or greater
    check(s)


def test_flames_of_the_raze_boar_with_a_power_four_creature(cards):
    s = three(cards, ["Flames of the Raze-Boar", ANGEL])
    put(s, ANGEL)
    victim, bears, carols, mine = put(s, GIANT, "p2"), put(s, BEARS, "p2"), put(s, BEARS, "p3"), put(s, BEARS)
    to_hand(s, "Flames of the Raze-Boar")
    mana(s, "p1", R=1, C=5)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Flames of the Raze-Boar").id, targets=[victim.id])
    settle(s)
    assert s.state.cards[victim.id].zone == "p2:graveyard" and s.state.cards[bears.id].zone == "p2:graveyard"
    assert s.state.cards[carols.id].zone == "p3:battlefield" and s.state.cards[mine.id].zone == "p1:battlefield"
    check(s)


def test_flames_leaves_the_target_out_of_the_others(cards):
    """4 damage to a 4/4 target and then 2 to "each other creature that player controls": the target is not one of the others (it would take 6 in all if it were; the
    other 4/4 takes 2 and lives)."""
    s = three(cards, ["Flames of the Raze-Boar", ANGEL], [(2, ANGEL)])
    put(s, ANGEL)
    victim = put(s, ANGEL, "p2")
    big = next(c for c in s.state.cards.values() if c.name == ANGEL and c.owner == "p2" and c.id != victim.id)
    act(s, "p2", type="move", card_ids=[big.id], to={"player": "p2", "zone": "battlefield"})
    to_hand(s, "Flames of the Raze-Boar")
    mana(s, "p1", R=1, C=5)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Flames of the Raze-Boar").id, targets=[victim.id])
    settle(s)
    assert s.state.cards[victim.id].zone == "p2:graveyard" and s.state.cards[big.id].zone == "p2:battlefield" and s.state.cards[big.id].damage == 2
    check(s)


def test_mark_for_death_the_others_of_that_player_cannot_block(cards):
    s = three(cards, ["Mark for Death", BEARS])
    stops(s)
    mine = put(s, BEARS)
    marked, other = put(s, GIANT, "p2"), put(s, BEARS, "p2")
    put(s, BEARS, "p3")
    alice_next(s)
    to_hand(s, "Mark for Death")
    mana(s, "p1", R=1, C=3)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Mark for Death").id, targets=[marked.id])
    settle(s)
    attack(s, mine)
    to_phase(s, "declare_blockers")
    with pytest.raises(ActionError):
        act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": other.id, "attacker_id": mine.id}])
    act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": marked.id, "attacker_id": mine.id}])
    check(s)


# -- a copy chooses new targets (707.10c, 115.7d) ----------------------------------------------------------------------------------------
def test_a_copy_of_mutiny_binds_the_second_target_to_its_new_first_target(cards):
    s = three(cards, ["Mutiny", "Twincast"])
    act(s, "p1", type="set_prefs", hold_priority=True)
    giant, bears = put(s, GIANT, "p2"), put(s, BEARS, "p2")
    cgiant, cbears = put(s, GIANT, "p3"), put(s, BEARS, "p3")
    to_hand(s, "Mutiny")
    to_hand(s, "Twincast")
    mana(s, "p1", R=1, U=2)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Mutiny").id, targets=[giant.id, bears.id], target_counts=[1, 1])
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Twincast").id, targets=[card_named(s, "Mutiny").id])
    for _ in range(4):
        if s.state.rules.decision is None:
            act(s, s.state.rules.priority, type="pass_priority")
    d = s.state.rules.decision
    assert d is not None and d.resume["step"] == "copy_target"
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[cgiant.id])  # a new first target: Carol's Giant
    d = s.state.rules.decision
    assert d is not None and sorted(o.id for o in d.options if o.id != "keep") == [cbears.id]  # Carol's other creature only: not Bob's, not Carol's Giant again
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["keep"])  # Bob's Bears are not Carol's: asked again
    d = s.state.rules.decision
    assert d is not None and d.resume["step"] == "copy_target" and d.resume["picks"] == []
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[cgiant.id])
    d = s.state.rules.decision
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[cbears.id])
    settle(s)
    assert s.state.cards[cbears.id].zone == "p3:graveyard" and s.state.cards[bears.id].zone == "p2:graveyard"  # the copy and the original both resolved
    check(s)

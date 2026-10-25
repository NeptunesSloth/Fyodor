"""Wave 100C: pumps, riders and conditions of instants and sorceries (app/rules/static_spell100c.py), real Oracle text
(tests/fixtures/wave100c_static_spells_cards.json; CR 2026-09-25). Every scenario checks the replay and a save and a load.

* 611.2a / 611.2c: "until end of turn" leading a sentence is each effect's duration; "other creatures you control" is the group as the spell
  resolves, other than the target.
* 601.2c / 115.1: "up to one [other] target" may choose none; a later group is distinct from the earlier ones (115.3).
* 701.16a: "Target player investigates": that player creates the Clue. 701.50a: connive (the creature's controller draws, then discards).
* 608.2c: a condition in a later sentence is checked as that sentence is reached ("If it's a Cyclops", "If target player has exactly 10 life").
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import coverage
from tests.game_helpers import act
from tests.wave9c_kit import build, check, life
from tests.wave100c_kit import (
    cast,
    chars,
    move,
    named,
    one,
    open_repo,
    pt_of,
    put_on,
    settle,
    start_cast,
    to_phase,
    walker,
    zone,
)

PROMOTED = ["Sigil Blessing", "Revenge of the Hunted", "Liliana's Triumph", "Liliana's Defeat", "Timely Reinforcements", "Undercity Plague",
            "Unstable Experiment", "Trickster's Stratagem", "Aspirant's Ascent", "Arm the Cathars", "Panther Pounce", "Hidetsugu's Second Rite",
            "Eye Gouge", "Ghostfire"]


@pytest.fixture()
def cards(settings):
    yield from open_repo(settings)


@pytest.mark.parametrize("name", PROMOTED)
def test_every_card_is_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def test_ghostfire_is_a_colorless_spell_that_deals_three(cards):
    """Ghostfire: "Ghostfire is colorless." (604.3, a characteristic-defining ability in every zone) / "… deals 3 damage to any target." """
    s = build(cards, ["Ghostfire"], [])
    act(s, "p1", type="set_prefs", hold_priority=True)
    spell = start_cast(s, "Ghostfire", targets=["p2"], R=1, C=2)
    assert zone(s, spell) == "stack" and not chars(s, spell).colors
    settle(s)
    assert life(s, "p2") == 37 and not chars(s, spell).colors
    check(s)


def test_sigil_blessing_pumps_the_target_and_each_other_creature_you_control(cards):
    """Sigil Blessing: "Until end of turn, target creature you control gets +3/+3 and other creatures you control get +1/+1." The target gets
    +3/+3 only (not +4/+4); Bob's creature nothing."""
    s = build(cards, ["Sigil Blessing", "Grizzly Bears", "Llanowar Elves"], ["Grizzly Bears"])
    bear, elves, theirs = put_on(s, "Grizzly Bears"), put_on(s, "Llanowar Elves"), put_on(s, "Grizzly Bears", "p2")
    with pytest.raises(ActionError):
        start_cast(s, "Sigil Blessing", targets=[theirs.id], G=1, W=1)
    cast(s, "Sigil Blessing", targets=[bear.id])
    assert pt_of(s, bear) == (5, 5) and pt_of(s, elves) == (2, 2) and pt_of(s, theirs) == (2, 2)
    check(s)


def test_revenge_of_the_hunted_makes_every_able_creature_block_it(cards):
    """Revenge of the Hunted: "Until end of turn, target creature gets +6/+6 and gains trample, and all creatures able to block it this turn do
    so." (509.1c) Bob may not leave his creature out of the block."""
    s = build(cards, ["Revenge of the Hunted", "Grizzly Bears"], ["Llanowar Elves"])
    bear, elves = put_on(s, "Grizzly Bears"), put_on(s, "Llanowar Elves", "p2")
    to_phase(s, "main1", turn=3)
    cast(s, "Revenge of the Hunted", targets=[bear.id], G=2, C=4)
    assert pt_of(s, bear) == (8, 8) and "trample" in chars(s, bear).keywords
    act(s, "p1", type="pass_priority")
    for _ in range(10):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_attackers":
            break
        act(s, s.state.rules.priority, type="pass_priority")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": bear.id, "target": "p2"}])
    for _ in range(10):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_blockers":
            break
        act(s, s.state.rules.priority, type="pass_priority")
    with pytest.raises(ActionError):
        act(s, "p2", type="declare_blockers", blocks=[])
    act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": elves.id, "attacker_id": bear.id}])
    assert s.state.cards[elves.id].is_blocking
    check(s)


def test_lilianas_triumph_discards_too_only_with_a_liliana(cards):
    """Liliana's Triumph: "Each opponent sacrifices a creature of their choice. If you control a Liliana planeswalker, each opponent also
    discards a card." Without one, the sacrifice alone."""
    for with_liliana in (False, True):
        s = build(cards, ["Liliana's Triumph", "Liliana of the Veil"], ["Grizzly Bears", "Opt"])
        bear = put_on(s, "Grizzly Bears", "p2")
        for c in list(s.state.zones["p2:hand"]):
            move(s, s.state.cards[c], "library")
        opt = move(s, one(s, "Opt", "p2"), "hand")
        if with_liliana:
            walker(s, "Liliana of the Veil")
        cast(s, "Liliana's Triumph", B=1, C=1)
        assert zone(s, bear) == "p2:graveyard"
        assert zone(s, opt) == ("p2:graveyard" if with_liliana else "p2:hand")
        check(s)


def test_lilianas_defeat_costs_a_destroyed_lilianas_controller_three_life(cards):
    """Liliana's Defeat: "Destroy target black creature or black planeswalker. If that permanent was a Liliana planeswalker, her controller
    loses 3 life." A black creature: no life loss."""
    s = build(cards, ["Liliana's Defeat"], ["Liliana of the Veil", "Twisted Abomination"])
    lili = walker(s, "Liliana of the Veil", "p2")
    cast(s, "Liliana's Defeat", targets=[lili.id], B=1)
    assert zone(s, lili) == "p2:graveyard" and life(s, "p2") == 37
    check(s)
    s = build(cards, ["Liliana's Defeat"], ["Twisted Abomination"])
    zombie = put_on(s, "Twisted Abomination", "p2")
    cast(s, "Liliana's Defeat", targets=[zombie.id], B=1)
    assert zone(s, zombie) == "p2:graveyard" and life(s, "p2") == 40
    check(s)


def test_timely_reinforcements_checks_each_sentence_against_an_opponent(cards):
    """Timely Reinforcements: life lower than an opponent's: gain 6; fewer creatures: three Soldiers. Equal life, more creatures: nothing."""
    s = build(cards, ["Timely Reinforcements"], ["Grizzly Bears"])
    put_on(s, "Grizzly Bears", "p2")
    act(s, "p1", type="set_life", player="p1", value=30)
    cast(s, "Timely Reinforcements", W=1, C=2)
    assert life(s) == 36 and len([c for c in s.state.cards.values() if c.name == "Soldier" and c.zone == "p1:battlefield"]) == 3
    check(s)
    s = build(cards, ["Timely Reinforcements", "Grizzly Bears"], [])
    put_on(s, "Grizzly Bears")
    cast(s, "Timely Reinforcements", W=1, C=2)
    assert life(s) == 40 and not [c for c in s.state.cards.values() if c.name == "Soldier"]
    check(s)


def test_undercity_plague_life_discard_then_sacrifice_in_order(cards):
    """Undercity Plague: "Target player loses 1 life, discards a card, then sacrifices a permanent of their choice." (and cipher: no creature
    to encode it on, it goes to the graveyard)."""
    s = build(cards, ["Undercity Plague"], ["Grizzly Bears", "Opt"])
    bear, opt = put_on(s, "Grizzly Bears", "p2"), move(s, one(s, "Opt", "p2"), "hand")
    hand = len(s.state.zones["p2:hand"])
    spell = cast(s, "Undercity Plague", targets=["p2"], prefer=["Opt", "Grizzly Bears"], B=2, C=4)
    assert life(s, "p2") == 39 and zone(s, bear) == "p2:graveyard" and len(s.state.zones["p2:hand"]) == hand - 1
    assert zone(s, opt) == "p2:graveyard" and zone(s, spell) == "p1:graveyard"
    check(s)


def test_unstable_experiment_draws_and_connives_with_one_target_or_just_draws_with_none(cards):
    """Unstable Experiment: "Target player draws a card, then up to one target creature you control connives." No creature chosen: the draw
    alone. With one: its controller draws, then discards; a nonland discard puts a +1/+1 counter on it (701.50a)."""
    s = build(cards, ["Unstable Experiment", "Grizzly Bears", "Opt"], [])
    hand = len(s.state.zones["p1:hand"])
    cast(s, "Unstable Experiment", targets=["p1"], target_counts=[1, 0], U=1, C=1)
    assert len(s.state.zones["p1:hand"]) == hand + 1  # (one card drawn, none discarded)
    check(s)
    s = build(cards, ["Unstable Experiment", "Grizzly Bears", "Opt"], [])
    bear, opt = put_on(s, "Grizzly Bears"), move(s, one(s, "Opt"), "hand")
    cast(s, "Unstable Experiment", targets=["p1", bear.id], target_counts=[1, 1], prefer=["Opt"], U=1, C=1)
    assert zone(s, opt) == "p1:graveyard" and s.state.cards[bear.id].counters.get("+1/+1") == 1
    check(s)


def test_tricksters_stratagem_tucks_the_creature_then_connives_up_to_one(cards):
    """Trickster's Stratagem: the owner of the opponent's creature puts it second from the top or on the bottom (their choice), then up to one
    creature of Alice's connives."""
    s = build(cards, ["Trickster's Stratagem", "Grizzly Bears", "Opt"], ["Llanowar Elves"])
    elves, bear = put_on(s, "Llanowar Elves", "p2"), put_on(s, "Grizzly Bears")
    opt = move(s, one(s, "Opt"), "hand")
    with pytest.raises(ActionError):
        start_cast(s, "Trickster's Stratagem", targets=[bear.id, bear.id], target_counts=[1, 1], U=1, C=3)
    cast(s, "Trickster's Stratagem", targets=[elves.id, bear.id], target_counts=[1, 1], prefer=["bottom", "Opt"])
    assert zone(s, elves) == "p2:library" and zone(s, opt) == "p1:graveyard"
    assert s.state.cards[bear.id].counters.get("+1/+1") == 1
    check(s)


def test_aspirants_ascent_grants_flying_and_toxic_until_end_of_turn(cards):
    """Aspirant's Ascent: "Until end of turn, target creature gets +1/+3 and gains flying and toxic 1." (702.164)"""
    s = build(cards, ["Aspirant's Ascent", "Grizzly Bears"], [])
    bear = put_on(s, "Grizzly Bears")
    cast(s, "Aspirant's Ascent", targets=[bear.id], U=1)
    ch = chars(s, bear)
    assert pt_of(s, bear) == (3, 5) and "flying" in ch.keywords and "toxic" in ch.keywords
    act(s, "p1", type="set_stops", own=[], others=["main1"], smart_pass=False)
    to_phase(s, "main1", turn=2)
    ch = chars(s, bear)
    assert pt_of(s, bear) == (2, 2) and "flying" not in ch.keywords and "toxic" not in ch.keywords
    check(s)


def test_arm_the_cathars_three_distinct_targets_and_vigilance_for_each(cards):
    """Arm the Cathars: +3/+3, up to one other +2/+2, up to one other +1/+1; "Those creatures gain vigilance". The same creature can't be
    chosen twice (115.3)."""
    s = build(cards, ["Arm the Cathars", "Grizzly Bears", "Llanowar Elves", "Benalish Hero"], [])
    a, b, c = put_on(s, "Grizzly Bears"), put_on(s, "Llanowar Elves"), put_on(s, "Benalish Hero")
    with pytest.raises(ActionError):
        start_cast(s, "Arm the Cathars", targets=[a.id, a.id], target_counts=[1, 1, 0], W=2, C=1)
    cast(s, "Arm the Cathars", targets=[a.id, b.id, c.id], target_counts=[1, 1, 1])
    assert pt_of(s, a) == (5, 5) and pt_of(s, b) == (3, 3) and pt_of(s, c) == (2, 2)
    assert all("vigilance" in chars(s, x).keywords for x in (a, b, c))
    check(s)


def test_panther_pounce_the_target_player_investigates_and_the_creature_untaps(cards):
    """Panther Pounce: "Target player investigates. Target creature gets +1/+0 and gains flying until end of turn. Untap it." Bob gets the Clue."""
    s = build(cards, ["Panther Pounce", "Grizzly Bears"], [])
    bear = put_on(s, "Grizzly Bears")
    act(s, "p1", type="tap", card_ids=[bear.id], tapped=True)
    cast(s, "Panther Pounce", targets=["p2", bear.id], target_counts=[1, 1], W=1)
    clues = [c for c in s.state.cards.values() if c.name == "Clue" and c.zone.endswith(":battlefield")]
    assert [c.controller for c in clues] == ["p2"]
    assert pt_of(s, bear) == (3, 2) and "flying" in chars(s, bear).keywords and not s.state.cards[bear.id].tapped
    check(s)


@pytest.mark.parametrize("bob_life", [10, 11])
def test_hidetsugus_second_rite_needs_exactly_ten_life(cards, bob_life):
    """Hidetsugu's Second Rite: "If target player has exactly 10 life, Hidetsugu's Second Rite deals 10 damage to that player." """
    s = build(cards, ["Hidetsugu's Second Rite"], [])
    act(s, "p2", type="set_life", player="p2", value=bob_life)
    cast(s, "Hidetsugu's Second Rite", targets=["p2"], R=1, C=3)
    assert life(s, "p2") == (0 if bob_life == 10 else 11)
    check(s)


def test_eye_gouge_destroys_only_a_cyclops(cards):
    """Eye Gouge: "Target creature gets -1/-1 until end of turn. If it's a Cyclops, destroy it." """
    s = build(cards, ["Eye Gouge"], ["Hulking Cyclops", "Grizzly Bears"])
    cyclops = put_on(s, "Hulking Cyclops", "p2")
    cast(s, "Eye Gouge", targets=[cyclops.id], B=1)
    assert zone(s, cyclops) == "p2:graveyard"
    check(s)
    s = build(cards, ["Eye Gouge"], ["Grizzly Bears"])
    bear = put_on(s, "Grizzly Bears", "p2")
    cast(s, "Eye Gouge", targets=[bear.id], B=1)
    assert zone(s, bear) == "p2:battlefield" and pt_of(s, bear) == (1, 1)
    check(s)


def test_named_helper_finds_every_copy(cards):
    s = build(cards, ["Grizzly Bears"], [])
    assert len(named(s, "Forest")) == 9
    settle(s)

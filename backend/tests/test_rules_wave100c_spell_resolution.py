"""Wave 100C: choices made as the spell resolves, later checks and multi-step instructions of instants and sorceries
(app/rules/static_spell100c.py), real Oracle text (tests/fixtures/wave100c_static_spells_cards.json; CR 2026-09-25). Every scenario checks
the replay and a save and a load.

* 608.2d: "A or B" (Essence Filter, Lava Storm): the controller chooses one as the spell resolves.
* 608.2c / 608.2h: a later sentence is judged as it is reached ("Then if that player … has more life than you"; "If its controller has more
  than four cards in hand"); a planeswalker's controller as it last existed.
* 502.3: "doesn't untap during its controller's next two untap steps": two of that player's untap steps.
* 508.1: "target player who attacked this turn": a player who declared attackers this turn.
* 701.21a: "sacrifices an artifact and a land": one of each, a permanent of both types chosen once only.
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import coverage
from tests.game_helpers import act
from tests.wave9c_kit import build, check, life
from tests.wave100c_kit import (
    cast,
    move,
    named,
    one,
    open_repo,
    put_on,
    settle,
    start_cast,
    three,
    to_phase,
    walker,
    zone,
)

PROMOTED = ["Essence Filter", "Lava Storm", "Tombfire", "Telekinesis", "Fire and Brimstone", "Structural Collapse", "Pulse of the Forge",
            "Feast of Worms", "Isildur's Fateful Strike", "No Witnesses", "False Memories", "Runic Repetition", "See Beyond"]


@pytest.fixture()
def cards(settings):
    yield from open_repo(settings)


@pytest.mark.parametrize("name", PROMOTED)
def test_every_card_is_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def declare(s, kind, pid, **payload):
    """Pass priority until ``pid`` is asked to declare attackers / blockers, then declare."""
    for _ in range(40):
        d = s.state.rules.decision
        if d is not None and d.kind == kind and d.player == pid:
            act(s, pid, type=kind, **payload)
            return
        if d is not None and d.kind in ("declare_attackers", "declare_blockers"):
            act(s, d.player, type=d.kind, **({"attackers": []} if d.kind == "declare_attackers" else {"blocks": []}))
            continue
        act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError(f"{pid} was never asked: {kind}")


def priority_in(s, phase, pid="p1"):
    for _ in range(20):
        if s.state.turn.phase == phase and s.state.rules.priority == pid and s.state.rules.decision is None:
            return
        act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError(f"no priority for {pid} in {phase}")


def alice_attacks(s, attacker, blocker=None):
    """Turn 3: Alice attacks Bob with ``attacker`` (Bob blocks with ``blocker``); Alice has priority in the declare blockers step."""
    act(s, "p1", type="set_stops", own=["declare_blockers"], others=[], smart_pass=False)
    to_phase(s, "declare_attackers", turn=3)
    declare(s, "declare_attackers", "p1", attackers=[{"card_id": attacker.id, "target": "p2"}])
    if blocker is not None:  # (no creature to block with: nobody is asked)
        declare(s, "declare_blockers", "p2", blocks=[{"blocker_id": blocker.id, "attacker_id": attacker.id}])
    priority_in(s, "declare_blockers")


# -- "A or B": the controller's choice as it resolves (608.2d) --------------------------------------------------------------------------
@pytest.mark.parametrize("nonwhite", [True, False])
def test_essence_filter_destroys_all_enchantments_or_only_the_nonwhite_ones(cards, nonwhite):
    """Essence Filter: "Destroy all enchantments or all nonwhite enchantments." Holy Strength is white, Propaganda blue."""
    s = build(cards, ["Essence Filter", "Grizzly Bears", "Holy Strength"], ["Propaganda"])
    bear, strength = put_on(s, "Grizzly Bears"), put_on(s, "Holy Strength")
    act(s, "p1", type="attach", card_ids=[strength.id], to=bear.id)
    propaganda = put_on(s, "Propaganda", "p2")
    cast(s, "Essence Filter", prefer=["All nonwhite enchantments" if nonwhite else "All enchantments"], G=2, C=1)
    assert zone(s, propaganda) == "p2:graveyard"
    assert zone(s, strength) == ("p1:battlefield" if nonwhite else "p1:graveyard") and zone(s, bear) == "p1:battlefield"
    check(s)


@pytest.mark.parametrize("blockers", [True, False])
def test_lava_storm_hits_each_attacking_or_each_blocking_creature(cards, blockers):
    """Lava Storm: "… 2 damage to each attacking creature or … 2 damage to each blocking creature." Alice's attacker and Bob's blocker; Alice
    chooses which group (her other creature, out of combat, is never hit)."""
    s = build(cards, ["Lava Storm", "Grizzly Bears", "Llanowar Elves"], ["Grizzly Bears"])
    attacker, home, blocker = put_on(s, "Grizzly Bears"), put_on(s, "Llanowar Elves"), put_on(s, "Grizzly Bears", "p2")
    alice_attacks(s, attacker, blocker)
    cast(s, "Lava Storm", prefer=["Each blocking creature" if blockers else "Each attacking creature"], R=2, C=3)
    assert zone(s, blocker) == ("p2:graveyard" if blockers else "p2:battlefield")
    assert zone(s, attacker) == ("p1:battlefield" if blockers else "p1:graveyard") and zone(s, home) == "p1:battlefield"
    check(s)


# -- graveyards and exile ---------------------------------------------------------------------------------------------------------------
def test_tombfire_exiles_only_the_flashback_cards_of_the_target_player(cards):
    """Tombfire: "Target player exiles all cards with flashback from their graveyard." Bob's Think Twice goes; his Opt and Alice's own
    flashback card stay."""
    s = build(cards, ["Tombfire", "Deep Analysis"], ["Think Twice", "Opt"])
    twice, opt = move(s, one(s, "Think Twice", "p2"), "graveyard"), move(s, one(s, "Opt", "p2"), "graveyard")
    mine = move(s, one(s, "Deep Analysis"), "graveyard")
    cast(s, "Tombfire", targets=["p2"], B=1)
    assert zone(s, twice) == "p2:exile" and zone(s, opt) == "p2:graveyard" and zone(s, mine) == "p1:graveyard"
    check(s)


def test_runic_repetition_returns_only_your_own_exiled_flashback_card(cards):
    """Runic Repetition: "Return target exiled card with flashback you own to your hand." Not a card without flashback, not Bob's."""
    s = build(cards, ["Runic Repetition", "Think Twice", "Opt"], ["Deep Analysis"])
    twice, opt = move(s, one(s, "Think Twice"), "exile"), move(s, one(s, "Opt"), "exile")
    theirs = move(s, one(s, "Deep Analysis", "p2"), "exile")
    for bad in (opt, theirs):
        with pytest.raises(ActionError):
            start_cast(s, "Runic Repetition", targets=[bad.id], U=1, C=2)
    cast(s, "Runic Repetition", targets=[twice.id])
    assert zone(s, twice) == "p1:hand" and zone(s, opt) == "p1:exile" and zone(s, theirs) == "p2:exile"
    check(s)


def test_false_memories_mills_seven_then_exiles_seven_of_your_choice_at_the_end_step(cards):
    """False Memories: "Mill seven cards. At the beginning of the next end step, exile seven cards from your graveyard." Eight cards there
    then: one stays."""
    s = build(cards, ["False Memories", "Opt"], [])
    move(s, one(s, "Opt"), "graveyard")
    cast(s, "False Memories", U=1, C=1)
    assert len(s.state.zones["p1:graveyard"]) == 9  # (Opt, seven milled cards, False Memories)
    act(s, "p1", type="set_stops", own=["end"], others=[], smart_pass=False)
    to_phase(s, "end", turn=1)
    settle(s)
    assert len([c for c in s.state.zones["p1:exile"]]) == 7 and len(s.state.zones["p1:graveyard"]) == 2
    check(s)


# -- later checks and their players -----------------------------------------------------------------------------------------------------
@pytest.mark.parametrize(("bob_life", "back"), [(40, False), (50, True)])
def test_pulse_of_the_forge_returns_to_hand_only_if_the_player_still_has_more_life(cards, bob_life, back):
    """Pulse of the Forge: 4 damage, then "if that player … has more life than you, return Pulse of the Forge to its owner's hand." Checked
    after the damage: 36 is not more than 40; 46 is."""
    s = build(cards, ["Pulse of the Forge"], [])
    act(s, "p2", type="set_life", player="p2", value=bob_life)
    spell = cast(s, "Pulse of the Forge", targets=["p2"], R=2, C=1)
    assert life(s, "p2") == bob_life - 4 and zone(s, spell) == ("p1:hand" if back else "p1:graveyard")
    check(s)


def test_pulse_of_the_forge_reads_a_dead_planeswalkers_last_controller(cards):
    """Pulse of the Forge at Bob's Liliana (3 loyalty, she dies): Bob, her controller as she last existed, has 41 life: back to hand."""
    s = build(cards, ["Pulse of the Forge"], ["Liliana of the Veil"])
    lili = walker(s, "Liliana of the Veil", "p2")
    act(s, "p2", type="set_life", player="p2", value=41)
    spell = cast(s, "Pulse of the Forge", targets=[lili.id], R=2, C=1)
    assert zone(s, lili) == "p2:graveyard" and zone(s, spell) == "p1:hand"
    check(s)


@pytest.mark.parametrize("legendary", [True, False])
def test_feast_of_worms_makes_the_controller_sacrifice_another_land_only_for_a_legendary_land(cards, legendary):
    """Feast of Worms: "Destroy target land. If that land was legendary, its controller sacrifices another land of their choice." """
    s = build(cards, ["Feast of Worms"], ["Urborg, Tomb of Yawgmoth"])
    target = put_on(s, "Urborg, Tomb of Yawgmoth", "p2") if legendary else move(s, named(s, "Island", "p2")[0], "battlefield")
    island = move(s, [c for c in named(s, "Island", "p2") if c.id != target.id][0], "battlefield")
    cast(s, "Feast of Worms", targets=[target.id], G=2, C=3)
    assert zone(s, target) == "p2:graveyard" and zone(s, island) == ("p2:graveyard" if legendary else "p2:battlefield")
    check(s)


@pytest.mark.parametrize(("in_hand", "exiled"), [(7, 3), (4, 0)])
def test_isildurs_fateful_strike_exiles_the_cards_beyond_four(cards, in_hand, exiled):
    """Isildur's Fateful Strike (Alice controls the legendary Sliver Queen): Bob's creature is destroyed; with seven cards in hand he exiles
    three of his choice, with four none."""
    s = build(cards, ["Isildur's Fateful Strike", "Sliver Queen"], ["Grizzly Bears"])
    put_on(s, "Sliver Queen")
    bear = put_on(s, "Grizzly Bears", "p2")
    for c in list(s.state.zones["p2:hand"]):
        move(s, s.state.cards[c], "library")
    for c in named(s, "Island", "p2")[:in_hand]:
        move(s, c, "hand")
    cast(s, "Isildur's Fateful Strike", targets=[bear.id], B=2, C=2)
    assert zone(s, bear) == "p2:graveyard"
    assert len(s.state.zones["p2:hand"]) == in_hand - exiled and len(s.state.zones.get("p2:exile", [])) == exiled
    check(s)


def test_isildurs_fateful_strike_needs_a_legendary_creature_or_planeswalker(cards):
    s = build(cards, ["Isildur's Fateful Strike"], ["Grizzly Bears"])
    bear = put_on(s, "Grizzly Bears", "p2")
    with pytest.raises(ActionError):
        start_cast(s, "Isildur's Fateful Strike", targets=[bear.id], B=2, C=2)


def test_structural_collapse_one_artifact_and_another_permanent_as_the_land(cards):
    """Structural Collapse: Bob controls Sol Ring and Seat of the Synod (an artifact land), no other land. He sacrifices Sol Ring as the
    artifact; then Seat of the Synod is the land. 2 damage to Bob."""
    s = build(cards, ["Structural Collapse"], ["Sol Ring", "Seat of the Synod"])
    ring, seat = put_on(s, "Sol Ring", "p2"), put_on(s, "Seat of the Synod", "p2")
    cast(s, "Structural Collapse", targets=["p2"], prefer=["Sol Ring"], R=1, C=5)
    assert zone(s, ring) == "p2:graveyard" and zone(s, seat) == "p2:graveyard" and life(s, "p2") == 38
    check(s)


def test_structural_collapse_never_counts_one_artifact_land_twice(cards):
    """Bob's only artifact is Seat of the Synod (no choice: it is the artifact); the land is then one of his Islands, not the Seat again."""
    s = build(cards, ["Structural Collapse"], ["Seat of the Synod"])
    seat, island = put_on(s, "Seat of the Synod", "p2"), move(s, named(s, "Island", "p2")[0], "battlefield")
    cast(s, "Structural Collapse", targets=["p2"], R=1, C=5)
    assert zone(s, seat) == "p2:graveyard" and zone(s, island) == "p2:graveyard" and life(s, "p2") == 38
    check(s)


def test_no_witnesses_the_players_tied_for_most_creatures_investigate_then_all_creatures_die(cards):
    """No Witnesses with three players: Alice and Bob control two creatures each, Carol one. Alice and Bob each get a Clue (it survives);
    every creature is destroyed."""
    s = three(cards, ["No Witnesses", "Grizzly Bears", "Llanowar Elves"], ["Grizzly Bears", "Llanowar Elves"], ["Grizzly Bears"])
    creatures = [put_on(s, n, p) for p, n in (("p1", "Grizzly Bears"), ("p1", "Llanowar Elves"), ("p2", "Grizzly Bears"),
                                              ("p2", "Llanowar Elves"), ("p3", "Grizzly Bears"))]
    cast(s, "No Witnesses", W=2, C=2)
    assert all(zone(s, c).endswith(":graveyard") for c in creatures)
    clues = sorted(c.controller for c in s.state.cards.values() if c.name == "Clue" and c.zone.endswith(":battlefield"))
    assert clues == ["p1", "p2"]
    check(s)


def test_see_beyond_draws_two_then_shuffles_a_chosen_card_from_hand_into_the_library(cards):
    s = build(cards, ["See Beyond", "Opt"], [])
    opt, _ = move(s, one(s, "Opt"), "hand"), move(s, one(s, "See Beyond"), "hand")
    hand, library = len(s.state.zones["p1:hand"]), len(s.state.zones["p1:library"])
    cast(s, "See Beyond", prefer=["Opt"], U=1, C=1)
    assert zone(s, opt) == "p1:library"
    assert len(s.state.zones["p1:hand"]) == hand - 1 + 2 - 1 and len(s.state.zones["p1:library"]) == library - 2 + 1
    check(s)


# -- combat history and untap steps -----------------------------------------------------------------------------------------------------
def test_fire_and_brimstone_targets_only_a_player_who_attacked_this_turn(cards):
    """Fire and Brimstone: "… 4 damage to target player who attacked this turn and 4 damage to you." On Alice's own turn Bob hasn't attacked
    (not a legal target); on Bob's turn, after he attacks, he is."""
    s = build(cards, ["Fire and Brimstone"], ["Grizzly Bears"])
    bear = put_on(s, "Grizzly Bears", "p2")
    with pytest.raises(ActionError):
        start_cast(s, "Fire and Brimstone", targets=["p2"], W=2, C=3)
    act(s, "p1", type="set_stops", own=[], others=["declare_blockers"], smart_pass=False)
    to_phase(s, "declare_attackers", turn=2)
    declare(s, "declare_attackers", "p2", attackers=[{"card_id": bear.id, "target": "p1"}])
    priority_in(s, "declare_blockers")
    cast(s, "Fire and Brimstone", targets=["p2"], W=2, C=3)
    assert life(s, "p2") == 36 and life(s) == 36  # (the bear's combat damage is still to come)
    check(s)


def test_telekinesis_prevents_its_combat_damage_and_keeps_it_tapped_for_two_untap_steps(cards):
    """Telekinesis on Alice's own attacker (turn 3): no combat damage to Bob; it stays tapped during her untap steps of turns 5 and 7 and
    untaps in turn 9."""
    s = build(cards, ["Telekinesis", "Grizzly Bears"], [])
    bear = put_on(s, "Grizzly Bears")
    alice_attacks(s, bear)
    cast(s, "Telekinesis", targets=[bear.id], U=2)
    to_phase(s, "main2", turn=3)
    assert life(s, "p2") == 40 and s.state.cards[bear.id].tapped
    for turn, tapped in ((5, True), (7, True), (9, False)):
        to_phase(s, "main1", turn=turn)
        assert s.state.cards[bear.id].tapped is tapped, turn
    check(s)

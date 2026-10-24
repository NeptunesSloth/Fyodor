"""Wave 100C: what players do — edicts, discards, draws and counts (app/rules/static_spell100c.py), real Oracle text
(tests/fixtures/wave100c_static_spells_cards.json; CR 2026-09-25). Every scenario checks the replay and a save and a load.

* 701.21a / 101.4: "sacrifices an artifact creature and a nonartifact creature of their choice": each opponent chooses one of each kind in
  APNAP order, then all are sacrificed at once; "If that player does" — a creature was actually sacrificed.
* 601.2c: "any number of target players / opponents"; "another target player" is a different player (115.3).
* 608.2h: "that many" is the number the instruction used ("draws cards equal to …, then discards that many"; "Sacrifice all creatures you
  control, then create that many …": the creatures actually sacrificed).
* 701.20a: a revealed hand is public; "a card for each Mountain and red card in it" counts a card once.
* 502.3: "Each attacking creature doesn't untap during its controller's next untap step": the creatures attacking as it resolves.
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
    zone,
)

PROMOTED = ["Perilous Predicament", "Self-Inflicted Wound", "Wheel and Deal", "Biomantic Mastery", "Cabal Conditioning", "Laquatus's Creativity",
            "Hellion Eruption", "Baleful Stare", "Withering Gaze", "Blow Your House Down", "Tangle", "Katara's Reversal"]


@pytest.fixture()
def cards(settings):
    yield from open_repo(settings)


@pytest.mark.parametrize("name", PROMOTED)
def test_every_card_is_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def hand(s, pid):
    return list(s.state.zones.get(f"{pid}:hand", []))


def empty_hand(s, pid):
    for cid in hand(s, pid):
        move(s, s.state.cards[cid], "library")


def test_perilous_predicament_each_opponent_sacrifices_one_of_each_kind(cards):
    """Perilous Predicament with three players: Bob has an artifact creature and two others (he picks one of those); Carol has no artifact
    creature (she sacrifices just a nonartifact one)."""
    s = three(cards, ["Perilous Predicament"], ["Frogmite", "Grizzly Bears", "Llanowar Elves"], ["Grizzly Bears", "Llanowar Elves"])
    frog, bob_bear, bob_elves = put_on(s, "Frogmite", "p2"), put_on(s, "Grizzly Bears", "p2"), put_on(s, "Llanowar Elves", "p2")
    carol_bear, carol_elves = put_on(s, "Grizzly Bears", "p3"), put_on(s, "Llanowar Elves", "p3")
    cast(s, "Perilous Predicament", prefer=["Llanowar Elves"], B=1, C=4)
    assert zone(s, frog) == "p2:graveyard" and zone(s, bob_elves) == "p2:graveyard" and zone(s, bob_bear) == "p2:battlefield"
    assert zone(s, carol_elves) == "p3:graveyard" and zone(s, carol_bear) == "p3:battlefield"
    check(s)


@pytest.mark.parametrize("green", [True, False])
def test_self_inflicted_wound_loses_life_only_if_a_creature_was_sacrificed(cards, green):
    """Self-Inflicted Wound: "Target opponent sacrifices a green or white creature of their choice. If that player does, they lose 2 life." """
    s = build(cards, ["Self-Inflicted Wound"], ["Grizzly Bears", "Frogmite"])
    victim = put_on(s, "Grizzly Bears" if green else "Frogmite", "p2")
    cast(s, "Self-Inflicted Wound", targets=["p2"], B=1, C=1)
    assert zone(s, victim) == ("p2:graveyard" if green else "p2:battlefield")
    assert life(s, "p2") == (38 if green else 40)
    check(s)


def test_wheel_and_deal_the_targets_discard_and_draw_seven_then_you_draw(cards):
    """Wheel and Deal: "Any number of target opponents each discard their hands, then draw seven cards." / "Draw a card." """
    s = build(cards, ["Wheel and Deal"], ["Opt", "Lightning Bolt"])
    empty_hand(s, "p2")
    opt, bolt = move(s, one(s, "Opt", "p2"), "hand"), move(s, one(s, "Lightning Bolt", "p2"), "hand")
    mine = len(hand(s, "p1"))
    cast(s, "Wheel and Deal", targets=["p2"], target_counts=[1], U=1, C=3)
    assert zone(s, opt) == "p2:graveyard" and zone(s, bolt) == "p2:graveyard" and len(hand(s, "p2")) == 7
    assert len(hand(s, "p1")) == mine + 1  # (one card drawn)
    check(s)
    s = build(cards, ["Wheel and Deal"], ["Opt"])
    theirs, mine = len(hand(s, "p2")), len(hand(s, "p1"))
    cast(s, "Wheel and Deal", targets=[], target_counts=[0], U=1, C=3)
    assert len(hand(s, "p2")) == theirs and len(hand(s, "p1")) == mine + 1
    check(s)


def test_biomantic_mastery_draws_for_two_different_players_creatures(cards):
    """Biomantic Mastery with three players: Bob has two creatures, Carol one: Alice draws three. The same player can't be both targets."""
    s = three(cards, ["Biomantic Mastery"], ["Grizzly Bears", "Llanowar Elves"], ["Grizzly Bears"])
    put_on(s, "Grizzly Bears", "p2"), put_on(s, "Llanowar Elves", "p2"), put_on(s, "Grizzly Bears", "p3")
    with pytest.raises(ActionError):
        start_cast(s, "Biomantic Mastery", targets=["p2", "p2"], target_counts=[1, 1], G=3, C=4)
    mine = len(hand(s, "p1"))
    cast(s, "Biomantic Mastery", targets=["p2", "p3"], target_counts=[1, 1])
    assert len(hand(s, "p1")) == mine - 1 + 3
    check(s)


def test_cabal_conditioning_discards_the_greatest_mana_value_among_your_permanents(cards):
    """Cabal Conditioning: Alice controls Sol Ring (1) and Wall of Stone (3): Bob discards three of his four cards."""
    s = build(cards, ["Cabal Conditioning", "Sol Ring", "Wall of Stone"], ["Opt", "Lightning Bolt", "Counterspell", "Mountain"])
    put_on(s, "Sol Ring"), put_on(s, "Wall of Stone")
    empty_hand(s, "p2")
    for name in ("Opt", "Lightning Bolt", "Counterspell", "Mountain"):
        move(s, one(s, name, "p2"), "hand")
    cast(s, "Cabal Conditioning", targets=["p2"], target_counts=[1], B=1, C=6)
    assert len(hand(s, "p2")) == 1 and len(s.state.zones["p2:graveyard"]) == 3
    check(s)


def test_laquatus_creativity_draws_as_many_as_in_hand_then_discards_that_many(cards):
    """Laquatus's Creativity: Bob has three cards: he draws three, then discards three (his choice) — six cards seen, three left."""
    s = build(cards, ["Laquatus's Creativity"], ["Opt", "Lightning Bolt", "Counterspell"])
    empty_hand(s, "p2")
    for name in ("Opt", "Lightning Bolt", "Counterspell"):
        move(s, one(s, name, "p2"), "hand")
    cast(s, "Laquatus's Creativity", targets=["p2"], U=1, C=4)
    assert len(hand(s, "p2")) == 3 and len(s.state.zones["p2:graveyard"]) == 3
    check(s)


def test_hellion_eruption_creates_a_hellion_for_each_creature_sacrificed(cards):
    """Hellion Eruption: "Sacrifice all creatures you control, then create that many 4/4 red Hellion creature tokens." Bob's creature stays."""
    s = build(cards, ["Hellion Eruption", "Grizzly Bears", "Llanowar Elves"], ["Grizzly Bears"])
    bear, elves, theirs = put_on(s, "Grizzly Bears"), put_on(s, "Llanowar Elves"), put_on(s, "Grizzly Bears", "p2")
    cast(s, "Hellion Eruption", R=1, C=5)
    assert zone(s, bear) == "p1:graveyard" and zone(s, elves) == "p1:graveyard" and zone(s, theirs) == "p2:battlefield"
    hellions = [c for c in s.state.cards.values() if c.name == "Hellion" and c.zone == "p1:battlefield"]
    assert len(hellions) == 2
    check(s)


@pytest.mark.parametrize("spell,cards_in_hand,drawn", [
    ("Baleful Stare", ["Mountain", "Lightning Bolt", "Opt", "Forest"], 2),
    ("Withering Gaze", ["Forest", "Llanowar Elves", "Grizzly Bears", "Lightning Bolt"], 3),
])
def test_baleful_stare_and_withering_gaze_draw_for_the_land_type_and_color_in_the_revealed_hand(cards, spell, cards_in_hand, drawn):
    """Baleful Stare / Withering Gaze: "Target opponent reveals their hand. You draw a card for each Mountain [Forest] and red [green] card in it." """
    s = build(cards, [spell], cards_in_hand)
    empty_hand(s, "p2")
    for name in cards_in_hand:
        move(s, one(s, name, "p2"), "hand")
    mine = len(hand(s, "p1"))
    cast(s, spell, targets=["p2"], U=1, C=2)
    assert len(hand(s, "p1")) == mine + drawn
    assert not any(s.state.cards[c].revealed_to for c in hand(s, "p2"))  # (shown while it resolved; hidden again after, 701.20a)
    check(s)


def test_blow_your_house_down_destroys_the_walls_and_the_rest_cant_block(cards):
    """Blow Your House Down: "Up to three target creatures can't block this turn. Destroy any of them that are Walls." """
    s = build(cards, ["Blow Your House Down", "Hulking Cyclops"], ["Wall of Stone", "Grizzly Bears"])
    cyclops, wall, bear = put_on(s, "Hulking Cyclops"), put_on(s, "Wall of Stone", "p2"), put_on(s, "Grizzly Bears", "p2")
    to_phase(s, "main1", turn=3)
    cast(s, "Blow Your House Down", targets=[wall.id, bear.id], target_counts=[2], R=1, C=2)
    assert zone(s, wall) == "p2:graveyard" and zone(s, bear) == "p2:battlefield"
    act(s, "p1", type="pass_priority")
    for _ in range(10):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_attackers":
            break
        act(s, s.state.rules.priority, type="pass_priority")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": cyclops.id, "target": "p2"}])
    for _ in range(10):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_blockers":
            break
        act(s, s.state.rules.priority, type="pass_priority")
    with pytest.raises(ActionError):
        act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": bear.id, "attacker_id": cyclops.id}])
    check(s)


def test_tangle_prevents_combat_damage_and_the_attackers_stay_tapped(cards):
    """Tangle: "Prevent all combat damage that would be dealt this turn." / "Each attacking creature doesn't untap during its controller's next
    untap step." Alice's attacker stays tapped in her next untap step; her creature that didn't attack untaps."""
    s = build(cards, ["Tangle", "Grizzly Bears", "Llanowar Elves"], ["Llanowar Elves"])
    bear, home, blocker = put_on(s, "Grizzly Bears"), put_on(s, "Llanowar Elves"), put_on(s, "Llanowar Elves", "p2")
    act(s, "p1", type="set_stops", own=["declare_blockers", "main1"], others=[], smart_pass=False)
    to_phase(s, "declare_attackers", turn=3)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": bear.id, "target": "p2"}])
    for _ in range(20):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_blockers":
            act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": blocker.id, "attacker_id": bear.id}])
            break
        act(s, s.state.rules.priority, type="pass_priority")
    for _ in range(10):
        if s.state.turn.phase == "declare_blockers" and s.state.rules.priority == "p1" and s.state.rules.decision is None:
            break
        act(s, s.state.rules.priority, type="pass_priority")
    act(s, "p1", type="tap", card_ids=[home.id], tapped=True)
    cast(s, "Tangle", G=1, C=1)
    to_phase(s, "main2", turn=3)
    assert zone(s, blocker) == "p2:battlefield" and zone(s, bear) == "p1:battlefield" and s.state.cards[blocker.id].damage == 0
    to_phase(s, "main1", turn=5)
    assert s.state.cards[bear.id].tapped and not s.state.cards[home.id].tapped
    check(s)


def test_katara_reversal_counters_a_spell_and_untaps(cards):
    """Katara's Reversal: "Counter up to four target spells and/or abilities." / "Untap up to four target artifacts and/or creatures." """
    s = build(cards, ["Katara's Reversal", "Opt", "Sol Ring"], [])
    ring = put_on(s, "Sol Ring")
    act(s, "p1", type="tap", card_ids=[ring.id], tapped=True)
    act(s, "p1", type="set_prefs", hold_priority=True)
    opt = start_cast(s, "Opt", U=1)
    assert zone(s, opt) == "stack"
    start_cast(s, "Katara's Reversal", targets=[opt.id, ring.id], target_counts=[1, 1], U=2, C=2)
    settle(s)
    assert zone(s, opt) == "p1:graveyard" and not s.state.cards[ring.id].tapped
    check(s)


def test_named_finds_lands(cards):
    s = build(cards, [], [])
    assert len(named(s, "Forest")) == 9

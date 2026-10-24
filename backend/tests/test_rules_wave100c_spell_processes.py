"""Wave 100C: earthbend riders, repeated processes, a win condition and cast-zone riders of instants and sorceries
(app/rules/static_spell100c.py), real Oracle text (tests/fixtures/wave100c_static_spells_cards.json; CR 2026-09-25). Every scenario
checks the replay and a save and a load.

* 603.12: "Earthbend 2. When you do, …": a reflexive ability, its targets chosen as it triggers; "that land's power": after its counters.
* 701.21a: "If they can't": nothing was sacrificed; "repeat this process": the same steps for each kind, in order (608.2c).
* 305.6 / 105.1: one permanent may give several basic land types or colors.
* 702.143: a foretold card is cast from exile; "for each opponent, choose …": the caster chooses (608.2d).
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

PROMOTED = ["Earth Rumble", "Earthshape", "Invoke Despair", "Coalition Victory", "Ultimate Magic: Meteor", "Imposing Grandeur"]


@pytest.fixture()
def cards(settings):
    yield from open_repo(settings)


@pytest.mark.parametrize("name", PROMOTED)
def test_every_card_is_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def test_earth_rumble_earthbends_then_your_creature_fights_theirs(cards):
    s = build(cards, ["Earth Rumble", "Grizzly Bears"], ["Llanowar Elves"])
    forest, bear, elves = move(s, named(s, "Forest")[0], "battlefield"), put_on(s, "Grizzly Bears"), put_on(s, "Llanowar Elves", "p2")
    cast(s, "Earth Rumble", targets=[forest.id], prefer=[bear.id, elves.id], G=1, C=3)
    assert pt_of(s, forest) == (2, 2) and zone(s, elves) == "p2:graveyard" and s.state.cards[bear.id].damage == 1
    check(s)


def test_earthshape_protects_creatures_up_to_the_lands_power_and_you(cards):
    """Earthshape: the Forest becomes 3/3; Grizzly Bears (2) and the land itself gain hexproof and indestructible, Hulking Cyclops (5) not;
    Alice gains hexproof (Bob's Lightning Bolt can't target her)."""
    s = build(cards, ["Earthshape", "Grizzly Bears", "Hulking Cyclops"], ["Lightning Bolt"])
    forest, bear, cyclops = move(s, named(s, "Forest")[0], "battlefield"), put_on(s, "Grizzly Bears"), put_on(s, "Hulking Cyclops")
    cast(s, "Earthshape", targets=[forest.id], W=1, C=2)
    assert {"hexproof", "indestructible"} <= chars(s, bear).keywords and {"hexproof", "indestructible"} <= chars(s, forest).keywords
    assert not {"hexproof", "indestructible"} & chars(s, cyclops).keywords
    act(s, "p1", type="pass_priority")
    with pytest.raises(ActionError):
        start_cast(s, "Lightning Bolt", "p2", targets=["p1"], R=1)
    check(s)


def test_invoke_despair_each_kind_sacrificed_or_two_life_and_a_card(cards):
    """Bob has a creature and Liliana, no enchantment: he sacrifices both; for the enchantment he loses 2 and Alice draws once."""
    s = build(cards, ["Invoke Despair"], ["Grizzly Bears", "Liliana of the Veil"])
    bear, lili = put_on(s, "Grizzly Bears", "p2"), walker(s, "Liliana of the Veil", "p2")
    move(s, one(s, "Invoke Despair"), "hand")
    library = len(s.state.zones["p1:library"])
    cast(s, "Invoke Despair", targets=["p2"], B=4, C=1)
    assert zone(s, bear) == "p2:graveyard" and zone(s, lili) == "p2:graveyard"
    assert life(s, "p2") == 38 and len(s.state.zones["p1:library"]) == library - 1
    check(s)


@pytest.mark.parametrize("complete", [True, False])
def test_coalition_victory_needs_every_basic_land_type_and_every_color(cards, complete):
    """Sliver Queen gives all five colors; Forest, Island, Mountain, Plains, and Urborg (each land is a Swamp too). Without the Plains: no win."""
    s = build(cards, ["Coalition Victory", "Sliver Queen", "Urborg, Tomb of Yawgmoth", "Plains", "Mountain", "Island"], [])
    for name in ("Sliver Queen", "Urborg, Tomb of Yawgmoth", "Mountain", "Island", *(("Plains",) if complete else ())):
        put_on(s, name)
    move(s, named(s, "Forest")[0], "battlefield")
    cast(s, "Coalition Victory", W=1, U=1, B=1, R=1, G=1, C=3)
    assert (s.state.rules.winner == "p1") is complete
    check(s)


def test_ultimate_magic_meteor_destroys_a_chosen_artifact_or_land_only_when_cast_from_exile(cards):
    """Ultimate Magic: Meteor foretold on turn 1, cast from exile on turn 3: 7 damage to each creature, then Alice chooses Bob's Sol Ring."""
    s = build(cards, ["Ultimate Magic: Meteor", "Grizzly Bears"], ["Sol Ring", "Grizzly Bears"])
    bear, theirs, ring = put_on(s, "Grizzly Bears"), put_on(s, "Grizzly Bears", "p2"), put_on(s, "Sol Ring", "p2")
    meteor = move(s, one(s, "Ultimate Magic: Meteor"), "hand")
    act(s, "p1", type="add_mana", player="p1", mana={"C": 2})
    act(s, "p1", type="activate_ability", card_id=meteor.id, ability=1)  # (the foretell special action, 702.143b)
    assert zone(s, meteor) == "p1:foretell"
    to_phase(s, "main1", turn=3)
    act(s, "p1", type="add_mana", player="p1", mana={"R": 1, "C": 5})
    act(s, "p1", type="cast_spell", card_id=meteor.id, targets=[])
    settle(s, prefer=[ring.id])
    assert zone(s, bear) == "p1:graveyard" and zone(s, theirs) == "p2:graveyard" and zone(s, ring) == "p2:graveyard"
    check(s)


def test_ultimate_magic_meteor_cast_from_hand_destroys_nothing_else(cards):
    s = build(cards, ["Ultimate Magic: Meteor"], ["Sol Ring"])
    ring = put_on(s, "Sol Ring", "p2")
    cast(s, "Ultimate Magic: Meteor", R=1, C=5)
    assert zone(s, ring) == "p2:battlefield"
    check(s)


def test_imposing_grandeur_each_player_who_agrees_draws_their_commanders_mana_value(cards):
    """Alice (Krenko, mana value 4, in the command zone) agrees: she discards her hand and draws four; Bob declines and keeps his hand."""
    s = build(cards, ["Imposing Grandeur", "Opt"], ["Opt"])
    opt, bobs = move(s, one(s, "Opt"), "hand"), move(s, one(s, "Opt", "p2"), "hand")
    move(s, one(s, "Imposing Grandeur"), "hand")
    bob_hand = len(s.state.zones["p2:hand"])
    start_cast(s, "Imposing Grandeur", R=1, C=4)
    for _ in range(20):
        d = s.state.rules.decision
        if d is not None:
            yes = [o.id for o in d.options if o.id in ("yes", "accept", "do")] or [d.options[0].id]
            no = [o.id for o in d.options if o.id in ("no", "decline", "skip")] or [d.options[-1].id]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=yes if d.player == "p1" else no)
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    assert zone(s, opt) == "p1:graveyard" and len(s.state.zones["p1:hand"]) == 4
    assert zone(s, bobs) == "p2:hand" and len(s.state.zones["p2:hand"]) == bob_hand
    check(s)

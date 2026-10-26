"""Wave 110K: single-card wordings, real Oracle text (tests/fixtures/wave110k_cards.json). Every scenario checks the replay and a save and a load.

* 608.2d, 800.4: Library of Lat-Nam's mode is chosen on resolution by an opponent (the caster picks which one with several): three cards at the
  next turn's upkeep, or a tutor.
* 111.1, 303.7, 608.2c: Twisted Sewer-Witch makes a Rat, then one Wicked Role for each Rat its controller has, each on its own Rat.
* 608.2d, 118.9, 702.145: Transforming Flourish destroys a permanent you don't control; only if it was destroyed does its controller exile until a nonland
  card and may cast it free.
* 702.26a, 702.26b: Teferi, Timeless Voyager's -8 phases out the opponent's creatures; they can't phase in until the end of Teferi's controller's next turn
  (so not in the untap step before it, nor in it), then phase in at their controller's next untap step.
* 702.96a, 205.4: Break the Ice destroys a land that is snow or could produce {C} (either one), one target or, overloaded, each such land.
* 701.19c, 614.8: Bone Shaman's granted ability makes a creature it dealt damage to this turn unable to be regenerated, so a regeneration shield
  doesn't save it; without the ability the shield does.
* 113.6m: Skyblade's Boon returns itself to its owner's hand from the battlefield (the Aura leaves its creature) or from its owner's graveyard, and from nowhere else.
* 602.2b, 118.3: Bullseye, Death Dealer's activation cost is a choice announced with the activation: sacrifice an artifact or discard a nonland card.
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.wave9c_kit import build, life
from tests.wave47b_kit import build3
from tests.wave110k_kit import (  # noqa: F401
    EXTRA,
    activate,
    card_db,
    cast_on,
    ch,
    check,
    full,
    hand_new,
    mana,
    now,
    put_new,
    refused,
    settle,
    to_hand,
    to_phase,
)


def test_bullseye_is_full():
    assert full("Bullseye, Death Dealer")


def _ready(cards):
    """Bullseye in play (its enter trigger declined), a Sol Ring and a Grizzly Bears (a nonland card) as the cost's two sides."""
    s = build(cards, ["Bullseye, Death Dealer", "Sol Ring", "Grizzly Bears"])
    bull = put_new(s, "Bullseye, Death Dealer")
    d = s.state.rules.decision
    if d is not None:
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[])
    settle(s)
    s.state.rules.controlled_since[bull.id].turn = 0
    return s, bull, put_new(s, "Sol Ring"), hand_new(s, "Grizzly Bears")


@pytest.mark.parametrize(("side", "zone_of_paid"), [(0, "ring"), (1, "bears")])
def test_bullseye_activation_cost_is_either_side(cards, side, zone_of_paid):
    s, bull, ring, bears = _ready(cards)
    mana(s, C=3)
    before = life(s, "p2")
    act(s, "p1", type="activate_ability", card_id=bull.id, ability=1, targets=["p2"],
        cost_choices=[{"component": 20, "cards": [f"either:{side}"]}])
    settle(s)
    assert life(s, "p2") == before - 2
    assert now(s, bull).tapped
    paid = {"ring": ring, "bears": bears}[zone_of_paid]
    kept = {"ring": bears, "bears": ring}[zone_of_paid]
    assert now(s, paid).zone.endswith(("graveyard",)) and not now(s, kept).zone.endswith("graveyard")
    check(s)


def test_bullseye_cannot_activate_without_either_side(cards):
    s, bull, ring, bears = _ready(cards)
    act(s, "p1", type="move", card_ids=[ring.id, bears.id], to={"zone": "exile"})
    mana(s, C=3)
    refused(s, "activation cost", bull, "{3}", targets=["p2"])


def test_library_of_lat_nam_is_full():
    assert full("Library of Lat-Nam")


def _hand_size(s, pid="p1"):
    return len(s.state.zones.get(f"{pid}:hand", []))


@pytest.mark.parametrize("pick", ["0", "1"])
def test_library_of_lat_nam_opponent_chooses_the_mode(cards, pick):
    s = build(cards, ["Library of Lat-Nam", "Sol Ring"])
    c = hand_new(s, "Library of Lat-Nam")
    mana(s, U=1, C=4)
    before = _hand_size(s)
    act(s, "p1", type="cast_spell", card_id=c.id)
    while s.state.zones.get("stack") and s.state.rules.decision is None:
        act(s, s.state.rules.priority, type="pass_priority")
    d = s.state.rules.decision
    assert d is not None and d.player == "p2" and [o.id for o in d.options] == ["0", "1"]
    act(s, "p2", type="choose", decision_id=d.id, option_ids=[pick])
    settle(s)
    if pick == "1":
        # a tutor: the controller finds a card; the hand lost the sorcery and gained that card
        d = s.state.rules.decision
        if d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[next(o.id for o in d.options)])
            settle(s)
        assert _hand_size(s) == before
    else:
        assert _hand_size(s) == before - 1
        to_phase(s, "upkeep", turn=2)  # the next turn (Bob's), not Alice's next: 603.7 delayed trigger, once
        settle(s)
        assert _hand_size(s) == before - 1 + 3
        to_phase(s, "main1", turn=3)  # only Alice's own draw step adds a card: the delayed trigger fired once
        assert _hand_size(s) == before - 1 + 3 + 1
    check(s)


def test_library_of_lat_nam_controller_names_which_opponent_chooses(cards):
    s = build3(cards, ["Library of Lat-Nam"])
    c = to_hand(s, "Library of Lat-Nam")
    mana(s, U=1, C=4)
    act(s, "p1", type="cast_spell", card_id=c.id)
    while s.state.zones.get("stack") and s.state.rules.decision is None:
        act(s, s.state.rules.priority, type="pass_priority")
    d = s.state.rules.decision
    assert d is not None and d.player == "p1" and sorted(o.id for o in d.options) == ["p2", "p3"]
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["p3"])
    d = s.state.rules.decision
    assert d is not None and d.player == "p3" and [o.id for o in d.options] == ["0", "1"]
    act(s, "p3", type="choose", decision_id=d.id, option_ids=["1"])
    settle(s)
    check(s)


def test_twisted_sewer_witch_is_full():
    assert full("Twisted Sewer-Witch")


def _roles(s):
    return [c for c in s.state.cards.values() if c.name == "Wicked" and c.zone.endswith(":battlefield")]


def test_twisted_sewer_witch_gives_each_rat_a_wicked_role(cards):
    s = build(cards, ["Twisted Sewer-Witch"])
    cast_on(s, "Twisted Sewer-Witch")
    rats = [c for c in s.state.cards.values() if c.name == "Rat" and c.zone.endswith(":battlefield")]
    assert len(rats) == 1 and [r.attached_to for r in _roles(s)] == [rats[0].id]
    assert int(ch(s, rats[0]).pt[0]) == 2  # 1/1 with Wicked's +1/+1
    check(s)


def test_second_witch_counts_the_rat_already_there_and_each_keeps_one_role(cards):
    s = build(cards, ["Twisted Sewer-Witch", "Twisted Sewer-Witch"])
    cast_on(s, "Twisted Sewer-Witch")
    life_before = life(s, "p2")
    cast_on(s, "Twisted Sewer-Witch")
    rats = [c for c in s.state.cards.values() if c.name == "Rat" and c.zone.endswith(":battlefield")]
    assert len(rats) == 2
    # 303.7 / 111.10: a Role replaces another Role you control on the same permanent; the old Role goes to the graveyard and its owner's opponents lose 1 life
    assert sorted(r.attached_to for r in _roles(s)) == sorted(r.id for r in rats)
    assert life(s, "p2") == life_before - 1
    check(s)


def test_transforming_flourish_is_full():
    assert full("Transforming Flourish")


def _flourish(cards, target_name, foe_top):
    from tests.wave110b_kit import top

    s = build(cards, ["Transforming Flourish"], [target_name, *dict.fromkeys(foe_top)])
    victim = put_new(s, target_name, "p2")
    for name in foe_top:
        top(s, name, "p2")
    cast = to_hand(s, "Transforming Flourish")
    mana(s, R=1, C=2)  # {2}{R}
    act(s, "p1", type="cast_spell", card_id=cast.id, targets=[victim.id])
    return s, victim


def _finish(s):
    for _ in range(40):
        d = s.state.rules.decision
        if d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)] if d.kind != "choose_one" else [d.options[0].id])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return
    raise AssertionError("never settled")


def test_flourish_makes_the_controller_exile_to_a_nonland_card_and_cast_it_free(cards):
    s, victim = _flourish(cards, "Grizzly Bears", ["Elvish Visionary", "Island"])  # listed bottom-up: an Island is on top of the Visionary
    _finish(s)
    assert now(s, victim).zone.endswith(":graveyard")
    assert sorted(c.name for c in s.state.cards.values() if c.zone == "p2:exile") == ["Island"]
    knight = [c for c in s.state.cards.values() if c.name == "Elvish Visionary" and c.zone.endswith(":battlefield")]
    assert len(knight) == 1 and knight[0].controller == "p2"
    check(s)


def test_flourish_does_nothing_more_when_the_permanent_survives(cards):
    s, victim = _flourish(cards, "Darksteel Colossus", ["Elvish Visionary"])
    _finish(s)
    assert now(s, victim).zone.endswith(":battlefield")
    assert not [c for c in s.state.cards.values() if c.zone == "p2:exile"]
    check(s)


def test_teferi_is_full():
    assert full("Teferi, Timeless Voyager")


def test_teferi_ultimate_keeps_the_creatures_out_until_after_your_next_turn(cards):
    s = build(cards, ["Teferi, Timeless Voyager", "Grizzly Bears"], ["Grizzly Bears", "Elvish Visionary"])
    teferi, mine = put_new(s, "Teferi, Timeless Voyager"), put_new(s, "Grizzly Bears")
    theirs = [put_new(s, n, "p2") for n in ("Grizzly Bears", "Elvish Visionary")]
    d = s.state.rules.decision
    while d is not None:  # (the Visionary's draw trigger)
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        d = s.state.rules.decision
    settle(s)
    act(s, "p1", type="counter", card_ids=[teferi.id], kind="loyalty", delta=8 - s.state.cards[teferi.id].counters.get("loyalty", 0))
    activate(s, teferi, "\u22128", targets=["p2"])
    assert all(now(s, c).zone == "p2:phased" for c in theirs) and now(s, mine).zone == "p1:battlefield"
    for turn in (2, 3):  # Bob's untap step, then all of Alice's turn: still out
        to_phase(s, "main1", turn=turn)
        assert all(now(s, c).zone == "p2:phased" for c in theirs), turn
    to_phase(s, "main1", turn=4)  # Bob's next untap step: back
    assert all(now(s, c).zone == "p2:battlefield" for c in theirs)
    check(s)


def test_break_the_ice_is_full():
    assert full("Break the Ice")


def _ice_table(cards):
    s = build(cards, ["Break the Ice"], ["Shivan Reef", "Snow-Covered Island", "Command Tower"])
    lands = {n: put_new(s, n, "p2") for n in ("Shivan Reef", "Snow-Covered Island", "Command Tower", "Island")}
    return s, lands


@pytest.mark.parametrize(("target", "destroyed"), [("Shivan Reef", True), ("Snow-Covered Island", True), ("Command Tower", False), ("Island", False)])
def test_break_the_ice_targets_a_snow_land_or_a_land_that_could_produce_colorless(cards, target, destroyed):
    s, lands = _ice_table(cards)
    c = to_hand(s, "Break the Ice")
    mana(s, B=2)
    if destroyed:
        act(s, "p1", type="cast_spell", card_id=c.id, targets=[lands[target].id])
        settle(s)
        assert now(s, lands[target]).zone.endswith(":graveyard")
    else:
        with pytest.raises(ActionError):
            act(s, "p1", type="cast_spell", card_id=c.id, targets=[lands[target].id])
    check(s)


def test_overloaded_break_the_ice_destroys_each_such_land_and_no_other(cards):
    s, lands = _ice_table(cards)
    c = to_hand(s, "Break the Ice")
    mana(s, B=2, C=4)
    act(s, "p1", type="cast_spell", card_id=c.id, alt_cost=f"{c.id}:1")
    settle(s)
    assert {n: now(s, land).zone.endswith(":graveyard") for n, land in lands.items()} == {
        "Shivan Reef": True, "Snow-Covered Island": True, "Command Tower": False, "Island": False}
    check(s)


def test_bone_shaman_is_full():
    assert full("Bone Shaman")


@pytest.mark.parametrize("shaman_ability", [False, True])
def test_bone_shaman_stops_a_creature_it_damaged_from_regenerating(cards, shaman_ability):
    from tests.wave110b_kit import through_combat
    from tests.wave110k_kit import ability

    s = build(cards, ["Drudge Skeletons"], ["Bone Shaman"])
    skeletons, shaman = put_new(s, "Drudge Skeletons"), put_new(s, "Bone Shaman", "p2")
    s.state.rules.controlled_since[skeletons.id].turn = 0  # (no summoning sickness: the passes below would otherwise skip combat)
    mana(s, B=1)
    if shaman_ability:
        mana(s, "p2", B=1)
    # (after an activation its controller passes on their own, so Bob has priority with it on the stack)
    act(s, "p1", type="activate_ability", card_id=skeletons.id, ability=ability(s, skeletons, "{B}"))  # a regeneration shield, until end of turn
    if shaman_ability:  # Bob answers: the shaman's creatures-it-damaged rule, also until end of turn
        act(s, "p2", type="activate_ability", card_id=shaman.id, ability=ability(s, shaman, "{B}"))
    settle(s)
    if s.state.rules.decision is None:
        act(s, "p1", type="pass_priority")
    assert s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_attackers"
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": skeletons.id, "target": "p2"}])
    through_combat(s, [(shaman, skeletons)])
    assert now(s, skeletons).zone == ("p1:graveyard" if shaman_ability else "p1:battlefield")
    check(s)


def test_skyblade_boon_is_full():
    assert full("Skyblade's Boon")


def test_skyblade_boon_returns_from_the_battlefield(cards):
    s = build(cards, ["Skyblade's Boon", "Grizzly Bears"])
    bears = put_new(s, "Grizzly Bears")
    boon = cast_on(s, "Skyblade's Boon", bears)
    assert now(s, boon).zone == "p1:battlefield" and "flying" in ch(s, bears).keywords
    mana(s, W=1, C=2)
    activate(s, boon, "{2}{W}")
    assert now(s, boon).zone == "p1:hand" and "flying" not in ch(s, bears).keywords
    check(s)


def test_skyblade_boon_returns_from_the_graveyard(cards):
    s = build(cards, ["Skyblade's Boon"])
    boon = move_to_graveyard(s, "Skyblade's Boon")
    mana(s, W=1, C=2)
    activate(s, boon, "{2}{W}")
    assert now(s, boon).zone == "p1:hand"
    check(s)


@pytest.mark.parametrize("zone", ["hand", "exile", "library"])
def test_skyblade_boon_does_nothing_from_other_zones(cards, zone):
    s = build(cards, ["Skyblade's Boon"])
    boon = to_hand(s, "Skyblade's Boon")
    if zone != "hand":
        act(s, "p1", type="move", card_ids=[boon.id], to={"zone": zone})
    mana(s, W=1, C=2)
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=boon.id, ability=2)
    check(s)


def move_to_graveyard(s, name, pid="p1"):
    c = to_hand(s, name, pid)
    act(s, pid, type="move", card_ids=[c.id], to={"zone": "graveyard"})
    return c


# -- Swinging Ship (Unfinity 231a, lit 2 and 6; the Attraction's own printing sets what lights it) --
SHIP = card("Swinging Ship", set_code="unf", number="231a", mana_cost="", cmc=0, type_line="Artifact — Attraction",
            oracle_text="Visit — After the first combat phase this turn, there's an additional combat phase. At the beginning of that combat, untap all "
                        "creatures that attacked this turn.", colors=[], color_identity=[], keywords=[])


@pytest.fixture()
def ship_cards(settings):
    from app.cards.images import ImageStore
    from app.cards.importer import build_database
    from app.cards.repository import CardRepository

    settings.ensure_dirs()
    build_database([*fixture_cards(), SHIP], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def test_swinging_ship_is_full(ship_cards):
    from app.rules import coverage

    assert coverage.of_card_data(ship_cards.resolve("Swinging Ship")).level == "FULL"


def _ship_turn(cards, monkeypatch, die):
    """Alice's turn 3 with the Ship and a 2/2 attacker: the visit roll comes up ``die``; stops at the first declaration of attackers (or main 1 when none)."""
    from tests.test_rules_conditionals import creature
    from tests.test_rules_wave12a_counters_keywords import rolls
    from tests.test_rules_wave100l_attractions import game
    from tests.wave9c_kit import put

    rolls(monkeypatch, die)
    s = game(cards, [], ["Swinging Ship"])
    put(s, "Swinging Ship")
    bear = creature(s, "p1", "Attacker", "2/2")
    for _ in range(400):
        d = s.state.rules.decision
        if s.state.turn.number == 3 and d is not None and d.kind == "declare_attackers":
            return s, bear
        if d is not None and d.kind in ("declare_attackers", "declare_blockers"):
            act(s, d.player, type=d.kind, **({"attackers": []} if d.kind == "declare_attackers" else {"blocks": []}))
        elif d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("never reached Alice's attack")


def _attack_all_combats(s, bear):
    """Alice attacks with ``bear`` in every combat phase she gets; returns how many combats it attacked in."""
    attacks = 0
    for _ in range(200):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_attackers" and d.player == "p1":
            alive = now(s, bear).zone == "p1:battlefield" and not now(s, bear).tapped
            act(s, "p1", type="declare_attackers", attackers=[{"card_id": bear.id, "target": "p2"}] if alive else [])
            attacks += alive
        elif d is not None and d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
        elif d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        elif s.state.turn.number == 3 and s.state.turn.phase == "main2" and not s.state.zones.get("stack"):
            break
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    return attacks


@pytest.mark.parametrize(("die", "attacks"), [(6, 2), (2, 2), (5, 1)])
def test_swinging_ship_adds_a_combat_in_which_the_attackers_untap(ship_cards, monkeypatch, die, attacks):
    s, bear = _ship_turn(ship_cards, monkeypatch, die)
    life_before = life(s, "p2")
    assert _attack_all_combats(s, bear) == attacks
    assert life(s, "p2") == life_before - 2 * attacks
    check(s)

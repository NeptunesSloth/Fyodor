"""Wave 110I (second session): real Oracle text; every scenario checks the replay and a save and a load.

* Curse of Conformity: base P/T 3/3 (613.4b) and no creature types (205.1a), nonlegendary only.
* Puppet Master: the payment is offered only once the creature card is back in hand; the Aura comes back from the graveyard (603.10a, 400.7).
* Rhuk, Hexgold Nabber: Equipment attached to the dying creature as it last was moves to Rhuk (701.3a, 603.10a); optional.
* The Moment: "phases out until The Moment leaves the battlefield" (610.3, 702.26a), untapped first, not tapped as it returns.
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import coverage
from app.rules.plan import Plan
from tests.fixtures.cards import card
from tests.game_helpers import act, mana_pool
from tests.test_rules_wave12a_counters_keywords import real
from tests.test_rules_wave34b_activated import stops, to_phase
from tests.wave9c_kit import card_named, life
from tests.wave110a_kit import next_turn
from tests.wave110c_kit import answer, build, cast, check, make_db, mana, put, zone

EXTRA = [
    real("The Moment", "{1}{W}{U}", 3, "Legendary Artifact",
         "At the beginning of your upkeep, put a time counter on The Moment.\n{2}, {T}: Untap target creature you control. It phases out until The Moment leaves the battlefield.\n{3}, {T}: Destroy each nonland permanent with mana value less than or equal to the number of time counters on The Moment. Then sacrifice The Moment. Activate only as a sorcery.",
         None, "WU"),
    real("Curse of Conformity", "{3}{U}", 4, "Enchantment — Aura Curse",
         "Enchant player\nNonlegendary creatures enchanted player controls have base power and toughness 3/3 and lose all creature types.", None, "U"),
    real("Probe Legend", "{1}", 1, "Legendary Creature — Human Soldier", "", ("1", "1"), ""),
    real("Puppet Master", "{U}{U}{U}", 3, "Enchantment — Aura",
         "Enchant creature\nWhen enchanted creature dies, return that card to its owner's hand. If that card is returned to its owner's hand this way, you may pay {U}{U}{U}. If you do, return this card to its owner's hand.",
         None, "U"),
    real("Lightning Bolt", "{R}", 1, "Instant", "Lightning Bolt deals 3 damage to any target.", None, "R"),
    real("Rhuk, Hexgold Nabber", "{2}{R}", 3, "Legendary Creature — Goblin Rebel",
         "Trample, haste\nWhenever an equipped creature you control other than Rhuk attacks or dies, you may attach all Equipment attached to that creature to Rhuk.",
         ("2", "2"), "R"),
    real("Soldier Maker", "{W}", 1, "Sorcery", "Create a 1/1 white Soldier creature token.", None, "W"),
    real("Errant Minion", "{2}{U}", 3, "Enchantment — Aura",
         "Enchant creature\nAt the beginning of the upkeep of enchanted creature's controller, that player may pay any amount of mana. This Aura deals 2 damage to that player. Prevent X of that damage, where X is the amount of mana that player paid this way.",
         None, "U"),
    real("Power Leak", "{1}{U}", 2, "Enchantment — Aura",
         "Enchant enchantment\nAt the beginning of the upkeep of enchanted enchantment's controller, that player may pay any amount of mana. This Aura deals 2 damage to that player. Prevent X of that damage, where X is the amount of mana that player paid this way.",
         None, "U"),
    real("Probe Rune", "{1}", 1, "Enchantment", "", None, ""),
    real("Glimpse the Cosmos", "{2}{U}", 3, "Sorcery",
         "Look at the top three cards of your library. Put one of them into your hand and the rest on the bottom of your library in any order.\nAs long as you control a Giant, you may cast this card from your graveyard by paying {U} rather than paying its mana cost. If you cast this card this way and it would be put into your graveyard, exile it instead.",
         None, "U"),
    real("Probe Giant", "{4}{R}", 5, "Creature — Giant", "", ("4", "3"), "R"),
    real("Probe Revenant", "{2}{U}", 3, "Enchantment — Aura",
         "Enchant creature\nAs long as you control a Giant, you may cast this card from your graveyard by paying {U} rather than paying its mana cost. If you cast this card this way and it would be put into your graveyard, exile it instead.",
         None, "U"),
    real("Traveler's Cloak", "{2}{U}", 3, "Enchantment — Aura",
         "Enchant creature\nAs this Aura enters, choose a land type.\nWhen this Aura enters, draw a card.\nEnchanted creature has landwalk of the chosen type. (It can't be blocked as long as defending player controls a land of that type.)",
         None, "U"),
    real("Bioessence Hydra", "{2}{G}{G}", 4, "Creature — Hydra",
         "Trample\nWhenever one or more loyalty counters are put on planeswalkers you control, put that many +1/+1 counters on this creature.",
         ("1", "1"), "G"),
    card("Probe Walker", set_code="tst", number="110I-W", mana_cost="{2}", cmc=2.0, type_line="Legendary Planeswalker — Probe", loyalty="3",
         oracle_text="+1: You gain 1 life.\n\u22122: You gain 2 life.", colors=[], color_identity=[], keywords=[]),
    real("Naturalize", "{1}{G}", 2, "Instant", "Destroy target artifact or enchantment.", None, "G"),
]
NAMES = ["The Moment", "Curse of Conformity", "Puppet Master", "Rhuk, Hexgold Nabber", "Errant Minion", "Power Leak", "Glimpse the Cosmos", "Traveler's Cloak", "Bioessence Hydra"]


@pytest.fixture()
def card_db(settings):
    return make_db(settings, EXTRA)


@pytest.mark.parametrize("name", NAMES)
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def test_the_moment_phases_out_untapped_until_it_leaves(cards):
    s = build(cards, ["The Moment", "Naturalize", "Grizzly Bears"], [])
    moment, bear = put(s, "The Moment"), put(s, "Grizzly Bears")
    act(s, "p1", type="tap", card_ids=[bear.id])
    mana(s, C=2)
    act(s, "p1", type="activate_ability", card_id=moment.id, ability=1, targets=[bear.id])
    answer(s)
    assert zone(s, bear) == "p1:phased" and not s.state.cards[bear.id].tapped
    check(s)
    mana(s, G=1, C=1)
    cast(s, "Naturalize", [moment.id])
    answer(s)
    assert zone(s, bear) == "p1:battlefield" and not s.state.cards[bear.id].tapped
    check(s)


def test_curse_of_conformity_makes_nonlegendary_creatures_3_3_without_types(cards):
    s = build(cards, ["Curse of Conformity"], ["Grizzly Bears", "Probe Legend"])
    bear, legend = put(s, "Grizzly Bears", "p2"), put(s, "Probe Legend", "p2")
    mana(s, U=1, C=3)
    cast(s, "Curse of Conformity", ["p2"])
    answer(s)
    plan = Plan(s.state, "p1", s.cards, None)
    assert (plan.ch(s.state.cards[bear.id]).pt, "Bear" in plan.ch(s.state.cards[bear.id]).subtypes) == ((3, 3), False)
    assert (plan.ch(s.state.cards[legend.id]).pt, "Human" in plan.ch(s.state.cards[legend.id]).subtypes) == ((1, 1), True)
    check(s)


@pytest.mark.parametrize("pay", [True, False])
def test_puppet_master_returns_the_creature_and_itself_if_paid(cards, pay):
    s = build(cards, ["Puppet Master", "Lightning Bolt"], ["Grizzly Bears"])
    bear = put(s, "Grizzly Bears", "p2")
    mana(s, U=3)
    master = cast(s, "Puppet Master", [bear.id])
    answer(s)
    assert zone(s, master) == "p1:battlefield"
    mana(s, R=1, U=3 if pay else 0)
    cast(s, "Lightning Bolt", [bear.id])
    answer(s, "pay" if pay else "decline")
    assert zone(s, bear) == "p2:hand"
    assert zone(s, master) == ("p1:hand" if pay else "p1:graveyard")
    check(s)


@pytest.mark.parametrize("take", [True, False])
def test_rhuk_takes_the_equipment_of_a_dying_equipped_creature(cards, take):
    s = build(cards, ["Rhuk, Hexgold Nabber", "Grizzly Bears", "Bonesplitter", "Lightning Bolt"], [])
    rhuk, bear, gear = put(s, "Rhuk, Hexgold Nabber"), put(s, "Grizzly Bears"), put(s, "Bonesplitter")
    act(s, "p1", type="attach", card_ids=[gear.id], to=bear.id)
    mana(s, R=1)
    cast(s, "Lightning Bolt", [bear.id])
    answer(s, "yes" if take else "no")
    assert zone(s, bear) == "p1:graveyard"
    assert s.state.cards[gear.id].attached_to == (rhuk.id if take else None)
    check(s)


def test_puppet_master_on_a_token_offers_no_payment(cards):
    """A token ceases to exist in the graveyard (111.7, 704.5d): nothing returns to hand, so no payment is offered and the Aura stays."""
    s = build(cards, ["Puppet Master", "Soldier Maker", "Lightning Bolt"], [])
    mana(s, W=1)
    cast(s, "Soldier Maker")
    answer(s)
    tok = next(c for c in s.state.cards.values() if c.zone == "p1:battlefield" and c.name != "Puppet Master")
    mana(s, U=3)
    master = cast(s, "Puppet Master", [tok.id])
    answer(s)
    mana(s, R=1, U=3)
    cast(s, "Lightning Bolt", [tok.id])
    answer(s, "pay")  # (no payment decision exists: the answer is ignored)
    assert s.state.rules.decision is None
    assert zone(s, master) == "p1:graveyard" and mana_pool(s).get("U", 0) == 3
    check(s)


def test_rhuk_takes_the_equipment_of_an_attacking_equipped_creature(cards):
    s = build(cards, ["Rhuk, Hexgold Nabber", "Grizzly Bears", "Bonesplitter"], [])
    rhuk, bear, gear = put(s, "Rhuk, Hexgold Nabber"), put(s, "Grizzly Bears"), put(s, "Bonesplitter")
    act(s, "p1", type="attach", card_ids=[gear.id], to=bear.id)
    next_turn(s)
    stops(s)
    to_phase(s, "declare_attackers")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": bear.id, "target": "p2"}])
    answer(s, "yes")
    assert s.state.cards[gear.id].attached_to == rhuk.id and s.state.cards[bear.id].is_attacking
    check(s)


@pytest.mark.parametrize("paid", [0, 1, 2, 3])
@pytest.mark.parametrize("aura, host", [("Errant Minion", "Grizzly Bears"), ("Power Leak", "Probe Rune")])
def test_errant_minion_and_power_leak_deal_2_minus_the_mana_paid(cards, aura, host, paid):
    """615.1 prevention of X of the 2 damage: 2 - X, never negative; the enchanted permanent's controller pays (118.3) and takes the damage."""
    s = build(cards, [aura], [host, "Forest", "Island", "Swamp"])
    target = put(s, host, "p2")
    for land in ("Forest", "Island", "Swamp"):
        put(s, land, "p2")
    mana(s, U=3)
    cast(s, aura, [target.id])
    answer(s)
    to_phase(s, "upkeep", turn=2)
    answer(s, f"x:{paid}" if paid else "decline")
    assert life(s, "p2") == 40 - max(0, 2 - paid) and life(s, "p1") == 40
    check(s)


def test_glimpse_the_cosmos_from_hand_takes_one_of_three(cards):
    s = build(cards, ["Glimpse the Cosmos", "Forest", "Island", "Swamp", "Mountain"], [])
    top = [c for c in s.state.zones["p1:library"][:3]]
    mana(s, U=1, C=2)
    cast(s, "Glimpse the Cosmos")
    answer(s)
    assert sum(s.state.cards[c].zone == "p1:hand" for c in top) == 1 and zone(s, card_named(s, "Glimpse the Cosmos")) == "p1:graveyard"
    check(s)


@pytest.mark.parametrize("giant", [True, False])
def test_glimpse_the_cosmos_from_graveyard_needs_a_giant_and_exiles(cards, giant):
    """614.1a: cast from the graveyard for {U} only while you control a Giant, then exiled instead of going to the graveyard."""
    from tests.wave110c_kit import offers

    s = build(cards, ["Glimpse the Cosmos", "Probe Giant", "Forest", "Island", "Swamp", "Mountain"], [])
    gl = put(s, "Glimpse the Cosmos")
    act(s, "p1", type="move", card_ids=[gl.id], to={"player": "p1", "zone": "graveyard"})
    if giant:
        put(s, "Probe Giant")
    assert bool(offers(s, gl)) is giant
    if giant:
        mana(s, U=1)
        act(s, "p1", type="cast_spell", card_id=gl.id, alt_cost=offers(s, gl)[0].key)
        answer(s)
        assert zone(s, gl) == "p1:exile"
        check(s)


def test_exile_instead_alternative_is_not_offered_for_a_permanent_spell(cards):
    from tests.wave110c_kit import offers

    s = build(cards, ["Probe Revenant", "Probe Giant"], [])
    aura = put(s, "Probe Revenant")
    act(s, "p1", type="move", card_ids=[aura.id], to={"player": "p1", "zone": "graveyard"})
    put(s, "Probe Giant")
    assert not offers(s, aura)


@pytest.mark.parametrize("land, blockable", [("Swamp", False), ("Forest", True)])
def test_travelers_cloak_gives_landwalk_of_the_chosen_land_type(cards, land, blockable):
    """702.14a: unblockable while the defending player controls a land of the chosen type; the Aura also draws a card as it enters."""
    s = build(cards, ["Traveler's Cloak", "Grizzly Bears", "Forest"], ["Grizzly Bears", land])
    bear, wall = put(s, "Grizzly Bears"), put(s, "Grizzly Bears", "p2")
    put(s, land, "p2")
    mana(s, U=1, C=2)
    hand = len([c for c in s.state.cards.values() if c.zone == "p1:hand"])
    cast(s, "Traveler's Cloak", [bear.id])
    d = s.state.rules.decision
    assert d is not None and any(o.label == "Swamp" or o.id == "Swamp" for o in d.options)
    answer(s, next(o.id for o in d.options if "Swamp" in (o.id, o.label)))
    assert len([c for c in s.state.cards.values() if c.zone == "p1:hand"]) == hand + 1  # (the Aura left the hand it was put in; one card drawn)
    next_turn(s)
    stops(s)
    to_phase(s, "declare_attackers")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": bear.id, "target": "p2"}])
    to_phase(s, "declare_blockers")
    block = {"type": "declare_blockers", "blocks": [{"blocker_id": wall.id, "attacker_id": bear.id}]}
    if blockable:
        act(s, "p2", **block)
    else:
        with pytest.raises(ActionError):
            act(s, "p2", **block)
    check(s)


def test_bioessence_hydra_grows_by_the_loyalty_counters_put_on_planeswalkers(cards):
    """122.6: entering with loyalty counters and a loyalty ability's cost both put counters on; removing them does not."""
    s = build(cards, ["Bioessence Hydra", "Probe Walker"], [])
    hydra = put(s, "Bioessence Hydra")
    mana(s, C=2)
    walker = cast(s, "Probe Walker")
    answer(s)
    counters = lambda: s.state.cards[hydra.id].counters.get("+1/+1", 0)  # noqa: E731
    assert counters() == 3
    act(s, "p1", type="activate_ability", card_id=walker.id, ability=0)
    answer(s)
    assert counters() == 4 and s.state.cards[walker.id].counters["loyalty"] == 4
    next_turn(s)
    act(s, "p1", type="activate_ability", card_id=walker.id, ability=1)
    answer(s)
    assert counters() == 4 and s.state.cards[walker.id].counters["loyalty"] == 2
    check(s)

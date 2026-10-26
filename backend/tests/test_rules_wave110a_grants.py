"""Wave 110A: spells gaining a keyword cost as they are cast (CR 2026-09-25), real Oracle text (tests/fixtures/wave110a_cards.json).

* Twins of Discord - "Each other colorless creature you control has bloodthirst 2." (702.54a: it enters with two additional +1/+1 counters if an
  opponent was dealt damage this turn).
* Umbra Mystic - "Auras attached to permanents you control have umbra armor." (702.89a: instead of being destroyed, remove all damage and
  destroy an Aura attached to it).
* Predatory Focus - "You may have creatures you control assign their combat damage this turn as though they weren't blocked." (510.1c: each
  blocked creature of the controller is asked; the permission lasts this turn).
* Ashling, the Limitless - "Elemental permanent spells you cast from your hand gain evoke {4} as you cast them." (702.74a: evoke is an
  alternative cost; 702.74a: the permanent is sacrificed when it enters; 601.2b: chosen as the spell is cast).
"""

# ruff: noqa: F403, F405
from __future__ import annotations

from app.game.errors import ActionError
from tests.wave110a_kit import *

ASHLING, AIR, TWINS, ORNI, BOLT = "Ashling, the Limitless", "Air Elemental", "Twins of Discord", "Ornithopter", "Lightning Bolt"


@pytest.fixture()
def cards(settings):
    yield from open_repo(settings)


test_full = full_test([ASHLING, TWINS, "Umbra Mystic", "Xenagos, the Reveler", "Obsidian Charmaw", "Predatory Focus", "Full Bore"])


def offers(s, name, zone="hand"):
    from app.rules import alt_costs
    from app.rules import characteristics as chars

    c = card_named(s, name)
    return c, [o for o in alt_costs.offers(s.state, "p1", c, chars.of(c, s.cards), s.cards) if o.tag == "evoke"]


def test_evoke_granted_to_elemental_in_hand_sacrifices_it_and_ashling_copies(cards):
    s = build(cards, [ASHLING, AIR, "Grizzly Bears"])
    put(s, ASHLING)
    air = to_hand(s, AIR)
    bears = to_hand(s, "Grizzly Bears")
    assert len(offers(s, AIR)[1]) == 1 and not offers(s, "Grizzly Bears")[1]  # only Elemental permanent spells
    mana(s, C=4)
    act(s, "p1", type="cast_spell", card_id=air.id, alt_cost=offers(s, AIR)[1][0].key)
    answer(s)
    assert s.state.cards[air.id].zone == "p1:graveyard" and s.state.cards[bears.id].zone == "p1:hand"
    assert sum(1 for c in s.state.cards.values() if c.name == AIR and c.zone == "p1:battlefield") == 1  # Ashling's token copy
    check(s)


def test_evoke_not_offered_from_other_zones(cards):
    s = build(cards, [ASHLING, AIR])
    put(s, ASHLING)
    to_graveyard(s, 1, AIR)
    assert not offers(s, AIR)[1]


@pytest.mark.parametrize(("bolt", "name", "counters"), [(True, ORNI, 2), (False, ORNI, 0), (True, "Grizzly Bears", 0)])
def test_bloodthirst_granted_to_other_colorless_creatures(cards, bolt, name, counters):
    s = build(cards, [TWINS, name, BOLT])
    put(s, TWINS)
    if bolt:
        mana(s, R=1)
        act(s, "p1", type="cast_spell", card_id=to_hand(s, BOLT).id, targets=["p2"])
        answer(s)
    mana(s, G=2)
    c = to_hand(s, name)
    act(s, "p1", type="cast_spell", card_id=c.id)
    answer(s)
    assert s.state.cards[c.id].counters.get("+1/+1", 0) == counters
    check(s)


@pytest.mark.parametrize("mystic", [True, False])
def test_umbra_armor_granted_to_auras_on_your_permanents(cards, mystic):
    s = build(cards, ["Umbra Mystic", "Grizzly Bears", "Holy Strength", "Murder"])
    if mystic:
        put(s, "Umbra Mystic")
    bears = put(s, "Grizzly Bears")
    mana(s, W=1)
    aura = to_hand(s, "Holy Strength")
    act(s, "p1", type="cast_spell", card_id=aura.id, targets=[bears.id])
    answer(s)
    mana(s, B=2, C=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Murder").id, targets=[bears.id])
    d = s.state.rules.decision
    if d is not None:
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[next(o.id for o in d.options if o.id.startswith("aura:"))])
    answer(s)
    assert (s.state.cards[bears.id].zone, s.state.cards[aura.id].zone) == (("p1:battlefield", "p1:graveyard") if mystic else ("p1:graveyard", "p1:graveyard"))
    check(s)


@pytest.mark.parametrize("take", [0, 2, 7])
def test_xenagos_exiles_seven_and_puts_any_number_of_creatures_and_lands(cards, take):
    """Xenagos, the Reveler -6: exile the top seven (701.13), then the controller puts any number of the creature/land ones onto the battlefield."""
    s = build(cards, ["Xenagos, the Reveler", "Grizzly Bears"])
    xen = put(s, "Xenagos, the Reveler")
    act(s, "p1", type="counter", card_ids=[xen.id], kind="loyalty", delta=6)
    act(s, "p1", type="activate_ability", card_id=xen.id, ability=2)
    d = s.state.rules.decision
    assert d is not None and d.min_choices == 0 and len(d.options) == 7
    pick = [o.id for o in d.options][:take]
    act(s, "p1", type="choose", decision_id=d.id, option_ids=pick)
    answer(s)
    assert sorted(c.id for c in s.state.cards.values() if c.zone == "p1:battlefield" and c.id != xen.id) == sorted(pick)
    assert sum(1 for c in s.state.cards.values() if c.zone == "p1:exile") == 7 - take
    check(s)


@pytest.mark.parametrize(("land", "total"), [("Wastes", 4), ("Island", 5)])
def test_obsidian_charmaw_costs_less_per_opponent_land_that_could_produce_colorless(cards, land, total):
    """Obsidian Charmaw: {1} less for each land your opponents control that could produce {C} (601.2f, 106.1)."""
    s = build(cards, ["Obsidian Charmaw"], theirs=[land])
    put(s, land, "p2")
    c = to_hand(s, "Obsidian Charmaw")
    mana(s, R=2, C=total - 2)
    act(s, "p1", type="cast_spell", card_id=c.id)
    answer(s)
    assert s.state.cards[c.id].zone == "p1:battlefield"
    check(s)
    t2 = build(cards, ["Obsidian Charmaw"], theirs=[land])
    put(t2, land, "p2")
    mana(t2, R=2, C=total - 3)
    with pytest.raises(ActionError):
        act(t2, "p1", type="cast_spell", card_id=to_hand(t2, "Obsidian Charmaw").id)


@pytest.mark.parametrize("cast_focus", [True, False])
def test_predatory_focus_blocked_creature_may_assign_damage_to_the_player(cards, cast_focus):
    s = build(cards, ["Predatory Focus", "Hill Giant"], ["Grizzly Bears"])
    giant = put(s, "Hill Giant")
    bears = put(s, "Grizzly Bears", "p2")
    next_turn(s)
    stops(s)
    if cast_focus:
        fund(s, "{3}{G}{G}")
        act(s, "p1", type="cast_spell", card_id=to_hand(s, "Predatory Focus").id)
        answer(s)
    to_phase(s, "declare_attackers")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": giant.id, "target": "p2"}])
    to_phase(s, "declare_blockers")
    act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": bears.id, "attacker_id": giant.id}])
    to_phase(s, "combat_damage")
    d = s.state.rules.decision
    assert (d is not None and d.kind == "confirm") == cast_focus
    if d is not None:
        act(s, d.player, type="choose", decision_id=d.id, option_ids=["yes"])
    answer(s)
    assert life(s, "p2") == (37 if cast_focus else 40)
    check(s)


@pytest.mark.parametrize("warp", [True, False])
def test_full_bore_grants_trample_and_haste_only_to_a_creature_cast_for_its_warp_cost(cards, warp):
    """Full Bore: "If that creature was cast for its warp cost" (702.185a), read from the record its spell left."""
    from app.rules import alt_costs
    from app.rules import characteristics as chars

    s = build(cards, ["Starwinder", "Full Bore"])
    star = to_hand(s, "Starwinder")
    key = next(o.key for o in alt_costs.offers(s.state, "p1", star, chars.of(star, s.cards), s.cards) if o.tag == "warp")
    fund(s, "{2}{U}{U}" if warp else "{5}{U}{U}")
    act(s, "p1", type="cast_spell", card_id=star.id, **({"alt_cost": key} if warp else {}))
    answer(s)
    fund(s, "{1}{R}")
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Full Bore").id, targets=[star.id])
    answer(s)
    assert {"trample", "haste"} <= ch(s, star).keywords if warp else not ({"trample", "haste"} & ch(s, star).keywords)
    check(s)

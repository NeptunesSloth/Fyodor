"""Wave 110A: spells gaining a keyword cost as they are cast (CR 2026-09-25), real Oracle text (tests/fixtures/wave110a_cards.json).

* Twins of Discord - "Each other colorless creature you control has bloodthirst 2." (702.54a: it enters with two additional +1/+1 counters if an
  opponent was dealt damage this turn).
* Umbra Mystic - "Auras attached to permanents you control have umbra armor." (702.89a: instead of being destroyed, remove all damage and
  destroy an Aura attached to it).
* Ashling, the Limitless - "Elemental permanent spells you cast from your hand gain evoke {4} as you cast them." (702.74a: evoke is an
  alternative cost; 702.74a: the permanent is sacrificed when it enters; 601.2b: chosen as the spell is cast).
"""

# ruff: noqa: F403, F405
from __future__ import annotations

from tests.wave110a_kit import *

ASHLING, AIR, TWINS, ORNI, BOLT = "Ashling, the Limitless", "Air Elemental", "Twins of Discord", "Ornithopter", "Lightning Bolt"


@pytest.fixture()
def cards(settings):
    yield from open_repo(settings)


test_full = full_test([ASHLING, TWINS, "Umbra Mystic"])


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

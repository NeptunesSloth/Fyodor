"""Wave 110C: Retether (303.4f-g: each returned Aura enchants a creature of its controller's choice, others stay), Another Round (608.2d chosen not
targeted, 400.7 new object so counters vanish, 608.2c repeat X more times)."""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.wave110c_kit import answer, build, cast, check, make_db, mana, put, real, to_graveyard, zone

EXTRA = [real("Retether", "{3}{W}", 4, "Sorcery",
              "Return each Aura card from your graveyard to the battlefield. Only creatures can be enchanted this way. (Aura cards that can't enchant a creature on the battlefield remain in your graveyard.)", None, "W"),
         real("Another Round", "{X}{X}{2}{W}", 3, "Sorcery",
              "Exile any number of creatures you control, then return them to the battlefield under their owner's control. Then repeat this process X more times.", None, "W"),
         real("Pacifism", "{1}{W}", 2, "Enchantment — Aura", "Enchant creature\nEnchanted creature can't attack or block.", None, "W"),
         real("Wild Growth", "{G}", 1, "Enchantment — Aura", "Enchant land\nWhenever enchanted land is tapped for mana, its controller adds an additional {G}.", None, "G"),
         real("Small Bear", "{1}{G}", 2, "Creature — Bear", "", ("2", "2"), "G"),
         real("Big Bear", "{3}{G}", 4, "Creature — Bear", "", ("4", "4"), "G")]


@pytest.fixture()
def card_db(settings):
    return make_db(settings, EXTRA)


@pytest.mark.parametrize("name", ["Retether", "Another Round"])
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def test_retether_returns_creature_auras_onto_any_creature_and_leaves_land_auras(cards):
    """303.4f-g: Pacifism returns attached to the creature its controller picks (an opponent's here); Wild Growth can't enchant a creature and stays."""
    s = build(cards, ["Retether", "Pacifism", "Wild Growth"], ["Small Bear"])
    opp = put(s, "Small Bear", "p2")
    pac, wg = (next(c for c in s.state.cards.values() if c.name == n and c.owner == "p1") for n in ("Pacifism", "Wild Growth"))
    act(s, "p1", type="move", card_ids=[pac.id, wg.id], to={"player": "p1", "zone": "graveyard"})
    mana(s, W=1, C=3)
    cast(s, "Retether")
    answer(s)
    assert zone(s, pac) == "p1:battlefield" and s.state.cards[pac.id].attached_to == opp.id
    assert zone(s, wg) == "p1:graveyard"
    check(s)


def test_retether_with_no_creature_returns_nothing(cards):
    s = build(cards, ["Retether", "Pacifism"])
    pac = next(c for c in s.state.cards.values() if c.name == "Pacifism" and c.owner == "p1")
    act(s, "p1", type="move", card_ids=[pac.id], to={"player": "p1", "zone": "graveyard"})
    mana(s, W=1, C=3)
    cast(s, "Retether")
    answer(s)
    assert zone(s, pac) == "p1:graveyard"
    check(s)


def counters(s, c):
    return s.state.cards[c.id].counters.get("+1/+1", 0)


@pytest.mark.parametrize("x,picks,left", [(0, 1, (0, 2)), (1, 1, (0, 0)), (1, 0, (2, 0))])
def test_another_round_blinks_chosen_creatures_and_repeats(cards, x, picks, left):
    """Counters come off a blinked creature (400.7). The process repeats X more times; each repeat re-chooses among the creatures then there."""
    s = build(cards, ["Another Round", "Small Bear", "Big Bear"])
    a, b = put(s, "Small Bear"), put(s, "Big Bear")
    for c in (a, b):
        act(s, "p1", type="counter", card_ids=[c.id], kind="+1/+1", delta=2)
    mana(s, W=1, C=2 + 2 * x)
    c = next(c for c in s.state.cards.values() if c.name == "Another Round" and c.owner == "p1")
    act(s, "p1", type="move", card_ids=[c.id], to={"player": "p1", "zone": "hand"})
    act(s, "p1", type="cast_spell", card_id=c.id, targets=[], x_value=x, sources=[])
    # first pass: Small Bear (or nothing); the repeat, if any, blinks Big Bear
    answer(s, [a.id] if picks else [], *([[b.id]] if x else []))
    assert (counters(s, a), counters(s, b)) == left
    check(s)

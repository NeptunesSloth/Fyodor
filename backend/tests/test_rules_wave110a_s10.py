"""Wave 110A session 10: real Oracle text cards (tests/fixtures/wave110a_cards.json), each scenario checks replay and save/load.

* Monstrous Emergence - 701.4a behold a creature (reveal a creature card from hand or choose a creature you control) as a cost; damage = its power.
* Dragon's Fire - the optional version: 3 damage, or the beheld Dragon's power instead.
* Yuna's Decision - 701.21a sacrifice, then (608.2c) "If you do" draw and put at most one creature card and one land card from hand onto the battlefield.
"""

# ruff: noqa: F403, F405
from __future__ import annotations

from tests.wave110a_kit import *

YUNA = "Yuna's Decision"
EMERGENCE = "Monstrous Emergence"
FIRE = "Dragon's Fire"
DRAGON = "Shivan Dragon"


@pytest.fixture()
def cards(settings):
    yield from open_repo(settings)


test_full = full_test([YUNA, EMERGENCE, FIRE])


def _on_bf(s, name):
    return sum(1 for c in s.state.cards.values() if c.name == name and c.zone == "p1:battlefield")


def test_yuna_sacrifices_draws_and_puts_a_creature_and_a_land(cards):
    s = build(cards, [YUNA, "Muscle Sliver", "Grizzly Bears", "Forest"])
    put(s, "Muscle Sliver")
    to_hand(s, "Grizzly Bears")
    to_hand(s, "Forest")
    cast(s, YUNA, modes=[0])
    answer(s)
    assert _on_bf(s, "Muscle Sliver") == 0 and zone_of(s, "Muscle Sliver") == "p1:graveyard"
    assert _on_bf(s, "Grizzly Bears") == 1 and _on_bf(s, "Forest") == 1
    check(s)


def test_yuna_does_nothing_more_without_a_creature_to_sacrifice(cards):
    s = build(cards, [YUNA, "Grizzly Bears", "Forest"])
    bears = to_hand(s, "Grizzly Bears")
    cast(s, YUNA, modes=[0])
    answer(s)
    assert s.state.cards[bears.id].zone == "p1:hand"  # 608.2c: "If you do" - nothing was sacrificed, so no puts
    check(s)


def _dies(s, name="Shivan Dragon"):
    return zone_of(s, name, "p2") == "p2:graveyard"


def test_monstrous_emergence_uses_the_power_of_a_creature_you_chose(cards):
    s = build(cards, [EMERGENCE, "Grizzly Bears"], ["Grizzly Bears"])
    bears = put(s, "Grizzly Bears")
    foe = put(s, "Grizzly Bears", "p2")
    spell = to_hand(s, EMERGENCE)
    fund(s, "{1}{G}")
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=[foe.id], cost_choices=[{"component": 0, "cards": [bears.id]}])
    answer(s)
    assert s.state.cards[foe.id].zone == "p2:graveyard" and s.state.cards[bears.id].zone == "p1:battlefield"  # the chosen creature isn't sacrificed
    check(s)


def test_monstrous_emergence_uses_the_power_of_a_revealed_card(cards):
    s = build(cards, [EMERGENCE, DRAGON], [DRAGON])
    dragon = to_hand(s, DRAGON)
    foe = put(s, DRAGON, "p2")
    spell = to_hand(s, EMERGENCE)
    fund(s, "{1}{G}")
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=[foe.id], cost_choices=[{"component": 0, "cards": [dragon.id]}])
    answer(s)
    assert _dies(s) and s.state.cards[dragon.id].zone == "p1:hand"  # 5 damage from the revealed Dragon card
    check(s)


@pytest.mark.parametrize("beheld", [True, False])
def test_dragons_fire_deals_the_dragons_power_only_when_one_was_beheld(cards, beheld):
    s = build(cards, [FIRE, DRAGON], [DRAGON])
    dragon = to_hand(s, DRAGON)
    foe = put(s, DRAGON, "p2")
    spell = to_hand(s, FIRE)
    fund(s, "{1}{R}")
    extra = {"optional_costs": [spell.id + ":behold"], "cost_choices": [{"component": 0, "cards": [dragon.id]}]} if beheld else {}
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=[foe.id], **extra)
    answer(s)
    assert _dies(s) == beheld  # 3 damage without the Dragon, 5 with it
    check(s)

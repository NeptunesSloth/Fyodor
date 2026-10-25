"""Wave 110J: single-card wordings, real Oracle text (tests/fixtures/wave110j_cards.json). Every scenario checks the replay and a save and a load.

* 613.4c, 107.1a: Aspect of Wolf gives +X/+Y, X half the Forests its controller has (rounded down), Y half of them (rounded up).
* 611.2a, 305.7, 502.3: Orcish Farmer makes a land a Swamp until its controller's next untap step — the land's controller, not the Farmer's.
* 602.2, 611.2a: Bronze Cudgels pumps by the number of times its ability has resolved this turn (1, then 2: +3 in all), and starts over next turn.
* 508.1, 603.2: Mob Mentality triggers only when every non-Wall creature its controller has is attacking (a Wall may stay home); +X/+0 counts the attackers.
* 502.3, 611.2a: Mindbender Spores puts four fungus counters on the creature it blocks, which then stays tapped through its controller's untap step
  while it has one, and loses one at each of its controller's upkeeps.
"""

from __future__ import annotations

import pytest

from tests.game_helpers import act
from tests.wave9c_kit import build
from tests.wave110b_kit import attack, through_combat
from tests.wave110j_kit import (  # noqa: F401
    EXTRA,
    activate,
    card_db,
    cast_on,
    ch,
    check,
    full,
    mana,
    move,
    now,
    put,
    put_new,
    settle,
    to_phase,
)


@pytest.mark.parametrize("name", ["Aspect of Wolf", "Orcish Farmer", "Bronze Cudgels", "Mob Mentality", "Mindbender Spores"])
def test_the_cards_are_full(name):
    assert full(name)


@pytest.mark.parametrize(("forests", "bonus"), [(0, (0, 0)), (1, (0, 1)), (4, (2, 2)), (5, (2, 3))])
def test_aspect_of_wolf_rounds_each_half_its_own_way(cards, forests, bonus):
    s = build(cards, ["Aspect of Wolf", "Templar Knight"])
    knight = put_new(s, "Templar Knight")
    for _ in range(forests):
        put_new(s, "Forest")
    base = ch(s, knight).pt
    cast_on(s, "Aspect of Wolf", knight)
    assert tuple(int(a) - int(b) for a, b in zip(ch(s, knight).pt, base, strict=True)) == bonus
    check(s)


def ready(s, c):
    s.state.rules.controlled_since[c.id].turn = 0


def types(s, c):
    return set(ch(s, c).subtypes)


@pytest.mark.parametrize(("owner", "still_a_swamp_on_turn_2"), [("p2", False), ("p1", True)])
def test_orcish_farmer_lasts_until_the_lands_controllers_next_untap_step(cards, owner, still_a_swamp_on_turn_2):
    s = build(cards, ["Orcish Farmer"])
    farmer = put(s, "Orcish Farmer")
    ready(s, farmer)
    land = put_new(s, "Island" if owner == "p2" else "Forest", owner)
    base = types(s, land)
    activate(s, farmer, "{T}", targets=[land.id])
    assert types(s, land) == {"Swamp"} and base != {"Swamp"}
    to_phase(s, "main1", turn=2)
    assert (types(s, land) == {"Swamp"}) is still_a_swamp_on_turn_2
    to_phase(s, "main1", turn=3)
    assert types(s, land) == base
    check(s)


def test_bronze_cudgels_counts_its_resolutions(cards):
    s = build(cards, ["Bronze Cudgels", "Templar Knight"])
    knight, cudgels = put_new(s, "Templar Knight"), put(s, "Bronze Cudgels")
    mana(s, C=1)
    activate(s, cudgels, "Equip", targets=[knight.id])
    base = int(ch(s, knight).pt[0])
    for total in (1, 3, 6):
        mana(s, C=2)
        activate(s, cudgels, "{2}")
        assert int(ch(s, knight).pt[0]) == base + total
    to_phase(s, "main1", turn=3)
    mana(s, C=2)
    activate(s, cudgels, "{2}")
    assert int(ch(s, knight).pt[0]) == base + 1
    check(s)


@pytest.mark.parametrize(("stay_home", "bonus"), [("Wall of Stone", 2), ("Templar Knight", 0)])
def test_mob_mentality_needs_every_non_wall_creature_to_attack(cards, stay_home, bonus):
    s = build(cards, ["Mob Mentality", "Grizzly Bears", "Templar Knight", "Wall of Stone"])
    crew = {n: put_new(s, n) for n in ("Grizzly Bears", "Templar Knight", "Wall of Stone")}
    cast_on(s, "Mob Mentality", crew["Grizzly Bears"])
    base = int(ch(s, crew["Grizzly Bears"]).pt[0])
    attack(s, *(c for n, c in crew.items() if n != stay_home and n != "Wall of Stone"))
    settle(s)
    assert int(ch(s, crew["Grizzly Bears"]).pt[0]) == base + bonus
    check(s)


def test_mindbender_spores_keeps_the_blocked_creature_tapped_until_the_counters_run_out(cards):
    s = build(cards, ["Grizzly Bears"], ["Mindbender Spores"])
    bears, spores = put_new(s, "Grizzly Bears"), put(s, "Mindbender Spores", "p2")
    attack(s, bears)
    through_combat(s, [(spores, bears)])
    assert s.state.cards[bears.id].counters == {"fungus": 4} and s.state.cards[bears.id].tapped
    for turn, left in ((3, 3), (5, 2)):
        to_phase(s, "main1", turn=turn)
        assert s.state.cards[bears.id].counters == {"fungus": left} and s.state.cards[bears.id].tapped
    check(s)


def test_loki_is_full():
    assert full("Loki, God of Lies")


def test_loki_steals_the_spells_single_target_until_end_of_turn(cards):
    """115.9c, 611.2b: Loki takes the creature a spell targets; on its controller's turn it also untaps and gains haste; control ends at cleanup."""
    s = build(cards, ["Loki, God of Lies", "Aspect of Wolf", "Grizzly Bears"], ["Grizzly Bears"])
    put(s, "Loki, God of Lies")
    bears = put_new(s, "Grizzly Bears", "p2")
    act(s, "p2", type="tap", card_ids=[bears.id])
    mana(s, G=1, C=1)
    cast_on(s, "Aspect of Wolf", bears)
    assert now(s, bears).controller == "p1" and not now(s, bears).tapped
    assert "haste" in ch(s, bears).keywords
    to_phase(s, "main1", turn=2)
    assert now(s, bears).controller == "p2"
    check(s)


def test_lithoform_blight_is_full():
    assert full("Lithoform Blight")


def test_lithoform_blight_replaces_a_lands_types_and_abilities(cards):
    """305.7, 613.1d, 613.1f: the land has no land types (so no intrinsic mana ability), only the two granted mana abilities; the Aura draws on entering."""
    s = build(cards, ["Lithoform Blight", "Forest"])
    forest = put_new(s, "Forest")
    assert "Forest" in ch(s, forest).subtypes
    hand = len(s.state.zones["p1:hand"])
    cast_on(s, "Lithoform Blight", forest)
    now_ch = ch(s, forest)
    assert not now_ch.subtypes and "Land" in now_ch.types
    assert sorted(a.text for a in now_ch.abilities if "Add" in a.text) == ["{T}, Pay 1 life: Add one mana of any color.", "{T}: Add {C}."]
    assert len(s.state.zones["p1:hand"]) == hand + 1
    check(s)


def test_love_on_the_battlefield_is_full():
    assert full("Love on the Battlefield")


@pytest.mark.parametrize(("attackers", "triggers"), [(1, False), (2, True), (3, False)])
def test_love_on_the_battlefield_needs_exactly_two_attackers(cards, attackers, triggers):
    """508.1, 603.2: exactly two attackers give first strike and a card; each unblocked one then grows by a +1/+1 counter when it hits a player."""
    s = build(cards, ["Love on the Battlefield", "Grizzly Bears", "Templar Knight", "Llanowar Elves"])
    put(s, "Love on the Battlefield")
    crew = [put_new(s, n) for n in ("Grizzly Bears", "Templar Knight", "Llanowar Elves")][:attackers]
    hand = len(s.state.zones["p1:hand"])
    attack(s, *crew)
    settle(s)
    assert (len(s.state.zones["p1:hand"]) == hand + 1) is triggers
    assert all(("first strike" in ch(s, c).keywords) is triggers for c in crew)
    through_combat(s)
    assert all((now(s, c).counters.get("+1/+1") == 1) is triggers for c in crew)
    check(s)


def test_rootwater_matriarch_is_full():
    assert full("Rootwater Matriarch")


@pytest.mark.parametrize("enchanted", [True, False])
def test_rootwater_matriarch_keeps_the_creature_only_while_it_is_enchanted(cards, enchanted):
    """611.2b, 303.4: control lasts while an Aura is attached to the creature, and does nothing if it has none as the ability resolves."""
    s = build(cards, ["Rootwater Matriarch", "Aspect of Wolf"], ["Grizzly Bears"])
    matriarch, bears = put(s, "Rootwater Matriarch"), put_new(s, "Grizzly Bears", "p2")
    ready(s, matriarch)
    aura = cast_on(s, "Aspect of Wolf", bears) if enchanted else None
    activate(s, matriarch, "{T}", targets=[bears.id])
    assert (now(s, bears).controller == "p1") is enchanted
    if enchanted:
        move(s, aura, "graveyard")
        act(s, "p1", type="pass_priority")  # (a table edit is looked at on the next intent)
        assert now(s, bears).controller == "p2"
    check(s)

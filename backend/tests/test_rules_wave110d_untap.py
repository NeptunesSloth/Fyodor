"""Wave 110D: rules imposed on a permanent, real Oracle text (tests/fixtures/wave110d_cards.json). Every scenario checks the replay and a save and a load.

* 701.26: "Enchanted creature … can't become untapped" (Frozen in Ice, Blossombind), "That creature can't become untapped for as long as you control
  Spider-Woman." — not in the untap step, not by an effect; the Aura's other halves ("loses all abilities", "can't have counters put on it", 614.17).
* 701.27, 701.28f: "can't transform" (Bound by Moonsilver, Immerwolf) — an ability's transform and a daybound / nightbound flip are both left undone.
"""

from __future__ import annotations

import pytest

from tests.wave9c_kit import build
from tests.wave110d_kit import (  # noqa: F401
    EXTRA,
    card_db,
    cast_on,
    ch,
    check,
    full,
    mana,
    next_turn,
    now,
    put,
    settle,
    to_hand,
    to_phase,
)

CY, VM = "Cloistered Youth // Unholy Fiend", "Village Messenger // Moonrise Intruder"
CARDS = ["Frozen in Ice", "Blossombind", "Bound by Moonsilver", "Immerwolf", "Spider-Woman, Secret Agent"]


@pytest.mark.parametrize("name", CARDS)
def test_the_cards_are_full(name):
    assert full(name)


def test_frozen_in_ice_taps_it_and_nothing_untaps_it(cards):
    s = build(cards, ["Frozen in Ice", "Vitalize", "Llanowar Elves"])
    elves = put(s, "Llanowar Elves")
    cast_on(s, "Frozen in Ice", elves)
    assert now(s, elves).tapped  # its enters trigger
    assert not ch(s, elves).abilities  # loses all abilities
    cast_on(s, "Vitalize")  # "Untap all creatures you control."
    assert now(s, elves).tapped  # 701.26: it can't become untapped
    next_turn(s)
    next_turn(s)
    assert now(s, elves).tapped  # nor in its controller's untap step
    check(s)


def test_blossombind_stops_untapping_and_counters(cards):
    s = build(cards, ["Blossombind", "Dragonscale Boon", "Grizzly Bears"])
    bound, free = put(s, "Grizzly Bears"), None
    cast_on(s, "Blossombind", bound)
    assert now(s, bound).tapped
    cast_on(s, "Dragonscale Boon", bound)  # "Put two +1/+1 counters on target creature and untap it."
    assert now(s, bound).tapped and not now(s, bound).counters  # 614.17 / 701.26: neither happens
    next_turn(s)
    next_turn(s)
    assert now(s, bound).tapped
    check(s)
    del free


def test_dragonscale_boon_without_the_aura_does_both(cards):
    s = build(cards, ["Dragonscale Boon", "Grizzly Bears"])
    bear = put(s, "Grizzly Bears")
    mana(s, G=4)
    from tests.game_helpers import act

    act(s, "p1", type="tap", card_ids=[bear.id], tapped=True)
    cast_on(s, "Dragonscale Boon", bear)
    assert not now(s, bear).tapped and now(s, bear).counters == {"+1/+1": 2}
    check(s)


def test_spider_woman_holds_the_creature_for_as_long_as_you_control_her(cards):
    s = build(cards, ["Spider-Woman, Secret Agent"], ["Grizzly Bears"])
    bear = put(s, "Grizzly Bears", "p2")
    spider = cast_on(s, "Spider-Woman, Secret Agent", None)
    assert now(s, bear).tapped  # tapped by her enters trigger (the only legal target)
    next_turn(s)
    next_turn(s)
    assert now(s, bear).tapped  # Bob's untap step: it can't become untapped while Alice controls Spider-Woman
    from tests.game_helpers import act

    act(s, "p1", type="move", card_ids=[spider.id], to={"player": "p1", "zone": "graveyard"})  # she leaves: the hold ends (611.2b)
    next_turn(s)
    next_turn(s)
    assert not now(s, bear).tapped
    check(s)


def test_cloistered_youth_transforms_at_upkeep_without_the_aura(cards):
    s = build(cards, [CY])
    youth = put(s, CY)
    next_turn(s)  # Bob's turn
    next_turn(s)  # Alice's upkeep: "you may transform" (the first option is yes)
    assert now(s, youth).face == 1
    check(s)


def test_bound_by_moonsilver_stops_the_transform(cards):
    s = build(cards, ["Bound by Moonsilver", CY])
    youth = put(s, CY)
    cast_on(s, "Bound by Moonsilver", youth)
    next_turn(s)
    next_turn(s)
    assert now(s, youth).face == 0  # 701.28f: it can't transform (the trigger resolved, the permanent didn't turn over)
    assert {"cant_attack_or_block", "cant_transform"} <= ch(s, youth).imposed  # (the combat half is the old rule, 508.1c / 509.1b)
    check(s)


def test_immerwolf_keeps_a_non_human_werewolf_from_transforming(cards):
    from tests.game_helpers import act

    s = build(cards, ["Immerwolf", VM, "Vitalize"])
    messenger = put(s, VM)
    put(s, "Immerwolf")
    act(s, "p1", type="set_face", card_id=messenger.id, face=1)  # Moonrise Intruder: a Werewolf that isn't Human
    assert now(s, messenger).face == 1
    cast_on(s, "Vitalize")  # two spells in a turn: "At the beginning of each upkeep, if a player cast two or more spells last turn, transform"
    cast_on(s, "Vitalize")
    next_turn(s)
    assert now(s, messenger).face == 1  # Immerwolf: it can't transform
    check(s)


def test_a_non_human_werewolf_transforms_without_immerwolf(cards):
    from tests.game_helpers import act

    s = build(cards, [VM, "Vitalize"])
    messenger = put(s, VM)
    act(s, "p1", type="set_face", card_id=messenger.id, face=1)
    cast_on(s, "Vitalize")
    cast_on(s, "Vitalize")
    next_turn(s)
    assert now(s, messenger).face == 0
    check(s)

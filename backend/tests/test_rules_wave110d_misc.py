"""Wave 110D: misc promotions, real Oracle text (tests/fixtures/wave110d_cards.json). Every scenario checks the replay and a save and a load.

* 702.6b, 614.1, 120.1: "Equip worthy {1}" (legendary non-Villain red and/or white creature) and "Double all damage equipped creature would deal." (Mjölnir).
* 601.2i, 707.10: "Whenever enchanted player casts a spell other than the first spell they cast each turn or copies a spell, this Aura deals 2
  damage to them." (Curse of Shaken Faith) — the first spell is free, the second costs 2.
* 602.5, 605.1a, 606: "Enchanted player can't activate abilities that aren't mana abilities or loyalty abilities." (Overwhelming Splendor) — a
  mana ability still works, any other activated ability is refused.
* 502.3, 603.2c, 107.1: "Whenever you untap one or more permanents during your untap step, put that many time counters on The Millennium Calendar." and
  "When there are 1,000 or more time counters on The Millennium Calendar, sacrifice it and each opponent loses 1,000 life." — one counter per permanent
  untapped; doubling past 1000 sacrifices it.
"""

from __future__ import annotations

from tests.game_helpers import act
from tests.wave9c_kit import build, life
from tests.wave110d_kit import (  # noqa: F401
    activate,
    card_db,
    cast_on,
    ch,
    check,
    full,
    mana,
    next_turn,
    put,
    refused,
    settle,
    to_phase,
)


def test_mjolnir_is_full():
    assert full("Mjölnir, Hammer of Thor")


def test_mjolnir_equips_only_worthy_and_doubles(cards):
    s = build(cards, ["Mjölnir, Hammer of Thor", "Krenko, Mob Boss", "Grizzly Bears"])
    hammer, krenko, bears = put(s, "Mjölnir, Hammer of Thor"), put(s, "Krenko, Mob Boss"), put(s, "Grizzly Bears")
    s.state.rules.controlled_since[krenko.id].turn = 0
    mana(s, C=2)
    refused(s, "target|legal|worthy|Choose", hammer, "Equip", targets=[bears.id])  # green, not legendary
    activate(s, hammer, "Equip", targets=[krenko.id])
    assert s.state.cards[hammer.id].attached_to == krenko.id
    next_turn(s)
    next_turn(s)
    to_phase(s, "declare_attackers", turn=3)
    act(s, "p1", type="set_stops", own=["declare_attackers"], smart_pass=False)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": krenko.id, "target": "p2"}])
    settle(s)
    to_phase(s, "end", turn=3)
    assert life(s, "p2") == 40 - 2 * ch(s, krenko).pt[0]  # Krenko's power doubled (the attack trigger adds a counter first)
    check(s)


def test_shaken_faith_is_full():
    assert full("Curse of Shaken Faith")


def test_shaken_faith_hurts_from_the_second_spell(cards):
    s = build(cards, ["Curse of Shaken Faith", "Lightning Bolt"])
    cast_on(s, "Curse of Shaken Faith", "p1")  # (the player enchanted is the one casting)
    next_turn(s)
    next_turn(s)  # (the Aura itself was the first spell of its turn)
    cast_on(s, "Lightning Bolt", "p2")
    assert life(s, "p1") == 40 and life(s, "p2") == 37  # the first spell is free
    cast_on(s, "Lightning Bolt", "p2")
    assert life(s, "p1") == 38 and life(s, "p2") == 34
    check(s)


def test_overwhelming_splendor_is_full():
    assert full("Overwhelming Splendor")


def test_overwhelming_splendor_stops_only_nonmana_abilities(cards):
    s = build(cards, ["Overwhelming Splendor", "Sol Ring", "Liquimetal Coating"], ["Sol Ring", "Liquimetal Coating"])
    ring, coat = put(s, "Sol Ring", "p2"), put(s, "Liquimetal Coating", "p2")
    cast_on(s, "Overwhelming Splendor", "p2")
    next_turn(s)
    refused(s, "can't be activated", coat, "{T}: Target permanent", pid="p2", targets=[ring.id])
    activate(s, ring, "{T}: Add", pid="p2")
    assert s.state.cards[ring.id].tapped
    check(s)


def test_millennium_calendar_is_full():
    assert full("The Millennium Calendar")


def test_millennium_calendar_counts_untapped_permanents_then_ends(cards):
    s = build(cards, ["The Millennium Calendar", "Sol Ring", "Grizzly Bears"])
    cal, ring, bears = put(s, "The Millennium Calendar"), put(s, "Sol Ring"), put(s, "Grizzly Bears")
    act(s, "p1", type="tap", card_ids=[ring.id, bears.id])
    next_turn(s)
    next_turn(s)
    assert s.state.cards[cal.id].counters == {"time": 2}  # the two that untapped
    act(s, "p1", type="counter", card_ids=[cal.id], kind="time", delta=598)
    mana(s, C=2)
    activate(s, cal, "{2}, {T}: Double")
    assert s.state.cards[cal.id].zone == "p1:graveyard" and life(s, "p2") == 40 - 1000
    check(s)

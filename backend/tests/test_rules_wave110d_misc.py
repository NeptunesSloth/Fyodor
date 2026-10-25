"""Wave 110D: misc promotions, real Oracle text (tests/fixtures/wave110d_cards.json). Every scenario checks the replay and a save and a load.

* 702.6b, 614.1, 120.1: "Equip worthy {1}" (legendary non-Villain red and/or white creature) and "Double all damage equipped creature would deal." (Mjölnir).
* 601.2i, 707.10: "Whenever enchanted player casts a spell other than the first spell they cast each turn or copies a spell, this Aura deals 2
  damage to them." (Curse of Shaken Faith) — the first spell is free, the second costs 2.
* 602.5, 605.1a, 606: "Enchanted player can't activate abilities that aren't mana abilities or loyalty abilities." (Overwhelming Splendor) — a
  mana ability still works, any other activated ability is refused.
* 502.3, 603.2c, 107.1: "Whenever you untap one or more permanents during your untap step, put that many time counters on The Millennium Calendar." and
  "When there are 1,000 or more time counters on The Millennium Calendar, sacrifice it and each opponent loses 1,000 life." — one counter per permanent
  untapped; doubling past 1000 sacrifices it.
* 603.2, 400.7: "Creatures you control have 'Whenever this creature becomes tapped for the first time during each of your turns, put a +1/+1 counter on it.'"
  (Tale of Katara and Toph) — the first tap in the controller's turn counts, a second tap that turn does not.
* 508.1, 603.2c: "Whenever you attack with creatures with total power 6 or greater, you may turn a face-down creature you control face up." (Ugin's
  Mastery) — attackers with power 7 in all trigger it, 2 do not.
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from tests.game_helpers import act
from tests.wave9c_kit import build, card_named, life, to_hand
from tests.wave110d_kit import (  # noqa: F401
    ability,
    activate,
    card_db,
    cast_on,
    ch,
    check,
    full,
    mana,
    next_turn,
    now,
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


def test_shaken_faith_hurts_when_the_enchanted_player_copies_a_spell(cards):
    s = build(cards, ["Curse of Shaken Faith", "Lightning Bolt", "Reverberate"])
    cast_on(s, "Curse of Shaken Faith", "p1")
    next_turn(s)
    next_turn(s)
    act(s, "p1", type="set_prefs", hold_priority=True)
    bolt = to_hand(s, "Lightning Bolt")
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])  # the first spell of the turn: free
    assert life(s, "p1") == 40
    rev = to_hand(s, "Reverberate")
    mana(s, R=2)
    act(s, "p1", type="cast_spell", card_id=rev.id, targets=[bolt.id])  # the second spell: 2; its copy of Bolt: 2 more
    settle(s)
    assert life(s, "p1") == 36 and life(s, "p2") == 34  # 40 - 2 (cast) - 2 (copy); 40 - 3 - 3
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


def test_tale_of_katara_is_full():
    assert full("Tale of Katara and Toph")


def test_tale_of_katara_counts_the_first_tap_only(cards):
    s = build(cards, ["Tale of Katara and Toph", "Grizzly Bears"])
    put(s, "Tale of Katara and Toph")
    bears = put(s, "Grizzly Bears")
    s.state.rules.controlled_since[bears.id].turn = 0
    next_turn(s)
    next_turn(s)
    to_phase(s, "declare_attackers", turn=3)
    act(s, "p1", type="set_stops", own=["declare_attackers"], smart_pass=False)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": bears.id, "target": "p2"}])
    settle(s)
    assert now(s, bears).counters == {"+1/+1": 1}
    act(s, "p1", type="untap_all")
    act(s, "p1", type="tap", card_ids=[bears.id])
    settle(s)
    assert now(s, bears).counters == {"+1/+1": 1}  # the second tap of the turn
    check(s)


def test_ugins_mastery_is_full():
    assert full("Ugin's Mastery")


def _attack(s, *creatures):
    for c in creatures:
        s.state.rules.controlled_since[c.id].turn = 0
    next_turn(s)
    next_turn(s)
    to_phase(s, "declare_attackers", turn=3)
    act(s, "p1", type="set_stops", own=["declare_attackers"], smart_pass=False)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": c.id, "target": "p2"} for c in creatures])


def _slinger(s):
    mana(s, C=3)
    slinger = to_hand(s, "Gravel Slinger")
    act(s, "p1", type="cast_spell", card_id=slinger.id, face_down=True, sources=[])
    settle(s)
    return slinger


def test_ugins_mastery_needs_total_power_six(cards):
    s = build(cards, ["Ugin's Mastery", "Gravel Slinger", "Twisted Abomination"])
    put(s, "Ugin's Mastery")
    dragon = put(s, "Twisted Abomination")  # (before the face-down cast: Mastery manifests the top card of the library for it)
    slinger = _slinger(s)
    _attack(s, slinger, dragon)
    assert s.state.zones.get("stack")  # 2 + 5: the trigger
    act(s, "p1", type="pass_priority")
    d = s.state.rules.decision
    assert d is not None and d.player == "p1"  # asks: the trigger asks
    mana(s, W=1, C=1)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["yes"])
    d = s.state.rules.decision  # (the manifested Forest is face down too)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[next(o.id for o in d.options if o.label == "Gravel Slinger")])
    settle(s)
    assert not now(s, slinger).face_down
    check(s)


def test_ugins_mastery_stays_quiet_below_six(cards):
    s = build(cards, ["Ugin's Mastery", "Gravel Slinger"])
    put(s, "Ugin's Mastery")
    slinger = _slinger(s)
    _attack(s, slinger)
    assert s.state.rules.decision is None and not s.state.zones.get("stack") and now(s, slinger).face_down  # 2 only
    check(s)


def test_summoners_grimoire_is_full():
    assert full("Summoner's Grimoire")


@pytest.mark.parametrize(("name", "enters_attacking"), [("Courser of Kruphix", True), ("Twisted Abomination", False)])
def test_summoners_grimoire_only_an_enchantment_enters_attacking(cards, name, enters_attacking):
    """508.4, 614.12: the put creature enters tapped and attacking only if it is an enchantment card."""
    s = build(cards, ["Summoner's Grimoire", "Grizzly Bears", name])
    grimoire, bears = put(s, "Summoner's Grimoire"), put(s, "Grizzly Bears")
    mana(s, C=3)
    activate(s, grimoire, "Equip {3}", targets=[bears.id])
    to_hand(s, name)
    _attack(s, bears)
    settle(s)
    other = next(c for c in s.state.cards.values() if c.name == name)
    assert other.zone == "p1:battlefield" and other.tapped == enters_attacking
    to_phase(s, "end", turn=3)
    assert life(s, "p2") == 40 - 2 - (ch(s, other).pt[0] if enters_attacking else 0)
    check(s)


def test_etrata_is_full():
    assert full("Etrata, the Silencer")


@pytest.mark.parametrize("already", [1, 2])
def test_etrata_exiles_counts_hit_counters_and_shuffles_in(cards, already):
    """701.13, 122.1, 104.3e, 701.24: the third owned exiled card with a hit counter loses the game; Etrata is shuffled into its owner's library."""
    mine = ["Etrata, the Silencer"]
    theirs = ["Grizzly Bears", "Twisted Abomination", "Courser of Kruphix"]
    s = build(cards, mine, theirs)
    etrata = put(s, "Etrata, the Silencer")
    victim = put(s, "Courser of Kruphix", "p2")
    for name in theirs[:already]:
        gone = put(s, name, "p2")
        act(s, "p2", type="move", card_ids=[gone.id], to={"player": "p2", "zone": "exile"})
        act(s, "p1", type="counter", card_ids=[gone.id], kind="hit", delta=1)
    s.state.rules.controlled_since[etrata.id].turn = 0
    _attack(s, etrata)
    settle(s)
    if already == 1:
        to_phase(s, "end", turn=3)
    else:
        with pytest.raises(ActionError, match="game is over"):  # (the third card: p2 loses, Alice wins)
            to_phase(s, "end", turn=3)
    assert now(s, victim).zone == "p2:exile" and now(s, victim).counters == {"hit": 1}
    assert now(s, etrata).zone == "p1:library"
    assert bool(s.state.rules.lost.get("p2")) == (already == 2)
    check(s)


def test_common_cause_is_full():
    assert full("Common Cause")


def test_common_cause_needs_one_color_all_nonartifact_creatures_share(cards):
    """105.4, 611.3a: +2/+2 only while every nonartifact creature has a color in common (Sol Ring-style artifacts do not count)."""
    s = build(cards, ["Common Cause", "Grizzly Bears", "Courser of Kruphix", "Twisted Abomination"])
    put(s, "Common Cause")
    bears, courser = put(s, "Grizzly Bears"), put(s, "Courser of Kruphix")
    assert ch(s, bears).pt == (4, 4) and ch(s, courser).pt == (4, 6)  # (both green)
    abomination = put(s, "Twisted Abomination")  # black: no color shared by all three
    assert ch(s, bears).pt == (2, 2) and ch(s, abomination).pt == (5, 3)
    act(s, "p1", type="move", card_ids=[abomination.id], to={"player": "p1", "zone": "graveyard"})
    assert ch(s, bears).pt == (4, 4)
    check(s)


def test_crown_of_the_ages_is_full():
    assert full("Crown of the Ages")


def test_crown_of_the_ages_moves_the_aura_to_another_creature(cards):
    """701.3a-b, 115.1: only the Aura is targeted; the new host is chosen on resolution and can't be the creature it is already on."""
    s = build(cards, ["Crown of the Ages", "Holy Strength", "Grizzly Bears", "Courser of Kruphix", "Twisted Abomination"])
    crown, bears, courser = put(s, "Crown of the Ages"), put(s, "Grizzly Bears"), put(s, "Courser of Kruphix")
    abomination = put(s, "Twisted Abomination")
    aura = cast_on(s, "Holy Strength", bears)
    assert aura.attached_to == bears.id and ch(s, bears).pt == (3, 4)
    mana(s, C=4)
    act(s, "p1", type="activate_ability", card_id=crown.id, ability=ability(s, crown, "{4}, {T}"), targets=[aura.id])
    for _ in range(5):  # (pass priority until the ability resolves and asks for the creature)
        if s.state.rules.decision is not None:
            break
        act(s, s.state.rules.priority, type="pass_priority")
    d = s.state.rules.decision
    assert sorted(o.id for o in d.options) == sorted([courser.id, abomination.id])  # (not the creature it is attached to)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[abomination.id])
    settle(s)
    assert now(s, aura).attached_to == abomination.id and ch(s, bears).pt == (2, 2)
    check(s)


def test_tizerus_charger_is_full():
    assert full("Tizerus Charger")


@pytest.mark.parametrize("pick", ["+1/+1", "flying"])
def test_tizerus_charger_escapes_with_the_chosen_counter(cards, pick):
    """702.138c, 122.1: it escapes with your choice of a +1/+1 counter or a flying counter; cast from the hand it has neither."""
    s = build(cards, ["Tizerus Charger", "Grizzly Bears", "Courser of Kruphix", "Twisted Abomination", "Holy Strength", "Pacifism"])
    charger = card_named(s, "Tizerus Charger")
    for name in ("Tizerus Charger", "Grizzly Bears", "Courser of Kruphix", "Twisted Abomination", "Holy Strength", "Pacifism"):
        act(s, "p1", type="move", card_ids=[card_named(s, name).id], to={"player": "p1", "zone": "graveyard"})
    mana(s, B=1, C=4)
    act(s, "p1", type="cast_spell", card_id=charger.id)
    for _ in range(10):
        d = s.state.rules.decision
        if d is not None:
            break
        act(s, s.state.rules.priority, type="pass_priority")
    assert sorted(o.id for o in d.options) == ["+1/+1", "flying"]
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[pick])
    settle(s)
    assert now(s, charger).zone == "p1:battlefield" and now(s, charger).counters == {pick: 1}
    check(s)

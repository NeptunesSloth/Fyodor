"""Wave 111D: Star Trek counters and triggers. Real Oracle text (Scryfall, 2026-10-30); every scenario checks the replay and a save and a load.

* Ensign Harry Kim: "if it has greater power than Ensign Kim" (603.4: checked as it triggers and as it resolves; "Ensign Kim" is its short name,
  201.5c) and "Remove two +1/+1 counters from among creatures you control" (602.2: one counter per pick, from any of them).
* Zefram Cochrane: "Spacecraft you control enter with two additional charge counters on them." (614.1c, 122.6).
* "Whenever you attack while creatures you control have total power 8 or greater, …" (Hologram Janeway, Tactical Officer): the condition is part of
  the trigger event, judged as attackers are declared (508.1, 603.2), over every creature you control, attacking or not.
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import real
from tests.test_rules_wave30m_durations import to_phase
from tests.test_rules_wave111d_costs import answer, build3, cast, ch, counters
from tests.wave9c_kit import build, check, life, mana, put

EXTRA = [
    real("Ensign Harry Kim, Operations", "{1}{W}", 2, "Legendary Creature — Human Officer", "Whenever another creature you control enters, if it has greater "
         "power than Ensign Kim, put a +1/+1 counter on Ensign Kim.\n{2}, Remove two +1/+1 counters from among creatures you control: Draw a card.", ("1", "2"), "W"),
    real("Zefram Cochrane, Warp Pioneer", "{2}{U}", 3, "Legendary Creature — Human Pilot", "You may look at the top card of your library any time.\nOnce "
         "during each of your turns, you may cast an artifact spell from the top of your library.\nSpacecraft you control enter with two additional charge "
         "counters on them.", ("2", "3"), "U"),
    real("Hologram Janeway", "{2}{W}", 3, "Legendary Artifact Creature — Illusion Officer", "Whenever you attack while creatures you control have total "
         "power 8 or greater, put a +1/+1 counter on target creature.", ("3", "3"), "W"),
    real("Tactical Officer", "{1}{W}", 2, "Creature — Human Officer", "Whenever you attack while creatures you control have total power 8 or greater, put a "
         "+1/+1 counter on this creature. Untap it.", ("2", "1"), "W"),
    real("Planet Killer", "{8}", 8, "Artifact Creature — Construct", "Flying, indestructible\nThis creature attacks each combat if able.\nWhenever this "
         "creature deals combat damage to a player, put a +1/+1 counter on it for each land that player controls.", ("9", "9"), ""),
    real("Dr. Beverly Crusher", "{2}{W}", 3, "Legendary Creature — Human Doctor", "If you gaining life causes a triggered ability of a permanent you "
         "control to trigger, that ability triggers an additional time.\nWhenever you gain life, put a +1/+1 counter on Dr. Crusher.", ("2", "2"), "W"),
]
NAMES = [c["name"] for c in EXTRA]
EXTRA += [
    real("Soul Warden", "{W}", 1, "Creature — Human Cleric", "Whenever another creature enters, you gain 1 life.", ("1", "1"), "W"),
    real("Ajani's Pridemate", "{1}{W}", 2, "Creature — Cat Soldier", "Whenever you gain life, put a +1/+1 counter on this creature.", ("2", "2"), "W"),
    real("Lizard Warrior", "{3}{R}", 4, "Creature — Lizard Warrior", "", ("4", "2"), "R"),
    real("Grizzly Bears", "{1}{G}", 2, "Creature — Bear", "", ("2", "2"), "G"),
    real("Centaur Courser", "{2}{G}", 3, "Creature — Centaur Warrior", "", ("3", "3"), "G"),
    real("Lumen-Class Frigate", "{1}{W}", 2, "Artifact — Spacecraft", "Station (Tap another creature you control: Put charge counters equal to its power on "
         "this Spacecraft. Station only as a sorcery. It's an artifact creature at 12+.)\n2+ | Other creatures you control get +1/+1.\n12+ | Flying, lifelink",
         ("3", "5"), "W"),
    real("Ur-Golem's Eye", "{4}", 4, "Artifact", "{T}: Add {C}{C}.", None, ""),
]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database
    from tests.fixtures.cards import fixture_cards

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.mark.parametrize("name", NAMES)
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def hand(s, pid="p1"):
    return len(s.state.zones.get(f"{pid}:hand", []))


# -- Ensign Harry Kim --------------------------------------------------------------------------------------------------------------------
def test_ensign_kim_grows_only_for_a_stronger_creature_of_yours(cards):
    s = build(cards, ["Ensign Harry Kim, Operations", "Grizzly Bears", "Centaur Courser"], ["Grizzly Bears"])
    kim = put(s, "Ensign Harry Kim, Operations")
    mana(s, G=1, C=1)
    cast(s, "Grizzly Bears")  # (2 > 1: a counter, Kim is 2/3)
    answer(s)
    assert counters(s, kim) == 1 and ch(s, kim).pt == (2, 3)
    mana(s, G=1, C=2)
    cast(s, "Centaur Courser")  # (3 > 2: another)
    answer(s)
    assert counters(s, kim) == 2
    to_phase(s, "main1", turn=2)
    mana(s, "p2", G=1, C=1)
    cast(s, "Grizzly Bears", pid="p2")  # (an opponent's creature: "you control", no trigger)
    answer(s)
    assert counters(s, kim) == 2
    check(s)


def test_ensign_kim_no_counter_for_equal_power(cards):
    s = build(cards, ["Ensign Harry Kim, Operations", "Grizzly Bears"])
    kim = put(s, "Ensign Harry Kim, Operations")
    act(s, "p1", type="counter", card_ids=[kim.id], kind="+1/+1", delta=1)  # (Kim is 2/3)
    mana(s, G=1, C=1)
    cast(s, "Grizzly Bears")  # (2 is not greater than 2)
    answer(s)
    assert counters(s, kim) == 1
    check(s)


def test_ensign_kim_draws_by_removing_two_counters_from_among_your_creatures(cards):
    s = build(cards, ["Ensign Harry Kim, Operations", "Grizzly Bears"])
    kim = put(s, "Ensign Harry Kim, Operations")
    bears = put(s, "Grizzly Bears")
    act(s, "p1", type="counter", card_ids=[kim.id], kind="+1/+1", delta=1)
    mana(s, C=2)
    with pytest.raises(ActionError):  # (one counter among them: the cost can't be paid, 602.2b → 601.2h)
        act(s, "p1", type="activate_ability", card_id=kim.id, ability=1)
    act(s, "p1", type="counter", card_ids=[bears.id], kind="+1/+1", delta=1)
    before = hand(s)
    act(s, "p1", type="activate_ability", card_id=kim.id, ability=1)
    answer(s)
    assert counters(s, kim) == 0 and counters(s, bears) == 0 and hand(s) == before + 1
    check(s)


# -- Zefram Cochrane ---------------------------------------------------------------------------------------------------------------------
def test_zefram_cochrane_gives_your_spacecraft_two_charge_counters_as_they_enter(cards):
    s = build(cards, ["Zefram Cochrane, Warp Pioneer", "Lumen-Class Frigate", "Ur-Golem's Eye"], ["Lumen-Class Frigate"])
    zefram = put(s, "Zefram Cochrane, Warp Pioneer")
    mana(s, W=1, C=1)
    frigate = cast(s, "Lumen-Class Frigate")
    answer(s)
    assert counters(s, frigate, "charge") == 2  # (614.1c, 122.6: it enters with them)
    assert ch(s, zefram).pt == (3, 4)  # (2+: the station symbol's ability works at once)
    mana(s, C=4)
    eye = cast(s, "Ur-Golem's Eye")  # (no Spacecraft: none)
    answer(s)
    to_phase(s, "main1", turn=2)
    mana(s, "p2", W=1, C=1)
    theirs = cast(s, "Lumen-Class Frigate", pid="p2")  # (not yours: none)
    answer(s)
    assert s.state.cards[theirs.id].zone == "p2:battlefield"
    assert counters(s, eye, "charge") == 0 and counters(s, theirs, "charge") == 0
    check(s)


# -- "Whenever you attack while creatures you control have total power 8 or greater" ----------------------------------------------------
def attack(s, attackers, turn=3):
    to_phase(s, "declare_attackers", turn=turn)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": a.id, "target": "p2"} for a in attackers])


@pytest.mark.parametrize("big", [True, False])
def test_hologram_janeway_counter_on_target_creature_only_with_total_power_8(cards, big):
    s = build(cards, ["Hologram Janeway", "Centaur Courser", "Grizzly Bears"])
    janeway = put(s, "Hologram Janeway")
    courser = put(s, "Centaur Courser")
    bears = put(s, "Grizzly Bears")
    if not big:
        act(s, "p1", type="move", card_ids=[bears.id], to={"player": "p1", "zone": "graveyard"})  # (3 + 3: 6)
    attack(s, [courser])  # (judged as attackers are declared: 3 + 3 + 2 = 8, counting the creatures that don't attack too)
    d = s.state.rules.decision
    assert (d is not None) is big
    if big:
        assert janeway.id in {o.id for o in d.options} and courser.id in {o.id for o in d.options}
        answer(s, courser.id)
    answer(s)
    assert counters(s, courser) == (1 if big else 0) and counters(s, janeway) == 0
    check(s)


@pytest.mark.parametrize(("other", "big"), [("Lizard Warrior", True), ("Grizzly Bears", False)])
def test_tactical_officer_grows_and_untaps_when_you_attack_with_total_power_8(cards, other, big):
    s = build(cards, ["Tactical Officer", "Centaur Courser", other])
    officer = put(s, "Tactical Officer")
    put(s, "Centaur Courser")
    put(s, other)
    attack(s, [officer])  # (2 + 3 + 4 = 9, or 2 + 3 + 2 = 7)
    answer(s)
    assert counters(s, officer) == (1 if big else 0)
    assert s.state.cards[officer.id].tapped is not big  # ("Untap it": still an attacking creature, 506.4)
    check(s)


# -- Planet Killer -----------------------------------------------------------------------------------------------------------------------
def lands_for(s, pid, name, n):
    found = [c for c in s.state.cards.values() if c.name == name and c.owner == pid and c.zone == f"{pid}:library"][:n]
    act(s, pid, type="move", card_ids=[c.id for c in found], to={"player": pid, "zone": "battlefield"})


@pytest.mark.parametrize(("target", "expected"), [("p2", 2), ("p3", 4)])
def test_planet_killer_grows_by_the_lands_of_the_player_it_hit(cards, target, expected):
    s = build3(cards, ["Planet Killer"])
    killer = put(s, "Planet Killer")
    lands_for(s, "p1", "Forest", 3)  # (yours: not counted)
    lands_for(s, "p2", "Island", 2)
    lands_for(s, "p3", "Mountain", 4)
    act(s, "p1", type="set_stops", own=["main1", "main2"])
    to_phase(s, "declare_attackers", turn=4)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": killer.id, "target": target}])
    to_phase(s, "main2", turn=4)
    assert counters(s, killer) == expected  # (510.2: dealt to that player; 603.7c-style, the player the event names)
    assert life(s, target) == 31
    check(s)


# -- Dr. Beverly Crusher -----------------------------------------------------------------------------------------------------------------
def test_dr_crusher_doubles_your_life_gain_triggers_only(cards):
    s = build(cards, ["Dr. Beverly Crusher", "Ajani's Pridemate", "Soul Warden", "Grizzly Bears"], ["Ajani's Pridemate", "Soul Warden", "Grizzly Bears"])
    crusher = put(s, "Dr. Beverly Crusher")
    mine = put(s, "Ajani's Pridemate")
    put(s, "Soul Warden")
    answer(s)
    assert (counters(s, crusher), counters(s, mine)) == (0, 0)
    mana(s, G=1, C=1)
    cast(s, "Grizzly Bears")  # (Soul Warden's trigger isn't caused by life gain: once; the gain triggers each "whenever you gain life" twice)
    answer(s)
    assert life(s, "p1") == 41
    assert (counters(s, crusher), counters(s, mine)) == (2, 2)  # (603.2c: each triggers an additional time)
    theirs = put(s, "Ajani's Pridemate", "p2")
    put(s, "Soul Warden", "p2")
    to_phase(s, "main1", turn=2)
    mana(s, "p2", G=1, C=1)
    cast(s, "Grizzly Bears", pid="p2")  # (Bob gaining life, his permanents: not Alice's Dr. Crusher's business; Alice's Soul Warden: she gains too)
    answer(s)
    assert life(s, "p2") == 41 and counters(s, theirs) == 1
    assert life(s, "p1") == 42 and (counters(s, crusher), counters(s, mine)) == (4, 4)
    check(s)

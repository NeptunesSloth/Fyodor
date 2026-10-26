"""Wave 110J session 16 (lead decisions; real Oracle text; every scenario checks the replay and a save and a load).

* Spinneret and Spiderling: "Whenever ~ deals 4 or more damage" sums all the damage it deals simultaneously in one damage event, to any
  number of recipients, and triggers once per event (603.2c; the Vampiric Link ruling of 2008-04-01 counts damage whatever the recipient).
  First-strike and regular combat damage are separate events (510.4); prevented damage isn't dealt (615.1).
* Titania's Song: a static ability while on the battlefield (611.3a: artifacts that arrive later are affected); when it leaves, the effect
  continues until end of turn for the artifacts it was affecting then (the principle of 611.2c), not for ones that arrive later.
  Summoning sickness is the ordinary rule (302.6; ruling 2008-08-01).
"""
from __future__ import annotations

import pytest

from app.rules import coverage
from app.rules.casting import summoning_sick
from app.rules.plan import Plan
from tests.game_helpers import act
from tests.test_rules_conditionals import settle
from tests.test_rules_wave12a_counters_keywords import real
from tests.test_rules_wave30m_durations import to_phase
from tests.wave9c_kit import build, check, life, mana, put

SPIN = "Whenever you attack with two or more Spiders, put a +1/+1 counter on Spinneret and Spiderling.\nWhenever Spinneret and Spiderling deals 4 or more damage, exile the top card of your library. Until the end of your next turn, you may play that card."
SONG = "Each noncreature artifact loses all abilities and becomes an artifact creature with power and toughness each equal to its mana value. If this enchantment leaves the battlefield, this effect continues until end of turn."
EXTRA = [
    real("Spinneret and Spiderling", "{R}", 1, "Legendary Creature — Spider Human Hero", SPIN, ("1", "2"), "R"),
    real("Titania's Song", "{3}{G}", 4, "Enchantment", SONG, None, "G"),
    real("Chandra's Ignition", "{3}{R}{R}", 5, "Sorcery", "Target creature you control deals damage equal to its power to each other creature and each opponent.", None, "R"),
    real("Soul's Fire", "{2}{R}", 3, "Instant", "Target creature you control deals damage equal to its power to any target.", None, "R"),
    real("Bandage", "{W}", 1, "Instant", "Prevent the next 1 damage that would be dealt to any target this turn.\nDraw a card.", None, "W"),
    real("Double Cleave", "{1}{R/W}", 2, "Instant", "Target creature gains double strike until end of turn. (It deals both first-strike and regular combat damage.)", None, ("R", "W")),
    real("Disenchant", "{1}{W}", 2, "Instant", "Destroy target artifact or enchantment.", None, "W"),
    real("Jayemdae Tome", "{4}", 4, "Artifact — Book", "{4}, {T}: Draw a card."),
]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database
    from tests.fixtures.cards import fixture_cards

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.mark.parametrize("name", ["Spinneret and Spiderling", "Titania's Song"])
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def cast(s, name, targets=(), pid="p1", **kw):
    c = next(c for c in s.state.cards.values() if c.name == name and c.owner == pid and c.zone in (f"{pid}:library", f"{pid}:hand"))
    act(s, pid, type="move", card_ids=[c.id], to={"zone": "hand"})
    mana(s, pid, C=6, R=3, W=2, G=2)
    act(s, pid, type="cast_spell", card_id=c.id, targets=list(targets), **kw)
    settle(s)
    act(s, pid, type="clear_mana", player=pid)
    return c


def exiled(s):
    return len(s.state.zones.get("p1:exile", []))


def spinneret(cards, *mine, power=1):
    s = build(cards, ["Spinneret and Spiderling", *mine], ["Grizzly Bears"])
    spin = put(s, "Spinneret and Spiderling")
    if power > 1:
        act(s, "p1", type="counter", card_ids=[spin.id], kind="+1/+1", delta=power - 1)
    return s, spin


def test_spinneret_four_to_one_target_exiles_the_top_card(cards):
    s, spin = spinneret(cards, "Soul's Fire", power=4)
    cast(s, "Soul's Fire", [spin.id, "p2"], target_counts=[1, 1])
    assert life(s, "p2") == 36 and exiled(s) == 1 and len(s.state.rules.permissions) == 1
    check(s)


@pytest.mark.parametrize("bandage", [False, True])
def test_spinneret_two_and_two_in_one_event_trigger_once_unless_some_is_prevented(cards, bandage):
    s, spin = spinneret(cards, "Chandra's Ignition", "Bandage", power=2)
    bear = put(s, "Grizzly Bears", "p2")
    if bandage:  # 615.1: the prevented 1 isn't dealt, so the event totals 3
        cast(s, "Bandage", ["p2"])
    cast(s, "Chandra's Ignition", [spin.id])
    assert s.state.cards[bear.id].zone == "p2:graveyard"
    assert life(s, "p2") == (39 if bandage else 38)
    assert exiled(s) == (0 if bandage else 1)
    check(s)


def test_spinneret_two_then_two_in_separate_events_doesnt_trigger(cards):
    s, spin = spinneret(cards, "Soul's Fire", "Soul's Fire", power=2)
    cast(s, "Soul's Fire", [spin.id, "p2"], target_counts=[1, 1])
    cast(s, "Soul's Fire", [spin.id, "p2"], target_counts=[1, 1])
    assert life(s, "p2") == 36 and exiled(s) == 0
    check(s)


@pytest.mark.parametrize("power,triggers", [(2, 0), (4, 2)])
def test_spinneret_double_strike_damage_steps_are_separate_events(cards, power, triggers):
    s, spin = spinneret(cards, "Double Cleave", power=power)
    to_phase(s, "main1", turn=3)
    cast(s, "Double Cleave", [spin.id])
    to_phase(s, "declare_attackers", turn=3)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": spin.id, "target": "p2"}])
    to_phase(s, "main2", turn=3)
    assert life(s, "p2") == 40 - 2 * power and exiled(s) == triggers
    check(s)


def ch(s, card):
    return Plan(s.state, "p1", s.cards, None).ch(s.state.cards[card.id])


def animated(s, card, pt=None):
    c = ch(s, card)
    return c.is_creature and "Artifact" in c.types and not c.abilities and (pt is None or c.pt == pt)


def test_titanias_song_on_the_battlefield_animates_artifacts_that_arrive_later(cards):
    s = build(cards, ["Titania's Song", "Jayemdae Tome", "Sol Ring"])
    tome = put(s, "Jayemdae Tome")
    put(s, "Titania's Song")
    assert animated(s, tome)
    ring = put(s, "Sol Ring")
    assert ch(s, ring).is_creature and not ch(s, ring).abilities
    check(s)


def test_titanias_song_leaving_keeps_its_set_until_end_of_turn_only(cards):
    from app.rules import sba

    s = build(cards, ["Titania's Song", "Jayemdae Tome", "Sol Ring", "Disenchant"])
    tome = put(s, "Jayemdae Tome")
    song = put(s, "Titania's Song")
    cast(s, "Disenchant", [song.id])
    assert s.state.cards[song.id].zone == "p1:graveyard"
    c = ch(s, tome)
    assert c.is_creature and "Artifact" in c.types and not c.abilities
    assert (sba.power(s.state.cards[tome.id], c), sba.toughness(s.state.cards[tome.id], c)) == (4, 4)
    ring = put(s, "Sol Ring")  # arrives after it left: not affected
    assert not ch(s, ring).is_creature and ch(s, ring).abilities
    to_phase(s, "main1", turn=2)  # 514.2: the effect ended in the cleanup step
    assert not ch(s, tome).is_creature and ch(s, tome).abilities
    check(s)


@pytest.mark.parametrize("since_turn_began", [True, False])
def test_titanias_song_summoning_sickness_is_the_ordinary_rule(cards, since_turn_began):
    s = build(cards, ["Titania's Song", "Jayemdae Tome"])
    if since_turn_began:
        tome = put(s, "Jayemdae Tome")
    to_phase(s, "main1", turn=3)
    if not since_turn_began:
        tome = put(s, "Jayemdae Tome")
    put(s, "Titania's Song")
    assert summoning_sick(s.state, s.state.cards[tome.id]) is not since_turn_began
    if since_turn_began:  # ruling 2008-08-01, 302.6
        to_phase(s, "declare_attackers", turn=3)
        act(s, "p1", type="declare_attackers", attackers=[{"card_id": tome.id, "target": "p2"}])
        to_phase(s, "main2", turn=3)
        assert life(s, "p2") == 36
    check(s)

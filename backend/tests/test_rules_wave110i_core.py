"""Wave 110I: real Oracle text; every scenario checks the replay and a save and a load.

* Kraven the Hunter: dies trigger judged on the dead creature's controller's creatures (700.4, 603.10a).
* Rebellion of the Flamekin: "if you won" reads the clash the trigger is about (701.30d).
* Rebellion of the Flamekin: "if you won" reads the clash the trigger is about (701.30d).
* Corrosion: a counter-count selector, "number of rust counters on it" (122.1) and no regeneration (701.8c, 701.19c).
* Survivor's Med Kit: "Choose one that hasn't been chosen" and "loses all rad counters" (122.1i, 728).
* Green Dragon: an end-of-turn watch on damage to creatures an opponent controls (603.7, 120.3).
"""

from __future__ import annotations

import pytest

from app.rules import coverage
from app.rules.plan import Plan
from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import real
from tests.test_rules_wave30m_durations import to_phase
from tests.test_rules_wave100n_multi import answer, cast
from tests.wave9c_kit import build, card_named, check, mana, put

EXTRA = [
    real("Green Dragon", "{3}{G}{G}", 5, "Creature — Dragon",
         "Flying\nPoison Breath — When this creature enters, until end of turn, whenever a creature an opponent controls is dealt damage, destroy it.",
         ("4", "4"), "G"),
    real("Kraven the Hunter", "{2}{G}{G}", 4, "Legendary Creature — Human Warrior",
         "Trample\nWhenever a creature an opponent controls with the greatest power among creatures that player controls dies, draw a card and put a +1/+1 counter on Kraven the Hunter.",
         ("3", "3"), "G"),
    real("Rebellion of the Flamekin", "{3}{R}", 4, "Enchantment",
         "Whenever you clash, you may pay {1}. If you do, create a 3/1 red Elemental Shaman creature token. If you won, that token gains haste until end of turn. (This ability triggers after the clash ends.)",
         None, "R"),
    real("Corrosion", "{2}{B}{B}", 4, "Enchantment",
         "Cumulative upkeep {1}\nAt the beginning of your upkeep, put a rust counter on each artifact target opponent controls. Then destroy each artifact with mana value less than or equal to the number of rust counters on it. Artifacts destroyed this way can't be regenerated.\nWhen this enchantment leaves the battlefield, remove all rust counters from all permanents.",
         None, "B"),
    real("Survivor's Med Kit", "{2}", 2, "Artifact",
         "{1}, {T}: Choose one that hasn't been chosen —\n• Stimpak — Draw a card.\n• Fancy Lads Snack Cakes — Create a Food token. (It's an artifact with \"{2}, {T}, Sacrifice this token: You gain 3 life.\")\n• RadAway — Target player loses all rad counters. Sacrifice this artifact.",
         None, ""),
]
NAMES = [c["name"] for c in EXTRA]
EXTRA += [real("Probe Trinket", "{1}", 1, "Artifact", "", None, ""), real("Probe Idol", "{3}", 3, "Artifact", "", None, "")]
EXTRA += [real("Probe Clash", "{U}", 1, "Sorcery", "Clash with an opponent.", None, "U")]


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


@pytest.mark.parametrize("mine", [False, True])
def test_green_dragon_destroys_damaged_opponent_creature_only(cards, mine):
    s = build(cards, ["Green Dragon", "Lightning Bolt", "Garruk's Horde"], ["Garruk's Horde"])
    horde = put(s, "Garruk's Horde", "p1" if mine else "p2")
    mana(s, G=2, C=3)
    cast(s, "Green Dragon")
    answer(s)
    mana(s, R=1)
    cast(s, "Lightning Bolt", [horde.id])
    answer(s)
    assert s.state.cards[horde.id].zone.endswith("graveyard") is (not mine)  # (your own creature isn't "an opponent controls")
    check(s)


@pytest.mark.parametrize("bigger", [False, True])
def test_kraven_draws_and_grows_only_when_the_greatest_power_creature_dies(cards, bigger):
    s = build(cards, ["Kraven the Hunter", "Lightning Bolt"], ["Grizzly Bears", "Garruk's Horde"])
    bears = put(s, "Grizzly Bears", "p2")
    if bigger:
        put(s, "Garruk's Horde", "p2")
    mana(s, G=2, C=2)
    cast(s, "Kraven the Hunter")
    answer(s)
    hand = len(s.state.zones["p1:hand"])
    mana(s, R=1)
    cast(s, "Lightning Bolt", [bears.id])
    answer(s)
    assert s.state.cards[bears.id].zone.endswith("graveyard")
    kraven = card_named(s, "Kraven the Hunter")
    assert (len(s.state.zones["p1:hand"]) - hand + 1, kraven.counters) == ((1, {}) if bigger else (2, {"+1/+1": 1}))
    check(s)


@pytest.mark.parametrize("win", [True, False])
def test_rebellion_of_the_flamekin_token_has_haste_only_if_you_won(cards, win):
    s = build(cards, ["Rebellion of the Flamekin", "Probe Clash", "Grizzly Bears", "Opt"], ["Grizzly Bears"])
    put(s, "Rebellion of the Flamekin")
    mine, theirs = card_named(s, "Grizzly Bears"), card_named(s, "Grizzly Bears", "p2")
    top = mine if win else card_named(s, "Opt")  # mana value 2 against Bob's 0 (an Island), or 1 against Bob's 2 (701.30d)
    act(s, "p1", type="move", card_ids=[top.id], to={"zone": "library"}, position="top")
    act(s, "p2", type="move", card_ids=[card_named(s, "Island", "p2").id if win else theirs.id], to={"zone": "library"}, position="top")
    mana(s, U=1, C=1)
    cast(s, "Probe Clash")
    answer(s, limit=80)
    token = next(c for c in s.state.cards.values() if c.name == "Elemental Shaman")
    assert ("haste" in Plan(s.state, "p1", s.cards, None).ch(token).keywords) is win
    check(s)


def test_corrosion_rusts_then_destroys_artifacts_the_counters_reach(cards):
    from tests.test_rules_wave30m_durations import to_phase

    s = build(cards, ["Corrosion"], ["Probe Trinket", "Probe Idol"])
    trinket, idol = put(s, "Probe Trinket", "p2"), put(s, "Probe Idol", "p2")
    put(s, "Corrosion"), put(s, "Forest")  # (the cumulative upkeep {1})
    to_phase(s, "upkeep", 3)
    answer(s)
    assert s.state.cards[trinket.id].zone.endswith("graveyard")  # mana value 1 <= 1 rust counter
    assert s.state.cards[idol.id].zone.endswith("battlefield") and s.state.cards[idol.id].counters == {"rust": 1}
    check(s)


def test_med_kit_radaway_clears_rad_counters_and_each_mode_is_used_once(cards):
    s = build(cards, ["Survivor's Med Kit"])
    kit = put(s, "Survivor's Med Kit")
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=kit.id, ability=0, sources=[])
    act(s, "p1", type="choose", decision_id=s.state.rules.decision.id, option_ids=["0:0"])  # Stimpak
    answer(s)
    assert s.state.cards[kit.id].tapped
    to_phase(s, "main1", 3)  # (untapped again)
    act(s, "p2", type="set_resource", player="p2", key="rad", value=3)
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=kit.id, ability=0, sources=[])
    d = s.state.rules.decision
    assert [o.id for o in d.options] == ["1:0", "2:0"]  # the chosen mode can't be chosen again
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["2:0"])
    answer(s, "p2")
    assert s.state.players["p2"].resources.get("rad", 0) == 0 and s.state.cards[kit.id].zone.endswith("graveyard")
    check(s)


def test_kraven_wipe_triggers_once_for_the_biggest_creature(cards):
    """603.10a: a simultaneous wipe is judged on the battlefield as it was just before (700.4)."""
    s = build(cards, ["Kraven the Hunter", "Day of Judgment"], ["Grizzly Bears", "Garruk's Horde"])
    bears, horde = put(s, "Grizzly Bears", "p2"), put(s, "Garruk's Horde", "p2")
    mana(s, G=2, C=2)
    cast(s, "Kraven the Hunter")
    answer(s)
    hand = len(s.state.zones["p1:hand"])
    mana(s, W=2, C=2)
    cast(s, "Day of Judgment")
    answer(s)
    assert all(s.state.cards[c.id].zone.endswith("graveyard") for c in (bears, horde))
    assert (hand, len(s.state.zones["p1:hand"])) == (0, 1)  # one draw: only the 7/7 had the greatest power (Kraven died too)
    check(s)

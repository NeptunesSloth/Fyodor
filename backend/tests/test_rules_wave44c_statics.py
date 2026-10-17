"""Wave 44C (commanders one static / counters / this-turn line short of FULL, CR 2026-09-25), real Oracle text (tests/fixtures/wave44c_cards.json).
Every scenario checks the replay and a save and a load.

* 702.78a, 601.2f: "Each red or green instant or sorcery spell you cast has conspire." (Wort, the Raidmother [13167]) - a red or green instant or sorcery only.
* 205.1b, 613.1d: "As long as Weatherlight Compleated has four or more phyresis counters on it, it's a Phyrexian creature in addition to its other types." [9796].
* 614.1, 616.1, 609.7: "If a creature you control that entered this turn would deal damage, it deals twice that much damage instead." (Neriv, Heart of the Storm [4797]),
  "Double all damage that creature sources you control would deal." (Absorbing Man and Titania [15189]).
* 728.1a, 614.1: "You gain life rather than lose life from radiation." (Strong, the Brutish Thespian [6226]) - its controller's, not an opponent's.
* 509.1c: "Gorm must be blocked if able, and Gorm must be blocked by two or more creatures if able." (Gorm the Great [15293]).
* 510.1a: "If Loot's power is negative, he assigns combat damage as though his power were positive." (Loot, the Anomaly [24455]).
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_wave34b_activated import attack, next_turn, settle, to_phase
from tests.wave44c_kit import DATA, ch, life, on_top, open_cards
from tests.wave9c_kit import build, card_named, check, mana, put, to_hand, zone_of

FULL = ["Wort, the Raidmother", "Weatherlight Compleated", "Neriv, Heart of the Storm", "Absorbing Man and Titania", "Strong, the Brutish Thespian",
        "Gorm the Great", "Loot, the Anomaly"]


@pytest.fixture()
def cards(settings):
    yield from open_cards(settings)


@pytest.mark.parametrize("name", FULL)
def test_coverage_full(cards, name):
    data = next(c for c in DATA if c["name"] == name)
    faces = data.get("card_faces") or [data]
    assert coverage.of_card_data({**data, "faces": faces, "oracle_id": name}).level == "FULL"


# ---- Wort, the Raidmother [13167] ---------------------------------------------------------------------------------------------------------------------
def goblins(s):
    """Wort's two 1/1 red and green Goblin Warrior tokens (put onto the table: the move action runs no enters trigger)."""
    for _ in range(2):
        act(s, "p1", type="create_token", player="p1", token={"name": "Goblin Warrior", "type_line": "Token Creature — Goblin Warrior", "power": "1",
                                                              "toughness": "1", "colors": ["R", "G"]})


def conspire(s, spell, **kw):
    """Cast ``spell`` with the optional conspire cost, tapping the two goblins; the spell and its copy resolve."""
    act(s, "p1", type="cast_spell", card_id=spell.id, optional_costs=[f"{spell.id}:conspire"], **kw)
    for _ in range(12):
        d = s.state.rules.decision
        if d is None:
            if not s.state.zones.get("stack"):
                return
            act(s, s.state.rules.priority, type="pass_priority")
            continue
        ids = [o.id for o in d.options]
        tokens = [c.id for c in s.state.cards.values() if c.is_token]
        pick = ["yes"] if "yes" in ids else tokens if all(g in ids for g in tokens) else ["p2"] if "p2" in ids else ids[:1]
        act(s, d.player, type="choose", decision_id=d.id, option_ids=pick)


def test_wort_gives_a_red_instant_conspire_and_copies_it(cards):
    s = build(cards, ["Wort, the Raidmother", "Lightning Bolt"], [])
    put(s, "Wort, the Raidmother")
    goblins(s)
    bolt = to_hand(s, "Lightning Bolt")
    mana(s, R=1)
    conspire(s, bolt, targets=["p2"])
    assert life(s, "p2") == 40 - 3 - 3  # the spell and its copy
    assert sum(c.tapped for c in s.state.cards.values() if c.is_token) == 2
    check(s)


def test_wort_gives_conspire_neither_to_a_blue_sorcery_nor_to_a_red_creature(cards):
    s = build(cards, ["Wort, the Raidmother", "Divination", "Hill Giant"], [])
    put(s, "Wort, the Raidmother")
    goblins(s)
    for name, pay in (("Divination", {"U": 1, "C": 2}), ("Hill Giant", {"R": 1, "C": 2})):
        spell = to_hand(s, name)
        mana(s, **pay)
        with pytest.raises(ActionError):
            act(s, "p1", type="cast_spell", card_id=spell.id, optional_costs=[f"{spell.id}:conspire"])
    check(s)


# ---- Weatherlight Compleated [9796] -------------------------------------------------------------------------------------------------------------------
def test_weatherlight_is_a_phyrexian_creature_with_four_phyresis_counters(cards):
    s = build(cards, ["Weatherlight Compleated"], [])
    wl = put(s, "Weatherlight Compleated")
    settle(s)
    assert "Creature" not in ch(s, wl).types and "Phyrexian" not in ch(s, wl).subtypes
    act(s, "p1", type="counter", card_ids=[wl.id], kind="phyresis", delta=3)
    assert "Creature" not in ch(s, wl).types
    act(s, "p1", type="counter", card_ids=[wl.id], kind="phyresis", delta=1)
    now = ch(s, wl)
    assert {"Artifact", "Creature"} <= now.types and {"Phyrexian", "Vehicle"} <= now.subtypes and "Legendary" in now.supertypes  # in addition to its other types
    act(s, "p1", type="counter", card_ids=[wl.id], kind="phyresis", delta=-1)
    assert "Creature" not in ch(s, wl).types and "Phyrexian" not in ch(s, wl).subtypes
    check(s)


# ---- Neriv, Heart of the Storm [4797]; Absorbing Man and Titania [15189] -----------------------------------------------------------------------------
def test_neriv_doubles_the_damage_of_a_creature_that_entered_this_turn_only(cards):
    s = build(cards, ["Neriv, Heart of the Storm", "Monastery Swiftspear"], [])
    put(s, "Neriv, Heart of the Storm")
    swift = put(s, "Monastery Swiftspear")  # haste
    settle(s)
    attack(s, swift)
    to_phase(s, "main2")
    assert life(s, "p2") == 40 - 2  # 1 damage, doubled: it entered this turn
    next_turn(s)
    attack(s, swift)
    to_phase(s, "main2")
    assert life(s, "p2") == 40 - 2 - 1  # it has been there since the turn began
    check(s)


def test_absorbing_man_doubles_creature_sources_but_not_spells(cards):
    s = build(cards, ["Absorbing Man and Titania", "Monastery Swiftspear", "Lightning Bolt"], [])
    put(s, "Absorbing Man and Titania")
    swift = put(s, "Monastery Swiftspear")
    settle(s)
    bolt = to_hand(s, "Lightning Bolt")
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])
    settle(s)
    assert life(s, "p2") == 40 - 3  # a spell is not a creature source
    attack(s, swift)
    to_phase(s, "main2")
    assert life(s, "p2") == 40 - 3 - 4  # the Swiftspear's prowess made it 2/3: 2 damage, doubled
    check(s)


# ---- Strong, the Brutish Thespian [6226] ---------------------------------------------------------------------------------------------------------------
def radiation(s, pid, rad=3):
    """``pid`` gets rad counters and four nonland cards on top of their library (the first is drawn in the draw step); returns at their precombat main."""
    act(s, pid, type="resource", player=pid, key="rad", delta=rad)
    for name in ("Hill Giant", "Grizzly Bears", "Shivan Dragon", "Goblin Piker"):
        on_top(s, name, pid)
    to_phase(s, "main1", turn=s.state.turn.number + (2 if pid == "p1" else 1))
    settle(s)


def test_strong_turns_the_life_lost_to_radiation_into_life_gained(cards):
    s = build(cards, ["Strong, the Brutish Thespian", "Hill Giant", "Grizzly Bears", "Shivan Dragon", "Goblin Piker"], [])
    put(s, "Strong, the Brutish Thespian")
    settle(s)
    radiation(s, "p1")
    assert life(s, "p1") == 43 and s.state.players["p1"].resources.get("rad", 0) == 0  # 3 nonland cards milled: gain 3, remove 3 counters
    check(s)


def test_strong_changes_nothing_for_an_opponents_radiation(cards):
    s = build(cards, ["Strong, the Brutish Thespian"], ["Hill Giant", "Grizzly Bears", "Shivan Dragon", "Goblin Piker"])
    put(s, "Strong, the Brutish Thespian")
    settle(s)
    radiation(s, "p2")
    assert life(s, "p2") == 37 and s.state.players["p2"].resources.get("rad", 0) == 0
    assert life(s, "p1") == 40
    check(s)

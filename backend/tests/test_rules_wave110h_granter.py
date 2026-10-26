"""Wave 110H: a quoted grant whose cost names its granter's counters (CR 607.1a, 602.2b, 118.3, 122.1).

* Hankyu: "{T}, Remove all aim counters from Hankyu: This creature deals damage to any target equal to the number of aim counters removed this way."
  The Equipment (not the creature) loses every aim counter as the cost; the count is what it deals (the creature is the source).
"""
from __future__ import annotations

import pytest

from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_effects import mana
from tests.test_rules_wave9b_exile_permission import answer, roundtrip
from tests.test_rules_wave18f_granted import _attach, _derived, _equipped

HANKYU = ('Equipped creature has "{T}: Put an aim counter on Hankyu" and "{T}, Remove all aim counters from Hankyu: This creature deals damage '
          'to any target equal to the number of aim counters removed this way."\nEquip {4} ({4}: Attach to target creature you control. Equip only as a sorcery.)')
EXTRA = [
    card("Test Small", set_code="tst", number="110H0", mana_cost="{G}", cmc=1.0, type_line="Creature — Elf", power="2", toughness="2",
         colors=["G"], color_identity=["G"], keywords=["Haste"], oracle_text="Haste"),
    card("Hankyu", set_code="tst", number="110H1", mana_cost="{3}", cmc=3.0, type_line="Artifact — Equipment", oracle_text=HANKYU),
]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def test_coverage_full(cards):
    assert coverage.of_card_data(cards.resolve("Hankyu")).level == "FULL"


@pytest.mark.parametrize("n", [0, 3])
def test_removes_all_aim_counters_from_the_equipment_and_deals_that_much(cards, n):
    s, gear, bear = _equipped(cards, "Hankyu")
    _attach(s, gear, bear)
    if n:
        act(s, "p1", type="counter", card_ids=[gear.id], kind="aim", delta=n)
    ability = next(a for a in _derived(s, "Test Small").abilities if a.kind == "activated" and "Remove all" in a.text)
    act(s, "p1", type="activate_ability", card_id=bear.id, ability=ability.index, targets=["p2"])
    assert s.state.cards[gear.id].counters.get("aim", 0) == 0 and s.state.cards[bear.id].tapped
    answer(s)
    assert s.state.players["p2"].life == 40 - n
    roundtrip(s)


# -- Lagrella, the Magpie --
LAGRELLA = ("When Lagrella enters, exile any number of other target creatures controlled by different players until Lagrella leaves the battlefield. "
            "When an exiled card enters under your control this way, put two +1/+1 counters on it.")
EXTRA2 = [
    card("Lagrella, the Magpie", set_code="tst", number="110H2", mana_cost="{3}{U}", cmc=4.0, type_line="Legendary Creature — Bird Rogue", power="3",
         toughness="3", colors=["U"], color_identity=["U"], oracle_text=LAGRELLA),
]


@pytest.fixture()
def card_db2(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA, *EXTRA2], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def test_lagrella_full(cards, card_db2):
    assert coverage.of_card_data(cards.resolve("Lagrella, the Magpie")).level == "FULL"


def test_lagrella_counters_only_on_the_card_that_returns_under_your_control(cards, card_db2):
    """603.7 / 610.3c: each exiled card returns under its owner's control; only yours gets the two counters (400.7: a new object)."""
    from tests.test_rules_wave9b_exile_permission import build, find, put

    s = build(cards, p1=("Lagrella, the Magpie", "Test Small"), p2=("Test Small",))
    mine, theirs = put(s, "Test Small", "battlefield"), put(s, "Test Small", "battlefield", "p2")
    put(s, "Lagrella, the Magpie", "hand")
    mana(s, U=1, C=3)
    act(s, "p1", type="cast_spell", card_id=find(s, "Lagrella, the Magpie").id)
    for _ in range(10):  # the spell resolves, then the enters trigger asks for its targets
        if s.state.rules.decision is not None:
            break
        act(s, s.state.rules.priority, type="pass_priority")
    d = s.state.rules.decision
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[mine.id, theirs.id])
    answer(s)
    assert s.state.cards[mine.id].zone.endswith(":exile") and s.state.cards[theirs.id].zone.endswith(":exile")
    act(s, "p1", type="set_damage", card_ids=[find(s, "Lagrella, the Magpie").id], value=3)  # state-based death, so the return is not manual
    act(s, "p1", type="pass_priority")
    answer(s)
    assert s.state.cards[mine.id].zone == "p1:battlefield" and s.state.cards[mine.id].counters.get("+1/+1", 0) == 2
    assert s.state.cards[theirs.id].zone == "p2:battlefield" and not s.state.cards[theirs.id].counters.get("+1/+1")
    roundtrip(s)


# -- Unpredictable Cyclone --
CYCLONE = ("If a cycling ability of another nonland card would cause you to draw a card, instead exile cards from the top of your library until you exile a card that "
           "shares a card type with the cycled card. You may cast that card without paying its mana cost. Then put the exiled cards that weren't cast this way on the bottom "
           "of your library in a random order.\nCycling {2} ({2}, Discard this card: Draw a card.)")
EXTRA3 = [
    card("Unpredictable Cyclone", set_code="tst", number="110H3", mana_cost="{3}{R}", cmc=4.0, type_line="Enchantment", oracle_text=CYCLONE),
    card("Test Cycler", set_code="tst", number="110H4", mana_cost="{3}", cmc=3.0, type_line="Creature — Elf", power="1", toughness="1",
         oracle_text="Cycling {1}"),
    card("Test Sandbar", set_code="tst", number="110H5", mana_cost="", cmc=0.0, type_line="Land", oracle_text="{T}: Add {U}.\nCycling {1}"),
]


@pytest.fixture()
def card_db3(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA, *EXTRA3], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def test_cyclone_full(cards, card_db3):
    assert coverage.of_card_data(cards.resolve("Unpredictable Cyclone")).level == "FULL"


def _cycle_setup(cards, cycler, with_cyclone=True, ability=0):
    from tests.test_rules_wave9b_exile_permission import build, find, put

    s = build(cards, p1=("Unpredictable Cyclone", cycler, "Test Small", "Forest"))
    if with_cyclone:
        put(s, "Unpredictable Cyclone", "battlefield")
    put(s, "Test Small", "library", position="top")
    put(s, "Forest", "library", position="top")
    put(s, cycler, "hand")
    mana(s, C=1)
    hand = len([c for c in s.state.cards.values() if c.zone == "p1:hand"])
    act(s, "p1", type="activate_ability", card_id=find(s, cycler).id, ability=ability)
    return s, hand


def _settle(s):
    for _ in range(20):
        d = s.state.rules.decision
        if d is not None:
            return d
        if not s.state.zones.get("stack"):
            return None
        act(s, s.state.rules.priority, type="pass_priority")


def _lib(s):
    return [c for c in s.state.cards.values() if c.zone == "p1:library"]


def _hand(s):
    return len([c for c in s.state.cards.values() if c.zone == "p1:hand"])


@pytest.mark.parametrize("cast", [True, False])
def test_cyclone_exiles_until_a_shared_type_and_may_cast_it(cards, card_db3, cast):
    """614.1a / 702.29a: Forest is exiled, then the creature found shares the cycled creature's type; cast free or not, the rest go to the bottom."""
    s, hand = _cycle_setup(cards, "Test Cycler")
    d = _settle(s)
    assert d is not None

    act(s, d.player, type="choose", decision_id=d.id, option_ids=[d.options[0].id] if cast else [])
    answer(s)
    zone = {c.name: c.zone for c in s.state.cards.values() if c.name in ("Test Small", "Forest")}
    assert _hand(s) == hand - 1  # the cycler left; nothing was drawn
    assert zone["Test Small"] == ("p1:battlefield" if cast else "p1:library")
    assert any(c.name == "Forest" and c.zone == "p1:library" for c in s.state.cards.values())
    roundtrip(s)


def test_cyclone_leaves_a_land_and_a_cycle_without_it_alone(cards, card_db3):
    """Only a nonland card's cycling is replaced; without a Cyclone the cycler draws (702.29a)."""
    for cycler, cyclone in (("Test Sandbar", True), ("Test Cycler", False)):
        s, hand = _cycle_setup(cards, cycler, cyclone, 1 if cycler == "Test Sandbar" else 0)
        assert _settle(s) is None
        assert _hand(s) == hand  # the cycler out, one drawn
        roundtrip(s)

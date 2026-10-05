"""Wave 25B: converge, "play a card", the Ring-bearer and cast-trigger conditions (CR 2026-09-25). Real Oracle text; every scenario
checks the replay and a save and a load.

* 701.18b: "whenever you play a card" - a land played or a spell cast.
* Converge: the colors of mana spent to cast the spell (601.2h) in a selector, a condition and a value; "Target player draws X cards,
  ~ deals X damage to any target, and you gain X life" (608.2c: each instruction in order, each with its own target).
* 701.54e: "if you don't control a Ring-bearer".  "If that spell has mana value 5 or greater" (cast triggers).
"""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import answer
from tests.wave9c_kit import build, card_named, check, life, mana, put, to_hand, zone_of

CARDS = [
    ("Recycle", "{4}{G}{G}", "Enchantment", None, None, "Skip your draw step.\nWhenever you play a card, draw a card.\nYour maximum hand size is two."),
    ("Together as One", "{6}", "Sorcery", None, None,
     "Converge — Target player draws X cards, Together as One deals X damage to any target, and you gain X life, where X is the number of "
     "colors of mana spent to cast this spell."),
    ("Dúnedain Rangers", "{3}{G}", "Creature — Human Ranger", "4", "4",
     "Landfall — Whenever a land you control enters, if you don't control a Ring-bearer, the Ring tempts you."),
    ("Prismari Apprentice", "{U}{R}", "Creature — Human Shaman", "2", "2",
     "Magecraft — Whenever you cast or copy an instant or sorcery spell, this creature can't be blocked this turn. If that spell has mana value 5 "
     "or greater, put a +1/+1 counter on this creature."),
    ("Prismatic Ending", "{X}{W}", "Sorcery", None, None,
     "Converge — Exile target nonland permanent if its mana value is less than or equal to the number of colors of mana spent to cast this spell."),
    ("Sundering Archaic", "{6}", "Creature — Avatar", "3", "3",
     "Converge — When this creature enters, exile target nonland permanent an opponent controls with mana value less than or equal to the number "
     "of colors of mana spent to cast this creature.\n{2}: Put target card from a graveyard on the bottom of its owner's library."),
    ("Probe Big Spell", "{4}{R}", "Sorcery", None, None, ""),
    ("Probe Small Spell", "{R}", "Sorcery", None, None, ""),
    ("Probe Two", "{1}{G}", "Creature — Bear", "2", "2", ""),
    ("Probe Three", "{2}{G}", "Creature — Bear", "3", "3", ""),
]
EXTRA = [card(n, set_code="t25b", number=f"C{i:02d}", mana_cost=mc, cmc=float(sum(1 for _ in mc.replace("{X}", "").split("}")) - 1), type_line=tl,
              colors=[], color_identity=[], oracle_text=text, power=p, toughness=t)
         for i, (n, mc, tl, p, t, text) in enumerate(CARDS)]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def level(name):
    c = next(c for c in EXTRA if c["name"] == name)
    return coverage.of_card_data({**c, "faces": c.get("card_faces") or []}).level


@pytest.mark.parametrize("name", [c[0] for c in CARDS if not c[0].startswith("Probe")])
def test_cards_are_full(name):
    assert level(name) == "FULL", name


def hand_size(s, pid="p1"):
    return len(s.state.zones[f"{pid}:hand"])


def test_recycle_draws_for_a_land_played_and_for_a_spell_cast(cards):
    s = build(cards, ["Recycle", "Probe Two"], forests=12)
    act(s, "p1", type="move", card_ids=[card_named(s, "Recycle").id], to={"player": "p1", "zone": "battlefield"})
    forest = next(c for c in s.state.zones["p1:library"] if s.state.cards[c].name == "Forest")
    act(s, "p1", type="move", card_ids=[forest], to={"player": "p1", "zone": "hand"})
    before = hand_size(s)
    act(s, "p1", type="play_land", card_id=forest)
    answer(s)
    assert hand_size(s) == before  # (one card left the hand, one was drawn)
    probe = to_hand(s, "Probe Two")
    mana(s, G=2)
    before = hand_size(s)
    act(s, "p1", type="cast_spell", card_id=probe.id)
    answer(s)
    assert hand_size(s) == before  # (the spell left the hand: -1, the trigger drew: +1)
    check(s)


def test_converge_with_three_targets_and_three_amounts(cards):
    """Together as One: X is the number of colors of mana spent (601.2h); each of the three instructions reads it."""
    s = build(cards, ["Together as One"])
    to_hand(s, "Together as One")
    mana(s, W=2, U=2, R=2)  # three colors
    hand_before, life_before, bob_life = hand_size(s, "p2"), life(s), life(s, "p2")
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Together as One").id)
    answer(s, "p2", "p2")  # (the player who draws, then the any target: one decision each, 601.2c)
    assert hand_size(s, "p2") == hand_before + 3 and life(s, "p2") == bob_life - 3 and life(s) == life_before + 3
    check(s)


@pytest.mark.parametrize("pay,exiled", [({"W": 1, "U": 1, "G": 1, "R": 1}, True), ({"W": 4}, False)])
def test_prismatic_ending_exiles_only_a_permanent_whose_mana_value_is_at_most_the_colors_spent(cards, pay, exiled):
    s = build(cards, ["Prismatic Ending"], ["Probe Three"])
    victim = put(s, "Probe Three", "p2")  # mana value 3
    to_hand(s, "Prismatic Ending")
    mana(s, **pay)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Prismatic Ending").id, targets=[victim.id], x_value=3)
    answer(s)
    assert zone_of(s, "Probe Three", "p2") == ("p2:exile" if exiled else "p2:battlefield")
    check(s)


@pytest.mark.parametrize("pay,exiled", [({"W": 3, "U": 3}, False), ({"W": 2, "U": 2, "R": 2}, True)])
def test_sundering_archaic_exiles_by_the_colors_spent(cards, pay, exiled):
    s = build(cards, ["Sundering Archaic"], ["Probe Three"])
    victim = put(s, "Probe Three", "p2")  # mana value 3
    to_hand(s, "Sundering Archaic")
    mana(s, **pay)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Sundering Archaic").id)
    answer(s, victim.id)
    assert zone_of(s, "Probe Three", "p2") == ("p2:exile" if exiled else "p2:battlefield")
    check(s)


def test_the_ring_tempts_you_only_while_you_control_no_ring_bearer(cards):
    s = build(cards, ["Dúnedain Rangers"], forests=14)
    act(s, "p1", type="move", card_ids=[card_named(s, "Dúnedain Rangers").id], to={"player": "p1", "zone": "battlefield"})
    forest = next(c for c in s.state.zones["p1:library"] if s.state.cards[c].name == "Forest")
    act(s, "p1", type="move", card_ids=[forest], to={"player": "p1", "zone": "hand"})
    act(s, "p1", type="play_land", card_id=forest)
    answer(s)
    assert s.state.rules.ring_tempted.get("p1") == 1 and s.state.rules.ring_bearers.get("p1")  # (the Rangers is the Ring-bearer now)
    forest2 = next(c for c in s.state.zones["p1:library"] if s.state.cards[c].name == "Forest")
    act(s, "p1", type="move", card_ids=[forest2], to={"player": "p1", "zone": "battlefield"})  # (entering by any means: landfall)
    answer(s)
    assert s.state.rules.ring_tempted.get("p1") == 1  # (it controls a Ring-bearer: the intervening "if" fails, 603.4)
    check(s)


@pytest.mark.parametrize("spell,counters", [("Probe Big Spell", 1), ("Probe Small Spell", 0)])
def test_magecraft_if_that_spell_has_mana_value_five_or_greater(cards, spell, counters):
    s = build(cards, ["Prismari Apprentice", spell])
    put(s, "Prismari Apprentice")
    to_hand(s, spell)
    mana(s, R=5)
    act(s, "p1", type="cast_spell", card_id=card_named(s, spell).id)
    answer(s)
    assert sum(s.state.cards[card_named(s, "Prismari Apprentice").id].counters.values()) == counters
    check(s)

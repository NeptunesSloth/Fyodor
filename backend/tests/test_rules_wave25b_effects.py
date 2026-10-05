"""Wave 25B: instruction wordings (CR 2026-09-25). Real Oracle text; every scenario checks the replay and a save and a load.

* 608.2c: one subject doing several things in order - "Target opponent sacrifices a creature or planeswalker of their choice, discards a
  card, and loses 3 life" (each instruction on its own, the one word "target" naming one player, 115.3).
* "... you gain 1 life and ~ deals 1 damage to target player" - each half read on its own.
* 603.10a / 400.7: "When this creature dies, return this card to its owner's hand": the card it is now.
* 608.2h: "if it was a creature" is read as the permanent last existed (an animated artifact).
* 401.4: "put the cards in your hand on the bottom of your library in any order, then draw that many cards" - the owner's private order,
  and "that many" is the cards put there.
"""

from __future__ import annotations

import pytest

from app.rules import coverage
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import answer
from tests.wave9c_kit import build, card_named, check, life, mana, put, to_hand, zone_of

CARDS = [
    ("Archon of Cruelty", "{6}{B}{B}", "Creature — Archon", "6", "6",
     "Flying\nWhenever this creature enters or attacks, target opponent sacrifices a creature or planeswalker of their choice, discards a card, "
     "and loses 3 life. You draw a card and gain 3 life."),
    ("Axelrod Gunnarson", "{4}{B}{B}{R}{R}", "Legendary Creature — Giant", "5", "5",
     "Trample\nWhenever a creature dealt damage by Axelrod Gunnarson this turn dies, you gain 1 life and Axelrod Gunnarson deals 1 damage to "
     "target player or planeswalker."),
    ("Weatherseed Totem", "{3}", "Artifact", None, None,
     "{T}: Add {G}.\n{2}{G}{G}{G}: This artifact becomes a 5/3 green Treefolk artifact creature with trample until end of turn.\n"
     "When this artifact is put into a graveyard from the battlefield, if it was a creature, return this card to its owner's hand."),
    ("Mindmoil", "{4}{R}", "Enchantment", None, None,
     "Whenever you cast a spell, put the cards in your hand on the bottom of your library in any order, then draw that many cards."),
    ("Teferi's Puzzle Box", "{4}", "Artifact", None, None,
     "At the beginning of each player's draw step, that player puts the cards in their hand on the bottom of their library in any order, then "
     "draws that many cards."),
    ("Rising Waters", "{3}{U}", "Enchantment", None, None,
     "Lands don't untap during their controllers' untap steps.\nAt the beginning of each player's upkeep, that player untaps a land they control."),
    ("Gruff Triplets", "{3}{G}{G}{G}", "Creature — Satyr Warrior", "3", "3",
     "Trample\nWhen this creature enters, if it isn't a token, create two tokens that are copies of it.\n"
     "When this creature dies, put a number of +1/+1 counters equal to its power on each creature you control named Gruff Triplets."),
    ("Presumed Dead", "{1}{B}", "Instant", None, None,
     "Until end of turn, target creature gets +2/+0 and gains \"When this creature dies, return it to the battlefield under its owner's control "
     "and suspect it.\" (A suspected creature has menace and can't block.)"),
    ("Probe Dummy", "{1}", "Creature — Bear", "1", "1", ""),
    ("Probe Tough", "{3}", "Creature — Wall", "0", "4", ""),
]
EXTRA = [card(n, set_code="t25b", number=f"E{i:02d}", mana_cost=mc, cmc=float(sum(1 for _ in mc.split("}")) - 1), type_line=tl,
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


def test_archon_of_cruelty_makes_the_opponent_sacrifice_discard_and_lose_life_while_you_draw_and_gain(cards):
    s = build(cards, ["Archon of Cruelty"], ["Probe Dummy", "Probe Tough"])
    put(s, "Probe Dummy", "p2")
    to_hand(s, "Probe Tough", "p2")
    to_hand(s, "Archon of Cruelty")
    mana(s, B=8)
    bob_hand, my_hand, my_life, bob_life = hand_size(s, "p2"), hand_size(s) - 1, life(s), life(s, "p2")
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Archon of Cruelty").id)
    answer(s)
    assert zone_of(s, "Probe Dummy", "p2") == "p2:graveyard"  # (their only creature: sacrificed)
    assert hand_size(s, "p2") == bob_hand - 1 and life(s, "p2") == bob_life - 3  # (one card discarded, 3 life lost)
    assert hand_size(s) == my_hand + 1 and life(s) == my_life + 3  # ("You draw a card and gain 3 life.")
    check(s)


def test_a_two_part_instruction_with_the_source_as_the_second_subject():
    """Axelrod Gunnarson: "you gain 1 life and Axelrod Gunnarson deals 1 damage to target player or planeswalker": two instructions in order."""
    from app.rules import scripts
    from app.rules.characteristics import printed_from_data

    c = next(c for c in EXTRA if c["name"] == "Axelrod Gunnarson")
    ch = printed_from_data({**c, "faces": []}, 0)
    (trigger,) = [d for d in scripts.definitions(ch).values() if d["kind"] == "triggered"]
    assert [e["do"] for e in trigger["effects"]] == ["gain_life", "damage"]


def test_weatherseed_totem_returns_to_hand_only_if_it_was_a_creature(cards):
    s = build(cards, ["Weatherseed Totem", "Lightning Bolt"])
    totem = put(s, "Weatherseed Totem")
    ch = Plan(s.state, "p1", s.cards, None).ch(card_named(s, "Weatherseed Totem"))
    ab = next(a for a in ch.abilities if a.kind == "activated" and "Treefolk" in a.text)
    mana(s, G=5)
    act(s, "p1", type="activate_ability", card_id=totem.id, ability=ab.index)
    answer(s)
    assert Plan(s.state, "p1", s.cards, None).ch(s.state.cards[totem.id]).is_creature
    to_hand(s, "Lightning Bolt")
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Lightning Bolt").id, targets=[totem.id])
    answer(s)
    assert zone_of(s, "Weatherseed Totem") == "p1:hand"  # (it was a 5/3 creature as it was put into the graveyard: 608.2h)
    check(s)


def test_mindmoil_puts_the_hand_on_the_bottom_in_the_order_chosen_and_draws_that_many(cards):
    s = build(cards, ["Mindmoil", "Probe Dummy", "Probe Tough", "Lightning Bolt"])
    put(s, "Mindmoil")
    cast_me = to_hand(s, "Probe Dummy")
    tough, bolt = to_hand(s, "Probe Tough"), to_hand(s, "Lightning Bolt")
    mana(s, G=1)
    act(s, "p1", type="cast_spell", card_id=cast_me.id)
    d = s.state.rules.decision
    assert d is not None and d.kind == "order" and d.player == "p1" and len(d.options) == 2  # (the two cards left in the hand)
    top_before = s.state.zones["p1:library"][:2]
    answer(s, [bolt.id, tough.id])  # (the first chosen ends at the very bottom, 401.4)
    library = s.state.zones["p1:library"]
    assert library[-1] == bolt.id and library[-2] == tough.id
    hand = s.state.zones["p1:hand"]
    assert len(hand) == 2 and set(hand) == set(top_before)  # (two cards drawn: the two that were on top)
    check(s)


def test_mindmoil_with_one_card_in_hand_asks_no_order(cards):
    s = build(cards, ["Mindmoil", "Probe Dummy", "Probe Tough"])
    put(s, "Mindmoil")
    cast_me = to_hand(s, "Probe Dummy")
    other = to_hand(s, "Probe Tough")
    mana(s, G=1)
    act(s, "p1", type="cast_spell", card_id=cast_me.id)
    assert s.state.rules.decision is None or s.state.rules.decision.kind != "order"  # (one card: nothing to order)
    answer(s)
    assert other.id in s.state.zones["p1:library"] and len(s.state.zones["p1:hand"]) == 1
    check(s)


def test_each_player_untaps_one_land_of_their_own_choice_in_their_upkeep(cards):
    """Rising Waters: "that player untaps a land they control" - that player (not the enchantment's controller) chooses which (608.2d)."""
    s = build(cards, ["Rising Waters"])
    put(s, "Rising Waters")
    islands = [c for c in s.state.zones["p2:library"] if s.state.cards[c].name == "Island"][:3]
    for c in islands:
        act(s, "p2", type="move", card_ids=[c], to={"player": "p2", "zone": "battlefield"})
    act(s, "p2", type="tap", card_ids=islands)
    for _ in range(60):  # on to Bob's turn: his lands don't untap in his untap step, but his upkeep trigger lets him untap one
        d = s.state.rules.decision
        if d is not None and d.player == "p2" and d.kind == "choose_cards":
            break
        act(s, s.state.rules.priority or "p1", type="pass_priority") if d is None else answer(s)
    d = s.state.rules.decision
    assert d is not None and d.player == "p2" and {o.id for o in d.options} == set(islands)
    act(s, "p2", type="choose", decision_id=d.id, option_ids=[islands[1]])
    answer(s)
    assert [s.state.cards[c].tapped for c in islands] == [True, False, True]
    check(s)


def test_gruff_triplets_dying_puts_counters_equal_to_its_power_on_each_creature_named_gruff_triplets(cards):
    s = build(cards, ["Gruff Triplets", "Lightning Bolt", "Probe Dummy"])
    dying = put(s, "Gruff Triplets")
    # a second creature with the same name (a token copy, 201.2): made by the table's token tool
    act(s, "p1", type="create_token", player="p1", token={"name": "Gruff Triplets", "type_line": "Token Creature — Satyr Warrior", "power": "3",
                                                            "toughness": "3", "text": ""})
    twin = next(c for c in s.state.cards.values() if c.is_token and c.name == "Gruff Triplets")
    dummy = put(s, "Probe Dummy")
    to_hand(s, "Lightning Bolt")
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Lightning Bolt").id, targets=[dying.id])
    answer(s)
    assert zone_of(s, "Gruff Triplets") == "p1:graveyard"
    assert sum(s.state.cards[twin.id].counters.values()) == 3  # (its power as it died: 3)
    assert sum(s.state.cards[dummy.id].counters.values()) == 0  # (only creatures named Gruff Triplets)
    check(s)

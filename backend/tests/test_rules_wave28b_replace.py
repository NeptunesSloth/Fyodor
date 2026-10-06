"""Wave 28B: draw replacements with a body ("If you would draw a card, instead <effects>") and life-loss modifiers.
Real Oracle wording (the local card database, current), replay and save/load for each scenario.

* 121.6, 614.11: an effect that replaces a card draw applies even with an empty library; 121.6b / 614.11a: its actions are
  completed before the sequence of draws goes on; 121.2: "draw N" is N separate draws, each replaced on its own.
* 614.5: a replacement effect applies once to an event and the events that modify it (a draw inside the replacement
  isn't replaced by the same effect again); 614.6: a replaced draw never happens (no "drew" event).
* 121.5: cards moved from a library to a hand without "draw" are not drawn.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.cards.importer import build_database
from app.config import Settings
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_effects import mana
from tests.test_rules_wave9b_exile_permission import answer, build, find, put, roundtrip

EXTRA = [
    card("Underrealm Lich", set_code="tst", number="W01", mana_cost="{3}{B}{G}", cmc=5.0, type_line="Creature — Zombie Elf Shaman", power="4", toughness="3", colors=["B", "G"], color_identity=["B", "G"], oracle_text="If you would draw a card, instead look at the top three cards of your library, then put one into your hand and the rest into your graveyard.\nPay 4 life: This creature gains indestructible until end of turn. Tap it."),  # noqa: E501
    card("Eruth, Tormented Prophet", set_code="tst", number="W02", mana_cost="{1}{U}{R}", cmc=3.0, type_line="Legendary Creature — Human Wizard", power="2", toughness="4", colors=["R", "U"], color_identity=["R", "U"], oracle_text="If you would draw a card, exile the top two cards of your library instead. You may play those cards this turn."),  # noqa: E501
    card("Blood Scrivener", set_code="tst", number="W03", mana_cost="{1}{B}", cmc=2.0, type_line="Creature — Zombie Wizard", power="2", toughness="1", colors=["B"], color_identity=["B"], oracle_text="If you would draw a card while you have no cards in hand, instead you draw two cards and you lose 1 life."),  # noqa: E501
    card("Phial of Galadriel", set_code="tst", number="W04", mana_cost="{3}", cmc=3.0, type_line="Legendary Artifact", oracle_text="If you would draw a card while you have no cards in hand, draw two cards instead.\nIf you would gain life while you have 5 or less life, you gain twice that much life instead.\n{T}: Add one mana of any color."),  # noqa: E501
    card("Enduring Renewal", set_code="tst", number="W05", mana_cost="{2}{W}{W}", cmc=4.0, type_line="Enchantment", colors=["W"], color_identity=["W"], oracle_text="Play with your hand revealed.\nIf you would draw a card, reveal the top card of your library instead. If it's a creature card, put it into your graveyard. Otherwise, draw a card.\nWhenever a creature is put into your graveyard from the battlefield, return it to your hand."),  # noqa: E501
    card("Obstinate Familiar", set_code="tst", number="W06", mana_cost="{R}", cmc=1.0, type_line="Creature — Lizard", power="1", toughness="1", colors=["R"], color_identity=["R"], oracle_text="If you would draw a card, you may skip that draw instead."),  # noqa: E501
    card("Forbidden Crypt", set_code="tst", number="W07", mana_cost="{3}{B}{B}", cmc=5.0, type_line="Enchantment", colors=["B"], color_identity=["B"], oracle_text="If you would draw a card, return a card from your graveyard to your hand instead. If you can't, you lose the game.\nIf a card would be put into your graveyard from anywhere, exile that card instead."),  # noqa: E501
    card("Bloodletter of Aclazotz", set_code="tst", number="W08", mana_cost="{1}{B}{B}{B}", cmc=4.0, type_line="Creature — Vampire Demon", power="2", toughness="4", colors=["B"], color_identity=["B"], oracle_text="Flying\nIf an opponent would lose life during your turn, they lose twice that much life instead. (Damage causes loss of life.)", keywords=["Flying"]),  # noqa: E501
    card("Tomorrow, Azami's Familiar", set_code="tst", number="W11", mana_cost="{5}{U}", cmc=6.0, type_line="Legendary Creature — Spirit", power="1", toughness="5", colors=["U"], color_identity=["U"], oracle_text="If you would draw a card, look at the top three cards of your library instead. Put one of those cards into your hand and the rest on the bottom of your library in any order."),  # noqa: E501
    card("Sages of the Anima", set_code="tst", number="W12", mana_cost="{3}{G}{U}", cmc=5.0, type_line="Creature — Elf Wizard", power="3", toughness="4", colors=["G", "U"], color_identity=["G", "U"], oracle_text="If you would draw a card, instead reveal the top three cards of your library. Put all creature cards revealed this way into your hand and the rest on the bottom of your library in any order."),  # noqa: E501
    card("Out of the Tombs", set_code="tst", number="W13", mana_cost="{2}{B}", cmc=3.0, type_line="Enchantment", colors=["B"], color_identity=["B"], oracle_text="At the beginning of your upkeep, put two eon counters on this enchantment, then mill cards equal to the number of eon counters on it.\nIf you would draw a card while your library has no cards in it, instead return a creature card from your graveyard to the battlefield. If you can't, you lose the game."),  # noqa: E501
    card("Pursuit of Knowledge", set_code="tst", number="W14", mana_cost="{3}{W}", cmc=4.0, type_line="Enchantment", colors=["W"], color_identity=["W"], oracle_text="If you would draw a card, you may put a study counter on this enchantment instead.\nRemove three study counters from this enchantment, Sacrifice this enchantment: Draw seven cards."),  # noqa: E501
    card("Vampire's Kiss", set_code="tst", number="W15", mana_cost="{1}{B}", cmc=2.0, type_line="Sorcery", colors=["B"], color_identity=["B"], oracle_text="Target player loses 2 life and you gain 2 life."),  # noqa: E501
    card("Greed", set_code="tst", number="W16", mana_cost="{3}{B}", cmc=4.0, type_line="Enchantment", colors=["B"], color_identity=["B"], oracle_text="{B}, Pay 2 life: Draw a card."),  # noqa: E501
    card("Boon Reflection", set_code="tst", number="W17", mana_cost="{4}{W}", cmc=5.0, type_line="Enchantment", colors=["W"], color_identity=["W"], oracle_text="If you would gain life, you gain twice that much life instead."),  # noqa: E501
    card("Thought Scour", set_code="tst", number="W18", mana_cost="{U}", cmc=1.0, type_line="Instant", colors=["U"], color_identity=["U"], oracle_text="Target player mills two cards.\nDraw a card."),  # noqa: E501
    card("Bruvac the Grandiloquent", set_code="tst", number="W19", mana_cost="{2}{U}", cmc=3.0, type_line="Legendary Creature — Human Advisor", power="1", toughness="4", colors=["U"], color_identity=["U"], oracle_text="If an opponent would mill one or more cards, they mill twice that many cards instead. (To mill a card, a player puts the top card of their library into their graveyard.)"),  # noqa: E501
    card("The Water Crystal", set_code="tst", number="W20", mana_cost="{2}{U}{U}", cmc=4.0, type_line="Legendary Artifact", colors=["U"], color_identity=["U"], oracle_text="Blue spells you cast cost {1} less to cast.\nIf an opponent would mill one or more cards, they mill that many cards plus four instead.\n{4}{U}{U}, {T}: Each opponent mills cards equal to the number of cards in your hand."),  # noqa: E501
    card("Faerie Vandal", set_code="tst", number="W21", mana_cost="{1}{U}", cmc=2.0, type_line="Creature — Faerie Rogue", power="1", toughness="2", colors=["U"], color_identity=["U"], keywords=["Flying", "Flash"], oracle_text="Flash (You may cast this spell any time you could cast an instant.)\nFlying\nWhenever you draw your second card each turn, put a +1/+1 counter on this creature."),  # noqa: E501
    card("Words of Worship", set_code="tst", number="W22", mana_cost="{2}{W}", cmc=3.0, type_line="Enchantment", colors=["W"], color_identity=["W"], oracle_text="{1}: The next time you would draw a card this turn, you gain 5 life instead."),  # noqa: E501
    card("Words of Wilding", set_code="tst", number="W23", mana_cost="{2}{G}", cmc=3.0, type_line="Enchantment", colors=["G"], color_identity=["G"], oracle_text="{1}: The next time you would draw a card this turn, create a 2/2 green Bear creature token instead."),  # noqa: E501
    card("Words of Waste", set_code="tst", number="W24", mana_cost="{2}{B}", cmc=3.0, type_line="Enchantment", colors=["B"], color_identity=["B"], oracle_text="{1}: The next time you would draw a card this turn, each opponent discards a card instead."),  # noqa: E501
    card("Quantum Riddler", set_code="tst", number="W25", mana_cost="{3}{U}{U}", cmc=5.0, type_line="Creature — Sphinx", power="4", toughness="6", colors=["U"], color_identity=["U"], keywords=["Flying", "Warp"], oracle_text="Flying\nWhen this creature enters, draw a card.\nAs long as you have one or fewer cards in hand, if you would draw one or more cards, you draw that many cards plus one instead.\nWarp {1}{U}"),  # noqa: E501
    card("Alms Collector", set_code="tst", number="W26", mana_cost="{3}{W}", cmc=4.0, type_line="Creature — Cat Cleric", power="3", toughness="4", colors=["W"], color_identity=["W"], keywords=["Flash"], oracle_text="Flash\nIf an opponent would draw two or more cards, instead you and that player each draw a card."),  # noqa: E501
    card("Sign in Blood", set_code="tst", number="W27", mana_cost="{B}{B}", cmc=2.0, type_line="Sorcery", colors=["B"], color_identity=["B"], oracle_text="Target player draws two cards and loses 2 life."),  # noqa: E501
    card("Test Small", set_code="tst", number="W10", mana_cost="{G}", cmc=1.0, type_line="Creature — Elf", power="2", toughness="2", colors=["G"], color_identity=["G"], oracle_text=""),  # noqa: E501
    card("Divination", set_code="tst", number="W09", mana_cost="{2}{U}", cmc=3.0, type_line="Sorcery", colors=["U"], color_identity=["U"], oracle_text="Draw two cards."),  # noqa: E501
]
FULL = [c["name"] for c in EXTRA if c["name"] not in ("Divination", "Test Small", "Vampire's Kiss", "Greed", "Boon Reflection", "Thought Scour", "Faerie Vandal", "Sign in Blood")]


@pytest.fixture()
def card_db(settings: Settings) -> Path:
    settings.ensure_dirs()
    names = {c["name"] for c in fixture_cards()}
    build_database(fixture_cards() + [c for c in EXTRA if c["name"] not in names], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def zone(s, name, pid="p1"):
    return s.state.zones.get(f"{pid}:{name}", [])


def cast_divination(cards, *others, hand_empty=False):
    s = build(cards, p1=("Divination", *others))
    c = put(s, "Divination", "hand")
    mana(s, C=2, U=1)
    act(s, "p1", type="cast_spell", card_id=c.id)
    return s


@pytest.mark.parametrize("name", FULL)
def test_coverage_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def test_underrealm_lich_replaces_each_draw_of_a_sequence_with_its_own_look(cards):
    s = build(cards, p1=("Divination", "Underrealm Lich"))
    put(s, "Underrealm Lich", "battlefield")
    c = put(s, "Divination", "hand")
    mana(s, C=2, U=1)
    hand, lib, gy = len(zone(s, "hand")), len(zone(s, "library")), len(zone(s, "graveyard"))
    top = list(zone(s, "library")[:6])
    act(s, "p1", type="cast_spell", card_id=c.id)
    d = s.state.rules.decision
    assert d is not None and d.player == "p1" and [o.card_id for o in d.options] == top[:3]  # 121.6b: the first draw's look
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[d.options[1].id])
    d = s.state.rules.decision
    assert d is not None and [o.card_id for o in d.options] == [x for x in zone(s, "library")[:3]]  # then the second draw's own look
    assert top[1] in zone(s, "hand") and top[0] in zone(s, "graveyard") and top[2] in zone(s, "graveyard")
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[d.options[0].id])
    answer(s)
    assert len(zone(s, "hand")) == hand - 1 + 2 and len(zone(s, "library")) == lib - 6  # (Divination left the hand)
    assert len(zone(s, "graveyard")) == gy + 4 + 1  # four not chosen, and Divination itself
    assert s.state.rules.turn_log.drew.get("p1", 0) == 0  # 614.6: the draws never happened, 121.5: nothing was drawn
    roundtrip(s)


def settle(s, pick=None, limit=40):
    """Resolve the stack, answering decisions with ``pick(decision)`` (option ids) or the first option."""
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None:
            ids = (pick(d) if pick else None) or [o.id for o in d.options][: max(1, d.min_choices)]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=ids)
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return
    raise AssertionError("never settled")


def empty_hand(s, keep):
    for x in list(zone(s, "hand")):
        if x != keep:
            act(s, "p1", type="move", card_ids=[x], to={"player": "p1", "zone": "graveyard"})


def to_draw_step_of_p1(s, limit=60):
    """Pass priority until p1's next draw step (turn 3): a decision of the replacement stops the walk."""
    for _ in range(limit):
        if s.state.rules.decision is not None or (s.state.turn.number == 3 and s.state.turn.phase == "draw"):
            return
        act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("no draw step")


def test_a_draw_step_draw_is_replaced_and_the_step_goes_on_afterwards(cards):
    s = build(cards, p1=("Underrealm Lich",))
    put(s, "Underrealm Lich", "battlefield")
    top = list(zone(s, "library")[:3])
    to_draw_step_of_p1(s)
    d = s.state.rules.decision
    assert d is not None and d.player == "p1" and [o.card_id for o in d.options] == top  # 504.1: the turn-based draw, replaced (121.6)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[d.options[2].id])
    assert top[2] in zone(s, "hand") and top[0] in zone(s, "graveyard")
    for _ in range(3):  # (the step goes on: the turn reaches its main phase with priority)
        if s.state.turn.phase == "main1":
            break
        act(s, s.state.rules.priority, type="pass_priority")
    assert s.state.turn.phase == "main1" and s.state.turn.number == 3
    roundtrip(s)


def test_a_replaced_draw_with_an_empty_library_still_happens_and_nobody_loses(cards):
    s = build(cards, p1=("Divination", "Underrealm Lich"))
    put(s, "Underrealm Lich", "battlefield")
    act(s, "p1", type="move", card_ids=list(zone(s, "library")), to={"player": "p1", "zone": "exile"})
    c = put(s, "Divination", "hand")
    mana(s, C=2, U=1)
    act(s, "p1", type="cast_spell", card_id=c.id)
    settle(s)
    assert "p1" not in s.state.rules.lost and "p1" not in s.state.rules.drew_from_empty  # 121.6a / 614.11: replaced, so no draw was attempted
    roundtrip(s)


def test_two_draw_replacements_are_ordered_by_the_player(cards):
    s = build(cards, p1=("Divination", "Underrealm Lich", "Eruth, Tormented Prophet"))
    put(s, "Underrealm Lich", "battlefield")
    put(s, "Eruth, Tormented Prophet", "battlefield")
    c = put(s, "Divination", "hand")
    mana(s, C=2, U=1)
    act(s, "p1", type="cast_spell", card_id=c.id)
    d = s.state.rules.decision
    assert d is not None and d.player == "p1" and "which applies first" in d.prompt.lower() or "apply" in d.prompt.lower()  # 616.1
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[d.options[0].id])
    settle(s)  # (whichever applied first replaced the draw; the other one found nothing left to replace: 614.5 / 614.6)
    assert s.state.rules.turn_log.drew.get("p1", 0) == 0
    roundtrip(s)


def test_eruth_exiles_two_for_each_draw_and_they_can_be_played_this_turn(cards):
    s = build(cards, p1=("Divination", "Eruth, Tormented Prophet"))
    put(s, "Eruth, Tormented Prophet", "battlefield")
    c = put(s, "Divination", "hand")
    mana(s, C=2, U=1)
    hand, lib = len(zone(s, "hand")), len(zone(s, "library"))
    top = list(zone(s, "library")[:4])
    act(s, "p1", type="cast_spell", card_id=c.id)
    settle(s)
    assert len(zone(s, "hand")) == hand - 1 and len(zone(s, "library")) == lib - 4  # Divination left the hand; nothing was drawn
    assert [x for x in top if x in zone(s, "exile")] == top  # 121.6b: two exiled for the first draw, two for the second
    assert s.state.rules.turn_log.drew.get("p1", 0) == 0
    land = next(x for x in top if s.state.cards[x].name == "Forest")  # "You may play those cards this turn"
    act(s, "p1", type="play_land", card_id=land)
    assert s.state.cards[land].zone == "p1:battlefield"
    roundtrip(s)


def test_blood_scrivener_draws_two_and_loses_a_life_only_with_an_empty_hand(cards):
    s = build(cards, p1=("Divination", "Blood Scrivener"))
    put(s, "Blood Scrivener", "battlefield")
    c = put(s, "Divination", "hand")
    empty_hand(s, c.id)
    mana(s, C=2, U=1)
    life, lib = s.state.players["p1"].life, len(zone(s, "library"))
    act(s, "p1", type="cast_spell", card_id=c.id)
    settle(s)
    # draw 1: the hand is empty -> two cards and 1 life (the replacement doesn't apply to those two draws again, 614.5);
    # draw 2: the hand isn't empty any more -> an ordinary draw
    assert s.state.players["p1"].life == life - 1
    assert len(zone(s, "hand")) == 3 and len(zone(s, "library")) == lib - 3
    assert s.state.rules.turn_log.drew.get("p1", 0) == 3
    roundtrip(s)


def test_blood_scrivener_does_nothing_with_cards_in_hand(cards):
    s = build(cards, p1=("Divination", "Blood Scrivener", "Test Small"))
    put(s, "Blood Scrivener", "battlefield")
    c = put(s, "Divination", "hand")
    put(s, "Test Small", "hand")  # (the hand isn't empty)
    mana(s, C=2, U=1)
    life, hand = s.state.players["p1"].life, len(zone(s, "hand"))
    act(s, "p1", type="cast_spell", card_id=c.id)
    settle(s)
    assert s.state.players["p1"].life == life and len(zone(s, "hand")) == hand - 1 + 2
    roundtrip(s)


def test_phial_of_galadriel_draws_two_instead_of_one_with_an_empty_hand(cards):
    s = build(cards, p1=("Divination", "Phial of Galadriel"))
    put(s, "Phial of Galadriel", "battlefield")
    c = put(s, "Divination", "hand")
    empty_hand(s, c.id)
    mana(s, C=2, U=1)
    act(s, "p1", type="cast_spell", card_id=c.id)
    settle(s)
    assert len(zone(s, "hand")) == 3  # two instead of the first draw, then one ordinary draw (hand no longer empty)
    roundtrip(s)


def test_enduring_renewal_puts_a_revealed_creature_into_the_graveyard_else_draws_it(cards):
    s = build(cards, p1=("Divination", "Enduring Renewal", "Test Small"))
    put(s, "Enduring Renewal", "battlefield")
    creature = find(s, "Test Small").id
    act(s, "p1", type="move", card_ids=[creature], to={"player": "p1", "zone": "library"}, position="top")
    c = put(s, "Divination", "hand")
    mana(s, C=2, U=1)
    hand, size = len(zone(s, "hand")), len(zone(s, "library"))
    act(s, "p1", type="cast_spell", card_id=c.id)
    settle(s)
    assert s.state.cards[creature].zone == "p1:graveyard"  # revealed creature card: into the graveyard (the draw is gone)
    assert len(zone(s, "hand")) == hand - 1 + 1 and len(zone(s, "library")) == size - 2  # the second draw: a Forest, drawn
    roundtrip(s)


def test_obstinate_familiar_may_skip_a_draw(cards):
    s = build(cards, p1=("Divination", "Obstinate Familiar"))
    put(s, "Obstinate Familiar", "battlefield")
    c = put(s, "Divination", "hand")
    mana(s, C=2, U=1)
    hand = len(zone(s, "hand"))
    act(s, "p1", type="cast_spell", card_id=c.id)
    d = s.state.rules.decision
    assert d is not None and d.player == "p1" and {o.id for o in d.options} >= {"decline"}
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["o0"])  # skip the first draw
    d = s.state.rules.decision
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["decline"])  # draw the second normally
    settle(s)
    assert len(zone(s, "hand")) == hand - 1 + 1
    roundtrip(s)


def test_tomorrow_puts_one_card_in_hand_and_the_rest_on_the_bottom(cards):
    s = build(cards, p1=("Divination", "Tomorrow, Azami's Familiar"))
    put(s, "Tomorrow, Azami's Familiar", "battlefield")
    c = put(s, "Divination", "hand")
    mana(s, C=2, U=1)
    top = list(zone(s, "library")[:3])
    lib = len(zone(s, "library"))
    act(s, "p1", type="cast_spell", card_id=c.id)
    d = s.state.rules.decision
    assert d is not None and [o.card_id for o in d.options] == top
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[top[1]])
    settle(s)  # (the order of the other two on the bottom, then the second draw's own look)
    assert top[1] in zone(s, "hand") and len(zone(s, "library")) == lib - 2
    assert s.state.rules.turn_log.drew.get("p1", 0) == 0
    roundtrip(s)


def test_sages_of_the_anima_reveals_three_and_takes_the_creatures(cards):
    s = build(cards, p1=("Divination", "Sages of the Anima", "Test Small"))
    put(s, "Sages of the Anima", "battlefield")
    small = find(s, "Test Small").id
    act(s, "p1", type="move", card_ids=[small], to={"player": "p1", "zone": "library"}, position="top")
    c = put(s, "Divination", "hand")
    mana(s, C=2, U=1)
    hand = len(zone(s, "hand"))
    act(s, "p1", type="cast_spell", card_id=c.id)
    settle(s)
    assert s.state.cards[small].zone == "p1:hand"  # 121.5: put into the hand, not drawn
    assert len(zone(s, "hand")) == hand - 1 + 1  # the second draw's three cards held no creature
    roundtrip(s)


def test_pursuit_of_knowledge_puts_a_study_counter_instead_when_its_player_says_so(cards):
    s = build(cards, p1=("Divination", "Pursuit of Knowledge"))
    pk = put(s, "Pursuit of Knowledge", "battlefield")
    c = put(s, "Divination", "hand")
    mana(s, C=2, U=1)
    hand = len(zone(s, "hand"))
    act(s, "p1", type="cast_spell", card_id=c.id)
    d = s.state.rules.decision
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["o0"])  # the first draw: a study counter instead
    d = s.state.rules.decision
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["decline"])  # the second: draw it
    settle(s)
    assert s.state.cards[pk.id].counters.get("study") == 1 and len(zone(s, "hand")) == hand - 1 + 1
    roundtrip(s)


def test_out_of_the_tombs_returns_a_creature_instead_of_a_draw_from_an_empty_library(cards):
    s = build(cards, p1=("Divination", "Out of the Tombs", "Test Small"))
    put(s, "Out of the Tombs", "battlefield")
    small = put(s, "Test Small", "graveyard")
    act(s, "p1", type="move", card_ids=list(zone(s, "library")), to={"player": "p1", "zone": "exile"})
    c = put(s, "Divination", "hand")
    mana(s, C=2, U=1)
    act(s, "p1", type="cast_spell", card_id=c.id)
    settle(s)
    assert s.state.cards[small.id].zone == "p1:battlefield"  # the first draw; the second finds no creature card: 104.3e
    assert "p1" in s.state.rules.lost
    roundtrip(s)


def kiss(cards, *, bloodletter_for="p1", extra=()):
    s = build(cards, p1=("Vampire's Kiss", "Bloodletter of Aclazotz", "Lightning Bolt", *extra))
    put(s, "Bloodletter of Aclazotz", "battlefield", bloodletter_for)
    return s


def test_bloodletter_doubles_an_opponents_life_loss_during_its_controllers_turn(cards):
    s = kiss(cards)
    c = put(s, "Vampire's Kiss", "hand")
    mana(s, B=1, C=1)
    act(s, "p1", type="cast_spell", card_id=c.id, targets=["p2"])
    settle(s)
    assert s.state.players["p2"].life == 40 - 4  # 614.1a: "loses 2 life" -> twice that much
    assert s.state.players["p1"].life == 40 + 2  # (gaining life is untouched)
    roundtrip(s)


def test_bloodletter_does_not_change_the_damage_only_the_life_it_causes_to_be_lost(cards):
    s = kiss(cards)
    c = put(s, "Lightning Bolt", "hand")
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=c.id, targets=["p2"])
    settle(s)
    assert s.state.players["p2"].life == 40 - 6  # 120.3a: 3 damage dealt, 6 life lost
    assert any(e.kind == "damage" and e.amount == 3 for e in s.state.rules.events)
    roundtrip(s)


def test_bloodletter_does_not_double_its_controllers_own_loss(cards):
    s = kiss(cards)
    c = put(s, "Vampire's Kiss", "hand")
    mana(s, B=1, C=1)
    act(s, "p1", type="cast_spell", card_id=c.id, targets=["p1"])
    settle(s)
    assert s.state.players["p1"].life == 40 - 2 + 2
    roundtrip(s)


def test_bloodletter_does_nothing_during_the_turn_of_another_player(cards):
    s = build(cards, p1=("Vampire's Kiss",), p2=("Bloodletter of Aclazotz",))
    put(s, "Bloodletter of Aclazotz", "battlefield", "p2")
    c = put(s, "Vampire's Kiss", "hand")
    mana(s, B=1, C=1)
    act(s, "p1", type="cast_spell", card_id=c.id, targets=["p1"])
    settle(s)
    assert s.state.players["p1"].life == 40 - 2 + 2  # it is p1's turn, not the turn of Bloodletter's controller (p2): not doubled
    roundtrip(s)


def test_bloodletter_doubles_life_an_opponent_pays_as_a_cost_during_its_controllers_turn(cards):
    s = build(cards, p1=("Vampire's Kiss", "Bloodletter of Aclazotz"), p2=("Greed",))
    put(s, "Bloodletter of Aclazotz", "battlefield")
    greed = put(s, "Greed", "battlefield", "p2")
    c = put(s, "Vampire's Kiss", "hand")
    mana(s, B=1, C=1)
    mana(s, "p2", B=1)
    act(s, "p1", type="cast_spell", card_id=c.id, targets=["p1"])
    assert s.state.rules.priority == "p2" and s.state.zones.get("stack")
    ability = 0
    life = s.state.players["p2"].life
    act(s, "p2", type="activate_ability", card_id=greed.id, ability=ability)  # 119.4 / 118.11: "Pay 2 life" -> lose twice that much
    assert s.state.players["p2"].life == life - 4
    settle(s)
    roundtrip(s)


def test_bloodletter_doubles_the_life_lost_to_combat_damage_not_the_damage_dealt(cards):
    from tests.test_rules_wave5c_combat import attacking, declare, old, through_combat, to_attack
    from tests.test_rules_wave5c_combat import build as cbuild
    from tests.test_rules_wave5c_combat import put as cput

    s = cbuild(cards, "Bloodletter of Aclazotz")
    cput(s, "Bloodletter of Aclazotz")
    ogre = old(s, "p1", "Ogre", "3/3")
    to_attack(s)
    declare(s, (ogre, "p2"))
    assert attacking(s, ogre) == "p2"
    through_combat(s)
    assert s.state.players["p2"].life == 40 - 6  # 120.3a, 614.1a: 3 combat damage, 6 life lost
    assert any(e.kind == "damage" and e.amount == 3 for e in s.state.rules.events)
    roundtrip(s)


def test_a_replaced_draw_is_not_drawn_for_second_card_each_turn_triggers_but_the_replacements_own_draws_are(cards):
    s = build(cards, p1=("Divination", "Underrealm Lich", "Faerie Vandal"))
    put(s, "Underrealm Lich", "battlefield")
    vandal = put(s, "Faerie Vandal", "battlefield")
    c = put(s, "Divination", "hand")
    mana(s, C=2, U=1)
    act(s, "p1", type="cast_spell", card_id=c.id)
    settle(s)
    assert not s.state.cards[vandal.id].counters  # 614.6 / 121.5: two cards were put into the hand, none was drawn
    roundtrip(s)
    s = build(cards, p1=("Divination", "Blood Scrivener", "Faerie Vandal"))
    put(s, "Blood Scrivener", "battlefield")
    vandal = put(s, "Faerie Vandal", "battlefield")
    c = put(s, "Divination", "hand")
    empty_hand(s, c.id)
    mana(s, C=2, U=1)
    act(s, "p1", type="cast_spell", card_id=c.id)
    settle(s)
    assert s.state.cards[vandal.id].counters == {"+1/+1": 1}  # the two draws Blood Scrivener makes instead are real draws: the second one counts
    roundtrip(s)


@pytest.mark.parametrize("in_hand,drawn", [(0, 3), (1, 3), (2, 2)])
def test_quantum_riddler_adds_a_card_to_a_draw_instruction_while_it_has_one_or_fewer_cards_in_hand(cards, in_hand, drawn):
    s = build(cards, p1=("Divination", "Quantum Riddler", "Test Small"))
    put(s, "Quantum Riddler", "battlefield")
    c = put(s, "Divination", "hand")
    if in_hand:
        extra = [x for x in zone(s, "library") if s.state.cards[x].name == "Forest"][:in_hand]
        act(s, "p1", type="move", card_ids=extra, to={"player": "p1", "zone": "hand"})
    mana(s, C=2, U=1)
    hand = len(zone(s, "hand"))
    act(s, "p1", type="cast_spell", card_id=c.id)
    settle(s)
    assert len(zone(s, "hand")) == hand - 1 + drawn  # 121.2a, 616.1g: "draw two" becomes three; the count is changed once
    roundtrip(s)


def test_alms_collector_replaces_an_opponents_draw_of_two_or_more_cards(cards):
    s = build(cards, p1=("Alms Collector", "Sign in Blood"))
    put(s, "Alms Collector", "battlefield")
    c = put(s, "Sign in Blood", "hand")
    mana(s, B=2)
    mine, theirs, life = len(zone(s, "hand")), len(zone(s, "hand", "p2")), s.state.players["p2"].life
    act(s, "p1", type="cast_spell", card_id=c.id, targets=["p2"])
    settle(s)
    assert len(zone(s, "hand")) == mine - 1 + 1 and len(zone(s, "hand", "p2")) == theirs + 1  # you and that player each draw a card
    assert s.state.players["p2"].life == life - 2  # (the rest of the spell still happens, 121.7)
    roundtrip(s)


def test_alms_collector_ignores_a_single_draw_and_its_controllers_own_draw(cards):
    s = build(cards, p1=("Alms Collector", "Divination"))
    put(s, "Alms Collector", "battlefield")
    c = put(s, "Divination", "hand")
    mana(s, C=2, U=1)
    hand = len(zone(s, "hand"))
    act(s, "p1", type="cast_spell", card_id=c.id)
    settle(s)
    assert len(zone(s, "hand")) == hand - 1 + 2  # (an opponent's draw of two or more cards only)
    roundtrip(s)


def test_words_of_worship_replaces_only_the_next_draw_this_turn(cards):
    s = build(cards, p1=("Divination", "Words of Worship"))
    words = put(s, "Words of Worship", "battlefield")
    c = put(s, "Divination", "hand")
    mana(s, C=3, U=1)
    life, hand = s.state.players["p1"].life, len(zone(s, "hand"))
    act(s, "p1", type="activate_ability", card_id=words.id, ability=0)
    settle(s)
    roundtrip(s)  # (the replacement effect waits: it is part of the saved table)
    act(s, "p1", type="cast_spell", card_id=c.id)
    settle(s)
    assert s.state.players["p1"].life == life + 5  # 611.2a: the first draw is replaced…
    assert len(zone(s, "hand")) == hand - 1 + 1  # …the second is drawn: the effect was used up (614.5)
    roundtrip(s)


def test_each_activation_of_words_replaces_a_draw_of_its_own(cards):
    s = build(cards, p1=("Divination", "Words of Wilding"))
    words = put(s, "Words of Wilding", "battlefield")
    c = put(s, "Divination", "hand")
    mana(s, C=4, U=1)
    hand = len(zone(s, "hand"))
    for _ in range(2):
        act(s, "p1", type="activate_ability", card_id=words.id, ability=0)
        settle(s)
    act(s, "p1", type="cast_spell", card_id=c.id)
    settle(s)
    bears = [x for x in s.state.cards.values() if x.token and x.token.name == "Bear" and x.zone == "p1:battlefield"]
    assert len(bears) == 2 and len(zone(s, "hand")) == hand - 1  # both draws replaced, by one effect each
    roundtrip(s)


def test_words_of_waste_makes_each_opponent_discard_instead_of_the_draw(cards):
    s = build(cards, p1=("Divination", "Words of Waste"), p2=("Test Small",))
    words = put(s, "Words of Waste", "battlefield")
    put(s, "Test Small", "hand", "p2")
    c = put(s, "Divination", "hand")
    mana(s, C=3, U=1)
    act(s, "p1", type="activate_ability", card_id=words.id, ability=0)
    settle(s)
    act(s, "p1", type="cast_spell", card_id=c.id)
    settle(s)
    assert zone(s, "hand", "p2") == [] and find(s, "Test Small", "p2").zone == "p2:graveyard"
    roundtrip(s)


def test_doc_samson_adds_one_counter_of_each_kind_to_a_permanent_its_controller_puts_them_on(cards):
    from tests.test_rules_attachments import build as tbuild
    from tests.test_rules_attachments import token
    from tests.test_rules_replacements2 import activate, permanent

    s = tbuild(cards)
    permanent(s, "p1", "Samson", "Creature", "If you would put one or more counters on a permanent you control, put that many plus one of "
              "each of those kinds of counters on that permanent instead.")
    mine, theirs = token(s, "p1", "Bear"), token(s, "p2", "Wolf")
    feeder = token(s, "p1", "Feeder", text="{1}: Put a +1/+1 counter on target creature.")
    activate(s, feeder, targets=[mine.id])
    activate(s, feeder, targets=[theirs.id])  # a permanent its controller doesn't control: no change
    assert s.state.cards[mine.id].counters == {"+1/+1": 2} and s.state.cards[theirs.id].counters == {"+1/+1": 1}
    roundtrip(s)


def mill_two(cards, *permanents):
    s = build(cards, p1=("Thought Scour", *permanents))
    for name in permanents:
        put(s, name, "battlefield")
    c = put(s, "Thought Scour", "hand")
    mana(s, U=1, C=4)
    return s, c


@pytest.mark.parametrize("names,milled", [((), 2), (("Bruvac the Grandiloquent",), 4), (("The Water Crystal",), 6)])
def test_mill_counts_are_changed_for_an_opponent(cards, names, milled):
    s, c = mill_two(cards, *names)
    lib, gy = len(zone(s, "library", "p2")), len(zone(s, "graveyard", "p2"))
    act(s, "p1", type="cast_spell", card_id=c.id, targets=["p2"])
    settle(s)
    assert len(zone(s, "graveyard", "p2")) == gy + milled and len(zone(s, "library", "p2")) == lib - milled  # 701.17a, 614.1a
    roundtrip(s)


def test_mill_replacement_does_not_change_its_controllers_own_mill(cards):
    s, c = mill_two(cards, "Bruvac the Grandiloquent")
    gy = len(zone(s, "graveyard"))
    act(s, "p1", type="cast_spell", card_id=c.id, targets=["p1"])
    settle(s)
    assert len(zone(s, "graveyard")) == gy + 2 + 1  # (and Thought Scour itself)
    roundtrip(s)


@pytest.mark.parametrize("first,milled", [("Bruvac", 2 * 2 + 4), ("Water Crystal", (2 + 4) * 2)])
def test_two_mill_replacements_that_do_not_commute_are_ordered_by_the_player(cards, first, milled):
    s, c = mill_two(cards, "Bruvac the Grandiloquent", "The Water Crystal")
    lib = len(zone(s, "library", "p2"))
    act(s, "p1", type="cast_spell", card_id=c.id, targets=["p2"])
    d = s.state.rules.decision
    assert d is not None and d.player == "p2"  # 616.1: the affected player chooses: (2×2)+4 or (2+4)×2
    prompt_first = "Bruvac" if "apply Bruvac" in d.prompt else "Water Crystal"
    keep = d.options[0].id if prompt_first == first else d.options[1].id
    act(s, "p2", type="choose", decision_id=d.id, option_ids=[keep])
    settle(s)
    assert len(zone(s, "library", "p2")) == max(0, lib - milled)  # (a library of ten holds fewer than twelve)
    roundtrip(s)


def test_a_mill_that_exceeds_the_library_mills_what_is_there(cards):
    s, c = mill_two(cards, "Bruvac the Grandiloquent")
    act(s, "p2", type="move", card_ids=list(zone(s, "library", "p2"))[3:], to={"player": "p2", "zone": "exile"})
    act(s, "p1", type="cast_spell", card_id=c.id, targets=["p2"])
    settle(s)
    assert len(zone(s, "library", "p2")) == 0 and "p2" not in s.state.rules.lost  # (701.17a; a player loses only on a later draw, 704.5b)
    roundtrip(s)


@pytest.mark.parametrize("start,gained", [(5, 4), (6, 2), (40, 2)])
def test_phial_of_galadriel_doubles_a_gain_only_while_at_five_or_less_life(cards, start, gained):
    s = build(cards, p1=("Vampire's Kiss", "Phial of Galadriel"))
    put(s, "Phial of Galadriel", "battlefield")
    act(s, "p1", type="life", player="p1", delta=start - 40)
    c = put(s, "Vampire's Kiss", "hand")
    mana(s, B=1, C=1)
    act(s, "p1", type="cast_spell", card_id=c.id, targets=["p2"])
    settle(s)
    assert s.state.players["p1"].life == start + gained  # 119.10: checked as the gain would happen
    roundtrip(s)


def test_phial_of_galadriel_and_a_second_life_gain_effect_commute(cards):
    s = build(cards, p1=("Vampire's Kiss", "Phial of Galadriel", "Boon Reflection"))
    put(s, "Phial of Galadriel", "battlefield")
    put(s, "Boon Reflection", "battlefield")
    act(s, "p1", type="life", player="p1", delta=-35)
    c = put(s, "Vampire's Kiss", "hand")
    mana(s, B=1, C=1)
    act(s, "p1", type="cast_spell", card_id=c.id, targets=["p2"])
    assert s.state.rules.decision is None  # 616.1: both double -> the same result either way: no question
    settle(s)
    assert s.state.players["p1"].life == 5 + 8
    roundtrip(s)


def test_forbidden_crypt_loses_the_game_with_an_empty_graveyard(cards):
    s = build(cards, p1=("Divination", "Forbidden Crypt"))
    put(s, "Forbidden Crypt", "battlefield")
    c = put(s, "Divination", "hand")
    mana(s, C=2, U=1)
    act(s, "p1", type="cast_spell", card_id=c.id)
    settle(s)
    assert "p1" in s.state.rules.lost  # 104.3e: "If you can't, you lose the game."
    roundtrip(s)

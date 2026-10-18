"""Wave 52C: "reveals N cards from their hand and you choose one of them" (CR 701.20a, 608.2d, 402.3) and the edict "of their choice with flying", real Oracle text
(tests/fixtures/wave52c_cards.json, from data/cards.sqlite). Every scenario checks the replay and a save and a load.

* The player whose hand it is chooses the cards to reveal (privately; the others never see the rest), they are shown to everyone, the spell's controller chooses among them, and the
  rest are hidden again. A hand with no more cards than the number shows them all (the hand size is public).
* 701.21a: "Each opponent sacrifices a creature of their choice with flying": the choice is the sacrificing player's, among their creatures with flying.
"""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.wave9c_kit import build, card_named, check, mana, put, to_hand, zone_of
from tests.wave52c_kit import open_repo

BLACKMAIL, NOGGIN, TOLL, CLIP, AFOUL = "Blackmail", "Noggin Whack", "Mire's Toll", "Clip Wings", "Run Afoul"
HAND = ["Grizzly Bears", "Llanowar Elves", "Frogmite", "Opt", "Giant Growth"]


@pytest.fixture()
def cards(settings):
    yield from open_repo(settings)


@pytest.mark.parametrize("name", [BLACKMAIL, NOGGIN, TOLL, "Pulse of the Dross", CLIP, AFOUL])
def test_the_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


def ask(s):
    d = s.state.rules.decision
    assert d is not None, "no question"
    return d


def names(s, d):
    return [s.state.cards[o.id].name for o in d.options]


def bob_with_hand(cards, spell, *mine):
    s = build(cards, [spell, *mine], HAND)
    for n in HAND:
        to_hand(s, n, "p2")
    to_hand(s, spell)
    return s


def seen_by_alice(s):
    """The names of the cards of Bob's hand that Alice can see (the rest show as hidden placeholders)."""
    return [s.state.cards[i].name for i in s.view("p1")["zones"]["p2:hand"] if not i.startswith("hidden:")]


def test_blackmail_bob_shows_three_alice_picks_one_and_the_rest_are_hidden_again(cards):
    s = bob_with_hand(cards, BLACKMAIL)
    mana(s, B=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, BLACKMAIL).id, targets=["p2"])
    d = ask(s)
    assert d.player == "p2" and d.min_choices == d.max_choices == 3 and len(d.options) == 5  # Bob chooses what to show
    assert seen_by_alice(s) == []  # (not even the five choices)
    check(s)
    shown = [o.id for o in d.options if s.state.cards[o.id].name in ("Grizzly Bears", "Opt", "Giant Growth")]
    act(s, "p2", type="choose", decision_id=d.id, option_ids=shown)
    d = ask(s)
    assert d.player == "p1" and sorted(names(s, d)) == ["Giant Growth", "Grizzly Bears", "Opt"]  # Alice chooses among those three
    assert sorted(seen_by_alice(s)) == ["Giant Growth", "Grizzly Bears", "Opt"]  # (shown to everyone; the other two are not)
    check(s)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[next(o.id for o in d.options if s.state.cards[o.id].name == "Opt")])
    assert zone_of(s, "Opt", "p2") == "p2:graveyard" and zone_of(s, "Grizzly Bears", "p2") == "p2:hand" and zone_of(s, "Giant Growth", "p2") == "p2:hand"
    assert seen_by_alice(s) == []  # (the two shown and kept are hidden again)
    check(s)


def test_noggin_whack_takes_two_of_the_three(cards):
    s = bob_with_hand(cards, NOGGIN)
    mana(s, B=2, C=2)
    act(s, "p1", type="cast_spell", card_id=card_named(s, NOGGIN).id, targets=["p2"])
    d = ask(s)
    act(s, "p2", type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][:3])
    d = ask(s)
    assert d.player == "p1" and d.min_choices == d.max_choices == 2 and len(d.options) == 3
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][:2])
    assert sum(1 for n in HAND if zone_of(s, n, "p2") == "p2:graveyard") == 2 and len(s.state.zones["p2:hand"]) == 3
    check(s)


def test_mires_toll_counts_the_swamps_and_a_small_hand_is_shown_whole(cards):
    s = build(cards, [TOLL, "Swamp", "Swamp"], HAND[:2])
    put(s, "Swamp")
    for n in HAND[:2]:
        to_hand(s, n, "p2")
    to_hand(s, TOLL)
    mana(s, B=1)
    assert len([c for c in s.state.zones["p1:battlefield"] if s.state.cards[c].name == "Swamp"]) == 1
    act(s, "p1", type="cast_spell", card_id=card_named(s, TOLL).id, targets=["p2"])
    d = ask(s)  # one Swamp, two cards in hand: Bob shows one
    assert d.player == "p2" and d.min_choices == 1
    check(s)
    act(s, "p2", type="choose", decision_id=d.id, option_ids=[d.options[0].id])
    d = ask(s)
    assert d.player == "p1" and len(d.options) == 1  # (one card shown: Alice's choice is that card)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[d.options[0].id])
    assert len(s.state.zones["p2:hand"]) == 1 and len(s.state.zones["p2:graveyard"]) == 1
    check(s)


def test_a_hand_no_bigger_than_the_number_is_shown_without_a_question(cards):
    s = build(cards, [BLACKMAIL], HAND[:3])
    for n in HAND[:3]:
        to_hand(s, n, "p2")
    to_hand(s, BLACKMAIL)
    mana(s, B=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, BLACKMAIL).id, targets=["p2"])
    d = ask(s)
    assert d.player == "p1" and len(d.options) == 3  # (all of Bob's three are shown)
    check(s)


@pytest.mark.parametrize("spell", [CLIP, AFOUL])
def test_the_edict_takes_a_flier_of_their_choice(cards, spell):
    s = build(cards, [spell], ["Mulldrifter", "Hundred-Talon Kami", "Grizzly Bears"])
    for n in ("Mulldrifter", "Hundred-Talon Kami", "Grizzly Bears"):
        put(s, n, "p2")
    to_hand(s, spell)
    mana(s, R=2, G=2, C=2)
    act(s, "p1", type="cast_spell", card_id=card_named(s, spell).id, **({"targets": ["p2"]} if spell == AFOUL else {}))
    d = ask(s)
    assert d.player == "p2" and sorted(names(s, d)) == ["Hundred-Talon Kami", "Mulldrifter"]  # the ground creature isn't offered
    act(s, "p2", type="choose", decision_id=d.id, option_ids=[next(o.id for o in d.options if s.state.cards[o.id].name == "Mulldrifter")])
    assert zone_of(s, "Mulldrifter", "p2") == "p2:graveyard" and zone_of(s, "Grizzly Bears", "p2") == "p2:battlefield"
    check(s)


def test_pulse_of_the_dross_comes_back_while_bob_holds_more_cards(cards):
    s = bob_with_hand(cards, "Pulse of the Dross")
    mana(s, B=2, C=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Pulse of the Dross").id, targets=["p2"])
    d = ask(s)
    act(s, "p2", type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][:3])
    d = ask(s)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[d.options[0].id])
    assert len(s.state.zones["p2:hand"]) == 4 and zone_of(s, "Pulse of the Dross") == "p1:hand"  # (four cards to Alice's none: back to its owner's hand)
    check(s)

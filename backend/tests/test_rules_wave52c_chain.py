"""Wave 52C: the chain spells (CR 707.10, 707.10c, 118.12), real Oracle text (tests/fixtures/wave52c_cards.json, from data/cards.sqlite). Every scenario checks the replay and a save
and a load.

* "[That player] may pay {R}{R}. If the player does, they may copy this spell and may choose a new target for that copy.": the player the spell's single target names (or the
  target permanent's controller, as it last existed, 608.2h) decides and pays; a copy is controlled by the player who copies it (707.10) and, being a copy of the same spell, goes
  on the same way with its own target.
"""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.wave9c_kit import build, card_named, check, life, mana, put, to_hand, zone_of
from tests.wave52c_kit import drive, open_repo

NAMES = ["Chain Lightning", "Chain of Vapor", "Chain of Smog", "Chain of Acid", "Chain of Plasma", "Chain of Silence", "String of Disappearances", "Chain Stasis"]
LIGHTNING, VAPOR, SMOG, STASIS, BEARS = "Chain Lightning", "Chain of Vapor", "Chain of Smog", "Chain Stasis", "Grizzly Bears"


@pytest.fixture()
def cards(settings):
    yield from open_repo(settings)


@pytest.mark.parametrize("name", NAMES)
def test_the_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


def ask(s):
    d = s.state.rules.decision
    assert d is not None, "no question"
    return d


def answer(s, option):
    d = ask(s)
    assert option in [o.id for o in d.options], (option, [o.id for o in d.options])
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[option])


def no(d):
    """Decline whatever can be declined (the chain ends), else the first option."""
    return ["decline"] if "decline" in [o.id for o in d.options] else [o.id for o in d.options][: max(1, d.min_choices)]


def cast(s, name, *targets, pid="p1"):
    act(s, pid, type="cast_spell", card_id=card_named(s, name, pid).id, targets=list(targets))


def lightning_at_bob(cards):
    s = build(cards, [LIGHTNING], [LIGHTNING])
    to_hand(s, LIGHTNING)
    mana(s, R=1)
    return s


def test_the_player_hit_pays_copies_and_aims_the_copy_at_the_caster(cards):
    s = lightning_at_bob(cards)
    mana(s, "p2", R=2)
    cast(s, LIGHTNING, "p2")
    assert life(s, "p2") == 37  # (3 damage)
    d = ask(s)
    assert d.player == "p2" and d.prompt == "Chain Lightning: pay {R}{R}?"  # Bob decides (118.12), not the caster
    check(s)
    answer(s, "pay")
    assert s.state.players["p2"].mana == {}
    d = ask(s)
    assert d.player == "p2" and d.prompt == "Chain Lightning: copy this spell?"
    answer(s, "pay")
    d = ask(s)  # 707.10c: keep the target or choose a new one
    assert d.player == "p2" and {o.id for o in d.options} >= {"keep", "p1"}
    assert [s.state.cards[i].controller for i in s.state.zones["stack"]] == ["p1", "p2"]  # the copy is Bob's (707.10)
    check(s)
    answer(s, "p1")
    assert life(s, "p1") == 37 and life(s, "p2") == 37 and not s.state.zones["stack"]  # the copy hit Alice; Bob's copy then asked Alice, who has no {R}{R}
    assert zone_of(s, LIGHTNING) == "p1:graveyard"
    check(s)


def test_declining_the_payment_or_the_copy_ends_the_chain(cards):
    s = lightning_at_bob(cards)
    mana(s, "p2", R=2)
    cast(s, LIGHTNING, "p2")
    answer(s, "decline")
    assert not s.state.zones["stack"] and s.state.players["p2"].mana == {"R": 2} and ask is not None
    check(s)
    s = lightning_at_bob(cards)
    mana(s, "p2", R=2)
    cast(s, LIGHTNING, "p2")
    answer(s, "pay")
    answer(s, "decline")  # paid, but "may copy"
    assert not s.state.zones["stack"] and s.state.players["p2"].mana == {}
    check(s)


def test_nothing_is_asked_when_the_payment_cannot_be_made(cards):
    s = lightning_at_bob(cards)
    mana(s, "p2", R=1)  # {R}{R} is needed
    cast(s, LIGHTNING, "p2")
    assert s.state.rules.decision is None and not s.state.zones["stack"] and life(s, "p2") == 37
    check(s)


def test_it_goes_on_round_and_round(cards):
    s = lightning_at_bob(cards)
    mana(s, "p2", R=2)
    mana(s, "p1", R=2)
    cast(s, LIGHTNING, "p2")
    answer(s, "pay")
    answer(s, "pay")
    answer(s, "p1")  # Bob's copy hits Alice ...
    d = ask(s)  # ... who may pay {R}{R} herself
    assert d.player == "p1" and d.prompt == "Chain Lightning: pay {R}{R}?"
    answer(s, "pay")
    answer(s, "pay")
    answer(s, "keep")  # her copy keeps Alice as the target (she may hit herself), 707.10c
    assert life(s, "p1") == 34 and life(s, "p2") == 37 and not s.state.zones["stack"]
    check(s)


def test_a_creature_that_died_is_still_its_controllers_chain(cards):
    s = build(cards, [LIGHTNING], [BEARS])
    put(s, BEARS, "p2")
    to_hand(s, LIGHTNING)
    mana(s, R=1)
    mana(s, "p2", R=2)
    cast(s, LIGHTNING, card_named(s, BEARS, "p2").id)
    d = ask(s)  # (the damage is marked; the creature dies when state-based actions are next checked, 704.3)
    assert d.player == "p2" and zone_of(s, BEARS, "p2") == "p2:battlefield"  # the controller of the creature
    answer(s, "pay")
    answer(s, "pay")
    answer(s, "p2")
    assert life(s, "p2") == 37 and not s.state.zones["stack"] and zone_of(s, BEARS, "p2") == "p2:graveyard"
    check(s)


def test_chain_of_vapor_asks_the_controller_not_the_owner(cards):
    s = build(cards, [VAPOR, BEARS], ["Island", "Llanowar Elves"])
    bears = put(s, BEARS, "p1")
    put(s, "Island", "p2")
    elves = put(s, "Llanowar Elves", "p2")
    act(s, "p1", type="set_controller", card_ids=[bears.id], player="p2")  # Alice owns it, Bob controls it
    to_hand(s, VAPOR)
    mana(s, U=2, C=1)
    cast(s, VAPOR, bears.id)
    assert zone_of(s, BEARS) == "p1:hand"  # (to its owner's hand: the permanent has left the battlefield)
    d = ask(s)
    assert d.player == "p2" and ": sacrifice a land?" in d.prompt  # the controller as it last existed (608.2h), not Alice, its owner
    answer(s, "pay")
    assert zone_of(s, "Island", "p2") == "p2:graveyard"  # (its one land: nothing to choose)
    assert ask(s).prompt == "Chain of Vapor: copy this spell?"
    answer(s, "pay")  # copy it
    answer(s, elves.id)  # a new target
    assert zone_of(s, "Llanowar Elves", "p2") == "p2:hand" and not s.state.zones["stack"]
    check(s)


def test_chain_of_smog_has_nothing_to_pay(cards):
    s = build(cards, [SMOG, "Frogmite", "Opt", "Giant Growth"], ["Island", BEARS, "Llanowar Elves"])
    for name in (BEARS, "Llanowar Elves"):
        to_hand(s, name, "p2")
    for name in ("Frogmite", "Opt", "Giant Growth"):
        to_hand(s, name)
    to_hand(s, SMOG)
    mana(s, B=1, C=2)
    hand = len(s.state.zones["p1:hand"]) - 1  # (the spell leaves it)
    cast(s, SMOG, "p2")
    d = ask(s)
    assert d.player == "p2" and d.kind != "copy"  # the discard comes first (Bob chooses)
    while s.state.rules.decision is not None and "copy" not in s.state.rules.decision.prompt:
        answer(s, ask(s).options[0].id)
    assert ask(s).prompt == "Chain of Smog: copy this spell?"
    check(s)
    answer(s, "pay")
    answer(s, "p1")  # the copy is Bob's: Alice discards two cards
    drive(s, no)
    assert not s.state.zones["stack"] and len(s.state.zones["p1:hand"]) == hand - 2
    check(s)


def test_chain_stasis_the_tap_is_optional_and_the_copy_is_the_controllers(cards):
    s = build(cards, [STASIS, BEARS], [BEARS])
    mine, theirs = put(s, BEARS, "p1"), put(s, BEARS, "p2")
    to_hand(s, STASIS)
    mana(s, U=2, C=1)
    mana(s, "p2", U=1, C=2)
    cast(s, STASIS, theirs.id)
    assert ask(s).player == "p1"
    answer(s, "yes")  # "You may tap or untap target creature"
    answer(s, "tap")
    assert s.state.cards[theirs.id].tapped
    assert ask(s).player == "p2" and "{2}{U}" in ask(s).prompt  # then its controller may pay
    answer(s, "pay")
    answer(s, "pay")  # and copy it
    answer(s, mine.id)  # the copy, Bob's, aims at Alice's creature
    assert ask(s).player == "p2"  # Bob chooses what his copy does
    answer(s, "yes")
    answer(s, "tap")
    assert s.state.cards[mine.id].tapped
    drive(s, no)
    assert not s.state.zones["stack"]
    check(s)

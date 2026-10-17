"""Wave 43B: the most-played cards one line short of FULL (CR 2026-09-25), real Oracle text (tests/fixtures/wave43b_cards.json, from data/cards.sqlite).
Every scenario checks the replay and a save and a load. This file: the shuffle-and-reveal, the land, the dies/graveyard trigger and the top-of-library spell;
the mana, spell and trigger cards are in test_rules_wave43b_mana.py, _spells.py and _triggers.py.

Ranked by how many decks hold them (the popularity rank of the card, in brackets), each fix is the one shape the card's last line needed:

* 701.24, 701.20a, 110.2, 608.2h: "The owner of target permanent shuffles it into their library, then reveals the top card of their library. If it's a permanent card,
  they put it onto the battlefield." (Chaos Warp [30]) - the owner of the permanent as it was (a token's owner shuffles before revealing); the revealed card is public; a card
  that isn't a permanent card stays on top; the owner, not the caster, puts it onto the battlefield (under their control).
* 115.1, 608.2h, 701.23: "Destroy target artifact, enchantment, or nonbasic land an opponent controls. That player may search their library for a land card with a basic
  land type, put it onto the battlefield, then shuffle." (Boseiju, Who Endures [77], channel from the hand) - "an opponent controls" closes the whole list, "nonbasic" stays
  the land's; "that player" is the controller of what was destroyed.
* 603.2c, 700.4, 603.6c: "Whenever another creature dies, or a creature card is put into a graveyard from anywhere other than the battlefield, or a creature card leaves your
  graveyard, ~ deals 1 damage to each opponent." (Syr Konrad, the Grim [260]) - three whole conditions, each its own event; a creature that dies is the first, never also the second.
* 118.9, 119.4, 107.3b: "You may play lands and cast spells from the top of your library. If you cast a spell this way, pay life equal to its mana value rather than pay its
  mana cost." (Bolas's Citadel [275]) - the life is paid with the rest of the cost; the top card is looked at by its owner alone.
* 500.7: "This land enters tapped unless it's your first, second, or third turn of the game." (Starting Town [704]) - your own turn, one of the first three turns you began.

Refused (manual, with the reason): Veil of Summer (hexproof from a color, for players too), Nature's Rhythm (an X in a harmonize cost), Sevinne's Reclamation and the Chain spells
(copying the resolving spell), Tainted Pact / Beseech the Mirror (hidden information in the repeat loop and the bargain), Forgotten Ancient (moving "any number" of counters).
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import coverage, view
from tests.game_helpers import act
from tests.test_rules_wave34b_activated import activate, settle, stops
from tests.wave9c_kit import build, card_named, check, mana, put, to_hand, zone_of
from tests.wave43b_kit import FULL, cast, library, life, names_in, on_top, open_cards, stack_size


@pytest.fixture()
def cards(settings):
    yield from open_cards(settings)


@pytest.mark.parametrize("name", FULL)
def test_every_card_is_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


# ---- Chaos Warp [30] -------------------------------------------------------------------------------------------------------------------------------------
def test_chaos_warp_shuffles_the_permanent_in_and_its_owner_puts_the_revealed_permanent_card_onto_the_battlefield(cards):
    s = build(cards, ["Chaos Warp"], ["Hill Giant"], islands=6)
    giant = put(s, "Hill Giant", "p2")
    to_hand(s, "Chaos Warp")
    mana(s, R=1, C=2)
    before = len(library(s, "p2"))
    cast(s, "Chaos Warp", targets=[giant.id])
    # 701.24: Bob's library was shuffled with the Giant in it; 701.20a: the top card was revealed, and every card in that library is a permanent card, so it entered
    # the battlefield - under BOB's control (his card, his instruction: 110.2)
    on_field = list(s.state.zones["p2:battlefield"])
    assert len(on_field) == 1 and len(library(s, "p2")) == before  # one card out of Bob's library (the Giant went in, one came out)
    entered = s.state.cards[on_field[0]]
    assert entered.controller == "p2" and entered.owner == "p2"
    assert zone_of(s, "Chaos Warp") == "p1:graveyard"
    check(s)


def test_chaos_warp_leaves_a_card_that_is_not_a_permanent_card_on_top(cards):
    s = build(cards, ["Chaos Warp"], ["Lightning Bolt", "Shock", "Counterspell"], islands=0)
    act(s, "p2", type="create_token", token={"name": "Spirit", "power": "1", "toughness": "1", "colors": ["W"], "type_line": "Token Creature — Spirit"})
    spirit = next(c for c in s.state.cards.values() if c.name == "Spirit")
    to_hand(s, "Chaos Warp")
    mana(s, R=1, C=2)
    names = names_in(s, "library", "p2")
    cast(s, "Chaos Warp", targets=[spirit.id])
    # 111.7: the token ceased to exist in the library, the owner shuffled anyway (701.24c) and revealed: an instant, not a permanent card - it stays on top
    assert not s.state.zones.get("p2:battlefield")
    assert names_in(s, "library", "p2") == names == ["Counterspell", "Lightning Bolt", "Shock"]
    assert not any(c.name == "Spirit" for c in s.state.cards.values())  # 111.7: it ceased to exist
    check(s)


def test_chaos_warp_needs_a_target(cards):
    s = build(cards, ["Chaos Warp"], [])
    to_hand(s, "Chaos Warp")
    mana(s, R=1, C=2)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=card_named(s, "Chaos Warp").id)  # 601.2c: a target is required
    assert not stack_size(s)
    check(s)


# ---- Boseiju, Who Endures [77] ---------------------------------------------------------------------------------------------------------------------------
def boseiju_table(cards):
    s = build(cards, ["Boseiju, Who Endures", "Mishra's Factory"], ["Mishra's Factory", "Sol Ring"], islands=8)
    to_hand(s, "Boseiju, Who Endures")
    return s, put(s, "Mishra's Factory"), put(s, "Mishra's Factory", "p2"), put(s, "Sol Ring", "p2")


def test_boseiju_channel_destroys_an_opponents_nonbasic_land_and_its_controller_may_fetch_a_basic_land_type(cards):
    s, mine, theirs, ring = boseiju_table(cards)
    mana(s, G=1, C=1)
    activate(s, "p1", card_named(s, "Boseiju, Who Endures"), "Channel", targets=[theirs.id])
    assert zone_of(s, "Boseiju, Who Endures") == "p1:graveyard"  # 602.2b: the discard is part of the cost
    settle(s, answer="no")  # Bob declines the search (701.23b: a player who doesn't search doesn't shuffle)
    assert zone_of(s, "Mishra's Factory", "p2") == "p2:graveyard" and not [c for c in s.state.zones["p2:battlefield"] if s.state.cards[c].name == "Island"]
    check(s)


def test_boseiju_that_player_is_the_one_whose_permanent_it_was(cards):
    s, mine, theirs, ring = boseiju_table(cards)
    mana(s, G=1, C=1)
    activate(s, "p1", card_named(s, "Boseiju, Who Endures"), "Channel", targets=[ring.id])
    d = None
    for _ in range(20):
        d = s.state.rules.decision
        if d is not None:
            break
        act(s, s.state.rules.priority, type="pass_priority")
    assert d is not None and d.player == "p2"  # 608.2h: Bob controlled the artifact; Alice isn't asked
    act(s, "p2", type="choose", decision_id=d.id, option_ids=["yes"])
    d = s.state.rules.decision
    assert d.player == "p2" and d.kind == "choose_cards" and all(s.state.cards[o.id].name == "Island" for o in d.options)  # a land card with a basic land type
    act(s, "p2", type="choose", decision_id=d.id, option_ids=[d.options[0].id])
    settle(s)
    assert zone_of(s, "Sol Ring", "p2") == "p2:graveyard"
    fetched = [s.state.cards[c] for c in s.state.zones["p2:battlefield"] if s.state.cards[c].name == "Island"]
    assert len(fetched) == 1 and fetched[0].controller == "p2" and not fetched[0].tapped  # onto the battlefield, untapped, under Bob's control
    check(s)


def test_boseiju_cannot_target_your_own_permanent_or_a_basic_land(cards):
    s, mine, theirs, ring = boseiju_table(cards)
    basic = put(s, "Island", "p2")
    mana(s, G=1, C=1)
    boseiju = card_named(s, "Boseiju, Who Endures")
    for target in (mine, basic):
        with pytest.raises(ActionError):
            activate(s, "p1", boseiju, "Channel", targets=[target.id])  # 115.1: an opponent's artifact, enchantment or nonbasic land only
    assert zone_of(s, "Boseiju, Who Endures") == "p1:hand" and not stack_size(s)  # 602.2b: nothing was paid
    check(s)


# ---- Syr Konrad, the Grim [260] ---------------------------------------------------------------------------------------------------------------------------
def konrad_table(cards):
    s = build(cards, ["Syr Konrad, the Grim", "Grizzly Bears", "Lightning Bolt", "Counterspell", "Test Grave Pilfer"], ["Elvish Mystic"])
    put(s, "Syr Konrad, the Grim")
    return s


def test_syr_konrad_pings_when_another_creature_dies_once_whoever_controlled_it(cards):
    s = konrad_table(cards)
    put(s, "Grizzly Bears")
    put(s, "Elvish Mystic", "p2")
    to_hand(s, "Lightning Bolt")
    mana(s, R=2)
    cast(s, "Lightning Bolt", targets=[card_named(s, "Elvish Mystic", "p2").id])
    assert zone_of(s, "Elvish Mystic", "p2") == "p2:graveyard"
    assert life(s, "p2") == 39  # 700.4: it died - ONE trigger (put into a graveyard "from anywhere other than the battlefield" doesn't count it again)
    check(s)
    to_hand(s, "Lightning Bolt") if False else None


def test_syr_konrad_pings_for_your_own_creature_dying_too(cards):
    s = konrad_table(cards)
    put(s, "Grizzly Bears")
    to_hand(s, "Lightning Bolt")
    mana(s, R=1)
    cast(s, "Lightning Bolt", targets=[card_named(s, "Grizzly Bears").id])
    assert life(s, "p2") == 39 and life(s) == 40  # "another creature", "each opponent"
    check(s)


def test_syr_konrad_pings_for_a_creature_card_put_into_a_graveyard_from_the_stack_and_for_one_leaving_your_graveyard(cards):
    s = build(cards, ["Syr Konrad, the Grim", "Grizzly Bears", "Test Grave Pilfer"], ["Counterspell"])
    put(s, "Syr Konrad, the Grim")
    stops(s)
    to_hand(s, "Grizzly Bears")
    to_hand(s, "Counterspell", "p2")
    mana(s, G=1, C=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Grizzly Bears").id)
    mana(s, "p2", U=2)
    act(s, "p2", type="cast_spell", card_id=card_named(s, "Counterspell", "p2").id, targets=[card_named(s, "Grizzly Bears").id])
    settle(s)
    assert zone_of(s, "Grizzly Bears") == "p1:graveyard"
    assert life(s, "p2") == 39  # a creature card put into a graveyard from the stack (countered): not from the battlefield
    to_hand(s, "Test Grave Pilfer")
    mana(s, B=1)
    cast(s, "Test Grave Pilfer", targets=[card_named(s, "Grizzly Bears").id])
    assert zone_of(s, "Grizzly Bears") == "p1:exile"
    assert life(s, "p2") == 38  # a creature card left your graveyard
    check(s)


def test_syr_konrad_does_not_ping_for_a_creature_card_leaving_an_opponents_graveyard_or_a_noncreature_card_arriving(cards):
    s = konrad_table(cards)
    put(s, "Elvish Mystic", "p2")
    to_hand(s, "Lightning Bolt")
    to_hand(s, "Test Grave Pilfer")
    mana(s, R=1, B=1)
    cast(s, "Lightning Bolt", targets=[card_named(s, "Elvish Mystic", "p2").id])
    assert life(s, "p2") == 39  # the dying creature (the Bolt, an instant card, arriving in a graveyard isn't a creature card)
    cast(s, "Test Grave Pilfer", targets=[card_named(s, "Elvish Mystic", "p2").id])
    assert zone_of(s, "Elvish Mystic", "p2") == "p2:exile" and life(s, "p2") == 39  # "leaves YOUR graveyard": not Bob's
    check(s)


# ---- Bolas's Citadel [275] --------------------------------------------------------------------------------------------------------------------------------
def citadel_table(cards, top="Grizzly Bears"):
    s = build(cards, ["Bolas's Citadel", top])
    put(s, "Bolas's Citadel")
    return s, on_top(s, top)


def test_bolas_citadel_casts_the_top_card_paying_life_equal_to_its_mana_value(cards):
    s, bears = citadel_table(cards)
    assert life(s) == 40 and bears.id in view.hints(s.state, "p1", cards).get("free_castable", [])  # offered as a cast "without paying its mana cost" (the alternative cost)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=bears.id)  # 118.9: the permission always takes the alternative cost - never the mana cost
    assert life(s) == 40 and not stack_size(s)
    act(s, "p1", type="cast_spell", card_id=bears.id, free=True)  # no mana at all: the mana cost is replaced (118.9)
    settle(s)
    assert life(s) == 38 and zone_of(s, "Grizzly Bears") == "p1:battlefield"  # 119.4: paid with the rest of the cost, as it is cast (Grizzly Bears: mana value 2)
    check(s)


def test_bolas_citadel_top_card_is_hidden_from_the_opponent_and_a_land_is_played_not_cast(cards):
    s, forest = citadel_table(cards, "Forest")
    assert s.view("p2")["zones"]["p1:library"]["known"] == []  # "You may look at the top card of your library any time": its owner alone
    assert forest.id in view.hints(s.state, "p1", cards)["playable_lands"]
    act(s, "p1", type="play_land", card_id=forest.id)
    assert zone_of(s, "Forest") == "p1:battlefield" and life(s) == 40  # a land costs no life
    check(s)


def test_bolas_citadel_only_lets_you_cast_the_top_card(cards):
    s, bears = citadel_table(cards)
    second = s.state.zones["p1:library"][1]
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=second, free=True)  # only the TOP card of the library
    assert life(s) == 40 and not stack_size(s)
    check(s)

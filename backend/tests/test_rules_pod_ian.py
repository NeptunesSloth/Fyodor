"""The pod's Ian Malcolm deck (tests/fixtures/soak_decks/ian_malcolm_group_play.txt): its plan, with real Oracle text.

Group draw (Vision Skeins, Temple Bell, Howling Mine) makes each player draw a second card, so Ian Malcolm has each of them exile their top
card. During their own turn, a player may cast the cards they don't own exiled with Ian, with mana of any type. The deck's payoffs see Alice
cast from exile (Sage of the Beyond, Keeper of Secrets, Nalfeshnee, Passionate Archaeologist on Ian), Brand takes back what an opponent cast
from Alice's library, and Laboratory Maniac wins off an empty library. "Exiled with Ian Malcolm" is linked to that object (607.2a): Ian back
from the hand is a new object (400.7) and his old exile isn't his.
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import coverage
from app.rules.view import rules_view
from tests.game_helpers import act
from tests.pod_c_kit import (
    card,
    cast,
    field,
    hold,
    mana,
    on_top,
    put,
    settle,
    table,
    to_hand,
    until,
    zone_names,
)
from tests.test_rules_wave12a_counters_keywords import real
from tests.wave9c_kit import check

IAN = "Ian Malcolm, Chaotician"
EXTRA = [
    real(IAN, '{1}{U}{R}', 3, 'Legendary Creature — Human Scientist',
         "Whenever a player draws their second card each turn, that player exiles the top card of their library.\nDuring each player's turn, that "
         "player may cast a spell from among the cards they don't own exiled with Ian Malcolm, and mana of any type can be spent to cast it.",
         ("2", "2"), 'RU'),
    real('Vision Skeins', '{1}{U}', 2, 'Instant', 'Each player draws two cards.', None, 'U'),
    real('Brand', '{R}', 1, 'Instant',
         'Gain control of all permanents you own. (This effect lasts indefinitely.)\nCycling {2} ({2}, Discard this card: Draw a card.)', None, 'R'),
    real('Temple Bell', '{3}', 3, 'Artifact', '{T}: Each player draws a card.', None, ''),
    real('Keeper of Secrets', '{5}{R}', 6, 'Creature — Demon',
         "First strike, haste\nSymphony of Pain — Whenever you cast a spell from anywhere other than your hand, this creature deals damage equal to "
         "that spell's mana value to target opponent.", ("6", "4"), 'R'),
    real('Nalfeshnee', '{5}{R}', 6, 'Creature — Beast Demon',
         'Flying\nWhenever you cast a spell from exile, copy it. You may choose new targets for the copy. If it\'s a permanent spell, the copy gains '
         'haste and "At the beginning of the end step, sacrifice this permanent." (A copy of a permanent spell becomes a token.)', ("4", "6"), 'R'),
    real('Passionate Archaeologist', '{1}{R}', 2, 'Legendary Enchantment — Background',
         'Commander creatures you own have "Whenever you cast a spell from exile, this creature deals damage equal to that spell\'s mana value to '
         'target opponent."', None, 'R'),
    real('Sage of the Beyond', '{5}{U}{U}', 7, 'Creature — Spirit Giant',
         'Flying\nSpells you cast from anywhere other than your hand cost {2} less to cast.\nForetell {4}{U} (During your turn, you may pay {2} and '
         'exile this card from your hand face down. Cast it on a later turn for its foretell cost.)', ("5", "5"), 'U'),
    real('Laboratory Maniac', '{2}{U}', 3, 'Creature — Human Wizard',
         'If you would draw a card while your library has no cards in it, you win the game instead.', ("2", "2"), 'U'),
    real('Howling Mine', '{2}', 2, 'Artifact',
         "At the beginning of each player's draw step, if this artifact is untapped, that player draws an additional card.", None, ''),
    real('Faerie Mastermind', '{1}{U}', 2, 'Creature — Faerie Rogue',
         'Flash\nFlying\nWhenever an opponent draws their second card each turn, you draw a card.\n{3}{U}: Each player draws a card.', ("2", "1"), 'U'),
    real('Scrawling Crawler', '{3}', 3, 'Artifact Creature — Phyrexian Construct',
         'At the beginning of your upkeep, each player draws a card.\nWhenever an opponent draws a card, that player loses 1 life.', ("3", "2"), ''),
    real('Brainstorm', '{U}', 1, 'Instant',
         'Draw three cards, then put two cards from your hand on top of your library in any order.', None, 'U'),
]
NAMES = [c["name"] for c in EXTRA]


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


def ian(cards, *mine, theirs=(), on_field=True):
    s = table(cards, mine, theirs, commander=IAN, lands=("Island", 10), their_lands=("Forest", 10))
    if on_field:
        put(s, IAN)
    hold(s)
    return s


def skeins(s, mine=(), theirs=()):
    """Alice casts Vision Skeins: each player draws two cards, and Ian has each exile their next card."""
    if mine:
        on_top(s, *mine)
    if theirs:
        on_top(s, *theirs, pid="p2")
    mana(s, U=2)
    cast(s, "Vision Skeins")


def test_each_second_draw_exiles_and_alice_casts_bobs_card_with_any_mana(cards):
    """Alice may cast Bob's exiled Giant Growth with {C} (and the table hints it), not her own exiled Sol Ring."""
    s = ian(cards, "Vision Skeins", "Brainstorm", "Opt", "Sol Ring", theirs=["Grizzly Bears", "Lightning Bolt", "Giant Growth"])
    skeins(s, ["Brainstorm", "Opt", "Sol Ring"], ["Grizzly Bears", "Lightning Bolt", "Giant Growth"])
    assert zone_names(s, "p1", "exile") == ["Sol Ring"] and zone_names(s, "p2", "exile") == ["Giant Growth"]
    growth = card(s, "Giant Growth", "p2")
    mana(s, C=1)
    assert growth.id in rules_view(s.state, "p1", s.cards)["hints"]["castable"]
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=card(s, "Sol Ring").id)
    act(s, "p1", type="cast_spell", card_id=growth.id, targets=[card(s, IAN).id])
    settle(s)
    assert s.state.cards[growth.id].zone == "p2:graveyard"
    check(s)


def test_bob_casts_alices_card_on_his_turn_alice_cant_and_brand_takes_it_back(cards):
    s = ian(cards, "Vision Skeins", "Brainstorm", "Opt", "Sol Ring", "Brand", theirs=["Grizzly Bears", "Lightning Bolt", "Murder", "Giant Growth"])
    to_hand(s, "Brand")
    skeins(s, ["Brainstorm", "Opt", "Sol Ring"], ["Grizzly Bears", "Murder", "Giant Growth"])
    until(s, "p2", "main1")
    hold(s, "p2")
    act(s, "p1", type="set_prefs", response="on")
    mana(s, "p2", R=1)
    bolt = card(s, "Lightning Bolt", "p2")
    assert bolt.zone == "p2:hand"  # (Bob's draw)
    act(s, "p2", type="cast_spell", card_id=bolt.id, targets=["p1"])
    act(s, "p2", type="pass_priority")
    mana(s, G=1)
    with pytest.raises(ActionError):  # (not Alice's turn)
        act(s, "p1", type="cast_spell", card_id=card(s, "Giant Growth", "p2").id, targets=[card(s, IAN).id])
    act(s, "p1", type="pass_priority")
    settle(s)
    ring = card(s, "Sol Ring")
    mana(s, "p2", G=1)
    act(s, "p2", type="cast_spell", card_id=ring.id)
    settle(s)
    assert s.state.cards[ring.id].zone == "p2:battlefield"
    until(s, "p1", "main1")
    mana(s, R=1)
    cast(s, "Brand")
    assert s.state.cards[ring.id].zone == "p1:battlefield" and s.state.cards[ring.id].controller == "p1"
    check(s)


def test_only_the_second_card_counts_even_if_drawn_before_ian(cards):
    """Temple Bell before Ian is each player's first card; Vision Skeins is their second and third: one exile each."""
    s = ian(cards, "Vision Skeins", "Temple Bell", on_field=False)
    bell = put(s, "Temple Bell")
    act(s, "p1", type="activate_ability", card_id=bell.id, ability=0)
    settle(s)
    put(s, IAN)
    skeins(s)
    assert len(s.state.zones["p1:exile"]) == 1 and len(s.state.zones["p2:exile"]) == 1
    check(s)


def test_ian_back_from_the_hand_doesnt_own_his_old_exile(cards):
    """400.7, 607.2a: Bob's card exiled with the old Ian isn't exiled with the new one."""
    s = ian(cards, "Vision Skeins", theirs=["Grizzly Bears", "Lightning Bolt", "Giant Growth"])
    skeins(s, theirs=["Grizzly Bears", "Lightning Bolt", "Giant Growth"])
    old = card(s, IAN)
    act(s, "p1", type="move", card_ids=[old.id], to={"player": "p1", "zone": "hand"})
    settle(s)
    if not s.state.cards[old.id].zone.endswith(":hand"):  # (the commander may go to the command zone instead)
        act(s, "p1", type="move", card_ids=[old.id], to={"player": "p1", "zone": "hand"})
    mana(s, U=1, R=1, C=1)
    cast(s, IAN)
    assert field(s)[IAN] == 1
    mana(s, G=1)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=card(s, "Giant Growth", "p2").id, targets=[old.id])
    check(s)


def test_casting_from_ian_exile_pays_off(cards):
    """Bob's Courser of Kruphix ({1}{G}{G}) costs {G}{G} with Sage of the Beyond, paid with {U}{U}. Keeper of Secrets and Ian (a commander,
    Passionate Archaeologist) each deal 3 to Bob; Nalfeshnee copies it (a hasty token)."""
    s = ian(cards, "Vision Skeins", "Keeper of Secrets", "Nalfeshnee", "Passionate Archaeologist", "Sage of the Beyond",
            theirs=["Grizzly Bears", "Lightning Bolt", "Courser of Kruphix"])
    for name in ("Keeper of Secrets", "Nalfeshnee", "Passionate Archaeologist", "Sage of the Beyond"):
        put(s, name)
    skeins(s, theirs=["Grizzly Bears", "Lightning Bolt", "Courser of Kruphix"])
    life = s.state.players["p2"].life
    mana(s, U=2)
    act(s, "p1", type="cast_spell", card_id=card(s, "Courser of Kruphix", "p2").id)
    settle(s)
    coursers = [s.state.cards[i] for i in s.state.zones["p1:battlefield"] if s.state.cards[i].name == "Courser of Kruphix"]
    assert len(coursers) == 2 and sum(bool(c.is_token) for c in coursers) == 1
    assert s.state.players["p2"].life == life - 6
    check(s)


def test_laboratory_maniac_wins_off_an_empty_library(cards):
    s = ian(cards, "Laboratory Maniac", "Brainstorm")
    put(s, "Laboratory Maniac")
    brainstorm = to_hand(s, "Brainstorm")
    act(s, "p1", type="move", card_ids=list(s.state.zones["p1:library"]), to={"player": "p1", "zone": "graveyard"})
    mana(s, U=1)
    act(s, "p1", type="cast_spell", card_id=brainstorm.id)
    settle(s)
    assert s.state.rules.winner == "p1"


def test_howling_mine_draw_step_triggers_ian_mastermind_and_crawler(cards):
    """Bob's draw step: his extra card is his second, so he exiles one; Faerie Mastermind draws Alice a card, Scrawling Crawler costs Bob 1
    life per card drawn."""
    s = ian(cards, "Howling Mine", "Faerie Mastermind", "Scrawling Crawler", theirs=["Grizzly Bears"])
    for name in ("Howling Mine", "Faerie Mastermind", "Scrawling Crawler"):
        put(s, name)
    hand, life = len(s.state.zones["p1:hand"]), s.state.players["p2"].life
    until(s, "p2", "main1")
    assert len(s.state.zones["p2:exile"]) == 1
    assert len(s.state.zones["p1:hand"]) == hand + 1 and s.state.players["p2"].life == life - 2
    check(s)

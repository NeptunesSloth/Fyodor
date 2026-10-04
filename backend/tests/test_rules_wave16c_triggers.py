"""Wave 16C: the trigger long tail, continued (CR 2026-09-25). Real Oracle text; every scenario checks the replay and a save and a load.

* 119.5: "target player's life total becomes 10" - the player gains or loses what it takes; "a third of their life, rounded up".
* 701.44a: "target creature you control explores"; 701.34a: "proliferate, then proliferate again".
* 608.2h: "if it was attacking / wasn't blocking" - the creature as it last existed; "dies during combat" (506.1).
* 607.2a: "exile a land you control" (chosen as it resolves) is the linked ability's "the exiled card".
* 401.4: "each player puts a card from their hand on top of their library" - each privately chooses, in turn order.
"""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.fixtures.cards import fixture_cards
from tests.game_helpers import act
from tests.test_rules_effects import mana
from tests.test_rules_wave12a_counters_keywords import answer, real
from tests.test_rules_wave15b_triggers import kill, on_battlefield
from tests.wave9c_kit import build, card_named, check, life, put, to_hand

EXTRA = [
    real("Magister Sphinx", "{4}{W}{U}{B}", 7, "Artifact Creature — Sphinx",
         "Flying\nWhen this creature enters, target player's life total becomes 10.", ("5", "5"), "BUW"),
    real("Dire Fleet Ravager", "{3}{B}{B}", 5, "Creature — Orc Pirate Wizard",
         "Menace, deathtouch\nWhen this creature enters, each player loses a third of their life, rounded up.", ("4", "4"), "B"),
    real("Miner's Guidewing", "{W}", 1, "Creature — Bird",
         "Flying, vigilance\nWhen this creature dies, target creature you control explores. (Reveal the top card of your library. Put "
         "that card into your hand if it's a land. Otherwise, put a +1/+1 counter on that creature, then put the card back or put it "
         "into your graveyard.)", ("1", "1"), "W"),
    real("Barishi", "{2}{G}{G}", 4, "Creature — Elemental",
         "When this creature dies, exile it, then shuffle all creature cards from your graveyard into your library.", ("4", "3"), "G"),
    real("Sadistic Augermage", "{2}{B}", 3, "Creature — Human Wizard",
         "When this creature dies, each player puts a card from their hand on top of their library.", ("3", "1"), "B"),
    real("Chimney Imp", "{4}{B}", 5, "Creature — Imp",
         "Flying\nWhen this creature dies, target opponent puts a card from their hand on top of their library.", ("1", "2"), "B"),
    real("Phage the Untouchable", "{3}{B}{B}{B}{B}", 7, "Legendary Creature — Avatar Minion",
         "When Phage enters, if you didn't cast it from your hand, you lose the game.\nWhenever Phage deals combat damage to a "
         "creature, destroy that creature. It can't be regenerated.\nWhenever Phage deals combat damage to a player, that player "
         "loses the game.", ("4", "4"), "B"),
    real("Wormfang Newt", "{1}{U}", 2, "Creature — Nightmare Salamander Beast",
         "When this creature enters, exile a land you control.\nWhen this creature leaves the battlefield, return the exiled card "
         "to the battlefield under its owner's control.", ("2", "2"), "U"),
    real("Glimmerpost", "", 0, "Land — Locus",
         "When this land enters, you gain 1 life for each Locus on the battlefield.\n{T}: Add {C}.", None),
    real("Earth Kingdom Jailer", "{2}{W}", 3, "Creature — Human Soldier Ally",
         "When this creature enters, exile up to one target artifact, creature, or enchantment an opponent controls with mana value 3 "
         "or greater until this creature leaves the battlefield.", ("3", "3"), "W"),
    real("Rukh Egg", "{3}{R}", 4, "Creature — Bird Egg",
         "When this creature dies, create a 4/4 red Bird creature token with flying at the beginning of the next end step.", ("0", "3"), "R"),
    real("Test Reanimation", "{B}", 1, "Sorcery", "Return target creature card from your graveyard to the battlefield.", None, "B"),
    real("Test Giant", "{5}", 5, "Creature — Giant", "", ("5", "5")),
    real("Test Land Card", "", 0, "Land", "", None),
]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.mark.parametrize("name", ["Magister Sphinx", "Dire Fleet Ravager", "Miner's Guidewing", "Barishi", "Sadistic Augermage",
                                  "Chimney Imp", "Phage the Untouchable", "Wormfang Newt", "Glimmerpost", "Earth Kingdom Jailer",
                                  "Rukh Egg"])
def test_coverage_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def cast(s, name, **m):
    spell = to_hand(s, name)
    mana(s, "p1", **m)
    act(s, "p1", type="cast_spell", card_id=spell.id)


def test_life_total_becomes_ten_gains_or_loses_the_difference(cards):
    # 119.5: Bob at 40 loses 30; Alice at 3 gains 7
    for target, start, end in (("p2", 40, 10), ("p1", 3, 10)):
        s = build(cards, ["Magister Sphinx"], [])
        act(s, target, type="set_life", player=target, value=start)
        cast(s, "Magister Sphinx", W=1, U=1, B=1, C=4)
        answer(s, target)
        assert s.state.players[target].life == end
        check(s)


def test_each_player_loses_a_third_of_their_life_rounded_up(cards):
    s = build(cards, ["Dire Fleet Ravager"], [])
    act(s, "p2", type="set_life", player="p2", value=20)
    cast(s, "Dire Fleet Ravager", B=2, C=3)
    answer(s)
    assert (life(s, "p1"), life(s, "p2")) == (26, 13)  # 107.1a: 40/3 = 13.33 -> 14 lost; 20/3 = 6.67 -> 7 lost
    check(s)


def test_phage_cast_from_hand_does_not_lose_the_game(cards):
    s = build(cards, ["Phage the Untouchable"], [])
    cast(s, "Phage the Untouchable", B=4, C=3)
    answer(s)
    assert card_named(s, "Phage the Untouchable").zone == "p1:battlefield" and "p1" not in s.state.rules.lost
    check(s)


def test_phage_put_onto_the_battlefield_without_casting_loses_the_game(cards):
    s = build(cards, ["Phage the Untouchable", "Test Reanimation"], [])
    phage = card_named(s, "Phage the Untouchable")
    act(s, "p1", type="move", card_ids=[phage.id], to={"zone": "graveyard"})
    cast(s, "Test Reanimation", B=1)
    answer(s, phage.id)
    assert card_named(s, "Phage the Untouchable").zone == "p1:battlefield" and "p1" in s.state.rules.lost
    check(s)


def test_wormfang_exiles_a_land_and_returns_it_when_it_leaves(cards):
    s = build(cards, ["Wormfang Newt"], [], forests=1)
    forest = next(c for c in s.state.cards.values() if c.name == "Forest" and c.owner == "p1")
    act(s, "p1", type="move", card_ids=[forest.id], to={"player": "p1", "zone": "battlefield"})
    cast(s, "Wormfang Newt", U=1, C=1)
    answer(s)
    assert s.state.cards[forest.id].zone == "p1:exile"  # chosen as the ability resolved (one land: no choice to make)
    kill(s, "Wormfang Newt")
    answer(s)
    assert s.state.cards[forest.id].zone == "p1:battlefield"  # the linked ability returns the exiled card (607.2a)
    check(s)

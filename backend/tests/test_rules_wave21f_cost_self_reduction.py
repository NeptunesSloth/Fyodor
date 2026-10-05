"""Wave 21F (cost_self_reduction). Real Oracle text, replay and save/load for each.

* 601.2f: the spell's own "This spell costs {N} less to cast for each …" counts what the table shows as the total cost is determined
  (the spell itself isn't cast yet: 601.2i, so "other spell cast this turn" doesn't count it).
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import coverage
from tests.fixtures.cards import fixture_cards
from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import answer, real
from tests.wave9c_kit import build, card_named, check, mana, to_hand

EXTRA = [
    real("Thrasta, Tempest's Roar", "{10}{G}{G}", 12, "Legendary Creature — Dinosaur",
         "This spell costs {3} less to cast for each other spell cast this turn.\nTrample, haste\nTrample over planeswalkers (This creature "
         "can deal excess combat damage to the controller of the planeswalker it's attacking.)\nThrasta has hexproof as long as it "
         "entered this turn.", ("7", "7"), "G"),
    real("Hollow One", "{5}", 5, "Artifact Creature — Golem", "This spell costs {2} less to cast for each card you've cycled or "
         "discarded this turn.\nCycling {2} ({2}, Discard this card: Draw a card.)", ("4", "4")),
    real("Gnoll War Band", "{5}{R}", 6, "Creature — Gnoll", "This spell costs {1} less to cast for each opponent who was dealt damage "
         "this turn.\nMenace\nMyriad (Whenever this creature attacks, for each opponent other than defending player, you may create a "
         "token copy that's tapped and attacking that player or a planeswalker they control. Exile the tokens at end of combat.)",
         ("5", "5"), "R"),
    real("Huskburster Swarm", "{7}{B}", 8, "Creature — Elemental Insect", "This spell costs {1} less to cast for each creature card you "
         "own in exile and in your graveyard.\nMenace, deathtouch", ("6", "6"), "B"),
    real("The Balrog, Durin's Bane", "{5}{B}{R}", 7, "Legendary Creature — Avatar Demon", "This spell costs {1} less to cast for each permanent "
         "sacrificed this turn.\nHaste\nThe Balrog can't be blocked except by legendary creatures.\nWhen The Balrog dies, destroy target "
         "artifact or creature an opponent controls.", ("7", "5"), "BR"),
    real("Valiant Changeling", "{5}{W}{W}", 7, "Creature — Shapeshifter", "This spell costs {1} less to cast for each creature type among "
         "creatures you control. This effect can't reduce the amount of mana this spell costs by more than {5}.\nChangeling (This card is "
         "every creature type.)\nDouble strike", ("3", "3"), "W"),
    real("Eris, Roar of the Storm", "{8}{U}{R}", 10, "Legendary Creature — Elemental Warlock", "This spell costs {2} less to cast for "
         "each different mana value among instant and sorcery cards in your graveyard.\nFlying, prowess\nWhenever you cast your second "
         "spell each turn, create a 4/4 red Dragon Elemental creature token with flying and prowess.", ("4", "4"), "UR"),
]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.mark.parametrize("name", [c["name"] for c in EXTRA])
def test_coverage_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def _cast_when(s, card, short, enough):
    """Casting with ``short`` mana fails; adding ``enough`` more lets it resolve onto the battlefield."""
    mana(s, **short)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=card.id)
    mana(s, **enough)
    act(s, "p1", type="cast_spell", card_id=card.id)
    answer(s)
    assert s.state.cards[card.id].zone == "p1:battlefield"
    check(s)


def test_each_other_spell_cast_this_turn_by_anyone(cards):
    s = build(cards, ["Thrasta, Tempest's Roar", "Lightning Bolt"])
    thrasta, bolt = to_hand(s, "Thrasta, Tempest's Roar"), to_hand(s, "Lightning Bolt")
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])
    answer(s)
    _cast_when(s, thrasta, {"G": 2, "C": 6}, {"C": 1})  # {10}{G}{G} less {3}: {7}{G}{G}


def test_cards_cycled_or_discarded_this_turn(cards):
    s = build(cards, ["Hollow One", "Hollow One"])
    first, second = [c for c in s.state.cards.values() if c.name == "Hollow One" and c.owner == "p1"]
    for c in (first, second):
        act(s, "p1", type="move", card_ids=[c.id], to={"zone": "hand"})
    mana(s, C=2)
    act(s, "p1", type="activate_ability", card_id=first.id, ability=1)  # cycling {2}: discards it
    answer(s)
    _cast_when(s, second, {"C": 2}, {"C": 1})  # {5} less {2}


def test_each_opponent_who_was_dealt_damage_this_turn(cards):
    s = build(cards, ["Gnoll War Band", "Lightning Bolt"])
    band, bolt = to_hand(s, "Gnoll War Band"), to_hand(s, "Lightning Bolt")
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])
    answer(s)
    _cast_when(s, band, {"R": 1, "C": 3}, {"C": 1})  # {5}{R} less {1}


def test_creature_cards_you_own_in_exile_and_your_graveyard(cards):
    s = build(cards, ["Huskburster Swarm", "Llanowar Elves", "Grizzly Bears"])
    swarm = to_hand(s, "Huskburster Swarm")
    act(s, "p1", type="move", card_ids=[card_named(s, "Llanowar Elves").id], to={"zone": "graveyard"})
    act(s, "p1", type="move", card_ids=[card_named(s, "Grizzly Bears").id], to={"zone": "exile"})
    _cast_when(s, swarm, {"B": 1, "C": 4}, {"C": 1})  # {7}{B} less {2}


def test_each_different_mana_value_among_instants_and_sorceries(cards):
    s = build(cards, ["Eris, Roar of the Storm", "Lightning Bolt", "Opt", "Murder"])
    eris = to_hand(s, "Eris, Roar of the Storm")
    for n in ("Lightning Bolt", "Opt", "Murder"):  # mana values 1, 1, 3: two different
        act(s, "p1", type="move", card_ids=[card_named(s, n).id], to={"zone": "graveyard"})
    _cast_when(s, eris, {"U": 1, "R": 1, "C": 3}, {"C": 1})  # {8}{U}{R} less {4}


def test_each_permanent_sacrificed_this_turn_by_anyone(cards):
    s = build(cards, ["The Balrog, Durin's Bane"])
    balrog = to_hand(s, "The Balrog, Durin's Bane")
    act(s, "p1", type="create_token", player="p1", token={"name": "Clue", "type_line": "Token Artifact — Clue", "colors": [], "power": None,
                                                           "toughness": None, "text": "{2}, Sacrifice this artifact: Draw a card."})
    clue = next(c for c in s.state.cards.values() if c.name == "Clue")
    mana(s, "p1", C=2)
    act(s, "p1", type="activate_ability", card_id=clue.id, ability=0)  # sacrificed as a cost
    answer(s)
    _cast_when(s, balrog, {"B": 1, "R": 1, "C": 3}, {"C": 1})  # {5}{B}{R} less {1}


def test_a_reduction_that_cant_reduce_by_more_than_five(cards):
    s = build(cards, ["Valiant Changeling", "Llanowar Elves", "Grizzly Bears", "Soul Warden", "Young Pyromancer", "Perilous Myr", "Ambush Viper"])
    changeling = to_hand(s, "Valiant Changeling")
    for n in ("Llanowar Elves", "Grizzly Bears", "Soul Warden", "Young Pyromancer", "Perilous Myr", "Ambush Viper"):
        act(s, "p1", type="move", card_ids=[card_named(s, n).id], to={"player": "p1", "zone": "battlefield"})
    _cast_when(s, changeling, {"W": 1}, {"W": 1})  # six types, capped at five less: {W}{W}

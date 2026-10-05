"""Review of wave 25B (CR 2026-09-25). Real Oracle text; every scenario checks the replay and a save and a load.

* 709.4 / 715.4 / 720.4 / 712.8a: a split card's half, an Adventure and an Omen are the whole card again once they leave the stack.
* 712.11b / 712.12: a modal double-faced card cast or played back face up stays back face up (leaving the hand resets the face).
* 715.2a / 720.2a: an omen card has an Omen, not an Adventure ("a creature spell that has an Adventure").
* Pack tactics: the total power of the creatures as they were declared as attackers (508.1), not as it is later.
* "Choose up to one target creature, then airbend all other creatures": "other" than the chosen one - refused.
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import coverage
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_wave5j_token_copies import drive
from tests.test_rules_wave12a_counters_keywords import answer
from tests.wave9c_kit import build, check, mana, put, to_hand, zone_of


def _face(name, mc, tl, text, p=None, t=None):
    return {"object": "card_face", "name": name, "mana_cost": mc, "type_line": tl, "oracle_text": text, "power": p, "toughness": t}


EXTRA = [
    card("Marang River Regent // Coil and Catch", set_code="t25r", number="R1", layout="adventure", mana_cost="{4}{U}{U} // {3}{U}", cmc=6.0,
         type_line="Creature — Dragon // Instant — Omen", colors=["U"], color_identity=["U"],
         card_faces=[_face("Marang River Regent", "{4}{U}{U}", "Creature — Dragon",
                           "Flying\nWhen this creature enters, return up to two other target nonland permanents to their owners' hands.", "6", "7"),
                     _face("Coil and Catch", "{3}{U}", "Instant — Omen",
                           "Draw three cards, then discard a card. (Then shuffle this card into its owner's library.)")]),
    card("Esika, God of the Tree // The Prismatic Bridge", set_code="t25r", number="R2", layout="modal_dfc", mana_cost="{1}{G}{G}", cmc=3.0,
         type_line="Legendary Creature — God // Legendary Enchantment", colors=["G"], color_identity=["W", "U", "B", "R", "G"],
         card_faces=[_face("Esika, God of the Tree", "{1}{G}{G}", "Legendary Creature — God",
                           "Vigilance\n{T}: Add one mana of any color.\nOther legendary creatures you control have vigilance and "
                           "\"{T}: Add one mana of any color.\"", "1", "4"),
                     _face("The Prismatic Bridge", "{W}{U}{B}{R}{G}", "Legendary Enchantment",
                           "At the beginning of your upkeep, reveal cards from the top of your library until you reveal a creature or "
                           "planeswalker card. Put that card onto the battlefield and the rest on the bottom of your library in a random order.")]),
    card("Valakut Awakening // Valakut Stoneforge", set_code="t25r", number="R3", layout="modal_dfc", mana_cost="{2}{R}", cmc=3.0,
         type_line="Instant // Land", colors=["R"], color_identity=["R"],
         card_faces=[_face("Valakut Awakening", "{2}{R}", "Instant",
                           "Put any number of cards from your hand on the bottom of your library, then draw that many cards plus one."),
                     _face("Valakut Stoneforge", "", "Land", "This land enters tapped.\n{T}: Add {R}.")]),
    card("Growing Rites of Itlimoc // Itlimoc, Cradle of the Sun", set_code="t25r", number="R4", layout="transform", mana_cost="{2}{G}", cmc=3.0,
         type_line="Legendary Enchantment // Legendary Land", colors=["G"], color_identity=["G"],
         card_faces=[_face("Growing Rites of Itlimoc", "{2}{G}", "Legendary Enchantment",
                           "When Growing Rites of Itlimoc enters, look at the top four cards of your library. You may reveal a creature card "
                           "from among them and put it into your hand. Put the rest on the bottom of your library in any order.\nAt the "
                           "beginning of your end step, if you control four or more creatures, transform Growing Rites of Itlimoc."),
                     _face("Itlimoc, Cradle of the Sun", "", "Legendary Land",
                           "(Transforms from Growing Rites of Itlimoc.)\n{T}: Add {G}.\n{T}: Add {G} for each creature you control.")]),
    card("Edgewall Innkeeper", set_code="t25r", number="R5", mana_cost="{G}", cmc=1.0, type_line="Creature — Human Peasant", power="1",
         toughness="1", colors=["G"], color_identity=["G"],
         oracle_text="Whenever you cast a creature spell that has an Adventure, draw a card. (It doesn't need to have gone on the adventure first.)"),
    card("Avatar's Wrath", set_code="t25r", number="R6", mana_cost="{2}{W}{W}", cmc=4.0, type_line="Sorcery", colors=["W"], color_identity=["W"],
         oracle_text="Choose up to one target creature, then airbend all other creatures. (Exile them. While each one is exiled, its owner may "
                     "cast it for {2} rather than its mana cost.)\nUntil your next turn, your opponents can't cast spells from anywhere other "
                     "than their hands.\nExile Avatar's Wrath."),
    card("Gnoll Hunter", set_code="t25r", number="R7", mana_cost="{1}{G}", cmc=2.0, type_line="Creature — Gnoll", power="2", toughness="2",
         colors=["G"], color_identity=["G"],
         oracle_text="Pack tactics — Whenever this creature attacks, if you attacked with creatures with total power 6 or greater this combat, "
                     "put a +1/+1 counter on this creature."),
    card("Probe Brute", set_code="t25r", number="R8", mana_cost="{3}", cmc=3.0, type_line="Creature — Ogre", power="4", toughness="4"),
]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def chars(s, c):
    return Plan(s.state, "p1", s.cards, None).ch(s.state.cards[c.id])


def test_an_adventure_that_resolved_is_the_creature_card_in_exile(cards):
    s = build(cards, ["Bonecrusher Giant // Stomp"])
    giant = to_hand(s, "Bonecrusher Giant // Stomp")
    mana(s, R=2)
    act(s, "p1", type="cast_spell", card_id=giant.id, face=1, targets=["p2"])
    answer(s)
    assert zone_of(s, "Bonecrusher Giant // Stomp") == "p1:exile"
    ch = chars(s, giant)
    assert ch.name == "Bonecrusher Giant" and "Creature" in ch.types  # 715.4
    mana(s, R=3)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=giant.id, face=1, targets=["p2"])  # (715.3d: not as an Adventure again)
    act(s, "p1", type="cast_spell", card_id=giant.id)  # (715.3d: the creature from exile)
    answer(s)
    assert zone_of(s, "Bonecrusher Giant // Stomp") == "p1:battlefield"
    check(s)


def test_a_split_cards_second_half_is_the_whole_card_in_the_graveyard(cards):
    s = build(cards, ["Fire // Ice", "Bonecrusher Giant // Stomp"])
    fire_ice = to_hand(s, "Fire // Ice")
    target = put(s, "Bonecrusher Giant // Stomp")
    mana(s, U=2)
    act(s, "p1", type="cast_spell", card_id=fire_ice.id, face=1, targets=[target.id])
    answer(s)
    assert zone_of(s, "Fire // Ice") == "p1:graveyard"
    ch = chars(s, fire_ice)
    assert ch.name == "Fire // Ice" and ch.mana_value == 4  # 709.4, 709.4b
    check(s)


def test_a_modal_double_faced_card_cast_back_face_up_resolves_back_face_up(cards):
    s = build(cards, ["Esika, God of the Tree // The Prismatic Bridge"])
    esika = to_hand(s, "Esika, God of the Tree // The Prismatic Bridge")
    mana(s, W=1, U=1, B=1, R=1, G=1)
    act(s, "p1", type="cast_spell", card_id=esika.id, face=1)
    answer(s)
    assert zone_of(s, "Esika, God of the Tree // The Prismatic Bridge") == "p1:battlefield"
    assert chars(s, esika).name == "The Prismatic Bridge"
    check(s)


def test_a_modal_double_faced_land_played_back_face_up_and_a_transforming_card_cant_be(cards):
    s = build(cards, ["Valakut Awakening // Valakut Stoneforge", "Growing Rites of Itlimoc // Itlimoc, Cradle of the Sun"])
    valakut = to_hand(s, "Valakut Awakening // Valakut Stoneforge")
    rites = to_hand(s, "Growing Rites of Itlimoc // Itlimoc, Cradle of the Sun")
    with pytest.raises(ActionError):
        act(s, "p1", type="play_land", card_id=rites.id, face=1)  # (712.12 is for modal double-faced cards only)
    act(s, "p1", type="play_land", card_id=valakut.id, face=1)
    assert zone_of(s, "Valakut Awakening // Valakut Stoneforge") == "p1:battlefield"
    assert chars(s, valakut).name == "Valakut Stoneforge" and s.state.cards[valakut.id].tapped  # 712.12 ("enters tapped")
    check(s)


@pytest.mark.parametrize("name,draws", [("Marang River Regent // Coil and Catch", 0), ("Bonecrusher Giant // Stomp", 1)])
def test_an_omen_card_does_not_have_an_adventure(cards, name, draws):
    s = build(cards, ["Edgewall Innkeeper", name])
    put(s, "Edgewall Innkeeper")
    spell = to_hand(s, name)
    mana(s, U=6, R=3)
    library = len(s.state.zones["p1:library"])
    act(s, "p1", type="cast_spell", card_id=spell.id, face=0)
    answer(s)
    assert library - len(s.state.zones["p1:library"]) == draws  # 715.2a / 720.2a
    check(s)


def test_an_omen_spell_is_shuffled_into_its_owners_library(cards):
    s = build(cards, ["Marang River Regent // Coil and Catch"])
    regent = to_hand(s, "Marang River Regent // Coil and Catch")
    mana(s, U=4)
    act(s, "p1", type="cast_spell", card_id=regent.id, face=1)
    answer(s)
    assert zone_of(s, "Marang River Regent // Coil and Catch") == "p1:library"  # 720.3d
    check(s)


def test_avatars_wrath_is_refused():
    c = next(c for c in EXTRA if c["name"] == "Avatar's Wrath")
    assert coverage.of_card_data({**c, "faces": []}).level != "FULL"


def test_pack_tactics_reads_the_total_power_as_the_attackers_were_declared(cards):
    """2 + 4 = 6 as declared: the creature that shrinks before the trigger resolves doesn't undo it (508.1, 603.4)."""
    s = build(cards, ["Gnoll Hunter", "Probe Brute"])
    hunter, brute = put(s, "Gnoll Hunter"), put(s, "Probe Brute")
    for c in (hunter, brute):
        s.state.rules.controlled_since[c.id].turn = 0
    act(s, "p1", type="pass_priority")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": c.id, "target": "p2"} for c in (hunter, brute)])
    act(s, "p1", type="counter", card_ids=[brute.id], kind="-1/-1", delta=1)  # (now 2 + 3 = 5)
    drive(s)
    assert s.state.cards[hunter.id].counters.get("+1/+1") == 1
    check(s)

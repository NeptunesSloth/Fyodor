"""Review of wave 22D (resolution memory & linked objects; CR 2026-09-25). Real Oracle text; replay and save/load checked.

* 607.2q: only an ability printed on the permanent spell links the cards exiled to pay its cost; an escape cost granted by another
  permanent (Underworld Breach) is not printed on the spell, so those cards are not "exiled with" it.
* 610.3 / 800.4a: a card exiled from a hand "until ~ leaves" returns to its owner's hand when the exiling player leaves the game.
* 607.2a / 406.3: a card exiled face down isn't played through "cards exiled with ~" by a player who can't see it.
"""

from __future__ import annotations

import pytest

from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from app.rules.plan import Plan
from tests.fixtures.cards import fixture_cards
from tests.game_helpers import act, deck, enable
from tests.test_rules_effects import mana, pass_until_stack_empty, replay_matches, run_until
from tests.test_rules_wave9b_exile_permission import answer, build, put, roundtrip
from tests.test_rules_wave12a_counters_keywords import real

EXTRA = [
    real("Necromantic Selection", "{4}{B}{B}{B}", 7, "Sorcery",
         "Destroy all creatures, then return a creature card put into a graveyard this way to the battlefield under your control. It's a black Zombie in addition to its other colors and types. Exile Necromantic Selection.",
         None, "B"),
    real("Skyclave Apparition", "{1}{W}{W}", 3, "Creature — Kor Wizard",
         "When this creature enters, exile up to one target nonland, nontoken permanent you don't control with mana value 4 or less.\nWhen this creature leaves the battlefield, the exiled card's owner creates an X/X blue Illusion creature token, where X is the mana value of the exiled card.",
         ("2", "2"), "W"),
    real("Knowledge Vault", "{4}", 4, "Artifact",
         "{2}, {T}: Exile the top card of your library face down.\n{0}: Sacrifice this artifact. If you do, discard your hand, then put all cards exiled with this artifact into their owner's hand.\nWhen this artifact leaves the battlefield, put all cards exiled with it into their owner's graveyard.",
         None),
    real("Brain Maggot", "{1}{B}", 2, "Enchantment Creature — Insect",
         "When this creature enters, target opponent reveals their hand and you choose a nonland card from it. Exile that card until this creature leaves the battlefield.",
         ("1", "1"), "B"),
    real("Promise of Tomorrow", "{2}{W}", 3, "Enchantment",
         "Whenever a creature you control dies, exile it.\nAt the beginning of each end step, if you control no creatures, sacrifice this enchantment and return all cards exiled with it to the battlefield under your control.",
         None, "W"),
    real("Underworld Breach", "{1}{R}", 2, "Enchantment",
         "Each nonland card in your graveyard has escape. The escape cost is equal to the card's mana cost plus exile three other cards from your graveyard. (You may cast cards from your graveyard for their escape cost.)\nAt the beginning of the end step, sacrifice this enchantment.",
         None, "R"),
    real("Severance Priest", "{W}{B}{G}", 3, "Creature — Djinn Cleric",
         "Deathtouch\nWhen this creature enters, target opponent reveals their hand. You may choose a nonland card from it. If you do, exile that card.\nWhen this creature leaves the battlefield, the exiled card's owner creates an X/X white Spirit creature token, where X is the mana value of the exiled card.",
         ("3", "3"), "WBG"),
    real("Random Encounter", "{4}{R}{R}", 6, "Sorcery",
         "Shuffle your library, then mill four cards. Put each creature card milled this way onto the battlefield. They gain haste. At the beginning of the next end step, return those creatures to their owner's hand.\nFlashback {6}{R}{R} (You may cast this card from your graveyard for its flashback cost. Then exile it.)",
         None, "R"),
    real("Unlicensed Hearse", "{2}", 2, "Artifact — Vehicle",
         "{T}: Exile up to two target cards from a single graveyard.\nUnlicensed Hearse's power and toughness are each equal to the number of cards exiled with it.\nCrew 2",
         ("*", "*")),
    real("Theater of Horrors", "{1}{B}{R}", 3, "Enchantment",
         "At the beginning of your upkeep, exile the top card of your library.\nDuring your turn, if an opponent lost life this turn, you may play lands and cast spells from among cards exiled with this enchantment.\n{3}{R}: This enchantment deals 1 damage to target opponent or planeswalker.",
         None, "BR"),
    real("Probe Rock", "{3}", 3, "Artifact", "", None),
    real("Probe Smash", "{1}{R}", 2, "Instant", "Destroy target artifact.", None, "R"),
    real("Probe Two", "{1}{G}", 2, "Creature — Beast", "", ("2", "2"), "G"),
    real("Probe Four", "{3}{G}", 4, "Creature — Beast", "", ("4", "4"), "G"),
]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def build3(cards, p1=(), p2=(), p3=()):
    decks = [deck(cards, "Krenko, Mob Boss", [*((1, n) for n in p1), (9, "Forest")]),
             deck(cards, "Atraxa, Praetors' Voice", [*((1, n) for n in p2), (10, "Island")]),
             deck(cards, "Atraxa, Praetors' Voice", [*((1, n) for n in p3), (10, "Island")])]
    s = GameSession(enable(new_game([PlayerSetup(n, cards=d) for n, d in zip(("Alice", "Bob", "Carol"), decks, strict=True)], shuffle=False)), cards=cards)
    act(s, "p1", type="pass_priority")
    return s


def ch(s, cid):
    from app.rules.plan import Plan

    return Plan(s.state, "p1", s.cards, None).ch(s.state.cards[cid])


def power(s, cid):
    from app.rules import sba

    c = s.state.cards[cid]
    return sba.power(c, ch(s, cid)), sba.toughness(c, ch(s, cid))


def zone(s, cid):
    return s.state.cards[cid].zone


def test_brain_maggot_card_goes_back_to_the_hand_when_its_controller_leaves_the_game(cards):
    s = build3(cards, p1=("Brain Maggot",), p2=("Probe Rock",))
    rock = put(s, "Probe Rock", "hand", pid="p2")
    maggot = put(s, "Brain Maggot", "hand")
    mana(s, B=1, C=1)
    act(s, "p1", type="cast_spell", card_id=maggot.id)
    pass_until_stack_empty(s)
    d = s.state.rules.decision
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["p2"])
    pass_until_stack_empty(s)
    answer(s, pick=rock.id)
    assert zone(s, rock.id) == "p2:exile"
    roundtrip(s)
    act(s, "p1", type="concede")  # 800.4a: Brain Maggot leaves the game with Alice; 610.3 the card returns to its previous zone
    answer(s)
    assert zone(s, rock.id) == "p2:hand"
    assert "p3" not in (s.state.cards[rock.id].revealed_to or [])
    replay_matches(s)


def test_brain_maggot_with_the_hand_owner_gone(cards):
    s = build3(cards, p1=("Brain Maggot",), p2=("Probe Rock",))
    rock = put(s, "Probe Rock", "hand", pid="p2")
    maggot = put(s, "Brain Maggot", "hand")
    mana(s, B=1, C=1)
    act(s, "p1", type="cast_spell", card_id=maggot.id)
    pass_until_stack_empty(s)
    d = s.state.rules.decision
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["p2"])
    pass_until_stack_empty(s)
    answer(s, pick=rock.id)
    act(s, "p2", type="concede")
    answer(s)
    act(s, "p1", type="set_damage", card_ids=[maggot.id], value=1)
    act(s, s.state.rules.priority, type="pass_priority")
    answer(s)
    assert not (rock.id in s.state.cards and zone(s, rock.id) in ("p2:hand", "p1:hand"))
    roundtrip(s)


def test_cards_exiled_by_a_granted_escape_cost_are_not_exiled_with_the_permanent(cards):
    """607.2q: Promise of Tomorrow cast with Underworld Breach's escape: the three cards exiled to pay aren't linked to it."""
    s = build(cards, p1=("Promise of Tomorrow", "Underworld Breach", "Probe Two", "Probe Four", "Ambush Viper"))
    put(s, "Underworld Breach", "battlefield")
    promise = put(s, "Promise of Tomorrow", "graveyard")
    paid = [put(s, n, "graveyard") for n in ("Probe Two", "Probe Four", "Ambush Viper")]
    mana(s, W=1, C=2)
    act(s, "p1", type="cast_spell", card_id=promise.id)
    answer(s)
    assert zone(s, promise.id) == "p1:battlefield" and all(zone(s, c.id) == "p1:exile" for c in paid)
    assert not s.state.rules.exiled_with.get(s.state.rules.object_id(promise.id))
    roundtrip(s)


def test_severance_priest_token_for_the_owner_in_multiplayer_and_none_when_the_owner_left(cards):
    s = build3(cards, p1=("Severance Priest",), p2=("Probe Four",))
    four = put(s, "Probe Four", "hand", pid="p2")
    priest = put(s, "Severance Priest", "hand")
    mana(s, W=1, B=1, G=1)
    act(s, "p1", type="cast_spell", card_id=priest.id)
    pass_until_stack_empty(s)
    d = s.state.rules.decision
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["p2"])
    answer(s, pick=four.id)
    assert zone(s, four.id) == "p2:exile"
    roundtrip(s)
    act(s, "p1", type="set_damage", card_ids=[priest.id], value=3)
    act(s, s.state.rules.priority, type="pass_priority")
    answer(s)
    spirits = [c for c in s.state.cards.values() if c.name == "Spirit" and c.zone.endswith(":battlefield")]
    assert [c.zone for c in spirits] == ["p2:battlefield"]
    roundtrip(s)


def test_random_encounter_haste_only_for_what_entered_and_they_return(cards):
    s = build(cards, p1=("Random Encounter", "Probe Two", "Probe Four"))
    spell = put(s, "Random Encounter", "hand")
    two, four = put(s, "Probe Two", "library", position="top"), put(s, "Probe Four", "library", position="top")
    forests = [c for c in s.state.zones["p1:library"] if s.state.cards[c].name == "Forest"]
    act(s, "p1", type="move", card_ids=forests[1:], to={"player": "p1", "zone": "exile"})  # it's shuffled first: three cards left
    act(s, "p1", type="move", card_ids=forests[1:2], to={"player": "p1", "zone": "battlefield"})
    lands = forests[:1]
    mana(s, R=2, C=4)
    act(s, "p1", type="cast_spell", card_id=spell.id)
    answer(s)
    entered = [c for c in (two.id, four.id) if zone(s, c) == "p1:battlefield"]
    roundtrip(s)
    graveyard = [s.state.cards[c].name for c in s.state.zones["p1:graveyard"]]
    assert len(entered) == 2 and graveyard.count("Forest") == len(lands) == 1  # each creature card milled; not the land
    for c in s.state.cards.values():
        if c.zone == "p1:battlefield" and not c.is_token:
            assert ("haste" in ch(s, c.id).keywords) == (c.id in entered)  # "They": the creatures put onto the battlefield only
    run_until(s, lambda s: s.state.turn.number == 2)
    assert all(zone(s, c) == "p1:hand" for c in entered)
    replay_matches(s)


def test_unlicensed_hearse_counts_only_what_is_still_exiled_with_it(cards):
    s = build(cards, p1=("Unlicensed Hearse", "Probe Two", "Probe Four", "Grizzly Bears"))
    hearse = put(s, "Unlicensed Hearse", "battlefield")
    pilot = put(s, "Grizzly Bears", "battlefield")
    two, four = put(s, "Probe Two", "graveyard"), put(s, "Probe Four", "graveyard")
    act(s, "p1", type="activate_ability", card_id=hearse.id, ability=0, targets=[two.id, four.id], target_counts=[2])
    answer(s)
    crew = next(a.index for a in Plan(s.state, "p1", s.cards, None).ch(s.state.cards[hearse.id]).abilities if a.text.startswith("Crew"))
    act(s, "p1", type="activate_ability", card_id=hearse.id, ability=crew, crew=[pilot.id])  # (a Vehicle has P/T only as a creature, 301.7a)
    answer(s)
    assert zone(s, two.id) == "p1:exile" and power(s, hearse.id) == (2, 2)
    roundtrip(s)
    put(s, "Probe Two", "hand")  # it left exile: a new object (400.7)
    assert power(s, hearse.id) == (1, 1)
    roundtrip(s)


def test_skyclave_apparition_makes_no_token_for_an_owner_who_left(cards):
    s = build3(cards, p1=("Skyclave Apparition",), p2=("Probe Rock",))
    rock = put(s, "Probe Rock", "battlefield", pid="p2")
    sky = put(s, "Skyclave Apparition", "hand")
    mana(s, W=2, C=1)
    act(s, "p1", type="cast_spell", card_id=sky.id)
    answer(s, pick=rock.id)
    assert zone(s, rock.id) == "p2:exile"
    act(s, "p2", type="concede")
    answer(s)
    act(s, "p1", type="set_damage", card_ids=[sky.id], value=2)
    act(s, s.state.rules.priority, type="pass_priority")
    answer(s)
    assert not [c for c in s.state.cards.values() if c.is_token and c.name == "Illusion"]
    roundtrip(s)


def test_necromantic_selection_takes_another_players_creature_card_in_multiplayer(cards):
    s = build3(cards, p1=("Necromantic Selection", "Probe Two"), p2=("Probe Four",), p3=("Ambush Viper",))
    put(s, "Probe Two", "battlefield")
    four = put(s, "Probe Four", "battlefield", pid="p2")
    viper = put(s, "Ambush Viper", "battlefield", pid="p3")
    sp = put(s, "Necromantic Selection", "hand")
    mana(s, B=3, C=4)
    act(s, "p1", type="cast_spell", card_id=sp.id)
    answer(s, pick=four.id)
    c = s.state.cards[four.id]
    assert c.zone.endswith(":battlefield") and c.controller == "p1" and "Zombie" in ch(s, four.id).subtypes and "B" in ch(s, four.id).colors
    assert zone(s, viper.id) == "p3:graveyard" and zone(s, sp.id) == "p1:exile"
    roundtrip(s)


def test_knowledge_vault_face_down_cards_go_to_the_graveyard_when_it_leaves(cards):
    from app.game.views import card_view

    s = build(cards, p1=("Knowledge Vault", "Probe Two", "Probe Smash"))
    vault = put(s, "Knowledge Vault", "battlefield")
    two = put(s, "Probe Two", "library", position="top")
    mana(s, C=2)
    act(s, "p1", type="activate_ability", card_id=vault.id, ability=0)
    answer(s)
    assert zone(s, two.id) == "p1:exile" and s.state.cards[two.id].face_down
    assert card_view(s.state, s.state.cards[two.id], "p2").get("name") != "Probe Two"  # hidden (406.3)
    roundtrip(s)
    smash = put(s, "Probe Smash", "hand")
    mana(s, R=1, C=1)
    act(s, "p1", type="cast_spell", card_id=smash.id, targets=[vault.id])
    answer(s)
    assert zone(s, vault.id) == "p1:graveyard"
    assert zone(s, two.id) == "p1:graveyard"
    roundtrip(s)


def test_linked_play_over_face_down_exile_is_not_read():
    from app.rules import permissions

    play = "You may play cards exiled with ~"
    assert permissions.define_static(play, "static", ("{2}, {T}: Exile the top card of your library face down.", play)) is None
    assert permissions.define_static(play, "static", ("{2}, {T}: Exile the top card of your library.", play)) is not None


def test_theater_of_horrors_only_during_your_turn_and_only_for_you(cards):
    from app.rules.casting import castable

    s = build(cards, p1=("Theater of Horrors", "Lightning Bolt"))
    put(s, "Theater of Horrors", "battlefield")
    bolt = put(s, "Lightning Bolt", "library", position="top")
    run_until(s, lambda s: s.state.turn.number == 3 and s.state.turn.phase == "main1")
    assert zone(s, bolt.id) == "p1:exile"
    run_until(s, lambda s: s.state.turn.number == 4 and s.state.turn.phase == "main1")  # Bob's turn
    act(s, "p2", type="life", player="p2", delta=-1)
    mana(s, R=1)
    mana(s, "p2", R=1)
    assert not castable(s.state, "p1", s.state.cards[bolt.id], cards)  # "During your turn"
    assert not castable(s.state, "p2", s.state.cards[bolt.id], cards)  # only for the enchantment's controller
    roundtrip(s)
    run_until(s, lambda s: s.state.turn.number == 5 and s.state.turn.phase == "main1")
    act(s, "p2", type="life", player="p2", delta=-1)
    mana(s, R=1)
    assert castable(s.state, "p1", s.state.cards[bolt.id], cards)  # (the control: Alice's turn, Bob lost life)

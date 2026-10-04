"""Wave 15B: the trigger long tail (CR 2026-09-25). Real Oracle text; every scenario checks the replay and a save and a load.

* 603.2: "When you cycle this card and when this creature dies" / "When you cast this spell and whenever this creature
  attacks" is one ability with two trigger conditions; it triggers on each.
* 700.4 / 608.2h: "for each Zubera that died this turn" counts the creatures put into a graveyard from the battlefield this
  turn, the one that died included, as they last existed.
"""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.fixtures.cards import fixture_cards
from tests.game_helpers import act
from tests.test_rules_effects import mana
from tests.test_rules_wave12a_counters_keywords import answer, real
from tests.wave9c_kit import build, card_named, check, put, to_hand

EXTRA = [
    real("Bant Sojourners", "{3}{W}{U}", 5, "Creature — Human Soldier",
         "Cycling {2}\nWhen you cycle this card and when this creature dies, you may create a 1/1 white Soldier creature token.",
         ("3", "3"), "WU"),
    real("Cityscape Leveler", "{8}", 8, "Artifact Creature — Construct",
         "Trample\nWhen you cast this spell and whenever this creature attacks, destroy up to one target nonland permanent. "
         "Its controller creates a tapped Powerstone token.\nUnearth {8}", ("8", "8")),
    real("Silent-Chant Zubera", "{3}{W}", 4, "Creature — Zubera Spirit",
         "When this creature dies, you gain 2 life for each Zubera that died this turn.", ("1", "2"), "W"),
    real("Dripping-Tongue Zubera", "{2}{G}", 3, "Creature — Zubera Spirit",
         "When this creature dies, create a 1/1 colorless Spirit creature token for each Zubera that died this turn.",
         ("2", "2"), "G"),
]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.mark.parametrize("name", ["Bant Sojourners", "Cityscape Leveler", "Silent-Chant Zubera", "Dripping-Tongue Zubera"])
def test_coverage_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


EXTRA += [
    real("Kozilek, Butcher of Truth", "{8}{C}{C}", 10, "Legendary Creature — Eldrazi",
         "When you cast this spell, draw four cards.\nAnnihilator 4\nWhen Kozilek is put into a graveyard from anywhere, its owner "
         "shuffles their graveyard into their library.", ("12", "12")),
    real("Wiccan, Young Avenger", "{1}{U}{R}", 3, "Legendary Creature — Human Wizard",
         "Whenever you cast a noncreature spell, exile the top card of your library. Until your next end step, you may play that card.",
         ("2", "2"), "UR"),
    real("Kinetic Augur", "{3}{R}", 4, "Creature — Human Wizard",
         "When this creature enters, discard up to two cards, then draw that many cards.", ("2", "3"), "R"),
    real("Armed with Proof", "{3}", 3, "Enchantment", "When this enchantment enters, investigate twice.", None),
    real("Teapot Slinger", "{3}{R}", 4, "Creature — Raccoon Warrior", "Menace\nWhenever you expend 4, this creature deals 2 damage to each opponent.", ("3", "3"), "R"),
    real("Raise the Alarm Copy", "{1}{W}", 2, "Instant", "Create two 1/1 white Soldier creature tokens.", None, "W"),
    real("God-Eternal Oketra", "{3}{W}{B}", 5, "Legendary Creature — Zombie God", "Double strike\nWhenever you cast a Zombie creature spell, create a 4/4 black Zombie Warrior creature token with vigilance.\nWhen God-Eternal Oketra dies or is put into exile from the battlefield, you may put it into its owner's library third from the top.", ("3", "6"), "WB"),
    real("The Endstone", "{3}", 3, "Artifact", "Whenever you play a land or cast a spell, draw a card.", None),
    real("Unshakable Tail", "{1}{W}", 2, "Creature — Cat Rogue", "Menace\nWhen this creature enters and at the beginning of your upkeep, surveil 1.", ("1", "1"), "W"),
    real("Intimidation Campaign", "{3}{B}", 4, "Enchantment", "When this enchantment enters, each opponent loses 1 life, you gain 1 life, and you draw a card.\nWhenever you cast a creature spell, you may return this enchantment to its owner's hand.", None, "B"),
    real("Weapons Manufacturing", "{2}{R}", 3, "Enchantment", "Whenever a nontoken artifact you control enters, create a colorless artifact token named Munitions with \"When this token leaves the battlefield, it deals 2 damage to any target.\"", None, "R"),
    real("Esgaroth Garrison", "{2}{W}", 3, "Creature — Human Soldier", "When this creature enters, recruit. (Draw a card, then discard a card. If you discarded a nonland card, create a 1/1 white Human Soldier creature token.)", ("2", "2"), "W"),
    real("Affectionate Indrik", "{4}{G}", 5, "Creature — Beast", "When this creature enters, you may have it fight target creature you don't control.", ("4", "4"), "G"),
    real("Vernal Sovereign", "{3}{G}{W}", 5, "Creature — Elemental", "Whenever this creature enters or attacks, create a green and white Elemental creature token with \"This token's power and toughness are each equal to the number of creatures you control.\"", ("4", "4"), "GW"),
    real("Preeminent Captain", "{2}{W}", 3, "Creature — Kithkin Soldier", "First strike\nWhenever this creature attacks, you may put a Soldier creature card from your hand onto the battlefield tapped and attacking.", ("2", "2"), "W"),
    real("Test Soldier", "{1}{W}", 2, "Creature — Human Soldier", "", ("1", "1"), "W"),
    real("Serra Avatar", "{4}{W}{W}", 6, "Creature — Avatar",
         "Serra Avatar's power and toughness are each equal to your life total.\nWhen Serra Avatar is put into a graveyard from "
         "anywhere, shuffle it into its owner's library.", ("*", "*"), "W"),
]


def on_battlefield(s, name, pid="p1"):
    return [c for c in s.state.cards.values() if c.name == name and c.zone == f"{pid}:battlefield"]


def kill(s, name, pid="p1"):
    """Lethal damage, then the state-based actions (704.5g) put it into the graveyard: it dies (700.4)."""
    act(s, pid, type="set_damage", card_ids=[card_named(s, name, pid).id], value=20)
    act(s, s.state.rules.priority or "p1", type="pass_priority")
    answer(s)


def test_cycle_and_dies_both_trigger_one_ability(cards):
    s = build(cards, ["Bant Sojourners"], [])
    sojourners = to_hand(s, "Bant Sojourners")
    mana(s, "p1", C=2)
    act(s, "p1", type="activate_ability", card_id=sojourners.id, ability=0)  # Cycling {2}
    answer(s)
    assert len(on_battlefield(s, "Soldier")) == 1  # cycled: the trigger (702.29c)
    check(s)
    s = build(cards, ["Bant Sojourners"], [])
    put(s, "Bant Sojourners")
    kill(s, "Bant Sojourners")
    answer(s)
    assert len(on_battlefield(s, "Soldier")) == 1  # died: the same ability
    check(s)


def test_zubera_count_includes_every_zubera_that_died_this_turn(cards):
    s = build(cards, ["Silent-Chant Zubera", "Dripping-Tongue Zubera"], [])
    put(s, "Silent-Chant Zubera")
    put(s, "Dripping-Tongue Zubera")
    kill(s, "Dripping-Tongue Zubera")
    answer(s)
    assert len(on_battlefield(s, "Spirit")) == 1
    kill(s, "Silent-Chant Zubera")
    answer(s)
    assert s.state.players["p1"].life == 44  # two Zubera died this turn: 2 life each
    check(s)


def test_put_into_a_graveyard_from_anywhere_works_from_the_graveyard(cards):
    # 603.6c: never a leaves-the-battlefield ability; the card's new object in the graveyard triggers (once)
    s = build(cards, ["Kozilek, Butcher of Truth", "Lightning Bolt"], [])
    put(s, "Kozilek, Butcher of Truth")
    act(s, "p1", type="move", card_ids=[card_named(s, "Lightning Bolt").id], to={"zone": "graveyard"})
    kill(s, "Kozilek, Butcher of Truth")
    assert [c.name for c in s.state.cards.values() if c.zone == "p1:graveyard"] == []
    assert {"Kozilek, Butcher of Truth", "Lightning Bolt"} <= {c.name for c in s.state.cards.values() if c.zone == "p1:library"}
    check(s)


def test_shuffle_it_into_its_owners_library_after_dying(cards):
    s = build(cards, ["Serra Avatar"], [])
    put(s, "Serra Avatar")
    act(s, "p1", type="set_damage", card_ids=[card_named(s, "Serra Avatar").id], value=99)
    act(s, s.state.rules.priority or "p1", type="pass_priority")
    answer(s)
    assert card_named(s, "Serra Avatar").zone == "p1:library"
    check(s)


def test_until_your_next_end_step_ends_as_that_end_step_begins(cards):
    # 611.2a: Wiccan exiles the top card; it may be played until the beginning of the controller's next end step
    s = build(cards, ["Wiccan, Young Avenger", "Opt"], [])
    put(s, "Wiccan, Young Avenger")
    opt = to_hand(s, "Opt")
    top = s.state.zones["p1:library"][0]
    mana(s, "p1", U=1)
    act(s, "p1", type="cast_spell", card_id=opt.id)
    answer(s)
    assert s.state.cards[top].zone == "p1:exile" and [p.until for p in s.state.rules.permissions] == ["next_end_step"]
    for _ in range(40):
        if s.state.turn.number == 2:
            break
        assert [p.until for p in s.state.rules.permissions] == ["next_end_step"]  # until the end step begins
        d = s.state.rules.decision
        if d is not None:
            act(s, d.player, type="declare_attackers", attackers=[])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    assert s.state.rules.permissions == []  # it ended as the end step began (the engine does not stop there)
    check(s)


def test_discard_up_to_two_then_draw_that_many(cards):
    # 701.9a: the player chooses how many (0 to 2); "that many" is the cards discarded this way, not a guess
    for chosen, drawn in ((1, 1), (0, 0)):
        s = build(cards, ["Kinetic Augur"], [])
        act(s, "p1", type="draw", player="p1", count=3)
        augur = to_hand(s, "Kinetic Augur")
        hand = [c for c in s.state.zones["p1:hand"] if c != augur.id]
        mana(s, "p1", R=1, C=3)
        act(s, "p1", type="cast_spell", card_id=augur.id)
        d = s.state.rules.decision
        act(s, "p1", type="choose", decision_id=d.id, option_ids=hand[:chosen])
        answer(s)
        assert len(s.state.zones["p1:hand"]) == len(hand) - chosen + drawn
        assert len(s.state.zones["p1:graveyard"]) == chosen
        check(s)


def test_investigate_twice_makes_two_clues(cards):
    s = build(cards, ["Armed with Proof"], [])
    spell = to_hand(s, "Armed with Proof")
    mana(s, "p1", C=3)
    act(s, "p1", type="cast_spell", card_id=spell.id)
    answer(s)
    assert len(on_battlefield(s, "Clue")) == 2  # 701.16a
    check(s)


def test_expend_four_triggers_once_when_the_fourth_mana_is_spent_on_spells(cards):
    # 700.14: you expend 4 as you spend your fourth total mana to cast spells during a turn
    s = build(cards, ["Teapot Slinger", "Raise the Alarm", "Raise the Alarm Copy"], ["Grizzly Bears"])
    put(s, "Teapot Slinger")
    for name, expected in (("Raise the Alarm", 40), ("Raise the Alarm Copy", 38)):
        spell = to_hand(s, name)
        mana(s, "p1", W=2)
        act(s, "p1", type="cast_spell", card_id=spell.id)
        answer(s)
        assert s.state.players["p2"].life == expected  # the second spell reaches the fourth mana: 2 damage, once
    check(s)


def test_dies_puts_it_third_from_the_top_of_its_owners_library(cards):
    # 400.7e: the card in the graveyard is a new object, found there; 401.4 the library's third card from the top
    s = build(cards, ["God-Eternal Oketra"], [])
    put(s, "God-Eternal Oketra")
    kill(s, "God-Eternal Oketra")
    answer(s, "yes")
    assert s.state.zones["p1:library"].index(card_named(s, "God-Eternal Oketra").id) == 2
    check(s)


def test_play_a_land_or_cast_a_spell_triggers_on_each(cards):
    s = build(cards, ["The Endstone", "Opt"], [])
    put(s, "The Endstone")
    forest = to_hand(s, "Forest")
    hand0 = len(s.state.zones["p1:hand"])
    act(s, "p1", type="play_land", card_id=forest.id)
    answer(s)
    assert len(s.state.zones["p1:hand"]) == hand0  # -1 land played, +1 drawn
    opt = to_hand(s, "Opt")
    before = len(s.state.zones["p1:hand"])
    mana(s, "p1", U=1)
    act(s, "p1", type="cast_spell", card_id=opt.id)
    answer(s)
    assert len(s.state.zones["p1:hand"]) == before - 1 + 2  # Opt cast, +1 from The Endstone, +1 from Opt
    check(s)


def test_enters_and_at_the_beginning_of_your_upkeep_is_one_ability_with_two_conditions(cards):
    s = build(cards, ["Unshakable Tail"], [])
    tail = to_hand(s, "Unshakable Tail")
    mana(s, "p1", W=1, C=2)
    act(s, "p1", type="cast_spell", card_id=tail.id)
    seen = []
    for _ in range(80):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_attackers":
            act(s, d.player, type="declare_attackers", attackers=[])
        elif d is not None:
            seen.append((s.state.turn.number, d.kind))
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        elif s.state.turn.number >= 3:
            break
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    assert [t for t, _ in seen if t == 1] and [t for t, _ in seen if t == 3]  # entered (turn 1), then its controller's upkeep (turn 3)
    check(s)


def test_deals_damage_to_a_vampire_destroys_that_creature(cards):
    # 120.1: only a creature of that type, as it last existed; a Wolf blocker is dealt damage and stays
    from tests.test_rules_combat import attack, automate, block, creature, table

    for kind, survives in (("Vampire", False), ("Wolf", True)):
        s = table(cards)
        slayer = creature(s, "p1", "Slayer", "2/2", "Whenever this creature deals damage to a Vampire, destroy that creature.")
        act(s, "p2", type="create_token", player="p2", token={"name": "Foe", "type_line": f"Token Creature — {kind}",
                                                              "power": "0", "toughness": "5", "text": ""})
        foe = next(c for c in s.state.cards.values() if c.name == "Foe")
        automate(s)
        attack(s, (slayer, "p2"))
        block(s, "p2", (foe, slayer))
        answer(s)
        assert (foe.id in s.state.cards and s.state.cards[foe.id].zone == "p2:battlefield") == survives
        check(s)


def test_a_serial_list_of_instructions_happens_in_order(cards):
    s = build(cards, ["Intimidation Campaign"], [])
    spell = to_hand(s, "Intimidation Campaign")
    mana(s, "p1", B=1, C=3)
    hand = len(s.state.zones["p1:hand"])
    act(s, "p1", type="cast_spell", card_id=spell.id)
    answer(s)
    assert (s.state.players["p2"].life, s.state.players["p1"].life) == (39, 41)
    assert len(s.state.zones["p1:hand"]) == hand  # -1 cast, +1 drawn
    check(s)


def test_a_named_artifact_token_carries_its_quoted_ability(cards):
    # 111.4: the ability sets the name; the quoted ability is the token's own (here: leaves-the-battlefield damage)
    s = build(cards, ["Weapons Manufacturing", "Sol Ring"], ["Grizzly Bears"])
    put(s, "Weapons Manufacturing")
    ring = to_hand(s, "Sol Ring")
    mana(s, "p1", C=1)
    act(s, "p1", type="cast_spell", card_id=ring.id)
    answer(s)
    token = next(c for c in s.state.cards.values() if c.name == "Munitions" and c.zone == "p1:battlefield")
    from app.rules.plan import Plan

    ch = Plan(s.state, "p1", s.cards, None).ch(token)
    assert token.is_token and "Artifact" in ch.types and "leaves the battlefield" in ch.oracle_text
    check(s)


def test_recruit_draws_discards_and_makes_a_soldier_for_a_nonland_discard(cards):
    # 701.70a: draw a card, then discard a card; a token only if the discarded card was a nonland card
    for pick, soldiers in (("Opt", 1), ("Forest", 0)):
        s = build(cards, ["Esgaroth Garrison", "Opt"], [])
        garrison, opt = to_hand(s, "Esgaroth Garrison"), to_hand(s, "Opt")
        mana(s, "p1", W=1, C=2)
        act(s, "p1", type="cast_spell", card_id=garrison.id)
        d = s.state.rules.decision
        chosen = next(o.id for o in d.options if s.state.cards[o.card_id].name == pick)
        act(s, "p1", type="choose", decision_id=d.id, option_ids=[chosen])
        answer(s)
        assert len(on_battlefield(s, "Human Soldier")) == soldiers
        check(s)


def test_you_may_have_it_fight_target_creature(cards):
    # 701.14: the source fights the target (each deals damage equal to its power to the other); "may": its controller's choice
    s = build(cards, ["Affectionate Indrik"], ["Grizzly Bears"])
    put(s, "Grizzly Bears", "p2")
    indrik = to_hand(s, "Affectionate Indrik")
    mana(s, "p1", G=1, C=4)
    act(s, "p1", type="cast_spell", card_id=indrik.id)
    answer(s)
    assert card_named(s, "Grizzly Bears", "p2").zone == "p2:graveyard"
    assert s.state.cards[card_named(s, "Affectionate Indrik").id].damage == 2
    check(s)


def test_young_hero_role_grants_an_attack_trigger_with_an_intervening_if(cards):
    # 303.7: the Role is an Aura token; its granted trigger keeps its own "if" (603.4), read on the quoted ability alone
    from tests.test_rules_combat import attack, automate, creature, table

    s = table(cards)
    bear = creature(s, "p1", "Bear", "2/2")
    act(s, "p1", type="create_token", player="p1", token={
        "name": "Young Hero", "type_line": "Token Enchantment — Aura Role", "power": None, "toughness": None, "colors": [],
        "text": "Enchant creature\nEnchanted creature has \"Whenever this creature attacks, if its toughness is 3 or less, "
                "put a +1/+1 counter on it.\""})
    hero = next(c for c in s.state.cards.values() if c.name == "Young Hero")
    act(s, "p1", type="attach", card_ids=[hero.id], to=bear.id)
    automate(s)
    attack(s, (bear, "p2"))
    answer(s)
    assert s.state.cards[bear.id].counters == {"+1/+1": 1}
    check(s)


def test_a_token_with_a_characteristic_defining_ability_counts_itself(cards):
    # 604.3, 208.1: the token has no printed power or toughness; its CDA (layer 7a) counts the creatures you control, itself included
    from app.rules import sba
    from app.rules.plan import Plan

    s = build(cards, ["Vernal Sovereign", "Llanowar Elves"], [])
    sovereign = to_hand(s, "Vernal Sovereign")
    put(s, "Llanowar Elves")
    mana(s, "p1", G=1, W=1, C=3)
    act(s, "p1", type="cast_spell", card_id=sovereign.id)
    answer(s)
    token = next(c for c in s.state.cards.values() if c.name == "Elemental" and c.zone == "p1:battlefield")
    ch = Plan(s.state, "p1", s.cards, None).ch(token)
    assert (sba.power(token, ch), sba.toughness(token, ch)) == (3, 3)  # Llanowar Elves, Vernal Sovereign and the token
    check(s)


def test_put_a_soldier_from_your_hand_onto_the_battlefield_tapped_and_attacking(cards):
    # 508.4: it is attacking (never "declared"), its controller chooses what it attacks; it enters tapped
    from app.game.factory import PlayerSetup, new_game
    from app.game.session import GameSession
    from tests.game_helpers import deck, turn_on
    from tests.test_rules_combat import attack

    alice = deck(cards, "Krenko, Mob Boss", [(1, "Preeminent Captain"), (1, "Test Soldier"), (8, "Forest")])
    bob = deck(cards, "Atraxa, Praetors' Voice", [(10, "Island")])
    s = GameSession(new_game([PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=bob)], shuffle=False), cards=cards)
    captain, soldier = card_named(s, "Preeminent Captain"), card_named(s, "Test Soldier")
    act(s, "p1", type="move", card_ids=[captain.id], to={"zone": "battlefield"})
    act(s, "p1", type="move", card_ids=[soldier.id], to={"zone": "hand"})
    turn_on(s)
    act(s, "p1", type="pass_priority")
    act(s, "p1", type="pass_priority")  # → Alice declares attackers
    attack(s, (s.state.cards[captain.id], "p2"))
    answer(s)
    got = s.state.cards[soldier.id]
    assert got.zone == "p1:battlefield" and got.tapped  # entered tapped ...
    assert s.state.players["p2"].life == 37  # ... and attacking: the Captain's 2 and the Soldier's 1 combat damage
    check(s)


@pytest.mark.parametrize("text", [
    # "that many" after a discard the player sizes is the cards discarded: only "then draw that many cards" is read (above)
    "Discard any number of cards. Search your library for up to that many basic land cards, reveal them, put them into your hand, then shuffle.",
    "Discard any number of cards, then draw that many cards plus one.",
    "Whenever you cast a spell, you may have it deal 1 damage to each opponent.",  # ("it" is the spell, not the source)
])
def test_wordings_that_stay_manual(text):
    from tests.test_rules_scripts import ch as characteristics

    kind = "Instant" if not text.startswith("Whenever") else "Creature"
    assert coverage.of_characteristics(characteristics("Test", kind, text)).level != "FULL", text


def test_cast_trigger_of_the_combined_ability_destroys_and_gives_a_powerstone(cards):
    s = build(cards, ["Cityscape Leveler"], ["Grizzly Bears"])
    put(s, "Grizzly Bears", "p2")
    spell = to_hand(s, "Cityscape Leveler")
    mana(s, "p1", C=8)
    act(s, "p1", type="cast_spell", card_id=spell.id)
    answer(s)
    assert card_named(s, "Grizzly Bears", "p2").zone == "p2:graveyard"  # "When you cast this spell" (601.2i)
    assert len(on_battlefield(s, "Powerstone", "p2")) == 1  # its controller creates a tapped Powerstone token
    check(s)

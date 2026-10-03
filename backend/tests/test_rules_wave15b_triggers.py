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

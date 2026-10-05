"""Wave 24B: loops and repeats (CR 608.2c: "Repeat this process"), real Oracle text; every scenario checks the replay and a save and a load.

608.2c: the instructions are followed in the order written, "apply the rules of English to the text": "this process" is the instructions of
the same ability before the repeat. The repeat is unrolled as the resolution reaches it (app/rules/loops.py), so a decision in the middle
of a turn waits where it is.
"""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.fixtures.cards import fixture_cards
from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import EXTRA as CLASH
from tests.test_rules_wave12a_counters_keywords import answer, on_top, real
from tests.wave9c_kit import build, check, life, mana, put, to_hand

EXTRA = [c for c in CLASH if c["name"] in ("Test Giant", "Test Mite")] + [
    real("Hoarder's Greed", "{3}{B}", 4, "Sorcery",
         "You lose 2 life and draw two cards, then clash with an opponent. If you win, repeat this process. (Each clashing player reveals the "
         "top card of their library, then puts that card on their choice of the top or bottom. A player wins if their card had a greater "
         "mana value.)", None, "B"),
    real("Remorseless Punishment", "{3}{B}{B}", 5, "Sorcery",
         "Target opponent loses 5 life unless that player discards two cards or sacrifices a creature or planeswalker of their choice. Repeat "
         "this process once.", None, "B"),
    real("Zimone and Dina", "{B}{G}{U}", 3, "Legendary Creature — Human Dryad",
         "Whenever you draw your second card each turn, target opponent loses 2 life and you gain 2 life.\n{T}, Sacrifice another creature: "
         "Draw a card. You may put a land card from your hand onto the battlefield tapped. If you control eight or more lands, repeat this "
         "process once.", ("3", "4"), "BGU"),
    real("Probe Fodder", "{1}", 1, "Creature — Human", "", ("1", "1")),
    real("Balustrade Spy", "{3}{B}", 4, "Creature — Vampire Rogue",
         "Flying\nWhen this creature enters, target player reveals cards from the top of their library until they reveal a land card, then "
         "puts those cards into their graveyard.", ("3", "2"), "B"),
    real("Insatiable Frugivore", "{3}{B}", 4, "Creature — Rat Berserker",
         "When this creature enters, create a Food token, then you may exile three cards from your graveyard. If you do, repeat this process.\n"
         "{3}{B}, Sacrifice X Foods: Creatures you control get +X/+0 and gain menace until end of turn.", ("2", "4"), "B"),
    real("Ad Nauseam", "{3}{B}{B}", 5, "Instant",
         "Reveal the top card of your library and put that card into your hand. You lose life equal to its mana value. You may repeat this "
         "process any number of times.", None, "B"),
]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.mark.parametrize("name", ["Hoarder's Greed", "Remorseless Punishment", "Zimone and Dina", "Ad Nauseam", "Balustrade Spy", "Insatiable Frugivore"])
def test_the_repeat_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


def hand(s, pid="p1"):
    return len(s.state.zones.get(f"{pid}:hand", []))


def test_repeat_this_process_once_does_the_whole_instruction_again(cards):
    s = build(cards, ["Remorseless Punishment"], [])
    spell = to_hand(s, "Remorseless Punishment")
    mana(s, B=2, G=3)
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=["p2"])
    for _ in range(4):  # (Bob has no cards to discard and no creature: each time he can only lose the life; if asked, take the first option)
        answer(s)
    assert life(s, "p2") == 30  # 5 life, twice (608.2c)
    check(s)


def test_each_turn_of_the_process_asks_its_own_question(cards):
    s = build(cards, ["Remorseless Punishment"], [])
    for c in [x for x in s.state.cards.values() if x.owner == "p2" and x.zone == "p2:library"][:4]:
        act(s, "p2", type="move", card_ids=[c.id], to={"zone": "hand"})
    spell = to_hand(s, "Remorseless Punishment")
    mana(s, B=2, G=3)
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=["p2"])
    asked = 0
    for _ in range(12):
        d = s.state.rules.decision
        if d is None:
            if s.state.zones.get("stack"):
                act(s, s.state.rules.priority, type="pass_priority")
                continue
            break
        asked += 1
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][:max(1, d.min_choices)])
    assert asked >= 2  # (the question is put to Bob once for each turn of the process)
    check(s)


@pytest.mark.parametrize("opens", [True, False])
def test_if_you_win_repeat_this_process(cards, opens):
    s = build(cards, ["Hoarder's Greed", "Test Giant", "Test Mite"], ["Test Mite"])
    spell = to_hand(s, "Hoarder's Greed")
    on_top(s, "Test Giant" if opens else "Test Mite", "p1")  # the clash card of the first turn: below the two cards the spell draws
    on_top(s, "Test Mite", "p2")
    for c in [x for x in s.state.cards.values() if x.owner == "p1" and x.name == "Forest" and x.zone == "p1:library"][:2]:
        act(s, "p1", type="move", card_ids=[c.id], to={"player": "p1", "zone": "library"})
    mana(s, B=1, G=3)
    start = hand(s)
    act(s, "p1", type="cast_spell", card_id=spell.id)
    answer(s, "top", "top", "top", "top", "top", "top")
    assert life(s) == (36 if opens else 38)  # a won clash: the process is carried out once more (608.2c)
    assert hand(s) == start - 1 + (4 if opens else 2)
    check(s)


@pytest.mark.parametrize("before,after", [(6, 7), (7, 9)])
def test_zimone_and_dina_repeat_only_with_eight_lands(cards, before, after):
    from tests.test_rules_conditionals import to_turn

    s = build(cards, ["Zimone and Dina", "Probe Fodder"], [], forests=20)
    zimone = put(s, "Zimone and Dina")
    put(s, "Probe Fodder")
    to_turn(s, 3)  # (no summoning sickness on her next turn)
    forests = [c for c in s.state.cards.values() if c.owner == "p1" and c.name == "Forest" and c.zone == "p1:library"]
    for c in forests[:before]:
        act(s, "p1", type="move", card_ids=[c.id], to={"player": "p1", "zone": "battlefield"})

    def lands():
        return sum(1 for c in s.state.cards.values() if c.zone == "p1:battlefield" and c.name == "Forest")

    assert lands() == before
    act(s, "p1", type="activate_ability", card_id=zimone.id, ability=1)
    answer(s)
    # one land card is put onto the battlefield; with eight or more lands then, the process (draw, put a land) is carried out once more
    assert lands() == after
    check(s)


@pytest.mark.parametrize("answers,lost,drawn", [(["no"], 1, 1), (["yes", "no"], 7, 2), (["yes", "yes", "no"], 7, 3)])
def test_you_may_repeat_this_process_any_number_of_times(cards, answers, lost, drawn):
    s = build(cards, ["Ad Nauseam", "Test Giant", "Test Mite"], [])
    spell = to_hand(s, "Ad Nauseam")
    on_top(s, "Test Giant", "p1")
    on_top(s, "Test Mite", "p1")  # the library, top first: the Mite (1), the Giant (6), then lands (0)
    mana(s, B=2, G=3)
    start = hand(s)
    act(s, "p1", type="cast_spell", card_id=spell.id)
    answer(s, *answers)
    assert life(s) == 40 - lost  # (each turn of the process: the card's own mana value)
    assert hand(s) == start - 1 + drawn
    check(s)


def test_reveal_until_a_land_then_the_revealed_cards_go_to_the_graveyard(cards):
    s = build(cards, ["Balustrade Spy"], ["Test Giant", "Test Mite"])
    spy = to_hand(s, "Balustrade Spy")
    on_top(s, "Test Giant", "p2")
    on_top(s, "Test Mite", "p2")  # Bob's library, top first: the Mite, the Giant, then lands
    before = len(s.state.zones["p2:graveyard"])
    mana(s, B=1, G=3)
    act(s, "p1", type="cast_spell", card_id=spy.id, targets=[], target_counts=[1])
    answer(s, "p2")
    names = [s.state.cards[c].name for c in s.state.zones["p2:graveyard"]]
    assert names.count("Test Mite") == 1 and names.count("Test Giant") == 1 and names.count("Island") == 1  # revealed down to the first land
    assert len(s.state.zones["p2:graveyard"]) == before + 3
    check(s)


@pytest.mark.parametrize("yards,foods", [(2, 1), (3, 2), (7, 3)])
def test_each_turn_of_the_process_pays_again_until_it_cant(cards, yards, foods):
    """Insatiable Frugivore: a Food, then exile three cards from the graveyard: if you do, the whole process again (a Food, three more cards …)."""
    s = build(cards, ["Insatiable Frugivore"], [], forests=12)
    spawn = [c for c in s.state.cards.values() if c.owner == "p1" and c.name == "Forest" and c.zone == "p1:library"][:yards]
    for c in spawn:
        act(s, "p1", type="move", card_ids=[c.id], to={"zone": "graveyard"})
    frug = to_hand(s, "Insatiable Frugivore")
    mana(s, B=1, G=3)
    act(s, "p1", type="cast_spell", card_id=frug.id)
    answer(s, limit=60)
    assert len([c for c in s.state.cards.values() if c.is_token and c.name == "Food"]) == foods
    check(s)

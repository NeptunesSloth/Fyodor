"""Wave 50I: modal cards that were not FULL only because one or two modes (or the header) did not parse (CR 2026-09-25), real Oracle text
(tests/fixtures/wave50i_cards.json, from data/cards.sqlite). Every scenario checks the replay and a save and a load.

* 700.2 / 700.2a / 601.2b: "gain lifelink, indestructible, and protection from each color" is one grant (Akroma's Will, 613.1f; ruling 2025-11-17: "protection
  from each color" is protection from the five colors); "This spell deals 5 damage …" in a mode is the spell itself (Choose Your Weapon).
* 700.2 / 608.2: a mode that is all "You may put a land card from your hand onto the battlefield." is the instruction's own choice (Atarka's Command);
  "Put up to two creature cards from your hand onto the battlefield." (Tooth and Nail).
* 701.22a: "Target player scries X, then draws a card." (Kozilek's Command): the named player looks, not the spell's controller.
* 700.2a / 702.33: "Choose one. If this spell was kicked, choose any number instead." (Inscription of Abundance).
* 700.2b: "choose up to X, where X is …" is counted as the triggered ability goes on the stack (Bumi, King of Three Trials; The Ruinous Wrecking Crew, X as cast);
  none to choose (X = 0): the ability is removed from the stack.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import coverage
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_wave33b_modal import settle
from tests.wave9c_kit import build, card_named, check, life, mana, put, reloaded, to_hand, zone_of

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave50i_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w50i", number=f"M{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]
LESSONS = [card(n, set_code="w50i", number=f"L{i:02d}", mana_cost="{G}", cmc=1.0, type_line="Sorcery — Lesson", oracle_text="Draw a card.",
                colors=["G"], color_identity=["G"]) for i, n in enumerate(("Test Lesson One", "Test Lesson Two"))]


def cards_fixture(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA, *LESSONS], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


cards = pytest.fixture()(cards_fixture)  # (the other wave 50I test files use the same table of cards)


@pytest.mark.parametrize("name", [c["name"] for c in DATA])
def test_every_card_is_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def kws(s, name, pid="p1"):
    return Plan(s.state, "p1", s.cards, None).ch(s.state.cards[card_named(s, name, pid).id]).keywords


def counters(s, name, pid="p1"):
    return s.state.cards[card_named(s, name, pid).id].counters.get("+1/+1", 0)


def until_decision(s, limit=20):
    """Pass priority until a decision is asked (or the stack is empty)."""
    for _ in range(limit):
        if s.state.rules.decision is not None or not s.state.zones.get("stack"):
            return s.state.rules.decision
        act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("never settled")


# --- Akroma's Will: three keywords and protection from each color ----------------------------------------------------------------------------


def test_akroma_s_will_gives_the_protection_list_and_both_modes_need_a_commander(cards):
    s = build(cards, ["Akroma's Will", "Grizzly Bears"], ["Grizzly Bears"], forests=30)
    put(s, "Grizzly Bears")
    put(s, "Grizzly Bears", "p2")
    to_hand(s, "Akroma's Will")
    mana(s, W=1, G=3)
    will = card_named(s, "Akroma's Will")
    with pytest.raises(ActionError, match="Choose 1 mode"):
        act(s, "p1", type="cast_spell", card_id=will.id, modes=[0, 1])  # no commander: one mode only
    put(s, "Krenko, Mob Boss")
    act(s, "p1", type="cast_spell", card_id=will.id, modes=[0, 1])
    settle(s)
    assert {"flying", "vigilance", "double strike", "lifelink", "indestructible", "protection"} <= set(kws(s, "Grizzly Bears"))
    assert not {"lifelink", "protection"} & set(kws(s, "Grizzly Bears", "p2"))  # (only your creatures)
    check(s)
    check(reloaded(s))


# --- Choose Your Weapon: "This spell deals 5 damage to target creature with flying" -----------------------------------------------------------


def test_choose_your_weapon_archery_hits_only_a_flyer(cards):
    s = build(cards, ["Choose Your Weapon"], ["Grizzly Bears", "Mulldrifter"], forests=30)
    bears, flyer = put(s, "Grizzly Bears", "p2"), put(s, "Mulldrifter", "p2")
    to_hand(s, "Choose Your Weapon")
    mana(s, G=3)
    spell = card_named(s, "Choose Your Weapon")
    with pytest.raises(ActionError, match="legal target"):
        act(s, "p1", type="cast_spell", card_id=spell.id, modes=[1], targets=[bears.id])  # no flying
    act(s, "p1", type="cast_spell", card_id=spell.id, modes=[1], targets=[flyer.id])
    settle(s)
    assert zone_of(s, "Mulldrifter", "p2") == "p2:graveyard" and zone_of(s, "Grizzly Bears", "p2") == "p2:battlefield"
    check(s)
    check(reloaded(s))


# --- Atarka's Command and Tooth and Nail: cards from the hand ----------------------------------------------------------------------------


def test_atarka_s_command_may_put_a_land_onto_the_battlefield(cards):
    s = build(cards, ["Atarka's Command"], forests=30)
    to_hand(s, "Atarka's Command")
    land = to_hand(s, "Forest")
    mana(s, R=1, G=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Atarka's Command").id, modes=[1, 2])
    d = until_decision(s)
    assert d is not None and d.player == "p1" and (d.min_choices, d.max_choices) == (0, 1)  # (a "may": no land is a choice)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[land.id])
    settle(s)
    assert life(s, "p2") == 37 and s.state.cards[land.id].zone == "p1:battlefield"
    check(s)
    check(reloaded(s))


def test_atarka_s_command_may_put_no_land(cards):
    s = build(cards, ["Atarka's Command"], forests=30)
    to_hand(s, "Atarka's Command")
    land = to_hand(s, "Forest")
    mana(s, R=1, G=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Atarka's Command").id, modes=[1, 2])
    d = until_decision(s)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[])
    settle(s)
    assert life(s, "p2") == 37 and s.state.cards[land.id].zone == "p1:hand"
    check(s)
    check(reloaded(s))


def test_tooth_and_nail_puts_up_to_two_creature_cards_from_hand(cards):
    s = build(cards, ["Tooth and Nail", "Grizzly Bears", "Young Wolf", "Llanowar Elves"], forests=30)
    to_hand(s, "Tooth and Nail")
    for n in ("Grizzly Bears", "Young Wolf", "Llanowar Elves"):
        to_hand(s, n)
    land = to_hand(s, "Forest")
    mana(s, G=7)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Tooth and Nail").id, modes=[1])
    d = until_decision(s)
    assert d is not None and (d.min_choices, d.max_choices) == (0, 2)
    assert {o.label for o in d.options} == {"Grizzly Bears", "Young Wolf", "Llanowar Elves"}  # (no land)
    picked = [o.id for o in d.options][:2]
    act(s, "p1", type="choose", decision_id=d.id, option_ids=picked)
    settle(s)
    assert sum(s.state.cards[c].zone == "p1:battlefield" for c in picked) == 2 and s.state.cards[land.id].zone == "p1:hand"
    check(s)
    check(reloaded(s))


# --- Inscription of Abundance: kicked, choose any number -----------------------------------------------------------------------------------


def test_inscription_of_abundance_kicked_chooses_any_number(cards):
    s = build(cards, ["Inscription of Abundance", "Grizzly Bears"], ["Grizzly Bears"], forests=30)
    mine, theirs = put(s, "Grizzly Bears"), put(s, "Grizzly Bears", "p2")
    to_hand(s, "Inscription of Abundance")
    mana(s, G=6)
    spell = card_named(s, "Inscription of Abundance")
    with pytest.raises(ActionError, match="Choose 1 mode"):
        act(s, "p1", type="cast_spell", card_id=spell.id, modes=[0, 2], targets=[mine.id, mine.id, theirs.id], target_counts=[1, 1, 1])  # not kicked: one mode
    act(s, "p1", type="cast_spell", card_id=spell.id, kicker=1, modes=[0, 1, 2], targets=[mine.id, "p1", mine.id, theirs.id], target_counts=[1, 1, 1, 1])
    settle(s)
    assert counters(s, "Grizzly Bears") >= 2 and life(s) == 40 + 4  # (two counters first: it has power 4 when the life is gained)
    assert zone_of(s, "Grizzly Bears", "p2") == "p2:graveyard"  # (fights: the 4/4 kills the 2/2)
    check(s)
    check(reloaded(s))


# --- Kozilek's Command: another player scries X --------------------------------------------------------------------------------------------


def test_kozilek_s_command_makes_the_target_player_scry_and_draw(cards):
    s = build(cards, ["Kozilek's Command"], ["Grizzly Bears"], forests=30)
    to_hand(s, "Kozilek's Command")
    mana(s, C=2, G=2)
    bears = put(s, "Grizzly Bears", "p2")
    hand, top = len(s.state.zones["p2:hand"]), list(s.state.zones["p2:library"])[:2]
    with pytest.raises(ActionError, match="no legal target"):  # (the Bears have mana value 2: "mana value X or less" with X = 1 finds nothing)
        act(s, "p1", type="cast_spell", card_id=card_named(s, "Kozilek's Command").id, x_value=1, modes=[1, 2], targets=["p2", bears.id])
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Kozilek's Command").id, x_value=2, modes=[1, 2], targets=["p2", bears.id])
    d = until_decision(s)
    assert d is not None and d.player == "p2" and d.prompt.startswith("Scry 2")  # (p2 looks at p2's cards, privately)
    act(s, "p2", type="choose", decision_id=d.id, option_ids=[top[0]])  # the first goes to the bottom
    settle(s)
    assert s.state.zones["p2:library"][-1] == top[0] and len(s.state.zones["p2:hand"]) == hand + 1
    assert s.state.zones["p2:hand"][-1] == top[1]
    check(s)
    check(reloaded(s))


# --- Bumi and The Ruinous Wrecking Crew: "choose up to X" ---------------------------------------------------------------------------------


def cast_bumi(s):
    to_hand(s, "Bumi, King of Three Trials")
    mana(s, G=6)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Bumi, King of Three Trials").id)
    return until_decision(s)


def test_bumi_chooses_up_to_the_number_of_lessons_in_the_graveyard(cards):
    s = build(cards, ["Bumi, King of Three Trials", "Test Lesson One", "Test Lesson Two"], forests=30)
    for n in ("Test Lesson One", "Test Lesson Two"):
        act(s, "p1", type="move", card_ids=[card_named(s, n).id], to={"zone": "graveyard"})
    d = cast_bumi(s)
    assert d is not None and d.kind == "choose_cards" and (d.min_choices, d.max_choices) == (0, 2)  # (X = 2 Lesson cards)
    with pytest.raises(ActionError):
        act(s, "p1", type="choose", decision_id=d.id, option_ids=["0:0", "1:0", "2:0"])  # three modes: more than X
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["0:0", "1:0"])
    d = until_decision(s)
    assert d is not None and d.kind == "choose_one"  # (the target player of the scry)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["p1"])
    for _ in range(10):
        d = until_decision(s)
        if d is None:
            break
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options] if d.kind == "order" else [])  # (the scry: keep all three on top)
    assert counters(s, "Bumi, King of Three Trials") == 3
    check(s)
    check(reloaded(s))


def test_bumi_with_no_lesson_card_chooses_nothing(cards):
    s = build(cards, ["Bumi, King of Three Trials"], forests=30)
    assert cast_bumi(s) is None  # (X = 0: no mode can be chosen, 700.2b: the ability is removed from the stack)
    assert counters(s, "Bumi, King of Three Trials") == 0 and zone_of(s, "Bumi, King of Three Trials") == "p1:battlefield"
    check(s)
    check(reloaded(s))


def test_ruinous_wrecking_crew_chooses_up_to_the_x_it_was_cast_with(cards):
    s = build(cards, ["The Ruinous Wrecking Crew"], forests=30)
    to_hand(s, "The Ruinous Wrecking Crew")
    mana(s, B=1, R=1, G=2)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "The Ruinous Wrecking Crew").id, x_value=2)
    d = until_decision(s)
    assert d is not None and (d.min_choices, d.max_choices) == (0, 2)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["1:0"])  # "Target opponent loses 2 life."
    settle(s)
    assert life(s, "p2") == 38 and counters(s, "The Ruinous Wrecking Crew") == 2
    check(s)
    check(reloaded(s))

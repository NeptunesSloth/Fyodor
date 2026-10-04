"""Wave 16B (the static_other long tail, continued). Real Oracle text, replay and save/load for each.

* 701.9a / 121.2: "each player discards …, then draws that many cards" (each player's own count; plus / minus one; any number).
* 702.77a: Reinforce (a hand ability: "{cost}, Discard this card: Put N +1/+1 counters on target creature").
* 702.69a: Gravestorm (a copy for each permanent put into a graveyard from the battlefield this turn).
* 702.127a: Aftermath (the half is cast only from a graveyard; exiled instead of going anywhere else as it leaves the stack).
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import characteristics as chars
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_effects import mana
from tests.test_rules_wave9b_exile_permission import answer, build, find, put, roundtrip

EXTRA = [
    card("Consign // Oblivion", set_code="tst", number="B01", layout="split", mana_cost="{1}{U} // {4}{B}", cmc=7.0,
         type_line="Instant // Sorcery — Aftermath", colors=["B", "U"], color_identity=["B", "U"], image_uris=None,
         card_faces=[
             {"object": "card_face", "name": "Consign", "mana_cost": "{1}{U}", "type_line": "Instant", "colors": ["U"],
              "oracle_text": "Return target nonland permanent to its owner's hand."},
             {"object": "card_face", "name": "Oblivion", "mana_cost": "{4}{B}", "type_line": "Sorcery — Aftermath", "colors": ["B"],
              "oracle_text": "Aftermath (Cast this spell only from your graveyard. Then exile it.)\nTarget opponent discards two cards."}]),
    card("Ominous Harvest", set_code="tst", number="B02", mana_cost="{1}{B}", cmc=2.0, type_line="Sorcery", colors=["B"],
         color_identity=["B"], oracle_text="Gravestorm (When you cast this spell, copy it for each permanent put into a graveyard "
         "from the battlefield this turn.)\nTarget player draws a card and loses 1 life."),
    card("Test Small", set_code="tst", number="B03", mana_cost="{G}", cmc=1.0, type_line="Creature — Elf", power="2", toughness="2",
         colors=["G"], color_identity=["G"], oracle_text=""),
    card("Fowl Strike", set_code="tst", number="B04", mana_cost="{1}{G}", cmc=2.0, type_line="Instant", colors=["G"],
         color_identity=["G"], oracle_text="Destroy target creature with flying.\nReinforce 2—{2}{G} ({2}{G}, Discard this card: Put two "
         "+1/+1 counters on target creature.)"),
    card("Test Flyer", set_code="tst", number="B05", mana_cost="{1}{U}", cmc=2.0, type_line="Creature — Bird", power="2",
         toughness="2", colors=["U"], color_identity=["U"], oracle_text="Flying"),
    card("Dark Deal", set_code="tst", number="B06", mana_cost="{2}{B}", cmc=3.0, type_line="Sorcery", colors=["B"], color_identity=["B"],
         oracle_text="Each player discards all the cards in their hand, then draws that many cards minus one."),
    card("Flux", set_code="tst", number="B07", mana_cost="{2}{U}", cmc=3.0, type_line="Sorcery", colors=["U"], color_identity=["U"],
         oracle_text="Each player discards any number of cards, then draws that many cards.\nDraw a card."),
    card("Awaken the Erstwhile", set_code="tst", number="B08", mana_cost="{3}{B}{B}", cmc=5.0, type_line="Sorcery", colors=["B"],
         color_identity=["B"], oracle_text="Each player discards all the cards in their hand, then creates that many 2/2 black Zombie "
         "creature tokens."),
    card("Winds of Change", set_code="tst", number="B09", mana_cost="{R}", cmc=1.0, type_line="Sorcery", colors=["R"],
         color_identity=["R"], oracle_text="Each player shuffles the cards from their hand into their library, then draws that many cards."),
    card("Funeral Rites", set_code="tst", number="B10", mana_cost="{3}{B}", cmc=4.0, type_line="Sorcery", colors=["B"],
         color_identity=["B"], oracle_text="You draw two cards, lose 2 life, then mill two cards."),
    card("Contact Other Plane", set_code="tst", number="B12", mana_cost="{2}{U}", cmc=3.0, type_line="Sorcery", colors=["U"],
         color_identity=["U"], oracle_text="Roll a d20.\n1—9 | Draw two cards.\n10—19 | Scry 2, then draw two cards.\n"
         "20 | Scry 3, then draw three cards."),
    card("Spiked Pit Trap", set_code="tst", number="B13", mana_cost="{3}", cmc=3.0, type_line="Artifact",
         oracle_text="Flash\n{5}, {T}, Sacrifice this artifact: Choose target creature, then roll a d20.\n"
         "1—9 | This artifact deals 5 damage to that creature.\n10—20 | This artifact deals 5 damage to that creature. Create a "
         "Treasure token."),
    card("Cathartic Pyre", set_code="tst", number="B11", mana_cost="{2}{R}", cmc=3.0, type_line="Instant", colors=["R"],
         color_identity=["R"], oracle_text="Choose one —\n• Cathartic Pyre deals 3 damage to target creature or planeswalker.\n"
         "• Discard up to two cards, then draw that many cards."),
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


def test_aftermath_half_only_from_the_graveyard_then_exiled(cards):
    s = build(cards, p1=("Consign // Oblivion",))
    c = put(s, "Consign // Oblivion", "hand")
    mana(s, C=2, B=3)
    with pytest.raises(ActionError):  # 702.127a: not from the hand
        act(s, "p1", type="cast_spell", card_id=c.id, face=1, targets=["p2"])
    put(s, "Consign // Oblivion", "graveyard")
    with pytest.raises(ActionError):  # the first half has no flashback: only the aftermath half is cast from there
        act(s, "p1", type="cast_spell", card_id=c.id, face=0, targets=[])
    ids = [x for x in s.state.zones["p2:library"][:3]]
    act(s, "p2", type="move", card_ids=ids, to={"player": "p2", "zone": "hand"})
    hand_before = len(s.state.zones["p2:hand"])
    act(s, "p1", type="cast_spell", card_id=c.id, face=1, targets=["p2"])
    answer(s)
    assert len(s.state.zones["p2:hand"]) == hand_before - 2
    assert find(s, "Consign // Oblivion").zone == "p1:exile"  # 702.127a: exiled instead of put anywhere else
    roundtrip(s)


def test_gravestorm_copies_for_each_permanent_that_went_to_a_graveyard(cards):
    s = build(cards, p1=("Ominous Harvest", "Test Small"))
    put(s, "Test Small", "battlefield")
    put(s, "Test Small", "graveyard")  # (a permanent put into a graveyard from the battlefield this turn)
    c = put(s, "Ominous Harvest", "hand")
    life, hand = s.state.players["p2"].life, len(s.state.zones["p2:hand"])
    mana(s, C=1, B=1)
    act(s, "p1", type="cast_spell", card_id=c.id, targets=["p2"])
    answer(s)
    assert s.state.players["p2"].life == life - 2 and len(s.state.zones["p2:hand"]) == hand + 2  # the spell and one copy
    roundtrip(s)


def test_reinforce_discards_the_card_for_counters_and_the_spell_is_still_cast(cards):
    s = build(cards, p1=("Fowl Strike", "Test Small"), p2=("Test Flyer",))
    small = put(s, "Test Small", "battlefield")
    put(s, "Test Flyer", "battlefield", "p2")
    fs = put(s, "Fowl Strike", "hand")
    mana(s, C=2, G=1)
    ab = next(a.index for a in chars.of(fs, s.cards).abilities if a.kind == "activated")
    act(s, "p1", type="activate_ability", card_id=fs.id, ability=ab, targets=[small.id])
    answer(s)
    assert find(s, "Fowl Strike").zone == "p1:graveyard" and s.state.cards[small.id].counters.get("+1/+1") == 2
    roundtrip(s)
    put(s, "Fowl Strike", "hand")
    mana(s, G=1, C=1)
    act(s, "p1", type="cast_spell", card_id=fs.id, targets=[find(s, "Test Flyer", "p2").id])
    answer(s)
    assert find(s, "Test Flyer", "p2").zone == "p2:graveyard"
    roundtrip(s)


def fill(s, pid, n):
    ids = s.state.zones[f"{pid}:library"][:n]
    act(s, pid, type="move", card_ids=ids, to={"player": pid, "zone": "hand"})


def hand_size(s, pid):
    return len(s.state.zones[f"{pid}:hand"])


def test_each_player_discards_hand_then_draws_that_many_minus_one(cards):
    s = build(cards, p1=("Dark Deal",))
    c = put(s, "Dark Deal", "hand")
    fill(s, "p1", 3), fill(s, "p2", 2)
    mana(s, C=2, B=1)
    act(s, "p1", type="cast_spell", card_id=c.id)
    answer(s)
    assert (hand_size(s, "p1"), hand_size(s, "p2")) == (2, 1)  # 3 - 1 and 2 - 1 (each player's own count)
    roundtrip(s)


def test_each_player_discards_any_number_then_draws_that_many(cards):
    s = build(cards, p1=("Flux",))
    c = put(s, "Flux", "hand")
    fill(s, "p1", 3), fill(s, "p2", 2)
    mana(s, C=2, U=1)
    act(s, "p1", type="cast_spell", card_id=c.id)
    for _ in range(30):
        d = s.state.rules.decision
        if d is None and not s.state.zones.get("stack"):
            break
        if d is None:
            act(s, s.state.rules.priority, type="pass_priority")
            continue
        assert d.min_choices == 0  # any number, from none (701.9a)
        ids = [o.id for o in d.options][: 2 if d.player == "p1" else 0]
        act(s, d.player, type="choose", decision_id=d.id, option_ids=ids)
    assert (hand_size(s, "p1"), hand_size(s, "p2")) == (3 - 2 + 2 + 1, 2)  # Alice swaps two and draws one more; Bob keeps his hand
    roundtrip(s)


def test_each_player_discards_hand_then_creates_that_many_tokens(cards):
    s = build(cards, p1=("Awaken the Erstwhile",))
    c = put(s, "Awaken the Erstwhile", "hand")
    fill(s, "p1", 3), fill(s, "p2", 2)
    mana(s, C=3, B=2)
    act(s, "p1", type="cast_spell", card_id=c.id)
    answer(s)
    zombies = [x for x in s.state.cards.values() if x.token and x.zone.endswith(":battlefield") and x.token.name == "Zombie"]
    assert sorted(x.controller for x in zombies) == ["p1"] * 3 + ["p2"] * 2
    roundtrip(s)


def test_each_player_shuffles_hand_into_library_then_draws_that_many(cards):
    s = build(cards, p1=("Winds of Change",))
    c = put(s, "Winds of Change", "hand")
    fill(s, "p1", 3), fill(s, "p2", 5)
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=c.id)
    answer(s)
    assert (hand_size(s, "p1"), hand_size(s, "p2")) == (3, 5)  # each draws as many as they shuffled in
    roundtrip(s)


def test_three_instructions_in_order_draw_lose_mill(cards):
    s = build(cards, p1=("Funeral Rites",))
    c = put(s, "Funeral Rites", "hand")
    life, lib = s.state.players["p1"].life, len(s.state.zones["p1:library"])
    mana(s, C=3, B=1)
    act(s, "p1", type="cast_spell", card_id=c.id)
    answer(s)
    assert s.state.players["p1"].life == life - 2 and hand_size(s, "p1") == 2 and len(s.state.zones["p1:library"]) == lib - 4
    roundtrip(s)


def test_discard_up_to_two_then_draw_that_many(cards):
    s = build(cards, p1=("Cathartic Pyre",))
    c = put(s, "Cathartic Pyre", "hand")
    fill(s, "p1", 3)
    mana(s, C=2, R=1)
    act(s, "p1", type="cast_spell", card_id=c.id, modes=[1])
    d = s.state.rules.decision
    assert d.min_choices == 0 and d.max_choices == 2  # up to two (701.9a)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][:2])
    answer(s)
    assert hand_size(s, "p1") == 3  # discarded two, drew two
    roundtrip(s)


def rolls(monkeypatch, *results):
    """The dice come up as asked (the result is recorded on the step, so a replay doesn't roll again)."""
    queue = list(results)
    monkeypatch.setattr("app.game.resolve._rng_int", lambda rng, lo, hi: queue.pop(0))


@pytest.mark.parametrize("die,drawn", [(1, 2), (9, 2), (10, 2), (19, 2), (20, 3)])
def test_roll_table_does_what_the_row_holding_the_result_says(cards, monkeypatch, die, drawn):
    rolls(monkeypatch, die)
    s = build(cards, p1=("Contact Other Plane",))
    c = put(s, "Contact Other Plane", "hand")
    before = hand_size(s, "p1")
    mana(s, C=2, U=1)
    act(s, "p1", type="cast_spell", card_id=c.id)
    answer(s)
    assert hand_size(s, "p1") == before - 1 + drawn
    roundtrip(s)


@pytest.mark.parametrize("die,treasures", [(9, 0), (10, 1)])
def test_roll_table_row_reads_the_target_chosen_before_the_roll(cards, monkeypatch, die, treasures):
    rolls(monkeypatch, die)
    s = build(cards, p1=("Spiked Pit Trap",), p2=("Test Small",))
    trap = put(s, "Spiked Pit Trap", "battlefield")
    victim = put(s, "Test Small", "battlefield", "p2")
    mana(s, C=5)
    ab = next(a.index for a in chars.of(trap, s.cards).abilities if a.kind == "activated")
    act(s, "p1", type="activate_ability", card_id=trap.id, ability=ab, targets=[victim.id])
    answer(s)
    assert find(s, "Test Small", "p2").zone == "p2:graveyard"
    made = [x for x in s.state.cards.values() if x.token and x.token.name == "Treasure" and x.zone.endswith(":battlefield")]
    assert len(made) == treasures
    roundtrip(s)

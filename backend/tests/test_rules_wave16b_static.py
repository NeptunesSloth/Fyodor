"""Wave 16B (the static_other long tail, continued). Real Oracle text, replay and save/load for each.

* 701.9a / 121.2: "each player discards …, then draws that many cards" (each player's own count; plus / minus one; any number).
* 702.77a: Reinforce (a hand ability: "{cost}, Discard this card: Put N +1/+1 counters on target creature").
* 702.69a: Gravestorm (a copy for each permanent put into a graveyard from the battlefield this turn).
* 702.127a: Aftermath (the half is cast only from a graveyard; exiled instead of going anywhere else as it leaves the stack).
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from app.rules import characteristics as chars
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from app.rules.layers import derive
from tests.game_helpers import act, deck, enable
from tests.test_rules_effects import mana, replay_matches
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
    card("Cecily, Haunted Mage", set_code="tst", number="B14", mana_cost="{1}{B}", cmc=2.0, type_line="Legendary Creature — Human Wizard",
         power="2", toughness="2", colors=["B"], color_identity=["B"], oracle_text="Your maximum hand size is eleven."),
    card("Trusted Advisor", set_code="tst", number="B15", mana_cost="{U}", cmc=1.0, type_line="Creature — Human Advisor", power="1",
         toughness="2", colors=["U"], color_identity=["U"], oracle_text="Your maximum hand size is increased by two."),
    card("Silent Arbiter", set_code="tst", number="B16", mana_cost="{4}", cmc=4.0, type_line="Artifact Creature — Construct", power="1",
         toughness="5", oracle_text="No more than one creature can attack each combat.\nNo more than one creature can block each combat."),
    card("Wear // Tear", set_code="tst", number="B20", layout="split", mana_cost="{1}{R} // {W}", cmc=3.0, type_line="Instant // Instant",
         colors=["R", "W"], color_identity=["R", "W"], image_uris=None,
         card_faces=[
             {"object": "card_face", "name": "Wear", "mana_cost": "{1}{R}", "type_line": "Instant", "colors": ["R"],
              "oracle_text": "Destroy target artifact.\nFuse (You may cast one or both halves of this card from your hand.)"},
             {"object": "card_face", "name": "Tear", "mana_cost": "{W}", "type_line": "Instant", "colors": ["W"],
              "oracle_text": "Destroy target enchantment.\nFuse (You may cast one or both halves of this card from your hand.)"}]),
    card("Test Relic", set_code="tst", number="B21", mana_cost="{2}", cmc=2.0, type_line="Artifact", oracle_text=""),
    card("Test Aura Wall", set_code="tst", number="B22", mana_cost="{1}{W}", cmc=2.0, type_line="Enchantment", colors=["W"],
         color_identity=["W"], oracle_text=""),
    card("Clutch of Currents", set_code="tst", number="B23", mana_cost="{1}{U}", cmc=2.0, type_line="Sorcery", colors=["U"],
         color_identity=["U"], oracle_text="Return target creature to its owner's hand.\nAwaken 3—{4}{U} (If you cast this spell for "
         "{4}{U}, also put three +1/+1 counters on target land you control and it becomes a 0/0 Elemental creature with haste. It's "
         "still a land.)"),
    card("Hull Breach", set_code="tst", number="B24", mana_cost="{2}{R}{G}", cmc=4.0, type_line="Sorcery", colors=["G", "R"],
         color_identity=["G", "R"], oracle_text="Choose one —\n• Destroy target artifact.\n• Destroy target enchantment.\n"
         "• Destroy target artifact and target enchantment."),
    card("Abzan Charm", set_code="tst", number="B25", mana_cost="{W}{B}{G}", cmc=3.0, type_line="Instant", colors=["B", "G", "W"],
         color_identity=["B", "G", "W"], oracle_text="Choose one —\n• Exile target creature with power 3 or greater.\n"
         "• You draw two cards and you lose 2 life.\n• Distribute two +1/+1 counters among one or two target creatures."),
    card("Urza's Rebuff", set_code="tst", number="B26", mana_cost="{1}{U}", cmc=2.0, type_line="Instant", colors=["U"],
         color_identity=["U"], oracle_text="Choose one —\n• Counter target spell.\n• Tap up to two target creatures."),
    card("Borrowed Hostility", set_code="tst", number="B27", mana_cost="{1}{R}", cmc=2.0, type_line="Instant", colors=["R"],
         color_identity=["R"], oracle_text="Escalate {3} (Pay this cost for each mode chosen beyond the first.)\nChoose one or both —\n"
         "• Target creature gets +3/+0 until end of turn.\n• Target creature gains first strike until end of turn."),
    card("Collective Brutality", set_code="tst", number="B28", mana_cost="{1}{B}", cmc=2.0, type_line="Sorcery", colors=["B"],
         color_identity=["B"], oracle_text="Escalate—Discard a card. (Discard a card for each mode chosen beyond the first.)\n"
         "Choose one or more —\n• Target opponent reveals their hand. You choose an instant or sorcery card from it. That player "
         "discards that card.\n• Target creature gets -2/-2 until end of turn.\n• Target opponent loses 2 life and you gain 2 life."),
    card("Hungry Graffalon", set_code="tst", number="B29", mana_cost="{3}{G}", cmc=4.0, type_line="Creature — Giraffe", power="3",
         toughness="4", colors=["G"], color_identity=["G"], oracle_text="Reach\nIncrement (Whenever you cast a spell, if the amount "
         "of mana you spent is greater than this creature's power or toughness, put a +1/+1 counter on this creature.)"),
    card("Pop Quiz", set_code="tst", number="B30", mana_cost="{1}{U}", cmc=2.0, type_line="Sorcery — Lesson", colors=["U"],
         color_identity=["U"], oracle_text="Draw a card.\nLearn. (You may reveal a Lesson card you own from outside the game and put it "
         "into your hand, or discard a card to draw a card.)"),
    card("Deep Analysis", set_code="tst", number="B19", mana_cost="{3}{U}", cmc=4.0, type_line="Sorcery", colors=["U"], color_identity=["U"],
         oracle_text="Target player draws two cards.\nFlashback—{1}{U}, Pay 3 life. (You may cast this card from your graveyard for "
         "its flashback cost. Then exile it.)"),
    card("Darkblast", set_code="tst", number="B17", mana_cost="{B}", cmc=1.0, type_line="Instant", colors=["B"], color_identity=["B"],
         oracle_text="Target creature gets -1/-1 until end of turn.\nDredge 3 (If you would draw a card, you may instead mill three "
         "cards and return this card from your graveyard to your hand.)"),
    card("Divination", set_code="tst", number="B18", mana_cost="{2}{U}", cmc=3.0, type_line="Sorcery", colors=["U"], color_identity=["U"],
         oracle_text="Draw two cards."),
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


@pytest.mark.parametrize("order,kept", [(("Cecily, Haunted Mage",), 11), (("Cecily, Haunted Mage", "Trusted Advisor"), 13),
                                        (("Trusted Advisor", "Cecily, Haunted Mage"), 11)])
def test_a_set_maximum_hand_size_applies_in_timestamp_order(cards, order, kept):
    from tests.test_rules_wave10b_static_forms import hand_after_cleanup

    alice = deck(cards, "Krenko, Mob Boss", [*((1, n) for n in order), (30, "Forest")])  # (a long library: the hand is topped up to 14)
    bob = deck(cards, "Atraxa, Praetors' Voice", [(10, "Island")])
    s = GameSession(enable(new_game([PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=bob)], shuffle=False)), cards=cards)
    act(s, "p1", type="pass_priority")
    for name in order:  # (each enters in turn: a later permanent's effect applies after an earlier one's, 613.7d)
        act(s, "p1", type="move", card_ids=[find(s, name).id], to={"player": "p1", "zone": "battlefield"})
    assert hand_after_cleanup(s, 14) == kept
    replay_matches(s)


def test_no_more_than_one_creature_can_attack_or_block_each_combat(cards):
    from tests.test_rules_wave5c_combat import build as cbuild
    from tests.test_rules_wave5c_combat import declare, old, to_attack
    from tests.test_rules_wave5c_combat import put as cput

    s = cbuild(cards, "Silent Arbiter")
    cput(s, "Silent Arbiter")
    a, b = old(s, "p1", "Ogre"), old(s, "p1", "Wolf")
    x, y = old(s, "p2", "Guard", "2/2"), old(s, "p2", "Guard two", "2/2")
    to_attack(s)
    with pytest.raises(ActionError, match="No more than 1 creature can attack each combat"):  # 508.1c
        declare(s, (a, "p2"), (b, "p2"))
    declare(s, (a, "p2"))
    with pytest.raises(ActionError, match="No more than 1 creature can block each combat"):  # 509.1b
        act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": x.id, "attacker_id": a.id}, {"blocker_id": y.id, "attacker_id": a.id}])
    act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": x.id, "attacker_id": a.id}])
    replay_matches(s)


def divination(cards, library_size=None):
    s = build(cards, p1=("Divination", "Darkblast"))
    put(s, "Darkblast", "graveyard")
    c = put(s, "Divination", "hand")
    if library_size is not None:
        extra = s.state.zones["p1:library"][library_size:]
        act(s, "p1", type="move", card_ids=extra, to={"player": "p1", "zone": "exile"})
    mana(s, C=2, U=1)
    act(s, "p1", type="cast_spell", card_id=c.id)
    return s


def test_dredge_replaces_one_draw_and_the_milled_cards_are_considered_for_the_next(cards):
    s = divination(cards)
    for _ in range(3):
        act(s, "p1", type="pass_priority") if s.state.rules.decision is None else None
    d = s.state.rules.decision
    assert d is not None and d.player == "p1" and {o.id for o in d.options} == {"o0", "decline"}  # 702.52a: its owner's choice
    lib, hand = len(s.state.zones["p1:library"]), hand_size(s, "p1")
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["o0"])
    answer(s)
    assert find(s, "Darkblast").zone == "p1:hand"  # returned from the graveyard
    assert len(s.state.zones["p1:library"]) == lib - 3 - 1  # three milled, one card drawn for the second draw
    assert hand_size(s, "p1") == hand + 1 + 1
    assert sum(1 for x in s.state.cards.values() if x.zone == "p1:graveyard") >= 3  # (the milled cards, and Divination)
    roundtrip(s)


def test_dredge_may_be_declined(cards):
    s = divination(cards)
    for _ in range(3):
        act(s, "p1", type="pass_priority") if s.state.rules.decision is None else None
    d = s.state.rules.decision
    hand = hand_size(s, "p1")
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["decline"])
    for _ in range(2):  # (the second draw asks again: it is its own draw)
        d = s.state.rules.decision
        if d is not None:
            act(s, "p1", type="choose", decision_id=d.id, option_ids=["decline"])
    answer(s)
    assert find(s, "Darkblast").zone == "p1:graveyard" and hand_size(s, "p1") == hand + 2
    roundtrip(s)


def test_dredge_needs_at_least_n_cards_in_the_library(cards):
    s = divination(cards, library_size=2)  # (two cards left: Dredge 3 can't be used)
    answer(s)
    assert s.state.rules.decision is None and find(s, "Darkblast").zone == "p1:graveyard"


def test_flashback_cost_with_life_is_paid_with_the_mana_and_the_card_is_exiled(cards):
    s = build(cards, p1=("Deep Analysis",))
    c = put(s, "Deep Analysis", "graveyard")
    life, hand = s.state.players["p1"].life, hand_size(s, "p1")
    mana(s, C=1, U=1)
    act(s, "p1", type="cast_spell", card_id=c.id, targets=["p1"])  # (702.34a: its flashback cost; the mana cost {3}{U} isn't paid)
    answer(s)
    assert s.state.players["p1"].life == life - 3 and hand_size(s, "p1") == hand + 2
    assert find(s, "Deep Analysis").zone == "p1:exile"  # 702.34a
    roundtrip(s)


def test_flashback_with_life_cannot_be_paid_without_the_life(cards):
    s = build(cards, p1=("Deep Analysis",))
    c = put(s, "Deep Analysis", "graveyard")
    s.state.players["p1"].life = 2
    mana(s, C=1, U=1)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=c.id, targets=["p1"])


def test_fuse_casts_both_halves_for_both_costs_and_follows_left_then_right(cards):
    s = build(cards, p1=("Wear // Tear", "Test Relic"), p2=("Test Aura Wall",))
    relic = put(s, "Test Relic", "battlefield")
    wall = put(s, "Test Aura Wall", "battlefield", "p2")
    c = put(s, "Wear // Tear", "hand")
    mana(s, C=1, R=1, W=1)  # {1}{R} for Wear and {W} for Tear (702.102c)
    act(s, "p1", type="cast_spell", card_id=c.id, fuse=True, targets=[relic.id, wall.id], target_counts=[1, 1])
    answer(s)
    assert find(s, "Test Relic").zone == "p1:graveyard" and find(s, "Test Aura Wall", "p2").zone == "p2:graveyard"
    roundtrip(s)


def test_fuse_only_from_the_hand_and_only_with_fuse(cards):
    s = build(cards, p1=("Wear // Tear", "Consign // Oblivion"))
    mana(s, C=2, R=1, W=1, U=1, B=3)
    g = put(s, "Wear // Tear", "graveyard")
    with pytest.raises(ActionError):  # 702.102a: the card with fuse is in a player's hand
        act(s, "p1", type="cast_spell", card_id=g.id, fuse=True, targets=[])
    h = put(s, "Consign // Oblivion", "hand")
    with pytest.raises(ActionError):  # no fuse on it
        act(s, "p1", type="cast_spell", card_id=h.id, fuse=True, targets=[])


def test_a_fuse_card_still_casts_one_half(cards):
    s = build(cards, p1=("Wear // Tear",), p2=("Test Aura Wall",))
    wall = put(s, "Test Aura Wall", "battlefield", "p2")
    c = put(s, "Wear // Tear", "hand")
    mana(s, W=1)
    act(s, "p1", type="cast_spell", card_id=c.id, face=1, targets=[wall.id])  # Tear alone, for {W}
    answer(s)
    assert find(s, "Test Aura Wall", "p2").zone == "p2:graveyard" and find(s, "Wear // Tear").zone == "p1:graveyard"
    roundtrip(s)


def test_awaken_cost_puts_counters_on_a_land_that_becomes_an_elemental_creature(cards):
    s = build(cards, p1=("Clutch of Currents",), p2=("Test Small",))
    victim = put(s, "Test Small", "battlefield", "p2")
    forest = next(x for x in s.state.cards.values() if x.name == "Forest" and x.owner == "p1")
    act(s, "p1", type="move", card_ids=[forest.id], to={"player": "p1", "zone": "battlefield"})
    c = put(s, "Clutch of Currents", "hand")
    mana(s, C=4, U=1)  # the awaken cost {4}{U}, not the mana cost {1}{U} (702.113a)
    act(s, "p1", type="cast_spell", card_id=c.id, awaken=True, targets=[victim.id, forest.id], target_counts=[1, 1])
    answer(s)
    assert find(s, "Test Small", "p2").zone == "p2:hand"
    land = s.state.cards[forest.id]
    assert land.counters.get("+1/+1") == 3
    ch = chars.of(land, s.cards)
    from app.rules.layers import derive

    d = derive(s.state, land, ch, s.cards)
    assert {"Land", "Creature"} <= d.types and "Elemental" in d.subtypes and "haste" in d.keywords and d.pt == (3, 3)
    roundtrip(s)


def test_cast_normally_awaken_does_nothing_and_needs_no_land_target(cards):
    s = build(cards, p1=("Clutch of Currents",), p2=("Test Small",))
    victim = put(s, "Test Small", "battlefield", "p2")
    c = put(s, "Clutch of Currents", "hand")
    mana(s, C=1, U=1)
    act(s, "p1", type="cast_spell", card_id=c.id, targets=[victim.id], target_counts=[1, 0])
    answer(s)
    assert find(s, "Test Small", "p2").zone == "p2:hand"
    roundtrip(s)


def test_a_mode_with_two_targets_destroys_both(cards):
    s = build(cards, p1=("Hull Breach", "Test Relic"), p2=("Test Aura Wall",))
    relic = put(s, "Test Relic", "battlefield")
    wall = put(s, "Test Aura Wall", "battlefield", "p2")
    c = put(s, "Hull Breach", "hand")
    mana(s, C=2, R=1, G=1)
    act(s, "p1", type="cast_spell", card_id=c.id, modes=[2], targets=[relic.id, wall.id], target_counts=[1, 1])
    answer(s)
    assert find(s, "Test Relic").zone == "p1:graveyard" and find(s, "Test Aura Wall", "p2").zone == "p2:graveyard"
    roundtrip(s)


def test_a_mode_with_up_to_two_targets_takes_none_one_or_two(cards):
    s = build(cards, p1=("Urza's Rebuff",), p2=("Test Small", "Test Flyer"))
    a, b = put(s, "Test Small", "battlefield", "p2"), put(s, "Test Flyer", "battlefield", "p2")
    c = put(s, "Urza's Rebuff", "hand")
    mana(s, C=1, U=1)
    act(s, "p1", type="cast_spell", card_id=c.id, modes=[1], targets=[a.id, b.id], target_counts=[2])
    answer(s)
    assert s.state.cards[a.id].tapped and s.state.cards[b.id].tapped
    roundtrip(s)
    s2 = build(cards, p1=("Urza's Rebuff",), p2=("Test Small",))
    put(s2, "Test Small", "battlefield", "p2")
    c2 = put(s2, "Urza's Rebuff", "hand")
    mana(s2, C=1, U=1)
    act(s2, "p1", type="cast_spell", card_id=c2.id, modes=[1], targets=[], target_counts=[0])  # "up to two": none is legal (115.6)
    answer(s2)
    assert not find(s2, "Test Small", "p2").tapped
    roundtrip(s2)


def test_a_mode_dividing_counters_among_one_or_two_targets(cards):
    s = build(cards, p1=("Abzan Charm", "Test Small"), p2=("Test Flyer",))
    a, b = put(s, "Test Small", "battlefield"), put(s, "Test Flyer", "battlefield", "p2")
    c = put(s, "Abzan Charm", "hand")
    mana(s, W=1, B=1, G=1)
    act(s, "p1", type="cast_spell", card_id=c.id, modes=[2], targets=[a.id, b.id], target_counts=[2], division=[1, 1])
    answer(s)
    assert s.state.cards[a.id].counters.get("+1/+1") == 1 and s.state.cards[b.id].counters.get("+1/+1") == 1
    roundtrip(s)


def test_escalate_mana_is_paid_for_each_mode_beyond_the_first(cards):
    s = build(cards, p1=("Borrowed Hostility", "Test Small"))
    mine = put(s, "Test Small", "battlefield")
    c = put(s, "Borrowed Hostility", "hand")
    mana(s, C=1, R=1)  # {1}{R} alone doesn't pay for two modes: {3} more
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=c.id, modes=[0, 1], targets=[mine.id, mine.id])
    mana(s, C=3)
    act(s, "p1", type="cast_spell", card_id=c.id, modes=[0, 1], targets=[mine.id, mine.id])
    answer(s)
    d = derive(s.state, s.state.cards[mine.id], chars.of(s.state.cards[mine.id], s.cards), s.cards)
    assert d.pt == (5, 2) and "first strike" in d.keywords
    roundtrip(s)


def test_escalate_discard_is_paid_once_for_each_extra_mode(cards):
    s = build(cards, p1=("Collective Brutality", "Test Small"), p2=("Test Flyer",))
    victim = put(s, "Test Flyer", "battlefield", "p2")
    c = put(s, "Collective Brutality", "hand")
    fill(s, "p1", 2)
    mana(s, C=1, B=1)
    hand, life = hand_size(s, "p1"), s.state.players["p2"].life
    act(s, "p1", type="cast_spell", card_id=c.id, modes=[1, 2], targets=[victim.id, "p2"])
    answer(s)
    assert hand_size(s, "p1") == hand - 1 - 1  # the spell, and one card discarded for the second mode
    assert s.state.players["p2"].life == life - 2 and find(s, "Test Flyer", "p2").zone == "p2:graveyard"
    roundtrip(s)


def test_increment_counts_the_mana_spent_against_the_smaller_of_power_and_toughness(cards):
    s = build(cards, p1=("Hungry Graffalon", "Divination", "Funeral Rites"))
    g = put(s, "Hungry Graffalon", "battlefield")
    d, f = put(s, "Divination", "hand"), put(s, "Funeral Rites", "hand")
    mana(s, C=2, U=1)  # three mana: not more than the 3 of its power
    act(s, "p1", type="cast_spell", card_id=d.id)
    answer(s)
    assert not s.state.cards[g.id].counters.get("+1/+1")
    mana(s, C=3, B=1)  # four mana: more than 3
    act(s, "p1", type="cast_spell", card_id=f.id)
    answer(s)
    assert s.state.cards[g.id].counters.get("+1/+1") == 1  # 702.190a
    roundtrip(s)


def test_learn_is_the_rummage_without_cards_outside_the_game(cards):
    s = build(cards, p1=("Pop Quiz",))
    c = put(s, "Pop Quiz", "hand")
    fill(s, "p1", 2)
    hand = hand_size(s, "p1")
    mana(s, C=1, U=1)
    act(s, "p1", type="cast_spell", card_id=c.id)
    answer(s)  # draws a card, discards one to draw one (701.48a: the Lesson reveal needs a card outside the game)
    assert hand_size(s, "p1") == hand - 1 + 1  # the spell leaves, one card drawn, one discarded and one drawn
    assert sum(1 for x in s.state.cards.values() if x.zone == "p1:graveyard") == 2  # the spell and the discarded card
    roundtrip(s)

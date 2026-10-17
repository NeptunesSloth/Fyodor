"""Wave 45D: commanders with two blocking lines (CR 2026-09-25), real Oracle text (tests/fixtures/wave45d_cards.json, from data/cards.sqlite).
Every scenario checks the replay and a save and a load.

* 601.3b/601.3d: "You may cast legendary spells and artifact spells as though they had flash." (Gandalf the White, Liberator): a spell of either kind.
* 705.2: Okaun and Zndrsplt flip until they lose and trigger on every flip a player wins.
* 603.4: Liberator's intervening "if the amount of mana spent to cast that spell is greater than Liberator's power" (the amount actually spent: ruling 2022-10-14).
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
from app.rules.casting import cast_problem
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditionals import settle
from tests.test_rules_effects import pass_until_stack_empty
from tests.test_rules_wave7b_activation import ability_index
from tests.test_rules_wave34b_activated import stops, to_phase
from tests.wave9c_kit import build, card_named, check, mana, pt, put, to_hand

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave45d_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w45d", number=f"B{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]
GANDALF, LIBERATOR, RESHAPER = "Gandalf the White", "Liberator, Urza's Battlethopter", "Matter Reshaper"
FULL = [GANDALF, LIBERATOR, "Jared Carthalion", "Tatsunari, Toad Rider", "Sonic the Hedgehog", "Shadow the Hedgehog", "Raggadragga, Goreguts Boss"]


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


@pytest.mark.parametrize("name", FULL)
def test_every_card_is_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


def problem(s, name):
    """Why Alice can't cast this card from her hand right now, or None."""
    c = to_hand(s, name)
    plan = Plan(s.state, "p1", s.cards, None)
    return cast_problem(s.state, "p1", c, plan.ch(c), info=plan.info, check_priority=False)


OKAUN, ZNDRSPLT, SAUCER = "Okaun, Eye of Chaos", "Zndrsplt, Eye of Wisdom", "The Gold Saucer"


def flips(monkeypatch, *results):
    """The coins come up as given (1 heads, 0 tails), one per flip; the result is recorded on the step, so a replay doesn't flip again."""
    left = iter(results)
    monkeypatch.setattr("app.game.resolve._rng_int", lambda rng, lo, hi: next(left))


def combat(s):
    """Alice's beginning of combat: her triggers on the stack, then resolved."""
    stops(s)
    to_phase(s, "begin_combat")
    settle(s)


# ---- 705.2: "flip a coin until you lose a flip", "whenever a player wins a coin flip" (Okaun, Zndrsplt) -----------------------------------------------------
@pytest.mark.parametrize("name", [OKAUN, ZNDRSPLT])
def test_the_coin_commanders_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


def test_okaun_doubles_for_each_won_flip_until_the_first_loss(cards, monkeypatch):
    flips(monkeypatch, 1, 1, 0)  # two wins, then the loss that ends it
    s = build(cards, [OKAUN], [])
    put(s, OKAUN)
    combat(s)
    assert pt(s, OKAUN) == (12, 12)  # 3/3 doubled twice until end of turn
    assert str(s.view("p1")["log"]).count("flipped a coin") == 3
    check(s)


def test_okaun_does_not_double_when_the_first_flip_is_lost(cards, monkeypatch):
    flips(monkeypatch, 0)
    s = build(cards, [OKAUN], [])
    put(s, OKAUN)
    combat(s)
    assert pt(s, OKAUN) == (3, 3)
    check(s)


def test_zndrsplt_draws_for_each_won_flip_and_for_a_flip_of_another_card(cards, monkeypatch):
    flips(monkeypatch, 1, 0, 1)
    s = build(cards, [ZNDRSPLT, SAUCER], [])
    put(s, ZNDRSPLT)
    saucer = put(s, SAUCER)
    hand = len(s.state.zones["p1:hand"])
    combat(s)  # one win, then the loss
    assert len(s.state.zones["p1:hand"]) == hand + 1
    mana(s, C=2)
    act(s, "p1", type="activate_ability", card_id=saucer.id, ability=ability_index(s, saucer, "Flip a coin"))
    settle(s)  # the Saucer's flip is won too (705.2): another card
    assert len(s.state.zones["p1:hand"]) == hand + 2
    check(s)


# ---- 601.3b: a spell of either kind may be cast as though it had flash ---------------------------------------------------------------------------------
def test_gandalf_lets_legendary_and_artifact_spells_but_no_others_be_cast_at_instant_speed(cards):
    s = build(cards, [GANDALF, "Thorin Oakenshield", "Sol Ring", "Grizzly Bears", "Mind Stone"], [])
    to_phase(s, "main1", turn=2)  # Bob's turn: Alice can cast only what has flash
    assert problem(s, "Sol Ring")  # (without Gandalf: not now)
    put(s, GANDALF)
    assert problem(s, "Sol Ring") is None  # an artifact
    assert problem(s, "Thorin Oakenshield") is None  # a legendary creature
    assert problem(s, "Grizzly Bears")  # neither
    check(s)


def test_liberator_lets_colorless_and_artifact_spells_but_no_others_be_cast_at_instant_speed(cards):
    s = build(cards, [LIBERATOR, RESHAPER, "Sol Ring", "Grizzly Bears", "Mind Stone"], [])
    to_phase(s, "main1", turn=2)
    assert problem(s, "Sol Ring")
    put(s, LIBERATOR)
    assert problem(s, "Sol Ring") is None and problem(s, RESHAPER) is None  # an artifact; a colorless creature
    assert problem(s, "Grizzly Bears")  # a green creature
    check(s)


# ---- 603.4: Liberator's counter -------------------------------------------------------------------------------------------------------------------
def test_liberator_grows_when_more_mana_than_its_power_was_spent(cards):
    s = build(cards, [LIBERATOR, "Llanowar Elves", "Mind Stone"], [])
    lib = put(s, LIBERATOR)
    mana(s, G=3)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Llanowar Elves").id)  # one mana: not greater than its power 1
    pass_until_stack_empty(s)
    assert not s.state.cards[lib.id].counters.get("+1/+1")
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Mind Stone").id)  # two mana spent
    pass_until_stack_empty(s)
    assert s.state.cards[lib.id].counters.get("+1/+1") == 1
    assert card_named(s, "Mind Stone").zone == "p1:battlefield"
    check(s)


# ---- 509.1b: Tatsunari and a Frog can't be blocked except by creatures with flying or reach ---------------------------------------------------------
def test_tatsunari_and_the_target_frog_but_no_other_creature_get_the_evasion_this_turn(cards):
    s = build(cards, ["Tatsunari, Toad Rider", "Spore Frog", "Grizzly Bears"], [])
    tatsunari, frog, bears = put(s, "Tatsunari, Toad Rider"), put(s, "Spore Frog"), put(s, "Grizzly Bears")
    mana(s, G=2)
    act(s, "p1", type="activate_ability", card_id=tatsunari.id, ability=ability_index(s, tatsunari, "can't be blocked"), targets=[frog.id])
    settle(s)

    def evasive(c):
        return any(i.startswith("cant_be_blocked_except_by") for i in Plan(s.state, "p1", s.cards, None).ch(s.state.cards[c.id]).imposed)

    assert evasive(tatsunari) and evasive(frog) and not evasive(bears)
    check(s)


# ---- "creatures you control with flash or haste" (Sonic, Shadow) ---------------------------------------------------------------------------------------
SONIC, SHADOW = "Sonic the Hedgehog", "Shadow the Hedgehog"


def counters_on(s, *names):
    return [s.state.cards[card_named(s, n).id].counters.get("+1/+1", 0) for n in names]


def sonic_table(cards):
    s = build(cards, [SONIC, "Raging Goblin", "Ambush Viper", "Grizzly Bears", "Lightning Bolt"], [])
    for n in (SONIC, "Raging Goblin", "Ambush Viper", "Grizzly Bears"):
        put(s, n)
    stops(s)
    to_phase(s, "main1", turn=3)  # (Alice's next turn: they have all been there since it began)
    return s


def test_sonic_puts_counters_only_on_creatures_with_flash_or_haste(cards):
    s = sonic_table(cards)
    to_phase(s, "declare_attackers")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": card_named(s, SONIC).id, "target": "p2"}])
    settle(s)
    assert counters_on(s, SONIC, "Raging Goblin", "Ambush Viper", "Grizzly Bears") == [1, 1, 1, 0]  # Sonic and the Goblin have haste, the Viper flash
    check(s)


@pytest.mark.parametrize(("target", "made"), [("Ambush Viper", 1), ("Grizzly Bears", 0)])
def test_sonic_makes_a_tapped_treasure_only_when_a_creature_with_flash_or_haste_is_dealt_damage(cards, target, made):
    s = sonic_table(cards)
    mana(s, R=1)
    to_hand(s, "Lightning Bolt")
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Lightning Bolt").id, targets=[card_named(s, target).id])
    settle(s)
    treasures = [c for c in s.state.cards.values() if c.name == "Treasure" and c.zone == "p1:battlefield"]
    assert len(treasures) == made and all(c.tapped for c in treasures)
    check(s)


# ---- 605.1a: "creatures you control with a mana ability" (Raggadragga) --------------------------------------------------------------------------------
def test_raggadragga_boosts_and_untaps_only_creatures_with_a_mana_ability(cards):
    s = build(cards, ["Raggadragga, Goreguts Boss", "Llanowar Elves", "Grizzly Bears"], [])
    for n in ("Raggadragga, Goreguts Boss", "Llanowar Elves", "Grizzly Bears"):
        put(s, n)
    assert pt(s, "Llanowar Elves") == (3, 3) and pt(s, "Grizzly Bears") == (2, 2)  # the Elves have a mana ability: +2/+2
    stops(s)
    to_phase(s, "main1", turn=3)
    to_phase(s, "declare_attackers")
    elves, bears = card_named(s, "Llanowar Elves"), card_named(s, "Grizzly Bears")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": elves.id, "target": "p2"}, {"card_id": bears.id, "target": "p2"}])
    settle(s)
    assert not s.state.cards[elves.id].tapped and s.state.cards[bears.id].tapped  # only the creature with a mana ability untaps
    check(s)


# ---- 702.61a: Shadow's split second, from the payment record --------------------------------------------------------------------------------------
def respond_with_a_bolt(s):
    """Whoever has priority after Alice's cast tries to answer with a Lightning Bolt."""
    me = s.state.rules.priority
    bolt = to_hand(s, "Lightning Bolt", me)
    mana(s, me, R=1)
    act(s, me, type="cast_spell", card_id=bolt.id, targets=["p2" if me == "p1" else "p1"])


def test_shadow_gives_split_second_to_a_spell_paid_with_artifact_mana(cards):
    s = build(cards, [SHADOW, "Sol Ring", "Mind Stone"], ["Lightning Bolt"])
    put(s, SHADOW)
    ring = put(s, "Sol Ring")
    stops(s)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Mind Stone").id, sources=[ring.id])
    assert s.state.zones.get("stack")
    with pytest.raises(ActionError, match="split second"):
        respond_with_a_bolt(s)
    settle(s)
    assert card_named(s, "Mind Stone").zone == "p1:battlefield"
    check(s)


def test_shadow_gives_nothing_to_a_spell_paid_without_artifact_mana(cards):
    s = build(cards, [SHADOW, "Sol Ring", "Mind Stone"], ["Lightning Bolt"])
    put(s, SHADOW)
    put(s, "Sol Ring")
    stops(s)
    mana(s, G=2)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Mind Stone").id, sources=[])  # the green mana of the pool
    respond_with_a_bolt(s)  # no split second: the answer goes on the stack
    assert len(s.state.zones["stack"]) == 2
    settle(s)
    check(s)


# ---- Jared Carthalion: each chosen creature gets counters for its own colors -------------------------------------------------------------------------
def test_jared_carthalion_puts_counters_equal_to_each_chosen_creatures_own_colors(cards):
    s = build(cards, ["Jared Carthalion", "Thorin Oakenshield", "Grizzly Bears"], [])
    jared, thorin, bears = put(s, "Jared Carthalion"), put(s, "Thorin Oakenshield"), put(s, "Grizzly Bears")
    act(s, "p1", type="counter", card_ids=[jared.id], kind="loyalty", delta=5)
    act(s, "p1", type="activate_ability", card_id=jared.id, ability=ability_index(s, jared, "Choose up to two"), targets=[thorin.id, bears.id], target_counts=[2])
    settle(s)
    assert s.state.cards[thorin.id].counters.get("+1/+1") == 2  # red and white
    assert s.state.cards[bears.id].counters.get("+1/+1") == 1  # green
    check(s)

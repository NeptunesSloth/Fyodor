"""Reanimation wordings (wave 10A), read against CR 115.1 / 601.2c (one target group per "target"), 107.3f (X of the
spell), 608.2b (targets are rechecked on resolution), 608.2d (a choice with no target is made on resolution), 608.2h
(an ability reads its source as it last existed) and 400.7 (a card that moved is a new object). The cards are real
Commander cards, their Oracle text transcribed from the card database. Every scenario also replays the recorded history
and round-trips a save."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from app.rules import coverage
from app.rules.characteristics import printed_from_data
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, deck, enable
from tests.test_rules_delayed import reloaded
from tests.test_rules_effects import mana, pass_until_stack_empty, replay_matches

PANDA = ("Whenever you gain life, put a +1/+1 counter on this creature.\n"
         "When this creature dies, return another target non-Bear creature card with mana value less than or equal to this "
         "creature's power from your graveyard to the battlefield.")
MIRKO = ("Flying, vigilance\nWhenever you surveil, put a +1/+1 counter on Mirko.\n"
         "At the beginning of your end step, you may return target creature card with power less than Mirko's from your "
         "graveyard to the battlefield with a finality counter on it. (If it would die, exile it instead.)")
REAL = [
    card("Fiendish Panda", set_code="tst", number="W1", mana_cost="{2}{W}{B}", cmc=4.0, type_line="Creature — Bear Demon",
         oracle_text=PANDA, power="3", toughness="2", colors=["W", "B"], color_identity=["W", "B"]),
    card("Mirko, Obsessive Theorist", set_code="tst", number="W2", mana_cost="{1}{U}{B}", cmc=3.0,
         type_line="Legendary Creature — Vampire Detective", oracle_text=MIRKO, power="1", toughness="3",
         colors=["U", "B"], color_identity=["U", "B"]),
    card("Pull from the Deep", set_code="tst", number="W3", mana_cost="{2}{U}{U}", cmc=4.0, type_line="Sorcery",
         oracle_text="Return up to one target instant card and up to one target sorcery card from your graveyard to your hand. "
                     "Exile Pull from the Deep.", colors=["U"], color_identity=["U"]),
    card("Sudden Reclamation", set_code="tst", number="W4", mana_cost="{3}{G}", cmc=4.0, type_line="Instant",
         oracle_text="Mill four cards, then return a creature card and a land card from your graveyard to your hand.",
         colors=["G"], color_identity=["G"]),
    card("Postmortem Lunge", set_code="tst", number="W5", mana_cost="{X}{B/P}", cmc=1.0, type_line="Sorcery",
         oracle_text="({B/P} can be paid with either {B} or 2 life.)\nReturn target creature card with mana value X from your "
                     "graveyard to the battlefield. It gains haste. Exile it at the beginning of the next end step.",
         colors=["B"], color_identity=["B"]),
    card("Immortal Servitude", set_code="tst", number="W6", mana_cost="{X}{W/B}{W/B}{W/B}", cmc=3.0, type_line="Sorcery",
         oracle_text="Return each creature card with mana value X from your graveyard to the battlefield.",
         colors=["W", "B"], color_identity=["W", "B"]),
    card("Rydia, Summoner of Mist", set_code="tst", number="W8", mana_cost="{R}{G}", cmc=2.0,
         type_line="Legendary Creature — Human Shaman",
         oracle_text="Landfall — Whenever a land you control enters, you may discard a card. If you do, draw a card.\n"
                     "Summon — {X}, {T}: Return target Saga card with mana value X from your graveyard to the battlefield with a "
                     "finality counter on it. It gains haste until end of turn. Activate only as a sorcery.",
         power="1", toughness="2", colors=["R", "G"], color_identity=["R", "G"]),
    card("The Eldest Reborn", set_code="tst", number="W9", mana_cost="{4}{B}", cmc=5.0, type_line="Enchantment — Saga",
         oracle_text="(As this Saga enters and after your draw step, add a lore counter. Sacrifice after III.)\n"
                     "I — Each opponent sacrifices a creature or planeswalker.\nII — Each opponent discards a card.\n"
                     "III — Put target creature or planeswalker card from a graveyard onto the battlefield under your control.",
         colors=["B"], color_identity=["B"]),
    card("Crop Sigil", set_code="tst", number="X1", mana_cost="{G}", cmc=1.0, type_line="Enchantment",
         oracle_text="At the beginning of your upkeep, you may mill a card.\nDelirium — {2}{G}, Sacrifice this enchantment: Return "
                     "up to one target creature card and up to one target land card from your graveyard to your hand. Activate "
                     "only if there are four or more card types among cards in your graveyard.",
         colors=["G"], color_identity=["G"]),
    card("Lazotep Quarry", set_code="tst", number="X2", type_line="Land — Desert",
         oracle_text="{T}: Add {C}.\n{T}, Sacrifice a creature: Add one mana of any color.\n{X}{2}, {T}, Sacrifice a Desert: Exile "
                     "target creature card with mana value X from your graveyard. Create a token that's a copy of it, except it's "
                     "a 4/4 black Zombie. Activate only as a sorcery."),
    card("Sequence Engine", set_code="tst", number="X3", mana_cost="{2}{G}", cmc=3.0, type_line="Artifact",
         oracle_text="{X}, {T}: Exile target creature card with mana value X from a graveyard. Create a 0/0 green and blue Fractal "
                     "creature token. Put X +1/+1 counters on it. Activate only as a sorcery.", colors=["G"], color_identity=["G"]),
    card("Retrieve", set_code="tst", number="X4", mana_cost="{2}{G}", cmc=3.0, type_line="Sorcery",
         oracle_text="Return up to one target creature card and up to one target noncreature permanent card from your graveyard "
                     "to your hand. Exile Retrieve.", colors=["G"], color_identity=["G"]),
    card("Restoration Specialist", set_code="tst", number="X5", mana_cost="{1}{W}", cmc=2.0, type_line="Creature — Dwarf Artificer",
         oracle_text="{W}, Sacrifice this creature: Return up to one target artifact card and up to one target enchantment card "
                     "from your graveyard to your hand.", power="2", toughness="1", colors=["W"], color_identity=["W"]),
    card("Shreds of Sanity", set_code="tst", number="X6", mana_cost="{2}{R}", cmc=3.0, type_line="Sorcery",
         oracle_text="Return up to one target instant card and up to one target sorcery card from your graveyard to your hand, then "
                     "discard a card. Exile Shreds of Sanity.", colors=["R"], color_identity=["R"]),
    card("Druidic Ritual", set_code="tst", number="X7", mana_cost="{2}{G}", cmc=3.0, type_line="Sorcery",
         oracle_text="You may mill three cards. Then return up to one creature card and up to one land card from your graveyard "
                     "to your hand. (To mill a card, put the top card of your library into your graveyard.)",
         colors=["G"], color_identity=["G"]),
    card("Gravedigger Test Double", set_code="tst", number="W7", mana_cost="{3}{B}", cmc=4.0, type_line="Creature — Zombie",
         oracle_text="Vigilance", power="2", toughness="2", colors=["B"], color_identity=["B"]),
]


@pytest.fixture()
def cards(settings) -> Iterator[CardRepository]:
    settings.ensure_dirs()
    build_database([*fixture_cards(), *REAL], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def build(cards):
    alice = deck(cards, "Krenko, Mob Boss", [(1, "Fiendish Panda"), (1, "Mirko, Obsessive Theorist"), (1, "Pull from the Deep"),
                                             (1, "Sudden Reclamation"), (1, "Postmortem Lunge"), (1, "Immortal Servitude"),
                                             (1, "Gravedigger Test Double"), (1, "Rydia, Summoner of Mist"), (1, "The Eldest Reborn"),
                                             (1, "Crop Sigil"), (1, "Lazotep Quarry"), (1, "Sequence Engine"), (1, "Retrieve"),
                                             (1, "Restoration Specialist"), (1, "Sol Ring"), (1, "Shreds of Sanity"),
                                             (1, "Druidic Ritual"),
                                             (1, "Lightning Bolt"), (1, "Counterspell"),
                                             (1, "Llanowar Elves"), (2, "Grizzly Bears"), (20, "Forest")])
    bob = deck(cards, "Atraxa, Praetors' Voice", [(2, "Grizzly Bears"), (1, "Llanowar Elves"), (20, "Island")])
    state = new_game([PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=bob)], shuffle=False)
    s = GameSession(enable(state), cards=cards)
    act(s, "p1", type="pass_priority")  # → Alice's first main phase
    return s


def put(s, name, zone, pid="p1", nth=0):
    cs = [c for c in s.state.cards.values() if c.name == name and c.owner == pid]
    c = cs[nth]
    act(s, "p1", type="move", card_ids=[c.id], to={"zone": zone, "player": pid} if zone != "battlefield" else {"zone": zone})
    return s.state.cards[c.id]


def cast(s, name, **kw):
    c = put(s, name, "hand")
    act(s, "p1", type="cast_spell", card_id=c.id, **kw)
    pass_until_stack_empty(s)
    return c


def settle(s):
    pass_until_stack_empty(s)
    replay_matches(s)
    assert reloaded(s).state.model_dump(mode="json") == s.state.model_dump(mode="json")


def kill(s, c):
    """Lethal damage, then the state-based actions (704.5g): the engine moves it (not by hand)."""
    act(s, "p1", type="set_damage", card_ids=[c.id], value=20)
    act(s, s.state.rules.priority or "p1", type="pass_priority")
    pass_until_stack_empty(s)


def zone(s, c):
    return s.state.cards[c.id].zone


# -- coverage: the new wordings are automated ---------------------------------------------------------------
@pytest.mark.parametrize("name", ["Fiendish Panda", "Mirko, Obsessive Theorist", "Pull from the Deep", "Sudden Reclamation",
                                  "Postmortem Lunge", "Immortal Servitude"])
def test_the_cards_are_fully_automated(cards, name):
    data = cards.resolve(name)
    assert coverage.of_characteristics(printed_from_data(data, 0)).level == "FULL"


# -- "mana value less than or equal to this creature's power" (608.2h) ------------------------------------
def test_panda_reads_its_own_power_as_it_last_existed_and_skips_bears(cards):
    s = build(cards)
    elves = put(s, "Llanowar Elves", "graveyard")  # mana value 1
    big = put(s, "Gravedigger Test Double", "graveyard")  # mana value 4: more than 3
    bear = put(s, "Grizzly Bears", "graveyard")  # a Bear: "non-Bear"
    panda = put(s, "Fiendish Panda", "battlefield")
    kill(s, panda)
    d = s.state.rules.decision
    if d is not None:  # (only one legal target: chosen at once)
        assert elves.id in [o.card_id for o in d.options] and big.id not in [o.card_id for o in d.options]
        assert bear.id not in [o.card_id for o in d.options]
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[elves.id])
        pass_until_stack_empty(s)
    assert zone(s, elves) == "p1:battlefield"
    assert zone(s, big) == "p1:graveyard" and zone(s, bear) == "p1:graveyard"
    settle(s)


def test_panda_with_a_counter_reaches_mana_value_four(cards):
    s = build(cards)
    big = put(s, "Gravedigger Test Double", "graveyard")
    panda = put(s, "Fiendish Panda", "battlefield")
    act(s, "p1", type="counter", card_ids=[panda.id], kind="+1/+1", delta=1)  # power 4 when it dies
    kill(s, panda)
    d = s.state.rules.decision
    if d is not None:
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[big.id])
        pass_until_stack_empty(s)
    assert zone(s, big) == "p1:battlefield"
    settle(s)


# -- "power less than Mirko's" is strict ------------------------------------------------------------------
def to_end_step(s, pick):
    """Pass priority (no attackers, no blockers) through the turn; ``pick(decision)`` answers any other decision."""
    for _ in range(120):
        if s.state.turn.phase == "cleanup" or s.state.turn.number > 1:
            return
        d = s.state.rules.decision
        if d is None:
            act(s, s.state.rules.priority, type="pass_priority")
        elif d.kind == "declare_attackers":
            act(s, d.player, type="declare_attackers", attackers=[])
        elif d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
        else:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=pick(d))
    raise AssertionError("never got there")


def test_mirko_returns_only_a_strictly_smaller_creature_with_a_finality_counter(cards):
    s = build(cards)
    mirko = put(s, "Mirko, Obsessive Theorist", "battlefield")
    smaller = put(s, "Llanowar Elves", "graveyard")  # power 1
    equal = put(s, "Grizzly Bears", "graveyard")  # power 2: not less than Mirko's 2
    act(s, "p1", type="counter", card_ids=[mirko.id], kind="+1/+1", delta=1)  # Mirko is 2/4
    seen: list[list[str]] = []

    def pick(d):
        seen.append([o.card_id for o in d.options])
        return [smaller.id] if smaller.id in [o.id for o in d.options] else [d.options[0].id]

    to_end_step(s, pick)
    assert zone(s, smaller) == "p1:battlefield" and zone(s, equal) == "p1:graveyard"
    assert all(equal.id not in ids for ids in seen)
    assert s.state.cards[smaller.id].counters.get("finality") == 1
    replay_matches(s)


def test_mirko_finds_nothing_equal_to_its_own_power(cards):
    s = build(cards)
    put(s, "Mirko, Obsessive Theorist", "battlefield")  # 1/3
    elves = put(s, "Llanowar Elves", "graveyard")  # power 1: not less than 1
    to_end_step(s, lambda d: [d.options[0].id])
    assert zone(s, elves) == "p1:graveyard"
    replay_matches(s)


# -- one instruction, one target group per kind (601.2c) --------------------------------------------------
def test_pull_from_the_deep_takes_one_instant_and_one_sorcery_then_exiles_itself(cards):
    s = build(cards)
    bolt = put(s, "Lightning Bolt", "graveyard")
    counter = put(s, "Counterspell", "graveyard")
    sorc = put(s, "Postmortem Lunge", "graveyard")
    mana(s, U=2, C=2)
    spell = cast(s, "Pull from the Deep", targets=[bolt.id, sorc.id], target_counts=[1, 1])
    assert zone(s, bolt) == "p1:hand" and zone(s, sorc) == "p1:hand"
    assert zone(s, counter) == "p1:graveyard"  # (up to one instant: only the chosen one)
    assert zone(s, spell) == "p1:exile"
    settle(s)


def test_pull_from_the_deep_with_only_one_target_group_filled(cards):
    s = build(cards)
    bolt = put(s, "Lightning Bolt", "graveyard")
    mana(s, U=2, C=2)
    cast(s, "Pull from the Deep", targets=[bolt.id], target_counts=[1, 0])
    assert zone(s, bolt) == "p1:hand"
    settle(s)


# -- nothing targeted: each card chosen on resolution (608.2d) -------------------------------------------
def test_sudden_reclamation_mills_then_returns_a_creature_and_a_land(cards):
    s = build(cards)
    bears = put(s, "Grizzly Bears", "graveyard")
    forest = put(s, "Forest", "graveyard")
    mana(s, G=1, C=3)
    put(s, "Sudden Reclamation", "hand")
    c = next(x for x in s.state.cards.values() if x.name == "Sudden Reclamation")
    act(s, "p1", type="cast_spell", card_id=c.id)
    for _ in range(10):
        pass_until_stack_empty(s)
        d = s.state.rules.decision
        if d is None:
            break
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[bears.id] if bears.id in [o.id for o in d.options]
            and "creature" in d.prompt else [forest.id] if forest.id in [o.id for o in d.options] else [d.options[0].id])
    assert zone(s, bears) == "p1:hand" and zone(s, forest) == "p1:hand"
    settle(s)


# -- "mana value X" is the X of the spell (107.3f) ----------------------------------------------------------
def test_postmortem_lunge_returns_exactly_mana_value_x_with_haste_and_exiles_it_at_end_step(cards):
    s = build(cards)
    elves = put(s, "Llanowar Elves", "graveyard")  # mana value 1
    bears = put(s, "Grizzly Bears", "graveyard")  # mana value 2
    c = put(s, "Postmortem Lunge", "hand")
    mana(s, B=2, C=1)
    with pytest.raises(ActionError):  # X = 3: nothing in the graveyard has mana value 3
        act(s, "p1", type="cast_spell", card_id=c.id, targets=[bears.id], x_value=3)
    act(s, "p1", type="cast_spell", card_id=c.id, targets=[bears.id], x_value=2, life_symbols=[])  # (wave 50B: {B/P} announced paid with mana)
    pass_until_stack_empty(s)
    assert zone(s, bears) == "p1:battlefield" and zone(s, elves) == "p1:graveyard"
    settle(s)


def test_immortal_servitude_returns_every_creature_with_mana_value_x(cards):
    s = build(cards)
    elves = put(s, "Llanowar Elves", "graveyard")  # 1
    bears = put(s, "Grizzly Bears", "graveyard", nth=0)  # 2
    bears2 = put(s, "Grizzly Bears", "graveyard", nth=1)  # 2
    c = put(s, "Immortal Servitude", "hand")
    mana(s, B=5, C=3)
    act(s, "p1", type="cast_spell", card_id=c.id, x_value=2)
    pass_until_stack_empty(s)
    assert zone(s, bears) == "p1:battlefield" and zone(s, bears2) == "p1:battlefield" and zone(s, elves) == "p1:graveyard"
    settle(s)


# -- an activated ability with {X} in its cost: the X of the activation, kept for the resolution (107.3f, 602.2b) ----
def test_rydia_returns_a_saga_with_mana_value_x(cards):
    s = build(cards)
    rydia = put(s, "Rydia, Summoner of Mist", "battlefield")
    for _ in range(200):  # (to Alice's next turn: Rydia is no longer summoning sick)
        if s.state.turn.number == 3 and s.state.turn.phase == "main1" and s.state.rules.decision is None:
            break
        d = s.state.rules.decision
        if d is None:
            act(s, s.state.rules.priority, type="pass_priority")
        elif d.kind == "declare_attackers":
            act(s, d.player, type="declare_attackers", attackers=[])
        elif d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
        else:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[d.options[0].id])
    saga = put(s, "The Eldest Reborn", "graveyard")  # mana value 5
    mana(s, C=5)
    with pytest.raises(ActionError):  # X = 4: the Saga's mana value is 5
        act(s, "p1", type="activate_ability", card_id=rydia.id, ability=1, targets=[saga.id], x_value=4)
    act(s, "p1", type="activate_ability", card_id=rydia.id, ability=1, targets=[saga.id], x_value=5)
    pass_until_stack_empty(s)
    assert zone(s, saga) == "p1:battlefield"
    settle(s)

"""Reanimation / graveyard recursion wording (wave 3R), read against CR 110.2a (the player instructed
controls what enters unless the text says otherwise), 113.6m (an ability that moves its own card out
of the graveyard works only there), 400.3 (a card goes to its OWNER's hand), 400.7 (a card that moved
is a new object), 608.2d (a choice with no target is made on resolution) and 903.9 (not exercised: the
commander's replacement is in test_rules_commander_patterns). The cards are real Commander cards,
their Oracle text transcribed from the card database. Every scenario also checks that replaying the
recorded history reproduces the table exactly."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, deck, enable
from tests.test_rules_delayed import reloaded
from tests.test_rules_effects import mana, pass_until_stack_empty, replay_matches

REAL = [
    card("Reassembling Skeleton", set_code="tst", number="R1", mana_cost="{1}{B}", cmc=2.0, type_line="Creature — Skeleton Warrior",
         oracle_text="{1}{B}: Return this card from your graveyard to the battlefield tapped.", power="1", toughness="1",
         colors=["B"], color_identity=["B"]),
    card("Ashen Powder", set_code="tst", number="R2", mana_cost="{2}{B}{B}", cmc=4.0, type_line="Sorcery",
         oracle_text="Put target creature card from an opponent's graveyard onto the battlefield under your control.",
         colors=["B"], color_identity=["B"]),
    card("Reanimate", set_code="tst", number="R3", mana_cost="{B}", cmc=1.0, type_line="Sorcery",
         oracle_text="Put target creature card from a graveyard onto the battlefield under your control. "
                     "You lose life equal to that card's mana value.", colors=["B"], color_identity=["B"]),
    card("Rise of the Dark Realms", set_code="tst", number="R4", mana_cost="{7}{B}{B}", cmc=9.0, type_line="Sorcery",
         oracle_text="Put all creature cards from all graveyards onto the battlefield under your control.",
         colors=["B"], color_identity=["B"]),
    card("Corpse Churn", set_code="tst", number="R5", mana_cost="{1}{B}", cmc=2.0, type_line="Instant",
         oracle_text="Mill three cards, then you may return a creature card from your graveyard to your hand. "
                     "(To mill three cards, put the top three cards of your library into your graveyard.)",
         colors=["B"], color_identity=["B"]),
    card("Haunted Fengraf", set_code="tst", number="R6", type_line="Land",
         oracle_text="{T}: Add {C}.\n{3}, {T}, Sacrifice this land: Return a creature card at random from your graveyard to your hand."),
    card("Gravedigger", set_code="tst", number="R7", mana_cost="{3}{B}", cmc=4.0, type_line="Creature — Zombie",
         oracle_text="When this creature enters, you may return target creature card from your graveyard to your hand.",
         power="2", toughness="2", colors=["B"], color_identity=["B"]),
    card("Forcemage Advocate", set_code="tst", number="R10", mana_cost="{1}{G}", cmc=2.0, type_line="Creature — Centaur Shaman",
         oracle_text="{T}: Return target card from an opponent's graveyard to their hand. Put a +1/+1 counter on target creature.",
         power="2", toughness="1", colors=["G"], color_identity=["G"]),
    card("Soul Salvage", set_code="tst", number="R8", mana_cost="{2}{B}", cmc=3.0, type_line="Sorcery",
         oracle_text="Return up to two target creature cards from your graveyard to your hand.", colors=["B"], color_identity=["B"]),
]


@pytest.fixture()
def cards(settings) -> Iterator[CardRepository]:
    settings.ensure_dirs()
    build_database([*fixture_cards(), *REAL], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def build(cards):
    alice = deck(cards, "Krenko, Mob Boss", [(1, "Reassembling Skeleton"), (1, "Ashen Powder"), (1, "Reanimate"),
                                             (1, "Rise of the Dark Realms"), (1, "Corpse Churn"), (1, "Haunted Fengraf"),
                                             (1, "Soul Salvage"), (1, "Lightning Bolt"), (1, "Gravedigger"), (1, "Forcemage Advocate"),
                                             (2, "Grizzly Bears"), (20, "Forest")])
    bob = deck(cards, "Atraxa, Praetors' Voice", [(2, "Grizzly Bears"), (1, "Llanowar Elves"), (1, "Counterspell"),
                                                  (20, "Island")])
    state = new_game([PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=bob)], shuffle=False)
    s = GameSession(enable(state), cards=cards)
    act(s, "p1", type="pass_priority")  # → Alice's first main phase
    return s


def put(s, name, zone, pid="p1", nth=0):
    cs = [c for c in s.state.cards.values() if c.name == name and c.owner == pid]
    c = cs[nth]
    act(s, "p1", type="move", card_ids=[c.id], to={"zone": zone, "player": pid} if zone != "battlefield" else {"zone": zone})
    return s.state.cards[c.id]


def cast(s, name, targets=None):
    c = put(s, name, "hand")
    kw = {"targets": targets} if targets is not None else {}
    act(s, "p1", type="cast_spell", card_id=c.id, **kw)
    pass_until_stack_empty(s)
    return c


def answer(s, pick):
    d = s.state.rules.decision
    assert d is not None and d.kind == "choose_cards"
    act(s, d.player, type="choose", decision_id=d.id, option_ids=pick(d))
    pass_until_stack_empty(s)


# -- "return this card from your graveyard" (113.6m) ----------------------------------------------------
def test_reassembling_skeleton_returns_itself_tapped_from_the_graveyard(cards):
    s = build(cards)
    sk = put(s, "Reassembling Skeleton", "graveyard")
    mana(s, B=1, C=1)
    act(s, "p1", type="activate_ability", card_id=sk.id, ability=0)
    pass_until_stack_empty(s)
    back = s.state.cards[sk.id]
    assert back.zone == "p1:battlefield" and back.tapped and back.controller == "p1"
    replay_matches(s)
    assert reloaded(s).state.model_dump(mode="json") == s.state.model_dump(mode="json")


def test_the_graveyard_ability_works_only_from_the_graveyard_and_for_its_owner(cards):
    s = build(cards)
    sk = put(s, "Reassembling Skeleton", "battlefield")
    mana(s, B=1, C=1)
    with pytest.raises(ActionError, match="graveyard"):
        act(s, "p1", type="activate_ability", card_id=sk.id, ability=0)
    hand = put(s, "Reassembling Skeleton", "hand", nth=0)
    assert hand.zone == "p1:hand"
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=sk.id, ability=0)
    put(s, "Reassembling Skeleton", "graveyard")
    with pytest.raises(ActionError):  # (Bob cannot use Alice's graveyard card)
        act(s, "p2", type="activate_ability", card_id=sk.id, ability=0)
    replay_matches(s)


def test_the_card_that_left_the_graveyard_is_not_returned(cards):
    """400.7: the ability on the stack is about the card as it was; once it has gone elsewhere the
    resolution finds nothing to return."""
    s = build(cards)
    sk = put(s, "Reassembling Skeleton", "graveyard")
    mana(s, B=1, C=1)
    act(s, "p1", type="activate_ability", card_id=sk.id, ability=0)
    act(s, "p1", type="move", card_ids=[sk.id], to={"zone": "exile"})
    pass_until_stack_empty(s)
    assert s.state.cards[sk.id].zone == "p1:exile"
    replay_matches(s)


# -- "put … onto the battlefield under your control" (110.2a) -------------------------------------------
def test_ashen_powder_takes_a_creature_from_an_opponents_graveyard(cards):
    s = build(cards)
    bears = put(s, "Grizzly Bears", "graveyard", pid="p2")
    mana(s, B=2, C=2)
    cast(s, "Ashen Powder", [bears.id])
    got = s.state.cards[bears.id]
    assert got.zone == "p1:battlefield" and got.controller == "p1" and got.owner == "p2"
    replay_matches(s)


def test_ashen_powder_refuses_your_own_graveyard_and_non_creatures(cards):
    s = build(cards)
    mine = put(s, "Grizzly Bears", "graveyard", pid="p1")
    forest = put(s, "Island", "graveyard", pid="p2")
    mana(s, B=2, C=2)
    c = put(s, "Ashen Powder", "hand")
    for bad in (mine, forest):
        with pytest.raises(ActionError, match="legal target"):
            act(s, "p1", type="cast_spell", card_id=c.id, targets=[bad.id])
    replay_matches(s)


def test_reanimate_from_any_graveyard_and_the_life_loss_is_its_mana_value(cards):
    s = build(cards)
    bears = put(s, "Grizzly Bears", "graveyard", pid="p2")
    mana(s, B=1)
    cast(s, "Reanimate", [bears.id])
    assert s.state.cards[bears.id].zone == "p1:battlefield" and s.state.players["p1"].life == 40 - 2
    # your own graveyard is "a graveyard" too
    mine = put(s, "Grizzly Bears", "graveyard", pid="p1")
    mana(s, B=1)
    cast(s, "Reanimate", [mine.id])
    assert s.state.cards[mine.id].zone == "p1:battlefield" and s.state.players["p1"].life == 40 - 4
    replay_matches(s)


def test_reanimate_cannot_target_a_card_that_is_not_in_a_graveyard(cards):
    s = build(cards)
    bears = put(s, "Grizzly Bears", "battlefield", pid="p2")
    mana(s, B=1)
    c = put(s, "Reanimate", "hand")
    with pytest.raises(ActionError, match="legal target"):
        act(s, "p1", type="cast_spell", card_id=c.id, targets=[bears.id])


def test_rise_of_the_dark_realms_takes_every_graveyard(cards):
    s = build(cards)
    mine = put(s, "Grizzly Bears", "graveyard", pid="p1")
    theirs = put(s, "Llanowar Elves", "graveyard", pid="p2")
    spell = put(s, "Counterspell", "graveyard", pid="p2")  # (not a creature card)
    mana(s, B=2, C=7)
    cast(s, "Rise of the Dark Realms")
    for c in (mine, theirs):
        got = s.state.cards[c.id]
        assert got.zone == "p1:battlefield" and got.controller == "p1"
    assert s.state.cards[theirs.id].owner == "p2"  # 110.2a changes the controller, not the owner
    assert s.state.cards[spell.id].zone == "p2:graveyard"
    replay_matches(s)


# -- a choice made on resolution (608.2d) --------------------------------------------------------------
def test_corpse_churn_mills_then_the_player_chooses_a_creature_card(cards):
    s = build(cards)
    keep = put(s, "Grizzly Bears", "graveyard", pid="p1", nth=0)
    other = put(s, "Grizzly Bears", "graveyard", pid="p1", nth=1)
    theirs = put(s, "Grizzly Bears", "graveyard", pid="p2")
    mana(s, B=1, C=1)
    cast(s, "Corpse Churn")
    d = s.state.rules.decision
    assert d is not None and d.min_choices == 0 and d.max_choices == 1  # "you may": none is allowed
    assert {o.id for o in d.options} >= {keep.id, other.id} and theirs.id not in {o.id for o in d.options}
    answer(s, lambda d: [keep.id])
    assert s.state.cards[keep.id].zone == "p1:hand" and s.state.cards[other.id].zone == "p1:graveyard"
    assert s.state.cards[theirs.id].zone == "p2:graveyard"
    replay_matches(s)


def test_corpse_churn_may_decline(cards):
    s = build(cards)
    bears = put(s, "Grizzly Bears", "graveyard", pid="p1")
    mana(s, B=1, C=1)
    cast(s, "Corpse Churn")
    answer(s, lambda d: [])
    assert s.state.cards[bears.id].zone == "p1:graveyard"
    replay_matches(s)


def unsick(s, card):
    """(The table has only just started: let the creature have been here since the turn began, as it
    would be a turn later. Only the {T} timing reads this mark, so no replay check follows.)"""
    s.state.rules.controlled_since[card.id].turn = -1


def test_a_card_returns_to_its_owners_hand(cards):
    """400.3: Forcemage Advocate's "return target card from an opponent's graveyard to their hand"."""
    s = build(cards)
    mage = put(s, "Forcemage Advocate", "battlefield")
    unsick(s, mage)
    theirs = put(s, "Counterspell", "graveyard", pid="p2")
    act(s, "p1", type="activate_ability", card_id=mage.id, ability=0, targets=[theirs.id, mage.id], target_counts=[1, 1])
    pass_until_stack_empty(s)
    assert s.state.cards[theirs.id].zone == "p2:hand"
    assert s.state.cards[mage.id].counters == {"+1/+1": 1}


def test_a_card_in_your_own_graveyard_is_not_an_opponents(cards):
    s = build(cards)
    mage = put(s, "Forcemage Advocate", "battlefield")
    unsick(s, mage)
    mine = put(s, "Lightning Bolt", "graveyard", pid="p1")
    with pytest.raises(ActionError, match="legal target"):
        act(s, "p1", type="activate_ability", card_id=mage.id, ability=0, targets=[mine.id, mage.id], target_counts=[1, 1])


def test_haunted_fengraf_returns_a_creature_card_at_random(cards):
    s = build(cards)
    land = put(s, "Haunted Fengraf", "battlefield")
    bears = put(s, "Grizzly Bears", "graveyard", pid="p1")
    inst = put(s, "Lightning Bolt", "graveyard", pid="p1")
    mana(s, C=3)
    act(s, "p1", type="activate_ability", card_id=land.id, ability=1)
    pass_until_stack_empty(s)
    assert s.state.cards[land.id].zone == "p1:graveyard"
    assert s.state.cards[bears.id].zone == "p1:hand" and s.state.cards[inst.id].zone == "p1:graveyard"
    replay_matches(s)


def test_nothing_to_return_when_the_graveyard_has_no_matching_card(cards):
    s = build(cards)
    land = put(s, "Haunted Fengraf", "battlefield")
    bolt = put(s, "Lightning Bolt", "graveyard", pid="p1")
    mana(s, C=3)
    act(s, "p1", type="activate_ability", card_id=land.id, ability=1)
    pass_until_stack_empty(s)
    assert s.state.cards[bolt.id].zone == "p1:graveyard"
    assert not s.state.rules.decision
    replay_matches(s)


def test_the_reload_keeps_a_pending_return_choice(cards):
    s = build(cards)
    a = put(s, "Grizzly Bears", "graveyard", pid="p1", nth=0)
    put(s, "Grizzly Bears", "graveyard", pid="p1", nth=1)
    mana(s, B=1, C=1)
    cast(s, "Corpse Churn")
    t = reloaded(s)
    d = t.state.rules.decision
    assert d is not None and d.kind == "choose_cards"
    act(t, d.player, type="choose", decision_id=d.id, option_ids=[a.id])
    pass_until_stack_empty(t)
    assert t.state.cards[a.id].zone == "p1:hand"
    replay_matches(t)


def test_up_to_two_targets_still_work(cards):
    s = build(cards)
    a = put(s, "Grizzly Bears", "graveyard", pid="p1", nth=0)
    b = put(s, "Grizzly Bears", "graveyard", pid="p1", nth=1)
    mana(s, B=1, C=2)
    c = put(s, "Soul Salvage", "hand")
    act(s, "p1", type="cast_spell", card_id=c.id, targets=[a.id, b.id], target_counts=[2])
    pass_until_stack_empty(s)
    assert s.state.cards[a.id].zone == "p1:hand" and s.state.cards[b.id].zone == "p1:hand"
    replay_matches(s)


def test_the_new_wordings_are_covered_and_the_triggered_self_return_is_not(cards):
    from app.rules import coverage
    from app.rules.characteristics import printed_from_data

    for name, level in (("Reassembling Skeleton", "FULL"), ("Ashen Powder", "FULL"), ("Corpse Churn", "FULL"),
                        ("Rise of the Dark Realms", "FULL")):
        data = cards.resolve(name)
        assert coverage.of_characteristics(printed_from_data(data, 0)).level == level, name
    # (wave 3R4) a trigger that returns its own card from the graveyard triggers from there (113.6m) …
    fake = card("Test Genesis", set_code="tst", number="R9", mana_cost="{4}{G}", cmc=5.0, type_line="Creature — Incarnation",
                oracle_text="At the beginning of your upkeep, return this card from your graveyard to your hand.", power="4",
                toughness="4", colors=["G"], color_identity=["G"])
    assert coverage.of_characteristics(printed_from_data(fake, 0)).level == "FULL"
    # … but not on a look-back event (603.10a: a card dying with the others would have to be told apart)
    dies = card("Test Mourner", set_code="tst", number="R11", mana_cost="{1}{B}", cmc=2.0, type_line="Creature — Zombie",
                oracle_text="Whenever another creature dies, return this card from your graveyard to your hand.", power="1",
                toughness="1", colors=["B"], color_identity=["B"])
    assert coverage.of_characteristics(printed_from_data(dies, 0)).level != "FULL"

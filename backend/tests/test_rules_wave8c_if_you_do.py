"""Wave 8C: fourth pass on "If you do" (CR 2026-09-25).

* The object a payment made as the ability resolves used (118.12): "You may sacrifice a creature. If you do, look at the
  top X cards of your library, where X is that creature's mana value" (Industrial Advancement; Shadow, Mysterious
  Assassin: "the mana value of the sacrificed permanent"), "You may exile a creature card from your graveyard. If you do,
  create a token that's a copy of that card, except it's a 4/4 black Zombie" (God-Pharaoh's Gift; Nexus of Becoming from
  the hand). The sacrificed object is read as it last existed (608.2h), the exiled card is the new object in exile
  (400.7j, 707.2: a copy of it is made from there).
* "You may mill four cards. If you do, …" (Ashcoat of the Shadow Swarm): milling is the cost (118.12) and a player can't
  mill more cards than their library holds (701.17b), so with fewer the option isn't offered (608.2d, 118.3).
* "You may sacrifice another creature or an artifact. If you do, …" (Gut, True Soul Zealot): either kind pays (118.3).
* "Put your choice of a +1/+1, first strike, or trample counter on that creature" (Assaultron Dominator, T-45 Power
  Armor): the controller chooses the kind as the instruction is carried out (608.2d); keyword counters give their
  keyword (122.1b).

Real Commander cards, their Oracle text transcribed from the card database. Every scenario checks that replaying the
recorded history reproduces the table and that the state survives a save."""

from __future__ import annotations

import pytest

from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from app.game.state import GameState
from app.rules import coverage, scripts
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, deck, enable, zone
from tests.test_rules_conditionals import (
    attack,
    creature,
    life,
    on_field,
    pick,
    through_combat,
    to_hand,
    until,
    until_asked,
)
from tests.test_rules_effects import replay_matches

EXTRA = [
    card('Industrial Advancement', set_code='tst', number='G1', mana_cost='{3}{R}', cmc=4.0, type_line='Enchantment',
         oracle_text="At the beginning of your end step, you may sacrifice a creature. If you do, look at the top X cards of your library, where X is that creature's mana value. You may put a creature card from among them onto the battlefield. Put the rest on the bottom of your library in a random order.", power=None, toughness=None, colors=['R'], color_identity=['R'], keywords=[]),
    card("God-Pharaoh's Gift", set_code='tst', number='G2', mana_cost='{7}', cmc=7.0, type_line='Artifact',
         oracle_text="At the beginning of combat on your turn, you may exile a creature card from your graveyard. If you do, create a token that's a copy of that card, except it's a 4/4 black Zombie. It gains haste until end of turn.", power=None, toughness=None, colors=[], color_identity=[], keywords=[]),
    card('Nexus of Becoming', set_code='tst', number='G3', mana_cost='{6}', cmc=6.0, type_line='Artifact',
         oracle_text="At the beginning of combat on your turn, draw a card. Then you may exile an artifact or creature card from your hand. If you do, create a token that's a copy of the exiled card, except it's a 3/3 Golem artifact creature in addition to its other types.", power=None, toughness=None, colors=[], color_identity=[], keywords=[]),
    card('Shadow, Mysterious Assassin', set_code='tst', number='G4', mana_cost='{2}{B}', cmc=3.0, type_line='Legendary Creature — Human Assassin',
         oracle_text='Deathtouch\nThrow — Whenever Shadow deals combat damage to a player, you may sacrifice another nonland permanent. If you do, draw two cards and each opponent loses life equal to the mana value of the sacrificed permanent.', power='3', toughness='3', colors=['B'], color_identity=['B'], keywords=['Deathtouch']),
    card('Ashcoat of the Shadow Swarm', set_code='tst', number='G5', mana_cost='{3}{B}', cmc=4.0, type_line='Legendary Creature — Rat Warlock',
         oracle_text='Whenever Ashcoat attacks or blocks, other Rats you control get +X/+X until end of turn, where X is the number of Rats you control.\nAt the beginning of your end step, you may mill four cards. If you do, return up to two Rat creature cards from your graveyard to your hand. (To mill a card, put the top card of your library into your graveyard.)', power='3', toughness='4', colors=['B'], color_identity=['B'], keywords=['Mill']),
    card('Gut, True Soul Zealot', set_code='tst', number='G6', mana_cost='{2}{R}', cmc=3.0, type_line='Legendary Creature — Goblin Shaman',
         oracle_text="Whenever you attack, you may sacrifice another creature or an artifact. If you do, create a 4/1 black Skeleton creature token with menace that's tapped and attacking. (It can't be blocked except by two or more creatures.)\nChoose a Background (You can have a Background as a second commander.)", power='2', toughness='2', colors=['R'], color_identity=['R'], keywords=['Choose a background']),
    card('Assaultron Dominator', set_code='tst', number='G7', mana_cost='{1}{R}', cmc=2.0, type_line='Artifact Creature — Robot',
         oracle_text='When this creature enters, you get {E}{E} (two energy counters).\nWhenever an artifact creature you control attacks, you may pay {E}. If you do, put your choice of a +1/+1, first strike, or trample counter on that creature.', power='2', toughness='2', colors=['R'], color_identity=['R'], keywords=[]),
    card('T-45 Power Armor', set_code='tst', number='G8', mana_cost='{2}', cmc=2.0, type_line='Artifact — Equipment',
         oracle_text="When this Equipment enters, you get {E}{E} (two energy counters).\nEquipped creature gets +3/+3 and doesn't untap during its controller's untap step.\nAt the beginning of your upkeep, you may pay {E}. If you do, untap equipped creature, then put your choice of a menace, trample, or lifelink counter on it.\nEquip {3}", power=None, toughness=None, colors=[], color_identity=[], keywords=['Equip']),
    card('Test Bear', set_code='tst', number='G90', mana_cost='{1}{G}', cmc=2.0, type_line='Creature — Bear',
         oracle_text='', power='2', toughness='2', colors=['G'], color_identity=['G'], keywords=[]),
    card('Test Rat', set_code='tst', number='G91', mana_cost='{B}', cmc=1.0, type_line='Creature — Rat',
         oracle_text='', power='1', toughness='1', colors=['B'], color_identity=['B'], keywords=[]),
    card('Test Golem', set_code='tst', number='G92', mana_cost='{4}', cmc=4.0, type_line='Artifact Creature — Golem',
         oracle_text='', power='3', toughness='3', colors=[], color_identity=[], keywords=[]),
]
FULL = ["Industrial Advancement", "God-Pharaoh's Gift", "Nexus of Becoming", "Shadow, Mysterious Assassin",
        "Ashcoat of the Shadow Swarm", "Gut, True Soul Zealot", "Assaultron Dominator", "T-45 Power Armor"]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def build(cards, p1=(), p2=()):
    alice = deck(cards, "Krenko, Mob Boss", [*((1, n) for n in p1), (12, "Forest")])
    bob = deck(cards, "Atraxa, Praetors' Voice", [*((1, n) for n in p2), (12, "Island")])
    s = GameSession(enable(new_game([PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=bob)], shuffle=False)),
                    cards=cards)
    act(s, "p1", type="pass_priority")  # → Alice's main phase
    return s


def roundtrip(s):
    replay_matches(s)
    saved = s.state.model_dump_json()
    loaded = GameSession(GameState.model_validate_json(saved), cards=s.cards)
    assert loaded.state.model_dump(mode="json") == s.state.model_dump(mode="json")


def card_named(s, name, pid="p1"):
    return next(c for c in s.state.cards.values() if c.name == name and c.owner == pid)


def to_graveyard(s, name, pid="p1"):
    c = card_named(s, name, pid)
    act(s, pid, type="move", card_ids=[c.id], to={"zone": "graveyard"})
    return c


def to_top(s, name, pid="p1"):
    c = card_named(s, name, pid)
    act(s, pid, type="move", card_ids=[c.id], to={"player": pid, "zone": "library"}, position="top")
    return c


def names(s, pid, z):
    return sorted(s.state.cards[c].name for c in zone(s.state, pid, z))


# -- the wording ------------------------------------------------------------------------------------
@pytest.mark.parametrize("name", FULL)
def test_coverage_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


def test_wordings():
    found = scripts.parse_effects("You may mill four cards. If you do, you gain 1 life.")
    assert found is not None and found[0][0] == {"do": "optional_payment", "who": "you", "cost": "Mill four cards", "bind": "pay0"}
    found = scripts.parse_effects("You may sacrifice a creature. If you do, you gain life equal to that creature's mana value.")
    assert found is not None and found[0][-1]["n"] == {"mana_value": "ref:pay0"}
    found = scripts.parse_effects("You may exile a creature card from your graveyard. If you do, create a token that's a copy of that card.")
    assert found is not None and found[0][-1]["who"] == "ref:pay0"
    found = scripts.parse_effects("Put your choice of a reach, vigilance, or trample counter on it.", "event")
    assert found is not None and found[0][0] == {"do": "pick_counter", "who": "event", "kinds": ["reach", "vigilance", "trample"]}


def test_refused_forms():
    # a counter that isn't a kind the engine models, one kind twice, or a single kind
    assert scripts.parse_effects("Put your choice of a fate, flying, or trample counter on it.", "event") is None
    assert scripts.parse_effects("Put your choice of a flying or a flying counter on it.", "event") is None
    # "the exiled card" with no payment before it, and an exile payment's "its" (the card? the source?) stay manual
    assert scripts.parse_effects("Create a token that's a copy of the exiled card.") is None
    assert scripts.parse_effects("You may exile a creature card from your graveyard. If you do, you gain life equal to its mana value.") is None
    # a trigger about an object: "that creature" stays the trigger's object, never the sacrificed one
    found = scripts.parse_effects("You may sacrifice a creature. If you do, you gain life equal to that creature's mana value.", "event")
    assert found is None or "ref:pay0" not in str(found)


def resolved(s):
    """Let the stack empty; stop where the active player is asked to declare attackers."""
    until(s, lambda s: not s.state.zones.get("stack")
          and (s.state.rules.decision is None or s.state.rules.decision.kind == "declare_attackers"))


def ch(s, c):
    from app.rules.plan import Plan

    return Plan(s.state, "p1", s.cards, None).ch(s.state.cards[c.id])


# -- exile a card: a copy of it ---------------------------------------------------------------------
@pytest.mark.parametrize("paid", [True, False])
def test_god_pharaohs_gift_copies_the_exiled_card_as_a_4_4_zombie(cards, paid):
    s = build(cards, p1=("God-Pharaoh's Gift", "Test Bear"))
    on_field(s, "God-Pharaoh's Gift")
    bear = to_graveyard(s, "Test Bear")
    act(s, "p1", type="pass_priority")  # → combat
    d = until_asked(s)
    assert d is not None and d.player == "p1" and [o.id for o in d.options][:2] == ["pay", "decline"]
    assert "options" not in s.view("p2")["rules"]["decision"]
    pick(s, "pay" if paid else "decline")
    resolved(s)
    tokens = [c for c in s.state.cards.values() if c.is_token and c.name == "Test Bear"]
    if not paid:
        assert not tokens and s.state.cards[bear.id].zone == "p1:graveyard"
    else:
        assert s.state.cards[bear.id].zone == "p1:exile"  # 118.12: the cost, paid
        (tok,) = tokens
        got = ch(s, tok)
        assert tok.zone == "p1:battlefield" and got.pt == (4, 4) and got.colors == frozenset({"B"}) and got.subtypes == {"Zombie"}
        assert "haste" in got.keywords  # "It gains haste until end of turn."
    roundtrip(s)


def the_end_step_asked(s):
    """Play on until a payment is offered (the end step's trigger)."""
    until(s, lambda s: s.state.rules.decision is not None
          and [o.id for o in s.state.rules.decision.options][:2] == ["pay", "decline"])


def resolved_end(s):
    until(s, lambda s: not s.state.zones.get("stack") and s.state.rules.decision is None)


def test_nexus_of_becoming_exiles_from_the_hand_and_copies_it_as_a_golem(cards):
    s = build(cards, p1=("Nexus of Becoming", "Test Golem", "Test Bear"))
    on_field(s, "Nexus of Becoming")
    golem = to_hand(s, "Test Golem")
    bear = to_hand(s, "Test Bear")
    act(s, "p1", type="pass_priority")  # → combat: draw a card, then the choice
    d = until_asked(s)
    assert d is not None and d.player == "p1" and [o.id for o in d.options][:2] == ["pay", "decline"]
    pick(s, "pay")
    d = s.state.rules.decision
    assert d is not None and d.kind == "choose_cards" and d.player == "p1"
    # an artifact or creature card from the hand: the two cards put there, never the lands drawn
    assert {o.id for o in d.options} == {golem.id, bear.id}
    assert "options" not in s.view("p2")["rules"]["decision"]  # (chosen privately)
    pick(s, golem.id)
    resolved(s)
    assert s.state.cards[golem.id].zone == "p1:exile" and s.state.cards[bear.id].zone == "p1:hand"
    (tok,) = [c for c in s.state.cards.values() if c.is_token and c.name == "Test Golem"]
    got = ch(s, tok)
    assert tok.zone == "p1:battlefield" and got.pt == (3, 3) and got.subtypes == {"Golem"} and {"Artifact", "Creature"} <= set(got.types)
    roundtrip(s)


# -- sacrifice a creature: its mana value ------------------------------------------------------------
def test_industrial_advancement_looks_at_as_many_cards_as_the_sacrificed_creatures_mana_value(cards):
    s = build(cards, p1=("Industrial Advancement", "Test Bear", "Test Rat"))
    on_field(s, "Industrial Advancement")
    bear = on_field(s, "Test Bear")  # mana value 2
    rat = to_top(s, "Test Rat")
    top3 = list(zone(s.state, "p1", "library"))[:3]
    the_end_step_asked(s)
    d = s.state.rules.decision
    assert d is not None and d.player == "p1" and [o.id for o in d.options][:2] == ["pay", "decline"]
    pick(s, "pay")
    d = s.state.rules.decision
    assert d is not None and d.kind == "choose_cards"  # (look at the top two, put a creature card from among them)
    assert {o.id for o in d.options} == {rat.id}  # 2 cards: the Rat on top and the next card — not the third
    assert top3[2] not in {o.id for o in d.options}
    pick(s, rat.id)
    resolved_end(s)
    assert s.state.cards[bear.id].zone == "p1:graveyard"  # 701.21a
    assert s.state.cards[rat.id].zone == "p1:battlefield"
    roundtrip(s)


def test_industrial_advancement_a_token_has_mana_value_zero(cards):
    s = build(cards, p1=("Industrial Advancement", "Test Rat"))
    on_field(s, "Industrial Advancement")
    token = creature(s, "p1", "Goblin Token")
    rat = to_top(s, "Test Rat")
    the_end_step_asked(s)
    pick(s, "pay")
    resolved_end(s)
    assert token.id not in s.state.cards  # (sacrificed: a token ceases to exist)
    assert s.state.cards[rat.id].zone == "p1:library"  # X is 0: nothing to look at
    roundtrip(s)


def ready(s, name, pid="p1"):
    """A creature that can attack this turn (the table is set up by hand)."""
    c = on_field(s, name, pid)
    from app.game.rules_state import ControlMark

    s.state.rules.controlled_since[c.id] = ControlMark(controller=pid, turn=0)  # (since before this turn began)
    return c


def attack_with(s, *creatures):
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_attackers")
    attack(s, *((c, "p2") for c in creatures))


def test_shadow_draws_two_and_each_opponent_loses_the_sacrificed_permanents_mana_value(cards):
    s = build(cards, p1=("Shadow, Mysterious Assassin", "Test Golem"))
    shadow = ready(s, "Shadow, Mysterious Assassin")
    golem = on_field(s, "Test Golem")  # mana value 4
    act(s, "p1", type="pass_priority")  # → combat
    attack_with(s, shadow)
    the_end_step_asked(s)
    bob, cards_in_hand = life(s, "p2"), len(zone(s.state, "p1", "hand"))
    pick(s, "pay")
    d = s.state.rules.decision
    if d is not None and d.kind == "choose_cards":
        assert {o.id for o in d.options} == {golem.id}  # another nonland permanent
        pick(s, golem.id)
    through_combat(s)
    assert s.state.cards[golem.id].zone == "p1:graveyard"
    assert life(s, "p2") == bob - 4  # (the 3 combat damage was dealt before the prompt) 4 life: the sacrificed Golem's mana value
    assert len(zone(s.state, "p1", "hand")) == cards_in_hand + 2
    roundtrip(s)


def test_shadow_declined_nothing_is_sacrificed(cards):
    s = build(cards, p1=("Shadow, Mysterious Assassin", "Test Golem"))
    shadow = ready(s, "Shadow, Mysterious Assassin")
    golem = on_field(s, "Test Golem")
    act(s, "p1", type="pass_priority")
    attack_with(s, shadow)
    the_end_step_asked(s)
    bob = life(s, "p2")
    pick(s, "decline")
    through_combat(s)
    assert s.state.cards[golem.id].zone == "p1:battlefield" and life(s, "p2") == bob
    roundtrip(s)


# -- mill: the cost ---------------------------------------------------------------------------------
def test_ashcoat_mills_four_then_returns_up_to_two_rats(cards):
    s = build(cards, p1=("Ashcoat of the Shadow Swarm", "Test Rat"))
    on_field(s, "Ashcoat of the Shadow Swarm")
    rat = to_graveyard(s, "Test Rat")
    library = len(zone(s.state, "p1", "library"))
    the_end_step_asked(s)
    pick(s, "pay")
    d = s.state.rules.decision
    if d is not None and d.kind == "choose_cards":
        assert rat.id in {o.id for o in d.options}
        pick(s, rat.id)
    resolved_end(s)
    assert len(zone(s.state, "p1", "library")) == library - 4  # 701.17a
    assert s.state.cards[rat.id].zone == "p1:hand"
    roundtrip(s)


def test_ashcoat_declined_mills_nothing(cards):
    s = build(cards, p1=("Ashcoat of the Shadow Swarm", "Test Rat"))
    on_field(s, "Ashcoat of the Shadow Swarm")
    rat = to_graveyard(s, "Test Rat")
    library = len(zone(s.state, "p1", "library"))
    the_end_step_asked(s)
    pick(s, "decline")
    resolved_end(s)
    assert len(zone(s.state, "p1", "library")) == library and s.state.cards[rat.id].zone == "p1:graveyard"
    roundtrip(s)


def test_ashcoat_is_not_offered_when_the_library_is_too_small(cards):
    """701.17b: a player can't mill more cards than their library holds, so the option isn't offered (608.2d, 118.3)."""
    s = build(cards, p1=("Ashcoat of the Shadow Swarm", "Test Rat"))
    on_field(s, "Ashcoat of the Shadow Swarm")
    rat = to_graveyard(s, "Test Rat")
    for c in list(zone(s.state, "p1", "library"))[3:]:
        act(s, "p1", type="move", card_ids=[c], to={"zone": "graveyard"})
    assert len(zone(s.state, "p1", "library")) == 3
    turn = s.state.turn.number
    until(s, lambda s: s.state.turn.number > turn and s.state.turn.phase == "main1")
    assert s.state.cards[rat.id].zone == "p1:graveyard"
    roundtrip(s)


# -- sacrifice another creature or an artifact -------------------------------------------------------
@pytest.mark.parametrize("fodder", ["Test Bear", "Sol Ring"])
def test_gut_sacrifices_a_creature_or_an_artifact_for_a_tapped_and_attacking_skeleton(cards, fodder):
    s = build(cards, p1=("Gut, True Soul Zealot", "Test Bear", "Sol Ring"))
    gut = ready(s, "Gut, True Soul Zealot")
    bear, ring = on_field(s, "Test Bear"), on_field(s, "Sol Ring")
    act(s, "p1", type="pass_priority")  # → combat
    attack_with(s, gut)
    the_end_step_asked(s)
    pick(s, "pay")
    d = s.state.rules.decision
    assert d is not None and d.kind == "choose_cards"
    assert {o.id for o in d.options} == {bear.id, ring.id}  # another creature, or an artifact (Gut itself is neither "another")
    pick(s, (bear if fodder == "Test Bear" else ring).id)
    until(s, lambda s: not s.state.zones.get("stack") and s.state.rules.decision is None or s.state.turn.phase == "main2")
    assert s.state.cards[(bear if fodder == "Test Bear" else ring).id].zone == "p1:graveyard"
    (skel,) = [c for c in s.state.cards.values() if c.is_token and c.name == "Skeleton"]
    got = ch(s, skel)
    assert got.pt == (4, 1) and "menace" in got.keywords and skel.tapped
    roundtrip(s)


def test_gut_with_nothing_to_sacrifice_is_not_asked(cards):
    s = build(cards, p1=("Gut, True Soul Zealot",))
    gut = ready(s, "Gut, True Soul Zealot")
    act(s, "p1", type="pass_priority")
    attack_with(s, gut)
    through_combat(s)
    assert not [c for c in s.state.cards.values() if c.is_token and c.name == "Skeleton"]
    roundtrip(s)


# -- your choice of a counter --------------------------------------------------------------------------
def test_assaultron_dominator_pays_energy_and_the_controller_picks_the_counter(cards):
    s = build(cards, p1=("Assaultron Dominator",))
    robot = ready(s, "Assaultron Dominator")
    act(s, "p1", type="resource", player="p1", key="energy", delta=2)  # (what its enters trigger gives)
    act(s, "p1", type="pass_priority")  # → combat
    attack_with(s, robot)
    the_end_step_asked(s)
    pick(s, "pay")
    d = s.state.rules.decision
    assert d is not None and d.kind == "choose_one" and d.player == "p1"
    assert [o.id for o in d.options] == ["+1/+1", "first strike", "trample"]
    pick(s, "first strike")
    through_combat(s)
    assert s.state.players["p1"].resources["energy"] == 1  # {E} paid
    assert s.state.cards[robot.id].counters.get("first strike") == 1
    assert "first strike" in ch(s, robot).keywords  # 122.1b, 613.1f
    roundtrip(s)


def test_assaultron_dominator_declining_keeps_the_energy(cards):
    s = build(cards, p1=("Assaultron Dominator",))
    robot = ready(s, "Assaultron Dominator")
    act(s, "p1", type="resource", player="p1", key="energy", delta=2)  # (what its enters trigger gives)
    act(s, "p1", type="pass_priority")
    attack_with(s, robot)
    the_end_step_asked(s)
    pick(s, "decline")
    through_combat(s)
    assert not s.state.cards[robot.id].counters and s.state.players["p1"].resources["energy"] == 2
    roundtrip(s)


def test_t45_power_armor_untaps_and_the_controller_picks_a_counter(cards):
    s = build(cards, p1=("T-45 Power Armor", "Test Bear"))
    armor = on_field(s, "T-45 Power Armor")
    bear = on_field(s, "Test Bear")
    act(s, "p1", type="resource", player="p1", key="energy", delta=2)
    act(s, "p1", type="attach", card_ids=[armor.id], to=bear.id)
    act(s, "p1", type="tap", card_ids=[bear.id])
    turn = s.state.turn.number
    until(s, lambda s: s.state.turn.number > turn + 1 and s.state.turn.active_player == "p1" and s.state.rules.decision is not None
          and [o.id for o in s.state.rules.decision.options][:2] == ["pay", "decline"])
    pick(s, "pay")
    d = s.state.rules.decision
    assert d is not None and [o.id for o in d.options] == ["menace", "trample", "lifelink"]
    pick(s, "lifelink")
    until(s, lambda s: not s.state.zones.get("stack") and s.state.rules.decision is None)
    assert not s.state.cards[bear.id].tapped  # ("doesn't untap during its controller's untap step", but this untaps it)
    assert s.state.cards[bear.id].counters.get("lifelink") == 1
    roundtrip(s)

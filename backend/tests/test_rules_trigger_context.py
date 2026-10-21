"""Trigger-context references read through the resolving ability's TriggerEvent (app/rules/context.py):
"it" / "that creature" (the object the event happened to, only while it's still that object where
it was: 400.7), "its power" from last known information after it died (603.10a, 608.2h), a dies
trigger's "return it …" finding the new object in the graveyard and only there (400.7e, 603.6c),
"that player", "its controller", "that many", "they" (every object of a "one or more" event,
603.2c) — captured as the ability triggers and carried through waiting, saves, undo and replay."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.cards.importer import build_database
from app.config import Settings
from app.game.history import History
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, zone
from tests.test_rules_attachments import build, mana, named, token
from tests.test_rules_combat import attack, automate, creature, table
from tests.test_rules_effects import pass_until_stack_empty, replay_matches

EXTRA = [
    card("Test Homing Spirit", set_code="tst", number="TC1", mana_cost="{1}{U}", cmc=2.0, type_line="Creature — Spirit",
         oracle_text="When this creature dies, return it to its owner's hand.", power="1", toughness="1",
         colors=["U"], color_identity=["U"]),
    card("Test Phoenix", set_code="tst", number="TC2", mana_cost="{2}{R}", cmc=3.0, type_line="Creature — Phoenix",
         oracle_text="When this creature dies, return it to the battlefield under its owner's control.",
         power="3", toughness="1", colors=["R"], color_identity=["R"]),
]


@pytest.fixture()
def card_db(settings: Settings) -> Path:
    settings.ensure_dirs()
    build_database(fixture_cards() + EXTRA, settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def responsive(s):
    for prefs in s.state.rules.prefs.values():
        prefs.response = "on"  # (everyone stops at each object on the stack)


def on_battlefield(s, name):
    c = named(s, name)
    act(s, "p1", type="move", card_ids=[c.id], to={"zone": "battlefield"})
    return c


def quake(s):
    """Deal 1 damage to each creature (an ability: the deaths are the rules engine's)."""
    src = token(s, "p1", "Quake", "5/5", text="{1}: This creature deals 1 damage to each creature.")
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=src.id, ability=0)


def resolve_all(s, rounds=12):
    for _ in range(rounds):
        d = s.state.rules.decision
        if d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return


def stack_entry(s, name):
    return next((e for e in s.state.rules.stack.values() if e.name == name), None)


def wait_for(s, name, rounds=10):
    for _ in range(rounds):
        if stack_entry(s, name) is not None:
            return stack_entry(s, name)
        act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError(f"{name}'s ability never went on the stack")


# -- "its power": last known information of the object that died (603.10a, 608.2h) ----------------
def test_dies_draws_cards_equal_to_its_power_as_it_last_existed(cards):
    s = build(cards)
    token(s, "p1", "Collector", "5/5", text="Whenever a creature you control dies, draw cards equal to its power.")
    victim = token(s, "p1", "Victim", "1/1", text="{1}: Sacrifice this creature.")
    act(s, "p1", type="counter", card_ids=[victim.id], kind="+1/+1", delta=2)  # a 3/3 as it dies
    hand = len(zone(s.state, "p1", "hand"))
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=victim.id, ability=0)
    pass_until_stack_empty(s)
    pass_until_stack_empty(s)
    assert len(zone(s.state, "p1", "hand")) == hand + 3
    replay_matches(s)


def test_gain_life_equal_to_its_toughness(cards):
    s = build(cards)
    token(s, "p1", "Avatar", "5/5", text="Whenever another creature you control dies, you gain life equal to its toughness.")
    token(s, "p1", "Wall", "0/1")
    quake(s)
    pass_until_stack_empty(s)
    pass_until_stack_empty(s)
    assert s.state.players["p1"].life == 41
    replay_matches(s)


# -- "return it": the new object in the graveyard, and only there (400.7e, 603.6c) -----------------
def test_another_creature_dies_return_it_to_hand(cards):
    s = build(cards, "Llanowar Elves")
    token(s, "p1", "Shepherd", "5/5", text="Whenever another creature you control dies, return it to its owner's hand.")
    elf = on_battlefield(s, "Llanowar Elves")
    quake(s)
    pass_until_stack_empty(s)
    pass_until_stack_empty(s)
    assert s.state.cards[elf.id].zone == "p1:hand"
    replay_matches(s)


def test_it_does_not_follow_the_card_after_it_left_the_graveyard(cards):
    # 400.7 / 603.6: it left the graveyard and came back — a new object: "it" finds nothing
    s = build(cards, "Llanowar Elves")
    responsive(s)
    token(s, "p1", "Shepherd", "5/5", text="Whenever another creature you control dies, return it to its owner's hand.")
    elf = on_battlefield(s, "Llanowar Elves")
    quake(s)
    entry = wait_for(s, "Shepherd")
    assert entry.event is not None and entry.event.kind == "die"
    assert entry.event.new_objects and entry.event.new_objects[0].zone == "p1:graveyard"
    act(s, "p1", type="move", card_ids=[elf.id], to={"zone": "exile"})
    act(s, "p1", type="move", card_ids=[elf.id], to={"zone": "graveyard"})
    resolve_all(s)
    assert s.state.cards[elf.id].zone == "p1:graveyard"


def test_dies_self_returns_to_the_battlefield(cards):
    s = build(cards, "Test Phoenix")
    phoenix = on_battlefield(s, "Test Phoenix")
    before = s.state.rules.object_id(phoenix.id)
    quake(s)
    pass_until_stack_empty(s)
    pass_until_stack_empty(s)
    assert s.state.cards[phoenix.id].zone == "p1:battlefield"
    assert s.state.rules.object_id(phoenix.id) != before  # a new object (400.7)
    replay_matches(s)


def test_dies_self_return_to_hand_waits_and_survives_save_and_undo(cards):
    s = build(cards, "Test Homing Spirit")
    responsive(s)
    spirit = on_battlefield(s, "Test Homing Spirit")
    token(s, "p1", "Filler", "5/5")
    quake(s)
    entry = wait_for(s, "Test Homing Spirit")
    assert s.state.cards[spirit.id].zone == "p1:graveyard"
    # saved and loaded (replayed from the history) with the trigger waiting: its event is kept
    loaded = History.from_dict(s.history.to_dict()).rebuild()
    assert next(e for e in loaded.rules.stack.values() if e.name == "Test Homing Spirit").event == entry.event
    assert s.history.rebuild().model_dump(mode="json") == s.state.model_dump(mode="json")
    # another action, undone and redone: the waiting trigger still remembers what it triggered on
    act(s, "p1", type="create_token", player="p1", token={"name": "Extra", "type_line": "Token Creature — Test"})
    s.undo("p1")
    s.redo("p1")
    assert stack_entry(s, "Test Homing Spirit").event == entry.event
    resolve_all(s)
    assert s.state.cards[spirit.id].zone == "p1:hand"
    replay_matches(s)


def test_a_token_that_died_is_not_returned(cards):
    # 704.5d / 111.7: the token ceased to exist in the graveyard; "it" finds nothing
    s = build(cards)
    token(s, "p1", "Shepherd", "5/5", text="Whenever another creature you control dies, return it to its owner's hand.")
    t = token(s, "p1", "Sprout", "1/1")
    quake(s)
    pass_until_stack_empty(s)
    pass_until_stack_empty(s)
    assert t.id not in s.state.cards
    assert not [c for c in zone(s.state, "p1", "hand") if s.state.cards[c].name == "Sprout"]


# -- "it" while it's still that object where it was (400.7) ---------------------------------------
@pytest.mark.parametrize("flicker", [False, True])
def test_it_does_not_find_a_flickered_new_object(cards, flicker):
    s = build(cards, "Llanowar Elves")
    responsive(s)
    token(s, "p1", "Taunter", "5/5", text="Whenever a creature you control becomes tapped, put a +1/+1 counter on it.")
    elf = on_battlefield(s, "Llanowar Elves")
    src = token(s, "p1", "Tapper", text="{1}: Tap target creature.")
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=src.id, ability=0, targets=[elf.id])
    wait_for(s, "Taunter")
    if flicker:  # exiled and returned — a new object (400.7), not the one that became tapped
        act(s, "p1", type="move", card_ids=[elf.id], to={"zone": "exile"})
        act(s, "p1", type="move", card_ids=[elf.id], to={"zone": "battlefield"})
    resolve_all(s)
    assert s.state.cards[elf.id].counters == ({} if flicker else {"+1/+1": 1})


# -- players: "that player", "its controller" ------------------------------------------------------
def test_that_player_is_the_player_dealt_combat_damage(cards):
    s = table(cards)
    creature(s, "p1", "Specter", "2/2", text="Whenever this creature deals combat damage to a player, that player discards a card.")
    act(s, "p2", type="draw", player="p2", count=2)
    hand = len(zone(s.state, "p2", "hand"))
    automate(s)
    attack(s, (named(s, "Specter"), "p2"))
    for _ in range(12):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
        elif d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[d.options[0].id])
        elif s.state.rules.priority and (s.state.zones.get("stack") or s.state.turn.phase in ("declare_blockers", "combat_damage")):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    assert len(zone(s.state, "p2", "hand")) == hand - 1
    replay_matches(s)


def test_that_creatures_controller_from_last_known_information(cards):
    s = build(cards)
    token(s, "p1", "Reaper", "5/5", text="Whenever a creature dies, that creature's controller loses 1 life.")
    token(s, "p2", "Theirs", "1/1")
    quake(s)
    pass_until_stack_empty(s)
    pass_until_stack_empty(s)
    assert s.state.players["p2"].life == 39 and s.state.players["p1"].life == 40
    replay_matches(s)


# -- "one or more": every object and the count of the batch (603.2c) ------------------------------
def test_they_are_every_attacking_creature(cards):
    s = table(cards)
    creature(s, "p1", "Warleader", "1/1", text="Whenever one or more creatures you control attack, they get +1/+0 until end of turn.")
    a = creature(s, "p1", "A")
    b = creature(s, "p1", "B")
    automate(s)
    attack(s, (a, "p2"), (b, "p2"))
    pass_until_stack_empty(s)
    from app.rules.plan import Plan

    plan = Plan(s.state, "p1", cards, None)
    assert plan.ch(s.state.cards[a.id]).pt == (3, 2) and plan.ch(s.state.cards[b.id]).pt == (3, 2)
    assert plan.ch(named(s, "Warleader")).pt == (1, 1)
    replay_matches(s)


def test_that_many_is_the_number_discarded(cards):
    s = build(cards)
    act(s, "p1", type="draw", player="p1", count=3)
    token(s, "p1", "Archivist", "1/1", text="Whenever you discard one or more cards, you gain that much life.")
    src = token(s, "p1", "Looter", text="{1}: Discard two cards.")
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=src.id, ability=0)
    resolve_all(s)
    assert s.state.players["p1"].life == 42  # one trigger for the two discards (603.2c): 2
    replay_matches(s)


@pytest.mark.parametrize(("text", "ok"), [
    ("Whenever a creature you control dies, draw cards equal to its power.", True),
    ("When this creature dies, return it to the battlefield under its owner's control.", True),
    ("Whenever a creature dies, that creature's controller loses 1 life.", True),
    ("Whenever one or more creatures you control attack, they get +1/+0 until end of turn.", True),
    # not an object a trigger can name: manual
    ("Whenever you gain life, draw cards equal to its power.", False),
    ("At the beginning of your upkeep, its controller loses 1 life.", False),
    ("Whenever a creature you control dies, put a +1/+1 counter on it.", False),  # (it's in a graveyard)
    ("Exile target creature. Return it to the battlefield under its owner's control.", False),  # (a blink)
    # "that creature" is the creature on the other side: the event names it since wave 6B (TriggerEvent.other) for a
    # block, and since wave 6D (app/rules/other_side.py) for "deals damage to a creature"
    ("Whenever this creature becomes blocked by a creature, destroy that creature.", True),
    ("Whenever this creature deals damage to a creature, exile that creature.", True),
    # (a bare "it" before "that creature" in a damage-to-a-creature trigger: the source? not read)
    ("Whenever this creature deals damage to a creature, it deals 2 damage to that creature.", False),
    # "that player" after a target player is that target, not the event's player (wave 9C: the caster of "Whenever you cast"
    # is "you", never "that player", so the only player it can name is the target)
    ("Whenever you cast a spell from exile, this creature deals 2 damage to target player. That player discards a card.",
     True),
    # The enchanted-creature antecedent remains the damage source and the power reference.
    ("When this creature enters, tap enchanted creature. It deals damage to you equal to its power.", True),
    # a card returned from a graveyard: its printed characteristics (a within-resolution binding)
    ("When this creature enters, return target creature card from your graveyard to your hand. "
     "You gain life equal to its power.", True),
    # "~ deals damage equal to its power": the source's own power
    ("When this creature enters, it deals damage equal to its power to any target.", True),
])
def test_trigger_references_are_read_or_refused(text, ok):
    from app.rules import scripts
    from tests.test_rules_scripts import ch

    assert bool(scripts.definitions(ch("X", "Creature", text))) == ok, text

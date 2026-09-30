"""Modal triggered and activated abilities (CR 700.2, 603.3c, 602.2b), app/rules/modal_abilities.py.

Modes of a modal triggered ability are announced as it is put on the stack, before its targets (603.3c,
700.2b); those of an activated ability while it is activated, before targets and costs (602.2b →
601.2b); a mode with no legal target can't be chosen, and an ability with no mode to choose is removed
from the stack (700.2b); each chosen mode has its own target (700.2c, 700.2f) and the modes are carried
out in printed order (608.2c). "Choose one that hasn't been chosen [this turn]" remembers, per object
(400.7), the modes already chosen (the CR has no rule for it: it is Oracle text, and the card rulings
say a mode counts once it was announced). Every scenario also checks that replaying the recorded
history reproduces the table, and the decisions' continuations survive a save and a reload.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.importer import build_database
from app.config import Settings
from app.game.errors import ActionError
from app.game.session import GameSession
from app.rules import coverage, scripts
from app.rules.characteristics import printed_from_data
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, zone
from tests.test_rules_attachments import build, mana, named, to_hand, token
from tests.test_rules_effects import pass_until_stack_empty, replay_matches
from tests.test_rules_scripts import ch as characteristics

# Real Commander-legal cards (Oracle text as in the card database, reminder text included).
EXTRA = [
    card("Knight of Autumn", set_code="tst", number="M1", mana_cost="{1}{G}{W}", cmc=3.0, type_line="Creature — Dryad Knight",
         oracle_text="When this creature enters, choose one —\n• Put two +1/+1 counters on this creature.\n"
                     "• Destroy target artifact or enchantment.\n• You gain 4 life.",
         power="2", toughness="1", colors=["G", "W"], color_identity=["G", "W"]),
    card("Felidar Retreat", set_code="tst", number="M2", mana_cost="{3}{W}", cmc=4.0, type_line="Enchantment",
         oracle_text="Landfall — Whenever a land you control enters, choose one —\n• Create a 2/2 white Cat Beast creature token.\n"
                     "• Put a +1/+1 counter on each creature you control. Those creatures gain vigilance until end of turn.",
         colors=["W"], color_identity=["W"]),
    card("Cankerbloom", set_code="tst", number="M3", mana_cost="{1}{G}", cmc=2.0, type_line="Creature — Phyrexian Fungus",
         oracle_text="{1}, Sacrifice this creature: Choose one —\n• Destroy target artifact.\n• Destroy target enchantment.\n"
                     "• Proliferate. (Choose any number of permanents and/or players, then give each another counter of each "
                     "kind already there.)",
         power="3", toughness="2", colors=["G"], color_identity=["G"]),
    card("Flash Thompson, Spider-Fan", set_code="tst", number="M4", mana_cost="{1}{W}", cmc=2.0,
         type_line="Legendary Creature — Human Citizen",
         oracle_text="Flash\nWhen Flash Thompson enters, choose one or both —\n• Heckle — Tap target creature.\n"
                     "• Hero Worship — Untap target creature.",
         power="2", toughness="2", colors=["W"], color_identity=["W"]),
    card("Shambling Ghast", set_code="tst", number="M5", mana_cost="{B}", cmc=1.0, type_line="Creature — Zombie",
         oracle_text="When this creature dies, choose one —\n• Target creature an opponent controls gets -1/-1 until end of turn.\n"
                     "• Create a Treasure token. (It's an artifact with \"{T}, Sacrifice this token: Add one mana of any color.\")",
         power="1", toughness="1", colors=["B"], color_identity=["B"]),
    card("Three Bowls of Porridge", set_code="tst", number="M6", mana_cost="{2}", cmc=2.0, type_line="Artifact — Food",
         oracle_text="{2}, {T}: Choose one that hasn't been chosen —\n• This artifact deals 2 damage to target creature.\n"
                     "• Tap target creature.\n• Sacrifice this artifact. You gain 3 life."),
    card("Kargan Intimidator", set_code="tst", number="M7", mana_cost="{1}{R}", cmc=2.0, type_line="Creature — Human Warrior",
         oracle_text="Cowards can't block Warriors.\n{1}: Choose one that hasn't been chosen this turn —\n"
                     "• This creature gets +1/+1 until end of turn.\n• Target creature becomes a Coward until end of turn.\n"
                     "• Target Warrior gains trample until end of turn.",
         power="3", toughness="1", colors=["R"], color_identity=["R"]),
    card("Sawblade Slinger", set_code="tst", number="M8", mana_cost="{3}{G}", cmc=4.0, type_line="Creature — Human Archer",
         oracle_text="When this creature enters, choose up to one —\n• Destroy target artifact an opponent controls.\n"
                     "• This creature fights target Zombie an opponent controls.",
         power="4", toughness="3", colors=["G"], color_identity=["G"]),
    card("Craftwork Crusher", set_code="tst", number="M9", mana_cost="{3}{R}{R}{G}{G}", cmc=7.0,
         type_line="Artifact Creature — Boar Construct",
         oracle_text="Trample\nWhen this creature enters, choose two —\n• This creature deals 4 damage to target creature or "
                     "planeswalker.\n• Create a 2/2 colorless Wizard Soldier creature token named Cadet.\n• Draw a card.",
         power="7", toughness="5", colors=["G", "R"], color_identity=["G", "R"]),
    # (not a real card: Craftwork Crusher's "choose two" header over two of Cankerbloom's targeted modes)
    card("Test Two-Mode Golem", set_code="tst", number="X1", mana_cost="{1}", cmc=1.0, type_line="Creature — Golem",
         oracle_text="When this creature enters, choose two —\n• Destroy target artifact.\n• Destroy target enchantment.\n"
                     "• Draw a card.", power="1", toughness="1"),
    card("Monument to Endurance", set_code="tst", number="M12", mana_cost="{3}", cmc=3.0, type_line="Artifact",
         oracle_text="Whenever you discard a card, choose one that hasn't been chosen this turn —\n• Draw a card.\n"
                     "• Create a Treasure token.\n• Each opponent loses 3 life."),
    card("Phoenix Down", set_code="tst", number="M11", mana_cost="{W}", cmc=1.0, type_line="Artifact",
         oracle_text="{1}{W}, {T}, Exile this artifact: Choose one —\n• Return target creature card with mana value 4 or less "
                     "from your graveyard to the battlefield tapped.\n• Exile target Skeleton, Spirit, or Zombie.",
         colors=["W"], color_identity=["W"]),
    card("Kimoyo Beads", set_code="tst", number="M10", mana_cost="{4}", cmc=4.0, type_line="Artifact",
         oracle_text="At the beginning of your end step, choose one that hasn't been chosen —\n• AV Bead — Draw a card.\n"
                     "• Communication Bead — Create two 1/1 white Soldier creature tokens.\n• Prime Bead — You gain 3 life. "
                     "Exile this artifact, then return it to the battlefield under its owner's control."),
]


@pytest.fixture()
def card_db(settings: Settings) -> Path:
    settings.ensure_dirs()
    build_database(fixture_cards() + EXTRA, settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def rules(s):
    return s.state.rules


def respond_on(s):
    for pid in s.state.players:
        act(s, pid, type="set_prefs", response="on")  # (everyone stops at each object on the stack)


def reloaded(s):
    """The table as a fresh session rebuilt from the saved history (a save and a load)."""
    return GameSession(s.history.rebuild(), cards=s.cards)


def battlefield(s, name, pid="p1"):
    c = named(s, name)
    act(s, pid, type="move", card_ids=[c.id], to={"player": pid, "zone": "battlefield"})
    return c


def cast(s, name, **m):
    """Cast a card from Alice's hand (paying with the mana given) and let it resolve."""
    c = to_hand(s, name)
    mana(s, **m)
    act(s, "p1", type="cast_spell", card_id=c.id)
    return c


def choose(s, *option_ids):
    d = rules(s).decision
    act(s, d.player, type="choose", decision_id=d.id, option_ids=list(option_ids))


def step(s):
    d = rules(s).decision
    return (d.resume or {}).get("step") if d else None


def offered(s):
    return [o.id for o in rules(s).decision.options]


def stack_modes(s):
    """The chosen modes shown on the ability objects on the stack, top first."""
    return [list(s.state.cards[cid].stack_info.modes) if s.state.cards[cid].stack_info else []
            for cid in reversed(s.state.zones.get("stack", []))]


def on_stack(s):
    """The names of the objects on the stack with rules entries, bottom to top."""
    return [rules(s).stack[c].name for c in s.state.zones.get("stack", []) if c in rules(s).stack]


def log_text(s):
    return json.dumps(s.view("p2")["log"])


# -- a modal "When ~ enters" trigger: modes, then the chosen mode's target (603.3c, 700.2b) -----------------
def test_modal_enters_trigger_asks_the_modes_then_the_target(cards):
    """Knight of Autumn: the artifact-or-enchantment mode is offered only with a legal target (700.2b)."""
    s = build(cards, "Knight of Autumn")
    respond_on(s)
    cast(s, "Knight of Autumn", G=1, W=1, C=1)
    pass_until_stack_empty(s)  # (the creature spell resolves, its trigger waits for its modes)
    assert step(s) == "trigger_modes" and offered(s) == ["0:0", "2:0"]  # (nothing to destroy: mode 1 isn't offered)
    d = rules(s).decision
    assert (d.min_choices, d.max_choices) == (1, 1) and d.player == "p1" and d.kind == "choose_cards"
    assert rules(s).stack == {} and s.state.zones.get("stack", []) == []  # (not on the stack until the mode is chosen)
    choose(s, "2:0")  # You gain 4 life.
    assert rules(s).decision is None and stack_modes(s) == [["You gain 4 life."]]
    entry = next(iter(rules(s).stack.values()))
    assert entry.kind == "trigger" and entry.modes == [2] and entry.targets == []
    pass_until_stack_empty(s)
    assert s.state.players["p1"].life == 44
    assert "put an ability on the stack" in log_text(s)
    replay_matches(s)


def test_modal_trigger_with_a_target_chooses_it_after_the_mode(cards):
    s = build(cards, "Knight of Autumn", "Sol Ring")
    respond_on(s)
    ring = battlefield(s, "Sol Ring", "p2")  # (an artifact Bob controls)
    cast(s, "Knight of Autumn", G=1, W=1, C=1)
    pass_until_stack_empty(s)
    assert offered(s) == ["0:0", "1:0", "2:0"]
    choose(s, "1:0")  # Destroy target artifact or enchantment.
    assert step(s) == "trigger_slot_target" and ring.id in offered(s)
    choose(s, ring.id)
    entry = next(iter(rules(s).stack.values()))
    assert entry.modes == [1] and [t.id for t in entry.targets] == [ring.id] and entry.slot_specs[0]["what"]
    pass_until_stack_empty(s)
    assert s.state.cards[ring.id].zone == "p1:graveyard"  # (Alice owns it: it goes to its owner's graveyard)
    replay_matches(s)


# -- a modal "Whenever …" trigger (603.3c) ---------------------------------------------------------------------
def test_modal_landfall_trigger_chooses_a_mode_each_time(cards):
    """Felidar Retreat: Landfall — Whenever a land you control enters, choose one —"""
    s = build(cards, "Felidar Retreat")
    respond_on(s)
    battlefield(s, "Felidar Retreat")
    bear = token(s, "p1", "Bear", "2/2")
    land = to_hand(s, "Forest")
    act(s, "p1", type="play_land", card_id=land.id)
    assert step(s) == "trigger_modes" and offered(s) == ["0:0", "1:0"]
    assert rules(s).decision.prompt.startswith("Felidar Retreat: choose one mode")
    choose(s, "1:0")  # a +1/+1 counter on each creature you control, vigilance
    assert stack_modes(s)[0][0].startswith("Put a +1/+1 counter on each creature you control")
    pass_until_stack_empty(s)
    assert s.state.cards[bear.id].counters == {"+1/+1": 1}
    replay_matches(s)


# -- a modal activated ability: announced before targets and costs (602.2b → 601.2b-c) --------------------------
def test_modal_activated_ability_announces_modes_and_targets_before_paying(cards):
    """Cankerbloom: {1}, Sacrifice this creature: Choose one — artifact / enchantment / proliferate."""
    s = build(cards, "Cankerbloom", "Sol Ring")
    respond_on(s)
    bloom = battlefield(s, "Cankerbloom")
    ring = battlefield(s, "Sol Ring")
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=bloom.id, ability=0)
    assert step(s) == "cast_modes" and offered(s) == ["0:0", "2:0"]  # (no enchantment to destroy: mode 1 can't be chosen)
    assert s.state.cards[bloom.id].zone == "p1:battlefield" and s.state.players["p1"].mana == {"C": 1}  # nothing paid yet
    choose(s, "0:0")
    assert step(s) == "cast_slot_target" and ring.id in offered(s)
    assert s.state.cards[bloom.id].zone == "p1:battlefield" and s.state.players["p1"].mana == {"C": 1}
    choose(s, ring.id)
    assert rules(s).decision is None
    assert s.state.cards[bloom.id].zone == "p1:graveyard" and s.state.players["p1"].mana == {}  # now the costs are paid
    assert stack_modes(s) == [["Destroy target artifact."]]
    entry = next(iter(rules(s).stack.values()))
    assert entry.kind == "activated" and entry.modes == [0] and [t.id for t in entry.targets] == [ring.id]
    pass_until_stack_empty(s)
    assert s.state.cards[ring.id].zone == "p1:graveyard"
    replay_matches(s)


def test_modal_activated_ability_with_the_modes_given_up_front(cards):
    s = build(cards, "Cankerbloom", "Sol Ring")
    bloom = battlefield(s, "Cankerbloom")
    ring = battlefield(s, "Sol Ring")
    mana(s, C=1)
    with pytest.raises(ActionError, match="no legal target"):
        act(s, "p1", type="activate_ability", card_id=bloom.id, ability=0, modes=[1])  # no enchantment
    with pytest.raises(ActionError, match="Choose 1"):
        act(s, "p1", type="activate_ability", card_id=bloom.id, ability=0, modes=[0, 2], targets=[ring.id])
    act(s, "p1", type="activate_ability", card_id=bloom.id, ability=0, modes=[0], targets=[ring.id])
    pass_until_stack_empty(s)
    assert s.state.cards[ring.id].zone == "p1:graveyard" and s.state.cards[bloom.id].zone == "p1:graveyard"
    replay_matches(s)


def test_a_modal_ability_with_no_mode_to_choose_cant_be_activated(cards):
    """Phoenix Down: both modes need a target. With none legal no mode can be chosen (700.2a), so the
    activation is illegal (602.2) and nothing is paid; with a creature card in the graveyard it can be."""
    s = build(cards, "Phoenix Down", "Llanowar Elves")
    down = battlefield(s, "Phoenix Down")
    mana(s, W=1, C=1)
    with pytest.raises(ActionError, match="no mode you can choose"):
        act(s, "p1", type="activate_ability", card_id=down.id, ability=0)
    assert s.state.cards[down.id].zone == "p1:battlefield" and s.state.players["p1"].mana == {"W": 1, "C": 1}
    elves = named(s, "Llanowar Elves")
    act(s, "p1", type="move", card_ids=[elves.id], to={"zone": "graveyard"})
    act(s, "p1", type="activate_ability", card_id=down.id, ability=0)
    assert offered(s) == ["0:0"]  # (the Skeleton, Spirit or Zombie mode still has no target)
    choose(s, "0:0")
    choose(s, elves.id)
    assert s.state.cards[down.id].zone == "p1:exile"  # "Exile this artifact" was the cost
    pass_until_stack_empty(s)
    assert s.state.cards[elves.id].zone == "p1:battlefield" and s.state.cards[elves.id].tapped
    replay_matches(s)


# -- no mode can be chosen: the ability is removed from the stack (603.3c, 700.2b) ---------------------------
def test_a_triggered_ability_with_no_legal_mode_is_removed(cards):
    """Sawblade Slinger: choose up to one — destroy target artifact an opponent controls / fights target Zombie
    an opponent controls. With neither target available no mode can be chosen: it never goes on the stack."""
    s = build(cards, "Sawblade Slinger")
    respond_on(s)
    cast(s, "Sawblade Slinger", G=1, C=3)
    pass_until_stack_empty(s)
    assert rules(s).decision is None and s.state.zones.get("stack", []) == [] and rules(s).pending_triggers == []
    assert "has no mode that can be chosen and is removed" in log_text(s)
    assert s.state.cards[named(s, "Sawblade Slinger").id].zone == "p1:battlefield"
    replay_matches(s)


def test_choosing_no_mode_of_an_up_to_one_ability_removes_it(cards):
    """700.2b: "If no mode is chosen, the ability is removed from the stack." (Choosing none is allowed: 0 to 1.)"""
    s = build(cards, "Sawblade Slinger", "Sol Ring")
    respond_on(s)
    ring = battlefield(s, "Sol Ring", "p2")
    cast(s, "Sawblade Slinger", G=1, C=3)
    pass_until_stack_empty(s)
    d = rules(s).decision
    assert step(s) == "trigger_modes" and (d.min_choices, d.max_choices) == (0, 1) and offered(s) == ["0:0"]
    assert d.prompt == "Sawblade Slinger: choose up to one mode"
    choose(s)  # (none)
    assert rules(s).decision is None and s.state.zones.get("stack", []) == []
    assert "has no mode chosen and is removed" in log_text(s)
    assert s.state.cards[ring.id].zone == "p2:battlefield"
    replay_matches(s)


def test_an_up_to_one_ability_can_still_take_its_mode(cards):
    s = build(cards, "Sawblade Slinger", "Sol Ring")
    respond_on(s)
    ring = battlefield(s, "Sol Ring", "p2")
    cast(s, "Sawblade Slinger", G=1, C=3)
    pass_until_stack_empty(s)
    choose(s, "0:0")
    choose(s, ring.id)
    pass_until_stack_empty(s)
    assert s.state.cards[ring.id].zone == "p1:graveyard"
    replay_matches(s)


def test_choose_two_takes_exactly_two_modes(cards):
    """Craftwork Crusher: choose two — 4 damage to target creature or planeswalker / a 2/2 Cadet / draw."""
    s = build(cards, "Craftwork Crusher")
    respond_on(s)
    cast(s, "Craftwork Crusher", R=2, G=2, C=3)
    pass_until_stack_empty(s)
    d = rules(s).decision
    assert step(s) == "trigger_modes" and (d.min_choices, d.max_choices) == (2, 2)
    assert offered(s) == ["0:0", "1:0", "2:0"]  # (the Crusher itself is a legal target for the damage)
    assert d.prompt == "Craftwork Crusher: choose two modes"
    with pytest.raises(ActionError, match="Choose 2"):
        choose(s, "1:0")
    choose(s, "2:0", "1:0")  # (draw, Cadet: in any order)
    assert stack_modes(s) == [["Create a 2/2 colorless Wizard Soldier creature token named Cadet.", "Draw a card."]]
    hand = len(zone(s.state, "p1", "hand"))
    pass_until_stack_empty(s)
    assert len(zone(s.state, "p1", "hand")) == hand + 1 and named(s, "Cadet").zone == "p1:battlefield"
    replay_matches(s)


def test_fewer_legal_modes_than_the_instruction_needs_removes_the_ability(cards):
    """603.3d / 700.2b: "choose two" with one mode that can be chosen: no legal choice can be made, so the
    ability is removed from the stack. (Craftwork Crusher's header over Cankerbloom's targeted modes.)"""
    s = build(cards, "Test Two-Mode Golem")
    respond_on(s)
    cast(s, "Test Two-Mode Golem", C=1)
    pass_until_stack_empty(s)
    assert rules(s).decision is None and s.state.zones.get("stack", []) == []
    assert "has no mode that can be chosen and is removed" in log_text(s)
    replay_matches(s)


# -- a target for each chosen mode, carried out in printed order (700.2c, 700.2d, 601.2c, 608.2c) --------------------
def test_each_chosen_mode_has_its_own_target_and_modes_run_in_printed_order(cards):
    """Flash Thompson: choose one or both — Heckle (tap target creature) / Hero Worship (untap target creature).
    Both modes may target the same creature (601.2c: another "target"); they are carried out as printed, so
    chosen in either order the creature ends up untapped (tap, then untap)."""
    s = build(cards, "Flash Thompson, Spider-Fan")
    respond_on(s)
    bear = token(s, "p1", "Bear", "2/2")
    cast(s, "Flash Thompson, Spider-Fan", W=1, C=1)
    pass_until_stack_empty(s)
    d = rules(s).decision
    assert step(s) == "trigger_modes" and (d.min_choices, d.max_choices) == (1, 2)
    assert d.prompt == "Flash Thompson, Spider-Fan: choose one or two modes"
    choose(s, "1:0", "0:0")  # (chosen Hero Worship first)
    assert step(s) == "trigger_slot_target" and "Heckle" in rules(s).decision.prompt  # (targets follow the printed order)
    choose(s, bear.id)
    assert step(s) == "trigger_slot_target" and "Hero Worship" in rules(s).decision.prompt
    choose(s, bear.id)  # the same creature for the second mode
    entry = next(iter(rules(s).stack.values()))
    assert entry.modes == [0, 1] and [[t.id for t in slot] for slot in entry.slots] == [[bear.id], [bear.id]]
    assert [list(m) for m in stack_modes(s)] == [["Heckle — Tap target creature.", "Hero Worship — Untap target creature."]]
    pass_until_stack_empty(s)
    assert not s.state.cards[bear.id].tapped  # tap first, then untap
    replay_matches(s)


def test_one_of_two_modes_can_be_chosen_alone(cards):
    s = build(cards, "Flash Thompson, Spider-Fan")
    respond_on(s)
    bear = token(s, "p1", "Bear", "2/2")
    cast(s, "Flash Thompson, Spider-Fan", W=1, C=1)
    pass_until_stack_empty(s)
    choose(s, "0:0")
    choose(s, bear.id)
    pass_until_stack_empty(s)
    assert s.state.cards[bear.id].tapped
    replay_matches(s)


def test_a_dies_trigger_offers_a_targeted_mode_only_with_a_legal_target(cards):
    """Shambling Ghast (dies): -1/-1 on target creature an opponent controls / a Treasure. Bob has no creature
    at first, so only the Treasure mode is offered; with one, both are."""
    s = build(cards, "Shambling Ghast")
    respond_on(s)
    ghast = battlefield(s, "Shambling Ghast")
    quake = token(s, "p1", "Quake", "5/5", text="{1}: This creature deals 1 damage to each creature.")
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=quake.id, ability=0)
    pass_until_stack_empty(s)
    assert s.state.cards[ghast.id].zone == "p1:graveyard"
    assert step(s) == "trigger_modes" and offered(s) == ["1:0"]  # (it died: no target for the first mode)
    choose(s, "1:0")
    pass_until_stack_empty(s)
    assert named(s, "Treasure").zone == "p1:battlefield"
    replay_matches(s)


def test_a_dies_trigger_with_a_target_mode(cards):
    s = build(cards, "Shambling Ghast")
    respond_on(s)
    ghast = battlefield(s, "Shambling Ghast")
    ogre = token(s, "p2", "Ogre", "3/3")
    quake = token(s, "p1", "Quake", "5/5", text="{1}: This creature deals 1 damage to each creature.")
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=quake.id, ability=0)
    pass_until_stack_empty(s)
    assert offered(s) == ["0:0", "1:0"]
    choose(s, "0:0")
    assert step(s) == "trigger_slot_target" and offered(s) == [ogre.id]
    choose(s, ogre.id)
    pass_until_stack_empty(s)
    assert s.state.cards[ogre.id].damage == 1  # (1 from the Quake, then -1/-1 makes it a 2/2 with 1 damage)
    assert ghast.id in s.state.cards
    replay_matches(s)


# -- the choices survive a save and a reload --------------------------------------------------------------------
def test_a_pending_mode_choice_survives_a_reload(cards):
    s = build(cards, "Flash Thompson, Spider-Fan")
    respond_on(s)
    bear = token(s, "p1", "Bear", "2/2")
    cast(s, "Flash Thompson, Spider-Fan", W=1, C=1)
    pass_until_stack_empty(s)
    assert step(s) == "trigger_modes"
    s = reloaded(s)  # save and load while the modes are still to be chosen
    assert step(s) == "trigger_modes" and len(rules(s).pending_triggers) == 1
    choose(s, "0:0", "1:0")
    assert step(s) == "trigger_slot_target"
    s = reloaded(s)  # … and between one mode's target and the next
    choose(s, bear.id)
    s = reloaded(s)
    choose(s, bear.id)
    pass_until_stack_empty(s)
    assert not s.state.cards[bear.id].tapped and rules(s).pending_triggers == []
    replay_matches(s)


# -- "choose one that hasn't been chosen": per object, for the game (400.7) -----------------------------------------
def untap(s, card, pid="p1"):
    act(s, pid, type="tap", card_ids=[card.id], tapped=False)


def activate_bowls(s, bowls, pid="p1"):
    act(s, pid, type="add_mana", player=pid, mana={"C": 2})
    act(s, pid, type="activate_ability", card_id=bowls.id, ability=0)


def test_unchosen_modes_are_remembered_per_object_across_reloads_and_control_changes(cards):
    """Three Bowls of Porridge ({2}, {T}: Choose one that hasn't been chosen —). The rulings (Demonic Pact): a
    mode counts once announced, it doesn't matter who chose it (a new controller can't choose it again);
    a card that left and came back is a new object with no memory (Silent Hallcreeper, 400.7)."""
    s = build(cards, "Three Bowls of Porridge")
    respond_on(s)
    bowls = battlefield(s, "Three Bowls of Porridge")
    ogre = token(s, "p2", "Ogre", "5/5")
    activate_bowls(s, bowls)
    assert step(s) == "cast_modes" and offered(s) == ["0:0", "1:0", "2:0"]
    choose(s, "1:0")  # Tap target creature.
    choose(s, ogre.id)
    oid = rules(s).object_id(bowls.id)
    assert rules(s).modes_chosen == {f"{oid}:0:game": [1]}
    assert stack_modes(s) == [["Tap target creature."]]
    pass_until_stack_empty(s)
    assert s.state.cards[ogre.id].tapped
    s = reloaded(s)  # a save and a load: the memory is part of the game
    assert rules(s).modes_chosen == {f"{oid}:0:game": [1]}
    untap(s, bowls)
    activate_bowls(s, bowls)
    assert offered(s) == ["0:0", "2:0"]  # (mode 1 was chosen: it isn't offered again)
    with pytest.raises(ActionError):
        act(s, "p1", type="choose", decision_id=rules(s).decision.id, option_ids=["1:0"])
    choose(s, "0:0")  # 2 damage to target creature
    choose(s, ogre.id)
    assert rules(s).modes_chosen == {f"{oid}:0:game": [0, 1]}
    pass_until_stack_empty(s)
    assert s.state.cards[ogre.id].damage == 2
    # a new controller: the memory is the object's, not the player's
    untap(s, bowls)
    act(s, "p1", type="set_controller", card_ids=[bowls.id], player="p2")
    pinger = token(s, "p1", "Pinger", "1/1", text="{1}: You gain 1 life.")
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=pinger.id, ability=0)  # (Bob gets priority, with it on the stack)
    assert rules(s).priority == "p2"
    activate_bowls(s, bowls, "p2")
    assert offered(s) == ["2:0"]  # (only "Sacrifice this artifact. You gain 3 life." is left)
    choose(s, "2:0")
    pass_until_stack_empty(s)
    assert s.state.players["p2"].life == 43 and s.state.cards[bowls.id].zone == "p1:graveyard"
    replay_matches(s)


def test_a_new_object_has_no_memory_of_the_modes(cards):
    s = build(cards, "Three Bowls of Porridge")
    respond_on(s)
    bowls = battlefield(s, "Three Bowls of Porridge")
    ogre = token(s, "p2", "Ogre", "5/5")
    activate_bowls(s, bowls)
    choose(s, "1:0")
    choose(s, ogre.id)
    pass_until_stack_empty(s)
    old = rules(s).object_id(bowls.id)
    assert old in next(iter(rules(s).modes_chosen))
    act(s, "p1", type="move", card_ids=[bowls.id], to={"zone": "hand"})  # it leaves the battlefield …
    battlefield(s, "Three Bowls of Porridge")  # … and returns: a new object (400.7)
    assert rules(s).object_id(bowls.id) != old
    activate_bowls(s, bowls)
    assert offered(s) == ["0:0", "1:0", "2:0"]  # (nothing is remembered: "Tap target creature." is offered again)
    choose(s, "1:0")
    choose(s, ogre.id)
    new = rules(s).object_id(bowls.id)
    assert rules(s).modes_chosen[f"{new}:0:game"] == [1]  # (its own memory: the old object's [1] doesn't count)
    pass_until_stack_empty(s)
    replay_matches(s)


def test_a_mode_already_chosen_is_refused_when_given_up_front(cards):
    s = build(cards, "Three Bowls of Porridge")
    bowls = battlefield(s, "Three Bowls of Porridge")
    ogre = token(s, "p2", "Ogre", "5/5")
    activate_bowls(s, bowls)
    choose(s, "1:0")
    choose(s, ogre.id)
    pass_until_stack_empty(s)
    untap(s, bowls)
    mana(s, C=2)
    with pytest.raises(ActionError, match="already been chosen"):
        act(s, "p1", type="activate_ability", card_id=bowls.id, ability=0, modes=[1], targets=[ogre.id])
    assert not s.state.cards[bowls.id].tapped and s.state.players["p1"].mana == {"C": 2}  # (nothing was paid)
    act(s, "p1", type="activate_ability", card_id=bowls.id, ability=0, modes=[0], targets=[ogre.id])
    pass_until_stack_empty(s)
    assert s.state.cards[ogre.id].damage == 2
    replay_matches(s)


# -- "that hasn't been chosen this turn": per object, per turn -------------------------------------------------
def test_unchosen_this_turn_starts_over_each_turn(cards):
    """Kargan Intimidator ({1}: Choose one that hasn't been chosen this turn —): three activations use the three
    modes; a fourth has no mode to choose; next turn all three are back."""
    s = build(cards, "Kargan Intimidator")
    respond_on(s)
    kargan = battlefield(s, "Kargan Intimidator")
    ogre = token(s, "p2", "Ogre", "5/5")
    for mode, target in (("0:0", None), ("2:0", kargan.id), ("1:0", ogre.id)):
        mana(s, C=1)
        act(s, "p1", type="activate_ability", card_id=kargan.id, ability=1)
        choose(s, mode)
        if target:
            choose(s, target)
        pass_until_stack_empty(s)
    turn = s.state.turn.number
    oid = rules(s).object_id(kargan.id)
    assert rules(s).modes_chosen == {f"{oid}:1:t{turn}": [0, 1, 2]}
    mana(s, C=1)
    with pytest.raises(ActionError, match="no mode you can choose"):
        act(s, "p1", type="activate_ability", card_id=kargan.id, ability=1)
    assert s.state.players["p1"].mana == {"C": 1}  # (nothing was paid)
    assert s.state.cards[ogre.id].zone == "p2:battlefield"  # (the Ogre is a Coward now)
    # the next turn: the memory of the old turn is gone
    for _ in range(40):
        if s.state.turn.number > turn and rules(s).priority == "p1" and rules(s).decision is None:
            break
        d = rules(s).decision
        if d is not None and d.kind in ("declare_attackers", "declare_blockers"):
            act(s, d.player, type=d.kind, **({"attackers": []} if d.kind == "declare_attackers" else {"blocks": []}))
        else:
            act(s, rules(s).priority, type="pass_priority")
    assert s.state.turn.number == turn + 1
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=kargan.id, ability=1)
    assert offered(s) == ["0:0", "1:0", "2:0"]
    replay_matches(s)


def test_every_instance_that_triggers_together_takes_a_different_mode(cards):
    """Monument to Endurance (Whenever you discard a card, choose one that hasn't been chosen this turn —). Two
    cards discarded at once are two instances: each announces its mode as it is put on the stack, so the second
    can't take the first's. The fourth discard of the turn has no mode left: that instance is removed from the
    stack with no effect (ruling, 2025-02-07). A mode counts once announced."""
    s = build(cards, "Monument to Endurance")
    respond_on(s)
    battlefield(s, "Monument to Endurance")
    act(s, "p1", type="draw", count=5)
    looter = token(s, "p1", "Looter", "1/1", text="{1}: Discard two cards.")
    mana(s, C=2)
    act(s, "p1", type="activate_ability", card_id=looter.id, ability=0)
    pass_until_stack_empty(s)
    assert rules(s).decision.kind == "choose_cards" and (rules(s).decision.min_choices, rules(s).decision.max_choices) == (2, 2)
    choose(s, *offered(s)[:2])  # the two cards to discard
    assert step(s) == "trigger_modes" and offered(s) == ["0:0", "1:0", "2:0"]
    choose(s, "1:0")  # the first instance: a Treasure
    assert step(s) == "trigger_modes" and offered(s) == ["0:0", "2:0"]  # (the second can't take it)
    choose(s, "0:0")  # the second: draw
    assert stack_modes(s) == [["Draw a card."], ["Create a Treasure token."]]
    oid = rules(s).object_id(named(s, "Monument to Endurance").id)
    turn = s.state.turn.number
    assert rules(s).modes_chosen == {f"{oid}:0:t{turn}": [0, 1]}
    pass_until_stack_empty(s)
    assert len([c for c in s.state.cards.values() if c.name == "Treasure"]) == 1
    # two more discards: one mode is left for the third, none for the fourth
    act(s, "p1", type="activate_ability", card_id=looter.id, ability=0)
    pass_until_stack_empty(s)
    choose(s, *offered(s)[:2])
    assert step(s) == "trigger_modes" and offered(s) == ["2:0"]  # (only "Each opponent loses 3 life." is left)
    choose(s, "2:0")
    assert rules(s).decision is None and len(rules(s).stack) == 1  # (the fourth instance never went on the stack)
    assert "has no mode that can be chosen and is removed" in log_text(s)
    pass_until_stack_empty(s)
    assert s.state.players["p2"].life == 37
    replay_matches(s)


# -- APNAP: two players' modal triggers (603.3b) -----------------------------------------------------------------
def test_two_players_modal_triggers_are_announced_in_apnap_order(cards):
    """A trigger each from Alice (active) and Bob, on one event. Alice puts hers on the stack first, announcing her
    mode; then Bob announces his; Bob's ability is on top and resolves first. (Wording of Vision, Synthezoid
    Avenger's header without its intervening "if".)"""
    s = build(cards, "Lightning Bolt")
    respond_on(s)
    text = "Whenever a player casts a spell, choose one —\n• You gain 2 life.\n• Draw a card."
    token(s, "p1", "Alice's Seer", "1/1", text=text)
    token(s, "p2", "Bob's Seer", "1/1", text=text)
    bolt = to_hand(s, "Lightning Bolt")
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])
    d = rules(s).decision
    assert d.player == "p1" and d.resume["step"] == "trigger_modes" and d.prompt.startswith("Alice's Seer")
    assert rules(s).decision.resume["trigger"] in {t.id for t in rules(s).pending_triggers}
    # (Bob sees only that somebody is choosing)
    assert s.view("p2")["rules"]["decision"]["public"] == {"type": "PLAYER_MAKING_CHOICE", "chooser": "Alice"}
    choose(s, "0:0")  # Alice: gain 2 life
    d = rules(s).decision
    assert d.player == "p2" and d.prompt.startswith("Bob's Seer") and offered(s) == ["0:0", "1:0"]
    assert on_stack(s) == ["Lightning Bolt", "Alice's Seer"]  # (hers is already on the stack, Bob's isn't yet)
    choose(s, "1:0")  # Bob: draw a card
    assert on_stack(s) == ["Lightning Bolt", "Alice's Seer", "Bob's Seer"]  # (bottom to top: Bob's resolves first)
    assert stack_modes(s)[:2] == [["Draw a card."], ["You gain 2 life."]]
    life = s.state.players["p1"].life
    pass_until_stack_empty(s)
    assert s.state.players["p1"].life == life + 2 and s.state.players["p2"].life == 40 - 3  # (Bob: the Bolt)
    replay_matches(s)


# -- loyalty abilities (606.2 → 602.2b) -------------------------------------------------------------------------
WALKER = ("+1: Choose one —\n• You gain 2 life.\n• Draw a card.\n"
          "−2: Choose one —\n• Target creature gets -2/-2 until end of turn.\n• You gain 3 life.")


def walker(s, loyalty=3):
    """(Not a real card: no Commander-legal planeswalker has a modal loyalty ability today.)"""
    act(s, "p1", type="create_token", player="p1", token={
        "name": "Modal Walker", "type_line": "Token Legendary Planeswalker — Test", "text": WALKER})
    w = named(s, "Modal Walker")
    act(s, "p1", type="counter", card_ids=[w.id], kind="loyalty", delta=loyalty)
    return w


def test_a_modal_loyalty_ability_announces_modes_before_its_loyalty_cost(cards):
    s = build(cards)
    respond_on(s)
    w = walker(s)
    life = s.state.players["p1"].life
    act(s, "p1", type="activate_ability", card_id=w.id, ability=0)
    assert step(s) == "cast_modes" and offered(s) == ["0:0", "1:0"]
    assert s.state.cards[w.id].counters["loyalty"] == 3 and rules(s).loyalty_used == {}  # (not paid, not used yet)
    choose(s, "0:0")
    assert s.state.cards[w.id].counters["loyalty"] == 4 and rules(s).loyalty_used[rules(s).object_id(w.id)] == s.state.turn.number
    assert stack_modes(s) == [["You gain 2 life."]]
    pass_until_stack_empty(s)
    assert s.state.players["p1"].life == life + 2
    with pytest.raises(ActionError, match="already used a loyalty ability"):  # (606.3: once per turn)
        act(s, "p1", type="activate_ability", card_id=w.id, ability=3)
    replay_matches(s)


def test_a_modal_loyalty_ability_offers_a_targeted_mode_only_with_a_target(cards):
    s = build(cards)
    respond_on(s)
    w = walker(s)
    act(s, "p1", type="activate_ability", card_id=w.id, ability=3)  # −2
    assert offered(s) == ["1:0"]  # (no creature to give −2/−2: that mode can't be chosen)
    choose(s, "1:0")
    assert s.state.cards[w.id].counters["loyalty"] == 1
    pass_until_stack_empty(s)
    assert s.state.players["p1"].life == 43
    replay_matches(s)


def test_a_modal_loyalty_ability_with_a_targeted_mode(cards):
    s = build(cards)
    respond_on(s)
    w = walker(s)
    bear = token(s, "p1", "Bear", "2/2")
    act(s, "p1", type="activate_ability", card_id=w.id, ability=3)
    assert offered(s) == ["0:0", "1:0"]
    choose(s, "0:0")
    assert step(s) == "cast_slot_target" and s.state.cards[w.id].counters["loyalty"] == 3  # (the cost isn't paid yet)
    choose(s, bear.id)
    assert s.state.cards[w.id].counters["loyalty"] == 1
    pass_until_stack_empty(s)
    assert bear.id not in s.state.cards  # (2/2 with -2/-2: a token that died ceases to exist)
    replay_matches(s)


# -- the wording: what is read, what is refused ------------------------------------------------------------------
def header(text, type_line="Creature"):
    found = {i: d for i, d in scripts.definitions(characteristics("Thing", type_line, text)).items() if d["kind"] != "mode"}
    return next(iter(found.values())) if found else None


@pytest.mark.parametrize(("text", "lo", "hi", "memory"), [
    # the headers of real cards (Commander-legal), over two or three plain modes
    ("When this creature enters, choose one —\n• Draw a card.\n• You gain 1 life.", 1, 1, None),  # Knight of Autumn
    ("When this creature enters, choose two —\n• Draw a card.\n• You gain 1 life.\n• Scry 1.", 2, 2, None),  # Craftwork Crusher
    ("When this creature enters, choose one or both —\n• Draw a card.\n• You gain 1 life.", 1, 2, None),  # Flash Thompson
    ("At the beginning of your first main phase, choose one or more —\n• Draw a card.\n• You gain 1 life.\n• Scry 1.", 1, 3, None),  # Black Market Connections
    ("Whenever this creature deals combat damage to a player, choose any number —\n• Draw a card.\n• You gain 1 life.", 0, 2, None),  # Rankle
    ("When this creature enters, choose up to one —\n• Draw a card.\n• You gain 1 life.", 0, 1, None),  # Sawblade Slinger
    ("When this creature enters, choose three —\n• Draw a card.\n• You gain 1 life.\n• Scry 1.\n• Surveil 1.", 3, 3, None),  # Mishra, Lost to Phyrexia
    ("At the beginning of your upkeep, choose one that hasn't been chosen —\n• Draw a card.\n• You gain 1 life.", 1, 1, "game"),  # Demonic Pact
    ("Whenever you discard a card, choose one that hasn't been chosen this turn —\n• Draw a card.\n• You gain 1 life.", 1, 1, "turn"),  # Monument to Endurance
    ("{1}: Choose one that hasn't been chosen this turn —\n• Draw a card.\n• You gain 1 life.", 1, 1, "turn"),  # Kargan Intimidator
    ("{T}: Choose one —\n• Draw a card.\n• You gain 1 life.", 1, 1, None),  # (an activated ability)
])
def test_headers_read(text, lo, hi, memory):
    d = header(text)
    assert d is not None and d["modes"] and d["effects"] == [] and d["target"] is None and d["optional"] is False
    assert (d["modal"]["min"], d["modal"]["max"], d["modal"]["memory"]) == (lo, hi, memory)
    assert d["kind"] == ("activated" if text.startswith(("{", "+")) else "triggered")
    assert coverage.definition_supported(d)


def test_the_lines_of_the_modes_belong_to_the_ability():
    c = characteristics("Thing", "Creature", "When this creature enters, choose one —\n• Draw a card.\n• You gain 1 life.\nFlying")
    defs = scripts.definitions(c)
    assert defs[0]["modes"] and defs[1] == defs[2] | {} and defs[1]["kind"] == "mode" and defs[1]["of"] == 0
    assert 3 not in defs  # (the next line, "Flying", is a keyword: not part of it)
    assert all(coverage.ability_supported(c, i) for i in (0, 1, 2))
    feats = {f.id: f.supported for f in coverage.features_of(c)}
    assert feats["text:0"] and feats["text:1"] and feats["text:2"] and feats["keyword:flying"]


@pytest.mark.parametrize("text", [
    # (each real: what the grammar refuses, and why — nothing here is guessed)
    "Whenever this creature attacks, choose one at random —\n• Draw a card.\n• You gain 1 life.",  # Cult of Skaro, Umaro: random
    "When this creature dies, choose one or more. Each mode must target a different player.\n• Target player loses 1 life.\n"
    "• Target player gains 1 life.",  # Vindictive Lich: a different player per mode
    "Whenever you attack, you may sacrifice another creature. When you do, choose two —\n• Draw a card.\n• You gain 1 life.",  # Caesar (603.12)
    "At the beginning of combat on your turn, you may pay {E}{E}. When you do, choose one —\n• Draw a card.\n• You gain 1 life.",  # Voltstorm Angel
    "When this creature enters, choose one. If you have exactly 13 life, you may choose both instead.\n• Draw a card.\n"
    "• You gain 1 life.",  # Disciple of Perdition: "choose both instead"
    "At the beginning of combat on your turn, choose one. If you control a commander, you may choose both instead.\n"
    "• Draw a card.\n• You gain 1 life.",  # SOLDIER Military Program
    "{T}: Choose one. X is the number of spells you've cast this turn.\n• Draw a card.\n• You gain 1 life.",  # Gnostro
    "When this creature enters, choose up to X, where X is the number of Lesson cards in your graveyard —\n• Draw a card.\n"
    "• You gain 1 life.",  # Bumi, King of Three Trials
    "At the beginning of your first main phase, choose one that hasn't been chosen and you lose 2 life —\n• Draw a card.\n"
    "• You gain 1 life.",  # Zuko, Conflicted
    "Whenever another nontoken permanent you control leaves the battlefield, choose one that hasn't been chosen this turn. "
    "Create a creature token with those characteristics.\n• Draw a card.\n• You gain 1 life.",  # Genku, Future Shaper
    "When this creature enters, choose one —\n• You may draw a card.\n• You gain 1 life.",  # (a mode with "you may")
    "When this creature enters, choose one —\n• Put a +1/+1 counter on each of up to two target creatures.\n• You gain 1 life.",  # Daily Bugle Reporters: a target group
    "When this creature enters, choose one —\n• Destroy up to one target artifact.\n• You gain 1 life.",  # (an "up to" target)
    "When this creature enters, choose one —\n• If you control a Forest, draw a card.\n• You gain 1 life.",  # (would read as a trigger condition)
    "When this creature enters, choose one —\n• Draw a card.\n• You gain 1 life.\nThis ability triggers only once each turn.",  # (a limit that'd go unenforced)
    "{T}: Choose one —\n• Draw a card.\n• You gain 1 life.\nActivate only as a sorcery.",  # (a restriction that'd go unenforced)
    "{T}: Choose up to one —\n• Draw a card.\n• You gain 1 life.",  # (an activation choosing no mode: not modelled)
    "When this creature enters, choose one —\n• Draw a card.",  # (700.2: two or more options)
    "When this creature enters, choose two —\n• Draw a card.",  # (more to choose than there are modes)
    "When this creature enters, choose one or both —\n• Draw a card.\n• You gain 1 life.\n• Scry 1.",  # (both of three?)
    "When this creature enters, choose one —\n• Draw a card.\n• Frobnicate the widget.",  # (a mode the grammar doesn't read)
])
def test_refused_wordings_stay_manual(text):
    c = characteristics("Thing", "Creature", text)
    assert not any(d.get("modes") for d in scripts.definitions(c).values())
    assert coverage.of_characteristics(c).level == "PARTIAL"


def test_a_triggers_intervening_if_belongs_to_the_whole_ability():
    """603.4: "…, if you control a Forest, choose one —": checked as it triggers (and again as it resolves)."""
    d = header("Whenever this creature attacks, if you control a Forest, choose one —\n• Draw a card.\n• You gain 1 life.")
    assert d["if"] == {"value": {"count": 'sel:{"controller":"you","subtypes":["Forest"]}'}, "op": ">=", "n": 1}
    assert d["trigger"] == "attacks_self" and [m["effects"][0]["do"] for m in d["modes"]] == ["draw", "gain_life"]
    # the same text when the "if" is unreadable: manual, not guessed
    assert header("Whenever this creature attacks, if a creature died this turn, choose one —\n• Draw a card.\n• You gain 1 life.") is None


def test_modes_that_name_the_event_keep_their_references():
    d = header("Whenever this creature deals combat damage to a player, choose one —\n• That player discards a card.\n• You gain 1 life.")
    assert d["modes"][0]["effects"][0]["who"] == "event_player" and d["modes"][1]["effects"][0]["do"] == "gain_life"
    # ("that player" needs an event about a player: refused after a trigger that has none)
    assert header("When this creature enters, choose one —\n• That player discards a card.\n• You gain 1 life.") is None


def test_mode_names_are_labels_not_rules_text():
    """Flash Thompson, Kimoyo Beads: "• Heckle — Tap target creature." reads as "Tap target creature."; the text
    kept for the players is the printed line."""
    d = header("When this creature enters, choose one or both —\n• Heckle — Tap target creature.\n• Hero Worship — Untap target creature.")
    assert [m["text"] for m in d["modes"]] == ["Heckle — Tap target creature.", "Hero Worship — Untap target creature."]
    assert [m["effects"][0]["do"] for m in d["modes"]] == ["tap", "untap"]


def test_real_cards_are_fully_automated(cards):
    for name in ("Knight of Autumn", "Felidar Retreat", "Cankerbloom", "Flash Thompson, Spider-Fan", "Shambling Ghast",
                 "Three Bowls of Porridge", "Kargan Intimidator", "Sawblade Slinger", "Craftwork Crusher", "Phoenix Down",
                 "Monument to Endurance", "Kimoyo Beads"):
        data = cards.get(cards.resolve(name)["id"])
        assert coverage.of_characteristics(printed_from_data(data)).level == "FULL", name


# -- end of tests --

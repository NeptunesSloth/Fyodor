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
    card("Black Market Connections", set_code="tst", number="M13", mana_cost="{2}{B}", cmc=3.0, type_line="Enchantment",
         oracle_text="At the beginning of your first main phase, choose one or more —\n• Sell Contraband — Create a Treasure "
                     "token. You lose 1 life.\n• Buy Information — Draw a card. You lose 2 life.\n• Hire a Mercenary — Create a "
                     "3/2 colorless Shapeshifter creature token with changeling. You lose 3 life. (It is every creature type.)",
         colors=["B"], color_identity=["B"]),
    card("Skinshifter", set_code="tst", number="M14", mana_cost="{1}{G}", cmc=2.0, type_line="Creature — Human Shaman",
         oracle_text="{G}: Choose one. Activate only once each turn.\n• Until end of turn, this creature becomes a Rhino with "
                     "base power and toughness 4/4 and gains trample.\n• Until end of turn, this creature becomes a Bird with "
                     "base power and toughness 2/2 and gains flying.\n• Until end of turn, this creature becomes a Plant with "
                     "base power and toughness 0/8.", power="1", toughness="1", colors=["G"], color_identity=["G"]),
    # (not a real card: a transform card with a "hasn't been chosen" ability on each face)
    card("Test Shifting Idol // Test Shifted Idol", set_code="tst", number="X2", layout="transform", mana_cost="{1}", cmc=1.0,
         type_line="Artifact // Artifact", image_uris=None,
         card_faces=[
             {"object": "card_face", "name": "Test Shifting Idol", "mana_cost": "{1}", "type_line": "Artifact",
              "oracle_text": "{1}: Choose one that hasn't been chosen —\n• You gain 1 life.\n• Draw a card."},
             {"object": "card_face", "name": "Test Shifted Idol", "mana_cost": "", "type_line": "Artifact",
              "oracle_text": "{1}: Choose one that hasn't been chosen —\n• Scry 1.\n• You gain 2 life."},
         ]),
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
    Both modes may target the same creature (601.2c: another "target"); they are carried out as printed (608.2c;
    ruling 2025-09-19: "if you choose the same target for both modes, it will be tapped before it is untapped"),
    so chosen in either order the creature ends up untapped."""
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


def test_a_mode_counts_even_if_the_ability_doesnt_resolve(cards):
    """Demonic Pact ruling: "If the ability doesn't resolve (either for having its target become illegal or because
    a spell or ability counters it), the mode chosen for that instance of the ability still counts as being
    chosen." The memory is written as the ability is put on the stack, not as it resolves."""
    s = build(cards, "Three Bowls of Porridge")
    respond_on(s)
    bowls = battlefield(s, "Three Bowls of Porridge")
    ogre = token(s, "p2", "Ogre", "5/5")
    activate_bowls(s, bowls)
    choose(s, "1:0")  # Tap target creature.
    choose(s, ogre.id)  # (Alice passes after activating: Bob has priority with it on the stack)
    act(s, "p2", type="move", card_ids=[ogre.id], to={"zone": "graveyard"})  # the target is gone
    pass_until_stack_empty(s)
    assert "does nothing: its targets are no longer legal" in log_text(s)
    oid = rules(s).object_id(bowls.id)
    assert rules(s).modes_chosen == {f"{oid}:0:game": [1]}  # (chosen, though nothing happened)
    untap(s, bowls)
    goblin = token(s, "p2", "Goblin", "1/1")
    activate_bowls(s, bowls)
    assert offered(s) == ["0:0", "2:0"] and goblin.id
    replay_matches(s)


def test_the_two_faces_of_one_object_keep_separate_memory(cards):
    """A double-faced permanent is one object (712), but its faces' abilities are different abilities: what was
    chosen for the front's doesn't count for the back's (not a real card)."""
    s = build(cards, "Test Shifting Idol // Test Shifted Idol")
    respond_on(s)
    idol = battlefield(s, "Test Shifting Idol // Test Shifted Idol")
    for face, choice in ((0, "0:0"), (1, "1:0")):  # (front: gain 1 life; back: gain 2 life)
        act(s, "p1", type="set_face", card_id=idol.id, face=face)
        mana(s, C=1)
        act(s, "p1", type="activate_ability", card_id=idol.id, ability=0)
        assert offered(s) == ["0:0", "1:0"]  # (the other face's choice isn't remembered here)
        choose(s, choice)
        pass_until_stack_empty(s)
    act(s, "p1", type="set_face", card_id=idol.id, face=0)
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=idol.id, ability=0)
    assert offered(s) == ["1:0"]  # (back on the front: its own memory is still there)
    oid = rules(s).object_id(idol.id)
    assert rules(s).modes_chosen == {f"{oid}:0:game": [0], f"{oid}:0.1:game": [1]}
    replay_matches(s)


def test_modes_given_out_of_order_keep_their_targets_and_run_as_printed(cards):
    """608.2c: modes are carried out in the order printed. Given out of order (modes=[1, 0]) with their targets
    (in that order), each target stays with its mode; a modal spell does the same as an ability."""
    s = build(cards, "Test Duo")
    respond_on(s)
    ogre = token(s, "p2", "Ogre", "5/5")
    duo = to_hand(s, "Test Duo")
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=duo.id, modes=[1, 0], targets=[ogre.id, "p2"])  # 3 to the Ogre, 2 to Bob
    entry = rules(s).stack[duo.id]
    assert entry.modes == [0, 1] and [[t.id for t in slot] for slot in entry.slots] == [["p2"], [ogre.id]]
    pass_until_stack_empty(s)
    assert s.state.players["p2"].life == 38 and s.state.cards[ogre.id].damage == 3
    replay_matches(s)
    # chosen from the decision in the wrong order: the next choices follow the printed order
    s = build(cards, "Test Duo")
    respond_on(s)
    duo = to_hand(s, "Test Duo")
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=duo.id)
    choose(s, "1:0", "0:0")
    assert step(s) == "cast_slot_target" and rules(s).decision.resume["intent"]["modes"] == [0, 1]
    # an ability with two chosen modes (not a real card)
    s = build(cards)
    respond_on(s)
    two = token(s, "p1", "Twin", "1/1", text="{1}: Choose two —\n• Target creature gets +1/+1 until end of turn.\n"
                                            "• Tap target creature.\n• You gain 1 life.")
    bear = token(s, "p1", "Bear", "2/2")
    goat = token(s, "p2", "Goat", "1/1")
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=two.id, ability=0, modes=[1, 0], targets=[goat.id, bear.id])
    entry = next(iter(rules(s).stack.values()))
    assert entry.modes == [0, 1] and [[t.id for t in slot] for slot in entry.slots] == [[bear.id], [goat.id]]
    pass_until_stack_empty(s)
    assert s.state.cards[goat.id].tapped and not s.state.cards[bear.id].tapped
    with pytest.raises(ActionError, match="printed order"):
        mana(s, C=1)
        act(s, "p1", type="activate_ability", card_id=two.id, ability=0, modes=[1, 0], targets=[goat.id])
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


# -- resolution: each mode's target is checked on its own (608.2b); restrictions on the ability ------------------
def test_one_modes_target_becomes_illegal_the_other_mode_still_happens(cards):
    """Flash Thompson with both modes: if one target is gone as the ability resolves, the other mode still
    happens; if both are, the ability does nothing (608.2b)."""
    s = build(cards, "Flash Thompson, Spider-Fan")
    respond_on(s)
    ogre = token(s, "p2", "Ogre", "5/5")
    bear = token(s, "p1", "Bear", "2/2")
    act(s, "p1", type="tap", card_ids=[bear.id], tapped=True)
    cast(s, "Flash Thompson, Spider-Fan", W=1, C=1)
    pass_until_stack_empty(s)
    choose(s, "0:0", "1:0")
    choose(s, ogre.id)  # Heckle: tap the Ogre
    choose(s, bear.id)  # Hero Worship: untap the Bear
    act(s, "p1", type="pass_priority")  # (Bob may respond)
    act(s, "p2", type="move", card_ids=[ogre.id], to={"zone": "graveyard"})  # the Ogre is gone
    pass_until_stack_empty(s)
    assert not s.state.cards[bear.id].tapped  # (Hero Worship still untapped the Bear)
    replay_matches(s)


def test_the_only_target_becoming_illegal_removes_the_whole_ability(cards):
    """Craftwork Crusher, ruling 2026-08-21: "If the first mode is chosen and the target … becomes an illegal target
    before the ability resolves, then the ability will be removed from the stack and none of its other effects
    will happen." (608.2b: every target is illegal, so the ability doesn't resolve; the Cadet isn't created.)"""
    s = build(cards, "Craftwork Crusher")
    respond_on(s)
    ogre = token(s, "p2", "Ogre", "5/5")
    cast(s, "Craftwork Crusher", R=2, G=2, C=3)
    pass_until_stack_empty(s)
    choose(s, "0:0", "1:0")  # 4 damage to target creature or planeswalker; a Cadet
    choose(s, ogre.id)
    act(s, "p1", type="pass_priority")
    act(s, "p2", type="move", card_ids=[ogre.id], to={"zone": "graveyard"})
    pass_until_stack_empty(s)
    assert not [c for c in s.state.cards.values() if c.name == "Cadet"]
    assert "does nothing: its targets are no longer legal" in log_text(s)
    replay_matches(s)


def test_a_modal_abilitys_own_restriction_still_applies(cards):
    """Skinshifter: {G}: Choose one. Activate only once each turn. (602.5b: the limit is per object.)"""
    s = build(cards, "Skinshifter")
    respond_on(s)
    shifter = battlefield(s, "Skinshifter")
    mana(s, G=2)
    act(s, "p1", type="activate_ability", card_id=shifter.id, ability=0)
    assert offered(s) == ["0:0", "1:0", "2:0"]
    choose(s, "1:0")  # a Bird with base power and toughness 2/2 and flying
    pass_until_stack_empty(s)
    from tests.test_rules_attachments import ch as characteristics_of

    now = characteristics_of(s, shifter)
    assert now.pt == (2, 2) and "flying" in now.keywords and "Bird" in now.subtypes
    with pytest.raises(ActionError, match="once each turn"):
        act(s, "p1", type="activate_ability", card_id=shifter.id, ability=0)
    assert s.state.players["p1"].mana == {"G": 1}  # (the second activation didn't cost anything)
    replay_matches(s)


# -- undo, redo, the other automation levels, combat triggers, costs with choices -----------------------------------
def test_undo_and_redo_take_back_a_mode_choice_and_its_memory(cards):
    s = build(cards, "Three Bowls of Porridge")
    respond_on(s)
    bowls = battlefield(s, "Three Bowls of Porridge")
    ogre = token(s, "p2", "Ogre", "5/5")
    activate_bowls(s, bowls)
    choose(s, "1:0")
    choose(s, ogre.id)
    assert list(rules(s).modes_chosen.values()) == [[1]] and len(rules(s).stack) == 1
    s.undo("p1")  # takes back the last choice (the target): the modes are chosen, the target isn't
    assert step(s) == "cast_slot_target" and rules(s).modes_chosen == {} and rules(s).stack == {}
    assert not s.state.cards[bowls.id].tapped and s.state.players["p1"].mana == {"C": 2}  # (nothing paid)
    s.undo("p1")  # … and the modes
    assert step(s) == "cast_modes"
    s.redo("p1")
    s.redo("p1")
    assert list(rules(s).modes_chosen.values()) == [[1]] and s.state.cards[bowls.id].tapped
    pass_until_stack_empty(s)
    assert s.state.cards[ogre.id].tapped
    replay_matches(s)


def assisted(cards, *names):
    from app.game.factory import PlayerSetup, new_game
    from tests.game_helpers import deck, enable

    alice = deck(cards, "Krenko, Mob Boss", [*((1, n) for n in names), (9, "Forest")])
    bob = deck(cards, "Atraxa, Praetors' Voice", [(10, "Island")])
    s = GameSession(enable(new_game([PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=bob)], shuffle=False),
                           "assisted"), cards=cards)
    act(s, "p1", type="pass_priority")
    return s


def test_in_assisted_mode_the_table_confirms_then_the_modes_are_chosen(cards):
    """ASSISTED doesn't stack triggers by itself: the table confirms first (app/rules/triggers.flush); the
    modes are announced once the ability is put on the stack."""
    s = assisted(cards, "Knight of Autumn")
    respond_on(s)
    cast(s, "Knight of Autumn", G=1, W=1, C=1)
    assert step(s) == "payment"
    choose(s, "pay")
    pass_until_stack_empty(s)
    assert step(s) == "trigger_confirm"
    choose(s, "yes")
    assert step(s) == "trigger_modes" and offered(s) == ["0:0", "2:0"]
    choose(s, "0:0")
    pass_until_stack_empty(s)
    assert s.state.cards[named(s, "Knight of Autumn").id].counters == {"+1/+1": 2}
    replay_matches(s)


def test_a_payment_decision_after_the_modes_keeps_them(cards):
    """The modes and targets announced first (601.2b-c) are part of the intent a payment decision resumes."""
    s = assisted(cards, "Cankerbloom", "Sol Ring")
    respond_on(s)
    bloom = battlefield(s, "Cankerbloom")
    ring = battlefield(s, "Sol Ring")
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=bloom.id, ability=0)
    choose(s, "0:0")
    choose(s, ring.id)
    assert step(s) == "payment" and s.state.cards[bloom.id].zone == "p1:battlefield"  # (nothing paid yet)
    choose(s, "pay")
    assert s.state.cards[bloom.id].zone == "p1:graveyard" and stack_modes(s) == [["Destroy target artifact."]]
    pass_until_stack_empty(s)
    assert s.state.cards[ring.id].zone == "p1:graveyard"
    replay_matches(s)


def test_a_modal_attack_trigger(cards):
    """Elder Gargaroth: Whenever this creature attacks or blocks, choose one — Beast / 3 life / draw."""
    from tests.test_rules_combat import attack, automate, creature, table

    s = table(cards)
    garg = creature(s, "p1", "Elder Gargaroth", "6/6", text="Reach, vigilance, trample\nWhenever this creature attacks or blocks, "
                    "choose one —\n• Create a 3/3 green Beast creature token.\n• You gain 3 life.\n• Draw a card.")
    automate(s)
    respond_on(s)
    attack(s, (garg, "p2"))
    assert step(s) == "trigger_modes" and offered(s) == ["0:0", "1:0", "2:0"]
    choose(s, "1:0")
    assert stack_modes(s)[0] == ["You gain 3 life."]
    advance(s, lambda s: s.state.turn.phase == "main2")  # (the ability resolves, then combat damage)
    assert s.state.players["p1"].life == 43 and s.state.players["p2"].life == 34
    replay_matches(s)


RANKLE = ("Flying, haste\nWhenever this creature deals combat damage to a player, choose any number —\n"
          "• Each player discards a card.\n• Each player loses 1 life and draws a card.\n"
          "• Each player sacrifices a creature of their choice.")


def test_choose_any_number_may_choose_none_and_runs_the_chosen_modes(cards):
    """Rankle, Master of Pranks (ruling 2019-10-04: you may choose zero modes; a mode can't be chosen more than
    once; each chosen mode is performed in full, in the order printed). Choosing zero removes the ability."""
    from tests.test_rules_combat import attack, automate, creature, table

    for picked in ((), ("1:0",)):
        s = table(cards)
        rankle = creature(s, "p1", "Rankle", "3/3", text=RANKLE)
        automate(s)
        respond_on(s)
        attack(s, (rankle, "p2"))
        advance(s, lambda s: rules(s).decision is not None and rules(s).decision.kind == "choose_cards")
        d = rules(s).decision
        assert step(s) == "trigger_modes" and (d.min_choices, d.max_choices) == (0, 3) and d.prompt == "Rankle: choose up to three modes"
        choose(s, *picked)
        if picked:
            advance(s, lambda s: s.state.turn.phase == "main2")
            assert s.state.players["p1"].life == 39 and s.state.players["p2"].life == 40 - 3 - 1  # (combat damage, then 1 each)
        else:
            assert rules(s).decision is None and "has no mode chosen and is removed" in log_text(s)
        replay_matches(s)


BREYA = ("{2}, Sacrifice two artifacts: Choose one —\n• Breya deals 3 damage to target player or planeswalker.\n"
         "• Target creature gets -4/-4 until end of turn.\n• You gain 5 life.")


def test_costs_with_choices_come_after_the_modes_and_targets(cards):
    """Breya, Etherium Shaper: the artifacts to sacrifice are chosen (602.2b → 601.2h) after the modes and the
    target, and nothing is sacrificed until everything is chosen."""
    s = build(cards, "Sol Ring")
    respond_on(s)
    breya = token(s, "p1", "Breya", "4/4", text=BREYA)
    rings = [battlefield(s, "Sol Ring")]
    act(s, "p1", type="create_token", player="p1", token={"name": "Gadget", "type_line": "Token Artifact — Test", "text": ""})
    act(s, "p1", type="create_token", player="p1", token={"name": "Gizmo", "type_line": "Token Artifact — Test", "text": ""})
    mana(s, C=2)
    act(s, "p1", type="activate_ability", card_id=breya.id, ability=0)
    assert step(s) == "cast_modes" and offered(s) == ["0:0", "1:0", "2:0"]
    choose(s, "2:0")  # You gain 5 life.
    d = rules(s).decision
    assert d is not None and d.resume["step"] == "ability_cost"  # (which two artifacts: only now)
    assert all(s.state.cards[c.id].zone == "p1:battlefield" for c in rings) and s.state.players["p1"].mana == {"C": 2}
    choose(s, *[o.id for o in d.options][:2])
    assert s.state.players["p1"].mana == {}
    life = s.state.players["p1"].life
    pass_until_stack_empty(s)
    assert s.state.players["p1"].life == life + 5
    replay_matches(s)


# -- step triggers: "choose one or more", and a mode that returns the object itself -------------------------------
def advance(s, done, limit=80):
    """Pass priority (declaring no attackers or blockers) until ``done(s)``; stops at any other decision."""
    for _ in range(limit):
        if done(s):
            return
        d = rules(s).decision
        if d is not None and d.kind in ("declare_attackers", "declare_blockers"):
            act(s, d.player, type=d.kind, **({"attackers": []} if d.kind == "declare_attackers" else {"blocks": []}))
        elif d is not None:
            return
        else:
            act(s, rules(s).priority, type="pass_priority")
    raise AssertionError("never got there")


def test_choose_one_or_more_at_the_beginning_of_the_first_main_phase(cards):
    """Black Market Connections: choose one or more — Sell Contraband / Buy Information / Hire a Mercenary, each
    with its own life loss; the modes are carried out in printed order."""
    s = build(cards, "Black Market Connections")
    respond_on(s)
    battlefield(s, "Black Market Connections")
    advance(s, lambda s: s.state.turn.number == 3 and rules(s).decision is not None)  # (Alice's next turn, main phase 1)
    d = rules(s).decision
    assert step(s) == "trigger_modes" and (d.min_choices, d.max_choices) == (1, 3) and s.state.turn.active_player == "p1"
    assert d.prompt == "Black Market Connections: choose one to three modes"
    assert offered(s) == ["0:0", "1:0", "2:0"]
    life, hand = s.state.players["p1"].life, len(zone(s.state, "p1", "hand"))
    choose(s, "1:0", "0:0")  # Buy Information and Sell Contraband (in either order)
    assert stack_modes(s)[0] == ["Sell Contraband — Create a Treasure token. You lose 1 life.",
                                 "Buy Information — Draw a card. You lose 2 life."]
    pass_until_stack_empty(s)
    assert s.state.players["p1"].life == life - 3 and named(s, "Treasure").zone == "p1:battlefield"
    assert len(zone(s.state, "p1", "hand")) == hand + 1
    replay_matches(s)


def test_choosing_none_of_a_one_or_more_ability_isnt_allowed(cards):
    s = build(cards, "Black Market Connections")
    respond_on(s)
    battlefield(s, "Black Market Connections")
    advance(s, lambda s: s.state.turn.number == 3 and rules(s).decision is not None)
    with pytest.raises(ActionError, match="Choose 1"):
        choose(s)
    assert step(s) == "trigger_modes"


def test_a_mode_that_returns_the_object_makes_it_a_new_one_with_no_memory(cards):
    """Kimoyo Beads (At the beginning of your end step, choose one that hasn't been chosen —): its third mode
    exiles it and returns it, a new object (400.7) — so next turn all three modes are offered again."""
    s = build(cards, "Kimoyo Beads")
    respond_on(s)
    beads = battlefield(s, "Kimoyo Beads")
    advance(s, lambda s: rules(s).decision is not None)  # (Alice's end step this turn)
    assert step(s) == "trigger_modes" and offered(s) == ["0:0", "1:0", "2:0"] and s.state.turn.phase == "end"
    first = rules(s).object_id(beads.id)
    choose(s, "2:0")  # Prime Bead
    assert list(rules(s).modes_chosen.items()) == [(f"{first}:0:game", [2])]
    pass_until_stack_empty(s)
    assert rules(s).object_id(beads.id) != first and s.state.cards[beads.id].zone == "p1:battlefield"
    s = reloaded(s)
    advance(s, lambda s: rules(s).decision is not None and s.state.turn.number == 3)
    assert step(s) == "trigger_modes" and offered(s) == ["0:0", "1:0", "2:0"]  # (a new object: nothing chosen yet)
    choose(s, "0:0")
    second = rules(s).object_id(beads.id)
    assert rules(s).modes_chosen[f"{second}:0:game"] == [0]
    pass_until_stack_empty(s)
    replay_matches(s)


# -- hidden information ------------------------------------------------------------------------------------------
def test_a_hidden_source_is_not_named_in_prompts_or_shown_in_the_stack_text(cards):
    """The chosen modes are public (601.2b, 603.3c) — as text of the ability — but a card in a hidden zone isn't
    named or quoted: its prompts say "A triggered ability" and the stack annotation says "Mode N"."""
    from app.game.rules_state import PendingTrigger
    from app.rules import modal_abilities
    from app.rules.plan import Plan

    s = build(cards, "Knight of Autumn")
    knight = to_hand(s, "Knight of Autumn")  # (in Alice's hand: nobody else can see it)
    plan = Plan(s.state, "p1", s.cards, None)
    definition = scripts.definitions(plan.ch(plan.state.cards[knight.id]))[0]
    assert modal_abilities._public_texts(plan, knight.id, definition, [0, 2]) == ["Mode 1", "Mode 3"]
    t = PendingTrigger(id="t1", controller="p1", source_card=knight.id, source_object=plan.oid(knight),
                       name="Knight of Autumn", ability=definition)
    plan.rules.pending_triggers.append(t)
    assert modal_abilities.put_trigger(plan, t) is False
    d = plan.rules.decision
    assert d.prompt == "A triggered ability: choose one mode" and d.source_id is None and "Knight" not in d.prompt
    # on the battlefield it is public, and so is what it says
    battlefield(s, "Knight of Autumn")
    plan = Plan(s.state, "p1", s.cards, None)
    shown = modal_abilities._public_texts(plan, knight.id, definition, [0, 2])
    assert shown == ["Put two +1/+1 counters on this creature.", "You gain 4 life."]


def test_the_other_players_see_only_who_is_choosing(cards):
    s = build(cards, "Knight of Autumn")
    respond_on(s)
    cast(s, "Knight of Autumn", G=1, W=1, C=1)
    pass_until_stack_empty(s)
    shown = json.dumps(s.view("p2")["rules"]["decision"])
    assert "gain 4 life" not in shown and "Knight" not in shown and "trigger_modes" not in shown
    assert s.view("p2")["rules"]["decision"]["public"] == {"type": "PLAYER_MAKING_CHOICE", "chooser": "Alice"}
    assert "gain 4 life" in json.dumps(s.view("p1")["rules"]["decision"])  # (the chooser sees the modes)
    choose(s, "2:0")  # the modes chosen are announced: everybody sees them on the ability
    ability_id = s.state.zones["stack"][-1]
    assert s.view("p2")["cards"][ability_id]["stack_info"]["modes"] == ["You gain 4 life."]
    assert '": You gain 4 life."' in log_text(s)  # (and in the log, after the ability's name)


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
    # (wave 3R1 reads "choose one at random", "Each mode must target a different player", reflexive "When you do,
    # choose …" and "If [condition], you may choose both instead": tests/test_rules_refused_r1.py)
    "Whenever this creature attacks, choose two at random —\n• Draw a card.\n• You gain 1 life.",  # (only "one at random" is read)
    "When this creature dies, choose one or more. Each mode must target a different player.\n• Target player loses 1 life.\n"
    "• You gain 1 life.",  # (a different player per mode: every mode must target a player)
    "When this creature enters, choose one. If you have exactly 13 poison counters, you may choose both instead.\n• Draw a card.\n"
    "• You gain 1 life.",  # Disciple of Perdition: "choose both instead"
    "{T}: Choose one. X is the number of spells you've cast this turn.\n• Draw a card.\n• You gain 1 life.",  # Gnostro (wave 50C reads it when a mode uses X: tests/test_rules_wave50c_header_extras.py; here none does)
    # (Bumi, King of Three Trials: "choose up to X, where X is …" is read since wave 50I, tests/test_rules_wave50i_modal_modes.py)
    "Whenever another nontoken permanent you control leaves the battlefield, choose one that hasn't been chosen this turn. "
    "Create a creature token with those characteristics.\n• Draw a card.\n• You gain 1 life.",  # Genku, Future Shaper
    "When this creature enters, choose one —\n• You may draw a card.\n• You gain 1 life.",  # (a mode with "you may")
    # Fixed activated groups are now read (Bow of Nylea); activated X-sized groups remain refused.
    "{T}: Choose one —\n• Put a +1/+1 counter on each of up to X target creatures.\n• You gain 1 life.",  # (an X-sized target group in an activated ability)
    "When this creature enters, choose one —\n• Put a +1/+1 counter on each of up to X target creatures.\n• You gain 1 life.",  # (X: not a plain group)
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
    assert header("Whenever this creature attacks, if a wizard sneezed this turn, choose one —\n• Draw a card.\n• You gain 1 life.") is None


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


def test_a_form_the_engine_doesnt_list_stays_partial(cards, monkeypatch):
    """Coverage follows SUPPORTED_MODAL_ABILITIES, not just what parses: take a form out and every card that
    uses it is PARTIAL again (the mode lines with it)."""
    data = cards.get(cards.resolve("Kargan Intimidator")["id"])
    assert coverage.of_characteristics(printed_from_data(data)).level == "FULL"
    monkeypatch.setattr(coverage, "SUPPORTED_MODAL_ABILITIES", coverage.SUPPORTED_MODAL_ABILITIES - {"memory:turn"})
    partial = coverage.of_characteristics(printed_from_data(data))
    assert partial.level == "PARTIAL" and len(partial.manual_parts) == 4  # ({1}: Choose one … and its three modes)
    knight = cards.get(cards.resolve("Knight of Autumn")["id"])
    assert coverage.of_characteristics(printed_from_data(knight)).level == "FULL"  # (other forms aren't affected)
    monkeypatch.setattr(coverage, "SUPPORTED_MODAL_ABILITIES", set())
    assert coverage.of_characteristics(printed_from_data(knight)).level == "PARTIAL"


def test_real_cards_are_fully_automated(cards):
    for name in ("Knight of Autumn", "Felidar Retreat", "Cankerbloom", "Flash Thompson, Spider-Fan", "Shambling Ghast",
                 "Three Bowls of Porridge", "Kargan Intimidator", "Sawblade Slinger", "Craftwork Crusher", "Phoenix Down",
                 "Monument to Endurance", "Kimoyo Beads"):
        data = cards.get(cards.resolve(name)["id"])
        assert coverage.of_characteristics(printed_from_data(data)).level == "FULL", name


def test_an_intervening_if_is_checked_as_it_triggers_and_again_as_it_resolves(cards):
    """603.4: "…, if you control a Forest, choose one —" doesn't trigger without a Forest (no modes are asked) and
    does nothing if the Forest is gone as it resolves. (Wording of Ojutai Exemplars' header plus an intervening
    "if"; not a real card.)"""
    s = build(cards, "Lightning Bolt", "Opt")
    respond_on(s)
    token(s, "p1", "Forester", "1/1", text="Whenever you cast a noncreature spell, if you control a Forest, choose one —\n"
          "• You gain 5 life.\n• Draw a card.")
    bolt = to_hand(s, "Lightning Bolt")
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])
    assert rules(s).decision is None and rules(s).pending_triggers == []  # (no Forest: it didn't trigger)
    pass_until_stack_empty(s)
    forest = battlefield(s, "Forest")
    opt = to_hand(s, "Opt")
    mana(s, U=1)
    act(s, "p1", type="cast_spell", card_id=opt.id)
    assert step(s) == "trigger_modes"
    choose(s, "0:0")
    entry = next(e for e in rules(s).stack.values() if e.kind == "trigger")
    assert entry.effects[0]["do"] == "only_if" and entry.effects[0]["skip"] == len(entry.effects) - 1
    act(s, "p1", type="move", card_ids=[forest.id], to={"zone": "graveyard"})  # the Forest is gone before it resolves
    life = s.state.players["p1"].life
    pass_until_stack_empty(s)
    assert s.state.players["p1"].life == life  # (nothing happened: the condition no longer holds)
    replay_matches(s)


def test_a_mode_can_create_a_delayed_trigger(cards):
    """Kykar, Zephyr Awakener (Whenever you cast a noncreature spell, choose one —): the first mode exiles another
    target creature you control and returns it at the beginning of the next end step (603.7: the delayed trigger
    is created as the mode resolves, with the object bound then)."""
    s = build(cards, "Lightning Bolt")
    respond_on(s)
    token(s, "p1", "Kykar", "3/4", text="Flying\nWhenever you cast a noncreature spell, choose one —\n• Exile another target "
          "creature you control. Return that card to the battlefield under its owner's control at the beginning of the next "
          "end step.\n• Create a 1/1 white Spirit creature token with flying.")
    bear = token(s, "p1", "Bear", "2/2")
    bolt = to_hand(s, "Lightning Bolt")
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])
    assert offered(s) == ["0:0", "1:0"]
    choose(s, "0:0")
    assert step(s) == "trigger_slot_target" and offered(s) == [bear.id]  # ("another": not Kykar itself)
    choose(s, bear.id)
    pass_until_stack_empty(s)
    assert s.state.cards.get(bear.id) is None or s.state.cards[bear.id].zone != "p1:battlefield"  # (exiled: a token is gone)
    assert len(rules(s).delayed) == 1 and rules(s).delayed[0].when == {"kind": "step", "step": "end", "whose": "next"}
    replay_matches(s)


def test_one_players_different_modal_triggers_are_ordered_then_announced_one_by_one(cards):
    """603.3b: a player with several triggers chooses their order; each is announced as it is put on the stack."""
    s = build(cards, "Lightning Bolt")
    respond_on(s)
    token(s, "p1", "Seer A", "1/1", text="Whenever a player casts a spell, choose one —\n• You gain 2 life.\n• Draw a card.")
    token(s, "p1", "Seer B", "1/1", text="Whenever a player casts a spell, choose one —\n• You gain 3 life.\n• Scry 1.")
    bolt = to_hand(s, "Lightning Bolt")
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])
    assert step(s) == "order_triggers"
    d = rules(s).decision
    first = next(o.id for o in d.options if o.label == "Seer B")
    second = next(o.id for o in d.options if o.label == "Seer A")
    choose(s, first, second)  # (the first picked goes on the stack first, resolves last)
    assert step(s) == "trigger_modes" and rules(s).decision.prompt.startswith("Seer B")
    choose(s, "0:0")
    assert step(s) == "trigger_modes" and rules(s).decision.prompt.startswith("Seer A")
    choose(s, "0:0")
    assert on_stack(s) == ["Lightning Bolt", "Seer B", "Seer A"]
    life = s.state.players["p1"].life
    pass_until_stack_empty(s)
    assert s.state.players["p1"].life == life + 2 + 3
    replay_matches(s)


# -- end of tests --


def test_a_paid_energy_cost_then_a_reflexive_modal_trigger():
    """Voltstorm Angel: "you may pay {E}{E}. When you do, choose one —" — the optional payment (107.14), then a
    reflexive modal trigger created only if it was paid (603.12)."""
    d = header("At the beginning of combat on your turn, you may pay {E}{E}. When you do, choose one —\n• Draw a card.\n• You gain 1 life.")
    pay, reflexive = d["effects"]
    assert pay["do"] == "optional_payment" and pay["cost"] == "Pay {E}{E}"
    assert reflexive["do"] == "reflexive" and reflexive["cond"] == {"succeeded": pay["bind"]}
    assert [m["effects"][0]["do"] for m in reflexive["ability"]["modes"]] == ["draw", "gain_life"]

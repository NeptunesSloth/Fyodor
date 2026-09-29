"""Attachment interactions (one model for Auras and Equipment, app/rules/attachments.py).

CR 303.4a (an Aura spell targets), 303.4c-d (illegal / creature Auras), 303.4e (control is
separate), 303.4f-g (an Aura entering without being cast: its controller chooses, no targeting;
nothing to enchant: it stays), 702.5a/d (enchant, players), 301.5b-d (Equipment; control of the
creature matters only on activation and resolution), 702.6a (equip), 701.3a-b (attach),
702.16c-d (protection), 608.2b (illegal targets), 704.5m-n (state-based actions).
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import attachments, effects
from app.rules.plan import Plan
from tests.game_helpers import act
from tests.test_rules_attachments import build, ch, mana, named, to_hand, token
from tests.test_rules_effects import pass_until_stack_empty


def respond_on(s):
    for prefs in s.state.rules.prefs.values():
        prefs.response = "on"


def cast(s, name, target, **m):
    card = to_hand(s, name)
    mana(s, **m)
    act(s, "p1", type="cast_spell", card_id=card.id, targets=[target])
    pass_until_stack_empty(s)
    return s.state.cards.get(card.id)


def equip(s, eq, target, n=1):
    mana(s, C=n)
    act(s, "p1", type="activate_ability", card_id=eq.id, ability=1, targets=[target])
    pass_until_stack_empty(s)


def on_battlefield(s, name, pid="p1"):
    card = named(s, name)
    act(s, pid, type="move", card_ids=[card.id], to={"player": pid, "zone": "battlefield"})
    return s.state.cards[card.id]


def run_sba(s):
    """Let state-based actions run (a priority pass, then back)."""
    act(s, s.state.rules.priority, type="pass_priority")


# -- Auras -------------------------------------------------------------------------------
def test_land_aura_enchants_only_a_land(cards):
    s = build(cards, "Test Land Aura")
    bear = token(s, "p1", "Bear")
    forest = on_battlefield(s, "Forest")
    card = to_hand(s, "Test Land Aura")
    mana(s, G=1)
    with pytest.raises(ActionError, match="legal target"):
        act(s, "p1", type="cast_spell", card_id=card.id, targets=[bear.id])
    act(s, "p1", type="cast_spell", card_id=card.id, targets=[forest.id])
    pass_until_stack_empty(s)
    assert s.state.cards[card.id].attached_to == forest.id
    assert "doesnt_untap" in ch(s, forest).imposed and not ch(s, bear).imposed


def test_permanent_aura_stops_activated_abilities(cards):
    s = build(cards, "Test Permanent Aura")
    rock = token(s, "p1", "Rock")
    act(s, "p1", type="create_token", player="p1", token={"name": "Signet", "type_line": "Token Artifact",
                                                         "text": "{T}: Add {C}."})
    signet = named(s, "Signet")
    aura = cast(s, "Test Permanent Aura", signet.id, W=1)
    assert aura.attached_to == signet.id
    with pytest.raises(ActionError, match="can't be activated"):
        act(s, "p1", type="activate_ability", card_id=signet.id, ability=0)  # mana abilities too
    assert rock.id  # (another permanent is unaffected)


def test_arrest_stops_attacks_blocks_and_abilities(cards):
    s = build(cards, "Arrest")
    pilot = token(s, "p1", "Pilot", text="{T}: Draw a card.")
    cast(s, "Arrest", pilot.id, W=3)
    assert {"cant_attack_or_block", "cant_activate"} <= ch(s, pilot).imposed
    with pytest.raises(ActionError, match="can't be activated"):
        act(s, "p1", type="activate_ability", card_id=pilot.id, ability=0)


def test_player_aura(cards):
    s = build(cards, "Test Curse")
    curse = cast(s, "Test Curse", "p2", B=1)
    assert curse.zone == "p1:battlefield" and curse.attached_player == "p2" and curse.attached_to is None
    run_sba(s)
    assert s.state.cards[curse.id].zone == "p1:battlefield"  # legal: it stays
    act(s, "p2", type="concede")
    plan = Plan(s.state, "p1", cards, None)  # (two players: the game just ended, so judge it directly)
    assert attachments.host_problem(plan, plan.state.cards[curse.id], "p2") == "that player left the game"  # 303.4c


def test_enchant_creature_you_control(cards):
    s = build(cards, "Test Own Aura")
    mine = token(s, "p1", "Mine")
    theirs = token(s, "p2", "Theirs")
    card = to_hand(s, "Test Own Aura")
    mana(s, G=1)
    with pytest.raises(ActionError, match="legal target"):
        act(s, "p1", type="cast_spell", card_id=card.id, targets=[theirs.id])
    act(s, "p1", type="cast_spell", card_id=card.id, targets=[mine.id])
    pass_until_stack_empty(s)
    assert ch(s, mine).pt == (4, 4)
    act(s, "p1", type="set_controller", card_ids=[mine.id], player="p2")  # the creature changes control
    run_sba(s)
    assert s.state.cards[card.id].zone == "p1:graveyard"  # no longer "a creature you control"


def test_aura_changing_controller(cards):
    """303.4e: control of the Aura is separate; "Enchant creature you control" is judged by the
    Aura's controller, so a new controller who doesn't control the creature loses it."""
    s = build(cards, "Test Own Aura", "Holy Strength")
    mine = token(s, "p1", "Mine")
    own = cast(s, "Test Own Aura", mine.id, G=1)
    holy = cast(s, "Holy Strength", mine.id, W=1)
    act(s, "p1", type="set_controller", card_ids=[holy.id], player="p2")  # "Enchant creature": still legal
    act(s, "p1", type="set_controller", card_ids=[own.id], player="p2")
    run_sba(s)
    assert s.state.cards[holy.id].zone == "p2:battlefield" and s.state.cards[holy.id].attached_to == mine.id
    assert s.state.cards[own.id].zone == "p1:graveyard"
    assert ch(s, mine).pt == (3, 4)  # the Holy Strength bonus still applies, whoever controls it


def test_enchanted_object_stops_being_legal(cards):
    """A crewed Vehicle is a creature until end of turn; when it stops being one, an "Enchant
    creature" Aura on it is put into its owner's graveyard (704.5m)."""
    s = build(cards, "Sky-Skiff", "Holy Strength")
    skiff = on_battlefield(s, "Sky-Skiff")
    pilot = token(s, "p1", "Pilot", "1/1")
    act(s, "p1", type="activate_ability", card_id=skiff.id, ability=1, crew=[pilot.id])
    pass_until_stack_empty(s)
    holy = cast(s, "Holy Strength", skiff.id, W=1)
    assert holy.attached_to == skiff.id
    act(s, "p1", type="pass_priority", until="next_turn")
    for _ in range(12):
        if s.state.cards[holy.id].zone != "p1:battlefield" or s.state.turn.active_player == "p2":
            break
        act(s, s.state.rules.priority, type="pass_priority")
    assert s.state.cards[holy.id].zone == "p1:graveyard"


def test_protection_can_not_be_targeted_or_enchanted(cards):
    s = build(cards, "Holy Strength")
    knight = token(s, "p1", "Knight", text="Protection from white")
    card = to_hand(s, "Holy Strength")
    mana(s, W=1)
    with pytest.raises(ActionError, match="legal target"):
        act(s, "p1", type="cast_spell", card_id=card.id, targets=[knight.id])
    act(s, "p1", type="move", card_ids=[card.id], to={"zone": "battlefield"})  # put there by hand …
    act(s, "p1", type="attach", card_ids=[card.id], to=knight.id)  # … and attached by hand
    run_sba(s)
    assert s.state.cards[card.id].zone == "p1:graveyard"  # 702.16c: it can't be enchanted by white Auras


def test_shroud_and_hexproof_targeting(cards):
    s = build(cards, "Holy Strength")
    veiled = token(s, "p1", "Veiled", text="Shroud")
    warded = token(s, "p1", "Warded", text="Hexproof")
    card = to_hand(s, "Holy Strength")
    mana(s, W=1)
    with pytest.raises(ActionError, match="legal target"):
        act(s, "p1", type="cast_spell", card_id=card.id, targets=[veiled.id])  # shroud: nobody
    act(s, "p1", type="cast_spell", card_id=card.id, targets=[warded.id])  # hexproof: its controller may
    pass_until_stack_empty(s)
    assert s.state.cards[card.id].attached_to == warded.id


def test_aura_entering_without_being_cast_chooses_without_targeting(cards):
    """303.4f: blinked, the Aura isn't cast and doesn't target: an opponent's hexproof creature is
    a legal choice. Its controller chooses among what it could enchant."""
    s = build(cards, "Holy Strength")
    mine = token(s, "p1", "Mine")
    hidden = token(s, "p2", "Hidden", text="Hexproof")
    holy = cast(s, "Holy Strength", mine.id, W=1)
    plan = Plan(s.state, "p1", cards, None)
    ctx = {"controller": "p1", "source_card": None, "source_object": None, "effects": [], "next": 0, "stack_id": "none",
           "targets": [{"id": holy.id, "object_id": plan.oid(holy.id)}]}
    assert effects.blink(plan, ctx, {"do": "blink", "who": "target"}) is False
    d = plan.rules.decision
    assert d.resume["step"] == "aura_enters" and {mine.id, hidden.id} <= {o.id for o in d.options}
    assert plan.state.cards[holy.id].zone == "p1:exile"  # it enters only once the choice is made
    attachments.resume_aura_enters(plan, d, [hidden.id])
    assert plan.state.cards[holy.id].zone == "p1:battlefield" and plan.state.cards[holy.id].attached_to == hidden.id


def test_aura_with_nothing_to_enchant_stays_where_it_is(cards):
    """303.4g: no legal object: the Aura stays in its current zone."""
    s = build(cards, "Holy Strength")
    holy = named(s, "Holy Strength")
    act(s, "p1", type="move", card_ids=[holy.id], to={"zone": "graveyard"})
    plan = Plan(s.state, "p1", cards, None)
    assert attachments.enter(plan, [{"card": holy.id, "player": "p1", "actor": "p1"}], None)
    assert plan.state.cards[holy.id].zone == "p1:graveyard"


def test_aura_entering_with_one_choice_attaches(cards):
    s = build(cards, "Holy Strength")
    only = token(s, "p1", "Only")
    holy = named(s, "Holy Strength")
    act(s, "p1", type="move", card_ids=[holy.id], to={"zone": "graveyard"})
    plan = Plan(s.state, "p1", cards, None)
    assert attachments.enter(plan, [{"card": holy.id, "player": "p1", "actor": "p1"}], None)
    assert plan.state.cards[holy.id].attached_to == only.id  # (a forced choice isn't asked)


# -- Equipment -----------------------------------------------------------------------------
def test_equip_fizzles_if_the_creature_changes_control_before_resolution(cards):
    s = build(cards, "Bonesplitter")
    respond_on(s)
    bear = token(s, "p1", "Bear")
    eq = on_battlefield(s, "Bonesplitter")
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=eq.id, ability=1, targets=[bear.id])
    act(s, "p1", type="set_controller", card_ids=[bear.id], player="p2")  # in response
    pass_until_stack_empty(s)
    assert s.state.cards[eq.id].attached_to is None  # 608.2b: no longer "a creature you control"


def test_equip_fizzles_if_the_creature_leaves(cards):
    s = build(cards, "Bonesplitter")
    respond_on(s)
    bear = token(s, "p1", "Bear")
    eq = on_battlefield(s, "Bonesplitter")
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=eq.id, ability=1, targets=[bear.id])
    act(s, "p1", type="move", card_ids=[bear.id], to={"zone": "graveyard"})
    pass_until_stack_empty(s)
    assert s.state.cards[eq.id].attached_to is None and s.state.cards[eq.id].zone == "p1:battlefield"


def test_equipped_creature_changes_control_equipment_stays(cards):
    """301.5d: changing control of the creature doesn't change control of the Equipment (it stays
    attached; the bonus follows the creature)."""
    s = build(cards, "Bonesplitter")
    bear = token(s, "p1", "Bear")
    eq = on_battlefield(s, "Bonesplitter")
    equip(s, eq, bear.id)
    act(s, "p1", type="set_controller", card_ids=[bear.id], player="p2")
    run_sba(s)
    assert s.state.cards[eq.id].attached_to == bear.id and s.state.cards[eq.id].controller == "p1"
    assert ch(s, bear).pt == (4, 2)


def test_equipment_changes_control(cards):
    s = build(cards, "Bonesplitter")
    bear = token(s, "p1", "Bear")
    eq = on_battlefield(s, "Bonesplitter")
    equip(s, eq, bear.id)
    act(s, "p1", type="set_controller", card_ids=[eq.id], player="p2")
    run_sba(s)
    assert s.state.cards[eq.id].attached_to == bear.id  # still attached (control is separate)
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=eq.id, ability=1, targets=[bear.id])  # only its controller


def test_equipped_creature_stops_being_a_creature(cards):
    s = build(cards, "Sky-Skiff", "Bonesplitter")
    skiff = on_battlefield(s, "Sky-Skiff")
    pilot = token(s, "p1", "Pilot", "1/1")
    eq = on_battlefield(s, "Bonesplitter")
    act(s, "p1", type="activate_ability", card_id=skiff.id, ability=1, crew=[pilot.id])
    pass_until_stack_empty(s)
    equip(s, eq, skiff.id)
    assert s.state.cards[eq.id].attached_to == skiff.id
    act(s, "p1", type="pass_priority", until="next_turn")
    for _ in range(12):
        if s.state.cards[eq.id].attached_to is None or s.state.turn.active_player == "p2":
            break
        act(s, s.state.rules.priority, type="pass_priority")
    assert s.state.cards[eq.id].attached_to is None and s.state.cards[eq.id].zone == "p1:battlefield"  # 704.5n


def test_equip_targeting_shroud_hexproof_protection(cards):
    s = build(cards, "Bonesplitter")
    veiled = token(s, "p1", "Veiled", text="Shroud")
    warded = token(s, "p1", "Warded", text="Hexproof")
    shielded = token(s, "p1", "Shielded", text="Protection from artifacts")
    eq = on_battlefield(s, "Bonesplitter")
    mana(s, C=1)
    for bad in (veiled, shielded):
        with pytest.raises(ActionError, match="legal target"):
            act(s, "p1", type="activate_ability", card_id=eq.id, ability=1, targets=[bad.id])
    act(s, "p1", type="activate_ability", card_id=eq.id, ability=1, targets=[warded.id])  # your own hexproof creature
    pass_until_stack_empty(s)
    assert s.state.cards[eq.id].attached_to == warded.id


def test_multiple_equipment_on_one_creature(cards):
    s = build(cards, "Bonesplitter", "Behemoth Sledge")
    bear = token(s, "p1", "Bear")
    a = on_battlefield(s, "Bonesplitter")
    b = on_battlefield(s, "Behemoth Sledge")
    equip(s, a, bear.id)
    equip(s, b, bear.id, n=3)
    assert ch(s, bear).pt == (6, 4)  # +2/+0 and +2/+2


def test_one_equipment_one_creature(cards):
    s = build(cards, "Bonesplitter")
    bear = token(s, "p1", "Bear")
    goat = token(s, "p1", "Goat")
    eq = on_battlefield(s, "Bonesplitter")
    equip(s, eq, bear.id)
    equip(s, eq, goat.id)
    assert s.state.cards[eq.id].attached_to == goat.id
    assert ch(s, bear).pt == (2, 2) and ch(s, goat).pt == (4, 2)


def test_host_problem_is_the_one_predicate(cards):
    s = build(cards, "Bonesplitter", "Holy Strength")
    bear = token(s, "p1", "Bear")
    eq = on_battlefield(s, "Bonesplitter")
    forest = on_battlefield(s, "Forest")
    holy = on_battlefield(s, "Holy Strength")
    plan = Plan(s.state, "p1", cards, None)
    assert attachments.host_problem(plan, plan.state.cards[eq.id], bear.id) is None
    assert "only equip a creature" in attachments.host_problem(plan, plan.state.cards[eq.id], forest.id)
    assert "itself" in attachments.host_problem(plan, plan.state.cards[eq.id], eq.id)
    assert "only an Aura" in attachments.host_problem(plan, plan.state.cards[eq.id], "p2")
    assert attachments.host_problem(plan, plan.state.cards[holy.id], bear.id) is None
    assert attachments.host_problem(plan, plan.state.cards[holy.id], forest.id)

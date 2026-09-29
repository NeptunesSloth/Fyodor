"""Replacement and prevention effects, stage 1 (CR 614, 615, 903.9b; app/rules/replacements.py).

Every scenario checks the final table, that replaying the recorded history reproduces it, and that
choices are private decisions with resume data (no RNG anywhere).
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import coverage, scripts
from tests.game_helpers import act, find, turn_on, zone
from tests.test_rules_attachments import build, mana, named, to_hand, token
from tests.test_rules_combat import attack, automate, block, creature, table
from tests.test_rules_effects import pass_until_stack_empty, replay_matches
from tests.test_rules_scripts import ch
from tests.test_rules_suspend import until


def permanent(s, pid, name, kind, text):
    act(s, pid, type="create_token", player=pid, token={"name": name, "type_line": f"Token {kind} — Test", "text": text})
    return next(c for c in s.state.cards.values() if c.name == name and c.owner == pid)


def activate(s, card, **kw):
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=card.id, ability=0, **kw)
    pass_until_stack_empty(s)


def rules(s):
    return s.state.rules


def tap_events(s, card_id):
    """A "tapped" event would mean the permanent entered untapped and was tapped afterwards."""
    return [e for e in rules(s).events if e.card == card_id and e.kind == "tapped"]


RAMP = "{1}: Search your library for a land card, put it onto the battlefield, then shuffle."
REANIMATE_LAND = "{1}: Return target land card from your graveyard to the battlefield."


# -- entering the battlefield (614.1c-d, 614.12a, 122.6) -----------------------------------------------
def test_enters_tapped_land_is_tapped_on_every_path(cards):
    # played from hand (a land drop)
    s = build(cards, "Test Guildgate")
    gate = to_hand(s, "Test Guildgate")
    act(s, "p1", type="play_land", card_id=gate.id)
    assert s.state.cards[gate.id].zone == "p1:battlefield" and s.state.cards[gate.id].tapped
    assert not tap_events(s, gate.id)  # tapped as part of the move (614.1d), not tapped afterwards
    replay_matches(s)
    # returned from the graveyard by an effect
    act(s, "p1", type="move", card_ids=[gate.id], to={"zone": "graveyard"})
    src = token(s, "p1", "Necro", text=REANIMATE_LAND)
    activate(s, src, targets=[gate.id])
    assert s.state.cards[gate.id].zone == "p1:battlefield" and s.state.cards[gate.id].tapped
    replay_matches(s)
    # put onto the battlefield by a search
    act(s, "p1", type="move", card_ids=[gate.id], to={"zone": "library"})
    ramp = token(s, "p1", "Ramp", text=RAMP)
    activate(s, ramp)
    d = rules(s).decision
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[gate.id])
    assert s.state.cards[gate.id].zone == "p1:battlefield" and s.state.cards[gate.id].tapped
    assert not tap_events(s, gate.id)
    replay_matches(s)
    assert s.history.rebuild().model_dump(mode="json") == s.state.model_dump(mode="json")


def test_check_land_enters_untapped_only_if_you_control_the_named_land(cards):
    s = build(cards, "Test Check Land")
    land = to_hand(s, "Test Check Land")
    act(s, "p1", type="play_land", card_id=land.id)
    assert s.state.cards[land.id].tapped  # no Forest or Island: tapped
    replay_matches(s)
    s = build(cards, "Test Check Land")
    land = to_hand(s, "Test Check Land")
    forest = find(s.state, "Forest", "p1")
    act(s, "p1", type="move", card_ids=[forest.id], to={"zone": "battlefield"})
    act(s, "p1", type="play_land", card_id=land.id)
    assert not s.state.cards[land.id].tapped
    replay_matches(s)
    # the same condition on the search path (the land itself doesn't count: it isn't there yet)
    s = build(cards, "Test Check Land")
    ramp = token(s, "p1", "Ramp", text=RAMP)
    activate(s, ramp)
    d = rules(s).decision
    land = named(s, "Test Check Land")
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[land.id])
    assert s.state.cards[land.id].zone == "p1:battlefield" and s.state.cards[land.id].tapped
    replay_matches(s)


def test_fast_land_counts_other_lands(cards):
    s = build(cards, "Test Fast Land")
    forests = [c for c in s.state.cards.values() if c.name == "Forest" and c.owner == "p1"]
    act(s, "p1", type="move", card_ids=[f.id for f in forests[:2]], to={"zone": "battlefield"})
    land = to_hand(s, "Test Fast Land")
    act(s, "p1", type="play_land", card_id=land.id)
    assert not s.state.cards[land.id].tapped  # two other lands
    act(s, "p1", type="move", card_ids=[land.id], to={"zone": "hand"})
    act(s, "p1", type="move", card_ids=[forests[2].id], to={"zone": "battlefield"})
    rules(s).lands_played = {}
    act(s, "p1", type="play_land", card_id=land.id)
    assert s.state.cards[land.id].tapped  # three other lands
    replay_matches(s)


def test_vivid_land_enters_tapped_with_its_counters_via_a_search(cards):
    s = build(cards, "Vivid Marsh")
    ramp = token(s, "p1", "Ramp", text=RAMP)
    activate(s, ramp)
    d = rules(s).decision
    marsh = named(s, "Vivid Marsh")
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[marsh.id])
    marsh = s.state.cards[marsh.id]
    assert marsh.zone == "p1:battlefield" and marsh.tapped and marsh.counters == {"charge": 2}
    assert not tap_events(s, marsh.id)
    replay_matches(s)


@pytest.mark.parametrize(("answer", "life", "tapped"), [("pay", 38, False), ("tapped", 40, True)])
def test_shock_land_put_onto_the_battlefield_by_an_effect_asks_its_controller(cards, answer, life, tapped):
    s = build(cards, "Breeding Pool")
    ramp = token(s, "p1", "Ramp", text=RAMP)
    activate(s, ramp)
    d = rules(s).decision
    pool = named(s, "Breeding Pool")
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[pool.id])
    d = rules(s).decision  # 614.12a: the choice is made before it enters
    assert d is not None and d.player == "p1" and d.resume["step"] == "enter_choice"
    assert s.state.cards[pool.id].zone == "p1:library"
    assert "Breeding Pool" in s.view("p1")["rules"]["decision"]["prompt"]
    assert "Breeding Pool" not in s.view("p2")["rules"]["decision"]["prompt"]  # (a card from a hidden zone)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[answer])
    pool = s.state.cards[pool.id]
    assert pool.zone == "p1:battlefield" and pool.tapped == tapped and s.state.players["p1"].life == life
    assert rules(s).decision is None and not tap_events(s, pool.id)
    replay_matches(s)


def test_enters_with_a_counter_for_each_creature_card_in_your_graveyard(cards):
    s = build(cards, "Test Ooze", "Grizzly Bears", "Llanowar Elves")
    for name in ("Grizzly Bears", "Llanowar Elves"):
        act(s, "p1", type="move", card_ids=[named(s, name).id], to={"zone": "graveyard"})
    ooze = to_hand(s, "Test Ooze")
    mana(s, G=1, C=1)
    act(s, "p1", type="cast_spell", card_id=ooze.id)
    pass_until_stack_empty(s)
    assert s.state.cards[ooze.id].zone == "p1:battlefield" and s.state.cards[ooze.id].counters == {"+1/+1": 2}
    replay_matches(s)


def test_for_each_of_a_group_it_might_belong_to_stays_manual():
    # whether an entering creature counts itself among "creatures you control" isn't decided here
    assert not scripts.definitions(ch("Hope", "Creature", "Hope enters with a hope counter on it for each creature you control."))
    assert not scripts.definitions(ch("Sun", "Creature", "Sun enters with a +1/+1 counter on it for each color of mana spent to cast it."))
    assert scripts.definitions(ch("Sludge", "Creature", "Sludge enters with a +1/+1 counter on it for each other Ooze you control."))


def test_tokens_enter_tapped_only_when_their_creator_says_so(cards):
    s = build(cards)
    plain = token(s, "p1", "Recruiter", text="{1}: Create a 1/1 white Soldier creature token.")
    tapped = token(s, "p1", "Drill", text="{1}: Create two 1/1 white Soldier creature tokens tapped.")
    activate(s, plain)
    soldiers = [c for c in s.state.cards.values() if c.name == "Soldier"]
    assert len(soldiers) == 1 and not soldiers[0].tapped
    activate(s, tapped)
    soldiers = [c for c in s.state.cards.values() if c.name == "Soldier"]
    assert sorted(c.tapped for c in soldiers) == [False, True, True]
    assert not any(tap_events(s, c.id) for c in soldiers)
    replay_matches(s)


def test_unearth_returns_the_creature_tapped_when_it_enters_tapped(cards):
    s = build(cards, "Test Unearth Golem")
    golem = named(s, "Test Unearth Golem")
    act(s, "p1", type="move", card_ids=[golem.id], to={"zone": "graveyard"})
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=golem.id, ability=1)  # unearth {1}
    pass_until_stack_empty(s)
    golem = s.state.cards[golem.id]
    assert golem.zone == "p1:battlefield" and golem.tapped and not tap_events(s, golem.id)
    act(s, "p1", type="set_damage", card_ids=[golem.id], value=2)
    act(s, "p1", type="pass_priority")  # state-based actions: it would die → exiled instead (702.84a)
    assert s.state.cards[golem.id].zone == "p1:exile"
    replay_matches(s)


def test_persist_returns_the_creature_tapped_with_its_counter(cards):
    s = build(cards, "Test Persist Golem")
    golem = named(s, "Test Persist Golem")
    act(s, "p1", type="move", card_ids=[golem.id], to={"zone": "battlefield"})
    act(s, "p1", type="set_damage", card_ids=[golem.id], value=2)
    act(s, "p1", type="pass_priority")
    until(s, lambda s: not s.state.zones.get("stack") and s.state.cards[golem.id].zone == "p1:battlefield")
    golem = s.state.cards[golem.id]
    assert golem.tapped and golem.counters == {"-1/-1": 1}
    replay_matches(s)


def test_planeswalker_loyalty_on_the_effect_path(cards):
    s = build(cards, "Test Walker Card")
    walker = named(s, "Test Walker Card")
    act(s, "p1", type="move", card_ids=[walker.id], to={"zone": "graveyard"})
    src = token(s, "p1", "Necro", text="{1}: Return target permanent card from your graveyard to the battlefield.")
    activate(s, src, targets=[walker.id])
    assert s.state.cards[walker.id].zone == "p1:battlefield" and s.state.cards[walker.id].counters == {"loyalty": 3}
    replay_matches(s)


# -- static prevention (615.1, 615.10) ------------------------------------------------------------
def test_prevent_all_combat_damage_to_you(cards):
    s = table(cards)
    vampire = creature(s, "p1", "Vampire", "3/3", "Lifelink\nDeathtouch")
    permanent(s, "p2", "Moat", "Enchantment", "Prevent all combat damage that would be dealt to you.")
    automate(s)
    attack(s, (vampire, "p2"))
    until(s, lambda s: s.state.turn.phase == "main2")
    assert s.state.players["p2"].life == 40 and s.state.players["p1"].life == 40  # nothing dealt: no lifelink gain
    assert not s.state.players["p2"].commander_damage
    replay_matches(s)


def test_prevent_all_combat_damage_by_small_creatures_blocked_and_unblocked(cards):
    s = table(cards)
    stinger = creature(s, "p1", "Stinger", "2/2", "Deathtouch\nLifelink")
    brute = creature(s, "p1", "Brute", "3/3")
    wall = creature(s, "p2", "Wall", "2/2")
    permanent(s, "p1", "Weakness", "Enchantment", "Prevent all combat damage that would be dealt by creatures with power 2 or less.")
    automate(s)
    attack(s, (stinger, "p2"), (brute, "p2"))
    block(s, "p2", (wall, stinger))
    until(s, lambda s: s.state.turn.phase == "main2")
    # the 2/2s' damage is prevented both ways (deathtouch never applied, no lifelink); the 3/3 hits
    assert wall.id in s.state.cards and s.state.cards[wall.id].damage == 0
    assert stinger.id in s.state.cards and s.state.cards[stinger.id].damage == 0
    assert s.state.players["p2"].life == 37 and s.state.players["p1"].life == 40
    replay_matches(s)


def test_fog_prevents_this_turns_combat_damage_only(cards):
    s = table(cards)
    brute = creature(s, "p1", "Brute", "3/3")
    fogger = permanent(s, "p1", "Fogger", "Artifact", "{1}: Prevent all combat damage that would be dealt this turn.")
    turn_on(s)
    act(s, "p1", type="pass_priority")  # → main 1
    activate(s, fogger)
    assert len(rules(s).replacements) == 1 and rules(s).replacements[0]["kind"] == "prevent"
    act(s, "p1", type="pass_priority")  # → combat
    attack(s, (brute, "p2"))
    until(s, lambda s: s.state.turn.phase == "main2")
    assert s.state.players["p2"].life == 40
    # next turn, the record has expired (615.3)
    until(s, lambda s: s.state.turn.number == 3 and s.state.turn.phase == "declare_attackers")
    attack(s, (brute, "p2"))
    until(s, lambda s: s.state.turn.phase == "main2")
    assert s.state.players["p2"].life == 37 and not rules(s).replacements
    replay_matches(s)


def test_prevent_all_damage_to_you_vs_noncombat_damage(cards):
    s = build(cards, "Test Ward", "Test Moat", "Lightning Bolt", "Pyroclasm")
    ward, moat = named(s, "Test Ward"), named(s, "Test Moat")
    act(s, "p1", type="move", card_ids=[ward.id], to={"player": "p2", "zone": "battlefield"})
    ogre = token(s, "p2", "Ogre", "4/4")
    bolt = to_hand(s, "Lightning Bolt")
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])
    pass_until_stack_empty(s)
    assert s.state.players["p2"].life == 40  # "Prevent all damage that would be dealt to you"
    # the same shield doesn't cover their creatures …
    act(s, "p1", type="move", card_ids=[bolt.id], to={"zone": "hand"})
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=[ogre.id])
    pass_until_stack_empty(s)
    assert s.state.cards[ogre.id].damage == 3
    # … and a combat-only one ("Prevent all combat damage that would be dealt to you") doesn't stop a Bolt
    act(s, "p1", type="move", card_ids=[ward.id], to={"player": "p2", "zone": "graveyard"})
    act(s, "p1", type="move", card_ids=[moat.id], to={"player": "p2", "zone": "battlefield"})
    act(s, "p1", type="move", card_ids=[bolt.id], to={"zone": "hand"})
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])
    pass_until_stack_empty(s)
    assert s.state.players["p2"].life == 37
    replay_matches(s)


def test_prevent_all_damage_to_creatures_you_control(cards):
    s = build(cards, "Test Aegis", "Pyroclasm")
    aegis = named(s, "Test Aegis")
    act(s, "p1", type="move", card_ids=[aegis.id], to={"zone": "battlefield"})
    mine = token(s, "p1", "Mine", "3/3")
    theirs = token(s, "p2", "Theirs", "3/3")
    pyro = to_hand(s, "Pyroclasm")
    mana(s, R=1, C=1)
    act(s, "p1", type="cast_spell", card_id=pyro.id)
    pass_until_stack_empty(s)
    assert s.state.cards[mine.id].damage == 0 and s.state.cards[theirs.id].damage == 2
    replay_matches(s)


# -- 615.7: which damage a shield prevents ----------------------------------------------------------
def test_shield_choice_between_two_sources_is_the_shielded_players(cards):
    s = table(cards)
    leech = creature(s, "p1", "Leech", "2/2", "Lifelink")
    brute = creature(s, "p1", "Brute", "2/2")
    automate(s)
    rules(s).prevention["p2"] = 2  # "prevent the next 2 damage that would be dealt to you this turn"
    attack(s, (leech, "p2"), (brute, "p2"))
    until(s, lambda s: rules(s).decision is not None and rules(s).decision.resume.get("step") == "shield_order")
    d = rules(s).decision
    assert d.player == "p2" and {o.card_id for o in d.options} == {leech.id, brute.id}
    act(s, "p2", type="choose", decision_id=d.id, option_ids=[f"p2:{rules(s).object_id(leech.id)}"])
    until(s, lambda s: s.state.turn.phase == "main2")
    assert s.state.players["p2"].life == 38 and s.state.players["p1"].life == 40  # the lifelinker's damage was prevented
    assert not rules(s).prevention
    replay_matches(s)


def test_shield_choice_the_other_way_round(cards):
    s = table(cards)
    leech = creature(s, "p1", "Leech", "2/2", "Lifelink")
    brute = creature(s, "p1", "Brute", "2/2")
    automate(s)
    rules(s).prevention["p2"] = 2
    attack(s, (leech, "p2"), (brute, "p2"))
    until(s, lambda s: rules(s).decision is not None and rules(s).decision.resume.get("step") == "shield_order")
    d = rules(s).decision
    act(s, "p2", type="choose", decision_id=d.id, option_ids=[f"p2:{rules(s).object_id(brute.id)}"])
    until(s, lambda s: s.state.turn.phase == "main2")
    assert s.state.players["p2"].life == 38 and s.state.players["p1"].life == 42
    replay_matches(s)


def test_interchangeable_sources_need_no_choice(cards):
    s = table(cards)
    a = creature(s, "p1", "Bear A", "2/2")
    b = creature(s, "p1", "Bear B", "2/2")
    automate(s)
    rules(s).prevention["p2"] = 2
    attack(s, (a, "p2"), (b, "p2"))
    until(s, lambda s: s.state.turn.phase == "main2")
    assert s.state.players["p2"].life == 38 and not rules(s).prevention
    assert not any(e.get("type") == "choose" for e in [])  # (no shield decision was ever opened: the turn went on)
    replay_matches(s)


# -- 903.9b: a commander that would go to its owner's hand ----------------------------------------
def test_commander_bounced_may_go_to_the_command_zone_instead(cards):
    s = build(cards)
    krenko = find(s.state, "Krenko, Mob Boss", "p1")
    act(s, "p1", type="move", card_ids=[krenko.id], to={"zone": "battlefield"})
    bouncer = token(s, "p1", "Bouncer", text="{1}: Return target creature to its owner's hand.")
    activate(s, bouncer, targets=[krenko.id])
    d = rules(s).decision
    assert d is not None and d.player == "p1" and d.resume["step"] == "commander_instead" and "903.9b" in d.prompt
    assert s.state.cards[krenko.id].zone == "p1:battlefield"  # nothing moved yet: the replacement applies to the move
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["no"])
    assert s.state.cards[krenko.id].zone == "p1:hand" and rules(s).decision is None
    replay_matches(s)
    act(s, "p1", type="move", card_ids=[krenko.id], to={"zone": "battlefield"})
    activate(s, bouncer, targets=[krenko.id])
    d = rules(s).decision
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["yes"], remember="yes_this_turn")
    assert s.state.cards[krenko.id].zone == "p1:command" and krenko.id not in zone(s.state, "p1", "hand")
    replay_matches(s)
    # the remembered answer applies to the next one this turn without asking
    act(s, "p1", type="move", card_ids=[krenko.id], to={"zone": "battlefield"})
    activate(s, bouncer, targets=[krenko.id])
    assert rules(s).decision is None and s.state.cards[krenko.id].zone == "p1:command"
    replay_matches(s)


def test_only_the_owner_is_asked_and_not_for_ordinary_creatures(cards):
    s = build(cards)
    bear = token(s, "p2", "Bear")
    bouncer = token(s, "p1", "Bouncer", text="{1}: Return target creature to its owner's hand.")
    activate(s, bouncer, targets=[bear.id])
    assert rules(s).decision is None and bear.id not in s.state.cards  # a token: gone
    atraxa = find(s.state, "Atraxa, Praetors' Voice", "p2")
    act(s, "p2", type="move", card_ids=[atraxa.id], to={"zone": "battlefield"})
    activate(s, bouncer, targets=[atraxa.id])
    d = rules(s).decision
    assert d is not None and d.player == "p2"
    with pytest.raises(ActionError):
        act(s, "p1", type="choose", decision_id=d.id, option_ids=["yes"])
    act(s, "p2", type="choose", decision_id=d.id, option_ids=["yes"])
    assert s.state.cards[atraxa.id].zone == "p2:command"
    replay_matches(s)


# -- "If ~ would die, exile it instead" (614.1a) ------------------------------------------------------
def test_would_die_exile_instead_on_damage_destroy_and_sacrifice(cards):
    s = build(cards, "Test Ghost", "Murder")
    ghost = named(s, "Test Ghost")
    act(s, "p1", type="move", card_ids=[ghost.id], to={"zone": "battlefield"})
    act(s, "p1", type="set_damage", card_ids=[ghost.id], value=2)
    act(s, "p1", type="pass_priority")  # lethal damage: a state-based action destroys it (704.5g)
    assert s.state.cards[ghost.id].zone == "p1:exile"
    replay_matches(s)
    # destroyed by a spell
    act(s, "p1", type="move", card_ids=[ghost.id], to={"zone": "battlefield"})
    murder = to_hand(s, "Murder")
    mana(s, B=2, C=1)
    act(s, "p1", type="cast_spell", card_id=murder.id, targets=[ghost.id])
    pass_until_stack_empty(s)
    assert s.state.cards[ghost.id].zone == "p1:exile"
    replay_matches(s)
    # sacrificed as a cost
    act(s, "p1", type="move", card_ids=[ghost.id], to={"zone": "battlefield"})
    act(s, "p1", type="activate_ability", card_id=ghost.id, ability=1)
    pass_until_stack_empty(s)
    assert s.state.cards[ghost.id].zone == "p1:exile" and s.state.players["p1"].life == 41
    replay_matches(s)


def test_from_anywhere_covers_a_mill(cards):
    s = build(cards, "Test Haunt")
    haunt = named(s, "Test Haunt")
    act(s, "p1", type="move", card_ids=[haunt.id], to={"zone": "library"}, position="top")
    miller = token(s, "p1", "Miller", text="{1}: Mill two cards.")
    activate(s, miller)
    assert s.state.cards[haunt.id].zone == "p1:exile" and len(zone(s.state, "p1", "graveyard")) == 1
    replay_matches(s)


def test_rest_in_peace_static_exiles_a_dying_commander_which_may_then_return_to_the_command_zone(cards):
    s = build(cards, "Test Rest")
    rest = named(s, "Test Rest")
    act(s, "p1", type="move", card_ids=[rest.id], to={"zone": "battlefield"})
    krenko = find(s.state, "Krenko, Mob Boss", "p1")
    act(s, "p1", type="move", card_ids=[krenko.id], to={"zone": "battlefield"})
    permanent(s, "p1", "Mourner", "Enchantment", "Whenever a creature you control dies, you gain 1 life.")
    act(s, "p1", type="set_damage", card_ids=[krenko.id], value=3)
    act(s, "p1", type="pass_priority")
    assert s.state.cards[krenko.id].zone == "p1:exile"  # exiled instead of dying: no "dies" trigger
    d = rules(s).decision  # 903.9a still applies: it was put into exile since the last check
    assert d is not None and d.player == "p1" and d.resume["step"] == "commander_zone"
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["yes"])
    pass_until_stack_empty(s)
    assert s.state.cards[krenko.id].zone == "p1:command" and s.state.players["p1"].life == 40
    replay_matches(s)


def test_reaper_only_exiles_opponents_creatures(cards):
    s = build(cards, "Test Reaper")
    reaper = named(s, "Test Reaper")
    act(s, "p1", type="move", card_ids=[reaper.id], to={"zone": "battlefield"})
    mine = token(s, "p1", "Mine", "1/1")
    bears = to_hand(s, "Forest")  # (a card of theirs that dies: use Bob's Atraxa)
    act(s, "p1", type="move", card_ids=[bears.id], to={"zone": "library"})
    atraxa = find(s.state, "Atraxa, Praetors' Voice", "p2")
    act(s, "p2", type="move", card_ids=[atraxa.id], to={"zone": "battlefield"})
    act(s, "p1", type="set_damage", card_ids=[atraxa.id, mine.id], value=9)
    act(s, "p1", type="pass_priority")
    assert s.state.cards[atraxa.id].zone == "p2:exile"
    assert mine.id not in s.state.cards  # own token: died normally (and ceased to exist)
    d = rules(s).decision
    assert d is not None and d.player == "p2" and d.resume["step"] == "commander_zone"
    replay_matches(s)


# -- parsing: what stays manual --------------------------------------------------------------------
@pytest.mark.parametrize("text", [
    "As ~ enters, you may reveal a Plains or Island card from your hand. If you don't, ~ enters tapped.",
    "~ enters tapped unless a player has 13 or less life.",
    "If a creature an opponent controls would die, exile it instead. When you do, create a 2/2 green Wolf creature token.",
    "Prevent all damage that would be dealt to you and permanents you control this turn by sources you don't control.",
    "~ enters tapped unless you control a Plains or an Island or it's your turn.",
])
def test_wordings_not_understood_stay_manual(text):
    assert not scripts.definitions(ch("X", "Land" if "enters tapped" in text else "Enchantment", text.replace("~", "X")))


def test_coverage_counts_the_new_definitions_as_full(cards):
    for name in ("Test Guildgate", "Test Check Land", "Test Ghost", "Test Rest", "Test Moat", "Test Fog", "Test Ooze"):
        assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name
    assert "enters_tapped" in coverage.SUPPORTED_REPLACEMENTS

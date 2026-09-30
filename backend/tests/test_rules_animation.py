"""Animation effects (agent A2): "~ becomes a N/N … creature until end of turn" and friends, read
against CR 205.1a/205.1b (types set or retained), 105.3 (colors), 613.1d-f / 613.4b / 613.7
(layers and timestamps), 302.6 (summoning sickness), 514.2 (cleanup) and 400.7 (zone changes).
Every scenario also checks that replaying the recorded history reproduces the table exactly."""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from app.rules.combat import attack_problem
from app.rules.creature_types import CREATURE_TYPES
from app.rules.plan import Plan
from tests.game_helpers import act, deck, enable, find
from tests.test_rules_effects import mana, pass_until_stack_empty, replay_matches, run_until, token


def build(cards, extra=()):
    alice = deck(cards, "Krenko, Mob Boss", [(1, "Mutavault"), (1, "Mishra's Factory"), (1, "Treetop Village"),
                                             (1, "Liquimetal Coating"), (1, "Karn's Touch"), (1, "Turn to Frog"),
                                             (1, "Mind Transfer Protocol"), (1, "Cyberdrive Awakener"), (1, "Lifespark Spellbomb"),
                                             (1, "Celestial Colonnade"), (1, "Stuffed Bear"), (1, "Sol Ring"),
                                             (1, "Murder"), (1, "Giant Growth"), *extra, (6, "Forest")])
    bob = deck(cards, "Atraxa, Praetors' Voice", [(10, "Island")])
    state = new_game([PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=bob)], shuffle=False)
    s = GameSession(enable(state), cards=cards)
    act(s, "p1", type="pass_priority")  # → Alice's first main phase
    return s


def to_hand(s, name, pid="p1"):
    card = find(s.state, name, pid)
    if card.zone != f"{pid}:hand":
        act(s, pid, type="move", card_ids=[card.id], to={"zone": "hand"})
    return s.state.cards[card.id]


def to_attackers(s):
    for _ in range(10):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_attackers":
            return
        act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("no declare-attackers step")


def ch(s, cards, card_id):
    return Plan(s.state, "p1", cards, None).ch(s.state.cards[card_id])


def onto_battlefield(s, name, pid="p1"):
    card = find(s.state, name, pid)
    act(s, pid, type="move", card_ids=[card.id], to={"zone": "battlefield"})
    return s.state.cards[card.id]


def test_mutavault_becomes_a_creature_with_all_creature_types_and_is_still_a_land(cards):
    s = build(cards)
    vault = to_hand(s, "Mutavault")
    act(s, "p1", type="play_land", card_id=vault.id)
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=vault.id, ability=1)
    pass_until_stack_empty(s)
    now = ch(s, cards, vault.id)
    assert now.is_creature and now.is_land  # 205.1b: "It's still a land"
    assert now.pt == (2, 2) and now.subtypes == CREATURE_TYPES  # "all creature types"
    assert now.colors == frozenset()  # 105.3: no color named, its colors don't change
    # 302.6: played this turn, so it can't attack yet (a land that became a creature is summoning sick)
    assert "summoning sickness" in (attack_problem(s.state, s.state.cards[vault.id], now) or "")
    log = str(s.view("p2")["log"])
    assert "Mutavault becomes 2/2 creature with all creature types until end of turn" in log
    effects = s.state.rules.effects
    assert {e.layer for e in effects} == {"4", "7b"} and all(e.duration == "end_of_turn" for e in effects)
    assert effects[0].add_types == ["Creature"] and effects[0].set_types is None  # retained (still_a)
    # 514.2: it ends at cleanup
    run_until(s, lambda s: s.state.turn.active_player == "p2")
    later = ch(s, cards, vault.id)
    assert not later.is_creature and later.is_land and later.pt is None and not s.state.rules.effects
    replay_matches(s)


def test_an_animated_land_controlled_since_the_turn_began_attacks(cards):
    s = build(cards)
    vault = to_hand(s, "Mutavault")
    act(s, "p1", type="play_land", card_id=vault.id)
    run_until(s, lambda s: s.state.turn.number == 3 and s.state.turn.phase == "main1")
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=vault.id, ability=1)
    pass_until_stack_empty(s)
    assert attack_problem(s.state, s.state.cards[vault.id], ch(s, cards, vault.id)) is None
    to_attackers(s)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": vault.id, "target": "p2"}])
    run_until(s, lambda s: s.state.players["p2"].life < 40)
    assert s.state.players["p2"].life == 38
    replay_matches(s)


def test_treetop_village_is_a_green_ape_with_trample_and_mishras_factory_pumps_itself(cards):
    s = build(cards)
    village = onto_battlefield(s, "Treetop Village")
    factory = onto_battlefield(s, "Mishra's Factory")
    run_until(s, lambda s: s.state.turn.number == 3 and s.state.turn.phase == "main1")  # (302.6 for its {T} ability)
    mana(s, G=1, C=3)
    act(s, "p1", type="activate_ability", card_id=village.id, ability=2)
    pass_until_stack_empty(s)
    now = ch(s, cards, village.id)
    assert now.pt == (3, 3) and now.colors == frozenset({"G"}) and now.subtypes == frozenset({"Ape"})
    assert now.is_land and now.is_creature and "trample" in now.keywords
    act(s, "p1", type="activate_ability", card_id=factory.id, ability=1)
    pass_until_stack_empty(s)
    now = ch(s, cards, factory.id)
    assert now.types == frozenset({"Land", "Artifact", "Creature"}) and now.subtypes == frozenset({"Assembly-Worker"})
    assert now.pt == (2, 2)
    # "{T}: Target Assembly-Worker creature gets +1/+1": 7c on top of the 7b setter (613.4)
    act(s, "p1", type="activate_ability", card_id=factory.id, ability=2, targets=[factory.id])
    pass_until_stack_empty(s)
    assert ch(s, cards, factory.id).pt == (3, 3)
    replay_matches(s)


def test_setting_effects_apply_in_timestamp_order_under_modifications_and_counters(cards):
    s = build(cards)
    bear = token(s, "p1", "Bear", "2/2", "Flying")
    mana(s, G=1, U=5)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Giant Growth").id, targets=[bear.id])
    pass_until_stack_empty(s)
    act(s, "p1", type="counter", card_ids=[bear.id], kind="+1/+1", delta=1)
    assert ch(s, cards, bear.id).pt == (6, 6)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Mind Transfer Protocol").id, targets=[bear.id])
    pass_until_stack_empty(s)
    now = ch(s, cards, bear.id)
    assert now.pt == (4 + 3 + 1, 5 + 3 + 1)  # 7b base 4/5, then 7c (+3/+3 and the counter), 613.4b-c
    assert now.types == frozenset({"Creature", "Artifact"}) and "flying" in now.keywords  # (no ability lost)
    # a later setting effect wins (613.7): Turn to Frog — 1/1, loses all abilities, a blue Frog
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Turn to Frog").id, targets=[bear.id])
    pass_until_stack_empty(s)
    now = ch(s, cards, bear.id)
    assert now.pt == (1 + 3 + 1, 1 + 3 + 1)
    assert "flying" not in now.keywords and now.abilities == ()
    assert now.colors == frozenset({"U"}) and now.subtypes == frozenset({"Frog"})
    assert now.types == frozenset({"Creature", "Artifact"})  # 205.1a: only creature types were set
    replay_matches(s)


def test_liquimetal_adds_a_type_and_karns_touch_reads_mana_value_once(cards):
    s = build(cards)
    coating = onto_battlefield(s, "Liquimetal Coating")
    ring = onto_battlefield(s, "Sol Ring")
    forest = onto_battlefield(s, "Forest")
    act(s, "p1", type="activate_ability", card_id=coating.id, ability=0, targets=[forest.id])
    pass_until_stack_empty(s)
    now = ch(s, cards, forest.id)
    assert now.types == frozenset({"Land", "Artifact"}) and now.subtypes == frozenset({"Forest"}) and not now.is_creature
    mana(s, U=2)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Karn's Touch").id, targets=[ring.id])
    pass_until_stack_empty(s)
    now = ch(s, cards, ring.id)
    assert now.is_creature and now.pt == (1, 1) and now.types == frozenset({"Artifact", "Creature"})
    assert [a.kind for a in now.abilities] == ["mana"]  # it retains its abilities
    assert s.state.rules.effects[-1].power == 1  # read once, as the effect began (611.2d)
    replay_matches(s)


def test_each_noncreature_artifact_you_control_and_the_effect_survives_saving(cards):
    s = build(cards)
    ring = onto_battlefield(s, "Sol Ring")
    bear = onto_battlefield(s, "Stuffed Bear")
    mana(s, U=1, C=5)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Cyberdrive Awakener").id)
    pass_until_stack_empty(s)
    for cid in (ring.id, bear.id):
        now = ch(s, cards, cid)
        assert now.is_creature and now.pt == (4, 4) and "Artifact" in now.types
    awakener = find(s.state, "Cyberdrive Awakener", "p1")
    assert not any(cid == awakener.id for e in s.state.rules.effects for cid in e.affected)  # it's a creature already
    # the effect is plain data: a save/load round trip keeps it
    from app.game.state import GameState

    copy = GameState.model_validate(s.state.model_dump(mode="json"))
    assert Plan(copy, "p1", cards, None).ch(copy.cards[ring.id]).pt == (4, 4)
    replay_matches(s)


def _murder_animated_vault(cards):
    s = build(cards)
    vault = onto_battlefield(s, "Mutavault")
    token(s, "p1", "Watcher", "1/1", "Whenever a creature you control dies, you gain 1 life.")
    mana(s, C=1, B=3)
    act(s, "p1", type="activate_ability", card_id=vault.id, ability=1)
    pass_until_stack_empty(s)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Murder").id, targets=[vault.id])
    pass_until_stack_empty(s)
    return s, vault


def test_the_animated_land_is_destroyed_and_the_effect_no_longer_applies(cards):
    s, vault = _murder_animated_vault(cards)
    assert s.state.cards[vault.id].zone == "p1:graveyard"
    new = s.state.rules.object_id(vault.id)
    assert not any(new in e.affected for e in s.state.rules.effects)  # 400.7: a new object, unaffected
    assert not ch(s, cards, vault.id).is_creature  # in the graveyard it's just a land card
    replay_matches(s)


@pytest.mark.xfail(strict=True, reason="last known information (ObjectSnapshot) records P/T but not types: an "
                   "animated land or crewed Vehicle that dies isn't seen as a creature by 'dies' triggers (lead: plan/triggers)")
def test_the_animated_land_dies_as_a_creature_for_dies_triggers(cards):
    s, _ = _murder_animated_vault(cards)
    assert s.state.players["p1"].life == 41  # 700.4 / 603.10a: it died as a creature


def test_lifespark_spellbomb_thats_still_a_land_keeps_the_forest_subtype(cards):
    s = build(cards)
    bomb = onto_battlefield(s, "Lifespark Spellbomb")
    forest = onto_battlefield(s, "Forest")
    mana(s, G=1)
    act(s, "p1", type="activate_ability", card_id=bomb.id, ability=0, targets=[forest.id])
    pass_until_stack_empty(s)
    now = ch(s, cards, forest.id)
    assert now.is_creature and now.is_land and now.pt == (3, 3) and now.subtypes == frozenset({"Forest"})
    assert s.state.cards[bomb.id].zone == "p1:graveyard"
    replay_matches(s)


def test_colonnade_and_stuffed_bear_wordings(cards):
    s = build(cards)
    colonnade = onto_battlefield(s, "Celestial Colonnade")
    bear = onto_battlefield(s, "Stuffed Bear")
    mana(s, W=1, U=1, C=5)
    act(s, "p1", type="activate_ability", card_id=colonnade.id, ability=2)
    act(s, "p1", type="activate_ability", card_id=bear.id, ability=0)
    pass_until_stack_empty(s)
    now = ch(s, cards, colonnade.id)
    assert now.pt == (4, 4) and now.colors == frozenset({"W", "U"}) and now.keywords >= {"flying", "vigilance"}
    assert now.subtypes == frozenset({"Elemental"}) and now.is_land
    now = ch(s, cards, bear.id)
    assert now.pt == (4, 4) and now.colors == frozenset({"G"}) and now.types == frozenset({"Artifact", "Creature"})
    assert now.subtypes == frozenset({"Bear"})
    replay_matches(s)


def test_a_land_animated_the_turn_it_was_played_cannot_tap_for_mana(cards):
    from app.rules.casting import can_use_tap_abilities

    s = build(cards)
    vault = to_hand(s, "Mutavault")
    act(s, "p1", type="play_land", card_id=vault.id)
    assert can_use_tap_abilities(s.state, s.state.cards[vault.id], ch(s, cards, vault.id))  # a land: 302.6 doesn't apply
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=vault.id, ability=1)
    pass_until_stack_empty(s)
    # 302.6: now a creature its controller hasn't controlled since the turn began: no {T} abilities
    assert not can_use_tap_abilities(s.state, s.state.cards[vault.id], ch(s, cards, vault.id))
    with pytest.raises(ActionError, match="summoning sickness"):
        act(s, "p1", type="activate_ability", card_id=vault.id, ability=0)


def test_until_your_next_turn_lasts_through_the_opponents_turn(cards):
    s = build(cards)
    forest = onto_battlefield(s, "Forest")
    source = token(s, "p1", "Warden", "1/1",
                   "{T}: Until your next turn, target land you control becomes a 5/5 Elemental creature with haste. It's still a land.")
    run_until(s, lambda s: s.state.turn.number == 3 and s.state.turn.phase == "main1")
    act(s, "p1", type="activate_ability", card_id=source.id, ability=0, targets=[forest.id])
    pass_until_stack_empty(s)
    assert ch(s, cards, forest.id).pt == (5, 5)
    run_until(s, lambda s: s.state.turn.active_player == "p2" and s.state.turn.phase == "main1")
    now = ch(s, cards, forest.id)
    assert now.pt == (5, 5) and now.is_land and now.subtypes == frozenset({"Forest", "Elemental"})  # past cleanup (514.2)
    run_until(s, lambda s: s.state.turn.number == 5)
    assert not ch(s, cards, forest.id).is_creature and not s.state.rules.effects  # 500.4: ended as her turn began
    assert not s.state.cards[forest.id].effects  # (the table marker went with it)
    replay_matches(s)


def test_creature_types_added_in_addition_but_replaced_otherwise(cards):
    s = build(cards)
    elf = token(s, "p1", "Elf", "1/1")  # (Token Creature — Test)
    goblin = token(s, "p1", "Goblin", "1/1")
    crab = token(s, "p1", "Crabber", "1/1",
                 "{T}: Until end of turn, target creature becomes a blue Crab in addition to its other types.")
    coward = token(s, "p1", "Cower", "1/1", "{T}: Target creature becomes a Coward until end of turn.")
    run_until(s, lambda s: s.state.turn.number == 3 and s.state.turn.phase == "main1")
    act(s, "p1", type="activate_ability", card_id=crab.id, ability=0, targets=[elf.id])
    pass_until_stack_empty(s)
    act(s, "p1", type="activate_ability", card_id=coward.id, ability=0, targets=[goblin.id])
    pass_until_stack_empty(s)
    assert ch(s, cards, elf.id).subtypes == frozenset({"Test", "Crab"})  # 205.1b: every prior subtype retained
    assert ch(s, cards, elf.id).colors == frozenset({"U"})  # 105.3: "in addition to its other types" isn't colors
    assert ch(s, cards, goblin.id).subtypes == frozenset({"Coward"})  # 205.1a: the new creature type replaces
    replay_matches(s)


def test_gideon_becomes_a_creature_thats_still_a_planeswalker_and_damage_to_him_is_prevented(cards):
    s = build(cards, extra=[(1, "Gideon Jura"), (1, "Lightning Bolt")])
    gideon = onto_battlefield(s, "Gideon Jura")
    act(s, "p1", type="counter", card_ids=[gideon.id], kind="loyalty", delta=6)
    act(s, "p1", type="activate_ability", card_id=gideon.id, ability=2)  # "0: Until end of turn, …"
    pass_until_stack_empty(s)
    now = ch(s, cards, gideon.id)
    assert now.types == frozenset({"Planeswalker", "Creature"}) and now.pt == (6, 6)
    assert now.subtypes == frozenset({"Gideon", "Human", "Soldier"})  # 205.1b: still a planeswalker, keeps "Gideon"
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Lightning Bolt").id, targets=[gideon.id])
    pass_until_stack_empty(s)
    assert s.state.cards[gideon.id].zone == "p1:battlefield"
    assert s.state.cards[gideon.id].counters.get("loyalty") == 6 and not s.state.cards[gideon.id].damage  # 615: prevented
    run_until(s, lambda s: s.state.turn.active_player == "p2")
    assert not ch(s, cards, gideon.id).is_creature  # 514.2
    replay_matches(s)


def test_has_base_power_and_toughness_is_layer_7b_only(cards):
    s = build(cards)
    bear = token(s, "p1", "Bear", "2/2", "Flying")
    shrinker = token(s, "p1", "Shrinker", "1/1", "{T}: Target creature has base power and toughness 0/1 until end of turn.")
    run_until(s, lambda s: s.state.turn.number == 3 and s.state.turn.phase == "main1")
    act(s, "p1", type="counter", card_ids=[bear.id], kind="+1/+1", delta=2)
    act(s, "p1", type="activate_ability", card_id=shrinker.id, ability=0, targets=[bear.id])
    pass_until_stack_empty(s)
    now = ch(s, cards, bear.id)
    assert now.pt == (2, 3) and "flying" in now.keywords and now.subtypes == frozenset({"Test"})  # 7b, then 7c counters
    assert [e.layer for e in s.state.rules.effects] == ["7b"]
    replay_matches(s)

"""Wave 53C: block events (CR 509.1, 509.3, 509.5, 603.2) and attaching to a target (701.3, 301.5, 303.4), real Oracle text
(tests/fixtures/wave53c_cards.json, from data/cards.sqlite). Every scenario checks the replay and a save and a load.

* 509.3c-d: "Whenever equipped creature becomes blocked, it deals 2 damage to each creature blocking it" (Trailblazer's Torch): "it" is the creature that
  became blocked, the blockers are the creatures blocking it as the ability resolves.
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import coverage
from app.rules.plan import Plan
from tests.game_helpers import act
from tests.test_rules_conditionals import token_of
from tests.test_rules_wave34b_activated import activate, ask
from tests.wave53c_kit import (
    alive,
    attach,
    bob_swings,
    cast_now,
    check,
    combat_step,
    creature,
    in_play,
    main_step,
    on_field,
    open_repo,
    pool,
    priority_to,
    sandbox,
    settle,
    swing,
    to_postcombat,
    until,
    zone_of,
)


@pytest.fixture()
def cards(settings):
    yield from open_repo(settings)


def full(cards, name):
    return coverage.of_card_data(cards.resolve(name)).level == "FULL"


def test_torch_deals_two_to_each_creature_blocking_the_equipped_creature(cards):
    s = sandbox(cards, "Trailblazer's Torch")
    torch = on_field(s, "Trailblazer's Torch")
    brute = creature(s, "p1", "Brute", "5/5")
    a = creature(s, "p2", "Guard A", "2/9")
    b = creature(s, "p2", "Guard B", "1/2")
    c = creature(s, "p2", "Bystander", "2/2")
    attach(s, torch, brute)
    combat_step(s)
    swing(s, [brute], [(a, brute), (b, brute)])
    settle(s)
    assert s.state.cards[a.id].damage == 2 and not alive(s, b)  # the Torch's 2 (Guard B, toughness 2, died to it), before combat damage
    assert s.state.cards[c.id].damage == 0
    to_postcombat(s)
    assert s.state.cards[a.id].damage == 2 + 5  # then Brute's 5
    check(s)


def test_halfheart_sacrifices_the_blocked_goblin_and_it_deals_four_to_each_blocker(cards):
    s = sandbox(cards, "Ib Halfheart, Goblin Tactician")
    on_field(s, "Ib Halfheart, Goblin Tactician")
    gob = creature(s, "p1", "Sneak", "1/1", type_line="Token Creature — Goblin")
    a = creature(s, "p2", "Guard A", "1/9")
    b = creature(s, "p2", "Guard B", "1/9")
    combat_step(s)
    swing(s, [gob], [(a, gob), (b, gob)])
    settle(s)
    assert not alive(s, gob)  # sacrificed on becoming blocked
    assert s.state.cards[a.id].damage == 4 and s.state.cards[b.id].damage == 4  # it dealt 4 to each creature that was blocking it
    check(s)


def test_halfheart_leaves_a_blocked_non_goblin_alone(cards):
    s = sandbox(cards, "Ib Halfheart, Goblin Tactician")
    on_field(s, "Ib Halfheart, Goblin Tactician")
    bear = creature(s, "p1", "Bear", "2/2", type_line="Token Creature — Bear")
    a = creature(s, "p2", "Guard A", "1/9")
    combat_step(s)
    swing(s, [bear], [(a, bear)])
    settle(s)
    assert alive(s, bear) and s.state.cards[a.id].damage == 0  # nothing happened on becoming blocked
    to_postcombat(s)
    assert s.state.cards[a.id].damage == 2
    check(s)


def test_raptor_makes_defending_player_sacrifice_one_blocker_of_their_choice(cards):
    s = sandbox(cards, "Labyrinth Raptor")
    on_field(s, "Labyrinth Raptor")
    menace = creature(s, "p1", "Menacer", "3/3", text="Menace")
    a = creature(s, "p2", "Guard A", "1/9")
    b = creature(s, "p2", "Guard B", "1/9")
    c = creature(s, "p2", "Bystander", "1/9")
    combat_step(s)
    swing(s, [menace], [(a, menace), (b, menace)])
    d = ask(s)
    assert d is not None and d.player == "p2" and {o.id for o in d.options} == {a.id, b.id}  # only a creature blocking it, chosen by the defender
    from tests.game_helpers import act

    act(s, "p2", type="choose", decision_id=d.id, option_ids=[b.id])
    settle(s)
    assert not alive(s, b) and alive(s, a) and alive(s, c)
    check(s)


def test_raptor_ignores_a_creature_without_menace(cards):
    s = sandbox(cards, "Labyrinth Raptor")
    on_field(s, "Labyrinth Raptor")
    plain = creature(s, "p1", "Plain", "3/3")
    a = creature(s, "p2", "Guard A", "1/9")
    combat_step(s)
    swing(s, [plain], [(a, plain)])
    settle(s)
    assert s.state.rules.decision is None and alive(s, a)
    check(s)


def test_abu_jafar_dying_destroys_every_creature_blocking_it(cards):
    s = sandbox(cards, "Abu Ja'far")
    abu = on_field(s, "Abu Ja'far")
    a = creature(s, "p2", "Guard A", "1/3")
    b = creature(s, "p2", "Guard B", "1/3")
    c = creature(s, "p2", "Bystander", "1/3")
    combat_step(s)
    swing(s, [abu], [(a, abu), (b, abu)])
    to_postcombat(s)
    assert not alive(s, abu) and not alive(s, a) and not alive(s, b) and alive(s, c)  # the blockers died with it (they were blocking it as it died)
    check(s)


def test_abu_jafar_dying_as_a_blocker_destroys_the_creature_it_blocked(cards):
    s = sandbox(cards, "Abu Ja'far")
    abu = on_field(s, "Abu Ja'far")
    brute = creature(s, "p2", "Brute", "5/5")
    other = creature(s, "p2", "Other", "1/9")
    combat_step(s)
    bob_swings(s, [brute, other], [(abu, brute)])  # Abu blocks Brute and dies, so Brute (blocked by it) is destroyed
    to_postcombat(s)
    assert not alive(s, abu) and not alive(s, brute) and alive(s, other)
    check(s)


def test_alms_beast_gives_lifelink_to_the_creatures_blocking_or_blocked_by_it(cards):
    s = sandbox(cards, "Alms Beast")
    beast = on_field(s, "Alms Beast")
    guard = creature(s, "p2", "Guard", "2/9")
    idle = creature(s, "p2", "Idle", "2/9")
    combat_step(s)
    swing(s, [beast], [(guard, beast)])
    to_postcombat(s)
    assert s.state.players["p2"].life == 40 + 2  # the blocker has lifelink (702.15b): its 2 damage to the Beast
    assert s.state.players["p1"].life == 40  # the Beast itself does not
    check(s)
    assert "lifelink" not in Plan(s.state, "p1", s.cards, None).ch(s.state.cards[idle.id]).keywords  # not blocking it, no lifelink


def test_alms_beast_blocking_gives_the_attacker_lifelink(cards):
    s = sandbox(cards, "Alms Beast")
    beast = on_field(s, "Alms Beast")
    raider = creature(s, "p2", "Raider", "3/9")
    combat_step(s)
    bob_swings(s, [raider], [(beast, raider)])
    to_postcombat(s)
    assert s.state.players["p2"].life == 40 + 3  # the creature blocked by the Beast has lifelink
    check(s)


def test_armasaur_deals_its_toughness_to_a_creature_blocking_it_only(cards):
    s = sandbox(cards, "Steadfast Armasaur")
    saur = on_field(s, "Steadfast Armasaur")
    guard = creature(s, "p2", "Guard", "0/9")
    idle = creature(s, "p2", "Idle", "0/9")
    combat_step(s)
    swing(s, [saur], [(guard, saur)])
    pool(s, W=1, C=1)
    with pytest.raises(ActionError):
        activate(s, "p1", saur, "damage equal", targets=[idle.id])  # not blocking it
    activate(s, "p1", saur, "damage equal", targets=[guard.id])
    settle(s)
    assert s.state.cards[guard.id].damage >= 3
    check(s)


def test_vortex_elemental_takes_itself_and_the_blockers_to_the_libraries(cards):
    s = sandbox(cards, "Vortex Elemental", p2=("Grizzly Bears",))
    vortex = on_field(s, "Vortex Elemental")
    bears = on_field(s, "Grizzly Bears", "p2")
    idle = creature(s, "p2", "Idle", "2/2")
    combat_step(s)
    swing(s, [vortex], [(bears, vortex)])
    pool(s, U=1)
    activate(s, "p1", vortex, "Put")
    settle(s)
    assert zone_of(s, vortex) == "p1:library" and zone_of(s, bears) == "p2:library" and alive(s, idle)
    check(s)


def test_trial_returns_the_attacker_and_its_blockers_to_their_owners_hands(cards):
    s = sandbox(cards, "Grizzly Bears", "Trial // Error", p2=("Grizzly Bears",))
    bears = on_field(s, "Grizzly Bears")
    guard = on_field(s, "Grizzly Bears", "p2")
    idle = creature(s, "p2", "Idle", "2/2")
    combat_step(s)
    swing(s, [bears], [(guard, bears)])
    trial = in_play(s, "Trial // Error")
    act(s, "p1", type="move", card_ids=[trial.id], to={"zone": "hand"})
    pool(s, W=1, U=1)
    act(s, "p1", type="cast_spell", card_id=trial.id, targets=[bears.id])
    settle(s)
    assert zone_of(s, guard) == "p2:hand" and zone_of(s, bears) == "p1:battlefield" and alive(s, idle)  # the creatures blocking it, not the target
    check(s)


def test_trial_on_the_blocker_returns_the_attacker_it_blocks(cards):
    s = sandbox(cards, "Grizzly Bears", "Trial // Error", p2=("Grizzly Bears",))
    bears = on_field(s, "Grizzly Bears")
    guard = on_field(s, "Grizzly Bears", "p2")
    combat_step(s)
    swing(s, [bears], [(guard, bears)])
    trial = in_play(s, "Trial // Error")
    act(s, "p1", type="move", card_ids=[trial.id], to={"zone": "hand"})
    pool(s, W=1, U=1)
    act(s, "p1", type="cast_spell", card_id=trial.id, targets=[guard.id])
    settle(s)
    assert zone_of(s, bears) == "p1:hand" and zone_of(s, guard) == "p2:battlefield"  # the creature it was blocking
    check(s)


# -- "blocked or was blocked by X this turn" (509.1g) --
def legend_vs_guards(s):
    legend = token_of(s, "p1", "Legend", "Legendary Token Creature — Human", "3/3")
    plain = creature(s, "p1", "Plain", "3/3")
    g1 = creature(s, "p2", "Guard One", "0/9")
    g2 = creature(s, "p2", "Guard Two", "0/9")
    idle = creature(s, "p2", "Idle", "0/9")
    combat_step(s)
    swing(s, [legend, plain], [(g1, legend), (g2, plain)])
    return g1, g2, idle


def test_you_cannot_pass_destroys_a_creature_that_blocked_a_legendary_creature(cards):
    s = sandbox(cards, "You Cannot Pass!")
    g1, g2, idle = legend_vs_guards(s)
    with pytest.raises(ActionError):
        cast_now(s, "You Cannot Pass!", [g2], W=1)  # blocked a creature that is not legendary
    with pytest.raises(ActionError):
        cast_now(s, "You Cannot Pass!", [idle], W=1)  # never in a block
    cast_now(s, "You Cannot Pass!", [g1], W=1)
    assert not alive(s, g1) and alive(s, g2) and alive(s, idle)
    check(s)


def test_time_to_reflect_exiles_a_creature_that_blocked_a_zombie(cards):
    s = sandbox(cards, "Time to Reflect")
    zombie = token_of(s, "p1", "Shambler", "Token Creature — Zombie", "3/3")
    plain = creature(s, "p1", "Plain", "3/3")
    g1 = creature(s, "p2", "Guard One", "0/9")
    g2 = creature(s, "p2", "Guard Two", "0/9")
    combat_step(s)
    swing(s, [zombie, plain], [(g1, zombie), (g2, plain)])
    with pytest.raises(ActionError):
        cast_now(s, "Time to Reflect", [g2], W=1)
    cast_now(s, "Time to Reflect", [g1], W=1)
    assert zone_of(s, g1) is None or zone_of(s, g1) != "p2:battlefield"
    assert alive(s, g2)
    check(s)


def test_ride_down_destroys_a_blocker_and_the_creatures_it_blocked_gain_trample(cards):
    s = sandbox(cards, "Ride Down")
    a1 = creature(s, "p1", "Raider One", "5/5")
    a2 = creature(s, "p1", "Raider Two", "2/2")
    g1 = creature(s, "p2", "Guard One", "1/9")
    g2 = creature(s, "p2", "Guard Two", "1/9")
    combat_step(s)
    swing(s, [a1, a2], [(g1, a1), (g2, a2)])
    cast_now(s, "Ride Down", [g1], R=1, W=1)
    ch = lambda c: Plan(s.state, "p1", s.cards, None).ch(s.state.cards[c.id])  # noqa: E731
    assert not alive(s, g1) and "trample" in ch(a1).keywords and "trample" not in ch(a2).keywords
    to_postcombat(s)
    assert s.state.players["p2"].life == 40 - 5  # trample: a blocked creature whose blocker is gone assigns all its damage to the player (702.19e)
    check(s)


# -- "attached to that creature" (301.5, 303.4) --
def test_treefolk_mystic_destroys_the_auras_on_the_creature_it_blocks_or_is_blocked_by(cards):
    s = sandbox(cards, "Treefolk Mystic", "Laccolith Rig", "Kjeldoran Pride")
    mystic = on_field(s, "Treefolk Mystic")
    rig = on_field(s, "Laccolith Rig")
    pride = on_field(s, "Kjeldoran Pride")
    guard = creature(s, "p2", "Guard", "0/9")
    bystander = creature(s, "p2", "Bystander", "0/9")
    attach(s, rig, guard, "p1")
    attach(s, pride, bystander, "p1")
    combat_step(s)
    swing(s, [mystic], [(guard, mystic)])
    settle(s)
    assert zone_of(s, rig) == "p1:graveyard" and zone_of(s, pride) == "p1:battlefield"  # only the Aura on the creature that blocked it
    check(s)


def test_corrosive_ooze_destroys_the_equipment_of_the_equipped_creature_it_blocks_at_end_of_combat(cards):
    s = sandbox(cards, "Corrosive Ooze", "Trailblazer's Torch", "Mirror Shield", p2=("Corrosive Ooze",))
    torch = on_field(s, "Trailblazer's Torch")
    shield = on_field(s, "Mirror Shield")
    brute = creature(s, "p1", "Brute", "1/1")
    ooze = on_field(s, "Corrosive Ooze", "p2")
    attach(s, torch, brute)
    attach(s, shield, brute)
    combat_step(s)
    swing(s, [brute], [(ooze, brute)])
    settle(s)
    assert zone_of(s, torch) == "p1:battlefield" and zone_of(s, shield) == "p1:battlefield"  # not yet: at end of combat
    to_postcombat(s)
    assert zone_of(s, torch) == "p1:graveyard" and zone_of(s, shield) == "p1:graveyard"
    check(s)


def test_corrosive_ooze_ignores_an_unequipped_creature(cards):
    s = sandbox(cards, "Trailblazer's Torch", p2=("Corrosive Ooze",))
    torch = on_field(s, "Trailblazer's Torch")
    plain = creature(s, "p1", "Plain", "1/1")
    other = creature(s, "p1", "Other", "1/1")
    ooze = on_field(s, "Corrosive Ooze", "p2")
    attach(s, torch, other)
    combat_step(s)
    swing(s, [plain], [(ooze, plain)])
    to_postcombat(s)
    assert zone_of(s, torch) == "p1:battlefield"
    check(s)


def test_strip_bare_destroys_the_auras_and_equipment_attached_to_the_target(cards):
    s = sandbox(cards, "Strip Bare", "Laccolith Rig", "Trailblazer's Torch", "Mirror Shield")
    rig = on_field(s, "Laccolith Rig")
    torch = on_field(s, "Trailblazer's Torch")
    shield = on_field(s, "Mirror Shield")
    target = creature(s, "p1", "Target", "2/2")
    other = creature(s, "p1", "Other", "2/2")
    attach(s, rig, target)
    attach(s, torch, target)
    attach(s, shield, other)
    main_step(s)
    cast_now(s, "Strip Bare", [target], W=1)
    assert zone_of(s, rig) == "p1:graveyard" and zone_of(s, torch) == "p1:graveyard" and zone_of(s, shield) == "p1:battlefield"
    assert alive(s, target)
    check(s)


# -- the end of combat step: "destroy all creatures that blocked or were blocked by it this turn" --
def test_gaze_of_the_gorgon_regenerates_and_destroys_what_blocked_or_was_blocked_by_it_at_end_of_combat(cards):
    s = sandbox(cards, "Gaze of the Gorgon")
    brute = creature(s, "p1", "Brute", "0/5")
    g1 = creature(s, "p2", "Guard One", "3/9")
    g2 = creature(s, "p2", "Guard Two", "2/9")
    idle = creature(s, "p2", "Idle", "3/9")
    combat_step(s)
    swing(s, [brute], [(g1, brute), (g2, brute)])
    cast_now(s, "Gaze of the Gorgon", [brute], B=1, C=3)
    assert alive(s, g1) and alive(s, g2)  # not before the end of combat
    to_postcombat(s)
    assert alive(s, brute) and not alive(s, g1) and not alive(s, g2) and alive(s, idle)  # Brute regenerated; both blockers destroyed
    check(s)


def test_venomous_breath_destroys_what_blocked_or_was_blocked_by_the_chosen_creature(cards):
    s = sandbox(cards, "Venomous Breath")
    brute = creature(s, "p1", "Brute", "1/1")
    other = creature(s, "p1", "Other", "1/1")
    guard = creature(s, "p2", "Guard", "0/9")
    guard2 = creature(s, "p2", "Guard Two", "0/9")
    combat_step(s)
    swing(s, [brute, other], [(guard, brute), (guard2, other)])
    cast_now(s, "Venomous Breath", [guard], G=1, C=3)
    to_postcombat(s)
    assert alive(s, guard) and not alive(s, brute) and alive(s, other) and alive(s, guard2)
    check(s)


def test_glyph_of_doom_targets_only_a_wall_and_destroys_what_it_blocked(cards):
    s = sandbox(cards, "Glyph of Doom")
    brute = creature(s, "p1", "Brute", "1/1")
    wall = token_of(s, "p2", "Barrier", "Token Creature — Wall", "0/9")
    other = creature(s, "p2", "Other", "0/9")
    combat_step(s)
    swing(s, [brute], [(wall, brute)])
    with pytest.raises(ActionError):
        cast_now(s, "Glyph of Doom", [other], B=1)
    cast_now(s, "Glyph of Doom", [wall], B=1)
    to_postcombat(s)
    assert alive(s, wall) and not alive(s, brute)
    check(s)


def test_triton_tactics_taps_what_the_targets_blocked_and_it_stays_tapped(cards):
    s = sandbox(cards, "Triton Tactics")
    b1 = creature(s, "p1", "Blocker One", "0/2")
    b2 = creature(s, "p1", "Blocker Two", "0/2")
    r1 = creature(s, "p2", "Raider One", "1/1", text="Vigilance")
    r2 = creature(s, "p2", "Raider Two", "1/1", text="Vigilance")
    r3 = creature(s, "p2", "Raider Three", "1/1", text="Vigilance")
    combat_step(s)
    bob_swings(s, [r1, r2, r3], [(b1, r1), (b2, r2)])
    cast_now(s, "Triton Tactics", [b1], counts=[1], U=1)  # one target: Blocker One only
    st = s.state.cards
    assert not st[r1.id].tapped
    to_postcombat(s)
    assert st[r1.id].tapped and not st[r2.id].tapped and not st[r3.id].tapped  # r1 was blocked by a target: tapped at end of combat
    until(s, lambda s: s.state.turn.number == 4 and s.state.turn.phase == "main1", limit=300)
    assert st[r1.id].tapped and not st[r2.id].tapped  # and it did not untap in its controller's next untap step
    check(s)


def test_sea_troll_regenerates_only_after_blocking_or_being_blocked_by_a_blue_creature(cards):
    s = sandbox(cards, "Sea Troll")
    troll = on_field(s, "Sea Troll")
    blue = token_of(s, "p2", "Merman", "Token Creature — Merfolk", "1/1", colors=["U"])
    red = token_of(s, "p2", "Imp", "Token Creature — Imp", "1/1", colors=["R"])
    combat_step(s)
    bob_swings(s, [blue, red], [(troll, red)])
    pool(s, U=1)
    priority_to(s, "p1")
    with pytest.raises(ActionError):
        activate(s, "p1", troll, "Regenerate")  # it blocked a red creature, not a blue one
    check(s)


def test_sea_troll_that_blocked_a_blue_creature_may_regenerate(cards):
    s = sandbox(cards, "Sea Troll")
    troll = on_field(s, "Sea Troll")
    blue = token_of(s, "p2", "Merman", "Token Creature — Merfolk", "1/1", colors=["U"])
    combat_step(s)
    bob_swings(s, [blue], [(troll, blue)])
    pool(s, U=1)
    priority_to(s, "p1")
    activate(s, "p1", troll, "Regenerate")
    settle(s)
    to_postcombat(s)
    assert alive(s, troll) and not alive(s, blue)  # regenerated from Merman's lethal damage; Merman took 2
    check(s)


def test_street_sweeper_destroys_the_auras_on_a_target_land_when_it_attacks(cards):
    s = sandbox(cards, "Street Sweeper", "Wild Growth", "Forest")
    sweeper = on_field(s, "Street Sweeper")
    growth = on_field(s, "Wild Growth")
    forest = on_field(s, "Forest")
    attach(s, growth, forest)
    assert s.state.cards[growth.id].attached_to == forest.id
    combat_step(s)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": sweeper.id, "target": "p2"}])
    for _ in range(6):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_blockers":
            break
        if d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][:1])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    assert zone_of(s, growth) == "p1:graveyard"
    check(s)


def test_scarab_of_the_unseen_returns_the_auras_to_their_owners_hands_and_draws_next_upkeep(cards):
    s = sandbox(cards, "Scarab of the Unseen", p2=("Kjeldoran Pride",))
    scarab = on_field(s, "Scarab of the Unseen")
    pride = on_field(s, "Kjeldoran Pride", "p2")
    mine = creature(s, "p1", "Mine", "2/2")
    attach(s, pride, mine, "p2")
    hand = len([c for c in s.state.cards.values() if c.zone == "p1:hand"])
    main_step(s)
    activate(s, "p1", scarab, "Return", targets=[mine.id])
    settle(s)
    assert zone_of(s, pride) == "p2:hand" and zone_of(s, scarab) == "p1:graveyard"
    until(s, lambda s: s.state.turn.number == 2 and s.state.turn.phase == "main1", limit=100)
    settle(s)
    assert len([c for c in s.state.cards.values() if c.zone == "p1:hand"]) == hand + 1  # drawn at the next turn's upkeep (Bob's)
    check(s)


# -- a trigger about the creature an Aura / Equipment is attached to, and the creature on the other side (509.3b, 509.3d) --
def test_dead_iron_sledge_destroys_both_creatures_when_the_equipped_creature_is_blocked(cards):
    s = sandbox(cards, "Dead-Iron Sledge")
    sledge = on_field(s, "Dead-Iron Sledge")
    brute = creature(s, "p1", "Brute", "2/2")
    guard = creature(s, "p2", "Guard", "1/1")
    bystander = creature(s, "p2", "Bystander", "1/1")
    attach(s, sledge, brute)
    combat_step(s)
    swing(s, [brute], [(guard, brute)])
    settle(s)
    assert not alive(s, brute) and not alive(s, guard) and alive(s, bystander)  # before combat damage
    check(s)


def test_dead_iron_sledge_destroys_both_when_the_equipped_creature_blocks(cards):
    s = sandbox(cards, "Dead-Iron Sledge")
    sledge = on_field(s, "Dead-Iron Sledge")
    wall = creature(s, "p1", "Wall", "0/6")
    raider = creature(s, "p2", "Raider", "1/1")
    attach(s, sledge, wall)
    combat_step(s)
    bob_swings(s, [raider], [(wall, raider)])
    settle(s)
    assert not alive(s, wall) and not alive(s, raider)
    check(s)


def test_mirror_shield_destroys_a_deathtouch_creature_that_blocks_the_equipped_creature(cards):
    s = sandbox(cards, "Mirror Shield")
    shield = on_field(s, "Mirror Shield")
    brute = creature(s, "p1", "Brute", "2/2")
    snake = creature(s, "p2", "Snake", "1/1", text="Deathtouch")
    plain = creature(s, "p2", "Plain", "1/1")
    attach(s, shield, brute)
    combat_step(s)
    swing(s, [brute], [(snake, brute), (plain, brute)])
    settle(s)
    assert not alive(s, snake) and alive(s, plain) and alive(s, brute)  # the deathtouch creature is destroyed as it blocks; the plain one is not
    check(s)


def test_mirror_shield_destroys_a_deathtouch_creature_the_equipped_creature_blocks(cards):
    s = sandbox(cards, "Mirror Shield")
    shield = on_field(s, "Mirror Shield")
    wall = creature(s, "p1", "Wall", "0/5")
    snake = creature(s, "p2", "Snake", "1/1", text="Deathtouch")
    plain = creature(s, "p2", "Plain", "1/1")
    attach(s, shield, wall)
    combat_step(s)
    bob_swings(s, [snake, plain], [(wall, snake)])
    settle(s)
    assert not alive(s, snake) and alive(s, plain) and alive(s, wall)  # the equipped creature blocked a creature with deathtouch
    check(s)


def test_hedron_blade_gives_deathtouch_when_blocked_by_colorless_creatures(cards):
    s = sandbox(cards, "Hedron Blade")
    blade = on_field(s, "Hedron Blade")
    brute = creature(s, "p1", "Brute", "2/2")
    robot = token_of(s, "p2", "Robot", "Token Artifact Creature — Robot", "1/9")
    other = creature(s, "p1", "Other", "2/2")
    green = token_of(s, "p2", "Elf", "Token Creature — Elf", "1/9", colors=["G"])
    attach(s, blade, brute)
    combat_step(s)
    swing(s, [brute, other], [(robot, brute), (green, other)])
    settle(s)
    ch = lambda c: Plan(s.state, "p1", s.cards, None).ch(s.state.cards[c.id])  # noqa: E731
    assert "deathtouch" in ch(brute).keywords and "deathtouch" not in ch(other).keywords
    check(s)


def test_dream_fighter_and_the_creature_it_blocks_phase_out(cards):
    s = sandbox(cards, "Dream Fighter")
    fighter = on_field(s, "Dream Fighter")
    raider = creature(s, "p2", "Raider", "3/3")
    other = creature(s, "p2", "Other", "3/3")
    combat_step(s)
    bob_swings(s, [raider, other], [(fighter, raider)])
    settle(s)
    assert zone_of(s, fighter) == "p1:phased" and zone_of(s, raider) == "p2:phased" and zone_of(s, other) == "p2:battlefield"
    check(s)


def test_giant_shark_gets_bigger_against_a_creature_that_was_dealt_damage(cards):
    s = sandbox(cards, "Giant Shark", "Lightning Bolt", "Island", p2=("Island",))
    on_field(s, "Island", "p2")
    on_field(s, "Island")  # (the Shark is sacrificed when its controller controls no Island)
    shark = on_field(s, "Giant Shark")
    hurt = creature(s, "p2", "Hurt", "0/9")
    creature(s, "p2", "Fresh", "0/9")  # (a second possible blocker, not dealt damage)
    combat_step(s)
    swing(s, [shark], [(hurt, shark)], before=lambda: cast_now(s, "Lightning Bolt", [hurt], R=1))
    settle(s)
    ch = Plan(s.state, "p1", s.cards, None).ch(s.state.cards[shark.id])
    assert ch.pt == (6, 4) and "trample" in ch.keywords
    check(s)


def test_giant_shark_is_not_bigger_against_a_fresh_creature(cards):
    s = sandbox(cards, "Giant Shark", "Island", p2=("Island",))
    on_field(s, "Island", "p2")
    on_field(s, "Island")
    shark = on_field(s, "Giant Shark")
    fresh = creature(s, "p2", "Fresh", "0/9")
    combat_step(s)
    swing(s, [shark], [(fresh, shark)])
    settle(s)
    ch = Plan(s.state, "p1", s.cards, None).ch(s.state.cards[shark.id])
    assert ch.pt == (4, 4) and "trample" not in ch.keywords
    check(s)


def test_seifer_gives_deathtouch_to_an_attacker_blocked_by_two_or_more_creatures(cards):
    s = sandbox(cards, "Seifer, Balamb Rival")
    on_field(s, "Seifer, Balamb Rival")
    one = creature(s, "p1", "Single", "2/2")
    two = creature(s, "p1", "Double", "2/2")
    g1 = creature(s, "p2", "Guard One", "0/9")
    g2 = creature(s, "p2", "Guard Two", "0/9")
    g3 = creature(s, "p2", "Guard Three", "0/9")
    combat_step(s)
    swing(s, [one, two], [(g1, one), (g2, two), (g3, two)])
    settle(s)
    ch = lambda c: Plan(s.state, "p1", s.cards, None).ch(s.state.cards[c.id])  # noqa: E731
    assert "deathtouch" in ch(two).keywords and "deathtouch" not in ch(one).keywords
    check(s)


def test_laccolith_rig_lets_the_blocked_creature_deal_damage_and_then_assign_none(cards):
    s = sandbox(cards, "Laccolith Rig")
    rig = on_field(s, "Laccolith Rig")
    brute = creature(s, "p1", "Brute", "4/4")
    guard = creature(s, "p2", "Guard", "0/9")
    victim = creature(s, "p2", "Victim", "0/3")
    attach(s, rig, brute)
    combat_step(s)
    swing(s, [brute], [(guard, brute)])
    for _ in range(8):
        d = s.state.rules.decision
        if d is None:
            if not alive(s, victim):
                break
            act(s, s.state.rules.priority, type="pass_priority")
        elif d.kind == "confirm":
            act(s, d.player, type="choose", decision_id=d.id, option_ids=["yes"])
        else:  # the target of the trigger: only the victim
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[victim.id])
    settle(s)
    assert not alive(s, victim)
    to_postcombat(s)
    assert s.state.cards[guard.id].damage == 0  # Brute assigned no combat damage
    check(s)


def test_barreling_attack_pumps_for_each_creature_blocking_it_when_it_becomes_blocked(cards):
    s = sandbox(cards, "Barreling Attack")
    brute = creature(s, "p1", "Brute", "2/2")
    other = creature(s, "p1", "Other", "2/2")
    g1 = creature(s, "p2", "Guard One", "0/9")
    g2 = creature(s, "p2", "Guard Two", "0/9")
    g3 = creature(s, "p2", "Guard Three", "0/9")
    combat_step(s)
    swing(s, [brute, other], [(g1, brute), (g2, brute), (g3, other)], before=lambda: cast_now(s, "Barreling Attack", [brute], R=2, C=2))
    settle(s)
    pl = Plan(s.state, "p1", s.cards, None)
    assert pl.ch(s.state.cards[brute.id]).pt == (4, 4) and "trample" in pl.ch(s.state.cards[brute.id]).keywords  # +1/+1 for each of its two blockers
    assert pl.ch(s.state.cards[other.id]).pt == (2, 2)
    check(s)


# -- "can't be blocked by …" (509.1b) --
def test_black_gate_picks_a_player_with_the_most_life_and_their_creatures_cannot_block(cards):
    s = sandbox(cards, "The Black Gate", p2=("Grizzly Bears",))
    gate = on_field(s, "The Black Gate")
    brute = creature(s, "p1", "Brute", "3/3")
    bears = on_field(s, "Grizzly Bears", "p2")
    main_step(s)
    pool(s, B=1, C=1)
    activate(s, "p1", gate, "Choose", targets=[brute.id])  # both players have 40 life: a tie, Alice chooses
    d = ask(s)
    assert {o.id for o in d.options} == {"p1", "p2"}
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["p2"])
    settle(s)
    until(s, lambda s: s.state.turn.phase == "declare_attackers", limit=20)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": brute.id, "target": "p2"}])
    for _ in range(6):
        if s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_blockers":
            break
        act(s, s.state.rules.priority, type="pass_priority")
    with pytest.raises(ActionError, match="can't be blocked"):
        act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": bears.id, "attacker_id": brute.id}])  # Bob has the most life: his creatures can't block it
    act(s, "p2", type="declare_blockers", blocks=[])
    check(s)


def test_black_gate_with_one_player_ahead_asks_nothing(cards):
    s = sandbox(cards, "The Black Gate", p2=("Grizzly Bears",))
    gate = on_field(s, "The Black Gate")
    brute = creature(s, "p1", "Brute", "3/3")
    bears = on_field(s, "Grizzly Bears", "p2")
    act(s, "p1", type="set_life", player="p2", value=30)
    main_step(s)
    pool(s, B=1, C=1)
    activate(s, "p1", gate, "Choose", targets=[brute.id])
    settle(s)
    assert s.state.rules.decision is None  # Alice has the most life: no choice, and her own creatures are not the blockers
    until(s, lambda s: s.state.turn.phase == "declare_attackers", limit=20)
    swing(s, [brute], [(bears, brute)])  # Bob's creature may block
    check(s)


def test_legion_loyalist_battalion_gives_first_strike_trample_and_evades_tokens(cards):
    s = sandbox(cards, "Legion Loyalist", p2=("Grizzly Bears",))
    loyalist = on_field(s, "Legion Loyalist")
    a = creature(s, "p1", "Attacker One", "2/2")
    b = creature(s, "p1", "Attacker Two", "2/2")
    home = creature(s, "p1", "Stays Home", "2/2")
    robot = token_of(s, "p2", "Robot", "Token Artifact Creature — Robot", "1/9")
    bears = on_field(s, "Grizzly Bears", "p2")
    combat_step(s)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": c.id, "target": "p2"} for c in (loyalist, a, b)])
    for _ in range(6):
        if s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_blockers":
            break
        act(s, s.state.rules.priority, type="pass_priority")
    pl = Plan(s.state, "p1", s.cards, None)
    for c in (loyalist, a, b, home):
        assert {"first strike", "trample"} <= pl.ch(s.state.cards[c.id]).keywords
    with pytest.raises(ActionError, match="can't be blocked"):
        act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": robot.id, "attacker_id": a.id}])  # creature tokens can't block
    act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": bears.id, "attacker_id": a.id}])  # a card can
    check(s)


def test_legion_loyalist_needs_two_other_attackers(cards):
    s = sandbox(cards, "Legion Loyalist")
    loyalist = on_field(s, "Legion Loyalist")
    a = creature(s, "p1", "Attacker One", "2/2")
    guard = creature(s, "p2", "Guard", "0/9")
    combat_step(s)
    swing(s, [loyalist, a], [(guard, a)])
    settle(s)
    pl = Plan(s.state, "p1", s.cards, None)
    assert "trample" not in pl.ch(s.state.cards[a.id]).keywords
    check(s)


def test_azure_fleet_admiral_cannot_be_blocked_by_the_monarchs_creatures(cards):
    s = sandbox(cards, "Azure Fleet Admiral")
    admiral = on_field(s, "Azure Fleet Admiral")
    guard = creature(s, "p2", "Guard", "0/9")
    main_step(s)
    s.state.table.monarch = "p2"  # (set by hand for the test: no action sets it, and the replay below is of the actions only)
    # the monarch's creatures may not block it
    from app.rules import combat
    from app.rules.plan import Plan as _Plan

    pl = _Plan(s.state, "p2", s.cards, None)
    problem = combat.block_problem(s.state, s.state.cards[guard.id], pl.ch(s.state.cards[guard.id]), s.state.cards[admiral.id], pl.ch(s.state.cards[admiral.id]), pl.info)
    assert problem is not None and "can't be blocked" in problem
    s.state.table.monarch = "p1"
    assert combat.block_problem(s.state, s.state.cards[guard.id], pl.ch(s.state.cards[guard.id]), s.state.cards[admiral.id], pl.ch(s.state.cards[admiral.id]), pl.info) is None
    s.state.table.monarch = None


def test_pompous_gadabout_cannot_be_blocked_by_a_face_down_creature(cards):
    s = sandbox(cards, "Pompous Gadabout", p2=("Gravel Slinger", "Grizzly Bears"))
    gadabout = on_field(s, "Pompous Gadabout")
    slinger = on_field(s, "Gravel Slinger", "p2")
    act(s, "p2", type="move", card_ids=[slinger.id], to={"player": "p2", "zone": "battlefield"}, face_down=True, face_down_kind="morph")
    bears = on_field(s, "Grizzly Bears", "p2")
    combat_step(s)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": gadabout.id, "target": "p2"}])
    for _ in range(6):
        if s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_blockers":
            break
        act(s, s.state.rules.priority, type="pass_priority")
    with pytest.raises(ActionError, match="can't be blocked"):
        act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": slinger.id, "attacker_id": gadabout.id}])  # it has no name
    act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": bears.id, "attacker_id": gadabout.id}])
    check(s)

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
from tests.test_rules_wave34b_activated import activate, ask
from tests.wave53c_kit import (
    alive,
    attach,
    bob_swings,
    check,
    combat_step,
    creature,
    in_play,
    on_field,
    open_repo,
    pool,
    sandbox,
    settle,
    swing,
    to_postcombat,
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

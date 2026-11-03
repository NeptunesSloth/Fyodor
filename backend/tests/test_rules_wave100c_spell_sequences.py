"""Wave 100C: sequences, reflexive riders, exceptions and per-player counts of instants and sorceries (app/rules/static_spell100c.py), real
Oracle text (tests/fixtures/wave100c_static_spells_cards.json; CR 2026-09-25). Every scenario checks the replay and a save and a load.

* 608.2c / 603.12: "Then you may [cost]. When you do, …": the reflexive ability triggers only if the cost was paid; its target is chosen as it
  is put on the stack.
* 120.3 / 608.2h: one damage instruction naming creatures and players is one damage event; "except for …" leaves those creatures out.
* 121.2c / 608.2h: "each player draws a card for each …" and "each player creates … for each … they control": each player's own count, all
  determined before the first draw / token.
* 701.4a: "If a Dragon was beheld" reads the spell's one optional behold cost.
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import coverage
from tests.game_helpers import act
from tests.wave9c_kit import build, check, life
from tests.wave100c_kit import (
    cast,
    move,
    named,
    one,
    open_repo,
    pt_of,
    put_on,
    settle,
    start_cast,
    three,
    to_phase,
    zone,
)

PROMOTED = ["Hypothesizzle", "Lithobraking", "Sonar Strike", "Savage Swipe", "Flame Sweep", "Disorder", "Death by Dragons", "Nature's Resurgence",
            "Waiting in the Weeds", "Osseous Exhale", "Hyperion's Atomic Vision"]


@pytest.fixture()
def cards(settings):
    yield from open_repo(settings)


@pytest.mark.parametrize("name", PROMOTED)
def test_every_card_is_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def answer(s, *prefer):
    """Answer the current decision with these option ids / labels / card names (in order of preference)."""
    d = s.state.rules.decision
    assert d is not None
    ids = [o.id for o in d.options if o.id in prefer or o.label in prefer
           or (getattr(o, "card_id", None) in s.state.cards and s.state.cards[o.card_id].name in prefer)]
    act(s, d.player, type="choose", decision_id=d.id, option_ids=ids[: max(1, d.min_choices)] if ids else [])


def resolve_with(s, choices, limit=40):
    """Pass priority and answer decisions: ``choices`` maps a decision's kind or prompt word to the preferred answers."""
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None:
            pick = next((v for k, v in choices.items() if k in d.prompt or k == d.kind), None)
            if pick is None:
                act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
            else:
                answer(s, *pick)
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return


@pytest.mark.parametrize("discard", [True, False])
def test_hypothesizzle_deals_four_only_when_a_nonland_card_was_discarded(cards, discard):
    """Hypothesizzle: "Draw two cards. Then you may discard a nonland card. When you do, Hypothesizzle deals 4 damage to target creature." """
    s = build(cards, ["Hypothesizzle", "Opt"], ["Grizzly Bears"])
    bear, opt = put_on(s, "Grizzly Bears", "p2"), move(s, one(s, "Opt"), "hand")
    hand = len(s.state.zones["p1:hand"])
    start_cast(s, "Hypothesizzle", U=1, R=1, C=3)
    resolve_with(s, {": discard a nonland card?": ["pay"] if discard else ["decline"], "target": ["Grizzly Bears"]})
    if discard:
        assert zone(s, opt) == "p1:graveyard" and zone(s, bear) == "p2:graveyard"
        assert len(s.state.zones["p1:hand"]) == hand + 1  # (the spell left, two drawn, Opt discarded)
    else:
        assert zone(s, opt) == "p1:hand" and zone(s, bear) == "p2:battlefield"
        assert len(s.state.zones["p1:hand"]) == hand + 2
    check(s)


def test_lithobraking_may_sacrifice_its_own_lander_to_deal_two_to_each_creature(cards):
    """Lithobraking: "Create a Lander token. Then you may sacrifice an artifact. When you do, Lithobraking deals 2 damage to each creature." """
    s = build(cards, ["Lithobraking", "Grizzly Bears"], ["Hulking Cyclops"])
    bear, cyclops = put_on(s, "Grizzly Bears"), put_on(s, "Hulking Cyclops", "p2")
    start_cast(s, "Lithobraking", R=1, C=2)
    resolve_with(s, {": sacrifice an artifact?": ["pay"]})
    assert zone(s, bear) == "p1:graveyard" and zone(s, cyclops) == "p2:battlefield"
    assert not [c for c in s.state.cards.values() if c.name == "Lander" and c.zone.endswith(":battlefield")]
    check(s)


def test_sonar_strike_targets_attacking_blocking_or_tapped_and_gains_with_a_bat(cards):
    """Sonar Strike: "… 4 damage to target attacking, blocking, or tapped creature. You gain 3 life if you control a Bat." An untapped creature out
    of combat can't be targeted."""
    s = build(cards, ["Sonar Strike", "Kelinore Bat"], ["Amateur Hero", "Grizzly Bears"])
    hero, bear = put_on(s, "Amateur Hero", "p2"), put_on(s, "Grizzly Bears", "p2")
    put_on(s, "Kelinore Bat")
    act(s, "p2", type="tap", card_ids=[hero.id], tapped=True)
    with pytest.raises(ActionError):
        start_cast(s, "Sonar Strike", targets=[bear.id], W=1, C=1)
    cast(s, "Sonar Strike", targets=[hero.id])
    assert zone(s, hero) == "p2:graveyard" and life(s) == 43
    check(s)


def test_savage_swipe_pumps_only_a_two_power_creature_then_it_fights(cards):
    """Savage Swipe: a 2-power creature gets +2/+2, then fights (4 damage kills a 3/3, which deals 3 to the 4/4); a 1-power one doesn't."""
    s = build(cards, ["Savage Swipe", "Grizzly Bears"], ["Amateur Hero"])
    bear, hero = put_on(s, "Grizzly Bears"), put_on(s, "Amateur Hero", "p2")
    cast(s, "Savage Swipe", targets=[bear.id, hero.id], target_counts=[1, 1], G=1)
    assert zone(s, hero) == "p2:graveyard" and zone(s, bear) == "p1:battlefield" and pt_of(s, bear) == (4, 4)
    check(s)
    s = build(cards, ["Savage Swipe", "Llanowar Elves"], ["Amateur Hero"])
    elves, hero = put_on(s, "Llanowar Elves"), put_on(s, "Amateur Hero", "p2")
    cast(s, "Savage Swipe", targets=[elves.id, hero.id], target_counts=[1, 1], G=1)
    assert zone(s, elves) == "p1:graveyard" and zone(s, hero) == "p2:battlefield" and s.state.cards[hero.id].damage == 1
    check(s)


def test_flame_sweep_spares_only_your_own_flyers(cards):
    """Flame Sweep: "… 2 damage to each creature except for creatures you control with flying." Alice's flyer is spared; her ground creature and
    Bob's flyer aren't."""
    s = build(cards, ["Flame Sweep", "Kelinore Bat", "Grizzly Bears"], ["Kelinore Bat"])
    mine, bear, theirs = put_on(s, "Kelinore Bat"), put_on(s, "Grizzly Bears"), put_on(s, "Kelinore Bat", "p2")
    cast(s, "Flame Sweep", R=1, C=2)
    assert zone(s, mine) == "p1:battlefield" and s.state.cards[mine.id].damage == 0
    assert zone(s, bear) == "p1:graveyard" and zone(s, theirs) == "p2:graveyard"
    check(s)


def test_disorder_hurts_white_creatures_and_the_players_who_control_one(cards):
    """Disorder: "… 2 damage to each white creature and each player who controls a white creature." Alice controls none: no damage to her."""
    s = build(cards, ["Disorder", "Grizzly Bears"], ["Benalish Hero"])
    bear, hero = put_on(s, "Grizzly Bears"), put_on(s, "Benalish Hero", "p2")
    cast(s, "Disorder", R=1, C=1)
    assert zone(s, hero) == "p2:graveyard" and life(s, "p2") == 38  # (the player who controlled it as the damage was dealt: one event)
    assert life(s) == 40 and zone(s, bear) == "p1:battlefield"
    check(s)


def test_death_by_dragons_gives_a_dragon_to_every_other_player(cards):
    """Death by Dragons with three players: "Each player other than target player creates a 5/5 red Dragon creature token with flying." """
    s = three(cards, ["Death by Dragons"])
    cast(s, "Death by Dragons", targets=["p2"], R=2, C=4)
    dragons = sorted(c.controller for c in s.state.cards.values() if c.name == "Dragon" and c.zone.endswith(":battlefield"))
    assert dragons == ["p1", "p3"]
    check(s)


def test_natures_resurgence_each_player_draws_for_their_own_creature_cards(cards):
    """Nature's Resurgence: Alice has two creature cards and a noncreature in her graveyard, Bob one."""
    s = build(cards, ["Nature's Resurgence", "Grizzly Bears", "Llanowar Elves", "Opt"], ["Benalish Hero"])
    for c in (one(s, "Grizzly Bears"), one(s, "Llanowar Elves"), one(s, "Opt"), one(s, "Benalish Hero", "p2")):
        move(s, c, "graveyard")
    mine, theirs = len(s.state.zones["p1:hand"]), len(s.state.zones["p2:hand"])
    cast(s, "Nature's Resurgence", G=2, C=2)
    assert len(s.state.zones["p1:hand"]) == mine + 2 and len(s.state.zones["p2:hand"]) == theirs + 1
    check(s)


def test_waiting_in_the_weeds_counts_each_players_untapped_forests(cards):
    """Waiting in the Weeds: Alice has three untapped Forests and a tapped one (3 Cats); Bob one untapped Forest (1 Cat)."""
    s = build(cards, ["Waiting in the Weeds"], ["Forest"])
    forests = [move(s, c, "battlefield") for c in named(s, "Forest")[:4]]
    act(s, "p1", type="tap", card_ids=[forests[3].id], tapped=True)
    put_on(s, "Forest", "p2")
    cast(s, "Waiting in the Weeds", G=2, C=1)
    cats = sorted(c.controller for c in s.state.cards.values() if c.name == "Cat" and c.zone.endswith(":battlefield"))
    assert cats == ["p1", "p1", "p1", "p2"]
    check(s)


def combat_with_block(s, attacker, blocker):
    """Alice attacks Bob with ``attacker`` on turn 3; Bob blocks with ``blocker``; Alice has priority in the declare blockers step."""
    act(s, "p1", type="set_stops", own=["declare_blockers"], others=[], smart_pass=False)
    to_phase(s, "declare_attackers", turn=3)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": attacker.id, "target": "p2"}])
    for _ in range(20):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_blockers":
            act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": blocker.id, "attacker_id": attacker.id}])
            break
        act(s, s.state.rules.priority, type="pass_priority")
    for _ in range(10):
        if s.state.turn.phase == "declare_blockers" and s.state.rules.priority == "p1" and s.state.rules.decision is None:
            return
        act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("no priority in the declare blockers step")


@pytest.mark.parametrize("behold", [True, False])
def test_osseous_exhale_gains_life_only_if_a_dragon_was_beheld(cards, behold):
    """Osseous Exhale: "… 5 damage to target attacking or blocking creature. If a Dragon was beheld, you gain 2 life." The Dragon is revealed
    from Alice's hand (701.4a)."""
    s = build(cards, ["Osseous Exhale", "Hulking Cyclops", "Volcanic Dragon"], ["Amateur Hero"])
    cyclops, hero = put_on(s, "Hulking Cyclops"), put_on(s, "Amateur Hero", "p2")
    dragon = move(s, one(s, "Volcanic Dragon"), "hand")
    combat_with_block(s, cyclops, hero)
    spell = move(s, one(s, "Osseous Exhale"), "hand")
    act(s, "p1", type="add_mana", player="p1", mana={"W": 1, "C": 1})
    extra = {"optional_costs": [spell.id + ":behold"], "cost_choices": [{"component": 0, "cards": [dragon.id]}]} if behold else {}
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=[hero.id], sources=[], **extra)
    settle(s)
    assert zone(s, hero) == "p2:graveyard" and zone(s, dragon) == "p1:hand"
    assert life(s) == (42 if behold else 40)
    check(s)


def test_hyperions_atomic_vision_scries_only_if_a_hero_was_beheld(cards):
    """Hyperion's Atomic Vision: "Destroy target tapped creature. If a Hero was beheld, scry 2." The Hero is one Alice controls; an untapped
    creature can't be targeted."""
    for behold in (True, False):
        s = build(cards, ["Hyperion's Atomic Vision", "Amateur Hero"], ["Grizzly Bears", "Llanowar Elves"])
        hero, bear, elves = put_on(s, "Amateur Hero"), put_on(s, "Grizzly Bears", "p2"), put_on(s, "Llanowar Elves", "p2")
        act(s, "p2", type="tap", card_ids=[bear.id], tapped=True)
        spell = move(s, one(s, "Hyperion's Atomic Vision"), "hand")
        act(s, "p1", type="add_mana", player="p1", mana={"W": 1, "C": 1})
        with pytest.raises(ActionError):
            act(s, "p1", type="cast_spell", card_id=spell.id, targets=[elves.id], sources=[])
        extra = {"optional_costs": [spell.id + ":behold"], "cost_choices": [{"component": 0, "cards": [hero.id]}]} if behold else {}
        act(s, "p1", type="cast_spell", card_id=spell.id, targets=[bear.id], sources=[], **extra)
        scried = []
        for _ in range(20):
            d = s.state.rules.decision
            if d is not None:
                scried.append(d.prompt)
                act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: d.min_choices])
            elif s.state.zones.get("stack"):
                act(s, s.state.rules.priority, type="pass_priority")
            else:
                break
        assert zone(s, bear) == "p2:graveyard" and zone(s, hero) == "p1:battlefield"
        assert bool(scried) == behold
        check(s)

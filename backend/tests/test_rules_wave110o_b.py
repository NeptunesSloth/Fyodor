"""Wave 110O (second half): single-card wordings, real Oracle text (tests/fixtures/wave110o_cards.json). Every scenario checks the replay and a save and a load.

* 601.2b, 118.8, 615.1: Undergrowth's optional {2}{R} (paid as it is cast) makes its combat damage prevention skip red creatures.
* 603.7a, 701.9, 603.2c: Pure Intentions returns the cards an opponent's spell or ability made you discard (one batch), and itself at the next end step.
* 601.2b, 107.3a, 601.2d: Nahiri's Sacrifice announces X as the mana value of the artifact or creature sacrificed, and divides X damage (none at all if X is 0).
* 608.2c, 118.12a, 101.4: Cleansing gives every land its own round of payments (every player decides in turn order); a land nobody paid for is destroyed.
* 603.7a, 603.7c: Mysterio's tokens are exiled when it leaves the battlefield (a delayed trigger on Mysterio, so none if it already left).
* 614.9, 122.8, 603.10a: Heroic Sacrifice sends damage to you and your creatures to the chosen creature (only while it is on the battlefield); when it dies its counters go to a creature.
* 118.9, 404.1, 118.3: Spinning Darkness's alternative cost exiles the top three black cards of the graveyard (no choice); with fewer it can't be paid.
* 608.2c, 118.12: Tidal Flats asks the controller of each attacking creature without flying for {1}; blockers of the creatures whose controller didn't pay get first strike.
* 614.1a, 704.5g: Pyramids' shield replaces the next destruction of a land this turn (an effect's or lethal damage) by removing the damage on it; its other mode destroys an Aura attached to a land.
* 614.1a, 608.2d: Soul Echo: the targeted opponent decides; each 1 damage to its controller until their next turn is replaced by an echo counter removed (while there is one).
* 114.1, 602.2, 113.6k: Ob Nixilis of the Black Oath's -8 emblem is activated from the command zone (sacrifice a creature: gain X life, draw X cards).
* 707.2, 611.2b, 610.3: Secret Invasion exiles a creature and makes the enchanted one a copy of it for as long as the Aura stays; the exiled one comes back with it.
* 615.1, 614.1a: Chromatic Armor prevents damage to the enchanted creature from sources of the last chosen color (each choice replaces the one before).
* 613.1d, 613.1c, 613.1f, 613.4b: Tenth District Hero becomes a legendary 5/5 named Mileva, the Stalwart (only if it is a Detective), giving other creatures its controller controls indestructible.
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import alt_costs
from app.rules.plan import Plan
from tests.game_helpers import act
from tests.test_rules_wave34b_activated import stops
from tests.wave9c_kit import build
from tests.wave110o_kit import (  # noqa: F401
    EXTRA,
    ability,
    activate,
    card_db,
    card_named,
    cast_on,
    ch,
    check,
    cost,
    full,
    grave_new,
    life,
    mana,
    next_turn,
    now,
    put,
    put_new,
    settle,
    to_hand,
    to_phase,
)

UNDERGROWTH = "Undergrowth"


@pytest.mark.parametrize("name", [UNDERGROWTH, "Pure Intentions", "Nahiri's Sacrifice", "Cleansing", "Mysterio, Master of Illusion", "Heroic Sacrifice", "Spinning Darkness", "Tidal Flats", "Pyramids", "Soul Echo", "Ob Nixilis of the Black Oath", "Secret Invasion", "Chromatic Armor", "Tenth District Hero"])
def test_the_cards_are_full(name):
    assert full(name)


def passes_to_bob(s):
    for _ in range(20):
        if s.state.rules.priority == "p2" and not s.state.zones.get("stack"):
            return
        act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("Bob never got priority")


@pytest.mark.parametrize("kicked", [False, True])
def test_undergrowth_prevents_all_combat_damage_but_red_creatures_when_the_extra_cost_is_paid(cards, kicked):
    s = build(cards, ["Mardu Scout", "Grizzly Bears"], [UNDERGROWTH])
    scout, bears = put(s, "Mardu Scout"), put(s, "Grizzly Bears")
    for c in (scout, bears):
        s.state.rules.controlled_since[c.id].turn = 0
    stops(s)
    while s.state.rules.decision is None or s.state.rules.decision.kind != "declare_attackers":
        act(s, s.state.rules.priority, type="pass_priority")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": c.id, "target": "p2"} for c in (scout, bears)])
    passes_to_bob(s)
    spell = to_hand(s, UNDERGROWTH, "p2")
    mana(s, "p2", **({"G": 1, "R": 1, "C": 2} if kicked else {"G": 1}))
    act(s, "p2", type="cast_spell", card_id=spell.id, **({"kicker": 1} if kicked else {}))
    settle(s)
    for _ in range(30):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
        elif s.state.turn.phase == "main2" and not s.state.zones.get("stack"):
            break
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    assert life(s, "p2") == 40 - (2 if kicked else 0)  # (the red Scout's 2 is not prevented when {2}{R} was paid; the green Bears' 2 always is)
    check(s)


PURE, ROT = "Pure Intentions", "Mind Rot"


def bobs_rot(cards, hand, in_response=True):
    """Bob's first main phase, Alice's hand exactly ``hand``; Bob casts Mind Rot on Alice and Alice (with priority) casts Pure Intentions."""
    s = build(cards, [PURE, "Grizzly Bears", "Llanowar Elves", "Barren Moor"], [ROT])
    for c in [c for c in s.state.cards.values() if c.zone == "p1:hand"]:
        act(s, "p1", type="move", card_ids=[c.id], to={"zone": "library"}, position="bottom")
    mine = [to_hand(s, n) for n in hand]
    stops(s)
    to_phase(s, "main1", turn=2)
    rot = to_hand(s, ROT, "p2")
    mana(s, "p2", B=1, C=2)
    act(s, "p2", type="cast_spell", card_id=rot.id, targets=["p1"])
    return s, mine


def alice_casts_pure(s):
    pure = card_named(s, PURE)
    mana(s, "p1", W=1)
    act(s, "p1", type="cast_spell", card_id=pure.id)


def finish(s, picks=()):
    """Resolve the stack; Alice's discard picks are ``picks`` (card ids)."""
    for _ in range(40):
        d = s.state.rules.decision
        if d is not None and d.kind in ("declare_attackers", "declare_blockers"):
            return
        if d is not None:
            ids = [o.id for o in d.options if o.card_id in picks][: max(1, d.min_choices)] or [o.id for o in d.options][: max(1, d.min_choices)]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=ids)
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return


def test_pure_intentions_returns_the_cards_an_opponents_spell_made_you_discard(cards):
    s, (pure, bears, elves) = bobs_rot(cards, [PURE, "Grizzly Bears", "Llanowar Elves"])
    alice_casts_pure(s)
    finish(s, picks={bears.id, elves.id})
    assert now(s, bears).zone == "p1:hand" and now(s, elves).zone == "p1:hand" and now(s, pure).zone == "p1:graveyard"
    check(s)


def test_pure_intentions_ignores_a_discard_you_pay_as_a_cost(cards):
    s, (pure, moor, bears) = bobs_rot(cards, [PURE, "Barren Moor", "Grizzly Bears"])
    alice_casts_pure(s)
    while not (s.state.rules.priority == "p1" and len(s.state.zones["stack"]) == 1):
        act(s, s.state.rules.priority, type="pass_priority")
    mana(s, "p1", B=1)
    act(s, "p1", type="activate_ability", card_id=moor.id, ability=next(a.index for a in ch(s, moor).abilities if a.text.startswith("Cycling")))
    finish(s)
    assert now(s, moor).zone == "p1:graveyard"  # (cycling discards it as a cost: not a spell or ability an opponent controls, 701.9, 118.8)
    assert now(s, bears).zone == "p1:hand"  # (Mind Rot's discards came back)
    check(s)


def test_pure_intentions_discarded_by_an_opponents_spell_returns_at_the_next_end_step(cards):
    s, (pure, bears) = bobs_rot(cards, [PURE, "Grizzly Bears"])
    finish(s)
    assert now(s, pure).zone == "p1:graveyard" and now(s, bears).zone == "p1:graveyard"
    for _ in range(40):
        if s.state.turn.phase == "end" or s.state.rules.decision is not None and s.state.rules.decision.kind in ("declare_attackers", "declare_blockers"):
            break
        act(s, s.state.rules.priority, type="pass_priority")
    settle(s)
    assert now(s, pure).zone == "p1:hand" and now(s, bears).zone == "p1:graveyard"  # (only Pure Intentions itself: the other card stays)
    check(s)


NAHIRI = "Nahiri's Sacrifice"


def nahiri_table(cards, mine, theirs):
    s = build(cards, [NAHIRI, *mine], theirs)
    return s, [put(s, n) for n in mine], [put(s, n, "p2") for n in theirs]


def nahiri_cast(s, victim, targets, x, division=None, pid="p1"):
    spell = to_hand(s, NAHIRI)
    mana(s, "p1", **cost(NAHIRI))
    kw = {"division": division} if division else {}
    act(s, "p1", type="cast_spell", card_id=spell.id, x_value=x, targets=[t.id for t in targets], target_counts=[len(targets)],
        cost_choices=[{"component": 0, "cards": [victim.id]}], **kw)
    settle(s)


def test_nahiri_sacrifice_sacrifices_a_creature_of_mana_value_x_and_divides_x_damage(cards):
    s, (bears,), (elves, wolf) = nahiri_table(cards, ["Grizzly Bears"], ["Llanowar Elves", "Grizzly Bears"])
    nahiri_cast(s, bears, [elves, wolf], 2, division=[1, 1])
    assert now(s, bears).zone == "p1:graveyard" and now(s, elves).zone == "p2:graveyard"  # (X is the sacrificed Bears' mana value, 2: 1 + 1)
    assert now(s, wolf).zone == "p2:battlefield" and now(s, wolf).damage == 1
    check(s)


def test_nahiri_sacrifice_sacrifices_an_artifact_too(cards):
    s, (ring,), (elves,) = nahiri_table(cards, ["Sol Ring"], ["Llanowar Elves"])
    nahiri_cast(s, ring, [elves], 1)
    assert now(s, ring).zone == "p1:graveyard" and now(s, elves).zone == "p2:graveyard"
    check(s)


def test_nahiri_sacrifice_cannot_sacrifice_a_permanent_of_another_mana_value(cards):
    s, (bears,), (elves,) = nahiri_table(cards, ["Grizzly Bears"], ["Llanowar Elves"])
    spell = to_hand(s, NAHIRI)
    mana(s, "p1", **cost(NAHIRI))
    before = s.state.model_dump(mode="json")
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=spell.id, x_value=1, targets=[elves.id], target_counts=[1],
            cost_choices=[{"component": 0, "cards": [bears.id]}])  # (Bears have mana value 2, not 1: 601.2b, 107.3a)
    assert s.state.model_dump(mode="json") == before
    check(s)


def test_nahiri_sacrifice_with_a_mana_value_zero_permanent_deals_no_damage(cards):
    s, (bird,), (elves,) = nahiri_table(cards, ["Ornithopter"], ["Llanowar Elves"])
    spell = to_hand(s, NAHIRI)
    mana(s, "p1", **cost(NAHIRI))
    act(s, "p1", type="cast_spell", card_id=spell.id, x_value=0, cost_choices=[{"component": 0, "cards": [bird.id]}])  # (X is 0: nothing to divide, so no target)
    settle(s)
    assert now(s, bird).zone == "p1:graveyard" and now(s, elves).zone == "p2:battlefield" and now(s, elves).damage == 0
    check(s)


def cleansing_table(cards):
    s = build(cards, ["Cleansing", "Grizzly Bears"], [])
    for _ in range(2):
        put_new(s, "Forest")
    put_new(s, "Island", "p2")
    put(s, "Grizzly Bears")
    return s


def cast_cleansing(s, pays):
    """Cast it; ``pays``: the (0-based) indexes of the answers (Alice's and Bob's about each land in turn: 0 Alice-land0, 1 Bob-land0, 2 Alice-land1 …) that pay."""
    lands = [c for c in s.state.cards.values() if c.zone.endswith(":battlefield") and c.name in ("Forest", "Island")]
    spell = to_hand(s, "Cleansing")
    mana(s, "p1", W=3)
    act(s, "p1", type="cast_spell", card_id=spell.id)
    asked = []
    for _ in range(80):
        d = s.state.rules.decision
        if d is None:
            if not s.state.zones.get("stack"):
                break
            act(s, s.state.rules.priority, type="pass_priority")
            continue
        asked.append((d.player, d.prompt))
        act(s, d.player, type="choose", decision_id=d.id, option_ids=["pay" if len(asked) - 1 in pays else "decline"])
    return lands, asked


def test_cleansing_asks_every_player_about_every_land_and_destroys_the_unpaid_ones(cards):
    s = cleansing_table(cards)
    lands, asked = cast_cleansing(s, pays={3, 4})  # (Bob pays for the second land; Alice for the third)
    assert [p for p, _ in asked] == ["p1", "p2"] * 3 and all("for " in q for _, q in asked)
    assert [now(s, c).zone.endswith(":battlefield") for c in lands] == [False, True, True]
    assert life(s, "p1") == 39 and life(s, "p2") == 39  # (a payment made is not undone by the land being saved already: both paid)
    assert now(s, next(c for c in s.state.cards.values() if c.name == "Grizzly Bears" and c.zone.endswith("battlefield"))).zone == "p1:battlefield"
    check(s)


def test_cleansing_with_no_payment_destroys_every_land_and_only_lands(cards):
    s = cleansing_table(cards)
    lands, _ = cast_cleansing(s, pays=set())
    assert all(now(s, c).zone.endswith(":graveyard") for c in lands)
    assert any(c.name == "Grizzly Bears" and c.zone == "p1:battlefield" for c in s.state.cards.values())
    assert life(s, "p1") == 40 and life(s, "p2") == 40
    check(s)


MYSTERIO = "Mysterio, Master of Illusion"


def illusions(s):
    return [c for c in s.state.cards.values() if c.is_token and c.name == "Illusion Villain" and c.zone != "exile" and not c.zone.endswith("graveyard")]


def test_mysterio_makes_a_token_for_each_nontoken_villain_and_exiles_them_when_it_leaves(cards):
    s = build(cards, [MYSTERIO, "Common Crook", "Murder"])
    put(s, "Common Crook")
    mys = cast_on(s, MYSTERIO)
    assert len(illusions(s)) == 2 and all(ch(s, t).pt == (3, 3) for t in illusions(s))  # (the Crook and Mysterio itself; the tokens are Villains but not counted)
    cast_on(s, "Murder", mys)
    assert now(s, mys).zone == "p1:graveyard" and not illusions(s)
    assert next(c for c in s.state.cards.values() if c.name == "Common Crook").zone == "p1:battlefield"
    check(s)


def test_mysterio_leaving_before_its_ability_resolves_leaves_the_tokens(cards):
    s = build(cards, [MYSTERIO, "Common Crook", "Murder"])
    put(s, "Common Crook")
    stops(s)
    mys = to_hand(s, MYSTERIO)
    mana(s, "p1", **cost(MYSTERIO))
    act(s, "p1", type="cast_spell", card_id=mys.id)
    while not any(c.name == MYSTERIO and c.zone == "p1:battlefield" for c in s.state.cards.values()):
        act(s, s.state.rules.priority, type="pass_priority")
    murder = to_hand(s, "Murder")
    mana(s, "p1", **cost("Murder"))
    act(s, "p1", type="cast_spell", card_id=murder.id, targets=[mys.id])  # (in response to Mysterio's enters trigger: 603.7c, nothing left to watch)
    settle(s)
    assert now(s, mys).zone == "p1:graveyard" and len(illusions(s)) == 1  # (only the Crook was counted: Mysterio had left)
    check(s)


HEROIC = "Heroic Sacrifice"


def heroic_table(cards, extra=()):
    s = build(cards, [HEROIC, "Grizzly Bears", "Llanowar Elves", "Murder", *extra], ["Lightning Bolt", "Lightning Bolt"])
    bears, elves = put(s, "Grizzly Bears"), put(s, "Llanowar Elves")
    s.state.cards[elves.id].counters["+1/+1"] = 2  # (a 3/3 holding the counters that will be put on the Bears)
    stops(s)
    heroic = to_hand(s, HEROIC)
    mana(s, "p1", **cost(HEROIC))
    act(s, "p1", type="cast_spell", card_id=heroic.id, targets=[elves.id])
    settle(s)
    return s, bears, elves


def bolt(s, target):
    while s.state.rules.priority != "p2":
        act(s, s.state.rules.priority, type="pass_priority")
    spell = to_hand(s, "Lightning Bolt", "p2")
    mana(s, "p2", R=1)
    act(s, "p2", type="cast_spell", card_id=spell.id, targets=[target])
    for _ in range(30):
        d = s.state.rules.decision
        if d is not None:
            ids = [o.id for o in d.options if o.card_id and now(s, next(c for c in s.state.cards.values() if c.id == o.card_id)).name == "Grizzly Bears"][:1] or [d.options[0].id]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=ids)
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return


@pytest.mark.parametrize("hit", ["player", "creature"])
def test_heroic_sacrifice_redirects_damage_to_you_and_your_creatures_and_moves_the_counters_on_death(cards, hit):
    s, bears, elves = heroic_table(cards)
    hand = len(s.state.zones["p1:hand"])
    bolt(s, "p1" if hit == "player" else bears.id)
    assert life(s, "p1") == 40 and now(s, bears).damage == 0  # (all of it went to the Elves)
    assert now(s, elves).zone == "p1:graveyard"
    assert now(s, bears).counters.get("+1/+1") == 2 and len(s.state.zones["p1:hand"]) == hand + 1  # (its counters as it last existed, 122.8, and a card)
    check(s)


def test_heroic_sacrifice_does_nothing_once_the_chosen_creature_is_gone(cards):
    s, bears, elves = heroic_table(cards)
    spell = to_hand(s, "Murder")
    mana(s, "p1", **cost("Murder"))
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=[elves.id])
    settle(s)
    assert now(s, elves).zone == "p1:graveyard"
    bolt(s, "p1")
    assert life(s, "p1") == 37  # (614.9: the chosen creature is no longer on the battlefield: the damage is dealt to Alice)
    check(s)


DARKNESS = "Spinning Darkness"


def darkness_table(cards, graveyard):
    s = build(cards, [DARKNESS, *graveyard], ["Grizzly Bears", "Llanowar Elves", "Roxxon Brutes"])
    for n in graveyard:
        grave_new(s, n)
    return s, put(s, "Grizzly Bears", "p2"), put(s, "Llanowar Elves", "p2")


def cast_free(s, target):
    spell = to_hand(s, DARKNESS)
    plan = Plan(s.state, "p1", s.cards, None)
    offers = alt_costs.offers(s.state, "p1", spell, plan.ch(spell), s.cards)
    assert len(offers) == 1
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=[target.id], alt_cost=offers[0].key)
    settle(s)
    return spell


def test_spinning_darkness_exiles_the_top_three_black_cards_of_your_graveyard_instead_of_its_mana(cards):
    names = ["Murder", "Lightning Bolt", "Mind Rot", "Grizzly Bears", "Common Crook", "Roxxon Brutes"]  # (the last one is the top)
    s, bears, elves = darkness_table(cards, names)
    cast_free(s, bears)
    gone = {c.name for c in s.state.cards.values() if c.zone == "p1:exile"}
    assert gone == {"Mind Rot", "Common Crook", "Roxxon Brutes"}  # (the Bears are on top of Mind Rot but not black: they stay, so do the older Murder and Bolt)
    assert now(s, bears).zone == "p2:graveyard" and life(s, "p1") == 43
    check(s)


def test_spinning_darkness_cannot_be_cast_free_with_fewer_than_three_black_cards(cards):
    s, bears, elves = darkness_table(cards, ["Murder", "Lightning Bolt", "Mind Rot", "Grizzly Bears"])
    spell = to_hand(s, DARKNESS)
    key = alt_costs.offers(s.state, "p1", spell, Plan(s.state, "p1", s.cards, None).ch(spell), s.cards)[0].key
    before = s.state.model_dump(mode="json")
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=spell.id, targets=[bears.id], alt_cost=key)  # (118.3: only two black cards, nothing is paid)
    assert s.state.model_dump(mode="json") == before
    check(s)


def test_spinning_darkness_cannot_target_a_black_creature_and_kills_a_nonblack_one_for_its_mana(cards):
    s, bears, elves = darkness_table(cards, ["Murder"])
    brutes = put(s, "Roxxon Brutes", "p2")
    spell = to_hand(s, DARKNESS)
    mana(s, "p1", **cost(DARKNESS))
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=spell.id, targets=[brutes.id])
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=[elves.id])
    settle(s)
    assert now(s, elves).zone == "p2:graveyard" and now(s, brutes).zone == "p2:battlefield" and life(s, "p1") == 43
    assert now(s, next(c for c in s.state.cards.values() if c.name == "Murder")).zone == "p1:graveyard"  # (paid with mana: no card exiled)
    check(s)


TIDAL = "Tidal Flats"


def tidal_table(cards):
    """Bob attacks Alice with Grizzly Bears and a Mesa Pegasus (flying); Alice blocks the Bears with hers and has priority with Tidal Flats in play."""
    s = build(cards, [TIDAL, "Grizzly Bears"], ["Grizzly Bears", "Mesa Pegasus"])
    flats, mine = put(s, TIDAL), put(s, "Grizzly Bears")
    bears, bird = put(s, "Grizzly Bears", "p2"), put(s, "Mesa Pegasus", "p2")
    stops(s)
    for c in (bears, bird):
        s.state.rules.controlled_since[c.id].turn = 0
    while s.state.rules.decision is None or s.state.rules.decision.kind != "declare_attackers":
        act(s, s.state.rules.priority, type="pass_priority")
    act(s, "p2", type="declare_attackers", attackers=[{"card_id": c.id, "target": "p1"} for c in (bears, bird)])
    while s.state.rules.decision is None or s.state.rules.decision.kind != "declare_blockers":
        act(s, s.state.rules.priority, type="pass_priority")
    act(s, "p1", type="declare_blockers", blocks=[{"blocker_id": mine.id, "attacker_id": bears.id}])
    while s.state.rules.priority != "p1":
        act(s, s.state.rules.priority, type="pass_priority")
    return s, flats, mine, bears, bird


@pytest.mark.parametrize("answer", ["pay", "decline", "cannot"])
def test_tidal_flats_gives_my_blockers_first_strike_unless_the_attackers_controller_pays(cards, answer):
    pays = answer == "pay"
    s, flats, mine, bears, bird = tidal_table(cards)
    mana(s, "p1", U=2)
    if answer != "cannot":
        mana(s, "p2", C=1)
    act(s, "p1", type="activate_ability", card_id=flats.id, ability=ability(s, flats, "{U}{U}"))
    asked = []
    for _ in range(20):
        d = s.state.rules.decision
        if d is None:
            if not s.state.zones.get("stack"):
                break
            act(s, s.state.rules.priority, type="pass_priority")
            continue
        asked.append((d.player, d.prompt))
        act(s, d.player, type="choose", decision_id=d.id, option_ids=["pay" if pays else "decline"])
    if answer == "cannot":  # (118.3: no mana to pay with, so no question; the attackers' controller doesn't pay)
        assert not asked
    else:
        assert [p for p, _ in asked] == ["p2"] and "Grizzly Bears (attacking)" in asked[0][1]  # (the flying Pegasus is not asked about)
    assert ("first strike" in ch(s, mine).keywords) is (not pays)
    check(s)


PYRAMIDS = "Pyramids"


def pyramids_table(cards, mine=(), theirs=()):
    s = build(cards, [PYRAMIDS, "Mutavault", "Stone Rain", "Armageddon", "Wild Growth", "Lightning Bolt", *mine], ["Pacifism", "Grizzly Bears", *theirs])
    return s, put(s, PYRAMIDS), put(s, "Mutavault")


def pyramids(s, pyr, mode, target):
    mana(s, "p1", C=2)
    act(s, "p1", type="activate_ability", card_id=pyr.id, ability=0, modes=[mode], targets=[target.id])
    settle(s)


def test_pyramids_shield_saves_a_land_from_the_next_destruction_only(cards):
    s, pyr, vault = pyramids_table(cards)
    pyramids(s, pyr, 1, vault)
    cast_on(s, "Stone Rain", vault)
    assert now(s, vault).zone == "p1:battlefield"  # (the first destruction is replaced: 614.1a)
    cast_on(s, "Stone Rain", vault)
    assert now(s, vault).zone == "p1:graveyard"  # (the shield was used up by the first)
    check(s)


def test_pyramids_shield_removes_the_damage_from_an_animated_land_instead_of_destroying_it(cards):
    s, pyr, vault = pyramids_table(cards)
    pyramids(s, pyr, 1, vault)
    mana(s, "p1", C=1)
    activate(s, vault, "{1}")
    assert "Creature" in ch(s, vault).types
    cast_on(s, "Lightning Bolt", vault)
    assert now(s, vault).zone == "p1:battlefield" and now(s, vault).damage == 0  # (704.5g: lethal damage destroys; the shield replaces that)
    check(s)


def test_pyramids_shield_ends_with_the_turn(cards):
    s, pyr, vault = pyramids_table(cards)
    pyramids(s, pyr, 1, vault)
    next_turn(s)
    to_phase(s, "main1", turn=3)
    cast_on(s, "Stone Rain", vault)
    assert now(s, vault).zone == "p1:graveyard"
    check(s)


def test_pyramids_other_mode_destroys_an_aura_attached_to_a_land_only(cards):
    s, pyr, vault = pyramids_table(cards)
    growth = cast_on(s, "Wild Growth", vault)
    assert now(s, growth).attached_to == vault.id
    bears = put(s, "Grizzly Bears", "p2")
    pacifism = to_hand(s, "Pacifism", "p2")
    act(s, "p2", type="move", card_ids=[pacifism.id], to={"zone": "battlefield"})
    mana(s, "p1", C=2)
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=pyr.id, ability=0, modes=[0], targets=[bears.id])  # (a creature, not an Aura attached to a land)
    pyramids(s, pyr, 0, growth)
    assert now(s, growth).zone == "p1:graveyard" and now(s, vault).zone == "p1:battlefield"
    check(s)


def test_pyramids_shield_saves_only_its_land_from_a_mass_destruction(cards):
    s, pyr, vault = pyramids_table(cards)
    forest = put_new(s, "Forest")
    pyramids(s, pyr, 1, vault)
    cast_on(s, "Armageddon")
    assert now(s, vault).zone == "p1:battlefield" and now(s, forest).zone == "p1:graveyard"
    check(s)


ECHO = "Soul Echo"


def echo_table(cards, x=2):
    s = build(cards, [ECHO], ["Lightning Bolt", "Lightning Bolt"])
    spell = to_hand(s, ECHO)
    mana(s, "p1", W=2, C=x)
    act(s, "p1", type="cast_spell", card_id=spell.id, x_value=x)
    settle(s)
    echo = now(s, spell)
    assert echo.zone == "p1:battlefield" and echo.counters.get("echo", 0) == x
    stops(s)
    to_phase(s, "upkeep", turn=3)
    return s, echo


def answer_echo(s, choice):
    for _ in range(20):
        d = s.state.rules.decision
        if d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[choice if "echo" in d.prompt or "damage" in d.prompt else d.options[0].id])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return


def test_soul_echo_removes_counters_instead_of_damage_when_the_opponent_chooses_it(cards):
    s, echo = echo_table(cards)
    answer_echo(s, "yes")
    bolt(s, "p1")
    assert life(s, "p1") == 39 and now(s, echo).counters.get("echo", 0) == 0  # (2 of the 3 damage replaced by 2 counters, the last point is dealt)
    check(s)


def test_soul_echo_does_nothing_when_the_opponent_declines(cards):
    s, echo = echo_table(cards)
    answer_echo(s, "no")
    bolt(s, "p1")
    assert life(s, "p1") == 37 and now(s, echo).counters.get("echo") == 2
    check(s)


def test_soul_echo_without_counters_is_sacrificed_at_the_upkeep(cards):
    s, echo = echo_table(cards, x=0)
    answer_echo(s, "yes")
    assert now(s, echo).zone == "p1:graveyard"
    check(s)


OB = "Ob Nixilis of the Black Oath"


def ob_table(cards):
    s = build(cards, [OB, "Grizzly Bears", "Llanowar Elves"], [])
    ob = put(s, OB)
    s.state.cards[ob.id].counters["loyalty"] = 8
    return s, ob, put(s, "Grizzly Bears"), put(s, "Llanowar Elves")


def test_ob_nixilis_emblem_sacrifices_a_creature_for_life_and_cards_from_the_command_zone(cards):
    s, ob, bears, elves = ob_table(cards)
    act(s, "p1", type="activate_ability", card_id=ob.id, ability=next(a.index for a in ch(s, ob).abilities if a.text.startswith("−8")))
    settle(s)
    emblem = next(c for c in s.state.cards.values() if c.zone == "p1:command" and c.token is not None and c.token.type_line == "Emblem")
    hand, life0 = len(s.state.zones["p1:hand"]), life(s, "p1")
    mana(s, "p1", B=1, C=1)
    act(s, "p1", type="activate_ability", card_id=emblem.id, ability=ability(s, emblem, "{1}{B}"), cost_choices=[{"component": 1, "cards": [bears.id]}])
    settle(s)
    assert now(s, bears).zone == "p1:graveyard" and life(s, "p1") == life0 + 2 and len(s.state.zones["p1:hand"]) == hand + 2  # (X is the sacrificed Bears' power, 2)
    # (it stays: 114.4 — a second activation works too)
    mana(s, "p1", B=1, C=1)
    act(s, "p1", type="activate_ability", card_id=emblem.id, ability=ability(s, emblem, "{1}{B}"), cost_choices=[{"component": 1, "cards": [elves.id]}])
    settle(s)
    assert now(s, elves).zone == "p1:graveyard" and life(s, "p1") == life0 + 3
    check(s)


SECRET = "Secret Invasion"


def test_secret_invasion_exiles_a_creature_and_makes_the_enchanted_one_its_copy_while_the_aura_stays(cards):
    s = build(cards, [SECRET, "Grizzly Bears", "Naturalize"], ["Mesa Pegasus"])
    bears, bird = put(s, "Grizzly Bears"), put(s, "Mesa Pegasus", "p2")
    aura = cast_on(s, SECRET, bears)
    assert now(s, aura).attached_to == bears.id and now(s, bird).zone == "p2:exile"
    assert ch(s, bears).name == "Mesa Pegasus" and ch(s, bears).pt == (1, 1) and "flying" in ch(s, bears).keywords  # (707.2: a copy of the exiled creature)
    assert any(k.lower().startswith("ward") for k in ch(s, bears).keywords)  # (and Secret Invasion's ward {2})
    check(s)
    cast_on(s, "Naturalize", aura)
    assert now(s, aura).zone == "p1:graveyard"
    assert ch(s, bears).name == "Grizzly Bears" and ch(s, bears).pt == (2, 2) and now(s, bird).zone == "p2:battlefield"  # (611.2b, 610.3: both end with the Aura)
    check(s)


def test_secret_invasion_with_no_creature_to_exile_changes_nothing(cards):
    s = build(cards, [SECRET, "Grizzly Bears"], [])
    bears = put(s, "Grizzly Bears")
    aura = cast_on(s, SECRET, bears)
    assert now(s, aura).attached_to == bears.id and ch(s, bears).name == "Grizzly Bears"
    check(s)


ARMOR = "Chromatic Armor"


def choose_color(s, label, pid="p1"):
    """Answer the next question (a colour) with ``label``; resolve the stack."""
    for _ in range(40):
        d = s.state.rules.decision
        if d is not None:
            ids = [o.id for o in d.options if o.label == label] or [d.options[0].id]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=ids)
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return


def test_chromatic_armor_prevents_damage_from_the_last_chosen_color(cards):
    s = build(cards, [ARMOR, "Grizzly Bears"], ["Lightning Bolt", "Lightning Bolt", "Lightning Bolt"])
    bears = put(s, "Grizzly Bears")
    stops(s)
    armor = to_hand(s, ARMOR)
    mana(s, "p1", **cost(ARMOR))
    act(s, "p1", type="cast_spell", card_id=armor.id, targets=[bears.id])
    choose_color(s, "Red")
    assert now(s, armor).counters.get("sleight") == 1
    bolt(s, bears.id)
    assert now(s, bears).damage == 0 and now(s, bears).zone == "p1:battlefield"  # (red: prevented)
    mana(s, "p1", C=1)  # {X}, X = 1 sleight counter: one more counter and a new colour
    act(s, "p1", type="activate_ability", card_id=armor.id, ability=ability(s, armor, "{X}"))
    choose_color(s, "Blue")
    assert now(s, armor).counters.get("sleight") == 2
    bolt(s, bears.id)
    assert now(s, bears).zone == "p1:graveyard"  # (red is no longer the chosen colour: Bolt kills the Bears)
    check(s)


HERO = "Tenth District Hero"


def hero_table(cards):
    s = build(cards, [HERO, "Grizzly Bears", "Llanowar Elves", "Murder", "Wrath of God", "Mesa Pegasus"], ["Grizzly Bears"])
    hero = put(s, HERO)
    for n in ("Grizzly Bears", "Llanowar Elves", "Murder", "Wrath of God"):
        grave_new(s, n)
    return s, hero


def hero_activate(s, hero, start, pay, **mana_):
    mana(s, "p1", **mana_)
    act(s, "p1", type="activate_ability", card_id=hero.id, ability=ability(s, hero, start), cost_choices=[{"component": 1, "cards": [c.id for c in pay]}])
    settle(s)


def test_tenth_district_hero_becomes_mileva_only_after_it_is_a_detective(cards):
    s, hero = hero_table(cards)
    grave = {c.name: c for c in s.state.cards.values() if c.zone == "p1:graveyard"}
    mine, theirs = put(s, "Mesa Pegasus"), put(s, "Grizzly Bears", "p2")
    hero_activate(s, hero, "{2}{W}", [grave["Wrath of God"]], W=1, C=2)  # (not a Detective yet: nothing happens, though the evidence is paid)
    assert ch(s, hero).name == HERO and ch(s, hero).pt == (2, 3)
    hero_activate(s, hero, "{1}{W}", [grave["Grizzly Bears"]], W=1, C=1)
    assert "Detective" in ch(s, hero).subtypes and ch(s, hero).pt == (4, 4) and "vigilance" in ch(s, hero).keywords
    assert "indestructible" not in ch(s, mine).keywords
    hero_activate(s, hero, "{2}{W}", [grave["Murder"], grave["Llanowar Elves"]], W=1, C=2)
    mileva = ch(s, hero)
    assert mileva.name == "Mileva, the Stalwart" and "Legendary" in mileva.supertypes and mileva.pt == (5, 5) and "Detective" in mileva.subtypes
    assert "indestructible" not in mileva.keywords  # (other creatures only)
    assert "indestructible" in ch(s, mine).keywords and "indestructible" not in ch(s, theirs).keywords  # (Mileva's controller's other creatures only)
    check(s)

"""Wave 110O (second half): single-card wordings, real Oracle text (tests/fixtures/wave110o_cards.json). Every scenario checks the replay and a save and a load.

* 601.2b, 118.8, 615.1: Undergrowth's optional {2}{R} (paid as it is cast) makes its combat damage prevention skip red creatures.
* 603.7a, 701.9, 603.2c: Pure Intentions returns the cards an opponent's spell or ability made you discard (one batch), and itself at the next end step.
* 601.2b, 107.3a, 601.2d: Nahiri's Sacrifice announces X as the mana value of the artifact or creature sacrificed, and divides X damage (none at all if X is 0).
* 608.2c, 118.12a, 101.4: Cleansing gives every land its own round of payments (every player decides in turn order); a land nobody paid for is destroyed.
* 603.7a, 603.7c: Mysterio's tokens are exiled when it leaves the battlefield (a delayed trigger on Mysterio, so none if it already left).
* 614.9, 122.8, 603.10a: Heroic Sacrifice sends damage to you and your creatures to the chosen creature (only while it is on the battlefield); when it dies its counters go to a creature.
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from tests.game_helpers import act
from tests.test_rules_wave34b_activated import stops
from tests.wave9c_kit import build
from tests.wave110o_kit import (  # noqa: F401
    EXTRA,
    card_db,
    card_named,
    cast_on,
    ch,
    check,
    cost,
    full,
    life,
    mana,
    now,
    put,
    put_new,
    settle,
    to_hand,
    to_phase,
)

UNDERGROWTH = "Undergrowth"


@pytest.mark.parametrize("name", [UNDERGROWTH, "Pure Intentions", "Nahiri's Sacrifice", "Cleansing", "Mysterio, Master of Illusion", "Heroic Sacrifice"])
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

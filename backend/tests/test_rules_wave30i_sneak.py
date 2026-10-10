"""Wave 30I: sneak (CR 702.190, 2026-09-25), real Oracle text (tests/fixtures/wave30i_cards.json, from data/cards.sqlite). Every scenario
checks the replay and a save and a load.

* 702.190a: "Sneak [cost]" = "Any time you could cast an instant during your declare blockers step, you may cast this spell by paying [cost]
  and returning an unblocked creature you control to its owner's hand rather than paying this spell's mana cost": an alternative cost (118.9),
  so it is a cast (the spell goes on the stack and can be countered) and the commander tax applies from the command zone (903.8).
* 702.190b, 506.3a, 508.4d: a permanent spell whose sneak cost was paid enters tapped and attacking the same player, planeswalker or battle as
  the returned creature, unblocked, and never "attacked".
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from app.rules.view import hints
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, deck, enable
from tests.test_rules_conditionals import settle, token_of, until
from tests.wave9c_kit import card_named, check, life, mana, pt, put, to_hand, zone_of

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave30i_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="t30i", number=f"S{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def pod(cards, mine=(), theirs=(), commander="Krenko, Mob Boss", players=2):
    """Alice (``commander`` and ``mine`` in her library), Bob (and Carol): rules automation on, Alice's first main phase."""
    setups = [PlayerSetup("Alice", cards=deck(cards, commander, [*((1, n) for n in mine), (20, "Forest")])),
              PlayerSetup("Bob", cards=deck(cards, "Atraxa, Praetors' Voice", [*((1, n) for n in theirs), (20, "Island")]))]
    if players == 3:
        setups.append(PlayerSetup("Carol", cards=deck(cards, "Atraxa, Praetors' Voice", [(20, "Island")])))
    s = GameSession(enable(new_game(setups, shuffle=False)), cards=cards)
    act(s, "p1", type="pass_priority")
    return s


def attackers_declared(s, attacks):
    """Alice's next turn: she attacks as ``attacks`` ((creature, defender) pairs); everyone declares no blocks; she has priority in the declare
    blockers step."""
    act(s, "p1", type="set_prefs", stops_my_turn=["main1", "declare_blockers", "main2"])
    until(s, lambda s: s.state.turn.number >= 3 and s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_attackers"
          and s.state.turn.active_player == "p1")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": c.id, "target": t} for c, t in attacks])
    blocked(s)


def blocked(s, blocks=()):
    """Every defender declares no blocks, except the (blocker, attacker) pairs given; Alice then has priority in the declare blockers step."""
    for _ in range(20):
        d = s.state.rules.decision
        if d is None and s.state.turn.phase == "declare_blockers" and s.state.rules.priority == "p1":
            return
        if d is not None and d.kind == "declare_blockers":
            mine = [{"blocker_id": b.id, "attacker_id": a.id} for b, a in blocks if s.state.cards[b.id].controller == d.player]
            act(s, d.player, type="declare_blockers", blocks=mine)
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("never got to the declare blockers step")


def table(cards, *mine, **kw):
    """Alice with a Grizzly Bears that can attack this turn, ``mine`` in her library; Bob with a Wall; she attacks Bob with the bears, unblocked."""
    s = pod(cards, ["Grizzly Bears", *mine], **kw)
    bear = put(s, "Grizzly Bears")
    wall = token_of(s, "p2", "Wall", "Token Creature — Wall", "0/4")
    attackers_declared(s, [(bear, "p2")])
    return s, bear, wall


def sneak_of(s, cards, c):
    (alt,) = hints(s.state, "p1", cards)["alt_castable"][c.id]
    return alt["id"]


def returned(s, creature):
    """Answer which unblocked creature is returned (when it is asked: with one candidate it is not)."""
    d = s.state.rules.decision
    if d is not None and creature.id in {o.id for o in d.options}:
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[creature.id])


def test_raphael_sneaks_in_tapped_and_attacking_and_deals_double_strike_damage(cards):
    s = pod(cards, ["Grizzly Bears", "Raphael, the Nightwatcher"])
    bear = put(s, "Grizzly Bears")
    raph = to_hand(s, "Raphael, the Nightwatcher")
    mana(s, R=3)
    assert raph.id not in hints(s.state, "p1", cards).get("alt_castable", {})  # 702.190a: only in the declare blockers step
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=raph.id, alt_cost=f"{raph.id}:0")
    attackers_declared(s, [(bear, "p2")])
    mana(s, R=3)  # (the pool empties at the end of every step)
    alt = sneak_of(s, cards, raph)
    act(s, "p1", type="set_prefs", hold_priority=True)
    act(s, "p1", type="cast_spell", card_id=raph.id, alt_cost=alt)
    returned(s, bear)
    assert s.state.zones["stack"] == [raph.id]  # a cast: a spell on the stack that can be responded to (601.2)
    assert zone_of(s, "Grizzly Bears") == "p1:hand"  # (the cost: returned as it was cast)
    act(s, "p1", type="set_prefs", hold_priority=False)
    settle(s)
    r = s.state.cards[raph.id]
    assert r.zone == "p1:battlefield" and r.tapped and r.attacking is not None and r.attacking.id == "p2"  # 702.190b
    until(s, lambda s: s.state.turn.phase == "main2")
    assert life(s, "p2") == 40 - 4  # unblocked (508.4d): "Attacking creatures you control have double strike": 2 + 2
    check(s)


def test_sneak_is_refused_with_no_unblocked_attacker(cards):
    s = pod(cards, ["Grizzly Bears", "Raphael, the Nightwatcher"])
    bear = put(s, "Grizzly Bears")
    wall = token_of(s, "p2", "Wall", "Token Creature — Wall", "0/4")
    raph = to_hand(s, "Raphael, the Nightwatcher")
    act(s, "p1", type="set_prefs", stops_my_turn=["main1", "declare_blockers", "main2"])
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_attackers" and s.state.turn.active_player == "p1")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": bear.id, "target": "p2"}])
    blocked(s, [(wall, bear)])  # the only attacker is blocked: nothing to return
    mana(s, R=3)
    assert raph.id not in hints(s.state, "p1", cards).get("alt_castable", {})
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=raph.id, alt_cost=f"{raph.id}:0")
    assert zone_of(s, "Raphael, the Nightwatcher") == "p1:hand" and zone_of(s, "Grizzly Bears") == "p1:battlefield"
    check(s)


def test_a_sneaked_creature_is_countered_like_any_spell_and_the_creature_stays_in_hand(cards):
    s = pod(cards, ["Grizzly Bears", "Raphael, the Nightwatcher"], ["Counterspell"])
    bear = put(s, "Grizzly Bears")
    counter = to_hand(s, "Counterspell", "p2")
    put(s, "Island", "p2")
    put(s, "Island", "p2")
    raph = to_hand(s, "Raphael, the Nightwatcher")
    act(s, "p2", type="set_prefs", response="on")
    attackers_declared(s, [(bear, "p2")])
    mana(s, R=3)
    act(s, "p1", type="cast_spell", card_id=raph.id, alt_cost=sneak_of(s, cards, raph))
    returned(s, bear)
    assert s.state.zones["stack"] == [raph.id] and s.state.rules.priority == "p2"
    mana(s, "p2", U=2)
    act(s, "p2", type="cast_spell", card_id=counter.id, targets=[raph.id])
    settle(s)
    assert zone_of(s, "Raphael, the Nightwatcher") == "p1:graveyard" and zone_of(s, "Grizzly Bears") == "p1:hand"
    check(s)


def test_enters_triggers_happen_as_it_enters_attacking(cards):
    # Elektra: "When Elektra enters, destroy target creature an opponent controls with power 3 or less." (she enters attacking, not "attacked")
    s, bear, wall = table(cards, "Elektra, Daughter of the Hand")
    elektra = to_hand(s, "Elektra, Daughter of the Hand")
    mana(s, B=3)
    act(s, "p1", type="cast_spell", card_id=elektra.id, alt_cost=sneak_of(s, cards, elektra))
    returned(s, bear)
    settle(s, )
    e = s.state.cards[elektra.id]
    assert e.zone == "p1:battlefield" and e.tapped and e.attacking is not None and e.attacking.id == "p2"
    assert wall.id not in s.state.zones["p2:battlefield"]
    check(s)


def test_hybrid_sneak_cost_and_a_sneaked_creature_is_unblocked(cards):
    # Foot Ninjas: "Sneak {3}{W/B} … When this creature enters, you gain 3 life."
    s, bear, wall = table(cards, "Foot Ninjas")
    ninjas = to_hand(s, "Foot Ninjas")
    mana(s, B=1, C=3)
    act(s, "p1", type="cast_spell", card_id=ninjas.id, alt_cost=sneak_of(s, cards, ninjas))
    returned(s, bear)
    settle(s)
    n = s.state.cards[ninjas.id]
    assert n.zone == "p1:battlefield" and n.attacking is not None and life(s, "p1") == 43
    until(s, lambda s: s.state.turn.phase == "main2")
    assert life(s, "p2") == 40 - pt(s, "Foot Ninjas")[0]  # 506.3d: it entered unblocked and deals its combat damage
    check(s)


def test_a_sorcery_with_sneak_is_cast_at_instant_speed_only_with_the_sneak_cost(cards):
    # Shredder's Technique (a sorcery): "Sneak {B} … Destroy target creature or enchantment. If an enchantment was destroyed this way, you lose 2 life."
    s, bear, wall = table(cards, "Shredder's Technique")
    tech = to_hand(s, "Shredder's Technique")
    mana(s, B=3)
    assert tech.id not in hints(s.state, "p1", cards)["castable"]  # a plain cast of a sorcery: not now (601.3)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=tech.id, targets=[wall.id])
    act(s, "p1", type="cast_spell", card_id=tech.id, targets=[wall.id], alt_cost=sneak_of(s, cards, tech))
    returned(s, bear)
    settle(s)
    assert wall.id not in s.state.zones["p2:battlefield"] and zone_of(s, "Grizzly Bears") == "p1:hand"
    assert zone_of(s, "Shredder's Technique") == "p1:graveyard" and life(s, "p1") == 40
    check(s)


def test_the_riders_see_that_the_sneak_cost_was_paid(cards):
    # Leonardo, Leader in Blue: "When Leonardo enters, if his sneak cost was paid, creatures you control get +2/+0 until end of turn."
    s, bear, wall = table(cards, "Leonardo, Leader in Blue")
    leo = to_hand(s, "Leonardo, Leader in Blue")
    mana(s, W=5)
    act(s, "p1", type="cast_spell", card_id=leo.id, alt_cost=sneak_of(s, cards, leo))
    returned(s, bear)
    settle(s)
    assert s.state.cards[leo.id].attacking is not None and pt(s, "Leonardo, Leader in Blue") == (4, 1)
    check(s)
    s2 = pod(cards, ["Leonardo, Leader in Blue"])
    leo2 = to_hand(s2, "Leonardo, Leader in Blue")
    mana(s2, W=1)
    act(s2, "p1", type="cast_spell", card_id=leo2.id)  # cast for its mana cost: no sneak cost was paid
    settle(s2)
    assert zone_of(s2, "Leonardo, Leader in Blue") == "p1:battlefield" and pt(s2, "Leonardo, Leader in Blue") == (2, 1)
    assert not s2.state.cards[leo2.id].tapped and s2.state.cards[leo2.id].attacking is None
    check(s2)


def test_it_never_attacked_so_its_attack_triggers_stay_quiet(cards):
    # Shredder, Unrelenting: "Whenever Shredder enters or attacks, another target creature you control gains deathtouch until end of turn." (508.4)
    s, bear, wall = table(cards, "Shredder, Unrelenting")
    token_of(s, "p1", "Rat", "Token Creature — Rat", "1/1")
    shredder = to_hand(s, "Shredder, Unrelenting")
    mana(s, B=1, C=3)
    act(s, "p1", type="cast_spell", card_id=shredder.id, alt_cost=sneak_of(s, cards, shredder))
    returned(s, bear)
    settle(s)
    puts = [e for e in s.state.log if "".join(p.t or "" for p in e.parts).startswith("Alice put an ability on the stack")]
    assert s.state.cards[shredder.id].attacking is not None and len(puts) == 1  # the enters trigger, not an attack trigger
    check(s)


def _karai(cards, sneaked):
    s = pod(cards, ["Grizzly Bears", "Hill Giant", "Karai, Future of the Foot"])
    bear = put(s, "Grizzly Bears")
    giant = card_named(s, "Hill Giant")
    act(s, "p1", type="move", card_ids=[giant.id], to={"zone": "graveyard"})
    if sneaked:
        karai = to_hand(s, "Karai, Future of the Foot")
        attackers_declared(s, [(bear, "p2")])
        mana(s, W=2, B=2)
        act(s, "p1", type="cast_spell", card_id=karai.id, alt_cost=sneak_of(s, cards, karai))
        returned(s, bear)
    else:
        karai = to_hand(s, "Karai, Future of the Foot")
        mana(s, W=1, B=1, C=1)
        act(s, "p1", type="cast_spell", card_id=karai.id)  # cast for her mana cost, two turns before she attacks
        settle(s)
        attackers_declared(s, [(karai, "p2")])
    settle(s)
    return s, giant


def test_karai_returns_the_card_to_the_battlefield_only_if_her_sneak_cost_was_paid_this_turn(cards):
    # "Whenever Karai deals combat damage to a player, return target creature card from your graveyard to your hand. If her sneak cost was paid this
    # turn, instead return that card to the battlefield."
    s, giant = _karai(cards, sneaked=True)
    until(s, lambda s: s.state.turn.phase == "main2")
    settle(s)
    assert s.state.cards[giant.id].zone == "p1:battlefield"
    check(s)
    s, giant = _karai(cards, sneaked=False)
    until(s, lambda s: s.state.turn.phase == "main2")
    settle(s)
    assert s.state.cards[giant.id].zone == "p1:hand"
    check(s)


def test_multiplayer_it_attacks_what_the_returned_creature_attacked(cards):
    s = pod(cards, ["Grizzly Bears", "Hill Giant", "Raphael, the Nightwatcher"], players=3)
    bear, giant, raph = put(s, "Grizzly Bears"), put(s, "Hill Giant"), to_hand(s, "Raphael, the Nightwatcher")
    attackers_declared(s, [(bear, "p2"), (giant, "p3")])
    mana(s, R=3)
    act(s, "p1", type="cast_spell", card_id=raph.id, alt_cost=sneak_of(s, cards, raph))
    d = s.state.rules.decision
    assert d is not None and {o.id for o in d.options} == {bear.id, giant.id}  # either unblocked creature may be returned
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[giant.id])
    settle(s)
    r = s.state.cards[raph.id]
    assert r.zone == "p1:battlefield" and r.attacking is not None and r.attacking.id == "p3"  # 702.190b: Carol, not Bob
    assert s.state.cards[bear.id].attacking.id == "p2" and zone_of(s, "Hill Giant") == "p1:hand"
    check(s)


def test_a_commander_sneaks_in_from_the_command_zone_paying_the_tax(cards):
    s = pod(cards, ["Grizzly Bears"], commander="Raphael, the Nightwatcher")
    bear = put(s, "Grizzly Bears")
    raph = next(c for c in s.state.cards.values() if c.name == "Raphael, the Nightwatcher")
    assert raph.zone == "p1:command"
    act(s, "p1", type="commander_tax", commander=raph.commander_key, value=2)  # cast once before: {2} more (903.8)
    attackers_declared(s, [(bear, "p2")])
    mana(s, R=3)
    assert raph.id not in hints(s.state, "p1", cards).get("alt_castable", {})  # {1}{R}{R} + {2}
    mana(s, C=2)
    act(s, "p1", type="cast_spell", card_id=raph.id, alt_cost=sneak_of(s, cards, raph))
    returned(s, bear)
    settle(s)
    r = s.state.cards[raph.id]
    assert r.zone == "p1:battlefield" and r.attacking is not None and s.state.players["p1"].commander_tax[raph.commander_key] == 4
    check(s)

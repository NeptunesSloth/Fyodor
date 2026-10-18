"""Wave 30M: durations and "doesn't untap" wordings (CR 2026-09-25), real Oracle text
(tests/fixtures/wave30m_durations_cards.json, from data/cards.sqlite). Every scenario checks the replay and a save and a load.

* 611.2a / 500.4: "Until your next turn" (and "until the beginning of your next upkeep") ends as *that player's* next turn begins: with three
  players the opponents' turns in between do not end it. A permission to play a card / to cast as though it had flash is such an effect.
* 611.2b: "for as long as you control ~ / it has a flood counter on it" ends the moment that stops being true, and does not start again
  when it becomes true later (a new object, 400.7, is a different one).
* 502.3: "doesn't untap during your / its controller's / that player's next untap step" keeps a tapped permanent tapped through exactly one
  untap step of that player, whoever else's untap steps come first (500.1 turn order).
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
from app.rules import coverage
from app.rules.casting import castable
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, deck, enable
from tests.wave9c_kit import build, card_named, check, mana, put, to_hand

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave30m_durations_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w30m", number=f"M{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


@pytest.mark.parametrize("name", [c["name"] for c in DATA])
def test_every_card_is_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def three(cards, a=(), b=(), c=()):
    """Alice, Bob and Carol; each deck is the named cards plus basic lands."""
    decks = [deck(cards, "Krenko, Mob Boss", [*((1, n) for n in a), (20, "Forest")]),
             deck(cards, "Atraxa, Praetors' Voice", [*((1, n) for n in b), (20, "Island")]),
             deck(cards, "Atraxa, Praetors' Voice", [*((1, n) for n in c), (20, "Island")])]
    s = GameSession(enable(new_game([PlayerSetup(n, cards=d) for n, d in zip(("Alice", "Bob", "Carol"), decks, strict=True)],
                                    shuffle=False)), cards=cards)
    act(s, "p1", type="pass_priority")
    return s


def settle(s, prefer=(), limit=60):
    """Resolve everything; a decision is answered with the first of ``prefer`` it offers (card names or option ids), else its first options."""
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None:
            ids = [o.id for o in d.options]
            want = [o.id for p in prefer for o in d.options if p in (o.id, o.label, s.state.cards[o.card_id].name if o.card_id in s.state.cards else None)]
            pick = want[: max(1, d.min_choices)] if len(want) >= max(1, d.min_choices) else ids[: max(1, d.min_choices)]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=pick)
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return
    raise AssertionError("never settled")


def to_phase(s, phase, turn=None, limit=200):
    """Pass priority (no attackers, no blockers) until ``phase`` (of turn ``turn``) is reached (its triggers may be on the stack)."""
    for _ in range(limit):
        d = s.state.rules.decision
        if s.state.turn.phase == phase and turn in (None, s.state.turn.number):
            return
        if d is not None and d.kind in ("declare_attackers", "declare_blockers"):
            act(s, d.player, type=d.kind, **({"attackers": []} if d.kind == "declare_attackers" else {"blocks": []}))
        elif d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError(f"never reached {phase} of turn {turn} (at {s.state.turn.phase} of turn {s.state.turn.number})")


def stops(s, *steps):
    """Alice is given priority in these steps of every turn (hers and the others')."""
    act(s, "p1", type="set_stops", own=list(steps), others=list(steps), smart_pass=False)


def put_in(s, name, where, pid="p1", position=None):
    c = card_named(s, name, pid)
    payload = {"type": "move", "card_ids": [c.id], "to": {"player": pid, "zone": where}}
    if position:
        payload["position"] = position
    act(s, pid, **payload)
    return s.state.cards[c.id]


def chars(s, c):
    return Plan(s.state, c.controller, s.cards, None).ch(s.state.cards[c.id])


def can_cast(s, pid, c):
    return castable(s.state, pid, s.state.cards[c.id], s.cards, check_priority=False)


# --- Form 1: "Until your next turn, …" and "for as long as you control ~" permissions ----------------------------------------------


def test_teferi_time_raveler_flash_lasts_until_alices_next_turn_not_the_next_turn(cards):
    """Teferi, Time Raveler +1: "Until your next turn, you may cast sorcery spells as though they had flash." With three players Bob's and Carol's
    turns come first: the permission is still there through both, and gone as Alice's own next turn begins (500.4, 611.2a)."""
    s = three(cards, ["Teferi, Time Raveler", "Rampant Growth"])
    teferi = put(s, "Teferi, Time Raveler")
    act(s, "p1", type="activate_ability", card_id=teferi.id, ability=1)
    settle(s)
    growth = to_hand(s, "Rampant Growth")
    stops(s, "upkeep")
    to_phase(s, "upkeep", turn=2)
    mana(s, G=1, C=1)
    assert can_cast(s, "p1", growth)  # (Bob's upkeep: a sorcery at instant speed)
    check(s)
    to_phase(s, "upkeep", turn=3)
    mana(s, G=1, C=1)
    assert can_cast(s, "p1", growth)  # (Carol's turn: still Alice's "until your next turn")
    to_phase(s, "upkeep", turn=4)
    mana(s, G=1, C=1)
    assert not can_cast(s, "p1", growth), "Alice's own next turn began: the permission ended"
    to_phase(s, "main1", turn=4)
    mana(s, G=1, C=1)
    assert can_cast(s, "p1", growth)  # (an ordinary sorcery-speed cast)
    check(s)


def test_elkin_bottle_card_is_playable_on_the_opponents_turn_but_not_from_the_next_upkeep(cards):
    """Elkin Bottle: "Exile the top card of your library. Until the beginning of your next upkeep, you may play that card." A Lightning Bolt is cast
    from exile during Bob's turn (a nonland card with instant speed)."""
    s = build(cards, ["Elkin Bottle", "Lightning Bolt"], [])
    bottle = put(s, "Elkin Bottle")
    bolt = put_in(s, "Lightning Bolt", "library", position="top")
    mana(s, C=3)
    act(s, "p1", type="activate_ability", card_id=bottle.id, ability=0)
    settle(s)
    assert s.state.cards[bolt.id].zone == "p1:exile"
    stops(s, "upkeep")
    to_phase(s, "upkeep", turn=2)
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])
    settle(s)
    assert s.state.players["p2"].life == 37 and s.state.cards[bolt.id].zone == "p1:graveyard"
    check(s)


def test_elkin_bottle_permission_is_gone_when_the_next_upkeep_begins(cards):
    """The same card, not cast: from Alice's next upkeep on it stays in exile for good (611.2a: "until" is the duration, nothing brings it back)."""
    s = build(cards, ["Elkin Bottle", "Lightning Bolt"], [])
    bottle = put(s, "Elkin Bottle")
    bolt = put_in(s, "Lightning Bolt", "library", position="top")
    mana(s, C=3)
    act(s, "p1", type="activate_ability", card_id=bottle.id, ability=0)
    settle(s)
    stops(s, "upkeep")
    to_phase(s, "upkeep", turn=2)
    mana(s, R=1)
    assert can_cast(s, "p1", bolt)
    to_phase(s, "upkeep", turn=3)
    mana(s, R=1)
    assert not can_cast(s, "p1", bolt) and s.state.cards[bolt.id].zone == "p1:exile"
    check(s)


def test_lightning_security_sergeant_card_is_playable_only_while_you_control_lightning(cards):
    """Lightning, Security Sergeant: "exile the top card of your library. You may play that card for as long as you control Lightning." (611.2b)
    A permanent that leaves and comes back is a new object (400.7): the card exiled with the old one can't be played."""
    s = build(cards, ["Lightning, Security Sergeant", "Grizzly Bears"], [])
    lightning = put(s, "Lightning, Security Sergeant")
    bears = put_in(s, "Grizzly Bears", "library", position="top")
    to_phase(s, "declare_attackers", turn=3)
    top = s.state.zones["p1:library"][0]
    put_in(s, "Grizzly Bears", "library", position="top") if top != bears.id else None
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": lightning.id, "target": "p2"}])
    to_phase(s, "main2")
    assert s.state.players["p2"].life == 38
    exiled = [c for c in s.state.zones["p1:exile"]]
    assert len(exiled) == 1
    mana(s, G=2)
    assert can_cast(s, "p1", s.state.cards[exiled[0]])
    check(s)
    put_in(s, "Lightning, Security Sergeant", "hand")  # (it left: 611.2b)
    assert not can_cast(s, "p1", s.state.cards[exiled[0]])
    put_in(s, "Lightning, Security Sergeant", "battlefield")  # (a new object: the permission does not come back)
    assert not can_cast(s, "p1", s.state.cards[exiled[0]])
    check(s)


def intet_table(cards):
    """Alice attacks with Intet on turn 3 and pays {2}{U}: the Grizzly Bears that was on top of her library is exiled face down."""
    s = build(cards, ["Intet, the Dreamer", "Grizzly Bears", "Island", "Island", "Island"], [])
    intet = put(s, "Intet, the Dreamer")
    for land in [c for c in s.state.cards.values() if c.name == "Island" and c.owner == "p1"][:3]:
        act(s, "p1", type="move", card_ids=[land.id], to={"player": "p1", "zone": "battlefield"})
    to_phase(s, "declare_attackers", turn=3)
    bears = put_in(s, "Grizzly Bears", "library", position="top")  # (after Alice's draw for the turn)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": intet.id, "target": "p2"}])
    settle(s, ["yes"])
    to_phase(s, "main2")
    assert s.state.cards[bears.id].zone == "p1:exile" and s.state.cards[bears.id].face_down
    return s, bears


def test_intet_the_dreamer_plays_the_exiled_card_free_while_intet_remains_on_the_battlefield(cards):
    """Intet, the Dreamer (a commander): "… exile the top card of your library face down. You may look at that card for as long as it remains
    exiled. You may play that card without paying its mana cost for as long as Intet remains on the battlefield." (611.2b)"""
    s, bears = intet_table(cards)
    check(s)
    act(s, "p1", type="cast_spell", card_id=bears.id, free=True)  # (no mana needed: it is free, 118.9)
    settle(s)
    assert s.state.cards[bears.id].zone == "p1:battlefield" and not s.state.cards[bears.id].face_down
    check(s)


def test_intet_the_dreamers_card_stays_in_exile_once_intet_has_left_even_if_it_comes_back(cards):
    """Once Intet has left, the card stays face down in exile for good: a new Intet is a new object (400.7), the duration did not start again."""
    s, bears = intet_table(cards)
    put_in(s, "Intet, the Dreamer", "hand")
    put_in(s, "Intet, the Dreamer", "battlefield")
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=bears.id, free=True)
    assert s.state.cards[bears.id].zone == "p1:exile"
    check(s)


# --- Form 2: "for as long as it has a flood counter on it" -------------------------------------------------------------------------


def test_aquitects_will_makes_the_land_an_island_only_while_it_has_the_counter(cards):
    """Aquitect's Will: "Put a flood counter on target land. That land is an Island in addition to its other types for as long as it has a flood
    counter on it." (305.7 / 205.1b: it is still a Forest; 611.2b: when the counter is gone the effect has ended and a new counter does not
    start it again.) A land that left and came back is a new object (400.7)."""
    s = build(cards, ["Aquitect's Will"], [])
    forest = put(s, "Forest")
    to_hand(s, "Aquitect's Will")
    mana(s, U=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Aquitect's Will").id, targets=[forest.id])
    settle(s)
    assert s.state.cards[forest.id].counters == {"flood": 1}
    assert {"Forest", "Island"} <= set(chars(s, forest).subtypes), chars(s, forest).subtypes
    check(s)
    act(s, "p1", type="counter", card_ids=[forest.id], kind="flood", delta=-1)
    act(s, "p1", type="pass_priority")  # (the next look at the table ends it, 611.2b)
    assert "Island" not in chars(s, forest).subtypes and "Forest" in chars(s, forest).subtypes
    act(s, "p1", type="counter", card_ids=[forest.id], kind="flood", delta=1)
    act(s, "p1", type="pass_priority")
    assert "Island" not in chars(s, forest).subtypes, "the effect ended with the first counter"
    check(s)


def test_xolatoyac_land_stays_an_island_through_the_turns_and_loses_it_when_it_leaves(cards):
    """Xolatoyac, the Smiling Flood (a commander): the same wording on its enters trigger."""
    s = build(cards, ["Xolatoyac, the Smiling Flood"], [])
    forest = put(s, "Forest")
    to_hand(s, "Xolatoyac, the Smiling Flood")
    mana(s, G=5, U=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Xolatoyac, the Smiling Flood").id)
    settle(s, [forest.id])
    assert "Island" in chars(s, forest).subtypes
    to_phase(s, "main1", turn=3)
    assert "Island" in chars(s, forest).subtypes  # (not an "until end of turn" effect)
    check(s)
    put_in(s, "Forest", "hand")
    back = put_in(s, "Forest", "battlefield")
    assert "Island" not in chars(s, back).subtypes and not back.counters
    check(s)


# --- Form 3: "doesn't untap during your / that player's next untap step" -------------------------------------------------------------


def test_reveka_stays_tapped_through_exactly_one_of_her_controllers_untap_steps(cards):
    """Reveka, Wizard Savant (a commander): "{T}: Reveka deals 2 damage to any target and doesn't untap during your next untap step." (502.3)
    Bob's and Carol's untap steps are not Alice's: she stays tapped through Alice's next one and untaps in the one after."""
    s = three(cards, ["Reveka, Wizard Savant"])
    reveka = put(s, "Reveka, Wizard Savant")
    to_phase(s, "main1", turn=4)
    act(s, "p1", type="activate_ability", card_id=reveka.id, ability=0, targets=["p2"])
    settle(s)
    assert s.state.players["p2"].life == 38 and s.state.cards[reveka.id].tapped
    to_phase(s, "main1", turn=5)  # (Bob's untap step)
    assert s.state.cards[reveka.id].tapped
    to_phase(s, "main1", turn=7)  # (Alice's next untap step: she stays tapped)
    assert s.state.cards[reveka.id].tapped
    check(s)
    to_phase(s, "main1", turn=10)
    assert not s.state.cards[reveka.id].tapped
    check(s)


def test_misstep_keeps_only_the_target_players_creatures_tapped_through_their_next_untap_step(cards):
    """Misstep: "Creatures target player controls don't untap during that player's next untap step." Targeting Carol: Bob's tapped creature
    untaps in his own untap step in between; Carol's stays tapped through hers (including a creature she has by then), and untaps after."""
    s = three(cards, ["Misstep"], ["Grizzly Bears"], ["Grizzly Bears"])
    bears, giant = put(s, "Grizzly Bears", "p2"), put(s, "Grizzly Bears", "p3")
    act(s, "p2", type="tap", card_ids=[bears.id])
    act(s, "p3", type="tap", card_ids=[giant.id])
    to_hand(s, "Misstep")
    mana(s, U=1, C=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Misstep").id, targets=["p3"])
    settle(s)
    to_phase(s, "main1", turn=2)
    assert not s.state.cards[bears.id].tapped
    to_phase(s, "main1", turn=3)
    assert s.state.cards[giant.id].tapped
    check(s)
    to_phase(s, "main1", turn=6)
    assert not s.state.cards[giant.id].tapped
    check(s)


def test_winterthorn_blessing_taps_the_creature_and_keeps_it_tapped(cards):
    """Winterthorn Blessing: "Tap up to one target creature you don't control, and that creature doesn't untap during its controller's next untap
    step." (the creature is the one tapped; its controller's untap step, not Alice's)."""
    s = build(cards, ["Winterthorn Blessing", "Grizzly Bears"], ["Grizzly Bears"])
    mine, theirs = put(s, "Grizzly Bears"), put(s, "Grizzly Bears", "p2")
    to_hand(s, "Winterthorn Blessing")
    mana(s, G=1, U=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Winterthorn Blessing").id, targets=[mine.id, theirs.id], target_counts=[1, 1])
    settle(s)
    assert s.state.cards[theirs.id].tapped and s.state.cards[mine.id].counters == {"+1/+1": 1}
    to_phase(s, "main1", turn=2)
    assert s.state.cards[theirs.id].tapped
    check(s)
    to_phase(s, "main1", turn=4)
    assert not s.state.cards[theirs.id].tapped
    check(s)


def test_homarid_warrior_gains_shroud_and_does_not_untap(cards):
    s = build(cards, ["Homarid Warrior"], [])
    warrior = put(s, "Homarid Warrior")
    mana(s, U=1)
    act(s, "p1", type="activate_ability", card_id=warrior.id, ability=0)
    settle(s)
    assert s.state.cards[warrior.id].tapped
    to_phase(s, "main1", turn=3)
    assert s.state.cards[warrior.id].tapped
    check(s)
    to_phase(s, "main1", turn=5)
    assert not s.state.cards[warrior.id].tapped
    check(s)

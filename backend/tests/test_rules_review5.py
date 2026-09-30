"""Regression tests for independent review 5: control, players leaving the game, and object identity.

- 701.21a: "sacrifice it" does nothing to a permanent its controller no longer controls.
- 800.4a / 610.3: a source that left the game with its owner returns what it exiled "until ~
  leaves the battlefield"; a card owned by the player who left stays where it is (800.4b).
- 800.4a / 611.2b: "for as long as …" effects end when their source leaves the game with its owner.
- 800.4m: "until your next turn" of a player who left lasts until that turn would have begun.
- 800.4a: counts ignore the zones of a player who left the game.
- 400.7: a card that left exile and came back is a new object; "until ~ leaves" doesn't return it.
- Table markers belong to the effect that wrote them: ending one effect leaves another's marker.
"""

from __future__ import annotations

from app.game.factory import PlayerSetup, new_game
from app.game.rules_state import ContinuousEffect
from app.game.session import GameSession
from tests.game_helpers import act, deck, enable
from tests.test_rules_attachments import build, ch, named, token
from tests.test_rules_delayed import activate, next_end_step, on_battlefield, reloaded, rules
from tests.test_rules_effects import mana, replay_matches
from tests.test_rules_suspend import until

JAILER = "{1}: Exile target artifact or creature an opponent controls until ~ leaves the battlefield."
BLESSER = "{1}: Target creature gets +2/+2 until your next turn."
MARKER = "until your next turn"


def build3(cards, *names):
    """Alice (p1, active, in her main phase), Bob (p2, with Grizzly Bears) and Carol (p3)."""
    alice = deck(cards, "Krenko, Mob Boss", [*((1, n) for n in names), (9, "Forest")])
    bob = deck(cards, "Atraxa, Praetors' Voice", [(1, "Grizzly Bears"), (9, "Island")])
    carol = deck(cards, "Krenko, Mob Boss", [(10, "Mountain")])
    s = GameSession(enable(new_game([PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=bob),
                                     PlayerSetup("Carol", cards=carol)], shuffle=False)), cards=cards)
    act(s, "p1", type="pass_priority")  # → Alice's main phase
    return s


def main_phase_of(s, pid):
    until(s, lambda s: s.state.turn.active_player == pid and s.state.turn.phase == "main1"
          and rules(s).priority == pid and not s.state.zones.get("stack"), limit=120)


def markers(s, card):
    return [m for m in s.state.cards[card.id].effects if m.text == MARKER]


# -- 701.21a -----------------------------------------------------------------------------------------
def test_sacrifice_it_does_nothing_once_another_player_controls_it(cards):
    # Lowland Oaf / Sneak Attack-style: "Sacrifice it at the beginning of the next end step" — a
    # player can't sacrifice a permanent they don't control.
    s = build(cards, "Llanowar Elves")
    elves = on_battlefield(s, "Llanowar Elves")
    src = token(s, "p1", "Firebreather", "2/2",
                text="{1}: Target creature gets +2/+0 until end of turn. Sacrifice it at the beginning of the next end step.")
    activate(s, src, targets=[elves.id])
    assert len(rules(s).delayed) == 1
    act(s, "p1", type="set_controller", card_ids=[elves.id], player="p2")  # Threaten-style, same object
    next_end_step(s)
    assert s.state.cards[elves.id].zone == "p2:battlefield"
    replay_matches(s)


# -- 800.4a, 610.3: "exile … until ~ leaves the battlefield" -----------------------------------------
def test_exile_until_returns_when_its_source_leaves_the_game_with_its_owner(cards):
    s = build3(cards, "Banisher Priest")
    bears = named(s, "Grizzly Bears")
    act(s, "p2", type="move", card_ids=[bears.id], to={"player": "p2", "zone": "battlefield"})
    priest = named(s, "Banisher Priest")
    act(s, "p1", type="move", card_ids=[priest.id], to={"zone": "hand"})
    mana(s, W=2, C=1)
    act(s, "p1", type="cast_spell", card_id=priest.id)
    until(s, lambda s: rules(s).decision is not None or s.state.cards[bears.id].zone == "p2:exile")
    d = rules(s).decision
    if d is not None:
        act(s, "p1", type="choose", decision_id=d.id, option_ids=[bears.id])
    until(s, lambda s: not s.state.zones.get("stack"))
    assert s.state.cards[bears.id].zone == "p2:exile"
    act(s, "p1", type="concede")  # the Priest leaves the game with Alice (800.4a)
    assert s.state.cards[bears.id].zone == "p2:battlefield"  # 610.3: the Bears come back at once
    assert not rules(s).linked_exile
    replay_matches(s)


def test_a_card_owned_by_the_player_who_left_stays_in_exile(cards):
    s = build3(cards, "Llanowar Elves")
    elves = on_battlefield(s, "Llanowar Elves")
    main_phase_of(s, "p2")
    jailer = token(s, "p2", "Jailer", "2/2", text=JAILER)
    activate(s, jailer, pid="p2", targets=[elves.id])
    assert s.state.cards[elves.id].zone == "p1:exile"
    act(s, "p1", type="concede")  # Alice's Elves left the game with her
    act(s, "p2", type="set_damage", card_ids=[jailer.id], value=2)
    act(s, rules(s).priority, type="pass_priority")  # the Jailer dies: its link ends
    assert jailer.id not in s.state.cards
    assert s.state.cards[elves.id].zone == "p1:exile"  # 800.4b: never onto the battlefield under a player who left
    replay_matches(s)


# -- 400.7: the link is to the object in exile --------------------------------------------------------
def test_a_card_that_left_exile_and_came_back_is_not_returned(cards):
    s = build(cards, "Grizzly Bears")  # (Alice's Bears, on Bob's side: a creature an opponent controls)
    bears = named(s, "Grizzly Bears")
    act(s, "p1", type="move", card_ids=[bears.id], to={"player": "p2", "zone": "battlefield"})
    jailer = token(s, "p1", "Jailer", "2/2", text=JAILER)
    activate(s, jailer, targets=[bears.id])
    assert s.state.cards[bears.id].zone == "p1:exile"
    act(s, "p1", type="move", card_ids=[bears.id], to={"player": "p1", "zone": "hand"})
    act(s, "p1", type="move", card_ids=[bears.id], to={"player": "p1", "zone": "exile"})  # back: a new object
    act(s, "p1", type="set_damage", card_ids=[jailer.id], value=2)
    act(s, rules(s).priority, type="pass_priority")  # the Jailer dies
    assert jailer.id not in s.state.cards
    assert s.state.cards[bears.id].zone == "p1:exile"  # not the object that was exiled: it stays
    replay_matches(s)


# -- 800.4a, 611.2b: "for as long as …" --------------------------------------------------------------
def test_for_as_long_as_ends_when_the_source_leaves_the_game_with_its_owner(cards):
    # Alice's nontoken permanent stays on her side of the table as a record after she leaves, but
    # it has left the game (800.4a), so "for as long as you control ~" / "… remains on the
    # battlefield" effects from it end. (Set up directly: the fixture set has no such card.)
    s = build3(cards, "Llanowar Elves")
    source = on_battlefield(s, "Llanowar Elves")
    bear = token(s, "p3", "Carol's Bear")
    oid = s.state.rules.object_id
    for i, duration in enumerate(("source_controlled", "source_on_battlefield")):
        s.state.rules.effects.append(ContinuousEffect(
            id=f"test{i}", affected=[oid(bear.id)], layer="6", source=oid(source.id), source_card=source.id,
            controller="p1", add_keywords=["indestructible"], duration=duration, until_player="p1"))
    assert "indestructible" in ch(s, bear).keywords
    act(s, "p1", type="concede")
    assert not rules(s).effects and "indestructible" not in ch(s, bear).keywords


# -- 800.4m: "until your next turn" of a player who left ----------------------------------------------
def test_until_your_next_turn_of_a_player_who_left_ends_when_that_turn_would_have_begun(cards):
    s = build3(cards, "Llanowar Elves")
    elves = on_battlefield(s, "Llanowar Elves")
    main_phase_of(s, "p2")
    blesser = token(s, "p2", "Blesser", "2/2", text=BLESSER)
    activate(s, blesser, pid="p2", targets=[elves.id])
    assert ch(s, elves).pt == (3, 3)
    act(s, "p2", type="concede")  # during Bob's own turn
    assert ch(s, elves).pt == (3, 3)  # neither expires at once …
    until(s, lambda s: s.state.turn.active_player == "p1", limit=120)  # Carol's turn, then Alice's
    assert ch(s, elves).pt == (3, 3) and markers(s, elves)
    s = reloaded(s)
    until(s, lambda s: s.state.turn.active_player == "p3", limit=120)  # Bob's turn would have begun first
    assert ch(s, elves).pt == (1, 1) and not rules(s).effects  # … nor lasts indefinitely
    assert not markers(s, elves)
    replay_matches(s)


# -- 800.4a: counts --------------------------------------------------------------------------------
def test_counts_ignore_the_zones_of_a_player_who_left(cards):
    # Tarmogoyf / "cards in all graveyards"-style counts: Bob's graveyard left the game with him.
    s = build3(cards, "Llanowar Elves")
    elves = on_battlefield(s, "Llanowar Elves")
    islands = [c.id for c in s.state.cards.values() if c.name == "Island" and c.owner == "p2"][:2]
    act(s, "p2", type="move", card_ids=islands, to={"player": "p2", "zone": "graveyard"})
    mountain = next(c.id for c in s.state.cards.values() if c.name == "Mountain" and c.owner == "p3")
    act(s, "p3", type="move", card_ids=[mountain], to={"player": "p3", "zone": "graveyard"})
    act(s, "p2", type="concede")
    counter = token(s, "p1", "Counter", "2/2",
                    text="{1}: Target creature gets +X/+0 until end of turn, where X is the number of cards in all graveyards.")
    activate(s, counter, targets=[elves.id])
    assert ch(s, elves).pt == (2, 1)  # Carol's Mountain only
    replay_matches(s)


# -- markers ---------------------------------------------------------------------------------------
def test_ending_one_effect_keeps_another_effects_marker(cards):
    s = build(cards, "Llanowar Elves")
    elves = on_battlefield(s, "Llanowar Elves")
    mine = token(s, "p1", "Blesser", "2/2", text=BLESSER)
    activate(s, mine, targets=[elves.id])
    main_phase_of(s, "p2")
    theirs = token(s, "p2", "Other Blesser", "2/2", text=BLESSER)
    activate(s, theirs, pid="p2", targets=[elves.id])
    assert ch(s, elves).pt == (5, 5) and len(markers(s, elves)) == 2
    until(s, lambda s: s.state.turn.active_player == "p1", limit=120)  # Alice's effect ends (500.4)
    assert ch(s, elves).pt == (3, 3) and len(markers(s, elves)) == 1  # Bob's stays, with its marker
    s = reloaded(s)
    until(s, lambda s: s.state.turn.active_player == "p2", limit=120)
    assert ch(s, elves).pt == (1, 1) and not markers(s, elves)
    replay_matches(s)

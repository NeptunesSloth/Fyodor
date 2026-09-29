"""Simultaneous events and one-event-per-source (CR 2026-09-25): 702.15e (each lifelink source is
its own life gain event, 119.9), 101.4 (APNAP choices, then the actions happen at once), 603.2c
("one or more" triggers once per event), 701.21a / 701.9a (sacrifice and discard go to the
owner's graveyard), 701.23b/d (search: a stated quality may find nothing; "a card" must find
one), 611.2c (a rule-modifying effect from a resolved ability isn't locked to a set of objects)."""

from __future__ import annotations

from app.game.state import zone_key
from app.rules import events
from app.rules.plan import Plan
from tests.game_helpers import act, find, zone
from tests.test_rules_attachments import build, mana, token
from tests.test_rules_combat import attack, automate, creature, table
from tests.test_rules_effects import pass_until_stack_empty, replay_matches


def activate(s, card, **kw):
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=card.id, ability=0, **kw)
    pass_until_stack_empty(s)


def permanent(s, pid, name, kind, text):
    act(s, pid, type="create_token", player=pid, token={"name": name, "type_line": f"Token {kind} — Test", "text": text})
    return next(c for c in s.state.cards.values() if c.name == name and c.owner == pid)


def zone_batches(s, *card_ids):
    return {e.batch for e in s.state.rules.events if e.card in card_ids and e.from_zone != e.to_zone and e.from_zone}


# -- lifelink: one life gain event per source (702.15e) ----------------------------------
def test_two_lifelinkers_are_two_life_gain_events(cards):
    s = table(cards)
    a = creature(s, "p1", "Lifelinker A", "2/2", "Lifelink")
    b = creature(s, "p1", "Lifelinker B", "3/3", "Lifelink")
    pet = creature(s, "p1", "Pet", "1/1", "Whenever you gain life, put a +1/+1 counter on this creature.")
    automate(s)
    attack(s, (a, "p2"), (b, "p2"))
    pass_until_stack_empty(s)
    pass_until_stack_empty(s)
    st = s.state
    assert st.players["p2"].life == 35 and st.players["p1"].life == 45  # the totals are unchanged
    assert st.cards[pet.id].counters == {"+1/+1": 2}  # two sources, two events, two triggers
    gains = [e for e in st.rules.events if e.kind == "life_gain"]
    assert [e.amount for e in gains] == [2, 3] and len({e.batch for e in gains}) == 1  # simultaneous
    replay_matches(s)


def test_one_lifelinker_is_one_event(cards):
    s = table(cards)
    a = creature(s, "p1", "Lifelinker", "2/2", "Lifelink")
    plain = creature(s, "p1", "Plain", "3/3")
    pet = creature(s, "p1", "Pet", "1/1", "Whenever you gain life, put a +1/+1 counter on this creature.")
    automate(s)
    attack(s, (a, "p2"), (plain, "p2"))
    pass_until_stack_empty(s)
    assert s.state.players["p1"].life == 42 and s.state.cards[pet.id].counters == {"+1/+1": 1}
    replay_matches(s)


# -- bounce: all at once, each to its owner's hand ----------------------------------------
def test_mass_bounce_is_one_event(cards):
    assert events.parse_condition("one or more creatures you control leave the battlefield")["aggregate"]
    s = build(cards)
    permanent(s, "p1", "Watcher", "Enchantment", "Whenever one or more creatures you control leave the battlefield, you gain 1 life.")
    src = permanent(s, "p1", "Evacuator", "Artifact", "{1}: Return all creatures you control to their owners' hands.")
    token(s, "p1", "A")
    token(s, "p1", "B")
    atraxa = find(s.state, "Atraxa, Praetors' Voice", "p2")
    act(s, "p2", type="move", card_ids=[atraxa.id], to={"zone": "battlefield"})
    act(s, "p2", type="set_controller", card_ids=[atraxa.id], player="p1")
    activate(s, src)
    pass_until_stack_empty(s)
    st = s.state
    assert st.cards[atraxa.id].zone == "p2:hand"  # its owner's hand
    assert not [c for c in st.cards.values() if c.zone == "p1:battlefield" and c.name in ("A", "B")]
    assert st.players["p1"].life == 41  # one batch: "one or more" triggers once (603.2c)
    replay_matches(s)


# -- sacrifice: APNAP choices, then all at once (101.4) -----------------------------------
def test_each_player_sacrifices_simultaneously(cards):
    s = build(cards)
    permanent(s, "p1", "Watcher", "Enchantment", "Whenever one or more creatures die, you gain 1 life.")
    a = token(s, "p1", "A")
    b = token(s, "p1", "B")
    c = token(s, "p2", "C")
    d = token(s, "p2", "D")
    src = permanent(s, "p1", "Edict", "Artifact", "{1}: Each player sacrifices a creature.")
    activate(s, src)
    first = s.state.rules.decision
    assert first.player == "p1" and {o.id for o in first.options} == {a.id, b.id}  # active player first
    act(s, "p1", type="choose", decision_id=first.id, option_ids=[a.id])
    assert s.state.cards[a.id].zone == "p1:battlefield"  # not yet: everyone chooses first
    second = s.state.rules.decision
    assert second.player == "p2" and {o.id for o in second.options} == {c.id, d.id}
    act(s, "p2", type="choose", decision_id=second.id, option_ids=[d.id])
    pass_until_stack_empty(s)
    pass_until_stack_empty(s)
    st = s.state
    assert a.id not in st.cards and d.id not in st.cards and b.id in st.cards and c.id in st.cards
    assert st.players["p1"].life == 41  # both died in one event
    replay_matches(s)


def test_forced_sacrifices_are_simultaneous(cards):
    s = build(cards)
    permanent(s, "p1", "Watcher", "Enchantment", "Whenever one or more creatures die, you gain 1 life.")
    token(s, "p1", "A")
    token(s, "p2", "C")
    src = permanent(s, "p1", "Edict", "Artifact", "{1}: Each player sacrifices a creature.")
    activate(s, src)
    pass_until_stack_empty(s)
    st = s.state
    assert not [c for c in st.cards.values() if c.name in ("A", "C")]
    assert st.players["p1"].life == 41
    replay_matches(s)


# -- discard: APNAP choices, then all at once ---------------------------------------------
def test_each_player_discards_simultaneously(cards):
    s = build(cards)
    act(s, "p1", type="draw", player="p1", count=2)
    act(s, "p2", type="draw", player="p2", count=2)
    src = token(s, "p1", "Wheel", text="{1}: Each player discards a card.")
    activate(s, src)
    first = s.state.rules.decision
    assert first.player == "p1"
    mine = first.options[0].id
    act(s, "p1", type="choose", decision_id=first.id, option_ids=[mine])
    assert s.state.cards[mine].zone == "p1:hand"  # not yet discarded
    second = s.state.rules.decision
    assert second.player == "p2" and s.view("p1")["rules"]["decision"].get("options") is None
    theirs = second.options[0].id
    act(s, "p2", type="choose", decision_id=second.id, option_ids=[theirs])
    pass_until_stack_empty(s)
    st = s.state
    assert st.cards[mine].zone == "p1:graveyard" and st.cards[theirs].zone == "p2:graveyard"
    assert len(zone_batches(s, mine, theirs)) == 1  # one event batch
    replay_matches(s)


# -- search: "a card" must find one (701.23d); a stated quality may find none (701.23b) --
def test_search_for_a_card_must_find_one(cards):
    s = build(cards)
    src = token(s, "p1", "Tutor", text="{1}: Search your library for a card, put it into your hand, then shuffle.")
    activate(s, src)
    d = s.state.rules.decision
    assert (d.min_choices, d.max_choices) == (1, 1)
    assert s.view("p2")["rules"]["decision"].get("options") is None  # private
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[d.options[0].id])
    pass_until_stack_empty(s)
    replay_matches(s)


def test_search_with_a_quality_may_find_nothing(cards):
    s = build(cards)
    src = token(s, "p1", "Seeker", text="{1}: Search your library for a basic land card, put it into your hand, then shuffle.")
    activate(s, src)
    assert s.state.rules.decision.min_choices == 0


def test_search_for_a_card_in_an_empty_library(cards):
    s = build(cards)
    library = zone(s.state, "p1", "library")
    act(s, "p1", type="move", card_ids=list(library), to={"zone": "exile"})
    assert not s.state.zones.get(zone_key("p1", "library"))
    src = token(s, "p1", "Tutor", text="{1}: Search your library for a card, put it into your hand, then shuffle.")
    activate(s, src)
    d = s.state.rules.decision
    assert d is None or d.min_choices == 0  # as many as possible: none


# -- "Creatures can't block this turn" isn't locked in (611.2c) ---------------------------
def test_cant_block_applies_to_creatures_that_enter_later(cards):
    s = build(cards)
    early = token(s, "p2", "Early")
    src = token(s, "p1", "Falter", text="{1}: Creatures can't block this turn.")
    activate(s, src)
    late = token(s, "p2", "Late")
    plan = Plan(s.state, "p1", cards, None)
    assert "cant_block" in plan.ch(s.state.cards[early.id]).imposed
    assert "cant_block" in plan.ch(s.state.cards[late.id]).imposed  # entered after it resolved
    replay_matches(s)


def test_target_restriction_stays_with_that_object(cards):
    s = build(cards)
    wall = token(s, "p2", "Wall", "0/4")
    other = token(s, "p2", "Other")
    src = token(s, "p1", "Taunter", text="{1}: Target creature can't block this turn.")
    activate(s, src, targets=[wall.id])
    plan = Plan(s.state, "p1", cards, None)
    assert "cant_block" in plan.ch(s.state.cards[wall.id]).imposed
    assert "cant_block" not in plan.ch(s.state.cards[other.id]).imposed

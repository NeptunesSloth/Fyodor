"""Wave 18G: "cards drawn this turn" kept per card and private to the drawing player (CR 121.2, 400.7) — Sylvan Library: "At the
beginning of your draw step, you may draw two additional cards. If you do, choose two cards in your hand drawn this turn. For each
of those cards, pay 4 life or put the card on top of your library." Which cards in a hand were drawn this turn is the owner's
information: every decision, view and log line is checked from the other players' side. Real Oracle text, a replay and a save/load
round trip."""

from __future__ import annotations

import json

import pytest

from app.game.session import GameSession
from app.game.state import GameState
from app.game.visibility import SPECTATOR
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, zone
from tests.test_rules_conditionals import build, on_field
from tests.test_rules_wave15d_activated import roundtrip

SYLVAN = ("At the beginning of your draw step, you may draw two additional cards. If you do, choose two cards in your hand drawn this "
          "turn. For each of those cards, pay 4 life or put the card on top of your library.")
EXTRA = [card("Sylvan Library", set_code="tst", number="18G1", mana_cost="{1}{G}", cmc=2.0, type_line="Enchantment", oracle_text=SYLVAN,
              colors=["G"], color_identity=["G"])]
TOP = ["Lightning Bolt", "Llanowar Elves", "Murder", "Giant Growth"]  # the next draws: the draw step's, then the two additional


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def name_of(s, cid):
    return s.state.cards[cid].name


def at_the_choice(cards, life=40):
    """Alice has Sylvan Library; it is her next draw step, the trigger resolved and she chose to draw: the pick decision is open."""
    s = build(cards, "Sylvan Library", *TOP)
    on_field(s, "Sylvan Library")
    library = [c for c in s.state.zones["p1:library"]]
    for n in reversed(TOP):  # (the top of the library, in order: Lightning Bolt first)
        cid = next(c.id for c in s.state.cards.values() if c.name == n and c.owner == "p1" and c.id in library)
        act(s, "p1", type="move", card_ids=[cid], to={"player": "p1", "zone": "library"}, position="top")
    act(s, "p1", type="life", player="p1", delta=life - 40)
    act(s, "p1", type="pass_priority", until="next_turn")
    for _ in range(400):
        d = s.state.rules.decision
        if d is not None and d.kind == "choose_cards" and "drawn this turn" in d.prompt:
            return s
        if d is not None:
            ids = [o.id for o in d.options]
            if d.kind == "declare_attackers":
                act(s, d.player, type="declare_attackers", attackers=[])
            elif d.kind == "declare_blockers":
                act(s, d.player, type="declare_blockers", blockers=[])
            else:
                act(s, d.player, type="choose", decision_id=d.id, option_ids=[next((i for i in ids if i == "yes"), ids[0])])
            continue
        act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("never reached the choice")


def hand_names(s):
    return sorted(name_of(s, c) for c in zone(s.state, "p1", "hand"))


def pick(s, names):
    d = s.state.rules.decision
    ids = [o.id for o in d.options if name_of(s, o.id) in names]
    act(s, d.player, type="choose", decision_id=d.id, option_ids=ids)


def test_sylvan_library_is_full(cards):
    assert coverage.of_card_data(cards.resolve("Sylvan Library")).level == "FULL"


def test_choose_two_drawn_cards_then_pay_life_or_put_each_on_top_in_the_order_chosen(cards):
    s = at_the_choice(cards)
    d = s.state.rules.decision
    drawn = {name_of(s, o.id) for o in d.options}
    assert drawn == {"Lightning Bolt", "Llanowar Elves", "Murder"}  # the draw step's card and the two additional ones ...
    assert "Giant Growth" not in drawn and len(d.options) == 3  # ... not the rest of the hand, not the library
    pick(s, {"Murder", "Lightning Bolt"})
    d = s.state.rules.decision
    assert d is not None and d.kind == "choose_one" and len(d.options) == 4  # pay or put, for either card (the order is hers)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[next(o.id for o in d.options if o.id.startswith("top:")
                                                                   and name_of(s, o.id[4:]) == "Murder")])
    d = s.state.rules.decision
    assert [o.id.split(":")[0] for o in d.options] == ["pay", "top"]  # the one left
    life = s.state.players["p1"].life
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[next(o.id for o in d.options if o.id.startswith("pay:"))])
    assert s.state.players["p1"].life == life - 4
    assert zone(s.state, "p1", "library")[0] and name_of(s, zone(s.state, "p1", "library")[0]) == "Murder"  # on top, face down
    assert "Murder" not in hand_names(s) and "Lightning Bolt" in hand_names(s)
    roundtrip(s)


def test_with_less_than_the_life_to_pay_the_cards_go_back(cards):
    s = at_the_choice(cards, life=3)
    pick(s, {"Murder", "Lightning Bolt"})
    d = s.state.rules.decision
    assert all(o.id.startswith("top:") for o in d.options) and len(d.options) == 2  # 119.4: nothing to pay with; the order is hers
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[next(o.id for o in d.options if name_of(s, o.id[4:]) == "Murder")])
    assert s.state.rules.decision is None and s.state.players["p1"].life == 3  # the last one is forced
    library = zone(s.state, "p1", "library")
    assert [name_of(s, c) for c in library[:2]] == ["Lightning Bolt", "Murder"]  # put one at a time: the last is on top
    roundtrip(s)


def test_a_card_that_left_the_hand_and_came_back_was_not_drawn(cards):
    """400.7: a returned card is a new object; cards drawn on an earlier turn, and a card taken from the library another way, weren't
    drawn this turn."""
    from app.rules import selectors
    from app.rules.plan import Plan

    s = build(cards)
    act(s, "p1", type="draw", player="p1", count=2)
    first, second = zone(s.state, "p1", "hand")[-2:]
    plan = Plan.view(s.state, "p1", s.cards)
    assert selectors.drawn_now(plan, s.state.cards[first]) and selectors.drawn_now(plan, s.state.cards[second])
    act(s, "p1", type="move", card_ids=[second], to={"player": "p1", "zone": "graveyard"})
    act(s, "p1", type="move", card_ids=[second], to={"zone": "hand"})
    plan = Plan.view(s.state, "p1", s.cards)
    assert selectors.drawn_now(plan, s.state.cards[first]) and not selectors.drawn_now(plan, s.state.cards[second])
    other = zone(s.state, "p1", "library")[0]
    act(s, "p1", type="move", card_ids=[other], to={"zone": "hand"})  # (put into the hand, not drawn)
    assert not selectors.drawn_now(Plan.view(s.state, "p1", s.cards), s.state.cards[other])
    act(s, "p1", type="pass_priority", until="next_turn")  # (a new turn: the record is this turn's)
    assert not selectors.drawn_now(Plan.view(s.state, "p1", s.cards), s.state.cards[first])
    roundtrip(s)


def test_nothing_about_the_cards_drawn_this_turn_reaches_another_player(cards):
    s = at_the_choice(cards)
    secret = ["Lightning Bolt", "Llanowar Elves", "Murder"]
    for viewer in ("p2", SPECTATOR):
        blob = json.dumps(s.view(viewer))
        assert not any(n in blob for n in secret), viewer  # no name, in the decision or anywhere else
        assert not any(o.id in blob for o in s.state.rules.decision.options), viewer  # no card id of the options either
        rules_view = s.view(viewer)["rules"]
        assert rules_view["decision"]["kind"] == "waiting" and "options" not in rules_view["decision"], viewer
    mine = json.dumps(s.view("p1"))
    assert all(n in mine for n in secret)  # (hers: she sees them)
    pick(s, {"Murder", "Lightning Bolt"})
    d = s.state.rules.decision
    for viewer in ("p2", SPECTATOR):  # the per-card decision is hidden the same way
        blob = json.dumps(s.view(viewer))
        assert not any(n in blob for n in secret) and s.view(viewer)["rules"]["decision"]["kind"] == "waiting", viewer
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[next(o.id for o in d.options if o.id.startswith("top:"))])
    d = s.state.rules.decision
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[next(o.id for o in d.options if o.id.startswith("pay:"))])
    for viewer in ("p2", SPECTATOR):  # the log names no card that went back, and the saved view of a spectator has none either
        blob = json.dumps(s.view(viewer))
        assert not any(n in blob for n in secret), viewer
    loaded = GameSession(GameState.model_validate_json(s.state.model_dump_json()), cards=s.cards)
    assert not any(n in json.dumps(loaded.view("p2")) for n in secret)

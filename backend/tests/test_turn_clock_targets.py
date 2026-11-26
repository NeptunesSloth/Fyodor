"""Turn clock (stage 3, final fix C1): at zero the clock never aims a required target choice at the player whose clock ran out.

115.1 / 601.2c / 603.3d: a triggered ability's targets are chosen as it is put on the stack, by its controller, and the choice is
required (when a legal one exists). The clock answers it for the timed-out player with the least drastic legal option: a permanent
(an opponent's first, then their own), then an opponent, and the timed-out player themself last of all; when only answers naming
themself remain, it leaves the choice to the table (``[]``).
"""

from __future__ import annotations

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game import dummy
from app.game.clock_defaults import answers
from app.game.rules_state import Decision, DecisionOption
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_declaration_requirements33 import start
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_shared_damage_choices import table

PING = "Clock Ping Totem"  # the final review's reproduction (a mandatory "any target" upkeep trigger)
DEMON = "Bloodgift Demon"
LEYLINE = "Leyline of Sanctity"
BEARS = "Grizzly Bears"


@pytest.fixture()
def cards(settings):
    base = {c["name"]: c for c in fixture_cards()}
    base[PING] = card(PING, set_code="tcx", number="1", type_line="Artifact",
                      oracle_text="At the beginning of your upkeep, this artifact deals 3 damage to any target.")
    base[DEMON] = card(DEMON, set_code="tcx", number="2", mana_cost="{3}{B}{B}", cmc=5.0, type_line="Creature — Demon",
                       power="5", toughness="4", colors=["B"], color_identity=["B"], keywords=["Flying"],
                       oracle_text="Flying\nAt the beginning of your upkeep, target player draws a card and loses 1 life.")
    base[LEYLINE] = card(LEYLINE, set_code="tcx", number="3", mana_cost="{2}{W}{W}", cmc=4.0, type_line="Enchantment",
                         colors=["W"], color_identity=["W"],
                         oracle_text="If this card is in your opening hand, you may begin the game with it on the battlefield.\n"
                                     "You have hexproof. (You can't be the target of spells or abilities your opponents control.)")
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def to_p1_target_choice(s):
    """Play on (every other decision answered by the clock's own defaults, priority passed) until p1 must choose a target."""
    for _ in range(120):
        r = s.state.rules
        d = r.decision
        if d is not None:
            if d.player == "p1" and any(o.id in s.state.players for o in d.options):
                return d
            act(s, d.player, **answers(s.state, d.player, s.cards)[0])
        else:
            act(s, r.priority, type="pass_priority")
    raise AssertionError("p1 was never asked for a target")


def finish(s):
    for _ in range(20):
        r = s.state.rules
        if r.decision is None and r.priority is not None and s.state.zones.get("stack"):
            act(s, r.priority, type="pass_priority")


def test_the_reviewers_reproduction_never_targets_the_timed_out_player(cards):
    names = [PING]
    s = table(cards, names, names, names)
    put(s, PING, "battlefield")
    start(s)
    s.state.players["p1"].life = 3
    d = to_p1_target_choice(s)
    assert [o.id for o in d.options][:3] == ["p1", "p2", "p3"]           # the engine offers players first, in seat order
    got = answers(s.state, "p1", s.cards)
    assert got and "p1" not in got[0]["option_ids"]
    assert [a for a in got if "p1" in a.get("option_ids", [])] in ([], got[-1:])  # (named last, if at all)
    act(s, "p1", **got[0])
    finish(s)
    assert s.state.players["p1"].life == 3 and "p1" not in s.state.rules.lost
    roundtrip(s)


def test_only_the_timed_out_player_is_legal_so_the_table_decides(cards):
    # Bloodgift Demon: "target player"; both opponents have hexproof (Leyline of Sanctity), so p1 is the only legal target
    s = table(cards, [DEMON], [LEYLINE], [LEYLINE])
    put(s, DEMON, "battlefield")
    put(s, LEYLINE, "battlefield", pid="p2")
    put(s, LEYLINE, "battlefield", pid="p3")
    start(s)
    s.state.players["p1"].life = 1
    d = to_p1_target_choice(s)
    assert [o.id for o in d.options] == ["p1"]
    assert answers(s.state, "p1", s.cards) == []
    roundtrip(s)


def test_a_creature_is_chosen_over_an_opponent(cards):
    s = table(cards, [PING], [BEARS], [])
    start(s)
    put(s, PING, "battlefield")  # (in Alice's main phase: its first trigger is the one the clock answers)
    bears = put(s, BEARS, "battlefield", pid="p2")
    d = to_p1_target_choice(s)
    assert {"p1", "p2", "p3", bears.id} <= {o.id for o in d.options}
    got = answers(s.state, "p1", s.cards)
    assert got[0]["option_ids"] == [bears.id]                              # a permanent, not a player
    act(s, "p1", **got[0])
    finish(s)
    assert bears.id not in s.state.cards or not s.state.cards[bears.id].zone.endswith(":battlefield")  # (3 damage: the Bears die)
    assert {p: x.life for p, x in s.state.players.items()} == {"p1": 40, "p2": 40, "p3": 40} and not s.state.rules.lost
    roundtrip(s)


# -- the guard: whatever the dummy's fallback order, the clock's ------------------------------------------------------------------


def _decision(ids, min_choices=1, kind=None):
    kind = kind or ("choose_one" if min_choices == 1 else "choose_cards")
    return Decision(id="d1", player="p1", kind=kind, prompt="Choose a target", min_choices=min_choices, max_choices=max(1, min_choices),
                    options=[DecisionOption(id=i, label=i) for i in ids])


def _rank(s, ids):
    def one(i):
        if i == "p1":
            return 3
        if i in s.state.players:
            return 2
        c = s.state.cards.get(i)
        return 1 if c is not None and c.controller == "p1" else 0
    return max((one(i) for i in ids), default=0)


@pytest.mark.parametrize("min_choices", [0, 1, 2])
@pytest.mark.parametrize("order", ["players_first", "cards_first", "self_last"])
def test_guard_the_fallback_names_the_timed_out_player_last(cards, order, min_choices):
    s = table(cards, [BEARS], [BEARS], [])
    mine = put(s, BEARS, "battlefield")
    theirs = put(s, BEARS, "battlefield", pid="p2")
    ids = {"players_first": ["p1", "p2", "p3", mine.id, theirs.id],
           "cards_first": [mine.id, theirs.id, "p1", "p2", "p3"],
           "self_last": ["p2", "p3", theirs.id, mine.id, "p1"]}[order]
    s.state.rules.decision = _decision(ids, min_choices)
    s.state.rules.priority = None
    got = [a for a in answers(s.state, "p1", s.cards) if a["type"] == "choose"]
    plain = dummy.answers(s.state.rules.decision, state=s.state, info=s.cards)
    assert plain and got
    if order == "players_first" and min_choices >= 1:
        assert "p1" in plain[0]["option_ids"]                             # the dummy's own order would name p1 first
    ranks = [_rank(s, a["option_ids"]) for a in got]
    assert ranks == sorted(ranks)                                         # least drastic first, the timed-out player last
    first = next(a for a in got if a["option_ids"])
    assert "p1" not in first["option_ids"]
    if min_choices == 1:
        assert first["option_ids"] == [theirs.id]                         # an opponent's permanent first
    if min_choices == 2:
        assert sorted(first["option_ids"]) == sorted([theirs.id, mine.id])  # the two permanents, no player


def test_guard_only_self_answers_are_left_to_the_table(cards):
    s = table(cards, [], [], [])
    s.state.rules.decision = _decision(["p1"])
    s.state.rules.priority = None
    assert answers(s.state, "p1", s.cards) == []
    s.state.rules.decision = _decision(["p1", "p2"], min_choices=2)  # (every answer names p1)
    assert answers(s.state, "p1", s.cards) == []


def test_guard_same_for_all_answers_never_name_the_timed_out_player_first(cards):
    # triggers.SAME_FOR_ALL: several identical triggers waiting together also offer "all:<target>" (one answer for every copy)
    s = table(cards, [], [], [])
    s.state.rules.decision = _decision(["p1", "p2", "p3", "all:p1", "all:p2", "all:p3"])
    s.state.rules.priority = None
    got = answers(s.state, "p1", s.cards)
    assert got and not {"p1", "all:p1"} & set(got[0]["option_ids"])
    named = [i for i, a in enumerate(got) if {"p1", "all:p1"} & set(a.get("option_ids") or [])]
    assert all(i > j for i in named for j, a in enumerate(got) if j not in named)  # (named last, if at all)
    s.state.rules.decision = _decision(["p1", "all:p1"])  # only themself, one copy or every copy: the table decides
    assert answers(s.state, "p1", s.cards) == []


def test_guard_a_choice_of_players_never_names_the_timed_out_player_first(cards):
    # wave110a_pick (Sower of Discord, "choose two players"): one option per pair, "p1,p2"; one naming p1 counts as naming them
    s = table(cards, [], [], [])
    s.state.rules.decision = _decision(["p1,p2", "p1,p3", "p2,p3"])
    s.state.rules.priority = None
    got = answers(s.state, "p1", s.cards)
    assert got and got[0]["option_ids"] == ["p2,p3"]
    assert all("p1" in a["option_ids"][0].split(",") for a in got[1:])  # (named last, if at all)
    s.state.rules.decision = _decision(["p1,p2"])  # every pair includes themself: the table decides
    assert answers(s.state, "p1", s.cards) == []


def test_guard_a_division_that_includes_the_timed_out_player_is_left_to_the_table(cards):
    s = table(cards, [], [], [])
    d = _decision(["p1", "p2"], kind="divide")
    d.resume = {"total": 3, "least": 1}
    s.state.rules.decision = d
    s.state.rules.priority = None
    assert answers(s.state, "p1", s.cards) == []
    d2 = _decision(["p2", "p3"], kind="divide")
    d2.resume = {"total": 3, "least": 1}
    s.state.rules.decision = d2
    assert answers(s.state, "p1", s.cards) == [{"type": "choose", "decision_id": "d1", "option_ids": [], "amounts": [2, 1]}]


def test_guard_choices_without_players_keep_the_offered_order(cards):
    s = table(cards, [BEARS], [BEARS], [])
    mine = put(s, BEARS, "battlefield")
    theirs = put(s, BEARS, "battlefield", pid="p2")
    s.state.rules.decision = _decision([mine.id, theirs.id])  # (no player offered: e.g. "sacrifice a creature": not reordered)
    s.state.rules.priority = None
    got = answers(s.state, "p1", s.cards)
    assert got[0]["option_ids"] == [mine.id]

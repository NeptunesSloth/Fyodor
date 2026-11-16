"""-- planechase deck (wave D) -- planar-deck manipulation from rules effects (``planar_deck_op``), several face-up planes (901.11c) and
Mount Keralia's planeswalk-away damage from its last known information (app/rules/planar_deck.py), on real Oracle text with the rules
engine on; each scenario ends with ``check`` (replay + save/load round trip), and one replays after an undo."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.cards.importer import build_database
from app.config import Settings
from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from app.game.state import GameSettings, PlanarCard
from app.game.views import planechase_view
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, deck, enable
from tests.test_planechase import replay_matches, script
from tests.test_rules_conditionals import to_turn
from tests.test_rules_wave12a_counters_keywords import real
from tests.wave9c_kit import check, life, mana, put

# Oracle text exactly as in the card database (data/cards.sqlite)
PLANES = {
    "Krosa": ("Plane — Dominaria", "All creatures get +2/+2.\nWhenever chaos ensues, you may add {W}{U}{B}{R}{G}."),
    "Llanowar": ("Plane — Dominaria", 'All creatures have "{T}: Add {G}{G}."\nWhenever chaos ensues, untap all creatures you control.'),
    "Fields of Summer": ("Plane — Moag", "Whenever a player casts a spell, that player may gain 2 life.\nWhenever chaos ensues, you may gain "
                         "10 life."),
    "Mount Keralia": ("Plane — Regatha", "At the beginning of your end step, put a pressure counter on Mount Keralia.\nWhen you planeswalk "
                      "away from Mount Keralia, it deals damage equal to the number of pressure counters on it to each creature and each "
                      "planeswalker.\nWhenever chaos ensues, prevent all damage that planes named Mount Keralia would deal this game to "
                      "permanents you control."),
    "Interplanar Tunnel": ("Phenomenon", "When you encounter Interplanar Tunnel, reveal cards from the top of your planar deck until you "
                           "reveal five plane cards. Put a plane card from among them on top of your planar deck, then put the rest of the "
                           "revealed cards on the bottom in a random order. (Then planeswalk away from this phenomenon.)"),
    "Stairs to Infinity": ("Plane — Xerex", "Players have no maximum hand size.\nWhenever you roll the planar die, draw a card.\nWhenever "
                           "chaos ensues, reveal the top card of your planar deck. You may put it on the bottom of your planar deck."),
    "Pools of Becoming": ("Plane — Bolas's Meditation Realm", "At the beginning of your end step, put the cards in your hand on the bottom of "
                          "your library in any order, then draw that many cards.\nWhenever chaos ensues, reveal the top three cards of your "
                          "planar deck. Each of the revealed cards' chaos abilities triggers. Then put the revealed cards on the bottom of "
                          "your planar deck in any order."),
    "The Fertile Lands of Saulvinia": ("Plane — Antausia", "Whenever a player taps a land for mana, that player adds one mana of any type "
                                       "that land produced.\nWhenever chaos ensues, reveal cards from the top of your planar deck until you "
                                       "reveal a plane card. Chaos ensues on that plane. Then put all cards revealed this way on the bottom "
                                       "of your planar deck in any order."),
    "Norn's Seedcore": ("Plane — New Phyrexia", "When you planeswalk to Norn's Seedcore, chaos ensues.\nWhenever chaos ensues, reveal cards "
                        "from the top of your planar deck until you reveal a plane card. Planeswalk to it, except don't planeswalk away from "
                        "any plane. Put the rest of the revealed cards on the bottom of your planar deck in any order."),
    "Spatial Merging": ("Phenomenon", "When you encounter Spatial Merging, reveal cards from the top of your planar deck until you reveal two "
                        "plane cards. Simultaneously planeswalk to both of them. Put all other cards revealed this way on the bottom of your "
                        "planar deck in any order."),
    "Chaotic Aether": ("Phenomenon", "When you encounter Chaotic Aether, each blank roll of the planar die is a {CHAOS} roll until a player "
                       "planeswalks away from a plane. (Then planeswalk away from this phenomenon.)"),
}
EXTRA = [card(n, set_code="opca", number=f"PD-{i}", layout="planar", type_line=t, oracle_text=o) for i, (n, (t, o)) in enumerate(PLANES.items())]
EXTRA += [real("Runeclaw Bear", "{1}{G}", 2, "Creature — Bear", "", ("2", "2"), "G"),
          real("Craw Wurm", "{4}{G}{G}", 6, "Creature — Wurm", "", ("6", "4"), "G")]
FULL = ["Interplanar Tunnel", "Spatial Merging", "Norn's Seedcore", "Pools of Becoming", "The Fertile Lands of Saulvinia", "Mount Keralia",
        "Stairs to Infinity"]


@pytest.fixture()
def card_db(settings: Settings) -> Path:
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


class _InOrder:
    def shuffle(self, items: list) -> None:
        pass

    def randint(self, lo: int, hi: int) -> int:
        return lo


def table(cards, planes: list[str]) -> GameSession:
    alice = deck(cards, "Krenko, Mob Boss", [(1, "Runeclaw Bear"), (1, "Craw Wurm"), (10, "Forest")])
    bob = deck(cards, "Atraxa, Praetors' Voice", [(1, "Runeclaw Bear"), (1, "Craw Wurm"), (10, "Island")])
    pool = [PlanarCard(printing_id=cards.resolve(n)["id"], name=n, phenomenon=PLANES[n][0] == "Phenomenon") for n in planes]
    state = new_game([PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=bob)], shuffle=False, first_player=0,
                     settings=GameSettings(planechase=True, planar_deck_size=len(pool)), planar_pool=lambda: pool, rng=_InOrder())
    assert [c.name for c in state.planechase.deck] == planes
    enable(state)
    s = GameSession(state, cards=cards)
    act(s, "p1", type="pass_priority")  # → Alice's main phase
    return s


def settle(s, picks=(), seen=None):
    """Everything resolves; a choice takes the ``picks`` (ids or labels, in this order of preference; an "order" choice takes them in
    that order) when offered, else the first it may. ``seen`` collects each decision as it comes up."""
    for _ in range(80):
        d = s.state.rules.decision
        if d is not None:
            if seen is not None:
                seen.append(d)
            chosen = [o.id for p in picks for o in d.options if p in (o.id, o.label)][: d.max_choices]
            if len(chosen) < d.min_choices:
                chosen += [o.id for o in d.options if o.id not in chosen][: d.min_choices - len(chosen)]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=chosen)
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return
    raise AssertionError("never settled")


def roll(s, monkeypatch, face: int, picks=(), seen=None):
    """Alice rolls the planar die: 1 the planeswalker symbol (901.8), 2 the chaos symbol (901.9b)."""
    from app.game.handlers.planechase import roll_cost

    if cost := roll_cost(s.state):
        mana(s, C=cost)
    script(monkeypatch, [face])
    act(s, "p1", type="roll_planar_die")
    settle(s, picks, seen)


def names(s) -> list[str]:
    return [c.name for c in s.state.planechase.deck]


def faces(s) -> list[str]:
    pc = s.state.planechase
    return [s.state.cards[i].name for i in [pc.face_id, *pc.face_ids]]


@pytest.mark.parametrize("name", FULL)
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


# -- Mount Keralia: its counters as it last existed (608.2h) ------------------------------------------------------------------------------
def test_mount_keralia_deals_damage_equal_to_its_pressure_counters_as_it_planeswalks_away(cards, monkeypatch):
    s = table(cards, ["Krosa", "Mount Keralia", "Llanowar"])
    bear, wurm, bobs = put(s, "Runeclaw Bear"), put(s, "Craw Wurm"), put(s, "Runeclaw Bear", "p2")
    roll(s, monkeypatch, 1)
    assert faces(s) == ["Mount Keralia"]
    to_turn(s, 3)  # Alice's and Bob's end steps: two pressure counters
    pc = s.state.planechase
    assert s.state.cards[pc.face_id].counters.get("pressure") == 2
    act(s, "p1", type="pass_priority") if s.state.turn.phase != "main1" else None
    roll(s, monkeypatch, 1)  # away from Mount Keralia: 2 damage to each creature (the plane is gone: its last known counters)
    assert faces(s) == ["Llanowar"]
    assert s.state.cards[bear.id].zone == "p1:graveyard" and s.state.cards[bobs.id].zone == "p2:graveyard"
    assert s.state.cards[wurm.id].damage == 2
    check(s)


def test_mount_keralia_chaos_prevents_its_damage_to_your_permanents_for_the_rest_of_the_game(cards, monkeypatch):
    s = table(cards, ["Krosa", "Mount Keralia", "Llanowar"])
    bear, bobs = put(s, "Runeclaw Bear"), put(s, "Runeclaw Bear", "p2")
    roll(s, monkeypatch, 1)
    roll(s, monkeypatch, 2)  # chaos (Alice is "you"): Mount Keralia's damage to permanents Alice controls is prevented, this game
    to_turn(s, 3)
    assert s.state.cards[s.state.planechase.face_id].counters.get("pressure") == 2
    act(s, "p1", type="pass_priority") if s.state.turn.phase != "main1" else None
    roll(s, monkeypatch, 1)
    assert s.state.cards[bear.id].zone == "p1:battlefield" and s.state.cards[bear.id].damage == 0
    assert s.state.cards[bobs.id].zone == "p2:graveyard"
    check(s)


# -- Stairs to Infinity ------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("answer", ["yes", "no"])
def test_stairs_to_infinity_reveals_the_top_card_and_may_put_it_on_the_bottom(cards, monkeypatch, answer):
    s = table(cards, ["Stairs to Infinity", "Krosa", "Llanowar"])
    seen: list = []
    script(monkeypatch, [2])
    mana(s, C=0)
    act(s, "p1", type="roll_planar_die")
    for _ in range(20):  # up to the choice: the revealed card is public while it stays revealed
        d = s.state.rules.decision
        if d is not None and d.kind == "confirm" and "planar deck" in d.prompt:
            break
        if d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    view = planechase_view(s.state)
    assert [c["name"] for c in view["revealed"]] == ["Krosa"]
    assert "Llanowar" not in str(view)  # (the rest of the deck stays hidden)
    settle(s, [answer], seen)
    assert names(s) == (["Stairs to Infinity", "Llanowar", "Krosa"] if answer == "yes" else ["Stairs to Infinity", "Krosa", "Llanowar"])
    assert planechase_view(s.state)["revealed"] == []
    check(s)


# -- Interplanar Tunnel --------------------------------------------------------------------------------------------------------------
def test_interplanar_tunnel_puts_the_chosen_plane_on_top_and_the_rest_at_random_then_planeswalks_to_it(cards, monkeypatch):
    deck_ = ["Krosa", "Interplanar Tunnel", "Llanowar", "Fields of Summer", "Chaotic Aether", "Stairs to Infinity", "Pools of Becoming",
             "Mount Keralia", "Norn's Seedcore"]
    s = table(cards, deck_)
    seen: list = []
    roll(s, monkeypatch, 1, picks=["Pools of Becoming"], seen=seen)
    tunnel = next(d for d in seen if d.kind == "choose_one")
    assert sorted(o.label for o in tunnel.options) == ["Fields of Summer", "Llanowar", "Mount Keralia", "Pools of Becoming",
                                                       "Stairs to Infinity"]  # (five planes; the phenomenon revealed among them isn't one)
    assert faces(s) == ["Pools of Becoming"]  # 704.6f: away from the Tunnel, to the plane put on top
    order = names(s)
    assert order[1:3] == ["Norn's Seedcore", "Krosa"]  # (the unrevealed cards are next)
    assert set(order[3:8]) == {"Llanowar", "Fields of Summer", "Chaotic Aether", "Stairs to Infinity", "Mount Keralia"}  # (at random)
    assert order[8:] == ["Interplanar Tunnel"]  # (then away from the phenomenon, 704.6f)
    text = " ".join("".join(p.get("t") or p.get("card", {}).get("name", "") for p in e["parts"]) for e in s.view("p2")["log"][-8:])
    assert "revealed Llanowar, Fields of Summer, Chaotic Aether, Stairs to Infinity, Pools of Becoming, Mount Keralia" in text
    check(s)


# -- Pools of Becoming / The Fertile Lands of Saulvinia: chaos ensues on revealed planes (311.7) -----------------------------------------
def test_pools_of_becoming_each_revealed_planes_chaos_ability_triggers_then_bottom_in_chosen_order(cards, monkeypatch):
    s = table(cards, ["Pools of Becoming", "Fields of Summer", "Chaotic Aether", "Krosa", "Llanowar"])
    seen: list = []
    before = life(s, "p1")
    roll(s, monkeypatch, 2, picks=["yes", "Krosa", "Chaotic Aether", "Fields of Summer"], seen=seen)
    assert life(s, "p1") == before + 10  # Fields of Summer's chaos ability (Krosa's: its mana, unspent)
    order = next(d for d in seen if d.kind == "order" and "planar deck" in d.prompt)
    assert sorted(o.label for o in order.options) == ["Chaotic Aether", "Fields of Summer", "Krosa"]
    assert names(s) == ["Pools of Becoming", "Llanowar", "Fields of Summer", "Chaotic Aether", "Krosa"]  # (first chosen: very bottom)
    check(s)


def test_fertile_lands_chaos_ensues_on_the_first_revealed_plane_only(cards, monkeypatch):
    s = table(cards, ["The Fertile Lands of Saulvinia", "Chaotic Aether", "Fields of Summer", "Krosa"])
    before = life(s, "p1")
    roll(s, monkeypatch, 2, picks=["yes", "Fields of Summer", "Chaotic Aether"])
    assert life(s, "p1") == before + 10  # Fields of Summer's chaos ability; the Fertile Lands' own doesn't trigger again (its ruling)
    assert names(s) == ["The Fertile Lands of Saulvinia", "Krosa", "Chaotic Aether", "Fields of Summer"]
    check(s)


# -- several face-up planes (901.11c) ------------------------------------------------------------------------------------------------
def test_norns_seedcore_planeswalks_to_the_revealed_plane_without_leaving_and_both_chaos_abilities_trigger(cards, monkeypatch):
    s = table(cards, ["Krosa", "Norn's Seedcore", "Chaotic Aether", "Fields of Summer", "Llanowar", "Mount Keralia"])
    bear = put(s, "Runeclaw Bear")
    roll(s, monkeypatch, 1, picks=["yes"])  # to Norn's Seedcore: chaos ensues → Chaotic Aether, then Fields of Summer face up beside it
    assert faces(s) == ["Norn's Seedcore", "Fields of Summer"]
    assert names(s) == ["Norn's Seedcore", "Fields of Summer", "Llanowar", "Mount Keralia", "Krosa", "Chaotic Aether"]
    view = planechase_view(s.state)
    assert [c["name"] for c in view["faces"]] == ["Norn's Seedcore", "Fields of Summer"] and view["current"]["name"] == "Norn's Seedcore"
    before = life(s, "p1")
    roll(s, monkeypatch, 2, picks=["yes"])  # chaos: both face-up planes' chaos abilities (Fields: 10 life; Norn's: Llanowar face up too)
    assert life(s, "p1") == before + 10
    assert faces(s) == ["Norn's Seedcore", "Fields of Summer", "Llanowar"]
    from app.rules.plan import Plan

    assert "{T}: Add {G}{G}." in str(Plan(s.state, "p1", s.cards, None).ch(s.state.cards[bear.id]).abilities)  # (Llanowar's grant, from the third face)
    seen: list = []
    roll(s, monkeypatch, 1, picks=["Llanowar", "Norn's Seedcore", "Fields of Summer"], seen=seen)  # away from all three (901.11c)
    assert any(d.kind == "order" and "Planeswalk" in d.prompt for d in seen)
    assert faces(s) == ["Mount Keralia"]
    assert names(s)[-3:] == ["Fields of Summer", "Norn's Seedcore", "Llanowar"]  # (first chosen: the very bottom)
    assert all(not c.startswith("planar-") or c == s.state.planechase.face_id for c in s.state.cards)
    check(s)


def test_spatial_merging_planeswalks_to_both_planes_at_once(cards, monkeypatch):
    s = table(cards, ["Krosa", "Spatial Merging", "Llanowar", "Chaotic Aether", "Mount Keralia", "Fields of Summer"])
    bear = put(s, "Runeclaw Bear")
    roll(s, monkeypatch, 1)
    assert faces(s) == ["Llanowar", "Mount Keralia"]
    assert names(s) == ["Llanowar", "Mount Keralia", "Fields of Summer", "Krosa", "Spatial Merging", "Chaotic Aether"]
    # both planes' abilities work: Llanowar's grant ({T}: Add {G}{G}); Mount Keralia's end step counter
    to_turn(s, 2)
    keralia = next(s.state.cards[i] for i in s.state.planechase.face_ids)
    assert keralia.name == "Mount Keralia" and keralia.counters.get("pressure") == 1
    assert s.state.cards[bear.id].zone == "p1:battlefield"
    check(s)


def test_undo_after_a_planar_deck_reveal_asks_the_table_then_replays(cards, monkeypatch):
    from app.game.errors import ActionError

    s = table(cards, ["Pools of Becoming", "Fields of Summer", "Krosa", "Llanowar"])
    script(monkeypatch, [2])
    act(s, "p1", type="roll_planar_die")
    for _ in range(20):  # up to Pools of Becoming's order choice (the three cards revealed, in the view)
        d = s.state.rules.decision
        if d is not None and d.kind == "order" and "planar deck" in d.prompt:
            break
        if d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    assert [c["name"] for c in planechase_view(s.state)["revealed"]] == ["Fields of Summer", "Krosa", "Llanowar"]
    pick = {o.label: o.id for o in d.options}
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[pick["Krosa"], pick["Llanowar"], pick["Fields of Summer"]])
    after = s.state.planechase.model_dump()
    assert names(s) == ["Pools of Becoming", "Fields of Summer", "Llanowar", "Krosa"]
    with pytest.raises(ActionError, match="Ask the table"):  # (the planar deck's reveal: undo_requests "reveal")
        s.undo("p1", others=["p2"])
    s.undo("p1")
    assert s.state.rules.decision is not None and s.state.rules.decision.kind == "order"
    replay_matches(s)
    d = s.state.rules.decision
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[pick["Krosa"], pick["Llanowar"], pick["Fields of Summer"]])
    assert s.state.planechase.model_dump() == after
    settle(s, ["yes"])
    check(s)
    while s.state.planechase.walks == 0 and s.history.cursor > 0 and s.state.planechase.last_roll is not None:
        s.undo("p1")  # (back past the roll that revealed: the planar deck as dealt, nothing revealed, from history alone)
    assert s.state.planechase.revealed == [] and names(s) == ["Pools of Becoming", "Fields of Summer", "Krosa", "Llanowar"]
    replay_matches(s)

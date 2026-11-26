"""-- planechase -- (CR 901, Commander's single shared planar deck; app/game/handlers/planechase.py).

The planar deck is dealt on the server when the game is created (part of its base state) or by the host's ``planar_start``; the
active player rolls the planar die (the first roll in a turn {0}, then {1} more each time; on a manual table the cost is shown, with
automation it is charged from the pool: ``roll_planar_die``); a
planeswalker result planeswalks, chaos leaves the plane in place (players apply it), a phenomenon waits until someone planeswalks
away from it. No view holds the deck's order; undo, replay and saves are exact; a table without Planechase is unchanged."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.importer import build_database
from app.config import Settings
from app.game import resolve
from app.game.errors import ActionError
from app.game.factory import DeckCard, PlayerSetup, new_game
from app.game.handlers import planechase
from app.game.session import GameSession
from app.game.state import GameSettings, GameState, PlanarCard
from app.game.visibility import OMNISCIENT, SPECTATOR
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act

PLANES = [card(f"Plane {n:02d}", set_code="opca", number=f"P{n}", layout="planar", type_line=f"Plane — World {n}",
               oracle_text=f"Static {n}.\nWhenever chaos ensues, chaos {n}.",
               image_uris={"normal": f"https://cards.scryfall.io/normal/front/p{n}.jpg"}) for n in range(1, 13)]
PHENOMENA = [card(f"Phenomenon {n}", set_code="opca", number=f"X{n}", layout="planar", type_line="Phenomenon",
                  oracle_text=f"When you encounter Phenomenon {n}, do {n}. (Then planeswalk away from this phenomenon.)") for n in range(1, 4)]


@pytest.fixture()
def card_db(settings: Settings) -> Path:  # (overrides conftest's: the fixture set plus planes and phenomena)
    settings.ensure_dirs()
    build_database([*fixture_cards(), *PLANES, *PHENOMENA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def table(cards, *, on: bool = True, count: int = 10, phenomena: bool = True, rng=None) -> GameSession:
    land = cards.resolve("Mountain")
    setups = [PlayerSetup(n, cards=[DeckCard("main", 9, land["name"], land["id"])]) for n in ("Alice", "Bob", "Cleo")]
    settings = GameSettings(planechase=on, planar_deck_size=count, planar_phenomena=phenomena)
    kw = {"rng": rng} if rng is not None else {}
    state = new_game(setups, shuffle=False, first_player=0, settings=settings, planar_pool=lambda: planechase.pool_of(cards), **kw)
    return GameSession(state, cards=cards)


def script(monkeypatch, values: list[int]) -> None:
    """The server's d6 numbers, in order (1 planeswalker, 2 chaos, 3-6 blank)."""
    left = list(values)

    def randint(lo: int, hi: int) -> int:
        v = left.pop(0)
        assert lo <= v <= hi
        return v

    monkeypatch.setattr(resolve._rng, "randint", randint)


def line(s: GameSession, back: int = 1) -> str:
    return "".join(p.get("t") or p.get("card", {}).get("name", "") for p in s.view("p1")["log"][-back]["parts"])


def replay_matches(s: GameSession) -> None:
    assert s.history.rebuild().model_dump(mode="json") == s.state.model_dump(mode="json")


def test_the_card_database_lists_every_plane_and_phenomenon(cards):
    pool = planechase.pool_of(cards)
    assert len(pool) == 15 and sum(c.phenomenon for c in pool) == 3
    assert {c.name for c in pool} == {*(f"Plane {n:02d}" for n in range(1, 13)), *(f"Phenomenon {n}" for n in range(1, 4))}


def test_the_deck_is_dealt_at_the_start_and_starts_on_a_plane(cards):
    for _ in range(10):
        s = table(cards)
        pc = s.state.planechase
        assert pc is not None and len(pc.deck) == 10 and len({c.name for c in pc.deck}) == 10
        assert not pc.deck[0].phenomenon
        v = s.view("p2")["planechase"]
        assert v["current"]["name"] == pc.deck[0].name and v["count"] == 10 and v["cost"] == 0 and v["walks"] == 0
    assert "The table starts on" in line(s)
    planes_only = table(cards, phenomena=False, count=12)
    assert all(not c.phenomenon for c in planes_only.state.planechase.deck)


def test_a_phenomenon_on_top_goes_to_the_bottom_when_dealt():
    class Fixed:
        def shuffle(self, x):  # the phenomena first
            x.sort(key=lambda c: not c.phenomenon)

        def randint(self, lo, hi):
            return lo

    pool = [PlanarCard(printing_id="a", name="Chaotic", phenomenon=True), PlanarCard(printing_id="b", name="Llanowar"),
            PlanarCard(printing_id="c", name="Otaria")]
    deck = planechase.deal(pool, 3, True, Fixed())
    assert [c.name for c in deck] == ["Llanowar", "Otaria", "Chaotic"]
    with pytest.raises(ActionError, match="no planes"):
        planechase.deal([pool[0]], 3, True, Fixed())


def test_rolls_cost_more_each_time_in_a_turn_and_reset_next_turn(cards, monkeypatch):
    s = table(cards)
    script(monkeypatch, [3, 4, 5, 6])
    costs = []
    for _ in range(3):
        costs.append(s.view("p1")["planechase"]["cost"])
        act(s, "p1", type="planar_roll")
    assert costs == [0, 1, 2] and s.view("p3")["planechase"]["cost"] == 3
    assert line(s) == "Alice rolled the planar die (cost {2}): blank"
    with pytest.raises(ActionError, match="Only the active player"):
        act(s, "p2", type="planar_roll")
    act(s, "p1", type="next_turn")
    assert s.view("p2")["planechase"]["cost"] == 0
    act(s, "p2", type="planar_roll")
    assert s.view("p1")["planechase"]["cost"] == 1 and s.state.planechase.last_roll.player == "p2"


def test_the_planeswalker_symbol_planeswalks(cards, monkeypatch):
    s = table(cards, phenomena=False)
    first, second = s.state.planechase.deck[0], s.state.planechase.deck[1]
    script(monkeypatch, [1])
    act(s, "p1", type="planar_roll")
    pc = s.state.planechase
    assert pc.deck[0] == second and pc.deck[-1] == first and pc.walks == 1 and pc.visited == [first]
    assert line(s, 2) == "Alice rolled the planar die: planeswalker"
    assert line(s) == f"The table planeswalked to {second.name}"
    v = s.view("p2")["planechase"]
    assert v["current"]["name"] == second.name and v["visited"][-1]["name"] == first.name
    assert v["last_roll"]["face"] == "planeswalker"


def test_chaos_leaves_the_plane_in_place(cards, monkeypatch):
    s = table(cards)
    before = list(s.state.planechase.deck)
    script(monkeypatch, [2])
    act(s, "p1", type="planar_roll")
    assert s.state.planechase.deck == before and s.state.planechase.walks == 0
    assert line(s) == "Alice rolled the planar die: chaos"
    assert s.view("p3")["planechase"]["last_roll"] == {"player": "p1", "face": "chaos", "cost": 0, "seq": s.state.seq}


def test_a_phenomenon_waits_until_the_table_planeswalks_away(cards, monkeypatch):
    s = table(cards)
    pc = s.state.planechase
    phen = PlanarCard(printing_id=PHENOMENA[0]["id"], name="Phenomenon 1", phenomenon=True)
    pc.deck = [pc.deck[0], phen, *(c for c in pc.deck[1:] if not c.phenomenon)]  # (the next card is a phenomenon)
    s.history.base = s.state.model_dump(mode="json")
    script(monkeypatch, [1])
    act(s, "p1", type="planar_roll")
    assert s.view("p1")["planechase"]["current"] == phen.model_dump()
    assert "(a phenomenon: resolve it, then planeswalk)" in line(s)
    with pytest.raises(ActionError, match="Planeswalk away from Phenomenon 1"):
        act(s, "p1", type="planar_roll")
    act(s, "p2", type="planeswalk")  # "Done — planeswalk" (anyone at the table)
    assert not s.state.planechase.deck[0].phenomenon and s.state.planechase.walks == 2
    replay_matches(s)


def test_the_deck_order_is_in_no_view(cards):
    s = table(cards)
    hidden = [c.name for c in s.state.planechase.deck[1:]]
    for viewer in ("p1", "p2", "p3", SPECTATOR, OMNISCIENT):
        dumped = json.dumps(s.view(viewer))
        assert not any(name in dumped for name in hidden), viewer
        assert not any(c.printing_id in dumped for c in s.state.planechase.deck[1:]), viewer
        assert s.view(viewer)["planechase"]["current"]["name"] == s.state.planechase.deck[0].name


def test_undo_replay_and_saves_are_exact(cards, monkeypatch):
    s = table(cards, phenomena=False)
    script(monkeypatch, [1, 2, 1, 5])
    for _ in range(4):
        act(s, "p1", type="planar_roll")
    replay_matches(s)
    walked = s.state.planechase.model_dump()
    s.undo("p1")
    assert s.state.planechase.rolls == 3 and s.state.planechase.walks == 2
    s.redo("p1")
    assert s.state.planechase.model_dump() == walked
    dumped = s.state.model_dump(mode="json")
    again = GameState.model_validate(dumped)
    assert again.model_dump(mode="json") == dumped and again.planechase.model_dump() == walked


def test_the_host_deals_and_puts_away_a_deck_at_the_table(cards):
    s = table(cards, on=False)
    with pytest.raises(ActionError, match="isn't playing Planechase"):
        act(s, "p1", type="planar_roll")
    act(s, "p1", type="planar_start", count=5, phenomena=False)
    pc = s.state.planechase
    assert len(pc.deck) == 5 and s.state.settings.planechase and all(not c.phenomenon for c in pc.deck)
    assert line(s).startswith("Alice dealt a planar deck of 5 cards. The table starts on ")
    replay_matches(s)
    act(s, "p1", type="planar_end")
    assert s.state.planechase is None and not s.state.settings.planechase and s.view("p1")["planechase"] is None
    s.undo("p1")
    assert s.state.planechase is not None and s.state.planechase.deck == pc.deck


def test_off_by_default_changes_nothing(cards):
    assert not GameSettings().planechase
    land = cards.resolve("Mountain")
    setups = [PlayerSetup(n, cards=[DeckCard("main", 9, land["name"], land["id"])]) for n in ("Alice", "Bob")]
    called = []
    state = new_game(setups, shuffle=False, planar_pool=lambda: called.append(1) or [])
    assert state.planechase is None and not called and state.log == []
    assert GameSession(state, cards=cards).view("p1")["planechase"] is None


def test_creating_a_game_with_planechase(client):
    res = client.post("/api/games", json={"players": [{"name": "A"}, {"name": "B"}], "planechase": True, "planar_deck_size": 6})
    assert res.status_code == 201, res.text
    gid = res.json()["game"]["id"]
    view = client.get(f"/api/games/{gid}/view", params={"viewer": "p1"}).json()
    assert view["planechase"]["count"] == 6 and view["game"]["settings"]["planechase"]
    plain = client.post("/api/games", json={"players": [{"name": "A"}]}).json()["game"]["id"]
    assert client.get(f"/api/games/{plain}/view", params={"viewer": "p1"}).json()["planechase"] is None


def test_the_lobby_setting_deals_at_the_start(client):
    res = client.post("/api/games", json={"mode": "lan", "lobby": True, "seats": 2, "players": [{"name": "Alice"}]})
    gid, alice = res.json()["game"]["id"], res.json()["seat"]["token"]
    h = {"X-Seat-Token": alice}
    res = client.post(f"/api/games/{gid}/lobby/settings", json={"planechase": True, "planar_phenomena": False}, headers=h)
    assert res.status_code == 200 and res.json()["settings"]["planechase"]
    assert client.post(f"/api/games/{gid}/lobby/start", json={"force": True}, headers=h).status_code == 200
    view = client.get(f"/api/games/{gid}/view", headers=h).json()
    assert view["planechase"]["count"] == 10 and not view["planechase"]["current"]["phenomenon"]


def test_a_planes_picture_is_fetched_when_first_shown(client, monkeypatch):
    """No deck brings a plane's art: like a token's, it is linked from Scryfall the first time a table shows it (app/cards/token_art.py)."""
    import httpx

    monkeypatch.setattr("app.cards.token_art.DOWNLOADS", True)
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(200, content=b"\xff\xd8\xff\xe0plane", headers={"Content-Type": "image/jpeg"})

    client.app.state.services.http_client = lambda user_agent, timeout=60.0: httpx.Client(transport=httpx.MockTransport(handler))
    assert client.get(f"/api/images/{PLANES[0]['id']}").status_code == 200 and calls == ["https://cards.scryfall.io/normal/front/p1.jpg"]
    sol_ring = next(c for c in fixture_cards() if c["name"] == "Sol Ring")
    assert client.get(f"/api/images/{sol_ring['id']}").status_code == 404 and len(calls) == 1  # (a deck's own card: still never)


# -- the die's cost with rules automation on (app/rules/planar_die.py): ``roll_planar_die`` pays {N} from the pool or opens the
# "tap your mana" prompt, as every cost at the table; the first roll in a turn is free; the manual ``planar_roll`` still works.
def automated(cards, *, to_main: bool = True) -> tuple[GameSession, list[str]]:
    from tests.game_helpers import enable

    s = table(cards)
    enable(s.state)
    for prefs in s.state.rules.prefs.values():
        prefs.payment = "self"  # the table default: players tap their own mana
    s = GameSession(s.state, cards=cards)
    if not to_main:
        return s, []
    act(s, "p1", type="pass_priority")  # → Alice's main phase
    assert s.state.turn.phase == "main1" and s.state.rules.priority == "p1"
    lands = [c.id for c in s.state.cards.values() if c.name == "Mountain" and c.zone == "p1:library"][:3]
    act(s, "p1", type="move", card_ids=lands, to={"zone": "battlefield"})
    return s, lands


def test_with_automation_the_first_roll_is_free_and_the_next_asks_you_to_tap_mana(cards, monkeypatch):
    from tests.game_helpers import mana_pool

    s, lands = automated(cards)
    script(monkeypatch, [4, 5, 3])
    act(s, "p1", type="roll_planar_die")
    pc = s.state.planechase
    assert pc.rolls == 1 and pc.last_roll.face == "blank" and pc.last_roll.cost == 0 and s.state.rules.decision is None
    assert s.state.rules.priority == "p1" and not any(s.state.cards[c].tapped for c in lands)
    seq = pc.last_roll.seq
    act(s, "p1", type="roll_planar_die")  # {1}, and the pool is empty: the prompt, nothing rolled yet
    d = s.state.rules.decision
    assert d is not None and d.display["kind"] == "tap_mana" and d.display["cost"] == "{1}" and set(d.display["sources"]) == set(lands)
    assert s.state.planechase.rolls == 1 and s.state.planechase.last_roll.seq == seq
    with pytest.raises(ActionError, match="Tap your mana first"):
        act(s, "p1", type="choose", decision_id=d.id, option_ids=["pay"])
    act(s, "p1", type="activate_ability", card_id=lands[0], ability=0)  # Alice taps a Mountain: the die is paid and rolled
    pc = s.state.planechase
    assert s.state.rules.decision is None and pc.rolls == 2 and pc.last_roll.cost == 1 and pc.last_roll.seq != seq
    assert s.state.cards[lands[0]].tapped and mana_pool(s) == {}
    assert "rolled the planar die (cost {1}): blank" in line(s)
    replay_matches(s)
    s.undo("p1")  # the tap that paid goes back, and the roll with it: the Mountain untapped, the prompt open again
    assert s.state.planechase.rolls == 1 and not s.state.cards[lands[0]].tapped and mana_pool(s) == {}
    assert s.state.rules.decision is not None and s.state.rules.decision.display["cost"] == "{1}"
    replay_matches(s)


def test_with_automation_mana_in_the_pool_pays_at_once_and_cancel_rolls_nothing(cards, monkeypatch):
    from tests.game_helpers import mana_pool

    s, lands = automated(cards)
    script(monkeypatch, [3, 2])
    act(s, "p1", type="roll_planar_die")
    act(s, "p1", type="roll_planar_die")
    d = s.state.rules.decision
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["cancel"])  # refused: nothing paid, nothing rolled
    assert s.state.rules.decision is None and s.state.planechase.rolls == 1 and s.state.rules.priority == "p1"
    act(s, "p1", type="activate_ability", card_id=lands[0], ability=0)
    act(s, "p1", type="activate_ability", card_id=lands[1], ability=0)
    assert mana_pool(s) == {"R": 2}
    act(s, "p1", type="roll_planar_die")  # {1} from the pool, no prompt
    pc = s.state.planechase
    assert s.state.rules.decision is None and pc.rolls == 2 and pc.last_roll.face == "chaos" and mana_pool(s) == {"R": 1}
    replay_matches(s)


def test_with_automation_the_die_is_rolled_only_in_your_main_phase_with_an_empty_stack(cards, monkeypatch):
    s, _ = automated(cards, to_main=False)
    assert s.state.turn.phase not in ("main1", "main2") and s.state.rules.priority == "p1"
    with pytest.raises(ActionError, match="main phase"):
        act(s, "p1", type="roll_planar_die")
    with pytest.raises(ActionError, match="priority"):
        act(s, "p2", type="roll_planar_die")
    act(s, "p1", type="pass_priority")
    card_id = next(c.id for c in s.state.cards.values() if c.zone == "p1:library")
    act(s, "p1", type="move", card_ids=[card_id], to={"zone": "stack"})  # (something on the stack, put there by hand)
    assert s.state.zones.get("stack")
    with pytest.raises(ActionError, match="stack is empty"):
        act(s, "p1", type="roll_planar_die")


def test_with_automation_a_roll_by_hand_is_a_manual_override(cards, monkeypatch):
    s, _ = automated(cards)
    script(monkeypatch, [3])
    act(s, "p1", type="planar_roll")  # (the table tools still roll: the cost isn't charged, and the log says it was by hand)
    assert s.state.planechase.rolls == 1 and s.state.log[-1].manual
    with pytest.raises(ActionError, match="Rules automation is off"):
        act(table(cards), "p1", type="roll_planar_die")  # (a manual table rolls with planar_roll and pays by hand)

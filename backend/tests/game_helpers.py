from __future__ import annotations

from typing import Any

from app.cards.repository import CardRepository
from app.game.factory import DeckCard, PlayerSetup, new_game
from app.game.session import GameSession
from app.game.state import CardInstance, GameState


def deck(cards: CardRepository, commander: str, spells: list[tuple[int, str]]) -> list[DeckCard]:
    cmd = cards.resolve(commander)
    out = [DeckCard("commander", 1, cmd["name"], cmd["id"])]
    for qty, name in spells:
        card = cards.resolve(name)
        out.append(DeckCard("main", qty, card["name"], card["id"]))
    return out


def make_session(cards: CardRepository, *, shuffle: bool = False) -> GameSession:
    p1 = deck(cards, "Krenko, Mob Boss", [(1, "Sol Ring"), (1, "Lightning Bolt"), (1, "Llanowar Elves"),
                                           (1, "Fire // Ice"), (1, "Delver of Secrets"), (10, "Mountain")])
    p2 = deck(cards, "Atraxa, Praetors' Voice", [(1, "Counterspell"), (1, "Arcane Signet"), (1, "Command Tower"),
                                                  (1, "Bonecrusher Giant"), (12, "Island")])
    p1 += [DeckCard("sideboard", 1, "Seething Song", cards.resolve("Seething Song")["id"])]
    state = new_game([PlayerSetup("Alice", cards=p1), PlayerSetup("Bob", cards=p2)], name="Test", shuffle=shuffle)
    return GameSession(state, cards=cards)


def zone(state: GameState, pid: str, name: str) -> list[str]:
    return state.zones[f"{pid}:{name}"]


def find(state: GameState, name: str, pid: str | None = None) -> CardInstance:
    for c in state.cards.values():
        if c.name == name and (pid is None or c.owner == pid):
            return c
    raise AssertionError(f"{name} not in game")


def act(session: GameSession, actor: str, **payload: Any):
    return session.perform(actor, payload)


def enable(state, level="full"):
    """Turn rules automation on for a table before play starts (like the API does)."""
    from app.game.rules_state import AUTOMATION_PRESETS, start_rules

    state.settings.automation = level
    state.settings.automation_options = AUTOMATION_PRESETS[level].model_copy()
    start_rules(state)
    engine_pays(state)
    return state


def engine_pays(state):
    """Most engine tests exercise payments with the internal AUTO payer; players at a real table
    always tap their own mana (payment "self", tested in test_rules_self_tap.py)."""
    from app.game.rules_state import PlayerPrefs

    if state.rules is not None:
        for pid in state.players:
            state.rules.prefs.setdefault(pid, PlayerPrefs()).payment = "auto"


def turn_on(s, level="full", *, arrived=(), land=False, player="p1"):
    """Turn automation on mid-game and answer the reconciliation questions: creatures in
    ``arrived`` came this turn, all others were already there."""
    act(s, player, type="configure", automation=level)
    engine_pays(s.state)
    d = s.state.rules.decision
    if d is not None and d.kind == "reconcile":
        answers = []
        for group in dict.fromkeys(o.group for o in d.options):
            if group == "land":
                answers.append("land:yes" if land else "land:no")
            else:
                cid = group.split(":", 1)[1]
                answers.append(f"{cid}:new" if cid in arrived else f"{cid}:old")
        act(s, d.player, type="choose", decision_id=d.id, option_ids=answers)


def mana_pool(session: GameSession, pid: str = 'p1') -> dict[str, int]:
    """The unrestricted pool players see, including remembered source identities."""
    player = session.state.players[pid]
    pool = dict(player.mana)
    for unit in player.mana_units:
        if not unit.only and not unit.riders:
            pool[unit.sym] = pool.get(unit.sym, 0) + 1
    return pool

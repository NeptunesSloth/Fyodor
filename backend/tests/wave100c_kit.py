"""Shared helpers of the wave 100C scenario tests: real Oracle text from tests/fixtures/wave100c_static_spells_cards.json (copied from
data/cards.sqlite), the wave 9C table (Alice and Bob, rules automation on), and small resolution helpers."""

from __future__ import annotations

import json
from pathlib import Path

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, deck, enable

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave100c_static_spells_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w100c", number=f"C{i:03d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]


def open_repo(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def three(cards, a=(), b=(), c=()):
    """Alice, Bob and Carol; each deck is the named cards plus basic lands."""
    decks = [deck(cards, "Krenko, Mob Boss", [*((1, n) for n in a), (20, "Forest")]),
             deck(cards, "Atraxa, Praetors' Voice", [*((1, n) for n in b), (20, "Island")]),
             deck(cards, "Atraxa, Praetors' Voice", [*((1, n) for n in c), (20, "Island")])]
    s = GameSession(enable(new_game([PlayerSetup(n, cards=d) for n, d in zip(("Alice", "Bob", "Carol"), decks, strict=True)],
                                    shuffle=False)), cards=cards)
    act(s, "p1", type="pass_priority")
    return s


def named(s, name, pid="p1"):
    return [c for c in s.state.cards.values() if c.name == name and c.owner == pid]


def one(s, name, pid="p1"):
    return named(s, name, pid)[0]


def move(s, c, zone, pid=None, position=None):
    payload = {"type": "move", "card_ids": [c.id], "to": {"player": pid or c.owner, "zone": zone}}
    if position:
        payload["position"] = position
    act(s, c.owner, **payload)
    return s.state.cards[c.id]


def put_on(s, name, pid="p1"):
    """A card of that name the player owns, put onto the battlefield under their control."""
    c = next(x for x in named(s, name, pid) if not x.zone.endswith(":battlefield"))
    return move(s, c, "battlefield")


def walker(s, name, pid="p1", loyalty=3):
    """A planeswalker put onto the battlefield with its loyalty counters (put there by hand, it would have none: 704.5i)."""
    c = put_on(s, name, pid)
    act(s, pid, type="set_counter", card_id=c.id, kind="loyalty", value=loyalty)
    return s.state.cards[c.id]


def zone(s, c):
    return s.state.cards[c.id].zone


def chars(s, c):
    return Plan(s.state, s.state.cards[c.id].controller, s.cards, None).ch(s.state.cards[c.id])


def pt_of(s, c):
    from app.rules import sba

    card_ = s.state.cards[c.id]
    ch = chars(s, c)
    return sba.power(card_, ch), sba.toughness(card_, ch)


def settle(s, prefer=(), limit=80):
    """Resolve everything; a decision is answered with ``prefer`` (option ids / labels / card names) when it offers them, else its first options."""
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None:
            if d.kind in ("declare_attackers", "declare_blockers"):
                act(s, d.player, type=d.kind, **({"attackers": []} if d.kind == "declare_attackers" else {"blocks": []}))
                continue
            ids = [o.id for o in d.options]
            want = [o.id for p in prefer for o in d.options
                    if p in (o.id, o.label, s.state.cards[o.card_id].name if getattr(o, "card_id", None) in s.state.cards else None)]
            need = max(1, d.min_choices)
            pick = want[: d.max_choices or len(want)] if len(want) >= need else ids[:need]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=pick)
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return
    raise AssertionError("never settled")


def to_phase(s, phase, turn=None, limit=300):
    """Pass priority (no attackers, no blockers) until ``phase`` (of turn ``turn``); set stops to be given priority there."""
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
    raise AssertionError(f"never reached {phase} of turn {turn}")


def start_cast(s, name, pid="p1", targets=(), target_counts=None, modes=None, kicker=0, **pool):
    """Put the card in hand, add the mana, cast it (nothing resolved yet)."""
    c = one(s, name, pid)
    if not zone(s, c).endswith(":hand"):
        move(s, c, "hand")
    if pool:
        act(s, pid, type="add_mana", player=pid, mana=pool)
    kw = {"target_counts": target_counts} if target_counts is not None else {}
    if modes is not None:
        kw["modes"] = modes
    if kicker:
        kw["kicker"] = kicker
    act(s, pid, type="cast_spell", card_id=c.id, targets=list(targets), **kw)
    return s.state.cards[c.id]


def cast(s, name, pid="p1", targets=(), prefer=(), target_counts=None, modes=None, kicker=0, **pool):
    c = start_cast(s, name, pid, targets, target_counts, modes, kicker, **pool)
    settle(s, prefer)
    return s.state.cards[c.id]

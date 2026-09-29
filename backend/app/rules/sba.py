"""State-based actions (rule 704): checked before anyone gets priority, repeated until none apply.

They run inside rules intents only. A manual change (say, adding damage by hand) is picked up
the next time the engine acts, so the sandbox never fights the players mid-edit.
"""

from __future__ import annotations

from app.game.rules_state import Decision, DecisionOption
from app.game.state import CardInstance
from app.rules.characteristics import Characteristics
from app.rules.plan import Plan, decide, live_players

POISON_LETHAL = 10
COMMANDER_LETHAL = 21
MAX_ROUNDS = 50


def _num(value: str | None) -> int | None:
    try:
        return int(value) if value is not None else None
    except ValueError:
        return None  # "*" and friends: characteristic-defining abilities aren't computed yet


def toughness(card: CardInstance, ch: Characteristics) -> int | None:
    base = _num(ch.toughness)
    if base is None:
        return None
    return base + card.counters.get("+1/+1", 0) - card.counters.get("-1/-1", 0)


def power(card: CardInstance, ch: Characteristics) -> int | None:
    base = _num(ch.power)
    if base is None:
        return None
    return base + card.counters.get("+1/+1", 0) - card.counters.get("-1/-1", 0)


def check(plan: Plan) -> None:
    """Perform state-based actions until none apply (or one needs a player's decision)."""
    for _ in range(MAX_ROUNDS):
        if plan.rules.decision is not None or not _round(plan):
            return


def _round(plan: Plan) -> bool:
    """One simultaneous check. Returns True if anything happened."""
    state = plan.state
    r = plan.rules
    happened = False

    # 704.5a–c, commander damage (903.10a), empty-library draws: players lose
    for pid in live_players(state):
        p = state.players[pid]
        reason = None
        if p.life <= 0:
            reason = "0 or less life"
        elif p.resources.get("poison", 0) >= POISON_LETHAL:
            reason = f"{POISON_LETHAL} poison counters"
        elif any(v >= COMMANDER_LETHAL for v in p.commander_damage.values()):
            reason = f"{COMMANDER_LETHAL} combat damage from one commander"
        elif pid in r.drew_from_empty:
            reason = "drew from an empty library"
        if reason:
            r.lost[pid] = reason
            plan.note(f"{p.name} loses the game ({reason})")
            happened = True
    left = live_players(state)
    if happened and len(left) == 1 and r.winner is None:
        r.winner = left[0]
        plan.note(f"{state.players[left[0]].name} wins the game")

    dying: list[tuple[CardInstance, str]] = []
    annihilate: list[tuple[CardInstance, int]] = []
    legends: dict[tuple[str, str], list[CardInstance]] = {}
    for card in list(state.cards.values()):
        if card.is_token and not card.zone.endswith(":battlefield") and card.zone != "stack":
            plan.do({"type": "delete_card", "card_ids": [card.id], "force": True}, actor=card.owner)  # 704.5d
            happened = True
            continue
        if not card.zone.endswith(":battlefield"):
            continue
        ch = plan.ch(card)
        plus, minus = card.counters.get("+1/+1", 0), card.counters.get("-1/-1", 0)
        if plus and minus:
            annihilate.append((card, min(plus, minus)))  # 704.5q
        if ch.is_creature:
            t = toughness(card, ch)
            if t is not None and t <= 0:
                dying.append((card, "0 toughness"))  # 704.5f (indestructible doesn't help)
            elif t is not None and card.damage >= t and "indestructible" not in ch.keywords:
                dying.append((card, "lethal damage"))  # 704.5g
            elif card.id in r.deathtouched and card.damage > 0 and "indestructible" not in ch.keywords:
                dying.append((card, "damage from a deathtouch source"))  # 704.5h
        if "Planeswalker" in ch.types and card.counters.get("loyalty", 0) <= 0:
            dying.append((card, "no loyalty"))  # 704.5i
        if "Legendary" in ch.supertypes and ch.name:
            legends.setdefault((card.controller, ch.name), []).append(card)

    for card, n in annihilate:
        plan.do({"type": "counter", "card_ids": [card.id], "kind": "+1/+1", "delta": -n}, actor=card.controller)
        plan.do({"type": "counter", "card_ids": [card.id], "kind": "-1/-1", "delta": -n}, actor=card.controller)
        happened = True
    for card, reason in dying:
        plan.note(f"State-based action: {reason} →", [card.id])
        plan.do({"type": "move", "card_ids": [card.id], "to": {"player": card.owner, "zone": "graveyard"}},
                actor=card.controller)
        r.deathtouched = [c for c in r.deathtouched if c != card.id]
        happened = True

    # 704.5j legend rule: the controller chooses one to keep (one decision at a time)
    for (controller, name), group in legends.items():
        alive = [c for c in group if c.id in state.cards and state.cards[c.id].zone.endswith(":battlefield")]
        if len(alive) > 1:
            decide(plan, player=controller, kind="choose_one",
                   prompt=f"Legend rule: choose which {name} to keep (the others go to the graveyard)",
                   options=[DecisionOption(id=c.id, label=f"{name} #{i + 1}", card_id=c.id) for i, c in enumerate(alive)],
                   resume={"step": "legend_rule", "cards": [c.id for c in alive]})
            return True

    # 903.9a: a commander put into a graveyard or exile may go to the command zone instead
    for card in state.cards.values():
        if not card.commander_key:
            continue
        zone = card.zone.split(":")[-1]
        if zone in ("graveyard", "exile"):
            if r.commander_offered.get(card.id) != card.zone:
                r.commander_offered[card.id] = card.zone
                decide(plan, player=card.owner, kind="confirm",
                       prompt=f"Move {card.name} to the command zone?",
                       options=[DecisionOption(id="yes", label="Command zone"),
                                DecisionOption(id="no", label=f"Leave it in {zone}")],
                       resume={"step": "commander_zone", "card": card.id}, source=card)
                return True
        else:
            r.commander_offered.pop(card.id, None)
    return happened


def resume_legend_rule(plan: Plan, d: Decision, chosen: list[str]) -> None:
    assert d.resume is not None
    keep = chosen[0]
    others = [cid for cid in d.resume["cards"] if cid != keep and cid in plan.state.cards]
    if others:
        plan.do({"type": "move", "card_ids": others, "to": {"zone": "graveyard"}}, actor=d.player)


def resume_commander_zone(plan: Plan, d: Decision, chosen: list[str]) -> None:
    assert d.resume is not None
    card = plan.state.cards.get(d.resume["card"])
    if card is not None and chosen[0] == "yes":
        plan.do({"type": "move", "card_ids": [card.id], "to": {"player": card.owner, "zone": "command"}},
                actor=card.owner)

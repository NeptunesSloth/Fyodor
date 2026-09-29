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


class Found:
    """The state-based actions that apply right now. They are performed simultaneously."""

    def __init__(self) -> None:
        self.losers: list[tuple[str, str]] = []
        self.vanishing: list[CardInstance] = []  # tokens outside the battlefield (704.5d)
        self.annihilate: list[tuple[CardInstance, int]] = []
        self.dying: list[tuple[CardInstance, str]] = []

    def visible(self) -> bool:
        return bool(self.losers or self.annihilate or self.dying)

    def fingerprint(self) -> str:
        return "|".join([*(f"L{p}" for p, _ in self.losers), *(f"D{c.id}:{why}" for c, why in self.dying),
                         *(f"A{c.id}:{n}" for c, n in self.annihilate)])

    def summary(self, plan: Plan) -> str:
        parts = [f"{plan.name(p)} loses ({why})" for p, why in self.losers]
        parts += [f"{c.name} dies ({why})" for c, why in self.dying]
        parts += [f"{c.name}: +1/+1 and -1/-1 counters cancel" for c, _ in self.annihilate]
        return "; ".join(parts)


def find(plan: Plan) -> Found:
    state = plan.state
    r = plan.rules
    out = Found()
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
            out.losers.append((pid, reason))
    for card in list(state.cards.values()):
        if card.is_token and not card.zone.endswith(":battlefield") and card.zone != "stack":
            out.vanishing.append(card)
            continue
        if not card.zone.endswith(":battlefield") or not plan.in_game(card):
            continue
        ch = plan.ch(card)
        plus, minus = card.counters.get("+1/+1", 0), card.counters.get("-1/-1", 0)
        if plus and minus:
            out.annihilate.append((card, min(plus, minus)))  # 704.5q
        if ch.is_creature:
            t = toughness(card, ch)
            if t is not None and t <= 0:
                out.dying.append((card, "0 toughness"))  # 704.5f (indestructible doesn't help)
            elif t is not None and card.damage >= t and "indestructible" not in ch.keywords:
                out.dying.append((card, "lethal damage"))  # 704.5g
            elif card.id in r.deathtouched and card.damage > 0 and "indestructible" not in ch.keywords:
                out.dying.append((card, "damage from a deathtouch source"))  # 704.5h
        if "Planeswalker" in ch.types and card.counters.get("loyalty", 0) <= 0:
            out.dying.append((card, "no loyalty"))  # 704.5i
    return out


def _round(plan: Plan, *, confirmed: bool = False) -> bool:
    """One simultaneous check. Returns True if anything happened."""
    state = plan.state
    r = plan.rules
    found = find(plan)
    if found.vanishing:
        plan.do({"type": "delete_card", "card_ids": [c.id for c in found.vanishing], "force": True},
                actor=found.vanishing[0].owner)
    if found.visible() and not (confirmed or plan.options.auto_sba):
        # ASSISTED: show what the rules say happens and let the table confirm (or handle it by
        # hand). A declined set isn't asked about again until something changes.
        fingerprint = found.fingerprint()
        if r.sba_declined == fingerprint:
            return bool(found.vanishing)
        decide(plan, player=plan.active, kind="confirm", prompt=f"State-based actions: {found.summary(plan)}",
               options=[DecisionOption(id="yes", label="Apply"), DecisionOption(id="no", label="Leave for now")],
               resume={"step": "sba_confirm", "fingerprint": fingerprint})
        return True
    happened = bool(found.vanishing)
    for pid, reason in found.losers:
        r.lost[pid] = reason
        plan.note(f"{state.players[pid].name} loses the game ({reason})")
        happened = True
    for card, n in found.annihilate:
        plan.do({"type": "counter", "card_ids": [card.id], "kind": "+1/+1", "delta": -n}, actor=card.controller)
        plan.do({"type": "counter", "card_ids": [card.id], "kind": "-1/-1", "delta": -n}, actor=card.controller)
        happened = True
    if found.dying:
        # All of them die at once: one move, one event batch (704.3), with last known information.
        for card, reason in found.dying:
            plan.note(f"State-based action: {reason} →", [card.id])
        dead = [card.id for card, _ in found.dying]
        plan.do({"type": "move", "card_ids": dead, "to": {"zone": "graveyard"}}, actor=found.dying[0][0].controller)
        r.deathtouched = [c for c in r.deathtouched if c not in dead]
        happened = True
    if found.losers:
        from app.rules.leave import leave_game  # leave → plan; imported late to stay acyclic

        for pid, _ in found.losers:
            leave_game(plan, pid)
        left = live_players(state)
        if len(left) == 1 and r.winner is None:
            r.winner = left[0]
            plan.note(f"{state.players[left[0]].name} wins the game")

    # 704.5j legend rule: the controller chooses one to keep (one decision at a time)
    legends: dict[tuple[str, str], list[CardInstance]] = {}
    for card in state.cards.values():
        if card.zone.endswith(":battlefield") and plan.in_game(card):
            ch = plan.ch(card)
            if "Legendary" in ch.supertypes and ch.name:
                legends.setdefault((card.controller, ch.name), []).append(card)
    for (controller, name), group in legends.items():
        if len(group) > 1:
            decide(plan, player=controller, kind="choose_one",
                   prompt=f"Legend rule: choose which {name} to keep (the others go to the graveyard)",
                   options=[DecisionOption(id=c.id, label=f"{name} #{i + 1}", card_id=c.id) for i, c in enumerate(group)],
                   resume={"step": "legend_rule", "cards": [c.id for c in group]})
            return True

    # 903.9a: a commander put into a graveyard or exile may go to the command zone instead
    for card in state.cards.values():
        if not card.commander_key:
            continue
        zone = card.zone.split(":")[-1]
        if zone in ("graveyard", "exile") and card.owner in live_players(state):
            if r.commander_offered.get(card.id) != card.zone:
                r.commander_offered[card.id] = card.zone
                key, context = f"commander_zone:{card.commander_key}", zone
                answer = remembered_answer(plan, card.owner, key, context)
                if answer in ("yes", "no"):
                    _commander_zone(plan, card, answer == "yes")
                    return True
                decide(plan, player=card.owner, kind="confirm",
                       prompt=f"Move {card.name} to the command zone?",
                       options=[DecisionOption(id="yes", label="Command zone"),
                                DecisionOption(id="no", label=f"Leave it in {zone}")],
                       resume={"step": "commander_zone", "card": card.id}, source=card,
                       memory_key=key, memory_context=context)
                return True
        else:
            r.commander_offered.pop(card.id, None)
    return happened


def remembered_answer(plan: Plan, player: str, key: str, context: str) -> str | None:
    from app.rules.engine import remembered  # engine → sba; imported late

    return remembered(plan, player, key, context)


def resume_confirm(plan: Plan, d: Decision, chosen: list[str]) -> None:
    assert d.resume is not None
    if chosen[0] == "yes":
        _round(plan, confirmed=True)
    else:
        plan.rules.sba_declined = str(d.resume.get("fingerprint", ""))
        plan.note(f"{plan.name(d.player)} left the state-based actions for now")


def _commander_zone(plan: Plan, card: CardInstance, yes: bool) -> None:
    if yes:
        plan.do({"type": "move", "card_ids": [card.id], "to": {"player": card.owner, "zone": "command"}},
                actor=card.owner)


def resume_legend_rule(plan: Plan, d: Decision, chosen: list[str]) -> None:
    assert d.resume is not None
    keep = chosen[0]
    others = [cid for cid in d.resume["cards"] if cid != keep and cid in plan.state.cards]
    if others:
        plan.do({"type": "move", "card_ids": others, "to": {"zone": "graveyard"}}, actor=d.player)


def resume_commander_zone(plan: Plan, d: Decision, chosen: list[str]) -> None:
    assert d.resume is not None
    card = plan.state.cards.get(d.resume["card"])
    if card is not None:
        _commander_zone(plan, card, chosen[0] == "yes")

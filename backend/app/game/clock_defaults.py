"""-- turn clock (stage 3) -- the safest legal default for each wait, for a player whose clock reached zero when the host chose "Act
for the player". A pure function of the table: the answers to try in order (the first the engine accepts is the one); ``[]`` leaves the
wait to the table. It never concedes or eliminates anyone: an optional choice is declined, and a wait whose answer could make a player
lose the game (a state-based loss to confirm, a "lose the game unless you pay") is left to the table. It reads only what the waited-on
player may see (their own decision and, while bottoming, their own hand). The engine stays the judge of every answer;
``app.game.dummy.answers`` gives the fallbacks.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

from app.game import dummy
from app.game.rules_state import Decision, cancelable
from app.game.state import CardInstance, GameState
from app.game.turn_clock import waiting_on

if TYPE_CHECKING:
    from app.rules.characteristics import CardInfo

log = logging.getLogger(__name__)

RULES_CONFIRMS = frozenset({"sba_confirm", "combat_damage", "trigger_confirm"})  # ASSISTED: the rules say it happens
TABLE_ONLY = frozenset({"manual_resolution", "reconcile"})  # what only the table knows
TABLE_STEPS = frozenset({"restore_global_word71"})  # a manual recovery of what an old save didn't record: only the table knows it
PAYMENT_STEPS = frozenset({"payment", "pay_mana"})  # a cast or activation's cost prompt (casting.ask_payment / ask_tap): pay / … / cancel
# The option that declines an optional choice, as each site names it: "no" (yes/no "may", tribute), "decline" (pay or decline: Browbeat,
# "pay or it's countered", optional payments), "none" ("you may choose / attach …"), "tapped" (a shock land's "If you don't, it enters
# tapped"). Earlier first: where one decision offers two ("no" and "tapped": enter untapped without rad counters), "no" declines.
DECLINES = ("no", "decline", "none", "tapped")


def answers(state: GameState, pid: str, info: CardInfo | None) -> list[dict[str, Any]]:
    """The payloads to try for ``pid``'s wait, safest first (``[]``: nothing to answer, or left to the table)."""
    key = waiting_on(state).get(pid)
    if key is None:
        return []
    if key.startswith("m:"):
        seat = state.pregame.seats.get(pid) if state.pregame is not None else None
        if seat is None:
            return []
        if seat.status == "deciding":
            # 103.5: keeping is the declaration not to take a mulligan; 103.5b: an "any time you could mulligan" action (Serum
            # Powder) is optional ("may") and is not used
            return [{"type": "mulligan_keep"}]
        # 103.5: the player puts that many cards on the bottom "in any order": which cards and their order are the player's, so the
        # first ones of the hand in hand order is an arbitrary but legal choice
        hand = state.zones.get(f"{pid}:hand", [])[:seat.to_bottom]
        return [{"type": "mulligan_bottom", "card_ids": hand}] if hand else []
    if key.startswith("p:"):
        return [{"type": "pass_priority"}]  # 117.3d: a player who takes no action passes (this priority only: no "until")
    d = state.rules.decision if state.rules is not None else None
    step = (d.resume or {}).get("step") if d is not None else None
    if d is None or d.kind in TABLE_ONLY or step in TABLE_STEPS or _could_eliminate(d):
        return []

    def choose(ids: list[str]) -> dict[str, Any]:
        return {"type": "choose", "decision_id": d.id, "option_ids": ids}

    offered = {o.id for o in d.options}
    out: list[dict[str, Any]] = []
    if cancelable(d) or (step in PAYMENT_STEPS and "cancel" in offered):
        # A cast or activation not yet complete is taken back: the engine rewinds it to before it was proposed (casting.cancelled,
        # resume_payment, resume_pay_mana: nothing committed was paid, 601.2h), as 733.1 reverses an action that can't be completed
        out.append(choose(["cancel"]))
    if d.kind == "declare_attackers":
        out.append({"type": "declare_attackers", "attackers": []})  # 508.1a: "which creatures ..., if any, will attack"
        must = (d.display or {}).get("must_attack") or {}
        # 508.1d: a requirement must be obeyed when it can be: each creature that must attack, at the first place it may
        forced = [{"card_id": cid, "target": places[0]} for cid, places in must.items() if places]
        if forced:
            out.append({"type": "declare_attackers", "attackers": forced})
        return _tidy(out)
    if d.kind == "declare_blockers":
        out.append({"type": "declare_blockers", "blocks": []})  # 509.1a: "which creatures ..., if any, will block"
        # 509.1c: the fewest blocks that obey the requirements: each creature a requirement names blocks one attacker it can; then,
        # only if that is refused, one blocker per attacker (the dummy's chumps), and every creature that can ("all") last of all
        if required := _required_blocks(d, state, info):
            out.append({"type": "declare_blockers", "blocks": required})
        for mode in ("chump", "all"):
            out += [b for b in dummy.answers(d, state=state, info=info, blocks=mode) if b.get("blocks")]
        return _tidy(out)
    if d.kind == "confirm" and step in RULES_CONFIRMS:
        # 704.3 (state-based actions are performed), 510.2 (assigned combat damage is dealt), 603.3 (a triggered ability is put on the
        # stack): ASSISTED only asks the table to confirm what the rules say happens
        out.append(choose(["yes"]))
    elif declined := next((i for i in DECLINES if i in offered), None):
        # 603.5, 608.2d, 118.12: a "may" or an optional cost is the player's choice, made as the effect applies: declined
        out.append(choose([declined]))
    if d.min_choices <= 0:
        out.append(choose([]))  # an optional ("up to") choice: nothing chosen
    # 608.2d, 700.2: otherwise the first legal options (``order``: as offered; ``divide``: as evenly as allowed, 601.2d; typed names)
    out += dummy.answers(d, state=state, info=info)
    return _tidy(out)


def _could_eliminate(d: Decision) -> bool:
    """Could an answer make a player lose the game? A state-based loss to confirm (704.5a-c, 704.6c: the decision's fingerprint lists each
    loser as ``L<player>``, sba.Found.fingerprint), or a resolving ability with a "lose the game" instruction (118.12a: "you lose the game
    unless you pay", the Pacts): left to the table."""
    resume = d.resume or {}
    if resume.get("step") == "sba_confirm":
        return any(part.startswith("L") for part in str(resume.get("fingerprint") or "").split("|"))
    ctx = resume.get("ctx")
    return isinstance(ctx, dict) and '"lose_game"' in json.dumps(ctx.get("effects") or [], default=str)


def _required_blocks(d: Decision, state: GameState, info: CardInfo | None) -> list[dict[str, str]]:
    """509.1c, as combat.block_requirements reads the requirements: each offered blocker with "blocks each combat if able" (must_block)
    blocks the first attacker it can; one told to block a given attacker (must_block_obj), or able to block a lure ("All creatures able
    to block ~ do so"), blocks that one. The engine judges the declaration (block_problem here only skips pairs it already refuses)."""
    try:
        return _plan_required(d, state, info)
    except Exception:  # noqa: BLE001 - never fail over a default: the dummy's blocks and the table remain
        log.exception("The turn clock couldn't work out the required blocks")
        return []


def _plan_required(d: Decision, state: GameState, info: CardInfo | None) -> list[dict[str, str]]:
    from app.game.resolve import NoCardInfo
    from app.rules import characteristics as chars  # (rules → game: imported late to stay acyclic)
    from app.rules import combat, layers, scripts
    from app.rules.statics import rule_arg

    cards: Any = info if info is not None else NoCardInfo()
    r = state.rules
    if r is None:
        return []

    def offered(prefix: str) -> list[CardInstance]:
        return [state.cards[o.id[2:]] for o in d.options if o.id.startswith(prefix) and o.id[2:] in state.cards]

    blockers, attackers = offered("b:"), offered("a:")
    ch = {c.id: layers.derive(state, c, chars.of(c, cards), cards) for c in blockers + attackers}
    lures = {a.id for a in attackers if any(rule_arg(x)[0] == "lure" for x in scripts.statics(ch[a.id]))}
    out: list[dict[str, str]] = []
    for b in blockers:
        rules = [rule_arg(x) for x in scripts.statics(ch[b.id])]
        wanted = {arg for name, arg in rules if name == "must_block_obj"}
        able = [a for a in attackers if combat.block_problem(state, b, ch[b.id], a, ch[a.id], cards) is None]
        pick = next((a for a in able if r.object_id(a.id) in wanted or a.id in lures), None)
        if pick is None and any(name == "must_block" for name, _ in rules) and able:
            pick = able[0]
        if pick is not None:
            out.append({"blocker_id": b.id, "attacker_id": pick.id})
    return out


def _tidy(out: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Each answer once, in order, at most ``dummy.MAX_TRIES + 2``."""
    seen: list[dict[str, Any]] = []
    for p in out:
        if p not in seen:
            seen.append(p)
    return seen[:dummy.MAX_TRIES + 2]

"""-- turn clock (stage 3) -- the safest legal default for each wait, for a player whose clock reached zero when the host chose "Act
for the player". A pure function of the table: the answers to try in order (the first the engine accepts is the one); ``[]`` leaves the
wait to the table. It never concedes for anyone, and it never chooses a loss: an optional choice is declined, a wait whose answer could
make a player lose the game (a state-based loss to confirm, a "lose the game unless you pay") is left to the table, and a required choice
offering players is never aimed at the timed-out player while another legal answer exists (a permanent first, then an opponent; only
themself: the table decides). It reads only what the waited-on
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
# Where declining, or not paying, brings a harm to the player deciding: the clock leaves these to the table. By the engine's own step:
# "bane100e" (Enchanter's Bane: "no" is "Take N damage"), "gy_pairs110g" and "cu_exile110n" (cumulative upkeep, 702.24a: not paying
# sacrifices the permanent). ``pay_or_sacrifice`` is judged by its resume in _decline_harms.
HARMFUL_DECLINES = frozenset({"bane100e", "gy_pairs110g", "cu_exile110n"})
# 903.9a / 903.9b: "put your commander into the command zone?" (yes = the command zone), by the step that asks it
COMMANDER_STEPS = frozenset({"commander_zone", "commander_instead", "commander_first", "exchange_hand_library", "exchange_zones94",
                             "library_placements", "life_command86", "post_mill_command60", "public_command65"})


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
    if _decline_harms(d):
        return []  # declining (not paying) would harm the player: the clock doesn't choose, the table does
    if d.kind == "confirm" and step in RULES_CONFIRMS:
        # 704.3 (state-based actions are performed), 510.2 (assigned combat damage is dealt), 603.3 (a triggered ability is put on the
        # stack): ASSISTED only asks the table to confirm what the rules say happens
        out.append(choose(["yes"]))
    elif "yes" in offered and (step in COMMANDER_STEPS or (step == "cost_moves" and (d.resume or {}).get("stage") == "commander")):
        # 903.9a / 903.9b: its owner may put the commander into the command zone (from a graveyard or exile; instead of a hand or
        # library): the default every Commander player expects
        out.append(choose(["yes"]))
    elif "map" not in (d.resume or {}) and (declined := next((i for i in DECLINES if i in offered), None)):
        # 603.5, 608.2d, 118.12: a "may" or an optional cost is the player's choice, made as the effect applies: declined (a harmless
        # decline only: see _decline_harms; replace.py's "map" yes/no is an order of replacement effects, 616.1, not a decline)
        out.append(choose([declined]))
    if d.min_choices <= 0:
        out.append(choose([]))  # an optional ("up to") choice: nothing chosen
    # -- never at themself (final fix C1) -- a choice offering players (115.1 / 601.2c / 603.3d: "any target", "target player")
    ranks = _target_ranks(d, state, pid)
    if ranks is not None:
        if d.kind == "divide":
            # 601.2d: the division among targets already chosen: when the timed-out player is one of them (their own earlier choice),
            # how much they deal themself is left to the table
            return [] if pid in ranks else _tidy(out + dummy.answers(d, state=state, info=info))
        # the least drastic options first (ruling: a permanent over a player), the dummy's first legal options over that order
        d = d.model_copy(update={"options": sorted(d.options, key=lambda o: ranks.get(o.id, 0))})
    # 608.2d, 700.2: otherwise the first legal options (``order``: as offered; ``divide``: as evenly as allowed, 601.2d; typed names)
    out += dummy.answers(d, state=state, info=info)
    if ranks is not None:
        out.sort(key=lambda a: max((ranks.get(i, 0) for i in a.get("option_ids") or []), default=0))  # (stable)
        if all(pid in (a.get("option_ids") or []) for a in out):
            return []  # every answer names the timed-out player: the table decides
    return _tidy(out)


# The order the clock tries the options of a choice that offers players (final fix C1; a controller ruling, the owner may overrule): an
# object someone else controls (an opponent's permanent), the timed-out player's own permanent, an opponent, the timed-out player last.
_OTHERS_OBJECT, _OWN_OBJECT, _OPPONENT, _SELF = 0, 1, 2, 3


def _target_ranks(d: Decision, state: GameState, pid: str) -> dict[str, int] | None:
    """Each option's rank, for a decision offering at least one player (a target or player choice); None for any other (modes, cards,
    trigger order …: as offered). The timed-out player ``pid`` is ranked last, so the clock never aims a required choice at them while
    any other legal answer exists (the anti-goal: a clock that makes a player lose the game); a permanent comes before any player, so
    its pick is the least drastic (no opponent eliminated by a target the clock chose, where a permanent is offered)."""
    if d.kind in ("order", "reconcile") or not any(o.id in state.players for o in d.options):
        return None
    out: dict[str, int] = {}
    for o in d.options:
        if o.id in state.players:
            out[o.id] = _SELF if o.id == pid else _OPPONENT
            continue
        card = state.cards.get(o.id) or (state.cards.get(o.card_id) if o.card_id else None)
        out[o.id] = _OWN_OBJECT if card is not None and card.controller == pid else _OTHERS_OBJECT
    return out


def _decline_harms(d: Decision) -> bool:
    """Would declining (not paying) bring a harm to the player deciding? Then the clock doesn't pick. ``pay_or_sacrifice`` is the step of
    three kinds of question:

    * "pay or it's countered" (effects.py, resume ``counter``): their own spell is countered: harmless, declined;
    * an optional payment (optional_payment.py, resume ``opt``): "you may pay … If you do" (every reading of its binding a plain
      ``{"succeeded": bind}`` gate) only forgoes a benefit: declined; "… unless they pay" / "If you don't" (118.12a: read negated,
      ``negate`` or ``not``) brings the other branch: declined only when that branch merely benefits someone else (Smothering Tithe's
      Treasure), else (Painful Quandary's 5 life, Essence Vortex's destroy) left to the table; any other reading (_payment_gates): the table;
    * "sacrifice ~ unless you pay", echo, cumulative upkeep (effects.pay_or_sacrifice: pay / sacrifice): left to the table.
    """
    resume = d.resume or {}
    step = resume.get("step")
    if step in HARMFUL_DECLINES:
        return True
    if step == "stack_enter_choice":
        from app.rules import tribute

        # 702.104a: tribute's chosen opponent decides; "if tribute wasn't paid" punishes them (Pharagax Giant's 5 damage to each
        # opponent, Shrike Harpy's sacrifice …): left to the table
        return resume.get("what") == tribute.WHAT
    if step != "pay_or_sacrifice" or "counter" in resume:
        return False
    opt, ctx = resume.get("opt"), resume.get("ctx")
    if not isinstance(opt, dict) or not isinstance(ctx, dict):
        return True
    gates = _payment_gates(ctx, opt)
    if gates is None:
        return True  # a reading of the payment this module can't place: the table decides (fail-safe)
    if not any(negated for _, negated, _ in gates):
        return False  # 118.12: only plain "If you do" gates: declining only forgoes their benefit
    return not _unpaid_only_benefits_others(ctx, opt, gates)


# What the not-paid branch may do and still be harmless to the payer: the ability's controller ("you", never the payer) gets something
# (Smothering Tithe's Treasure, Rhystic Study's draw). ``may_rest`` is the "you may" marker of such a branch. Anything else: the table.
_BENEFITS = frozenset({"create_token", "draw", "gain_life", "scry", "surveil"})
# The readings of a payment's binding the engine has (conditions.holds): ``{"succeeded": b}`` ("If you do"), ``{"succeeded": b,
# "negate": True}`` and ``{"not": {"succeeded": b}}`` ("If you don't", 118.12a), and anything else (a ``flag`` verdict recorded by a
# gate's own ``bind``, an ``any`` / ``all``, a ``ref:`` to what it moved, a primitive reading it in code): only the first three, as the
# whole condition of a plain top-level ``only_if``, are placed; any other is unplaced and leaves the payment to the table.
_GATE_KEYS = frozenset({"do", "cond", "skip"})


def _payment_gates(ctx: dict[str, Any], opt: dict[str, Any]) -> list[tuple[int, bool, int]] | None:
    """The gates on the payment ``opt["bind"]`` in the resolution ``ctx``, as (index, negated, skip): or None when anything in the
    resolution mentions the binding other than its own ``optional_payment`` and plain gates, or when an instruction after the payment
    isn't inside a gate's range (a primitive could read the binding in code, by a name the data doesn't show). Fail-safe by
    construction: every string containing the binding's name, anywhere in the resolution (its effects and any other part but the
    recorded bindings), must be one of those placed readings."""
    bind, effects = opt.get("bind"), ctx.get("effects")
    if not isinstance(bind, str) or not bind or not isinstance(effects, list):
        return None
    pays = [i for i, e in enumerate(effects) if isinstance(e, dict) and e.get("do") == "optional_payment" and e.get("bind") == bind]
    if len(pays) != 1:
        return None
    at = pays[0]
    gates: list[tuple[int, bool, int]] = []
    placed: set[tuple[Any, ...]] = {("effects", at, "bind")}
    for i, e in enumerate(effects):
        if i <= at or not isinstance(e, dict) or set(e) != _GATE_KEYS or e.get("do") != "only_if":
            continue
        skip, cond = e.get("skip"), e.get("cond")
        if type(skip) is not int or skip < 0:
            continue
        if cond == {"succeeded": bind}:
            gates.append((i, False, skip))
            placed.add(("effects", i, "cond", "succeeded"))
        elif cond == {"succeeded": bind, "negate": True}:
            gates.append((i, True, skip))
            placed.add(("effects", i, "cond", "succeeded"))
        elif cond == {"not": {"succeeded": bind}}:
            gates.append((i, True, skip))
            placed.add(("effects", i, "cond", "not", "succeeded"))
    rest = {k: v for k, v in ctx.items() if k not in ("refs", "paid_x")}  # (the recorded bindings are results, not readings)
    if any(path not in placed for path in _mentions(rest, bind, ())):
        return None
    # every instruction after the payment lies in the range of a gate on it, the gates one after another to the end
    starts = {i: skip for i, _, skip in gates}
    j = at + 1
    while j < len(effects):
        if j not in starts:
            return None
        j += 1 + starts[j]
    return gates if gates and j == len(effects) else None


def _mentions(node: Any, bind: str, path: tuple[Any, ...]) -> list[tuple[Any, ...]]:
    """The path of every string (value or key) that contains ``bind``, at any depth."""
    if isinstance(node, str):
        return [path] if bind in node else []
    if isinstance(node, dict):
        out = [(*path, k, "<key>") for k in node if isinstance(k, str) and bind in k]
        for k, v in node.items():
            out += _mentions(v, bind, (*path, k))
        return out
    if isinstance(node, (list, tuple)):
        return [p for i, v in enumerate(node) for p in _mentions(v, bind, (*path, i))]
    return []


def _unpaid_only_benefits_others(ctx: dict[str, Any], opt: dict[str, Any], gates: list[tuple[int, bool, int]]) -> bool:
    """118.12 / 118.12a: the instructions in the range of each negated gate (``{"succeeded": bind, "negate": True}`` or ``{"not":
    {"succeeded": bind}}``) are what not paying does. Harmless to decline only when each of them gives something to the ability's
    controller and the payer is someone else; anything else (another instruction, another recipient, a condition in the branch) isn't
    (fail-safe)."""
    if opt.get("payer") in (None, ctx.get("controller")):
        return False
    effects = ctx["effects"]
    branch = [e for i, negated, skip in gates if negated for e in effects[i + 1:i + 1 + skip]]
    if not branch or any(w in json.dumps(branch, default=str) for w in ('"cond"', '"succeeded"', '"flag"', '"not"')):
        return False
    return all(isinstance(e, dict) and (e.get("do") == "may_rest" or (e.get("do") in _BENEFITS and e.get("who") == "you"))
               for e in branch)


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
    from app.rules import combat, combat_rules, layers, scripts, wave110m_cards
    from app.rules.plan import Plan
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
    plan = Plan(state, d.player, cards, None)  # (a scratch copy: has_block_cost reads the costs through a plan)
    out: list[dict[str, str]] = []
    for b in blockers:
        if combat_rules.has_block_cost(plan, b.id, ch[b.id]):
            continue  # 509.1c: "that player is not required to pay that cost" (combat.block_requirements exempts it too)
        rules = [rule_arg(x) for x in scripts.statics(ch[b.id])]
        wanted = {arg for name, arg in rules if name == "must_block_obj"}
        able = [a for a in attackers if not wave110m_cards.attacker_tax(ch[a.id])  # (Awesome Presence: a cost to block it, 509.1c)
                and combat.block_problem(state, b, ch[b.id], a, ch[a.id], cards) is None]
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

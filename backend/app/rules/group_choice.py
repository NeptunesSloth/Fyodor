# -- group choices (wave 53D) --
"""Group choices: several players choose at once, and what they chose is used afterwards.
"Each player chooses a creature type. Destroy all creatures that aren't of a type chosen this way." (Harsh Mercy), "Each player chooses a
creature type. Each player returns all creature cards of a type chosen this way …" (Patriarch's Bidding), "Each opponent chooses fame or
fortune. For each player who chose fame, …" (Seize the Spotlight, Master of Ceremonies), and the secret ones: "Each player secretly chooses a
number … then all players reveal those numbers simultaneously" (Wheel of Misfortune, Menacing Ogre), "Each opponent secretly chooses silence
or snitch, then the choices are revealed" (Prisoner's Dilemma). Researched against CR 2026-09-25 and the cards' rulings.

State (``ctx["gc"][name]``, in the resolution context of the pending decision: server-side only, saved with the game, old saves have none):
``order`` (the players still to choose, APNAP), ``i`` (how many have chosen), ``ballots`` ([[player, value], …] in the order chosen),
``secret``. When the last has chosen, each value's players are bound as ``<name>:<value>`` (players bindings: ``who: "ref:<name>:<value>"``).

* 101.4: the players choose in APNAP order (active player first, then turn order; ``start`` "you" / "next" begins with the ability's
  controller / the next opponent, 101.4 "starting with …"), each knowing the earlier public choices (101.4b: they are logged as made and
  repeated in the prompt); everything the choices do happens afterwards, all at once.
* A choice is a creature type (205.3m), a color (105.1), a basic land type, a listed word with no rules meaning (207.2c style: fame or
  fortune), or a number typed into the one option ``NUMBER`` (the answer arrives in ``Choose.name``, like a card name, 201.4: card_names.answer).
  A number is a whole number ≥ ``min``; up to 9 digits are read (a bigger one is far more life than any game has).
* Secret choices ("secretly chooses … then the choices are revealed"): the decision goes to the chooser alone (rules/view.decision_view shows
  everyone else "is making a choice"), nothing is logged and no public state changes until every choice is in; then all are revealed at
  once in the log. A player who left the game (800.4a) chooses nothing and is not counted.
* Bids (``bid``, "bid life": Mages' Contest, Illicit Auction, Pain's Reward): the controller starts with a bid (a number, or any number: typed), then in turn order
  each other player may top the high bid (a whole number above it) or pass; a raise lets every other player top the new bid again, and the bidding ends when
  every player but the high bidder has declined to top the bid that stands. Bids are public and may be more than a player's life (the rulings: it is life loss,
  not a payment). The high bidder's players binding is ``<name>:winner`` and the bid ``<name>_high``.
* "of a type / color chosen this way": the later instructions' ``chosen_type`` / ``chosen_color`` selectors are bound to every type or color
  chosen (any of them; "aren't of": none of them). Choosing a value already chosen is allowed and changes nothing (Patriarch's Bidding ruling).
* "For each player who chose X, …" (``gc_each``): the next ``skip`` instructions once for each such player in APNAP order, "that player" being
  ``@P`` in the instructions (becomes ``player:<id>``). "the highest / lowest number" (``gc_extremes``): binds the players who chose the
  highest (``<name>:hi``), the lowest (``lo``) and not the lowest (``nlo``) number and their amounts (``<name>_hi``, ``<name>_lo``).
* An auction (``gc_auction``: Thieves' Auction): starting with the controller, in turn order, each player chooses one of the cards exiled by the earlier
  instruction and puts it onto the battlefield tapped under their control, round after round until all are chosen. The choices are public; a card that can't legally
  enter (an Aura with nothing to enchant) can't be picked, stays exiled and may be picked by a later player; the process ends when a whole round picks nothing.
* A secret choice a permanent keeps (``gc_secret``: "When this creature enters, secretly choose an opponent." Stalking Leonin; "Then secretly choose Human, Merfolk, or Goblin."
  A Killer Among Us): a private decision of its controller, stored by rules object in ``RulesState.secret_choices`` as [chooser, value] and never shown (nothing is logged, the
  views have no such field) until the cost "Reveal the player / creature type you chose" is paid (costs.REVEAL_SECRET: it needs the choice of the player activating, so a creature you
  took, or became a copy of it, can't pay it; a permanent that left and returned is a new object with none, 400.7). The ability's effect then asks ``secret`` conditions
  ("if it's controlled by the chosen player", "if target attacking creature token is the chosen type").
* A guessed secret number (``gc_guess``: The Toymaker's Trap): the controller secretly chooses a number from a list minus the numbers this object has
  chosen before (``RulesState.chosen_numbers``, by rules object: a new object, or a second copy, has no memory: ruling 2023-10-13), "an opponent" (chosen as
  the ability resolves, 608.2d) guesses in public, then the number is revealed and recorded. The guess is right or wrong; the wrong and right instructions are
  put in place as it resolves. The ability counts for The Celestial Toymaker (``pile_groups.note_grouping``).
"""

from __future__ import annotations

import copy
import json
import re
from typing import TYPE_CHECKING, Any

from app.game.errors import ActionError
from app.game.rules_state import DecisionOption
from app.game.state import zone_key

if TYPE_CHECKING:
    from app.game.rules_state import Decision
    from app.rules.plan import Plan

Context = dict[str, Any]
NUMBER = "__number__"  # the one option of a typed-number decision (its ``group`` says "number")
MAX_DIGITS = 9


# -- typed numbers ---------------------------------------------------------------------------------------------
def is_number(d: Decision) -> bool:
    return bool(d.options) and d.options[0].id == NUMBER


def number_answer(d: Decision, typed: str | None) -> str:
    """The whole number the player typed (≥ the decision's minimum), or an ActionError saying what is wrong."""
    text = (typed or "").strip()
    if text.lower() == "pass" and any(o.id == "pass" for o in d.options):  # a bid may be declined
        return "pass"
    if not re.fullmatch(rf"\d{{1,{MAX_DIGITS}}}", text):
        raise ActionError(f"Type a whole number of 0 to {'9' * MAX_DIGITS}")
    least = int(d.options[0].label.rsplit("≥", 1)[-1]) if "≥" in d.options[0].label else 0
    if int(text) < least:
        raise ActionError(f"Type a number of {least} or more")
    return str(int(text))


# -- the choice ------------------------------------------------------------------------------------------------
def _options(plan: Plan, ctx: Context, e: dict[str, Any], pid: str = "", k: int = 0) -> list[DecisionOption]:
    if e["what"] == "object":  # a permanent the chooser controls (``mine``) or doesn't, that the selector names (Call to the Void)
        from app.rules import selectors

        kind = e["kinds"][k]
        found = selectors.candidates(plan, selectors.from_key(kind["sel"]), pid, ctx.get("source_card"))
        if kind.get("of"):  # -- wave 110F -- "a creature that player controls": only the permanents those players control (Malik)
            from app.rules.effects import _players

            owners = _players(plan, ctx, kind["of"])
            return [DecisionOption(id=c, label=plan.state.cards[c].name or "Permanent", card_id=c)
                    for c in found if plan.state.cards[c].zone.endswith(":battlefield") and plan.state.cards[c].controller in owners]
        return [DecisionOption(id=c, label=(plan.state.cards[c].name or "Permanent") + ("" if kind["mine"] else f" — {plan.name(plan.state.cards[c].controller)}"), card_id=c)
                for c in found if plan.state.cards[c].zone.endswith(":battlefield") and (plan.state.cards[c].controller == pid) == kind["mine"]]
    if e["what"] == "hand":  # a card in the chooser's hand: only they see it (101.4a)
        return [DecisionOption(id=c, label=plan.state.cards[c].name or "Card", card_id=c) for c in plan.state.zones.get(zone_key(pid, "hand"), [])]
    if e["what"] == "word":
        gone = {str(n) for n in plan.rules.chosen_numbers.get(_memory(ctx), [])} if e.get("memory") else set()  # (-- guessed numbers (wave 53D) --)
        return [DecisionOption(id=w.lower(), label=w) for w in e["opts"] if w not in gone]
    if e["what"] == "number":
        return [DecisionOption(id=NUMBER, label=f"Type a number ≥ {int(e.get('min', 0))}", group="number")]
    from app.rules.effects import _choice_options

    return _choice_options(plan, ctx, e["what"])


def _label(e: dict[str, Any], value: str, plan: Plan | None = None) -> str:
    if e["what"] in ("object", "hand") and plan is not None:
        return plan.state.cards[value].name or "a permanent" if value in plan.state.cards else "a permanent"
    return next((w for w in e.get("opts") or [] if w.lower() == value), value)


def choose(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """Start: who chooses, in which order (101.4), then the first question."""
    from app.rules.effects import _players

    who: list[str] = []
    for w in e["who"] if isinstance(e["who"], list) else [e["who"]]:
        who += [p for p in _players(plan, ctx, w) if p not in who]
    order = [p for p in plan.apnap() if p in who]
    if e.get("start") and order:  # 101.4: "starting with you" / "with the next opponent in turn order", then turn order
        first = ctx["controller"] if e["start"] == "you" else plan.after(ctx["controller"])
        at = order.index(first) if first in order else 0
        order = order[at:] + order[:at]
    # a turn is a player and the kind of thing they choose (one choice for each kind, in the order written: 101.4c)
    kinds = e.get("kinds") or [None]
    # (-- wave 110F -- a kind with ``by`` is chosen only by those players: Malik, Grim Manipulator, "you and target opponent each secretly choose a creature that player controls")
    turns = [[p, k] for p in order for k in range(len(kinds)) if not (kinds[k] or {}).get("by") or p in _players(plan, ctx, kinds[k]["by"])]
    ctx.setdefault("gc", {})[e["as"]] = {"order": order, "turns": turns, "i": 0, "ballots": [], "secret": bool(e.get("secret"))}
    return _ask(plan, ctx, e)


def _ask(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    from app.rules.plan import decide

    g = ctx["gc"][e["as"]]
    while g["i"] < len(g["turns"]):
        pid, k = g["turns"][g["i"]]
        options = _options(plan, ctx, e, pid, k) if pid in plan.live() else []
        if not options:  # (800.4a: a player who left the game chooses nothing; nothing of that kind to choose)
            g["i"] += 1
            continue
        if e["what"] in ("object", "hand") and len(options) == 1:  # the only one there is: no choice to make (nothing is told by it: the table, or the one card of a hand)
            g["ballots"].append([pid, options[0].id])
            g["i"] += 1
            continue
        known = "" if g["secret"] or not g["ballots"] else " — chosen: " + ", ".join(f"{plan.name(p)} {_label(e, v)}" for p, v in g["ballots"])
        label = e["kinds"][k]["say"] if e["what"] == "object" else e.get("say") or e["what"]
        decide(plan, player=pid, kind="choose_cards" if e["what"] in ("object", "hand") else "choose_one",
               prompt=f"{ctx.get('name') or 'Choose'}: choose {label}{' (secret)' if g['secret'] else ''}{known}",
               options=options, resume={"step": "gc_choose", "ctx": ctx, "e": e, "rest": [], "picked": []})  # (rest, picked: engine._settle_decision)
        return False
    return _finish(plan, ctx, e)


def resume(plan: Plan, d: Decision, chosen: list[str]) -> None:
    from app.rules.effects import continue_effects

    ctx, e = d.resume["ctx"], d.resume["e"]  # type: ignore[index]
    g = ctx["gc"][e["as"]]
    pid = g["turns"][g["i"]][0]
    g["i"] += 1
    if chosen:  # (none: the chooser left the game, 800.4)
        g["ballots"].append([pid, chosen[0]])
        if not g["secret"]:
            plan.note(f"{plan.name(pid)} chooses {_label(e, chosen[0], plan)}" if e["what"] != "hand" else f"{plan.name(pid)} chooses a card in their hand",
                      [chosen[0]] if e["what"] == "object" else [], actor=pid)  # 101.4b (101.4a: a card of a hand stays face down until it is revealed)
    if _ask(plan, ctx, e):
        continue_effects(plan, ctx)


def _finish(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """Everyone has chosen: reveal a secret choice, bind each value's players, bind the later instructions' "chosen this way"."""
    from app.rules import context

    g = ctx["gc"][e["as"]]
    g["ballots"] = [b for b in g["ballots"] if b[0] in plan.live()]
    if g["secret"] and g["ballots"] and not e.get("quiet"):  # (quiet: revealed by a later instruction, gc_guess)
        plan.note("The choices are revealed: " + "; ".join(f"{plan.name(p)} chose {_label(e, v, plan)}" for p, v in g["ballots"]),
                  [v for _, v in g["ballots"]] if e["what"] in ("object", "hand") else [])
    if e["what"] == "hand":  # "Then each player reveals their chosen card": all at once (701.20a: public until the instructions are done)
        ids = [v for _, v in g["ballots"] if v in plan.state.cards and plan.state.cards[v].zone.endswith(":hand")]
        for p, v in g["ballots"]:
            if v in ids:
                plan.do({"type": "reveal", "card_ids": [v]}, actor=p)
        ctx["revealed"] = ids
        if not ctx.get("hide_queued"):  # (appended in place: the resolver walks the same list)
            ctx["hide_queued"] = True
            ctx["effects"].append({"do": "hide_revealed"})
        return True
    if e["what"] == "object":  # "Destroy each creature chosen this way": the objects chosen (one chosen twice is one object)
        context.bind_objects(plan, ctx, f"{e['as']}:chosen", list(dict.fromkeys(v for _, v in g["ballots"])))
        return True
    for value in dict.fromkeys(v for _, v in g["ballots"]):
        context.bind_players(ctx, f"{e['as']}:{value}", [p for p, v in g["ballots"] if v == value])
    if e.get("bind"):  # "of a type chosen this way": any of the types chosen
        at = ctx["next"]
        ctx["effects"][at:] = bind_values(ctx["effects"][at:], e["what"], list(dict.fromkeys(v for _, v in g["ballots"])))
    return True


def bind_values(effects: list[dict[str, Any]], what: str, values: list[str]) -> list[dict[str, Any]]:
    """The instructions with "of the chosen <what>" read as "of one of the ``values``" ("that aren't of the chosen <what>": of none of them)."""
    from dataclasses import replace

    from app.rules import selectors

    def one(sel: selectors.Selector) -> selectors.Selector | None:
        rest = tuple(x for x in sel.extras if x not in selectors.CHOSEN_EXTRAS)
        neg = any(x.startswith("not_") for x in sel.extras if x in selectors.CHOSEN_EXTRAS)
        if what == "creature type":
            if sel.subtypes or sel.not_subtypes or sel.union:
                return None
            return replace(sel, extras=rest, not_subtypes=tuple(values)) if neg else replace(sel, extras=rest, subtypes=tuple(values) or ("",))
        if what == "color":
            if sel.colors or sel.not_colors:
                return None
            codes = tuple(selectors.COLORS[v.lower()] for v in values)
            return replace(sel, extras=rest, not_colors=codes) if neg else replace(sel, extras=rest, colors=codes or ("",))
        return None

    def walk(node: Any) -> Any:
        if isinstance(node, dict):
            return {k: walk(v) for k, v in node.items()}
        if isinstance(node, list):
            return [walk(v) for v in node]
        if isinstance(node, str) and node.startswith(selectors.PREFIX) and "chosen_" in node:
            sel = selectors.from_key(node)
            if selectors.chosen_what(sel) == what and (bound := one(sel)) is not None:
                return bound.key()
        return node

    return [walk(x) for x in effects]


# -- using the choices ------------------------------------------------------------------------------------------
def each(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """The next ``skip`` instructions once for each player who chose ``value``, in APNAP order, with "@P" in them that player."""
    effects, at, n = ctx["effects"], ctx["next"], int(e["skip"])
    block = effects[at:at + n]
    g = ctx["gc"][e["as"]]
    out: list[dict[str, Any]] = []
    for p in g["order"]:
        if [p, e["value"]] in g["ballots"] and p in plan.live():
            out += json.loads(json.dumps(copy.deepcopy(block)).replace("@P", f"player:{p}"))
    effects[at:at + n] = out
    return True


def extremes(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """"the highest and lowest numbers revealed this way": the players who chose each, and the numbers."""
    from app.rules import context

    name = e["as"]
    ballots = [(p, int(v)) for p, v in ctx["gc"][name]["ballots"]]
    hi, lo = max((n for _, n in ballots), default=0), min((n for _, n in ballots), default=0)
    context.bind_players(ctx, f"{name}:hi", [p for p, n in ballots if n == hi])
    context.bind_players(ctx, f"{name}:lo", [p for p, n in ballots if n == lo])
    context.bind_players(ctx, f"{name}:nlo", [p for p, n in ballots if n != lo])
    context.bind_amount(ctx, f"{name}_hi", hi)
    context.bind_amount(ctx, f"{name}_lo", lo)
    return True


def holds(plan: Plan, ctx: Context, cond: dict[str, Any]) -> bool:
    """Conditions on a group choice: ``{"gc": {"as": name, "is": "all" | "mixed" | "you", …}}``."""
    c = cond["gc"]
    ballots = (ctx.get("gc") or {}).get(c["as"], {}).get("ballots") or []
    values = {v for _, v in ballots}
    if c["is"] == "any":  # "If you do": somebody chose
        return bool(ballots)
    if c["is"] == "match":  # "If they match"
        return len(ballots) >= 2 and len(values) == 1
    if c["is"] == "differ":  # (otherwise)
        return len(values) >= 2
    if c["is"] == "all":  # "if each opponent chose silence"
        return bool(ballots) and values == {c["value"]}
    if c["is"] == "mixed":  # neither of the "each opponent chose …" cases
        return bool(ballots) and not (len(values) == 1 and values <= set(c["values"]))
    if c["is"] == "you":  # "If you are one of those players": the controller is among the players bound as ``name:set``
        from app.rules import context

        return ctx["controller"] in context.players(plan, ctx, f"{c['as']}:{c['set']}")
    return False


# -- bids ---------------------------------------------------------------------------------------------------------
def _target_controller(plan: Plan, ctx: Context) -> str | None:
    """The controller of the spell the ability targets (it is on the stack: 109.4)."""
    for t in (ctx.get("targets") or []):
        card = plan.state.cards.get(t["id"])
        if card is not None and plan.oid(card) == t.get("object_id"):
            return str(card.controller)
    return None


def bid(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """Start: who bids, the controller's opening bid (a number, or any number they type)."""
    me = ctx["controller"]
    who = [p for p in plan.live()] if e["who"] == "each_player" else [me, _target_controller(plan, ctx)]
    turn = [me]
    while (nxt := plan.after(turn[-1])) != me and len(turn) < 64:
        turn.append(nxt)
    order = [p for p in turn if p in who]
    ctx.setdefault("bid", {})[e["as"]] = {"order": order, "high": 0, "bidder": me, "at": 1 % max(len(order), 1), "passes": 0}
    if e["start"] == "any":
        from app.rules.plan import decide

        decide(plan, player=me, kind="choose_one", prompt=f"{ctx.get('name') or 'Bid'}: start the bidding with a bid of any number",
               options=[DecisionOption(id=NUMBER, label="Type a number ≥ 0", group="number")],
               resume={"step": "gc_bid", "ctx": ctx, "e": e, "open": True, "rest": [], "picked": []})
        return False
    b = ctx["bid"][e["as"]]
    b["high"] = int(e["start"])
    plan.note(f"{plan.name(me)} starts the bidding with a bid of {b['high']}", actor=me)
    return _ask_bid(plan, ctx, e)


def _ask_bid(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    from app.rules import context
    from app.rules.plan import decide

    b = ctx["bid"][e["as"]]
    order = b["order"]
    while b["passes"] < len(order) - 1:
        pid = order[b["at"] % len(order)]
        if pid not in plan.live():  # (a player who left the game, 800.4a, bids no more)
            b["at"] = (b["at"] + 1) % len(order)
            b["passes"] += 1
            continue
        decide(plan, player=pid, kind="choose_one",
               prompt=f"{ctx.get('name') or 'Bid'}: the high bid is {b['high']} ({plan.name(b['bidder'])}). Bid more life, or pass",
               options=[DecisionOption(id=NUMBER, label=f"Type a number ≥ {b['high'] + 1}", group="number"), DecisionOption(id="pass", label="Pass")],
               resume={"step": "gc_bid", "ctx": ctx, "e": e, "rest": [], "picked": []})
        return False
    winner = b["bidder"] if b["bidder"] in plan.live() else None
    context.bind_players(ctx, f"{e['as']}:winner", [winner] if winner else [])
    context.bind_amount(ctx, f"{e['as']}_high", b["high"])
    if winner:
        plan.note(f"{plan.name(winner)} wins the bidding with a bid of {b['high']}", actor=winner)
    return True


def resume_bid(plan: Plan, d: Decision, chosen: list[str]) -> None:
    from app.rules.effects import continue_effects

    ctx, e = d.resume["ctx"], d.resume["e"]  # type: ignore[index]
    b = ctx["bid"][e["as"]]
    if (d.resume or {}).get("open"):  # the opening bid
        b["high"] = int(chosen[0]) if chosen else 0
        plan.note(f"{plan.name(d.player)} starts the bidding with a bid of {b['high']}", actor=d.player)
    elif chosen and chosen[0] != "pass":
        b.update(high=int(chosen[0]), bidder=d.player, passes=0, at=(b["at"] + 1) % len(b["order"]))
        plan.note(f"{plan.name(d.player)} bids {b['high']}", actor=d.player)
    else:
        b["passes"] += 1
        b["at"] = (b["at"] + 1) % len(b["order"])
        plan.note(f"{plan.name(d.player)} passes", actor=d.player)
    if _ask_bid(plan, ctx, e):
        continue_effects(plan, ctx)


def sweep(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """"Exile each permanent unless it's colorless or it's only the color its controller chose." (Selective Obliteration): a permanent stays if it has no color or
    exactly one, the color its controller chose (105.2); a multicolored one always goes (ruling), and a controller's choice counts for their own permanents only."""
    from app.rules import selectors
    from app.rules.effects import exile_cards

    chosen = {p: v for p, v in ctx["gc"][e["as"]]["ballots"]}
    gone = []
    for cid in [c for z, ids in plan.state.zones.items() if z.endswith(":battlefield") for c in ids]:
        card = plan.state.cards[cid]
        colors = plan.ch(card).colors
        mine = chosen.get(card.controller)
        if colors and not (len(colors) == 1 and mine is not None and selectors.COLORS[mine.lower()] in colors):
            gone.append(cid)
    exile_cards(plan, ctx, {}, gone)
    return True


# -- cards in a hand or a graveyard, chosen by each player -----------------------------------------------------------------
# One question for each player in APNAP order (101.4), who sees only their own cards (a hand is hidden: 101.4a, the choices stay face down, only how many is
# said); what they chose is acted on for everyone at once after the last.
def keep_hand(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """"Each player chooses up to seven cards in their hand, then shuffles the rest into their library." (Worldpurge): the rest of each hand is shuffled in."""
    ctx["keep"] = {"order": [p for p in plan.apnap() if p in plan.live()], "i": 0, "kept": {}}
    return _ask_keep(plan, ctx, e)


def _ask_keep(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    from app.rules.plan import decide

    k = ctx["keep"]
    while k["i"] < len(k["order"]):
        pid = k["order"][k["i"]]
        hand = plan.state.zones.get(zone_key(pid, "hand"), [])
        if not hand or pid not in plan.live():
            k["i"] += 1
            continue
        n = min(int(e["n"]), len(hand))
        decide(plan, player=pid, kind="choose_cards", prompt=f"{ctx.get('name') or 'Choose'}: choose up to {e['n']} cards in your hand; the rest are shuffled into your library",
               options=[DecisionOption(id=c, label=plan.state.cards[c].name or "Card", card_id=c) for c in hand], min_choices=0, max_choices=n,
               resume={"step": "gc_keep", "ctx": ctx, "e": e, "rest": [], "picked": []})
        return False
    for pid in k["order"]:
        rest = [c for c in plan.state.zones.get(zone_key(pid, "hand"), []) if c not in k["kept"].get(pid, [])]
        if rest and pid in plan.live():
            plan.do({"type": "move", "card_ids": rest, "to": {"player": pid, "zone": "library"}}, actor=pid)
            plan.do({"type": "shuffle", "player": pid, "zone": "library"}, actor=pid)
            plan.note(f"{plan.name(pid)} shuffles {len(rest)} card{'s' if len(rest) != 1 else ''} from their hand into their library", actor=pid)
    del ctx["keep"]
    return True


def resume_keep(plan: Plan, d: Decision, chosen: list[str]) -> None:
    from app.rules.effects import continue_effects

    ctx, e = d.resume["ctx"], d.resume["e"]  # type: ignore[index]
    k = ctx["keep"]
    k["kept"][k["order"][k["i"]]] = list(chosen)
    plan.note(f"{plan.name(d.player)} chooses {len(chosen)} card{'s' if len(chosen) != 1 else ''} in their hand", actor=d.player)  # 101.4a: how many, not which
    k["i"] += 1
    if _ask_keep(plan, ctx, e):
        continue_effects(plan, ctx)


def typed_return(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """"Each player chooses a creature type and returns any number of cards of that type from their graveyard to their hand." (Grave Sifter): the type each chose
    (``gc_choose``) is theirs alone; each, in APNAP order, picks the cards of that type in their own graveyard (public, 404.2), then all go to hand at once."""
    g = ctx["gc"][e["as"]]
    ctx["ret"] = {"order": [p for p in plan.apnap() if any(b[0] == p for b in g["ballots"])], "i": 0, "picked": []}
    return _ask_return(plan, ctx, e)


def _ask_return(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    from app.rules import characteristics as chars
    from app.rules.effects import _return_cards
    from app.rules.plan import decide

    r = ctx["ret"]
    ballots = dict(ctx["gc"][e["as"]]["ballots"])
    while r["i"] < len(r["order"]):
        pid = r["order"][r["i"]]
        mine = [c for c in plan.state.zones.get(zone_key(pid, "graveyard"), []) if ballots[pid] in chars.of(plan.state.cards[c], plan.info).subtypes]
        if not mine or pid not in plan.live():
            r["i"] += 1
            continue
        decide(plan, player=pid, kind="choose_cards", prompt=f"{ctx.get('name') or 'Choose'}: return any number of {ballots[pid]} cards from your graveyard to your hand",
               options=[DecisionOption(id=c, label=plan.state.cards[c].name or "Card", card_id=c) for c in mine], min_choices=0, max_choices=len(mine),
               resume={"step": "gc_return", "ctx": ctx, "e": e, "rest": [], "picked": []})
        return False
    picked = [c for c in r["picked"] if c in plan.state.cards]
    del ctx["ret"]
    if picked:
        _return_cards(plan, ctx, {"to": "hand"}, picked)
    return True


def resume_return(plan: Plan, d: Decision, chosen: list[str]) -> None:
    from app.rules.effects import continue_effects

    ctx, e = d.resume["ctx"], d.resume["e"]  # type: ignore[index]
    r = ctx["ret"]
    r["picked"] += list(chosen)
    if chosen:
        plan.note(f"{plan.name(d.player)} chooses {', '.join(plan.state.cards[c].name or 'a card' for c in chosen)}", list(chosen), actor=d.player)
    r["i"] += 1
    if _ask_return(plan, ctx, e):
        continue_effects(plan, ctx)


def reveal_names(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """"Each player reveals the top card of their library. If the card a player revealed has the name they chose, that player puts it into their hand. If it doesn't,
    that player puts it on the bottom of their library." (Conundrum Sphinx): all reveal at once (public, 701.20a), then each puts theirs where it goes."""
    from app.rules import card_names

    chosen = dict(ctx["gc"][e["as"]]["ballots"])
    tops = {p: plan.state.zones.get(zone_key(p, "library"), [])[:1] for p in plan.apnap() if p in chosen and p in plan.live()}
    for p, top in tops.items():
        if top:
            plan.do({"type": "reveal_top", "player": p, "count": 1}, actor=p)
    for p, top in tops.items():
        if not top:
            continue
        hit = card_names.has_name(plan.ch(plan.state.cards[top[0]]), chosen[p])
        plan.note(f"{plan.name(p)} revealed {plan.state.cards[top[0]].name}: " + ("the name they chose, into their hand" if hit else "not the name they chose, to the bottom of their library"),
                  top, actor=p)
        if hit:
            plan.do({"type": "move", "card_ids": top, "to": {"player": p, "zone": "hand"}}, actor=p)
        else:
            plan.do({"type": "move", "card_ids": top, "to": {"player": p, "zone": "library"}, "position": "bottom"}, actor=p)
    return True


def lowest_creature(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """"The owner of each creature card revealed this way with the lowest mana value puts it onto the battlefield." (Stronghold Gambit): among the creature cards
    chosen, those with the lowest mana value (X is 0 in a hand, 202.3e) enter under their owners' control, all at once; the others stay in hand (ruling)."""
    from app.rules.effects import _return_cards
    from app.rules.stack_interaction import mana_value

    cards = [v for _, v in ctx["gc"][e["as"]]["ballots"] if v in plan.state.cards and plan.state.cards[v].zone.endswith(":hand")]
    creatures = [c for c in cards if "Creature" in plan.ch(plan.state.cards[c]).types]
    values = {c: mana_value(plan.state.cards[c], plan.ch(plan.state.cards[c])) for c in creatures}
    low = min(values.values(), default=0)
    entering = [c for c in creatures if values[c] == low]
    if entering:
        _return_cards(plan, ctx, {"to": "battlefield", "under": "owner"}, entering)
    return True


def succession(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """"Starting with you and proceeding in the chosen direction, each player chooses a creature controlled by the next player in that direction. Each player gains
    control of the creature they chose." (Order of Succession): left is the next player in turn order, right the previous (101.4, 808.4); the choices are public and
    made one after the other, the control changes all together."""
    me = ctx["controller"]
    right = (ctx["gc"][e["as"]]["ballots"] or [[me, "left"]])[0][1] == "right"
    live = plan.live()
    order = [me]
    while len(order) < len(live):
        nxt = _neighbor(plan, order[-1], right)
        if nxt in order:
            break
        order.append(nxt)
    ctx["succ"] = {"order": order, "right": right, "i": 0, "pairs": []}
    return _ask_succession(plan, ctx, e)


def _neighbor(plan: Plan, pid: str, right: bool) -> str:
    seats = [p for p in plan.state.seat_order if p in plan.live()]
    return seats[(seats.index(pid) + (-1 if right else 1)) % len(seats)]


def _ask_succession(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    from app.rules import selectors
    from app.rules.effects import _control_effect, layers
    from app.rules.plan import decide

    s = ctx["succ"]
    creature = selectors.parse("creature")
    assert creature is not None
    while s["i"] < len(s["order"]):
        pid = s["order"][s["i"]]
        target = _neighbor(plan, pid, s["right"])
        mine = [c for c in selectors.candidates(plan, creature, pid, ctx.get("source_card")) if plan.state.cards[c].controller == target
                and plan.state.cards[c].zone.endswith(":battlefield")]
        if pid not in plan.live() or not mine or target == pid:
            s["i"] += 1
            continue
        if len(mine) == 1:
            s["pairs"].append([pid, mine[0]])
            plan.note(f"{plan.name(pid)} chooses {plan.state.cards[mine[0]].name} (no choice: the only one)", mine, actor=pid)
            s["i"] += 1
            continue
        known = " — chosen: " + ", ".join(f"{plan.name(p)} {plan.state.cards[c].name}" for p, c in s["pairs"]) if s["pairs"] else ""
        decide(plan, player=pid, kind="choose_cards", prompt=f"{ctx.get('name') or 'Choose'}: choose a creature controlled by {plan.name(target)}{known}",
               options=[DecisionOption(id=c, label=plan.state.cards[c].name or "Creature", card_id=c) for c in mine],
               resume={"step": "gc_succession", "ctx": ctx, "e": e, "rest": [], "picked": []})
        return False
    pairs = [(p, c) for p, c in s["pairs"] if c in plan.state.cards and plan.state.cards[c].zone.endswith(":battlefield") and p in plan.live()]
    del ctx["succ"]
    for p, c in pairs:
        _control_effect(plan, ctx, [c], p, "permanent")
    if pairs:
        layers.control_sync(plan)
    return True


def resume_succession(plan: Plan, d: Decision, chosen: list[str]) -> None:
    from app.rules.effects import continue_effects

    ctx, e = d.resume["ctx"], d.resume["e"]  # type: ignore[index]
    s = ctx["succ"]
    pid = s["order"][s["i"]]
    if chosen:
        s["pairs"].append([pid, chosen[0]])
        plan.note(f"{plan.name(pid)} chooses {plan.state.cards[chosen[0]].name}", [chosen[0]], actor=pid)
    s["i"] += 1
    if _ask_succession(plan, ctx, e):
        continue_effects(plan, ctx)


def lose_mana(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """"Each player loses all unspent mana." (Worldpurge): every pool is emptied (106.4); a player with "If you would lose unspent mana, that mana becomes colorless
    instead" keeps it as colorless mana (614.1a, kept_mana)."""
    from app.rules import (
        kept_mana,
        wave110j_cards,  # -- Yurlok (wave 110J) --
    )

    lost = wave110j_cards.pools(plan)
    colorless = kept_mana._colorless(plan)
    from app.rules import effects
    players=effects._players(plan,ctx,e['who']) if e.get('who') else list(plan.state.players)
    for pid in players:
        player=plan.state.players[pid]
        if pid in colorless:
            kept_mana._to_colorless(plan, pid, {}, [])
        elif any(player.mana.values()) or player.mana_units:
            plan.do({'type':'clear_mana','player':pid},actor=plan.active)
    kept_mana.clamp(plan.state)
    wave110j_cards.mana_lost(plan, {pid: n for pid, n in lost.items() if pid in players})
    return True


# -- secret choices a permanent keeps (wave 53D) --
def secret(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """"Secretly choose an opponent" / "secretly choose Human, Merfolk, or Goblin": its controller's private choice (a single opponent is the choice already)."""
    from app.rules.plan import decide

    me = ctx["controller"]
    if e["what"] == "opponent":
        values = [p for p in plan.live() if p != me]
        options = [DecisionOption(id=p, label=plan.name(p)) for p in values]
    else:
        values = [w for w in e["opts"]]
        options = [DecisionOption(id=w, label=w) for w in values]
    if not values or me not in plan.live():
        return True
    if len(values) == 1:
        _keep_secret(plan, ctx, me, values[0])
        return True
    decide(plan, player=me, kind="choose_one", prompt=f"{ctx.get('name') or 'Choose'}: secretly choose {'an opponent' if e['what'] == 'opponent' else ', '.join(values)}",
           options=options, resume={"step": "gc_secret", "ctx": ctx, "e": e, "rest": [], "picked": []})
    return False


def _keep_secret(plan: Plan, ctx: Context, pid: str, value: str) -> None:
    plan.rules.secret_choices = {k: v for k, v in plan.rules.secret_choices.items() if k.rsplit(".", 1)[0] in plan.state.cards and plan.oid(k.rsplit(".", 1)[0]) == k}
    plan.rules.secret_choices[str(ctx.get("source_object") or "")] = [pid, value]


def resume_secret(plan: Plan, d: Decision, chosen: list[str]) -> None:
    from app.rules.effects import continue_effects

    if chosen:  # (none: the chooser left the game, 800.4)
        _keep_secret(plan, d.resume["ctx"], d.player, chosen[0])  # type: ignore[index]
    continue_effects(plan, d.resume["ctx"])  # type: ignore[index]


def secret_holds(plan: Plan, ctx: Context, cond: dict[str, Any]) -> bool:
    """``{"secret": {"is": "controller" | "type"}}``: the first target (a permanent) is controlled by the player the source's controller secretly chose / has the
    creature type they chose. Without a choice (or by a player who isn't the controller now) nothing matches."""
    c = cond["secret"]
    entry = plan.rules.secret_choices.get(str(ctx.get("source_object") or ""))
    target = next((plan.state.cards[t["id"]] for t in (ctx.get("targets") or []) if t["id"] in plan.state.cards), None)
    if not entry or target is None or entry[0] != ctx["controller"]:
        return False
    return str(target.controller) == entry[1] if c["is"] == "controller" else entry[1] in plan.ch(target).subtypes


# -- auctions (wave 53D) --
def auction(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """"Starting with you, each player chooses one of the exiled cards and puts it onto the battlefield tapped under their control. Repeat this process until all cards
    exiled this way have been chosen." (Thieves' Auction): ``from`` is the binding of the cards exiled."""
    me = ctx["controller"]
    turn = [me]
    while (nxt := plan.after(turn[-1])) != me and len(turn) < 64:
        turn.append(nxt)
    ctx.setdefault("auction", {}).setdefault(e["as"], {"order": [p for p in turn if p in plan.live()], "at": 0, "idle": 0})  # (re-entered after an Aura's host is chosen)
    return _auction_turn(plan, ctx, e)


def _auction_turn(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    from app.rules import attachments, context
    from app.rules.plan import decide

    st = ctx["auction"][e["as"]]
    while st["order"] and st["idle"] < len(st["order"]):
        pid = st["order"][st["at"] % len(st["order"])]
        left = context.objects(plan, ctx, e["from"][len(context.PREFIX):])
        if not left:
            break
        options = [DecisionOption(id=c, label=plan.state.cards[c].name or "Card", card_id=c) for c in left
                   if pid in plan.live() and (attachments.attach_kind(plan.ch(plan.state.cards[c])) != "aura" or attachments.legal_hosts(plan, plan.state.cards[c], pid))]
        if not options:  # (nothing this player could legally put onto the battlefield, or they left the game, 800.4a)
            st["idle"] += 1
            st["at"] += 1
            continue
        decide(plan, player=pid, kind="choose_cards", prompt=f"{ctx.get('name') or 'Auction'}: choose one of the exiled cards to put onto the battlefield tapped under your control",
               options=options, min_choices=1, max_choices=1, resume={"step": "gc_auction", "ctx": ctx, "e": e, "rest": [], "picked": []})
        return False
    del ctx["auction"][e["as"]]
    return True


def resume_auction(plan: Plan, d: Decision, chosen: list[str]) -> None:
    from app.rules import attachments
    from app.rules.effects import continue_effects

    ctx, e = d.resume["ctx"], d.resume["e"]  # type: ignore[index]
    st = ctx["auction"][e["as"]]
    st["at"] += 1
    st["idle"] = 0
    card = plan.state.cards.get(chosen[0]) if chosen else None
    if card is not None:
        plan.note(f"{plan.name(d.player)} chooses {card.name}", [card.id], actor=d.player)
        if not attachments.enter(plan, [{"card": card.id, "player": d.player, "actor": d.player, "tapped": True}], ctx):
            ctx["next"] -= 1  # (an Aura asks what it enchants: the auction goes on when it has entered)
            return
    if _auction_turn(plan, ctx, e):
        continue_effects(plan, ctx)


# -- guessed secret numbers (wave 53D) --
def _memory(ctx: Context) -> str:
    """Whose numbers are remembered: the rules object of the ability's source (400.7: a permanent that left and came back is another object)."""
    return str(ctx.get("source_object") or ctx.get("source_card") or "")


def guess(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """"An opponent guesses which number you chose, then you reveal the number you chose. If they guessed wrong, … If they guessed right, …" (The Toymaker's Trap):
    the chosen number is revealed (and remembered), the guess is compared with it, and the matching instructions follow. The guess is bound as ``<guess>_n``."""
    from app.rules import context, pile_groups

    secret, guessed = ctx["gc"][e["bind"]]["ballots"], ctx["gc"][e["as"]]["ballots"]  # (``bind``: the secret choice, ``as``: the guess; both names are renamed with a clause's)
    if not secret:
        return True
    pid, number = secret[0]
    pile_groups.note_grouping(plan, ctx)  # (the Celestial Toymaker counts spells and abilities that made players guess)
    plan.rules.chosen_numbers.setdefault(_memory(ctx), []).append(int(number))
    plan.note(f"{plan.name(pid)} reveals the number they chose: {number}", actor=pid)
    if not guessed:  # (the guesser left the game, 800.4a: nobody guessed)
        return True
    context.bind_amount(ctx, f"{e['as']}_n", int(guessed[0][1]))
    at = ctx["next"]
    ctx["effects"][at:at] = e["right"] if guessed[0][1] == number else e["wrong"]
    return True


def exile_linked(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """"Exile the top card of your library face down", linked to the object (607.2a): effects.exile_top, recorded as exiled with the source."""
    from app.rules.effects import exile_top

    return exile_top(plan, ctx, {**e, "link": True})


PRIMITIVES = {"gc_choose": choose, "gc_each": each, "gc_extremes": extremes, "gc_bid": bid, "gc_exile_linked": exile_linked, "gc_sweep": sweep,
              "gc_keep_hand": keep_hand, "gc_typed_return": typed_return, "gc_reveal_names": reveal_names, "gc_lowest_creature": lowest_creature,
              "gc_succession": succession, "gc_lose_mana": lose_mana, "gc_guess": guess, "gc_auction": auction, "gc_secret": secret}
RESUME = {"gc_choose": resume, "gc_bid": resume_bid, "gc_keep": resume_keep, "gc_return": resume_return, "gc_succession": resume_succession, "gc_auction": resume_auction, "gc_secret": resume_secret}


# -- reading the wording ----------------------------------------------------------------------------------------
_GATE = re.compile(r"\b(?:secretly|[Ee]ach (?:player|opponent) chooses|bid life|[Cc]hoose left or right|[Cc]hoose (?:up to )?(?:one|two|three|four|five|six|seven|eight|nine|\d+) .+?, then destroy the rest)\b")
_TYPE_HEAD = re.compile(r"^[Ee]ach player chooses an? (?P<what>creature type|color|basic land type)\. (?P<rest>.+)$", re.DOTALL)
_THIS_WAY = re.compile(r"\bof an? (?P<w>type|color|basic land type) chosen this way\b")
_EACH_RETURNS = re.compile(r"[Ee]ach player returns all (.+?) from their graveyard to the battlefield\.")
_WORDS_HEAD = re.compile(r"^[Ee]ach opponent chooses (?P<a>[a-z]+), (?P<b>[a-z]+), or (?P<c>[a-z]+)\.|^[Ee]ach opponent chooses (?P<a2>[a-z]+) or (?P<b2>[a-z]+)\.")
_FOR_CHOSE = re.compile(r"^For each player who chose (?P<w>[a-z]+), (?P<inst>.+)\.$")
_BOTH_EACH = re.compile(r"^you and that player each (?P<v>create|draw) (?P<rest>.+)$")
_SEIZE_FAME = ("For each player who chose fame, gain control of a creature that player controls until end of turn.",
               "Untap those creatures and they gain haste until end of turn.")
_SECRET_NUMBERS = ("Each player secretly chooses a number", "each player secretly chooses a number")


def bind(body: str, parse: Any, split_sentences: Any) -> tuple[list[dict[str, Any]], Any, bool] | None:
    """The effects of a group-choice body, or None when it isn't one (or isn't read)."""
    if " pile" in body:  # -- piles (wave 53D) -- 700.3 (app/rules/pile_groups.py)
        from app.rules import pile_groups

        return pile_groups.bind(body, parse, split_sentences)
    if ("secretly choose" in body or "chosen player" in body or "is the chosen type" in body) \
            and (found := _secret_ability(body.strip(), parse, split_sentences)) is not None:  # -- secret choices a permanent keeps (wave 53D) --
        return found
    if " exiled with " in body and (found := _linked_graveyard(body.strip(), parse, split_sentences)) is not None:  # -- exiled with (wave 53D) -- 607.2a: "Put a card exiled with it into its owner's graveyard. If you do, investigate." (Foreboding Steamboat)
        return found
    if body.strip().capitalize() == _BOND and (key := _key("permanent")) is not None:
        return [{"do": "edict", "who": "each_opponent", "sel": key, "n": 1, "label": "permanent", "shares_type_with": "event"}], None, False
    if _GATE.search(body) is None:
        return None
    text = body.strip()
    for recipe in (_chosen_type, _words, _numbers, _chosen_objects, _bids, _hands, _guess, _auction):
        if (found := recipe(text, parse, split_sentences)) is not None:
            return found
    return None


def _chosen_type(text: str, parse: Any, split_sentences: Any) -> tuple[list[dict[str, Any]], Any, bool] | None:
    """"Each player chooses a creature type. [instructions] of a type chosen this way": one choice by each player, then the instructions."""
    m = _TYPE_HEAD.match(text)
    if m is None or not _THIS_WAY.search(m["rest"]):
        return None
    rest = _THIS_WAY.sub(lambda t: f"of the chosen {t['w']}", m["rest"])
    rest = _EACH_RETURNS.sub(r"Return all \1 from all graveyards to the battlefield under their owners' control.", rest)  # (each returns their own cards: all of them, 101.4)
    found = parse(rest)
    if found is None or found[1] is not None or found[2] or "chosen_" not in json.dumps(found[0]):
        return None
    return [{"do": "gc_choose", "who": "each_player", "what": m["what"], "as": "gc", "bind": True}, *found[0]], None, False


def _words(text: str, parse: Any, split_sentences: Any) -> tuple[list[dict[str, Any]], Any, bool] | None:
    """"Each opponent chooses A, B, or C. For each player who chose A, [instruction about that player]. …": a public choice among words."""
    sentences = split_sentences(text)
    m = _WORDS_HEAD.match(sentences[0]) if sentences else None
    if m is None or len(sentences) < 2:
        return None
    words = [w for w in (m["a"], m["b"], m["c"]) if w] or [m["a2"], m["b2"]]
    say = " or ".join(words) if len(words) == 2 else ", ".join(words[:-1]) + ", or " + words[-1]
    effects: list[dict[str, Any]] = [{"do": "gc_choose", "who": "each_opponent", "what": "word", "opts": words, "as": "gc", "say": say}]
    seen: set[str] = set()
    rest = sentences[1:]
    while rest:
        f = _FOR_CHOSE.match(rest[0])
        if f is None or f["w"] not in words or f["w"] in seen:
            return None
        seen.add(f["w"])
        if f["w"] == "fame" and tuple(rest[:2]) == _SEIZE_FAME:
            block, rest = _seize_block(), rest[2:]
        else:
            found = _instruction(f["inst"], parse)
            if found is None:
                return None
            block, rest = found, rest[1:]
        effects += [{"do": "gc_each", "as": "gc", "value": f["w"], "skip": len(block)}, *block]
    return effects, None, False


def _instruction(inst: str, parse: Any) -> list[dict[str, Any]] | None:
    """One "for each player who chose …" instruction, "that player" being "@P": "you and that player each create X" / the plain ones."""
    both = _BOTH_EACH.match(inst)
    sentence = f"You {both['v']} {both['rest']}. That player {both['v']}s {both['rest']}." if both else inst[:1].upper() + inst[1:] + "."
    found = parse(sentence)
    if found is None or found[1] is not None or found[2] or not found[0] or any(e.get("bind") or e.get("as") or e.get("did") for e in found[0]):
        return None
    raw = json.dumps(found[0])
    if "target" in raw or '"it"' in raw or "that_player" in raw or "ref:e" in raw:
        return None  # (anything that still names another target or event stays manual)
    return list(json.loads(raw.replace("event_player", "@P")))


def _seize_block() -> list[dict[str, Any]]:
    """Seize the Spotlight: "gain control of a creature that player controls until end of turn" (the controller chooses it, 608.2d: no target),
    "Untap those creatures and they gain haste until end of turn" (done for each as it is gained: the same creatures, the same result)."""
    from dataclasses import replace

    from app.rules import selectors

    base = selectors.parse("creature")
    assert base is not None
    sel = replace(base, controller="@P").key()
    return [{"do": "player_chooses", "who": "you", "sel": sel, "n": 1, "label": "creature", "any": True, "as": "gcx"},
            {"do": "gain_control", "who": "ref:gcx", "duration": "end_of_turn"},
            {"do": "untap", "who": "ref:gcx"},
            {"do": "grant", "who": "ref:gcx", "keywords": ["haste"]}]


def _is(sentences: list[str], expected: tuple[str, ...]) -> bool:
    return tuple(sentences) == expected or (bool(sentences) and tuple([sentences[0][:1].upper() + sentences[0][1:], *sentences[1:]]) == expected)


_WHEEL = ("Each player secretly chooses a number 0 or greater, then all players reveal those numbers simultaneously and determine the highest and lowest "
          "numbers revealed this way.", "~ deals damage equal to the highest number to each player who chose that number.",
          "Each player who didn't choose the lowest number discards their hand, then draws seven cards.")
_OGRE = ("Each player secretly chooses a number.", "Then those numbers are revealed.", "Each player with the highest number loses that much life.",
         "If you are one of those players, put two +1/+1 counters on ~.")
_DILEMMA = ("Each opponent secretly chooses silence or snitch, then the choices are revealed.", "If each opponent chose silence, ~ deals 4 damage to each of them.",
            "If each opponent chose snitch, ~ deals 8 damage to each of them.", "Otherwise, ~ deals 12 damage to each opponent who chose silence.")


def _numbers(text: str, parse: Any, split_sentences: Any) -> tuple[list[dict[str, Any]], Any, bool] | None:
    """Wheel of Misfortune, Menacing Ogre: each player secretly chooses a number (0 or greater), revealed together; the highest / lowest decide."""
    sentences = split_sentences(text)
    pick = {"do": "gc_choose", "who": "each_player", "what": "number", "min": 0, "secret": True, "as": "gc", "say": "a number"}
    hi = {"who": "ref:gc:hi", "n": {"ref_amount": "gc_hi"}}
    if _is(sentences, _WHEEL):  # (the highest number's players take that much; everyone but the lowest's players wheels: the existing "discards their hand, then draws")
        return [pick, {"do": "gc_extremes", "as": "gc"}, {"do": "damage", **hi}, {"do": "discard", "who": "ref:gc:nlo", "n": 0, "all": True},
                {"do": "draw", "who": "ref:gc:nlo", "n": 7}], None, False
    if _is(sentences, _OGRE):
        counters = parse("Put two +1/+1 counters on ~.")
        if counters is None or counters[1] is not None or counters[2]:
            return None
        return [pick, {"do": "gc_extremes", "as": "gc"}, {"do": "lose_life", **hi},
                {"do": "only_if", "cond": {"gc": {"as": "gc", "is": "you", "set": "hi"}}, "skip": len(counters[0])}, *counters[0]], None, False
    if _is(sentences, _DILEMMA):
        pick = {**pick, "who": "each_opponent", "what": "word", "opts": ["silence", "snitch"], "say": "silence or snitch"}
        both = ["silence", "snitch"]
        return [pick, {"do": "only_if", "cond": {"gc": {"as": "gc", "is": "all", "value": "silence"}}, "skip": 1},
                {"do": "damage", "who": "each_opponent", "n": 4},
                {"do": "only_if", "cond": {"gc": {"as": "gc", "is": "all", "value": "snitch"}}, "skip": 1},
                {"do": "damage", "who": "each_opponent", "n": 8},
                {"do": "only_if", "cond": {"gc": {"as": "gc", "is": "mixed", "values": both}}, "skip": 1},
                {"do": "damage", "who": "ref:gc:silence", "n": 12}], None, False
    return None


# -- choosing objects (101.4) ------------------------------------------------------------------------------------
# Each player (opponent) chooses an object, and what was chosen (or what was not) is acted on once all have chosen: the existing ``player_chooses``
# (effects._choose_next: APNAP, each knowing the earlier choices, 101.4b; a player with exactly as many as asked has no choice to make) with the
# instruction after it aimed at the objects chosen (``as``) or at all the others (``except:``).
_ONE_CHOICE = re.compile(r"^[Ee]ach player chooses an? (?P<sel>[a-z ]+?) they control\.$")
_NOT_CHOSEN = re.compile(r"^(?P<verb>Return|Exile|Destroy) all (?P<sel>[a-z ]+?) not chosen this way(?: to their owners' hands)?\.$")
_AND_COUNTER = re.compile(r"^[Ee]ach player chooses an? (?P<sel>[a-z ]+?) and puts an? (?P<kind>[a-z]+) counter on it\.$")
_PLANAR = ("Each player chooses a land they control of each basic land type.", "Return those lands to their owners' hands.")
_REJOIN = ("Mill three cards.", "Then starting with the next opponent in turn order, each opponent chooses a creature card in your graveyard that hasn't been chosen.",
           "Return each card chosen this way to the battlefield under your control.")
_DREDGE = ("Each opponent chooses a creature card in their graveyard.", "Put those cards onto the battlefield under your control.")
_WATCHERS = ("Each opponent chooses two cards in their graveyard and exiles the rest.",)
_GRENZO = ("Create a 4/4 red Ogre creature token.", "Starting with you, each player chooses an artifact, a creature, and a land from among the permanents "
           "controlled by the player to their left.", "Destroy each permanent chosen this way.")
_SUNBURST = ("Choose a creature you control, then each opponent chooses a creature they control with equal or lesser power.",
             "If you chose a creature this way, exile each creature not chosen by any player this way.")
_VERBS = {"Return": "bounce", "Exile": "exile", "Destroy": "destroy"}
_OBLITERATION = ("Each player chooses a color.", "Then exile each permanent unless it's colorless or it's only the color its controller chose.")
_STICK = ("Each player chooses a party from among creatures they control, then sacrifices the rest.",)
_BALANCE = re.compile(r"^Each player chooses a number of (?P<k>lands|permanents) they control equal to the number of (?P=k) controlled by the player who controls the "
                      r"fewest, then sacrifices the rest\. (?P<tail>Players sacrifice creatures and discard cards the same way|Players discard cards and sacrifice "
                      r"creatures the same way|Each player discards cards the same way)\.$")
_STEAMBOAT = ("Each player chooses two nontoken, non-Vehicle creatures they control.", "Exile them until ~ leaves the battlefield.")
_SOTHERA = ("Each opponent chooses a creature they control and exiles it.",)
_BOND = "Each opponent sacrifices a permanent of their choice that shares a card type with it."  # (wave 110B: Martyr's Bond, "it" = the permanent that was put into the graveyard)
_GRUDGE = "Each opponent chooses a permanent they control that shares a card type with the sacrificed permanent and sacrifices it."
_MANIFOLD = ("Reveal the top ten cards of your library.", "Starting with the next opponent in turn order, each opponent chooses a different nonland card from "
             "among them.", "Put the chosen cards into your hand and the rest on the bottom of your library in a random order.")


def _key(phrase: str) -> str | None:
    from app.rules import selectors

    sel = selectors.parse(phrase)
    return None if sel is None else sel.key()


_VOID = ("Each player secretly chooses a creature they control and a creature they don't control.", "Then those choices are revealed.",
         "Destroy each creature chosen this way.")
_SAFE = ("You and target opponent each secretly choose 1, 2, or 3.", "Then those choices are revealed.",
         "If they match, sacrifice ~ and put all cards exiled with it into their owners' hands.", "Otherwise, exile the top card of your library face down.")


def _chosen_objects(text: str, parse: Any, split_sentences: Any) -> tuple[list[dict[str, Any]], Any, bool] | None:
    sentences = split_sentences(text)
    if len(sentences) == 1 and (keep := re.fullmatch(
            r"[Cc]hoose (?P<upto>up to )?(?P<n>one|two|three|four|five|six|seven|eight|nine|\d+) "
            r"(?P<sel>.+?), then destroy the rest\.", sentences[0])) is not None:
        from app.rules import selectors, values

        sel = selectors.parse(keep["sel"])
        keep_n = int(keep["n"]) if keep["n"].isdigit() else values.NUMBERS[keep["n"]]
        if sel is None or sel.player is not None or sel.card or sel.zones != ("battlefield",) or keep_n < 1:
            return None
        # CR 608.2d: choose on resolution, without targeting, from all eligible
        # permanents. A separate complement instruction spans every controller;
        # player_chooses.rest instead refers to that player's own permanents.
        keep_key = sel.key()
        return [{"do": "player_chooses", "who": "you", "sel": keep_key, "n": keep_n, "label": keep["sel"],
                 "any": True, "upto": bool(keep["upto"]), "as": "gco"},
                {"do": "destroy", "who": f"except:gco|{keep_key}"}], None, False
    if tuple(sentences) == _VOID and (key := _key("creature")) is not None:
        # Call to the Void: a creature they control and a creature they don't, in secret (101.4c: in that order), revealed at once, each destroyed once
        return [{"do": "gc_choose", "who": "each_player", "what": "object", "secret": True, "as": "gc", "kinds": [
            {"sel": key, "mine": True, "say": "a creature you control"}, {"sel": key, "mine": False, "say": "a creature you don't control"}]},
                {"do": "destroy", "who": "ref:gc:chosen"}], None, False
    if tuple(sentences) == _SAFE:
        # Expert-Level Safe: you and the target opponent each secretly choose 1, 2 or 3; if they match, the cards exiled with it go to hand and it is sacrificed
        # (the cards first: "exiled with it" is read while it is here; the two happen together), otherwise the top card of your library is exiled face down (linked).
        # (built here, not read from the sentences; the exile is a primitive of its own so that this is no "ability that exiles and refers to its own exiled card",
        # which exiled_with._link reads again without the templates and refuses: it refers to everything exiled with it, by this ability and by the other, 607.2a)
        return [{"do": "gc_choose", "who": ["you", "target"], "what": "word", "opts": ["1", "2", "3"], "secret": True, "as": "gc", "say": "1, 2, or 3"},
                {"do": "only_if", "cond": {"gc": {"as": "gc", "is": "match"}}, "skip": 2}, {"do": "return_card", "who": "exiled_with", "to": "hand"},
                {"do": "sacrifice", "who": "self"}, {"do": "only_if", "cond": {"gc": {"as": "gc", "is": "differ"}}, "skip": 1},
                {"do": "gc_exile_linked", "n": 1, "player": "you", "face_down": True}], "opponent", False
    if len(sentences) == 2 and [sentences[0][:1].upper() + sentences[0][1:], re.sub(r"\bthis (?:Vehicle|creature|artifact|permanent)\b", "~", sentences[1])] == list(_STEAMBOAT) \
            and (chosen := parse(_STEAMBOAT[0])) is not None and len(chosen[0]) == 1 and chosen[0][0].get("do") == "player_chooses":
        # Foreboding Steamboat: starting with the active player each player chooses two (101.4), then all the chosen creatures are exiled at once, until it leaves
        return [{**chosen[0][0], "as": "gco"}, {"do": "exile_until", "who": "ref:gco"}], None, False
    if sentences and [sentences[0][:1].upper() + sentences[0][1:]] == list(_SOTHERA) and len(sentences) == 1 and (key := _key("creature")) is not None:
        # Sothera, the Supervoid: each opponent chooses a creature they control and exiles it (the exiles are linked to Sothera, 607.2a: exiled_with.link)
        return [{"do": "player_chooses", "who": "each_opponent", "sel": key, "n": 1, "label": "creature", "as": "gco"}, {"do": "exile", "who": "ref:gco"}], None, False
    m = _ONE_CHOICE.match(sentences[0]) if sentences else None
    if m is not None and len(sentences) in (2, 3) and (n := _NOT_CHOSEN.match(sentences[1])) is not None:
        # Consuming Tide: "Each player chooses a nonland permanent they control. Return all nonland permanents not chosen this way to their owners' hands."
        # (+ "Then you draw a card for each opponent who has more cards in their hand than you.")
        key, key2 = _key(m["sel"]), _key(n["sel"])
        tail = parse(re.sub(r"^Then you draw (.+?) in their hand than you\.$", r"Draw \1 in hand than you.", sentences[2])) if len(sentences) == 3 else ([], None, False)
        if key is None or key != key2 or tail is None or tail[1] is not None or tail[2]:
            return None
        return [{"do": "player_chooses", "who": "each_player", "sel": key, "n": 1, "label": m["sel"], "as": "gco"},
                {"do": _VERBS[n["verb"]], "who": f"except:gco|{key}"}, *tail[0]], None, False
    m = _AND_COUNTER.match(sentences[0]) if len(sentences) == 1 else None
    if m is not None and (key := _key(m["sel"])) is not None:
        # Eye of Doom: "Each player chooses a nonland permanent and puts a doom counter on it": any permanent, the counters all at once afterwards
        return [{"do": "player_chooses", "who": "each_player", "sel": key, "n": 1, "label": m["sel"], "any": True, "as": "gco"},
                {"do": "add_counters", "who": "ref:gco", "kind": m["kind"], "n": 1}], None, False
    if tuple(sentences) == _PLANAR:  # Planar Overlay
        from app.rules import language

        got = language._kinds_effect("each player", ["Plains", "Island", "Swamp", "Mountain", "Forest"], "lands", rest=None)  # (205.3i)
        return [{**got[0][0], "as": "gco"}, {"do": "bounce", "who": "ref:gco"}], None, False
    if tuple(sentences) == _REJOIN and (key := _key("creature card in your graveyard")) is not None and (mill := parse(_REJOIN[0])) is not None:
        return [*mill[0], {"do": "player_chooses", "who": "each_opponent", "sel": key, "n": 1, "label": "creature card", "any": True, "start": "next",
                           "distinct": True, "as": "gco"},
                {"do": "return_card", "who": "ref:gco", "to": "battlefield", "tapped": False, "under": "you"}], None, False
    if tuple(sentences) == _DREDGE and (key := _key("creature card in your graveyard")) is not None:
        return [{"do": "player_chooses", "who": "each_opponent", "sel": key, "n": 1, "label": "creature card", "as": "gco"},
                {"do": "return_card", "who": "ref:gco", "to": "battlefield", "tapped": False, "under": "you"}], None, False
    if tuple(sentences) == _WATCHERS and (key := _key("card in your graveyard")) is not None:
        return [{"do": "player_chooses", "who": "each_opponent", "sel": key, "n": 2, "label": "card", "rest": "exile"}], None, False
    if tuple(sentences) == _GRENZO and (token := parse(_GRENZO[0])) is not None:
        kinds = [_key(k) for k in ("artifact", "creature", "land")]
        if None in kinds or (all_perm := _key("permanent")) is None:
            return None
        return [*token[0], {"do": "player_chooses", "who": "each_player", "sel": all_perm, "sels": kinds, "labels": ["artifact", "creature", "land"], "n": 1,
                            "label": "permanent", "start": "you", "left": True, "as": "gco"}, {"do": "destroy", "who": "ref:gco"}], None, False
    if tuple(sentences) == _SUNBURST and (key := _key("creature")) is not None:
        # Sculpted Sunburst: you choose first, then each opponent chooses one with equal or lesser power than yours; if you chose, every other creature goes
        return [{"do": "player_chooses", "who": "you", "sel": key, "n": 1, "label": "creature", "as": "gco", "did": "gcd"},
                {"do": "player_chooses", "who": "each_opponent", "sel": key, "n": 1, "label": "creature", "cap_power": "ref:gco", "add": True, "as": "gco"},
                {"do": "only_if", "cond": {"succeeded": "gcd"}, "skip": 1}, {"do": "exile", "who": f"except:gco|{key}"}], None, False
    if tuple(sentences) == _OBLITERATION:  # Selective Obliteration: a public choice of a color by each player, then the sweep
        return [{"do": "gc_choose", "who": "each_player", "what": "color", "as": "gc"}, {"do": "gc_sweep", "as": "gc"}], None, False
    if tuple(sentences) == _STICK:  # Stick Together: a party (700.8) from the creatures they control; the rest are sacrificed
        kinds = [_key(f"{t} creature") for t in ("Cleric", "Rogue", "Warrior", "Wizard")]
        if None in kinds or (key := _key("creature")) is None:
            return None
        return [{"do": "player_chooses", "who": "each_player", "sel": key, "n": 1, "label": "creature of the party", "party": kinds, "rest": "sacrifice"}], None, False
    if (b := _BALANCE.match(text)) is not None:  # Restore Balance, Magus of the Balance, Balancing Act: each stage down to the fewest, one after the other
        order = {"lands": ["lands"], "permanents": ["permanents"]}[b["k"]]
        stages = ["creatures", "hand"] if b["tail"].startswith("Players sacrifice") else ["hand", "creatures"] if b["tail"].startswith("Players discard") else ["hand"]
        out: list[dict[str, Any]] = []
        for kind in [*order, *stages]:
            if kind == "hand":
                out.append({"do": "discard", "who": "each_player", "n": 0, "fewest": True})
            elif (key := _key(kind[:-1])) is not None:
                out.append({"do": "player_chooses", "who": "each_player", "sel": key, "n": {"fewest": key}, "label": kind[:-1], "rest": "sacrifice"})
        return out, None, False
    if tuple(sentences) == (_GRUDGE,) and (key := _key("permanent")) is not None:
        # Fatal Grudge: each opponent chooses (and sacrifices) a permanent sharing a card type with the one sacrificed as the spell's additional cost
        return [{"do": "edict", "who": "each_opponent", "sel": key, "n": 1, "label": "permanent", "shares_type_with": "cost"}], None, False
    if tuple(sentences) == _MANIFOLD and (key := _key("nonland card")) is not None and (look := parse("Reveal the top ten cards of your library. Put the rest "
                                                                                                    "on the bottom of your library in a random order.")) is not None:
        return [look[0][0], {"do": "player_chooses", "who": "each_opponent", "sel": key, "n": 1, "label": "nonland card", "looked": True, "start": "next",
                             "distinct": True, "as": "gco"}, {"do": "return_card", "who": "ref:gco", "to": "hand"}, look[0][1]], None, False
    return None


# -- bids (Mages' Contest, Illicit Auction, Pain's Reward) ----------------------------------------------------------
_BID_HEADS = {"You and target spell's controller bid life.": ("you_and_spell_controller", "Counter target spell."),
              "Each player may bid life for control of target creature.": ("each_player", "Gain control of target creature."),
              "Each player may bid life.": ("each_player", None)}
_BID_START = re.compile(r"^You start the bidding with a bid of (?P<n>\d+|any number)\.$")
_BID_RULES = ("In turn order, each player may top the high bid.", "The bidding ends if the high bid stands.")
_BID_RESULT = re.compile(r"^The high bidder loses life equal to the high bid(?P<tail> and gains control of the creature| and draws four cards)?\.$")
_BID_COUNTER = "If you win the bidding, counter that spell."


def _bids(text: str, parse: Any, split_sentences: Any) -> tuple[list[dict[str, Any]], Any, bool] | None:
    sentences = split_sentences(text)
    head = _BID_HEADS.get(sentences[0]) if sentences else None
    if head is None or len(sentences) < 5 or (start := _BID_START.match(sentences[1])) is None or tuple(sentences[2:4]) != _BID_RULES \
            or (result := _BID_RESULT.match(sentences[4])) is None:
        return None
    rest = sentences[5:]
    tail = result["tail"]
    if (head[0] == "you_and_spell_controller") != (rest == [_BID_COUNTER]) or (head[0] != "you_and_spell_controller" and rest) \
            or (head[1] and head[1].startswith("Gain") != (tail == " and gains control of the creature")) \
            or ((tail == " and draws four cards") != (head[1] is None)):
        return None
    target = parse(head[1]) if head[1] else None
    if head[1] and (target is None or len(target[0]) != 1):
        return None
    out: list[dict[str, Any]] = [{"do": "gc_bid", "who": head[0], "start": "any" if start["n"] == "any number" else int(start["n"]), "as": "bd"},
                                 {"do": "lose_life", "who": "ref:bd:winner", "n": {"ref_amount": "bd_high"}}]
    if tail == " and gains control of the creature" and target is not None:
        out.append({**target[0][0], "to": "ref:bd:winner"})
    elif tail == " and draws four cards":
        out.append({"do": "draw", "who": "ref:bd:winner", "n": 4})
    elif target is not None:  # "If you win the bidding, counter that spell."
        out += [{"do": "only_if", "cond": {"gc": {"as": "bd", "is": "you", "set": "winner"}}, "skip": 1}, target[0][0]]
    return out, target[1] if target else None, False


# -- hands, graveyards, names, directions -------------------------------------------------------------------------------
_WORLDPURGE = ("Return all permanents to their owners' hands.", "Each player chooses up to seven cards in their hand, then shuffles the rest into their library.",
               "Each player loses all unspent mana.")
_GAMBIT = ("Each player chooses a card in their hand.", "Then each player reveals their chosen card.",
           "The owner of each creature card revealed this way with the lowest mana value puts it onto the battlefield.")
_SIFTER = ("Each player chooses a creature type and returns any number of cards of that type from their graveyard to their hand.",)
_SPHINX = ("Each player chooses a card name.", "Then each player reveals the top card of their library.",
           "If the card a player revealed has the name they chose, that player puts it into their hand.",
           "If it doesn't, that player puts it on the bottom of their library.")
_SUCCESSION = ("Choose left or right.", "Starting with you and proceeding in the chosen direction, each player chooses a creature controlled by the next player in that direction.",
               "Each player gains control of the creature they chose.")


def _hands(text: str, parse: Any, split_sentences: Any) -> tuple[list[dict[str, Any]], Any, bool] | None:
    sentences = split_sentences(text)
    if sentences:
        sentences[0] = sentences[0][:1].upper() + sentences[0][1:]  # (a trigger's body)
    if tuple(sentences) == _WORLDPURGE and (back := parse(_WORLDPURGE[0])) is not None:
        return [*back[0], {"do": "gc_keep_hand", "n": 7}, {"do": "gc_lose_mana"}], None, False
    if tuple(sentences) == _GAMBIT:  # each chooses a card in hand (face down, 101.4a), all revealed together; the lowest creature card(s) enter
        return [{"do": "gc_choose", "who": "each_player", "what": "hand", "secret": True, "as": "gc", "say": "a card in your hand"}, {"do": "gc_lowest_creature", "as": "gc"}], None, False
    if tuple(sentences) == _SIFTER:  # Grave Sifter
        return [{"do": "gc_choose", "who": "each_player", "what": "creature type", "as": "gc"}, {"do": "gc_typed_return", "as": "gc"}], None, False
    if tuple(sentences) == _SPHINX:  # Conundrum Sphinx
        return [{"do": "gc_choose", "who": "each_player", "what": "card name", "as": "gc"}, {"do": "gc_reveal_names", "as": "gc"}], None, False
    if tuple(sentences) == _SUCCESSION:  # Order of Succession
        return [{"do": "gc_choose", "who": "you", "what": "word", "opts": ["left", "right"], "as": "gc", "say": "left or right"}, {"do": "gc_succession", "as": "gc"}], None, False
    return None


_TRAP = ("Secretly choose a number between 1 and 5 that hasn't been chosen.",
         "If you do, an opponent guesses which number you chose, then you reveal the number you chose.",
         "If they guessed wrong, they lose life equal to the number they guessed and you draw a card.", "If they guessed right, sacrifice ~.")


def _guess(text: str, parse: Any, split_sentences: Any) -> tuple[list[dict[str, Any]], Any, bool] | None:
    """The Toymaker's Trap: secretly choose a number (not one chosen before), an opponent guesses, the number is revealed, a wrong guess loses life and draws, a
    right guess sacrifices the enchantment."""
    sentences = split_sentences(text)
    if sentences:
        sentences[0] = sentences[0][:1].upper() + sentences[0][1:]  # (a trigger's body)
    draw, sacrifice = parse("Draw a card."), parse("Sacrifice ~.")
    if tuple(sentences) != _TRAP or draw is None or sacrifice is None or len(draw[0]) != 1 or len(sacrifice[0]) != 1:
        return None
    numbers = ["1", "2", "3", "4", "5"]
    return [{"do": "gc_choose", "who": "you", "what": "word", "opts": numbers, "memory": True, "secret": True, "quiet": True, "as": "tn",
             "say": "a number between 1 and 5 that hasn't been chosen"},
            {"do": "only_if", "cond": {"gc": {"as": "tn", "is": "any"}}, "skip": 3},
            {"do": "choose_opponent", "as": "copp"},
            {"do": "gc_choose", "who": "ref:copp", "what": "word", "opts": numbers, "as": "tg", "say": "which number was chosen"},
            {"do": "gc_guess", "bind": "tn", "as": "tg", "wrong": [{"do": "lose_life", "who": "ref:copp", "n": {"ref_amount": "tg_n"}}, draw[0][0]],
             "right": [sacrifice[0][0]]}], None, False


_AUCTION = ("Exile all nontoken permanents.", "Starting with you, each player chooses one of the exiled cards and puts it onto the battlefield tapped under their control.",
            "Repeat this process until all cards exiled this way have been chosen.")


def _auction(text: str, parse: Any, split_sentences: Any) -> tuple[list[dict[str, Any]], Any, bool] | None:
    """Thieves' Auction: all nontoken permanents exiled, then the players take turns choosing one each until all are chosen."""
    if tuple(split_sentences(text)) != _AUCTION or (exile := parse(_AUCTION[0])) is None or len(exile[0]) != 1:
        return None
    return [{**exile[0][0], "as": "ex"}, {"do": "gc_auction", "from": "ref:ex", "as": "ac"}], None, False


def _linked_graveyard(text: str, parse: Any, split_sentences: Any) -> tuple[list[dict[str, Any]], Any, bool] | None:
    """Foreboding Steamboat: one of the cards exiled with it goes into its owner's graveyard, and if a card did, investigate."""
    sentences = split_sentences(text)
    if sentences:
        sentences[0] = sentences[0][:1].upper() + sentences[0][1:]  # (a trigger's body)
    if len(sentences) != 2 or sentences[1] != "If you do, investigate." or (put := parse(sentences[0])) is None or len(put[0]) != 1 or put[0][0].get("do") != "return_choice" \
            or put[0][0].get("to") != "graveyard" or (clue := parse("Investigate.")) is None or len(clue[0]) != 1:
        return None
    return [{**put[0][0], "did": "rd"}, {"do": "only_if", "cond": {"succeeded": "rd"}, "skip": 1}, clue[0][0]], None, False


_EMISSARY_USE = "Choose new targets for target spell or ability if it's controlled by the chosen player and if it targets you or a permanent you control."
_LEONIN_USE = "Exile target creature that's attacking you if it's controlled by the chosen player."
_KILLER_TOKENS = "Create a 1/1 white Human creature token, a 1/1 blue Merfolk creature token, and a 1/1 red Goblin creature token."
_KILLER_USE = "If target attacking creature token is the chosen type, put three +1/+1 counters on it and it gains deathtouch until end of turn."


def _secret_ability(text: str, parse: Any, split_sentences: Any) -> tuple[list[dict[str, Any]], Any, bool] | None:
    """Stalking Leonin ("secretly choose an opponent"; the reveal ability exiles the attacker if its controller is the chosen player) and A Killer Among Us (three tokens, then
    "secretly choose Human, Merfolk, or Goblin"; the reveal ability gives a token of the chosen type three counters and deathtouch)."""
    sentences = split_sentences(text)
    if sentences:
        sentences[0] = sentences[0][:1].upper() + sentences[0][1:]  # (a trigger's body)
    if sentences == ["Secretly choose an opponent."]:
        return [{"do": "gc_secret", "what": "opponent"}], None, False
    if sentences == [_KILLER_TOKENS, "Then secretly choose Human, Merfolk, or Goblin."] and (tokens := parse(_KILLER_TOKENS)) is not None:
        return [*tokens[0], {"do": "gc_secret", "what": "word", "opts": ["Human", "Merfolk", "Goblin"]}], tokens[1], False
    if sentences == [_LEONIN_USE] and (found := parse("Exile target creature that's attacking you.")) is not None and len(found[0]) == 1:
        return [{"do": "only_if", "cond": {"secret": {"is": "controller"}}, "skip": 1}, found[0][0]], found[1], False
    if sentences == [_EMISSARY_USE] and (found := parse("Choose new targets for target spell or ability.")) is not None and len(found[0]) == 1:  # (wave 110E)
        return [{"do": "only_if", "cond": {"secret": {"is": "controller"}}, "skip": 2}, {"do": "only_if", "cond": {"targets_mine110e": True}, "skip": 1}, found[0][0]], found[1], False
    if sentences == [_KILLER_USE] and (found := parse("Put three +1/+1 counters on target attacking creature token. It gains deathtouch until end of turn.")) is not None:
        return [{"do": "only_if", "cond": {"secret": {"is": "type"}}, "skip": len(found[0])}, *found[0]], found[1], False
    return None

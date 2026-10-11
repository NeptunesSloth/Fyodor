"""-- per-player filters (wave 23A) -- "Each opponent who doesn't control an Elf loses 1 life." (Thornbow Archer), "Each player who
controls a multicolored creature draws a card." (Depopulate), "Each player who controls the most creatures investigates." (No
Witnesses), "Each opponent discards a card. Each opponent who can't loses 3 life." (Entropic Battlecruiser, Refurbished Familiar,
Plaguecrafter), "Draw a card for each opponent who controls fewer creatures than you." (Voice of Many).

CR 2026-09-25: 608.2c (an instruction is carried out for each player it names, in the order the text gives: here APNAP, 101.4, by
the instruction itself); 608.2h (what a player controls, has or did is read as the instruction is carried out); 800.4a (a player who
left the game is none of them).

A *predicate* is data, judged for one player at a time as the instruction is reached:

* ``{"cond": <condition>}`` — any condition conditions.py reads for "you" ("you control an Elf", "you have three or more poison
  counters", "you lost life this turn"), read as that player;
* ``{"vs": <value>, "op": ">" | "<"}`` — that player's quantity (a value read as "you") against the ability's controller's: "controls
  more creatures than you", "has fewer cards in hand than you", "has more life than you";
* ``{"extreme": <value>, "most": bool}`` — the most / fewest of every player still in the game (ties all qualify: "the most" is
  met by whoever has no fewer than anyone else);
* ``{"dealt": bool}`` — the player was dealt damage (``dealt`` True: combat damage) this turn (the turn's log, history.py);
* ``{"tw": <spec>, "has": bool}`` — whether the player is among those an earlier instruction of this resolution acted on
  ("Each player who can't" / "who didn't discard a nonland card this way": ``has`` False; the instruction recorded them, this_way.py).

The sentence form ``sentence`` turns "Each opponent who P, [do it]" into one ``players_where`` instruction (the players, bound as
``ref:pw<k>``) followed by the clause read for "each opponent", aimed at that binding; ``count`` reads "the number of opponents who
P" as a value. Neither reads a predicate it doesn't know (the card stays manual); nothing here looks at hidden information (counts
of cards in a hand are public, 402.3)."""

from __future__ import annotations

import copy
import json
import re
from typing import TYPE_CHECKING, Any

from app.rules import conditions, context, values

if TYPE_CHECKING:
    from collections.abc import Callable

    from app.rules.plan import Plan

Pred = dict[str, Any]
Context = dict[str, Any]
_BASE = {"opponent": "each_opponent", "player": "each_player"}
_THIS_WAY_KINDS = {"discard": "discarded", "edict": "sacrificed", "sacrifice_choice": "sacrificed"}
_VERB = {"discard": "discarded", "sacrifice": "sacrificed"}
_CANT = re.compile(r"^(?:can't|couldn't)$")
_DIDNT = re.compile(r"^(?:didn't|did not|doesn't|does not|don't) (?P<verb>discard|sacrifice)(?: (?P<what>.+?))?(?: this way)?$")
_DID = re.compile(r"^(?P<verb>discarded|sacrificed)(?: (?P<what>.+?))?(?: this way)?$")
_REL = re.compile(r"^(?P<verb>controls?|has|have) (?P<cmp>more|fewer|less) (?P<what>.+?) than you(?: do)?$")
_EXT = re.compile(r"^(?P<verb>controls?|has|have) the (?P<ext>most|fewest|least|highest|lowest) (?P<what>.+)$")
_BAD = re.compile(r"\b(?:another|~|this|that|it|them|they|their|each other)\b")


def _quantity(what: str, verb: str) -> Any:
    """"creatures" / "lands" (controls), "life" / "cards in hand" (has) as a value read for "you"."""
    if verb in ("has", "have"):
        return {"life": "you"} if what == "life" else {"hand": "you"} if what == "cards in hand" else None
    key = conditions._count(what, "you control")
    return {"count": key} if key else None


def parse_pred(text: str, prior: dict[str, Any] | None = None) -> Pred | None:
    """The predicate a "who …" phrase states, or None. ``prior``: the earlier instruction a "this way" form is about (resolve_it binds
    its recording to the placeholder)."""
    t = text.strip().rstrip(".").strip()
    if not t or _BAD.search(t.replace("this way", "").replace("this turn", "")):
        return None
    if re.search(r"\byou(?:r|rs|rself)?\b", re.sub(r" than you(?: do)?$", "", t)):
        return None  # (review 23A: "controls your commander": "you" is the ability's controller, not the player judged)
    if prior is not None and (m := (_CANT.match(t) or _DIDNT.match(t) or _DID.match(t))) is not None:
        kind = _THIS_WAY_KINDS.get(prior.get("do", ""))
        verb = m.groupdict().get("verb")
        if kind is None or not str(prior.get("who", "")).startswith("each") or (verb is not None and _VERB.get(verb, verb) != kind):
            return None
        spec: dict[str, Any] = {"this_way": kind, "of": None}
        n = 1
        if m.groupdict().get("what"):
            from app.rules import this_way

            q = re.match(r"^(?P<q>an?|one|two|three|four|five|\d+) (?P<noun>.+)$", m["what"])
            if q is None:
                return None
            n = 1 if q["q"] in ("a", "an", "one") else int(q["q"]) if q["q"].isdigit() else values.NUMBERS[q["q"]]
            got = this_way.parse(f"{q['noun']} {kind} this way")
            if got is None or got.get("this_way") != kind:
                return None
            spec["of"] = got.get("of")
        return {"tw": spec, "has": _DID.match(t) is not None, "n": n}
    if (m := _REL.match(t)) is not None:
        value = _quantity(m["what"], m["verb"])
        return None if value is None else {"vs": value, "op": ">" if m["cmp"] == "more" else "<"}
    if (m := _EXT.match(t)) is not None:
        value = _quantity(m["what"], m["verb"])
        return None if value is None else {"extreme": value, "most": m["ext"] in ("most", "highest")}
    if (m := re.fullmatch(r"(?:was|were) dealt (?P<c>combat )?damage this turn", t)) is not None:
        return {"dealt": bool(m["c"])}
    # a condition as that player: "controls an Elf" → "you control an Elf", "has three or more poison counters" → "you have …"
    sub = re.sub(r"^(?:controls|control)\b", "you control", t)
    sub = re.sub(r"^(?:doesn't|does not|don't) control\b", "you don't control", sub)
    sub = re.sub(r"^(?:has|have)\b", "you have", sub)
    sub = re.sub(r"^(?:doesn't|does not|don't) have\b", "you don't have", sub)
    if not sub.startswith("you "):
        sub = f"you {t}"
    cond = conditions.parse(sub)
    if cond is None or '"as"' in json.dumps(cond) or "event" in json.dumps(cond):
        return None
    return {"cond": cond}


def holds(plan: Plan, ctx: Context, pred: Pred, pid: str) -> bool:
    """Is the predicate true of this player now (608.2h)?"""
    if "any" in pred:
        return True
    if "cond" in pred:
        return conditions.holds(plan, {**ctx, "controller": pid}, pred["cond"])
    if "vs" in pred:
        mine = values.evaluate(plan, ctx, pred["vs"])
        theirs = values.evaluate(plan, {**ctx, "controller": pid}, pred["vs"])
        return theirs > mine if pred["op"] == ">" else theirs < mine
    if "extreme" in pred:
        got = {p: values.evaluate(plan, {**ctx, "controller": p}, pred["extreme"]) for p in plan.live()}
        best = max(got.values(), default=0) if pred["most"] else min(got.values(), default=0)
        return pid in got and got[pid] == best
    if "dealt" in pred:  # (this turn's log: damage dealt to the player, 120.3; ``dealt`` True: combat damage only)
        from app.rules import history

        return any(f.kind == "damage" and f.player == pid and f.amount > 0 and (f.combat or not pred["dealt"])
                   for f in history.log_for(plan).facts)
    if "tw" in pred:
        from app.rules import this_way

        did = this_way.by_controller(plan, ctx, pred["tw"]).get(pid, 0) >= int(pred.get("n", 1))
        return did == bool(pred["has"])
    raise ValueError(f"unknown player predicate {pred!r}")


def players(plan: Plan, ctx: Context, base: str, pred: Pred) -> list[str]:
    """The players of the group ("opponent" / "player") the predicate holds for, still in the game (800.4a)."""
    me = ctx["controller"]
    return [p for p in plan.live() if (base == "player" or p != me) and holds(plan, ctx, pred, p)]


def players_where(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """Bind the players the predicate holds for (as the instruction is reached) under ``as``; the instruction after reads them."""
    who = players(plan, ctx, e["base"], e["pred"])
    context.bind_players(ctx, e["as"], who)
    if e.get("repeat"):  # "For each opponent who can't, you draw a card.": the next instructions once for each of them (608.2c)
        effects, at, k = ctx["effects"], ctx["next"], int(e["repeat"])
        block = effects[at:at + k]
        effects[at:at + k] = [copy.deepcopy(x) for _ in who for x in block]
    return True


PRIMITIVES = {"players_where": players_where}


def allowed(definition: dict[str, Any]) -> bool:
    """-- review (wave 23A) -- a "who" read from this turn's log ("each player who discarded a card this turn", "who lost life this
    turn", "who were dealt combat damage this turn") only as an ability's first instruction: the log takes in an instruction's
    events after the resolution (history.note_events), so one read after an earlier instruction of the same ability would miss
    what that instruction did (Azula: "You may discard a card. Then … for each player who discarded a card this turn")."""
    for effects in [definition.get("effects") or [], *((m.get("effects") or []) for m in definition.get("modes") or [])]:
        for e in effects[1:]:
            dumped = json.dumps(e)
            if "players_where" in dumped and ('"history"' in dumped or '"dealt"' in dumped):
                return False
    return True

# -- activated other (wave 34B) -- "Each opponent with no cards in hand loses 10 life." (Tinybones, Trinket Thief): "with …" is "who has …"
_SENTENCE = re.compile(r"^each (?P<b>opponent|player) (?:who|(?P<with>with)) (?P<rest>.+)$")
_FOR_EACH = re.compile(r"^for each (?P<b>opponent|player) who (?P<pred>[^,]+), (?P<rest>.+)$")
_EACH_OPP = re.compile(r"^for each opponent, (?P<rest>.+)$")
_THEN = re.compile(r"(?i)(?<=[a-z]), then (each (?:opponent|player) who )")


def rewrite(body: str) -> str:
    """"Each opponent discards a card, then each opponent who didn't discard a nonland card this way loses 3 life." (Kroxa): the
    second part is a sentence of its own."""
    return _THEN.sub(lambda m: f". E{m[1][1:]}", body)


def sentence(text: str, effects: list[dict[str, Any]], read: Callable[[str], list[dict[str, Any]] | None]) -> list[dict[str, Any]] | None:
    """"Each opponent who [predicate] [verb phrase]" (a sentence of its own, lower-cased as the sentence loop has it) → the
    ``players_where`` instruction and the clause with its "each opponent" aimed at those players, or None (not this grammar, or a
    predicate / clause that isn't read). ``read`` parses "Each opponent [verb phrase]." into effects. An earlier instruction a
    "this way" predicate is about must follow an instruction that records who it acted on."""
    prior = effects[-1] if effects else None
    name = f"pw{sum(1 for x in effects if x.get('do') == 'players_where')}"
    if (f := _FOR_EACH.match(text.rstrip("."))) is not None:
        return _for_each(f["b"], parse_pred(f["pred"], prior), f["rest"], name, read)
    if (o := _EACH_OPP.match(text.rstrip("."))) is not None:
        return _for_each("opponent", {"any": True}, o["rest"], name, read)
    m = _SENTENCE.match(text.rstrip("."))
    if m is None:
        return None
    base, words = m["b"], (("has " if m["with"] else "") + m["rest"]).split(" ")
    for i in range(1, len(words)):
        pred = parse_pred(" ".join(words[:i]), prior)
        if pred is None:
            continue
        clause = " ".join(words[i:])
        inner = read(f"Each {base} {clause}.")
        if not inner:
            continue
        key = _BASE[base]
        aimed = [{**e, "who": f"ref:{name}"} if e.get("who") == key else e for e in inner]
        if aimed == inner or any(str(e.get("who", "")).startswith("each") for e in aimed):
            continue  # (nothing aimed at the group, or a part of the clause still addresses everyone)
        return [{"do": "players_where", "as": name, "base": base, "pred": pred}, *aimed]
    return None


def _for_each(base: str, pred: Pred | None, clause: str, name: str,
              read: Callable[[str], list[dict[str, Any]] | None]) -> list[dict[str, Any]] | None:
    """"For each opponent [who predicate], [instruction]": the instruction once for each player the predicate holds for (the
    instruction names no player of the group: it is the controller's, once for each; "create a token" is one creation)."""
    rest = clause[:1].upper() + clause[1:]
    if pred is None or re.search(r"\b(?:that (?:player|opponent)|they|them|their|each (?:opponent|player))\b", rest):
        return None
    inner = read(rest + ".")
    dumped = json.dumps(inner)
    if not inner or '"ref:' in dumped or '"target' in dumped or '"it"' in dumped or "event_amount" in dumped or "this_way" in dumped:
        return None
    if len(inner) == 1 and inner[0].get("do") == "create_token" and inner[0].get("n") == 1:
        return [{**inner[0], "n": {"players_where": {"base": base, "pred": pred}}}]  # (one creation of that many tokens, 111.2)
    return [{"do": "players_where", "as": name, "base": base, "pred": pred, "repeat": len(inner)}, *inner]


def count(what: str) -> dict[str, Any] | None:
    """"the number of opponents who P" / "opponent who P" (a "for each" count) → ``{"players_where": …}``, or None."""
    m = re.fullmatch(r"(?:the number of )?(?P<b>opponent|player)s? who (?P<p>.+)", what.strip())
    if m is None or "this way" in m["p"]:
        return None
    pred = parse_pred(m["p"])
    return None if pred is None else {"players_where": {"base": m["b"], "pred": pred}}


def amount(plan: Plan, ctx: Context, v: dict[str, Any]) -> int:
    spec = v["players_where"]
    return len(players(plan, ctx, spec["base"], spec["pred"]))

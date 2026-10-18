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
* "of a type / color chosen this way": the later instructions' ``chosen_type`` / ``chosen_color`` selectors are bound to every type or color
  chosen (any of them; "aren't of": none of them). Choosing a value already chosen is allowed and changes nothing (Patriarch's Bidding ruling).
* "For each player who chose X, …" (``gc_each``): the next ``skip`` instructions once for each such player in APNAP order, "that player" being
  ``@P`` in the instructions (becomes ``player:<id>``). "the highest / lowest number" (``gc_extremes``): binds the players who chose the
  highest (``<name>:hi``), the lowest (``lo``) and not the lowest (``nlo``) number and their amounts (``<name>_hi``, ``<name>_lo``).
"""

from __future__ import annotations

import copy
import json
import re
from typing import TYPE_CHECKING, Any

from app.game.errors import ActionError
from app.game.rules_state import DecisionOption

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
    if not re.fullmatch(rf"\d{{1,{MAX_DIGITS}}}", text):
        raise ActionError(f"Type a whole number of 0 to {'9' * MAX_DIGITS}")
    least = int(d.options[0].label.rsplit("≥", 1)[-1]) if "≥" in d.options[0].label else 0
    if int(text) < least:
        raise ActionError(f"Type a number of {least} or more")
    return str(int(text))


# -- the choice ------------------------------------------------------------------------------------------------
def _options(plan: Plan, ctx: Context, e: dict[str, Any]) -> list[DecisionOption]:
    if e["what"] == "word":
        return [DecisionOption(id=w.lower(), label=w) for w in e["opts"]]
    if e["what"] == "number":
        return [DecisionOption(id=NUMBER, label=f"Type a number ≥ {int(e.get('min', 0))}", group="number")]
    from app.rules.effects import _choice_options

    return _choice_options(plan, ctx, e["what"])


def _label(e: dict[str, Any], value: str) -> str:
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
    ctx.setdefault("gc", {})[e["as"]] = {"order": order, "i": 0, "ballots": [], "secret": bool(e.get("secret"))}
    return _ask(plan, ctx, e)


def _ask(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    from app.rules.plan import decide

    g = ctx["gc"][e["as"]]
    while g["i"] < len(g["order"]):
        pid = g["order"][g["i"]]
        options = _options(plan, ctx, e) if pid in plan.live() else []
        if not options:  # (800.4a: a player who left the game chooses nothing)
            g["i"] += 1
            continue
        known = "" if g["secret"] or not g["ballots"] else " — chosen: " + ", ".join(f"{plan.name(p)} {_label(e, v)}" for p, v in g["ballots"])
        decide(plan, player=pid, kind="choose_one",
               prompt=f"{ctx.get('name') or 'Choose'}: choose {e.get('say') or e['what']}{' (secret)' if g['secret'] else ''}{known}",
               options=options, resume={"step": "gc_choose", "ctx": ctx, "e": e, "rest": [], "picked": []})  # (rest, picked: engine._settle_decision)
        return False
    return _finish(plan, ctx, e)


def resume(plan: Plan, d: Decision, chosen: list[str]) -> None:
    from app.rules.effects import continue_effects

    ctx, e = d.resume["ctx"], d.resume["e"]  # type: ignore[index]
    g = ctx["gc"][e["as"]]
    pid = g["order"][g["i"]]
    g["i"] += 1
    if chosen:  # (none: the chooser left the game, 800.4)
        g["ballots"].append([pid, chosen[0]])
        if not g["secret"]:
            plan.note(f"{plan.name(pid)} chooses {_label(e, chosen[0])}", actor=pid)  # 101.4b
    if _ask(plan, ctx, e):
        continue_effects(plan, ctx)


def _finish(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """Everyone has chosen: reveal a secret choice, bind each value's players, bind the later instructions' "chosen this way"."""
    from app.rules import context

    g = ctx["gc"][e["as"]]
    g["ballots"] = [b for b in g["ballots"] if b[0] in plan.live()]
    if g["secret"] and g["ballots"]:
        plan.note("The choices are revealed: " + "; ".join(f"{plan.name(p)} chose {_label(e, v)}" for p, v in g["ballots"]))
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
    if c["is"] == "all":  # "if each opponent chose silence"
        return bool(ballots) and values == {c["value"]}
    if c["is"] == "mixed":  # neither of the "each opponent chose …" cases
        return bool(ballots) and not (len(values) == 1 and values <= set(c["values"]))
    if c["is"] == "you":  # "If you are one of those players": the controller is among the players bound as ``name:set``
        from app.rules import context

        return ctx["controller"] in context.players(plan, ctx, f"{c['as']}:{c['set']}")
    return False


PRIMITIVES = {"gc_choose": choose, "gc_each": each, "gc_extremes": extremes}
RESUME = {"gc_choose": resume}


# -- reading the wording ----------------------------------------------------------------------------------------
_GATE = re.compile(r"\b(?:secretly|[Ee]ach (?:player|opponent) chooses)\b")
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
    if " piles" in body:  # -- piles (wave 53D) -- 700.3 (app/rules/pile_groups.py)
        from app.rules import pile_groups

        return pile_groups.bind(body, parse, split_sentences)
    if _GATE.search(body) is None:
        return None
    text = body.strip()
    for recipe in (_chosen_type, _words, _numbers, _chosen_objects):
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
_STICK = ("Each player chooses a party from among creatures they control, then sacrifices the rest.",)
_BALANCE = re.compile(r"^Each player chooses a number of (?P<k>lands|permanents) they control equal to the number of (?P=k) controlled by the player who controls the "
                      r"fewest, then sacrifices the rest\. (?P<tail>Players sacrifice creatures and discard cards the same way|Players discard cards and sacrifice "
                      r"creatures the same way|Each player discards cards the same way)\.$")
_GRUDGE = "Each opponent chooses a permanent they control that shares a card type with the sacrificed permanent and sacrifices it."
_MANIFOLD = ("Reveal the top ten cards of your library.", "Starting with the next opponent in turn order, each opponent chooses a different nonland card from "
             "among them.", "Put the chosen cards into your hand and the rest on the bottom of your library in a random order.")


def _key(phrase: str) -> str | None:
    from app.rules import selectors

    sel = selectors.parse(phrase)
    return None if sel is None else sel.key()


def _chosen_objects(text: str, parse: Any, split_sentences: Any) -> tuple[list[dict[str, Any]], Any, bool] | None:
    sentences = split_sentences(text)
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

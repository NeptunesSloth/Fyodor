"""-- rolling dice (wave 12A) -- "Roll a d20." (Ancient Gold Dragon), "Roll a six-sided die." (Vegetation Abomination), "Roll two
d12 and choose one result." (Reckless Endeavor), with the result as an amount: "equal to the result", "that result", "the other
result". Researched against CR 2026-09-25, 706.

* 706.1a: a dN has N equally likely outcomes, 1 to N. The table's recorded "roll" action is one randomizer (the result is in the
  history, so a replay or a reload reproduces it): app/game/actions.py ``Roll``.
* 706.2: the natural result is the number rolled; no modifier exists unless an effect makes one (not read: see below).
* 706.4: an ability without a results table says in its text how the result is used; here as an amount, read from this
  resolution's own roll (``ctx["die"]``; ``ctx["die_other"]`` for the other die of "choose one result": the roller chooses).

-- wave 13E -- "Whenever you roll one or more dice" is a trigger event (a "designation" event, counter "roll", once per roll of
any number of dice; its highest result rides along); the results themselves are not read by a trigger yet.

-- wave 24B -- more of 706. "Roll three six-sided dice." / "Roll X six-sided dice." (706.1: the effect says how many; ``ctx["dice"]`` holds
the results, "the total of those results", "for each even / odd / different result" read them), and the dice as events: every die rolled
is a ``designation`` event (counter "roll_die") with its result after modifiers, its natural result, its size and which of the turn's
dice it is, so "Whenever you roll a 6" / "a 4 or higher" / "your third die each turn" / "a die's highest natural result" trigger per die
(each die is a roll, 706.2; "one or more dice" stays one event per roll) and "If the roll was 4 or higher" reads the die's own result.

"If you would roll one or more dice, instead roll that many dice plus one and ignore the lowest roll." (Wyll, Pixie Guide, Barbarian Class) is
the static ``roll_extra`` (614.1a): ``roll_extras`` counts the player's permanents with it; the extra dice are rolled and the lowest rolls
are ignored (706.6: a roll that never happened: no trigger, not counted as one of the turn's dice).

Refused (manual): rerolls (706.2b), modifiers of a roll ("and add"), rolling for each player, a roll that is part of a cost, a result used by
a reflexive "When you do" ability, "the next time target player would roll" (a one-shot replacement).
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from app.game.errors import ActionError
from app.game.rules_state import DecisionOption
from app.rules import values
from app.rules.plan import decide

if TYPE_CHECKING:
    from app.rules.plan import Plan

Context = dict[str, Any]
STEP = "roll_choose"
_SIDES = {"four": 4, "six": 6, "eight": 8, "ten": 10, "twelve": 12, "twenty": 20}
_ONE = re.compile(r"^roll (?:a d(?P<n>\d+)|a (?P<w>four|six|eight|ten|twelve|twenty)-sided die)(?: and (?P<op>add|subtract) (?P<v>.+))?$")
_TWO = re.compile(r"^roll two d(?P<n>\d+) and choose one result$")
_COUNTS = {"two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}
_MANY = re.compile(r"^roll (?P<c>two|three|four|five|six|seven|eight|nine|ten|X) (?:d(?P<n>\d+)|(?P<w>four|six|eight|ten|twelve|twenty)-sided dice)$")
_RESULT = {"the result": "result", "that result": "result", "the other result": "other",
           "the total of those results": "total", "the total of the results": "total"}


def _one(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    from app.rules import scripts

    sides = int(m["n"]) if m["n"] else _SIDES[m["w"]]
    effect: dict[str, Any] = {"do": "roll", "sides": sides, "count": 1}
    if m["op"]:  # (wave 24B) 706.2: "Roll a d20 and add the number of cards in your hand": a modifier of the natural result
        v = values.parse_count(m["v"])
        if v is None or isinstance(v, int):
            raise scripts._NoMatch
        effect["mod"] = {"op": "+" if m["op"] == "add" else "-", "v": v}
    return ([effect] if 2 <= sides <= 1000 else []), None


def _two(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    return ([{"do": "roll", "sides": int(m["n"]), "count": 2, "choose": True}] if 2 <= int(m["n"]) <= 1000 else []), None


def _many(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    sides = int(m["n"]) if m["n"] else _SIDES[m["w"]]
    count: Any = {"x": 1} if m["c"] == "X" else _COUNTS[m["c"]]
    return ([{"do": "roll", "sides": sides, "count": count}] if 2 <= sides <= 1000 else []), None


TEMPLATES: list[tuple[re.Pattern[str], Any]] = [(_ONE, _one), (_TWO, _two), (_MANY, _many)]


def amount(phrase: str) -> dict[str, Any] | None:
    """"the result" / "that result" / "the other result" → the value ``{"die": "result" | "other"}``; (wave 24B) "the total of those
    results" → ``{"die": "total"}``, "the number of even / odd / different results" → ``{"dice": "even" | "odd" | "different"}``."""
    which = _RESULT.get(phrase)
    if which:
        return {"die": which}
    m = re.fullmatch(r"(?:the number of )?(even|odd|different) results?", phrase)
    return {"dice": m[1]} if m else None


def count_of(ctx: Context, kind: str) -> int:
    """How many of this resolution's dice show an even / odd result, or how many different results there are."""
    dice = [int(r) for r in ctx.get("dice") or []]
    return len(set(dice)) if kind == "different" else sum(1 for r in dice if r % 2 == (0 if kind == "even" else 1))


_AT = re.compile(r"^the result is (?P<n>\d+) or (?P<c>less|more|greater)$")
_BETWEEN = re.compile(r"^the result is (?:(?P<lo>\d+) to (?P<hi>\d+)|(?P<one>\d+))$")  # (the results table's rows, wave 16B)
_ROLLED = re.compile(r"\broll a (?:d\d+|\w+-sided die)\b.*\bthe result is\b", re.I)


_ORDINALS = {"first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "sixth": 6, "seventh": 7, "eighth": 8, "ninth": 9, "tenth": 10}
_DIE = re.compile(r"you roll (?:a die|an? (?P<a>\d+)(?: or (?:(?P<b>\d+)|(?P<c>higher|greater|more|lower|less|fewer)))?"
                  r"|your (?P<nth>first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth) die each turn"
                  r"|a die's (?P<hi>highest natural result))")
_ROLL_WAS = re.compile(r"the roll was (?P<n>\d+) or (?P<c>higher|greater|more|lower|less|fewer)")


def event_condition(text: str) -> dict[str, Any] | None:
    """-- dice (wave 24B) -- "you roll a 6" / "a 1 or 2" / "a 4 or higher" / "a die" / "your third die each turn" / "a die's highest natural
    result": one trigger per die (706.2: every die is a roll)."""
    m = _DIE.fullmatch(text)
    if m is None:
        return None
    out: dict[str, Any] = {"event": "roll_die", "subject": "player", "player": "you"}
    if m["a"]:
        a = int(m["a"])
        if m["b"]:
            out["in"] = [a, int(m["b"])]
        elif m["c"]:
            out["min" if m["c"] in ("higher", "greater", "more") else "max"] = a
        else:
            out["in"] = [a]
    elif m["nth"]:
        out["nth"] = _ORDINALS[m["nth"]]
    elif m["hi"]:
        out["highest"] = True
    return out


def die_matches(cond: dict[str, Any], info: dict[str, Any]) -> bool:
    """Is this die (its fact: ``amount`` the result, ``natural``, ``sides``, ``nth``) the one the trigger asks about?"""
    r = int(info.get("amount") or 0)
    return ("in" not in cond or r in cond["in"]) and ("min" not in cond or r >= cond["min"]) and ("max" not in cond or r <= cond["max"]) \
        and (not cond.get("nth") or info.get("nth") == cond["nth"]) \
        and (not cond.get("highest") or int(info.get("natural") or 0) == int(info.get("sides") or -1))


def condition(text: str) -> dict[str, Any] | None:
    """"the result is 3 or less" / "… 4 or greater" → a comparison of this resolution's roll (706.4); (wave 24B) "the roll was 4 or
    higher": the die a roll trigger is about."""
    if (w := _ROLL_WAS.fullmatch(text)) is not None:
        return {"value": {"event_amount": 1, "of": "roll"}, "op": ">=" if w["c"] in ("higher", "greater", "more") else "<=", "n": int(w["n"])}
    m = _AT.fullmatch(text)
    if m is None and (b := _BETWEEN.fullmatch(text)) is not None:  # -- static_other sweep (wave 16B) -- one row of a results table (706.3)
        lo, hi = int(b["lo"] or b["one"]), int(b["hi"] or b["one"])
        return {"all": [{"value": {"die": "result"}, "op": ">=", "n": lo}, {"value": {"die": "result"}, "op": "<=", "n": hi}]}
    return {"value": {"die": "result"}, "op": "<=" if m["c"] == "less" else ">=", "n": int(m["n"])} if m else None


# -- static_other sweep (wave 16B) -- 706.3: a results table ("Roll a d20. / 1—9 | You gain 1 life. / 10—19 | You gain 2 life. / 20 |
# You gain 5 life."): the ability reads the die's result and does what the row that holds it says. Read as the same text with each
# sentence of each row under "If the result is lo to hi," — the conditional sentences of 706.4 — only when the rows are exactly the
# die's results, each once (an unfinished table stays manual).
ROW = re.compile(r"(?:^|(?<=[.!?] ))(?P<lo>\d+)(?:[—–-](?P<hi>\d+)|(?P<plus>\+)| (?P<less>or less))? \| ")
_SIDES_IN = re.compile(r"\broll a (?:d(?P<n>\d+)|(?P<w>four|six|eight|ten|twelve|twenty)-sided die)\b")


def rows_in_text(text: str) -> bool:
    return ROW.search(text) is not None


def rewrite(body: str) -> str:
    rows = list(ROW.finditer(body))
    if not rows:
        return body
    head = body[: rows[0].start()].strip()
    roll = _SIDES_IN.search(head.lower())
    if roll is None or head.lower().count("roll ") != 1 or not head.endswith("."):
        return body
    sides = int(roll["n"]) if roll["n"] else _SIDES[roll["w"]]
    top = 10**6 if re.search(r"\band add\b", head, re.IGNORECASE) else sides  # (wave 24B: "Roll a d20 and add …": the last row may go on, "15+")
    from app.rules.oracle import split_sentences

    spans: list[tuple[int, int, str]] = []
    out = [head]
    for k, m in enumerate(rows):
        end = rows[k + 1].start() if k + 1 < len(rows) else len(body)
        lo = 1 if m["less"] else int(m["lo"])
        hi = int(m["lo"]) if m["less"] else int(m["hi"]) if m["hi"] else top if m["plus"] else int(m["lo"])
        spans.append((lo, hi, ""))
        for s in split_sentences(body[m.end():end].strip()):
            out.append(f"If the result is {lo} to {hi}, {s[:1].lower()}{s[1:]}")
    spans.sort()
    if [s[0] for s in spans][0] != 1 or spans[-1][1] != top or any(b[0] != a[1] + 1 for a, b in zip(spans, spans[1:], strict=False)):
        return body
    return " ".join(out)


_FOR_EACH = re.compile(r"(?:^|(?<=[.!?] ))For each (?P<k>even|odd|different) result, (?P<do>put [^.]+)\.")


def plain(body: str) -> str:
    """"Roll a six-sided die. If the result is 3 or less, you lose that much life.": "that much" is the result. (Wave 24B) "For each even
    result, put two -1/-1 counters on that creature." is that instruction with its multiplier after it (as the grammar reads it)."""
    if re.search(r"\broll (?:a |two |three |four |five |six |seven |eight |nine |ten |X )", body, re.IGNORECASE):
        body = _FOR_EACH.sub(lambda m: f"{m['do'][:1].upper()}{m['do'][1:]} for each {m['k']} result.", body)
        body = re.sub(r"\b([Ss])cry a number of cards equal to (the|that) result\b", r"\1cry X, where X is \2 result", body)
    return re.sub(r"\bthat much (life|damage)", r"\1 equal to the result", body) if _ROLLED.search(body) else body


def evaluate(ctx: Context, which: str) -> int:
    if which == "total":  # (wave 24B) 706.4: the text says how the results are used
        return max(0, sum(int(r) for r in ctx.get("dice") or []))
    return max(0, int(ctx.get("die" if which == "result" else "die_other") or 0))


_EXTRA = "If you would roll one or more dice, instead roll that many dice plus one and ignore the lowest roll."


def static_definition(text: str) -> dict[str, Any] | None:
    """-- dice (wave 24B) -- 614.1a / 706.6: "If you would roll one or more dice, instead roll that many dice plus one and ignore the lowest
    roll." (Wyll, Pixie Guide's "Grant an Advantage", Barbarian Class), read at the roll (``roll_extras``)."""
    return {"kind": "static", "static": "roll_extra", "effects": []} if text.strip() == _EXTRA else None


def roll_extras(plan: Plan, pid: str) -> int:
    """How many "roll that many dice plus one and ignore the lowest roll" effects of ``pid``'s permanents apply to their roll. Each one is
    applied to the roll as the one before it left it (616.1: they are all the same replacement; a Class level they haven't reached has
    no ability, 716.2a): with two, two more dice are rolled and the two lowest rolls ignored: as many dice are kept as were asked for."""
    from app.rules import scripts
    from app.rules.replace import conditional_lines

    n = 0
    for c in plan.state.cards.values():
        if c.controller != pid or not c.zone.endswith(":battlefield") or c.face_down or not plan.in_game(c) or plan.manual(c):
            continue
        ch = plan.ch(c)
        skip = conditional_lines(ch)
        n += sum(1 for i, d in scripts.definitions(ch).items() if i not in skip and d.get("static") == "roll_extra")
    return n


def roll(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    import secrets

    from app.game.rules_state import emit, turn_log_now
    from app.rules import effects

    if plan.rng is None:
        plan.rng = secrets.SystemRandom()  # (the result is recorded on the step: the history replays it, not the generator)
    pid = ctx["controller"]
    n = max(0, int(effects._amount(plan, ctx, e["count"])))
    extra = roll_extras(plan, pid) if n > 0 else 0  # 614.1a: "would roll one or more dice"
    results: list[int] = []
    while len(results) < n + extra:  # (one roll step holds up to 100 dice)
        step = min(100, n + extra - len(results))
        done = plan.do({"type": "roll", "sides": e["sides"], "count": step}, actor=pid)
        results += list(done.r.results)  # type: ignore[union-attr]
    for lowest in sorted(results)[:extra]:  # 706.6: an ignored roll never happened (tied lowest rolls are the same number: no choice to make)
        results.remove(lowest)
    if extra:
        plan.note(f"{plan.name(pid)} ignores the lowest {'roll' if extra == 1 else f'{extra} rolls'}")
    ctx["dice"] = results
    if not results:
        ctx["die"] = ctx["die_other"] = 0
        return True
    log = turn_log_now(plan.state)
    naturals = list(results)
    if e.get("mod"):  # 706.2: the result is the natural result after the modifiers (one die: an instruction with a modifier asks for one)
        delta = int(effects._amount(plan, ctx, e["mod"]["v"]))
        results = [r + delta if e["mod"]["op"] == "+" else r - delta for r in results]
        ctx["dice"] = results
    for k, r in enumerate(results):  # 706.2: each die is a roll; -- wave 24B -- one event each (the one-or-more event follows)
        emit(plan.state, "designation", counter="roll_die", player=pid, amount=r, natural=naturals[k], sides=e["sides"],
             nth=(log.rolled.get(pid, 0) if log is not None else 0) + k + 1)
    if log is not None:
        log.rolled[pid] = log.rolled.get(pid, 0) + len(results)
    emit(plan.state, "designation", counter="roll", player=pid, amount=max(results))  # "Whenever you roll one or more dice"
    if not e.get("choose") or results[0] == results[-1]:
        ctx["die"], ctx["die_other"] = results[0], results[-1]
        return True
    decide(plan, player=pid, kind="choose_one", prompt=f"{ctx.get('name') or 'Roll'}: choose one result",
           options=[DecisionOption(id=str(i), label=str(r)) for i, r in enumerate(results)],
           resume={"step": STEP, "ctx": ctx, "results": results})
    return False


def resume(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import effects

    r = d.resume
    if len(chosen) != 1 or chosen[0] not in ("0", "1"):
        raise ActionError("Choose one of the results")
    results, ctx = r["results"], r["ctx"]
    ctx["die"], ctx["die_other"] = results[int(chosen[0])], results[1 - int(chosen[0])]
    plan.note(f"{plan.name(d.player)} chooses {ctx['die']}")
    effects.continue_effects(plan, ctx)


def refs_ok(effects: list[dict[str, Any]]) -> bool:
    """An amount from a roll only after a roll of the same ability."""
    rolled = False
    for e in effects:
        text = str(e)
        if "'do': 'roll'" in text:
            rolled = True
        elif ("'die':" in text or "'dice':" in text) and not rolled:
            return False
    return True


PRIMITIVES = {"roll": roll}

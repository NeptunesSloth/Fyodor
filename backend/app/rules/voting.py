# -- voting (wave 18C) --
"""Voting: "Starting with you, each player votes for death or torture. If death gets more votes, …" (Tyrant's Choice, Bite of the
Black Rose, Plea for Power), "…votes for strength or numbers. Put a +1/+1 counter on this creature for each strength vote …"
(Lieutenants of the Guard, Orchard Elemental, Capital Punishment, Emissary Green, Tivit), "…votes for a nonland permanent you don't
control. Exile each permanent with the most votes or tied for most votes." (Council's Judgment, Custodi Squire) and the secret
"Each player secretly votes for up to one creature, then those votes are revealed." (Vault 11). Researched against CR 2026-09-25.

* 701.38a: to vote, each player, starting with a specified player and proceeding in turn order, chooses one of the listed choices;
  701.38b: the choices may be objects or words with no rules meaning (207.2c: "Will of the council", "Council's dilemma" and
  "Secret council" are ability words); 701.38c: only an actual vote is a vote.
* 701.38d: an effect that gives a player several votes ("While voting, you get an additional vote", Brago's Representative; "you
  may vote an additional time", Ballot Broker, Tivit): the votes all happen at the same time the player would otherwise have voted;
  they may be for different choices or the same one. A "may" extra vote is offered after the player's other votes.
* A vote is public: it is logged as it is made, so later voters see it. A secret vote ("secretly votes … then those votes are
  revealed") is a private decision of each voter, in the same order; nothing is logged or shown until every vote is in, and then all
  are revealed at once. The votes cast so far live only in the server-side resolution context of the pending decision.
* "gets more votes" is strictly more than every other choice; "or the vote is tied" adds a tie for the most (any tie, as the cards
  with two choices need). "each X with the most votes or tied for most votes" is every object with the highest count (at least one
  vote). "for each X vote" does the instruction once per vote for X (608.2c, in order). The instruction after "for each" must be a
  plain, target-free, mandatory one; anything else keeps the card manual.

* (wave 47B) A vote for a player ("votes for a player" Círdan; "for another player" Mob Verdict, nobody votes for themself): the choices are the
  players in the game as the vote begins; "Each player draws a card for each vote they received." / "For each vote an opponent received, …" do the
  instruction for each player (turn order, 101.4) once for each vote that player got (``vote_each``), "that player" being the one voted for.
  "Each player who received no votes may …" is a per-player filter (player_filter, ``{"votes": 0}``).

Not read (manual): "for each creature with one or more votes, … that many …" (Trap the
Trespassers), several-choice results that move cards between voters (Expropriate), a "this way" count of a repeated instruction
(Messenger Jays), "Whenever players finish voting" triggers and "You choose how each player votes" (Illusion of Choice).
"""

from __future__ import annotations

import copy
import json
import re
from typing import TYPE_CHECKING, Any

from app.game.rules_state import DecisionOption

if TYPE_CHECKING:
    from app.rules.plan import Plan

Context = dict[str, Any]
STATIC = "extra_vote"
NONE_LEFT = "__none__"
_HEAD = re.compile(r"^(?P<start>Starting with you, )?[Ee]ach player (?P<sec>secretly )?votes for (?P<what>.+?)"
                   r"(?P<rev>, then those votes are revealed)?\.(?: (?P<rest>.*))?$", re.DOTALL)
_WORD = re.compile(r"^[a-z][a-z']*(?: [A-Za-z][A-Za-z']*){0,2}$|^[A-Z][A-Za-z']*(?: [A-Za-z][A-Za-z']*){0,2}$")
_ARTICLE = re.compile(r"^(?:an? |another |up to |the |each |target )", re.I)
_EXTRA = re.compile(r"^While voting, you (?P<k>may vote an additional time|get an additional vote)\.(?: \(.*\))?$")
_FOR_EACH = re.compile(r"^For each (?P<w>[\w' ]+?) vote, (?P<e>.+)\.$")
_SUFFIX_EACH = re.compile(r"^(?P<e>.+?) for each (?P<w>[\w' ]+?) vote\.$")
_TWO_EACH = re.compile(r"^(?P<e1>.+?) for each (?P<w1>[\w' ]+?) vote and (?P<e2>.+?) for each (?P<w2>[\w' ]+?) vote\.$")
_SUBJECT = re.compile(r"^(?P<s>Each opponent|Each player|You|Target opponent) ")
_NUMBER_OF = re.compile(r"^(?P<e>.+?) a number of (?P<what>.+?) equal to (?P<twice>twice )?the number of (?P<w>[\w' ]+?) votes\.$")
_DRAW_NUMBER = re.compile(r"^(?:You )?[Dd]raw cards equal to the number of (?P<w>[\w' ]+?) votes\.$")
_LEADERS = re.compile(r"^(?P<pre>Otherwise, )?(?P<verb>[A-Za-z]+) each (?P<noun>[a-z ]+?) with the most votes or tied for most votes"
                      r"(?P<rest>[^.]*)\.$")
_EACH_RECEIVED = re.compile(r"^(?P<s>Each player|Each opponent) (?P<v>.+?) for each vote (?:they|that player) received\.$")
_FOR_RECEIVED = re.compile(r"^For each vote (?P<s>an opponent|you) received, (?P<e>.+)\.$")
_SCALED = ("add_counters", "create_token", "gain_life", "lose_life", "draw", "discard", "mill", "edict")
_COND = re.compile(r"^(?:(?P<w>[\w' ]+?) gets more votes(?P<tie> or the vote is tied)?|no (?P<none>[a-z ]+?) got votes)$")


TEMPLATES: list[tuple[re.Pattern[str], Any]] = [
    (re.compile(r"^you choose how each player votes this turn$"), lambda m: ([{"do": "vote_control"}], None)),
]


# -- reading the wording -------------------------------------------------------------------------
def static_definition(text: str) -> dict[str, Any] | None:
    m = _EXTRA.match(text.strip())
    return None if m is None else {"kind": "static", "static": STATIC, "mode": "get" if m["k"].startswith("get") else "may", "effects": []}


def split(body: str) -> dict[str, Any] | None:
    """The vote a body starts with: {"words": [...]} or {"sel": key, "upto": bool}, "secret", and the sentences after it."""
    body = body.strip()
    m = _HEAD.match(body[:1].upper() + body[1:])
    if m is None or bool(m["start"]) == bool(m["sec"]) or bool(m["sec"]) != bool(m["rev"]):
        return None  # (a public vote starts with you; a secret one is revealed afterwards)
    what, out = m["what"], {"secret": bool(m["sec"]), "rest": m["rest"] or ""}
    if what in ("a player", "another player"):  # -- random choices (wave 47B) -- votes for players
        return {**out, "players": True, "other": what == "another player"}
    if not _ARTICLE.match(what):
        words = [w for w in re.split(r", or |, | or ", what) if w]
        if len(words) < 2 or not all(_WORD.match(w) for w in words) or len({w.lower() for w in words}) != len(words):
            return None
        return {**out, "words": words}
    from app.rules import selectors

    upto = what.startswith("up to one ")
    phrase = re.sub(r"^(?:up to one |an? )", "", what)
    sel = selectors.parse(phrase) or selectors.parse_either(phrase)
    if sel is None or sel.player is not None or sel.zones not in (("battlefield",), ("graveyard",)) or sel.ability is not None:
        return None
    return {**out, "sel": sel.key(), "upto": upto, "zone": sel.zones[0]}


def _plain(found: Any) -> list[dict[str, Any]] | None:
    """The effects of an instruction repeated per vote: plain, target-free, mandatory, no bindings."""
    if found is None:
        return None
    inner, groups, optional = found
    if groups or optional or not inner or any(e.get("bind") or e.get("as") or e.get("did") for e in inner):
        return None
    if re.search(r'"ref_count"|"this_way"|"ref_amount"|"it"|"that_|"event_', json.dumps(inner)):
        return None
    return list(inner)


def _retarget(node: Any, name: str) -> bool:
    """Every "target" of the effects becomes the binding ``name`` (the objects the vote picked); False if there was none."""
    hit = False
    if isinstance(node, dict):
        if node.get("who") == "target":
            node["who"] = f"ref:{name}"
            hit = True
        for v in node.values():
            hit = _retarget(v, name) or hit
    elif isinstance(node, list):
        for v in node:
            hit = _retarget(v, name) or hit
    return hit


def bind(head: dict[str, Any], parse: Any, split_sentences: Any) -> tuple[list[dict[str, Any]], Any, bool] | None:
    """The effects of a voting body; ``parse`` reads one instruction (scripts._parse_effects)."""
    words = head.get("words")
    labels = list(words) if words else []
    opts = [w.lower() for w in labels]
    effects: list[dict[str, Any]] = [{"do": "vote", "secret": head["secret"], **(
        {"players": True, "other": head["other"]} if head.get("players") else {"opts": opts, "labels": labels} if words else
        {"sel": head["sel"], "upto": head["upto"], "as": "vote"})}]
    buffer: list[str] = []
    leaders = [False]

    def flush() -> bool:
        if not buffer:
            return True
        found = parse(" ".join(buffer))
        buffer.clear()
        if found is None or found[2] or not found[0] or (found[1] and not leaders[0]):
            return False
        if leaders[0] and not _retarget(found[0], "vote"):
            return False
        leaders[0] = False
        effects.extend(found[0])
        return True

    def repeat(word: str, text: str, scale: bool = True) -> bool:
        inner = _plain(parse(text[:1].upper() + text[1:].rstrip(".") + "."))
        if inner is None or not words or word.lower() not in opts:
            return False
        # "X for each W vote" is one instruction for all the votes (Capital Punishment ruling: the creatures are sacrificed at
        # once): its amount is multiplied (one event: Hardened Scales adds one counter, a life-gain trigger triggers once)
        one = scale and len(inner) == 1 and inner[0].get("do") in _SCALED and type(inner[0].get("n")) is int
        effects.extend([{"do": "vote_repeat", "choice": word.lower(), "skip": len(inner), **({"scale": True} if one else {})}, *inner])
        return True

    def received(who: str, text: str, scale: bool) -> bool:
        """-- random choices (wave 47B) -- the instruction (about "that player") once for each vote each player of ``who`` received."""
        from app.rules import scripts

        got = scripts.parse_effects(text[:1].upper() + text[1:].rstrip(".") + ".", None, event_player=True)
        if got is None or got[1] is not None or got[2] or not got[0] or not head.get("players") \
                or any(x.get("bind") or x.get("as") or x.get("did") for x in got[0]):  # (plain: target-free, mandatory, no bindings)
            return False
        inner = _vp(got[0])
        if inner is None:
            return False
        one = scale and len(inner) == 1 and inner[0].get("do") in _SCALED and type(inner[0].get("n")) is int
        effects.extend([{"do": "vote_each", "who": who, "skip": len(inner), "as": "vp", **({"scale": True} if one else {})}, *inner])
        return True

    for sentence in split_sentences(head["rest"]):
        if (m := _EACH_RECEIVED.match(sentence)) is not None:
            if not (flush() and received("each_player" if m["s"] == "Each player" else "each_opponent", f"that player {m['v']}", True)):
                return None
        elif (m := _FOR_RECEIVED.match(sentence)) is not None:
            if not (flush() and received("you" if m["s"] == "you" else "each_opponent", m["e"], False)):
                return None
        elif (m := _TWO_EACH.match(sentence)) is not None:
            e1, e2 = m["e1"], m["e2"]
            subject = _SUBJECT.match(e1)
            if e2[:1].islower() and subject is not None:  # "Each opponent sacrifices a creature … and discards a card …"
                e2 = f"{subject['s']} {e2}"
            if not (flush() and repeat(m["w1"], e1) and repeat(m["w2"], e2)):
                return None
        elif (m := _FOR_EACH.match(sentence)) is not None or (m := _SUFFIX_EACH.match(sentence)) is not None:
            if not (flush() and repeat(m["w"], m["e"], not sentence.startswith("For each "))):
                return None
        elif (m := _NUMBER_OF.match(sentence)) is not None:  # "Put a number of X equal to twice the number of W votes."
            what = m["what"] if m["twice"] else re.sub(r"\b(tokens|counters)\b", lambda t: t[1][:-1], m["what"], count=1)
            if not (flush() and repeat(m["w"], f"{m['e']} {'two' if m['twice'] else 'a'} {what}")):
                return None
        elif (m := _DRAW_NUMBER.match(sentence)) is not None:
            if not (flush() and repeat(m["w"], "Draw a card")):
                return None
        elif (m := _LEADERS.match(sentence)) is not None and "sel" in head:
            zone = " from your graveyard" if head["zone"] == "graveyard" else ""
            if any("target" in x for x in [*buffer, head["rest"]]):
                return None  # (the stand-in "target" below must be the only one)
            buffer.append(f"{m['pre'] or ''}{m['verb']} target {m['noun']}{zone}{m['rest']}.")
            leaders[0] = True
        else:
            buffer.append(sentence)
    if not flush():
        return None
    if any(name not in opts for name in _walk(effects)):  # every choice a condition names is one that was listed
        return None
    if "tied_or_more" in json.dumps(effects) and len(opts) != 2:
        return None  # ("or the vote is tied" is read for two choices: with more it would be a tie for what?)
    if any(x.get("do") == "vote_repeat" for x in effects) and not words:
        return None
    return effects, None, False


def _vp(node: Any) -> Any:
    """The effects of a per-vote instruction aimed at the player voted for: "that player" (read as the trigger event's) is the binding ``vp``;
    None if the instruction still names anyone else's event or target (stays manual)."""
    text = json.dumps(node)
    if "target" in text or '"it"' in text or "that_player" in text or "ref:e" in text:
        return None
    return json.loads(text.replace('"event_player"', '"ref:vp"').replace("controlled:event_player|", "controlled:ref:vp|"))


def _walk(node: Any) -> list[str]:
    out: list[str] = []
    if isinstance(node, dict):
        if node.get("vote") in ("more", "tied_or_more") and "w" in node:
            out.append(node["w"])
        for v in node.values():
            out += _walk(v)
    elif isinstance(node, list):
        for v in node:
            out += _walk(v)
    return out


# -- conditions ------------------------------------------------------------------------------------
def condition(text: str) -> dict[str, Any] | None:
    """"death gets more votes" / "torture gets more votes or the vote is tied" / "no creature got votes"."""
    m = _COND.fullmatch(text)
    if m is None:
        return None
    if m["none"]:
        return {"vote": "none"}
    return {"vote": "tied_or_more" if m["tie"] else "more", "w": m["w"].lower()}


def holds(ctx: Context, cond: dict[str, Any]) -> bool:
    tally = (ctx.get("vote") or {}).get("tally")
    if tally is None:
        return False
    if cond["vote"] == "none":
        return not any(tally.values())
    mine = tally.get(cond["w"], 0)
    others = [n for k, n in tally.items() if k != cond["w"]]
    best = max(others, default=0)
    return mine > best if cond["vote"] == "more" else mine >= best


# -- extra votes (701.38d) -----------------------------------------------------------------------
def extra_votes(plan: Plan, pid: str) -> tuple[int, int]:
    """(additional votes ``pid`` must cast, additional votes they may cast) from permanents they control."""
    from app.rules import scripts
    from app.rules.replace import conditional_lines

    must = may = 0
    for c in plan.state.cards.values():
        if not c.zone.endswith(":battlefield") or c.controller != pid or c.face_down or not plan.in_game(c) or plan.manual(c):
            continue
        ch = plan.ch(c)
        skip = conditional_lines(ch)
        for i, d in scripts.definitions(ch).items():
            if i not in skip and d.get("static") == STATIC:
                must, may = (must + 1, may) if d["mode"] == "get" else (must, may + 1)
    return must, may


# -- carrying it out -----------------------------------------------------------------------------------
def vote_control(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """"You choose how each player votes this turn.": until end of turn the chooser makes every vote (the latest such effect wins)."""
    plan.rules.vote_control.append([plan.state.turn.number, ctx["controller"]])
    return True


def _chooser(plan: Plan, voter: str) -> str:
    turn = plan.state.turn.number
    plan.rules.vote_control = [c for c in plan.rules.vote_control if c[0] == turn]
    return str(plan.rules.vote_control[-1][1]) if plan.rules.vote_control and plan.rules.vote_control[-1][1] in plan.live() else voter


def vote(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """701.38a: each player, starting with the ability's controller and proceeding in turn order, votes."""
    me = ctx["controller"]
    order = [me]
    while (nxt := plan.after(order[-1])) != me:
        order.append(nxt)
    if e.get("players"):  # -- random choices (wave 47B) -- the players in the game as the vote begins
        opts = list(plan.live())
        labels = [plan.name(p) for p in opts]
    elif "sel" in e:
        from app.rules import selectors

        opts = selectors.candidates(plan, selectors.from_key(e["sel"]), me, ctx.get("source_card"))
        labels = [plan.state.cards[c].name or "Card" for c in opts]
    else:
        opts, labels = list(e["opts"]), list(e["labels"])
    schedule: list[list[Any]] = []
    for p in order:
        if p not in plan.live():
            continue
        must, may = extra_votes(plan, p)
        schedule += [[p, False]] * (1 + must) + [[p, True]] * may
    ctx["vote"] = {"opts": opts, "labels": labels, "secret": bool(e.get("secret")), "schedule": schedule, "i": 0, "ballots": [], "other": bool(e.get("other"))}
    return _ask(plan, ctx, e)


def _ask(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    from app.rules.plan import decide

    v = ctx["vote"]
    while v["i"] < len(v["schedule"]):
        pid, extra = v["schedule"][v["i"]]
        pool = [(o, lab) for o, lab in zip(v["opts"], v["labels"], strict=True) if not (v.get("other") and o == pid)]  # (nobody votes for themself: "another player")
        if not pool or pid not in plan.live():  # (800.4a: a player who left the game doesn't vote)
            v["i"] += 1
            continue
        chooser = _chooser(plan, pid)
        if extra and chooser != pid and v.get("taken") != v["i"]:
            # Illusion of Choice ruling: the voter decides whether to take a "may" additional vote; the chooser picks it
            decide(plan, player=pid, kind="confirm", prompt="Vote an additional time?",
                   options=[DecisionOption(id="yes", label="Yes"), DecisionOption(id="no", label="No")],
                   resume={"step": "vote", "ctx": ctx, "e": e, "extra": True})
            return False
        if v.get("taken") == v["i"]:
            extra = False
        options = [DecisionOption(id=o, label=lab) if "sel" not in e else DecisionOption(id=o, label=lab, card_id=o) for o, lab in pool]
        optional = extra or bool(e.get("upto"))
        if optional and "sel" not in e:
            options.append(DecisionOption(id=NONE_LEFT, label="Don't vote again"))
        decide(plan, player=chooser, kind="choose_cards" if optional and "sel" in e else "choose_one",
               prompt="Vote" + (f" for {plan.name(pid)}" if chooser != pid else "") + (" (secret)" if v["secret"] else "")
               + (": " + " or ".join(lab for _, lab in pool) if "sel" not in e else ""),
               options=options, min_choices=0 if optional and "sel" in e else 1, max_choices=1,
               resume={"step": "vote", "ctx": ctx, "e": e})
        return False
    return _finish(plan, ctx, e)


def resume(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules.effects import continue_effects

    ctx, e = d.resume["ctx"], d.resume["e"]
    v = ctx["vote"]
    pid, _ = v["schedule"][v["i"]]
    if d.resume.get("extra"):
        if chosen == ["yes"]:
            v["taken"] = v["i"]
        else:
            v["i"] += 1
        chosen = []
    elif d.player != pid and d.player not in plan.live() and pid in plan.live():
        chosen = []  # (the player choosing the votes left the game: the voter votes for themself, 800.4a)
    else:
        v["i"] += 1
    if chosen and chosen[0] != NONE_LEFT:
        v["ballots"].append([pid, chosen[0]])
        if not v["secret"]:
            plan.note(f"{plan.name(pid)} voted for {_label(plan, v, chosen[0])}", [chosen[0]] if "sel" in e else [])
    if _ask(plan, ctx, e):
        continue_effects(plan, ctx)


def _label(plan: Plan, v: dict[str, Any], choice: str) -> str:
    return v["labels"][v["opts"].index(choice)]


def _finish(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """Everyone has voted: reveal a secret vote, count, and bind the leading objects of an object vote."""
    v = ctx["vote"]
    if v["secret"] and v["ballots"]:
        plan.note("The votes are revealed: " + "; ".join(f"{plan.name(p)} voted for {_label(plan, v, c)}" for p, c in v["ballots"]),
                  [c for _, c in v["ballots"]] if "sel" in e else [])
    tally = {o: 0 for o in v["opts"]}
    for _, choice in v["ballots"]:
        tally[choice] += 1
    v["tally"] = tally
    if "sel" in e:
        from app.rules import context

        top = max(tally.values(), default=0)
        context.bind_objects(plan, ctx, e["as"], [o for o, n in tally.items() if top and n == top])
    return True


def repeat(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """The next ``skip`` instructions once for each vote for the choice (none: they don't happen)."""
    effects, at, n = ctx["effects"], ctx["next"], int(e["skip"])
    times = int(ctx["vote"]["tally"].get(e["choice"], 0))
    if times == 0:
        ctx["next"] = at + n
        return True
    if e.get("scale"):
        effects[at] = {**effects[at], "n": int(effects[at]["n"]) * times}
        return True
    block = effects[at:at + n]
    effects[at + n:at + n] = [copy.deepcopy(x) for _ in range(times - 1) for x in block]
    return True


def each(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """-- random choices (wave 47B) -- the next ``skip`` instructions, for each player of ``who`` in turn order (101.4), once for each vote that player
    received (a counted instruction once, with its amount multiplied), the player bound as ``vp``; a player with no votes gets none."""
    from app.rules.effects import _players

    effects, at, n = ctx["effects"], ctx["next"], int(e["skip"])
    block, who, tally = effects[at:at + n], _players(plan, ctx, e["who"]), ctx["vote"]["tally"]
    out: list[dict[str, Any]] = []
    for p in (q for q in plan.apnap() if q in who):
        k = int(tally.get(p, 0))
        if k and e.get("scale"):
            out += [{"do": "vote_bind", "player": p, "as": e["as"]}, {**block[0], "n": int(block[0]["n"]) * k}]
        elif k:
            out += [{"do": "vote_bind", "player": p, "as": e["as"]}, *(copy.deepcopy(x) for _ in range(k) for x in block)]
    effects[at:at + n] = out
    return True


def bind_player(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    from app.rules import context

    context.bind_players(ctx, e["as"], [e["player"]] if e["player"] in plan.live() else [])
    return True


PRIMITIVES = {"vote": vote, "vote_repeat": repeat, "vote_control": vote_control, "vote_each": each, "vote_bind": bind_player}
RESUME = {"vote": resume}

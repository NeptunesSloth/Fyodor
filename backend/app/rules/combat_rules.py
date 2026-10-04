"""-- combat (wave 5C) -- Attack costs, attack limits, block restrictions about the attacker's controller, attack
requirements from effects, additional combat phases and tokens entering attacking each opponent. Researched against
the Comprehensive Rules of 2026-09-25 (data/rules/comprehensive_rules/).

* Attack costs (508.1d, 508.1h-j): "Creatures can't attack you unless their controller pays {2} for each creature
  they control that's attacking you." (Propaganda, Ghostly Prison, Windborn Muse, Elephant Grass). A rule on each
  creature the subject names (``attack_tax:<player>:<n>:<source>``, one per source: two Propagandas cost twice).
  The attacking player declares, then the total cost is determined and locked in (508.1h), mana abilities may be
  activated (508.1i) and everything is paid at once (508.1j); if it can't be paid the declaration is illegal and is
  made again. The text counts *every* creature attacking that player once any creature the subject names does
  (Elephant Grass's black creatures can't attack you at all, so the count is the same). Attacking a planeswalker the
  player controls costs nothing. 508.1d: nobody is required to pay, so a requirement never forces a paid attack.
* "No more than two creatures can attack you each combat." (Crawlspace, 508.1c): a restriction on the declaration.
  With such a limit the requirements (508.1d) are weighed over the whole declaration (the most requirements any
  legal declaration obeys), not creature by creature.
* "Creatures with power less than ~'s power can't block creatures you control." (Champion of Lambholt) and
  "Creatures with flying can't block creatures you control." (Bower Passage): restrictions on blockers (509.1b),
  read against the attacker's controller as the block is declared (``cant_block_ctrl[_power]``).
* "Creatures your opponents control attack this turn if able." (Bident of Thassa), "Target creature attacks this
  turn if able.", and Kardur's "until your next turn, creatures your opponents control attack each combat if able
  and attack a player other than you if able": rule-modifying effects (611.2c: creatures that arrive later are
  affected too), requirements weighed like goad's (508.1d, ``attack_other_than:<player>``).
* "After this [main] phase, there is an additional combat phase [followed by an additional main phase]." (500.8):
  the new phases go directly after the current one, the most recently created first. The turn's remaining
  phases are kept as a queue (``RulesState.extra_phases``) ending with the phase that would have come next.
* "for each opponent, create a … token that's tapped and attacking that player [or a planeswalker they
  control]" (Adeline) and "Whenever you attack a player, create … tapped and attacking that player." (508.4).
* "Remove target attacking creature you control from combat" (Reconnaissance, 506.4), Maze of Ith's "Prevent all combat
  damage that would be dealt to and dealt by that creature this turn" (615), "if it's the first combat phase of the
  turn" (Finest Hour, Karlach: ``RulesState.combats``), "creatures that attacked this turn" (Relentless Assault: the
  wave 4D attackers log), and doubling power and toughness (701.10b-c, layer 7c: Unnatural Growth, Bulk Up).

Refused (manual): attack costs sized by a count or covering planeswalkers (Sphere of Safety), "attacks a player each
combat" (Nahiri), "Only land creatures can attack during that combat phase" (Bumi), additional phases scheduled for a
later phase ("After the second main phase this turn", World at War), "can't attack a player it has already attacked
this turn" (Port Razer), costs to block (Heat Wave's second line).
"""

from __future__ import annotations

import re
from functools import cache
from typing import TYPE_CHECKING, Any

from app.game.rules_state import DecisionOption
from app.rules.plan import decide

if TYPE_CHECKING:
    from app.game.state import CardInstance, GameState
    from app.rules.characteristics import CardInfo, Characteristics
    from app.rules.plan import Plan

Definition = dict[str, Any]
Effects = list[dict[str, Any]]

TAX = "attack_tax"
TAX_PW = "attack_tax_pw"  # (also attacking a planeswalker the player controls)
OTHER_THAN = "attack_other_than"
CANT_BLOCK_CTRL = "cant_block_ctrl"
CANT_BLOCK_CTRL_POWER = "cant_block_ctrl_power"
LIMIT = "attack_limit"
LIMIT_ALL = "attack_limit_all"  # -- static_other sweep (wave 16B) -- "No more than one creature can attack each combat." (Silent Arbiter)
BLOCK_LIMIT_ALL = "block_limit_all"  # … "can block each combat": the creatures that block, all players together
_NUMBERS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5}


# -- statics ---------------------------------------------------------------------------------------------------------
_TAX_RE = re.compile(r"(?P<sub>.+?) can't attack you unless their controller pays (?P<cost>(?:\{[^}]+\})+) for each "
                     r"creature they control that's attacking you(?:, where X is (?P<x>.+))?\.")
_TAX_PW_RE = re.compile(r"(?P<sub>.+?) can't attack you or planeswalkers you control unless their controller pays "
                        r"(?P<cost>(?:\{[^}]+\})+) for each of those creatures(?:, where X is (?P<x>.+))?\.")
_CTRL_RE = re.compile(r"(?P<sub>.+?) can't block creatures you control\.")
_POWER_SUB = re.compile(r"Creatures with power less than (?:~|this creature)'s power")
_LIMIT_RE = re.compile(r"No more than (?P<n>one|two|three|four|five) creatures? can attack you each combat\.")
_LIMIT_ALL_RE = re.compile(r"No more than (?P<n>one|two|three|four|five) creatures? can (?P<v>attack|block) each combat\.")


def static_definition(text: str) -> Definition | None:
    """One static ability (the card's own name written as ~) of this module, or None."""
    from app.rules import statics

    t = text.strip()
    m = _LIMIT_RE.fullmatch(t)
    if m:
        return {"kind": "static", "static": LIMIT, "n": _NUMBERS[m["n"]], "effects": []}
    m = _LIMIT_ALL_RE.fullmatch(t)
    if m:
        return {"kind": "static", "static": LIMIT_ALL if m["v"] == "attack" else BLOCK_LIMIT_ALL, "n": _NUMBERS[m["n"]], "effects": []}
    m = _TAX_RE.fullmatch(t) or _TAX_PW_RE.fullmatch(t)
    if m:
        from app.rules import mana as M

        who, _ = statics._subject(m["sub"])
        cost = M.parse_cost(m["cost"])
        x_value = None
        if m["x"] is not None or cost.x:  # "{X} …, where X is the number of enchantments you control" (Sphere of Safety)
            from app.rules import values

            x_value = values.parse_count(m["x"] or "")
            if m["cost"] != "{X}" or x_value is None:
                return None
        if who is None or who in ("self", "attached") or cost.unsupported or (cost.is_free and not cost.x) \
                or ":" in m["cost"]:
            return None
        name = TAX if m.re is _TAX_RE else TAX_PW
        out = statics._definition(who, None, [], rules=[f"{name}:@you:{m['cost']}:@src"])
        if x_value is not None:
            out["tax_x"] = x_value  # (read as the total cost is determined: 508.1h)
        return out
    m = _CTRL_RE.fullmatch(t)
    if m:
        if _POWER_SUB.fullmatch(m["sub"]):
            who, _ = statics._subject("Creatures")
            rule = f"{CANT_BLOCK_CTRL_POWER}:@you:@src"
        else:
            who, _ = statics._subject(m["sub"])
            rule = f"{CANT_BLOCK_CTRL}:@you"
        if who is None or who in ("self", "attached"):
            return None
        return statics._definition(who, None, [], rules=[rule])
    return None


# -- attack costs (508.1d, 508.1h) -----------------------------------------------------------------------------------
def _parts(rule: str) -> list[str]:
    return rule.split(":")


def _defended(plan: Plan, target: str) -> tuple[str | None, bool]:
    """(the player attacked, directly or through a planeswalker they control; whether it's the player)."""
    if target in plan.state.players:
        return target, True
    card = plan.state.cards.get(target)
    if card is not None and "Planeswalker" in plan.ch(card).types:
        return card.controller, False
    return None, False


def taxes(plan: Plan, ch: Characteristics, target: str) -> list[tuple[str, str, str, str]]:
    """The attack-cost rules on this creature for attacking ``target``: (kind, player, cost per creature, source)."""
    player, direct = _defended(plan, target)
    out = []
    for rule in ch.imposed:
        p = _parts(rule)
        if p[0] in (TAX, TAX_PW) and len(p) == 4 and p[1] == player and (direct or p[0] == TAX_PW):
            out.append((p[0], p[1], p[2], p[3]))
    return out


def attack_cost(plan: Plan, declared: list[tuple[str, str]]) -> str:
    """The total cost of the declaration (508.1h, "" when none): for each attack-cost static that applies to a creature
    attacking its controller (or, for "you or planeswalkers you control", one of their planeswalkers), its cost for
    each creature attacking that player (or them and their planeswalkers)."""
    from app.rules import mana as M

    applying: set[tuple[str, str, str, str]] = set()
    direct: dict[str, int] = {}
    any_way: dict[str, int] = {}
    for cid, target in declared:
        player, is_direct = _defended(plan, target)
        if player is None:
            continue
        any_way[player] = any_way.get(player, 0) + 1
        if is_direct:
            direct[player] = direct.get(player, 0) + 1
        applying.update(taxes(plan, plan.ch(plan.state.cards[cid]), target))
    generic, symbols = 0, []
    for kind, player, cost, src in sorted(applying):
        n = (direct if kind == TAX else any_way).get(player, 0)
        if cost == "{X}":
            cost = f"{{{_tax_x(plan, src)}}}"
        each = M.parse_cost(cost)
        generic += each.generic * n
        symbols += [s for s in re.findall(r"\{[^}]+\}", cost) if not s[1:-1].isdigit()] * n
    if not generic and not symbols:
        return ""
    return (f"{{{generic}}}" if generic else "") + "".join(symbols)


def _tax_x(plan: Plan, source: str) -> int:
    """X of an attack cost "{X} …, where X is …", read from its source now (508.1h: as the total is determined)."""
    from app.rules import scripts, values

    card = plan.state.cards.get(source)
    if card is None:
        return 0
    for d in scripts.definitions(plan.ch(card)).values():
        if d.get("tax_x") is not None:
            return values.evaluate(plan, {"controller": card.controller, "source_card": card.id,
                                          "source_object": plan.oid(card)}, d["tax_x"])
    return 0


def taxed(plan: Plan, ch: Characteristics, target: str) -> bool:
    return bool(taxes(plan, ch, target))


# -- attack limits (508.1c) ------------------------------------------------------------------------------------------
def limits(plan: Plan, kind: str = LIMIT) -> dict[str, int]:
    """Players and the most creatures that can attack them each combat (the smallest of their limits); ``"*"``: the most
    that can attack at all (``LIMIT_ALL``), or that can block at all (``kind`` BLOCK_LIMIT_ALL, key ``"*"`` only)."""
    from app.rules import scripts

    out: dict[str, int] = {}
    for c in plan.state.cards.values():
        if not c.zone.endswith(":battlefield") or c.face_down or not plan.in_game(c) or plan.manual(c):
            continue
        for d in scripts.definitions(plan.ch(c)).values():
            if d.get("kind") != "static":
                continue
            if d.get("static") == kind == LIMIT:
                out[c.controller] = min(out.get(c.controller, 99), int(d["n"]))
            elif d.get("static") == (BLOCK_LIMIT_ALL if kind == BLOCK_LIMIT_ALL else LIMIT_ALL):
                out["*"] = min(out.get("*", 99), int(d["n"]))
    return out


def limit_problem(plan: Plan, declared: list[tuple[str, str]], caps: dict[str, int]) -> str | None:
    for player, n in caps.items():
        k = len(declared) if player == "*" else sum(1 for _, t in declared if t == player)
        if k > n:
            return f"No more than {n} creature{'s' if n != 1 else ''} can attack {'' if player == '*' else plan.name(player) + ' '}each combat"
    return None


# -- requirements (508.1d) -------------------------------------------------------------------------------------------
def other_than(ch: Characteristics) -> set[str]:
    """Players this creature attacks someone other than if able (Kardur's effect: ``attack_other_than:<player>``)."""
    return {r.split(":", 1)[1] for r in ch.imposed if r.startswith(OTHER_THAN + ":")}


def requirements_problem(plan: Plan, eligible: set[str], places: dict[str, list[str]],
                         declared: dict[str, str], caps: dict[str, int]) -> str | None:
    """508.1d over the whole declaration when some player limits how many creatures attack them: the number of
    requirements obeyed must be the most any declaration obeying the restrictions could obey. ``places``: for each
    creature with requirements, where it could attack without a restriction or a cost (508.1d)."""
    from app.rules import scripts
    from app.rules.keyword_actions import goaded_by

    live = set(plan.live())
    weights: list[dict[str | None, int]] = []
    obeyed = 0
    for cid in sorted(places):
        ch = plan.ch(plan.state.cards[cid])
        attack = len(goaded_by(ch) & live) + (1 if "must_attack" in scripts.statics(ch) else 0)
        others = (goaded_by(ch) | other_than(ch)) & live

        def score(place: str | None, attack: int = attack, others: set[str] = others) -> int:
            if place is None:
                return 0
            return attack + sum(1 for g in others if place in plan.state.players and place != g)

        weights.append({None: 0, **{t: score(t) for t in places[cid]}})
        obeyed += score(declared.get(cid))
    order = sorted(caps)

    @cache
    def best(i: int, left: tuple[int, ...]) -> int:
        if i == len(weights):
            return 0
        top = best(i + 1, left)
        for place, w in weights[i].items():
            if place is None:
                continue
            pools = [j for j, p in enumerate(order) if p in (place, "*")]  # (the place's own limit, and the one for all attackers)
            if any(left[j] <= 0 for j in pools):
                continue
            top = max(top, w + best(i + 1, tuple(n - (j in pools) for j, n in enumerate(left))))
        return top

    if obeyed < best(0, tuple(caps[p] for p in order)):
        return "The attack doesn't obey as many attack requirements as it could (508.1d)"
    return None


# -- blocks (509.1b) -------------------------------------------------------------------------------------------------
def block_problem(state: GameState, blocker: CardInstance, bch: Characteristics, attacker: CardInstance,
                  info: CardInfo | None) -> str | None:
    for rule in sorted(bch.imposed):
        p = _parts(rule)
        if p[0] == CANT_BLOCK_CTRL and len(p) == 2 and attacker.controller == p[1]:
            return f"{bch.name} can't block creatures {state.players[p[1]].name} controls"
        if p[0] == CANT_BLOCK_CTRL_POWER and len(p) == 3 and attacker.controller == p[1]:
            src = state.cards.get(p[2])
            if src is None or info is None or not src.zone.endswith(":battlefield"):
                continue
            from app.rules import characteristics as chars
            from app.rules.combat import _power
            from app.rules.layers import derive

            sch = derive(state, src, chars.of(src, info), info)
            if _power(bch) < _power(sch):
                return f"{bch.name} can't block creatures {state.players[p[1]].name} controls (its power is less than {sch.name}'s)"
    return None


# -- additional combat phases (500.8) --------------------------------------------------------------------------------
_MAIN = ("main1", "main2")
_COMBAT = ("begin_combat", "declare_attackers", "declare_blockers", "combat_damage", "end_combat")
_NATURAL = {"main1": "begin_combat", "main2": "end", "combat": "main2"}


def extra_phases(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """``{"do": "extra_phases", "after": "main" | "phase", "main": bool}``: an additional combat phase (and an
    additional main phase after it) directly after this phase (500.8)."""
    r = plan.rules
    phase = plan.state.turn.phase
    current = "combat" if phase in _COMBAT else phase if phase in _MAIN else None
    if current is None or (e["after"] == "main" and current == "combat") or (e["after"] == "combat" and current != "combat"):
        kind = {"main": "main ", "combat": "combat "}.get(e["after"], "")
        plan.note(f"{ctx.get('name') or 'It'}: this isn't a {kind}phase to add a combat phase after (500.8)")
        return True
    added = ["begin_combat"] + (["main2"] if e.get("main") else [])
    r.extra_phases = added + (list(r.extra_phases) or [_NATURAL[current]])
    plan.note(f"{ctx.get('name') or 'An effect'}: an additional combat phase"
              + (" and an additional main phase" if e.get("main") else "") + " after this phase (500.8)",
              actor=ctx["controller"])
    return True


def next_phase(plan: Plan) -> str | None:
    """As a main phase or a combat phase ends: the phase that begins next, when additional phases were added."""
    r = plan.rules
    if not r.extra_phases:
        return None
    return r.extra_phases.pop(0)


def new_turn(plan: Plan) -> None:
    plan.rules.extra_phases = []
    plan.rules.combats = 0


def combat_began(plan: Plan) -> None:
    plan.rules.combats += 1


# -- effects ---------------------------------------------------------------------------------------------------------
_EXTRA = re.compile(r"(?:after this (?:(?P<main>main )|(?P<combat>combat ))?phase, there is an additional combat phase"
                    r"(?P<and> followed by an additional main phase)?"
                    r"|there is an additional combat phase after this (?:(?P<main2>main )|(?P<combat2>combat ))?phase)")
_MUST = re.compile(r"(?P<o>.+?) attacks? this turn if able")
_EACH_COMBAT = re.compile(r"(?P<o>.+?) (?:attack each combat if able(?P<pl> and attack a player other than you if able)?"
                         r"|attacks each combat if able(?P<sg> and attacks a player other than you if able)?)"
                         r"(?P<eot> until end of turn)?")
_EACH_OPP = re.compile(r"for each opponent, (?P<create>create .+? token(?:s)? that's tapped and attacking) that player"
                       r"(?P<pw> or a planeswalker they control)?")
_AND_EXTRA = re.compile(r"(?P<a>.+?),? and (?P<b>after this (?:main |combat )?phase, there is an additional combat phase.*)")
_REMOVE = re.compile(r"remove (?P<o>.+?) from combat")
_MAZE = re.compile(r"prevent all combat damage that would be dealt to and dealt by (?P<o>that creature|it|target creature(?: you control)?|~)"
                   r" this turn")
_DOUBLE = re.compile(r"double (?:the (?P<w1>power and toughness|power) of (?P<o1>.+?)|(?P<o2>.+?)'s "
                     r"(?P<w2>power and toughness|power)|(?P<o3>its) (?P<w3>power and toughness|power)) until end of turn")
# -- keywords (wave 15E) -- myriad (702.116a): "for each opponent other than defending player, you may create a token that's a
# copy of ~ that's tapped and attacking that player or a planeswalker they control. If one or more tokens are created this way,
# exile the tokens at end of combat."
_MYRIAD = re.compile(r"for each opponent other than defending player, you may create a token that's a copy of (?:~|this creature) "
                     r"that's tapped and attacking that player or a planeswalker they control \[exile at end of combat\]")
_MYRIAD_EXILE = re.compile(r"(planeswalker they control)\. If one or more tokens are created this way, exile the tokens at end of "
                           r"combat\.")


def merge_myriad(body: str) -> str:
    """myriad's two sentences (702.116a) as the one instruction they are (scripts._parse_effects)."""
    return _MYRIAD_EXILE.sub(r"\1 [exile at end of combat].", body) if "other than defending player" in body else body
_THAT_PLAYER = re.compile(r"(?P<create>create .+? tokens? that(?:'s| are) tapped and attacking) that player")


def clause(text: str) -> tuple[Effects, Any] | None:
    """One instruction of this module (lower-cased first word, no final period), or None."""
    m = _EXTRA.fullmatch(text)
    if m:
        after = "main" if m["main"] or m["main2"] else "combat" if m["combat"] or m["combat2"] else "phase"
        return [{"do": "extra_phases", "after": after, "main": bool(m["and"])}], None
    m = _AND_EXTRA.fullmatch(text)
    if m:  # "untap all attacking creatures and after this phase, there is an additional combat phase"
        from app.rules import scripts

        left, right = scripts._clause(m["a"]), clause(m["b"])
        if left is None or right is None:
            return None
        return left[0] + right[0], left[1]
    m = _REMOVE.fullmatch(text)
    if m:  # 506.4
        found = _object(m["o"])
        return ([{"do": "remove_from_combat", "who": found[0]}], found[1]) if found is not None else None
    m = _MAZE.fullmatch(text)
    if m:  # (Maze of Ith: 615, a prevention effect for this turn)
        found = _object(m["o"])
        if found is None:
            return None
        return [{"do": "prevent_all", "scope": {"combat": True, "to_or_by": True}, "who": found[0], "role": "both"}], found[1]
    m = _DOUBLE.fullmatch(text)
    if m:  # 701.10b / 613.4c
        what = m["w1"] or m["w2"] or m["w3"]
        found = _object(m["o1"] or m["o2"] or m["o3"], each=True)
        if found is None:
            return None
        return [{"do": "double_pt", "who": found[0], "toughness": what == "power and toughness"}], found[1]
    m = _EACH_COMBAT.fullmatch(text)
    if m:  # (with a duration: "until end of turn", or "until your next turn, …" read as that: ``unwrapped``)
        restricted = _restrict(m["o"], ["must_attack"] + ([f"{OTHER_THAN}:@you"] if m["pl"] or m["sg"] else []))
        if restricted is None:
            return None
        return ([restricted[0][0]] if m["eot"] else [{**restricted[0][0], "each_combat": True}]), restricted[1]
    m = _MUST.fullmatch(text)
    if m:
        return _restrict(m["o"], ["must_attack"])
    if _MYRIAD.fullmatch(text):  # (both sentences: the exile is part of the keyword, 702.116a)
        from app.rules import delayed

        return [{"do": "myriad_choose"}, {"do": "myriad_create", "who": "self", "as": "myriad_tokens"},
                *delayed.wrap_when([{"do": "exile", "who": "ref:myriad_tokens"}], delayed.END_OF_COMBAT)], None
    m = _EACH_OPP.fullmatch(text)
    if m:
        made = _token(m["create"])
        if made is None:
            return None
        return [{"do": "create_attacking_each", "token": made["token"], "n": made["n"], "pw": bool(m["pw"])}], None
    m = _THAT_PLAYER.fullmatch(text)
    if m:
        made = _token(m["create"])
        if made is None:
            return None
        return [{"do": "create_attacking_each", "token": made["token"], "n": made["n"], "pw": False,
                 "who": "defended"}], None
    return None


def unwrapped(d: Definition) -> bool:
    """An "attacks each combat if able" effect must have a duration ("until your next turn, …"): one without it
    isn't read. "Tapped and attacking that player" is read only in "Whenever you attack a player, …" (the player
    attacked, 508.3e)."""
    if any(e.get("do") in ("myriad_choose", "myriad_create") for e in d.get("effects") or []) and not (
            d.get("kind") == "triggered" and d.get("trigger") == "attacks_self"):
        return True  # (-- keywords (wave 15E) -- myriad is about the attacking creature itself)
    effects = d.get("effects") or []
    cond = d.get("cond") or {}
    if any(e.get("who") == "defended" for e in effects) and not (
            d.get("kind") == "triggered" and cond.get("event") == "you_attack" and cond.get("player") == "you"
            and cond.get("defender") == "player" and not cond.get("min_attackers")):
        return True
    covered: set[int] = set()
    for i, e in enumerate(effects):
        if e.get("do") == "until":
            covered.update(range(i + 1, i + 1 + int(e.get("n") or 0)))
    return any(e.get("each_combat") and i not in covered for i, e in enumerate(effects)) or any(
        unwrapped(m) for m in d.get("modes") or [])


def _token(create: str) -> dict[str, Any] | None:
    from app.rules import token_grammar

    found = token_grammar.parse(create)
    if not found or len(found) != 1 or found[0].get("do") != "create_attacking" or not found[0].get("tapped") or isinstance(found[0].get("n"), dict):
        return None
    return found[0]


def _object(phrase: str, *, each: bool = False) -> tuple[str, Any] | None:
    """An object reference: a target, "it" / "that creature", ~ (and with ``each``, a group: "each creature you
    control") -> (who, target group)."""
    from app.rules import language

    if phrase == "its":
        phrase = "it"
    try:
        kind, key, group = language.ref(phrase)
    except language._Fail:
        return None
    if kind in ("players", "them", "host") or (kind == "each" and not each):
        return None
    return language._who(kind, key), language._one(group)


def _restrict(phrase: str, rules: list[str]) -> tuple[Effects, Any] | None:
    from app.rules import language

    if " and " in phrase or phrase.startswith(("you ", "each player", "each opponent")):
        return None
    try:
        kind, key, group = language.ref(phrase)
    except language._Fail:
        return None
    if kind == "players":
        return None
    return [{"do": "restrict", "who": language._who(kind, key), "rules": rules}], language._one(group)


# -- "tapped and attacking that player" (508.4) ----------------------------------------------------------------------
_ATTACKING_PHASES = ("declare_attackers", "declare_blockers", "combat_damage", "end_combat")


def create_attacking_each(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """For each opponent (or the trigger's player), create the tokens tapped; while their controller is the attacking
    player in the declare attackers step or later (508.4, 506.3b) they are attacking that player — or, with "or a
    planeswalker they control", a planeswalker of theirs the controller chooses. 508.4a: a player who left gets none
    attacking them. They were never declared as attackers (no attack triggers)."""
    from app.rules import effects

    me = ctx["controller"]
    if e.get("who") == "defended":  # (the player the trigger's attack was declared against: ``refused``)
        defended = (ctx.get("event") or {}).get("defended")
        players = [defended] if defended in plan.live() and defended != me else []
    else:
        players = [p for p in plan.apnap() if p != me and p in plan.live()]
    attacking = plan.state.turn.phase in _ATTACKING_PHASES and me == plan.active
    asks: list[dict[str, Any]] = []
    for pid in players:
        before = set(plan.state.cards)
        effects.create_token(plan, ctx, {"do": "create_token", "who": "you", "n": e["n"], "token": e["token"],
                                         "tapped": True})
        new = [cid for cid, c in plan.state.cards.items() if cid not in before and c.controller == me
               and c.zone.endswith(":battlefield")]
        if not new or not attacking or pid not in plan.live():
            continue
        walkers = [c.id for c in plan.state.cards.values() if e.get("pw") and c.zone.endswith(":battlefield")
                   and c.controller == pid and plan.in_game(c) and "Planeswalker" in plan.ch(c).types]
        if walkers:
            asks.append({"player": pid, "cards": new, "walkers": walkers})
        else:
            _attack(plan, new, pid, me)
    return _ask_next(plan, ctx, asks)


def _attack(plan: Plan, cards: list[str], target: str, actor: str) -> None:
    from app.rules.token_grammar import _attack_with

    _attack_with(plan, cards, target, actor)


def _ask_next(plan: Plan, ctx: dict[str, Any], asks: list[dict[str, Any]]) -> bool:
    if not asks:
        return True
    ask, rest = asks[0], asks[1:]
    me = ctx["controller"]
    options = [DecisionOption(id=ask["player"], label=plan.name(ask["player"]))]
    options += [DecisionOption(id=c, label=plan.state.cards[c].name or "Planeswalker", card_id=c) for c in ask["walkers"]
                if c in plan.state.cards]
    n = len(ask["cards"])
    decide(plan, player=me, kind="choose_one",
           prompt=f"{n} token{'s' if n != 1 else ''} enter attacking {plan.name(ask['player'])} or a planeswalker they "
                  "control: attacking which?",
           options=options, resume={"step": "attack_each_opponent", "ctx": ctx, "ask": ask, "rest": rest})
    return False


def resume_attack_each(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import effects

    r = d.resume
    if chosen:
        _attack(plan, r["ask"]["cards"], chosen[0], d.player)
    if _ask_next(plan, r["ctx"], r["rest"]):
        effects.continue_effects(plan, r["ctx"])


# -- removing from combat (506.4), doubling power and toughness (701.10) --------------------------------------------
def remove_from_combat(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """506.4: the creature stops being an attacking or blocking creature (a creature it blocked stays blocked,
    509.1h). It doesn't untap or tap."""
    from app.rules import effects

    for cid in effects._cards(plan, ctx, e["who"]):
        card = plan.state.cards[cid]
        if not card.zone.endswith(":battlefield"):
            continue
        if card.attacking is not None:
            plan.do({"type": "attack", "card_ids": [cid], "target": None}, actor=ctx["controller"])
            plan.rules.blocked = [c for c in plan.rules.blocked if c != cid]
        if card.blocking:
            plan.do({"type": "block", "card_id": cid, "attacker_id": None}, actor=ctx["controller"])
    return True


def double_pt(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """701.10b: doubling a creature's power gives it +X/+0 where X is its power as the effect begins (and +0/+Y for
    its toughness); 701.10c: a negative power gets -X/-0 where X is the difference from 0 - the same as adding the
    power. Layer 7c (613.4c), until end of turn; each creature its own amount."""
    from app.rules import effects, layers
    from app.rules.sba import power, toughness

    cards = effects._cards(plan, ctx, e["who"])
    effects._remember(plan, ctx, e, cards)
    for cid in cards:
        card = plan.state.cards[cid]
        ch = plan.ch(card)
        if not card.zone.endswith(":battlefield") or not ch.is_creature:
            continue
        p = power(card, ch)
        t = toughness(card, ch) if e.get("toughness") else 0
        if p is None or t is None:
            plan.note(f"{ctx.get('name') or 'The effect'}: {card.name}'s power isn't known: double it by hand")
            continue
        layers.add_effect(plan, affected=[plan.oid(card)], layer="7c", source=ctx.get("source_object"),
                          controller=ctx["controller"], power=p, toughness=t,
                          label=f"doubled: {p:+d}/{t:+d} until end of turn ({ctx.get('name', '')})")
        effects._mark(plan, [cid], f"{p:+d}/{t:+d}")
    return True


# -- keywords (wave 15E) -- myriad (702.116a): the choices first (one decision per opponent other than the defending player,
# private to the attacker), then the copies are made at once and each attacks the player or planeswalker chosen for it
def myriad_choose(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import defending

    src = plan.state.cards.get(ctx.get("source_card") or "")
    me = ctx["controller"]
    defended = defending.defended(plan, src) if src is not None and src.zone.endswith(":battlefield") else None
    ctx["myriad"] = []
    if defended is None or me != plan.active or plan.state.turn.phase not in _ATTACKING_PHASES:
        return True  # (no longer an attacking creature: nobody to create a token for)
    return _myriad_next(plan, ctx, [p for p in plan.apnap() if p != me and p != defended and p in plan.live()], [])


def _myriad_next(plan: Plan, ctx: dict[str, Any], remaining: list[str], picked: list[str]) -> bool:
    me = ctx["controller"]
    while remaining:
        pid = remaining[0]
        if pid not in plan.live():
            remaining = remaining[1:]
            continue
        walkers = [c.id for c in plan.state.cards.values() if c.zone.endswith(":battlefield") and c.controller == pid
                   and plan.in_game(c) and "Planeswalker" in plan.ch(c).types]
        options = [DecisionOption(id="none", label=f"No token for {plan.name(pid)}"),
                   DecisionOption(id=pid, label=f"A token attacking {plan.name(pid)}"),
                   *(DecisionOption(id=c, label=f"A token attacking {plan.state.cards[c].name or 'a planeswalker'}", card_id=c)
                     for c in walkers)]
        decide(plan, player=me, kind="choose_one",
               prompt=f"{ctx.get('name') or 'Myriad'}: create a token copy attacking {plan.name(pid)} or a planeswalker they control?",
               options=options, resume={"step": "myriad_pick", "ctx": ctx, "remaining": remaining[1:], "picked": picked})
        return False
    ctx["myriad"] = picked
    return True


def resume_myriad(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import effects

    r = d.resume
    picked = list(r["picked"]) + ([chosen[0]] if chosen and chosen[0] != "none" else [])
    if _myriad_next(plan, r["ctx"], list(r["remaining"]), picked):
        effects.continue_effects(plan, r["ctx"])


def myriad_create(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import context, copying

    picked = [t for t in ctx.get("myriad") or [] if t in plan.state.players and t in plan.live()
              or (t in plan.state.cards and plan.state.cards[t].zone.endswith(":battlefield"))]
    if not picked:
        return True
    if not copying.token_copy(plan, ctx, {"do": "token_copy", "who": "self", "n": len(picked), "tapped": True,
                                          "as": e.get("as")}):
        return False
    for token, target in zip(context.objects(plan, ctx, str(e.get("as"))), picked, strict=False):
        _attack(plan, [token], target, ctx["controller"])  # 508.4: attacking, never declared as an attacker
    return True


PRIMITIVES = {"extra_phases": extra_phases, "create_attacking_each": create_attacking_each,
              "remove_from_combat": remove_from_combat, "double_pt": double_pt,
              "myriad_choose": myriad_choose, "myriad_create": myriad_create}
RESUME = {"attack_each_opponent": resume_attack_each, "myriad_pick": resume_myriad}

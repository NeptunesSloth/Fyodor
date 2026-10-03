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
OTHER_THAN = "attack_other_than"
CANT_BLOCK_CTRL = "cant_block_ctrl"
CANT_BLOCK_CTRL_POWER = "cant_block_ctrl_power"
LIMIT = "attack_limit"
_NUMBERS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5}


# -- statics ---------------------------------------------------------------------------------------------------------
_TAX_RE = re.compile(r"(?P<sub>.+?) can't attack you unless their controller pays \{(?P<n>\d+)\} for each creature "
                     r"they control that's attacking you\.")
_CTRL_RE = re.compile(r"(?P<sub>.+?) can't block creatures you control\.")
_POWER_SUB = re.compile(r"Creatures with power less than (?:~|this creature)'s power")
_LIMIT_RE = re.compile(r"No more than (?P<n>one|two|three|four|five) creatures? can attack you each combat\.")


def static_definition(text: str) -> Definition | None:
    """One static ability (the card's own name written as ~) of this module, or None."""
    from app.rules import statics

    t = text.strip()
    m = _LIMIT_RE.fullmatch(t)
    if m:
        return {"kind": "static", "static": LIMIT, "n": _NUMBERS[m["n"]], "effects": []}
    m = _TAX_RE.fullmatch(t)
    if m:
        who, _ = statics._subject(m["sub"])
        if who is None or who in ("self", "attached"):
            return None
        return statics._definition(who, None, [], rules=[f"{TAX}:@you:{int(m['n'])}:@src"])
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


def taxes(ch: Characteristics, target: str) -> list[tuple[str, int, str]]:
    """The attack-cost rules on this creature for attacking ``target`` (a player): (player, {N}, source)."""
    out = []
    for rule in ch.imposed:
        p = _parts(rule)
        if p[0] == TAX and len(p) == 4 and p[1] == target and p[2].isdigit():
            out.append((p[1], int(p[2]), p[3]))
    return out


def attack_cost(plan: Plan, declared: list[tuple[str, str]]) -> int:
    """The generic mana the declaration costs (508.1h): for each attack-cost static that applies to a creature
    attacking its controller, {N} for each creature attacking that player."""
    applying: set[tuple[str, int, str]] = set()
    count: dict[str, int] = {}
    for cid, target in declared:
        if target not in plan.state.players:
            continue
        count[target] = count.get(target, 0) + 1
        applying.update(taxes(plan.ch(plan.state.cards[cid]), target))
    return sum(n * count[player] for player, n, _ in applying)


def taxed(ch: Characteristics, target: str) -> bool:
    return bool(taxes(ch, target))


# -- attack limits (508.1c) ------------------------------------------------------------------------------------------
def limits(plan: Plan) -> dict[str, int]:
    """Players and the most creatures that can attack them each combat (the smallest of their limits)."""
    from app.rules import scripts

    out: dict[str, int] = {}
    for c in plan.state.cards.values():
        if not c.zone.endswith(":battlefield") or c.face_down or not plan.in_game(c) or plan.manual(c):
            continue
        for d in scripts.definitions(plan.ch(c)).values():
            if d.get("kind") == "static" and d.get("static") == LIMIT:
                out[c.controller] = min(out.get(c.controller, 99), int(d["n"]))
    return out


def limit_problem(plan: Plan, declared: list[tuple[str, str]], caps: dict[str, int]) -> str | None:
    for player, n in caps.items():
        k = sum(1 for _, t in declared if t == player)
        if k > n:
            return f"No more than {n} creature{'s' if n != 1 else ''} can attack {plan.name(player)} each combat"
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
            if place in caps:
                j = order.index(place)
                if left[j] <= 0:
                    continue
                top = max(top, w + best(i + 1, left[:j] + (left[j] - 1,) + left[j + 1:]))
            else:
                top = max(top, w + best(i + 1, left))
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
    if current is None or (e["after"] == "main" and current == "combat"):
        plan.note(f"{ctx.get('name') or 'It'}: there is no {'main ' if e['after'] == 'main' else ''}phase this turn to "
                  "add a combat phase after (500.8)")
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
_EXTRA = re.compile(r"after this (?P<main>main )?phase, there is an additional combat phase"
                    r"(?P<and> followed by an additional main phase)?")
_MUST = re.compile(r"(?P<o>.+?) attacks? this turn if able")
_EACH_COMBAT = re.compile(r"(?P<o>.+?) (?:attack each combat if able(?P<pl> and attack a player other than you if able)?"
                         r"|attacks each combat if able(?P<sg> and attacks a player other than you if able)?)"
                         r"(?P<eot> until end of turn)?")
_EACH_OPP = re.compile(r"for each opponent, (?P<create>create .+? token(?:s)? that's tapped and attacking) that player"
                       r"(?P<pw> or a planeswalker they control)?")
_THAT_PLAYER = re.compile(r"(?P<create>create .+? tokens? that(?:'s| are) tapped and attacking) that player")


def clause(text: str) -> tuple[Effects, Any] | None:
    """One instruction of this module (lower-cased first word, no final period), or None."""
    m = _EXTRA.fullmatch(text)
    if m:
        return [{"do": "extra_phases", "after": "main" if m["main"] else "phase", "main": bool(m["and"])}], None
    m = _EACH_COMBAT.fullmatch(text)
    if m:  # (with a duration: "until end of turn", or "until your next turn, …" read as that: ``unwrapped``)
        found = _restrict(m["o"], ["must_attack"] + ([f"{OTHER_THAN}:@you"] if m["pl"] or m["sg"] else []))
        if found is None:
            return None
        return ([found[0][0]] if m["eot"] else [{**found[0][0], "each_combat": True}]), found[1]
    m = _MUST.fullmatch(text)
    if m:
        return _restrict(m["o"], ["must_attack"])
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
    if not found or len(found) != 1 or found[0].get("do") != "create_attacking" or isinstance(found[0].get("n"), dict):
        return None
    return found[0]


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


PRIMITIVES = {"extra_phases": extra_phases, "create_attacking_each": create_attacking_each}
RESUME = {"attack_each_opponent": resume_attack_each}

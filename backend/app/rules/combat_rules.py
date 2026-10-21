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
later phase ("After the second main phase this turn", World at War), costs to block (Heat Wave's second line).
"""

from __future__ import annotations

import re
from functools import cache
from typing import TYPE_CHECKING, Any

from app.game.rules_state import DecisionOption
from app.rules import token_attack_continuations as _token_attack_continuations
from app.rules.plan import decide

if TYPE_CHECKING:
    from app.game.state import CardInstance, GameState
    from app.rules.characteristics import CardInfo, Characteristics
    from app.rules.plan import Plan

Definition = dict[str, Any]
Effects = list[dict[str, Any]]

TAX = "attack_tax"
TAX_PW = "attack_tax_pw"  # (also attacking a planeswalker the player controls)
BLOCK_TAX = "block_tax"
OTHER_THAN = "attack_other_than"
ATTACK_PLAYER = "attack_player"  # -- casting extras (wave 18E) -- "attacks that opponent this turn if able" (encore, 702.141a): ``attack_player:<player>``
CANT_BLOCK_CTRL = "cant_block_ctrl"
CANT_BLOCK_CTRL_POWER = "cant_block_ctrl_power"
LIMIT = "attack_limit"
LIMIT_ALL = "attack_limit_all"  # -- static_other sweep (wave 16B) -- "No more than one creature can attack each combat." (Silent Arbiter)
BLOCK_LIMIT_ALL = "block_limit_all"  # … "can block each combat": the creatures that block, all players together
_NUMBERS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5}


# -- statics ---------------------------------------------------------------------------------------------------------
_TAX_RE = re.compile(r"(?P<sub>.+?) can't attack you unless their controller pays (?P<cost>(?:\{[^}]+\})+) for each "
                     r"(?:creature they control that's attacking you|of those creatures)(?:, where X is (?P<x>.+))?\.")  # (wave 45D: Dáin)
_TAX_PW_RE = re.compile(r"(?P<sub>.+?) can't attack you or planeswalkers you control unless their controller pays "
                        r"(?P<cost>(?:\{[^}]+\})+) for each of those creatures(?:, where X is (?P<x>.+))?\.")
_CTRL_RE = re.compile(r"(?P<sub>.+?) can't block creatures you control\.")
_POWER_SUB = re.compile(r"Creatures with power less than (?:~|this creature)'s power")
_LIMIT_RE = re.compile(r"No more than (?P<n>one|two|three|four|five) creatures? can attack you each combat\.")
_LIMIT_PW_RE = re.compile(r"No more than (?P<n>one|two|three|four|five) creatures? can attack (?:~|this planeswalker) each combat\.")  # (wave 44C: Tomik, Orzhov Lawmage)
_LIMIT_ALL_RE = re.compile(r"No more than (?P<n>one|two|three|four|five) creatures? can (?P<v>attack|block) each combat\.")


def static_definition(text: str) -> Definition | None:
    """One static ability (the card's own name written as ~) of this module, or None."""
    from app.rules import attack_destinations, creature_combat_costs, nonmana_combat_costs, statics

    if (destination := attack_destinations.static_definition(text)) is not None:
        return destination

    if (nonmana := nonmana_combat_costs.parse(text)) is not None:
        return nonmana

    if (own_cost := creature_combat_costs.parse(text)) is not None:
        return own_cost
    t = text.strip()
    blocked = re.fullmatch(r"(?P<sub>.+?) can't block unless their controller pays (?P<cost>(?:\{[^}]+\})+) for each of those creatures\.", t)
    if blocked:
        from app.rules import mana as M

        who, _ = statics._subject(blocked['sub'])
        cost = M.parse_cost(blocked['cost'])
        if who is None or who in ('self', 'attached') or cost.unsupported or cost.x or cost.is_free:
            return None
        return statics._definition(who, None, [], rules=[f"{BLOCK_TAX}:{blocked['cost']}:@src"])
    held = re.fullmatch(r"As long as ~ is (un)?tapped, ([Nn]o more than .+)", t)  # -- commander sweep (wave 49B) -- 611.3a: "As long as Mirri is tapped, no more than one creature can attack you each combat."
    if held:
        own = static_definition(held[2][0].upper() + held[2][1:])
        return {**own, "conditions": [{"static": "self", "test": "untapped" if held[1] else "tapped"}]} if own is not None and own["static"] == LIMIT else None
    m = _LIMIT_RE.fullmatch(t)
    if m:
        return {"kind": "static", "static": LIMIT, "n": _NUMBERS[m["n"]], "effects": []}
    m = _LIMIT_PW_RE.fullmatch(t)  # -- counters (wave 44C) -- 508.1: no more than N creatures attack this planeswalker (keyed by it in ``limits``)
    if m:
        return {"kind": "static", "static": LIMIT, "n": _NUMBERS[m["n"]], "pw": True, "effects": []}
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
            who, kind = statics._subject(m["sub"])
            if who == "attached" and kind != "creature":
                return None
            rule = f"{CANT_BLOCK_CTRL}:@you"
        if who is None or who == "self":
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


def _applying(plan: Plan, declared: list[tuple[str, str]]) -> tuple[set[tuple[str, str, str, str]], dict[str, int], dict[str, int]]:
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
    return applying, direct, any_way


def attack_cost(plan: Plan, declared: list[tuple[str, str]]) -> str:
    """The total cost of the declaration (508.1h, "" when none): for each attack-cost static that applies to a creature
    attacking its controller (or, for "you or planeswalkers you control", one of their planeswalkers), its cost for
    each creature attacking that player (or them and their planeswalkers)."""
    from app.rules import mana as M

    applying, direct, any_way = _applying(plan, declared)
    generic, symbols = 0, []
    for kind, player, cost, src in sorted(applying):
        n = (direct if kind == TAX else any_way).get(player, 0)
        if cost.endswith(" life"):  # (the life part: ``attack_life``)
            continue
        if cost == "{X}":
            cost = f"{{{_tax_x(plan, src)}}}"
        each = M.parse_cost(cost)
        generic += each.generic * n
        symbols += [s for s in re.findall(r"\{[^}]+\}", cost) if not s[1:-1].isdigit()] * n
    from app.rules import creature_combat_costs

    extra = creature_combat_costs.total(plan, [cid for cid, _ in declared], defenders=dict(declared))
    combined = M.parse_cost((f"{{{generic}}}" if generic else "") + "".join(symbols) + extra.text())
    return "" if combined.is_free else combined.text()


def attack_life(plan: Plan, declared: list[tuple[str, str]]) -> int:
    """-- life attack costs (wave 49D) -- 508.1g-h: the life the declaration costs, "unless their controller pays 2 life for each of those
    creatures" (Sivitri, Dragon Master): the same count as a mana cost's, paid together with it (508.1j)."""
    applying, direct, any_way = _applying(plan, declared)
    return sum(int(cost.split()[0]) * (direct if kind == TAX else any_way).get(player, 0)
               for kind, player, cost, _ in applying if cost.endswith(" life"))


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


def taxed(plan: Plan, ch: Characteristics, target: str, card_id: str | None = None, *, declared: bool = False) -> bool:
    """Whether reaching this defender requires a cost not accepted by the declaration."""
    from app.rules import creature_combat_costs, nonmana_combat_costs
    return bool(taxes(plan, ch, target)) or (card_id is not None and (
        not creature_combat_costs.total(plan, [card_id], defenders={card_id: target}, destination_only=declared).is_free
        or not declared and nonmana_combat_costs.has_cost(plan, card_id, 'attack')))


def block_taxes(ch: Characteristics) -> set[tuple[str, str]]:
    return {(p[1], p[2]) for r in ch.imposed if len(p := r.split(':')) == 3 and p[0] == BLOCK_TAX}


def block_cost(plan: Plan, blockers: set[str]) -> str:
    from app.rules import creature_combat_costs
    from app.rules import mana as M

    fixed = "".join(cost for cid in sorted(blockers) for cost, _ in sorted(block_taxes(plan.ch(plan.state.cards[cid]))))
    return M.parse_cost(fixed + creature_combat_costs.total(plan, list(blockers), mode="block").text()).text()


def has_block_cost(plan: Plan, card_id: str, ch: Characteristics) -> bool:
    from app.rules import creature_combat_costs, nonmana_combat_costs
    return bool(block_taxes(ch)) or not creature_combat_costs.total(plan, [card_id], mode="block").is_free or nonmana_combat_costs.has_cost(plan, card_id, 'block')


# -- attack limits (508.1c) ------------------------------------------------------------------------------------------
def limits(plan: Plan, kind: str = LIMIT) -> dict[str, int]:
    """Players and the most creatures that can attack them each combat (the smallest of their limits); ``"*"``: the most
    that can attack at all (``LIMIT_ALL``), or that can block at all (``kind`` BLOCK_LIMIT_ALL, key ``"*"`` only)."""
    from app.rules import scripts, statics

    out: dict[str, int] = {}
    for c in plan.state.cards.values():
        if not c.zone.endswith(":battlefield") or c.face_down or not plan.in_game(c) or plan.manual(c):
            continue
        for d in scripts.definitions(plan.ch(c)).values():
            if d.get("kind") != "static" or not statics.conditions_hold(plan, d, source=c, controller=c.controller):  # (wave 49B: Mirri's "as long as it is tapped")
                continue
            if d.get("static") == kind == LIMIT:
                who = c.id if d.get("pw") else c.controller  # (wave 44C: "attack this planeswalker": the planeswalker itself)
                out[who] = min(out.get(who, 99), int(d["n"]))
            elif d.get("static") == (BLOCK_LIMIT_ALL if kind == BLOCK_LIMIT_ALL else LIMIT_ALL):
                out["*"] = min(out.get("*", 99), int(d["n"]))
    return out


def limit_problem(plan: Plan, declared: list[tuple[str, str]], caps: dict[str, int]) -> str | None:
    for player, n in caps.items():
        k = len(declared) if player == "*" else sum(1 for _, t in declared if t == player)
        if k > n:
            who = "" if player == "*" else (plan.state.cards[player].name if player in plan.state.cards else plan.name(player)) + " "
            return f"No more than {n} creature{'s' if n != 1 else ''} can attack {who}each combat"
    return None


# -- requirements (508.1d) -------------------------------------------------------------------------------------------
def other_than(ch: Characteristics) -> set[str]:
    """Players this creature attacks someone other than if able (Kardur's effect: ``attack_other_than:<player>``)."""
    return {r.split(":", 1)[1] for r in ch.imposed if r.startswith(OTHER_THAN + ":")}


def attack_players(ch: Characteristics) -> set[str]:
    """-- casting extras (wave 18E) -- Players this creature attacks this turn if able (encore's tokens, 702.141a)."""
    return {r.split(":", 1)[1] for r in ch.imposed if r.startswith(ATTACK_PLAYER + ":")}


def requirements_problem(plan: Plan, eligible: set[str], places: dict[str, list[str]],
                         declared: dict[str, str], caps: dict[str, int]) -> str | None:
    """508.1d over the whole declaration when some player limits how many creatures attack them: the number of
    requirements obeyed must be the most any declaration obeying the restrictions could obey. ``places``: for each
    creature with requirements, where it could attack without a restriction or a cost (508.1d)."""

    weights: list[dict[str | None, int]] = []
    obeyed = 0
    for cid in sorted(places):
        ch = plan.ch(plan.state.cards[cid])
        from app.rules import attack_requirements

        def score(place: str | None, ch: Characteristics = ch) -> int:
            return attack_requirements.score(plan, ch, place)

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
    tag = ""
    if e.get("then"):  # -- commander sweep (wave 49B) -- 603.7: "At the beginning of that combat, untap all creatures you control." (Moraug): a delayed trigger of the combat this adds
        # (tagged on its queue entry, so another phase added before it in the same turn doesn't take its trigger)
        import secrets

        from app.game.rules_state import DelayedTrigger

        tag = secrets.token_hex(4)
        r.delayed.append(DelayedTrigger(
            id=tag, controller=ctx["controller"], source_card=ctx.get("source_card"), source_object=ctx.get("source_object"), name=ctx.get("name") or "",
            when={"kind": "step", "step": "begin_combat", "whose": "next", "tag": tag}, effects=e["then"], turn=plan.state.turn.number, step=phase,
            until_turn=plan.state.turn.number))
    count = int(e.get("count", 1))
    added = ["begin_combat" + (f"@{tag}" if tag else "")] * count + (["main2"] if e.get("main") else [])
    r.extra_phases = added + (list(r.extra_phases) or [_NATURAL[current]])
    combats = "an additional combat phase" if count == 1 else f"{count} additional combat phases"
    plan.note(f"{ctx.get('name') or 'An effect'}: {combats}"
              + (" and an additional main phase" if e.get("main") else "") + " after this phase (500.8)",
              actor=ctx["controller"])
    return True


def extra_steps(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    phase = plan.state.turn.phase
    current = "combat" if phase in ("begin_combat", "declare_attackers", "declare_blockers", "combat_damage", "end_combat") else phase
    if e["kind"] == "beginning" and current in (*_MAIN, "combat"):
        plan.rules.extra_phases = ["untap", *(plan.rules.extra_phases or [_NATURAL[current]])]
    elif e["kind"] == "upkeep":
        from app.rules import effects, values

        recipients = effects._players(plan, ctx, e.get("who", "you"))
        if plan.active not in recipients:
            return True  # CR 500.10a: "you get" cannot add steps to another player's turn.
        count = max(0, values.evaluate(plan, ctx, e.get("n", 1)))
        if not count:
            return True
        if e.get("after") == "phase":
            if current in _NATURAL:
                plan.rules.extra_phases = ["upkeep@upkeep_only"] * count + (plan.rules.extra_phases or [_NATURAL[current]])
        elif phase in ("upkeep", "draw"):
            resume = "phase" if plan.rules.upkeep_only or (phase == "draw" and plan.rules.extra_beginning) else "draw" if phase == "upkeep" else "main1"
            plan.rules.extra_steps = ["upkeep"] * count + (plan.rules.extra_steps or [resume])
    elif e["kind"] == "end" and phase == "end":
        plan.rules.extra_phases = ["end", *(plan.rules.extra_phases or ["cleanup"])]
    return True


def next_phase(plan: Plan) -> str | None:
    """As a main phase or a combat phase ends: the phase that begins next, when additional phases were added."""
    r = plan.rules
    if not r.extra_phases:
        return None
    name, _, r.combat_tag = r.extra_phases.pop(0).partition("@")  # (wave 49B: the trigger id of the combat now beginning, "" for any other phase)
    return name


def new_turn(plan: Plan) -> None:
    plan.rules.extra_phases = []
    plan.rules.extra_steps = []
    plan.rules.upkeep_only = False
    plan.rules.extra_beginning = False
    plan.rules.combat_tag = ""
    plan.rules.combats = 0


def combat_began(plan: Plan) -> None:
    plan.rules.combats += 1
    from app.rules import last_combat_receipts44

    last_combat_receipts44.combat_began(plan)


# -- effects ---------------------------------------------------------------------------------------------------------
_EXTRA = re.compile(r"(?:after this (?:(?P<main>main )|(?P<combat>combat ))?phase, there is an additional combat phase"
                    r"|there(?: is|'s) an additional combat phase after this (?:(?P<main2>main )|(?P<combat2>combat ))?phase)"  # (wave 49B: "there's", Moraug)
                    r"(?P<and>,? followed by an additional main phase)?(?: \[at the beginning of that combat, (?P<then>untap all creatures[^\]]*)\])?")
_EXTRA_THEN = re.compile(r"(?P<x>(?:[Aa]fter this (?:main |combat )?phase, there is|[Tt]here(?: is|'s)) an additional combat phase"
                         r"(?: after this (?:main |combat )?phase)?)\. At the beginning of that combat, (?P<u>untap all creatures[^.]*)\.")


def merge_extra(body: str) -> str:
    """-- commander sweep (wave 49B) -- the two sentences "There's an additional combat phase after this phase. At the beginning of that combat, untap all creatures you control."
    (Moraug) as the one instruction they are (scripts._parse_effects)."""
    return _EXTRA_THEN.sub(r"\g<x> [at the beginning of that combat, \g<u>].", body) if "At the beginning of that combat" in body else body
_MUST = re.compile(r"(?P<o>.+?) attacks? this turn if able")
_MUST_COMBAT = re.compile(r"(?P<o>.+?) attacks this combat if able")  # -- trigger other (wave 26B) -- 508.1d, this combat only
_MUST_THAT = re.compile(r"(?P<o>.+?) attacks that player this combat if able")  # -- random choices (wave 47B) -- the player an instruction before picked (Ruhan)
_MUST_YOU = re.compile(r"(?P<o>target creature(?: an opponent controls)?) attacks you this turn if able")  # -- activated other (wave 21E) --
_EACH_COMBAT = re.compile(r"(?P<o>.+?) (?:attack each combat if able(?P<pl> and attack a player other than you if able)?"
                         r"|attacks each combat if able(?P<sg> and attacks a player other than you if able)?)"
                         r"(?P<eot> until end of turn)?")
# -- tapped and attacking (wave 38B) -- "for each opponent, you create a 2/2 … token that's tapped and attacking that opponent" (Stampede Surfer, Veteran
# Soldier): the same instruction as "… attacking that player", the player being the one this opponent is (508.4: the effect says what it attacks)
_EACH_OPP = re.compile(r"for each opponent, (?:you )?(?P<create>create .+? token(?:s)? that's tapped and attacking) "
                       r"(?:that player(?P<pw> or a planeswalker they control)?|that opponent)")
_AND_EXTRA = re.compile(r"(?P<a>.+?),? and (?P<b>after this (?:main |combat )?phase, there is an additional combat phase.*)")
_BLOCK_CAP = re.compile(r"each opponent can't block with more than (?P<n>one|two|three|four|five) creatures? this combat")
_REMOVE = re.compile(r"remove (?P<o>.+?) from combat")
_MAZE = re.compile(r"prevent all combat damage that would be dealt to and dealt by (?P<o>that creature|it|target creature(?: you control)?|~)"
                   r" this turn")
_DOUBLE = re.compile(r"double (?:the (?P<w1>power and toughness|power|toughness) of (?P<o1>.+?)|(?P<o2>.+?)'s "  # (-- trigger other (wave 41C) -- toughness alone, Rasaad yn Bashir)
                     r"(?P<w2>power and toughness|power|toughness)|(?P<o3>its) (?P<w3>power and toughness|power|toughness)) until end of turn")
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
    war = re.fullmatch(r"this turn, creatures can't (?P<mode>attack|block) unless their controller pays \{X\} for each (?:attacking|blocking) creature they control", text, re.IGNORECASE)
    if war:
        return [{'do': 'restrict', 'who': 'each_creature', 'rules': [f"declaration_cost:{war['mode'].lower()}:{'{@x}'}:@cost_instance"]}], None
    upkeep = re.fullmatch(r"(?P<p>you get|that player gets) (?P<n>an|that many) additional upkeep steps? after this (?P<after>step|phase)", text)
    if upkeep:
        return [{"do": "extra_steps", "kind": "upkeep", "who": "you" if upkeep["p"] == "you get" else "event_player",
                 "n": {"event_amount": 1} if upkeep["n"] == "that many" else 1, "after": upkeep["after"]}], None
    if text in ("there is an additional beginning phase after this phase", "there is an additional end step after this step"):
        return [{"do": "extra_steps", "kind": "beginning" if "beginning" in text else "end"}], None
    if (many := re.fullmatch(r"after this main phase, there are (?P<n>two|three|four) additional combat phases", text)) is not None:
        return [{"do": "extra_phases", "after": "main", "main": False,
                 "count": {"two": 2, "three": 3, "four": 4}[many["n"]]}], None
    m = _EXTRA.fullmatch(text)
    if m:
        after = "main" if m["main"] or m["main2"] else "combat" if m["combat"] or m["combat2"] else "phase"
        then = None
        if m["then"]:  # (wave 49B) the untap that begins that combat: one instruction without a target of its own
            from app.rules import scripts

            inner = scripts._clause(m["then"])
            if inner is None or inner[1] is not None or [x["do"] for x in inner[0]] != ["untap"]:
                return None
            then = inner[0]
        return [{"do": "extra_phases", "after": after, "main": bool(m["and"]), **({"then": then} if then else {})}], None
    m = _AND_EXTRA.fullmatch(text)
    if m:  # "untap all attacking creatures and after this phase, there is an additional combat phase"
        from app.rules import scripts

        left, right = scripts._clause(m["a"]), clause(m["b"])
        if left is None or right is None:
            return None
        return left[0] + right[0], left[1]
    m = _BLOCK_CAP.fullmatch(text)
    if m:  # -- commander sweep (wave 49B) -- 509.1b: "Each opponent can't block with more than one creature this combat." (Mirri)
        return [{"do": "block_cap", "n": _NUMBERS[m["n"]]}], None
    m = _REMOVE.fullmatch(text)
    if m:  # 506.4
        found = _object(m["o"], host=True)  # (wave 40B: "remove enchanted creature from combat", 303.4b)
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
        return [{"do": "double_pt", "who": found[0], "toughness": what != "power", **({"power": False} if what == "toughness" else {})}], found[1]
    m = _EACH_COMBAT.fullmatch(text)
    if m:  # (with a duration: "until end of turn", or "until your next turn, …" read as that: ``unwrapped``)
        restricted = _restrict(m["o"], ["must_attack"] + ([f"{OTHER_THAN}:@you"] if m["pl"] or m["sg"] else []))
        if restricted is None:
            return None
        return ([restricted[0][0]] if m["eot"] else [{**restricted[0][0], "each_combat": True}]), restricted[1]
    m = _MUST_THAT.fullmatch(text)
    if m:  # 508.1d, Ruhan ruling 2011-09-22: that player, not a planeswalker of theirs; this combat only (611.2), the player bound by random_choice
        that = _restrict(m["o"], [f"{ATTACK_PLAYER}:@that"])
        return ([{**that[0][0], "player": "that_player", "duration": "end_of_combat"}], that[1]) if that is not None else None
    m = _MUST_YOU.fullmatch(text)
    if m:  # 508.1d: it attacks the effect's controller ("you") if able (ATTACK_PLAYER, as encore's tokens)
        return _restrict(m["o"], [f"{ATTACK_PLAYER}:@you"])
    m = _MUST.fullmatch(text)
    if m:
        return _restrict(m["o"], ["must_attack"])
    m = _MUST_COMBAT.fullmatch(text)
    if m:  # -- trigger other (wave 26B) -- "That token attacks this combat if able." (Legion Warboss): ends with the combat (611.2)
        combat = _restrict(m["o"], ["must_attack"])
        return ([{**combat[0][0], "duration": "end_of_combat"}], combat[1]) if combat is not None else None
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


def _object(phrase: str, *, each: bool = False, host: bool = False) -> tuple[str, Any] | None:
    """An object reference: a target, "it" / "that creature", ~ (and with ``each``, a group: "each creature you
    control"; with ``host``, -- attached events (wave 40B) -- "enchanted creature") -> (who, target group)."""
    from app.rules import language

    if phrase == "its":
        phrase = "it"
    try:
        kind, key, group = language.ref(phrase)
    except language._Fail:
        return None
    if kind in ("players", "them") or (kind == "host" and not host) or (kind == "each" and not each):
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
    if not e.get("pw"):
        from app.rules import replace, values

        source = ctx.get("source_card")
        requests = [(me, e["token"], values.evaluate(plan, ctx, e["n"]), source, True) for _ in players]
        made = replace.create_token_batch(plan, requests, ctx=ctx, bind=None, then=effects._then(ctx, e),
                                         recipient_refs=players, creation_atoms=["opponent:" + pid for pid in players])
        return made is not None
    from app.rules import replace, token_attack_continuations, values

    continuation = token_attack_continuations.terminal(ctx, players)
    requests = [(me, {**e["token"], '_effect_tapped': True}, values.evaluate(plan, ctx, e["n"]),
                 ctx.get("source_card"), True) for _ in players]
    made = replace.create_token_batch(plan, requests, ctx=ctx, bind=None, then=continuation,
                                     creation_atoms=["opponent:" + pid for pid in players],
                                     receipt_bind=token_attack_continuations.BINDING)
    if made is None:
        return False
    return token_attack_continuations.finish(plan, continuation)


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
        if card.is_attacking:
            plan.do({"type": "attack", "card_ids": [cid], "target": None}, actor=ctx["controller"])
            plan.rules.blocked = [c for c in plan.rules.blocked if c != cid]
        if card.is_blocking:
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
        p = power(card, ch) if e.get("power", True) else 0  # (701.10b: +X/+0 for its power, +0/+X for its toughness)
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
        options = [DecisionOption(id="none", label=f"No token for {plan.name(pid)}"),
                   DecisionOption(id=pid, label=f"Create a token for {plan.name(pid)}")]
        decide(plan, player=me, kind="choose_one",
               prompt=f"{ctx.get('name') or 'Myriad'}: create a token copy for {plan.name(pid)}?",
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
    from app.rules import copying, replace, token_attack_continuations

    # Older saved decisions may name a planeswalker. Resolve that old choice
    # only to its opponent's action; each actual output chooses its defender.
    players = [target if target in plan.state.players else plan.state.cards[target].controller
               for target in ctx.get("myriad") or []
               if target in plan.live() or target in plan.state.cards and plan.state.cards[target].zone.endswith(':battlefield')]
    if not players:
        return True
    continuation = token_attack_continuations.terminal(ctx, players)
    if not copying.token_copy(plan, ctx, {"do": "token_copy", "who": "self", "n": 1, "tapped": True,
                                          "as": e.get("as"), "creation_recipients": players,
                                          "receipt_bind": token_attack_continuations.BINDING},
                              then=replace.rerun_then(ctx, e)):
        return False
    return token_attack_continuations.finish(plan, continuation)


def encore_attack(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """-- casting extras (wave 18E) -- 702.141a: "For each opponent, create a token that's a copy of this card that attacks that
    opponent this turn if able": each printed opponent action retains the exact objects created by it, including replacements and must attack that player this turn if able (508.1d)."""
    from app.rules import context, effects, layers, token_attack_continuations

    receipts = ctx.pop('_encore_created', None)
    if receipts is not None:
        pairs: list[tuple[str, str]] = []
        for raw in receipts:
            atom = token_attack_continuations.CreatedAtom.model_validate(raw)
            pid = atom.atom.removeprefix('opponent:')
            if pid not in plan.live():
                continue
            pairs.extend((card.id, pid) for ref in atom.objects
                         if (card := context._same(plan, ref)) is not None and card.zone.endswith(':battlefield'))
    else:
        # Preserve native pre-extension saves whose already-created tokens have
        # no typed receipt. Fresh instructions always supply exact atom refs.
        tokens = [c for c in effects._cards(plan, ctx, e["who"]) if plan.state.cards[c].zone.endswith(":battlefield")]
        pairs = list(zip(tokens, [p for p in plan.apnap() if p != ctx["controller"] and p in plan.live()], strict=False))
    for cid, pid in pairs:
        layers.add_effect(plan, affected=[plan.oid(plan.state.cards[cid])], layer="6", source=ctx.get("source_object"),
                          controller=ctx["controller"], imposes=(f"{ATTACK_PLAYER}:{pid}",), label="Attacks that player if able",
                          source_card=ctx.get("source_card"))
    return True


def block_cap(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """-- commander sweep (wave 49B) -- 509.1b: each opponent of the ability's controller can't block with more than N creatures this combat (the smallest N
    stands); the cap is dropped as the combat ends (``combat.end_combat``)."""
    caps = plan.rules.block_caps
    for pid in plan.live():
        if pid != ctx["controller"]:
            caps[pid] = min(caps.get(pid, 99), int(e["n"]))
    return True


# -- blocking tokens (wave 50J) -- "Whenever Brimaz blocks a creature, create a 1/1 white Cat Soldier creature token with vigilance that's blocking that creature."
# 509.4: a creature put onto the battlefield blocking is a blocking creature that never "blocked" (no block triggers); 509.4a: if the creature it is to block is no longer
# attacking, or its controller isn't a defending player for it, it enters but never blocks; 509.4b: requirements and restrictions of the declaration don't apply.
# Read only where the creature is the one the trigger's source blocks (so it is a blocked creature already: an unblocked attacker would stay unblocked, 509.1h)
_BLOCKING_TOKEN = re.compile(r"^(?P<make>[Cc]reate (?:a|an) [^.]+? token[^.]*?) that's blocking that creature\.$")


def blocking_token(body: str, it: str | None, parse: Any) -> tuple[list[dict[str, Any]], Any, bool] | None:
    m = _BLOCKING_TOKEN.match(body.strip())
    if m is None or it != "event":
        return None
    found = parse(m["make"] + ".", it)
    if found is None or len(found[0]) != 1 or found[0][0].get("do") != "create_token" or found[1] is not None or found[2]:
        return None
    return [{**found[0][0], "as": "blk0"}, {"do": "enter_blocking", "who": "ref:blk0", "blocked": "event"}], None, False


def enter_blocking(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import effects

    for att_id in effects._cards(plan, ctx, e["blocked"]):
        attacker = plan.state.cards[att_id]
        for cid in effects._cards(plan, ctx, e["who"]):
            token = plan.state.cards[cid]
            target = attacker.attacking
            protected = target is not None and (target.id == token.controller or (
                target.id in plan.state.cards and plan.state.cards[target.id].controller == token.controller))  # (a planeswalker's controller; a battle's protector: not read)
            if attacker.zone.endswith(":battlefield") and token.zone.endswith(":battlefield") and protected and plan.ch(token).is_creature:
                plan.do({"type": "block", "card_id": cid, "attacker_id": att_id, "also": token.blocking is not None}, actor=ctx["controller"])
                plan.note(f"{token.name} enters blocking {plan.ch(attacker).name}", [cid, att_id], actor=ctx["controller"])
    return True


PRIMITIVES = {"extra_steps": extra_steps, "enter_blocking": enter_blocking, "block_cap": block_cap, "encore_attack": encore_attack, "extra_phases": extra_phases, "create_attacking_each": create_attacking_each,
              "remove_from_combat": remove_from_combat, "double_pt": double_pt,
              "myriad_choose": myriad_choose, "myriad_create": myriad_create}
RESUME: dict[str, Any] = {"attack_each_opponent": resume_attack_each, "myriad_pick": resume_myriad}


# Saved native post-creation choices are registered on every fresh process load.

_token_attack_continuations.register()
RESUME['token_attack_created'] = _token_attack_continuations.resume

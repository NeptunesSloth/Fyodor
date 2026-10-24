"""-- if you do (wave 100B) -- "if you do / if they do / this way" riders read onto the existing grammar.

Each form here is a narrow reading of one wording, rewritten onto instructions the engine already carries out
(CR 2026-09-25):

* "Defending player sacrifices a creature of their choice. If they do, …" (Gisa's Favorite Shovel): 118.12, the sacrifice
  is the thing done; "if they do" asks whether they did — the instruction's own "sacrificed this way" (this_way.py: 701.21a).
* "… discard a card. If you discard a land card this way, put it from your graveyard onto the battlefield tapped." (Silvan
  Reveler): the discarded card (701.9a, 400.7: the new object in the graveyard), only while it is still in that graveyard —
  a card a replacement effect put elsewhere isn't there to put onto the battlefield (``from``: effects.return_card).
* "~ deals 2 damage to any target …. If a player is dealt damage this way, they discard a card." (Sonic Shrieker): the one
  target, when it is a player and some damage was actually dealt to it (120.3, 615.1: this_way.dealt_to).
* "Draw a card if [condition]. If you don't draw a card this way, …" (Trade Route Envoy): 608.2c, the draw is judged as it is
  made — a draw that didn't happen (the condition was false, or no card was drawn: 121.2, 121.3) is "don't draw".
* "~ deals 1 damage to any target. A creature dealt damage this way can't block this turn." (Ballista Watcher): the
  objects the damage was actually dealt to (615.1), that were creatures (a player or a noncreature planeswalker isn't).
"""

from __future__ import annotations

import json
import re
from typing import Any

Found = tuple[list[dict[str, Any]], Any, bool]

_THEY_DO = re.compile(r"\b(?P<a>(?:[Dd]efending player|[Tt]arget opponent|[Tt]arget player|[Tt]hat player) sacrifices (?P<det>an?) (?P<what>[a-z]+) "
                      r"of their choice)\. If they do, ")
_PUT_DISCARDED = re.compile(r"^(?P<a>.+?\bdiscard a card)\. If you (?:discard|discarded) (?P<w>an? [a-z ]+? card) this way, put it from your graveyard "
                            r"onto the battlefield(?P<t> tapped)?\.$")
_HIT_DISCARD = re.compile(r"^(?P<a>(?:~|it) deals (?P<n>\d+) damage to any target(?: and you gain \d+ life)?)\. If a player is dealt damage this way, "
                          r"(?:they discard|that player discards) a card\.$")
_DRAW_IF = re.compile(r"^draw a card if (?P<c>[^.,]+)\. If you don't draw a card this way, (?P<b>[^.]+)\.$")
_TAP_IF_HURT = re.compile(r"^(?P<a>~ deals \d+ damage to you unless [^.]+)\. If (?:it|~) deals damage to you this way, tap it\.$")  # ("it": the source that dealt it)
_DEALT_CANT_BLOCK = re.compile(r"^(?P<a>[^.]+? deals (?:\d+|X) damage to [^.]+)\. (?:A creature|Creatures) dealt damage this way can't block this turn\.$")
_GIVE_SOURCE = re.compile(r"^you may exile (?P<t>target [^.]+)\. If you do, its controller gains control of ~\.$")
_EXILED_MV = re.compile(r"^(?P<a>you may exile target [^.]+ card from a graveyard\. If you do, create [^.]+ token[^.]*)\. Put a \+1/\+1 counter on it if the exiled "
                        r"card's mana value is (?P<n>\d+) or greater\.$")
# Same instructions, other words (608.2c):
_REWRITES = [
    # Assault Suit: "you may have that player gain control …. If you do, untap it." — 603.5: declining does neither; "it" is the creature that changed control
    (re.compile(r"^(you may have that player gain control of equipped creature until end of turn)\. If you do, untap it\.$"), r"\1. Untap it."),
    # Check for Traps: "they" is the target opponent whose hand was revealed
    (re.compile(r"^(Target opponent reveals their hand\. You choose a nonland card from it\. Exile that card\. If [^.]+ this way), they lose (\d+) life\. "
                r"Otherwise, you lose (\d+) life\.$"), r"\1, that player loses \2 life. Otherwise, you lose \3 life."),
    # Azra Bladeseeker: 102.4, outside a game between teams "your team" is "you"; the one who discarded draws (118.12: a discard can't be begun and not made)
    (re.compile(r"^each player on your team may discard a card, then each player who discarded a card this way draws a card\.$"),
     "you may discard a card. If you do, draw a card."),
]


_CONNIVES = re.compile(r"^(?:it|~) connives\. When it connives this way, (?P<b>[^.]+)\.$")
_EMPTY_GY = re.compile(r"^(?P<a>Exile target card from an opponent's graveyard)\. If no cards are in that graveyard, (?P<b>flip ~)\.$")
GY_EMPTY = "gy_empty100b"


def parse(body: str, it: str | None, event_player: bool) -> Found | None:
    text = body.strip()
    for form in (_put_discarded, _hit_discard, _draw_if, _dealt_cant_block, _give_source, _exiled_mv, _connives, _empty_gy, _truce, _each_who_lost):
        if (found := form(text, it, event_player)) is not None:
            return found
    for pattern, repl in _REWRITES:
        if pattern.match(text):
            return _effects(pattern.sub(repl, text), it, event_player)
    if _THEY_DO.search(text):
        return _they_do(text, it, event_player)
    if (hurt := _TAP_IF_HURT.match(text)) is not None:  # (Mishra's War Machine: 120.3, the damage actually dealt to you — none if it was prevented, 615.1)
        return _effects(f"{hurt['a']}. If it deals damage to you this way, tap ~.", it, event_player)
    return None


def _effects(text: str, it: str | None, event_player: bool) -> Found | None:
    from app.rules import scripts

    return scripts.parse_effects(text, it, event_player=event_player)


def _they_do(text: str, it: str | None, event_player: bool) -> Found | None:
    """118.12: "If they do" after the sacrifice is "if a creature was sacrificed this way" (the edict's own count)."""
    found = _effects(_THEY_DO.sub(lambda m: f"{m['a']}. If {m['det']} {m['what']} was sacrificed this way, ", text), it, event_player)
    if found is None or not any(e.get("do") == "edict" and e.get("as") for e in found[0]):
        return None
    return found


def _put_discarded(text: str, it: str | None, event_player: bool) -> Found | None:
    m = _PUT_DISCARDED.match(text)
    if m is None:
        return None
    found = _effects(f"{m['a']}. If you discarded {m['w']} this way, return it to the battlefield{m['t'] or ''}.", it, event_player)
    if found is None or not found[0] or found[0][-1].get("do") != "return_card" or not str(found[0][-1].get("who")).startswith("ref:"):
        return None
    effects = [*found[0][:-1], {**found[0][-1], "from": "graveyard", "under": "you"}]  # (110.2a: the player who puts it onto the battlefield controls it)
    return effects, found[1], found[2]


def _hit_discard(text: str, it: str | None, event_player: bool) -> Found | None:
    m = _HIT_DISCARD.match(text)
    if m is None:
        return None
    found = _effects(f"{m['a']}. If a player is dealt damage this way, you draw a card.", it, event_player)
    if found is None or not found[0] or found[0][-1] != {"do": "draw", "who": "you", "n": 1} or not any(e.get("bind_hit") for e in found[0]):
        return None
    if found[1] != "any" and not (isinstance(found[1], list) and len(found[1]) == 1):
        return None
    return [*found[0][:-1], {"do": "discard", "who": "target", "n": 1}], found[1], found[2]  # (the gate: the target is a player dealt damage)


def _draw_if(text: str, it: str | None, event_player: bool) -> Found | None:
    m = _DRAW_IF.match(text)
    if m is None:
        return None
    first, rest = _effects(f"draw a card if {m['c']}.", it, event_player), _effects(f"{m['b'][0].upper()}{m['b'][1:]}.", it, event_player)
    if first is None or rest is None or first[1] is not None or rest[1] is not None or first[2] or rest[2]:
        return None
    if len(first[0]) != 2:
        return None
    gate, draw = first[0]
    if gate.get("do") != "only_if" or gate.get("skip") != 1 or draw != {"do": "draw", "who": "you", "n": 1}:
        return None
    name = "e1"
    effects: list[dict[str, Any]] = [gate, {**draw, "as": name},
               {"do": "only_if", "cond": {"value": {"this_way": "drawn", "of": None, "players": "you", "ref_count": name}, "op": "==", "n": 0},
                "skip": len(rest[0])}, *rest[0]]
    return effects, None, False


def _dealt_cant_block(text: str, it: str | None, event_player: bool) -> Found | None:
    m = _DEALT_CANT_BLOCK.match(text)
    if m is None:
        return None
    found = _effects(f"{m['a']}.", it, event_player)
    if found is None:
        return None
    dmg = [i for i, e in enumerate(found[0]) if e.get("do") == "damage"]
    if len(dmg) != 1 or dmg[0] != len(found[0]) - 1 or any(found[0][dmg[0]].get(k) for k in ("dealt_as", "with_next", "bind_hit")):
        return None
    key = f"ref:d{dmg[0]}"
    effects = [*found[0][:-1], {**found[0][-1], "dealt_as": key},
               {"do": "restrict", "who": "union:", "dealt": key, "rules": ["cant_block"], "types": ["Creature"]}]
    return effects, found[1], found[2]


def _give_source(text: str, it: str | None, event_player: bool) -> Found | None:
    """Act of Authority: "you may exile target artifact or enchantment. If you do, its controller gains control of ~." — the exiled
    permanent's controller as it last existed (608.2h), for good (611.2a: no duration)."""
    m = _GIVE_SOURCE.match(text)
    if m is None:
        return None
    found = _effects(f"you may exile {m['t']}. If you do, its controller draws a card.", it, event_player)
    if found is None or not found[0]:
        return None
    last = found[0][-1]
    if last.get("do") != "draw" or not re.fullmatch(r"ref:e\d+\.controller", str(last.get("who"))) or last.get("n") != 1:
        return None
    return [*found[0][:-1], {"do": "gain_control", "who": "self", "to": last["who"], "duration": "permanent"}], found[1], found[2]


def _exiled_mv(text: str, it: str | None, event_player: bool) -> Found | None:
    """Summoner's Sending: "… Put a +1/+1 counter on it if the exiled card's mana value is 4 or greater." — "it" is the token, the mana value is
    the exiled card's (the new object in exile, 400.7j)."""
    m = _EXILED_MV.match(text)
    if m is None:
        return None
    found = _effects(f"{m['a']}. Put a +1/+1 counter on it.", it, event_player)
    if found is None or len(found[0]) < 4:
        return None
    effects = [dict(e) for e in found[0]]
    exile, gate, last = effects[0], effects[1], effects[-1]
    if exile.get("do") != "exile" or exile.get("who") != "target" or gate.get("do") != "only_if" or "succeeded" not in gate.get("cond", {}) \
            or last.get("do") != "add_counters" or gate["skip"] != len(effects) - 2:
        return None
    exile.setdefault("as", "e0")
    gate["skip"] += 1
    check = {"do": "only_if", "cond": {"object": f"ref:{exile['as']}", "stat": "mana_value", "op": ">=", "n": int(m["n"])}, "skip": 1}
    return [*effects[:-1], check, last], found[1], found[2]


def _connives(text: str, it: str | None, event_player: bool) -> Found | None:
    """Psychic Pickpocket, Obscura Interceptor: "it connives. When it connives this way, return up to one target …" — 701.50f: it connives once the
    process is complete, even if the draw or the discard was impossible (and 701.50b: even if it left the battlefield), so the reflexive ability
    (603.12) always triggers; its target is chosen as it is put on the stack, after the connive."""
    from app.rules import scripts

    m = _CONNIVES.match(text)
    if m is None or it != "self":
        return None
    first = _effects("it connives.", it, event_player)
    body = _effects(f"{m['b'][0].upper()}{m['b'][1:]}.", None, False)
    if first is None or first[0] != [{"do": "connive", "who": "self", "n": 1}] or body is None or not body[0]:
        return None
    if re.search(r'"(?:event|it|self_gone)"|event_amount|"that_', json.dumps(body[:2], default=str)):
        return None  # (the reflexive ability has no event of its own to name)
    reflex = {"do": "reflexive", "cond": {"all": []},
              "ability": {"kind": "triggered", "trigger": "reflexive", "effects": body[0], "optional": body[2], **scripts.target_fields(body[1])}}
    return [*first[0], reflex], None, False


def _empty_gy(text: str, it: str | None, event_player: bool) -> Found | None:
    """Nezumi Graverobber: "Exile target card from an opponent's graveyard. If no cards are in that graveyard, flip this creature." — the graveyard
    the target card was in (its owner's, 404.2), judged after the exile (608.2c)."""
    m = _EMPTY_GY.match(text)
    if m is None:
        return None
    first, flip = _effects(f"{m['a']}.", it, event_player), _effects(f"{m['b'][0].upper()}{m['b'][1:]}.", it, event_player)
    if first is None or flip is None or first[0] != [{"do": "exile", "who": "target"}] or flip[0] != [{"do": "flip", "who": "self"}] or flip[1] is not None:
        return None
    return [{"do": "exile", "who": "target", "as": "e0"}, {"do": GY_EMPTY, "of": "e0", "skip": 1}, *flip[0]], first[1], first[2]


_EACH_WHO_LOST = re.compile(r"^Return all creatures to their owners' hands\. For each opponent who controlled a creature returned this way, (?P<b>you create [^.]+\.(?:\")?)$")


def _each_who_lost(text: str, it: str | None, event_player: bool) -> Found | None:
    """Faerie Slumber Party: "For each opponent who controlled a creature returned this way, you create …" — the opponents who controlled (as each
    creature last existed, 608.2h) at least one creature the bounce returned to a hand, each one once (608.2c)."""
    from app.rules import selectors

    m = _EACH_WHO_LOST.match(text)
    if m is None:
        return None
    found = _effects(f"Return all creatures to their owners' hands. For each opponent, {m['b']}", it, event_player)
    if found is None or len(found[0]) != 3 or found[1] is not None:
        return None
    bounce, where, make = (dict(e) for e in found[0])
    creature = selectors.parse("creature")
    if bounce.get("do") != "bounce" or where.get("do") != "players_where" or where.get("pred") != {"any": True} or make.get("do") != "create_token" \
            or creature is None:
        return None
    bounce["as"] = "e0"
    where["pred"] = {"tw": {"this_way": "returned", "of": creature.key(), "ref_count": "e0"}, "has": True, "n": 1}
    return [bounce, where, make], None, found[2]


def gy_empty(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """The gate: the next ``skip`` instructions happen only if the graveyard of the exiled card's owner has no cards."""
    from app.rules import context

    refs = context.refs(ctx).get(e["of"]) or {}
    owners = {plan.state.cards[str(o["card"])].owner for o in refs.get("objects") or [] if str(o.get("card")) in plan.state.cards}
    if len(owners) != 1 or plan.state.zones.get(f"{owners.pop()}:graveyard"):
        ctx["next"] = min(len(ctx["effects"]), ctx["next"] + int(e["skip"]))
    return True


# -- Truce, Temporary Truce: "Each player may draw up to two cards. For each card less than two a player draws this way, that player gains 2 life."
# 101.4: each player chooses in turn order (APNAP) how many to draw, then the draws happen (121.2c: the active player first); the life follows
# what each actually drew (121.2a, 614.11: a draw a replacement effect replaced, or one from an empty library, wasn't a card drawn this way).
_TRUCE = re.compile(r"^Each player may draw up to two cards\. For each card less than two a player draws this way, that player gains 2 life\.$")
TRUCE, TRUCE_ASK, TRUCE_DRAW, TRUCE_LIFE = "truce100b", "truce_ask100b", "truce_draw100b", "truce_life100b"


def _truce(text: str, it: str | None, event_player: bool) -> Found | None:
    return ([{"do": TRUCE, "n": 2, "life": 2}], None, False) if _TRUCE.match(text) else None


def truce(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    at = ctx["next"]
    added = [{"do": TRUCE_ASK, "player": p, "n": e["n"]} for p in plan.apnap() if p in plan.live()]
    ctx["effects"][at:at] = [*added, {"do": TRUCE_DRAW}, {"do": TRUCE_LIFE, "n": e["n"], "life": e["life"]}]  # (in place, as tempting.tempt)
    ctx[TRUCE] = {}
    return True


def truce_ask(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.game.rules_state import DecisionOption
    from app.rules.plan import decide

    if e["player"] not in plan.live():
        return True
    decide(plan, player=e["player"], kind="choose_one", prompt=f"{ctx.get('name') or 'It'}: draw how many cards (up to {e['n']})?",
           options=[DecisionOption(id=str(i), label=f"Draw {i}") for i in range(int(e["n"]) + 1)], resume={"step": TRUCE_ASK, "ctx": ctx})
    return False


def resume_truce_ask(plan: Any, d: Any, chosen: list[str]) -> None:
    from app.rules.effects import continue_effects

    ctx = d.resume["ctx"]
    ctx.setdefault(TRUCE, {})[d.player] = int(chosen[0])
    plan.note(f"{plan.name(d.player)} chose to draw {chosen[0]}", actor=d.player)
    continue_effects(plan, ctx)


def truce_draw(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import history, replace
    from app.rules.effects import _then

    ctx[f"{TRUCE}_before"] = dict(history.log_for(plan).drew)
    each = {p: n for p, n in (ctx.get(TRUCE) or {}).items() if n > 0 and p in plan.live()}
    return not each or replace.draw_cards(plan, list(each), each, then=_then(ctx, e), ctx=ctx)


def truce_life(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import history
    from app.rules.effects import gain_life

    before, now = ctx.get(f"{TRUCE}_before") or {}, history.log_for(plan).drew
    counts = {p: int(e["life"]) * max(0, int(e["n"]) - (now.get(p, 0) - before.get(p, 0))) for p in plan.live()}
    return gain_life(plan, ctx, {"do": "gain_life", "who": "each_player", "n": 0, "counts": counts})


PRIMITIVES = {GY_EMPTY: gy_empty, TRUCE: truce, TRUCE_ASK: truce_ask, TRUCE_DRAW: truce_draw, TRUCE_LIFE: truce_life}
RESUME = {TRUCE_ASK: resume_truce_ask}

"""-- if you do (wave 6F) -- "Each opponent may [cost]. Each opponent who doesn't [effect]." and its forms:

* "each opponent may sacrifice a nontoken creature of their choice. Each opponent who doesn't loses 2 life for each
  instant and sorcery card in your graveyard." (Fandaniel, Telophoroi Ascian);
* "Each player may discard a card. Each player who doesn't loses 3 life." (The Death of Gwen Stacy);
* "each opponent may discard a card or sacrifice a permanent of their choice. Zoyowa deals 3 damage to each opponent who
  didn't." (Zoyowa Lava-Tongue); "Each player may sacrifice an artifact or enchantment. Impulsive Destruction deals 3
  damage to each player who didn't sacrifice a permanent this way.";
* "you may sacrifice an artifact, creature, enchantment, land, or planeswalker. If you do, each opponent may sacrifice a
  permanent of their choice that shares a card type with it. For each opponent who doesn't, that player loses 2 life
  and you draw a card." (Braids, Arisen Nightmare).

CR 2026-09-25: 118.12 — "[A player] may [do something]. If [that player] [doesn't], [effect]": the action is a cost,
paid as the ability resolves; 118.12a — the same as "[effect] unless [that player does something]". Each player is
offered their own payment, in turn order (101.4: the active player chooses first, then each other player in turn
order), each privately and only while it is payable in full (118.3; a sacrifice of a permanent the player doesn't
control, or a discard from an empty hand, isn't); then the effect happens for each player who didn't pay. The
payments and the effects are spliced into the resolution as the instruction is reached (designations.each_unless:
one optional payment per player, then each one's effect behind the negation of their payment).

"shares a card type with it" (Braids): "it" is the permanent sacrificed for the payment before ("If you do"), read
as it last existed on the battlefield (608.2h); the cost each opponent is offered is the sacrifice of a permanent with
any of its card types (205.2a), worked out as the instruction is reached.

Not read: anything after "who doesn't" that names an object, a target or "this way" beyond the plain wording above;
"If no one does" (Browbeat); costs that aren't ones optional_payment pays.
"""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan

Context = dict[str, Any]
_WHO = {"opponent": "each_opponent", "player": "each_player"}
_MAY = re.compile(r"^(?:if (?P<cond>(?!you do\b)[^,]+), )?(?P<if>if you do, )?each (?P<who>opponent|player) may (?P<cost>.+)$")
_FOR_EACH = re.compile(r"^for each (?P<who>opponent|player) who (?:doesn't|didn't), (?P<rest>.+)$")
_WHO_DOESNT = re.compile(r"^each (?P<who>opponent|player) who (?:doesn't|didn't) (?P<rest>.+)$")
_TO_EACH = re.compile(r"^(?P<lead>.+) to each (?P<who>opponent|player) who (?:doesn't|didn't)(?P<this> sacrifice a permanent this way)?$")
# -- each player may (wave 23A) -- "Each player may discard their hand and draw five cards." (Raphael's Technique, Ruin Grinder) and
# "Each player who discarded a card this way draws a card." / "… who does, …": what the players who paid get, once all have paid
_AND_DRAW = re.compile(r"^(?P<cost>discard (?:their|your) hand) and draw (?P<rest>.+)$")
_WHO_DID = re.compile(r"^each (?P<who>opponent|player) who (?:does|did|discarded (?:a card|their hand) this way),? (?P<rest>.+)$")
_TO_EACH_DID = re.compile(r"^(?P<lead>.+) to each (?P<who>opponent|player) who discarded (?:a card|their hand) this way$")
_SHARES = "sacrifice a permanent that shares a card type with it"
_TYPES = ("Artifact", "Battle", "Creature", "Enchantment", "Kindred", "Land", "Planeswalker")


def _third_person(rest: str) -> str:
    """"loses 3 life" → "That player loses 3 life" (the player who didn't pay)."""
    return f"That player {rest}"


def pair(text: str, following: str | None, effects: list[dict[str, Any]], last_payment: str | None
         ) -> tuple[list[dict[str, Any]], int] | None:
    """The effects of "each opponent may [cost]." and the "who doesn't" sentence after it (``following``, as written), with the
    number of sentences they read (1 or 2), or None (not this grammar, or a form that isn't read)."""
    from app.rules import optional_payment, scripts

    m = _MAY.match(text)
    if m is None:
        return None
    cost_phrase = m["cost"].replace(" of their choice", "")
    then_texts: list[str] = []
    opp_texts: list[str] = []
    if (inline := _AND_DRAW.match(cost_phrase)) is not None:  # (one optional instruction: the draw is for the players who chose it)
        cost_phrase = "discard your hand"  # (the payer's own: each_may asks every player for theirs)
        then_texts.append(f"That player draws {inline['rest']}")
    elif following is None:
        return None
    nxt = re.sub(r"^then ", "", scripts._lower_first((following or "").rstrip(".").strip()))  # (wave 23A: "Then ~ deals 5 damage to each …")
    entry: dict[str, Any] = {"do": "each_may", "who": _WHO[m["who"]]}
    if cost_phrase == _SHARES:
        if last_payment is None or not m["if"]:
            return None
        pay = next(e for e in effects if e.get("bind") == last_payment)
        if not re.fullmatch(r"Sacrifice (?:a|an) [a-z]+(?: or [a-z]+)*", str(pay.get("cost") or "")) or pay.get("alts"):
            return None  # (one permanent sacrificed: "it")
        entry["shares_type"] = last_payment
    elif (cost := optional_payment.cost_text(cost_phrase)) is not None:
        entry["cost"] = cost
    elif (alts := optional_payment.alternatives(cost_phrase)) is not None:
        entry["alts"] = alts
    else:
        return None
    body: str | None = None
    used = 2
    if (d := _WHO_DID.match(nxt)) is not None and d["who"] == m["who"] and entry.get("cost", "").startswith("Discard"):
        then_texts.append(_third_person(d["rest"]))
    elif (td := _TO_EACH_DID.match(nxt)) is not None and td["who"] in (m["who"], "opponent") and entry.get("cost", "").startswith("Discard"):
        opp_texts.append(f"{td['lead']} to that player")  # ("each opponent who …" among each player: not the controller)
    elif then_texts and not opp_texts:
        used = 1  # (the inline form stands alone; the sentence after it is its own)
    elif (f := _FOR_EACH.match(nxt)) is not None and f["who"] == m["who"]:
        body = f["rest"][:1].upper() + f["rest"][1:]
    elif (w := _WHO_DOESNT.match(nxt)) is not None and w["who"] == m["who"]:
        body = _third_person(w["rest"])
    elif (t := _TO_EACH.match(nxt)) is not None and t["who"] == m["who"]:
        if t["this"] and not (entry.get("cost") or "").startswith("Sacrifice") and not all(
                a.startswith("Sacrifice") for a in entry.get("alts") or ()):
            return None  # ("who didn't sacrifice a permanent this way": only after a sacrifice)
        body = f"{t['lead']} to that player"
    if body is None and not then_texts and not opp_texts:
        return None

    def plain(sentence: str) -> list[dict[str, Any]] | None:
        parsed = scripts.parse_effects(sentence + ".", "self", event_player=True)
        if parsed is None or parsed[1] is not None or parsed[2] or not parsed[0]:
            return None
        dumped = json.dumps(parsed[0])
        if '"ref:' in dumped or '"target' in dumped or '"it"' in dumped or "event_amount" in dumped or "this_way" in dumped:
            return None  # (only "that player", "you" and plain counts)
        return list(parsed[0])

    if body is not None:
        if (inner := plain(body)) is None:
            return None
        entry["effects"] = inner
    for key, texts_ in (("then", then_texts), ("then_opp", opp_texts)):  # (-- each player may (wave 23A) -- what the players who paid get)
        if texts_:
            done = [plain(t) for t in texts_]
            if any(x is None for x in done):
                return None
            entry[key] = [e for x in done for e in (x or [])]
    out = [entry]
    if m["if"]:
        if not last_payment:
            return None
        out = [{"do": "only_if", "cond": {"succeeded": last_payment}, "skip": 1}, *out]
    if m["cond"]:  # ("At the beginning of your end step, if you descended this turn, each opponent may …": 603.4)
        from app.rules import conditions

        cond = conditions.parse(m["cond"], objects=True)
        if cond is None:
            return None
        out = [{"do": "only_if", "cond": cond, "skip": len(out)}, *out]
    return out, used


_UNLESS_EACH = re.compile(r"^(?:if (?P<cond>[^,]+), )?each (?P<who>opponent|player) (?P<lead>.+?) unless (?:they|that player) (?P<act>.+)$")


def unless_sentence(text: str) -> list[dict[str, Any]] | None:
    """-- if you do (wave 15C) -- "Each opponent loses 3 life unless they discard a card." / "… unless that player sacrifices a nonland
    permanent of their choice or discards a card." (Court of Ambition, Nicol Bolas, the Deceiver): 118.12a reads it as "Each
    opponent may [cost]. Each opponent who doesn't [effect]" — the same entry as ``pair`` builds (turn order, 101.4)."""
    from app.rules import optional_payment, scripts

    m = _UNLESS_EACH.match(text)
    if m is None:
        return None
    act = re.sub(r"\b(pays?|discards?|sacrifices?|returns?|exiles?)\b", lambda v: v[1].rstrip("s") if v[1] != "pays" else "pay", m["act"])
    if " another " in f" {act} ":
        return None  # ("another" than what: not read)
    act = act.replace(" of their choice", "")
    entry: dict[str, Any] = {"do": "each_may", "who": _WHO[m["who"]]}
    if (cost := optional_payment.cost_text(act)) is not None:
        entry["cost"] = cost
    elif (alts := optional_payment.alternatives(act)) is not None:
        entry["alts"] = alts
    else:
        return None
    if not optional_payment.defers(entry.get("cost"), entry.get("alts")):
        return None  # (a mana payment by each opponent in turn: refused since wave 4C, as before)
    parsed = scripts.parse_effects(_third_person(m["lead"]) + ".", "self", event_player=True)
    if parsed is None or parsed[1] is not None or parsed[2] or not parsed[0]:
        return None
    dumped = json.dumps(parsed[0])
    if '"ref:' in dumped or '"target' in dumped or '"it"' in dumped or "event_amount" in dumped or "this_way" in dumped:
        return None
    entry["effects"] = parsed[0]
    out = [entry]
    if m["cond"]:  # ("At the beginning of your end step, if you attacked this turn, each opponent loses …": 603.4)
        from app.rules import conditions

        cond = conditions.parse(m["cond"], objects=True)
        if cond is None:
            return None
        out = [{"do": "only_if", "cond": cond, "skip": 1}, *out]
    return out


def _for(value: Any, pid: str) -> Any:
    """The effects with "that player" (event_player) as ``pid``."""
    if value == "event_player":
        return f"player:{pid}"
    if isinstance(value, list):
        return [_for(v, pid) for v in value]
    if isinstance(value, dict):
        return {k: _for(v, pid) for k, v in value.items()}
    return value


def _shared_cost(plan: Plan, ctx: Context, bind: str) -> str | None:
    """"Sacrifice a permanent that shares a card type with it": the card types of the permanent sacrificed (608.2h)."""
    from app.rules import context

    found = context.info(plan, ctx, bind)
    if found is None:
        return None
    types = [t for t in _TYPES if t in found[1].types]
    if not types:
        return None
    words = " or ".join(t.lower() for t in types)
    return f"Sacrifice {'an' if words[0] in 'aeiou' else 'a'} {words}"


def each_may(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """One optional payment per player of the group (turn order, 101.4), then the effect for each who didn't pay."""
    from app.rules import effects, optional_payment

    players = [p for p in plan.apnap() if p in effects._players(plan, ctx, e["who"])]
    cost = e.get("cost")
    if e.get("shares_type"):
        cost = _shared_cost(plan, ctx, e["shares_type"])
        if cost is None:  # (no card type to share: no payment can be made — every player "doesn't")
            cost = ""
    at = ctx["next"]
    tag = f"m{at}_"
    added: list[dict[str, Any]] = []
    # -- review (wave 6R) -- 101.4: every choice first (in turn order), then the payments together (pay_deferred)
    defer = optional_payment.defers(cost, None if cost is not None else e.get("alts"))
    for i, p in enumerate(players):
        pay: dict[str, Any] = {"do": "optional_payment", "who": f"player:{p}", "cost": cost if cost is not None else e["alts"][0], "bind": f"{tag}{i}"}
        if e.get("alts") and cost is None:
            pay["alts"] = list(e["alts"])
        if defer:
            pay["defer"] = True
        added.append(pay)
    if defer and players:
        added.append({"do": "pay_deferred", "binds": [f"{tag}{i}" for i in range(len(players))]})
    for i, p in enumerate(players):
        inner = _for(e.get("effects") or [], p)
        if inner:
            added += [{"do": "only_if", "cond": {"succeeded": f"{tag}{i}", "negate": True}, "skip": len(inner)}, *inner]
        for key in ("then", "then_opp"):  # -- each player may (wave 23A) -- the players who paid: "Each player who discarded a card this way draws a card"
            if e.get(key) and (key == "then" or p != ctx["controller"]):
                done = _for(e[key], p)
                added += [{"do": "only_if", "cond": {"succeeded": f"{tag}{i}"}, "skip": len(done)}, *done]
    ctx["effects"] = [*ctx["effects"][:at], *added, *ctx["effects"][at:]]
    effects.continue_effects(plan, ctx)
    return False


PRIMITIVES = {"each_may": each_may}


def _pay_deferred(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:  # -- review (wave 6R) --
    from app.rules import optional_payment

    return optional_payment.pay_deferred(plan, ctx, e)


PRIMITIVES["pay_deferred"] = _pay_deferred

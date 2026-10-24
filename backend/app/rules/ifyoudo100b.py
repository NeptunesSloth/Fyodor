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
    # Werewolf Ransacker: the one target ("that artifact" is the artifact destroyed; a token counts, one exiled instead doesn't: the 2011-01-22 and 2013-07-01 rulings)
    (re.compile(r"^(you may destroy target artifact)\. If that artifact is put into a graveyard this way, "), r"\1. If an artifact is put into a graveyard this way, "),
    # Koya, Death from Above: 118.12a, "you may pay [cost]. If you don't, [do it]" is "[do it] unless you pay [cost]"
    (re.compile(r"^(.+?)\. At the beginning of the next end step, you may pay ((?:\{[^}]+\})+)\. If you don't, (return that card to the battlefield under its owner's "
                r"control)\.$"), r"\1. At the beginning of the next end step, \3 unless you pay \2."),
    # Invasion of Kaldheim: "that many" is how many cards were exiled (the cards actually in exile, 400.7j), not the trigger event's amount
    (re.compile(r"^exile all cards from your hand, then draw that many cards\. (?=Until the end of your next turn, you may play cards exiled this way\.$)"),
     "Exile all cards from your hand, then draw a card for each card exiled this way. "),
    # Veteran's Voice ("Tap enchanted creature: …", the one card so worded): the creature the cost taps is the enchanted creature (601.2c-h)
    (re.compile(r"^Target creature other than the creature tapped this way (gets \+2/\+1 until end of turn\.)$"), r"Target creature other than enchanted creature \1"),
    # Azra Bladeseeker: 102.4, outside a game between teams "your team" is "you"; the one who discarded draws (118.12: a discard can't be begun and not made)
    (re.compile(r"^each player on your team may discard a card, then each player who discarded a card this way draws a card\.$"),
     "you may discard a card. If you do, draw a card."),
]


_CONNIVES = re.compile(r"^(?:it|~) connives\. When it connives this way, (?P<b>[^.]+)\.$")
_EMPTY_GY = re.compile(r"^(?P<a>Exile target card from an opponent's graveyard)\. If no cards are in that graveyard, (?P<b>flip ~)\.$")
GY_EMPTY = "gy_empty100b"


def parse(body: str, it: str | None, event_player: bool) -> Found | None:
    text = body.strip()
    for form in (_put_discarded, _hit_discard, _draw_if, _dealt_cant_block, _give_source, _exiled_mv, _connives, _empty_gy, _truce, _each_who_lost,
                 _either, _plot_paid, _hand_exile, _dont_sacrifice, _put_mv_x, _fold, _swift, _untap_then, _may_attach, _vanish, _dakra, _durin, _latnam, _surge, _locke, _gy_exile, _manabond, _have_deal, _own_bounce, _clash, _reveal_win, _fishing, _runes, _rally, _long_rest, _bringer, _vault101, _becomes20, _foxglove, _spirit_dragons, _holistic):
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


# -- Kellan Joins Up: "you may exile a nonland card with mana value 3 or less from your hand. If you do, it becomes plotted." 118.12: the exile is
# the payment; "it" is the card it exiled, the new object in exile (400.7j: the payment's moved objects), 702.170c.
_PLOT_PAID = re.compile(r"^(?P<a>you may exile an? [^.]+ from your hand)\. If you do, (?:it|that card) becomes plotted\.$")


def _plot_paid(text: str, it: str | None, event_player: bool) -> Found | None:
    m = _PLOT_PAID.match(text)
    found = _effects(f"{m['a']}. If you do, draw a card.", it, event_player) if m is not None else None
    if found is None or len(found[0]) != 3 or found[0][0].get("do") != "optional_payment" or not str(found[0][0].get("cost")).startswith("Exile ") \
            or found[0][2] != {"do": "draw", "who": "you", "n": 1}:
        return None
    return [*found[0][:2], {"do": "plotted", "who": f"ref:{found[0][0]['bind']}"}], found[1], found[2]


# -- Ego Drain, Specter's Shriek: "… If you don't control a Faerie, exile a card from your hand." / "If you do, that player exiles that card. If a
# nonblack card is exiled this way, exile a card from your hand." — the controller's own choice as it resolves (608.2d, not a target), private
# (their hand, 400.2); with no card in hand nothing is exiled (the Specter's Shriek 2019-10-04 ruling). The opponent's card goes to its owner's
# exile whoever moves it (406.1).
_HAND_EXILE = re.compile(r"^(?P<a>Target opponent reveals their hand\. You (?:may )?choose a nonland card from it\. .+ If [^.,]+), exile a card from your hand\.$")


def _hand_exile(text: str, it: str | None, event_player: bool) -> Found | None:
    from app.rules import selectors

    m = _HAND_EXILE.match(text)
    body = m["a"].replace(" If you do, that player exiles that card.", " If you do, exile that card.") if m is not None else ""
    found = _effects(f"{body}, draw a card.", it, event_player) if m is not None else None
    hand = selectors.parse("card in your hand")
    if found is None or not found[0] or found[0][-1] != {"do": "draw", "who": "you", "n": 1} or found[0][-2].get("do") != "only_if" or hand is None:
        return None
    exile = {"do": "return_choice", "to": "exile", "sel": hand.key(), "n": 1, "upto": False, "random": False, "label": "card"}
    return [*found[0][:-1], exile], found[1], found[2]


# -- Gargantuan Gorilla: "you may sacrifice a Forest. If you sacrifice a snow Forest this way, … If you don't sacrifice a Forest, sacrifice this
# creature and it deals 7 damage to you." 701.21a: zero or one Forest, the player's choice; the last sentence follows when none was sacrificed.
_DONT_SAC = re.compile(r"^(?P<a>you may sacrifice an? (?P<w>[A-Z][a-z]+)\. If you sacrifice [^.]+ this way, [^.]+\.) If you don't sacrifice an? (?P=w), (?P<b>[^.]+\.)$")


def _dont_sacrifice(text: str, it: str | None, event_player: bool) -> Found | None:
    m = _DONT_SAC.match(text)
    first = _effects(m["a"], it, event_player) if m is not None else None
    rest = _effects(m["b"][0].upper() + m["b"][1:], it, event_player) if m is not None and first is not None else None
    if first is None or rest is None or not first[2] or first[1] is not None or rest[1] is not None or rest[2]:
        return None
    sac = first[0][0]
    if sac.get("do") != "sacrifice_choice" or sac.get("n") != 1 or sac.get("who") != "you" or "as" not in sac:
        return None
    none = {"do": "only_if", "cond": {"value": {"this_way": "sacrificed", "of": None, "ref_count": sac["as"]}, "op": "==", "n": 0}, "skip": len(rest[0])}
    tail = json.loads(json.dumps(rest[0]).replace(f'"{sac["as"]}"', '"dont100b"').replace(f'"ref:{sac["as"]}"', '"ref:dont100b"'))  # (its own binding)
    return [{**sac, "upto": True}, *first[0][1:], none, *tail], None, False


# -- Metathran Aerostat: "{X}{U}: You may put a creature card with mana value X from your hand onto the battlefield. If you do, return this creature
# to its owner's hand." (put_from_hand's mana value test, X as announced: 107.3a; 118.12: "If you do" is a card put onto the battlefield)
_PUT_MV_X = re.compile(r"^(?P<a>You may put a creature card) with mana value X (?P<b>from your hand onto the battlefield\. If you do, [^.]+\.)$")


def _put_mv_x(text: str, it: str | None, event_player: bool) -> Found | None:
    m = _PUT_MV_X.match(text)
    found = _effects(f"{m['a']} {m['b']}", it, event_player) if m is not None else None
    if found is None or not found[0] or found[0][0].get("do") != "put_from_hand" or "mv" in found[0][0] or not found[0][0].get("did"):
        return None
    return [{**found[0][0], "mv": ["==", {"x": 1}]}, *found[0][1:]], found[1], found[2]


# -- Fold into Aether: "Counter target spell. If that spell is countered this way, its controller may put a creature card from their hand onto the
# battlefield." 701.6a; a spell that can't be countered isn't, and nothing happens (2004-12-01); "its controller": as it last existed (608.2h), who
# chooses in private (400.2) and is asked whenever their hand holds a card (put_from_hand.each_put).
_FOLD = "Counter target spell. If that spell is countered this way, its controller may put a creature card from their hand onto the battlefield."
COUNTERED = "countered100b"


def _fold(text: str, it: str | None, event_player: bool) -> Found | None:
    if text != _FOLD:
        return None
    first, put = _effects("Counter target spell.", it, event_player), _effects("Each player may put a creature card from their hand onto the battlefield.", it, event_player)
    if first is None or put is None or len(first[0]) != 1 or first[0][0].get("do") != "counter" or put[0][0].get("do") != "each_put":
        return None
    return [{**first[0][0], "as": "fold100b"}, {"do": COUNTERED, "of": "ref:fold100b", "skip": 1}, {**put[0][0], "who": "ref:fold100b.controller"}], first[1], first[2]


def countered(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """The gate: the next ``skip`` instructions happen only if the spell it names left the stack (it was countered)."""
    from app.rules import context

    b = context.refs(ctx).get(e["of"].removeprefix("ref:")) or {}  # (a "ref:" value: a spell's lines rename it, scripts.rename_bindings)
    was = b.get("was") or b.get("objects") or []
    if not any((c := plan.state.cards.get(str(o["card"]))) is None or c.zone != "stack" or plan.oid(c) != o.get("object_id") for o in was):
        ctx["next"] = min(len(ctx["effects"]), ctx["next"] + int(e["skip"]))
    return True


# -- Swift Silence: "Counter all other spells. Draw a card for each spell countered this way." 701.6a: every spell on the stack but this one (copies
# too, 707.10); one that can't be countered stays, and isn't counted.
SWIFT = "swift100b"


def _swift(text: str, it: str | None, event_player: bool) -> Found | None:
    return ([{"do": SWIFT}], None, False) if text == "Counter all other spells. Draw a card for each spell countered this way." else None


def swift(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules.effects import counter_object

    me = ctx.get("stack_id")
    spells = [sid for sid in list(plan.state.zones.get("stack", [])) if sid != me and plan.state.cards[sid].ability is None]
    for sid in spells:
        counter_object(plan, sid, ctx["controller"], by=ctx["controller"])
    n = sum(1 for sid in spells if sid not in plan.state.zones.get("stack", []))
    ctx["effects"][ctx["next"]:ctx["next"]] = [{"do": "draw", "who": "you", "n": n}] if n else []
    return True


# -- Innocuous Researcher: "you may untap all lands you control. If you do, you can't cast spells until your next turn." The untap can always be done
# (608.2c), so "If you do" is the "you may" (603.5): declining does neither; no window between the two (the 2024-02-02 ruling).
_UNTAP_THEN = re.compile(r"^you may (?P<a>untap all lands you control)\. If you do, (?P<b>you can't cast spells until your next turn)\.$")


def _untap_then(text: str, it: str | None, event_player: bool) -> Found | None:
    m = _UNTAP_THEN.match(text)
    a = _effects(f"{m['a'][0].upper()}{m['a'][1:]}.", it, event_player) if m is not None else None
    b = _effects(f"{m['b'][0].upper()}{m['b'][1:]}.", it, event_player) if a is not None and m is not None else None
    if a is None or b is None or a[1] is not None or b[1] is not None or a[2] or b[2]:
        return None
    return [*a[0], *b[0]], None, True


# -- Auriok Survivors: "you may return target Equipment card from your graveyard to the battlefield. If you do, you may attach it to this creature."
# 603.5 then a second choice; 701.3a-b: "it" is the permanent the card became (400.7j); with this creature gone, it stays unattached (2011-06-01).
_MAY_ATTACH = re.compile(r"^(?P<a>you may return target Equipment card from your graveyard to the battlefield)\. If you do, you may attach it to ~\.$")


def _may_attach(text: str, it: str | None, event_player: bool) -> Found | None:
    m = _MAY_ATTACH.match(text)
    found = _effects(f"{m['a']}.", it, event_player) if m is not None else None
    if found is None or not found[2] or len(found[0]) != 1 or found[0][0].get("do") != "return_card" or found[0][0].get("to") != "battlefield":
        return None
    return [{**found[0][0], "as": "e0"}, {"do": "may_rest", "skip": 1, "label": "attach it to this creature"},
            {"do": "attach_to", "src": "ref:e0", "who": "self"}], found[1], True


# -- Vanish into Memory: "… At the beginning of your next upkeep, return that card to the battlefield under its owner's control. If you do, discard
# cards equal to that creature's toughness." The returned permanent's toughness (the 2017-03-14 rulings: a token never returns, nothing is
# discarded; a card that returns as a noncreature has no toughness, 208.3).
_VANISH = re.compile(r"^(?P<a>Exile target creature\. You draw cards equal to that creature's power\. At the beginning of your next upkeep, return that card to "
                     r"the battlefield under its owner's control)\. If you do, discard cards equal to that creature's toughness\.$")


def _vanish(text: str, it: str | None, event_player: bool) -> Found | None:
    m = _VANISH.match(text)
    found = _effects(f"{m['a']}.", it, event_player) if m is not None else None
    if found is None or [e.get("do") for e in found[0]] != ["exile", "draw", "delayed", "deferred:return_card"] or found[0][2].get("n") != 1:
        return None
    return [*found[0][:2], {**found[0][2], "n": 3}, {**found[0][3], "as": "vanish100b"}, {"do": f"deferred:{BACK}", "of": "ref:vanish100b", "skip": 1},
            {"do": "deferred:discard", "who": "you", "n": {"toughness": "ref:vanish100b"}}], found[1], found[2]


BACK = "back_creature100b"


def back_creature(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """The gate: the next ``skip`` instructions happen only if the card it names is now a creature on the battlefield (it returned)."""
    from app.rules import context

    if not any(plan.state.cards[c].zone.endswith(":battlefield") and plan.ch(plan.state.cards[c]).is_creature
               for c in context.objects(plan, ctx, e["of"].removeprefix("ref:")) if c in plan.state.cards):
        ctx["next"] = min(len(ctx["effects"]), ctx["next"] + int(e["skip"]))
    return True


# -- Dakra Mystic: "Each player reveals the top card of their library. You may put the revealed cards into their owners' graveyards. If you don't, each
# player draws a card." Decided after all are revealed (the 2014-04-26 ruling), all or none: either the revealed cards go to their owners'
# graveyards (not a mill, 701.17a: no "mill" instruction), or each player draws (then the revealed card).
_DAKRA = "Each player reveals the top card of their library. You may put the revealed cards into their owners' graveyards. If you don't, each player draws a card."
TO_GRAVEYARDS = "to_graveyards100b"


def _dakra(text: str, it: str | None, event_player: bool) -> Found | None:
    if text != _DAKRA:
        return None
    look, draw = _effects("Each player reveals the top card of their library.", it, event_player), _effects("Each player draws a card.", it, event_player)
    if look is None or draw is None or len(look[0]) != 1 or look[0][0].get("do") != "look_top":
        return None
    return [{**look[0][0], "as": "dakra100b"}, {"do": EITHER, "a": [{"do": TO_GRAVEYARDS, "of": "ref:dakra100b"}], "b": draw[0],
                                                "labels": ["Put the revealed cards into their owners' graveyards", "Each player draws a card"]}], None, False


def to_graveyards(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import context

    cards = [c for c in context.objects(plan, ctx, e["of"].removeprefix("ref:")) if plan.state.cards[c].zone.endswith(":library")]
    if cards:
        plan.do({"type": "move", "card_ids": cards, "to": {"zone": "graveyard"}}, actor=ctx["controller"])
    return True


# -- Doors of Durin: "… put it onto the battlefield tapped and attacking. Until your next turn, it gains trample if you control a Dwarf and hexproof if you
# control an Elf." Each "if" read as the ability resolves (608.2c); both grants are to the creature put onto the battlefield.
_DURIN = re.compile(r"^(?P<a>.+ put it onto the battlefield tapped and attacking)\. Until your next turn, it gains (?P<k1>[a-z]+) if you control (?P<w1>an? [A-Z][a-z]+) "
                    r"and (?P<k2>[a-z]+) if you control (?P<w2>an? [A-Z][a-z]+)\.$")


def _durin(text: str, it: str | None, event_player: bool) -> Found | None:
    m = _DURIN.match(text)
    found = _effects(f"{m['a']}. If you control {m['w1']}, it gains {m['k1']} until your next turn. If you control {m['w2']}, it gains {m['k2']} until your "
                     "next turn.", it, event_player) if m is not None else None
    grants = [i for i, e in enumerate(found[0]) if e.get("do") == "grant"] if found is not None else []
    if found is None or len(grants) != 2:
        return None
    first = found[0][grants[0]]
    effects = [{k: v for k, v in e.items() if k != "as"} if i == grants[0] else {**e, "who": first["who"]} if i == grants[1] else e for i, e in enumerate(found[0])]
    return effects, found[1], found[2]


# -- Lat-Nam's Legacy: "Shuffle a card from your hand into your library. If you do, draw two cards at the beginning of the next turn's upkeep." The
# shuffle is mandatory; "If you do" fails only with an empty hand (the 2008-10-01 ruling). To shuffle it in: put it into the library, then shuffle.
_LATNAM = "Shuffle a card from your hand into your library. If you do, draw two cards at the beginning of the next turn's upkeep."
HAND_GATE = "hand_gate100b"


def _latnam(text: str, it: str | None, event_player: bool) -> Found | None:
    if text != _LATNAM:
        return None
    put, shuffle = _effects("Put a card from your hand on the bottom of your library.", it, event_player), _effects("Shuffle your library.", it, event_player)
    later = _effects("Draw two cards at the beginning of the next turn's upkeep.", it, event_player)
    if put is None or shuffle is None or later is None or put[0] != [{"do": "put_back", "n": 1, "place": "bottom"}]:
        return None
    rest = [*put[0], *shuffle[0], *later[0]]
    return [{"do": HAND_GATE, "skip": len(rest)}, *rest], None, False


def hand_gate(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """The gate: the next ``skip`` instructions happen only if the controller's hand holds a card."""
    if not plan.state.zones.get(f"{ctx['controller']}:hand"):
        ctx["next"] = min(len(ctx["effects"]), ctx["next"] + int(e["skip"]))
    return True


# -- Primal Surge: "Exile the top card of your library. If it's a permanent card, you may put it onto the battlefield. If you do, repeat this process."
# The 2012-05-01 rulings: the repeat includes the repeat; it ends at a card that isn't a permanent card (110.4), one you don't put, or one that
# can't be put there (an Aura with nothing to enchant, 303.4g); what the cards' entering triggers waits until it has resolved (603.3).
SURGE = "surge100b"
_PERMANENT = {"Artifact", "Battle", "Creature", "Enchantment", "Land", "Planeswalker"}


def _surge(text: str, it: str | None, event_player: bool) -> Found | None:
    ok = text == "Exile the top card of your library. If it's a permanent card, you may put it onto the battlefield. If you do, repeat this process."
    return ([{"do": SURGE}], None, False) if ok else None


def surge(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules.effects import exile_cards

    library = plan.state.zones.get(f"{ctx['controller']}:library") or []
    if library:
        exile_cards(plan, ctx, {"as": SURGE}, [library[0]])
        ctx["effects"][ctx["next"]:ctx["next"]] = [{"do": PUT_EXILED, "of": f"ref:{SURGE}", "then": [{"do": SURGE}], "else": []}]
    return True


# -- Fishing Gear: "exile the top card of that player's library. If it's a permanent card, you may put it onto the battlefield under your control. If you
# don't, create a 1/1 blue Fish creature token." "If you don't": not a permanent card, declined, or one that couldn't be put there (the 2025-10-02
# rulings). The shared step (Primal Surge too): ``then`` once the exiled card entered, ``else`` otherwise.
_FISHING = re.compile(r"^(?P<a>exile the top card of that player's library)\. If it's a permanent card, you may put it onto the battlefield under your control\. "
                      r"If you don't, (?P<b>create [^.]+ token)\.$")
PUT_EXILED, PUT_CHECK = "put_exiled100b", "put_check100b"


def _fishing(text: str, it: str | None, event_player: bool) -> Found | None:
    m = _FISHING.match(text)
    found = _effects(f"{m['a']}. Draw a card for each card exiled this way.", it, event_player) if m is not None else None
    token = _effects(f"{m['b'][0].upper()}{m['b'][1:]}.", it, event_player) if found is not None and m is not None else None
    if found is None or token is None or len(found[0]) != 2 or found[0][0].get("do") != "exile_top" or not found[0][0].get("as"):
        return None
    return [found[0][0], {"do": PUT_EXILED, "of": f"ref:{found[0][0]['as']}", "then": [], "else": token[0]}], None, False


def put_exiled(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.game.rules_state import DecisionOption
    from app.rules import context
    from app.rules.plan import decide

    cards = [plan.state.cards[c] for c in context.objects(plan, ctx, e["of"].removeprefix("ref:")) if plan.state.cards[c].zone.endswith(":exile")]
    if not cards or not _PERMANENT & set(plan.ch(cards[0]).types):
        ctx["effects"][ctx["next"]:ctx["next"]] = e["else"]
        return True
    decide(plan, player=ctx["controller"], kind="confirm", prompt=f"{ctx.get('name') or 'It'}: put {cards[0].name} onto the battlefield?",
           options=[DecisionOption(id="yes", label="Put it onto the battlefield"), DecisionOption(id="no", label="Don't")],
           resume={"step": PUT_EXILED, "ctx": ctx, "e": e})
    return False


def resume_put_exiled(plan: Any, d: Any, chosen: list[str]) -> None:
    from app.rules.effects import continue_effects

    ctx, e = d.resume["ctx"], d.resume["e"]
    ctx["effects"][ctx["next"]:ctx["next"]] = ([{"do": "return_card", "who": e["of"], "to": "battlefield", "tapped": False, "under": "you", "as": PUT_CHECK},
                                                {"do": PUT_CHECK, "then": e["then"], "else": e["else"]}] if chosen == ["yes"] else e["else"])
    continue_effects(plan, ctx)


def put_check(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import context

    entered = any(plan.state.cards[c].zone.endswith(":battlefield") for c in context.objects(plan, ctx, PUT_CHECK))
    ctx["effects"][ctx["next"]:ctx["next"]] = e["then"] if entered else e["else"]
    return True


# -- Locke, Treasure Hunter: "each player mills a card. If a land card was milled this way, create a Treasure token. Until end of turn, you may cast a
# spell from among those cards." "Those cards": every card milled (the new objects in the graveyards, 400.7j); one spell, its timing and costs as
# usual (the 2025-06-06 rulings).
_LOCKE = re.compile(r"^(?P<a>each player mills a card\. If a land card was milled this way, create a Treasure token)\. Until end of turn, you may cast a spell from among "
                    r"those cards\.$")


def _locke(text: str, it: str | None, event_player: bool) -> Found | None:
    m = _LOCKE.match(text)
    found = _effects(f"{m['a']}.", it, event_player) if m is not None else None
    if found is None or found[1] is not None or found[2] or found[0][0].get("do") != "mill" or not found[0][0].get("as"):
        return None
    grant = {"do": "grant_play", "who": f"ref:{found[0][0]['as']}", "play": False, "cast": True, "until": "end_of_turn", "optional": True, "limit": 1}
    return [*found[0], grant], None, False


# -- Deathbonnet Hulk: "you may exile a card from a graveyard. If a creature card was exiled this way, put a +1/+1 counter on this creature." Not
# targeted: chosen as it resolves among the cards in all graveyards (public, 404.2), none if they choose; the kind read in exile (400.7j).
_GY_EXILE = re.compile(r"^you may exile a card from a graveyard\. (?P<b>If a creature card was exiled this way, [^.]+\.)$")


def _gy_exile(text: str, it: str | None, event_player: bool) -> Found | None:
    from app.rules import selectors

    m = _GY_EXILE.match(text)
    found = _effects(f"you may exile target card from a graveyard. {m['b']}", it, event_player) if m is not None else None
    pool = selectors.parse("card in a graveyard")
    if found is None or pool is None or not found[2] or found[0][0].get("do") != "exile" or found[0][0].get("who") != "target" or not found[0][0].get("as"):
        return None
    pick = {"do": "return_choice", "to": "exile", "sel": pool.key(), "n": 1, "upto": True, "random": False, "label": "card", "as": found[0][0]["as"]}
    return [pick, *found[0][1:]], None, False


# -- Manabond: "you may reveal your hand and put all land cards from it onto the battlefield. If you do, discard your hand." 603.5: declining does
# nothing; the lands enter during the resolution (not played, 305.4) and the rest of the hand is discarded after (the 2004-10-04 rulings).
_MANABOND = "you may reveal your hand and put all land cards from it onto the battlefield. If you do, discard your hand."


def _manabond(text: str, it: str | None, event_player: bool) -> Found | None:
    from app.rules import selectors

    if text != _MANABOND:
        return None
    lands, discard = selectors.parse("land card in your hand"), _effects("Discard your hand.", it, event_player)
    if lands is None or discard is None:
        return None
    return [{"do": "reveal_hand", "who": "you"}, {"do": "return_card", "who": lands.key(), "to": "battlefield", "tapped": False, "under": "you"},
            *discard[0]], None, True


# -- Wicked Guardian: "you may have it deal 2 damage to another creature you control. If you do, draw a card." Not targeted: the creature (if any) is
# chosen as it resolves; "If you do" is that choice, even if the damage is prevented or it left the battlefield (the 2019-10-04 rulings).
_HAVE_DEAL = re.compile(r"^you may (?:have it deal|~ deals) (?P<n>\d+) damage to another creature you control\. If you do, draw a card\.$")


def _have_deal(text: str, it: str | None, event_player: bool) -> Found | None:
    from app.rules import selectors

    m = _HAVE_DEAL.match(text)
    other = selectors.parse("another creature you control") if m is not None else None
    if m is None or other is None or it != "self":
        return None
    return [{"do": "return_choice", "to": "choose", "sel": other.key(), "n": 1, "upto": True, "random": False, "label": "creature", "as": "deal100b",
             "did": "deal100b_did"}, {"do": "only_if", "cond": {"succeeded": "deal100b_did"}, "skip": 2},
            {"do": "damage", "who": "ref:deal100b", "n": int(m["n"])}, {"do": "draw", "who": "you", "n": 1}], None, False


# -- Phenomenon Investigators: "you may return a nonland permanent you own to your hand. If you do, draw a card." Chosen as it resolves among the
# nonland permanents you own, whoever controls them (108.3; to its owner's hand, 400.3); none if you choose.
_OWN_BOUNCE = "you may return a nonland permanent you own to your hand. If you do, draw a card."


def _own_bounce(text: str, it: str | None, event_player: bool) -> Found | None:
    from app.rules import selectors

    if text != _OWN_BOUNCE or (mine := selectors.parse("nonland permanent you own")) is None:
        return None
    return [{"do": "return_choice", "to": "hand", "sel": mine.key(), "n": 1, "upto": True, "random": False, "label": "nonland permanent",
             "did": "own100b_did"}, {"do": "only_if", "cond": {"succeeded": "own100b_did"}, "skip": 1}, {"do": "draw", "who": "you", "n": 1}], None, False


# -- Clash of Elements: "Choose target nonland permanent. Its owner may put it on top of their library. If they do, Clash of Elements deals 2 damage
# to them. If they didn't put the card on top of their library, they put it on the bottom." The owner's choice as it resolves (608.2d, 101.4b).
_CLASH = ("Choose target nonland permanent. Its owner may put it on top of their library. If they do, ~ deals 2 damage to them. If they didn't put the card on "
          "top of their library, they put it on the bottom.")


def _clash(text: str, it: str | None, event_player: bool) -> Found | None:
    if text != _CLASH:
        return None
    top = _effects("Put target nonland permanent on top of its owner's library. ~ deals 2 damage to its owner.", it, event_player)
    bottom = _effects("Put target nonland permanent on the bottom of its owner's library.", it, event_player)
    if top is None or bottom is None or top[1] != bottom[1] or len(top[0]) != 2:
        return None
    return [{"do": EITHER, "who": "target_owner", "a": top[0], "b": bottom[0],
             "labels": ["Put it on top of your library (it deals 2 damage to you)", "Put it on the bottom of your library"]}], top[1], False


# -- Hedron Alignment: "you may reveal your hand. If you do, you win the game if you own a card named Hedron Alignment in exile, in your hand, in your
# graveyard, and on the battlefield." (a face-down card has no name: one exiled face down doesn't count, the 2016-01-22 ruling; 406.3a, 708.2)
# Atemsis, All-Seeing: "you may reveal your hand. If cards with at least six different mana values are revealed this way, that player loses the game."
# (202.3: one mana value each, X is 0, a split card's halves combined - the 2019-07-12 rulings). 603.5: declining reveals nothing.
_HEDRON = re.compile(r"^you may reveal your hand\. If you do, you win the game if you own a card named (?P<name>[^,]+) in exile, in your hand, in your graveyard, "
                     r"and on the battlefield\.$")
_ATEMSIS = "you may reveal your hand. If cards with at least six different mana values are revealed this way, that player loses the game."
OWN_EVERYWHERE, HAND_VALUES = "own_everywhere100b", "hand_values100b"


def _reveal_win(text: str, it: str | None, event_player: bool) -> Found | None:
    if (m := _HEDRON.match(text)) is not None:
        return [{"do": "reveal_hand", "who": "you"}, {"do": OWN_EVERYWHERE, "name": m["name"], "skip": 1}, {"do": "win_game", "who": "you"}], None, True
    if text == _ATEMSIS and event_player:
        return [{"do": "reveal_hand", "who": "you"}, {"do": HAND_VALUES, "n": 6, "skip": 1}, {"do": "lose_game", "who": "event_player"}], None, True
    return None


def own_everywhere(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """The gate: you own a card with that name in exile, in your hand, in your graveyard and on the battlefield (each face up)."""
    me = ctx["controller"]
    zones = {c.zone.rsplit(":", 1)[-1] for c in plan.state.cards.values() if c.owner == me and not c.face_down and plan.ch(c).name == e["name"]}
    if not {"exile", "hand", "graveyard", "battlefield"} <= zones:
        ctx["next"] = min(len(ctx["effects"]), ctx["next"] + int(e["skip"]))
    return True


def hand_values(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """The gate: the cards in your hand (all revealed) have at least ``n`` different mana values."""
    hand = plan.state.zones.get(f"{ctx['controller']}:hand") or []
    if len({int(plan.ch(plan.state.cards[c]).mana_value) for c in hand}) < int(e["n"]):
        ctx["next"] = min(len(ctx["effects"]), ctx["next"] + int(e["skip"]))
    return True


# -- Moonring Mirror: "you may exile all cards from your hand face down. If you do, put all other cards you own exiled with this artifact into your hand."
# Both abilities' cards are exiled with it (607.2a); "other": not the ones just exiled (the 2004-12-01 ruling). 603.5: declining does neither.
_MOONRING = "you may exile all cards from your hand face down. If you do, put all other cards you own exiled with ~ into your hand."
OTHERS = "others_back100b"


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    """The whole ability (its link accumulates both abilities' cards, exiled_with.accumulating_link), or None."""
    from dataclasses import replace

    from app.rules import scripts

    if ability.kind != "triggered" or scripts.self_text(ability.text, ch.name) != f"At the beginning of your upkeep, {_MOONRING}":
        return None
    base = scripts.define(replace(ability, text="At the beginning of your upkeep, draw a card."), ch)
    down, back = _effects("you may exile all cards from your hand face down.", None, False), _effects("Put all cards you own exiled with ~ into your hand.", None, False)
    if base is None or down is None or back is None or len(down[0]) != 1 or len(back[0]) != 1 or back[0][0].get("do") != "return_card":
        return None
    return {**base, "optional": True, "accumulating_link": True,
            "effects": [{**down[0][0], "link": True, "as": "moon100b"}, {**back[0][0], "do": OTHERS, "not": "moon100b"}]}


def others_back(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """``return_card`` of the cards ``who`` names but those the binding ``not`` names (the ones exiled a moment ago)."""
    from app.rules import context
    from app.rules.effects import _cards, _return_cards

    fresh = set(context.objects(plan, ctx, e["not"]))
    return _return_cards(plan, ctx, {**e, "do": "return_card"}, [c for c in _cards(plan, ctx, e["who"]) if c not in fresh])


# -- Read the Runes: "Draw X cards. For each card drawn this way, discard a card unless you sacrifice a permanent." The 2004-10-04 rulings: draw, then
# sacrifice any permanents you want (up to that many, all at once), then discard the rest of the number at once; never forced to sacrifice.
_RUNES = "Draw X cards. For each card drawn this way, discard a card unless you sacrifice a permanent."


def _runes(text: str, it: str | None, event_player: bool) -> Found | None:
    from app.rules import selectors

    if text != _RUNES:
        return None
    base, mine = _effects("Draw X cards. Draw a card for each card drawn this way.", it, event_player), selectors.parse("permanent you control")
    if base is None or mine is None or len(base[0]) != 2:
        return None
    drawn = base[0][1]["n"]
    gone = {"this_way": "sacrificed", "of": None, "ref_count": "runes100b"}
    return [base[0][0], {"do": "sacrifice_choice", "who": "you", "sel": mine.key(), "n": drawn, "upto": True, "as": "runes100b"},
            {"do": "discard", "who": "you", "n": {"minus": [drawn, gone]}}], None, False


# -- Rally the Horde: "Exile the top card of your library. (three times) If the last card exiled isn't a land card, repeat this process. Create a 1/1
# red Warrior creature token for each nonland card exiled this way." Each card one at a time; the process stops at a land, or when the library is empty.
_RALLY = ("Exile the top card of your library. Exile the top card of your library. Exile the top card of your library. If the last card exiled isn't a land "
          "card, repeat this process. Create a 1/1 red Warrior creature token for each nonland card exiled this way.")
RALLY = "rally100b"


def _rally(text: str, it: str | None, event_player: bool) -> Found | None:
    token = _effects("Create a 1/1 red Warrior creature token.", it, event_player) if text == _RALLY else None
    return ([{"do": RALLY, "token": token[0][0]}], None, False) if token is not None and len(token[0]) == 1 else None


def rally(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules.effects import exile_cards

    me, nonland, last = ctx["controller"], 0, None
    while last is None or not plan.ch(last).is_land:
        for _ in range(3):
            library = plan.state.zones.get(f"{me}:library") or []
            if not library:
                break
            top = library[0]
            exile_cards(plan, ctx, {}, [top])
            last = plan.state.cards[top]
            nonland += not plan.ch(last).is_land
        else:
            continue
        break  # (the library ran out)
    ctx["effects"][ctx["next"]:ctx["next"]] = [{**e["token"], "n": nonland}] if nonland else []
    return True


# -- Long Rest: "If eight or more cards were returned to your hand this way, your life total becomes equal to your starting life total. Exile Long
# Rest." (the cards now in your hand, 400.7j; 119.5: the life is gained or lost, the 2021-07-23 ruling; 103.4: the starting life total)
_LONG_REST = re.compile(r"^(?P<a>Return X target cards with different mana values from your graveyard to your hand)\. If eight or more cards were returned to your "
                        r"hand this way, your life total becomes equal to your starting life total\. (?P<b>Exile ~\.)$")


def _long_rest(text: str, it: str | None, event_player: bool) -> Found | None:
    m = _LONG_REST.match(text)
    found = _effects(f"{m['a']}. {m['b']}", it, event_player) if m is not None else None
    if found is None or len(found[0]) != 2 or found[0][0].get("do") != "return_card" or found[0][0].get("to") != "hand":
        return None
    eight = {"do": "only_if", "cond": {"value": {"this_way": "your_hand", "of": None, "ref_count": "rest100b"}, "op": ">=", "n": 8}, "skip": 1}
    return [{**found[0][0], "as": "rest100b"}, eight, {"do": "set_life", "who": "you", "n": "start"}, found[0][1]], found[1], found[2]


# -- Bringer of the Last Gift: "each player sacrifices all other creatures they control. Then each player returns all creature cards from their graveyard
# that weren't put there this way to the battlefield." Each card under its owner's control (the graveyard is its owner's, 404.2), all at once; not the
# cards just sacrificed (the new objects in the graveyards, 400.7).
_BRINGER = ("each player sacrifices all other creatures they control. Then each player returns all creature cards from their graveyard that weren't put there "
            "this way to the battlefield.")


def _bringer(text: str, it: str | None, event_player: bool) -> Found | None:
    from app.rules import selectors

    if text[:1].lower() + text[1:] != _BRINGER or (dead := selectors.parse("creature card in a graveyard")) is None:
        return None
    sac = _effects("each player sacrifices all other creatures they control.", it, event_player)
    if sac is None or len(sac[0]) != 1 or sac[0][0].get("do") != "sacrifice_choice":
        return None
    return [{**sac[0][0], "as": "bringer100b"}, {"do": OTHERS, "who": dead.key(), "to": "battlefield", "tapped": False, "under": "owner",
                                                  "not": "bringer100b"}], None, False


# -- Vault 101: Birthday Party: "You may put an Aura or Equipment card from your hand or graveyard onto the battlefield. If an Equipment is put onto the
# battlefield this way, you may attach it to a creature you control." Not targeted: the creature (if any) is chosen as it resolves (701.3a).
_VAULT101 = re.compile(r"^(?P<a>You may put an Aura or Equipment card from your hand or graveyard onto the battlefield)\. If an Equipment is put onto the battlefield "
                       r"this way, you may attach it to a creature you control\.$")


def _vault101(text: str, it: str | None, event_player: bool) -> Found | None:
    from app.rules import selectors

    m = _VAULT101.match(text)
    found = _effects(f"{m['a']}.", it, event_player) if m is not None else None
    equipment, mine = selectors.parse("Equipment"), selectors.parse("creature you control")
    if found is None or equipment is None or mine is None or len(found[0]) != 1 or found[0][0].get("do") != "return_choice":
        return None
    return [{**found[0][0], "as": "v101"}, {"do": "only_if", "cond": {"object": "ref:v101", "is": equipment.key()}, "skip": 2},
            {"do": "return_choice", "to": "choose", "sel": mine.key(), "n": 1, "upto": True, "random": False, "label": "creature to attach it to", "as": "v101c"},
            {"do": "attach_to", "src": "ref:v101", "who": "ref:v101c"}], found[1], found[2]


# -- Inferno of the Star Mounts: "~ gets +1/+0 until end of turn. When its power becomes 20 this way, it deals 20 damage to any target." 603.12: a
# reflexive ability, its target chosen only if it triggers - only when this +1/+0 made the power exactly 20 (the 2021-07-23 rulings): the creature
# still there with power 20 after it (a +1/+0, 613.4c, was the change).
_BECOMES = re.compile(r"^(?P<a>~ gets \+1/\+0 until end of turn)\. When its power becomes (?P<n>\d+) this way, (?P<b>it deals \d+ damage to any target)\.$")
BECAME = "became100b"


def _becomes20(text: str, it: str | None, event_player: bool) -> Found | None:
    from app.rules import scripts

    m = _BECOMES.match(text)
    pump = _effects(f"{m['a']}.", it, event_player) if m is not None else None
    hit = _effects(m["b"].replace("it deals", "~ deals", 1) + ".", None, False) if pump is not None and m is not None else None
    if m is None or pump is None or hit is None or pump[1] is not None or hit[1] != "any":
        return None
    reflex = {"do": "reflexive", "cond": {"all": []}, "ability": {"kind": "triggered", "trigger": "reflexive", "effects": hit[0], "optional": False,
                                                                **scripts.target_fields(hit[1])}}
    return [*pump[0], {"do": BECAME, "n": int(m["n"]), "reflex": reflex}], None, False


def became(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import effects, values

    src = effects._cards(plan, ctx, "self")
    if src and values._stat_of(plan.ch(plan.state.cards[src[0]]), "power") == e["n"]:
        return effects.reflexive(plan, ctx, e["reflex"])
    return True


# -- Mr. Foxglove: "draw cards equal to the number of cards in defending player's hand minus the number of cards in your hand. If you didn't draw cards
# this way, you may put a creature card from your hand onto the battlefield." 107.1b: 0 or less draws none (the 2024-07-26 ruling); the hand counts
# are read once, as it resolves (608.2h); a replaced or impossible draw is no card drawn (121.2).
_FOXGLOVE = ("draw cards equal to the number of cards in defending player's hand minus the number of cards in your hand. If you didn't draw cards this way, you "
             "may put a creature card from your hand onto the battlefield.")


def _foxglove(text: str, it: str | None, event_player: bool) -> Found | None:
    put = _effects("you may put a creature card from your hand onto the battlefield.", it, event_player) if text == _FOXGLOVE else None
    if put is None or len(put[0]) != 1 or put[0][0].get("do") != "put_from_hand":
        return None
    none = {"do": "only_if", "cond": {"value": {"this_way": "drawn", "of": None, "players": "you", "ref_count": "fox100b"}, "op": "==", "n": 0}, "skip": 1}
    return [{"do": "draw", "who": "you", "n": {"minus": [{"hand": "defending_player"}, {"hand": "you"}]}, "as": "fox100b"}, none,
            {**put[0][0], "optional": True}], None, False


# -- Call the Spirit Dragons: "for each color, put a +1/+1 counter on a Dragon you control of that color. If you put +1/+1 counters on five Dragons this
# way, you win the game." One Dragon chosen for each of the five colors (105.1), a multicolored one may be chosen more than once; the win needs five
# different Dragons that got their counters (the 2025-04-04 rulings).
_SPIRIT = ("for each color, put a +1/+1 counter on a Dragon you control of that color. If you put +1/+1 counters on five Dragons this way, you win the "
           "game.")
SPIRIT, SPIRIT_WIN = "spirit100b", "spirit_win100b"


def _spirit_dragons(text: str, it: str | None, event_player: bool) -> Found | None:
    return ([{"do": SPIRIT, "left": ["W", "U", "B", "R", "G"], "picks": []}], None, False) if text == _SPIRIT else None


def spirit(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.game.rules_state import DecisionOption
    from app.rules.plan import decide

    me, left, picks = ctx["controller"], list(e["left"]), list(e["picks"])
    while left:
        color = left.pop(0)
        dragons = [c for c in plan.state.zones.get(f"{me}:battlefield", []) if plan.in_game(plan.state.cards[c])
                   and "Dragon" in plan.ch(plan.state.cards[c]).subtypes and color in plan.ch(plan.state.cards[c]).colors]
        if len(dragons) > 1:
            decide(plan, player=me, kind="choose_cards", prompt=f"{ctx.get('name') or 'It'}: put a +1/+1 counter on a {color} Dragon you control",
                   options=[DecisionOption(id=c, label=plan.state.cards[c].name or "Dragon", card_id=c) for c in dragons], min_choices=1, max_choices=1,
                   resume={"step": SPIRIT, "ctx": ctx, "e": {**e, "left": left, "picks": picks}})
            return False
        picks += dragons
    oids = [plan.oid(c) for c in picks]
    ctx["effects"][ctx["next"]:ctx["next"]] = [*({"do": "add_counters", "who": f"object:{o}", "kind": "+1/+1", "n": 1} for o in oids),
                                               {"do": SPIRIT_WIN, "before": {o: plan.state.cards[o.rsplit(".", 1)[0]].counters.get("+1/+1", 0) for o in oids}}]
    return True


def resume_spirit(plan: Any, d: Any, chosen: list[str]) -> None:
    from app.rules.effects import continue_effects

    ctx, e = d.resume["ctx"], d.resume["e"]
    ctx["effects"][ctx["next"]:ctx["next"]] = [{**e, "picks": [*e["picks"], *chosen[:1]]}]
    continue_effects(plan, ctx)


def spirit_win(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import win_game

    got = [o for o, n in e["before"].items() if (c := plan.state.cards.get(o.rsplit(".", 1)[0])) is not None and plan.oid(c) == o
           and c.counters.get("+1/+1", 0) > n]
    return win_game.win_game(plan, ctx, {"who": "you"}) if len(got) >= 5 else True


# -- Holistic Wisdom: "{2}, Exile a card from your hand: Return target card from your graveyard to your hand if it shares a card type with the card exiled
# this way." (the one card so worded: "this way" is the cost's exile, 601.2h; the card types of 300.1, read as the ability resolves, 608.2c)
_HOLISTIC = "Return target card from your graveyard to your hand if it shares a card type with the card exiled this way."
SHARES = "shares_type100b"
_CARD_TYPES = {"Artifact", "Battle", "Creature", "Enchantment", "Instant", "Kindred", "Land", "Planeswalker", "Sorcery"}


def _holistic(text: str, it: str | None, event_player: bool) -> Found | None:
    base = _effects("Return target card from your graveyard to your hand.", it, event_player) if text == _HOLISTIC else None
    return ([{"do": SHARES, "skip": len(base[0])}, *base[0]], base[1], base[2]) if base is not None and base[0] else None


def shares_type(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """The gate: the target shares a card type with the card the cost exiled."""
    from app.rules.effects import _cards

    def types(who: str) -> set[str]:
        return {t for c in _cards(plan, ctx, who) for t in plan.ch(plan.state.cards[c]).types} & _CARD_TYPES
    if not types("target") & types("cost:exiled"):
        ctx["next"] = min(len(ctx["effects"]), ctx["next"] + int(e["skip"]))
    return True


# -- Reign of Terror: "Destroy all green creatures or all white creatures. They can't be regenerated. You lose 2 life for each creature that died
# this way." 608.2d: the controller picks one as it resolves (and announces it, 101.4b); the rest of the text reads the one done.
_EITHER = re.compile(r"^Destroy all (?P<a>[a-z]+ creatures) or all (?P<b>[a-z]+ creatures)\. (?P<rest>[^.]+\.(?: [^.]+\.)*)$")
EITHER = "either100b"


def _either(text: str, it: str | None, event_player: bool) -> Found | None:
    m = _EITHER.match(text)
    if m is None:
        return None
    first, other = _effects(f"Destroy all {m['a']}. {m['rest']}", it, event_player), _effects(f"Destroy all {m['b']}.", it, event_player)
    if first is None or other is None or first[1] is not None or other[1] is not None or first[2] or len(other[0]) != 1:
        return None
    a, b = first[0][0], other[0][0]
    if a.get("do") != "destroy" or b.get("do") != "destroy" or set(a) - {"do", "who", "as"} or set(b) - {"do", "who"}:
        return None
    b = {**b, **({"as": a["as"]} if "as" in a else {})}
    return [{"do": EITHER, "a": [a], "b": [b], "labels": [f"Destroy all {m['a']}", f"Destroy all {m['b']}"]}, *first[0][1:]], None, False


def either(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.game.rules_state import DecisionOption
    from app.rules.effects import _players
    from app.rules.plan import decide

    who = _players(plan, ctx, e["who"]) if e.get("who") else [ctx["controller"]]  # (Clash of Elements: the target's owner chooses)
    if not who:
        return True
    decide(plan, player=who[0], kind="choose_one", prompt=f"{ctx.get('name') or 'It'}: choose one",
           options=[DecisionOption(id="a", label=e["labels"][0]), DecisionOption(id="b", label=e["labels"][1])], resume={"step": EITHER, "ctx": ctx, "e": e})
    return False


def resume_either(plan: Any, d: Any, chosen: list[str]) -> None:
    from app.rules.effects import continue_effects

    ctx, e = d.resume["ctx"], d.resume["e"]
    pick = 0 if chosen == ["a"] else 1
    plan.note(f"{plan.name(d.player)} chooses: {e['labels'][pick]}", actor=d.player)
    ctx["effects"][ctx["next"]:ctx["next"]] = e["a" if pick == 0 else "b"]
    continue_effects(plan, ctx)


PRIMITIVES = {GY_EMPTY: gy_empty, TRUCE: truce, TRUCE_ASK: truce_ask, TRUCE_DRAW: truce_draw, TRUCE_LIFE: truce_life, EITHER: either, COUNTERED: countered,
              SWIFT: swift, BACK: back_creature, TO_GRAVEYARDS: to_graveyards, HAND_GATE: hand_gate,
              SURGE: surge, PUT_EXILED: put_exiled, PUT_CHECK: put_check, OWN_EVERYWHERE: own_everywhere, HAND_VALUES: hand_values,
              OTHERS: others_back, RALLY: rally, BECAME: became, SPIRIT: spirit, SPIRIT_WIN: spirit_win, SHARES: shares_type}
RESUME = {TRUCE_ASK: resume_truce_ask, EITHER: resume_either, PUT_EXILED: resume_put_exiled, SPIRIT: resume_spirit}

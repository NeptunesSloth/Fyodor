"""-- enters attacking (wave 111R3) -- "If a creature you control would enter while you control an attacking creature, instead it enters tapped and
attacking." (Kira Nerys, Firebrand)

A replacement effect that modifies how a permanent enters (614.1c-d, 614.12): it applies to the creature as it would exist on the battlefield under
its controller (614.12: a card that enters as a copy of a creature, a face-down 2/2, a creature spell; not an Aura bestowed, nor a noncreature), and
only while that player controls an attacking creature as it would enter (the condition read before anything enters: creatures entering together
don't see each other, 614.12). It covers every entry the engine plans through ``replacements.entry_plan`` — a resolving creature spell (608.3),
a card put onto the battlefield or returned by an effect, a blink — and every token created (``replacements.token_choices`` / ``replace._make_tokens``).

Tapped is part of the move (it never "becomes tapped"); attacking is 508.4: its controller chooses the defending player, a planeswalker a defending
player controls or a battle a defending player protects it attacks *as it enters* — an entering choice (614.12a), asked before it enters like any
"As ~ enters, choose …" (``WHAT``), each creature its own question (Anim Pakal's ruling, wave 30D). One possible answer is no question; none (it isn't
the attacking player's, 506.3b, or nothing is left to attack, 508.4a) and it enters tapped but never attacking (614.6: the impossible part is
ignored). It is attacking but never "attacked" (508.4); it enters unblocked after blockers are declared (508.4d); "enters attacking" triggers
trigger (token_grammar._attack_with). An entry whose path asks nothing before it enters (a manifested or cloaked card, 701.40) is asked right after
it entered, before anyone gets priority (``offer``: sba).

An effect that already puts the creature onto the battlefield attacking ("tapped and attacking", ninjutsu 702.49c, sneak 702.190b, a token "that's
attacking that player") is not changed by it: that effect's own choice (or what it names, 508.4) stands, asked once (``BY_EFFECT``).
"""

from __future__ import annotations

from typing import Any

from app.game.rules_state import DecisionOption
from app.game.state import STACK, zone_key

STATIC = "enters_attacking111r3"
WHAT = "attacking111r3"  # the entering choice: what it attacks (508.4)
BY_EFFECT = "*effect"  # the effect putting it onto the battlefield puts it attacking itself: nothing for this to change
PENDING = "*pending"  # it applied to an entry that couldn't ask before it entered: asked right after (``offer``)
TOKEN_FLAG = "attacking111r3"  # a token creation event whose instruction makes the tokens attacking
TEXT = "If a creature you control would enter while you control an attacking creature, instead it enters tapped and attacking."
_PUTS_ATTACKING = frozenset({"create_attacking", "ninjutsu_enter"})  # (and any effect with "attacking": "tapped and attacking")


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    """Kira's line: a static of its controller's (``static_if``: "while you control an attacking creature", 611.3a)."""
    from app.rules import conditions

    if ability.text.strip() != TEXT:
        return None
    cond = conditions.parse("you control an attacking creature")
    return {"kind": "static", "static": STATIC, "static_if": [cond], "effects": []} if cond is not None else None


def _sources(plan: Any, controller: str) -> list[Any]:
    """The permanents of ``controller`` whose replacement applies now (their condition read now, 611.3a)."""
    from app.rules import cast_limits

    if plan.state.rules is None:
        return []
    return [src for src, _ in cast_limits._statics(plan.state, plan.info, STATIC) if src.controller == controller and plan.in_game(src)]


def applies(plan: Any, card: Any, controller: str) -> bool:
    """Would ``card`` enter under ``controller`` as a creature they control while they control an attacking creature (614.12)?"""
    if not _sources(plan, controller):
        return False
    probe = card.model_copy(update={"zone": zone_key(controller, "battlefield"), "controller": controller})
    return bool(plan.ch(probe).is_creature)


def options(plan: Any, controller: str) -> list[DecisionOption]:
    """What it may attack (508.4): none outside the combat phase's declare attackers step or later, or for a player who isn't attacking (506.3b)."""
    from app.rules import token_grammar

    if plan.state.turn.phase not in token_grammar._ATTACKING_PHASES or controller != plan.active:
        return []
    return token_grammar.attack_options(plan, {"controller": controller}, controller, None)


def _sneaked(plan: Any, card: Any) -> bool:
    """A permanent spell cast for its sneak cost enters attacking what the returned creature attacked (702.190b: engine.resolve_top)."""
    if card.zone != STACK:
        return False
    paid = plan.rules.payments.get(plan.oid(card))
    return paid is not None and paid.alternative == "sneak"


def _answer(found: list[DecisionOption], answer: str | None) -> str | None:
    """The answer recorded without a question: the one given (if still possible), the only possibility, nothing to attack (""); None: ask."""
    ids = [o.id for o in found]
    if answer is not None and (answer in ids or (answer == "" and not ids)):
        return answer
    if len(ids) <= 1:
        return ids[0] if ids else ""
    return None


def plan_entry(plan: Any, card: Any, controller: str, answers: dict[str, str] | None, out: dict[str, Any]) -> None:
    """``replacements.entry_plan``'s part: tapped (614.1d), and what it attacks in ``out["choices"][WHAT]`` — or the question (614.12a)."""
    answer = (answers or {}).get(WHAT)
    if answer == BY_EFFECT or _sneaked(plan, card) or not applies(plan, card, controller):
        return
    out["tapped"] = True
    picked = _answer(options(plan, controller), answer)
    out.setdefault("choices", {})[WHAT] = picked if picked is not None else PENDING  # (PENDING: replaced by the answer when it's asked first)
    if picked is None and "choice" not in out:
        out["choice"] = {"what": WHAT}


def prompt(plan: Any, card: Any, controller: str) -> tuple[str, list[DecisionOption]]:
    name = "A face-down creature" if card.face_down else (plan.ch(card).name or card.name or "A creature")
    return f"{name} enters tapped and attacking: attacking whom? (508.4)", options(plan, controller)


def entered(plan: Any, card_id: str, controller: str, choices: dict[str, str] | None) -> None:
    """``replacements.after_entry``: it entered attacking what was chosen (508.4; 508.4a: nothing if that is gone)."""
    from app.rules.token_grammar import _attack_with

    target = (choices or {}).get(WHAT)
    card = plan.state.cards.get(card_id)
    if not target or target == BY_EFFECT or card is None or not card.zone.endswith(":battlefield") or card.controller != controller \
            or not plan.ch(card).is_creature:
        return
    if target == PENDING:
        plan.rules.attack_pending111r3.append({"card": card_id, "object": plan.oid(card), "player": controller})
        return
    _attack_with(plan, [card_id], target, controller)


# -- effects that put creatures onto the battlefield attacking themselves ----------------------------------------------------------------------------
def by_effect(ctx: dict[str, Any] | None) -> bool:
    """Is the instruction being carried out (``ctx``'s current effect) one that puts what it puts onto the battlefield attacking?"""
    at = (ctx or {}).get("next") or 0
    effects = (ctx or {}).get("effects") or []
    e = effects[at - 1] if 0 < at <= len(effects) else {}
    return isinstance(e, dict) and (bool(e.get("attacking")) or e.get("do") in _PUTS_ATTACKING)


def mark(plan: Any, entries: list[dict[str, Any]], ctx: dict[str, Any] | None) -> None:
    """``attachments.enter``: entries an attacking instruction puts onto the battlefield answer ``BY_EFFECT`` (only where the replacement is)."""
    if by_effect(ctx):
        for entry in entries:
            if _sources(plan, entry["player"]):
                entry["choices"] = {**(entry.get("choices") or {}), WHAT: BY_EFFECT}


def flag_tokens(plan: Any, ev: dict[str, Any], ctx: dict[str, Any] | None, receipt_bind: str | None = None) -> None:
    """``replace.create_token_batch``: a creation event of an attacking instruction (only where the replacement is). (-- review (wave 111R) --
    also tokens whose creator makes them attacking right after, through token_attack_continuations: myriad's copies, "tapped and attacking that
    player or a planeswalker they control" — that instruction says what each attacks, 508.4, so nothing is asked twice)"""
    from app.rules import token_attack_continuations

    if (by_effect(ctx) or receipt_bind == token_attack_continuations.BINDING) and _sources(plan, ev["player"]):
        ev[TOKEN_FLAG] = True


# -- tokens (701.7a, 111.1): asked before any is created (token_choices), each token its own question ---------------------------------------------
def _token_probe(plan: Any, pid: str, spec: dict[str, Any]) -> Any:
    from app.rules import token_copy_entry

    return token_copy_entry.probe(plan, pid, spec)


def token_applies(plan: Any, pid: str, spec: dict[str, Any], ev: dict[str, Any]) -> bool:
    if ev.get(TOKEN_FLAG) or ev.get("recipient_ref") or not _sources(plan, pid):
        return False  # (the instruction makes them attacking itself: token_grammar.create_attacking, copying, replace._make_tokens)
    return applies(plan, _token_probe(plan, pid, spec), pid)


def token_question(plan: Any, pid: str, spec: dict[str, Any], ev: dict[str, Any], key: str, answers: dict[str, str]) -> tuple[dict[str, str], dict[str, Any] | None]:
    """``replacements.token_choices``: ({WHAT: answer}, None), or the question ({"key", "player", "prompt", "options"}); ({}, None) when it doesn't apply."""
    if not token_applies(plan, pid, spec, ev):
        return {}, None
    found = options(plan, pid)
    picked = _answer(found, answers.get(key))
    if picked is not None:
        return {WHAT: picked}, None
    name = str(spec.get("name") or "A token")
    return {}, {"key": key, "player": pid, "prompt": f"{name} enters tapped and attacking: attacking whom? (508.4)", "options": found}


# -- asked right after it entered (an entry that asks nothing first): before anyone gets priority (sba) -----------------------------------------
def offer(plan: Any) -> bool:
    """Ask the controller of the first creature still waiting what it attacks. True while a question is open."""
    from app.rules.plan import decide
    from app.rules.token_grammar import _attack_with

    r = plan.rules
    while r.attack_pending111r3:
        p = r.attack_pending111r3[0]
        card = plan.state.cards.get(p["card"])
        if card is None or plan.oid(card) != p["object"] or not card.zone.endswith(":battlefield") or card.controller != p["player"]:
            r.attack_pending111r3.pop(0)  # (gone, or another object now: 400.7)
            continue
        found = options(plan, p["player"])
        if len(found) <= 1:
            r.attack_pending111r3.pop(0)
            if found:
                _attack_with(plan, [card.id], found[0].id, p["player"])
            continue
        name = "A face-down creature" if card.face_down else (plan.ch(card).name or "A creature")
        decide(plan, player=p["player"], kind="choose_one", prompt=f"{name} entered tapped and attacking: attacking whom? (508.4)", options=found,
               resume={"step": "attack111r3", "card": card.id, "object": p["object"]}, source=card)
        return True
    return False


def resume(plan: Any, d: Any, chosen: list[str]) -> None:
    from app.rules.token_grammar import _attack_with

    r = plan.rules
    r.attack_pending111r3 = [p for p in r.attack_pending111r3 if not (p["card"] == d.resume["card"] and p["object"] == d.resume["object"])]
    card = plan.state.cards.get(d.resume["card"])
    if chosen and card is not None and plan.oid(card) == d.resume["object"] and card.zone.endswith(":battlefield"):
        _attack_with(plan, [card.id], chosen[0], d.player)

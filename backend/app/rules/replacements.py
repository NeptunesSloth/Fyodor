"""Replacement and prevention effects (CR 614, 615): one place for each kind of event they modify.

Replacement effects "watch for a particular event that would happen and completely or partially
replace that event with a different event" (614.1); prevention effects do the same for damage
(615.1). Neither is locked in ahead of time: they apply as the event happens. So the engine applies
them at the three points where such events are produced, whichever rules code produces them:

* **entering the battlefield** — :func:`entry_plan` / :func:`move_onto_battlefield` /
  :func:`after_entry`: "~ enters tapped [unless …]" (614.1d), "As ~ enters, you may pay N life. If
  you don't, it enters tapped" (614.1c, a choice made before it enters: 614.12a), "~ enters [tapped]
  with N … counters on it" (614.1c; the counters are put on it as it enters: 122.6), a
  planeswalker's loyalty (306.5b). Every path onto the battlefield goes through here: a resolving
  permanent spell, a land play, an effect that puts a card onto the battlefield (search,
  reanimation, blink, unearth, persist / undying) and tokens being created.
* **a zone change** — :func:`replace_move` (called by ``Plan.do`` for every ``move`` / ``mill``
  step): unearth's "if it would leave the battlefield, exile it instead" (702.84a), "If ~ would die
  / be put into a graveyard from anywhere, exile it instead" (the object's own ability), "If a
  creature would die, exile it instead" statics of permanents on the battlefield, madness (702.35a)
  and 903.9b (a commander that would go to its owner's hand or library may go to the command
  zone instead).
* **damage** — :func:`apply_prevention` (called by combat damage and the ``damage`` primitive):
  "Prevent all [combat] damage that would be dealt [to …] [by …]" statics of permanents on the
  battlefield and "… this turn" effects of resolved spells (records in ``RulesState.replacements``),
  then the "prevent the next N damage" shields (615.7), where the shielded player or the
  permanent's controller chooses which source's damage a shield prevents when several sources
  would deal it at once.

What stage 1 does NOT do (kept honest rather than guessed): the 616.1 ordering choice when several
replacement effects would modify the same event differently (the ones here never conflict: every
applicable one sends the object to exile, or applies to a different aspect of entering), "enters
tapped / with counters" imposed by *other* permanents (614.1d, "Permanents your opponents control
enter tapped"), damage doubling / redirection (614.9), draw and life-gain replacements, and "can't be
prevented" (615.12: the engine doesn't model it yet, so no prevention is skipped on its account).

Permanents an effect puts onto the battlefield together enter one after another here (each entry
is its own move step), so the second of two shock lands found by one search sees the first on the
battlefield already; the rules would have them enter simultaneously (614.12b). The difference only
shows for "enters tapped unless you control …" conditions met by the other card entering with it.

Records live in ``RulesState.replacements`` as JSON (saved and replayed with the rest of the rules
state); every choice is a ``Decision`` with resume data, and prompts about a hidden card only go to
the player who may see it.
"""

from __future__ import annotations

import re
import secrets
from typing import TYPE_CHECKING, Any

from app.game.rules_state import DecisionOption
from app.game.state import CardInstance, TokenDef, zone_key
from app.rules import characteristics as chars
from app.rules import conditions, scripts, selectors, values

if TYPE_CHECKING:
    from app.rules.plan import Plan

Entry = dict[str, Any]  # {"card", "player", "actor", "tapped"?, "pay_life"?, "x"?, "gain_haste"?, "counter"?, "exile_if_leaves"?, "delayed"?}


def _definitions(plan: Plan, card: CardInstance) -> dict[int, dict[str, Any]]:
    """The card's own definitions, unless it was taken out of automation (never guess for those)."""
    if plan.manual(card):
        return {}
    return scripts.definitions(plan.ch(card))


# -- entering the battlefield (614.1c-d, 614.12, 122.6, 306.5b) --------------------------------------
def unless_holds(plan: Plan, controller: str, card: CardInstance, cond: dict[str, Any]) -> bool:
    """"~ enters tapped unless <condition>": checked as it enters, while it is still in the zone it
    comes from (it is not yet on the battlefield: "unless you control a Plains" is not met by itself)."""
    if "any" in cond:  # "unless you control a Plains or an Island"
        return any(unless_holds(plan, controller, card, c) for c in cond["any"])
    return conditions.holds(plan, {"controller": controller, "source_card": card.id}, cond)


def entry_plan(plan: Plan, card: CardInstance, controller: str, *, pay_life: bool | None = None,
               tapped: bool = False, answers: dict[str, str] | None = None) -> dict[str, Any]:
    """How the permanent's own replacement effects modify its entering: {"tapped": bool, "life": N
    (a shock land whose controller pays), "choices": {"color": "Blue", …} (its "As ~ enters, choose
    …" answers, ``answers``), "choice": {"life": N} | {"what": "color"} (the next thing still to be
    decided: 614.12a, choices are made before it enters)}. ``tapped`` is what the effect putting it
    onto the battlefield says ("put it onto the battlefield tapped")."""
    out: dict[str, Any] = {"tapped": bool(tapped)}
    defs = [d for d in _definitions(plan, card).values() if d["kind"] == "replacement"]
    answers = dict(answers or {})
    for d in defs:  # "As ~ enters, choose a color." (614.1c): the answer is recorded on the permanent
        if d["replacement"] != "enters_choice":
            continue
        for e in d.get("effects") or []:
            what = e.get("what")
            if e.get("do") != "choose_value" or not what:
                continue
            if what in answers:
                out.setdefault("choices", {})[what] = answers[what]
            elif "choice" not in out:
                out["choice"] = {"what": what}
    for d in defs:
        kind = d["replacement"]
        if kind == "enters_tapped":
            unless = d.get("unless")
            if unless is None or not unless_holds(plan, controller, card, unless):
                out["tapped"] = True
        elif kind == "enters_with_counters" and d.get("tapped"):  # "~ enters tapped with two charge counters on it."
            out["tapped"] = True
    for d in defs:
        if d["replacement"] != "pay_life_or_tapped":
            continue
        life = int(d["life"])
        if out["tapped"] or "choice" in out:
            continue  # it enters tapped anyway ("put it onto the battlefield tapped"), or another choice comes first
        player = plan.state.players.get(controller)
        if player is None or player.life < life:
            out["tapped"] = True  # 119.4: life can be paid only from a life total of at least that much
            continue
        if pay_life is None:
            out["choice"] = {"life": life}
        elif pay_life:
            out["life"] = out.get("life", 0) + life
        else:
            out["tapped"] = True
    return out


def choice_needed(plan: Plan, card: CardInstance, entry: Entry) -> dict[str, Any] | None:
    """The choice a permanent's own "As ~ enters, you may …" asks for before it enters (614.12a)."""
    if not plan.state.players.get(entry["player"]):
        return None
    return entry_plan(plan, card, entry["player"], pay_life=entry.get("pay_life"), tapped=bool(entry.get("tapped")),
                      answers=entry.get("choices")).get("choice")


def choice_prompt(plan: Plan, card: CardInstance, controller: str, choice: dict[str, Any]) -> tuple[str, list[DecisionOption]]:
    """The prompt and options for one entering choice (a shock land's life, or a named choice)."""
    if "life" in choice:
        n = choice["life"]
        return (f"{card.name}: pay {n} life, or it enters tapped?",
                [DecisionOption(id="pay", label=f"Pay {n} life (untapped)"), DecisionOption(id="tapped", label="Enters tapped")])
    from app.rules.effects import _choice_options

    what = choice["what"]
    article = "an" if what[:1] in "aeiou" else "a"
    return f"{card.name}: as it enters, choose {article} {what}", _choice_options(plan, {"controller": controller}, what)


def _answer(entry_or_answers: dict[str, Any], choice: dict[str, Any], chosen: str) -> dict[str, Any]:
    """Record an answer: a shock land's ``pay_life``, or a named choice under ``choices``."""
    if "life" in choice:
        return {**entry_or_answers, "pay_life": chosen == "pay"}
    return {**entry_or_answers, "choices": {**(entry_or_answers.get("choices") or {}), choice["what"]: chosen}}


def ask_entry_choice(plan: Plan, entry: Entry, rest: list[Entry], ctx: dict[str, Any] | None, shuffle: str | None) -> None:
    """A shock land put onto the battlefield by an effect: its controller decides in private (the
    card may come from a hidden zone: the prompt names it only to them)."""
    from app.rules.plan import decide

    card = plan.state.cards[entry["card"]]
    choice = choice_needed(plan, card, entry) or {"life": 0}
    prompt, options = choice_prompt(plan, card, entry["player"], choice)
    if not options:  # (no opponent left to choose, 800.4: the choice is skipped)
        entry = _answer(entry, choice, "")
        from app.rules import attachments

        if attachments.enter(plan, [entry, *rest], ctx, shuffle=shuffle):
            _finish_entries(plan, ctx, shuffle)
        return
    decide(plan, player=entry["player"], kind="choose_one", prompt=prompt, options=options,
           resume={"step": "enter_choice", "entry": entry, "rest": rest, "ctx": ctx, "shuffle": shuffle, "choice": choice},
           source=card)


def _finish_entries(plan: Plan, ctx: dict[str, Any] | None, shuffle: str | None) -> None:
    from app.rules.effects import continue_effects

    if shuffle:
        plan.do({"type": "shuffle", "player": shuffle, "zone": "library"}, actor=shuffle)
    if ctx is not None:
        continue_effects(plan, ctx)


def resume_entry_choice(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import attachments

    entry = _answer(d.resume["entry"], d.resume.get("choice") or {"life": 0}, chosen[0])
    rest, ctx, shuffle = d.resume.get("rest") or [], d.resume.get("ctx"), d.resume.get("shuffle")
    if not attachments.enter(plan, [entry, *rest], ctx, shuffle=shuffle):
        return  # another choice (a second shock land, an Aura choosing what it enchants)
    _finish_entries(plan, ctx, shuffle)


def stack_entry_choice(plan: Plan, card: CardInstance, controller: str) -> bool:
    """A permanent spell about to resolve with an "As ~ enters, choose …" ability: ask its
    controller before it enters (614.12a). True while a question is open; the answers wait in
    ``RulesState.entry_choices`` and the spell resolves again with them."""
    from app.rules.plan import decide

    r = plan.rules
    ep = entry_plan(plan, card, controller, answers=r.entry_choices.get(card.id))
    choice = ep.get("choice")
    if choice is None or "what" not in choice:
        return False  # (a shock land's question is never asked on the stack: the wording is printed on lands)
    prompt, options = choice_prompt(plan, card, controller, choice)
    if not options:
        r.entry_choices.setdefault(card.id, {})[choice["what"]] = ""
        return stack_entry_choice(plan, card, controller)
    decide(plan, player=controller, kind="choose_one", prompt=prompt, options=options,
           resume={"step": "stack_enter_choice", "card": card.id, "what": choice["what"]}, source=card)
    return True


def resume_stack_enter_choice(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules.engine import resolve_top_of_stack

    plan.rules.entry_choices.setdefault(d.resume["card"], {})[d.resume["what"]] = chosen[0]
    resolve_top_of_stack(plan)


def resume_land_enter_choice(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.game import actions as A
    from app.rules.engine import play_land

    plan.rules.entry_choices.setdefault(d.resume["card"], {})[d.resume["what"]] = chosen[0]
    plan.rules.priority = d.player
    play_land(plan, A.parse_action(d.resume["intent"]))  # type: ignore[arg-type]


def move_onto_battlefield(plan: Plan, entry: Entry) -> None:
    """Put one card onto the battlefield under ``entry["player"]``'s control with its "enters"
    replacements applied: tapped status is part of the move itself (it never enters untapped and
    then taps), a shock land's life is paid as it enters, its "enters with" counters and loyalty
    follow as the same event (122.6, 306.5b). Extras recorded on the entry by the effect that puts it
    there — a persist / undying counter, unearth's haste and "exile it instead" — are applied after."""
    card = plan.state.cards.get(entry["card"])
    if card is None:
        return
    controller, actor = entry["player"], entry["actor"]
    ep = entry_plan(plan, card, controller, pay_life=entry.get("pay_life"), tapped=bool(entry.get("tapped")),
                    answers=entry.get("choices"))
    if ep.get("life"):
        plan.do({"type": "life", "player": controller, "delta": -int(ep["life"])}, actor=actor)
    payload: dict[str, Any] = {"type": "move", "card_ids": [card.id], "to": {"player": controller, "zone": "battlefield"}}
    if ep["tapped"]:
        payload["tapped"] = True
    plan.do(payload, actor=actor)
    after_entry(plan, card.id, controller, x=entry.get("x"), extra_counters={entry["counter"]: 1} if entry.get("counter") else None,
                choices=ep.get("choices"))
    entered = plan.state.cards.get(card.id)
    if entered is None or not entered.zone.endswith(":battlefield"):
        return
    oid = plan.oid(entered)
    if entry.get("gain_haste"):
        from app.rules import layers

        layers.add_effect(plan, affected=[oid], layer="6", source=None, controller=controller, add_keywords=("haste",),
                          duration="permanent", label=f"Haste ({entry['gain_haste']})")
    if entry.get("exile_if_leaves"):  # 702.84a: "If it would leave the battlefield, exile it instead of putting it anywhere else."
        plan.rules.exile_if_leaves.append(oid)
    if entry.get("delayed"):  # "Exile it at the beginning of the next end step" (702.84a) — a delayed trigger (603.7)
        from app.rules import delayed

        delayed.create_move(plan, controller, entered.id, oid, entry["delayed"], entered.name)


def _counter_amount(plan: Plan, card_id: str, controller: str, d: dict[str, Any], x: int | None) -> int:
    n = d["n"]
    if n == "X":  # the X its spell was cast with (107.3); 0 when it wasn't cast (put onto the battlefield)
        amount = int(x or 0)
    elif isinstance(n, dict):  # "for each creature card in your graveyard": the values grammar
        amount = values.evaluate(plan, {"controller": controller, "source_card": card_id}, n)
    else:
        amount = int(n)
    if d.get("if_kicked") or d.get("per_kick"):  # 702.33e: how its spell was cast (the payment record)
        record = plan.rules.payments.get(plan.oid(card_id))
        kicked = record.kicked if record is not None else 0
        amount = 0 if d.get("if_kicked") and not kicked else amount * kicked if d.get("per_kick") else amount
    return amount


def after_entry(plan: Plan, card_id: str, controller: str, *, x: int | None = None,
                extra_counters: dict[str, int] | None = None, choices: dict[str, str] | None = None) -> None:
    """The "enters with" part of entering (122.6: counters put on it as it enters, by its controller;
    306.5b: a planeswalker's loyalty), right after the move that put it onto the battlefield, and the
    record of what was chosen as it entered ("Chosen color: Blue" on the permanent, 614.12a)."""
    card = plan.state.cards.get(card_id)
    if card is None or not card.zone.endswith(":battlefield"):
        return
    if choices:
        from app.rules.effects import CHOICE_LABELS

        for what, value in choices.items():
            if not value or what not in CHOICE_LABELS:
                continue
            shown = plan.name(value) if what in ("opponent", "player") and value in plan.state.players else value
            plan.do({"type": "set_choice", "card_id": card_id, "key": CHOICE_LABELS[what], "value": shown}, actor=controller)
    counters: dict[str, int] = dict(extra_counters or {})
    ch = plan.ch(card)
    if "Planeswalker" in ch.types:  # 306.5b: intrinsic, however it enters (even a card taken out of automation)
        # (a printed loyalty of X is the X its spell was cast with, 107.3; 0 when it wasn't cast)
        loyalty = int(ch.loyalty) if ch.loyalty and ch.loyalty.isdigit() else int(x or 0) if ch.loyalty == "X" else 0
        if loyalty:
            counters["loyalty"] = counters.get("loyalty", 0) + loyalty
    if not plan.manual(card):
        r = plan.rules
        bled = any(t == plan.state.turn.number for p, t in r.damaged.items() if p != card.controller)
        for ab in ch.abilities:  # 702.54 bloodthirst N: if an opponent was dealt damage this turn
            if ab.kind == "keywords" and bled:
                for kw in ab.keywords:
                    if kw == "bloodthirst":
                        m = re.fullmatch(r"bloodthirst (\d+)", ab.text.strip().rstrip(".").lower())
                        if m:
                            counters["+1/+1"] = counters.get("+1/+1", 0) + int(m.group(1))
        for d in scripts.definitions(ch).values():
            if d["kind"] == "replacement" and d.get("replacement") == "enters_with_counters":
                n = _counter_amount(plan, card_id, controller, d, x)
                if n > 0:
                    counters[d["counter"]] = counters.get(d["counter"], 0) + n
    for kind, n in counters.items():
        if n > 0:
            plan.do({"type": "counter", "card_ids": [card_id], "kind": kind, "delta": n}, actor=controller)


def token_enters_tapped(plan: Plan, controller: str, spec: dict[str, Any]) -> bool:
    """A token about to be created: does its own text say it enters tapped? (Its creator saying
    "create … tapped" is the effect's own business; both count.)"""
    probe = CardInstance(id="token-probe", name=spec["name"], owner=controller, controller=controller,
                         zone=zone_key(controller, "battlefield"), is_token=True,
                         token=TokenDef(name=spec["name"], power=spec.get("power"), toughness=spec.get("toughness"),
                                        colors=list(spec.get("colors") or []), type_line=spec["type_line"], text=spec.get("text") or ""))
    for d in scripts.definitions(chars.of(probe, plan.info)).values():
        if d["kind"] != "replacement":
            continue
        if d["replacement"] == "enters_tapped" and (d.get("unless") is None or not unless_holds(plan, controller, probe, d["unless"])):
            return True
        if d["replacement"] == "enters_with_counters" and d.get("tapped"):
            return True
    return False


# -- zone changes (614.1a "instead", 702.84a, 702.35a, 903.9b) ------------------------------------------
def _from_zone(card: CardInstance) -> str:
    return card.zone.rsplit(":", 1)[-1]


def _self_exile_instead(plan: Plan, card: CardInstance) -> bool:
    """"If ~ would die, exile it instead." (from the battlefield) / "If ~ would be put into a
    graveyard from anywhere, exile it instead." — the object's own replacement effect."""
    frm = _from_zone(card)
    return any(d["kind"] == "replacement" and d.get("replacement") == "exile_instead"
               and (d.get("from") == "anywhere" or frm == "battlefield") for d in _definitions(plan, card).values())


def _static_exile_instead(plan: Plan, card: CardInstance) -> CardInstance | None:
    """A permanent on the battlefield whose static ability replaces this card's trip to the
    graveyard ("If a creature an opponent controls would die, exile it instead.", "If a card or
    token would be put into a graveyard from anywhere, exile it instead."): the first that applies."""
    frm = _from_zone(card)
    for src in plan.state.cards.values():
        if not src.zone.endswith(":battlefield") or src.face_down or not plan.in_game(src) or plan.manual(src):
            continue
        for d in scripts.definitions(plan.ch(src)).values():
            if d["kind"] != "static" or d.get("static") != "exile_instead":
                continue
            if d.get("from") == "battlefield" and frm != "battlefield":
                continue
            whose = d.get("graveyard_of", "any")  # "your graveyard" / "an opponent's graveyard"
            if whose == "you" and card.owner != src.controller or whose == "opponent" and card.owner == src.controller:
                continue
            who = d.get("who", "any")
            if who == "card" and card.is_token:
                continue  # "If a card would be put into …": tokens aren't cards (108.2a)
            if who not in ("any", "card"):
                if frm != "battlefield":
                    continue
                if not selectors.matches(plan, selectors.from_key(who), card, plan.ch(card), src.controller, src.id):
                    continue
            return src
    return None


def _commander_instead(plan: Plan, card: CardInstance, dest: str) -> bool | None:
    """903.9b: a commander that would be put into its owner's hand or library may go to the command
    zone instead. True: a remembered answer ("always" / "this turn", the same memory key as 903.9a
    with the destination as its context) says so and the move is replaced. None: no answer is known
    — a ``Plan.do`` step can't pause for a decision, so the move happens as asked and its owner is
    asked right after (``pending_903_9b``, offered by app/rules/sba.py before anyone gets priority)
    whether it goes to the command zone instead; the answer is remembered for the next time."""
    from app.rules.engine import remembered

    if not card.commander_key or card.owner not in plan.live():
        return False
    answer = remembered(plan, card.owner, f"commander_zone:{card.commander_key}", dest)
    return True if answer == "yes" else False if answer == "no" else None


def replace_move(plan: Plan, payload: dict[str, Any], actor: str | None) -> dict[str, Any]:
    """Apply the zone-change replacements to a ``move`` (or ``mill``) step before it happens. Cards
    whose move is replaced are moved separately to where the replacement says; the rest move as
    asked. Self-replacement first (614.15), then the object's own and the statics' "exile instead"
    (all of which agree, so there is no 616.1 choice to make), then madness, then 903.9b."""
    kind = payload.get("type")
    if kind == "mill":
        return _replace_mill(plan, payload, actor)
    if kind != "move":
        return payload
    dest = (payload.get("to") or {}).get("zone")
    r = plan.rules
    replaced: list[tuple[str, str, str]] = []  # (card, zone it goes to instead, why)
    madness: list[tuple[str, str]] = []
    for cid in payload.get("card_ids") or []:
        card = plan.state.cards.get(cid)
        if card is None:
            continue
        frm = _from_zone(card)
        oid = plan.oid(card)
        if frm == "battlefield" and dest not in ("exile", "battlefield") and oid in r.exile_if_leaves:
            r.exile_if_leaves = [o for o in r.exile_if_leaves if o != oid]  # used up (614.5)
            replaced.append((cid, "exile", "unearth"))
            continue
        if dest == "graveyard":
            if frm == "hand":
                # 616.1: madness and an "exile instead" static (Rest in Peace) would both replace a
                # discard; the card's owner chooses. Only madness leads anywhere different (the
                # card is exiled either way, and may then be cast), so it is applied first.
                cost = _madness_cost(plan, card)
                if cost is not None:
                    madness.append((cid, cost))
                    continue
            if _self_exile_instead(plan, card):
                replaced.append((cid, "exile", card.name or "its own ability"))
                continue
            src = _static_exile_instead(plan, card)
            if src is not None:
                replaced.append((cid, "exile", src.name or "a static ability"))
                continue
        if dest in ("hand", "library"):
            answer = _commander_instead(plan, card, dest)
            if answer:
                replaced.append((cid, "command", "903.9b"))
            elif answer is None:
                r.pending_903_9b[cid] = dest  # asked right after the move (sba → offer_903_9b)
    if not replaced and not madness:
        return payload
    for cid, zone, _why in replaced:
        owner = plan.state.cards[cid].owner
        plan.do({"type": "move", "card_ids": [cid], "to": {"player": owner, "zone": zone}}, actor=actor)
    for cid, cost in madness:
        _discard_into_exile(plan, cid, cost, actor)
    taken = {cid for cid, _, _ in replaced} | {cid for cid, _ in madness}
    rest = [c for c in payload["card_ids"] if c not in taken]
    if rest:
        return {**payload, "card_ids": rest}
    whys = sorted({why for _, _, why in replaced})
    text = ("Exiled instead" + (f" ({', '.join(whys)})" if whys and whys != ["903.9b"] else "")) if replaced else "Discarded into exile (madness)"
    if replaced and all(zone == "command" for _, zone, _ in replaced):
        text = "Put into the command zone instead (903.9b)"
    ids = [cid for cid, _, _ in replaced] + [cid for cid, _ in madness]
    return {"type": "rules_log", "text": text, "card_ids": ids[:20]}  # (a log line names at most 20 cards)


def _replace_mill(plan: Plan, payload: dict[str, Any], actor: str | None) -> dict[str, Any]:
    """Milled cards that would be exiled instead ("If ~ would be put into a graveyard from anywhere",
    a Rest in Peace on the battlefield): the mill becomes one move per card, in library order."""
    if payload.get("to", "graveyard") != "graveyard":
        return payload
    pid = payload.get("player") or actor or plan.actor
    library = plan.state.zones.get(zone_key(pid, "library"), [])
    top = library[: int(payload.get("count", 1))]
    exiled = [cid for cid in top if _self_exile_instead(plan, plan.state.cards[cid]) or _static_exile_instead(plan, plan.state.cards[cid]) is not None]
    if not exiled:
        return payload
    for cid in top:
        zone = "exile" if cid in exiled else "graveyard"
        plan.do({"type": "move", "card_ids": [cid], "to": {"player": pid, "zone": zone}}, actor=actor)
    return {"type": "rules_log", "text": f"{plan.name(pid)} milled {len(top)}: exiled instead", "card_ids": exiled[:20]}


def _madness_cost(plan: Plan, card: CardInstance) -> str | None:
    """702.35a madness: a card discarded from a hand is discarded into exile instead."""
    from app.rules.casting import MADNESS, keyword_cost  # casting → plan → this module

    if plan.manual(card):
        return None
    return keyword_cost(plan.ch(card), "madness", MADNESS)


def _discard_into_exile(plan: Plan, cid: str, cost: str, actor: str | None) -> None:
    """702.35a: "… discard it into exile. When this card is exiled this way, its owner may cast it by
    paying [cost] rather than its mana cost. If that player doesn't, they put this card into their
    graveyard." — the exile, then the reflexive trigger that offers the cast."""
    from app.rules.triggers import _add

    card = plan.state.cards[cid]
    plan.do({"type": "move", "card_ids": [cid], "to": {"player": card.owner, "zone": "exile"}}, actor=actor)
    plan.rules.free_casts.append(cid)
    plan.rules.alt_costs[cid] = cost
    _add(plan, controller=card.owner, source_card=cid, source_object=plan.oid(cid), name=card.name, index=8000,
         definition={"kind": "triggered", "trigger": "madness", "optional": False, "target": None,
                     "effects": [{"do": "madness_offer", "card": cid, "cost": cost}]})


def offer_903_9b(plan: Plan) -> bool:
    """A commander that was just put into its owner's hand or library without a known answer to
    903.9b: ask its owner now (the one place, whatever moved it). Returns True while a question is
    open. The answer is remembered (the 903.9a memory key with the destination as its context), so
    the next such move is replaced outright."""
    from app.rules.plan import decide

    r = plan.rules
    for cid, dest in list(r.pending_903_9b.items()):
        card = plan.state.cards.get(cid)
        if card is None or _from_zone(card) != dest or not card.commander_key or card.owner not in plan.live():
            r.pending_903_9b.pop(cid, None)  # it went on elsewhere: the moment has passed
            continue
        where = "your library" if dest == "library" else "your hand"
        decide(plan, player=card.owner, kind="confirm",
               prompt=f"{card.name} was put into {where}: put it into the command zone instead? (903.9b)",
               options=[DecisionOption(id="yes", label="Command zone"), DecisionOption(id="no", label=f"Keep it in {where}")],
               resume={"step": "commander_instead", "card": cid, "dest": dest}, source=card,
               memory_key=f"commander_zone:{card.commander_key}", memory_context=dest)
        return True
    return False


def resume_commander_instead(plan: Plan, d: Any, chosen: list[str]) -> None:
    cid = d.resume["card"]
    plan.rules.pending_903_9b.pop(cid, None)
    card = plan.state.cards.get(cid)
    if chosen[0] == "yes" and card is not None and _from_zone(card) == d.resume["dest"]:
        plan.do({"type": "move", "card_ids": [cid], "to": {"player": card.owner, "zone": "command"}}, actor=card.owner)


# -- damage prevention (615) ------------------------------------------------------------------------
DamageEvent = dict[str, Any]  # {"source_card", "source_oid", "target" (player id or card id), "amount", "combat", "prevented"}


def _static_records(plan: Plan) -> list[dict[str, Any]]:
    out = []
    for c in plan.state.cards.values():
        if not c.zone.endswith(":battlefield") or c.face_down or not plan.in_game(c) or plan.manual(c):
            continue
        for d in scripts.definitions(plan.ch(c)).values():
            if d["kind"] == "static" and d.get("static") == "prevent":
                out.append({"kind": "prevent", "controller": c.controller, "source": plan.oid(c), "source_card": c.id,
                            "scope": d["scope"]})
    return out


def _records(plan: Plan) -> list[dict[str, Any]]:
    """Prevention effects in force: statics of permanents on the battlefield, then this turn's
    records (a record from another turn has expired: "this turn")."""
    turn = plan.state.turn.number
    r = plan.rules
    if any(rec.get("turn") != turn for rec in r.replacements):
        r.replacements = [rec for rec in r.replacements if rec.get("turn") == turn]
    return _static_records(plan) + [rec for rec in r.replacements if rec.get("kind") == "prevent"]


def _source_card(plan: Plan, ev: DamageEvent) -> CardInstance | None:
    card = plan.state.cards.get(ev.get("source_card") or "")
    return card if card is not None and plan.oid(card) == ev.get("source_oid") else None


def _object_matches(plan: Plan, spec: str, card: CardInstance, you: str, source_card: str | None) -> bool:
    if spec == "self":
        return card.id == source_card
    if spec == "attached":  # "enchanted creature" / "equipped creature": what the source is attached to now
        src = plan.state.cards.get(source_card or "")
        return src is not None and src.attached_to == card.id
    return selectors.matches(plan, selectors.from_key(spec), card, plan.ch(card), you, source_card)


def _target_in_scope(plan: Plan, sc: dict[str, Any], you: str, source_card: str | None, target: str) -> bool:
    if target in plan.state.players:
        want = sc.get("to_players")
        if want is None:
            return bool(sc.get("any_target"))
        return not (want == "you" and target != you or want == "opponent" and target == you)
    card = plan.state.cards.get(target)
    if card is None:
        return False
    if sc.get("to_oids"):
        return plan.oid(card) in sc["to_oids"]
    if sc.get("to_objects"):
        return _object_matches(plan, sc["to_objects"], card, you, source_card)
    return bool(sc.get("any_target"))


def _source_in_scope(plan: Plan, sc: dict[str, Any], you: str, source_card: str | None, ev: DamageEvent) -> bool:
    if sc.get("by_oids"):
        return ev.get("source_oid") in sc["by_oids"]
    if sc.get("by_objects"):
        src = _source_card(plan, ev)
        return src is not None and _object_matches(plan, sc["by_objects"], src, you, source_card)
    return True


def _applies(plan: Plan, rec: dict[str, Any], ev: DamageEvent) -> bool:
    """Does a "prevent all …" effect apply to this damage event? Its scope names what the damage
    would be dealt to and/or by; combat / noncombat when it says so (609.7c: a static's source
    filter applies to any source with the property, on the battlefield or not)."""
    sc = rec["scope"]
    you, source_card = rec["controller"], rec.get("source_card")
    if sc.get("combat") is not None and bool(sc["combat"]) != bool(ev.get("combat")):
        return False
    if sc.get("to_or_by"):  # "… dealt to and dealt by ~" (Fog Bank): either side
        return _target_in_scope(plan, sc, you, source_card, ev["target"]) or _source_in_scope(plan, sc, you, source_card, ev)
    return _target_in_scope(plan, sc, you, source_card, ev["target"]) and _source_in_scope(plan, sc, you, source_card, ev)


def _label(plan: Plan, key: str) -> str:
    if key in plan.state.players:
        return plan.name(key)
    card = plan.state.cards.get(key)
    return (card.name if card is not None else None) or "the permanent"


def _shield_signature(plan: Plan, ev: DamageEvent) -> tuple[Any, ...]:
    """What makes two sources' damage to a shielded target interchangeable: the same amount from
    literally identical objects (same card or token definition, controller, counters, attachments,
    continuous effects on them) — anything else (a damage trigger, a keyword) could make the outcome
    differ, so the choice is asked (615.7)."""
    src = _source_card(plan, ev)
    if src is None:
        return (ev["amount"] - ev["prevented"], None)
    token = src.token
    identity = (src.card_id, src.face, src.face_down, token.name if token else None, token.text if token else None,
                token.power if token else None, token.toughness if token else None, tuple(token.colors) if token else ())
    return (ev["amount"] - ev["prevented"], src.controller, src.commander_key, identity,
            tuple(sorted(src.counters.items())), src.attached_to,
            tuple(sorted(o.id for o in plan.state.cards.values() if o.attached_to == src.id)),
            tuple(sorted(e.id for e in plan.rules.effects if plan.oid(src) in e.affected)),
            tuple(sorted(m.value or m.name for m in src.effects)))


def apply_prevention(plan: Plan, events: list[DamageEvent], *, order: list[str] | None = None,
                     resume: dict[str, Any] | None = None) -> list[DamageEvent] | None:
    """Prevention effects on one simultaneous damage event batch (615.1): each event's ``prevented``
    is set. First the "prevent all …" effects in force (statics and this turn's records), then the
    "prevent the next N" shields (615.7): when two or more sources would deal damage to a shielded
    player or permanent at the same time and it matters which is prevented, the player or the
    permanent's controller chooses (a private decision; ``order`` holds the answers so far, as
    "<target>:<source object>"). Returns None while such a choice is open (only when ``resume``
    gives the step to continue: combat damage), else the events."""
    from app.rules.plan import decide

    r = plan.rules
    for ev in events:
        ev["prevented"] = 0
    recs = _records(plan)
    for ev in events:
        if ev["amount"] <= 0:
            continue
        for rec in recs:
            if _applies(plan, rec, ev):
                ev["prevented"] = ev["amount"]
                who = _label(plan, ev["target"])
                plan.note(f"{ev['amount']} damage to {who} prevented")
                break
    if not r.prevention:
        return events
    picks = list(order or [])
    by_target: dict[str, list[DamageEvent]] = {}
    for ev in events:
        if ev["amount"] - ev["prevented"] > 0 and r.prevention.get(ev["target"] if ev["target"] in plan.state.players
                                                                  else plan.oid(ev["target"]), 0) > 0:
            by_target.setdefault(ev["target"], []).append(ev)
    for target, evs in by_target.items():
        key = target if target in plan.state.players else plan.oid(target)
        shield = r.prevention.get(key, 0)
        pending = list(evs)
        while shield > 0 and pending:
            if len(pending) == 1 or len({_shield_signature(plan, e) for e in pending}) == 1:
                ev = pending[0]  # one source, or literally identical ones: the outcome is the same either way
            else:
                mine = [p for p in picks if p.startswith(f"{target}:")]
                if mine:
                    pick = mine[0]
                    picks.remove(pick)
                    ev = next((e for e in pending if f"{target}:{e['source_oid']}" == pick), pending[0])
                elif resume is None:
                    ev = pending[0]  # (noncombat damage has one source: never reached)
                else:
                    chooser = target if target in plan.state.players else plan.state.cards[target].controller
                    options = []
                    for e in pending:
                        src = _source_card(plan, e)
                        options.append(DecisionOption(id=f"{target}:{e['source_oid']}",
                                                      label=f"{(src.name if src else None) or 'a source'} ({e['amount'] - e['prevented']})",
                                                      card_id=src.id if src is not None else None))
                    decide(plan, player=chooser, kind="choose_one",
                           prompt=f"{_label(plan, target)}: a shield prevents the next {shield} damage — which source's damage does it prevent first? (615.7)",
                           options=options, resume={**resume, "step": "shield_order", "order": list(order or [])})
                    return None
            left = ev["amount"] - ev["prevented"]
            used = min(shield, left)
            ev["prevented"] += used
            shield -= used
            plan.note(f"{used} damage to {_label(plan, target)} prevented (shield)")
            if ev["amount"] - ev["prevented"] <= 0:
                pending.remove(ev)
        if shield > 0:
            r.prevention[key] = shield
        else:
            r.prevention.pop(key, None)
    return events


def resume_shield_order(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import combat
    from app.rules.engine import _after_resolution

    order = [*(d.resume.get("order") or []), chosen[0]]
    if combat.deal_combat_damage(plan, d.resume["round"], shield_order=order):
        _after_resolution(plan)


def prevent_all(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """"Prevent all [combat] damage that would be dealt [to …] [by …] this turn": a record for this
    turn. A targeted one locks its target (the object it is now: 400.7); with no legal target left
    nothing is recorded."""
    from app.rules.effects import _cards

    scope = dict(e["scope"])
    if e.get("who") == "target":
        oids = [plan.oid(c) for c in _cards(plan, ctx, "target")]
        if not oids:
            return True
        scope["by_oids" if e.get("role") == "by" else "to_oids"] = oids
    plan.rules.replacements.append({"id": secrets.token_hex(4), "kind": "prevent", "turn": plan.state.turn.number,
                                    "controller": ctx["controller"], "source": ctx.get("source_object"), "scope": scope})
    return True

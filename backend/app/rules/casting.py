"""Mana abilities, paying costs and casting spells (milestone 15).

Casting follows the real order (announce → move to the stack → pay), but everything is planned on
the scratch table first, so a spell you can't pay for simply isn't cast: nothing half-happens.
Costs are paid automatically from your mana pool and untapped mana sources (see ``mana.solve``);
tap lands yourself first (``activate_ability`` on their mana ability) to pay a particular way.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import Any

from app.game import actions as A
from app.game.errors import ActionError
from app.game.rules_state import DecisionOption, StackEntry, TargetRef, TurnCount, emit
from app.game.state import STACK, CardInstance, GameState, zone_key
from app.rules import characteristics as chars
from app.rules import commander as cmdr
from app.rules import mana as M
from app.rules import scripts
from app.rules.characteristics import CardInfo, Characteristics
from app.rules.costs import AbilityCost, parse_ability_cost
from app.rules.oracle import AbilityText
from app.rules.plan import Plan, decide, require_no_decision, require_priority
from app.rules.targets import label as target_label
from app.rules.targets import legal_targets, source_of
from app.rules.targets import ref as target_ref

MAIN_PHASES = ("main1", "main2")


# -- facts about permanents -------------------------------------------------------------
def commander_identity(state: GameState, player: str, info: CardInfo) -> tuple[str, ...]:
    commanders = [info.get(c.card_id) for c in state.cards.values() if c.owner == player and c.commander_key and c.card_id]
    return cmdr.deck_identity([d for d in commanders if d])  # the same identity the deck checks use


def summoning_sick(state: GameState, card: CardInstance) -> bool:
    """A creature can't attack or use {T} abilities unless its controller has controlled it
    continuously since the start of their most recent turn (haste is checked by the caller)."""
    r = state.rules
    if r is None or r.card_mode(card.id) == "manual":
        return False  # a MANUAL card's timing isn't enforced: its controller handles it
    mark = r.controlled_since.get(card.id)
    started = r.turn_started.get(card.controller)
    if mark is None or started is None:
        return True
    return mark.turn >= started


def can_use_tap_abilities(state: GameState, card: CardInstance, ch: Characteristics) -> bool:
    if card.tapped or not card.zone.endswith(":battlefield"):
        return False
    return not (ch.is_creature and "haste" not in ch.keywords and summoning_sick(state, card))


COLOR_NAMES = {"white": "W", "blue": "U", "black": "B", "red": "R", "green": "G"}


def _chosen_color(card: CardInstance) -> str | None:
    for key, value in card.choices.items():
        if "color" in key.lower():
            return COLOR_NAMES.get(value.strip().lower())
    return None


def _land_mana(state: GameState, players: list[str], info: CardInfo, *, skip: str) -> set[str]:
    """Types of mana lands these players control could produce (Reflecting Pool, Exotic Orchard)."""
    out: set[str] = set()
    for p in players:
        for cid in state.zones.get(zone_key(p, "battlefield"), []):
            if cid == skip:
                continue
            card = state.cards[cid]
            ch = chars.of(card, info)
            if not ch.is_land:
                continue
            for ab in ch.abilities:
                if ab.kind != "mana":
                    continue
                parsed = M.parse_mana_ability(ab.text)
                if parsed is None:
                    continue
                for opt in parsed.options:
                    out |= {m for m in opt if m in M.ALL_MANA}
    return out


def _mana_count(state: GameState, card: CardInstance, count: str, info: CardInfo) -> int:
    """How many times a counted mana ability's mana is added (Gaea's Cradle, Cabal Coffers, …)."""
    from app.rules.layers import derive

    if count == "power":
        ch = derive(state, card, chars.of(card, info), info)
        if ch.pt:
            return max(0, ch.pt[0])
        return int(ch.power) if ch.power and ch.power.isdigit() else 0
    what = count.split(":", 1)[1]
    n = 0
    for cid in state.zones.get(zone_key(card.controller, "battlefield"), []):
        c = state.cards[cid]
        if c.controller != card.controller:
            continue
        ch = derive(state, c, chars.of(c, info), info)
        if what in ch.types or what in ch.subtypes:
            n += 1
    return n


def _resolve_options(state: GameState, card: CardInstance, ab: M.ManaAbility, info: CardInfo) -> tuple[tuple[str, ...], ...]:
    if ab.count:
        n = _mana_count(state, card, ab.count, info)
        return tuple(opt * n for opt in ab.options) if n > 0 else ()
    out: list[tuple[str, ...]] = []
    for opt in ab.options:
        if "CHOSEN" in opt:
            color = _chosen_color(card)
            if color is None:
                continue  # nothing chosen yet: that option can't be used
            out.append(tuple(color if m == "CHOSEN" else m for m in opt))
        elif opt == ("LANDS",):
            out += [(m,) for m in M.ALL_MANA if m in _land_mana(state, [card.controller], info, skip=card.id)]
        elif opt == ("LANDS_OPP",):
            opponents = [p for p in state.seat_order if p != card.controller]
            out += [(m,) for m in M.COLORS if m in _land_mana(state, opponents, info, skip=card.id)]
        else:
            out.append(opt)
    return tuple(dict.fromkeys(out))


def _controls(state: GameState, player: str, what: str, info: CardInfo) -> bool:
    for cid in state.zones.get(zone_key(player, "battlefield"), []):
        ch = chars.of(state.cards[cid], info)
        if what in ch.subtypes or what in ch.types:
            return True
    return False


def mana_abilities(state: GameState, card: CardInstance, info: CardInfo) -> list[tuple[int, M.ManaAbility]]:
    """The permanent's mana abilities the engine can carry out right now (options resolved:
    chosen color, lands' mana; conditions, once-per-turn and non-mana costs checked)."""
    ch = chars.of(card, info)
    identity = commander_identity(state, card.controller, info)
    r = state.rules
    out = []
    for ab in ch.abilities:
        if ab.kind != "mana":
            continue
        parsed = M.parse_mana_ability(ab.text, identity)
        if parsed is None:
            continue
        if parsed.condition and parsed.condition.startswith("control:") and \
                not _controls(state, card.controller, parsed.condition.split(":", 1)[1], info):
            continue
        if parsed.once_per_turn and r is not None and \
                r.once_per_turn.get(f"{r.object_id(card.id)}:{ab.index}") == state.turn.number:
            continue
        if parsed.extra_cost:
            extra = parse_ability_cost(parsed.extra_cost, card_name=ch.name)
            if extra.unsupported or (extra.life and state.players[card.controller].life < extra.life) or \
                    any(card.counters.get(k, 0) < n for k, n in extra.remove_counters):
                continue
        options = _resolve_options(state, card, parsed, info)
        if options:
            out.append((ab.index, replace(parsed, options=options)))
    return out


def spend_allowed(kind: str | None, purpose: Purpose | None) -> bool:
    """May mana with this spending restriction pay for ``purpose``?"""
    if kind is None:
        return True
    if purpose is None:
        return False
    spell, source = purpose.spell, purpose.ability_of
    if kind == "creature":
        return spell is not None and spell.is_creature
    if kind == "instant_sorcery":
        return spell is not None and bool(spell.types & {"Instant", "Sorcery"})
    if kind == "artifact":
        return spell is not None and "Artifact" in spell.types
    if kind == "ability":
        return source is not None
    if kind == "artifact_or_artifact_ability":
        return (spell is not None and "Artifact" in spell.types) or (source is not None and "Artifact" in source.types)
    if kind == "legendary":
        return spell is not None and "Legendary" in spell.supertypes
    if kind.startswith("type:"):
        t = kind[5:]
        return spell is not None and (t in spell.subtypes or t in spell.types)
    return False


def mana_sources(state: GameState, player: str, info: CardInfo, purpose: Purpose | None = None) -> list[M.Source]:
    """Untapped permanents ``player`` controls that can pay for things right now. Each permanent
    is one source whose options are ordered painless-first; a filter-style ability (with its own
    mana cost) is a separate source that other mana must pay for."""
    out: list[M.Source] = []
    for cid in state.zones.get(zone_key(player, "battlefield"), []):
        card = state.cards[cid]
        if card.controller != player:
            continue
        ch = chars.of(card, info)
        usable_tap = can_use_tap_abilities(state, card, ch)
        abilities = [(i, ab) for i, ab in mana_abilities(state, card, info)
                     if (usable_tap or not ab.tap) and spend_allowed(ab.spend_only, purpose)]
        rank = 0 if ch.is_land else 2 if ch.is_creature else 1
        free = [(i, ab) for i, ab in abilities if not parse_ability_cost(ab.extra_cost, card_name=ch.name).mana]
        plain = [(i, ab) for i, ab in free if not ab.sacrifice_self and ab.tap]
        chosen = plain or [(i, ab) for i, ab in free if ab.tap]
        if chosen:
            pairs: dict[tuple[str, ...], tuple[int, int]] = {}
            for i, ab in sorted(chosen, key=lambda x: x[1].penalty):
                for opt in ab.options:
                    pairs.setdefault(opt, (i, ab.penalty))
            opts = tuple(pairs)
            out.append(M.Source(card.id, opts, sacrifice=not plain, rank=rank + (5 if not plain else 0),
                                abilities=tuple(pairs[o][0] for o in opts)))
        for i, ab in abilities:
            mana_cost = parse_ability_cost(ab.extra_cost, card_name=ch.name).mana
            if mana_cost and ab.tap and not ab.sacrifice_self:
                out.append(M.Source(card.id, ab.options, rank=rank + 3, abilities=(i,) * len(ab.options),
                                    activation=M.parse_cost(mana_cost)))
    if purpose is not None and purpose.spell is not None and "convoke" in purpose.spell.keywords:
        out = _convoke_sources(state, player, info, out)
    return out


CONVOKE = -1  # the "ability index" of a creature tapped for convoke (not a mana ability)


def _convoke_sources(state: GameState, player: str, info: CardInfo, out: list[M.Source]) -> list[M.Source]:
    """702.51 convoke: each untapped creature you control can be tapped to pay for {1} or one mana
    of that creature's color (summoning sickness doesn't matter: it isn't a {T} ability)."""
    from app.rules.layers import derive

    by_card = {s.card_id: k for k, s in enumerate(out)}
    for cid in state.zones.get(zone_key(player, "battlefield"), []):
        card = state.cards[cid]
        if card.controller != player or card.tapped:
            continue
        ch = derive(state, card, chars.of(card, info), info)
        if not ch.is_creature:
            continue
        opts = tuple((c,) for c in sorted(ch.colors)) + (("C",),)
        if cid in by_card:  # a mana creature: its mana abilities or convoke, never both
            src = out[by_card[cid]]
            extra = tuple(o for o in opts if o not in src.options)
            abilities = src.abilities or (0,) * len(src.options)
            out[by_card[cid]] = M.Source(cid, src.options + extra, sacrifice=src.sacrifice, rank=src.rank,
                                         preferred=src.preferred, abilities=abilities + (CONVOKE,) * len(extra),
                                         activation=src.activation)
        else:
            out.append(M.Source(cid, opts, rank=4, abilities=(CONVOKE,) * len(opts)))
    return out


# -- targets (601.2c) --------------------------------------------------------------------
def choose_target(plan: Plan, a: A.CastSpell | A.ActivateAbility, definition: dict[str, Any] | None,
                  what: str) -> list[TargetRef] | None:
    """The target of an automated spell or ability: validated if given, else asked (privately).
    Returns the chosen targets, or None while waiting for the choice."""
    spec = definition.get("target") if definition else None
    if not spec:
        return []
    legal = legal_targets(plan, spec["what"], plan.actor, source_of(plan, a.card_id))
    if a.targets:
        if len(a.targets) != 1 or a.targets[0] not in legal:
            raise ActionError("That isn't a legal target")
        return [target_ref(plan, a.targets[0])]
    if not legal:
        raise ActionError(f"{what} has no legal target")
    decide(plan, player=plan.actor, kind="choose_one", prompt=f"Choose a target for {what}",
           options=[DecisionOption(id=x, label=target_label(plan, x), card_id=x if x in plan.state.cards else None) for x in legal],
           resume={"step": "cast_target", "intent": a.model_dump(mode="json", exclude={"r", "actor", "ts"})})
    return None


def resume_target(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules.engine import INTENTS  # the engine imports this module

    intent = A.parse_action(d.resume["intent"])
    intent.targets = list(chosen)  # type: ignore[union-attr]
    plan.rules.priority = d.player
    plan.rules.passed = []
    INTENTS[intent.type](plan, intent)


# -- paying mana ------------------------------------------------------------------------
PaymentMode = str  # "auto" | "ask" | "manual"


def payment_mode(plan: Plan, player: str) -> PaymentMode:
    """AUTO pays; ASK shows the suggested payment first (also when the table's AUTO MANA PAYMENT is
    off); MANUAL lets the player pick the exact sources."""
    pref = plan.rules.prefs_for(player).payment
    if pref == "manual":
        return "manual"
    if pref == "ask" or not plan.options.auto_mana_payment:
        return "ask"
    return "auto"


@dataclass(frozen=True)
class Purpose:
    """What the mana is for (spending restrictions: "Spend this mana only to cast a creature spell")."""

    spell: Characteristics | None = None
    ability_of: Characteristics | None = None


def _solve_with_filters(cost: M.ManaCost, pool: dict[str, int], plain: list[M.Source], filters: list[M.Source],
                        life: int) -> M.Payment:
    """Pay with ordinary sources; if that fails, add filter sources one or two at a time. A
    filter's own activation cost joins the requirement, and must be payable without it."""
    try:
        return M.solve(cost, pool, plain, life=life)
    except M.ManaError as first:
        error = first
    by_card: dict[str, M.Source] = {}
    for f in filters:
        by_card.setdefault(f.card_id, f)  # one filter ability per permanent (it taps)
    candidates = list(by_card.values())[:6]
    tried: list[tuple[M.Source, ...]] = [(f,) for f in candidates]
    tried += [(a, b) for i, a in enumerate(candidates) for b in candidates[i + 1:]]
    for combo in tried:
        activation = M.ManaCost()
        for f in combo:
            act = f.activation or M.ManaCost()
            activation = M.ManaCost(activation.generic + act.generic, activation.colored + act.colored,
                                    activation.hybrid + act.hybrid)
        others = [s for s in plain if s.card_id not in {f.card_id for f in combo}]
        try:
            M.solve(activation, pool, others, life=life)  # the filters can't pay for themselves
        except M.ManaError:
            continue
        total = M.ManaCost(cost.generic + activation.generic, cost.colored + activation.colored,
                           cost.hybrid + activation.hybrid, cost.phyrexian, 0, cost.unsupported)
        free = [replace(f, activation=None) for f in combo]
        try:
            return M.solve(total, pool, others + free, life=life)
        except M.ManaError:
            continue
    raise error


def find_payment(state: GameState, player: str, cost: M.ManaCost, info: CardInfo, *,
                 sources: list[str] | None = None, exclude: tuple[str, ...] = (), purpose: Purpose | None = None) -> M.Payment:
    """How to pay ``cost``: with exactly ``sources`` when given (MANUAL PAY), else automatically,
    PREFER sources first and SAVE sources only when there is no other way."""
    everything = [s for s in mana_sources(state, player, info, purpose) if s.card_id not in exclude]
    available = [s for s in everything if s.activation is None]
    filters = [s for s in everything if s.activation is not None]
    pool = dict(state.players[player].mana)
    life = state.players[player].life
    if sources is not None:
        chosen = [s for s in available if s.card_id in set(sources)]
        chosen_filters = [s for s in filters if s.card_id in set(sources) and s.card_id not in {c.card_id for c in chosen}]
        if len({s.card_id for s in chosen + chosen_filters}) != len(set(sources)):
            raise ActionError("Pick untapped mana sources you control")
        try:
            payment = _solve_with_filters(cost, pool, chosen, chosen_filters, life)
        except M.ManaError as exc:
            raise ActionError(f"Those sources can't pay {cost.text()}") from exc
        unused = set(sources) - set(payment.tapped)
        if unused:
            names = ", ".join(state.cards[c].name or "a source" for c in unused)
            raise ActionError(f"{names} isn't needed to pay {cost.text()}")
        return payment
    protection = state.rules.prefs_for(player).mana_sources if state.rules else {}
    marked = [replace(s, preferred=protection.get(s.card_id) == "prefer") for s in available]
    normal = [s for s in marked if protection.get(s.card_id) != "save"]
    normal_filters = [s for s in filters if protection.get(s.card_id) != "save"]
    try:
        return _solve_with_filters(cost, pool, normal, normal_filters, life)
    except M.ManaError:
        pass
    try:
        return _solve_with_filters(cost, pool, marked, filters, life)  # SAVE sources only when nothing else works
    except M.ManaError as exc:
        raise ActionError(f"{exc}. Tap mana yourself first, or use the table tools.") from exc


def mana_ability_extras(plan: Plan, card: CardInstance, index: int) -> tuple[int, list[tuple[str, int]]]:
    """Life to pay and counters to remove for using mana ability ``index`` (besides tapping)."""
    ability = dict(mana_abilities(plan.state, card, plan.info)).get(index)
    if ability is None or not ability.extra_cost:
        return 0, []
    extra = parse_ability_cost(ability.extra_cost, card_name=plan.ch(card).name)
    return extra.life, list(extra.remove_counters)


def after_mana_ability(plan: Plan, card: CardInstance, index: int, ability: M.ManaAbility) -> None:
    """Riders and bookkeeping once a mana ability was used: "deals 1 damage to you", "Draw a
    card", once-per-turn marks, counters removed as a cost."""
    r = plan.rules
    if ability.once_per_turn:
        r.once_per_turn[f"{r.object_id(card.id)}:{index}"] = plan.state.turn.number
    extra = parse_ability_cost(ability.extra_cost, card_name=plan.ch(card).name) if ability.extra_cost else None
    for kind, n in extra.remove_counters if extra else ():
        plan.do({"type": "counter", "card_ids": [card.id], "kind": kind, "delta": -n}, actor=card.controller)
    for kind, n in ability.riders:
        if kind == "damage":
            plan.do({"type": "rules_damage", "creatures": {}, "players": {card.controller: n}, "planeswalkers": {},
                     "lifelink": {}, "combat": False,
                     "dealt": [{"source": plan.oid(card.id), "target": card.controller, "amount": n}]}, actor=card.controller)
        elif kind == "draw":
            plan.do({"type": "draw", "player": card.controller, "count": n}, actor=card.controller)


def pay(plan: Plan, player: str, cost: M.ManaCost, label: str, *, sources: list[str] | None = None,
        exclude: tuple[str, ...] = (), purpose: Purpose | None = None) -> None:
    if cost.is_free and not sources:
        return
    payment = find_payment(plan.state, player, cost, plan.info, sources=sources, exclude=exclude, purpose=purpose)
    extras: list[tuple[CardInstance, int, M.ManaAbility]] = []
    life = payment.life
    for cid, index in payment.used:
        card = plan.state.cards[cid]
        ability = dict(mana_abilities(plan.state, card, plan.info)).get(index)
        if ability is None:
            continue
        extras.append((card, index, ability))
        if ability.extra_cost:
            life += parse_ability_cost(ability.extra_cost, card_name=plan.ch(card).name).life
    plan.do({"type": "rules_mana", "player": player, "tap": payment.tapped, "sacrifice": payment.sacrificed,
             "delta": payment.delta(), "life": life, "label": label}, actor=player)
    for card, index, ability in extras:
        after_mana_ability(plan, card, index, ability)


def payment_step(plan: Plan, a: A.CastSpell | A.ActivateAbility, cost: M.ManaCost, what: str, *,
                 exclude: tuple[str, ...] = (), purpose: Purpose | None = None) -> bool:
    """Before a spell or ability is put on the stack: does the player want to see or choose the
    payment first? Returns True if a decision was opened (the intent then waits for it; nothing
    has moved yet, so CANCEL simply leaves everything where it was)."""
    if a.sources is not None or cost.is_free:
        return False
    mode = payment_mode(plan, plan.actor)
    if mode == "auto":
        return False
    payment = find_payment(plan.state, plan.actor, cost, plan.info, exclude=exclude, purpose=purpose)  # (can it be paid at all?)
    resume = {"step": "payment", "intent": a.model_dump(mode="json", exclude={"r", "actor", "ts"}),
              "exclude": list(exclude), "cost": cost.text(), "what": what}
    if mode == "manual":
        ask_sources(plan, cost, what, resume)
        return True
    names = [plan.state.cards[c].name or "a source" for c in payment.tapped]
    pool = sum(payment.spent.values()) - sum(payment.produced.values())
    if pool > 0:
        names.append(f"{pool} from your mana pool")
    resume["suggested"] = payment.tapped
    others = list(dict.fromkeys(s.card_id for s in mana_sources(plan.state, plan.actor, plan.info, purpose)
                                if s.card_id not in payment.tapped and s.card_id not in exclude))[:12]
    decide(plan, player=plan.actor, kind="choose_one",
           display={"kind": "payment", "cost": cost.text(), "what": what, "suggested": list(payment.tapped),
                    "alternatives": others, "pool": pool},
           prompt=f"Pay {cost.text()} for {what}. Suggested payment: {', '.join(names) or 'nothing'}",
           options=[DecisionOption(id="pay", label="Pay"), DecisionOption(id="manual", label="Manual"),
                    DecisionOption(id="cancel", label="Cancel")],
           resume=resume)
    return True


def ask_sources(plan: Plan, cost: M.ManaCost, what: str, resume: dict[str, Any]) -> None:
    exclude = tuple(resume.get("exclude") or ())
    sources = [s for s in mana_sources(plan.state, plan.actor, plan.info) if s.card_id not in exclude]
    options = [DecisionOption(id=s.card_id, label=plan.state.cards[s.card_id].name or "Source", card_id=s.card_id)
               for s in sources]
    decide(plan, player=plan.actor, kind="choose_cards",
           prompt=f"Choose the mana sources to pay {cost.text()} for {what} (your mana pool is used first)",
           options=options, min_choices=0, max_choices=max(len(options), 0),
           resume={**resume, "step": "payment_sources"})


def resume_payment(plan: Plan, d: Any, chosen: list[str]) -> None:
    """PAY (the suggestion), MANUAL (pick sources) or CANCEL."""
    assert d.resume is not None
    answer = chosen[0]
    if answer == "cancel":
        plan.note(f"{plan.name(d.player)} cancelled")
        plan.rules.priority = d.player
        plan.hold = d.player
        return
    intent = A.parse_action(d.resume["intent"])
    if answer == "manual":
        ask_sources(plan, M.parse_cost(d.resume["cost"]), d.resume["what"], d.resume)
        return
    _rerun(plan, d, intent, list(d.resume.get("suggested") or []))


def resume_payment_sources(plan: Plan, d: Any, chosen: list[str]) -> None:
    assert d.resume is not None
    _rerun(plan, d, A.parse_action(d.resume["intent"]), chosen)


def _rerun(plan: Plan, d: Any, intent: Any, sources: list[str]) -> None:
    from app.rules.engine import INTENTS  # the engine imports this module

    intent.sources = sources
    plan.rules.priority = d.player
    plan.rules.passed = []
    INTENTS[intent.type](plan, intent)


def can_pay(state: GameState, player: str, cost: M.ManaCost, info: CardInfo, *, exclude: tuple[str, ...] = (),
            purpose: Purpose | None = None) -> bool:
    everything = [s for s in mana_sources(state, player, info, purpose) if s.card_id not in exclude]
    try:
        _solve_with_filters(cost, dict(state.players[player].mana), [s for s in everything if s.activation is None],
                            [s for s in everything if s.activation is not None], state.players[player].life)
    except M.ManaError:
        return False
    return True


# -- casting ----------------------------------------------------------------------------
FLASHBACK = re.compile(r"^flashback (?P<cost>(?:\{[^}]+\})+)$", re.IGNORECASE)


def flashback_cost(ch: Characteristics) -> str | None:
    """702.34: the mana flashback cost printed on the card ("Flashback {2}{R}"), or None.
    Flashback with other costs ("Flashback—Sacrifice …") stays manual."""
    for ab in ch.abilities:
        if ab.kind == "keywords" and "flashback" in ab.keywords:
            m = FLASHBACK.fullmatch(ab.text.strip().rstrip("."))
            if m:
                return m["cost"]
    return None


def from_graveyard(card: CardInstance, player: str, ch: Characteristics) -> bool:
    """Casting with flashback: from your own graveyard, when it has a (mana) flashback cost."""
    return card.zone == zone_key(player, "graveyard") and card.owner == player and flashback_cost(ch) is not None


MORPH = re.compile(r"^(?P<kind>morph|megamorph) (?P<cost>(?:\{[^}]+\})+)$", re.IGNORECASE)
FACE_DOWN = Characteristics(name="", types=frozenset({"Creature"}), power="2", toughness="2", face_down=True)


def morph_cost(ch: Characteristics) -> tuple[str, str] | None:
    """702.37 morph / megamorph with a mana cost: (kind, cost), from the printed card."""
    for ab in ch.abilities:
        if ab.kind == "keywords" and ({"morph", "megamorph"} & set(ab.keywords)):
            m = MORPH.fullmatch(ab.text.strip().rstrip("."))
            if m:
                return m["kind"].lower(), m["cost"]
    return None


def turn_face_up(plan: Plan, a: A.TurnFaceUp) -> None:
    """702.37e: a special action any time you have priority (it doesn't use the stack)."""
    require_no_decision(plan)
    require_priority(plan)
    card = plan.state.cards.get(a.card_id)
    if card is None or card.controller != plan.actor or not card.zone.endswith(":battlefield") or not card.face_down:
        raise ActionError("Turn face up a face-down permanent you control")
    printed = chars.of(card.model_copy(update={"face_down": False}), plan.info)
    found = morph_cost(printed)
    if found is None:
        raise ActionError(f"{printed.name} has no morph cost: turn it face up with the table tools")
    kind, cost_text = found
    cost = M.parse_cost(cost_text)
    if not can_pay(plan.state, plan.actor, cost, plan.info, purpose=Purpose(ability_of=printed)):
        raise ActionError(f"Not enough mana to pay {cost.text()}")
    pay(plan, plan.actor, cost, f"paid {cost.text()} to turn {printed.name} face up", sources=a.sources,
        purpose=Purpose(ability_of=printed))
    plan.do({"type": "face_down", "card_ids": [card.id], "face_down": False})
    if kind == "megamorph":
        plan.do({"type": "counter", "card_ids": [card.id], "kind": "+1/+1", "delta": 1})
    emit(plan.state, "turned_face_up", object_id=plan.oid(card), card=card.id, player=plan.actor)
    plan.rules.passed = []


def from_command_zone(card: CardInstance, player: str) -> bool:
    return card.zone == zone_key(player, "command") and card.commander_key is not None and card.owner == player


def cast_problem(state: GameState, player: str, card: CardInstance, ch: Characteristics, *,
                 check_priority: bool = True) -> str | None:
    """Why ``player`` can't cast ``card`` right now (costs aside), or None."""
    r = state.rules
    if r is None:
        return "Rules automation is off"
    if not (card.zone == zone_key(player, "hand") or from_command_zone(card, player) or from_graveyard(card, player, ch)):
        return "You can cast spells from your hand, and your commander from the command zone"
    if ch.is_land:
        return f"{ch.name or 'That card'} is a land: play it instead"
    if not ch.types:
        return "Fyodor doesn't know what that card is. Use the table tools."
    if check_priority and (r.priority != player or r.decision is not None):
        return "You don't have priority"
    if "Instant" in ch.types or ch.has_flash:
        return None
    if state.turn.active_player != player:
        return f"{ch.name} can only be cast during your turn"
    if state.turn.phase not in MAIN_PHASES:
        return f"{ch.name} can only be cast in a main phase"
    if state.zones.get(STACK):
        return f"{ch.name} can only be cast while the stack is empty"
    return None


AFFINITY = re.compile(r"^affinity for (?P<what>[a-z ]+)$", re.IGNORECASE)
_AFFINITY_TYPES = {"artifacts": "Artifact", "creatures": "Creature", "enchantments": "Enchantment", "lands": "Land",
                   "planeswalkers": "Planeswalker"}
_AFFINITY_SUBTYPES = {"Plains", "Island", "Swamp", "Mountain", "Forest", "Equipment", "Gate", "Town", "Food", "Clue",
                      "Treasure", "Vehicle", "Aura"}


def affinity_filter(ch: Characteristics) -> Any:
    """702.41 "Affinity for X": a predicate on permanents, or None (no affinity / a wording we don't know)."""
    for ab in ch.abilities:
        if ab.kind != "keywords" or "affinity" not in ab.keywords:
            continue
        m = AFFINITY.fullmatch(ab.text.strip().rstrip("."))
        if not m:
            return None
        what = m["what"].lower()
        if what in _AFFINITY_TYPES:
            t = _AFFINITY_TYPES[what]
            return lambda c: t in c.types
        if what == "artifact creatures":
            return lambda c: "Artifact" in c.types and c.is_creature
        from app.rules.creature_types import CREATURE_TYPES
        from app.rules.protection import _PLURALS

        sub = _PLURALS.get(what) or (what[:-1] if what.endswith("s") and what != "plains" else what).title()
        if sub in CREATURE_TYPES or sub in _AFFINITY_SUBTYPES:
            return lambda c: sub in c.subtypes
        return None
    return None


def affinity_discount(state: GameState, player: str, ch: Characteristics, info: CardInfo) -> int:
    pred = affinity_filter(ch)
    if pred is None:
        return 0
    from app.rules.layers import derive

    return sum(1 for c in state.cards.values() if c.zone == zone_key(player, "battlefield") and c.controller == player
               and pred(derive(state, c, chars.of(c, info), info)))


def spell_cost(state: GameState, card: CardInstance, ch: Characteristics, x: int = 0,
               info: CardInfo | None = None) -> M.ManaCost:
    flashback = flashback_cost(ch) if card.zone == zone_key(card.owner, "graveyard") else None
    cost = M.parse_cost(flashback or ch.mana_cost).with_x(x)
    if info is not None:  # cost reductions reduce only the generic part (601.2f)
        cost = cost.plus_generic(-min(cost.generic, affinity_discount(state, card.owner, ch, info)))
    if from_command_zone(card, card.owner) and card.commander_key:
        cost = cost.plus_generic(state.players[card.owner].commander_tax.get(card.commander_key, 0))
    return cost


def castable(state: GameState, player: str, card: CardInstance, info: CardInfo, *, check_priority: bool = True) -> bool:
    faces = (0, 1) if chars.is_two_spell_card(card, info) else (None,)
    for face in faces:
        ch = chars.as_cast(card, info, face)
        if cast_problem(state, player, card, ch, check_priority=check_priority) is None and \
                can_pay(state, player, spell_cost(state, card, ch, info=info), info, purpose=Purpose(spell=ch)):
            return True
    return False


def cast_spell(plan: Plan, a: A.CastSpell) -> None:
    from app.rules.engine import advance  # the engine imports this module

    require_no_decision(plan)
    card = plan.state.cards.get(a.card_id)
    if card is None:
        raise ActionError("That card isn't here any more")
    ch = chars.as_cast(card, plan.info, a.face)  # split cards / adventures: the half being cast
    if a.face_down:  # morph: a nameless 2/2 creature spell for {3}
        if morph_cost(ch) is None or card.zone != zone_key(plan.actor, "hand"):
            raise ActionError("Only a card with morph can be cast face down from your hand")
        ch = FACE_DOWN
    problem = cast_problem(plan.state, plan.actor, card, ch)
    if problem:
        raise ActionError(problem)
    base = M.parse_cost(ch.mana_cost)
    if base.x and a.x_value is None:
        raise ActionError(f"Choose a value for X to cast {ch.name}")
    cost = M.parse_cost("{3}") if a.face_down else spell_cost(plan.state, card, ch, a.x_value or 0, plan.info)
    for target in a.targets:
        if target not in plan.state.cards and target not in plan.state.players:
            raise ActionError("A chosen target isn't on the table")
    definition = None if plan.manual(card) or a.face_down else scripts.spell_definition(ch)
    chosen = choose_target(plan, a, definition, ch.name or "it")
    if chosen is None:
        return  # waiting for the target choice (601.2c comes before paying costs)
    if payment_step(plan, a, cost, ch.name or "it", purpose=Purpose(spell=ch)):
        return
    commander_cast = from_command_zone(card, plan.actor)
    flashback = from_graveyard(card, plan.actor, ch)
    if a.face is not None and a.face != card.face:
        plan.do({"type": "set_face", "card_id": card.id, "face": a.face})
    if a.face_down:
        plan.do({"type": "move", "card_ids": [card.id], "to": {"zone": "stack"}, "face_down": True, "face_down_kind": "morph"})
    else:
        plan.do({"type": "move", "card_ids": [card.id], "to": {"zone": "stack"}})
    if commander_cast and not plan.state.settings.auto_commander_tax and card.commander_key:
        plan.do({"type": "commander_tax", "commander": card.commander_key, "delta": 2})
    pay(plan, plan.actor, cost, f"paid {cost.text()} for {ch.name or 'a face-down spell'}", sources=a.sources,
        purpose=Purpose(spell=ch))
    tags = ["Cast from the command zone"] if commander_cast else ["Flashback"] if flashback else []
    if flashback:
        plan.rules.flashback.append(plan.oid(card))  # 702.34a: exiled instead of going anywhere else
    if a.x_value is not None or tags:
        info: dict[str, Any] = {"type": "set_stack_info", "card_id": card.id}
        if a.x_value is not None:
            info["x"] = a.x_value
        if tags:
            info["tags"] = tags
        plan.do(info)
    if a.targets:
        plan.do({"type": "create_arrow", "source": card.id, "targets": list(a.targets), "kind": "target"})
    r = plan.rules
    emit(plan.state, "spell_cast", object_id=plan.oid(card), card=card.id, player=plan.actor)  # for "whenever you cast"
    if definition is not None:
        r.stack[card.id] = StackEntry(kind="spell", controller=plan.actor, source_card=card.id, source_object=plan.oid(card),
                                      name=ch.name, effects=list(definition["effects"]), targets=chosen,
                                      target_spec=definition.get("target"), x=a.x_value)
    turn = plan.state.turn.number
    r.spells_cast[plan.actor] = TurnCount(turn=turn, count=r.spells_this_turn(plan.actor, turn) + 1)
    r.passed = []
    r.priority = plan.actor
    if r.prefs_for(plan.actor).hold_priority:
        plan.hold = plan.actor
        return  # HOLD PRIORITY: you keep it, whatever your RESPONSE setting says
    r.passed.append(plan.actor)  # Arena-style: you pass after casting unless you hold priority
    r.priority = plan.after(plan.actor)
    advance(plan)


# -- mana abilities ---------------------------------------------------------------------
def _find_ability(ch: Characteristics, index: int) -> AbilityText:
    ability = next((ab for ab in ch.abilities if ab.index == index), None)
    if ability is None:
        raise ActionError(f"{ch.name or 'That card'} has no such ability")
    return ability


CYCLING = re.compile(r"^(?P<kind>(?:basic )?(?:[a-z]+)?)cycling (?P<cost>(\{[^}]+\})+)$", re.IGNORECASE)


def hand_ability(ch: Characteristics, index: int) -> tuple[str, str] | None:
    """A cycling keyword on ability line ``index``: (kind, mana cost). kind "" = plain cycling,
    "basic land" / "Swamp" / "Wizard" … = typecycling (search for that card)."""
    for ab in ch.abilities:
        if ab.index != index or ab.kind != "keywords":
            continue
        m = CYCLING.fullmatch(ab.text.strip().rstrip("."))
        if m:
            kind = m["kind"].strip()
            return (kind if kind.lower() != "basic land" else "basic land"), m["cost"]
    return None


def cycle(plan: Plan, card: CardInstance, ch: Characteristics, a: A.ActivateAbility) -> None:
    """Cycling (702.29): pay the cost and discard this card from your hand, then the ability on
    the stack draws a card; typecycling searches your library for a card of that type instead."""
    found = hand_ability(ch, a.ability)
    if found is None:
        raise ActionError("That card has no ability to use from your hand")
    kind, mana_text = found
    mana = M.parse_cost(mana_text)
    if payment_step(plan, a, mana, f"cycling {ch.name}", purpose=Purpose(ability_of=ch)):
        return
    if kind:
        filt = "basic_land" if kind == "basic land" else f"type:{kind[0].upper()}{kind[1:].lower()}"
        effects = [{"do": "search", "who": "you", "filter": filt, "to": "hand", "reveal": True}]
        text = f"Search your library for a {kind} card, reveal it, put it into your hand, then shuffle."
    else:
        effects = [{"do": "draw", "who": "you", "n": 1}]
        text = "Draw a card."
    oid = plan.oid(card)
    ability_id = _new_ability(plan, card, text)
    pay(plan, plan.actor, mana, f"paid {mana.text()} to cycle {ch.name}", sources=a.sources, purpose=Purpose(ability_of=ch))
    plan.do({"type": "move", "card_ids": [card.id], "to": {"player": card.owner, "zone": "graveyard"}})
    emit(plan.state, "cycled", object_id=oid, card=card.id, player=plan.actor)
    _stacked(plan, card, oid, ch, ability_id, effects)


def _new_ability(plan: Plan, card: CardInstance, text: str) -> str | None:
    created = plan.do({"type": "create_ability", "text": text[:500], "source_id": card.id, "kind": "activated"})
    new_ids = getattr(created, "r", None)
    return new_ids.ids[0] if new_ids is not None else None


def _stacked(plan: Plan, card: CardInstance, oid: str, ch: Characteristics, ability_id: str | None,
             effects: list[dict[str, Any]]) -> None:
    """An activated ability is on the stack: record what it does, then pass priority Arena-style."""
    from app.rules.engine import advance  # the engine imports this module

    r = plan.rules
    if ability_id:
        r.stack[ability_id] = StackEntry(kind="activated", controller=plan.actor, source_card=card.id, source_object=oid,
                                         name=ch.name, effects=effects, targets=[], target_spec=None)
    r.passed = []
    r.priority = plan.actor
    if r.prefs_for(plan.actor).hold_priority:
        plan.hold = plan.actor
        return
    r.passed.append(plan.actor)
    r.priority = plan.after(plan.actor)
    advance(plan)


CREW = re.compile(r"^crew (?P<n>\d+)$", re.IGNORECASE)


def crew_power(ch: Characteristics, index: int) -> int | None:
    """Crew N (702.122) on ability line ``index``: N, or None."""
    for ab in ch.abilities:
        if ab.index == index and ab.kind == "keywords":
            m = CREW.fullmatch(ab.text.strip().rstrip("."))
            if m:
                return int(m["n"])
    return None


def crew(plan: Plan, card: CardInstance, ch: Characteristics, a: A.ActivateAbility, n: int) -> None:
    """Crew N: tap any number of untapped creatures you control with total power N or greater:
    this Vehicle becomes an artifact creature until end of turn. (Summoning-sick creatures may crew.)"""
    from app.rules.combat import power

    def crew_power_of(cid: str) -> int:
        c = plan.state.cards[cid]
        return max(0, power(c, plan.ch(c)) or 0)

    candidates = [c.id for c in plan.state.cards.values() if c.zone == card.zone and c.controller == plan.actor
                  and c.id != card.id and not c.tapped and plan.in_game(c) and plan.ch(c).is_creature]
    if sum(crew_power_of(c) for c in candidates) < n:
        raise ActionError(f"{ch.name}: you don't control untapped creatures with total power {n} or greater")
    if a.crew is None:
        decide(plan, player=plan.actor, kind="choose_cards", prompt=f"Crew {n}: tap creatures with total power {n} or greater",
               options=[DecisionOption(id=c, label=f"{plan.state.cards[c].name} ({crew_power_of(c)})", card_id=c)
                        for c in candidates],
               min_choices=1, max_choices=len(candidates),
               resume={"step": "crew", "intent": a.model_dump(mode="json", exclude={"r", "actor", "ts"})}, source=card)
        return
    chosen = list(dict.fromkeys(a.crew))
    if not chosen or any(c not in candidates for c in chosen):
        raise ActionError("Crew with untapped creatures you control")
    if sum(crew_power_of(c) for c in chosen) < n:
        raise ActionError(f"Those creatures have less than {n} total power")
    oid = plan.oid(card)
    ability_id = _new_ability(plan, card, f"{ch.name} becomes an artifact creature until end of turn.")
    plan.do({"type": "tap", "card_ids": chosen, "tapped": True})
    emit(plan.state, "crewed", object_id=oid, card=card.id, player=plan.actor)
    _stacked(plan, card, oid, ch, ability_id, [{"do": "animate", "who": "self", "types": ["Artifact", "Creature"], "crewed": True}])


def resume_crew(plan: Plan, d: Any, chosen: list[str]) -> None:
    intent = A.parse_action(d.resume["intent"])
    intent.crew = list(chosen)  # type: ignore[union-attr]
    plan.rules.priority = d.player
    activate_ability(plan, intent)  # type: ignore[arg-type]


def activate_ability(plan: Plan, a: A.ActivateAbility) -> None:
    require_no_decision(plan)
    require_priority(plan)
    card = plan.state.cards.get(a.card_id)
    if card is None:
        raise ActionError("That card isn't here any more")
    if card.zone == zone_key(plan.actor, "hand"):
        cycle(plan, card, plan.ch(card), a)
        return
    if card.controller != plan.actor or not card.zone.endswith(":battlefield"):
        raise ActionError("You can only activate abilities of permanents you control")
    ch = plan.ch(card)
    ability = _find_ability(ch, a.ability)
    n = crew_power(ch, a.ability) if not plan.manual(card) else None
    if n is not None:
        crew(plan, card, ch, a, n)
        return
    if ability.kind in ("activated", "loyalty"):
        activate_to_stack(plan, card, ch, ability, a)
        return
    if ability.kind != "mana":
        raise ActionError(f"“{ability.text}” isn't an ability you activate")
    parsed = dict(mana_abilities(plan.state, card, plan.info)).get(a.ability)
    if parsed is None:
        if M.parse_mana_ability(ability.text, commander_identity(plan.state, card.controller, plan.info)) is not None:
            raise ActionError(f"{ch.name} can't use “{ability.text}” right now")
        raise ActionError(f"Fyodor can't carry out “{ability.text}” yet. Use the table tools.")
    if parsed.spend_only is not None:
        raise ActionError(f"{ch.name}’s mana can only pay for certain things: Fyodor taps it when you cast or activate them")
    if parsed.tap and not can_use_tap_abilities(plan.state, card, ch):
        raise ActionError(f"{ch.name} is tapped" if card.tapped else f"{ch.name} has summoning sickness")
    options = parsed.options
    if len(options) == 1:
        produce(plan, card, parsed, options[0], a.ability)
    elif a.mana_choice is not None:
        chosen = next((o for o in options if o == (a.mana_choice,)), None)
        if chosen is None:
            raise ActionError(f"{ch.name} can't add {{{a.mana_choice}}}")
        produce(plan, card, parsed, chosen, a.ability)
    else:
        decide(plan, player=plan.actor, kind="choose_one", prompt=f"Which mana should {ch.name} add?",
               options=[DecisionOption(id=str(i), label=M.symbols(_count(o))) for i, o in enumerate(options)],
               resume={"step": "mana_ability", "card": card.id, "ability": a.ability}, source=card)
        return
    plan.rules.passed = []


# -- other activated abilities (they use the stack) -----------------------------------------
def ability_cost(ch: Characteristics, ability: AbilityText) -> AbilityCost:
    return parse_ability_cost(ability.cost or "", card_name=ch.name, loyalty=ability.kind == "loyalty")


def ability_problem(state: GameState, player: str, card: CardInstance, ch: Characteristics, ability: AbilityText,
                    cost: AbilityCost, *, check_priority: bool = True, x: int = 0,
                    info: CardInfo | None = None) -> str | None:
    """Why ``player`` can't activate this ability now (None if they can, costs included when
    ``info`` is given)."""
    r = state.rules
    if r is None:
        return "Rules automation is off"
    if card.controller != player or not card.zone.endswith(":battlefield"):
        return "You can only activate abilities of permanents you control"
    if cost.unsupported:
        return f"Pay “{', '.join(cost.unsupported)}” by hand with the table tools"
    if check_priority and (r.priority != player or r.decision is not None):
        return "You don't have priority"
    sorcery = ability.kind == "loyalty" or "Activate only as a sorcery" in ability.text
    if sorcery and (state.turn.active_player != player or state.turn.phase not in MAIN_PHASES or state.zones.get(STACK)):
        return "That can only be activated in your main phase while the stack is empty"
    if ability.kind == "loyalty":
        if r.loyalty_used.get(r.object_id(card.id)) == state.turn.number:
            return f"{ch.name} has already used a loyalty ability this turn"
        if cost.loyalty is not None and cost.loyalty < 0 and card.counters.get("loyalty", 0) < -cost.loyalty:
            return f"{ch.name} doesn't have enough loyalty"
    once_key = f"{r.object_id(card.id)}:{ability.index}"  # per object: a flickered permanent is a new one
    if "Activate only once each turn" in ability.text and r.once_per_turn.get(once_key) == state.turn.number:
        return "That can only be activated once each turn"
    if cost.tap and not can_use_tap_abilities(state, card, ch):
        return f"{ch.name} is tapped" if card.tapped else f"{ch.name} has summoning sickness"
    for kind, n in cost.remove_counters:
        if card.counters.get(kind, 0) < n:
            return f"{ch.name} doesn't have {n} {kind} counter{'s' if n != 1 else ''}"
    if cost.life and state.players[player].life < cost.life:
        return f"You don't have {cost.life} life to pay"
    if info is not None and cost.mana:
        mana = M.parse_cost(cost.mana).with_x(x)
        if not can_pay(state, player, mana, info, exclude=(card.id,) if cost.tap else (), purpose=Purpose(ability_of=ch)):
            return f"Not enough mana to pay {mana.text()}"
    return None


def activate_to_stack(plan: Plan, card: CardInstance, ch: Characteristics, ability: AbilityText,
                      a: A.ActivateAbility) -> None:
    from app.rules.engine import advance  # the engine imports this module

    cost = ability_cost(ch, ability)
    problem = ability_problem(plan.state, plan.actor, card, ch, ability, cost)
    if problem:
        raise ActionError(problem)
    oid = plan.oid(card)  # the object activating (paying a cost may move it: it'd be a new object)
    mana = M.parse_cost(cost.mana)
    if mana.x and a.x_value is None:
        raise ActionError("Choose a value for X")
    definition = None if plan.manual(card) else scripts.definitions(ch).get(ability.index)
    if definition is not None and definition["kind"] != "activated":
        definition = None
    chosen = choose_target(plan, a, definition, f"{ch.name}’s ability")
    if chosen is None:
        return
    if payment_step(plan, a, mana.with_x(a.x_value or 0), f"{ch.name}’s ability",
                    exclude=(card.id,) if cost.tap else (), purpose=Purpose(ability_of=ch)):
        return
    effect = ability.text.split(":", 1)[1].strip() if ":" in ability.text else ability.text
    created = plan.do({"type": "create_ability", "text": effect[:500], "source_id": card.id, "kind": "activated"})
    new_ids = getattr(created, "r", None)
    ability_id = new_ids.ids[0] if new_ids is not None else None
    # Pay the costs (602.2): tap first so the source can't also pay for its own mana cost.
    if cost.tap:
        plan.do({"type": "tap", "card_ids": [card.id], "tapped": True})
    if cost.loyalty:
        plan.do({"type": "counter", "card_ids": [card.id], "kind": "loyalty", "delta": cost.loyalty})
    for kind, n in cost.remove_counters:
        plan.do({"type": "counter", "card_ids": [card.id], "kind": kind, "delta": -n})
    if cost.life:
        plan.do({"type": "life", "player": plan.actor, "delta": -cost.life})
    pay(plan, plan.actor, mana.with_x(a.x_value or 0), f"paid {mana.with_x(a.x_value or 0).text()} to activate {ch.name}",
        sources=a.sources, exclude=(card.id,) if cost.tap else (), purpose=Purpose(ability_of=ch))
    if cost.sacrifice_self:
        plan.do({"type": "move", "card_ids": [card.id], "to": {"player": card.owner, "zone": "graveyard"}})
    if a.x_value is not None and ability_id:
        plan.do({"type": "set_stack_info", "card_id": ability_id, "x": a.x_value})
    if a.targets and ability_id:
        plan.do({"type": "create_arrow", "source": ability_id, "targets": list(a.targets), "kind": "target"})
    r = plan.rules
    if definition is not None and ability_id:
        r.stack[ability_id] = StackEntry(kind="activated", controller=plan.actor, source_card=card.id, source_object=oid,
                                         name=ch.name, effects=list(definition["effects"]), targets=chosen,
                                         target_spec=definition.get("target"), x=a.x_value)
    if ability.kind == "loyalty":
        r.loyalty_used[oid] = plan.state.turn.number
    if "Activate only once each turn" in ability.text:
        r.once_per_turn[f"{oid}:{ability.index}"] = plan.state.turn.number
    r.passed = []
    r.priority = plan.actor
    if r.prefs_for(plan.actor).hold_priority:
        plan.hold = plan.actor
        return
    r.passed.append(plan.actor)
    r.priority = plan.after(plan.actor)
    advance(plan)


def activatable(state: GameState, player: str, info: CardInfo, *, check_priority: bool = True) -> list[dict[str, Any]]:
    """Abilities of ``player``'s permanents that could be activated right now (for hints)."""
    out: list[dict[str, Any]] = []
    for cid in state.zones.get(zone_key(player, "battlefield"), []):
        card = state.cards[cid]
        if card.controller != player:
            continue
        ch = chars.of(card, info)
        for ab in ch.abilities:
            if ab.kind in ("activated", "loyalty"):
                problem = ability_problem(state, player, card, ch, ab, ability_cost(ch, ab),
                                          check_priority=check_priority, info=info)
                if problem is None:
                    out.append({"card_id": cid, "ability": ab.index})
            elif ab.kind == "keywords" and _can_crew(state, player, card, ch, ab.index, info, check_priority):
                out.append({"card_id": cid, "ability": ab.index})
    return out


def _can_crew(state: GameState, player: str, card: CardInstance, ch: Characteristics, index: int, info: CardInfo,
              check_priority: bool) -> bool:
    n = crew_power(ch, index)
    r = state.rules
    if n is None or r is None or (check_priority and (r.priority != player or r.decision is not None)):
        return False
    from app.rules.combat import power
    from app.rules.layers import derive

    total = 0
    for c in state.cards.values():
        if c.zone == card.zone and c.controller == player and c.id != card.id and not c.tapped:
            cch = derive(state, c, chars.of(c, info), info)
            if cch.is_creature:
                total += max(0, power(c, cch) or 0)
    return total >= n


def _count(option: tuple[str, ...]) -> dict[str, int]:
    out: dict[str, int] = {}
    for m in option:
        out[m] = out.get(m, 0) + 1
    return out


def produce(plan: Plan, card: CardInstance, ability: M.ManaAbility, option: tuple[str, ...], index: int | None = None) -> None:
    """Activate a mana ability by hand: pay its other costs (mana from the pool or other sources,
    life, counters), add the mana, then its riders."""
    extra = parse_ability_cost(ability.extra_cost, card_name=plan.ch(card).name) if ability.extra_cost else None
    if extra is not None and extra.mana:
        pay(plan, card.controller, M.parse_cost(extra.mana), f"paid {extra.mana} to activate {plan.ch(card).name}",
            exclude=(card.id,))
    mana = _count(option)
    plan.do({"type": "rules_mana", "player": card.controller, "tap": [card.id] if ability.tap else [],
             "sacrifice": [card.id] if ability.sacrifice_self else [], "delta": mana,
             "life": extra.life if extra else 0, "label": f"added {M.symbols(mana)}"}, actor=card.controller)
    if index is not None:
        after_mana_ability(plan, card, index, ability)


def resume_mana_ability(plan: Plan, d: Any, chosen: list[str]) -> None:
    card = plan.state.cards.get(d.resume["card"])
    if card is None:
        return
    index = int(d.resume["ability"])
    parsed = dict(mana_abilities(plan.state, card, plan.info)).get(index)
    if parsed is None or (parsed.tap and not can_use_tap_abilities(plan.state, card, plan.ch(card))):
        raise ActionError("That mana ability can't be activated any more")
    produce(plan, card, parsed, parsed.options[int(chosen[0])], index)
    plan.rules.priority = plan.actor
    plan.rules.passed = []


# -- responding -------------------------------------------------------------------------
def has_responses(state: GameState, player: str, info: CardInfo) -> bool:
    """Could ``player`` do anything at instant speed right now? (For Arena-style auto-passing.)"""
    for key in (zone_key(player, "hand"), zone_key(player, "command"), zone_key(player, "graveyard")):
        for cid in state.zones.get(key, []):
            card = state.cards[cid]
            ch = chars.of(card, info)
            if ("Instant" in ch.types or ch.has_flash) and castable(state, player, card, info, check_priority=False):
                return True
    return bool(activatable(state, player, info, check_priority=False))


def can_act(state: GameState, player: str, info: CardInfo) -> bool:
    """Could ``player`` do anything at all right now (a land, a spell, an ability)?"""
    from app.rules.engine import land_play_problem  # engine imports this module

    for key in (zone_key(player, "hand"), zone_key(player, "command"), zone_key(player, "graveyard")):
        for cid in state.zones.get(key, []):
            card = state.cards[cid]
            if castable(state, player, card, info, check_priority=False):
                return True
            if key.endswith(":hand") and land_play_problem(state, player, card, chars.of(card, info), check_priority=False) is None:
                return True
    return bool(activatable(state, player, info, check_priority=False))

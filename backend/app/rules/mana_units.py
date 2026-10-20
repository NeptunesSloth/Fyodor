"""Mana that remembers where it came from (wave 18B), researched against CR 2026-09-25.

106.3: the source of mana is the permanent, spell or ability that produced it. 106.6: an ability that produces mana may restrict how it
can be spent, give the spell or ability it is spent on an additional effect, or create a delayed trigger for when it is spent; none of
that changes the mana's type. 106.6a: a replacement that adds mana applies the restriction to all of it. 107.4h: {S} is paid with one
mana of any type produced by a snow source. 106.12: "tap for mana" means a mana ability with {T} in its cost.

The plain pool (``PlayerState.mana``) holds mana with an unknown origin, such as
mana added by table tools or loaded from older saves. Every mana produced by a
known source is a ``ManaUnit`` carrying its exact rules object ID, source traits,
spending restrictions, and riders. Remembering only currently special sources
would lose valid history: an ordinary land can become a copy of Tecutlan or The
Myriad Pools without changing object identity (201.5, 707.4).

Unrestricted units appear as ordinary pooled mana to players. The solver spends
them as pool pseudo-sources; ``settle`` records only sources of mana actually
spent. Unspent units keep their original source and traits through copying,
transformation, and mana-preserving effects."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from app.game.errors import ActionError
from app.rules import mana as M
from app.rules.mana_requirement_rows import ProducerFact

if TYPE_CHECKING:
    from app.game.state import GameState
    from app.rules.casting import Purpose
    from app.rules.characteristics import Characteristics
    from app.rules.plan import Plan

PREFIX = "unit:"


def visible_pool(state: GameState, player: str) -> dict[str, int]:
    """Unrestricted, riderless mana displayed as ordinary pooled mana to players."""
    p = state.players[player]
    pool = dict(p.mana)
    for unit in p.mana_units:
        if not unit.only and not unit.riders and unit.generic_allowed:
            pool[unit.sym] = pool.get(unit.sym, 0) + 1
    return pool


# Sources whose mana a rule asks about later: snow ({S}, 107.4h), Treasures, "mana from an artifact / a creature / a Desert / a Cave".
INTERESTING = frozenset({"Snow", "Treasure", "Artifact", "Creature", "Desert", "Cave"})
# A game remembers the source of plain mana only if one of its cards asks (so a table without such cards keeps its one plain pool).
ASKS = re.compile(r"\{S\}|\bmana (?:from|produced by|of a snow)\b|\bsnow (?:mana|source)", re.IGNORECASE)


def tracking(plan: Plan) -> bool:
    """Does any card of this game ask where mana came from ("mana from a Treasure was spent", {S}, "mana produced by creatures")?"""
    from app.rules import characteristics as chars

    r = plan.rules
    if r.provenance is None:
        r.provenance = any(ASKS.search(chars.of(c, plan.info).oracle_text) for c in plan.state.cards.values())
    return r.provenance


def tags_of(ch: Characteristics) -> list[str]:
    """What a source was when it produced mana: its supertypes, types and subtypes (last known information, 608.2h)."""
    return sorted(ch.supertypes | ch.types | ch.subtypes)


def needs_unit(plan: Plan, only: str | None, riders: list[dict[str, Any]] | tuple[Any, ...], tags: list[str]) -> bool:
    """Does mana with this restriction, these riders and this source have to be remembered?"""
    # CR 201.5 / 400.7: an ordinary land can become a copy of a source whose
    # later cast trigger asks about mana it produced earlier, without changing
    # object identity. Retain every known source, not only currently interesting
    # printed types or abilities. Player views still fold plain units together.
    return True


def unit_sources(state: GameState, player: str, purpose: Purpose | None) -> list[M.Source]:
    """The player's pool units that may pay for ``purpose`` (a spending restriction is checked as for a source), as pseudo-sources
    that are already 'tapped': used first (rank -1), each producing its one mana; a snow unit pays {S}."""
    from app.rules.casting import spend_allowed

    return [M.Source(f"{PREFIX}{u.id}", ((u.sym,),), rank=-1, snow="Snow" in u.tags,
                     generic_allowed=(False,) if not u.generic_allowed else (),
                     producer_facts=((ProducerFact(tuple(u.tags), u.production_zone),),))
            for u in state.players[player].mana_units if spend_allowed(u.only, purpose)]


@dataclass
class Slot:
    """One mana of a payment: a unit of the pool, or one a tapped source produced."""

    sym: str
    tags: list[str]
    only: str | None
    riders: list[dict[str, Any]]
    src: str
    unit: int | None = None
    note: str = ""
    generic_allowed: bool = True
    production_zone: str | None = None


def settle(plan: Plan, player: str, payment: M.Payment) -> dict[str, Any]:
    """The ``rules_mana`` fields (net plain ``delta``, units spent and added) for a solved payment, and on ``payment`` the provenance of
    the mana spent (``tags``: one tag list per mana with a known source; ``riders``: the riders of the mana spent). Units are spent
    first, then what the tapped sources produced; the rest of the cost comes from the plain pool; what a source produced and wasn't
    needed stays (restricted / remembered mana as a unit, plain mana as a plain count)."""
    from app.rules.casting import mana_abilities

    state = plan.state
    units = {u.id: u for u in state.players[player].mana_units}
    used = dict(payment.used)
    ability_options = dict(payment.ability_options)
    slots: list[Slot] = []
    for cid, opt in payment.slots:
        if cid.startswith(PREFIX):
            u = units[int(cid[len(PREFIX):])]
            slots.append(Slot(u.sym, list(u.tags), u.only, list(u.riders), u.src, unit=u.id, note=u.note,
                              generic_allowed=u.generic_allowed, production_zone=u.production_zone))
            continue
        card = state.cards[cid]
        ab = dict(mana_abilities(state, card, plan.info)).get(used.get(cid, -1))
        only = ab.spend_only if ab else None
        riders = rider_specs(ab, plan.ch(card).name)
        tags = tags_of(plan.ch(card))
        if ab is None or ab.output_producers is None:
            raise ActionError('This saved mana ability has unknown producer choices; resolve it manually with the table tools')
        if ab is not None and ab.output_producers:
            if cid not in ability_options:
                raise ActionError('This saved mana ability has unknown option history; resolve it manually with the table tools')
            profile = ab.output_producers[ability_options[cid]]
        else:
            profile = (None,) * len(opt)
        for m, spec in zip(opt, profile, strict=True):
            if spec is None:
                slots.append(Slot(m, tags, only, riders, plan.oid(card), note=ab.spend_text if ab else "",
                    generic_allowed=ab.generic_allowed if ab else True, production_zone=card.zone))
            else:
                slots.append(Slot(m, list(spec.producer.tags) if spec.producer else [], None, [], spec.source_object,
                    production_zone=spec.producer.zone if spec.producer else None))
    producer_receipt = any(row.unit.producer is not None for row in payment.allocation or ())
    delta: dict[str, int] = {}
    spend: list[int] = []
    add: list[dict[str, Any]] = []
    for sym in sorted({*payment.spent, *(s.sym for s in slots)}):  # (review 18B: sorted — a set's order changes between processes)
        n = payment.spent.get(sym, 0)
        mine = sorted((s for s in slots if s.sym == sym), key=lambda s: s.unit is None)  # (units first)
        taken, left = mine[:n], mine[n:]
        if payment.allocation is not None:
            from app.rules.mana_requirement_rows import UnitClass

            taken, left = [], list(mine)
            for row in (r for r in payment.allocation if r.unit.sym == sym):
                matching = [s for s in left if UnitClass(s.sym, s.generic_allowed, 'Snow' in s.tags,
                    ProducerFact(tuple(s.tags), s.production_zone) if producer_receipt else None) == row.unit]
                selected = matching[:row.amount]
                if len(selected) < row.amount and row.unit != UnitClass(sym):
                    raise M.ManaError('The payment has no matching actual mana units')
                taken.extend(selected)
                for slot in selected:
                    left.remove(slot)
        payment.snow_spent[sym] = payment.snow_spent.get(sym, 0) + sum('Snow' in s.tags for s in taken)
        payment.tags += [s.tags for s in taken if s.tags]
        payment.sources += [s.src for s in taken if s.src]
        payment.riders += [(s.src, r) for s in taken for r in s.riders]
        spend += [s.unit for s in taken if s.unit is not None]
        if n > len(taken):
            delta[sym] = delta.get(sym, 0) - (n - len(taken))  # the rest came from the plain pool
        for s in left:
            if s.unit is not None:
                continue
            if needs_unit(plan, s.only, s.riders, s.tags):
                add.append({"sym": s.sym, "src": s.src, "tags": s.tags, "only": s.only, "riders": s.riders, "note": s.note,
                            "generic_allowed": s.generic_allowed, "production_zone": s.production_zone})
            else:
                delta[sym] = delta.get(sym, 0) + 1
    return {"delta": {k: v for k, v in delta.items() if v}, "spend_units": spend, "add_units": add}


def rider_specs(ability: Any, name: str = "") -> list[dict[str, Any]]:
    """The riders of a mana ability ("when that mana is spent …"), as the dicts units keep (``name``: its source, for the log)."""
    import json

    scope = getattr(ability, 'borrowed_link_scope', None)
    return [{**json.loads(r), "name": name, **({'borrowed_link_scope': scope} if scope is not None else {})}
            for r in getattr(ability, "on_spend", ())]


def restrict(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """"Spend this mana only to cast …" / "This mana can't be spent to …" after an instruction that added mana (106.6, 106.6a: all
    of it): the mana it just added (``ctx["_mana_added"]``, a plain count in the pool) becomes units that carry the restriction.
    ``ctx["_mana_unit_ids"]`` names them for "you don't lose this mana" (kept_mana)."""
    added_: dict[str, int] = ctx.pop("_mana_added", None) or {}
    pid = ctx["controller"]
    if not added_:
        return True
    card = plan.state.cards.get(ctx.get("source_card") or "")
    tags = tags_of(plan.ch(card)) if card is not None else []
    src = ctx.get("source_object") or (plan.oid(card) if card is not None else "")
    before = {u.id for u in plan.state.players[pid].mana_units}
    prior_units = [u for u in plan.state.players[pid].mana_units if u.id in ctx.get("_mana_unit_ids", [])]
    prior = [u.id for u in prior_units]
    converted = [{**u.model_dump(exclude={'id'}), 'only': e['only'], 'riders': list(e.get('riders') or []),
                  'note': e.get('note', '')} for u in prior_units] if prior else [
        {'sym': s, 'src': src, 'tags': tags, 'only': e['only'], 'riders': list(e.get('riders') or []),
         'note': e.get('note', ''), 'generic_allowed': ctx.get('generic_allowed', True),
         'production_zone': card.zone if card is not None and plan.oid(card) == src else None}
        for s, n in added_.items() for _ in range(n)]
    plan.do({"type": "rules_mana", "player": pid, "tap": [], "sacrifice": [], "life": 0, "label": "",
             **({"spend_units": prior} if prior else {"delta": {s: -n for s, n in added_.items()}}),
             "add_units": converted}, actor=pid)
    ctx["_mana_unit_ids"] = [u.id for u in plan.state.players[pid].mana_units if u.id not in before]
    if '_mana_pool_added' in ctx:
        ctx['_mana_pool_added'] = {}  # The completed restriction conversion now represents this output entirely as units.
    return True


def added(plan: Plan, card: Any, ability: Any, mana: dict[str, int], *, option: tuple[str, ...] | None = None, option_index: int | None = None) -> dict[str, Any]:
    """The ``rules_mana`` fields that add the mana a source's mana ability produced (106.3): a plain count, or units when it is
    restricted, carries riders or comes from a source later rules ask about (see the module docstring)."""
    tags = tags_of(plan.ch(card))
    riders = rider_specs(ability, plan.ch(card).name)
    only = getattr(ability, "spend_only", None)
    if not needs_unit(plan, only, riders, tags):
        return {"delta": mana}
    src = plan.oid(card)
    added_ = {"add_units": [{"sym": m, "src": src, "tags": tags, "only": only, "riders": riders, "note": getattr(ability, "spend_text", ""),
                           "generic_allowed": getattr(ability, 'generic_allowed', True), 'production_zone': card.zone}
                          for m, n in mana.items() for _ in range(n)]}
    return with_profile(ability, option, added_, option_index=option_index) if option is not None else added_


def with_profile(ability: M.ManaAbility, option: tuple[str, ...], added: dict[str, Any], *, option_index: int | None) -> dict[str, Any]:
    """Expand independently constructed producer entries; no nominal inference."""
    if ability.output_producers is None:
        raise ActionError('This saved mana ability has unknown producer choices; resolve it manually with the table tools')
    if not ability.output_producers:
        return added
    if option_index is None or not 0 <= option_index < len(ability.options):
        raise ActionError('This saved mana ability has unknown option history; resolve it manually with the table tools')
    index = option_index
    if ability.options[index] != option:
        raise M.ManaError('The selected mana ability option does not match its actual output')
    if len(ability.output_producers) != len(ability.options) or len(ability.output_producers[index]) != len(option):
        raise M.ManaError('The saved mana output has no matching producer profile')
    base = {u['sym']: u for u in added.get('add_units', [])}
    result = []
    for sym, spec in zip(option, ability.output_producers[index], strict=True):
        if spec is None:
            if sym not in base:
                raise M.ManaError('The original mana producer has no actual unit receipt')
            result.append(dict(base[sym]))
        else:
            result.append({'sym': sym, 'src': spec.source_object,
                'tags': list(spec.producer.tags) if spec.producer else [],
                'production_zone': spec.producer.zone if spec.producer else None,
                'only': None, 'riders': [], 'note': '', 'generic_allowed': True})
    return {'add_units': result}


# -- riders (106.6) -----------------------------------------------------------------------------------------------------------
# "If that mana is spent on a creature spell, it gains haste." / "If that mana is spent on an instant or sorcery spell, that spell can't be
# countered." / "… that creature enters with an additional +1/+1 counter on it." / "When that mana is spent to cast a red instant or sorcery
# spell, copy that spell …": the mana carries the rider (a JSON dict: ``spell`` = the selector key of the spells it applies to, ``kind``);
# when the mana pays for a spell that matches, ``pay_spell`` keeps the rider on the spell's payment record (``PaymentRecord.mana_riders``) and
# it is carried out: "uncounterable" and "haste" / "counter" as the permanent enters (``replacements``), a "trigger" as a delayed trigger
# (603.7) that goes on the stack above the spell (106.6; ``triggers._cast_triggers``). 106.6a: each mana carries its own, so two mana
# of one source spent on one spell apply it twice.
_IF_SPENT = re.compile(r"^If (?:(?:that|any of that|this) mana is spent (?:on|to cast)|you spend this mana to cast) (?P<f>.+?), (?P<e>.+)$")
_WHEN_SPENT = re.compile(r"^When (?:that mana is spent|you spend this mana) to cast (?P<f>.+?), (?P<e>.+)$")
_HASTE = re.compile(r"^(?:it|that creature) gains haste(?P<u> until end of turn)?$")
_COUNTER = re.compile(r"^(?:that creature|it) enters with an additional \+1/\+1 counter on it$")
# (Opal Palace: "If you spend this mana to cast your commander, it enters with a number of additional +1/+1 counters on it equal to the number
# of times it's been cast from the command zone this game": the count includes the cast being paid for, 903.8 / its ruling)
_COUNTERS_CASTS = re.compile(r"^it enters with a number of additional \+1/\+1 counters on it equal to the number of times it's been cast "
                             r"from the command zone this game$")


def _spell_key(phrase: str) -> str | None:
    from app.rules import events

    cond = events.parse_condition("you cast " + ("a commander spell you own" if phrase == "your commander" else phrase))
    return cond["spell"] if cond is not None and cond.get("event") == "cast" and "spell" in cond else None


def rider(sentence: str) -> str | None:
    """A rider sentence of a mana ability as the JSON ``ManaAbility.on_spend`` keeps (None: not one the engine carries out)."""
    import json

    s = sentence.strip().rstrip(".")
    if s == ('When you spend this mana to cast a spell or activate an ability, copy that spell or ability. '
             'You may choose new targets for the copy'):
        return json.dumps({'kind': 'copy_paid_stack'}, sort_keys=True)
    if m := _IF_SPENT.fullmatch(s):
        spell, e = _spell_key(m["f"]), m["e"]
        if spell is None:
            return None
        if e == "that spell can't be countered":
            return json.dumps({"kind": "uncounterable", "spell": spell}, sort_keys=True)
        if h := _HASTE.fullmatch(e):
            return json.dumps({"kind": "haste", "spell": spell, "until": "end_of_turn" if h["u"] else "permanent"}, sort_keys=True)
        if e == 'it gains riot':
            return json.dumps({'kind': 'riot', 'spell': spell}, sort_keys=True)
        if _COUNTER.fullmatch(e):
            return json.dumps({"kind": "counter", "spell": spell}, sort_keys=True)
        if _COUNTERS_CASTS.fullmatch(e):
            return json.dumps({"kind": "counter", "spell": spell, "per": "commander_casts"}, sort_keys=True)
        return None
    if m := _WHEN_SPENT.fullmatch(s):
        from app.rules import cast_riders, events, scripts

        spell = _spell_key(m["f"])
        condition = events.parse_condition("you cast " + m["f"])
        if spell and (deferred := cast_riders.parse(condition, m["e"])) is not None:
            return json.dumps({"kind": "trigger", "spell": spell, "effects": deferred[0]}, sort_keys=True)
        if spell and m["e"] == "scry X, where X is the number of times it's been cast from the command zone this game":
            return json.dumps({"kind": "trigger", "spell": spell,
                               "effects": [{"do": "scry", "who": "you", "n": {"commander_casts_of": "event"}}]}, sort_keys=True)
        found = scripts.parse_effects(m["e"][:1].upper() + m["e"][1:] + ".", it="event_spell", event_player=False) if spell else None
        if found is None or found[1] is not None or found[2]:
            return None  # (a target or a "you may" of its own: not carried out)
        return json.dumps({"kind": "trigger", "spell": spell, "effects": found[0]}, sort_keys=True)
    return None


def matching(plan: Plan, riders: list[tuple[str, dict[str, Any]]], card: Any, ch: Any, player: str) -> list[dict[str, Any]]:
    """The riders of the mana spent that apply to this spell (their selector matches it), each with the object that produced the mana."""
    from app.rules import selectors

    return [{"src": src, **r} for src, r in riders
            if r.get("kind") == "copy_paid_stack" or selectors.matches(plan, selectors.from_key(r["spell"]), card, ch, player, None)]


def record_of(plan: Plan, card: Any) -> Any:
    return plan.rules.payments.get(plan.oid(card))


def uncounterable(plan: Plan, card: Any) -> bool:
    """106.6: mana spent on it carried "that spell can't be countered"."""
    rec = record_of(plan, card)
    return rec is not None and any(r["kind"] == "uncounterable" for r in rec.mana_riders)


def entering_counters(plan: Plan, card: Any) -> int:
    """The additional +1/+1 counters mana spent on this permanent spell gives it as it enters (one per rider, 106.6a)."""
    rec = record_of(plan, card)
    if rec is None:
        return 0
    casts = plan.state.players[card.owner].commander_casts.get(card.commander_key or "", 0)
    return sum(casts if r.get("per") == "commander_casts" else 1 for r in rec.mana_riders if r["kind"] == "counter")


def entered(plan: Plan, card: Any, controller: str) -> None:
    """The permanent spell entered: "it gains haste" riders (permanent, or until end of turn)."""
    from app.rules import layers

    rec = record_of(plan, card)
    for r in (rec.mana_riders if rec is not None else ()):
        if r["kind"] == "keyword" and r.get("until") == "next_turn":
            from app.rules import values

            caster = r['until_player']
            taken = values.evaluate(plan, {"controller": caster}, {"turns_taken": 1})
            if taken > r['turns_taken']:
                continue
            effect = layers.add_effect(plan, affected=[plan.oid(card)], layer="6", source=None,
                                       controller=caster, add_keywords=(r['keyword'],), duration="next_turn",
                                       label=f"{r['keyword'].title()} ({r.get('name') or 'mana'})")
            effect.until_player, effect.turn = caster, r['turn']
        if r["kind"] == "haste":
            layers.add_effect(plan, affected=[plan.oid(card)], layer="6", source=None, controller=controller, add_keywords=("haste",),
                              duration="permanent" if r.get("until") == "permanent" else "end_of_turn",
                              label=f"Haste ({r.get('name') or 'mana'})")


def cast_triggers(plan: Plan, spell: Any, caster: str, cast: Any) -> None:
    """"When that mana is spent to cast …, …": a delayed trigger per rider (603.7), on the stack above the spell."""
    from app.rules.trigger_multipliers import DELAYED
    from app.rules.triggers import _add

    rec = record_of(plan, spell)
    copy_spend_triggers(plan, rec, cast, caster)
    from app.rules import layers

    for rider in rec.mana_riders if rec is not None else ():
        if rider.get('kind') == 'riot':
            layers.add_effect(plan, affected=[plan.oid(spell)], layer='6', source=rider.get('src'),
                              controller=caster, add_abilities=['Riot'], duration='permanent', label='Riot (mana spent)')
    for r in rec.mana_riders if rec is not None else ():
        if r["kind"] == "trigger":
            snap = plan.rules.lki.get(r["src"])
            source = snap.card if snap is not None else r["src"].rsplit(".", 1)[0]
            body = ([{'do': 'borrowed_link_scope', 'scope': r['borrowed_link_scope']}] if r.get('borrowed_link_scope') is not None else []) + r['effects']
            _add(plan, controller=caster, source_card=source, source_object=r["src"], name=r.get("name") or spell.name, index=DELAYED,
                 definition={"kind": "triggered", "trigger": "mana_spent", "optional": False, "target": None, "effects": body},
                 event=cast.model_copy(deep=True))


def from_context(plan: Plan, ctx: dict[str, Any], mana: dict[str, int]) -> dict[str, Any]:
    """Mana from a resolving ability retains its original source, even after departure."""
    source = ctx.get('source_object')
    card = plan.state.cards.get(ctx.get('source_card') or '')
    if source is None:
        return {'delta': mana}
    snap = plan.rules.lki.get(source)
    if card is not None and plan.oid(card) == source:
        tags = tags_of(plan.ch(card))
        production_zone = card.zone
    elif snap is not None:
        from app.rules.triggers import _snapshot_card

        tags = tags_of(_snapshot_card(plan, snap)[1])
        production_zone = snap.zone
    else:
        tags = []
        production_zone = None
        if ctx.get('producer_before_cost') is not None:
            from pydantic import TypeAdapter

            captured = TypeAdapter(M.OutputProducer).validate_python(ctx['producer_before_cost'])
            if captured.source_object == source and captured.producer is not None:
                tags = list(captured.producer.tags)
                production_zone = captured.producer.zone
    return {'add_units': [{'sym': sym, 'src': source, 'tags': tags, 'only': None, 'riders': [], 'note': '',
                          'generic_allowed': ctx.get('generic_allowed', True), 'production_zone': production_zone}
                          for sym, n in mana.items() for _ in range(n)]}


def ability_riders(riders: list[tuple[str, dict[str, Any]]]) -> list[dict[str, Any]]:
    """Only riders explicitly referring to ability activation apply to an ability cost."""
    return [{'src': src, **r} for src, r in riders if r.get('kind') == 'copy_paid_stack']


def copy_spend_triggers(plan: Plan, record: Any, event: Any, caster: str) -> None:
    from app.rules.trigger_multipliers import DELAYED
    from app.rules.triggers import _add

    for rider in record.mana_riders if record is not None else ():
        if rider.get('kind') != 'copy_paid_stack':
            continue
        oid = rider['src']
        snap = plan.rules.lki.get(oid)
        source = snap.card if snap is not None else oid.rsplit('.', 1)[0]
        _add(plan, controller=caster, source_card=source, source_object=oid,
             name=rider.get('name') or 'Mana spent', index=DELAYED,
             definition={'kind': 'triggered', 'trigger': 'mana_spent', 'optional': False, 'target': None,
                         'effects': [{'do': 'copy_event_stack'}, {'do': 'copy_new_targets', 'optional': True}]},
             event=event.model_copy(deep=True))

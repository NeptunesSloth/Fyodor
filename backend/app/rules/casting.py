"""Mana abilities, paying costs and casting spells (milestone 15).

Casting follows the real order (announce → move to the stack → pay), but everything is planned on
the scratch table first, so a spell you can't pay for simply isn't cast: nothing half-happens.
Costs are paid automatically from your mana pool and untapped mana sources (see ``mana.solve``);
tap lands yourself first (``activate_ability`` on their mana ability) to pay a particular way.
"""

from __future__ import annotations

import json
import re
import secrets
from collections.abc import Callable
from dataclasses import dataclass, replace
from itertools import islice, product
from typing import Any

from pydantic import TypeAdapter

from app.game import actions as A
from app.game.errors import ActionError
from app.game.rules_state import (
    CostContribution,
    DecisionOption,
    NumericRollCostReceipt,
    ObjectRef,
    OpponentGainCostReceipt,
    PaymentRecord,
    Permission,
    SpliceText71,
    StackEntry,
    TargetRef,
    TriggerEvent,
    TurnCount,
    cancelable,
    emit,
)
from app.game.state import ALL, STACK, CardInstance, GameState, zone_key
from app.rules import (
    alt_costs,
    attachments,
    cost_changes,
    cost_payment,
    costs,
    delayed,  # -- as long as (wave 37A) --
    graveyard_keywords,
    history,
    merged,  # -- merged permanents (wave 18D) --
    modal_abilities,
    ninjutsu,
    offering,  # -- offering (wave 51H) --
    per_opponent,  # -- per-opponent targets (wave 23A) --
    permissions,
    player_relative,  # -- player-relative selectors (wave 53A) --
    read_pass,
    restrictions,
    scripts,
)
from app.rules import characteristics as chars
from app.rules import commander as cmdr
from app.rules import mana as M
from app.rules import payment as P
from app.rules.activation_words import actor_allowed, opponents_only  # -- activation wordings (wave 7B) --
from app.rules.characteristics import CardInfo, Characteristics
from app.rules.costs import AbilityCost, kicker_cost, parse_ability_cost
from app.rules.oracle import AbilityText
from app.rules.plan import Plan, decide, require_no_decision, require_priority
from app.rules.targets import choose_groups, legal_targets, source_of
from app.rules.targets import label as target_label
from app.rules.targets import ref as target_ref

MAIN_PHASES = ("main1", "main2")


# -- facts about permanents -------------------------------------------------------------
def commander_identity(state: GameState, player: str, info: CardInfo) -> tuple[str, ...]:
    def work() -> tuple[str, ...]:
        commanders = [info.get(c.card_id) for c in state.cards.values() if c.owner == player and c.commander_key and c.card_id]
        return cmdr.deck_identity([d for d in commanders if d])  # the same identity the deck checks use

    return read_pass.once(state, info, ("commander_identity", player), work)  # (wave 29A: once per read-only pass)


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


def can_use_tap_abilities(state: GameState, card: CardInstance, ch: Characteristics, info: CardInfo | None = None) -> bool:
    if card.tapped or not card.zone.endswith(":battlefield"):
        return False
    return not (ch.is_creature and "haste" not in ch.keywords and summoning_sick(state, card)
                and not _as_though_haste(state, card, info))


def _as_though_haste(state: GameState, card: CardInstance, info: CardInfo | None) -> bool:
    """-- cast limits (wave 5E) -- "You may activate abilities of creatures you control as though those creatures had
    haste" (302.6, 602.5a: their {T} / {Q} abilities only; app/rules/cast_limits.py)."""
    from app.rules import cast_limits

    return cast_limits.as_though_haste(state, card, info)


COLOR_NAMES = {"white": "W", "blue": "U", "black": "B", "red": "R", "green": "G"}


def _chosen_color(card: CardInstance) -> str | None:
    for key, value in card.choices.items():
        if "color" in key.lower():
            return COLOR_NAMES.get(value.strip().lower())
    return None


# -- refused copy/mana (wave 3R3) -- a mana restriction "of the chosen type" (205.3m: a creature type)
def _chosen_creature_type(card: CardInstance) -> str | None:
    from app.rules.creature_types import CREATURE_TYPES

    for key, value in card.choices.items():
        if "creature type" in key.lower():
            v = value.strip()
            return v if v in CREATURE_TYPES else None
    return None


def _choice_cost_ok(extra: Any) -> bool:
    """The other parts of a mana ability's cost are ones its activation pays (mana, life, the source's
    counters …) or objects the payer chooses (Ashnod's Altar's "Sacrifice a creature")."""
    from app.rules import costs as C

    return not extra.unsupported and all(
        c.kind in (C.MANA, C.TAP, C.PAY_LIFE, C.EXERT, C.UNTAP, C.FORAGE, C.DISCARD_HAND, C.COLLECT_EVIDENCE, C.RETURN_PERMANENT, "EXILE_FROM_HAND")  # (wave 17B: exert, {Q}, forage: paid by hand; 26C: discard your hand)
        or ((not c.activation_only or c.kind == C.EXILE or (c.x and c.kind in (C.TAP_OTHER, C.SACRIFICE))) and (  # (X: Hazel of the Rootbloom)
            (c.kind in (C.SACRIFICE, C.REMOVE_COUNTER, C.EXILE_FROM_GRAVEYARD) and c.selector is None)
            or (c.selector is not None and c.kind in (C.SACRIFICE, C.DISCARD, C.TAP_OTHER, C.EXILE_FROM_GRAVEYARD, C.EXILE)
                and not c.random)))  # (activation_only: wave 4H, 605)
        for c in extra.components)


def _with_chosen_type(spend: str, creature_type: str) -> str:
    import json

    spec = json.loads(spend[2:])
    for side in ("cast", "ability"):
        alts = spec.get(side)
        if isinstance(alts, list):
            for alt in alts:
                if alt.pop("chosen", False):
                    alt["subtypes"] = sorted({*alt.get("subtypes", []), creature_type})
    return "q:" + json.dumps(spec, sort_keys=True)


def _with_chosen_color(spend: str, color: str) -> str:
    """-- most-played cards (wave 51F) -- "monocolored spells of that color" (Throne of Eldraine): the color chosen as the permanent entered, as the letter spells must be."""
    import json

    spec = json.loads(spend[2:])
    for alt in spec["cast"] if isinstance(spec.get("cast"), list) else []:
        if alt.pop("chosen_color", False):
            alt["mono_color"] = color
    return "q:" + json.dumps(spec, sort_keys=True)
# -- end refused copy/mana (wave 3R3) --


def _land_mana(state: GameState, players: list[str], info: CardInfo, *, skip: str, only: str = "land") -> set[str]:
    """Types of mana lands these players control could produce (Reflecting Pool, Exotic Orchard); ``only``: "basic" lands or
    "Gate" lands (-- mana (wave 19E) -- Star Compass, Gond Gate)."""
    out: set[str] = set()
    from app.rules import (
        mana_replace,  # -- mana replacements (wave 9C) -- 106.7: replacement effects change what lands produce
    )

    if mana_replace.in_play(state, info):
        return out
    for p in players:
        for cid in state.zones.get(zone_key(p, "battlefield"), []):
            if cid == skip:
                continue
            card = state.cards[cid]
            ch = chars.of(card, info)
            if not ch.is_land or (only == "basic" and "Basic" not in ch.supertypes) or (only == "Gate" and "Gate" not in ch.subtypes):
                continue
            for ab in ch.abilities:
                if ab.kind != "mana":
                    continue
                parsed = M.parse_mana_ability(ab.text, commander_identity(state, p, info), card_name=ch.name)  # (wave 19E: Command Tower: its controller's identity)
                if parsed is None:
                    continue
                for opt in parsed.options:
                    out |= {m for m in opt if m in M.ALL_MANA}
    return out


def _mana_count(state: GameState, card: CardInstance, count: str, info: CardInfo) -> int:
    """How many times a counted mana ability's mana is added (Gaea's Cradle, Cabal Coffers, …)."""
    from app.rules.layers import derive

    if count in ("power", "toughness"):
        ch = derive(state, card, chars.of(card, info), info)
        if ch.pt:
            return max(0, ch.pt[0 if count == "power" else 1])
        stat = ch.power if count == "power" else ch.toughness
        return int(stat) if stat and stat.isdigit() else 0
    if count.startswith("counters:"):  # (wave 3M) "for each charge counter on this artifact"
        return card.counters.get(count.split(":", 1)[1], 0)
    if count == "chosen_type":  # -- refused copy/mana (wave 3R3) -- "creatures you control of the chosen type"
        chosen = _chosen_creature_type(card)
        if chosen is None:
            return 0
        return sum(1 for cid in state.zones.get(zone_key(card.controller, "battlefield"), [])
                   if state.cards[cid].controller == card.controller
                   and (lambda c: c.is_creature and chosen in c.subtypes)(derive(state, state.cards[cid], chars.of(state.cards[cid], info), info)))
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
    # -- mana riders (wave 5A) -- "for each …" / "where X is …" counts, "any color among …" (app/rules/mana_riders.py)
    from app.rules import mana_riders

    more = mana_riders.resolve(state, card, ab, info)
    if more is not None:
        return more
    # -- end mana riders (wave 5A) --
    if ab.instead_if == (M.PLAYED_LAND,):  # -- this-turn history (wave 4D) -- River of Tears
        played = state.rules is not None and state.rules.lands_this_turn(card.controller, state.turn.number) > 0
        return ab.instead if played else ab.options
    if ab.instead_if and ab.instead_if[0][:1] == ("@status",):  # -- designations (wave 45B) -- 726.1 the initiative, 309.7 a completed dungeon
        held = state.table.initiative == card.controller if ab.instead_if[0][1] == "initiative" \
            else bool(state.rules is not None and state.rules.completed_dungeons.get(card.controller))
        return ab.instead if held else ab.options
    chosen_options = ab.options
    if ab.instead_if and ab.instead_if[0][:1] == ("@counter",):  # -- opening hand (wave 18C) -- the source's own counter (122.1)
        chosen_options = ab.instead if card.counters.get(ab.instead_if[0][1], 0) > 0 else ab.options
        if ("LANDS",) not in (o[:1] for o in chosen_options):  # (-- most-played cards (wave 51F) -- Incubation Druid's types are resolved below)
            return chosen_options
    if ab.instead_if and ab.instead_if[0][:1] in (("@count",), ("@power",)):  # -- kicked / instead (wave 4G) --
        return ab.instead if _controls_for_instead(state, card.controller, ab.instead_if[0], info) else ab.options
    if ab.instead_if and ab.instead_if[0][:1] == ("@named",):  # -- named permanents (wave 35C) -- Tower Worker: a creature with each name
        return ab.instead if all(_controls_named(state, card.controller, need[1], info) for need in ab.instead_if) else ab.options
    if ab.instead_if and all(_controls_subtypes(state, card.controller, need, info) for need in ab.instead_if):
        return ab.instead  # -- refused copy/mana (wave 3R3): Urza's Tower with the Mine and the Power-Plant --
    from app.rules import removed_mana  # -- if you do (wave 6F) -- one option per number removed

    if (ab.count or "").startswith("xcost:") or ab.count in ("sacrificed_mv", "exiled_mv_plus_one", "paid_sacrifice_count"):
        return ab.options  # (wave 17B: the mana depends on the X announced as it's activated: _activate_choosing)
    if (removed := removed_mana.parts(ab.count)) is not None:
        return removed_mana.options(card.counters.get(removed[0], 0), ab.count or "", ab.options[0])
    if ab.count == "devotion":  # -- refused copy/mana (wave 3R3): Nykthos, per chosen color (700.5) --
        found = [opt * n for opt in ab.options if (n := _devotion(state, card.controller, opt[0], info)) > 0]
        return tuple(found)
    if ab.count:
        n = _mana_count(state, card, ab.count, info)
        return tuple(opt * n for opt in ab.options) if n > 0 else ((),)
    out: list[tuple[str, ...]] = []
    for opt in chosen_options:
        if not opt:
            out.append(())
            continue
        if "CHOSEN" in opt:
            color = _chosen_color(card)
            if color is None:
                continue  # nothing chosen yet: that option can't be used
            out.append(tuple(color if m == "CHOSEN" else m for m in opt))
        elif opt == ("OWN_COLORS",):  # -- counters (wave 44C) -- "one mana of any of this creature's colors" (Katilda): its colors now (613), none when it is colorless (106.1b: no mana)
            from app.rules.layers import derive

            own = derive(state, card, chars.of(card, info), info).colors
            out += [(m,) for m in M.COLORS if m in own]
        elif opt == ("EXILED_COLORS",):  # -- imprint (wave 51B) -- 607.2a, 106.1b: the colors now (613) of the cards its linked ability exiled and that are still there (400.7); a colorless one gives no mana
            from app.rules import exiled_with
            from app.rules.layers import derive

            rs = state.rules
            key = exiled_with.link_key({'source_object': rs.object_id(card.id) if rs else '', 'borrowed_link_scope': ab.borrowed_link_scope})
            seen = {col for o in (rs.exiled_with.get(key, []) if rs is not None else []) if (c := state.cards.get(o.rsplit(".", 1)[0])) is not None
                    and c.zone.endswith(":exile") and rs is not None and rs.object_id(c.id) == o for col in derive(state, c, chars.of(c, info), info).colors}
            out += [(m,) for m in M.COLORS if m in seen]
        elif set(opt) == {"LANDS"}:  # (-- most-played cards (wave 51F) -- "three mana of that type": the same type, n times)
            out += [(m,) * len(opt) for m in M.ALL_MANA if m in _land_mana(state, [card.controller], info, skip=card.id)]
        elif opt[0].startswith("LANDS:"):  # -- mana (wave 19E) -- any color / type a (basic / Gate) land you control could produce
            _, kind, only = opt[0].split(":")
            produced = _land_mana(state, [card.controller], info, skip=card.id, only=only)
            out += [(m,) for m in (M.ALL_MANA if kind == "type" else M.COLORS) if m in produced]
        elif opt == ("LANDS_OPP",):
            opponents = [p for p in state.seat_order if p != card.controller]
            out += [(m,) for m in M.COLORS if m in _land_mana(state, opponents, info, skip=card.id)]
        else:
            out.append(opt)
    return tuple(dict.fromkeys(out))


def _controls_for_instead(state: GameState, player: str, marker: tuple[str, ...], info: CardInfo) -> bool:
    """-- kicked / instead (wave 4G) -- a mana ability's "If you control …, add … instead" (mana._CONTROL_INSTEAD), as
    the permanents are now (613: their characteristics after continuous effects)."""
    from app.rules.layers import derive

    found = [derive(state, state.cards[cid], chars.of(state.cards[cid], info), info)
             for cid in state.zones.get(zone_key(player, "battlefield"), []) if state.cards[cid].controller == player]
    if marker[0] == "@count":
        return sum(1 for ch in found if marker[1] in ch.types) >= int(marker[2])
    return any(ch.is_creature and _power(ch) >= int(marker[1]) for ch in found)


def _power(ch: Characteristics) -> int:
    if ch.pt:
        return ch.pt[0]
    return int(ch.power) if ch.power and ch.power.lstrip("-").isdigit() else 0


def _devotion(state: GameState, player: str, color: str, info: CardInfo) -> int:
    """-- refused copy/mana (wave 3R3) -- 700.5: mana symbols of that color among the mana costs of permanents
    ``player`` controls (a hybrid symbol counts once; Phyrexian ones count, 107.4e-f; as values._devotion)."""
    from app.rules import values
    return values._devotion(Plan.view(state,player,info),player,[color])


def _controls_named(state: GameState, player: str, name: str, info: CardInfo) -> bool:
    """-- named permanents (wave 35C) -- ``player`` controls a creature with this name (201.2, 709.4a; a face-down one has none, 708.2a)."""
    from app.rules import card_names
    from app.rules.layers import derive

    for cid in state.zones.get(zone_key(player, "battlefield"), []):
        c = state.cards[cid]
        if c.controller == player and not c.face_down:
            ch = derive(state, c, chars.of(c, info), info)
            if ch.is_creature and card_names.has_name(ch, name):
                return True
    return False


def _controls_subtypes(state: GameState, player: str, need: tuple[str, ...], info: CardInfo) -> bool:
    """-- refused copy/mana (wave 3R3) -- ``player`` controls a permanent with all these subtypes ("an Urza's
    Power-Plant": the subtypes Urza's and Power-Plant, 205.3n), its current characteristics (613)."""
    from app.rules.layers import derive

    for cid in state.zones.get(zone_key(player, "battlefield"), []):
        c = state.cards[cid]
        if c.controller == player and set(need) <= derive(state, c, chars.of(c, info), info).subtypes:
            return True
    return False


def _controls(state: GameState, player: str, what: str, info: CardInfo) -> bool:
    """A mana ability's "Activate only if you control …": "<Type>[|<Type>]" (one of them), or
    "count:<Type>:<n>" (n or more) — wave 3M."""
    if what.startswith("count:"):
        _, kind, n = what.split(":")
        return sum(1 for cid in state.zones.get(zone_key(player, "battlefield"), [])
                   if kind in chars.of(state.cards[cid], info).types) >= int(n)
    wanted = what.split("|")
    for cid in state.zones.get(zone_key(player, "battlefield"), []):
        ch = chars.of(state.cards[cid], info)
        if any(w in ch.subtypes or w in ch.types for w in wanted):
            return True
    return False


# -- ability words (wave 4F) -- a mana ability's "Activate only if [condition]" (602.5, 605.3a): the
# condition grammar of app/rules/conditions.py, read for the ability's controller as it would be activated
def _mana_condition_holds(state: GameState, card: CardInstance, cond: str, info: CardInfo) -> bool:
    import json

    from app.rules import conditions

    view = Plan.view(state, card.controller, info)
    return conditions.holds(view, {"controller": card.controller, "source_card": card.id}, json.loads(cond[len("cond:"):]))
# -- end ability words (wave 4F) --


def mana_abilities(state: GameState, card: CardInstance, info: CardInfo) -> list[tuple[int, M.ManaAbility]]:
    """The permanent's mana abilities the engine can carry out right now (options resolved:
    chosen color, lands' mana; conditions, once-per-turn and non-mana costs checked)."""
    from app.rules.layers import derive

    ch = derive(state, card, chars.of(card, info), info)  # (granted mana abilities: Cryptolith Rite …)
    if "cant_activate" in ch.imposed:  # "its activated abilities can't be activated" (mana abilities too)
        return []
    no_tap = "cant_activate_tap" in ch.imposed  # -- attached (wave 100F) -- "… with {T} in their costs can't be activated" (Serra Bestiary)
    # -- cast limits (wave 5E) -- Grand Abolisher, Collector Ouphe (602.5, 605.1a)
    from app.rules import cast_limits

    if cast_limits.any_activation_limits(state, info) and \
            cast_limits.activation_problem(state, card.controller, card, ch, info, mana=True) is not None:
        return []
    identity = commander_identity(state, card.controller, info)
    r = state.rules
    out = []
    for ab in ch.abilities:
        if ab.kind != "mana":
            continue
        parsed = M.parse_mana_ability(ab.text, identity, card_name=ch.name)
        if parsed is None or parsed.from_hand or (no_tap and parsed.tap):  # (from_hand: only from the hand, wave 5A — mana_riders.activate_from_hand)
            continue
        if parsed.from_graveyard and card.zone != zone_key(card.owner, 'graveyard'):
            continue
        from app.rules import cost_moves
        if parsed.sacrifice_self and cost_moves.reserved(state, card.controller, card.id):
            continue  # A chosen declaration cost still needs this exact permanent.
        if ab.borrowed_origin:
            from app.rules import abilities_of

            parsed = replace(parsed, borrowed_link_scope=abilities_of.link_scope(ab))
        if parsed.extra_cost and r is not None and getattr(ab, "borrowed_color", None) == r.object_id(card.id):
            colored = parse_ability_cost(parsed.extra_cost, card_name=ch.name).mana
            if colored:
                mode = cast_limits.ability_spend_mode(state, card.controller, card, ch, info) or "color"
                parsed = replace(parsed, extra_cost=parsed.extra_cost.replace(colored, M.spend_as(M.parse_cost(colored), mode).text(), 1))
        limits = restrictions.parse(_own_text(ab.text, ch.name)) or []
        if limits and not any(x["kind"] == "any_player" for x in limits) and restrictions.problem(state, card.controller, card, ab.index, limits,
                                           Plan.view(state, card.controller, info), ch.name) is not None:
            continue  # CR 605.3a, 702.177a: mana abilities obey their activation limits too
        if parsed.spend_only is not None and parsed.spend_only.startswith("q:") and '"chosen": true' in parsed.spend_only:
            # -- refused copy/mana (wave 3R3) -- "a creature spell of the chosen type": the type chosen as it entered
            chosen = _chosen_creature_type(card)
            if chosen is None:
                continue
            parsed = replace(parsed, spend_only=_with_chosen_type(parsed.spend_only, chosen))
        if parsed.spend_only is not None and parsed.spend_only.startswith("q:") and '"chosen_color": true' in parsed.spend_only:
            color = _chosen_color(card)  # -- most-played cards (wave 51F) -- "monocolored spells of that color": nothing chosen, nothing to spend it on
            if color is None:
                continue
            parsed = replace(parsed, spend_only=_with_chosen_color(parsed.spend_only, color))
        cond = parsed.condition or ""
        if cond.startswith(("control:", "count:")) and \
                not _controls(state, card.controller, cond[len("control:"):] if cond.startswith("control:") else cond, info):
            continue
        if cond.startswith("cond:") and not _mana_condition_holds(state, card, cond, info):  # -- ability words (wave 4F) --
            continue
        if parsed.once_per_turn and r is not None and \
                r.once_per_turn.get(f"{r.object_id(card.id)}:{ab.index}") == state.turn.number:
            continue
        if parsed.sacrifice_self or parsed.extra_cost:  # -- prohibitions (wave 22B) -- "Players can't pay life or sacrifice creatures …" (119.4)
            from app.rules import prohibitions

            if (parsed.sacrifice_self and prohibitions.sacrifice_banned(state, info, card, mana_ability=True)) or (
                    parsed.extra_cost and parse_ability_cost(parsed.extra_cost, card_name=ch.name).life
                    and prohibitions.life_banned(state, info, mana_ability=True)):
                continue
        if parsed.extra_cost:
            extra = parse_ability_cost(parsed.extra_cost, card_name=ch.name)
            energy = extra.energy  # (wave 3E: "{T}, Pay {E}: Add …", 107.14)
            if not (extra.basic or (parsed.chooses and _choice_cost_ok(extra))) or extra.energy_x or \
                    (extra.life and state.players[card.controller].life < extra.life) or \
                    _life_locked(state, info, card.controller, extra.life) or \
                    any(card.counters.get(k, 0) < n or (n > 0 and prohibitions.cant_remove_counters(Plan.view(state, card.controller, info), card.id, k)) for k, n in extra.remove_counters) or \
                    state.players[card.controller].resources.get("energy", 0) < energy:
                continue
        options = _resolve_options(state, card, parsed, info)
        if options:
            out.append((ab.index, replace(parsed, options=options)))
    # -- attached events (wave 4L) -- "Whenever enchanted land is tapped for mana"
    from app.rules import attached_mana, mana_replace, tap_mana
    from app.rules.contextual_mana_triggers import prepare as prepare_staged_mana

    out = prepare_staged_mana(state, card, info, out)
    reveal_sources = [(i, ab) for i, ab in out if ab.reveal_hand is not None or ab.native_body]
    out = [(i, ab) for i, ab in out if ab.reveal_hand is None and not ab.native_body]
    out = mana_replace.extend(state, card, info, out)  # -- mana replacements (wave 9C) -- 106.12b: first, then the triggers' extras
    out = tap_mana.extend(state, card, info, out)  # -- mana riders (wave 5A) -- "Whenever you tap a land for mana, …"
    return attached_mana.extend(state, card, info, ch.is_land, out) + reveal_sources


def _spending_cost(state: GameState, player: str, info: CardInfo | None, cost: M.ManaCost) -> M.ManaCost:
    from app.rules import mana_sunglasses49

    return mana_sunglasses49.spending_cost(state, player, info, cost)


# Mana abilities use the same cost-modifier stage as other activated abilities (605.3a).
def mana_activation_cost(state: GameState, card: CardInstance, ch: Characteristics,
                         ability: M.ManaAbility, info: CardInfo, *, x: int | None = None) -> M.ManaCost:
    from app.rules import cast_limits

    raw = parse_ability_cost(ability.extra_cost, card_name=ch.name).mana if ability.extra_cost else ''
    if x is not None:
        raw = M.parse_cost(raw).with_x(x).text()
    keyword_text = {"exhaust": "Exhaust — ", "boast": "Boast — "}.get(ability.activation_keyword or "", "")
    cost = M.parse_cost(permissions.ability_mana(state, card.controller, card, ch, raw, info,
                                              ability_text=keyword_text, mana_ability=True))
    mode = cast_limits.ability_spend_mode(state, card.controller, card, ch, info)
    return M.spend_as(cost, mode) if mode else cost


def spend_allowed(kind: str | None, purpose: Purpose | None) -> bool:
    """May mana with this spending restriction pay for ``purpose``?"""
    if kind is None:
        return True
    if purpose is None:
        return False
    spell, source = purpose.spell, purpose.ability_of
    if kind.startswith(('cast_object:', 'cast_objects:')):
        if spell is None or purpose.spell_object is None:
            return False
        raw = json.loads(kind.partition(':')[2])
        wanted = raw if kind.startswith('cast_objects:') else [raw]
        return any(ObjectRef.model_validate(purpose.spell_object) == ObjectRef.model_validate(ref) for ref in wanted)
    if kind == "creature":
        return spell is not None and spell.is_creature
    if kind == "instant_sorcery":
        return spell is not None and bool(spell.types & {"Instant", "Sorcery"})
    if kind == "instant_sorcery_or_class_level":
        return (spell is not None and bool(spell.types & {'Instant', 'Sorcery'})) or (source is not None and purpose.special == 'class_level')
    if kind == "artifact":
        return spell is not None and "Artifact" in spell.types
    if kind == "ability":
        return source is not None and purpose.special not in ('turn_up','unlock','foretell')
    if kind == "artifact_or_artifact_ability":
        return (spell is not None and "Artifact" in spell.types) or (source is not None and "Artifact" in source.types and purpose.special not in ('turn_up','unlock','foretell'))
    if kind == "legendary":
        return spell is not None and "Legendary" in spell.supertypes
    if kind.startswith("type:"):
        t = kind[5:]
        return spell is not None and (t in spell.subtypes or t in spell.types)
    if kind == "colorless_eldrazi":  # (wave 3M) Eldrazi Temple
        return (spell is not None and "Eldrazi" in spell.subtypes and not spell.colors) or \
            (source is not None and "Eldrazi" in source.subtypes and not source.colors)
    if kind == "not_nonartifact_spell":  # (wave 3M) Powerstone: any ability, or an artifact spell
        return spell is None or "Artifact" in spell.types
    if kind.startswith("q:"):  # -- refused copy/mana (wave 3R3): the general restriction (mana.parse_spend) --
        spec = json.loads(kind[2:])
        if spec.get('cost_colorless') and purpose.cost_colorless:
            return True
        if purpose.spell is not None and purpose.alternative in (spec.get('alternative') or ()):
            return True
        if purpose.special == 'turn_up' and purpose.payment_method in (spec.get('turn_up_methods') or ()):
            return True
        if spec.get("cost_x"):  # -- mana provenance (wave 18B) -- "only on costs that contain {X}"
            return purpose.selected_cost_has_x is True
        if purpose.special and purpose.special in (spec.get("special") or ()):  # -- mana for special abilities (wave 19E) --
            return True
        if purpose.special in ('turn_up','unlock','foretell'):
            return False  # These are special actions, not activated abilities of a source.
        side, ch = ("cast", spell) if spell is not None else ("ability", source)
        allowed = spec.get(side)
        if ch is None or allowed is None or any(a.get("chosen") or a.get("chosen_color") for a in allowed if isinstance(allowed, list)):
            return False
        return allowed == "any" or any(M.spend_alt_matches(a, ch) and (side == "ability" or _cast_origin_ok(a, purpose))
                                       for a in allowed)
    return False


def _cast_origin_ok(alt: dict[str, Any], purpose: Purpose) -> bool:
    """-- activated sweep (wave 17B) -- the origin parts of a "Spend this mana only to cast …" alternative: kicked (702.33), the
    zone it's cast from (exile / a graveyard / your graveyard / not your hand)."""
    zone = purpose.zone.rsplit(":", 1)[-1] if purpose.zone else None
    if alt.get("kicked") and not purpose.kicked:
        return False
    if alt.get("not_own") and purpose.own:  # (-- mana provenance (wave 18B) --)
        return False
    if alt.get("zone") and (zone != alt["zone"] or (alt.get("own") and (purpose.zone or "").split(":")[0] != purpose.player)):
        return False
    return not (alt.get("not_zone") and (zone is None or zone == alt["not_zone"]))


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
        usable_tap = can_use_tap_abilities(state, card, ch, info)
        # (wave 3E) an ability paying energy is activated by hand only: several sources sharing one
        # energy total aren't something the solver can split (118.3: no partial payment)
        abilities = [(i, ab) for i, ab in mana_abilities(state, card, info)
                     if (usable_tap or not ab.tap) and spend_allowed(ab.spend_only, purpose) and any(ab.options)
                     and not ab.chooses and ab.reveal_hand is None and ab.self_counter is None  # (wave 3R3: the payer's choice: by hand)
                     and not (ab.count or "").startswith("removed:")  # -- if you do (wave 6F) -- how many: by hand
                     and not (ab.extra_cost and parse_ability_cost(ab.extra_cost, card_name=ch.name).energy)]
        if any(ab.output_producers is None for _, ab in abilities):
            raise ActionError("Saved mana ability has unknown producer choices; resolve manually with table tools")
        from app.rules.layers import derive
        producer_ch = derive(state, card, ch, info)
        producer = M.ProducerFact(tuple(sorted(producer_ch.supertypes | producer_ch.types | producer_ch.subtypes)), card.zone)
        rank = 0 if ch.is_land else 2 if ch.is_creature else 1
        activation_costs = {i: mana_activation_cost(state, card, ch, ab, info) for i, ab in abilities}
        free = [(i, ab) for i, ab in abilities if activation_costs[i].is_free]
        plain = [(i, ab) for i, ab in free if not ab.sacrifice_self and ab.tap]
        chosen = plain or [(i, ab) for i, ab in free if ab.tap]
        if chosen:
            pairs: dict[tuple[tuple[str, ...], bool, tuple[M.OutputProducer | None, ...]], tuple[int, int, int]] = {}
            for i, ab in sorted(chosen, key=lambda x: x[1].penalty):
                for position, opt in enumerate(ab.options):
                    profile = ab.output_producers[position] if ab.output_producers else (None,) * len(opt)
                    pairs.setdefault((opt, ab.generic_allowed, profile), (i, ab.penalty, position))
            opts = tuple(o for o, _, _ in pairs)
            out.append(M.Source(card.id, opts, sacrifice=not plain, rank=rank + (5 if not plain else 0),
                                abilities=tuple(pairs[o][0] for o in pairs), snow="Snow" in ch.supertypes,
                                generic_allowed=tuple(mask for _, mask, _ in pairs) if any(not mask for _, mask, _ in pairs) else (),
                                producer_facts=tuple(tuple(item.producer if item is not None else producer for item in profile)
                                    for _, _, profile in pairs),
                                ability_options=tuple(pairs[key][2] for key in pairs)))
        for i, ab in abilities:
            mana_cost = activation_costs[i]
            if not mana_cost.is_free and ab.tap and not ab.sacrifice_self:
                out.append(M.Source(card.id, ab.options, rank=rank + 3, abilities=(i,) * len(ab.options),
                                    activation=mana_cost, snow="Snow" in ch.supertypes,
                                    generic_allowed=(False,) * len(ab.options) if not ab.generic_allowed else (),
                                    producer_facts=tuple(tuple(item.producer if item is not None else producer
                                        for item in (ab.output_producers[position] if ab.output_producers else (None,) * len(opt)))
                                        for position, opt in enumerate(ab.options)),
                                    ability_options=tuple(range(len(ab.options)))))
    return out


# -- paying with things that aren't mana: convoke / improvise / delve (app/rules/payment.py) ----
HELPER_ABILITY: dict[P.Kind, int] = {"convoke": -1, "improvise": -2, "delve": -3}  # pseudo "ability index" in the can_pay hint


def helper_kinds(spell: Characteristics | None, state: GameState | None = None, player: str | None = None,
                 spell_card: str | None = None, info: CardInfo | None = None) -> tuple[P.Kind, ...]:
    """The spell's convoke / improvise / delve — its own, and (-- cast limits (wave 5E) --, given the table) those a
    permanent grants ("Nonartifact spells you cast have improvise.": app/rules/cast_limits.py)."""
    granted: set[str] = set()
    if spell is not None and state is not None and player is not None and spell_card is not None and info is not None:
        from app.rules import cast_limits

        granted = cast_limits.granted_helpers(state, player, spell_card, spell, info)
    return tuple(k for k in P.KINDS if spell is not None and (k in spell.keywords or k in granted))


def helper_problem(state: GameState, player: str, info: CardInfo, kind: P.Kind, card: CardInstance | None,
                   spell_card: str | None) -> tuple[str | None, frozenset[str]]:
    """Why ``card`` can't be used for ``kind`` right now (or None), and its colors (convoke)."""
    from app.rules.layers import derive

    if card is None:
        return "That card isn't here any more", frozenset()
    if kind == "delve":  # 702.66a: a card from your graveyard (not the spell being cast)
        if card.zone != zone_key(player, "graveyard") or card.id == spell_card:
            return "Exile a card from your graveyard for delve", frozenset()
        return None, frozenset()
    ch = derive(state, card, chars.of(card, info), info)
    on_field = card.zone == zone_key(player, "battlefield") and card.controller == player
    if kind == "convoke" and (not on_field or card.tapped or not ch.is_creature):  # 702.51a
        return "Tap an untapped creature you control for convoke", frozenset()
    if kind == "improvise" and (not on_field or card.tapped or "Artifact" not in ch.types):  # 702.126a
        return "Tap an untapped artifact you control for improvise", frozenset()
    return None, frozenset(ch.colors)


def helpers_for(state: GameState, player: str, info: CardInfo, spell: Characteristics | None, spell_card: str | None,
                contributions: list[dict[str, Any]]) -> list[P.Helper]:
    """Validate a spell's chosen cost contributions (each card once, the spell has the keyword)."""
    kinds = helper_kinds(spell, state, player, spell_card, info)
    out: list[P.Helper] = []
    seen: set[str] = set()
    for c in contributions:
        kind, cid = P.kind_of(str(c["kind"])), str(c["card"])
        if kind is None or kind not in kinds:
            raise ActionError(f"Only a spell with {kind} can be paid for that way")
        if cid in seen:
            raise ActionError("Each card can pay for only one mana of the cost")
        seen.add(cid)
        problem, colors = helper_problem(state, player, info, kind, state.cards.get(cid), spell_card)
        if problem:
            raise ActionError(problem)
        out.append(P.Helper(kind, cid, colors))
    return out


def available_helpers(state: GameState, player: str, info: CardInfo, spell: Characteristics | None,
                      spell_card: str | None) -> list[P.Helper]:
    """Everything that could pay part of this spell's cost right now."""
    out: list[P.Helper] = []
    for kind in helper_kinds(spell, state, player, spell_card, info):
        zone = zone_key(player, "graveyard" if kind == "delve" else "battlefield")
        for cid in state.zones.get(zone, []):
            problem, colors = helper_problem(state, player, info, kind, state.cards[cid], spell_card)
            if problem is None:
                out.append(P.Helper(kind, cid, colors))
    return out


def _helper_sources(state: GameState, player: str, info: CardInfo, spell: Characteristics,
                    spell_card: str | None, sources: list[M.Source]) -> list[M.Source]:
    """For the castability hint only (never to pay): each helper as a pseudo-source whose units
    can pay what it may pay — its colors (convoke) or GENERIC ("1"), which no mana requirement
    other than generic accepts, so {C} is never paid this way. A creature is one source: its
    mana abilities or convoke, never both."""
    from app.rules import mana_producer_profiles45

    producer = mana_producer_profiles45.requirement(spell) if spell is not None else None
    out = list(sources)
    by_card = {s.card_id: k for k, s in enumerate(out)}
    for h in available_helpers(state, player, info, spell, spell_card):
        opts = tuple((c,) for c in sorted(h.colors)) + ((P.GENERIC,),) if h.kind == "convoke" else ((P.GENERIC,),)
        idx = HELPER_ABILITY[h.kind]
        if h.card in by_card:
            src = out[by_card[h.card]]
            extra = tuple(o for o in opts if o not in src.options or producer is not None
                          or (src.generic_allowed and not all(src.generic_allowed)))
            abilities = src.abilities or (0,) * len(src.options)
            out[by_card[h.card]] = M.Source(h.card, src.options + extra, sacrifice=src.sacrifice, rank=src.rank,
                                            preferred=src.preferred, abilities=abilities + (idx,) * len(extra),
                                            activation=src.activation, snow=src.snow,
                                            generic_allowed=(src.generic_allowed + (True,) * len(extra)) if src.generic_allowed else (),
                                            producer_facts=(src.producer_facts + tuple((None,) * len(opt) for opt in extra)) if src.producer_facts else (),
                                            ability_options=(src.ability_options + (-1,) * len(extra)) if src.ability_options else ())
        else:
            by_card[h.card] = len(out)
            out.append(M.Source(h.card, opts, rank=6, abilities=(idx,) * len(opts)))
    return out


# -- targets (601.2c) --------------------------------------------------------------------
# -- cancelling a cast (wave 24D) -- 601.2 / 602.2: a proposal that can't be completed is rewound to before it was made; the
# announcement choices (modes, targets) come before anything is paid or moved here, so cancelling one just ends the attempt.
def cancelled(plan: Plan, d: Any, chosen: list[str]) -> bool:
    """Did the player cancel this announcement? Then nothing was committed: priority comes back to them."""
    if chosen != ["cancel"] or not cancelable(d):
        return False
    plan.note(f"{plan.name(d.player)} cancelled")
    plan.rules.priority = d.player
    plan.hold = d.player
    return True


def _announcing(plan: Plan, step: str, a: A.CastSpell | A.ActivateAbility, **extra: Any) -> dict[str, Any]:
    """The resume of an announcement choice. -- review (wave 29B) -- ``abandon``: a free cast begun as an effect resolves whose end is
    recorded (``RulesState.free_cast_then``: permissions.free_cast_abandoned carries on, or sends the card where a card not cast goes) may be
    cancelled too (rules_state.cancelable): the way out of a cast that turns out not to be possible once its targets are chosen (601.2: its
    total cost can't be paid), which is otherwise a dead end."""
    out = {"step": step, "intent": a.model_dump(mode="json", exclude={"r", "actor", "ts"}), **extra}
    pending = plan.rules.free_cast_then
    if getattr(a, "free", False) and pending is not None and pending["card"] == a.card_id:
        out["abandon"] = True
    return out


def _target_source(plan: Plan, a: A.CastSpell | A.ActivateAbility) -> Characteristics | None:
    if isinstance(a, A.CastSpell):
        return source_of(plan, a.card_id, True, x=a.x_value or 0, face=a.face, fused=a.fuse)
    return source_of(plan, a.card_id)


def choose_target(plan: Plan, a: A.CastSpell | A.ActivateAbility, definition: dict[str, Any] | None,
                  what: str, *, exclude: tuple[str, ...] = ()) -> list[TargetRef] | None:
    """The target of an automated spell or ability: validated if given, else asked (privately).
    Returns the chosen targets, or None while waiting for the choice."""
    spec = definition.get("target") if definition else None
    if not spec:
        return []
    legal = [t for t in legal_targets(plan, spec["what"], plan.actor, _target_source(plan, a), a.card_id)
             if t not in exclude]  # (wave 49C: a spell's targeting, 115.2)
    from app.rules import flagbearer86

    legal = flagbearer86.single(plan, legal)
    if a.targets:
        if len(a.targets) != 1 or a.targets[0] not in legal:
            raise ActionError("That isn't a legal target")
        return [target_ref(plan, a.targets[0])]
    if not legal:
        raise ActionError(f"{what} has no legal target")
    decide(plan, player=plan.actor, kind="choose_one", prompt=f"Choose a target for {what}",
           options=[DecisionOption(id=x, label=target_label(plan, x), card_id=x if x in plan.state.cards else None) for x in legal],
           resume=_announcing(plan, "cast_target", a))
    return None


@dataclass
class ChosenTargets:
    """The targets of a spell or ability as it's put on the stack: all of them (``flat``), and for
    one with target groups, each group's and each divided group's division (601.2c-d)."""

    flat: list[TargetRef]
    groups: list[list[TargetRef]] | None = None
    specs: list[dict[str, Any]] | None = None
    division: list[list[int]] | None = None

    def entry(self, definition: dict[str, Any] | None) -> dict[str, Any]:
        """The StackEntry fields for them."""
        if self.specs is None:
            return {"targets": self.flat, "target_spec": (definition or {}).get("target")}
        return {"targets": self.flat, "target_spec": None, "groups": self.groups, "group_specs": self.specs,
                "division": self.division}


def choose_targets(plan: Plan, a: A.CastSpell | A.ActivateAbility, definition: dict[str, Any] | None, what: str,
                   *, exclude: tuple[str, ...] = ()) -> ChosenTargets | None:
    """All targets of an automated spell or ability (601.2c-d): one plain "target", or target
    groups. None while waiting for a choice."""
    if definition and definition.get("delegated_target"):
        from app.rules import delegated_target_announcements

        if delegated_target_announcements.handles(definition):
            return delegated_target_announcements.announce(plan, a, definition, what)
        raise ActionError("Unsupported delegated target announcement")
    plan.x_choice = getattr(a, "x_value", None)  # -- control (wave 3K) -- "creature with mana value X or less": the X announced
    if not definition or not definition.get("targets"):
        chosen = choose_target(plan, a, definition, what, exclude=exclude)
        return None if chosen is None else ChosenTargets(flat=chosen)
    specs = scripts.target_groups(definition)
    if isinstance(a, A.CastSpell):  # -- kicked / instead (wave 4G) -- 601.2c / 702.33g: targets tied to the kicker
        from app.rules import kicked_instead

        specs = kicked_instead.applicable(specs, a.kicker or int(a.awaken) or int(f"{a.card_id}:gift" in a.optional_costs) or int(f"{a.card_id}:bargain" in a.optional_costs)
                                          or int(f"{a.card_id}:teamwork" in a.optional_costs)
                                          or int(any(f"{a.card_id}:{g['optional']}" in a.optional_costs for g in specs if "optional" in g)))  # (wave 110E: Hulk's Thunderclap)  # (awaken: wave 16B; bargain: 30E; teamwork: wave 100K, aslongas100k.TEAMWORK;
        # gift: wave 23D, 702.174m: the targets only a promised spell chooses)
    from app.rules import flagbearer86

    found = choose_groups(plan, specs, plan.actor, _target_source(plan, a), a.card_id, list(a.targets),  # (review 41: 115.2)
                          list(a.target_counts), list(a.division), a.x_value, what, exclude,
                          required_any=frozenset(flagbearer86.current(plan)))
    if found.ask is not None:
        ask_targets(plan, plan.actor, found, specs, what, _announcing(plan, "cast_group", a, counts=found.counts))
        return None
    flagbearer86.enforce_groups(plan, a, specs, found, _target_source(plan, a), what, exclude)
    groups = [[target_ref(plan, t) for t in g] for g in found.groups]
    return ChosenTargets(flat=[t for g in groups for t in g], groups=groups, specs=specs, division=found.division)


def ask_targets(plan: Plan, player: str, found: Any, specs: list[dict[str, Any]], what: str, resume: dict[str, Any]) -> None:
    """The next missing choice of a spell or ability with target groups, asked privately: a
    group's targets (601.2c), or a division (601.2d; answered with amounts, one per target)."""
    many = len(specs) > 1
    if found.ask[0] == "group":
        _, g, options, lo, hi = found.ask
        count = str(lo) if lo == hi else f"up to {hi}" if lo == 0 else f"{lo} to {hi}"
        cut = f" (the rules allow up to {found.capped}, but at most {hi} targets can be chosen at once)" if found.capped else ""  # (wave 29C)
        decide(plan, player=player, kind="choose_cards",
               prompt=f"Choose {count} target{'s' if hi != 1 else ''} for {what}" + (f" (group {g + 1} of {len(specs)})" if many else "") + cut,
               options=[DecisionOption(id=x, label=target_label(plan, x), card_id=x if x in plan.state.cards else None)
                        for x in options],
               min_choices=lo, max_choices=hi, resume=resume)
        return
    _, g, total = found.ask
    chosen = found.groups[g]
    noun = "damage" if specs[g]["divide"]["what"] == "damage" else "counters"
    decide(plan, player=player, kind="divide", prompt=f"Divide {total} {noun} among the targets of {what} (at least 1 each)",
           options=[DecisionOption(id=x, label=target_label(plan, x), card_id=x if x in plan.state.cards else None)
                    for x in chosen],
           min_choices=len(chosen), max_choices=len(chosen), display={"kind": "divide", "total": total, "what": noun},
           resume={**resume, "step": resume["step"].replace("group", "divide"), "total": total})


def resume_cast_group(plan: Plan, d: Any, chosen: list[str]) -> None:
    if cancelled(plan, d, chosen):
        return
    from app.rules.engine import INTENTS  # the engine imports this module

    intent = A.parse_action(d.resume["intent"])
    intent.targets = [*intent.targets, *chosen]  # type: ignore[union-attr]
    intent.target_counts = [*d.resume["counts"], len(chosen)]  # type: ignore[union-attr]
    plan.rules.priority = d.player
    plan.rules.passed = []
    INTENTS[intent.type](plan, intent)


def resume_cast_divide(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules.engine import INTENTS  # the engine imports this module

    intent = A.parse_action(d.resume["intent"])
    intent.division = [*intent.division, *(int(c) for c in chosen)]  # type: ignore[union-attr]
    plan.rules.priority = d.player
    plan.rules.passed = []
    INTENTS[intent.type](plan, intent)


def _instead_holds(plan: Plan, a: A.CastSpell | A.ActivateAbility, cond: dict[str, Any]) -> bool:
    """-- modal frames (wave 33B) -- the condition of "Choose one. If …, choose both instead.", as the spell is cast (601.2b): whether it was
    kicked (702.33d) or cast using teamwork (702.194b) is what is announced now, anything else is read off the table."""
    if (how := cond.get("cast")) is not None:
        return isinstance(a, A.CastSpell) and (bool(a.kicker) if "kicked" in how else f"{a.card_id}:{how['optional']}" in a.optional_costs)
    from app.rules import conditions

    return conditions.holds(plan, {"controller": plan.actor, "source_card": a.card_id, "source_object": plan.oid(a.card_id)}, cond)


def modal_groups(definition: dict[str, Any], picked: list[int]) -> list[dict[str, Any]] | None:
    """-- static_other sweep (wave 16B) -- a modal spell with a mode that has several target groups (or "up to N", or a division)
    chooses its targets as one list of groups, each chosen mode's after the one before it (601.2c); None when every chosen mode has at
    most one plain target (each mode's own slot, ``choose_slot_targets``)."""
    modes = [definition["modes"][i] for i in picked]
    if not any(m.get("groups") for m in modes):
        return None
    out: list[dict[str, Any]] = []
    for m in modes:
        base = len(out)  # (-- shuffle target cards (wave 46B) -- a mode's "graveyard_of" names a group of its own, numbered from its first)
        out += [{**g, "graveyard_of": g["graveyard_of"] + base} if g.get("graveyard_of") is not None else
                {**g, "of": g["of"] + base} if g.get("of") is not None else g  # (-- player-relative selectors (wave 53A) --)
                for g in m.get("groups") or ([{"what": m["target"]["what"]}] if m["target"] else [])]
    return out


def modal_effects(definition: dict[str, Any], picked: list[int], grouped: bool) -> list[dict[str, Any]]:
    """The chosen modes' effects in printed order (608.2c): each with its own target slot, or (``grouped``) with its target words
    renumbered to the spell's groups."""
    out: list[dict[str, Any]] = []
    offset = 0
    for k, i in enumerate(picked):
        mode = definition["modes"][i]
        if not grouped:
            out += [{"do": "use_targets", "slot": k}, *mode["effects"]]
            continue
        n = len(mode.get("groups") or ([mode["target"]] if mode["target"] else []))
        out += scripts._renumber(mode["effects"], list(range(offset, offset + n))) if n else mode["effects"]
        offset += n
    return out + list(definition.get("after") or ())  # -- wave 110A -- lines printed after the modes (scripts.modal_definition)


def choose_modes(plan: Plan, a: A.CastSpell | A.ActivateAbility, definition: dict[str, Any], what: str,
                 *, exclude: tuple[int, ...] = ()) -> list[int] | None:
    """700.2a / 601.2b: the modes of a modal spell (or activated ability: 602.2b), validated if given,
    else asked. A mode whose target can't be chosen can't be chosen (700.2a). ``exclude``: modes that
    can't be chosen either ("choose one that hasn't been chosen"). Returns None while waiting."""
    modal, modes = definition["modal"], definition["modes"]
    plan.x_choice = getattr(a, "x_value", None)  # -- most-played modal spells (wave 50I) -- 601.2b: X is announced before the modes; a mode's "creature with mana value X or less" reads it
    lo, hi, repeat = modal["min"], modal["max"], modal["repeat"]
    allowed = choosable_modes(plan, definition, a.card_id, exclude, isinstance(a, A.CastSpell), source=_target_source(plan, a))
    if (inst := modal.get("instead")) is not None and _instead_holds(plan, a, inst["cond"]):
        # -- modal frames (wave 33B) -- 700.2a, 601.2b: "If [condition] as you cast this spell, [you may] choose both instead." — judged as the
        # modes are chosen; a "both" the table can't give (a mode with no legal target, 700.2a) is not cast that way
        lo, hi = inst["min"], inst["max"]
        if len(allowed) < lo:
            raise ActionError(f"{what} can't have {lo} modes chosen (a mode has no legal target)")
    if a.modes or (lo == 0 and isinstance(a, A.CastSpell) and plan.locked_zero_modes == plan.oid(a.card_id)):
        if (w := modal.get("weights")) is not None and sum(w[i] for i in a.modes if 0 <= i < len(w)) > modal["budget"]:  # -- most-played modal spells (wave 50I) -- the Seasons' pawprints
            raise ActionError(f"The modes you chose add up to more than {modal['budget']} pawprints")
        if not lo <= len(a.modes) <= hi:
            raise ActionError(f"Choose {lo if lo == hi else f'{lo} to {hi}'} mode{'s' if hi > 1 else ''} for {what}")
        if not repeat and len(set(a.modes)) != len(a.modes):
            raise ActionError("You can't choose the same mode more than once")
        if any(i in exclude for i in a.modes):
            raise ActionError("That mode has already been chosen")
        if any(i not in allowed for i in a.modes):
            raise ActionError("That mode can't be chosen (it has no legal target)")
        return list(a.modes)
    if not allowed or (not repeat and len(allowed) < lo):
        raise ActionError(f"{what} has no mode you can choose")
    per = hi if repeat else 1  # "You may choose the same mode more than once": each mode offered N times
    decide(plan, player=plan.actor, kind="choose_cards",
           prompt=f"Choose {lo if lo == hi else f'{lo} to {hi}'} mode{'s' if hi > 1 else ''} for {what}",
           options=[DecisionOption(id=f"{i}:{k}", label=modes[i]["text"][:120]) for i in allowed for k in range(per)],
           min_choices=lo, max_choices=hi, resume=_announcing(plan, "cast_modes", a))
    return None


def choosable_modes(plan: Plan, definition: dict[str, Any], card_id: str | None, exclude: tuple[int, ...] = (), spell: bool = False,
                    *, source: Characteristics | None = None) -> list[int]:
    """700.2a: the modes ``plan.actor`` can choose for this spell / ability now (each target it requires can be chosen; ``spell``: 115.2)."""
    src = source if source is not None else source_of(plan, card_id, spell)
    return [i for i, m in enumerate(definition["modes"]) if i not in exclude
            and (not m["target"] or legal_targets(plan, m["target"]["what"], plan.actor, src, card_id))
            and all(len(legal_targets(plan, g["what"], plan.actor, src, card_id)) >= g.get("min", 1)  # (several groups: wave 16B)
                    for g in m.get("groups") or ())]


def resume_cast_modes(plan: Plan, d: Any, chosen: list[str]) -> None:
    if cancelled(plan, d, chosen):
        return
    from app.rules.engine import INTENTS  # the engine imports this module

    intent = A.parse_action(d.resume["intent"])
    intent.modes = [int(c.split(":")[0]) for c in chosen]  # type: ignore[union-attr]
    if not chosen and isinstance(intent, A.CastSpell):
        plan.locked_zero_modes = plan.oid(intent.card_id)
    plan.rules.priority = d.player
    plan.rules.passed = []
    INTENTS[intent.type](plan, intent)


def choose_slot_targets(plan: Plan, a: A.CastSpell | A.ActivateAbility, specs: list[dict[str, Any] | None],
                        what: str) -> list[list[TargetRef]] | None:
    """One target per chosen mode that has one, in order (``a.targets``); the next one missing is
    asked. The same object may be chosen for different modes (601.2c: another "target" word)."""
    need = [k for k, spec in enumerate(specs) if spec]
    if len(a.targets) > len(need):
        raise ActionError("Too many targets for the chosen modes")
    src = _target_source(plan, a)
    out: list[list[TargetRef]] = [[] for _ in specs]
    for n, k in enumerate(need):
        spec = specs[k]
        assert spec is not None
        legal = legal_targets(plan, spec["what"], plan.actor, src, a.card_id)
        if len(need) == 1:
            from app.rules import flagbearer86

            legal = flagbearer86.single(plan, legal)
        if n < len(a.targets):
            if a.targets[n] not in legal:
                raise ActionError("That isn't a legal target")
            out[k] = [target_ref(plan, a.targets[n])]
            continue
        if not legal:
            raise ActionError(f"{what} has no legal target for that mode")
        decide(plan, player=plan.actor, kind="choose_one", prompt=f"Choose a target for {what} (mode {n + 1})",
               options=[DecisionOption(id=x, label=target_label(plan, x), card_id=x if x in plan.state.cards else None)
                        for x in legal],
               resume=_announcing(plan, "cast_slot_target", a))
        return None
    from app.rules import flagbearer86, targets

    selected_specs = [{**(specs[k] or {}), "min": 1, "max": 1} for k in need]
    selected = targets.GroupChoice(groups=[[t.id for t in out[k]] for k in need], counts=[1] * len(need))
    flagbearer86.enforce_groups(plan, a, selected_specs, selected, src, what, ())
    return out


def resume_cast_slot_target(plan: Plan, d: Any, chosen: list[str]) -> None:
    if cancelled(plan, d, chosen):
        return
    from app.rules.engine import INTENTS  # the engine imports this module

    intent = A.parse_action(d.resume["intent"])
    intent.targets = [*intent.targets, chosen[0]]  # type: ignore[union-attr]
    plan.rules.priority = d.player
    plan.rules.passed = []
    INTENTS[intent.type](plan, intent)


def resume_target(plan: Plan, d: Any, chosen: list[str]) -> None:
    if cancelled(plan, d, chosen):
        return
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
    if pref == "self":
        return "self"
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
    # The spell's card: set only for the castability hint, which then counts convoke / improvise /
    # delve helpers too (the spell can't delve itself). Payments never treat helpers as mana.
    card: str | None = None
    spell_object: ObjectRef | None = None  # Original exact pre-cast object; never its new stack incarnation.
    # -- activated sweep (wave 17B) -- where the spell is cast from, by whom, and whether kicked ("Spend this mana only to cast
    # kicked spells", "…spells from exile"; 601.2h: the cost is paid with these locked in, 601.2a-b)
    zone: str | None = None
    player: str | None = None
    kicked: bool = False
    # -- mana provenance (wave 18B) -- does the player own the spell ("spells you don't own", Thieving Varmint)
    own: bool = True
    # -- mana provenance (wave 18B) -- the cost being paid contains {X} ("Spend this mana only on costs that contain {X}", Rosheen Meanderer)
    cost_x: bool | None = None  # Legacy printed-X heuristic; never establishes eligibility.
    # -- mana for special abilities (wave 19E) -- what else the mana pays for: "equip", "power_up" (an ability of that kind: ``ability_of``
    # is its source), "turn_up" (the cost to turn a permanent face up, 116.2b), "foretell" (116.2h)
    special: str | None = None
    x_payment: dict[str, Any] | None = None
    alternative: str | None = None
    payment_method: str | None = None
    cost_colorless: bool = False
    allocation: M.RequirementPlan | None = None
    selected_cost_has_x: bool | None = None
    producer_requirement: M.ProducerRequirement | None = None
    cycling_menu72: bool = False  # Announced cycling ability/cost menu, retained through mana preparation.


_PURPOSE = TypeAdapter(Purpose)

def _purpose_context(purpose: Purpose | None) -> dict[str, Any]:
    return ({'producer_requirement': _producer_requirement(purpose),
             'alternative':purpose.alternative, 'payment_method':purpose.payment_method,
             'selected_cost_has_x':purpose.selected_cost_has_x,
             'cycling_menu72': purpose.cycling_menu72,
             'cost_colorless':purpose.cost_colorless,
             'allocation': TypeAdapter(M.RequirementPlan).dump_python(
                 TypeAdapter(M.RequirementPlan).validate_python(purpose.allocation), mode='json')
                 if purpose.allocation is not None else None,
             'spell_object': ObjectRef.model_validate(purpose.spell_object).model_dump(mode='json')
                 if purpose.spell_object is not None else None} if purpose else {})


def _spell_reference(state: GameState, card: CardInstance) -> ObjectRef | None:
    return ObjectRef(card=card.id, object_id=state.rules.object_id(card.id), zone=card.zone) if state.rules is not None else None


def _producer_requirement(purpose: Purpose) -> M.ProducerRequirement | None:
    if purpose.producer_requirement is not None:
        return M.ProducerRequirement(purpose.producer_requirement)
    if purpose.spell is None:
        return None
    from app.rules import mana_producer_profiles45

    return mana_producer_profiles45.requirement(purpose.spell)



def _purpose_for_cost(cost: M.ManaCost, purpose: Purpose | None) -> Purpose:
    base = purpose or Purpose()
    rows = cost.allocation or base.allocation
    return replace(base, producer_requirement=_producer_requirement(base), cost_colorless=base.cost_colorless or 'C' in cost.colored,
                   spell_object=ObjectRef.model_validate(base.spell_object) if base.spell_object is not None else None,
                   allocation=TypeAdapter(M.RequirementPlan).validate_python(rows) if rows is not None else None)


def _constrained(cost: M.ManaCost, purpose: Purpose | None) -> M.ManaCost:
    from app.rules import x_mana_restrictions

    if cost.allocation is None and purpose is not None and purpose.allocation is not None:
        cost = replace(cost, allocation=TypeAdapter(M.RequirementPlan).validate_python(purpose.allocation))
    cost = x_mana_restrictions.solver_cost(cost, purpose.x_payment if purpose is not None else None)
    producer = _producer_requirement(purpose) if purpose is not None else None
    if producer is not None:
        from app.rules import mana_allocation_masks

        cost = mana_allocation_masks.constrain_producer(cost, producer)
    return cost


def _solve_with_filters(cost: M.ManaCost, pool: dict[str, int], plain: list[M.Source], filters: list[M.Source],
                        life: int, *, input_spending: Callable[[M.ManaCost], M.ManaCost] | None = None) -> M.Payment:
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
        from app.rules import mana_allocation_masks as allocation
        from app.rules.mana_requirement_rows import RequirementPlan

        activation = M.ManaCost()
        for f in combo:
            act = f.activation or M.ManaCost()
            activation = M.ManaCost(activation.generic + act.generic, activation.colored + act.colored,
                                    activation.hybrid + act.hybrid, allocation=RequirementPlan(
                                        allocation.requirements(activation).generic + allocation.requirements(act).generic,
                                        allocation.requirements(activation).symbols + allocation.requirements(act).symbols,
                                        allocation.requirements(activation).phyrexian + allocation.requirements(act).phyrexian))
        matching_activation = input_spending(activation) if input_spending is not None else activation
        others = [s for s in plain if s.card_id not in {f.card_id for f in combo}]
        try:
            M.solve(matching_activation, pool, others, life=life)  # the filters can't pay for themselves
        except M.ManaError:
            continue
        free = [replace(f, activation=None) for f in combo]
        # Name the generic activation inputs explicitly. Otherwise an aggregate
        # solution can use the filter's output to fund its own activation, or
        # spend a Forest needed by the spell instead of an available Island.
        for colors in islice(product(M.ALL_MANA, repeat=activation.generic), M.MAX_SEARCH):
            total = M.ManaCost(cost.generic, cost.colored + matching_activation.colored + colors,
                               cost.hybrid + matching_activation.hybrid, cost.phyrexian, 0, cost.unsupported)
            base_rows = allocation.requirements(cost)
            assigned_rows = allocation.assign_generic_encoding(matching_activation, colors)
            total = replace(total, allocation=RequirementPlan(base_rows.generic + assigned_rows.generic,
                base_rows.symbols + assigned_rows.symbols, base_rows.phyrexian + assigned_rows.phyrexian))
            try:
                payment = M.solve(total, pool, others + free, life=life)
                fixed = {cid: option for cid, option in payment.slots}
                selected = dict(payment.selected_options)
                inputs = []
                for src in others:
                    if src.card_id not in fixed:
                        continue
                    if src.card_id not in selected:
                        raise M.ManaError('The selected source option has unknown history')
                    index = selected[src.card_id]
                    inputs.append(replace(src, options=(fixed[src.card_id],),
                        abilities=(src.abilities[index],) if src.abilities else (),
                        generic_allowed=(src.generic_allowed[index],) if src.generic_allowed else (),
                        producer_facts=(src.producer_facts[index],) if src.producer_facts else (),
                        ability_options=(src.ability_options[index],) if src.ability_options else ()))
                constrained = M.ManaCost(0, matching_activation.colored + colors, matching_activation.hybrid, allocation=assigned_rows)
                M.solve(constrained, pool, inputs, life=life)
            except M.ManaError:
                continue
            indices = dict(payment.used)
            filter_ids = {f.card_id for f in combo}
            assigned: dict[str, M.ManaCost] = {}
            offset = 0
            for f in combo:
                act = f.activation or M.ManaCost()
                assigned[f.card_id] = M.ManaCost(0, act.colored + colors[offset:offset + act.generic], act.hybrid)
                assigned[f.card_id] = replace(assigned[f.card_id], allocation=allocation.assign_generic_encoding(
                    act, colors[offset:offset + act.generic]))
                offset += act.generic
            payment.filters = [(cid, indices[cid], option, assigned[cid]) for cid, option in payment.slots
                               if cid in filter_ids and cid in indices]
            return payment
    raise error


def find_payment(state: GameState, player: str, cost: M.ManaCost, info: CardInfo, *,
                 sources: list[str] | None = None, exclude: tuple[str, ...] = (), purpose: Purpose | None = None,
                 reserve: int = 0) -> M.Payment:
    """How to pay ``cost``: with exactly ``sources`` when given (MANUAL PAY), else automatically,
    PREFER sources first and SAVE sources only when there is no other way. Pool units that may pay for ``purpose`` (restricted or
    remembered mana, app/rules/mana_units.py) are spent like pool mana: ``Payment.slots`` names them ("unit:<id>"), ``tapped`` doesn't."""
    purpose = _purpose_for_cost(cost,purpose)
    if purpose.allocation is not None and cost.allocation is None:
        cost = replace(cost, allocation=purpose.allocation)
    try:
        payment = _find_payment(state, player, _constrained(_spending_cost(state, player, info, life_for_mana(state, player, info, cost)), purpose), info, sources=sources, exclude=exclude,
                                purpose=purpose, reserve=reserve)
    except ActionError as exc:
        if purpose.producer_requirement is not None:
            producer = ('creatures on the battlefield' if purpose.producer_requirement is M.ProducerRequirement.CREATURE_PERMANENT
                        else 'Treasures' if purpose.producer_requirement is M.ProducerRequirement.TREASURE_PERMANENT else 'basic lands')
            unknown = bool(state.players[player].mana) or any(unit.production_zone is None
                for unit in state.players[player].mana_units)
            detail = " Mana of unknown origin can't pay this cost." if unknown else ''
            raise ActionError(f'Spend only mana produced by {producer} to cast this spell.{detail}') from exc
        if purpose.x_payment:
            raise ActionError(f"Not enough legal mana to pay {cost.text()} with its restriction on X") from exc
        raise
    payment.tapped = [c for c in payment.tapped if not c.startswith("unit:")]
    return payment


LIFE_FOR_MANA = "For each {B} in a cost, you may pay 2 life rather than pay that mana."


def _life_locked(state: GameState, info: CardInfo | None, player: str, amount: int) -> bool:
    """-- can't lose life (wave 29D) -- 119.8, 614.17b: ``amount`` life (more than 0) can't be paid by a player who can't lose life."""
    from app.rules import life_lock

    return life_lock.pay_problem(state, info, player, amount) is not None


def spendable_life(state: GameState, player: str, info: CardInfo | None) -> int:
    """-- prohibitions (wave 22B) -- the life that may pay Phyrexian mana: none while "players can't pay life" (119.4, 614.17)."""
    from app.rules import life_lock, prohibitions

    # (-- can't lose life (wave 29D) -- 119.8, 614.17b: nor while this player can't lose life)
    return 0 if prohibitions.life_banned(state, info) or life_lock.why_not_state(state, info, player, "lose") else state.players[player].life


def life_for_mana(state: GameState, player: str, info: CardInfo, cost: M.ManaCost) -> M.ManaCost:
    """-- mana provenance (wave 18B) -- K'rrik, Son of Yawgmoth: "For each {B} in a cost, you may pay 2 life rather than pay that mana."
    Each {B} of the cost becomes a Phyrexian {B/P} while its controller has one (the solver pays mana first and life only where
    mana can't, one symbol at a time; a hybrid {B/…} isn't a {B}, left as it is)."""
    from app.rules.layers import derive

    if "B" not in cost.colored:
        return cost
    for z, ids in state.zones.items():
        if z.endswith(":battlefield"):
            for cid in ids:
                c = state.cards[cid]
                printed = chars.of(c, info)  # (review 18B: its current abilities: not once it lost them, 613.1f)
                if c.controller == player and LIFE_FOR_MANA in printed.oracle_text and \
                        any(ab.text == LIFE_FOR_MANA for ab in derive(state, c, printed, info).abilities):
                    n = cost.colored.count("B")
                    rows = cost.allocation
                    if rows is not None:
                        actual_black = [row for row in rows.symbols if not row.generic and row.alternatives == ('B',)]
                        n = min(n, len(actual_black))
                        if not n:
                            return cost
                        left = list(rows.symbols)
                        for row in actual_black[:n]:
                            left.remove(row)
                        colors = list(cost.colored)
                        for _ in range(n):
                            colors.remove('B')
                        return M.ManaCost(cost.generic, tuple(colors), cost.hybrid, cost.phyrexian + ('B',) * n,
                            cost.x, cost.unsupported, replace(rows, symbols=tuple(left), phyrexian=rows.phyrexian + tuple(actual_black[:n])))
                    return M.ManaCost(cost.generic, tuple(x for x in cost.colored if x != "B"), cost.hybrid, cost.phyrexian + ("B",) * n,
                                      cost.x, cost.unsupported)
    return cost


def _find_payment(state: GameState, player: str, cost: M.ManaCost, info: CardInfo, *,
                  sources: list[str] | None = None, exclude: tuple[str, ...] = (), purpose: Purpose | None = None,
                  reserve: int = 0) -> M.Payment:
    from app.rules import mana_units

    everything = [s for s in mana_sources(state, player, info, purpose) if s.card_id not in exclude]
    available = [s for s in everything if s.activation is None]
    filters = [s for s in everything if s.activation is not None]
    pool = dict(state.players[player].mana)
    life = max(0, spendable_life(state, player, info) - reserve)  # (wave 22B: 119.4; wave 29C: less the life other costs of it pay)
    units = mana_units.unit_sources(state, player, purpose)  # -- mana provenance (wave 18B) -- pool mana that remembers its source
    if sources is not None:
        chosen = [s for s in available if s.card_id in set(sources)]
        chosen_filters = [s for s in filters if s.card_id in set(sources) and s.card_id not in {c.card_id for c in chosen}]
        if len({s.card_id for s in chosen + chosen_filters}) != len(set(sources)):
            raise ActionError("Pick untapped mana sources you control")
        try:
            payment = _solve_with_filters(cost, pool, chosen + units, chosen_filters, life, input_spending=lambda due: _spending_cost(state, player, info, due))
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
        return _solve_with_filters(cost, pool, normal + units, normal_filters, life, input_spending=lambda due: _spending_cost(state, player, info, due))
    except M.ManaError:
        pass
    try:
        return _solve_with_filters(cost, pool, marked + units, filters, life, input_spending=lambda due: _spending_cost(state, player, info, due))  # SAVE sources only when nothing else works
    except M.ManaError as exc:
        raise ActionError(f"{exc}. Tap mana yourself first, or use the table tools.") from exc


def mana_ability_extras(plan: Plan, card: CardInstance, index: int) -> tuple[int, list[tuple[str, int]]]:
    """Life to pay and counters to remove for using mana ability ``index`` (besides tapping)."""
    ability = dict(mana_abilities(plan.state, card, plan.info)).get(index)
    if ability is None or not ability.extra_cost:
        return 0, []
    extra = parse_ability_cost(ability.extra_cost, card_name=plan.ch(card).name)
    return extra.life, list(extra.remove_counters)


def after_mana_ability(plan: Plan, card: CardInstance, index: int, ability: M.ManaAbility, who: str | None = None,
                       *, source_object: str | None = None, then: dict[str, Any] | None = None,
                       option: tuple[str, ...] = (), mana_context: dict[str, Any] | None = None) -> bool:
    """Riders and bookkeeping once a mana ability was used: "deals 1 damage to you", "Draw a
    card", once-per-turn marks, counters removed as a cost. ``who``: the player who activated it (-- mana riders (wave 24D) -- 603.7e-style:
    a source sacrificed as the cost is back under its owner's control by now, so "you" is read before the cost)."""
    who = who or card.controller
    r = plan.rules
    restrictions.record_use(r, source_object or r.object_id(card.id), index, plan.state.turn.number)
    if ability.once_per_turn:
        r.once_per_turn[f"{r.object_id(card.id)}:{index}"] = plan.state.turn.number
    extra = parse_ability_cost(ability.extra_cost, card_name=plan.ch(card).name) if ability.extra_cost else None
    for kind, n in extra.remove_counters if extra and not (mana_context or {}).get("nonmana_cost_paid") else ():
        plan.do({"type": "counter", "card_ids": [card.id], "kind": kind, "delta": -n}, actor=card.controller)
    if extra is not None and extra.energy and not (mana_context or {}).get("nonmana_cost_paid"):  # (wave 3E: "{T}, Pay {E}: Add one mana of any color", 107.14)
        plan.do({"type": "resource", "player": card.controller, "key": "energy", "delta": -extra.energy}, actor=card.controller)
    from app.rules.triggers import activated as mana_activated

    payment_record = PaymentRecord.model_validate(mana_context['activation_payment']) if mana_context is not None and mana_context.get('activation_payment') is not None else PaymentRecord(
        card=card.id, controller=who, activation_cost_has_x='{X}' in ability.extra_cost, activation_cost_has_tap=ability.tap,
        activation_life_paid=extra.life if extra else 0)
    mana_activated(plan, card, source_object or plan.oid(card), payment=payment_record, mana_ability=True, actor=who, cost_has_tap=ability.tap)
    if ability.delayed_effects:
        from app.rules import mana_delayed_effects

        mana_delayed_effects.start(plan, card, who, source_object or plan.oid(card), ability.delayed_effects)
    if ability.immediate_effects:
        from app.rules import immediate_mana_resolutions

        return immediate_mana_resolutions.run(plan, card, index, ability, who, source_object or plan.oid(card),
                                               option, then, mana_context)
    if then is not None:
        from app.rules import payment_continuations as pc

        return pc.riders(plan, pc.ManaRiderFrame(card.model_dump(mode="json"), source_object or plan.oid(card),
                                                who, list(ability.riders), then, plan.actor, plan.reserved_life))
    from app.rules import replace as _replace_rider

    for kind, n in ability.riders:
        if kind == "damage" and _player_protected(plan, card, who):  # -- player shields (wave 5E) -- 702.16e, 702.16j
            plan.note(f"Protection prevents the damage {plan.ch(card).name} would deal to {plan.name(who)}")
        elif kind == "damage":
            mana_ability_damage(plan, card, who, n)
        elif kind == "draw":  # (review 28B: through the draw choke point like any other draw — a mana ability can't pause: then=None)
            _replace_rider.draw_cards(plan, [who], n)
        else:  # -- mana riders (wave 5A) -- "You gain 2 life.", "Each opponent gains 1 life."
            from app.rules import mana_riders

            mana_riders.after(plan, card, kind, n, who)
    return True


def mana_ability_damage(plan: Plan, card: CardInstance, who: str, n: int, *, then: dict[str, Any] | None = None,
                        source_object: str | None = None) -> bool:
    """Deal a mana ability's damage before the remaining payment continuation.

    Native live callers supply a terminal so replacement and immediate-rider choices
    suspend safely without priority. Legacy low-level callers remain synchronous.
    """
    from app.rules import effects as _effects
    from app.rules import replace as _replace

    ch = plan.ch(card)
    oid = source_object or plan.oid(card.id)
    ev = {"source_card": card.id, "source_oid": oid, "target": who, "amount": n, "combat": False,
          "src": _replace.source_info(plan, card.id, oid, ch, who), "kw": sorted(ch.keywords & _effects._DAMAGE_KEYWORDS), "lkey": card.id}
    if then is not None:
        from app.rules import damage_rider_continuations

        return damage_rider_continuations.mana_damage(plan, damage_rider_continuations.ManaDamageFrame([ev], who, then))
    out = _replace.damage_outcome(plan, [ev], answers={}, order=None, ask=False)
    if isinstance(out, _replace.DamageOutcome):
        return _replace.do_damage(plan, out, actor=who, combat=False)
    raise ActionError("This mana damage choice requires a saved payment continuation")


def _player_protected(plan: Plan, card: CardInstance, who: str) -> bool:
    """-- player shields (wave 5E) -- does the controller's protection prevent the damage this mana source deals them?"""
    from app.rules import player_shields, source_shields
    from app.rules import replace as replacements

    if player_shields.protected_from(plan, who, plan.ch(card)) is None:
        return False
    ev = {"source_card": card.id, "source_oid": plan.oid(card.id), "target": who, "combat": False,
          "src": replacements.source_info(plan, card.id, plan.oid(card.id), plan.ch(card), who)}
    return source_shields.protection_applies(plan, ev)


@dataclass
class _FilterPayment:
    player: str
    cost: M.ManaCost
    label: str
    payment: M.Payment
    exclude: tuple[str, ...]
    purpose: Purpose | None
    life_due: int
    then: dict[str, Any]
    at: int = 0
    allow_more_sources: bool = False


@dataclass
class _FilterResult:
    tapped: list[str]
    then: dict[str, Any]


def _filter_result(plan: Plan, data: _FilterResult, payment: M.Payment | None) -> None:
    from app.rules import payment_continuations as pc

    if payment is not None:
        payment.tapped = list(dict.fromkeys(data.tapped + payment.tapped))
    pc.finish(plan, data.then, payment)


def _filter_next(plan: Plan, data: _FilterPayment, payment: M.Payment | None) -> None:
    from app.rules import payment_continuations as pc

    result = _filter_run(plan, data)
    if not isinstance(result, _PaymentWaiting):
        pc.finish(plan, data.then, result)


def _filter_run(plan: Plan, data: _FilterPayment) -> M.Payment | None | _PaymentWaiting:
    from app.rules import payment_continuations as pc

    selected = set(data.payment.tapped)
    filter_ids = {cid for cid, _, _, _ in data.payment.filters}
    outside = data.exclude if data.allow_more_sources else tuple(cid for cid in plan.state.cards if cid not in selected)
    for i in range(data.at, len(data.payment.filters)):
        cid, index, option, activation_cost = data.payment.filters[i]
        card = plan.state.cards[cid]
        ability = dict(mana_abilities(plan.state, card, plan.info))[index]
        after = pc.continuation(plan, "payment_filter_next", replace(data, at=i + 1))
        if not produce(plan, card, ability, option, index, activation_exclude=outside + tuple(filter_ids),
                       activation_cost=activation_cost, then=after, option_index=dict(data.payment.ability_options).get(cid)):
            return _PAYMENT_WAITING
    remaining = [cid for cid in data.payment.tapped if cid not in filter_ids and cid in plan.state.cards
                 and not plan.state.cards[cid].tapped and plan.state.cards[cid].zone.endswith(":battlefield")]
    after = pc.continuation(plan, "payment_filter_result", _FilterResult(data.payment.tapped, data.then))
    result = _pay(plan, data.player, data.cost, data.label, sources=None if data.allow_more_sources else remaining, exclude=data.exclude,
                  purpose=data.purpose, life_due=data.life_due, then=after)
    if not isinstance(result, _PaymentWaiting) and result is not None:
        result.tapped = list(dict.fromkeys(data.payment.tapped + result.tapped))
    return result


def _pay_filters(plan: Plan, player: str, cost: M.ManaCost, label: str, payment: M.Payment,
                 exclude: tuple[str, ...], purpose: Purpose | None, life_due: int,
                 then: dict[str, Any], *, allow_more_sources: bool = False) -> M.Payment | None | _PaymentWaiting:
    return _filter_run(plan, _FilterPayment(player, cost, label, payment, exclude, purpose, life_due, then,
                                           allow_more_sources=allow_more_sources))


@dataclass
class _SequentialSource:
    source: CardInstance
    object_id: str
    index: int
    ability: M.ManaAbility
    option: tuple[str, ...]
    option_index: int | None = None


@dataclass
class _SequentialPayment:
    player: str
    cost: M.ManaCost
    label: str
    payment: M.Payment
    sources: list[_SequentialSource]
    exclude: tuple[str, ...]
    purpose: Purpose | None
    life_due: int
    source_life: int
    then: dict[str, Any]
    at: int = 0
    allow_more_sources: bool = False


def _sequential_merge(data: _SequentialPayment, payment: M.Payment | None) -> M.Payment | None:
    if payment is not None:
        payment.tapped = list(dict.fromkeys(data.payment.tapped + payment.tapped))
        payment.sacrificed = list(dict.fromkeys(data.payment.sacrificed + payment.sacrificed))
        payment.used = list(dict.fromkeys(data.payment.used + payment.used))
        payment.life += data.source_life
        payment.auxiliary_life += data.source_life
    return payment


def _sequential_result(plan: Plan, data: _SequentialPayment, payment: M.Payment | None) -> None:
    from app.rules import payment_continuations as pc

    pc.finish(plan, data.then, _sequential_merge(data, payment))


def _sequential_next(plan: Plan, data: _SequentialPayment, payment: M.Payment | None) -> None:
    from app.rules import payment_continuations as pc

    result = _sequential_run(plan, data)
    if not isinstance(result, _PaymentWaiting):
        pc.finish(plan, data.then, result)


def _sequential_run(plan: Plan, data: _SequentialPayment) -> M.Payment | None | _PaymentWaiting:
    from app.rules import payment_continuations as pc

    for i in range(data.at, len(data.sources)):
        source = data.sources[i]
        card = plan.state.cards.get(source.source.id)
        if card is None or plan.oid(card) != source.object_id or not card.zone.endswith(":battlefield"):
            raise ActionError("A chosen mana source is no longer on the battlefield")
        after = pc.continuation(plan, "sequential_mana_next", replace(data, at=i + 1))
        if not produce(plan, card, source.ability, source.option, source.index, then=after, option_index=source.option_index):
            return _PAYMENT_WAITING
    after = pc.continuation(plan, "sequential_mana_result", data)
    result = _pay(plan, data.player, data.cost, data.label, sources=None if data.allow_more_sources else [], exclude=data.exclude,
                  purpose=data.purpose, life_due=data.life_due, then=after)
    return result if isinstance(result, _PaymentWaiting) else _sequential_merge(data, result)


class _PaymentWaiting:
    pass


_PAYMENT_WAITING = _PaymentWaiting()


def pay(plan: Plan, player: str, cost: M.ManaCost, label: str, *, sources: list[str] | None = None,
        exclude: tuple[str, ...] = (), purpose: Purpose | None = None, life_due: int = 0) -> M.Payment | None:
    result = _pay(plan, player, cost, label, sources=sources, exclude=exclude, purpose=purpose, life_due=life_due)
    assert not isinstance(result, _PaymentWaiting)
    return result


def pay_then(plan: Plan, player: str, cost: M.ManaCost, label: str, *, then: dict[str, Any],
             sources: list[str] | None = None, exclude: tuple[str, ...] = (), purpose: Purpose | None = None,
             life_due: int = 0) -> None:
    from app.rules import payment_continuations as pc

    result = _pay(plan, player, cost, label, sources=sources, exclude=exclude, purpose=purpose,
                  life_due=life_due, then=then)
    if not isinstance(result, _PaymentWaiting):
        pc.finish(plan, then, result)


def _pay(plan: Plan, player: str, cost: M.ManaCost, label: str, *, sources: list[str] | None = None,
        exclude: tuple[str, ...] = (), purpose: Purpose | None = None, life_due: int = 0, then: dict[str, Any] | None = None) -> M.Payment | None | _PaymentWaiting:
    """``life_due``: -- phyrexian mana (wave 50B) -- the life announced for Phyrexian symbols (601.2b), paid with the rest; it is already in ``plan.reserved_life``."""
    purpose = _purpose_for_cost(cost, purpose)
    if cost.is_free and not sources and not life_due:
        return None
    payment = find_payment(plan.state, player, cost, plan.info, sources=sources, exclude=exclude, purpose=purpose,
                           reserve=plan.reserved_life)
    from app.rules import mana_sunglasses49

    live_spending = mana_sunglasses49.present(plan.state, player, plan.info)
    if live_spending and then is None and payment.filters:
        raise ActionError('Activate these mana sources before paying this cost')
    if payment.filters and then is not None:
        return _pay_filters(plan, player, cost, label, payment, exclude, purpose, life_due, then,
                            allow_more_sources=live_spending and sources is None)
    if payment.filters:
        # Filter inputs pay a mana ability, not the spell/ability whose payment
        # requested the filter (106.4). Execute those payments separately: their
        # source history, snow and spend riders must not leak into this record.
        selected = set(payment.tapped)
        filter_ids = {cid for cid, _, _, _ in payment.filters}
        outside = tuple(cid for cid in plan.state.cards if cid not in selected)
        for cid, index, option, activation_cost in payment.filters:
            card = plan.state.cards[cid]
            filter_ability = dict(mana_abilities(plan.state, card, plan.info))[index]
            produce(plan, card, filter_ability, option, index,
                    activation_exclude=outside + tuple(filter_ids), activation_cost=activation_cost, option_index=dict(payment.ability_options).get(cid))
        remaining = [cid for cid in payment.tapped if cid not in filter_ids and cid in plan.state.cards
                     and not plan.state.cards[cid].tapped
                     and plan.state.cards[cid].zone.endswith(":battlefield")]
        result = pay(plan, player, cost, label, sources=remaining, exclude=exclude,
                     purpose=purpose, life_due=life_due)
        if result is not None:
            result.tapped = list(dict.fromkeys(payment.tapped + result.tapped))
        return result
    extras: list[tuple[CardInstance, int, M.ManaAbility]] = []
    life = payment.life + life_due
    for cid, index in payment.used:
        card = plan.state.cards[cid]
        ability = dict(mana_abilities(plan.state, card, plan.info)).get(index)
        if ability is None:
            continue
        extras.append((card, index, ability))
        if ability.extra_cost:
            life += parse_ability_cost(ability.extra_cost, card_name=plan.ch(card).name).life
    # -- life payments (wave 29C) -- 119.4: all the life this payment takes (Phyrexian mana, "Pay 1 life" mana abilities) and the spell's other
    # life costs together can't be more than the life total (each source was checked on its own when it was listed): refused, not carried out
    if life > max(0, plan.state.players[player].life - plan.reserved_life + life_due) and life > payment.life + life_due:  # (the true total: Karn's Sylex bans only spells')
        raise ActionError(f"Those sources would take {life} life to pay {cost.text()}, and you can't pay more life than you have (119.4): "
                          "tap other sources")
    if live_spending and extras and then is None:
        raise ActionError('Activate these mana sources before paying this cost')
    if then is not None and (live_spending and bool(extras) or any(ab.immediate_effects or any(kind == "draw" for kind, _ in ab.riders) or (ab.extra_cost and parse_ability_cost(ab.extra_cost, card_name=plan.ch(source).name).life > 0) for source, _, ab in extras)):
        # Mana abilities finish in 601.2g before the spell's mana is spent in
        # 601.2h. In particular, source two cannot activate during source one's
        # replacement draw choice, and later costs cannot consume its cards yet.
        options = dict(payment.slots)
        sequence = [_SequentialSource(card, plan.oid(card), index, ab, options[card.id], dict(payment.ability_options).get(card.id)) for card, index, ab in extras]
        data = _SequentialPayment(player, cost, label, payment, sequence, exclude, purpose, life_due,
                                  life - payment.life - life_due, then, allow_more_sources=live_spending and sources is None)
        return _sequential_run(plan, data)
    oids = {card.id: plan.oid(card) for card, _, _ in extras}  # (wave 5A: the objects as they were tapped)
    from app.rules import mana_units

    pool = mana_units.settle(plan, player, payment)  # -- mana provenance (wave 18B) -- units spent / left over, what the mana was
    # A computed cost can exceed one table action's plain-pool delta bound.
    # Keep source changes and unit provenance together once; only split spending.
    large_pool_spend: dict[str, int] = {sym: n + 1000 for sym, n in pool["delta"].items() if n < -1000}
    pool["delta"] = {sym: max(-1000, n) for sym, n in pool["delta"].items()}
    plan.do({"type": "rules_mana", "player": player, "tap": payment.tapped, "sacrifice": payment.sacrificed, "life": 0,
             "label": label, **pool}, actor=player)
    while large_pool_spend:
        part_spend = {sym: max(-1000, n) for sym, n in large_pool_spend.items()}
        plan.do({"type": "rules_mana", "player": player, "delta": part_spend, "label": label}, actor=player)
        large_pool_spend = {sym: n - part_spend[sym] for sym, n in large_pool_spend.items() if n != part_spend[sym]}
    if life:  # -- life modifiers (wave 28B) -- 119.4 / 118.11: the life paid is a life loss the replacements may change
        from app.rules import replace as _replace_life

        _replace_life.lose_life(plan, [(player, life)], actor=player)
    payment.auxiliary_life += max(0, life - payment.life - life_due)
    payment.life = life
    if then is not None:
        from app.rules import payment_continuations as pc

        frame = pc.PaymentRiderFrame(player, payment,
                                    [pc.PaidManaSource(c.model_dump(mode="json"), oids[c.id], i, ab) for c, i, ab in extras], then)
        return payment if pc.payment_riders(plan, frame) else _PAYMENT_WAITING
    for card, index, ability in extras:
        # -- mana riders (wave 5A) -- counter "tap": tapped for mana (106.12a: an ability with {T} in its cost)
        emit(plan.state, "mana_added", object_id=oids[card.id], card=card.id, player=player,
             counter="tap" if ability.tap else None)
        after_mana_ability(plan, card, index, ability, player, source_object=oids[card.id])
    payment.life = life
    return payment


def _auto_helpers(plan: Plan, cost: M.ManaCost, spell: Characteristics, spell_card: str, purpose: Purpose) -> list[P.Helper]:
    """The engine pays (AUTO/ASK — tests and the sandbox payer): use convoke / improvise / delve
    only when mana alone can't pay, choosing them with the castability solver."""
    state, player = plan.state, plan.actor
    purpose = _purpose_for_cost(cost,purpose)
    if not helper_kinds(spell, state, player, spell_card, plan.info) or can_pay(state, player, cost, plan.info,
                                                                               purpose=purpose):
        return []
    plain = [s for s in mana_sources(state, player, plan.info, purpose) if s.activation is None]
    try:
        found = M.solve(_constrained(_spending_cost(state, player, plan.info, life_for_mana(state, player, plan.info, cost)), purpose), dict(state.players[player].mana),
                        _helper_sources(state, player, plan.info, spell, spell_card, plain), life=spendable_life(state, player, plan.info))
    except M.ManaError:
        return []
    kinds = {v: k for k, v in HELPER_ABILITY.items()}
    return helpers_for(state, player, plan.info, spell, spell_card,
                       [{"kind": kinds[i], "card": cid} for cid, i in found.used if i < 0])


def _pay_spell(plan: Plan, a: A.CastSpell, card: CardInstance, ch: Characteristics, cost: M.ManaCost,
              label: str, *, not_mana: tuple[str, ...] = (), origin: str | None = None, then: dict[str, Any] | None = None, x_payment: dict[str, Any] | None = None,
              payment_context: dict[str, Any] | None = None) -> PaymentRecord | None:
    """601.2h: pay a spell's locked-in total cost — the convoke / improvise / delve contributions
    (each paying one symbol, 702.51a / 702.126a / 702.66a) and mana for everything else — all at
    once. Returns how it was paid; contributions are not mana spent."""
    player = plan.actor
    # (wave 17B: origin: before the stack; wave 18B: the spell's mana value with the X it was announced with, 202.3e, and who owns it)
    spell_ch = replace(ch, mana_value=ch.mana_value + (a.x_value or 0) * ch.mana_cost.count("{X}")) if a.x_value else ch
    kick = kicker_cost(ch.abilities) if a.kicker else None  # (an entwined spell isn't kicked: review 18E)
    purpose = Purpose(spell=spell_ch, zone=origin or card.zone, player=player,
                      kicked=bool(a.kicker) and not (kick is not None and kick.entwine), own=card.owner == player,
                      x_payment=x_payment, **(payment_context or {}))
    if a.contributions:
        helpers = helpers_for(plan.state, player, plan.info, ch, card.id, [c.model_dump() for c in a.contributions])
    elif a.sources is None and payment_mode(plan, player) != "self":
        helpers = _auto_helpers(plan, cost, ch, card.id, purpose)
    else:
        helpers = []
    if any(h.card in not_mana for h in helpers):  # (wave 3$) an object an additional cost uses can't also help pay
        raise ActionError("A permanent that pays the additional cost can't also convoke / improvise")
    exclude = tuple(h.card for h in helpers) + not_mana
    from app.rules import static_perm100d  # -- static permanents (wave 100D) -- Hogaak: no mana at all

    manaless = static_perm100d.no_mana(ch)

    def covers(rest: M.ManaCost) -> bool:
        if rest.is_free:
            return True
        if manaless:
            return False
        try:
            find_payment(plan.state, player, rest, plan.info, sources=a.sources, exclude=exclude, purpose=purpose,
                         reserve=plan.reserved_life)
        except ActionError:
            return False
        return True

    assignment = P.assign(cost, helpers, covers) if helpers else []
    if manaless and (assignment is None or not P.remaining(cost, assignment).is_free):
        raise ActionError(f"You can't spend mana to cast {ch.name or 'this spell'}: pay it all with convoke and delve")
    if assignment is None:
        raise ActionError(f"Those can't pay {cost.text()}: convoke pays {{1}} or one mana of the creature's color; "
                          "improvise and delve pay only {1}")
    if then is not None and x_payment and x_payment.get('attribute_black') and x_payment.get('black') is None:
        frame = _XAllocation(player, cost, label, a.sources, exclude, purpose, 2*len(a.life_symbols or ()),
                             then, a, card.id, ch, not_mana, origin)
        _offer_x_allocation(plan, frame, helpers)
        return None
    contributions = [CostContribution(kind=h.kind, card=h.card, object_id=plan.oid(h.card),
                                      name=plan.state.cards[h.card].name or "", pays=sym,
                                      card_types=sorted(plan.ch(plan.state.cards[h.card]).types))
                     for h, sym in zip(helpers, assignment, strict=True)]
    tap = [h.card for h in helpers if h.kind != "delve"]
    if tap:
        kinds = " and ".join(dict.fromkeys(h.kind for h in helpers if h.kind != "delve"))
        plan.do({"type": "rules_mana", "player": player, "tap": tap, "sacrifice": [], "delta": {}, "life": 0,
                 "label": f"paid part of {cost.text()} for {ch.name or 'a spell'} with {kinds}"}, actor=player)
    delved = [h.card for h in helpers if h.kind == "delve"]
    if delved:
        plan.do({"type": "move", "card_ids": delved, "to": {"player": player, "zone": "exile"}}, actor=player)
        for contribution in contributions:
            if contribution.kind == 'delve' and plan.state.cards[contribution.card].zone.endswith(':exile'):
                contribution.exiled_object_id = plan.oid(contribution.card)
    rest = P.remaining(cost, assignment)
    n_life = len(a.life_symbols or ())  # -- phyrexian mana (wave 50B) -- announced in 601.2b: 2 life each, paid with the rest
    data = _SpellPayment(card.id, player, cost, spell_ch, contributions, a, n_life, then or {},
                         (x_payment or {}).get("black"))
    if then is not None:
        from app.rules import payment_continuations as pc

        after = pc.continuation(plan, "spell_mana_paid", data)
        pay_then(plan, player, rest, label, sources=a.sources, exclude=exclude, purpose=purpose,
                 life_due=2*n_life, then=after)
        return None
    payment = pay(plan, player, rest, label, sources=a.sources, exclude=exclude, purpose=purpose, life_due=2 * n_life)
    return _spell_record(plan, data, payment)


@dataclass
class _SpellPayment:
    card: str
    player: str
    cost: M.ManaCost
    spell_ch: Characteristics
    contributions: list[CostContribution]
    a: A.CastSpell
    n_life: int
    then: dict[str, Any]
    x_black_spent: int | None = None


@dataclass
class _XAllocation:
    player: str
    cost: M.ManaCost
    label: str
    sources: list[str] | None
    exclude: tuple[str, ...]
    purpose: Purpose
    life_due: int
    then: dict[str, Any]
    a: A.CastSpell
    card: str
    ch: Characteristics
    not_mana: tuple[str, ...]
    origin: str | None


def _offer_x_allocation(plan: Plan, data: _XAllocation, helpers: list[P.Helper]) -> None:
    from app.rules import payment_continuations as pc

    metadata = data.purpose.x_payment or {}
    feasible = []
    for black in range(min(int(metadata.get("max", data.cost.generic)), data.cost.generic)+1):
        purpose = replace(data.purpose, x_payment={**metadata, "black": black})
        candidates = (_auto_helpers(plan, data.cost, data.ch, data.card, purpose)
                      if not data.a.contributions and data.sources is None and payment_mode(plan, data.player) != 'self'
                      else helpers)
        excluded = tuple(h.card for h in candidates) + data.not_mana
        def covers(rest: M.ManaCost, purpose: Purpose = purpose, excluded: tuple[str, ...] = excluded) -> bool:
            try:
                find_payment(plan.state, data.player, rest, plan.info, sources=data.sources,
                             exclude=excluded, purpose=purpose, reserve=plan.reserved_life)
            except ActionError:
                return False
            return True

        if (P.assign(data.cost, candidates, covers) is None) if candidates else not covers(data.cost):
            continue
        feasible.append(black)
    if not feasible:
        raise ActionError("No legal allocation of mana to X")
    after = pc.continuation(plan, "x_allocation_paid", data)
    if len(feasible) == 1:
        _select_x_allocation(plan, after, feasible[0])
        return
    _x_allocation_page(plan, data.player, after, feasible, 0)


def _x_allocation_page(plan: Plan, player: str, after: dict[str, Any], feasible: list[int], page: int) -> None:
    options = [DecisionOption(id=str(k), label=f"{k} black mana spent on X") for k in feasible[page:page+98]]
    if page:
        options.append(DecisionOption(id="previous", label="Previous amounts"))
    if page+98 < len(feasible):
        options.append(DecisionOption(id="next", label="More amounts"))
    decide(plan, player=player, kind="choose_one", prompt="How much black mana do you spend on X?", options=options,
           resume={"step":"x_allocation", "after":after, "feasible":feasible, "page":page})


def resume_x_allocation(plan: Plan, d: Any, chosen: list[str]) -> None:
    frame = d.resume
    if chosen[0] in ("previous", "next"):
        page = frame["page"] + (-98 if chosen[0] == "previous" else 98)
        _x_allocation_page(plan, d.player, frame["after"], frame["feasible"], page)
    else:
        _select_x_allocation(plan, frame["after"], int(chosen[0]))


def _select_x_allocation(plan: Plan, after: dict[str, Any], black: int) -> None:
    from app.rules import payment_continuations as pc

    payload = after["payload"]
    payload["purpose"]["x_payment"]["black"] = black
    pc.finish(plan, after, None)


def _x_allocation_paid(plan: Plan, data: _XAllocation, payment: M.Payment | None) -> None:
    _pay_spell(plan, data.a, plan.state.cards[data.card], data.ch, data.cost, data.label,
               not_mana=data.not_mana, origin=data.origin, then=data.then, x_payment=data.purpose.x_payment, payment_context=_purpose_context(data.purpose))


def _spell_record(plan: Plan, data: _SpellPayment, payment: M.Payment | None) -> PaymentRecord:
    from app.rules import mana_units

    card = plan.state.cards[data.card]
    return PaymentRecord(card=data.card, controller=data.player, total_cost=data.cost.text(),
                         mana_spent=dict(payment.spent) if payment else {}, x_black_spent=data.x_black_spent, contributions=data.contributions,
                         mana_tags=payment.tags if payment else [], snow_spent=dict(payment.snow_spent) if payment else {},
                         mana_sources=payment.sources if payment else [],
                         mana_riders=mana_units.matching(plan, payment.riders, card, data.spell_ch, data.player) if payment else [],
                         life=payment.life if payment else 0,  # (wave 43D: compleated; wave 50B: the symbols announced, else the life the solver took)
                         phyrexian=data.n_life if data.a.life_symbols is not None else payment.life // 2 if payment else 0,
                         tapped=list(payment.tapped) if payment else [],
                         sacrificed=list(payment.sacrificed) if payment else [], x=data.a.x_value)




def _spell_mana_paid(plan: Plan, data: _SpellPayment, payment: M.Payment | None) -> None:
    from app.rules import payment_continuations as pc

    record = _spell_record(plan, data, payment)
    after = {**data.then, "payload": {**data.then["payload"], "record": record.model_dump(mode="json")}}
    gain_payment = None
    if data.then.get("stage") == "post_cast":
        post = TypeAdapter(_PostCast).validate_python(data.then["payload"])
        if post.add_cost is not None and any(c.kind == costs.OPPONENT_GAIN_LIFE for c in post.add_cost.components):
            gain_payment = payment
    pc.finish(plan, after, gain_payment)


def pay_spell(plan: Plan, a: A.CastSpell, card: CardInstance, ch: Characteristics, cost: M.ManaCost,
              label: str, *, not_mana: tuple[str, ...] = (), origin: str | None = None) -> PaymentRecord:
    result = _pay_spell(plan, a, card, ch, cost, label, not_mana=not_mana, origin=origin)
    assert result is not None
    return result


def pay_spell_then(plan: Plan, a: A.CastSpell, card: CardInstance, ch: Characteristics, cost: M.ManaCost,
                   label: str, *, then: dict[str, Any], not_mana: tuple[str, ...] = (), origin: str | None = None,
                   x_payment: dict[str, Any] | None = None, payment_context: dict[str, Any] | None = None) -> None:
    _pay_spell(plan, a, card, ch, cost, label, not_mana=not_mana, origin=origin, then=then, x_payment=x_payment, payment_context=payment_context)


# -- refused modal/conditional (wave 3R1) --
def _note_cast(plan: Plan, record: PaymentRecord, zone: str, *, zone_player: str | None = None) -> None:
    """How a spell was cast, on its payment record: the zone it was cast from ("if you cast it from your hand",
    "if this spell was cast from a graveyard") and whether it was cast during its caster's own main phase
    (addendum: "if you cast this spell during your main phase" — 505.1: a main phase of the caster's turn)."""
    record.cast_from = zone
    record.cast_from_player = zone_player
    record.cast_controlled_subtypes = sorted({subtype for c in plan.state.cards.values()
        if c.controller == record.controller and c.zone.endswith(":battlefield") and plan.in_game(c)
        for subtype in plan.ch(c).subtypes})
    from app.rules import (
        selectors,  # -- xdamage (wave 100E) -- "if you controlled a modified creature as you cast this spell" (601.2i)
    )

    modified = selectors.candidates(plan, selectors.Selector(controller="you", types=("Creature",), extras=("modified",)), record.controller, None)
    record.cast_controlled_modified = bool(modified)
    record.cast_modified_n110e = len(modified)  # -- wave 110E -- the count, for "for each modified creature you controlled as you cast this spell"
    record.cast_revealed_subtypes = sorted({subtype for cid in record.revealed
        if (revealed_card := plan.state.cards.get(cid)) is not None
        for subtype in plan.ch(revealed_card).subtypes})
    if (cast_card := plan.state.cards.get(record.card)) is not None:
        from app.rules import prohibitions

        prohibitions.bind_next_uncounterable(plan, cast_card, record.controller)  # -- most-played cards (wave 43B) -- "The next spell you cast this turn can't be countered." (ponytail: spells cast by hand, outside this path, are bound in engine.py)
    r = plan.rules  # (-- review 30 -- a new spell (400.7): an evoke / dash mark left by an earlier spell of this card that never resolved —
    # bounced or countered back to hand — isn't this one's, 702.74a, 702.109a; this cast marks it again if it pays that cost)
    r.evoked, r.dashed = [c for c in r.evoked if c != record.card], [c for c in r.dashed if c != record.card]
    turn = plan.state.turn
    record.cast_main = turn.active_player == record.controller and turn.phase in ("main1", "main2")
    from app.rules import casting_timing_permissions

    if (cast_object := plan.state.cards.get(record.card)) is not None:
        casting_timing_permissions.bind_next_entry(plan, cast_object, record)

# -- end refused modal/conditional (wave 3R1) --


def record_payment(plan: Plan, card_id: str, record: PaymentRecord) -> None:
    """Keep how the spell was paid, on its stack object (and later the permanent it becomes). A record of an
    object that has just left is kept while its last known information is (wave 3R1: "if you cast it" as an
    intervening "if" is checked again as the ability resolves, 603.4, after the permanent may have left)."""
    r = plan.rules
    r.payments = {k: v for k, v in r.payments.items()
                  if (v.card in plan.state.cards and r.object_id(v.card) == k) or k in r.lki}
    r.payments[plan.oid(card_id)] = record


def payment_step(plan: Plan, a: A.CastSpell | A.ActivateAbility | A.EndEffect | A.PayDeferred, cost: M.ManaCost, what: str, *,  # (-- licids (wave 50A) -- EndEffect)
                 exclude: tuple[str, ...] = (), purpose: Purpose | None = None, then: dict[str, Any] | None = None,
                 cast_greatest_power: int | None = None, counter_cost_origins70: list[ObjectRef] | None = None) -> bool:
    """Before a spell or ability is put on the stack: does the player want to see or choose the
    payment first? Returns True if a decision was opened (the intent then waits for it; nothing
    has moved yet, so CANCEL simply leaves everything where it was)."""
    purpose = _purpose_for_cost(cost, purpose)
    def saved(resume: dict[str, Any]) -> dict[str, Any]:
        if counter_cost_origins70 is not None:
            resume['counter_first70'] = True
            resume['counter_cost_origins70'] = [ref.model_dump(mode='json') for ref in counter_cost_origins70]
        if cast_greatest_power is not None:
            resume['cast_greatest_power'] = cast_greatest_power
        if then is not None:
            resume.update(paid_then=then, paid_purpose=_PURPOSE.dump_python(purpose, mode='json') if purpose is not None else None,
                          paid_life_due=2 * len(getattr(a, 'life_symbols', None) or ()))
        return resume

    if a.sources is not None or cost.is_free:
        return False
    timing_object = plan.oid(a.card_id) if isinstance(a, A.CastSpell) else None
    pending = plan.rules.free_cast_then
    if (isinstance(a, A.CastSpell) and a.free and pending is not None and pending["card"] == a.card_id
            and pending.get("e", {}).get("required")):
        # 118.3c: a required cast cannot force mana abilities to be activated.
        # Offer that choice only after modes/targets and the exact cost are locked.
        resume = {"step": "pay_mana", "intent": a.model_dump(mode="json", exclude={"r", "actor", "ts"}),
                  "exclude": list(exclude), "cost": cost.text(), "what": what, "required_mana_decline": True, "x_payment": purpose.x_payment if purpose else None, "payment_context": _purpose_context(purpose), "cast_timing_object": timing_object}
        if _covered(plan, plan.actor, cost, [], resume) is None:
            ask_to_tap(plan, cost, what, saved(resume))
            return True
        a.sources = []
        return False
    mode = payment_mode(plan, plan.actor)
    if mode == "self":  # the player taps their own mana: pay from the pool, or ask them to tap
        probe: dict[str, Any] = saved({"intent": a.model_dump(mode="json", exclude={"r", "actor", "ts"}), "x_payment": purpose.x_payment if purpose else None, "payment_context": _purpose_context(purpose), "cast_timing_object": timing_object})
        helpers = _prompt_helpers(plan, plan.actor, probe) if getattr(a, "contributions", None) else []
        if _covered(plan, plan.actor, cost, helpers, probe) is not None:
            a.sources = []
            return False
        ask_to_tap(plan, cost, what, saved({"step": "pay_mana", "intent": a.model_dump(mode="json", exclude={"r", "actor", "ts"}),
                                      "exclude": list(exclude), "cost": cost.text(), "what": what, "x_payment": purpose.x_payment if purpose else None, "payment_context": _purpose_context(purpose), "cast_timing_object": timing_object}))
        return True
    if mode == "auto":
        return False
    payment = find_payment(plan.state, plan.actor, cost, plan.info, exclude=exclude, purpose=purpose,
                           reserve=plan.reserved_life)  # (can it be paid at all?)
    resume = {"step": "payment", "intent": a.model_dump(mode="json", exclude={"r", "actor", "ts"}),
                              "exclude": list(exclude), "cost": cost.text(), "what": what, "x_payment": purpose.x_payment if purpose else None, "payment_context": _purpose_context(purpose), "cast_timing_object": timing_object}
    resume = saved(resume)
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


# -- phyrexian mana (wave 50B) -- 601.2b, 107.4f: the payer announces, for each Phyrexian symbol, one mana of its color or 2 life, and the
# announced cost is paid as it is (601.2h): the solver no longer picks life where mana would do. ``life_symbols`` (on the intent): the symbols
# (their colors, "G/W" for {G/W/P}) paid with life; None until announced. Kept legacy: an explicit ``sources`` list, and every other payer of a
# cost (unless-pays, special actions), where the solver pays mana first and life only where mana falls short (ponytail ceiling).
def split_phyrexian(cost: M.ManaCost, life: list[str]) -> M.ManaCost:
    """``cost`` with the symbols paid with life taken out and the others made plain colored (hybrid for {G/W/P}) mana; a symbol already gone
    (a locked cost, split before) is skipped."""
    rest = list(cost.phyrexian)
    for c in life:
        if c in rest:
            rest.remove(c)
    any_mana = rest.count(M.ANY_PHYREXIAN)
    rest = [c for c in rest if c != M.ANY_PHYREXIAN]
    result = M.ManaCost(cost.generic + any_mana, cost.colored + tuple(c for c in rest if "/" not in c),
                        cost.hybrid + tuple(tuple(c.split("/")) for c in rest if "/" in c), (), cost.x, cost.unsupported)
    if cost.allocation is not None:
        paid = list(life)
        kept = []
        for label, row in zip(cost.phyrexian, cost.allocation.phyrexian, strict=True):
            if label in paid:
                paid.remove(label)
            else:
                kept.append(row)
        result = replace(result, allocation=replace(cost.allocation,
            symbols=cost.allocation.symbols + tuple(kept), phyrexian=()))
    return result


def phyrexian_options(plan: Plan, cost: M.ManaCost, exclude: tuple[str, ...], purpose: Purpose | None) -> list[tuple[str, ...]]:
    """The ways to pay the Phyrexian symbols of ``cost`` that can be paid now (the sorted symbols paid with life, fewest first): 119.4 the life
    (less what the other costs of it pay), and the mana for the rest from the pool and the untapped sources."""
    from itertools import combinations

    life = spendable_life(plan.state, plan.actor, plan.info) - plan.reserved_life
    ways = dict.fromkeys(tuple(sorted(cost.phyrexian[i] for i in ix)) for k in range(len(cost.phyrexian) + 1)
                         for ix in combinations(range(len(cost.phyrexian)), k))
    return [w for w in ways if 2 * len(w) <= life and can_pay(plan.state, plan.actor, split_phyrexian(cost, list(w)), plan.info, exclude=exclude,
                                                              purpose=purpose, reserve=plan.reserved_life + 2 * len(w))]


def _phyrexian_label(cost: M.ManaCost, way: tuple[str, ...]) -> str:
    rest = list(way)
    out = []
    for c in cost.phyrexian:
        if c in rest:
            rest.remove(c)
            out.append("Pay 2 life (instead of any mana)" if c == M.ANY_PHYREXIAN else f"{{{c}/P}}: 2 life")
        else:
            out.append("Pay one mana of any type (instead of 2 life)" if c == M.ANY_PHYREXIAN else
                       f"{{{c}/P}}: " + " or ".join(f"{{{x}}}" for x in c.split("/")))
    return ", ".join(out)


def announce_phyrexian(plan: Plan, a: A.CastSpell | A.ActivateAbility, cost: M.ManaCost, what: str, *, exclude: tuple[str, ...] = (),
                       purpose: Purpose | None = None, trusted: bool = False) -> M.ManaCost | None:
    """The cost with the announced Phyrexian choices applied, or None while the payer is asked (nothing has moved yet). Asked only when more than one
    way can be paid; the one way left is announced for them. ``trusted``: a payment resumed with its locked cost (``a.life_symbols`` was checked)."""
    life = a.life_symbols
    if life is None and (not cost.phyrexian or a.sources is not None):
        return cost  # nothing to announce, or the payer named their sources (MANUAL PAY): the legacy payment
    ways = [] if trusted and life is not None else phyrexian_options(plan, cost, exclude, purpose)
    if life is None:
        if len(ways) > 1:
            shown_cost = cost.text().replace(f"{{{M.ANY_PHYREXIAN}/P}}", "(one mana of any type or 2 life)")
            decide(plan, player=plan.actor, kind="choose_one", prompt=f"Pay {shown_cost} for {what}: mana or 2 life for each Phyrexian symbol (601.2b)",
                   options=[DecisionOption(id=str(i), label=_phyrexian_label(cost, w)) for i, w in enumerate(ways)],
                   resume=_announcing(plan, "phyrexian", a, options=[list(w) for w in ways]))
            return None
        if not ways:
            return cost  # neither way can be paid: the payment says why
        life = a.life_symbols = list(ways[0])
    elif not trusted and tuple(sorted(life)) not in ways:
        raise ActionError(f"{cost.text()} can't be paid with 2 life for {', '.join(life) or 'no symbol'}: choose Phyrexian symbols of the cost you can pay")
    plan.reserved_life += 2 * len(life)  # 119.4: the life is paid with the rest, so the sources' life payments leave it
    return split_phyrexian(cost, life)


def resume_phyrexian(plan: Plan, d: Any, chosen: list[str]) -> None:
    if cancelled(plan, d, chosen):
        return
    from app.rules.engine import INTENTS  # the engine imports this module

    intent = A.parse_action(d.resume["intent"])
    intent.life_symbols = d.resume["options"][int(chosen[0])]  # type: ignore[union-attr]
    plan.rules.priority = d.player
    plan.rules.passed = []
    INTENTS[intent.type](plan, intent)


def pool_covers(state: GameState, player: str, cost: M.ManaCost, purpose: Purpose | None = None, info: CardInfo | None = None) -> bool:
    """Can ``cost`` be paid from the player's mana pool alone (plus life for Phyrexian mana)? (-- mana provenance (wave 18B) --
    the units that may pay for ``purpose`` are in the pool; review 18B: with ``info``, K'rrik's life too.)"""
    from app.rules import mana_units

    purpose = _purpose_for_cost(cost,purpose)
    try:
        M.solve(_constrained(_spending_cost(state, player, info, life_for_mana(state, player, info, cost) if info is not None else cost), purpose), dict(state.players[player].mana), mana_units.unit_sources(state, player, purpose),
                life=spendable_life(state, player, info))
    except M.ManaError:
        return False
    return True


def pay_from_pool(plan: Plan, player: str, cost: M.ManaCost, label: str, *, purpose: Purpose | None = None) -> None:
    """Pay from the mana pool only (players tap their own lands), or explain what's missing."""
    if not cost.is_free and payment_mode(plan, player) == "self":
        if not pool_covers(plan.state, player, cost, purpose, plan.info):
            raise ActionError(f"Tap your mana first: {cost.text()} isn't in your mana pool")
        pay(plan, player, cost, label, sources=[], purpose=purpose)
    else:
        pay(plan, player, cost, label, purpose=purpose)


def pay_from_pool_then(plan: Plan, player: str, cost: M.ManaCost, label: str, *, then: dict[str, Any],
                       purpose: Purpose | None = None) -> None:
    own_pool = payment_mode(plan, player) == "self"
    if own_pool and not cost.is_free and not pool_covers(plan.state, player, cost, purpose, plan.info):
        raise ActionError(f"Tap your mana first: {cost.text()} isn't in your mana pool")
    pay_then(plan, player, cost, label, sources=[] if own_pool else None, purpose=purpose, then=then)


def _prompt_spell(plan: Plan, resume: dict[str, Any]) -> tuple[Characteristics | None, str | None]:
    """The spell a "tap your mana" prompt is paying for, if it is casting one (only spells have
    convoke / improvise / delve: never ward, "counter unless its controller pays", or abilities)."""
    intent = resume.get("intent") or {}
    card = plan.state.cards.get(intent.get("card_id") or "") if intent.get("type") == "cast_spell" else None
    if card is None:
        return None, None
    if intent.get('face_down'):
        return chars.face_down_characteristics(intent.get('face_down_kind') or 'morph'), card.id
    return chars.as_cast(card, plan.info, intent.get("face")), card.id


def _prompt_helpers(plan: Plan, player: str, resume: dict[str, Any]) -> list[P.Helper]:
    contributions = (resume.get("intent") or {}).get("contributions") or []
    if not contributions:
        return []
    spell, spell_card = _prompt_spell(plan, resume)
    return helpers_for(plan.state, player, plan.info, spell, spell_card, contributions)


def _prompt_purpose(plan: Plan, resume: dict[str, Any]) -> Purpose | None:
    """-- mana provenance (wave 18B) -- what a "tap your mana" prompt pays for, so the pool's restricted mana counts only where it may."""
    if resume.get("paid_purpose") is not None:
        return _PURPOSE.validate_python(resume["paid_purpose"])
    intent = resume.get("intent") or {}
    spell, spell_card = _prompt_spell(plan, resume)
    if spell is not None and spell_card is not None:
        return Purpose(spell=spell, zone=plan.state.cards[spell_card].zone, player=plan.actor, kicked=bool(intent.get("kicker")), x_payment=resume.get("x_payment"), **resume.get('payment_context',{}))
    card = plan.state.cards.get(intent.get("card_id") or "") if intent.get("type") == "activate_ability" else None
    return Purpose(ability_of=plan.ch(card), x_payment=resume.get("x_payment"), **resume.get('payment_context',{})) if card is not None else None


def _covered(plan: Plan, player: str, cost: M.ManaCost, helpers: list[P.Helper],
             resume: dict[str, Any] | None = None) -> list[str] | None:
    """How the committed helpers pay part of ``cost`` so that the mana pool pays the rest, or None."""
    from app.rules import mana_units

    p = plan.state.players[player]
    purpose = _purpose_for_cost(cost,_prompt_purpose(plan, resume) if resume else None)
    if cost.allocation is None and purpose.allocation is not None:
        cost = replace(cost, allocation=purpose.allocation)
    units = mana_units.unit_sources(plan.state, player, purpose)
    reserve = plan.reserved_life
    after = (resume or {}).get('paid_then') or {}
    if after.get('stage') == 'activation_announced':
        reserve = max(reserve, int(after.get('reserved_life', 0)))
    covers = P.pool_pays(dict(p.mana), max(0, spendable_life(plan.state, player, plan.info) - reserve), units)
    return P.assign(cost, helpers, lambda rest: covers(_constrained(_spending_cost(plan.state, player, plan.info, life_for_mana(plan.state, player, plan.info, rest)), purpose)))  # (review 18B: K'rrik)


def _tap_display(plan: Plan, player: str, cost: M.ManaCost, what: str, resume: dict[str, Any]) -> dict[str, Any]:
    """The payment panel: the cost, what's been committed to pay it (each with the symbol it pays),
    what mana is still needed, and what can be clicked."""
    from app.rules import mana_units

    helpers = _prompt_helpers(plan, player, resume)
    committed = {h.card for h in helpers}
    exclude = set(resume.get("exclude") or ()) | committed
    sources = list(dict.fromkeys(s.card_id for s in mana_sources(plan.state, player, plan.info)
                                 if s.card_id not in exclude and s.activation is None))
    for cid in plan.state.zones.get(zone_key(player, "battlefield"), []):
        card = plan.state.cards[cid]
        if cid not in exclude and can_use_tap_abilities(plan.state, card, plan.ch(card), plan.info) and any(
                ab.reveal_hand is not None for _, ab in mana_abilities(plan.state, card, plan.info)):
            sources.append(cid)
    spell, spell_card = _prompt_spell(plan, resume)
    usable = available_helpers(plan.state, player, plan.info, spell, spell_card) if spell is not None else []
    by_kind: dict[str, list[str]] = {k: [] for k in P.KINDS}
    for h in usable:
        by_kind[h.kind].append(h.card)
    for h in helpers:  # committed ones stay clickable (click again to take it back)
        if h.card not in by_kind[h.kind]:
            by_kind[h.kind].append(h.card)
    assignment = _covered(plan, player, cost, helpers, resume) or P.assign(cost, helpers) or []
    paid = [{"card": h.card, "name": plan.state.cards[h.card].name or "a card", "kind": h.kind, "pays": sym}
            for h, sym in zip(helpers, assignment, strict=False)]
    rest = P.remaining(cost, assignment) if len(assignment) == len(helpers) else cost
    from app.rules import x_mana_restrictions

    remaining = P.after_pool(_constrained(_spending_cost(plan.state, player, plan.info, rest), _prompt_purpose(plan, resume)), mana_units.visible_pool(plan.state, player))
    remaining = x_mana_restrictions.visible(remaining)
    # (wave 29C: every helper is listed — the table clicks a creature / artifact / card only if it is on its list, so a cut list hid some)
    return {"kind": "tap_mana", "cost": cost.text(), "what": what, "sources": sources,
            "convoke": by_kind["convoke"], "improvise": by_kind["improvise"], "delve": by_kind["delve"],
            "committed": sorted(committed), "paid": paid, "mana_due": rest.text() if not rest.is_free else "",
            "remaining": _left_text(remaining),
            "pool": mana_units.visible_pool(plan.state, player)}


def _left_text(cost: M.ManaCost) -> str:
    return "" if cost.is_free else cost.text()


def ask_to_tap(plan: Plan, cost: M.ManaCost, what: str, resume: dict[str, Any]) -> None:
    """Open the "tap your mana" prompt: the player taps lands / mana sources (mana abilities are
    allowed while it's open) and, for a spell with convoke / improvise / delve, clicks creatures,
    artifacts or graveyard cards to pay parts of the cost. The spell goes on as soon as the pool
    covers what's left."""
    display = _tap_display(plan, plan.actor, cost, what, resume)
    hint = " (you can tap creatures for convoke)" if display["convoke"] else \
        " (you can tap artifacts for improvise)" if display["improvise"] else \
        " (you can exile cards from your graveyard for delve)" if display["delve"] else ""
    decide(plan, player=plan.actor, kind="choose_one", prompt=f"Tap mana to pay {cost.text()} for {what}{hint}",
           display=display, options=[DecisionOption(id="pay", label="Pay"),
                                    DecisionOption(id="cancel", label="Decline activating mana abilities" if resume.get("required_mana_decline") else "Cancel")],
           resume=resume)


def resume_pay_mana(plan: Plan, d: Any, chosen: list[str]) -> None:
    assert d.resume is not None
    if chosen[0] == "cancel":  # nothing committed was tapped or exiled yet (601.2h: no partial payments)
        pending = plan.rules.free_cast_then
        if (d.resume.get("required_mana_decline") and pending is not None
                and pending.get("e", {}).get("required") and pending["card"] == d.resume["intent"].get("card_id")
                and _covered(plan, d.player, M.parse_cost(d.resume["cost"]), [], d.resume) is None):
            pending["required_unpayable"] = True
        plan.note(f"{plan.name(d.player)} cancelled")
        if _attack_cancelled(plan, d):  # -- combat (wave 5C) --
            return
        plan.rules.priority = d.player
        plan.hold = d.player
        return
    if _covered(plan, d.player, M.parse_cost(d.resume["cost"]), _prompt_helpers(plan, d.player, d.resume), d.resume) is None:
        raise ActionError(f"Tap your mana first: {d.resume['cost']} isn't paid yet")
    _rerun(plan, d, A.parse_action(d.resume["intent"]), [])


def paying_now(plan: Plan) -> bool:
    """Is the actor in the middle of paying (a "tap your mana" or pay-or-sacrifice prompt)?"""
    d = plan.rules.decision
    return d is not None and d.player == plan.actor and (d.resume or {}).get("step") in ("pay_mana", "pay_or_sacrifice")


def after_tapping(plan: Plan) -> None:
    """Mana was added (or a helper committed) during a "tap your mana" prompt: finish the payment
    once the pool covers what's left, else refresh the prompt."""
    from app.rules import mana_units

    d = plan.rules.decision
    resume = (d.resume or {}) if d is not None else {}
    if d is None or resume.get("step") != "pay_mana":
        if d is not None and d.display is not None:
            d.display = {**d.display, "pool": mana_units.visible_pool(plan.state, d.player)}
        return
    from app.rules import fixed_top_graveyard_cost46

    if fixed_top_graveyard_cost46.refresh_mana_window(plan):
        return
    cost = M.parse_cost(resume["cost"])
    if _covered(plan, d.player, cost, _prompt_helpers(plan, d.player, resume), resume) is not None:
        plan.rules.decision = None
        _rerun(plan, d, A.parse_action(resume["intent"]), [])
    else:
        d.display = _tap_display(plan, d.player, cost, resume.get("what", ""), resume)


def _best_option_index(plan: Plan, options: tuple[tuple[str, ...], ...]) -> int:
    """The mana option that helps the pending payment most (the player tapped; this only picks
    which color to add for them)."""
    d = plan.rules.decision
    if d is None or not d.resume or "cost" not in d.resume:
        return 0
    cost = M.parse_cost(d.resume["cost"])
    cost = _constrained(_spending_cost(plan.state, plan.actor, plan.info, life_for_mana(plan.state, plan.actor, plan.info, cost)), _prompt_purpose(plan, d.resume))
    pool = dict(plan.state.players[plan.actor].mana)
    for option_index, opt in enumerate(options):
        trial = dict(pool)
        for m in opt:
            trial[m] = trial.get(m, 0) + 1
        try:
            M.solve(cost, trial, [])
            return option_index
        except M.ManaError:
            pass
    needed = set(cost.colored) | {c for h in cost.hybrid for c in h} | {c for p in cost.phyrexian for c in p.split("/")}
    return next((i for i, o in enumerate(options) if set(o) & needed - set(pool)),
                next((i for i, o in enumerate(options) if set(o) & needed), 0))


def ask_sources(plan: Plan, cost: M.ManaCost, what: str, resume: dict[str, Any]) -> None:
    exclude = tuple(resume.get("exclude") or ())
    sources = [s for s in mana_sources(plan.state, plan.actor, plan.info) if s.card_id not in exclude]
    options = [DecisionOption(id=s.card_id, label=plan.state.cards[s.card_id].name or "Source", card_id=s.card_id)
               for s in sources]
    decide(plan, player=plan.actor, kind="choose_cards",
           prompt=f"Choose the mana sources to pay {cost.text()} for {what} (your mana pool is used first)",
           options=options, min_choices=0, max_choices=max(len(options), 0),
           resume={**resume, "step": "payment_sources"})


def _attack_cancelled(plan: Plan, d: Any) -> bool:
    """-- combat (wave 5C) -- the cost to attack wasn't paid: attackers are declared again (508.1j: the declaration
    is illegal without the payment)."""
    kind = ((d.resume or {}).get("intent") or {}).get("type")
    if kind not in ('declare_attackers', 'declare_blockers'):
        return False
    from app.rules import combat

    plan.rules.declaration_cost_reserved = None
    if kind == 'declare_blockers':
        combat.ask_next_blocker(plan)
    else:
        combat.start_declare_attackers(plan)
    return True


def resume_payment(plan: Plan, d: Any, chosen: list[str]) -> None:
    """PAY (the suggestion), MANUAL (pick sources) or CANCEL."""
    assert d.resume is not None
    answer = chosen[0]
    if answer == "cancel":
        plan.note(f"{plan.name(d.player)} cancelled")
        if _attack_cancelled(plan, d):  # -- combat (wave 5C) --
            return
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


def _locked(plan: Plan, cost: M.ManaCost) -> M.ManaCost:
    """-- cost changers (wave 4I) -- the total cost locked in when the payment was asked for (601.2f), if this is that
    cast or activation resumed (``_rerun``); read once."""
    locked, plan.locked_cost = plan.locked_cost, None
    if locked is None:
        return cost
    parsed = M.parse_cost(locked)
    data = (plan.locked_payment_context or {}).get('allocation')
    return replace(parsed, allocation=TypeAdapter(M.RequirementPlan).validate_python(data)) if data is not None else parsed


def _rerun(plan: Plan, d: Any, intent: Any, sources: list[str]) -> None:
    from app.rules.engine import INTENTS  # the engine imports this module

    if isinstance(d.resume, dict) and d.resume.get('counter_first70'):
        from app.rules import counter_cost_order70

        raw = d.resume.get('counter_cost_origins70')
        counter_cost_order70.guard_original(plan, [ObjectRef.model_validate(ref) for ref in raw] if raw is not None else None)
    intent.sources = sources
    plan.rules.priority = d.player
    plan.rules.passed = []
    if isinstance(d.resume, dict) and d.resume.get('paid_then') is not None:
        cost = M.parse_cost(d.resume['cost'])
        if d.resume.get('paid_purpose') is not None:
            plan.reserved_life = int(d.resume['paid_then'].get('reserved_life', plan.reserved_life))
        pay_then(plan, d.player, cost, f"paid {cost.text()} for {d.resume['what']}",
                 sources=sources, exclude=tuple(d.resume.get('exclude') or ()), then=d.resume['paid_then'],
                 purpose=_PURPOSE.validate_python(d.resume['paid_purpose']) if d.resume.get('paid_purpose') is not None else None,
                 life_due=int(d.resume.get('paid_life_due', 0)))
        return
    # -- cost changers (wave 4I) -- 601.2f: the total cost was locked in when the payment was asked for; mana abilities
    # activated meanwhile (a Treasure sacrificed, a creature sacrificed for mana) don't change it
    plan.locked_cost = d.resume.get("cost") if isinstance(d.resume, dict) else None
    plan.locked_x_payment = d.resume.get("x_payment") if isinstance(d.resume, dict) else None
    plan.locked_payment_context = d.resume.get('payment_context') if isinstance(d.resume,dict) else None
    plan.locked_cast_timing = d.resume.get('cast_timing_object') if isinstance(d.resume, dict) else None
    plan.locked_cast_greatest_power = d.resume.get('cast_greatest_power') if isinstance(d.resume, dict) else None
    zero_modes = d.resume.get("zero_modes_object") if isinstance(d.resume, dict) else None
    plan.locked_zero_modes = zero_modes if isinstance(zero_modes, str) else None
    try:
        INTENTS[intent.type](plan, intent)
    finally:
        plan.locked_cost = None
        plan.locked_x_payment = None
        plan.locked_payment_context = None
        plan.locked_cast_timing = None
        plan.locked_cast_greatest_power = None
        plan.locked_zero_modes = None


def can_pay(state: GameState, player: str, cost: M.ManaCost, info: CardInfo, *, exclude: tuple[str, ...] = (),
            purpose: Purpose | None = None, reserve: int = 0) -> bool:
    purpose = _purpose_for_cost(cost,purpose)
    if reserve > spendable_life(state, player, info):
        return False  # 119.4: equality is legal, but the announced life costs must be payable in full
    everything = [s for s in mana_sources(state, player, info, purpose) if s.card_id not in exclude]
    if purpose is not None and purpose.card is not None \
            and helper_kinds(purpose.spell, state, player, purpose.card, info):  # (a hint: never paid here)
        assert purpose.spell is not None
        everything = _helper_sources(state, player, info, purpose.spell, purpose.card, everything)
    from app.rules import mana_units

    cost = _constrained(_spending_cost(state, player, info, life_for_mana(state, player, info, cost)), purpose)
    try:
        _solve_with_filters(cost, dict(state.players[player].mana),
                            [s for s in everything if s.activation is None] + mana_units.unit_sources(state, player, purpose),
                            [s for s in everything if s.activation is not None],
                            max(0, spendable_life(state, player, info) - reserve),
                            input_spending=lambda due: _spending_cost(state, player, info, due))  # (-- hints (wave 30B) -- 119.4: less the life the spell's other costs pay, as ``_find_payment``'s ``reserve``)
    except M.ManaError:
        return False
    return True


# -- casting ----------------------------------------------------------------------------
FLASHBACK = re.compile(r"^flashback (?P<cost>(?:\{[^}]+\})+)$", re.IGNORECASE)


# -- static_other sweep (wave 16B) -- 702.34a: a flashback cost with other parts: "Flashback—{1}{U}, Pay 3 life.", "Flashback—Sacrifice a
# creature.", "Flashback—Tap three untapped white creatures you control." — the parts alt_costs reads (never X, "behold", loyalty counters)
FLASHBACK_MORE = re.compile(r"^flashback—(?P<mana>(?:\{[^}]+\})+)?(?:, )?(?P<rest>[^{}]+)$", re.IGNORECASE)


def flashback_parts(text: str) -> tuple[str, AbilityCost | None] | None:
    """The flashback line's (mana cost, other cost parts) — "{0}" when it has no mana — or None when a part isn't read."""
    from app.rules import alt_costs, conditional_own_discounts

    t = text.strip().rstrip(".")
    t = conditional_own_discounts.flashback_line(t) or t
    if (m := FLASHBACK.fullmatch(t)) is not None:
        return m["cost"], None
    m = FLASHBACK_MORE.fullmatch(t)
    if m is None:
        return None
    parts = [alt_costs._part(p.strip()) or _sized_part(p.strip()) for p in m["rest"].split(", ")]  # (wave 43D: "Sacrifice X Mountains", "Behold three Elementals")
    if any(p is None or isinstance(p, str) for p in parts) or sum(1 for p in parts if getattr(p, "x", False)) > 1:
        return None
    comps = tuple(p for p in parts if not isinstance(p, str) and p is not None)
    return m["mana"] or "{0}", AbilityCost(components=comps, life=sum(c.amount for c in comps if c.kind == costs.PAY_LIFE))


def _sized_part(text: str) -> costs.CostComponent | None:
    """-- cast keywords (wave 43D) -- a part of a flashback cost an alternative cost doesn't read: one sized by the announced X (107.3a: "Sacrifice X Mountains",
    "Discard X cards", "Exile X blue cards from your graveyard") or by a count ("Behold three Elementals", 701.4a) — the parts a spell's additional cost reads."""
    found = costs.parse_additional_cost(text[:1].lower() + text[1:])
    return found.components[0] if found is not None and len(found.components) == 1 and not found.either else None


# -- static_other sweep (wave 16B) -- 702.120a: "Escalate {cost}" / "Escalate—Discard a card.": "for each mode you choose beyond the first, you pay
# [cost] as an additional cost to cast this spell" (a mana cost, or other parts alt_costs reads)
ESCALATE = re.compile(r"^escalate(?: (?P<mana>(?:\{[^}]+\})+)|—(?P<rest>[^{}]+))$", re.IGNORECASE)


def escalate_parts(text: str) -> tuple[str, AbilityCost | None] | None:
    """The escalate line's (mana cost, other cost parts) per extra mode, or None when it isn't read."""
    from app.rules import alt_costs

    m = ESCALATE.fullmatch(text.strip().rstrip("."))
    if m is None:
        return None
    if m["mana"]:
        return m["mana"], None
    parts = [alt_costs._part(p.strip()) for p in m["rest"].split(", ")]
    if any(p is None or isinstance(p, str) or getattr(p, "x", False) for p in parts):
        return None
    comps = tuple(p for p in parts if not isinstance(p, str) and p is not None)
    return "{0}", AbilityCost(components=comps, life=sum(c.amount for c in comps if c.kind == costs.PAY_LIFE))


def escalate_cost(ch: Characteristics) -> tuple[str, AbilityCost | None] | None:
    for ab in ch.abilities:
        if ab.kind == "keywords" and "escalate" in ab.keywords and (found := escalate_parts(ab.text)) is not None:
            return found
    return None


def flashback_cost(ch: Characteristics) -> str | None:
    """702.34: the mana part of the flashback cost printed on the card ("Flashback {2}{R}"), or None (``flashback_extra``: the
    other parts of "Flashback—{1}{U}, Pay 3 life")."""
    for ab in ch.abilities:
        if ab.kind == "keywords" and "flashback" in ab.keywords and (found := flashback_parts(ab.text)) is not None:
            return found[0]
    return None


def flashback_extra(ch: Characteristics) -> AbilityCost | None:
    """-- static_other sweep (wave 16B) -- the non-mana parts of the flashback cost, paid with the mana (118.9a, 601.2h)."""
    for ab in ch.abilities:
        if ab.kind == "keywords" and "flashback" in ab.keywords and (found := flashback_parts(ab.text)) is not None:
            return found[1]
    return None


def from_graveyard(card: CardInstance, player: str, ch: Characteristics, state: GameState | None = None, info: CardInfo | None = None) -> bool:
    """Casting with flashback: from your own graveyard, when it has a (mana) flashback cost — its
    own, or (wave 3R2, ``state``) one an effect gave it this turn (app/rules/graveyard_grants.py)."""
    if card.zone != zone_key(player, "graveyard") or card.owner != player:
        return False
    # -- static_other sweep (wave 16B) -- 702.127a: the aftermath half is cast from a graveyard and exiled as it leaves the stack
    return "aftermath" in ch.keywords or flashback_cost(ch) is not None or (state is not None and _granted_flashback(state, card, ch, info) is not None)


def _granted_flashback(state: GameState, card: CardInstance, ch: Characteristics, info: CardInfo | None = None) -> str | None:
    """-- refused grants/replacements (wave 3R2) -- "… gains flashback until end of turn" (Snapcaster Mage)."""
    from app.rules import graveyard_grants

    return graveyard_grants.flashback_cost(state, card, ch, info)


MORPH = re.compile(r"^(?P<kind>morph|megamorph) (?P<cost>(?:\{[^}]+\})+)$", re.IGNORECASE)
# -- hidden exile (wave 18A) -- a morph cost that isn't mana ("Morph—Discard a card.", "Morph—Reveal a blue card in your hand.", "Morph—Pay 5
# life."): paid as an ability cost (602.2b's procedure, app/rules/cost_payment.py) when the permanent is turned face up (702.37e)
MORPH_COST = re.compile(r"^(?P<kind>morph|megamorph)—(?P<cost>[^{}]+)$", re.IGNORECASE)


def nonmana_cost(text: str) -> AbilityCost | None:
    """The non-mana cost a morph line names, as parts the engine pays, or None."""
    from app.rules import optional_payment

    found = optional_payment.parse(re.sub(r" in your hand$", " from your hand", text.strip().rstrip(".")))
    return found if found is not None and not found.mana and (found.components or found.life) else None


FACE_DOWN = chars.face_down_characteristics("morph")  # (708.2a; disguise: chars.face_down_characteristics)


def morph_cost(ch: Characteristics) -> tuple[str, str] | None:
    """702.37 morph / megamorph with a mana cost: (kind, cost), from the printed card."""
    for ab in ch.abilities:
        if ab.kind == "keywords" and ({"morph", "megamorph"} & set(ab.keywords)):
            m = MORPH.fullmatch(ab.text.strip().rstrip("."))
            if m:
                return m["kind"].lower(), m["cost"]
            m = MORPH_COST.fullmatch(ab.text.strip().rstrip("."))
            if m and nonmana_cost(m["cost"]) is not None:  # (wave 18A)
                return m["kind"].lower(), m["cost"]
    return None


# -- keyword actions & face-down (wave 3F) ------------------------------------------------------
def disguise_cost(ch: Characteristics) -> str | None:
    """702.168 disguise with a mana cost, from the printed card."""
    from app.rules import disguise_costs

    spec = disguise_costs.of(ch)
    return spec[0] if spec is not None else None


def face_down_cast_kind(ch: Characteristics) -> str | None:
    """How a card may be cast face down (702.37c / 702.168b): "morph" (morph, megamorph) or "disguise"."""
    return "morph" if morph_cost(ch) is not None else "disguise" if disguise_cost(ch) is not None else None


def face_up_ways(card: CardInstance, printed: Characteristics, *, state: GameState | None = None,
                 info: CardInfo | None = None) -> dict[str, tuple[str, str]]:
    """The ways its controller may turn this face-down permanent face up, as {way: (cost, kind)}:
    "morph" (702.37e: its morph or megamorph cost; "megamorph" as kind), "disguise" (702.168d), and
    "mana_cost" for a manifested or cloaked permanent (701.40b / 701.58b: a creature card's mana cost
    — not an instant or sorcery card, nor one without a mana cost; 701.40c-d / 701.58c-d: a manifested
    or cloaked card with morph or disguise may use those too). A cost with X isn't automated."""
    if state is not None and info is not None:
        from app.rules import layers

        prospective95 = card.model_copy(update={'face_down': False})
        printed = layers.derive(state, prospective95, chars.of(prospective95, info), info)
    ways: dict[str, tuple[str, str]] = {}
    found = morph_cost(printed)
    if found is not None:
        cost78 = found[1]
        if state is not None and info is not None and cost78.startswith('{'):
            from app.rules import morph_costs78

            cost78 = M.parse_cost(cost78).plus_generic(morph_costs78.tax(state, info)).text()
        ways["morph"] = (cost78, found[0])
    disguise = disguise_cost(printed)
    if disguise is not None:
        from app.rules import disguise_costs

        ways["disguise"] = (disguise_costs.reduced(state, card, printed, info) if state is not None and info is not None else disguise, "disguise")
    if card.face_down_kind in ("manifest", "cloak") and printed.is_creature and printed.mana_cost:
        ways["mana_cost"] = (printed.mana_cost, "mana_cost")
    return ways  # (-- face-down X (wave 110B) -- a cost with X is paid with the X announced: turn_face_up)


def pay_nonmana_cost(plan: Plan, a: A.TurnFaceUp, card: CardInstance, printed: Characteristics, text: str) -> bool:
    """-- hidden exile (wave 18A) -- 702.37e: pay a morph cost that isn't mana (discard, return, sacrifice, reveal, life), the
    parts chosen as an activated ability's are (cost_payment.choose: a private decision when there is a choice, 118.3: only if
    all of it can be paid). False while the player is asked what pays it."""
    from app.rules import cost_payment

    cost = nonmana_cost(text)
    if cost is None:
        raise ActionError("That morph cost can't be paid here: turn it face up with the table tools")
    if (why := cost_payment.problem(plan, cost, card, plan.actor)) is not None:
        raise ActionError(why)
    if cost.life and plan.state.players[plan.actor].life < cost.life:
        raise ActionError(f"You don't have {cost.life} life to pay")  # 119.4
    from app.rules import life_lock  # -- can't lose life (wave 29D) -- 119.8

    if (why := life_lock.pay_problem(plan.state, plan.info, plan.actor, cost.life)) is not None:
        raise ActionError(why)
    chosen = cost_payment.choose(plan, a, cost, card, f"Turn {printed.name} face up")
    if chosen is None:
        return False
    if cost.life:
        from app.rules import replace as _replace_life  # (wave 28B: 119.4)
        _replace_life.lose_life(plan, [(plan.actor, cost.life)])
    cost_payment.pay(plan, cost, card, chosen, PaymentRecord(card=card.id, controller=plan.actor, total_cost=text))
    for i, comp in enumerate(cost.components):  # "Reveal a blue card in your hand": shown to everyone as the cost is paid (701.20a)
        if comp.kind == "REVEAL_FROM_HAND" and chosen.get(i):
            plan.do({"type": "reveal", "card_ids": chosen[i]}, actor=plan.actor)
            plan.do({"type": "hide", "card_ids": chosen[i]}, actor=plan.actor)
    plan.note(f"{plan.name(plan.actor)} paid “{text}” to turn a permanent face up")  # (702.37e: the cost is shown to all players)
    return True


def turned_up(plan: Plan, card: CardInstance, x: int | None = None, by: str | None = None) -> None:
    """-- hidden exile (wave 18A) -- the permanent was just turned face up (by the special action or by an effect): its "When ~ is
    turned face up" and the table's "Whenever a permanent you control is turned face up" abilities trigger (702.37e: not
    "enters" abilities, 708.8)."""
    # 702.37e: who turned it up (the special action's player, or the effect's controller) rides on the event: "Whenever you turn a permanent face up"
    emit(plan.state, "turned_face_up", object_id=plan.oid(card), card=card.id, player=card.controller, actor=by or plan.actor)
    from app.rules import (
        counters52d,  # -- counters (wave 52D) -- 708.11: "As ~ is turned face up, put five +1/+1 counters on it."
    )

    counters52d.turned_up(plan, card)
    from app.rules import triggers  # (triggers imports this module)

    face_up = plan.ch(plan.state.cards[card.id])
    if not plan.manual(card):  # "When ~ is turned face up, …"
        for i, d in triggers.abilities(plan, face_up, "turned_face_up_self"):
            triggers._add(plan, controller=card.controller, source_card=card.id, source_object=plan.oid(card),
                          name=face_up.name, index=i, definition=d,
                          event=TriggerEvent(kind="turned_face_up", objects=[ObjectRef(card=card.id, object_id=plan.oid(card), zone=card.zone)], x=x))  # (wave 110B: the X paid)


def turn_face_up(plan: Plan, a: A.TurnFaceUp) -> None:
    """702.37e / 702.168d / 701.40b / 701.58b: a special action any time you have priority (it
    doesn't use the stack): show the cost, pay it, turn the permanent face up (708.8: no "enters"
    ability triggers). ``a.method`` picks the way when there are several (default: morph or
    disguise when the card has it, else its mana cost)."""
    require_no_decision(plan)
    require_priority(plan)
    card = plan.state.cards.get(a.card_id)
    if card is None or card.controller != plan.actor or not card.zone.endswith(":battlefield") or not card.face_down:
        raise ActionError("Turn face up a face-down permanent you control")
    from app.rules import static_perm100d  # -- static permanents (wave 100D) -- Karlov Watchdog

    if (barred := static_perm100d.face_up_barred(plan, card)) is not None:
        raise ActionError(barred)
    printed = chars.of(card.model_copy(update={"face_down": False}), plan.info)
    ways = face_up_ways(card, printed, state=plan.state, info=plan.info)
    method = a.method or next((w for w in ("morph", "disguise", "mana_cost") if w in ways), None)
    if method is None or method not in ways:
        raise ActionError("It can't be turned face up that way: turn it face up with the table tools")
    cost_text, kind = ways[method]
    from app.rules import morph_costs78

    tax78 = morph_costs78.tax(plan.state, plan.info) if method == 'morph' else 0
    if tax78 and not cost_text.startswith('{'):
        morph_costs78.pay_nonmana(plan, a, card, printed, cost_text, kind, tax78)
        return
    if not cost_text.startswith("{"):  # -- hidden exile (wave 18A) -- a morph cost that isn't mana (702.37e: "pay that cost")
        if not pay_nonmana_cost(plan, a, card, printed, cost_text):
            return  # (waiting for the choice of what pays it)
    else:
        from app.rules import special_payment_tails

        cost = M.parse_cost(cost_text)
        x110b = None
        if cost.x:  # -- face-down X (wave 110B) -- 107.3a, 702.37e: "Morph {X}{B}{B}": X is announced as the cost is paid; the face-up trigger reads it (triggers.x_source)
            if a.x_value is None:
                raise ActionError("Choose a value for X")
            x110b, cost = a.x_value, cost.with_x(a.x_value)
        payment_method = ('morph' if method == 'morph' else f'{card.face_down_kind}_mana' if method == 'mana_cost' else method)
        purpose = Purpose(special="turn_up",payment_method=payment_method, selected_cost_has_x=x110b is not None)
        own_pool = payment_mode(plan, plan.actor) == "self"
        if own_pool and not cost.is_free and not pool_covers(plan.state, plan.actor, cost, purpose, plan.info):
            raise ActionError(f"Tap your mana first: {cost.text()} isn't in your mana pool")
        if not own_pool and not can_pay(plan.state, plan.actor, cost, plan.info, purpose=purpose):
            raise ActionError(f"Not enough mana to pay {cost.text()}")
        special_payment_tails.pay(plan, "face_up", card, printed, cost, f"paid {cost.text()} to turn {printed.name} face up",
                                  sources=[] if own_pool else a.sources, purpose=purpose, faceup_kind=kind,
                                  number=x110b or 0, original_cost=cost_text if x110b is not None else None)
        return
    from app.rules import chosen_forms95

    if chosen_forms95.prepare_up(plan, card, actor=plan.actor, kind=kind):
        return
    plan.do({"type": "face_down", "card_ids": [card.id], "face_down": False})
    turned_up(plan, card)
    plan.rules.passed = []
    if kind == "megamorph":  # 702.37b, 708.11: the counter is put on as it's turned face up (the counter choke point)
        from app.rules import replace as replace_effects

        replace_effects.put_counters(plan, [(card.id, "+1/+1", 1)], by=plan.actor, then={"do": "face_up_done"})


def from_command_zone(card: CardInstance, player: str) -> bool:
    return card.zone == zone_key(player, "command") and card.commander_key is not None and card.owner == player


def cast_grant(state: GameState, player: str, card: CardInstance, ch: Characteristics, info: CardInfo | None, *,
               free: bool = False, slot: str | None = None, via: str | None = None,
               alternative_key: str | None = None) -> permissions.Grant | None:
    """How ``player`` may cast this card from where it is (601.3): from their hand, their commander
    from the command zone, flashback from their graveyard, or a permission (app/rules/permissions):
    a static ability on the table or one an effect granted. ``free``: they want to use a "without
    paying its mana cost" permission (118.9) — an alternative cost, which is optional (118.9b), so
    it is never applied to a plain cast: without the opt-in only paid ways count, and a card that
    only a free permission lets them cast isn't castable that way."""
    from app.rules import keyword_actions

    if card.zone != zone_key(player, "graveyard") and any(d.get("only") for d in scripts.definitions(ch).values()):
        return None  # -- cant restrictions (wave 50G) -- Haakon, Stromgald Scourge: "You may cast this card from your graveyard, but not from anywhere else."
    how = "hand" if card.zone == zone_key(player, "hand") else "command" if from_command_zone(card, player) else \
        "flashback" if from_graveyard(card, player, ch, state, info) else None
    if how is None and card.is_token and (perm := keyword_actions.prepared_permanent(state, card.id)) is not None \
            and perm.controller == player:
        how = "prepared"  # -- prepared (wave 13C) -- 722.3c: its controller may cast the copy in exile
    found = permissions.grants(state, player, card, ch, info, verb="cast") if info is not None else []
    from app.rules import required_keyword79, required_mutate75

    if not free and via is None and slot is None and required_mutate75.selected(state, player, card, ch, info, alternative_key):
        how = 'mutate'  # Required native alternative; unrelated permissions remain selectable independently.
    if not free and via is None and slot is None and (required79 := required_keyword79.selected(state, player, card, ch, info, alternative_key)) is not None:
        how = required79
    flash = any(g.flash and (free or not g.flash_requires_free) for g in found)
    if how is None and info is not None and card.zone == zone_key(player, "foretell") and not free and card.owner == player \
            and _foretell_offers(state, player, card, ch, info):
        how = "foretell"  # -- hidden exile (wave 18A) -- 702.143a: cast from the foretell exile for the foretell cost (only that way)
    if "aftermath" in ch.keywords:  # -- static_other sweep (wave 16B) -- 702.127a: "can't be cast from any zone other than a graveyard"
        return permissions.Grant("flashback", flash=flash) if how == "flashback" else None
    from app.rules import paid_effect_costs

    if not free and paid_effect_costs.active(state, player, card.id):
        pending = state.rules.free_cast_then if state.rules is not None else None
        spend = (pending.get("e") or {}).get("spend", "") if pending is not None else ""
        return permissions.Grant("resolving", spend=spend, alt_mana=((pending.get("e") or {}).get("effect_mana_cost") or "") if pending else "")  # 608.2g: the saved effect supplies any mandatory alternative.
    if how is None and info is not None and card.zone == zone_key(player, "graveyard") and not free \
            and not any(g.zone_ok and not g.free for g in found) and _escape_offers(state, player, card, ch, info):
        how = "escape"  # -- escape (wave 5I) -- 702.138a: cast from the graveyard for an escape cost (only that way)
    if free:
        # (wave 3C) a free permission with no zone of its own ("you may cast Dragon spells without paying")
        # covers the zones a card can be cast from anyway
        ways = [g for g in found if g.free and (g.zone_ok or how is not None)]
    else:
        ways = [g for g in found if g.zone_ok and not g.free]
        if how is not None:
            return permissions.Grant(how, flash=flash)
    if slot is not None:  # -- cast permissions (wave 30Q) -- the permanent type the caster chose to use up (Muldrotha)
        ways = [g for g in ways if g.slot == slot]
    if via is not None:  # -- cast permissions (wave 32D) -- the limited permission the caster named (601.2)
        ways = [g for g in ways if via in (g.use, g.choice_key)]
    if not ways:
        return None
    # (a way with no extra cost to pay first: the cheaper of two permissions; -- review 30c -- then one with no rider on what it becomes: Karador's
    # before Serra Paragon's "it gains … exile it", Edgar's "enters tapped")
    best = min(ways, key=lambda g: (bool(g.extra), g.generic_extra, bool(g.enters), not bool(g.spell_keywords)))
    return permissions.with_choices(replace(best, flash=flash or best.flash), ways, compare_costs=free)  # (-- wave 32D -- a limited default: the other limited uses, to ask which)


def _foretell_offers(state: GameState, player: str, card: CardInstance, ch: Characteristics, info: CardInfo) -> list[Any]:
    """-- hidden exile (wave 18A) -- the foretell costs this foretold card can be cast for now (alt_costs.offers: tag "foretell")."""
    from app.rules import alt_costs

    return alt_costs.offers(state, player, card, ch, info)


def _escape_offers(state: GameState, player: str, card: CardInstance, ch: Characteristics, info: CardInfo) -> list[Any]:
    """-- escape (wave 5I) -- the escape costs this card can be cast for now (app/rules/escape.py)."""
    from app.rules import escape

    return escape.offers(state, player, card, ch, info)


def cast_problem(state: GameState, player: str, card: CardInstance, ch: Characteristics, *,
                 check_priority: bool = True, info: CardInfo | None = None, free: bool = False, sneak: bool = False,
                 announced: bool = False, alternative_key: str | None = None,
                 optional_keys: tuple[str, ...] = ()) -> str | None:
    """Why ``player`` can't cast ``card`` right now (costs aside), or None. ``sneak``: cast for its sneak cost (702.190a), which
    is cast at instant timing (the offer itself exists only in your declare blockers step: alt_costs.sneak_timing)."""
    r = state.rules
    if r is None:
        return "Rules automation is off"
    if not ch.types:
        return "Fyodor doesn't know what that card is. Use the table tools."
    if ch.is_land:  # 305.9: a land card is played, never cast
        return f"{ch.name or 'That card'} is a land: play it instead"
    grant = cast_grant(state, player, card, ch, info, free=free, alternative_key=alternative_key)
    if grant is None:
        if free:
            return "Nothing lets you cast that without paying its mana cost now"
        return "You can cast spells from your hand, and your commander from the command zone"
    if check_priority and grant.how != "resolving" and (r.priority != player or r.decision is not None):
        return "You don't have priority"
    if "Legendary" in ch.supertypes and ch.is_instant_or_sorcery and not _controls_legendary(state, player, info):
        # 205.4e: a legendary instant or sorcery needs a legendary creature or planeswalker
        return f"{ch.name} needs you to control a legendary creature or planeswalker"
    # -- cast limits (wave 5E) -- 601.3: no rule or effect prohibits it
    from app.rules import cast_limits

    limited = cast_limits.cast_problem(state, player, card, ch, info, resolving=grant.how == "resolving")
    if limited:
        return limited
    from app.rules import cast_timing  # -- cast timing (wave 7A) -- "Cast this spell only during …" (601.3)

    if (timed := cast_timing.problem(state, player, card, ch, info)) is not None:
        return timed
    if grant.sorcery:  # -- keywords (wave 15E) -- plot 702.170d: during your main phase while the stack is empty
        if state.turn.active_player != player or state.turn.phase not in MAIN_PHASES or state.zones.get(STACK):
            return f"{ch.name} can only be cast in your main phase while the stack is empty (plot)"
        return None
    timing = None if sneak else timing_problem(state, player, ch, grant)  # -- keywords (wave 30I) -- 702.190a
    fl = flash_if(ch) if timing else None  # (wave 22F: 601.3b-c, decided once its targets / cost / X are chosen)
    if fl is not None and fl.get('optional'):
        from app.rules import casting_timing_permissions

        if info is None or not casting_timing_permissions.optional_flash(state, player, card, ch, info, fl, announced=announced, selected=optional_keys):
            fl = None
    if fl is not None and ("targets" not in fl or (info is not None and _flash_target_exists(state, player, card, fl["targets"], info))) \
            and ("offering" not in fl or (not free and info is not None and offering_paid(state, player, card, ch, info))):  # (-- offering (wave 51H) -- 702.48a: only by sacrificing one, never cast free)
        return None  # (review 22F: "if it targets a commander" with no such object to target isn't offered: the target choice would be a dead end)
    if timing and not free and info is not None:
        from app.rules import casting_timing_permissions

        if casting_timing_permissions.alternative_flash(state, player, card, ch, info, announced=announced, key=alternative_key):
            return None
    return timing


def flash_sac(state: GameState, player: str, card: CardInstance, ch: Characteristics, info: CardInfo | None) -> bool:
    """-- flash auras (wave 46B) -- "If you cast it any time a sorcery couldn't have been cast" (Ward of Lights): its own flash permission, used while a sorcery couldn't
    be cast (not your main phase, or the stack isn't empty: 307.1). Ruling 2022-12-08: any other way of casting it then (a flash of its own or from another effect)
    doesn't sacrifice it. ponytail: with two sources of flash the engine can't tell which the player used; it takes the other, never a wrong sacrifice."""
    if info is None or not any(d.get("flash_sac") for d in scripts.definitions(ch).values()):
        return False
    t = state.turn
    if (t.active_player == player and t.phase in MAIN_PHASES and not state.zones.get(STACK)) or "Instant" in ch.types or ch.has_flash:
        return False
    own = f"{ch.name}: as though it had flash"
    return not any(g.flash and g.label != own for g in permissions.grants(state, player, card, ch, info, verb="cast"))


def _flash_target_exists(state: GameState, player: str, card: CardInstance, key: str, info: CardInfo) -> bool:
    from app.rules import cost_changes

    return cost_changes.targets_fit(permissions._view(state, player, info), card, player, key, tuple(state.cards))


def timing_problem(state: GameState, player: str, ch: Characteristics, grant: Any) -> str | None:
    if grant.how == "resolving":
        return None
    if "Instant" in ch.types or ch.has_flash or grant.flash:  # (601.3b: as though it had flash)
        return None
    if state.turn.active_player != player:
        return f"{ch.name} can only be cast during your turn"
    if state.turn.phase not in MAIN_PHASES:
        return f"{ch.name} can only be cast in a main phase"
    if state.zones.get(STACK):
        return f"{ch.name} can only be cast while the stack is empty"
    return None


def flash_if(ch: Characteristics) -> dict[str, Any] | None:
    """-- casting costs (wave 22F) -- 601.3b-c: the card's own "You may cast this spell as though it had flash if it targets …
    / you pay {2} more / X is 3 or less", which counts only when the spell couldn't be cast now without flash."""
    return next((d["flash_if"] for d in scripts.definitions(ch).values() if d.get("static") == "permission" and d.get("flash_if")), None)


def offering_paid(state: GameState, player: str, card: CardInstance, ch: Characteristics, info: CardInfo) -> list[M.ManaCost]:
    """-- offering (wave 51H) -- 702.48a: the mana cost of each permanent ``player`` could sacrifice for the offering of this card ([] when it has none, or nothing to sacrifice)."""
    part = offering.component(q) if (q := (flash_if(ch) or {}).get("offering")) else None
    view = permissions._view(state, player, info)
    return [] if part is None else [M.parse_cost(view.ch(view.state.cards[c]).mana_cost) for c in cost_payment.candidates(view, part, player, card)]


def _controls_legendary(state: GameState, player: str, info: CardInfo | None) -> bool:
    if info is None:
        return False  # (can't tell: refuse rather than allow a cast the rules forbid)
    from app.rules.layers import derive

    for cid in state.zones.get(zone_key(player, "battlefield"), []):
        card = state.cards[cid]
        if card.controller != player:
            continue
        ch = derive(state, card, chars.of(card, info), info)
        if "Legendary" in ch.supertypes and (ch.is_creature or "Planeswalker" in ch.types):
            return True
    return False


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
        return affinity_pred(m["what"].lower())
    return None


OUTLAWS = frozenset({"Assassin", "Mercenary", "Pirate", "Rogue", "Warlock"})  # -- cast keywords (wave 43D) -- 700.12


def affinity_pred(what: str) -> Any:
    """The predicate on permanents (their characteristics, the permanent) of "affinity for <what>" (lower case), or None for a wording we don't know."""
    if what in _AFFINITY_TYPES:
        t = _AFFINITY_TYPES[what]
        return lambda c, _card: t in c.types
    if what == "artifact creatures":
        return lambda c, _card: "Artifact" in c.types and c.is_creature
    # -- cast keywords (wave 43D) -- 702.41a "for each [text] you control": tokens (111), historic permanents (700.6), outlaws (700.12)
    if what == "tokens":
        return lambda _c, card: card.is_token
    if what == "historic permanents":
        return lambda c, _card: "Legendary" in c.supertypes or "Artifact" in c.types or "Saga" in c.subtypes
    if what == "outlaws":
        return lambda c, _card: bool(OUTLAWS & set(c.subtypes))
    if what == "snow lands":  # -- multi (wave 100M) -- Icebreaker Kraken (205.4a: snow is a supertype)
        return lambda c, _card: "Snow" in c.supertypes and "Land" in c.types
    from app.rules.creature_types import CREATURE_TYPES
    from app.rules.protection import _PLURALS
    from app.rules.selectors import _IRREGULAR

    sub = _IRREGULAR.get(what) or _PLURALS.get(what) or (what[:-1] if what.endswith("s") and what != "plains" else what).title()
    if sub in CREATURE_TYPES or sub in _AFFINITY_SUBTYPES:
        return lambda c, _card: sub in c.subtypes
    return None


def affinity_discount(state: GameState, player: str, ch: Characteristics, info: CardInfo, card: CardInstance | None = None) -> int:
    # Each affinity instance is cumulative, including one granted by the selected permission.
    preds = [affinity_pred(m['what'].lower()) for ability in ch.abilities
             if ability.kind == 'keywords' and 'affinity' in ability.keywords
             and (m := AFFINITY.fullmatch(ability.text.strip().rstrip('.'))) is not None]
    preds = [predicate for predicate in preds if predicate is not None]
    if card is not None:  # -- static_other sweep (wave 17C) -- "Artifact spells you cast have affinity for artifacts." (cast_limits)
        from app.rules import cast_limits

        preds += [affinity_pred(w) for w in cast_limits.granted_affinities(state, player, card, ch, info)]
    if not preds:
        return 0
    from app.rules.layers import derive

    mine = [(derive(state, c, chars.of(c, info), info), c) for c in state.cards.values()
            if c.zone == zone_key(player, "battlefield") and c.controller == player]
    return sum(1 for pred in preds for c, card_ in mine if pred(c, card_))


def spell_cost(state: GameState, card: CardInstance, ch: Characteristics, x: int = 0,
               info: CardInfo | None = None, *, player: str | None = None, alternative: M.ManaCost | None = None,
               free: bool = False, kicker: int = 0, additional: tuple[M.ManaCost, ...] = (),
               face_down: bool = False, targets: tuple[str, ...] = (), reduce: int = 0,
               flashback_choice: int | None = None, mana_symbols: list[str] | None = None,
               capture: list[Any] | None = None, announced_kicker77: bool = False) -> M.ManaCost:
    """The total cost to cast (601.2f), in the rules' order: the mana cost (with X) or the
    alternative cost — flashback from the graveyard, evoke, dash, a face-down {3}, or {0} for
    "without paying its mana cost" (118.9) — plus additional costs (kicker 702.33a, buyback: 118.8)
    and cost increases (commander tax 903.8, "cost {N} more"), minus cost reductions (affinity
    702.41, "cost {N} less", the spell's own; 118.7a: generic only, never below {0}). Additional
    costs, increases and reductions apply to an alternative cost too (118.9d)."""
    player = player or card.owner
    paying_flashback = False
    if free:
        raw_base = M.ManaCost()
    elif alternative is not None:
        raw_base = alternative
    else:
        in_graveyard = card.zone == zone_key(card.owner, "graveyard")
        from app.rules import flashback_choices

        ways = flashback_choices.options(state, card, ch, info) if in_graveyard else []
        flashback = flashback_choices.selected(ways, flashback_choice)[0] if ways else None
        raw_base = M.parse_cost(flashback or ch.mana_cost)
        paying_flashback = flashback is not None
    extras = list(additional)
    if kicker:
        extras.append(kicker_extra(ch, kicker, face_down=face_down))
    from app.rules import waterbend102

    if not face_down:
        extras.append(waterbend102.mana(ch))
    selected_cost_has_x = bool(raw_base.x or any(extra.x for extra in extras))
    base = raw_base.with_x(x)
    extras = [extra.with_x(x) for extra in extras]
    tax = state.players[card.owner].commander_tax.get(card.commander_key, 0) \
        if from_command_zone(card, card.owner) and card.commander_key else 0
    from app.rules import cost_statics101

    if cost_statics101.replaces_commander_tax(card, ch):
        tax = 0
    affinity = (affinity_discount(state, player, ch, info, card) if info is not None else 0) + reduce  # (reduce: emerge, 18E)
    if paying_flashback and info is not None:
        from app.rules import flashback_costs

        extra_tax, discount = flashback_costs.changes(state, player, info)
        tax += extra_tax
        from app.rules import conditional_own_discounts

        affinity += discount + conditional_own_discounts.printed_flashback_discount(state, player, card, ch, info, flashback_choice)
    from app.rules import first_kicked_costs77

    if info is not None and kicker and (actual_kicker77 := kicker_cost(ch.abilities)) is not None and not actual_kicker77.entwine:
        if announced_kicker77:
            first_kicked_costs77.guard(state, player, info)
        affinity += first_kicked_costs77.discount(state, player, info)
    # -- cost changers (wave 44D) -- 107.3f, 202.3e: the spell being cast has the X announced for it, so a cost changer reading its mana value ("spells with mana value 4 or
    # greater cost {X} less") counts it (Thryx ruling 2020-01-24)
    captured: list[Any] = capture if capture is not None else []
    total = permissions.total_cost(state, player, card, replace(ch, mana_value=ch.mana_value + x * ch.mana_cost.count("{X}")) if x else ch, info, base=base,
                                   additional=tuple(extras), tax=tax, affinity=affinity, targets=targets,
                                   symbols=mana_symbols, capture=captured)
    captured[-1] = replace(captured[-1], selected_cost_has_x=selected_cost_has_x)
    from app.rules import (
        cast_limits,  # -- static_other sweep (wave 19A) -- Oath of Nissa: how the mana may be spent
    )
    mode = cast_limits.spend_mode(state, player, card, ch, info)
    from app.rules import spell_cost_stages, spell_mana_floor

    if capture is None and spell_mana_floor.minimum(state, info):
        prepared = captured[0]
        choices = mana_symbols if mana_symbols is not None else [slot[0] for slot in spell_cost_stages.symbols(prepared.raw)]
        total = spell_mana_floor.apply(state, info, prepared.evaluate(choices))
    return M.spend_as(total, mode) if mode and capture is None else total


def spell_cost_ways(state: GameState, card: CardInstance, ch: Characteristics, *, info: CardInfo,
                    finalize: Any = None, x_payments: list[dict[str, Any] | None] | None = None,
                    selected_costs: list[bool | None] | None = None, **kwargs: Any) -> list[tuple[M.ManaCost, int]]:
    """Hint payments, with every concrete announcement evaluated before reductions/floors."""
    from app.rules import cast_limits, spell_cost_stages, spell_mana_floor

    captured: list[Any] = []
    legacy = spell_cost(state, card, ch, info=info, capture=captured, **kwargs)
    prepared = captured[0]
    floor = spell_mana_floor.minimum(state, info)
    mode = cast_limits.spend_mode(state, kwargs.get('player') or card.owner, card, ch, info)
    ways = [(prepared.evaluate(w), 2 * len(spell_cost_stages.life_symbols(prepared.raw, w)))
            for w in spell_cost_stages.variants(prepared.raw)] if floor else [(legacy, 0)]
    out = []
    for cost, life in ways:
        for final in finalize(cost) if finalize is not None else [cost]:
            x_maximum = min(kwargs.get('x', 0), final.generic)
            final = spell_mana_floor.apply(state, info, final) if floor else final
            final = M.spend_as(final, mode) if floor and mode else final
            from app.rules import cost_statics101

            out.append((final, life + cost_statics101.commander_life(state, card, ch)))
            if selected_costs is not None:
                selected_costs.append(prepared.selected_cost_has_x)
            if x_payments is not None:
                from app.rules import x_mana_restrictions

                reduction = prepared.raw.generic - prepared.evaluate().generic
                x_payments.append(x_mana_restrictions.metadata(ch.oracle_text, kwargs.get('x', 0), reduction, final, mode=mode, maximum=x_maximum))
    return out


def additional_problem(plan: Plan, extra: AbilityCost, card: CardInstance, player: str) -> str | None:
    """(wave 3$) Why a spell's additional cost can't be paid now (118.3: no partial payments; 119.4: life), or None."""
    if extra.either:  # -- static wordings (wave 6E) -- a choice: payable when one side is (app/rules/either_costs.py)
        from app.rules import either_costs

        return either_costs.problem(plan, extra, card, player)
    if extra.life and plan.state.players[player].life < extra.life:
        return f"You can't pay {extra.life} life"
    from app.rules import life_lock  # -- can't lose life (wave 29D) -- 119.8, 614.17b

    if (why := life_lock.pay_problem(plan.state, plan.info, player, extra.life)) is not None:
        return why
    return cost_payment.problem(plan, extra, card, player)


def life_x_problem(plan: Plan, extra: AbilityCost, a: Any, player: str) -> str | None:
    """-- X sized by a count (wave 4K) -- "As an additional cost to cast this spell, pay X life.": X is announced as the
    spell is cast (601.2b, 107.3a) and can't be more than the caster's life (119.4; 119.4b: 0 always can be paid)."""
    if extra.x_chosen and a.x_value is None:  # -- X sized by a count (wave 25D) -- "discard X cards": the announced X sizes the cost (107.3a, 601.2b)
        return "Choose a value for X (the number of objects to pay)"
    if any(c.counters_x for c in extra.components) and a.x_value:  # -- blight X (wave 110C) -- "X can't be greater than the greatest toughness among creatures you control" (601.2b)
        from app.rules import values as _values

        best = max((_values._stat_of(ch, "toughness") or 0 for c in plan.state.cards.values()
                    if c.zone == f"{player}:battlefield" and "Creature" in (ch := plan.ch(c)).types), default=0)
        if a.x_value > best:
            return f"X can't be greater than {best}, the greatest toughness among your creatures"
    if not extra.life_x:
        return None
    if a.x_value is None:
        return "Choose a value for X (the life to pay)"
    if a.x_value > 0 and plan.state.players[player].life < extra.life + a.x_value:
        return f"You can't pay {a.x_value} life"
    from app.rules import life_lock  # -- can't lose life (wave 29D) -- 119.8, 119.4b: only 0 life can be paid

    if (why := life_lock.pay_problem(plan.state, plan.info, player, a.x_value)) is not None:
        return why
    from app.rules import prohibitions

    if a.x_value > 0 and (why := prohibitions.life_banned(plan.state, plan.info)):  # -- review 22B -- 119.4b: only 0 life can be paid
        return f"{why}: players can't pay life to cast spells"
    return None


def castable(state: GameState, player: str, card: CardInstance, info: CardInfo, *, check_priority: bool = True) -> bool:
    from app.rules import dynamic_zone_keyword_costs56

    faces = dynamic_zone_keyword_costs56.foretell_faces(state, player, card, info) or ((0, 1) if chars.is_two_spell_card(card, info) else (None,))
    for face in faces:
        ch = chars.as_cast(card, info, face)
        from app.rules import text_global_word71

        ch = text_global_word71.prospective(state, card, ch, info)
        if cast_problem(state, player, card, ch, check_priority=check_priority, info=info) is not None:
            continue
        manual = state.rules is not None and state.rules.card_mode(card.id) == "manual"
        extra = None if manual else costs.spell_additional_cost(ch.abilities)
        if extra is not None and additional_problem(permissions._view(state, player, info), extra, card, player):
            continue  # (wave 3$) the additional cost can't be paid: not offered
        grant = cast_grant(state, player, card, ch, info)
        from app.rules import permission_spell_keywords, wave110a_grants

        ch = permission_spell_keywords.apply(ch, grant)
        ch = wave110a_grants.with_replicate(state, player, card, ch, info)  # -- grants (wave 110A) --
        grant_extra = costs.parse_additional_cost(grant.extra) if grant is not None and grant.extra else None
        if grant_extra is not None and additional_problem(permissions._view(state, player, info), grant_extra, card, player):
            continue  # -- cast permissions (wave 30Q) -- the permission's own additional cost ("by sacrificing a land") can't be paid: not offered
        if grant is not None and grant.how in ("escape", "foretell"):  # -- escape (wave 5I) -- only for an escape cost (702.138a)
            if alt_castable(state, player, card, info, check_priority=check_priority, face=face):
                return True
            continue
        from app.rules import flashback_choices

        fb_ways = flashback_choices.options(state, card, ch, info) if grant is not None and grant.how == "flashback" and not manual else []
        # -- keywords (wave 30E) -- spree / tiered: at least one mode, so some mode's cost is paid with the rest (702.172a, 702.183a)
        spree: list[M.ManaCost | None] = [] if manual or not ({"spree", "tiered"} & set(ch.keywords)) else [
            M.parse_cost(m["cost"]) for m in (scripts.spell_definition(ch) or {}).get("modes", ()) if m.get("cost")]
        for fb_index in range(len(fb_ways)) if fb_ways else [None]:
            fb_more = fb_ways[fb_index][1] if fb_index is not None else None
            if fb_more is not None and additional_problem(permissions._view(state, player, info), fb_more, card, player):
                continue
            for mode_cost in spree or [None]:
                off_only = grant is not None and "offering" in (flash_if(ch) or {}) and timing_problem(state, player, ch, grant) is not None

                paid_offerings = offering_paid(state, player, card, ch, info)

                def finish(cost: M.ManaCost, paid_offerings: Any = paid_offerings, off_only: bool = off_only) -> list[M.ManaCost]:
                    return [*(offering.reduce(cost, paid) for paid in paid_offerings), *([] if off_only else [cost])]

                selected_costs: list[bool | None] = []
                cost_ways = spell_cost_ways(state, card, ch, info=info, player=player, free=grant is not None and grant.free,
                                                    alternative=M.parse_cost(grant.alt_mana) if grant is not None and grant.alt_mana else None,
                                                    flashback_choice=fb_index, targets=_hint_targets(ch),
                                                    additional=tuple(([mode_cost] if mode_cost is not None else []) +
                                                                     ([M.ManaCost(generic=grant.generic_extra)] if grant is not None and grant.generic_extra else [])), finalize=finish,
                                                    selected_costs=selected_costs)
                for (way, life_due), cost_x in zip(cost_ways, selected_costs, strict=True):
                    if grant is not None and grant.spend:
                        way = M.spend_as(way, grant.spend)
                    from app.rules import waterbend102

                    hinted_way=waterbend102.hint(state,player,card,ch,info,way)
                    if can_pay(state, player, hinted_way, info, purpose=Purpose(spell=ch, card=card.id, zone=card.zone, player=player,
                               spell_object=_spell_reference(state, card), selected_cost_has_x=cost_x),
                               reserve=(extra.life if extra is not None else 0) + (grant_extra.life if grant_extra is not None else 0) + (fb_more.life if fb_more is not None else 0) + life_due):
                        return True
    return False


def announces_x(card: CardInstance, info: CardInfo) -> bool:
    """-- X announced (wave 24D) -- 107.3a, 601.2b: does casting this card (either face) ask for X: {X} in its mana cost, or
    an additional cost sized by X ("pay X life", "discard X cards"…)? The hint lists only the viewer's own cards."""
    for face in (0, 1) if chars.is_two_spell_card(card, info) else (None,):
        ch = chars.as_cast(card, info, face)
        extra = costs.spell_additional_cost(ch.abilities)
        if M.parse_cost(ch.mana_cost).x or (extra is not None and (extra.life_x or extra.x_chosen)):
            return True
    return False


def announces_kicker_x(card: CardInstance, info: CardInfo) -> bool:
    """-- cast keywords (wave 43D) -- 107.3a: does a kicked cast of this card ask for X ("Kicker {X}")? The hint lists only the viewer's own cards."""
    return any((k := kicker_cost(chars.as_cast(card, info, face).abilities)) is not None and k.x
               for face in ((0, 1) if chars.is_two_spell_card(card, info) else (None,)))


def _hint_targets(ch: Characteristics) -> tuple[str, ...]:
    """-- review (Codex) -- the targets a castability hint assumes: none for a spell without targets, else the best
    case for "spells that target …" cost changes (cost_changes.ANY_TARGET)."""
    from app.rules import cost_changes

    return cost_changes.ANY_TARGET if "target" in ch.oracle_text.lower() else ()


# -- cost changers (wave 4I) --
def alt_castable(state: GameState, player: str, card: CardInstance, info: CardInfo, *,
                 check_priority: bool = True, face: int | None = None) -> list[dict[str, Any]]:
    """The alternative costs (118.9) ``player`` could cast this card for right now, each with what the intent's
    ``alt_cost`` names: its condition holds, and the whole total cost (601.2f) can be paid (118.3)."""
    from app.rules import alt_costs  # (a leaf over this module)

    out: list[dict[str, Any]] = []
    if chars.is_two_spell_card(card, info) or state.rules is None or state.rules.card_mode(card.id) == "manual":
        return out  # (a split card / adventure: which half isn't part of the hint)
    ch = chars.as_cast(card, info, face)
    from app.rules import text_global_word71

    ch = text_global_word71.prospective(state, card, ch, info)
    from app.rules import required_keyword79, required_mutate75

    required_mutate = required_mutate75.candidate(state, player, card, ch) or required_keyword79.kind(state, player, card, ch) is not None
    blocked = cast_problem(state, player, card, ch, check_priority=check_priority, info=info) is not None
    if blocked and not required_mutate and cast_problem(state, player, card, ch, check_priority=check_priority, info=info, sneak=True) is not None:
        return out
    grant = cast_grant(state, player, card, ch, info)
    in_graveyard = card.zone == zone_key(player, "graveyard")  # -- escape (wave 5I) -- from there: escape costs only
    if grant is not None and grant.how == "flashback" and not in_graveyard:
        return out  # (flashback is an alternative cost already: 118.9a)
    view = permissions._view(state, player, info)
    for offer in alt_costs.offers(state, player, card, ch, info):
        if required_mutate:
            grant = cast_grant(state, player, card, ch, info, alternative_key=offer.key)
            blocked = cast_problem(state, player, card, ch, check_priority=check_priority, info=info, alternative_key=offer.key) is not None
            if grant is None:
                continue
        if grant is not None and timing_problem(state, player, ch, grant) is not None and not offer.flash and offer.tag != "sneak":
            continue
        if blocked and offer.tag != "sneak":
            continue  # -- keywords (wave 30I) -- timing stops a plain cast; only a sneak cost (702.190a) is cast at instant speed
        if in_graveyard and not offer.escape and grant is not None and grant.how in ("escape", "flashback"):
            continue  # (escape and flashback are the cast's own alternative costs: 118.9a)
        extra = alt_costs.merged(costs.spell_additional_cost(ch.abilities), offer.alt.cost)
        if extra is not None and additional_problem(view, extra, card, player):
            continue
        selected_costs: list[bool | None] = []
        ways = spell_cost_ways(state, card, ch, info=info, player=player, alternative=alt_costs.bind_template(offer, x=0).alt.mana_cost,
                               additional=(M.ManaCost(generic=grant.generic_extra),) if grant is not None and grant.generic_extra else (),
                               targets=_hint_targets(ch), selected_costs=selected_costs)
        if any(can_pay(state, player, cost, info, purpose=Purpose(spell=ch, card=card.id, zone=card.zone, player=player,
                                                                spell_object=_spell_reference(state, card),
                                                                selected_cost_has_x=True if offer.template_mana_has_x else cost_x, alternative=offer.tag,
                                                                producer_requirement=offer.producer_requirement),
                       reserve=(extra.life if extra is not None else 0) + life_due)
               for (cost, life_due), cost_x in zip(ways, selected_costs, strict=True)):
            out.append({"id": offer.key, "label": offer.label, **({"x": True} if alt_costs.announces_x(offer) else {})})
    return out


def optional_castable(state: GameState, player: str, card: CardInstance, info: CardInfo) -> list[dict[str, str]]:
    """The optional additional costs (Defiler of Vigor) ``player`` could pay casting this card right now, each alone."""
    from app.rules import cost_changes

    out: list[dict[str, str]] = []
    if chars.is_two_spell_card(card, info) or state.rules is None or state.rules.card_mode(card.id) == "manual":
        return out
    ch = chars.as_cast(card, info, None)
    from app.rules import text_global_word71

    ch = text_global_word71.prospective(state, card, ch, info)
    if ch.is_land or cast_problem(state, player, card, ch, info=info) is not None:
        return out
    grant = cast_grant(state, player, card, ch, info)
    for offer in cost_changes.optional_offers(state, player, card, ch, info):
        if state.players[player].life < offer.life or (offer.life and spendable_life(state, player, info) == 0):  # (wave 22B: 119.4)
            continue
        if offer.kind and cost_payment.problem(permissions._view(state, player, info),
                                               costs.AbilityCost(components=(cost_changes.keyword_component(offer),)), card, player):
            continue  # (-- static_other sweep (wave 17C) -- conspire / teamwork: the creatures to tap aren't there)
        part = cost_changes.keyword_component(offer) if offer.kind in ("reduce", "bargain") or (offer.kind == "evidence" and offer.n) else None  # -- cost reductions paid with objects (wave 47C) -- the most the objects it can take
        paid_offerings = offering_paid(state, player, card, ch, info) if offer.kind == "offering" else []

        def finish(cost: M.ManaCost, mana: Any = offer.mana, paid: Any = paid_offerings) -> list[M.ManaCost]:
            cost = cost_changes.reduce_only(cost, (mana,))
            return [offering.reduce(cost, p) for p in paid] if paid else [cost]

        try:
            selected_costs: list[bool | None] = []
            ways = spell_cost_ways(state, card, ch, info=info, player=player,
                                   free=grant is not None and grant.free,
                                   alternative=M.parse_cost(grant.alt_mana) if grant is not None and grant.alt_mana else None,
                                   additional=(M.ManaCost(generic=grant.generic_extra),) if grant is not None and grant.generic_extra else (),
                                   reduce=part.reduces * (min(1, len(cost_payment.candidates(permissions._view(state, player, info), part, player, card)))
                                                          if offer.kind in ("bargain", "evidence") else len(cost_payment.candidates(permissions._view(state, player, info), part, player, card)))
                                   if part is not None else 0, finalize=finish, selected_costs=selected_costs)
        except ActionError:
            continue
        if any(can_pay(state, player, way, info, purpose=Purpose(spell=ch, card=card.id, zone=card.zone, player=player,
                                                                spell_object=_spell_reference(state, card),
                                                                selected_cost_has_x=cost_x), reserve=offer.life + life_due)
               for (way, life_due), cost_x in zip(ways, selected_costs, strict=True)):
            out.append({"id": offer.source, "label": offer.label})
    return out
# -- end cost changers (wave 4I) --


def resume_free_multikicker(plan: Plan, d: Any, chosen: list[str]) -> None:
    """A typed count continues the same native cast; all actual costs remain payable normally."""
    from app.rules.engine import INTENTS

    count = int(chosen[0])
    if not 0 <= count <= 1000:
        raise ActionError("Choose a multikicker count from 0 to 1000 (platform numeric range)")
    intent = A.parse_action(d.resume["intent"])
    assert isinstance(intent, A.CastSpell)
    if plan.oid(intent.card_id) != d.resume["card_object"]:
        raise ActionError("That spell is a different object now")
    intent.kicker = count
    plan.rules.priority = d.player
    plan.rules.passed = []
    INTENTS[intent.type](plan, intent)


# -- cast without paying (wave 3C) --
def free_castable(state: GameState, player: str, card: CardInstance, info: CardInfo, *, check_priority: bool = True) -> bool:
    """Whether any legal alternative permission can pay this face's required costs now."""
    from app.rules import alt_costs, spell_mana_floor

    faces = (0, 1) if chars.is_two_spell_card(card, info) else (None,)
    for face in faces:
        ch = chars.as_cast(card, info, face)
        from app.rules import text_global_word71

        ch = text_global_word71.prospective(state, card, ch, info)
        if cast_problem(state, player, card, ch, info=info, free=True, check_priority=check_priority) is not None:
            continue
        manual = state.rules is not None and state.rules.card_mode(card.id) == "manual"
        printed = None if manual else costs.spell_additional_cost(ch.abilities)
        grant = cast_grant(state, player, card, ch, info, free=True)
        for candidate in (grant, *grant.among) if grant is not None else (None,):
            extra = printed
            if (life_more := permissions.life_cost(candidate, ch)) is not None:
                extra = alt_costs.merged(extra, life_more)
            if extra is not None and additional_problem(permissions._view(state, player, info), extra, card, player):
                continue
            if spell_mana_floor.minimum(state, info) and not any(
                    can_pay(state, player, due, info, purpose=Purpose(spell=ch, card=card.id, zone=card.zone, player=player,
                            spell_object=_spell_reference(state, card)),
                            reserve=(extra.life if extra is not None else 0) + life_due)
                    for due, life_due in spell_cost_ways(state, card, ch, info=info, player=player, free=True)):
                continue
            return True
    return False


def free_cast_problem(plan: Plan, player: str, card: CardInstance, ch: Characteristics, *,
                      paid: bool = False, x: int | None = None) -> str | None:
    """-- review (wave 29B) -- why ``player`` can't cast this half / face (``ch``) of a card the engine lets them cast as an effect resolves
    (``cast_free``), checked before the choice is offered, so that no answer is a dead end: 205.4e (a legendary instant or sorcery), 700.2a (no
    mode can be chosen), 601.2c (a required target group can't get enough legal targets: the proposal is illegal, 601.5) and 601.2h / 118.9d (a
    mandatory additional cost, "sacrifice a creature", can't be paid). The same checks as ``cast_free``, in the same order; cast_limits'
    prohibitions (601.3) are the caller's. Mana is not checked here: ``can_pay`` doesn't count the mana abilities activated by hand (a Spirit
    Guide, Ashnod's Altar), so a cost increase that can't be paid is met in the payment, where the cast can be cancelled (``_announcing``)."""
    from app.rules import text_global_word71

    ch = text_global_word71.prospective(plan.state, card, ch, plan.info)
    from app.rules import cast_timing

    if (timed := cast_timing.problem(plan.state, player, card, ch, plan.info)) is not None:
        return timed  # CR601.3: a resolving effect's permission does not override a card's own restrictions.
    if paid and x is None and '{X}' in ch.mana_cost:
        from app.rules import source_qualities

        first_problem = None
        for value in source_qualities.candidate_x_values(plan, ch):
            problem = free_cast_problem(plan, player, card, ch, paid=True, x=value)
            if problem is None:
                return None
            first_problem = first_problem or problem
        return first_problem
    from app.rules.targets import as_spell

    quality_source = as_spell(ch, x or 0)
    if "Legendary" in ch.supertypes and ch.is_instant_or_sorcery and not _controls_legendary(plan.state, player, plan.info):
        return f"{ch.name} needs you to control a legendary creature or planeswalker"
    prev, plan.actor = plan.actor, player
    try:
        manual = plan.manual(card)  # (cast by hand: no targets, modes or additional costs read, as in cast_free)
        definition = None if manual else per_opponent.for_cast(plan, card.id, scripts.spell_definition(ch))
        if definition is not None and definition.get("modes"):
            modal = definition["modal"]
            allowed = choosable_modes(plan, definition, card.id, spell=True, source=quality_source)
            if not allowed or (not modal["repeat"] and len(allowed) < modal["min"]):
                return f"{ch.name or 'It'} has no mode you can choose"
        elif not manual:
            from app.rules import static_perm100d  # -- static permanents (wave 100D) -- 601.2c

            aura = static_perm100d.cast_aura(ch, attachments.enchant_selector(ch))
            src = quality_source  # The actual prospective face and announced X.
            from app.rules import kicked_instead
            from app.rules.targets import group_limits

            specs_all = kicked_instead.applicable(scripts.target_groups(definition if aura is None else {"target": {"what": aura}}), 0)
            for spec in specs_all:
                lo, hi = (0, 0) if "x_value" in spec or (spec.get("divide") or {}).get("value") is not None \
                    else group_limits(spec, None)  # (X is 0: 107.3b; "up to X" may be none; wave 34D: nor a total counted as it's cast, that may be 0)
                if hi < lo or player_relative.room(plan, spec, specs_all, lambda w: legal_targets(plan, w, player, src, card.id)) < lo:  # (-- player-relative selectors (wave 53A) --)
                    return f"{ch.name or 'It'} has no legal target"
        extra = None if manual else costs.spell_additional_cost(ch.abilities)
        if extra is None or any(c.kind in _HAND_PARTS for side in (extra, *extra.either) for c in side.components):
            return None  # (a part read from the hand — "reveal a creature card from your hand", "discard a land card" — is hidden: whether
            # the question is skipped mustn't tell the others what the hand holds; that cast is refused in the cast, where it can be cancelled)
        return additional_problem(plan, extra, card, player)
    finally:
        plan.actor = prev


_HAND_PARTS = frozenset({costs.DISCARD, "EXILE_FROM_HAND", "HAND_TO_BOTTOM", "REVEAL_FROM_HAND", costs.BEHOLD, costs.BEHOLD_EXILE})  # (cost_payment._candidates)
# -- end cast without paying (wave 3C) --


def cast_spell(plan: Plan, a: A.CastSpell) -> None:
    require_no_decision(plan)
    card = plan.state.cards.get(a.card_id)
    if card is None:
        raise ActionError("That card isn't here any more")
    if card.zone == zone_key(plan.actor, "graveyard") and a.face is None and not a.fuse and not a.free:  # -- casting extras (wave 18E) -- 702.146a
        from app.rules import disturb

        if disturb.cast_face(plan.state, plan.actor, card, plan.info, a.alt_cost):
            a.face = 1  # cast transformed: the spell is the back face (702.146b, 712.8c)
    if a.face is None and a.alt_cost is not None and not a.fuse and not a.free and not plan.manual(card):  # -- commanders (wave 50C) -- 702.162a: cast converted = the back face is the spell (701.28a, 712.8c)
        from app.rules import alt_costs as _converted

        if any(o.key == a.alt_cost and o.tag == _converted.CONVERTED_TAG for o in _converted.converted_offers(plan.state, plan.actor, card, plan.info)):
            a.face = 1
    ch = chars.as_cast(card, plan.info, a.face, a.fuse)  # split cards / adventures: the half being cast
    from app.rules import text_global_word71

    global_text_prepared71 = bool(text_global_word71.global_changes(plan.state, card.model_copy(update={'zone': 'stack'}), plan.info))
    ch = text_global_word71.prospective(plan.state, card, ch, plan.info)
    from app.rules import paid_effect_costs

    if paid_effect_costs.announce(plan, a, card, ch):
        return
    if a.fuse and (ch.name.count(" // ") != 1 or card.zone != zone_key(plan.actor, "hand")):  # -- static_other sweep (wave 16B) -- 702.102a
        raise ActionError("Only a split card with fuse can be cast as both halves, from your hand")
    if a.alt_cost is not None and (a.free or a.evoke or a.dash or a.awaken or a.face_down):  # -- cost changers (wave 4I) --
        raise ActionError("Only one alternative cost can be applied to a spell (118.9a)")
    if a.free and card.id in plan.rules.free_casts:  # suspend / cascade / rebound / madness: what the engine granted
        cast_free(plan, card, ch, a)
        return
    if a.alt_cost is not None and not plan.manual(card):  # -- keywords (wave 15E) -- bestow 702.103b/d: cast as an Aura spell
        from app.rules import alt_costs as _alt
        from app.rules import bestow

        kinds = {o.tag for o in _alt.offers(plan.state, plan.actor, card, ch, plan.info) if o.key == a.alt_cost}
        if "overload" in kinds:  # -- casting extras (wave 18E) -- 702.96a: "target" is "each" (no targets, 702.96b)
            from app.rules import overload

            ch = overload.overlay(ch)
        if "cleave" in kinds:  # -- keywords (wave 50H) -- 702.148a: the words in square brackets are removed
            from app.rules import cleave

            ch = cleave.overlay(ch)
        bestowed_cast = "bestow" in kinds
        sneaking = "sneak" in kinds  # -- keywords (wave 30I) -- 702.190a
        mutating_cast = "mutate" in kinds  # -- merged permanents (wave 18D) -- 702.140a: a mutating creature spell, targeting a creature
        if bestowed_cast:
            ch = bestow.overlay(ch)
    else:
        bestowed_cast = mutating_cast = sneaking = False
    if a.prototype:  # -- casting extras (wave 18E) -- 702.160a / 718.3a: only the alternative cost, power and toughness are used to cast it
        from app.rules import prototype

        if a.face_down or a.fuse or prototype.parse(ch) is None or plan.manual(card):
            raise ActionError(f"{ch.name or 'That card'} has no prototype the engine can cast it with")
        ch = prototype.overlay(ch)
    face_down_kind = face_down_cast_kind(ch) if a.face_down else None  # -- keyword actions & face-down (wave 3F) --
    if a.face_down:  # morph / disguise: a nameless 2/2 creature spell (disguise: with ward {2}) for {3}
        if face_down_kind is None or card.zone != zone_key(plan.actor, "hand"):
            raise ActionError("Only a card with morph or disguise can be cast face down from your hand")
        ch = chars.face_down_characteristics(face_down_kind)
        # -- granted casts (wave 29B) -- 707.2: a copy of a face-down spell is not face down
        from app.rules import cast_limits as _limits

        if not plan.manual(card) and _limits.granted_cascade(plan, card.id, ch, "hand", "storm"):
            raise ActionError("A face-down spell that is given storm isn't automated (its copies are face-up 2/2 creature spells): cast it face up")
    # 601.3d / 601.2g: mana abilities may remove a conditional timing source after this announcement was legal.
    # Only a server-created payment resume can authorize its original object; new casts and new incarnations cannot.
    timing_locked = plan.locked_cast_timing == plan.oid(card)
    problem = cast_problem(plan.state, plan.actor, card, ch, info=plan.info, free=a.free, sneak=sneaking or timing_locked, announced=True, alternative_key=a.alt_cost, optional_keys=tuple(a.optional_costs))
    if problem:
        raise ActionError(problem)
    grant = cast_grant(plan.state, plan.actor, card, ch, plan.info, free=a.free, slot=a.slot, via=a.via, alternative_key=a.alt_cost)
    sac_at_cleanup = not a.free and flash_sac(plan.state, plan.actor, card, ch, plan.info)  # (-- flash auras (wave 46B) -- judged before it is on the stack)
    if grant is not None and grant.how == "permission" and a.x_value and "{X}" in ch.mana_cost:
        # -- review 30c -- 202.3e, 601.2e: "with mana value 3 or less" reads the X announced (Lurrus ruling 2020-04-17: "{X}{W} … with X as 1 but not as 2")
        grant = cast_grant(plan.state, plan.actor, card, replace(ch, mana_value=ch.mana_value + a.x_value * ch.mana_cost.count("{X}")), plan.info,
                           free=a.free, slot=a.slot, via=a.via, alternative_key=a.alt_cost)
        if grant is None:
            raise ActionError(f"{ch.name} can't be cast this way with X = {a.x_value}: its mana value would be too high")
    if a.slot is not None and grant is None:
        raise ActionError(f"{ch.name or 'That card'} can't be cast as a {a.slot} spell now")
    if a.via is not None and (grant is None or a.via not in (grant.use, grant.choice_key)):  # -- cast permissions (wave 32D) -- 601.2: a permission that doesn't cover this cast
        raise ActionError(f"{ch.name or 'That card'} can't be cast using that permission now")
    if grant is not None and len(grant.among) > 1:
        permissions.ask_use(plan, a, card, ch, grant.among, "cast")  # (-- wave 30Q, 32D -- "choose one as you cast it" (Muldrotha); which limited permission: asked before anything is paid)
        return
    from app.rules import permission_spell_keywords, wave110a_grants

    ch = permission_spell_keywords.apply(ch, grant)
    ch = wave110a_grants.with_replicate(plan.state, plan.actor, card, ch, plan.info)  # -- grants (wave 110A) --
    free = grant is not None and grant.free  # "without paying its mana cost" (118.9): an alternative cost of {0}
    from app.rules import flashback_choices

    using_flashback = not free and a.alt_cost is None and not a.face_down and not plan.manual(card) and grant is not None and grant.how == "flashback"
    if using_flashback and flashback_choices.announce(plan, a, card, ch):
        return
    selected_flashback = flashback_choices.selected(flashback_choices.options(plan.state, card, ch, plan.info), a.flashback_choice) \
        if using_flashback and "aftermath" not in ch.keywords else None  # (wave 110A: an Aftermath half has no flashback cost to announce, 702.127a)
    flashback_without_x = selected_flashback is not None and not M.parse_cost(selected_flashback[0]).x and not (selected_flashback[1] and selected_flashback[1].x_chosen)
    base = M.parse_cost(ch.mana_cost)
    airbent = grant is not None and bool(grant.alt_mana)  # -- trigger other (wave 25B) -- airbend 701.65a: cast only by paying its alternative cost
    from app.rules import alt_costs as _alt_x  # (leaves over this module)

    alt_x = a.alt_cost is not None and not free and not plan.manual(card) and any(  # -- cast keywords (wave 43D) -- 107.3a: an alternative cost with {X}
        o.key == a.alt_cost and _alt_x.announces_x(o) for o in _alt_x.offers(plan.state, plan.actor, card, ch, plan.info))  # (harmonize, overload, surge …)
    if (base.x or alt_x) and a.x_value is None:
        if alt_x or (not free and a.alt_cost is None and not airbent and not flashback_without_x):
            raise ActionError(f"Choose a value for X to cast {ch.name}")
        a.x_value = 0  # 107.3b: X is 0 when a spell is cast without paying its mana cost (or for an alternative cost, wave 4I)
    elif base.x and a.x_value and (free or airbent or flashback_without_x):  # -- review (wave 25A) -- 107.3b: the only legal choice is 0
        raise ActionError(f"X is 0 when {ch.name} is cast without paying its mana cost or for an alternative cost without X (107.3b)")
    from app.rules import cast_limits as _x_limits

    if base.x and (limited := _x_limits.cast_problem(plan.state, plan.actor, card, ch, plan.info, announced=a.x_value or 0)):
        raise ActionError(limited)  # -- review 38 -- 601.2e: the X announced counts in its mana value ("spells with mana value 3 or less", Brisela)
    if base.x and a.x_value and not plan.manual(card):  # -- X caps (wave 51C) -- 601.2b: "X can't be greater than the number of players in the game." (Open the Way): an X above it isn't a legal announcement
        from app.rules import scripts as _caps
        from app.rules import values as _cap_values

        for d in _caps.definitions(ch).values():
            if d.get("static") == "x_cap" and a.x_value > (cap := _cap_values.evaluate(plan, {"controller": plan.actor}, d["n"])):
                raise ActionError(f"{ch.name}: X can't be greater than {cap}")
    kick_x = a.kicker and not a.face_down and (kc := kicker_cost(ch.abilities)) is not None and kc.x  # -- cast keywords (wave 43D) -- 107.3a: "Kicker {X}"
    if kick_x and (base.x or a.x_value is None):  # The additional kicker X is announced even when the mana cost is waived (118.9d).
        raise ActionError(f"Choose a value for X to pay the kicker cost of {ch.name}" if a.x_value is None and not base.x
                          else f"{ch.name}: pay its kicker X by hand")
    if kick_x and kc is not None and (a.x_value or 0) < kc.minimum_x:
        raise ActionError(f"{ch.name}: kicker X must be at least {kc.minimum_x}")
    alternative: M.ManaCost | None = M.parse_cost("{3}") if a.face_down else None
    additional: list[M.ManaCost] = [M.ManaCost(generic=grant.generic_extra)] if grant is not None and grant.generic_extra else []
    if a.buyback:
        extra = keyword_cost(ch, "buyback", BUYBACK)
        if extra is None and buyback_parts(ch) is None:  # (-- keywords (wave 30E) -- a buyback cost of other parts: merged below)
            raise ActionError(f"{ch.name} has no buyback cost")
        if extra is not None:
            from app.rules import buyback_costs

            additional.append(buyback_costs.reduced(plan.state, plan.info, extra))
    if a.evoke:
        evoke = keyword_cost(ch, "evoke", EVOKE)
        if evoke is None or card.zone != zone_key(plan.actor, "hand"):
            raise ActionError("Only a card with evoke can be cast for its evoke cost from your hand")
        alternative = M.parse_cost(evoke)
    if a.dash:
        if alternative is not None:
            raise ActionError("Only one alternative cost can be applied to a spell (118.9a)")
        dash = keyword_cost(ch, "dash", DASH)
        if dash is None:
            raise ActionError("That spell has no dash cost")
        if grant is not None and (grant.how in ('flashback', 'foretell', 'escape') or grant.alt_mana or grant.life_mv):
            raise ActionError("The selected casting permission requires a different alternative cost (118.9a)")
        alternative = M.parse_cost(dash)  # 702.109a: the actual casting permission, not dash, determines the allowed zone.
    if a.awaken:  # -- static_other sweep (wave 16B) -- 702.113a: an alternative cost; its text is the spell's "if cast for its awaken cost" line
        if a.evoke or a.dash or a.face_down or alternative is not None or keyword_cost(ch, "awaken", AWAKEN) is None \
                or card.zone != zone_key(plan.actor, "hand"):
            raise ActionError("Only a card with awaken can be cast for its awaken cost from your hand, with no other alternative cost")
        alternative = M.parse_cost(keyword_cost(ch, "awaken", AWAKEN) or "")
    if airbent:  # (an alternative cost: only one, 118.9a; the intent names none of its own)
        if free or alternative is not None or a.face_down or a.alt_cost is not None:
            raise ActionError("Only one alternative cost can be applied to a spell (118.9a)")
        alternative = M.parse_cost(grant.alt_mana)  # type: ignore[union-attr]
    if free and (alternative is not None or a.face_down):
        raise ActionError("Only one alternative cost can be applied to a spell (118.9a)")
    # -- cost changers (wave 4I) -- an alternative cost written on a card (Force of Will, Jodah: app/rules/alt_costs.py)
    from app.rules import alt_costs, cost_changes  # (leaves over this module)

    alt_offer: alt_costs.Offer | None = None
    # -- escape (wave 5I) -- a card cast from the graveyard only by escape: its (first) escape cost unless the intent
    # names one (702.138a); an escape cost named for a card that also has flashback is used instead of flashback
    if grant is not None and grant.how == "escape" and a.alt_cost is None and not free:
        escapes = _escape_offers(plan.state, plan.actor, card, ch, plan.info)
        if escapes:
            a.alt_cost = escapes[0].key
    foretold = grant is not None and grant.how == "foretell"  # -- hidden exile (wave 18A) -- 702.143a: only for its foretell cost
    if foretold:
        fore = _foretell_offers(plan.state, plan.actor, card, ch, plan.info)
        if a.alt_cost is None and fore:
            a.alt_cost = fore[0].key
        if not any(o.key == a.alt_cost for o in fore):
            raise ActionError(f"{ch.name} can be cast from foretell exile only for its foretell cost (702.143a)")
    escaping = a.alt_cost is not None and card.zone == zone_key(plan.actor, "graveyard") and any(
        o.key == a.alt_cost for o in _escape_offers(plan.state, plan.actor, card, ch, plan.info))
    if grant is not None and grant.how == "escape" and not escaping:
        raise ActionError(f"{ch.name} can be cast from your graveyard only for its escape cost (702.138a)")
    # -- commander sweep (wave 49B) -- 118.6, 202.1b: a card with no mana cost has an unpayable cost; one with an alternative cost of its own (Asmoranomardicadaistinaculdacar) is cast for that
    # cost alone (118.6a), and not at all while it doesn't apply (review 41: from any zone, the command zone above all: it is a commander)
    if not ch.mana_cost and a.alt_cost is None and not free and alternative is None and not a.face_down and not plan.manual(card) \
            and any(d.get("static") == "alt_cost" and not d.get("table") for d in permissions._definitions(ch).values()):
        ways = alt_costs.offers(plan.state, plan.actor, card, ch, plan.info)
        if len(ways) != 1:
            raise ActionError(f"{ch.name} has no mana cost (118.6): it can be cast only for its alternative cost, and only while that applies")
        a.alt_cost = ways[0].key
    if a.alt_cost is not None:  # (a foretold card: no other alternative cost, 118.9a)
        if free or alternative is not None or a.face_down or (grant is not None and grant.how == "flashback" and not escaping):
            raise ActionError("Only one alternative cost can be applied to a spell (118.9a)")
        alt_offer = alt_costs.chosen(plan, a.alt_cost, card, ch, x=a.x_value)
        alternative = alt_offer.alt.mana_cost
        if base.x and a.x_value and not alt_costs.announces_x(alt_offer):
            raise ActionError("X is 0 when the spell is cast for an alternative cost without X (107.3b)")
    # -- end cost changers (wave 4I) --
    # -- static wordings (wave 6E) -- 601.2b: which of its additional costs the caster pays, announced before targets
    from app.rules import either_costs

    either = None if plan.manual(card) or a.face_down else either_costs.announce(plan, a, card, ch)
    if either is either_costs.WAITING:
        return
    if either is not None and either.mana:  # (601.2f: a mana side is added to the total cost like kicker, 118.8)
        additional.append(M.parse_cost(either.mana))
    for target in a.targets:
        if target not in plan.state.cards and target not in plan.state.players:
            raise ActionError("A chosen target isn't on the table")
    flashing = None  # -- casting costs (wave 22F) -- 601.3c: the timing is legal only if the flash condition is met by what is chosen below
    if grant is not None and (flashing := flash_if(ch)) is not None and not plan.manual(card) \
            and timing_problem(plan.state, plan.actor, ch, grant) is not None and not (alt_offer is not None and alt_offer.flash):
        if "pay" in flashing:
            additional.append(M.parse_cost(flashing["pay"]))  # ("if you pay {2} more": an additional cost, only at the timing that needs it)
        elif "x_max" in flashing and (a.x_value or 0) > flashing["x_max"]:
            raise ActionError(f"{ch.name} can be cast now only if X is {flashing['x_max']} or less")
        elif "offering" in flashing and f"{card.id}:offering" not in a.optional_costs:  # -- offering (wave 51H) -- 702.48a: instant timing only by sacrificing one
            raise ActionError(f"{ch.name} can be cast now only by sacrificing a {flashing['offering']} (offering)")
    else:
        flashing = None
    definition = None if plan.manual(card) or a.face_down else scripts.spell_definition(ch)
    definition = per_opponent.for_cast(plan, card.id, definition)  # -- per-opponent targets (wave 23A) --
    if definition is not None and (a.x_value or 0) < definition.get("x_min", 0):
        raise ActionError(f"{ch.name}: X can't be {a.x_value or 0}")
    entwined = bool(a.kicker) and (kick := kicker_cost(ch.abilities)) is not None and kick.entwine  # (an entwined spell isn't kicked: review 18E)
    kicked = 0 if entwined else kick_count(ch, a.kicker)
    if entwined and not (definition or {}).get("modes"):
        raise ActionError(f"{ch.name} can be entwined only as a modal spell")  # -- casting extras (wave 18E) -- 702.42a
    splice_extra: list[AbilityCost] = []
    if a.splice:  # -- casting extras (wave 18E) -- 702.47: the spliced cards' text is part of the spell; their costs are additional costs
        from app.rules import splice

        if plan.manual(card) or a.face_down:
            raise ActionError("That card is played by hand: splice by hand with the table tools")
        spliced_ch, spliced_costs = splice.prepare(plan, a.splice, card, ch)
        original_splice71 = spliced_ch
        spliced_ch = text_global_word71.prospective(plan.state, card, spliced_ch, plan.info)
        if (definition := per_opponent.for_cast(plan, card.id, scripts.spell_definition(spliced_ch))) is None:  # (review 23A: its groups too)
            raise ActionError("That splice can't be carried out by the engine")
        for sc in spliced_costs:
            if sc.mana:
                additional.append(sc.mana_cost)
            if sc.cost.components:
                splice_extra.append(sc.cost)
    aura = None if plan.manual(card) or a.face_down else (merged.MUTATE_TARGET if mutating_cast else attachments.enchant_selector(ch))
    from app.rules import static_perm100d  # -- static permanents (wave 100D) -- 601.2c

    aura = static_perm100d.cast_aura(ch, aura)
    slots: list[list[TargetRef]] = []
    slot_specs: list[dict[str, Any] | None] = []
    picked: list[int] = []
    escalate_more: AbilityCost | None = None
    if definition is not None and definition.get("modes"):
        from app.rules.modal_abilities import printed_order

        if a.kicker and (kick := kicker_cost(ch.abilities)) is not None and kick.entwine:  # -- casting extras (wave 18E) --
            # 702.42a: entwined, the spell's controller chooses all its modes (each must be choosable, 700.2a)
            a.modes = list(range(len(definition["modes"])))
            definition = {**definition, "modal": {**definition["modal"], "min": len(a.modes), "max": len(a.modes), "repeat": False, "instead": None}}
        a.modes, a.targets = printed_order(definition, a.modes, a.targets)  # (wave 1A) 608.2c: carried out as printed
        modes = choose_modes(plan, a, definition, ch.name or "it")  # 601.2b: modes first …
        if modes is None:
            return
        picked = modes
        additional += [M.parse_cost(definition["modes"][i]["cost"]) for i in picked if definition["modes"][i].get("cost")]  # -- keywords (wave 30E) -- 702.172a, 702.183a
        if len(picked) > 1 and (esc := escalate_cost(ch)) is not None:  # -- static_other sweep (wave 16B) -- 702.120a: each mode beyond the first
            more = len(picked) - 1
            one = M.parse_cost(esc[0])
            additional.append(M.ManaCost(one.generic * more, one.colored * more, one.hybrid * more, one.phyrexian * more, 0, one.unsupported * more))
            if esc[1] is not None:
                escalate_more = AbilityCost(components=esc[1].components * more, life=esc[1].life * more)
        grouped = modal_groups(definition, picked)  # -- static_other sweep (wave 16B) --
        if grouped is not None:
            picked_targets: ChosenTargets | None = choose_targets(plan, a, {"targets": grouped}, ch.name or "it")
        else:
            slot_specs = [definition["modes"][i]["target"] for i in picked]
            found = choose_slot_targets(plan, a, slot_specs, ch.name or "it")  # … then each mode's target (601.2c)
            if found is None:
                return
            slots = found
            picked_targets = ChosenTargets(flat=[t for slot in slots for t in slot])
    else:
        picked_targets = choose_targets(plan, a, definition if aura is None else {"target": {"what": aura}}, ch.name or "it")
    if picked_targets is None:
        return  # waiting for the target choice (601.2c comes before paying costs)
    chosen = picked_targets.flat
    if flashing is not None and "targets" in flashing and not cost_changes.targets_fit(
            plan, card, plan.actor, flashing["targets"], tuple(t.id for t in chosen)):
        raise ActionError(f"{ch.name} can be cast now only if its targets meet its flash condition")
    announced = optional_announced(plan, a, card, ch)  # -- cost changers (wave 4I) -- (601.2b)
    if announced is None:
        return
    optional, gift_to, bargained = announced
    # -- costs (wave 3$) -- 601.2b: an additional cost ("sacrifice a creature", "discard a card", "pay 2 life") is
    # announced with the rest; 601.2h pays it all at once, so nothing moves until every part is chosen and payable
    add_cost = None if plan.manual(card) or a.face_down else costs.spell_additional_cost(ch.abilities)
    if either is not None:  # -- static wordings (wave 6E) -- the announced side's non-mana parts
        add_cost = either if either.components else None
    alt_at = len(add_cost.components) if add_cost is not None else 0
    if alt_offer is not None:  # -- cost changers (wave 4I) -- its other parts are paid with the rest (601.2h)
        add_cost = alt_costs.merged(add_cost, alt_offer.alt.cost)
    if escalate_more is not None:  # -- static_other sweep (wave 16B) -- escalate's non-mana parts, once for each mode beyond the first
        add_cost = alt_costs.merged(add_cost, escalate_more)
    if a.buyback and (bb_more := buyback_parts(ch)) is not None:  # -- keywords (wave 30E) -- 702.27a: "Buyback—Sacrifice a land." is paid with the rest (601.2h)
        add_cost = alt_costs.merged(add_cost, bb_more)
    if grant is not None and grant.how == "flashback" and not escaping and (fb_more := flashback_choices.extra(plan.state, card, ch, plan.info, a.flashback_choice)) is not None \
            and card.zone == zone_key(plan.actor, "graveyard"):  # -- static_other sweep (wave 16B) -- the flashback cost's other parts
        add_cost = alt_costs.merged(add_cost, fb_more)
    if grant is not None and grant.extra:  # -- cost alt (wave 16F) -- "cast this card from your graveyard by discarding a card"
        extra_cost = costs.parse_additional_cost(grant.extra)
        if extra_cost is None:  # (defined only when it parses; never cast without the cost)
            raise ActionError("That additional cost can't be paid automatically")
        add_cost = alt_costs.merged(add_cost, extra_cost)
    for sx in splice_extra:  # -- casting extras (wave 18E) -- splice costs that aren't mana (702.47a)
        add_cost = alt_costs.merged(add_cost, sx)
    if (kick_more := kicker_parts(ch, a.kicker)) is not None:  # (702.42a: "Entwine—Sacrifice two lands"; wave 43D: "Kicker—Sacrifice a land.")
        add_cost = alt_costs.merged(add_cost, kick_more)
    if (life_more := permissions.life_cost(grant, ch)) is not None:
        add_cost = alt_costs.merged(add_cost, life_more)
    from app.rules import cost_statics101

    if (commander_life101 := cost_statics101.commander_life(plan.state, card, ch)):
        add_cost = alt_costs.merged(add_cost, costs.AbilityCost(
            components=(costs.CostComponent(costs.PAY_LIFE, amount=commander_life101, text=f"Pay {commander_life101} life"),), life=commander_life101))
    if (target_life := cost_changes.targeting_life(plan.state, plan.actor, card, ch, plan.info, tuple(t.id for t in chosen))):
        add_cost = alt_costs.merged(add_cost, costs.AbilityCost(  # -- casting costs (wave 22F) -- Terror of the Peaks: life for its targets (601.2f)
            components=(costs.CostComponent(costs.PAY_LIFE, amount=target_life, text=f"Pay {target_life} life"),), life=target_life))
    if (each_life := sum(d.get("life_per_target", 0) for d in permissions._definitions(ch).values())) and chosen:  # -- wave 110E -- "costs 3 life more for each target"
        add_cost = alt_costs.merged(add_cost, costs.AbilityCost(
            components=(costs.CostComponent(costs.PAY_LIFE, amount=each_life * len(chosen), text=f"Pay {each_life * len(chosen)} life"),), life=each_life * len(chosen)))
    if (optional_more := optional_parts(optional, a.x_value or 0)) is not None:  # -- cost changers (wave 4I) -- Defiler of Vigor's 2 life, paid with the rest (601.2h, 119.4)
        add_cost = alt_costs.merged(add_cost, optional_more)
    add_objects: dict[int, list[str]] = {}
    if add_cost is not None:
        from app.rules import counter_cost_order70

        counter_first70 = bool(grant is not None and counter_cost_order70.selected(grant.extra)
                               and counter_cost_order70.index(add_cost) is not None)
        problem_cost70 = counter_cost_order70.preflight(add_cost) if counter_first70 else add_cost
        problem = additional_problem(plan, problem_cost70, card, plan.actor) or life_x_problem(plan, add_cost, a, plan.actor)  # (4K)
        if problem:
            raise ActionError(problem)
        plan.reserved_life = add_cost.life + ((a.x_value or 0) if add_cost.life_x else 0)  # (wave 29C: 119.4, with Phyrexian mana's life)
        found_objects = cost_payment.choose(plan, a, add_cost, card, ch.name or "it", counter_first=counter_first70)
        if found_objects is None:
            return  # waiting for the payer's choice; nothing has been paid
        add_objects = found_objects
    emerge_reduction = 0  # -- casting extras (wave 18E) -- 702.119a: reduced by the sacrificed permanent's mana value; 702.180a: harmonize, by
    # the tapped creature's power
    if a.dash:
        from app.rules import selected_keyword_costs65

        emerge_reduction += selected_keyword_costs65.dash_discount(plan.state, plan.actor, plan.info)
    if alt_offer is not None and alt_offer.tag == "blitz":
        from app.rules import dynamic_keyword_costs55

        emerge_reduction += dynamic_keyword_costs55.blitz_discount(plan.state, plan.actor, plan.info)
    if alt_offer is not None and alt_offer.tag in ("emerge", "harmonize"):
        n_alt = len(alt_offer.alt.cost.components)
        for i, ids in add_objects.items():
            if alt_at <= i < alt_at + n_alt:
                for c in ids:
                    now = plan.ch(plan.state.cards[c])
                    emerge_reduction += max(0, int(now.mana_value) if alt_offer.tag == "emerge" else now.pt[0] if now.pt else 0)
    # (-- casting extras (wave 18E) -- the additional costs are chosen before the total cost is worked out: emerge's reduction reads
    # the creature sacrificed for it, 702.119a)
    # 601.2f (after the targets, 601.2c): the total cost in the rules' order — kicker is an additional cost (118.8)
    # added before increases and reductions apply, so a reduction sees the kicked total; "spells that target …" cost
    # changers read the targets chosen (wave 4I)
    from app.rules import cast_limits, spell_mana_floor, spell_symbol_choices, waterbend103

    additional.append(waterbend103.mana(optional))
    prepared: list[Any] = []
    cost = spell_cost(plan.state, card, ch, a.x_value or 0, plan.info, player=plan.actor, alternative=(alternative if alternative is not None else M.parse_cost(ch.mana_cost) if grant is not None and grant.how == "resolving" else None),
                      free=free, kicker=a.kicker, additional=tuple(additional), face_down=a.face_down, targets=tuple(t.id for t in chosen),
                      reduce=emerge_reduction + (cost_payment.reduction(add_cost, add_objects) if add_cost is not None else 0),
                      flashback_choice=a.flashback_choice, mana_symbols=a.mana_symbols, capture=prepared, announced_kicker77=True)  # (wave 47C: "you may sacrifice any number of …")
    if alt_offer is not None and alt_offer.template_mana_has_x is not None:
        prepared[-1] = replace(prepared[-1], selected_cost_has_x=bool(alt_offer.template_mana_has_x or prepared[-1].selected_cost_has_x))
    if spell_mana_floor.minimum(plan.state, plan.info) or a.mana_symbols is not None:
        if spell_symbol_choices.announce(plan, a, card, ch, prepared[0]):
            return
        cost = prepared[0].evaluate(a.mana_symbols)
    from app.rules import x_mana_restrictions

    x_reduction = prepared[0].raw.generic - prepared[0].evaluate(a.mana_symbols).generic
    before_offering = cost.generic
    for i, part in enumerate(add_cost.components if add_cost is not None else ()):  # -- offering (wave 51H) -- 702.48a, c: what is sacrificed for it, colors included
        for sacrificed in add_objects.get(i, []) if part.offering else []:
            cost = offering.reduce(cost, M.parse_cost(plan.ch(plan.state.cards[sacrificed]).mana_cost))
    x_reduction += max(0, before_offering-cost.generic)
    x_maximum = min(a.x_value or 0, cost.generic)
    cost = cost_changes.reduce_only(cost, tuple(o.mana for o in optional if o.mana))  # ("reduces only the amount of green mana")
    if spell_mana_floor.minimum(plan.state, plan.info):
        cost = spell_mana_floor.apply(plan.state, plan.info, cost)
    from app.rules import waterbend102

    cost = waterbend102.due(cost,add_cost,add_objects)
    cost_colorless = 'C' in cost.colored
    spend_mode = cast_limits.spend_mode(plan.state, plan.actor, card, ch, plan.info)
    if spend_mode:
        cost = M.spend_as(cost, spend_mode)
    cost = M.spend_as(cost, grant.spend) if grant is not None and grant.spend else cost  # -- as long as (wave 9B) -- 118.14
    x_payment = x_mana_restrictions.metadata(ch.oracle_text, a.x_value or 0, x_reduction, cost, maximum=x_maximum,
        mode=(grant.spend if grant is not None and grant.spend else cast_limits.spend_mode(plan.state, plan.actor, card, ch, plan.info)),
        locked=plan.locked_x_payment)
    helper, helper_pays = None, 0  # -- casting extras (wave 18E) -- 702.132a assist: another player pays some generic mana (601.2g-h)
    if "assist" in ch.keywords and not plan.manual(card) and not a.face_down:
        from app.rules import assist

        found_helper = assist.announce(plan, a, card, ch, cost, cost_has_x=prepared[0].selected_cost_has_x)
        if found_helper is assist.WAITING:
            return
        helper, helper_pays = found_helper
        cost = cost.plus_generic(-helper_pays)
    was_locked = plan.locked_cost is not None
    cost = _locked(plan, cost)  # -- cost changers (wave 4I) -- 601.2f: locked in once the payment was asked for (the caster's share, after assist)
    not_mana = cost_payment.excluded(add_cost, card, add_objects) if add_cost is not None else ()
    origin = card.zone  # (wave 17B: where it is cast from, before it moves to the stack)
    from_oid = plan.oid(card)  # -- as long as (wave 37A) -- the object it is before it becomes the spell (400.7): "until this card is cast from exile"
    purpose = Purpose(spell=ch, zone=origin, player=plan.actor, kicked=bool(kicked), x_payment=x_payment,
                      **{'spell_object': _spell_reference(plan.state, card),
                         **(plan.locked_payment_context or {'alternative':alt_offer.tag if alt_offer else None,
                                                          'producer_requirement':alt_offer.producer_requirement if alt_offer else None, 'cost_colorless':cost_colorless,
                                                          'selected_cost_has_x':prepared[0].selected_cost_has_x})})
    announced_cost = cost if a.mana_symbols is not None else announce_phyrexian(plan, a, cost, ch.name or "it", exclude=not_mana, purpose=purpose, trusted=was_locked)  # (wave 50B: 601.2b)
    if announced_cost is None:
        return
    cost = announced_cost
    from app.rules import as_cast_values42

    cast_greatest_power = as_cast_values42.capture(plan, definition)
    origins70 = counter_cost_order70.capture(plan, add_cost, add_objects) if add_cost is not None and grant is not None and counter_cost_order70.selected(grant.extra) else None
    if payment_step(plan, a, cost, ch.name or "it", exclude=not_mana, purpose=purpose,
                    cast_greatest_power=cast_greatest_power, counter_cost_origins70=origins70):
        return
    commander_cast = from_command_zone(card, plan.actor)
    harmonized = alt_offer is not None and alt_offer.tag == "harmonize"  # -- casting extras (wave 18E) -- 702.180a: exiled as it leaves the stack
    flashback = from_graveyard(card, plan.actor, ch, plan.state, plan.info) and not escaping and not (grant is not None and grant.how == "resolving")  # (wave 5I: escape instead, 118.9a)
    jumped = grant is not None and grant.exile  # -- casting extras (wave 18E) -- 702.133a: cast with jump-start
    card_was_in_hand = card.zone == zone_key(plan.actor, "hand")
    cast_zone = card.zone.rsplit(":", 1)[-1]  # -- refused modal/conditional (wave 3R1) -- where it was cast from
    if cast_zone == "foretell":
        cast_zone = "exile"  # -- hidden exile (wave 18A) -- the foretell zone is the exile zone (702.143a): "cast from exile"
    from_where = {"graveyard": "the graveyard", "exile": "exile", "library": "the library", "hand": "the hand"}.get(
        card.zone.rsplit(":", 1)[-1], card.zone)
    if a.face is not None and a.face != card.face:
        plan.do({"type": "set_face", "card_id": card.id, "face": a.face})
    if a.face_down:
        plan.do({"type": "move", "card_ids": [card.id], "to": {"zone": "stack"}, "face_down": True, "face_down_kind": face_down_kind})
    else:
        plan.do({"type": "move", "card_ids": [card.id], "to": {"zone": "stack"}})
    if a.face and not a.face_down and plan.state.cards[card.id].face != a.face:
        # -- Rooms (wave 18G) -- 709.5d: the cast half (the move out of the hand reset the face); -- trigger other (wave 25B) -- 709.3b, 715.3b:
        # likewise the Adventure / the second half of a split card: on the stack it has only that half's characteristics (so "a creature spell"
        # isn't an Adventure half, "whenever you cast an Adventure spell" is); (review 25B) and a modal double-faced card's back face, 712.11
        plan.do({"type": "set_face", "card_id": card.id, "face": a.face})
    if cast_zone == "exile":  # -- static_other sweep (wave 17C) -- "Spells you cast from exile have convoke." (cast_limits.granted_helpers reads it)
        plan.do({"type": "set_stack_info", "card_id": card.id, "tags": ["Cast from exile"]})
    if grant is not None and grant.how == "prepared":  # -- prepared (wave 13C) -- 722.3c, 601.2i: it loses the designation as the copy is cast
        plan.rules.prepared = {o: c for o, c in plan.rules.prepared.items() if c != card.id}
    if commander_cast and not plan.state.settings.auto_commander_tax and card.commander_key:
        plan.do({"type": "commander_tax", "commander": card.commander_key, "delta": 2})
    data = _PostCast(a, add_cost, add_objects, alt_offer, aura, bargained, bestowed_cast, card, card_was_in_hand, cast_zone, ch, chosen, commander_cast, definition, entwined, escaping, flashback, foretold, free, from_oid, from_where, gift_to, grant, harmonized, jumped, kicked, mutating_cast, optional, picked, picked_targets, sac_at_cleanup, slot_specs, slots)
    if add_cost is not None and grant is not None and counter_cost_order70.selected(grant.extra):
        data.counter_cost_origins70 = origins70
    data.origin_player103 = origin.split(":", 1)[0] if ":" in origin else None
    data.cast_greatest_power = cast_greatest_power
    from app.rules import card_names

    data.spliced_names = sorted({name for cid in a.splice for name in card_names.names_of(plan.ch(plan.state.cards[cid]))})
    from app.rules import text_spell_refresh71

    data.splice_text71 = text_spell_refresh71.extras(ch.name, ch, original_splice71) if a.splice else SpliceText71(name=ch.name)
    data.splice_text71.global_change = global_text_prepared71
    payment_data = _CastPayment(data, cost, not_mana, origin, x_payment, _purpose_context(purpose))
    from app.rules import payment_continuations as pc

    after = pc.continuation(plan, "cast_payment", payment_data)
    if helper is not None and helper_pays:
        from app.rules import assist

        assist.pay(plan, helper, helper_pays, card, ch, then=after, spell_object=purpose.spell_object, cost_has_x=purpose.selected_cost_has_x)
        return
    _cast_payment(plan, payment_data, None)


@dataclass
class _PostCast:
    a: A.CastSpell
    add_cost: AbilityCost | None
    add_objects: dict[int, list[str]]
    alt_offer: alt_costs.Offer | None
    aura: str | None
    bargained: bool
    bestowed_cast: bool
    card: CardInstance
    card_was_in_hand: bool
    cast_zone: str
    ch: Characteristics
    chosen: list[TargetRef]
    commander_cast: bool
    definition: dict[str, Any] | None
    entwined: bool
    escaping: bool
    flashback: bool
    foretold: bool
    free: bool
    from_oid: str
    from_where: str
    gift_to: str | None
    grant: permissions.Grant | None
    harmonized: bool
    jumped: bool
    kicked: int
    mutating_cast: bool
    optional: list[cost_changes.Optional]
    picked: list[int]
    picked_targets: ChosenTargets
    sac_at_cleanup: bool
    slot_specs: list[dict[str, Any] | None]
    slots: list[list[TargetRef]]
    record: PaymentRecord | None = None
    opponent_gain_receipts: list[OpponentGainCostReceipt] | None = None
    spliced_names: list[str] | None = None  # Announcement snapshot; None only in legacy saved continuations.
    splice_text71: SpliceText71 | None = None
    cast_greatest_power: int | None = None
    counter_cost_origins70: list[ObjectRef] | None = None
    origin_player103: str | None = None  # Physical origin owner, captured before moving to the stack.


@dataclass
class _CastPayment:
    data: _PostCast
    cost: M.ManaCost
    not_mana: tuple[str, ...]
    origin: str
    x_payment: dict[str, Any] | None = None
    payment_context: dict[str, Any] | None = None


def _cast_payment(plan: Plan, data: _CastPayment, payment: M.Payment | None) -> None:
    from app.rules import payment_continuations as pc

    card = plan.state.cards.get(data.data.card.id) or data.data.card
    after = pc.continuation(plan, "post_cast", data.data)
    pay_spell_then(plan, data.data.a, card, data.data.ch, data.cost,
                   f"paid {data.cost.text()} for {data.data.ch.name or 'a face-down spell'}",
                   not_mana=data.not_mana, origin=data.origin, then=after, x_payment=data.x_payment, payment_context=data.payment_context)


def _post_cast(plan: Plan, data: _PostCast, payment: M.Payment | None) -> None:
    from app.rules import waterbend102
    from app.rules.engine import advance

    record = data.record
    assert record is not None
    record.cast_greatest_power = data.cast_greatest_power
    a = data.a
    add_cost = data.add_cost
    add_objects = data.add_objects
    alt_offer = data.alt_offer
    aura = data.aura
    bargained = data.bargained
    bestowed_cast = data.bestowed_cast
    card_was_in_hand = data.card_was_in_hand
    cast_zone = data.cast_zone
    ch = data.ch
    chosen = data.chosen
    commander_cast = data.commander_cast
    definition = data.definition
    from app.rules import as_cast_values42

    effect_x = as_cast_values42.stack_x(definition, data.cast_greatest_power, a.x_value)
    entwined = data.entwined
    escaping = data.escaping
    flashback = data.flashback
    foretold = data.foretold
    free = data.free
    from_oid = data.from_oid
    from_where = data.from_where
    gift_to = data.gift_to
    grant = data.grant
    harmonized = data.harmonized
    jumped = data.jumped
    kicked = data.kicked
    mutating_cast = data.mutating_cast
    optional = data.optional
    picked = data.picked
    picked_targets = data.picked_targets
    sac_at_cleanup = data.sac_at_cleanup
    slot_specs = data.slot_specs
    slots = data.slots
    card = plan.state.cards.get(data.card.id) or data.card
    if add_cost is not None and any(c.kind == costs.OPPONENT_GAIN_LIFE for c in add_cost.components):
        from app.rules import opponent_gain_costs44
        from app.rules import payment_continuations as pc

        if data.opponent_gain_receipts is None:
            gains = opponent_gain_costs44.selected(plan, add_cost, add_objects)
            after = pc.continuation(plan, 'post_cast', data)
            opponent_gain_costs44.start(plan, opponent_gain_costs44.GainLifeCosts(gains, after, payment))
            return  # Native completion or saved replacement continuation owns the rest.
        expected = [(pid, c.amount) for i, c in enumerate(add_cost.components) if c.kind == costs.OPPONENT_GAIN_LIFE for pid in add_objects[i]]
        if [(r.recipient, r.nominal_amount) for r in data.opponent_gain_receipts] != expected:
            raise ActionError('The opponent-gain cost has not been paid')
        record.opponent_gain_costs = list(data.opponent_gain_receipts)
    if add_cost is not None:
        if add_cost.life:
            from app.rules import replace as _replace_life  # (wave 28B: 119.4)
            _replace_life.lose_life(plan, [(plan.actor, add_cost.life)])  # 119.4: paying life is losing it
            record.life += add_cost.life
        if add_cost.life_x and a.x_value:  # -- X sized by a count (wave 4K) -- "pay X life" (119.4)
            from app.rules import replace as _replace_life  # (wave 28B: 119.4)
            _replace_life.lose_life(plan, [(plan.actor, a.x_value)])
            record.life += a.x_value
        from app.rules import counter_cost_order70

        if grant is not None and counter_cost_order70.selected(grant.extra):
            counter_cost_order70.guard(plan, add_cost, card, add_objects, data.counter_cost_origins70)
        waterbend102.record(plan,a,add_cost,add_objects,record)
        cost_payment.pay(plan, add_cost, card, add_objects, record)  # sacrifice, discard, exile, return, tap …
        plan.reserved_life = 0  # (wave 29C: paid now; later payments of this intent are their own)
    if a.splice:  # -- casting extras (wave 18E) -- 702.47a: the spliced cards are revealed (they stay in the hand)
        plan.do({"type": "reveal", "card_ids": list(a.splice)}, actor=plan.actor)
        plan.do({"type": "hide", "card_ids": list(a.splice)}, actor=plan.actor)  # (701.20a: shown, then hidden again in the hand: review 18E)
    record.alternative = "face_down" if a.face_down else "evoke" if a.evoke else "dash" if a.dash else "awaken" if a.awaken else \
        "harmonize" if harmonized else "flashback" if flashback else "free" if free \
        else alt_offer.tag if escaping and alt_offer is not None and alt_offer.tag in ("disturb", "graveyard", "mayhem") else "escape" if escaping else \
        (alt_offer.tag or "alternative") if alt_offer is not None else None  # ("escape": 702.138b, wave 5I; blitz: 15E)
    if foretold:
        plan.rules.foretold.pop(card.id, None)
    if alt_offer is not None:  # -- cost changers (wave 4I) --
        if alt_offer.once_key:
            plan.rules.once_per_turn[alt_offer.once_key] = plan.state.turn.number  # ("once each turn")
        plan.note(f"{plan.name(plan.actor)} cast {ch.name} for an alternative cost ({alt_offer.label})", [card.id])
    record.additional = (["buyback"] if a.buyback else []) + (["entwine"] if entwined else ["kicker"] if a.kicker else []) \
        + [f"optional:{o.source}" for o in optional]  # (wave 4I: Defiler of Vigor's life)
    record.prototyped = a.prototype  # -- casting extras (wave 18E) -- 718.3b
    record.kicked_mask = kick_mask(ch, a.kicker)  # (-- keywords (wave 50H) -- "kicked with its {R} kicker", 702.33f)
    record.kicked = kicked or int(a.awaken) or int(gift_to is not None or bargained)  # 702.33d (-- static_other sweep (wave 16B) -- awaken: the line is read as
    record.pick110e = a.pick110e  # (wave 110E)
    record.gift_to = gift_to  # "If this spell was kicked"; wave 23D: a promised gift, 702.174k, likewise)
    _note_cast(plan, record, cast_zone, zone_player=data.origin_player103)  # -- refused modal/conditional (wave 3R1) --
    record.spliced_names = data.spliced_names
    record.splice_text71 = data.splice_text71
    record.flash_sac = sac_at_cleanup
    record_payment(plan, card.id, record)
    tags = ["Cast from the command zone"] if commander_cast else ["Harmonize"] if harmonized else ["Jump-start"] if jumped else \
        ["Aftermath" if "aftermath" in ch.keywords else "Flashback"] if flashback else ["Dashed"] if a.dash else \
        ["Disturbed" if alt_offer is not None and alt_offer.tag == "disturb" else "Alternative cost" if alt_offer is not None and alt_offer.tag in ("graveyard", "mayhem") else "Escaped"] if escaping else ["Foretold"] if foretold else []  # (wave 5I; 18E)
    if grant is not None and grant.how == "permission":
        from app.rules import permission_spell_keywords

        permission_spell_keywords.retain(plan, card, grant)
        tags.append(f"Cast from {from_where}" + (" without paying its mana cost" if free else ""))
    if a.dash:
        plan.rules.dashed.append(card.id)
    if bestowed_cast:  # -- keywords (wave 15E) -- 702.103b: the spell on the stack is a bestowed Aura spell
        plan.rules.bestowed.append(plan.oid(card))
        tags.append("Bestowed")
    if mutating_cast:  # -- merged permanents (wave 18D) -- 702.140a: it becomes a mutating creature spell
        merged.note_cast(plan, card)
        tags.append("Mutating")
    if a.kicker and (kick := kicker_cost(ch.abilities)) is not None and kick.entwine:  # -- casting extras (wave 18E) --
        tags.append("Entwined")
    elif a.kicker:
        tags.append("Kicked" if kicked == 1 else f"Kicked ×{kicked}")
    if a.awaken:
        tags.append("Awakened")
    if bargained:
        tags.append("Bargained")
    if a.splice:
        tags.append("Spliced")
    if a.prototype:
        tags.append("Prototyped")
    if a.buyback:
        tags.append("Buyback")
        plan.rules.buyback.append(plan.oid(card))
    if a.evoke or (alt_offer is not None and alt_offer.tag == "evoke"):  # (-- keywords (wave 30E) -- 702.74a: a pitched evoke cost is the offer's)
        tags.append("Evoked")
        plan.rules.evoked.append(card.id)
    if "rebound" in ch.keywords and card_was_in_hand:
        plan.rules.rebound_cast.append(plan.oid(card))
    if flashback or harmonized or jumped:
        plan.rules.flashback.append(plan.oid(card))  # 702.34a: exiled instead of going anywhere else (702.133a, 702.180a)
    if alt_offer is not None and alt_offer.exile_gy:  # -- wave 110I -- Glimpse the Cosmos (614.1a)
        plan.rules.exile_if_graveyard.append(plan.oid(card))
    if grant is not None and grant.graveyard_destination == "library_bottom":
        plan.rules.bottom_if_graveyard.append(plan.oid(card))
    if grant is not None and grant.exile_gy and (grant.exile_gy == "all" or ch.is_instant_or_sorcery):  # -- cast from graveyard (wave 19C) -- 614.1a
        plan.rules.exile_if_graveyard.append(plan.oid(card))
    if grant is not None and grant.enters and (grant.enters.get("only") is None or grant.enters["only"] in ch.types):  # -- cast permissions (wave 30Q; wave 51D: "If you cast a creature spell this way") -- "If you cast a spell this way, that artifact enters tapped / with a finality counter on it"
        plan.rules.cast_enters[plan.oid(card)] = grant.enters  # (applied as it enters: engine.resolve_top; a countered spell never does, and a new object is a new id, 400.7)
    if a.x_value is not None or tags:
        info: dict[str, Any] = {"type": "set_stack_info", "card_id": card.id}
        if a.x_value is not None:
            info["x"] = a.x_value
        if tags:
            info["tags"] = tags
        plan.do(info)
    if grant is not None and grant.how == "permission":
        permissions.consume(plan, grant, card_id=card.id, verb="cast")  # Actual stack X and face are now committed.
    if a.targets:
        plan.target_arrows(card.id, a.targets)
    r = plan.rules
    # for "whenever you cast"; amount: the Nth spell its caster cast this turn ("your second spell each turn")
    emit(plan.state, "spell_cast", object_id=plan.oid(card), card=card.id, player=plan.actor,
         amount=r.spells_this_turn(plan.actor, plan.state.turn.number) + 1)
    delayed.spell_cast(plan, from_oid)  # -- as long as (wave 37A) -- 611.2a: "until this card is cast from exile" is over
    from app.rules import (
        wave110m_cards as _w110m,  # -- (wave 110M) -- "until a player casts a creature spell" is over
    )

    _w110m.spell_cast(plan, card)
    # -- granted casts (wave 29B) -- 708.2, 613.1f, 601.2a: a face-down spell has no abilities of its own, but an effect that gives its spell cascade or
    # ripple ("the next creature spell you cast this turn has cascade") gives it to this one as it is cast: they trigger (702.85a, 702.60a). Its mana
    # value is 0 and it has no name (708.2a), so cascade finds nothing and ripple nothing with its name (201.2a). Storm / conspire copy the spell:
    # not read for a face-down one (a grant of them to a creature spell is refused when it is cast, above)
    more_cascade = 0 if plan.manual(card) else _granted_cascade(plan, card, ch, record.cast_from)
    if more_cascade or ("cascade" in ch.keywords and not a.face_down and not plan.manual(card)):
        _cascade_triggers(plan, card, ch, more_cascade)
    if not plan.manual(card):
        if not a.face_down:
            _storm_triggers(plan, card, ch, record.cast_from)
        _ripple_triggers(plan, card, ch, record.cast_from)
        if not a.face_down:
            _conspire_trigger(plan, card, ch, record)
            _demonstrate_trigger(plan, card, ch, record.cast_from)  # (wave 43D)
    if "replicate" in ch.keywords and not a.face_down and not plan.manual(card):  # (wave 15E)
        _replicate_trigger(plan, card, ch, a.kicker)
    if definition is not None and picked and not slot_specs and any(definition["modes"][i].get("groups") for i in picked):
        r.stack[card.id] = StackEntry(kind="spell", controller=plan.actor, source_card=card.id, source_object=plan.oid(card),
                                      name=ch.name, effects=modal_effects(definition, picked, True), x=effect_x, modes=picked,
                                      **picked_targets.entry(None), kicked=kicked or int(a.awaken) or int(gift_to is not None or bargained), kicked_mask=record.kicked_mask)  # (-- static_other sweep (wave 16B) --)
    elif definition is not None and picked:  # a modal spell: each chosen mode's effects, with its own target slot
        effects_in_order = modal_effects(definition, picked, False)
        r.stack[card.id] = StackEntry(kind="spell", controller=plan.actor, source_card=card.id, source_object=plan.oid(card),
                                      name=ch.name, effects=effects_in_order, targets=chosen, target_spec=None,
                                      x=effect_x, modes=picked, slots=slots, slot_specs=slot_specs, kicked=kicked or int(a.awaken) or int(gift_to is not None or bargained), kicked_mask=record.kicked_mask)
    elif definition is not None:
        r.stack[card.id] = StackEntry(kind="spell", controller=plan.actor, source_card=card.id, source_object=plan.oid(card),
                                      name=ch.name, effects=list(definition["effects"]), x=effect_x,
                                      **picked_targets.entry(definition), kicked=kicked or int(a.awaken) or int(gift_to is not None or bargained), kicked_mask=record.kicked_mask)
    r.aura_targets = {k: v for k, v in r.aura_targets.items() if k != card.id and plan.state.cards.get(k) is not None
                      and plan.state.cards[k].zone == STACK}  # (review (wave 18D): never a target this card had as an earlier spell)
    if aura is not None and chosen:
        r.aura_targets[card.id] = chosen[0]  # 303.4a: the Aura spell's (or mutating spell's, 702.140a) target
    if chosen:
        from app.rules.triggers import targeted

        targeted(plan, card.id, plan.actor, chosen)
    turn = plan.state.turn.number
    r.spells_cast[plan.actor] = TurnCount(turn=turn, count=r.spells_this_turn(plan.actor, turn) + 1)
    history.note_cast(plan, card)  # -- this-turn history (wave 4D) --
    if grant is not None and grant.how == "resolving":
        r.free_casts = [c for c in r.free_casts if c != card.id]
        permissions.free_cast_done(plan, card.id, cast=True)
        return  # parent resolution continues before anyone receives priority
    r.passed = []
    r.priority = plan.actor
    if r.prefs_for(plan.actor).hold_priority:
        plan.hold = plan.actor
        return  # HOLD PRIORITY: you keep it, whatever your RESPONSE setting says
    r.auto_pass = plan.actor  # Arena-style: you pass after casting unless you hold priority (engine.advance, once the
    advance(plan)  # triggers that cast caused are on the stack: 117.3c, 603.3)


# -- mana abilities ---------------------------------------------------------------------
def _find_ability(ch: Characteristics, index: int) -> AbilityText:
    ability = next((ab for ab in ch.abilities if ab.index == index), None)
    if ability is None:
        raise ActionError(f"{ch.name or 'That card'} has no such ability")
    return ability


CYCLING = re.compile(r"^(?P<kind>(?:basic )?(?:[a-z]+)?)cycling (?P<cost>(\{[^}]+\})+)$", re.IGNORECASE)


def hand_abilities(ch: Characteristics, index: int) -> list[tuple[str, str]]:
    """The cycling keywords on ability line ``index``: (kind, mana cost) each. kind "" = plain cycling,
    "basic land" / "Swamp" / "Wizard" … = typecycling (search for that card). -- keywords (wave 50H) -- one line may have several
    ("Mountaincycling {2}, forestcycling {2}", 702.29e: each is an ability of its own)."""
    from app.rules import cycling_costs

    ability = next((ab for ab in ch.abilities if ab.index == index and ab.kind == "keywords"), None)
    return cycling_costs.parts(ability.text) if ability is not None else []


def hand_ability(ch: Characteristics, index: int) -> tuple[str, str] | None:
    """The (first) cycling keyword on ability line ``index``: (kind, mana cost)."""
    return next(iter(hand_abilities(ch, index)), None)


# -- refused zones/sized (wave 3R4) -- 702.53a transmute: "[Cost], Discard this card: Search your library for a card
# with the same mana value as the discarded card, reveal that card, and put it into your hand. Then shuffle your
# library. Activate only as a sorcery." (only from the hand; a mana cost only)
TRANSMUTE = re.compile(r"^transmute (?P<cost>(?:\{[^}]+\})+)$", re.IGNORECASE)


def transmute_cost(ch: Characteristics, index: int) -> str | None:
    ab = next((x for x in ch.abilities if x.index == index and x.kind == "keywords"), None)
    m = TRANSMUTE.fullmatch(ab.text.strip().rstrip(".")) if ab is not None else None
    return m["cost"] if m else None


def transmute(plan: Plan, card: CardInstance, ch: Characteristics, a: A.ActivateAbility, cost_text: str) -> None:
    turn = plan.state.turn
    if turn.active_player != plan.actor or turn.phase not in ("main1", "main2") or plan.state.zones.get("stack"):
        raise ActionError("Transmute only as a sorcery: in your main phase while the stack is empty")  # 702.53a, 307.5
    mana = M.parse_cost(permissions.ability_mana(plan.state, plan.actor, card, ch, cost_text, plan.info))
    mana = _locked(plan, mana)  # -- review (wave 4R) -- 602.2b → 601.2f: locked in, as for other activations
    if payment_step(plan, a, mana, f"transmuting {ch.name}", purpose=Purpose(ability_of=ch)):
        return
    mv = int(ch.mana_value)  # the discarded card's (608.2h: as it last existed in the hand; a mana value doesn't change there)
    effects = [{"do": "search", "who": "you", "sel": 'sel:{"card":true,"zone_owner":"you","zones":["library"]}',
                "label": f"card with mana value {mv}", "max": 1, "to": "hand", "reveal": True, "upto": False, "mv": ["==", mv]}]
    ability_id = _new_ability(plan, card, f"Search your library for a card with mana value {mv}, reveal it, put it into "
                                          f"your hand, then shuffle.")
    from app.rules import special_payment_tails

    special_payment_tails.pay(plan, "transmute", card, ch, mana, f"paid {mana.text()} to transmute {ch.name}",
                              sources=a.sources, purpose=Purpose(ability_of=ch), ability_id=ability_id, effects=effects)
# -- end refused zones/sized (wave 3R4) --


def cycle(plan: Plan, card: CardInstance, ch: Characteristics, a: A.ActivateAbility) -> None:
    """Cycling (702.29): pay the cost and discard this card from your hand, then the ability on
    the stack draws a card; typecycling searches your library for a card of that type instead."""
    if (transmuting := transmute_cost(ch, a.ability)) is not None:  # -- refused zones/sized (wave 3R4) --
        transmute(plan, card, ch, a, transmuting)
        return
    pieces = hand_abilities(ch, a.ability)
    if not pieces:
        raise ActionError("That card has no ability to use from your hand")
    from app.rules import cast_limits

    if prohibited := cast_limits.cycling_problem(plan.state, plan.info):
        raise ActionError(prohibited)
    kind, mana_text = pieces[0]
    # The native locked payment context captures which menu was announced before mana abilities.
    free_alt = bool((plan.locked_payment_context or {}).get('cycling_menu72')) if plan.locked_cost is not None else _first_alt(plan, "cycling")
    original_mana_text = mana_text
    if len(pieces) > 1 and free_alt:
        # One native announced choice binds both which cycling ability and its alternative cost.
        sides = [side for _, cost in pieces for side in (cost, "{0}")]
        labels = [f"{k}cycling {side}".capitalize() for k, cost in pieces for side in (cost, "{0}")]
        selected = _equip_side(plan, card, ch, a, sides, cycling=True, labels=labels)
        if selected is None:
            return
        index = int(next(c.cards[0] for c in a.cost_choices if c.component == costs.EITHER_SLOT and c.cards)[7:])
        kind, original_mana_text = pieces[index // 2]
        mana_text = selected
    else:
        if len(pieces) > 1:
            if _equip_side(plan, card, ch, a, [c for _, c in pieces], cycling=True, labels=[f"{k}cycling {c}".capitalize() for k, c in pieces]) is None:
                return
            kind, mana_text = pieces[int(next(c.cards[0] for c in a.cost_choices if c.component == costs.EITHER_SLOT and c.cards)[7:])]
        original_mana_text = mana_text
        if free_alt and mana_text != "{0}":
            side = _equip_side(plan, card, ch, a, [mana_text, "{0}"], cycling=True)
            if side is None:
                return
            mana_text = side
    from app.rules import cycling_costs

    if not cycling_costs.mana_only(mana_text):
        ability = AbilityText(index=a.ability, kind="activated", cost=f"{mana_text}, Discard this card",
                              text=f"Cycling — {mana_text}, Discard this card: Draw a card.")
        activate_to_stack(plan, card, ch, ability, a,
                          definition={"kind": "activated", "effects": cycling_costs.effects(kind), "cycling": True})
        return
    # 702.29a: cycling is an activated ability — "Abilities you activate that aren't mana abilities cost {1} less"
    # applies to it (602.2b -> 601.2f; app/rules/permissions.py ability_mana)
    mana = M.parse_cost(permissions.ability_mana(plan.state, plan.actor, card, ch, mana_text, plan.info, ability_text="cycling"))
    if mana.x and a.x_value is None:  # -- X from the triggering object (wave 34C) -- 107.3a: "Cycling {X}{1}{U}": X is announced as it is activated
        raise ActionError("Choose a value for X")
    cycling_x = a.x_value or 0 if mana.x else None
    mana = _locked(plan, mana).with_x(cycling_x or 0)  # -- review (wave 4R) -- 602.2b → 601.2f: locked in, as for other activations
    if payment_step(plan, a, mana, f"cycling {ch.name}", purpose=Purpose(ability_of=ch, selected_cost_has_x=cycling_x is not None, cycling_menu72=free_alt)):
        return
    if kind:
        effects = cycling_costs.effects(kind)
        text = f"Search your library for a {kind} card, reveal it, put it into your hand, then shuffle."
    else:
        effects = [{"do": "draw", "who": "you", "n": 1}]
        text = "Draw a card."
    ability_id = _new_ability(plan, card, text)
    from app.rules import special_payment_tails

    special_payment_tails.pay(plan, "cycling", card, ch, mana, f"paid {mana.text()} to cycle {ch.name}", sources=a.sources,
                              purpose=Purpose(ability_of=ch, selected_cost_has_x=cycling_x is not None, cycling_menu72=free_alt), ability_id=ability_id,
                              effects=effects, number=cycling_x or 0, original_cost=original_mana_text)


def _create_ability(plan: Plan, card: CardInstance, text: str, keep: bool = False) -> Any:
    """-- hidden-zone abilities (wave 28C) -- 602.2a / 701.20a: an ability activated from a hidden zone (the hand) reveals its card, so
    the ability on the stack names it for everyone (cycling, channel, ninjutsu, "put this card from your hand …"); the card is hidden
    again at once if it stays there (``keep``: it stays revealed, ninjutsu 702.49b), and the rest of the hand is never shown."""
    shown = card.zone == zone_key(plan.actor, "hand") and not card.revealed_to
    if shown:
        plan.do({"type": "reveal", "card_ids": [card.id]}, actor=plan.actor)
    created = plan.do({"type": "create_ability", "text": text, "source_id": card.id if card.id in plan.state.cards else None, "kind": "activated"})
    if shown and not keep:  # (review 28C: ninjutsu's card was revealed, hidden and revealed again)
        plan.do({"type": "hide", "card_ids": [card.id]}, actor=plan.actor)
    return created


def _new_ability(plan: Plan, card: CardInstance, text: str) -> str | None:
    created = _create_ability(plan, card, text[:500])
    new_ids = getattr(created, "r", None)
    return new_ids.ids[0] if new_ids is not None else None


def _stacked(plan: Plan, card: CardInstance, oid: str, ch: Characteristics, ability_id: str | None,
             effects: list[dict[str, Any]], *, cost_has_x: bool | None = None, cost_has_tap: bool | None = None, x: int | None = None) -> None:
    """An activated ability is on the stack: record what it does, then pass priority Arena-style."""
    from app.rules.engine import advance  # the engine imports this module

    r = plan.rules
    if ability_id:
        r.stack[ability_id] = StackEntry(kind="activated", controller=plan.actor, source_card=card.id, source_object=oid,
                                         name=ch.name, effects=effects, targets=[], target_spec=None, x=x)
        from app.rules.triggers import activated  # -- activation (wave 11F) --

        activated(plan, card, oid, ability_id=ability_id, cost_has_x=cost_has_x, cost_has_tap=cost_has_tap)
    r.passed = []
    r.priority = plan.actor
    if r.prefs_for(plan.actor).hold_priority:
        plan.hold = plan.actor
        return
    r.auto_pass = plan.actor  # (as after a cast: engine.advance passes for you once the triggers are on the stack)
    advance(plan)


CREW = re.compile(r"^crew (?P<n>\d+)$", re.IGNORECASE)


SUSPEND = re.compile(r"^suspend (?P<n>\d+|x)\s*[—-]\s*(?P<cost>(?:\{[^}]+\})+)(?:\. x can't be 0)?$", re.IGNORECASE)  # (-- keywords (wave 50H) -- "Suspend X—{X}{3}{U}. X can't be 0.")


def suspend_info(ch: Characteristics, index: int) -> tuple[int | None, str] | None:
    """702.62 "Suspend N—{cost}" on ability line ``index``: (N, cost); N is None for "Suspend X—{X}{3}{U}. X can't be 0." (X is announced, 107.3d)."""
    for ab in ch.abilities:
        if ab.index == index and ab.kind == "keywords" and "suspend" in ab.keywords:
            m = SUSPEND.fullmatch(ab.text.strip().rstrip("."))
            if m:
                return (None if m["n"].lower() == "x" else int(m["n"])), m["cost"]
    return None


def suspend(plan: Plan, card: CardInstance, ch: Characteristics, a: A.ActivateAbility, n: int | None, cost_text: str) -> None:
    """702.62a: a special action — whenever you could begin to cast it, pay the suspend cost and
    exile it with N time counters. It doesn't use the stack."""
    problem = cast_problem(plan.state, plan.actor, card, ch, info=plan.info)
    if problem:
        raise ActionError(problem)
    cost = M.parse_cost(cost_text)
    purpose = Purpose(selected_cost_has_x=bool(cost.x))
    if n is None:  # -- keywords (wave 50H) -- 107.3d: X is chosen by the player taking the special action, immediately before they pay the cost; it can't be 0 (the printed line)
        if not a.x_value or a.x_value < 1:
            raise ActionError("Choose a value for X (it can't be 0)")
        n, cost = a.x_value, cost.with_x(a.x_value)
    if payment_step(plan, a, cost, f"suspending {ch.name}", purpose=purpose):  # (review 18B: a special action, 116.2f: not a cast — restricted mana for spells or abilities doesn't pay it)
        return
    from app.rules import special_payment_tails

    special_payment_tails.pay(plan, "suspend", card, ch, cost, f"paid {cost.text()} to suspend {ch.name}",
                              sources=a.sources, purpose=purpose, number=n, original_cost=cost_text)


PLOT = re.compile(r"^plot (?P<cost>(?:\{[^}]+\})+)$", re.IGNORECASE)


def plot(plan: Plan, card: CardInstance, ch: Characteristics, a: A.ActivateAbility, cost_text: str) -> None:
    """-- keywords (wave 15E) -- 702.170a/b plot: a special action, any time you have priority during your main phase while the
    stack is empty: exile this card from your hand and pay the plot cost. It becomes a plotted card (702.170d): its owner may cast
    it from exile without paying its mana cost during their main phase while the stack is empty, on a later turn."""
    state = plan.state
    if state.turn.active_player != plan.actor or state.turn.phase not in MAIN_PHASES or state.zones.get(STACK):
        raise ActionError("You can plot a card only in your main phase while the stack is empty")
    cost = M.parse_cost(permissions.ability_mana(plan.state, plan.actor, card, ch, cost_text, plan.info, 0, "plot"))  # (wave 46A: "Plotting cards from your hand costs {2} less", 118.7a)
    if payment_step(plan, a, cost, f"plotting {ch.name}", purpose=Purpose()):  # (review 18B: a special action, 116.2k)
        return
    from app.rules import special_payment_tails

    special_payment_tails.pay(plan, "plot", card, ch, cost, f"paid {cost.text()} to plot {ch.name}",
                              sources=a.sources, purpose=Purpose())


def become_plotted(plan: Plan, card_id: str) -> None:
    """-- cast riders (wave 38C) -- 702.170c-d: a card in exile becomes plotted (the plot special action, or "it becomes plotted": Lilah): its owner may
    cast it without paying its mana cost during their main phase while the stack is empty, on any turn after this one (a permission that follows the
    object, 400.7h)."""
    card = plan.state.cards.get(card_id)
    if card is None or not card.zone.endswith(":exile") or card.is_token or card.copy_of is not None:
        return  # (a copy of a spell exiled ceases to exist, 704.5e)
    name = plan.ch(card).name or card.name
    plan.rules.permissions.append(Permission(
        id=secrets.token_hex(4), player=card.owner, cast=True, zone="any", object_id=plan.oid(card), card=card.id, free=True,
        until="permanent", turn=plan.state.turn.number, after_turn=plan.state.turn.number, sorcery=True,
        label=f"{name}: cast it without paying its mana cost (plotted)"))
    plan.note(f"{name} is plotted", [card.id])
    emit(plan.state, "plotted", object_id=plan.oid(card), card=card.id, player=card.owner)  # -- (wave 110B) -- "When this card becomes plotted"


FORETELL = re.compile(r"^foretell (?P<cost>(?:\{[^}]+\})+)$", re.IGNORECASE)


def foretell(plan: Plan, card: CardInstance, ch: Characteristics, a: A.ActivateAbility) -> None:
    """-- hidden exile (wave 18A) -- 702.143a/b foretell: a special action (116.2h), any time you have priority during your turn:
    pay {2} and exile this card from your hand face down. Its owner alone may look at it (the foretell zone); it may be cast
    after this turn has ended for its foretell cost (alt_costs.offers, casting.cast_grant)."""
    from app.rules import static_perm100d  # -- static permanents (wave 100D) -- Cosmos Charger

    chargers = static_perm100d.yours(plan, static_perm100d.FORETELL, plan.actor)
    if plan.state.turn.active_player != plan.actor and not chargers:
        raise ActionError("You can foretell a card only during your turn (702.143a)")
    cost = M.parse_cost(f"{{{max(0, 2 - chargers)}}}")
    if payment_step(plan, a, cost, f"foretelling {ch.name}", purpose=Purpose(special="foretell")):  # (review 19: 116.2h, not a cast)
        return
    from app.rules import special_payment_tails

    selected = next((ability for ability in ch.abilities if ability.index == a.ability), None)
    special_payment_tails.pay(plan, "foretell", card, ch, cost, f"paid {cost.text()} to foretell a card",
                              sources=a.sources, purpose=Purpose(special="foretell"),
                              granted_mana_cost=selected.granted_mana_cost if selected is not None else None)


def companion_problem(state: GameState, player: str, card: CardInstance, info: CardInfo) -> str | None:
    """Why ``player`` can't take this companion by the special action (116.2g, 103.2b, 702.139b), or None. (-- special actions (wave 50B) -- shared with ``can_act``.)"""
    mine = [c for c in state.cards.values() if c.owner == player and c.origin == "companion"]
    if len(mine) != 1:
        return "You may reveal no more than one companion (103.2b)"
    # 702.139b: the starting deck contains physical cards, including every merged
    # component and commander. Current copied characteristics do not remove one.
    start = [part for shell in state.cards.values() if not shell.ability
             for part in (shell.merged if shell.merged else [shell])
             if part.owner == player and part.origin in ('library', 'command')
             and not (part.is_token or part.test_object)]
    deck = [info.get(c.card_id) if c.card_id else None for c in start]
    data = info.get(card.card_id) if card.card_id else None
    if data is None or any(d is None for d in deck) or any(c.copy_of is not None for c in start):
        return "Fyodor doesn't know every card of your starting deck: take your companion by hand"
    return cmdr.companion_problem(data, [d for d in deck if d is not None])


def companion_action(plan: Plan, card: CardInstance, ch: Characteristics, a: A.ActivateAbility) -> None:
    """-- companion (wave 38D) -- 116.2g, 702.139a: a player who has chosen a companion may pay {3} to put it from outside the game into
    their hand, any time they have priority and the stack is empty during a main phase of their turn, once per game (a card that has
    left the companion zone has been taken: 702.139c). A special action: no stack, no response, not a cast or an ability (mana that can
    pay only for those can't pay it). The player's companion is the one card of the companion zone; its condition must hold for the
    starting deck (103.2b; 702.139b: the commander counts) — what isn't checked (a wording outside commander.COMPANION_RESTRICTIONS,
    a card Fyodor has no data for) is refused, never allowed."""
    state = plan.state
    ability = next((ab for ab in ch.abilities if ab.index == a.ability), None)
    if ability is None or "companion" not in ability.keywords:
        raise ActionError("Only a card's companion ability puts it into your hand from outside the game")
    if state.turn.active_player != plan.actor or state.turn.phase not in MAIN_PHASES or state.zones.get(STACK):
        raise ActionError("You can take your companion only in your main phase while the stack is empty (116.2g)")
    if (problem := companion_problem(state, plan.actor, card, plan.info)) is not None:
        raise ActionError(problem)
    cost = M.parse_cost("{3}")
    if payment_step(plan, a, cost, f"taking {ch.name}", purpose=Purpose()):
        return
    from app.rules import special_payment_tails

    special_payment_tails.pay(plan, "companion", card, ch, cost, f"paid {cost.text()} to put {ch.name} into their hand",
                              sources=a.sources, purpose=Purpose())


MADNESS = re.compile(r"^madness (?P<cost>(?:\{[^}]+\})+)$", re.IGNORECASE)
BUYBACK = re.compile(r"^buyback (?P<cost>(?:\{[^}]+\})+)$", re.IGNORECASE)
BUYBACK_PARTS = re.compile(r"^buyback—(?P<cost>[^{}]+)$", re.IGNORECASE)  # (wave 30E) "Buyback—Sacrifice a land." / "Discard two cards" / "Pay 4 life"


def buyback_parts_line(line: str) -> AbilityCost | None:
    """-- keywords (wave 30E) -- 702.27a: a buyback cost without mana ("Buyback—Sacrifice three Islands.", "Discard two cards", "Pay 4 life"):
    an additional cost (118.8) of the parts alt_costs reads, or None."""
    from app.rules import alt_costs, random_choice_receipts  # (leaves over this module)

    if (random_cost := random_choice_receipts.random_buyback(line)) is not None:
        return random_cost

    m = BUYBACK_PARTS.fullmatch(line.strip().rstrip("."))
    found = alt_costs.parse_cost(m["cost"]) if m else None
    return found.cost if found is not None and not found.mana and found.cost.components else None


def buyback_parts(ch: Characteristics) -> AbilityCost | None:
    return next((p for ab in ch.abilities if ab.kind == "keywords" and "buyback" in ab.keywords and (p := buyback_parts_line(ab.text)) is not None), None)
EVOKE = re.compile(r"^evoke (?P<cost>(?:\{[^}]+\})+)$", re.IGNORECASE)
DASH = re.compile(r"^dash (?P<cost>(?:\{[^}]+\})+)$", re.IGNORECASE)
AWAKEN = re.compile(r"^awaken (?P<n>\d+)—(?P<cost>(?:\{[^}]+\})+)$", re.IGNORECASE)  # (wave 16B) 702.113a


def kick_count(ch: Characteristics, times: int) -> int:
    """-- keywords (wave 50H) -- 702.33d: how many times the cast's ``kicker`` kicks it (the bits of a mask of two kicker costs, else the count)."""
    kick = kicker_cost(ch.abilities) if times else None
    return kick.paid(times) if kick is not None else times


def kick_mask(ch: Characteristics, times: int) -> int:
    """-- keywords (wave 50H) -- 702.33f: which of the two kicker costs were paid (1: the first, 2: the second); 0 for any other card."""
    kick = kicker_cost(ch.abilities) if times else None
    return times if kick is not None and kick.second else 0


def kicker_extra(ch: Characteristics, times: int, *, face_down: bool = False) -> M.ManaCost:
    """702.33a / 702.33c: the kicker cost paid ``times`` times — an additional cost (118.8) that
    joins the total cost (601.2f) before increases and reductions; the spell's mana cost and mana
    value don't change (118.8d)."""
    kick = None if face_down else kicker_cost(ch.abilities)  # (a face-down spell has no abilities, 708.2)
    if kick is None:
        raise ActionError(f"{ch.name or 'That spell'} has no kicker cost Fyodor can pay: kick it by hand with the table tools")
    if kick.second:  # -- keywords (wave 50H) -- 702.33b: ``times`` is a mask of the two costs, each paid at most once
        if not 1 <= times <= 3:
            raise ActionError(f"{ch.name} has two kicker costs: pay the first (1), the second (2) or both (3)")
        return M.parse_cost("".join(c for c, bit in ((kick.cost, 1), (kick.second, 2)) if times & bit))
    if times > 1 and not kick.multi:
        raise ActionError(f"{ch.name} can be kicked only once")  # (multikicker: any number of times, 702.33c)
    if not kick.cost:  # (-- casting extras (wave 18E) -- an entwine cost with no mana: paid as an additional cost)
        return M.ManaCost()
    extra = M.parse_cost(kick.cost)
    return M.ManaCost(extra.generic * times, extra.colored * times, extra.hybrid * times, extra.phyrexian * times, extra.x * times,
                      extra.unsupported * times)  # (wave 43D: "Kicker {X}", once: spell_cost gives the announced X to it)


def kicker_parts(ch: Characteristics, times: int) -> AbilityCost | None:
    """-- cast keywords (wave 43D) -- the parts of a kicker (squad, replicate, entwine) cost that isn't mana, paid ``times`` times with the other
    additional costs (702.33a, 702.42a, 601.2h): "Kicker—Sacrifice a land.", "Replicate—Tap an untapped Dalek you control."; None when it has none."""
    from app.rules import alt_costs

    kick = kicker_cost(ch.abilities) if times else None
    found = alt_costs.parse_cost(kick.extra) if kick is not None and kick.extra else None
    if found is None:
        return None
    n = 1 if kick is not None and kick.entwine else times
    return AbilityCost(components=found.cost.components * n, life=found.cost.life * n)


def cost_with_kicker(ch: Characteristics, cost: M.ManaCost, times: int, *, face_down: bool = False) -> M.ManaCost:
    """``cost`` plus the kicker cost ``times`` times (see ``kicker_extra``)."""
    extra = kicker_extra(ch, times, face_down=face_down)
    return M.ManaCost(cost.generic + extra.generic, cost.colored + extra.colored, cost.hybrid + extra.hybrid,
                      cost.phyrexian + extra.phyrexian, cost.x, cost.unsupported + extra.unsupported)


def keyword_cost(ch: Characteristics, word: str, pattern: re.Pattern[str], index: int | None = None) -> str | None:
    """The mana cost of a "<Keyword> {cost}" line (unearth, dash …), optionally on line ``index``."""
    for ab in ch.abilities:
        if ab.kind == "keywords" and word in ab.keywords and (index is None or ab.index == index):
            m = pattern.fullmatch(ab.text.strip().rstrip("."))
            if m:
                return m["cost"]
    return None


def unearth(plan: Plan, card: CardInstance, ch: Characteristics, a: A.ActivateAbility, cost_text: str) -> None:
    """702.84a: "{cost}: Return this card from your graveyard to the battlefield. It gains haste.
    Exile it at the beginning of the next end step. If it would leave the battlefield, exile it
    instead of putting it anywhere else. Activate only as a sorcery." """
    from app.rules import unearth_costs

    oid = plan.oid(card)
    activate_to_stack(plan, card, ch, unearth_costs.ability(a.ability, cost_text), a,
                      definition={"kind": "activated", "target": None,
                                  "effects": [{"do": "unearth", "card": card.id, "object": oid}]})


def crew_cost_line(line: str) -> int | None:
    """A crew keyword with only activation restrictions the shared engine understands."""
    body, _ = restrictions.split(line)
    m = CREW.fullmatch(body.strip().rstrip("."))
    return int(m["n"]) if m is not None and restrictions.parse(line) is not None else None


def crew_power(ch: Characteristics, index: int) -> int | None:
    """Crew N (702.122) on ability line ``index``: N, or None."""
    for ab in ch.abilities:
        if ab.index == index and ab.kind == "keywords":
            return crew_cost_line(ab.text)
    return None


def crew_value(c: CardInstance, ch: Characteristics) -> int:
    """What a creature counts toward crewing a Vehicle (702.122a: its power) — -- static_other sweep (wave 17C) -- or its toughness,
    or its power as though it were greater, while a static says so ("crews Vehicles using its toughness rather than its power")."""
    from app.rules.combat import power
    from app.rules.sba import toughness

    base = (toughness(c, ch) if "crew_toughness" in ch.imposed else power(c, ch)) or 0
    return max(0, base + sum(int(r.split(":")[1]) for r in ch.imposed if r.startswith("crew_plus:")))


def crew(plan: Plan, card: CardInstance, ch: Characteristics, a: A.ActivateAbility, n: int, kind: str = "crew") -> None:
    """Crew N: tap any number of untapped creatures you control with total power N or greater:
    this Vehicle becomes an artifact creature until end of turn. (Summoning-sick creatures may crew.)
    -- crew & saddle (wave 23D) -- ``kind`` "saddle" (702.171a): the same cost, "this permanent becomes saddled until end of turn.
    Activate only as a sorcery." (app/rules/crew_saddle.py)"""
    from app.rules import crew_saddle

    saddle = kind == "saddle"
    limits = restrictions.parse(_find_ability(ch, a.ability).text) or []
    if why := restrictions.problem(plan.state, plan.actor, card, a.ability, limits, plan, ch.name):
        raise ActionError(why)
    if saddle and (plan.state.turn.active_player != plan.actor or plan.state.turn.phase not in MAIN_PHASES or plan.state.zones.get(STACK)):
        raise ActionError("Saddle only as a sorcery: in your main phase with an empty stack")

    def crew_power_of(cid: str) -> int:
        c = plan.state.cards[cid]
        return crew_value(c, plan.ch(c))

    candidates = [c.id for c in plan.state.cards.values() if c.zone == card.zone and c.controller == plan.actor
                  and c.id != card.id and not c.tapped and plan.in_game(c) and plan.ch(c).is_creature
                  and (saddle or "cant_crew" not in plan.ch(c).imposed)]  # (wave 16F: Bound in Gold, 702.122d; review 23D: it may saddle)
    if sum(crew_power_of(c) for c in candidates) < n:
        raise ActionError(f"{ch.name}: you don't control untapped creatures with total power {n} or greater")
    if a.crew is None:
        decide(plan, player=plan.actor, kind="choose_cards", prompt=f"{kind.capitalize()} {n}: tap creatures with total power {n} or greater",
               options=[DecisionOption(id=c, label=f"{plan.state.cards[c].name} ({crew_power_of(c)})", card_id=c)
                        for c in candidates],
               min_choices=1, max_choices=len(candidates),
               resume={"step": "crew", "intent": a.model_dump(mode="json", exclude={"r", "actor", "ts"})}, source=card)
        return
    chosen = list(dict.fromkeys(a.crew))
    if not chosen or any(c not in candidates for c in chosen):
        raise ActionError(f"{kind.capitalize()} with untapped creatures you control")
    if sum(crew_power_of(c) for c in chosen) < n:
        raise ActionError(f"Those creatures have less than {n} total power")
    oid = plan.oid(card)
    ability_id = _new_ability(plan, card, f"{ch.name} becomes {'saddled' if saddle else 'an artifact creature'} until end of turn.")
    plan.do({"type": "tap", "card_ids": chosen, "tapped": True})
    crew_saddle.tapped_to_pay(plan, kind, chosen, card)  # (702.122b, 702.171c)
    if restrictions.limited(limits):
        restrictions.record_use(plan.rules, oid, a.ability, plan.state.turn.number)
    _stacked(plan, card, oid, ch, ability_id, [{"do": "saddled"}] if saddle else
             [{"do": "animate", "who": "self", "types": ["Artifact", "Creature"], "crewed": True, "crew_count80": len(chosen)}], cost_has_tap=False)


# -- static statics (wave 10B) -- cascade a permanent gives the spell as it's cast (cast_limits.granted_cascade)
def _granted_cascade(plan: Plan, card: CardInstance, ch: Characteristics, cast_from: str | None) -> int:
    from app.rules import cast_limits, turnstate100h

    return cast_limits.granted_cascade(plan, card.id, ch, cast_from) + turnstate100h.own_cascade(plan, card, ch, cast_from)  # (wave 100H: Bloodbraid Marauder, Yidris)


def _cascade_triggers(plan: Plan, card: CardInstance, ch: Characteristics, extra: int = 0) -> None:
    """702.85a: "When you cast this spell, …" — one trigger per instance of cascade (``extra``: those a static ability
    gave the spell, 10B)."""
    from app.rules.triggers import _add

    n = extra + sum(1 for ab in ch.abilities if ab.kind == "keywords" for kw in ab.keywords if kw == "cascade")
    for k in range(n):
        _add(plan, controller=plan.actor, source_card=card.id, source_object=plan.oid(card), name=ch.name,
             index=6000 + k, definition={"kind": "triggered", "trigger": "cascade", "optional": False, "target": None,
                                         "effects": [{"do": "cascade", "mv": ch.mana_value}]})


def _replicate_trigger(plan: Plan, card: CardInstance, ch: Characteristics, times: int) -> None:
    """-- keywords (wave 15E) -- 702.56a replicate: "When you cast this spell, copy it for each time you paid its replicate cost. You
    may choose new targets for the copies." (the cost is paid as kicker is: ``times``)"""
    from app.rules.triggers import _add

    if times and any(ab.kind == "keywords" and "replicate" in ab.keywords for ab in ch.abilities):
        _add(plan, controller=plan.actor, source_card=card.id, source_object=plan.oid(card), name=ch.name, index=6150,
             definition={"kind": "triggered", "trigger": "storm", "optional": False, "target": None,
                         "effects": [{"do": "storm", "spell": card.id, "object": plan.oid(card), "n": times}]})


def _demonstrate_trigger(plan: Plan, card: CardInstance, ch: Characteristics, cast_from: str | None = None) -> None:
    """-- cast keywords (wave 43D) -- 702.144a demonstrate: "When you cast this spell, you may copy it and you may choose new targets for the copy. If you
    copy the spell, choose an opponent. That player copies the spell and may choose new targets for that copy." (copying.demonstrate_copy)"""
    from app.rules import cast_limits
    from app.rules.triggers import _add

    instances = max(int("demonstrate" in ch.keywords),
                    sum(1 for ab in ch.abilities if ab.kind == "keywords" for keyword in ab.keywords if keyword == "demonstrate"))
    instances += cast_limits.granted_cascade(plan, card.id, ch, cast_from, "demonstrate")
    for index in range(instances):
        spell = {"spell": card.id, "object": plan.oid(card)}
        _add(plan, controller=plan.actor, source_card=card.id, source_object=plan.oid(card), name=ch.name, index=6170 + index,
             definition={"kind": "triggered", "trigger": "demonstrate", "optional": True, "target": None,
                         "effects": [{"do": "demonstrate_copy", **spell}, {"do": "demonstrate_opponent", **spell}]})


def _conspire_trigger(plan: Plan, card: CardInstance, ch: Characteristics, record: PaymentRecord) -> None:
    """-- static_other sweep (wave 17C) -- 702.78a: "When you cast this spell, if its conspire cost was paid, copy it. If the spell has
    any targets, you may choose new targets for the copy." (the copy is storm's: copying.storm)"""
    from app.rules import casualty_x
    from app.rules.triggers import _add

    exceptions = ([{"remove_supertypes": ["Legendary"], "loyalty": record.x or 0}]
                  if casualty_x.has(ch) and f"optional:{card.id}:casualty" in record.additional else [])
    # (-- casting extras (wave 18E) -- 702.153a casualty: "When you cast this spell, if a casualty cost was paid for it, copy it.")
    if f"optional:{card.id}:conspire" in record.additional or f"optional:{card.id}:casualty" in record.additional:
        _add(plan, controller=plan.actor, source_card=card.id, source_object=plan.oid(card), name=ch.name, index=6160,
             definition={"kind": "triggered", "trigger": "storm", "optional": False, "target": None,
                         "effects": [{"do": "storm", "spell": card.id, "object": plan.oid(card), "n": 1,
                                      **({"excepts": exceptions} if exceptions else {})}]})


def _ripple_triggers(plan: Plan, card: CardInstance, ch: Characteristics, cast_from: str | None) -> None:
    """-- static_other sweep (wave 17C) -- 702.60a ripple N: "When you cast this spell, you may reveal the top N cards of your library. You may
    cast any of the revealed cards with the same name as this spell without paying their mana costs. Put all revealed cards not cast this
    way on the bottom of your library in any order." One trigger per instance (702.60b), its own and those a static ability gave it."""
    from app.rules import cast_limits
    from app.rules.triggers import _add

    ns = [int(m[1]) for ab in ch.abilities if ab.kind == "keywords" for m in [re.fullmatch(r"(?i)ripple (\d+)\.?", ab.text.strip())] if m]
    ns += [int(d["n"]) for d in cast_limits.granted_instances(plan, card.id, ch, cast_from, "ripple")]
    for k, n in enumerate(ns):
        _add(plan, controller=plan.actor, source_card=card.id, source_object=plan.oid(card), name=ch.name, index=6200 + k,
             definition={"kind": "triggered", "trigger": "ripple", "optional": False, "target": None, "effects": [
                 {"do": "look_top", "n": n, "player": "you", "reveal": True, "optional": True},
                 {"do": "ripple_split", "name": ch.name},
                 {"do": "ripple_cast"},  # (-- free-cast cleanup (wave 30A) -- before the rest go: a card not cast joins them in one order)
                 {"do": "rest_looked", "to": "bottom_any"}]})


def _storm_triggers(plan: Plan, card: CardInstance, ch: Characteristics, cast_from: str | None) -> None:
    """The storm triggers of a spell just cast: one per instance, its own (gravestorm too) and those a static ability gave it
    (-- static_other sweep (wave 17C) -- 702.40b: each triggers separately)."""
    from app.rules import cast_limits

    granted = cast_limits.granted_cascade(plan, card.id, ch, cast_from, "storm")
    own = "storm" in ch.keywords or "gravestorm" in ch.keywords
    for k in range(granted + int(own)):
        _storm_trigger(plan, card, ch, k)


def _storm_trigger(plan: Plan, card: CardInstance, ch: Characteristics, k: int = 0) -> None:
    """702.40a: "When you cast this spell, copy it for each other spell that was cast before it
    this turn. You may choose new targets for the copies." """
    from app.rules.triggers import _add

    r = plan.rules
    turn = plan.state.turn.number
    before = sum(r.spells_this_turn(p, turn) for p in plan.state.seat_order)
    if "gravestorm" in ch.keywords:  # -- static_other sweep (wave 16B) -- 702.69a: each permanent put into a graveyard from the battlefield this turn (tokens too)
        from app.rules import history

        before = sum(1 for d in history.log_for(plan).left if d.to == "graveyard")
    if before:
        _add(plan, controller=plan.actor, source_card=card.id, source_object=plan.oid(card), name=ch.name, index=6100 + k,
             definition={"kind": "triggered", "trigger": "storm", "optional": False, "target": None,
                         "effects": [{"do": "storm", "spell": card.id, "object": plan.oid(card), "n": before}]})


# -- free-cast optional costs (wave 41D) --
def optional_announced(plan: Plan, a: A.CastSpell, card: CardInstance, ch: Characteristics) -> tuple[list[Any], str | None, bool] | None:
    """601.2b: the optional additional costs the intent names, each checked now, the opponent a promised gift goes to (702.174a: asked as a
    decision when there is a choice) and whether the bargain cost is paid (702.166b). One announcement for a cast with its cost and for a free
    one (118.9d: ``cast_free``). None while the gift's opponent is asked."""
    from app.rules import cost_changes

    optional = cost_changes.chosen_optional(plan.state, plan.actor, card, ch, plan.info, a.optional_costs) \
        if a.optional_costs and not plan.manual(card) else []
    from app.rules import casualty_x

    if casualty_x.announce(plan, a, card, ch, optional):
        return None
    gift_to: str | None = None
    if any(o.kind == "gift" for o in optional):  # -- gift (wave 23D) -- 702.174a: the opponent the gift is promised to
        from app.rules import gift

        found_gift = gift.announce(plan, a, card, ch)
        if found_gift is gift.WAITING:
            return None
        gift_to = found_gift
    if not plan.manual(card):  # -- cast-time choice (wave 110E) -- 601.2b
        from app.rules import wave110e_opp

        if (picked := wave110e_opp.announce(plan, a, card, ch)) is wave110e_opp.WAITING:
            return None
        a.pick110e = picked
    if a.optional_costs and plan.manual(card):
        raise ActionError("That card is played by hand: pay its costs with the table tools")
    return optional, gift_to, any(o.kind == "bargain" for o in optional)  # -- keywords (wave 30E) -- 702.166b: its controller declared the intention to pay it


def optional_parts(optional: list[Any], x: int = 0) -> AbilityCost | None:
    """The cost parts the announced optional costs add (paid with the rest, 601.2h): a sacrifice, a tap, life; a gift costs nothing (wave 23D)."""
    from app.rules import cost_changes

    parts = tuple(c for o in optional if (c := cost_changes.keyword_component(o, x) if o.kind else costs.CostComponent(
        costs.PAY_LIFE, amount=o.life, text=f"Pay {o.life} life")) is not None)
    return costs.AbilityCost(components=parts, life=sum(o.life for o in optional)) if parts else None


FREE_KICKS = 6  # quick choices only; a typed count uses the platform range 0..1000


def free_optional_offers(plan: Plan, card: CardInstance, ch: Characteristics) -> list[tuple[str, str]]:
    """118.9d: the optional additional costs the caster of a spell cast without paying its mana cost could pay, each one now possible (id, label):
    the kicker cost ("kicker:N", N times; the mana is paid with the total cost, 601.2f) and the costs of ``cost_changes.optional_offers`` (bargain,
    gift, casualty, conspire, teamwork, collect evidence, behold). Only what is public decides whether one is offered (mana, the permanents to
    sacrifice or tap, an opponent): "behold" may be paid from the hand, so it is always offered (the cast refuses it if it can't be paid). A
    permanent's "you may pay 2 life" that reduces one colour (Defiler of Vigor) is not asked: it changes nothing when no mana is paid."""
    from app.rules import cost_changes

    r = plan.rules
    pending = r.free_cast_then
    paid = pending is not None and pending["card"] == card.id and bool(pending["e"].get("paid"))  # (707.12: the copy's mana cost is paid)
    alt = ch.mana_cost if paid else r.alt_costs.get(card.id)
    from app.rules import effect_cast_costs

    alternative_parts = None
    if alt is not None and not paid:
        alt, alternative_parts = effect_cast_costs.textual_alternative(alt)
    out: list[tuple[str, str]] = []
    if (kick := kicker_cost(ch.abilities)) is not None and not kick.entwine:  # (702.42a: entwine by hand)
        for n in range(1, 4 if kick.second else FREE_KICKS + 1 if kick.multi else 2):  # (wave 50H: the masks of two costs)
            try:
                selected_costs: list[bool | None] = []
                ways = spell_cost_ways(plan.state, card, ch, info=plan.info, player=plan.actor, free=alt is None,
                                       alternative=M.parse_cost(alt) if alt is not None else None, kicker=n, x=kick.minimum_x, selected_costs=selected_costs)
            except ActionError:
                break  # (a kicker cost Fyodor can't pay)
            if not any(can_pay(plan.state, plan.actor, total, plan.info,
                               purpose=Purpose(spell=ch, card=card.id, zone=card.zone, player=plan.actor, kicked=True,
                                               spell_object=_spell_reference(plan.state, card), selected_cost_has_x=cost_x),
                               reserve=life_due + (alternative_parts.life if alternative_parts is not None else 0))
                       for (total, life_due), cost_x in zip(ways, selected_costs, strict=True)):
                if kick.second:
                    continue  # (-- keywords (wave 50H) -- another of the two costs may still be payable)
                break
            if (more := kicker_parts(ch, n)) is not None and not any(c.kind in _HAND_PARTS for c in more.components) \
                    and additional_problem(plan, more, card, plan.actor):
                break  # (-- cast keywords (wave 43D) -- a "Kicker—Sacrifice a land." with nothing to sacrifice; a part paid from the hand is always offered: no omission tells)
            out.append((f"kicker:{n}", f"Kicker {(kick.cost, kick.second, kick.cost + ' and ' + kick.second)[n - 1]}" if kick.second
                        else kick.text if n == 1 else f"{kick.text}, paid {n} times"))
    if kick is not None and kick.multi:
        out.append(("kicker:other", "Multikicker: another count (0–1000)"))
    for o in cost_changes.optional_offers(plan.state, plan.actor, card, ch, plan.info):
        if not o.kind or o.kind == "offering":  # (-- offering (wave 51H) -- 702.48a: a reduction of a cost that is {0} here, and no timing to change)
            continue
        part = cost_changes.keyword_component(o)
        if part is None:  # a gift: an opponent to give it to (702.174a)
            if len(plan.live()) < 2:
                continue
        elif o.kind != "behold" and additional_problem(plan, costs.AbilityCost(components=(part,)), card, plan.actor):
            continue
        out.append((o.source, o.label))
    return out


def announce_free_optional(plan: Plan, a: A.CastSpell, card: CardInstance, ch: Characteristics) -> bool:
    """601.2b, 118.9d: ask the caster of a free cast which optional additional costs to pay (privately; none may be chosen), unless the intent
    already announced them (``kicker``, ``optional_costs``) or they were asked. True while the question waits; its answer re-runs the cast."""
    if a.optional_asked or a.kicker or a.optional_costs or plan.manual(card):
        return False
    offers = free_optional_offers(plan, card, ch)
    if not offers:
        return False
    decide(plan, player=plan.actor, kind="choose_cards", prompt=f"{ch.name or 'This spell'}: pay any optional additional costs? (118.9d, 601.2b)",
           options=[DecisionOption(id=i, label=text) for i, text in offers], min_choices=0, max_choices=len(offers),
           resume=_announcing(plan, "free_optional", a, card_object=plan.oid(card)), source=card)
    return True


def announce_free_x(plan: Plan, a: A.CastSpell, card: CardInstance, ch: Characteristics) -> bool:
    """-- cast keywords (wave 43D) -- 107.3a: a free cast whose alternative cost (miracle, madness) or kicker cost has {X} announces X with it (107.3b's 0
    is for the spell's own mana cost): asked privately, up to what the caster's mana pays. True while the question waits; its answer re-runs the cast."""

    from app.rules import alt_costs

    r = plan.rules
    pending = r.free_cast_then
    paid = pending is not None and pending["card"] == card.id and bool(pending["e"].get("paid"))  # 707.12: announce and pay the copy's mana-cost X
    alt = (alt_costs.chosen(plan, a.alt_cost, card, ch).alt.mana_cost.text() if a.alt_cost is not None else ch.mana_cost) if paid else r.alt_costs.get(card.id)
    from app.rules import effect_cast_costs

    alternative_parts = None
    if alt is not None and not paid:
        alt, alternative_parts = effect_cast_costs.textual_alternative(alt)
    kick = kicker_cost(ch.abilities) if a.kicker and not plan.manual(card) else None
    if a.x_value is not None or not ((kick is not None and kick.x) or (alt is not None and M.parse_cost(alt).x)):
        return False
    options: list[DecisionOption] = []
    for n in range(kick.minimum_x if kick is not None and kick.x else 0, 1001):  # actual selected kicker lower bound
        x_payments: list[dict[str, Any] | None] = []
        selected_costs: list[bool | None] = []
        ways = spell_cost_ways(plan.state, card, ch, x=n, info=plan.info, player=plan.actor, free=alt is None,
                               alternative=M.parse_cost(alt) if alt is not None else None, kicker=a.kicker, x_payments=x_payments,
                               selected_costs=selected_costs)
        if not any(can_pay(plan.state, plan.actor, total, plan.info,
                           purpose=Purpose(spell=ch, card=card.id, zone=card.zone, player=plan.actor, kicked=bool(a.kicker),
                                           spell_object=_spell_reference(plan.state, card), x_payment=x_payments[i], selected_cost_has_x=selected_costs[i]),
                           reserve=life_due + (alternative_parts.life if alternative_parts is not None else 0)) for i, (total, life_due) in enumerate(ways)):
            break
        options.append(DecisionOption(id=f"x:{n}", label=str(n)))
    if not options and kick is not None and kick.minimum_x:
        raise ActionError(f"{ch.name}: you cannot pay its minimum kicker X")
    if paid:
        options.append(DecisionOption(id="x:other", label="Another value for X (0–1000)"))
    decide(plan, player=plan.actor, kind="choose_one", prompt=f"{ch.name or 'This spell'}: choose a value for X (107.3a)",
           options=options or [DecisionOption(id="x:0", label="0")],
           resume=_announcing(plan, "free_x", a, card_object=plan.oid(card), paid_x=paid), source=card)
    return True


def resume_spell_symbols(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import spell_symbol_choices

    spell_symbol_choices.resume(plan, d, chosen)


def resume_flashback_choice(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import flashback_choices

    flashback_choices.resume(plan, d, chosen)


def resume_casualty_x(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import casualty_x

    casualty_x.resume(plan, d, chosen)


def _paid_x_identity(plan: Plan, intent: A.CastSpell, resume: dict[str, Any]) -> None:
    """A numeric paid-copy continuation belongs to the originally selected spell object and authority."""
    pending = plan.rules.free_cast_then
    if (not resume.get("paid_x") or resume.get("card_object") is None
            or plan.oid(intent.card_id) != resume["card_object"] or pending is None
            or pending["card"] != intent.card_id or not pending["e"].get("paid")):
        raise ActionError("The original paid spell object or casting permission is no longer available")


def resume_paid_x_number(plan: Plan, d: Any, chosen: list[str]) -> None:
    """Type X in the platform range; actual payment, including SELF mana abilities, checks its cost."""
    from app.rules.engine import INTENTS

    if cancelled(plan, d, chosen):
        return
    count = int(chosen[0])
    if not 0 <= count <= 1000:
        raise ActionError("Choose X from 0 to 1000 (platform numeric range)")
    intent = A.parse_action(d.resume["intent"])
    assert isinstance(intent, A.CastSpell)
    _paid_x_identity(plan, intent, d.resume)
    intent.x_value = count
    plan.rules.priority = d.player
    plan.rules.passed = []
    INTENTS[intent.type](plan, intent)


def resume_free_x(plan: Plan, d: Any, chosen: list[str]) -> None:
    """The caster's X: the cast goes on with it announced."""
    from app.rules.engine import INTENTS  # the engine imports this module

    intent = A.parse_action(d.resume["intent"])
    if chosen == ["x:other"]:
        assert isinstance(intent, A.CastSpell)
        _paid_x_identity(plan, intent, d.resume)
        decide(plan, player=d.player, kind="choose_one", prompt="Choose X (platform range 0–1000)",
               options=[DecisionOption(id="__number__", label="Paid spell X: 0–1000")],
               resume=_announcing(plan, "paid_x_number", intent, card_object=d.resume["card_object"], paid_x=True),
               source=plan.state.cards[intent.card_id])
        return
    intent.x_value = int(chosen[0].split(":")[1])  # type: ignore[union-attr]
    plan.rules.priority = d.player
    plan.rules.passed = []
    INTENTS[intent.type](plan, intent)


def resume_free_optional(plan: Plan, d: Any, chosen: list[str]) -> None:
    """The caster's answer: the cast goes on with those costs announced (``kicker``, ``optional_costs``)."""
    from app.rules.engine import INTENTS  # the engine imports this module

    intent = A.parse_action(d.resume["intent"])
    kicks = [c for c in chosen if c.startswith("kicker:")]
    if len(kicks) > 1:
        raise ActionError("Pay the kicker cost one number of times")
    if kicks == ["kicker:other"]:
        assert isinstance(intent, A.CastSpell)
        if d.resume.get("card_object") is None or plan.oid(intent.card_id) != d.resume["card_object"]:
            raise ActionError("That spell is a different object now")
        intent.optional_costs = [c for c in chosen if not c.startswith("kicker:")]
        intent.optional_asked = True
        decide(plan, player=d.player, kind="choose_one", prompt="Choose a multikicker count (platform range 0–1000)",
               options=[DecisionOption(id="__number__", label="Multikicker count: 0–1000")],
               resume=_announcing(plan, "free_multikicker", intent, card_object=plan.oid(intent.card_id)), source=plan.state.cards[intent.card_id])
        return
    intent.kicker = int(kicks[0].split(":")[1]) if kicks else 0  # type: ignore[union-attr]
    intent.optional_costs = [c for c in chosen if not c.startswith("kicker:")]  # type: ignore[union-attr]
    intent.optional_asked = True  # type: ignore[union-attr]
    plan.rules.priority = d.player
    plan.rules.passed = []
    INTENTS[intent.type](plan, intent)


# -- cast without paying (wave 3C) --
def cast_free(plan: Plan, card: CardInstance, ch: Characteristics, a: A.CastSpell) -> None:
    """Cast a card the engine let its player cast without paying its mana cost, as an effect
    resolves (CR 608.2g: the steps of 601.2a-i, timing ignored): a suspended card (702.62d),
    cascade, rebound, madness (its cost instead), "you may cast a spell with mana value N or less
    from your hand without paying its mana cost". Only cards the engine listed in ``free_casts``.
    X is 0 (107.3b); kicker and other additional costs may still be paid (118.9d); modes, an
    Aura's target and "when you cast" triggers (storm, cascade) work as for any cast."""
    from app.rules import text_global_word71

    global_text_prepared71 = bool(text_global_word71.global_changes(plan.state, card.model_copy(update={'zone': 'stack'}), plan.info))
    ch = text_global_word71.prospective(plan.state, card, ch, plan.info)
    r = plan.rules
    if card.id not in r.free_casts or card.zone == STACK or ch.is_land:
        raise ActionError("You can't cast that without paying its mana cost now")
    pending = r.free_cast_then  # (review 28A) only the half / face the effect's choice named; a cascaded, suspended … card is cast as it is
    from app.rules import effect_cast_costs

    required_effect = pending.get('e', {}) if pending is not None and pending.get('card') == card.id else {}
    required_alternative = effect_cast_costs.kind(required_effect)
    if required_alternative and (a.alt_cost is not None or a.evoke or a.dash or a.awaken or a.face_down):
        raise ActionError('Only one alternative cost can be applied to a spell')
    if pending is not None and pending["card"] == card.id and pending.get("object") is not None and plan.oid(card) != pending["object"]:
        raise ActionError("That exiled card is no longer the same object")
    if pending is not None and pending["card"] == card.id and pending.get("e", {}).get("exact_refs") \
            and card.id not in permissions._free_pool(plan, pending["ctx"], pending["e"]):
        raise ActionError("That revealed card is no longer the same object")
    # -- granted casts (wave 29B) -- "yes@1" of a cascade, discover, ripple, suspend, rebound names a face too
    from app.rules import granted_casts

    if not granted_casts.face_ok(r, card.id, a.face) and not (a.face and pending is not None and pending["card"] == card.id
                                                              and pending.get("face") == a.face):
        raise ActionError("That face of the card can't be cast this way")
    if a.splice or a.prototype or a.buyback:  # (-- free-cast optional costs (wave 41D) -- buyback too: it was dropped without a word)
        raise ActionError("Splice, prototype and buyback by hand: Fyodor does them only when a spell is cast with its cost")
    if a.kicker and (ek := kicker_cost(ch.abilities)) is not None and ek.entwine:  # (-- review (wave 18E) -- 702.42a: all modes, by hand here)
        raise ActionError("Entwine by hand: Fyodor entwines a spell only when it is cast with its cost")
    if "Legendary" in ch.supertypes and ch.is_instant_or_sorcery and not _controls_legendary(plan.state, plan.actor, plan.info):
        raise ActionError(f"{ch.name} needs you to control a legendary creature or planeswalker")  # 205.4e
    # -- cast limits (wave 5E) -- 601.3 applies to a cast as something resolves too
    from app.rules import cast_limits

    limited = cast_limits.cast_problem(plan.state, plan.actor, card, ch, plan.info, resolving=True)
    if limited:
        raise ActionError(limited)
    from app.rules import cast_timing

    if (timed := cast_timing.problem(plan.state, plan.actor, card, ch, plan.info)) is not None:
        raise ActionError(timed)
    # -- static wordings (wave 6E) -- 118.9d: a choice of additional costs is still announced (601.2b) and paid
    from app.rules import alt_costs, cost_changes, either_costs

    either = None if plan.manual(card) else either_costs.announce(plan, a, card, ch)
    if either is either_costs.WAITING:
        return
    if announce_free_optional(plan, a, card, ch):  # -- free-cast optional costs (wave 41D) -- 118.9d, 601.2b: kicker, bargain, gift, casualty … are announced too
        return
    if announce_free_x(plan, a, card, ch):  # -- cast keywords (wave 43D) -- 107.3a: "Kicker {X}" kicked on a free cast, a miracle cost with {X}: X is announced with it
        return
    if a.kicker and (minimum_kick := kicker_cost(ch.abilities)) is not None and (a.x_value or 0) < minimum_kick.minimum_x:
        raise ActionError(f"{ch.name}: kicker X must be at least {minimum_kick.minimum_x}")
    if M.parse_cost(ch.mana_cost).x and (limited := cast_limits.cast_problem(plan.state, plan.actor, card, ch, plan.info, resolving=True, announced=a.x_value or 0)):
        raise ActionError(limited)  # -- review 38 -- 601.2e, 107.3b: X is 0 unless a miracle cost with {X} announced it
    definition = None if plan.manual(card) else scripts.spell_definition(ch)
    definition = per_opponent.for_cast(plan, card.id, definition)  # -- per-opponent targets (wave 23A) --
    if definition is not None and (a.x_value or 0) < definition.get("x_min", 0):
        raise ActionError(f"{ch.name}: X can't be {a.x_value or 0}")
    aura = None if plan.manual(card) else attachments.enchant_selector(ch)
    from app.rules import static_perm100d  # -- static permanents (wave 100D) -- 601.2c

    aura = static_perm100d.cast_aura(ch, aura)
    slots: list[list[TargetRef]] = []
    slot_specs: list[dict[str, Any] | None] = []
    picked: list[int] = []
    if definition is not None and definition.get("modes"):
        from app.rules.modal_abilities import printed_order

        a.modes, a.targets = printed_order(definition, a.modes, a.targets)
        modes = choose_modes(plan, a, definition, ch.name or "it")
        if modes is None:
            return
        picked = modes
        if len(picked) > 1 and escalate_cost(ch) is not None:  # (-- static_other sweep (wave 16B) -- its escalate cost is still paid, 118.9d)
            raise ActionError("Choose one mode: the escalate cost of a spell cast without paying its mana cost is paid by hand")
        grouped = modal_groups(definition, picked)  # -- static_other sweep (wave 16B) --
        if grouped is not None:
            picked_targets = choose_targets(plan, a, {"targets": grouped}, ch.name or "it")
            if picked_targets is None:
                return
        else:
            slot_specs = [definition["modes"][i]["target"] for i in picked]
            found = choose_slot_targets(plan, a, slot_specs, ch.name or "it")
            if found is None:
                return
            slots = found
            picked_targets = ChosenTargets(flat=[t for slot in slots for t in slot])
    else:
        found_targets = choose_targets(plan, a, definition if aura is None else {"target": {"what": aura}}, ch.name or "it")
        if found_targets is None:
            return  # waiting for the target choice; the grant stays
        picked_targets = found_targets
    chosen = picked_targets.flat
    announced = optional_announced(plan, a, card, ch)  # -- free-cast optional costs (wave 41D) --
    if announced is None:
        return
    optional, gift_to, bargained = announced
    alt = r.alt_costs.get(card.id)
    pending = r.free_cast_then  # -- cast a copy (wave 18F) -- 707.12: "You may cast the copy." pays its mana cost (never a flashback cost)
    paid = pending is not None and pending["card"] == card.id and bool(pending["e"].get("paid"))
    if paid:
        alt = ch.mana_cost
    alternative_parts = None
    if alt is not None and not paid:
        alt, alternative_parts = effect_cast_costs.textual_alternative(alt)
    # 118.9d / 601.2b: a spell's own additional cost ("As an additional cost to cast this spell,
    # sacrifice a creature": Fling cast by cascade) is still paid — chosen now, paid with the rest
    add_cost = None if plan.manual(card) else costs.spell_additional_cost(ch.abilities)
    if either is not None:  # -- static wordings (wave 6E) --
        add_cost = either if either.components else None
    if alternative_parts is not None:
        add_cost = alt_costs.merged(add_cost, alternative_parts)
    if required_alternative:
        add_cost = alt_costs.merged(add_cost, effect_cast_costs.cost(required_effect, ch))
    if (optional_more := optional_parts(optional, a.x_value or 0)) is not None:  # -- free-cast optional costs (wave 41D) -- paid with the rest (601.2h)
        add_cost = alt_costs.merged(add_cost, optional_more)
    if (kick_more := kicker_parts(ch, a.kicker)) is not None:  # -- cast keywords (wave 43D) -- "Kicker—Sacrifice a land." is still paid (118.9d)
        add_cost = alt_costs.merged(add_cost, kick_more)
    add_objects: dict[int, list[str]] = {}
    if add_cost is not None:
        problem = additional_problem(plan, add_cost, card, plan.actor) or life_x_problem(plan, add_cost, a, plan.actor)  # (4K)
        if problem:
            raise ActionError(problem)
        plan.reserved_life = add_cost.life + ((a.x_value or 0) if add_cost.life_x else 0)  # (wave 29C: 119.4, with Phyrexian mana's life)
        found_objects = cost_payment.choose(plan, a, add_cost, card, ch.name or "it")
        if found_objects is None:
            return  # waiting for the payer's choice; nothing has been paid (the grant stays)
        add_objects = found_objects
    not_mana = cost_payment.excluded(add_cost, card, add_objects) if add_cost is not None else ()
    # 118.9d / 601.2f: additional costs (kicker), increases and reductions still apply to the
    # alternative cost — {0}, or the madness cost
    mode_costs = [M.parse_cost(definition["modes"][i]["cost"]) for i in picked if definition and definition["modes"][i].get("cost")]  # (30E: spree, 118.9d)
    from app.rules import cast_limits, spell_mana_floor, spell_symbol_choices, waterbend103

    prepared: list[Any] = []
    cost = spell_cost(plan.state, card, ch, a.x_value or 0, plan.info, player=plan.actor, free=alt is None,
                      alternative=M.parse_cost(alt) if alt is not None else None, kicker=a.kicker,
                      targets=tuple(t.id for t in chosen),  # (wave 4I: "spells that target …")
                      additional=(*((M.parse_cost(either.mana),) if either is not None and either.mana else ()), *mode_costs, waterbend103.mana(optional)),  # (wave 6E)
                      reduce=cost_payment.reduction(add_cost, add_objects) if add_cost is not None else 0,
                      mana_symbols=a.mana_symbols, capture=prepared, announced_kicker77=True)  # (wave 47C: 118.9d, 601.2f)
    if spell_mana_floor.minimum(plan.state, plan.info) or a.mana_symbols is not None:
        if spell_symbol_choices.announce(plan, a, card, ch, prepared[0]):
            return
        cost = prepared[0].evaluate(a.mana_symbols)
    cost = cost_changes.reduce_only(cost, tuple(o.mana for o in optional if o.mana))  # (wave 41D, as the cast with its cost)
    x_maximum = min(a.x_value or 0, cost.generic)
    if spell_mana_floor.minimum(plan.state, plan.info):
        cost = spell_mana_floor.apply(plan.state, plan.info, cost)
    from app.rules import waterbend102

    cost = waterbend102.due(cost,add_cost,add_objects)
    cost_colorless = 'C' in cost.colored
    spend_mode = cast_limits.spend_mode(plan.state, plan.actor, card, ch, plan.info)
    if spend_mode:
        cost = M.spend_as(cost, spend_mode)
    was_locked = plan.locked_cost is not None
    cost = _locked(plan, cost)  # (wave 4I: 601.2f)
    if paid and pending is not None and pending["e"].get("spend"):  # -- cast-permission riders (wave 38C) -- 118.14: "…, and mana of any type can be spent to cast that spell" (Quistis)
        cost = M.spend_as(cost, pending["e"]["spend"])
    from app.rules import as_cast_values42

    data = _PostFreeCast(a, add_cost, add_objects, alt, aura, bargained, card, ch, chosen, definition, gift_to, optional, paid, picked, picked_targets, slot_specs, slots)
    data.global_text_prepared71 = global_text_prepared71
    data.cast_greatest_power = as_cast_values42.capture(plan, definition)
    if alt is not None or not cost.is_free:
        from app.rules import x_mana_restrictions

        x_reduction = prepared[0].raw.generic - prepared[0].evaluate(a.mana_symbols).generic
        x_payment = x_mana_restrictions.metadata(ch.oracle_text, a.x_value or 0, x_reduction, cost, maximum=x_maximum,
            mode=(pending["e"]["spend"] if paid and pending is not None and pending["e"].get("spend") else cast_limits.spend_mode(plan.state, plan.actor, card, ch, plan.info)),
            locked=plan.locked_x_payment)
        purpose = Purpose(spell=ch, zone=card.zone, player=plan.actor, kicked=bool(a.kicker), x_payment=x_payment,
                          **{'spell_object': _spell_reference(plan.state, card),
                             **(plan.locked_payment_context or {'cost_colorless':cost_colorless,
                                                              'selected_cost_has_x':prepared[0].selected_cost_has_x})})
        announced_cost = cost if a.mana_symbols is not None else announce_phyrexian(plan, a, cost, ch.name or "it", exclude=not_mana, purpose=purpose, trusted=was_locked)  # (wave 50B: 601.2b)
        if announced_cost is None:
            return
        cost = announced_cost
        if payment_step(plan, a, cost, ch.name or "it", exclude=not_mana, purpose=purpose,
                        cast_greatest_power=data.cast_greatest_power):
            return
        kind = "miracle" if card.id in r.miracled else "madness"  # -- casting extras (wave 18E) -- 702.94a: its miracle cost
        data.kind = kind
        from app.rules import payment_continuations as pc

        after = pc.continuation(plan, "post_free_cast", data)
        pay_spell_then(plan, a, card, ch, cost, f"paid {cost.text()} for {ch.name}" + (f" ({kind})" if alt and not paid else ""),
                       not_mana=not_mana, then=after, x_payment=x_payment, payment_context=_purpose_context(purpose))
        return
    data.record = PaymentRecord(card=card.id, controller=plan.actor, alternative="free", x_black_spent=0, splice_text71=SpliceText71(name=ch.name))
    _post_free_cast(plan, data, None)


@dataclass
class _PostFreeCast:
    a: A.CastSpell
    add_cost: AbilityCost | None
    add_objects: dict[int, list[str]]
    alt: str | None
    aura: str | None
    bargained: bool
    card: CardInstance
    ch: Characteristics
    chosen: list[TargetRef]
    definition: dict[str, Any] | None
    gift_to: str | None
    optional: list[cost_changes.Optional]
    paid: bool
    picked: list[int]
    picked_targets: ChosenTargets
    slot_specs: list[dict[str, Any] | None]
    slots: list[list[TargetRef]]
    kind: str = ""
    record: PaymentRecord | None = None
    cast_greatest_power: int | None = None
    global_text_prepared71: bool = False


def _post_free_cast(plan: Plan, data: _PostFreeCast, payment: M.Payment | None) -> None:
    from app.rules import waterbend102
    record = data.record
    assert record is not None
    record.cast_greatest_power = data.cast_greatest_power
    record.splice_text71 = SpliceText71(name=data.ch.name, global_change=data.global_text_prepared71)
    r = plan.rules
    a = data.a
    add_cost = data.add_cost
    add_objects = data.add_objects
    alt = data.alt
    aura = data.aura
    bargained = data.bargained
    ch = data.ch
    chosen = data.chosen
    definition = data.definition
    from app.rules import as_cast_values42

    effect_x = as_cast_values42.stack_x(definition, data.cast_greatest_power, a.x_value)
    gift_to = data.gift_to
    optional = data.optional
    paid = data.paid
    picked = data.picked
    picked_targets = data.picked_targets
    slot_specs = data.slot_specs
    slots = data.slots
    card = plan.state.cards.get(data.card.id) or data.card
    kind = data.kind
    record.alternative = "" if paid else kind if alt is not None else "free"
    required = (r.free_cast_then or {}).get('e', {}).get('effect_alternative')
    if required:
        record.alternative = required
    r.alt_costs.pop(card.id, None)
    record.additional = (["kicker"] if a.kicker else []) + [f"optional:{o.source}" for o in optional]  # -- free-cast optional costs (wave 41D) --
    record.kicked_mask = kick_mask(ch, a.kicker)  # (-- keywords (wave 50H) --)
    record.kicked = kick_count(ch, a.kicker) or int(gift_to is not None or bargained)  # (702.33d; a promised gift and a bargain read as kicked, as with the cost: 702.174k, 702.166)
    record.gift_to = gift_to
    record.pick110e = a.pick110e  # (wave 110E)
    pending_suspend = r.free_cast_then or {}
    was_suspended = (pending_suspend["suspend_object"] == plan.oid(card) if "suspend_object" in pending_suspend
                     else card.id in r.suspended)  # absent only: preserve legacy saved announcement behavior
    from_hand = card.zone == zone_key(plan.actor, "hand")
    _note_cast(plan, record, card.zone.rsplit(":", 1)[-1], zone_player=card.zone.split(":", 1)[0] if ":" in card.zone else None)  # -- refused modal/conditional (wave 3R1) --
    r.free_casts = [c for c in r.free_casts if c != card.id]
    r.free_cast_faces.pop(card.id, None)  # (wave 29B)
    r.miracled = [c for c in r.miracled if c != card.id]
    r.suspended = [c for c in r.suspended if c != card.id]
    if card.counters.get("time"):
        plan.do({"type": "counter", "card_ids": [card.id], "kind": "time", "delta": -card.counters["time"]})
    if a.x_value is None and M.parse_cost(ch.mana_cost).x:
        a.x_value = 0  # X is 0 when a spell is cast without paying its mana cost (107.3b)
    from_oid = plan.oid(card)  # (-- as long as (wave 37A) --)
    plan.do({"type": "move", "card_ids": [card.id], "to": {"zone": "stack"}})
    if a.face and plan.state.cards[card.id].face != a.face:  # -- play now (wave 28A) -- 712.11b, 709.3b: the half / back face being cast
        plan.do({"type": "set_face", "card_id": card.id, "face": a.face})
    if add_cost is not None:  # (601.2h: with the rest of the total cost)
        if add_cost.life:
            from app.rules import replace as _replace_life  # (wave 28B: 119.4)
            _replace_life.lose_life(plan, [(plan.actor, add_cost.life)])  # 119.4
            record.life += add_cost.life
        if add_cost.life_x and a.x_value:  # -- X sized by a count (wave 4K) -- "pay X life" (119.4)
            from app.rules import replace as _replace_life  # (wave 28B: 119.4)
            _replace_life.lose_life(plan, [(plan.actor, a.x_value)])
            record.life += a.x_value
        waterbend102.record(plan,a,add_cost,add_objects,record)
        cost_payment.pay(plan, add_cost, card, add_objects, record)  # sacrifice, discard, exile …
        plan.reserved_life = 0  # (wave 29C)
    plan.do({"type": "set_stack_info", "card_id": card.id,
             "tags": ([] if paid else [f"Cast for its {kind} cost" if alt is not None else "Cast without paying its mana cost"])
             + (["Kicked" if record.kicked == 1 else f"Kicked ×{record.kicked}"] if a.kicker else []) + (["Bargained"] if bargained else [])})
    record.x = a.x_value
    record_payment(plan, card.id, record)
    if a.targets:
        plan.target_arrows(card.id, a.targets)
    if ch.is_creature and was_suspended:
        r.suspend_haste.append(card.id)  # 702.62e: it gains haste
    if "rebound" in ch.keywords and from_hand:
        r.rebound_cast.append(plan.oid(card))
    emit(plan.state, "spell_cast", object_id=plan.oid(card), card=card.id, player=plan.actor,
         amount=r.spells_this_turn(plan.actor, plan.state.turn.number) + 1)  # (the Nth spell this turn)
    delayed.spell_cast(plan, from_oid)  # (-- as long as (wave 37A) --)
    from app.rules import (
        wave110m_cards as _w110m,  # -- (wave 110M) -- "until a player casts a creature spell" is over
    )

    _w110m.spell_cast(plan, card)
    extra = 0 if plan.manual(card) else _granted_cascade(plan, card, ch, record.cast_from)
    if extra or ("cascade" in ch.keywords and not plan.manual(card)):
        _cascade_triggers(plan, card, ch, extra)
    if not plan.manual(card):
        _storm_triggers(plan, card, ch, record.cast_from)
        _ripple_triggers(plan, card, ch, record.cast_from)
        _conspire_trigger(plan, card, ch, record)  # (wave 41D: casualty 702.153a, conspire 702.78a)
        _demonstrate_trigger(plan, card, ch, record.cast_from)  # (wave 43D)
    if "replicate" in ch.keywords and not plan.manual(card):  # (wave 15E)
        _replicate_trigger(plan, card, ch, a.kicker)
    if definition is not None and picked and not slot_specs and any(definition["modes"][i].get("groups") for i in picked):
        r.stack[card.id] = StackEntry(kind="spell", controller=plan.actor, source_card=card.id, source_object=plan.oid(card),
                                      name=ch.name, effects=modal_effects(definition, picked, True), x=effect_x, modes=picked,
                                      **picked_targets.entry(None), kicked=record.kicked, kicked_mask=record.kicked_mask)
    elif definition is not None and picked:
        effects_in_order = modal_effects(definition, picked, False)
        r.stack[card.id] = StackEntry(kind="spell", controller=plan.actor, source_card=card.id, source_object=plan.oid(card),
                                      name=ch.name, effects=effects_in_order, targets=chosen, target_spec=None,
                                      x=effect_x, modes=picked, slots=slots, slot_specs=slot_specs, kicked=record.kicked, kicked_mask=record.kicked_mask)
    elif definition is not None:
        r.stack[card.id] = StackEntry(kind="spell", controller=plan.actor, source_card=card.id, source_object=plan.oid(card),
                                      name=ch.name, effects=list(definition["effects"]), x=effect_x,
                                      **picked_targets.entry(definition), kicked=record.kicked, kicked_mask=record.kicked_mask)
    r.aura_targets = {k: v for k, v in r.aura_targets.items() if k != card.id and plan.state.cards.get(k) is not None
                      and plan.state.cards[k].zone == STACK}  # (review (wave 18D): never a target this card had as an earlier spell)
    if aura is not None and chosen:
        r.aura_targets[card.id] = chosen[0]  # 303.4a: the Aura spell's (or mutating spell's, 702.140a) target
    if chosen:
        from app.rules.triggers import targeted

        targeted(plan, card.id, plan.actor, chosen)
    turn = plan.state.turn.number
    r.spells_cast[plan.actor] = TurnCount(turn=turn, count=r.spells_this_turn(plan.actor, turn) + 1)
    history.note_cast(plan, card)  # -- this-turn history (wave 4D) --
    permissions.free_cast_done(plan, card.id, cast=True)  # -- refused look/cast-free (wave 3R5) -- 608.2g: resolution goes on
# -- end cast without paying (wave 3C) --


def resume_crew(plan: Plan, d: Any, chosen: list[str]) -> None:
    intent = A.parse_action(d.resume["intent"])
    intent.crew = list(chosen)  # type: ignore[union-attr]
    plan.rules.priority = d.player
    activate_ability(plan, intent)  # type: ignore[arg-type]


def activate_ability(plan: Plan, a: A.ActivateAbility) -> None:
    if paying_now(plan):  # tapping mana while paying: only mana abilities
        _mana_while_paying(plan, a)
        return
    if a.convoke or a.improvise or a.delve:  # only while paying for a spell with that keyword
        kind = "convoke" if a.convoke else "improvise" if a.improvise else "delve"
        raise ActionError(f"{kind.capitalize()} can only pay for the spell you're casting, while you pay for it")
    require_no_decision(plan)
    require_priority(plan)
    card = plan.state.cards.get(a.card_id)
    if card is None:
        raise ActionError("That card isn't here any more")
    if card.zone == zone_key(plan.actor, "hand"):
        ch = plan.ch(card)
        ability = next((ab for ab in ch.abilities if ab.index == a.ability), None)
        if suspend_info(ch, a.ability) is None:  # -- cast limits (wave 5E) -- (suspend is a special action, 116.2f)
            _activation_limit(plan, card, ch)
        if ability is not None and ability.kind == "activated" and ability_cost(ch, ability).from_hand:
            activate_to_stack(plan, card, ch, ability, a)  # -- ability words (wave 4F) -- channel (113.6m)
            return
        if ability is not None and ability.kind == "mana":  # -- mana riders (wave 5A) -- Simian Spirit Guide (605.3a)
            from app.rules import mana_riders

            mana_riders.activate_from_hand(plan, card, ch, ability)
            plan.rules.passed = []
            return
        found = suspend_info(ch, a.ability)
        if found is not None:
            suspend(plan, card, ch, a, *found)
        elif (plot_cost := keyword_cost(ch, "plot", PLOT, a.ability)) is not None and not plan.manual(card):
            plot(plan, card, ch, a, plot_cost)
        elif (keyword_cost(ch, "foretell", FORETELL, a.ability) is not None or (ability is not None and ability.granted_mana_cost is not None and ability.granted_mana_cost.keyword == "foretell")) and not plan.manual(card):
            foretell(plan, card, ch, a)
        elif (ninja := ninjutsu.cost_of(ch, a.ability)) is not None and not plan.manual(card):
            on_stack = len(plan.state.zones.get(STACK, []))
            activate_to_stack(plan, card, ch, ninjutsu.ability(ch, a.ability, ninja), a, definition=ninjutsu.DEFINITION, keep_revealed=True)
            if len(plan.state.zones.get(STACK, [])) > on_stack and card.zone == zone_key(plan.actor, "hand") \
                    and ALL not in card.revealed_to:  # -- keywords
                # (wave 15E) -- 702.49b: revealed until the ability leaves the stack (ninjutsu.enter hides it again)
                plan.do({"type": "reveal", "card_ids": [card.id]}, actor=plan.actor)
        else:
            cycle(plan, card, ch, a)
        return
    if card.zone == zone_key(plan.actor, "graveyard") and card.owner == plan.actor:
        ch = plan.ch(card)
        from app.rules import unearth_costs

        unearth_cost = unearth_costs.of(ch, a.ability)
        ability = next((ab for ab in ch.abilities if ab.index == a.ability), None)
        if unearth_cost is None and ability is not None and ability.kind == 'mana':
            parsed_gy = M.parse_mana_ability(ability.text, commander_identity(plan.state, plan.actor, plan.info), card_name=ch.name)
            if parsed_gy is not None and parsed_gy.from_graveyard:
                _activation_limit(plan, card, ch, mana=True)
                problem = ability_problem(plan.state, plan.actor, card, ch, ability,
                                          parse_ability_cost(parsed_gy.extra_cost, card_name=ch.name), plan=plan)
                if problem:
                    raise ActionError(problem)
                _activate_choosing(plan, card, ch, parsed_gy, a)
                return
        if unearth_cost is None and ability is not None and ability.kind == "activated" and \
                ability_cost(ch, ability).from_graveyard:  # 113.6m: "Exile this card from your graveyard: …"
            _activation_limit(plan, card, ch)  # -- cast limits (wave 5E) --
            activate_to_stack(plan, card, ch, ability, a)
            return
        if unearth_cost is None and (gk := graveyard_keywords.ability(ch, a.ability)) is not None and not plan.manual(card):
            _activation_limit(plan, card, ch)  # -- keywords (wave 15E) -- embalm / eternalize: activated from the graveyard
            activate_to_stack(plan, card, ch, gk, a, definition=scripts.define(gk, ch))
            return
        if unearth_cost is None:
            raise ActionError("That card has no ability to use from your graveyard")
        _activation_limit(plan, card, ch)  # -- cast limits (wave 5E) --
        unearth(plan, card, ch, a, unearth_cost)
        return
    if card.zone == zone_key(plan.actor, "exile") and card.owner == plan.actor:  # -- activated other (wave 42C) -- 113.6m: "… from your graveyard or from exile"
        ch = plan.ch(card)
        ability = next((ab for ab in ch.abilities if ab.index == a.ability), None)
        if ability is not None and ability.kind == "activated" and ability_cost(ch, ability).exile_too:
            _activation_limit(plan, card, ch)
            activate_to_stack(plan, card, ch, ability, a)
            return
        raise ActionError("That card has no ability to use from exile")
    if card.zone == zone_key(plan.actor, "companion") and card.owner == plan.actor:  # -- companion (wave 38D) -- 116.2g
        companion_action(plan, card, plan.ch(card), a)
        return
    if card.zone == zone_key(plan.actor, "command") and card.owner == plan.actor:  # -- activated from hand / command zone (wave 27D)
        ch = plan.ch(card)
        ability = next((ab for ab in ch.abilities if ab.index == a.ability), None)
        if ability is not None and ability.kind == "activated" and ability_cost(ch, ability).command_only:  # 113.6m
            _activation_limit(plan, card, ch)
            activate_to_stack(plan, card, ch, ability, a)
            return
        if (ninja := ninjutsu.cost_of(ch, a.ability, command=True)) is not None and not plan.manual(card):  # -- commander ninjutsu (wave 50J) -- 702.49d
            activate_to_stack(plan, card, ch, ninjutsu.ability(ch, a.ability, ninja), a, definition=ninjutsu.DEFINITION)
            return
        raise ActionError("That card has no ability to use from the command zone")
    ch = plan.ch(card)
    # -- activation wordings (wave 7B) -- 602.2: "Any player may activate this ability."
    ab = next((x for x in ch.abilities if x.index == a.ability), None)
    if not card.zone.endswith(":battlefield") or not (
            actor_allowed(ab, ability_cost(ch, ab, state=plan.state, card=card, info=plan.info), card.controller, plan.actor, owner=card.owner)
            if ab is not None else card.controller == plan.actor):
        if ab is not None and opponents_only(ab) and card.controller == plan.actor:
            raise ActionError("Only your opponents may activate this ability")
        raise ActionError("You can only activate abilities of permanents you control")
    if "cant_activate" in ch.imposed:  # an Aura: "its activated abilities can't be activated" (crew, equip too)
        raise ActionError(f"{ch.name}’s activated abilities can't be activated")
    ability = _find_ability(ch, a.ability)
    if "cant_activate_nonmana" in ch.imposed and ability.kind != "mana":  # -- attached events (wave 16F) -- Faith's Fetters (605.1a)
        raise ActionError(f"{ch.name}’s activated abilities can't be activated unless they're mana abilities")
    if "cant_activate_tap" in ch.imposed and ab is not None and ability_cost(ch, ab, state=plan.state, card=card, info=plan.info).tap:  # -- attached (wave 100F) --
        raise ActionError(f"{ch.name}’s activated abilities with {{T}} in their costs can't be activated")
    _activation_limit(plan, card, ch, mana=ability.kind == "mana", loyalty=ability.kind == "loyalty")  # -- cast limits (wave 5E) --
    n = crew_power(ch, a.ability) if not plan.manual(card) else None
    if n is not None:
        crew(plan, card, ch, a, n)
        return
    from app.rules import crew_saddle  # -- crew & saddle (wave 23D) --

    n = crew_saddle.saddle_power(ch, a.ability) if not plan.manual(card) else None
    if n is not None:
        crew(plan, card, ch, a, n, "saddle")
        return
    equip = attachments.equip_cost(ch, a.ability) if not plan.manual(card) else None
    if equip is not None:
        equip_ability(plan, card, ch, a, equip)
        return
    fortify = attachments.fortify_cost(ch, a.ability) if not plan.manual(card) else None  # -- (wave 110M) -- 702.67a
    if fortify is not None:
        if "Fortification" not in ch.subtypes or ch.is_creature:
            raise ActionError(f"{ch.name} can't fortify a land" + (" while it's a creature" if ch.is_creature else ""))  # 301.6
        ability = AbilityText(index=a.ability, kind="activated", cost=fortify, text=f"{fortify}: Attach {ch.name} to target land you control. Activate only as a sorcery.")
        activate_to_stack(plan, card, ch, ability, a, definition={"kind": "activated", "effects": [{"do": "attach_self"}],
                                                                   "target": {"what": 'sel:{"controller":"you","types":["Land"]}'}}, exclude_targets=(card.id,))
        return
    if ability.kind in ("activated", "loyalty"):
        activate_to_stack(plan, card, ch, ability, a)
        return
    if ability.kind != "mana":
        raise ActionError(f"“{ability.text}” isn't an ability you activate")
    parsed = dict(mana_abilities(plan.state, card, plan.info)).get(a.ability)
    if parsed is None:
        if M.parse_mana_ability(ability.text, commander_identity(plan.state, card.controller, plan.info), card_name=ch.name) is not None:
            raise ActionError(f"{ch.name} can't use “{ability.text}” right now")
        raise ActionError(f"Fyodor can't carry out “{ability.text}” yet. Use the table tools.")
    if parsed.tap and not can_use_tap_abilities(plan.state, card, ch, plan.info):
        raise ActionError(f"{ch.name} is tapped" if card.tapped else f"{ch.name} has summoning sickness")
    if parsed.reveal_hand is not None:
        from app.rules import reveal_mana

        reveal_mana.start(plan, card, parsed, a.ability)
        return
    if parsed.chooses:  # -- refused copy/mana (wave 3R3) --
        _activate_choosing(plan, card, ch, parsed, a)
        return
    options = parsed.options
    if len(options) == 1:
        _manual_produce(plan, card, parsed, options[0], a.ability, option_index=0)
    elif a.mana_choice is not None:
        selected = next(((i, o) for i, o in enumerate(options) if o and all(symbol == a.mana_choice for symbol in o)), None)
        if selected is None:
            raise ActionError(f"{ch.name} can't add {{{a.mana_choice}}}")
        _manual_produce(plan, card, parsed, selected[1], a.ability, option_index=selected[0])
    else:
        decide(plan, player=plan.actor, kind="choose_one", prompt=f"Which mana should {ch.name} add?",
               options=[DecisionOption(id=str(i), label=M.symbols(_count(o))) for i, o in enumerate(options)],
               resume={"step": "mana_ability", "card": card.id, "ability": a.ability}, source=card)
        return
    plan.rules.passed = []


def _activation_limit(plan: Plan, card: CardInstance, ch: Characteristics, *, mana: bool = False, loyalty: bool = False) -> None:
    """-- cast limits (wave 5E) -- 602.5: an ability a rule or effect prohibits can't begin to be activated."""
    from app.rules import cast_limits

    why = cast_limits.activation_problem(plan.state, plan.actor, card, ch, plan.info, mana=mana, loyalty=loyalty)
    if why:
        raise ActionError(why)


def _commit_helper(plan: Plan, card: CardInstance | None, kind: P.Kind) -> None:
    """Click a creature (convoke), an artifact (improvise) or a graveyard card (delve) while paying
    for a spell with that keyword: it's committed to pay one symbol of the total cost — or, if it
    already was, taken back. Nothing is tapped or exiled, and no mana is added (702.51a,
    702.126a, 702.66a: "rather than pay that mana"); that happens when the whole cost is paid."""
    d = plan.rules.decision
    assert d is not None and d.resume is not None
    resume = d.resume
    spell, spell_card = _prompt_spell(plan, resume)
    if spell is None or kind not in helper_kinds(spell, plan.state, d.player, spell_card, plan.info):  # (wave 5E: granted)
        raise ActionError(f"Only a spell with {kind} can be paid for that way")
    if card is None:
        raise ActionError("That card isn't here any more")
    intent = dict(resume.get("intent") or {})
    contributions = list(intent.get("contributions") or [])
    if any(c["card"] == card.id for c in contributions):
        contributions = [c for c in contributions if c["card"] != card.id]
    else:
        contributions.append({"kind": kind, "card": card.id})
        helpers = helpers_for(plan.state, d.player, plan.info, spell, spell_card, contributions)
        if P.assign(M.parse_cost(resume["cost"]), helpers) is None:
            what = "generic mana" if kind != "convoke" else "generic mana or mana of its color"
            raise ActionError(f"{card.name or 'That card'} can't pay for any of what's left of {resume['cost']}: "
                              f"{kind} pays only {what} (never {{C}})")
    d.resume = {**resume, "intent": {**intent, "contributions": contributions}}
    after_tapping(plan)


def _activate_choosing_nested(plan: Plan, card: CardInstance, ch: Characteristics, ability: AbilityText, parsed: M.ManaAbility,
                              a: A.ActivateAbility) -> None:
    """-- nested payment choices (wave 28D) -- a mana ability whose cost chooses objects ("Sacrifice a creature") activated while a
    payment prompt is open. 605.3a: a mana ability may be activated while paying a cost; 601.2g-h: its own costs are chosen as it's
    paid, so the choice (and a color to add, 605.3a) is nested in the payment prompt, which is set aside (``payment_outer``) and comes
    back once the ability is done (``resume_outer``) or its choice is cancelled. "Activate only as an instant" (Lion's Eye Diamond)
    needs priority, which a player paying a cost doesn't have (602.5d, 304.5): refused."""
    if any(t in ability.text for t in ("Activate only as an instant", "Activate only as a sorcery")):
        raise ActionError(f"{ch.name} can only be activated when you have priority (not while paying a cost)")
    input_cost = mana_activation_cost(plan.state, card, ch, parsed, plan.info, x=a.x_value)
    if not input_cost.is_free and not pool_covers(plan.state, card.controller, input_cost,
                                                purpose=Purpose(ability_of=ch, player=card.controller,
                                                                selected_cost_has_x='{X}' in (parsed.extra_cost or '')), info=plan.info):
        raise ActionError(f"Add {input_cost.text()} to your mana pool first to activate {ch.name}")
    r = plan.rules
    outer = r.decision
    assert outer is not None
    r.payment_outer, r.decision = outer, None
    r.priority = plan.actor
    try:
        _activate_choosing(plan, card, ch, parsed, a)
    finally:
        r.priority = None
    resume_outer(plan)


def unnest(plan: Plan) -> None:
    """-- review 28D -- the nested choice is abandoned (its player left the game, or it no longer matches the table): the payment
    prompt it was nested in is the pending decision again, to be settled like any other (800.4a; nothing of the nested cost was paid
    while it was being chosen)."""
    r = plan.rules
    if r.payment_outer is not None:
        r.decision, r.payment_outer = r.payment_outer, None


def resume_outer(plan: Plan) -> None:
    """The payment prompt a nested mana ability's choice was made in comes back (once no further choice is pending): the mana added
    may cover it now."""
    r = plan.rules
    if r.payment_outer is None or r.decision is not None:
        return
    r.decision, r.payment_outer = r.payment_outer, None
    r.priority = None
    r.passed = []
    plan.hold = None
    after_tapping(plan)


def _mana_while_paying(plan: Plan, a: A.ActivateAbility) -> None:
    pending = plan.rules.decision
    after = (pending.resume or {}).get('paid_then') if pending is not None else None
    if after and after.get('stage') == 'activation_announced':
        plan.reserved_life = max(plan.reserved_life, int(after.get('reserved_life', 0)))
    card = plan.state.cards.get(a.card_id)
    if a.convoke or a.improvise or a.delve:
        _commit_helper(plan, card, "convoke" if a.convoke else "improvise" if a.improvise else "delve")
        return
    if card is not None and card.zone == zone_key(plan.actor, "hand"):  # -- mana riders (wave 5A) -- a Spirit Guide
        from app.rules import mana_riders

        hand_ch = plan.ch(card)
        hand_ability = _find_ability(hand_ch, a.ability)
        if hand_ability.kind == "mana":
            mana_riders.activate_from_hand(plan, card, hand_ch, hand_ability)
            after_tapping(plan)
            return
    if card is not None and card.owner == plan.actor and card.zone == zone_key(plan.actor, 'graveyard'):
        grave_ch = plan.ch(card)
        grave_ability = _find_ability(grave_ch, a.ability)
        grave_mana = M.parse_mana_ability(grave_ability.text, commander_identity(plan.state, plan.actor, plan.info), card_name=grave_ch.name)
        if grave_ability.kind == 'mana' and grave_mana is not None and grave_mana.from_graveyard:
            _activation_limit(plan, card, grave_ch, mana=True)
            _activate_choosing_nested(plan, card, grave_ch, grave_ability, grave_mana, a)
            return
    if card is None or not card.zone.endswith(":battlefield"):
        raise ActionError("Tap mana sources you control")
    d = plan.rules.decision
    if d is not None and any(c["card"] == card.id for c in ((d.resume or {}).get("intent") or {}).get("contributions") or []):
        raise ActionError(f"{card.name or 'That card'} is already paying part of the cost (click it again to take it back)")
    ch = plan.ch(card)
    ability = _find_ability(ch, a.ability)
    if not actor_allowed(ability, ability_cost(ch, ability, state=plan.state, card=card, info=plan.info),
                         card.controller, plan.actor, owner=card.owner):
        raise ActionError("You cannot activate that mana ability")
    if "Activate only as an instant" in ability.text:
        raise ActionError(f"{ch.name} can only be activated when you have priority (not while paying a cost)")
    parsed = dict(mana_abilities(plan.state, card, plan.info)).get(a.ability) if ability.kind == "mana" else None
    if parsed is None:
        raise ActionError("While paying you can only tap for mana")
    if parsed.tap and not can_use_tap_abilities(plan.state, card, ch, plan.info):
        raise ActionError(f"{ch.name} is tapped" if card.tapped else f"{ch.name} has summoning sickness")
    if parsed.reveal_hand is not None:
        from app.rules import reveal_mana

        reveal_mana.start(plan, card, parsed, a.ability)
        return
    if parsed.chooses:  # -- nested payment choices (wave 28D) -- 605.3a, 601.2g-h: the costs it chooses are paid in a prompt nested in this one
        _activate_choosing_nested(plan, card, ch, ability, parsed, a)
        return
    options = parsed.options
    chosen_index = next((i for i, o in enumerate(options) if o and all(symbol == a.mana_choice for symbol in o)), None) if a.mana_choice else None
    selected_index = chosen_index if chosen_index is not None else (0 if len(options) == 1 else _best_option_index(plan, options))
    selected = options[selected_index]
    outer = plan.rules.decision
    assert outer is not None
    plan.rules.payment_outer, plan.rules.decision = outer, None
    _manual_produce(plan, card, parsed, selected, a.ability, nested=True, option_index=selected_index)


# -- other activated abilities (they use the stack) -----------------------------------------
SPEND_CHOSEN = "Spend only mana of the chosen color to activate this ability."


def ability_mana_cost(cost: AbilityCost) -> M.ManaCost:
    return replace(M.parse_cost(cost.mana), allocation=cost.mana_allocation)


def _variable_ability_matching(state: GameState, card: CardInstance, ch: Characteristics,
                               ability: AbilityText, info: CardInfo, cost: M.ManaCost) -> M.ManaCost:
    from app.rules import cast_limits, mana_allocation_masks

    mode = cast_limits.ability_spend_mode(state, card.controller, card, ch, info) or (
        'color' if state.rules is not None and ability.borrowed_color == state.rules.object_id(card.id) else None)
    if mode:
        cost = M.spend_as(cost, mode)
    if SPEND_CHOSEN in ability.text:
        color = _chosen_color(card)
        if color is not None and not (cost.hybrid or cost.phyrexian or cost.x) and all(c == color for c in cost.colored):
            rows = mana_allocation_masks.assign_generic_encoding(cost, (color,) * cost.generic)
            cost = replace(M.ManaCost(0, (*cost.colored, *(color,) * cost.generic)), allocation=rows)
    return cost


def ability_cost(ch: Characteristics, ability: AbilityText, *, state: GameState | None = None,
                 card: CardInstance | None = None, info: CardInfo | None = None, target: str | None = None,
                 targets: tuple[str, ...] | None = None, actor: str | None = None) -> AbilityCost:
    from app.rules import activation_alternatives, hybrid_power_up71

    if (branches71 := hybrid_power_up71.alternatives(state, card, ch, ability)) is not None:
        return AbilityCost(either=tuple(ability_cost(ch, branch, state=state, card=card, info=info, target=target, targets=targets, actor=actor)
                                       for branch in branches71))
    if (sides := activation_alternatives.sides(ability.cost or "")) is not None:
        return AbilityCost(either=tuple(ability_cost(ch, activation_alternatives.with_cost(ability, side),
                           state=state, card=card, info=info, target=target, targets=targets, actor=actor) for side in sides))
    cost = parse_ability_cost(ability.cost or "", card_name=ch.name, loyalty=ability.kind == "loyalty")
    if state is not None and card is not None and any(c.amount_rule == "opponents" for c in cost.components):
        from app.rules.plan import live_players

        count = sum(pid != card.controller for pid in live_players(state))
        cost = replace(cost, components=tuple(replace(c, amount=count, amount_rule=None) if c.amount_rule == "opponents" else c
                                              for c in cost.components))
    if any(c.kind == costs.EXILE_TO_GY for c in cost.components):
        from app.rules import abilities_of, selectors

        scope = abilities_of.link_scope(ability)
        if scope is not None:
            def scoped(component: Any) -> Any:
                if component.kind != costs.EXILE_TO_GY or not component.selector:
                    return component
                sel = selectors.from_key(component.selector)
                return replace(component, selector=selectors.replace(sel, extras=tuple(
                    'source_linked:' + scope if x == 'source_linked' else x for x in sel.extras)).key())
            cost = replace(cost, components=tuple(scoped(c) for c in cost.components))
    if state is not None and card is not None and info is not None and ability.kind in ("activated", "loyalty"):
        # -- costs (wave 3$) -- "Activated abilities of creatures you control cost {2} less to activate" (601.2f)
        # (wave 4I: a cost with no mana in it can be increased too: "{T}: …" taxed {2} is "{2}, {T}: …")
        # -- cost changers (wave 4I) -- and the ability's own "This ability costs {1} less to activate for each …" (602.2b)
        from app.rules import cost_changes  # (a leaf over this module)

        if ability.text.startswith("Power-up — ") and not ability.power_up_prepared:  # 702.193a
            from app.rules import power_up

            cost = replace(cost, mana=power_up.reduced(state, card, ch, cost.mana) or "")
        own = cost_changes.ability_delta(state, card.controller, card, ch, ability.text, info, target=target, targets=targets) \
            if "This ability costs " in ability.text else 0
        reduced = permissions.ability_mana(state, actor or card.controller, card, ch, cost.mana, info, own, ability.text, target, targets=targets)
        if reduced != cost.mana:
            cost = replace(cost, mana=reduced)
        from app.rules import (
            cast_limits,  # -- casting costs (wave 22F) -- 609.4b: "spend mana as though it were mana of any color" on abilities
        )

        variable = bool(ability_mana_cost(cost).x)
        if cost.mana and not variable and (mode := (cast_limits.ability_spend_mode(state, card.controller, card, ch, info) or
                                  ("color" if state.rules is not None and getattr(ability, "borrowed_color", None) == state.rules.object_id(card.id) else None))):
            transformed = M.spend_as(ability_mana_cost(cost), mode)
            cost = replace(cost, mana=transformed.text(), mana_allocation=transformed.allocation)
        if SPEND_CHOSEN in ability.text and cost.mana and not variable:  # -- most-played cards (wave 51F) -- "Spend only mana of the chosen color to activate this ability" (Throne of Eldraine, 106.6)
            # is every generic mana of the cost as colored mana of that color: only mana of it pays (after the any-color mode above, which cannot undo it)
            # ponytail: K'rrik's "{B} … pay 2 life" would read these as {B} symbols when black is chosen
            m, color = ability_mana_cost(cost), _chosen_color(card)
            if color is None or m.hybrid or m.phyrexian or m.x or any(c != color for c in m.colored):
                cost = replace(cost, unsupported=(*cost.unsupported, "mana of the chosen color"))
            else:
                from app.rules import mana_allocation_masks

                rows = mana_allocation_masks.assign_generic_encoding(m, (color,) * m.generic)
                cost = replace(cost, mana=M.ManaCost(0, (*m.colored, *(color,) * m.generic)).text(),
                               mana_allocation=rows)
    # -- reanimation (wave 3R) -- 113.6m: "{1}{B}: Return this card from your graveyard to the battlefield" moves the
    # card out of the graveyard, so the ability works only there
    # (review 40: anywhere in the effect, "Exile five target cards from an opponent's graveyard. Return this card from your graveyard to your hand." on
    # Lochmere Serpent; ponytail: no card's earlier part puts it into the graveyard first, the 113.6m exception)
    if ability.kind == "activated" and ":" in ability.text and (_GRAVEYARD_SELF.search(ability.text.split(":", 1)[1].strip().replace(ch.name, "~"))
                                                                 or "Activate only if this card is in your graveyard" in ability.text):
        cost = replace(cost, graveyard_only=True,  # (review 20E: Glory's "Activate only if this card is in your graveyard.", 113.6m)
                       exile_too=_GRAVEYARD_OR_EXILE.match(ability.text.split(":", 1)[1].strip().replace(ch.name, "~")) is not None)  # (wave 42C)
    if ability.kind == "activated" and "Activate only if this card is suspended." in ability.text:
        cost = replace(cost, graveyard_only=True, exile_too=True)
    # -- activated from hand / command zone (wave 27D) -- 113.6m: "Put this card from your hand onto the battlefield" / "Put ~ onto the
    # battlefield from the command zone" moves the card out of that zone, so the ability works only there
    if ability.kind == "activated" and ":" in ability.text:
        body = scripts.self_text(ability.text.split(":", 1)[1].strip(), ch.name).lower()
        if "put this card from your hand onto the battlefield" in body or "put ~ from your hand onto the battlefield" in body:
            cost = replace(cost, hand_only=True)
        elif "put ~ onto the battlefield from the command zone" in body:
            cost = replace(cost, command_only=True)
    return cost


# (-- reanimation (wave 37B) -- "Return this card and target land card from your graveyard to the battlefield tapped" (Sandman): this card too)
# -- activated other (wave 42C) -- 113.6m: "Return this card from your graveyard or from exile to the battlefield tapped." (Mister Immortal) moves the card out of
# either zone, so it works in either
_GRAVEYARD_OR_EXILE = re.compile(r"(?:return|put) (?:this card|~) from your graveyard or from exile\b", re.I)
_GRAVEYARD_SELF = re.compile(r"(?:return|put) (?:this card|this creature|this artifact|this land|~)(?: and [^:.]*?)? from your graveyard\b", re.I)


def _own_text(text: str, name: str) -> str:
    """-- activation wordings (wave 7B) -- the ability with its own name / "this creature" as ~ in the effect and restriction
    (what scripts reads), the cost and any "Exhaust — " / "Boast — " prefix left as written."""
    head, colon, body = text.partition(":")
    return head + colon + scripts.self_text(body, name) if colon else text


def ability_problem(state: GameState, player: str, card: CardInstance, ch: Characteristics, ability: AbilityText,
                    cost: AbilityCost, *, check_priority: bool = True, x: int = 0,
                    info: CardInfo | None = None, plan: Plan | None = None) -> str | None:
    """Why ``player`` can't activate this ability now (None if they can, costs included when
    ``info`` is given; "Activate only if …" conditions need ``plan`` or ``info``)."""
    if cost.either:
        reasons = [ability_problem(state, player, card, ch, ability, side, check_priority=check_priority,
                                   x=x, info=info, plan=plan) for side in cost.either]
        return None if any(reason is None for reason in reasons) else reasons[0]
    r = state.rules
    if r is None:
        return "Rules automation is off"
    from app.rules import defined_activation_x

    fixed_x = defined_activation_x.spec(ability, ch.name)
    if fixed_x is not None:
        view = plan
        if view is None and info is not None:
            view = Plan.view(state, player, info)
        if view is not None:
            x = defined_activation_x.evaluate(view, card, fixed_x)
    if "Activate only if this card is suspended." in ability.text:
        from app.rules import suspend_grants

        suspended_view = plan if plan is not None else Plan.view(state, player, info) if info is not None else None
        if suspended_view is None or not suspend_grants.is_suspended(suspended_view, card):
            return "That ability can only be activated while this card is suspended"
    if cost.from_hand:  # -- ability words (wave 4F) -- 113.6m: "Discard this card" (channel) works only from the hand
        if card.zone != zone_key(player, "hand") or card.owner != player:
            return "That ability can only be activated from your hand"
    elif cost.command_only:  # -- activated from hand / command zone (wave 27D) -- 113.6m
        if card.zone != zone_key(player, "command") or card.owner != player:
            return "That ability can only be activated from the command zone"
    elif cost.from_graveyard:  # 113.6m: its cost moves it out of your graveyard, so it works only there
        if card.zone not in ((zone_key(player, "graveyard"), zone_key(player, "exile")) if cost.exile_too else (zone_key(player, "graveyard"),)) \
                or card.owner != player:  # (-- activated other (wave 42C) -- or from exile, where the text says so)
            return "That ability can only be activated from your graveyard" + (" or from exile" if cost.exile_too else "")
    elif ninjutsu.is_ninjutsu(ability.text):  # -- keywords (wave 15E) -- 702.49a: from the hand, once blockers are declared
        why = ninjutsu.problem(state, player, card)
        if why:
            return why
    elif not card.zone.endswith(":battlefield") or not actor_allowed(ability, cost, card.controller, player, owner=card.owner):  # (wave 7B)
        if opponents_only(ability) and card.controller == player:
            return "Only your opponents may activate this ability"
        return "You can only activate abilities of permanents you control"
    if cost.unsupported:
        return f"Pay “{', '.join(cost.unsupported)}” by hand with the table tools"
    if "cant_activate" in ch.imposed or ("cant_activate_nonmana" in ch.imposed and ability.kind != "mana") or ("cant_activate_tap" in ch.imposed and cost.tap):  # (wave 100F: {T})
        return f"{ch.name}’s activated abilities can't be activated"
    # -- cast limits (wave 5E) -- (602.5)
    from app.rules import cast_limits

    limited = cast_limits.activation_problem(state, player, card, ch, info, loyalty=ability.kind == "loyalty")
    if limited:
        return limited
    if check_priority and (r.priority != player or r.decision is not None):
        return "You don't have priority"
    if ability.kind == "loyalty":  # 606.3: as a sorcery, once per permanent each turn
        rule_info = info or (plan.info if plan is not None else None)  # (wave 19A: the statics of other permanents are read from it)
        if (state.turn.active_player != player or state.turn.phase not in MAIN_PHASES or state.zones.get(STACK)) \
                and not cast_limits.loyalty_rule(state, card, rule_info, "instant"):  # (Teferi, Master of Time)
            return "That can only be activated in your main phase while the stack is empty"
        oid = r.object_id(card.id)
        if r.loyalty_used.get(oid) == state.turn.number and (r.loyalty_second.get(oid) == state.turn.number
                                                             or not cast_limits.loyalty_rule(state, card, rule_info, "twice")):  # (Oath of Teferi)
            return f"{ch.name} has already used a loyalty ability this turn"
        from app.rules import static_perm100d  # -- static permanents (wave 100D) -- Carth the Lion

        loyal = None if cost.loyalty is None else cost.loyalty + static_perm100d.loyalty_plus(state, rule_info, player)
        if loyal is not None and loyal < 0 and card.counters.get("loyalty", 0) < -loyal:
            return f"{ch.name} doesn't have enough loyalty"
    # -- activation restrictions (602.5; app/rules/restrictions.py): "Activate only as a sorcery",
    # "… only once each turn" (per object, 602.5b / 400.7), "… only during your turn", "… only if …"
    limits = restrictions.parse(_own_text(ability.text, ch.name)) or []  # (a wording it doesn't read: the ability is manual anyway)
    if limits and attachments.is_equip_text(ability.text) and cast_limits.loyalty_rule(state, card, info or (plan.info if plan is not None else None), "equip_instant"):
        limits = [x for x in limits if x["kind"] != "sorcery"]  # -- most-played cards III (wave 46C) -- 702.6a: "You may activate equip abilities any time you could cast an instant."
    if limits:
        view = plan or (Plan.view(state, player, info) if info is not None else None)
        why = restrictions.problem(state, player, card, ability.index, limits, view, ch.name)
        if why:
            return why
    if cost.tap and not can_use_tap_abilities(state, card, ch, info or (plan.info if plan is not None else None)):
        return f"{ch.name} is tapped" if card.tapped else f"{ch.name} has summoning sickness"
    for kind, n in cost.remove_counters:
        if n and (info is not None or plan is not None):
            from app.rules import prohibitions

            if plan is not None:
                view = plan
            else:
                assert info is not None
                view = Plan.view(state, player, info)
            if (why := prohibitions.cant_remove_counters(view, card.id, kind)):
                return f"{why}: {kind} counters can't be removed from {ch.name}"
        if card.counters.get(kind, 0) < n:
            return f"{ch.name} doesn't have {n} {kind} counter{'s' if n != 1 else ''}"
    if cost.life and state.players[player].life < cost.life:
        return f"You don't have {cost.life} life to pay"
    from app.rules import life_lock  # -- can't lose life (wave 29D) -- 119.8, 614.17b

    if (why := life_lock.pay_problem(state, info, player, cost.life)) is not None:
        return why
    if info is not None and cost.components:  # 118.3: untap, sacrifice, discard, exile … (cost_payment)
        found = cost_payment.problem(Plan.view(state, player, info), cost, card, player)
        if found:
            return found
    if info is not None and cost.mana:
        mana = ability_mana_cost(cost).with_x(x)
        if fixed_x is not None and ability_mana_cost(cost).x:
            from app.rules import cost_changes

            own = cost_changes.ability_delta(state, player, card, ch, ability.text, info) if "This ability costs " in ability.text else 0
            mana = M.parse_cost(permissions.ability_mana(state, player, card, ch, mana.text(), info, own, ability.text))
        if ability_mana_cost(cost).x:
            mana = _variable_ability_matching(state, card, ch, ability, info, mana)
        for _, comp in cost.choices:  # -- activated sweep (wave 17B) -- waterbend: the untapped artifacts and creatures that could help
            if comp.kind == "WATERBEND":
                helpers = len(cost_payment.candidates(Plan.view(state, player, info), comp, player, card))
                mana = mana.plus_generic(-min((x or 0) if comp.x else comp.amount, helpers))
        if not can_pay(state, player, mana, info, exclude=(card.id,) if cost.tap else (),
                       purpose=Purpose(ability_of=ch, selected_cost_has_x="{X}" in cost.mana, special=_special(ability), cost_colorless='{C}' in (ability.cost or ''))):
            return f"Not enough mana to pay {mana.text()}"
    return None


def _special(ability: AbilityText) -> str | None:
    """-- mana for special abilities (wave 19E) -- the kind of ability "Spend this mana only to activate an equip ability / power-up
    abilities" asks about (702.6 equip; 702.193 power-up)."""
    if re.search(r"(?:^|:\s+)(?:~|[Tt]his Class)'s level becomes \d+\.", ability.text):
        return 'class_level'
    return ability.special or ("power_up" if ability.text.startswith("Power-up — ") else None)


def equip_ability(plan: Plan, card: CardInstance, ch: Characteristics, a: A.ActivateAbility,
                  equip: tuple[str, str, str]) -> None:
    """702.6a Equip [cost]: "[Cost]: Attach this permanent to target creature you control. Activate only as a sorcery."
    (702.6b: the target narrowed by a quality; -- equip (wave 15E) -- non-mana costs and the line's own trailing sentences).
    An Equipment that's also a creature can't equip (301.5c)."""
    cost, target, tail = equip
    if "Equipment" not in ch.subtypes or ch.is_creature:
        raise ActionError(f"{ch.name} can't equip a creature" + (" while it's a creature" if ch.is_creature else ""))
    sides = attachments.equip_sides(cost)
    if _first_alt(plan, "equip") and "{0}" not in sides:  # -- first activation (wave 48D) -- 118.9: "You may pay {0} rather than pay the equip cost of the first equip ability you activate"
        sides = [*sides, "{0}"]
    if len(sides) > 1:  # -- cast keywords (wave 43D) -- "Equip {2} or {B}", "Equip—Pay {3} or discard a card.": the cost is announced (601.2b)
        picked = _equip_side(plan, card, ch, a, sides)
        if picked is None:
            return  # waiting for the choice
        cost = picked
    ability = AbilityText(index=a.ability, kind="activated", cost=cost, special="equip",
                          text=f"{cost}: Attach {ch.name} to target creature you control. Activate only as a sorcery."
                               + (f" {tail}" if tail else ""))
    definition = {"kind": "activated", "effects": [{"do": "attach_self"}], "target": {"what": target}}
    activate_to_stack(plan, card, ch, ability, a, definition=definition, exclude_targets=(card.id,))


def _first_alt(plan: Plan, act: str) -> bool:
    """-- first activation (wave 48D) -- 118.9, 602.2b: may the actor pay {0} rather than the ``act`` ("equip" / "cycling") cost? A static says so (cast_limits.first_alt)
    and they haven't activated one this turn (``_activated`` keeps the log, whoever's static is there: Gavi's ruling, the whole turn counts)."""
    from app.rules import cast_limits

    return cast_limits.first_alt(plan.state, plan.actor, act, plan.info,
                                 first=plan.rules.once_per_turn.get(f"activated:{plan.actor}:{act}") != plan.state.turn.number)


def _activated(plan: Plan, act: str) -> None:
    """-- first activation (wave 48D) -- the per-turn log of the actor's activations by kind, at the choke point (equip: activate_to_stack; cycling: cycle)."""
    plan.rules.once_per_turn[f"activated:{plan.actor}:{act}"] = plan.state.turn.number


def _equip_side(plan: Plan, card: CardInstance, ch: Characteristics, a: A.ActivateAbility, sides: list[str], cycling: bool = False,
                labels: list[str] | None = None) -> str | None:
    """-- cast keywords (wave 43D) -- 601.2b: the cost the activator announced for an equip ability that lets them pay one of several ("{2} or {B}",
    "Pay {3} or discard a card"; 702.6a, 118.3: a side that can't be paid can't be chosen), or None while they're asked. What is public decides whether one is
    offered (mana, the permanents, the counters): a side that discards a card from the hand is always offered, so that no omission tells the table what the
    hand holds (the activation refuses it if it can't be paid)."""
    def ability_of(side: str) -> AbilityText:
        if cycling:
            return AbilityText(index=a.ability, kind="activated", cost=f"{side}, Discard this card",
                               text=f"Cycling — {side}, Discard this card: Draw a card.")
        return AbilityText(index=a.ability, kind="activated", cost=side, special="equip", text=f"{side}: Attach {ch.name} to target creature you control. "
                           "Activate only as a sorcery.")

    given = next((c.cards[0] for c in a.cost_choices if c.component == costs.EITHER_SLOT and c.cards), None)
    if given is not None:
        i = int(given[7:]) if given.startswith("either:") and given[7:].isdigit() else -1
        if not 0 <= i < len(sides):
            raise ActionError("Choose one of the costs of the equip ability")
        return sides[i]
    from app.rules import cycling_costs

    if cycling and all(cycling_costs.mana_only(side) for side in sides):
        paid = []
        problems = [None if can_pay(plan.state, plan.actor, M.parse_cost(permissions.ability_mana(plan.state, plan.actor, card, ch, side, plan.info, ability_text="cycling")).with_x(0), plan.info,
                                    purpose=Purpose(ability_of=ch, selected_cost_has_x="{X}" in side)) else "Not enough mana" for side in sides]
        offered = [i for i, why in enumerate(problems) if why is None]
    else:
        paid = [ability_cost(ch, ability_of(side), state=plan.state, card=card, info=plan.info) for side in sides]
        problems = [ability_problem(plan.state, plan.actor, card, ch, ability_of(side), cost, check_priority=False, info=plan.info, plan=plan)
                    for side, cost in zip(sides, paid, strict=True)]
        offered = [i for i, cost in enumerate(paid) if problems[i] is None or not cycling and any(c.kind in _HAND_PARTS for c in cost.components)]
    if not offered:
        raise ActionError(problems[0] or "You can't pay the cost of that ability")
    if len(offered) == 1:  # (118.3: the other can't be paid — nothing to choose)
        a.cost_choices = [*a.cost_choices, A.CostChoice(component=costs.EITHER_SLOT, cards=[f"either:{offered[0]}"])]
        return sides[offered[0]]
    decide(plan, player=plan.actor, kind="choose_cards", prompt=f"{ch.name or 'It'}: choose the cost of its {'cycling' if cycling else 'equip'} ability (601.2b), or none to cancel",
           options=[DecisionOption(id=f"either:{i}", label=(labels or sides)[i]) for i in offered], min_choices=0, max_choices=1,
           resume={"step": "ability_cost", "component": costs.EITHER_SLOT, "amount": 1, "intent": a.model_dump(mode="json", exclude={"r", "actor", "ts"})},
           source=card)
    return None


def activate_to_stack(plan: Plan, card: CardInstance, ch: Characteristics, ability: AbilityText,
                      a: A.ActivateAbility, *, definition: dict[str, Any] | None = None,
                      exclude_targets: tuple[str, ...] = (), keep_revealed: bool = False) -> None:
    from app.rules import (
        activation_alternatives,
        colored_activation_costs83,
        defined_activation_x,
        modal_abilities,  # (a leaf module over this one)
    )

    colored_activation_costs83.require_known(plan, card, ability.text)
    input_x = a.x_value
    announced = activation_alternatives.announce(plan, a, card, ch, ability)
    if announced is None:
        return
    ability = announced
    if plan.locked_cost is None and (fixed := defined_activation_x.spec(ability, ch.name)) is not None:
        x = defined_activation_x.evaluate(plan, card, fixed)
        if a.x_value is not None and a.x_value != x:
            raise ActionError(f"X is {x} for this ability; it isn't chosen (107.3c)")
        a.x_value = x
    cost = ability_cost(ch, ability, state=plan.state, card=card, info=plan.info, target="?", actor=plan.actor)  # (wave 46C: the best case until the targets are chosen, below)
    if a.x_value is not None and any(c.kind == costs.PAY_LIFE and c.x for c in cost.components):
        from dataclasses import replace as replace_cost

        # 602.2b / 601.2b: the announced X sizes life before affordability/payment.
        parts = tuple(replace_cost(c, amount=max(0, a.x_value)) if c.kind == costs.PAY_LIFE and c.x else c for c in cost.components)
        cost = replace_cost(cost, components=parts, life=sum(c.amount for c in parts if c.kind == costs.PAY_LIFE))
        plan.reserved_life = cost.life
    plan.reserved_life = cost.life
    problem = ability_problem(plan.state, plan.actor, card, ch, ability, cost, plan=plan)
    if problem:
        raise ActionError(problem)
    oid = plan.oid(card)  # the object activating (paying a cost may move it: it'd be a new object)
    mana = ability_mana_cost(cost)
    was_locked = plan.locked_cost is not None
    if plan.locked_cost is not None and not mana.x:  # -- cost changers (wave 4I) -- 602.2b → 601.2f: locked in
        mana = _locked(plan, mana)
    if (mana.x or cost.loyalty_x or cost.energy_x or cost.x_chosen) and a.x_value is None:  # (wave 3E: "Pay X {E}"; x_chosen: wave 4H)
        raise ActionError("Choose a value for X")
    if (every := next((c for c in cost.components if c.every), None)) is not None:
        a.x_value = cost_payment.counters_on(card, every.counter)  # -- activated sweep (wave 26C) -- "Remove all oil counters": all there are now (602.2b)
    from app.rules import static_perm100d  # -- static permanents (wave 100D) -- Carth the Lion: [+1] more

    plus = static_perm100d.loyalty_plus(plan.state, plan.info, plan.actor) if cost.loyalty is not None or cost.loyalty_x else 0
    if cost.loyalty_x and card.counters.get("loyalty", 0) < (a.x_value or 0) - plus:
        raise ActionError(f"{ch.name} doesn't have {a.x_value} loyalty")  # 606.6
    if definition is None:
        definition = None if plan.manual(card) else scripts.definitions(ch).get(ability.index)
    if definition is not None and definition["kind"] != "activated":
        definition = None
    definition = per_opponent.for_cast(plan, card.id, definition)  # -- per-opponent targets (wave 23A) --
    from app.rules import random_consequences

    definition = random_consequences.bind_activation(plan, card, definition)
    if definition is not None and (a.x_value or 0) < definition.get("x_min", 0):  # -- spell copies (wave 31D) -- 107.1b: "X can't be 0"
        raise ActionError(f"{ch.name}: X can't be {a.x_value or 0}")
    if exclude_targets and set(a.targets) & set(exclude_targets):
        raise ActionError(f"{ch.name} can't target itself")
    modal: modal_abilities.Announced | None = None
    if definition is not None and definition.get("modes"):  # -- modal abilities (wave 1A): 602.2b → 601.2b-c --
        modal = modal_abilities.announce(plan, a, card, definition, ability.index, oid, f"{ch.name}’s ability")
        picked_targets = None if modal is None else modal.targets  # (modes first, then each mode's target)
    else:
        picked_targets = choose_targets(plan, a, definition, f"{ch.name}’s ability", exclude=exclude_targets)
    if picked_targets is None:
        return
    chosen = picked_targets.flat
    if not was_locked:  # -- most-played cards III (wave 46C) -- 601.2f: the total cost once the targets are chosen (601.2c): "Equip abilities you activate that target this creature cost {2} less"
        exact = ability_cost(ch, ability, state=plan.state, card=card, info=plan.info, target=chosen[0].id if chosen else None,
                             targets=tuple(t.id for t in chosen), actor=plan.actor)
        if exact.mana != cost.mana:
            mana = ability_mana_cost(exact)
    problem = cost_payment.problem(plan, cost, card, plan.actor, a.x_value)  # 118.3 / 601.2h: nothing is paid unless all can be
    if problem:
        raise ActionError(problem)
    cost_objects = cost_payment.choose(plan, a, cost, card, f"{ch.name}’s ability")  # (602.2b → 601.2h)
    if cost_objects is None:
        return  # waiting for the payer's choice; nothing has been paid
    not_mana = cost_payment.excluded(cost, card, cost_objects)  # (they can't also tap for mana)
    due = mana.with_x(a.x_value or 0)
    x_reductions: list[int] = []
    if mana.x:  # -- review 35 -- 601.2f (602.2b): X is chosen first (601.2b), then the total is increased and reduced ("Abilities you activate cost {2}
        # less": Zirda, Training Grounds); ability_cost leaves an {X} cost alone (its X isn't known there)
        from app.rules import cost_changes

        own = cost_changes.ability_delta(plan.state, card.controller, card, ch, ability.text, plan.info) if "This ability costs " in ability.text else 0
        due = M.parse_cost(permissions.ability_mana(plan.state, plan.actor, card, ch, due.text(), plan.info, own, ability.text, target=chosen[0].id if chosen else None, capture=x_reductions, targets=tuple(t.id for t in chosen)))
        due = _variable_ability_matching(plan.state, card, ch, ability, plan.info, due)
    from app.rules import waterbend102

    due = waterbend102.due(due, cost, cost_objects)
    from app.rules import cast_limits, x_mana_restrictions

    restriction_text = ability.text + (" " + " ".join(definition["modes"][i]["text"] for i in modal.modes) if modal is not None and definition is not None else "")
    x_payment = x_mana_restrictions.metadata(restriction_text, a.x_value or 0, x_reductions[0] if x_reductions else 0, due,
        mode=cast_limits.ability_spend_mode(plan.state, plan.actor, card, ch, plan.info), locked=plan.locked_x_payment)
    purpose = Purpose(ability_of=ch, selected_cost_has_x="{X}" in cost.mana, special=_special(ability), x_payment=x_payment, cost_colorless='{C}' in (ability.cost or ''))
    announced_due = announce_phyrexian(plan, a, due, f"{ch.name}’s ability", exclude=not_mana, purpose=purpose, trusted=was_locked)  # (wave 50B: 602.2b → 601.2b)
    if announced_due is None:
        return
    due = announced_due
    from app.rules import payment_continuations as pc

    resolved_x = a.x_value
    a.x_value = input_x
    from app.rules import first_target_activation_cost58

    data = _PostActivation(a.model_copy(deep=True), ability, None, card.model_copy(deep=True), ch, chosen, cost, cost_objects,
                           definition, oid, picked_targets, _ModalSnapshot.capture(modal), resolved_x,
                           {cid: plan.oid(cid) for cid in not_mana if cid in plan.state.cards}, keep_revealed=keep_revealed,
                           targets_controlled_creature=first_target_activation_cost58.qualifies(plan.state, plan.actor, tuple(t.id for t in chosen), plan.info))
    after = pc.continuation(plan, "activation_announced", data)
    from app.rules import fixed_top_graveyard_cost46

    if fixed_top_graveyard_cost46.has(cost) and a.sources is None:
        fixed_top_graveyard_cost46.offer_mana_window(plan, a, due, f"{ch.name}’s ability",
            exclude=not_mana, purpose=purpose, then=after)
        return
    if payment_step(plan, a, due, f"{ch.name}’s ability", exclude=not_mana, purpose=purpose, then=after):
        return
    pay_then(plan, plan.actor, due, f"paid {due.text()} to activate {ch.name}",
             sources=a.sources, exclude=not_mana, purpose=purpose, life_due=2 * len(a.life_symbols or ()), then=after)



@dataclass
class _ModalSnapshot:
    targets: ChosenTargets
    modes: list[int]
    slots: list[list[TargetRef]]
    specs: list[dict[str, Any] | None]
    effects: list[dict[str, Any]]
    definition: dict[str, Any]
    index: int

    @classmethod
    def capture(cls, modal: modal_abilities.Announced | None) -> _ModalSnapshot | None:
        return None if modal is None else cls(modal.targets, modal.modes, modal.slots, modal.specs, modal.effects, modal.definition, modal.index)

    def native(self) -> modal_abilities.Announced:
        return modal_abilities.Announced(self.targets, self.modes, self.slots, self.specs, self.effects, self.definition, self.index)


@dataclass
class _PostActivation:
    a: A.ActivateAbility
    ability: AbilityText
    ability_id: str | None
    card: CardInstance
    ch: Characteristics
    chosen: list[TargetRef]
    cost: AbilityCost
    cost_objects: dict[int, list[str]]
    definition: dict[str, Any] | None
    oid: str
    picked_targets: ChosenTargets | None
    modal: _ModalSnapshot | None

    resolved_x: int | None = None
    reserved_objects: dict[str, str] | None = None
    keep_revealed: bool = False
    numeric_roll_cost: NumericRollCostReceipt | None = None
    targets_controlled_creature: bool | None = None  # Frozen before any nonmana target may leave as payment.


def _activation_announced(plan: Plan, data: _PostActivation, paid: M.Payment | None) -> None:
    from app.rules import fixed_top_graveyard_cost46, payment_continuations

    if fixed_top_graveyard_cost46.has(data.cost):
        then = payment_continuations.continuation(plan, "activation_announced", data)
        then["payment"] = payment_continuations.payment_data(paid)
        if fixed_top_graveyard_cost46.offer_order(plan, then):
            return
        fixed_top_graveyard_cost46.top(plan, plan.actor)
    a = data.a.model_copy(update={"x_value": data.resolved_x}) if data.resolved_x is not None else data.a
    ability, cost = data.ability, data.cost
    card = plan.state.cards.get(data.card.id) or data.card
    for cid, oid in (data.reserved_objects or {}).items():
        if cid not in plan.state.cards or plan.oid(cid) != oid:
            raise ActionError("An object reserved for the activation cost moved before it could be paid")
    if (problem := cost_payment.problem(plan, cost, card, plan.actor, a.x_value)) is not None:
        raise ActionError(problem)
    if cost.tap and card.tapped:
        raise ActionError("The source cannot tap to pay the announced activation cost")
    selected = [choice for choice in a.cost_choices if choice.component not in data.cost_objects]
    selected += [A.CostChoice.model_construct(component=index, cards=list(ids)) for index, ids in data.cost_objects.items()]
    checking = a.model_copy(update={"cost_choices": selected})
    if cost_payment.choose(plan, checking, cost, card, f"{data.ch.name}’s ability") is None:
        raise ActionError("The originally chosen activation costs can no longer be paid")
    effect = ability.text.split(":", 1)[1].strip() if ":" in ability.text else ability.text
    # -- review (wave 27D) -- 602.2a / 701.20a: a card whose ability is activated from the hand is revealed, so the ability on the stack
    # names it for everyone; the card stays in the hand, anonymous again once the stack object carries its name
    created = _create_ability(plan, card, effect[:500], keep=data.keep_revealed)
    new_ids = getattr(created, "r", None)
    ability_id = new_ids.ids[0] if new_ids is not None else None
    # Pay the costs (602.2): tap first so the source can't also pay for its own mana cost.
    if cost.tap:
        plan.do({"type": "tap", "card_ids": [card.id], "tapped": True})
    from app.rules import static_perm100d  # -- static permanents (wave 100D) -- Carth the Lion

    plus = static_perm100d.loyalty_plus(plan.state, plan.info, plan.actor) if cost.loyalty is not None or cost.loyalty_x else 0
    delta = ((cost.loyalty or 0) if not cost.loyalty_x else -(a.x_value or 0)) + plus
    plan.rules.once_per_turn["loyalty_removed110b"] = max(0, -delta) if cost.loyalty is not None or cost.loyalty_x else 0  # -- wave 110B -- read by triggers.activated
    if delta:
        if delta > 0:  # -- loyalty costs (review 31) -- 606.4: put as a cost through the counter choke point like any cost's counters (122.6):
            from app.rules import replace

            # "If you would put …" applies (Vorinclex, Lae'zel), "If an effect would put …" doesn't (614.16, Doubling Season ruling)
            replace.put_counters(plan, [(card.id, "loyalty", delta)], by=plan.actor, effect=False)
        else:
            plan.do({"type": "counter", "card_ids": [card.id], "kind": "loyalty", "delta": delta})
    for kind, n in cost.remove_counters:
        plan.do({"type": "counter", "card_ids": [card.id], "kind": kind, "delta": -n})
    if cost.life:
        from app.rules import replace as _replace_life  # (wave 28B: 119.4)
        _replace_life.lose_life(plan, [(plan.actor, cost.life)])
    data.ability_id = ability_id
    _post_activation(plan, data, paid)


def _post_activation(plan: Plan, data: _PostActivation, paid: M.Payment | None) -> None:
    if data.cost.numeric_roll_sides == 8:
        from app.rules import payment_continuations as pc
        from app.rules import random_cost_roll44

        if data.numeric_roll_cost is None:
            if data.ability_id is None:
                raise ActionError('This numeric cost needs its announced stack ability')
            then = {**pc.continuation(plan, 'post_activation', data), 'payment': pc.payment_data(paid)}
            random_cost_roll44.run(plan, random_cost_roll44.Frame(source=data.card.id, source_object=data.oid,
                ability=data.ability_id, ability_object=plan.oid(data.ability_id), roller=plan.actor, then=then))
            return
        receipt = data.numeric_roll_cost
        if (data.ability_id is None or receipt.source_object != data.oid or receipt.roller != plan.actor
                or receipt.ability_object != plan.oid(data.ability_id) or receipt.result != data.resolved_x):
            raise ActionError('The numeric cost receipt does not match this activation')
    from app.rules.engine import advance

    a = data.a.model_copy(update={"x_value":data.resolved_x}) if data.resolved_x is not None else data.a
    ability = data.ability
    ability_id = data.ability_id
    ch = data.ch
    chosen = data.chosen
    cost = data.cost
    cost_objects = data.cost_objects
    definition = data.definition
    oid = data.oid
    picked_targets = data.picked_targets
    card = plan.state.cards.get(data.card.id) or data.card
    modal = None if data.modal is None else data.modal.native()
    from app.rules import mana_units

    record = PaymentRecord(card=ability_id or card.id, controller=plan.actor, total_cost=ability.cost or "",
                           mana_spent=dict(paid.spent) if paid else {},
                           mana_riders=mana_units.ability_riders(paid.riders) if paid else [],
                           mana_tags=paid.tags if paid else [], snow_spent=dict(paid.snow_spent) if paid else {}, mana_sources=paid.sources if paid else [],
                           numeric_roll_cost=data.numeric_roll_cost, life=cost.life + (paid.life if paid else 0),
                           tapped=list(paid.tapped) if paid else [], x=a.x_value)
    plan.cycling_card = card.id if definition is not None and definition.get("cycling") else None
    try:
        cost_payment.pay(plan, cost, card, cost_objects, record)  # sacrifice, discard, exile, return, tap others …
    finally:
        plan.cycling_card = None
    if definition is not None and definition.get("cycling"):
        _activated(plan, "cycling")
        emit(plan.state, "cycled", object_id=oid, card=card.id, player=plan.actor, amount=a.x_value or 0)
    record.activation_cost_has_x = "{X}" in (ability.cost or "")
    record.activation_cost_has_tap = cost.tap
    record.activation_life_paid = max(0, record.life - (paid.auxiliary_life if paid else 0))
    if ability_id:
        record_payment(plan, ability_id, record)  # Each activation has its own mana and nonmana payment.
    if a.x_value is not None and ability_id:
        plan.do({"type": "set_stack_info", "card_id": ability_id, "x": a.x_value})
    if a.targets and ability_id:
        plan.target_arrows(ability_id, a.targets)
    r = plan.rules
    if modal is not None and ability_id:  # (wave 1A) each chosen mode's effects, with its own target slot
        r.stack[ability_id] = StackEntry(kind="activated", controller=plan.actor, source_card=card.id, source_object=oid,
                                         name=ch.name, x=a.x_value, **modal.entry)
        modal_abilities.announced(plan, ability_id, card, modal, oid)  # the modes chosen are public; remembered
    elif definition is not None and ability_id:
        assert picked_targets is not None
        r.stack[ability_id] = StackEntry(kind="activated", controller=plan.actor, source_card=card.id, source_object=oid,
                                         name=ch.name, x=a.x_value, optional=bool(definition.get("optional")),  # (wave 34B: 608.2d, asked on resolution)
                                         **picked_targets.entry(definition),
                                         # -- this-turn history (wave 4D) -- "the second time this ability has resolved"
                                         effects=history.counting_activations(history.counting_resolutions(list(definition["effects"]), f"{oid}:{a.ability}"),
                                                                f"{oid}:{a.ability}"))
    if chosen and ability_id:
        from app.rules.triggers import targeted

        targeted(plan, ability_id, plan.actor, chosen)
    from app.rules import first_target_activation_cost58

    first_target_activation_cost58.record(plan, data.targets_controlled_creature)
    if ability.special == "equip":  # -- first activation (wave 48D) --
        _activated(plan, "equip")
    if ability_id:  # -- activation (wave 11F) -- 602.2: "Whenever a player activates an ability …"
        from app.rules.triggers import activated

        activated(plan, card, oid, loyalty=ability.kind == "loyalty", ability_id=ability_id, text=ability.text, outlast=ability.special == "outlast" or ability.index >= 100)
    if ability.kind == "loyalty":
        if r.loyalty_used.get(oid) == plan.state.turn.number:
            r.loyalty_second[oid] = plan.state.turn.number  # -- static_other sweep (wave 19A) -- the second use (Oath of Teferi)
        r.loyalty_used[oid] = plan.state.turn.number
    # -- turn state (wave 100H) -- "if you've activated a loyalty ability this turn", "… an ability of a card in a graveyard", "an exhaust ability"
    # (602.2: who did; the source as it was as it was activated, before a cost moved it: 603.10a; 702.177b)
    was = r.lki.get(oid) if plan.oid(card) != oid else None
    kinds100h = [k for k, hit in (("loyalty", ability.kind == "loyalty"), ("exhaust", ability.text.startswith(restrictions.EXHAUST)),
                                  ("gy_ability", (was.zone if was is not None else card.zone).endswith(":graveyard"))) if hit]
    if kinds100h:
        from app.game.rules_state import TurnFact, turn_log_now

        if (log100h := turn_log_now(plan.state)) is not None:
            log100h.facts += [TurnFact(kind=k, player=plan.actor, object_id=oid) for k in kinds100h]
    if restrictions.limited(restrictions.parse(_own_text(ability.text, ch.name)) or []) or (  # "Activate only once each turn" / "… only once"
            definition is not None and '"history": "activations"' in json.dumps(definition["effects"])):
        restrictions.record_use(r, oid, ability.index, plan.state.turn.number)  # (wave 19E: also for "activated N or more times this turn")
    r.passed = []
    r.priority = plan.actor
    if r.prefs_for(plan.actor).hold_priority:
        plan.hold = plan.actor
        return
    r.auto_pass = plan.actor  # (as after a cast: engine.advance passes for you once the triggers are on the stack)
    advance(plan)


def activatable(state: GameState, player: str, info: CardInfo, *, check_priority: bool = True) -> list[dict[str, Any]]:
    """Abilities of ``player``'s permanents that could be activated right now (for hints)."""
    out: list[dict[str, Any]] = []
    for cid in [c for zone, ids in state.zones.items() if zone.endswith(":battlefield") for c in ids]:
        card = state.cards[cid]
        from app.rules.layers import derive

        ch = derive(state, card, chars.of(card, info), info)
        for ab in ch.abilities:
            if ab.kind in ("activated", "loyalty"):
                problem = ability_problem(state, player, card, ch, ab, ability_cost(ch, ab, state=state, card=card, info=info),
                                          check_priority=check_priority, info=info)
                if problem is None:
                    cost = ability_cost(ch, ab, state=state, card=card, info=info)
                    # (wave 24D) 107.3k: X announced as the ability is activated ("{X}, {T}:", "Sacrifice X …", −X, "Pay X {E}")
                    needs_x = ability_mana_cost(cost).x or cost.loyalty_x or cost.energy_x or cost.x_chosen
                    from app.rules import defined_activation_x

                    if defined_activation_x.spec(ab, ch.name) is not None:
                        needs_x = False
                    out.append({"card_id": cid, "ability": ab.index, **({"x": True} if needs_x else {})})
            elif card.controller == player and ab.kind == "keywords" and _can_crew(state, player, card, ch, ab.index, info, check_priority):
                out.append({"card_id": cid, "ability": ab.index})
    for cid in state.zones.get(zone_key(player, "hand"), []):  # -- ability words (wave 4F) -- channel (113.6m)
        card = state.cards[cid]
        ch = chars.of(card, info)
        for ab in ch.abilities:
            if ab.kind == "activated" and ability_cost(ch, ab).from_hand and \
                    ability_problem(state, player, card, ch, ab, ability_cost(ch, ab, state=state, card=card, info=info),  # (wave 4I)
                                    check_priority=check_priority,
                                    info=info) is None:
                out.append({"card_id": cid, "ability": ab.index})
    for cid in state.zones.get(zone_key(player, "command"), []):  # -- activated from hand / command zone (wave 27D) -- 113.6m
        card = state.cards[cid]
        ch = chars.of(card, info)
        for ab in ch.abilities:
            if ab.kind == "activated" and ability_cost(ch, ab).command_only and \
                    ability_problem(state, player, card, ch, ab, ability_cost(ch, ab, state=state, card=card, info=info),
                                    check_priority=check_priority, info=info) is None:
                out.append({"card_id": cid, "ability": ab.index})
    for cid in [*state.zones.get(zone_key(player, "hand"), []), *state.zones.get(zone_key(player, "command"), [])]:  # -- keywords (wave 15E) -- ninjutsu (702.49a; wave 50J: commander ninjutsu, 702.49d)
        card = state.cards[cid]
        ch = chars.of(card, info)
        for ab in ch.abilities:
            if (cost_text := ninjutsu.cost_of(ch, ab.index, command=card.zone == zone_key(player, "command"))) is not None:
                made = ninjutsu.ability(ch, ab.index, cost_text)
                if ability_problem(state, player, card, ch, made, ability_cost(ch, made, state=state, card=card, info=info),
                                   check_priority=check_priority, info=info) is None:
                    out.append({"card_id": cid, "ability": ab.index})
    for cid in state.zones.get(zone_key(player, "hand"), []):  # -- X from the triggering object (wave 34C) -- 107.3a: "Cycling {X}{1}{U}" asks for X
        r = state.rules
        if r is not None and (not check_priority or (r.priority == player and r.decision is None)):
            ch = chars.of(state.cards[cid], info)
            out += [{"card_id": cid, "ability": ab.index, "x": True} for ab in ch.abilities
                    if (found := hand_ability(ch, ab.index)) is not None and M.parse_cost(found[1]).x or (sus := suspend_info(ch, ab.index)) is not None and sus[0] is None]  # (wave 50H: Suspend X)
    for cid in state.zones.get(zone_key(player, "graveyard"), []):  # 113.6m: "Exile this card from your graveyard: …"
        card = state.cards[cid]
        ch = chars.of(card, info)
        from app.rules import unearth_costs

        for ab in ch.abilities:
            if (unearth_text := unearth_costs.of(ch, ab.index)) is not None:
                synthetic = unearth_costs.ability(ab.index, unearth_text)
                if ability_problem(state, player, card, ch, synthetic, ability_cost(ch, synthetic, state=state, card=card, info=info),
                                   check_priority=check_priority, info=info) is None:
                    out.append({"card_id": cid, "ability": ab.index})
        for ab in ch.abilities:  # -- keywords (wave 15E) -- embalm / eternalize
            if (gk := graveyard_keywords.ability(ch, ab.index)) is not None and ability_problem(
                    state, player, card, ch, gk, ability_cost(ch, gk, state=state, card=card, info=info),
                    check_priority=check_priority, info=info) is None:
                out.append({"card_id": cid, "ability": ab.index})
        for ab in ch.abilities:
            if ab.kind == "activated" and ability_cost(ch, ab).from_graveyard and \
                    ability_problem(state, player, card, ch, ab, ability_cost(ch, ab, state=state, card=card, info=info),  # (wave 4I)
                                    check_priority=check_priority,
                                    info=info) is None:
                out.append({"card_id": cid, "ability": ab.index})
    for cid in state.zones.get(zone_key(player, "exile"), []):  # -- activated other (wave 42C) -- 113.6m: "Return this card from your graveyard or from exile …"
        card = state.cards[cid]
        ch = chars.of(card, info)
        for ab in ch.abilities:
            if ab.kind == "activated" and ability_cost(ch, ab).exile_too and \
                    ability_problem(state, player, card, ch, ab, ability_cost(ch, ab, state=state, card=card, info=info),
                                    check_priority=check_priority, info=info) is None:
                out.append({"card_id": cid, "ability": ab.index})
    return out


def _can_crew(state: GameState, player: str, card: CardInstance, ch: Characteristics, index: int, info: CardInfo,
              check_priority: bool) -> bool:
    from app.rules import (
        crew_saddle,  # -- crew & saddle (wave 23D) -- 702.171a: a saddle ability is the same cost, at sorcery speed
    )

    n = crew_power(ch, index)
    r = state.rules
    saddle = n is None
    if n is None and (n := crew_saddle.saddle_power(ch, index)) is not None and (
            state.turn.active_player != player or state.turn.phase not in MAIN_PHASES or state.zones.get(STACK)):
        return False
    if n is None or r is None or (check_priority and (r.priority != player or r.decision is not None)):
        return False
    # -- cast limits (wave 5E) -- crew is an activated ability (702.122a)
    from app.rules import cast_limits

    if cast_limits.activation_problem(state, player, card, ch, info) is not None:
        return False
    limits = restrictions.parse(_find_ability(ch, index).text) or []
    if restrictions.problem(state, player, card, index, limits, Plan.view(state, player, info), ch.name):
        return False
    from app.rules.layers import derive

    total = 0
    for c in state.cards.values():
        if c.zone == card.zone and c.controller == player and c.id != card.id and not c.tapped:
            cch = derive(state, c, chars.of(c, info), info)
            if cch.is_creature and (saddle or "cant_crew" not in cch.imposed):
                total += crew_value(c, cch)
    return total >= n


def _count(option: tuple[str, ...]) -> dict[str, int]:
    out: dict[str, int] = {}
    for m in option:
        out[m] = out.get(m, 0) + 1
    return out


@dataclass
class _ManaDone:
    nested: bool = False


def _mana_done(plan: Plan, data: _ManaDone, payment: M.Payment | None) -> None:
    plan.rules.passed = []
    if data.nested:
        resume_outer(plan)
    else:
        plan.rules.priority = plan.actor


def _mana_terminal(plan: Plan, *, nested: bool = False) -> dict[str, Any]:
    from app.rules import payment_continuations as pc

    return pc.continuation(plan, "mana_done", _ManaDone(nested))


def _manual_produce(plan: Plan, card: CardInstance, ability: M.ManaAbility, option: tuple[str, ...], index: int,
                    *, nested: bool = False, option_index: int | None = None) -> None:
    from app.rules import replace as replacements_

    after = _mana_terminal(plan, nested=nested)
    if produce(plan, card, ability, option, index, then=after, option_index=option_index):
        replacements_.run_then(plan, after)


@dataclass
class _Production:
    source: CardInstance
    ability: M.ManaAbility
    option: tuple[str, ...]
    index: int | None
    extra: AbilityCost | None
    then: dict[str, Any]
    option_index: int | None = None


def _production_paid(plan: Plan, data: _Production, payment: M.Payment | None) -> None:
    from app.rules import replace as replacements_

    card = plan.state.cards.get(data.source.id) or data.source
    if _produce_body(plan, card, data.ability, data.option, data.index, data.extra, data.then, input_payment=payment, option_index=data.option_index):
        replacements_.run_then(plan, data.then)


def produce(plan: Plan, card: CardInstance, ability: M.ManaAbility, option: tuple[str, ...], index: int | None = None,
            *, activation_exclude: tuple[str, ...] = (), activation_cost: M.ManaCost | None = None,
            then: dict[str, Any] | None = None, option_index: int | None = None) -> bool:
    """Produce mana; false means its persistent continuation owns all further work."""
    extra = parse_ability_cost(ability.extra_cost, card_name=plan.ch(card).name) if ability.extra_cost else None
    cost = activation_cost if activation_cost is not None else mana_activation_cost(plan.state, card, plan.ch(card), ability, plan.info)
    purpose = Purpose(ability_of=plan.ch(card), player=card.controller,
                      selected_cost_has_x='{X}' in (extra.mana if extra else ''),
                      cost_colorless='{C}' in (extra.mana if extra else ''))
    input_payment: M.Payment | None = None
    if not cost.is_free:
        if payment_mode(plan, card.controller) == "self" and not pool_covers(plan.state, card.controller, cost, purpose=purpose, info=plan.info):
            raise ActionError(f"Add {cost.text()} to your mana pool first to activate {plan.ch(card).name}")
        sources: list[str] | None = [] if payment_mode(plan, card.controller) == "self" else None
        if then is not None:
            from app.rules import payment_continuations as pc

            after = pc.continuation(plan, "production_paid", _Production(card, ability, option, index, extra, then, option_index))
            pay_then(plan, card.controller, cost, f"paid {cost.text()} to activate {plan.ch(card).name}", then=after,
                     sources=sources, exclude=(card.id,) + activation_exclude, purpose=purpose)
            return False
        input_payment = pay(plan, card.controller, cost, f"paid {cost.text()} to activate {plan.ch(card).name}", sources=sources,
            exclude=(card.id,) + activation_exclude, purpose=purpose)
    return _produce_body(plan, card, ability, option, index, extra, then, input_payment=input_payment, option_index=option_index)


def _produce_body(plan: Plan, card: CardInstance, ability: M.ManaAbility, option: tuple[str, ...], index: int | None,
                  extra: AbilityCost | None, then: dict[str, Any] | None, *, input_payment: M.Payment | None = None, option_index: int | None = None) -> bool:
    from app.rules import cost_moves
    if ability.sacrifice_self and cost_moves.reserved(plan.state, card.controller, card.id):
        raise ActionError(f'{card.name} is reserved for a declaration cost; tap it for mana without sacrificing it')
    if ability.self_counter is not None:  # -- refused copy/mana (wave 3R3) -- the cost: a counter on the source (122.1a)
        if not card.zone.endswith(":battlefield"):
            raise ActionError(f"{plan.ch(card).name} isn't on the battlefield")
        from app.rules import replace as replace_  # (the counter choke point; a cost, not an effect)

        replace_.put_counters(plan, [(card.id, ability.self_counter, 1)], by=card.controller, effect=False)
    from app.rules import removed_mana  # -- if you do (wave 6F) -- the cost: n counters removed

    if removed_mana.parts(ability.count) is not None:
        kind, n = removed_mana.removed(ability.count or "", option)
        if n < 0 or card.counters.get(kind, 0) < n:  # 118.3
            raise ActionError(f"{plan.ch(card).name} doesn't have {n} {kind} counters")
        if n:
            plan.do({"type": "counter", "card_ids": [card.id], "kind": kind, "delta": -n}, actor=card.controller)
    mana = _count(option)
    who = card.controller  # (wave 24D: before a sacrifice cost sends the card away)
    oid = plan.oid(card)  # (wave 5A: the object as it was tapped)
    from app.rules import mana_units

    plan.do({"type": "rules_mana", "player": who, "tap": [card.id] if ability.tap else [],
             "sacrifice": [card.id] if ability.sacrifice_self else [], **mana_units.added(plan, card, ability, mana, option=option, option_index=option_index),
             "life": 0, "label": f"added {M.symbols(mana)}"[:200]}, actor=who)
    if extra and extra.life:  # -- life modifiers (wave 28B) -- 119.4 / 118.11: the life paid is a life loss the replacements may change
        from app.rules import replace as _replace_life

        _replace_life.lose_life(plan, [(who, extra.life)], actor=who)
    if mana:
        emit(plan.state, "mana_added", object_id=oid, card=card.id, player=who, amount=sum(mana.values()),
             counter="tap" if ability.tap else None)  # -- mana riders (wave 5A) -- tapped for mana (106.12a)
    if index is not None:
        return after_mana_ability(plan, card, index, ability, who, source_object=oid, then=then, option=option,
            mana_context={'activation_payment': PaymentRecord(card=card.id, controller=who,
                mana_spent=dict(input_payment.spent) if input_payment else {},
                mana_tags=input_payment.tags if input_payment else [],
                mana_riders=mana_units.ability_riders(input_payment.riders) if input_payment else [],
                activation_cost_has_x='{X}' in ability.extra_cost, activation_cost_has_tap=ability.tap,
                activation_life_paid=(extra.life if extra else 0) + max(0, (input_payment.life-input_payment.auxiliary_life) if input_payment else 0)).model_dump(mode='json')})
    return True


# -- refused copy/mana (wave 3R3) -- a mana ability whose cost chooses objects (Ashnod's Altar: "Sacrifice a
# creature: Add {C}{C}."). 605.3a / 602.2b → 601.2h: the player chooses the objects as the cost is paid (a private
# decision, app/rules/cost_payment.py; none chosen cancels), the costs are paid all at once, then the ability
# resolves at once (605.3a: no stack) — a color to choose is chosen then, after the costs (resume "paid").
def _activate_choosing(plan: Plan, card: CardInstance, ch: Characteristics, parsed: M.ManaAbility,
                       a: A.ActivateAbility) -> None:
    from app.rules import costs as C
    from app.rules import removed_mana

    limits = restrictions.parse(_own_text(_find_ability(ch, a.ability).text, ch.name)) or []
    if why := restrictions.problem(plan.state, plan.actor, card, a.ability, limits, plan, ch.name):
        raise ActionError(why)
    cost = parse_ability_cost(parsed.extra_cost, card_name=ch.name)
    if ability_mana_cost(cost).x and a.x_value is None:
        raise ActionError('Choose a value for X')
    input_cost = mana_activation_cost(plan.state, card, ch, parsed, plan.info, x=a.x_value)
    cost = replace(cost, mana=input_cost.text() if not input_cost.is_free else '', mana_allocation=input_cost.allocation)
    xcost = (parsed.count or "").startswith("xcost:")
    sacrificed_count = parsed.count == "paid_sacrifice_count"
    if sacrificed_count and a.x_value is None:
        raise ActionError("Choose a value for X")
    if xcost and (a.x_value is None or a.x_value < 1):
        raise ActionError(f"Say what X is to activate {ch.name} (it taps X permanents and adds X mana)")
    problem = cost_payment.problem(plan, cost, card, plan.actor, a.x_value)
    if problem is not None:
        raise ActionError(problem)
    objects = cost_payment.choose(plan, a, cost, card, ch.name or "It")
    if objects is None:
        return  # (the payer's choice is pending; its resume runs this intent again with it)
    options = removed_mana.x_options(parsed.count or "", a.x_value or 0) if xcost else parsed.options
    if parsed.count == "sacrificed_mv":  # -- activated sweep (wave 17B) -- the mana value of what the cost sacrifices (608.2h)
        sacrificed = [c for i, comp in cost.choices if comp.kind == C.SACRIFICE for c in objects.get(i, [])]
        options = (parsed.options[0] * int(sum(plan.ch(plan.state.cards[c]).mana_value for c in sacrificed)),)
    if sacrificed_count:
        options = tuple(o * (a.x_value or 0) for o in options) if a.x_value else ((),)
    option: tuple[str, ...] | None = () if parsed.native_body else options[0] if len(options) == 1 else None
    if option is None and a.mana_choice is not None:
        option = next((o for o in options if o and all(symbol == a.mana_choice for symbol in o)), None)
        if option is None:
            raise ActionError(f"{ch.name} can't add {{{a.mana_choice}}}")
    if parsed.count == "exiled_mv_plus_one":
        # 608.2h: "the exiled creature" uses its battlefield characteristics,
        # including copied mana costs and face-down mana value, before paying.
        exiled = [c for i, comp in cost.choices if comp.kind == C.EXILE for c in objects.get(i, [])]
        amount = 1 + int(sum(plan.ch(plan.state.cards[c]).mana_value for c in exiled))
        options = tuple(o * amount for o in options)
        if option is not None:
            option *= amount
    from app.rules import mana_units

    mana_context: dict[str, Any] = {"source_card": card.id, "source_object": plan.oid(card), "only": parsed.spend_only,
                    "riders": mana_units.rider_specs(parsed, ch.name), "note": parsed.spend_text, "tap": parsed.tap, "x": a.x_value,
                    "generic_allowed": parsed.generic_allowed, "option_index": 0 if len(options) == 1 else None}
    data = _ChosenManaPayment(card, ch, parsed, a.ability, cost, objects, options, option, mana_context)
    if cost.mana:
        mana_cost = ability_mana_cost(cost)
        if payment_mode(plan, plan.actor) == "self" and not pool_covers(plan.state, plan.actor, mana_cost,
                        purpose=Purpose(ability_of=ch, player=plan.actor, selected_cost_has_x='{X}' in (parsed.extra_cost or '')), info=plan.info):
            raise ActionError(f"Add {mana_cost.text()} to your mana pool first to activate {ch.name}")
        from app.rules import payment_continuations as pc

        after = pc.continuation(plan, "chosen_mana_paid", data)
        pay_then(plan, plan.actor, mana_cost, f"paid {cost.mana} to activate {ch.name}", then=after,
                 sources=[] if payment_mode(plan, plan.actor) == "self" else None,
                 exclude=cost_payment.excluded(cost, card, objects),
                 purpose=Purpose(ability_of=ch, player=plan.actor, selected_cost_has_x='{X}' in (parsed.extra_cost or '')))
        return
    _chosen_mana_paid(plan, data, None)


@dataclass
class _ChosenManaPayment:
    source: CardInstance
    ch: Characteristics
    parsed: M.ManaAbility
    index: int
    cost: AbilityCost
    objects: dict[int, list[str]]
    options: tuple[tuple[str, ...], ...]
    option: tuple[str, ...] | None
    mana_context: dict[str, Any]


def _chosen_mana_paid(plan: Plan, data: _ChosenManaPayment, payment: M.Payment | None) -> None:
    card = plan.state.cards.get(data.source.id) or data.source
    ch = data.ch
    parsed = data.parsed
    index = data.index
    cost = data.cost
    objects = data.objects
    options = data.options
    option = data.option
    mana_context = data.mana_context
    from app.rules import mana_units
    from app.rules import payment_continuations as pc

    input_record = PaymentRecord(card=card.id, controller=plan.actor,
        mana_spent=dict(payment.spent) if payment else {}, mana_tags=payment.tags if payment else [],
        mana_riders=mana_units.ability_riders(payment.riders) if payment else [],
        snow_spent=dict(payment.snow_spent) if payment else {},
        mana_sources=payment.sources if payment else [], activation_cost_has_x='{X}' in parsed.extra_cost, activation_cost_has_tap=parsed.tap,
        activation_life_paid=cost.life + max(0, (payment.life-payment.auxiliary_life) if payment else 0))
    mana_context['activation_payment'] = input_record.model_dump(mode='json')
    source_snapshot = card.model_dump(mode="json")
    mana_context["source_snapshot"] = source_snapshot
    record = PaymentRecord(card=card.id, controller=plan.actor)
    who = plan.actor  # (wave 24D)
    cost_payment.pay(plan, cost, card, objects, record)
    for kind, n in cost.remove_counters:
        plan.do({"type": "counter", "card_ids": [card.id], "kind": kind, "delta": -n}, actor=who)
    mana_context["nonmana_cost_paid"] = True
    if parsed.tap or parsed.sacrifice_self or cost.life:
        plan.do({"type": "rules_mana", "player": who, "tap": [card.id] if parsed.tap else [],
                 "sacrifice": [card.id] if parsed.sacrifice_self else [], "delta": {}, "life": 0,
                 "label": f"paid to activate {ch.name}"}, actor=who)
        if cost.life:  # -- life modifiers (wave 28B) -- 119.4 / 118.11
            from app.rules import replace as _replace_life

            _replace_life.lose_life(plan, [(who, cost.life)], actor=who)
    if option is None:
        decide(plan, player=plan.actor, kind="choose_one", prompt=f"Which mana should {ch.name} add?",
               options=[DecisionOption(id=str(i), label=M.symbols(_count(o))) for i, o in enumerate(options)],
               resume={"step": "mana_ability", "card": card.id, "ability": index, "paid": True,
                       "options": [list(o) for o in options], "oid": mana_context["source_object"], "who": who, "mana_context": mana_context, "ability_snapshot": pc.ability_data(parsed), "source_snapshot": source_snapshot}, source=card)
        return
    _add_paid_mana(plan, card, parsed, option, index, mana_context["source_object"], who, mana_context)


def _add_paid_mana(plan: Plan, card: CardInstance, ability: M.ManaAbility, option: tuple[str, ...], index: int,
                   oid: str | None, who: str | None = None, mana_context: dict[str, Any] | None = None, *, option_index: int | None = None) -> None:
    """The mana of an ability whose costs are paid (605.3a), then its riders (as ``produce``)."""
    from app.rules import mana_units

    mana = _count(option)
    who = who or card.controller
    if ability.native_body:
        after = _mana_terminal(plan, nested=plan.rules.payment_outer is not None)
        after_mana_ability(plan, card, index, ability, who, source_object=oid, then=after,
                           option=option, mana_context=mana_context)
        return
    if mana_context is not None:
        added = mana_units.from_context(plan, mana_context, mana)
        for unit in added.get("add_units", []):
            unit.update(only=mana_context.get("only"), riders=mana_context.get("riders", []), note=mana_context.get("note", ""),
                        generic_allowed=mana_context.get('generic_allowed', True))
        added = mana_units.with_profile(ability, option, added, option_index=option_index if option_index is not None else mana_context.get('option_index'))
    else:
        added = mana_units.added(plan, card, ability, mana, option=option, option_index=option_index)
    plan.do({"type": "rules_mana", "player": who, "tap": [], "sacrifice": [], **added,
             "life": 0, "label": f"added {M.symbols(mana)}"[:200]}, actor=plan.actor)
    if mana:
        emit(plan.state, "mana_added", object_id=oid, card=card.id, player=who, amount=sum(mana.values()),
             counter="tap" if (mana_context.get("tap") if mana_context is not None else ability.tap) else None)  # -- mana riders (wave 5A) -- tapped for mana (106.12a)
    from app.rules import replace as replacements_

    after = _mana_terminal(plan, nested=plan.rules.payment_outer is not None)
    if after_mana_ability(plan, card, index, ability, who, source_object=oid, then=after, option=option, mana_context=mana_context):
        replacements_.run_then(plan, after)


def _resume_paid_mana(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import payment_continuations as pc

    card = plan.state.cards.get(d.resume["card"])
    if card is None and d.resume.get("source_snapshot") is not None:
        card = CardInstance.model_validate(d.resume["source_snapshot"])
    options = [tuple(o) for o in d.resume["options"]]
    k = int(chosen[0]) if chosen and chosen[0].isdigit() else -1
    if card is None or not 0 <= k < len(options):
        raise ActionError("Choose one of the offered mana")
    if d.resume.get("ability_snapshot") is not None:
        parsed = pc.ability_of(d.resume["ability_snapshot"])
    else:  # Original producer choices cannot be rebuilt from a later physical card.
        raise ActionError('This saved mana ability has unknown producer choices; resolve it manually with the table tools')
    _add_paid_mana(plan, card, parsed, options[k], int(d.resume["ability"]), d.resume.get("oid"), d.resume.get("who"), d.resume.get("mana_context"), option_index=k)
# -- end refused copy/mana (wave 3R3) --


def resume_mana_ability(plan: Plan, d: Any, chosen: list[str]) -> None:
    if d.resume.get("paid"):  # -- refused copy/mana (wave 3R3): the costs are paid; the mana is added --
        _resume_paid_mana(plan, d, chosen)
        return
    card = plan.state.cards.get(d.resume["card"])
    if card is None:
        return
    index = int(d.resume["ability"])
    parsed = dict(mana_abilities(plan.state, card, plan.info)).get(index)
    if parsed is None or (parsed.tap and not can_use_tap_abilities(plan.state, card, plan.ch(card), plan.info)):
        raise ActionError("That mana ability can't be activated any more")
    _manual_produce(plan, card, parsed, parsed.options[int(chosen[0])], index, option_index=int(chosen[0]))
    plan.rules.priority = plan.actor
    plan.rules.passed = []


# -- responding -------------------------------------------------------------------------
def has_responses(state: GameState, player: str, info: CardInfo) -> bool:
    """Could ``player`` do anything at instant speed right now? (For Arena-style auto-passing.)"""
    from app.rules import required_keyword79, required_mutate75
    from app.rules.pooled_casting_authorities71 import external_candidates

    candidates = [cid for key in (zone_key(player, "hand"), zone_key(player, "command"), zone_key(player, "graveyard"),
                                 zone_key(player, "exile"), zone_key(player, "foretell"))
                  for cid in state.zones.get(key, [])]
    candidates += external_candidates(state, player, info)
    for cid in candidates:
        card = state.cards[cid]
        ch = chars.of(card, info)
        if required_mutate75.candidate(state, player, card, ch) or required_keyword79.kind(state, player, card, ch) is not None:
            for option in alt_castable(state, player, card, info, check_priority=False):
                selected_grant = cast_grant(state, player, card, ch, info, alternative_key=option['id'])
                if selected_grant is not None and selected_grant.flash:
                    return True  # Timing-only grants must accompany this selected zone authority.
        if ("Instant" in ch.types or ch.has_flash or _flash_granted(state, player, card, ch, info) or flash_if(ch) is not None) \
                and (castable(state, player, card, info, check_priority=False)
                     or free_castable(state, player, card, info, check_priority=False)
                     or ((required_mutate75.candidate(state, player, card, ch) or required_keyword79.kind(state, player, card, ch) is not None)
                         and alt_castable(state, player, card, info, check_priority=False))):
            return True
        if any(g.flash and g.flash_requires_free for g in permissions.grants(state, player, card, ch, info, verb="cast")) and free_castable(
                state, player, card, info, check_priority=False):
            return True
        # -- cost changers (wave 4I) -- an instant castable only for an alternative cost (Force of Will with no mana
        # open) is a response too: never auto-passed over
        if ("Instant" in ch.types or ch.has_flash or "sneak" in ch.keywords) \
                and alt_castable(state, player, card, info, check_priority=False):  # (-- keywords (wave 30I) -- sneak: 702.190a)
            return True
    return bool(activatable(state, player, info, check_priority=False)) or special_action(state, player, info, instant=True)  # (wave 50B: 116.2b, c: any time, so a response too)


def _flash_granted(state: GameState, player: str, card: CardInstance, ch: Characteristics, info: CardInfo) -> bool:
    """"You may cast creature spells as though they had flash" (601.3b) applies to this card."""
    if ch.is_land or not ch.types:
        return False
    grant = cast_grant(state, player, card, ch, info)
    return grant is not None and grant.flash


def special_action(state: GameState, player: str, info: CardInfo, *, instant: bool = False) -> bool:
    """-- special actions (wave 50B) -- 116.2: could ``player`` take a special action now that isn't a land, a cast or an ability, and pay for it: turn a
    face-down permanent up (116.2b: any time they have priority), end an effect of theirs that lets them (a Licid, 116.2c: likewise), unlock a door of a Room
    (116.2m) or pay {3} for the companion (116.2g): those two in their main phase with the stack empty (``instant``: only the first two, a response).
    For the auto-pass (``can_act``, ``has_responses``): a player who can must not be passed over. A morph cost that isn't mana is counted without checking it can be paid (a stop too many,
    never one too few; ponytail: the hint of suspend, foretell and plot, 116.2f, h, k, isn't read)."""
    from app.rules import deferred_payment82, licids
    from app.rules.copying import room_printing

    if any(can_pay(state, player, M.parse_cost(w.cost), info, purpose=Purpose()) for w in deferred_payment82.active(state, player)):
        return True
    r = state.rules
    main = not instant and state.turn.active_player == player and state.turn.phase in MAIN_PHASES and not state.zones.get(STACK)
    ends = r is not None and any(x.end_cost for x in r.effects)
    for cid in state.zones.get(zone_key(player, "battlefield"), []):
        card = state.cards[cid]
        if card.controller != player:
            continue
        if card.face_down:
            ways = face_up_ways(card, chars.of(card.model_copy(update={"face_down": False}), info), state=state, info=info)
            if any(not cost.startswith("{") or can_pay(state, player, M.parse_cost(cost), info, purpose=Purpose(special="turn_up"))
                   for cost, _ in ways.values()):
                return True
            continue
        if ends and r is not None and (found := licids.ending(state, card, player)) and found[0].end_cost \
                and can_pay(state, player, M.parse_cost(found[0].end_cost), info, purpose=Purpose()):
            return True
        if main and r is not None:  # (a Room, or a copy of one: the printing whose halves it has, 709.5b)
            oid = r.object_id(card.id)
            data = info.get(room_printing(r, card, oid))
            if data is not None and chars.room(data):
                for door in (1, 2):
                    if door not in r.unlocked.get(oid, []) and can_pay(
                            state, player, M.parse_cost((half := chars.half_from_data(data, door - 1)).mana_cost), info, purpose=Purpose(ability_of=half, special="unlock")):
                        return True
    if main:
        for cid in state.zones.get(zone_key(player, "companion"), []):
            card = state.cards[cid]
            if card.owner == player and any("companion" in ab.keywords for ab in chars.of(card, info).abilities) \
                    and companion_problem(state, player, card, info) is None and can_pay(state, player, M.parse_cost("{3}"), info, purpose=Purpose()):
                return True
    return False


def can_act(state: GameState, player: str, info: CardInfo) -> bool:
    """Could ``player`` do anything at all right now (a land, a spell, an ability, a special action)?"""
    from app.rules.engine import land_play_problem  # engine imports this module

    for key in (zone_key(player, "hand"), zone_key(player, "command"), zone_key(player, "graveyard")):
        for cid in state.zones.get(key, []):
            card = state.cards[cid]
            if castable(state, player, card, info, check_priority=False):
                return True
            if key.endswith(":hand") and land_play_problem(state, player, card, chars.of(card, info), check_priority=False,
                                                                 info=info) is None:  # (info: wave 4J, additional land plays)
                return True
    return bool(activatable(state, player, info, check_priority=False)) or special_action(state, player, info)  # (wave 50B: 116.2b, c, g, m)


# Persistent payment stages are registered on import, including after loading a saved decision.
from app.rules import payment_continuations as _pc  # noqa: E402

_pc.register("payment_filter_next", _FilterPayment, _filter_next)
_pc.register("payment_filter_result", _FilterResult, _filter_result)

_pc.register("production_paid", _Production, _production_paid)

_pc.register("mana_done", _ManaDone, _mana_done)

_pc.register("chosen_mana_paid", _ChosenManaPayment, _chosen_mana_paid)

_pc.register("spell_mana_paid", _SpellPayment, _spell_mana_paid)
_pc.register("x_allocation_paid", _XAllocation, _x_allocation_paid)

_pc.register("cast_payment", _CastPayment, _cast_payment)
_pc.register("post_cast", _PostCast, _post_cast)

_pc.register("post_free_cast", _PostFreeCast, _post_free_cast)

_pc.register("post_activation", _PostActivation, _post_activation)
_pc.register("activation_announced", _PostActivation, _activation_announced)

_pc.register("sequential_mana_next", _SequentialPayment, _sequential_next)
_pc.register("sequential_mana_result", _SequentialPayment, _sequential_result)

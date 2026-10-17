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
from dataclasses import dataclass, replace
from typing import Any

from app.game import actions as A
from app.game.errors import ActionError
from app.game.rules_state import (
    CostContribution,
    DecisionOption,
    PaymentRecord,
    Permission,
    StackEntry,
    TargetRef,
    TurnCount,
    cancelable,
    emit,
)
from app.game.state import ALL, STACK, CardInstance, GameState, zone_key
from app.rules import (
    attachments,
    cost_payment,
    costs,
    delayed,  # -- as long as (wave 37A) --
    graveyard_keywords,
    history,
    merged,  # -- merged permanents (wave 18D) --
    ninjutsu,
    per_opponent,  # -- per-opponent targets (wave 23A) --
    permissions,
    read_pass,
    restrictions,
    scripts,
)
from app.rules import characteristics as chars
from app.rules import commander as cmdr
from app.rules import mana as M
from app.rules import payment as P
from app.rules.activation_words import any_player  # -- activation wordings (wave 7B) --
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
        c.kind in (C.MANA, C.TAP, C.PAY_LIFE, C.EXERT, C.UNTAP, C.FORAGE, C.DISCARD_HAND)  # (wave 17B: exert, {Q}, forage: paid by hand; 26C: discard your hand)
        or ((not c.activation_only or (c.x and c.kind == C.TAP_OTHER)) and (  # (X: Hazel of the Rootbloom)
            (c.kind in (C.SACRIFICE, C.REMOVE_COUNTER) and c.selector is None)
            or (c.selector is not None and c.kind in (C.SACRIFICE, C.DISCARD, C.TAP_OTHER, C.EXILE_FROM_GRAVEYARD)
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
                parsed = M.parse_mana_ability(ab.text, commander_identity(state, p, info))  # (wave 19E: Command Tower: its controller's identity)
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
    if ab.instead_if and ab.instead_if[0][:1] == ("@counter",):  # -- opening hand (wave 18C) -- the source's own counter (122.1)
        return ab.instead if card.counters.get(ab.instead_if[0][1], 0) > 0 else ab.options
    if ab.instead_if and ab.instead_if[0][:1] in (("@count",), ("@power",)):  # -- kicked / instead (wave 4G) --
        return ab.instead if _controls_for_instead(state, card.controller, ab.instead_if[0], info) else ab.options
    if ab.instead_if and ab.instead_if[0][:1] == ("@named",):  # -- named permanents (wave 35C) -- Tower Worker: a creature with each name
        return ab.instead if all(_controls_named(state, card.controller, need[1], info) for need in ab.instead_if) else ab.options
    if ab.instead_if and all(_controls_subtypes(state, card.controller, need, info) for need in ab.instead_if):
        return ab.instead  # -- refused copy/mana (wave 3R3): Urza's Tower with the Mine and the Power-Plant --
    from app.rules import removed_mana  # -- if you do (wave 6F) -- one option per number removed

    if (ab.count or "").startswith("xcost:") or ab.count == "sacrificed_mv":
        return ab.options  # (wave 17B: the mana depends on the X announced as it's activated: _activate_choosing)
    if (removed := removed_mana.parts(ab.count)) is not None:
        return removed_mana.options(card.counters.get(removed[0], 0), ab.count or "", ab.options[0])
    if ab.count == "devotion":  # -- refused copy/mana (wave 3R3): Nykthos, per chosen color (700.5) --
        found = [opt * n for opt in ab.options if (n := _devotion(state, card.controller, opt[0], info)) > 0]
        return tuple(found)
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
        elif opt == ("OWN_COLORS",):  # -- counters (wave 44C) -- "one mana of any of this creature's colors" (Katilda): its colors now (613), none when it is colorless (106.1b: no mana)
            from app.rules.layers import derive

            own = derive(state, card, chars.of(card, info), info).colors
            out += [(m,) for m in M.COLORS if m in own]
        elif opt == ("LANDS",):
            out += [(m,) for m in M.ALL_MANA if m in _land_mana(state, [card.controller], info, skip=card.id)]
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
    from app.rules.layers import derive

    total = 0
    for cid in state.zones.get(zone_key(player, "battlefield"), []):
        c = state.cards[cid]
        if c.controller != player:
            continue
        for sym in re.findall(r"\{([^}]+)\}", derive(state, c, chars.of(c, info), info).mana_cost or ""):
            if color in sym.split("/"):
                total += 1
    return total


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
        parsed = M.parse_mana_ability(ab.text, identity)
        if parsed is None or parsed.from_hand:  # (from_hand: only from the hand, wave 5A — mana_riders.activate_from_hand)
            continue
        if parsed.spend_only is not None and parsed.spend_only.startswith("q:") and '"chosen": true' in parsed.spend_only:
            # -- refused copy/mana (wave 3R3) -- "a creature spell of the chosen type": the type chosen as it entered
            chosen = _chosen_creature_type(card)
            if chosen is None:
                continue
            parsed = replace(parsed, spend_only=_with_chosen_type(parsed.spend_only, chosen))
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
                    any(card.counters.get(k, 0) < n for k, n in extra.remove_counters) or \
                    state.players[card.controller].resources.get("energy", 0) < energy:
                continue
        options = _resolve_options(state, card, parsed, info)
        if options:
            out.append((ab.index, replace(parsed, options=options)))
    # -- attached events (wave 4L) -- "Whenever enchanted land is tapped for mana"
    from app.rules import attached_mana, mana_replace, tap_mana

    out = mana_replace.extend(state, card, info, out)  # -- mana replacements (wave 9C) -- 106.12b: first, then the triggers' extras
    out = tap_mana.extend(state, card, info, out)  # -- mana riders (wave 5A) -- "Whenever you tap a land for mana, …"
    return attached_mana.extend(state, card, info, ch.is_land, out)


# -- review (wave 4R) -- 602.2b → 601.2f: "Activated abilities of … cost {N} more / less to activate" (Gloom, Training
# Grounds) apply to mana abilities too (605.3a: they're activated abilities). The engine doesn't pay such a changed
# cost for a mana ability: one whose cost a modifier changes isn't tapped automatically, and is activated by hand.
def ability_taxes(state: GameState, info: CardInfo) -> bool:
    """Is any "activated abilities … cost more / less" static on the battlefield (a cheap scan of printed text)?"""
    for cid in (c for z, ids in state.zones.items() if z.endswith(":battlefield") for c in ids):
        card = state.cards[cid]
        if card.face_down:
            continue
        ch = chars.of(card, info)
        if " to activate" in ch.oracle_text and any(d.get("static") == "ability_cost_modifier"
                                                    for d in scripts.definitions(ch).values()):
            return True
    return False


def mana_ability_taxed(state: GameState, card: CardInstance, ch: Characteristics, ab: M.ManaAbility, info: CardInfo) -> bool:
    """Does a cost modifier change this mana ability's cost (``ability_taxes`` checked first by the caller)?"""
    mana = parse_ability_cost(ab.extra_cost, card_name=ch.name).mana if ab.extra_cost else ""
    return permissions.ability_mana(state, card.controller, card, ch, mana, info) != mana
# -- end review (wave 4R) --


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
    if kind == "colorless_eldrazi":  # (wave 3M) Eldrazi Temple
        return (spell is not None and "Eldrazi" in spell.subtypes and not spell.colors) or \
            (source is not None and "Eldrazi" in source.subtypes and not source.colors)
    if kind == "not_nonartifact_spell":  # (wave 3M) Powerstone: any ability, or an artifact spell
        return spell is None or "Artifact" in spell.types
    if kind.startswith("q:"):  # -- refused copy/mana (wave 3R3): the general restriction (mana.parse_spend) --
        import json

        spec = json.loads(kind[2:])
        if spec.get("cost_x"):  # -- mana provenance (wave 18B) -- "only on costs that contain {X}"
            return purpose.cost_x
        if purpose.special and purpose.special in (spec.get("special") or ()):  # -- mana for special abilities (wave 19E) --
            return True
        side, ch = ("cast", spell) if spell is not None else ("ability", source)
        allowed = spec.get(side)
        if ch is None or allowed is None or any(a.get("chosen") for a in allowed if isinstance(allowed, list)):
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
    taxes = ability_taxes(state, info)  # -- review (wave 4R) --
    for cid in state.zones.get(zone_key(player, "battlefield"), []):
        card = state.cards[cid]
        if card.controller != player:
            continue
        ch = chars.of(card, info)
        usable_tap = can_use_tap_abilities(state, card, ch, info)
        # (wave 3E) an ability paying energy is activated by hand only: several sources sharing one
        # energy total aren't something the solver can split (118.3: no partial payment)
        abilities = [(i, ab) for i, ab in mana_abilities(state, card, info)
                     if (usable_tap or not ab.tap) and spend_allowed(ab.spend_only, purpose)
                     and not ab.chooses and ab.self_counter is None  # (wave 3R3: the payer's choice: by hand)
                     and not (ab.count or "").startswith("removed:")  # -- if you do (wave 6F) -- how many: by hand
                     and not (ab.extra_cost and parse_ability_cost(ab.extra_cost, card_name=ch.name).energy)
                     and not (taxes and mana_ability_taxed(state, card, ch, ab, info))]  # (review 4R: by hand)
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
                                abilities=tuple(pairs[o][0] for o in opts), snow="Snow" in ch.supertypes))  # (wave 7E)
        for i, ab in abilities:
            mana_cost = parse_ability_cost(ab.extra_cost, card_name=ch.name).mana
            if mana_cost and ab.tap and not ab.sacrifice_self:
                out.append(M.Source(card.id, ab.options, rank=rank + 3, abilities=(i,) * len(ab.options),
                                    activation=M.parse_cost(mana_cost), snow="Snow" in ch.supertypes))  # (wave 7E)
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
    out = list(sources)
    by_card = {s.card_id: k for k, s in enumerate(out)}
    for h in available_helpers(state, player, info, spell, spell_card):
        opts = tuple((c,) for c in sorted(h.colors)) + ((P.GENERIC,),) if h.kind == "convoke" else ((P.GENERIC,),)
        idx = HELPER_ABILITY[h.kind]
        if h.card in by_card:
            src = out[by_card[h.card]]
            extra = tuple(o for o in opts if o not in src.options)
            abilities = src.abilities or (0,) * len(src.options)
            out[by_card[h.card]] = M.Source(h.card, src.options + extra, sacrifice=src.sacrifice, rank=src.rank,
                                            preferred=src.preferred, abilities=abilities + (idx,) * len(extra),
                                            activation=src.activation, snow=src.snow)
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


def choose_target(plan: Plan, a: A.CastSpell | A.ActivateAbility, definition: dict[str, Any] | None,
                  what: str, *, exclude: tuple[str, ...] = ()) -> list[TargetRef] | None:
    """The target of an automated spell or ability: validated if given, else asked (privately).
    Returns the chosen targets, or None while waiting for the choice."""
    spec = definition.get("target") if definition else None
    if not spec:
        return []
    legal = [t for t in legal_targets(plan, spec["what"], plan.actor, source_of(plan, a.card_id, isinstance(a, A.CastSpell)), a.card_id)
             if t not in exclude]  # (wave 49C: a spell's targeting, 115.2)
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
    plan.x_choice = getattr(a, "x_value", None)  # -- control (wave 3K) -- "creature with mana value X or less": the X announced
    if not definition or not definition.get("targets"):
        chosen = choose_target(plan, a, definition, what, exclude=exclude)
        return None if chosen is None else ChosenTargets(flat=chosen)
    specs = scripts.target_groups(definition)
    if isinstance(a, A.CastSpell):  # -- kicked / instead (wave 4G) -- 601.2c / 702.33g: targets tied to the kicker
        from app.rules import kicked_instead

        specs = kicked_instead.applicable(specs, a.kicker or int(a.awaken) or int(f"{a.card_id}:gift" in a.optional_costs) or int(f"{a.card_id}:bargain" in a.optional_costs))  # (awaken: wave 16B; bargain: 30E;
        # gift: wave 23D, 702.174m: the targets only a promised spell chooses)
    found = choose_groups(plan, specs, plan.actor, source_of(plan, a.card_id, isinstance(a, A.CastSpell)), a.card_id, list(a.targets),  # (review 41: 115.2)
                          list(a.target_counts), list(a.division), a.x_value, what, exclude)
    if found.ask is not None:
        ask_targets(plan, plan.actor, found, specs, what, _announcing(plan, "cast_group", a, counts=found.counts))
        return None
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
        out += [{**g, "graveyard_of": g["graveyard_of"] + base} if g.get("graveyard_of") is not None else g
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
    return out


def choose_modes(plan: Plan, a: A.CastSpell | A.ActivateAbility, definition: dict[str, Any], what: str,
                 *, exclude: tuple[int, ...] = ()) -> list[int] | None:
    """700.2a / 601.2b: the modes of a modal spell (or activated ability: 602.2b), validated if given,
    else asked. A mode whose target can't be chosen can't be chosen (700.2a). ``exclude``: modes that
    can't be chosen either ("choose one that hasn't been chosen"). Returns None while waiting."""
    modal, modes = definition["modal"], definition["modes"]
    lo, hi, repeat = modal["min"], modal["max"], modal["repeat"]
    allowed = choosable_modes(plan, definition, a.card_id, exclude, isinstance(a, A.CastSpell))
    if (inst := modal.get("instead")) is not None and _instead_holds(plan, a, inst["cond"]):
        # -- modal frames (wave 33B) -- 700.2a, 601.2b: "If [condition] as you cast this spell, [you may] choose both instead." — judged as the
        # modes are chosen; a "both" the table can't give (a mode with no legal target, 700.2a) is not cast that way
        lo, hi = inst["min"], inst["max"]
        if len(allowed) < lo:
            raise ActionError(f"{what} can't have {lo} modes chosen (a mode has no legal target)")
    if a.modes:
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


def choosable_modes(plan: Plan, definition: dict[str, Any], card_id: str | None, exclude: tuple[int, ...] = (), spell: bool = False) -> list[int]:
    """700.2a: the modes ``plan.actor`` can choose for this spell / ability now (each target it requires can be chosen; ``spell``: 115.2)."""
    src = source_of(plan, card_id, spell)
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
    src = source_of(plan, a.card_id, isinstance(a, A.CastSpell))
    out: list[list[TargetRef]] = [[] for _ in specs]
    for n, k in enumerate(need):
        spec = specs[k]
        assert spec is not None
        legal = legal_targets(plan, spec["what"], plan.actor, src, a.card_id)
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
    # -- activated sweep (wave 17B) -- where the spell is cast from, by whom, and whether kicked ("Spend this mana only to cast
    # kicked spells", "…spells from exile"; 601.2h: the cost is paid with these locked in, 601.2a-b)
    zone: str | None = None
    player: str | None = None
    kicked: bool = False
    # -- mana provenance (wave 18B) -- does the player own the spell ("spells you don't own", Thieving Varmint)
    own: bool = True
    # -- mana provenance (wave 18B) -- the cost being paid contains {X} ("Spend this mana only on costs that contain {X}", Rosheen Meanderer)
    cost_x: bool = False
    # -- mana for special abilities (wave 19E) -- what else the mana pays for: "equip", "power_up" (an ability of that kind: ``ability_of``
    # is its source), "turn_up" (the cost to turn a permanent face up, 116.2b), "foretell" (116.2h)
    special: str | None = None


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
                 sources: list[str] | None = None, exclude: tuple[str, ...] = (), purpose: Purpose | None = None,
                 reserve: int = 0) -> M.Payment:
    """How to pay ``cost``: with exactly ``sources`` when given (MANUAL PAY), else automatically,
    PREFER sources first and SAVE sources only when there is no other way. Pool units that may pay for ``purpose`` (restricted or
    remembered mana, app/rules/mana_units.py) are spent like pool mana: ``Payment.slots`` names them ("unit:<id>"), ``tapped`` doesn't."""
    payment = _find_payment(state, player, life_for_mana(state, player, info, cost), info, sources=sources, exclude=exclude,
                            purpose=purpose, reserve=reserve)
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
            payment = _solve_with_filters(cost, pool, chosen + units, chosen_filters, life)
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
        return _solve_with_filters(cost, pool, normal + units, normal_filters, life)
    except M.ManaError:
        pass
    try:
        return _solve_with_filters(cost, pool, marked + units, filters, life)  # SAVE sources only when nothing else works
    except M.ManaError as exc:
        raise ActionError(f"{exc}. Tap mana yourself first, or use the table tools.") from exc


def mana_ability_extras(plan: Plan, card: CardInstance, index: int) -> tuple[int, list[tuple[str, int]]]:
    """Life to pay and counters to remove for using mana ability ``index`` (besides tapping)."""
    ability = dict(mana_abilities(plan.state, card, plan.info)).get(index)
    if ability is None or not ability.extra_cost:
        return 0, []
    extra = parse_ability_cost(ability.extra_cost, card_name=plan.ch(card).name)
    return extra.life, list(extra.remove_counters)


def after_mana_ability(plan: Plan, card: CardInstance, index: int, ability: M.ManaAbility, who: str | None = None) -> None:
    """Riders and bookkeeping once a mana ability was used: "deals 1 damage to you", "Draw a
    card", once-per-turn marks, counters removed as a cost. ``who``: the player who activated it (-- mana riders (wave 24D) -- 603.7e-style:
    a source sacrificed as the cost is back under its owner's control by now, so "you" is read before the cost)."""
    who = who or card.controller
    r = plan.rules
    if ability.once_per_turn:
        r.once_per_turn[f"{r.object_id(card.id)}:{index}"] = plan.state.turn.number
    extra = parse_ability_cost(ability.extra_cost, card_name=plan.ch(card).name) if ability.extra_cost else None
    for kind, n in extra.remove_counters if extra else ():
        plan.do({"type": "counter", "card_ids": [card.id], "kind": kind, "delta": -n}, actor=card.controller)
    if extra is not None and extra.energy:  # (wave 3E: "{T}, Pay {E}: Add one mana of any color", 107.14)
        plan.do({"type": "resource", "player": card.controller, "key": "energy", "delta": -extra.energy}, actor=card.controller)
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


def mana_ability_damage(plan: Plan, card: CardInstance, who: str, n: int) -> None:
    """-- replacements: damage (wave 29C) -- "This land deals 1 damage to you." is damage like any other (120.3): the replacement and
    prevention effects on it (614, 615: Furnace of Rath, Urza's Armor, a "next N damage" shield), then the life that damage makes the player
    lose (120.3a, the life-loss replacements: Bloodletter of Aclazotz) — the damage choke point (``replace.damage_outcome``). A mana ability
    resolves as it is activated and can't pause (605.3a, 605.3b): when two effects both apply and their order matters (616.1) the damage is
    dealt as it is and the log names the effects the players must apply by hand (``left_to_players``) — never skipped without saying."""
    from app.rules import effects as _effects
    from app.rules import replace as _replace

    ch = plan.ch(card)
    oid = plan.oid(card.id)
    ev = {"source_card": card.id, "source_oid": oid, "target": who, "amount": n, "combat": False,
          "src": _replace.source_info(plan, card.id, oid, ch, who), "kw": sorted(ch.keywords & _effects._DAMAGE_KEYWORDS), "lkey": card.id}
    out = _replace.damage_outcome(plan, [ev], answers={}, order=None, ask=False)
    if isinstance(out, _replace.DamageOutcome):
        _replace.do_damage(plan, out, actor=who, combat=False)


def _player_protected(plan: Plan, card: CardInstance, who: str) -> bool:
    """-- player shields (wave 5E) -- does the controller's protection prevent the damage this mana source deals them?"""
    from app.rules import player_shields, source_shields
    from app.rules import replace as replacements

    if player_shields.protected_from(plan, who, plan.ch(card)) is None:
        return False
    ev = {"source_card": card.id, "source_oid": plan.oid(card.id), "target": who, "combat": False,
          "src": replacements.source_info(plan, card.id, plan.oid(card.id), plan.ch(card), who)}
    return source_shields.protection_applies(plan, ev)


def pay(plan: Plan, player: str, cost: M.ManaCost, label: str, *, sources: list[str] | None = None,
        exclude: tuple[str, ...] = (), purpose: Purpose | None = None, life_due: int = 0) -> M.Payment | None:
    """``life_due``: -- phyrexian mana (wave 50B) -- the life announced for Phyrexian symbols (601.2b), paid with the rest; it is already in ``plan.reserved_life``."""
    if cost.is_free and not sources and not life_due:
        return None
    payment = find_payment(plan.state, player, cost, plan.info, sources=sources, exclude=exclude, purpose=purpose,
                           reserve=plan.reserved_life)
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
    oids = {card.id: plan.oid(card) for card, _, _ in extras}  # (wave 5A: the objects as they were tapped)
    from app.rules import mana_units

    pool = mana_units.settle(plan, player, payment)  # -- mana provenance (wave 18B) -- units spent / left over, what the mana was
    plan.do({"type": "rules_mana", "player": player, "tap": payment.tapped, "sacrifice": payment.sacrificed, "life": 0,
             "label": label, **pool}, actor=player)
    if life:  # -- life modifiers (wave 28B) -- 119.4 / 118.11: the life paid is a life loss the replacements may change
        from app.rules import replace as _replace_life

        _replace_life.lose_life(plan, [(player, life)], actor=player)
    for card, index, ability in extras:
        # -- mana riders (wave 5A) -- counter "tap": tapped for mana (106.12a: an ability with {T} in its cost)
        emit(plan.state, "mana_added", object_id=oids[card.id], card=card.id, player=player,
             counter="tap" if ability.tap else None)
        after_mana_ability(plan, card, index, ability, player)
    payment.life = life
    return payment


def _auto_helpers(plan: Plan, cost: M.ManaCost, spell: Characteristics, spell_card: str, purpose: Purpose) -> list[P.Helper]:
    """The engine pays (AUTO/ASK — tests and the sandbox payer): use convoke / improvise / delve
    only when mana alone can't pay, choosing them with the castability solver."""
    state, player = plan.state, plan.actor
    if not helper_kinds(spell, state, player, spell_card, plan.info) or can_pay(state, player, cost, plan.info,
                                                                               purpose=purpose):
        return []
    plain = [s for s in mana_sources(state, player, plan.info, purpose) if s.activation is None]
    try:
        found = M.solve(cost, dict(state.players[player].mana),
                        _helper_sources(state, player, plan.info, spell, spell_card, plain), life=spendable_life(state, player, plan.info))
    except M.ManaError:
        return []
    kinds = {v: k for k, v in HELPER_ABILITY.items()}
    return helpers_for(state, player, plan.info, spell, spell_card,
                       [{"kind": kinds[i], "card": cid} for cid, i in found.used if i < 0])


def pay_spell(plan: Plan, a: A.CastSpell, card: CardInstance, ch: Characteristics, cost: M.ManaCost,
              label: str, *, not_mana: tuple[str, ...] = (), origin: str | None = None) -> PaymentRecord:
    """601.2h: pay a spell's locked-in total cost — the convoke / improvise / delve contributions
    (each paying one symbol, 702.51a / 702.126a / 702.66a) and mana for everything else — all at
    once. Returns how it was paid; contributions are not mana spent."""
    player = plan.actor
    # (wave 17B: origin: before the stack; wave 18B: the spell's mana value with the X it was announced with, 202.3e, and who owns it)
    spell_ch = replace(ch, mana_value=ch.mana_value + (a.x_value or 0) * ch.mana_cost.count("{X}")) if a.x_value else ch
    kick = kicker_cost(ch.abilities) if a.kicker else None  # (an entwined spell isn't kicked: review 18E)
    purpose = Purpose(spell=spell_ch, zone=origin or card.zone, player=player,
                      kicked=bool(a.kicker) and not (kick is not None and kick.entwine), own=card.owner == player,
                      cost_x="{X}" in ch.mana_cost)
    if a.contributions:
        helpers = helpers_for(plan.state, player, plan.info, ch, card.id, [c.model_dump() for c in a.contributions])
    elif a.sources is None and payment_mode(plan, player) != "self":
        helpers = _auto_helpers(plan, cost, ch, card.id, purpose)
    else:
        helpers = []
    if any(h.card in not_mana for h in helpers):  # (wave 3$) an object an additional cost uses can't also help pay
        raise ActionError("A permanent that pays the additional cost can't also convoke / improvise")
    exclude = tuple(h.card for h in helpers) + not_mana

    def covers(rest: M.ManaCost) -> bool:
        if rest.is_free:
            return True
        try:
            find_payment(plan.state, player, rest, plan.info, sources=a.sources, exclude=exclude, purpose=purpose,
                         reserve=plan.reserved_life)
        except ActionError:
            return False
        return True

    assignment = P.assign(cost, helpers, covers) if helpers else []
    if assignment is None:
        raise ActionError(f"Those can't pay {cost.text()}: convoke pays {{1}} or one mana of the creature's color; "
                          "improvise and delve pay only {1}")
    contributions = [CostContribution(kind=h.kind, card=h.card, object_id=plan.oid(h.card),
                                      name=plan.state.cards[h.card].name or "", pays=sym)
                     for h, sym in zip(helpers, assignment, strict=True)]
    tap = [h.card for h in helpers if h.kind != "delve"]
    if tap:
        kinds = " and ".join(dict.fromkeys(h.kind for h in helpers if h.kind != "delve"))
        plan.do({"type": "rules_mana", "player": player, "tap": tap, "sacrifice": [], "delta": {}, "life": 0,
                 "label": f"paid part of {cost.text()} for {ch.name or 'a spell'} with {kinds}"}, actor=player)
    delved = [h.card for h in helpers if h.kind == "delve"]
    if delved:
        plan.do({"type": "move", "card_ids": delved, "to": {"player": player, "zone": "exile"}}, actor=player)
    rest = P.remaining(cost, assignment)
    n_life = len(a.life_symbols or ())  # -- phyrexian mana (wave 50B) -- announced in 601.2b: 2 life each, paid with the rest
    payment = pay(plan, player, rest, label, sources=a.sources, exclude=exclude, purpose=purpose, life_due=2 * n_life)
    from app.rules import mana_units

    return PaymentRecord(card=card.id, controller=player, total_cost=cost.text(),
                         mana_spent=dict(payment.spent) if payment else {}, contributions=contributions,
                         mana_tags=payment.tags if payment else [],
                         mana_riders=mana_units.matching(plan, payment.riders, card, spell_ch, player) if payment else [],
                         life=payment.life if payment else 0,  # (wave 43D: compleated; wave 50B: the symbols announced, else the life the solver took)
                         phyrexian=n_life if a.life_symbols is not None else payment.life // 2 if payment else 0,
                         tapped=list(payment.tapped) if payment else [],
                         sacrificed=list(payment.sacrificed) if payment else [], x=a.x_value)


# -- refused modal/conditional (wave 3R1) --
def _note_cast(plan: Plan, record: PaymentRecord, zone: str) -> None:
    """How a spell was cast, on its payment record: the zone it was cast from ("if you cast it from your hand",
    "if this spell was cast from a graveyard") and whether it was cast during its caster's own main phase
    (addendum: "if you cast this spell during your main phase" — 505.1: a main phase of the caster's turn)."""
    record.cast_from = zone
    if (cast_card := plan.state.cards.get(record.card)) is not None:
        from app.rules import prohibitions

        prohibitions.bind_next_uncounterable(plan, cast_card, record.controller)  # -- most-played cards (wave 43B) -- "The next spell you cast this turn can't be countered." (ponytail: spells cast by hand, outside this path, are bound in engine.py)
    r = plan.rules  # (-- review 30 -- a new spell (400.7): an evoke / dash mark left by an earlier spell of this card that never resolved —
    # bounced or countered back to hand — isn't this one's, 702.74a, 702.109a; this cast marks it again if it pays that cost)
    r.evoked, r.dashed = [c for c in r.evoked if c != record.card], [c for c in r.dashed if c != record.card]
    turn = plan.state.turn
    record.cast_main = turn.active_player == record.controller and turn.phase in ("main1", "main2")
# -- end refused modal/conditional (wave 3R1) --


def record_payment(plan: Plan, card_id: str, record: PaymentRecord) -> None:
    """Keep how the spell was paid, on its stack object (and later the permanent it becomes). A record of an
    object that has just left is kept while its last known information is (wave 3R1: "if you cast it" as an
    intervening "if" is checked again as the ability resolves, 603.4, after the permanent may have left)."""
    r = plan.rules
    r.payments = {k: v for k, v in r.payments.items()
                  if (v.card in plan.state.cards and r.object_id(v.card) == k) or k in r.lki}
    r.payments[plan.oid(card_id)] = record


def payment_step(plan: Plan, a: A.CastSpell | A.ActivateAbility | A.EndEffect, cost: M.ManaCost, what: str, *,  # (-- licids (wave 50A) -- EndEffect)
                 exclude: tuple[str, ...] = (), purpose: Purpose | None = None) -> bool:
    """Before a spell or ability is put on the stack: does the player want to see or choose the
    payment first? Returns True if a decision was opened (the intent then waits for it; nothing
    has moved yet, so CANCEL simply leaves everything where it was)."""
    if a.sources is not None or cost.is_free:
        return False
    mode = payment_mode(plan, plan.actor)
    if mode == "self":  # the player taps their own mana: pay from the pool, or ask them to tap
        probe: dict[str, Any] = {"intent": a.model_dump(mode="json", exclude={"r", "actor", "ts"})}
        helpers = _prompt_helpers(plan, plan.actor, probe) if getattr(a, "contributions", None) else []
        if _covered(plan, plan.actor, cost, helpers, probe) is not None:
            a.sources = []
            return False
        ask_to_tap(plan, cost, what, {"step": "pay_mana", "intent": a.model_dump(mode="json", exclude={"r", "actor", "ts"}),
                                      "exclude": list(exclude), "cost": cost.text(), "what": what})
        return True
    if mode == "auto":
        return False
    payment = find_payment(plan.state, plan.actor, cost, plan.info, exclude=exclude, purpose=purpose,
                           reserve=plan.reserved_life)  # (can it be paid at all?)
    resume: dict[str, Any] = {"step": "payment", "intent": a.model_dump(mode="json", exclude={"r", "actor", "ts"}),
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
    return M.ManaCost(cost.generic, cost.colored + tuple(c for c in rest if "/" not in c),
                      cost.hybrid + tuple(tuple(c.split("/")) for c in rest if "/" in c), (), cost.x, cost.unsupported)


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
            out.append(f"{{{c}/P}}: 2 life")
        else:
            out.append(f"{{{c}/P}}: " + " or ".join(f"{{{x}}}" for x in c.split("/")))
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
            decide(plan, player=plan.actor, kind="choose_one", prompt=f"Pay {cost.text()} for {what}: mana or 2 life for each Phyrexian symbol (601.2b)",
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

    try:
        M.solve(life_for_mana(state, player, info, cost) if info is not None else cost, dict(state.players[player].mana), mana_units.unit_sources(state, player, purpose),
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


def _prompt_spell(plan: Plan, resume: dict[str, Any]) -> tuple[Characteristics | None, str | None]:
    """The spell a "tap your mana" prompt is paying for, if it is casting one (only spells have
    convoke / improvise / delve: never ward, "counter unless its controller pays", or abilities)."""
    intent = resume.get("intent") or {}
    card = plan.state.cards.get(intent.get("card_id") or "") if intent.get("type") == "cast_spell" else None
    if card is None or intent.get("face_down"):
        return None, None
    return chars.as_cast(card, plan.info, intent.get("face")), card.id


def _prompt_helpers(plan: Plan, player: str, resume: dict[str, Any]) -> list[P.Helper]:
    contributions = (resume.get("intent") or {}).get("contributions") or []
    if not contributions:
        return []
    spell, spell_card = _prompt_spell(plan, resume)
    return helpers_for(plan.state, player, plan.info, spell, spell_card, contributions)


def _prompt_purpose(plan: Plan, resume: dict[str, Any]) -> Purpose | None:
    """-- mana provenance (wave 18B) -- what a "tap your mana" prompt pays for, so the pool's restricted mana counts only where it may."""
    intent = resume.get("intent") or {}
    spell, spell_card = _prompt_spell(plan, resume)
    if spell is not None and spell_card is not None:
        return Purpose(spell=spell, zone=plan.state.cards[spell_card].zone, player=plan.actor, kicked=bool(intent.get("kicker")))
    card = plan.state.cards.get(intent.get("card_id") or "") if intent.get("type") == "activate_ability" else None
    return Purpose(ability_of=plan.ch(card)) if card is not None else None


def _covered(plan: Plan, player: str, cost: M.ManaCost, helpers: list[P.Helper],
             resume: dict[str, Any] | None = None) -> list[str] | None:
    """How the committed helpers pay part of ``cost`` so that the mana pool pays the rest, or None."""
    from app.rules import mana_units

    p = plan.state.players[player]
    units = mana_units.unit_sources(plan.state, player, _prompt_purpose(plan, resume) if resume else None)
    covers = P.pool_pays(dict(p.mana), max(0, spendable_life(plan.state, player, plan.info) - plan.reserved_life), units)
    return P.assign(cost, helpers, lambda rest: covers(life_for_mana(plan.state, player, plan.info, rest)))  # (review 18B: K'rrik)


def _tap_display(plan: Plan, player: str, cost: M.ManaCost, what: str, resume: dict[str, Any]) -> dict[str, Any]:
    """The payment panel: the cost, what's been committed to pay it (each with the symbol it pays),
    what mana is still needed, and what can be clicked."""
    helpers = _prompt_helpers(plan, player, resume)
    committed = {h.card for h in helpers}
    exclude = set(resume.get("exclude") or ()) | committed
    sources = list(dict.fromkeys(s.card_id for s in mana_sources(plan.state, player, plan.info)
                                 if s.card_id not in exclude and s.activation is None))
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
    # (wave 29C: every helper is listed — the table clicks a creature / artifact / card only if it is on its list, so a cut list hid some)
    return {"kind": "tap_mana", "cost": cost.text(), "what": what, "sources": sources,
            "convoke": by_kind["convoke"], "improvise": by_kind["improvise"], "delve": by_kind["delve"],
            "committed": sorted(committed), "paid": paid, "mana_due": rest.text() if not rest.is_free else "",
            "remaining": _left_text(P.after_pool(rest, dict(plan.state.players[player].mana))),
            "pool": dict(plan.state.players[player].mana)}


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
           display=display, options=[DecisionOption(id="pay", label="Pay"), DecisionOption(id="cancel", label="Cancel")],
           resume=resume)


def resume_pay_mana(plan: Plan, d: Any, chosen: list[str]) -> None:
    assert d.resume is not None
    if chosen[0] == "cancel":  # nothing committed was tapped or exiled yet (601.2h: no partial payments)
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
    d = plan.rules.decision
    resume = (d.resume or {}) if d is not None else {}
    if d is None or resume.get("step") != "pay_mana":
        if d is not None and d.display is not None:
            d.display = {**d.display, "pool": dict(plan.state.players[d.player].mana)}
        return
    cost = M.parse_cost(resume["cost"])
    if _covered(plan, d.player, cost, _prompt_helpers(plan, d.player, resume), resume) is not None:
        plan.rules.decision = None
        _rerun(plan, d, A.parse_action(resume["intent"]), [])
    else:
        d.display = _tap_display(plan, d.player, cost, resume.get("what", ""), resume)


def _best_option(plan: Plan, options: tuple[tuple[str, ...], ...]) -> tuple[str, ...]:
    """The mana option that helps the pending payment most (the player tapped; this only picks
    which color to add for them)."""
    d = plan.rules.decision
    if d is None or not d.resume or "cost" not in d.resume:
        return options[0]
    cost = M.parse_cost(d.resume["cost"])
    pool = dict(plan.state.players[plan.actor].mana)
    for opt in options:
        trial = dict(pool)
        for m in opt:
            trial[m] = trial.get(m, 0) + 1
        try:
            M.solve(cost, trial, [])
            return opt
        except M.ManaError:
            pass
    needed = set(cost.colored) | {c for h in cost.hybrid for c in h} | {c for p in cost.phyrexian for c in p.split("/")}
    return next((o for o in options if set(o) & needed - set(pool)), next((o for o in options if set(o) & needed), options[0]))


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
    if ((d.resume or {}).get("intent") or {}).get("type") != "declare_attackers":
        return False
    from app.rules import combat

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
    return M.parse_cost(locked) if locked is not None else cost


def _rerun(plan: Plan, d: Any, intent: Any, sources: list[str]) -> None:
    from app.rules.engine import INTENTS  # the engine imports this module

    intent.sources = sources
    plan.rules.priority = d.player
    plan.rules.passed = []
    # -- cost changers (wave 4I) -- 601.2f: the total cost was locked in when the payment was asked for; mana abilities
    # activated meanwhile (a Treasure sacrificed, a creature sacrificed for mana) don't change it
    plan.locked_cost = d.resume.get("cost") if isinstance(d.resume, dict) else None
    try:
        INTENTS[intent.type](plan, intent)
    finally:
        plan.locked_cost = None


def can_pay(state: GameState, player: str, cost: M.ManaCost, info: CardInfo, *, exclude: tuple[str, ...] = (),
            purpose: Purpose | None = None, reserve: int = 0) -> bool:
    everything = [s for s in mana_sources(state, player, info, purpose) if s.card_id not in exclude]
    if purpose is not None and purpose.card is not None \
            and helper_kinds(purpose.spell, state, player, purpose.card, info):  # (a hint: never paid here)
        assert purpose.spell is not None
        everything = _helper_sources(state, player, info, purpose.spell, purpose.card, everything)
    from app.rules import mana_units

    cost = life_for_mana(state, player, info, cost)
    try:
        _solve_with_filters(cost, dict(state.players[player].mana),
                            [s for s in everything if s.activation is None] + mana_units.unit_sources(state, player, purpose),
                            [s for s in everything if s.activation is not None],
                            max(0, spendable_life(state, player, info) - reserve))  # (-- hints (wave 30B) -- 119.4: less the life the spell's other costs pay, as ``_find_payment``'s ``reserve``)
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
    from app.rules import alt_costs

    t = text.strip().rstrip(".")
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
DISGUISE = re.compile(r"^disguise (?P<cost>(?:\{[^}]+\})+)$", re.IGNORECASE)


def disguise_cost(ch: Characteristics) -> str | None:
    """702.168 disguise with a mana cost, from the printed card."""
    return keyword_cost(ch, "disguise", DISGUISE)


def face_down_cast_kind(ch: Characteristics) -> str | None:
    """How a card may be cast face down (702.37c / 702.168b): "morph" (morph, megamorph) or "disguise"."""
    return "morph" if morph_cost(ch) is not None else "disguise" if disguise_cost(ch) is not None else None


def face_up_ways(card: CardInstance, printed: Characteristics) -> dict[str, tuple[str, str]]:
    """The ways its controller may turn this face-down permanent face up, as {way: (cost, kind)}:
    "morph" (702.37e: its morph or megamorph cost; "megamorph" as kind), "disguise" (702.168d), and
    "mana_cost" for a manifested or cloaked permanent (701.40b / 701.58b: a creature card's mana cost
    — not an instant or sorcery card, nor one without a mana cost; 701.40c-d / 701.58c-d: a manifested
    or cloaked card with morph or disguise may use those too). A cost with X isn't automated."""
    ways: dict[str, tuple[str, str]] = {}
    found = morph_cost(printed)
    if found is not None:
        ways["morph"] = (found[1], found[0])
    disguise = disguise_cost(printed)
    if disguise is not None:
        ways["disguise"] = (disguise, "disguise")
    if card.face_down_kind in ("manifest", "cloak") and printed.is_creature and printed.mana_cost:
        ways["mana_cost"] = (printed.mana_cost, "mana_cost")
    return {w: v for w, v in ways.items() if "{X}" not in v[0]}


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


def turned_up(plan: Plan, card: CardInstance) -> None:
    """-- hidden exile (wave 18A) -- the permanent was just turned face up (by the special action or by an effect): its "When ~ is
    turned face up" and the table's "Whenever a permanent you control is turned face up" abilities trigger (702.37e: not
    "enters" abilities, 708.8)."""
    emit(plan.state, "turned_face_up", object_id=plan.oid(card), card=card.id, player=card.controller)
    from app.rules import triggers  # (triggers imports this module)

    face_up = plan.ch(plan.state.cards[card.id])
    if not plan.manual(card):  # "When ~ is turned face up, …"
        for i, d in triggers.abilities(plan, face_up, "turned_face_up_self"):
            triggers._add(plan, controller=card.controller, source_card=card.id, source_object=plan.oid(card),
                          name=face_up.name, index=i, definition=d)


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
    printed = chars.of(card.model_copy(update={"face_down": False}), plan.info)
    ways = face_up_ways(card, printed)
    method = a.method or next((w for w in ("morph", "disguise", "mana_cost") if w in ways), None)
    if method is None or method not in ways:
        raise ActionError("It can't be turned face up that way: turn it face up with the table tools")
    cost_text, kind = ways[method]
    if not cost_text.startswith("{"):  # -- hidden exile (wave 18A) -- a morph cost that isn't mana (702.37e: "pay that cost")
        if not pay_nonmana_cost(plan, a, card, printed, cost_text):
            return  # (waiting for the choice of what pays it)
    else:
        cost = M.parse_cost(cost_text)
        if payment_mode(plan, plan.actor) == "self":  # (review 18B: a special action, 116.2b: Purpose() — mana only for abilities or spells can't pay it)
            pay_from_pool(plan, plan.actor, cost, f"paid {cost.text()} to turn {printed.name} face up",
                          purpose=Purpose(special="turn_up"))
        else:
            if not can_pay(plan.state, plan.actor, cost, plan.info, purpose=Purpose(special="turn_up")):
                raise ActionError(f"Not enough mana to pay {cost.text()}")
            pay(plan, plan.actor, cost, f"paid {cost.text()} to turn {printed.name} face up", sources=a.sources,
                purpose=Purpose(special="turn_up"))
    plan.do({"type": "face_down", "card_ids": [card.id], "face_down": False})
    turned_up(plan, card)
    plan.rules.passed = []
    if kind == "megamorph":  # 702.37b, 708.11: the counter is put on as it's turned face up (the counter choke point)
        from app.rules import replace as replace_effects

        replace_effects.put_counters(plan, [(card.id, "+1/+1", 1)], by=plan.actor, then={"do": "face_up_done"})


def from_command_zone(card: CardInstance, player: str) -> bool:
    return card.zone == zone_key(player, "command") and card.commander_key is not None and card.owner == player


def cast_grant(state: GameState, player: str, card: CardInstance, ch: Characteristics, info: CardInfo | None, *,
               free: bool = False, slot: str | None = None, via: str | None = None) -> permissions.Grant | None:
    """How ``player`` may cast this card from where it is (601.3): from their hand, their commander
    from the command zone, flashback from their graveyard, or a permission (app/rules/permissions):
    a static ability on the table or one an effect granted. ``free``: they want to use a "without
    paying its mana cost" permission (118.9) — an alternative cost, which is optional (118.9b), so
    it is never applied to a plain cast: without the opt-in only paid ways count, and a card that
    only a free permission lets them cast isn't castable that way."""
    from app.rules import keyword_actions

    how = "hand" if card.zone == zone_key(player, "hand") else "command" if from_command_zone(card, player) else \
        "flashback" if from_graveyard(card, player, ch, state, info) else None
    if how is None and card.is_token and (perm := keyword_actions.prepared_permanent(state, card.id)) is not None \
            and perm.controller == player:
        how = "prepared"  # -- prepared (wave 13C) -- 722.3c: its controller may cast the copy in exile
    found = permissions.grants(state, player, card, ch, info, verb="cast") if info is not None else []
    flash = any(g.flash for g in found)
    if how is None and info is not None and card.zone == zone_key(player, "foretell") and not free and card.owner == player \
            and _foretell_offers(state, player, card, ch, info):
        how = "foretell"  # -- hidden exile (wave 18A) -- 702.143a: cast from the foretell exile for the foretell cost (only that way)
    if "aftermath" in ch.keywords:  # -- static_other sweep (wave 16B) -- 702.127a: "can't be cast from any zone other than a graveyard"
        return permissions.Grant("flashback", flash=flash) if how == "flashback" else None
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
        ways = [g for g in ways if g.use == via]
    if not ways:
        return None
    # (a way with no extra cost to pay first: the cheaper of two permissions; -- review 30c -- then one with no rider on what it becomes: Karador's
    # before Serra Paragon's "it gains … exile it", Edgar's "enters tapped")
    best = min(ways, key=lambda g: (bool(g.extra), bool(g.enters)))
    return permissions.with_choices(replace(best, flash=flash or best.flash), ways)  # (-- wave 32D -- a limited default: the other limited uses, to ask which)


def _foretell_offers(state: GameState, player: str, card: CardInstance, ch: Characteristics, info: CardInfo) -> list[Any]:
    """-- hidden exile (wave 18A) -- the foretell costs this foretold card can be cast for now (alt_costs.offers: tag "foretell")."""
    from app.rules import alt_costs

    return alt_costs.offers(state, player, card, ch, info)


def _escape_offers(state: GameState, player: str, card: CardInstance, ch: Characteristics, info: CardInfo) -> list[Any]:
    """-- escape (wave 5I) -- the escape costs this card can be cast for now (app/rules/escape.py)."""
    from app.rules import escape

    return escape.offers(state, player, card, ch, info)


def cast_problem(state: GameState, player: str, card: CardInstance, ch: Characteristics, *,
                 check_priority: bool = True, info: CardInfo | None = None, free: bool = False, sneak: bool = False) -> str | None:
    """Why ``player`` can't cast ``card`` right now (costs aside), or None. ``sneak``: cast for its sneak cost (702.190a), which
    is cast at instant timing (the offer itself exists only in your declare blockers step: alt_costs.sneak_timing)."""
    r = state.rules
    if r is None:
        return "Rules automation is off"
    if not ch.types:
        return "Fyodor doesn't know what that card is. Use the table tools."
    if ch.is_land:  # 305.9: a land card is played, never cast
        return f"{ch.name or 'That card'} is a land: play it instead"
    grant = cast_grant(state, player, card, ch, info, free=free)
    if grant is None:
        if free:
            return "Nothing lets you cast that without paying its mana cost now"
        return "You can cast spells from your hand, and your commander from the command zone"
    if check_priority and (r.priority != player or r.decision is not None):
        return "You don't have priority"
    if "Legendary" in ch.supertypes and ch.is_instant_or_sorcery and not _controls_legendary(state, player, info):
        # 205.4e: a legendary instant or sorcery needs a legendary creature or planeswalker
        return f"{ch.name} needs you to control a legendary creature or planeswalker"
    # -- cast limits (wave 5E) -- 601.3: no rule or effect prohibits it
    from app.rules import cast_limits

    limited = cast_limits.cast_problem(state, player, card, ch, info)
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
    if fl is not None and ("targets" not in fl or (info is not None and _flash_target_exists(state, player, card, fl["targets"], info))):
        return None  # (review 22F: "if it targets a commander" with no such object to target isn't offered: the target choice would be a dead end)
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
    from app.rules.creature_types import CREATURE_TYPES
    from app.rules.protection import _PLURALS
    from app.rules.selectors import _IRREGULAR

    sub = _IRREGULAR.get(what) or _PLURALS.get(what) or (what[:-1] if what.endswith("s") and what != "plains" else what).title()
    if sub in CREATURE_TYPES or sub in _AFFINITY_SUBTYPES:
        return lambda c, _card: sub in c.subtypes
    return None


def affinity_discount(state: GameState, player: str, ch: Characteristics, info: CardInfo, card: CardInstance | None = None) -> int:
    preds = [p for p in (affinity_filter(ch),) if p is not None]
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
               face_down: bool = False, targets: tuple[str, ...] = (), reduce: int = 0) -> M.ManaCost:
    """The total cost to cast (601.2f), in the rules' order: the mana cost (with X) or the
    alternative cost — flashback from the graveyard, evoke, dash, a face-down {3}, or {0} for
    "without paying its mana cost" (118.9) — plus additional costs (kicker 702.33a, buyback: 118.8)
    and cost increases (commander tax 903.8, "cost {N} more"), minus cost reductions (affinity
    702.41, "cost {N} less", the spell's own; 118.7a: generic only, never below {0}). Additional
    costs, increases and reductions apply to an alternative cost too (118.9d)."""
    player = player or card.owner
    if free:
        base = M.ManaCost()
    elif alternative is not None:
        base = alternative.with_x(x)  # (-- cast keywords (wave 43D) -- 107.3a: an alternative cost's {X} is the announced X)
    else:
        in_graveyard = card.zone == zone_key(card.owner, "graveyard")
        flashback = (flashback_cost(ch) or _granted_flashback(state, card, ch, info)) if in_graveyard else None  # (wave 3R2)
        base = M.parse_cost(flashback or ch.mana_cost).with_x(x)
    extras = list(additional)
    if kicker:
        extras.append(kicker_extra(ch, kicker, face_down=face_down).with_x(x))  # (-- cast keywords (wave 43D) -- 107.3a: "Kicker {X}" is paid with the announced X)
    tax = state.players[card.owner].commander_tax.get(card.commander_key, 0) \
        if from_command_zone(card, card.owner) and card.commander_key else 0
    affinity = (affinity_discount(state, player, ch, info, card) if info is not None else 0) + reduce  # (reduce: emerge, 18E)
    # -- cost changers (wave 44D) -- 107.3f, 202.3e: the spell being cast has the X announced for it, so a cost changer reading its mana value ("spells with mana value 4 or
    # greater cost {X} less") counts it (Thryx ruling 2020-01-24)
    total = permissions.total_cost(state, player, card, replace(ch, mana_value=ch.mana_value + x * ch.mana_cost.count("{X}")) if x else ch, info, base=base,
                                   additional=tuple(extras), tax=tax, affinity=affinity, targets=targets)
    from app.rules import (
        cast_limits,  # -- static_other sweep (wave 19A) -- Oath of Nissa: how the mana may be spent
    )
    mode = cast_limits.spend_mode(state, player, card, ch, info)
    return M.spend_as(total, mode) if mode else total


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
    faces = (0, 1) if chars.is_two_spell_card(card, info) else (None,)
    for face in faces:
        ch = chars.as_cast(card, info, face)
        if cast_problem(state, player, card, ch, check_priority=check_priority, info=info) is not None:
            continue
        manual = state.rules is not None and state.rules.card_mode(card.id) == "manual"
        extra = None if manual else costs.spell_additional_cost(ch.abilities)
        if extra is not None and additional_problem(permissions._view(state, player, info), extra, card, player):
            continue  # (wave 3$) the additional cost can't be paid: not offered
        grant = cast_grant(state, player, card, ch, info)
        grant_extra = costs.parse_additional_cost(grant.extra) if grant is not None and grant.extra else None
        if grant_extra is not None and additional_problem(permissions._view(state, player, info), grant_extra, card, player):
            continue  # -- cast permissions (wave 30Q) -- the permission's own additional cost ("by sacrificing a land") can't be paid: not offered
        if grant is not None and grant.how in ("escape", "foretell"):  # -- escape (wave 5I) -- only for an escape cost (702.138a)
            if alt_castable(state, player, card, info, check_priority=check_priority):
                return True
            continue
        if grant is not None and grant.how == "flashback" and not manual and card.zone == zone_key(player, "graveyard") \
                and (fb_more := flashback_extra(ch)) is not None \
                and additional_problem(permissions._view(state, player, info), fb_more, card, player):
            continue  # -- can't lose life (wave 29D) -- the flashback cost's other parts ("Pay 3 life") can't be paid (118.3, 119.4b): not offered, as the cast refuses
        # -- keywords (wave 30E) -- spree / tiered: at least one mode, so some mode's cost is paid with the rest (702.172a, 702.183a)
        spree: list[M.ManaCost | None] = [] if manual or not ({"spree", "tiered"} & set(ch.keywords)) else [
            M.parse_cost(m["cost"]) for m in (scripts.spell_definition(ch) or {}).get("modes", ()) if m.get("cost")]
        for mode_cost in spree or [None]:
            cost = spell_cost(state, card, ch, info=info, player=player, free=grant is not None and grant.free,
                              alternative=M.parse_cost(grant.alt_mana) if grant is not None and grant.alt_mana else None,  # (wave 25B: airbend)
                              targets=_hint_targets(ch), additional=(mode_cost,) if mode_cost is not None else ())  # -- review (Codex) --
            if grant is not None and grant.spend:  # -- as long as (wave 9B) -- 118.14
                cost = M.spend_as(cost, grant.spend)
            if can_pay(state, player, cost, info, purpose=Purpose(spell=ch, card=card.id, zone=card.zone, player=player,
                                                                  cost_x="{X}" in ch.mana_cost),
                       reserve=(extra.life if extra is not None else 0) + (grant_extra.life if grant_extra is not None else 0)):  # (-- hints (wave 30B) -- 119.4: the additional "pay 3 life" first)
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
                 check_priority: bool = True) -> list[dict[str, Any]]:
    """The alternative costs (118.9) ``player`` could cast this card for right now, each with what the intent's
    ``alt_cost`` names: its condition holds, and the whole total cost (601.2f) can be paid (118.3)."""
    from app.rules import alt_costs  # (a leaf over this module)

    out: list[dict[str, Any]] = []
    if chars.is_two_spell_card(card, info) or state.rules is None or state.rules.card_mode(card.id) == "manual":
        return out  # (a split card / adventure: which half isn't part of the hint)
    ch = chars.as_cast(card, info, None)
    blocked = cast_problem(state, player, card, ch, check_priority=check_priority, info=info) is not None
    if blocked and cast_problem(state, player, card, ch, check_priority=check_priority, info=info, sneak=True) is not None:
        return out
    grant = cast_grant(state, player, card, ch, info)
    in_graveyard = card.zone == zone_key(player, "graveyard")  # -- escape (wave 5I) -- from there: escape costs only
    if grant is not None and grant.how == "flashback" and not in_graveyard:
        return out  # (flashback is an alternative cost already: 118.9a)
    view = permissions._view(state, player, info)
    for offer in alt_costs.offers(state, player, card, ch, info):
        if blocked and offer.tag != "sneak":
            continue  # -- keywords (wave 30I) -- timing stops a plain cast; only a sneak cost (702.190a) is cast at instant speed
        if in_graveyard and not offer.escape and grant is not None and grant.how in ("escape", "flashback"):
            continue  # (escape and flashback are the cast's own alternative costs: 118.9a)
        extra = alt_costs.merged(costs.spell_additional_cost(ch.abilities), offer.alt.cost)
        if extra is not None and additional_problem(view, extra, card, player):
            continue
        cost = spell_cost(state, card, ch, info=info, player=player, alternative=offer.alt.mana_cost,
                          targets=_hint_targets(ch))  # -- review (Codex) --
        if can_pay(state, player, cost, info, purpose=Purpose(spell=ch, card=card.id, zone=card.zone, player=player,
                                                              cost_x="{X}" in ch.mana_cost),
                   reserve=extra.life if extra is not None else 0):  # (-- hints (wave 30B) -- 119.4)
            out.append({"id": offer.key, "label": offer.label, **({"x": True} if offer.alt.mana_cost.x else {})})  # (wave 43D: 107.3a, X is announced)
    return out


def optional_castable(state: GameState, player: str, card: CardInstance, info: CardInfo) -> list[dict[str, str]]:
    """The optional additional costs (Defiler of Vigor) ``player`` could pay casting this card right now, each alone."""
    from app.rules import cost_changes

    out: list[dict[str, str]] = []
    if chars.is_two_spell_card(card, info) or state.rules is None or state.rules.card_mode(card.id) == "manual":
        return out
    ch = chars.as_cast(card, info, None)
    if ch.is_land or cast_problem(state, player, card, ch, info=info) is not None:
        return out
    grant = cast_grant(state, player, card, ch, info)
    for offer in cost_changes.optional_offers(state, player, card, ch, info):
        if state.players[player].life < offer.life or (offer.life and spendable_life(state, player, info) == 0):  # (wave 22B: 119.4)
            continue
        if offer.kind and cost_payment.problem(permissions._view(state, player, info),
                                               costs.AbilityCost(components=(cost_changes.keyword_component(offer),)), card, player):
            continue  # (-- static_other sweep (wave 17C) -- conspire / teamwork: the creatures to tap aren't there)
        part = cost_changes.keyword_component(offer) if offer.kind == "reduce" else None  # -- cost reductions paid with objects (wave 47C) -- the most the objects it can take
        try:  # off (601.2f; the hint goes to its player alone, who knows their own hand)
            cost = cost_changes.reduce_only(spell_cost(state, card, ch, info=info, player=player,
                                                       free=grant is not None and grant.free,
                                                       alternative=M.parse_cost(grant.alt_mana) if grant is not None and grant.alt_mana else None,
                                                       reduce=part.reduces * len(cost_payment.candidates(permissions._view(state, player, info), part, player, card))
                                                       if part is not None else 0),
                                            (offer.mana,))
        except ActionError:
            continue
        if can_pay(state, player, cost, info, purpose=Purpose(spell=ch, card=card.id, zone=card.zone, player=player,
                                                              cost_x="{X}" in ch.mana_cost), reserve=offer.life):  # (-- hints (wave 30B) -- 119.4)
            out.append({"id": offer.source, "label": offer.label})
    return out
# -- end cost changers (wave 4I) --


# -- cast without paying (wave 3C) --
def free_castable(state: GameState, player: str, card: CardInstance, info: CardInfo) -> bool:
    """Does a permission let ``player`` cast this card without paying its mana cost right now (118.9)?"""
    faces = (0, 1) if chars.is_two_spell_card(card, info) else (None,)
    for face in faces:
        ch = chars.as_cast(card, info, face)
        if cast_problem(state, player, card, ch, info=info, free=True) is not None:
            continue
        manual = state.rules is not None and state.rules.card_mode(card.id) == "manual"
        extra = None if manual else costs.spell_additional_cost(ch.abilities)
        if extra is not None and additional_problem(permissions._view(state, player, info), extra, card, player):
            continue  # (118.9d: its additional cost still has to be paid, and can't be now)
        return True
    return False


def free_cast_problem(plan: Plan, player: str, card: CardInstance, ch: Characteristics) -> str | None:
    """-- review (wave 29B) -- why ``player`` can't cast this half / face (``ch``) of a card the engine lets them cast as an effect resolves
    (``cast_free``), checked before the choice is offered, so that no answer is a dead end: 205.4e (a legendary instant or sorcery), 700.2a (no
    mode can be chosen), 601.2c (a required target group can't get enough legal targets: the proposal is illegal, 601.5) and 601.2h / 118.9d (a
    mandatory additional cost, "sacrifice a creature", can't be paid). The same checks as ``cast_free``, in the same order; cast_limits'
    prohibitions (601.3) are the caller's. Mana is not checked here: ``can_pay`` doesn't count the mana abilities activated by hand (a Spirit
    Guide, Ashnod's Altar), so a cost increase that can't be paid is met in the payment, where the cast can be cancelled (``_announcing``)."""
    if "Legendary" in ch.supertypes and ch.is_instant_or_sorcery and not _controls_legendary(plan.state, player, plan.info):
        return f"{ch.name} needs you to control a legendary creature or planeswalker"
    prev, plan.actor = plan.actor, player
    try:
        manual = plan.manual(card)  # (cast by hand: no targets, modes or additional costs read, as in cast_free)
        definition = None if manual else per_opponent.for_cast(plan, card.id, scripts.spell_definition(ch))
        if definition is not None and definition.get("modes"):
            modal = definition["modal"]
            allowed = choosable_modes(plan, definition, card.id, spell=True)
            if not allowed or (not modal["repeat"] and len(allowed) < modal["min"]):
                return f"{ch.name or 'It'} has no mode you can choose"
        elif not manual:
            aura = attachments.enchant_selector(ch)
            src = source_of(plan, card.id, True)  # (wave 49C: a spell)
            from app.rules import kicked_instead
            from app.rules.targets import group_limits

            for spec in kicked_instead.applicable(scripts.target_groups(definition if aura is None else {"target": {"what": aura}}), 0):
                lo, hi = (0, 0) if "x_value" in spec or (spec.get("divide") or {}).get("value") is not None \
                    else group_limits(spec, None)  # (X is 0: 107.3b; "up to X" may be none; wave 34D: nor a total counted as it's cast, that may be 0)
                if hi < lo or len(legal_targets(plan, spec["what"], player, src, card.id)) < lo:
                    return f"{ch.name or 'It'} has no legal target"
        extra = None if manual else costs.spell_additional_cost(ch.abilities)
        if extra is None or any(c.kind in _HAND_PARTS for side in (extra, *extra.either) for c in side.components):
            return None  # (a part read from the hand — "reveal a creature card from your hand", "discard a land card" — is hidden: whether
            # the question is skipped mustn't tell the others what the hand holds; that cast is refused in the cast, where it can be cancelled)
        return additional_problem(plan, extra, card, player)
    finally:
        plan.actor = prev


_HAND_PARTS = frozenset({costs.DISCARD, "EXILE_FROM_HAND", "HAND_TO_BOTTOM", "REVEAL_FROM_HAND", costs.BEHOLD})  # (cost_payment._candidates)
# -- end cast without paying (wave 3C) --


def cast_spell(plan: Plan, a: A.CastSpell) -> None:
    from app.rules.engine import advance  # the engine imports this module

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
    problem = cast_problem(plan.state, plan.actor, card, ch, info=plan.info, free=a.free, sneak=sneaking)
    if problem:
        raise ActionError(problem)
    grant = cast_grant(plan.state, plan.actor, card, ch, plan.info, free=a.free, slot=a.slot, via=a.via)
    sac_at_cleanup = not a.free and flash_sac(plan.state, plan.actor, card, ch, plan.info)  # (-- flash auras (wave 46B) -- judged before it is on the stack)
    if grant is not None and grant.how == "permission" and a.x_value and "{X}" in ch.mana_cost:
        # -- review 30c -- 202.3e, 601.2e: "with mana value 3 or less" reads the X announced (Lurrus ruling 2020-04-17: "{X}{W} … with X as 1 but not as 2")
        grant = cast_grant(plan.state, plan.actor, card, replace(ch, mana_value=ch.mana_value + a.x_value * ch.mana_cost.count("{X}")), plan.info,
                           free=a.free, slot=a.slot, via=a.via)
        if grant is None:
            raise ActionError(f"{ch.name} can't be cast this way with X = {a.x_value}: its mana value would be too high")
    if a.slot is not None and grant is None:
        raise ActionError(f"{ch.name or 'That card'} can't be cast as a {a.slot} spell now")
    if a.via is not None and (grant is None or grant.use != a.via):  # -- cast permissions (wave 32D) -- 601.2: a permission that doesn't cover this cast
        raise ActionError(f"{ch.name or 'That card'} can't be cast using that permission now")
    if grant is not None and len(grant.among) > 1:
        permissions.ask_use(plan, a, card, ch, grant.among, "cast")  # (-- wave 30Q, 32D -- "choose one as you cast it" (Muldrotha); which limited permission: asked before anything is paid)
        return
    free = grant is not None and grant.free  # "without paying its mana cost" (118.9): an alternative cost of {0}
    base = M.parse_cost(ch.mana_cost)
    airbent = grant is not None and bool(grant.alt_mana)  # -- trigger other (wave 25B) -- airbend 701.65a: cast only by paying its alternative cost
    from app.rules import alt_costs as _alt_x  # (leaves over this module)

    alt_x = a.alt_cost is not None and not free and not plan.manual(card) and any(  # -- cast keywords (wave 43D) -- 107.3a: an alternative cost with {X}
        o.key == a.alt_cost and o.alt.mana_cost.x for o in _alt_x.offers(plan.state, plan.actor, card, ch, plan.info))  # (harmonize, overload, surge …)
    if (base.x or alt_x) and a.x_value is None:
        if alt_x or (not free and a.alt_cost is None and not airbent):
            raise ActionError(f"Choose a value for X to cast {ch.name}")
        a.x_value = 0  # 107.3b: X is 0 when a spell is cast without paying its mana cost (or for an alternative cost, wave 4I)
    elif base.x and a.x_value and (free or airbent):  # -- review (wave 25A) -- 107.3b: the only legal choice is 0
        raise ActionError(f"X is 0 when {ch.name} is cast without paying its mana cost or for an alternative cost without X (107.3b)")
    from app.rules import cast_limits as _x_limits

    if base.x and (limited := _x_limits.cast_problem(plan.state, plan.actor, card, ch, plan.info, announced=a.x_value or 0)):
        raise ActionError(limited)  # -- review 38 -- 601.2e: the X announced counts in its mana value ("spells with mana value 3 or less", Brisela)
    kick_x = a.kicker and not a.face_down and (kc := kicker_cost(ch.abilities)) is not None and kc.x  # -- cast keywords (wave 43D) -- 107.3a: "Kicker {X}"
    if kick_x and (base.x or a.x_value is None or free):  # ponytail: a spell with another X, or cast free this way, pays a kicker X by hand
        raise ActionError(f"Choose a value for X to pay the kicker cost of {ch.name}" if a.x_value is None and not (base.x or free)
                          else f"{ch.name}: pay its kicker X by hand")
    alternative: M.ManaCost | None = M.parse_cost("{3}") if a.face_down else None
    additional: list[M.ManaCost] = []
    if a.buyback:
        extra = keyword_cost(ch, "buyback", BUYBACK)
        if extra is None and buyback_parts(ch) is None:  # (-- keywords (wave 30E) -- a buyback cost of other parts: merged below)
            raise ActionError(f"{ch.name} has no buyback cost")
        if extra is not None:
            additional.append(M.parse_cost(extra))
    if a.evoke:
        evoke = keyword_cost(ch, "evoke", EVOKE)
        if evoke is None or card.zone != zone_key(plan.actor, "hand"):
            raise ActionError("Only a card with evoke can be cast for its evoke cost from your hand")
        alternative = M.parse_cost(evoke)
    if a.dash:
        dash = keyword_cost(ch, "dash", DASH)
        if dash is None or card.zone != zone_key(plan.actor, "hand"):
            raise ActionError("Only a card with dash can be cast for its dash cost from your hand")
        alternative = M.parse_cost(dash)
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
        alt_offer = alt_costs.chosen(plan, a.alt_cost, card, ch)
        alternative = alt_offer.alt.mana_cost
        if base.x and a.x_value and not alternative.x:
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
            and timing_problem(plan.state, plan.actor, ch, grant) is not None:
        if "pay" in flashing:
            additional.append(M.parse_cost(flashing["pay"]))  # ("if you pay {2} more": an additional cost, only at the timing that needs it)
        elif "x_max" in flashing and (a.x_value or 0) > flashing["x_max"]:
            raise ActionError(f"{ch.name} can be cast now only if X is {flashing['x_max']} or less")
    else:
        flashing = None
    definition = None if plan.manual(card) or a.face_down else scripts.spell_definition(ch)
    definition = per_opponent.for_cast(plan, card.id, definition)  # -- per-opponent targets (wave 23A) --
    entwined = bool(a.kicker) and (kick := kicker_cost(ch.abilities)) is not None and kick.entwine  # (an entwined spell isn't kicked: review 18E)
    kicked = 0 if entwined else a.kicker
    if entwined and not (definition or {}).get("modes"):
        raise ActionError(f"{ch.name} can be entwined only as a modal spell")  # -- casting extras (wave 18E) -- 702.42a
    splice_extra: list[AbilityCost] = []
    if a.splice:  # -- casting extras (wave 18E) -- 702.47: the spliced cards' text is part of the spell; their costs are additional costs
        from app.rules import splice

        if plan.manual(card) or a.face_down:
            raise ActionError("That card is played by hand: splice by hand with the table tools")
        spliced_ch, spliced_costs = splice.prepare(plan, a.splice, card, ch)
        if (definition := per_opponent.for_cast(plan, card.id, scripts.spell_definition(spliced_ch))) is None:  # (review 23A: its groups too)
            raise ActionError("That splice can't be carried out by the engine")
        for sc in spliced_costs:
            if sc.mana:
                additional.append(sc.mana_cost)
            if sc.cost.components:
                splice_extra.append(sc.cost)
    aura = None if plan.manual(card) or a.face_down else (merged.MUTATE_TARGET if mutating_cast else attachments.enchant_selector(ch))
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
    if grant is not None and grant.how == "flashback" and not escaping and (fb_more := flashback_extra(ch)) is not None \
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
    if grant is not None and grant.life_mv and (mv := int(ch.mana_value)):  # -- casting costs (wave 22F) -- "pay life equal to its mana value"
        add_cost = alt_costs.merged(add_cost, costs.AbilityCost(  # (X is 0: 107.3b; the free alternative cost left no mana cost to read)
            components=(costs.CostComponent(costs.PAY_LIFE, amount=mv, text=f"Pay {mv} life"),), life=mv))
    if (target_life := cost_changes.targeting_life(plan.state, plan.actor, card, ch, plan.info, tuple(t.id for t in chosen))):
        add_cost = alt_costs.merged(add_cost, costs.AbilityCost(  # -- casting costs (wave 22F) -- Terror of the Peaks: life for its targets (601.2f)
            components=(costs.CostComponent(costs.PAY_LIFE, amount=target_life, text=f"Pay {target_life} life"),), life=target_life))
    if (optional_more := optional_parts(optional)) is not None:  # -- cost changers (wave 4I) -- Defiler of Vigor's 2 life, paid with the rest (601.2h, 119.4)
        add_cost = alt_costs.merged(add_cost, optional_more)
    add_objects: dict[int, list[str]] = {}
    if add_cost is not None:
        problem = additional_problem(plan, add_cost, card, plan.actor) or life_x_problem(plan, add_cost, a, plan.actor)  # (4K)
        if problem:
            raise ActionError(problem)
        plan.reserved_life = add_cost.life + ((a.x_value or 0) if add_cost.life_x else 0)  # (wave 29C: 119.4, with Phyrexian mana's life)
        found_objects = cost_payment.choose(plan, a, add_cost, card, ch.name or "it")
        if found_objects is None:
            return  # waiting for the payer's choice; nothing has been paid
        add_objects = found_objects
    emerge_reduction = 0  # -- casting extras (wave 18E) -- 702.119a: reduced by the sacrificed permanent's mana value; 702.180a: harmonize, by
    # the tapped creature's power
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
    cost = spell_cost(plan.state, card, ch, a.x_value or 0, plan.info, player=plan.actor, alternative=alternative,
                      free=free, kicker=a.kicker, additional=tuple(additional), face_down=a.face_down, targets=tuple(t.id for t in chosen),
                      reduce=emerge_reduction + (cost_payment.reduction(add_cost, add_objects) if add_cost is not None else 0))  # (wave 47C: "you may sacrifice any number of …")
    cost = cost_changes.reduce_only(cost, tuple(o.mana for o in optional if o.mana))  # ("reduces only the amount of green mana")
    cost = M.spend_as(cost, grant.spend) if grant is not None and grant.spend else cost  # -- as long as (wave 9B) -- 118.14
    helper, helper_pays = None, 0  # -- casting extras (wave 18E) -- 702.132a assist: another player pays some generic mana (601.2g-h)
    if "assist" in ch.keywords and not plan.manual(card) and not a.face_down:
        from app.rules import assist

        found_helper = assist.announce(plan, a, card, ch, cost)
        if found_helper is assist.WAITING:
            return
        helper, helper_pays = found_helper
        cost = cost.plus_generic(-helper_pays)
    was_locked = plan.locked_cost is not None
    cost = _locked(plan, cost)  # -- cost changers (wave 4I) -- 601.2f: locked in once the payment was asked for (the caster's share, after assist)
    not_mana = cost_payment.excluded(add_cost, card, add_objects) if add_cost is not None else ()
    origin = card.zone  # (wave 17B: where it is cast from, before it moves to the stack)
    from_oid = plan.oid(card)  # -- as long as (wave 37A) -- the object it is before it becomes the spell (400.7): "until this card is cast from exile"
    purpose = Purpose(spell=ch, zone=origin, player=plan.actor, kicked=bool(kicked))
    announced_cost = announce_phyrexian(plan, a, cost, ch.name or "it", exclude=not_mana, purpose=purpose, trusted=was_locked)  # (wave 50B: 601.2b)
    if announced_cost is None:
        return
    cost = announced_cost
    if payment_step(plan, a, cost, ch.name or "it", exclude=not_mana, purpose=purpose):
        return
    commander_cast = from_command_zone(card, plan.actor)
    harmonized = alt_offer is not None and alt_offer.tag == "harmonize"  # -- casting extras (wave 18E) -- 702.180a: exiled as it leaves the stack
    flashback = from_graveyard(card, plan.actor, ch, plan.state, plan.info) and not escaping  # (wave 5I: escape instead, 118.9a)
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
    if helper is not None and helper_pays:  # (the helper's mana first: 601.2g, then the caster's own payment, 601.2h)
        from app.rules import assist

        assist.pay(plan, helper, helper_pays, card, ch)
    record = pay_spell(plan, a, card, ch, cost, f"paid {cost.text()} for {ch.name or 'a face-down spell'}", not_mana=not_mana,
                       origin=origin)
    if add_cost is not None:
        if add_cost.life:
            from app.rules import replace as _replace_life  # (wave 28B: 119.4)
            _replace_life.lose_life(plan, [(plan.actor, add_cost.life)])  # 119.4: paying life is losing it
            record.life += add_cost.life
        if add_cost.life_x and a.x_value:  # -- X sized by a count (wave 4K) -- "pay X life" (119.4)
            from app.rules import replace as _replace_life  # (wave 28B: 119.4)
            _replace_life.lose_life(plan, [(plan.actor, a.x_value)])
            record.life += a.x_value
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
    record.kicked = kicked or int(a.awaken) or int(gift_to is not None or bargained)  # 702.33d (-- static_other sweep (wave 16B) -- awaken: the line is read as
    record.gift_to = gift_to  # "If this spell was kicked"; wave 23D: a promised gift, 702.174k, likewise)
    _note_cast(plan, record, cast_zone)  # -- refused modal/conditional (wave 3R1) --
    record.flash_sac = sac_at_cleanup
    record_payment(plan, card.id, record)
    tags = ["Cast from the command zone"] if commander_cast else ["Harmonize"] if harmonized else ["Jump-start"] if jumped else \
        ["Aftermath" if "aftermath" in ch.keywords else "Flashback"] if flashback else ["Dashed"] if a.dash else \
        ["Disturbed" if alt_offer is not None and alt_offer.tag == "disturb" else "Alternative cost" if alt_offer is not None and alt_offer.tag in ("graveyard", "mayhem") else "Escaped"] if escaping else ["Foretold"] if foretold else []  # (wave 5I; 18E)
    if grant is not None and grant.how == "permission":
        permissions.consume(plan, grant)  # (a "once during each of your turns" permission is used up)
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
        tags.append("Kicked" if a.kicker == 1 else f"Kicked ×{a.kicker}")
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
    if grant is not None and grant.exile_gy and (grant.exile_gy == "all" or ch.is_instant_or_sorcery):  # -- cast from graveyard (wave 19C) -- 614.1a
        plan.rules.exile_if_graveyard.append(plan.oid(card))
    if grant is not None and grant.enters:  # -- cast permissions (wave 30Q) -- "If you cast a spell this way, that artifact enters tapped / with a finality counter on it"
        plan.rules.cast_enters[plan.oid(card)] = grant.enters  # (applied as it enters: engine.resolve_top; a countered spell never does, and a new object is a new id, 400.7)
    if a.x_value is not None or tags:
        info: dict[str, Any] = {"type": "set_stack_info", "card_id": card.id}
        if a.x_value is not None:
            info["x"] = a.x_value
        if tags:
            info["tags"] = tags
        plan.do(info)
    if a.targets:
        plan.target_arrows(card.id, a.targets)
    r = plan.rules
    # for "whenever you cast"; amount: the Nth spell its caster cast this turn ("your second spell each turn")
    emit(plan.state, "spell_cast", object_id=plan.oid(card), card=card.id, player=plan.actor,
         amount=r.spells_this_turn(plan.actor, plan.state.turn.number) + 1)
    delayed.spell_cast(plan, from_oid)  # -- as long as (wave 37A) -- 611.2a: "until this card is cast from exile" is over
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
            _demonstrate_trigger(plan, card, ch)  # (wave 43D)
    if "replicate" in ch.keywords and not a.face_down and not plan.manual(card):  # (wave 15E)
        _replicate_trigger(plan, card, ch, a.kicker)
    if definition is not None and picked and not slot_specs and any(definition["modes"][i].get("groups") for i in picked):
        r.stack[card.id] = StackEntry(kind="spell", controller=plan.actor, source_card=card.id, source_object=plan.oid(card),
                                      name=ch.name, effects=modal_effects(definition, picked, True), x=a.x_value, modes=picked,
                                      **picked_targets.entry(None), kicked=kicked or int(a.awaken) or int(gift_to is not None or bargained))  # (-- static_other sweep (wave 16B) --)
    elif definition is not None and picked:  # a modal spell: each chosen mode's effects, with its own target slot
        effects_in_order = modal_effects(definition, picked, False)
        r.stack[card.id] = StackEntry(kind="spell", controller=plan.actor, source_card=card.id, source_object=plan.oid(card),
                                      name=ch.name, effects=effects_in_order, targets=chosen, target_spec=None,
                                      x=a.x_value, modes=picked, slots=slots, slot_specs=slot_specs, kicked=kicked or int(a.awaken) or int(gift_to is not None or bargained))
    elif definition is not None:
        r.stack[card.id] = StackEntry(kind="spell", controller=plan.actor, source_card=card.id, source_object=plan.oid(card),
                                      name=ch.name, effects=list(definition["effects"]), x=a.x_value,
                                      **picked_targets.entry(definition), kicked=kicked or int(a.awaken) or int(gift_to is not None or bargained))
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
    for ab in ch.abilities:
        if ab.index != index or ab.kind != "keywords":
            continue
        found = [CYCLING.fullmatch(p) for p in re.split(r",\s*", ab.text.strip().rstrip("."))]
        if found and all(found):
            return [((k if (k := m["kind"].strip()).lower() != "basic land" else "basic land"), m["cost"]) for m in found if m]
    return []


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
    oid = plan.oid(card)
    ability_id = _new_ability(plan, card, f"Search your library for a card with mana value {mv}, reveal it, put it into "
                                          f"your hand, then shuffle.")
    pay(plan, plan.actor, mana, f"paid {mana.text()} to transmute {ch.name}", sources=a.sources, purpose=Purpose(ability_of=ch))
    plan.do({"type": "move", "card_ids": [card.id], "to": {"player": card.owner, "zone": "graveyard"}})  # discarded (701.9a)
    _stacked(plan, card, oid, ch, ability_id, effects)
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
    kind, mana_text = pieces[0]
    if len(pieces) > 1:  # -- keywords (wave 50H) -- 702.29e: "Mountaincycling {2}, forestcycling {2}": the ability activated is announced first (601.2b)
        if _first_alt(plan, "cycling"):
            raise ActionError("Cycle it by hand while an effect lets you pay {0} for the first cycling each turn: Fyodor can't ask both choices yet")
        if _equip_side(plan, card, ch, a, [c for _, c in pieces], cycling=True, labels=[f"{k}cycling {c}".capitalize() for k, c in pieces]) is None:
            return  # waiting for the choice
        kind, mana_text = pieces[int(next(c.cards[0] for c in a.cost_choices if c.component == costs.EITHER_SLOT and c.cards)[7:])]
    if _first_alt(plan, "cycling") and mana_text != "{0}":  # -- first activation (wave 48D) -- 118.9: "You may pay {0} rather than pay the cycling cost of the first card you cycle each turn" (typecycling too, 702.29f)
        side = _equip_side(plan, card, ch, a, [mana_text, "{0}"], cycling=True)  # (601.2b: announced before the cost is determined)
        if side is None:
            return  # waiting for the choice
        mana_text = side
    # 702.29a: cycling is an activated ability — "Abilities you activate that aren't mana abilities cost {1} less"
    # applies to it (602.2b -> 601.2f; app/rules/permissions.py ability_mana)
    mana = M.parse_cost(permissions.ability_mana(plan.state, plan.actor, card, ch, mana_text, plan.info))
    if mana.x and a.x_value is None:  # -- X from the triggering object (wave 34C) -- 107.3a: "Cycling {X}{1}{U}": X is announced as it is activated
        raise ActionError("Choose a value for X")
    cycling_x = a.x_value or 0 if mana.x else None
    mana = _locked(plan, mana).with_x(cycling_x or 0)  # -- review (wave 4R) -- 602.2b → 601.2f: locked in, as for other activations
    if payment_step(plan, a, mana, f"cycling {ch.name}", purpose=Purpose(ability_of=ch, cost_x=cycling_x is not None)):
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
    pay(plan, plan.actor, mana, f"paid {mana.text()} to cycle {ch.name}", sources=a.sources, purpose=Purpose(ability_of=ch, cost_x=cycling_x is not None))
    _activated(plan, "cycling")  # (-- first activation (wave 48D) -- the card is discarded to pay a cycling cost, 702.29c)
    plan.do({"type": "move", "card_ids": [card.id], "to": {"player": card.owner, "zone": "graveyard"}})
    emit(plan.state, "cycled", object_id=oid, card=card.id, player=plan.actor, amount=cycling_x or 0)  # (wave 34C: amount: the X, for triggers.x_source)
    _stacked(plan, card, oid, ch, ability_id, effects)


def _create_ability(plan: Plan, card: CardInstance, text: str, keep: bool = False) -> Any:
    """-- hidden-zone abilities (wave 28C) -- 602.2a / 701.20a: an ability activated from a hidden zone (the hand) reveals its card, so
    the ability on the stack names it for everyone (cycling, channel, ninjutsu, "put this card from your hand …"); the card is hidden
    again at once if it stays there (``keep``: it stays revealed, ninjutsu 702.49b), and the rest of the hand is never shown."""
    shown = card.zone == zone_key(plan.actor, "hand") and not card.revealed_to
    if shown:
        plan.do({"type": "reveal", "card_ids": [card.id]}, actor=plan.actor)
    created = plan.do({"type": "create_ability", "text": text, "source_id": card.id, "kind": "activated"})
    if shown and not keep:  # (review 28C: ninjutsu's card was revealed, hidden and revealed again)
        plan.do({"type": "hide", "card_ids": [card.id]}, actor=plan.actor)
    return created


def _new_ability(plan: Plan, card: CardInstance, text: str) -> str | None:
    created = _create_ability(plan, card, text[:500])
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
        from app.rules.triggers import activated  # -- activation (wave 11F) --

        activated(plan, card, oid, ability_id=ability_id)
    r.passed = []
    r.priority = plan.actor
    if r.prefs_for(plan.actor).hold_priority:
        plan.hold = plan.actor
        return
    r.auto_pass = plan.actor  # (as after a cast: engine.advance passes for you once the triggers are on the stack)
    advance(plan)


CREW = re.compile(r"^crew (?P<n>\d+)$", re.IGNORECASE)


SUSPEND = re.compile(r"^suspend (?P<n>\d+)\s*[—-]\s*(?P<cost>(?:\{[^}]+\})+)$", re.IGNORECASE)


def suspend_info(ch: Characteristics, index: int) -> tuple[int, str] | None:
    """702.62 "Suspend N—{cost}" on ability line ``index``: (N, cost)."""
    for ab in ch.abilities:
        if ab.index == index and ab.kind == "keywords" and "suspend" in ab.keywords:
            m = SUSPEND.fullmatch(ab.text.strip().rstrip("."))
            if m:
                return int(m["n"]), m["cost"]
    return None


def suspend(plan: Plan, card: CardInstance, ch: Characteristics, a: A.ActivateAbility, n: int, cost_text: str) -> None:
    """702.62a: a special action — whenever you could begin to cast it, pay the suspend cost and
    exile it with N time counters. It doesn't use the stack."""
    problem = cast_problem(plan.state, plan.actor, card, ch, info=plan.info)
    if problem:
        raise ActionError(problem)
    cost = M.parse_cost(cost_text)
    if payment_step(plan, a, cost, f"suspending {ch.name}", purpose=Purpose()):  # (review 18B: a special action, 116.2f: not a cast — restricted mana for spells or abilities doesn't pay it)
        return
    pay(plan, plan.actor, cost, f"paid {cost.text()} to suspend {ch.name}", sources=a.sources, purpose=Purpose())
    plan.do({"type": "move", "card_ids": [card.id], "to": {"player": card.owner, "zone": "exile"}})
    if n:
        plan.do({"type": "counter", "card_ids": [card.id], "kind": "time", "delta": n})
    plan.rules.suspended.append(card.id)
    plan.note(f"{ch.name} is suspended with {n} time counter{'s' if n != 1 else ''}", [card.id])
    plan.rules.passed = []


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
    pay(plan, plan.actor, cost, f"paid {cost.text()} to plot {ch.name}", sources=a.sources, purpose=Purpose())
    plan.do({"type": "move", "card_ids": [card.id], "to": {"player": card.owner, "zone": "exile"}})
    become_plotted(plan, card.id)
    plan.rules.passed = []


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


FORETELL = re.compile(r"^foretell (?P<cost>(?:\{[^}X]+\})+)$", re.IGNORECASE)


def foretell(plan: Plan, card: CardInstance, ch: Characteristics, a: A.ActivateAbility) -> None:
    """-- hidden exile (wave 18A) -- 702.143a/b foretell: a special action (116.2h), any time you have priority during your turn:
    pay {2} and exile this card from your hand face down. Its owner alone may look at it (the foretell zone); it may be cast
    after this turn has ended for its foretell cost (alt_costs.offers, casting.cast_grant)."""
    if plan.state.turn.active_player != plan.actor:
        raise ActionError("You can foretell a card only during your turn (702.143a)")
    cost = M.parse_cost("{2}")
    if payment_step(plan, a, cost, f"foretelling {ch.name}", purpose=Purpose(special="foretell")):  # (review 19: 116.2h, not a cast)
        return
    pay(plan, plan.actor, cost, "paid {2} to foretell a card", sources=a.sources,
        purpose=Purpose(special="foretell"))
    plan.do({"type": "move", "card_ids": [card.id], "to": {"player": card.owner, "zone": "foretell"}})
    plan.rules.foretold[card.id] = plan.state.turn.number
    plan.note(f"{plan.name(plan.actor)} foretells a card")
    plan.rules.passed = []


def companion_problem(state: GameState, player: str, card: CardInstance, info: CardInfo) -> str | None:
    """Why ``player`` can't take this companion by the special action (116.2g, 103.2b, 702.139b), or None. (-- special actions (wave 50B) -- shared with ``can_act``.)"""
    mine = [c for c in state.cards.values() if c.owner == player and c.origin == "companion"]
    if len(mine) != 1:
        return "You may reveal no more than one companion (103.2b)"
    start = [c for c in state.cards.values() if c.owner == player and c.origin in ("library", "command") and c.card_id
             and not (c.is_token or c.copy_of or c.ability or c.test_object)]  # (702.139b: the commander too)
    deck = [info.get(c.card_id) for c in start if c.card_id]
    data = info.get(card.card_id) if card.card_id else None
    if data is None or any(d is None for d in deck):
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
    pay(plan, plan.actor, cost, f"paid {cost.text()} to put {ch.name} into their hand", sources=a.sources, purpose=Purpose())
    plan.do({"type": "move", "card_ids": [card.id], "to": {"player": card.owner, "zone": "hand"}})
    plan.note(f"{plan.name(plan.actor)} puts their companion {ch.name} into their hand", [card.id])
    plan.rules.passed = []


UNEARTH = re.compile(r"^unearth (?P<cost>(?:\{[^}]+\})+)$", re.IGNORECASE)
MADNESS = re.compile(r"^madness (?P<cost>(?:\{[^}]+\})+)$", re.IGNORECASE)
BUYBACK = re.compile(r"^buyback (?P<cost>(?:\{[^}]+\})+)$", re.IGNORECASE)
BUYBACK_PARTS = re.compile(r"^buyback—(?P<cost>[^{}]+)$", re.IGNORECASE)  # (wave 30E) "Buyback—Sacrifice a land." / "Discard two cards" / "Pay 4 life"


def buyback_parts_line(line: str) -> AbilityCost | None:
    """-- keywords (wave 30E) -- 702.27a: a buyback cost without mana ("Buyback—Sacrifice three Islands.", "Discard two cards", "Pay 4 life"):
    an additional cost (118.8) of the parts alt_costs reads, or None."""
    from app.rules import alt_costs  # (a leaf over this module)

    m = BUYBACK_PARTS.fullmatch(line.strip().rstrip("."))
    found = alt_costs.parse_cost(m["cost"]) if m else None
    return found.cost if found is not None and not found.mana and found.cost.components else None


def buyback_parts(ch: Characteristics) -> AbilityCost | None:
    return next((p for ab in ch.abilities if ab.kind == "keywords" and "buyback" in ab.keywords and (p := buyback_parts_line(ab.text)) is not None), None)
EVOKE = re.compile(r"^evoke (?P<cost>(?:\{[^}]+\})+)$", re.IGNORECASE)
DASH = re.compile(r"^dash (?P<cost>(?:\{[^}]+\})+)$", re.IGNORECASE)
AWAKEN = re.compile(r"^awaken (?P<n>\d+)—(?P<cost>(?:\{[^}]+\})+)$", re.IGNORECASE)  # (wave 16B) 702.113a


def kicker_extra(ch: Characteristics, times: int, *, face_down: bool = False) -> M.ManaCost:
    """702.33a / 702.33c: the kicker cost paid ``times`` times — an additional cost (118.8) that
    joins the total cost (601.2f) before increases and reductions; the spell's mana cost and mana
    value don't change (118.8d)."""
    kick = None if face_down else kicker_cost(ch.abilities)  # (a face-down spell has no abilities, 708.2)
    if kick is None:
        raise ActionError(f"{ch.name or 'That spell'} has no kicker cost Fyodor can pay: kick it by hand with the table tools")
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
    state = plan.state
    if state.turn.active_player != plan.actor or state.turn.phase not in MAIN_PHASES or state.zones.get(STACK):
        raise ActionError("Unearth only as a sorcery: in your main phase with an empty stack")
    cost = M.parse_cost(cost_text)
    if payment_step(plan, a, cost, f"unearthing {ch.name}", purpose=Purpose(ability_of=ch)):
        return
    oid = plan.oid(card)
    ability_id = _new_ability(plan, card, f"Return {ch.name} to the battlefield. It gains haste. Exile it at the next end step.")
    pay(plan, plan.actor, cost, f"paid {cost.text()} to unearth {ch.name}", sources=a.sources, purpose=Purpose(ability_of=ch))
    _stacked(plan, card, oid, ch, ability_id, [{"do": "unearth", "card": card.id, "object": oid}])


def crew_power(ch: Characteristics, index: int) -> int | None:
    """Crew N (702.122) on ability line ``index``: N, or None."""
    for ab in ch.abilities:
        if ab.index == index and ab.kind == "keywords":
            m = CREW.fullmatch(ab.text.strip().rstrip("."))
            if m:
                return int(m["n"])
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
    _stacked(plan, card, oid, ch, ability_id, [{"do": "saddled"}] if saddle else
             [{"do": "animate", "who": "self", "types": ["Artifact", "Creature"], "crewed": True}])


# -- static statics (wave 10B) -- cascade a permanent gives the spell as it's cast (cast_limits.granted_cascade)
def _granted_cascade(plan: Plan, card: CardInstance, ch: Characteristics, cast_from: str | None) -> int:
    from app.rules import cast_limits

    return cast_limits.granted_cascade(plan, card.id, ch, cast_from)


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


def _demonstrate_trigger(plan: Plan, card: CardInstance, ch: Characteristics) -> None:
    """-- cast keywords (wave 43D) -- 702.144a demonstrate: "When you cast this spell, you may copy it and you may choose new targets for the copy. If you
    copy the spell, choose an opponent. That player copies the spell and may choose new targets for that copy." (copying.demonstrate_copy)"""
    from app.rules.triggers import _add

    if "demonstrate" in ch.keywords:
        spell = {"spell": card.id, "object": plan.oid(card)}
        _add(plan, controller=plan.actor, source_card=card.id, source_object=plan.oid(card), name=ch.name, index=6170,
             definition={"kind": "triggered", "trigger": "demonstrate", "optional": True, "target": None,
                         "effects": [{"do": "demonstrate_copy", **spell}, {"do": "demonstrate_opponent", **spell}]})


def _conspire_trigger(plan: Plan, card: CardInstance, ch: Characteristics, record: PaymentRecord) -> None:
    """-- static_other sweep (wave 17C) -- 702.78a: "When you cast this spell, if its conspire cost was paid, copy it. If the spell has
    any targets, you may choose new targets for the copy." (the copy is storm's: copying.storm)"""
    from app.rules.triggers import _add

    # (-- casting extras (wave 18E) -- 702.153a casualty: "When you cast this spell, if a casualty cost was paid for it, copy it.")
    if f"optional:{card.id}:conspire" in record.additional or f"optional:{card.id}:casualty" in record.additional:
        _add(plan, controller=plan.actor, source_card=card.id, source_object=plan.oid(card), name=ch.name, index=6160,
             definition={"kind": "triggered", "trigger": "storm", "optional": False, "target": None,
                         "effects": [{"do": "storm", "spell": card.id, "object": plan.oid(card), "n": 1}]})


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
    gift_to: str | None = None
    if any(o.kind == "gift" for o in optional):  # -- gift (wave 23D) -- 702.174a: the opponent the gift is promised to
        from app.rules import gift

        found_gift = gift.announce(plan, a, card, ch)
        if found_gift is gift.WAITING:
            return None
        gift_to = found_gift
    if a.optional_costs and plan.manual(card):
        raise ActionError("That card is played by hand: pay its costs with the table tools")
    return optional, gift_to, any(o.kind == "bargain" for o in optional)  # -- keywords (wave 30E) -- 702.166b: its controller declared the intention to pay it


def optional_parts(optional: list[Any]) -> AbilityCost | None:
    """The cost parts the announced optional costs add (paid with the rest, 601.2h): a sacrifice, a tap, life; a gift costs nothing (wave 23D)."""
    from app.rules import cost_changes

    parts = tuple(c for o in optional if (c := cost_changes.keyword_component(o) if o.kind else costs.CostComponent(
        costs.PAY_LIFE, amount=o.life, text=f"Pay {o.life} life")) is not None)
    return costs.AbilityCost(components=parts, life=sum(o.life for o in optional)) if parts else None


FREE_KICKS = 6  # (the most times a multikicker cost is offered to a free cast: the table menu's own, frontend rulesMenu.ts MULTIKICKER_COUNTS)


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
    out: list[tuple[str, str]] = []
    if (kick := kicker_cost(ch.abilities)) is not None and not kick.entwine:  # (702.42a: entwine by hand)
        for n in range(1, FREE_KICKS + 1 if kick.multi else 2):
            try:
                total = spell_cost(plan.state, card, ch, 0, plan.info, player=plan.actor, free=alt is None,
                                   alternative=M.parse_cost(alt) if alt is not None else None, kicker=n)
            except ActionError:
                break  # (a kicker cost Fyodor can't pay)
            if not can_pay(plan.state, plan.actor, total, plan.info, purpose=Purpose(spell=ch, card=card.id, zone=card.zone, player=plan.actor,
                                                                                      kicked=True)):
                break
            if (more := kicker_parts(ch, n)) is not None and not any(c.kind in _HAND_PARTS for c in more.components) \
                    and additional_problem(plan, more, card, plan.actor):
                break  # (-- cast keywords (wave 43D) -- a "Kicker—Sacrifice a land." with nothing to sacrifice; a part paid from the hand is always offered: no omission tells)
            out.append((f"kicker:{n}", kick.text if n == 1 else f"{kick.text}, paid {n} times"))
    for o in cost_changes.optional_offers(plan.state, plan.actor, card, ch, plan.info):
        if not o.kind:
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
           resume=_announcing(plan, "free_optional", a), source=card)
    return True


def announce_free_x(plan: Plan, a: A.CastSpell, card: CardInstance, ch: Characteristics) -> bool:
    """-- cast keywords (wave 43D) -- 107.3a: a free cast whose alternative cost (miracle, madness) or kicker cost has {X} announces X with it (107.3b's 0
    is for the spell's own mana cost): asked privately, up to what the caster's mana pays. True while the question waits; its answer re-runs the cast."""
    r = plan.rules
    pending = r.free_cast_then
    paid = pending is not None and pending["card"] == card.id and bool(pending["e"].get("paid"))  # (707.12: a copy's mana cost is paid with X = 0)
    alt = None if paid else r.alt_costs.get(card.id)
    kick = kicker_cost(ch.abilities) if a.kicker and not plan.manual(card) else None
    if a.x_value is not None or not ((kick is not None and kick.x) or (alt is not None and M.parse_cost(alt).x)):
        return False
    options: list[DecisionOption] = []
    for n in range(41):  # ponytail: X is offered up to 40
        total = spell_cost(plan.state, card, ch, n, plan.info, player=plan.actor, free=alt is None,
                           alternative=M.parse_cost(alt) if alt is not None else None, kicker=a.kicker)
        if not can_pay(plan.state, plan.actor, total, plan.info, purpose=Purpose(spell=ch, card=card.id, zone=card.zone, player=plan.actor,
                                                                                  kicked=bool(a.kicker))):
            break
        options.append(DecisionOption(id=f"x:{n}", label=str(n)))
    decide(plan, player=plan.actor, kind="choose_one", prompt=f"{ch.name or 'This spell'}: choose a value for X (107.3a)",
           options=options or [DecisionOption(id="x:0", label="0")], resume=_announcing(plan, "free_x", a), source=card)
    return True


def resume_free_x(plan: Plan, d: Any, chosen: list[str]) -> None:
    """The caster's X: the cast goes on with it announced."""
    from app.rules.engine import INTENTS  # the engine imports this module

    intent = A.parse_action(d.resume["intent"])
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
    r = plan.rules
    if card.id not in r.free_casts or card.zone == STACK or ch.is_land:
        raise ActionError("You can't cast that without paying its mana cost now")
    pending = r.free_cast_then  # (review 28A) only the half / face the effect's choice named; a cascaded, suspended … card is cast as it is
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
    # -- static wordings (wave 6E) -- 118.9d: a choice of additional costs is still announced (601.2b) and paid
    from app.rules import alt_costs, cost_changes, either_costs

    either = None if plan.manual(card) else either_costs.announce(plan, a, card, ch)
    if either is either_costs.WAITING:
        return
    if announce_free_optional(plan, a, card, ch):  # -- free-cast optional costs (wave 41D) -- 118.9d, 601.2b: kicker, bargain, gift, casualty … are announced too
        return
    if announce_free_x(plan, a, card, ch):  # -- cast keywords (wave 43D) -- 107.3a: "Kicker {X}" kicked on a free cast, a miracle cost with {X}: X is announced with it
        return
    if M.parse_cost(ch.mana_cost).x and (limited := cast_limits.cast_problem(plan.state, plan.actor, card, ch, plan.info, resolving=True, announced=a.x_value or 0)):
        raise ActionError(limited)  # -- review 38 -- 601.2e, 107.3b: X is 0 unless a miracle cost with {X} announced it
    definition = None if plan.manual(card) else scripts.spell_definition(ch)
    definition = per_opponent.for_cast(plan, card.id, definition)  # -- per-opponent targets (wave 23A) --
    aura = None if plan.manual(card) else attachments.enchant_selector(ch)
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
    # 118.9d / 601.2b: a spell's own additional cost ("As an additional cost to cast this spell,
    # sacrifice a creature": Fling cast by cascade) is still paid — chosen now, paid with the rest
    add_cost = None if plan.manual(card) else costs.spell_additional_cost(ch.abilities)
    if either is not None:  # -- static wordings (wave 6E) --
        add_cost = either if either.components else None
    if (optional_more := optional_parts(optional)) is not None:  # -- free-cast optional costs (wave 41D) -- paid with the rest (601.2h)
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
    cost = spell_cost(plan.state, card, ch, 0 if paid else (a.x_value or 0), plan.info, player=plan.actor, free=alt is None,
                      alternative=M.parse_cost(alt) if alt is not None else None, kicker=a.kicker,
                      targets=tuple(t.id for t in chosen),  # (wave 4I: "spells that target …")
                      additional=(*((M.parse_cost(either.mana),) if either is not None and either.mana else ()), *mode_costs),  # (wave 6E)
                      reduce=cost_payment.reduction(add_cost, add_objects) if add_cost is not None else 0)  # (wave 47C: 118.9d, 601.2f)
    cost = cost_changes.reduce_only(cost, tuple(o.mana for o in optional if o.mana))  # (wave 41D, as the cast with its cost)
    was_locked = plan.locked_cost is not None
    cost = _locked(plan, cost)  # (wave 4I: 601.2f)
    if paid and pending is not None and pending["e"].get("spend"):  # -- cast-permission riders (wave 38C) -- 118.14: "…, and mana of any type can be spent to cast that spell" (Quistis)
        cost = M.spend_as(cost, pending["e"]["spend"])
    if alt is not None or not cost.is_free:
        purpose = Purpose(spell=ch, zone=card.zone, player=plan.actor, kicked=bool(a.kicker))
        announced_cost = announce_phyrexian(plan, a, cost, ch.name or "it", exclude=not_mana, purpose=purpose, trusted=was_locked)  # (wave 50B: 601.2b)
        if announced_cost is None:
            return
        cost = announced_cost
        if payment_step(plan, a, cost, ch.name or "it", exclude=not_mana, purpose=purpose):
            return
        kind = "miracle" if card.id in r.miracled else "madness"  # -- casting extras (wave 18E) -- 702.94a: its miracle cost
        record = pay_spell(plan, a, card, ch, cost, f"paid {cost.text()} for {ch.name}" + (f" ({kind})" if alt and not paid else ""),
                           not_mana=not_mana)
        record.alternative = "" if paid else kind if alt is not None else "free"
        r.alt_costs.pop(card.id, None)
    else:
        record = PaymentRecord(card=card.id, controller=plan.actor, alternative="free")
    record.additional = (["kicker"] if a.kicker else []) + [f"optional:{o.source}" for o in optional]  # -- free-cast optional costs (wave 41D) --
    record.kicked = a.kicker or int(gift_to is not None or bargained)  # (702.33d; a promised gift and a bargain read as kicked, as with the cost: 702.174k, 702.166)
    record.gift_to = gift_to
    was_suspended = card.id in r.suspended
    from_hand = card.zone == zone_key(plan.actor, "hand")
    _note_cast(plan, record, card.zone.rsplit(":", 1)[-1])  # -- refused modal/conditional (wave 3R1) --
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
        cost_payment.pay(plan, add_cost, card, add_objects, record)  # sacrifice, discard, exile …
        plan.reserved_life = 0  # (wave 29C)
    plan.do({"type": "set_stack_info", "card_id": card.id,
             "tags": ([] if paid else [f"Cast for its {kind} cost" if alt is not None else "Cast without paying its mana cost"])
             + (["Kicked" if a.kicker == 1 else f"Kicked ×{a.kicker}"] if a.kicker else []) + (["Bargained"] if bargained else [])})
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
    extra = 0 if plan.manual(card) else _granted_cascade(plan, card, ch, record.cast_from)
    if extra or ("cascade" in ch.keywords and not plan.manual(card)):
        _cascade_triggers(plan, card, ch, extra)
    if not plan.manual(card):
        _storm_triggers(plan, card, ch, record.cast_from)
        _ripple_triggers(plan, card, ch, record.cast_from)
        _conspire_trigger(plan, card, ch, record)  # (wave 41D: casualty 702.153a, conspire 702.78a)
        _demonstrate_trigger(plan, card, ch)  # (wave 43D)
    if "replicate" in ch.keywords and not plan.manual(card):  # (wave 15E)
        _replicate_trigger(plan, card, ch, a.kicker)
    if definition is not None and picked and not slot_specs and any(definition["modes"][i].get("groups") for i in picked):
        r.stack[card.id] = StackEntry(kind="spell", controller=plan.actor, source_card=card.id, source_object=plan.oid(card),
                                      name=ch.name, effects=modal_effects(definition, picked, True), x=a.x_value, modes=picked,
                                      **picked_targets.entry(None), kicked=record.kicked)
    elif definition is not None and picked:
        effects_in_order = modal_effects(definition, picked, False)
        r.stack[card.id] = StackEntry(kind="spell", controller=plan.actor, source_card=card.id, source_object=plan.oid(card),
                                      name=ch.name, effects=effects_in_order, targets=chosen, target_spec=None,
                                      x=a.x_value, modes=picked, slots=slots, slot_specs=slot_specs, kicked=record.kicked)
    elif definition is not None:
        r.stack[card.id] = StackEntry(kind="spell", controller=plan.actor, source_card=card.id, source_object=plan.oid(card),
                                      name=ch.name, effects=list(definition["effects"]), x=a.x_value,
                                      **picked_targets.entry(definition), kicked=record.kicked)
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
        elif keyword_cost(ch, "foretell", FORETELL, a.ability) is not None and not plan.manual(card):
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
        unearth_cost = keyword_cost(ch, "unearth", UNEARTH, a.ability)
        ability = next((ab for ab in ch.abilities if ab.index == a.ability), None)
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
        raise ActionError("That card has no ability to use from the command zone")
    ch = plan.ch(card)
    # -- activation wordings (wave 7B) -- 602.2: "Any player may activate this ability."
    ab = next((x for x in ch.abilities if x.index == a.ability), None)
    if not card.zone.endswith(":battlefield") or (card.controller != plan.actor and not (
            ab is not None and any_player(ab, ability_cost(ch, ab, state=plan.state, card=card, info=plan.info)))):
        raise ActionError("You can only activate abilities of permanents you control")
    if "cant_activate" in ch.imposed:  # an Aura: "its activated abilities can't be activated" (crew, equip too)
        raise ActionError(f"{ch.name}’s activated abilities can't be activated")
    ability = _find_ability(ch, a.ability)
    if "cant_activate_nonmana" in ch.imposed and ability.kind != "mana":  # -- attached events (wave 16F) -- Faith's Fetters (605.1a)
        raise ActionError(f"{ch.name}’s activated abilities can't be activated unless they're mana abilities")
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
    if ability_taxes(plan.state, plan.info) and mana_ability_taxed(plan.state, card, ch, parsed, plan.info):  # (review 4R)
        raise ActionError(f"Another effect changes the cost of {ch.name}’s mana ability: activate it by hand with the table tools")
    if parsed.tap and not can_use_tap_abilities(plan.state, card, ch, plan.info):
        raise ActionError(f"{ch.name} is tapped" if card.tapped else f"{ch.name} has summoning sickness")
    if parsed.chooses:  # -- refused copy/mana (wave 3R3) --
        _activate_choosing(plan, card, ch, parsed, a)
        return
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
    if "Activate only as an instant" in ability.text:
        raise ActionError(f"{ch.name} can only be activated when you have priority (not while paying a cost)")
    cost = parse_ability_cost(parsed.extra_cost, card_name=ch.name)
    if cost.mana:
        raise ActionError(f"Activate {ch.name}’s mana ability before you start paying (it has a mana cost of its own)")
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
    if card is None or card.controller != plan.actor or not card.zone.endswith(":battlefield"):
        raise ActionError("Tap mana sources you control")
    d = plan.rules.decision
    if d is not None and any(c["card"] == card.id for c in ((d.resume or {}).get("intent") or {}).get("contributions") or []):
        raise ActionError(f"{card.name or 'That card'} is already paying part of the cost (click it again to take it back)")
    ch = plan.ch(card)
    ability = _find_ability(ch, a.ability)
    parsed = dict(mana_abilities(plan.state, card, plan.info)).get(a.ability) if ability.kind == "mana" else None
    if parsed is None:
        raise ActionError("While paying you can only tap for mana")
    if ability_taxes(plan.state, plan.info) and mana_ability_taxed(plan.state, card, ch, parsed, plan.info):  # (review 4R)
        raise ActionError(f"Another effect changes the cost of {ch.name}’s mana ability: activate it by hand with the table tools")
    if parsed.tap and not can_use_tap_abilities(plan.state, card, ch, plan.info):
        raise ActionError(f"{ch.name} is tapped" if card.tapped else f"{ch.name} has summoning sickness")
    if parsed.chooses:  # -- nested payment choices (wave 28D) -- 605.3a, 601.2g-h: the costs it chooses are paid in a prompt nested in this one
        _activate_choosing_nested(plan, card, ch, ability, parsed, a)
        return
    options = parsed.options
    chosen = next((o for o in options if o == (a.mana_choice,)), None) if a.mana_choice else None
    produce(plan, card, parsed, chosen or (options[0] if len(options) == 1 else _best_option(plan, options)), a.ability)
    after_tapping(plan)


# -- other activated abilities (they use the stack) -----------------------------------------
def ability_cost(ch: Characteristics, ability: AbilityText, *, state: GameState | None = None,
                 card: CardInstance | None = None, info: CardInfo | None = None, target: str | None = None) -> AbilityCost:
    cost = parse_ability_cost(ability.cost or "", card_name=ch.name, loyalty=ability.kind == "loyalty")
    if state is not None and card is not None and info is not None and ability.kind == "activated":
        # -- costs (wave 3$) -- "Activated abilities of creatures you control cost {2} less to activate" (601.2f)
        # (wave 4I: a cost with no mana in it can be increased too: "{T}: …" taxed {2} is "{2}, {T}: …")
        # -- cost changers (wave 4I) -- and the ability's own "This ability costs {1} less to activate for each …" (602.2b)
        from app.rules import cost_changes  # (a leaf over this module)

        if ability.text.startswith("Power-up — "):  # -- counters (wave 7C) -- 702.193a: reduced by its mana cost this turn
            from app.rules import power_up

            cost = replace(cost, mana=power_up.reduced(state, card, ch, cost.mana) or "")
        own = cost_changes.ability_delta(state, card.controller, card, ch, ability.text, info) \
            if "This ability costs " in ability.text else 0
        reduced = permissions.ability_mana(state, card.controller, card, ch, cost.mana, info, own, ability.text, target)
        if reduced != cost.mana:
            cost = replace(cost, mana=reduced)
        from app.rules import (
            cast_limits,  # -- casting costs (wave 22F) -- 609.4b: "spend mana as though it were mana of any color" on abilities
        )

        if cost.mana and (mode := cast_limits.ability_spend_mode(state, card.controller, card, ch, info)):
            cost = replace(cost, mana=M.spend_as(M.parse_cost(cost.mana), mode).text())
    # -- reanimation (wave 3R) -- 113.6m: "{1}{B}: Return this card from your graveyard to the battlefield" moves the
    # card out of the graveyard, so the ability works only there
    # (review 40: anywhere in the effect, "Exile five target cards from an opponent's graveyard. Return this card from your graveyard to your hand." on
    # Lochmere Serpent; ponytail: no card's earlier part puts it into the graveyard first, the 113.6m exception)
    if ability.kind == "activated" and ":" in ability.text and (_GRAVEYARD_SELF.search(ability.text.split(":", 1)[1].strip().replace(ch.name, "~"))
                                                                 or "Activate only if this card is in your graveyard" in ability.text):
        cost = replace(cost, graveyard_only=True,  # (review 20E: Glory's "Activate only if this card is in your graveyard.", 113.6m)
                       exile_too=_GRAVEYARD_OR_EXILE.match(ability.text.split(":", 1)[1].strip().replace(ch.name, "~")) is not None)  # (wave 42C)
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
    r = state.rules
    if r is None:
        return "Rules automation is off"
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
    elif not card.zone.endswith(":battlefield") or (card.controller != player and not any_player(ability, cost)):  # (wave 7B)
        return "You can only activate abilities of permanents you control"
    if cost.unsupported:
        return f"Pay “{', '.join(cost.unsupported)}” by hand with the table tools"
    if "cant_activate" in ch.imposed or ("cant_activate_nonmana" in ch.imposed and ability.kind != "mana"):
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
        if cost.loyalty is not None and cost.loyalty < 0 and card.counters.get("loyalty", 0) < -cost.loyalty:
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
    if cost.tap and not can_use_tap_abilities(state, card, ch, info):
        return f"{ch.name} is tapped" if card.tapped else f"{ch.name} has summoning sickness"
    for kind, n in cost.remove_counters:
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
        mana = M.parse_cost(cost.mana).with_x(x)
        for _, comp in cost.choices:  # -- activated sweep (wave 17B) -- waterbend: the untapped artifacts and creatures that could help
            if comp.kind == "WATERBEND":
                helpers = len(cost_payment.candidates(Plan.view(state, player, info), comp, player, card))
                mana = mana.plus_generic(-min(comp.amount, helpers))
        if not can_pay(state, player, mana, info, exclude=(card.id,) if cost.tap else (),
                       purpose=Purpose(ability_of=ch, cost_x="{X}" in cost.mana, special=_special(ability))):
            return f"Not enough mana to pay {mana.text()}"
    return None


def _special(ability: AbilityText) -> str | None:
    """-- mana for special abilities (wave 19E) -- the kind of ability "Spend this mana only to activate an equip ability / power-up
    abilities" asks about (702.6 equip; 702.193 power-up)."""
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

    return plan.rules.once_per_turn.get(f"activated:{plan.actor}:{act}") != plan.state.turn.number and cast_limits.first_alt(plan.state, plan.actor, act, plan.info)


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
        return AbilityText(index=a.ability, kind="activated", cost=side, special="equip", text=f"{side}: Attach {ch.name} to target creature you control. "
                           "Activate only as a sorcery.")

    given = next((c.cards[0] for c in a.cost_choices if c.component == costs.EITHER_SLOT and c.cards), None)
    if given is not None:
        i = int(given[7:]) if given.startswith("either:") and given[7:].isdigit() else -1
        if not 0 <= i < len(sides):
            raise ActionError("Choose one of the costs of the equip ability")
        return sides[i]
    if cycling:  # -- first activation (wave 48D) -- the mana sides of a cycling cost: each is offered if it can be paid (mana is public)
        paid = []
        problems = [None if can_pay(plan.state, plan.actor, M.parse_cost(permissions.ability_mana(plan.state, plan.actor, card, ch, side, plan.info)).with_x(0), plan.info,
                                    purpose=Purpose(ability_of=ch, cost_x="{X}" in side)) else "Not enough mana" for side in sides]
        offered = [i for i, why in enumerate(problems) if why is None]
    else:
        paid = [ability_cost(ch, ability_of(side), state=plan.state, card=card, info=plan.info) for side in sides]
        problems = [ability_problem(plan.state, plan.actor, card, ch, ability_of(side), cost, check_priority=False, info=plan.info, plan=plan)
                    for side, cost in zip(sides, paid, strict=True)]
        offered = [i for i, cost in enumerate(paid) if problems[i] is None or any(c.kind in _HAND_PARTS for c in cost.components)]
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
    from app.rules import modal_abilities  # (a leaf module over this one)
    from app.rules.engine import advance  # the engine imports this module

    cost = ability_cost(ch, ability, state=plan.state, card=card, info=plan.info, target="?")  # (wave 46C: the best case until the targets are chosen, below)
    problem = ability_problem(plan.state, plan.actor, card, ch, ability, cost, plan=plan)
    if problem:
        raise ActionError(problem)
    oid = plan.oid(card)  # the object activating (paying a cost may move it: it'd be a new object)
    mana = M.parse_cost(cost.mana)
    was_locked = plan.locked_cost is not None
    if plan.locked_cost is not None and not mana.x:  # -- cost changers (wave 4I) -- 602.2b → 601.2f: locked in
        mana = _locked(plan, mana)
    if (mana.x or cost.loyalty_x or cost.energy_x or cost.x_chosen) and a.x_value is None:  # (wave 3E: "Pay X {E}"; x_chosen: wave 4H)
        raise ActionError("Choose a value for X")
    if (every := next((c for c in cost.components if c.every), None)) is not None:
        a.x_value = cost_payment.counters_on(card, every.counter)  # -- activated sweep (wave 26C) -- "Remove all oil counters": all there are now (602.2b)
    if cost.loyalty_x and card.counters.get("loyalty", 0) < (a.x_value or 0):
        raise ActionError(f"{ch.name} doesn't have {a.x_value} loyalty")  # 606.6
    if definition is None:
        definition = None if plan.manual(card) else scripts.definitions(ch).get(ability.index)
    if definition is not None and definition["kind"] != "activated":
        definition = None
    definition = per_opponent.for_cast(plan, card.id, definition)  # -- per-opponent targets (wave 23A) --
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
        exact = ability_cost(ch, ability, state=plan.state, card=card, info=plan.info, target=chosen[0].id if chosen else None)
        if exact.mana != cost.mana:
            mana = M.parse_cost(exact.mana)
    problem = cost_payment.problem(plan, cost, card, plan.actor, a.x_value)  # 118.3 / 601.2h: nothing is paid unless all can be
    if problem:
        raise ActionError(problem)
    cost_objects = cost_payment.choose(plan, a, cost, card, f"{ch.name}’s ability")  # (602.2b → 601.2h)
    if cost_objects is None:
        return  # waiting for the payer's choice; nothing has been paid
    for i, comp in cost.choices:  # -- activated sweep (wave 17B) -- waterbend: each artifact / creature tapped pays for {1} (701.67a)
        if comp.kind == "WATERBEND":
            mana = mana.plus_generic(-len(cost_objects.get(i, [])))
    not_mana = cost_payment.excluded(cost, card, cost_objects)  # (they can't also tap for mana)
    due = mana.with_x(a.x_value or 0)
    if mana.x:  # -- review 35 -- 601.2f (602.2b): X is chosen first (601.2b), then the total is increased and reduced ("Abilities you activate cost {2}
        # less": Zirda, Training Grounds); ability_cost leaves an {X} cost alone (its X isn't known there)
        from app.rules import cost_changes

        own = cost_changes.ability_delta(plan.state, card.controller, card, ch, ability.text, plan.info) if "This ability costs " in ability.text else 0
        due = M.parse_cost(permissions.ability_mana(plan.state, plan.actor, card, ch, due.text(), plan.info, own, ability.text))
    purpose = Purpose(ability_of=ch, cost_x="{X}" in cost.mana, special=_special(ability))
    announced_due = announce_phyrexian(plan, a, due, f"{ch.name}’s ability", exclude=not_mana, purpose=purpose, trusted=was_locked)  # (wave 50B: 602.2b → 601.2b)
    if announced_due is None:
        return
    due = announced_due
    if payment_step(plan, a, due, f"{ch.name}’s ability", exclude=not_mana, purpose=purpose):
        return
    effect = ability.text.split(":", 1)[1].strip() if ":" in ability.text else ability.text
    # -- review (wave 27D) -- 602.2a / 701.20a: a card whose ability is activated from the hand is revealed, so the ability on the stack
    # names it for everyone; the card stays in the hand, anonymous again once the stack object carries its name
    created = _create_ability(plan, card, effect[:500], keep=keep_revealed)
    new_ids = getattr(created, "r", None)
    ability_id = new_ids.ids[0] if new_ids is not None else None
    # Pay the costs (602.2): tap first so the source can't also pay for its own mana cost.
    if cost.tap:
        plan.do({"type": "tap", "card_ids": [card.id], "tapped": True})
    if cost.loyalty or (cost.loyalty_x and a.x_value):
        delta = (cost.loyalty or 0) if not cost.loyalty_x else -(a.x_value or 0)
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
    paid = pay(plan, plan.actor, due, f"paid {due.text()} to activate {ch.name}",
               sources=a.sources, exclude=not_mana, purpose=purpose, life_due=2 * len(a.life_symbols or ()))
    record = PaymentRecord(card=ability_id or card.id, controller=plan.actor, total_cost=ability.cost or "",
                           mana_spent=dict(paid.spent) if paid else {}, life=cost.life + (paid.life if paid else 0),
                           tapped=list(paid.tapped) if paid else [], x=a.x_value)
    cost_payment.pay(plan, cost, card, cost_objects, record)  # sacrifice, discard, exile, return, tap others …
    if ability_id and (record.sacrificed or record.discarded or record.exiled or record.returned or record.tapped_for_cost):
        record_payment(plan, ability_id, record)  # ("the sacrificed creature" …: what paid for it)
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
        r.stack[ability_id] = StackEntry(kind="activated", controller=plan.actor, source_card=card.id, source_object=oid,
                                         name=ch.name, x=a.x_value, optional=bool(definition.get("optional")),  # (wave 34B: 608.2d, asked on resolution)
                                         **picked_targets.entry(definition),
                                         # -- this-turn history (wave 4D) -- "the second time this ability has resolved"
                                         effects=history.counting_activations(history.counting_resolutions(list(definition["effects"]), f"{oid}:{a.ability}"),
                                                                f"{oid}:{a.ability}"))
    if chosen and ability_id:
        from app.rules.triggers import targeted

        targeted(plan, ability_id, plan.actor, chosen)
    if ability.special == "equip":  # -- first activation (wave 48D) --
        _activated(plan, "equip")
    if ability_id:  # -- activation (wave 11F) -- 602.2: "Whenever a player activates an ability …"
        from app.rules.triggers import activated

        activated(plan, card, oid, loyalty=ability.kind == "loyalty", ability_id=ability_id, text=ability.text)
    if ability.kind == "loyalty":
        if r.loyalty_used.get(oid) == plan.state.turn.number:
            r.loyalty_second[oid] = plan.state.turn.number  # -- static_other sweep (wave 19A) -- the second use (Oath of Teferi)
        r.loyalty_used[oid] = plan.state.turn.number
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
    for cid in state.zones.get(zone_key(player, "battlefield"), []):
        card = state.cards[cid]
        if card.controller != player:
            continue
        from app.rules.layers import derive

        ch = derive(state, card, chars.of(card, info), info)
        for ab in ch.abilities:
            if ab.kind in ("activated", "loyalty"):
                problem = ability_problem(state, player, card, ch, ab, ability_cost(ch, ab, state=state, card=card, info=info),
                                          check_priority=check_priority, info=info)
                if problem is None:
                    cost = ability_cost(ch, ab, state=state, card=card, info=info)
                    # (wave 24D) 107.3k: X announced as the ability is activated ("{X}, {T}:", "Sacrifice X …", −X, "Pay X {E}")
                    needs_x = M.parse_cost(cost.mana).x or cost.loyalty_x or cost.energy_x or cost.x_chosen
                    out.append({"card_id": cid, "ability": ab.index, **({"x": True} if needs_x else {})})
            elif ab.kind == "keywords" and _can_crew(state, player, card, ch, ab.index, info, check_priority):
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
    for cid in state.zones.get(zone_key(player, "hand"), []):  # -- keywords (wave 15E) -- ninjutsu (702.49a)
        card = state.cards[cid]
        ch = chars.of(card, info)
        for ab in ch.abilities:
            if (cost_text := ninjutsu.cost_of(ch, ab.index)) is not None:
                made = ninjutsu.ability(ch, ab.index, cost_text)
                if ability_problem(state, player, card, ch, made, ability_cost(ch, made, state=state, card=card, info=info),
                                   check_priority=check_priority, info=info) is None:
                    out.append({"card_id": cid, "ability": ab.index})
    for cid in state.zones.get(zone_key(player, "hand"), []):  # -- X from the triggering object (wave 34C) -- 107.3a: "Cycling {X}{1}{U}" asks for X
        r = state.rules
        if r is not None and (not check_priority or (r.priority == player and r.decision is None)):
            ch = chars.of(state.cards[cid], info)
            out += [{"card_id": cid, "ability": ab.index, "x": True} for ab in ch.abilities
                    if (found := hand_ability(ch, ab.index)) is not None and M.parse_cost(found[1]).x]
    for cid in state.zones.get(zone_key(player, "graveyard"), []):  # 113.6m: "Exile this card from your graveyard: …"
        card = state.cards[cid]
        ch = chars.of(card, info)
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


def produce(plan: Plan, card: CardInstance, ability: M.ManaAbility, option: tuple[str, ...], index: int | None = None) -> None:
    """Activate a mana ability by hand: pay its other costs (mana from the pool or other sources,
    life, counters), add the mana, then its riders."""
    extra = parse_ability_cost(ability.extra_cost, card_name=plan.ch(card).name) if ability.extra_cost else None
    if extra is not None and extra.mana:
        cost = M.parse_cost(extra.mana)
        if payment_mode(plan, card.controller) == "self":
            if not pool_covers(plan.state, card.controller, cost):
                raise ActionError(f"Add {cost.text()} to your mana pool first to activate {plan.ch(card).name}")
            pay(plan, card.controller, cost, f"paid {extra.mana} to activate {plan.ch(card).name}", sources=[])
        else:
            pay(plan, card.controller, cost, f"paid {extra.mana} to activate {plan.ch(card).name}", exclude=(card.id,))
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
             "sacrifice": [card.id] if ability.sacrifice_self else [], **mana_units.added(plan, card, ability, mana),
             "life": 0, "label": f"added {M.symbols(mana)}"}, actor=who)
    if extra and extra.life:  # -- life modifiers (wave 28B) -- 119.4 / 118.11: the life paid is a life loss the replacements may change
        from app.rules import replace as _replace_life

        _replace_life.lose_life(plan, [(who, extra.life)], actor=who)
    emit(plan.state, "mana_added", object_id=oid, card=card.id, player=who, amount=sum(mana.values()),
         counter="tap" if ability.tap else None)  # -- mana riders (wave 5A) -- tapped for mana (106.12a)
    if index is not None:
        after_mana_ability(plan, card, index, ability, who)


# -- refused copy/mana (wave 3R3) -- a mana ability whose cost chooses objects (Ashnod's Altar: "Sacrifice a
# creature: Add {C}{C}."). 605.3a / 602.2b → 601.2h: the player chooses the objects as the cost is paid (a private
# decision, app/rules/cost_payment.py; none chosen cancels), the costs are paid all at once, then the ability
# resolves at once (605.3a: no stack) — a color to choose is chosen then, after the costs (resume "paid").
def _activate_choosing(plan: Plan, card: CardInstance, ch: Characteristics, parsed: M.ManaAbility,
                       a: A.ActivateAbility) -> None:
    from app.rules import costs as C
    from app.rules import removed_mana

    cost = parse_ability_cost(parsed.extra_cost, card_name=ch.name)
    xcost = (parsed.count or "").startswith("xcost:")
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
    option: tuple[str, ...] | None = options[0] if len(options) == 1 else None
    if option is None and a.mana_choice is not None:
        option = next((o for o in options if o == (a.mana_choice,)), None)
        if option is None:
            raise ActionError(f"{ch.name} can't add {{{a.mana_choice}}}")
    if cost.mana:
        mana_cost = M.parse_cost(cost.mana)
        if payment_mode(plan, card.controller) == "self":
            if not pool_covers(plan.state, card.controller, mana_cost):
                raise ActionError(f"Add {mana_cost.text()} to your mana pool first to activate {ch.name}")
            pay(plan, card.controller, mana_cost, f"paid {cost.mana} to activate {ch.name}", sources=[])
        else:
            pay(plan, card.controller, mana_cost, f"paid {cost.mana} to activate {ch.name}",
                exclude=cost_payment.excluded(cost, card, objects))
    record = PaymentRecord(card=card.id, controller=card.controller)
    who = card.controller  # (wave 24D)
    cost_payment.pay(plan, cost, card, objects, record)
    if parsed.tap or parsed.sacrifice_self or cost.life:
        plan.do({"type": "rules_mana", "player": card.controller, "tap": [card.id] if parsed.tap else [],
                 "sacrifice": [card.id] if parsed.sacrifice_self else [], "delta": {}, "life": 0,
                 "label": f"paid to activate {ch.name}"}, actor=card.controller)
        if cost.life:  # -- life modifiers (wave 28B) -- 119.4 / 118.11
            from app.rules import replace as _replace_life

            _replace_life.lose_life(plan, [(card.controller, cost.life)], actor=card.controller)
    if option is None:
        decide(plan, player=plan.actor, kind="choose_one", prompt=f"Which mana should {ch.name} add?",
               options=[DecisionOption(id=str(i), label=M.symbols(_count(o))) for i, o in enumerate(options)],
               resume={"step": "mana_ability", "card": card.id, "ability": a.ability, "paid": True,
                       "options": [list(o) for o in options], "oid": plan.oid(card), "who": who}, source=card)
        return
    _add_paid_mana(plan, card, parsed, option, a.ability, plan.oid(card), who)
    plan.rules.passed = []


def _add_paid_mana(plan: Plan, card: CardInstance, ability: M.ManaAbility, option: tuple[str, ...], index: int,
                   oid: str | None, who: str | None = None) -> None:
    """The mana of an ability whose costs are paid (605.3a), then its riders (as ``produce``)."""
    from app.rules import mana_units

    mana = _count(option)
    who = who or card.controller
    plan.do({"type": "rules_mana", "player": who, "tap": [], "sacrifice": [], **mana_units.added(plan, card, ability, mana),
             "life": 0, "label": f"added {M.symbols(mana)}"}, actor=plan.actor)
    emit(plan.state, "mana_added", object_id=oid, card=card.id, player=who, amount=sum(mana.values()),
         counter="tap" if ability.tap else None)  # -- mana riders (wave 5A) -- tapped for mana (106.12a)
    after_mana_ability(plan, card, index, ability, who)


def _resume_paid_mana(plan: Plan, d: Any, chosen: list[str]) -> None:
    card = plan.state.cards.get(d.resume["card"])
    options = [tuple(o) for o in d.resume["options"]]
    k = int(chosen[0]) if chosen and chosen[0].isdigit() else -1
    if card is None or not 0 <= k < len(options):
        raise ActionError("Choose one of the offered mana")
    found = dict(mana_abilities(plan.state, card, plan.info)).get(int(d.resume["ability"]))
    parsed = found if found is not None else M.ManaAbility(tap=False, sacrifice_self=False, options=tuple(options))
    _add_paid_mana(plan, card, parsed, options[k], int(d.resume["ability"]), d.resume.get("oid"), d.resume.get("who"))
    plan.rules.priority = plan.actor
    plan.rules.passed = []
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
    produce(plan, card, parsed, parsed.options[int(chosen[0])], index)
    plan.rules.priority = plan.actor
    plan.rules.passed = []


# -- responding -------------------------------------------------------------------------
def has_responses(state: GameState, player: str, info: CardInfo) -> bool:
    """Could ``player`` do anything at instant speed right now? (For Arena-style auto-passing.)"""
    for key in (zone_key(player, "hand"), zone_key(player, "command"), zone_key(player, "graveyard"), zone_key(player, "exile"),
                zone_key(player, "foretell")):
        for cid in state.zones.get(key, []):
            card = state.cards[cid]
            ch = chars.of(card, info)
            if ("Instant" in ch.types or ch.has_flash or _flash_granted(state, player, card, ch, info) or flash_if(ch) is not None) \
                    and castable(state, player, card, info, check_priority=False):
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
    from app.rules import licids
    from app.rules.copying import room_printing

    r = state.rules
    main = not instant and state.turn.active_player == player and state.turn.phase in MAIN_PHASES and not state.zones.get(STACK)
    ends = r is not None and any(x.end_cost for x in r.effects)
    for cid in state.zones.get(zone_key(player, "battlefield"), []):
        card = state.cards[cid]
        if card.controller != player:
            continue
        if card.face_down:
            ways = face_up_ways(card, chars.of(card.model_copy(update={"face_down": False}), info))
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
                            state, player, M.parse_cost((half := chars.half_from_data(data, door - 1)).mana_cost), info, purpose=Purpose(ability_of=half)):
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

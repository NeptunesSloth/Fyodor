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
from app.game.rules_state import (
    CostContribution,
    DecisionOption,
    PaymentRecord,
    StackEntry,
    TargetRef,
    TurnCount,
    emit,
)
from app.game.state import STACK, CardInstance, GameState, zone_key
from app.rules import attachments, cost_payment, costs, history, permissions, restrictions, scripts
from app.rules import characteristics as chars
from app.rules import commander as cmdr
from app.rules import mana as M
from app.rules import payment as P
from app.rules.activation_words import any_player  # -- activation wordings (wave 7B) --
from app.rules.characteristics import CardInfo, Characteristics
from app.rules import graveyard_keywords, ninjutsu
from app.rules.costs import AbilityCost, kicker_cost, parse_ability_cost
from app.rules.oracle import AbilityText
from app.rules.plan import Plan, decide, require_no_decision, require_priority
from app.rules.targets import choose_groups, legal_targets, source_of
from app.rules.targets import label as target_label
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

    return not extra.unsupported and not extra.activation_only and all(  # (activation_only: wave 4H, 605)
        c.kind in (C.MANA, C.TAP, C.PAY_LIFE) or (c.kind in (C.SACRIFICE, C.REMOVE_COUNTER) and c.selector is None)
        or (c.selector is not None and c.kind in (C.SACRIFICE, C.DISCARD, C.TAP_OTHER, C.EXILE_FROM_GRAVEYARD) and not c.random)
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


def _land_mana(state: GameState, players: list[str], info: CardInfo, *, skip: str) -> set[str]:
    """Types of mana lands these players control could produce (Reflecting Pool, Exotic Orchard)."""
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
    if ab.instead_if and ab.instead_if[0][:1] in (("@count",), ("@power",)):  # -- kicked / instead (wave 4G) --
        return ab.instead if _controls_for_instead(state, card.controller, ab.instead_if[0], info) else ab.options
    if ab.instead_if and all(_controls_subtypes(state, card.controller, need, info) for need in ab.instead_if):
        return ab.instead  # -- refused copy/mana (wave 3R3): Urza's Tower with the Mine and the Power-Plant --
    from app.rules import removed_mana  # -- if you do (wave 6F) -- one option per number removed

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
        elif opt == ("LANDS",):
            out += [(m,) for m in M.ALL_MANA if m in _land_mana(state, [card.controller], info, skip=card.id)]
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
        if parsed.extra_cost:
            extra = parse_ability_cost(parsed.extra_cost, card_name=ch.name)
            energy = extra.energy  # (wave 3E: "{T}, Pay {E}: Add …", 107.14)
            if not (extra.basic or (parsed.chooses and _choice_cost_ok(extra))) or extra.energy_x or \
                    (extra.life and state.players[card.controller].life < extra.life) or \
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
        side, ch = ("cast", spell) if spell is not None else ("ability", source)
        allowed = spec.get(side)
        if ch is None or allowed is None or any(a.get("chosen") for a in allowed if isinstance(allowed, list)):
            return False
        return allowed == "any" or any(M.spend_alt_matches(a, ch) for a in allowed)
    return False


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
def choose_target(plan: Plan, a: A.CastSpell | A.ActivateAbility, definition: dict[str, Any] | None,
                  what: str, *, exclude: tuple[str, ...] = ()) -> list[TargetRef] | None:
    """The target of an automated spell or ability: validated if given, else asked (privately).
    Returns the chosen targets, or None while waiting for the choice."""
    spec = definition.get("target") if definition else None
    if not spec:
        return []
    legal = [t for t in legal_targets(plan, spec["what"], plan.actor, source_of(plan, a.card_id), a.card_id) if t not in exclude]
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

        specs = kicked_instead.applicable(specs, a.kicker)
    found = choose_groups(plan, specs, plan.actor, source_of(plan, a.card_id), a.card_id, list(a.targets),
                          list(a.target_counts), list(a.division), a.x_value, what, exclude)
    if found.ask is not None:
        ask_targets(plan, plan.actor, found, specs, what,
                    {"step": "cast_group", "intent": a.model_dump(mode="json", exclude={"r", "actor", "ts"}),
                     "counts": found.counts})
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
        decide(plan, player=player, kind="choose_cards",
               prompt=f"Choose {count} target{'s' if hi != 1 else ''} for {what}" + (f" (group {g + 1} of {len(specs)})" if many else ""),
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


def _controls_commander(plan: Plan, player: str) -> bool:
    return any(c.commander_key is not None and c.controller == player and c.zone.endswith(":battlefield")
               for c in plan.state.cards.values())


def choose_modes(plan: Plan, a: A.CastSpell | A.ActivateAbility, definition: dict[str, Any], what: str,
                 *, exclude: tuple[int, ...] = ()) -> list[int] | None:
    """700.2a / 601.2b: the modes of a modal spell (or activated ability: 602.2b), validated if given,
    else asked. A mode whose target can't be chosen can't be chosen (700.2a). ``exclude``: modes that
    can't be chosen either ("choose one that hasn't been chosen"). Returns None while waiting."""
    modal, modes = definition["modal"], definition["modes"]
    lo, hi, repeat = modal["min"], modal["max"], modal["repeat"]
    if modal.get("condition") == "commander" and _controls_commander(plan, plan.actor):
        hi = 2  # "If you control a commander as you cast this spell, you may choose both instead."
    src = source_of(plan, a.card_id)
    allowed = [i for i, m in enumerate(modes) if i not in exclude
               and (not m["target"] or legal_targets(plan, m["target"]["what"], plan.actor, src, a.card_id))]
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
           min_choices=lo, max_choices=hi,
           resume={"step": "cast_modes", "intent": a.model_dump(mode="json", exclude={"r", "actor", "ts"})})
    return None


def resume_cast_modes(plan: Plan, d: Any, chosen: list[str]) -> None:
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
    src = source_of(plan, a.card_id)
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
               resume={"step": "cast_slot_target", "intent": a.model_dump(mode="json", exclude={"r", "actor", "ts"})})
        return None
    return out


def resume_cast_slot_target(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules.engine import INTENTS  # the engine imports this module

    intent = A.parse_action(d.resume["intent"])
    intent.targets = [*intent.targets, chosen[0]]  # type: ignore[union-attr]
    plan.rules.priority = d.player
    plan.rules.passed = []
    INTENTS[intent.type](plan, intent)


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
    if extra is not None and extra.energy:  # (wave 3E: "{T}, Pay {E}: Add one mana of any color", 107.14)
        plan.do({"type": "resource", "player": card.controller, "key": "energy", "delta": -extra.energy}, actor=card.controller)
    for kind, n in ability.riders:
        if kind == "damage" and _player_protected(plan, card):  # -- player shields (wave 5E) -- 702.16e, 702.16j
            plan.note(f"Protection prevents the damage {plan.ch(card).name} would deal to {plan.name(card.controller)}")
        elif kind == "damage":
            plan.do({"type": "rules_damage", "creatures": {}, "players": {card.controller: n}, "planeswalkers": {},
                     "lifelink": {}, "combat": False,
                     "dealt": [{"source": plan.oid(card.id), "target": card.controller, "amount": n}]}, actor=card.controller)
        elif kind == "draw":
            plan.do({"type": "draw", "player": card.controller, "count": n}, actor=card.controller)
        else:  # -- mana riders (wave 5A) -- "You gain 2 life.", "Each opponent gains 1 life."
            from app.rules import mana_riders

            mana_riders.after(plan, card, kind, n)


def _player_protected(plan: Plan, card: CardInstance) -> bool:
    """-- player shields (wave 5E) -- does the controller's protection prevent the damage this mana source deals them?"""
    from app.rules import player_shields, source_shields
    from app.rules import replace as replacements

    if player_shields.protected_from(plan, card.controller, plan.ch(card)) is None:
        return False
    ev = {"source_card": card.id, "source_oid": plan.oid(card.id), "target": card.controller, "combat": False,
          "src": replacements.source_info(plan, card.id, plan.oid(card.id), plan.ch(card), card.controller)}
    return source_shields.protection_applies(plan, ev)


def pay(plan: Plan, player: str, cost: M.ManaCost, label: str, *, sources: list[str] | None = None,
        exclude: tuple[str, ...] = (), purpose: Purpose | None = None) -> M.Payment | None:
    if cost.is_free and not sources:
        return None
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
    oids = {card.id: plan.oid(card) for card, _, _ in extras}  # (wave 5A: the objects as they were tapped)
    plan.do({"type": "rules_mana", "player": player, "tap": payment.tapped, "sacrifice": payment.sacrificed,
             "delta": payment.delta(), "life": life, "label": label}, actor=player)
    for card, index, ability in extras:
        # -- mana riders (wave 5A) -- counter "tap": tapped for mana (106.12a: an ability with {T} in its cost)
        emit(plan.state, "mana_added", object_id=oids[card.id], card=card.id, player=player,
             counter="tap" if ability.tap else None)
        after_mana_ability(plan, card, index, ability)
    payment.life = life
    return payment


def _auto_helpers(plan: Plan, cost: M.ManaCost, spell: Characteristics, spell_card: str) -> list[P.Helper]:
    """The engine pays (AUTO/ASK — tests and the sandbox payer): use convoke / improvise / delve
    only when mana alone can't pay, choosing them with the castability solver."""
    state, player = plan.state, plan.actor
    if not helper_kinds(spell, state, player, spell_card, plan.info) or can_pay(state, player, cost, plan.info,
                                                                               purpose=Purpose(spell=spell)):
        return []
    plain = [s for s in mana_sources(state, player, plan.info, Purpose(spell=spell)) if s.activation is None]
    try:
        found = M.solve(cost, dict(state.players[player].mana),
                        _helper_sources(state, player, plan.info, spell, spell_card, plain), life=state.players[player].life)
    except M.ManaError:
        return []
    kinds = {v: k for k, v in HELPER_ABILITY.items()}
    return helpers_for(state, player, plan.info, spell, spell_card,
                       [{"kind": kinds[i], "card": cid} for cid, i in found.used if i < 0])


def pay_spell(plan: Plan, a: A.CastSpell, card: CardInstance, ch: Characteristics, cost: M.ManaCost,
              label: str, *, not_mana: tuple[str, ...] = ()) -> PaymentRecord:
    """601.2h: pay a spell's locked-in total cost — the convoke / improvise / delve contributions
    (each paying one symbol, 702.51a / 702.126a / 702.66a) and mana for everything else — all at
    once. Returns how it was paid; contributions are not mana spent."""
    player = plan.actor
    purpose = Purpose(spell=ch)
    if a.contributions:
        helpers = helpers_for(plan.state, player, plan.info, ch, card.id, [c.model_dump() for c in a.contributions])
    elif a.sources is None and payment_mode(plan, player) != "self":
        helpers = _auto_helpers(plan, cost, ch, card.id)
    else:
        helpers = []
    if any(h.card in not_mana for h in helpers):  # (wave 3$) an object an additional cost uses can't also help pay
        raise ActionError("A permanent that pays the additional cost can't also convoke / improvise")
    exclude = tuple(h.card for h in helpers) + not_mana

    def covers(rest: M.ManaCost) -> bool:
        if rest.is_free:
            return True
        try:
            find_payment(plan.state, player, rest, plan.info, sources=a.sources, exclude=exclude, purpose=purpose)
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
    payment = pay(plan, player, rest, label, sources=a.sources, exclude=exclude, purpose=purpose)
    return PaymentRecord(card=card.id, controller=player, total_cost=cost.text(),
                         mana_spent=dict(payment.spent) if payment else {}, contributions=contributions,
                         life=payment.life if payment else 0, tapped=list(payment.tapped) if payment else [],
                         sacrificed=list(payment.sacrificed) if payment else [], x=a.x_value)


# -- refused modal/conditional (wave 3R1) --
def _note_cast(plan: Plan, record: PaymentRecord, zone: str) -> None:
    """How a spell was cast, on its payment record: the zone it was cast from ("if you cast it from your hand",
    "if this spell was cast from a graveyard") and whether it was cast during its caster's own main phase
    (addendum: "if you cast this spell during your main phase" — 505.1: a main phase of the caster's turn)."""
    record.cast_from = zone
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


def payment_step(plan: Plan, a: A.CastSpell | A.ActivateAbility, cost: M.ManaCost, what: str, *,
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
        if _covered(plan, plan.actor, cost, helpers) is not None:
            a.sources = []
            return False
        ask_to_tap(plan, cost, what, {"step": "pay_mana", "intent": a.model_dump(mode="json", exclude={"r", "actor", "ts"}),
                                      "exclude": list(exclude), "cost": cost.text(), "what": what})
        return True
    if mode == "auto":
        return False
    payment = find_payment(plan.state, plan.actor, cost, plan.info, exclude=exclude, purpose=purpose)  # (can it be paid at all?)
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


def pool_covers(state: GameState, player: str, cost: M.ManaCost) -> bool:
    """Can ``cost`` be paid from the player's mana pool alone (plus life for Phyrexian mana)?"""
    try:
        M.solve(cost, dict(state.players[player].mana), [], life=state.players[player].life)
    except M.ManaError:
        return False
    return True


def pay_from_pool(plan: Plan, player: str, cost: M.ManaCost, label: str, *, purpose: Purpose | None = None) -> None:
    """Pay from the mana pool only (players tap their own lands), or explain what's missing."""
    if not cost.is_free and payment_mode(plan, player) == "self":
        if not pool_covers(plan.state, player, cost):
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


def _covered(plan: Plan, player: str, cost: M.ManaCost, helpers: list[P.Helper]) -> list[str] | None:
    """How the committed helpers pay part of ``cost`` so that the mana pool pays the rest, or None."""
    p = plan.state.players[player]
    return P.assign(cost, helpers, P.pool_pays(dict(p.mana), p.life))


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
    assignment = _covered(plan, player, cost, helpers) or P.assign(cost, helpers) or []
    paid = [{"card": h.card, "name": plan.state.cards[h.card].name or "a card", "kind": h.kind, "pays": sym}
            for h, sym in zip(helpers, assignment, strict=False)]
    rest = P.remaining(cost, assignment) if len(assignment) == len(helpers) else cost
    return {"kind": "tap_mana", "cost": cost.text(), "what": what, "sources": sources[:40],
            "convoke": by_kind["convoke"][:40], "improvise": by_kind["improvise"][:40], "delve": by_kind["delve"][:60],
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
    if _covered(plan, d.player, M.parse_cost(d.resume["cost"]), _prompt_helpers(plan, d.player, d.resume)) is None:
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
    if _covered(plan, d.player, cost, _prompt_helpers(plan, d.player, resume)) is not None:
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
    needed = set(cost.colored) | {c for h in cost.hybrid for c in h} | set(cost.phyrexian)
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
            purpose: Purpose | None = None) -> bool:
    everything = [s for s in mana_sources(state, player, info, purpose) if s.card_id not in exclude]
    if purpose is not None and purpose.card is not None \
            and helper_kinds(purpose.spell, state, player, purpose.card, info):  # (a hint: never paid here)
        assert purpose.spell is not None
        everything = _helper_sources(state, player, info, purpose.spell, purpose.card, everything)
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


def from_graveyard(card: CardInstance, player: str, ch: Characteristics, state: GameState | None = None) -> bool:
    """Casting with flashback: from your own graveyard, when it has a (mana) flashback cost — its
    own, or (wave 3R2, ``state``) one an effect gave it this turn (app/rules/graveyard_grants.py)."""
    if card.zone != zone_key(player, "graveyard") or card.owner != player:
        return False
    return flashback_cost(ch) is not None or (state is not None and _granted_flashback(state, card, ch) is not None)


def _granted_flashback(state: GameState, card: CardInstance, ch: Characteristics) -> str | None:
    """-- refused grants/replacements (wave 3R2) -- "… gains flashback until end of turn" (Snapcaster Mage)."""
    from app.rules import graveyard_grants

    return graveyard_grants.flashback_cost(state, card, ch)


MORPH = re.compile(r"^(?P<kind>morph|megamorph) (?P<cost>(?:\{[^}]+\})+)$", re.IGNORECASE)
FACE_DOWN = chars.face_down_characteristics("morph")  # (708.2a; disguise: chars.face_down_characteristics)


def morph_cost(ch: Characteristics) -> tuple[str, str] | None:
    """702.37 morph / megamorph with a mana cost: (kind, cost), from the printed card."""
    for ab in ch.abilities:
        if ab.kind == "keywords" and ({"morph", "megamorph"} & set(ab.keywords)):
            m = MORPH.fullmatch(ab.text.strip().rstrip("."))
            if m:
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
    cost = M.parse_cost(cost_text)
    if payment_mode(plan, plan.actor) == "self":
        pay_from_pool(plan, plan.actor, cost, f"paid {cost.text()} to turn {printed.name} face up",
                      purpose=Purpose(ability_of=printed))
    else:
        if not can_pay(plan.state, plan.actor, cost, plan.info, purpose=Purpose(ability_of=printed)):
            raise ActionError(f"Not enough mana to pay {cost.text()}")
        pay(plan, plan.actor, cost, f"paid {cost.text()} to turn {printed.name} face up", sources=a.sources,
            purpose=Purpose(ability_of=printed))
    plan.do({"type": "face_down", "card_ids": [card.id], "face_down": False})
    emit(plan.state, "turned_face_up", object_id=plan.oid(card), card=card.id, player=plan.actor)
    from app.rules import triggers  # (triggers imports this module)

    face_up = plan.ch(plan.state.cards[card.id])
    if not plan.manual(card):  # "When ~ is turned face up, …" (702.37e: not "enters" abilities, 708.8)
        for i, d in triggers.abilities(plan, face_up, "turned_face_up_self"):
            triggers._add(plan, controller=card.controller, source_card=card.id, source_object=plan.oid(card),
                          name=face_up.name, index=i, definition=d)
    for other in list(plan.state.cards.values()):  # "Whenever a permanent you control is turned face up, …"
        if other.zone == card.zone and other.controller == card.controller and not other.face_down and not plan.manual(other):
            och = plan.ch(other)
            for i, d in triggers.abilities(plan, och, "turned_face_up_you"):
                triggers._add(plan, controller=other.controller, source_card=other.id, source_object=plan.oid(other),
                              name=och.name, index=i, definition=d)
    plan.rules.passed = []
    if kind == "megamorph":  # 702.37b, 708.11: the counter is put on as it's turned face up (the counter choke point)
        from app.rules import replace as replace_effects

        replace_effects.put_counters(plan, [(card.id, "+1/+1", 1)], by=plan.actor, then={"do": "face_up_done"})


def from_command_zone(card: CardInstance, player: str) -> bool:
    return card.zone == zone_key(player, "command") and card.commander_key is not None and card.owner == player


def cast_grant(state: GameState, player: str, card: CardInstance, ch: Characteristics, info: CardInfo | None, *,
               free: bool = False) -> permissions.Grant | None:
    """How ``player`` may cast this card from where it is (601.3): from their hand, their commander
    from the command zone, flashback from their graveyard, or a permission (app/rules/permissions):
    a static ability on the table or one an effect granted. ``free``: they want to use a "without
    paying its mana cost" permission (118.9) — an alternative cost, which is optional (118.9b), so
    it is never applied to a plain cast: without the opt-in only paid ways count, and a card that
    only a free permission lets them cast isn't castable that way."""
    from app.rules import keyword_actions

    how = "hand" if card.zone == zone_key(player, "hand") else "command" if from_command_zone(card, player) else \
        "flashback" if from_graveyard(card, player, ch, state) else None
    if how is None and card.is_token and (perm := keyword_actions.prepared_permanent(state, card.id)) is not None \
            and perm.controller == player:
        how = "prepared"  # -- prepared (wave 13C) -- 722.3c: its controller may cast the copy in exile
    found = permissions.grants(state, player, card, ch, info, verb="cast") if info is not None else []
    flash = any(g.flash for g in found)
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
    if not ways:
        return None
    best = ways[0]
    return replace(best, flash=flash or best.flash)


def _escape_offers(state: GameState, player: str, card: CardInstance, ch: Characteristics, info: CardInfo) -> list[Any]:
    """-- escape (wave 5I) -- the escape costs this card can be cast for now (app/rules/escape.py)."""
    from app.rules import escape

    return escape.offers(state, player, card, ch, info)


def cast_problem(state: GameState, player: str, card: CardInstance, ch: Characteristics, *,
                 check_priority: bool = True, info: CardInfo | None = None, free: bool = False) -> str | None:
    """Why ``player`` can't cast ``card`` right now (costs aside), or None."""
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
    if "Instant" in ch.types or ch.has_flash or grant.flash:  # (601.3b: as though it had flash)
        return None
    if state.turn.active_player != player:
        return f"{ch.name} can only be cast during your turn"
    if state.turn.phase not in MAIN_PHASES:
        return f"{ch.name} can only be cast in a main phase"
    if state.zones.get(STACK):
        return f"{ch.name} can only be cast while the stack is empty"
    return None


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
               info: CardInfo | None = None, *, player: str | None = None, alternative: M.ManaCost | None = None,
               free: bool = False, kicker: int = 0, additional: tuple[M.ManaCost, ...] = (),
               face_down: bool = False, targets: tuple[str, ...] = ()) -> M.ManaCost:
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
        base = alternative
    else:
        in_graveyard = card.zone == zone_key(card.owner, "graveyard")
        flashback = (flashback_cost(ch) or _granted_flashback(state, card, ch)) if in_graveyard else None  # (wave 3R2)
        base = M.parse_cost(flashback or ch.mana_cost).with_x(x)
    extras = list(additional)
    if kicker:
        extras.append(kicker_extra(ch, kicker, face_down=face_down))
    tax = state.players[card.owner].commander_tax.get(card.commander_key, 0) \
        if from_command_zone(card, card.owner) and card.commander_key else 0
    affinity = affinity_discount(state, player, ch, info) if info is not None else 0
    return permissions.total_cost(state, player, card, ch, info, base=base, additional=tuple(extras), tax=tax, affinity=affinity,
                                  targets=targets)


def additional_problem(plan: Plan, extra: AbilityCost, card: CardInstance, player: str) -> str | None:
    """(wave 3$) Why a spell's additional cost can't be paid now (118.3: no partial payments; 119.4: life), or None."""
    if extra.either:  # -- static wordings (wave 6E) -- a choice: payable when one side is (app/rules/either_costs.py)
        from app.rules import either_costs

        return either_costs.problem(plan, extra, card, player)
    if extra.life and plan.state.players[player].life < extra.life:
        return f"You can't pay {extra.life} life"
    return cost_payment.problem(plan, extra, card, player)


def life_x_problem(plan: Plan, extra: AbilityCost, a: Any, player: str) -> str | None:
    """-- X sized by a count (wave 4K) -- "As an additional cost to cast this spell, pay X life.": X is announced as the
    spell is cast (601.2b, 107.3a) and can't be more than the caster's life (119.4; 119.4b: 0 always can be paid)."""
    if not extra.life_x:
        return None
    if a.x_value is None:
        return "Choose a value for X (the life to pay)"
    if a.x_value > 0 and plan.state.players[player].life < extra.life + a.x_value:
        return f"You can't pay {a.x_value} life"
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
        if grant is not None and grant.how == "escape":  # -- escape (wave 5I) -- only for an escape cost (702.138a)
            if alt_castable(state, player, card, info, check_priority=check_priority):
                return True
            continue
        cost = spell_cost(state, card, ch, info=info, player=player, free=grant is not None and grant.free,
                          targets=_hint_targets(ch))  # -- review (Codex) --
        if grant is not None and grant.spend:  # -- as long as (wave 9B) -- 118.14
            cost = M.spend_as(cost, grant.spend)
        if can_pay(state, player, cost, info, purpose=Purpose(spell=ch, card=card.id)):
            return True
    return False


def _hint_targets(ch: Characteristics) -> tuple[str, ...]:
    """-- review (Codex) -- the targets a castability hint assumes: none for a spell without targets, else the best
    case for "spells that target …" cost changes (cost_changes.ANY_TARGET)."""
    from app.rules import cost_changes

    return cost_changes.ANY_TARGET if "target" in ch.oracle_text.lower() else ()


# -- cost changers (wave 4I) --
def alt_castable(state: GameState, player: str, card: CardInstance, info: CardInfo, *,
                 check_priority: bool = True) -> list[dict[str, str]]:
    """The alternative costs (118.9) ``player`` could cast this card for right now, each with what the intent's
    ``alt_cost`` names: its condition holds, and the whole total cost (601.2f) can be paid (118.3)."""
    from app.rules import alt_costs  # (a leaf over this module)

    out: list[dict[str, str]] = []
    if chars.is_two_spell_card(card, info) or state.rules is None or state.rules.card_mode(card.id) == "manual":
        return out  # (a split card / adventure: which half isn't part of the hint)
    ch = chars.as_cast(card, info, None)
    if cast_problem(state, player, card, ch, check_priority=check_priority, info=info) is not None:
        return out
    grant = cast_grant(state, player, card, ch, info)
    in_graveyard = card.zone == zone_key(player, "graveyard")  # -- escape (wave 5I) -- from there: escape costs only
    if grant is not None and grant.how == "flashback" and not in_graveyard:
        return out  # (flashback is an alternative cost already: 118.9a)
    view = permissions._view(state, player, info)
    for offer in alt_costs.offers(state, player, card, ch, info):
        if in_graveyard and not offer.escape and grant is not None and grant.how in ("escape", "flashback"):
            continue  # (escape and flashback are the cast's own alternative costs: 118.9a)
        extra = alt_costs.merged(costs.spell_additional_cost(ch.abilities), offer.alt.cost)
        if extra is not None and additional_problem(view, extra, card, player):
            continue
        cost = spell_cost(state, card, ch, info=info, player=player, alternative=offer.alt.mana_cost,
                          targets=_hint_targets(ch))  # -- review (Codex) --
        if can_pay(state, player, cost, info, purpose=Purpose(spell=ch, card=card.id)):
            out.append({"id": offer.key, "label": offer.label})
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
        if state.players[player].life < offer.life:
            continue
        try:
            cost = cost_changes.reduce_only(spell_cost(state, card, ch, info=info, player=player,
                                                       free=grant is not None and grant.free), (offer.mana,))
        except ActionError:
            continue
        if can_pay(state, player, cost, info, purpose=Purpose(spell=ch, card=card.id)):
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
# -- end cast without paying (wave 3C) --


def cast_spell(plan: Plan, a: A.CastSpell) -> None:
    from app.rules.engine import advance  # the engine imports this module

    require_no_decision(plan)
    card = plan.state.cards.get(a.card_id)
    if card is None:
        raise ActionError("That card isn't here any more")
    ch = chars.as_cast(card, plan.info, a.face)  # split cards / adventures: the half being cast
    if a.alt_cost is not None and (a.free or a.evoke or a.dash or a.face_down):  # -- cost changers (wave 4I) --
        raise ActionError("Only one alternative cost can be applied to a spell (118.9a)")
    if a.free and card.id in plan.rules.free_casts:  # suspend / cascade / rebound / madness: what the engine granted
        cast_free(plan, card, ch, a)
        return
    face_down_kind = face_down_cast_kind(ch) if a.face_down else None  # -- keyword actions & face-down (wave 3F) --
    if a.face_down:  # morph / disguise: a nameless 2/2 creature spell (disguise: with ward {2}) for {3}
        if face_down_kind is None or card.zone != zone_key(plan.actor, "hand"):
            raise ActionError("Only a card with morph or disguise can be cast face down from your hand")
        ch = chars.face_down_characteristics(face_down_kind)
    problem = cast_problem(plan.state, plan.actor, card, ch, info=plan.info, free=a.free)
    if problem:
        raise ActionError(problem)
    grant = cast_grant(plan.state, plan.actor, card, ch, plan.info, free=a.free)
    free = grant is not None and grant.free  # "without paying its mana cost" (118.9): an alternative cost of {0}
    base = M.parse_cost(ch.mana_cost)
    if base.x and a.x_value is None:
        if not free and a.alt_cost is None:
            raise ActionError(f"Choose a value for X to cast {ch.name}")
        a.x_value = 0  # 107.3b: X is 0 when a spell is cast without paying its mana cost (or for an alternative cost, wave 4I)
    alternative: M.ManaCost | None = M.parse_cost("{3}") if a.face_down else None
    additional: list[M.ManaCost] = []
    if a.buyback:
        extra = keyword_cost(ch, "buyback", BUYBACK)
        if extra is None:
            raise ActionError(f"{ch.name} has no buyback cost")
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
    escaping = a.alt_cost is not None and card.zone == zone_key(plan.actor, "graveyard") and any(
        o.key == a.alt_cost for o in _escape_offers(plan.state, plan.actor, card, ch, plan.info))
    if grant is not None and grant.how == "escape" and not escaping:
        raise ActionError(f"{ch.name} can be cast from your graveyard only for its escape cost (702.138a)")
    if a.alt_cost is not None:
        if free or alternative is not None or a.face_down or (grant is not None and grant.how == "flashback" and not escaping):
            raise ActionError("Only one alternative cost can be applied to a spell (118.9a)")
        alt_offer = alt_costs.chosen(plan, a.alt_cost, card, ch)
        alternative = alt_offer.alt.mana_cost
        if base.x and a.x_value:
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
    definition = None if plan.manual(card) or a.face_down else scripts.spell_definition(ch)
    aura = None if plan.manual(card) or a.face_down else attachments.enchant_selector(ch)
    slots: list[list[TargetRef]] = []
    slot_specs: list[dict[str, Any] | None] = []
    picked: list[int] = []
    if definition is not None and definition.get("modes"):
        from app.rules.modal_abilities import printed_order

        a.modes, a.targets = printed_order(definition, a.modes, a.targets)  # (wave 1A) 608.2c: carried out as printed
        modes = choose_modes(plan, a, definition, ch.name or "it")  # 601.2b: modes first …
        if modes is None:
            return
        picked = modes
        slot_specs = [definition["modes"][i]["target"] for i in picked]
        found = choose_slot_targets(plan, a, slot_specs, ch.name or "it")  # … then each mode's target (601.2c)
        if found is None:
            return
        slots = found
        picked_targets: ChosenTargets | None = ChosenTargets(flat=[t for slot in slots for t in slot])
    else:
        picked_targets = choose_targets(plan, a, definition if aura is None else {"target": {"what": aura}}, ch.name or "it")
    if picked_targets is None:
        return  # waiting for the target choice (601.2c comes before paying costs)
    chosen = picked_targets.flat
    # 601.2f (after the targets, 601.2c): the total cost in the rules' order — kicker is an additional cost (118.8)
    # added before increases and reductions apply, so a reduction sees the kicked total; "spells that target …" cost
    # changers read the targets chosen (wave 4I)
    cost = spell_cost(plan.state, card, ch, a.x_value or 0, plan.info, player=plan.actor, alternative=alternative,
                      free=free, kicker=a.kicker, additional=tuple(additional), face_down=a.face_down, targets=tuple(t.id for t in chosen))
    optional = cost_changes.chosen_optional(plan.state, plan.actor, card, ch, plan.info, a.optional_costs) \
        if a.optional_costs and not plan.manual(card) else []  # -- cost changers (wave 4I) -- (601.2b)
    if a.optional_costs and plan.manual(card):
        raise ActionError("That card is played by hand: pay its costs with the table tools")
    cost = cost_changes.reduce_only(cost, tuple(o.mana for o in optional))  # ("reduces only the amount of green mana")
    cost = M.spend_as(cost, grant.spend) if grant is not None and grant.spend else cost  # -- as long as (wave 9B) -- 118.14
    cost = _locked(plan, cost)  # -- cost changers (wave 4I) -- 601.2f: locked in once the payment was asked for
    # -- costs (wave 3$) -- 601.2b: an additional cost ("sacrifice a creature", "discard a card", "pay 2 life") is
    # announced with the rest; 601.2h pays it all at once, so nothing moves until every part is chosen and payable
    add_cost = None if plan.manual(card) or a.face_down else costs.spell_additional_cost(ch.abilities)
    if either is not None:  # -- static wordings (wave 6E) -- the announced side's non-mana parts
        add_cost = either if either.components else None
    if alt_offer is not None:  # -- cost changers (wave 4I) -- its other parts are paid with the rest (601.2h)
        add_cost = alt_costs.merged(add_cost, alt_offer.alt.cost)
    if optional:  # -- cost changers (wave 4I) -- Defiler of Vigor's 2 life, paid with the rest (601.2h, 119.4)
        add_cost = alt_costs.merged(add_cost, costs.AbilityCost(components=tuple(
            costs.CostComponent(costs.PAY_LIFE, amount=o.life, text=f"Pay {o.life} life") for o in optional)))
    add_objects: dict[int, list[str]] = {}
    if add_cost is not None:
        problem = additional_problem(plan, add_cost, card, plan.actor) or life_x_problem(plan, add_cost, a, plan.actor)  # (4K)
        if problem:
            raise ActionError(problem)
        found_objects = cost_payment.choose(plan, a, add_cost, card, ch.name or "it")
        if found_objects is None:
            return  # waiting for the payer's choice; nothing has been paid
        add_objects = found_objects
    not_mana = cost_payment.excluded(add_cost, card, add_objects) if add_cost is not None else ()
    if payment_step(plan, a, cost, ch.name or "it", exclude=not_mana, purpose=Purpose(spell=ch)):
        return
    commander_cast = from_command_zone(card, plan.actor)
    flashback = from_graveyard(card, plan.actor, ch, plan.state) and not escaping  # (wave 5I: escape instead, 118.9a)
    card_was_in_hand = card.zone == zone_key(plan.actor, "hand")
    cast_zone = card.zone.rsplit(":", 1)[-1]  # -- refused modal/conditional (wave 3R1) -- where it was cast from
    from_where = {"graveyard": "the graveyard", "exile": "exile", "library": "the library", "hand": "the hand"}.get(
        card.zone.rsplit(":", 1)[-1], card.zone)
    if a.face is not None and a.face != card.face:
        plan.do({"type": "set_face", "card_id": card.id, "face": a.face})
    if a.face_down:
        plan.do({"type": "move", "card_ids": [card.id], "to": {"zone": "stack"}, "face_down": True, "face_down_kind": face_down_kind})
    else:
        plan.do({"type": "move", "card_ids": [card.id], "to": {"zone": "stack"}})
    if grant is not None and grant.how == "prepared":  # -- prepared (wave 13C) -- 722.3c, 601.2i: it loses the designation as the copy is cast
        plan.rules.prepared = {o: c for o, c in plan.rules.prepared.items() if c != card.id}
    if commander_cast and not plan.state.settings.auto_commander_tax and card.commander_key:
        plan.do({"type": "commander_tax", "commander": card.commander_key, "delta": 2})
    record = pay_spell(plan, a, card, ch, cost, f"paid {cost.text()} for {ch.name or 'a face-down spell'}", not_mana=not_mana)
    if add_cost is not None:
        if add_cost.life:
            plan.do({"type": "life", "player": plan.actor, "delta": -add_cost.life})  # 119.4: paying life is losing it
            record.life += add_cost.life
        if add_cost.life_x and a.x_value:  # -- X sized by a count (wave 4K) -- "pay X life" (119.4)
            plan.do({"type": "life", "player": plan.actor, "delta": -a.x_value})
            record.life += a.x_value
        cost_payment.pay(plan, add_cost, card, add_objects, record)  # sacrifice, discard, exile, return, tap …
    record.alternative = "face_down" if a.face_down else "evoke" if a.evoke else "dash" if a.dash else \
        "flashback" if flashback else "free" if free else "escape" if escaping else \
        "alternative" if alt_offer is not None else None  # ("escape": 702.138b, wave 5I)
    if alt_offer is not None:  # -- cost changers (wave 4I) --
        if alt_offer.once_key:
            plan.rules.once_per_turn[alt_offer.once_key] = plan.state.turn.number  # ("once each turn")
        plan.note(f"{plan.name(plan.actor)} cast {ch.name} for an alternative cost ({alt_offer.label})", [card.id])
    record.additional = (["buyback"] if a.buyback else []) + (["kicker"] if a.kicker else []) \
        + [f"optional:{o.source}" for o in optional]  # (wave 4I: Defiler of Vigor's life)
    record.kicked = a.kicker  # 702.33d
    _note_cast(plan, record, cast_zone)  # -- refused modal/conditional (wave 3R1) --
    record_payment(plan, card.id, record)
    tags = ["Cast from the command zone"] if commander_cast else ["Flashback"] if flashback else ["Dashed"] if a.dash else \
        ["Escaped"] if escaping else []  # (wave 5I)
    if grant is not None and grant.how == "permission":
        permissions.consume(plan, grant)  # (a "once during each of your turns" permission is used up)
        tags.append(f"Cast from {from_where}" + (" without paying its mana cost" if free else ""))
    if a.dash:
        plan.rules.dashed.append(card.id)
    if a.kicker:
        tags.append("Kicked" if a.kicker == 1 else f"Kicked ×{a.kicker}")
    if a.buyback:
        tags.append("Buyback")
        plan.rules.buyback.append(plan.oid(card))
    if a.evoke:
        tags.append("Evoked")
        plan.rules.evoked.append(card.id)
    if "rebound" in ch.keywords and card_was_in_hand:
        plan.rules.rebound_cast.append(plan.oid(card))
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
    # for "whenever you cast"; amount: the Nth spell its caster cast this turn ("your second spell each turn")
    emit(plan.state, "spell_cast", object_id=plan.oid(card), card=card.id, player=plan.actor,
         amount=r.spells_this_turn(plan.actor, plan.state.turn.number) + 1)
    more_cascade = 0 if a.face_down or plan.manual(card) else _granted_cascade(plan, card, ch, record.cast_from)
    if more_cascade or ("cascade" in ch.keywords and not a.face_down and not plan.manual(card)):
        _cascade_triggers(plan, card, ch, more_cascade)
    if "storm" in ch.keywords and not a.face_down and not plan.manual(card):
        _storm_trigger(plan, card, ch)
    if definition is not None and picked:  # a modal spell: each chosen mode's effects, with its own target slot
        effects_in_order = [e for k, i in enumerate(picked)
                            for e in [{"do": "use_targets", "slot": k}, *definition["modes"][i]["effects"]]]
        r.stack[card.id] = StackEntry(kind="spell", controller=plan.actor, source_card=card.id, source_object=plan.oid(card),
                                      name=ch.name, effects=effects_in_order, targets=chosen, target_spec=None,
                                      x=a.x_value, modes=picked, slots=slots, slot_specs=slot_specs, kicked=a.kicker)
    elif definition is not None:
        r.stack[card.id] = StackEntry(kind="spell", controller=plan.actor, source_card=card.id, source_object=plan.oid(card),
                                      name=ch.name, effects=list(definition["effects"]), x=a.x_value,
                                      **picked_targets.entry(definition), kicked=a.kicker)
    if aura is not None and chosen:
        r.aura_targets = {k: v for k, v in r.aura_targets.items() if plan.state.cards.get(k) is not None
                          and plan.state.cards[k].zone == STACK}
        r.aura_targets[card.id] = chosen[0]  # 303.4a: the Aura spell's target
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
    found = hand_ability(ch, a.ability)
    if found is None:
        raise ActionError("That card has no ability to use from your hand")
    kind, mana_text = found
    # 702.29a: cycling is an activated ability — "Abilities you activate that aren't mana abilities cost {1} less"
    # applies to it (602.2b -> 601.2f; app/rules/permissions.py ability_mana)
    mana = M.parse_cost(permissions.ability_mana(plan.state, plan.actor, card, ch, mana_text, plan.info))
    mana = _locked(plan, mana)  # -- review (wave 4R) -- 602.2b → 601.2f: locked in, as for other activations
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
        from app.rules.triggers import activated  # -- activation (wave 11F) --

        activated(plan, card, oid)
    r.passed = []
    r.priority = plan.actor
    if r.prefs_for(plan.actor).hold_priority:
        plan.hold = plan.actor
        return
    r.passed.append(plan.actor)
    r.priority = plan.after(plan.actor)
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
    if payment_step(plan, a, cost, f"suspending {ch.name}", purpose=Purpose(spell=ch)):
        return
    pay(plan, plan.actor, cost, f"paid {cost.text()} to suspend {ch.name}", sources=a.sources, purpose=Purpose(spell=ch))
    plan.do({"type": "move", "card_ids": [card.id], "to": {"player": card.owner, "zone": "exile"}})
    if n:
        plan.do({"type": "counter", "card_ids": [card.id], "kind": "time", "delta": n})
    plan.rules.suspended.append(card.id)
    plan.note(f"{ch.name} is suspended with {n} time counter{'s' if n != 1 else ''}", [card.id])
    plan.rules.passed = []


UNEARTH = re.compile(r"^unearth (?P<cost>(?:\{[^}]+\})+)$", re.IGNORECASE)
MADNESS = re.compile(r"^madness (?P<cost>(?:\{[^}]+\})+)$", re.IGNORECASE)
BUYBACK = re.compile(r"^buyback (?P<cost>(?:\{[^}]+\})+)$", re.IGNORECASE)
EVOKE = re.compile(r"^evoke (?P<cost>(?:\{[^}]+\})+)$", re.IGNORECASE)
DASH = re.compile(r"^dash (?P<cost>(?:\{[^}]+\})+)$", re.IGNORECASE)


def kicker_extra(ch: Characteristics, times: int, *, face_down: bool = False) -> M.ManaCost:
    """702.33a / 702.33c: the kicker cost paid ``times`` times — an additional cost (118.8) that
    joins the total cost (601.2f) before increases and reductions; the spell's mana cost and mana
    value don't change (118.8d)."""
    kick = None if face_down else kicker_cost(ch.abilities)  # (a face-down spell has no abilities, 708.2)
    if kick is None:
        raise ActionError(f"{ch.name or 'That spell'} has no kicker cost Fyodor can pay: kick it by hand with the table tools")
    if times > 1 and not kick.multi:
        raise ActionError(f"{ch.name} can be kicked only once")  # (multikicker: any number of times, 702.33c)
    extra = M.parse_cost(kick.cost)
    return M.ManaCost(extra.generic * times, extra.colored * times, extra.hybrid * times, extra.phyrexian * times, 0,
                      extra.unsupported * times)


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


def _storm_trigger(plan: Plan, card: CardInstance, ch: Characteristics) -> None:
    """702.40a: "When you cast this spell, copy it for each other spell that was cast before it
    this turn. You may choose new targets for the copies." """
    from app.rules.triggers import _add

    r = plan.rules
    turn = plan.state.turn.number
    before = sum(r.spells_this_turn(p, turn) for p in plan.state.seat_order)
    if before:
        _add(plan, controller=plan.actor, source_card=card.id, source_object=plan.oid(card), name=ch.name, index=6100,
             definition={"kind": "triggered", "trigger": "storm", "optional": False, "target": None,
                         "effects": [{"do": "storm", "spell": card.id, "object": plan.oid(card), "n": before}]})


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
    if "Legendary" in ch.supertypes and ch.is_instant_or_sorcery and not _controls_legendary(plan.state, plan.actor, plan.info):
        raise ActionError(f"{ch.name} needs you to control a legendary creature or planeswalker")  # 205.4e
    # -- cast limits (wave 5E) -- 601.3 applies to a cast as something resolves too
    from app.rules import cast_limits

    limited = cast_limits.cast_problem(plan.state, plan.actor, card, ch, plan.info, resolving=True)
    if limited:
        raise ActionError(limited)
    # -- static wordings (wave 6E) -- 118.9d: a choice of additional costs is still announced (601.2b) and paid
    from app.rules import either_costs

    either = None if plan.manual(card) else either_costs.announce(plan, a, card, ch)
    if either is either_costs.WAITING:
        return
    definition = None if plan.manual(card) else scripts.spell_definition(ch)
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
    alt = r.alt_costs.get(card.id)
    # 118.9d / 601.2b: a spell's own additional cost ("As an additional cost to cast this spell,
    # sacrifice a creature": Fling cast by cascade) is still paid — chosen now, paid with the rest
    add_cost = None if plan.manual(card) else costs.spell_additional_cost(ch.abilities)
    if either is not None:  # -- static wordings (wave 6E) --
        add_cost = either if either.components else None
    add_objects: dict[int, list[str]] = {}
    if add_cost is not None:
        problem = additional_problem(plan, add_cost, card, plan.actor) or life_x_problem(plan, add_cost, a, plan.actor)  # (4K)
        if problem:
            raise ActionError(problem)
        found_objects = cost_payment.choose(plan, a, add_cost, card, ch.name or "it")
        if found_objects is None:
            return  # waiting for the payer's choice; nothing has been paid (the grant stays)
        add_objects = found_objects
    not_mana = cost_payment.excluded(add_cost, card, add_objects) if add_cost is not None else ()
    # 118.9d / 601.2f: additional costs (kicker), increases and reductions still apply to the
    # alternative cost — {0}, or the madness cost
    cost = spell_cost(plan.state, card, ch, 0, plan.info, player=plan.actor, free=alt is None,
                      alternative=M.parse_cost(alt) if alt is not None else None, kicker=a.kicker,
                      targets=tuple(t.id for t in chosen),  # (wave 4I: "spells that target …")
                      additional=(M.parse_cost(either.mana),) if either is not None and either.mana else ())  # (wave 6E)
    cost = _locked(plan, cost)  # (wave 4I: 601.2f)
    if alt is not None or not cost.is_free:
        if payment_step(plan, a, cost, ch.name or "it", exclude=not_mana, purpose=Purpose(spell=ch)):
            return
        record = pay_spell(plan, a, card, ch, cost, f"paid {cost.text()} for {ch.name}" + (" (madness)" if alt else ""),
                           not_mana=not_mana)
        record.alternative = "madness" if alt is not None else "free"
        record.additional = ["kicker"] if a.kicker else []
        record.kicked = a.kicker
        r.alt_costs.pop(card.id, None)
    else:
        record = PaymentRecord(card=card.id, controller=plan.actor, alternative="free")
    was_suspended = card.id in r.suspended
    from_hand = card.zone == zone_key(plan.actor, "hand")
    _note_cast(plan, record, card.zone.rsplit(":", 1)[-1])  # -- refused modal/conditional (wave 3R1) --
    r.free_casts = [c for c in r.free_casts if c != card.id]
    r.suspended = [c for c in r.suspended if c != card.id]
    if card.counters.get("time"):
        plan.do({"type": "counter", "card_ids": [card.id], "kind": "time", "delta": -card.counters["time"]})
    if a.x_value is None and M.parse_cost(ch.mana_cost).x:
        a.x_value = 0  # X is 0 when a spell is cast without paying its mana cost (107.3b)
    plan.do({"type": "move", "card_ids": [card.id], "to": {"zone": "stack"}})
    if add_cost is not None:  # (601.2h: with the rest of the total cost)
        if add_cost.life:
            plan.do({"type": "life", "player": plan.actor, "delta": -add_cost.life})  # 119.4
            record.life += add_cost.life
        if add_cost.life_x and a.x_value:  # -- X sized by a count (wave 4K) -- "pay X life" (119.4)
            plan.do({"type": "life", "player": plan.actor, "delta": -a.x_value})
            record.life += a.x_value
        cost_payment.pay(plan, add_cost, card, add_objects, record)  # sacrifice, discard, exile …
    plan.do({"type": "set_stack_info", "card_id": card.id,
             "tags": ["Cast for its madness cost" if alt is not None else "Cast without paying its mana cost"]
             + (["Kicked" if a.kicker == 1 else f"Kicked ×{a.kicker}"] if a.kicker else [])})
    record.x = a.x_value
    record_payment(plan, card.id, record)
    if a.targets:
        plan.do({"type": "create_arrow", "source": card.id, "targets": list(a.targets), "kind": "target"})
    if ch.is_creature and was_suspended:
        r.suspend_haste.append(card.id)  # 702.62e: it gains haste
    if "rebound" in ch.keywords and from_hand:
        r.rebound_cast.append(plan.oid(card))
    emit(plan.state, "spell_cast", object_id=plan.oid(card), card=card.id, player=plan.actor,
         amount=r.spells_this_turn(plan.actor, plan.state.turn.number) + 1)  # (the Nth spell this turn)
    extra = 0 if plan.manual(card) else _granted_cascade(plan, card, ch, record.cast_from)
    if extra or ("cascade" in ch.keywords and not plan.manual(card)):
        _cascade_triggers(plan, card, ch, extra)
    if "storm" in ch.keywords and not plan.manual(card):
        _storm_trigger(plan, card, ch)
    if definition is not None and picked:
        effects_in_order = [e for k, i in enumerate(picked)
                            for e in [{"do": "use_targets", "slot": k}, *definition["modes"][i]["effects"]]]
        r.stack[card.id] = StackEntry(kind="spell", controller=plan.actor, source_card=card.id, source_object=plan.oid(card),
                                      name=ch.name, effects=effects_in_order, targets=chosen, target_spec=None,
                                      x=a.x_value, modes=picked, slots=slots, slot_specs=slot_specs, kicked=a.kicker)
    elif definition is not None:
        r.stack[card.id] = StackEntry(kind="spell", controller=plan.actor, source_card=card.id, source_object=plan.oid(card),
                                      name=ch.name, effects=list(definition["effects"]), x=a.x_value,
                                      **picked_targets.entry(definition), kicked=a.kicker)
    if aura is not None and chosen:
        r.aura_targets = {k: v for k, v in r.aura_targets.items() if plan.state.cards.get(k) is not None
                          and plan.state.cards[k].zone == STACK}
        r.aura_targets[card.id] = chosen[0]  # 303.4a: the Aura spell's target
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
        elif (ninja := ninjutsu.cost_of(ch, a.ability)) is not None and not plan.manual(card):
            on_stack = len(plan.state.zones.get(STACK, []))
            activate_to_stack(plan, card, ch, ninjutsu.ability(ch, a.ability, ninja), a, definition=ninjutsu.DEFINITION)
            if len(plan.state.zones.get(STACK, [])) > on_stack and card.zone == zone_key(plan.actor, "hand"):  # -- keywords
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
    ch = plan.ch(card)
    # -- activation wordings (wave 7B) -- 602.2: "Any player may activate this ability."
    ab = next((x for x in ch.abilities if x.index == a.ability), None)
    if not card.zone.endswith(":battlefield") or (card.controller != plan.actor and not (
            ab is not None and any_player(ab, ability_cost(ch, ab, state=plan.state, card=card, info=plan.info)))):
        raise ActionError("You can only activate abilities of permanents you control")
    if "cant_activate" in ch.imposed:  # an Aura: "its activated abilities can't be activated" (crew, equip too)
        raise ActionError(f"{ch.name}’s activated abilities can't be activated")
    ability = _find_ability(ch, a.ability)
    _activation_limit(plan, card, ch, mana=ability.kind == "mana", loyalty=ability.kind == "loyalty")  # -- cast limits (wave 5E) --
    n = crew_power(ch, a.ability) if not plan.manual(card) else None
    if n is not None:
        crew(plan, card, ch, a, n)
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
    if parsed.spend_only is not None:
        raise ActionError(f"{ch.name}’s mana can only pay for certain things: Fyodor taps it when you cast or activate them")
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
    if parsed is None or parsed.spend_only is not None:
        raise ActionError("While paying you can only tap for mana")
    if ability_taxes(plan.state, plan.info) and mana_ability_taxed(plan.state, card, ch, parsed, plan.info):  # (review 4R)
        raise ActionError(f"Another effect changes the cost of {ch.name}’s mana ability: activate it by hand with the table tools")
    if parsed.tap and not can_use_tap_abilities(plan.state, card, ch, plan.info):
        raise ActionError(f"{ch.name} is tapped" if card.tapped else f"{ch.name} has summoning sickness")
    options = parsed.options
    chosen = next((o for o in options if o == (a.mana_choice,)), None) if a.mana_choice else None
    produce(plan, card, parsed, chosen or (options[0] if len(options) == 1 else _best_option(plan, options)), a.ability)
    after_tapping(plan)


# -- other activated abilities (they use the stack) -----------------------------------------
def ability_cost(ch: Characteristics, ability: AbilityText, *, state: GameState | None = None,
                 card: CardInstance | None = None, info: CardInfo | None = None) -> AbilityCost:
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
        reduced = permissions.ability_mana(state, card.controller, card, ch, cost.mana, info, own, ability.text)
        if reduced != cost.mana:
            cost = replace(cost, mana=reduced)
    # -- reanimation (wave 3R) -- 113.6m: "{1}{B}: Return this card from your graveyard to the battlefield" moves the
    # card out of the graveyard, so the ability works only there
    if ability.kind == "activated" and ":" in ability.text and _GRAVEYARD_SELF.match(ability.text.split(":", 1)[1].strip().replace(ch.name, "~")):
        cost = replace(cost, graveyard_only=True)
    return cost


_GRAVEYARD_SELF = re.compile(r"(?:return|put) (?:this card|this creature|this artifact|this land|~) from your graveyard\b", re.I)


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
    elif cost.from_graveyard:  # 113.6m: its cost moves it out of your graveyard, so it works only there
        if card.zone != zone_key(player, "graveyard") or card.owner != player:
            return "That ability can only be activated from your graveyard"
    elif ninjutsu.is_ninjutsu(ability.text):  # -- keywords (wave 15E) -- 702.49a: from the hand, once blockers are declared
        why = ninjutsu.problem(state, player, card)
        if why:
            return why
    elif not card.zone.endswith(":battlefield") or (card.controller != player and not any_player(ability, cost)):  # (wave 7B)
        return "You can only activate abilities of permanents you control"
    if cost.unsupported:
        return f"Pay “{', '.join(cost.unsupported)}” by hand with the table tools"
    if "cant_activate" in ch.imposed:
        return f"{ch.name}’s activated abilities can't be activated"
    # -- cast limits (wave 5E) -- (602.5)
    from app.rules import cast_limits

    limited = cast_limits.activation_problem(state, player, card, ch, info, loyalty=ability.kind == "loyalty")
    if limited:
        return limited
    if check_priority and (r.priority != player or r.decision is not None):
        return "You don't have priority"
    if ability.kind == "loyalty":  # 606.3: as a sorcery, once per permanent each turn
        if state.turn.active_player != player or state.turn.phase not in MAIN_PHASES or state.zones.get(STACK):
            return "That can only be activated in your main phase while the stack is empty"
        if r.loyalty_used.get(r.object_id(card.id)) == state.turn.number:
            return f"{ch.name} has already used a loyalty ability this turn"
        if cost.loyalty is not None and cost.loyalty < 0 and card.counters.get("loyalty", 0) < -cost.loyalty:
            return f"{ch.name} doesn't have enough loyalty"
    # -- activation restrictions (602.5; app/rules/restrictions.py): "Activate only as a sorcery",
    # "… only once each turn" (per object, 602.5b / 400.7), "… only during your turn", "… only if …"
    limits = restrictions.parse(_own_text(ability.text, ch.name)) or []  # (a wording it doesn't read: the ability is manual anyway)
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
    if info is not None and cost.components:  # 118.3: untap, sacrifice, discard, exile … (cost_payment)
        found = cost_payment.problem(Plan.view(state, player, info), cost, card, player)
        if found:
            return found
    if info is not None and cost.mana:
        mana = M.parse_cost(cost.mana).with_x(x)
        if not can_pay(state, player, mana, info, exclude=(card.id,) if cost.tap else (), purpose=Purpose(ability_of=ch)):
            return f"Not enough mana to pay {mana.text()}"
    return None


def equip_ability(plan: Plan, card: CardInstance, ch: Characteristics, a: A.ActivateAbility,
                  equip: tuple[str, str, str]) -> None:
    """702.6a Equip [cost]: "[Cost]: Attach this permanent to target creature you control. Activate only as a sorcery."
    (702.6b: the target narrowed by a quality; -- equip (wave 15E) -- non-mana costs and the line's own trailing sentences).
    An Equipment that's also a creature can't equip (301.5c)."""
    cost, target, tail = equip
    if "Equipment" not in ch.subtypes or ch.is_creature:
        raise ActionError(f"{ch.name} can't equip a creature" + (" while it's a creature" if ch.is_creature else ""))
    ability = AbilityText(index=a.ability, kind="activated", cost=cost,
                          text=f"{cost}: Attach {ch.name} to target creature you control. Activate only as a sorcery."
                               + (f" {tail}" if tail else ""))
    definition = {"kind": "activated", "effects": [{"do": "attach_self"}], "target": {"what": target}}
    activate_to_stack(plan, card, ch, ability, a, definition=definition, exclude_targets=(card.id,))


def activate_to_stack(plan: Plan, card: CardInstance, ch: Characteristics, ability: AbilityText,
                      a: A.ActivateAbility, *, definition: dict[str, Any] | None = None,
                      exclude_targets: tuple[str, ...] = ()) -> None:
    from app.rules import modal_abilities  # (a leaf module over this one)
    from app.rules.engine import advance  # the engine imports this module

    cost = ability_cost(ch, ability, state=plan.state, card=card, info=plan.info)
    problem = ability_problem(plan.state, plan.actor, card, ch, ability, cost, plan=plan)
    if problem:
        raise ActionError(problem)
    oid = plan.oid(card)  # the object activating (paying a cost may move it: it'd be a new object)
    mana = M.parse_cost(cost.mana)
    if plan.locked_cost is not None and not mana.x:  # -- cost changers (wave 4I) -- 602.2b → 601.2f: locked in
        mana = _locked(plan, mana)
    if (mana.x or cost.loyalty_x or cost.energy_x or cost.x_chosen) and a.x_value is None:  # (wave 3E: "Pay X {E}"; x_chosen: wave 4H)
        raise ActionError("Choose a value for X")
    if cost.loyalty_x and card.counters.get("loyalty", 0) < (a.x_value or 0):
        raise ActionError(f"{ch.name} doesn't have {a.x_value} loyalty")  # 606.6
    if definition is None:
        definition = None if plan.manual(card) else scripts.definitions(ch).get(ability.index)
    if definition is not None and definition["kind"] != "activated":
        definition = None
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
    problem = cost_payment.problem(plan, cost, card, plan.actor, a.x_value)  # 118.3 / 601.2h: nothing is paid unless all can be
    if problem:
        raise ActionError(problem)
    cost_objects = cost_payment.choose(plan, a, cost, card, f"{ch.name}’s ability")  # (602.2b → 601.2h)
    if cost_objects is None:
        return  # waiting for the payer's choice; nothing has been paid
    not_mana = cost_payment.excluded(cost, card, cost_objects)  # (they can't also tap for mana)
    if payment_step(plan, a, mana.with_x(a.x_value or 0), f"{ch.name}’s ability",
                    exclude=not_mana, purpose=Purpose(ability_of=ch)):
        return
    effect = ability.text.split(":", 1)[1].strip() if ":" in ability.text else ability.text
    created = plan.do({"type": "create_ability", "text": effect[:500], "source_id": card.id, "kind": "activated"})
    new_ids = getattr(created, "r", None)
    ability_id = new_ids.ids[0] if new_ids is not None else None
    # Pay the costs (602.2): tap first so the source can't also pay for its own mana cost.
    if cost.tap:
        plan.do({"type": "tap", "card_ids": [card.id], "tapped": True})
    if cost.loyalty or (cost.loyalty_x and a.x_value):
        delta = cost.loyalty if not cost.loyalty_x else -(a.x_value or 0)
        plan.do({"type": "counter", "card_ids": [card.id], "kind": "loyalty", "delta": delta})
    for kind, n in cost.remove_counters:
        plan.do({"type": "counter", "card_ids": [card.id], "kind": kind, "delta": -n})
    if cost.life:
        plan.do({"type": "life", "player": plan.actor, "delta": -cost.life})
    paid = pay(plan, plan.actor, mana.with_x(a.x_value or 0), f"paid {mana.with_x(a.x_value or 0).text()} to activate {ch.name}",
               sources=a.sources, exclude=not_mana, purpose=Purpose(ability_of=ch))
    record = PaymentRecord(card=ability_id or card.id, controller=plan.actor, total_cost=ability.cost or "",
                           mana_spent=dict(paid.spent) if paid else {}, life=cost.life + (paid.life if paid else 0),
                           tapped=list(paid.tapped) if paid else [], x=a.x_value)
    cost_payment.pay(plan, cost, card, cost_objects, record)  # sacrifice, discard, exile, return, tap others …
    if ability_id and (record.sacrificed or record.discarded or record.exiled or record.returned or record.tapped_for_cost):
        record_payment(plan, ability_id, record)  # ("the sacrificed creature" …: what paid for it)
    if a.x_value is not None and ability_id:
        plan.do({"type": "set_stack_info", "card_id": ability_id, "x": a.x_value})
    if a.targets and ability_id:
        plan.do({"type": "create_arrow", "source": ability_id, "targets": list(a.targets), "kind": "target"})
    r = plan.rules
    if modal is not None and ability_id:  # (wave 1A) each chosen mode's effects, with its own target slot
        r.stack[ability_id] = StackEntry(kind="activated", controller=plan.actor, source_card=card.id, source_object=oid,
                                         name=ch.name, x=a.x_value, **modal.entry)
        modal_abilities.announced(plan, ability_id, card, modal, oid)  # the modes chosen are public; remembered
    elif definition is not None and ability_id:
        r.stack[ability_id] = StackEntry(kind="activated", controller=plan.actor, source_card=card.id, source_object=oid,
                                         name=ch.name, x=a.x_value, **picked_targets.entry(definition),
                                         # -- this-turn history (wave 4D) -- "the second time this ability has resolved"
                                         effects=history.counting_resolutions(list(definition["effects"]), f"{oid}:{a.ability}"))
    if chosen and ability_id:
        from app.rules.triggers import targeted

        targeted(plan, ability_id, plan.actor, chosen)
    if ability_id:  # -- activation (wave 11F) -- 602.2: "Whenever a player activates an ability …"
        from app.rules.triggers import activated

        activated(plan, card, oid, loyalty=ability.kind == "loyalty")
    if ability.kind == "loyalty":
        r.loyalty_used[oid] = plan.state.turn.number
    if restrictions.limited(restrictions.parse(_own_text(ability.text, ch.name)) or []):  # "Activate only once each turn" / "… only once"
        restrictions.record_use(r, oid, ability.index, plan.state.turn.number)
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
        from app.rules.layers import derive

        ch = derive(state, card, chars.of(card, info), info)
        for ab in ch.abilities:
            if ab.kind in ("activated", "loyalty"):
                problem = ability_problem(state, player, card, ch, ab, ability_cost(ch, ab, state=state, card=card, info=info),
                                          check_priority=check_priority, info=info)
                if problem is None:
                    out.append({"card_id": cid, "ability": ab.index})
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
    for cid in state.zones.get(zone_key(player, "hand"), []):  # -- keywords (wave 15E) -- ninjutsu (702.49a)
        card = state.cards[cid]
        ch = chars.of(card, info)
        for ab in ch.abilities:
            if (cost_text := ninjutsu.cost_of(ch, ab.index)) is not None:
                made = ninjutsu.ability(ch, ab.index, cost_text)
                if ability_problem(state, player, card, ch, made, ability_cost(ch, made, state=state, card=card, info=info),
                                   check_priority=check_priority, info=info) is None:
                    out.append({"card_id": cid, "ability": ab.index})
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
    return out


def _can_crew(state: GameState, player: str, card: CardInstance, ch: Characteristics, index: int, info: CardInfo,
              check_priority: bool) -> bool:
    n = crew_power(ch, index)
    r = state.rules
    if n is None or r is None or (check_priority and (r.priority != player or r.decision is not None)):
        return False
    # -- cast limits (wave 5E) -- crew is an activated ability (702.122a)
    from app.rules import cast_limits

    if cast_limits.activation_problem(state, player, card, ch, info) is not None:
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
    oid = plan.oid(card)  # (wave 5A: the object as it was tapped)
    plan.do({"type": "rules_mana", "player": card.controller, "tap": [card.id] if ability.tap else [],
             "sacrifice": [card.id] if ability.sacrifice_self else [], "delta": mana,
             "life": extra.life if extra else 0, "label": f"added {M.symbols(mana)}"}, actor=card.controller)
    emit(plan.state, "mana_added", object_id=oid, card=card.id, player=card.controller, amount=sum(mana.values()),
         counter="tap" if ability.tap else None)  # -- mana riders (wave 5A) -- tapped for mana (106.12a)
    if index is not None:
        after_mana_ability(plan, card, index, ability)


# -- refused copy/mana (wave 3R3) -- a mana ability whose cost chooses objects (Ashnod's Altar: "Sacrifice a
# creature: Add {C}{C}."). 605.3a / 602.2b → 601.2h: the player chooses the objects as the cost is paid (a private
# decision, app/rules/cost_payment.py; none chosen cancels), the costs are paid all at once, then the ability
# resolves at once (605.3a: no stack) — a color to choose is chosen then, after the costs (resume "paid").
def _activate_choosing(plan: Plan, card: CardInstance, ch: Characteristics, parsed: M.ManaAbility,
                       a: A.ActivateAbility) -> None:
    cost = parse_ability_cost(parsed.extra_cost, card_name=ch.name)
    problem = cost_payment.problem(plan, cost, card, plan.actor)
    if problem is not None:
        raise ActionError(problem)
    objects = cost_payment.choose(plan, a, cost, card, ch.name or "It")
    if objects is None:
        return  # (the payer's choice is pending; its resume runs this intent again with it)
    options = parsed.options
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
    cost_payment.pay(plan, cost, card, objects, record)
    if parsed.tap or parsed.sacrifice_self or cost.life:
        plan.do({"type": "rules_mana", "player": card.controller, "tap": [card.id] if parsed.tap else [],
                 "sacrifice": [card.id] if parsed.sacrifice_self else [], "delta": {}, "life": cost.life,
                 "label": f"paid to activate {ch.name}"}, actor=card.controller)
    if option is None:
        decide(plan, player=plan.actor, kind="choose_one", prompt=f"Which mana should {ch.name} add?",
               options=[DecisionOption(id=str(i), label=M.symbols(_count(o))) for i, o in enumerate(options)],
               resume={"step": "mana_ability", "card": card.id, "ability": a.ability, "paid": True,
                       "options": [list(o) for o in options], "oid": plan.oid(card)}, source=card)
        return
    _add_paid_mana(plan, card, parsed, option, a.ability, plan.oid(card))
    plan.rules.passed = []


def _add_paid_mana(plan: Plan, card: CardInstance, ability: M.ManaAbility, option: tuple[str, ...], index: int,
                   oid: str | None) -> None:
    """The mana of an ability whose costs are paid (605.3a), then its riders (as ``produce``)."""
    mana = _count(option)
    plan.do({"type": "rules_mana", "player": card.controller, "tap": [], "sacrifice": [], "delta": mana, "life": 0,
             "label": f"added {M.symbols(mana)}"}, actor=plan.actor)
    emit(plan.state, "mana_added", object_id=oid, card=card.id, player=card.controller, amount=sum(mana.values()),
         counter="tap" if ability.tap else None)  # -- mana riders (wave 5A) -- tapped for mana (106.12a)
    after_mana_ability(plan, card, index, ability)


def _resume_paid_mana(plan: Plan, d: Any, chosen: list[str]) -> None:
    card = plan.state.cards.get(d.resume["card"])
    options = [tuple(o) for o in d.resume["options"]]
    k = int(chosen[0]) if chosen and chosen[0].isdigit() else -1
    if card is None or not 0 <= k < len(options):
        raise ActionError("Choose one of the offered mana")
    found = dict(mana_abilities(plan.state, card, plan.info)).get(int(d.resume["ability"]))
    parsed = found if found is not None else M.ManaAbility(tap=False, sacrifice_self=False, options=tuple(options))
    _add_paid_mana(plan, card, parsed, options[k], int(d.resume["ability"]), d.resume.get("oid"))
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
    for key in (zone_key(player, "hand"), zone_key(player, "command"), zone_key(player, "graveyard"), zone_key(player, "exile")):
        for cid in state.zones.get(key, []):
            card = state.cards[cid]
            ch = chars.of(card, info)
            if ("Instant" in ch.types or ch.has_flash or _flash_granted(state, player, card, ch, info)) \
                    and castable(state, player, card, info, check_priority=False):
                return True
            # -- cost changers (wave 4I) -- an instant castable only for an alternative cost (Force of Will with no mana
            # open) is a response too: never auto-passed over
            if ("Instant" in ch.types or ch.has_flash) and alt_castable(state, player, card, info, check_priority=False):
                return True
    return bool(activatable(state, player, info, check_priority=False))


def _flash_granted(state: GameState, player: str, card: CardInstance, ch: Characteristics, info: CardInfo) -> bool:
    """"You may cast creature spells as though they had flash" (601.3b) applies to this card."""
    if ch.is_land or not ch.types:
        return False
    grant = cast_grant(state, player, card, ch, info)
    return grant is not None and grant.flash


def can_act(state: GameState, player: str, info: CardInfo) -> bool:
    """Could ``player`` do anything at all right now (a land, a spell, an ability)?"""
    from app.rules.engine import land_play_problem  # engine imports this module

    for key in (zone_key(player, "hand"), zone_key(player, "command"), zone_key(player, "graveyard")):
        for cid in state.zones.get(key, []):
            card = state.cards[cid]
            if castable(state, player, card, info, check_priority=False):
                return True
            if key.endswith(":hand") and land_play_problem(state, player, card, chars.of(card, info), check_priority=False,
                                                                 info=info) is None:  # (info: wave 4J, additional land plays)
                return True
    return bool(activatable(state, player, info, check_priority=False))

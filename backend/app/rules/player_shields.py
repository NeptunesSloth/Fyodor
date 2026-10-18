"""-- player shields (wave 5E) -- hexproof, shroud and protection on a player. Researched against the Comprehensive
Rules of 2026-09-25.

* 702.11c: hexproof on a player — "You can't be the target of spells or abilities your opponents control."
* 702.18a: shroud — nobody's spells or abilities can target that player.
* 702.16b/c/e: a player with protection from a quality can't be targeted by spells with that quality or by
  abilities from sources with it, can't be enchanted by Auras with it (an Aura already attached is put into its
  owner's graveyard, 704.5m), and damage sources with it would deal to the player is prevented. 702.16j:
  "protection from everything" — protection from each object: no spell or ability can target the player, no Aura
  can enchant them, all damage that would be dealt to them is prevented. Protection doesn't stop being attacked.
  615.12: damage that can't be prevented still is dealt (source_shields.protection_applies).
* A static ability's shield applies while its source is on the battlefield (611.3a); a resolved effect's for its
  stated duration (611.2a: "until end of turn" ends at cleanup, 514.2; "until your next turn" as that player's
  next turn begins, 500.4 / 800.4m).
* "of your choice": chosen as the effect resolves (608.2), publicly.

Wordings: statics "You have hexproof." / "You have shroud." / "You and <permanents> have hexproof." / "You,
planeswalkers you control, and other creatures you control have hexproof." (the permanents' part is an ordinary
layer-6 grant, app/rules/statics.py); effects "You gain protection from everything until your next turn.", "You
gain protection from the color of your choice until end of turn.", "You gain hexproof / shroud until end of turn /
until your next turn.", "You and permanents you control gain hexproof until end of turn.". Refused: protection from
a player, conditional statics ("During your turn, you and this creature have hexproof"),
"your life total can't change" (Teferi's Protection), Auras that grant it ("Enchanted player has …").
"""

from __future__ import annotations

import re
import secrets
from typing import TYPE_CHECKING, Any

from app.rules.characteristics import CardInfo, Characteristics

if TYPE_CHECKING:
    from app.rules.plan import Plan

Context = dict[str, Any]
Definition = dict[str, Any]

_STATIC = re.compile(r"^you(?P<rest>(?:, [A-Za-z][A-Za-z' ]*?)*,? and (?:other )?[A-Za-z][A-Za-z' ]*?)? (?:have|has) (?P<kw>hexproof|shroud)$")
_EFFECT = re.compile(r"^(?P<all>players|you)(?P<also> and permanents you control)? gain (?P<what>hexproof from (?P<h>.+?)|hexproof|shroud|protection from (?P<q>.+?)) "
                     r"(?P<when>until end of turn|until your next turn)$")
_CHOICE = "the color of your choice"


def _lower_first(s: str) -> str:
    return s[:1].lower() + s[1:] if s[:1].isupper() else s


_STATIC_PROTECTION = re.compile(r"^you and (?P<perm>permanents you control) have protection from (?P<q>[A-Za-z]+)$")  # (wave 44C: Gor Muldrak, Amphinologist)


def static_definition(text: str) -> Definition | None:
    t = _lower_first(text.strip().rstrip("."))
    if (p := _STATIC_PROTECTION.fullmatch(t)) is not None:  # -- counters (wave 44C) -- 702.16b: you have protection from that quality, as the permanents do (a layer-6 grant)
        from app.rules import protection, statics

        d = statics.parse(f"Permanents you control have protection from {p['q']}.")
        if d is None or d.get("static") != "grant" or d.get("conditions") or protection.parse(f"protection from {p['q']}") is None:
            return None
        return {**d, "player_shield": "protection", "quality": p["q"]}
    m = _STATIC.fullmatch(t)
    if m is None:
        return None
    kind = m["kw"]
    if not m["rest"]:
        return {"kind": "static", "static": "player_shield", "shield": kind, "effects": []}
    if kind != "hexproof":
        return None
    from app.rules import selectors, statics

    rest = re.sub(r"^and ", "", m["rest"].strip(", "))
    parts = [p.strip() for p in re.split(r",? and |, ", rest) if p.strip()]
    sels = [selectors.parse(p) for p in parts]
    if not sels or any(s is None or s.player is not None or s.zones != ("battlefield",) or s.controller != "you" or s.extras
                       for s in sels):
        return None
    if len(sels) > 1 and any(s is not None and (s.subtypes or s.colors or s.not_types or s.union) for s in sels):
        return None  # (a union of several kinds of subject: card types only)
    if len(sels) == 1:
        d = statics.parse(f"{parts[0][0].upper()}{parts[0][1:]} have hexproof.")
    else:  # "planeswalkers you control, and other creatures you control" → one subject: the union of their types
        from dataclasses import replace

        first = sels[0]
        assert first is not None
        union = replace(first, types=tuple(t for s in sels if s is not None for t in s.types),
                        other=any(s is not None and s.other for s in sels))
        if sum(1 for s in sels if s is not None and s.other) > 1 or any(s is not None and not s.types for s in sels):
            return None
        d = statics.parse("Creatures you control have hexproof.")
        if d is not None:
            d = {**d, "who": union.key()}
    if d is None or d.get("static") != "grant" or d.get("conditions"):
        return None
    return {**d, "player_shield": "hexproof"}


def _effect(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    until = "turn" if m["when"] == "until end of turn" else "next_turn"
    out: list[dict[str, Any]] = []
    q = m["q"]
    if m["all"] == "players":  # -- player shields (wave 51C) -- "Players gain hexproof until end of turn." (Everybody Lives!): every player, each one's own shield (702.11c: against their opponents)
        if q is not None or m["h"] or m["also"] or until != "turn":
            raise ValueError("only hexproof / shroud until end of turn for every player")
        return [{"do": "player_shield", "shield": m["what"], "until": until, "who": "each"}], None
    if m["h"]:  # -- hexproof from (wave 51B) -- Veil of Summer: "You and permanents you control gain hexproof from blue and from black": 702.11d, 702.11f; the card's reminder text says it covers you too
        from app.rules import protection

        if protection.hexproof(f"hexproof from {m['h']}") is None:
            raise ValueError("quality")
        out.append({"do": "player_shield", "shield": "hexproof_from", "quality": m["h"], "until": until})
    elif q is None:
        out.append({"do": "player_shield", "shield": m["what"], "until": until})
    elif q == _CHOICE:
        out.append({"do": "player_shield_choice", "until": until})
    else:
        from app.rules import protection

        if protection.parse(f"protection from {q}") is None:
            raise ValueError("quality")
        out.append({"do": "player_shield", "shield": "protection", "quality": q, "until": until})
    if m["also"]:
        if q is not None or until != "turn":
            raise ValueError("only hexproof / shroud until end of turn for the permanents")
        from app.rules import selectors

        sel = selectors.parse("permanents you control")
        assert sel is not None
        out.append({"do": "grant", "who": sel.key(), "keywords": [], "abilities": [f"Hexproof from {m['h']}"]} if m["h"]
                   else {"do": "grant", "who": sel.key(), "keywords": [m["what"]]})
    return out, None


def _template(m: re.Match[str]) -> Any:
    from app.rules.scripts import _NoMatch

    try:
        return _effect(m)
    except ValueError as exc:
        raise _NoMatch from exc


TEMPLATES: list[tuple[re.Pattern[str], Any]] = [(_EFFECT, _template)]


# -- effects ---------------------------------------------------------------------------------------
def _add(plan: Plan, ctx: Context, shield: str, quality: str | None, until: str, pid: str | None = None) -> None:
    pid = pid or ctx["controller"]
    r = plan.rules
    turn = plan.state.turn.number
    r.player_shields = [x for x in r.player_shields if not (x.get("until") == "turn" and x.get("turn") != turn)]
    label = ctx.get("name") or "An effect"
    r.player_shields.append({"id": secrets.token_hex(4), "player": pid, "controller": ctx["controller"], "shield": shield, "quality": quality,
                             "until": until, "turn": turn, "label": label})
    what = {"protection": f"protection from {quality}", "hexproof_from": f"hexproof from {quality}"}.get(shield, shield)
    plan.note(f"{plan.name(pid)} gains {what} {'until end of turn' if until == 'turn' else 'until their next turn'} ({label})",
              actor=pid)


def player_shield(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    from app.rules.plan import live_players

    for pid in live_players(plan.state) if e.get("who") == "each" else [ctx["controller"]]:  # (wave 51C)
        _add(plan, ctx, e["shield"], e.get("quality"), e["until"], pid)
    return True


def player_shield_choice(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    from app.game.rules_state import DecisionOption
    from app.rules.plan import decide
    from app.rules.protection_grants import COLORS

    src = plan.state.cards.get(ctx.get("source_card") or "")
    decide(plan, player=ctx["controller"], kind="choose_one", prompt=f"{ctx.get('name') or 'Protection'}: protection from which color?",
           options=[DecisionOption(id=c, label=c) for c in COLORS], resume={"step": "player_shield_choice", "ctx": ctx, "e": e},
           source=src)
    return False


def resume_choice(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.game.errors import ActionError
    from app.rules.effects import continue_effects
    from app.rules.protection_grants import COLORS

    ctx, e = d.resume["ctx"], d.resume["e"]
    value = chosen[0] if chosen else ""
    if value not in COLORS:
        raise ActionError("Choose one of the colors")
    plan.note(f"{plan.name(d.player)} chooses {value.lower()}", actor=d.player)
    _add(plan, ctx, "protection", value.lower(), e["until"])
    continue_effects(plan, ctx)


PRIMITIVES = {"player_shield": player_shield, "player_shield_choice": player_shield_choice}
RESUME = {"player_shield_choice": resume_choice}


def turn_began(plan: Plan, ended: set[tuple[str, int]]) -> None:
    """500.4 / 800.4m: "until your next turn" shields end as that player's next turn begins (or would have)."""
    r = plan.rules
    turn = plan.state.turn.number
    r.player_shields = [x for x in r.player_shields if not (x.get("until") == "next_turn" and any(
        x.get("controller") == p and n > int(x.get("turn") or 0) for p, n in ended))
        and not (x.get("until") == "turn" and x.get("turn") != turn)]


# -- reading them ----------------------------------------------------------------------------------
def _shields(plan: Plan, player: str) -> list[tuple[str, str | None, str]]:
    """(shield, quality, label) of every hexproof / shroud / protection ``player`` has now."""
    from app.rules import cast_limits

    r = plan.rules
    turn = plan.state.turn.number
    out = [(str(x["shield"]), x.get("quality"), str(x.get("label") or "an effect")) for x in r.player_shields
           if x.get("player") == player and (x.get("until") != "turn" or x.get("turn") == turn)]
    for src, d in cast_limits._statics(plan.state, plan.info, "player_shield"):
        if src.controller == player:
            out.append((d["shield"], None, src.name or "a permanent"))
    from app.rules import statics

    for src, d in cast_limits._statics(plan.state, plan.info, "grant"):
        if d.get("player_shield") and src.controller == player and statics.conditions_hold(plan, d, source=src, controller=src.controller):  # (wave 35D)
            out.append((d["player_shield"], d.get("quality"), src.name or "a permanent"))  # (wave 44C: protection has its quality)
    return out


def _protects(quality: str | None, source: Characteristics | None) -> bool:
    if quality == "everything":
        return True
    if source is None or quality is None:
        return False
    from app.rules import protection

    return any(q(source) for q in protection.parse(f"protection from {quality}") or [])


def can_target(plan: Plan, chooser: str, player: str, source: Characteristics | None) -> bool:
    """702.11c / 702.18a / 702.16b: may ``chooser``'s spell or ability (from ``source``) target ``player``?"""
    if not plan.rules.player_shields and not _any_static(plan.state, plan.info):
        return True
    from app.rules import protection

    for shield, quality, _ in _shields(plan, player):
        if shield == "shroud" or (shield == "hexproof" and chooser != player):
            return False
        if shield == "protection" and _protects(quality, source):
            return False
        if shield == "hexproof_from" and chooser != player and source is not None and any(q(source) for q in protection.hexproof(f"hexproof from {quality}") or []):
            return False  # (wave 51B) 702.11d: spells and abilities your opponents control from that quality
    return True


def protected_from(plan: Plan, player: str, source: Characteristics | None) -> str | None:
    """702.16c/e/j: the label of a protection ``player`` has from ``source`` (an Aura, a damage source), or None."""
    if not plan.rules.player_shields and not _any_static(plan.state, plan.info):  # (wave 44C: a static's protection too)
        return None
    for shield, quality, label in _shields(plan, player):
        if shield == "protection" and _protects(quality, source):
            return label
    return None


def _any_static(state: Any, info: CardInfo | None) -> bool:
    from app.rules import cast_limits

    if info is None or state.rules is None:
        return False
    return any(d["static"] == "player_shield" or (d["static"] == "grant" and d.get("player_shield"))
               for _, _, d in cast_limits._scan(state, info))

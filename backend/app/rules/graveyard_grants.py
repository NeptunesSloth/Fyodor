"""-- refused grants/replacements (wave 3R2) -- Abilities granted to cards in a graveyard for a
duration (611.2a, 611.2c, 702.34, 113.6). Researched against the Comprehensive Rules of 2026-09-25.

* "Target instant or sorcery card in your graveyard gains flashback until end of turn. The flashback
  cost is equal to its mana cost." (Snapcaster Mage, Flashback, Recoup), "Each instant and sorcery
  card in your graveyard gains flashback until end of turn. …" (Past in Flames, Backdraft
  Hellkite), "… gains flashback {2}{R}{G} until end of turn." (The Fugitive Doctor).
* "Until end of turn, each legendary card in your graveyard gains "You may play this card from your
  graveyard."" (Kethis, the Hidden Hand): a permission per card (601.3, 305.1).

611.2c: the cards an effect like this affects are fixed as it resolves — a card put into the
graveyard later doesn't get it — and 400.7: a card that leaves the graveyard is a new object
without it (cast with flashback, it is exiled as it leaves the stack: 702.34a, the cast's own
record, app/rules/casting.py). "Equal to its mana cost": the mana cost of the card as it is cast; a
card with no mana cost can't be cast this way (its flashback cost can't be paid), and a split card
or a card with an Adventure (two ways to cast it) isn't offered this way (UNVERIFIED which mana cost
applies: left to the players).

A flashback the card prints and a granted one are two ways to cast it; the engine offers the
player a private choice of the distinct available costs.
"""

from __future__ import annotations

import re
import secrets
from typing import TYPE_CHECKING, Any

from app.game.rules_state import Permission

if TYPE_CHECKING:
    from app.game.state import CardInstance, GameState
    from app.rules.characteristics import Characteristics
    from app.rules.plan import Plan

Context = dict[str, Any]

_WHO = r"(?P<who>target (?P<s1>[a-z ]+?) card in your graveyard|each (?P<s2>[a-z ]+?) card in your graveyard)"
_FLASHBACK = re.compile(rf"(?P<lead>until end of turn, )?{_WHO} gains flashback(?: (?P<cost>(?:\{{[^}}]+\}})+))?"
                        r"(?P<trail> until end of turn)?")
_PLAY = re.compile(rf"until end of turn, {_WHO} gains \"you may play this card from your graveyard\.?\"\.?", re.IGNORECASE)
COST_SENTENCE = re.compile(r"the flashback cost is equal to (?:its|that card's) mana cost")
_HARMONIZE = re.compile(rf"^{_WHO} gains harmonize until end of turn$")  # -- one-card wordings (wave 110B) -- 702.180a, 611.2a (Songcrafter Mage)
_HARMONIZE_COST = re.compile(r"its harmonize cost is equal to its mana cost")


def _selector(m: re.Match[str]) -> str:
    from app.rules import selectors
    from app.rules.scripts import _NoMatch

    words = (m.groupdict().get("s1") or m["s2"] or "").replace(" and ", " or ")
    sel = selectors.parse(f"{words} card in your graveyard")
    if sel is None or sel.zones != ("graveyard",) or not sel.card:
        raise _NoMatch
    return sel.key()


def _flashback(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    from app.rules.scripts import _NoMatch

    if bool(m["lead"]) == bool(m["trail"]):
        raise _NoMatch
    sel = _selector(m)
    target = m["s1"] is not None
    e = {"do": "grant_flashback", "who": "target" if target else sel, "cost": m["cost"] or "pending"}
    return [e], sel if target else None


def _harmonize(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    sel = _selector(m)
    return [{"do": "grant_flashback", "who": "target", "cost": "pending", "keyword": "harmonize"}], sel


_JUMP_START = re.compile(rf"^{_WHO} gains jump-start until end of turn$")  # -- (wave 110O) -- 702.133a, 611.2a (Filigree Racer)


def _jump_start(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    sel = _selector(m)
    return [{"do": "grant_flashback", "who": "target", "cost": "none", "keyword": "jump_start"}], sel


_ESCAPE = re.compile(r"^until end of turn, (?P<who>each (?P<s2>[a-z ]+?) card in your graveyard) gains \"escape—(?P<mana>(?:\{[^}]+\})+), "
                     r"exile (?P<n>[a-z]+) other cards from your graveyard\.?\"$", re.IGNORECASE)  # -- (wave 110O) -- 702.138a (The Grim Captain's Locker)


def _escape(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    from app.rules.escape import _WORDS
    from app.rules.scripts import _NoMatch

    n = _WORDS.get(m["n"].lower())
    if n is None:
        raise _NoMatch
    return [{"do": "grant_flashback", "who": _selector(m), "cost": f"{m['mana']}|{n}", "keyword": "escape110o"}], None


def _play(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    sel = _selector(m)
    target = m["s1"] is not None
    return [{"do": "grant_graveyard_play", "who": "target" if target else sel}], sel if target else None


TEMPLATES: list[tuple[re.Pattern[str], Any]] = [
    (re.compile("^" + _FLASHBACK.pattern + "$"), _flashback),
    (_HARMONIZE, _harmonize),
    (_JUMP_START, _jump_start),  # -- (wave 110O) --
    (_ESCAPE, _escape),
    (re.compile("^" + _PLAY.pattern + "$", re.IGNORECASE), _play),
]


def cost_sentence(text: str, effects: list[dict[str, Any]]) -> bool:
    """"The flashback cost is equal to its mana cost." after a grant of flashback: its cost."""
    harmonize = _HARMONIZE_COST.fullmatch(text) is not None
    if not harmonize and not COST_SENTENCE.fullmatch(text):
        return False
    pending = [e for e in effects if e.get("do") == "grant_flashback" and e.get("cost") == "pending" and (e.get("keyword") == "harmonize") == harmonize]
    if len(pending) != 1:
        return False
    pending[0]["cost"] = "mana_cost"
    return True


def unsupported(d: dict[str, Any]) -> bool:
    """A grant of flashback whose cost the text never stated isn't carried out."""
    import json

    return '"cost": "pending"' in json.dumps(d, default=str)


def _cards(plan: Plan, ctx: Context, who: str) -> list[str]:
    from app.rules.effects import _cards as cards

    return [c for c in cards(plan, ctx, who) if plan.state.cards[c].zone.endswith(":graveyard")]


def grant_flashback(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    r = plan.rules
    turn = plan.state.turn.number
    r.graveyard_grants = [g for g in r.graveyard_grants if g.get("turn") == turn]  # (earlier turns' have ended)
    found = _cards(plan, ctx, e["who"])
    for cid in found:
        r.graveyard_grants.append({"id": secrets.token_hex(4), "oid": plan.oid(cid), "card": cid, "turn": turn,
                                   e.get("keyword", "flashback"): e["cost"], "controller": ctx["controller"]})
    if found:
        cost = "equal to its mana cost" if e["cost"] == "mana_cost" else e["cost"]
        kw = e.get("keyword", "flashback")
        names = ", ".join(plan.state.cards[c].name or "a card" for c in found[:5]) + (" …" if len(found) > 5 else "")
        plan.note(f"{names} gain{'s' if len(found) == 1 else ''} {kw} ({cost}) until end of turn", found[:20],
                  actor=ctx["controller"])
    return True


def grant_graveyard_play(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """Each card gets "You may play this card from your graveyard." until end of turn: its owner may
    play it from there (the ability is the card's; its owner controls it in a graveyard)."""
    turn = plan.state.turn.number
    for cid in _cards(plan, ctx, e["who"]):
        card = plan.state.cards[cid]
        plan.rules.permissions.append(Permission(
            id=secrets.token_hex(4), player=card.owner, play=True, cast=True, zone="any", object_id=plan.oid(card), card=cid,
            until="end_of_turn", turn=turn, source=ctx.get("source_object"),
            label=f"{ctx.get('name') or 'An effect'}: play it from your graveyard this turn"))
        plan.note(f"{plan.name(card.owner)} may play {card.name} from their graveyard this turn", [cid], actor=ctx["controller"])
    return True


def flashback_cost(state: GameState, card: CardInstance, ch: Characteristics, info: Any = None) -> str | None:
    """Compatibility reader: the first available granted flashback cost."""
    return next(iter(flashback_costs(state, card, ch, info)), None)


def flashback_costs(state: GameState, card: CardInstance, ch: Characteristics, info: Any = None) -> list[str]:
    """CR 702.34: each currently applicable grant is a separate casting alternative."""
    from app.rules import selectors
    from app.rules.cast_limits import _statics
    from app.rules.plan import Plan

    r = state.rules
    if r is None or not card.zone.endswith(":graveyard"):
        return []
    found: list[str] = []
    if info is not None:
        for src, d in _statics(state, info, "gy_flashback"):
            if src.controller == card.owner and (not d["your_turn"] or state.turn.active_player == card.owner) and selectors.matches(
                    Plan.view(state, card.owner, info), selectors.from_key(d["sel"]), card, ch, card.owner):
                found.append(str(d.get("cost") or "mana_cost"))
    from app.rules import (  # -- wave 110E -- the card's own "as long as … and this card is in your graveyard, it has flashback"
        conditions,
        scripts,
    )

    for d in scripts.definitions(ch).values():
        if d.get("static") == "gy_flashback110e" and card.zone == f"{card.owner}:graveyard" \
                and conditions.holds(Plan.view(state, card.owner, info), {"controller": card.owner, "source_card": card.id}, d["cond"]):
            found.append(str(d["cost"]))
    oid = r.object_id(card.id)
    found.extend(str(g["flashback"]) for g in r.graveyard_grants
                 if g.get("oid") == oid and g.get("turn") == state.turn.number and g.get("flashback"))
    result: list[str] = []
    for cost in found:
        if cost == "mana_cost":
            if not ch.mana_cost or "//" in ch.mana_cost or _two_ways(card):
                continue
            cost = str(ch.mana_cost)
        if cost not in result:
            result.append(cost)
    return result


def _two_ways(card: CardInstance) -> bool:
    """A split card, a card with an Adventure, a double-faced card (two ways to cast it): which mana
    cost is "its" mana cost isn't settled here (UNVERIFIED): not offered."""
    return bool(card.face) or "//" in (card.name or "")


# -- "Choose one of them." (impulse draws: "Exile the top two cards of your library. Choose one of them. Until the end
# of your next turn, you may play that card." — Mishra's Research Desk, Strongbox Raider) ----------------------------
# The controller chooses one of the cards the instruction before exiled (608.2d: a choice made as the ability
# resolves), and "that card" is the one chosen (app/rules/scripts.py binds it). A card exiled face down is offered
# without its name (the chooser may not know it).
_CHOOSE = re.compile(r"choose one of (?:them|those cards|the exiled cards)")


def _choose(m: re.Match[str]) -> tuple[list[dict[str, Any]], None]:
    return [{"do": "choose_one_of", "who": "them:card", "n": 1}], None


TEMPLATES.append((re.compile("^" + _CHOOSE.pattern + "$"), _choose))


def choose_one_of(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    from app.game.rules_state import DecisionOption
    from app.game.visibility import publicly_visible
    from app.rules import context
    from app.rules.plan import decide

    who = str(e.get("who") or "")
    pool = context.objects(plan, ctx, who[len(context.PREFIX):]) if who.startswith(context.PREFIX) else []
    if len(pool) <= 1:
        _bind(plan, ctx, e, pool)
        return True
    options = []
    for i, cid in enumerate(pool):
        card = plan.state.cards[cid]
        shown = publicly_visible(plan.state, card)
        options.append(DecisionOption(id=f"c{i}", label=(card.name or "a card") if shown else "a face-down card",
                                      card_id=cid if shown else None))
    decide(plan, player=ctx["controller"], kind="choose_one", prompt="Choose one of them", options=options,
           resume={"step": "choose_one_of", "ctx": ctx, "e": e, "map": {f"c{i}": cid for i, cid in enumerate(pool)}})
    return False


def _bind(plan: Plan, ctx: Context, e: dict[str, Any], chosen: list[str]) -> None:
    from app.rules import context

    if e.get("as"):
        context.bind_objects(plan, ctx, e["as"], chosen)
    if chosen:
        from app.game.visibility import publicly_visible

        card = plan.state.cards[chosen[0]]
        if publicly_visible(plan.state, card):  # (a face-down card's name is never logged)
            plan.note(f"{plan.name(ctx['controller'])} chose {card.name or 'a card'}", chosen, actor=ctx["controller"])


def resume_choose_one_of(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules.effects import continue_effects

    ctx, e = d.resume["ctx"], d.resume["e"]
    _bind(plan, ctx, e, [d.resume["map"][chosen[0]]])
    continue_effects(plan, ctx)


PRIMITIVES = {"grant_flashback": grant_flashback, "grant_graveyard_play": grant_graveyard_play, "choose_one_of": choose_one_of}
RESUME = {"choose_one_of": resume_choose_one_of}

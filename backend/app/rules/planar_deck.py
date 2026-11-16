"""-- planechase deck (wave D) -- planar-deck manipulation from rules effects and several face-up planes (CR 311.7, 701.31, 901.11c),
read by exact Oracle wording (the playbook's cheapest hook: a native placeholder ability read by ``planar.definition``, its effects
replaced by this module's primitives).

**The planar deck changes only through recorded steps.** A primitive's direct change to ``state.planechase`` isn't replayed (only
table actions and the rules state are), so every change is a server-built ``planar_deck_op`` table action (``actions.PlanarDeckOp``,
handled by ``handlers.planechase.deck_op``): "reveal" (the top ``count`` cards, or until ``planes`` plane cards: public, logged by
name, and shown in ``planechase_view``'s ``revealed`` while they stay revealed), "arrange" (revealed cards on top / on the bottom in a
chosen order / on the bottom in a random order: the random order is decided on the server, ``resolve``, and stored on the action;
the log says how many, never the order), "walk_to" (planeswalk to revealed planes, with or without planeswalking away first).
The model: ``deck[:face_count]`` are face up and not part of the planar deck proper; "the top of your planar deck" is the card after
them (``deck[face_count]``; Pools of Becoming's ruling: the face-up plane isn't one of the cards revealed).

* Stairs to Infinity: "reveal the top card of your planar deck. You may put it on the bottom of your planar deck."
* Interplanar Tunnel: reveal until five planes; the planar controller puts one of them on top (it's the one planeswalked to next, the
  card's ruling), the rest on the bottom in a random order; then 704.6f planeswalks away from the phenomenon (``planar.sba``).
* Pools of Becoming / The Fertile Lands of Saulvinia: "chaos ensues for a particular object" (311.7: the chaos ability of a revealed
  plane card still in the planar deck triggers, controlled by the planar controller; Fertile Lands' ruling: its own doesn't). The
  revealed card's ability is put on the stack from a transient object built from its printing (``planar._source``), as a plane
  planeswalked away from is (113.7a: the ability exists independently of its source). Then the revealed cards go on the bottom in
  an order the planar controller chooses (an "order" choice when there are two or more).
* Norn's Seedcore: "Planeswalk to it, except don't planeswalk away from any plane": the plane is turned face up beside the face-up
  one(s) (``walk_to`` without ``away``; it is planeswalked to, 701.31d / 901.11: "When you planeswalk to" triggers, "until a player
  planeswalks" ends).
* Spatial Merging: "Simultaneously planeswalk to both of them": planeswalk away from the phenomenon (701.31b) and turn both planes face
  up (one step, one event batch).
* Several face-up planes (901.11c; Spatial Merging's / Norn's Seedcore's rulings): each is its own rules object (``handlers.planechase
  .sync``); chaos makes each one's chaos ability trigger (``handlers.planechase.emit_chaos``); planeswalking leaves all of them, their
  owner (the planar controller, 901.15b) choosing the order they go to the bottom in, not revealed (``planeswalk``: an "order" choice).
* Mount Keralia's chaos ability: a prevention record for the rest of the game (``until: "game"``, 615; its ruling: damage from any plane
  named Mount Keralia), to permanents "you" (the planar controller as it resolved) control — the native "Prevent all damage that red
  sources would deal to permanents you control" with the source filter "a Plane named Mount Keralia" (``named_pdk``, replace.py).
* Mount Keralia: "When you planeswalk away from Mount Keralia, it deals damage equal to the number of pressure counters on it …": the
  native "Mount Keralia deals damage … on Mount Keralia …"; the plane is gone by then (901.7a), its counters read as it last existed
  (608.2h: ``handlers.planechase._away`` keeps its last known information before turning it face down).
"""

from __future__ import annotations

import copy
from dataclasses import replace
from typing import TYPE_CHECKING, Any

from app.rules.characteristics import Characteristics
from app.rules.oracle import AbilityText

if TYPE_CHECKING:
    from app.game.state import PlanarCard
    from app.rules.plan import Plan

Def = dict[str, Any]
_LIFE = "you gain 1 life."  # (a native placeholder body: its effects are replaced)

# exact Oracle line → (the native ability read in its place by ``planar.definition``, the effects replacing its own; None: keep them)
REWRITES: dict[str, tuple[str, list[Def] | None]] = {
    "When you planeswalk away from Mount Keralia, it deals damage equal to the number of pressure counters on it to each creature and "
    "each planeswalker.":
        ("When you planeswalk away from Mount Keralia, Mount Keralia deals damage equal to the number of pressure counters on Mount Keralia "
         "to each creature and each planeswalker.", None),
    "Whenever chaos ensues, prevent all damage that planes named Mount Keralia would deal this game to permanents you control.":
        ("Whenever chaos ensues, " + _LIFE, [{"do": "prevent_all", "duration": "game", "scope": {
            "combat": None, "to_objects": 'sel:{"controller":"you"}', "by_source": {"types": ["Plane"], "named_pdk": "Mount Keralia"}}}]),
    "Whenever chaos ensues, reveal the top card of your planar deck. You may put it on the bottom of your planar deck.":
        ("Whenever chaos ensues, " + _LIFE, [{"do": "planar_top_pdk"}]),
    "When you encounter Interplanar Tunnel, reveal cards from the top of your planar deck until you reveal five plane cards. Put a plane "
    "card from among them on top of your planar deck, then put the rest of the revealed cards on the bottom in a random order.":
        ("When you encounter Interplanar Tunnel, " + _LIFE, [{"do": "planar_tunnel_pdk", "planes": 5}]),
    "Whenever chaos ensues, reveal the top three cards of your planar deck. Each of the revealed cards' chaos abilities triggers. Then put "
    "the revealed cards on the bottom of your planar deck in any order.":
        ("Whenever chaos ensues, " + _LIFE, [{"do": "planar_chaos_on_pdk", "count": 3}]),
    "Whenever chaos ensues, reveal cards from the top of your planar deck until you reveal a plane card. Chaos ensues on that plane. Then "
    "put all cards revealed this way on the bottom of your planar deck in any order.":
        ("Whenever chaos ensues, " + _LIFE, [{"do": "planar_chaos_on_pdk", "planes": 1}]),
    "Whenever chaos ensues, reveal cards from the top of your planar deck until you reveal a plane card. Planeswalk to it, except don't "
    "planeswalk away from any plane. Put the rest of the revealed cards on the bottom of your planar deck in any order.":
        ("Whenever chaos ensues, " + _LIFE, [{"do": "planar_walk_to_pdk", "planes": 1, "away": False}]),
    "When you encounter Spatial Merging, reveal cards from the top of your planar deck until you reveal two plane cards. Simultaneously "
    "planeswalk to both of them. Put all other cards revealed this way on the bottom of your planar deck in any order.":
        ("When you encounter Spatial Merging, " + _LIFE, [{"do": "planar_walk_to_pdk", "planes": 2, "away": True}]),
}


def definition(ability: AbilityText, ch: Characteristics) -> Def | None:
    """A plane's or phenomenon's ability in one of the wordings above; else None."""
    from app.rules import planar

    if ability.kind != "triggered" or not planar.planar(ch):
        return None
    entry = REWRITES.get(ability.text.strip())
    if entry is None:
        return None
    native, effects = entry
    d = planar.definition(replace(ability, text=native), ch)
    if d is None or d.get("kind") != "triggered":
        return None
    return {**d, "effects": copy.deepcopy(effects)} if effects is not None else d


# -- steps -----------------------------------------------------------------------------------------------------------------------------
def _live(plan: Plan) -> bool:
    pc = plan.state.planechase
    if pc is None or not pc.deck:
        plan.note("Not a Planechase game: there is no planar deck")
        return False
    return True


def _op(plan: Plan, ctx: dict[str, Any], **fields: Any) -> None:
    plan.do({"type": "planar_deck_op", "by": str(ctx.get("name") or "")[:200], **fields}, actor=_who(plan, ctx))


def _who(plan: Plan, ctx: dict[str, Any]) -> str:
    from app.game.handlers import planechase

    return planechase.planar_controller(plan.state) or ctx["controller"]


def _reveal(plan: Plan, ctx: dict[str, Any], e: Def) -> list[PlanarCard]:
    _op(plan, ctx, op="reveal", count=int(e.get("count") or 0), planes=int(e.get("planes") or 0))
    pc = plan.state.planechase
    return list(pc.revealed) if pc is not None else []


def _ids(cards: list[PlanarCard]) -> list[str]:
    return [c.printing_id for c in cards]


def _bottom_in_order(plan: Plan, ctx: dict[str, Any], cards: list[PlanarCard]) -> bool:
    """Put ``cards`` (revealed) on the bottom of the planar deck in an order the planar controller chooses (an "order" choice for two or
    more: the first chosen ends up at the very bottom). True when done, False when the choice is asked (``_resume_order`` goes on)."""
    if len(cards) < 2:
        _op(plan, ctx, op="arrange", bottom=_ids(cards))
        return True
    from app.game.rules_state import DecisionOption
    from app.rules.plan import decide

    decide(plan, player=_who(plan, ctx), kind="order",
           prompt="Order the cards for the bottom of the planar deck (first chosen ends up at the very bottom)",
           options=[DecisionOption(id=c.printing_id, label=c.name) for c in cards], min_choices=len(cards), max_choices=len(cards),
           resume={"step": "planar_order_pdk", "ctx": ctx, "cards": _ids(cards)})
    return False


def _resume_order(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import effects

    cards = list(d.resume["cards"])
    picked = [c for c in chosen if c in cards]
    order = [*picked, *[c for c in cards if c not in picked]]  # (first chosen at the very bottom)
    _op(plan, d.resume["ctx"], op="arrange", bottom=list(reversed(order)))
    effects.continue_effects(plan, d.resume["ctx"])


# Stairs to Infinity
def top(plan: Plan, ctx: dict[str, Any], e: Def) -> bool:
    """"Reveal the top card of your planar deck. You may put it on the bottom of your planar deck." (the planar controller's choice)."""
    if not _live(plan):
        return True
    shown = _reveal(plan, ctx, {"count": 1})
    if not shown:
        return True
    from app.game.rules_state import DecisionOption
    from app.rules.plan import decide

    decide(plan, player=_who(plan, ctx), kind="confirm", prompt=f"{ctx.get('name') or 'It'}: put {shown[0].name} on the bottom of the planar deck?",
           options=[DecisionOption(id="yes", label="Put it on the bottom"), DecisionOption(id="no", label="Leave it on top")],
           resume={"step": "planar_top_pdk", "ctx": ctx, "card": shown[0].printing_id})
    return False


def _resume_top(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import effects

    r = d.resume
    _op(plan, r["ctx"], op="arrange", bottom=[r["card"]] if chosen and chosen[0] == "yes" else [])
    effects.continue_effects(plan, r["ctx"])


# Interplanar Tunnel
def tunnel(plan: Plan, ctx: dict[str, Any], e: Def) -> bool:
    """Reveal until ``planes`` plane cards; the planar controller puts one of the planes on top, the rest go on the bottom at random."""
    if not _live(plan):
        return True
    shown = _reveal(plan, ctx, e)
    planes = [c for c in shown if not c.phenomenon]
    if len(planes) < 2:
        _op(plan, ctx, op="arrange", top=_ids(planes), random=[c.printing_id for c in shown if c not in planes])
        return True
    from app.game.rules_state import DecisionOption
    from app.rules.plan import decide

    decide(plan, player=_who(plan, ctx), kind="choose_one", prompt=f"{ctx.get('name') or 'It'}: put a plane card on top of the planar deck",
           options=[DecisionOption(id=c.printing_id, label=c.name) for c in planes],
           resume={"step": "planar_tunnel_pdk", "ctx": ctx, "cards": _ids(shown), "planes": _ids(planes)})
    return False


def _resume_tunnel(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import effects

    r = d.resume
    pick = chosen[0] if chosen and chosen[0] in r["planes"] else r["planes"][0]
    _op(plan, r["ctx"], op="arrange", top=[pick], random=[c for c in r["cards"] if c != pick])
    effects.continue_effects(plan, r["ctx"])


# Pools of Becoming, The Fertile Lands of Saulvinia
def chaos_on(plan: Plan, ctx: dict[str, Any], e: Def) -> bool:
    """Reveal (``count`` cards, or until ``planes`` plane cards); the chaos ability of each revealed plane card triggers (311.7: chaos
    ensues for that object, controlled by the planar controller); then all of them go on the bottom in the planar controller's order."""
    if not _live(plan):
        return True
    from app.game.rules_state import emit

    shown = _reveal(plan, ctx, e)
    ctl = _who(plan, ctx)
    for c in shown:
        if not c.phenomenon:  # (a phenomenon has no chaos ability)
            cid = f"planar-shown-{plan.state.seq}.{len(plan.steps)}-{c.printing_id}"[:120]
            emit(plan.state, "planar", counter="chaos", card=cid, object_id=f"{cid}.0", printing=c.printing_id, player=ctl)
    if shown:
        plan.note("Chaos ensues on " + ", ".join(c.name for c in shown if not c.phenomenon) if any(not c.phenomenon for c in shown)
                  else "No plane card was revealed")
    return _bottom_in_order(plan, ctx, shown)


# Norn's Seedcore, Spatial Merging
def walk_to(plan: Plan, ctx: dict[str, Any], e: Def) -> bool:
    """Reveal until ``planes`` plane cards and planeswalk to them (``away``: away from every face-up card first, 701.31b; else beside
    them); the other revealed cards go on the bottom in the planar controller's order."""
    if not _live(plan):
        return True
    shown = _reveal(plan, ctx, e)
    planes = [c for c in shown if not c.phenomenon]
    if planes:
        _op(plan, ctx, op="walk_to", to=_ids(planes), away=bool(e.get("away")))
    return _bottom_in_order(plan, ctx, [c for c in shown if c not in planes])


# -- planeswalking away from several face-up planes (901.11c) ---------------------------------------------------------------------------
def planeswalk(plan: Plan, ctx: dict[str, Any], ctl: str) -> bool:
    """The planar controller planeswalks (``planar.planeswalk``); with two or more face-up planes they choose the order their cards go
    to the bottom in (Spatial Merging's ruling: an order of their choice, not revealed to the others)."""
    from app.game.handlers import planechase

    pc = plan.state.planechase
    faces = pc.deck[:planechase.face_count(pc)] if pc is not None else []
    if len(faces) < 2:
        plan.do({"type": "planeswalk"}, actor=ctl)
        return True
    from app.game.rules_state import DecisionOption
    from app.rules.plan import decide

    decide(plan, player=ctl, kind="order",
           prompt="Planeswalk: order the face-up planes for the bottom of the planar deck (first chosen ends up at the very bottom)",
           options=[DecisionOption(id=c.printing_id, label=c.name) for c in faces], min_choices=len(faces), max_choices=len(faces),
           resume={"step": "planar_away_pdk", "ctx": ctx, "cards": _ids(faces), "ctl": ctl})
    return False


def _resume_away(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import effects

    r = d.resume
    cards = list(r["cards"])
    picked = [c for c in chosen if c in cards]
    order = [*picked, *[c for c in cards if c not in picked]]
    plan.do({"type": "planeswalk", "bottom": list(reversed(order))}, actor=r["ctl"])
    effects.continue_effects(plan, r["ctx"])


PRIMITIVES: dict[str, Any] = {"planar_top_pdk": top, "planar_tunnel_pdk": tunnel, "planar_chaos_on_pdk": chaos_on,
                              "planar_walk_to_pdk": walk_to}
RESUME: dict[str, Any] = {"planar_order_pdk": _resume_order, "planar_top_pdk": _resume_top, "planar_tunnel_pdk": _resume_tunnel,
                          "planar_away_pdk": _resume_away}

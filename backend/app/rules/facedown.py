"""Face-down permanents put onto the battlefield by keyword actions (wave 3F): manifest (701.40),
manifest dread (701.62) and cloak (701.58).

A manifested or cloaked card is turned face down before it enters (708.3), as a 2/2 creature with no
text, no name, no subtypes and no mana cost (cloak: with ward {2}; app/rules/characteristics.py
``face_down_characteristics``), so its own "enters" abilities neither trigger nor apply; other
permanents' "enters" replacement effects see the face-down creature (614.1d, 614.12). Only its
controller may look at it (708.5: app/game/visibility.py); everyone sees how it got face down
(``face_down_kind``). Turning it face up is the special action in app/rules/casting.py
(``turn_face_up``: its mana cost if it's a creature card, 701.40b / 701.58b; its morph or disguise
cost if it has one, 701.40c-d). Leaving the battlefield it is revealed (708.9: app/game/handlers/zones.py).

Instructions to manifest or cloak several cards are carried out one card at a time (701.40e,
701.58e). Manifest dread (701.62a): look at the top two cards, manifest one, put the other into the
graveyard — the choice is the manifesting player's private decision.
"""

from __future__ import annotations

from typing import Any

from app.game.rules_state import DecisionOption
from app.game.state import CardInstance, zone_key
from app.rules import effects
from app.rules.plan import Plan, decide

Context = dict[str, Any]


def put_face_down(plan: Plan, card_id: str, player: str, kind: str, *, actor: str) -> bool:
    """Put one card onto the battlefield face down under ``player``'s control (701.40a / 701.58a).
    Its "enters" replacements are those that apply to the face-down creature (708.3). True if it
    entered."""
    from app.rules import replacements

    card = plan.state.cards.get(card_id)
    if card is None:
        return False
    probe: CardInstance = card.model_copy(update={"face_down": True, "face_down_kind": kind,
                                                  "zone": zone_key(player, "battlefield"), "controller": player})
    ep = replacements.entry_plan(plan, probe, player)
    payload: dict[str, Any] = {"type": "move", "card_ids": [card_id], "to": {"player": player, "zone": "battlefield"},
                               "face_down": True, "face_down_kind": kind}
    if ep.get("tapped"):
        payload["tapped"] = True
    plan.do(payload, actor=actor)
    entered = plan.state.cards.get(card_id)
    if entered is None or not entered.zone.endswith(":battlefield"):
        return False
    replacements.after_entry(plan, card_id, player)  # (other permanents' "enters with" counters: 122.6, 614.1c)
    return True


def manifest(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """"[Player] manifest(s) / cloak(s) the top [N] card(s) of [their] library", "manifest dread":
    for each named player in APNAP order (101.4), one card at a time (701.40e). ``kind``: "manifest"
    or "cloak"; ``dread``: manifest dread (701.62a); ``n``: how many (dread: how many times).
    Binds the manifested permanents ("that creature", "those creatures": ``as``)."""
    players = effects._players(plan, ctx, e.get("who", "you"))
    order = [p for p in plan.apnap() if p in players]
    ctx.setdefault("manifested", [])
    todo = [(p, effects._amount(plan, ctx, e.get("n", 1))) for p in order]
    return _manifest_next(plan, ctx, e, todo)


def _manifest_next(plan: Plan, ctx: Context, e: dict[str, Any], todo: list[tuple[str, int]]) -> bool:
    kind = e.get("kind", "manifest")
    while todo:
        pid, left = todo[0]
        if left <= 0:
            todo = todo[1:]
            continue
        todo = [(pid, left - 1), *todo[1:]]
        library = plan.state.zones.get(zone_key(pid, "library"), [])
        if not library:
            continue  # (nothing to manifest: 701.40f in spirit — the instruction does what it can)
        if e.get("dread"):
            top = library[:2]
            if len(top) == 1:
                _manifested(plan, ctx, pid, top[0], "manifest")
                continue
            plan.do({"type": "look_top", "player": pid, "count": 2}, actor=pid)
            decide(plan, player=pid, kind="choose_cards", prompt="Manifest dread: choose the card to manifest (the other goes "
                   "to your graveyard)",
                   options=[DecisionOption(id=c, label=plan.state.cards[c].name or "Card", card_id=c) for c in top],
                   min_choices=1, max_choices=1,
                   resume={"step": "manifest_dread", "ctx": ctx, "e": e, "todo": todo, "cards": top})
            return False
        _manifested(plan, ctx, pid, library[0], kind)
    _bind(plan, ctx, e)
    return True


def _manifested(plan: Plan, ctx: Context, pid: str, card_id: str, kind: str) -> None:
    if put_face_down(plan, card_id, pid, kind, actor=pid):
        ctx["manifested"] = [*ctx.get("manifested", []), card_id]
        verb = "cloaks" if kind == "cloak" else "manifests"
        plan.note(f"{plan.name(pid)} {verb} a card", actor=pid)


def _bind(plan: Plan, ctx: Context, e: dict[str, Any]) -> None:
    """"That creature" / "those creatures" after the instruction: the face-down permanents it made."""
    if e.get("as"):
        from app.rules import context

        context.bind_objects(plan, ctx, e["as"], [c for c in ctx.get("manifested", [])
                                                  if c in plan.state.cards and plan.state.cards[c].zone.endswith(":battlefield")])


def resume_manifest_dread(plan: Plan, d: Any, chosen: list[str]) -> None:
    r = d.resume
    ctx, e, cards = r["ctx"], r["e"], r["cards"]
    todo: list[tuple[str, int]] = [(str(t[0]), int(t[1])) for t in r["todo"]]
    pid = d.player
    library = plan.state.zones.get(zone_key(pid, "library"), [])
    pick = next((c for c in chosen if c in library), None)
    if pick is not None:
        _manifested(plan, ctx, pid, pick, "manifest")
    rest = [c for c in cards if c != pick and c in plan.state.zones.get(zone_key(pid, "library"), [])]
    if rest:
        plan.do({"type": "move", "card_ids": rest, "to": {"player": pid, "zone": "graveyard"}}, actor=pid)
    if _manifest_next(plan, ctx, e, todo):
        effects.continue_effects(plan, ctx)


PRIMITIVES: dict[str, Any] = {"manifest": manifest}
RESUME: dict[str, Any] = {"manifest_dread": resume_manifest_dread}

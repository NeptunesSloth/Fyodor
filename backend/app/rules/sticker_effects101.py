"""Native optional sticker choices; card, sticker and name position have separate authorities."""

from __future__ import annotations

import re
from typing import Any

_PUT = re.compile(
    r"^(?:you )?may put (?P<n>a|an|up to two) (?:(?P<kind>name|art|ability|power and toughness) )?stickers?(?P<cap> with ticket cost X or less)? on (?P<on>a nonland permanent you own|a creature you own(?: that entered this turn)?|a creature card in your graveyard|it|~)(?P<pin> without paying that sticker's ticket cost)?(?P<rest>\..*)?$",
    re.I,
)
_GET = re.compile(r"^you get (?P<n>(?:\{TK\})+), then (?P<rest>.+)$", re.I)
_DISTRIBUTE = re.compile(
    r"^distribute up to two art stickers among one or two nonland permanents you own\.$", re.I
)


def parse(body: str, it: str | None = None) -> tuple[list[dict[str, Any]], Any, bool] | None:
    from app.rules import scripts, selectors

    text = body.strip()
    if (get := _GET.fullmatch(text)) is not None:
        rest = scripts.parse_effects(get["rest"])
        if rest is None or rest[2]:
            return None
        return (
            [{"do": "player_counter", "who": "you", "counter": "ticket", "n": get["n"].count("{")}, *rest[0]],
            rest[1],
            rest[2],
        )
    m = _PUT.fullmatch(text)
    if m is None and _DISTRIBUTE.fullmatch(text) is None:
        return None
    if m is None:
        return (
            [
                {
                    "do": "put_sticker101",
                    "sel": selectors.Selector(owner="you", not_types=("Land",)).key(),
                    "kind": "art",
                    "n": 2,
                    "as": "placed101",
                }
            ],
            None,
            False,
        )
    on = m["on"].casefold()
    if on.endswith("entered this turn"):
        return None  # Park Bleater needs a separately proved saved-turn history contract.
    descriptor: dict[str, Any] = {
        "do": "put_sticker101",
        "kind": "pt"
        if m["kind"] and m["kind"].casefold() == "power and toughness"
        else m["kind"].casefold()
        if m["kind"]
        else None,
        "n": 2 if m["n"].casefold() == "up to two" else 1,
        "as": "placed101",
    }
    if on in ("it", "~"):
        if on == "it" and it is None:
            return None
        descriptor["who"] = it if on == "it" else "self"
    elif on == "a creature card in your graveyard":
        descriptor["sel"] = selectors.Selector(
            types=("Creature",), card=True, zones=("graveyard",), zone_owner="you"
        ).key()
    else:
        descriptor["sel"] = (
            selectors.Selector(owner="you", not_types=("Land",)).key()
            if on.startswith("a nonland")
            else selectors.Selector(owner="you", types=("Creature",)).key()
        )
        if on.endswith("entered this turn"):
            descriptor["entered"] = True
    if m["cap"]:  # -- cards (wave 110I) -- Pin Collection: ticket cost X or less (the X it was cast with, 107.3m), placed without paying it
        descriptor["cost_cap"] = {"x": 1}
    if m["pin"]:
        descriptor["free"] = True
    rest_text = (m["rest"] or "").lstrip(".").strip()
    if not rest_text:
        return [descriptor], None, False
    rest = scripts.parse_effects(rest_text)
    return ([descriptor, *rest[0]], rest[1], rest[2]) if rest is not None and not rest[2] else None


def _current(plan: Any, frame: Any) -> Any:
    from app.game.rules_state import ObjectRef

    if not frame.get("card"):
        return None
    ref = ObjectRef.model_validate(frame["card"])
    card = plan.state.cards.get(ref.card)
    return (
        card
        if card is not None
        and plan.oid(card) == ref.object_id
        and ref.zone is not None
        and card.zone.rsplit(":", 1)[-1] == ref.zone.rsplit(":", 1)[-1]
        else None
    )


def _options(plan: Any, frame: Any, cid: str) -> list[dict[str, Any]]:
    from app.rules import selectors, stickers101, values

    e, pid = frame["e"], frame["ctx"]["controller"]
    if pid not in plan.live():
        return []
    card = plan.state.cards.get(cid)
    if card is None or (
        e.get("sel")
        and not selectors.matches(
            plan, selectors.from_key(e["sel"]), card, plan.ch(card), pid, frame["ctx"].get("source_card")
        )
    ):
        return []
    return [
        s
        for s in stickers101.available(plan, pid, e.get("kind"))
        if stickers101.can_place(plan, pid, cid, s["id"], free=bool(e.get("free")))
        and (e.get("cost_cap") is None or s["cost"] <= values.evaluate(plan, frame["ctx"], e["cost_cap"]))
    ]


def _cards(plan: Any, frame: Any) -> list[str]:
    from app.rules import effects, history, selectors

    ctx, e = frame["ctx"], frame["e"]
    selected = (
        effects._cards(plan, ctx, e["who"])
        if e.get("who")
        else selectors.candidates(
            plan, selectors.from_key(e["sel"]), ctx["controller"], ctx.get("source_card")
        )
    )
    if e.get("entered"):
        entered = {entry.object_id for entry in history.log_for(plan).entered}
        selected = [cid for cid in selected if plan.oid(plan.state.cards[cid]) in entered]
    return [cid for cid in selected if _options(plan, frame, cid)]


def put(plan: Any, ctx: Any, e: Any) -> bool:
    frame = {"ctx": ctx, "e": e, "left": e.get("n", 1), "receipts": []}
    return _choose_card(plan, frame)


def _choose_card(plan: Any, frame: Any) -> bool:
    from app.game.rules_state import DecisionOption
    from app.rules import context
    from app.rules.plan import decide

    choices = _cards(plan, frame)
    if not choices:
        _done(frame)
        return True
    original = {
        cid: ref.model_dump(mode="json") for cid in choices if (ref := context.ref_of(plan, cid)) is not None
    }
    frame.pop("card", None)
    frame.pop("sticker", None)
    decide(
        plan,
        player=frame["ctx"]["controller"],
        kind="choose_cards",
        prompt="You may choose an object you own for a sticker",
        options=[
            DecisionOption(
                id=cid, label=(plan.ch(plan.state.cards[cid]).name or "Nameless permanent")[:200], card_id=cid
            )
            for cid in choices
        ],
        min_choices=0,
        max_choices=1,
        resume={
            "step": "put_sticker101",
            "ctx": frame["ctx"],
            "frame": frame,
            "stage": "card",
            "originals": original,
        },
    )
    return False


def _choose_sticker(plan: Any, frame: Any) -> bool:
    from app.game.rules_state import DecisionOption
    from app.rules.plan import decide

    card = _current(plan, frame)
    choices = _options(plan, frame, card.id) if card is not None else []
    if not choices:
        _done(frame)
        return True
    decide(
        plan,
        player=frame["ctx"]["controller"],
        kind="choose_one",
        prompt="Choose a sticker (ticket cost is paid when it is placed)",
        options=[
            DecisionOption(
                id=s["id"], label=(s["label"] + (f" — {s['cost']} tickets" if s["cost"] else ""))[:200]
            )
            for s in choices
        ]
        + [DecisionOption(id="decline", label="Do not place a sticker")],
        resume={"step": "put_sticker101", "ctx": frame["ctx"], "frame": frame, "stage": "sticker"},
    )
    return False


def _choose_position(plan: Any, frame: Any) -> bool:
    from app.game.rules_state import DecisionOption
    from app.rules import stickers101
    from app.rules.plan import decide

    card = _current(plan, frame)
    sticker = (
        next((s for s in _options(plan, frame, card.id) if s["id"] == frame["sticker"]), None)
        if card is not None
        else None
    )
    if sticker is None:
        _done(frame)
        return True
    frame["definition"] = sticker
    names = stickers101.words(plan.ch(card).name)
    if sticker["kind"] != "name" or not names:
        return _apply(plan, frame, 0)
    decide(
        plan,
        player=card.controller,
        kind="choose_one",
        prompt="Choose where the name sticker goes (the permanent’s controller chooses)",
        options=[
            DecisionOption(id=str(i), label=(" ".join([*names[:i], sticker["text"], *names[i:]]))[:200])
            for i in range(len(names) + 1)
        ],
        resume={"step": "put_sticker101", "ctx": frame["ctx"], "frame": frame, "stage": "position"},
    )
    return False


def _apply(plan: Any, frame: Any, position: int) -> bool:
    from app.rules import context, stickers101

    card = _current(plan, frame)
    pid = frame["ctx"]["controller"]
    if card is not None and stickers101.can_place(
        plan, pid, card.id, frame["sticker"], free=bool(frame["e"].get("free"))
    ):
        stickers101.place(plan, pid, card.id, frame["sticker"], position, free=bool(frame["e"].get("free")))
        frame["receipts"].append(
            {"card": frame["card"], "sticker": frame["definition"], "position": position}
        )
        context.bind_objects(plan, frame["ctx"], frame["e"]["as"], [card.id])
    frame["left"] -= 1
    if frame["left"]:
        return _choose_card(plan, frame)
    _done(frame)
    return True


def _done(frame: Any) -> None:
    frame["ctx"].setdefault("sticker_receipts101", {})[frame["e"]["as"]] = frame["receipts"]


def resume(plan: Any, decision: Any, chosen: list[str]) -> None:
    from app.rules import effects

    data, frame = decision.resume, decision.resume["frame"]
    if not chosen or chosen == ["decline"]:
        _done(frame)
        effects.continue_effects(plan, frame["ctx"])
        return
    stage = data["stage"]
    if stage == "card":
        frame["card"] = data["originals"][chosen[0]]
        finished = _choose_sticker(plan, frame)
    elif stage == "sticker":
        frame["sticker"] = chosen[0]
        finished = _choose_position(plan, frame)
    else:
        finished = _apply(plan, frame, int(chosen[0]))
    if finished:
        effects.continue_effects(plan, frame["ctx"])


PRIMITIVES = {"put_sticker101": put}
RESUME = {"put_sticker101": resume}


def replaced_choice(plan: Any, decision: Any) -> bool:
    """Re-evaluate a pending placement after a player leaves, including current name authority."""
    data = decision.resume or {}
    if data.get("step") != "put_sticker101":
        return False
    frame = data["frame"]
    if frame["ctx"]["controller"] not in plan.live():
        return False
    from app.rules import effects

    plan.rules.decision = None
    step = data["stage"]
    finished = (
        _choose_card(plan, frame)
        if step == "card"
        else _choose_sticker(plan, frame)
        if step == "sticker"
        else _choose_position(plan, frame)
    )
    if finished:
        effects.continue_effects(plan, frame["ctx"])
    return True

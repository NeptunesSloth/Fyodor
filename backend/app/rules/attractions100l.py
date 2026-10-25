"""-- Attractions (wave 100L) -- CR 2026-09-25: 717, 701.51, 701.52, 702.159, 505.5.

* 717.2, 103.3a: a player's Attraction deck is a supplementary deck in the command zone: the hidden zone ``<pid>:attractions``, built from
  the deck's "Attractions" section and shuffled as the game begins (app/game/factory.py). Its last card is its top. An old save has none:
  that player plays without an Attraction deck (701.51a: then nothing is opened).
* 717.1: the numbers lit up are per printing and aren't in the card data: ``LIT`` (Scryfall's ``attraction_lights`` for the Commander-legal
  Unfinity printings). Only an Attraction *card* has lights; a token copy has none (it is never visited).
* 701.51b-c: "open an Attraction": the top card of your Attraction deck onto the battlefield under your control; "Whenever you open an
  Attraction" triggers for each one that entered this way.
* 701.52a: "roll to visit your Attractions": roll a six-sided die (a roll, 706: Wyll's extra die, Dee Kay's "Whenever you roll a 2"), then each
  Attraction you control with that number lit is visited (a turn fact: "the number of Attractions you've visited this turn" counts the
  Attractions, each once) and its visit ability (702.159a: "Whenever you roll to visit your Attractions, if the result is equal to a number
  that is lit up on this Attraction, [effect]") triggers. 505.5: the active player does it as their precombat main phase begins, if they
  control one or more Attractions (a turn-based action: no stack).
* 717.6: a card with an Astrotorium back that would be put anywhere but the battlefield, exile or the command zone goes to its owner's command
  zone instead (its junkyard, 717.6a: a face-up pile, not a zone of its own): app/rules/replacements.zone_candidates.
* 702.159b: "claim the prize!" performs the visit ability's "Prize —" paragraph (Pick-a-Beeble, the one Commander-legal prize).
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from app.game.state import zone_key

if TYPE_CHECKING:
    from app.game.state import CardInstance
    from app.rules.characteristics import Characteristics
    from app.rules.oracle import AbilityText
    from app.rules.plan import Plan

ZONE = "attractions"
ROLL: list[dict[str, Any]] = [{"do": "roll", "sides": 6, "count": 1}, {"do": "visit100l"}]  # 701.52a
_LIT = (
    "200a:26 200b:36 200c:46 200d:56 201a:26 201b:36 201c:46 201d:56 202a:236 202b:246 202c:256 202d:346 202e:356 202f:456 "
    "204a:26 204b:36 204c:46 204d:56 205a:26 205b:36 205c:46 205d:56 206a:236 206b:246 206c:256 206d:346 206e:356 206f:456 "
    "209a:236 209b:246 209c:256 209d:346 209e:356 209f:456 210:456 211a:26 211b:36 211c:46 211d:56 212a:236 212b:246 212c:256 "
    "212d:346 212e:356 212f:456 216a:26 216b:46 217a:36 217b:46 218a:26 218b:36 218c:46 218d:56 219a:236 219b:246 219c:256 "
    "219d:346 219e:356 219f:456 222a:26 222b:56 223a:236 223b:246 223c:256 223d:346 223e:356 223f:456 225a:26 225b:36 225c:46 "
    "225d:56 227a:236 227b:246 227c:256 227d:346 227e:356 227f:456 229a:256 229b:346 231a:26 231b:46 232a:26 232b:36 232c:46 "
    "232d:56 234a:26 234b:36")
LIT = {k: frozenset(int(n) for n in v) for k, v in (x.split(":") for x in _LIT.split())}


def _printing(plan: Plan, card: CardInstance) -> dict[str, Any] | None:
    return None if card.is_token or not card.card_id else plan.info.get(card.card_id)


def lights(plan: Plan, card: CardInstance) -> frozenset[int]:
    data = _printing(plan, card) or {}
    return LIT.get(str(data.get("collector_number")), frozenset()) if data.get("set_code") == "unf" else frozenset()


def astrotorium(plan: Plan, card: CardInstance) -> bool:
    """717.6: an Attraction card (they all have the Astrotorium back); not a token, nor another card that is a copy of one."""
    return "Attraction" in str((_printing(plan, card) or {}).get("type_line") or "").partition("—")[2].split()


def _yours(plan: Plan, pid: str) -> list[CardInstance]:
    """The Attractions ``pid`` controls (the battlefield zone a card is in is its controller's)."""
    return [c for cid in plan.state.zones.get(zone_key(pid, "battlefield"), [])
            if plan.in_game(c := plan.state.cards[cid]) and "Attraction" in plan.ch(c).subtypes]


def precombat_main(plan: Plan) -> None:
    """505.5: as their precombat main phase begins, the active player rolls to visit their Attractions if they control one or more."""
    from app.rules import effects

    ap = plan.active
    if ap in plan.live() and _yours(plan, ap):
        effects.run_body(plan, {"controller": ap, "source_card": None, "source_object": None, "name": "Roll to visit your Attractions",
                                "effects": [dict(e) for e in ROLL], "next": 0, "body_done": {"do": "noop"}})


def open_attraction(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """701.51b: the top ``n`` cards of the Attraction deck onto the battlefield together (none without a deck, 701.51a)."""
    from app.rules import attachments

    pid = ctx["controller"]
    deck = plan.state.zones.get(zone_key(pid, ZONE), [])
    top = deck[::-1][: int(e.get("n", 1))]
    if not top:
        return True
    ctx["effects"] = [*ctx["effects"][: ctx["next"]], {"do": "opened100l", "cards": top}, *ctx["effects"][ctx["next"]:]]
    return attachments.enter(plan, [{"card": cid, "player": pid, "actor": pid} for cid in top], ctx)


def opened(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """701.51c: "Whenever you open an Attraction": once per Attraction card that entered the battlefield this way."""
    from app.game.rules_state import emit, track

    pid = ctx["controller"]
    for cid in e["cards"]:
        c = plan.state.cards.get(cid)
        if c is not None and c.zone == zone_key(pid, "battlefield") and astrotorium(plan, c):
            emit(plan.state, "designation", counter="open_attraction", player=pid, card=cid, object_id=plan.oid(c))
    track(plan.state)
    return True


def visit(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """701.52a after its die: each Attraction you control with the result lit up is visited; then the visit abilities trigger."""
    from app.game.rules_state import TurnFact, emit, track, turn_log_now

    if not ctx.get("dice"):
        return True
    pid, result = ctx["controller"], int(ctx["die"])
    log = turn_log_now(plan.state)
    for c in _yours(plan, pid):
        if result in lights(plan, c):
            if log is not None:
                log.facts.append(TurnFact(kind="visit", player=pid, object_id=plan.oid(c)))
            emit(plan.state, "designation", counter="visit", player=pid, card=c.id, object_id=plan.oid(c))
    emit(plan.state, "designation", counter="roll_visit", player=pid, amount=result)
    track(plan.state)
    return True


def visited(plan: Plan, pid: str) -> int:
    """The Attractions ``pid`` visited this turn, each once (the object it was then)."""
    from app.rules import history

    return len({f.object_id for f in history.log_for(plan).facts if f.kind == "visit" and f.player == pid})


def claim(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """702.159b: "claim the prize!" — the "Prize —" actions come next (``prize`` effects); "Whenever you claim the prize" triggers."""
    from app.game.rules_state import emit, track

    emit(plan.state, "designation", counter="claim_prize", player=ctx["controller"])
    track(plan.state)
    return True


def matches(plan: Plan, cond: dict[str, Any], watcher: CardInstance, info: dict[str, Any]) -> bool:
    """A "roll to visit" trigger: a visit ability only for a number lit up on its Attraction (702.159a); "if you roll a 6" (an intervening
    "if": the result never changes, 603.4)."""
    result = int(info.get("amount") or 0)
    return (not cond.get("lit") or result in lights(plan, watcher)) and cond.get("result", result) == result


_PRIZE = re.compile(r"(?P<head>.+) Then if (?P<cond>[^,.]+), claim the prize!")
_VISIT = "Whenever you roll to visit your Attractions, "
_STORY = " At the beginning of the next end step, if any of those cards remain exiled, put them on the bottom of your library in any order."


def definition(ability: AbilityText, ch: Characteristics) -> dict[str, Any] | None:
    """"Visit — [effect]" (702.159a: a triggered ability; "Visit — Choose one." with its bulleted modes: Balloon Stand); its "Prize —"
    paragraph is part of it (702.159b: read with the visit line, the paragraph's own line is covered by it); "Whenever you roll to visit your
    Attractions, if you roll a 6, …" ("Lifetime" Pass Holder)."""
    import dataclasses

    from app.rules import conditions, modal_abilities, scripts

    def trigger(body: str) -> dict[str, Any] | None:
        d = scripts.define(dataclasses.replace(ability, text=_VISIT + body[:1].lower() + body[1:], kind="triggered"), ch)
        return d if d is not None and d.get("kind") == "triggered" and (d.get("cond") or {}).get("event") == "roll_visit" else None

    text = ability.text
    if not text.startswith(("Visit — ", "Prize — ", "• ", _VISIT)) or (text.startswith("• ") and "Visit — Choose one." not in ch.oracle_text):
        return None
    if (six := re.fullmatch(_VISIT + r"if you roll an? (?P<n>\d), (?P<rest>.+)", text)) and (d := trigger(six["rest"])):
        return {**d, "cond": {**d["cond"], "result": int(six["n"])}}
    before = [a for a in ch.abilities if a.index < ability.index and not a.text.startswith("• ")][-1:]
    if text.startswith("• "):  # a mode of "Visit — Choose one." (the header's definition holds the modes)
        return {"kind": "mode", "of": before[0].index, "form": "triggered", "memory": None, "effects": []} \
            if before and before[0].text == "Visit — Choose one." and definition(before[0], ch) is not None else None
    if text.startswith("Prize — "):
        return {"kind": "static", "static": "prize100l", "effects": []} if before and definition(before[0], ch) is not None else None
    if not text.startswith("Visit — "):
        return None
    body = text[len("Visit — "):]
    if body == "Choose one.":
        d = modal_abilities.definitions(dataclasses.replace(ability, text=_VISIT + "choose one —", kind="triggered"), ch).get(ability.index)
        return {**d, "cond": {**d["cond"], "lit": True}} if d is not None and (d.get("cond") or {}).get("event") == "roll_visit" else None
    story = body.endswith(_STORY)
    m = _PRIZE.fullmatch(body.removesuffix(_STORY))
    if (d := trigger(m["head"] if m else body.removesuffix(_STORY))) is None:
        return None
    effects = d["effects"]
    if story:  # (Storybook Ride: a delayed trigger with an intervening "if", 603.7c, 603.4: those cards still in exile go to the bottom)
        bound = next((e["as"] for e in effects if e.get("do") == "exile_top" and e.get("as")), None)
        if bound is None:
            return None
        still = {"exiled100l": bound}
        effects = [*effects, {"do": "delayed", "when": {"kind": "step", "step": "end", "whose": "next", "if": still}, "n": 2},
                   {"do": "deferred:only_if", "cond": still, "skip": 1}, {"do": "deferred:bottom_linked100g", "who": f"ref:{bound}"}]
    if m:
        after = next((a for a in ch.abilities if a.index == ability.index + 1), None)
        if after is None or not after.text.startswith("Prize — "):
            return None
        # (Pick-a-Beeble: "…, then sacrifice ~ and open an Attraction." is the two instructions in order, 608.2c)
        prize = scripts.parse_effects(scripts.self_text(after.text[len("Prize — "):].replace(" and open an Attraction.", ". Open an Attraction."), ch.name))
        cond = conditions.parse(scripts.self_text(m["cond"], ch.name), objects=True)
        if prize is None or prize[1] is not None or cond is None:
            return None
        then = [{"do": "claim100l"}, *prize[0]]
        effects = [*effects, {"do": "only_if", "cond": cond, "skip": len(then)}, *then]
    return {**d, "cond": {**d["cond"], "lit": True}, "effects": effects}


def still_exiled(plan: Plan, ctx: dict[str, Any], cond: dict[str, Any]) -> bool:
    """"if any of those cards remain exiled": one of them is still that object in exile (400.7)."""
    from app.rules import context

    return any(plan.state.cards[c].zone.endswith(":exile") for c in context.objects(plan, ctx, cond["exiled100l"]))


PRIMITIVES = {"open_attraction": open_attraction, "opened100l": opened, "visit100l": visit, "claim100l": claim}

# -- opening hand (wave 18C) --
"""Opening-hand actions: "If this card is in your opening hand, you may begin the game with it on the battlefield." (the
Leylines, Leyline Axe, Quicksilver), "You may reveal this card from your opening hand. If you do, at the beginning of the first
upkeep, …" (the Chancellors, Devourer of Destiny, Sphinx of Foresight) and Gemstone Caverns. Researched against CR 2026-09-25.

* 103.6: once the mulligan process (103.5) is complete, the starting player may take any such actions in any order, then each
  other player in turn order may do the same. One decision per player, in that order, asked as soon as the last player has kept
  (the mulligan actions carry the compiled steps: ``app/game/handlers/mulligan.py``).
* 103.6a: a card that lets a player begin the game with it on the battlefield is put onto the battlefield by that player (it
  enters like any permanent: "enters with" replacements, its enters triggers).
* 103.6b: a card revealed from the opening hand stays revealed until the first turn begins (hidden again when the last player
  has acted); each card may be revealed only once. The delayed triggered ability that "If you do" creates (603.7a) is the
  revealer's, whatever happens to the card.
* "the first upkeep" is the first upkeep step of the game (the starting player's); "your first upkeep" is the first upkeep of
  the revealer's own turns; "your first main phase of the game" their first precombat or postcombat main phase (505.1).
* Gemstone Caverns: only a player who is not the starting player may begin the game with it; it enters with a luck counter, and
  if the player did, they exile a card from their hand (the card of their choice, face up: exiled cards are public).

Privacy: every player is asked, with the same prompt, whether or not their hand holds such a card, so the decision's existence
and timing say nothing about a hand (the options are shown to the chooser only: rules/view.decision_view).

Not read (stay manual): Chancellor of the Annex ("when each opponent casts their first spell of the game": a per-opponent
delayed cast trigger), cards whose other lines ask for a choice as they enter (Leyline of Transformation: "As this enchantment
enters, choose a creature type" would pause the game's start) and any other wording.
"""

from __future__ import annotations

import re
import secrets
from typing import TYPE_CHECKING, Any

from app.game.rules_state import DecisionOption, DelayedTrigger
from app.game.state import zone_key

if TYPE_CHECKING:
    from app.rules.plan import Plan

STATIC = "opening_hand"
_BEGIN = re.compile(r"^If (?:this card|~) is in your opening hand(?P<ns> and you're not the starting player)?, you may begin the "
                    r"game with (?:it|him|her|them|~|this card) on the battlefield(?P<luck> with a luck counter on it)?\."
                    r"(?P<exile> If you do, exile a card from your hand\.)?$")
_REVEAL = re.compile(r"^You may reveal this card from your opening hand\. If you do, (?P<rest>.+)$")
_AT = r"at the beginning of (?P<when>the first upkeep|your first upkeep|your first main phase of the game)"
_LEAD = re.compile(rf"^{_AT}, (?P<body>.+)$")
_TAIL = re.compile(rf"^(?P<body>.+?) {_AT}\.$")
WHEN = {
    "the first upkeep": {"kind": "step", "step": "upkeep", "whose": "next"},  # 500.1: the first upkeep of the game
    "your first upkeep": {"kind": "step", "step": "upkeep", "whose": "you"},
    "your first main phase of the game": {"kind": "step", "step": "main", "whose": "you"},  # 505.1
}
PROMPT = "Opening hand: choose the cards to use, or none (103.6)"


_POWDER = re.compile(r"Any time you could mulligan and (?:~|[^,.]+?) is in your hand, you may exile all the cards from your hand, then "
                     r"draw that many cards\.(?: \(You can do this in addition to taking mulligans\.\))?")


def powder_ok(data: dict[str, Any] | None) -> bool:
    """Whether a card (Scryfall data) has "Any time you could mulligan and … is in your hand, you may exile all the cards from your hand,
    then draw that many cards." (Serum Powder; 103.5b)."""
    if not data:
        return False
    texts = [str(data.get("oracle_text") or ""), *(str(f.get("oracle_text") or "") for f in data.get("faces") or [])]
    return any(_POWDER.search(t) for t in texts)


def powder_cards(state: Any, pid: str, info: Any) -> list[str]:
    """The cards in ``pid``'s hand that can do that now (their owner's own view of their own hand)."""
    out = []
    for cid in state.zones.get(zone_key(pid, "hand"), []):
        card = state.cards[cid]
        if card.card_id and powder_ok(info.get(card.card_id)):
            out.append(cid)
    return out


def definition(text: str, ch: Any) -> dict[str, Any] | None:
    """The opening-hand ability a line of Oracle text is, or None (not read)."""
    from app.rules import scripts

    if _POWDER.fullmatch(text.strip()):  # 103.5b: carried out by the pregame (app/game/handlers/mulligan.py ``powder``)
        return {"kind": "static", "static": "mulligan_powder", "effects": []}
    if "Aura" in ch.subtypes:
        return None  # (an Aura's host choice is not read here)
    t = text.strip()
    if (m := _BEGIN.match(t)) is not None:
        if bool(m["luck"]) != bool(m["exile"]):
            return None
        return {"kind": "static", "static": STATIC, "action": "begin", "effects": [],
                **({"not_starting": True} if m["ns"] else {}), **({"counter": "luck", "exile": True} if m["luck"] else {})}
    m = _REVEAL.match(t)
    rest = _LEAD.match(m["rest"]) if m else None
    rest = rest or (_TAIL.match(m["rest"]) if m else None)
    if rest is None:
        return None
    body = rest["body"].rstrip()
    body = body[:1].upper() + body[1:]
    if not body.endswith("."):
        body += "."
    found = scripts._parse_effects_checked(body, None, False)
    if found is None or found[1] or found[2] or not found[0] or any(e.get("do") in ("delayed", "until") for e in found[0]):
        return None
    return {"kind": "static", "static": STATIC, "action": "reveal", "when": dict(WHEN[rest["when"]]), "effects": [],
            "delayed": found[0]}


def eligible(plan: Plan, pid: str) -> list[tuple[str, dict[str, Any]]]:
    """The cards in ``pid``'s hand with an opening-hand ability they can use now (103.6)."""
    from app.rules import scripts

    out = []
    for cid in plan.state.zones.get(zone_key(pid, "hand"), []):
        card = plan.state.cards[cid]
        if plan.manual(card):
            continue
        for d in scripts.definitions(plan.ch(card)).values():
            if d.get("static") == STATIC and not (d.get("not_starting") and pid == plan.active):
                out.append((cid, d))
                break
    return out


def start(plan: Plan) -> None:
    """The mulligans are done: ask each player, the starting player first, in turn order (103.6)."""
    order = [plan.active]
    while (nxt := plan.after(order[-1])) != order[0]:
        order.append(nxt)
    ask(plan, [p for p in order if p in plan.live()])


def ask(plan: Plan, order: list[str]) -> None:
    from app.rules.plan import decide

    order = [p for p in order if p in plan.live()]  # (someone may have left the game meanwhile)
    if not order:
        finish(plan)
        return
    pid = order[0]
    options = [DecisionOption(id=c, label=plan.state.cards[c].name or "Card", card_id=c) for c, _ in eligible(plan, pid)]
    decide(plan, player=pid, kind="choose_cards", prompt=PROMPT, options=options, min_choices=0, max_choices=len(options),
           resume={"step": "opening_hand", "order": order})


def resume(plan: Plan, d: Any, chosen: list[str]) -> None:
    """One player's answer: the cards they use, in the order they chose them (103.6: any order)."""
    order = list(d.resume["order"])
    pid = order[0]
    allowed = dict(eligible(plan, pid))
    use = [c for c in chosen if c in allowed]
    act(plan, pid, use, order[1:])


def act(plan: Plan, pid: str, queue: list[str], rest: list[str]) -> None:
    while queue:
        cid, queue = queue[0], queue[1:]
        card = plan.state.cards.get(cid)
        d = dict(eligible(plan, pid)).get(cid)
        if card is None or d is None or not card.zone.endswith(":hand"):
            continue
        if d["action"] == "reveal":
            plan.do({"type": "reveal", "card_ids": [cid]}, actor=pid)  # 103.6b
            plan.rules.opening_revealed.append(cid)
            plan.rules.delayed.append(DelayedTrigger(
                id=secrets.token_hex(4), controller=pid, source_card=cid, source_object=plan.oid(card), name=card.name or "",
                when=dict(d["when"]), effects=[dict(e) for e in d["delayed"]], turn=plan.state.turn.number,
                step=plan.state.turn.phase))
            continue
        from app.rules import attachments

        plan.note(f"{plan.name(pid)} begins the game with {card.name or 'a card'} on the battlefield", [cid])
        entry = {"card": cid, "player": pid, "actor": pid, "tapped": False,
                 **({"counter": d["counter"], "counter_n": 1} if d.get("counter") else {})}
        # -- opening-hand entry choice (wave 110A) -- 614.12a: "As ~ enters, choose …" pauses; on answer the sequence goes on (103.6)
        ctx = {"controller": pid, "source_card": cid, "source_object": None, "name": card.name or "", "effects": [], "next": 0, "x": None,
               "event": None, "body_done": {"do": "opening_go110a", "pid": pid, "queue": queue, "rest": rest}}
        if not attachments.enter(plan, [entry], ctx):
            return
        if d.get("exile"):
            hand = list(plan.state.zones.get(zone_key(pid, "hand"), []))
            if hand:
                _ask_exile(plan, pid, hand, queue, rest)
                return
    ask(plan, rest)


def _ask_exile(plan: Plan, pid: str, hand: list[str], queue: list[str], rest: list[str]) -> None:
    from app.rules.plan import decide

    decide(plan, player=pid, kind="choose_cards", prompt="Exile a card from your hand", min_choices=1, max_choices=1,
           options=[DecisionOption(id=c, label=plan.state.cards[c].name or "Card", card_id=c) for c in hand],
           resume={"step": "opening_exile", "pid": pid, "queue": queue, "rest": rest})


def resume_exile(plan: Plan, d: Any, chosen: list[str]) -> None:
    pid = d.resume["pid"]
    if chosen and chosen[0] in plan.state.zones.get(zone_key(pid, "hand"), []):
        plan.do({"type": "move", "card_ids": chosen[:1], "to": {"player": pid, "zone": "exile"}}, actor=pid)
    act(plan, pid, d.resume["queue"], d.resume["rest"])


def finish(plan: Plan) -> None:
    """Everyone has acted: the revealed cards are hidden again (103.6b: until the first turn begins) and play starts."""
    r = plan.rules
    shown = [c for c in r.opening_revealed if c in plan.state.cards and plan.state.cards[c].zone.endswith(":hand")]
    r.opening_revealed = []
    if shown:
        plan.do({"type": "hide", "card_ids": shown})
    r.priority = None  # (settle gives the starting player priority)


def _go(plan: Plan, then: dict[str, Any]) -> None:
    act(plan, then["pid"], list(then["queue"]), list(then["rest"]))


from app.rules import replace as _replace  # noqa: E402

_replace.THEN["opening_go110a"] = _go

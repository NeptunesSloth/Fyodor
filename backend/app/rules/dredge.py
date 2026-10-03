"""-- keyword mechanics (wave 9D) -- dredge N (702.52).

"Dredge N" is a static ability that functions only while the card is in a player's graveyard: "As long as you have at least N
cards in your library, if you would draw a card, you may instead mill N cards and return this card from your graveyard to
your hand." (702.52a; 702.52b: a player with fewer cards than N in their library can't mill any of them this way.)

It is one more replacement effect on the draw choke point (app/rules/replace.py, 614.11, 616.1): a candidate for each dredge card
in a graveyard whose owner is the player drawing, applicable while their library holds at least N cards (after the earlier draws
of the same call, 121.2) and the card is still there. It is optional ("you may instead"): the drawing player is asked whenever
one applies, and may decline (the draw happens as it would have). The replaced draw never happens (614.6): no card is drawn,
so nothing that counts cards drawn counts it. Mill and the return are the final events, in that order. "Dredge" given to cards
by another permanent (The Necrobloom) isn't read.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan
    from app.rules.replace import Candidate

_PIECE = re.compile(r"dredge (\d+)")


def amounts(line: str) -> list[int]:
    """The dredge numbers of a keyword line ("Dredge 3" → [3])."""
    out = []
    for p in re.split(r"[,;]\s*", re.sub(r"\s*\(.*?\)", "", line).strip().rstrip(".")):
        m = _PIECE.fullmatch(p.strip().lower())
        if m:
            out.append(int(m[1]))
    return out


def supported(line: str) -> bool:
    return len(amounts(line)) == 1


def candidates(plan: Plan) -> list[Candidate]:
    """A candidate for each dredge instance on a card in a graveyard (the owner is "you", 108.3)."""
    from app.rules.layers import timestamp
    from app.rules.replace import Candidate

    out: list[Candidate] = []
    for key, ids in plan.state.zones.items():
        if not key.endswith(":graveyard") or key.split(":")[0] not in plan.live():
            continue
        for cid in ids:
            card = plan.state.cards[cid]
            if card.is_token or not plan.in_game(card) or plan.manual(card):
                continue
            for ab in plan.ch(card).abilities:
                if ab.kind != "keywords" or "dredge" not in ab.keywords:
                    continue
                for n in amounts(ab.text):
                    out.append(Candidate(id=f"d:{plan.oid(card)}:{ab.index}", event="draw", match={}, op={"do": "dredge", "n": n, "card": cid},
                                         controller=card.owner, source_card=cid, source_oid=plan.oid(card),
                                         seq=(timestamp(plan.state, cid), 0, ab.index), label=f"{card.name} (dredge {n})",
                                         optional=True))
    return out


def applies(plan: Plan, c: Candidate, ev: dict[str, Any], sim: dict[str, Any]) -> bool:
    card = plan.state.cards.get(c.op["card"])
    return (ev["player"] == c.controller and card is not None and card.zone == f"{c.controller}:graveyard"
            and c.op["card"] not in sim.get("dredged", ()) and sim["library"].get(ev["player"], 0) >= c.op["n"])


def apply(c: Candidate, ev: dict[str, Any]) -> list[dict[str, Any]]:
    return [{"kind": "dredge", "player": ev["player"], "card": c.op["card"], "n": c.op["n"]}]


def perform_sim(ev: dict[str, Any], sim: dict[str, Any]) -> None:
    sim["library"][ev["player"]] = max(0, sim["library"].get(ev["player"], 0) - ev["n"])
    sim.setdefault("dredged", []).append(ev["card"])


def do(plan: Plan, ev: dict[str, Any]) -> None:
    """702.52a: mill N cards, return the card from the graveyard to its owner's hand."""
    pid = ev["player"]
    library = plan.state.zones.get(f"{pid}:library", [])
    n = min(ev["n"], len(library))
    if n:
        plan.do({"type": "mill", "player": pid, "count": n}, actor=pid)
    card = plan.state.cards.get(ev["card"])
    if card is not None and card.zone == f"{pid}:graveyard":
        plan.do({"type": "move", "card_ids": [card.id], "to": {"player": pid, "zone": "hand"}}, actor=pid)

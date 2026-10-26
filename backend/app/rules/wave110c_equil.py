"""-- Land Equilibrium (wave 110C) -- "If an opponent who controls at least as many lands as you do would put a land onto the battlefield, that player instead
puts that land onto the battlefield then sacrifices a land of their choice."

614.1a / 614.12: a replacement effect of the land entering, judged before it enters (the lands each player controls then; rulings 2009-10-01: it applies however
the land would enter, played or put by a spell or ability). The sacrifice (701.21a) is part of the replaced event, not a trigger: it happens right after the
land has entered, so nothing can respond, and the chosen land may be the land that just entered. Each Land Equilibrium that applies adds one sacrifice
(ponytail: several of them are applied one after another by their opponent without the 616.1 ordering question, which changes nothing: the same sacrifices).
"That player" is the opponent who puts the land, not whoever controls it (rulings 2009-10-01: Yavimaya Dryad puts it under another player's control and that
opponent still sacrifices a land): the entry's ``actor`` is the putter, who also is the one whose lands are counted; the choice is stored as "<n>:<putter>"."""

from __future__ import annotations

from typing import Any

STATIC = "land_equilibrium110c"
KEY = "equilibrium110c"
TEXT = ("If an opponent who controls at least as many lands as you do would put a land onto the battlefield, that player instead puts that land onto the "
        "battlefield then sacrifices a land of their choice.")


def definition(text: str) -> dict[str, Any] | None:
    return {"kind": "static", "static": STATIC, "effects": []} if text.strip() == TEXT else None


def _lands(plan: Any, pid: str) -> int:
    return sum(1 for c in plan.state.zones.get(f"{pid}:battlefield", []) if plan.in_game(plan.state.cards[c]) and plan.ch(plan.state.cards[c]).is_land)


def plan_entry(plan: Any, putter: str, card: Any, controller: str, out: dict[str, Any]) -> None:
    from app.rules import scripts

    if card.is_token or not plan.ch(card).is_land:
        return
    n = 0
    for src in list(plan.state.cards.values()):
        if (src.zone.endswith(":battlefield") and src.controller != putter and src.controller in plan.live() and plan.in_game(src) and not plan.manual(src)
                and any(d.get("static") == STATIC for d in scripts.definitions(plan.ch(src)).values())
                and _lands(plan, putter) >= _lands(plan, src.controller)):
            n += 1
    if n:
        out.setdefault("choices", {})[KEY] = f"{n}:{putter}"


def sacrifice(plan: Any, card_id: str, choice: str) -> None:
    """Right after the land entered: the player who put it sacrifices a land of their choice, ``n`` times."""
    from app.rules import effects

    count, controller = choice.split(":")
    n = int(count)
    card = plan.state.cards.get(card_id)
    if card is None or n <= 0:
        return
    effects.run_body(plan, {"controller": controller, "source_card": None, "source_object": None, "name": "Land Equilibrium",
                            "effects": [{"do": "sacrifice_choice", "who": "you", "sel": 'sel:{"types":["Land"]}', "n": 1}] * n, "next": 0,
                            "body_done": {"do": "noop"}})

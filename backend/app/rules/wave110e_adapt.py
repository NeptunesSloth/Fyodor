"""-- wave 110E -- Selective Adaptation: "Reveal the top seven cards of your library. Choose from among them a card with flying, a card with first strike, and so
on for double strike, deathtouch, haste, hexproof, indestructible, lifelink, menace, reach, trample, and vigilance. Put one of the chosen cards onto the
battlefield, the other chosen cards into your hand, and the rest into your graveyard."

608.2d: one choice per keyword, in the printed order, from the revealed cards not chosen yet (ruling 2020-04-17: a card with several of the keywords is chosen for
ONE of them, so it can't be chosen twice). Each choice is mandatory when a card qualifies. Then the player picks which chosen card enters; the others go to hand.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan

KEYWORDS = ("flying", "first strike", "double strike", "deathtouch", "haste", "hexproof", "indestructible", "lifelink", "menace", "reach", "trample", "vigilance")
TEXT = ("Reveal the top seven cards of your library. Choose from among them a card with flying, a card with first strike, and so on for double strike, deathtouch, "
        "haste, hexproof, indestructible, lifelink, menace, reach, trample, and vigilance. Put one of the chosen cards onto the battlefield, the other chosen cards "
        "into your hand, and the rest into your graveyard.")


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    if body.strip() != TEXT:
        return None
    picks = [{"do": "pick_looked", "n": 1, "sel": f'sel:{{"card":true,"with_keywords":["{k}"],"zones":[]}}', "to": "choose", "optional": False, "reveal": False}
             for k in KEYWORDS]  # (pick_looked takes each chosen card out of ctx["looked"]: it can't be chosen again)
    return [{"do": "look_top", "n": 7, "player": "you", "reveal": True}, {"do": "adapt_all110e"}, *picks, {"do": "adapt_split110e"},
            {"do": "pick_looked", "n": 1, "sel": None, "to": "battlefield", "optional": False, "reveal": False}, {"do": "rest_looked", "to": "hand"},
            {"do": "adapt_join110e"}, {"do": "rest_looked", "to": "graveyard"}], None, False


def start(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    ctx["all110e"] = list(ctx.get("looked") or [])
    return True


def split(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """The chosen cards (taken out of ``looked`` as they were chosen) become the cards looked at; the unchosen wait in ``rest110e``."""
    ctx["rest110e"] = list(ctx.get("looked") or [])
    ctx["looked"] = [c for c in ctx.pop("all110e", []) if c not in ctx["rest110e"]]
    return True


def join(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    ctx["looked"] = [c for c in ctx.pop("rest110e", []) if c in plan.state.zones.get(f"{ctx['controller']}:library", [])]
    return True


PRIMITIVES = {"adapt_all110e": start, "adapt_split110e": split, "adapt_join110e": join}

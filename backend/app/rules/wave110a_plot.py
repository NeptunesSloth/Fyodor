"""Wave 110A: Fblthp, Lost on the Range - "The top card of your library has plot. The plot cost is equal to its mana cost." and "You may plot nonland cards from the
top of your library."

702.170a: plot is a static ability that functions while the card is in the player's hand; 113.6 / 113.6k: a permanent's static can instead give the top card of
the library the ability, and a permission (the second line) lets it be used from there. Plotting is a special action (116.2k, 702.170b): the owner exiles the card
and pays the plot cost at sorcery timing, which ``casting.plot`` already checks (702.170d). The top card is the one the owner may look at any time (the card's
first line), so the grant and the action are for the owner alone; a card with an X, no mana cost, or two faces is not given plot (which mana cost is "its" is
not settled, as zone_grants)."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

GRANT = "The top card of your library has plot. The plot cost is equal to its mana cost."
PERMIT = "You may plot nonland cards from the top of your library."


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    text = scripts.self_text(ability.text, ch.name)
    if text == GRANT:
        return {"kind": "static", "static": "plot_top110a", "effects": []}
    if text == PERMIT:
        return {"kind": "static", "static": "plot_top_permit110a", "effects": []}
    return None


def _source(state: Any, card: Any, info: Any) -> bool:
    """Is ``card`` the top card of its owner's library while a permanent they control gives it plot and lets them plot it?"""
    from app.rules import permissions

    if state.zones.get(f"{card.owner}:library", [])[:1] != [card.id]:
        return False
    found = permissions._table_statics(state, info, {"plot_top110a", "plot_top_permit110a"})
    return {d["static"] for s, _, d in found if s.controller == card.owner} == {"plot_top110a", "plot_top_permit110a"}


def apply(state: Any, card: Any, ch: Any, info: Any) -> Any:
    """The top card of the library has plot {its mana cost} (a numbered, granted ability, as ``dynamic_zone_keyword_costs56``)."""
    from app.rules.oracle import parse_abilities

    cost = ch.mana_cost or ""
    if "Land" in ch.types or not cost or "{X}" in cost or ch.doors is not None or any("plot" in a.keywords for a in ch.abilities) or not _source(state, card, info):
        return ch
    ability = parse_abilities(f"Plot {cost}")[0]
    return replace(ch, abilities=(*ch.abilities, replace(ability, index=max(100, max((a.index for a in ch.abilities), default=99) + 1))))

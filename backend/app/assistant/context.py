"""Builds the assistant's context from a player's sanitized view."""

from __future__ import annotations

from typing import Any, Protocol

MAX_CARDS = 120


class CardLookup(Protocol):
    def get_many(self, card_ids: list[str]) -> dict[str, dict[str, Any]]: ...


def build_context(view: dict[str, Any], cards: CardLookup) -> dict[str, Any]:
    """Summarize what the asking player can see: battlefield, stack, their hand, phase.

    ``view`` must come from ``build_view`` for that player, so hidden cards are already
    reduced to placeholders and cannot leak into the prompt.
    """
    viewer = view["viewer"]
    names = {p["id"]: p["name"] for p in view["players"]}
    visible = {cid: c for cid, c in view["cards"].items() if not c.get("hidden")}
    oracle = cards.get_many(sorted({c["card_id"] for c in visible.values() if c.get("card_id")})[:MAX_CARDS])

    def describe(cid: str) -> dict[str, Any] | None:
        c = visible.get(cid)
        if c is None:
            return None
        data = oracle.get(c.get("card_id") or "", {})
        entry = {
            "name": c.get("name"),
            "controller": names.get(c.get("controller"), c.get("controller")),
            "type_line": data.get("type_line") or (c.get("token") or {}).get("type_line"),
            "oracle_text": data.get("oracle_text") or (c.get("token") or {}).get("text"),
        }
        for key in ("tapped", "counters", "attacking", "blocking", "face_down"):
            if c.get(key):
                entry[key] = c[key]
        if c.get("ability"):
            entry["ability"] = c["ability"]["text"]
        return entry

    battlefield = [
        d for key, ids in view["zones"].items() if key.endswith(":battlefield") and isinstance(ids, list) for cid in ids
        if (d := describe(cid))
    ]
    stack = [d for cid in view["zones"].get("stack", []) if (d := describe(cid))]
    hand = [d for cid in view["zones"].get(f"{viewer}:hand", []) if (d := describe(cid))] if viewer in names else []
    return {
        "you": names.get(viewer),
        "turn": view["turn"],
        "active_player": names.get(view["turn"]["active_player"]),
        "life": {p["name"]: p["life"] for p in view["players"]},
        "battlefield": battlefield[:MAX_CARDS],
        "stack_top_last": stack,
        "your_hand": hand,
    }

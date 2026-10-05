"""-- chosen player (wave 4J) -- the player a permanent's "As ~ enters, choose an opponent / a player" chose
(614.12a: the choice is made as it enters and belongs to that object; 400.7: a new object has no such choice).
Researched against CR 2026-09-25.

The choice is recorded twice: the permanent's public ``choices`` entry ("Chosen opponent: Bob", the display, which a
player may also edit by hand) and ``RulesState.chosen_players`` (object id -> player id, what the rules read). A
reading is trusted only while both agree; a save from before the id was kept has only the display name, resolved when
exactly one player has that name. Anything else reads as no chosen player (the ability does nothing automatically).

Read by: step triggers "At the beginning of the chosen player's upkeep" (Black Vise, The Rack; triggers._whose_step),
and the effect subject "the chosen player" (``who: "chosen_player"``, effects._players).
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.game.state import CardInstance
    from app.rules.characteristics import Characteristics
    from app.rules.plan import Plan

LABELS = ("Chosen opponent", "Chosen player")  # effects.CHOICE_LABELS for "opponent" / "player"
WHO = "chosen_player"


def chooses_player(ch: Characteristics) -> bool:
    """Whether the object has exactly one "As ~ enters, choose an opponent / a player." (what "the chosen player" in
    its other abilities names)."""
    from app.rules.language import ENTERS_CHOICE
    from app.rules.scripts import self_text

    found = [m for ab in ch.abilities if (m := ENTERS_CHOICE.match(self_text(ab.text, ch.name))) is not None]
    return len(found) == 1 and found[0]["what"] in ("opponent", "player")


# -- chosen type (wave 4J) ------------------------------------------------------------------------------------------
# "of the chosen type / color" (selectors.CHOSEN_EXTRAS) names one of two choices:
# * the source permanent's "As ~ enters, choose a creature type / a color." (614.12a) — read by selectors.matches from
#   the source's record. Only where the source is the permanent itself: its statics' affected objects (layers), its
#   trigger conditions, its targets and its resolving instructions; never inside a counted value (a static's count
#   is evaluated for another object) and never on a card without that one enters choice.
# * a "Choose a creature type." instruction earlier in the same resolution (Kindred Dominance, Bloodline Bidding) —
#   bind_effects puts the answer into the instructions after it as the choice is made (effects.resume_choose_value).
_SOURCE_KEYS = frozenset({"who", "sel", "spell", "obj", "what"})


def _uses(node: Any, key: str = "") -> list[tuple[str, str]]:
    """(the JSON key, "creature type" / "color") for every selector in the definition that reads a chosen value."""
    from app.rules import selectors

    if isinstance(node, dict):
        return [u for k, v in node.items() for u in _uses(v, k)]
    if isinstance(node, list):
        return [u for v in node for u in _uses(v, key)]
    if isinstance(node, str) and node.startswith(selectors.PREFIX) and "chosen_" in node:
        sel = selectors.from_key(node)
        what = selectors.chosen_what(sel)
        return [(key, what or "?")] if any(e in selectors.CHOSEN_EXTRAS for e in sel.extras) else []
    return []


def _enters_choices(ch: Characteristics) -> list[str]:
    from app.rules import (
        card_names,  # -- card names (wave 22B) -- "As ~ enters, choose a card name." counts as a card name choice
    )
    from app.rules.language import ENTERS_CHOICE
    from app.rules.scripts import self_text

    texts = [self_text(ab.text, ch.name) for ab in ch.abilities]
    named = [e["what"] for t in texts if (d := card_names.enters_choice(t)) is not None for e in d["effects"] if card_names.is_choice(e["what"])]
    return [m["what"] for t in texts if (m := ENTERS_CHOICE.match(t)) is not None] + ["card name" for _ in named]


def _kind(what: str | None) -> str | None:
    from app.rules import (
        card_names,  # -- card names (wave 22B) -- every "… card name" choice is the one "card name" value
    )

    return "card name" if card_names.is_choice(what) else what


def chosen_value_ok(d: dict[str, Any], ch: Characteristics) -> bool:
    """Whether every "of the chosen type / color" in this definition names a choice the engine knows (see above)."""
    if d.get("chosen_type") and _enters_choices(ch).count("creature type") != 1:
        return False  # (wave 11E: "~ is the chosen type in addition to its other types" needs that one choice)

    dumped = json.dumps(d)
    if "Protection from the chosen color" in dumped:  # -- chosen type (wave 20E) -- only in the instructions after a "Choose a color." of this resolution
        effects = d.get("effects") or []
        picks = [i for i, e in enumerate(effects) if e.get("do") == "choose_value" and e.get("what") == "color" and not e.get("remember")]
        if len(picks) != 1 or any("Protection from the chosen color" in json.dumps(e) for e in effects[: picks[0]]) \
                or "Protection from the chosen color" in json.dumps({k: v for k, v in d.items() if k != "effects"}):
            return False
    if ('"hand": "chosen"' in dumped or '\\"controller\\":\\"chosen\\"' in dumped or '\\"zone_owner\\":\\"chosen\\"' in dumped) \
            and not chooses_player(ch):
        return False  # (wave 16F: "the chosen player" needs the one "As ~ enters, choose an opponent / a player.")
    if '"chosen_color": true' in dumped:  # -- prevention riders (wave 17A) -- "sources of the chosen color": this permanent's own choice
        return d.get("kind") != "spell" and _enters_choices(ch).count("color") == 1
    uses = _uses(d)
    if not uses:
        return True
    effects = d.get("effects") or []
    for what in {w for _, w in uses}:
        if what == "?":
            return False
        inside = [i for i, e in enumerate(effects) if e.get("do") == "choose_value" and _kind(e.get("what")) == what
                  and not e.get("remember")]
        if inside:  # a choice made as it resolves: only in the instructions after it
            if len(inside) != 1 or what in _enters_choices(ch):
                return False
            rest = {k: v for k, v in d.items() if k != "effects"}
            if any(w == what for _, w in _uses(rest)) or any(w == what for _, w in _uses(effects[:inside[0]])):
                return False
            continue
        if d.get("kind") == "spell" or _enters_choices(ch).count(what) != 1:
            return False
        if any(w == what and k not in _SOURCE_KEYS and not (k == "filter" and d.get("static") == "cast_limit") for k, w in uses):  # (wave 22B)
            return False
    return True


def bind_effects(effects: list[dict[str, Any]], what: str, value: str) -> list[dict[str, Any]]:
    """The instructions with "of the chosen <what>" replaced by the answer just given (``value``)."""
    from app.rules import selectors

    def walk(node: Any) -> Any:
        if isinstance(node, dict):
            return {k: walk(v) for k, v in node.items()}
        if isinstance(node, list):
            return [walk(v) for v in node]
        if isinstance(node, str) and node.startswith(selectors.PREFIX) and "chosen_" in node:
            sel = selectors.from_key(node)
            if selectors.chosen_what(sel) == what and (bound := selectors.bind_chosen(sel, value)) is not None:
                return bound.key()
        if node == "Protection from the chosen color" and what == "color":  # (wave 20E: protection_grants.CHOSEN_LINE)
            return f"Protection from {value.lower()}"
        return node

    return [walk(e) for e in effects]
# -- end chosen type (wave 4J) --------------------------------------------------------------------------------------


def record(plan: Plan, card_id: str, player: str) -> None:
    """Remember the player this object chose (its object id now)."""
    r = plan.rules
    on_field = {plan.oid(c) for c in plan.state.cards.values() if c.zone.endswith(":battlefield")}
    r.chosen_players = {oid: p for oid, p in r.chosen_players.items() if oid in on_field or oid in r.lki}  # (400.7)
    r.chosen_players[plan.oid(card_id)] = player


def _shown(card: CardInstance) -> str | None:
    found = [card.choices[k] for k in LABELS if card.choices.get(k)]
    return found[0] if len(found) == 1 else None


def player_of(plan: Plan, card_id: str, object_id: str | None = None) -> str | None:
    """The player the object chose, or None. ``object_id``: the object asked about (default: what the card is now);
    once it has left the battlefield, its recorded choice as it last existed (608.2h)."""
    card = plan.state.cards.get(card_id)
    oid = object_id or (plan.oid(card_id) if card is not None else "")
    pid = plan.rules.chosen_players.get(oid)
    current = card is not None and plan.oid(card) == oid and card.zone.endswith(":battlefield")
    if not current:
        return pid if pid in plan.state.players else None
    assert card is not None
    shown = _shown(card)
    if shown is None:
        return None
    if pid is not None:
        return pid if pid in plan.state.players and plan.state.players[pid].name == shown else None
    named = [p for p, player in plan.state.players.items() if player.name == shown]  # (an older save: a name only)
    return named[0] if len(named) == 1 else None

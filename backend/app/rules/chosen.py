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

from typing import TYPE_CHECKING

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

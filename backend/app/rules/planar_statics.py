"""-- planechase statics (wave A) -- the face-up plane's or phenomenon's static abilities and collector-only triggers (CR 311.4, 312.4,
113.6p, 901.7: its abilities function face up in the command zone; "you" is the planar controller, 311.5). app/rules/planar.py holds the
object, its own triggers and the coverage allowlists (``STATIC_KINDS`` / ``TRIGGER_KINDS``); this module is how the engine's other
collectors (battlefield-only ones: replacement effects, combat limits, hand size, mana riders, prevention, untap skips, enters-tapped,
spend-as and zone grants, top-card reveals) read the face-up card too.

``functions``: the gates every collector applies to the planar object (mirroring ``permissions._all_table_statics``): face up in the
command zone, its controller still in the game, the card not set to manual. ``face``: that object for a table, if any. ``read``: only
the kinds coverage claims for a plane (``planar.ability_ok``).

``definition`` (a ``hooks.DEFINE`` entry; planes and phenomena only): a plane's static in an exact wording the grammar reads in another
wording with the same rules meaning:

* Akoum: "Players may cast enchantment spells as though they had flash." — "Any player may …" (cast_limits: ``any_player``; 601.3b);
* Onakke Catacomb: "All creatures are black and have deathtouch." — one static (611.3a) of "All creatures are black." (613.1e, layer 5)
  and "All creatures have deathtouch." (613.1f, layer 6), the same affected set (613.6: both as of one timestamp);
* The Moonbase: "Low Gravity — All creatures have "{2}: …"": a flavor word (207.2c) before a static the grammar reads.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.game.state import CardInstance, GameState
    from app.rules.characteristics import Characteristics
    from app.rules.oracle import AbilityText


def functions(state: GameState, card: CardInstance) -> bool:
    """Is this the face-up planar object, and do its abilities work now (the module docstring)?"""
    if not card.id.startswith("planar-"):  # (cheap: called for every card a collector walks)
        return False
    from app.rules import planar
    from app.rules.plan import live_players

    r = state.rules
    return (r is not None and planar.face_card(card) and not card.face_down and card.controller in live_players(state)
            and r.card_mode(card.id) != "manual")


def read(d: dict[str, Any]) -> bool:
    """Is this ability one coverage claims for a plane (``planar.ability_ok``)? A collector reads only those on the planar object."""
    from app.rules import planar

    return planar.ability_ok(d)


def face(state: GameState) -> CardInstance | None:
    """The face-up plane or phenomenon's rules object whose abilities work now, else None."""
    pc = state.planechase
    card = state.cards.get(pc.face_id or "") if pc is not None else None
    return card if card is not None and functions(state, card) else None


# -- exact wordings (the module docstring) ---------------------------------------------------------------------------------------------
REWRITES = {
    "Players may cast enchantment spells as though they had flash.": "Any player may cast enchantment spells as though they had flash.",  # Akoum
}
FLAVOR_WORDS = frozenset({"Low Gravity"})  # The Moonbase's static (its chaos ability: wave B)
MERGES = {  # one static, read as these sentences' definitions together (the same "who")
    "All creatures are black and have deathtouch.": ("All creatures are black.", "All creatures have deathtouch."),  # Onakke Catacomb
}


def definition(ability: AbilityText, ch: Characteristics) -> dict[str, Any] | None:
    from app.rules import planar, scripts

    if not planar.planar(ch):
        return None
    text = ability.text.strip()
    word, dash, rest = text.partition(" — ")
    if dash and word in FLAVOR_WORDS:  # 207.2c: a flavor word has no rules meaning
        return scripts.define(replace(ability, text=rest), ch)
    if (native := REWRITES.get(text)) is not None:
        return scripts.define(replace(ability, text=native), ch)
    if (parts := MERGES.get(text)) is not None:
        colors, keywords = (scripts.define(replace(ability, text=t), ch) for t in parts)
        if colors is None or keywords is None or colors.get("static") != "grant" or keywords.get("static") != "grant" \
                or colors["who"] != keywords["who"] or not colors.get("set_colors") or not keywords.get("keywords") or colors.get("keywords"):
            return None
        return {**colors, "keywords": list(keywords["keywords"])}
    return None

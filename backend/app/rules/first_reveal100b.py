"""-- if you do (wave 100B) -- "Reveal the first card you draw each turn. Whenever you reveal a basic land card this way, draw a card." (Rowen,
Primitive Etchings), "Reveal the first card you draw on each of your turns. Whenever you reveal a land card this way, draw a card. Whenever you
reveal a nonland card this way, Keranos deals 3 damage to any target." (Keranos, God of Storms).

CR 2026-09-25 and the Wizards rulings: the first sentence is a static ability — the card is revealed (701.20a) as it is drawn, during the
draw (121.2: each card of a multi-card draw is drawn one at a time, so only the first card drawn that turn is revealed); the second is a
triggered ability that waits until the whole draw is done (603.3: put on the stack the next time a player would receive priority) — Rowen
2004-10-04. A card drawn before the permanent was on the battlefield was the turn's first: no later card is (Primitive Etchings 2004-10-04:
two of them reveal the one card once, and each triggers). The card's kind is read as it is revealed (in the hand); the trigger resolves even if
the card has left the hand since. Draws a replacement effect replaced weren't draws (614.6, 121.6): only the cards actually drawn count.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.characteristics import AbilityText, Characteristics
    from app.rules.plan import Plan

RULE = "first_draw_reveal100b"
_LINE = re.compile(r"^Reveal the first card you draw (?P<when>each turn|on each of your turns)\.(?P<rest>(?: Whenever you reveal an? [a-z ]+? card this way, "
                   r"[^.]+\.)+)$")
_EACH = re.compile(r" Whenever you reveal an? (?P<what>[a-z ]+? card) this way, (?P<body>[^.]+\.)")


def definition(ability: AbilityText, ch: Characteristics) -> dict[str, Any] | None:
    from app.rules import scripts, selectors

    m = _LINE.fullmatch(scripts.self_text(ability.text, ch.name))
    if m is None or ability.kind != "static":
        return None
    reveals = []
    for each in _EACH.finditer(m["rest"]):
        sel, found = selectors.parse(each["what"]), scripts.parse_effects(each["body"][0].upper() + each["body"][1:], None)
        if sel is None or not sel.card or found is None or not found[0] or found[2] or '"event' in str(found[0]) or '"it"' in str(found[0]):
            return None
        reveals.append({"sel": sel.key(), "effects": found[0], **scripts.target_fields(found[1])})
    return {"kind": "static", "static": RULE, "yours": m["when"] != "each turn", "reveals": reveals, "effects": []}


def on_draw(plan: Plan, player: str, drawn: list[str]) -> None:
    """The cards ``player`` just drew in one draw (replace.do_draws): the turn's first one is revealed once, and each ability triggers."""
    from app.game.rules_state import turn_log_now
    from app.game.state import zone_key
    from app.rules import scripts, selectors
    from app.rules.triggers import _add

    log = turn_log_now(plan.state)
    card = plan.state.cards.get(drawn[0]) if drawn else None
    if log is None or card is None or log.drew.get(player, 0) != len(drawn) or card.zone != zone_key(player, "hand"):
        return
    found = [(src, i, d) for cid in plan.state.zones.get(zone_key(player, "battlefield"), []) if (src := plan.state.cards[cid]).controller == player
             and plan.in_game(src) for i, d in scripts.definitions(plan.ch(src)).items()
             if d.get("kind") == "static" and d.get("static") == RULE and (not d["yours"] or plan.active == player)]
    if not found:
        return
    plan.do({"type": "reveal", "card_ids": [card.id]}, actor=player)
    plan.note(f"{plan.name(player)} reveals {card.name}, the first card drawn this turn", [card.id], actor=player)
    ch = plan.ch(card)
    for src, i, d in found:
        for each in d["reveals"]:
            if selectors.matches(plan, selectors.from_key(each["sel"]), card, ch, player, src.id):
                _add(plan, controller=player, source_card=src.id, source_object=plan.oid(src), name=src.name, index=i,
                     definition={"kind": "triggered", "trigger": RULE, "optional": False, "effects": each["effects"],
                                 **{k: each[k] for k in ("target", "targets") if k in each}})

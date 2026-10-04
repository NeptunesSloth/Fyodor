"""-- casting extras (wave 18E) -- splice (CR 702.47), researched against the stored Comprehensive Rules (2026-09-25).

* 702.47a — "Splice onto [quality] [cost]": as you cast a spell of that quality you may reveal this card from your hand; the spell
  gains this card's rules text and you pay [cost] as an additional cost (601.2b, 601.2f-h). The card stays in your hand; the
  reveal is public (701.20a, ``reveal``).
* 702.47b — a card can't be spliced if its text's choices can't be made, and not twice onto one spell; several are revealed at once and
  their effects follow the main spell's, in the order the caster lists them (``CastSpell.splice``).
* 702.47c — the spell keeps its own characteristics (name, colors, types …); text that names the spliced card names the spell
  instead. :func:`overlay` is the main spell's characteristics with the spliced lines appended (names rewritten), read whole by
  ``scripts.spell_definition`` so the targets come out in printed order (601.2c, 702.47d).
* 702.47e — the changes end when the spell leaves the stack: the stack entry carries the combined effects only.

Refused (manual): a modal main spell, a spliced card that isn't a plain one-definition spell, and a splice cost the engine can't pay
(here "An opponent gains 5 life", Roar of Jukai, isn't a cost: 118.1).
"""

from __future__ import annotations

import re
from dataclasses import replace
from typing import TYPE_CHECKING

from app.game.errors import ActionError
from app.rules import alt_costs

if TYPE_CHECKING:
    from app.game.state import CardInstance
    from app.rules.characteristics import Characteristics
    from app.rules.plan import Plan

_LINE = re.compile(r"^splice onto (?P<q>arcane|instant or sorcery)(?: (?P<mana>(?:\{[^}X]+\})+)|—(?P<rest>[^{}]+))$", re.IGNORECASE)


def parse(ch: Characteristics) -> tuple[str, alt_costs.AltCost] | None:
    """The card's one splice line: (the quality it splices onto, the cost), or None when it has none we can read."""
    found = [a for a in ch.abilities if a.kind == "keywords" and "splice" in a.keywords]
    if len(found) != 1:
        return None
    m = _LINE.fullmatch(re.sub(r"\s*\(.*?\)", "", found[0].text).strip().rstrip("."))
    if m is None:
        return None
    cost = alt_costs.parse_cost(f"pay {m['mana']}" if m["mana"] else m["rest"][:1].lower() + m["rest"][1:])
    return (m["q"].lower(), cost) if cost is not None else None


def spliceable(ch: Characteristics) -> bool:
    """Whether the card's own text is something the engine can add to another spell: a plain one-definition spell (no modes)."""
    from app.rules import coverage, scripts

    whole = scripts.spell_definition(ch)
    return (parse(ch) is not None and ch.is_instant_or_sorcery and all("splice" in a.keywords for a in ch.abilities if a.kind == "keywords")
            and whole is not None and not whole.get("modes") and coverage.definition_supported(whole))


def overlay(main: Characteristics, spliced: list[Characteristics]) -> Characteristics:
    """The main spell with each spliced card's text after its own (702.47b-c): its name is the spell's."""
    abilities = list(main.abilities)
    for other in spliced:
        for ab in (a for a in other.abilities if a.kind != "keywords"):
            abilities.append(replace(ab, index=len(abilities), text=ab.text.replace(other.name, main.name or "~")))
    return replace(main, abilities=tuple(abilities))


def prepare(plan: Plan, ids: list[str], card: CardInstance, ch: Characteristics) -> tuple[Characteristics, list[alt_costs.AltCost]]:
    """Validate the cards the caster splices (702.47a-b) → (the spell's characteristics with their text, their costs). An ActionError names what's wrong; nothing is moved or paid here."""
    if len(set(ids)) != len(ids) or card.id in ids:
        raise ActionError("You can't splice one card onto the same spell more than once (702.47b)")
    from app.rules import scripts

    main_defn = scripts.spell_definition(ch)
    if main_defn is None or main_defn.get("modes"):
        raise ActionError(f"{ch.name or 'That spell'} can't have a card spliced onto it by the engine")
    others, costs = [], []
    for cid in ids:
        other = plan.state.cards.get(cid)
        if other is None or other.zone != f"{plan.actor}:hand" or plan.manual(other):
            raise ActionError("A spliced card must be in your hand")
        och = plan.ch(other)
        found = parse(och)
        quality = found[0] if found else None
        if found is None or not spliceable(och) or not (("Arcane" in ch.subtypes) if quality == "arcane" else ch.is_instant_or_sorcery):
            raise ActionError(f"{och.name} can't be spliced onto {ch.name or 'that spell'}")
        others.append(och)
        costs.append(found[1])
    return overlay(ch, others), costs

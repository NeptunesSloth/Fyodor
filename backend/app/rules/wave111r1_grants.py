"""-- granted abilities (wave 111R1) -- layer-6 ability-adding effects of resolved spells and abilities whose quoted abilities are
static or are activated from outside the battlefield (CR 113.10, 611.2, 613.1f), researched against CR 2026-09-25.

* **Quoted static abilities.** 'If Nog is a Scout, he becomes a Ferengi Officer and gains "You may play lands from your graveyard" and "You
  may play an additional land on each of your turns."' (Nog, Ambitious Cadet). The grant is the ordinary layer-6 effect of the ``become``
  (613.1f; one timestamp, 613.7b), its object fixed as it begins (611.2c), for the rest of the game (611.2a) — so for as long as that
  object stays on the battlefield (400.7). app/rules/granted.py ``layer6`` adds the quote to the object's abilities; a static ability the
  engine reads from its source's *current* abilities (``layers.derive`` → ``scripts.definitions``) then works as a printed one does
  (611.3a, applied whenever it is read). ``current_static`` names those: a permission to play or cast cards from a zone
  (permissions._table_statics, 305.1 / 601.3; not "this card", which a card's own zone reads, nor a linked one, 607.2a) and additional
  land plays (land_plays.allowed, 305.2). Every other static stays refused by granted.quote (layers.py reads the rest from printed text).
* **Abilities granted to a card in exile.** 'When Q enters, shuffle your library, then exile cards from the top of your library until you
  exile a nonland card. That nonland card gains "Exile a card from your hand: Create a copy of this card. You may cast the copy. Activate
  only during your turn and only if this card is exiled."' (Q, Stacking the Deck). "That nonland card" is the card the exile stopped at,
  which the effect can find in exile (400.7j). The grant's object is fixed as it begins (611.2c) and it has no duration (611.2a): it lasts
  as long as that object is in exile — a card that leaves is a new object without it (400.7); Q leaving changes nothing. It is the
  exact-object layer-6 effect app/rules/layers.py applies in exile (``ability_zone``); app/rules/view.py shows it with the card, and
  casting.activatable lists it. Read only for a quoted activated ability that states it works in exile (``EXILED_ONLY``).
  - Activation: an ability that states which zone it functions in functions only there (113.6b: "only if this card is exiled"). A card in
    exile has no controller, so its owner activates it (602.2; 108.4a): casting.ability_cost marks it exile-only, restrictions read
    "if this card is exiled" as the same object being in its owner's exile (400.7), and "during your turn" is any time in that turn.
  - "Create a copy of this card. You may cast the copy." (707.12): the copy is created in the zone the card is in and its owner may cast it
    while the ability resolves (608.2g), paying its costs (no "without paying"; card_copy_sources.copy_cast); a copy not cast ceases to
    exist (704.5e). The copy has the card's copiable values only (707.2), not the granted ability. If the card has left that zone by
    the time the ability resolves, the ability uses its last known information (113.7a); the engine hands that rare case to the players
    (manual resolution) rather than guess the copy.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from app.game.rules_state import DecisionOption

if TYPE_CHECKING:
    from app.rules.oracle import AbilityText
    from app.rules.plan import Plan

Context = dict[str, Any]


# -- quoted static abilities ------------------------------------------------------------------------------------------------------------
def current_static(d: dict[str, Any]) -> bool:
    """Is this static ability one the engine reads from its source's current abilities (so a resolved effect may grant it)?"""
    from app.rules.land_plays import EXTRA_LANDS

    if d.get("kind") != "static":
        return False
    if d.get("static") == EXTRA_LANDS:  # land_plays.allowed: derive → scripts.definitions of each permanent (305.2)
        return True
    # permissions._table_statics: derive → scripts.definitions of each permanent; "you" is the source's controller (305.1, 601.3)
    return d.get("static") == "permission" and not d.get("self") and not d.get("linked") and not d.get("look")


# -- "That <card> gains "…"" after "… until you exile a <card>" ------------------------------------------------------------------------
_FOUND_GAINS = re.compile(r'^(?P<pre>.+? until you exile an? (?P<np>[a-z][a-z -]*?card))\. That (?P=np) gains (?P<q>"[^"]+"(?: and "[^"]+")*)\.?$')
_QUOTES = re.compile(r'"([^"]+)"')
# An activated ability that states it functions in exile (113.6b): casting.ability_cost makes it exile-only
EXILED_ONLY = re.compile(r"^[^\"]*?: [^\"]*\bActivate only (?:[^.]*? and only )?if this card is exiled\.$")
# "Create a copy of this card. You may cast the copy." (707.12): the card the ability is on
_COPY_SELF = "create a copy of this card. you may cast the copy."
# The quoted ability Q grants: defined as granted.quote checked it, without the name of the card that has it (a card named "Exile" or "Copy"
# can't turn a word of the ability into a reference to itself)
Q_ABILITY = ("Exile a card from your hand: Create a copy of this card. You may cast the copy. Activate only during your turn and only if this "
             "card is exiled.")


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    from app.rules import card_copy_sources, granted, scripts

    text = body.strip()
    if text.lower() == _COPY_SELF:
        copy, cast = card_copy_sources.copy_cast(paid=True)
        copy = {k: v for k, v in copy.items() if k != "source_zone"}  # (the zone the card is in: exile or a graveyard)
        return [{"do": "source_card_111r1", "as": card_copy_sources.ORIGINAL}, copy, cast], None, False
    m = _FOUND_GAINS.fullmatch(text)
    if m is None:
        return None
    before = scripts.parse_effects(m["pre"] + ".")
    if before is None or not before[0]:
        return None
    effects, target, optional = before
    last = effects[-1]
    if last.get("do") != "exile_top" or not last.get("until") or last.get("player") != "you" or last.get("face_down"):
        return None  # (only one library's card is "found", effects.exile_top)
    checked = [granted.quote(q) for q in _QUOTES.findall(m["q"])]
    if not checked or any(c is None or not EXILED_ONLY.search(c) for c in checked):
        return None  # (only an activated ability that works in exile, 113.6b: the engine runs no other ability of a card there)
    return [*effects, {"do": "grant_found_111r1", "abilities": checked}], target, optional


def definition(ability: AbilityText, ch: Any) -> dict[str, Any] | None:
    """Q's granted ability on the card that has it, read as granted.quote read it (the holder's name plays no part in it)."""
    if ability.text.strip() != Q_ABILITY or ch.name == "\u0000":
        return None
    from app.rules import scripts
    from app.rules.characteristics import Characteristics

    return scripts.define(ability, Characteristics(name="\u0000", abilities=(ability,)))


def holder_name(ability: AbilityText, ch: Any) -> str:
    """The name casting.ability_cost reads the ability's cost with: none for Q's granted ability (see ``definition``)."""
    return "" if ability.text.strip() == Q_ABILITY else str(ch.name)


# -- primitives -------------------------------------------------------------------------------------------------------------------------
def grant_found(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """The card a "… until you exile a …" stopped at (ctx["found"], effects.exile_top), found in exile (400.7j), gains the quoted abilities:
    that object (611.2c), for as long as it stays there (400.7). One a replacement effect put elsewhere gains nothing that works there (113.6b)."""
    from app.rules import layers

    card = plan.state.cards.get(str(ctx.get("found") or ""))
    if card is None or card.face_down or card.is_token or not card.zone.endswith(":exile"):
        return True
    abilities = list(e.get("abilities") or [])
    quoted = " and ".join(f'"{a}"' for a in abilities)
    layers.add_effect(plan, affected=[plan.oid(card)], layer="6", source=ctx.get("source_object"), controller=ctx["controller"],
                      duration="permanent", add_abilities=abilities, ability_zone="exile", label=f"{card.name} gains {quoted} while it stays exiled")
    plan.note(f"{card.name} gains {quoted}"[:300], [card.id], actor=ctx["controller"])
    return True


def source_card(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """"this card": the ability's source, still the object it was, in exile or a graveyard (400.7). One that has left: its last known
    information would be copied (113.7a) — made by hand."""
    from app.rules import effects
    from app.rules.plan import decide

    card = plan.state.cards.get(str(ctx.get("source_card") or ""))
    if card is not None and plan.oid(card) == ctx.get("source_object") and card.zone.endswith((":exile", ":graveyard")) and not card.face_down:
        effects._remember(plan, ctx, e, [card.id])
        return True
    effects._remember(plan, ctx, e, [])
    name = card.name if card is not None and not card.face_down else "the card"
    decide(plan, player=ctx["controller"], kind="manual_resolution", options=[DecisionOption(id="done", label="Done")],
           prompt=f"{name} left its zone before this resolved: create the copy from its last known information and cast it if you "
                  "wish by hand (113.7a, 707.12), then press Done"[:300],
           resume={"step": "manual_copy_111r1", "ctx": ctx})
    return False


def resume_manual(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import effects

    plan.note(f"{plan.name(d.player)} finished the copy by hand", actor=d.player)
    effects.continue_effects(plan, d.resume["ctx"])


PRIMITIVES = {"grant_found_111r1": grant_found, "source_card_111r1": source_card}
RESUME = {"manual_copy_111r1": resume_manual}

"""-- card names (wave 22B) -- "Choose a card name." / "As ~ enters, choose a card name." (Pithing Needle, Meddling Mage, Nevermore,
Phyrexian Revoker, Voidstone Gargoyle, Declaration of Naught …) and the selector "with the chosen name". Researched against CR 2026-09-25.

* 201.4: the player must choose the name of a card in the Oracle card reference (a token's name only if it is also a card's);
  201.4a: "a nonland card name", "a land card name", "an artifact card name": the card's Oracle characteristics must match;
  201.4b: a split card's name is one of its halves, not both (709.4a: "An object has the chosen name if one of its names is the chosen
  name"); 201.4c-f: a flip card's alternative name, the back face of a double-faced card (and of a meld pair) and an adventurer's
  alternative name may be chosen, judged by that face's own characteristics. Not read: interchangeable names (201.3, 201.4g: Un-cards)
  and meld pairs' combined names; the Oracle name list is the card database's, and a name two cards share ("Fire": Start // Fire and
  Fire // Ice) is judged by the card the database resolves it to.
* The name is typed (the Oracle list is 36,000 names): the decision carries one option, ``FREE_TEXT``, whose ``group`` says what may be named,
  and the answer arrives in ``Choose.name``; nothing about the player's hand or library is in it (hidden information never leaks).
* A permanent's choice is public and is recorded on it as its ``choices`` entry ("Chosen card name: Sol Ring", 614.12a); it is the choice of
  that object only (400.7: a new object has no choice). The selector "with the chosen name" reads the source permanent's record and compares
  with every name the object has (709.4a); a face-down object has no name (708.2a).
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from app.cards.names import normalize_name
from app.game.errors import ActionError
from app.game.rules_state import DecisionOption
from app.game.state import zone_key

if TYPE_CHECKING:
    from app.game.rules_state import Decision
    from app.game.state import CardInstance
    from app.rules.characteristics import Characteristics
    from app.rules.plan import Plan

LABEL = "Chosen card name"
FREE_TEXT = "__name__"  # the one option of a typed-name decision (its ``group`` is the ``what``)
_TYPES = ("nonland", "land", "artifact", "creature", "enchantment", "instant", "sorcery", "planeswalker")
# the phrase after "choose a/an": "card name", "nonland card name", "card name other than a basic land card name"
WHAT_RX = (r"(?:(?:" + "|".join(_TYPES) + r") card name|card name(?: other than a basic land card name)?)")
_WHAT = re.compile(rf"^{WHAT_RX}$")
ALL_WHATS = ("card name", "card name other than a basic land card name", *(f"{t} card name" for t in _TYPES))


def is_choice(what: str | None) -> bool:
    return bool(what) and _WHAT.match(what or "") is not None


def option(what: str) -> DecisionOption:
    return DecisionOption(id=FREE_TEXT, label="Type a card name", group=what)


def is_free_text(d: Decision) -> bool:
    return bool(d.options) and d.options[0].id == FREE_TEXT  # (further options only show what the chooser looked at)


def _allowed(what: str, type_line: str) -> bool:
    types = set(type_line.replace("—", " ").split())
    if what.endswith("other than a basic land card name"):
        return not {"Basic", "Land"} <= types
    kind = what.split(" ")[0]
    if kind == "nonland":
        return "Land" not in types
    if kind in _TYPES:
        return kind.capitalize() in types
    return True


def canonical(plan: Plan, what: str, typed: str | None) -> str:
    """The Oracle name the player typed (201.4), or an ActionError saying what is wrong."""
    text = (typed or "").strip()
    if not text:
        raise ActionError("Type the name of a card")
    resolve = getattr(plan.info, "resolve", None)
    card = resolve(text) if resolve is not None else None
    if card is None or card.get("layout") in ("token", "emblem"):
        raise ActionError("That isn't the name of a card in the Oracle card reference (201.4)")
    norm = normalize_name(text)
    faces = card.get("faces") or []
    if len(faces) > 1:
        match = next((f for f in faces if normalize_name(str(f.get("name") or "")) == norm), None)
        if match is None:
            raise ActionError("Name one face of that card (201.4b, 709.4a), not both")
        name, type_line = str(match["name"]), str(match.get("type_line") or "")
    else:
        if normalize_name(str(card.get("name") or "")) != norm:
            raise ActionError("That isn't the name of a card in the Oracle card reference (201.4)")
        name, type_line = str(card["name"]), str(card.get("type_line") or "")
    if not _allowed(what, type_line):
        raise ActionError(f"That name doesn't fit \"{what}\" (201.4a)")
    return name


def answer(plan: Plan, d: Decision, typed: str | None) -> str:
    return canonical(plan, d.options[0].group or "card name", typed)


def names_of(ch: Characteristics) -> list[str]:
    """Every name the object has (709.4a: a split card outside the stack has both); none while face down (708.2a)."""
    return [n.strip() for n in ch.name.split(" // ")] if ch.name and not ch.face_down else []


def chosen(plan: Plan, source: str | None) -> str | None:
    """The name the source permanent recorded as it entered (its public ``choices`` entry), or None."""
    card = plan.state.cards.get(source or "")
    value = card.choices.get(LABEL) if card is not None else None
    return value.strip() if value else None


def has_name(ch: Characteristics, name: str | None) -> bool:
    """709.4a: the object has the chosen name if one of its names is it."""
    return bool(name) and normalize_name(name or "") in {normalize_name(n) for n in names_of(ch)}


def matches(plan: Plan, source: str | None, ch: Characteristics) -> bool:
    return has_name(ch, chosen(plan, source))


LOOK = "opponent to look at"  # the first question of "look at an opponent's hand, then choose any card name" (public: which hand)


def enters_choice(text: str) -> dict[str, Any] | None:
    """"As ~ enters, choose a card name." (614.1c, 614.12a): the same entering replacement as the other "As ~ enters, choose …".
    "As ~ enters, look at an opponent's hand, then choose any card name." (Sorcerous Spyglass, Anointed Peacekeeper): which opponent is asked
    first (publicly), then the name, with that hand shown in the private decision (``prompt``)."""
    m = re.fullmatch(rf"As ~ enters, choose (?:a|an) (?P<what>{WHAT_RX})\.", text)
    if m is not None:
        return {"kind": "replacement", "replacement": "enters_choice",
                "effects": [{"do": "choose_value", "who": "you", "what": m["what"], "remember": True}]}
    if text == "As ~ enters, look at an opponent's hand, then choose any card name.":
        return {"kind": "replacement", "replacement": "enters_choice",
                "effects": [{"do": "choose_value", "who": "you", "what": LOOK},
                            {"do": "choose_value", "who": "you", "what": "card name", "remember": True, "look": True}]}
    return None


def sole_opponent(plan: Plan, player: str) -> str | None:
    """The one opponent left, if exactly one (no question is needed to pick whose hand)."""
    others = [p for p in plan.live() if p != player]
    return others[0] if len(others) == 1 else None


def prompt(plan: Plan, card: CardInstance, player: str, choice: dict[str, Any]) -> tuple[str, list[DecisionOption]] | None:
    """The question of the look-then-name entry (None: not one of its questions). Naming shows the chosen opponent's hand to the chooser alone,
    as options of the private decision (701.20e: only the one looking sees it; nothing is revealed, nothing is recorded in the log but the look)."""
    what = choice["what"]
    if what == LOOK:
        return (f"{card.name}: as it enters, choose an opponent whose hand you look at",
                [DecisionOption(id=p, label=plan.name(p)) for p in plan.live() if p != player])
    look = choice.get("look")
    if not is_choice(what) or not look or look not in plan.state.players:
        return None
    plan.note(f"{plan.name(player)} looks at {plan.name(look)}'s hand", actor=player)
    hand = [DecisionOption(id=f"seen:{cid}", label=plan.state.cards[cid].name or "a card", card_id=cid, group="seen")
            for cid in plan.state.zones.get(zone_key(look, "hand"), []) if cid in plan.state.cards]
    return f"{card.name}: as it enters, choose any card name (you look at {plan.name(look)}'s hand)", [option(what), *hand]

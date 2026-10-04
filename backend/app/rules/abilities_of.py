"""-- borrowed abilities (wave 18F) -- "has all activated abilities of …" (CR 113.10, 613.1f, 607.5).

"Necrotic Ooze has all activated abilities of all creature cards in all graveyards.", "Experiment Kraj has all activated abilities of each
other creature with a +1/+1 counter on it.", "Myr Welder has all activated abilities of all cards exiled with it.", "Sharkey has all
activated abilities of lands your opponents control except mana abilities.": a static (layer 6) gives the object a copy of each activated
ability of the objects its wording names, as they are now (611.3a: read again whenever characteristics are derived — an ability whose
object left is gone, a card that enters the graveyard brings its own).

* **The text.** An ability that names its object — "Sacrifice Foo", "this creature" — names the object that has it now (the reminder on
  Skill Borrower: "use this creature's name instead"): the lender's name and its "this creature" become "this permanent", read again on
  the borrower like any granted ability.
* **Numbering.** Each is numbered from its lender's object number (``BORROWED``), so it stays the same ability while the lender stays the
  object it is (400.7), and a lender that changes zones is a new object with new ones.
* **Linked abilities (607.5).** A lender's ability that refers to a choice or to cards exiled with it (its linked half may be elsewhere),
  or to a card by name (201.5b vs "a card named …"), is lent but never automated (``manual``): it would link to the wrong thing. A modal
  ability is lent with its modes (shown) and is manual too. Characteristics are read as the lender has them without other statics (a lender's own
  borrowed abilities, an Aura's grants: ``layers._depth``), so a lender's abilities from other statics aren't lent either.
* **Refused** (never guessed): sources the selector grammar doesn't read, "the top card of your library" (Skill Borrower: it isn't an
  object that stays), cards in exile with counters ("Mairsil": each once a turn), planeswalkers' loyalty abilities.
"""

from __future__ import annotations

import itertools
import re
from dataclasses import replace
from typing import TYPE_CHECKING, Any

from app.rules import selectors
from app.rules.oracle import AbilityText, parse_abilities

if TYPE_CHECKING:
    from app.game.state import CardInstance
    from app.rules.layers import Static
    from app.rules.plan import Plan

BORROWED = 2_000_000  # above every other number an ability of an object is known by (granted.py INDEX_BASE …); bound: ActivateAbility.ability
STRIDE = 32  # abilities of one lender

_SOURCE = re.compile(r"^all activated abilities of (?P<src>.+?)(?P<nomana> except mana abilities)?$")
_LINKED = re.compile(r"^(?:all |the )?(?P<what>(?:[\w\-]+ )*cards?) exiled with (?:it|this \w+|~)$")
_EXILED_CARD = re.compile(r"^the exiled card$")
# a lender's ability that refers to what another of its abilities did (607.2, 607.5), or names a card: lent, but manual (``manual``)
_LINKED_TEXT = re.compile(r"\bexiled with\b|\bthe exiled cards?\b|\bchosen\b|\bnoted\b|\bnamed\b", re.IGNORECASE)
# activated abilities that are keyword lines (113.1, 702): the ones that work from the battlefield
_ACTIVATED_KEYWORDS = frozenset({"equip", "crew", "outlast", "fortify", "reconfigure"})


def parse(rest: str) -> dict[str, Any] | None:
    """The predicate "all activated abilities of <objects>" → {"sel": selector key | None, "linked": bool, "no_mana": bool}."""
    m = _SOURCE.match(rest)
    if m is None:
        return None
    src = m["src"]
    out: dict[str, Any] = {"sel": None, "linked": False, "no_mana": bool(m["nomana"])}
    if _EXILED_CARD.match(src):
        out["linked"] = True
        return out
    linked = _LINKED.match(src)
    if linked is not None:  # 607.2a: the cards the borrower's (or its source's) exiling ability put into exile
        sel = selectors.parse(linked["what"])
        if sel is None or sel.player is not None or not sel.card or sel.extras:
            return None
        out.update(linked=True, sel=None if linked["what"] in ("cards", "card") else replace(sel, zones=("exile",)).key())
        return out
    zone = "graveyard" if src.endswith(" in all graveyards") else None
    phrase = re.sub(r"^(?:all|each) ", "", re.sub(r" in all graveyards$| on the battlefield$", "", src))
    sel = selectors.parse(phrase)
    if sel is None or sel.player is not None or sel.either or sel.ability or sel.attacking or sel.blocking:
        return None
    if zone is not None:
        if not sel.card or sel.zones not in ((), ("graveyard",)) or sel.zone_owner or sel.controller or sel.owner:
            return None
        sel = replace(sel, zones=("graveyard",))
    elif sel.card:  # ("Elf cards in your graveyard": the selector grammar's own zone)
        if sel.zones not in (("graveyard",), ("exile",)) or sel.extras:
            return None
    elif sel.zones != ("battlefield",):
        return None
    out["sel"] = sel.key()
    return out


def manual(ability: AbilityText) -> bool:
    """A borrowed ability that is lent but not automated (scripts.define): a linked one (607.5) or a modal one (its modes are shown)."""
    return ability.index >= BORROWED and (bool(_LINKED_TEXT.search(ability.text)) or "\n• " in ability.text)


def _lent(plan: Plan, lender: CardInstance, no_mana: bool) -> list[AbilityText]:
    from app.rules import scripts

    ch = plan.ch(lender)

    def own(text: str) -> str:
        text = scripts.self_text(text, ch.name)
        return re.sub(r"(^|: |\. )~", r"\1This permanent", text).replace("~", "this permanent")

    out: list[AbilityText] = []
    for i, ab in enumerate(ch.abilities):
        if ab.index >= BORROWED:
            continue
        keyword = ab.kind == "keywords" and len(ab.keywords) == 1 and ab.keywords[0] in _ACTIVATED_KEYWORDS
        if not (ab.kind == "activated" or (ab.kind == "mana" and not no_mana) or keyword):
            continue
        found = parse_abilities(ab.text if keyword else own(ab.text))
        if len(found) != 1 or found[0].kind != ab.kind:
            continue
        modes = [own(x.text) for x in itertools.takewhile(lambda x: x.text.startswith("• "), ch.abilities[i + 1:])]
        out.append(replace(found[0], text="\n".join([found[0].text, *modes])) if modes else found[0])  # (a modal one: manual)
    return out


def collect(plan: Plan, st: Static, borrower: CardInstance) -> list[AbilityText]:
    """The abilities the static ``st`` lends ``borrower`` right now, numbered (``BORROWED``)."""
    d = st.definition["abilities_of"]
    state, r = plan.state, plan.state.rules
    if r is None:
        return []
    sel = selectors.from_key(d["sel"]) if d["sel"] else None
    if d["linked"]:
        found = [state.cards[cid] for oid in r.exiled_with.get(r.object_id(st.source), []) if (cid := oid.rsplit(".", 1)[0]) in state.cards
                 and state.cards[cid].zone.endswith(":exile") and r.object_id(cid) == oid]
        lenders = [c for c in found if sel is None or selectors.matches(plan, sel, c, plan.ch(c), st.controller, st.source)]
    else:
        assert sel is not None
        lenders = [state.cards[c] for c in selectors.candidates(plan, sel, st.controller, st.source)]
    out: list[AbilityText] = []
    for lender in sorted(lenders, key=lambda c: r.objects.get(c.id, 0)):
        if lender.id == borrower.id or lender.face_down:  # (a face-down card's abilities are hidden information: never shown by lending)
            continue
        for k, ab in enumerate(_lent(plan, lender, d["no_mana"])[: STRIDE]):
            out.append(replace(ab, index=BORROWED + STRIDE * r.objects.get(lender.id, 0) + k))
    return out

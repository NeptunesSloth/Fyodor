"""-- attach abilities (wave 7E) -- "{B}{B}: Attach this Equipment to target creature you control." (Cranial Plating, Horned Helm),
"{T}: Attach target Equipment you control to target creature you control." (Brass Squire, Auriok Windwalker), "{0}: Attach target
Equipment you control to this creature." (Kazuul's Toll Collector).

701.3a: to attach an Aura, Equipment or Fortification to an object is to put it onto that object; 701.3b: if it can't be
attached there (``attachments.host_problem``: an Equipment that's a creature, protection, an Aura's enchant restriction) or
it is already attached to it, nothing moves; 701.3c: attaching gives it a new timestamp. This is not the equip keyword
(702.6): no sorcery-speed restriction and no equip cost. Each "target" is its own group (115.3); an illegal target (608.2b)
leaves nothing to attach.
"""

from __future__ import annotations

import re
from typing import Any

_SELF = r"(?:~|this (?:Equipment|equipment|permanent|Aura|aura))"
_ONE = re.compile(rf"^attach {_SELF} to (?P<tgt>target [^,.]+)$")
_PAIR = re.compile(r"^attach (?P<src>target [^,.]+?) to (?P<dst>target [^,.]+)$")
_TO_SELF = re.compile(rf"^attach (?P<src>target [^,.]+?) to {_SELF}$")
_TO_THIS_CREATURE = re.compile(r"^attach (?P<src>target [^,.]+?) to this creature$")


def _group(phrase: str, *, kinds: tuple[str, ...]) -> dict[str, Any] | None:
    from app.rules import selectors
    from app.rules.copying import _target_group

    g = _target_group(phrase)
    if g is None or (g["min"], g["max"]) != (1, 1) or "another" in g or not g["what"].startswith(selectors.PREFIX):
        return None
    sel = selectors.from_key(g["what"])
    if sel.player is not None or sel.zones != ("battlefield",) or sel.card or sel.ability is not None:
        return None
    if kinds and not set(sel.subtypes) & set(kinds) and not (set(kinds) == {"Creature"} and "Creature" in sel.types):
        return None
    return g


def _one(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    from app.rules.scripts import _NoMatch

    g = _group(m["tgt"], kinds=("Creature",))
    if g is None:
        raise _NoMatch
    return [{"do": "attach_to", "src": "self", "who": "target"}], g


def _pair(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    from app.rules.scripts import _NoMatch

    src, dst = _group(m["src"], kinds=("Equipment", "Aura")), _group(m["dst"], kinds=("Creature",))
    if src is None or dst is None:
        raise _NoMatch
    return [{"do": "attach_to", "src": "target", "who": "target:1"}], [src, dst]


def _to_self(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    from app.rules.scripts import _NoMatch

    src = _group(m["src"], kinds=("Equipment", "Aura"))
    if src is None:
        raise _NoMatch
    return [{"do": "attach_to", "src": "target", "who": "self"}], src


TEMPLATES: list[tuple[re.Pattern[str], Any]] = [(_ONE, _one), (_PAIR, _pair), (_TO_SELF, _to_self),
                                                (_TO_THIS_CREATURE, _to_self)]

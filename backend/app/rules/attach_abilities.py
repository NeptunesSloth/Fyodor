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
_ONE = re.compile(rf"^attach {_SELF} to (?P<tgt>(?:up to one )?(?:another )?target [^,.]+)$")  # (wave 16D: "up to one"; 18E: "another")
_UNATTACH = re.compile(rf"^unattach {_SELF}$")  # -- casting extras (wave 18E) -- 702.151a (reconfigure)
_PAIR = re.compile(r"^attach (?P<src>target [^,.]+?) to (?P<dst>(?:up to one )?target [^,.]+)$")  # (wave 19B: "up to one")
_TO_SELF = re.compile(rf"^attach (?P<src>target [^,.]+?) to {_SELF}$")
_TO_THIS_CREATURE = re.compile(r"^attach (?P<src>target [^,.]+?) to this creature$")
_TO_IT = re.compile(r"^attach (?P<src>(?:up to one )?target [^,.]+?) to (?:it|that creature)$")  # (wave 19B: the trigger's creature, or ~)


def _group(phrase: str, *, kinds: tuple[str, ...], upto: bool = False) -> dict[str, Any] | None:
    from app.rules import selectors
    from app.rules.copying import _target_group

    g = _target_group(phrase)
    if g is None or (g["min"], g["max"]) != ((0, 1) if upto else (1, 1)) or "another" in g or not g["what"].startswith(selectors.PREFIX):
        return None
    sel = selectors.from_key(g["what"])
    if sel.player is not None or sel.zones != ("battlefield",) or sel.card or sel.ability is not None:
        return None
    if kinds and not set(sel.subtypes) & set(kinds) and not (set(kinds) == {"Creature"} and "Creature" in sel.types):
        return None
    return g


def _one(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    from app.rules.scripts import _NoMatch

    another = "another target" in m["tgt"]  # -- casting extras (wave 18E) -- 702.151a: another creature than the source (a creature itself)
    g = _group(m["tgt"].replace("another target", "target"), kinds=("Creature",), upto=m["tgt"].startswith("up to"))
    if g is None:
        raise _NoMatch
    if another:
        from dataclasses import replace

        from app.rules import selectors

        g = {**g, "what": replace(selectors.from_key(g["what"]), other=True).key()}
    return [{"do": "attach_to", "src": "self", "who": "target"}], g


def _unattach(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    return [{"do": "unattach_self"}], None


def _pair(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    from app.rules.scripts import _NoMatch

    src = _group(m["src"], kinds=("Equipment", "Aura"))
    dst = _group(m["dst"], kinds=("Creature",), upto=m["dst"].startswith("up to"))
    if src is None or dst is None:
        raise _NoMatch
    return [{"do": "attach_to", "src": "target", "who": "target:1"}], [src, dst]


def _to_self(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    from app.rules.scripts import _NoMatch

    src = _group(m["src"], kinds=("Equipment", "Aura"))
    if src is None:
        raise _NoMatch
    return [{"do": "attach_to", "src": "target", "who": "self"}], src


def _to_it(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    from app.rules.scripts import _NoMatch

    src = _group(m["src"], kinds=("Equipment", "Aura"), upto=m["src"].startswith("up to"))
    if src is None:
        raise _NoMatch
    return [{"do": "attach_to", "src": "target", "who": "it"}], src  # (-- triggers (wave 19B) -- resolve_it binds "it")


TEMPLATES: list[tuple[re.Pattern[str], Any]] = [(_ONE, _one), (_PAIR, _pair), (_TO_SELF, _to_self),
                                                (_TO_THIS_CREATURE, _to_self), (_TO_IT, _to_it), (_UNATTACH, _unattach)]

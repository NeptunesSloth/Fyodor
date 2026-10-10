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
_PAIR = re.compile(r"^attach (?P<src>(?:up to one )?target [^,.]+?) to (?P<dst>(?:up to one )?target [^,.]+)$")  # (wave 19B: "up to one"; 30S: the Equipment too)
_TO_SELF = re.compile(rf"^attach (?P<src>(?:up to one )?target [^,.]+?) to {_SELF}$")
_TO_THIS_CREATURE = re.compile(r"^attach (?P<src>target [^,.]+?) to this creature$")
_TO_IT = re.compile(r"^attach (?P<src>(?:up to one |any number of )?target [^,.]+?) to (?:it|that creature)$")  # (wave 19B: the trigger's creature, or ~)


def _group(phrase: str, *, kinds: tuple[str, ...], upto: bool = False) -> dict[str, Any] | None:
    from app.rules import selectors
    from app.rules.copying import _target_group

    g = _target_group(phrase)
    # -- attach all (wave 30S) -- "any number of target Equipment" (Armory Automaton): none up to as many as there are (max > 1)
    many = phrase.startswith("any number of ")
    if g is None or "another" in g or not g["what"].startswith(selectors.PREFIX):
        return None
    if (g["min"] != 0 or g["max"] <= 1) if many else (g["min"], g["max"]) != ((0, 1) if upto else (1, 1)):
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

    # (-- wave 30S -- the object it goes to is any permanent the selector names, "target Rebel you control": an Equipment that can't be
    # attached there doesn't move, 701.3b, ``attachments.host_problem``)
    src = _group(m["src"], kinds=("Equipment", "Aura"), upto=m["src"].startswith("up to"))
    dst = _group(m["dst"], kinds=(), upto=m["dst"].startswith("up to"))
    if src is None or dst is None:
        raise _NoMatch
    return [{"do": "attach_to", "src": "target", "who": "target:1"}], [src, dst]


def _to_self(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    from app.rules.scripts import _NoMatch

    src = _group(m["src"], kinds=("Equipment", "Aura"), upto=m["src"].startswith("up to"))
    if src is None:
        raise _NoMatch
    return [{"do": "attach_to", "src": "target", "who": "self"}], src


def _to_it(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    from app.rules.scripts import _NoMatch

    src = _group(m["src"], kinds=("Equipment", "Aura"), upto=m["src"].startswith("up to"))
    if src is None:
        raise _NoMatch
    return [{"do": "attach_to", "src": "target", "who": "it"}], src  # (-- triggers (wave 19B) -- resolve_it binds "it")


# -- attach choice (wave 25A) -- "you may attach an Equipment you control to it" (attach_entry.choose: not targeted)
_CHOOSE = re.compile(rf"^(?P<may>you may )?attach (?P<n>an|any number of|all) (?P<k>Auras and Equipment|Equipment|Auras|Aura) "
                     rf"(?P<scope>you control|on the battlefield) to (?P<to>it|that creature|{_SELF}|target [^,.]+)$")
_KINDS = {"Equipment": ["Equipment"], "Auras": ["Aura"], "Aura": ["Aura"], "Auras and Equipment": ["Aura", "Equipment"]}


def _choose(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    from app.rules.scripts import _NoMatch

    # -- attach all (wave 30S) -- "attach all Equipment on the battlefield to it" (Vulshok Battlemaster), "attach any number of Auras and
    # Equipment you control to it" (Heavenly Blademaster), "… to target creature you control" (Beatrix): 701.3a
    one = m["n"] == "an"
    if m["k"] not in (("Equipment", "Aura") if one else ("Equipment", "Auras", "Auras and Equipment")):
        raise _NoMatch
    group = _group(m["to"], kinds=()) if m["to"].startswith("target") else None
    if m["to"] == "target permanent or player":  # (Ardenn: an Aura can enchant a player, 303.4c; ``attach_entry.choose`` reads a player host)
        from app.rules.copying import _target_group

        group = _target_group(m["to"])
    if m["to"].startswith("target") and group is None:
        raise _NoMatch
    return [{"do": "attach_choose", "n": 1 if one else "all" if m["n"] == "all" else 0, "kinds": _KINDS[m["k"]],
             "who": "target" if group else "it" if m["to"] in ("it", "that creature") else "self",
             **({"anyone": True} if m["scope"] == "on the battlefield" else {}), **({"optional": True} if m["may"] else {})}], group


_UNATTACH_ALL = re.compile(r"^unattach all Equipment from (?P<from>target [^,.]+|them|it|that creature)$")  # -- attach all (wave 30S) -- Disarm


def _unattach_all(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    from app.rules.scripts import _NoMatch

    if not m["from"].startswith("target"):  # ("Choose two target creatures. Tap those creatures, then unattach all Equipment from them.")
        return [{"do": "unattach_all", "who": "them" if m["from"] == "them" else "it"}], None
    group = _group(m["from"], kinds=())
    if group is None:
        raise _NoMatch
    return [{"do": "unattach_all", "who": "target"}], group


TEMPLATES: list[tuple[re.Pattern[str], Any]] = [(_CHOOSE, _choose), (_ONE, _one), (_PAIR, _pair), (_TO_SELF, _to_self), (_UNATTACH_ALL, _unattach_all),
                                                (_TO_THIS_CREATURE, _to_self), (_TO_IT, _to_it), (_UNATTACH, _unattach)]

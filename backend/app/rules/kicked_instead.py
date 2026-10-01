"""-- kicked / instead (wave 4G) -- kicked spells and "If …, … instead" clauses.

Two generalizations of what scripts.py already reads (wave 1B "instead" clauses, 702.33e kicked gates):

* **Elliptical restatements** (608.2c: read the whole text). "Burst Lightning deals 2 damage to any target. If
  this spell was kicked, it deals 4 damage instead." / "Create two 1/1 green Saproling creature tokens. If this
  spell was kicked, create four of those tokens instead." The alternative repeats the replaced instruction with
  another amount: the same instruction (same target, same source, same token) with that amount. Only a replaced
  sentence of exactly one instruction with a plain number is restated; anything else stays manual.

* **Targets that depend on the kicker** (601.2c, 702.33g). "Exile target artifact or enchantment. If this spell
  was kicked, exile target nonland permanent instead." — kicked status is announced (601.2b) before targets are
  chosen (601.2c), so a spell requires its kicked-only targets only if it was kicked, and the targets of the
  instruction a kicked alternative replaces only if it wasn't ("a spell may require alternative targets only if
  an alternative or additional cost was chosen for it"). A target group carries ``"kicked": True`` (chosen only
  when kicked) or ``"kicked": False`` (only when not kicked); :func:`applicable` turns the other ones into groups
  of zero targets as the spell is cast — "the spell is cast as though it did not require those targets"
  (601.2c) — so the group numbering the effects use never shifts. Spells only: an ability's targets are never
  filtered (702.33g is about "part of a spell's ability").
"""

from __future__ import annotations

import re
from typing import Any

_WORDS = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
          "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
          "twenty": 20}
_TIMES = {"once": 1, "twice": 2, "three times": 3, "four times": 4, "five times": 5}

# "it deals 4 damage" / "~ deals 4 damage" (no recipient: the replaced instruction's)
_DEALS = re.compile(r"^(?:it|~) deals (?P<n>\d+|[a-z]+) damage$")
# "create four of those tokens" (the replaced instruction's tokens: the same token, another number)
_THOSE_TOKENS = re.compile(r"^create (?P<n>\d+|[a-z]+) of those tokens$")
# "investigate twice"
_INVESTIGATE = re.compile(r"^investigate (?P<t>twice|three times|four times|five times)$")


_ALSO = re.compile(r"^(?P<who>that creature|those creatures|it|they) also (?P<verb>gains?|gets?) ")
_ADDITIONAL = re.compile(r"^(?P<lead>.+? gets?) an additional (?P<pt>[+-]\d+/[+-]\d+ until end of turn)$")


def plain_addition(rest: str) -> str:
    """"If this spell was kicked, that creature also gains hexproof …" / "… Zombie creatures you control get an
    additional +2/+2 until end of turn": an addition to what the spell already did (702.33e: it happens too), read
    without the word that says so. (Other wordings pass through unchanged.)"""
    rest = _ALSO.sub(lambda m: f"{m['who']} {m['verb']} ", rest)
    m = _ADDITIONAL.fullmatch(rest)
    return f"{m['lead']} {m['pt']}" if m else rest


def _amount(word: str) -> int | None:
    return int(word) if word.isdigit() else _WORDS.get(word)


def restate(rest: str, base: list[dict[str, Any]]) -> list[dict[str, Any]] | None:
    """The alternative instruction(s) of "[X]. If C, [rest] instead." when ``rest`` repeats X with another
    amount, else None (not such a restatement: the caller reads ``rest`` as a full instruction)."""
    if len(base) != 1 or not isinstance(base[0].get("n"), int):
        return None
    e = base[0]
    if (m := _DEALS.fullmatch(rest)) is not None:
        if e["do"] != "damage" or e.get("src") not in (None, "self"):
            return None  # ("it" is the source of the replaced damage: the spell, or this permanent)
        n = _amount(m["n"])
    elif (m := _THOSE_TOKENS.fullmatch(rest)) is not None:
        if e["do"] not in ("create_token", "token_copy"):
            return None
        n = _amount(m["n"])
    elif (m := _INVESTIGATE.fullmatch(rest)) is not None:
        if e["do"] != "create_token" or (e.get("token") or {}).get("name") != "Clue" or e.get("n") != 1:
            return None
        # (investigating twice is two investigations — two Clues made one at a time — not one with two: 701.16a)
        return [dict(e) for _ in range(_TIMES[m["t"]])]
    else:
        return None
    if n is None or n < 1:
        return None
    return [{**e, "n": n}]


def implies(stronger: dict[str, Any], weaker: dict[str, Any]) -> bool:
    """Does condition ``stronger`` hold only when ``weaker`` does? Read narrowly: the same condition; one part of an
    "all"; "you control a [color] permanent" against "you control a [color] or [color] permanent" (Dega Sanctuary:
    "if you control a black or red permanent, … If you control a black permanent and a red permanent, … instead")."""
    from app.rules import selectors

    if stronger == weaker:
        return True
    if "all" in stronger:
        return any(implies(c, weaker) for c in stronger["all"])
    if set(stronger) != {"value", "op", "n"} or set(weaker) != {"value", "op", "n"}:
        return False
    if stronger["op"] != ">=" or weaker["op"] != ">=" or stronger["n"] < weaker["n"]:
        return False
    a, b = stronger["value"].get("count"), weaker["value"].get("count")
    if not (isinstance(a, str) and isinstance(b, str) and a.startswith(selectors.PREFIX) and b.startswith(selectors.PREFIX)):
        return False
    sa, sb = selectors.from_key(a), selectors.from_key(b)
    from dataclasses import replace

    return replace(sa, colors=()) == replace(sb, colors=()) and bool(sa.colors) and set(sa.colors) <= set(sb.colors)


def mark(groups: list[dict[str, Any]], start: int, end: int, kicked: bool) -> bool:
    """Mark target groups ``start``…``end`` as chosen only when the spell was (or wasn't) kicked. False if one
    of them is already tied to the kicker the other way (nothing to read)."""
    for g in groups[start:end]:
        if g.get("kicked", kicked) != kicked:
            return False
        g["kicked"] = kicked
    return True


def applicable(specs: list[dict[str, Any]], kicked: int) -> list[dict[str, Any]]:
    """601.2c / 702.33g: the target groups a spell kicked ``kicked`` times requires; the others become groups of
    no targets (cast "as though it did not require those targets")."""
    out = []
    for spec in specs:
        if "kicked" in spec and spec["kicked"] != (kicked > 0):
            spec = {**spec, "min": 0, "max": 0}
        out.append(spec)
    return out


def has_kicked_groups(definition: dict[str, Any] | None) -> bool:
    """Does a definition have target groups that depend on the kicker?"""
    return any("kicked" in g for g in (definition or {}).get("targets") or [])


_TARGET_REF = re.compile(r"^target(?::(?P<g>\d+))?(?![a-z_])")


def _groups_named(value: Any) -> set[int]:
    if isinstance(value, str):
        m = _TARGET_REF.match(value)
        return {int(m["g"] or 0)} if m else set()
    out: set[int] = set()
    for v in value if isinstance(value, list) else value.values() if isinstance(value, dict) else ():
        out |= _groups_named(v)
    return out


def refs_ok(effects: list[dict[str, Any]], groups: list[dict[str, Any]]) -> bool:
    """Every instruction naming a target group tied to the kicker happens only when that group was chosen: inside
    the matching kicked gate. An instruction outside it, or in the other branch, would name a target the spell
    may not have: the ability stays manual."""
    tied = {k: g["kicked"] for k, g in enumerate(groups) if "kicked" in g}
    if not tied:
        return True
    state: list[tuple[int, bool]] = []  # (the last effect index a gate covers, its kicked value)
    for i, e in enumerate(effects):
        state = [s for s in state if s[0] >= i]
        if e["do"] == "kicked_gate":
            state.append((i + int(e["n"]), bool(e["kicked"])))
            continue
        under = {k for _, k in state}
        if any(g in tied and tied[g] not in under for g in _groups_named(e)):
            return False
    return True

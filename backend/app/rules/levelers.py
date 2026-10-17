"""-- keyword mechanics (wave 9D) -- leveler cards: level up (702.87) and level symbols (711).

"Level up [cost]" means "[Cost]: Put a level counter on this permanent. Activate only as a sorcery." (702.87a) and
"{LEVEL N1-N2} [Abilities] [P/T]" means "As long as this creature has at least N1 level counters on it, but no more than N2 level
counters on it, it has base power and toughness [P/T] and has [abilities]." (711.2a; "{LEVEL N3+}": N3 or more, 711.2b).
A leveler's lines are rewritten into exactly those sentences when the card's text is split into abilities
(oracle.parse_abilities), so the engine reads them with the grammar it has: a conditional grant of base power and toughness
and of abilities (a keyword, or a quoted ability the grant machinery knows). Whatever the grammar doesn't read stays
unsupported, as before. Below the first symbol's N1 the creature keeps the power and toughness printed on its top box (711.5);
outside the battlefield too (711.6): that is its printed power/toughness. A line that isn't a plain cost, a symbol, a
power/toughness box and ability lines (every leveler printed so far) leaves the card's text as it is.
"""

from __future__ import annotations

import re
from collections.abc import Callable

_LEVEL_UP = re.compile(r"^Level up ((?:\{[^}]+\})+)$")
_SYMBOL = re.compile(r"^LEVEL (\d+)(?:-(\d+)|(\+))$")
_PT = re.compile(r"^\d+/\d+$")
_STARTS_AS_ABILITY = re.compile(r"^(?:When|Whenever|At) |^[^\"]*: ")


def condition(lo: int, hi: int | None) -> str:
    """"this creature has N1 or more level counters on it [but no more than N2 level counters on it]"."""
    text = f"this creature has {lo} or more level counters on it"
    return text + (f" but no more than {hi} level counters on it" if hi is not None else "")


def rewrite(lines: list[str], is_keyword: Callable[[str], bool]) -> list[str]:
    """The card's lines with the level up cost and the level sections written out as CR 702.87a / 711.2 sentences."""
    first = next((i for i, line in enumerate(lines) if _SYMBOL.match(line)), None)
    ups = [i for i, line in enumerate(lines) if line.startswith("Level up")]
    if first is None or len(ups) != 1 or (m := _LEVEL_UP.match(lines[ups[0]])) is None or ups[0] > first:
        return lines
    out = [*lines[: ups[0]], f"{m[1]}: Put a level counter on this creature. Activate only as a sorcery.",
           *lines[ups[0] + 1: first]]
    i = first
    while i < len(lines):
        sym = _SYMBOL.match(lines[i])
        if sym is None or i + 1 >= len(lines) or not _PT.match(lines[i + 1]):
            return lines
        lo, hi = int(sym[1]), (int(sym[2]) if sym[2] else None)
        when = condition(lo, hi)
        out.append(f"As long as {when}, it has base power and toughness {lines[i + 1]}.")
        i += 2
        while i < len(lines) and not _SYMBOL.match(lines[i]):
            out.append(granted(when, lines[i], is_keyword))
            i += 1
    return out


def granted(when: str, text: str, is_keyword: Callable[[str], bool]) -> str:
    """One ability line of a section as "As long as [when], it has [it]." (711.2a, 721.2a): a keyword line, a quoted ability, or a static."""
    line = text.rstrip(".")
    if is_keyword(line):
        words = [w.strip().lower() for w in line.split(", ")]
        return f"As long as {when}, it has {', '.join(words[:-1]) + ' and ' if len(words) > 1 else ''}{words[-1]}."
    if _STARTS_AS_ABILITY.search(text):
        return f'As long as {when}, it has "{text}"'
    return f"As long as {when}, {text[0].lower() + text[1:]}"


# -- Station (wave 46D) -- 702.184a: "Station" means "Tap another untapped creature you control: Put a number of charge counters on this
# permanent equal to the tapped creature's power. Activate only as a sorcery." (the power as the ability resolves: "the creature tapped
# this way", 608.2h). 721.2a-b: a station symbol "N+" is "As long as this permanent has N or more charge counters on it, it has [abilities]"
# (and, with a power/toughness box, "and is a creature with base power and toughness [P/T] in addition to its other types"); the box is the
# one the reminder text names ("It's an artifact creature at N+."). 721.2c: a station card has no power or toughness off the battlefield.
_STATION_SYMBOL = re.compile(r"^(\d+)\+ \| (.+)$")
STATION = ("Tap another untapped creature you control: Put a number of charge counters on this permanent equal to the power of the creature "
           "tapped this way. Activate only as a sorcery.")


def station_creature(text: str) -> int | None:
    """The N of "It's an artifact creature at N+." in a station card's reminder text."""
    m = re.search(r"It's an artifact creature at (\d+)\+\.", text)
    return int(m[1]) if m else None


def station(lines: list[str], text: str, pt: tuple[str | None, str | None], is_keyword: Callable[[str], bool]) -> list[str]:
    """The station card's lines with the station ability and the station symbols written out as CR 702.184a / 721.2 sentences."""
    at, syms = station_creature(text), [i for i, line in enumerate(lines) if _STATION_SYMBOL.match(line)]
    if lines.count("Station") != 1 or (at is None) != (pt == (None, None)) or not syms or syms[0] < lines.index("Station") \
            or (at is not None and (at not in {int(_STATION_SYMBOL.match(lines[i])[1]) for i in syms} or not all(  # type: ignore[index]
                (v or "").isdigit() for v in pt))):
        return lines
    out, when = [STATION if line == "Station" else line for line in lines[: syms[0]]], ""
    for line in lines[syms[0]:]:
        if m := _STATION_SYMBOL.match(line):
            when, line = f"this permanent has {m[1]} or more charge counters on it", m[2]
            if int(m[1]) == at:
                out.append(f"As long as {when}, it is a {pt[0]}/{pt[1]} creature in addition to its other types.")
        out.append(granted(when, line, is_keyword))
    return out

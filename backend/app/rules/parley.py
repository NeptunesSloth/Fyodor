"""-- parley (wave 9C) -- "Each player reveals the top card of their library. For each nonland card revealed this way, [E].
Then each player draws a card." (Selvala's Charge, Rousing of Souls, Cutthroat Negotiator, Phabine, …). Researched
against CR 2026-09-25.

* 701.20a — each player in the game reveals their top card to everyone; revealing leaves it where it is (701.20b), so
  the draw that follows takes the revealed card. A player whose library is empty reveals nothing.
* 608.2c / 608.2h — "for each [kind] card revealed this way" counts the cards the revealing really revealed, once, when
  the instruction after it is carried out; the instruction is then carried out once per card (not once with a bigger
  number), in order with the sentences around it ("Then creatures you control get +1/+1 for each nonland card
  revealed this way" sees the tokens the sentence before made).
* 121.2c — "each player draws a card": every player draws, in turn order.
* 207.2c — "Parley" is an ability word with no rules meaning.

The instruction after "for each" must be a plain, target-free, mandatory one (a Map token, mana and life, a counter, a
pump); anything else stays manual.
"""

from __future__ import annotations

import copy
import re
from typing import Any

_HEAD = re.compile(r"^[Ee]ach player reveals the top card of their library\. (?P<mid>.+) Then each player draws a card\.$")
_FOR_EACH = re.compile(r"^For each (?P<k>nonland|land) card revealed this way, (?P<e>[^.]+)\.")
_THEN_FOR_EACH = re.compile(r"^Then (?P<e>[^.]+?) for each (?P<k>nonland|land) card revealed this way\.")


def split(body: str, head: re.Pattern[str] = _HEAD) -> list[tuple[str, str]] | None:
    """[(land | nonland, the instruction that many times)] of a parley body, or None."""
    m = head.match(body.strip())
    if m is None:
        return None
    mid, out = m["mid"], []
    while mid:
        f = _FOR_EACH.match(mid) or _THEN_FOR_EACH.match(mid)
        if f is None:
            return None
        e = f["e"]
        out.append((f["k"], e[:1].upper() + e[1:] + "."))
        mid = mid[f.end():].lstrip()
    return out or None


def bind(parts: list[tuple[str, str]], parse: Any, *, draw_first: bool = False) -> tuple[list[dict[str, Any]], Any, bool] | None:
    """The effects of a parley body; ``parse`` reads one instruction's text (scripts._parse_effects)."""
    effects: list[dict[str, Any]] = [{"do": "parley_reveal"}]
    draw = {"do": "draw", "who": "each_player", "n": 1}
    if draw_first:  # -- parley (wave 111E) -- the draws come right after the reveal (``split_draw_first``)
        effects.append(draw)
    for kind, text in parts:
        found = parse(text)
        if found is None:
            return None
        inner, groups, optional = found
        if groups or optional or not inner or any(e.get("bind") or e.get("as") or e.get("did") for e in inner):
            return None
        # (Selvala, Explorer Returned: "{T}: … add {G} …" is not a mana ability although it could add mana: its effect
        # moves a card from a library, the draw — 605.1a — so it uses the stack)
        effects += [{"do": "parley_repeat", "kind": kind, "skip": len(inner)}, *inner]
    return [*effects, *([] if draw_first else [draw])], None, False


# -- parley (wave 111E) -- "Each player reveals the top card of their library, then draws a card. For each nonland card revealed this way, [E]."
# (Ambassador K'Ehleyr): the same reveal (701.20a), then every player draws, in turn order (121.2c: the card each revealed), then the instruction
# once for each card of the kind the reveal counted (608.2c: the cards "revealed this way", whatever was drawn since)
_HEAD_DRAW = re.compile(r"^[Ee]ach player reveals the top card of their library, then draws a card\. (?P<mid>For each .+)$")


def split_draw_first(body: str) -> list[tuple[str, str]] | None:
    """The parts of a parley body whose draws come right after the reveal, or None."""
    return split(body, _HEAD_DRAW)


def reveal(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """701.20a: every player reveals their top card; the lands and nonlands among them are counted."""
    counts = {"land": 0, "nonland": 0}
    for pid in plan.live():
        library = plan.state.zones.get(f"{pid}:library", [])
        if not library:
            continue
        plan.do({"type": "reveal_top", "player": pid, "count": 1, **({"source": str(ctx["name"])[:200]} if ctx.get("name") else {})}, actor=ctx["controller"])
        counts["land" if "Land" in plan.ch(plan.state.cards[library[0]]).types else "nonland"] += 1
    ctx["parley"] = counts
    return True


def repeat(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """The next ``skip`` instructions once for each card of the kind revealed (zero: none of them happen)."""
    effects, at, n = ctx["effects"], ctx["next"], int(e["skip"])
    times = int((ctx.get("parley") or {}).get(e["kind"], 0))
    if times == 0:
        ctx["next"] = at + n
        return True
    block = effects[at:at + n]
    effects[at + n:at + n] = [copy.deepcopy(x) for _ in range(times - 1) for x in block]
    return True

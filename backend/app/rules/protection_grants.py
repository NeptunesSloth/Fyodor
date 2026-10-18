"""-- protection grants (wave 5E) -- "… gains protection from <quality> until end of turn", including a quality
chosen as the effect resolves. Researched against the Comprehensive Rules of 2026-09-25.

* 702.16a-f: protection from a quality — DEBT (damage, enchanting/equipping, blocking, targeting), enforced by
  app/rules/protection.py wherever the object's keyword lines are read. The grant is a layer-6 ability-adding
  effect (613.1f) on the objects named now (611.2c), ending at cleanup (514.2): the existing ``grant`` effect with
  the keyword line as a granted ability, so protection.qualities reads it like a printed one.
* 702.16g: "protection from A and from B" is two protection abilities (one granted line, as printed).
* "of your choice": the choice is made as the effect resolves (608.2: instructions are followed in order;
  nothing is chosen on casting), by the effect's controller, and is public. "protection from colorless or from
  the color of your choice" (Giver of Runes) / "from artifacts or from the color of your choice" (Apostle's
  Blessing) is one choice among those qualities: the object gains protection from one of them.
* 105.1-105.2: the five colors; "colorless" is not a color, so it's offered only where the text names it.

"the color of its controller's choice" (Wishmonger, Pale Wayfarer; wave 34B) is the same choice made by the player who controls the target as it resolves.

"the card type of your choice" (Pippin; wave 42C): any card type may be named (205.2a), but only the nine a Commander deck holds can matter in a game
(a Dungeon, Plane, Scheme, Vanguard or Phenomenon is never a source, spell or permanent here), so those are offered.

Refused (manual): "the chosen color" after "Choose a color." (the binding isn't read), a player gaining protection (that's
app/rules/player_shields.py), a duration other than "until end of turn".
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan

Context = dict[str, Any]

_GAIN = re.compile(r"^(?P<o>.+?) gains? (?:(?P<kw>[a-z]+(?: strike)?(?:(?:, and |, | and )[a-z]+(?: strike)?)*)(?:, and | and |, ))?protection from (?P<q>.+?) until end of turn$")  # (wave 50I: keywords first)
COLORS = ["White", "Blue", "Black", "Red", "Green"]
CHOSEN_LINE = "Protection from the chosen color"
CHOSEN_HEXPROOF = "Hexproof from the chosen color"  # (wave 50J)
_TOXIC_HEXPROOF = re.compile(r"^(?P<o>.+?) gains? toxic (?P<n>\d+) and hexproof from that color until end of turn$")  # Skrelv, Defector Mite (702.164 toxic, 702.11d)
CHOICES: dict[str, list[str]] = {
    "the color of your choice": COLORS,
    "colorless or from the color of your choice": ["Colorless", *COLORS],
    "artifacts or from the color of your choice": ["Artifacts", *COLORS],
    # -- activated other (wave 42C) -- 205.2a: the card types a Commander deck can hold (language._COMMANDER_CARD_TYPES), as protection names them (702.16a)
    "the card type of your choice": ["Artifacts", "Battles", "Creatures", "Enchantments", "Instants", "Kindreds", "Lands", "Planeswalkers", "Sorceries"],
}


def fixed_line(quality: str) -> str | None:
    """"red" / "black and from green" / "creatures" → the keyword line "Protection from …" if protection.py enforces it."""
    from app.rules import protection

    line = f"Protection from {quality}"
    return line if "your choice" not in quality and "chosen" not in quality and protection.supported(line) else None


def clause(text: str) -> tuple[list[dict[str, Any]], Any] | None:
    """The effect sentence "<object> gains protection from <quality> until end of turn", or None when it isn't one
    (``language._Fail`` when it is one this grammar refuses)."""
    m = _GAIN.fullmatch(text)
    if m is None and (th := _TOXIC_HEXPROOF.fullmatch(text)) is not None:  # -- chosen type (wave 50J) -- "Choose a color. … gains toxic 1 and hexproof from that color until end of turn." (Skrelv): the color is bound as protection's is
        from app.rules import language as L

        kind, key, group = L.ref(th["o"])
        if kind == "players":
            raise L._Fail
        return [{"do": "grant", "who": L._who(kind, key), "keywords": [], "abilities": [f"Toxic {th['n']}", CHOSEN_HEXPROOF]}], L._one(group)
    if m is None:
        return None
    from app.rules import language as L

    kind, key, group = L.ref(m["o"])
    if kind == "players":
        raise L._Fail  # (a player gaining protection: app/rules/player_shields.py)
    who = L._who(kind, key)
    q = m["q"]
    kws = re.split(r", and |, | and ", m["kw"]) if m["kw"] else []
    if kws and (not all(re.fullmatch(L.GRANT_KEYWORDS, k) for k in kws) or (line := fixed_line(q)) is None):
        raise L._Fail  # -- most-played modal spells (wave 50I) -- "gain lifelink, indestructible, and protection from each color" (Akroma's Will): one grant, 613.1f; a choice stays apart
    if kws:
        return [{"do": "grant", "who": who, "keywords": kws, "abilities": [line]}], L._one(group)
    if q == "the color of its controller's choice" and who == "target":  # -- activated other (wave 34B) -- Wishmonger, Pale Wayfarer: the target's controller chooses
        return [{"do": "protection_choice", "who": who, "options": list(COLORS), "chooser": "controller"}], L._one(group)
    if q in CHOICES:
        return [{"do": "protection_choice", "who": who, "options": list(CHOICES[q])}], L._one(group)
    if q == "the chosen color":  # -- chosen type (wave 20E) -- "Choose a color. … gain protection from the chosen color": chosen.bind_effects
        return [{"do": "grant", "who": who, "keywords": [], "abilities": [CHOSEN_LINE]}], L._one(group)  # writes the answer in (chosen_value_ok: only after that choice)
    line = fixed_line(q)
    if line is None:
        raise L._Fail
    return [{"do": "grant", "who": who, "keywords": [], "abilities": [line]}], L._one(group)


def protection_choice(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """Ask the effect's controller which quality (608.2), then grant protection from it (``resume``)."""
    from app.game.rules_state import DecisionOption
    from app.rules.effects import _cards
    from app.rules.plan import decide

    if not [c for c in _cards(plan, ctx, e["who"]) if plan.state.cards[c].zone.endswith(":battlefield")]:
        return True  # (nothing left to gain it: 611.2e)
    src = plan.state.cards.get(ctx.get("source_card") or "")
    # -- activated other (wave 34B) -- "the color of its controller's choice": 608.2d, the choice is made by the player who controls the target as it resolves
    chooser = next(plan.state.cards[c].controller for c in _cards(plan, ctx, e["who"]) if plan.state.cards[c].zone.endswith(":battlefield")) \
        if e.get("chooser") == "controller" else ctx["controller"]
    decide(plan, player=chooser, kind="choose_one",
           prompt=f"{ctx.get('name') or 'Protection'}: protection from which {'color' if e['options'] == COLORS else 'quality'}?",
           options=[DecisionOption(id=o, label=o) for o in e["options"]],
           resume={"step": "protection_choice", "ctx": ctx, "e": e}, source=src)
    return False


def resume(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.game.errors import ActionError
    from app.rules.effects import continue_effects, grant

    ctx, e = d.resume["ctx"], d.resume["e"]
    value = chosen[0] if chosen else ""
    if value not in e["options"]:
        raise ActionError("Choose one of the offered qualities")
    plan.note(f"{plan.name(d.player)} chooses {value.lower()}", actor=d.player)
    grant(plan, ctx, {"do": "grant", "who": e["who"], "keywords": [], "abilities": [f"Protection from {value.lower()}"]})
    continue_effects(plan, ctx)


PRIMITIVES = {"protection_choice": protection_choice}
RESUME = {"protection_choice": resume}

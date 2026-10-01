"""Token-creation wording (CR 701.7 "create", 111.10 predefined tokens) → ``create_token`` effects.

One grammar for the sentence "Create [N] [tapped] [P/T color(s) Subtype(s) [artifact] creature |
Predefined] token(s) [named X] [with keywords and/or "a quoted ability"] [that's tapped and
attacking] [for each … | , where X is …]". Every part must be understood — a keyword the engine
doesn't carry out, a quoted ability it can't run, a creature type it doesn't know — or the
sentence is not a template match (``parse`` returns None: the card stays manual).

Tokens are created with their full characteristics (111.10 for predefined ones: the CR text of
their abilities, so the engine runs them like any permanent's; the token's own abilities that
the engine can't run yet — a Map's "target creature you control explores" — stay manual on the
token). "Tapped" is the token entering tapped (111.4, 701.7a); "tapped and attacking" is 508.4:
its controller chooses which defending player or planeswalker it attacks, it is attacking but
never "attacked", and outside the declare attackers step or later of a combat phase (or created
by someone other than the attacking player, 506.3b) it simply isn't attacking.
"""

from __future__ import annotations

import re
from typing import Any

from app.game.rules_state import DecisionOption
from app.rules import values
from app.rules.creature_types import CREATURE_TYPES
from app.rules.plan import Plan, decide

Effect = dict[str, Any]

NUMBERS = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
           "nine": 9, "ten": 10}
COLOR_WORDS = {"white": "W", "blue": "U", "black": "B", "red": "R", "green": "G"}

# 205.3g / 205.3h: an artifact creature token or an enchantment creature token may carry an
# artifact type ("Sculpture Treasure artifact creature token") or an enchantment type ("Shrine
# enchantment creature token") among its subtypes.
ARTIFACT_TYPES = frozenset({"Attraction", "Blood", "Bobblehead", "Book", "Clue", "Contraption", "Equipment", "Food",
                            "Fortification", "Gold", "Heartwood", "Incubator", "Infinity", "Junk", "Lander", "Map",
                            "Mutagen", "Powerstone", "Spacecraft", "Stone", "Treasure", "Vehicle", "Vibranium"})
ENCHANTMENT_TYPES = frozenset({"Aura", "Background", "Cartouche", "Case", "Class", "Curse", "Plan", "Role", "Room",
                               "Rune", "Saga", "Shard", "Shrine"})

# 111.10s–v, colorless artifact tokens with the CR's rules text (the older ones are in
# app.rules.scripts.PREDEFINED_TOKENS; both are consulted).
PREDEFINED_TOKENS = {
    "Map": ("Token Artifact — Map", "{1}, {T}, Sacrifice this token: Target creature you control explores. Activate only as a sorcery."),
    "Junk": ("Token Artifact — Junk", "{T}, Sacrifice this token: Exile the top card of your library. You may play that card this turn. Activate only as a sorcery."),
    "Lander": ("Token Artifact — Lander", "{2}, {T}, Sacrifice this token: Search your library for a basic land card, put it onto the battlefield tapped, then shuffle."),
    "Mutagen": ("Token Artifact — Mutagen", "{1}, {T}, Sacrifice this token: Put a +1/+1 counter on target creature. Activate only as a sorcery."),
}

_QTY = r"\d+|a|an|one|two|three|four|five|six|seven|eight|nine|ten|x|X"
_COLORS = r"colorless|(?:white|blue|black|red|green)(?:(?:,)? (?:and )?(?:white|blue|black|red|green))*"
_CAPS = r"[A-Z][A-Za-z'\-]*(?: [A-Z][A-Za-z'\-]*)*"
_SENTENCE = re.compile(
    rf"^create (?P<n>{_QTY}) (?P<tapped>tapped )?"
    rf"(?:(?P<pt>(?:\d+|X)/(?:\d+|X)) (?P<colors>{_COLORS}) (?P<sub>{_CAPS}) (?P<ench>enchantment )?(?P<art>artifact )?creature tokens?"
    r"|(?P<pre>[A-Z][a-z]+) tokens?)"
    rf"(?: named (?P<name>{_CAPS}))?"
    r"(?: with (?P<with>.+?))?"
    r"(?P<attacking> that(?:'s| are) tapped and attacking)?$")
_RIDER = re.compile(r"^(?P<head>.+?)(?: for each (?P<each>[^\"]+)|, where [xX] is (?P<xdef>[^\"]+))$")


def _qty(word: str) -> Any:
    if word in ("x", "X"):
        return {"x": 1}
    return int(word) if word.isdigit() else NUMBERS[word]


def _subtypes(phrase: str, extra: frozenset[str] = frozenset()) -> list[str] | None:
    """"Human Soldier" → ["Human", "Soldier"]; "Time Lord" is one type. None for a word the rules
    don't list as a creature type (205.3m) — or, for an artifact / enchantment creature token, as
    an artifact type (205.3g) / enchantment type (205.3h): ``extra``."""
    words = phrase.split(" ")
    out: list[str] = []
    while words:
        if len(words) >= 2 and " ".join(words[:2]) in CREATURE_TYPES:
            out.append(" ".join(words[:2]))
            words = words[2:]
        elif words[0] in CREATURE_TYPES or words[0] in extra:
            out.append(words.pop(0))
        else:
            return None
    return out


def _quoted_text(quoted: str) -> str | None:
    """A quoted ability a creature token is created with, if the engine carries it out. "This
    token" is written as the object's own type ("this creature"), which is how the templates
    know the token means itself (app.rules.scripts.self_text)."""
    from app.rules import scripts  # (scripts calls this module from its templates)

    if re.search(r"\btransform\b", quoted, re.I):
        return None  # -- wave 3F -- only the Incubator is a double-faced token (111.10i); others stay manual
    if scripts.granted_ability(quoted) is not None:  # (a mana ability: "Sacrifice this token: Add {C}.")
        return quoted
    text = re.sub(r"\bthis token\b", "this creature", quoted)
    text = re.sub(r"\bThis token\b", "This creature", text)
    return text if scripts.granted_ability(text) is not None else None


def _with(part: str | None) -> tuple[list[str], str | None] | None:
    """"flying", "flying and vigilance", "flying, first strike, and lifelink", '"…"',
    'haste and "…"' → (keywords the engine implements, the quoted ability's text)."""
    if part is None:
        return [], None
    from app.rules.coverage import SUPPORTED_KEYWORDS

    quoted = None
    if part.endswith('"'):
        first = part.find('"')
        if first < 0 or first == len(part) - 1:
            return None
        quoted = part[first + 1:-1]
        part = part[:first].rstrip()
        if part.endswith(" and"):
            part = part[:-4]
        if '"' in quoted:
            return None
    kws = [k.strip() for k in re.split(r", and |, | and ", part) if k.strip()]
    # (wave 3E: "toxic N", read by combat.py from the token's keyword line, 702.164)
    if any(k not in SUPPORTED_KEYWORDS and not re.fullmatch(r"toxic \d+", k) for k in kws):
        return None
    if quoted is not None:
        quoted = _quoted_text(quoted)
        if quoted is None:
            return None
    return kws, quoted


def parse(sentence: str) -> list[Effect] | None:
    """The effects of one "create …" sentence (lower-cased first word, no final period), or None."""
    from app.rules import scripts  # (scripts calls this module from its templates)

    text, each, xdef = sentence, None, None
    # -- X sized by a count (wave 4K) -- "create twice X …", "create half X Food tokens, rounded up" (107.1a: the text
    # says which way to round)
    half = re.match(r"^create (?:(?P<twice>twice X)|half X) (?P<rest>.+?)(?:, rounded (?P<round>up|down))?$", sentence)
    if half is not None and (half["twice"] is None) != (half["round"] is None):  # (half: rounded as the text says)
        sentence = f"create X {half['rest']}"
    else:
        half = None
    r = _RIDER.match(sentence)
    if r:
        text, each, xdef = r["head"], r["each"], r["xdef"]
    else:
        text = sentence
    m = _SENTENCE.match(text)
    if not m:
        return None
    n = _qty(m["n"])
    if half is not None:
        n = {"times": [2, n]} if half["twice"] else {"half": n, "round": half["round"]}
    if each is not None:
        # -- "this way" outcomes (wave 4A) -- "for each creature card milled this way"
        from app.rules import this_way

        v = this_way.parse(each) or values.parse_count(each)
        if v is None:
            return None
        n = v if n == 1 else {"times": [n, v]}
    if m["pre"]:
        if m["with"] or m["name"] or m["attacking"]:
            return None
        found = PREDEFINED_TOKENS.get(m["pre"]) or scripts.PREDEFINED_TOKENS.get(m["pre"])
        if found is None:
            return None
        type_line, ability = found
        token: dict[str, Any] = {"name": m["pre"], "power": None, "toughness": None,
                                 "colors": list(scripts.PREDEFINED_COLORS.get(m["pre"], ())), "type_line": type_line,
                                 "text": ability}
    else:
        extra = (ARTIFACT_TYPES if m["art"] else frozenset()) | (ENCHANTMENT_TYPES if m["ench"] else frozenset())
        subtypes = _subtypes(m["sub"], extra)
        parsed_with = _with(m["with"])
        if subtypes is None or parsed_with is None:
            return None
        kws, quoted = parsed_with
        # -- X sized by a count (wave 4K) -- "an X/X … token": the value of X as the token is created is its printed P/T
        # (111.3: its copiable values; fixed then, 608.2h), evaluated by effects.create_token
        p, t = (_qty(s) if s == "X" else s for s in m["pt"].split("/"))
        colors = [] if m["colors"] == "colorless" else [COLOR_WORDS[w] for w in re.findall(r"white|blue|black|red|green", m["colors"])]
        type_line = f"Token {'Enchantment ' if m['ench'] else ''}{'Artifact ' if m['art'] else ''}Creature — {' '.join(subtypes)}"
        lines = [k.capitalize() for k in kws] + ([quoted] if quoted else [])
        token = {"name": m["name"] or " ".join(subtypes), "power": p, "toughness": t, "colors": colors,
                 "type_line": type_line, "text": "\n".join(lines)}
    if xdef is not None:  # -- X sized by a count (wave 4K) -- one X for the number and the P/T alike (107.3c)
        from app.rules import language

        v = language.x_definition(xdef)
        if v is None or not language._has_x([n, token["power"], token["toughness"]]):
            return None
        n, token = language._bind_x(n, v), language._bind_x(token, v)
    effect: Effect = {"do": "create_attacking" if m["attacking"] else "create_token", "who": "you", "n": n, "token": token}
    if m["tapped"] or m["attacking"]:
        effect["tapped"] = True
    return [effect]


def token_text(quoted: str) -> str | None:
    """'It has "…"' / 'They have "…"' after a create sentence: the quoted ability, if the engine
    carries it out (the same test as "with …")."""
    return _quoted_text(quoted)


# -- "tapped and attacking" (508.4) -----------------------------------------------------------
_ATTACKING_PHASES = ("declare_attackers", "declare_blockers", "combat_damage", "end_combat")


def create_attacking(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Create the tokens tapped; during the declare attackers step or later of the combat phase
    (508.4) their controller, if they are the attacking player (506.3b), chooses which defending
    player or planeswalker they attack (802.2: in a multiplayer game every opponent is a
    defending player). They are attacking but never "attacked" (no attack triggers)."""
    from app.rules import effects  # (effects registers this module's primitives)

    pid = ctx["controller"]
    before = set(plan.state.cards)
    effects.create_token(plan, ctx, {**e, "who": "you", "tapped": True})
    new = [cid for cid, c in plan.state.cards.items() if cid not in before and c.controller == pid
           and c.zone.endswith(":battlefield")]
    if not new or plan.state.turn.phase not in _ATTACKING_PHASES or pid != plan.active:
        return True
    options = [DecisionOption(id=p, label=plan.name(p)) for p in plan.live() if p != pid]
    options += [DecisionOption(id=c.id, label=f"{c.name} ({plan.name(c.controller)})", card_id=c.id)
                for c in plan.state.cards.values() if c.zone.endswith(":battlefield") and c.controller != pid
                and c.controller in plan.live() and plan.in_game(c) and "Planeswalker" in plan.ch(c).types]
    if not options:
        return True
    if len(options) == 1:
        _attack_with(plan, new, options[0].id, pid)
        return True
    decide(plan, player=pid, kind="choose_one", prompt=f"{len(new)} token{'s' if len(new) != 1 else ''} enter attacking: attacking whom?",
           options=options, resume={"step": "token_attack", "ctx": ctx, "cards": new})
    return False


def _attack_with(plan: Plan, cards: list[str], target: str, actor: str) -> None:
    kind = "player" if target in plan.state.players else "card"
    cards = [c for c in cards if c in plan.state.cards and plan.state.cards[c].zone.endswith(":battlefield")]
    if kind == "card" and target not in plan.state.cards:
        return  # 508.4a: the planeswalker is gone: never an attacking creature
    if cards:
        plan.do({"type": "attack", "card_ids": cards, "target": {"kind": kind, "id": target}}, actor=actor)


def resume_token_attack(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import effects

    r = d.resume
    if chosen:
        _attack_with(plan, r["cards"], chosen[0], d.player)
    effects.continue_effects(plan, r["ctx"])


PRIMITIVES = {"create_attacking": create_attacking}
RESUME = {"token_attack": resume_token_attack}

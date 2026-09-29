"""Static abilities that grant characteristics (CR 604, 611.3, 613), parsed from Oracle wording.

"Creatures you control get +1/+1.", "Other Elves you control get +1/+1 and have haste.", "Artifacts
you control have hexproof.", "Commander creatures you own have "…"", "Enchanted creature gets +2/+2
and has first strike.", "~ gets +2/+2 as long as you control three or more artifacts.", "During your
turn, ~ has flying.", "As long as ~ is equipped, it gets +1/+1 and has flying.", "Other creatures
have base power and toughness 2/2."

The subject is the selector grammar (app/rules/selectors.py) or the object itself ("~", "it") or
the object the source is attached to (303.4b, 301.5a). The predicate is any combination of a P/T
modification (layer 7c, 613.4c), a "base power and toughness" setting (layer 7b, 613.4b), keyword
abilities and quoted abilities (layer 6, 613.1f). A condition ("as long as …", "during your turn":
604.2 — a static ability that applies only while its condition is true) is data too: it's checked
each time characteristics are derived (611.3a: never locked in).

Definition (JSON-able)::

    {"kind": "static", "static": "grant", "effects": [],
     "who": "self" | "attached" | "<selector key>",   # what it applies to
     "attached_kind": "creature" | "land" | "permanent" | None,   # "Enchanted creature": only while it's one
     "p": int, "t": int,                # layer 7c
     "base": [p, t] | None,             # layer 7b
     "keywords": [...],                 # layer 6
     "grants": ["<quoted ability>", …], # layer 6 (scripts.granted_ability decides what the engine can run)
     "conditions": [<condition>, …]}    # all must hold; [] for an unconditional static

Conditions: a ``conditions.Condition`` ("you control a Forest", "you have 5 or less life"), or one of
the static-only shapes ``{"static": "your_turn"}``, ``{"static": "self", "test": "attacking" |
"blocking" | "tapped" | "untapped" | "enchanted" | "equipped"}``, ``{"static": "self_counter",
"counter": <kind> | None, "op": ">=", "n": N}`` and ``{"static": "graveyard", "op": ">=", "n": N}``
("there are seven or more cards in your graveyard": threshold, 702.xx wording without the word).

Anything not understood parses to None: the ability then stays manual (wrong automation is worse
than none). Applying these in layer order is app/rules/layers.py's job.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from app.rules import conditions, selectors

if TYPE_CHECKING:
    from app.game.state import CardInstance
    from app.rules.characteristics import Characteristics
    from app.rules.plan import Plan

Definition = dict[str, Any]

# Keyword abilities a static may grant: only ones the engine carries out by reading
# ``Characteristics.keywords`` (combat, targeting, damage). Keywords that are triggered abilities
# (prowess, exalted …), characteristic-defining (changeling, devoid) or that carry a parameter
# (ward {1}, protection from …) aren't granted this way: those lines stay manual. So does flash: it
# matters to a card in hand (702.8a, 113.6e), where a static of a permanent doesn't apply (611.3b).
GRANTABLE_KEYWORDS: frozenset[str] = frozenset({
    "flying", "first strike", "double strike", "deathtouch", "lifelink", "vigilance", "trample", "haste",
    "reach", "menace", "indestructible", "hexproof", "defender", "shroud",
    "plainswalk", "islandwalk", "swampwalk", "mountainwalk", "forestwalk", "desertwalk",
    "shadow", "horsemanship", "fear", "intimidate", "skulk", "wither", "infect",
})

ATTACHED_SUBJECTS = {"enchanted creature": "creature", "equipped creature": "creature", "enchanted land": "land",
                     "enchanted permanent": "permanent", "enchanted artifact": "artifact",
                     "enchanted creatures": None}  # (plural: not a template)
_PT = re.compile(r"^(?P<p>[+−-]\d+)/(?P<t>[+−-]\d+)$")
_BASE = re.compile(r"^base power and toughness (?P<p>\d+)/(?P<t>\d+)$")
_QUOTED = re.compile(r'^"(?P<q>[^"]+)"$')
_NUMBERS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}


def _signed(s: str) -> int:
    return int(s.replace("−", "-"))


def _num(word: str) -> int | None:
    return int(word) if word.isdigit() else _NUMBERS.get(word.lower())


# -- the sentence -----------------------------------------------------------------------------
def parse(text: str) -> Definition | None:
    """One static ability sentence (the card's own name already written as ~) → definition, or None."""
    t = text.strip().replace("’", "'").replace("“", '"').replace("”", '"')
    if not t.endswith(".") and not t.endswith('."'):
        return None
    if t.count(". ") or "\n" in t:
        return None  # two sentences: one of them says something we'd silently drop
    body = t[:-1] if t.endswith(".") else t
    conds: list[dict[str, Any]] = []
    # "During your turn, …" / "As long as <condition>, …" / "… as long as <condition>"
    m = re.match(r"^(?:During your turn|As long as it's your turn), (?P<rest>.+)$", body)
    if m:
        conds.append({"static": "your_turn"})
        body = m["rest"]
    else:
        m = re.match(r"^As long as (?P<cond>.+?), (?P<rest>(?:~|it|[A-Z]).+)$", body)
        if m:
            cond = _condition(m["cond"])
            if cond is None:
                return None
            conds.append(cond)
            body = m["rest"]
        else:
            m = re.match(r"^(?P<rest>.+?) as long as (?P<cond>.+)$", body)
            if m:
                cond = _condition(m["cond"])
                if cond is None:
                    return None
                conds.append(cond)
                body = m["rest"]
    if " as long as " in body or body.startswith(("As long as", "During ", "If ", "if ")):
        return None
    subject, predicate = _split_subject(body)
    if subject is None or predicate is None:
        return None
    who, kind = _subject(subject)
    if who is None:
        return None
    if who == "self" and not conds:
        return None  # "~ has flying." unconditionally is a keyword line, not a static: not a template
    if who != "self" and any(c.get("static") == "self" or c.get("static") == "self_counter" for c in conds):
        return None  # "it's attacking" means the source; a group subject would need "each … that's attacking"
    parts = _predicate(predicate)
    if parts is None:
        return None
    out: Definition = {"kind": "static", "static": "grant", "effects": [], "who": who, "attached_kind": kind,
                       "conditions": conds, **parts}
    return out


def _split_subject(body: str) -> tuple[str | None, str | None]:
    """"Other Elves you control get +1/+1 and have haste" → ("Other Elves you control", "get +1/+1 and
    have haste"): the subject ends before the first verb (get / have)."""
    m = re.search(r"\b(?:gets?|ha(?:s|ve))\b", body)
    if m is None or m.start() == 0:
        return None, None
    return body[: m.start()].strip(), body[m.start():].strip()


def _subject(subject: str) -> tuple[str | None, str | None]:
    """→ ("self" | "attached" | selector key, attached kind)."""
    low = subject.lower()
    if low in ("~", "it"):
        return "self", None
    if low in ATTACHED_SUBJECTS:
        kind = ATTACHED_SUBJECTS[low]
        return ("attached", kind) if kind else (None, None)
    phrase = subject
    each = False
    for det in ("All ", "Each ", "all ", "each "):
        if phrase.startswith(det):
            phrase = phrase[len(det):]
            each = det.lower() == "each "
            break
    if phrase.lower().startswith("other "):
        phrase = "other " + phrase[6:]
    # nouns the selector grammar doesn't name: tokens are "token <permanents>" to it
    phrase = re.sub(r"\bcreature tokens\b", "token creatures", phrase, flags=re.IGNORECASE)
    phrase = re.sub(r"^(?P<pre>(?:other |attacking |untapped |tapped )*)tokens\b", r"\g<pre>token permanents", phrase)
    if not each and not selectors.is_plural(phrase):
        return None, None  # "Creature you control gets …": not Oracle wording for a static
    sel = selectors.parse(phrase)
    if sel is None or sel.player is not None or sel.zones != ("battlefield",) or sel.card:
        return None, None  # spells ("Creature spells you cast have …") and cards in other zones: not here
    return sel.key(), None


def _pieces(predicate: str) -> list[str]:
    """Split "gets +1/+1, has menace, and has "…"" on commas and "and" outside quotes."""
    out: list[str] = []
    buf = ""
    quoted = False
    i = 0
    predicate = predicate.replace("power and toughness", "power_and_toughness")
    while i < len(predicate):
        c = predicate[i]
        if c == '"':
            quoted = not quoted
        if not quoted:
            for sep in (", and ", " and ", ", "):
                if predicate.startswith(sep, i):
                    out.append(buf.strip())
                    buf = ""
                    i += len(sep)
                    break
            else:
                buf += c
                i += 1
            continue
        buf += c
        i += 1
    out.append(buf.strip())
    return [p.replace("power_and_toughness", "power and toughness") for p in out if p]


def _predicate(predicate: str) -> dict[str, Any] | None:
    """"get +1/+1 and have haste" / "has base power and toughness 2/2" / "have "{T}: Add {G}."" →
    the P/T, base, keyword and ability parts (any that are absent are empty)."""
    from app.rules.scripts import granted_ability  # (scripts imports this module)

    p = t = 0
    base: list[int] | None = None
    keywords: list[str] = []
    grants: list[str] = []
    verb: str | None = None
    for piece in _pieces(predicate):
        m = re.match(r"^(?P<verb>gets?|ha(?:s|ve)) (?P<rest>.+)$", piece)
        if m:
            verb, rest = ("get" if m["verb"].startswith("get") else "have"), m["rest"]
        elif verb is None:
            return None
        else:
            rest = piece  # "has flying and vigilance": the verb carries over
        if verb == "get":
            pt = _PT.match(rest)
            if pt is None:
                return None
            p += _signed(pt["p"])
            t += _signed(pt["t"])
            continue
        b = _BASE.match(rest)
        if b:
            if base is not None:
                return None
            base = [int(b["p"]), int(b["t"])]
            continue
        q = _QUOTED.match(rest)
        if q:
            if granted_ability(q["q"]) is None:
                return None
            grants.append(q["q"])
            continue
        if rest in GRANTABLE_KEYWORDS:
            keywords.append(rest)
            continue
        return None
    if not (p or t or base or keywords or grants):
        return None
    return {"p": p, "t": t, "base": base, "keywords": keywords, "grants": grants}


# -- conditions -------------------------------------------------------------------------------
def _condition(text: str) -> dict[str, Any] | None:
    c = text.strip()
    if c in ("it's your turn",):
        return {"static": "your_turn"}
    m = re.fullmatch(r"(?:it|~)(?:'s| is) (?P<test>attacking|blocking|tapped|untapped|enchanted|equipped)", c)
    if m:
        return {"static": "self", "test": m["test"]}
    m = re.fullmatch(r"(?:it|~) has (?:(?P<one>a|an)|(?P<n>\w+) or more) "
                     r"(?P<kind>\+1/\+1|-1/-1|[a-z]+ )?counters? on it", c)
    if m:
        n = 1 if m["one"] else _num(m["n"] or "")
        if n is None:
            return None
        kind = (m["kind"] or "").strip() or None
        return {"static": "self_counter", "counter": kind, "op": ">=", "n": n}
    m = re.fullmatch(r"(?:there are (?P<n1>\w+) or more cards in your graveyard"
                     r"|(?P<n2>\w+) or more cards are in your graveyard)", c)
    if m:
        n = _num(m["n1"] or m["n2"])
        return {"static": "graveyard", "op": ">=", "n": n} if n is not None else None
    return conditions.parse(c)


def holds(plan: Plan, cond: dict[str, Any], *, source: CardInstance, controller: str) -> bool:
    """Is the condition true right now (611.3a)? ``source`` is the permanent with the static."""
    kind = cond.get("static")
    if kind == "your_turn":
        return plan.state.turn.active_player == controller
    if kind == "self":
        test = cond["test"]
        if test == "attacking":
            return source.attacking is not None
        if test == "blocking":
            return bool(source.blocking)
        if test in ("tapped", "untapped"):
            return source.tapped == (test == "tapped")
        sub = "Aura" if test == "enchanted" else "Equipment"
        return any(c.attached_to == source.id and c.zone.endswith(":battlefield") and sub in plan.ch(c).subtypes
                   for c in plan.state.cards.values())
    if kind == "self_counter":
        kinds = [cond["counter"]] if cond["counter"] else list(source.counters)
        return sum(source.counters.get(k, 0) for k in kinds) >= cond["n"]
    if kind == "graveyard":
        return len(plan.state.zones.get(f"{controller}:graveyard", [])) >= cond["n"]
    return conditions.holds(plan, {"controller": controller, "source_card": source.id}, cond)


# -- applying -----------------------------------------------------------------------------------
def conditions_hold(plan: Plan, d: Definition, *, source: CardInstance, controller: str) -> bool:
    """All the static's conditions hold right now. They read the source and the table, never the
    affected object, so one verdict serves every object the static may apply to."""
    return all(holds(plan, c, source=source, controller=controller) for c in d.get("conditions", ()))


def applies(plan: Plan, d: Definition, *, source: CardInstance, controller: str, card: CardInstance,
            ch: Characteristics, conditions: bool | None = None) -> bool:
    """Does this static's effect apply to ``card`` (as it is, ``ch``) right now? The source is on
    the battlefield (611.3b: the caller checks); "you" is its controller (613: the source's
    controller, so the effect follows a change of control). ``conditions``: the verdict of
    :func:`conditions_hold` when the caller has it already (None: evaluated here)."""
    if conditions is False:
        return False
    who = d["who"]
    if who == "self":
        if card.id != source.id:
            return False
    elif who == "attached":
        if source.attached_to != card.id:
            return False
        kind = d.get("attached_kind")
        if kind == "creature" and not ch.is_creature:
            return False
        if kind == "land" and not ch.is_land:
            return False
        if kind == "artifact" and "Artifact" not in ch.types:
            return False
    elif not selectors.matches(plan, selectors.from_key(who), card, ch, controller, source.id):
        return False
    return conditions if conditions is not None else conditions_hold(plan, d, source=source, controller=controller)

"""Declarative ability definitions from Oracle text: the template library.

A card ability the engine automates is described as **data**: a trigger (or spell / activated /
replacement), an optional target, and a list of effects built from the primitives in
``app.rules.effects``. Common Oracle wordings map onto templates here, so one tested mechanic
unlocks every card that uses it. Nothing is ever evaluated or executed from card text; a line
either matches a known template completely or it stays manual.

Definition shape (JSON-able)::

    {"kind": "triggered" | "spell" | "activated" | "replacement" | "static",  # (static: app/rules/statics.py)
     "trigger": "enters_self" | "dies_self" | "ltb_self" | "upkeep_you" | "end_step_you" | "attacks_self",
     "optional": bool,                       # "you may …": asked on resolution (603.5)
     "target": {"what": "creature" | "any" | …} or None,   # one "target [something]", one target
     # or target groups (115.1, 601.2c-d), one per word "target" in printed order; effects name
     # them "target:<g>" and a divided amount {"divided": g}:
     "targets": [{"what": sel, "min": 0, "max": 2, "distinct_from": [0], "divide": {"what": "damage", "total": 3}}],
     "cost": "{2}" (activated only),
     "effects": [{"do": "draw", "who": "you", "n": 1}, …],
     "replacement": "enters_tapped"}

Every template is covered by ``tests/test_rules_scripts.py`` (parsing) and the scenario tests
(outcomes). Hand-written scripts (``app.rules.cards``) take precedence.
"""

from __future__ import annotations

import json
import re
import threading
from collections.abc import Iterator
from dataclasses import replace
from functools import lru_cache
from typing import Any, Literal

from app.rules import characteristics as _chars  # (-- hidden exile (wave 18A) --)
from app.rules import chosen as _chosen  # -- chosen player (wave 4J) --
from app.rules import keyword_triggers as _kw_meanings  # -- static wordings (wave 6E) --
from app.rules import land_plays as _land_plays  # -- one-shot extra land plays (wave 8A) --
from app.rules import restrictions, selectors, this_way  # (this_way: wave 4A)
from app.rules.characteristics import Characteristics
from app.rules.costs import DISCARD, SACRIFICE, parse_ability_cost, spell_additional_cost
from app.rules.oracle import AbilityText, parse_abilities, split_sentences, word_prefix
from app.rules.values import UNMODELED_COUNTERS

Definition = dict[str, Any]

NUMBERS = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
           "nine": 9, "ten": 10}
_N = r"(?P<{name}>\d+|a|an|one|two|three|four|five|six|seven|eight|nine|ten)"
GRANTABLE = ("flying", "first strike", "double strike", "deathtouch", "lifelink", "vigilance", "trample", "haste",
             "reach", "menace", "indestructible", "hexproof")

# Target selectors (CR 115) in Oracle wording → selector key (see app.rules.targets.SELECTORS).
SELECTORS = {
    "any target": "any",
    "target creature": "creature",
    "target creature you control": "creature_you_control",
    "target creature an opponent controls": "creature_opponent_controls",
    "target creature you don't control": "creature_opponent_controls",
    "target creature or planeswalker": "creature_or_planeswalker",
    "target artifact": "artifact",
    "target enchantment": "enchantment",
    "target artifact or enchantment": "artifact_or_enchantment",
    "target land": "land",
    "target planeswalker": "planeswalker",
    "target permanent": "permanent",
    "target nonland permanent": "nonland_permanent",
    "target player": "player",
    "target opponent": "opponent",
    "target attacking or blocking creature": "attacking_or_blocking_creature",
    "target nonland permanent an opponent controls": "nonland_permanent_opp",
    "target artifact or enchantment an opponent controls": "artifact_or_enchantment_opp",
    "target creature or planeswalker an opponent controls": "creature_or_planeswalker_opp",
    "target spell": "spell",
    "target creature spell": "creature_spell",
    "target noncreature spell": "noncreature_spell",
    "target instant or sorcery spell": "instant_or_sorcery_spell",
    "target attacking creature": "attacking_creature",
    "target blocking creature": "blocking_creature",
}
_SEL = "|".join(sorted((re.escape(k) for k in SELECTORS), key=len, reverse=True))

TRIGGERS = [
    (re.compile(r"^When ~ enters, (?P<body>.+)$"), "enters_self"),
    (re.compile(r"^When ~ dies, (?P<body>.+)$"), "dies_self"),
    (re.compile(r"^When ~ leaves the battlefield, (?P<body>.+)$"), "ltb_self"),
    (re.compile(r"^At the beginning of your upkeep, (?P<body>.+)$"), "upkeep_you"),
    (re.compile(r"^At the beginning of your end step, (?P<body>.+)$"), "end_step_you"),
    (re.compile(r"^Whenever ~ attacks, (?P<body>.+)$"), "attacks_self"),
    (re.compile(r"^Whenever ~ enters or attacks, (?P<body>.+)$"), "enters_or_attacks_self"),
    (re.compile(r"^(?:Landfall — )?Whenever a land you control enters, (?P<body>.+)$"), "landfall"),
    (re.compile(r"^When ~ becomes the target of a spell or ability, (?P<body>.+)$"), "targeted_self"),
    # -- keyword actions & face-down (wave 3F) -- 702.37e / 702.168d / 701.40b: fired by casting.turn_face_up
    (re.compile(r"^When ~ is turned face up, (?P<body>.+)$"), "turned_face_up_self"),
    (re.compile(r"^Whenever (?P<filter>another creature you control|a creature you control|another nontoken creature you control|"
                r"a nontoken creature you control|another creature|a creature) enters, (?P<body>.+)$"), "enters_other"),
    # 503.1a / 504 / 505 / 507 / 513: "At the beginning of [whose] [step]" (generic: see step_trigger)
    (re.compile(r"^At the beginning of (?:(?P<whose>your|each|each player's|each opponent's|the|enchanted player's|the chosen player's) "
                r"(?P<step>upkeep|draw step|end step|first main phase|precombat main phase|second main phase|"
                r"postcombat main phase)|the (?P<hstep>upkeep|end step) of enchanted (?:creature|permanent|land|artifact|"
                r"enchantment)'s controller|combat on (?P<cwhose>your|each opponent's) turn|(?P<each_combat>each combat)), "
                r"(?P<body>.+)$"), "step"),
    (re.compile(r"^Whenever you cast (?P<filter>a spell|a creature spell|a noncreature spell|an instant or sorcery spell|"
                r"an artifact spell|an enchantment spell), (?P<body>.+)$"), "cast_you"),
    # -- cast triggers (wave 6D) -- "When you cast this spell, …" (603.2, 601.2i: it triggers from the stack)
    (re.compile(r"^When you cast this spell, (?P<body>.+)$"), "cast_self"),
    # -- state triggers (wave 6D) -- "When you control no Islands, …" (603.8: app/rules/state_triggers.py)
    (re.compile(r"^When (?P<state>you control (?:no|a|an|\w+ or more) [^,]+|there are no [^,]+ on the battlefield|"
                r"you have \w+ or (?:more|less) life|"
                r"(?:~|this [a-z]+) has (?:no|\w+ or more) [^,]+? counters on it|there are (?:\w+ or more|no) [^,]+? counters on (?:~|this [a-z]+)), "  # -- state triggers (waves 19C, 19D) -- its own counters
                r"(?P<body>.+)$"), "state"),
    # Anything else "When/Whenever [subject] [event], …": the generic condition grammar (app/rules/events.py)
    (re.compile(r"^(?:When|Whenever) (?P<cond>[^,]+), (?P<body>.+)$"), "event"),
]


STEPS = {"upkeep": "upkeep", "draw step": "draw", "end step": "end", "first main phase": "main1",
         "precombat main phase": "main1", "second main phase": "main2", "postcombat main phase": "main2"}
WHOSE = {"your": "you", "each": "each", "each player's": "each", "the": "each", "each opponent's": "opponent",
         "enchanted player's": "enchanted_player",
         "the chosen player's": "chosen_player"}  # (-- chosen player (wave 4J) --: app/rules/chosen.py)


def step_trigger(m: re.Match[str]) -> str:
    """"step:<phase>:<whose>": whose step it is decides whether it triggers (at_step)."""
    if m["each_combat"]:
        return "step:begin_combat:each"
    if m["cwhose"]:
        return f"step:begin_combat:{WHOSE[m['cwhose']]}"
    if m["hstep"]:
        return f"step:{STEPS[m['hstep']]}:host_controller"
    return f"step:{STEPS[m['step']]}:{WHOSE[m['whose']]}"


# ("Whenever ~ deals combat damage to a player" is generic: its event has the player dealt the
# damage and the amount — "that player", "that much", 510.2)
_LEGACY_SELF = {"enter": "enters_self", "die": "dies_self", "leave": "ltb_self", "attack": "attacks_self",
                "turned_face_up": "turned_face_up_self"}  # (-- face up (wave 6D) --: only in "~ enters or is turned face up")


def _legacy_trigger(cond: dict[str, Any]) -> str | None:
    """Plain self conditions the engine already fires by name ("When ~ dies" → dies_self); one with
    more to it ("~ attacks alone", "~ attacks or blocks") is matched generically."""
    if cond.get("event") == "multi":
        if cond.get("other") or cond.get("subject") == "host" or not all(e in _LEGACY_SELF for e in cond["events"]):
            return None
        return "multi:" + "+".join(_LEGACY_SELF[e] for e in cond["events"])
    if cond.get("subject") == "self" and cond["event"] in _LEGACY_SELF and set(cond) == {"event", "subject"}:
        return _LEGACY_SELF[cond["event"]]
    return None


def _half_trigger(text: str) -> tuple[str, dict[str, Any] | None] | None:
    """-- trigger tail (wave 15B) -- one half of "A and when B": a trigger the engine fires by name, or a generic condition."""
    if text == "you cast this spell":
        return "cast_self", None
    if text in ("at the beginning of your upkeep", "at the beginning of your end step"):
        return ("upkeep_you" if text.endswith("upkeep") else "end_step_you"), None
    from app.rules import events as event_grammar

    text = re.sub(r"^it ", "~ ", re.sub(r" it$", " ~", text))  # ("~ enters and when you sacrifice it": the first half's object)
    found = event_grammar.parse_condition(text)
    if found is None or found["event"] == "multi":
        return None
    legacy = _legacy_trigger(found)
    return (legacy, None) if legacy else ("event", found)


_HAVE_VERBS = {"fight": "fights", "deal": "deals", "lose": "loses", "become": "becomes", "connive": "connives"}


def _may_have(body: str, ante: str | None) -> str:
    """"you may have it fight target creature" / "you may have target creature lose flying" is the same optional instruction
    in the third person; "it" is the source itself only when the trigger is about it (``ante``), else it stays unread."""
    m = re.match(rf"^you may have (?P<s>~|it|target [a-z ]+?) (?P<v>{'|'.join(_HAVE_VERBS)})\b", body)
    if m is None or (m["s"] == "it" and ante != "self"):
        return body
    return f"you may {'~' if m['s'] == 'it' else m['s']} {_HAVE_VERBS[m['v']]}{body[m.end():]}"


def num(word: str) -> int:
    return int(word) if word.isdigit() else NUMBERS[word.lower()]


def _signed(p: str) -> int:
    return -int(p[1:]) if p[0] in "-−" else int(p.lstrip("+"))


# 207.2c: ability words tie abilities together but have no rules meaning
ABILITY_WORDS = (
    "adamant", "addendum", "alliance", "battalion", "bloodrush", "celebration", "channel", "chroma", "cohort",
    "constellation", "converge", "council's dilemma", "coven", "delirium", "descend 4", "descend 8", "disappear",
    "domain", "eerie", "eminence", "enrage", "fateful hour", "fathomless descent", "ferocious", "flurry", "formidable",
    "grandeur", "hellbent", "heroic", "imprint", "infusion", "inspired", "join forces", "kinship", "landfall",
    "lieutenant", "magecraft", "metalcraft", "morbid", "opus", "pack tactics", "paradox", "parley", "radiance", "raid",
    "rally", "renew", "repartee", "revolt", "secret council", "spell mastery", "strive", "survival", "sweep",
    "tempting offer", "threshold", "undergrowth", "valiant", "vivid", "void", "will of the council",
    # -- ability words (wave 4F) -- printed in italics like an ability word but absent from 207.2c's list (and from
    # the whole CR): no rules meaning either way (207.2d); the condition it names is spelled out after the dash
    "corrupted")
_ABILITY_WORD = re.compile(r"^(?:" + "|".join(re.escape(w).replace("'", "['’]") for w in ABILITY_WORDS) + r") — ",
                           re.IGNORECASE)


_SELF_VERBS = r"(?:enters|attacks|dies|deals|becomes|is|gets|gains|can't|has|blocks|leaves|fights|isn't|doesn't)\b"


def _short_name(name: str, text: str = "") -> str | None:
    """How Oracle text shortens a name like "Sharuum the Hegemon" or "Zur the Enchanter" (the
    first word), unless that word is also a creature type ("Soldier of the Pantheon")."""
    from app.rules.creature_types import CREATURE_TYPES

    two = re.match(r"^([A-ZÀ-ÖØ-Þ][\w'-]+ [A-ZÀ-ÖØ-Þ][\w'-]+) (?:the|of) ", name)  # -- trigger tail (wave 15B) -- "Tor Wauki the Younger"
    if two is not None and re.search(rf"\b{re.escape(two[1])}\b", text):
        return two[1]
    m = re.match(r"^([A-ZÀ-ÖØ-Þ][\w'-]{2,}) (?:the|of) ", name)  # (-- extremes (wave 8B) -- a capital with an accent: Éomer)
    if m is None:
        # -- grammar (wave 11C) -- 201.5c: "Elanor Gardner" is "Elanor" in its own text; taken only where that word acts as
        # the subject ("Elanor enters", "Elanor's power"), so a color or type word of a plain name is never read as it
        m = re.match(r"^([A-ZÀ-ÖØ-Þ][\w'-]{2,}) [A-ZÀ-ÖØ-Þ]", name)
        # (wave 19D: also "put a +1/+1 counter on Legolas", the name after "counter(s) on")
        if m is None or not re.search(rf"\b{re.escape(m[1])}(?: {_SELF_VERBS}|'s )|counters? on {re.escape(m[1])}\b", text):
            return None
    if m[1] in CREATURE_TYPES or m[1].rstrip("s") in CREATURE_TYPES:
        return None
    return m[1]


_POSSESSED = r"(?:owner|library|hand|graveyard|name|power|toughness)"


def _self_pronouns(part: str) -> str:
    """-- grammar (wave 11C) -- a named character's "he / she / him / her / his" is the card itself ("Hercules attacks, put a
    counter on him. He gains …"), written as ~. Anything else stays and so stays unsupported: "he or she" (a player), a
    contraction ("he's"), "her controller" (an earlier permanent's)."""
    part = re.sub(r"(~ enters (?:tapped )?with [^.]+? counters? on) (?:him|her)\b", r"\1 it", part)  # (as the "on it" form)
    part = re.sub(r"\b(?:[Hh]e|[Ss]he)\b(?! or |')", "~", part)
    part = re.sub(rf"\b(?:his|her) (?={_POSSESSED}\b)", "~'s ", part)
    return re.sub(r"(?<!or )\b(?:him|her)\b(?=[.,;:)]|$| (?:and|until|this|then|to|from|into|onto|on|with|unless|if|as|equal|for)\b)",
                  "~", part)


def self_text(text: str, name: str) -> str:
    """The ability with the card's own name (and "this creature" etc.) written as ~, without an
    ability word (207.2c)."""
    out = _ABILITY_WORD.sub("", text, count=1)
    if out.startswith("Exhaust — "):  # -- ability words (wave 4F) -- 702.177a (the restriction: restrictions.parse)
        out = out[len("Exhaust — "):]
    if out.startswith("Boast — "):  # -- activation costs (wave 4H) -- 702.142a (the restriction: restrictions.parse)
        out = out[len("Boast — "):]
    if out.startswith("Power-up — "):  # -- counters (wave 7C) -- 702.193a (restrictions.parse, power_up.py)
        out = out[len("Power-up — "):]
    if out == text and (worded := word_prefix(text)) is not None:  # -- refused zones/sized (wave 3R4) -- 207.2d
        out = worded[1]
    short = _short_name(name, out)
    names = [n for n in sorted({name, name.split(",")[0].strip(), *([short] if short else [])}, key=len, reverse=True)
             if len(n) >= 3 or (len(n) == 2 and n.isupper())]  # (wave 15D: "MJ")

    def own(part: str) -> str:
        # -- activated wordings (wave 15D) -- a token's name is its own ("a Kobold token named Kobolds of Kher Keep" on Kher Keep)
        kept = re.split(r"(?:(?<=token named )|(?<=tokens named ))((?:[A-Z][\w'\-]*)(?: (?:(?:of|the|and|in) )?[A-Z][\w'\-]*)*)", part)
        part = "".join(sub if i % 2 else _own(sub) for i, sub in enumerate(kept))
        return _self_pronouns(part) if "~" in part else part

    def _own(part: str) -> str:
        for n in names:
            # (wave 20C: the short name before "the/of Capital" starts another name: "create Tuktuk the Returned, a legendary …")
            part = re.sub(rf"(?<!\w){re.escape(n)}(?!\w)" + (r"(?! (?:the|of) [A-Z])" if n == short else ""), "~", part)  # (wave 16D: a name ending in "!" has no \b after it)
        return part

    # -- quoted grants (wave 2D) -- inside a quoted ability a name is the card that grants it, not the
    # object that gets it ("this creature" is): it stays as written, so no ~ there means the granter
    # (wave 18F: a granter's name — not a "card named …" — is ‹granter›, 607.1a, bound to the object by app/rules/layers.py)
    def granter(part: str) -> str:
        part = re.sub(rf"(?<!named )(?<!\w){re.escape(name)}(?!\w)", "‹granter›", part)  # (the full name: "each Garruk you control" is no granter)
        return part

    parts = out.split('"')
    out = '"'.join(own(p) if i % 2 == 0 else granter(p) for i, p in enumerate(parts)) if len(parts) % 2 else own(out)
    out = re.sub(r"\b(?:a|an) ((?:[a-z]+ )*?card) other than this card\b", r"another \1", out)  # (wave 19C: Ichorid; the source is that card)
    out = re.sub(r"(\bto the battlefield) and (attach this (?:Equipment|Aura) to it\b)", lambda m: f"{m[1]}. {m[2][0].upper()}{m[2][1:]}", out)  # (wave 19C: Nim Deathmantle: two instructions in order)
    out = re.sub(r"\b[Tt]his (creature|artifact|enchantment|land|permanent|planeswalker|battle|Siege|Class|Equipment|Vehicle|Aura|emblem|Room)\b", "~", out)
    # -- damage sized by a count (wave 20A) -- "Choose any target. Scry 3, then reveal the top card of your library. ~ deals damage equal to
    # that card's mana value to that permanent or player." (Riddle of Lightning): the target is declared as the spell is cast (115.1, 601.2c)
    # whatever the order of the text, so the damage sentence names "any target" itself
    if out.startswith("Choose any target. ") and out.count("that permanent or player") == 1 and out.count("\n") == 0:
        out = out[len("Choose any target. "):].replace("that permanent or player", "any target")
    return _counter_threshold(out)


# -- counters sweep (wave 19D) -- "Put a ribbon counter on ~. Then if it has three or more ribbon counters on it, remove those counters
# and untap it." (Prize Pig, Waterbender Ascension, Cursed Recording): after a sentence that put counters on ~, "it" in the next
# sentence's count is ~ itself (122.1: the counters of that one object), and "those counters" are the ones of that kind ~ has (122.8)
def _counter_threshold(text: str) -> str:
    text = re.sub(r"(counters? on ~) and ~ (gains|gets) ", r"\1. ~ \2 ", text)  # "put a counter on ~ and he gains flying …": two instructions
    text = re.sub(r"(counters? on ~\. Then if )it has( [^,.]+? counters? on )it,", r"\1~ has\2~,", text)
    text = re.sub(r"(counters? on ~\. Then if there (?:are|is) [^,.]+? counters? on )it,", r"\1~,", text)
    return re.sub(r"(Then if (?:~ has|there are) [^,.]+? (\S+) counters? on ~, (?:you may )?)remove (?:those counters|them all|all of them|them)\b",
                  r"\1remove all \2 counters from ~", text)  # (wave 20F: "you may remove those counters and transform it", Primal Amulet)


EFFECTS: list[tuple[re.Pattern[str], Any]] = []


def _self_or_it(word: str) -> str:
    """"~" is the source; "it" is a pronoun resolved later against its antecedent (resolve_it)."""
    return "it" if word == "it" else "self"


def _it_source(word: str) -> dict[str, str]:
    """"It deals …" / "It explores": the pronoun names the object doing it (resolve_it)."""
    return {"src": "it"} if word == "it" else {}


# Events after which the object is still where it was, so "it" can name it (not dies / leaves:
# that's a new object in another zone, 400.7)
_STAYING = {"enter", "attack", "unblocked", "block", "blocked", "tapped", "untapped", "dealt_damage", "deal_damage_opponent",
            "deal_combat_damage_player", "deal_damage", "counters_put", "targeted", "create_token"}
_STAYING.update({"become_monstrous", "become_renowned", "become_level", "explore", "connive", "mutate"})  # -- becomes monstrous (wave 6D) --
_STAYING.add("to_graveyard")  # -- into a graveyard (wave 6D) -- the card(s) there, as they are there
_STAYING.add("tapped_for_mana")  # -- mana riders (wave 5A) -- "Whenever you tap this creature for mana, it deals …"
_STAYING.add("turned_face_up")  # -- hidden exile (wave 18A) -- "Whenever a creature you control is turned face up, put a counter on it"
# Zone-change events after which "it" is the new object the card became where it went — found
# only there (400.7e, 603.6, 603.6c): "When ~ dies, return it to its owner's hand"
_GONE = {"die", "leave"}
# Instructions that act on a card where a zone change put it (a graveyard, exile): what "it" can do
# after "dies" / "leaves the battlefield"
_MOVES = {"bounce", "return_card", "exile"}


def _condition_says_other(cond: dict[str, Any]) -> bool:
    from app.rules import selectors  # (a leaf module)

    subs = [*cond.get("all", ()), *cond.get("any", ()), *([cond["not"]] if "not" in cond else [])]
    if any(_condition_says_other(c) for c in subs):  # (conditional / instead clauses, wave 1B: composed conditions)
        return True
    key = (cond.get("value") or {}).get("count")
    return isinstance(key, str) and selectors.from_key(key).other


def _trigger_antecedent(name: str, cond: dict[str, Any] | None) -> str | None:
    """What "it" / "that creature" means in a triggered ability's effect (its TriggerEvent, 603.2,
    608.2k): "self" — this object when the trigger is about it and it's still there; "self_gone" —
    this object after it died / left (its last known information, 608.2h; a moving instruction
    finds the new object where it went, 400.7e); "event" — the object the event happened to
    ("Whenever another creature you control enters, put a +1/+1 counter on it"); "event_gone" — that
    object after it died / left; "event_all" — every object of a "one or more" event ("they",
    "those creatures"); else None (a pronoun then leaves the ability manual)."""
    if name.startswith("multi:") and not any(x in ("dies_self", "ltb_self") for x in name[6:].split("+")) \
            and (cond is None or cond.get("event") not in _GONE) and "cast_self" not in name:
        return "self"  # -- trigger tail (wave 15B) -- "When ~ enters and whenever you expend 4, put a counter on it": ~ is still there
    if name in ("dies_self", "ltb_self") or name.startswith("multi:"):
        return "self_gone"
    if name.endswith(":host_controller"):  # -- sagas & attached-object triggers (wave 3S) -- "that creature"
        return "event"  # (the enchanted creature as the step began: triggers.at_step_generic)
    cond = cond or {}
    event = cond.get("event")
    if cond.get("other") or (event == "deal_damage" and cond.get("to") == "creature"):
        # "… becomes blocked by a creature, destroy that creature" / "… deals damage to a creature,
        # exile that creature": the creature on the other side, which the event doesn't name
        return None
    if event == "either" and cond.get("subject") in ("self", "self_or", "sel", "host") and all(c["event"] in _GONE for c in cond["conds"]):
        return "self_gone" if cond["subject"] == "self" else "event_gone"  # -- trigger tail (wave 15B) -- "dies or is put into exile"
    if event == "multi":
        if cond.get("subject") == "host":  # -- attached events (wave 4L) -- the attacking / blocking creature
            return "event" if all(x in _STAYING for x in cond["events"]) else None
        return "self" if all(x in _STAYING for x in cond["events"]) else None
    if name.endswith("_self") or cond.get("subject") == "self":
        if event in _GONE or event == "sacrifice":
            return "self_gone"
        return "self" if event in _STAYING or event is None else None
    if name in ("enters_other", "landfall"):
        return "event"
    if name == "state":
        return "self"  # -- state triggers (wave 19C) -- "When ~ has no ice counters on it, sacrifice it": the permanent itself (603.8)
    subject = cond.get("subject")
    if subject == "player" and event == "cast":
        return "event_spell"  # -- sized amounts (wave 3D) -- "that spell's mana value": read from the spell, never "it"
    if subject == "player" and event == "sacrifice" and cond.get("obj") and not cond.get("aggregate"):
        return "event_gone"  # -- triggers (wave 19B) -- "Whenever an opponent sacrifices a permanent, put that card onto the battlefield": 603.10a
    if subject == "player" and event in ("discard", "tapped_for_mana") and cond.get("obj") and not cond.get("aggregate"):
        return "event"  # -- triggers (wave 17D) -- "Whenever you discard a card, exile that card": the discarded card, now in the graveyard (701.9a)
    if subject in ("sel", "self_or", "host", "self_or_host") or (subject == "player" and event == "create_token"):  # (wave 20A: "~ or equipped creature … it")
        if event in _STAYING:
            return "event_all" if cond.get("aggregate") else "event"
        if event in _GONE and not cond.get("aggregate"):
            return "event_gone"
    return None


# -- sagas & attached-object triggers (wave 3S) --
AURA_CARD = "self_aura_gy"  # the Aura's new object in its owner's graveyard (400.7f; effects._cards)


def _aura_card_effects(effects: list[dict[str, Any]]) -> list[dict[str, Any]] | None:
    """"Return this card to its owner's hand" in a trigger on the enchanted permanent leaving: the
    only instruction "this card" may name is returning it to its owner's hand (anything else: manual)."""
    out = []
    for e in effects:
        if e.get("do") == "bounce" and e.get("who") == "self":
            e = {**e, "who": AURA_CARD}
        out.append(e)
    return None if '"self"' in json.dumps(out, default=str) else out


# "At the beginning of enchanted player's upkeep / the upkeep of enchanted creature's controller /
# each opponent's upkeep, that player …": the player whose step it is (triggers.at_step_generic
# gives the event that player and, for the enchanted creature's controller, that creature)
STEP_PLAYER_WHOSE = ("enchanted_player", "host_controller", "opponent", "each", "chosen_player")  # (chosen_player: wave 4J)


def step_names_player(d: dict[str, Any]) -> bool:
    trigger = str(d.get("trigger") or "")
    return d.get("kind") == "triggered" and trigger.startswith("step:") and trigger.rsplit(":", 1)[-1] in STEP_PLAYER_WHOSE
# -- end sagas & attached-object triggers (wave 3S) --


def _group_of(e: dict[str, Any]) -> int | None:
    """The target group an effect acts on ("target:<g>"; plain "target" is group 0)."""
    who = e.get("who")
    if who == "target":
        return 0
    if isinstance(who, str) and who.startswith("target:"):
        return int(who[7:])
    m = re.match(r"controlled:target(?::(\d+))?\|", who) if isinstance(who, str) else None
    if m:  # (wave 13E) "all creatures target player controls"; not 6B's "controlled:target_player_or_controller|…"
        return int(m[1] or 0)
    return None


# -- within-resolution references ----------------------------------------------------------------
# Primitives that record the objects they act on as a named binding of the resolution
# (app/rules/context.py) when the grammar asks them to ("as": "e<k>"), so a later instruction of
# the same spell or ability can refer to them explicitly — never by scanning the board later:
# "Destroy target creature. Its controller gains life equal to its toughness." reads the creature's
# last known information (608.2h); "Exile target creature. Return it to the battlefield" finds the
# new object in exile (400.7j). Each maps to the verb "… <verb> this way" names, if any.
_RECORDING: dict[str, str | None] = {
    "destroy": "destroyed", "destroy_all": "destroyed", "exile": "exiled", "exile_until": "exiled",
    "bounce": "returned", "return_card": "returned", "blink": "returned", "sacrifice": "sacrificed",
    "sacrifice_choice": "sacrificed", "discard": "discarded", "mill": "milled", "search": None, "pick_looked": None,
    "create_token": None, "tap": None, "untap": None, "phase_out": None, "pump": None, "grant": None, "restrict": None,
    "add_counters": None, "remove_counters": None, "regenerate": None, "damage": None,
    "edict": "sacrificed",  # -- "this way" outcomes (wave 4A) -- "each opponent sacrifices a creature …" (effects._choose_next)
    "tap_choice": "tapped",  # (wave 4A) "tap any number of untapped creatures you control" (this_way.tap_choice)
    "double_counters": None, "lki_counters": None, "move_counters": None,  # -- counters (wave 5H) --
}
# Effects that introduce objects by themselves — by moving, choosing or creating them — rather than
# by naming a target: a pronoun after them binds to their recorded objects (the object may be in
# another zone by then, 400.7j, or gone, 608.2h). After a plain target, "it" stays the target.
_MOVERS = {"destroy", "destroy_all", "exile", "exile_until", "bounce", "return_card", "blink", "sacrifice",
           "sacrifice_choice", "discard", "mill", "search", "pick_looked", "create_token",
           "edict"}  # (edict: wave 4A)
_TOKEN_MAKERS = {"create_token", "create_attacking"}  # (what they introduce are tokens, not cards: 111.1)
_RECORDING["create_attacking"] = None  # -- keywords (wave 15E) -- "create … tokens that are tapped and attacking. Sacrifice them …":
_MOVERS.add("create_attacking")  # the pronoun names the tokens made, not the ability's source (was bound to the source)
_CHOSEN = {"sacrifice_choice": "n", "edict": "n", "discard": "n", "mill": "n", "create_token": "n", "search": "max", "pick_looked": "n",
           "create_attacking": "n"}
# ("on": "for each +1/+1 counter on it" — the object a pronoun names, as for its power. Not "hand":
# "that player's hand" names a player, which _bind_stats (objects only) can't bind — values reads
# only "you" / "target" hands, so the phrase stays manual.)
_STAT_KEYS = ("power", "toughness", "mana_value", "on")
# -- stack interaction (wave 5B) -- "Counter target spell. Its controller …": the counter records the
# spell it countered (effects.counter), so "its controller" / "its mana value" read it as it last existed
# on the stack (608.2h). Not a mover: after it, "it" stays the target (the countered card isn't "it").
_RECORDING["counter"] = "countered"
# -- end stack interaction (wave 5B) --


def _is_player_group(group: dict[str, Any]) -> bool:
    from app.rules import selectors  # (a leaf module)

    what = group.get("what") or ""
    if what in ("player", "opponent") or what.startswith("opponent_as:"):  # (wave 21E)
        return True
    return what.startswith(selectors.PREFIX) and selectors.from_key(what).player is not None


class _Introducer:
    """What one effect introduced: objects (with their number) and/or a player."""

    __slots__ = ("index", "objects", "recording", "number", "player", "verb", "do")

    def __init__(self, index: int, e: dict[str, Any], groups: list[dict[str, Any]] | None) -> None:
        from app.rules import selectors  # (a leaf module)

        self.index = index
        self.do = e.get("do")
        self.verb = _RECORDING.get(self.do or "")
        self.recording = self.do in _RECORDING  # (can carry a binding: "its controller", "its power")
        self.objects = self.recording
        self.player = False
        self.number: int | None = 1  # 1 (singular), 2 (several), None (unknown)
        g = _group_of(e)
        who = e.get("who") or ""
        if g is not None and groups is not None and g < len(groups):
            if _is_player_group(groups[g]):
                self.player = groups[g]["max"] == 1
                self.objects = self.objects and (self.do in _CHOSEN or who.startswith("controlled:"))  # ("target player sacrifices a creature")
            else:
                self.objects = True  # (a targeted object: "it" is that target, whatever the effect)
            self.number = 1 if groups[g]["max"] == 1 else 2
        elif who.startswith(selectors.PREFIX) or who in ("creatures_you_control", "each_creature", "all",
                                                        "each_player", "each_opponent"):
            self.number = 2  # ("exile all creatures", "each opponent sacrifices …")
        if who.startswith("controlled:"):  # (wave 13E: "Tap all creatures target player controls. Those creatures …")
            self.number = 2
        if self.do in _CHOSEN:  # ("sacrifice a creature", "create two … tokens"): as many as it says
            n = e.get(_CHOSEN[self.do], 1)
            self.number = 1 if n == 1 else (2 if isinstance(n, int) else None)
            if self.do == "look_top" and e.get("until"):
                self.number = 1  # -- damage sized by a count (wave 20A) -- "until you reveal a nonland card. … that card's mana value": the one found
        if self.do == "destroy_all":
            self.number = 2
        if self.do == "edict" and g is None and who != "you":  # (wave 4A: one each, from several players)
            self.number = 2


def _bind_stats(v: Any, bind: Any, spell: Any = None) -> Any:
    """Rewrite {"power" | "toughness" | "mana_value": "it"} placeholders in a value expression
    ("that_spell": ``spell`` binds it when given, else as "it")."""
    if isinstance(v, list):
        return [_bind_stats(x, bind, spell) for x in v]
    if not isinstance(v, dict):
        return v
    out = {}
    for k, x in v.items():
        if k in _STAT_KEYS and (x in ("it", "that_spell", "cost:exiled") or (isinstance(x, str) and x.startswith("it:"))):
            x = (spell or bind)() if x == "that_spell" else bind(x[3:]) if x.startswith("it:") else bind("exiled") if x == "cost:exiled" else bind()
            if x is None:
                raise _NoMatch
        else:
            x = _bind_stats(x, bind, spell)
        out[k] = x
    return out


# -- counters (wave 5H) --
def _counted_group(e: dict[str, Any]) -> str | None:
    """The permanents an instruction's amount counts ("draw a card for each creature you control with …"): a
    selector over the battlefield, or None."""
    from app.rules import selectors  # (a leaf module)

    n = e.get("n")
    key = n.get("count") if isinstance(n, dict) and set(n) == {"count"} else None
    if not isinstance(key, str) or not key.startswith(selectors.PREFIX):
        return None
    sel = selectors.from_key(key)
    return key if sel.zones == ("battlefield",) and sel.player is None and not sel.card else None
# -- end counters (wave 5H) --


def _cast_trigger_spell_cond(cond: dict[str, Any]) -> bool:
    """-- ability words (wave 9C) -- is a condition (or a part of one, under "not" / "all" / "any" as an "instead" clause
    makes it) about the mana spent to cast a cast trigger's spell ("if no mana was spent to cast it", opus)?"""
    cast = cond.get("cast") or {}
    return bool(cast.get("no_mana") or cast.get("event_spell")) or (cond.get("stat") == "mana_value" and cond.get("object") == "it") or any(
        _cast_trigger_spell_cond(c) for k in ("all", "any") for c in cond.get(k, ())) or (
        "not" in cond and _cast_trigger_spell_cond(cond["not"]))


def resolve_it(effects: list[dict[str, Any]], antecedent: str | None, groups: list[dict[str, Any]] | None = None,
               *, sentences: list[int] | None = None, event_player: bool = False) -> list[dict[str, Any]] | None:
    """Resolve the pronouns in parsed effects — the placeholders "who": "it" / "them" (with a verb:
    "it:exiled" for "the exiled card", "them:exiled" for "cards exiled this way"), "it.controller"
    / "it.owner", "that_player", "src": "it", and {"power": "it"} in values.

    A pronoun binds to the nearest compatible *introducer* by number and kind: the latest sentence
    (``sentences``: where each starts) before it that introduced something compatible — an object
    for "it" (one) / "them" (several), a player for "that player". If that sentence introduced two
    compatible candidates ("Destroy target creature and target artifact. Its controller …"), the
    ability stays manual (None): never a guess.

    After a plain target, "it" / "them" are that target ("Untap target creature. It gets +1/+4")
    — the target as it was chosen, still that object (608.2b). After an instruction that moved,
    chose or created objects, or for information about the object ("its controller", "its
    toughness"), the pronoun names the instruction's recorded objects: it gets a binding ("as":
    "e<k>") and the pronoun reads "ref:e<k>" (app/rules/context.py: the new object where it went,
    400.7j, or its last known information, 608.2h). Otherwise "it" is ``antecedent`` ("self" for
    "When ~ dies, return it …", "event" for the object a trigger was about); "that player" with no
    target player is the trigger event's player (checked by _event_refs_ok), unless the event has
    one *and* a player was targeted (ambiguous, None)."""
    out: list[dict[str, Any]] = []
    intros: list[_Introducer] = []
    starts = sentences if sentences is not None else list(range(len(effects)))

    def sentence_of(index: int) -> int:
        return sum(1 for s in starts if s <= index) - 1

    def find(ok: Any, before: int) -> _Introducer | None:
        """The unique compatible introducer in the latest sentence that has one (None: none, or
        two in the same sentence)."""
        fitting = [i for i in intros if i.index < before and ok(i)]
        if not fitting:
            return None
        latest = sentence_of(fitting[-1].index)
        same = [i for i in fitting if sentence_of(i.index) == latest]
        # -- looks (wave 8B) -- "Reveal the top card of your library and put that card into your hand. You lose life equal
        # to its mana value.": "that card" is the card revealed, so the one card is the pick (not two candidates)
        if any(i.do == "pick_looked" and out[i.index].get("which") in ("that", "all") for i in same):
            same = [i for i in same if i.do != "look_top"]
        # ("target creature gets +2/+2 and gains reach": two effects on one target are one candidate)
        distinct = {(("g", _group_of(out[i.index])) if _group_of(out[i.index]) is not None else ("i", i.index)): i
                    for i in same}
        if len(distinct) != 1:
            raise _NoMatch  # (ambiguous)
        return same[-1]

    def bound(intro: _Introducer) -> str:
        """The binding name of an introducer (marking its effect to record it)."""
        if not intro.recording:
            raise _NoMatch  # (an effect that doesn't record what it acted on: manual)
        name = f"e{intro.index}"
        out[intro.index]["as"] = name
        return name

    def closed_gate(k: int, index: int) -> bool:
        """Is effect k inside a gated (only_if) block that ended before ``index``? (what a gated
        instruction moved may never have happened: a later condition's "it" isn't that)"""
        return any(g.get("do") == "only_if" and g_i < k <= g_i + int(g.get("skip", 0)) < index
                   for g_i, g in enumerate(out[:index]))

    def objects(index: int, number: int | None, verb: str | None, skip_gated: bool = False) -> _Introducer | None:
        def ok(i: _Introducer) -> bool:
            if not i.objects or (skip_gated and closed_gate(i.index, index)):
                return False
            if verb == "card":  # "that card": a card, so not a token an instruction created (111.1)
                if i.do == "look_top" and any(o.get("do") == "pick_looked" and o.get("to") == "exile" for o in out[i.index + 1:index]):
                    return False  # -- hidden exile (wave 18A) -- "look at …, exile two of them, … You may play those cards": the exiled ones
                return i.do not in _TOKEN_MAKERS and (i.number is None or number is None or i.number == number)
            if verb is not None:
                return i.verb == verb
            return i.number is None or number is None or i.number == number
        return find(ok, index)

    def stat_ref(index: int, verb: str | None = None) -> Any:
        intro = objects(index, 1, verb)
        if verb is not None and intro is None:
            return "cost:" + verb  # -- as long as (wave 9B) -- "the discarded card's mana value" of a cost (scripts.define checks it is one)
        if intro is not None:
            if not intro.recording and intro.do not in _MOVERS and _group_of(out[intro.index]) is not None:
                # -- sized amounts (wave 3D) -- a plain target ("Put a +1/+1 counter on target creature you control.
                # Then that creature deals damage equal to its power"): the target itself, as it is (or was: 608.2h)
                g = _group_of(out[intro.index])
                return "target" if groups is None else f"target:{g}"
            return "ref:" + bound(intro)
        # (the source's own power, as it is or as it last existed: values._object reads its LKI)
        if antecedent in ("self", "self_gone"):
            return "self"
        # the trigger event's object, as it is or as it last existed (603.10a, 608.2h)
        return "event" if antecedent in ("event", "event_gone", "event_spell") else None

    def cond_ref(index: int) -> Any:
        """The object "it" names in a condition (conditional / instead clauses, wave 1B): what an earlier
        instruction moved, chose or created (its recorded object, 400.7j), a plain target of one
        (the target itself), the source, or the trigger event's object."""
        intro = objects(index, 1, None, skip_gated=True)
        if intro is None:
            return None if antecedent == "event_spell" else stat_ref(index)
        if intro.do in _MOVERS or _group_of(out[intro.index]) is None:
            return "ref:" + bound(intro)
        g = _group_of(out[intro.index])
        return "target" if groups is None else f"target:{g}"

    try:
        for index, e in enumerate(effects):
            e = dict(e)
            out.append(e)
            if e.get("do") == "copy_spell" and e.get("first") and not e.get("excepts") and index > 0 \
                    and (moved := objects(index, 1, "card")) is not None and moved.do in _MOVERS:
                # -- cast a copy (wave 13C) -- "Exile target … card. Copy it.": the card an earlier instruction moved
                e.update(do="copy_cards", who="ref:" + bound(moved))
                e.pop("first")
                intros.append(_Introducer(index, e, groups))  # (wave 18F: the copies, for "You may cast the copy" next)
                continue
            if e.get("player") == "that_player":  # -- static wordings (wave 6E) -- "that player exiles the top card of
                intro = find(lambda i: i.player, index)  # their library": whose library, bound like "who" below
                if intro is not None:
                    if event_player:
                        return None
                    g = _group_of(out[intro.index])
                    e["player"] = "target" if groups is None else f"target:{g}"
                else:
                    e["player"] = "event_player"
            who = e.get("who")
            if isinstance(who, str) and (who in ("it", "them") or who.startswith(("it:", "them:"))):
                pronoun, _, verb = who.partition(":")
                if e.get("do") == "free_cast" and _free_cast_source(e, pronoun, objects(index, None, verb or None), out, bound):
                    continue  # -- refused look/cast-free (wave 3R5) -- the cards looked at, or the card found
                if verb == "chosen":  # -- "this way" outcomes (wave 4A) -- "the chosen cards": a "Choose target …" sentence's
                    want = 1 if pronoun == "it" else 2
                    intro = find(lambda i, want=want: i.do == "choose_targets" and i.number == want, index)
                    if intro is None:
                        return None
                else:
                    intro = objects(index, 1 if pronoun == "it" else 2, verb or None)
                if e.get("do") in ("grant_play", "free_cast", "look_exiled") and (intro is None or intro.do not in _MOVERS):
                    # "You may play that card this turn": only what an earlier instruction of this
                    # ability moved (exiled, found), where it went (400.7h/j) — never the source,
                    # a trigger's object, or a card an instruction put in a hidden zone ("draw a
                    # card. You may play it": the hand is hidden, 400.7 — manual)
                    return None
                if intro is not None:
                    if intro.do in _MOVERS or _group_of(out[intro.index]) is None \
                            or str(out[intro.index].get("who")).startswith("controlled:"):  # (wave 13E: the objects, not the player)
                        e["who"] = "ref:" + bound(intro)
                    else:
                        g = _group_of(out[intro.index])
                        e["who"] = "target" if groups is None else f"target:{g}"
                elif pronoun == "it" and not verb and antecedent in ("self", "event"):
                    e["who"] = antecedent
                elif pronoun == "it" and not verb and antecedent in ("self_gone", "event_gone") and e.get("do") in _MOVES:
                    # "When ~ dies, return it to its owner's hand": the new object the card became in
                    # the zone it went to, found there and only there (400.7e, 603.6c)
                    e["who"] = "event.new"
                elif pronoun == "it" and not verb and antecedent in ("self_gone", "event_gone") and e.get("do") == "token_copy":
                    # -- token copy (wave 20F) -- 608.2h, 111.12: "When ~ dies, create a token that's a copy of it": its last known information
                    e["who"] = "self" if antecedent == "self_gone" else "event"
                elif pronoun == "them" and not verb and antecedent == "event_all":
                    e["who"] = "event"  # "they get +1/+0": every object of the "one or more" event (603.2c)
                elif pronoun == "them" and not verb and index > 0 and _counted_group(out[index - 1]) is not None \
                        and sentence_of(index - 1) == sentence_of(index) - 1:
                    # -- counters (wave 5H) -- "Draw a card for each creature you control with a +1/+1 counter on
                    # it. Those creatures gain indestructible …" (Inspiring Call): the permanents the count read,
                    # recorded as it was read (608.2h: objects, not the group read again)
                    name = f"g{index - 1}"
                    out[index - 1]["note_group"] = {"who": _counted_group(out[index - 1]), "as": name}
                    e["who"] = "ref:" + name
                else:
                    return None
            elif who in ("it.controller", "it.owner"):
                intro = objects(index, 1, None)
                if intro is not None:
                    e["who"] = f"ref:{bound(intro)}.{who[3:]}"
                elif antecedent in ("event", "event_gone", "self_gone"):
                    e["who"] = f"ref:event.{who[3:]}"  # (as it last existed if it left: 608.2h)
                else:
                    return None
            elif who == "that_player":
                intro = find(lambda i: i.player, index)
                if intro is not None:
                    if event_player:
                        return None  # the trigger's player or the target player? (manual)
                    g = _group_of(out[intro.index])
                    e["who"] = "target" if groups is None else f"target:{g}"
                else:
                    e["who"] = "event_player"  # (only a trigger about a player can: _event_refs_ok)
            elif isinstance(who, str) and who.startswith("controlled:that_player|"):
                # -- damage sized by a count (wave 4E) -- "each creature that player controls": that player, bound the same way
                intro = find(lambda i: i.player, index)
                if intro is not None:
                    if event_player:
                        return None
                    g = _group_of(out[intro.index])
                    player = "target" if groups is None else f"target:{g}"
                else:
                    player = "event_player"
                e["who"] = "controlled:" + player + "|" + who.partition("|")[2]
            # -- conditional / instead clauses (wave 1B) --  "If it's a land card, …": the object the pronoun
            # names, read as it is (or as it last existed, 608.2h): a plain target stays "target"
            if e.get("do") == "only_if" and _cond_has_it(e["cond"]) and antecedent == "event_spell" \
                    and _cast_trigger_spell_cond(e["cond"]):
                # (-- if you do (wave 5G) -- the cast spell; -- ability words (wave 9C) -- opus: "five or more mana was spent")
                e["cond"] = _bind_cond(e["cond"], "event")
            if e.get("do") == "only_if" and _cond_has_it(e["cond"]):
                ref = cond_ref(index)
                if ref is None:
                    return None
                e["cond"] = _bind_cond(e["cond"], ref)
            if "n" in e:
                e["n"] = _bind_stats(e["n"], lambda verb=None, at=index: stat_ref(at, verb),
                                     (lambda: "event") if antecedent == "event_spell" else None)  # (wave 3R3)
            if "life_x" in e:  # -- sized payments (wave 5G) -- "pay X life, where X is its power"
                e["life_x"] = _bind_stats(e["life_x"], lambda verb=None, at=index: stat_ref(at, verb),
                                          (lambda: "event") if antecedent == "event_spell" else None)
            for pk in ("p", "t"):  # -- as long as (wave 9B) -- "gets +X/+X …, where X is the discarded card's mana value" (a pump / become)
                # (wave 20A: a pump's plain "it" is "that card's mana value", language._Ante; a "become" reads its own "it")
                placeholder = r'"(?:it:[a-z]+|cost:exiled)"|"(?:power|toughness|mana_value)": "it"' if e.get("do") == "pump" else r'"(?:it:[a-z]+|cost:exiled)"'
                if e.get("do") in ("pump", "become") and re.search(placeholder, json.dumps(e.get(pk), default=str)):
                    e[pk] = _bind_stats(e[pk], lambda verb=None, at=index: stat_ref(at, verb), None)
            # -- X sized by a count (wave 4K) -- an "X/X" token's P/T: the same placeholders as an amount
            if isinstance(e.get("token"), dict) and any(isinstance(e["token"].get(k), dict) for k in ("power", "toughness")):
                e["token"] = {**e["token"], **{k: _bind_stats(e["token"][k], lambda verb=None, at=index: stat_ref(at, verb),
                                                               (lambda: "event") if antecedent == "event_spell" else None)
                                               for k in ("power", "toughness")}}
            if this_way.unbound(e):  # -- "this way" outcomes (wave 4A) -- the instruction a count names
                try:
                    e = out[index] = this_way.bind(e, lambda kinds, at=index: _this_way_binding(kinds, at, find, bound))
                except LookupError:
                    return None
            if e.get("do") == "lki_counters" and e.get("from") in ("it", "self_named"):  # -- counters (wave 5H) --
                # 122.8: the object that left (as it last existed); "its" after another instruction: manual
                if any(i.index < index for i in intros) or antecedent not in ("self_gone", "event_gone") \
                        or (e["from"] == "self_named" and antecedent != "self_gone"):
                    return None
                e = out[index] = {**e, "from": "self" if antecedent == "self_gone" else "event"}
            if e.get("src") == "it":
                if any(i.index < index and out[i.index].get("who") == "host" for i in intros):
                    return None  # ("tap enchanted creature. It deals …": the host, not the source)
                if e.get("do") != "damage" and any(
                        i.index < index and (i.do in _MOVERS or _group_of(out[i.index]) is not None) for i in intros):
                    return None  # (an explore of the target, not the source)
                found = objects(index, 1, None) if e.get("do") == "damage" else None
                if found is not None:
                    # -- sized amounts (wave 3D) -- "… Then that creature deals damage equal to its power to …": the object
                    # an earlier instruction named (its target, or what it moved / chose), the damage's source
                    if found.do in _MOVERS or _group_of(out[found.index]) is None:
                        e["src"] = "ref:" + bound(found)
                    else:
                        g = _group_of(out[found.index])
                        e["src"] = "target" if groups is None else f"target:{g}"
                elif antecedent in ("event", "event_gone") and e.get("do") == "damage":
                    # "Whenever a creature you control enters, it deals damage equal to its power": the trigger's
                    # object deals it (as it is, or as it last existed: 608.2h)
                    e["src"] = "event"
                elif antecedent in ("self", "self_gone"):
                    del e["src"]
                elif antecedent == "event" and e.get("do") == "explore":  # -- triggers (wave 17D) -- "Whenever a creature … enters, it explores"
                    del e["src"]
                    e["who"] = "event"
                elif antecedent == "event" and e.get("do") == "attach_to":  # -- token copies & attach on entry (wave 5J) --
                    e["src"] = "event"  # ("Whenever an Equipment you control enters, you may attach it to …")
                else:
                    return None
            if e.get("src") == "them":  # -- as long as (wave 9B) -- "Tap two target creatures. They each deal damage equal to their power …"
                found = objects(index, 2, None) if e.get("do") == "damage" else None
                if found is None or found.do in _MOVERS or _group_of(out[found.index]) is None:
                    return None
                g = _group_of(out[found.index])
                e["src"] = "target" if groups is None else f"target:{g}"
            if e.get("do") in _RECORDING or _group_of(e) is not None:
                intros.append(_Introducer(index, e, groups))
    except _NoMatch:
        return None
    return out


_FOR_EACH_LEADING = re.compile(r"^for each (?P<what>[^,]+ this way), (?:you (?=create |draw |put ))?(?P<rest>[^,]+)$")
_PER_OBJECT = re.compile(r"\b(?:its|it|their|that player|that card|that creature|that permanent|those|they|them)\b")


def _for_each_this_way(text: str) -> str:
    """-- "this way" outcomes (wave 4A) -- "For each creature card milled this way, create a 2/2 … token." is the
    instruction with its multiplier after it ("create a 2/2 … token for each creature card milled this way"). Only
    when the instruction is the same whatever object is counted: "For each permanent destroyed this way, its
    controller creates …" (one instruction per object) stays as written (not read)."""
    m = _FOR_EACH_LEADING.match(text)
    if m is None or this_way.parse(m["what"]) is None or _PER_OBJECT.search(m["rest"]):
        return text
    return f"{m['rest']} for each {m['what']}"


# "Counter target spell. If that spell is countered this way, exile it / put it on top of its owner's library
# instead of into that player's graveyard." (Dissipate, Memory Lapse; 608.2c: the counter's own destination)
_COUNTERED_INSTEAD = re.compile(
    r"if (?:that|the) spell is countered this way, (?:(?P<exile>exile it)|put it on (?:(?P<top>top)|the bottom) of its "
    r"owner's library) instead of (?:putting it )?into (?:its owner's|that player's) graveyard")
_EACH_CONTROLLER = re.compile(r"^for each (?P<what>[^,]+ this way), its controller creates (?P<token>.+)$")


def _each_controller_creates(text: str) -> list[dict[str, Any]] | None:
    """-- "this way" outcomes (wave 4A) -- "For each permanent destroyed this way, its controller creates a 3/3 green
    Elephant creature token." (Terastodon, Rampage of the Clans): one creation, each player making as many as the
    counted objects they controlled (effects.create_token "per_controller"). None: not this form."""
    m = _EACH_CONTROLLER.match(text)
    if m is None or (counted := this_way.parse(m["what"])) is None:
        return None
    from app.rules import token_grammar

    found = token_grammar.parse(f"create {m['token']}")
    if not found or len(found) != 1 or found[0].get("do") != "create_token" or not isinstance(found[0].get("n"), int):
        return None
    return [{**found[0], "who": "you", "per_controller": counted}]


def _this_way_binding(kinds: tuple[str, ...], at: int, find: Any, bound: Any) -> str | None:
    """-- "this way" outcomes (wave 4A) -- the binding of the latest instruction before ``at`` that did one of
    ``kinds`` ("destroyed", "milled", …: _RECORDING's verbs), marking it to record what it acted on."""
    found = find(lambda i: i.objects and i.recording and i.verb in kinds, at)
    return bound(found) if found is not None else None


def _free_cast_source(e: dict[str, Any], pronoun: str, intro: _Introducer | None, out: list[dict[str, Any]],
                      bound: Any) -> bool:
    """-- refused look/cast-free (wave 3R5) -- What a free cast's "them" / "that card" names when the
    instruction before it set cards aside from the top of a library: the cards looked at (still in
    the library, private to the looker: "looked"), or the card a "… until you exile / reveal a …"
    stopped at ("found"). True when bound here; "from among them" after a move ("exile the top X
    cards") is bound by the caller as the moved cards ("that")."""
    if intro is None or intro.do not in ("look_top", "exile_top"):
        if e.get("zone") == "among":
            e["zone"] = "that"
        return False
    src = out[intro.index]
    if str(src.get("player") or "you").startswith("each") and (intro.do == "look_top" or src.get("until")):
        raise _NoMatch  # (several libraries looked at / searched until: ctx keeps one library's; exiled cards are bound)
    if src.get("until"):
        if pronoun != "it":
            raise _NoMatch
        e["zone"] = "found"
    elif intro.do == "look_top" and (e.get("zone") == "among" or src.get("n") == 1):
        e["zone"] = "looked"
    elif intro.do == "exile_top" and e.get("zone") == "among":
        e["zone"], e["who"] = "that", "ref:" + bound(intro)  # (every card exiled, from one library or several)
        return True
    else:
        return False
    e.pop("who", None)
    return True


_TARGET_REFS = ("who", "to", "from", "redirect", "power", "toughness", "mana_value", "on", "with", "src", "src2", "object", "player")  # ("with": the other creature of a fight; "src": a bite's biter; "object": the object a condition tests)


def rename_bindings(value: Any, prefix: str) -> Any:
    """Prefix the resolution bindings ("as": "e0", "ref:e0", "ref:e0.controller") of one clause,
    so clauses parsed separately and run as one resolution (a spell's lines, a modal spell's
    modes) never share a name. The trigger event's binding ("ref:event…") is not a clause's."""
    if isinstance(value, list):
        return [rename_bindings(v, prefix) for v in value]
    if not isinstance(value, dict):
        return value
    out = {}
    for k, v in value.items():
        if k == "rider":  # -- prevention riders (wave 17A) -- its bindings ("prevented", "to", "from_ctrl") are its own
            out[k] = v
            continue
        if k in ("as", "bind", "succeeded", "flag", "did", "ref_amount", "ref_count",
                 "bind_dealt", "bind_excess", "bind_hit", "paid_x") and isinstance(v, str):  # (bind_dealt, paid_x: wave 5G; bind_excess: wave 9B)  # ("bind": the library primitives' recorder;
            v = prefix + v  # "succeeded": the payment an "If you do" / "unless … pays" gate depends on;
            # "flag": the verdict an "instead" / "Otherwise" clause reads)
        elif isinstance(v, str) and v.startswith("ref:") and not v.startswith("ref:event"):
            v = "ref:" + prefix + v[4:]
        elif isinstance(v, str) and v.startswith("except:"):  # -- refused modal/conditional (wave 3R1) -- (Martial Coup)
            v = "except:" + prefix + v[len("except:"):]
        else:
            v = rename_bindings(v, prefix)
        out[k] = v
    return out


def _renumber(value: Any, index: list[int] | None) -> Any:
    """Rewrite a clause's own target references ("target" = its first group, "target:<k>", n
    {"divided": k}) to the ability's group numbers (``index[k]``); ``index`` None: back to the
    plain "target" of an ability with one simple target."""
    if isinstance(value, list):
        return [_renumber(v, index) for v in value]
    if not isinstance(value, dict):
        return value
    out = {}
    for k, v in value.items():
        if k in _TARGET_REFS and isinstance(v, str) and (v == "target" or v.startswith("target:")):
            local = 0 if v == "target" else int(v[7:])
            v = "target" if index is None else f"target:{index[local]}"
        elif k in _TARGET_REFS and isinstance(v, str) and re.match(r"controlled:target(?::\d+)?\|", v):
            # -- static wordings (wave 6E) -- "creatures target player controls": the player is the clause's target too
            # (only "target" / "target:<k>": "controlled:target_player_or_controller|…" is 6B's player reference)
            players, _, key = v[len("controlled:"):].partition("|")
            local = 0 if players == "target" else int(players[7:])
            v = f"controlled:{'target' if index is None else f'target:{index[local]}'}|{key}"
        elif k == "divided" and isinstance(v, int):
            if index is None:
                raise _NoMatch
            v = index[v]
        # -- review (wave 5R) -- a reflexive trigger's ability (603.12) chooses its own targets as it's put on the
        # stack: its "target" words aren't the spell's target groups (an IndexError on "You may sacrifice a creature.
        # When you do, ~ deals 4 damage to target creature." in a spell)
        elif k == "ability" and value.get("do") == "reflexive":
            pass
        # -- end review (wave 5R) --
        else:
            v = _renumber(v, index)
        out[k] = v
    return out


def _as_groups(sel: Any) -> list[dict[str, Any]]:
    """A clause's targets (None, a selector key, one group, several) as target groups."""
    if sel is None:
        return []
    if isinstance(sel, str):
        return [{"what": sel, "min": 1, "max": 1}]
    return [dict(g) for g in ([sel] if isinstance(sel, dict) else sel)]


def _add_groups(groups: list[dict[str, Any]], found: list[dict[str, Any]], sel: Any) -> list[dict[str, Any]]:
    """Append a clause's target groups to the ability's: every word "target" is its own group
    (115.3, 601.2c). "another target …" after an earlier target of the ability can't be the same
    object as those; with no earlier target it means other than the source (as before)."""
    index = []
    for g in _as_groups(sel):
        if "another" in g:
            plain = g.pop("another")
            if groups:
                g = {**g, "what": plain, "distinct_from": list(range(len(groups)))}
            elif not g["what"]:
                raise _NoMatch  # "another target" with nothing before it
        index.append(len(groups))
        groups.append(g)
    return _renumber(found, index)


def _finish_targets(effects: list[dict[str, Any]], groups: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], Any]:
    """(effects, the definition's targets): one simple target keeps the plain "target" shape
    (``"target": {"what": key}``); anything else is a list of groups (``"targets"``)."""
    from app.rules.language import simple

    if not groups:
        return effects, None
    if len(groups) == 1 and simple(groups[0]):
        return _renumber(effects, None), groups[0]["what"]
    return effects, groups


def target_fields(target: Any) -> dict[str, Any]:
    """The definition keys for parsed targets: "target" (one simple target, or None) and, for
    target groups, "targets": [{"what", "min", "max", "distinct_from"?, "divide"?}, …]."""
    if target is None or isinstance(target, str):
        return {"target": {"what": target} if target else None}
    return {"target": None, "targets": target}


def target_groups(definition: dict[str, Any] | None) -> list[dict[str, Any]]:
    """A definition's target groups in printed order (601.2c); the old single "target" is one
    group of exactly one target."""
    if not definition:
        return []
    if definition.get("targets"):
        return [{"min": 1, "max": 1, **g} for g in definition["targets"]]
    spec = definition.get("target")
    return [{**spec, "min": 1, "max": 1}] if spec else []


def effect(pattern: str):  # type: ignore[no-untyped-def]
    def register(fn):  # type: ignore[no-untyped-def]
        EFFECTS.append((re.compile("^" + pattern.format(N=_N.format(name="n"), M=_N.format(name="m"), SEL=_SEL) + "$"), fn))
        return fn
    return register


@effect(r"draw {N} cards?")
def _draw(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    return [{"do": "draw", "who": "you", "n": num(m["n"])}], None


@effect(r"target player draws {N} cards?")
def _target_draws(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    return [{"do": "draw", "who": "target", "n": num(m["n"])}], "player"


# -- activated sweep (wave 17B) -- "Target opponent may draw a card." (Phelddagrif): that player decides (608.2d), on resolution
@effect(r"target (?P<w>player|opponent) may draw {N} cards?")
def _target_may_draw(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    return [{"do": "draw", "who": "target", "n": num(m["n"]), "may": True}], m["w"]


@effect(r"each player draws {N} cards?")
def _each_draws(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    return [{"do": "draw", "who": "each_player", "n": num(m["n"])}], None


# -- triggers (wave 5D) -- "You and target opponent each draw a card." (Loran of the Third Path, Secret Rendezvous):
# one draw instruction for both players — the active player draws first, then the other (121.2c: replace.draw_cards)
@effect(r"you and target opponent each draw {N} cards?")
def _you_and_target_draw(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    return [{"do": "draw", "who": "target", "also": "you", "n": num(m["n"])}], "opponent"


# -- trigger tail (wave 15B) -- "Whenever ~ deals combat damage to a player, you and that player each draw that many cards." (Xyris,
# Sergeant John Benton), "… each gain that much life." (Angel of Destiny): the event's player and amount (a trigger about a player,
# scripts._event_refs_ok); the draw is one instruction for both (121.2c), a gain or loss is each player's own event
@effect(r"you and that player each (?P<v>draw|gain|lose) (?P<n>\d+|a|an|one|two|three|four|five|that many|that much) (?P<what>cards?|life)")
def _you_and_that_player(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    n: Any = {"event_amount": 1} if m["n"].startswith("that ") else num(m["n"])
    if (m["v"] == "draw") != m["what"].startswith("card"):
        raise _NoMatch
    if m["v"] == "draw":
        return [{"do": "draw", "who": "that_player", "also": "you", "n": n}], None
    kind = "gain_life" if m["v"] == "gain" else "lose_life"
    return [{"do": kind, "who": "you", "n": n}, {"do": kind, "who": "that_player", "n": n}], None


# "put two cards from your hand on top of your library in any order" (Brainstorm): a private choice, then the owner's
# order (401.4) — app/rules/put_back.py
@effect(r"put (?:(?P<one>a card)|(?P<n>two|three|four|five) cards) from your hand on top of your library"
        r"(?P<any> in any order)?")
def _put_back(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    if bool(m["one"]) == bool(m["any"]):
        raise _NoMatch  # (several cards come with "in any order"; one card never does)
    return [{"do": "put_back", "n": 1 if m["one"] else num(m["n"])}], None


# -- trigger tail (wave 16C) -- "Target opponent puts a card from their hand on top of their library." (Chimney Imp), "Each player
# puts a card from their hand on top of their library." (Sadistic Augermage): each chooses privately from their own hand (401.4), in
# turn order (101.4)
@effect(r"(?P<who>each player|each opponent|target opponent|target player) puts a card from their hand on top of their library")
def _each_put_back(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    who = m["who"]
    return [{"do": "put_back", "n": 1, "who": "target" if who.startswith("target") else who.replace(" ", "_")}], \
        {"target opponent": "opponent", "target player": "player"}.get(who)
# -- end triggers (wave 5D) --


@effect(r"you gain {N} life")
def _gain(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    return [{"do": "gain_life", "who": "you", "n": num(m["n"])}], None


@effect(r"each opponent loses {N} life")
def _drain(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    return [{"do": "lose_life", "who": "each_opponent", "n": num(m["n"])}], None


@effect(r"each opponent loses {N} life and you gain {M} life")
def _drain_gain(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    return [{"do": "lose_life", "who": "each_opponent", "n": num(m["n"])}, {"do": "gain_life", "who": "you", "n": num(m["m"])}], None


@effect(r"target player loses {N} life")
def _target_loses(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    return [{"do": "lose_life", "who": "target", "n": num(m["n"])}], "player"


# -- life lost (wave 8B) -- "Each opponent loses life equal to the life they lost this turn." (Wound Reflection): each
# opponent's own total (the turn's log, 119.3), read for them as the instruction is carried out (608.2h)
@effect(r"each opponent loses life equal to the life (?:they|that player) lost this turn")
def _lose_life_lost(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    return [{"do": "lose_life", "who": "each_opponent", "n": {"per_player": {"turn_history": "lost"}}}], None


@effect(r"(?P<src>~|it) deals {N} damage to (?P<sel>{SEL})")
def _damage(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    return [{"do": "damage", "who": "target", "n": num(m["n"]), **_it_source(m["src"])}], SELECTORS[m["sel"]]


@effect(r"~ deals {N} damage to each opponent")
def _damage_opponents(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    return [{"do": "damage", "who": "each_opponent", "n": num(m["n"])}], None


@effect(r"~ deals {N} damage to each creature")
def _damage_creatures(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    return [{"do": "damage", "who": "each_creature", "n": num(m["n"])}], None


@effect(r"(?P<sel>target creature|target creature you control) gets (?P<p>[+−-]\d+)/(?P<t>[+−-]\d+) until end of turn")
def _pump_target(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    return [{"do": "pump", "who": "target", "p": _signed(m["p"]), "t": _signed(m["t"])}], SELECTORS[m["sel"]]


@effect(r"(?P<who>~|it) gets (?P<p>[+−-]\d+)/(?P<t>[+−-]\d+) until end of turn")
def _pump_self(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    return [{"do": "pump", "who": _self_or_it(m["who"]), "p": _signed(m["p"]), "t": _signed(m["t"])}], None


@effect(r"creatures you control get (?P<p>[+−-]\d+)/(?P<t>[+−-]\d+) until end of turn")
def _pump_team(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    return [{"do": "pump", "who": "creatures_you_control", "p": _signed(m["p"]), "t": _signed(m["t"])}], None


_KW = "|".join(GRANTABLE)


@effect(rf"(?P<who>target creature|~|it) gains (?P<kw>{_KW}) until end of turn")
def _grant(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    who = "target" if m["who"].startswith("target") else _self_or_it(m["who"])
    return [{"do": "grant", "who": who, "keywords": [m["kw"]]}], "creature" if who == "target" else None


@effect(rf"(?P<sel>target creature|target creature you control) gets (?P<p>[+−-]\d+)/(?P<t>[+−-]\d+) and gains (?P<kw>{_KW}) until end of turn")
def _pump_grant(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    return [{"do": "pump", "who": "target", "p": _signed(m["p"]), "t": _signed(m["t"])},
            {"do": "grant", "who": "target", "keywords": [m["kw"]]}], SELECTORS[m["sel"]]


@effect(r"destroy (?P<sel>{SEL})")
def _destroy(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    return [{"do": "destroy", "who": "target"}], SELECTORS[m["sel"]]


@effect(r"exile (?P<sel>{SEL})")
def _exile(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    return [{"do": "exile", "who": "target"}], SELECTORS[m["sel"]]


@effect(r"return (?P<sel>{SEL}) to its owner's hand")
def _bounce(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    return [{"do": "bounce", "who": "target"}], SELECTORS[m["sel"]]


@effect(r"(?P<verb>tap|untap) (?P<sel>{SEL})")
def _tap(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    return [{"do": m["verb"], "who": "target"}], SELECTORS[m["sel"]]


@effect(r"(?P<verb>scry|surveil) {N}")
def _scry(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    return [{"do": m["verb"], "who": "you", "n": num(m["n"])}], None


@effect(r"you get (?P<e>(?:\{{E\}})+)")
def _energy(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    return [{"do": "player_counter", "who": "you", "counter": "energy", "n": m["e"].count("{E}")}], None


# Predefined tokens (CR 111.10), created with their full rules text.
PREDEFINED_TOKENS = {
    "Treasure": ("Token Artifact — Treasure", "{T}, Sacrifice this token: Add one mana of any color."),
    "Food": ("Token Artifact — Food", "{2}, {T}, Sacrifice this token: You gain 3 life."),
    "Gold": ("Token Artifact — Gold", "Sacrifice this token: Add one mana of any color."),
    "Clue": ("Token Artifact — Clue", "{2}, Sacrifice this token: Draw a card."),
    "Blood": ("Token Artifact — Blood", "{1}, {T}, Discard a card, Sacrifice this token: Draw a card."),
    "Shard": ("Token Enchantment — Shard", "{2}, Sacrifice this token: Scry 1, then draw a card."),
    "Powerstone": ("Token Artifact — Powerstone", "{T}: Add {C}. This mana can't be spent to cast a nonartifact spell."),
    "Heartwood": ("Token Artifact — Heartwood", "{T}: Add {R} or {G}."),
}
PREDEFINED_COLORS = {"Heartwood": ["R", "G"]}  # 111.10x: "a red and green Heartwood artifact token" (the others are colorless)
COLOR_WORDS = {"white": "W", "blue": "U", "black": "B", "red": "R", "green": "G"}
_COLORS_RE = r"(?P<colors>colorless|(?:white|blue|black|red|green)(?:(?:,)? (?:and )?(?:white|blue|black|red|green))*)"


@effect(r"create {N} (?P<pt>\d+/\d+) " + _COLORS_RE + r" (?P<sub>[A-Z][A-Za-z'\-]*(?: [A-Z][A-Za-z'\-]*)*) (?P<ench>enchantment )?(?P<art>artifact )?creature tokens?"
        r"(?: with (?P<kws>(?:(?!, then )[a-z ,])+?)| with \"(?P<quoted>[^\"]+)\")?")  # (", then …": wave 5J, _clause)
def _create_creature(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    p, t = m["pt"].split("/")
    colors = [] if m["colors"] == "colorless" else [COLOR_WORDS[w] for w in re.findall(r"white|blue|black|red|green", m["colors"])]
    kws = [k.strip() for k in re.split(r", and |, | and ", m["kws"] or "") if k.strip()]
    if any(k not in GRANTABLE and k not in ("defender",) for k in kws):
        raise _NoMatch
    type_line = f"Token {'Enchantment ' if m['ench'] else ''}{'Artifact ' if m['art'] else ''}Creature — {m['sub']}"
    text = "\n".join(k.capitalize() for k in kws)
    if m["quoted"]:
        text = _granted_token_text(m["quoted"])
    return [{"do": "create_token", "who": "you", "n": num(m["n"]),
             "token": {"name": m["sub"], "power": p, "toughness": t, "colors": colors, "type_line": type_line, "text": text}}], None


def _token_parse(sentence: str) -> list[dict[str, Any]] | None:  # -- token & pump wordings (wave 6C) --
    from app.rules import token_grammar

    return token_grammar.parse(sentence)


def _granted_token_text(quoted: str) -> str:
    """The quoted ability a token is created with; only ones the engine carries out (a mana
    ability such as an Eldrazi Spawn's "Sacrifice this token: Add {C}.")."""
    from app.rules.mana import parse_mana_ability

    if parse_mana_ability(quoted) is None:
        raise _NoMatch
    return quoted


@effect(r"(?P<s>its controller|its owner|that player|that creature's controller|that permanent's controller|"
        r"target player|target opponent|each opponent|each player) creates (?P<rest>.+)")
def _someone_creates(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    """"Its controller creates a 3/3 green Beast creature token": the create templates with a
    subject (a pronoun is resolved later, resolve_it)."""
    from app.rules import language  # (a leaf module)

    # -- token & pump wordings (wave 6C) -- "Its controller creates a 1/1 … token with changeling": the token grammar
    made = _token_parse("create " + m["rest"]) if not re.search(r"\bfor each\b|, where ", m["rest"]) else None
    if made is not None and all(e["do"] == "create_token" for e in made):
        if m["s"] in ("target player", "target opponent"):
            return [{**e, "who": "target"} for e in made], SELECTORS[m["s"]]
        return [{**e, "who": language.PLAYER_GROUPS[m["s"]]} for e in made], None
    for pattern, build in EFFECTS:
        if build not in (_create_creature, _create_predefined):
            continue
        found = pattern.match("create " + m["rest"])
        if found:
            effects, _ = build(found)
            if m["s"] in ("target player", "target opponent"):
                return [{**e, "who": "target"} for e in effects], SELECTORS[m["s"]]
            return [{**e, "who": language.PLAYER_GROUPS[m["s"]]} for e in effects], None
    raise _NoMatch


@effect(r"(?:it has|they have) \"(?P<quoted>[^\"]+)\"")
def _token_has(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    return [{"do": "token_text", "text": _granted_token_text(m["quoted"])}], None


@effect(r"create {N} (?P<kind>Treasure|Food|Gold|Clue|Blood|Shard|Powerstone|Heartwood) tokens?")
def _create_predefined(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    type_line, text = PREDEFINED_TOKENS[m["kind"]]
    return [{"do": "create_token", "who": "you", "n": num(m["n"]),
             "token": {"name": m["kind"], "power": None, "toughness": None, "colors": list(PREDEFINED_COLORS.get(m["kind"], ())),
                       "type_line": type_line, "text": text}}], None


# -- if you do (wave 8C) -- "put your choice of a +1/+1, first strike, or trample counter on that creature" (counter_pick.py)
@effect(r"put your choice of (?P<kinds>.+?) counters? on (?P<who>~|this creature|it|that creature)")
def _counter_pick(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    from app.rules import counter_pick

    found = counter_pick.parse(m["kinds"], m["who"])
    if found is None:
        raise _NoMatch
    return found, None


@effect(r"put {N} (?P<kind>\+1/\+1|-1/-1) counters? on (?P<who>target creature you control|target creature|~|it|each creature you control)")
def _counters(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    who = {"~": "self", "it": "it", "each creature you control": "creatures_you_control"}.get(m["who"], "target")
    return [{"do": "add_counters", "who": who, "kind": m["kind"], "n": num(m["n"])}], SELECTORS.get(m["who"])


@effect(r"proliferate(?P<again>, then proliferate again| twice)?")
def _proliferate(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    return [{"do": "proliferate", "who": "you"}] * (2 if m["again"] else 1), None  # (wave 16C: 701.34a, one after the other)


# -- X sized by a count (wave 19F) -- "Proliferate X times." (701.34), "it explores X times" (701.44), "Investigate X times." (701.16):
# the instruction after a repeat is carried out as many times as the amount says, one after the other (effects.repeat)
_TIMES = r"(?P<n>\d+|two|three|four|five|X)"


def _repeat(word: str, span: int = 1) -> dict[str, Any]:
    from app.rules import values

    return {"do": "repeat", "n": values.parse_amount(word), "span": span}


@effect(rf"proliferate {_TIMES} times")
def _proliferate_times(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    return [_repeat(m["n"]), {"do": "proliferate", "who": "you"}], None


WIPES = {"creatures": ["Creature"], "artifacts": ["Artifact"], "enchantments": ["Enchantment"],
         "artifacts and enchantments": ["Artifact", "Enchantment"], "creatures and planeswalkers": ["Creature", "Planeswalker"],
         "nonland permanents": ["*nonland"], "artifacts, creatures, and enchantments": ["Artifact", "Creature", "Enchantment"]}


@effect(r"destroy all (?P<what>creatures|artifacts|enchantments|artifacts and enchantments|creatures and planeswalkers|nonland permanents|artifacts, creatures, and enchantments)")
def _wipe(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    return [{"do": "destroy_all", "who": "all", "types": WIPES[m["what"]]}], None


@effect(r"exile (?P<sel>target creature you control|target creature), then return (?:it|that card) to the battlefield under (?P<under>its owner's|your) control")
def _blink(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    return [{"do": "blink", "who": "target", "under": "you" if m["under"] == "your" else "owner"}], SELECTORS[m["sel"]]


@effect(r"return {N} (?P<what>lands?|creatures?) you control to (?:its|their) owner's hands?")
def _return_yours(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    return [{"do": "return_yours", "n": num(m["n"]), "what": "land" if m["what"].startswith("land") else "creature"}], None


@effect(r"counter (?P<sel>target spell|target creature spell|target noncreature spell|target instant or sorcery spell)")
def _counter(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    return [{"do": "counter", "who": "target"}], SELECTORS[m["sel"]]


@effect(r"counter (?P<sel>target spell|target creature spell|target noncreature spell|target instant or sorcery spell)"
        r" unless its controller pays (?P<cost>(?:\{{[^}}X]+\}})+)")  # ({X}: sized as it resolves, _unless_sentence — wave 4C)
def _counter_unless(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    return [{"do": "counter_unless", "who": "target", "cost": m["cost"]}], SELECTORS[m["sel"]]


@effect(r"prevent the next {N} damage that would be dealt to (?P<sel>any target|target creature|target player|~) this turn")
def _prevent(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    if m["sel"] == "~":
        return [{"do": "prevent", "who": "self", "n": num(m["n"])}], None
    return [{"do": "prevent", "who": "target", "n": num(m["n"])}], SELECTORS[m["sel"]]


@effect(r"(?:this spell|~) can't be countered")
def _uncounterable(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    return [], None  # a property of the spell (see uncounterable), not an effect


def uncounterable(ch: Characteristics) -> bool:
    """"This spell can't be countered." / "~ can't be countered." on the card."""
    return any(self_text(ab.text, ch.name).rstrip(".") in ("This spell can't be countered", "~ can't be countered")
               for ab in ch.abilities)


@effect(r"mill {N} cards?")
def _mill(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    return [{"do": "mill", "who": "you", "n": num(m["n"])}], None


@effect(r"exile (?P<sel>{SEL}) until ~ leaves the battlefield")
def _exile_until(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    from app.rules.language import on_battlefield_only

    if not on_battlefield_only(SELECTORS[m["sel"]]):
        raise _NoMatch  # 610.3: a card from another zone goes back there, not onto the battlefield
    return [{"do": "exile_until", "who": "target"}], SELECTORS[m["sel"]]


@effect(r"investigate")
def _investigate(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    type_line, text = PREDEFINED_TOKENS["Clue"]
    return [{"do": "create_token", "who": "you", "n": 1,
             "token": {"name": "Clue", "power": None, "toughness": None, "colors": [], "type_line": type_line, "text": text}}], None


@effect(rf"investigate {_TIMES} times")  # (wave 19F: each time is its own investigation, 701.16a: one Clue, one event)
def _investigate_times(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    return [_repeat(m["n"]), *_investigate(m)[0]], None


@effect(r"investigate that many times")  # -- triggers (wave 19B) -- 701.16a: one Clue each time, as many times as the event's amount
def _investigate_many(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    type_line, text = PREDEFINED_TOKENS["Clue"]
    return [{"do": "create_token", "who": "you", "n": {"event_amount": 1},
             "token": {"name": "Clue", "power": None, "toughness": None, "colors": [], "type_line": type_line, "text": text}}], None


@effect(r"investigate twice")  # -- trigger tail (wave 15B) -- 701.16a: investigating twice makes two Clues
def _investigate_twice(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    return [{**_investigate(m)[0][0], "n": 2}], None


# -- life lost (wave 8B) -- "Investigate for each opponent who lost life this turn." (Teysa): one Clue per counted thing
# (701.16a: investigating is creating a Clue token; the count is worked out as the instruction is carried out, 608.2h)
@effect(r"investigate (?:once )?for each (?P<what>.+)")
def _investigate_each(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    from app.rules import sized_damage, values

    n = values.parse_count(m["what"])
    if n is None or sized_damage.has_per_player(n):
        raise _NoMatch
    return [{**_investigate(m)[0][0], "n": n}], None


def _x_amount(xdef: str | None) -> Any:
    """-- X sized by a count (wave 4K) -- X as a cost announced it (107.3a), or as "where X is …" defines it (107.3c)."""
    if xdef is None:
        return {"x": 1}
    from app.rules import language

    v = language.x_definition(xdef)
    if v is None:
        raise _NoMatch
    return v


@effect(r"(?P<verb>scry|surveil) X(?:, where X is (?P<xdef>[^\"]+))?")
def _scry_x(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    return [{"do": m["verb"], "who": "you", "n": _x_amount(m["xdef"])}], None  # (wave 4K: 701.22, 701.25)


@effect(r"(?P<src>~|it) explores, then (?:it|~) explores again")
def _explore_twice(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    return [{"do": "explore", **_it_source(m["src"])}, {"do": "explore", **_it_source(m["src"])}], None  # -- triggers (wave 17D) -- 701.44a twice


@effect(rf"(?P<src>~|it) explores (?:{_TIMES} times|(?P<twice>twice))")
def _explore_times(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    return [_repeat("two" if m["twice"] else m["n"]), {"do": "explore", **_it_source(m["src"])}], None  # (wave 19F)


@effect(r"(?P<src>~|it|target creature you control) explores")
def _explore(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    if m["src"] == "target creature you control":  # -- trigger tail (wave 16C) -- 701.44a: the creature explores (you control it)
        return [{"do": "explore", "who": "target"}], "creature_you_control"
    return [{"do": "explore", **_it_source(m["src"])}], None


# -- merged permanents (wave 18D) -- 701.42a: "exile them, then meld them into [name]" (app/rules/merged.py; the condition names the partner)
@effect(r"exile them, then meld them into meldname:(?P<r>[0-9a-f]+)")
def _meld(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    from app.rules import merged

    return [{"do": "meld", "who": "self", "result": merged.name_of(m["r"])}], None


@effect(r"sacrifice (?P<who>~|it)")
def _sacrifice_self(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    return [{"do": "sacrifice", "who": _self_or_it(m["who"])}], None


@effect(r"sacrifice ~ unless you pay (?P<cost>(?:\{{[^}}]+\}})+)")
def _pay_or_sacrifice(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    return [{"do": "pay_or_sacrifice", "cost": m["cost"]}], None


@effect(r"sacrifice ~ unless you pay its mana cost")  # -- cost alt (wave 16F) -- (effects.pay_or_sacrifice reads the printed cost)
def _pay_mana_cost_or_sacrifice(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    return [{"do": "pay_or_sacrifice", "cost": "mana_cost"}], None


@effect(r"(?:it|they) can't be regenerated")
def _no_regeneration(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    return [{"do": "no_regen"}], None  # the destruction of this spell/ability ignores regeneration shields


@effect(r"(?P<sel>{SEL}) can't be regenerated this turn")  # -- can't regenerate (wave 19E) -- 701.19c
def _no_regeneration_turn(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    return [{"do": "no_regen_turn", "who": "target"}], SELECTORS[m["sel"]]


@effect(r"regenerate (?P<who>~|it|target creature|target creature you control|enchanted creature|equipped creature)")
def _regenerate(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    if m["who"] in ("enchanted creature", "equipped creature"):  # -- attached events (wave 4L) -- (701.19a)
        return [{"do": "regenerate", "who": "host"}], None
    if m["who"] in ("~", "it"):
        return [{"do": "regenerate", "who": _self_or_it(m["who"])}], None
    return [{"do": "regenerate", "who": "target"}], SELECTORS[m["who"]]


# -- static wordings (wave 6E) -- "Creatures target player controls get +2/+0 until end of turn." (How to Start a Riot,
# Arms of Hadar): the creatures that player controls as it resolves (608.2c), each until end of turn (611.2c: locked in)
@effect(r"creatures target (?P<pl>player|opponent) controls get (?P<p>[+−-]\d+)/(?P<t>[+−-]\d+) until end of turn")
def _pump_their_team(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    creatures = 'sel:{"types":["Creature"]}'
    return [{"do": "pump", "who": f"controlled:target|{creatures}", "p": _signed(m["p"]), "t": _signed(m["t"])}], \
        SELECTORS[f"target {m['pl']}"]


# -- untap restrictions (wave 13E) -- "Tap all creatures target player controls." (Sleep, Kiora Bests the Sea God): the
# permanents that player controls as it resolves (608.2c)
@effect(r"(?P<v>tap|untap|destroy|exile) all (?P<what>creatures|nonland permanents|lands|artifacts|permanents) target (?P<pl>player|opponent) controls")  # (wave 19C: destroy, exile)
def _tap_their_all(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    from app.rules import selectors

    sel = selectors.parse(m["what"])
    if sel is None:
        raise _NoMatch
    return [{"do": m["v"], "who": f"controlled:target|{sel.key()}"}], SELECTORS[f"target {m['pl']}"]


# -- counters sweep (wave 19D) -- "Put a -1/-1 counter on each creature target player controls." (Contagion Engine, Meadowboon): the
# creatures that player controls as it resolves (608.2c), the same group form as the tap above
@effect(r"put {N} (?P<k>\+1/\+1|-1/-1|[a-z]+) counters? on each (?P<what>creature|artifact|land|permanent) target (?P<pl>player|opponent) controls")
def _counters_their_all(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    from app.rules import selectors

    sel = selectors.parse(m["what"])
    if sel is None or m["k"] in UNMODELED_COUNTERS:
        raise _NoMatch
    return [{"do": "add_counters", "who": f"controlled:target|{sel.key()}", "kind": m["k"], "n": num(m["n"])}], SELECTORS[f"target {m['pl']}"]


# -- static wordings (wave 6E) -- "Regenerate each creature you control." (Golgari Charm, Wrap in Vigor): a shield on each
# object of the group as the effect resolves (701.19a; 608.2c: the group is read then)
@effect(r"regenerate (?:each|all) (?P<what>[a-z][a-z ]*?)")
def _regenerate_group(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    key = _selector_key(m["what"])
    if key is None:
        raise _NoMatch
    return [{"do": "regenerate", "who": key}], None


SEARCH_FILTERS = {"basic land card": "basic_land", "land card": "land", "creature card": "creature", "card": "any",
                  "artifact card": "artifact", "enchantment card": "enchantment", "instant or sorcery card": "instant_or_sorcery"}


@effect(r"search your library for an? (?P<what>basic land card|land card|creature card|artifact card|enchantment card|instant or sorcery card|card), (?:reveal it, )?put (?:it|that card) (?P<to>into your hand|onto the battlefield tapped|onto the battlefield), then shuffle")
def _tutor(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    to = {"into your hand": "hand", "onto the battlefield tapped": "battlefield_tapped", "onto the battlefield": "battlefield"}[m["to"]]
    return [{"do": "search", "who": "you", "filter": SEARCH_FILTERS[m["what"]], "to": to,
             "reveal": "reveal it" in m.group(0)}], None


@effect(r"(?:then )?each player who searched their library this way shuffles")
def _searchers_shuffle(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    return [{"do": "searchers_shuffle"}], None  # (joined to the search before it: _gy_shuffle; alone it stays manual)


@effect(r"tap any number of untapped (?P<sel>.+?) you control")
def _tap_choice(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    """-- "this way" outcomes (wave 4A) -- "Tap any number of untapped creatures you control." (a choice of 0 or more,
    not a target: this_way.tap_choice), read for what "… tapped this way" counts."""
    from app.rules import selectors

    sel = selectors.parse(f"untapped {m['sel']} you control")
    if sel is None or sel.player is not None or sel.zones != ("battlefield",):
        raise _NoMatch
    return [{"do": "tap_choice", "sel": sel.key()}], None


@effect(r"you become the monarch")
def _monarch(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    return [{"do": "monarch", "who": "you"}], None


@effect(r"draw {N} cards?, then discard {M} cards?")
def _loot(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    return [{"do": "draw", "who": "you", "n": num(m["n"])}, {"do": "discard", "who": "you", "n": num(m["m"])}], None


# -- keyword actions (CR 701; app/rules/keyword_actions.py) and token wording (app/rules/token_grammar.py) --
def _first(fn):  # type: ignore[no-untyped-def]
    """The template just registered is tried before every earlier one: the older create-token
    templates above reject (rather than decline) wordings they half-understand — "with prowess",
    a quoted triggered ability — so the general token grammar must see the sentence first."""
    EFFECTS.insert(0, EFFECTS.pop())
    return fn


@_first
@effect(r"create (?:\d+|a|an|one|two|three|four|five|six|seven|eight|nine|ten|x|X|twice X|half X) (?:tapped )?"  # (half/twice, X/X: wave 4K)
        r"(?:(?:(?:\d+|X)/(?:\d+|X) )?(?:colorless|(?:white|blue|black|red|green)(?:(?:,)? (?:and )?(?:white|blue|black|red|green))*) "
        r"[A-Z][A-Za-z'\-]*(?: [A-Z][A-Za-z'\-]*)* (?:enchantment )?(?:artifact )?(?:land )?creature tokens?|[A-Z][a-z]+ tokens?)"
        r"(?: named [A-Z][A-Za-z'\-]*(?: [A-Z][A-Za-z'\-]*)*)?(?: with (?:(?!, then )[^\"])*(?:\"[^\"]+\")?)?"
        r"(?: that(?:'s| are) (?:tapped and )?attacking)?(?: for each [^\"]+|, where [xX] is [^\"]+|, rounded (?:up|down))?")
def _create_tokens(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    """"Create [N] [tapped] [P/T colors Subtypes [artifact] creature | Predefined] token(s) [named …]
    [with …] [that's tapped and attacking] [for each … | , where X is …]" (701.7, 111.10, 508.4).
    The "with …" part never crosses ", then " ("create a 1/2 green Spider creature token with
    reach, then each opponent loses 1 life …" is two instructions, which _clause splits; a match
    here that the grammar then rejected used to fail the whole ability)."""
    from app.rules import token_grammar

    found = token_grammar.parse(m.group(0))
    if found is None:
        raise _NoMatch
    return found, None


# -- token & pump wordings (wave 6C) -- the token grammar's newer forms (app/rules/token_grammar.py): "For each …, create
# …", "Create Voja, a legendary 2/2 …", "… named Kobolds of Kher Keep", "… with flying named Wasp", "… that's all
# colors", "Create thirteen …" (never a copy, nor an instruction joined to another one)
@_first
@effect(r"(?!.*\b(?:cop(?:y|ies)|then|unless|instead|blocking|attached|equal|attacking that|that player)\b)"
        r"(?:(?:for each [^,\"]+, )?create (?:[A-Z][^\"]*?, an? legendary .+|(?:eleven|twelve|thirteen|fourteen|fifteen|"
        r"sixteen|seventeen|eighteen|nineteen|twenty) .+|.+ named .+|.+ that's (?:all colors|colorless|white|blue|black|red|"
        r"green)(?:[ ,].+)?)|for each [^,\"]+, create .+)")
def _create_tokens_6c(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    from app.rules import token_grammar

    found = token_grammar.parse(m.group(0))
    if found is None:
        raise _NoMatch
    return found, None


@_first
@effect(r"(?:it has|they have) \"(?P<quoted>[^\"]+)\"")
def _token_has_ability(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    """'It has "…"' after a create sentence: the quoted ability, if the engine carries it out."""
    from app.rules import token_grammar

    text = token_grammar.token_text(m["quoted"])
    if text is None:
        raise _NoMatch
    return [{"do": "token_text", "text": text}], None


@effect(r"amass (?P<sub>[A-Z][a-z]+) (?P<n>\d+|X)")
def _amass(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    """701.47a: "amass [Subtype]s N" (the plural names the creature type the Army gets)."""
    from app.rules.creature_types import CREATURE_TYPES
    from app.rules.protection import _PLURALS

    word = m["sub"]
    sub = _PLURALS.get(word.lower()) or (word[:-1] if word.endswith("s") else word)
    if sub not in CREATURE_TYPES:
        raise _NoMatch
    return [{"do": "amass", "sub": sub, "n": {"x": 1} if m["n"] == "X" else int(m["n"])}], None


@effect(r"(?P<who>~|it|he|she|{SEL}) connives(?: {N})?")
def _connive(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    """701.50a/d: "~ connives", "it connives", "target creature you control connives [N]"."""
    n = num(m["n"]) if m["n"] else 1
    if m["who"] == "~":
        return [{"do": "connive", "who": "self", "n": n}], None
    if m["who"] in ("it", "he", "she"):
        return [{"do": "connive", "who": "it", "n": n}], None
    if SELECTORS[m["who"]] not in ("creature", "creature_you_control", "creature_opponent_controls"):
        raise _NoMatch
    return [{"do": "connive", "who": "target", "n": n}], SELECTORS[m["who"]]


@effect(r"monstrosity {N}")
def _monstrosity(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    return [{"do": "monstrosity", "n": num(m["n"])}], None  # 701.37a


@effect(r"monstrosity X")
def _monstrosity_x(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    return [{"do": "monstrosity", "n": {"x": 1}}], None  # -- X sized by a count (wave 19F) -- X announced as it's activated (107.3a)


@effect(r"~'s level becomes {N}")
def _class_level(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    return [{"do": "class_level", "n": num(m["n"])}], None  # 716.2a: the Class's level becomes N


@effect(r"bolster {N}")
def _bolster(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    return [{"do": "bolster", "n": num(m["n"])}], None  # 701.39a


@effect(r"support {N}")
def _support(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    """701.41a: "Put a +1/+1 counter on each of up to N other target creatures." ("other" than the
    source: for an instant or sorcery, which is never on the battlefield, that's every creature.)"""
    other_creature = 'sel:{"other":true,"types":["Creature"]}'  # selectors.parse("other creature").key()
    return [{"do": "add_counters", "who": "target", "kind": "+1/+1", "n": 1}], {"what": other_creature, "min": 0, "max": num(m["n"])}


class _NoMatch(Exception):
    """A template that matched the shape but not the details (e.g. an unknown keyword)."""


def _lower_first(s: str) -> str:
    # (-- X sized by a count (wave 19F) -- "X target creatures can't block this turn": the X of the group stays a capital)
    return s[:1].lower() + s[1:] if s[:1].isupper() and not s.startswith(("~", "X target", "X blocked")) else s


def _one_clause(text: str) -> tuple[list[dict[str, Any]], Any] | None:
    """One instruction: a literal template, else the generic grammar (app/rules/language.py)."""
    # -- combat (wave 5C) -- extra combat phases, "attacks this turn if able", attacking tokens
    from app.rules import combat_rules

    if (combat_found := combat_rules.clause(text)) is not None:
        return combat_found
    # -- token & pump wordings (wave 6C) -- "create a Monster Role token attached to it"
    from app.rules import roles

    if (role_found := roles.clause(text)) is not None:
        return role_found
    # (wave 6C) "[you may] have target creature get -1/-1 until end of turn": the same instruction as "target creature
    # gets -1/-1 until end of turn" (the "you may" is read before this)
    had = re.fullmatch(r"have (?P<o>target [^,\"]+?) (?P<v>get|gain) (?P<rest>[^\"]+ until end of turn)", text)
    if had is not None:
        rest = re.sub(r" and (get|gain) ", r" and \1s ", had["rest"])
        return _one_clause(f"{had['o']} {had['v']}s {rest}")
    from app.rules import language  # the generic grammar (a leaf module)

    for pattern, build in EFFECTS:
        m = pattern.match(text)
        if m:
            try:
                found, sel = build(m)
            except _NoMatch:
                return None
            if found and found[0]["do"] == "token_text":
                return None
            return found, sel
    from app.rules import permissions  # cast / play permissions ("you may play that card this turn")

    granted = permissions.parse_clause(text)
    if granted is not None:
        return granted
    found_sentence = language.parse_sentence(text)
    # -- attached events (wave 4L) -- "you untap all lands you control" / "you create a Treasure token": an
    # instruction with "you" spelled out is the imperative one (the controller does it either way), read as such
    # when it isn't read with the subject ("… that player discards a card and you untap all lands you control")
    if found_sentence is None and (m := _YOU_IMPERATIVE.match(text)) is not None:
        return _one_clause(text[m.end():])
    return found_sentence


# -- attached events (wave 4L) --
_YOU_IMPERATIVE = re.compile(r"you (?=(?:create|untap|tap|put|return|exile|destroy|scry|surveil|proliferate|"
                             r"investigate|sacrifice|discard|mill|shuffle)\b)")


# -- static_other sweep (wave 16B) -- "Each player discards all the cards in their hand, then draws that many cards [minus one]." /
# "Discard any number of cards, then draw that many cards plus one." / "… then creates that many 2/2 black Zombie creature tokens.":
# "that many" is the cards the discard before it put into the graveyard (701.9a), for each player their own (108.4a: a card's owner)
_THAT_MANY = re.compile(r"^(?P<s>(?:target player|each player|each opponent|that player|defending player) )?(?P<v>draws?|creates?) "
                        r"that many (?P<what>cards|[^,.]+? tokens)(?: (?P<d>plus|minus) one)?$")


def _that_many(left: tuple[list[dict[str, Any]], Any], text: str) -> tuple[list[dict[str, Any]], Any] | None:
    m = _THAT_MANY.match(text)
    first = left[0][0] if len(left[0]) == 1 else {}
    kind = "discarded" if first.get("do") == "discard" and (first.get("all") or first.get("upto")) else \
        "sacrificed" if first.get("do") == "sacrifice_choice" and first.get("upto") else \
        "shuffled" if first.get("do") == "shuffle_library" and first.get("zones") == ["hand"] else None
    if m is None or kind is None:
        return None
    s, plural = m["s"] or "", bool(m["s"]) and m["s"].startswith("each")
    verb = m["v"] if s else m["v"].rstrip("s")
    if verb.startswith("draw"):
        right = _clause(f"{s}{verb} a card for each {'permanent sacrificed' if kind == 'sacrificed' else 'card discarded'} this way")
        if right is None or len(right[0]) != 1 or right[0][0].get("do") != "draw":
            return None
        if kind == "shuffled":  # (the shuffle is no introducer of "it": its binding is named here)
            first["as"] = "shuffled"
        n = {**right[0][0]["n"], "this_way": kind, **({"ref_count": "shuffled"} if kind == "shuffled" else {}), **({"delta": 1 if m["d"] == "plus" else -1} if m["d"] else {}),
             **({"each_owner": True} if plural else {})}
        return [{**right[0][0], "n": n}], right[1]
    if m["d"] or m["what"] == "cards":
        return None
    right = _clause(f"{s}{verb} a {m['what'][:-1]}")
    if right is None or len(right[0]) != 1 or right[0][0].get("do") != "create_token" or right[0][0].get("n") != 1:
        return None
    return [{**right[0][0], "per_controller": {"this_way": kind, "of": None}}], right[1]


def _clause(text: str, may_ok: bool = False) -> tuple[list[dict[str, Any]], Any] | None:
    """An instruction, or two joined by ", then" / "and" ("Scry 1, then draw a card.", "You draw
    two cards and you lose 2 life."): each half must be understood. Each "target" word is its
    own target group (115.3); the halves' groups are numbered in order."""
    found = _one_clause(text)
    if found is not None:
        return found
    # -- token & pump wordings (wave 6C) -- "This creature gets +1/+0 until end of turn and deals 1 damage to you." (one
    # subject, two instructions in order, 608.2c): the pump (or grant), then the source's damage
    selfdmg = re.fullmatch(r"(?P<s>~|this creature) (?P<a>(?:gets|gains) [^\"]+? until end of turn) and deals (?P<d>.+)", text)
    if selfdmg is not None:
        left, right = _one_clause(f"{selfdmg['s']} {selfdmg['a']}"), _one_clause(f"~ deals {selfdmg['d']}")
        if left is not None and right is not None and left[1] is None and right[1] is None:
            return left[0] + right[0], None
    # -- grammar (wave 11C) -- "Put a +1/+1 counter on ~ and a +1/+1 counter on each Golem you control." (two instructions of
    # one sentence, in order: 608.2c)
    text = re.sub(r"^(Put an? [^,.]+? counters? on ~) and prevent all damage that would be dealt to it this turn$",
                  r"\1 and prevent all damage that would be dealt to ~ this turn", text)  # ("it" is the one object named)
    twin = re.fullmatch(r"(?P<p>[Pp]ut) (?P<a>an? .+? counters?) on (?P<x>(?:(?!\bcounters?\b).)+?) and (?P<b>an? .+? counters?) on "
                        r"(?P<y>.+)", text)
    if twin is not None:
        text = f"{twin['p']} {twin['a']} on {twin['x']}, then put {twin['b']} on {twin['y']}"
    # -- trigger tail (wave 15B) -- "You draw three cards, gain 6 life, and create three Bats." (a serial list of instructions, in
    # order: 608.2c): read as the same instructions joined by "and"; each part must still be understood on its own
    if (serial := re.fullmatch(r"([^,]+(?:, [^,]+)+), and ([^,]+)", text) or re.fullmatch(
            r"((?![^,]*\b(?:search|reveal|look)\b)[^,]+(?:, (?!then\b)[^,]+)+), then ((?:investigate|surveil|scry|draw|gain|mill|explore)\b[^,]*)", text)) is not None:
        # (wave 16D: "Gain 2 life, surveil 2, then investigate"; a search's ", then shuffle" is no list)
        text = serial[1].replace(", ", " and ") + " and " + serial[2]
    # -- static_other sweep (wave 16B) -- "You draw two cards, lose 2 life, then mill two cards." is three instructions in order (608.2c)
    text = re.sub(r"^(?P<a>(?:you )?(?:gain|lose|draw|mill|scry|surveil)\b[^,.]*), (?P<b>(?:draw|lose|gain|mill|scry|surveil|investigate)\b[^,.]*), then ",
                  r"\g<a>, then \g<b>, then ", text)
    for joiner in (r", then ", r" and (?=(?:you|target|each|~|it|that player|draw|lose|gain|put|return|exile|"
                                 r"destroy|tap|untap|create|sacrifice|discard|mill|scry|surveil|get|goad|"
                                 r"remove|add|investigate|prevent|amass|proliferate|manifest|transform)\b)"):  # (wave 20F: transform)  # (remove: wave 6D, "untap it and remove it from combat")
        parts = re.split(joiner, text, maxsplit=1)
        if len(parts) != 2:
            continue
        # "Target player draws a card, then discards a card": the right half's subject is the
        # left's (608.2c reads the whole text), not "you"
        subj = re.match(r"^(target player|target opponent|each player|each opponent|each of your opponents|"
                        r"that player) ", parts[0])
        same_target = False
        if subj and re.match(r"^(?:draws|discards|mills|loses|gains|sacrifices|shuffles|puts|reveals|exiles|"
                             r"returns|creates|searches|scry|surveil|gets)\b", parts[1]):
            parts[1] = f"{subj[1]} {parts[1]}"
            same_target = subj[1].startswith("target")  # (one word "target": the same target)
        left = _clause(parts[0], may_ok)
        right = _that_many(left, parts[1]) if left is not None else None  # -- static_other sweep (wave 16B) --
        right = right or _clause(parts[1], may_ok)
        # -- reanimation (wave 20C) -- "You gain 3 life and you may return up to one target creature card …" (608.2c): only the second
        # instruction is optional, asked as the resolution reaches it (unless_pays.may_rest: the rest of the ability, so it must end the
        # sentence and, in parse_effects, the ability)
        if right is None and may_ok and parts[1].startswith("you may ") and (inner := _one_clause(parts[1][len("you may "):])) is not None:
            right = ([{"do": "may_rest"}, *inner[0]], inner[1])
        if left is None or right is None or any(e.get("do") == "may_rest" for e in left[0]):
            continue
        lgroups, rgroups = _as_groups(left[1]), _as_groups(right[1])
        if same_target:
            if not lgroups or len(rgroups) != 1:
                continue
            return left[0] + _renumber(right[0], [0]), left[1]
        groups = lgroups + rgroups
        index = list(range(len(lgroups), len(groups)))
        return _renumber(left[0], list(range(len(lgroups)))) + _renumber(right[0], index), groups or None
    return None


def parse_effects(body: str, it: str | None = None, *, event_player: bool = False) -> tuple[list[dict[str, Any]], Any, bool] | None:
    """One sentence (or two joined by ". ") of effects → (effects, targets, optional). Targets:
    None, a selector key (one "target [something]"), or a list of target groups (see
    target_fields). ``it``: what the pronoun "it" means when no target precedes it (resolve_it);
    ``event_player``: the trigger event names a player ("that player" may mean them)."""
    from app.rules import refused_zones  # -- refused zones/sized (wave 3R4) -- Gifts piles (a leaf module)

    if (gifts := refused_zones.gifts_ability(body)) is not None:
        return gifts
    # -- voting (wave 18C) -- "For each opponent, you create a 1/1 white Human Soldier creature token." (Vault 11): one token for each
    # opponent, the token grammar's "… for each opponent"
    body = re.sub(r"(^|\. )For each opponent, you (create [^.,]+? tokens?)\.", lambda m: f"{m[1]}{m[2][:1].upper()}{m[2][1:]} for each opponent.", body)
    from app.rules import (
        friend_foe,  # -- friend or foe (wave 18C) -- "For each player, choose friend or foe. Each friend …"
        tempting,  # -- tempting offers (wave 18C) -- "Each opponent may …. For each opponent who does, you …"
    )

    if (sides := friend_foe.bind(body, lambda t: parse_effects(t, it, event_player=event_player), split_sentences)) is not None:
        return sides

    if (offer := tempting.bind(body, lambda t: parse_effects(t, it, event_player=event_player), split_sentences)) is not None:
        return offer
    from app.rules import voting  # -- voting (wave 18C) -- 701.38 (read before the sentence rewrites below)

    if (vote := voting.split(body)) is not None:
        return voting.bind(vote, lambda t: parse_effects(t, it, event_player=event_player), split_sentences)
    from app.rules import trigger_words  # -- triggers (wave 5D) -- "create a number of … equal to …"

    body = _dice.plain(trigger_words.plain_amounts(_dice.rewrite(body)))  # (rewrite: a results table, wave 16B)
    # -- static_other sweep (wave 16B) -- 701.48a: "Learn." means "You may reveal a Lesson card you own from outside the game and put it
    # into your hand. If you don't, you may discard a card. If you do, draw a card." A game here has no cards outside it (no sideboard is
    # modelled: the decks are the games'), so the reveal never has a Lesson to show and the rest is the rummage
    body = re.sub(r"(^|\. )[Ll]earn\.", r"\1You may discard a card. If you do, draw a card.", body)
    body = _extra_turns.one_sentence(body)  # -- static_other sweep (wave 19A) -- Final Fortune
    # -- tutor (wave 20D) -- the same search spelled as sentences: "Search your library for two cards[ and reveal them]. Put one into your hand
    # and the other into your graveyard. Then shuffle." (Final Parting, Fork in the Road), "… for a white card, …, and a green card. Reveal
    # those cards, put them into your hand, then shuffle." (Conflux), "…. Put those cards into your graveyard, then shuffle.": one search
    # sentence (701.23), read by language._search
    body = re.sub(r"((?i:search) your library for [^.]+?)(?: and (reveal (?:them|it)))?\. ((?:Reveal (?:those cards|them|that card|it), )?"
                  r"[Pp]ut (?:one(?: of them)?|those cards|them|that card|it) [^.]+?)(?:, then shuffle|\. Then shuffle)\b",
                  lambda m: f"{m[1]}, {m[2] + ', ' if m[2] else ''}{m[3][:1].lower()}{m[3][1:]}, then shuffle", body)
    body = re.sub(r"(?i)^(sacrifice (?:~|this \w+)), (search your library for )", r"\1. \2", body)  # (Defense of the Heart: two instructions in order)
    # -- static_other sweep (wave 19A) -- "Choose a creature type. Draw a card for each permanent you control of that type." (Distant
    # Melody): "that type" is the type just chosen, as in "of the chosen type" (app/rules/chosen.py)
    body = re.sub(r"(Choose a creature type\. [^.]*?) of that type\b", r"\1 of the chosen type", body)  # (-- rolling dice, wave 12A -- "that much" after a roll is the result)
    # -- trigger tail (wave 16C) -- "Create a 4/4 … token with flying at the beginning of the next end step." (Rukh Egg): the same delayed
    # trigger (603.7) as the leading wording, which the token grammar reads whole
    body = re.sub(rf"(?i)^(create [^.]+?) (at the beginning of (?:{_delayed.WHEN_RE}))(\.?)$", r"\2, \1\3", body)
    # -- trigger tail (wave 15B) -- "Discard any number of cards, then draw that many cards.": "that many" is the cards discarded
    # this way (701.9a), not a trigger event's amount; "plus one" would be a different (single) draw: not read
    body = re.sub(r"(?i)\b(discard (?:up to \w+|any number of|\w+) cards?)(?:, then |\. (?:then )?)draw that many cards\b(?! plus)",
                  r"\1, then draw a card for each card discarded this way", body)
    # 701.70a: "Recruit" means "Draw a card, then discard a card. If you discarded a nonland card this way, create a 1/1 white
    # Human Soldier creature token." (one card is discarded, so the token is made once for it or not at all)
    body = re.sub(r"(?i)(?:^|(?<=, )|(?<=\. ))(?:you )?recruit(?=[.,]|$)",
                  "draw a card, then discard a card, then create a 1/1 white Human Soldier creature token for each nonland card "
                  "discarded this way", body)
    # -- static_other sweep (wave 17C) -- "The owner of target nonland permanent shuffles it into their library, then draws two cards."
    # (Oblation): the shuffle, then its owner's draw
    body = re.sub(r"(?i)^the owner of (target [^.,]+?) shuffles it into their library, then draws (\w+) cards?\b",
                  r"Shuffle \1 into its owner's library. Its owner draws \2 cards", body)
    # -- static_other sweep (wave 17C) -- 701.16a: "Its controller investigates." is "Its controller creates a Clue token." (Fateful Absence)
    body = re.sub(r"(?i)\b(its controller|that creature's controller|that permanent's controller) investigates\b", r"\1 creates a Clue token", body)
    body = _dice.plain(trigger_words.plain_amounts(body))  # (-- rolling dice, wave 12A -- "that much" after a roll is the result)
    # -- activated sweep (wave 17B) -- "Destroy each artifact, creature, and enchantment with mana value X or less.": "each" is distributive,
    # so the list is any of them and the qualifier is every kind's (Pernicious Deed); "and/or" is the selector grammar's spelling
    body = re.sub(r"(?i)\b(each|all) ((?:(?:artifact|creature|enchantment|land|planeswalker|battle), )+)and "
                  r"((?:artifact|creature|enchantment|land|planeswalker|battle) with mana value\b)", r"\1 \2and/or \3", body)
    from app.rules import per_opponent  # -- per-opponent targets (wave 12C) --

    if (each_opp := per_opponent.parse(body, lambda b: parse_effects(b, it, event_player=event_player))) is not None:
        return each_opp
    found = _parse_effects_checked(body, it, event_player)
    if found is not None and '"target_sel"' in json.dumps(found[0], default=str):
        return None  # (-- static_other sweep (wave 16B) -- a "target …" an amount names that no instruction declared as its target)
    if found is not None and '{"x": 1}' not in json.dumps(found[0]):
        return found
    return _where_x(body, it, event_player) or found  # (X left as a cast X by the sentence grammar: read as the text defines it, if it can be)


def _parse_effects_checked(body: str, it: str | None, event_player: bool) -> tuple[list[dict[str, Any]], Any, bool] | None:
    try:
        # -- top of library (wave 5I) -- "If it's a …, you may reveal it" (private)
        from app.rules import top_library

        return top_library.private_gate(_excess_redirect(_that_players_hand(_attached_host(_gy_shuffle(_life_lost(
            this_way.dealt_to(this_way.excess_dealt(this_way.damage_dealt(_energy_paid(_parse_effects(body, it, event_player))))))),
            it))))  # (damage_dealt: wave 5G; excess_dealt: wave 9B; dealt_to: wave 10C)
    except _NoMatch:
        return None


# -- X defined by text (wave 12C) -- "Each opponent loses X life and you scry X, where X is the number of Zombies you control."
# (107.3c: the text defines X; 608.2h: read as the effect is carried out). The sentence is read with a stand-in number for X, which
# is then swapped for the value; only in amount fields that evaluate values (a target count or a selector bound would not).
_WHERE_X = re.compile(r",? where X is (?P<def>[^.\"]+?)(?=\.(?: |$)|$)")
_X_SENTINEL = 7919
_X_KEYS = frozenset({"n", "p", "t"})


def _where_x(body: str, it: str | None, event_player: bool) -> tuple[list[dict[str, Any]], Any, bool] | None:
    from app.rules import language

    found = list(_WHERE_X.finditer(body))
    if len(found) != 1 or "{X}" in body:
        return None
    m = found[0]
    value = language.x_definition(m["def"])
    start = body.rfind(". ", 0, m.start()) + 2 if ". " in body[: m.start()] else 0
    head, rest = body[start: m.start()], body[:start] + "\0" + body[m.end():]
    # (what the wrappers around the sentence grammar bind afterwards — "this way" counts, the target player's hand — is not read)
    if value is None or re.search(r'"(?:that_player|ref_amount|ref_count)"|"this_way"|"cost:exiled"', json.dumps(value)) or not re.search(r"\bX\b", head) or re.search(r"\bX\b", rest):
        return None
    now = _x_now()
    outer = list(now)
    now[:] = [value, False]  # (-- X sized by a count (wave 19F) -- swapped in by _parse_effects before it binds the pronouns)
    try:
        got = _parse_effects_checked(rest.replace("\0", re.sub(r"\bX\b", str(_X_SENTINEL), head)), it, event_player)
        hit = now[1]
    finally:
        now[:] = outer
    if got is None or str(_X_SENTINEL) in json.dumps(got[1]) or not hit:
        return None
    return got


_X_LOCAL = threading.local()  # (review 19: per thread — games may parse cards concurrently)


def _x_now() -> list[Any]:
    """[value, swapped?] while _where_x parses its stand-in sentence (empty otherwise)."""
    if not hasattr(_X_LOCAL, "v"):
        _X_LOCAL.v = []
    return _X_LOCAL.v


def _swap_x(effects: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """-- X sized by a count (wave 19F) -- the stand-in of _where_x → the value, in amount fields only (a pronoun in the value is
    bound by the resolve_it that follows: "where X is that creature's power", "… the milled card's mana value")."""
    value = _x_now()[0]

    def swap(v: Any, key: str | None) -> Any:
        if isinstance(v, list):
            return [swap(x, key) for x in v]
        if isinstance(v, dict):
            return {k: swap(x, k) for k, x in v.items()}
        if isinstance(v, bool) or v not in (_X_SENTINEL, -_X_SENTINEL):
            return v
        if key not in _X_KEYS or (v < 0 and key == "n"):
            raise _NoMatch
        _x_now()[1] = True
        return value if v > 0 else {"neg": value}

    return swap(effects, None)


_EXCESS = re.compile(r"(?P<trample>if the creature you control has trample, )?excess damage is dealt to that "
                     r"creature's controller instead")


def _excess_redirect(found: tuple[list[dict[str, Any]], Any, bool] | None) -> tuple[list[dict[str, Any]], Any, bool] | None:
    """-- refused zones/sized (wave 3R4) -- "[If the creature you control has trample,] excess damage is dealt to that
    creature's controller instead" (Flame Spill, Ram Through): the damage instruction right before it, to one target
    creature, is split as it is dealt (120.4a: before prevention and replacement, lethal damage counting what is
    already marked and the source's deathtouch). The trample condition reads the creature dealing the damage."""
    if found is None or not any(e.get("do") == "excess_redirect" for e in found[0]):
        return found
    effects: list[dict[str, Any]] = []
    for e in found[0]:
        if e.get("do") != "excess_redirect":
            effects.append(e)
            continue
        prev = effects[-1] if effects else None
        if prev is None or prev.get("do") != "damage" or prev.get("with_next") or prev.get("excess") or \
                not (prev.get("who") == "target" or str(prev.get("who")).startswith("target:")) or str(prev.get("src", "")).startswith("each:"):
            return None
        if e["if_trample"] and not str(prev.get("src") or "").startswith("target"):
            return None  # ("the creature you control": the creature dealing the damage, a target)
        effects[-1] = {**prev, "excess": "trample" if e["if_trample"] else "always"}
    return effects, found[1], found[2]


def _that_players_hand(found: tuple[list[dict[str, Any]], Any, bool] | None) -> tuple[list[dict[str, Any]], Any, bool] | None:
    """-- refused zones/sized (wave 3R4) -- "the number of cards in that player's / their hand": the target player's
    when the ability targets one player (and names no other), else the player the trigger was about — only when the
    ability also says "that player" for its recipient (``event_player``: _event_refs_ok checks the trigger has one)."""
    text = json.dumps(found[0]) if found is not None else ""
    marker = '{"hand": "that_player"}'
    if found is None or marker not in text:
        return found
    if (found[1] in ("player", "opponent") or str(found[1]).startswith("opponent_as:")) and '"event_player"' not in text:
        bound = "target"
    elif found[1] is None and any(e.get("who") == "event_player" for e in found[0]):
        bound = "event"
    else:
        return None
    return json.loads(text.replace(marker, '{"hand": "' + bound + '"}')), found[1], found[2]


def _attached_host(found: tuple[list[dict[str, Any]], Any, bool] | None, it: str | None,
                   ) -> tuple[list[dict[str, Any]], Any, bool] | None:
    """-- refused zones/sized (wave 3R4) -- "… return this card from your graveyard to the battlefield attached to
    that creature": the creature the trigger was about (a creature entering), when nothing earlier in the ability
    introduced another object; any other reading stays manual."""
    if found is None or not any(e.get("host") == "that_creature" for e in found[0]):
        return found
    if it != "event":
        return None
    out: list[dict[str, Any]] = []
    for e in found[0]:
        if e.get("host") == "that_creature":
            if any(x.get("do") not in ("only_if", "optional_payment") for x in out):
                return None
            e = {**e, "host": "event"}
        out.append(e)
    return out, found[1], found[2]


def _gy_shuffle(found: tuple[list[dict[str, Any]], Any, bool] | None) -> tuple[list[dict[str, Any]], Any, bool] | None:
    """-- refused zones/sized (wave 3R4) -- "If you search your library this way, shuffle." belongs to the
    "search your library and/or graveyard" right before it (language._search_gy); anywhere else: manual."""
    if found is None or not any(e.get("do") in ("gy_search_shuffle", "searchers_shuffle") for e in found[0]):
        return found
    effects: list[dict[str, Any]] = []
    for e in found[0]:
        if e.get("do") == "searchers_shuffle":  # -- other players' choices (wave 12D) -- "Then each player who searched their
            prev = effects[-1] if effects else None  # library this way shuffles." (701.24): after "Each opponent may search …"
            if prev is None or prev.get("do") != "search" or prev.get("who") not in ("each_opponent", "each_player") \
                    or prev.get("shuffle", True):
                return None
            effects[-1] = {**prev, "shuffle": True}
            continue
        if e.get("do") != "gy_search_shuffle":
            effects.append(e)
            continue
        prev = effects[-1] if effects else None
        if prev is None or prev.get("do") != "search" or not prev.get("graveyard") or prev.get("shuffle", True):
            return None
        effects[-1] = {**prev, "shuffle": True}
    return effects, found[1], found[2]


def _life_lost(found: tuple[list[dict[str, Any]], Any, bool] | None) -> tuple[list[dict[str, Any]], Any, bool] | None:
    """-- refused zones/sized (wave 3R4) -- "Each opponent loses 3 life. You gain life equal to the life
    lost this way": the total the instruction just before actually took (119.3, 608.2c). Anything
    else in between, or no such instruction, leaves the ability manual."""
    if found is None or '"life_lost"' not in json.dumps(found[0]):
        return found
    effects = found[0]
    for i, e in enumerate(effects):
        if '"life_lost"' not in json.dumps(e):
            continue
        prev = effects[i - 1] if i else None
        if prev is None or prev.get("do") != "lose_life" or e.get("do") != "gain_life" or prev.get("bind"):
            return None
        effects = [*effects[:i - 1], {**prev, "bind": "life_lost"}, *effects[i:]]
    return effects, found[1], found[2]


def _energy_paid(found: tuple[list[dict[str, Any]], Any, bool] | None) -> tuple[list[dict[str, Any]], Any, bool] | None:
    """-- counters & designations (wave 3E) -- After "you may pay any amount of {E}", "that much" is the
    amount paid (608.2c: the text read as a whole), not a trigger event's."""
    if found is None or not any(e.get("do") == "pay_energy_any" for e in found[0]):
        return found
    at = next(i for i, e in enumerate(found[0]) if e.get("do") == "pay_energy_any")
    paid = json.loads(json.dumps(found[0][at + 1:]).replace('{"event_amount": 1}', '{"ref_amount": "energy_paid"}'))
    return [*found[0][:at + 1], *paid], found[1], found[2]


# -- may pay or else (wave 4J) -- the whole ability: one payment, one consequence (no "you may" in it)
_MAY_PAY_ELSE = re.compile(r"^(?:[Tt]hat player|[Tt]hey) may pay (?P<cost>(?:\{[^}]+\})+)\. If (?:the player|that player|they) "
                           r"(?:doesn't|don't), (?:you (?=create ))?(?P<rest>(?![^.]*\bmay\b)[^.]+)\.$")


def _parse_effects(body: str, it: str | None, event_player: bool = False) -> tuple[list[dict[str, Any]], Any, bool] | None:
    body = body.strip()
    if not body.endswith(".") and not body.endswith('."'):
        return None
    if it == "self":  # -- triggers (wave 17D) -- "draw a card for each Aura and Equipment attached to it": "it" is the source (Wyleth)
        body = re.sub(r"\b(Auras?|Equipment) attached to it\b", r"\1 attached to ~", body)
    # -- review (wave 7R) -- "Create a tapped 2/2 black Zombie creature token and exile that card." (Wight): "that card" is
    # the card the trigger is about, never the token just created (a token is no card), and the pronoun reader would bind it
    # to the token. The two instructions don't depend on each other: read as "Exile that card. Create …" (the trigger's
    # card); any other verb or shape is not read
    if (swapped := re.fullmatch(r"(?P<make>[Cc]reates? [^.]*?\btokens?\b[^.]*?) and exile (?P<that>that card|the card)\.", body)):
        body = f"Exile {swapped['that']}. {swapped['make']}."
    elif re.search(r"\bcreates? [^.]*\btokens?\b[^.]* and (?:exile|return|put|destroy|sacrifice|tap|untap) (?:that|the) cards?\b",
                 body, re.IGNORECASE):
        return None
    # -- static grants (wave 15A) -- "Discard all the cards in your hand, then draw that many cards." (Tolarian Winds): one player's
    # hand, so "that many" is the number of cards discarded (701.9a), which the "this way" count already reads
    body = re.sub(r"(?P<d>^|\. )(?P<h>(?:[Dd]iscard|[Tt]arget player discards) (?:(?:your|their) hand|all the cards in (?:your|their) hand)), then "
                  r"(?P<v>draw|(?:that player )?draws) that many cards\.",
                  lambda m: f"{m['d']}{m['h']}, then {m['v']} a card for each card discarded this way.", body)
    from app.rules import radiance  # -- radiance (wave 9C) --

    if (rad := radiance.split(body)) is not None:
        return radiance.bind(_parse_effects(rad[0], it, event_player), rad[1], rad[2])  # (wave 11D: or "the same name")
    from app.rules import (
        pump_each,  # -- ability words (wave 9C) -- "Until end of turn, … gets +1/+1 for each …"
    )

    body = pump_each.rewrite(body)
    # -- ability words (wave 20C) -- "… if this is the first time this ability has resolved this turn. If it's the second time, …" (Omnath,
    # Vito): a bare "it's the second time" means this same ability's resolutions, once the sentence before has said so
    if re.search(r"\bthis is the \w+ time this ability has resolved this turn\b", body):
        body = re.sub(r"\b([Ii]f) it's the (first|second|third|fourth|fifth) time\b", r"\1 this is the \2 time this ability has resolved this turn", body)
    # -- reanimation (wave 20C) -- "Put a +1/+1 counter on each of those creatures." / "Each of those creatures gains haste": the
    # objects the sentence before named, as "each of them" / "those creatures" read them (608.2c)
    body = re.sub(r"(\b[Pp]ut [^.,]+? counters? on) each of those (?:creatures|permanents|cards|artifacts|lands|enchantments)\b", r"\1 each of them", body)
    body = re.sub(r"(^|\. )Each of those (creatures|permanents|cards|artifacts|lands|enchantments) (gains|gets|loses) ",
                  lambda m: f"{m[1]}Those {m[2]} {m[3][:-1]} ", body)
    from app.rules import combat_rules as _combat_rules  # -- keywords (wave 15E) -- myriad's two sentences

    body = _combat_rules.merge_myriad(body)
    from app.rules import kinship  # -- kinship (wave 9C) --

    if (kin := kinship.split(body)) is not None:
        return kinship.bind(_parse_effects(kin, it, event_player))
    from app.rules import parley  # -- parley (wave 9C) --

    if (parts := parley.split(body)) is not None:
        return parley.bind(parts, lambda t: _parse_effects(t, it, event_player))
    optional = False
    effects: list[dict[str, Any]] = []
    groups: list[dict[str, Any]] = []
    start = 0
    # -- may pay or else (wave 4J) -- "That player may pay {2}. If the player doesn't, you create a Treasure token."
    # (Smothering Tithe) is 118.12a's own reading of "[Effect] unless that player pays {2}": read as that
    body = _MAY_PAY_ELSE.sub(lambda m: f"{m['rest'][:1].upper()}{m['rest'][1:]} unless that player pays {m['cost']}.", body)
    from app.rules import recursion as _recursion  # -- recursion & tutors (wave 4M) --

    body = _recursion.join_sized_search(body)
    from app.rules import name_search  # -- name search (wave 11D) --

    body = name_search.rewrite(body)
    from app.rules import looking as _looking
    from app.rules import permissions as _permissions  # -- hidden exile (wave 18A) --

    body = _permissions.join_exile_play(body)
    body = _chars.join_spec(body)  # -- hidden exile (wave 18A) --
    body = _looking.join_down_piles(body)
    # -- activated wordings (wave 15D) -- "Choose a creature type [other than Wall]. Each creature you control becomes that type until
    # end of turn." is one choice made as it resolves (608.2d): read as "… becomes the creature type [other than Wall] of your choice …"
    body = re.sub(r"([^.]+?) (gets [+−-]\d+/[+−-]\d+) and (becomes the color of your choice) until end of turn\.",
                  r"\1 \2 until end of turn. \1 \3 until end of turn.", body)  # (Wild Mongrel: two instructions in order)
    body = re.sub(r"Choose a creature type( other than [A-Z][a-z]+)?\. ([^.]+?) becomes? that type until end of turn\.",
                  r"\2 becomes the creature type\1 of your choice until end of turn.", body)
    body = re.sub(r"(chooses [^.]*? they control)\. Destroy the rest\.", r"\1, then the rest are destroyed.", body)  # (wave 11D)
    # -- reveal until (wave 13E) -- 701.20b: the revealed cards stay in the library, so "shuffle the rest into your library" is a
    # shuffle of it ("…, then shuffle"); "you may reveal … until … If you do, put that card …": the reveal is the optional action
    if "until you reveal " in body:
        body = re.sub(r"(until you reveal [^.]*?)\. If you do, put ", r"\1. Put ", body) if "ou may reveal cards" in body else body
        body = re.sub(r"(?:, then| and) shuffle (?:the rest|all other cards revealed this way) into your library", ", then shuffle", body)
    from app.rules import watches  # -- turn watches (wave 7D) --

    body = watches.join_retarget(body)
    if it is None and not event_player:  # -- if you do (wave 5G) -- a spell's or an activated ability's "each other
        # player": every other player than its controller is an opponent in a free-for-all (102.2, 806.2); in a trigger
        # "other" may be relative to the event's player — not read there
        # (not where the grammar reads it already: an edict, language.EDICT_OTHERS; "during each other player's …")
        body = re.sub(r"\b([Ee])ach other player\b(?! sacrifices)(?!'s)", lambda m: f"{m[1]}ach opponent", body)
    body = _choose_then(body)  # -- if you do (wave 6F) --
    texts =[s for s in split_sentences(body) if s]  # ("You may pay …" looks ahead at "If you do"; quote-aware: wave 2D)
    sentences: list[int] = []  # where each sentence's effects start (resolve_it: the pronouns' reach)
    skip_to = 0  # -- refused look/cast-free (wave 3R5) -- sentences read together with an earlier one (piles)
    groups_at = 0  # -- kicked / instead (wave 4G) --
    for i, sentence in enumerate(texts):
        if i < skip_to:
            continue
        text = _lower_first(sentence.rstrip(".").strip())
        if (i > 0 or effects) and text.startswith("then ") and not text.startswith(("then shuffle", "then you may ")):
            text = text[5:]  # -- waves 3D/3L/3C -- "Then that creature deals …" / "Then draw a card.": "then" only orders (608.2c)
        if any(x.get("do") == "token_copy" for x in effects):  # -- token copy (wave 20F) -- "Exile the token at end of combat": the one just made
            text = re.sub(r"^(exile|sacrifice) (?:the|that) token (at (?:the beginning of .+|end of combat))$", r"\1 it \2", text)
        # -- X sized by a count (wave 4K) -- "If X is 10 or more, also create X 4/4 … tokens" (Finale of Glory): in addition
        # to what came before (not instead of it): the plain conditional instruction
        text = re.sub(r"^(if x is \w+ or (?:more|greater), )also (?=create |draw |you gain |put )", r"\1", text, flags=re.I)
        prev_start, start = start, len(effects)
        prev_groups, groups_at = groups_at, len(groups)  # -- kicked / instead (wave 4G) -- each sentence's own target groups
        sentences.append(start)
        if (per := _each_controller_creates(text)) is not None:  # -- "this way" outcomes (wave 4A) --
            effects += per
            continue
        if (swap := this_way.graveyard_swap(text)) is not None:  # -- if you do (wave 5G) -- Living Death
            effects += swap
            continue
        if (dest := _COUNTERED_INSTEAD.fullmatch(text)) is not None and len(effects) - prev_start == 1 \
                and effects[-1]["do"] == "counter" and "to" not in effects[-1]:  # -- "this way" outcomes (wave 4A) --
            # (after anything but a plain counter: other readers, e.g. unless_pays (wave 4C), or manual)
            effects[-1] = {**effects[-1], "to": "exile" if dest["exile"] else ("top" if dest["top"] else "bottom")}
            continue
        text = _for_each_this_way(text)  # -- "this way" outcomes (wave 4A) --
        if (piles := _piles(texts, i, effects)) is not None:  # -- refused look/cast-free (wave 3R5) -- 700.3
            if not piles[0]:
                return None
            effects += piles[0]
            skip_to = i + piles[1]
            continue
        if _WIN_IF_X.fullmatch(text):  # -- refused look/cast-free (wave 3R5) -- Thassa's Oracle (104.2b)
            bound_x = [x["n"] for x in effects if isinstance(x.get("n"), dict) and x["n"] != {"x": 1}]
            if len(bound_x) != 1 or not re.search(r"\bwhere x is\b", body, re.IGNORECASE):
                return None  # (X is the one an earlier sentence of this ability defined: 107.3c)
            effects.append({"do": "win_if_library", "x": bound_x[0]})
            continue
        # -- token copies & attach on entry (wave 5J) -- Mechanized Production's win
        from app.rules import populate as _populate

        if (won := _populate.win_sentence(text)) is not None and effects:
            effects.append(won)
            continue
        if text == "if you search your library this way, shuffle":  # -- refused zones/sized (wave 3R4) -- (_gy_shuffle)
            effects.append({"do": "gy_search_shuffle"})
            continue
        may_mill = re.fullmatch(r"you may mill (?P<n>two|three|four|five|\d+) cards", text) if i == 0 and len(texts) > 1 \
            and not texts[1].startswith("If you ") else None  # (wave 8C: "If you do" asks about the mill: a payment)
        if may_mill is not None:  # -- refused zones/sized (wave 3R4) -- "You may mill three cards. Then return …": only the
            # mill is optional (the rest happens either way): refused_zones.may_mill asks as it resolves
            effects.append({"do": "may_mill", "n": num(may_mill["n"])})
            continue
        excess = _EXCESS.fullmatch(text)  # -- refused zones/sized (wave 3R4) -- 120.4a (_excess_redirect)
        if excess is not None:
            effects.append({"do": "excess_redirect", "if_trample": bool(excess["trample"])})
            continue
        if (kicked := _KICKED.match(text)) is not None:
            with_kicker = _kicked_sentence(kicked, effects, prev_start, groups, prev_groups)
            if with_kicker is None:
                return None
            effects = with_kicker
            continue
        # -- refused grants/replacements (wave 3R2) -- "… deals 4 damage to target creature. The damage can't be
        # prevented." (615.12): the damage the sentence before deals
        if text == "the damage can't be prevented":
            dealt = [e for e in effects[prev_start:] if e.get("do") == "damage"]
            if not dealt or len(dealt) != len(effects[prev_start:]):
                return None
            for e in dealt:
                e["unpreventable"] = True
            continue
        # -- prevention riders (wave 17A) -- 615.5: "You gain life equal to the damage prevented this way." after a prevention
        if (attached := _source_shields.rider(text, effects)) is not None:
            if not attached:
                return None
            continue
        # "The flashback cost is equal to its mana cost." (the grant before it)
        from app.rules import graveyard_grants

        if graveyard_grants.cost_sentence(text, effects[prev_start:]):
            continue
        # -- end refused grants/replacements (wave 3R2) --
        if (exile_gy := _FREE_EXILE_GY.fullmatch(text)) and effects and effects[-1]["do"] == "free_cast":
            effects[-1] = {**effects[-1], "exile_gy": "is" if exile_gy["is"] else True}  # -- refused look/cast-free (wave 3R5) -- 614.1a, on the spell cast
            continue
        if text.startswith("if you do, you may cast the cop") and effects and effects[-1]["do"] == "copy_cards":
            text = text[len("if you do, "):]  # -- copied abilities (wave 18F) -- "You may copy the exiled card. If you do, …": the first sentence's "may"
            # is the whole choice (a copy that isn't cast ceases to exist, 707.10a)
        if text.startswith("you may copy ") and not effects and _exiled_with._COPY.match(text):
            effects += [{"do": "copy_cards", "who": _exiled_with.WHO}]  # (the "may" is the cast's: a copy not cast ceases to exist, 707.10a)
            continue
        if text.startswith("you may exile ") and not effects and (imprint := _exiled_with.imprint(text)) is not None:
            effects += imprint  # -- copied abilities (wave 18F) -- "Imprint — … you may exile an instant card from your hand."
            continue
        # -- unless pays (wave 4C) -- the riders of "Counter target spell unless its controller pays …" (608.2c, 118.12)
        if (rider := _unless_rider(text, effects, prev_start)) is not None:
            if rider is False:
                return None
            if rider is not True:
                text = rider  # ("If they do, …": the payer's choice, read below as the payment's "If you do")
            else:
                continue
        # -- end unless pays (wave 4C) --
        if (instead := replacement_sentence(text, effects, groups)) is not None:  # -- replacement effects stage 2 (wave 2E) --  (before 1B: a replacement, not a condition)
            effects += instead
            continue
        # -- conditional / instead clauses (wave 1B) --  "If C, Y instead." / "Y instead if C." / "Otherwise, Z."
        if (branch := _instead_or_otherwise(text, effects, prev_start, groups, it)) is not None:
            if branch is False:
                return None
            effects, shift = branch
            start += shift  # (an effect was put before this sentence's first: the pronouns' reach moves with it)
            sentences[-1] = start
            continue
        # "You may pay {2}. If you do, …" (118.12): the cost is an effect that records whether it
        # was paid; "If you do" / "If you don't" then gates the sentence on that payment
        from app.rules import paid_x as _paid_x  # -- sized payments (wave 5G) -- "X can't be greater than …"

        if _paid_x.cap_sentence(text, effects):
            continue
        # -- if you do (wave 6F) -- "Each opponent may …. Each opponent who doesn't …"
        from app.rules import each_may as _each_may

        if (unless_each := _each_may.unless_sentence(text)) is not None:  # -- if you do (wave 15C) -- "Each opponent … unless they …"
            effects += unless_each
            continue
        if (each := _each_may.pair(text, texts[i + 1] if i + 1 < len(texts) else None, effects, _last_payment(effects))) is not None:
            effects += each
            skip_to = i + 2
            continue
        if text.startswith("then you may ") and effects and texts[i + 1:i + 2] and texts[i + 1].startswith("If you do") \
                and _may_pay_sentence(text[5:], texts[i + 1:i + 2], it, effects) is not None:
            text = text[5:]  # ("You gain 2 life. Then you may discard two cards. If you do, …": "then" only orders, 608.2c)
        if (paid := _may_pay_sentence(text, texts[i + 1:i + 2], it, effects)) is not None:
            effects.append(paid)
            continue
        if text.startswith("when you do, ") or _REFLEX_DISCARD.match(text):  # -- refused modal/conditional (wave 3R1) -- a reflexive trigger (603.12)
            reflex = _reflexive(" ".join(texts[i:]), effects, prev_start, optional, it)
            if reflex is None:
                return None
            effects.append(reflex)
            break  # (the rest of the ability is the reflexive trigger's)
        if (dont := _FREE_DONT.match(text)) is not None and effects and effects[-1]["do"] == "free_cast":
            gated = _free_dont(dont["rest"], effects, dont["neg"] == "don't")  # -- refused look/cast-free (wave 3R5) -- "If you don't cast it, …"
            if gated is None:
                return None
            effects += gated
            continue
        text = _PICK_NEG.sub(r"if you \1, ", text)  # -- look and distribute (wave 3L) -- "If you don't put the card into your hand, …"
        if _PICK_DIDNT.match(text) and any(x["do"] == "pick_looked" and x["to"] == "hand" for x in effects):
            text = _PICK_DIDNT.sub("if you don't, ", text)  # -- if you do (wave 10C) -- "If you didn't put a card into your hand this way, …"
        or_if = re.match(r"^if you do or if (?P<c>[^,]+), (?P<rest>.+)$", text)
        if or_if is not None and _last_payment(effects) is not None:
            # -- if you do (wave 15C) -- "…, you may reveal a Dinosaur card from your hand. If you do or if you control another
            # Dinosaur, you gain 3 life.": the payment was made, or the condition holds — either one (608.2c)
            from app.rules import conditions

            cond_or = conditions.parse(or_if["c"], objects=True)
            inner_or = _clause(or_if["rest"]) if cond_or is not None and not or_if["rest"].startswith("you may ") else None
            if inner_or is None:
                return None
            added = _add_groups(groups, *inner_or)
            effects += [{"do": "only_if", "cond": {"any": [{"succeeded": _last_payment(effects)}, cond_or]}, "skip": len(added)}, *added]
            continue
        if text.startswith("if you can't, ") and not optional and len(effects) - prev_start == 1 \
                and effects[prev_start]["do"] == "remove_counters":  # -- keywords (wave 15E) -- fading 702.32a: "Remove a fade counter
            text = "if you don't, " + text[len("if you can't, "):]  # from this permanent. If you can't, sacrifice it." (the removal
            # of a counter that isn't there is the one that wasn't done, as "If you don't" reads it)
        if (if_do := _IF_YOU_DO.match(text)) is not None:
            bind = _last_payment(effects)
            pick = next((e for e in reversed(effects) if e["do"] == "pick_looked"), None)
            if bind is None and pick is not None and (pick.get("optional") or (pick.get("sel") and not pick.get("which"))):  # (wave 10C: "Put a land card from among them into your hand. If you didn't …")
                # -- look and distribute (wave 3L) -- "You may put a land card from among them onto the
                # battlefield. If you don't, put a card from among them into your hand.": the pick records
                # whether it moved a card (effects._picked)
                inner = _clause(if_do["rest"])
                if inner is None:
                    return None
                name = pick.setdefault("did", f"pdid{sum(1 for x in effects if x.get('did'))}")
                added = _add_groups(groups, *inner)
                pick_gate: dict[str, Any] = {"succeeded": name, **({"negate": True} if if_do["neg"] else {})}
                effects += [{"do": "only_if", "cond": pick_gate, "skip": len(added)}, *added]
                continue
            chooser = next((e for e in reversed(effects) if e["do"] == "choose_from_hand"), None)
            if bind is None and chooser is not None and chooser.get("optional") and (chooser.get("did") or effects[-1] is chooser):
                # -- if you do (wave 15C) -- "Target opponent reveals their hand. You may choose a nonland card from it. If you do,
                # that player discards that card. If you don't, …": whether a card was chosen (effects.resume_choose_from_hand)
                inner = _clause(if_do["rest"]) if not if_do["rest"].startswith("you may ") else None
                if inner is None:
                    return None
                name = chooser.setdefault("did", f"hdid{sum(1 for x in effects if x.get('did'))}")
                added = _add_groups(groups, *inner)
                effects += [{"do": "only_if", "cond": {"succeeded": name, **({"negate": True} if if_do["neg"] else {})},
                             "skip": len(added)}, *added]
                continue
            if bind is None and not optional and (did_r1 := _if_you_do_after_mandatory(if_do, effects, prev_start)) is not None:
                name, inner = did_r1  # -- refused modal/conditional (wave 3R1) -- "Sacrifice ~. If you do, …"
                added = _add_groups(groups, *inner)
                gate_r1: dict[str, Any] = {"succeeded": name, **({"negate": True} if if_do["neg"] else {})}
                effects += [{"do": "only_if", "cond": gate_r1, "skip": len(added)}, *added]
                continue
            if bind is None:  # -- conditional / instead clauses (wave 1B) --  "You may draw a card. If you do, discard a card."
                after_may = _if_you_do_after_may(if_do, effects, optional, i, len(texts))
                if after_may is None:
                    return None
                added = _add_groups(groups, *after_may)  # (B's own target, if any: wave 4A)
                # (A may be replaced or impossible: "If you do" reads what A actually did)
                tracked = [e for e in effects if e["do"] in _PROBED]
                probes = [f"did{k}" for k in range(len(tracked))]
                for e, name in zip(tracked, probes, strict=True):
                    e["did"] = name
                if probes:
                    did_gate: dict[str, Any] = {"succeeded": probes[0]} if len(probes) == 1 else {"all": [{"succeeded": n} for n in probes]}
                    added = [{"do": "only_if", "cond": did_gate, "skip": len(added)}, *added]
                effects += added
                continue
            # -- sized payments (wave 5G) -- the X the payment paid (app/rules/paid_x.py)
            pay_e = next(e for e in reversed(effects) if e["do"] == "optional_payment")
            rest_text = if_do["rest"]
            sized_pay = "choose_x" in pay_e or "life_x" in pay_e
            if pay_e.get("that_many") and not if_do["neg"]:
                rest_text = re.sub(r"\bthat many\b", "X", rest_text)
            # -- if you do (wave 6F) -- "you may discard your hand. If you do, draw that many cards": the cards discarded
            # (optional_payment records them as the payment's X), never a trigger event's amount
            hand_pay = pay_e.get("cost") == "Discard your hand" and re.search(r"\bthat many\b", rest_text) is not None
            if hand_pay and (if_do["neg"] or re.search(r"\bX\b", rest_text)):
                return None
            if hand_pay:
                rest_text = re.sub(r"\bthat many\b", "X", rest_text)
            if sized_pay and (if_do["neg"] or not re.search(r"\bX\b", rest_text)) and not (
                    pay_e.get("life_x") == {"event_amount": 1} and not if_do["neg"]):  # (Niv-Mizzet: "that many" = that much)
                return None
            from app.rules import pay_objects

            # ("that creature" is the paid object only when nothing else in the ability could be what it names)
            others = bool(groups) or any(x["do"] in _MOVERS for x in effects if x is not pay_e)
            rest_text = pay_objects.rewrite(rest_text, pay_e, "event" if others else it)  # -- if you do (wave 8C) -- "that creature's mana value"
            inner = _clause(rest_text) if not rest_text.startswith("you may ") else None
            if inner is not None:
                inner = pay_objects.bind(inner, pay_e)  # -- if you do (wave 8C) -- the sacrificed / exiled object, from the payment
            if inner is None:
                return None
            if sized_pay or hand_pay:  # (hand_pay: wave 6F)
                from app.rules import paid_x

                if re.search(r'"x"|\bX\b', json.dumps(inner[1], default=str)):
                    return None  # (an X in a target's definition: the target is chosen before X is, 603.3d)
                inner = (paid_x.bind_x(inner[0], bind), inner[1])
            # -- end sized payments (wave 5G) --
            added = _add_groups(groups, *inner)
            gate: dict[str, Any] = {"succeeded": bind, **({"negate": True} if if_do["neg"] else {})}
            effects += [{"do": "only_if", "cond": gate, "skip": len(added)}, *added]
            continue
        # -- if you do (wave 15C) -- "Scry 3, then you may reveal the top card of your library. If a creature card is revealed
        # this way, …": the one card the reveal before showed (701.20a), the same question as "If it's a creature card"
        last_look = next((e for e in reversed(effects) if e["do"] == "look_top"), None)
        revealed = re.match(r"^if (?:a|an) (?P<w>[^,]+? card) is revealed this way, (?P<r>.+)$", text)
        if revealed is not None and last_look is not None and last_look.get("reveal") and last_look.get("n") == 1 \
                and not last_look.get("until") and last_look.get("player") == "you":
            text = f"if it's a {revealed['w']}, {revealed['r']}"
        cond_m = re.match(r"^if (?P<c>[^,]+), (?P<rest>.+)$", text)
        if cond_m:  # "If you control a Forest, draw a card." (608.2c): a condition on this sentence
            from app.rules import conditions

            cond = conditions.parse(cond_m["c"], objects=True)
            if cond is None and (cond := this_way.condition(cond_m["c"])) is not None:  # -- "this way" outcomes (wave 4A) --
                inner = _conditional_inner(cond_m["rest"])
            else:
                inner = _conditional_inner(cond_m["rest"], cond) if cond is not None else None
            if inner is None and cond is not None and cond_m["rest"].startswith("you may ") and i == len(texts) - 1 and effects:
                # -- transform (wave 20F) -- "Then if you have seven or more cards in your graveyard, you may transform ~." at the end of
                # the ability (608.2c): the gate, then the controller's choice for the rest (unless_pays.may_rest, 603.5)
                inner = _conditional_inner(cond_m["rest"][len("you may "):], cond)
                inner = ([{"do": "may_rest"}, *inner[0]], inner[1]) if inner is not None and not inner[1] else None
            if inner is None:
                return None
            added = _add_groups(groups, *inner)  # (its target, if any: its own group, 115.3)
            effects += [{"do": "only_if", "cond": cond, "skip": len(added)}, *added]
            continue
        # -- unless pays (wave 4C) -- "You may draw a card unless that player pays {1}." (118.12a): that player decides
        # first; the "you may" is asked after (unless_pays.may_rest), not as the resolution begins
        if text.startswith("you may ") and not effects and len(texts) == 1 and " unless that player pays " in text \
                and (paid_may := _unless_sentence(text[len("you may "):], effects, may=True, it=it)) is not None:
            effects += _add_groups(groups, *paid_may)
            continue
        # -- cast limits (wave 5E) -- "You may cast spells this turn as though they had flash."
        from app.rules import cast_limits

        if (flash := cast_limits.flash_sentence(text)) is not None:  # (a permission, not a choice made on resolution)
            effects += flash
            continue
        if (extra_land := _land_plays.sentence(text)) is not None:  # -- one-shot extra land plays (wave 8A) -- 305.2 (a permission)
            effects += extra_land
            continue
        if effects and text.startswith("then you may ") and _may_then_if_you_do(text[5:], texts[i + 1:], effects, probe=False) is not None:
            text = text[5:]  # (-- if you do (wave 15C) -- "then" only orders, 608.2c)
        if text.startswith("you may "):
            if effects and (mid := _may_then_if_you_do(text, texts[i + 1:], effects)) is not None:
                effects += _add_groups(groups, *mid)  # -- if you do (wave 15C) -- "…. You may draw a card. If you do, discard a card."
                skip_to = i + 2
                continue
            if effects:
                # "…. You may reveal … from among them …": a clause that models its own choice
                own = _clause(text, True)
                if own is None and i == len(texts) - 1 and (inner := _one_clause(text[len("you may "):])) is not None:
                    own = ([{"do": "may_rest"}, *inner[0]], inner[1])  # -- reanimation (wave 20C) -- the last sentence: may_rest asks for all of it
                if own is None or not any(x.get("optional") or x.get("do") == "may_rest" for x in own[0]):
                    return None  # "…. You may …" mid-ability: not a simple optional trigger
                effects += _add_groups(groups, own[0], own[1])
                continue
            optional, text = True, text[len("you may "):]
            # -- triggers (wave 5D) -- "you may have ~ deal 1 damage …" (603.5)
            from app.rules import trigger_words

            text = trigger_words.have_subject(text)
        if effects and (bare := _language.bare_pronoun_grant(text)) is not None:  # -- recursion & tutors (wave 4M) --
            effects += bare  # ("It gains haste.": a whole sentence, after the instruction that names "it")
            continue
        for pattern, build in EFFECTS:
            m = pattern.match(text)
            if m:
                found, sel = build(m)
                if found and found[0]["do"] == "token_text":  # "It has "…"": the token just created
                    if not effects or effects[-1]["do"] != "create_token":
                        return None
                    effects[-1] = {**effects[-1], "token": {**effects[-1]["token"], "text": found[0]["text"]}}
                    break
                effects += _add_groups(groups, found, sel)  # each word "target": its own group (115.3)
                break
        else:
            parsed_clause = _unless_sentence(text, effects, it=it) or _trailing_conditional(text) or _clause(text, True)
            if parsed_clause is None:
                return None
            found, sel = parsed_clause
            effects += _add_groups(groups, found, sel)
    if _x_now():
        effects = _swap_x(effects)
    if any(e.get("do") == "may_rest" for e in effects[:sentences[-1]]):
        return None  # -- reanimation (wave 20C) -- may_rest ends the resolution on "no": nothing may follow its sentence
    resolved = resolve_it(effects, it, groups, sentences=sentences, event_player=event_player)
    if resolved is not None:  # -- refused modal/conditional (wave 3R1) -- an "instead" pronoun naming the target
        resolved = _gated_other_rewrite(_branch_refs_retarget(resolved))
    if resolved is None or not _branch_refs_ok(resolved) or not _gated_other_ok(resolved):  # (conditional clauses, wave 1B)
        return None
    from app.rules import pay_objects  # -- if you do (wave 8C) --

    if pay_objects.leftover(resolved):  # -- if you do (wave 8C) -- "the exiled card" with no payment before it
        return None
    if re.search(r'"(?:power|toughness|mana_value)": "it:(?!discarded)', json.dumps(resolved, default=str)):
        return None  # (-- X sized by a count (wave 19F) -- "the milled card's …" in a field that binds no such reference)
    if not _cast_conditions_ok(resolved) or not _did_refs_ok(resolved):  # -- refused modal/conditional (wave 3R1) --
        return None
    if not _dice.refs_ok(resolved):  # -- rolling dice (wave 12A) -- "equal to the result" only after a roll
        return None
    if not _coin_flips.refs_ok(resolved):  # -- coin flips (wave 7E) -- "If you win the flip" only after a flip
        return None
    # -- "this way" outcomes (wave 4A) -- "discard your hand, then draw that many cards": "that many" is the
    # cards discarded, not a trigger event's amount (not read)
    for k, e in enumerate(resolved):
        if e["do"] == "discard" and (e.get("all") or e.get("upto")) and '"event_amount"' in json.dumps(resolved[k + 1:]):
            return None
    # -- kicked / instead (wave 4G) -- targets tied to the kicker (702.33g)
    from app.rules import kicked_instead

    if not kicked_instead.refs_ok(resolved, groups):
        return None
    resolved, target = _finish_targets(resolved, groups)
    looked = False
    exiled_at, cast_from_exile = None, False  # -- refused look/cast-free (wave 3R5) --
    mill_k: int | None = None  # (wave 10C)
    for k, e in enumerate(resolved):  # "… from among them" needs the cards a look put aside (not milled ones)
        looked = looked or e["do"] == "look_top"
        if e["do"] == "exile_top":
            exiled_at, cast_from_exile = (None if e.get("face_down") else k), False
        elif e["do"] == "free_cast" and exiled_at is not None and (
                e.get("zone") == "found" or e.get("who") == f"ref:{resolved[exiled_at].get('as')}"):
            cast_from_exile = True
        if e["do"] == "rest_looked" and not looked and exiled_at is not None and cast_from_exile \
                and e["to"] in ("bottom_random", "graveyard", "hand"):
            # "Put the rest / the exiled cards not cast this way on the bottom of your library in a random order"
            # (after "Exile the top six cards. You may cast … from among them …"): the exiled cards still in exile
            src = resolved[exiled_at]
            src.setdefault("as", f"x{exiled_at}")
            resolved[k] = {"do": "rest_exiled", "who": f"ref:{src['as']}", "to": e["to"]}
            continue
        if e["do"] == "mill":
            mill_k = k
        if k and any(x.get("upto") and x["do"] == "sacrifice_choice" for x in resolved[:k]) and "event_amount" in json.dumps(e):
            return None  # -- triggers (wave 19B) -- "up to that many" after "sacrifice any number of": the sacrificed count, not the event's
        if e.get("put") and not str(e.get("who")).startswith("event"):
            return None  # -- triggers (wave 19B) -- "put it onto the battlefield" is read only for the trigger event's card (a graveyard card)
        if e["do"] == "pick_looked" and not looked and mill_k is None and e.get("which") in ("that", "all") and not e.get("sel") \
                and not e.get("optional") and e["to"] in ("battlefield", "battlefield_tapped") and str(it).startswith("event"):
            # -- triggers (wave 19B) -- "Whenever one or more land cards are put into your graveyard from your library, put them onto the
            # battlefield tapped": nothing was looked at, so it is the trigger event's card(s), as "return them to the battlefield" reads it
            resolved[k] = {"do": "return_card", "who": "event", "to": "battlefield", "tapped": e["to"] == "battlefield_tapped", "under": "you"}
            continue
        if e["do"] in ("pick_looked", "rest_looked") and not looked:
            # -- if you do (wave 10C) -- "Mill three cards. You may put a land card from among them into your hand.": the pick
            # is from the cards that mill put into the graveyard (the controller's own mill, a choice among chosen-by-kind cards)
            if mill_k is None or e["do"] != "pick_looked" or resolved[mill_k].get("who") != "you" or e.get("which") \
                    or e.get("reveal") or e["to"] not in ("hand", "top", "battlefield", "battlefield_tapped"):
                return None
            resolved[mill_k]["look"] = True
    # -- cast without paying (wave 3C) -- (wave 3R5: the cast is made during the resolution, 608.2g, and the
    # instructions after it follow it — permissions.free_cast; "from among them" was bound by resolve_it)
    if any(e["do"] == "free_cast" and e.get("zone") == "among" for e in resolved):
        return None
    for k, e in enumerate(resolved):  # -- refused look/cast-free (wave 3R5) --
        if e["do"] == "found_to" and not any(x["do"] == "free_cast" and x.get("zone") in ("found", "looked") for x in resolved[:k]):
            return None  # ("put it into your hand": the card found / the one revealed, nothing else)
        if e["do"] == "free_cast" and e.get("mv") == "x" and re.search(r"\bwhere x is\b", body, re.IGNORECASE):
            # "reveal the top X cards …, where X is that spell's mana value. You may cast a spell with mana value
            # X or less from among …": the one X the ability defines (107.3c), not a cost's X
            bound = [x["n"] for x in resolved[:k] if isinstance(x.get("n"), dict) and x["n"] != {"x": 1}]
            if len(bound) != 1:
                return None
            resolved[k] = {**e, "mv": bound[0]}
    if optional and len(resolved) > 1 and resolved[0]["do"] == "free_cast" and resolved[0].get("optional"):
        optional = False  # -- refused look/cast-free (wave 3R5) -- "You may cast … . Draw a card.": only the cast is optional
    return resolved, target, optional


# -- if you do (wave 6F) -- "If you do, choose a color, then return all creatures of that color to their owners' hands."
# (Dromar, Rith, Treva, Crosis): the choice is made as the instruction is reached (608.2c), then the rest reads it — the
# same as "Choose a color. Return all creatures of the chosen color …" (effects.choose_value, chosen.bind_effects).
_CHOOSE_THEN = re.compile(r"(?:^|(?<=\. ))(?P<if>If you do, )?(?P<c>[Cc])hoose a (?P<what>color|creature type), then "
                          r"(?P<rest>[^.]+)\.")


def _choose_then(body: str) -> str:
    def sub(m: re.Match[str]) -> str:
        rest = m["rest"]
        if f"of that {m['what']}" not in rest or "chosen" in rest:
            return m[0]
        rest = rest.replace(f"of that {m['what']}", f"of the chosen {m['what']}")
        if m["if"]:  # (both instructions hinge on the same payment: "If you do" names the latest one)
            return f"If you do, choose a {m['what']}. If you do, {rest}."
        return f"{m['c']}hoose a {m['what']}. {rest[:1].upper()}{rest[1:]}."
    return _CHOOSE_THEN.sub(sub, body)


def _own_choice(parsed: tuple[list[dict[str, Any]], Any, bool] | None) -> tuple[list[dict[str, Any]], Any, bool] | None:
    """-- refused look/cast-free (wave 3R5) -- A spell or activated ability that is all "You may cast …
    without paying its mana cost": the "may" is the cast's own choice (choosing no card), not a
    question about the whole ability (which spells and activated abilities don't have)."""
    if parsed is not None and parsed[2] and len(parsed[0]) == 1 and parsed[0][0]["do"] == "free_cast" \
            and parsed[0][0].get("optional"):
        return parsed[0], parsed[1], False
    # -- token copies & attach on entry (wave 5J) -- "You may put a creature card from your hand onto the battlefield."
    # (Elvish Piper): the "may" is choosing no card
    if parsed is not None and parsed[2] and parsed[0] and parsed[0][0]["do"] == "put_from_hand":
        return [{**parsed[0][0], "optional": True}, *parsed[0][1:]], parsed[1], False
    # -- activated leftovers (wave 7E) -- "{U}, {T}: You may tap or untap target creature.": the "may" is choosing neither
    if parsed is not None and parsed[2] and len(parsed[0]) == 1 and parsed[0][0]["do"] == "tap_or_untap":
        return [{**parsed[0][0], "optional": True}], parsed[1], False
    return parsed


_KICKED = re.compile(r"^if (?:this spell|it|~) was kicked, (?P<instead1>instead )?(?P<rest>.+?)(?P<instead2> instead)?$")
# -- refused look/cast-free (wave 3R5) -- after a free cast: a replacement effect on the spell cast (614.1a)
_FREE_EXILE_GY = re.compile(r"^if (?:that spell|that card|a spell cast this way|(?P<is>an instant or sorcery) spell cast this way) "  # (wave 19C: "is")
                            r"would be put into (?:your|their|a) graveyard, exile it instead$")
# -- refused look/cast-free (wave 3R5) -- 700.3: piles of the cards just revealed (public: 701.20a)
_PILES_THEY = re.compile(r"^an opponent separates (?:those|the revealed|these) cards into two piles$")
_PILES_YOU = re.compile(r"^(?P<reveal>reveal the top .+? of your library) and separate them into two piles$")
_PILES_CHOOSE = re.compile(r"^an opponent chooses one of (?:those|the) piles$")
_PILES_PUT = re.compile(r"^put (?:one|that) pile into your hand and the other into your graveyard$")


def _piles(texts: list[str], i: int, effects: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int] | None:
    """"Reveal the top five cards of your library. An opponent separates those cards into two piles. Put one
    pile into your hand and the other into your graveyard." (Fact or Fiction: the opponent separates, you
    choose) / "Reveal the top five cards of your library and separate them into two piles. An opponent
    chooses one of those piles. Put that pile into your hand and the other into your graveyard." (Steam
    Augury: you separate, the opponent chooses). Which opponent: the spell's controller chooses (608.2d).
    Returns (effects, sentences used); ([], …) refuses; None: not a piles sentence."""
    from app.rules.language import parse_sentence

    def text(k: int) -> str:
        return _lower_first(texts[k].rstrip(".").strip()) if k < len(texts) else ""

    if _PILES_THEY.match(text(i)):
        if not _PILES_PUT.match(text(i + 1)) or "one pile" not in text(i + 1):
            return [], 1
        if not effects or effects[-1]["do"] != "look_top" or not effects[-1].get("reveal") or effects[-1].get("until") \
                or effects[-1].get("player") != "you":
            return [], 1  # (only cards just revealed from your library: public, 700.3c)
        return [{"do": "piles", "separator": "opponent", "chooser": "you"}], 2
    m = _PILES_YOU.match(text(i))
    if m:
        found = parse_sentence(m["reveal"])
        if not _PILES_CHOOSE.match(text(i + 1)) or not _PILES_PUT.match(text(i + 2)) or "that pile" not in text(i + 2) \
                or found is None or len(found[0]) != 1 or found[0][0]["do"] != "look_top" or not found[0][0].get("reveal"):
            return [], 1
        return [found[0][0], {"do": "piles", "separator": "you", "chooser": "opponent"}], 3
    return None


_WIN_IF_X = re.compile(r"^if [xX] is greater than or equal to the number of cards in your library, you win the game$")
# (wave 18F: "You may cast the copy. If you do, you lose 2 life." too: the same record of what the cast did)
_FREE_DONT = re.compile(r"^if you (?P<neg>don't|do)(?: cast (?:it|that card|the exiled card|the revealed card)(?: this way)?)?, (?P<rest>.+)$")


def _free_dont(rest: str, effects: list[dict[str, Any]], negate: bool = True) -> list[dict[str, Any]] | None:
    """-- refused look/cast-free (wave 3R5) -- "If you don't cast it, put it into your hand / draw a card"
    after a free cast (608.2c: it reads what the cast did; the cast records it as ``did``)."""
    if rest in ("put it into your hand", "put that card into your hand"):
        if not negate:
            return None
        inner: list[dict[str, Any]] = [{"do": "found_to", "to": "hand"}]  # (checked against the cast's source below)
    else:
        parsed = _clause(rest)
        if parsed is None or parsed[1] is not None:
            return None
        inner = parsed[0]
        if any(isinstance(x.get("who"), str) and x["who"].startswith(("it", "them")) for x in inner):
            return None
    name = effects[-1].get("did") or f"fdid{len(effects)}"
    effects[-1] = {**effects[-1], "did": name}
    return [{"do": "only_if", "cond": {"succeeded": name, **({"negate": True} if negate else {})}, "skip": len(inner)}, *inner]


# -- optional payments (118.12 / 118.12a): app/rules/optional_payment.py ------------------------------
_PICK_NEG = re.compile(r"^if you (don't|do) put (?:the card|that card|it|them) (?:into your (?:hand|graveyard)|onto the battlefield(?: tapped)?"
                       r"|on (?:top of|the bottom of) your library), ")
_PICK_DIDNT = re.compile(r"^if you didn't put (?:a|the|that) card into your hand this way, ")
_IF_YOU_DO = re.compile(r"^if you (?:(?P<neg>don't)|do), (?P<rest>.+)$")
_UNLESS = re.compile(r"^(?P<lead>.+?) unless (?P<who>you|that player|they|its controller|that creature's controller) "
                     r"(?P<act>(?:pays?|discards?|sacrifices?|returns?|exiles?|removes?|taps?) .+)$")  # (wave 1B: any cost the engine pays)


def _last_payment(effects: list[dict[str, Any]]) -> str | None:
    """The binding of the most recent optional payment ("If you do" refers to it)."""
    return next((e["bind"] for e in reversed(effects) if e["do"] == "optional_payment"), None)


def _may_pay_sentence(text: str, following: list[str], it: str | None,
                      effects: list[dict[str, Any]]) -> dict[str, Any] | None:
    """"You may [cost]." when the next sentence is "If you do, …" / "If you don't, …": the cost as
    an optional_payment effect, bound as pay<k>. A cost about "it" is only read when "it" is this
    object (the trigger's own source); "When you do" (a reflexive trigger, 603.12) isn't read."""
    from app.rules import optional_payment

    if not text.startswith("you may ") or not following or not re.match(r"^(?:If you (?:do|don't)|If you do or if [^,]+|When you do), ", following[0]):
        return None
    phrase = text[len("you may "):]
    if re.search(r"\bit\b", phrase) and it != "self":
        return None
    cost = optional_payment.cost_text(phrase)
    sized: dict[str, Any] = {}
    if cost is None and (alts := optional_payment.alternatives(phrase)) is not None:  # -- if you do (wave 6F) -- A or B
        cost, sized = alts[0], {"alts": alts}
    if cost is None:  # -- sized payments (wave 5G) -- "pay {X}" / "pay X life, where X is …" (app/rules/paid_x.py)
        from app.rules import paid_x

        found = paid_x.payment(phrase) if following[0].startswith("If you do, ") else None
        if found is None:
            return None
        cost, sized = found.pop("cost"), found
    bind = f"pay{sum(1 for e in effects if e['do'] == 'optional_payment')}"
    return {"do": "optional_payment", "who": "you", "cost": cost, "bind": bind, **sized}


def _unless_sentence(text: str, effects: list[dict[str, Any]], may: bool = False,
                     it: str | None = None) -> tuple[list[dict[str, Any]], Any] | None:
    """"[Effect] unless [you / that player / they / its controller] pay(s) [cost]." (118.12a): the
    payer may pay; if they don't, the effect happens. "That player" / "they" is the effect's
    target player or the trigger event's player; "its controller" the controller of the effect's
    target object. Several payers ("each opponent … unless they pay") aren't read. The cost is any
    the engine pays (conditional / instead clauses, wave 1B): mana, life, "discard a card",
    "sacrifice a land", "return a land you control to its owner's hand", "exile a card from your
    graveyard" — 118.12a reads "X unless [a player] discards a card" as "[That player] may discard a
    card. If they don't, X."."""
    from app.rules import optional_payment

    m = _UNLESS.match(text)
    if m is None:
        return None
    verb, _, rest = m["act"].partition(" ")
    phrase = rest if verb.startswith("pay") else f"{verb[:-1] if verb.endswith('s') else verb} {rest}"
    if (it == "self" or m["lead"] == "sacrifice ~") and re.search(r"^remove an? [^ ]+ counter from it$", phrase):
        phrase = phrase[:-2] + "~"  # -- trigger tail (wave 15B) -- "sacrifice ~ unless you remove a +1/+1 counter from it": it is the source
    phrase = re.sub(r" or (pays?|discards?|sacrifices?|returns?|exiles?) ", lambda v: f" or {v[1].rstrip('s')} ", phrase)  # (wave 15C)
    if re.search(r"\bit\b", phrase):
        return None
    cost = optional_payment.cost_text(phrase)
    alts = optional_payment.alternatives(phrase) if cost is None else None  # -- if you do (wave 15C) -- "sacrifice … or discard a card"
    if alts is not None:
        cost = alts[0]
    # -- unless pays (wave 4C) -- a cost sized as it resolves ("{X}", "{X}, where X is …", "{1} for each …")
    sized: dict[str, Any] | None = None
    if cost is None and verb.startswith("pay"):
        from app.rules import unless_pays

        its = "target" if m["who"] in ("its controller", "that player", "they") else None  # (checked below: a target object)
        if re.fullmatch(r"(?:\{E\})+", rest):  # "unless you pay {E}{E}" (107.14: energy counters, not mana)
            cost = optional_payment.cost_text(f"pay {rest}")
        else:
            sized = unless_pays.sized_cost(rest, its)
            cost = "" if sized is not None else None
    # "Whenever a player casts a spell, counter it unless that player pays {3}.": the spell cast (the trigger event's)
    lead = ([{"do": "counter", "who": "event_spell"}], None) if it == "event_spell" and m["lead"] in ("counter it", "counter that spell") \
        else _clause(m["lead"])
    # -- end unless pays (wave 4C) --
    if cost is None or lead is None or not lead[0]:
        return None
    found, sel = lead
    groups = _as_groups(sel)
    who = m["who"]
    whos = {e.get("who") for e in found}
    group_player = bool(groups) and _player_target(groups[0]["what"])
    if sized is not None and '"target"' in json.dumps(sized) and not ("target" in whos and groups and group_player is False):
        return None  # -- unless pays (wave 4C) -- "its mana value": the target object's, only when there is one
    if who == "you":
        payer = "you"
    elif who in ("its controller", "that creature's controller"):
        if "target" not in whos or not groups or group_player is not False:
            return None
        payer = "target"
    elif "target" in whos and groups and group_player:
        payer = "target"
    elif whos == {"event_player"}:
        payer = "event_player"
    elif who in ("that player", "they") and whos == {"that_player"}:
        payer = "that_player"  # the player the lead is about (the trigger event's, or a target: resolve_it binds it)
    elif who in ("that player", "they") and whos == {"target"} and groups and group_player is False:
        payer = "target"  # "Counter target spell unless they pay {1}": they = the spell's controller
    # -- unless pays (wave 4C) -- "[You] draw a card unless that player pays {1}." / "Counter it unless that player
    # pays {3}." (a cast trigger's spell): no target, no other player in the lead — "that player" is the trigger
    # event's player (resolve_it binds it; _event_refs_ok refuses an ability whose event names no player)
    elif who == "that player" and not groups and whos <= {"you", "it", "event_spell"}:
        payer = "that_player"
    # -- end unless pays (wave 4C) --
    else:
        return None
    bind = f"pay{sum(1 for e in effects if e['do'] == 'optional_payment')}"
    pay: dict[str, Any] = {"do": "optional_payment", "who": payer, "cost": cost, "bind": bind}
    if alts is not None:
        pay["alts"] = alts
    if sized is not None:  # -- unless pays (wave 4C) --
        pay.update(sized)
    gated = [{"do": "may_rest"}, *found] if may else found  # (wave 4C: the "you may" after the payment, 118.12a)
    return [pay, {"do": "only_if", "cond": {"succeeded": bind, "negate": True}, "skip": len(gated)}, *gated], sel


# -- unless pays (wave 4C) --
_THEY_DO = re.compile(r"^if (?:they|that player) (?P<v>do|does|don't|doesn't), (?P<rest>.+)$")
_ALT_COST = re.compile(r"^if (?P<c>[^,]+), counter (?:that spell|it) unless its controller pays (?P<cost>(?:\{[^}X]+\})+) instead$")


def _unless_rider(text: str, effects: list[dict[str, Any]], prev_start: int) -> bool | str | None:
    """A sentence about the "… unless [a player] pays …" just before it: "If that spell is countered
    this way, exile it instead of putting it into its owner's graveyard." (608.2c: it modifies the
    counter — True, handled) or "If they do, …" / "If they don't, …" (118.12: whether that player
    chose to pay — the text to read as the payment's "If you do, …"). None: not such a sentence;
    False: such a sentence after something else (manual)."""
    from app.rules import unless_pays

    exile = unless_pays.countered_this_way(text)
    they = _THEY_DO.match(text)
    alt = _ALT_COST.match(text)
    if not exile and they is None and alt is None:
        return None
    prev = effects[prev_start:]
    if len(prev) == 1 and prev[0]["do"] == "counter_unless" and str(prev[0].get("who")).startswith("target"):
        # "Counter target spell unless its controller pays {3}." read as the payment it is (118.12a), so the
        # rider has a payment to read and a counter to modify
        bind = f"pay{sum(1 for e in effects if e['do'] == 'optional_payment')}"
        who = prev[0]["who"]
        effects[prev_start:] = prev = [{"do": "optional_payment", "who": who, "cost": prev[0]["cost"], "bind": bind},
                                       {"do": "only_if", "cond": {"succeeded": bind, "negate": True}, "skip": 1},
                                       {"do": "counter", "who": who}]
    if len(prev) < 3 or prev[0]["do"] != "optional_payment" or prev[0].get("who") == "you" or prev[1]["do"] != "only_if" \
            or prev[1]["cond"] != {"succeeded": prev[0]["bind"], "negate": True} or prev[1]["skip"] != len(prev) - 2:
        return False
    if exile or alt is not None:
        if len(prev) != 3 or prev[2]["do"] != "counter" or prev[2].get("who") != prev[0].get("who"):
            return False
        if alt is not None:
            # "If you control a Bird, counter that spell unless its controller pays {4} instead." (608.2c: the
            # condition is checked as the spell resolves, before the payment is asked for)
            from app.rules import conditions

            cond = conditions.parse(alt["c"], objects=True)
            if cond is None or "per" in prev[0] or prev[0].get("alt"):
                return False
            prev[0]["alt"] = {"cond": cond, "cost": alt["cost"]}
            return True
        prev[2]["exile"] = True
        return True
    assert they is not None
    verb = "do" if they["v"] in ("do", "does") else "don't"
    return f"if you {verb}, {they['rest']}"
# -- end unless pays (wave 4C) --


def _player_target(what: str) -> bool | None:
    """Is a target group's selector a player (True), an object (False), or either ("any target": None)?"""
    from app.rules import selectors

    if what in ("player", "opponent") or what.startswith("opponent_as:"):  # (wave 21E)
        return True
    if what == "any" or not what:
        return None
    return selectors.from_key(what).player is not None if what.startswith(selectors.PREFIX) else False


def _kicked_sentence(m: re.Match[str], effects: list[dict[str, Any]], prev_start: int,
                     groups: list[dict[str, Any]], prev_groups: int) -> list[dict[str, Any]] | None:
    """702.33e: "If this spell was kicked, [effect]." — the effect happens only if it was kicked;
    "… instead" replaces the sentence before it when it was kicked. -- kicked / instead (wave 4G) --
    Kicked-only text may add targets: they're chosen only if it's kicked (702.33g), and the targets of
    the sentence an "instead" replaces only if it isn't (601.2c; kicked_instead.applicable). "… instead"
    may restate the replaced instruction with another amount (kicked_instead.restate)."""
    from app.rules import kicked_instead

    rest = m["rest"]
    if rest.startswith("you may ") or rest.startswith("instead "):
        return None
    instead = bool(m["instead1"] or m["instead2"])
    if not instead:
        rest = kicked_instead.plain_addition(rest)
    base = effects[prev_start:]
    restated = kicked_instead.restate(rest, base) if instead else None
    if restated is not None:
        found: tuple[list[dict[str, Any]], Any] | None = (restated, None)
    else:
        if rest.startswith("it deals "):
            rest = "~ deals " + rest[len("it deals "):]  # "If this spell was kicked, it deals …": the spell (wave 1B)
        found = _clause(rest)
    if found is None or not found[0]:
        return None
    own = len(groups)
    try:  # (its own targets: its own groups, 115.3; a restatement's are the replaced instruction's, numbered already)
        alt = restated if restated is not None else _add_groups(groups, *found)
    except _NoMatch:
        return None
    if not kicked_instead.mark(groups, own, len(groups), True):
        return None
    if instead:
        if not base or any(e["do"] == "kicked_gate" for e in base):
            return None
        # (an alternative with targets of its own replaces the replaced sentence's targets too; one without
        # any — "it deals 4 damage instead", "put that card onto the battlefield instead" — keeps them)
        if len(groups) > own and not kicked_instead.mark(groups, prev_groups, own, False):
            return None
        return [*effects[:prev_start], {"do": "kicked_gate", "kicked": False, "n": len(base)}, *base,
                {"do": "kicked_gate", "kicked": True, "n": len(alt)}, *alt]
    return [*effects, {"do": "kicked_gate", "kicked": True, "n": len(alt)}, *alt]


ATTACHED_SUBJECTS = ("Enchanted creature", "Equipped creature", "Enchanted land")


@lru_cache(maxsize=4096)
def granted_ability(text: str) -> AbilityText | None:
    """A quoted ability granted by a static ("All Slivers have "…"") if the engine carries it out."""
    from app.rules.mana import parse_mana_ability

    parsed = parse_abilities(text)
    if len(parsed) != 1:
        return None
    ab = parsed[0]
    if ab.kind == "mana":
        return ab if parse_mana_ability(ab.text) is not None else None
    if ab.kind == "keywords":
        from app.rules.coverage import SUPPORTED_KEYWORDS

        if set(ab.keywords) <= SUPPORTED_KEYWORDS:
            return ab
        # -- attached events (wave 4L) -- "Protection from red", "Ward {2}", "Toxic 1"
        from app.rules import statics

        line = ab.text.rstrip(".")  # -- protection grants (wave 5E) -- (a resolved grant's text ends with a period)
        if re.fullmatch(statics.MEANING_GRANTS, line.lower()) or line.lower() == "riot":  # -- static grants (wave 15A) --
            return ab  # "Extort", "Afflict 2": their CR meaning; (wave 17C) riot: read as it enters (app/rules/riot.py)
        if ab.keywords == ("cumulative upkeep",):  # -- attached events (wave 20A) -- 702.24a: a triggered ability of whatever has it (triggers._cumulative_upkeep)
            from app.rules.coverage import _keyword_supported

            return ab if _keyword_supported("cumulative upkeep", line) else None
        return ab if statics.keyword_line(line[0].lower() + line[1:]) == line else None
    probe = Characteristics(name="\u0000", abilities=(ab,))
    return ab if define(ab, probe) is not None else None


def parse_anthem(text: str) -> Definition | None:
    """613 static P/T, keyword and ability grants ("Creatures you control get +1/+1.", "Other Elves
    you control get +1/+1 and have haste.", "All Slivers have "{T}: Add one mana of any color."",
    "~ gets +2/+2 as long as you control three or more artifacts."): app/rules/statics.py."""
    from app.rules import statics  # (statics imports granted_ability from here)

    return statics.parse(text)


# -- granted from object (wave 18F) -- an activated ability a static grant gave, whose effect names only its granter ("Blazing Torch deals
# 2 damage to any target", "Return Trusty Boomerang to its owner's hand"): read as the object's own ability (the granter is "~"), then
# its instructions' subject is that object, bound by the id the grant carries (selectors.GRANTER). An effect that also names the
# creature ("this creature", "it") is ambiguous to the grammar and stays unread.
_GRANTER_RE = re.compile(selectors.GRANTER)
_OTHER_SELF = re.compile(r"\b(?:this \w+|it|its(?! owner)|that creature|equipped creature)\b", re.IGNORECASE)
_GRANTER_SUBJECT = {"add_counters", "bounce", "sacrifice", "tap", "untap"}


def _granter_view(ability: AbilityText) -> tuple[AbilityText, str] | None:
    head, _, effect = ability.text.partition(":")
    found = _GRANTER_RE.search(effect)
    if ability.kind != "activated" or found is None or _OTHER_SELF.search(_GRANTER_RE.sub("", effect)):
        return None
    return replace(ability, text=f"{head}:{_GRANTER_RE.sub('this permanent', effect)}"), found["oid"] or ""


def _granter_bound(d: Definition, oid: str) -> Definition | None:
    effects = []
    for e in d["effects"]:
        if e.get("do") in _GRANTER_SUBJECT and e.get("who") == "self":
            e = {**e, "who": f"obj:{oid}"}
        elif e.get("do") == "damage" and not e.get("src"):
            e = {**e, "src": f"obj:{oid}"}
        effects.append(e)
    return None if '"self"' in json.dumps(effects) else {**d, "effects": effects}


def define(ability: AbilityText, ch: Characteristics) -> Definition | None:
    """The engine definition of one ability, or None (manual)."""
    from app.rules import abilities_of

    if abilities_of.manual(ability):  # (review 18F: a borrowed linked or modal ability, 607.5)
        return None
    view = _granter_view(ability) if "‹granter" in ability.text else None
    d = _define(view[0] if view else ability, ch)
    if view and d is not None:
        d = _granter_bound(d, view[1])
    # -- exiled with (wave 6D) -- 607.2a linked abilities (app/rules/exiled_with.py)
    from app.rules import exiled_with

    d = exiled_with.link(d, ability, ch)
    from app.rules import kicked_instead  # -- kicked / instead (wave 4G) -- 702.33g: a spell's targets only

    if d is not None and d.get("kind") != "spell" and kicked_instead.has_kicked_groups(d):
        return None
    cond = d.get("cond") if d is not None and d.get("kind") == "triggered" else None
    if cond is not None and cond.get("event") == "enter" and cond.get("aggregate"):
        # "Whenever one or more artifacts you control enter, ~ deals that much damage": the number of them (603.2c)
        d = json.loads(json.dumps(d, default=str).replace('{"event_amount": 1}', '{"event_count": 1}'))
    # -- sized amounts (wave 3D) -- "the sacrificed creature's power" reads what a *cost* sacrificed (the payment record):
    # in any other ability (an effect sacrificed it, a spell's additional cost) it isn't read
    if d is not None and '"cost:discarded"' in json.dumps(d, default=str):  # -- as long as (wave 9B) -- one card discarded to pay
        cost = parse_ability_cost(ability.cost, card_name=ch.name) if d.get("kind") == "activated" and ability.cost else None
        if cost is None and d.get("kind") == "spell":
            cost = spell_additional_cost(ch.abilities)
        if cost is None or [c.kind for c in cost.components].count(DISCARD) != 1 or not any(
                c.kind == DISCARD and c.selector is not None and c.amount == 1 for c in cost.components):
            return None
    if d is not None and ("cost:revealed" in json.dumps(d, default=str) or '"rev:' in json.dumps(d, default=str)):  # -- static_other sweep (wave 17C) --
        cost = spell_additional_cost(ch.abilities) if d.get("kind") == "spell" else None  # (a spell's additional cost revealed it)
        if cost is None or [c.kind for c in cost.components].count("REVEAL_FROM_HAND") != 1 or cost.either:
            return None
    if d is not None and "cost:sacrificed" in json.dumps(d, default=str):
        cost = parse_ability_cost(ability.cost, card_name=ch.name) if d.get("kind") == "activated" and ability.cost else None
        if cost is None and d.get("kind") == "spell":  # -- costs (wave 3$) -- a spell's additional cost ("sacrifice a creature")
            cost = spell_additional_cost(ch.abilities)
        if cost is None or not any(c.kind == SACRIFICE and c.selector is not None for c in cost.components):
            return None
    # -- refused zones/sized (wave 3R4) -- a triggered ability's X is not the X its source was cast with
    # (107.3m isn't carried to triggers: X reads 0 there), so a search sized by X in one stays manual (Fblthp)
    # -- cast X (wave 4J) -- except an enters trigger of the object itself: 107.3m gives it the X of the spell it was
    # (triggers.cast_x)
    if d is not None and d.get("kind") == "triggered" and d.get("trigger") != "enters_self" and \
            '{"x": 1}' in json.dumps([e for e in d.get("effects") or [] if e.get("do") == "search"]):
        return None
    # -- unless pays (wave 4C) -- likewise "unless that player pays {X}" with no X defined: only a spell's or an
    # activated ability's X (107.3a/107.3k) sizes the payment
    if d is not None and d.get("kind") == "triggered" and \
            '{"x": 1}' in json.dumps([e.get("n") for e in d.get("effects") or [] if e.get("do") == "optional_payment"]):
        return None
    if d is not None and d.get("kind") != "spell" and '"spell_self_move"' in json.dumps(d, default=str):
        return None  # -- counters (wave 7C) -- only a spell moves itself off the stack
    if d is not None and this_way.unbound(d):  # -- "this way" outcomes (wave 4A) -- a count no instruction bound
        return None
    from app.rules import (
        per_opponent,  # -- per-opponent targets (wave 12C) -- only a triggered ability's own group
    )

    if d is not None and not per_opponent.allowed(d):
        return None
    # -- defending player (wave 6D) -- only an attacking creature's trigger names one (508.5: app/rules/defending.py)
    from app.rules import defending

    if d is not None and not defending.allowed(d):
        return None
    # -- blocking it (wave 6D) -- "each creature blocking it": "it" must be the source (a trigger about this object)
    # -- activated sweep (wave 17B) -- or an activated ability of the source: "{R}: This creature deals 1 damage to target creature blocking it."
    # (its own cost doesn't sacrifice it: the block is read while it's there, _event_refs_ok)
    if d is not None and "blocking_source" in json.dumps(d, default=str) and not (
            d.get("kind") == "activated" or d.get("kind") == "triggered" and (
                str(d.get("trigger", "")).endswith("_self") or (d.get("cond") or {}).get("subject") == "self")):
        return None
    # -- combat (wave 5C) -- "attacks each combat if able" needs its duration
    from app.rules import combat_rules

    if d is not None and combat_rules.unwrapped(d):
        return None
    # -- mana riders (wave 5A) -- 605.1b: adding mana makes it a mana ability
    from app.rules import tap_mana as _tm

    if d is not None and _tm.adds_mana(d):
        return None
    # -- other players' choices (wave 12D) -- "{T}: That player adds {G}" without a target would be a mana ability (605.1a): no
    # stack, which the engine doesn't do for another player's pool -- manual. (With a target it is not one.)
    if d is not None and d.get("kind") == "activated" and any(
            e.get("do") == "add_mana" and e.get("who") not in (None, "target") for e in d.get("effects") or []):
        return None
    # -- chosen player (wave 4J) -- "the chosen player" is the one this permanent chose as it entered (app/rules/chosen.py):
    # only on a card with exactly one "As ~ enters, choose an opponent / a player." ("Choose target opponent. … the chosen
    # player" in one resolution — Haunt the Network — is another choice: not read as this)
    if d is not None and _chosen.WHO in json.dumps(d, default=str) and not _chosen.chooses_player(ch):
        return None
    if d is not None and not _chosen.chosen_value_ok(d, ch):  # -- chosen type (wave 4J) -- "of the chosen type / color"
        return None
    # -- discover (wave 9A) -- the free cast ends the resolution (effects.resume_suspend_cast): nothing may follow it
    if d is not None and any(e.get("do") == "discover" for e in (d.get("effects") or [])[:-1]):
        return None
    # -- X sized by a count (wave 4K) -- a bare X left in an ability whose text defines X ("Create an X/X … token, where X
    # is half your life total, rounded up. It deals X damage to you."): one X for the whole ability (107.3c) that a later
    # sentence would read as 0 — manual. And a triggered ability's bare X other than an enters trigger's (107.3m, the
    # cast X: triggers.py) is some cost's X the trigger isn't given ("When you cycle this card, create an X/X …": the
    # cycling cost's): manual too.
    # (wave 19F: or its own "When this creature becomes monstrous" with a "Monstrosity X" ability on the card: that X, 701.37c)
    monstrous_x = d is not None and (d.get("cond") or {}) == {"subject": "self", "event": "become_monstrous"} and any(
        "Monstrosity X" in a.text for a in ch.abilities) and "where X is" not in ability.text
    if d is not None and '{"x": 1}' in json.dumps(d.get("effects") or [], default=str) and (
            re.search(r"\bwhere X is\b", ability.text)
            or (d.get("kind") == "triggered" and d.get("trigger") != "enters_self" and not monstrous_x)):
        return None
    # -- review (wave 12C) -- the X a selector compares with ("with mana value X or less": selectors.X_VALUE, the cast X) or
    # the stand-in number of _where_x, left in any field: that X isn't what "where X is" defines — manual
    from app.rules import selectors  # (a leaf module)

    if d is not None and re.search(r"\bwhere X is\b", ability.text) and re.search(
            rf'(?<![\d-]){_X_SENTINEL}(?!\d)|,{selectors.X_VALUE}\]', json.dumps(d, default=str)):
        return None
    if d is not None and d.get("kind") == "triggered" and '"x_count"' in json.dumps(d, default=str) and not (
            monstrous_x or (d.get("trigger") == "enters_self" and "{X}" in (ch.mana_cost or "") and "where X is" not in ability.text)):
        return None  # ("up to X target …" in a trigger: its targets are chosen before any X is known to it; wave 19F: but the X an
        # enters trigger of a spell cast with X, or a becomes-monstrous trigger, is given: triggers.cast_x)
    # -- entry forms (wave 5F) -- "It's an enchantment." only right after a return
    from app.rules import entry_forms

    if d is not None and not entry_forms.enters_as_bound(d.get("effects") or []):
        return None
    if d is not None:  # "becomes a copy of …, except it has this ability" (707.9a): this ability's own line
        from app.rules import copying

        d = copying.with_this_ability(d, ability.text)
    return d


def _define(ability: AbilityText, ch: Characteristics) -> Definition | None:
    """The engine definition of one ability, or None (manual)."""
    from app.rules import (
        merged,  # -- merged permanents (wave 18D) -- meld wordings carry card names with commas
    )

    text = self_text(merged.protect(ability.text), ch.name)
    if ability.kind == "keywords" and ability.keywords in (("spectacle",), ("surge",), ("blitz",), ("warp",), ("bestow",), ("prowl",), ("overload",), ("emerge",), ("foretell",), ("mutate",)):  # -- keywords (wave 15E) -- alt_costs
        from app.rules import alt_costs

        return alt_costs.keyword_definition(ability.text)
    if ability.kind == "keywords" and ability.keywords == ("unleash",):  # -- keywords (wave 15E) -- 702.98a's second static
        return parse_anthem("~ can't block as long as it has a +1/+1 counter on it.")
    if text.startswith("Cast this spell only "):  # -- cast timing (wave 7A) -- 601.3 (app/rules/cast_timing.py)
        from app.rules import cast_timing

        return cast_timing.definition(text)
    if "Saga" in ch.subtypes:  # -- sagas & attached-object triggers (wave 3S): chapter abilities, read ahead (714, 702.155) --
        from app.rules import sagas

        if sagas.chapters_of(ability.text):
            return sagas.chapter_definition(ability, ch)
        if ability.kind == "keywords":
            return sagas.read_ahead_definition(ability, ch)
    if ability.kind == "triggered" and text.startswith("Whenever enchanted land is tapped for mana"):
        # -- attached events (wave 4L) -- a triggered mana ability (605.1b)
        from app.rules import attached_mana

        return attached_mana.definition(text)
    if ability.kind == "triggered" and (text.startswith(("Whenever you tap ", "Whenever a player taps "))
                                        or re.match(r"Whenever an? [^,]+ is tapped for mana, its controller adds ", text)):
        from app.rules import tap_mana  # -- mana riders (wave 5A) -- a triggered mana ability (605.1b)

        if (tapped := tap_mana.definition(text)) is not None:
            return tapped
    if ability.kind == "static" and text.startswith("While voting, "):  # -- voting (wave 18C) -- 701.38d
        from app.rules import voting

        return voting.static_definition(text)
    if ability.kind == "static" and ("opening hand" in text or text.startswith("Any time you could mulligan")):  # -- opening hand (wave 18C) -- 103.6 (app/rules/opening_hand.py)
        from app.rules import opening_hand

        return opening_hand.definition(text, ch)
    if ability.kind == "static" and text.startswith("You may exert "):  # -- static wordings (wave 6E) -- 701.43d
        from app.rules import exert

        return exert.definition(text, ch, ability.index)
    if ability.kind == "static" and text.startswith("If ") and "mana, it produces" in text:
        from app.rules import mana_replace  # -- mana replacements (wave 9C) -- 106.12b

        if (replaced := mana_replace.definition(text)) is not None:
            return replaced
    if ability.kind == "static" and (untap_limit := _untap_choice.static_definition(text)) is not None:
        return untap_limit  # -- untap restrictions (wave 13E) -- "Players can't untap more than one creature during their untap steps."
    if ability.kind == "static" and (untaps := _untap_riders.static_definition(text)) is not None:
        return untaps  # -- mana riders (wave 5A) -- "Untap all … you control during each other player's untap step."
    if ability.kind == "static":
        # replacement / prevention effects of the permanent itself (the block at the end of this
        # module): "~ enters tapped [unless …]", shock lands, "~ enters with … counters", "If ~ would
        # die, exile it instead", "Prevent all …"
        replacement = define_replacement(ability, text)
        if replacement is not None:
            return replacement
    if ability.kind == "static" and (copied := _copy_static(text)) is not None:  # -- copy system (wave 2F) --
        return copied
    if ability.kind == "static":  # -- combat (wave 5C) -- attack costs and limits, "can't block creatures you control"
        from app.rules import combat_rules

        if (found := combat_rules.static_definition(text)) is not None:
            return found
    if ability.kind == "static":  # -- type statics (wave 5F) -- "Each land is a Swamp in addition …" (613.1d, 305.7)
        from app.rules import type_statics

        if (typed := type_statics.parse(text)) is not None:
            return typed
    if ability.kind == "static" and (anthem := parse_anthem(text)) is not None:
        return anthem
    if ability.kind == "static":  # -- as long as (wave 9B) -- "… as long as it's black. Otherwise, it gets -1/-2." (app/rules/static_pairs.py)
        from app.rules import static_pairs

        if (paired := static_pairs.definition(text)) is not None:
            return paired
    if ability.kind == "static" and (rule := attached_rule(text)) is not None:
        return rule
    if ability.kind == "static" and re.fullmatch(r"You control enchanted (?:creature|permanent|land|artifact)\.", text):
        return {"kind": "static", "static": "control", "who": "host", "effects": []}  # -- control (wave 3K) -- layer 2 (613.1b)
    if ability.kind == "static" and text == "If it's neither day nor night, it becomes day as ~ enters.":
        return {"kind": "static", "static": "day_as_enters", "effects": []}  # (wave 3E: app/rules/designations.py, 731.1)
    if ability.kind == "static" and text == "~ can be your commander.":
        return {"kind": "static", "static": "deckbuilding", "effects": []}  # 903.3a: deck construction only
    # -- static_other sweep (wave 19A) -- 510.1c: "You may have this creature assign its combat damage as though it weren't blocked."
    if ability.kind == "static" and re.fullmatch(r"You may have (?:~|this creature) assign (?:its|his|her|their) combat damage as though "
                                                 r"(?:it|he|she|they|~) weren't blocked\.", text):
        return {"kind": "static", "static": "assign_unblocked", "effects": []}
    if ability.kind == "static" and text in COMBAT_STATICS:
        return {"kind": "static", "static": COMBAT_STATICS[text], "effects": []}
    if ability.kind in ("static", "spell"):
        from app.rules import permissions  # permissions, cost modifiers, "play with the top card revealed"

        granted = permissions.define_static(text, ability.kind, tuple(self_text(ab.text, ch.name) for ab in ch.abilities))
        if granted is not None and granted.get("static") in ("alt_cost", "cost_modifier") and "Room" in ch.subtypes:
            return None  # -- cost changers (wave 4I) -- a Room door's ability works only while it's unlocked: not modelled
        if granted is not None:
            return granted
    if ability.kind == "triggered":
        text = re.sub(r"^((?:When|Whenever) [^,]+?) while this card is in your graveyard, ", r"\1, if this card is in your graveyard, ", text)  # (wave 19C)
        # -- counters sweep (wave 19D) -- "At the beginning of your upkeep and whenever you cast a white spell, …" (the Shrines): the same
        # two conditions as "Whenever you cast a white spell and at the beginning of your upkeep, …" (603.2: it triggers on each)
        text = re.sub(r"^At the beginning of your (upkeep|end step) and (?:when|whenever) ([^,]+), (.+)$",
                      r"Whenever \2 and at the beginning of your \1, \3", text)
        for pattern, trigger in TRIGGERS:
            m = pattern.match(text)
            if m and trigger == "event":  # -- triggers (wave 5D) -- a condition with commas in it ("an Aura, Equipment,
                from app.rules import trigger_words  # or Vehicle spell", "a noncreature, nonland card")

                m = trigger_words.comma_condition(text, m)
            if m and trigger == "cast_you" and re.search(r"\bthat spell\b|\bcopy it\b|\bthe amount of mana you spent\b|\bwas spent to cast it\b", m["body"]):  # (3R3: copy it; wave 16B: increment; 18B: mana spent)
                continue  # -- sized amounts (wave 3D) -- it reads the spell cast: the generic condition's event carries it
            if m:
                name = step_trigger(m) if trigger == "step" else trigger
                if name.startswith("step:") and not name.endswith(":you") and re.search(r"\beach other player\b", m["body"]):
                    return None  # -- if you do (wave 5G) -- "other" than whose step it is, or than you? (not read)
                # -- trigger limits (app/rules/restrictions.py): "This ability triggers only once
                # each turn." is split off and enforced as it triggers (triggers._add); "Do this
                # only once each turn." (603.2h) isn't modeled yet: the ability stays manual
                body, limit = restrictions.split_trigger_limit(m["body"])
                if limit in restrictions.TRIGGER_LIMIT_REFUSED:
                    return None
                if trigger == "state" and "counters on" in m["state"]:  # (wave 19D: a state about ~'s own counters: "it" is ~)
                    body = re.sub(r"^(exile|sacrifice) it\b", r"\1 ~", body)
                kicked = re.match(r"^if (?:it|~) was kicked, (?P<rest>.+)$", body) if name in ("enters_self", "cast_self") else None  # (wave 20F: cast_self, 702.33d)
                if kicked is not None:  # 603.4 intervening "if": checked as it triggers (triggers._add)
                    body = kicked["rest"]
                cond = None
                if trigger == "event":
                    from app.rules import events as event_grammar  # (a leaf module)

                    # -- triggers (wave 5D) -- "When ~ enters and whenever an opponent draws a card …" (Orcish
                    # Bowmasters): one ability, two trigger conditions — it triggers on each (603.2)
                    both = re.fullmatch(r"(?P<a>.+?) and (?:(?:when|whenever) |(?=at the beginning of your (?:upkeep|end step)))(?P<b>.+)", m["cond"])
                    pair = (both["a"], both["b"]) if both else None
                    if pair is None and event_grammar.parse_condition(m["cond"]) is None and (
                            either := re.fullmatch(r"(~ (?:enters|dies|attacks)) or ((?:becomes|deals|enters|dies|attacks) .+)", m["cond"])):
                        pair = (either[1], "~ " + either[2])  # "~ enters or becomes monstrous": each its own (603.2)
                    halves = [_half_trigger(pair[0]), _half_trigger(pair[1])] if pair else []
                    if pair:  # -- trigger tail (wave 15B) -- two conditions, at most one of them generic: "When you cycle this
                        # card and when ~ dies", "When you cast this spell and whenever ~ attacks" (603.2: it triggers on each)
                        if None in halves:
                            return None
                        names = [h[0] for h in halves if h]
                        generic = [h[1] for h in halves if h and h[1] is not None]
                        if names == ["event", "event"] and generic[0]["event"] != generic[1]["event"] and not re.search(
                                r"\b(?:it|its|it's|that|those|them|they)\b", re.sub(r"\bit's the \w+ time\b", "", m["body"])) and not any(
                                g.get("aggregate") or g["event"] in ("either", "multi") for g in generic):
                            # -- ability words (wave 20C) -- "Whenever an enchantment you control enters and whenever you fully unlock a
                            # Room" (eerie): two whole conditions, each its own event (603.2c) — the "or" form's either condition
                            cond = {"event": "either", "conds": generic,
                                    "subject": generic[0]["subject"] if generic[0]["subject"] == generic[1]["subject"] else "mixed"}
                            name = "event"
                        elif len(set(names)) < 2 or len(generic) > 1:
                            return None
                        else:
                            cond = generic[0] if generic else None
                            name = "multi:" + "+".join(names)
                    else:
                        cond = event_grammar.parse_condition(m["cond"])
                        if cond is None:
                            return None
                        name = _legacy_trigger(cond) or "event"
                if cond is not None and cond.get("event") == "activate" and not cond["loyalty"]:
                    # -- activation (wave 11F) -- only non-mana abilities use the stack (605.3b): "if it isn't a mana ability"
                    # (Harsh Mentor) is the same as "that isn't a mana ability"; without either, mana abilities would trigger it
                    nm = re.match(r"^if it isn't a mana ability, ", body)
                    if nm:
                        body = body[nm.end():]
                    elif not cond["nonmana"]:
                        return None
                # (a trigger about a player, or damage to one, names them: "that player")
                has_player = cond is not None and _has_player(cond)
                if cond is not None and cond.get("event") == "cast" and cond.get("player") == "you":
                    has_player = False  # -- ability words (wave 9C) -- "Whenever you cast …, target player mills …. … that player
                    # mills ten cards instead" (Exhibition Tidecaller): the caster is "you", never "that player"
                # -- sagas & attached-object triggers (wave 3S) -- "When enchanted creature dies, return
                # this card to its owner's hand": the Aura's new object in its owner's graveyard (400.7f)
                aura_card = cond is not None and cond.get("subject") == "host" and cond["event"] in _GONE \
                    and re.search(r"\bthis card\b", body) is not None
                if aura_card:
                    body = re.sub(r"\bthis card\b", "~", body)
                # -- attached events (wave 20A) -- "Whenever enchanted creature attacks, put a +1/+1 counter on it. Then if it has three or more
                # +1/+1 counters on it, sacrifice this Aura." (the Ordeals): the "it" that got the counter is the creature (or ~ itself)
                if cond is not None and cond.get("subject", "self") in ("self", "host"):
                    body = re.sub(r"(counters? on it\. Then if )it( has \w+ or more [^,.]+? counters on it,)",
                                  rf"\g<1>{'enchanted creature' if cond.get('subject') == 'host' else '~'}\2", body)
                if _trigger_antecedent(name, cond) is None:  # -- step triggers (wave 4J) -- "At the beginning of your draw
                    # step, if this artifact is tapped, it deals 1 damage to you." (Mana Vault): the only object named is ~
                    body = re.sub(r"^(if ~ is (?:tapped|untapped)), it deals ", r"\1, ~ deals ", body)
                # -- attached events (wave 4L) -- "Whenever enchanted player is attacked, create a Gold token. Each
                # opponent attacking that player does the same." (app/rules/attached_players.py)
                from app.rules import attached_players

                same, body = attached_players.split_same(body, cond)
                # -- triggers (wave 5D) -- "they lose 2 life", "an additional card"
                from app.rules import trigger_words

                if cond is not None and cond.get("subject") == "source" and re.search(r"\b(?:that player|they|them)\b", body):
                    return None  # -- source damage (wave 11F) -- the source's controller, or the player dealt damage? (not read)
                body = trigger_words.rewrite_body(body, name, cond, has_player)
                if name == "step:draw:you":  # -- draw step (wave 6D) -- "At the beginning of your draw step, draw an
                    # additional card.": a triggered ability that draws, after the draw of 504.1 (504.2)
                    body = re.sub(r"^(you may )?draw (an|two|three) additional (cards?)(?=\.)",  # (wave 18G: "you may draw two additional
                                  lambda m: f"{m[1] or ''}draw {'a' if m[2] == 'an' else m[2]} {m[3]}", body)  # cards. If you do, …")
                # -- other side (wave 6D) -- "… blocks a creature, destroy that creature. You gain life equal to that
                # creature's toughness" / "… deals damage to a creature, …": the event's object (app/rules/other_side.py)
                from app.rules import other_side

                if cond is not None and other_side.wanted(cond) and cond.get("subject") == "host" and "that creature" not in body:
                    body = body.replace("the other creature", "that creature")  # (wave 11E: Venom, Mammoth Harness)
                if cond is not None and other_side.wanted(cond) and cond.get("subject", "self") == "self":
                    # -- trigger tail (wave 15B) -- "When this creature blocks a creature, destroy both creatures / that creature and
                    # this creature.": the creature on the other side, then this one (509.3b)
                    body = re.sub(r"^destroy (?:both creatures|that creature and ~)\.$", "destroy that creature. Destroy ~.", body)
                ante = _trigger_antecedent(name, cond) or other_side.antecedent(cond, body)
                if ante == "self_gone":  # -- trigger tail (wave 15B) -- "put her into her owner's library third from the top"
                    # (a gendered pronoun is written ~): the card after it left, found where it went (400.7e), like "it"
                    body = re.sub(r"\bput ~ into ~'s owner's library\b", "put it into its owner's library", body)
                body = _may_have(body, ante)  # -- trigger tail (wave 15B) --
                to_gy = cond is not None and cond.get("event") == "to_graveyard" and cond.get("subject") == "self"
                if to_gy:  # -- trigger tail (wave 15B) -- 603.6c: the card is in its owner's graveyard, whose owner controls the ability
                    body = {"shuffle it into its owner's library.": "shuffle ~ into its owner's library.",
                            "its owner shuffles their graveyard into their library.":
                                "shuffle your graveyard into your library."}.get(body, body)
                if ante is None and (cond is None or cond.get("subject") == "player") and re.match(r"^if ~ ", body) \
                        and name not in ("cast_you", "cast_self") and (cond or {}).get("event") != "cast":
                    # -- intervening ifs (wave 11F) -- "At the beginning of your upkeep, if ~ has no charge counters on it, return
                    # it …": a step or a player's event names no object, so the "if" names the only one: ~
                    ante = "self"
                # -- unless pays (wave 20E) -- "Whenever ~ becomes the target of a spell or ability an opponent controls, counter that
                # spell or ability unless its controller pays {2}." (ward's own text, 702.21a): the spell or ability the event names
                tm = re.fullmatch(r"counter that spell or ability unless its controller pays ((?:\{[^}X]+\})+)\.?", body)
                counter_it: list[dict[str, Any]] = [{"do": "counter_unless", "who": "event_source", "cost": tm[1]}] if tm else []
                parsed = parse_effects(body, it=ante, event_player=has_player) if tm is None or (cond or {}).get("event") != "targeted" \
                    else (counter_it, None, False)
                # -- damage wordings (wave 6B) -- "Whenever ~ blocks or becomes blocked by a creature, ~ deals 1 damage to
                # that creature" (509.3c-d: once per creature on the other side): that creature is the event's ``other``
                if parsed is None and cond is not None and cond.get("other") and cond.get("subject", "self") in ("self", "host") and (
                        cond["event"] in ("block", "blocked")
                        or (cond["event"] == "multi" and set(cond["events"]) <= {"block", "blocked"})):
                    from app.rules.language import OTHER_SIDE

                    if cond.get("subject", "self") == "self":
                        body = re.sub(r"^it deals ", "~ deals ", body)
                    body = body.replace("that creature's controller", OTHER_SIDE + "'s controller")
                    body = body.replace("that creature", OTHER_SIDE)
                    ante = _trigger_antecedent(name, cond)
                    parsed = parse_effects(body, it=ante, event_player=has_player)
                if same and parsed is not None:
                    parsed = attached_players.does_the_same(parsed)
                if parsed is None:  # -- this-turn history (wave 4D) -- "…, if [condition], you may …" (603.4 + 603.5)
                    parsed = _intervening_may(body, ante, has_player)
                if parsed is None:
                    return None
                effects, target, optional = parsed
                if to_gy or any(e.get("who") == "self_gy" for e in effects):  # (-- casting extras (wave 18E) -- recover: "If you don't, exile ~" too)
                    effects = [{**e, "who": "self_gy"} if e.get("who") == "self" else e for e in effects]
                if aura_card:
                    aura_effects = _aura_card_effects(effects)
                    if aura_effects is None:
                        return None
                    effects = aura_effects
                # 603.4: "When/Whenever/At …, if [condition], …" — an intervening "if": checked as it
                # triggers (triggers._add) and again as it resolves (the only_if effect)
                intervening = None
                if body.lower().startswith("if "):
                    if not effects or effects[0]["do"] != "only_if" or effects[0].get("bind"):
                        return None  # (with "Otherwise, …" the condition isn't the whole ability's: wave 1B)
                    # the whole ability, however many sentences follow: if it doesn't hold, the
                    # ability doesn't trigger, or does nothing as it resolves
                    intervening = effects[0]["cond"]
                    effects = [{**effects[0], "skip": len(effects) - 1}, *effects[1:]]
                    if intervening == {"object": "self", "test": "in_graveyard"}:  # -- graveyard triggers (wave 19C) -- "it" is the card there
                        effects = [{**e, "who": "self_gy"} if e.get("who") == "self" else e for e in effects]
                # (-- intervening ifs (wave 11F) -- a step, or an event about a player, has no other object: "another" is
                # "other than ~", 603.4)
                alone = _trigger_antecedent(name, cond) is None and (cond is None or cond.get("subject") == "player")
                if _trigger_antecedent(name, cond) != "self" and not alone and any(
                        e["do"] == "only_if" and _condition_says_other(e["cond"]) for e in effects):
                    return None  # ("other" than the object the event happened to, not ~: not modeled)
                out = {"kind": "triggered", "trigger": name,
                       "effects": effects, "optional": optional, **target_fields(target)}
                if cond is not None and "event" in name.removeprefix("multi:").split("+"):  # (wave 5D, 15B)
                    out["cond"] = cond
                if intervening is not None:
                    out["if"] = intervening
                    if intervening == {"object": "self", "test": "in_graveyard"}:
                        out["gy_watch"] = True  # -- graveyard triggers (wave 19C) -- it sees the events that come after the card is there
                if kicked is not None:
                    out["if_kicked"] = True
                if limit is not None:
                    out["limit"] = restrictions.limit_kind(limit)
                if "filter" in pattern.groupindex:
                    out["filter"] = m["filter"]
                from app.rules import (
                    conditions as _conds,  # (-- kicked instead (wave 20F) -- "if it was kicked": the spell's own record, 601.2h)
                )

                if (trigger == "cast_self" or "cast_self" in name) and re.search(r'"(?:self|event)', json.dumps(
                        [e for e in effects if not (e["do"] == "only_if" and _conds.is_cast_condition(e["cond"]))], default=str)):
                    return None  # -- cast triggers (wave 6D) -- the spell itself is on the stack: not read as "~"
                if trigger == "state":  # -- state triggers (wave 6D) -- 603.8
                    from app.rules import state_triggers

                    state = state_triggers.condition(m["state"])
                    if state is None or intervening is not None or limit is not None:
                        return None
                    out["state"] = state
                return out
        return None
    if ability.kind == "spell":
        parsed = _own_choice(parse_effects(text))  # (_own_choice: wave 3R5)
        if parsed is None or parsed[2]:
            return None
        effects, target, _ = parsed
        return {"kind": "spell", "effects": effects, **target_fields(target)}
    if ability.kind == "loyalty" and ability.cost:
        # 606: a loyalty ability is an activated ability; its cost (loyalty counters) is paid on
        # activation (casting.activate_to_stack), its effect uses the same grammar
        cost = parse_ability_cost(ability.cost, card_name=ch.name, loyalty=True)
        if cost.unsupported:
            return None
        parsed = parse_effects(text.split(":", 1)[1])
        if parsed is None or parsed[2]:
            return None
        effects, target, _ = parsed
        return {"kind": "activated", "loyalty": True, "cost": ability.cost, "effects": effects,
                **target_fields(target)}
    if ability.kind == "activated" and ability.cost:
        cost = parse_ability_cost(ability.cost, card_name=ch.name)
        if cost.unsupported:
            return None
        # -- activation restrictions (app/rules/restrictions.py): the trailing "Activate only …"
        # sentences are split off the effect and enforced as it's activated (casting.ability_problem);
        # a restriction the engine doesn't read leaves the ability manual
        if ability.text.startswith("Power-up — "):  # -- counters (wave 7C) -- 702.193: the reduction must be readable
            from app.rules import power_up

            if not power_up.readable(ch, cost.mana):
                return None
        body, restriction = restrictions.split(text.split(":", 1)[1])
        parsed_restriction = restrictions.parse(text) if restriction is not None else []
        if parsed_restriction is None:
            return None
        if any(x["kind"] == "any_player" for x in parsed_restriction) and (  # -- activation wordings (wave 7B) --
                cost.tap or cost.sacrifice_self or cost.untap):  # (only the controller can pay {T} or sacrifice it)
            return None
        # -- cost changers (wave 4I) -- "This ability costs {1} less to activate for each …" is part of its total cost
        # (602.2b → 601.2f; casting.ability_cost reads it), not of what it does
        from app.rules import cost_changes

        body, own_cost = cost_changes.split_ability(body)
        if own_cost is not None and (not cost_changes.ability_change(text) or "{X}" in (ability.cost or "") or not cost.mana):
            return None
        # -- end cost changers (wave 4I) --
        # -- sized amounts (wave 3D) -- "Sacrifice this creature: It deals damage equal to its power": "it" is the source
        # the cost put into a graveyard (its last known information: 608.2h)
        gone = cost.sacrifice_self or re.search(r"\b(?:[Dd]iscard|[Ee]xile) (?:this card|~)", ability.cost or "") is not None
        # -- small wordings (wave 11E) -- "Remove a +1/+1 counter from this creature: It deals 1 damage …": the only object
        # the cost names is the source, so "it" is the source itself (a cost that names another object stays unbound)
        # -- activated wordings (wave 15D) -- also with mana, {T}, life or an exert beside it: "{T}, Remove a javelin counter from this
        # creature: It deals 1 damage to any target." (the only object any part names is the source)
        own = "self" if re.fullmatch(r"(?:(?:(?:\{[^}]+\})+|Pay \d+ life|Exert (?:~|this \w+)), )*Remove [^,]+ counters? from (?:~|this \w+)"
                                     r"(?:, (?:(?:\{[^}]+\})+|Pay \d+ life|Exert (?:~|this \w+)))*",
                                     self_text(ability.cost or "", ch.name)) else None
        # -- activated sweep (wave 17B) -- "{T}, Exert this creature: It deals 1 damage to target creature.": the exerted object is the source
        if own is None and re.fullmatch(r"(?:(?:(?:\{[^}]+\})+|Pay \d+ life), )*Exert (?:~|this \w+)(?:, (?:(?:\{[^}]+\})+|Pay \d+ life))*",
                                        self_text(ability.cost or "", ch.name)):
            own = "self"
        if any(c.kind == SACRIFICE and c.selector is not None for c in cost.components) and "target" not in body:
            # -- X sized by a count (wave 19F) -- "Sacrifice another creature: Draw X cards, where X is that creature's power.": the only
            # object the cost names (as it last existed, 608.2h), read as "the sacrificed creature's power"
            body = re.sub(r"\bthat (creature|permanent|artifact|enchantment|land)'s (?=power|toughness|mana value)", r"the sacrificed \1's ", body)
        # -- activated sweep (wave 19E) -- "This creature gets +2/+0 and gains indestructible until end of turn. Tap it.": the only
        # object the ability names is the source, so "it" is that creature
        body = re.sub(r"^(\s*~ (?:gets|gains) [^.\"]+\.) Tap it\.$", r"\1 Tap ~.", body)
        parsed = _own_choice(parse_effects(body, "self_gone" if gone else own))  # (_own_choice: wave 3R5)
        if parsed is None or parsed[2]:
            return None
        effects, target, _ = parsed
        out = {"kind": "activated", "cost": ability.cost, "effects": effects, **target_fields(target)}
        if parsed_restriction:
            out["restriction"] = parsed_restriction
        return out
    return None


# Trigger events that come with an amount ("that much" / "that many", TriggerEvent.amount): life
# gained / lost, damage dealt, counters put; for a "one or more" batch of sacrifices, discards,
# tokens created … the number of them (603.2c)
_AMOUNT_EVENTS = {"gain_life", "lose_life", "dealt_damage", "deal_damage_opponent", "deal_combat_damage_player",
                  "deal_damage", "counters_put", "discard", "sacrifice", "create_token", "cycle", "leave_graveyard",
                  "player_counters", "mill", "attack", "scry"}  # (player_counters: wave 3E, "you get that many {E}"; scry: wave 19C, the cards looked at)


_PLAYER_EVENTS = {"deal_combat_damage_player", "deal_damage_opponent"}  # events with a player dealt damage


# -- this-turn history (wave 4D) --
def _intervening_may(body: str, it: str | None, event_player: bool) -> tuple[list[dict[str, Any]], Any, bool] | None:
    """"At the beginning of each end step, if a creature died this turn, you may draw a card.": an intervening "if"
    (603.4: checked as it triggers and as it resolves) over an optional ability (603.5: the choice is made as it
    resolves) — the gate over the whole of the rest. A condition about an object ("if it's …") isn't read here."""
    from app.rules import conditions

    # (-- long tail (wave 16D) -- the rest may be any instructions, "…, you draw a card. If seven or more creatures died this
    # turn, instead you draw seven cards.": the gate is still over the whole ability, 603.4)
    m = re.match(r"^if (?P<c>[^,]+), (?P<rest>.+)$", body.strip(), re.DOTALL)
    if m is None:
        return None
    cond = conditions.parse(m["c"], objects=True)
    if cond is None or set(conditions.objects_in(cond)) - {"self"}:
        return None
    # -- if you do (wave 10C) -- "At the beginning of your upkeep, if this creature has a +1/+1 counter on it, you may remove a
    # +1/+1 counter from it. If you do, draw a card." (Ingenious Prodigy): the only object the condition names is the source, so
    # the "it" of the sentence after it is that object (the pronoun's nearest antecedent, 608.2c)
    about_self = it is None and "self" in str(cond)  # ({"object": "self", …} or {"value": {"on": "self"}, …})
    parsed = parse_effects(m["rest"][0].upper() + m["rest"][1:], it="self" if about_self else it, event_player=event_player)
    if parsed is None or not parsed[0]:
        return None
    effects, target, optional = parsed
    return [{"do": "only_if", "cond": cond, "skip": len(effects)}, *effects], target, optional
# -- end this-turn history (wave 4D) --


def _has_player(cond: dict[str, Any]) -> bool:
    """Does the event name a player ("that player")? The player who acted, or who was dealt damage."""
    if cond.get("subject") == "player" or cond["event"] in _PLAYER_EVENTS:
        return True
    if cond["event"] == "targeted" and cond.get("by") in ("opponent", "you"):  # -- triggers (wave 19B) -- the player whose spell or ability it was
        return True
    # -- triggers (wave 5D) -- "Whenever a creature an opponent controls dies / enters, that player …": the opponent
    # who controlled it (one object per event: not "one or more", 603.2c; triggers._event)
    if cond.get("subject") == "sel" and cond["event"] in ("enter", "die", "leave") and not cond.get("aggregate") \
            and re.search(r'"controller":"(?:opponent|enchanted)"', str(cond.get("sel"))):
        return True
    # -- source damage (wave 11F) -- "that source's controller": the player who controlled the source (triggers._fire_generic)
    return cond["event"] == "deal_damage" and (cond.get("to") in ("player", "opponent", "you") or cond.get("subject") == "source")


def _wants_amount(value: Any) -> bool:
    if isinstance(value, list):
        return any(_wants_amount(v) for v in value)
    return isinstance(value, dict) and ("event_amount" in value or any(_wants_amount(v) for v in value.values()))


def _event_refs_ok(d: Definition) -> bool:
    """"That player" / "that much" name what a trigger event was about (its TriggerEvent): only a
    generic trigger condition whose event has that player or amount can use them. A "one or more"
    trigger has one event per batch (603.2c) — per damaged player for damage to players, per
    acting player for a player's actions — so it can too."""
    effects = [e for e in d.get("effects") or []] + [e for m in d.get("modes") or [] for e in m.get("effects") or []]
    if not _event_spell_ok(d):  # -- refused copy/mana (wave 3R3) --
        return False
    # -- intervening ifs (wave 11F) -- "if that player controls …" / "if defending player has …" (603.4: read as it triggers
    # and as it resolves): only a trigger whose event names that player — the one the event is about, or the one attacked
    raw = json.dumps(d)
    ev = d.get("cond") if d.get("kind") == "triggered" and d.get("trigger") == "event" else None
    if '"spells_cast": "event_player"' in raw and not (  # -- triggers (wave 17D) -- "they … for each spell they've cast this turn": "they" is
            ev is not None and ev["event"] == "cast" and ev.get("subject") == "player"  # the casting player, who is also the recipient
            and all(e.get("who") == "event_player" for e in effects if '"spells_cast"' in json.dumps(e))):
        return False
    if '"turn": "event_player"' in raw and not (ev is not None and ev["event"] != "multi" and _has_player(ev)):
        return False  # -- triggers (wave 17D) -- "if it's not that player's turn": only a trigger whose event names a player
    if '"as": "event"' in raw and not (d.get("kind") == "triggered" and (step_names_player(d) or (
            ev is not None and ev["event"] != "multi" and _has_player(ev)))):
        return False
    if '\\"evt:' in raw and not (ev is not None and ev["event"] != "multi" and not ev.get("aggregate") and (
            ev.get("subject") in ("sel", "self", "self_or", "self_or_host", "host") or (ev.get("subject") == "player" and ev.get("obj")))):
        return False  # -- reanimation (wave 16F) -- "lesser mana value": than the one object the event is about
    if '"as": "defended"' in raw and not (d.get("trigger") == "attacks_self" or (
            ev is not None and ev["event"] in ("attack", "unblocked", "blocked", "you_attack"))):
        return False
    # -- damage wordings (wave 6B) -- "target artifact that player controls": the one player a trigger is about, bound
    # as it's put on the stack (triggers.bind_that_player) — never in a spell, nor beside a target player (which one?)
    # "target creature blocking it" / "it's blocking": "it" must be the source itself, still there to be read (a cost that
    # sacrifices it — Tinder Wall — leaves only its last known block, which isn't kept)
    if "blocking_source" in json.dumps(d) or "blocked_by_source" in json.dumps(d):
        self_trigger = d.get("kind") == "triggered" and _trigger_antecedent(str(d.get("trigger")), d.get("cond")) == "self"
        mine = d.get("kind") == "activated" and not re.search(r"\b[Ss]acrifice (?:this|~)", str(d.get("cost")))
        if not (self_trigger or mine):
            return False
    if '\\"controller\\":\\"that_player\\"' in json.dumps(d) or '\\"zone_owner\\":\\"that_player\\"' in json.dumps(d):
        cond = d.get("cond") if d.get("trigger") == "event" else None
        about_player = step_names_player(d) or (cond is not None and cond["event"] != "multi" and _has_player(cond))
        specs = [d.get("target") or {}, *(d.get("targets") or [])]
        if not about_player or any(str(s.get("what")) in ("player", "opponent", "any", "player_or_planeswalker",
                                                         "opponent_or_planeswalker") or str(s.get("what")).startswith("opponent_as:") for s in specs):
            return False
    from app.rules import watches  # -- turn watches (wave 7D) -- their deferred effects name their own event

    skip = watches.deferred_event_effects(effects)
    effects = [e for i, e in enumerate(effects) if i not in skip]
    wants_player = any(e.get("who") in ("event_player", "each_other_opponent")
                       or str(e.get("who")).startswith("controlled:event_player|") for e in effects) \
        or any(e.get("player") == "event_player" for e in effects)  # (wave 4E; "player": wave 6E)
    wants_amount = any(_wants_amount(e.get(k)) for e in effects for k in ("n", "p", "t", "mv"))  # ("mv": a free cast's limit, wave 3R5)
    if not wants_player and not wants_amount:
        return True
    if not wants_amount and step_names_player(d):  # -- sagas & attached-object triggers (wave 3S) --
        return True
    cond = d.get("cond") if d.get("kind") == "triggered" and d.get("trigger") == "event" else None
    if cond is None or cond["event"] == "multi":
        return False
    if wants_player and not _has_player(cond):
        return False
    return not wants_amount or (cond["event"] in _AMOUNT_EVENTS and (cond["event"] != "attack" or bool(cond.get("aggregate"))))  # (17D: attack counts only as "one or more")


@lru_cache(maxsize=20000)
def _cached(ch: Characteristics) -> dict[int, Definition]:
    out: dict[int, Definition] = {}
    for ab in ch.abilities:
        if ch.level is not None and ab.section > ch.level:
            continue  # -- Class (wave 16A) -- 716.2a: an ability under a level bar the permanent hasn't reached
        if ch.doors is not None and ab.section not in ch.doors:
            continue  # -- Rooms (wave 18G) -- 709.5: the rules text of a locked door isn't there
        if out.get(ab.index, {}).get("kind") == "mode":
            continue  # (a mode line of the modal ability above it)
        d = define(ab, ch)
        if d is None and ab.kind in ("triggered", "activated", "loyalty"):
            # -- modal triggered/activated abilities (wave 1A): "…, choose one —" and its bulleted modes,
            # read by app/rules/modal_abilities.py (the header's definition and one stub per mode line)
            from app.rules import modal_abilities

            found = modal_abilities.definitions(ab, ch)
            if found and all(_event_refs_ok(x) for x in found.values()):  # (all of it or nothing)
                out.update(found)
            continue
        if d is not None and _event_refs_ok(d):
            if ch.doors is not None and (d.get("cond") or {}).get("event") == "unlock_door":  # -- Rooms (wave 18G) -- 709.5h: its own door
                d = {**d, "cond": {**d["cond"], "door": ab.section}}
            out[ab.index] = d
    _merge_instead_lines(ch, out)  # -- refused copy/mana (wave 3R3) --
    return out


# -- refused copy/mana (wave 3R3) -- an instant or sorcery whose second line replaces what the first did: Cabal
# Ritual "Add {B}{B}{B}." / "Threshold — Add {B}{B}{B}{B}{B} instead if there are seven or more cards in your
# graveyard." The ability word has no rules meaning (207.2c): the two lines are one spell ability's text in order
# (608.2c), so the "instead" (614.1a) reads the line above. The pair is parsed as one text; the first line's
# definition is the pair, the second's an empty spell line (spell_definition joins the lines in order).
def _merge_instead_lines(ch: Characteristics, out: dict[int, Definition]) -> None:
    if not ch.is_instant_or_sorcery:
        return
    lines = [ab for ab in ch.abilities if ab.kind == "spell"]
    for prev, ab in zip(lines, lines[1:], strict=False):
        if ab.index in out or out.get(prev.index, {}).get("kind") != "spell" or ab.index != prev.index + 1:
            continue
        own = _ABILITY_WORD.sub("", ab.text, count=1)
        if own == ab.text or not re.search(r"\binstead\b", own) or " would " in own:
            continue  # (only an ability-word line, as printed: "<ability word> — … instead if …")
        merged = define(replace(prev, text=f"{prev.text} {own}"), ch)
        if merged is None or merged.get("kind") != "spell" or not _event_refs_ok(merged):
            continue
        out[prev.index] = merged
        out[ab.index] = {"kind": "spell", "effects": [], "target": None, "merged_into": prev.index}
# -- end refused copy/mana (wave 3R3) --


def definitions(ch: Characteristics) -> dict[int, Definition]:
    """Engine definitions for a card's abilities, by ability index (see ``app.rules.oracle``).
    Hand-written scripts (``app.rules.cards``) are consulted by the caller first."""
    if ch.is_ability or ch.face_down:
        return {}
    from app.rules import cards  # hand-written scripts (a leaf package)

    if cards.get(ch.oracle_id) is not None and cards.trusted(ch.oracle_id, ch.oracle_text) is None:
        return {}  # REVIEW: a reviewed script exists for other Oracle text; nothing is automated until re-checked
    return _cached(replace(ch, pt=None, granted=frozenset(), lost=frozenset(), imposed=frozenset()))


# Combat restrictions and requirements printed on a permanent (CR 508.1c-d, 509.1b-c) that the
# wording grammar doesn't read. "~ can't block.", "~ can't be blocked by creatures with power 2 or
# less.", "Creatures your opponents control can't block.", "~ doesn't untap during your untap
# step." … are app/rules/statics.py rules (see its docstring for the vocabulary), applied through
# ``Characteristics.imposed`` by app/rules/layers.py and read here by ``statics``.
COMBAT_STATICS = {
    "~ can't attack unless defending player controls an Island.": "attack_needs_island",
    "~ can't be countered.": "cant_be_countered",
    "This spell can't be countered.": "cant_be_countered",
}


# Rules an Aura or Equipment imposes on the object it's attached to (not abilities it grants).
# Each: the restrictions imposed (the names scripts.statics / Characteristics.imposed use).
ATTACHED_RULES: dict[str, tuple[str, ...]] = {
    "can't attack or block.": ("cant_attack_or_block",),
    "can't attack.": ("cant_attack",),
    "can't block.": ("cant_block",),
    "can't be blocked.": ("cant_be_blocked",),
    "attacks each combat if able.": ("must_attack",),
    "doesn't untap during its controller's untap step.": ("doesnt_untap",),
    "can't attack or block, and its activated abilities can't be activated.": ("cant_attack_or_block", "cant_activate"),
    "can't attack or block and its activated abilities can't be activated.": ("cant_attack_or_block", "cant_activate"),
    "is goaded.": ("goaded:@you",),  # -- wave 3F -- 701.15b: by the Aura's controller (app/rules/layers.py ``_own``)
}
# "Enchanted creature's activated abilities can't be activated." (possessive subjects)
_POSSESSIVE_RULES: dict[str, tuple[str, ...]] = {
    "activated abilities can't be activated.": ("cant_activate",),
}


def attached_rule(text: str) -> Definition | None:
    """"Enchanted creature can't attack or block.", "Enchanted creature doesn't untap during its
    controller's untap step." …: a rule for whatever the source is attached to."""
    text = text.replace("’", "'")
    # -- small wordings (wave 11E) -- "All creatures able to block enchanted creature do so." (Lure; 509.1c): the rule "lure" on
    # the creature it's attached to (combat.block_requirements, wave 12B)
    if re.fullmatch(r"All creatures able to block (?:enchanted|equipped) creature do so\.", text):
        return {"kind": "static", "static": "attached_rule", "imposes": ["lure"], "effects": [], "lands": False,
                "permanent": False}
    for subject in (*ATTACHED_SUBJECTS, "Enchanted permanent"):
        imposed = None
        if text.startswith(subject + " "):
            imposed = ATTACHED_RULES.get(text[len(subject) + 1:])
        elif text.startswith(subject + "'s "):
            imposed = _POSSESSIVE_RULES.get(text[len(subject) + 3:])
        if imposed is not None:
            return {"kind": "static", "static": "attached_rule", "imposes": list(imposed), "effects": [],
                    "lands": subject == "Enchanted land", "permanent": subject == "Enchanted permanent"}
    return None


def statics(ch: Characteristics) -> set[str]:
    """The combat statics a card has (from its definitions), and those imposed on it by
    attached Auras / Equipment."""
    return {d["static"] for d in definitions(ch).values() if d["kind"] == "static"} | ch.imposed


# Keyword abilities that are triggered abilities (CR 702), as template definitions.
KEYWORD_TRIGGERS: dict[str, Definition] = {
    # 702.108 prowess: "Whenever you cast a noncreature spell, this creature gets +1/+1 until end of turn."
    "prowess": {"kind": "triggered", "trigger": "cast_you", "filter": "a noncreature spell",
                "effects": [{"do": "pump", "who": "self", "p": 1, "t": 1}], "optional": False, "target": None},
}


def keyword_triggers(ch: Characteristics) -> list[tuple[int, Definition]]:
    """Triggered keyword abilities of a card, with keys that can't clash with ability indexes."""
    if ch.is_ability or ch.face_down:
        return []
    out = []
    for ab in ch.abilities:
        if ab.kind != "keywords":
            continue
        for k, kw in enumerate(ab.keywords):
            if kw in KEYWORD_TRIGGERS:
                out.append((1000 + ab.index * 10 + k, KEYWORD_TRIGGERS[kw]))
            if kw in _kw_meanings.MEANINGS:  # -- static wordings (wave 6E) -- read as its CR meaning (app/rules/keyword_triggers.py)
                out += [(1000 + ab.index * 10 + k + 100000 * j, d) for j, d in enumerate(_kw_meanings.first_piece(kw, ab.text, ab.keywords[:k].count(kw)))]
            if kw == "backup" and (bd := _kw_meanings.backup_definition(ch, ab, ab.keywords[:k].count(kw))) is not None:
                out.append((1000 + ab.index * 10 + k, bd))  # -- keywords (wave 15E) -- 702.165a
            if kw == "partner" and (pw := _kw_meanings.partner_with_definition(ab.text)) is not None:  # -- keyword pieces (wave 8A) --
                out.append((1000 + ab.index * 10 + k, pw))
            if kw == "decayed":  # -- token & pump wordings (wave 6C) -- 702.147a (app/rules/decayed.py)
                from app.rules import decayed

                out.append((1000 + ab.index * 10 + k, decayed.TRIGGER))
            if kw in ("persist", "undying"):  # 702.79 / 702.93: return with a -1/-1 (+1/+1) counter
                out.append((1000 + ab.index * 10 + k, {
                    "kind": "triggered", "trigger": "dies_self", "optional": False, "target": None,
                    "unless_counter": "-1/-1" if kw == "persist" else "+1/+1",
                    "effects": [{"do": "return_with_counter", "counter": "-1/-1" if kw == "persist" else "+1/+1"}]}))
            f = re.fullmatch(r"fabricate (\d+)", ab.text.strip().rstrip(".").lower()) if kw == "fabricate" else None
            if f:  # 702.123a: "When this permanent enters, put N +1/+1 counters on it or create N 1/1 Servos."
                out.append((1000 + ab.index * 10 + k, {
                    "kind": "triggered", "trigger": "enters_self", "optional": False, "target": None,
                    "effects": [{"do": "fabricate", "n": int(f.group(1))}]}))
            ns = re.findall(r"soulshift (\d+)", ab.text.lower()) if kw == "soulshift" and re.fullmatch(  # (wave 15E: each instance, 702.46b)
                r"soulshift \d+(?:, soulshift \d+)*", ab.text.strip().rstrip(".").lower()) else []
            if ns:  # 702.46a: "When this creature dies, you may return target Spirit card with mana value N or less …"
                out.append((1000 + ab.index * 10 + k, {
                    "kind": "triggered", "trigger": "dies_self", "optional": True,
                    "target": {"what": f"graveyard:Spirit:{ns[ab.keywords[:k].count(kw)]}"},
                    "effects": [{"do": "bounce", "who": "target"}]}))
            fb = re.fullmatch(r"firebending (\d+)", ab.text.strip().rstrip(".").lower()) if kw == "firebending" else None
            if fb:  # -- keyword actions & face-down (wave 3F) -- 702.189a: "Whenever this creature attacks, add N {R}. …"
                out.append((1000 + ab.index * 10 + k, {
                    "kind": "triggered", "trigger": "attacks_self", "optional": False, "target": None,
                    "effects": [{"do": "firebend", "n": int(fb.group(1))}]}))
    return out


# 700.2: "Choose …" followed by bulleted modes. (n_min, n_max, same mode more than once?, condition)
_MODAL_HEADERS = {
    "Choose one —": (1, 1, False, None),
    "Choose two —": (2, 2, False, None),
    "Choose one or both —": (1, 2, False, None),
    "Choose one or more —": (1, 99, False, None),
    "Choose three. You may choose the same mode more than once.": (3, 3, True, None),
    "Choose one. If you control a commander as you cast this spell, you may choose both instead.": (1, 1, False, "commander"),
}


def modal_definition(lines: list[AbilityText], name: str = "") -> Definition | None:
    """A modal spell (700.2): the header line, then one bulleted line per mode, each an effect
    sentence the engine reads with at most one target. None if any part isn't understood (the
    whole spell is then resolved by hand)."""
    if len(lines) < 3 or lines[0].text not in _MODAL_HEADERS:
        return None
    lo, hi, repeat, condition = _MODAL_HEADERS[lines[0].text]
    modes: list[dict[str, Any]] = []
    for ab in lines[1:]:
        if not ab.text.startswith("• "):
            return None
        parsed = parse_effects(self_text(ab.text[2:], name))
        if parsed is None or parsed[2]:  # ("you may" inside a mode: not yet)
            return None
        effects, target, _ = parsed
        if target is not None and not isinstance(target, str):
            # -- static_other sweep (wave 16B) -- a mode with several target groups, "up to N targets" or a division: its groups join the
            # spell's (601.2c: casting.modal_groups); the effects name them as the mode's own "target" / "target:<k>"
            modes.append({"text": ab.text[2:], "effects": rename_bindings(effects, f"m{len(modes)}_"), "target": None,
                          "groups": _as_groups(target)})
            continue
        modes.append({"text": ab.text[2:], "effects": rename_bindings(effects, f"m{len(modes)}_"),
                      "target": {"what": target} if target else None})
    if not repeat and lo > len(modes):
        return None
    if condition == "commander":  # "… you may choose both instead" (while you control a commander)
        hi = 1
    return {"kind": "spell", "effects": [], "target": None, "modes": modes,
            "modal": {"min": lo, "max": min(hi, 99 if repeat else len(modes)), "repeat": repeat, "condition": condition}}


def _from_hand_ability(ab: AbilityText) -> bool:
    return ab.kind == "activated" and re.search(r"(?:^|, )Discard (?:this card|~)(?:,|$)", ab.cost or "") is not None


def spell_definition(ch: Characteristics) -> Definition | None:
    """A whole instant/sorcery as one definition, if every line is automated (else None)."""
    if not ch.is_instant_or_sorcery:
        return None
    # (-- static_other sweep (wave 16B) -- a hand ability on the card — reinforce 702.77a, "{cost}, Discard this card: …" — is not
    # part of what the spell does)
    text_lines = [ab for ab in ch.abilities if ab.kind != "keywords" and not _from_hand_ability(ab)]
    if text_lines and text_lines[0].text in _MODAL_HEADERS:
        modal = modal_definition(text_lines, ch.name)
        # (a spell has no trigger event: "that player" / "that much" can't be bound)
        return modal if modal is not None and _event_refs_ok(modal) else None
    defs = definitions(ch)
    # ("This spell costs {1} less to cast for each …": part of the total cost, not of what it does)
    # (wave 3C: nor "If you control a commander, you may cast this spell without paying its mana cost"; 3$: additional costs)
    lines = [ab for ab in ch.abilities if ab.kind != "keywords" and not _from_hand_ability(ab)
             and defs.get(ab.index, {}).get("static") not in ("self_cost", "additional_cost", "alt_cost", "cast_restriction")  # (alt_cost: wave 4I; cast_restriction: wave 7A)
             and not (defs.get(ab.index, {}).get("static") == "permission" and defs[ab.index].get("self")
                      and (defs[ab.index].get("free") or defs[ab.index].get("zone") in ("graveyard", "exile")))]  # (wave 17C: retrace, 702.81a)
    if (not lines and not any(defs.get(ab.index, {}).get("zone") in ("graveyard", "exile") for ab in ch.abilities)) \
            or any(ab.index not in defs or defs[ab.index]["kind"] != "spell" for ab in lines):
        return None  # (wave 17C: a retrace spell with nothing else on it, Throes of Chaos: cascade does it all)
    # Each line's "target" words are the spell's target groups, in printed order (601.2c, 115.3:
    # "Destroy target creature. / Tap target creature." targets twice, not once).
    groups: list[dict[str, Any]] = []
    effects: list[dict[str, Any]] = []
    for ab in lines:
        own = target_groups(defs[ab.index])
        if groups and any('"other":true' in g["what"] for g in own):
            return None  # ("another target" on a later line: distinct from which target?)
        offset = len(groups)
        index = list(range(offset, offset + len(own)))
        for g in own:
            if g.get("distinct_from"):
                g["distinct_from"] = [offset + d for d in g["distinct_from"]]
            groups.append(g)
        try:  # (each line's bindings keep their own names: "e0" of line 2 isn't line 1's)
            effects += rename_bindings(_renumber(defs[ab.index]["effects"], index), f"l{ab.index}_")
        except _NoMatch:
            return None
    # -- X sized by a count (wave 4K) -- the Zenith cycle's "Shuffle ~ into its owner's library."
    from app.rules import x_spells

    shuffled = x_spells.spell_effects(effects)
    # -- recursion & tutors (wave 4M) -- otherwise "Exile ~." / "Put ~ on the bottom of its owner's library." (and a
    # shuffle that isn't last): the spell card itself, moved where the instruction stands (608.2m/n: app/rules/recursion.py)
    if shuffled is None:
        from app.rules import recursion as _recursion

        shuffled = [{"do": "spell_self_move", "to": to} if (to := _recursion.self_move_of(e)) is not None else e for e in effects]
        if sum(e["do"] == "spell_self_move" for e in shuffled) > 1 or any(e.get("who") == "self" for e in shuffled):
            shuffled = None
    # -- end recursion & tutors (wave 4M) --
    if shuffled is None:
        return None  # ("Exile ~." on an instant or sorcery: the spell itself, which effects don't move)
    effects = shuffled
    if ch.is_instant_or_sorcery and any(ab.kind == "keywords" and "ascend" in ab.keywords for ab in ch.abilities):
        effects = [{"do": "ascend"}, *effects]  # -- keywords (wave 15E) -- 702.131a: the spell ability, first
    if ch.is_instant_or_sorcery and any(ab.kind == "keywords" and ab.keywords == ("cipher",) for ab in ch.abilities):
        effects = [*effects, {"do": "cipher"}]  # -- static_other sweep (wave 17C) -- 702.99a: encoded last (recursion.cipher)
    effects, target = _finish_targets(effects, groups)
    return {"kind": "spell", "effects": effects, **target_fields(target)}


# =====================================================================================================
# Replacement and prevention effects (CR 614, 615) — applied by app/rules/replacements.py.
# A wording either matches one of these exactly or the line stays manual (never a guess).
# =====================================================================================================
SHOCK = re.compile(r"^As ~ enters, you may pay (?P<n>\d+) life\. If you don't, it enters tapped\.$")
# "~ enters [tapped] with N … counters on it [for each …]" (614.1c); "If ~ was kicked, it enters with …" (702.33e)
ENTERS_WITH = re.compile(r"^(?:(?P<kicked>If ~ was kicked, it)|~) enters (?P<tapped>tapped (?:and )?)?with "
                         r"(?P<n>twice X|X|\d+|a|an|one|two|three|four|five|six|seven|eight|nine|ten) "  # (twice X: wave 4K)
                         r"(?P<kind>\+1/\+1|-1/-1|[a-z]+) counters? on it(?: for each (?P<each>.+?)|, where X is (?P<xdef>.+?))?"
                         r"(?: and with (?P<kw>haste|trample|flying|first strike|fear))?\.$")  # (kw: wave 7C)
ENTERS_TAPPED_UNLESS = re.compile(r"^~ enters tapped unless (?P<cond>.+)\.$")
_A_THING = r"(?:a|an) (?P<{name}>[A-Z][A-Za-z]*(?: [A-Z][A-Za-z]*)*|legendary(?: [a-z]+)? creature|basic land|planeswalker)"
_UNLESS_ONE_OR_TWO = re.compile(r"^you control " + _A_THING.format(name="a") + r"(?: or " + _A_THING.format(name="b") + r")?$")
_UNLESS_COUNT = re.compile(r"^you control (?P<n>\w+) or (?P<cmp>more|fewer) (?P<what>.+)$")
_UNLESS_OPPONENTS = re.compile(r"^you have (?P<n>\w+) or more opponents$")
# The object's own "instead": "If ~ would die, exile it instead." / "… be put into a graveyard from anywhere …"
EXILE_INSTEAD_SELF = re.compile(r"^If ~ would (?P<what>die|be put into a graveyard from anywhere), exile it instead\.$")
# -- instead (wave 20B) -- "If this creature would die, put it on the bottom of its owner's library instead." (Nissa's Chosen; on top: Gravebane Zombie)
LIBRARY_INSTEAD_SELF = re.compile(r"^If ~ would die, put it on (?P<pos>top|the bottom) of its owner's library instead\.$")
# Statics: "If a creature an opponent controls would die, exile it instead." / Rest in Peace / Leyline of the Void
EXILE_INSTEAD_STATIC = re.compile(r"^If (?P<subject>a card or token|a card|(?:a|an) (?P<sel>[a-z][a-z' ~]+?)) would "
                                  r"(?P<what>die|be put into (?P<whose>a|your|an opponent's) graveyard(?P<any> from anywhere)?), "
                                  r"exile (?:it|that card) instead\.$")  # (any: "If a permanent would be put into a graveyard" — wave 20B)
# Prevention: "Prevent all [combat] damage that would be dealt [this turn] [to …] [by …] [this turn]."
PREVENT_ALL = re.compile(r"^prevent all (?P<kind>combat |noncombat )?damage that would be dealt(?P<t1> this turn)?"
                         r"(?: to (?P<to>.+?))?(?P<t2> this turn)?(?: by (?P<by>.+?))?(?P<t3> this turn)?$")
_PREVENT_WOULD_DEAL = re.compile(r"^prevent all (?P<kind>combat |noncombat )?damage (?:that )?(?P<subj>(?!would be dealt).+?) would deal"
                                 r"(?: to (?P<to>.+?))?(?P<t> this turn)?$")
PREVENT_TO_AND_BY = re.compile(r"^prevent all (?P<kind>combat |noncombat )?damage that would be dealt to and dealt by "
                               r"(?P<x>~|enchanted creature|equipped creature)$")
_PREVENT_TARGETS = {  # what the damage would be dealt to → (players, objects)
    "you": ("you", None), "players": ("all", None), "each player": ("all", None), "~": (None, "self"),
    "enchanted creature": (None, "attached"), "equipped creature": (None, "attached"),
    "you and creatures you control": ("you", "creatures you control"),
    # -- damage wordings (wave 6B) -- The Wanderer ("other": not itself), Endure
    "you and other permanents you control": ("you", "other permanents you control"),
    "you and permanents you control": ("you", "permanents you control"),
}
_PREVENT_SOURCES = {"~": "self", "this creature": "self", "enchanted creature": "attached", "equipped creature": "attached"}


def _selector_key(phrase: str) -> str | None:
    """A group of permanents on the battlefield as a selector key, or None."""
    from app.rules import selectors  # (a leaf module)

    sel = selectors.parse(phrase)
    if sel is None or sel.player is not None or sel.zones != ("battlefield",) or sel.card:
        return None
    return sel.key()


def _word_num(word: str) -> int | None:
    return num(word) if word.isdigit() or word.lower() in NUMBERS else None


def _unless_condition(text: str) -> Definition | None:
    """"~ enters tapped unless <condition>" → a condition (app/rules/conditions.py shape; ``{"any":
    [...]}`` for "a Plains or an Island"). Reveal-or-tapped wordings stay manual."""
    from app.rules import selectors  # (a leaf module)

    t = text.strip()
    # -- static wordings (wave 6E) -- "unless a player has 13 or less life" (the Slow lands of Duskmourn), "unless your
    # opponents control eight or more lands" (the Turbulent lands): read as the land enters (614.1c, 614.12)
    m = re.fullmatch(r"a player has (?P<n>\w+) or less life", t)
    if m:
        n = _word_num(m["n"])
        return {"value": {"life": "player_min"}, "op": "<=", "n": n} if n is not None else None
    if t == "it's your turn":  # -- static_other sweep (wave 19A) -- "This creature enters tapped unless it's your turn." (Horned Loch-Whale)
        return {"turn": "yours"}
    m = re.fullmatch(r"your opponents control (?P<n>\w+) or more (?P<what>[a-z]+)", t)
    if m:
        n = _word_num(m["n"])
        key = _selector_key(m["what"] + " your opponents control")
        return {"value": {"count": key}, "op": ">=", "n": n} if n is not None and key is not None else None
    m = _UNLESS_OPPONENTS.fullmatch(t)
    if m:
        n = _word_num(m["n"])
        return {"value": {"opponents": 1}, "op": ">=", "n": n} if n is not None else None
    m = _UNLESS_COUNT.fullmatch(t)
    if m:
        n = _word_num(m["n"])
        key = _selector_key(m["what"] + " you control")
        if n is None or key is None:
            return None
        return {"value": {"count": key}, "op": ">=" if m["cmp"] == "more" else "<=", "n": n}
    m = _UNLESS_ONE_OR_TWO.fullmatch(t)
    if m:
        conds = []
        for word in (m["a"], m["b"]):
            if not word:
                continue
            key = _selector_key(word + " you control")
            if key is None and word[:1].isupper() and " " not in word:  # "a Plains": the selector grammar reads Plains as plural
                key = selectors.Selector(controller="you", subtypes=(word,)).key()
            if key is None:
                return None
            conds.append({"value": {"count": key}, "op": ">=", "n": 1})
        return conds[0] if len(conds) == 1 else {"any": conds}
    return None


def _for_each(phrase: str) -> Any:
    """"for each <group>" on an "enters with" ability: a count the values grammar evaluates as it enters
    — of cards elsewhere ("creature card in your graveyard") or of *other* permanents. A group the
    entering permanent might itself belong to is not read (whether it counts itself is not settled
    here); "creatures that died this turn" isn't modeled ("for each color of mana spent": wave 4F)."""
    from app.rules import selectors  # (a leaf module)

    if phrase in ("time it was kicked", "time this spell was kicked", "time ~ was kicked"):
        return {"kicked": 1}
    if phrase in ("mana spent to cast it", "mana spent to cast ~"):  # -- counters sweep (wave 19D) -- 601.2h: the amount of mana its spell cost
        return {"mana_spent": "self"}
    if phrase in ("color of mana spent to cast it", "color of mana spent to cast ~"):  # -- ability words (wave 4F) --
        return {"colors_spent": 1}  # converge (its spell's payment record, read as it enters: replacements._counter_amount)
    sel = selectors.parse(phrase)
    if sel is None or sel.player is not None or (not sel.card and sel.zones == ("battlefield",) and not sel.other):
        return None
    return {"count": sel.key()}


def _prevent_group(phrase: str) -> Any:
    """"target legendary creature" / "up to two target creatures" → its target group when it names battlefield permanents."""
    from app.rules import language, selectors

    try:
        group = language.target_group(phrase)
    except language._Fail:
        return None
    what = group["what"] if group else ""
    if not what.startswith(selectors.PREFIX):
        return None
    sel = selectors.from_key(what)
    return group if sel.player is None and sel.zones == ("battlefield",) else None


def _prevent_scope(kind: str | None, to: str | None, by: str | None) -> tuple[Definition, str | None, str | None] | None:
    """The scope of a "prevent all" wording → (scope, target selector for a targeted one, its role)."""
    scope: Definition = {"combat": {"combat ": True, "noncombat ": False}.get(kind or "")}
    target: str | None = None
    role: str | None = None
    if to is None:
        scope["any_target"] = True
    elif to in _PREVENT_TARGETS:
        players, objects = _PREVENT_TARGETS[to]
        if players:
            scope["to_players"] = players
        if objects:
            scope["to_objects"] = objects if objects in ("self", "attached") else _selector_key(objects)
            if scope["to_objects"] is None:
                return None
    elif to in SELECTORS and SELECTORS[to] in ("creature", "creature_you_control", "creature_opponent_controls"):
        target, role = SELECTORS[to], "to"
    elif to in ("it", "that creature"):  # "Untap target creature. Prevent all damage that would be dealt to it this turn." (Djeru's Resolve);
        # -- prevention riders (wave 17A) -- "… to that creature this turn by colorless sources." (Lithomancer's Focus)
        target, role = "it", "to"
    # -- prevention variants (wave 12B) -- "to target legendary creature", "to up to two target creatures", "to target
    # creature with power 5 or greater": the creatures chosen as the spell or ability is put on the stack (115.1); the
    # damage a creature would be dealt this turn (615.1)
    elif by is None and to.startswith(("target ", "up to ", "another target ")) and _prevent_group(to) is not None:
        target, role = _prevent_group(to), "to"
    else:
        key = _selector_key(to)
        if key is None:
            return None
        scope["to_objects"] = key
    if by is None:
        pass
    elif by in _PREVENT_SOURCES:
        scope["by_objects"] = _PREVENT_SOURCES[by]
    elif by in SELECTORS and SELECTORS[by] in ("creature", "attacking_creature", "attacking_or_blocking_creature"):
        if target is not None:
            return None  # (two targets: not this template)
        target, role = SELECTORS[by], "by"
    elif target is None and by.startswith(("target ", "up to ", "one or two ", "x target ", "X target ", "another target ")) \
            and _prevent_group(by) is not None:  # -- prevention riders (wave 17A) -- "one or two target creatures would deal"
        target, role = _prevent_group(by), "by"
    else:
        key = _selector_key(by)
        if key is not None:
            scope["by_objects"] = key
        elif (spec := _source_shields.source_scope(by)) is not None:  # -- prevention riders (wave 17A) -- "red sources", "sources you don't control"
            scope["by_source"] = spec
        else:
            return None
    return scope, target, role


def parse_prevent_all(text: str) -> tuple[Definition, bool, str | None, str | None] | None:
    """"Prevent all …" (one sentence, no trailing period, first letter lower-cased) → (scope, this
    turn?, target selector, role)."""
    # -- damage wordings (wave 6B) -- "… dealt to and dealt by creatures you control" (Statecraft): either side in the group
    g = re.fullmatch(r"prevent all (?P<kind>combat |noncombat )?damage that would be dealt to and dealt by (?P<g>creatures .+)", text)
    if g and (key := _selector_key(g["g"])) is not None:
        return ({"combat": {"combat ": True, "noncombat ": False}.get(g["kind"] or ""), "to_objects": key, "by_objects": key,
                 "to_or_by": True}, False, None, None)
    m = PREVENT_TO_AND_BY.fullmatch(text)
    if m:
        what = _PREVENT_SOURCES[m["x"]]
        return ({"combat": {"combat ": True, "noncombat ": False}.get(m["kind"] or ""), "to_objects": what, "by_objects": what,
                 "to_or_by": True}, False, None, None)
    # -- prevention riders (wave 17A) -- "Prevent all damage that black sources and red sources would deal this turn." (Luminesce),
    # "Prevent all combat damage target creature would deal this turn." (Azorius Ploy): the same as "… dealt by [them]"
    w = _PREVENT_WOULD_DEAL.fullmatch(text)
    if w:
        text = (f"prevent all {w['kind'] or ''}damage that would be dealt{' to ' + w['to'] if w['to'] else ''} by {w['subj']}"
                f"{' this turn' if w['t'] else ''}")
    m = PREVENT_ALL.fullmatch(text)
    if not m:
        return None
    turns = sum(1 for t in (m["t1"], m["t2"], m["t3"]) if t)
    if turns > 1:
        return None
    got = _prevent_scope(m["kind"], m["to"], m["by"])
    if got is None:
        return None
    scope, target, role = got
    return scope, turns == 1, target, role


def define_replacement(ability: AbilityText, text: str) -> Definition | None:
    """A static line that is a replacement or prevention effect of the permanent itself."""
    if ability.kind != "static":
        return None
    text = re.sub(r"^~ enters tapped if it's not your turn\.$", "~ enters tapped unless it's your turn.", text)  # (wave 19A: Eddymurk Crab)
    # -- refused grants/replacements (wave 3R2) -- "Damage can't be prevented." and friends (615.12)
    from app.rules import skips, source_shields

    if (unpreventable := source_shields.static_definition(text)) is not None:
        return unpreventable
    if (skip := skips.static_definition(text)) is not None:  # "Skip your draw step." (614.10)
        return skip
    from app.rules import cant_gain, extra_tokens

    if (extra := extra_tokens.static_definition(text)) is not None:  # "those tokens plus a Food token" (614.16)
        return extra
    if (cant := cant_gain.static_definition(text)) is not None:  # "Players can't gain life." (614.17)
        return cant
    from app.rules import hand_size  # -- hand size (wave 4J) -- "You have no maximum hand size." (402.2)

    if (no_max := hand_size.static_definition(text)) is not None:
        return no_max
    from app.rules import game_result  # -- game result statics (wave 10B) -- 104.2, 104.3

    if (result := game_result.static_definition(text)) is not None:
        return result
    from app.rules import legend_rule  # -- legend rule (wave 10B) -- 704.5j

    if (no_legend := legend_rule.static_definition(text)) is not None:
        return no_legend
    from app.rules import land_plays  # -- additional land plays (wave 4J) -- (305.2)

    if (extra_lands := land_plays.static_definition(text)) is not None:
        return extra_lands
    from app.rules import trigger_multipliers  # -- trigger multipliers (wave 5D) -- 603.2d

    if (multiplier := trigger_multipliers.static_definition(text)) is not None:
        return multiplier
    from app.rules import (
        player_control,  # -- controlling another player (wave 18H) -- Opposition Agent (723.2)
    )

    if (searching := player_control.static_definition(text)) is not None:
        return searching
    # -- end refused grants/replacements (wave 3R2) --
    if text == "~ enters tapped.":
        return {"kind": "replacement", "replacement": "enters_tapped", "effects": []}
    if text == "~ enters prepared.":  # -- prepared (wave 13C) -- 722.3a: applied as it enters (replacements.after_entry)
        return {"kind": "replacement", "replacement": "enters_prepared", "effects": []}
    from app.rules import language  # (a leaf module)

    chosen = language.enters_choice(text)  # "As ~ enters, choose a color." (614.1c, 614.12a)
    if chosen is not None:
        return chosen
    # -- entry forms (wave 5F) -- "~ enters tapped. As it enters, choose a color …"
    from app.rules import entry_forms

    if (tapped_choice := entry_forms.tapped_choice(text)) is not None:
        return tapped_choice
    if (standalone := entry_forms.standalone_choice(text)) is not None:  # -- static statics (wave 10B) --
        return standalone
    if (turn_down := entry_forms.turn_others_down(text)) is not None:  # -- hidden exile (wave 18A) --
        return turn_down
    m = ENTERS_TAPPED_UNLESS.match(text)
    if m:  # check lands, fast lands, battle lands, Battlebond lands (614.1d)
        cond = _unless_condition(m["cond"])
        return {"kind": "replacement", "replacement": "enters_tapped", "unless": cond, "effects": []} if cond else None
    # -- "this way" outcomes (wave 4A) -- Snarls: reveal a card or enter tapped
    from app.rules import reveal_lands

    if (revealed := reveal_lands.definition(text)) is not None:
        return revealed
    from app.rules import enter_cost  # -- entering for a cost (wave 5G) -- Mox Diamond, Lake of the Dead

    if (entering_cost := enter_cost.definition(text)) is not None:
        return entering_cost
    # -- conditional statics (wave 4B) -- "If you control two or more other lands, this land enters tapped." (Den of
    # the Bugbear; 614.1d, checked as it enters, 614.12): "enters tapped unless" the condition is false
    m = re.fullmatch(r"If (?P<cond>you control .+), ~ enters tapped\.", text)
    if m:
        cond = _unless_condition(m["cond"])
        return {"kind": "replacement", "replacement": "enters_tapped", "unless": {"not": cond}, "effects": []} if cond else None
    m = SHOCK.match(text)
    if m:  # shock lands: "As ~ enters, you may pay 2 life. If you don't, it enters tapped."
        return {"kind": "replacement", "replacement": "pay_life_or_tapped", "life": int(m["n"]), "effects": []}
    # -- escape (wave 5I) -- 702.138c: "~ escapes with two +1/+1 counters on it."
    from app.rules import escape

    text = escape.escapes_with(text) or text
    # -- counters (wave 5H) -- "~ enters with an indestructible counter on her", "… on it if you cast it from your hand"
    # (Myojin: the cast condition as "If you cast it from your hand, ~ enters with …"), "~ enters with a number of +1/+1
    # counters on it equal to the number of creatures that died this turn" (a count read as it enters, 614.1c)
    text = re.sub(r"^(~ enters (?:tapped )?with .+? counters? on) (?:him|her)( |\.)", r"\1 it\2", text)
    tail = re.fullmatch(r"(?P<body>~ enters with .+? counters? on it) (?P<c>if you cast it(?: from your hand)?)\.", text)
    if tail is not None:
        text = f"If {tail['c'][3:].replace(' it', ' ~', 1)}, {tail['body']}."
    # -- this-turn conditions (wave 8D) -- "~ enters with a +1/+1 counter on it if you attacked this turn." (Raid, Morbid …)
    ttail = re.fullmatch(r"(?P<body>~ enters with .+? counters? on it) if (?P<c>[^,]+ this turn)\.", text)
    if ttail is not None:
        text = f"If {ttail['c']}, {ttail['body']}."
    # -- end this-turn conditions --
    eq = re.fullmatch(r"~ enters with a number of (?P<kind>\+1/\+1|[a-z]+) counters on it equal to (?P<v>.+)\.", text)
    if eq is not None:
        from app.rules import values

        ev = values.parse_count(eq["v"].replace("mana spent to cast it", "mana spent to cast ~"))  # (wave 19D: "it" is ~ here)
        if ev is None or eq["kind"] in UNMODELED_COUNTERS or '"it"' in json.dumps(ev):
            return None
        # (a count of permanents that could include itself is read before it enters, 614.12; it's counted after the
        # move here: only "other …" counts and counts outside the battlefield are read)
        from app.rules import selectors

        def sels(v: Any) -> list[str]:
            if isinstance(v, dict):
                return [x for k, w in v.items() for x in ([w] if k in ("count", "of") and isinstance(w, str) else sels(w))]
            return [x for w in v for x in sels(w)] if isinstance(v, list) else []

        if any(selectors.from_key(k).zones == ("battlefield",) and not selectors.from_key(k).other for k in sels(ev)):
            return None
        return {"kind": "replacement", "replacement": "enters_with_counters", "counter": eq["kind"], "n": ev, "effects": []}
    # -- end counters (wave 5H) --
    cast_if = None  # -- refused modal/conditional (wave 3R1) -- adamant: "If at least three white mana was spent to
    lead = re.match(r"^If (?P<c>[^,]+), ~ enters with ", text)  # cast this spell, ~ enters with a +1/+1 counter on it."
    if lead is not None:
        from app.rules import conditions

        cast_if = conditions.parse(lead["c"], objects=True)
        if cast_if is not None and lead["c"].endswith(" this turn") and (  # -- this-turn conditions (wave 8D) -- 608.2i, 614.12:
                "history" in cast_if or all("history" in x for x in cast_if.get("any", [None]))):  # read as it enters
            pass
        elif cast_if is None or "cast" not in cast_if or cast_if.get("object") != "self":
            return None
        text = "~ enters with " + text[lead.end():]
    # -- counters (wave 7C) --
    from app.rules import counter_choice

    if (chosen_kind := counter_choice.parse(text)) is not None:
        return chosen_kind
    m = ENTERS_WITH.match(text)
    if m and m["kw"] and (not m["kicked"] or m["each"] or m["xdef"] or cast_if is not None or m["n"] in ("X", "twice X")):
        return None  # -- counters (wave 7C) -- "If ~ was kicked, it enters with N +1/+1 counters on it and with haste." only
    if m and (m["xdef"] or m["n"] == "twice X"):  # -- X sized by a count (wave 4K) -- "~ enters with X +1/+1 counters on it,
        # where X is the greatest power among other creatures you control" (read as it enters, 614.1c, 608.2h); "twice X":
        # the X its spell was cast with, doubled (107.3m)
        if cast_if is not None or m["kicked"] or m["each"] or m["kind"] in UNMODELED_COUNTERS:
            return None
        if m["xdef"]:
            from app.rules import values

            xv = values.parse_count(m["xdef"]) if m["n"] == "X" else None
            if xv is None:
                return None
        else:
            xv = {"times": [2, {"x": 1}]}
        return {"kind": "replacement", "replacement": "enters_with_counters", "counter": m["kind"], "n": xv, "effects": [],
                **({"tapped": True} if m["tapped"] else {})}
    if m and cast_if is not None and (m["kicked"] or m["each"] or m["n"] == "X"):
        return None
    if m and m["kind"] not in UNMODELED_COUNTERS and cast_if is not None:
        return {"kind": "replacement", "replacement": "enters_with_counters", "counter": m["kind"], "n": num(m["n"]),
                "effects": [], **({"tapped": True} if m["tapped"] else {}), "if_cast": cast_if}
    if m and m["kind"] not in UNMODELED_COUNTERS:  # 614.1c: "~ enters with N … counters on it"
        n: Any = "X" if m["n"] == "X" else num(m["n"])
        out: Definition = {"kind": "replacement", "replacement": "enters_with_counters", "counter": m["kind"], "n": n,
                           "effects": []}
        if m["tapped"]:  # "~ enters tapped with two charge counters on it." (Vivid lands)
            out["tapped"] = True
        if m["kicked"]:  # 702.33e: "If ~ was kicked, it enters with …"
            out["if_kicked"] = True
        if m["kw"]:  # -- counters (wave 7C) -- "… and with haste": the keyword it enters with, for as long as it stays
            out["grant"] = [m["kw"]]
        if m["each"]:
            each = _for_each(m["each"])
            if each is None and re.fullmatch(r"(?:nontoken )?creature that died this turn", m["each"]):
                # -- counters (wave 7C) -- this turn's history (wave 4D), read as it enters
                from app.rules import values

                each = values.parse_count("the number of " + m["each"].replace("creature", "creatures", 1))
            if each is None or n == "X" or (m["kicked"] and each == {"kicked": 1}):  # (wave 7C: kicked + each is read)
                return None
            if each == {"kicked": 1}:  # "… for each time it was kicked" (multikicker, 702.33c)
                out["per_kick"] = True
            else:
                out["n"] = {"times": [n, each]} if n != 1 else each
        return out
    m = EXILE_INSTEAD_SELF.match(text)
    if m:
        return {"kind": "replacement", "replacement": "exile_instead",
                "from": "battlefield" if m["what"] == "die" else "anywhere", "effects": []}
    m = LIBRARY_INSTEAD_SELF.match(text)
    if m:
        return {"kind": "replacement", "replacement": "library_instead", "from": "battlefield", "effects": [],
                "position": "top" if m["pos"] == "top" else "bottom"}
    m = EXILE_INSTEAD_STATIC.match(text)
    if m:
        out = {"kind": "static", "static": "exile_instead", "effects": [],
               "from": "anywhere" if m["any"] else "battlefield",
               "graveyard_of": {"a": "any", "your": "you", "an opponent's": "opponent"}.get(m["whose"] or "a", "any")}
        if m["subject"] in ("a card or token", "a card") and m["what"] != "die" and not m["any"]:
            return None  # (wave 20B: without "from anywhere" only a permanent's trip from the battlefield is read)
        if m["subject"] == "a card or token":
            out["who"] = "any"
        elif m["subject"] == "a card":
            out["who"] = "card"
        elif m["any"]:
            # -- instead (wave 20B) -- "an instant or sorcery card would be put into a graveyard from anywhere" (Dryad Militant): a card
            # of those types wherever it is (public once it moves: to the graveyard or to exile)
            kinds = re.fullmatch(r"(?P<a>instant|sorcery)(?: or (?P<b>instant|sorcery))? card", m["sel"])
            if kinds is None or kinds["b"] is None or kinds["a"] == kinds["b"]:
                return None  # ("a creature card … from anywhere": a card in a hidden zone, not modeled)
            out["who"] = "types:Instant|Sorcery"
        else:
            key = _selector_key(m["sel"])  # (a permanent: a battlefield object, "put into a graveyard" being "dies" for any permanent)
            if key is None:
                return None
            out["who"] = key
        return out
    low = _lower_first(text.rstrip("."))
    if low.startswith("prevent all ") and text.endswith(".") and text.count(". ") == 0:
        got = parse_prevent_all(low)
        if got is None:
            return None
        scope, this_turn, target, _role = got
        if this_turn or target is not None:
            return None  # a static ability doesn't last "this turn" and doesn't target
        return {"kind": "static", "static": "prevent", "scope": scope, "effects": []}
    # -- replacement effects stage 2 (wave 2E): token / counter / draw / life / damage statics and
    # "[Objects] enter tapped" (app/rules/replace_grammar.py, applied by app/rules/replace.py) --
    from app.rules import replace_grammar  # (a leaf module)

    return replace_grammar.parse(text)


# -- replacement effects stage 2 (wave 2E): "If that creature would die this turn, exile it instead." --
# A replacement effect of the resolving spell or ability lasting this turn (611.2a), locked to the
# objects it names (the target as the object it is, 400.7; "a creature dealt damage this way": the
# objects that preceding damage was actually dealt to, 615 prevention included) or a group checked
# whenever something would die ("If a creature would die this turn"). Applied by
# replacements.replace_move with the other "exile instead" effects (700.4: dies = put into a
# graveyard from the battlefield). Read by the hook in _parse_effects (before its "If …," condition).
_DIES_THIS_TURN = re.compile(r"^if (?P<det>that|a|an) (?P<what>.+?) would die this turn, exile it instead$")
_CREATURE_NO_REGEN_EXILE = re.compile(r"^if it's a creature, it can't be regenerated this turn, and if it would die this turn, exile it instead$")
_DIES_THAT = {"creature": ["Creature"], "permanent": [], "creature or planeswalker": ["Creature", "Planeswalker"],
              "planeswalker": ["Planeswalker"]}
_DIES_DEALT = re.compile(r"(?P<what>creature|permanent|creature or planeswalker) dealt damage this way")


_UNTIL_EOT_IF = re.compile(r"^until end of turn, (?P<rest>if .+)$")
_IF_THIS_TURN = re.compile(r"^(?P<head>if [^,]+?) this turn(?P<tail>, .+)$")


def _turn_record(text: str) -> list[dict[str, Any]] | None:
    """"Until end of turn, if one or more tokens would be created under your control, twice that
    many … instead." / "If a source you control would deal damage to an opponent this turn, it
    deals double that damage …": a static replacement wording (app/rules/replace_grammar.py) as a
    record of this resolution, lasting this turn (611.2a)."""
    from app.rules import replace_grammar  # (a leaf module)

    # -- long tail (wave 16D) -- "This turn, each creature you control enters with an additional +1/+1 counter on it." (Zameck
    # Guildmage): the static wording (replace_grammar._enter_extra) as a record of this resolution (614.1c, 611.2a)
    if (enter := re.match(r"^this turn, (?P<rest>each .+ enters with .+)$", text)) is not None:
        d = replace_grammar.parse(enter["rest"][0].upper() + enter["rest"][1:] + ".")
        if d is not None and d.get("static") == "replace":
            return [{"do": "replace_record", "event": d["event"], "match": d["match"], "op": d["op"]}]
    m = _UNTIL_EOT_IF.match(text)
    body = m["rest"] if m else None
    if body is None:
        m2 = _IF_THIS_TURN.match(text)
        body = m2["head"] + m2["tail"] if m2 else None
    if body is None or " this turn" in body:
        return None
    d = replace_grammar.parse("I" + body[1:] + ".")
    if d is None or d.get("static") != "replace":
        return None
    return [{"do": "replace_record", "event": d["event"], "match": d["match"], "op": d["op"]}]


def replacement_sentence(text: str, effects: list[dict[str, Any]], groups: list[dict[str, Any]]) -> list[dict[str, Any]] | None:
    """A sentence that sets up a replacement effect for the rest of the turn, or None."""
    if _CREATURE_NO_REGEN_EXILE.match(text):  # -- can't regenerate (wave 19E) -- "If it's a creature, it can't be regenerated this turn, …"
        refs = {e["who"] for e in effects if isinstance(e.get("who"), str) and _group_of(e) is not None}
        found = [w for w in refs if (g := _group_of({"who": w})) is not None and g < len(groups)
                 and _player_target(groups[g].get("what") or "") is not True]
        if len(found) != 1 or len(refs) != 1:
            return None  # (Disintegrate, Carbonize: the one target, "any target" or an object)
        return [{"do": "no_regen_turn", "who": found[0], "types": ["Creature"]},
                {"do": "exile_if_dies", "who": found[0], "types": ["Creature"]}]
    m = _DIES_THIS_TURN.match(text)
    if m is None:
        return _turn_record(text)
    what = m["what"]
    if m["det"] == "that":  # the object the ability's target names (its only object target group)
        if what not in _DIES_THAT:
            return None
        refs = {e["who"] for e in effects if isinstance(e.get("who"), str) and _group_of(e) is not None}
        objects = [w for w in refs if (g := _group_of({"who": w})) is not None and g < len(groups)
                   and _player_target(groups[g].get("what") or "") is False]
        if len(objects) != 1 or len(refs) != 1:
            return None  # (two targets, or a player among them: which one is "that creature"? manual)
        return [{"do": "exile_if_dies", "who": objects[0], "types": _DIES_THAT[what]}]
    dealt = _DIES_DEALT.fullmatch(what)
    if dealt:  # "a creature dealt damage this way": each preceding damage instruction's recipients
        dmg = [(i, e) for i, e in enumerate(effects) if e.get("do") in ("damage", "fight")]
        if not dmg:
            return None
        out = []
        for i, e in dmg:
            e["dealt_as"] = e.get("dealt_as") or f"ref:d{i}"
            out.append({"do": "exile_if_dies", "dealt": e["dealt_as"], "types": _DIES_THAT[dealt["what"]]})
        return out
    from app.rules import selectors  # (a leaf module)

    sel = selectors.parse(what)  # "If a creature [an opponent controls] would die this turn"
    if sel is None or sel.player is not None or sel.zones != ("battlefield",) or sel.card or sel.other:
        return None
    return [{"do": "exile_if_dies", "each": sel.key()}]
# -- end replacement effects stage 2 (wave 2E) --


# -- if you do (wave 10C) -- "Reveal any number of green cards in your hand." (reveal_hand.py): the cards shown are "revealed this way"
@effect(r"reveal any number of (?P<what>[\w ]+?) cards? in your hand")
def _reveal_any_in_hand(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    from app.rules import selectors  # (a leaf module)

    sel = selectors.parse(f"{m['what']} cards in your hand")
    if sel is None or sel.zones != ("hand",) or sel.zone_owner != "you" or not sel.card or sel.other:
        raise _NoMatch
    return [{"do": "reveal_hand_cards", "sel": sel.key(), "n": 99}], None


# -- hidden exile (wave 18A) -- Scroll Rack / Ignorant Bliss: the hand cards exiled face down are "exiled this way" (facedown.py)
@effect(r"exile (?P<k>all|any number of|a) cards? from your hand face down")
def _exile_hand_down(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    if m["k"] == "a":  # (Ethereal Valkyrie: one card, chosen on resolution)
        return [{"do": "exile_hand_down", "all": False, "pick": 1, "n": 1}], None
    return [{"do": "exile_hand_down", "all": m["k"] == "all", "n": 99}], None  # (n: several cards, for "those cards")


@effect(r"reveal (?P<o>target face-down permanent) and you may turn it face up if it's a creature card")
def _reveal_turn_up(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    from app.rules import language

    group = language.target_group(m["o"])
    if group is None:
        raise _NoMatch
    return [{"do": "reveal_turn_up", "who": "target"}], group["what"]


@effect(r"it becomes foretold(?: with a foretell cost of its mana cost reduced by \{{(?P<n>\d+)\}})?")
def _becomes_foretold(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    return [{"do": "become_foretold", "who": "it", **({"reduce": int(m["n"])} if m["n"] else {})}], None


@effect(r"exile all cards from your library face down")
def _exile_library_down(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    return [{"do": "exile_top", "n": 99999, "player": "you", "face_down": True}], None  # (the whole library: min'd with its size)


@effect(r"each player exiles all but the bottom {N} cards of their library face down")  # (Doomsday Excruciator)
def _exile_all_but_bottom(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    return [{"do": "exile_top", "n": 0, "keep_bottom": num(m["n"]), "player": "each_player", "face_down": True}], None


@effect(r"put that many cards from the top of your library into your hand")
def _top_to_hand_that_many(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    return [{"do": "top_to_hand", "n": {"this_way": "exiled", "of": None}}], None


@effect(r"look at the exiled cards and put them on top of your library in any order")
def _look_exiled_to_top(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    return [{"do": "to_library", "who": "them:exiled", "place": "top"}], None


@effect(r"(?P<text>prevent all (?:combat |noncombat )?damage (?:that would be dealt|(?:that )?(?!would be dealt).+? would deal).*)")
def _prevent_all_this_turn(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    got = parse_prevent_all(m["text"])
    if got is None or not got[1]:
        from app.rules import combat_rules  # -- combat (wave 5C) -- (Maze of Ith)

        if (maze := combat_rules.clause(m["text"])) is not None:
            return maze
        raise _NoMatch
    scope, _this_turn, target, role = got
    e: dict[str, Any] = {"do": "prevent_all", "scope": scope}
    if target == "it":  # (a pronoun: scripts.resolve_it binds it to the earlier instruction's object)
        return [{**e, "who": "it", "role": role}], None
    if target is not None:
        e.update(who="target", role=role)
    return [e], target


# -- library primitives (app/rules/effects.py: look_top, exile_top, to_library) as introducers ----
# "Exile the top card of your library. …that card" / "cards exiled this way"; "reveal cards from the
# top of your library until you reveal a creature card. …that card's mana value" (the card found);
# "put target creature on top of its owner's library" (moved: a new object there, 400.7).
_RECORDING.update({"exile_top": "exiled", "look_top": None, "to_library": None,
                   "reveal_hand_cards": "revealed"})  # (wave 10C: "Reveal any number of green cards in your hand")
_MOVERS.update({"exile_top", "to_library"})
_CHOSEN.update({"exile_top": "n", "look_top": "n", "reveal_hand_cards": "n"})


# -- delayed triggers & durations (app/rules/delayed.py, agent J) ----------------------------------
# "At the beginning of the next end step, exile it." / "Sacrifice it at the beginning of the next
# end step." / "When that creature dies this turn, return it to the battlefield." become a
# ``delayed`` effect over the deferred effects (flat, so resolve_it binds their pronouns to the
# earlier instructions of the same ability: 603.7c). "… until your next turn" / "for as long as ~
# remains on the battlefield" become an ``until`` effect over a pump / grant / restriction (611.2).
from app.rules import delayed as _delayed  # noqa: E402  (a leaf module over rules_state)

# A deferred move of "it" after "When ~ dies" / "Whenever a creature dies" still means the new
# object where it went (400.7e); deferred effects are never introducers (not in _RECORDING): a
# later sentence's "that creature" can't name what a move that hasn't happened yet would record.
_MOVES.update({_delayed.DEFERRED + x for x in _MOVES})
# -- triggers (wave 5D) -- "When this creature dies, put it on the bottom of its owner's library." (Murderous Rider): the
# card's new object in the graveyard, found there and only there (400.7e, 603.6c), as for "return it"
_MOVES.add("to_library")


def _deferred(clause: str, when: dict[str, Any], key: str = "") -> tuple[list[dict[str, Any]], Any]:
    inner = _clause(clause)
    if inner is None or any(e.get("do") in _delayed.UNDEFERRABLE for e in inner[0]):
        raise _NoMatch
    if when.get("whose") == "owner" and not (  # -- triggers (wave 17D) -- one move of "it", with "its owner" in the clause for "their"
            len(inner[0]) == 1 and inner[0][0].get("do") in ("return_card", "bounce") and inner[0][0].get("who") == "it"
            and (key != "their next upkeep" or "its owner's" in clause)):
        raise _NoMatch
    return _delayed.wrap_when(inner[0], when), inner[1]


@effect(rf"at the beginning of (?P<when>{_delayed.WHEN_RE}), (?P<clause>.+)")
def _delayed_leading(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    return _deferred(m["clause"], _delayed.WHEN[m["when"]], m["when"])


@effect(rf"(?P<clause>.+?) at the beginning of (?P<when>{_delayed.WHEN_RE})")
def _delayed_trailing(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    return _deferred(m["clause"], _delayed.WHEN[m["when"]], m["when"])


# -- other side (wave 6D) -- "Destroy that creature at end of combat." / "At end of combat, sacrifice it.": a delayed
# trigger (603.7) that triggers as the next end of combat step begins (511.2)
@effect(r"at end of combat, (?P<clause>.+)")
def _delayed_end_combat_leading(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    return _deferred(m["clause"], _delayed.END_OF_COMBAT)


@effect(r"(?P<clause>.+?) at end of combat")
def _delayed_end_combat_trailing(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    return _deferred(m["clause"], _delayed.END_OF_COMBAT)


# -- transform (wave 11A) -- Conqueror's Galleon: the delayed trigger holds both halves ("then return it" is deferred too)
@effect(r"exile (?:it|~) at end of combat, then return it to the battlefield transformed under (?P<u>your|its owner's) control")
def _delayed_exile_return_transformed(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    back = {"do": "return_card", "who": "ref:e0", "to": "battlefield", "tapped": False,
            "under": "you" if m["u"] == "your" else "owner", "transformed": True}
    return _delayed.wrap_when([{"do": "exile", "who": "self", "as": "e0"}, back], _delayed.END_OF_COMBAT), None
# -- end other side (wave 6D) --


@effect(_delayed.EVENT.pattern.lstrip("^").rstrip("$"))
def _delayed_event(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    inner = _clause(m["clause"].replace("the creature's controller", "that creature's controller"))  # (wave 16D)
    if inner is None or inner[1] is not None:  # (the deferred effect's own target: not modeled)
        raise _NoMatch
    effects = _delayed.inner_for_event(inner[0])
    if effects is None or any(e.get("do") in _delayed.UNDEFERRABLE for e in effects):
        raise _NoMatch
    when, who = _delayed.event_when(m)
    sel = None
    if who == "target":  # "When target creature dies this turn, …": the creature is this ability's target
        from app.rules import language

        group = language.target_group(m["subject"])
        if group is None:
            raise _NoMatch
        sel = group["what"]
    return _delayed.wrap_when(effects, when, who=who, this_turn=bool(m["turn"])), sel  # (-- hidden exile (wave 18A) -- no "this turn": it waits for as long as it takes, 603.7)


# -- turn watches (wave 7D; app/rules/watches.py) -- "Whenever you cast a spell this turn, draw a card." / "When you next
# cast an instant or sorcery spell this turn, copy that spell." (603.7: a delayed trigger on an ordinary event)
@effect(r"whenever (?P<cond>.+?) this turn, (?P<clause>.+)")
def _watch_whenever(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    from app.rules import events, watches

    found = watches.build(events.parse_condition(m["cond"]), m["clause"], once=False, text=m["cond"])
    return _from_language(found)


@effect(r"when you next cast (?P<spell>.+?) this turn, (?P<clause>.+)")
def _watch_next_cast(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    from app.rules import events, watches

    cond = events.parse_condition(f"you cast {m['spell']}")
    if cond is None or set(cond) - {"event", "subject", "player", "spell"}:
        raise _NoMatch
    return _from_language(watches.build(cond, m["clause"], once=True, text=f"you next cast {m['spell']}"))
# -- end turn watches (wave 7D) --


def _with_duration(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    clause, duration = _delayed.duration_clause(m)
    inner = _clause(clause)
    if inner is None:
        raise _NoMatch
    wrapped = _delayed.wrap_duration(inner[0], duration)
    if wrapped is None:
        raise _NoMatch
    return wrapped, inner[1]


@effect(rf"(?P<duration>{_delayed.DURATION_RE}), (?P<clause>.+)")
def _until_leading(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    return _with_duration(m)


@effect(rf"(?P<clause>.+?) (?P<duration>{_delayed.DURATION_RE})")
def _until_trailing(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    return _with_duration(m)


def _from_language(found: tuple[list[dict[str, Any]], Any] | None) -> tuple[list[dict[str, Any]], Any]:
    if found is None:
        raise _NoMatch
    return found


# -- activated other (wave 21E) -- "Two target players each draw a card." / "Any number of target players each mill two cards.":
# one group of player targets (601.2c: the number chosen), the instruction done for each of them (who "target" is every target
# of the group); the instruction is read as its singular form for "target player" ("each draw" -> "draws")
_EACH_VERB = {"draw": "draws", "mill": "mills", "discard": "discards", "lose": "loses", "gain": "gains"}
_EACH_PLAYERS = re.compile(rf"(?P<g>(?:any number of|up to \w+|\w+) target players) each (?P<v>{'|'.join(_EACH_VERB)}) (?P<rest>.+)")


@effect(_EACH_PLAYERS.pattern)
def _each_target_players(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    from app.rules import language

    group = language.target_group(m["g"])
    inner = _one_clause(f"target player {_EACH_VERB[m['v']]} {m['rest']}")
    if group is None or inner is None or inner[1] != "player" or group["what"] != "player" or len(inner[0]) != 1:
        raise _NoMatch
    return inner[0], group


@effect(r"sacrifice (?P<o>them|those tokens|those creatures|the tokens|those permanents|that creature|that token|"
        r"the token|that permanent|that card|the creature|that artifact)")  # (the creature / that artifact: wave 6A)
def _sacrifice_pronoun(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    from app.rules import language

    return _from_language(language.parse_sacrifice_pronoun(m["o"]))


@effect(r"return (?P<o>.+?) to the battlefield(?P<t> tapped)?(?:(?P<fd> face down) under (?:their owner's|its owner's|your) control(?: as .+)?"
        r"| under (?:their|its) owner's control)")
def _return_owner(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    from app.rules import language

    return _from_language(language.parse_return_owner(m.group(0)))


@effect(r"exile (?P<o>.+?) until ~ leaves the battlefield")
def _exile_until_any(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    from app.rules import language

    return _from_language(language.parse_exile_until(m["o"]))


# -- player choices (app/rules/language.py "player choices", app/rules/effects.py) -------------------
# Edicts ("each opponent sacrifices a creature of their choice"), "target opponent chooses a
# creature they control", a revealed hand ("target player reveals their hand. You choose a nonland
# card from it. That player discards that card."), "choose a color". The choosing primitives
# introduce objects a pronoun can name ("that card", "that creature", "it"): they record them.
def _choice_template(pattern: str, build: Any) -> None:
    def template(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
        from app.rules import language

        try:
            return build(m)
        except language._Fail:
            raise _NoMatch from None
    effect(pattern)(template)


from app.rules import language as _language  # noqa: E402  (a leaf module)

for _pattern, _build in ((_language.EDICT, _language.edict), (_language.EDICT_OTHERS, _language.edict),
                         (_language.PLAYER_CHOOSES, _language.player_chooses), (_language.REVEAL_HAND, _language.reveal_hand),
                         (_language.CHOOSE_FROM_HAND, _language.choose_from_hand), (_language.DISCARD_NAMED, _language.discard_named),
                         (_language.CHOOSE_VALUE, _language.choose_value),
                         (_language.CHOOSE_FROM_HAND_GY, _language.choose_from_hand_gy), (_language.LOOK_HAND, _language.look_hand),  # (wave 11D)
                         (_language.DISCARD_ALL_REVEALED, _language.discard_all_revealed),
                         (_language.EXILE_FROM_HAND, _language.exile_from_hand)):
    _choice_template(_pattern, _build)
from app.rules import name_search as _name_search  # noqa: E402  (a leaf module)

_choice_template(_name_search.PATTERN, _name_search.build)  # (wave 11D)
from app.rules import drawn_toll as _drawn_toll  # noqa: E402  (a leaf module)

_choice_template(_drawn_toll.PATTERN, _drawn_toll.build)  # (wave 18G)
_RECORDING.update({"edict": "sacrificed", "player_chooses": None, "choose_from_hand": None, "discard_named": "discarded",
                   "reveal_hand": None, "choose_value": None})
_MOVERS.update({"edict", "player_chooses", "choose_from_hand", "discard_named"})
_CHOSEN.update({"edict": "n", "player_chooses": "n", "choose_from_hand": "n"})


# -- temporary grants & riders (agent G: app/rules/language.py "temporary grants & riders") ----------
# "Target player draws two cards and loses 2 life": one subject for two instructions — each half is
# read with the subject repeated; a target subject is ONE target (one word "target", 115.3), so the
# second half's group is the first's. Both halves must parse, or the sentence stays manual.
@effect(_language.COMPOUND)
def _compound_subject(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    # -- X sized by a count (wave 4K) -- "Target player draws X cards and loses X life, where X is …": the trailing
    # definition of X is the whole sentence's (107.3c), so the left half reads it too
    rider = re.search(r", where X is [^\"]+$", m["r"])
    lead = f"{m['l']}{rider[0]}" if rider is not None and re.search(r"\bX\b", m["l"]) else m["l"]
    left, right = _clause(f"{m['s']} {lead}"), _clause(f"{m['s']} {m['r']}")
    if left is None or right is None:
        raise _NoMatch
    lgroups, rgroups = _as_groups(left[1]), _as_groups(right[1])
    if m["s"].startswith("target"):
        if len(lgroups) != 1 or lgroups != rgroups:
            raise _NoMatch
        return left[0] + right[0], left[1]  # (both halves name the one group: "target" / "target:0")
    if lgroups or rgroups:
        raise _NoMatch  # (a target inside a half: not read here)
    return left[0] + right[0], None


# -- animation (app/rules/language.py "animation", app/rules/effects.py ``become``, agent A2) --------
# "~ becomes a 2/2 creature with all creature types until end of turn. It's still a land."
# (Mutavault): the first sentence is a ``become`` effect (types, colors, abilities and base P/T in
# their layers, 613.6); "It's still a land." is ``still_a``, which turns the types it set into
# types added (205.1b). A quoted ability it grants must be one the engine carries out
# (``granted_ability``), else the ability stays manual.
@effect(r"(?P<text>(?:until end of turn, )?(?:have )?.+? (?:loses all abilities and )?becomes? (?:(?:a|an) |(?=\d+/\d+ [A-Za-z ]*creatures)|the basic land type of your choice|the (?:creature type|color or colors|color)(?: other than [A-Z][a-z]+)? of your choice).*)")
def _become(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    from app.rules import language

    found = language.parse_become(m["text"])
    if found is None:
        raise _NoMatch
    # (quoted grants, wave 2D: each quote is one the engine carries out as granted)
    from app.rules import granted

    for e in found[0]:
        if e["do"] == "become" and e.get("abilities"):
            checked = [granted.quote(text) for text in e["abilities"]]
            if any(c is None for c in checked):
                raise _NoMatch
            e["abilities"] = checked
    return found


# -- static wordings (wave 6E) -- "Target creature becomes red [and gains haste] until end of turn." (language._BECOME_COLOR)
@effect(r"(?P<text>(?:until end of turn, )?.+? becomes? (?:colorless|white|blue|black|red|green)\b.*)")
def _become_colored(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    found = _language.parse_become(m["text"])
    if found is None or any(e["do"] == "become" and (e.get("types") or e.get("p") is not None) for e in found[0]):
        raise _NoMatch
    return found


# -- recursion & tutors (wave 4M) -- "That creature is a black Zombie in addition to its other colors and types."
# (Rise from the Grave, Liliana, Death's Majesty), "It's a Phyrexian in addition to its other types." (Portal to
# Phyrexia): the object an earlier instruction put onto the battlefield gets the types (and colors) for as long as
# it exists (611.2a, 205.1b): the "becomes" effect above, said of a pronoun only
@effect(r"(?P<o>it|that creature|each of them|each of those creatures)(?:'s| is) (?P<desc>an? [^.]+? in addition to its other "
        r"(?:colors and )?types)")
def _is_in_addition(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    o = "each of them" if m["o"].startswith("each of") else "it"
    found = _language.parse_become(f"{o} becomes {m['desc']}")
    if found is None or any(e["do"] != "become" or e.get("abilities") or e.get("lose_abilities") for e in found[0]):
        raise _NoMatch
    return found


# -- entry forms (wave 5F) -- "It's an enchantment." after "return it to the battlefield" (the Enduring cycle): the card
# types are set as it enters (611.2e; app/rules/entry_forms.py) — read only right after such a return (``define``)
@effect(r"it's an enchantment(?: \(it's not a creature\.?\))?")
def _enters_as_enchantment(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    return [{"do": "enters_as", "who": "it", "types": ["Enchantment"]}], None


_RECORDING["enters_as"] = None


@_first  # (before agent J's "until your next turn" wrapper, which only wraps pumps, grants and restrictions)
@effect(r"(?P<text>(?:until your next turn, (?:have )?.+? becomes? (?:(?:a|an) |(?=\d+/\d+ )).+|(?:have )?.+? becomes? (?:(?:a|an) |(?=\d+/\d+ )).+ until your next turn))")
def _become_next_turn(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    return _become(m)


@_first  # ("… until your next turn": before agent J's wrapper, as above)
@effect(_language.BASE_PT)
def _base_pt(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    try:
        return _language.parse_base_pt(m)
    except _language._Fail:
        raise _NoMatch from None


# -- static_other sweep (wave 19A) -- "Until end of turn, creatures target player controls lose all abilities and have base power and
# toughness 0/2." (Sudden Spoiling), "… each creature target player controls loses all abilities and becomes a blue Frog with base
# power and toughness 1/1" (Polymorphist's Jest), "Until your next turn, creatures target player controls have base power and toughness
# 1/1" (Mass Diminish): the group's own grammar for "all creatures …", over the creatures that player controls as it resolves (608.2c),
# locked in then (611.2c)
@_first
@effect(r"(?P<lead>(?:until end of turn|until your next turn), )?(?:each creature|creatures) target (?P<pl>player|opponent) controls "
        r"(?P<rest>(?:loses? all abilities and )?(?:becomes? .+|(?:has|have) base .+))")
def _their_creatures_become(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    text = f"{m['lead'] or ''}all creatures {re.sub(r'^lose ', 'loses ', m['rest'])}"
    bm = _language.re.fullmatch(_language.BASE_PT, text)
    try:
        found = _language.parse_base_pt(bm) if bm else _language.parse_become(text)
    except _language._Fail:
        raise _NoMatch from None
    if found is None or any(e["do"] != "become" or e.get("abilities") or not e["who"].startswith("sel:") for e in found[0]):
        raise _NoMatch
    return [{**e, "who": f"controlled:target|{e['who']}"} for e in found[0]], SELECTORS[f"target {m['pl']}"]


@effect(_language.STILL_A)
def _still_a(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    return _language.parse_still(m)


@_first  # (the general prevention template rejects the pronoun)
@effect(r"prevent all damage that would be dealt to (?:him|her) this turn")
def _prevent_to_self(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    """Gideon: "Until end of turn, Gideon becomes a 6/6 … creature that's still a planeswalker.
    Prevent all damage that would be dealt to him this turn." — Oracle's "him" / "her" is the
    named planeswalker itself, the ability's source: the "~" of ``prevent_all`` (locked to the
    source object, 615, 400.7)."""
    return [{"do": "prevent_all", "scope": {"combat": None, "to_objects": "self"}}], None


@_first  # (before the "until your next turn, …" duration wrapper, which only wraps pumps, grants and restrictions)
@effect(r"(?P<text>until your next turn, .+ spells you cast cost {{\d+}} (?:less|more) to cast)")
def _stored_cost_next_turn(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    """Ral, Leyline Prodigy's +1: "Until your next turn, instant and sorcery spells you cast cost
    {1} less to cast." — a stored cost modifier (app/rules/permissions.py ``cost_modifier``)."""
    from app.rules import permissions

    got = permissions.parse_clause(m["text"])
    if got is None:
        raise _NoMatch
    return got


_RECORDING.update({"become": None})


# =====================================================================================================
# -- conditional / instead clauses (wave 1B) --
# Conditions (app/rules/conditions.py) gating the effects that follow, read against CR 608.2c ("later
# text on the card may modify the meaning of earlier text … read the whole text and apply the rules of
# English"), 608.2h (information from the game is determined once, as the effect is applied), 608.2i
# (effects that look back in time) and 614.1a ("instead" effects are replacement effects: the resolving
# spell or ability applies its own "instead" text to the instruction it modifies, as it reaches it).
#
#   "If C, X."                — X happens only if C holds as it's carried out
#   "X. If C, Y instead."     — C is judged ONCE, as X would be carried out (the verdict is recorded: a
#     "X. Y instead if C."      ``flag`` binding); if it holds, Y replaces X — all of X: Y must be at least
#     "X. If C, instead Y."     as big (an "instead" that could replace only part of the sentence before it
#                               is never guessed) and have no target of its own
#   "If C, X. Otherwise, Z."  — Z happens when C didn't hold (the same recorded verdict)
#   "X if C." / "X unless C." — one instruction, gated (a lead of several instructions isn't read: which
#                               of them the condition belongs to is English, not grammar)
# "It" in a condition is the object the sentence is about: a plain target, what an earlier instruction
# moved or chose (its recorded object, 400.7j), the source, the trigger event's object.
# Refused, never guessed: an "instead" clause that isn't a condition the engine reads (replacement
# effects a resolving spell creates, "If that creature would die this turn, exile it instead": 614.1a
# continuous replacement effects are a different mechanism), a pronoun in one branch that names what
# the other branch's instruction would have moved, a chain of "instead" clauses.
# (Wave 3R1: a pronoun naming the replaced instruction's own target — or the source — is that object:
# _branch_refs_retarget. "Other" after the spell made tokens is other than those tokens: _gated_other_rewrite.
# Still refused: chains, an "instead" with a target of its own — its targets would depend on the condition,
# 115.3 / 601.2c — and a pronoun naming what a non-target instruction moved.)
# ==============================================================================================

_BRANCHING = frozenset({"only_if", "kicked_gate", "optional_payment", "delayed", "until", "record_action", "action_gate",
                        "bind_refs"})
_INSTEAD_FORMS = (re.compile(r"^if (?P<c>[^,]+), (?P<rest>.+) instead$"),
                  re.compile(r"^if (?P<c>[^,]+), instead (?P<rest>.+)$"),
                  re.compile(r"^(?P<rest>.+) instead if (?P<c>.+)$"))
_OTHERWISE = re.compile(r"^otherwise, (?P<rest>.+)$")
_TRAILING = re.compile(r"^(?P<lead>.+?) (?P<kw>if|unless) (?P<c>.+)$")
_REF_NAME = re.compile(r"^ref:(?P<name>e\d+)(?:\..*)?$")


def _cond_has_it(cond: dict[str, Any]) -> bool:
    from app.rules import conditions

    return conditions._has_objects(cond)


def _bind_cond(cond: dict[str, Any], ref: str) -> dict[str, Any]:
    from app.rules import conditions

    return conditions.bind_objects(cond, ref)


def _conditional_inner(rest: str, cond: dict[str, Any] | None = None) -> tuple[list[dict[str, Any]], Any] | None:
    """The instruction(s) of "If C, [rest]" / "Otherwise, [rest]": its own targets (115.3) are its own
    groups; "you may …" only when the clause models its own choice (else the gate would make the whole
    effect optional, or ask nothing). ``cond``: the condition it belongs to, whose subject "it" names
    when that is the source ("If this enchantment isn't a creature, it becomes …")."""
    from app.rules import (
        kicked_instead,  # -- ability words (wave 9C) -- "If C, ~ also gains double strike" (an addition)
    )

    rest = kicked_instead.plain_addition(rest)
    found = _clause(rest)
    if found is None or not found[0]:
        return None
    if rest.startswith("you may ") and not any(e.get("optional") for e in found[0]):
        return None
    return _bind_subject(cond, found) if cond is not None else found


def _holds_pronoun(value: Any) -> bool:
    """Does an effect still hold a pronoun placeholder (its controller, its power, them, "it deals")?"""
    if isinstance(value, list):
        return any(_holds_pronoun(v) for v in value)
    if not isinstance(value, dict):
        return False
    for k, x in value.items():
        if k == "who" and isinstance(x, str) and (x == "them" or x.startswith(("it.", "it:", "them:"))):
            return True
        if (k == "src" or k in _STAT_KEYS) and x == "it":
            return True
        if _holds_pronoun(x):
            return True
    return False


def _bind_subject(cond: dict[str, Any], found: tuple[list[dict[str, Any]], Any] | None) -> tuple[list[dict[str, Any]], Any] | None:
    """"If this enchantment isn't a creature, it becomes …": when the condition is about the source itself
    ("~"), "it" in what follows is the source — the subject of the sentence — not the trigger event's
    object or an earlier sentence's. Other pronouns there (its controller, its power, them) aren't read."""
    from app.rules import conditions

    if found is None or set(conditions.objects_in(cond)) != {"self"}:
        return found
    if conditions.is_cast_condition(cond):  # -- refused modal/conditional (wave 3R1) -- "If this spell was cast from a
        return found  # graveyard, …": how the spell was cast isn't the subject of what follows

    effects = []
    for e in found[0]:
        e = {**e, "who": "self"} if e.get("who") == "it" else e
        if _holds_pronoun(e):
            return None
        effects.append(e)
    return effects, found[1]


def _replaceable(base: list[dict[str, Any]], alt: list[dict[str, Any]]) -> bool:
    """Does ``alt`` take the place of all of ``base`` ("X. If C, Y instead.")? Y must be at least as big
    as X: a Y with fewer instructions could be replacing only part of X's sentence, and dropping the
    rest of X would be wrong. Neither may itself branch (a chain of "instead" clauses)."""
    if not base or not alt or len(alt) < len(base):
        return False
    return not any(e["do"] in _BRANCHING for e in (*base, *alt))


def _next_flag(effects: list[dict[str, Any]]) -> str:
    return f"cond{sum(1 for e in effects if str(e.get('bind') or '').startswith('cond'))}"


def _instead_or_otherwise(text: str, effects: list[dict[str, Any]], prev_start: int,
                          groups: list[dict[str, Any]], it: str | None = None) -> tuple[list[dict[str, Any]], int] | Literal[False] | None:
    """One sentence as an "instead" / "Otherwise" clause of the sentence before it: None (it isn't one),
    False (it is, but not one the engine reads: the whole ability stays manual), or the effects so far
    with it added and how many effects it put before its own first (the gate goes before the sentence
    it replaces). The condition is judged once, before the replaced instruction (608.2c)."""
    from app.rules import conditions

    m = next((found for found in (form.match(text) for form in _INSTEAD_FORMS) if found is not None), None)
    if m is not None:
        cond = conditions.parse(m["c"], objects=True)
        rest = m["rest"]
        base = effects[prev_start:]
        if cond is None or rest.startswith("you may ") or not base:
            return False
        # -- kicked / instead (wave 4G) -- "it deals 7 damage instead" (608.2c)
        from app.rules import kicked_instead

        outer = None  # "If C1, X. If C2, Y instead." with C2 holding only when C1 does: Y replaces X inside C1's gate
        if (len(base) > 1 and base[0]["do"] == "only_if" and not base[0].get("bind") and base[0].get("skip") == len(base) - 1
                and kicked_instead.implies(cond, base[0]["cond"])):
            outer, base = base[0], base[1:]
            prev_start += 1
        rest = kicked_instead.plain_pronoun(rest)
        restated = kicked_instead.restate(rest, base)
        spell_cond = _cast_trigger_spell_cond(cond)  # -- ability words (wave 9C) -- opus: the cast trigger's spell, never a target
        if restated is not None and it is not None and _cond_has_it(cond) and not spell_cond:
            return False  # ("If that land is a Mountain, ~ deals 2 damage instead": the trigger's land, not the target)
        if rest.startswith("it deals ") and base[0]["do"] == "damage" and not base[0].get("src"):
            rest = "~ deals " + rest[len("it deals "):]  # (the source of the damage the sentence before it dealt)
        alt = (restated, None) if restated is not None else _bind_subject(cond, _clause(rest))
        if alt is None or alt[1] is not None or not _replaceable(base, alt[0]):
            return False
        if _cond_has_it(cond) and not spell_cond:  # "it": what the replaced sentence is about — its one target (else an earlier object)
            whos = {str(e["who"]) for e in base if str(e.get("who") or "").startswith("target")}
            if len(whos) > 1:
                return False
            if whos:
                cond = _bind_cond(cond, next(iter(whos)))
        flag = _next_flag(effects)
        if outer is not None:  # -- kicked / instead (wave 4G) -- (the outer gate now covers both branches)
            effects = [*effects[:prev_start - 1], {**outer, "skip": len(base) + len(alt[0]) + 2}, *effects[prev_start:]]
        return [*effects[:prev_start], {"do": "only_if", "cond": {"not": cond}, "skip": len(base), "bind": flag}, *base,
                {"do": "only_if", "cond": {"flag": flag, "negate": True}, "skip": len(alt[0])}, *alt[0]], 1
    m = _OTHERWISE.match(text)
    if m is not None:
        gate = effects[prev_start] if prev_start < len(effects) else None
        if (gate is None or gate["do"] != "only_if" or gate.get("bind") or "succeeded" in gate["cond"]
                or gate.get("skip") != len(effects) - prev_start - 1):
            return False  # ("Otherwise" belongs to the "If C, X." sentence right before it, and to nothing else)
        alt = _conditional_inner(m["rest"], gate["cond"])
        if alt is None:
            return False
        flag = _next_flag(effects)
        added = _add_groups(groups, *alt)
        return [*effects[:prev_start], {**gate, "bind": flag}, *effects[prev_start + 1:],
                {"do": "only_if", "cond": {"flag": flag, "negate": True}, "skip": len(added)}, *added], 0
    return None


def _trailing_conditional(text: str) -> tuple[list[dict[str, Any]], Any] | None:
    """"[One instruction] if [condition]." / "… unless [condition].": the instruction gated by the
    condition as it's carried out. "It" in the condition is the instruction's own target (a plain target
    is read as it is, 608.2h)."""
    from app.rules import conditions

    m = _TRAILING.match(text)
    if m is None or m["lead"].startswith(("if ", "unless ", "you may ")):
        return None
    cond = conditions.parse(m["c"], objects=True)
    found = _bind_subject(cond, _clause(m["lead"])) if cond is not None else None
    if cond is None or found is None or len(found[0]) != 1:
        return None
    lead_groups = _as_groups(found[1])
    if _cond_has_it(cond) and lead_groups:
        if len(lead_groups) > 1 or _is_player_group(lead_groups[0]):
            return None
        cond = _bind_cond(cond, "target")  # (the lead's one target: numbered with its group by _add_groups)
    elif _cond_has_it(cond) and found[0] and all(e.get("who") == "host" for e in found[0]):
        cond = _bind_cond(cond, "host")  # -- attached events (wave 8D) -- "… on equipped creature if it's red": "it" is the host
    if m["kw"] == "unless":
        cond = {"not": cond}
    return [{"do": "only_if", "cond": cond, "skip": 1}, *found[0]], found[1]


# Optional actions that, once the player has said yes, can't come out as "did nothing": a card drawn (an
# empty library loses the game at the next check whatever follows), a token created, a chosen target
# exiled or returned (115.3 / 608.2b: a target that is no longer legal stops the whole ability, so one that
# is still legal is acted on). An object named any other way ("exile it": the card may have left where it
# was) might not be there: "If you do" would then be false, which this reading can't tell.
_CERTAIN_WHEN_CHOSEN = frozenset({"draw", "create_token"})
_CERTAIN_ON_A_TARGET = frozenset({"exile", "bounce", "gain_control"})  # (wave 19E: gain control of a chosen target: it changes hands or the ability fizzles)
_PROBED = frozenset({"draw", "exile", "bounce", "add_counters"})  # (their "If you do" reads the result: effects._did)


def _probed_move(e: dict[str, Any]) -> bool:
    """-- refused modal/conditional (wave 3R1) -- Academy Rector: "When this creature dies, you may exile it. If you
    do, …": the exile is probed (effects._did: the card it became in the graveyard reached exile), so "If you do" is
    false when the card had already left (400.7: there's nothing to exile) — no certainty is needed."""
    if e["do"] == "add_counters":  # -- if you do (wave 15C) -- counters on a chosen object: probed (effects._did_counters_up)
        return isinstance(e.get("who"), str) and isinstance(e.get("n"), int) and e["n"] > 0 and not e.get("optional")
    return e["do"] in ("exile", "bounce") and isinstance(e.get("who"), str) and not e.get("optional")


def _certain_when_chosen(e: dict[str, Any]) -> bool:
    if not isinstance(e.get("n", 1), int):
        return False  # (a count that could be zero)
    return e["do"] in _CERTAIN_WHEN_CHOSEN or (e["do"] in _CERTAIN_ON_A_TARGET and str(e.get("who")).startswith("target"))


def _if_you_do_after_may(if_do: re.Match[str], effects: list[dict[str, Any]], optional: bool, index: int,
                         sentences: int) -> tuple[list[dict[str, Any]], Any] | None:
    """"You may [do A]. If you do, [B]." as a whole-ability "you may" (608.2d): the player chooses once,
    and either does A and then B, or neither — exactly what "If you do" says while A can't fail once
    chosen (``_certain_when_chosen``; A itself decides nothing else: no cost). Only the two-sentence form:
    anything after B would then be optional too. B is no "you may" itself. Returns B's effects and its
    target spec, or None (not read).
    -- "this way" outcomes (wave 4A) -- B may have a target of its own ("When this creature dies, you may exile
    it. If you do, return target card from your graveyard to your hand."): like every target of a triggered
    ability it is chosen as the ability is put on the stack (603.3d), whatever the player answers later; the
    "you may" is asked on resolution (603.5), and with no legal target left the ability doesn't resolve at all
    (608.2b), A included — which is what the rules say for the printed ability too."""
    if not optional or index != 1 or sentences != 2 or if_do["neg"] or if_do["rest"].startswith("you may "):
        return None
    if not effects or not all(_certain_when_chosen(e) or _probed_move(e) for e in effects):  # (wave 3R1: a probed move)
        return None
    found = _clause(if_do["rest"])
    if found is None or not found[0]:
        return None
    return found[0], found[1]


def _may_then_if_you_do(text: str, following: list[str], effects: list[dict[str, Any]], probe: bool = True) -> tuple[list[dict[str, Any]], Any] | None:
    """-- if you do (wave 15C) -- "[A]. You may draw a card. If you do, discard a card." as the last two sentences of an ability
    that did something first (The Celestus, Gate to the Afterlife): the player is asked once as the resolution reaches it
    (608.2d, unless_pays.may_rest: "no" ends the resolution), and "if you do" reads what the draw actually did (a draw
    replaced or impossible is not "done", 608.2c) — the same certainty rule as the whole-ability form above."""
    m = _IF_YOU_DO.match(_lower_first(following[0].rstrip(".").strip())) if len(following) == 1 else None
    if m is None or m["neg"] or m["rest"].startswith("you may "):
        return None
    a, b = _clause(text[len("you may "):]), _clause(m["rest"])
    if a is None or b is None or a[1] is not None or not a[0] or not b[0]:
        return None
    if not all(_certain_when_chosen(e) or _probed_move(e) for e in a[0]):
        return None
    taken = sum(1 for e in effects if str(e.get("did") or "").startswith("midid"))
    probes = [f"midid{taken + k}" for k, e in enumerate(e for e in a[0] if e["do"] in _PROBED)]
    for e, name in zip((e for e in a[0] if e["do"] in _PROBED), probes, strict=True):
        if probe:  # (probe=False: only asking whether the sentence is read; nothing is marked)
            e["did"] = name
    gate: list[dict[str, Any]] = []
    if probes:
        cond: dict[str, Any] = {"succeeded": probes[0]} if len(probes) == 1 else {"all": [{"succeeded": n} for n in probes]}
        gate = [{"do": "only_if", "cond": cond, "skip": len(b[0])}]
    return [{"do": "may_rest"}, *a[0], *gate, *b[0]], b[1]


def _refs_in(value: Any) -> Iterator[str]:
    """The names of the earlier effects' bindings a value refers to ("ref:e3", "ref:e3.controller")."""
    if isinstance(value, str):
        m = _REF_NAME.match(value)
        if m:
            yield m["name"]
    elif isinstance(value, list):
        for v in value:
            yield from _refs_in(v)
    elif isinstance(value, dict):
        for v in value.values():
            yield from _refs_in(v)


def _mentions_other(value: Any) -> bool:
    """Does an effect select "other" objects ("destroy all other creatures": other than what)?"""
    from app.rules import selectors

    if isinstance(value, str):
        return value.startswith(selectors.PREFIX) and selectors.from_key(value).other
    if isinstance(value, list):
        return any(_mentions_other(v) for v in value)
    return isinstance(value, dict) and any(_mentions_other(v) for v in value.values())


def _gated_other_ok(effects: list[dict[str, Any]]) -> bool:
    """A gated instruction that says "other" after the ability made tokens ("Create X 1/1 Soldier creature
    tokens. If X is 5 or more, destroy all other creatures." — Martial Coup's rulings: other than the tokens)
    is refused: the engine's "other" is other than the source, which for a spell isn't on the battlefield, so
    it would destroy the tokens too."""
    made = False
    for i, e in enumerate(effects):
        made = made or e["do"] in ("create_token", "create_attacking")
        if made and e["do"] == "only_if" and _mentions_other(effects[i + 1:i + 1 + int(e.get("skip", len(effects)))]):
            return False
    return True


# -- refused modal/conditional (wave 3R1) --
def _gated_other_rewrite(effects: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Martial Coup / White Sun's Twilight: "Create X … tokens. If X is 5 or more, destroy all other creatures." —
    the rulings read "other" as other than the tokens just created (the spell itself isn't on the battlefield). With
    exactly one token-making instruction before the gate, a "who" selector saying "other" there becomes "every one
    of them except what that instruction made" (``except:<binding>|<selector>``: effects._cards). Anything else
    stays as it was (and _gated_other_ok refuses it)."""
    from app.rules import selectors

    makers = [i for i, e in enumerate(effects) if e["do"] == "create_token"]
    if len(makers) != 1 or any(e["do"] == "create_attacking" for e in effects):
        return effects
    k = makers[0]
    out = [dict(e) for e in effects]
    for i, e in enumerate(effects):
        if i < k or e["do"] != "only_if":
            continue
        for j in range(i + 1, min(len(effects), i + 1 + int(e.get("skip", len(effects))))):
            who = out[j].get("who")
            if not (isinstance(who, str) and who.startswith(selectors.PREFIX) and selectors.from_key(who).other):
                continue
            if _mentions_other({kk: v for kk, v in out[j].items() if kk != "who"}):
                return effects
            name = out[k].setdefault("as", f"made{k}")
            out[j]["who"] = f"except:{name}|{replace(selectors.from_key(who), other=False).key()}"
    return out


# "If you do" after an instruction that isn't optional ("Sacrifice this enchantment. If you do, create …", "Remove a
# +1/+1 counter from it. If you do, …", "Discard a card. If you do, draw a card.", "Return it to its owner's hand. If
# you do, …"): whether that one instruction was actually carried out (608.2c), probed as it runs (effects._did_r1,
# effects._did). The sentence before must be that one instruction (an intervening "if" of a trigger may gate it).
_DID_MANDATORY = frozenset({"sacrifice", "sacrifice_choice", "remove_counters", "discard", "exile", "bounce"})


def _if_you_do_after_mandatory(if_do: re.Match[str], effects: list[dict[str, Any]],
                               prev_start: int) -> tuple[str, tuple[list[dict[str, Any]], Any]] | None:
    """The probe name and B's effects for "[A]. If you do[n't], [B].", or None (not read)."""
    if if_do["rest"].startswith("you may "):
        return None
    found = _clause(if_do["rest"])
    if found is None or not found[0]:
        return None
    name = _probe_previous(effects, prev_start)
    return (name, found) if name is not None else None


# -- reflexive discards (wave 19C) -- "Draw a card, then discard a card. When you discard a creature card this way, …" (603.12)
_REFLEX_DISCARD = re.compile(r"^when you discard (?P<w>a card|a nonland card|a creature card) this way, ", re.I)


def _reflexive(rest: str, effects: list[dict[str, Any]], prev_start: int, optional: bool,
               it: str | None = None) -> dict[str, Any] | None:
    """"[A]. When you do, [B]." (603.12): a reflexive triggered ability that triggers if A was done — a "you may
    [cost]" payment made (118.12), or an instruction that isn't optional actually carried out (probed as it runs) —
    and whose B (everything to the end of the ability) is put on the stack afterwards with its own targets and
    "you may" (603.3c-d). B is read alone: a pronoun in it naming what A did ("that creature's power") isn't read."""
    base = effects[prev_start:]
    if (disc := _REFLEX_DISCARD.match(rest)) is not None:  # -- reflexive discards (wave 19C) -- the discard just before, counted "this way"
        last = base[-1] if base else None
        cond_d = this_way.condition(f"{disc['w']} was discarded this way")
        tail = rest[disc.end():]
        if last is None or last["do"] != "discard" or last.get("who") not in (None, "you") or last.get("n") != 1 \
                or any(last.get(k) for k in ("all", "random", "upto", "to", "zone")) or cond_d is None:
            return None
        parsed_d = parse_effects(tail[:1].upper() + tail[1:], "self" if it == "self" else None)
        if parsed_d is None or not parsed_d[0]:
            return None
        return {"do": "reflexive", "cond": cond_d, "ability": {"kind": "triggered", "trigger": "reflexive", "effects": parsed_d[0],
                                                             "optional": parsed_d[2], **target_fields(parsed_d[1])}}
    if len(base) == 1 and base[0]["do"] == "optional_payment" and base[0].get("bind"):
        cond: dict[str, Any] = {"succeeded": base[0]["bind"]}
    elif (name := _probe_previous(effects, prev_start)) is not None and (not optional or prev_start == 0):
        # (-- death triggers (wave 20C) -- "When this creature dies, you may exile it. When you do, …": the "may" at the head of an
        # ability is asked as it resolves, then A runs and B follows only if A was done, 603.12)
        cond = {"succeeded": name}
    else:
        return None
    body = rest[len("When you do, "):] if rest.startswith("When you do, ") else rest[len("when you do, "):]
    # -- reflexive LKI (wave 4J) -- "… sacrifice another creature. When you do, ~ deals damage equal to that creature's
    # power …": the sacrificed object, as it last existed (608.2h, 113.7a), is the reflexive trigger's event object
    lki = _reflexive_lki(base, cond["succeeded"], body)
    if lki is not None:
        body = lki
    # -- end reflexive LKI (wave 4J) --
    # (-- trigger tail (wave 15B) -- "it" is the ability's source when the trigger is about it: "you may pay {2}{R}. When you do, it
    # deals 3 damage to any target"; the reflexive ability has that same source, 603.12)
    parsed = parse_effects(body[:1].upper() + body[1:], "event" if lki is not None else ("self" if it == "self" else None))
    if parsed is None or not parsed[0]:
        return None
    b_effects, b_target, b_optional = parsed
    out = {"do": "reflexive", "cond": cond, "ability": {"kind": "triggered", "trigger": "reflexive", "effects": b_effects,
                                                        "optional": b_optional, **target_fields(b_target)}}
    if lki is not None:
        out["lki"] = cond["succeeded"]  # -- reflexive LKI (wave 4J) --
    return out


# -- reflexive LKI (wave 4J) -------------------------------------------------------------------------------------------
# "You may sacrifice a/another creature. When you do, …": the reflexive ability (603.12) reads the sacrificed object
# ("that creature's power", "the sacrificed creature's toughness") as it last existed on the battlefield (608.2h,
# 113.7a: an ability's effect can read an object that left through its last known information). The sacrificed object
# is carried to the reflexive trigger as its event object (effects.reflexive); the body is then read with "that
# creature" meaning it. Only one object sacrificed, and only stat phrases: any other mention of it ("If the sacrificed
# creature was a Giant", "return it") stays manual.
_SAC_ONE = re.compile(r"^sacrifice (?:a|an|another) [a-z ,]+$", re.I)
_LKI_STAT = re.compile(r"\b(?:that|the sacrificed) (?:creature|artifact|permanent)'s (power|toughness|mana value)\b")
_LKI_OTHER = re.compile(r"\b(?:it|its|itself|they|them|that creature|that artifact|that permanent|the sacrificed)\b")


def _reflexive_lki(base: list[dict[str, Any]], name: str, body: str) -> str | None:
    """The body with each stat phrase about the sacrificed object worded for the event object ("that permanent's
    power"), or None: no such phrase, more than one object, or another mention of it."""
    if not _LKI_STAT.search(body):
        return None
    if not (len(base) == 1 and base[0]["do"] == "optional_payment" and base[0].get("bind") == name
            and _SAC_ONE.fullmatch(str(base[0].get("cost") or ""))):
        return None  # (a mandatory "Sacrifice a creature. When you do, …" — Tip the Scales — isn't read yet)
    out = _LKI_STAT.sub(lambda m: f"that permanent's {m[1]}", body)
    if _LKI_OTHER.search(_LKI_STAT.sub("", out)):
        return None
    return out
# -- end reflexive LKI (wave 4J) ---------------------------------------------------------------------------------------


def _probe_previous(effects: list[dict[str, Any]], prev_start: int) -> str | None:
    """A probe on the one instruction of the sentence before ("Sacrifice ~."), named for its "If you do" / "When
    you do" (effects._did_r1 / effects._did); None if that sentence isn't one such instruction."""
    base = effects[prev_start:]
    if len(base) == 2 and base[0]["do"] == "only_if" and not base[0].get("bind") and base[0].get("skip") == 1:
        base = base[1:]  # (a trigger's intervening "if" in that sentence: it gates A, and so B)
    if len(base) != 1 or base[0]["do"] not in _DID_MANDATORY or base[0].get("did") or base[0].get("optional"):
        return None
    if base[0].get("all"):  # -- "this way" outcomes (wave 4A) -- "Discard your hand. If you do, …" with an empty hand:
        return None  # whether that was "done" isn't settled here (UNCERTAIN): not read
    if base[0]["do"] in ("exile", "bounce") and not isinstance(base[0].get("who"), str):
        return None
    name = f"mdid{sum(1 for e in effects if str(e.get('did') or '').startswith('mdid'))}"
    base[0]["did"] = name
    return name


def _branch_blocks(effects: list[dict[str, Any]]) -> list[tuple[int, int]]:
    """The instructions only one branch of an "instead" / "Otherwise" clause runs ([start, end) of each): an only_if
    block, and (wave 13E) the base and the kicked alternative of "If this spell was kicked, … instead"."""
    return [(i + 1, min(len(effects), i + 1 + int(e.get("skip", len(effects)) if e["do"] == "only_if" else e.get("n", 0))))
            for i, e in enumerate(effects)
            if (e["do"] == "only_if" and (e.get("bind") or "flag" in e["cond"])) or e["do"] == "kicked_gate"]


def _branch_refs_retarget(effects: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """"Return target permanent to its owner's hand. If that permanent is red or green, put it on top of its owner's
    library instead." (Consign to Dream): the pronoun in the "instead" branch names the object the replaced
    instruction would have acted on — it never did (614.6: a replaced event never happens), so that is the object as
    the replaced instruction named it: its target (or the source). Such a reference across the branches is
    rewritten to that target; any other one stays (and _branch_refs_ok refuses it)."""
    blocks = _branch_blocks(effects)
    if not blocks:
        return effects
    produced = {e["as"]: (i, e.get("who")) for i, e in enumerate(effects) if e.get("as")}
    out = []
    for i, e in enumerate(effects):
        changed = dict(e)
        for key, value in e.items():
            m = _REF_NAME.match(value) if isinstance(value, str) else None
            if m is None or value != f"ref:{m['name']}" or m["name"] not in produced:
                continue
            k, who = produced[m["name"]]
            across = any(lo <= k < hi and not lo <= i < hi for lo, hi in blocks)
            if across and isinstance(who, str) and (who in ("target", "self") or re.fullmatch(r"target:\d+", who)
                                                    or who.startswith(("controlled:target", "sel:")) or who == "creatures_you_control"):
                changed[key] = who  # (wave 13E: a group is named again as the branch that ran reads it, 608.2c)
        out.append(changed)
    return out


def _did_refs_ok(effects: list[dict[str, Any]]) -> bool:
    """After "Sacrifice this enchantment. If you do, destroy that creature." the pronoun is the trigger's creature,
    never what A sacrificed — but the pronoun grammar names the latest object: an instruction of the ability that
    acts on ("who") what a probed A moved is refused. Reading its characteristics (its toughness, "it deals") is
    fine: that is the object as it last existed (608.2h)."""
    probed = {str(e["as"]) for e in effects if str(e.get("did") or "").startswith("mdid") and e.get("as")}
    return not probed or not any(isinstance(e.get("who"), str) and (m := _REF_NAME.match(e["who"])) is not None
                                 and m["name"] in probed for e in effects)


def _cast_conditions_ok(effects: list[dict[str, Any]]) -> bool:
    """A condition about how a spell was cast ("if you cast it", "if {R} was spent to cast it") is read only of
    the source itself — the spell, or the permanent it became, whose payment record it keeps — never of another
    object "it" names (a trigger's creature, a target): their records aren't kept."""
    from app.rules import conditions

    return all(conditions.cast_conditions_on_source(e["cond"]) for e in effects
               if e["do"] == "only_if" and conditions.is_cast_condition(e["cond"]))
# -- end refused modal/conditional (wave 3R1) --


def _branch_refs_ok(effects: list[dict[str, Any]]) -> bool:
    """Nothing refers to what an instruction in an "instead" / "Otherwise" branch moved or chose, from
    outside that branch: only one of the branches happens, so the other branch's (and any later)
    "it" / "its controller" would name nothing, silently — the ability stays manual instead."""
    blocks = _branch_blocks(effects)
    if not blocks:
        return True
    produced = {e["as"]: i for i, e in enumerate(effects) if e.get("as")}
    for i, e in enumerate(effects):
        for name in _refs_in(e):
            k = produced.get(name)
            if k is None:
                continue
            for lo, hi in blocks:
                if lo <= k < hi and not lo <= i < hi:
                    return False
    return True

# -- copy system (wave 2F): copying spells, abilities and permanents (CR 707; app/rules/copying.py) --
# "Copy target instant or sorcery spell[, except that the copy is red]." / "Copy target triggered
# ability you control." then "You may choose new targets for the copy." (707.10, 707.10c); "Create
# a token that's a copy of target creature[, except it has haste]." (707.9); "~ becomes a copy of
# target creature until end of turn." (707.4); "You may have ~ enter as a copy of any creature on the
# battlefield[, except …]." (707.5, a replacement effect). Each is tried before the older templates
# (a "becomes a …" or "create … token" template would otherwise claim and reject the sentence).
# =====================================================================================================
def _copy_static(text: str) -> Definition | None:
    from app.rules import copying

    return copying.define_static(text)


@_first
@effect(r"copy target (?P<what>.+?)(?:, except (?P<exc>.+))?")
def _copy_target(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    from app.rules import copying

    found = copying.parse_copy_target(m["what"], m["exc"])
    if found is None:
        raise _NoMatch
    return found


@_first
@effect(r"you may choose new targets for the cop(?:y|ies)")
def _copy_new_targets(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    return [{"do": "copy_new_targets", "optional": True}], None  # (read by the copy before it: 707.10c)


@_first
@effect(r"create (?P<n>a|an|one|two|three|four|five|six|seven|eight|nine|ten|x|X|\d+) (?P<tapped>tapped (?P<atk>and attacking )?)?tokens? "
        r"that(?:'s| are) (?:a )?cop(?:y|ies) of (?P<src>.+?)(?P<atk2> and that's tapped and attacking)?"
        r"(?P<each> for each time (?:it|this creature) was kicked)?(?:, except (?P<exc>.+))?")
def _token_copy(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    from app.rules import copying

    found = copying.parse_token_copy(m["n"], bool(m["tapped"] or m["atk2"]), m["src"], m["exc"])
    if found is None:
        raise _NoMatch
    if m["atk"] or m["atk2"]:  # -- token copy (wave 20F) -- 508.4: it enters tapped and attacking (token_grammar.enter_attacking)
        found[0][0]["attacking"] = True
    if m["each"]:  # -- keywords (wave 15E) -- squad 702.157a: once for each time its cost was paid (702.33d's count)
        found[0][0]["n"] = {"kicked": 1}
    return found


# -- casting extras (wave 18E) -- 702.167a craft: "Return this card to the battlefield transformed under its owner's control" (the card
# the cost exiled: effects._cards "cost_exiled_self")
@_first
@effect(r"return this card to the battlefield transformed under its owner's control")
def _craft_return(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    return [{"do": "return_card", "who": "cost_exiled_self", "to": "battlefield", "tapped": False, "under": "owner",
             "transformed": True}], None


# -- casting extras (wave 18E) -- 702.141a encore: one token copy for each opponent (one creation event), each attacking its opponent
@_first
@effect(r"for each opponent, create a token that's a copy of the card exiled to activate this ability that attacks that opponent "
        r"this turn if able")
def _encore_copies(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    return [{"do": "token_copy", "n": {"opponents": 1}, "who": "cost_exiled"}, {"do": "encore_attack", "who": "it"}], None


# -- if you do (wave 8C) -- "that creature's controller creates a token that's a copy of that creature" (Bramble Sovereign):
# the copy's maker is the object's controller (111.2: the player who creates it owns it), not the ability's
@_first
@effect(r"(?:that creature's|its) controller creates (?P<n>a|one) (?P<tapped>tapped )?token that's a copy of (?P<src>it|that creature)")
def _their_token_copy(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    from app.rules import copying

    found = copying.parse_token_copy(m["n"], bool(m["tapped"]), m["src"], None)
    if found is None or found[1] is not None:
        raise _NoMatch
    return [{**found[0][0], "their": True}], None


@_first
@effect(r"~ becomes a copy of target (?P<what>.+?)(?P<until> until end of turn)?(?:, except (?P<exc>.+))?")
def _become_copy(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    from app.rules import copying

    found = copying.parse_become(m["what"], bool(m["until"]), m["exc"])
    if found is None:
        raise _NoMatch
    return found


# The tokens a copy creates are what a following "it" / "that token" names ("Sacrifice it at the
# beginning of the next end step."): the resolution records them (effects._remember).
_RECORDING.update({"token_copy": None})
_MOVERS.add("token_copy")
_TOKEN_MAKERS.add("token_copy")
_CHOSEN["token_copy"] = "n"


# -- token copies & attach on entry (wave 5J) -- "attach it to target creature you control" (Embercleave, Sigarda's Aid,
# Hammer of Nazahn: "attach that Equipment to …"): 701.3a-b — the source (or the trigger's object) attached to the
# target if it can be, else it doesn't move (app/rules/attach_entry.py, through effects.attach_self). "it" is resolved by
# resolve_it: this object ("When ~ enters"), or the object the trigger was about ("Whenever an Equipment … enters")
@_first
@effect(r"attach (?:it|that Equipment) to (?P<tgt>(?:up to one )?target [^,.]+)")
def _attach_it(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    from app.rules import attach_entry

    found = attach_entry.parse(m["tgt"])
    if found is None:
        raise _NoMatch
    return found


# -- other side (wave 6D) / if you do (wave 6F) -- "Whenever a creature you control enters, you may attach ~ to it." (Hero's
# Blade), "create a 1/1 … token, then attach ~ to it." (Ancestral Blade, Dwarven Hammer): this object attached to the one
# the pronoun names (701.3a-b, attachments.host_problem: nothing moves if it can't be attached there or either has become
# a new object, 400.7)
@_first
@effect(r"attach ~ to (?:it|that creature)")
def _attach_self_to_it(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    return [{"do": "attach_to", "src": "self", "who": "it"}], None


@_first
@effect(r"populate")
def _populate(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    return [{"do": "populate"}], None  # 701.36 (app/rules/populate.py)


@_first
@effect(r"for each [^,]+, (?:its controller creates|create) (?:a|one) (?:tapped )?token that's a copy of that [a-z]+(?:, except .+)?")
def _for_each_token_copy(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    from app.rules import populate

    inner = populate.FOR_EACH.fullmatch(m.group(0))
    found = populate.parse_for_each(inner) if inner is not None else None
    if found is None:
        raise _NoMatch
    return found


@_first
@effect(r"for each of them, create (?:a|one) (?P<tapped>tapped )?token that's a copy of it")
def _for_each_of_them_copy(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    """"Whenever one or more tokens … enter, for each of them, create a tapped token that's a copy of it." (Kambal):
    one copy of every object of the event ("them": resolve_it binds it to the "one or more" event, 603.2c)."""
    return [{"do": "token_copy", "n": 1, "who": "them", **({"tapped": True} if m["tapped"] else {})}], None


@_first
@effect(r"(?P<may>you may )?put (?:a|an|any number of) [^.]+? from your hand onto the battlefield(?: tapped(?: and attacking)?)?")
def _put_from_hand(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    """"You may put an Equipment card from your hand onto the battlefield." (Stoneforge Mystic): app/rules/put_from_hand.py.
    "You may" after another instruction ("Draw a card. You may put a land card …"): choosing no card."""
    from app.rules import put_from_hand

    inner = re.fullmatch(put_from_hand.PATTERN, m.group(0)[len(m["may"] or ""):])
    found = put_from_hand.parse(inner) if inner is not None else None
    if found is None:
        raise _NoMatch
    if m["may"]:
        found[0][0]["optional"] = True
    return found


from app.rules.put_from_hand import EACH_PATTERN as _put_from_hand_pattern  # noqa: E402  (a leaf module)


@_first
@effect(_put_from_hand_pattern)
def _each_put_from_hand(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    """-- other players' choices (wave 12D) -- "Each opponent may put a creature card from their hand onto the battlefield."
    (app/rules/put_from_hand.py)"""
    from app.rules import put_from_hand

    found = put_from_hand.parse_each(m)
    if found is None:
        raise _NoMatch
    return found


_RECORDING["put_from_hand"] = None  # ("That creature gains haste.": the permanent it put onto the battlefield)
_MOVERS.add("put_from_hand")
# -- end token copies & attach on entry (wave 5J) --


# -- mana (wave 3M): "Add {B}{B}{B}." / "Add one mana of any color." / "Add {R} for each …" as an effect (CR 106.3, 605.1a) --
def _mana_effect(pattern: str):  # type: ignore[no-untyped-def]
    def register(fn):  # type: ignore[no-untyped-def]
        EFFECTS.append((re.compile("^" + pattern + "$"), fn))
        return fn
    return register


_SYM = r"\{[WUBRGC]\}"
_MANA_AMOUNT = r"(?P<n>\d+|a|an|one|two|three|four|five|six|seven|eight|nine|ten|x|X)"


def _mana_n(word: str) -> Any:
    from app.rules import values

    v = values.parse_amount(word)
    if v is None:
        raise _NoMatch
    return v


@_mana_effect(rf"add (?P<m>(?:{_SYM})+)")
def _add_fixed(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    return [{"do": "add_mana", "mana": re.findall(r"\{(.)\}", m["m"])}], None


@_mana_effect(rf"add (?P<m>{_SYM}(?:, {_SYM})*,? or {_SYM})")
def _add_one_of(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    return [{"do": "add_mana", "of": list(dict.fromkeys(re.findall(r"\{(.)\}", m["m"]))), "n": 1}], None


@_mana_effect(r"add one mana of any color")
def _add_any(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    return [{"do": "add_mana", "of": list("WUBRG"), "n": 1}], None


@_mana_effect(r"add one mana of any color in your commander's color identity")
def _add_identity(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    return [{"do": "add_mana", "of": list("WUBRG"), "n": 1, "identity": True}], None


@_mana_effect(rf"add {_MANA_AMOUNT} mana of any one color")
def _add_one_color(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    return [{"do": "add_mana", "of": list("WUBRG"), "n": _mana_n(m["n"]), "same": True}], None


@_mana_effect(rf"add {_MANA_AMOUNT} mana in any combination of colors")
def _add_combination(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    return [{"do": "add_mana", "of": list("WUBRG"), "n": _mana_n(m["n"])}], None


@_mana_effect(rf"add {_MANA_AMOUNT} mana in any combination of (?P<a>{_SYM}) and/or (?P<b>{_SYM})")
def _add_combination_two(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    return [{"do": "add_mana", "of": [m["a"][1], m["b"][1]], "n": _mana_n(m["n"])}], None


# -- if you do (wave 6F) -- "Add {B} or {G} for each permanent destroyed this way." (Culling Ritual), "add {R} or {G} for
# each Raccoon you control" (Muerra): one mana per object counted, each of the two types chosen separately (106.1:
# each mana is chosen on its own; effects.add_mana asks once per mana)
@_mana_effect(rf"add (?P<a>{_SYM}) or (?P<b>{_SYM}) for each (?P<what>[^,.]+)")
def _add_either_counted(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    from app.rules import values

    what = m["what"]
    count = this_way.parse(what) if " this way" in what else values.parse_count(what)
    if count is None or (isinstance(count, dict) and count.get("hand") == "target") or m["a"] == m["b"]:
        raise _NoMatch
    return [{"do": "add_mana", "of": [m["a"][1], m["b"][1]], "n": count}], None


@_mana_effect(rf"add (?:(?P<sym>{_SYM}) for each|an amount of (?P<sym2>{_SYM}) equal to the number of) (?P<what>[^,.]+)")
def _add_counted(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    from app.rules import values

    what = m["what"]
    # -- if you do (wave 6F) -- "Add {B} for each permanent destroyed this way." (Culling Ritual's form): the objects the
    # earlier instruction actually destroyed (app/rules/this_way.py; resolve_it binds it, 608.2h)
    if " this way" in what and m["sym"] and (counted := this_way.parse(what)) is not None:
        return [{"do": "add_mana", "sym": m["sym"][1], "n": counted}], None
    if (what.startswith(("card named", "color ", "different ", "creature that", "permanent ")) or " this way" in what) \
            and not re.fullmatch(r"card named ~ in each graveyard", what):  # (wave 5A: Rite of Flame, values.parse_count)
        raise _NoMatch
    # -- refused copy/mana (wave 3R3) -- Jeska's Will: "Add {R} for each card in target opponent's hand." The player
    # is the instruction's one target (115.1: chosen as it's cast, checked as it resolves, 608.2b); the amount is
    # that player's hand size as it resolves (values: {"hand": "target"})
    hand = re.fullmatch(r"cards? in target (?P<who>player|opponent)'s hand", what)
    if hand is not None:
        return [{"do": "add_mana", "sym": (m["sym"] or m["sym2"])[1], "n": {"hand": "target"}}], hand["who"]
    # -- mana riders (wave 5A) -- Rite of Flame: "add {R} for each card named ~ in each graveyard" (the spell's own name;
    # only in this "add" instruction: values.evaluate {"named_self_in_graveyards": 1})
    count = {"named_self_in_graveyards": 1} if what == "card named ~ in each graveyard" else values.parse_count(what)
    if count is None:
        raise _NoMatch
    if isinstance(count, dict) and count.get("hand") == "target":
        raise _NoMatch  # ("cards in target opponent's hand": a player amount the pronoun binder can't carry yet: manual)
    return [{"do": "add_mana", "sym": (m["sym"] or m["sym2"])[1], "n": count}], None


# -- ability words (wave 9C) -- opus: "add an amount of {R} equal to this creature's power" (Molten-Core Maestro): the source's
# power as the instruction is carried out (a triggered ability that adds mana still uses the stack: 605.1b)
@_mana_effect(rf"add an amount of (?P<sym>{_SYM}) equal to (?:this creature|~)'s power")
def _add_own_power(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    return [{"do": "add_mana", "sym": m["sym"][1], "n": {"power": "self"}}], None


# -- amounts (wave 12C) -- Sacrifice: "Add an amount of {B} equal to the sacrificed creature's mana value": what the spell's
# additional cost sacrificed, as it last existed (608.2h; define() checks the cost sacrificed exactly one object)
@_mana_effect(rf"add an amount of (?P<sym>{_SYM}) equal to the sacrificed (?:creature|artifact|permanent|land|enchantment)'s mana value")
def _add_sacrificed_mv(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    return [{"do": "add_mana", "sym": m["sym"][1], "n": {"mana_value": "cost:sacrificed"}}], None


# -- stack interaction (wave 5B) -- Mana Drain: "… add an amount of {C} equal to that spell's mana value": the spell an
# earlier instruction countered, as it last existed on the stack (608.2h; its X counts, 202.3e). resolve_it binds
# "that spell" to that instruction's record; with nothing to bind it to, the line stays manual.
@_mana_effect(rf"add an amount of (?P<sym>{_SYM}) equal to that spell's mana value")
def _add_spell_mv(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    return [{"do": "add_mana", "sym": m["sym"][1], "n": {"mana_value": "that_spell"}}], None
# -- end stack interaction (wave 5B) --


# -- reanimation (wave 3R) --  "return a creature card from your graveyard …": chosen on resolution; what it
# returned is what "that card" / "it" names afterwards (400.7j).
_RECORDING["return_choice"] = "returned"
_MOVERS.add("return_choice")
_CHOSEN["return_choice"] = "n"


# -- control (wave 3K) -- "Gain control of target creature until end of turn. Untap that creature. It gains haste
# until end of turn." The control-changing effect (layer 2, 613.1b) names its objects: a following "it" / "that
# creature" is the target, as after any plain target (app/rules/language.py "control", app/rules/effects.py).
_RECORDING.update({"gain_control": None, "exchange_control": None})


@_first
@effect(r"(?P<t>(?!.* (?:for as long as|until your next turn)\b)(?:(?:untap .+? and )?(?:you )?gain control of .+|.+? gains control of .+|exchange control of .+))")
def _control(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    from app.rules import language

    return _from_language(language.control_forms(m["t"]))
# -- counters & designations (wave 3E) -- Palace Jailer: "exile target creature an opponent controls until an
# opponent becomes the monarch" — a delayed trigger (603.7) watching for a player who is an opponent of the
# ability's controller to become the monarch (725.3; app/rules/designations.py), however long that takes and
# whether or not the source is still there; the exiled card returns under its owner's control.
@effect(r"exile (?P<o>target .+?) until an opponent becomes the monarch")
def _exile_until_monarch(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    found = _one_clause(f"exile {m['o']}")
    if found is None or len(found[0]) != 1 or found[0][0]["do"] != "exile" or found[0][0]["who"] != "target":
        raise _NoMatch
    back = {"do": "return_card", "who": "ref:m0", "to": "battlefield", "tapped": False, "under": "owner"}
    return [{**found[0][0], "as": "m0"}, *_delayed.wrap_when([back], {"kind": "designation", "what": "monarch", "by": "opponent"})], found[1]
# -- end counters & designations (wave 3E) --


# -- keyword actions & face-down (wave 3F) -- goad names its objects ("goad it" after a target, "tap it and goad
# it"); manifest / cloak put cards onto the battlefield ("then put X +1/+1 counters on it": the face-down
# permanent it made, app/rules/facedown.py binds it)
_RECORDING.update({"goad": None, "manifest": None, "detain": None, "suspect": None, "exile_hand_down": "exiled"})  # (detain, suspect: wave 12A; exile_hand_down: 18A)
_MOVERS.update({"manifest", "exile_hand_down"})  # (exile_hand_down: wave 18A)
_CHOSEN.update({"manifest": "n", "exile_hand_down": "n"})


# -- refused grants/replacements (wave 3R2) -- source-of-your-choice shields (609.7, 615.8) and "Damage can't be
# prevented this turn." (615.12): app/rules/source_shields.py. Tried first: the generic "prevent all damage that would
# be dealt …" template refuses (rather than declines) the "source of your choice" wording.
from app.rules import cant_gain as _cant_gain  # noqa: E402
from app.rules import graveyard_grants as _graveyard_grants  # noqa: E402
from app.rules import skips as _skips  # noqa: E402
from app.rules import source_shields as _source_shields  # noqa: E402

# (and 614.10 skips: app/rules/skips.py; 614.17 "can't gain life": app/rules/cant_gain.py; flashback and "you may play
# this card" granted to graveyard cards: app/rules/graveyard_grants.py)
EFFECTS[:0] = [*_source_shields.TEMPLATES, *_skips.TEMPLATES, *_cant_gain.TEMPLATES, *_graveyard_grants.TEMPLATES]
from app.rules import hand_size as _hand_size  # noqa: E402  -- ability words (wave 20C) --

EFFECTS[:0] = _hand_size.TEMPLATES  # "You have no maximum hand size for the rest of the game."
# -- next untap step (wave 6A) -- "… doesn't untap during its controller's next untap step" (app/rules/next_untap.py)
from app.rules import next_untap as _next_untap  # noqa: E402

EFFECTS[:0] = _next_untap.TEMPLATES
# -- extra turns (wave 8A) -- "Take an extra turn after this one." (app/rules/extra_turns.py)
from app.rules import extra_turns as _extra_turns  # noqa: E402

EFFECTS[:0] = _extra_turns.TEMPLATES
# -- controlling another player (wave 18H) -- "You control target player during that player's next turn." (app/rules/player_control.py)
from app.rules import player_control as _player_control  # noqa: E402

EFFECTS[:0] = _player_control.TEMPLATES
# -- untap choice (wave 7F) -- "… doesn't untap during its controller's untap step for as long as ~ remains tapped"
from app.rules import untap_choice as _untap_choice  # noqa: E402

EFFECTS[:0] = _untap_choice.TEMPLATES
# -- bounce forms (wave 6A) -- "Return a permanent you control to its owner's hand." … (app/rules/bounce_forms.py):
# after the older literal templates ("return a land you control …": effects.return_yours)
from app.rules import bounce_forms as _bounce_forms  # noqa: E402

EFFECTS.extend(_bounce_forms.TEMPLATES)
# -- turn grants (wave 6A) -- "can't be blocked by Walls this turn", one subject for two grants (app/rules/turn_grants.py)
from app.rules import turn_grants as _turn_grants  # noqa: E402

EFFECTS[:0] = _turn_grants.TEMPLATES
_RECORDING["bounce_together"] = "returned"
_MOVERS.add("bounce_together")
from app.rules import graveyard_exile as _graveyard_exile  # noqa: E402, I001  -- graveyard exile (wave 4J) --

EFFECTS[:0] = _graveyard_exile.TEMPLATES  # "Exile target player's graveyard." (app/rules/graveyard_exile.py)
from app.rules import tap_mana as _tap_mana  # noqa: E402, I001  -- mana riders (wave 5A) --

EFFECTS[:0] = _tap_mana.TEMPLATES  # "Until end of turn, whenever a player taps an Island for mana, …" (High Tide)
from app.rules import untap_riders as _untap_riders  # noqa: E402, I001

EFFECTS[:0] = _untap_riders.TEMPLATES  # "Untap up to three lands." (app/rules/untap_riders.py)
# -- cast limits (wave 5E) -- "Your opponents can't cast spells this turn." / "You may cast spells this turn as though they
# had flash." (app/rules/cast_limits.py)
from app.rules import cast_limits as _cast_limits  # noqa: E402, I001

EFFECTS[:0] = _cast_limits.TEMPLATES
# -- end cast limits (wave 5E) --
# "Choose one of them." chooses among what the instruction before moved; "that card" is then the chosen one
_RECORDING["choose_one_of"] = None
_MOVERS.add("choose_one_of")
_CHOSEN["choose_one_of"] = "n"
# -- end refused grants/replacements (wave 3R2) --


# -- refused copy/mana (wave 3R3) -- 106.4 / 500.4: "Until end of turn, you don't lose this mana as steps and phases
# end." (after an "add" instruction of the same ability: the mana it added, app/rules/kept_mana.py); "Until end of
# combat, you don't lose this mana as steps end." (511.3: kept to the end of the end of combat step)
@_first
@effect(r"until end of (?P<u>turn|combat), you don't lose this mana as steps(?: and phases)? end")
def _keep_mana(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    return [{"do": "keep_mana", "until": "end_of_turn" if m["u"] == "turn" else "end_of_combat"}], None


# -- mana provenance (wave 18B) -- "Spend this mana only to cast artifact or creature spells." / "This mana can't be spent to cast
# nonartifact spells." after an "add" instruction: the mana it added is restricted (106.6; app/rules/mana_units.py)
@_first
@effect(r"(?P<s>spend this mana only .+|this mana can't be spent .+)")
def _restrict_mana(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    from app.rules import mana as mana_

    only = mana_.spend_kind(m["s"][:1].upper() + m["s"][1:])
    if only is None:
        raise _NoMatch
    return [{"do": "restrict_mana", "only": only, "note": m["s"][:1].upper() + m["s"][1:] + "."}], None


# "Add six {R}" / "add eight {C}" / "add that much {G}" (the trigger event's amount, 608.2k): n of one type
@_mana_effect(r"add (?P<n>two|three|four|five|six|seven|eight|nine|ten|that much) (?P<sym>\{[WUBRGC]\})")
def _add_n_of(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    return [{"do": "add_mana", "sym": m["sym"][1], "n": _mana_n(m["n"])}], None


# -- other players' choices (wave 12D) -- "That player adds {G}{G}." (Eladamri's Vineyard), "Target player adds one mana of any
# color." (The Warring Triad): 106.3-106.4, the mana goes into that player's pool and any choice in it (a color) is theirs.
# ("Each player adds {B}{R}{G}." (Yurlok) is a mana ability with no target, 605.1a: not read.)
@effect(r"(?P<who>that player|target player|target opponent) adds (?P<rest>.+)")
def _other_adds(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    found = _one_clause("add " + m["rest"])
    if found is None or found[1] is not None or len(found[0]) != 1 or found[0][0].get("do") != "add_mana":
        raise _NoMatch
    target = m["who"].startswith("target")
    return [{**found[0][0], "who": "target" if target else "that_player"}], SELECTORS[m["who"]] if target else None


# "Whenever you cast …, copy that spell [, except …]. You may choose new targets for the copy." / "…, copy it." (707.10):
# the trigger event's spell (603.2, 601.2i), while it is still that object on the stack (400.7). Only in a cast
# trigger (``_event_spell_ok``); "copy it" only as the ability's first instruction (an "it" after another instruction
# names that instruction's object, never guessed).
@_first
@effect(r"copy (?P<w>that spell|it)(?: (?P<k>twice|three times|[xX] times))?(?:, except (?P<exc>.+))?")  # (k: wave 7D)
def _copy_event_spell(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    from app.rules import copying

    ex = copying.parse_excepts(m["exc"])
    if ex is None:
        raise _NoMatch
    out: dict[str, Any] = {"do": "copy_spell", "who": "event_spell", **copying._dump(ex)}
    if m["k"]:
        out["n"] = {"twice": 2, "three times": 3, "x times": {"x": 1}}[m["k"].lower()]
    if m["w"] == "it":
        out["first"] = True
    return [out], None


# -- copied abilities (wave 18F) -- "Whenever you activate an ability of an artifact, … copy that ability." (Kurkesh, 707.10): the
# activated ability the trigger's event is about (``_event_spell_ok``: only in an activation trigger)
@_first
@effect(r"copy that ability")
def _copy_event_ability(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    return [{"do": "copy_ability", "who": "event_ability"}], None


# -- copied for each (wave 18F) -- 707.10d: "Copy that spell for each other creature you control that the spell could target. Each copy
# targets a different one of those creatures." (Zada, Hedron Grinder; Mirrorwing Dragon's "that player copies …": the caster)
@_first
@effect(r"(?:(?P<you>copy that spell for each other creature you control)|(?P<they>that player copies that spell for each other "
        r"creature they control)) that the spell could target")
def _copy_each_target(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    return [{"do": "copy_each", "who": "event_spell", "by": "you" if m["you"] else "event_player"}], None


@_first
@effect(r"each copy targets a different one of those creatures")
def _copy_each_marker(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    return [{"do": "copy_each_marker"}], None  # (707.10d: read by the copy instruction before it, ``_event_spell_ok``)


# -- cast a copy (wave 13C) -- "Copy that card [three times]." / "Copy those cards." (707.12): copies of the card(s) an
# earlier instruction exiled, made in exile (copying.copy_cards) for "You may cast the copy without paying its mana cost"
# ("copy it" is read above as a cast trigger's spell; resolve_it turns it into this after a moved card).
@effect(r"(?P<w>~|it) becomes prepared")
def _becomes_prepared(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    """-- prepared (wave 13C) -- "This creature becomes prepared." (722.3a, keyword_actions.prepare)."""
    return [{"do": "prepare", "who": "self" if m["w"] == "~" else "it"}], None


@_first
@effect(r"copy (?P<w>that card|those cards|them)(?: (?P<k>twice|three times))?")
def _copy_cards(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    out: dict[str, Any] = {"do": "copy_cards", "who": ("it:card" if m["w"] == "that card" else "them:card")}
    if m["k"]:
        out["n"] = {"twice": 2, "three times": 3}[m["k"]]
    return [out], None


@_first
@effect(r"(?P<ex>exile [^,]+?) and copy it")
def _exile_and_copy(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    """"Exile up to one target instant or sorcery card from your graveyard and copy it." (Renegade Bull): the exile
    instruction, then the copy of the card it exiled (707.12; the exile may be replaced: then nothing is copied)."""
    found = _one_clause(m["ex"])
    if found is None or len(found[0]) != 1 or found[0][0].get("do") != "exile":
        raise _NoMatch
    return [found[0][0], {"do": "copy_cards", "who": "it:card"}], found[1]


@_first
@effect(r"copy it, then (?P<cast>you may cast the copy without paying its mana cost)")
def _copy_then_cast(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    from app.rules import permissions

    found = permissions.parse_clause(m["cast"])
    if found is None:
        raise _NoMatch
    return [{"do": "copy_cards", "who": "it:card"}, *found[0]], found[1]


_RECORDING["copy_cards"] = "copy"
_MOVERS.add("copy_cards")
_CHOSEN["copy_cards"] = "n"


# -- if you do (wave 5G) -- "Whenever a player casts a spell, if no mana was spent to cast it, counter that spell."
# (Vexing Bauble, Boromir): the trigger event's spell (701.6a), while it is still that object on the stack (400.7;
# effects.counter); only in a cast trigger (``_event_spell_ok``).
@effect(r"counter that spell")
def _counter_event_spell(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    return [{"do": "counter", "who": "event_spell"}], None


def _event_spell_ok(d: Definition) -> bool:
    """A copy of "that spell" belongs to a trigger on casting a spell (603.2: the event names it)."""
    effects = list(d.get("effects") or [])
    for k, e in enumerate(effects):  # -- copied for each (wave 18F) -- the instruction and its "Each copy targets …" sentence go together
        nxt = effects[k + 1].get("do") if k + 1 < len(effects) else None
        if (e.get("do") == "copy_each" and nxt != "copy_each_marker") or (
                e.get("do") == "copy_each_marker" and (not k or effects[k - 1].get("do") != "copy_each")):
            return False
    if any(e.get("who") == "event_ability" for e in effects):  # -- copied abilities (wave 18F) -- the ability an activation trigger is about
        cond = d.get("cond") if d.get("kind") == "triggered" and d.get("trigger") == "event" else None
        return cond is not None and cond.get("event") == "activate" and cond.get("subject") == "player" and not cond.get("loyalty")
    from app.rules import watches  # -- turn watches (wave 7D) --

    watched = watches.deferred_event_effects(effects)
    uses = [k for k, e in enumerate(effects) if e.get("who") == "event_spell" and k not in watched]
    if not uses:
        return True
    cond = d.get("cond") if d.get("kind") == "triggered" and d.get("trigger") == "event" else None
    if cond is None or cond.get("event") != "cast" or cond.get("subject") != "player" or cond.get("copy"):
        return False
    lead = [e for e in effects if e.get("do") != "only_if"]
    return all(not effects[k].get("first") or (lead and lead[0] is effects[k]) for k in uses)
# -- end refused copy/mana (wave 3R3) --


# -- triggers (wave 5D) -------------------------------------------------------------------------------------------
# "create a 3/3 colorless Phyrexian Wurm artifact creature token with deathtouch and a 3/3 colorless Phyrexian Wurm
# artifact creature token with lifelink" (Wurmcoil Engine), "create A, B, and C" (Triplicate Titan): one instruction
# creating several kinds of token (701.7a), carried out as one create_token effect (effects.create_token's "more").
# Each kind must read on its own as a plain "create …" with a fixed number; anything else stays manual.
_TOKEN_LIST_SPLIT = re.compile(r"(?:, and |, | and )(?=an? [^,]*?\btokens?\b)")


@effect(r"create (?P<list>(?=[^\"]*$)an? [^.]*?\btokens?\b[^.]*?(?:, and |, | and )an? [^.]*?\btokens?\b[^.]*)")
def _create_several_kinds(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    pieces = _TOKEN_LIST_SPLIT.split(m["list"])
    made: list[dict[str, Any]] = []
    for piece in pieces:
        found = _one_clause("create " + piece)
        if found is None or found[1] is not None or len(found[0]) != 1:
            raise _NoMatch
        e = found[0][0]
        if e.get("do") != "create_token" or e.get("who") != "you" or not isinstance(e.get("n"), int) \
                or set(e) - {"do", "who", "n", "token", "tapped"}:
            raise _NoMatch
        made.append(e)
    if len(made) < 2:
        raise _NoMatch
    first, *rest = made
    return [{**first, "more": [{k: v for k, v in e.items() if k in ("token", "n", "tapped")} for e in rest]}], None


EFFECTS[:0] = [EFFECTS.pop()]  # (before the one-kind templates, which would read "with deathtouch and a 3/3 …" as keywords)


@effect(r"create that many (?P<rest>[^\"]+ tokens?(?: with [^\"]+)?)")
def _create_that_many(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    """"Whenever a creature you control deals combat damage to a player, create that many Treasure tokens." (Old
    Gnawbone): as many as the trigger event's amount (608.2k; scripts._event_refs_ok: only an event with an amount)."""
    found = _one_clause("create two " + m["rest"])
    if found is None or found[1] is not None or len(found[0]) != 1 or found[0][0].get("do") != "create_token" \
            or found[0][0].get("n") != 2:
        raise _NoMatch
    return [{**found[0][0], "n": {"event_amount": 1}}], None
# -- end triggers (wave 5D) --

# -- stack interaction (wave 5B) -- "Change the target of target spell with a single target." / "Change a target of
# target spell or ability to this creature." (115.7): app/rules/stack_interaction.py
from app.rules import stack_interaction as _stack_interaction  # noqa: E402, I001

EFFECTS[:0] = _stack_interaction.TEMPLATES
# -- end stack interaction (wave 5B) --

# -- turn grants (wave 6A) -- one subject for two grants ("… gains vigilance until end of turn and can't be blocked this
# turn"): after every other template (it defers to the generic grammar first: app/rules/turn_grants.py)
EFFECTS.extend(_turn_grants.LAST)
# -- attach abilities (wave 7E) -- "Attach this Equipment to target creature you control." (app/rules/attach_abilities.py)
from app.rules import attach_abilities as _attach_abilities  # noqa: E402

EFFECTS[:0] = _attach_abilities.TEMPLATES
# -- tap or untap (wave 6D) -- "You may tap or untap target permanent." (app/rules/tap_or_untap.py)
from app.rules import tap_or_untap as _tap_or_untap  # noqa: E402

EFFECTS[:0] = _tap_or_untap.TEMPLATES
# -- exiled with (wave 6D) -- "return the exiled card to the battlefield under its owner's control" (607.2a)
from app.rules import exiled_with as _exiled_with  # noqa: E402

EFFECTS[:0] = _exiled_with.TEMPLATES
# -- endure (wave 6D) -- "it endures 2" (701.63: app/rules/endure.py)
from app.rules import endure as _endure  # noqa: E402

EFFECTS[:0] = _endure.TEMPLATES
# -- win the game (wave 6D) -- "you win the game" (104.2b: app/rules/win_game.py)
from app.rules import win_game as _win_game  # noqa: E402

EFFECTS[:0] = _win_game.TEMPLATES
# -- activation wordings (wave 7B) -- "Adapt N." (app/rules/activation_words.py)
from app.rules import activation_words as _activation_words  # noqa: E402, I001

EFFECTS[:0] = _activation_words.TEMPLATES
# -- choice grants and switches (wave 7E) -- "gains your choice of …", "gets +1/-1 or -1/+1", "Switch … power and toughness",
# "Regenerate target Elf" (app/rules/choice_grants.py)
from app.rules import choice_grants as _choice_grants  # noqa: E402, I001

EFFECTS[:0] = _choice_grants.TEMPLATES
# -- coin flips (wave 7E) -- "Flip a coin." (app/rules/coin_flips.py; the conditions are in conditions.py)
from app.rules import voting as _voting_templates  # noqa: E402, I001  -- voting (wave 18C) --
from app.rules import coin_flips as _coin_flips  # noqa: E402, I001

EFFECTS[:0] = _coin_flips.TEMPLATES
EFFECTS[:0] = _voting_templates.TEMPLATES
# -- clash (wave 12A) -- "Clash with an opponent." (701.30: app/rules/clash.py)
from app.rules import clash as _clash  # noqa: E402, I001

EFFECTS[:0] = _clash.TEMPLATES
# -- rolling dice (wave 12A) -- "Roll a d20." (706: app/rules/dice.py)
from app.rules import dice as _dice  # noqa: E402, I001

EFFECTS[:0] = _dice.TEMPLATES
# -- block effects (wave 7E) -- "Target creature can't block this creature this turn." (app/rules/block_effects.py)
from app.rules import block_effects as _block_effects  # noqa: E402, I001

EFFECTS[:0] = _block_effects.TEMPLATES
# -- discover (wave 9A) -- "Discover 4." / "discover X, where X is …" (701.57: app/rules/discover.py)
from app.rules import discover as _discover  # noqa: E402, I001

EFFECTS[:0] = _discover.TEMPLATES
# -- X actions (wave 9A) -- "bolster X, where X is …", "amass Orcs X, where X is …" (app/rules/x_actions.py)
from app.rules import x_actions as _x_actions  # noqa: E402, I001

EFFECTS[:0] = _x_actions.templates(_SEL)

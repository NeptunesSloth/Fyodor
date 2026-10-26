"""Triggered keyword abilities read through their Comprehensive Rules definition (wave 6E).

A triggered keyword means a sentence the rules spell out (702.1); where the engine's trigger grammar already reads that
sentence, the keyword is carried out as it: battle cry (702.91a: "Whenever this creature attacks, each other attacking
creature gets +1/+0 until end of turn."), ingest (702.115a: "Whenever this creature deals combat damage to a player, that
player exiles the top card of their library."), poisonous N (702.70a), frenzy N (702.68a), afterlife N (702.135a). Each instance triggers
separately (702.91b, 702.115b, 702.70b, 702.68b): one definition per keyword piece of a line.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from typing import Any

from app.rules import hideaway, pairing
from app.rules.oracle import AbilityText

# keyword → its meaning (CR 2026-09-25), "{n}" standing for the keyword's number
MEANINGS: dict[str, str] = {
    "battle cry": "Whenever this creature attacks, each other attacking creature gets +1/+0 until end of turn.",  # 702.91a
    "ingest": "Whenever this creature deals combat damage to a player, that player exiles the top card of their library.",  # 702.115a
    "poisonous": "Whenever this creature deals combat damage to a player, that player gets {n} poison counters.",  # 702.70a
    "frenzy": "Whenever this creature attacks and isn't blocked, it gets +{n}/+0 until end of turn.",  # 702.68a
    # 702.101a ("you gain life equal to the total life lost this way": the grammar's "the life lost this way" is that
    # total, 119.3 — effects.lose_life binds what was actually lost)
    "extort": "Whenever you cast a spell, you may pay {{W/B}}. If you do, each opponent loses 1 life and you gain life equal "
              "to the life lost this way.",
    # 702.135a
    "afterlife": "When this permanent is put into a graveyard from the battlefield, create {n} 1/1 white and black Spirit "
                 "creature tokens with flying.",
    # -- keyword pieces (wave 8A) -- 702.43a: the triggered half of modular N (the static half, "enters with N +1/+1
    # counters", is replacements.entering_counters). The counters are those the permanent had as it left (113.6, LKI)
    "modular": "When this permanent is put into a graveyard from the battlefield, you may put a +1/+1 counter on target "
               "artifact creature for each +1/+1 counter on this permanent.",
    # -- keyword mechanics (wave 9D) -- 702.58a: the triggered half of graft N (the static half, "enters with N +1/+1 counters",
    # is replacements.entering_counters). 122.5: if either object has left the battlefield nothing is moved.
    "graft": "Whenever another creature enters, if this creature has a +1/+1 counter on it, you may move a +1/+1 counter "
             "from this creature onto that creature.",
    # -- keyword meanings (wave 11B) --
    "living weapon": "When this Equipment enters, create a 0/0 black Phyrexian Germ creature token, then attach this "
                     "Equipment to it.",  # 702.92a
    "for mirrodin!": "When this Equipment enters, create a 2/2 red Rebel creature token, then attach this Equipment to it.",  # 702.163a
    "haunt": "When this creature dies, exile it haunting target creature.",  # -- keywords (wave 50H) -- 702.55a (a permanent's: app/rules/haunt.py)
    "job select": "When this Equipment enters, create a 1/1 colorless Hero creature token, then attach this Equipment to it.",  # -- keywords (wave 50H) -- 702.182a
    "annihilator": "Whenever this creature attacks, defending player sacrifices {n} permanents.",  # 702.86a
    "afflict": "Whenever this creature becomes blocked, defending player loses {n} life.",  # 702.130a
    # 702.156a: the triggered half of ravenous (its "enters with X +1/+1 counters" half is replacements.entering_counters;
    # X is 0 when it isn't cast, 107.3m)
    "ravenous": "When this permanent enters, if X is 5 or more, draw a card.",
    # -- static_other sweep (wave 16B) -- 702.190a: the mana spent is read from the cast spell's payment record (conditions._total_mana_spent)
    "increment": "Whenever you cast a spell, if the amount of mana you spent is greater than this creature's power or toughness, put a "
                 "+1/+1 counter on this creature.",
    # -- keywords (wave 15E) --
    "training": "Whenever this creature and at least one other creature with power greater than this creature's power attack, "
                "put a +1/+1 counter on this creature.",  # 702.149a
    "dethrone": "Whenever this creature attacks the player with the most life or tied for most life, put a +1/+1 counter on "
                "this creature.",  # 702.105a
    "evolve": "Whenever a creature you control enters, if that creature's power is greater than this creature's power and/or "
              "that creature's toughness is greater than this creature's toughness, put a +1/+1 counter on this creature.",  # 702.100a
    # 702.181a ("those tokens enter tapped and attacking" written as the grammar reads it; "a" for one, {w} the number word)
    "mobilize": "Whenever this creature attacks, create {w} 1/1 red Warrior creature token{s} that{be} tapped and attacking. "
                "Sacrifice {them} at the beginning of the next end step.",
    # 702.63a vanishing N: enters with N time counters (replacements.entering_counters), and these two
    "vanishing": "At the beginning of your upkeep, if this permanent has a time counter on it, remove a time counter from it.\n"
                 "When the last time counter is removed from this permanent, sacrifice this permanent.",
    # 702.32a fading N: enters with N fade counters (replacements.entering_counters), and this
    "fading": "At the beginning of your upkeep, remove a fade counter from this permanent. If you can't, sacrifice this "
              "permanent.",
    # 702.116a (written as combat_rules.clause reads it: "~" for this creature)
    "myriad": "Whenever this creature attacks, for each opponent other than defending player, you may create a token that's a copy "
              "of this creature that's tapped and attacking that player or a planeswalker they control. If one or more tokens are "
              "created this way, exile the tokens at end of combat.",
    "rampage": "Whenever this creature becomes blocked, it gets +{n}/+{n} until end of turn for each creature blocking it beyond "
               "the first.",  # 702.23a
    # 702.157a squad (the count: how many times its cost was paid, as kicker's: values.kicked_count)
    "squad": "When this creature enters, create a token that's a copy of it for each time it was kicked.",
    # 702.175a offspring: "if its offspring cost was paid" is "if it was kicked"
    "offspring": "When this creature enters, if it was kicked, create a token that's a copy of it, except it's 1/1.",
    "mentor": "Whenever this creature attacks, put a +1/+1 counter on target attacking creature with power less than this "
              "creature's power.",  # 702.134a
    # -- casting extras (wave 18E) -- 702.121a melee (values.parse_count: the opponents attacked directly, 506.3)
    "melee": "Whenever this creature attacks, it gets +1/+1 until end of turn for each opponent you attacked with a creature this combat.",
    # 702.39a provoke: "you may choose to have target creature … block … If you do, untap that creature" — the whole of it is the "may"
    # (``_OPTIONAL``); the requirement ends with this combat (block_effects: a turn may have several combats, 500.8)
    "provoke": "Whenever this creature attacks, target creature defending player controls blocks this creature this combat if able. "
               "Untap that creature.",
    # 702.59a recover [cost]: a triggered ability that functions in a graveyard (the effects' "~ from your graveyard", scripts.define);
    # "Otherwise" is "If you don't"; a mana cost only ({cost})
    "recover": "Whenever a creature is put into your graveyard from the battlefield, you may pay {cost}. If you do, return ~ from your "
               "graveyard to your hand. If you don't, exile ~.",
    # -- keyword triggers (wave 23D) -- 702.110a exploit ("you may sacrifice a creature" is the exploit: effects.sacrifice_choice ``exploit``)
    "exploit": "When this creature enters, you may sacrifice a creature.",
    "soulbond": pairing.MEANING,  # -- soulbond (wave 24B) -- 702.95a: two triggered abilities (app/rules/pairing.py)
    "hideaway": hideaway.MEANING,  # -- hideaway (wave 29D) -- 702.75a (app/rules/hideaway.py)
}
_OPTIONAL = frozenset({"provoke"})  # (the controller may choose not to do it, when it resolves)
_COSTED = frozenset({"squad", "offspring"})  # keywords written with a cost (paid as kicker is: costs.kicker_cost)
_NUMBERED = frozenset({"poisonous", "frenzy", "afterlife", "modular", "graft", "annihilator", "afflict", "mobilize", "vanishing", "fading", "backup", "rampage", "hideaway"})


def modular_sunburst(line: str) -> bool:
    from app.rules.oracle import strip_reminders

    return strip_reminders(line).strip().rstrip(".").lower() == "modular—sunburst"


def _squad_mixed(line: str) -> bool:
    from app.rules import costs

    return costs.kicker_mixed_parts(re.sub(r"\s*\(.*?\)", "", line).strip()) is not None


def pieces(kw: str, line: str) -> list[str]:
    """The pieces of a keyword line that are this keyword ("Flying, battle cry" → ["battle cry"])."""
    if kw == "modular" and modular_sunburst(line):
        # Its triggered half is ordinary modular; entry computes the variable
        # count separately from mana colors (702.44c), rather than this zero.
        return ["modular 0"]
    if kw == "squad" and _squad_mixed(line):  # -- squad (wave 110E) -- "Squad—{1}, Discard a card." is one keyword (its cost has a comma)
        return [kw]
    out = []
    for p in re.split(r"[,;]\s*", re.sub(r"\s*\(.*?\)", "", line).strip().rstrip(".")):
        p = p.strip().lower()
        if p == kw or (kw in _NUMBERED and re.fullmatch(rf"{re.escape(kw)} \d+", p)) or kw == "recover" and re.fullmatch(r"recover (?:\{[^}x]+\})+", p):
            out.append(p)
        elif kw in _COSTED and re.fullmatch(rf"{re.escape(kw)} (?:\{{[^}}]+\}})+|{re.escape(kw)}—[^{{}}]+", p):  # (wave 15E) "squad {1}{g}": the keyword (wave 43D: "squad—exile four cards from your graveyard")
            out.append(kw)
    return out


@lru_cache(maxsize=256)
def _definition(piece: str) -> str | None:
    """The definitions of one keyword piece as JSON: a list, one per ability the keyword is ("\n" in its meaning: vanishing is
    two triggered abilities, 702.63a)."""
    from app.rules import scripts  # (scripts imports this module)
    from app.rules.characteristics import Characteristics

    kw, _, n = piece.rpartition(" ") if piece.split(" ")[-1].isdigit() else (piece, "", "")
    cost = ""
    if piece.startswith("recover "):  # -- casting extras (wave 18E) -- 702.59a
        kw, cost = "recover", piece[len("recover "):].upper()
    meaning = MEANINGS.get(kw)
    if meaning is None or ((kw in _NUMBERED) != bool(n) and not (kw == "vanishing" and not n)):  # (-- keywords (wave 50H) -- 702.63b: "Vanishing" without a number is the two triggers only)
        return None
    one = n == "1"
    word = "a" if one else {"2": "two", "3": "three", "4": "four", "5": "five"}.get(n, n)
    out = []
    for text in meaning.format(n=n, w=word, s="" if one else "s", be="'s" if one else " are", cost=cost,
                               them="it" if one else "them").split("\n"):
        ab = AbilityText(index=0, text=text, kind="triggered")
        d = scripts.define(ab, Characteristics(name="\u0000", abilities=(ab,), types=frozenset({"Creature"})))
        if d is None or d.get("kind") != "triggered" or not scripts._event_refs_ok(d):
            return None
        if kw == 'evolve':
            d = {**d, 'effects': [{'do': 'evolve_outcome', 'stage': 'mark'}, *d['effects'], {'do': 'evolve_outcome', 'stage': 'finish'}]}
        if kw == "training":  # -- trains (wave 110G) -- 702.149c: "trains" = the resolving training ability put counters on it
            d = {**d, 'effects': [{'do': 'evolve_outcome', 'stage': 'mark'}, *d['effects'], {'do': 'evolve_outcome', 'stage': 'finish', 'event': 'trained'}]}
        if kw == "modular":  # -- (wave 110O) -- 702.43a: "a modular triggered ability" (Zabaz): its counters are tagged so a replacement can tell (replace.put_counters)
            d = {**d, "effects": [{**x, "modular110o": True} for x in d["effects"]]}
        if kw == "exploit":  # (702.110b: the sacrifice is what "exploits a creature")
            d = {**d, "effects": [{**x, "exploit": True} for x in d["effects"]]}
        if kw == "hideaway":  # -- hideaway (wave 29D) -- 607.2a: the card exiled is the one the permanent's other abilities call "the exiled card"
            d = hideaway.link(d)
            if d is None:
                return None
        out.append({**d, "optional": True} if kw in _OPTIONAL else {**d, "gy_watch": True} if kw == "recover" else d)
    return json.dumps(out)


def definitions(kw: str, line: str) -> list[dict[str, Any]]:
    """The triggered abilities this keyword gives the line (every ability of each instance), or [] when not read."""
    out: list[dict[str, Any]] = []
    for piece in pieces(kw, line):
        found = _definition(piece)
        if found is None:
            return []
        out += json.loads(found)
    return out


def first_piece(kw: str, line: str, nth: int = 0) -> list[dict[str, Any]]:
    """The abilities of the ``nth`` instance of the keyword on the line (each instance is its own keyword ability)."""
    found = [_definition(p) for p in pieces(kw, line)[nth:nth + 1]]
    return json.loads(found[0]) if found and found[0] is not None else []


def supported(kw: str, line: str) -> bool:
    return kw in MEANINGS and bool(definitions(kw, line))


# -- keyword pieces (wave 8A) -- 702.124j: "Partner with [name]" is the commander pairing (app/rules/commander.py) and
# "When this permanent enters, target player may search their library for a card named [name], reveal it, put it into
# their hand, then shuffle."
_PARTNER_WITH = re.compile(r"partner with (?P<name>[^,.;()]+(?:, [^,.;()]+)?)", re.IGNORECASE)


def partner_with_name(line: str) -> str | None:
    m = _PARTNER_WITH.fullmatch(re.sub(r"\s*\(.*?\)", "", line).strip().rstrip("."))
    return m["name"].strip() if m else None


def partner_with_definition(line: str) -> dict[str, Any] | None:
    name = partner_with_name(line)
    if name is None:
        return None
    from app.rules import scripts
    from app.rules.characteristics import Characteristics

    text = f"Search your library for a card named {name}, reveal it, put it into your hand, then shuffle."
    ab = AbilityText(index=0, text=text, kind="spell")
    d = scripts.define(ab, Characteristics(name="\u0000", abilities=(ab,), types=frozenset({"Instant"})))
    if d is None or len(d.get("effects") or []) != 1 or d["effects"][0].get("do") != "search":
        return None
    return {"kind": "triggered", "trigger": "enters_self", "optional": False, "target": {"what": "player"},
            "effects": [{**d["effects"][0], "who": "target", "may": True}]}


# -- keywords (wave 15E) -- backup N (702.165a): "When this creature enters, put N +1/+1 counters on target creature. If that's
# another creature, it gains the following abilities until end of turn." The abilities are those written below the keyword
# on the card (keyword pieces and quoted abilities); each instance triggers separately (702.165b).
_COUNT_WORDS = {1: "a", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight", 9: "nine"}


def backup_definition(ch: Any, ab: AbilityText, nth: int = 0) -> dict[str, Any] | None:
    """The triggered ability of the ``nth`` backup instance on ability line ``ab`` of ``ch``, or None when not read."""
    from app.rules import scripts
    from app.rules.characteristics import Characteristics

    found = pieces("backup", ab.text)
    following = [x for x in ch.abilities if x.index > ab.index]
    if nth >= len(found) or not following:
        return None
    n = int(found[nth].split()[1]) if " " in found[nth] else 0
    if n not in _COUNT_WORDS:
        return None
    keywords: list[str] = []
    quotes: list[str] = []
    for x in following:
        text = re.sub(r"\s*\(.*?\)", "", x.text).strip()
        if x.kind == "keywords":
            keywords += [p.strip().lower() for p in re.split(r"[,;]\s*", text.rstrip(".")) if p.strip()]
        elif '"' not in text:
            from app.rules import zones100g

            quotes.append(zones100g.native(text))  # -- zones (wave 100G) -- a line read in other words with the same meaning (Guardian Scalelord)
        else:
            return None
    gains = [*keywords, *(f'"{q}"' for q in quotes)]
    if not gains:
        return None
    gained = ", ".join(gains[:-1]) + (", and " if len(gains) > 2 else " and ") + gains[-1] if len(gains) > 1 else gains[0]
    counters = f"{_COUNT_WORDS[n]} +1/+1 counter{'' if n == 1 else 's'}"
    text = (f"When this creature enters, put {counters} on target creature. If that's another creature, until end of turn, "
            f"it gains {gained}.")
    probe = AbilityText(index=0, text=text, kind="triggered")
    d = scripts.define(probe, Characteristics(name="\u0000", abilities=(probe,), types=frozenset({"Creature"})))
    return {**d, "stack_tags": ["Backup"]} if d is not None and d.get("kind") == "triggered" and scripts._event_refs_ok(d) else None


# -- X keywords (wave 41B) -- "Fumiko has bushido X, where X is the number of attacking creatures." (702.45a), "Firebending X, where X is
# ~'s power." (702.189a), "Mobilize X, where X is the number of creature cards in your graveyard." (702.181a): the keyword's own meaning with
# the number the text defines (107.3c); a triggered ability works its X out as it resolves (608.2h) — Fumiko's ruling (2005-02-01): "The bushido
# bonus is calculated each time Fumiko's bushido trigger resolves, based on the number of attackers at that time." Soulshift X (Kodama of the
# Center Tree) stays manual: its ruling reads the state "immediately before the Soulshift trigger", Kodama's own count included, which is not
# when its trigger resolves. A bushido definition is carried by triggers.blocked, the others are ordinary triggers (triggers.abilities).
_DYNAMIC_X = re.compile(r"(?P<kw>bushido|firebending|mobilize|annihilator) X, where X is (?P<xdef>[^.]+?)\.?", re.IGNORECASE)
_NOT_ALONE = re.compile(r'"(?:it|that_player|this_way|event[a-z_]*|ref[a-z_]*|cost:[a-z]+)"|"x"')  # a value that needs what this line has not got


def dynamic_x(text: str) -> dict[str, Any] | None:
    """The triggered ability of a static line "[~ has] bushido / firebending / mobilize X, where X is …", or None (not read)."""
    from app.rules import scripts  # (scripts imports this module)

    if sm := re.fullmatch(r"soulshift X, where X is the number of (\w+)s you control\.?", text.removeprefix("~ has ")):
        # -- soulshift X (wave 110G) -- 702.46a; Kodama's ruling (2005-02-01): X is read from the state just before it died (triggers.py)
        return {"kind": "triggered", "trigger": "dies_self", "optional": True, "soulshift_x110g": sm[1],
                "target": {"what": "graveyard:" + sm[1] + ":0"}, "effects": [{"do": "bounce", "who": "target"}]}
    m = _DYNAMIC_X.fullmatch(text.removeprefix("~ has "))
    if m is None:
        return None
    try:
        value = scripts._x_amount(re.sub(r"\bon it$", "on ~", m["xdef"]))  # (wave 49B: "counters on it", the creature that has the keyword)
    except scripts._NoMatch:
        return None
    if _NOT_ALONE.search(json.dumps(value)):
        return None
    kw = m["kw"].lower()
    if kw in ("mobilize", "annihilator"):  # (wave 49B: annihilator X, 702.86a, read as it resolves: Ulamog, the Defiler's ruling 2024-06-07)
        d = json.loads(_definition(f"{kw} 2") or "[]")
        if len(d) != 1 or d[0]["effects"][0].get("do") != ("create_attacking" if kw == "mobilize" else "sacrifice_choice"):
            return None
        d[0]["effects"][0]["n"] = value
        return d[0]
    effect = {"do": "firebend", "n": value} if kw == "firebending" else {"do": "pump", "who": "self", "p": value, "t": value}
    return {"kind": "triggered", "trigger": "attacks_self" if kw == "firebending" else "bushido", "optional": False, "target": None,
            "effects": [effect]}

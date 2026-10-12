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
by someone other than the attacking player, 506.3b) it simply isn't attacking. "… attacking that player" (wave 30P) says whom (``at``: the player the
trigger's event is about); ``enter_attacking`` is the one place that asks it, for tokens, token copies and cards put onto the battlefield attacking.
"""

from __future__ import annotations

import json
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
LAND_TYPES = frozenset({"Plains", "Island", "Swamp", "Mountain", "Forest", "Desert", "Cave", "Gate", "Lair", "Locus", "Sphere",
                        "Town", "Urza's", "Mine", "Power-Plant", "Tower"})  # 205.3i (wave 4K: a land creature token)
ENCHANTMENT_TYPES = frozenset({"Aura", "Background", "Cartouche", "Case", "Class", "Curse", "Plan", "Role", "Room",
                               "Rune", "Saga", "Shard", "Shrine"})

# 111.10s–v, colorless artifact tokens with the CR's rules text (the older ones are in
# app.rules.scripts.PREDEFINED_TOKENS; both are consulted).
PREDEFINED_TOKENS = {
    "Map": ("Token Artifact — Map", "{1}, {T}, Sacrifice this token: Target creature you control explores. Activate only as a sorcery."),
    "Junk": ("Token Artifact — Junk", "{T}, Sacrifice this token: Exile the top card of your library. You may play that card this turn. Activate only as a sorcery."),
    "Lander": ("Token Artifact — Lander", "{2}, {T}, Sacrifice this token: Search your library for a basic land card, put it onto the battlefield tapped, then shuffle."),
    "Mutagen": ("Token Artifact — Mutagen", "{1}, {T}, Sacrifice this token: Put a +1/+1 counter on target creature. Activate only as a sorcery."),
    # -- token & pump wordings (wave 6C) -- 111.10w
    "Vibranium": ("Token Artifact — Vibranium", "Indestructible\n{T}: Add {C}. This mana can't be spent to cast a nonartifact spell."),
}
# -- token & pump wordings (wave 6C) -- 111.10d: "A Walker token is a 2/2 black Zombie creature token named Walker."
PREDEFINED_CREATURES = {"Walker": {"power": "2", "toughness": "2", "colors": ["B"], "type_line": "Token Creature — Zombie", "text": ""}}

# -- enter attacking (wave 30P) -- 508.4: its controller chooses what it attacks "unless the effect that put it onto the battlefield specifies what
# it's attacking": "… tapped and attacking that player" (Kaalia: that opponent; Shark Shredder: that player; "defending player"). One reading,
# ``{"as": "that"}``: the player the trigger's event is about — the one the attacking creature attacks (508.5; TriggerEvent.defended), else the one dealt
# combat damage (``players``) — read from the event when it resolves, so it is the same player the trigger saw. "… or a planeswalker they control"
# (Zara, Hans Eriksson) is not read: those stay manual.
def at_re(n: str = "") -> str:
    return rf"(?: (?P<at{n}>that player|that opponent|defending player))?"


AT = at_re()


def at_spec(m: re.Match[str], n: str = "") -> dict[str, Any] | None:
    # (wave 38B: "that opponent" is said apart — ``allowed``: in "a player attacks one of your opponents" it is the one attacked, "that player" the attacker)
    return {"as": "that", **({"opp": True} if m[f"at{n}"] == "that opponent" else {})} if m[f"at{n}"] else None


# -- token & pump wordings (wave 6C) -- numbers past ten ("Create thirteen tapped 2/2 black Zombie creature tokens.")
NUMBERS.update({"eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16,
                "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20})
_QTY = r"[xX] (?:plus|minus) (?:\d+|one|two|three|four|five)|\d+|a|an|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|" \
       r"fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|x|X"  # (wave 34C: "X minus one 2/2 … tokens")
_COLORS = r"colorless|(?:white|blue|black|red|green)(?:(?:,)? (?:and )?(?:white|blue|black|red|green))*"
_CAPS = r"[A-Z][A-Za-z'\-]*(?: [A-Z][A-Za-z'\-]*)*"
# -- token & pump wordings (wave 6C) -- a token's name (111.4: the ability sets it): capitalized words, with the small
# words a name may have inside ("Kobolds of Kher Keep", "Wolves of the Hunt", "Voja, Friend to Elves")
_NAME = r"[A-Z][A-Za-z'\-]*(?:,? (?:(?:of|the|to|of the) )?[A-Z][A-Za-z'\-]*)*"
_SENTENCE = re.compile(
    rf"^create (?:(?P<n>{_QTY}) |(?P<lname>{_NAME}), an? (?P<legendary>legendary) )(?P<tapped>tapped (?P<atk0>and attacking )?)?"
    rf"(?:(?:(?P<pt>(?:\d+|X)/(?:\d+|X)) )?(?:(?P<colors>{_COLORS}) )?(?P<sub>{_CAPS}) (?P<ench>enchantment )?(?P<art>artifact )?"
    r"(?P<land>land )?creature tokens?"
    rf"|(?:(?P<npt>\d+/\d+) )?(?P<ncolors>{_COLORS}) (?P<nsnow>snow )?(?:(?P<nsub>{_CAPS}) )?(?P<nkind>artifact|enchantment) tokens?"  # (wave 15B; wave 38B: a Vehicle's P/T)
    r"|(?P<pre>[A-Z][a-z]+) tokens?)"
    rf"(?: named (?P<name>{_NAME}))?"
    r"(?: with (?P<with>.+?))?"
    rf"(?: named (?P<name2>{_NAME}))?"  # (wave 6C: "… with flying named Wasp")
    rf"(?: that's (?P<thats>all colors|{_COLORS}))?"  # (wave 6C: "an 8/8 Beast creature token that's red, green, and white")
    rf"(?P<attacking> that(?:'s| are) (?P<atapped>tapped and )?attacking{AT})?$")  # (wave 17D: untapped, "that's attacking": Brimaz)
# (wave 6C) "For each creature your opponents control, create a 4/4 green Phyrexian Beast creature token.": the same
# instruction as "Create a 4/4 … token for each creature your opponents control." (the count is read as it resolves)
_EACH_FIRST = re.compile(r"^for each (?P<each>[^,\"]+), create (?P<rest>[^\"]+?(?:\"[^\"]+\")?)$")
_RIDER = re.compile(r"^(?P<head>.+?)(?: for each (?P<each>[^\"]+)|, where [xX] is (?P<xdef>[^\"]+))$")


def _qty(word: str) -> Any:
    if word in ("x", "X"):
        return {"x": 1}
    if " " in word:  # -- X arithmetic (wave 34C) -- "X minus one": values.parse_amount
        return values.parse_amount(word)
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
    if quoted[-1] not in ".)" and (dotted := scripts.granted_ability(quoted + ".")) is not None:  # -- attached events (wave 25D) -- "…gets +1/+0" ends the clause
        return dotted.text
    text = re.sub(r"\bthis token\b", "this creature", quoted)
    text = re.sub(r"\bThis token\b", "This creature", text)
    return text if scripts.granted_ability(text) is not None else None


def _with(part: str | None, vehicle: bool = False) -> tuple[list[str], str | None] | None:
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
            part = part[:-4].rstrip(", ")  # (wave 26D: "flying, haste, and "…"")
        if '"' in quoted:
            return None
    kws = [k.strip() for k in re.split(r", and |, | and ", part) if k.strip()]
    # (wave 3E: "toxic N", read by combat.py from the token's keyword line, 702.164)
    # (wave 17D: a keyword whose meaning is a triggered ability the engine reads — training, mentor, dethrone … — 702.149a)
    from app.rules import (
        keyword_triggers,
        protection,  # -- trigger other (wave 26B) -- "with protection from black" (702.16): the qualities the engine enforces
    )

    if any(k not in SUPPORTED_KEYWORDS and not re.fullmatch(r"toxic \d+", k) and not keyword_triggers.supported(k, k)
           and not (k.startswith("protection from ") and protection.supported(k))
           and not (vehicle and re.fullmatch(r"crew \d+", k)) for k in kws):  # (wave 38B: a Vehicle token's "crew N", 702.122a)
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
    first = _EACH_FIRST.match(sentence)  # -- token & pump wordings (wave 6C) --
    if first is not None:
        if " for each " in first["rest"] or ", where " in first["rest"]:
            return None
        sentence = f"create {first['rest']} for each {first['each']}"
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
    if m["name"] and m["name2"]:
        return None
    if m["nkind"]:
        plain = each is None and xdef is None and half is None
        return _vehicle(m, n_word=m["n"], plain=plain) if m["npt"] else _named_noncreature(m, n_word=m["n"], plain=plain)
    if m["lname"] and (m["pre"] or m["name"] or m["name2"] or each is not None or xdef is not None or half is not None):
        return None  # -- token & pump wordings (wave 6C) -- "create Voja, a legendary 2/2 … token": one, named so (111.4)
    if (m["colors"] is None) == (m["thats"] is None) and not m["pre"]:
        return None  # (the colors are said once: before the creature types, or as "that's …")
    n = _qty(m["n"]) if m["n"] else 1
    if half is not None:
        n = {"times": [2, n]} if half["twice"] else {"half": n, "round": half["round"]}
    if each is not None:
        # -- "this way" outcomes (wave 4A) -- "for each creature card milled this way"
        from app.rules import this_way

        v = this_way.parse(each) or values.parse_count(each, it="it") or values.player_relative(each)  # (wave 19D: "for each +1/+1 counter on it": the trigger's object, bound by scripts)
        if v is None:  # (wave 30N: "for each artifact they control": the trigger's player, scripts._that_players_hand)
            return None
        n = v if n == 1 else {"times": [n, v]}
    if m["pre"]:
        if m["with"] or m["name"] or m["name2"] or m["thats"] or m["attacking"]:
            return None
        found = PREDEFINED_TOKENS.get(m["pre"]) or scripts.PREDEFINED_TOKENS.get(m["pre"])
        creature = PREDEFINED_CREATURES.get(m["pre"])  # (wave 6C)
        if found is None and creature is None:
            return None
        if creature is not None or found is None:
            assert creature is not None
            token: dict[str, Any] = {"name": m["pre"], **creature, "colors": list(creature["colors"])}
        else:
            type_line, ability = found
            token = {"name": m["pre"], "power": None, "toughness": None,
                     "colors": list(scripts.PREDEFINED_COLORS.get(m["pre"], ())), "type_line": type_line, "text": ability}
    else:
        extra = (ARTIFACT_TYPES if m["art"] else frozenset()) | (ENCHANTMENT_TYPES if m["ench"] else frozenset()) \
            | (LAND_TYPES if m["land"] else frozenset())  # (wave 4K: "Forest Dryad land creature tokens", 205.3i)
        if m["land"] and (m["ench"] or m["art"]):
            return None
        subtypes = _subtypes(m["sub"], extra)
        own = m["lname"] or m["name"] or m["name2"]  # -- saga (wave 26D) -- its own name in its quoted ability: "When Smaug dies, …" is "When this creature dies, …"
        parsed_with = _with(re.sub(r'"[^"]*"', lambda q: re.sub(rf'(^"|\. )?{re.escape(own)}', lambda k: f"{k[1]}This creature" if k[1] else "this creature",
                                                                q[0]), m["with"]) if own and m["with"] else m["with"])  # (review: "The Tiger God can't …" starts a sentence)
        if subtypes is None or parsed_with is None:
            return None
        kws, quoted = parsed_with
        # -- X sized by a count (wave 4K) -- "an X/X … token": the value of X as the token is created is its printed P/T
        # (111.3: its copiable values; fixed then, 608.2h), evaluated by effects.create_token
        if m["pt"] is None:  # -- trigger tail (wave 15B) -- no printed P/T: a quoted characteristic-defining ability sets both (604.3, 208.1)
            if not quoted or not re.match(r"This (?:creature|token)'s power (?:and toughness are each|is) equal to ", quoted):
                return None
            m_pt = "*/*"  # (nothing is printed: the CDA, layer 7a, defines both, as for a card printed with "*")
        else:
            m_pt = m["pt"]
        p, t = (_qty(s) if s == "X" else s for s in m_pt.split("/"))
        said = m["colors"] or m["thats"]
        # (105.2c colorless; wave 6C: "that's all colors" — each of the five, 105.1)
        colors = [] if said == "colorless" else list("WUBRG") if said == "all colors" else \
            [COLOR_WORDS[w] for w in re.findall(r"white|blue|black|red|green", said)]
        type_line = (f"{'Legendary ' if m['legendary'] else ''}Token {'Enchantment ' if m['ench'] else ''}"
                     f"{'Artifact ' if m['art'] else ''}{'Land ' if m['land'] else ''}Creature — {' '.join(subtypes)}")
        lines = [k.capitalize() for k in kws] + ([quoted] if quoted else [])
        name = m["lname"] or m["name"] or m["name2"]
        token = {"name": name or " ".join(subtypes), "power": p, "toughness": t, "colors": colors,
                 "type_line": type_line, "text": "\n".join(lines)}
    if xdef is not None:  # -- X sized by a count (wave 4K) -- one X for the number and the P/T alike (107.3c)
        from app.rules import language

        v = language.x_definition(xdef)
        if v is None or not language._has_x([n, token["power"], token["toughness"]]):
            return None
        n, token = language._bind_x(n, v), language._bind_x(token, v)
    effect: Effect = {"do": "create_attacking" if m["attacking"] or m["atk0"] else "create_token", "who": "you", "n": n, "token": token}
    if m["tapped"] or m["atapped"]:
        effect["tapped"] = True
    if (at := at_spec(m)) is not None:  # -- enter attacking (wave 30P) -- "… that's tapped and attacking that player" (508.4)
        effect["at"] = at
    return [effect]


def _vehicle(m: re.Match[str], *, n_word: str | None, plain: bool) -> list[Effect] | None:
    """-- vehicle tokens (wave 38B) -- "create a 3/2 colorless Vehicle artifact token with crew 1" (Mu Yanling, Chandra, Spark Hunter), "… named Zeppelin with
    flying and crew 3" (Lita), "create The Blackjack, a legendary 3/3 colorless Vehicle artifact token with flying and crew 2" (Setzer): a Vehicle is an
    artifact with a printed power and toughness (301.7) that is no creature until crewed (702.122a: the token's own "Crew N" line, run like a card's, 111.3).
    The name is the effect's (111.4), else the subtype's. Only a fixed power and toughness, keywords and crew: any other rider leaves the sentence unread."""
    if not plain or m["nkind"] != "artifact" or m["nsub"] != "Vehicle" or m["nsnow"] or m["thats"] or m["attacking"] or m["pre"] or (
            m["lname"] and (m["name"] or m["name2"])):
        return None
    parsed = _with(m["with"], vehicle=True)
    if parsed is None:
        return None
    kws, quoted = parsed
    power, toughness = m["npt"].split("/")
    colors = [] if m["ncolors"] == "colorless" else [COLOR_WORDS[w] for w in re.findall(r"white|blue|black|red|green", m["ncolors"])]
    name = m["lname"] or m["name"] or m["name2"] or "Vehicle"
    effect: Effect = {"do": "create_token", "who": "you", "n": _qty(n_word) if n_word else 1,
                      "token": {"name": name, "power": power, "toughness": toughness, "colors": colors,
                                "type_line": f"{'Legendary ' if m['lname'] else ''}Token Artifact — Vehicle",
                                "text": "\n".join([k.capitalize() for k in kws] + ([quoted] if quoted else []))}}
    if m["tapped"]:
        effect["tapped"] = True
    return [effect]


def _named_noncreature(m: re.Match[str], *, n_word: str | None, plain: bool) -> list[Effect] | None:
    """-- trigger tail (wave 15B) -- "create a colorless artifact token named Scrap [with "…" and "…"]" (111.4: the ability sets
    the name; 111.10 has no such predefined token): a noncreature token with its quoted abilities, each of which the engine must
    carry out (a keyword, a name or an ability it doesn't know leaves the sentence unread)."""
    kind, said = m["nkind"], m["ncolors"]
    name = m["name"] or m["name2"] or m["lname"]  # (wave 25D: "create Cragflame, a legendary colorless Equipment artifact token with …")
    if m["lname"] and (m["name"] or m["name2"]):
        return None
    # -- attached events (wave 25D) -- 702.6: an Equipment token's own "equip {2}" ("create a colorless Equipment artifact token named Axe with
    # "Equipped creature gets +1/+0" and equip {2}.")
    equip = re.search(r'(?:^| and )(equip \{[^}"]+\}(?: and equip \{[^}"]+\})*)$', m["with"] or "") if m["nsub"] == "Equipment" else None
    with_ = (m["with"] or "")[:equip.start()] if equip else m["with"] or ""
    quotes = re.findall(r'"([^"]+)"', with_)
    if not plain or not name or m["thats"] or m["attacking"] or m["pre"] or (
            with_ and not re.fullmatch(r'"[^"]+"(?: and "[^"]+")*', with_)):
        return None
    allowed = ARTIFACT_TYPES if kind == "artifact" else ENCHANTMENT_TYPES
    subs = [m["nsub"]] if m["nsub"] else []
    if any(x not in allowed for x in subs):
        return None
    lines = []
    for q in quotes:
        line = _quoted_text(q.replace("this token", f"this {kind}")) if "this token" in q else _quoted_text(q)
        if line is None or ('"' in line):
            return None
        lines.append(line)
    for cost in re.findall(r"equip (\{[^}]+\})", equip[1]) if equip else ():
        line = _quoted_text(f"Equip {cost}")
        if line is None:
            return None
        lines.append(line)
    colors = [] if said == "colorless" else [COLOR_WORDS[w] for w in re.findall(r"white|blue|black|red|green", said)]
    type_line = f"{'Legendary ' if m['lname'] else ''}Token {'Snow ' if m['nsnow'] else ''}{kind.capitalize()}" + (f" — {' '.join(subs)}" if subs else "")
    effect: Effect = {"do": "create_token", "who": "you", "n": _qty(n_word) if n_word else 1,
                      "token": {"name": name, "power": None, "toughness": None, "colors": colors, "type_line": type_line,
                                "text": "\n".join(lines)}}
    if m["tapped"]:
        effect["tapped"] = True
    return [effect]


def token_text(quoted: str) -> str | None:
    """'It has "…"' / 'They have "…"' after a create sentence: the quoted ability, if the engine
    carries it out (the same test as "with …")."""
    return _quoted_text(quoted)


# -- "tapped and attacking" (508.4) -----------------------------------------------------------
_ATTACKING_PHASES = ("declare_attackers", "declare_blockers", "combat_damage", "end_combat")


def allowed(d: dict[str, Any]) -> bool:
    """``at`` names "that player": only a trigger about an attack (the player attacked) or combat damage to a player (the one dealt it) has one."""
    if '"as": "that"' not in json.dumps(d, default=str):
        return True
    cond = d.get("cond") or {}
    # -- tapped and attacking (wave 38B) -- 508.4: "Whenever a player attacks one of your opponents, that attacking player creates a tapped … token that's
    # attacking that opponent" (Ellie, Combat Calligrapher): the opponent the event's attack was declared against (TriggerEvent.defended); "that player" there
    # would be the attacker, so only the word "opponent" is read
    others = cond.get("player") == "any" and cond.get("defender") == "opponent" and not cond.get("min_attackers") and '"opp": true' in json.dumps(d, default=str)
    return d.get("kind") == "triggered" and (d.get("trigger") == "attacks_self" or (
        d.get("trigger") == "event" and cond.get("event") in ("attack", "you_attack", "deal_combat_damage_player") and not cond.get("aggregate")
        and (cond.get("event") != "you_attack" or cond.get("player") == "you" or others)))  # ("you attack a player": not "a player attacks you")


def create_attacking(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Create the tokens tapped; during the declare attackers step or later of the combat phase
    (508.4) their controller, if they are the attacking player (506.3b), chooses which defending
    player or planeswalker they attack (802.2: in a multiplayer game every opponent is a
    defending player). They are attacking but never "attacked" (no attack triggers)."""
    from app.rules import effects  # (effects registers this module's primitives)

    # -- tapped and attacking (wave 38B) -- whoever creates them: "that attacking player creates a tapped … token that's attacking that opponent" (Ellie):
    # that player is the creature's controller and so the one who attacks with it (508.4), or it never attacks if they aren't an attacking player (506.3b)
    who = e.get("who") or "you"
    makers = effects._players(plan, ctx, who)
    before = set(plan.state.cards)
    effects.create_token(plan, ctx, {**e, "who": who, "tapped": bool(e.get("tapped"))})
    return enter_attacking(plan, ctx, [cid for cid in plan.state.cards if cid not in before], e.get("at"), makers[0] if len(makers) == 1 else None)


def attack_options(plan: Plan, ctx: dict[str, Any], pid: str, at: dict[str, Any] | None = None) -> list[DecisionOption]:
    """What a creature put onto the battlefield attacking may attack (508.4): any defending player (802.2: every opponent), a planeswalker a defending
    player controls, or a battle a defending player protects (310.9b); with ``at``, only the player the effect names. Nobody left to name (508.4a-b:
    that player is gone) leaves none: it enters but never attacks."""
    from app.rules import battles

    defenders = [p for p in plan.live() if p != pid]
    if at is not None:
        ev = ctx.get("event") or {}
        named = ev.get("defended") or next(iter(ev.get("players") or []), None)
        defenders = [named] if named in defenders else []
    options = [DecisionOption(id=p, label=plan.name(p)) for p in defenders]
    if at is None:
        options += [DecisionOption(id=c.id, label=f"{c.name} ({plan.name(c.controller)})", card_id=c.id)
                    for c in plan.state.cards.values() if c.zone.endswith(":battlefield") and c.controller in defenders
                    and plan.in_game(c) and "Planeswalker" in plan.ch(c).types]
        options += [DecisionOption(id=b, label=f"{plan.state.cards[b].name or 'Battle'} (battle)", card_id=b)
                    for b in battles.attackable(plan.state, pid, defenders, plan.ch)]
    return options


def enter_attacking(plan: Plan, ctx: dict[str, Any], made: list[str], at: dict[str, Any] | None = None, pid: str | None = None) -> bool:
    """-- token copy (wave 20F) -- the attack choice of creatures that just entered "tapped and attacking" (508.4): tokens, token copies
    (copying.token_copy), cards put onto the battlefield from a hand or a graveyard or a look (refused_zones, looking, put_from_hand); False while
    their controller is asked whom they attack. (wave 38B: ``pid``, their controller when it isn't the ability's.)"""
    pid = pid or ctx["controller"]
    new = [c for c in made if (card := plan.state.cards.get(c)) is not None and card.controller == pid and card.zone.endswith(":battlefield")
           and plan.ch(card).is_creature]
    if not new or plan.state.turn.phase not in _ATTACKING_PHASES or pid != plan.active:
        return True
    options = attack_options(plan, ctx, pid, at)
    if not options:
        return True
    if len(options) == 1:
        _attack_with(plan, new, options[0].id, pid)
        return True
    # -- falsification (wave 30D) -- 508.4: its controller chooses what *each* creature put onto the battlefield attacking attacks (Anim Pakal's
    # ruling: each Gnome can attack a different player): one question per token, the rest follow in ``more``
    decide(plan, player=pid, kind="choose_one", prompt=f"{plan.state.cards[new[0]].name or 'A token'} enters attacking: attacking whom?"
           + (f" ({len(new) - 1} more to place)" if len(new) > 1 else ""),
           options=options, resume={"step": "token_attack", "ctx": ctx, "cards": new[:1], "more": new[1:], "at": at, "pid": pid})
    return False


def _attack_with(plan: Plan, cards: list[str], target: str, actor: str) -> None:
    kind = "player" if target in plan.state.players else "card"
    cards = [c for c in cards if c in plan.state.cards and plan.state.cards[c].zone.endswith(":battlefield")]
    if kind == "card" and (target not in plan.state.cards or not plan.state.cards[target].zone.endswith(":battlefield")):
        return  # 508.4a: the planeswalker or battle is gone: never an attacking creature
    if kind == "player" and target not in plan.live():
        return  # 508.4a: that player left the game
    if cards:
        plan.do({"type": "attack", "card_ids": cards, "target": {"kind": kind, "id": target}}, actor=actor)


def resume_token_attack(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import effects

    r = d.resume
    if chosen:
        _attack_with(plan, r["cards"], chosen[0], d.player)
    # -- falsification (wave 30D) -- the next token (old saves have no "more": their one answer covered every token)
    if r.get("more") and not enter_attacking(plan, r["ctx"], r["more"], r.get("at"), r.get("pid")):
        return
    effects.continue_effects(plan, r["ctx"])


# -- your choice (wave 38B) -- "create your choice of a Clue token, a Food token, or a Treasure token" (The Third Doctor, Transmutation Font): the controller
# chooses one of the predefined tokens named as the instruction is carried out (608.2d: a choice the effect offers; 111.10: each is its own definition).
# The kind chosen replaces this instruction in the resolution (an ordinary ``create_token`` then runs in its place, so a replacement — Doubling Season,
# 616.1 — sees one creation like any other, and can pause it). Only predefined tokens with no power and toughness (artifact and enchantment ones).
def pick_parse(kinds: str) -> list[Effect] | None:
    """The instruction for "a X token, a Y token, or a Z token", or None (not read)."""
    found: list[str] = []
    for item in (i.strip() for i in re.split(r", or |, | or ", kinds.strip()) if i.strip()):
        m = re.fullmatch(r"an? ([A-Z][a-z]+) tokens?", item)
        made = parse(f"create a {m[1]} token") if m else None
        if m is None or made is None or len(made) != 1 or made[0]["do"] != "create_token" or made[0]["token"]["power"] is not None:
            return None
        found.append(m[1])
    return [{"do": "pick_token", "who": "you", "kinds": found}] if len(found) >= 2 and len(set(found)) == len(found) else None


def pick_token(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    decide(plan, player=ctx["controller"], kind="choose_one", prompt=f"{ctx.get('name') or 'Choose'}: choose a token to create",
           options=[DecisionOption(id=k, label=f"{k} token") for k in e["kinds"]], resume={"step": "pick_token", "ctx": ctx, "e": e},
           source=plan.state.cards.get(ctx.get("source_card") or ""))
    return False


def resume_pick_token(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.game.errors import ActionError
    from app.rules import effects

    ctx, e = d.resume["ctx"], d.resume["e"]
    if len(chosen) != 1 or chosen[0] not in e["kinds"]:
        raise ActionError("Choose one of the tokens offered")
    made = parse(f"create a {chosen[0]} token")
    assert made is not None
    plan.note(f"{plan.name(d.player)} chooses a {chosen[0]} token", actor=d.player)
    at = ctx["next"] - 1
    ctx["effects"] = [*ctx["effects"][:at], *made, *ctx["effects"][at + 1:]]
    ctx["next"] = at
    effects.continue_effects(plan, ctx)


PRIMITIVES = {"create_attacking": create_attacking, "pick_token": pick_token}
RESUME = {"token_attack": resume_token_attack, "pick_token": resume_pick_token}

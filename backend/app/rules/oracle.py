"""Oracle text → a list of classified ability lines.

This is *parsing as data*: it never evaluates anything. The classification feeds coverage
(which parts of a card the engine automates) and gives every ability a stable index, so a client
can say ``activate_ability(card, 2)``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from app.game.mana_cost_templates import GrantedManaCost

AbilityKind = Literal["keywords", "mana", "activated", "loyalty", "triggered", "static", "spell"]

_REMINDER = re.compile(r"\s*\([^()]*\)")
_MANA_SYMBOL = r"\{(?:[WUBRGCS]|\d+)\}"
# "{T}: Add {G}." / "{T}: Add {R} or {G}." / "{T}: Add {C}{C}." / "{T}: Add one mana of any color."
_MANA_ABILITY = re.compile(
    rf"^\{{T\}}: Add (?:{_MANA_SYMBOL}(?:{_MANA_SYMBOL})*(?:(?:, | or |, or ){_MANA_SYMBOL})*|one mana of any color)\.$"
)
_LOYALTY = re.compile(r"^[+−-]?\d+: |^[+−-]X: ")
_TRIGGER = re.compile(r"^(?:[A-Z0-9][\w'’!?,.\- ]+ — )?(When|Whenever|At) ")  # (wave 6E: "Exterminate! — When …"; wave 41A: a letter with a mark, "Pavitr's Sevā — When …")  # an ability word ("Landfall — ") may lead
# (-- ability words (wave 4F) -- digits too: "Descend 4 — Whenever …", 207.2c)
# (-- attached events (wave 4L) -- "Equipped creature has "{T}: …"" is a static granting an ability, not a cost)
_COST_START = re.compile(
    r"^(\{[^}]+\}|Sacrifice|Tap|Untap|Unattach|Discard|Pay|Remove|Exile|Return|Put|Reveal|Mill|Collect|Forage|[Ee]quip(?!ped)|Crew|"
    r"Channel|Cycling|Ninjutsu|Boast|Exhaust|Waterbend)"
)

# Keyword *abilities* a line may consist of (lower case, parameters stripped). Keyword actions
# (scry, surveil, proliferate…) and ability words are deliberately absent: in a spell they are the
# effect. Being listed only means "recognised"; whether it's automated is up to coverage.
KEYWORDS = frozenset({
    "absorb", "devoid", "renown", "bloodthirst", "soulshift",
    "flying", "reach", "vigilance", "trample", "deathtouch", "lifelink", "first strike", "double strike", "haste",
    "defender", "menace", "hexproof", "hexproof from", "indestructible", "flash", "shroud", "fear", "intimidate", "skulk", "prowess",
    "protection", "ward", "equip", "enchant", "cycling", "kicker", "multikicker", "flashback", "convoke", "delve", "cascade",
    "affinity", "storm", "partner", "partner with", "changeling", "landwalk", "islandwalk", "swampwalk",
    "forestwalk", "mountainwalk", "plainswalk", "snow landwalk", "nonbasic landwalk", "legendary landwalk", "artifact landwalk", "snow plainswalk", "snow islandwalk", "snow swampwalk", "snow mountainwalk", "snow forestwalk", "desertwalk", "exalted", "undying", "persist", "wither", "infect", "toxic",
    "annihilator", "evolve", "extort", "unearth", "embalm", "eternalize", "afflict", "riot", "escape", "mutate",
    "companion", "foretell", "disturb", "daybound", "nightbound", "training", "casualty", "blitz", "backup",
    "bargain", "craft", "disguise", "offspring", "saddle", "crew", "ninjutsu", "commander ninjutsu", "morph", "megamorph", "suspend",
    "rebound", "overload", "surge", "emerge", "madness", "miracle", "dash", "evoke", "bestow", "outlast", "dethrone",
    "fabricate", "improvise", "ascend", "mentor", "jump-start", "spectacle", "encore", "boast", "sneak",
    "champion", "horsemanship", "shadow", "banding", "rampage", "flanking", "bushido", "provoke", "fading", "vanishing", "echo",
    "cumulative upkeep", "buyback", "entwine", "splice", "retrace", "replicate", "soulbond", "unleash", "battle cry",
    "living weapon", "totem armor", "umbra armor", "fortify", "reconfigure", "for mirrodin!", "prototype",
    "read ahead", "ravenous", "squad", "enlist", "decayed", "cleave", "compleated", "demonstrate", "hideaway",
    "exploit",  # (wave 23D)
    "myriad", "melee", "friends forever", "choose a background", "doctor's companion", "space sculptor", "gift",
    "impending", "plot", "spree", "freerunning", "start your engines!", "station", "warp", "job select", "tiered",
    "firebending", "storied", "mobilize", "harmonize", "renew", "undaunted",
    "mayhem", "web-slinging",  # -- Marvel keywords (wave 25A) -- 702.187, 702.188
    "more than meets the eye", "living metal",  # -- commanders (wave 50C) -- 702.162, 702.161 (the Transformers)
    "tribute", "haunt", "paradigm",  # -- keywords (wave 50H) -- 702.104 (app/rules/tribute.py), 702.55 (app/rules/haunt.py), 702.192 (app/rules/paradigm.py)
    "recover", "amplify", "assist",  # -- casting extras (wave 18E) -- 702.59, 702.38, 702.132
    "phasing", "transmute",  # (wave 3R4: casting.transmute)
    "aftermath", "gravestorm", "dredge", "fuse", "awaken", "escalate", "increment",  # -- static_other sweep (wave 16B) -- 702.127 (casting.from_graveyard / cast_grant)
    "ripple",  # -- static_other sweep (wave 17C) -- 702.60 (casting._ripple_triggers)
    "prowl",  # (702.76: alt_costs.KEYWORD_CONDS)
    "cipher",  # (702.99: recursion.cipher)
    "conspire", "teamwork",  # (702.78, 702.194: cost_changes.optional_offers)
    "ingest", "poisonous", "frenzy", "afterlife", "modular", "split second", "graft", "sunburst", "devour",  # -- static wordings (wave 6E) -- (app/rules/keyword_triggers.py)
})

_FORMS = {"awaken": r"awaken \d+—.*", "escalate": r"escalate(?: \{.*|—.*)", "dredge": r"dredge \d+", "fuse": "fuse",
          "aftermath": "aftermath", "gravestorm": "gravestorm", "increment": "increment", "unleash": "unleash"}
_PARAM = re.compile(r"(\{[^}]*\}|\d+|—.*$|\bfrom\b.*$| with .*$|walk$)")


@dataclass(frozen=True)
class AbilityText:
    index: int
    text: str
    kind: AbilityKind
    keywords: tuple[str, ...] = ()  # for "keywords" lines: the normalised keyword names
    cost: str | None = None  # for activated/loyalty abilities: the text before the colon
    intrinsic: bool = False  # granted by a basic land type rather than printed
    section: int = 1  # -- Class (wave 16A) -- 716.2a: the class level whose "as long as this Class is level N or greater" it is under
    keeps: str | None = None  # -- attached events (wave 25D) -- 702.16n: a granted protection that "doesn't remove" "auras" / "self:<granting Aura's id>"
    special: str | None = None  # -- mana for special abilities (wave 19E) -- "equip": an equip ability (702.6); a "Power-up — " line reads as "power_up"
    linked: str | None = None  # -- linked words (wave 33B) -- 607.2f: the word of "As ~ enters, choose Khans or Dragons." this ability ("• Khans — …") belongs to
    borrowed_origin: tuple[str, ...] = ()  # canonical granting path, not a mutable read-time registry
    borrowed_scope: str | None = None  # Explicit scope for an unambiguous legacy saved link, when needed.
    borrowed_color: str | None = None  # object whose particular borrowing static permits colored-mana substitutions
    activation_player: str | None = None  # A resolved grant may reserve activation to its original controller.
    power_up_prepared: bool = False  # A selected native reduction branch, before other cost modifiers.
    granted_mana_cost: GrantedManaCost | None = None  # Frozen actual grant provenance; absent on legacy abilities.


def strip_reminders(text: str) -> str:
    previous = None
    while previous != text:  # nested parentheses are rare but exist
        previous, text = text, _REMINDER.sub("", text)
    return text


_WORDS_HEADER = re.compile(r"As (?:this [a-z]+|~) enters, choose ([A-Z][\w'’-]*) or ([A-Z][\w'’-]*)\.")  # (wave 33B: 607.2f)
_TYPECYCLING = re.compile(r"^((?:(?:basic|artifact) )?[a-z]+cycling)(?: \{|$)")


def keyword_name(piece: str) -> str | None:
    """"Protection from red" → "protection"; "Ward {2}" → "ward"; "Equip {1}" → "equip"."""
    raw = piece.strip().rstrip(".").lower()
    if not raw:
        return None
    if raw in KEYWORDS:
        return raw
    if re.match(r"^\w+ (?:abilities|costs) you (?:activate|pay)\b", raw):  # -- keywords (wave 15E) -- "Equip abilities you activate
        return None  # cost {1} less", "Dash costs you pay cost {2} less": a static ability about the keyword, not the keyword
    if re.match(r"^\w+ costs (?:cost|(?:you|your opponents) pay cost)\b", raw):
        return None  # A global change to a keyword's costs is not that keyword ability.
    if raw.startswith("bands with other "):
        return raw  # CR 702.22b: the quality is part of this keyword's identity.
    if raw.startswith("hexproof from "):  # -- keywords (wave 44D) -- 702.11d: a variant of hexproof, not plain hexproof (_PARAM strips the quality)
        return "hexproof from"
    base = _PARAM.sub("", raw).strip(" —-")
    if base in KEYWORDS:
        return base
    first_two = " ".join(raw.split()[:2])
    if first_two in KEYWORDS:
        return first_two
    first = raw.split()[0]
    if first == "devour" and not re.match(r"devour (?:(?:land|artifact|food) )?(?:\d+|x)\b", raw):  # -- keyword mechanics (wave 9D) --
        return None  # ("Devour in Flames deals 5 damage …" is a card's name, not the keyword)
    # -- static_other sweep (wave 16B) -- ordinary words that open a card's rules text ("Awaken the Inferno deals 6 damage …"): the keyword has its form
    if first in _FORMS and not re.fullmatch(_FORMS[first], raw):
        return None
    if first in KEYWORDS:
        return first
    typecycling = _TYPECYCLING.match(raw)  # "Swampcycling {2}", "Basic landcycling {1}{G}", "Wizardcycling {3}"
    return typecycling[1] if typecycling else None


def keyword_pieces(line: str) -> list[str]:
    """The keyword abilities a keyword line lists, each as written ("Flying, hexproof from artifacts, creatures, and enchantments" → two)."""
    pieces: list[str] = []
    for p in (p for p in re.split(r"[,;]\s*", line) if p.strip()):
        # -- keywords (wave 44D) -- 702.11d, 702.11f: the commas of "hexproof from artifacts, creatures, and enchantments" list the qualities of one keyword
        if pieces and pieces[-1].lower().startswith("hexproof from") and keyword_name(p) is None:
            pieces[-1] += f", {p}"
        else:
            pieces.append(p)
    return pieces


def _keywords_line(line: str) -> tuple[str, ...] | None:
    from app.rules.required_keyword79 import composite_kind

    if (composite79 := composite_kind(line)) is not None:
        return (composite79,)
    if line == 'Equip {10}. This ability costs {X} less to activate, where X is the power of the creature it targets.':
        return ('equip',)
    from app.rules.conditional_own_discounts import flashback_line
    from app.rules.random_choice_receipts import random_buyback

    if random_buyback(line) is not None:
        return ("buyback",)
    if flashback_line(line) is not None:
        return ("flashback",)
    if re.fullmatch(r"partner with [^;.]+", line.strip(), re.IGNORECASE):  # -- keyword pieces (wave 8A) -- 702.124j: the name has a comma
        return ("partner",)
    if re.fullmatch(r"madness—(?:\{[^}]+\})+, Pay \d+ life\.?", line.strip(), re.IGNORECASE):
        return ("madness",)  # one alternative cost, including its life component
    if re.fullmatch(r"flashback—.+", line.strip(), re.IGNORECASE):  # -- static_other sweep (wave 16B) -- 702.34a: "Flashback—{1}{U}, Pay 3 life."
        return ("flashback",)  # (one keyword: the comma is inside its cost)
    if re.fullmatch(r"devour x, where x is the number of creatures devoured this way", line.strip(), re.IGNORECASE):  # -- keyword mechanics (wave 48B) -- Thromok: one keyword (app/rules/devour.py)
        return ("devour",)
    if re.fullmatch(r"enchant [^;]+", line.strip(), re.IGNORECASE):  # -- layers (wave 22A) -- 702.5a: "Enchant creature, land, or planeswalker" is one keyword
        return ("enchant",)  # (the commas list what it may enchant)
    if re.fullmatch(r"ward—[^;]+", line.strip(), re.IGNORECASE):  # -- static_other sweep (wave 17C) -- "Ward—{2}, Pay 2 life." (one cost of two parts)
        return ("ward",)
    if re.fullmatch(r"protection from [^,;]+(?:, (?:and )?from [^,;]+)+", line.strip(), re.IGNORECASE):  # -- keywords (wave 50H) -- 702.16a: "Protection from blue, from black, and from red" is one keyword (app/rules/protection.py)
        return ("protection",)
    if re.fullmatch(r"squad—(?:\{[^}]+\})+, [^;{}]+", line.strip(), re.IGNORECASE):  # -- squad (wave 110E) -- "Squad—{1}, Discard a card." is one keyword (702.157a)
        return ("squad",)
    if re.fullmatch(r"kicker—(?:\{[^}]+\})+, [^;{}]+", line.strip(), re.IGNORECASE):  # -- keywords (wave 50H) -- 702.33a: "Kicker—{2}{R}, Sacrifice a land." is one keyword (its cost has two parts)
        return ("kicker",)
    if re.fullmatch(r"(?i:equip)—(?:\{[^}]+\})+, [^;{}]+|Equip [A-Z][a-z]+(?:, [A-Z][a-z]+)+,? or [A-Z][a-z]+ (?:\{[^}]+\})+", line.strip()):
        return ("equip",)  # -- static permanents (wave 100D) -- 702.6a-b: "Equip—{2}, Pay 2 life.", "Equip Shaman, Warlock, or Wizard {1}": one keyword
    if re.fullmatch(r"eternalize—\{[^;]+", line.strip(), re.IGNORECASE):  # -- keywords (wave 49C) -- 702.129a: "Eternalize—{2}{W}{W}, Discard a card." is one keyword (its cost has two parts)
        return ("eternalize",)
    if re.fullmatch(r"companion\s*—.+", line.strip(), re.IGNORECASE):  # -- companion (wave 38D) -- 702.139a: one keyword (Kaheera's condition lists creature types)
        return ("companion",)
    pieces = keyword_pieces(line)
    names = [keyword_name(p) for p in pieces]
    if names and all(names):
        return tuple(n for n in names if n)
    return None


# (wave 3R3: "{2}, {T}: Choose a color. Add …" (Nykthos) is a mana ability too, 605.1a: it could add mana)
_ADD_MANA = re.compile(r"^(?P<cost>[^:]+): (?:Choose a color(?: of (?:a permanent you control|a card in your graveyard))?\. )?Add ")  # (wave 17B: Meteor Crater)


# -- refused zones/sized (wave 3R4) -- 207.2c ability words and 207.2d flavor words have no rules
# meaning: "Formidable — {G}: …" is an activated ability, "No Mercy — Whenever …" a triggered one.
# A prefix that IS a rule is never one of them: keywords written "Name — " (702.142 boast, 702.177
# exhaust, 702.178 max speed, 702.193 power-up, 702.57 forecast, 702.159 visit, 702.139 companion,
# 702.160 prototype), Case conditions (719.3 "To solve —", "Solved —"), Saga chapters (714.2b),
# "Corrupted —" (-- ability words (wave 4F) -- read like an ability word: scripts.ABILITY_WORDS).
# Anything else is a flavor word only when what follows is a trigger or a cost-led activated ability; other lines are left as they were.
# (-- counters (wave 41A) -- \w: a flavor word may carry a mark on a letter, "Pavitr's Sevā — Whenever …" (Spider-Man India); 207.2d)
_WORD_PREFIX = re.compile(r"^(?P<w>[A-Z0-9][\w'’!?,.\- ]{0,48}?) — (?P<rest>\S.*)$")  # (-- most-played cards II (wave 45A) -- a digit may lead: "10,000 Needles — Whenever …", Jumbo Cactuar)
_NOT_FLAVOR = frozenset({"max speed", "power-up", "exhaust", "boast", "forecast", "visit", "companion", "prototype",
                         "solved", "to solve", "station", "level up",
                         "prize"})  # (-- review (wave 6R) -- "Prize —" is part of an Attraction's visit ability: 702.159b)
_ROMAN = re.compile(r"^[IVX]+(?:, [IVX]+)*$")


def word_prefix(line: str) -> tuple[str, str] | None:
    """(the ability or flavor word, the rest of the line) — or None when the line has no such word."""
    m = _WORD_PREFIX.match(line)
    if m is None or _ROMAN.match(m["w"]):
        return None
    word = m["w"].lower().replace("’", "'")
    from app.rules.scripts import ABILITY_WORDS  # (scripts imports this module at load time)

    if word in ABILITY_WORDS or word == "solved":  # -- Case (wave 51C) -- 719.3c: "Solved — [ability]" is that ability, which works only while the Case is solved (characteristics.of drops it otherwise)
        return m["w"], m["rest"]
    kw = keyword_name(m["w"])
    # (-- long tail (wave 16D) -- a flavor word that merely starts with a keyword's name, "Toxic Spores —", is still a flavor word)
    if word in _NOT_FLAVOR or (kw is not None and (len(word.split()) == 1 or word.split()[0] != kw)) or "{" in word:
        return None
    if word.endswith("villainous choice"):  # -- review (wave 6R) -- "Each opponent faces a villainous choice — …" (701.55a)
        return None
    rest = m["rest"]
    if re.match(r"(?:When|Whenever|At) ", rest):
        return m["w"], rest
    if ":" in rest and _COST_START.match(rest.split(":", 1)[0]) and len(rest.split(":", 1)[0]) < 120:
        return m["w"], rest
    # -- static wordings (wave 6E) -- a flavor word before a static ability or a spell's instruction ("Devastating Charge
    # — Other creatures you control have trample."): no rules meaning either (207.2d)
    if ":" not in rest and not rest.startswith(("•", "(", "{")):
        return m["w"], rest
    return None


_WATCH_LINE = re.compile(r"^(?:At the beginning of each combat this turn, |Whenever .+? this (?:turn|combat), |When you next cast .+? this turn, "
                         r"|When (?:target|that) [^,]+? (?:dies|leaves the battlefield) this turn, "
                         r"|At the beginning of (?:the next|your next|the next turn's|that player's next|its owner's next|their next) [^,]+, )")  # (wave 23B: the Pacts' own paragraph, 603.7)  # -- turn watches (wave 7D; 16D: "When target creature dies this turn,") --


CRAFT_FROM = " from among permanents you control and/or cards in your graveyard"  # -- casting extras (wave 18E) -- 702.167a


def _moves_library(line: str) -> bool:
    """605.1a: immediate instructions move cards to/from a library.

    Delayed/reflexive triggers and quoted granted abilities are other abilities;
    looking, revealing, scrying and reordering within the library do not move a
    card to or from that zone. Replacement effects are deliberately not read.
    """
    immediate = re.split(r"\b(?:When(?:ever)?|At the beginning)\b", line, maxsplit=1)[0]
    immediate = re.sub(r'"[^"\n]*"', '', immediate)
    immediate = re.sub(r"\bDraw [^.]* at the beginning[^.]*\.?", '', immediate, flags=re.I)
    if re.search(r"\b(?:draws?|mills?)\s+(?:a|an|one|two|three|four|five|six|seven|eight|nine|ten|X|\d+|cards?|half|the|up to|that many|a number|any number)\b", immediate, re.I):
        return True
    if re.search(r"\b(?:surveil|discover|connive|manifest|explore|seek)\b", immediate, re.I):
        return True
    if 'library' not in immediate.lower():
        return False
    library_seen = False
    for clause in re.split(r"[.;]|\bthen\b", immediate, flags=re.I):
        has_library = 'library' in clause.lower()
        to_library = re.search(r"\b(?:exile|put|return|shuffle)\b[^:]*\b(?:into|onto|to)\b[^:]*\blibrary\b", clause, re.I)
        same_zone = re.search(r"\b(?:put|return) (?:them|those cards|it|that card) (?:back )?(?:on|onto|to|in)\b", clause, re.I)
        outside_zone = re.search(r"\b(?:hand|graveyard|battlefield|exile)\b", clause, re.I)
        if to_library and not (same_zone and library_seen and not outside_zone):
            return True
        if re.search(r"\b(?:exile|put|return)\b[^:]*\b(?:top|bottom)\b[^:]*\blibrary\b", clause, re.I) and not (same_zone and library_seen and not outside_zone):
            return True
        if (library_seen or has_library) and re.search(
                r"\b(?:put|return) (?:it|them|that card|those cards|any number of them)\b[^:]*\b(?:hand|graveyard|battlefield)\b|"
                         r"\bexile (?:it|them|that card|those cards)\b", clause, re.I):
            return True
        library_seen = library_seen or has_library
    return False


def classify(line: str, *, spell: bool) -> tuple[AbilityKind, tuple[str, ...], str | None]:
    from app.rules import reveal_mana

    if reveal_mana.spec(line) is not None:
        return "mana", (), "{T}"
    if _MANA_ABILITY.match(line):
        return "mana", (), "{T}"
    # -- mana riders (wave 5A) -- 605.1a: "{T}: For each color among permanents you control, add one mana of that color."
    if re.fullmatch(r'[^:]+: For each color among monocolored permanents you control, add one mana of that color\.', line):
        return 'mana', (), line.split(':',1)[0]
    if re.fullmatch(r'[^:]+: For each color among the exiled cards used to craft this creature, add one mana of that color\.', line) and not _moves_library(line):
        return 'mana', (), line.split(':', 1)[0]
    from app.rules.mana_riders import EACH_COLOR_LINE  # (Bloom Tender: no target, adds mana: a mana ability)

    if (each := EACH_COLOR_LINE.match(line)) is not None and not _moves_library(line):
        return "mana", (), each["cost"]
    from app.rules.immediate_mana_resolutions import beneficiary_spec

    if (benefit := beneficiary_spec(line)) is not None and _COST_START.match(benefit[0]) and not _moves_library(line) and not _LOYALTY.match(line):
        return 'mana', (), benefit[0]
    m = _ADD_MANA.match(line)
    if m and _moves_library(line):  # CR 605.1a applies to both costs and effects, not delayed triggers.
        m = None  # e.g. Millikin's cost or Chromatic Sphere's immediate draw uses the stack.
    from app.rules.activated_copy_effects import NEXT_X

    mana_target_line = line.replace('choose new targets for the copy', '') if NEXT_X + '.' in line else line
    if m and not _LOYALTY.match(line) and "target" not in (line.replace("choose new targets for the copy", "") if "that mana is spent" in line or "When you spend this mana" in line else mana_target_line).lower() and '"' not in m.group("cost") \
            and not _TRIGGER.match(line) and not line.startswith("•"):  # a granted/token ability isn't one
        return "mana", (), m.group("cost")
    kws = _keywords_line(line)
    if kws is not None and ":" not in line:
        return "keywords", kws, None
    if _LOYALTY.match(line):
        return "loyalty", (), line.split(":", 1)[0]
    if _TRIGGER.match(line):
        # -- turn watches (wave 7D) -- an instant's or sorcery's "Whenever … this turn, …" is a spell ability that
        # creates a delayed triggered ability (603.7), not a triggered ability of the spell
        return ("spell" if spell and _WATCH_LINE.match(line) else "triggered"), (), None
    worded = word_prefix(line) if ":" in line else None  # -- refused zones/sized (wave 3R4) -- 207.2c/207.2d
    if line.startswith("Exhaust — ") and ":" in line:  # -- ability words (wave 4F) -- 702.177a: an activated ability
        worded = ("Exhaust", line[len("Exhaust — "):])  # (its "Activate only once": restrictions.parse)
    if line.startswith("Boast — ") and ":" in line:  # -- activation costs (wave 4H) -- 702.142a (restrictions.parse)
        worded = ("Boast", line[len("Boast — "):])
    if line.startswith("Power-up — ") and ":" in line:  # -- counters (wave 7C) -- 702.193a (restrictions.parse, power_up.py)
        worded = ("Power-up", line[len("Power-up — "):])
    if line.startswith("Forecast — ") and ":" in line:  # -- forecast (wave 24C) -- 702.57a (restrictions.parse; the cost is revealed from the hand)
        worded = ("Forecast", line[len("Forecast — "):])
    if worded is not None:  # (wave 4F: channel is read, 113.6m)
        cost = worded[1].split(":", 1)[0]
        if _COST_START.match(cost) and len(cost) < 120:
            return "activated", (), cost
    if ":" in line:
        cost = line.split(":", 1)[0]
        if _COST_START.match(cost) and len(cost.replace(CRAFT_FROM, "")) < 120:  # (wave 18E: craft's materials parts are long)
            return "activated", (), cost
    if kws is not None:  # keyword with a cost after a colon, e.g. "Equip: {2}" style oddities
        return "keywords", kws, None
    return ("spell" if spell else "static"), (), None


def split_sentences(body: str) -> list[str]:
    """Split an ability's text into its sentences: after a full stop and a space — but never inside
    a quoted ability, and a stop that ends a quote is followed by the closing quotation mark
    (``… it." It's still a land.`` is two sentences; ``gains "Whenever …. Draw a card."`` is one).
    Text after the last boundary is the last sentence; empty pieces are dropped."""
    out: list[str] = []
    inside = False
    start = 0
    i = 0
    n = len(body)
    while i < n:
        ch = body[i]
        if ch == '"':
            inside = not inside
        elif ch.isspace() and not inside and i > start:
            prev = body[i - 1]
            if prev == "." or (prev == '"' and i >= 2 and body[i - 2] == "."):
                out.append(body[start:i])
                while i < n and body[i].isspace():
                    i += 1
                start = i
                continue
        i += 1
    out.append(body[start:])
    return [s for s in out if s]


MASTER_CHEF = ('Commander creatures you own have "This creature enters with an additional +1/+1 counter on it" and '
               '"Other creatures you control enter with an additional +1/+1 counter on them."')


STAFF_ROOM = "Whenever a creature you control deals combat damage to a player, turn that creature face up or put a +1/+1 counter on it."
DOG_UMBRA = "As long as another player controls enchanted creature, it can't attack or block. Otherwise, this Aura has umbra armor."
EARTHBIND = "When this Aura enters, if enchanted creature has flying, this Aura deals 2 damage to that creature and this Aura gains \"Enchanted creature loses flying.\""


def parse_abilities(oracle_text: str | None, *, spell: bool = False, pt: tuple[str | None, str | None] = (None, None)) -> list[AbilityText]:
    """Split Oracle text into classified ability lines (reminder text removed).

    ``spell`` is true for instants and sorceries: their non-keyword lines are the spell's effect.
    ``pt``: a station card's printed power and toughness (the box under its last station symbol, 721.2b)."""
    if not oracle_text:
        return []
    out: list[AbilityText] = []
    lines = [raw.strip() for raw in strip_reminders(oracle_text).split("\n") if raw.strip()]
    if spell and any(line.startswith("Cleave {") for line in lines):  # -- keywords (wave 50H) -- 702.148a: cast any other way the brackets are only punctuation (cleave.cleaved)
        lines = [line if line.startswith("Cleave {") else line.replace("[", "").replace("]", "") for line in lines]
    if not spell and "LEVEL " in oracle_text:  # -- keyword mechanics (wave 9D) -- a leveler's text as 702.87a / 711.2 say it
        from app.rules import levelers

        lines = levelers.rewrite(lines, lambda t: _keywords_line(t) is not None)
    if not spell and "Station" in lines:  # -- Station (wave 46D) -- a station card's text as 702.184a / 721.2 say it
        from app.rules import levelers

        lines = levelers.station(lines, oracle_text, pt, lambda t: _keywords_line(t) is not None)
    # -- keyword meanings (wave 12B) -- 702.72a: "Champion an [object]" represents two linked triggered abilities (607.2a)
    for i, line in enumerate(lines):
        if m := re.fullmatch(r"Champion an? ([A-Za-z]+(?: or [A-Za-z]+)?)", line):
            lines[i:i + 1] = [f"When this permanent enters, sacrifice it unless you exile another {m[1]} you control.",
                              "When this permanent leaves the battlefield, return the exiled card to the battlefield under "
                              "its owner's control."]
    # -- lines (wave 110D) -- Master Chef: 614.12 a commander creature entering is checked with the abilities it would have there (its own and Chef's
    # grants), so the granted "This creature enters with ..." is "commander creatures you own enter with ...", then the second grant as its own ability
    for i, line in enumerate(lines):
        if line == MASTER_CHEF:
            lines[i:i + 1] = ["Commander creatures you own enter with an additional +1/+1 counter on them.",
                              'Commander creatures you own have "Other creatures you control enter with an additional +1/+1 counter on them."']
    # -- lines (wave 110D) -- Dog Umbra: 608.2c "Otherwise" = the enchanted creature is not controlled by another player, so you control it (an Aura's
    # controller can't be attached to nothing); two conditional statics
    for i, line in enumerate(lines):
        if line == DOG_UMBRA:
            lines[i:i + 1] = ["As long as another player controls enchanted creature, it can't attack or block.",
                              "As long as you control enchanted creature, this Aura has umbra armor."]
    # -- lines (wave 110D) -- Staff Room: "A or B" is a choice of one of the two (700.2), a modal trigger
    for i, line in enumerate(lines):
        if line == STAFF_ROOM:
            lines[i:i + 1] = ["Whenever a creature you control deals combat damage to a player, choose one —",
                              "• Turn that creature face up.", "• Put a +1/+1 counter on that creature."]
    # -- (wave 110J) -- Earthbind: "…and this Aura gains "Enchanted creature loses flying."" is the trigger plus a static that applies once it was gained
    for i, line in enumerate(lines):
        if line == EARTHBIND:
            lines[i:i + 1] = [line, "As long as this Aura gained that ability, enchanted creature loses flying."]
    # -- lines (wave 110G) -- Ertai's Familiar: phasing out is not leaving (702.26d), so "phases out or leaves the battlefield" is two triggers that never share an event
    for i, line in enumerate(lines):
        if line == "When this creature phases out or leaves the battlefield, mill three cards.":
            lines[i:i + 1] = ["When this creature phases out, mill three cards.", "When this creature leaves the battlefield, mill three cards."]
    # -- keywords (wave 50H) -- 207.2d: a flavor word before an equip cost ("Machina — Equip {4}", Final Fantasy equipment) has no rules meaning
    for i, line in enumerate(lines):
        if not spell and " — Equip" in line and (w := word_prefix(line)) is not None and w[1].startswith("Equip") and _keywords_line(w[1]) == ("equip",):
            lines[i] = w[1]
    # -- keywords (wave 51C) -- 207.2d: a flavor word before a protection keyword line ("Void Shields — Protection from mana value 3 or less", Reaver Titan) has no rules meaning either
    for i, line in enumerate(lines):
        if not spell and " — Protection from " in line and (w := word_prefix(line)) is not None and w[1].startswith("Protection from ") and _keywords_line(w[1]) == ("protection",):
            lines[i] = w[1]
    # -- any number as an additional cost (wave 48B) -- 603.12: "As an additional cost to cast this spell, you may sacrifice one or more creatures. When you do, copy this spell for each
    # creature sacrificed this way." (Plumb the Forbidden) is the cost and a trigger of the spell on being cast (601.2i), which only exists if something was sacrificed
    if spell:
        for i, line in enumerate(lines):
            if m := re.fullmatch(r"(As an additional cost to cast this spell, you may sacrifice one or more (creature)s)\. When you do, copy this spell for each \2 sacrificed this way\.", line):
                lines[i:i + 1] = [f"{m[1]}.", f"When you cast this spell, if you sacrificed one or more {m[2]}s this way, copy it for each {m[2]} sacrificed this way."]
    # -- keywords (wave 50H) -- 702.192a: paradigm exiles the spell and sets up the copies (app/rules/paradigm.py): the spell's last instruction
    if spell and "Paradigm" in lines:
        lines.append("Set up the paradigm of ~.")
    # -- static_other sweep (wave 16B) -- 702.113a: "Awaken N—[cost]" means "You may cast this spell for [cost]" and "If you cast this spell for
    # its awaken cost, put N +1/+1 counters on target land you control. That land becomes a 0/0 Elemental creature with haste. It's still a
    # land." The cost is the keyword line's (casting: CastSpell.awaken); the effect is read as the spell's own "if kicked" line (the same
    # optional-payment flag the kicker gates read: no card has both)
    if spell:
        for line in list(lines):
            if m := re.fullmatch(r"Awaken (\d+)—(?:\{[^}]+\})+", line):
                lines.append(f"If this spell was kicked, put {m[1]} +1/+1 counters on target land you control. If this spell was kicked, "
                             "that land becomes a 0/0 Elemental creature with haste and it's still a land.")
    # -- static_other sweep (wave 16B) -- 706.3: a results table's rows (one per line) belong to the roll before them
    merged: list[str] = []
    for line in lines:
        if merged and re.match(r"^\d+(?:[—–-]\d+|\+| or less)? \| ", line) and re.search(r"\broll a (?:d\d+|\w+-sided die)\b", merged[-1], re.I) \
                and (not re.search(r"\bactivate only\b", merged[-1], re.I)
                     or (merged[-1].endswith("Activate only as a sorcery.") and merged[-1].lower().count("activate only") == 1)):
            restriction = "Activate only as a sorcery." if merged[-1].endswith("Activate only as a sorcery.") else ""
            merged[-1] = merged[-1].removesuffix(restriction).rstrip() + " " + line + (" " + restriction if restriction else "")
        else:
            merged.append(line)
    lines = merged
    # -- Class (wave 16A) -- 716.2a: "[Cost]: Level N" is "[Cost]: This Class's level becomes N. Activate only if this Class is
    # level N-1 and only as a sorcery."; the lines under it belong to level N (scripts.definitions gates them by the permanent's level)
    sections, level = [], 1
    for i, line in enumerate(lines):
        if (m := re.fullmatch(r"((?:\{[^}]+\})+): Level (\d+)", line)) and not spell:
            lines[i] = (f"{m[1]}: This Class's level becomes {m[2]}. Activate only if this Class is level {int(m[2]) - 1} and "
                        "only as a sorcery.")
            sections.append(level)
            level = int(m[2])
        else:
            sections.append(level)
    # -- linked words (wave 33B) -- 607.2f: "As this enchantment enters, choose Khans or Dragons." and a bulleted line for each word ("• Khans — …"):
    # each bullet is an ability of its own, linked to that choice; the bullet and its word are labels (207.2c), not part of the ability
    linked: dict[int, str] = {}
    for i, line in enumerate(lines[:-2]):
        if (m := _WORDS_HEADER.fullmatch(line)) and not spell and lines[i + 1].startswith(f"• {m[1]} — ") and lines[i + 2].startswith(f"• {m[2]} — ") \
                and m[1] != m[2] and not (i + 3 < len(lines) and lines[i + 3].startswith("•")):
            for j, word in ((i + 1, m[1]), (i + 2, m[2])):
                lines[j], linked[j] = lines[j][len(f"• {word} — "):], word
    tail: list[tuple[str, int]] = []
    for n, line in enumerate(lines):
        # -- keyword meanings (wave 11B) -- 702.107a: "Outlast [cost]" means "[Cost], {T}: Put a +1/+1 counter on this
        # creature. Activate only as a sorcery." (read as that activated ability)
        outlast = False
        if m := re.fullmatch(r"Outlast ((?:\{[^}]+\})+)", line):
            line, outlast = f"{m[1]}, {{T}}: Put a +1/+1 counter on this creature. Activate only as a sorcery.", True
        # -- keyword meanings (wave 17C) -- 702.81a: "Retrace" means "You may cast this card from your graveyard by discarding a land
        # card as an additional cost to cast it." (a permission with an additional cost, 601.2b: permissions.SELF_GY_BY)
        if line == "Retrace":
            line = "You may cast this card from your graveyard by discarding a land card in addition to paying its other costs."
        # -- keyword meanings (wave 18E) -- 702.167a: "Craft with [materials] [cost]" means "[Cost], Exile this permanent, Exile [materials]
        # from among permanents you control and/or cards in your graveyard: Return this card to the battlefield transformed under its
        # owner's control. Activate only as a sorcery." (one cost part for each material description, costs._CRAFT)
        if (m := re.fullmatch(r"Craft with (?P<mats>.+?) (?P<cost>(?:\{[^}]+\})+)", line)) and not spell:
            pieces = re.split(r", (?:and )?", m["mats"]) if re.match(r"(?:a|an) ", m["mats"]) else [m["mats"]]
            pieces = [p if re.match(r"(?:a|an|one|two|three|four|five|six|seven|\d+) ", p) or p == "one or more"
                      else ("an " if p[:1].lower() in "aeiou" else "a ") + p for p in pieces]
            exiles = ", ".join(f"Exile {p}{CRAFT_FROM}" for p in pieces)
            line = (f"{m['cost']}, Exile this permanent, {exiles}: Return this card to the battlefield transformed under its owner's "
                    "control. Activate only as a sorcery.")
        # -- keyword meanings (wave 18E) -- 702.133a: "Jump-start" means "You may cast this card from your graveyard by discarding a card as
        # an additional cost to cast it" and "If this spell was cast using its jump-start ability, exile this card instead of putting
        # it anywhere else any time it would leave the stack." (a permission with an additional cost, as retrace's; ``exile``)
        if line == "Jump-start":
            line = "You may cast this card from your graveyard by discarding a card in addition to paying its other costs. Then exile this card."
        # -- keyword meanings (wave 12B) -- 702.97a: "Scavenge [cost]" means "[Cost], Exile this card from your graveyard: Put a
        # number of +1/+1 counters equal to the power of the card you exiled on target creature. Activate only as a sorcery."
        if m := re.fullmatch(r"Scavenge ((?:\{[^}]+\})+)", line):
            line = (f"{m[1]}, Exile this card from your graveyard: Put X +1/+1 counters on target creature, where X is this "
                    "creature's power. Activate only as a sorcery.")  # (X: the exiled card's power, as it last existed)
        # -- static_other sweep (wave 16B) -- 702.77a: "Reinforce N—[cost]" means "[Cost], Discard this card: Put N +1/+1 counters on
        # target creature." (an activated ability that works only from the hand)
        if m := re.fullmatch(r"Reinforce (\d+|X)—((?:\{[^}]+\})+)", line):  # (-- xdamage (wave 100E) -- X: the X paid, 107.3a)
            line = f"{m[2]}, Discard this card: Put {m[1]} +1/+1 counters on target creature."
        # -- wave 110F -- Circling Vultures: 116.2e special action (casting.VULTURES handles it: no stack); the line is only a marker so the card reads as an ability
        if line == "You may discard this card any time you could cast an instant.":
            line = "Discard this card: You gain 0 life."
        # -- wave 110F -- Taste of Paradise: "you may pay {1}{G} any number of times" repeats like multikicker (702.33c) but is not kicker: the keyword line is flagged "any number of times"
        if m := re.fullmatch(r"As an additional cost to cast this spell, you may pay ((?:\{[^}]+\})+) any number of times\.", line):
            line = f"Multikicker {m[1]} any number of times"
        # -- static_other sweep (wave 19A) -- "Traxos enters tapped and doesn't untap during your untap step.": two abilities, "enters tapped"
        # (614.1d) and the static "doesn't untap" (502.3), the second one added after the printed lines as Reconfigure's are
        if (um := re.fullmatch(r"(.+?) enters tapped and (doesn't untap during your untap step)\.", line)) and not spell:
            line = f"{um[1]} enters tapped."
            tail.append((f"{um[1]} {um[2]}.", sections[n]))
        # -- keyword meanings (wave 49C) -- "{3}, {T} or {R}, {T}: …" (the Shards): one ability payable either way (the rulings: one cost or the other, not both) is read as two
        # activated abilities with the same effect, the second added after the printed lines (the card menu's mapping, as Reconfigure's)
        if (sm := re.fullmatch(r"((?:\{[^}]+\}(?:, )?)+) or ((?:\{[^}]+\}(?:, )?)+): (.+)", line)) and not spell:
            line = f"{sm[1]}: {sm[3]}"
            tail.append((f"{sm[2]}: {sm[3]}", sections[n]))
        if line.startswith("Max speed — ") and not spell:  # -- speed (wave 24B) -- 702.178a: "As long as you have max speed, ~ has …"
            from app.rules import speed

            line = speed.rewrite(line)
        kind, kws, cost = classify(line, spell=spell)
        out.append(AbilityText(index=len(out), text=line, kind=kind, keywords=kws, cost=cost, section=sections[n], linked=linked.get(n),
                               special="outlast" if outlast else None))  # (wave 110B: the keyword's origin, 702.107a)
        # -- keyword meanings (wave 18E) -- 702.151a: "Reconfigure [cost]" is two activated abilities, "[Cost]: Attach this permanent to another
        # target creature you control. Activate only as a sorcery." and "[Cost]: Unattach this permanent. Activate only if this permanent is
        # attached to a creature and only as a sorcery."; 702.151b: attached to a creature, it isn't a creature (a static of its own).
        # (review 18E: added after the printed lines, so a printed line's ability number is its line number — the card menu's mapping)
        from app.rules import activation_alternatives

        if not spell and (reconfigure := activation_alternatives.reconfigure_cost(line)) is not None:
            tail += [(f"{reconfigure}: Attach ~ to another target creature you control. Activate only as a sorcery.", sections[n]),
                     (f"{reconfigure}: Unattach ~. Activate only if ~ is attached to a creature and only as a sorcery.", sections[n]),
                     ("As long as ~ is attached to a creature, ~ isn't a creature.", sections[n])]
    for extra, section in tail:
        ekind, ekws, ecost = classify(extra, spell=spell)
        out.append(AbilityText(index=len(out), text=extra, kind=ekind, keywords=ekws, cost=ecost, section=section))
    return out

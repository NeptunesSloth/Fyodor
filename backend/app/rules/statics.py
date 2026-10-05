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
     "rules": ["<rule>", …],            # rules it imposes (see below); not abilities of the object
     "conditions": [<condition>, …]}    # all must hold; [] for an unconditional static

Conditions: a ``conditions.Condition`` ("you control a Forest", "you have 5 or less life"), or one of
the static-only shapes ``{"static": "your_turn"}``, ``{"static": "self", "test": "attacking" |
"blocking" | "tapped" | "untapped" | "enchanted" | "equipped" | "attacking_alone"}``,
``{"static": "self_counter", "counter": <kind> | None, "op": ">=", "n": N}``, ``{"static":
"graveyard", "op": ">=", "n": N}`` ("there are seven or more cards in your graveyard": threshold,
702.xx wording without the word) and ``{"static": "not", "cond": <condition>}`` ("unless …").

**Rules** (restrictions and requirements, CR 508.1c-d, 509.1b-c, 502.3) are rule-modifying
continuous effects of static abilities: "~ can't be blocked by creatures with power 2 or less.",
"Creatures your opponents control can't block.", "Islands don't untap during their controllers'
untap steps.", "Enchanted creature gets +2/+2 and attacks each combat if able.", "~ must be blocked
if able.", "Cowards can't block Warriors.", "~ can't attack or block unless you control another
Elf.". They land in ``Characteristics.imposed`` (app/rules/layers.py) on whatever the subject
names right now (611.3a: a creature that enters later too) and are read by app/rules/combat.py and
the untap step. The vocabulary (``RULES`` plus parameterised ones, ``name:value``):

    cant_block, cant_attack, cant_attack_or_block, cant_be_blocked, must_attack, must_block,
    must_be_blocked, doesnt_untap, max_one_blocker, cant_attack_alone, cant_block_alone, cant_attack_attacked (wave 19A),
    cant_activate, attack_despite_defender (wave 4B: "can attack as though it didn't have defender"),
    min_blockers:N                         "can't be blocked except by N or more creatures"
    cant_be_blocked_by:<sel>[|<sel>…]       "can't be blocked by artifact creatures"
    cant_be_blocked_except_by:<sel>[|…]     "can't be blocked except by creatures with flying or reach"
    cant_be_blocked_by_power:less|greater   "creatures with power less than ~'s power can't block it"
    cant_be_blocked_if_defender_controls:<sel>   "… as long as defending player controls an artifact"
    cant_block_sel:<sel>[|…]                "can't block creatures with power 3 or greater"
    cant_block_power:greater                "can't block creatures with power greater than ~'s power"
    block_only:<sel>[|…]                    "can block only creatures with flying"
    block_extra:N:<source>                  "can block an additional creature [each combat]" (wave 13B; 509.1a)

A ``<sel>`` is a selector key; ``|`` joins alternatives ("flying or reach"). The selector is
evaluated against the *other* creature in the block, with "you" the rule's source's controller.

Anything not understood parses to None: the ability then stays manual (wrong automation is worse
than none). Applying these in layer order is app/rules/layers.py's job.
"""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Any

from app.rules import conditions, selectors, values

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
    "snow landwalk", "nonbasic landwalk", "legendary landwalk", "artifact landwalk", "snow plainswalk", "snow islandwalk", "snow swampwalk", "snow mountainwalk", "snow forestwalk",  # (wave 12B: 702.14c variants)
    "shadow", "horsemanship", "fear", "intimidate", "skulk", "wither", "infect",
})

# -- static wordings (wave 6E) -- triggered keywords a static may grant (613.1f): granted as the keyword line itself, an
# ability of the object like a printed one (scripts.keyword_triggers: prowess 702.108a, persist 702.79a, undying
# 702.93a; triggers._exalted: exalted 702.83a, each instance triggering separately, 702.83b / 702.108b)
TRIGGERED_GRANTS: frozenset[str] = frozenset({"prowess", "exalted", "persist", "undying",
                                              "mentor", "training", "dethrone", "evolve", "flanking", "battle cry"})  # (wave 15E)
# -- static grants (wave 15A) -- keywords whose whole meaning is one triggered ability (keyword_triggers.MEANINGS): granted as the
# line itself (613.1f). Not modular / graft / living weapon / for mirrodin! / ravenous: those have a half that works as the
# permanent enters (a granted one would miss it).
MEANING_GRANTS = r"extort|ingest|melee|myriad|(?:poisonous|frenzy|afterlife|annihilator|afflict) \d+"

ATTACHED_SUBJECTS = {"enchanted creature": "creature", "equipped creature": "creature", "enchanted land": "land",
                     "enchanted permanent": "permanent", "enchanted artifact": "artifact",
                     "enchanted creatures": None}  # (plural: not a template)
_PT = re.compile(r"^(?P<p>[+−-]\d+)/(?P<t>[+−-]\d+)$")
_BASE = re.compile(r"^base power and toughness (?P<p>\d+)/(?P<t>\d+)$")
_QUOTED = re.compile(r'^"(?P<q>[^"]+)"$')
_DENY = re.compile(r"^(?P<s>(?:Creatures|Permanents) .+? control) lose (?P<kw>[a-z ]+) and can't have or gain (?P=kw)$")  # (10B)
_NUMBERS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}


def _signed(s: str) -> int:
    return int(s.replace("−", "-"))


def _num(word: str) -> int | None:
    return int(word) if word.isdigit() else _NUMBERS.get(word.lower())


# -- the sentence -----------------------------------------------------------------------------
def parse(text: str) -> Definition | None:
    """One static ability sentence (the card's own name already written as ~) → definition, or None."""
    t = text.strip().replace("’", "'").replace("“", '"').replace("”", '"')
    t = t.replace(" your team controls ", " you control ")  # -- static_other sweep (wave 19A) -- 102.4: outside a team game "your team" is you
    # -- attached events (wave 16F) -- "Enchanted permanent can't attack, block, or crew Vehicles. Its activated abilities can't be
    # activated unless they're mana abilities." (Intercessor's Arrest): the two sentences are one static's two rules
    # -- attached events (wave 16F) -- Zendikon: "Enchanted land is a 3/3 black Ooze creature with reach. It's still a land." is
    # 205.1b's "is a black Ooze creature with base power and toughness 3/3 in addition to its other types and has reach"
    # (the land keeps its types and its subtypes: 305.7 only takes the rules text away when a land TYPE is set)
    t = re.sub(r"^(Enchanted land) is an? (\d+)/(\d+) ([^.]+?)(?: with ([^.]+))?\. It's still a land\.$",
               lambda m: f"{m[1]} is a {m[4]} with base power and toughness {m[2]}/{m[3]} in addition to its other types"
                         + (f" and has {m[5]}." if m[5] else "."), t)
    # -- attached events (wave 20A) -- "Enchanted creature is a Citizen with base power and toughness 1/1. It has defender and loses all
    # other abilities." (Spider-Man No More), "… 0/1. It can't attack and loses all abilities." (Retro-Mutation): one static's three parts
    t = re.sub(r"^(Enchanted creature is an? [^.]+? with base power and toughness \d+/\d+)\. It (has [a-z]+|can't attack) and "
               r"(loses all (?:other )?abilities)\.$", r"\1, \2, and \3.", t)
    # (Canopy Cover, Shielding Plax) 702.11b: hexproof is exactly "can't be the target of spells or abilities your opponents control"
    t = re.sub(r"^((?:Enchanted|Equipped) creature) can't be the target of spells or abilities your opponents control\.$", r"\1 has hexproof.", t)
    t = re.sub(r"^(Enchanted land) is an? (\d+)/(\d+) ([^.]+? creature) that's still a land\.$",  # (wave 20A: Living Terrain, the same as Zendikon)
               r"\1 is a \4 with base power and toughness \2/\3 in addition to its other types.", t)
    t = t.replace(" be activated unless they're mana abilities", " be activated-nonmana")  # ("unless" is not a condition here)
    t = re.sub(r"(?<=Vehicles)\. Its (activated abilities can't be activated-nonmana\.)$", r", and its \1", t)
    if not t.endswith(".") and not t.endswith('."'):
        return None
    if re.sub(r'"[^"]*"', "", t).count(". ") or "\n" in t:  # (wave 16F: sentences inside a quoted granted ability are its own)
        return None  # two sentences: one of them says something we'd silently drop
    body = t[:-1] if t.endswith(".") else t
    if re.fullmatch(r"A deck can have (?:any number of|up to \w+) cards named ~", body):
        return {"kind": "static", "static": "deck_rule", "effects": []}  # -- static grants (wave 15A) -- 100.2a / 903.5b: deck building only
    cda = parse_cda(body)
    if cda is not None:
        return cda
    # -- small wordings (wave 11E) -- "This creature is the chosen type in addition to its other types." (Metallic Mimic):
    # layer 4 (613.1d, 205.1b), the creature type chosen as it entered (layers._own_layer4 reads it, chosen.chosen_value_ok)
    if body == "~ is the chosen type in addition to its other types":
        return {**_definition("self", None, []), "remove_types": [], "add_subtypes": [], "chosen_type": True}
    # -- untap choice (wave 7F) -- 502.3: asked in the untap step (app/rules/untap_choice.py)
    if body == "You may choose not to untap ~ during your untap step":
        return _definition("self", None, [], rules=["may_stay_tapped"])
    # -- dynamic values (agent F): "~ gets +X/+X, where X is …" (the X of a static is defined by its text)
    x_phrase: str | None = None
    m = re.match(r"^(?P<rest>.+), where X is (?P<x>.+)$", body)
    if m and m["rest"].count('"') % 2 == 0:  # (not inside a quoted granted ability)
        x_phrase, body = m["x"], m["rest"]
    # -- static statics (wave 10B) -- "Creatures your opponents control lose flying and can't have or gain flying."
    # (the Archetypes): lose it now (613.1f, in timestamp order) and never have or gain it (the deny is applied last)
    m = _DENY.fullmatch(body)
    if m is not None and m["kw"] in GRANTABLE_KEYWORDS:
        who, kind = _subject(m["s"], plural=True)
        if who is None or who == "self" or who.startswith(UNION):
            return None
        return {**_definition(who, kind, []), "lose_keywords": [m["kw"]], "deny_keywords": [m["kw"]]}
    # "Creatures with power less than ~'s power can't block it." (Wandering Wolf): an evasion ability
    # of the source, worded from the blockers' side.
    m = re.fullmatch(r"Creatures with power (?P<dir>less|greater) than ~'s power can't block it", body)
    if m:
        return _definition("self", None, [], rules=[f"cant_be_blocked_by_power:{m['dir']}"])
    # -- lure (wave 12B) -- "All creatures able to block ~ do so." / "…, and all creatures able to block it do so." (Lure,
    # Nemesis Mask): every creature able to block it must (509.1c) — the rule "lure" on the attacker
    body = re.sub(r"^All (?P<w>[A-Za-z ]+?) able to block (?P<o>~|this creature|enchanted creature|equipped creature) do so$",
                  lambda m: f"{'~' if m['o'] in ('~', 'this creature') else m['o'].capitalize()} must be blocked by all {m['w']} able",
                  body)
    body = re.sub(r"(?P<sep>, and| and|,) all creatures able to block it do so$", r"\g<sep> must be blocked by all creatures able", body)
    # -- borrowed abilities (wave 18F) -- "As long as ~ is on the battlefield, …": a static of a permanent works there only (611.3b)
    body = re.sub(r"^As long as (?:~|it) is on the battlefield, ", "", body)
    conds: list[dict[str, Any]] = []
    names_source = False  # -- conditional statics (wave 4B) -- the condition names the source as "~", not "it"
    defender_sel: str | None = None  # "… as long as defending player controls an artifact"
    rule_cond = False  # "unless …" / "if …": conditions only restrictions are worded with
    # "During your turn, …" / "As long as <condition>, …" / "… as long as <condition>"
    m = re.match(r"^(?:During your turn|As long as it's your turn), (?P<rest>.+)$", body)
    m = m or re.match(r"^(?P<rest>.+? (?:has|have|gets?) .+) during your turn$", body)  # (wave 15A: "~ has first strike during your turn")
    if m:
        conds.append({"static": "your_turn"})
        body = m["rest"]
    else:
        # -- conditional statics (wave 4B) -- the subject after the condition may be any group ("As long as
        # ~ has seven or more quest counters on it, creatures you control get +5/+5.")
        m = re.match(r"^As long as (?P<cond>.+?), (?P<rest>(?:~|it|[A-Z]|[a-z]+ ).+)$", body)
        if m:
            cond = _condition(m["cond"])
            if cond is None:
                return None
            conds.append(cond)
            body = m["rest"]
            names_source = _names_source(m["cond"])
        else:
            m = re.match(r"^(?P<rest>.+?) as long as defending player controls an? (?P<sel>.+)$", body)
            if m:
                defender_sel = _sel_key(m["sel"], plural=False)
                if defender_sel is None:
                    return None
                body = m["rest"]
            else:
                # (-- trigger tail (wave 15B) -- a condition inside a quoted granted ability is that ability's own: masked here)
                masked = re.sub(r'"[^"]*"', lambda q: "\0" * len(q[0]), body)
                m = re.match(r"^(?P<rest>.+?) (?:as long as|(?P<r>unless|if)) (?P<cond>(?!able\b).+)$", masked)
                if m:
                    cond_text, rest_text = body[m.start("cond"):m.end("cond")], body[m.start("rest"):m.end("rest")]
                    # -- attached events (wave 16F) -- "Enchanted creature gets +1/+2 as long as it's white": "it" is the creature the
                    # static modifies (the object attached to), as in "As long as enchanted creature is white, it gets +1/+2"
                    host = re.match(r"(?P<w>Enchanted|Equipped) (?P<n>creature|permanent|land|artifact) (?:gets?|ha(?:s|ve)) ", rest_text)
                    it_is = re.fullmatch(r"it(?:'s| is) (?P<d>.+)", cond_text)
                    if host and it_is:
                        cond_text = f"{host['w'].lower()} {host['n']} is {it_is['d']}"
                    cond = _condition(cond_text)
                    if cond is None:
                        return None
                    names_source = _names_source(cond_text)  # -- conditional statics (wave 4B) --
                    if m["r"]:
                        rule_cond = True
                        if m["r"] == "unless":
                            cond = {"static": "not", "cond": cond}
                    conds.append(cond)
                    body = rest_text
    outside = re.sub(r'"[^"]*"', "", body)  # (wave 16F: a condition inside a quoted granted ability is that ability's own)
    if " as long as " in outside or " unless " in outside or body.startswith(("As long as", "During ", "If ", "if ")):
        return None
    # -- conditional statics (wave 4B) -- "Creatures you control also get +1/+0 and have trample as long as …"
    # (Jetmir: "also" only says the effect adds to the line before it)
    body = re.sub(r"^(?P<s>[A-Z][\w' ]*?) also (?P<v>gets?|ha(?:s|ve)) ", r"\g<s> \g<v> ", body)
    body = re.sub(r"^(?P<s>it|~) gets an additional (?P<pt>[+−-]\d+/[+−-]\d+)$", r"\g<s> gets \g<pt>", body)  # (Bladed Pinions-style)
    # -- ability words (wave 9C) -- "Enchanted creature gets an additional +2/+2 as long as …" (Strange Augmentation, Divine
    # Sacrament, Taste for Mayhem): "additional" only says the modification adds to the line before it; a P/T bonus of
    # layer 7c adds to the others either way (613.4c)
    body = re.sub(r"\b(?P<v>gets?) an additional (?=[+−-]\d+/[+−-]\d+)", r"\g<v> ", body)
    # layer 4 (613.1d) on the source itself: "~ isn't a creature" (Theros gods), "… and is a Knight in addition to
    # its other types" (205.1b)
    # -- attached events (wave 4L) -- "Enchanted creature … is an Angel in addition to its other types": the attached
    # object's own types (app/rules/attached_types.py), not the source's
    attached_body = re.match(r"(?:enchanted|equipped) (?:creature|permanent|land) ", body, re.I) is not None
    layer4 = None if attached_body else _layer4_parts(body)
    if layer4 is not None:
        if defender_sel or rule_cond or x_phrase is not None or not conds or not all(_layer4_safe(c) for c in conds):
            return None
        body, type_parts = layer4
        if not body:
            return {**_definition("self", None, conds), **type_parts}
    attached_cond = next((c for c in conds if c.get("static") == "attached_is"), None)
    if attached_cond is not None and re.match(r"it (?:gets?|has|can't|attacks|blocks|must|doesn't)\b", body):
        # "As long as equipped creature is legendary, it has hexproof.": "it" is the object the condition names
        body = f"{attached_cond['who'].capitalize()} {attached_cond['noun']}{body[2:]}"
    subject, predicate = _split_subject(body)
    # -- attached events (wave 4L) -- "Enchanted creature loses all abilities and is a …" (verbs the split doesn't know)
    m = re.match(r"(?P<s>(?:Enchanted|Equipped) (?:creature|permanent|land)) (?P<p>(?:loses|is) .+)$", body)
    if m is not None:
        subject, predicate = m["s"], m["p"]
    if subject is None or predicate is None:
        return None
    # -- token & pump wordings (wave 6C) -- a plural verb ("get", "have") says the subject is a group even when its noun
    # is the same in both numbers ("Other Merfolk you control get +1/+1.")
    who, kind = _subject(subject, plural=re.match(r"(?:get|have) ", predicate) is not None)
    if who is None:
        return None
    if who != "attached" and any(_mentions(c, ("attached_stat", "attached_ctrl")) for c in conds):
        return None  # -- attached events (wave 16F) -- "its power / its controller" names the object an Aura or Equipment is on
    if who.startswith(UNION) and (conds or x_phrase is not None or defender_sel or rule_cond):
        return None  # -- static wordings (wave 6E) -- (a union subject: only plain grants)
    if layer4 is not None and who != "self":
        return None
    if attached_cond is not None and (who != "attached" or (kind or attached_cond["noun"]) != attached_cond["noun"]):
        return None  # (the condition and the subject name the same attached object)
    if who != "self" and not names_source and any(c.get("static") in ("self", "self_counter", "designation") for c in conds):
        return None  # "it's attacking" means the source; a group subject would need "each … that's attacking"
    # "counters on it": "it" is the source only when the source is the subject ("~ gets …"); for
    # "Equipped creature gets +1/+1 for each counter on it" it's the equipped creature (not read)
    it = "self" if who == "self" else None
    x_value = values.parse_count(x_phrase, it=it) if x_phrase is not None else None
    if x_value is None and who == "attached" and x_phrase == "its mana value":
        x_value = {"relative": "mana_value"}  # -- attached events (wave 20A) -- the host's own (Hedron Matrix), read per object (611.3a)
    if x_phrase is not None and x_value is None:
        return None
    parts = _predicate(predicate, x_value, it)
    if parts is None:
        return None
    if who.startswith(UNION) and (parts["rules"] or parts["each"] or parts["extra"]):
        return None  # -- static wordings (wave 6E) -- (a union subject: only P/T, keyword and ability grants)
    # -- attached events (wave 4L) --
    from app.rules import attached_types

    extra = parts.pop("extra")
    # -- ability words (wave 9C) -- "As long as there are seven or more cards in your graveyard, this creature gets +1/+1, is
    # black, and has "…"" (Possessed Aven): its own color (layer 5, 613.1e) under a condition about the graveyard or the
    # players, which never reads the colors of what it modifies (layers._own_layer5)
    own_colors = bool(extra) and who == "self" and set(extra) == {"set_colors"} and bool(conds) \
        and all(_color_safe(c) for c in conds) and x_value is None and not defender_sel and not rule_cond
    if extra and not own_colors and (who != "attached" or conds or x_value is not None or defender_sel or rule_cond):
        return None  # (layers 4-6 parts of a static: only an Aura's or Equipment's, unconditional)
    if extra and not own_colors and not attached_types.consistent(extra, kind):
        return None
    if x_value is not None and parts["each"] is None:
        return None  # ("where X is …" with no X in the sentence)
    if who == "self" and not conds and not parts["rules"] and parts["each"] is None and parts["abilities_of"] is None:
        return None  # "~ has flying." unconditionally is a keyword line, not a static: not a template
    if rule_cond and not parts["rules"]:
        return None  # "~ gets +1/+1 if …" isn't how a static grant is worded
    if who != "self" and any(_relative(sel) for r in parts["rules"] for sel in rule_selectors(rule_arg(r)[1])):
        return None  # "Blue creatures can't block creatures you control": the rule, once on a blue creature, has lost "you"
    if defender_sel is not None:
        if parts["rules"] != ["cant_be_blocked"] or parts["p"] or parts["t"] or parts["keywords"] or parts["grants"] \
                or parts["each"]:
            return None
        parts["rules"] = [f"cant_be_blocked_if_defender_controls:{defender_sel}"]
    if who in ("self", "attached") and any(_zone_of(c) for c in conds):
        return None  # -- conditional statics (wave 4B) -- a card in a graveyard is no permanent to grant to
    if layer4 is not None:
        return {**_definition(who, kind, conds, **parts), **layer4[1]}
    if extra:  # -- attached events (wave 4L) --
        return {**_definition(who, kind, conds, **parts), **extra}
    return _definition(who, kind, conds, **parts)


# -- conditional statics (wave 4B) ----------------------------------------------------------------------------
_NOT_CREATURE = re.compile(r"^(?:~|it) isn't a creature$")
_IN_ADDITION = re.compile(r"^(?:(?P<pre>.+?),? and |(?:~|it) )is (?:a|an) (?P<sub>[A-Z][a-z]+) in addition to its other types$")


def _names_source(cond: str) -> bool:
    """The condition names the source as "~" ("~ has seven or more quest counters on it", "there are five or more
    growth counters on ~"), not with a bare "it" a group subject could claim."""
    return "~" in cond and not re.match(r"it\b|it's\b", cond)


def _layer4_parts(body: str) -> tuple[str, dict[str, Any]] | None:
    """Layer-4 parts of a static of the source itself (613.1d): "~ isn't a creature" (removes the card type,
    and with it the creature types, 205.3d) and "is a Knight in addition to its other types" (205.1b: adds a
    creature type). → (the rest of the predicate, or "" when nothing is left; the definition keys)."""
    if _NOT_CREATURE.fullmatch(body):
        return "", {"remove_types": ["Creature"], "add_subtypes": []}
    m = _IN_ADDITION.fullmatch(body)
    if m:
        from app.rules.creature_types import CREATURE_TYPES

        if m["sub"] not in CREATURE_TYPES:
            return None
        return (m["pre"] or ""), {"remove_types": [], "add_subtypes": [m["sub"]]}
    return None


def _layer4_safe(cond: dict[str, Any]) -> bool:
    """A layer-4 static's condition must not read characteristics (it is applied while they are being derived,
    for every reader: 613.8 dependencies on other objects' types aren't modelled): the source's counters, devotion
    (700.5a: mana costs after copy effects only), life totals, whose turn it is."""
    if cond.get("static") in ("self_counter", "your_turn", "life_vs_start", "opp_life"):
        return True
    if cond == {"static": "self", "test": "attached_to_a_creature"}:  # -- casting extras (wave 18E) -- reconfigure 702.151b
        return True
    value = cond.get("value")
    return cond.get("static") is None and isinstance(value, dict) and set(value) == {"devotion"}


def _color_safe(cond: dict[str, Any]) -> bool:
    """-- ability words (wave 9C) -- may a condition gate the source's own color change? It is read while the source's colors
    are being derived, so it must not read colors (613.8): cards in graveyards (their own characteristics, not the
    battlefield's), counts of card types among them, player counters, life, whose turn it is."""
    if cond.get("static") in ("graveyard", "your_turn", "life_vs_start", "opp_life", "opp_graveyard", "self_counter"):
        return True
    value = cond.get("value")
    if cond.get("static") is None and isinstance(value, dict):
        if set(value) == {"player_counters"}:
            return True
        return value.get("distinct") == "types" and "graveyard" in str(value.get("among"))
    return False


def _zone_of(cond: dict[str, Any]) -> bool:
    return cond.get("static") == "zone" or (cond.get("static") == "all" and any(_zone_of(c) for c in cond["conds"]))


def zone_static(d: Definition) -> bool:
    """Does the static function from its owner's graveyard ("As long as this card is in your graveyard, …",
    113.6b) rather than from the battlefield?"""
    return any(_zone_of(c) for c in d.get("conditions") or ())


def _definition(who: str, kind: str | None, conds: list[dict[str, Any]], *, p: int = 0, t: int = 0,
                base: list[int] | None = None, keywords: list[str] | None = None, grants: list[str] | None = None,
                rules: list[str] | None = None, each: dict[str, Any] | None = None,
                abilities_of: dict[str, Any] | None = None) -> Definition:
    out: Definition = {"kind": "static", "static": "grant", "effects": [], "who": who, "attached_kind": kind,
           "conditions": conds, "p": p, "t": t, "base": base, "keywords": keywords or [], "grants": grants or [],
           "rules": rules or []}
    if each is not None:
        out["each"] = each
    if abilities_of is not None:  # -- borrowed abilities (wave 18F) --
        out["abilities_of"] = abilities_of
    return out


# -- dynamic values (agent F): "gets +N/+N for each …", characteristic-defining P/T ---------------
_PT_EACH = re.compile(r"^(?P<p>[+−-]\d+)/(?P<t>[+−-]\d+) for each (?P<each>.+)$")
_PT_X = re.compile(r"^(?P<p>[+−-])X/(?P<t>[+−-])(?P<t2>X|0)$|^(?P<p2>[+−-])0/(?P<t3>[+−-])X$")
_CDA = re.compile(r"^(?:[A-Z][a-z]+ — )?~'s (?:(?P<both>power and toughness are each)|(?P<power>power is)|"
                  r"(?P<toughness>toughness is)) equal to (?P<v>.+?)"
                  r"(?: and its toughness is equal to that number plus (?P<plus>\d+))?$")


def _each_part(rest: str, x_value: values.Value | None, it: str | None) -> dict[str, Any] | None:
    """"+1/+0 for each artifact you control" / "+X/+X" (with the sentence's "where X is …") → the
    dynamic part of a 7c modification (613.4c): ``{"p": ±k, "t": ±k, "value": <value>}`` — the
    object gets p×value / t×value, read whenever its characteristics are (611.3a). None if it
    isn't one.

    Definition key ``each`` on a grant static; app/rules/layers.py applies it in layer 7c."""
    m = _PT_EACH.match(rest)
    if m and (rel := _relative_count(m["each"])) is not None:  # -- token & pump wordings (wave 6C) --
        return {"p": _signed(m["p"]), "t": _signed(m["t"]), "value": rel}
    if m:
        v = values.parse_count(m["each"], it=it)  # ("counters on it": on the source, when ~ is the subject)
        if v is None:  # -- attached events (wave 8D) -- "Equipped creature gets +1/+1 for each Aura and Equipment attached to it"
            v = _attached_relative(m["each"])
        if v is None:
            return None
        return {"p": _signed(m["p"]), "t": _signed(m["t"]), "value": v}
    m = _PT_X.match(rest)
    if m and x_value is not None:
        if m["p2"]:  # "+0/+X"
            return {"p": 0, "t": 1 if m["t3"] == "+" else -1, "value": x_value}
        p = 1 if m["p"] == "+" else -1
        t = 0 if m["t2"] == "0" else (1 if m["t"] == "+" else -1)
        return {"p": p, "t": t, "value": x_value}
    return None


# -- token & pump wordings (wave 6C) -- a count relative to the object the static modifies (613.4c, read for each one,
# 611.3a): "Each creature gets +1/+1 for each other creature on the battlefield that shares at least one creature type
# with it" (Coat of Arms: 205.3m creature types, a changeling has them all, 702.73a), "Each nontoken creature you control
# gets +1/+1 for each other creature you control with the same name as that creature" (Mirror Box; 201.2)
_SHARING = re.compile(r"^(?P<sel>other .+?) that shares? (?:at least one|a) creature type with it$")  # (wave 8D: "a")
_SAME_NAME = re.compile(r"^(?P<sel>other .+?) with the same name as that creature$")


def _attached_relative(each: str) -> dict[str, Any] | None:
    """-- attached events (wave 8D) -- 301.5, 303.4: the Auras / Equipment attached to the object the static modifies (the
    host of an Aura or Equipment: "it"), read for it whenever its characteristics are (611.3a)."""
    m = re.fullmatch(r"(?P<kinds>Aura|Equipment|Aura (?:and|or|and/or) Equipment) attached to it", each)
    return {"relative": "attached", "kinds": sorted(set(re.findall(r"Aura|Equipment", m["kinds"])))} if m else None


def _relative_count(each: str) -> dict[str, Any] | None:
    if each == "of its colors":  # -- attached events (wave 16F) -- 105.1: the colors of the object modified (Civic Saber)
        return {"relative": "colors"}
    m = _SHARING.match(each) or _SAME_NAME.match(each)
    if m is None:
        return None
    sel = selectors.parse(re.sub(r" on the battlefield$", "", m["sel"]))
    if sel is None or sel.player is not None or sel.zones != ("battlefield",) or sel.card or not sel.other:
        return None
    return {"relative": "creature_type" if m.re is _SHARING else "name", "among": sel.key()}


def parse_cda(body: str) -> Definition | None:
    """A characteristic-defining ability setting power and/or toughness (604.3, 604.3a): "~'s
    power and toughness are each equal to the number of lands you control", "~'s power is equal
    to the number of cards in your hand", "Domain — ~'s power is equal to the number of basic land
    types among lands you control", "~'s power is equal to the number of card types among cards in
    all graveyards and its toughness is equal to that number plus 1". Applied in layer 7a
    (613.4a), in every zone (604.3) — app/rules/layers.py. Definition: ``{"kind": "static",
    "static": "cda", "p": <value> | None, "t": <value> | None}``."""
    m = _CDA.match(body)
    if m is None:
        return None
    v = values.parse_count(m["v"], it="self")
    if v is None:
        return None
    if m["plus"]:
        if not m["power"]:
            return None
        return {"kind": "static", "static": "cda", "effects": [], "p": v, "t": {"plus": [v, int(m["plus"])]}}
    both = bool(m["both"])
    return {"kind": "static", "static": "cda", "effects": [], "p": v if both or m["power"] else None,
            "t": v if both or m["toughness"] else None}


def _split_subject(body: str) -> tuple[str | None, str | None]:
    """"Other Elves you control get +1/+1 and have haste" → ("Other Elves you control", "get +1/+1 and
    have haste"): the subject ends before the first verb (get / have, or a restriction's can't /
    can / attack(s) / block(s) / must / don't / doesn't)."""
    goaded = re.fullmatch(r"(?P<s>.+?) (?P<p>(?:is|are) goaded)", body)  # -- wave 3F -- 701.15b
    if goaded and not re.search(r"\b(?:gets?|ha(?:s|ve)|can't|can|attacks?|blocks?|must|don't|doesn't)\b", goaded["s"]):
        return goaded["s"], goaded["p"]
    m = re.search(r"\b(?:gets?|ha(?:s|ve)|can't|can|attacks?|blocks?|must|don't|doesn't|assigns?(?= combat damage)|crews(?= Vehicles))\b", body)  # (assigns: wave 6E; crews: 17C)
    if m is None or m.start() == 0:
        return None, None
    return body[: m.start()].strip(), body[m.start():].strip()


# -- token & pump wordings (wave 6C) -- "Other Wolves and Werewolves you control", "Skeletons, Vampires, and Zombies you
# control": a list of creature types joined by "and" names each creature with any of them (the same group as "Wolves
# or Werewolves")
_TYPE_LIST = re.compile(r"^(?P<pre>(?:[Oo]ther |[Aa]ll )?)(?P<list>[A-Z][a-z'\-]+(?:, [A-Z][a-z'\-]+)*,? and [A-Z][a-z'\-]+)"
                        r"(?P<post> you control)?$")


def _type_list(subject: str) -> str:
    from app.rules.creature_types import CREATURE_TYPES
    from app.rules.protection import _PLURALS

    m = _TYPE_LIST.match(subject)
    if m is None:
        return subject
    words = re.split(r",? and |, ", m["list"])
    for w in words:
        one = _PLURALS.get(w.lower()) or (w[:-1] if w.endswith("s") else w)
        if one not in CREATURE_TYPES and w not in CREATURE_TYPES:
            return subject
    return f"{m['pre']}{' or '.join(words)}{m['post'] or ''}"


# -- static wordings (wave 6E) -- two groups joined by "and", each its own selector: "Skeletons you control and other
# Zombies you control" (Death Baron: "other" belongs to the Zombies only, so a Skeleton Death Baron would pump itself),
# "Goblins you control and Elementals you control", "Other Treefolk and Forests you control". The static applies to an
# object in either group (``UNION`` + the selector keys; ``applies``), once.
UNION = "any:"
_UNION_TWO = re.compile(r"^(?P<a>.+? you control) and (?P<b>(?:other )?[A-Za-z][\w' -]*? you control)$")
_UNION_SHARED = re.compile(r"^(?P<pre>[Oo]ther )?(?P<a>[A-Z][a-z'\-]+) and (?P<b>[A-Z][a-z'\-]+) you control$")


_EACH_TWO = re.compile(r"^(?P<d>Each|All) (?P<a>[A-Za-z][\w'-]*(?: [a-z][\w'-]*)?) and (?P<b>[A-Za-z][\w'-]*(?: [a-z][\w'-]*)?) you control$")


def _union_subject(subject: str) -> str | None:
    m = _UNION_TWO.match(subject)
    parts = [m["a"], m["b"]] if m else None
    if parts is None and (e := _EACH_TWO.match(subject)) is not None and e["d"] == "Each":  # -- static_other sweep (wave 17C) --
        parts = [f"Each {e['a']} you control", f"Each {e['b']} you control"]  # "Each land and Ally you control has …"
    if parts is None and (m := _UNION_SHARED.match(subject)) is not None and _type_list(subject) == subject:
        parts = [f"{m['pre'] or ''}{m['a']} you control", f"{m['pre'] or ''}{m['b']} you control"]
    if parts is None:
        return None
    keys = []
    for part in parts:
        if " and " in part:
            return None
        key, _ = _subject(part[0].upper() + part[1:], plural=True)
        if key is None or not key.startswith(selectors.PREFIX) or "keywords" in key:
            return None
        keys.append(key)
    return UNION + json.dumps(keys)


def _union_keys(who: str) -> list[str]:
    return list(json.loads(who[len(UNION):]))


def _subject(subject: str, *, plural: bool = False) -> tuple[str | None, str | None]:
    """→ ("self" | "attached" | selector key, attached kind). ``plural``: the verb is plural (wave 6C)."""
    union = _union_subject(subject)  # -- static wordings (wave 6E) --
    if union is not None:
        return union, None
    subject = _type_list(subject)  # -- token & pump wordings (wave 6C) --
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
    if not each and not plural and not selectors.is_plural(phrase):
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
    predicate = predicate.replace("can't attack, block, or crew Vehicles", "can't attack,_block,_or_crew_Vehicles")  # (wave 16F)
    predicate = predicate.replace("Aura and Equipment", "Aura_and_Equipment")  # (wave 6C: one count, values._ATTACHED_TO)
    predicate = re.sub(r"(for each [^,\"]*?) and each ", r"\1 and_each ", predicate)  # (wave 15A: one sum, values._parse_count)
    # -- X sized by a count (wave 19F) -- "for each Dwarf, Equipment, and/or Vehicle you control": one count of a list of kinds
    predicate = re.sub(r"for each [\w'-]+(?:, [\w'-]+)*,? (?:and/or|and|or) [\w'-]+ you control", lambda m: m.group(0).replace(" ", "\x00"), predicate)
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
    return [p.replace("power_and_toughness", "power and toughness").replace("Aura_and_Equipment", "Aura and Equipment")
            .replace(" and_each ", " and each ").replace("attack,_block,_or_crew_Vehicles", "attack, block, or crew Vehicles")
            .replace("\x00", " ") for p in out if p]


def _predicate(predicate: str, x_value: values.Value | None = None, it: str | None = None) -> dict[str, Any] | None:
    """"get +1/+1 and have haste" / "has base power and toughness 2/2" / "have "{T}: Add {G}."" →
    the P/T, base, keyword and ability parts (any that are absent are empty)."""
    from app.rules.scripts import granted_ability  # (scripts imports this module)

    p = t = 0
    base: list[int] | None = None
    keywords: list[str] = []
    grants: list[str] = []
    rules: list[str] = []
    each: dict[str, Any] | None = None
    lent: dict[str, Any] | None = None  # -- borrowed abilities (wave 18F) --
    verb: str | None = None
    # -- attached events (wave 4L) -- "protection from black and from green" is one keyword (702.16g): not split
    if "protection from " in predicate and '"' not in predicate:
        predicate = re.sub(r"(?:,| and|, and) from ", _FROM_JOIN, predicate)
    # -- attached events (wave 4L) --
    from app.rules import attached_types

    extra: dict[str, Any] = {}
    predicate = attached_types.protect(predicate)
    predicate = predicate.replace("instant and sorcery card", "instant or sorcery card")  # -- attached events (wave 20A) -- one noun phrase, not two pieces
    for piece in _pieces(predicate):
        rule = _rule(piece)
        if rule is not None:
            rules.extend(r for r in rule if r not in rules)
            continue
        # -- attached events (wave 4L) -- "loses flying", "loses all abilities", "is a green Elk creature with base
        # power and toughness 3/3", "is legendary": layers 4-6 (app/rules/attached_types.py)
        found = attached_types.piece(piece, extra)
        if found is not None:
            if found is False:
                return None
            if isinstance(found, list):
                if base is not None:
                    return None
                base = found
            verb = "is"
            continue
        m = re.match(r"^(?P<verb>gets?|ha(?:s|ve)) (?P<rest>.+)$", piece)
        if m:
            verb, rest = ("get" if m["verb"].startswith("get") else "have"), m["rest"]
        elif verb is None or verb == "is":
            return None
        else:
            rest = piece  # "has flying and vigilance": the verb carries over
        if verb == "get":
            pt = _PT.match(rest)
            if pt is None:
                if each is not None:
                    return None  # (two dynamic parts: not a template)
                each = _each_part(rest, x_value, it)
                if each is None:
                    return None
                continue
            p += _signed(pt["p"])
            t += _signed(pt["t"])
            continue
        b = _BASE.match(rest)
        if b:
            if base is not None:
                return None
            base = [int(b["p"]), int(b["t"])]
            continue
        if rest.startswith("all activated abilities of "):  # -- borrowed abilities (wave 18F) -- app/rules/abilities_of.py
            from app.rules import abilities_of

            found_lent = abilities_of.parse(rest)
            if found_lent is None or lent is not None or verb != "have":
                return None
            lent = found_lent
            continue
        q = _QUOTED.match(rest)
        if q:
            text = q["q"] if q["q"][-1] in ".)" else q["q"] + "."  # (wave 16F: a quote ending a clause has no period of its own)
            if granted_ability(text) is None:
                return None
            grants.append(text)
            continue
        if rest in GRANTABLE_KEYWORDS:
            keywords.append(rest)
            continue
        if rest in TRIGGERED_GRANTS or rest == "riot" or re.fullmatch(MEANING_GRANTS, rest):  # -- static wordings (wave 6E) --
            # (wave 17C: riot is read from the entering permanent's characteristics as it enters, 614.12: app/rules/riot.py)
            grants.append(rest.capitalize())  # (wave 15A: "have extort", "have afflict 2": their CR meaning, keyword_triggers)
            continue
        line = keyword_line(rest.replace(_FROM_JOIN, " and from "))  # -- attached events (wave 4L) --
        if line is not None:
            grants.append(line)
            continue
        return None
    if not (p or t or base or keywords or grants or rules or each or extra or lent):
        return None
    return {"p": p, "t": t, "base": base, "keywords": keywords, "grants": grants, "rules": rules, "each": each,
            "extra": extra, "abilities_of": lent}


# -- attached events (wave 4L) ---------------------------------------------------------------------------------
# Keyword abilities with a parameter a static may grant ("Equipped creature gets +2/+2 and has protection from black
# and from green.", "… has lifelink and ward {2}.", "… has toxic 2."): granted as the keyword line itself (layer 6,
# 613.1f), which the engine reads wherever it reads printed ones: protection (702.16, app/rules/protection.py:
# targeting, blocking, damage, attachments), ward (702.21a: each instance triggers, triggers.ward_costs), toxic
# (702.164: combat.py). Only qualities and costs the engine enforces (coverage._keyword_supported).
_FROM_JOIN = "\u0001from "
_PARAM_KEYWORDS = ("protection", "ward", "toxic", "annihilator", "afflict", "poisonous", "bushido", "mobilize", "frenzy",
                   "soulshift", "afterlife", "crew", "equip")  # (wave 15E: keywords whose line is carried out wherever it is: keyword_triggers; 17C: crew, equip)


def keyword_line(rest: str) -> str | None:
    """"protection from creatures" / "ward {2}" / "toxic 1" → the keyword line to grant ("Protection from
    creatures"), or None."""
    from app.rules.coverage import _keyword_supported  # (coverage imports this module through scripts)

    word = "ward" if rest.startswith("ward—") else rest.split(" ", 1)[0]
    # -- static_other sweep (wave 17C) -- "Ward—Pay 2 life." / "Ward—{2}, Pay 2 life.": a ward cost that isn't just mana (triggers.ward_piece_cost)
    if not (word in _PARAM_KEYWORDS and re.fullmatch(r"[a-z]+ [\w{}, ]+", rest)) and not re.fullmatch(r"ward—[\w{}, ]+", rest):
        return None
    line = rest[0].upper() + rest[1:]
    return line if _keyword_supported(word, line) else None


# -- rules (restrictions and requirements) ----------------------------------------------------
# Wordings with nothing to parameterise (singular and plural verb forms: "~ can't block." and
# "Creatures your opponents control can't block."). CR 508.1c-d (attack), 509.1b-c (block), 502.3
# (untap), 702.111b-style "except by N or more creatures" is a min_blockers:N rule instead.
RULES: dict[str, tuple[str, ...]] = {
    "can't block": ("cant_block",),
    "can't attack": ("cant_attack",),
    "can't attack or block": ("cant_attack_or_block",),
    "can't be blocked": ("cant_be_blocked",),
    "can't attack alone": ("cant_attack_alone",),
    "can't block alone": ("cant_block_alone",),
    "can't attack a player it has already attacked this turn": ("cant_attack_attacked",),  # -- static_other sweep (wave 19A) -- 508.1c
    "can't attack or block alone": ("cant_attack_alone", "cant_block_alone"),
    "can't be blocked by more than one creature": ("max_one_blocker",),
    "attacks each combat if able": ("must_attack",),
    "attack each combat if able": ("must_attack",),
    "blocks each combat if able": ("must_block",),
    "block each combat if able": ("must_block",),
    "attacks or blocks each combat if able": ("must_attack", "must_block"),
    "attack or block each combat if able": ("must_attack", "must_block"),
    "must be blocked if able": ("must_be_blocked",),
    "must be blocked by all creatures able": ("lure",),  # -- lure (wave 12B) -- 509.1c: combat.block_requirements
    "doesn't untap during your untap step": ("doesnt_untap",),
    "doesn't untap during its controller's untap step": ("doesnt_untap",),
    "don't untap during your untap step": ("doesnt_untap",),
    "don't untap during their controllers' untap steps": ("doesnt_untap",),
    "don't untap during their controller's untap step": ("doesnt_untap",),
    "its activated abilities can't be activated": ("cant_activate",),
    "their activated abilities can't be activated": ("cant_activate",),
    # -- attached events (wave 16F) -- 602.2: not the mana abilities (605.1a); 702.122: a creature that can't crew a Vehicle
    "its activated abilities can't be activated-nonmana": ("cant_activate_nonmana",),
    "can't attack, block, or crew Vehicles": ("cant_attack_or_block", "cant_crew"),
}
# -- keyword actions & face-down (wave 3F) -- "Enchanted creature gets +2/+2 and is goaded.", "Creatures your
# opponents control with power less than ~'s power are goaded." (701.15b: goaded by the controller of the
# permanent that caused it — "@you" becomes the static's controller where app/rules/layers.py applies it)
RULES.update({"is goaded": ("goaded:@you",), "are goaded": ("goaded:@you",)})
# -- attached events (wave 4L) -- "Enchanted creature … can't attack you or planeswalkers you control." (Vow of Duty;
# 508.1c: a restriction on where it attacks — "you" is the Aura's controller, app/rules/combat.py ``attack_forbidden``)
RULES.update({"can't attack you or planeswalkers you control": ("cant_attack_player_pw:@you",),
              "can't attack you": ("cant_attack_player:@you",)})
# -- conditional statics (wave 4B) -- 702.3b: a creature with defender can't attack; this lets it (app/rules/combat.py)
RULES.update({"can attack as though it didn't have defender": ("attack_despite_defender",),
              "can attack as though they didn't have defender": ("attack_despite_defender",)})
# -- damage wordings (wave 6B) -- 510.1a: "Each creature assigns combat damage equal to its toughness rather than its
# power" (Doran): the amount it assigns in the combat damage step (app/rules/combat.py ``compute_combat_damage``)
RULES.update({"assigns combat damage equal to its toughness rather than its power": ("assign_toughness",),
              "assign combat damage equal to their toughness rather than their power": ("assign_toughness",)})


def _rule(piece: str) -> list[str] | None:
    """One predicate piece that imposes a rule → the rule names, or None (not a rule)."""
    plain = RULES.get(piece)
    if plain is not None:
        return list(plain)
    m = re.fullmatch(r"must be blocked by all (?P<sel>.+) able", piece)  # (-- lure (wave 12B) -- only those creatures must)
    if m:
        sels = _sels(m["sel"])
        return [f"lure:{sels}"] if sels else None
    # -- multiple blocks (wave 13B) -- 509.1a: "can block an additional creature [each combat]" is block_extra:1:@src (the number of
    # extra attackers; one entry per source so that several of them add up), "any number of creatures" a huge number
    m = re.fullmatch(r"can block (?:(?P<one>an additional creature)|an additional (?P<a>\w+) creatures|up to (?P<b>\w+) additional "
                     r"creatures|(?P<any>any number of creatures))(?: each combat)?", piece)
    if m:
        n = 1 if m["one"] else 999 if m["any"] else _num(m["a"] or m["b"])
        return [f"block_extra:{n}:@src"] if n else None
    # -- static_other sweep (wave 17C) -- 702.122: "This creature crews Vehicles as though its power were 2 greater." / "… using its toughness
    # rather than its power." — the number it counts toward crew (casting.crew_value)
    m = re.fullmatch(r"crews Vehicles as though its power were (?P<n>\w+) greater", piece)
    if m and _num(m["n"]):
        return [f"crew_plus:{_num(m['n'])}"]
    if piece == "crews Vehicles using its toughness rather than its power":
        return ["crew_toughness"]
    m = re.fullmatch(r"can't be blocked except by (?P<n>\w+) or more creatures", piece)
    if m:
        n = _num(m["n"])
        return [f"min_blockers:{n}"] if n is not None and n >= 2 else None
    if piece == "can't be blocked by creatures with greater power":
        return ["cant_be_blocked_by_power:greater"]
    if piece == "can't block creatures with power greater than ~'s power":
        return ["cant_block_power:greater"]
    # -- cant (wave 16F) -- 115.2: "can't be the target of black spells or abilities from black sources" (Mercenary Informer) /
    # "… of nongreen spells or abilities from nongreen sources" (Gaea's Revenge), "… your opponents control" (Thrun): an object
    # whose source (a spell, or the source of an ability) has that color (or lacks it) can't target it. Colorless is nongreen.
    m = re.fullmatch(r"can't be the targets? of (?P<n>non)?(?P<c>white|blue|black|red|green) spells(?: (?P<o1>your opponents control))? or "
                     r"abilities from (?P=n)?(?P=c) sources(?: (?P<o2>your opponents control))?", piece)
    if m:
        colors = {"white": "W", "blue": "U", "black": "B", "red": "R", "green": "G"}[m["c"]]
        return [f"untargetable:{1 if m['o1'] or m['o2'] else 0}:{1 if m['n'] else 0}:{colors}"]
    m = re.fullmatch(r"can't be blocked (?P<except>except )?by (?P<sel>.+)", piece)
    if m:
        sels = _sels(m["sel"])
        return [f"cant_be_blocked_{'except_' if m['except'] else ''}by:{sels}"] if sels else None
    m = re.fullmatch(r"can block only (?P<sel>.+)", piece)
    if m:
        sels = _sels(m["sel"])
        return [f"block_only:{sels}"] if sels else None
    m = re.fullmatch(r"can't block (?P<sel>.+)", piece)
    if m:
        sels = _sels(m["sel"])
        return [f"cant_block_sel:{sels}"] if sels else None
    return None


def _sels(phrase: str) -> str | None:
    """"artifact creatures" / "creatures with flying or reach" / "Walls" → selector keys joined
    by "|" (any of them), or None when a part isn't a plural battlefield selector."""
    whole = _sel_key(phrase)
    if whole is not None:
        return whole
    parts = [p.strip() for p in re.split(r" or |, ", phrase.replace(" and/or ", " or "))]
    if len(parts) < 2:
        return None
    keys: list[str] = []
    for i, part in enumerate(parts):
        key = _sel_key(part)
        if key is None and i and " with " in parts[0]:  # "creatures with flying or reach"
            key = _sel_key(parts[0].split(" with ")[0] + " with " + part)
        if key is None:
            return None
        keys.append(key)
    return "|".join(keys)


def _sel_key(phrase: str, *, plural: bool = True) -> str | None:
    if plural and not selectors.is_plural(phrase):
        return None
    sel = selectors.parse(phrase)
    if sel is None or sel.player is not None or sel.zones != ("battlefield",) or sel.card:
        return None
    return sel.key()


def _relative(sel: selectors.Selector) -> bool:
    """Does the selector read "you" (a controller or owner)?"""
    return sel.controller is not None or sel.owner is not None or sel.zone_owner is not None


def rule_selectors(value: str) -> list[selectors.Selector]:
    """The alternatives of a parameterised rule's value ("<sel>|<sel>")."""
    return [selectors.from_key(k) for k in value.split("|") if k.startswith(selectors.PREFIX)]


def rule_arg(rule: str) -> tuple[str, str]:
    """"cant_be_blocked_by:sel:{…}" → ("cant_be_blocked_by", "sel:{…}"); a plain rule → (rule, "")."""
    name, _, arg = rule.partition(":")
    return name, arg


# -- conditions -------------------------------------------------------------------------------
def _condition(text: str) -> dict[str, Any] | None:
    c = text.strip()
    if c in ("it's your turn",):
        return {"static": "your_turn"}
    m = re.fullmatch(r"(?:it|~)(?:'s| is) (?P<test>attacking alone|attacking|blocking|tapped|untapped|enchanted|equipped|attached to a creature)", c)
    if m:
        return {"static": "self", "test": m["test"].replace(" ", "_")}
    if c in ("it entered this turn", "~ entered this turn"):  # -- refused modal/conditional (wave 3R1) -- (Crew Captain)
        return {"history": "entered_self"}
    m = re.fullmatch(r"(?:it|this creature|~) has (?P<n>\d+) or more level counters on it but no more than (?P<m>\d+) level counters on it", c)
    if m:  # -- keyword mechanics (wave 9D) -- 711.2a: a leveler's level symbol with a range
        return {"static": "self_counter", "counter": "level", "op": ">=", "n": int(m["n"]), "max": int(m["m"])}
    m = re.fullmatch(r"(?:it|~) has (?:(?P<one>a|an)|(?P<n>\w+) or more) "  # (wave 4B: "+1/+1 counters", "on him")
                     r"(?P<kind>(?:\+1/\+1|-1/-1|[a-z]+) )?counters? on (?:it|him|her)", c)
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
    from app.rules import static_conditions  # -- conditional statics (wave 4B) --

    found = static_conditions.parse(c)
    if found is not None:
        return found
    found = conditions.parse(c)
    return found if found is not None else static_conditions.compound(c)


def _mentions(cond: Any, kinds: tuple[str, ...]) -> bool:
    """Does the condition (or one nested in it) have one of these static kinds?"""
    if isinstance(cond, dict):
        return cond.get("static") in kinds or any(_mentions(v, kinds) for v in cond.values())
    if isinstance(cond, list):
        return any(_mentions(v, kinds) for v in cond)
    return False


def condition(text: str) -> dict[str, Any] | None:
    """-- conditional statics (wave 4B) -- one static condition from its wording."""
    return _condition(text)


def holds(plan: Plan, cond: dict[str, Any], *, source: CardInstance, controller: str) -> bool:
    """Is the condition true right now (611.3a)? ``source`` is the permanent with the static."""
    kind = cond.get("static")
    if kind == "your_turn":
        return plan.state.turn.active_player == controller
    if kind == "not":  # "unless …"
        return not holds(plan, cond["cond"], source=source, controller=controller)
    if kind == "self":
        test = cond["test"]
        if test == "attacking":
            return source.attacking is not None
        if test == "attacking_alone":  # 506.5: it's the only attacking creature
            return source.attacking is not None and sum(
                1 for c in plan.state.cards.values() if c.attacking is not None and c.zone.endswith(":battlefield")) == 1
        if test == "blocking":
            return bool(source.blocking)
        if test in ("tapped", "untapped"):
            return source.tapped == (test == "tapped")
        if test == "modified":  # -- conditional statics (wave 4B) -- 700.9
            from app.rules import static_conditions

            return static_conditions.modified(plan, source)
        if test == "attached_to_a_creature":  # -- casting extras (wave 18E) -- reconfigure 702.151b (judged without the host's types)
            host = plan.state.cards.get(source.attached_to or "")
            return host is not None and host.zone.endswith(":battlefield")
        sub = "Aura" if test == "enchanted" else "Equipment"
        return any(c.attached_to == source.id and c.zone.endswith(":battlefield") and sub in plan.ch(c).subtypes
                   for c in plan.state.cards.values())
    if kind == "self_counter":
        kinds = [cond["counter"]] if cond["counter"] else list(source.counters)
        total = sum(source.counters.get(k, 0) for k in kinds)
        return total >= cond["n"] and (cond.get("max") is None or total <= cond["max"])  # (max: wave 9D, 711.2a)
    if kind == "graveyard":
        return len(plan.state.zones.get(f"{controller}:graveyard", [])) >= cond["n"]
    from app.rules import static_conditions  # -- conditional statics (wave 4B) --

    if kind in static_conditions.KINDS:
        return static_conditions.holds(plan, cond, source=source, controller=controller)
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
    elif who.startswith(UNION):  # -- static wordings (wave 6E) -- either group
        if not any(selectors.matches(plan, selectors.from_key(k), card, ch, controller, source.id) for k in _union_keys(who)):
            return False
    elif not selectors.matches(plan, selectors.from_key(who), card, ch, controller, source.id):
        return False
    return conditions if conditions is not None else conditions_hold(plan, d, source=source, controller=controller)

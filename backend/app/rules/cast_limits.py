"""-- cast limits (wave 5E) -- what keeps a player from casting a spell or activating an ability, and the
"as though … had flash / haste" permissions next to them. Researched against the Comprehensive Rules of
2026-09-25 (data/rules/comprehensive_rules/).

* 601.3: a player can begin to cast a spell only if a rule or effect allows it *and no rule or effect
  prohibits it*. The prohibition is checked as the cast begins, on every path that casts: from the hand
  or the command zone, by a permission, by an effect that casts as it resolves (608.2g: suspend, cascade,
  rebound, "you may cast … without paying its mana cost") — copies aren't cast (707.10), so they never
  meet it. 601.3a: the spell's qualities are the ones it would have as proposed (the half of a split card
  or the adventure being cast, a face-down spell's: ``casting.cast_problem`` gets those characteristics).
* 602.5: a player can't begin to activate an ability that's prohibited from being activated. Mana
  abilities are activated abilities (605.1a, 605.3a), so "can't activate abilities of artifacts,
  creatures, or enchantments" (Grand Abolisher) stops them too — the automatic mana payment doesn't
  offer such a source (``casting.mana_abilities``). Crew and equip are activated abilities (702.122a,
  702.6a); turning a face-down permanent face up, suspending a card and playing a land are special
  actions (116.2), never stopped by these. "Artifacts, creatures, or enchantments" are permanents
  (109.2): cards in other zones aren't.
* 506.1: "during combat" is the combat phase (its five steps).
* 611.3a: a static ability's prohibition applies while its source is on the battlefield, read whenever it
  matters; 611.2a/c: a resolved effect's ("Your opponents can't cast spells this turn") lasts for its
  stated duration and affects the players it named as it resolved. "Until your next turn" ends as that
  player's next turn begins (500.4; 800.4m for a player who left: when that turn would have begun).
* "Can't cast more than one spell each turn" counts the spells that player cast this turn (601.2i,
  history.py's turn log), whatever happened to them since.
* 601.3b-d: "as though it had flash" only changes when a spell may be cast. 302.6 / 602.5a: "You may
  activate abilities of creatures you control as though those creatures had haste" lifts the summoning
  sickness rule for their {T} / {Q} abilities only (the creatures don't gain haste: they still can't
  attack, 508.1a).
* -- spell grants (wave 30T) -- "the first <kind> spell you cast each turn" (601.2i): the spell is the first of that kind the player cast this turn, the
  whole turn's casts counting whenever the source arrived (Radagast of Rhosgobel's rulings, 2026-06-29; cost_changes.first_ok). It gives convoke /
  improvise (Peri Brown, The Fifteenth Doctor), casualty N (Anhelo, Ashad; Silverquill's "each … has casualty 1") or flash (The Blue Spirit, Radagast).
  "As long as <condition>, you may cast … as though they had flash" (Quicksilver, Captain Mar-Vell, Kianne) is a flash permission read afresh, as its
  source's controller (611.3a, 601.3d).

The grammar is a closed list of wordings; anything else stays manual. Refused: other conditional statics
("As long as this Equipment is attached …"), prohibitions on a chosen name or "the same name as …",
"with even mana values", per-player conditions ("each opponent who attacked …"), "Hope of Ghirapur"'s
"target player who was dealt combat damage by ~", Auras on players ("Enchanted player can't …").
"""

from __future__ import annotations

import re
import secrets
from dataclasses import replace
from typing import TYPE_CHECKING, Any

from app.cards.names import normalize_name
from app.game.state import COMBAT_PHASES, CardInstance, GameState, zone_key
from app.rules import selectors
from app.rules.characteristics import CardInfo, Characteristics

if TYPE_CHECKING:
    from app.rules.plan import Plan

Context = dict[str, Any]
Definition = dict[str, Any]

# -- grammar ---------------------------------------------------------------------------------------
_SPELLS = r"(?:(?P<sel>[A-Za-z][A-Za-z' ,-]*?) )?spells(?P<tail> with the chosen name| of the chosen type| with mana value equal to the chosen number| with (?:even|odd) mana values| with mana value \d+ or (?:greater|less)| with mana value greater than the number of lands you control)?"  # (wave 22B: card_names.py; wave 44D: Brisela's mana value bound, as STATIC_NOBODY reads it; wave 50J: Lavinia's, counted for the caster)
_FROM = r"(?: from (?P<frm>anywhere other than their hands|graveyards or libraries|graveyards or exile|graveyards))?"
_ACT = (r"(?: or (?P<act>activate abilities of artifacts, creatures, or enchantments|activate abilities that aren't mana abilities"
        r"|activate abilities of cards in graveyards|activate planeswalkers' loyalty abilities))?")
_FROMS = {"anywhere other than their hands": ("not_hand",), "graveyards": ("graveyard",),
          "graveyards or libraries": ("graveyard", "library"), "graveyards or exile": ("graveyard", "exile")}
_ACTS = {"activate abilities of artifacts, creatures, or enchantments": "ace",
         "activate abilities that aren't mana abilities": "nonmana",
         "activate abilities of cards in graveyards": "graveyard", "activate planeswalkers' loyalty abilities": "loyalty"}
_WHO = {"your opponents": "opponents", "each opponent": "opponents", "players": "each", "each player": "each", "you": "you",
        "enchanted player": "enchanted", "enchanted creature's controller": "host_controller",  # (wave 25D: an Aura's Curse, Brand of Ill Omen)
        "defending player": "defending"}  # (wave 100K: Wardscale Dragon, while it is attacking)
_WHEN = {"during your turn": "your_turn", "during combat": "combat"}
# "Your opponents can't cast spells during your turn." / "During your turn, your opponents can't cast spells or activate
# abilities of artifacts, creatures, or enchantments." / "Your opponents can't cast spells from anywhere other than their
# hands." / "Players can't cast spells from graveyards or activate abilities of cards in graveyards." / "During combat,
# players can't cast spells or activate abilities that aren't mana abilities." / "You can't cast creature spells."
STATIC_CAST = re.compile(rf"^(?:(?P<lead>during your turn|during combat), )?(?P<who>your opponents|each opponent|players|each player|you|enchanted player|enchanted creature's controller|defending player) "
                         rf"can't cast {_SPELLS}{_FROM}{_ACT}(?: (?P<when>during your turn|during combat))?$")
# "Each player can't cast more than one spell each turn." / "Each player can't cast more than one noncreature spell each turn."
# -- prohibitions (wave 22B) -- 601.3: "Spells with the chosen name can't be cast." (Meddling Mage, Nevermore), "Creature spells can't be cast."
# (Aether Storm), "Noncreature spells with mana value 4 or greater can't be cast." (Gaddock Teeg): nobody may cast them
STATIC_NOBODY = re.compile(r"^(?P<sel>[A-Za-z][A-Za-z' ,-]*?)? ?spells(?P<tail> of the chosen type| with mana value equal to the chosen number| with (?:the chosen name|mana value \d+ or (?:greater|less)"
                           r"|\{X\} in their mana costs))? can't be cast$")
# 602.5: "Activated abilities of sources with the chosen name can't be activated [unless they're mana abilities]." (Pithing Needle, Phyrexian
# Revoker, Sorcerous Spyglass, Voidstone Gargoyle)
STATIC_NAMED = re.compile(r"^activated abilities of sources with the chosen name can't be activated(?P<nm> unless they're mana abilities)?$")
# -- linked exile (wave 30H) -- 201.2a, 607.2a: "Your opponents can't cast spells with the same name as the exiled card." (Ixalan's Binding, Ashiok's Erasure),
# "Players can't cast …" (Exclusion Ritual), "… as a card exiled with ~." (Circu, Godsend): a name in common with a card still exiled with the source
STATIC_EXILED_NAME = re.compile(r"^(?P<who>your opponents|players) can't cast spells with the same name as (?:the exiled card|a card exiled with ~)$")
STATIC_ONE = re.compile(r"^(?P<who>each player|you|enchanted player) can't cast more than one (?:(?P<sel>[A-Za-z][A-Za-z' ,-]*?) )?spell each turn$")
# "Each player who has cast a nonartifact spell this turn can't cast additional nonartifact spells." (the same, read as one)
STATIC_ADDITIONAL = re.compile(r"^each player who has cast (?:a|an) (?P<sel>[a-z][a-z' ,-]*?) spell this turn can't cast additional "
                               r"(?P<sel2>[a-z][a-z' ,-]*?) spells$")
# "Activated abilities of artifacts can't be activated." / "… of artifacts your opponents control …" / "… of artifacts,
# creatures, and planeswalkers …" (mana abilities included, 605.1a, unless it says otherwise)
STATIC_ABILITIES = re.compile(r"^activated abilities of (?P<sel>[a-z][a-z' ,-]*?) can't be activated(?P<nm> unless they're mana abilities)?$")
STATIC_LOYALTY = "players can't activate planeswalkers' loyalty abilities"
# 307.1: "Each opponent can cast spells only any time they could cast a sorcery." (Teferi, Mage of Zhalfir) — their own main
# phase, with priority and an empty stack: never as something resolves (608.2g), whatever lets them cast it then
STATIC_SORCERY = "each opponent can cast spells only any time they could cast a sorcery"
# "Creature cards you own that aren't on the battlefield have flash." (Teferi, Mage of Zhalfir): what matters of having flash
# is when the card may be cast (601.3b-d)
STATIC_OWN_FLASH = re.compile(r"^(?P<sel>[a-z]+) cards you own that aren't on the battlefield have flash$")
# 601.3d: "You may cast this spell as though it had flash if you control a Faerie."
SELF_FLASH_IF = re.compile(r"^you may cast (?:this spell|~) as though it had flash if (?P<cond>.+)$")
# Effects: "Your opponents can't cast spells this turn." / "Target player can't cast spells this turn." / "Players can't cast
# noncreature spells this turn." / "Until your next turn, your opponents can't cast spells from anywhere other than their hands."
EFFECT_CAST = re.compile(rf"^(?:(?P<lead>until your next turn|until the end of your next turn|this turn), )?(?P<who>your opponents|opponents|players|each player|each opponent|"
                         rf"target player|target opponent|its controller|you) can't cast {_SPELLS}{_FROM}{_ACT}(?: (?P<when>this turn|until your next turn|until the end of your next turn|during that player's next turn))?$")  # (wave 32C: Single Combat)
# -- trigger lines (wave 100A) -- "Each opponent can't cast instant or sorcery spells during that player's next turn." (Azor, the Lawbringer; Sphinx's
# Decree): each player's own next turn — the next one that player actually takes (723.1's reading of "that player's next turn"), never the current
# one; the official rulings: several such effects all apply to that same turn. ``until`` "their_next100a"; ``during`` is set as that turn begins.
# Flash permissions (601.3b): "You may cast Spirit spells as though they had flash." / "You may cast Dragon spells and artifact
# spells as though they had flash." / "Any player may cast spells as though they had flash." / "During each opponent's end
# step, you may cast spells as though they had flash." — and the effect "You may cast spells this turn as though they had flash."
STATIC_FLASH = re.compile(r"^(?P<during>during each opponent's end step, )?(?P<who>you|any player) may cast "
                          r"(?:(?P<sel>[A-Za-z][A-Za-z' ,-]*?) )?spells as though they had flash$")
EFFECT_FLASH = re.compile(r"^(?:(?P<lead>until end of turn|until your next turn), )?you may cast (?:(?P<sel>[A-Za-z][A-Za-z' ,-]*?) )?spells(?P<this> this turn)? "
                          r"as though they had flash$")
# -- static_other sweep (wave 19A) -- 609.4b / 118.14: "You may spend mana as though it were mana of any color to cast planeswalker spells."
# (Oath of Nissa), "You can spend mana of any type to cast creature spells." (Vizier of the Menagerie): how the cost of those spells may be paid
# -- casting costs (wave 22F) -- Chromatic Orrery / Mycosynth Lattice: "You may spend mana as though it were mana of any color." / "Players may
# …" (every spell and ability: any mana pays a colored symbol, 609.4b), Agatha's Soul Cauldron: "… to activate abilities of creatures you control."
STATIC_SPEND = re.compile(r"^(?P<who>you|players) (?P<how>may spend mana as though it were mana of any color|can spend mana of any type)"
                          r"(?: to (?:(?P<own>cast spells you don't own or to activate abilities of permanents you control but don't own)"  # (wave 50G: Nathan Drake)
                          r"|cast (?P<sel>[A-Za-z][A-Za-z' ,-]*?) spells|(?P<act>activate abilities of creatures you control)))?$")
_SELF_ABILITY_SPEND = re.compile(
    r"^(?:you may spend mana as though it were mana of any color to pay the activation costs of "
    r"(?:~|this artifact|this creature|this permanent)'s abilities"
    r"|mana of any type can be spent to activate (?:~|this artifact|this creature|this permanent)'s abilities)$")
_LAND_PLAY_LIMIT = re.compile(r"^(?P<lead>until end of turn, )?(?P<who>target player|target opponent|you|players|each opponent) "
                              r"can't play lands(?P<this> this turn)?$")
STATIC_HASTE = "you may activate abilities of creatures you control as though those creatures had haste"
# 702.51 / 702.126 / 702.66: "Nonartifact spells you cast have improvise." / "Artifact spells you cast have convoke." / "Spells
# you cast have delve." — the spell has it while it's being cast (601.2g-h: costs are paid with the spell on the stack)
# -- spell grants (wave 30T) -- "The first historic spell you cast each turn has convoke." (Peri Brown), "The first nonartifact spell you cast each turn
# has improvise." (The Fifteenth Doctor): the same grant to the first spell of a kind the turn's casts record (601.2i), counted from the whole turn
STATIC_HELPER = re.compile(r"^(?:(?P<first>the first) )?(?:(?P<sel>[A-Za-z][A-Za-z' ,-]*?) )?spells? you cast(?P<frm> from exile)?(?P<each> each turn)? "
                           r"(?:has|have) (?P<kw>convoke|improvise|delve)$")
# 601.3b: "You may cast the first creature spell you cast each turn as though it had flash." (The Blue Spirit)
STATIC_FIRST_FLASH = re.compile(r"^you may cast the first (?:(?P<sel>[A-Za-z][A-Za-z' ,-]*?) )?spell you cast each turn as though it had flash$")


# -- static_other sweep (wave 17C) -- 702.41a: "Artifact spells you cast have affinity for artifacts." / "Spells you cast have affinity for
# artifacts." — the spell has it while it's being cast (601.2f: the total cost is determined with it), one more reduction per instance
STATIC_AFFINITY = re.compile(r"^(?:(?P<sel>[A-Za-z][A-Za-z' ,-]*?) )?spells you cast have affinity for (?P<what>[A-Za-z ]+)$")


# -- static statics (wave 10B) -- 702.85a: "Spells you cast with mana value 6 or greater have cascade." / "The first spell
# you cast each turn has cascade." / "Enchantment spells you cast from your hand have cascade." / `Colorless spells you
# cast from your hand with mana value 7 or greater have "Cascade, cascade."` — the spell has the keyword as it's cast
# (601.2i: it becomes cast with its abilities; cascade's "when you cast this spell" trigger, 702.85a, is then put on the
# stack), one instance per word quoted. A grant to the spell's own copy or to a spell cast by another player isn't read.
_FROM_ZONES = {"your hand": "hand", "exile": "exile", "anywhere other than your hand": "not_hand"}
STATIC_CASCADE = re.compile(
    r"^(?:each |(?P<first>the first) )?(?:(?P<sel>[A-Za-z][A-Za-z' ,-]*?) )?spells? you cast"
    r"(?: from (?P<frm>your hand|exile|anywhere other than your hand))?"
    r"(?: (?P<tail>with mana value \d+ or (?:greater|less)))?(?P<each> each turn)? "
    r"(?:has|have) (?P<kw>cascade|storm|conspire|demonstrate|ripple \d+|casualty \d+|\"[Cc]ascade, cascade\.?\")$")  # (wave 17C: storm 702.40a, ripple 702.60a, conspire 702.78a; 30T: casualty 702.153a)


def _cascade_definition(m: re.Match[str]) -> Definition | None:
    if m["first"]:
        # "The first spell you cast each turn" / "… from exile each turn": no spell filter, one condition
        # (-- spell grants (wave 30T) -- "The first instant or sorcery spell you cast each turn has casualty 2." (Anhelo): the first of a kind)
        if m["tail"] or not m["each"] or m["frm"] == "your hand" or (m["sel"] and (m["frm"] or not m["kw"].startswith("casualty"))):
            return None
        first = "from" if m["frm"] else "kind" if m["sel"] else "turn"
        ok, key = _first_filter(m["sel"])
        if not ok:
            return None
    elif m["each"]:
        return None
    else:
        from app.rules.permissions import spell_filter

        phrase = re.sub(r"^(\w+) spells and (\w+)$", r"\1 or \2", m["sel"].strip()) if m["sel"] else None
        key = spell_filter(phrase, m["tail"]) if phrase or m["tail"] else None
        if key is None and (phrase or m["tail"]):
            return None  # (a wording the spell selector doesn't read)
        first = None
    word = m["kw"].split()[0]
    return {"kind": "static", "static": "spell_keyword", "keyword": word if word in ("storm", "conspire", "casualty", "demonstrate") else "ripple"
            if word == "ripple" else "cascade", **({"n": int(m["kw"].split()[1])} if word in ("ripple", "casualty") else {}),
            "count": 2 if m["kw"].startswith('"') else 1, "filter": key,
            "from": _FROM_ZONES[m["frm"]] if m["frm"] else None, "first": first, "effects": []}


def _lower_first(s: str) -> str:
    return s[:1].lower() + s[1:] if s[:1].isupper() else s


def _first_filter(sel: str | None) -> tuple[bool, str | None]:
    """-- spell grants (wave 30T) -- (understood, key) for the kind of "the first <sel> spell you cast each turn": one the turn's cast records answer
    (history.note_selector_ok: a kicked or face-down spell isn't recorded, so it isn't read)."""
    from app.rules import history, selectors

    ok, key = _filter(sel)
    return ok and (key is None or history.note_selector_ok(selectors.from_key(key))), key


def _filter(sel: str | None, tail: str | None = None) -> tuple[bool, str | None]:
    """(understood, the spell selector key) for "<sel> spells [<tail>]" (None: any spell)."""
    if not sel and not tail:
        return True, None
    from app.rules.permissions import spell_filter

    phrase = re.sub(r"^(\w+) spells and (\w+)$", r"\1 or \2", (sel or "").strip())  # "Dragon spells and artifact" → "Dragon or artifact"
    key = spell_filter(phrase or None, (tail or "").strip() or None)
    if key is None and not tail and (m := re.fullmatch(r"(\w+) spells and (\w+)", (sel or "").strip())):
        # (wave 45D: Gandalf the White "legendary spells and artifact spells", Liberator "colorless spells and artifact spells") a spell of either kind; two qualities of
        # different kinds (a supertype or colorless with a type) can't be one selector's list, so each is its own selector
        keys = [spell_filter(m[1]), spell_filter(m[2])]
        if all(keys):
            from app.rules.selectors import Selector

            return True, Selector(either=(keys[0], keys[1]), zones=("stack",)).key()  # type: ignore[arg-type]
    return key is not None, key


def _cast_definition(m: re.Match[str]) -> Definition | None:
    ok, key = _filter(m["sel"], m["tail"])
    if not ok:
        return None
    lead, when = m["lead"], m["when"]
    if lead and when:
        return None
    return {"kind": "static", "static": "cast_limit", "who": _WHO[m["who"]], "when": _WHEN.get(lead or when or ""),
            "filter": key, "from": list(_FROMS[m["frm"]]) if m["frm"] else None, "act": _ACTS.get(m["act"] or ""),
            "max": None, "effects": []}


def flash_def(key: str | None, **extra: Any) -> Definition:
    """A flash-only permission (601.3b): no zone, nothing played; ``extra``: "any_player", "during", "first" (-- spell grants (wave 30T) --), "if"."""
    return {"kind": "static", "static": "permission", "zone": "any", "once": False, "flash": True, "self": False, "play": False, "cast": True,
            "filter": key, "effects": [], **extra}


# -- spell grants (wave 30T) -- 601.3d, 611.3a: "As long as ~ is tapped, you may cast spells as though they had flash." (Quicksilver), "As long as an
# opponent has cast a spell this turn, …" (Captain Mar-Vell), "As long as ~'s power is even, you may cast noncreature spells as though they had
# flash." (Kianne), "As long as you control a green or blue permanent, you may cast this spell as though it had flash." (Hungering Yeti = "… if …")
AS_LONG_FLASH = re.compile(r"^as long as (?P<c>.+?), (?P<r>you may cast .+ as though (?:they|it) had flash)$")
# -- as long as (wave 35D) -- 702.8a: "This spell has flash as long as you control a Spirit." (Supernatural Rescue, Crashing Tide, Mutual Destruction, Take for
# a Ride, Graveyard Shift), "~ has flash as long as you control a Desert." (Colossal Rattlewurm): flash is only read when the spell is cast (601.3b), so it is
# the permission of "You may cast this spell as though it had flash if …" (601.3d), its condition read as it is cast
HAS_FLASH_WHILE = re.compile(r"^(?:this spell|~) has flash as long as (?P<c>.+)$")


def _conditional_flash(cond_text: str, rest: str) -> Definition | None:
    """The permission of "<rest>" that works only while the condition holds (read afresh each time, as its source's controller: 611.3a)."""
    from app.rules import conditions

    cond = conditions.parse(cond_text, objects=True)  # ("~ is tapped": the source itself)
    inner = static_definition(rest)
    if cond is None or "succeeded" in cond or set(conditions.objects_in(cond)) - {"self"} or inner is None or inner.get("static") != "permission":
        return None
    return {**inner, "if": cond}


# -- first activation (wave 48D) -- 118.9, 602.2b: "You may pay {0} rather than pay the equip cost of the first equip ability you activate each turn." (Bruenor
# Battlehammer; Kíli's "As long as you have an enduring story, …" is scripts._conditional_static; Forge Anew: "during each of your turns") and "You may pay {0}
# rather than pay the cycling cost of the first card you cycle each turn." (Gavi, Nest Warden)
FIRST_ALT = re.compile(r"you may pay \{0\} rather than pay the (?:(?P<eq>equip) cost of the first equip ability you activate|cycling cost of the first card you cycle)"
                       r" (?:each turn|(?P<own>during each of your turns))")


def static_definition(text: str) -> Definition | None:
    """The definition of a static line of this grammar (``permissions.define_static`` asks), or None."""
    from app.rules import casting_timing_permissions

    if (timing := casting_timing_permissions.static(text)) is not None:
        return timing
    t = _lower_first(text.strip().rstrip(".")).replace("the number of lands that player controls", "the number of lands you control")
    if t in ("players can't cast spells with the same name as a nontoken permanent", "players can't play nonbasic lands with the same name as a nontoken permanent"):
        return {'kind': 'static', 'static': 'cast_limit', 'who': 'each', 'filter': None, 'from': None,
                'act': None, 'when': None, 'max': None, 'name_permanent': True,
                'spells': 'cast spells' in t, 'nonbasic_lands': 'nonbasic lands' in t, 'effects': []}
  # (wave 50J: counted for the caster, who is "you" to the spell selector)
    if (own := HAS_FLASH_WHILE.fullmatch(t)) is not None:  # (wave 35D)
        t = f"you may cast this spell as though it had flash if {own['c']}"
    if (lead := AS_LONG_FLASH.fullmatch(t)) is not None:
        if lead["r"] not in ("you may cast this spell as though it had flash", "you may cast ~ as though it had flash"):
            return _conditional_flash(lead["c"], lead["r"])
        t = f"{lead['r']} if {lead['c']}"  # (a spell's own: "… if …", SELF_FLASH_IF)
    m = STATIC_CAST.fullmatch(t)
    if m:
        return _cast_definition(m)
    if t in ("players can cast spells only during their own turns", "each player can cast spells only during their own turn"):
        # -- static_other (wave 42A) -- 601.3: "Players can cast spells only during their own turns." (Dosan the Falling Leaf): a spell is cast only while its
        # caster is the active player (500.1), flash or not; the limit of every player is on the turns that are not theirs
        return {"kind": "static", "static": "cast_limit", "who": "each", "when": "not_own_turn", "filter": None, "from": None, "act": None, "max": None,
                "effects": []}
    m = STATIC_NOBODY.fullmatch(t)
    if m:  # -- prohibitions (wave 22B) --
        ok, key = _filter(m["sel"], m["tail"])
        if not ok or key is None:
            return None
        return {"kind": "static", "static": "cast_limit", "who": "each", "when": None, "filter": key, "from": None,
                "act": None, "max": None, "effects": []}
    if t == "enchanted player can't activate abilities that aren't mana abilities or loyalty abilities":  # -- cant restrictions (wave 110D) -- 602.5, 605.1a, 606 (Overwhelming Splendor)
        return {"kind": "static", "static": "cast_limit", "who": "enchanted", "when": None, "filter": None, "from": None, "act": "nonmana_noloyalty",
                "max": None, "spells": False, "effects": []}
    m = STATIC_NAMED.fullmatch(t)
    if m:
        return {"kind": "static", "static": "cast_limit", "who": "each", "when": None, "filter": None, "from": None,
                "act": "nonmana_named" if m["nm"] else "named", "max": None, "spells": False, "effects": []}
    m = STATIC_EXILED_NAME.fullmatch(t)
    if m:  # (-- linked exile (wave 30H) -- the key names the link: exiled_with.link reads it as a reference to the cards exiled with the source)
        return {"kind": "static", "static": "cast_limit", "who": _WHO[m["who"]], "when": None, "filter": None, "from": None, "act": None,
                "max": None, "exiled_with_name": True, "effects": []}
    m = STATIC_ONE.fullmatch(t)
    if m:
        ok, key = _filter(m["sel"])
        if not ok:
            return None
        return {"kind": "static", "static": "cast_limit", "who": _WHO[m["who"]], "when": None, "filter": key, "from": None,
                "act": None, "max": 1, "effects": []}
    m = STATIC_ADDITIONAL.fullmatch(t)
    if m and m["sel"] == m["sel2"]:
        ok, key = _filter(m["sel"])
        if not ok or key is None:
            return None
        return {"kind": "static", "static": "cast_limit", "who": "each", "when": None, "filter": key, "from": None,
                "act": None, "max": 1, "effects": []}
    m = STATIC_ABILITIES.fullmatch(t)
    if m:  # ("of artifacts, creatures, and planeswalkers": the abilities of each of them)
        sel = selectors.parse(re.sub(r",? and ", ", or " if "," in m["sel"] else " or ", m["sel"]))
        if sel is None or sel.player is not None or sel.card or sel.zones != ("battlefield",) or sel.extras or sel.other:
            return None
        return {"kind": "static", "static": "cast_limit", "who": "each", "when": None, "filter": None, "from": None,
                "act": "nonmana_of" if m["nm"] else "of", "of": sel.key(), "max": None, "spells": False, "effects": []}
    if t == STATIC_SORCERY:
        return {"kind": "static", "static": "cast_limit", "who": "opponents", "when": None, "filter": None, "from": None,
                "act": None, "max": None, "sorcery": True, "effects": []}
    m = STATIC_OWN_FLASH.fullmatch(t)
    if m:
        ok, key = _filter(m["sel"])
        if not ok or key is None:
            return None
        return {"kind": "static", "static": "permission", "zone": "any", "once": False, "flash": True, "self": False,
                "play": False, "cast": True, "filter": key, "own": True, "effects": []}
    m = SELF_FLASH_IF.fullmatch(t)
    if m:
        from app.rules import conditions

        cond = conditions.parse(m["cond"])
        if cond is None or "succeeded" in cond:
            return None
        return {"kind": "static", "static": "permission", "zone": "any", "once": False, "flash": True, "self": True,
                "play": False, "cast": True, "filter": None, "if": cond, "effects": []}
    if t == STATIC_LOYALTY:
        return {"kind": "static", "static": "cast_limit", "who": "each", "when": None, "filter": None, "from": None,
                "act": "loyalty", "max": None, "spells": False, "effects": []}
    m = STATIC_FLASH.fullmatch(t)
    if m:
        ok, key = _filter(m["sel"])
        if not ok:
            return None
        d: Definition = flash_def(key)
        if m["who"] == "any player":
            d["any_player"] = True
        if m["during"]:
            d["during"] = "opponents_end_step"
        return d
    if (m := STATIC_FIRST_FLASH.fullmatch(t)) is not None:  # -- spell grants (wave 30T) -- The Blue Spirit
        ok, key = _first_filter(m["sel"])
        return flash_def(key, first=True) if ok else None
    if t in (STATIC_HASTE, STATIC_HASTE.replace("of creatures", "of other creatures")):
        return {"kind": "static", "static": "activate_as_haste", "other": "of other creatures" in t, "effects": []}
    # -- static_other sweep (wave 19A) -- 606.3: "You may activate the loyalty abilities of planeswalkers you control twice each turn
    # rather than only once." (Oath of Teferi), "You may activate loyalty abilities of ~ on any player's turn any time you could cast an
    # instant." (Teferi, Master of Time): the once-a-turn and the sorcery timing of a loyalty ability, changed for those permanents
    if t == "you may activate the loyalty abilities of planeswalkers you control twice each turn rather than only once":
        return {"kind": "static", "static": "loyalty_rule", "who": "you", "twice": True, "effects": []}
    if t == "you may activate loyalty abilities of ~ on any player's turn any time you could cast an instant":
        return {"kind": "static", "static": "loyalty_rule", "who": "self", "instant": True, "effects": []}
    if t == "you may activate loyalty abilities of planeswalkers you control on any player's turn any time you could cast an instant":
        return {"kind": "static", "static": "loyalty_rule", "who": "you", "instant": True,
                "planeswalker_only": True, "effects": []}
    if t in ("you may activate equip abilities any time you could cast an instant", "during your turn, you may activate equip abilities any time you could cast an instant"):
        # -- most-played cards III (wave 46C) -- 702.6a: the sorcery timing of equip lifted (Leonin Shikari); (wave 48D: Forge Anew, only during your turn)
        return {"kind": "static", "static": "loyalty_rule", "who": "you", "equip_instant": True, "effects": [], **({"own_turn": True} if t.startswith("during") else {})}
    if t == "you may pay {0} rather than pay cycling costs":
        return {"kind": "static", "static": "first_alt", "act": "cycling", "own_turn": False, "repeat": True, "effects": []}
    if (m := FIRST_ALT.fullmatch(t)) is not None:  # -- first activation (wave 48D) -- 118.9: an alternative cost for the first activation (casting.py _first_alt)
        return {"kind": "static", "static": "first_alt", "act": "equip" if m["eq"] else "cycling", "own_turn": bool(m["own"]), "effects": []}
    # -- unspent mana (wave 35C) -- 500.4, 614.1a: "If you would lose unspent mana, that mana becomes colorless instead." (Kruphix, Omnath, Horizon Stone:
    # app/rules/kept_mana.py): the mana stays in the pool, colorless, with its restrictions and riders (the Gatherer rulings)
    if t == "players don't lose unspent mana as steps and phases end":
        return {'kind':'static','static':'keep_mana','color':'*','who':'any','effects':[]}
    if t == "if you would lose unspent mana, that mana becomes colorless instead":
        return {"kind": "static", "static": "colorless_mana", "effects": []}
    # -- static_other sweep (wave 21A) -- 106.4 / 500.4: "You don't lose unspent red mana as steps and phases end." (app/rules/kept_mana.py)
    m = re.fullmatch(r"you don't lose unspent (white|blue|black|red|green) mana as steps and phases end", t)
    if m:
        return {"kind": "static", "static": "keep_mana", "color": {"white": "W", "blue": "U", "black": "B", "red": "R", "green": "G"}[m[1]], "effects": []}
    # -- static_other sweep (wave 21A) -- 702.34a: "Each instant and sorcery card in your graveyard has flashback. The flashback cost is equal to that
    # card's mana cost." (Lier, Disciple of the Drowned), "During your turn, each … has flashback. Its flashback cost is equal to its mana cost."
    # -- casting costs (wave 22F) -- "During your turn, each Lesson card in your graveyard has flashback {1}." (Iroh, Grand Lotus): a fixed cost; a
    # reminder after the sentence is read past
    m = re.fullmatch(r"(?P<turn>during your turn, )?each (?P<sel>[a-z ,'-]+?) cards? in your graveyard has flashback(?:\. (?:the|its) flashback cost "
                     r"is equal to (?:that card's|its) mana cost| (?P<fixed>\{\d+\}))(?: \(.*\))?", t, re.I)
    if m:
        sel = selectors.parse(m["sel"].replace(" and ", " or ") + " card in your graveyard")
        if sel is None or sel.zones != ("graveyard",) or not sel.card or sel.player is not None:
            return None
        return {"kind": "static", "static": "gy_flashback", "sel": selectors.replace(sel, zone_owner="you").key(),
                "your_turn": bool(m["turn"]), "effects": [], **({"cost": m["fixed"]} if m["fixed"] else {})}
    if _SELF_ABILITY_SPEND.fullmatch(t):
        return {"kind": "static", "static": "spend_as", "mode": "type" if t.startswith("mana") else "color",
                "abilities": "self", "filter": None, "no_spells": True, "effects": []}
    m = STATIC_SPEND.fullmatch(t)
    if m:
        ok, key = _filter(m["sel"])
        if m["own"]:  # -- cant restrictions (wave 50G) -- 609.4b: "… to cast spells you don't own or to activate abilities of permanents you control but don't own" (Nathan Drake)
            if m["who"] != "you" or m["how"].startswith("can"):
                return None
            from dataclasses import replace as _replace

            from app.rules.selectors import parse as _parse

            unowned = _parse("spell")
            return None if unowned is None else {"kind": "static", "static": "spend_as", "mode": "color", "filter": _replace(unowned, owner="opponent").key(),
                                                 "abilities": "unowned", "effects": []}
        everything = not m["sel"] and not m["act"]  # (wave 22F: no "to …": every spell and every activated ability)
        if not ok or (key is None and m["sel"]) or (m["who"] == "players" and (m["sel"] or m["act"] or m["how"].startswith("can"))):
            return None
        return {"kind": "static", "static": "spend_as", "mode": "type" if m["how"].startswith("can") else "color", "filter": key, "effects": [],
                **({"abilities": "all" if everything else "creatures"} if everything or m["act"] else {}),
                **({"players": True} if m["who"] == "players" else {}), **({"no_spells": True} if m["act"] else {})}
    from app.rules import first_mana_source_spell

    if (mana_first := first_mana_source_spell.definition(t)) is not None:
        return mana_first
    m = STATIC_CASCADE.fullmatch(t)
    if m:  # -- static statics (wave 10B) --
        return _cascade_definition(m)
    m = STATIC_HELPER.fullmatch(t)
    if m:
        if bool(m["first"]) != bool(m["each"]) or (m["first"] and m["frm"]):
            return None
        ok, key = _first_filter(m["sel"]) if m["first"] else _filter(m["sel"])
        if not ok:
            return None
        return {"kind": "static", "static": "spell_helper", "keyword": m["kw"], "filter": key, "effects": [],
                **({"from": "exile"} if m["frm"] else {}), **({"first": True} if m["first"] else {})}  # (wave 17C: "Spells you cast from exile have convoke.")
    m = STATIC_AFFINITY.fullmatch(t)
    if m:
        from app.rules.casting import affinity_pred

        ok, key = _filter(m["sel"])
        if not ok or affinity_pred(m["what"].lower()) is None:
            return None
        return {"kind": "static", "static": "spell_helper", "keyword": "affinity", "what": m["what"].lower(), "filter": key, "effects": []}
    from app.rules import (  # "You have hexproof." (app/rules/player_shields.py); -- prohibitions (wave 22B) --
        hexproof_targeting,
        life_lock,  # -- can't lose life (wave 29D) -- "Your life total can't change." (app/rules/life_lock.py)
        player_shields,
        prohibitions,
    )

    return (hexproof_targeting.static_definition(text) or prohibitions.static_definition(text)
            or player_shields.static_definition(text) or life_lock.static_definition(text))


def _effect_cast(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    lead, when = m["lead"], m["when"]
    if bool(lead) == bool(when):
        raise ValueError("one duration")
    ok, key = _filter(m["sel"], m["tail"])
    if not ok:
        raise ValueError("selector")
    act = _ACTS.get(m["act"] or "")
    if act not in (None, "loyalty"):
        raise ValueError("only loyalty abilities")  # (an effect's other activation limits aren't read)
    who = {"your opponents": "each_opponent", "opponents": "each_opponent", "each opponent": "each_opponent", "players": "each_player", "each player": "each_player",
           "target player": "target", "target opponent": "target", "its controller": "it.controller", "you": "you"}[m["who"]]  # (wave 51C: Render Silent; wave 100B: "you", Innocuous Researcher)
    sel = {"target player": "player", "target opponent": "opponent"}.get(m["who"])
    until = "end_of_next_turn" if "end of your next turn" in (lead or when or "") else "next_turn" if "next turn" in (lead or when or "") else "turn"
    if when == "during that player's next turn":  # -- trigger lines (wave 100A) -- (each player named: "that player" is each of them)
        if who not in ("each_opponent", "each_player", "target"):
            raise ValueError("whose next turn")
        until = "their_next100a"
    return [{"do": "cast_limit", "who": who, "until": until, "filter": key, "from": list(_FROMS[m["frm"]]) if m["frm"] else None,
             "act": act}], sel


def _effect_land_play_limit(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    if bool(m["lead"]) == bool(m["this"]):
        raise ValueError("one duration")
    who = {"target player": "target", "target opponent": "target", "you": "you",
           "players": "each_player", "each opponent": "each_opponent"}[m["who"]]
    selector = {"target player": "player", "target opponent": "opponent"}.get(m["who"])
    return [{"do": "cast_limit", "who": who, "until": "turn", "lands": True, "spells": False}], selector


def _effect_flash(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    if not m["this"] and not m["lead"]:
        raise ValueError("a duration")  # ("you may cast spells as though they had flash" as an effect: no duration — refused)
    ok, key = _filter(m["sel"])
    if not ok or (m["this"] and m["lead"]):
        raise ValueError("selector")
    # (-- durations (wave 30M) -- Teferi, Time Raveler: "Until your next turn, you may cast sorcery spells as though they had flash.")
    return [{"do": "flash_permission", "filter": key, **({"until": "next_turn"} if m["lead"] == "until your next turn" else {})}], None


# -- chosen filters (wave 53B) -- "The next spell of the chosen type you cast this turn can be cast as though it had flash." (Progenitor's Icon): 601.3b, a flash permission for
# the next spell of the creature type its source chose as it entered, bound now (the choice is public and stays the source's, 614.12a); cast_limits.flash_permission
EFFECT_NEXT_FLASH = re.compile(r"^the next spell of the chosen type you cast this turn can be cast as though it had flash$")


def _effect_next_flash(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    from app.rules import selectors

    sel = selectors.parse("spells of the chosen type")
    if sel is None:
        raise ValueError("selector")
    return [{"do": "flash_permission", "spell": sel.key(), "next": True}], None


# -- chosen filters (wave 53B) -- "Until your next turn, spells with the chosen name can't be cast and lands with the chosen name can't be played." (Conjurer's Ban): 601.3, 305.1;
# the name is bound into the spell selector (chosen.bind_effects) and the lands are judged by that same name (``land_problem``)
EFFECT_BAN_NAMED = re.compile(r"^until your next turn, spells with the chosen name can't be cast(?P<lands> and lands with the chosen name can't be played)?$")


def _effect_ban_named(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    from app.rules import selectors

    sel = selectors.parse("spells with the chosen name")
    if sel is None:
        raise ValueError("selector")
    return [{"do": "cast_limit", "who": "each_player", "until": "next_turn", "filter": sel.key(), "from": None, "act": None,
             **({"lands": True} if m["lands"] else {})}], None


def cycling_problem(state: GameState, info: CardInfo | None) -> str | None:
    """CR 702.29f: a cycling prohibition also covers typecycling."""
    source = next((src for src, _ in _statics(state, info, "cant_cycle")), None)
    return f"{source.name or 'A permanent'}: players can't cycle cards" if source is not None else None


def land_problem(state: GameState, player: str, ch: Characteristics, info: CardInfo | None = None, zone: str = '') -> str | None:
    """Why a stored limit forbids ``player`` playing this land now (305.1), or None: "lands with the chosen name can't be played" until a turn (the name is the bound ``name:`` of its spell selector)."""
    r = state.rules
    if info is not None and 'Basic' not in ch.supertypes:
        for src, d in _statics(state, info, 'cast_limit'):
            if d.get('nonbasic_lands') and _shares_permanent_name(state, info, ch):
                return f"{src.name}: you can't play a nonbasic land with the same name as a nontoken permanent"
    for x in r.cast_limits if r is not None else ():
        if x.get("lands") and x.get("player") == player and _record_live(state, x):
            if x.get("from") and not any(zone.endswith(f":{z}") for z in x["from"]):  # -- one-card wordings (wave 110H) -- Memory Vessel: lands from hand only (305.1)
                continue
            if not x.get("filter"):
                return f"{x.get('label') or 'An effect'}: you can't play lands now"
            names = [e[5:] for e in selectors.from_key(x["filter"]).extras if e.startswith("name:")]
            from app.rules import card_names

            if names and card_names.has_name(ch, names[0]):
                return f"{x.get('label') or 'An effect'}: you can't play {ch.name} now"
    return None


def _template(rx: re.Pattern[str], fn: Any) -> tuple[re.Pattern[str], Any]:
    def run(m: re.Match[str]) -> Any:
        from app.rules.scripts import _NoMatch

        try:
            return fn(m)
        except ValueError as exc:
            raise _NoMatch from exc

    return rx, run


def _player_templates() -> list[tuple[re.Pattern[str], Any]]:
    from app.rules import life_lock, player_shields

    return [*player_shields.TEMPLATES, *life_lock.TEMPLATES]  # (-- can't lose life (wave 29D) --)


TEMPLATES: list[tuple[re.Pattern[str], Any]] = [_template(_LAND_PLAY_LIMIT, _effect_land_play_limit), _template(EFFECT_CAST, _effect_cast), _template(EFFECT_NEXT_FLASH, _effect_next_flash), _template(EFFECT_BAN_NAMED, _effect_ban_named), *_player_templates()]


# -- chosen filters (wave 53B) -- "If you won five flips this way, you may cast spells from your hand this turn without paying their mana costs." (Yusri): 118.9, a stored
# permission for the spells in the controller's hand until end of turn (611.2a), each cast free (the other costs are still paid, 118.9d)
EFFECT_FREE = re.compile(r"^(?:until end of turn, )?you may cast spells from your hand(?: this turn)? without paying their mana costs$")


def free_sentence(text: str) -> list[dict[str, Any]] | None:
    return [{"do": "free_permission"}] if EFFECT_FREE.fullmatch(text) else None


def free_permission(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    from app.game.rules_state import Permission

    pid = ctx["controller"]
    label = ctx.get("name") or "An effect"
    plan.rules.permissions.append(Permission(id=secrets.token_hex(4), player=pid, cast=True, zone="hand", free=True, until="end_of_turn", turn=plan.state.turn.number,
                                             source=ctx.get("source_object"), label=f"{label}: without paying their mana costs"))
    plan.note(f"{plan.name(pid)} may cast spells from their hand this turn without paying their mana costs ({label})", actor=pid)
    return True


def flash_sentence(text: str) -> list[dict[str, Any]] | None:
    """A whole sentence "You may cast [<sel>] spells this turn as though they had flash." (``scripts._parse_effects``
    reads it before its "you may" choices: it grants a permission, nothing is chosen as it resolves)."""
    m = EFFECT_FLASH.fullmatch(text)
    if m is None:
        return None
    try:
        return _effect_flash(m)[0]
    except ValueError:
        return None


# -- effects ---------------------------------------------------------------------------------------
def cast_limit(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """A resolved "… can't cast … this turn / until your next turn": one record per player named now (611.2c)."""
    from app.rules.effects import _players

    r = plan.rules
    turn = plan.state.turn.number
    r.cast_limits = [x for x in r.cast_limits if not (x.get("until") == "turn" and x.get("turn") != turn)]
    label = ctx.get("name") or "An effect"
    for pid in _players(plan, ctx, e["who"]):
        r.cast_limits.append({"id": secrets.token_hex(4), "player": pid, "controller": ctx["controller"], "until": e["until"],
                              "turn": turn, "filter": e.get("filter"), "from": e.get("from"), "act": e.get("act"), "lands": e.get("lands"),
                              "label": label, **({"spells": e["spells"]} if "spells" in e else {})})
        if e.get("lands") and e.get("spells") is False:
            plan.note(f"{plan.name(pid)} can't play lands this turn ({label})", actor=ctx["controller"])
            continue
        what = _spells_words(e.get("filter"), e.get("from"))
        if e.get("act") == "loyalty":
            what += " or activate loyalty abilities"
        when = "for the rest of the game" if e["until"] == "game" else "during their next turn" if e["until"] == "their_next100a" else "this turn" if e["until"] == "turn" else \
            ("until the end of " if e["until"] == "end_of_next_turn" else "until ") + plan.name(ctx["controller"]) + "’s next turn"
        plan.note(f"{plan.name(pid)} can't cast {what} {when} ({label})", actor=ctx["controller"])
    return True


def flash_permission(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """"You may cast spells this turn as though they had flash" (601.3b): a stored flash-only permission until cleanup."""
    from app.game.rules_state import Permission

    pid = ctx["controller"]
    label = ctx.get("name") or "An effect"
    key, nth = e.get("filter"), None
    if e.get("spell"):  # -- chosen filters (wave 53B) -- "the next spell of the chosen type": the type read from the source now, the spells cast so far counted (cast_limits.EFFECT_NEXT_FLASH)
        from app.rules import selectors
        from app.rules.cost_changes import casts_so_far

        value = selectors.source_choice(plan, ctx.get("source_card"), "creature type")
        bound = selectors.bind_chosen(selectors.from_key(e["spell"]), value) if value else None
        if bound is None:
            return True  # (no type chosen: nothing is granted)
        key, nth = bound.key(), casts_so_far(plan.state, plan.info, pid, bound.key())
    if e.get("next_matching"):
        from app.rules.cost_changes import casts_so_far

        nth = casts_so_far(plan.state, plan.info, pid, key)
    plan.rules.permissions.append(Permission(id=secrets.token_hex(4), player=pid, cast=True, zone="any", filter=key, nth=nth,
                                             flash=True, until=e.get("until", "end_of_turn"), turn=plan.state.turn.number,
                                             source=ctx.get("source_object"), label=f"{label}: as though it had flash"))
    plan.note(f"{plan.name(pid)} may cast {_spells_words(key, None)} {'until their next turn' if e.get('until') else 'this turn'} "
              f"as though they had flash ({label})",
              actor=pid)
    return True


def _player_primitives() -> tuple[dict[str, Any], dict[str, Any]]:
    from app.rules import player_shields

    return player_shields.PRIMITIVES, player_shields.RESUME


def _life_primitives() -> dict[str, Any]:
    from app.rules import life_lock

    return life_lock.PRIMITIVES  # -- can't lose life (wave 29D) --


PRIMITIVES = {"cast_limit": cast_limit, "flash_permission": flash_permission, "free_permission": free_permission, **_player_primitives()[0], **_life_primitives()}
RESUME = dict(_player_primitives()[1])


def turn_began(plan: Plan, skipped: list[tuple[str, int]] | None = None) -> None:
    """500.4 / 800.4m: "until your next turn" limits end as that player's next turn begins (or would have)."""
    r = plan.rules
    turn, active = plan.state.turn.number, plan.active
    ended = {(active, turn), *(skipped or ())}
    for x in r.cast_limits:  # -- trigger lines (wave 100A) -- "during that player's next turn": this is it (the first turn they take after the effect)
        if x.get("until") == "their_next100a" and x.get("during") is None and x.get("player") == active and turn > int(x.get("turn") or 0):
            x["during"] = turn
    r.cast_limits = [x for x in r.cast_limits if not (x.get("until") == "their_next100a" and x.get("during") is not None and x["during"] != turn)]
    old110i = r.cast_limits
    r.cast_limits = [x for x in r.cast_limits if not (x.get("until") == "next_turn" and any(
        x.get("controller") == p and n > int(x.get("turn") or 0) for p, n in ended))
        and not (x.get("until") == "end_of_next_turn" and any(x.get("controller") == p and n > int(x.get("turn") or 0) for p, n in skipped or ()))  # (wave 32C)
        and not (x.get("until") == "turn" and x.get("turn") != turn)]
    for x in old110i:  # -- cards (wave 110I) -- the reveal lasts as long as the ban (Firestorm Phoenix)
        if x.get("reveal110i") and x not in r.cast_limits and (k := plan.state.cards.get(x["reveal110i"])) is not None and plan.oid(k) == x["obj110i"]:
            plan.do({"type": "hide", "card_ids": [k.id]}, actor=k.owner)
    # -- durations (wave 30M) -- "Until your next turn, you may play that card / cast … as though … had flash": a permission (500.4, 800.4m)
    r.permissions = [p for p in r.permissions if not (p.until == "next_turn" and any((p.until_player or p.player) == pl and n > p.turn for pl, n in ended))]
    from app.rules import life_lock, player_shields

    player_shields.turn_began(plan, ended)
    life_lock.turn_began(plan, ended)  # -- can't lose life (wave 29D) --


def _spells_words(key: str | None, frm: list[str] | None) -> str:
    words = "spells" if key is None else "those spells"
    if frm == ["not_hand"]:
        words += " from anywhere other than their hand"
    elif frm:
        words += " from " + " or ".join(f"{z}s" if z != "library" else "libraries" for z in frm).replace("exiles", "exile")
    return words


# -- reading the table -----------------------------------------------------------------------------
_CACHE: dict[tuple, list[tuple[str, int, Definition]]] = {}
_KINDS = ("cant_cycle", "hexproof_targeting", "cast_limit", "activate_as_haste", "player_shield", "spell_helper", "spell_keyword", "loyalty_rule", "spend_as", "keep_mana", "colorless_mana", "gy_flashback",
          "cant_enter", "cant_counters", "cant_remove_counters", "cant_play_lands", "cant_pay", "cant_cause_sacrifice", "cant_search", "search_top", "draw_cap", "cant_target", "cant_play_gy_lands",  # (wave 22B: app/rules/prohibitions.py; 43B: Aven Mindcensor)
          "zone_grant",  # (wave 25A: app/rules/zone_grants.py)
          "life_lock",  # (wave 29D: app/rules/life_lock.py)
          "rad_gain", "venture_limit", "first_alt", "spell_replicate110a")  # (wave 44C: app/rules/designations.py; 45B: Keen-Eared Sentry)


def _scan(state: GameState, info: CardInfo) -> list[tuple[str, int, Definition]]:
    from app.rules import read_pass

    return read_pass.once(state, info, "cast_limits.scan", lambda: _scan_table(state, info))  # (wave 29A: once per read-only pass)


def _scan_table(state: GameState, info: CardInfo) -> list[tuple[str, int, Definition]]:
    """(permanent, ability index, definition) of every limit / haste-permission static on the battlefield, read
    from copiable values (cheap, cached by what is there); ``_statics`` confirms each with the permanent's
    current characteristics (a "loses all abilities" effect removes it, 613.1f)."""
    from app.rules import designations, scripts, static_pairs
    from app.rules.copying import copy_index
    from app.rules.layers import copiable
    from app.rules.plan import live_players

    r = state.rules
    if r is None:
        return []
    live = tuple(live_players(state))
    copies = copy_index(r)
    key = (live, tuple(sorted((cid, c.controller, c.zone, c.face_down, c.face, c.flipped, c.card_id or c.name,
                               c.token.text if c.token else "", r.card_mode(cid), copies.get(r.object_id(cid), (0, "")))
                              for cid, c in state.cards.items() if c.zone.endswith(":battlefield") or designations.emblem_card(c))))
    hit = _CACHE.get(key)
    if hit is not None:
        return hit
    out = []
    for cid, c in state.cards.items():
        if not (c.zone.endswith(":battlefield") or designations.emblem_card(c)) or c.face_down or c.controller not in live or r.card_mode(cid) == "manual":
            continue
        entries = scripts.definitions(copiable(state, c, info))
        for index, d in ((i, part) for i, definition in entries.items() for part in static_pairs.parts(definition)):
            if not c.zone.endswith(':battlefield') and d.get('static') not in ('spell_keyword', 'loyalty_rule', 'cast_limit'):
                continue
            if d.get("kind") == "static" and (d.get("static") in _KINDS or d.get("player_shield") or d.get("spell_grants")):  # (wave 28C: spell_grants.py)
                out.append((cid, index, d))
    if len(_CACHE) > 256:
        _CACHE.clear()
    _CACHE[key] = out
    return out


def _statics(state: GameState, info: CardInfo | None, kind: str) -> list[tuple[CardInstance, Definition]]:
    if info is None or state.rules is None:
        return []
    found = list(dict.fromkeys((cid, i) for cid, i, d in _scan(state, info) if d["static"] == kind))
    if not found:
        return []
    from app.rules import characteristics as chars
    from app.rules import scripts, static_pairs, statics
    from app.rules.layers import _view, derive

    out = []
    for cid, index in found:
        card = state.cards[cid]
        now = scripts.definitions(derive(state, card, chars.of(card, info), info))
        for d in static_pairs.parts(now.get(index, {})):
            if d.get("static") == kind and statics.static_if_holds(_view(state, info), d, card):  # (wave 35D: 611.3a)
                out.append((card, d))
    return out


def _who_ok(who: str, player: str, controller: str, src: CardInstance | None = None, state: GameState | None = None) -> bool:
    if who == "defending":  # -- instead (wave 100K) -- 506.2, 802.1b: the player the source is attacking (or who controls or protects what it attacks)
        from app.rules.combat import defender_of

        return src is not None and state is not None and src.attacking is not None and defender_of(state, src.attacking) == player
    if who in ("enchanted", "host_controller"):  # -- attached events (wave 25D) -- the player the Aura is attached to / the controller of the creature it is
        if src is None or state is None:
            return False
        if who == "enchanted":
            return src.attached_player == player
        host = state.cards.get(src.attached_to or "")
        return host is not None and host.zone.endswith(":battlefield") and host.controller == player
    return who == "each" or (who == "opponents" and player != controller) or (who == "you" and player == controller)


def _when_ok(state: GameState, when: str | None, controller: str, player: str | None = None) -> bool:
    if when == "not_own_turn":  # (wave 42A) a turn that isn't the casting player's own
        return player is not None and state.turn.active_player != player
    if when == "your_turn":
        return state.turn.active_player == controller
    if when == "combat":
        return state.turn.phase in COMBAT_PHASES
    if when == "attacked110a":  # -- wave 110A -- Angelic Arbiter: the player declared attackers this turn (508.1)
        log = state.rules.turn_log if state.rules is not None else None
        return player is not None and log is not None and log.turn == state.turn.number and player in log.attacked
    if when == "attacked_me110c":  # -- wave 110C -- Midnight Crusader Shuttle: the player attacked the source's controller or a planeswalker they control this turn
        log = state.rules.turn_log if state.rules is not None else None
        return player is not None and log is not None and log.turn == state.turn.number and player in log.attacked_at110c.get(controller, [])
    return True


def _record_live(state: GameState, x: dict[str, Any]) -> bool:
    if x.get("until") == "their_next100a":  # -- trigger lines (wave 100A) -- only during that player's next turn
        return x.get("during") == state.turn.number
    return x.get("until") != "turn" or x.get("turn") == state.turn.number


def _cast_hit(state: GameState, player: str, card: CardInstance, ch: Characteristics, info: CardInfo | None,
              d: dict[str, Any], resolving: bool = False, source: str | None = None, x: int | None = None) -> bool:
    """Does this limit forbid ``player`` casting this card as this spell now (``resolving``: as something resolves; ``x``: the X announced)?"""
    if d.get("spells") is False:
        return False
    if d.get("obj110i"):  # -- cards (wave 110I) -- Firestorm Phoenix: this one card (object), nothing else
        return state.rules is not None and state.rules.object_id(card.id) == d["obj110i"]
    if d.get("more110a"):  # -- wave 110A -- Ward of Bones: only while the player controls more permanents of the cast spell's type than the source's controller
        from app.rules import wave110a_spells

        return source in state.cards and wave110a_spells.more_of(state, info, state.cards[source], d, player, ch.types)
    if d.get('name_permanent'):
        return info is not None and _shares_permanent_name(state, info, ch)
    if d.get("exiled_with_name"):  # -- linked exile (wave 30H) --
        return source is not None and info is not None and _same_name_as_exiled(state, info, source, ch)
    if d.get("sorcery"):  # 307.1
        return resolving or not (state.turn.active_player == player and state.turn.phase in ("main1", "main2")
                                 and not state.zones.get("stack"))
    if d.get("share_last100i"):  # -- activated (wave 100I) -- "share a color with the spell most recently cast this turn" (any player's, as it was cast)
        log = state.rules.turn_log if state.rules is not None else None
        last = log.casts[-1] if log is not None and log.turn == state.turn.number and log.casts else None
        return last is not None and bool(set(last.colors) & ch.colors)
    frm = d.get("from")
    if frm:
        if frm == ["not_hand"]:
            if card.zone == zone_key(player, "hand"):
                return False
        elif not any(card.zone.endswith(f":{z}") for z in frm):
            return False
    key = d.get("filter")
    if key is not None:
        if info is None:
            return True  # (can't tell: forbid rather than allow a cast the rules may forbid)
        from app.rules.permissions import spell_matches

        if x is not None:  # -- review 38 -- 601.2e, 202.3e: once X is announced, the proposed spell's mana value counts it (Void Winnower ruling 2015-08-25)
            ch = replace(ch, mana_value=ch.mana_value + x * ch.mana_cost.count("{X}"))
        if not spell_matches(state, player, card, ch, key, info, source):  # (source: wave 22B, "with the chosen name")
            return False
        # -- prohibitions (wave 44D) -- 601.3a: a choice made while proposing the spell (the X of a mana cost with {X}) could raise its mana value past an upper bound
        # ("spells with mana value 3 or less", Brisela), so the player may begin to cast it, ignoring the effect
        if x is None and "{X}" in ch.mana_cost and any(what == "mv" and op == "<=" for what, op, _ in selectors.from_key(key).compare):
            return False
    if d.get("max") is not None:
        return _cast_this_turn(state, player, key) >= int(d["max"])
    return True


def _same_name_as_exiled(state: GameState, info: CardInfo, source: str, ch: Characteristics) -> bool:
    """-- linked exile (wave 30H) -- 201.2a: does the spell share a name with a face-up card still exiled with the source (607.2a)? (a face-down one
    has no name; the card exiled with it is only its name for those who may look, so it never makes a spell uncastable here)"""
    from app.rules import card_names, exiled_with
    from app.rules.plan import Plan

    src = state.cards[source]
    plan = Plan.view(state, src.controller, info)
    ctx = {"controller": src.controller, "source_card": source, "source_object": plan.oid(src)}
    names = {normalize_name(n) for c in exiled_with.cards(plan, ctx) if not state.cards[c].face_down for n in card_names.names_of(plan.ch(state.cards[c]))}
    return bool(names & {normalize_name(n) for n in card_names.names_of(ch)})


def _cast_this_turn(state: GameState, player: str, key: str | None) -> int:
    from app.rules import history

    r = state.rules
    if r is None or r.turn_log.turn != state.turn.number:
        return 0
    sel = selectors.from_key(key) if key is not None else None
    return sum(1 for n in r.turn_log.casts if n.player == player
               and (sel is None or history.note_matches(sel, n.types, n.subtypes, n.supertypes, n.colors, n.mv)))


def cast_problem(state: GameState, player: str, card: CardInstance, ch: Characteristics, info: CardInfo | None, *,
                 resolving: bool = False, announced: int | None = None) -> str | None:
    """Why a rule or effect prohibits ``player`` from casting this card as this spell now (601.3), or None. ``resolving``:
    the cast is made as something resolves (608.2g: suspend, cascade, "you may cast … without paying …"). ``announced``: the X
    of its mana cost, once chosen (601.2e checks the proposed spell again)."""
    r = state.rules
    if r is None:
        return None
    from app.rules import source_spell_discounts64

    if (unknown_source := source_spell_discounts64.cast_problem(state, player, ch, info)) is not None:
        return unknown_source
    from app.rules import split_second  # -- split second (wave 8A) -- 702.61a

    if (why := split_second.problem(state, info, "cast other spells", card.id)) is not None:
        return why
    from app.rules import scripts

    if card.zone != zone_key(player, "graveyard") and any(d.get("only") for d in scripts.definitions(ch).values()):
        return f"{ch.name or 'It'} can be cast only from your graveyard"  # -- review 43 -- Haakon's "but not from anywhere else" (101.2) also holds as something resolves (cascade; 2006-07-15 ruling)
    from app.rules import static_perm100d  # -- static permanents (wave 100D) -- Serra Avenger

    if (first := static_perm100d.cast_problem(state, player, ch)) is not None:
        return first
    from app.rules import wave110n_cards  # -- (wave 110N) -- Rock Jockey

    if (rock := wave110n_cards.cast_problem(state, player, ch)) is not None:
        return rock
    for x in r.cast_limits:
        if x.get("player") == player and _record_live(state, x) and _cast_hit(state, player, card, ch, info, x, x=announced):
            return f"{x.get('label') or 'An effect'}: you can't cast {_spells_words(x.get('filter'), x.get('from'))} now"
    for src, d in _statics(state, info, "cast_limit"):
        if _who_ok(d["who"], player, src.controller, src, state) and _when_ok(state, d.get("when"), src.controller, player) \
                and _cast_hit(state, player, card, ch, info, d, resolving, src.id, announced):
            more = " more than once this turn" if d.get("max") is not None else \
                " except any time you could cast a sorcery" if d.get("sorcery") else ""
            return f"{src.name or 'A permanent'}: you can't cast {_spells_words(d.get('filter'), d.get('from'))}{more} now"
    return None


def _act_hit(state: GameState, player: str, card: CardInstance, ch: Characteristics, act: str | None, d: dict[str, Any],
             src_controller: str, info: CardInfo | None, *, mana: bool, loyalty: bool, source: str | None = None) -> bool:
    on_field = card.zone.endswith(":battlefield")
    if act in ("named", "nonmana_named"):  # -- prohibitions (wave 22B) -- 602.5, 709.4a: sources with the chosen name
        if info is None or (act == "nonmana_named" and mana):
            return False
        from app.rules import card_names
        from app.rules.plan import Plan

        return card_names.matches(Plan.view(state, src_controller, info), source, ch)
    if act == "all":  # -- static permanents (wave 100D) -- every activated ability, mana abilities too (City of Solitude, 605.1a)
        return True
    if act == "ace":
        return on_field and bool({"Artifact", "Creature", "Enchantment"} & set(ch.types))
    if act == "nonmana":
        return not mana
    if act == "nonmana_noloyalty":  # (wave 110D)
        return not mana and not loyalty
    if act == "graveyard":
        return card.zone.endswith(":graveyard")
    if act == "loyalty":
        return loyalty
    if act in ("of", "nonmana_of"):
        if not on_field or (act == "nonmana_of" and mana) or info is None:
            return False
        from app.rules.plan import Plan

        return selectors.matches(Plan.view(state, src_controller, info), selectors.from_key(d["of"]), card, ch, src_controller)
    return False


def activation_problem(state: GameState, player: str, card: CardInstance, ch: Characteristics, info: CardInfo | None, *,
                       mana: bool = False, loyalty: bool = False) -> str | None:
    """Why ``player`` can't activate this ability of this object now (602.5), or None. ``mana``: it's a mana ability
    (605.1a); ``loyalty``: a loyalty ability (606)."""
    r = state.rules
    if r is None:
        return None
    if not mana:  # -- split second (wave 8A) -- 702.61a, 702.61b: mana abilities stay possible
        from app.rules import split_second

        if (why := split_second.problem(state, info, "activate abilities that aren't mana abilities")) is not None:
            return why
    for x in r.cast_limits:
        if x.get("player") == player and _record_live(state, x) and x.get("act") \
                and _act_hit(state, player, card, ch, x["act"], x, x.get("controller") or player, info, mana=mana, loyalty=loyalty):
            return f"{x.get('label') or 'An effect'}: that ability can't be activated now"
    for src, d in _statics(state, info, "cast_limit"):
        if d.get("act") and _who_ok(d["who"], player, src.controller, src, state) and _when_ok(state, d.get("when"), src.controller, player) \
                and _act_hit(state, player, card, ch, d["act"], d, src.controller, info, mana=mana, loyalty=loyalty, source=src.id):
            return f"{src.name or 'A permanent'}: that ability can't be activated now"
    return None


def any_activation_limits(state: GameState, info: CardInfo | None) -> bool:
    """A cheap test before ``activation_problem`` in hot paths (the mana sources of every payment)."""
    r = state.rules
    if r is None:
        return False
    if state.zones.get("stack"):  # (-- split second (wave 8A) --)
        return True
    if any(x.get("act") and _record_live(state, x) for x in r.cast_limits):
        return True
    return info is not None and any(d["static"] == "cast_limit" and d.get("act") for _, _, d in _scan(state, info))


def loyalty_rule(state: GameState, card: CardInstance, info: CardInfo | None, key: str) -> bool:
    """-- static_other sweep (wave 19A) -- does a static let this planeswalker's loyalty abilities be activated ``key`` ("twice" each turn, at
    "instant" speed on any player's turn)? Its controller's "planeswalkers you control", or its own."""
    if key == "twice" and state.rules is not None and state.rules.once_per_turn.get(f"loyalty_twice100g:{card.controller}") == state.turn.number:
        return True  # -- zones (wave 100G) -- "… twice this turn rather than only once" (Urza Assembles the Titans III: zones100g.loyalty_twice)
    if key == "twice" and state.rules is not None and state.rules.once_per_turn.get(f"loyalty_veil110b:{card.id}") == state.turn.number:
        return True  # -- wave 110B -- The Chain Veil: one more activation of this planeswalker this turn (wave110b_cards.veil)
    if info is None:
        return False
    from app.rules.plan import Plan

    for src, d in _statics(state, info, 'loyalty_rule'):
        if not d.get(key) or not (src.id == card.id if d['who'] == 'self' else src.controller == card.controller):
            continue
        if d.get('own_turn') and state.turn.active_player != card.controller:
            continue
        if d.get('planeswalker_only') and 'Planeswalker' not in Plan.view(state, card.controller, info).ch(card).types:
            continue
        if d.get('entered100h'):  # -- turn state (wave 100H) -- "as long as ~ entered this turn" (The Wandering Emperor)
            from app.rules import history

            view = Plan.view(state, card.controller, info)
            if not any(e.object_id == view.oid(card) for e in history.log_for(view).entered):
                continue
        return True
    return False


def first_alt(state: GameState, player: str, act: str, info: CardInfo | None, *, first: bool = True) -> bool:
    """-- first activation (wave 48D) -- does a static let ``player`` pay {0} rather than the ``act`` ("equip" / "cycling") cost of their first such activation (the
    caller checks that none was activated this turn)?"""
    return any(d["act"] == act and src.controller == player and (first or d.get("repeat"))
               and (not d["own_turn"] or state.turn.active_player == player)
               for src, d in _statics(state, info, "first_alt"))


def spend_mode(state: GameState, player: str, card: CardInstance, ch: Characteristics, info: CardInfo | None) -> str | None:
    """-- static_other sweep (wave 19A) -- how ``player``'s statics let them spend mana on this spell ("type": any type, else "color")."""
    if info is None:
        return None
    from app.rules.permissions import spell_matches

    modes = {d["mode"] for src, d in _statics(state, info, "spend_as") if (src.controller == player or d.get("players")) and not d.get("no_spells")
             and (d["filter"] is None or spell_matches(state, player, card, ch, d["filter"], info))}
    return "type" if "type" in modes else "color" if modes else None


def ability_spend_mode(state: GameState, player: str, card: CardInstance, ch: Characteristics, info: CardInfo | None) -> str | None:
    """-- casting costs (wave 22F) -- 609.4b: how ``player``'s statics let them spend mana on this activated ability."""
    if info is None:
        return None
    modes = {d["mode"] for src, d in _statics(state, info, "spend_as") if (src.controller == player or d.get("players")) and d.get("abilities")
             and (d["abilities"] == "all" or d["abilities"] == "self" and card.id == src.id
                  or card.controller == src.controller and (d["abilities"] == "unowned" and card.owner != card.controller
                                                           or d["abilities"] == "creatures" and ch.is_creature))}
    return "type" if "type" in modes else "color" if modes else None


def as_though_haste(state: GameState, card: CardInstance, info: CardInfo | None) -> bool:
    """302.6 / 602.5a: may this creature's {T} / {Q} abilities be activated as though it had haste?"""
    if info is None:
        return False
    return any(src.controller == card.controller and (not d.get("other") or src.id != card.id)
               for src, d in _statics(state, info, "activate_as_haste"))


def granted_helpers(state: GameState, player: str, spell_card: str, spell: Characteristics, info: CardInfo) -> set[str]:
    """Convoke / improvise / delve that permanents ``player`` controls give this spell they're casting."""
    found = _statics(state, info, "spell_helper")
    card = state.cards.get(spell_card)
    from app.rules import (
        spell_grants,  # -- spell grants (wave 28C) -- "The next spell you cast this turn has improvise."
    )

    nxt = {kw for kw in ("convoke", "improvise") if card is not None and spell_grants.pending(state, player, card, spell, info, kw)}
    if not found or card is None:
        return nxt
    from app.rules.cost_changes import first_ok
    from app.rules.permissions import spell_matches

    return nxt | {d["keyword"] for src, d in found if src.controller == player and d["keyword"] != "affinity"
            and (d.get("from") is None or card.zone.endswith(":exile")
                 or (card.stack_info is not None and "Cast from exile" in card.stack_info.tags))
            and (d.get("filter") is None or spell_matches(state, player, card, spell, d["filter"], info))
            and (not d.get("first") or first_ok(state, info, player, d.get("filter")))}  # (wave 30T: "the first … spell you cast each turn")


def granted_affinities(state: GameState, player: str, card: CardInstance, spell: Characteristics, info: CardInfo) -> list[str]:
    """-- static_other sweep (wave 17C) -- the "affinity for X" words that permanents ``player`` controls give this spell (702.41a)."""
    from app.rules import (
        spell_grants,  # -- spell grants (wave 28C) -- "The next spell you cast this turn has affinity for artifacts."
    )
    from app.rules.permissions import spell_matches

    return [d["what"] for src, d in _statics(state, info, "spell_helper") if src.controller == player and d["keyword"] == "affinity"
            and (d.get("filter") is None or spell_matches(state, player, card, spell, d["filter"], info))] + [
        g.what for g in spell_grants.pending(state, player, card, spell, info, "affinity")]


def from_ok(d: Definition, card: CardInstance, state: GameState | None = None, info: CardInfo | None = None, player: str = "") -> bool:
    """-- static_other sweep (wave 17C) -- a granted keyword's "from exile" / "from your hand" zone, for a spell not yet cast (the card is
    where it is cast from) — "first … each turn" statics are not offered ahead (conspire reads none); -- spell grants (wave 30T) -- with the table
    (casualty): the first spell / first of a kind this turn, none cast before it (601.2i)."""
    from app.rules.cost_changes import first_ok

    zone = d.get("from")
    where = card.zone.rsplit(":", 1)[-1]
    first = d.get("first")
    if first is not None and (state is None or info is None or state.rules is None or first == "from"
                              or (first == "turn" and state.rules.spells_this_turn(player, state.turn.number) > 0)
                              or (first == "kind" and not first_ok(state, info, player, d["filter"]))):
        return False
    return zone is None or (where != "hand" if zone == "not_hand" else where == zone)


def granted_cascade(plan: Plan, spell_card: str, spell: Characteristics, cast_from: str | None, keyword: str = "cascade") -> int:
    """-- static statics (wave 10B) -- how many extra instances of cascade (702.85a) the permanents ``plan.actor``
    controls give this spell as it is cast from ``cast_from`` (the zone's name). "The first spell you cast each turn"
    reads the spells cast before this one (it isn't counted yet: 601.2i), "from exile" those cast from exile."""
    return len(granted_instances(plan, spell_card, spell, cast_from, keyword))


def granted_instances(plan: Plan, spell_card: str, spell: Characteristics, cast_from: str | None, keyword: str) -> list[Definition]:
    """The statics (one entry per instance) that give this spell ``keyword`` as it is cast (-- static_other sweep (wave 17C) -- ripple
    reads each one's N)."""
    found = _statics(plan.state, plan.info, "spell_keyword")
    card = plan.state.cards.get(spell_card)
    if card is None or plan.rules is None:
        return []
    from app.rules import (
        spell_grants,  # -- spell grants (wave 28C) -- "The next spell you cast this turn has cascade." (702.85a, 702.40a)
    )
    from app.rules.cost_changes import first_ok
    from app.rules.permissions import spell_matches

    player, turn = plan.actor, plan.state.turn.number
    log = plan.rules.turn_log if plan.rules.turn_log.turn == turn else None
    earlier = [c for c in (log.casts if log else []) if c.player == player and c.object_id != plan.oid(card)]
    total: list[Definition] = [{"keyword": keyword, "count": 1} for _g in spell_grants.pending(plan.state, player, card, spell, plan.info, keyword)]
    if not found:
        return total
    for src, d in found:
        if src.controller != player or d.get("keyword") != keyword:
            continue
        zone = d.get("from")
        if zone is not None and not (cast_from != "hand" if zone == "not_hand" else cast_from == zone):
            continue
        if d.get("first") == "mana_source":
            from app.rules import first_mana_source_spell

            if not first_mana_source_spell.eligible(plan, plan.oid(card), earlier, d["mana_tag"]):
                continue
        if d.get("first") == "turn" and plan.rules.spells_this_turn(player, turn) > 0:
            continue
        if d.get("first") == "from" and (cast_from is None or any(c.cast_from == cast_from or (zone == "not_hand" and c.cast_from != "hand")
                                                                  for c in earlier)):
            continue
        if d.get("filter") is not None and not spell_matches(plan.state, player, card, spell, d["filter"], plan.info):
            continue
        if d.get("first") == "kind" and not first_ok(plan.state, plan.info, player, d["filter"]):
            continue  # -- spell grants (wave 30T) -- "The first instant or sorcery spell you cast each turn has casualty 2." (601.2i: this one isn't counted yet)
        total += [d] * int(d.get("count", 1))
    return total


def permission_during_ok(state: GameState, d: Definition, player: str) -> bool:
    """A flash permission's "During each opponent's end step" (513: the end step of a turn of an opponent's)."""
    if d.get("during") == "opponents_end_step":
        return state.turn.active_player != player and state.turn.phase == "end"
    if d.get("during") == "your_turn":  # (wave 17C) "During your turn, …"
        return state.turn.active_player == player
    return True


def self_flash(state: GameState, player: str, card: CardInstance, ch: Characteristics, info: CardInfo) -> str | None:
    """601.3d: the card's own "You may cast this spell as though it had flash if …", when its condition holds now (the
    grant's label), else None."""
    from app.rules import conditions, scripts
    from app.rules.plan import Plan

    for d in scripts.definitions(ch).values():
        if d.get("static") == "permission" and d.get("self") and d.get("flash") and d.get("flash_sac"):
            return f"{ch.name}: as though it had flash"  # -- flash auras (wave 46B) -- unconditional (the sacrifice is casting.flash_sac's)
        if d.get("static") == "permission" and d.get("self") and d.get("flash") and d.get("if") is not None:
            ctx = {"controller": player, "source_card": card.id, "source_object": state.rules.object_id(card.id) if state.rules else None}
            # 601.2a: the announced spell has left its original zone before its timing condition is evaluated.
            # A graveyard-cast Swift Reckoning therefore needs two OTHER instants/sorceries there.
            prospect = state
            if card.zone.endswith(":graveyard"):
                prospect = state.model_copy(deep=True)
                prospect.zones[card.zone] = [cid for cid in prospect.zones.get(card.zone, []) if cid != card.id]
                prospect.zones.setdefault("stack", []).append(card.id)
                prospect.cards[card.id].zone = "stack"
                prospect.cards[card.id].face = card.face
            if conditions.holds(Plan.view(prospect, player, info), ctx, d["if"]):
                return f"{ch.name}: as though it had flash"
    return None


def free_cast_blocked(plan: Plan, player: str, card_id: str, face: int | None = None) -> str | None:
    """A card the engine offered ``player`` to cast as something resolves (608.2g): is that cast prohibited now (601.3)?
    (A split card / adventure: prohibited only if every half it could be cast as is; -- granted casts (wave 29B) -- ``face``: that half / face
    only, 709.3a / 712.11c.)"""
    from app.rules import characteristics as chars

    card = plan.state.cards.get(card_id)
    if card is None:
        return None
    faces = (face,) if face is not None else (0, 1) if chars.is_two_spell_card(card, plan.info) else (None,)
    from app.rules import text_global_word71

    found = [cast_problem(plan.state, player, card, text_global_word71.prospective(plan.state, card, chars.as_cast(card, plan.info, f), plan.info), plan.info, resolving=True) for f in faces]
    return found[0] if all(found) else None


def _shares_permanent_name(state: GameState, info: CardInfo, ch: Characteristics) -> bool:
    from app.rules import card_names
    from app.rules.layers import _view

    view = _view(state, info)
    return any(c.zone.endswith(':battlefield') and not c.token and card_names.share(ch, view.ch(c))
               for c in state.cards.values())

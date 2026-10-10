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

The grammar is a closed list of wordings; anything else stays manual. Refused: conditional statics
("As long as this Equipment is attached …"), prohibitions on a chosen name or "the same name as …",
"with even mana values", per-player conditions ("each opponent who attacked …"), "Hope of Ghirapur"'s
"target player who was dealt combat damage by ~", Auras on players ("Enchanted player can't …").
"""

from __future__ import annotations

import re
import secrets
from typing import TYPE_CHECKING, Any

from app.game.state import COMBAT_PHASES, CardInstance, GameState, zone_key
from app.rules import selectors
from app.rules.characteristics import CardInfo, Characteristics

if TYPE_CHECKING:
    from app.rules.plan import Plan

Context = dict[str, Any]
Definition = dict[str, Any]

# -- grammar ---------------------------------------------------------------------------------------
_SPELLS = r"(?:(?P<sel>[A-Za-z][A-Za-z' ,-]*?) )?spells(?P<tail> with the chosen name)?"  # (wave 22B: card_names.py)
_FROM = r"(?: from (?P<frm>anywhere other than their hands|graveyards or libraries|graveyards or exile|graveyards))?"
_ACT = (r"(?: or (?P<act>activate abilities of artifacts, creatures, or enchantments|activate abilities that aren't mana abilities"
        r"|activate abilities of cards in graveyards|activate planeswalkers' loyalty abilities))?")
_FROMS = {"anywhere other than their hands": ("not_hand",), "graveyards": ("graveyard",),
          "graveyards or libraries": ("graveyard", "library"), "graveyards or exile": ("graveyard", "exile")}
_ACTS = {"activate abilities of artifacts, creatures, or enchantments": "ace",
         "activate abilities that aren't mana abilities": "nonmana",
         "activate abilities of cards in graveyards": "graveyard", "activate planeswalkers' loyalty abilities": "loyalty"}
_WHO = {"your opponents": "opponents", "players": "each", "each player": "each", "you": "you",
        "enchanted player": "enchanted", "enchanted creature's controller": "host_controller"}  # (wave 25D: an Aura's Curse, Brand of Ill Omen)
_WHEN = {"during your turn": "your_turn", "during combat": "combat"}
# "Your opponents can't cast spells during your turn." / "During your turn, your opponents can't cast spells or activate
# abilities of artifacts, creatures, or enchantments." / "Your opponents can't cast spells from anywhere other than their
# hands." / "Players can't cast spells from graveyards or activate abilities of cards in graveyards." / "During combat,
# players can't cast spells or activate abilities that aren't mana abilities." / "You can't cast creature spells."
STATIC_CAST = re.compile(rf"^(?:(?P<lead>during your turn|during combat), )?(?P<who>your opponents|players|each player|you|enchanted player|enchanted creature's controller) "
                         rf"can't cast {_SPELLS}{_FROM}{_ACT}(?: (?P<when>during your turn|during combat))?$")
# "Each player can't cast more than one spell each turn." / "Each player can't cast more than one noncreature spell each turn."
# -- prohibitions (wave 22B) -- 601.3: "Spells with the chosen name can't be cast." (Meddling Mage, Nevermore), "Creature spells can't be cast."
# (Aether Storm), "Noncreature spells with mana value 4 or greater can't be cast." (Gaddock Teeg): nobody may cast them
STATIC_NOBODY = re.compile(r"^(?P<sel>[A-Za-z][A-Za-z' ,-]*?)? ?spells(?P<tail> with (?:the chosen name|mana value \d+ or (?:greater|less)"
                           r"|\{X\} in their mana costs))? can't be cast$")
# 602.5: "Activated abilities of sources with the chosen name can't be activated [unless they're mana abilities]." (Pithing Needle, Phyrexian
# Revoker, Sorcerous Spyglass, Voidstone Gargoyle)
STATIC_NAMED = re.compile(r"^activated abilities of sources with the chosen name can't be activated(?P<nm> unless they're mana abilities)?$")
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
EFFECT_CAST = re.compile(rf"^(?:(?P<lead>until your next turn|this turn), )?(?P<who>your opponents|players|each player|each opponent|"
                         rf"target player|target opponent) can't cast {_SPELLS}{_FROM}{_ACT}(?: (?P<when>this turn|until your next turn))?$")
# Flash permissions (601.3b): "You may cast Spirit spells as though they had flash." / "You may cast Dragon spells and artifact
# spells as though they had flash." / "Any player may cast spells as though they had flash." / "During each opponent's end
# step, you may cast spells as though they had flash." — and the effect "You may cast spells this turn as though they had flash."
STATIC_FLASH = re.compile(r"^(?P<during>during each opponent's end step, )?(?P<who>you|any player) may cast "
                          r"(?:(?P<sel>[A-Za-z][A-Za-z' ,-]*?) )?spells as though they had flash$")
EFFECT_FLASH = re.compile(r"^(?:until end of turn, )?you may cast (?:(?P<sel>[A-Za-z][A-Za-z' ,-]*?) )?spells(?P<this> this turn)? "
                          r"as though they had flash$")
# -- static_other sweep (wave 19A) -- 609.4b / 118.14: "You may spend mana as though it were mana of any color to cast planeswalker spells."
# (Oath of Nissa), "You can spend mana of any type to cast creature spells." (Vizier of the Menagerie): how the cost of those spells may be paid
# -- casting costs (wave 22F) -- Chromatic Orrery / Mycosynth Lattice: "You may spend mana as though it were mana of any color." / "Players may
# …" (every spell and ability: any mana pays a colored symbol, 609.4b), Agatha's Soul Cauldron: "… to activate abilities of creatures you control."
STATIC_SPEND = re.compile(r"^(?P<who>you|players) (?P<how>may spend mana as though it were mana of any color|can spend mana of any type)"
                          r"(?: to (?:cast (?P<sel>[A-Za-z][A-Za-z' ,-]*?) spells|(?P<act>activate abilities of creatures you control)))?$")
STATIC_HASTE = "you may activate abilities of creatures you control as though those creatures had haste"
# 702.51 / 702.126 / 702.66: "Nonartifact spells you cast have improvise." / "Artifact spells you cast have convoke." / "Spells
# you cast have delve." — the spell has it while it's being cast (601.2g-h: costs are paid with the spell on the stack)
STATIC_HELPER = re.compile(r"^(?:(?P<sel>[A-Za-z][A-Za-z' ,-]*?) )?spells you cast(?P<frm> from exile)? have (?P<kw>convoke|improvise|delve)$")


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
    r"(?:has|have) (?P<kw>cascade|storm|conspire|ripple \d+|\"[Cc]ascade, cascade\.?\")$")  # (wave 17C: storm 702.40a, ripple 702.60a, conspire 702.78a)


def _cascade_definition(m: re.Match[str]) -> Definition | None:
    if m["first"]:
        # "The first spell you cast each turn" / "… from exile each turn": no spell filter, one condition
        if m["sel"] or m["tail"] or not m["each"] or m["frm"] == "your hand":
            return None
        first = "from" if m["frm"] else "turn"
        key = None
    elif m["each"]:
        return None
    else:
        from app.rules.permissions import spell_filter

        phrase = re.sub(r"^(\w+) spells and (\w+)$", r"\1 or \2", m["sel"].strip()) if m["sel"] else None
        key = spell_filter(phrase, m["tail"]) if phrase or m["tail"] else None
        if key is None and (phrase or m["tail"]):
            return None  # (a wording the spell selector doesn't read)
        first = None
    return {"kind": "static", "static": "spell_keyword", "keyword": m["kw"] if m["kw"] in ("storm", "conspire") else "ripple"
            if m["kw"].startswith("ripple") else "cascade", **({"n": int(m["kw"].split()[1])} if m["kw"].startswith("ripple") else {}),
            "count": 2 if m["kw"].startswith('"') else 1, "filter": key,
            "from": _FROM_ZONES[m["frm"]] if m["frm"] else None, "first": first, "effects": []}


def _lower_first(s: str) -> str:
    return s[:1].lower() + s[1:] if s[:1].isupper() else s


def _filter(sel: str | None, tail: str | None = None) -> tuple[bool, str | None]:
    """(understood, the spell selector key) for "<sel> spells [<tail>]" (None: any spell)."""
    if not sel and not tail:
        return True, None
    from app.rules.permissions import spell_filter

    phrase = re.sub(r"^(\w+) spells and (\w+)$", r"\1 or \2", (sel or "").strip())  # "Dragon spells and artifact" → "Dragon or artifact"
    key = spell_filter(phrase or None, (tail or "").strip() or None)
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


def static_definition(text: str) -> Definition | None:
    """The definition of a static line of this grammar (``permissions.define_static`` asks), or None."""
    t = _lower_first(text.strip().rstrip("."))
    m = STATIC_CAST.fullmatch(t)
    if m:
        return _cast_definition(m)
    m = STATIC_NOBODY.fullmatch(t)
    if m:  # -- prohibitions (wave 22B) --
        ok, key = _filter(m["sel"], m["tail"])
        if not ok or key is None:
            return None
        return {"kind": "static", "static": "cast_limit", "who": "each", "when": None, "filter": key, "from": None,
                "act": None, "max": None, "effects": []}
    m = STATIC_NAMED.fullmatch(t)
    if m:
        return {"kind": "static", "static": "cast_limit", "who": "each", "when": None, "filter": None, "from": None,
                "act": "nonmana_named" if m["nm"] else "named", "max": None, "spells": False, "effects": []}
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
        d: Definition = {"kind": "static", "static": "permission", "zone": "any", "once": False, "flash": True, "self": False,
                         "play": False, "cast": True, "filter": key, "effects": []}
        if m["who"] == "any player":
            d["any_player"] = True
        if m["during"]:
            d["during"] = "opponents_end_step"
        return d
    if t == STATIC_HASTE:
        return {"kind": "static", "static": "activate_as_haste", "effects": []}
    # -- static_other sweep (wave 19A) -- 606.3: "You may activate the loyalty abilities of planeswalkers you control twice each turn
    # rather than only once." (Oath of Teferi), "You may activate loyalty abilities of ~ on any player's turn any time you could cast an
    # instant." (Teferi, Master of Time): the once-a-turn and the sorcery timing of a loyalty ability, changed for those permanents
    if t == "you may activate the loyalty abilities of planeswalkers you control twice each turn rather than only once":
        return {"kind": "static", "static": "loyalty_rule", "who": "you", "twice": True, "effects": []}
    if t == "you may activate loyalty abilities of ~ on any player's turn any time you could cast an instant":
        return {"kind": "static", "static": "loyalty_rule", "who": "self", "instant": True, "effects": []}
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
    m = STATIC_SPEND.fullmatch(t)
    if m:
        ok, key = _filter(m["sel"])
        everything = not m["sel"] and not m["act"]  # (wave 22F: no "to …": every spell and every activated ability)
        if not ok or (key is None and m["sel"]) or (m["who"] == "players" and (m["sel"] or m["act"] or m["how"].startswith("can"))):
            return None
        return {"kind": "static", "static": "spend_as", "mode": "type" if m["how"].startswith("can") else "color", "filter": key, "effects": [],
                **({"abilities": "all" if everything else "creatures"} if everything or m["act"] else {}),
                **({"players": True} if m["who"] == "players" else {}), **({"no_spells": True} if m["act"] else {})}
    m = STATIC_CASCADE.fullmatch(t)
    if m:  # -- static statics (wave 10B) --
        return _cascade_definition(m)
    m = STATIC_HELPER.fullmatch(t)
    if m:
        ok, key = _filter(m["sel"])
        if not ok:
            return None
        return {"kind": "static", "static": "spell_helper", "keyword": m["kw"], "filter": key, "effects": [],
                **({"from": "exile"} if m["frm"] else {})}  # (wave 17C: "Spells you cast from exile have convoke.")
    m = STATIC_AFFINITY.fullmatch(t)
    if m:
        from app.rules.casting import affinity_pred

        ok, key = _filter(m["sel"])
        if not ok or affinity_pred(m["what"].lower()) is None:
            return None
        return {"kind": "static", "static": "spell_helper", "keyword": "affinity", "what": m["what"].lower(), "filter": key, "effects": []}
    from app.rules import (  # "You have hexproof." (app/rules/player_shields.py); -- prohibitions (wave 22B) --
        life_lock,  # -- can't lose life (wave 29D) -- "Your life total can't change." (app/rules/life_lock.py)
        player_shields,
        prohibitions,
    )

    return prohibitions.static_definition(text) or player_shields.static_definition(text) or life_lock.static_definition(text)


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
    who = {"your opponents": "each_opponent", "each opponent": "each_opponent", "players": "each_player", "each player": "each_player",
           "target player": "target", "target opponent": "target"}[m["who"]]
    sel = {"target player": "player", "target opponent": "opponent"}.get(m["who"])
    until = "next_turn" if "next turn" in (lead or when or "") else "turn"
    return [{"do": "cast_limit", "who": who, "until": until, "filter": key, "from": list(_FROMS[m["frm"]]) if m["frm"] else None,
             "act": act}], sel


def _effect_flash(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    if not m["this"] and not m.string.startswith("until end of turn, "):
        raise ValueError("a duration")  # ("you may cast spells as though they had flash" as an effect: no duration — refused)
    ok, key = _filter(m["sel"])
    if not ok:
        raise ValueError("selector")
    return [{"do": "flash_permission", "filter": key}], None


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


TEMPLATES: list[tuple[re.Pattern[str], Any]] = [_template(EFFECT_CAST, _effect_cast), *_player_templates()]


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
                              "turn": turn, "filter": e.get("filter"), "from": e.get("from"), "act": e.get("act"),
                              "label": label})
        what = _spells_words(e.get("filter"), e.get("from"))
        if e.get("act") == "loyalty":
            what += " or activate loyalty abilities"
        plan.note(f"{plan.name(pid)} can't cast {what} {'this turn' if e['until'] == 'turn' else 'until ' + plan.name(ctx['controller']) + '’s next turn'} ({label})",
                  actor=ctx["controller"])
    return True


def flash_permission(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """"You may cast spells this turn as though they had flash" (601.3b): a stored flash-only permission until cleanup."""
    from app.game.rules_state import Permission

    pid = ctx["controller"]
    label = ctx.get("name") or "An effect"
    plan.rules.permissions.append(Permission(id=secrets.token_hex(4), player=pid, cast=True, zone="any", filter=e.get("filter"),
                                             flash=True, until="end_of_turn", turn=plan.state.turn.number,
                                             source=ctx.get("source_object"), label=f"{label}: as though it had flash"))
    plan.note(f"{plan.name(pid)} may cast {_spells_words(e.get('filter'), None)} this turn as though they had flash ({label})",
              actor=pid)
    return True


def _player_primitives() -> tuple[dict[str, Any], dict[str, Any]]:
    from app.rules import player_shields

    return player_shields.PRIMITIVES, player_shields.RESUME


def _life_primitives() -> dict[str, Any]:
    from app.rules import life_lock

    return life_lock.PRIMITIVES  # -- can't lose life (wave 29D) --


PRIMITIVES = {"cast_limit": cast_limit, "flash_permission": flash_permission, **_player_primitives()[0], **_life_primitives()}
RESUME = dict(_player_primitives()[1])


def turn_began(plan: Plan, skipped: list[tuple[str, int]] | None = None) -> None:
    """500.4 / 800.4m: "until your next turn" limits end as that player's next turn begins (or would have)."""
    r = plan.rules
    turn, active = plan.state.turn.number, plan.active
    ended = {(active, turn), *(skipped or ())}
    r.cast_limits = [x for x in r.cast_limits if not (x.get("until") == "next_turn" and any(
        x.get("controller") == p and n > int(x.get("turn") or 0) for p, n in ended))
        and not (x.get("until") == "turn" and x.get("turn") != turn)]
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
_KINDS = ("cast_limit", "activate_as_haste", "player_shield", "spell_helper", "spell_keyword", "loyalty_rule", "spend_as", "keep_mana", "gy_flashback",
          "cant_enter", "cant_counters", "cant_pay", "cant_cause_sacrifice", "cant_search",  # (wave 22B: app/rules/prohibitions.py)
          "zone_grant",  # (wave 25A: app/rules/zone_grants.py)
          "life_lock")  # (wave 29D: app/rules/life_lock.py)


def _scan(state: GameState, info: CardInfo) -> list[tuple[str, int, Definition]]:
    from app.rules import read_pass

    return read_pass.once(state, info, "cast_limits.scan", lambda: _scan_table(state, info))  # (wave 29A: once per read-only pass)


def _scan_table(state: GameState, info: CardInfo) -> list[tuple[str, int, Definition]]:
    """(permanent, ability index, definition) of every limit / haste-permission static on the battlefield, read
    from copiable values (cheap, cached by what is there); ``_statics`` confirms each with the permanent's
    current characteristics (a "loses all abilities" effect removes it, 613.1f)."""
    from app.rules import scripts
    from app.rules.copying import copy_index
    from app.rules.layers import copiable
    from app.rules.plan import live_players

    r = state.rules
    if r is None:
        return []
    live = tuple(live_players(state))
    copies = copy_index(r)
    key = (live, tuple(sorted((cid, c.controller, c.face_down, c.face, c.flipped, c.card_id or c.name,
                               c.token.text if c.token else "", r.card_mode(cid), copies.get(r.object_id(cid), (0, "")))
                              for cid, c in state.cards.items() if c.zone.endswith(":battlefield"))))
    hit = _CACHE.get(key)
    if hit is not None:
        return hit
    out = []
    for cid, c in state.cards.items():
        if not c.zone.endswith(":battlefield") or c.face_down or c.controller not in live or r.card_mode(cid) == "manual":
            continue
        for index, d in scripts.definitions(copiable(state, c, info)).items():
            if d.get("kind") == "static" and (d.get("static") in _KINDS or d.get("player_shield") or d.get("spell_grants")):  # (wave 28C: spell_grants.py)
                out.append((cid, index, d))
    if len(_CACHE) > 256:
        _CACHE.clear()
    _CACHE[key] = out
    return out


def _statics(state: GameState, info: CardInfo | None, kind: str) -> list[tuple[CardInstance, Definition]]:
    if info is None or state.rules is None:
        return []
    found = [(cid, i, d) for cid, i, d in _scan(state, info) if d["static"] == kind]
    if not found:
        return []
    from app.rules import characteristics as chars
    from app.rules import scripts
    from app.rules.layers import derive

    out = []
    for cid, index, _d in found:
        card = state.cards[cid]
        now = scripts.definitions(derive(state, card, chars.of(card, info), info))
        if now.get(index, {}).get("static") == kind:
            out.append((card, now[index]))
    return out


def _who_ok(who: str, player: str, controller: str, src: CardInstance | None = None, state: GameState | None = None) -> bool:
    if who in ("enchanted", "host_controller"):  # -- attached events (wave 25D) -- the player the Aura is attached to / the controller of the creature it is
        if src is None or state is None:
            return False
        if who == "enchanted":
            return src.attached_player == player
        host = state.cards.get(src.attached_to or "")
        return host is not None and host.zone.endswith(":battlefield") and host.controller == player
    return who == "each" or (who == "opponents" and player != controller) or (who == "you" and player == controller)


def _when_ok(state: GameState, when: str | None, controller: str) -> bool:
    if when == "your_turn":
        return state.turn.active_player == controller
    if when == "combat":
        return state.turn.phase in COMBAT_PHASES
    return True


def _record_live(state: GameState, x: dict[str, Any]) -> bool:
    return x.get("until") != "turn" or x.get("turn") == state.turn.number


def _cast_hit(state: GameState, player: str, card: CardInstance, ch: Characteristics, info: CardInfo | None,
              d: dict[str, Any], resolving: bool = False, source: str | None = None) -> bool:
    """Does this limit forbid ``player`` casting this card as this spell now (``resolving``: as something resolves)?"""
    if d.get("spells") is False:
        return False
    if d.get("sorcery"):  # 307.1
        return resolving or not (state.turn.active_player == player and state.turn.phase in ("main1", "main2")
                                 and not state.zones.get("stack"))
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

        if not spell_matches(state, player, card, ch, key, info, source):  # (source: wave 22B, "with the chosen name")
            return False
    if d.get("max") is not None:
        return _cast_this_turn(state, player, key) >= int(d["max"])
    return True


def _cast_this_turn(state: GameState, player: str, key: str | None) -> int:
    from app.rules import history

    r = state.rules
    if r is None or r.turn_log.turn != state.turn.number:
        return 0
    sel = selectors.from_key(key) if key is not None else None
    return sum(1 for n in r.turn_log.casts if n.player == player
               and (sel is None or history.note_matches(sel, n.types, n.subtypes, n.supertypes, n.colors, n.mv)))


def cast_problem(state: GameState, player: str, card: CardInstance, ch: Characteristics, info: CardInfo | None, *,
                 resolving: bool = False) -> str | None:
    """Why a rule or effect prohibits ``player`` from casting this card as this spell now (601.3), or None. ``resolving``:
    the cast is made as something resolves (608.2g: suspend, cascade, "you may cast … without paying …")."""
    r = state.rules
    if r is None:
        return None
    from app.rules import split_second  # -- split second (wave 8A) -- 702.61a

    if (why := split_second.problem(state, info, "cast other spells", card.id)) is not None:
        return why
    for x in r.cast_limits:
        if x.get("player") == player and _record_live(state, x) and _cast_hit(state, player, card, ch, info, x):
            return f"{x.get('label') or 'An effect'}: you can't cast {_spells_words(x.get('filter'), x.get('from'))} now"
    for src, d in _statics(state, info, "cast_limit"):
        if _who_ok(d["who"], player, src.controller, src, state) and _when_ok(state, d.get("when"), src.controller) \
                and _cast_hit(state, player, card, ch, info, d, resolving, src.id):
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
    if act == "ace":
        return on_field and bool({"Artifact", "Creature", "Enchantment"} & set(ch.types))
    if act == "nonmana":
        return not mana
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
        if d.get("act") and _who_ok(d["who"], player, src.controller, src, state) and _when_ok(state, d.get("when"), src.controller) \
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
    return info is not None and any(d.get(key) and (src.id == card.id if d["who"] == "self" else src.controller == card.controller)
                                    for src, d in _statics(state, info, "loyalty_rule"))


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
             and (d["abilities"] == "all" or (ch.is_creature and card.controller == src.controller))}
    return "type" if "type" in modes else "color" if modes else None


def as_though_haste(state: GameState, card: CardInstance, info: CardInfo | None) -> bool:
    """302.6 / 602.5a: may this creature's {T} / {Q} abilities be activated as though it had haste?"""
    if info is None:
        return False
    return any(src.controller == card.controller for src, _ in _statics(state, info, "activate_as_haste"))


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
    from app.rules.permissions import spell_matches

    return nxt | {d["keyword"] for src, d in found if src.controller == player and d["keyword"] != "affinity"
            and (d.get("from") is None or card.zone.endswith(":exile")
                 or (card.stack_info is not None and "Cast from exile" in card.stack_info.tags))
            and (d.get("filter") is None or spell_matches(state, player, card, spell, d["filter"], info))}


def granted_affinities(state: GameState, player: str, card: CardInstance, spell: Characteristics, info: CardInfo) -> list[str]:
    """-- static_other sweep (wave 17C) -- the "affinity for X" words that permanents ``player`` controls give this spell (702.41a)."""
    from app.rules import (
        spell_grants,  # -- spell grants (wave 28C) -- "The next spell you cast this turn has affinity for artifacts."
    )
    from app.rules.permissions import spell_matches

    return [d["what"] for src, d in _statics(state, info, "spell_helper") if src.controller == player and d["keyword"] == "affinity"
            and (d.get("filter") is None or spell_matches(state, player, card, spell, d["filter"], info))] + [
        g.what for g in spell_grants.pending(state, player, card, spell, info, "affinity")]


def from_ok(d: Definition, card: CardInstance) -> bool:
    """-- static_other sweep (wave 17C) -- a granted keyword's "from exile" / "from your hand" zone, for a spell not yet cast (the card is
    where it is cast from) — "first … each turn" statics are not offered ahead (conspire reads none)."""
    zone = d.get("from")
    where = card.zone.rsplit(":", 1)[-1]
    return d.get("first") is None and (zone is None or (where != "hand" if zone == "not_hand" else where == zone))


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
        if d.get("first") == "turn" and plan.rules.spells_this_turn(player, turn) > 0:
            continue
        if d.get("first") == "from" and (cast_from is None or any(c.cast_from == cast_from or (zone == "not_hand" and c.cast_from != "hand")
                                                                  for c in earlier)):
            continue
        if d.get("filter") is not None and not spell_matches(plan.state, player, card, spell, d["filter"], plan.info):
            continue
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
        if d.get("static") == "permission" and d.get("self") and d.get("flash") and d.get("if") is not None:
            ctx = {"controller": player, "source_card": card.id, "source_object": state.rules.object_id(card.id) if state.rules else None}
            if conditions.holds(Plan.view(state, player, info), ctx, d["if"]):
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
    found = [cast_problem(plan.state, player, card, chars.as_cast(card, plan.info, f), plan.info, resolving=True) for f in faces]
    return found[0] if all(found) else None

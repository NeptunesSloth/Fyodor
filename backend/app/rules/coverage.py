"""How much of a card the rules engine automates: FULL / PARTIAL / REVIEW / MANUAL.

A card is broken into *features*: what it needs to be played (a land drop, casting a spell,
fighting in combat) and one feature per ability line (a keyword, a mana ability, a scripted
ability, or free text). Coverage compares those features with ``SUPPORTED``, the set of things
the engine really implements. ``SUPPORTED`` only grows when a feature lands *with* tests, so the
report is honest: a card is FULL only when every part of it is automated.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Literal

from app.rules import cards as scripts
from app.rules import protection
from app.rules import scripts as templates
from app.rules.characteristics import HALVES, Characteristics, half_from_data, printed_from_data
from app.rules.mana import parse_mana_ability
from app.rules.oracle import AbilityText

Level = Literal["FULL", "PARTIAL", "REVIEW", "MANUAL"]

# Everything the engine automates today. Add a feature only together with its scenario tests.
SUPPORTED: set[str] = {
    "play:land",  # play_land: timing, one land per turn, priority (M14)
    "cast:spell",  # cast_spell: timing, costs (auto-paid), commander tax, the stack, resolution (M15)
    "mana:ability",  # {T}[, Sacrifice this]: Add … mana abilities, incl. basic land types (M15)
    "combat",  # attacking and blocking, combat damage (M15c)
    # 306/606: loyalty on entering however it enters (306.5b), loyalty abilities (606.3-606.6, incl.
    # −X), damage removing loyalty (120.3c), attacking planeswalkers, 0 loyalty (704.5i):
    # test_rules_loyalty.py, test_rules_combat.py
    "planeswalker",
    # M16: templated Oracle text (app/rules/scripts.py): triggers, spell effects, activated abilities,
    # "enters tapped"; every template has parsing and scenario tests. Static grants ("Other Elves you
    # control get +1/+1 and have haste.", "~ gets +2/+2 as long as …") are app/rules/statics.py, applied
    # in layer order by app/rules/layers.py (test_rules_statics.py).
    "templates",
}

# Replacement and prevention effects the engine applies (app/rules/replacements.py; CR 614 / 615),
# each with scenario tests in tests/test_rules_replacements.py. A parsed definition of another
# kind counts as manual until it is listed here.
SUPPORTED_REPLACEMENTS: set[str] = {
    "enters_tapped",  # "~ enters tapped [unless …]" (614.1d), on every path onto the battlefield
    "pay_life_or_tapped",  # shock lands (614.1c, 614.12a): a private decision on every path
    "enters_choice",  # "As ~ enters, choose a color / creature type / …" (614.12a): chosen before it enters, recorded on it
    "enters_with_counters",  # "~ enters [tapped] with N … counters on it [for each …]" (614.1c, 122.6)
    "exile_instead",  # "If ~ would die / be put into a graveyard from anywhere, exile it instead" (own and statics)
    "prevent",  # "Prevent all [combat] damage that would be dealt [to …] [by …] [this turn]" (615)
}
# -- copy system (wave 2F): "You may have ~ enter as a copy of …[, except …]" (707.5, 614.1c, 614.12a;
# app/rules/copying.py, tests/test_rules_copy.py). Copies of spells and abilities, token copies and
# "becomes a copy" are templates (their definitions parse only in the wording the engine carries out).
SUPPORTED_REPLACEMENTS.add("enter_as_copy")
# -- "this way" outcomes (wave 4A) -- "As ~ enters, you may reveal an X or Y card from your hand. If you don't, ~
# enters tapped." (614.1c, 614.12a, 701.20a; app/rules/reveal_lands.py, tests/test_rules_wave4a_this_way.py)
SUPPORTED_REPLACEMENTS.add("reveal_or_tapped")
# -- entering for a cost (wave 5G) -- "If ~ would enter, you may discard a land card / sacrifice a Swamp instead. If you
# do, put ~ onto the battlefield. If you don't, put it into its owner's graveyard." (614.1a, 614.12a, 614.13, 118.12;
# app/rules/enter_cost.py, tests/test_rules_wave5g_if_you_do.py)
SUPPORTED_REPLACEMENTS.add("enter_cost")


# -- modal triggered/activated abilities (wave 1A) ---------------------------------------------------
# The forms of modal ability the engine carries out (app/rules/modal_abilities.py; CR 700.2, 603.3c,
# 602.2b), each with scenario tests in tests/test_rules_modal_abilities.py. A modal ability's definition
# names its form; a form not listed here stays manual. Refused on purpose (the grammar never reads them):
# "You may choose the same mode more than once", "choose X / up to X", a mode with "you may", several targets
# or a division, and "up to"/"any number" modes on an activated ability (choosing none isn't modelled).
# (Read since wave 3R1: "choose one at random", "each mode must target a different player", "choose both
# instead", reflexive "When you do, choose …" — the entries at the end of the set.)
SUPPORTED_MODAL_ABILITIES: set[str] = {
    "triggered",  # "When/Whenever/At …, choose one —": announced as it's put on the stack (603.3c, 700.2b)
    "activated",  # "{cost}: Choose one —": announced before targets and costs (602.2b, 601.2b)
    "loyalty",  # "+1: Choose one —" (606.2 → 602.2b)
    "memory:game",  # "choose one that hasn't been chosen —": per object, for as long as it is that object
    "memory:turn",  # "choose one that hasn't been chosen this turn —": per object, per turn
    # -- refused modal/conditional (wave 3R1): tests/test_rules_refused_r1.py --
    "random",  # "choose one at random —" (triggered): among the modes that can be chosen, as it goes on the stack
    "different_players",  # "Each mode must target a different player." (every mode targets a player of one kind)
    "instead",  # "Choose one. If [condition], [you may] choose both instead." (checked as it goes on the stack)
    # (reflexive "When you do, choose …" (603.12) is the "triggered" form inside a reflexive trigger: effects.reflexive)
}


def modal_supported(d: dict[str, Any]) -> bool:
    """A modal triggered / activated ability (or one of its mode lines, ``kind`` "mode") is automated
    only when its form is listed above."""
    modal = d if d.get("kind") == "mode" else d.get("modal") or {}
    if any(modal.get(k) and k not in SUPPORTED_MODAL_ABILITIES for k in ("random", "different_players", "instead")):
        return False  # -- refused modal/conditional (wave 3R1) --
    return modal.get("form") in SUPPORTED_MODAL_ABILITIES and (
        modal.get("memory") is None or f"memory:{modal['memory']}" in SUPPORTED_MODAL_ABILITIES)


def definition_supported(d: dict[str, Any]) -> bool:
    """A replacement / prevention definition is automated only when its kind is listed above."""
    if d.get("kind") == "mode" or (d.get("modes") and d.get("kind") in ("triggered", "activated")):
        return modal_supported(d)  # (wave 1A) a modal triggered / activated ability
    # -- reanimation (wave 3R) -- "return this card from your graveyard": only an activated ability works from
    # there (113.6m); a trigger or static line would need the graveyard scanned for triggers
    if d.get("kind") != "activated" and '"self_gy"' in json.dumps(d, default=str):
        from app.rules.triggers import graveyard_trigger_ok  # -- refused zones/sized (wave 3R4) -- (113.6m)

        if not graveyard_trigger_ok(d):
            return False
    # -- refused grants/replacements (wave 3R2) -- a flashback cost never stated
    from app.rules import graveyard_grants

    if graveyard_grants.unsupported(d):
        return False
    verdict = stage2_supported(d)  # -- replacement effects stage 2 (wave 2E) --
    if verdict is not None:
        return verdict
    if d.get("kind") == "replacement":
        return d.get("replacement") in SUPPORTED_REPLACEMENTS
    if d.get("kind") == "static" and d.get("static") in ("prevent", "exile_instead"):
        return d["static"] in SUPPORTED_REPLACEMENTS
    if d.get("kind") == "spell" and any(e.get("do") == "prevent_all" for e in d.get("effects") or []):
        return "prevent" in SUPPORTED_REPLACEMENTS
    return True


# -- counters & designations (wave 3E) -----------------------------------------------------------------
# Player counters with rules (energy 107.14, experience, poison 704.5c, rad 728), the monarch (725), the
# initiative (726), venture into the dungeon (701.49, 309) and the Ring tempts you (701.54) are carried out
# by app/rules/designations.py. A card that ventures (or takes the initiative: 726.2 ventures into Undercity)
# is carried out, but it is FULL only while every room it may lead into is automated too
# (designations.room_definition; an "engine:dungeon" feature otherwise): goad (Undercity's Arena), Oubliette,
# Mad Wizard's Lair and Throne of the Dead Three are resolved by hand.
def counters_designations_gap(d: dict[str, Any]) -> str | None:
    from app.rules import designations

    return designations.unautomated(d)
# -- end counters & designations (wave 3E) --


# -- replacement effects stage 2 (wave 2E) -----------------------------------------------------------
# The events app/rules/replace.py applies statics to (app/rules/replace_grammar.py) and the ops it
# carries out for each, every one with scenario tests in tests/test_rules_replacements2.py. A parsed
# static with another op stays manual.
SUPPORTED_REPLACE_OPS: dict[str, frozenset[str]] = {
    "tokens": frozenset({"mul", "add"}),  # 614.16: Parallel Lives, Doubling Season, Xorn
    "counters": frozenset({"mul", "add"}),  # 122.6, 614.16: Hardened Scales, Winding Constrictor, Doubling Season
    "player_counters": frozenset({"add"}),  # Winding Constrictor ("If you would get one or more counters")
    "draw": frozenset({"win", "skip", "steal", "draw"}),  # 121.6, 614.11: Laboratory Maniac, Notion Thief
    "life": frozenset({"mul", "add", "set", "lose"}),  # 119.10: Boon Reflection, Sulfuric Vortex, Tainted Remedy
    "damage": frozenset({"mul", "add", "sub", "half", "prevent", "prevent_all_but", "prevent_all"}),  # 614, 615.10
}
# -- refused grants/replacements (wave 3R2) -- 614.9 redirection statics (Pariah, Palisade Giant: app/rules/source_shields.py,
# tests/test_rules_refused_grants.py)
SUPPORTED_REPLACE_OPS["damage"] = SUPPORTED_REPLACE_OPS["damage"] | {"redirect"}
# -- damage wordings (wave 6B) -- "prevent half that damage, rounded up" (Gisela, Blade of Goldnight; 615)
SUPPORTED_REPLACE_OPS["damage"] = SUPPORTED_REPLACE_OPS["damage"] | {"prevent_half_up"}
# … and token creation adding a different token (Peregrin Took, Chatterfang: app/rules/extra_tokens.py)
SUPPORTED_REPLACE_OPS["tokens"] = SUPPORTED_REPLACE_OPS["tokens"] | {"extra"}
SUPPORTED_REPLACEMENTS |= {
    "enters_tapped_others",  # 614.1d, 614.12: "Creatures your opponents control enter tapped."
    "exile_if_dies",  # "If that creature / a creature dealt damage this way would die this turn, exile it instead." (611.2a)
}


def stage2_supported(d: dict[str, Any]) -> bool | None:
    """Stage 2 definitions: automated when their event and op are listed above (None: not one, or
    nothing here to object to)."""
    if d.get("kind") == "static" and d.get("static") == "replace":
        return (d.get("op") or {}).get("do") in SUPPORTED_REPLACE_OPS.get(str(d.get("event")), frozenset())
    if d.get("kind") == "static" and d.get("static") == "enters_tapped_others":
        return "enters_tapped_others" in SUPPORTED_REPLACEMENTS
    effects = d.get("effects") or []
    if any(e.get("do") == "exile_if_dies" for e in effects) and "exile_if_dies" not in SUPPORTED_REPLACEMENTS:
        return False
    for e in effects:  # "Until end of turn, if …" / "If … this turn, …": a record of a statics' wording
        if e.get("do") == "replace_record" and (e.get("op") or {}).get("do") not in SUPPORTED_REPLACE_OPS.get(str(e.get("event")), ()):
            return False
    return None
# -- end replacement effects stage 2 (wave 2E) --

# Activation restrictions and trigger limits (app/rules/restrictions.py, test_rules_restrictions.py)
# are part of "templates": an activated ability whose trailing "Activate only …" sentence the engine
# reads (as a sorcery / instant, once or N times each turn, once, during your turn / upkeep /
# combat / a step, before attackers are declared, if a condition app/rules/conditions.py reads — the
# turn's history, card types among graveyard cards, total power, your commander, the monarch … since
# conditional clauses, wave 1B) is automated with it enforced; any other restriction wording leaves the
# ability manual. Refused on purpose (never guessed): "Do this only once each turn." (603.2h: the
# action itself has to be recorded as it's taken), "Activate only if …" conditions the engine can't
# evaluate ("this creature is attacking", "you control the most creatures", what was cast and how).
# Keyword abilities the engine implements (each needs tests before it is listed here).
SUPPORTED_KEYWORDS: set[str] = {
    # combat (M15c): legality and damage, each covered by test_rules_combat.py
    "flying", "reach", "vigilance", "trample", "deathtouch", "lifelink", "first strike", "double strike",
    "haste", "defender", "menace",
    # state-based actions (M15b)
    "indestructible",
    # M16: casting timing and targeting (test_rules_effects.py)
    "flash", "hexproof", "shroud",
    # evasion (test_rules_combat.py::test_evasion, landwalk tests)
    "plainswalk", "islandwalk", "swampwalk", "mountainwalk", "forestwalk", "desertwalk",
    "shadow", "horsemanship", "fear", "intimidate", "skulk",
    # triggered keywords (app/rules/scripts.py KEYWORD_TRIGGERS)
    "prowess",
    # damage as counters (test_rules_infect.py)
    "wither", "infect",
    # exalted (app/rules/triggers.py _exalted, test_rules_infect.py)
    "exalted",
    # characteristic-defining (app/rules/characteristics.py changeling)
    "changeling", "devoid", "cascade", "persist", "undying", "flanking", "delve", "improvise", "rebound", "storm",
    # costs (casting._convoke_sources)
    "convoke",
    # 702.125 undaunted: costs {1} less for each opponent (permissions.self_reduction)
    "undaunted",
    # -- counters & designations (wave 3E) -- 702.145 day and night (app/rules/designations.py day_night_sync)
    "daybound", "nightbound",
    # -- token & pump wordings (wave 6C) -- 702.147 decayed (app/rules/decayed.py, test_rules_wave6c_tokens_pumps.py)
    "decayed",
}
# -- sagas & attached-object triggers (wave 3S) --------------------------------------------------------
# Sagas (714, app/rules/sagas.py; tests/test_rules_sagas.py): lore counters as it enters and at the
# precombat main phase, chapter abilities (a chapter line is automated when its effect parses: it is a
# template), the 714.4 sacrifice; read ahead (702.155): the number chosen as it enters, skipped chapters.
SUPPORTED_KEYWORDS.add("read ahead")
SUPPORTED_KEYWORDS.add("split second")  # -- split second (wave 8A) -- 702.61 (app/rules/split_second.py, cast_limits)
# -- end sagas & attached-object triggers (wave 3S) --


# Keyword actions (CR 701) the engine carries out when an ability's text calls for them (a template
# in app/rules/scripts.py over a primitive in app/rules/effects.py or app/rules/keyword_actions.py).
# Coverage of a card is decided by its templates parsing; this set is the honest list for the
# mechanics report (tools/commander_coverage.py). Each entry has scenario tests.
SUPPORTED_KEYWORD_ACTIONS: set[str] = {
    "counter", "create", "destroy", "discard", "exile", "mill", "regenerate", "sacrifice", "scry", "search", "surveil",
    "tap and untap", "proliferate", "investigate", "explore",
    # test_rules_keyword_actions.py
    "amass", "connive", "monstrosity", "bolster", "support",
    # -- counters & designations (wave 3E): app/rules/designations.py, tests/test_rules_designations.py
    # (venture into Undercity's Arena room — goad — is still resolved by hand)
    "venture into the dungeon", "the ring tempts you",
    # -- keyword actions & face-down (wave 3F) -- test_rules_keywords3f.py
    "goad", "manifest", "manifest dread", "cloak", "earthbend", "incubate",
}
SUPPORTED_KEYWORD_ACTIONS.add("populate")  # -- token copies & attach on entry (wave 5J) -- test_rules_wave5j_token_copies.py


# -- refusals (agent T) ------------------------------------------------------------------------------
# Wordings the grammar reads far enough to know it must NOT automate them, and why. A card with
# one of these stays PARTIAL/MANUAL on purpose; the reason names the missing piece so the gap
# report can rank it (never a guess at what the card does). ``refusal(text)`` gives the reason.
REFUSED: tuple[tuple[re.Pattern[str], str], ...] = (
    # (fight (701.14) and "choose … target" are read now: effects.fight, effects.choose_targets)
    (re.compile(r"\bfor each target beyond the first\b", re.I),
     "a cost per extra target (601.2b/601.2c): the cost grammar doesn't read it"),
    # (-- graveyard exile (wave 4J) -- "exile target player's graveyard" itself is read: app/rules/graveyard_exile.py)
    (re.compile(r"(?<!exile )\btarget (?:player|opponent)'s (?:graveyard|hand|library)\b", re.I),
     "a target player's zone as the object set (\"exile all creature cards from target player's graveyard\"): the "
     "effects can't reach the chosen player from a selector"),
    (re.compile(r"\btarget \w+(?: \w+)* that player controls\b", re.I),
     "a selector relative to a player named earlier (\"target creature that player controls\"): not modelled"),
    # ("up to X target …": read now, the number of targets announced with X, 601.2c — wave 4K)
    # (copy system, wave 2F / 3R3: "copy target spell", and "copy it / that spell" for the spell a cast trigger
    # was about, are read now: app/rules/copying.py)
    (re.compile(r"\bshuffles? up to \w+ target cards? from their graveyard\b", re.I),
     "cards from a target player's graveyard (a zone bound to an earlier target): not modelled"),
    (re.compile(r"\btarget creature with the greatest\b", re.I), "\"the greatest … among\" (a computed extreme): not modelled"),
    (re.compile(r"(?<!switch )\btarget creature's power and toughness\b", re.I),  # (switching: wave 7E, choice_grants.switch_pt)
     "switching or reading a target's P/T pair: not modelled"),
    # -- conditional / instead clauses (wave 1B) --------------------------------------------------------
    # Conditions app/rules/conditions.py deliberately doesn't read: the clause (or the whole ability) stays manual.
    # -- refused modal/conditional (wave 3R1) -- how a spell was cast (the zone, the caster's main phase, the mana of
    # each type spent) is now on its payment record (conditions._cast_how); what stays refused:
    (re.compile(r"\b(?:entered|was put onto the battlefield) from (?:your|a) (?:library|graveyard)\b", re.I),
     "the zone a permanent entered from isn't recorded with the object: not modelled"),
    (re.compile(r"\b(?:\{S\}|mana from [^.,]+) (?:of [^.,]+ )?was spent to (?:cast|activate)\b|\bwas spent to activate\b", re.I),
     "snow mana, the source of the mana spent, and mana spent on an ability aren't recorded (601.2h): not modelled"),
    # (wave 3E: "you've completed a dungeon" and "it's day / night" are read now: app/rules/designations.py)
    # (-- this-turn history (wave 4D) -- "this is the second time this ability has resolved this turn" is read now:
    # app/rules/history.py counts each object's ability resolutions per turn)
)


# -- keyword actions & face-down (wave 3F) -- refused on purpose, with the missing piece named
REFUSED += (
    (re.compile(r"\bairbend", re.I),
     "airbend (701.65): needs a cast-from-exile permission whose alternative cost is {2}, for the card's owner"),
    (re.compile(r"\bwaterbend", re.I),
     "waterbend (701.67): a cost whose generic part may be paid by tapping artifacts/creatures isn't modelled"),
    (re.compile(r"\bmanifests? the top card of (?:that player's|target player's|an opponent's)", re.I),
     "manifesting another player's card under your control: not modelled"),
)


# -- refused look/cast-free (wave 3R5) -- look-at-the-top and cast-without-paying forms still left to the players
# (the ones read now: app/rules/permissions.py free_cast, app/rules/looking.py; tests/test_rules_refused_look.py)
REFUSED += (
    (re.compile(r"\b(?:of the chosen (?:creature |card )?type|with (?:the|that) chosen name|choose a (?:nonland )?card name)\b", re.I),
     "a value chosen as the ability resolves used as a filter (\"cards of the chosen type\", \"a card with the chosen name\"): "
     "no selector reads the resolution's choice, and naming a card would need a prompt over the whole card pool"),
    (re.compile(r"\bchoose two cards in your hand drawn this turn\b", re.I),
     "Sylvan Library: which hidden cards in a hand were drawn this turn isn't tracked per card"),
    (re.compile(r"\bas many times as you choose, you may pay 1 life, put those cards on the bottom\b", re.I),
     "Lim-Dûl's Vault: a repeated look-and-pay loop, then a shuffle that keeps the last cards on top, isn't modelled"),
    (re.compile(r"\byou may play (?:that card|it|one of those cards) without paying\b", re.I),
     "\"you may play that card\" as the ability resolves: playing a land during a resolution (305.2a: it uses a land play) "
     "isn't modelled; free casts never play lands"),
    (re.compile(r"\b(?:any number of|up to \w+) (?!target\b)[^.]*?with total mana value \w+ or less\b", re.I),  # (targets: wave 3R4)
     "choosing a set of cards or spells under a total mana value limit: not modelled"),
    (re.compile(r"\bcast (?:the copy|the copies|any number of the copies|those copies)\b", re.I),
     "casting a copy of a card (707.12): belongs to the copy system"),
    (re.compile(r"\bcast target [^.]*with mana value less than or equal to [^.]*from [^.]*graveyard\b", re.I),
     "a target card whose mana value limit is read as it resolves: the target's legality would change with it"),
    (re.compile(r"\b(?:each opponent|each player) (?:exiles|reveals) cards from the top of their library until\b", re.I),
     "\"until\" in several libraries at once: the resolution keeps one found card"),
    (re.compile(r"\btapped and attacking (?:that player|defending player)\b", re.I),
     "put onto the battlefield attacking a player the effect names (508.4: its choice isn't the controller's)"),
)


def refusal(text: str) -> str | None:
    """Why the engine refuses to automate this wording, if it is a known refusal (else None)."""
    for pattern, reason in REFUSED:
        if pattern.search(text):
            return reason
    return None


# Cycling / typecycling with a plain mana cost (casting.cycle); "Cycling—Pay 2 life" and friends stay manual.
_MANA_CYCLING = re.compile(r"(?:(?:basic )?[a-z]+)?cycling (?:\{[^}]+\})+")


_MANA_FLASHBACK = re.compile(r"flashback (?:\{[^}]+\})+")


# 702.124a: partner abilities modify deck construction and "function before the game begins":
# during the game there's nothing to do (pairings are checked by app/rules/commander.py and the
# deck checks). "Partner with [name]" also has an enters trigger (702.124j): not listed here.
DECKBUILDING_KEYWORDS = {"partner", "choose a background", "doctor's companion", "friends forever"}


def _keyword_supported(kw: str, line: str) -> bool:
    if kw in DECKBUILDING_KEYWORDS:
        if line.strip().lower().startswith("partner with"):  # -- keyword pieces (wave 8A) -- 702.124j's enters trigger
            from app.rules import keyword_triggers

            return keyword_triggers.partner_with_definition(line) is not None
        return True
    if kw in ("enchant", "equip"):  # app/rules/attachments.py: the wordings it maps
        from app.rules import attachments

        return attachments.supported_keyword(kw, line)
    if kw == "protection":  # DEBT for the qualities app/rules/protection.py understands
        return protection.supported(line)
    if kw == "affinity":  # casting.affinity_filter
        from app.rules.casting import affinity_filter  # casting imports coverage (via engine)

        return affinity_filter(Characteristics(name="", abilities=(AbilityText(index=0, text=line, kind="keywords",
                                                                              keywords=("affinity",)),))) is not None
    if kw == "echo":  # triggers.echo_cost: a mana echo cost
        return re.fullmatch(r"echo (?:\{[^}]+\})+", line.strip().rstrip(".").lower()) is not None
    if kw in ("morph", "megamorph"):  # casting.morph_cost: a mana morph cost
        return re.fullmatch(r"(?:mega)?morph (?:\{[^}x]+\})+", line.strip().rstrip(".").lower()) is not None  # (no X: wave 3F)
    if kw == "disguise":  # -- keyword actions & face-down (wave 3F) -- casting.disguise_cost: a mana disguise cost
        return re.fullmatch(r"disguise (?:\{[^}x]+\})+", line.strip().rstrip(".").lower()) is not None
    if kw == "toxic":  # -- counters & designations (wave 3E) -- combat.py reads "toxic N" anywhere in a keyword line ("Menace, toxic 1")
        return re.search(r"(?:^|, )toxic \d+(?:,|$)", re.sub(r"\s*\(.*?\)", "", line).strip().rstrip(".").lower()) is not None
    if kw in ("bushido", "renown", "bloodthirst", "soulshift", "toxic", "fabricate", "firebending"):  # numbered keywords (firebending: wave 3F) (triggers.py, engine.enter_with_counters)
        return re.fullmatch(rf"{kw} \d+", line.strip().rstrip(".").lower()) is not None
    if kw == "suspend":  # casting.suspend_info: "Suspend N—{cost}"
        return re.fullmatch(r"suspend \d+\s*[—-]\s*(?:\{[^}]+\})+", line.strip().rstrip(".").lower()) is not None
    if kw == "cumulative upkeep":  # triggers.cumulative_cost: a mana cost
        return re.fullmatch(r"cumulative upkeep (?:\{[^}]+\})+", line.strip().rstrip(".").lower()) is not None
    from app.rules import (
        keyword_triggers,  # -- static wordings (wave 6E) -- battle cry, ingest … (their CR meaning)
    )

    if kw == "sunburst":  # -- keyword mechanics (wave 9D) -- 702.44a: replacements.entering_counters (not "Modular—Sunburst")
        return bool(keyword_triggers.pieces(kw, line)) and re.fullmatch(r"(?:sunburst)(?:, sunburst)*", re.sub(
            r"\s*\(.*?\)", "", line).strip().rstrip(".").lower()) is not None
    if kw in keyword_triggers.MEANINGS:
        return keyword_triggers.supported(kw, line)
    if kw == "ward":  # -- static wordings (wave 6E) -- every ward piece of the line has a mana cost (triggers.ward_costs)
        from app.rules.triggers import WARD, ward_pieces

        pieces = ward_pieces(line)
        return bool(pieces) and all(WARD.fullmatch(p) for p in pieces)
    if kw in ("unearth", "dash", "buyback", "madness", "ward", "evoke"):  # casting.keyword_cost: a mana cost
        return re.fullmatch(rf"{kw} (?:\{{[^}}]+\}})+", line.strip().rstrip(".").lower()) is not None
    if kw in ("kicker", "multikicker"):  # casting.cost_with_kicker: one mana kicker cost
        from app.rules.costs import kicker_line

        return kicker_line(line)
    if kw == "transmute":  # -- refused zones/sized (wave 3R4) -- casting.transmute: a mana transmute cost (702.53a)
        from app.rules.casting import TRANSMUTE

        return TRANSMUTE.fullmatch(line.strip().rstrip(".")) is not None
    if kw == "crew":  # casting.crew: "Crew N"
        return re.fullmatch(r"crew \d+", line.strip().rstrip(".").lower()) is not None
    if kw == "flashback":  # casting.flashback_cost: a mana flashback cost
        return _MANA_FLASHBACK.fullmatch(line.strip().rstrip(".").lower()) is not None
    if kw.endswith("cycling"):
        return _MANA_CYCLING.fullmatch(line.strip().rstrip(".").lower()) is not None
    return kw in SUPPORTED_KEYWORDS


@dataclass(frozen=True)
class Feature:
    id: str  # e.g. "play:land", "cast:spell", "combat", "keyword:flying", "mana:intrinsic", "text:2"
    label: str  # human readable ("Flying", "{T}: Add {G}.", "Play as a land")
    supported: bool


@dataclass(frozen=True)
class Coverage:
    level: Level
    name: str
    oracle_id: str | None
    features: tuple[Feature, ...] = field(default_factory=tuple)
    review_needed: bool = False  # a script exists but the Oracle text changed since it was validated

    @property
    def manual_parts(self) -> list[str]:
        return [f.label for f in self.features if not f.supported]

    def as_dict(self) -> dict[str, Any]:
        return {
            "level": self.level,
            "name": self.name,
            "oracle_id": self.oracle_id,
            "features": [{"id": f.id, "label": f.label, "supported": f.supported} for f in self.features],
            "manual_parts": self.manual_parts,
            "review_needed": self.review_needed,
        }


def features_of(ch: Characteristics) -> list[Feature]:
    script = scripts.trusted(ch.oracle_id, ch.oracle_text)
    templated = {i for i, d in templates.definitions(ch).items() if definition_supported(d)}
    if ch.is_instant_or_sorcery:
        whole = templates.spell_definition(ch)
        if whole is None or not definition_supported(whole):
            templated = set()  # a spell is automated as a whole or resolved by hand
        elif whole.get("modes"):
            templated = {ab.index for ab in ch.abilities if ab.kind != "keywords"}  # a modal spell (700.2)
    out: list[Feature] = []

    def add(fid: str, label: str, ok: bool | None = None) -> None:
        out.append(Feature(fid, label, fid in SUPPORTED if ok is None else ok))

    if ch.is_land:
        add("play:land", "Play it as your land for the turn")
    elif ch.types:
        add("cast:spell", "Cast it (timing, costs, the stack)")
    if ch.is_creature:
        add("combat", "Attack and block")
    if "Planeswalker" in ch.types:
        add("planeswalker", "Loyalty and damage to planeswalkers")
    if "Battle" in ch.types:  # 310 (app/rules/battles.py): a Siege's defeat is cast transformed by hand (310.12b)
        add("battle", "Defense, protector, attacks (310)" + ("; casting it transformed when defeated is by hand"
                                                            if "Siege" in ch.subtypes else ""), "Siege" not in ch.subtypes)
    for ab in ch.abilities:
        if script is not None and ab.index in script.covers:
            add(f"script:{ab.index}", ab.text, True)
        elif ab.kind == "keywords":
            for kw in ab.keywords:
                add(f"keyword:{kw}", kw.capitalize(), _keyword_supported(kw, ab.text))
        elif ab.kind == "mana":
            add("mana:ability", ab.text, "mana:ability" in SUPPORTED and parse_mana_ability(ab.text) is not None)
        else:
            add(f"text:{ab.index}", ab.text, ab.index in templated)
    # -- counters & designations (wave 3E) -- the dungeon rooms a venture may lead into (automated or not)
    defs = templates.definitions(ch)
    gaps = {g for i in templated if i in defs and (g := counters_designations_gap(defs[i])) is not None}
    if ch.is_instant_or_sorcery and templated and (whole := templates.spell_definition(ch)) is not None:
        gaps |= {g for g in [counters_designations_gap(whole)] if g is not None}
    for gap in sorted(gaps):
        add("engine:dungeon", gap[0].upper() + gap[1:], False)
    return out


def of_characteristics(ch: Characteristics) -> Coverage:
    feats = tuple(features_of(ch))
    supported = sum(1 for f in feats if f.supported)
    if feats and supported == len(feats):
        level: Level = "FULL"
    elif supported:
        level = "PARTIAL"
    else:
        level = "MANUAL"
    stale = scripts.get(ch.oracle_id) is not None and scripts.trusted(ch.oracle_id, ch.oracle_text) is None
    if stale:
        level = "REVIEW"  # a script exists, but for different Oracle text: never claim FULL on a guess
    return Coverage(level=level, name=ch.name, oracle_id=ch.oracle_id, features=feats, review_needed=stale)


def of_card_data(data: dict[str, Any]) -> Coverage:
    """Coverage of a card from the card database (all faces of a double-faced card count)."""
    faces = data.get("faces") or []
    if len(faces) > 1:  # double-faced, split, adventure, flip …: each face's text on its own (no "//" line)
        halves = data.get("layout") in HALVES  # split cards / adventures: each half is its own spell
        parts = [of_characteristics(half_from_data(data, i) if halves else printed_from_data(data, i))
                 for i in range(len(faces))]
        feats = tuple(f for p in parts for f in p.features)
        supported = sum(1 for f in feats if f.supported)
        level: Level = "FULL" if supported == len(feats) and feats else ("PARTIAL" if supported else "MANUAL")
        review = any(p.review_needed for p in parts)
        if review:
            level = "REVIEW"
        return Coverage(level=level, name=str(data.get("name") or ""), oracle_id=data.get("oracle_id"), features=feats,
                        review_needed=review)
    return of_characteristics(printed_from_data(data, 0))


def ability_supported(ch: Characteristics, index: int) -> bool:
    """Whether the engine can carry out ability ``index`` of this object by itself."""
    script = scripts.trusted(ch.oracle_id, ch.oracle_text)  # a script for other Oracle text: by hand
    if script is not None and index in script.covers:
        return True
    ab = next((a for a in ch.abilities if a.index == index), None)
    if ab is None:
        return False
    if ab.kind == "keywords":
        return all(k in SUPPORTED_KEYWORDS for k in ab.keywords)
    if ab.kind == "mana":
        return "mana:ability" in SUPPORTED and parse_mana_ability(ab.text) is not None
    if ch.is_instant_or_sorcery:
        whole = templates.spell_definition(ch)
        return whole is not None and definition_supported(whole)
    d = templates.definitions(ch).get(index)
    return d is not None and definition_supported(d)

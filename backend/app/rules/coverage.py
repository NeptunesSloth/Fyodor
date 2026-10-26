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
from app.rules import keyword_triggers, protection
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
    "enters_numeric_roll",  # Exact X-d6 entry receipt, resolved before native entering counters.
    "enters_choice",  # "As ~ enters, choose a color / creature type / …" (614.12a): chosen before it enters, recorded on it
    "enters_with_counters",  # "~ enters [tapped] with N … counters on it [for each …]" (614.1c, 122.6)
    "enters_turn_down",  # "As ~ enters, turn all other nontoken creatures face down." (708.2a; wave 18A: replacements.turn_down)
    "discard_battlefield",  # -- discard causes (wave 23D) -- "If a spell or ability an opponent controls causes you to discard this card, put it onto the battlefield instead of putting it into your graveyard."
    "exile_instead",  # "If ~ would die / be put into a graveyard from anywhere, exile it instead" (own and statics)
    "hand_instead",  # -- instead (wave 100K) -- "If a creature you control that's enchanted would die, return it to its owner's hand instead." (Necromancer's Magemark)
    "hand_instead110i",  # -- cards (wave 110I) -- Firestorm Phoenix
    "library_instead",  # "If ~ would die, put it on top of / on the bottom of its owner's library instead" (wave 20B)
    "tapped_for_rad110c",  # -- optional entering choice (wave 110C) -- "You may have this land enter tapped. If you do, you get two rad counters." (Mariposa Military Base)
    "library_may110c",  # -- optional replacements (wave 110C) -- "If this permanent would be put into a graveyard, you may put it on top of its owner's library instead." (Pulmonic Sliver grant)
    "shuffle_instead",  # -- zone replacements (wave 22C) -- "… reveal ~ and shuffle it into its owner's library instead" (Blightsteel)
    "prevent",  # "Prevent all [combat] damage that would be dealt [to …] [by …] [this turn]" (615)
}
# -- copy system (wave 2F): "You may have ~ enter as a copy of …[, except …]" (707.5, 614.1c, 614.12a;
# app/rules/copying.py, tests/test_rules_copy.py). Copies of spells and abilities, token copies and
# "becomes a copy" are templates (their definitions parse only in the wording the engine carries out).
SUPPORTED_REPLACEMENTS.add("enter_as_copy")
# -- "this way" outcomes (wave 4A) -- "As ~ enters, you may reveal an X or Y card from your hand. If you don't, ~
# enters tapped." (614.1c, 614.12a, 701.20a; app/rules/reveal_lands.py, tests/test_rules_wave4a_this_way.py)
SUPPORTED_REPLACEMENTS.add("reveal_or_tapped")
SUPPORTED_REPLACEMENTS.add("enters_prepared")  # -- prepared (wave 13C) -- "~ enters prepared." (722.3a; replacements.after_entry)
# -- entering for a cost (wave 5G) -- "If ~ would enter, you may discard a land card / sacrifice a Swamp instead. If you
# do, put ~ onto the battlefield. If you don't, put it into its owner's graveyard." (614.1a, 614.12a, 614.13, 118.12;
# app/rules/enter_cost.py, tests/test_rules_wave5g_if_you_do.py)
SUPPORTED_REPLACEMENTS.add("enter_cost")
SUPPORTED_REPLACEMENTS.add("enters_exile_unpaid")  # Own prospective payment-conditioned entry diversion.
SUPPORTED_REPLACEMENTS.add("turned_up_attach110d")  # -- turned up (wave 110D) -- "As ~ is turned face up, you may attach it to a creature." (wave110d_misc.attach_up)
SUPPORTED_REPLACEMENTS.add("turned_up_counters")  # -- counters (wave 52D) -- 708.11: "As ~ is turned face up, put five +1/+1 counters on it." (app/rules/counters52d.py)


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
    if d.get("kind") == "static" and d.get("static") == "exert_attack" and not d.get("effects"):
        return True
    if any(isinstance(g, dict) and g.get("random") for g in d.get("targets") or []) and len(d["targets"]) != 1:
        return False  # -- random choices (wave 47B) -- "target … chosen at random" is read as the ability's only target group (the pick is made as the targets are chosen, not between questions)
    if d.get("kind") == "mode" or (d.get("modes") and d.get("kind") in ("triggered", "activated")):
        return modal_supported(d)  # (wave 1A) a modal triggered / activated ability
    # -- reanimation (wave 3R) -- "return this card from your graveyard": only an activated ability works from
    # there (113.6m); a trigger or static line would need the graveyard scanned for triggers
    if d.get("kind") != "activated" and '"self_gy_exile"' in json.dumps(d, default=str):
        return False  # -- activated other (wave 42C) -- "from your graveyard or from exile": only an activated ability is read there (113.6m)
    if d.get("kind") != "activated" and '"self_gy"' in json.dumps(d, default=str):
        from app.rules.triggers import graveyard_trigger_ok  # -- refused zones/sized (wave 3R4) -- (113.6m)

        if not graveyard_trigger_ok(d):
            return False
    if d.get("kind") != "activated" and any(f'"{w}"' in json.dumps(d, default=str) for w in ("self_hand", "self_command")):
        return False  # -- activated from hand / command zone (wave 27D) -- 113.6m: only an activated ability is read there
    # -- refused grants/replacements (wave 3R2) -- a flashback cost never stated
    from app.rules import graveyard_grants

    if graveyard_grants.unsupported(d):
        return False
    verdict = stage2_supported(d)  # -- replacement effects stage 2 (wave 2E) --
    if verdict is not None:
        return verdict
    if d.get("kind") == "replacement":  # (review 26D: self_in_group — scripts._enters_self_check, unsettled)
        return d.get("replacement") in SUPPORTED_REPLACEMENTS and not d.get("self_in_group")
    if d.get("kind") == "static" and d.get("static") in ("prevent", "exile_instead", "hand_instead"):
        return d["static"] in SUPPORTED_REPLACEMENTS
    if d.get("kind") == "spell" and any(e.get("do") == "prevent_all" for e in d.get("effects") or []):
        return "prevent" in SUPPORTED_REPLACEMENTS
    return True


# -- counters & designations (wave 3E) -----------------------------------------------------------------
# Player counters with rules (energy 107.14, experience, poison 704.5c, rad 728), the monarch (725), the
# initiative (726), venture into the dungeon (701.49, 309) and the Ring tempts you (701.54) are carried out
# by app/rules/designations.py. A card that ventures (or takes the initiative: 726.2 ventures into Undercity)
# is carried out, but it is FULL only while every room it may lead into is automated too
# (designations.room_definition; an "engine:dungeon" feature otherwise); every room of the four dungeons is automated (wave 45B: Undercity's
# Arena, goad).
def counters_designations_gap(d: dict[str, Any]) -> str | None:
    from app.rules import designations

    return designations.unautomated(d)
# -- end counters & designations (wave 3E) --


# -- replacement effects stage 2 (wave 2E) -----------------------------------------------------------
# The events app/rules/replace.py applies statics to (app/rules/replace_grammar.py) and the ops it
# carries out for each, every one with scenario tests in tests/test_rules_replacements2.py. A parsed
# static with another op stays manual.
SUPPORTED_REPLACE_OPS: dict[str, frozenset[str]] = {
    "creature_entry": frozenset({"exile"}),
    "tokens": frozenset({"mul", "add", "set_creator"}),  # 614.16: Parallel Lives, Doubling Season, Xorn
    "counters": frozenset({"mul", "add"}),  # 122.6, 614.16: Hardened Scales, Winding Constrictor, Doubling Season
    "player_counters": frozenset({"add", "mul"}),  # Winding Constrictor; energy-specific additions/doubling (107.14)
    "draw": frozenset({"win", "skip", "steal", "draw"}),  # 121.6, 614.11: Laboratory Maniac, Notion Thief
    "life": frozenset({"mul", "add", "set", "lose"}),  # 119.10: Boon Reflection, Sulfuric Vortex, Tainted Remedy
    "damage": frozenset({"mul", "add", "sub", "half", "prevent", "prevent_all_but", "prevent_all", "cap", "set_value", "prevent_counters110j"}),  # 614, 615.10 (cap: wave 20B)
}
# -- refused grants/replacements (wave 3R2) -- 614.9 redirection statics (Pariah, Palisade Giant: app/rules/source_shields.py,
# tests/test_rules_refused_grants.py)
SUPPORTED_REPLACE_OPS["damage"] = SUPPORTED_REPLACE_OPS["damage"] | {"redirect"}
# -- damage wordings (wave 6B) -- "prevent half that damage, rounded up" (Gisela, Blade of Goldnight; 615)
SUPPORTED_REPLACE_OPS["damage"] = SUPPORTED_REPLACE_OPS["damage"] | {"prevent_half_up"}
# -- keyword actions (wave 35C) -- the action as the event: scry → draw (Eligeth), explore twice / after a scry (Topography Tracker, Twists and Turns),
# connive after a draw (Leader, Super-Genius): app/rules/replace.py ``keyword_replace``
SUPPORTED_REPLACE_OPS["scry"] = frozenset({"draw", "plus"})  # (wave 50G: Kenessos)
SUPPORTED_REPLACE_OPS["explore"] = frozenset({"again", "before"})
SUPPORTED_REPLACE_OPS["connive"] = frozenset({"before"})
SUPPORTED_REPLACE_OPS["proliferate"] = frozenset({"again"})  # -- keyword actions (wave 50F) -- 701.34a, 614.1a: "proliferate twice instead" (Tekuthal, Inquiry Dominus)
# -- damage bodies (wave 35C) -- "put that many counters on it instead" (Phytohydra, Szadek, Soul-Scar Mage: app/rules/replace_grammar.py _damage_body)
SUPPORTED_REPLACE_OPS["damage"] = SUPPORTED_REPLACE_OPS["damage"] | {"body"}
# … and token creation adding a different token (Peregrin Took, Chatterfang: app/rules/extra_tokens.py)
SUPPORTED_REPLACE_OPS["tokens"] = SUPPORTED_REPLACE_OPS["tokens"] | {"extra", "replace", "each_of", "token_characteristics"}  # (wave 35C: token swaps)
# -- replacements & prevention (wave 22C) -- "put half that many … rounded down" (Vorinclex) on counters
SUPPORTED_REPLACE_OPS["counters"] = SUPPORTED_REPLACE_OPS["counters"] | {"half"}
# -- replacements: draws and life (wave 28B) -- a draw replaced by its own instructions (app/rules/draw_bodies.py)
SUPPORTED_REPLACE_OPS["draw"] = SUPPORTED_REPLACE_OPS["draw"] | {"body"}
SUPPORTED_REPLACE_OPS["mill"] = frozenset({"mul", "add"})  # 701.17a: Bruvac the Grandiloquent, The Water Crystal (replace.mill_counts)
SUPPORTED_REPLACE_OPS["draw_count"] = frozenset({"add", "each_one"})  # 121.2a: Quantum Riddler, Alms Collector (replace.draw_cards)
SUPPORTED_REPLACE_OPS["life_loss"] = frozenset({"mul", "floor"})  # 119.3: Bloodletter of Aclazotz (app/rules/replace.py lose_life); floor: wave 35C
SUPPORTED_REPLACEMENTS |= {
    "enters_tapped_others",  # 614.1d, 614.12: "Creatures your opponents control enter tapped."
    "enters_untapped_others",  # 614.1d: "Lands you control enter untapped." (wave 45A)
    "exile_if_dies",  # "If that creature / a creature dealt damage this way would die this turn, exile it instead." (611.2a)
}


def stage2_supported(d: dict[str, Any]) -> bool | None:
    """Stage 2 definitions: automated when their event and op are listed above (None: not one, or
    nothing here to object to)."""
    if d.get("kind") == "static" and d.get("static") == "replace":
        if 'also' in d:
            from app.rules import conditional_prevention_grants45

            if not conditional_prevention_grants45.supported(d):
                return False
        op = d.get("op") or {}
        if d.get("event") == "damage" and op.get("do") == "finite_prevention":
            from app.rules import prevention_frontier_cards

            return prevention_frontier_cards.supported_static(d)
        if op.get("do") == "body":  # -- replacements: draws and life (wave 28B) -- only the instructions a body may carry
            from app.rules import draw_bodies

            return draw_bodies.supported(op.get("effects") or [])
        return op.get("do") in SUPPORTED_REPLACE_OPS.get(str(d.get("event")), frozenset())
    if d.get("kind") == "static" and d.get("static") in ("enters_tapped_others", "enters_untapped_others"):
        return str(d["static"]) in SUPPORTED_REPLACEMENTS
    effects = d.get("effects") or []
    if any(e.get("do") == "exile_if_dies" for e in effects) and "exile_if_dies" not in SUPPORTED_REPLACEMENTS:
        return False
    for e in effects:  # "Until end of turn, if …" / "If … this turn, …": a record of a statics' wording
        if e.get("do") == "replace_record" and (e.get("op") or {}).get("do") not in SUPPORTED_REPLACE_OPS.get(str(e.get("event")), ()):
            return False
        if e.get("do") == "replace_record" and (e.get("op") or {}).get("do") == "body":  # -- replacements: draws (wave 28B) --
            from app.rules import draw_bodies

            if not draw_bodies.supported((e.get("op") or {}).get("effects") or []):
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
    "haste", "defender", "menace", "banding",  # CR 702.22: declared bands, shared blocks, assignment control.
    # state-based actions (M15b)
    "indestructible",
    # M16: casting timing and targeting (test_rules_effects.py)
    "flash", "hexproof", "shroud",
    # evasion (test_rules_combat.py::test_evasion, landwalk tests)
    "plainswalk", "islandwalk", "swampwalk", "mountainwalk", "forestwalk", "desertwalk",
    "snow landwalk", "nonbasic landwalk", "legendary landwalk", "artifact landwalk", "snow plainswalk", "snow islandwalk", "snow swampwalk", "snow mountainwalk", "snow forestwalk",  # (wave 12B: 702.14c variants)
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
SUPPORTED_KEYWORDS.add("absorb")  # CR 702.64: separate prevention instances, app/rules/absorb.py
SUPPORTED_KEYWORDS.add("read ahead")
SUPPORTED_KEYWORDS.add("storied")  # -- storied (wave 45D) -- 702.195 (designations.storied_permanents)
SUPPORTED_KEYWORDS.add("ascend")  # -- keywords (wave 15E) -- 702.131 (designations.ascend_permanents; effects.ascend)
SUPPORTED_KEYWORDS.add("umbra armor")  # -- keywords (wave 15E) -- 702.89a (regeneration.umbra_armor)
SUPPORTED_KEYWORDS.add("start your engines!")  # -- speed (wave 24B) -- 702.179 (app/rules/speed.py)
SUPPORTED_KEYWORDS.add("phasing")  # -- phasing (wave 13D) -- 702.26 (app/rules/phasing.py)
SUPPORTED_KEYWORDS.update(("aftermath", "gravestorm", "dredge", "fuse", "awaken", "escalate"))  # -- static_other sweep (wave 16B) -- 702.127 (casting.cast_grant)
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
    "venture into the dungeon", "the ring tempts you",
    # -- keyword actions & face-down (wave 3F) -- test_rules_keywords3f.py
    "goad", "manifest", "manifest dread", "cloak", "earthbend", "incubate",
}
SUPPORTED_KEYWORD_ACTIONS.update({"clash", "detain", "suspect"})  # -- clash, detain, suspect (wave 12A) -- app/rules/clash.py, test_rules_wave12a_counters_keywords.py
SUPPORTED_KEYWORD_ACTIONS.add("populate")  # -- token copies & attach on entry (wave 5J) -- test_rules_wave5j_token_copies.py
SUPPORTED_KEYWORD_ACTIONS.update({"open an attraction", "roll to visit your attractions"})  # -- Attractions (wave 100L) -- test_rules_wave100l_attractions.py


# -- refusals (agent T) ------------------------------------------------------------------------------
# Wordings the grammar reads far enough to know it must NOT automate them, and why. A card with
# one of these stays PARTIAL/MANUAL on purpose; the reason names the missing piece so the gap
# report can rank it (never a guess at what the card does). ``refusal(text)`` gives the reason.
REFUSED: tuple[tuple[re.Pattern[str], str], ...] = (
    # (fight (701.14) and "choose … target" are read now: effects.fight, effects.choose_targets)
    # (-- static_other sweep (wave 16B) -- "costs {N} more to cast for each target beyond the first" is read now: permissions._PER_TARGET)
    # (-- graveyard exile (wave 4J) -- "exile target player's graveyard" itself is read: app/rules/graveyard_exile.py)
    (re.compile(r"(?<!exile )\btarget (?:player|opponent)'s (?:graveyard|hand|library)\b", re.I),
     "a target player's zone as the object set (\"exile all creature cards from target player's graveyard\"): the "
     "effects can't reach the chosen player from a selector"),
    (re.compile(r"\btarget \w+(?: \w+)* that player controls\b", re.I),
     "a selector relative to a player named earlier (\"target creature that player controls\"): not modelled"),
    # ("up to X target …": read now, the number of targets announced with X, 601.2c — wave 4K)
    # (copy system, wave 2F / 3R3: "copy target spell", and "copy it / that spell" for the spell a cast trigger
    # was about, are read now: app/rules/copying.py)
    # ("target player shuffles up to N target cards from their graveyard into their library": read now, wave 46B — the graveyard_of target group)
    # ("target creature with the greatest power among creatures on the battlefield": read now, wave 49C — selectors "ext:")
    (re.compile(r"(?<!switch )\btarget creature's power and toughness\b", re.I),  # (switching: wave 7E, choice_grants.switch_pt)
     "switching or reading a target's P/T pair: not modelled"),
    # -- conditional / instead clauses (wave 1B) --------------------------------------------------------
    # Conditions app/rules/conditions.py deliberately doesn't read: the clause (or the whole ability) stays manual.
    # -- refused modal/conditional (wave 3R1) -- how a spell was cast (the zone, the caster's main phase, the mana of
    # each type spent) is now on its payment record (conditions._cast_how); what stays refused:
    (re.compile(r"\b(?:entered from (?:your|a) library|was put onto the battlefield from (?:your|a) (?:library|graveyard))\b", re.I),  # (wave 22E: "entered from a graveyard" is recorded now)
     "the zone a permanent entered from isn't recorded with the object: not modelled"),
    # (-- mana provenance (wave 18B) -- {S} and "mana from a Treasure" spent to cast a spell are read now: app/rules/mana_units.py;
    # what stays refused: mana spent on an ability, {S} "of that spell's colors", mana spent to cast other creatures as they enter)
    (re.compile(r"\bspent to activate\b|\{S\} of [^.,]+ was spent to cast\b|\bspent to cast them\b", re.I),
     "mana spent on an ability, snow mana by color, and the mana spent to cast other creatures as they enter aren't recorded: not modelled"),
    # (wave 3E: "you've completed a dungeon" and "it's day / night" are read now: app/rules/designations.py)
    # (-- this-turn history (wave 4D) -- "this is the second time this ability has resolved this turn" is read now:
    # app/rules/history.py counts each object's ability resolutions per turn)
)


# -- keyword actions & face-down (wave 3F) -- refused on purpose, with the missing piece named
REFUSED += (
    # (-- trigger other (wave 25B) -- airbending a permanent is read now: app/rules/airbend.py; a spell's exile from the stack isn't)
    (re.compile(r"\bairbend[^.]*\bspells?\b", re.I), "airbending a spell: exiling it from the stack with that permission isn't modelled"),
    # (review 25B: "Choose up to one target creature, then airbend all other creatures": "other" is other than the chosen one, not the source;
    # scripts._clause refuses it)
    (re.compile(r"\bchoose [^.]*\btargets?\b[^.]*, then \w+ all other\b", re.I),
     "'all other' after a chosen target means other than the chosen objects: not modelled"),
    (re.compile(r"\bwaterbend", re.I),
     "waterbend (701.67): a cost whose generic part may be paid by tapping artifacts/creatures isn't modelled"),
    (re.compile(r"\bmanifests? the top card of (?:that player's|target player's|an opponent's)", re.I),
     "manifesting another player's card under your control: not modelled"),
)


# -- refused look/cast-free (wave 3R5) -- look-at-the-top and cast-without-paying forms still left to the players
# (the ones read now: app/rules/permissions.py free_cast, app/rules/looking.py; tests/test_rules_refused_look.py)
REFUSED += (
    (re.compile(r"\b(?:of the chosen (?:creature |card )?type|with (?:the|that) chosen name|choose a (?:nonland )?card name)\b", re.I),
     "a value chosen as the ability resolves used as a filter (\"cards of the chosen type\", \"a card with the chosen name\") in a wording "
     "no selector reads (wave 22B: card names are typed, app/rules/card_names.py; a name is read from the source permanent or an earlier "
     "\"Choose a card name\" of the same resolution)"),
    (re.compile(r"\bchoose two cards in your hand drawn this turn\b", re.I),
     "Sylvan Library: which hidden cards in a hand were drawn this turn isn't tracked per card"),
    (re.compile(r"\bas many times as you choose, you may pay 1 life, put those cards on the bottom\b", re.I),
     "Lim-Dûl's Vault: a repeated look-and-pay loop, then a shuffle that keeps the last cards on top, isn't modelled"),
    (re.compile(r"\byou may play one of those cards without paying\b", re.I),  # (-- play now (wave 28A) -- "that card" / "it" are read now)
     "\"you may play one of those cards\" as the ability resolves: a choice among several cards, any of them a land, isn't modelled"),
    (re.compile(r"\b(?:any number of|up to \w+) (?!target\b)[^.]*?with total mana value \w+ or less\b", re.I),  # (targets: wave 3R4)
     "choosing a set of cards or spells under a total mana value limit: not modelled"),
    (re.compile(r"\bcast (?:the copy|the copies|any number of the copies|those copies)\b", re.I),
     "casting a copy of a card (707.12): belongs to the copy system"),
    (re.compile(r"\bcast target [^.]*with mana value less than or equal to [^.]*from [^.]*graveyard\b", re.I),
     "a target card whose mana value limit is read as it resolves: the target's legality would change with it"),
    (re.compile(r"\b(?:each opponent|each player) reveals cards from the top of their library until\b", re.I),  # (exiles: wave 44A)
     "\"until\" in several libraries at once: the resolution keeps one found card"),
    (re.compile(r"\btapped and attacking (?:that player|defending player)\b", re.I),
     "put onto the battlefield attacking a player the effect names (508.4: its choice isn't the controller's)"),
)


def refusal(text: str) -> str | None:
    """Why the engine refuses to automate this wording, if it is a known refusal (else None)."""
    from app.rules import activation_payment_conditions

    text = activation_payment_conditions.refusal_text(text)
    from app.rules.contextual_mana_triggers import stack_definition

    if text == ('Whenever an opponent casts a spell or activates an ability, if mana from a Treasure was spent to cast it or activate it, '
                'put a +1/+1 counter on target creature, then draw a card.'):
        text = text.replace('spent to cast it or activate it', 'supported event payment')
    if stack_definition(text) is not None:
        text = text.replace("{S} of any of that spell's colors was spent to cast", "supported snow-colored payment for")
    if 'spent to cast them' in text:
        from app.rules import replace_grammar

        entry = replace_grammar._enter_extra(text)
        if entry is not None and 'mana_from' in entry.get('op', {}).get('times', {}):
            text = text.replace('spent to cast them', 'supported entry payment')
    for pattern, reason in REFUSED:
        if pattern.search(text):
            if "choosing a set of cards or spells under a total mana value limit" in reason:
                from app.rules import total_mv_casts

                if total_mv_casts.supported_wording(text):
                    continue
            if "put onto the battlefield attacking a player" in reason:
                from app.rules import combat_rules

                body = text.rstrip(".").split(", for each opponent, ", 1)
                if len(body) == 2:
                    found = combat_rules.clause("for each opponent, " + body[1])
                    if found is not None and found[0] and all(e.get("do") == "create_attacking_each"
                                                             and not e.get("pw") for e in found[0]):
                        continue
            return reason
    return None




_MANA_FLASHBACK = re.compile(r"flashback (?:\{[^}]+\})+")


# 702.124a: partner abilities modify deck construction and "function before the game begins":
# during the game there's nothing to do (pairings are checked by app/rules/commander.py and the
# deck checks). "Partner with [name]" also has an enters trigger (702.124j): not listed here.
DECKBUILDING_KEYWORDS = {"partner", "choose a background", "doctor's companion", "friends forever"}


def _keyword_supported(kw: str, line: str) -> bool:
    if kw == "absorb":
        from app.rules.oracle import keyword_name, keyword_pieces, strip_reminders

        pieces = [p for p in keyword_pieces(strip_reminders(line)) if keyword_name(p) == "absorb"]
        return bool(pieces) and all(re.fullmatch(r"absorb \d+\.?", p.strip(), re.I) for p in pieces)
    if kw.startswith("bands with other "):
        from app.rules import banding

        return banding.quality(kw) is not None
    if kw in DECKBUILDING_KEYWORDS:
        if line.strip().lower().startswith("partner with"):  # -- keyword pieces (wave 8A) -- 702.124j's enters trigger
            from app.rules import keyword_triggers

            return keyword_triggers.partner_with_definition(line) is not None
        return True
    if kw == "companion":  # -- companion (wave 38D) -- 702.139a: it functions outside the game; in the deck or as the commander it does nothing.
        # Supported when its condition is one commander.COMPANION_RESTRICTIONS checks (the deck check and the 116.2g special action use it)
        from app.rules import commander

        return commander.companion_condition(line) in commander.COMPANION_RESTRICTIONS
    if kw in ("enchant", "equip", "fortify"):  # app/rules/attachments.py: the wordings it maps
        from app.rules import attachments

        return attachments.supported_keyword(kw, line)
    if kw == "protection":  # DEBT for the qualities app/rules/protection.py understands
        return protection.supported(line)
    if kw == "hexproof from":  # -- keywords (wave 44D) -- 702.11d: the qualities app/rules/protection.py understands
        return protection.hexproof(line) is not None
    if kw == "affinity":  # casting.affinity_filter
        from app.rules.casting import affinity_filter  # casting imports coverage (via engine)

        return affinity_filter(Characteristics(name="", abilities=(AbilityText(index=0, text=line, kind="keywords",
                                                                              keywords=("affinity",)),))) is not None
    if kw == "paradigm":  # -- keywords (wave 50H) -- 702.192a: app/rules/paradigm.py (an instant or sorcery's last instruction, oracle.parse_abilities)
        return line.strip().lower() == "paradigm"
    if kw == "tribute":  # -- keywords (wave 50H) -- app/rules/tribute.py (one instance)
        from app.rules import tribute

        return tribute.supported(line)
    if kw == "amplify":  # -- casting extras (wave 18E) -- app/rules/amplify.py (one instance)
        from app.rules import amplify

        return amplify.supported(line)
    if kw == "assist":  # -- casting extras (wave 18E) -- app/rules/assist.py
        from app.rules import assist

        return assist.supported(line)
    if kw == "enlist":  # -- casting extras (wave 18E) -- app/rules/enlist.py: a plain keyword line (each instance asks on its own)
        from app.rules import enlist

        return enlist.supported(line)
    if kw == "casualty":  # -- casting extras (wave 18E) -- cost_changes.optional_offers / casting._conspire_trigger (one instance)
        from app.rules import casualty_x

        return casualty_x.supported(line) or re.fullmatch(r"casualty \d+", line.strip().rstrip(".").lower()) is not None
    if kw == "conspire":  # -- static_other sweep (wave 17C) -- cost_changes.optional_offers / casting._conspire_trigger
        return line.strip().rstrip(".").lower() == "conspire"
    if kw == "compleated":  # -- cast keywords (wave 43D) -- replacements.entering_counters (702.150a): a plain keyword line
        return line.strip().rstrip(".").lower() == "compleated"
    if kw == "demonstrate":  # -- cast keywords (wave 43D) -- casting._demonstrate_trigger / copying.demonstrate_copy (702.144a): a plain keyword line
        return line.strip().rstrip(".").lower() == "demonstrate"
    if kw == "bargain":  # -- keywords (wave 30E) -- cost_changes.optional_offers (702.166a); "was bargained" is read as kicked (scripts.self_text)
        return line.strip().rstrip(".").lower() == "bargain"
    if kw == "teamwork":  # (702.194a: its optional cost, and "cast using teamwork" in the text)
        return re.fullmatch(r"teamwork \d+", line.strip().rstrip(".").lower()) is not None
    if kw == "cipher":  # -- static_other sweep (wave 17C) -- recursion.cipher: an instant or sorcery's own line (spell_definition appends it)
        return line.strip().rstrip(".").lower() == "cipher"
    if kw == "ripple":  # -- static_other sweep (wave 17C) -- casting._ripple_triggers: "Ripple N", each instance its own line
        return re.fullmatch(r"ripple \d+", line.strip().rstrip(".").lower()) is not None
    if kw == "echo":  # triggers.echo_cost: a mana echo cost (-- keywords (wave 43C) -- or "Echo—Discard a card.": a cost the optional payment pays)
        from app.rules.triggers import keyword_cost

        return keyword_cost(line, "echo") is not None
    if kw in ("morph", "megamorph"):  # casting.morph_cost: a mana morph cost
        if re.fullmatch(r"(?:mega)?morph (?:\{[^}]+\})+", line.strip().rstrip(".").lower()) is not None:  # (X: wave 110B, 107.3a: announced as it is turned face up)
            return True
        from app.rules.casting import (  # -- hidden exile (wave 18A) -- "Morph—Discard a card."
            MORPH_COST,
            nonmana_cost,
        )

        found = MORPH_COST.fullmatch(re.sub(r"\s*\(.*?\)", "", line).strip().rstrip("."))
        return found is not None and nonmana_cost(found["cost"]) is not None
    if kw == "disguise":
        from app.rules import disguise_costs

        spec = disguise_costs.parse(line)
        return spec is not None and "{X}" not in spec[0].upper()
    if kw == "toxic":  # -- counters & designations (wave 3E) -- combat.py reads "toxic N" anywhere in a keyword line ("Menace, toxic 1")
        return re.search(r"(?:^|, )toxic \d+(?:,|$)", re.sub(r"\s*\(.*?\)", "", line).strip().rstrip(".").lower()) is not None
    if kw == "escalate":  # -- static_other sweep (wave 16B) -- casting.escalate_parts
        from app.rules.casting import escalate_parts

        return escalate_parts(line) is not None
    if kw == "awaken":  # -- static_other sweep (wave 16B) -- casting.AWAKEN: "Awaken N—{cost}"
        return re.fullmatch(r"awaken \d+—(?:\{[^}]+\})+", line.strip().rstrip(".").lower()) is not None
    if kw == "miracle":  # -- casting extras (wave 18E) -- app/rules/miracle.py: a mana miracle cost (wave 43D: with X, announced as the cast begins)
        return re.fullmatch(r"miracle (?:\{[^}]+\})+", line.strip().rstrip(".").lower()) is not None
    if kw == "prototype":  # -- casting extras (wave 18E) -- app/rules/prototype.py: "Prototype {cost} — P/T"
        return re.fullmatch(r"prototype (?:\{[^}x]+\})+ [—-] \d+/\d+", line.strip().rstrip(".").lower()) is not None
    if kw == "reconfigure":  # -- casting extras (wave 18E) -- oracle.parse_abilities: the attach / unattach abilities and the static it adds
        from app.rules import activation_alternatives

        return activation_alternatives.reconfigure_cost(line.strip()) is not None
    if kw == "harmonize":  # -- casting extras (wave 18E) -- app/rules/harmonize.py: a mana harmonize cost without X
        from app.rules import harmonize

        return harmonize.parse(line) is not None
    if kw == "mayhem":  # -- Marvel keywords (wave 25A) -- app/rules/mayhem.py: a mana mayhem cost without X, or none
        from app.rules import mayhem

        return mayhem.parse(line) is not None
    if kw == "disturb":  # -- casting extras (wave 18E) -- app/rules/disturb.py: a mana disturb cost (the back face is the spell)
        from app.rules import disturb

        return disturb.parse(line) is not None
    if kw in ("embalm", "eternalize", "encore"):  # -- keywords (wave 15E; encore: 18E) -- app/rules/graveyard_keywords.py
        from app.rules import graveyard_keywords

        return graveyard_keywords.supported(kw, line)
    if kw == "living metal":  # -- commanders (wave 50C) -- 702.161a: scripts.define reads it as its static meaning
        return True
    if kw in ("spectacle", "surge", "blitz", "warp", "bestow", "prowl", "overload", "cleave", "emerge", "foretell", "mutate", "web-slinging", "sneak", "freerunning", "impending", "more than meets the eye"):  # -- keywords (wave 15E; sneak: 30I; freerunning, impending: 43D) -- app/rules/alt_costs.py: the cost with its condition
        from app.rules import alt_costs

        return alt_costs.keyword_definition(line) is not None
    if kw in ("ninjutsu", "commander ninjutsu"):  # -- keywords (wave 15E; commander ninjutsu: wave 50J) -- app/rules/ninjutsu.py: a mana ninjutsu cost on a line of its own
        from app.rules import ninjutsu

        return ninjutsu.supported(line)
    if kw in ("riot", "unleash"):  # -- keywords (wave 15E) -- app/rules/riot.py
        from app.rules import riot

        return riot.supported(kw, line)
    if kw == "soulshift":  # (wave 15E: each instance of the line, scripts.keyword_triggers)
        return re.fullmatch(r"soulshift \d+(?:, soulshift \d+)*", line.strip().rstrip(".").lower()) is not None
    if kw in ("bushido", "renown"):  # -- flip (wave 24C) -- "Double strike; bushido 2": each piece of the line (triggers._keyword_n reads them one by one)
        pieces = [p.strip() for p in re.split(r"[,;]\s*", re.sub(r"\s*\(.*?\)", "", line).strip().rstrip(".").lower())]
        mine = [p for p in pieces if p.startswith(kw)]
        return bool(mine) and all(re.fullmatch(rf"{kw} \d+", p) for p in mine)
    if kw == "firebending":  # -- wave 110B -- 702.189a: its piece of a line with other keywords
        from app.rules import wave110b_cards

        return wave110b_cards.firebending(line) is not None
    if kw in ("bloodthirst", "toxic", "fabricate", "dredge"):  # numbered keywords (firebending: wave 3F) (triggers.py, engine.enter_with_counters)
        return re.fullmatch(rf"{kw} \d+", line.strip().rstrip(".").lower()) is not None or (  # (-- random choices (wave 47B) -- 702.54b "Bloodthirst X": replacements.entering_counters)
            kw == "bloodthirst" and line.strip().rstrip(".").lower() == "bloodthirst x")
    if kw == "plot":  # -- keywords (wave 15E) -- casting.plot: a mana plot cost
        return re.fullmatch(r"plot (?:\{[^}]+\})+", line.strip().rstrip(".").lower()) is not None
    if kw == "suspend":  # casting.suspend_info: "Suspend N—{cost}"
        return re.fullmatch(r"suspend (?:\d+|x)\s*[—-]\s*(?:\{[^}]+\})+(?:\. x can't be 0)?", line.strip().rstrip(".").lower()) is not None  # (wave 50H: "Suspend X—{X}{3}{U}. X can't be 0.")
    if kw == "cumulative upkeep":  # triggers.cumulative_costs: a mana cost (-- keywords (wave 43C) -- or any cost the optional payment pays, 702.24a)
        from app.rules.triggers import keyword_cost

        return keyword_cost(line, "cumulative upkeep") is not None
    from app.rules import (
        keyword_triggers,  # -- static wordings (wave 6E) -- battle cry, ingest … (their CR meaning)
    )

    if kw == "devour":  # -- keyword mechanics (wave 9D) -- app/rules/devour.py (one instance)
        from app.rules import devour

        return devour.supported(line)
    if kw == "sunburst":  # -- keyword mechanics (wave 9D) -- 702.44a: replacements.entering_counters (not "Modular—Sunburst")
        return bool(keyword_triggers.pieces(kw, line)) and re.fullmatch(r"(?:sunburst)(?:, sunburst)*", re.sub(
            r"\s*\(.*?\)", "", line).strip().rstrip(".").lower()) is not None
    if kw in keyword_triggers.MEANINGS:
        return keyword_triggers.supported(kw, line)
    if kw == "ward":  # -- static wordings (wave 6E) -- every ward piece of the line has a mana cost (triggers.ward_costs)
        from app.rules.triggers import ward_piece_cost, ward_pieces

        pieces = ward_pieces(line)
        return bool(pieces) and all(ward_piece_cost(p) is not None for p in pieces)
    if kw == "evoke" and line.strip().lower().startswith("evoke—"):  # -- keywords (wave 30E) -- "Evoke—Exile a white card from your hand." (alt_costs)
        from app.rules import alt_costs

        return alt_costs.keyword_definition(line) is not None
    if kw == "buyback" and line.strip().lower().startswith("buyback—"):  # -- keywords (wave 30E) -- casting.buyback_parts: "Buyback—Sacrifice a land."
        from app.rules.casting import buyback_parts_line

        return buyback_parts_line(line) is not None
    if kw == "unearth":
        from app.rules import unearth_costs

        return unearth_costs.parse(line) is not None
    if kw == "madness":
        from app.rules import madness_costs

        return madness_costs.line(line) is not None
    if kw in ("dash", "buyback", "madness", "ward", "evoke"):  # casting.keyword_cost: a mana cost
        return re.fullmatch(rf"{kw} (?:\{{[^}}]+\}})+", line.strip().rstrip(".").lower()) is not None
    if kw in ("squad", "offspring", "replicate"):  # -- keywords (wave 15E) -- the cost is paid as kicker's; squad / offspring's
        from app.rules.costs import (
            kicker_line,  # enters trigger is its meaning (keyword_triggers), replicate's the cast trigger
        )

        return kicker_line(line) and (kw == "replicate" or keyword_triggers.supported(kw, line))
    if kw in ("kicker", "multikicker", "entwine"):  # casting.cost_with_kicker: one mana kicker cost (entwine, wave 18E: modal spells' all-modes cost)
        from app.rules.costs import kicker_line

        return kicker_line(line)
    if kw == "transmute":  # -- refused zones/sized (wave 3R4) -- casting.transmute: a mana transmute cost (702.53a)
        from app.rules.casting import TRANSMUTE

        return TRANSMUTE.fullmatch(line.strip().rstrip(".")) is not None
    if kw == "gift":  # -- gift (wave 23D) -- app/rules/gift.py (the gifts the grammar performs; not "an extra turn")
        from app.rules import gift

        return gift.supported(line)
    if kw == "crew":
        from app.rules.casting import crew_cost_line

        return crew_cost_line(line) is not None
    if kw == "saddle":  # 702.171a: saddle remains at sorcery speed.
        return re.fullmatch(r"saddle \d+", line.strip().rstrip(".").lower()) is not None
    if kw == "flashback":  # casting.flashback_parts: a mana flashback cost, with other parts alt_costs reads (wave 16B)
        from app.rules.casting import flashback_parts  # (casting imports coverage, via the engine)

        return flashback_parts(line) is not None
    if kw.endswith("cycling"):
        from app.rules import cycling_costs

        return bool(cycling_costs.parts(line))
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
    templated = {i for i, d in templates.definitions(ch).items() if definition_supported(d) and x_selector_ok(ch, d)}
    if ch.is_instant_or_sorcery:
        whole = templates.spell_definition(ch)
        if whole is None or not definition_supported(whole) or not x_selector_ok(ch, whole):
            # a spell is automated as a whole or resolved by hand. -- reanimation (wave 25D) -- 113.6m: unless it has no spell ability at all and
            # only abilities that work from the graveyard (Reach of Branches: "Whenever a Forest … enters, you may return this card …")
            defs = templates.definitions(ch)
            only_gy = [ab for ab in ch.abilities if ab.kind != "keywords"]
            templated = {i for i in templated if templates.graveyard_only_ability(defs.get(i))} \
                if only_gy and all(templates.graveyard_only_ability(defs.get(ab.index)) for ab in only_gy) else set()
        elif whole.get("modes") or whole.get("whole110k"):  # (-- wave 110K -- whole110k: the resolution-time mode choice of "An opponent chooses one —", whose bullets are read with its header)
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
    if "Battle" in ch.types:  # 310 (app/rules/battles.py): a Siege's defeat casts it transformed (310.12b; wave 45B)
        add("battle", "Defense, protector, attacks (310)", True)
    for ab in ch.abilities:
        if script is not None and ab.index in script.covers:
            add(f"script:{ab.index}", ab.text, True)
        elif ab.kind == "keywords":
            for kw in ab.keywords:
                if kw == "splice":  # -- casting extras (wave 18E) -- app/rules/splice.py
                    from app.rules import splice

                    add("keyword:splice", "Splice", splice.spliceable(ch))
                    continue
                if kw in ("spree", "tiered"):  # -- keywords (wave 30E) -- 702.172a, 702.183a: every mode line read with its cost (scripts.spree_definition)
                    whole = templates.spell_definition(ch)
                    add(f"keyword:{kw}", kw.capitalize(), whole is not None and bool(whole.get("modes")) and definition_supported(whole))
                    continue
                if kw == "overload":  # -- casting extras (wave 18E) -- the spell read with "each" for "target" (702.96a)
                    from app.rules import overload

                    add("keyword:overload", "Overload", _keyword_supported(kw, ab.text) and overload.supported(ch))
                    continue
                if kw == "haunt":  # -- keywords (wave 50H) -- 702.55a: a creature dying, or an instant or sorcery put into a graveyard during its resolution (engine.leave_stack)
                    add("keyword:haunt", "Haunt", bool({"Creature", "Instant", "Sorcery"} & ch.types) and _keyword_supported(kw, ab.text))
                    continue
                if kw == "cleave":  # -- keywords (wave 50H) -- 702.148a: the spell read without the words in square brackets too
                    from app.rules import cleave

                    add("keyword:cleave", "Cleave", _keyword_supported(kw, ab.text) and cleave.supported(ch))
                    continue
                add(f"keyword:{kw}", kw.capitalize(), _keyword_supported(kw, ab.text) if kw != "backup" else all(
                    keyword_triggers.backup_definition(ch, ab, n) is not None
                    for n in range(len(keyword_triggers.pieces("backup", ab.text)))) and bool(
                        keyword_triggers.pieces("backup", ab.text)))  # (wave 15E: the abilities below it, 702.165a)
        elif ab.kind == "mana":
            add("mana:ability", ab.text, "mana:ability" in SUPPORTED and parse_mana_ability(ab.text, card_name=ch.name) is not None)
        else:
            add(f"text:{ab.index}", ab.text, ab.index in templated)
    # -- counters & designations (wave 3E) -- the dungeon rooms a venture may lead into (automated or not)
    defs = templates.definitions(ch)
    gaps = {g for i in templated if i in defs and (g := counters_designations_gap(defs[i])) is not None}
    if ch.is_instant_or_sorcery and templated and (whole := templates.spell_definition(ch)) is not None:
        gaps |= {g for g in [counters_designations_gap(whole)] if g is not None}
    for gap in sorted(gaps):
        add("engine:dungeon", gap[0].upper() + gap[1:], False)
    if any(d.get("kind") == "static" and d.get("static") == "roll_adjust" and d.get("life", True) for d in defs.values()):  # (wave 110H: a counter cost has no life to pay)
        # Night Shift's numeric rules are complete. Its accepted-use life payment
        # on a symbolic planar die still requires the native planar-roll model.
        add("engine:planar_roll_payment", "Planar-die life payment and accepted-use accounting", False)
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
        return "mana:ability" in SUPPORTED and parse_mana_ability(ab.text, card_name=ch.name) is not None
    if ch.is_instant_or_sorcery:
        whole = templates.spell_definition(ch)
        own = templates.definitions(ch).get(index)
        if own is not None and templates.own_graveyard_activation(own):
            return whole is not None and definition_supported(whole) and definition_supported(own) and x_selector_ok(ch, own)
        if own is not None and (own.get("trigger") == "cast_self" or templates.own_card_event_ability(own)):  # -- spell copies (wave 31D) -- its own trigger (601.2i), apart from what the spell does (wave 36A: and a cycling / discard trigger of the card, 702.29d)
            return whole is not None and definition_supported(own) and x_selector_ok(ch, own)
        return whole is not None and definition_supported(whole) and x_selector_ok(ch, whole)
    d = templates.definitions(ch).get(index)
    return d is not None and definition_supported(d) and x_selector_ok(ch, d)


_X_SELECTOR = re.compile(r'\["mv","==",-1\]')  # (selectors.X_VALUE; "or less" wordings predate this check)


def x_selector_ok(ch: Characteristics, d: dict[str, Any]) -> bool:
    """-- reanimation (wave 10A) -- a selector reading "mana value X" (107.3f) needs an X the player announces: the {X} of
    the spell's mana cost or of the activated ability's cost. X in an activation cost is announced before targets, including energy and counters. An X chosen
    by an optional payment on resolution is not yet known when targets are chosen and stays manual."""
    # -- cast-permission riders (wave 38C) -- 603.12: "you may pay {X}. When you do, … target … with mana value X": the reflexive ability's targets are chosen after the
    # payment, knowing the X paid (scripts: "x_event", triggers.event_x)
    own = {**d, "effects": [e for e in d.get("effects") or [] if not (e.get("do") == "reflexive" and e.get("x_from") and (e.get("ability") or {}).get("x_event"))]}
    if not _X_SELECTOR.search(json.dumps(own, default=str).replace('\\"', '"')):
        return True
    if d.get("kind") == "activated":  # (-- reanimation (wave 50F) -- 606.4, 601.2b: a loyalty ability's "−X" is announced before its targets, like an {X} cost: Sorin, Vengeful Bloodlord)
        from app.rules.costs import parse_ability_cost

        cost_text = str(d.get("cost") or "")
        cost = parse_ability_cost(cost_text, card_name=ch.name, loyalty=bool(d.get("loyalty")))
        return "{X}" in cost_text or (bool(d.get("loyalty")) and cost_text.endswith("X")) or (not cost.unsupported and cost.x_chosen)
    if d.get("kind") == "triggered":  # -- X from the triggering object (wave 34C) -- the X of the spell cast / the cycling cost (triggers.x_source)
        from app.rules import triggers

        return triggers.x_source(d, ch) is not None
    # -- additional cost X (wave 110C) -- 107.3a, 601.2b: "As an additional cost to cast this spell, pay X life." announces the X too (Fix What's Broken)
    from app.rules.costs import spell_additional_cost

    extra = spell_additional_cost(ch.abilities)
    return d.get("kind") == "spell" and ("{X}" in (ch.mana_cost or "") or (extra is not None and (extra.life_x or any(c.counters_x for c in extra.components))))

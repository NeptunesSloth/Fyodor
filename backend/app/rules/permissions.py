"""Cast / play permissions and cost modifiers: the generic infrastructure behind "you may cast
creature spells from the top of your library", "you may play that card this turn", "spells you
cast cost {1} less to cast" and friends.

Rules (stored Comprehensive Rules, 2026-09-25):

* 601.3 — a player can begin to cast a spell only if a rule or effect allows it. By default that
  is a card in their hand (601.2), a commander in the command zone (903.6), flashback (702.34).
  Everything else is a *permission*: a static ability of a permanent on the table (read from the
  table, never stored), or one granted by a resolved spell or ability (a ``Permission`` record in
  ``RulesState.permissions``).
* 400.7h/i — "you may play that card this turn" follows the specific *object* the effect found:
  once the card changes zones it is a new object and the permission no longer applies. Such a
  permission carries the object id; it is never matched by card.
* 601.3b — "as though it had flash": only the timing changes.
* 118.9 — "without paying its mana cost" is an alternative cost of {0}; only one alternative cost
  per spell (118.9a); additional costs (kicker, buyback), increases and reductions still apply to
  it (118.9d).
* 601.2f / 118.7 — total cost = mana cost or alternative cost, plus additional costs and cost
  increases, minus reductions; reductions by generic amounts touch only the generic component
  (118.7a) and never take it below {0}. Commander tax is a cost increase (903.8).
* 401.5 — "play with the top card of your library revealed" / "you may look at the top card of
  your library any time": what the table makes public (``RulesState.top_reveals``, checked by
  ``app.game.visibility``). Casting from the top of the library is only offered when the player
  can see that card; the card becomes public as it moves to the stack, nothing else is revealed.

The grammar (``define_static`` for ability lines, ``parse_clause`` for effect sentences) is a
closed list of wordings; anything else stays manual.
"""

from __future__ import annotations

import re
import secrets
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any

from app.game.rules_state import CostModifier, Permission, PermissionUseTrigger, TopReveal
from app.game.state import STACK, CardInstance, GameState, zone_key
from app.game.visibility import can_see
from app.rules import characteristics as chars
from app.rules import cost_changes, costs, delayed, land_plays, offering, selectors
from app.rules import mana as M
from app.rules.characteristics import CardInfo, Characteristics

if TYPE_CHECKING:
    from app.rules.plan import Plan

Definition = dict[str, Any]

# -- grammar ---------------------------------------------------------------------------------------
_SEL = r"(?P<sel>[a-z][a-z' ,-]*?)"
_N = r"\{(?P<n>\d+)\}"
# "Creature spells you cast cost {1} less to cast." / "Spells your opponents cast cost {2} more to
# cast." / "Noncreature spells cost {1} more to cast." (any caster)
# -- costs (wave 3$) -- also "Aura and Equipment spells you cast cost {1} less" (subtypes are capitalized), "Kithkin spells and
# Soldier spells you cast …", "Each spell you cast that's red or green costs {1} less", "Creature spells you cast with power 4
# or greater cost {2} less", "Historic spells you cast cost {1} less"
_WITH = r"with (?:mana value|power|toughness) \d+ or (?:less|greater|more)"
STATIC_COST = re.compile(
    rf"^(?:each )?(?:{_SEL} )?spells? (?P<who>you cast |your opponents cast )?(?:that's (?:an? )?(?P<thats>[a-z][a-z' ,-]*?) )?"
    rf"(?:(?P<with>{_WITH}) )?costs? {_N} (?P<dir>less|more) to cast$", re.IGNORECASE)
# -- costs (wave 3$) -- "Activated abilities of creatures you control cost {2} less to activate. This effect can't reduce the
# mana in that cost to less than one mana." / "Abilities you activate that aren't mana abilities cost {2} less to activate."
ABILITY_COST = re.compile(
    rf"^(?:activated abilities(?: of (?P<sel>[a-z][a-z' ,-]*?))?|(?P<yours>abilities you activate that aren't mana abilities)) "
    rf"costs? (?:{_N}|\{{(?P<x>X)\}}) (?P<dir>less|more) to activate(?P<nomana> unless they're mana abilities)?(?:, where X is (?P<xv>~'s (?:power|toughness)))?"  # (wave 44D: Agatha of the Vile Cauldron; wave 53B: Anointed Peacekeeper)
    rf"(?:\. (?P<floor>this effect can't reduce the mana in that cost to less than one mana))?$",
    re.IGNORECASE)
# -- equip (wave 15E) -- "Equip abilities you activate cost {1} less to activate." (Bureau Headmaster), "Equip costs you pay cost
# {1} less." (Auriok Steelshaper), "Equip abilities you activate of other Equipment cost {1} less to activate." (Bladehold
# War-Whip): a cost modifier (601.2f) of equip abilities only (attachments.is_equip_text), the player's own
EQUIP_COST = re.compile(
    rf"^equip (?:abilities you activate(?P<other> of other equipment)?|costs you pay) costs? {_N} (?P<dir>less|more)(?: to activate)?$",
    re.IGNORECASE)
POWER_UP_COST = re.compile(rf"^power-up abilities of (?P<sel>other creatures you control) cost {_N} less to activate$", re.IGNORECASE)
# An effect's cost modifier with a duration (611.2a): "Artifact, instant, and sorcery spells you cast this turn cost {2}
# less to cast." (Urza, Planeswalker) / "Until your next turn, instant and sorcery spells you cast cost {1} less to cast."
# (Ral, Leyline Prodigy)
STORED_COST = re.compile(
    rf"^(?P<until>until your next turn, )?{_SEL} spells you cast (?P<this_turn>this turn )?cost {_N} (?P<dir>less|more) to cast$",
    re.IGNORECASE)
# -- cost changers (wave 44D) -- "Spells you cast this turn that are white and/or blue cost {X} less to cast, where X is the amount of life you gained this turn." (Will,
# Scion of Peace; Rowan, Scion of War): X is read once, as the ability resolves (the rulings of 2023-09-01), then it is the stored cost modifier above
STORED_COST_X = re.compile(r"^spells you cast this turn that are (?P<sel>[a-z]+) and/or (?P<sel2>[a-z]+) cost \{X\} less to cast, where X is (?P<v>.+)$", re.IGNORECASE)
# "This spell costs {1} less to cast for each creature card in your graveyard."
SELF_PER = re.compile(rf"^(?:this spell|~) costs {_N} less to cast for each (?P<what>.+)$")
# "This spell costs {1} less to cast if you control a Wizard."
SELF_IF = re.compile(rf"^(?:this spell|~) costs {_N} less to cast if (?P<cond>.+)$")
# "You may cast creature spells from the top of your library." / "You may play lands from your
# graveyard." / "Once during each of your turns, you may cast a creature spell from your graveyard."
# -- cast permissions (wave 30Q) -- also "During your turn, …" (Leonardo, Festival of Embers), "During each of your turns, you may play a land and
# cast a permanent spell of each permanent type from your graveyard." (Muldrotha: one use per type, ``slots``), "… play lands and cast Insect spells …"
# (Zask), "You may play Forests / Desert lands from your graveyard." (Titania, Hazezon: the land's own kind), "… play a [historic] land [from your
# graveyard] or cast a … spell [with mana value 3 or less] from your graveyard" (Serra Paragon, The Eighth Doctor: one use for either), a quality of the
# spell ("with mana value 2 or less" Lurrus, "with power or toughness 1 or less"), "… by paying 3 life / sacrificing a land … in addition to paying its
# other costs" (Noctis, Maestros Ascendancy: a cost paid with the rest, 601.2b), and the rider "If you cast a spell this way, that artifact enters
# tapped / with a finality counter on it." (Edgar, Noctis, Leonardo) or "If you do, it gains "…"" (Serra Paragon, The Eighth Doctor)
_QUAL = r" with [a-z ]+? (?:\d+ or (?:less|greater)|less than or equal to the number of [a-z]+ counters on ~)"
PERMISSION = re.compile(
    r"^(?:(?P<once>once during each of your turns, )|(?P<during>during (?:your turn|each of your turns), )|(?P<whilst>as long as [^,]+, ))?you may "
    r"(?P<what>play lands and cast spells|play cards|play lands|cast spells|play a land|(?P<slots>play a land and cast a permanent spell of each permanent type)|"
    r"play lands and cast (?P<psel>[a-z][a-z' ,-]*?) spells|play (?P<lsel>[a-z][a-z']*)(?P<lands> lands)?|"
    rf"play a (?P<hist>historic )?land(?: from your graveyard)? or cast (?:a |an )?(?P<csel>[a-z][a-z' ,-]*?) spell(?P<cq>{_QUAL})?|"
    rf"cast (?:a |an )?(?P<sel>[a-z][a-z' ,-]*?) spells?(?P<qual>{_QUAL})?|cast (?:this card|~))"
    rf" from (?P<zone>your graveyard|the top of your library)(?P<qual2>{_QUAL})?"
    r"(?: by (?P<by>.+?) in addition to (?:paying )?(?:its|their) other costs)?"
    # -- cast from graveyard (wave 19C) -- 614.1a: "If a spell cast this way would be put into your graveyard, exile it instead."
    r"(?:\. If (?:(?P<exile>a|an instant or sorcery) spell cast this way would be put into your graveyard, exile it instead"
    r"|(?:you cast a spell this way|you do), (?:that [a-z]+ enters (?:(?P<tapped>tapped)|(?P<fin>with a finality counter on it))|it gains \"(?P<gain>[^\"]+)\"))"
    # -- most-played cards (wave 43B) -- "If you cast a spell this way, pay life equal to its mana value rather than pay its mana cost." (Bolas's Citadel)
    r"|\. If you cast a spell this way, (?P<lmv>pay life equal to its mana value rather than pay its mana cost)"
    # -- if you do (wave 51D) -- 601.3b / 614.1c / 611.2a: the riders of a cast from the top of the library: "If you cast a creature spell this way, it gains haste until end of
    # turn." (Thundermane Dragon), "…, that creature enters with an additional +1/+1 counter on it." (Mikey & Don), "If you cast a spell this way, you may cast it as though it had flash." (Elsha)
    r"|\. If you cast (?P<rtype>a creature spell|a spell) this way, (?:(?P<rhaste>it gains haste until end of turn)|(?P<rcounter>that creature enters with an additional \+1/\+1 counter on it)"
    r"|(?P<rflash>you may cast it as though it had flash)))?$",
    re.IGNORECASE)
_GY_POOL = re.compile(r" from among cards in your graveyard that (?:were put there from (?P<from>anywhere other than the battlefield|your library)|"
                      r"(?P<milled>were milled)) this turn$")  # (-- free cast (wave 40D) --)
# -- resolution memory (wave 22D) -- "You may play lands and cast spells from among cards exiled with this creature." (Nightveil Specter),
# "During your turn, if an opponent lost life this turn, you may play lands and cast spells from among cards exiled with this enchantment."
# (Theater of Horrors): a static permission (611.3a) over the cards the object's linked exiling ability exiled (607.2a)
# -- linked permissions (wave 30H) -- also "You may cast spells from among cards exiled with ~." (Rona), "You may play lands from among …" (Hedonist's
# Trove), "You may play cards exiled with ~ as long as you attacked this turn." (Pick Up the Pace), "You can't cast more than one spell this way each
# turn." (Hedonist's Trove: once a turn, any turn) and "If you cast a spell this way, pay life equal to its mana value rather than pay its mana cost."
# (Valgavoth: the alternative cost of 118.9, 119.4, always paid when the permission is used)
LINKED_PLAY = re.compile(r"^(?:(?P<during>during your turn), )?(?:(?:if|as long as) (?P<cond>[^,]+), )?you may "
                         r"(?P<what>play lands and cast spells from among|cast spells from among|play lands from among|play) cards exiled with ~"
                         r"(?: as long as (?P<cond2>[^,.]+))?(?:\. (?:(?P<once>[Yy]ou can't cast more than one spell this way each turn)"
                         r"|(?P<life>[Ii]f you cast a spell this way, pay life equal to its mana value rather than pay its mana cost)))?$")


def exiled_with_exiles(line: str) -> bool:
    """Is this ability line one that exiles (the linked ability of "cards exiled with ~")? (read as text: the cards exile only through it)"""
    return re.search(r"\bexiles?\b", line, re.IGNORECASE) is not None and "exiled with" not in line


SELF_GY_BY = re.compile(r"^you may cast (?:this card|~) from your graveyard by (?P<cost>.+) in addition to paying its other costs"
                        r"(?P<exile>\. Then exile this card)?$")  # (-- casting extras (wave 18E) -- jump-start 702.133a: exiled as it leaves the stack)
# -- keyword grants (wave 17C) -- 702.81a: "Instant and sorcery cards in your graveyard have retrace." / "During your turn, nonland
# permanent cards in your graveyard have retrace." — a permission to cast those cards from the graveyard whose additional cost is
# discarding a land card (the granted keyword's meaning, as the card's own retrace line says it)
RETRACE_GRANT = re.compile(r"^(?P<during>during your turn, )?(?P<sel>[a-z][a-z' ,-]*?) cards in your graveyard have retrace$", re.IGNORECASE)
_GERUND = {"discarding": "discard", "paying": "pay", "sacrificing": "sacrifice", "exiling": "exile", "removing": "remove"}
# -- free_cast (wave 20D) -- "You may cast this card from exile." (Eternal Scourge), "… from your graveyard or from exile." (Squee, the
# Immortal): the card's own ability, functioning in those zones (113.6b), a permission to cast it from where it is
SELF_EXILE = re.compile(r"^you may cast (?:this card|~) from (?P<z>exile|your graveyard or from exile)$")
SELF_GY_WHILE = re.compile(r"^you may cast (?:this card|~) from your graveyard (?:as long as|if) (?P<cond>.+)$")  # (wave 4B; 16D: "if")
# "You may cast creature spells as though they had flash." (601.3b)
FLASH = re.compile(rf"^you may cast (?:{_SEL} )?spells as though they had flash$")
TOP_REVEAL = "play with the top card of your library revealed"
REVEALED_ZONES: dict[str, dict[str, str]] = {  # -- revealed zones (wave 25A) --
    "players play with the top card of their libraries revealed": {"zone": "library", "whose": "players"},
    "your opponents play with their hands revealed": {"zone": "hand", "whose": "opponents"},
    "players play with their hands revealed": {"zone": "hand", "whose": "players"},
    "play with your hand revealed": {"zone": "hand", "whose": "you"},
}
TOP_LOOK = "you may look at the top card of your library any time"
# 708.5 lets you look at your own face-down permanents only; these let you look at the others' (creatures: face-down spells aren't
# permanents). In Commander every other player is an opponent.
FACE_DOWN_LOOK = re.compile(r"^you may look at (?P<top>the top card of your library and at )?face-down creatures "
                            r"(?:you don't control|your opponents control) any time$")
# -- durations (wave 30M) -- 611.2a: "Until your next turn, you may play that card." (Three Wishes) / "Until the beginning of your next upkeep, …"
# (Elkin Bottle, Grinning Totem): ends as that player's next turn begins (500.4; no player gets priority in the untap step, 502.4, so the two
# wordings end the same way for a permission)
_UNTILS = "until end of turn|until the end of your next turn|until your next end step|until your next turn|until the beginning of your next upkeep"
# Effect sentences: "Exile the top card of your library. You may play that card this turn." — the
# pronoun ("that card" / "it" / "those cards") is bound by scripts.resolve_it to what an earlier
# instruction of the same ability moved (400.7j: found where it went); with no such instruction
# the ability stays manual. A bare "You may cast that card." (no duration) means "cast it now, as
# this resolves, ignoring timing" — not a permission that lasts: refused.
GRANT_THAT = re.compile(rf"^(?:(?:(?P<until>{_UNTILS})|during any turn you attacked with (?P<watt>[^,]+)), )?you may (?P<verb>play|cast) "  # (wave 51E: watt)
                        r"(?:(?P<upto>(?:up to (?P<upn>one|two|three|four)|(?P<one>one)) of ))?(?P<what>that card|those cards|it)(?P<from_ex> from exile)?(?P<this_turn> this turn)?(?P<free> without paying (?:its|their) mana costs?)?"
                        r"(?:, and (?P<spend>mana of any type can be spent to cast (?:that spell|those spells))"  # (wave 25C: Dire Fleet Daredevil)
                        r"| and (?P<spend2>you may spend mana as though it were mana of any (?P<k2>color|type) to cast (?:that spell|those spells)))?"
                        r"(?P<life>, paying life equal to its mana value rather than paying its mana cost)?$")  # (Hurl Through Hell)
# -- free cast (wave 40D) -- "Until end of turn, you may cast noncreature spells from among those cards without paying their mana costs." (Narset, Enlightened
# Master), "Until end of turn, you may cast spells from among them." (Apex of Power): a permission (611.2a) for each of the cards an earlier instruction moved,
# any number of them, with the cast's own timing (601.3) — the spell kind a quality of the permission (it is read when a card is cast)
AMONG_GRANT = re.compile(rf"^(?P<until>{_UNTILS}), you may cast (?:(?P<one>an?) )?(?:(?P<sel>[A-Za-z][A-Za-z' ,-]*?) )?(?P<sp>spells?) from among (?:them|those cards|those exiled cards|the exiled cards)"
                         r"(?P<free> without paying (?P<poss>its|their) mana costs?)?"
                         r"(?:,? and (?:(?P<spend>mana of any type can be spent to cast (?:those spells|them))|"
                         r"you may spend mana as though it were mana of any (?P<kind>color|type) to cast (?:those spells|them)))?$")
# -- refused grants/replacements (wave 3R2) -- "You may play that card until the end of your next turn."
_TRAILING_UNTIL = re.compile(r"^(?P<rest>you may (?:play|cast) (?:up to (?:one|two|three|four) of )?(?:that card|those cards|it|them)(?: without paying (?:its|their) mana costs?)?) "
                             rf"(?P<until>{_UNTILS})$")
# -- end refused grants/replacements (wave 3R2) --
# "Until end of turn, you may play lands and cast spells from your graveyard." (Yawgmoth's Will)
# -- cast permissions (wave 30Q) -- also "You may cast a creature spell from your graveyard this turn." (Chainer: one spell) and "You may cast Zombie spells
# from your graveyard this turn." (Liliana, Untouched by Death: any number)
# (-- zone replacements (wave 37B) -- "When you unlock this door, you may cast spells from your graveyard this turn" (Walk-In Closet): the trigger's own "you may"
# is the ability's, so the sentence arrives without it)
GRANT_ZONE = re.compile(r"^(?:(?P<until>until end of turn), )?(?:you may )?(?P<what>play lands and cast spells|play lands|cast spells|"
                        r"cast (?P<a>an? )?(?P<sel>[A-Za-z][A-Za-z' ,-]*?) (?P<sp>spells?))"
                        r" from (?P<owner>your|any) graveyard(?P<this_turn> this turn)?$")
# -- cast a copy (wave 13C) -- "You may cast the copy without paying its mana cost." (707.12; each copy is its own choice, 707.12a)
# (wave 18F: without "without paying …" the copy's mana cost is paid: 707.12 "You may cast the copy. (You still pay its costs.)")
FREE_COPY = re.compile(r"^(?:if you do, )?you may cast (?P<w>the copy|the copies|any number of the copies)(?P<free> without paying (?:its|their) mana costs?)?$")
# -- trigger other (wave 44D) -- "Whenever you discard a nonland card, you may cast it from your graveyard." (Oskar, Rubbish Reclaimer): cast now, as this resolves (608.2g), paying its
# costs (the Oskar ruling of 2022-04-29: "You may cast the spell immediately. You must pay all costs")
CAST_IT_FROM_GRAVEYARD = re.compile(r"^(?:you may )?cast (?:it|that card) from your graveyard$")
# -- cast without paying (wave 3C) --
# "You may cast a spell with mana value 5 or less from your hand without paying its mana cost." (cast now,
# as this resolves: 608.2g) / "You may cast an instant or sorcery spell from your hand with mana value X
# or less without paying its mana cost."
FREE_HAND = re.compile(r"^(?:you may )?cast (?:a|an) (?:(?P<sel>[A-Za-z][A-Za-z' ,-]*?) )?(?:spell|card)(?P<h1> from your hand)?"
                       r"(?: with mana value (?:(?P<n>\d+|X) or less|less than or equal to (?P<x2>[^,]+?)))?"
                       # -- if you do (wave 40A) -- "a permanent spell with equal or lesser mana value" (Kellan, the Kid), "a spell with lesser mana value that shares a card type
                       # with it" (Baral and Kari Zev): than the spell that triggered it, the reading of Rashmi's "lesser mana value" below (_free_if)
                       r"(?: with (?P<rel>equal or lesser|lesser) mana value(?P<share> that shares a card type with it)?)?(?P<h2> from your hand)?"
                       r" without paying its mana cost$")
# -- play now (wave 28A) -- "You may play a land from the top of your library or cast a spell with mana value less than or equal to the damage dealt
# from the top of your library without paying its mana cost." (Ziatora's Envoy): the card looked at, a land played (305.2a) or a spell cast within the limit
PLAY_OR_CAST_TOP = re.compile(r"^you may play a land from the top of your library or cast a spell with mana value (?:(?P<n>\d+|X) or less|"
                              r"less than or equal to (?P<v>[^,]+?)) from the top of your library without paying its mana cost$")
# "You may cast spells from your hand without paying their mana costs." (Omniscience) / "You may cast
# Dragon spells without paying their mana costs."
STATIC_FREE = re.compile(r"^you may cast (?:(?P<sel>[A-Za-z][A-Za-z' ,-]*?) )?spells(?P<hand> from your hand)? without paying their mana costs$")
# "If you control a commander, you may cast this spell without paying its mana cost." (Fierce Guardianship)
SELF_FREE = re.compile(r"^if you control a commander, you may cast (?:this spell|~) without paying its mana cost$")
# -- end cast without paying (wave 3C) --
# -- refused look/cast-free (wave 3R5) -- casts made as the ability resolves (608.2g), with more
# instructions after them: "You may cast an instant or sorcery spell with mana value less than or
# equal to ~'s power from among them without paying its mana cost." (the cards looked at / exiled),
# "You may cast any number of spells with mana value X or less from among them without paying their
# mana costs.", "You may cast up to two sorcery spells …", "You may cast target instant or sorcery
# card with mana value 3 or less from your graveyard without paying its mana cost."
_FREE_MV = r"with mana value (?:(?P<n>\d+|X) or less|less than or equal to (?P<v>[^,]+?))"
FREE_AMONG = re.compile(
    r"^(?:you may )?cast (?:(?P<q>a|an|up to (?P<k>one|two|three)|any number of) )?(?:(?P<sel>[A-Za-z][A-Za-z' ,-]*?) )?(?P<sp>spells?)"
    rf"(?: {_FREE_MV.replace('?P<n>', '?P<n1>').replace('?P<v>', '?P<v1>')})?"
    r"(?: with mana value (?P<eq>X))?"  # -- linked casting (wave 30H) -- exactly X: "a spell with mana value X from among cards exiled with ~" (Kaho)
    r" from among (?P<src>them|those cards|those nonland cards|cards revealed this way|the revealed cards|the exiled cards"
    r"|cards exiled this way|the cards exiled this way|the nonland cards exiled this way)"  # (wave 44A: a land is never cast, so "nonland" adds nothing)
    rf"(?: {_FREE_MV.replace('?P<n>', '?P<n2>').replace('?P<v>', '?P<v2>')})?"
    r"(?P<free> without paying (?:its|their) mana costs?)?$")  # (wave 50G: without it, the cast is paid for, as the ability resolves: 608.2g, Nathan Drake)
# -- cast riders (wave 38C) -- "You may cast a spell from among cards you own in exile with dream counters on them without paying its mana cost." (Goliath
# Daydreamer; the cards its other ability exiled), "… from among cards in exile with page counters on them …" (Tasha, the Witch Queen: any owner's): one at a time
FREE_COUNTED = re.compile(r"^(?:you may )?cast (?:a|an) (?:(?P<sel>[A-Za-z][A-Za-z' ,-]*?) )?spell from among cards (?P<own>you own )?in exile with "
                          r"(?P<kind>[a-z]+) counters on them without paying its mana cost$")
# "Once during each of your turns, you may cast an instant or sorcery spell from your hand without paying its
# mana cost." (Zaffai and the Tempests): a static permission used up by the cast (``consume``), on its
# controller's own turns only, with the cast's normal timing (601.3: a permission, not a cast as something resolves)
ONCE_FREE = re.compile(r"^once during each of your turns, you may cast (?:a|an) (?:(?P<sel>[a-z][a-z' ,-]*?) )?spell from your hand "
                       r"(?P<top>or the top of your library )?without paying its mana cost$")
# -- casting costs (wave 22F) -- 118.9 / 119.4: "Once during each of your turns, you may cast an enchantment spell by paying life equal to its mana value
# rather than paying its mana cost." (Demon of Fate's Design) — an alternative cost of {0} plus life (X is 0, 107.3b), chosen with the free cast
ONCE_LIFE = re.compile(r"^once during each of your turns, you may cast (?:a|an) (?:(?P<sel>[a-z][a-z' ,-]*?) )?spell(?P<hand> from your hand)? by paying "
                       r"life equal to its mana value rather than paying its mana cost$")
# -- if you do (wave 25C) -- also "You may cast target instant or sorcery card from your graveyard this turn." (a permission for that card,
# 611.2a), "Until end of turn, you may cast target … without paying its mana cost." and the bare "You may cast target instant card from
# your graveyard." (cast as this resolves, its mana cost paid: 608.2g, the paid free_cast of the copy wording)
FREE_TARGET = re.compile(r"^(?:(?P<until>until end of turn), )?(?:you may )?(?P<verb>cast|play) (?P<what>target .+?)(?P<this_turn> this turn)?"
                         r"(?P<free> without paying its mana cost)?(?:, and (?P<spend>mana of any type can be spent to cast that spell))?$")
_FREE_COUNT = {"a": 1, "an": 1, "up to one": 1, "up to two": 2, "up to three": 3, "any number of": 99}


def free_mv(n: str | None, v: str | None) -> Any:
    """The mana value limit of a free cast: a number, "x" (the X of the spell or ability), or a
    value read as it resolves (608.2h): "~'s power", "that damage" (the trigger event's amount),
    "the number of Spirits you control" (app/rules/values.py). Raises ValueError if unread."""
    from app.rules import language

    if n is not None:
        return "x" if n == "X" else int(n)
    if v is None:
        return None
    if v == "X":
        return "x"
    if v in ("that damage", "the damage dealt", "the amount of damage dealt"):
        return {"event_amount": 1}
    try:
        value = language._stat(v.replace("this creature's", "~'s"), "self")
    except Exception as exc:  # noqa: BLE001  (language._Fail: a phrase the value grammar doesn't read)
        raise ValueError(v) from exc
    if not isinstance(value, dict) or "it" in value.values():
        raise ValueError(v)  # ("its power": whose? not bound here)
    return value


# -- play now (wave 28A) -- "You may play lands and cast spells from among cards exiled this way without paying their mana costs." (Gix, Yawgmoth
# Praetor): any number of them, one at a time (608.2g); a land only while a land play is left (305.2a-b)
PLAY_AMONG = re.compile(r"^you may play lands and cast spells from among (?:them|those cards|cards exiled this way|the exiled cards|the cards exiled this way)"
                        r" without paying their mana costs$")


# "You may play one of those cards without paying its mana cost." (Vault 112: Sadistic Simulation): one card of those an earlier instruction exiled
PLAY_ONE = re.compile(r"^you may (?P<verb>play|cast) one of (?:those|the exiled) cards without paying its mana cost$")


# -- hideaway (wave 29D) -- "…, you may play one of them without paying its mana cost." (Evercoat Ursine: the cards exiled with it, 607.2a) - read only
# in an ability that refers to what another exiled (exiled_with.linked)
_LINKED_ONE = re.compile(r"^you may (?P<verb>play|cast) one of them without paying its mana cost$")


def _linked_one(text: str) -> re.Match[str] | None:
    from app.rules import exiled_with

    return _LINKED_ONE.fullmatch(text) if exiled_with.linked() else None


def _free_among(text: str) -> list[dict[str, Any]] | None:
    if PLAY_AMONG.fullmatch(text):
        return [{"do": "free_cast", "zone": "among", "who": "them:card", "filter": None, "optional": True, "mv": None, "n": 99, "play": True}]
    if (one := PLAY_ONE.fullmatch(text) or _linked_one(text)) is not None:
        return [{"do": "free_cast", "zone": "among", "who": "them:card", "filter": None, "optional": True, "mv": None, "n": 1,
                 **({"play": True} if one["verb"] == "play" else {})}]
    if (c := FREE_COUNTED.fullmatch(text)) is not None:  # -- cast riders (wave 38C) -- the cards in exile with that kind of counter (``_free_pool``)
        key = spell_filter(c["sel"]) if c["sel"] else None
        if c["sel"] and key is None:
            return None
        return [{"do": "free_cast", "zone": "exile_counters", "kind": c["kind"], "own": bool(c["own"]), "filter": key, "optional": True, "mv": None, "n": 1}]
    m = FREE_AMONG.fullmatch(text)
    if m is None:
        return None
    if (m["n1"] or m["v1"]) and (m["n2"] or m["v2"]) or (m["eq"] and (m["n1"] or m["v1"] or m["n2"] or m["v2"])):
        return None
    if m["q"] is None and m["sp"] != "spells":
        return None  # ("cast instant and sorcery spells … from among them": any number of them; "cast spell": not English)
    key = spell_filter(m["sel"]) if m["sel"] else None
    if m["sel"] and key is None:
        two = re.fullmatch(r"(.+?) or (.+)", m["sel"])  # -- cant restrictions (wave 50G) -- "a Vehicle or artifact creature spell" (Sanwell): a spell of either kind, each its own selector
        if two is None or not (first := spell_filter(two[1])) or not (second := spell_filter(two[2])):
            return None
        key = selectors.Selector(either=(first, second), zones=("stack",)).key()
    try:
        mv = free_mv(m["n1"] or m["n2"], m["v1"] or m["v2"])
    except ValueError:
        return None
    # "zone": "among" — resolved to the cards looked at (still in the library: "looked") or to the
    # cards an earlier instruction moved ("that", a binding) by scripts.resolve_it
    return [{"do": "free_cast", "zone": "among", "who": "them:card", "filter": key, "optional": True, "mv": "x" if m["eq"] else mv,
             "n": _FREE_COUNT[m["q"] or "any number of"], **({"mv_eq": True} if m["eq"] else {}), **({} if m["free"] else {"paid": True})}]


# "You may cast it without paying its mana cost if it's a spell with lesser mana value." (Rashmi, Eternities
# Crafter), "… if its mana value is odd." (Yennett), "… if that spell's mana value is 8 or less.", "… if the
# spell's mana value is less than the number of Mountains you control.", "… if it's an instant or sorcery spell."
FREE_IF = re.compile(r"^(?:then )?you may cast (?:it|that card|the exiled card|the revealed card) without paying its mana cost "
                     r"if (?P<cond>.+)$")
_MV_OF = r"(?:its|that spell's|the spell's) mana value is"
# "You may cast an instant or sorcery spell from your graveyard with mana value 4 or less without paying its mana
# cost." (Diviner of Mist) / "… from a graveyard …" (every graveyard: public, 400.2)
FREE_GY = re.compile(r"^(?:you may )?cast (?:a|an) (?:(?P<sel>[A-Za-z][A-Za-z' ,-]*?) )?spell(?P<g1> from (?P<w1>your|a) graveyard)?"
                     rf"(?: {_FREE_MV})?(?P<g2> from (?P<w2>your|a) graveyard)?(?P<free> without paying its mana cost)?$")


def _free_if(text: str) -> list[dict[str, Any]] | None:
    """The cast of the card just revealed / exiled, on a condition about the spell it would be: a mana
    value limit (``mv``: at most, ``mv_lt``: less than), its parity, or a kind of spell (``filter``)."""
    m = FREE_IF.fullmatch(text)
    if m is None:
        return None
    cond = m["cond"]
    e: dict[str, Any] = {"do": "free_cast", "zone": "that", "who": "it:card", "filter": None, "optional": True, "mv": None, "n": 1}
    try:
        if cond == "it's a spell with lesser mana value":  # (than the spell that triggered it: Rashmi)
            e["mv_lt"] = {"mana_value": "event"}
        elif (c := re.fullmatch(rf"(?:it's a spell with mana value|{_MV_OF}) (?:(?P<n>\d+) or less|less than or equal to "
                                r"(?P<v>.+)|less than (?P<lt>.+))", cond)):
            if c["lt"]:
                e["mv_lt"] = free_mv(None, c["lt"])
            else:
                e["mv"] = free_mv(c["n"], c["v"])
        elif (c := re.fullmatch(rf"{_MV_OF} (?P<p>odd|even)", cond)):
            e["parity"] = c["p"]
        elif (c := re.fullmatch(r"it's (?:a|an) (?P<sel>[a-z][a-z ,]*?) spell", cond)):
            e["filter"] = spell_filter(c["sel"])
            if e["filter"] is None:
                return None
        else:
            return None
    except ValueError:
        return None
    return [e]


def _free_gy(text: str) -> list[dict[str, Any]] | None:
    m = FREE_GY.fullmatch(text)
    if m is None or bool(m["g1"]) == bool(m["g2"]):
        return None
    key = spell_filter(m["sel"]) if m["sel"] else None
    if m["sel"] and key is None:
        return None
    try:
        mv = free_mv(m["n"], m["v"])
    except ValueError:
        return None
    if not m["free"] and (mv is not None or (m["w1"] or m["w2"]) != "your"):
        return None  # -- if you do (wave 25C) -- the paid cast of "a spell from your graveyard" (608.2g): own graveyard, no limit read
    return [{"do": "free_cast", "zone": "graveyard", "whose": "you" if (m["w1"] or m["w2"]) == "your" else "any",
             "filter": key, "optional": True, "mv": mv, "n": 1, **({} if m["free"] else {"paid": True})}]


def _free_target(text: str) -> tuple[list[dict[str, Any]], Any] | None:
    """"You may cast target instant or sorcery card [with mana value N or less] from your graveyard
    without paying its mana cost": a target card in a graveyard (public: 400.2), cast as this
    resolves if it's still a legal target (608.2b)."""
    m = FREE_TARGET.fullmatch(text)
    if m is None:
        return None
    # -- free cast (wave 27D) -- "play target …" only as a permission for a stated duration (611.2a). -- review (wave 27D) -- a bare "You may
    # play target Elemental card from your graveyard without paying its mana cost." (Horde of Notions) is played as it resolves (608.2g),
    # a land among them only with a land play left on your turn (305.2a/305.3: Tangled Florahedron's back face): not modelled, stays manual
    play = m["verb"] == "play"
    timed = bool(m["until"] or m["this_turn"])
    if (m["until"] and m["this_turn"]) or (m["spend"] and (m["free"] or (play and not timed))):
        return None  # (a free cast spends no mana; -- cast-permission riders (wave 38C) -- the bare paid cast may: "… from a graveyard, and mana of any type can be spent to cast that spell")
    # -- play now (wave 28A) -- the bare "play target … card from your graveyard [without paying its mana cost]" (Horde of Notions) is played as it
    # resolves (608.2g; a land with a land play left on its controller's turn, 305.2a-b, 305.3: ``free_cast`` "play")
    phrase = m["what"][len("target "):]
    mv = re.search(rf" {_FREE_MV}(?= from )", phrase)
    sel = selectors.parse(phrase)
    if sel is None or sel.player is not None or sel.zones != ("graveyard",) or not sel.card:
        return None
    if mv and mv["v"] is not None and not any(isinstance(c[2], str) and c[2].startswith("src:") for c in sel.compare):
        return None  # (a limit read as it resolves that the selector doesn't read: only "its / ~'s power" is — the target's legality is checked then, 608.2b)
    if timed:
        return [{"do": "grant_play", "who": "target", "play": play, "cast": True, "until": "end_of_turn", "optional": True,
                 **({"free": True} if m["free"] else {}), **({"spend": "type"} if m["spend"] else {})}], sel.key()
    return [{"do": "free_cast", "zone": "target", "filter": None, "optional": True, "mv": None, "n": 1,
             **({} if m["free"] else {"paid": True}), **({"play": True} if play else {}),
             **({"spend": "type"} if m["spend"] else {})}], sel.key()  # (118.14: casting.cast_free spends the mana as the permission says)
# -- end refused look/cast-free (wave 3R5) --


def _lower_first(s: str) -> str:
    return s[:1].lower() + s[1:] if s[:1].isupper() else s


def spell_filter(phrase: str | None, tail: str | None = None) -> str | None:
    """A selector key for "<phrase> spells [<tail>]" ("creature", "instant and sorcery", "Aura or Equipment";
    tail: "with power 4 or greater"), or None when the grammar doesn't read it (the ability then stays manual)."""
    if phrase is None and tail is None:
        return None
    text = re.sub(r"\band\b", "or", (phrase or "").strip()).strip()
    if text.lower() == "historic":  # 700.6: an artifact, a legendary or a Saga
        sel = selectors.parse("spell")
        sel = replace(sel, extras=("historic",)) if sel is not None else None
    else:
        sel = selectors.parse(f"{text} spell {tail or ''}".replace("  ", " ").strip())
    if sel is None or sel.player is not None or sel.zones != ("stack",):
        return None
    kinds = sum(bool(x) for x in (sel.types, sel.subtypes, sel.colors, sel.supertypes, sel.not_types, sel.colorless))
    # (-- cost changers (wave 20E) -- "red or green creature": any of those colors, and the type: the colors are one list, 105.1)
    colors_then_type = re.fullmatch(r"(?:white|blue|black|red|green)(?:(?: or|,) (?:white|blue|black|red|green))+ (?:instant or sorcery|[a-z]+)", text, re.I)  # (wave 44C: Wort, "red or green instant or sorcery")
    if re.search(r"\bor\b|,", text) and not sel.union and kinds > 1 and not (colors_then_type and len(sel.colors) > 1 and sel.types):
        return None  # "red or creature" can't be one selector: a list of one kind only
    return sel.key()


def _permission_what(what: str, sel: str | None, qual: str | None) -> dict[str, Any] | None:
    if what in ("play lands and cast spells", "play cards"):  # (-- free cast (wave 40D) -- 305.1, 601.1: playing cards is playing lands and casting spells: Hades, Sorcerer of Eld)
        return {"play": True, "cast": True, "filter": None}
    if what in ("play lands", "play a land"):
        return {"play": True, "cast": False, "filter": None}
    if what == "cast spells":
        return {"play": False, "cast": True, "filter": None}
    if what in ("cast this card", "cast ~"):
        return {"play": False, "cast": True, "filter": None, "self": True}
    if sel in ("a", "an") and not qual:  # (-- free cast (wave 40D) -- "you may cast a spell from your graveyard": any spell, "a" is the article)
        return {"play": False, "cast": True, "filter": None}
    key = spell_filter(sel, qual.strip() if qual else None)  # (-- cast permissions (wave 30Q) -- the quality is the selector's tail: "permanent" + "with mana value 2 or less")
    if key is None:
        return None
    return {"play": False, "cast": True, "filter": key}


# -- cast permissions (wave 30Q) -- the permission sentence's other forms (PERMISSION): two kinds of card in one use ("play a land … or cast …"),
# a land's own kind ("Forests"), and one use per permanent type (Muldrotha)
SLOT_TYPES = ("Land", "Artifact", "Battle", "Creature", "Enchantment", "Planeswalker")  # 110.4: the permanent types (a land is played, 305.1)


def _permission_forms(m: re.Match[str]) -> dict[str, Any] | None:
    if m["qual2"] and not m["sel"]:
        return None
    if m["slots"]:
        return {"play": True, "cast": True, "filter": spell_filter("permanent"), "slots": True}
    if m["psel"]:
        key = spell_filter(m["psel"])
        return {"play": True, "cast": True, "filter": key} if key else None
    if m["lsel"]:
        key = spell_filter(m["lsel"] + (" land" if m["lands"] else ""))
        return {"play": True, "cast": False, "filter": None, "land_filter": key} if key else None
    if m["csel"]:
        key = spell_filter(m["csel"], m["cq"].strip() if m["cq"] else None)
        return {"play": True, "cast": True, "filter": key, **({"land_filter": "historic"} if m["hist"] else {})} if key else None
    if m["qual"] and m["qual2"]:
        return None
    return _permission_what(m["what"], m["sel"], m["qual"] or m["qual2"])  # ("… spell from your graveyard with mana value …": Arcade Gannon)


# -- casting costs (wave 22F) -- 601.3b-c: "You may cast this spell as though it had flash if it targets a commander." (a target chosen
# while casting), "… if you pay {2} more to cast it." (an additional cost, paid only when the timing needs it), "… if X is 3 or less."
SELF_FLASH_COND = re.compile(r"^you may cast (?:this spell|~) as though it had flash if (?:it targets (?:an? )?(?P<what>.+)|you pay "
                             r"(?P<pay>\{\d+\}) more to cast it|x is (?P<x>\d+) or less)(?:\. \(.*\))?$", re.IGNORECASE)


# -- flash auras (wave 46B) -- 601.3b: "You may cast this spell as though it had flash. If you cast it any time a sorcery couldn't have been cast, the controller of the
# permanent it becomes sacrifices it at the beginning of the next cleanup step." (Ward of Lights, Mystic Veil, Soar …): the flash is the card's own permission, the
# sacrifice a delayed trigger created as the permanent spell resolves (603.7; ruling 2022-12-08: only when this ability was the one used, casting.flash_sac)
SELF_FLASH_SAC = re.compile(r"^you may cast (?:this spell|~) as though it had flash\. if you cast it any time a sorcery couldn't have been cast, the controller of "
                            r"the permanent it becomes sacrifices it at the beginning of the next cleanup step$", re.IGNORECASE)


def flash_condition(t: str) -> dict[str, Any] | None:
    m = SELF_FLASH_COND.fullmatch(t)
    if m is None:
        return None
    if m["pay"]:
        return {"pay": m["pay"]}
    if m["x"]:
        return {"x_max": int(m["x"])}
    sel = selectors.parse(m["what"])
    return {"targets": sel.key()} if sel is not None and sel.player is None else None


def define_static(text: str, kind: str, lines: tuple[str, ...] = ()) -> Definition | None:
    """The definition of one ability line (``scripts.define`` calls this for "static" lines, and
    for the "spell" lines of instants and sorceries so a cost-reduction line on a spell is
    understood). ``text`` is the line with the card's own name written as ~; ``lines`` are all
    the card's ability lines (a permission to cast from the top of the library is only usable
    when the card also reveals that card, or lets its owner look at it)."""
    t = _lower_first(text.strip().rstrip("."))
    t = re.sub(r"(you may) reveal an? (\w+) card from your hand or choose an? \2 you control$", r"\1 behold a \2", t)  # 701.4a (wave 110A): Dragon's Fire
    linked_spend = ""
    if "exiled with ~" in t or "the exiled card" in t:
        if (linked_rider := re.search(r", and (?:you may spend mana as though it were mana of any (?P<kind>color|type) to cast (?:that spell|those spells)|(?P<type>mana of any type can be spent to cast (?:that spell|those spells)))$", t)) is not None:
            linked_spend = "type" if linked_rider["type"] else linked_rider["kind"]
            t = t[:linked_rider.start()]
        t = t.replace("you may cast the exiled card", "you may cast spells from among cards exiled with ~")
    linked_look = bool(re.fullmatch(r"you may look at (?:the )?cards exiled with ~(?:, and you may (?:play lands and cast spells from among|play) those cards)?", t))
    if linked_look:
        if ", and you may " not in t:
            return {"kind": "static", "static": "linked_look", "effects": []}
        t = "you may play cards exiled with ~"
    if kind not in ("static", "spell"):
        return None
    from app.rules import (
        buyback_costs,
        flashback_costs,
        spell_copy_replacements,
        spell_mana_floor,
        x_mana_restrictions,
    )

    if (x_restriction := x_mana_restrictions.definition(t)) is not None:
        return x_restriction
    if kind == "static" and (unlock_reduction := re.fullmatch(r"unlock costs you pay cost \{(?P<n>\d+)\} less", t)) is not None:
        return {"kind": "static", "static": "unlock_cost", "reduce": int(unlock_reduction["n"]), "effects": []}
    if kind == "static" and (floor := spell_mana_floor.definition(t)) is not None:
        return floor
    if kind == "static" and (copy_replacement := spell_copy_replacements.definition(t)) is not None:
        return copy_replacement
    if kind == "static" and (buyback := buyback_costs.definition(t)) is not None:
        return buyback
    if kind == "static" and (flashback := flashback_costs.definition(t)) is not None:
        return flashback
    from app.rules import conditional_cast_permissions

    if (conditional_permission := conditional_cast_permissions.definition(t, kind)) is not None:
        return conditional_permission
    if kind == "static" and t == (
            "you may cast ~ from your graveyard if you pay {1} more to cast it "
            "for each other creature card in your graveyard"):
        return {"kind": "static", "static": "permission", "zone": "graveyard",
                "once": False, "flash": False, "self": True, "play": False,
                "cast": True, "filter": None, "effects": [], "other_creature_tax": True}
    if kind == "static" and t == (
            "you may cast Dinosaur creature spells from among cards you own exiled with ~. "
            "If you cast a spell this way, that creature enters with a finality counter on it"):
        if not any(exiled_with_exiles(line) for line in lines):
            return None
        return {"kind": "static", "static": "permission", "zone": "exile",
                "linked": True, "own": True, "once": False, "flash": False,
                "self": False, "play": False, "cast": True,
                "filter": spell_filter("Dinosaur creature"), "effects": [],
                "enters": {"counters": {"finality": 1}}}
    if kind == "static":
        # 400.7h: the entry consequence belongs only to the card actually cast
        # using this graveyard permission, not to copies of its resulting spell.
        entry_permission = re.fullmatch(
            r"you may cast (?:this card|~) from your graveyard"
            r"(?: by paying (?P<mana>(?:\{[WUBRGC0-9]+\})+) rather than paying its mana cost)?"
            r"\. If you do, it enters with (?P<counters>a finality counter|two \+1/\+1 counters) on it", t)
        if entry_permission is not None:
            return {"kind": "static", "static": "permission", "zone": "graveyard",
                    "once": False, "flash": False, "self": True, "play": False,
                    "cast": True, "filter": None, "effects": [],
                    "alt_mana": entry_permission["mana"] or "",
                    "enters": {"counters": {"finality": 1} if entry_permission["counters"] == "a finality counter" else {"+1/+1": 2}}}
    if kind == "static":  # -- cant restrictions (wave 50G) -- "As long as Haakon is on the battlefield, you may cast Knight spells from your graveyard.": a static of a permanent works only there anyway (113.6)
        t = re.sub(r"^as long as ~ is on the battlefield, (?=you may cast )", "", t)
        if t in ("you may cast this card from your graveyard, but not from anywhere else", "you may cast ~ from your graveyard, but not from anywhere else"):
            # 2006-07-15 ruling: it can't be cast from any other zone, the command zone or one an effect opens included (casting.cast_grant reads ``only``)
            return {"kind": "static", "static": "permission", "zone": "graveyard", "once": False, "flash": False, "self": True, "play": False, "cast": True,
                    "filter": None, "only": True, "effects": []}
    # -- cost changers (wave 44D) -- "Spells you cast with mana value 5 or greater cost {1} less to cast and can't be countered." (Thryx, the Sudden Storm): the cost change
    # (601.2f), whose spells also can't be countered (101.2: ``spell_uncounterable`` reads the mark)
    if (both := re.fullmatch(r"(spells you cast with mana value \d+ or greater cost \{\d+\} less to cast) and can't be countered", t)) is not None:
        cheaper = define_static(both[1], kind, lines)
        return {**cheaper, "uncounterable": True} if cheaper is not None and cheaper.get("static") == "cost_modifier" and cheaper.get("caster") == "you" else None
    # -- costs (wave 3$) -- "As an additional cost to cast this spell, sacrifice a creature." (601.2b): paid with the
    # rest of the cost as the spell is cast (casting.cast_spell); a wording the cost grammar can't pay stays manual
    if cost_changes.OWN_OPTIONAL.fullmatch(t) or cost_changes.ANY_COST.fullmatch(t) or cost_changes.EVIDENCE_REDUCTION.fullmatch(t):  # -- casting costs (wave 22F) -- "you may collect evidence 6" / "you may behold a Dragon"; (wave 47C) "you may sacrifice any number of …"
        return cost_changes.optional_definition(t)
    extra = costs.additional_cost_text(t)
    if extra is not None:
        ok = costs.parse_additional_cost(extra) is not None
        return {"kind": "static", "static": "additional_cost", "cost": extra, "effects": []} if ok else None
    if kind == "static" and (off := offering.definition(t)) is not None:  # -- offering (wave 51H) -- 702.48a
        return off
    if SELF_FLASH_SAC.fullmatch(t):  # -- flash auras (wave 46B) --
        return {"kind": "static", "static": "permission", "zone": "any", "once": False, "flash": True, "self": True, "play": False,
                "cast": True, "filter": None, "flash_sac": True, "effects": []}
    if (fl := flash_condition(t)) is not None:  # -- casting costs (wave 22F) -- 601.3b-d: flash only if a choice made while casting is …
        return {"kind": "static", "static": "permission", "zone": "any", "once": False, "flash": True, "self": True, "play": False,
                "cast": True, "filter": None, "flash_if": fl, "effects": []}
    # -- cost changers (wave 4I) -- "This spell costs {X} less to cast, where X is …" / "… for each …" / "… if …" / "{G} less"
    # (app/rules/cost_changes.py: read as the total cost is determined, 601.2f)
    # -- static_other sweep (wave 16B) -- strive (207.2c ability word) / Fireball: "This spell costs {1}{W} more to cast for each target beyond the
    # first." — an additional cost determined once the targets are chosen (601.2b, 601.2f: total_cost reads them)
    if (sv := _PER_TARGET.fullmatch(t)) is not None:
        pc = M.parse_cost(sv["cost"])
        if pc.hybrid or pc.phyrexian or pc.x or pc.unsupported or pc.is_free:
            return None
        return {"kind": "static", "static": "self_cost", "per_target": sv["cost"], "effects": []}
    if (lv := _LIFE_PER_TARGET.fullmatch(t)) is not None:  # -- wave 110E -- Phyrexian Purge: 118.8 additional life cost, 601.2f once the targets are chosen
        return {"kind": "static", "static": "self_cost", "life_per_target": int(lv["n"]), "effects": []}
    if cost_changes.is_self(t):
        change = cost_changes.self_change(t)
        return {"kind": "static", "static": "self_cost", "change": change, "effects": []} if change else None
    # -- mana provenance (wave 18B) -- K'rrik: each {B} of any cost may be paid with 2 life instead (118.1: life is paid like a Phyrexian
    # symbol; 601.2h: while the cost is paid, casting.life_for_mana)
    if t == "for each {B} in a cost, you may pay 2 life rather than pay that mana":
        return {"kind": "static", "static": "life_for_mana", "sym": "B", "life": 2, "effects": []}
    if " have prowl " in t and kind == "static":  # -- static_other sweep (wave 17C) -- granted prowl (702.76a)
        from app.rules import alt_costs

        return alt_costs.grant_prowl(t)
    if t == "auras attached to permanents you control have umbra armor" and kind == "static":  # -- grants (wave 110A) -- Umbra Mystic
        from app.rules import wave110a_grants

        return wave110a_grants.umbra_static(wave110a_grants.UMBRA)
    if " gain evoke " in t and kind == "static":  # -- grants (wave 110A) -- Ashling, the Limitless
        from app.rules import wave110a_grants

        return wave110a_grants.grant_evoke(t)
    if t.startswith("as ") and ", note your life total" in t and kind == "static":  # -- entry types (wave 110A) -- Sigarda's Splendor
        from app.rules import wave110a_enter

        return wave110a_enter.static(t)
    if t.startswith("as a historic permanent you control enters, it becomes ") and kind == "static":  # -- entry types (wave 110A) -- Displaced Dinosaurs
        from app.rules import wave110a_enter

        return wave110a_enter.static(t)
    if " have freerunning " in t and kind == "static":  # -- grants (wave 110A) -- Ezio Auditore da Firenze
        from app.rules import wave110a_grants

        return wave110a_grants.grant_freerunning(t)
    if " has madness. " in t and kind == "static":  # -- grants (wave 110A) -- Falkenrath Gorger
        from app.rules import wave110a_grants

        return wave110a_grants.grant_madness(t)
    if " has replicate. " in t and kind == "static":  # -- grants (wave 110A) -- Hatchery Sliver, Ian Chesterton
        from app.rules import wave110a_grants

        return wave110a_grants.grant_replicate(t)
    if " has web-slinging " in t and kind == "static":  # -- Marvel keywords (wave 25A) -- granted web-slinging (702.188a)
        from app.rules import alt_costs

        return alt_costs.grant_web_slinging(t)
    if " rather than pay " in t or t.startswith("rather than pay ") or (" without paying its mana cost" in t and t.startswith("if ") and "commander" not in t) \
            or (t.startswith("as long as ") and re.search(r", you may pay [^,]+? to cast (?:this spell|~)$", t)):  # alternative costs (118.9): app/rules/alt_costs.py (wave 49B: "As long as …, you may pay {B/R} to cast this spell")
        from app.rules import alt_costs

        found_alt = alt_costs.define(t)
        if found_alt is not None and (kind == "static" or not found_alt.get("table")):
            return found_alt
    if kind == "static" and t.startswith("as an additional cost to cast "):  # Defiler of Vigor (cost_changes.py)
        return cost_changes.optional_definition(t)
    # -- end cost changers (wave 4I) --
    m = SELF_PER.fullmatch(t)
    if m:
        what = m["what"]
        if what == "opponent":
            return {"kind": "static", "static": "self_cost", "n": int(m["n"]), "per": "opponent", "effects": []}
        sel = selectors.parse(what)
        if sel is None or sel.player is not None:
            return None
        return {"kind": "static", "static": "self_cost", "n": int(m["n"]), "per": sel.key(), "effects": []}
    m = SELF_IF.fullmatch(t)
    if m:
        from app.rules import conditions

        cond = conditions.parse(m["cond"])
        if cond is None or "succeeded" in cond:
            return None
        return {"kind": "static", "static": "self_cost", "n": int(m["n"]), "cond": cond, "effects": []}
    # -- cast without paying (wave 3C) --
    # (-- multi (wave 100N) -- "Spell mastery — If there are two or more instant and/or sorcery cards in your graveyard, this spell can't be countered."
    # (Exquisite Firecraft): judged as the countering spell or ability resolves, its 2021-03-19 ruling)
    if (conditional_counter := re.fullmatch(r"if (?P<c>you revealed an? [A-Z][a-z]+ card or controlled an? [A-Z][a-z]+ as you cast this spell|"
                                            r"there are two or more instant and/or sorcery cards in your graveyard), this spell can't be countered", t)) is not None:
        from app.rules import conditions

        cond = conditions.parse(conditional_counter["c"], objects=True)
        if cond is not None:
            return {"kind": "static", "static": "self_uncounterable", "cond": cond, "effects": []}
    if SELF_FREE.fullmatch(t):
        return {"kind": "static", "static": "permission", "zone": "hand", "once": False, "flash": False, "self": True, "free": True,
                "cond": "commander", "play": False, "cast": True, "filter": None, "effects": []}
    # -- cost alt (wave 16F) -- "You may cast this card from your graveyard by discarding a card in addition to paying its other
    # costs." (Alien Symbiosis): a permission to cast it from there whose additional cost (601.2b) is paid with its mana cost
    m = SELF_GY_BY.fullmatch(t)
    if m:
        extra = re.sub(r"\b(discarding|paying|sacrificing|exiling|removing)\b", lambda g: _GERUND[g[1]], m["cost"])
        if costs.parse_additional_cost(extra) is None:
            return None
        return {"kind": "static", "static": "permission", "zone": "graveyard", "once": False, "flash": False, "self": True,
                "play": False, "cast": True, "filter": None, "extra": extra, "effects": [], **({"exile": True} if m["exile"] else {})}
    if kind == "spell":  # -- as long as (wave 35D) -- 601.3d: an instant's or sorcery's own flash condition ("This spell has flash as long as …")
        from app.rules import cast_limits

        if cast_limits.SELF_FLASH_IF.fullmatch(t) or cast_limits.HAS_FLASH_WHILE.fullmatch(t):
            return cast_limits.static_definition(text)
        if t.startswith(("escape—", "as long as you control a")):  # -- static_other (wave 52C) -- 702.138a: an instant's or sorcery's printed escape (Cling to Dust): functions from the graveyard
            from app.rules import escape

            return escape.define_static(t)
    if kind != "static":
        return None
    # -- small wordings (wave 11E) -- "Creature spells you control can't be countered." (101.2, 701.6)
    # (-- cant restrictions (wave 20F) -- "Creature spells can't be countered" (Gaea's Herald), "Creature spells you cast …", "… you control
    # with power 5 or greater …": whose spells, and a with-tail; 101.2, 701.6)
    if t == "spells and abilities can't be countered":  # -- cant restrictions (wave 46A) -- 101.2, 701.6: Spider-Punk; counter_object lets neither a spell nor an ability be countered
        return {"kind": "static", "static": "spells_uncounterable", "filter": None, "effects": [], "any_player": True, "abilities": True}
    m = re.fullmatch(r"(?:(?P<sel>[\w ,'-]+?) )?spells(?: (?P<own>you control|you cast))?(?: (?P<with>with (?:power|toughness) "
                     r"\d+ or (?:greater|less)))? can't be countered", t)  # (not "mana value": a spell's X, 107.3f, isn't read here)
    if m:
        key = spell_filter(m["sel"], m["with"]) if m["sel"] or m["with"] else None
        if (m["sel"] or m["with"]) and key is None:
            return None
        return {"kind": "static", "static": "spells_uncounterable", "filter": key, "effects": [], **({} if m["own"] else {"any_player": True})}
    m = STATIC_FREE.fullmatch(t)
    if m:
        key = spell_filter(m["sel"]) if m["sel"] else None
        if m["sel"] and key is None:
            return None
        return {"kind": "static", "static": "permission", "zone": "hand" if m["hand"] else "any", "once": False, "flash": False,
                "self": False, "free": True, "play": False, "cast": True, "filter": key, "effects": []}
    m = ONCE_LIFE.fullmatch(t)  # -- casting costs (wave 22F) --
    if m:
        key = spell_filter(m["sel"]) if m["sel"] else None
        if m["sel"] and key is None:
            return None
        return {"kind": "static", "static": "permission", "zone": "hand" if m["hand"] else "any", "once": True, "flash": False, "self": False, "free": True,
                "life_mv": True, "play": False, "cast": True, "filter": key, "effects": []}
    m = ONCE_FREE.fullmatch(t)  # -- refused look/cast-free (wave 3R5) -- a once-each-turn free cast from the hand
    if m:
        key = spell_filter(m["sel"]) if m["sel"] else None
        if m["sel"] and key is None:
            return None
        if m["top"] and not any(_lower_first(x.strip().rstrip(".")) in (TOP_REVEAL, TOP_LOOK) for x in lines):
            return None  # A top-library offer needs the source's own look/reveal permission.
        return {"kind": "static", "static": "permission", "zone": "hand", "once": True, "flash": False,
                "self": False, "free": True, "play": False, "cast": True, "filter": key, "effects": [],
                **({"zones": ["hand", "library_top"]} if m["top"] else {})}
    # -- end cast without paying (wave 3C) --
    t = re.sub(r"^(\w+) spells and (\w+) spells ", r"\1 or \2 spells ", t)  # "kithkin spells and soldier spells you cast"
    # -- cost changers (wave 20E) -- "Red creature spells and green creature spells cost {1} more" is "red or green creature spells"; a
    # leading "As long as ~ is tapped, creature spells you cast cost {2} less to cast" is the same sentence with its condition last
    t = re.sub(r"^(\w+) (\w+) spells and (\w+) \2 spells ", r"\1 or \3 \2 spells ", t, flags=re.I)
    t = re.sub(r"^as long as (?P<c>[^,]+), (?P<r>.+ costs? \{[^}]+\} (?:less|more) to cast)$", r"\g<r> as long as \g<c>", t, flags=re.I)
    if cost_changes.special(t):  # -- cost changers (wave 4I) -- a turn, the chosen type, a zone, "for each", X, colored
        return cost_changes.static_definition(t, lines)
    m = STATIC_COST.fullmatch(t)
    if m:
        if m["sel"] and m["thats"]:
            return None
        phrase = m["sel"] or m["thats"]
        key = spell_filter(phrase, m["with"]) if phrase or m["with"] else None
        if (phrase or m["with"]) and key is None:
            return None
        caster = {None: "any", "you cast ": "you", "your opponents cast ": "opponent"}[m["who"]]
        delta = int(m["n"]) * (-1 if m["dir"] == "less" else 1)
        return {"kind": "static", "static": "cost_modifier", "delta": delta, "caster": caster, "filter": key, "effects": []}
    if (ninjutsu_cost := re.fullmatch(r"ninjutsu abilities you activate cost \{(?P<n>\d+)\} (?P<dir>less|more) to activate", t)) is not None:
        return {"kind": "static", "static": "ability_cost_modifier", "delta": int(ninjutsu_cost["n"]) * (-1 if ninjutsu_cost["dir"] == "less" else 1),
                "filter": None, "who": "you", "floor": False, "ninjutsu": True, "effects": []}
    if (cycling := re.fullmatch(r"cycling abilities you activate cost \{(?P<n>\d+)\} (?P<dir>less|more) to activate", t)) is not None:
        return {"kind": "static", "static": "ability_cost_modifier", "delta": int(cycling["n"]) * (-1 if cycling["dir"] == "less" else 1),
                "filter": None, "who": "you", "floor": False, "cycling": True, "effects": []}
    m = re.fullmatch(r"plotting cards from your hand costs \{(?P<n>\d+)\} less", t)  # -- cant restrictions (wave 46A) -- 702.170a, 118.7a: the plot cost (Doc Aurlock, Grizzled Genius)
    if m:
        return {"kind": "static", "static": "ability_cost_modifier", "delta": -int(m["n"]), "filter": None, "who": "you", "floor": False, "plot": True, "effects": []}
    # -- most-played cards III (wave 46C) -- "Equip abilities you activate that target this creature cost {2} less to activate." (Helitrooper, Fervent Champion, Dwarven
    # Mauler), "Activated abilities of Equipment you control that target this creature cost {1} less to activate." (Bladegraft Aspirant): the ability's target is the
    # source of this static (target_self): known once targets are chosen (601.2c), before the total cost is determined (601.2f)
    tt = re.sub(r" that target (?:this creature|~)", "", t)
    tgt = tt != t
    own_equip = re.fullmatch(r"(?:~|this equipment)'s equip abilities cost \{(?P<n>\d+)\} less to activate", tt)
    if own_equip:
        return {'kind': 'static', 'static': 'ability_cost_modifier', 'delta': -int(own_equip['n']),
                'filter': None, 'who': 'all', 'floor': False, 'equip': True, 'source_only': True, 'effects': []}
    m = EQUIP_COST.fullmatch(tt)
    if m:
        return {"kind": "static", "static": "ability_cost_modifier", "delta": int(m["n"]) * (-1 if m["dir"] == "less" else 1),
                "filter": other.key() if m["other"] and (other := selectors.parse("other Equipment")) else None, "who": "you", "floor": False,
                "equip": True, "effects": [], **({"target_self": True} if tgt else {})}
    m = POWER_UP_COST.fullmatch(tt)
    if m and (pu := selectors.parse(m["sel"])) is not None and pu.other and pu.controller == "you":
        # -- power-up (wave 50J) -- "Power-up abilities of other creatures you control cost {3} less to activate." (Hulk, Gamma Goliath): after the reduction by the
        # permanent's own mana cost (702.193a), on the generic component (118.7a)
        return {"kind": "static", "static": "ability_cost_modifier", "delta": -int(m["n"]), "filter": pu.key(), "who": "you", "floor": False, "power_up": True, "effects": []}
    m = ABILITY_COST.fullmatch(tt)
    if m:  # -- costs (wave 3$) -- the source permanent is matched at the cost, relative to the ability's controller
        key = None
        if m["sel"] == "sources with the chosen name":  # -- chosen filters (wave 53B) -- 201.2 / 709.4a: any source with the permanent's chosen name, in any zone it can be activated from
            key = selectors.Selector(zones=("battlefield", "hand", "graveyard", "exile", "command"), extras=("chosen_name",)).key()
        elif m["sel"] and m["sel"] != "enchanted creature":
            sel = selectors.parse(m["sel"])
            if sel is None or sel.player is not None or sel.card or sel.zones != ("battlefield",) or sel.controller == "opponent" \
                    or sel.extras or sel.attacking or sel.blocking:
                return None
            key = sel.key()
        sign = -1 if m["dir"] == "less" else 1
        xtra: dict[str, Any] = {}
        if m["x"]:  # -- cost changers (wave 44D) -- "{X} less to activate, where X is ~'s power": the source's power, read as each cost is determined (601.2f)
            value = cost_changes._value(m["xv"] or "")
            if value is None:
                return None
            xtra = {"value": value, "sign": sign}
        elif m["xv"]:
            return None
        return {"kind": "static", "static": "ability_cost_modifier", "delta": 0 if m["x"] else int(m["n"]) * sign,
                "filter": key, "who": "you" if m["yours"] or (m["sel"] and "you control" in m["sel"]) else "any",
                "floor": bool(m["floor"]), "effects": [], **({"attached_host": True} if m["sel"] == "enchanted creature" else {}), **xtra, **({"target_self": True} if tgt else {}), **({"nonmana": True} if m["nomana"] else {})}  # (wave 53B: "unless they're mana abilities", 605.1a)
    # -- conditional statics (wave 4B) -- "You may cast this card from your graveyard as long as you control a Zombie."
    # (Gravecrawler; 113.6f: functions from the graveyard; 611.3a: checked whenever the cast is offered or begun)
    m = RETRACE_GRANT.fullmatch(t)
    if m:
        key = spell_filter(m["sel"])
        if key is None:
            return None
        return {"kind": "static", "static": "permission", "zone": "graveyard", "once": False, "flash": False, "self": False,
                "play": False, "cast": True, "filter": key, "extra": "discard a land card", "own": True,
                **({"during": "your_turn"} if m["during"] else {}), "effects": []}
    if t in ("you may cast this card from exile as long as you've cast another spell this turn",
             "you may cast ~ from exile as long as you've cast another spell this turn"):
        return {'kind':'static','static':'permission','zone':'exile','once':False,'flash':False,
                'self':True,'play':False,'cast':True,'filter':None,
                'while':{'history':'spells','n':1},'effects':[]}
    if (m := SELF_EXILE.fullmatch(t)) is not None:
        return {"kind": "static", "static": "permission", "zone": "exile", "zones": ["graveyard", "exile"] if "graveyard" in m["z"] else ["exile"],
                "once": False, "flash": False, "self": True, "play": False, "cast": True, "filter": None, "effects": []}
    m = SELF_GY_WHILE.fullmatch(t)
    if m:
        from app.rules import conditions

        cond = conditions.parse(m["cond"])
        if cond is None or "succeeded" in cond or "flag" in cond:
            return None
        return {"kind": "static", "static": "permission", "zone": "graveyard", "once": False, "flash": False, "self": True,
                "play": False, "cast": True, "filter": None, "while": cond, "effects": []}
    # -- top of library (wave 5I) -- "You may cast Dragon spells / artifact spells and colorless spells / creature spells of
    # the chosen type … from the top of your library", Radha's look-and-play line (app/rules/top_library.py)
    from app.rules import escape, mayhem, top_library, zone_grants

    if (top := top_library.permission(t, lines)) is not None:
        return top
    if t.lower().startswith("each ") and (found_mayhem := mayhem.define_grant(t)) is not None:  # -- Marvel keywords (wave 25A) -- 702.187
        return found_mayhem
    if re.search(r" in (?:your|each player's) (?:hand|graveyard)(?: that's [^.]*?)? (?:has|have) ", t) and (found_zone := zone_grants.define(t)) is not None:  # -- zone keyword grants (wave 25A)
        return found_zone
    if t.lower().startswith(("escape—", "each ", "you may cast ~ from your graveyard by", "you may cast this c", "as long as you control a")) and (found_escape := escape.define_static(t)) is not None:
        return found_escape  # (702.138a: a printed escape cost, or "Each nonland card in your graveyard has escape. …")
    # -- end top of library (wave 5I) --
    if (m := LINKED_PLAY.fullmatch(t)) is not None:  # -- resolution memory (wave 22D) -- 607.2a: "cards exiled with ~" (app/rules/exiled_with.py)
        cond = None
        if m["cond"] and m["cond2"] or (m["once"] and m["what"] != "cast spells from among") or (m["life"] and m["what"] != "play"):
            return None
        if m["cond"] or m["cond2"]:
            from app.rules import conditions

            cond = conditions.parse(m["cond"] or m["cond2"])
            if cond is None or "succeeded" in cond or "flag" in cond:
                return None
        exiling = [x for x in lines if x.strip().rstrip(".") and exiled_with_exiles(x)]
        linked_face_down = linked_look or any(re.search(r"you may look at (?:it|that card) for as long as it remains exiled", x, re.IGNORECASE)
                                                   for x in exiling)
        if not exiling or (not linked_face_down and any("face down" in x.lower() for x in exiling)):
            return None  # (the linked ability must be one that exiles: otherwise the permission has nothing to read; review 22D: a card
            # exiled face down is hidden even from its exiler unless the text lets them look, 406.3 — not read)
        return {"kind": "static", "static": "permission", "zone": "exile", "linked": True, "linked_look": linked_look, "linked_face_down": linked_face_down, "spend": linked_spend, "once": bool(m["once"]), "flash": False, "self": False,
                "play": m["what"] != "cast spells from among", "cast": m["what"] != "play lands from among", "filter": None, "effects": [],
                **({"once_any": True} if m["once"] else {}), **({"free": True, "life_mv": True} if m["life"] else {}),
                **({"during": "your_turn"} if m["during"] else {}), **({"if": cond} if cond is not None else {})}
    # -- free cast (wave 40D) -- "… from among cards in your graveyard that were put there from anywhere other than the battlefield / from your library this turn"
    # (Banon, Kagha), "… that were milled this turn" (Raul): the permission of the graveyard, for the cards that arrived this turn as that says (the turn's log, 400.7)
    if t == "you may cast spells that have a cycling ability from your graveyard":
        sel = selectors.parse("spell with a cycling ability")
        assert sel is not None
        return {"kind": "static", "static": "permission", "zone": "graveyard", "once": False,
                "flash": False, "self": False, "play": False, "cast": True, "filter": sel.key(), "effects": []}
    pool = _GY_POOL.search(t)
    m = PERMISSION.fullmatch(t[:pool.start()] + " from your graveyard" if pool is not None else t)
    if m:
        what = _permission_forms(m)
        if what is None:
            return None
        zone = "graveyard" if m["zone"] == "your graveyard" else "library_top"
        if (what.get("self") and zone != "graveyard") or (m["exile"] and (zone != "graveyard" or what.get("self"))):
            return None
        extras: dict[str, Any] = {}
        if m["whilst"]:  # -- as long as (wave 35D) -- 611.3a: "As long as ~ is attached to a creature, you may play lands and cast spells from the top of your
            # library." (The Reality Chip, Summoning Materia), "As long as an opponent controls more lands than you, you may play lands from the top of
            # your library." (Verge Rangers): the permission of the top of the library, read afresh as a card there is looked at
            from app.rules import statics

            cond = statics.condition(m["whilst"][len("as long as "):-2])
            if zone != "library_top" or what.get("self") or cond is None or "succeeded" in cond or "flag" in cond:
                return None
            extras["if"] = cond
        if m["by"] or m["tapped"] or m["fin"] or m["gain"] or m["during"] or m["slots"] or m["lsel"] or m["psel"] or m["csel"]:
            if (zone != "graveyard" or what.get("self")) and not (  # (-- if you do (wave 51D) -- "play lands and cast Mutant, Ninja, or Turtle spells from the top of your library", Mikey & Don: the same wording as Zask's)
                    zone == "library_top" and m["psel"] and not what.get("self") and not (m["by"] or m["tapped"] or m["fin"] or m["gain"] or m["during"] or m["slots"] or m["lsel"] or m["csel"])):
                return None  # (-- cast permissions (wave 30Q) -- the new wordings are the graveyard's)
            if m["by"]:  # 601.2b: "by paying 3 life / sacrificing a creature in addition to paying its other costs" is an additional cost, paid with the rest
                extra = re.sub(r"\b(discarding|paying|sacrificing|exiling|removing)\b", lambda g: _GERUND[g[1].lower()], m["by"])
                if costs.parse_additional_cost(extra) is None:
                    return None
                extras["extra"] = extra
            if m["tapped"] or m["fin"] or m["gain"]:
                extras["enters"] = {**({"tapped": True} if m["tapped"] else {}), **({"counters": {"finality": 1}} if m["fin"] else {}),
                                    **({"abilities": [m["gain"].replace("~", "this permanent")]} if m["gain"] else {})}  # (the card's own name stands for the one that gains it)
            if m["during"]:
                extras["during"] = "your_turn"
            if what.get("slots"):
                extras["slots"] = True
            if what.get("land_filter"):
                extras["land_filter"] = what["land_filter"]
        if m["rhaste"] or m["rcounter"] or m["rflash"]:  # -- if you do (wave 51D) -- the top of the library alone, a spell cast with the permission (never the land it plays)
            if zone != "library_top" or not what["cast"] or what.get("self") or what.get("slots") or (m["rflash"] is None) != (m["rtype"] == "a creature spell"):
                return None  # ("a creature spell" for haste and the counter, "a spell" for flash)
            if m["rflash"]:
                extras["flash"] = True  # 601.3b: every spell cast with this permission may be cast any time its caster has priority
            else:  # (the rider is for creature spells only: a spell of another kind cast with the same permission gets none, casting.py)
                extras["enters"] = {"only": "Creature", **({"keywords": ["haste"]} if m["rhaste"] else {"counters": {"+1/+1": 1}})}
        if m["lmv"]:  # -- most-played cards (wave 43B) -- 118.9, 119.4: the alternative cost of a spell cast from the top of the library, always paid (X is 0: 107.3b)
            if zone != "library_top" or not what["cast"] or what.get("self"):
                return None
            extras["free"], extras["life_mv"] = True, True
        if zone == "library_top" and not any(_lower_first(x.strip().rstrip(".")) in (TOP_REVEAL, TOP_LOOK) for x in lines):
            # The engine offers a cast from the top of the library only when the player can see
            # that card (401.5; app/rules/view.hints): without a reveal / look line on the same
            # card the permission could never be used — refused rather than claimed
            return None
        if pool is not None:
            if zone != "graveyard" or what.get("self") or what.get("slots") or m["by"] or m["exile"] or m["gain"] or m["fin"] or m["tapped"]:
                return None  # (the pool is read for the plain graveyard permission only)
            extras["put_there"] = "milled" if pool["milled"] else "library" if pool["from"] == "your library" else "not_battlefield"
        return {"kind": "static", "static": "permission", "zone": zone, "once": bool(m["once"]), "flash": False,
                "self": bool(what.get("self")), "play": what["play"], "cast": what["cast"], "filter": what["filter"],
                "effects": [], **extras, **({"exile_gy": "is" if m["exile"] == "an instant or sorcery" else "all"} if m["exile"] else {})}
    m = FLASH.fullmatch(t)
    key = spell_filter(m["sel"]) if m and m["sel"] else None
    if m and not (m["sel"] and key is None):  # (wave 45D: not read here, cast_limits reads "legendary spells and artifact spells")
        return {"kind": "static", "static": "permission", "zone": "any", "once": False, "flash": True, "self": False,
                "play": False, "cast": True, "filter": key, "effects": []}
    if (shown := REVEALED_ZONES.get(t)) is not None:  # -- revealed zones (wave 25A) -- 401.5, 701.20a: every player's top card, or the hands
        return {"kind": "static", "static": "top_reveal", "to": "all", "effects": [], **shown}
    if t == TOP_REVEAL:
        return {"kind": "static", "static": "top_reveal", "to": "all", "effects": []}
    if t == TOP_LOOK:
        return {"kind": "static", "static": "top_reveal", "to": "owner", "effects": []}
    m = FACE_DOWN_LOOK.fullmatch(t)  # -- hidden exile (wave 18A) -- Found Footage, Keeper of the Lens, Lens of Clarity
    if m:
        return {"kind": "static", "static": "top_reveal", "to": "owner" if m["top"] else "none", "face_down": True, "effects": []}
    # -- cast limits (wave 5E) -- "Your opponents can't cast spells during your turn.", "Any player may cast spells as though
    # they had flash.", "You may activate abilities of creatures you control as though those creatures had haste."
    from app.rules import cast_limits

    found_limit = cast_limits.static_definition(text)
    if found_limit is not None and found_limit.get("exiled_with_name") and any("face down" in x.lower() for x in lines):
        return None  # -- linked exile (wave 30H) -- 406.3: a card exiled face down has no name to share (nor may the table learn it from what can't be cast)
    return found_limit


# -- as long as (wave 9B) -- 611.2b: the permission lasts for as long as the card (the object an earlier instruction exiled,
# 400.7h) is still in exile; a card that leaves is a new object. "mana of any type can be spent" (118.14) and "you may spend
# mana as though it were mana of any color" (609.4b) are about the mana spent to cast the spell with this permission.
_RIDER = (r"(?:, and (?:mana of any type can be spent to cast (?P<t>that spell|it|them|those spells)|you may spend mana as though "
          r"it were mana of any (?P<k>color|type) to cast (?P<t2>that spell|it|them|those spells)))")
GRANT_EXILED = re.compile(
    r"^(?:for as long as (?P<d1>it|they|that card|those cards) remains? exiled, )?(?P<who>you|its owner|their owners) may (?P<verb>play|cast) "
    r"(?P<what>that card|those cards|it|them|this card)(?P<free> without paying (?:its|their) mana costs?)?"  # (this card: wave 37A)
    # (-- durations (wave 30M) -- 611.2b: "You may play that card for as long as you control Lightning" (d3): while its source is controlled)
    r"(?: for as long as (?:(?P<d2>it|they|that card|those cards) remains? exiled|(?P<d3>you control ~|~ remains on the battlefield)))?" + _RIDER + r"?$")


def _grant_exiled(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any] | None:
    if sum(map(bool, (m["d1"], m["d2"], m["d3"]))) != 1:
        return None  # (exactly one duration)
    plural = m["what"] in ("those cards", "them")
    # the duration and the rider name the same card(s) the permission is for
    if (m["d1"] or m["d2"]) and (m["d1"] or m["d2"]) not in (("they", "those cards") if plural else ("it", "that card")):
        return None
    rider = m["t"] or m["t2"]
    if rider and rider not in (("them", "those spells") if plural else ("it", "that spell")):
        return None
    spend = "type" if m["t"] else (m["k"] if m["t2"] else "")
    if m["free"] and spend:
        return None  # (a free cast spends no mana: no card words it so)
    owner = m["who"] != "you"  # -- Marvel keywords (wave 25A) -- "For as long as that card remains exiled, its owner may cast it without paying its mana cost."
    if owner and (m["verb"] == "play" or spend or bool(m["d2"]) or m["d3"] or plural != (m["who"] == "their owners")):
        return None  # (read for casting only, the duration first, one rider-less permission)
    until = "permanent" if not m["d3"] else "source_controlled" if m["d3"].startswith("you control") else "source_on_battlefield"
    if m["what"] == "this card" and (owner or spend or m["free"] or not m["d2"] or m["verb"] != "cast"):
        return None  # (wave 37A: only "You may cast this card for as long as it remains exiled.")
    # -- as long as (wave 37A) -- "{2}, Exile this card from your hand: … You may cast this card for as long as it remains exiled." (400.7j: the
    # card the cost exiled; scripts.define reads it only after that cost)
    return [{"do": "grant_play", "who": "cost_exiled_self" if m["what"] == "this card" else "them:card" if plural else "it:card",
             "play": m["verb"] == "play", "cast": True, "until": until, "optional": not owner, **({"free": True} if m["free"] else {}),
             **({"spend": spend} if spend else {}), **({"owner": True} if owner else {})}], None


# -- hidden exile (wave 18A) -- cards exiled face down that "you may look at" (406.3a: a face-down exiled card has no characteristics,
# but the spell or ability that exiled it may let a player look at it and play it): the looker alone sees them (``revealed_to``,
# which ends when the card leaves exile, 400.7). Printed wordings, read as two plain sentences:
#   "You may look at and play those cards for as long as they remain exiled."   (look at + play)
#   "You may play it for as long as it remains exiled. Mana of any type can be spent to cast a spell this way."  (one permission)
LOOK_EXILED = re.compile(r"^you may look at (?P<what>it|that card|those cards|them) for as long as (?:it|they|that card|those cards) "
                         r"remains? exiled$")
_LOOK_AND_PLAY = re.compile(r"You may look at and (?P<v>play|cast) (?P<w>that card|those cards|it|them)(?P<free> without paying "
                            r"(?:its|their) mana costs?)? for as long as (?P<d>it|they) (?P<r>remains?) exiled")
_PLAY_RIDER = re.compile(r"(?P<g>[Yy]ou may (?:play|cast) (?P<w>that card|those cards|it|them)[^.]*?)\. (?:(?P<a>Mana of any type can be "
                         r"spent to cast (?:a spell|spells) this way|If you cast a spell this way, mana of any type can be spent to cast it)"
                         r"|(?P<b>If you cast a spell this way, you may spend mana as though it were mana of any type to cast it))\.")  # (wave 32C: Bloodsoaked Insight, after "Until …, you may play …")


_LIFE_PLAY_RIDER = re.compile(r"(?P<g>[Yy]ou may (?:play|cast) (?:(?:up to )?one of )?(?:that card|those cards|it|them)[^.]*?)\. "
                              r"If you cast a spell this way, pay life equal to its mana value rather than pay(?:ing)? its mana cost\.")


def join_exile_play(body: str) -> str:
    """The wordings above as the sentences the permission grammar reads (permissions.GRANT_EXILED, LOOK_EXILED)."""
    from app.rules import exiled_with

    if exiled_with.linked():  # -- linked casting (wave 30H) -- 607.2a
        body = exiled_with.among(body)
    # (Ugin, the Ineffable: "Exile the top card of your library face down and look at it." — 406.3: whoever looked may go on looking;
    # "put the exiled card into your hand" is the return of that card, 400.3)
    body = re.sub(r"([Ee]xile the top card of your library face down) and look at it\b", r"\1. You may look at it for as long as it remains exiled",
                  body)
    body = re.sub(r"(face down\. )You may look at and play (that card) this turn\b", r"\1You may look at \2 for as long as it remains exiled. You may play \2 this turn",
                  body)  # -- hidden exile (wave 48C) -- Headliner Scarlett: two permissions (the look stays, like Ugin's "and look at it")
    body = re.sub(r"For each card exiled this way, you may (play|cast) that card for as long as it remains exiled, and mana of any type can be "
                  r"spent to cast that spell\.", r"You may \1 those cards for as long as they remain exiled, and mana of any type can be spent to "
                  r"cast those spells.", body)  # (Heartless Conscription)
    body = re.sub(r"You may cast spells from among those cards for as long as they remain exiled, and mana of any type can be spent to cast them\.",
                  "You may cast those cards for as long as they remain exiled, and mana of any type can be spent to cast those spells.", body)  # (Shadow of the Enemy)
    body = re.sub(r"\b([Pp])ut the exiled card into your hand\b", lambda m: ("R" if m[1] == "P" else "r") + "eturn the exiled card to your hand", body)
    body = re.sub(r"Look at (target player's hand), (the top card of that player's library), and any face-down creatures they control\.",
                  r"Look at \1. Look at \2. Look at all face-down creatures that player controls.", body)  # (Spy Network: 701.20e each)
    body = re.sub(r"Reveal (target face-down permanent)\. If it's a creature card, you may turn it face up\.",
                  r"Reveal \1 and you may turn it face up if it's a creature card.", body)  # (Hauntwoods Shrieker)
    body = re.sub(r"(cloak those cards)\. They enter tapped\.", r"\1 tapped.", body)  # (Become Anonymous)
    body = re.sub(r"\b([Ee]xile it) face down\. (It becomes foretold\.)", r"\1. \2", body)  # (The Foretold Soldier: the foretell zone is face down)
    body = re.sub(r"\bIt becomes foretold\. Its foretell cost is its mana cost reduced by (\{\d+\})\.",
                  r"It becomes foretold with a foretell cost of its mana cost reduced by \1.", body)  # (Ethereal Valkyrie: 702.143d)
    body = re.sub(r"([Yy]ou may (?:look at and )?(?:play|cast) )the exiled (card|cards)\b",  # (-- hideaway (wave 29D) -- also mid-sentence: "Then if …, you may play the exiled card")
                  lambda m: m[1] + ("that card" if m[2] == "card" else "those cards"), body)
    # -- end of next turn (wave 32C) -- "Until the end of your next turn, you may play those cards. If this spell was cast from a graveyard, you may play
    # cards this way without paying their mana costs." (Ignite the Future): "this way" is the same permission's duration, said again
    body = re.sub(r"(Until [a-z ]+?), you may (play|cast) those cards\. (If [^,.]+), you may \2 cards this way without paying their mana costs\.",
                  lambda m: f"{m[1]}, you may {m[2]} those cards. {m[3]}, {m[1][0].lower()}{m[1][1:]}, you may {m[2]} those cards without paying their mana costs.", body)
    body = _LOOK_AND_PLAY.sub(lambda m: f"You may look at {m['w']} for as long as {m['d']} {m['r']} exiled. You may {m['v']} {m['w']}"
                              f"{m['free'] or ''} for as long as {m['d']} {m['r']} exiled", body)

    def rider(m: re.Match[str]) -> str:
        plural = m["w"] in ("those cards", "them")
        spell = "those spells" if plural else "that spell"
        tail = f"mana of any type can be spent to cast {spell}" if m["a"] else \
            f"you may spend mana as though it were mana of any type to cast {spell}"
        return f"{m['g']}, and {tail}."

    body = _LIFE_PLAY_RIDER.sub(lambda m: f"{m['g']}, paying life equal to its mana value rather than paying its mana cost.", body)
    return _PLAY_RIDER.sub(rider, body)


def parse_clause(text: str) -> tuple[list[dict[str, Any]], Any] | None:
    """An effect sentence of the permission grammar (see ``scripts._one_clause``), or None.
    ("Exile the top card of your library" itself is the library grammar's: app/rules/language.py.)"""
    if (named := re.fullmatch(rf"spells with the chosen name cost {_N} (?P<dir>less|more) to cast this turn", text, re.IGNORECASE)) is not None:
        # -- chosen filters (wave 53B) -- "Choose a card name. Spells with the chosen name cost {1} less to cast this turn." (Cheering Fanatic): everybody's spells (601.2f,
        # 611.2a), the name just chosen bound into the filter (chosen.bind_effects)
        sel = selectors.parse("spells with the chosen name")
        if sel is None:
            return None
        return [{"do": "cost_modifier", "delta": int(named["n"]) * (-1 if named["dir"] == "less" else 1), "filter": sel.key(), "until": "end_of_turn", "any": True}], None
    if (next_exile := re.fullmatch(r"you may (?P<verb>play|cast) (?P<what>it|that card) until you exile another card with ~", text)) is not None:
        return [{"do": "grant_play", "who": "it:card", "play": next_exile["verb"] == "play", "cast": True,
                 "until": "permanent", "from_exile": True, "stop_on_linked_exile": True, "optional": True}], None
    from app.rules import total_mv_casts

    if (budget := total_mv_casts.clause(text)) is not None:
        return budget, None
    m = STORED_COST.fullmatch(text)
    if m and bool(m["until"]) != bool(m["this_turn"]):
        key = spell_filter(m["sel"])
        if key is None:
            return None
        return [{"do": "cost_modifier", "delta": int(m["n"]) * (-1 if m["dir"] == "less" else 1), "filter": key,
                 "until": "next_turn" if m["until"] else "end_of_turn"}], None
    if (x := STORED_COST_X.fullmatch(text)) is not None:
        from app.rules import values

        key, value = spell_filter(f"{x['sel']} or {x['sel2']}"), values.parse_count(x["v"])
        if key is None or not isinstance(value, dict) or "turn_history" not in value:
            return None
        return [{"do": "cost_modifier", "delta": value, "dir": -1, "filter": key, "until": "end_of_turn"}], None
    m = LOOK_EXILED.fullmatch(text)  # -- hidden exile (wave 18A) --
    if m:
        return [{"do": "look_exiled", "who": "them:card" if m["what"] in ("those cards", "them") else "it:card", "optional": True}], None
    if CAST_IT_FROM_GRAVEYARD.fullmatch(text):
        return [{"do": "free_cast", "zone": "that", "who": "ref:event", "filter": None, "optional": True, "mv": None, "n": 1, "paid": True}], None
    m = FREE_COPY.fullmatch(text)  # -- cast a copy (wave 13C) --
    if m:
        many = m["w"] != "the copy"
        return [{"do": "free_cast", "zone": "that", "who": "them:copy" if many else "it:copy", "filter": None, "optional": True,
                 "mv": None, "n": 1, **({"all": True} if many else {}), **({} if m["free"] else {"paid": True})}], None
    among = _free_among(text)  # -- refused look/cast-free (wave 3R5) --
    if among is not None:
        return among, None
    if (granted := AMONG_GRANT.fullmatch(text)) is not None:  # -- free cast (wave 40D) --
        if bool(granted["one"]) == (granted["sp"] == "spells"):
            return None
        key = spell_filter(granted["sel"]) if granted["sel"] else None
        if granted["sel"] and key is None:
            return None
        spend = "type" if granted["spend"] else granted["kind"]
        if granted["free"] and (spend or (granted["poss"] == "its") != bool(granted["one"])):
            return None
        until = {"until the end of your next turn": "end_of_next_turn", "until your next end step": "next_end_step",
                 "until your next turn": "next_turn", "until the beginning of your next upkeep": "next_turn"}.get(granted["until"], "end_of_turn")
        # 601.3 / 609.4b: a spell-only permission never grants a land play. An
        # indefinite singular permits one spell total across the entire set.
        return [{"do": "grant_play", "who": "them:card", "play": False, "cast": True, "until": until, "optional": True,
                 **({"filter": key} if key else {}), **({"free": True} if granted["free"] else {}),
                 **({"limit": 1} if granted["one"] else {}), **({"spend": spend} if spend else {})}], None
    target = _free_target(text)
    if target is not None:
        return target
    conditional = _free_if(text) or _free_gy(text)
    if conditional is not None:
        return conditional, None
    m = FREE_HAND.fullmatch(text)  # -- cast without paying (wave 3C) --
    if m:
        if bool(m["h1"]) == bool(m["h2"]):
            return None
        key = spell_filter(m["sel"]) if m["sel"] else None
        if m["sel"] and key is None:
            return None
        try:  # -- refused look/cast-free (wave 3R5) -- "less than or equal to that damage / ~'s power …"
            mv = free_mv(m["n"], m["x2"])
        except ValueError:
            return None
        e: dict[str, Any] = {"do": "free_cast", "zone": "hand", "filter": key, "optional": True, "mv": mv}
        if m["rel"]:  # (-- if you do (wave 40A) -- the trigger's spell: scripts._event_refs_ok accepts it only on a cast trigger)
            if mv is not None:
                return None
            e["mv" if m["rel"] == "equal or lesser" else "mv_lt"] = {"mana_value": "event"}
            if m["share"]:
                e["shares_type"] = "event"
        return [e], None
    m = PLAY_OR_CAST_TOP.fullmatch(text)  # -- play now (wave 28A) --
    if m:
        try:
            mv = free_mv(m["n"], m["v"])
        except ValueError:
            return None
        return [{"do": "free_cast", "zone": "that", "who": "it:card", "filter": None, "mv": mv, "optional": True, "play": True}], None
    # -- refused grants/replacements (wave 3R2) -- the same permission with its duration at the end ("You may play it
    # until the end of your next turn.": 611.2a, the duration is the one stated, wherever the sentence states it) and
    # "them" for "those cards" ("You may play them until the end of your next turn.")
    text = re.sub(r"^((?:until [a-z ]+, )?you may (?:play|cast)) (?:them|cards exiled this way|the exiled cards)\b", r"\1 those cards", text)  # (wave 32C: Escape to the Wilds)
    trailing = _TRAILING_UNTIL.fullmatch(text)
    if trailing:
        text = f"{trailing['until']}, {trailing['rest']}"
    # -- end refused grants/replacements (wave 3R2) --
    # -- as long as (wave 9B) -- "You may cast that card for as long as it remains exiled, and mana of any type can be spent
    # to cast that spell." (Gonti, Hostage Taker, Thief of Sanity)
    m = GRANT_EXILED.fullmatch(text)
    if m and (m["d1"] or m["d2"] or m["d3"]):
        return _grant_exiled(m)
    m = GRANT_THAT.fullmatch(text)
    if m and m["watt"]:  # -- trigger other (wave 51E) -- "During any turn you attacked with a token, you may play that card." (Neyali, Neriv, Goblin Researcher): it stays exiled with a
        # permission that works in the turns you attacked with such a creature (611.2a: no end but the card leaving exile); the usual timing rules still apply
        when = _attacked_when(m["watt"])
        if when is None or m["upto"] or m["from_ex"] or m["this_turn"] or m["free"] or m["spend"] or m["spend2"] or m["life"]:
            return None
        return [{"do": "grant_play", "who": "them:card" if m["what"] == "those cards" else "it:card", "play": m["verb"] == "play", "cast": True,
                 "until": "permanent", "optional": True, "when": when}], None
    if m and m["life"] and not (m["until"] or m["this_turn"]):
        return None  # A required life-cost grant here must have a stated duration.
    if m and m["upto"] and m["what"] != "those cards":
        return None
    if m and m["from_ex"] and bool(m["until"]) == bool(m["this_turn"]):
        return None  # -- free cast (wave 40D) -- "play that card from exile this turn" (Norin) is a permission with a stated duration only
    if m and m["free"] and not (m["until"] or m["this_turn"]):
        if m["what"] == "those cards":
            return None  # (several cards at once: not modelled)
        # -- play now (wave 28A) -- "You may play that card without paying its mana cost." as this resolves (608.2g): a land too, with a land play left
        return [{"do": "free_cast", "zone": "that", "who": "it:card", "filter": None, "mv": None, "optional": True,
                 **({"play": True} if m["verb"] == "play" else {})}], None
    if m:
        spend_kind = "type" if m["spend"] else (m["k2"] if m["spend2"] else "")
        if not (m["until"] or m["this_turn"]) and m["what"] != "those cards" and not spend_kind:
            # -- if you do (wave 25C) -- a bare "You may cast that card." (Chandra, Torch of Defiance): cast as this resolves (608.2g), its mana cost
            # paid — the paid free cast of the copy wording; "If you don't, …" after it reads whether a spell was cast
            # (-- play now (wave 28A) -- "You may play that card.": the same, or a land played with a land play left)
            return [{"do": "free_cast", "zone": "that", "who": "it:card", "filter": None, "mv": None, "optional": True, "paid": True,
                     **({"play": True} if m["verb"] == "play" else {})}], None
        if (m["until"] and m["this_turn"]) or not (m["until"] or m["this_turn"]):
            return None  # (a bare "you may play that card" / several cards: cast as this resolves, not modelled)
        life_mv = bool(m["life"])
        if life_mv and (m["free"] or spend_kind):
            return None  # One required alternative cost; no competing mana-spending rider.
        free = bool(m["free"]) or life_mv  # (wave 3C) "... without paying its mana cost" (118.9)
        if spend_kind and (free or (m["what"] == "those cards") != ("those spells" in (m["spend"] or m["spend2"]))):
            return None  # (-- if you do (wave 25C) -- 118.14: mana is spent only to cast, never for a free cast)
        until = {"until the end of your next turn": "end_of_next_turn", "until your next end step": "next_end_step",
                 "until your next turn": "next_turn", "until the beginning of your next upkeep": "next_turn"}.get(m["until"], "end_of_turn")
        # "who": a pronoun for scripts.resolve_it — the object(s) the preceding instruction moved
        # ("that card": a card — never a token the same sentence created, 111.1: scripts.resolve_it)
        if m["upto"] and ((free and not life_mv) or spend_kind or m["from_ex"]):
            return None  # (-- cost reductions paid with objects (wave 47C) -- "You may play up to two of those cards until the end of your next turn." (March of Reckless Joy) only)
        return [{"do": "grant_play", "who": "them:card" if m["what"] == "those cards" else "it:card", "play": m["verb"] == "play",
                 "cast": True, "until": until, "optional": True, **({"free": True} if free else {}), **({"life_mv": True} if life_mv else {}),
                 **({"limit": {"one": 1, "two": 2, "three": 3, "four": 4}[m["upn"] or m["one"]]} if m["upto"] else {}),
                 **({"spend": spend_kind} if spend_kind else {}), **({"from_exile": True} if m["from_ex"] else {})}], None
    if text.lower() == (
            "until end of turn, you may cast creature spells from your graveyard by foraging "
            "in addition to paying their other costs. if you cast a spell this way, "
            "that creature enters with a finality counter on it"):
        return [{"do": "grant_play", "zone": "graveyard", "zone_owner": "you",
                 "play": False, "cast": True, "until": "end_of_turn", "optional": True,
                 "filter": spell_filter("creature"), "extra": "forage",
                 "enters": {"counters": {"finality": 1}}}], None
    if text.lower() == ("you may cast a creature spell from your graveyard this turn. if you do, it enters with a finality counter on it "
                        "and is a vampire in addition to its other types"):  # -- Tarrian's Journal (wave 110C) -- one creature spell; 122.6, 205.1b
        return [{"do": "grant_play", "zone": "graveyard", "zone_owner": "you", "play": False, "cast": True, "until": "end_of_turn", "optional": True,
                 "once": True, "filter": spell_filter("creature"), "enters": {"counters": {"finality": 1}, "subtypes": ["Vampire"]}}], None
    m = GRANT_ZONE.fullmatch(text)
    if m:
        if m["until"] and m["this_turn"]:
            return None
        if m["sel"] and bool(m["a"]) == (m["sp"] == "spells"):
            return None  # ("a creature spells": not English)
        what = {"play": False, "cast": True, "filter": spell_filter(m["sel"])} if m["sel"] else _permission_what(m["what"], None, None)
        if what is None or (m["sel"] and what["filter"] is None):
            return None
        return [{"do": "grant_play", "zone": "graveyard", "zone_owner": "any" if m["owner"] == "any" else "you",
                 "play": what["play"], "cast": what["cast"], "until": "end_of_turn",
                 "optional": True, **({"filter": what["filter"]} if m["sel"] else {}), **({"once": True} if m["a"] else {})}], None
    return None


# -- what the table grants -------------------------------------------------------------------------
@dataclass(frozen=True)
class Grant:
    """One way a player may cast (or play) a card right now."""

    how: str  # "hand" | "command" | "flashback" | "permission"
    label: str = ""
    zone_ok: bool = True  # it allows the cast from where the card is (a flash-only grant doesn't)
    free: bool = False  # cast without paying its mana cost (118.9)
    life_mv: bool = False  # -- casting costs (wave 22F) -- ... paying life equal to its mana value instead (an alternative cost, 118.9; 119.4)
    use_trigger: PermissionUseTrigger | None = None
    spell_keywords: tuple[str, ...] = ()  # Abilities of a spell cast using this selected authority.
    flash: bool = False  # as though it had flash (601.3b)
    flash_requires_free: bool = False  # This timing authority applies only to its zero-mana casting option.
    permission: str | None = None  # the stored Permission's id
    spend: str = ""  # -- as long as (wave 9B) -- "" | "type" | "color": how mana may be spent casting with it (118.14, 609.4b)
    once_key: str | None = None  # a static "once during each of your turns" ability's key
    sorcery: bool = False  # -- keywords (wave 15E) -- plot 702.170d: only in your main phase with an empty stack, whatever it is
    generic_extra: int = 0  # Additional generic mana charged by this permission.
    extra: str = ""  # -- cost alt (wave 16F) -- an additional cost the permission names ("discard a card"), paid with the rest (601.2b)
    graveyard_destination: str = ""  # Selected cast authority: library_bottom replaces this spell going to any graveyard.
    exile_gy: str = ""  # -- cast from graveyard (wave 19C) -- 614.1a: "all" | "is" (instants and sorceries only): "If a spell cast this way would be put into your graveyard, exile it instead"
    exile: bool = False  # -- casting extras (wave 18E) -- jump-start 702.133a: exile the card instead of putting it anywhere else as it leaves the stack
    alt_mana: str = ""  # -- trigger other (wave 25B) -- airbend 701.65a: an alternative cost the permission requires ("{2}")
    slot: str = ""  # -- cast permissions (wave 30Q) -- the permanent type this use of "each permanent type" is for (Muldrotha); its ``once_key`` is that type's
    enters: dict[str, Any] | None = None  # -- cast permissions (wave 30Q) -- "If you cast a spell this way, that artifact enters tapped / with a finality counter" / "it gains …"
    choice_key: str = ""  # Stable identity for choosing between costs, including unlimited life alternatives.
    use: str = ""  # -- cast permissions (wave 32D) -- what this way uses up (a once-a-turn permission's key, Muldrotha's type: the action's ``via``); "" = unlimited
    among: tuple[Grant, ...] = ()  # -- cast permissions (wave 32D) -- on the way taken by default: one way per different use up, when there is more than one (``with_choices``)


def life_cost(grant: Grant | None, ch: Characteristics) -> costs.AbilityCost | None:
    """The alternative life payment uses the spell being cast, including its chosen face (118.9c)."""
    mv = int(ch.mana_value)
    if grant is None or not grant.life_mv or not mv:
        return None  # 118.3b / 119.4b: paying zero life is always legal.
    return costs.AbilityCost(components=(costs.CostComponent(costs.PAY_LIFE, amount=mv, text=f"Pay {mv} life"),), life=mv)


def _view(state: GameState, player: str, info: CardInfo) -> Plan:
    from app.rules.plan import Plan

    return Plan.view(state, player, info)


def spell_matches(state: GameState, player: str, card: CardInstance, ch: Characteristics, key: str, info: CardInfo,
                  source: str | None = None) -> bool:
    """Would the spell this card becomes match the selector ("creature spells", "red spells")? (``source``: the
    permanent whose "chosen type" the selector reads, wave 5I)"""
    probe = card.model_copy(update={"zone": STACK, "controller": player, **({"face_down": True} if ch.face_down else {})})  # (wave 46A: a spell being cast face down, 708.4)
    return selectors.matches(_view(state, player, info), selectors.from_key(key), probe, ch, player, source)


def abilities_uncounterable(state: GameState, info: CardInfo) -> bool:
    """-- cant restrictions (wave 46A) -- does a static on the table say abilities can't be countered (Spider-Punk: "Spells and abilities can't be countered", 101.2)?"""
    return any(d.get("abilities") for _, _, d in _table_statics(state, info, {"spells_uncounterable"}))


def spell_uncounterable(state: GameState, info: CardInfo, card: CardInstance, ch: Characteristics) -> bool:
    """-- small wordings (wave 11E) -- does a static on the table say this spell, controlled by its caster, can't be
    countered (101.2, 701.6)?"""
    from app.rules import conditions

    for d in _definitions(ch).values():
        if d.get("static") == "self_uncounterable" and state.rules is not None:
            ctx = {"controller": card.controller, "source_card": card.id, "source_object": state.rules.object_id(card.id),
                   "x": card.stack_info.x if card.stack_info is not None else None}  # (-- multi (wave 100M) -- Banefire: the X chosen as it was cast, 107.3)
            if conditions.holds(_view(state, card.controller, info), ctx, d["cond"]):
                return True
    turn = state.turn.number  # -- most-played cards (wave 43B) -- "Spells you control can't be countered this turn." (prohibitions.uncounterable_turn)
    if state.rules is not None and any(x.get("what") == "uncounterable" and x["turn"] == turn and x["player"] == card.controller
                                       and (x["oid"] == state.rules.object_id(card.id) if x.get("oid") else
                                            (not x.get("filter") or spell_matches(state, card.controller, card, ch, x["filter"], info)))
                                       for x in state.rules.results):
        return True
    return any((d.get("any_player") or src.controller == card.controller) and (not d["filter"] or spell_matches(state, card.controller, card, ch, d["filter"], info))
               for src, _, d in _table_statics(state, info, {"spells_uncounterable"})) \
        or any(d.get("uncounterable") and src.controller == card.controller and (not d["filter"] or spell_matches(state, card.controller, card, ch, d["filter"], info))
               for src, _, d in _table_statics(state, info, {"cost_modifier"}))  # (-- cost changers (wave 44D) -- Thryx)


def _table_statics(state: GameState, info: CardInfo, kinds: set[str]) -> list[tuple[CardInstance, int, Definition]]:
    """(permanent, ability index, definition) for the static abilities of the named kinds on the
    battlefield (manual cards and face-down permanents excepted)."""
    from app.rules import read_pass

    # -- hints speed (wave 29A) -- a pass that only reads the table derives each permanent once, not once per call and kind
    found = read_pass.once(state, info, "table_statics", lambda: _all_table_statics(state, info))
    return [t for t in found if t[2].get("static") in kinds]


def _all_table_statics(state: GameState, info: CardInfo) -> list[tuple[CardInstance, int, Definition]]:
    """``_table_statics`` for every kind: the static abilities of the permanents (and eminence cards), in table order."""
    from app.rules import scripts
    from app.rules.layers import derive
    from app.rules.plan import live_players

    r = state.rules
    if r is None:
        return []
    live = set(live_players(state))
    out = []
    from app.rules import designations, triggers

    for card in state.cards.values():
        # -- trigger other (wave 25B) -- eminence: a static that names "in the command zone or on the battlefield" works from the command zone (113.6b)
        eminent = card.zone.endswith(":command") and not designations.emblem_card(card)
        emblem = designations.emblem_card(card)
        if not (card.zone.endswith(":battlefield") or eminent or emblem) or card.face_down or card.controller not in live \
                or r.card_mode(card.id) == "manual":
            continue
        ch = derive(state, card, chars.of(card, info), info)
        for index, d in scripts.definitions(ch).items():
            if d.get("kind") == "static":
                if emblem and d.get('static') not in ('permission', 'cost_modifier', 'untap_limit'):  # -- planeswalker statics (wave 110A) -- Dovin Baan's emblem
                    continue
                if eminent and (d.get("change") or {}).get("cond") != triggers.COMMAND_OR_BATTLEFIELD:
                    continue
                out.append((card, index, d))
    return out


def _card_zone(state: GameState, player: str, card: CardInstance) -> str | None:
    """Which permission zone the card is in for ``player``: their graveyard, exile (their own
    card), hand, or the top of their library."""
    if card.zone == zone_key(player, "graveyard") and card.owner == player:
        return "graveyard"
    if card.zone == zone_key(player, "hand"):
        return "hand"
    if card.zone.endswith(":exile") and card.owner == player:
        return "exile"
    if card.zone == zone_key(player, "library"):
        library = state.zones.get(card.zone) or []
        return "library_top" if library and library[0] == card.id else None
    return None


def _wants(p: Permission, verb: str) -> bool:
    return p.play if verb == "play" else p.cast


def grants(state: GameState, player: str, card: CardInstance, ch: Characteristics, info: CardInfo, *,
           verb: str = "cast") -> list[Grant]:
    """Every permission that applies to ``player`` casting (``verb`` "cast") or playing as a land
    ("play") this card from where it is now: stored permissions first, then static abilities of
    permanents they control and the card's own "you may cast this card from your graveyard"."""
    r = state.rules
    if r is None or not ch.types:
        return []
    turn = state.turn.number
    where = _card_zone(state, player, card)
    oid = r.object_id(card.id)
    from app.rules import conditional_free_casts68, permission_use_triggers43

    out: list[Grant] = []
    for p in r.permissions:
        if p.player != player or not _wants(p, verb) or (p.once and p.used_turn == turn) or (p.after_turn and turn <= p.after_turn):
            continue
        if p.until in SOURCE_UNTIL and not source_holds(state, p):
            continue  # (-- durations (wave 30M) -- 611.2b: over, whenever the table was last looked at)
        if p.when is not None:  # -- trigger other (wave 51E) -- "During any turn you attacked with …": read now; ``source`` is the object the permission came from ("this creature")
            from app.rules import conditions
            from app.rules.layers import _view as layer_view

            if not conditions.holds(layer_view(state, info), {"controller": player, "source_object": p.source, "source_card": card.id}, p.when):
                continue
        if p.object_id is not None:
            if p.object_id != oid or (p.top110j and where != "library_top"):  # (-- wave 110J -- Temporal Aperture: only while it is the top card)
                continue  # a new object since (400.7): the permission was for the one it was
        elif p.zone != "any" and p.zone != where and not (
                p.zone in ("graveyard", "exile") and p.zone_owner == "any" and card.zone.endswith(":" + p.zone)):
            continue
        if p.card_filter:
            from app.rules import selectors

            if not selectors.matches(_view(state, player, info), selectors.from_key(p.card_filter), card, ch, player):
                continue
        if p.filter and verb == "cast" and not spell_matches(state, player, card, ch, p.filter, info):
            continue
        if p.nth is not None and cost_changes.casts_so_far(state, info, player, p.filter) != p.nth:
            continue  # -- chosen filters (wave 53B) -- "the next spell of the kind": a spell of the kind was cast since (601.2i)
        zone_ok = p.object_id is not None or p.zone != "any"  # (a flash-only permission grants no zone)
        out.append(Grant("permission", p.label, zone_ok=zone_ok, free=p.free, life_mv=p.life_mv, spell_keywords=tuple(p.spell_keywords), flash=p.flash, permission=p.id, spend=p.spend, use_trigger=p.use_trigger, graveyard_destination=p.graveyard_destination,
                         choice_key=p.id, generic_extra=p.generic_extra,
                         sorcery=p.sorcery, alt_mana=p.alt_mana, enters=p.enters, extra=p.extra,  # (wave 51D: "If you do, it enters tapped", Jorn)
                         exile_gy=p.exile_gy if not p.exile_own or card.owner == player else ""))  # (wave 25C)
    if verb == "cast" and where in ("graveyard", "exile") and card.owner == player and not card.face_down:
        from app.rules import layers

        self_ch = layers.derive(state, card, ch, info) if layers.affecting(state, card) else ch
        for index, d in _definitions(self_ch).items():  # the card's own ability, functioning in the graveyard (113.6) / exile (wave 20D)
            if d.get("static") == "permission" and d.get("self") and where in d.get("zones", [d["zone"]]):
                if d.get('required_mutate75') or d.get('required_keyword79'):
                    continue  # This authority exists only for a selected native mutate alternative.
                key = f"{card.id}:permission:{index}"
                if d["once"] and r.once_per_turn.get(key) == turn:
                    continue
                if d.get("while") is not None and not _while_holds(state, info, player, card, d["while"]):
                    continue  # -- conditional statics (wave 4B) -- "as long as you control a Zombie"
                out.append(Grant("permission", f"{ch.name}: cast it from {'exile' if where == 'exile' else 'your graveyard'}", once_key=key if d["once"] else None,
                                 extra=d.get("extra") or "", exile=bool(d.get("exile")), choice_key=key,
                                 exile_gy=d.get("exile_gy", ""),
                                 alt_mana=d.get("alt_mana") or "", enters=d.get("enters"),
                                 generic_extra=sum(1 for other in state.cards.values()
                                                   if other.id != card.id and other.zone == zone_key(player, "graveyard")
                                                   and "Creature" in _view(state, player, info).ch(other).types)
                                 if d.get("other_creature_tax") else 0))
    if verb == "cast" and where == "graveyard" and card.owner == player and not card.face_down:  # -- static_other (wave 44C) -- 702.133a: jump-start a static gave it (Niv-Mizzet, Supreme)
        from app.rules import zone_grants

        if zone_grants.jump_start(state, player, card, ch, info):
            out.append(Grant("permission", f"{ch.name}: cast it from your graveyard (jump-start)", extra="discard a card", exile=True))
    if verb == "play" and where == "graveyard" and card.owner == player:  # -- Marvel keywords (wave 25A) -- 702.187c: a bare "Mayhem"
        from app.rules import mayhem

        if mayhem.plays_land(state, player, card, ch):
            out.append(Grant("permission", f"{ch.name}: play it from your graveyard (mayhem)"))
    if verb == "cast" and where == "hand":  # -- cast without paying (wave 3C) -- the card's own "cast this spell without paying"
        for d in _definitions(ch).values():
            if d.get("static") == "permission" and d.get("self") and d.get("free") and d["zone"] == "hand" \
                    and (d.get("cond") != "commander" or _controls_commander(state, player)):
                if not conditional_free_casts68.eligible(state, info, player, card, ch, d):
                    continue
                if d.get("while") is not None and not _while_holds(state, info, player, card, d["while"]):
                    continue
                out.append(Grant("permission", f"{ch.name}: cast it without paying its mana cost", free=True, flash=bool(d.get("flash"))))
    if verb == "cast":  # -- cast limits (wave 5E) -- 601.3d: "You may cast this spell as though it had flash if …"
        from app.rules import cast_limits

        if (label := cast_limits.self_flash(state, player, card, ch, info)) is not None:
            out.append(Grant("permission", label, zone_ok=False, flash=True))
    # (-- spell grants (wave 30T) -- a cost changer that also gives flash carries it as "flash_perm": Radagast of Rhosgobel)
    for src, index, d in [*_table_statics(state, info, {"permission"}),
                          *((s, i, x["flash_perm"]) for s, i, x in _table_statics(state, info, {"cost_modifier"}) if x.get("flash_perm"))]:
        # -- cast limits (wave 5E) -- "Any player may cast …" / "During each opponent's end step, you may cast …"
        if (src.controller != player and not d.get("any_player")) or d.get("self") or not d[verb]:
            continue
        if d.get("during"):
            from app.rules import cast_limits

            if not cast_limits.permission_during_ok(state, d, player):
                continue
        if d.get("own") and card.owner != player:  # ("Creature cards you own …")
            continue
        if d.get("linked"):  # -- resolution memory (wave 22D) -- only a card still the object this permanent's ability exiled (400.7, 607.2a)
            from app.rules import exiled_with

            linked_ctx: dict[str, Any] = {"source_object": r.object_id(src.id)}
            for linked_effect in d.get("effects") or []:
                if linked_effect.get("do") == "borrowed_link_scope":
                    linked_ctx["borrowed_link_scope"] = linked_effect["scope"]
            linked_scope = exiled_with.link_key(linked_ctx)
            if not card.zone.endswith(":exile") or (card.face_down and not d.get("linked_face_down")) \
                    or oid not in r.exiled_with.get(linked_scope, []):
                continue
            if d.get('linked_current_turn71') and r.linked_exile_turns71.get(linked_scope, {}).get(oid) != turn:
                continue
            if not conditional_free_casts68.eligible(state, info, player, card, ch, d):
                continue
            if d.get("filter") and not spell_matches(state, player, card, ch, d["filter"], info, source=src.id):
                continue
            if d.get("if") is not None and not _linked_if(state, info, player, src, d["if"]):
                continue
            key = f"{r.object_id(src.id)}:permission:{index}:{player}" if d.get("once_per_player") else f"{src.id}:permission:{index}"  # -- linked permissions (wave 30H) -- "You can't cast more than one spell this way each turn."
            if d.get('once_per_object71'):
                key = f"{r.object_id(src.id)}:permission:{index}"
            if d["once"] and r.once_per_turn.get(key) == turn:
                continue
            out.append(Grant("permission", src.name, zone_ok=True, flash=bool(d.get("flash")), free=bool(d.get("free")), life_mv=bool(d.get("life_mv")),
                             once_key=key if d["once"] else None, choice_key=key, enters=d.get("enters"), spend=d.get("spend", ""), extra=d.get("extra", ""),
                             use_trigger=permission_use_triggers43.static_receipt(state, src, index, d.get("use_trigger"))))
            continue
        if not conditional_free_casts68.eligible(state, info, player, card, ch, d):
            continue
        permission_where = 'exile' if d.get('exile_counter') and card.zone.endswith(':exile') else where
        if d.get('zone_owner') == 'any' and d['zone'] == 'graveyard' and card.zone.endswith(':graveyard'):
            permission_where = 'graveyard'
        if d["zone"] != "any" and permission_where not in d.get("zones", [d["zone"]]):
            continue
        if d.get('foreign') and card.owner == player:
            continue
        if d.get('exile_counter') and (permission_where != 'exile' or card.counters.get(d['exile_counter'], 0) <= 0):
            continue
        if d.get("put_there") and not selectors.put_there_state(state, card, d["put_there"]):
            continue  # -- free cast (wave 40D) -- only a card that is the object put into the graveyard this turn from there (400.7)
        # -- spell grants (wave 30T) -- 611.3a: "As long as ~ is tapped, you may cast spells as though they had flash" is read now, as its source's controller;
        # "the first creature spell you cast each turn" (601.2i): none of that kind cast earlier this turn, whenever the source arrived
        if d.get("if") is not None and not _linked_if(state, info, src.controller, src, d["if"]):
            continue
        if d.get("first") and not cost_changes.first_ok(state, info, player, d["filter"]):
            continue
        if d.get('linked_type_union') and verb == 'cast':
            from app.rules import linked_aggregates

            linked_view = _view(state, player, info)
            linked_ctx = linked_aggregates.source_context(linked_view, src, d)
            if not set(ch.types) & linked_aggregates.aggregate(linked_view, linked_ctx, {'projection': 'card_types'}):
                continue
        if d["filter"] and verb == "cast" and not spell_matches(state, player, card, ch, d["filter"], info, source=src.id):  # (wave 30Q: "quest counters on ~")
            continue
        # -- top of library (wave 5I) -- "artifact spells and colorless spells", the chosen type, historic lands
        from app.rules import top_library

        if not top_library.static_ok(state, player, card, ch, info, d, src, verb):
            continue
        key = f"{r.object_id(src.id)}:permission:{index}"  # (-- review 30c -- 400.7: a new Muldrotha / Lurrus has new uses, the rulings 2020-11-10)
        if d.get('separate_verb71'):
            key += ':' + verb
        if d["once"] and (r.once_per_turn.get(key) == turn or (state.turn.active_player != player and not d.get("once_any"))):
            continue  # "once during each of your turns" ("once each turn": any turn, wave 5I)
        # -- cast permissions (wave 30Q) -- Muldrotha: a use for each permanent type, a card of several types counting as one of them as it is played or
        # cast ("choose one as you play it"); one grant per type still unused, the player picks which (cast_grant ``slot``)
        slots = [t for t in SLOT_TYPES if (t == "Land") == (verb == "play") and t in ch.types and r.once_per_turn.get(f"{key}:{t}") != turn] \
            if d.get("slots") else [""]
        out += [Grant("permission", src.name, zone_ok=d["zone"] != "any", flash=d["flash"], flash_requires_free=bool(d.get("flash_requires_free")), free=bool(d.get("free")), life_mv=bool(d.get("life_mv")),
                      once_key=f"{key}:{slot}" if slot else key if d["once"] else None, choice_key=f"{key}:{slot}" if slot else key, extra=d.get("extra") or "", exile_gy=d.get("exile_gy", ""),
                      slot=slot, enters=d.get("enters"), spend=d.get("spend", ""),
                      use_trigger=permission_use_triggers43.static_receipt(state, src, index, d.get("use_trigger"))) for slot in slots]
    # -- top of library (wave 5I) -- the player picks the permission they use (601.3): a once-each-turn one is offered
    # last, so a cast another permission also allows doesn't use it up
    # (-- review 30c -- a stored one-spell permission too: Chainer's is kept while Liliana's covers the cast, the Chainer ruling 2019-08-23)
    once = {p.id for p in r.permissions if p.once}
    out = [replace(g, use=g.once_key or ((g.permission or "") if g.permission in once else "")) for g in out]  # (-- wave 32D -- what each use of it uses up)
    out.sort(key=lambda g: bool(g.use))
    return out


def with_choices(best: Grant, ways: list[Grant], *, compare_costs: bool = False) -> Grant:
    """-- cast permissions (wave 32D) -- 601.2: the player announces the permission a cast or play uses (the Muldrotha ruling 2020-11-10: "you choose which
    permission you're using"). ``best`` is the way taken by default; when it is a limited one (a once-a-turn permission, a Muldrotha type) and ``ways`` holds
    others that use up something else, it carries them in ``among`` and the caster is asked. An unlimited way as the default uses nothing up: no question."""
    # Distinct life alternatives remain a real choice even when one permission
    # is unlimited. Keeping the selection identity separate avoids spending a use
    # merely to name an unlimited alternative (e.g. Bolas's Citadel).
    if (compare_costs and len({g.life_mv for g in ways}) > 1) or len({g.graveyard_destination for g in ways}) > 1 or len({g.spell_keywords for g in ways}) > 1 or len({g.use_trigger.model_dump_json() if g.use_trigger else "" for g in ways}) > 1:
        choices = {g.choice_key or g.use: g for g in ways if g.choice_key or g.use}
        if len(choices) > 1:
            return replace(best, among=tuple(choices.values()))
    uses = {g.use: g for g in ways if g.use}
    return replace(best, among=tuple(uses.values())) if best.use and len(uses) > 1 else best


def _linked_if(state: GameState, info: CardInfo, player: str, src: CardInstance, cond: dict[str, Any]) -> bool:
    """-- resolution memory (wave 22D) -- "if an opponent lost life this turn" / "as long as you've sacrificed …": read now, for the source's controller (611.3a)."""
    from app.rules import conditions
    from app.rules.plan import Plan

    ctx = {"controller": player, "source_card": src.id, "source_object": state.rules.object_id(src.id) if state.rules else None}
    if "static" in cond:  # -- as long as (wave 35D) -- a static's own condition ("~ is attached to a creature", "~ is tapped"): app/rules/statics.py
        from app.rules import statics

        return statics.holds(Plan.view(state, player, info), cond, source=src, controller=player)
    return conditions.holds(Plan.view(state, player, info), ctx, cond)


def _while_holds(state: GameState, info: CardInfo, player: str, card: CardInstance, cond: dict[str, Any]) -> bool:
    """-- conditional statics (wave 4B) -- the condition of a card's own "as long as …" permission, read now
    (611.3a); "you" is the card's owner, who is casting it (108.4a)."""
    from app.rules import conditions
    from app.rules.layers import _view

    return conditions.holds(_view(state, info), {"controller": player, "source_card": card.id}, cond)


def _controls_commander(state: GameState, player: str) -> bool:
    """"If you control a commander": a commander (of any player) on the battlefield under your control."""
    return any(c.commander_key is not None and c.controller == player and c.zone.endswith(":battlefield")
               for c in state.cards.values())


def _definitions(ch: Characteristics) -> dict[int, Definition]:
    from app.rules import scripts

    return scripts.definitions(ch)


def ask_use(plan: Plan, a: Any, card: CardInstance, ch: Characteristics, among: tuple[Grant, ...], verb: str) -> None:
    """-- cast permissions (wave 32D) -- which of several limited permissions this cast ("cast") or land play ("play") uses up (601.2; Muldrotha's types are
    one source's uses: the rulings 2020-11-10, an artifact creature spell may be the artifact or the creature). The answer is the action's ``via``,
    asked before anything is paid (wave 30Q asked the types only; an answer saved then, with no ``field``, sets ``slot``)."""
    from app.game.rules_state import DecisionOption
    from app.rules.plan import decide

    types = len({g.label for g in among}) == 1 and all(g.slot for g in among)  # (one permission's types)
    distinct_costs = len({g.life_mv for g in among}) > 1

    def label(g: Grant) -> str:
        base = g.slot if types else f"{g.label} ({g.slot})" if g.slot else g.label
        if g.spell_keywords:
            base += ' — ' + ', '.join(k.capitalize() for k in g.spell_keywords)
        return base if not distinct_costs else base + (" — Pay life equal to mana value" if g.life_mv else " — Without paying its mana cost")

    def source_card(g: Grant) -> str | None:
        # A static source's selection key begins with its exact object id. Show
        # the physical source so identical enchantments are distinguishable.
        key = g.choice_key or g.use
        if ":permission:" not in key:
            return None
        cid = key.split(":permission:", 1)[0].rsplit(".", 1)[0]
        return cid if cid in plan.state.cards else None

    decide(plan, player=plan.actor, kind="choose_one", prompt=f"{ch.name or 'This card'}: {verb} it as which permanent type?" if types
           else f"{ch.name or 'This card'}: {verb} it using which permission?",
           options=[DecisionOption(id=g.choice_key or g.use, label=label(g), card_id=source_card(g)) for g in among],
           resume={"step": "slot", "field": "via", "intent": a.model_dump(mode="json", exclude={"r", "actor", "ts"})}, source=card)


def resume_slot(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.game import actions as A
    from app.rules.engine import INTENTS

    intent = A.parse_action(d.resume["intent"])
    setattr(intent, d.resume.get("field", "slot"), chosen[0])
    plan.rules.priority = d.player
    plan.rules.passed = []
    INTENTS[intent.type](plan, intent)


def gain_on_entry(plan: Plan, card_id: str, controller: str, rider: dict[str, Any] | None) -> None:
    """-- cast permissions (wave 30Q) -- "If you do, it gains "When this permanent is put into a graveyard from the battlefield, exile it and you gain 2
    life."" (Serra Paragon): the permanent the card became has the ability for as long as it is that object (613.1f layer 6; a new object has none, 400.7)."""
    card = plan.state.cards.get(card_id)
    if rider and rider.get("keywords") and card is not None and card.zone.endswith(":battlefield"):  # -- if you do (wave 51D) -- 611.2a: "it gains haste until end of turn", from the moment it is on the battlefield (613.1f)
        from app.rules import layers

        layers.add_effect(plan, affected=[plan.oid(card_id)], layer="6", source=None, controller=controller, add_keywords=tuple(rider["keywords"]),
                          label="Gained from the cast permission")
    if rider and rider.get("subtypes") and card is not None and card.zone.endswith(":battlefield"):  # -- wave 110C -- "and is a Vampire in addition to its other types": layer 4 (205.1b, 613.1d), kept while it is that object
        from app.rules import layers

        layers.add_effect(plan, affected=[plan.oid(card_id)], layer="4", source=None, controller=controller, duration="permanent",
                          add_subtypes=tuple(rider["subtypes"]), label="Gained from the cast permission")
    if rider and rider.get("abilities") and card is not None and card.zone.endswith(":battlefield"):
        from app.rules import layers

        layers.add_effect(plan, affected=[plan.oid(card_id)], layer="6", source=None, controller=controller, duration="permanent",
                          add_abilities=list(rider["abilities"]), label="Gained from the cast permission")


def consume(plan: Plan, grant: Grant | None, *, card_id: str | None = None, verb: str = "cast") -> None:
    """The spell was cast (or the land played) this way: a once-per-turn permission is used up."""
    if grant is None:
        return
    r = plan.rules
    turn = plan.state.turn.number
    if grant.once_key:
        r.once_per_turn[grant.once_key] = turn
    if grant.permission:
        used = next((p for p in r.permissions if p.id == grant.permission), None)
        if used is not None and used.group:  # -- cost reductions paid with objects (wave 47C) -- "play up to two of those cards": one fewer may be, the rest end with the last
            for p in r.permissions:
                if p.group == used.group:
                    p.left -= 1
            r.permissions = [p for p in r.permissions if not (p.group == used.group and p.left <= 0)]
        for p in r.permissions:
            if p.id == grant.permission and p.once:
                p.used_turn = turn
        # "you may play that card": the card is a new object on the stack / battlefield now (400.7)
        r.permissions = [p for p in r.permissions if not (p.id == grant.permission and p.object_id is not None)]

    if grant.use_trigger is not None:
        from app.rules import permission_use_triggers43

        if card_id is None:
            raise ValueError("A consumed trigger authority requires the actual committed card")
        permission_use_triggers43.committed(plan, grant.use_trigger, card_id, verb)


# -- costs (601.2f) --------------------------------------------------------------------------------
def _add(a: M.ManaCost, b: M.ManaCost) -> M.ManaCost:
    return M.ManaCost(a.generic + b.generic, a.colored + b.colored, a.hybrid + b.hybrid, a.phyrexian + b.phyrexian,
                      a.x, a.unsupported + b.unsupported)


def modifiers(state: GameState, player: str, card: CardInstance, ch: Characteristics, info: CardInfo,
              targets: tuple[str, ...] = ()) -> list[CostModifier]:
    """The cost modifiers that apply to ``player`` casting this spell: static abilities on the
    table ("Creature spells you cast cost {1} less to cast", "Spells your opponents cast cost {2}
    more to cast") and stored ones with a duration."""
    r = state.rules
    if r is None:
        return []
    found: list[CostModifier] = []
    from app.rules import cost_statics101

    for src, index, d in _table_statics(state, info, {"cost_modifier"}) + cost_statics101.stack_statics(state, info):
        # -- cost changers (wave 4I) -- per count, with a turn, of the chosen type, from a zone, colored (cost_changes.py)
        delta = cost_changes.static_delta(state, info, src, d, player, card, ch, targets)
        if delta is None:
            continue
        if d["caster"] == "enchanted" and src.attached_player != player:  # -- chosen filters (wave 53B) -- "Spells … enchanted player casts" (Curse of Silence): only the player this Aura enchants
            continue
        found.append(CostModifier(id=f"{src.id}:{index}", controller=src.controller, delta=delta, caster="any" if d["caster"] == "enchanted" else d["caster"],
                                  filter=d["filter"], until="permanent", source=r.object_id(src.id), label=src.name,
                                  mana=cost_changes.stored_mana(d)))
    found += [m for m in r.cost_modifiers  # ("until your next turn": over once its controller's next turn began)
              if not (m.until == "next_turn" and r.turn_started.get(m.until_player or m.controller, 0) > m.turn)]
    out = []
    for m in found:
        if m.from_zones:
            origin: str | None = card.zone.rsplit(':', 1)[-1]
            if origin == 'stack':
                receipt = r.payments.get(r.object_id(card.id))
                origin = receipt.cast_from if receipt is not None else None
            if origin not in m.from_zones:
                continue
        if m.caster == "you" and m.controller != player:
            continue
        if m.caster == "opponent" and m.controller == player:
            continue
        if m.filter and not spell_matches(state, player, card, ch, m.filter, info):
            continue
        out.append(m)
    return out


_LIFE_PER_TARGET = re.compile(r"^(?:this spell|~) costs (?P<n>\d+) life more to cast for each target$")
_PER_TARGET = re.compile(r"^(?:this spell|~) costs (?P<cost>(?:\{[^}]+\})+) more to cast for each target beyond the first$")


def self_reduction(state: GameState, player: str, card: CardInstance, ch: Characteristics, info: CardInfo) -> int:
    """The spell's own reductions: "costs {1} less to cast for each …" / "… if …", undaunted (702.125)."""
    from app.rules import conditions
    from app.rules.plan import live_players

    total = 0
    opponents = sum(1 for p in live_players(state) if p != player)
    if "undaunted" in ch.keywords:
        total += opponents * max(1, sum('undaunted' in ability.keywords for ability in ch.abilities))
    view = None
    for d in _definitions(ch).values():
        if d.get("static") != "self_cost" or "change" in d or "per_target" in d or "life_per_target" in d:  # (wave 4I: a "change" is cost_changes.own_changes')
            continue
        if d.get("per") == "opponent":
            total += d["n"] * opponents
            continue
        view = view or _view(state, player, info)
        if d.get("per"):
            total += d["n"] * len(selectors.candidates(view, selectors.from_key(d["per"]), player, card.id))
        elif d.get("cond") is not None and conditions.holds(view, {"controller": player, "source_card": card.id}, d["cond"]):
            total += d["n"]
    return total


def total_cost(state: GameState, player: str, card: CardInstance, ch: Characteristics, info: CardInfo | None, *,
               base: M.ManaCost, additional: tuple[M.ManaCost, ...] = (), tax: int = 0, affinity: int = 0,
               targets: tuple[str, ...] = (), symbols: list[str] | None = None,
               capture: list[Any] | None = None) -> M.ManaCost:
    """601.2f: the mana cost or alternative cost (``base``), plus additional costs (kicker,
    buyback: 118.8) and cost increases (commander tax, "cost {N} more"), minus cost reductions
    (affinity, "cost {N} less", the spell's own). Reductions affect only the generic component
    (118.7a) and can't take it below {0}."""
    cost = base
    for extra in additional:
        cost = _add(cost, extra)
    increase = tax
    reduction = affinity
    changes = cost_changes.Changes()  # -- cost changers (wave 4I) -- colored increases / reductions (118.7b/c)
    if info is not None:
        from app.rules import spell_grants

        reduction += spell_grants.cost_reduction(state, player, card, ch, info)  # (-- cant restrictions (wave 46A) -- "The next spell you cast this turn costs {1} less")
        for m in modifiers(state, player, card, ch, info, targets):  # (targets: wave 4I, "spells that target …")
            if m.mana:
                changes.add(m.delta, m.mana)
            elif m.delta > 0:
                increase += m.delta
            else:
                reduction -= m.delta
        reduction += self_reduction(state, player, card, ch, info)
        own = cost_changes.own_changes(state, player, card, ch, info, _definitions(ch), targets)
        increase += own.increase
        reduction += own.reduction
        changes.colored_more += own.colored_more
        changes.colored_less += own.colored_less
        changes.colored_only += own.colored_only
        for d in _definitions(ch).values():  # -- static_other sweep (wave 16B) -- strive: for each target beyond the first
            if d.get("static") == "self_cost" and d.get("per_target"):
                more, each = max(0, len(targets) - 1), M.parse_cost(d["per_target"])
                increase += each.generic * more
                changes.colored_more += tuple(each.colored) * more
    from app.rules.spell_cost_stages import PreparedCost

    prepared = PreparedCost(cost_changes.add_colored(cost.plus_generic(increase), changes.colored_more),
                            reduction, changes.colored_less, changes.colored_only)
    if capture is not None:
        capture.append(prepared)
    return prepared.evaluate(symbols)


# -- costs (wave 3$) -- cost modifiers for activated abilities (602.2b -> 601.2f, 118.7) ---------------------
def ability_mana(state: GameState, player: str, card: CardInstance, ch: Characteristics, mana: str, info: CardInfo,
                 own: int = 0, ability_text: str = "", target: str | None = None, mana_ability: bool = False,
                 capture: list[int] | None = None, targets: tuple[str, ...] | None = None) -> str:
    """The mana part of an activated ability's cost after "Activated abilities of creatures you control cost {2} less to
    activate" and its increases: increases first, then reductions on the generic component only (118.7a, 601.2f), and with
    "can't reduce the mana in that cost to less than one mana" never below one mana. Costs with {X} are left alone."""
    cost_statics = _table_statics(state, info, {"ability_cost_modifier", "cost_modifier", "grant"})
    mods = [(src, d) for src, _, d in cost_statics if d.get("static") == "ability_cost_modifier"]
    from app.rules import caster_turn_costs63

    mods += caster_turn_costs63.ability_modifiers(state, player, cost_statics)
    from app.rules import selected_keyword_costs65

    mods += selected_keyword_costs65.ability_modifiers(state, player, cost_statics)
    from app.rules import colored_activation_costs83

    own_cut83, own_colors83 = colored_activation_costs83.reduction(state, player, card, ability_text, info)
    if capture is not None:
        capture.append(0)
    if not mods and not own and not own_cut83 and not own_colors83:  # (own: the ability's "This ability costs {1} less …", wave 4I)
        return mana
    cost = M.parse_cost(mana)
    if cost.x or cost.unsupported:
        return mana
    view = None
    increase, reduction = max(0, own), max(0, -own) + own_cut83
    floored_reduction = 0
    from app.rules import attachments

    for src, d in mods:
        if d.get('target_rule62'):
            from app.rules import target_cost_conditions62

            chosen = targets if targets is not None else ((target,) if target and target != '?' else ())
            if not target_cost_conditions62.available(state, player, src, d['target_rule62'], chosen, info, preview=target == '?'):
                continue
        if d.get("first_controlled_creature_target58"):
            from app.rules import first_target_activation_cost58

            if not first_target_activation_cost58.available(state, player, target, targets, info):
                continue
        if d.get('source_only') and src.id != card.id:
            continue
        if d["who"] == "you" and src.controller != player:
            continue
        if d.get("attached_host") and (src.attached_to != card.id or not card.zone.endswith(":battlefield")):
            continue
        if d.get('condition') is not None:
            from app.rules import conditions

            view = view or _view(state, player, info)
            if not conditions.holds(view, cost_changes.context(state, src.controller, src), d['condition']):
                continue
        if d.get('loyalty_only'):
            from app.rules import oracle

            if not oracle._LOYALTY.match(ability_text):
                continue
        if d.get('exhaust_only') and not ability_text.startswith('Exhaust — '):
            continue
        if d.get('boast_only') and not ability_text.startswith('Boast — '):
            continue
        if mana_ability and d.get("nonmana"):  # -- chosen filters (wave 53B) -- "unless they're mana abilities": a mana ability is not charged
            continue
        if d.get("ninjutsu"):
            from app.rules import ninjutsu

            if not ninjutsu.is_ninjutsu(ability_text):
                continue
        if d.get("cycling") and ability_text != "cycling" and not ability_text.startswith("Cycling — "):
            continue
        if d.get("equip") and not attachments.is_equip_text(ability_text):  # -- equip (wave 15E) --
            continue
        if d.get("power_up") and not ability_text.startswith("Power-up — "):  # (wave 50J)
            continue
        if d.get("target_self") and (target is None or target not in ("?", src.id) or (target == "?" and d["delta"] > 0)):
            continue  # -- most-played cards III (wave 46C) -- only for an ability that targets the source ("?": not chosen yet, the best case for a reduction)
        if bool(d.get("plot")) != (ability_text == "plot"):  # -- cant restrictions (wave 46A) -- plotting is a special action (116.2k): only plot changers touch its cost, and they touch nothing else
            continue
        if d["filter"]:
            view = view or _view(state, player, info)
            if not selectors.matches(view, selectors.from_key(d["filter"]), card, ch, src.controller, src.id):
                continue
        delta = d["delta"]
        if d.get("value") is not None:  # (wave 44D) the amount read now, with the source's own context
            view = view or _view(state, player, info)
            from app.rules import values

            delta = d["sign"] * values.evaluate(view, cost_changes.context(state, src.controller, src), d["value"])
        if delta > 0:
            increase += delta
        elif delta < 0:
            if d['floor']:
                floored_reduction -= delta
            else:
                reduction -= delta
    if not increase and not reduction and not floored_reduction and not own_colors83:
        return mana
    cost = cost.plus_generic(increase)
    # 601.2f: floored reductions may be applied before unrestricted ones.
    symbols = cost.generic + len(cost.colored) + len(cost.hybrid) + len(cost.phyrexian)
    floored_cut = min(floored_reduction, max(0, symbols - 1))
    cut = min(cost.generic, floored_cut + reduction)
    if capture is not None:
        capture[-1] = cut
    out = cost.plus_generic(-cut)
    if own_colors83:
        out = cost_changes.reduce_colored(out, own_colors83)
    return mana if not mana and out.is_free else out.text()  # (wave 4I: "{T}: …" taxed {2} becomes "{2}, {T}: …")


# -- effects ---------------------------------------------------------------------------------------
def _attacked_when(what: str) -> dict[str, Any] | None:
    """-- trigger other (wave 51E) -- the condition of "During any turn you attacked with <what>": "this creature" (the permission's source), "three or more creatures", or a
    kind of creature ("a token", "a commander", "a Rogue"), read from the turn's declared attackers (508.1, history._attacked_with)."""
    from app.rules import selectors

    if what in ("this creature", "~"):
        return {"history": "attacked_with", "self": True}
    if (m := re.fullmatch(r"(\w+) or more creatures", what)) is not None:
        n = {"two": 2, "three": 3, "four": 4, "five": 5}.get(m[1])
        return {"history": "attackers", "n": n} if n else None
    sel = selectors.parse(re.sub(r"^an? ", "", what))
    return {"history": "attacked_with", "sel": sel.key()} if sel is not None and sel.player is None and not sel.card and sel.zones in ((), ("battlefield",)) else None


def grant_play(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """"You may play that card this turn" (the objects an earlier instruction of this ability
    moved — bound by scripts.resolve_it, found where they went: 400.7h/j) or "Until end of turn,
    you may play lands and cast spells from your graveyard"."""
    from app.rules import context, permission_use_triggers43

    pid = ctx["controller"]
    r = plan.rules
    turn = plan.state.turn.number
    when = "until their next upkeep begins" if e["until"] == "next_upkeep" else \
        "until the end of combat on their next turn" if e["until"] == "next_combat_end" else \
        "until the end of their next turn" if e["until"] == "end_of_next_turn" else \
        "until their next end step" if e["until"] == "next_end_step" else \
        "until their next turn" if e["until"] == "next_turn" else \
        f"for as long as they {'control' if e['until'] == 'source_controlled' else 'have'} {ctx.get('name') or 'its source'}" \
        if e["until"] in SOURCE_UNTIL else \
        "for as long as it remains there" if e["until"] == "permanent" else "this turn"  # (permanent: wave 3E, 611.2a)
    if e["until"] in SOURCE_UNTIL and not delayed._source_ok(plan, e["until"], ctx.get("source_card"), ctx.get("source_object"), pid):
        plan.note(f"{ctx.get('name') or 'The effect'} does nothing: its duration has already ended")  # 611.2b
        return True
    if e.get("stop_on_linked_exile"):
        when = "until they exile another card with its source"
    verb = "play" if e["play"] else "cast"
    if e.get("who"):
        if not str(e["who"]).startswith(context.PREFIX) and e["who"] not in ("target", "cost_exiled_self"):
            return True  # (an unbound pronoun never reaches here: resolve_it refuses the ability)
        # -- as long as (wave 37A) -- "You may cast this card for as long as it remains exiled": the card its cost exiled
        from app.rules import effects as _effects
        from app.rules import exiled_with

        stop_on_linked_exile = exiled_with.link_key(ctx) if e.get("stop_on_linked_exile") else None
        group = secrets.token_hex(4) if e.get("limit") else ""  # (-- cost reductions paid with objects (wave 47C) -- "up to two of those cards": one limit for them all)
        for cid in _effects._cards(plan, ctx, "cost_exiled_self") if e["who"] == "cost_exiled_self" else \
                context.objects(plan, ctx, e["who"][len(context.PREFIX):]) if e["who"] != "target" else _target_cards(plan, ctx):
            card = plan.state.cards[cid]
            if e.get("from_exile") and not card.zone.endswith(":exile"):
                continue  # -- free cast (wave 40D) -- "play that card from exile this turn" (Norin): a card a replacement put elsewhere isn't in exile to be played from
            if (e["until"] == "permanent" or e["until"] in SOURCE_UNTIL) and not card.zone.endswith(":exile"):
                continue  # (-- Marvel keywords (wave 25A) -- "for as long as it remains exiled": a spell that wasn't countered, a card replaced elsewhere: no permission)
            holder = card.owner if e.get("owner") else pid  # ("its owner may cast it")
            r.permissions.append(Permission(id=secrets.token_hex(4), player=holder, play=e["play"], cast=e["cast"], zone="any",
                                            object_id=plan.oid(card), card=cid, generic_extra=int(e.get("generic_extra", 0)) + (int(e.get("generic_extra_opponents", 0)) if holder != pid else 0), until=e["until"], turn=turn, granted_step=r.step_serial, stop_on_linked_exile=stop_on_linked_exile, free=bool(e.get("free")), life_mv=bool(e.get("life_mv")), spend=e.get("spend", ""),
                                            filter=e.get("filter"), spell_keywords=e.get('spell_keywords', []), until_player=e.get("until_player"), after_turn=int(e.get("after_turn", 0)),
                                            exile_gy=e.get("exile_gy", ""), exile_own=bool(e.get("exile_own")), graveyard_destination=e.get("graveyard_destination", ""), enters=e.get("enters"),  # (wave 25C; wave 51D: enters)
                                            use_trigger=permission_use_triggers43.stored_receipt(plan, ctx, e.get("use_trigger")),
                                            source=ctx.get("source_object"), group=group, left=int(e.get("limit") or 0), when=e.get("when"),  # (wave 51E)
                                            label=f"{ctx.get('name') or 'An effect'}: {verb} it {when}" + (" paying life equal to its mana value" if e.get("life_mv") else " without paying its mana cost" if e.get("free") else "")))
            plan.note(f"{plan.name(holder)} may {verb} {card.name} {when}", [cid])
        return True
    zone_label = "exile" if e.get("zone_owner") == "any" and e["zone"] == "exile" else "any graveyard" if e.get("zone_owner") == "any" and e["zone"] == "graveyard" else f"your {e['zone']}"
    r.permissions.append(Permission(id=secrets.token_hex(4), player=pid, play=e["play"], cast=e["cast"], zone=e["zone"],
                                    zone_owner=e.get("zone_owner", "you"), card_filter=e.get("card_filter"), look_top=bool(e.get("look_top")),
                                    free=bool(e.get("free")), life_mv=bool(e.get("life_mv")),
                                    extra=e.get("extra", ""), enters=e.get("enters"),
                                    filter=e.get("filter"), once=bool(e.get("once")),  # (-- cast permissions (wave 30Q) -- "a creature spell": one spell, of that kind)
                                    exile_gy=e.get("exile_gy", ""), exile_own=bool(e.get("exile_own")), graveyard_destination=e.get("graveyard_destination", ""),  # (wave 25C)
                                    until=e["until"], until_player=e.get("until_player"), after_turn=int(e.get("after_turn", 0)), turn=turn, granted_step=r.step_serial, source=ctx.get("source_object"),
                                    label=f"{ctx.get('name') or 'An effect'}: {verb} from {zone_label} {when}"))
    what = "play lands and cast spells" if e["play"] and e["cast"] else "play lands" if e["play"] else "cast spells"
    note_zone = zone_label if e.get("zone_owner") == "any" else f"their {e['zone']}"
    plan.note(f"{plan.name(pid)} may {what} from {note_zone} {when}")
    return True


def _target_cards(plan: Plan, ctx: dict[str, Any]) -> list[str]:
    """-- if you do (wave 25C) -- the ability's target cards still in a graveyard (608.2b: legal targets only; public zone, 400.2)."""
    return [t["id"] for t in ctx.get("targets") or [] if t.get("id") in plan.state.cards and plan.state.cards[t["id"]].zone.endswith(":graveyard")]


def expire(plan: Plan) -> None:
    """514.2: "this turn" / "until end of turn" permissions and modifiers end in the cleanup step;
    "until the end of your next turn" ones at the end of that player's next turn; a permission
    for an object that is gone (400.7) is dropped too."""
    r = plan.rules
    turn = plan.state.turn.number
    active = plan.active
    keep = []
    for p in r.permissions:
        if p.until == "end_of_turn":
            continue
        if p.until == "end_of_next_turn" and (p.until_player or p.player) == active and turn > p.turn:
            continue
        if p.object_id is not None and (p.card not in plan.state.cards or r.object_id(p.card) != p.object_id):
            continue
        keep.append(p)
    r.permissions = keep
    r.cost_modifiers = [m for m in r.cost_modifiers if m.until != "end_of_turn"
                        and not (m.until == "next_turn" and r.turn_started.get(m.until_player or m.controller, 0) > m.turn)]


SOURCE_UNTIL = ("source_controlled", "source_on_battlefield")  # (-- durations (wave 30M) -- Permission.until: "for as long as you control ~")


def source_holds(state: GameState, p: Permission) -> bool:
    """-- durations (wave 30M) -- 611.2b: "for as long as you control ~ / ~ remains on the battlefield" is still true: the granting object is the one
    that was on the battlefield (a new object, 400.7, is not), in the game (800.4a), and under the permission's player's control for "you control"."""
    from app.rules.plan import live_players

    card = state.cards.get((p.source or "").rsplit(".", 1)[0])
    return (card is not None and state.rules is not None and card.zone.endswith(":battlefield") and state.rules.object_id(card.id) == p.source
            and card.owner in (live := live_players(state)) and card.controller in live
            and (p.until != "source_controlled" or card.controller == p.player))


def _on_top(plan: Plan, p: Permission) -> bool:
    card = plan.state.cards.get(p.card or "")
    return card is not None and (plan.state.zones.get(card.zone) or [""])[0] == card.id and card.zone.endswith(":library")


def expire_source(plan: Plan) -> None:
    """-- durations (wave 30M) -- the stored permissions whose "for as long as …" is over are gone (called with the other checks: delayed.expire)."""
    r = plan.rules
    r.permissions = [p for p in r.permissions if not p.top110j or _on_top(plan, p)]  # -- wave 110J -- "for as long as that card remains on top": once it isn't, it's over for good
    if any(p.until in SOURCE_UNTIL for p in r.permissions):
        r.permissions = [p for p in r.permissions if p.until not in SOURCE_UNTIL or source_holds(plan.state, p)]


def expire_end_step(plan: Plan) -> None:
    """-- trigger tail (wave 15B) -- "until your next end step" (611.2a): the permission ends as that player's end step begins
    (``turn`` is the first turn whose end step may end it: grant_play), before anything is played in it."""
    turn = plan.state.turn.number
    plan.rules.permissions = [p for p in plan.rules.permissions
                              if not (p.until == "next_end_step" and (p.until_player or p.player) == plan.active and turn >= p.turn
                                      and (p.granted_step is None or plan.rules.step_serial > p.granted_step))]


def expire_combat(plan: Plan) -> None:
    """611.2a: a duration ending at next turn's combat ends at the phase boundary."""
    turn = plan.state.turn.number
    plan.rules.permissions = [p for p in plan.rules.permissions
                              if not (p.until == "next_combat_end" and (p.until_player or p.player) == plan.active
                                      and turn > p.turn)]


def cost_modifier(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """"<Spells> you cast this turn cost {N} less to cast" / "Until your next turn, <spells> you cast
    cost {N} less to cast": a cost modifier for its controller's spells with that duration (601.2f,
    611.2a; generic mana only, 118.7a), read with the table's static ones (``modifiers``)."""
    if e.get("recipient66"):
        from app.rules import effects

        for recipient in effects._players(plan, ctx, e["recipient66"]):
            cost_modifier(plan, {**ctx, "controller": recipient}, {k: v for k, v in e.items() if k != "recipient66"})
        return True
    pid = ctx["controller"]
    from app.rules import values

    delta = e["dir"] * values.evaluate(plan, ctx, e["delta"]) if isinstance(e["delta"], dict) else int(e["delta"])  # (wave 44D: an amount read now, 611.2a)
    plan.rules.cost_modifiers.append(CostModifier(
        id=secrets.token_hex(4), controller=pid, delta=delta, caster=e.get("caster") or ("any" if e.get("any") else "you"), filter=e.get("filter"),  # (wave 53B: Cheering Fanatic, everybody's spells)
        until=e["until"], until_player=e.get("until_player69"), turn=plan.state.turn.number, source=ctx.get("source_object"),
        from_zones=list(e.get("from_zones") or []), label=(ctx.get("name") or "An effect")[:120]))
    amount = f"{{{abs(delta)}}} {'less' if delta < 0 else 'more'}"
    duration_owner = e.get('until_player69') or pid
    duration = (f"until {plan.name(duration_owner)}’s next turn" if duration_owner != pid else "until their next turn") if e["until"] == "next_turn" else "this turn"
    plan.note(f"{plan.name(pid)}'s spells cost {amount} to cast {duration} ({ctx.get('name') or 'an effect'})")
    return True


def refresh_reveals(state: GameState, info: CardInfo) -> None:
    """Recompute which cards of the game have a "play with the top card of your library revealed"
    / "you may look at the top card of your library any time" ability (401.5): every card, in
    whatever zone, since the view (``app.game.visibility``, which has no card database) reads the
    *table* for the rest — whether the source is on a battlefield right now, face up, and under
    whose control — so a source put onto the battlefield, taken or removed by hand reveals the
    right library at once, with no engine action in between. Pure: a function of the cards and
    the database, so replay reproduces it. ``player`` records the controller as listed, for
    information only."""
    from app.rules import scripts
    from app.rules.layers import derive

    r = state.rules
    if r is None:
        return
    found = []
    for card in state.cards.values():
        if card.ability is not None:
            continue
        ch = chars.of(card, info)
        if card.zone.endswith(":battlefield") and not card.face_down:
            ch = derive(state, card, ch, info)
        for d in scripts.definitions(ch).values():
            if d.get("kind") == "static" and d.get("static") == "top_reveal":
                found.append(TopReveal(source=card.id, player=card.controller, to=d["to"], face_down=bool(d.get("face_down")),
                                       zone=d.get("zone", "library"), whose=d.get("whose", "you")))
            elif d.get("kind") == "static" and d.get("static") == "permission" and d.get("look"):  # (wave 5I: Radha)
                found.append(TopReveal(source=card.id, player=card.controller, to="owner"))
    if found != r.top_reveals:
        r.top_reveals = found


# -- cast without paying (wave 3C) --
def free_cast(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """"You may cast a spell with mana value N or less from your hand without paying its mana cost" /
    "you may cast that card without paying its mana cost": as this resolves (608.2g) its controller
    picks one eligible card (or none); the engine then lets them cast it for {0} (118.9: X is 0,
    107.3b; kicker and other additional costs may still be paid, 118.9d). Nothing is kept: a card
    not cast now can't be cast this way later.

    -- refused look/cast-free (wave 3R5) -- The cast happens during the resolution (608.2g: the spell
    becomes the topmost object and the resolving spell or ability continues), so instructions after it
    follow the cast ("Put the rest on the bottom of your library"). ``zone``: "hand", "that" (the
    cards a binding names), "looked" (the cards looked at, still in the library), "found" (the card a
    "… until you exile / reveal a …" stopped at), "target" (the ability's target card); ``n``: how
    many spells may be cast this way (one at a time, each cast before the next is chosen: 608.2g
    "which may include casting other spells this way"); the cards cast are ctx["free_cast_done"]."""
    from app.game.rules_state import DecisionOption
    from app.rules import characteristics as chars
    from app.rules import values
    from app.rules.effects import decide

    pid = ctx["controller"]
    if e.get("caster"):  # -- (wave 110J) -- Swindler's Scheme: "that opponent may cast the revealed card"
        from app.rules import wave110j_cards

        pid = wave110j_cards.caster(plan, ctx, e)
    done = ctx.setdefault("free_cast_done", [])
    if not e.get("all") and sum(1 for c in done if c not in (ctx.get("free_cast_before") or [])) >= int(e.get("n", 1)):
        return _free_cast_over(ctx, e)
    pool = _free_pool(plan, ctx, e)
    if e.get("each") and len(done) > len(ctx.get("free_cast_before") or []) and all(c in done for c in pool):
        return _free_cast_over(ctx, e)  # -- review 29D -- 607.3: each linked card has been played (hideaway.each)
    limit = None
    if e.get("mv") is not None:
        limit = values.evaluate(plan, ctx, {"x": 1} if e["mv"] == "x" else e["mv"])
    if e.get('mv_total') is not None:
        if 'free_cast_budget' not in ctx:
            ctx['free_cast_budget'] = max(0, values.evaluate(plan, ctx, e['mv_total']))
        limit = min(limit, ctx['free_cast_budget']) if limit is not None else ctx['free_cast_budget']
    below = values.evaluate(plan, ctx, e["mv_lt"]) if e.get("mv_lt") is not None else None  # (wave 3R5: "lesser")
    options = []
    required_decline = False
    play = bool(e.get("play"))  # -- play now (wave 28A) -- "you may play that card": a land too, and each face of a card with two (712.12, 709.3)
    land_open = play and land_plays.open_for_effect(plan.state, pid, plan.info)  # 305.2a-b, 305.3
    for cid in pool:
        card = plan.state.cards[cid]
        if not _effect_source_zone_ok(plan, ctx, e, card, pid):
            continue
        if plan.rules.card_mode(cid) == "manual" or cid in done or not plan.in_game(card):  # (review 28A: 800.4a, its owner left)
            continue
        if card.face_down and card.zone.endswith(":exile") and not can_see(plan.state, card, pid):
            continue  # -- hideaway (wave 29D) -- 406.3b: a face-down card may be cast only by a player who is allowed to look at it
        # (review 28A) a cast too is of one half / face, and only that one is evaluated (709.3a, 712.11c, 715.3a, 601.3e): a sorcery-only cast
        # never casts the instant half of Consecrate // Consume. "If its mana value is odd" (Yennett) tests the card (709.4b) as before, one way
        for face, ch in [(None, chars.of(card, plan.info))] if e.get("parity") else play_faces(plan, card):
            if not ch.types:
                continue
            if ch.is_land:
                if land_open:  # (never reached without ``play``: land_open is False then)
                    options.append(DecisionOption(id=_option_id(cid, face), label=f"{ch.name or card.name or 'Card'} (play as a land)",
                                                  card_id=cid))
                continue
            if limit is not None and (ch.mana_value > limit or (e.get("mv_eq") and ch.mana_value != limit)):
                continue
            if e.get("paid") and not ch.mana_cost and e.get("effect_mana_cost") is None:
                from app.rules import paid_effect_costs

                if not paid_effect_costs.alternatives(plan, card, ch, player=pid):
                    continue  # 118.6: a missing cost needs a payable alternative
            if below is not None and ch.mana_value >= below:
                continue
            if e.get("shares_type") and not _shares_type(plan, ctx, ch, "target" if e["shares_type"] == "target" else "event"):  # -- if you do (wave 40A) -- "that shares a card type with it": the spell that triggered this
                continue
            if e.get("parity") and ch.mana_value % 2 != (1 if e["parity"] == "odd" else 0):
                continue
            if e.get("filter") and not spell_matches(plan.state, pid, card, ch, e["filter"], plan.info):
                continue
            # -- cast limits (wave 5E) -- a cast no rule or effect prohibits (601.3)
            from app.rules import cast_limits

            if cast_limits.free_cast_blocked(plan, pid, cid, face) is not None:  # (wave 29B: the half / face being offered)
                continue
            from app.rules import (
                casting,  # (review 29B: no choice may be a dead end, 601.2c / 601.5)
                text_global_word71,
            )

            prospective71 = text_global_word71.prospective(plan.state, card, chars.as_cast(card, plan.info, face), plan.info)
            if casting.free_cast_problem(plan, pid, card, prospective71, paid=bool(e.get("paid")), x=0 if e.get("effect_mana_cost") is not None else None) is not None:  # (the half cast_spell casts)
                continue
            if e.get('effect_alternative'):
                from app.rules import effect_cast_costs

                if effect_cast_costs.problem(plan, pid, card, prospective71, e) is not None:
                    continue
            if e.get('required'):
                from app.rules import costs

                extra = costs.spell_additional_cost(prospective71.abilities)
                if extra is not None and casting.additional_problem(plan, extra, card, pid) is not None:
                    continue
                # 118.8c: a mandatory cast may be declined rather than exposing
                # whether cards with a stated quality exist in a hidden zone.
                for side in (() if extra is None else (extra, *extra.either)):
                    for part in side.components:
                        if part.kind in casting._HAND_PARTS and part.selector:
                            sel = selectors.from_key(part.selector)
                            plain = selectors.replace(sel, zones=(), zone_owner=None, card=False, controller=None, owner=None)
                            if plain != selectors.Selector():
                                required_decline = True
            options.append(DecisionOption(id=_option_id(cid, face), label=(ch.name if face is not None else card.name) or "Card",
                                          card_id=cid))
    # (cards in a hand or a library are hidden: whether a choice appears mustn't tell the other
    # players whether one was eligible, so the looker is asked whenever there were cards to look at)
    # (-- hideaway (wave 29D) -- 406.3: a face-down exiled card is as hidden as one in a hand: "has nothing to cast" would tell the table it is a land
    # with no land play left, or a spell that can't be cast)
    hidden = (e["zone"] in ("hand", "looked", "revealed") or any(
        plan.state.cards[c].face_down or plan.state.cards[c].zone.endswith(':hand') for c in pool)) and bool(pool)
    if not options and not hidden:
        plan.note(f"{plan.name(pid)} has nothing to cast" + ("" if e.get("paid") else " without paying its mana cost"))
        return _free_cast_over(ctx, e)
    many = (e.get("all") or int(e.get("n", 1)) > 1) and not (e.get("each") and len(pool) < 2)
    decide(plan, player=pid, kind="choose_cards",
           prompt="Choose a spell to cast" + ("" if e.get("paid") else " without paying its mana cost") + (" (one at a time)" if many else "")
                  + ("" if e.get('required') and options and not required_decline else " (or none)"),
           options=options, min_choices=1 if e.get('required') and options and not required_decline else 0,
           max_choices=1, resume={"step": "free_cast_pick", "ctx": ctx, "e": e})
    return False


def _shares_type(plan: Plan, ctx: dict[str, Any], ch: Characteristics, who: str = "event") -> bool:
    """-- if you do (wave 40A) -- 205.2: the card shares a card type with the spell the trigger is about (as it was cast, 608.2h)."""
    from app.rules import values

    found = values._object(plan, ctx, who)
    return found is not None and bool(set(ch.types) & set(found[1].types))


# -- play now (wave 28A) --
def _option_id(cid: str, face: int | None) -> str:
    return cid if face is None else f"{cid}@{face}"


def play_faces(plan: Plan, card: CardInstance) -> list[tuple[int | None, Characteristics]]:
    """Each way a card can be played or cast: one face of a modal double-faced card (712.12: a land face is played, a spell face cast), one
    half of a split card or an Adventure (709.3, 715.3; an Aftermath half only from a graveyard, 702.127a), else the card as it is."""
    data = plan.info.get(card.card_id or "") if card.card_id and card.token is None and (not card.is_token or card.copy_of is not None) else None
    layout = (data or {}).get("layout")
    if data is None or len(data.get("faces") or []) < 2 or layout not in (*chars.HALVES, "modal_dfc"):
        return [(None, chars.of(card, plan.info))]
    out: list[tuple[int | None, Characteristics]] = []
    for face in (0, 1):
        ch = chars.as_cast(card, plan.info, face)
        if ((layout == "aftermath" and face == 1) or "aftermath" in ch.keywords) and not card.zone.endswith(":graveyard"):
            continue  # current canonical data labels Aftermath cards as split
        out.append((face, ch))
    return out


def play_land_now(plan: Plan, ctx: dict[str, Any], e: dict[str, Any], cid: str, face: int | None) -> None:
    """305.1 / 608.2g: the card is played as a land by the effect (not cast: it never uses the stack). It counts against the land plays of the
    turn (305.2a) from the moment it is played; the entering choices (a shock land's life, "as it enters, choose …": 614.12a) are asked as
    for any permanent put onto the battlefield, then the resolution goes on (replacements.resume_entry_choice)."""
    from app.game.rules_state import TurnCount
    from app.rules import attachments, effects

    pid = ctx["controller"]
    card = plan.state.cards[cid]
    r, turn = plan.rules, plan.state.turn.number
    r.lands_played[pid] = TurnCount(turn=turn, count=r.lands_this_turn(pid, turn) + 1)
    ctx.setdefault("free_cast_done", []).append(cid)
    if e.get("all") or int(e.get("n", 1)) > 1:
        ctx["next"] -= 1  # "any number of them": the same instruction is carried out again for the next card once this one has entered
    else:
        _free_cast_over(ctx, e)
    plan.note(f"{plan.name(pid)} plays {chars.as_cast(card, plan.info, face).name or card.name} from their "
              f"{card.zone.rsplit(':', 1)[-1]} ({ctx.get('name') or 'an effect'})", [cid])
    entry: dict[str, Any] = {"card": cid, "player": pid, "actor": pid, "played": True}
    if face:
        entry["modal_back"] = True  # 712.12: it enters with the land face up
    if attachments.enter(plan, [entry], ctx):
        effects.continue_effects(plan, ctx)
# -- end play now (wave 28A) --


def _free_cast_over(ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """This free cast is over: "If you don't cast it, …" reads whether it cast anything (``did``)."""
    from app.rules import context

    done, before = ctx.get("free_cast_done") or [], ctx.get("free_cast_before") or []
    if e.get("did"):
        context.refs(ctx)[e["did"]] = {"kind": "payment", "ok": len(done) > len(before)}
    ctx.pop("free_cast_budget", None)
    ctx["free_cast_before"] = list(done)  # (a later free cast of the same ability counts afresh)
    return True


def found_to(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """-- refused look/cast-free (wave 3R5) -- "If you don't cast it, put it into your hand": the card a
    "… until you exile / reveal a …" stopped at, or the one card revealed, if it is still there."""
    pid = ctx["controller"]
    owner = ctx.get("looked_owner") or pid
    found = ctx.get("found")
    looked = [c for c in ctx.get("looked") or [] if c in plan.state.zones.get(zone_key(owner, "library"), [])]
    cid = found if found else (looked[0] if len(looked) == 1 else None)
    card = plan.state.cards.get(cid or "")
    if card is None or not card.zone.endswith((":exile", ":library")):
        return True
    # (review 28A) its owner's hand or exile (400.3: "your hand" is its owner's when the card came from another library)
    plan.do({"type": "move", "card_ids": [card.id], "to": {"player": card.owner, "zone": e["to"]}}, actor=pid)
    return True


def _effect_source_zone_ok(plan: Plan, ctx: dict[str, Any], e: dict[str, Any], card: CardInstance, player: str) -> bool:
    if not e.get('source_zone'):
        return True
    from app.rules import effects

    owners = effects._players(plan, ctx, e['source_owner']) if e.get('source_owner') else [player]
    return any(card.zone == zone_key(owner, e['source_zone']) for owner in owners)


def _free_pool(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> list[str]:
    """The cards a free cast may choose from (their current objects only, 400.7)."""
    from app.rules import context

    pid = ctx["controller"]
    zone = e["zone"]
    if zone == "selector" and e.get("pool_selector"):
        return selectors.candidates(plan, selectors.from_key(e["pool_selector"]), pid, ctx.get("source_card"))
    if zone == "hand_graveyard":
        return [cid for place in ("hand", "graveyard") for cid in plan.state.zones.get(zone_key(pid, place), [])]
    if zone == "hand":
        return list(plan.state.zones.get(zone_key(pid, "hand"), []))
    if zone == "looked":  # still in the library they were looked at in
        owner = ctx.get("looked_owner") or pid
        library = plan.state.zones.get(zone_key(owner, "library"), [])
        return [c for c in ctx.get("looked") or [] if c in library]
    if zone == "revealed":  # -- player-relative selectors (wave 53A) -- the cards seen in a hand ("look at that player's hand"), while they are still there (400.7)
        return [c for c in ctx.get("looked_hand") or [] if c in plan.state.cards and plan.state.cards[c].zone.endswith(":hand")]
    if zone == "found":
        found = ctx.get("found")
        card = plan.state.cards.get(found or "")
        return [found] if found is not None and card is not None and card.zone.endswith((":exile", ":library")) else []
    if zone == "target":
        return [t["id"] for t in ctx.get("targets") or [] if t.get("id") in plan.state.cards
                and plan.state.cards[t["id"]].zone.endswith(":graveyard")]
    if zone == "graveyard":  # your graveyard, or every graveyard (public zones)
        whose = [pid] if e.get("whose") == "you" else plan.live()
        return [c for p in whose for c in plan.state.zones.get(zone_key(p, "graveyard"), [])]
    if zone == "exile_counters":  # -- cast riders (wave 38C) -- the cards in exile (a player's own, or all) that have that kind of counter on them
        return [c for p in ([pid] if e.get("own") else plan.live()) for c in plan.state.zones.get(zone_key(p, "exile"), [])
                if plan.state.cards[c].counters.get(e["kind"], 0) > 0 and (not e.get("own") or plan.state.cards[c].owner == pid)]
    who = str(e.get("who") or "")
    if who == "self_gy":
        from app.rules.effects import _cards

        return _cards(plan, ctx, who)
    # (-- if you do (wave 52A) -- a spell that was not countered is still on the stack: no card to cast, 601.2a)
    return [c for c in context.objects(plan, ctx, who[len(context.PREFIX):]) if getattr(plan.state.cards.get(c), "zone", "") != "stack"] if who.startswith(context.PREFIX) else []


def resume_free_cast(plan: Plan, d: Any, chosen: list[str]) -> None:
    """The spell chosen is cast now, while the ability is still resolving (608.2g); the resolution
    goes on once that cast is done (``free_cast_done``, from casting.cast_free) or abandoned
    (cancelled while paying: ``free_cast_abandoned``, from engine.settle)."""
    from app.game import actions as A
    from app.rules import effects
    from app.rules.casting import cast_spell

    ctx = d.resume["ctx"]
    e = d.resume.get("e") or {"n": 1}
    if not chosen:
        _free_cast_over(ctx, e)
        effects.continue_effects(plan, ctx)
        return
    r = plan.rules
    cid, _, at = chosen[0].partition("@")  # -- play now (wave 28A) -- "<card>@<face>": the face of a card with two
    face = int(at) if at else None
    if e.get("exact_refs") and cid not in _free_pool(plan, ctx, e):
        if free_cast(plan, ctx, e):
            effects.continue_effects(plan, ctx)
        return
    if not _effect_source_zone_ok(plan, ctx, e, plan.state.cards[cid], d.player):
        if free_cast(plan, ctx, e):
            effects.continue_effects(plan, ctx)
        return
    if not plan.in_game(plan.state.cards[cid]):  # (review 28A) its owner left the game while this was asked (800.4a): asked again without it
        if free_cast(plan, ctx, e):
            effects.continue_effects(plan, ctx)
        return
    if e.get("play") and chars.as_cast(plan.state.cards[cid], plan.info, face).is_land:
        play_land_now(plan, ctx, e, cid, face)
        return
    r.free_casts.append(cid)
    r.free_cast_then = {"card": cid, "ctx": ctx, "e": e, "suspend_object": None, **({"face": face} if face else {})}  # (face: review 28A, casting.cast_free checks it)
    prev = plan.actor
    plan.actor = d.player
    try:
        cast_spell(plan, A.CastSpell(card_id=cid, free=not bool(e.get("paid")), face=face))
    finally:
        plan.actor = prev


def free_cast_done(plan: Plan, card_id: str, *, cast: bool) -> None:
    """A free cast made during a resolution is over (cast, or abandoned): carry on resolving."""
    from app.rules import effects

    r = plan.rules
    pending = r.free_cast_then
    if pending is None or pending["card"] != card_id:
        return
    r.free_cast_then = None
    if (granted := pending.get("granted")) is not None:  # -- review (wave 29B) -- a cascade, discover, ripple, suspend, rebound, madness or
        if not cast:  # miracle cast (effects.resume_suspend_cast): its ability is over; a card not cast goes where the declined one goes
            effects.leave_uncast(plan, granted["player"], card_id, granted.get("decline"), granted.get("group") or ())
        if granted.get("ctx") is not None:  # -- free-cast cleanup (wave 30A) -- ripple (702.60a): the ability puts the revealed cards not cast on the bottom
            effects.continue_effects(plan, granted["ctx"])
        return
    ctx, e = pending["ctx"], pending["e"]
    if not cast:
        r.free_casts = [c for c in r.free_casts if c != card_id]
        if e.get("all") or (e.get('required') and not pending.get('required_unpayable')):
            if free_cast(plan, ctx, e):
                effects.continue_effects(plan, ctx)
            return
        _free_cast_over(ctx, e)
        effects.continue_effects(plan, ctx)
        return
    if e.get('mv_total') is not None:
        from app.rules.stack_interaction import mana_value

        card = plan.state.cards[card_id]
        ctx['free_cast_budget'] -= mana_value(card, plan.ch(card))
    ctx.setdefault("free_cast_done", []).append(card_id)
    if e.get("graveyard_destination") == "library_bottom":
        r.bottom_if_graveyard.append(plan.oid(card_id))
    if (e.get("exile_gy") and (e["exile_gy"] is True or plan.ch(plan.state.cards[card_id]).is_instant_or_sorcery)
            and (not e.get("exile_own") or plan.state.cards[card_id].owner == ctx["controller"])):  # (wave 25C: "your graveyard")
        r.exile_if_graveyard.append(plan.oid(card_id))  # "If that spell would be put into your graveyard, exile it instead" (614.1a; wave 19C: "an instant or sorcery spell" only)
    if e.get("all") or int(e.get("n", 1)) > 1:
        if free_cast(plan, ctx, e):  # (-- review 29D -- over: free_cast has said so once, _free_cast_over; a second call would read "If you
            effects.continue_effects(plan, ctx)  # do" as nothing cast, Smuggler's Buggy)
        return  # (else the next one is being chosen)
    _free_cast_over(ctx, e)
    effects.continue_effects(plan, ctx)


def free_cast_abandoned(plan: Plan) -> None:
    """After an intent (engine.settle): a free cast begun during a resolution that no longer waits
    for any choice and never reached the stack was cancelled (a payment cancelled: 601.2h, nothing
    was paid); the resolution goes on without it."""
    pending = plan.rules.free_cast_then
    if pending is None or plan.rules.decision is not None:
        return
    card = plan.state.cards.get(pending["card"])
    if card is not None and card.zone == STACK:
        free_cast_done(plan, pending["card"], cast=True)  # (defensive: it did reach the stack)
        return
    plan.note(f"{plan.name(pending['granted']['player'] if pending.get('granted') else pending['ctx']['controller'])} doesn't cast it")
    free_cast_done(plan, pending["card"], cast=False)


def rest_exiled(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """-- refused look/cast-free (wave 3R5) -- "Put the rest / the exiled cards not cast this way on
    the bottom of your library in a random order" / "… into your graveyard / hand": the cards an
    earlier instruction exiled that are still those objects in exile (400.7: the ones cast are on
    the stack now). A library is the card's owner's; "a random order" is the table's randomness,
    recorded as moves (replay is deterministic)."""
    from app.rules import context

    pid = ctx["controller"]
    who = str(e["who"])
    cards = [c for c in context.objects(plan, ctx, who[len(context.PREFIX):]) if plan.state.cards[c].zone.endswith(":exile")]
    if not cards:
        return True
    if e["to"] == "bottom_random":  # (-- review 30 -- one move per library: one move per card made the order readable, 401.4)
        from app.rules import effects

        by_owner: dict[str, list[str]] = {}
        for cid in cards:
            by_owner.setdefault(plan.state.cards[cid].owner, []).append(cid)
        for owner, group in by_owner.items():
            effects.bottom_at_random(plan, owner, group, actor=pid)
        return True
    for cid in cards:
        to = pid if e["to"] == "hand" else plan.state.cards[cid].owner
        plan.do({"type": "move", "card_ids": [cid], "to": {"player": to, "zone": e["to"]}}, actor=pid)
    return True
# -- end cast without paying (wave 3C) --

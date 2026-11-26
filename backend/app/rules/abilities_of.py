"""-- borrowed abilities (wave 18F) -- "has all activated abilities of …" (CR 113.10, 613.1f, 607.5).

"Necrotic Ooze has all activated abilities of all creature cards in all graveyards.", "Experiment Kraj has all activated abilities of each
other creature with a +1/+1 counter on it.", "Myr Welder has all activated abilities of all cards exiled with it.", "Sharkey has all
activated abilities of lands your opponents control except mana abilities.": a static (layer 6) gives the object a copy of each activated
ability of the objects its wording names, as they are now (611.3a: read again whenever characteristics are derived — an ability whose
object left is gone, a card that enters the graveyard brings its own).

* **The text.** An ability that names its object — "Sacrifice Foo", "this creature" — names the object that has it now (the reminder on
  Skill Borrower: "use this creature's name instead"): the lender's name and its "this creature" become "this permanent", read again on
  the borrower like any granted ability.
* **Numbering.** Each is numbered from its lender's object number (``BORROWED``), so it stays the same ability while the lender stays the
  object it is (400.7), and a lender that changes zones is a new object with new ones.
* **Linked abilities (607.5).** A lent ability that refers to cards exiled with its object ("exiled with this permanent", "the exiled card") is
  automated with its lending path's link scope (``link_scope``, ``scope_definition``; activated and triggered alike, and kept in the last known
  information of a borrower that left: granted.last_existed): it refers only to what an exiling ability lent by the same effect exiled — both
  halves lent together are linked as on the lender (Sisters of Stone Death on Marvin, Fiend Hunter on Koh), and a half lent alone refers to
  nothing (Quintorius on Marvin: no legal target), never to the borrower's own exiles. A lent ability that refers to a choice made by another
  ability (607.2d-f, 607.5a: "the chosen …", "noted") is lent but manual (``manual``), as is a modal ability ``modal_definition`` doesn't read.
  "A card named <name>" is a characteristic match, not a reference to the object (201.5, 201.5b): kept literal and read as written.
  Characteristics are read as the lender has them without the borrowing statics (a lender's own borrowed abilities: ``layers._T.depth``);
  abilities other statics grant it are lent as it has them (113.10, 613.1f: Tazri's and Katilda's quoted mana abilities).
* **Library top** (Conspicuous Snoop, Skill Borrower): the typed top-card reference is re-read for each derivation, so changing the top
  immediately changes the borrowed abilities. This form requires the card's public top-reveal line; hidden top-card lending stays unsupported.
* **Refused** (never guessed): sources the selector grammar doesn't read, cards in exile with counters ("Mairsil": each once a turn),
  and planeswalkers' loyalty abilities.
"""

from __future__ import annotations

import hashlib
import itertools
import json
import re
from dataclasses import replace
from typing import TYPE_CHECKING, Any, cast

from app.rules import selectors
from app.rules.oracle import AbilityText, parse_abilities, strip_reminders

if TYPE_CHECKING:
    from app.game.state import CardInstance
    from app.rules.characteristics import Characteristics
    from app.rules.layers import Static
    from app.rules.plan import Plan

BORROWED = 2_000_000  # above every other number an ability of an object is known by (granted.py INDEX_BASE …); bound: ActivateAbility.ability
STRIDE = 32  # legacy direct slots; additional/recursive abilities use provenance IDs

_SOURCE = re.compile(r"^all activated abilities of (?P<src>.+?)(?P<nomana> except mana abilities)?(?: except for loyalty abilities)?$")  # (loyalty abilities are never lent by ``_lent`` unless asked)
LOYALTY_ALL = "all loyalty abilities of all other planeswalkers on the battlefield"  # -- wave 110A -- Nicol Bolas, Dragon-God
_LINKED = re.compile(r"^(?:all |the )?(?P<what>(?:[\w\-]+ )*cards?) exiled with (?:it|this \w+|~)$")
_EXILED_CARD = re.compile(r"^the exiled card$")
# a lender's ability that refers to what another of its abilities did (607.2, 607.5), or names a card: lent, but manual (``manual``)
_LINKED_TEXT = re.compile(r"\bexiled with\b|\bthe exiled cards?\b|\bchosen\b|\bnoted\b|\bnamed\b", re.IGNORECASE)
# activated abilities that are keyword lines (113.1, 702): the ones that work from the battlefield
_ACTIVATED_KEYWORDS = frozenset({"equip", "crew", "outlast", "fortify", "reconfigure"})


def top_definition(text: str, ch: Characteristics) -> dict[str, Any] | None:
    """113.10 / 611.3a: borrow from the current qualifying, publicly revealed top card."""
    from app.rules.statics import _definition as definition

    m = re.fullmatch(r"As long as the top card of your library is an? (?P<what>[^,.]+) card, (?:~|this creature|this permanent) has all activated abilities of that card\.",
                     strip_reminders(text).strip(), re.IGNORECASE)
    if m is None or not any(a.text == "Play with the top card of your library revealed." for a in ch.abilities):
        return None
    sel = selectors.parse(m["what"] + " card")
    if sel is None or not sel.card or sel.player is not None or sel.zones or sel.controller or sel.owner or sel.extras:
        return None
    return definition("self", None, [], abilities_of={"top": True, "sel": sel.key(), "linked": False, "no_mana": False})


def parse(rest: str) -> dict[str, Any] | None:
    """The predicate "all activated abilities of <objects>" → {"sel": selector key | None, "linked": bool, "no_mana": bool}."""
    if rest == LOYALTY_ALL:  # loyalty abilities are lent like activated ones (113.10); each use counts for the borrower (606.3)
        return {"sel": selectors.parse("planeswalker").key(), "linked": False, "no_mana": True, "loyalty": True}  # type: ignore[union-attr]
    m = _SOURCE.match(rest)
    if m is None:
        return None
    src = m["src"]
    out: dict[str, Any] = {"sel": None, "linked": False, "no_mana": bool(m["nomana"])}
    if _EXILED_CARD.match(src):
        out["linked"] = True
        return out
    linked = _LINKED.match(src)
    if linked is not None:  # 607.2a: the cards the borrower's (or its source's) exiling ability put into exile
        sel = selectors.parse(linked["what"])
        if sel is None or sel.player is not None or not sel.card or sel.extras:
            return None
        out.update(linked=True, sel=None if linked["what"] in ("cards", "card") else replace(sel, zones=("exile",)).key())
        return out
    zone = "graveyard" if src.endswith(" in all graveyards") else None
    phrase = re.sub(r"^(?:all|each|the) ", "", re.sub(r" in all graveyards$| on the battlefield$", "", src))
    sel = selectors.parse(phrase)
    if sel is None or sel.player is not None or sel.either or sel.ability or sel.attacking or sel.blocking:
        return None
    if zone is not None:
        if not sel.card or sel.zones not in ((), ("graveyard",)) or sel.zone_owner or sel.controller or sel.owner:
            return None
        sel = replace(sel, zones=("graveyard",))
    elif sel.card:  # ("Elf cards in your graveyard": the selector grammar's own zone)
        if sel.zones not in (("graveyard",), ("exile",)) or any(not x.startswith("counter:") for x in sel.extras):  # (wave 50J: "cards in exile with brain counters on them", Rex)
            return None
    elif sel.zones != ("battlefield",):
        return None
    out["sel"] = sel.key()
    return out


# -- keyword inheritance (wave 25A) -- "As long as a card exiled with this creature has flying, this creature has flying. The same is true for
# fear, first strike, double strike, haste, landwalk, protection, and trample." (Death-Mask Duplicant, Urborg Scavengers, Eater of Virtue),
# "As long as a creature card with flying is in a graveyard, this creature has flying. The same is true for fear, …" (Cairn Wanderer): the
# subject has each listed keyword while some object of the set has it — read as lending those keyword abilities (113.10, 613.1f), the lender's own
# lines as it has them (a lender's protection is "protection from red": the subject gets that line; a landwalk, its own line).
INHERITED = frozenset({"flying", "fear", "first strike", "double strike", "deathtouch", "haste", "hexproof", "indestructible", "lifelink", "menace",
                       "reach", "trample", "vigilance", "shroud", "landwalk", "protection"})
_EXILED_SET = r"a card exiled with (?:~|this creature|it)"
_INHERIT = [re.compile(rf"^As long as (?P<set>{_EXILED_SET}) has (?P<k>[a-z ]+?), (?P<who>~|this creature|equipped creature) has (?P=k)\.$"),
            re.compile(rf"^(?P<who>~|This creature|Equipped creature) has (?P<k>[a-z ]+?) as long as (?P<set>{_EXILED_SET}) has (?P=k)\.$"),
            re.compile(r"^As long as (?P<set>a creature card with (?P<k>[a-z ]+?) is in a graveyard), (?P<who>~|this creature) has (?P=k)\.$"),
            # (wave 50J) Rayami, First of the Fallen
            re.compile(r"^As long as (?P<set>an exiled creature card with an? (?P<ctr>[a-z]+) counter on it) has (?P<k>[a-z ]+?), (?P<who>~|this creature) has (?P=k)\.$")]
_SAME = re.compile(r"^The same is true for (?P<ks>[a-z, ]+?)\.$")


def inherit(text: str, definition: Any) -> dict[str, Any] | None:
    """The static for "As long as <set> has K, <subject> has K. The same is true for K2, K3, and K4." (``definition``: statics._definition)."""
    parts = re.split(r"(?<=\.) (?=The same)", text.strip())
    if len(parts) != 2 or (same := _SAME.match(parts[1])) is None:
        return None
    for rx in _INHERIT:
        m = rx.match(parts[0])
        if m is not None:
            break
    else:
        return None
    keywords = [m["k"], *(k.strip() for k in re.split(r", and |, | and ", same["ks"]) if k.strip())]
    if not set(keywords) <= INHERITED:
        return None  # (e.g. "protection from any color": not read)
    attached = m["who"].lower() == "equipped creature"
    linked = m["set"].startswith("a card exiled with")
    ctr = m.groupdict().get("ctr")  # (wave 50J: "an exiled creature card with a blood counter on it", Rayami)
    sel = None if linked else selectors.parse(f"creature card in exile with a {ctr} counter on it" if ctr else "creature card in a graveyard")
    if not linked and (sel is None or sel.zones != (("exile",) if ctr else ("graveyard",))):
        return None
    found: dict[str, Any] = definition("attached" if attached else "self", "creature" if attached else None, [],
                                       abilities_of={"sel": sel.key() if sel is not None else None, "linked": linked, "no_mana": False,
                                                     "keywords": keywords})
    return found


def _keyword_lines(plan: Plan, lender: CardInstance, keywords: list[str]) -> list[AbilityText]:
    """-- keyword inheritance (wave 25A) -- the keyword lines of the lender among ``keywords`` (a landwalk: any "…walk" line)."""
    r = plan.state.rules
    assert r is not None
    out: list[AbilityText] = []
    for ab in plan.ch(lender).abilities:
        if ab.kind != "keywords":
            continue
        for kw in ab.keywords:
            # (-- review 38 -- 702.11e: a "hexproof from [quality]" line is a hexproof ability, lent as it is: Eater of Virtue ruling 2022-02-18)
            if kw in keywords or (kw.endswith("walk") and "landwalk" in keywords) or (kw == "hexproof from" and "hexproof" in keywords):
                out.append(replace(ab, keywords=(kw,), borrowed_origin=ab.borrowed_origin or
                                   (_origin_oid(plan, lender.id), str(ab.index), f"keyword:{kw}")))
    return out


def manual(ability: AbilityText) -> bool:
    """A lent ability refused outright: one that refers to a prior choice it doesn't make itself (607.5a: "the chosen …", "noted", "the named
    card"), or a modal form ``modal_definition`` didn't read. Exiled-with links are scoped instead (``scope_definition``)."""
    if ability.index < BORROWED:
        return False
    if "\n• " in ability.text:
        return True  # supported forms are handled by modal_definition before this guard
    return prior_choice(ability)


def prior_choice(ability: AbilityText) -> bool:
    """-- lent abilities -- a lent ability that refers to a choice or note another ability made (607.2d-e): the borrower's choice records are keyed
    on the object, not on the lending path, so the reference is refused rather than read from the borrower's own choices (607.5a: undefined).
    The effect of an activated ability is what follows its cost; a triggered ability's whole text is its effect (no colon: "When the chosen
    creature leaves …", Zenos yae Galvus; "sacrifice the chosen creature", Tyrannical Pitlord)."""
    if not ability.borrowed_origin and ability.index < BORROWED:
        return False
    body = ability.text.partition(":")[2] if ability.kind in ("activated", "mana", "loyalty") else ability.text
    choice = re.search(r"\bchosen\b|\bnoted\b|\bthe named card\b", body, re.I)
    own_choice = re.search(r"\bchoose\b|\bnote\b|\bname a card\b", body, re.I)
    return bool(choice and not own_choice)


# -- lent abilities -- the lent text names its object "this permanent" (``_lent``: the lender's name, 201.5b, and its "this creature"). Many readers
# match the lender's Oracle wording itself ("When this creature enters, …"), so a lent ability no reader knows as "this permanent" is read again as
# "this creature" — but only on a borrower that is a creature, where both words name the same object (113.10: the borrower has the ability itself).
# Refused there (kept manual) whatever a reader makes of it: text whose meaning on another object is unsettled — turning the object over (transform,
# convert, flip it: 701.27c, 701.28c, 710 — only a double-faced or flip card does; "flip a coin" is no such thing), "this card" (an ability that works
# from another zone, 113.6m), a branch on what kind of permanent the object is ("If it's an Aura, …"), craft materials (702.167c: the cards exiled to
# craft *this* permanent), an ability of the object in exile ("if this permanent is exiled": Cosima, 113.6). A linked or named wording
# (``_LINKED_TEXT``, "note") is not re-read either: conservative only — the lent reading itself still scopes such links (``scope_definition``).
# (``scripts._LENT`` marks the whole outer reading: another lent ability a reader defines meanwhile is read once, unscoped, and never re-read.)
_AS_CREATURE_REFUSED = re.compile(r"\b(?:transform|convert)(?:s|ed)?\b|\bflip(?:s|ped)? (?:this permanent|it)\b|\bthis card\b|"
                                  r"\bif it's an? (?:Aura|Equipment|Fortification|Vehicle)\b|\bcraft|\bthis permanent is exiled\b|\bnote\b|"
                                  + _LINKED_TEXT.pattern, re.IGNORECASE)


# -- lent abilities -- whatever reads it: a cost paid "as this permanent entered" (or was cast) is linked to the lender's own entering ability (607.2g,
# 607.2j), which isn't lent — on the borrower the cost is undefined (607.5a's reading for a choice; unsettled for a cost): manual
_UNSETTLED = re.compile(r"\bas this permanent (?:entered|was cast)\b", re.IGNORECASE)


def unsettled(ability: AbilityText) -> bool:
    """-- lent abilities -- a lent ability no reading may automate (``_UNSETTLED``)."""
    return bool(ability.borrowed_origin) and _UNSETTLED.search(ability.text) is not None


def as_creature(ability: AbilityText, ch: Characteristics) -> AbilityText | None:
    """-- lent abilities -- the lent ``ability`` with "this permanent" read as "this creature" (None: not lent, not a creature, or refused)."""
    if not ability.borrowed_origin or "Creature" not in ch.types or not re.search(r"\b[Tt]his permanent\b", ability.text) \
            or _AS_CREATURE_REFUSED.search(ability.text):
        return None
    text = re.sub(r"\b([Tt])his permanent\b", lambda m: f"{m[1]}his creature", ability.text)
    return replace(ability, text=text, cost=None if ability.cost is None else re.sub(r"\b([Tt])his permanent\b", lambda m: f"{m[1]}his creature", ability.cost))


def link_scope(ability: AbilityText) -> str | None:
    if not ability.borrowed_origin:
        return None
    if ability.borrowed_scope is not None:
        return ability.borrowed_scope
    # The final original ability slot differs between linked halves; their granting path is identical.
    return _scope_hash(ability.borrowed_origin[:-1])


def _scope_hash(origin: tuple[str, ...] | list[str]) -> str:
    return hashlib.sha256(json.dumps(origin, separators=(',', ':')).encode()).hexdigest()


def _origin_oid(plan: Plan, cid: str) -> str:
    card = plan.state.cards[cid]
    return f'{card.borrow_identity or cid}.{plan.rules.objects.get(cid, 0)}'


def _saved_scope(plan: Plan, borrower: str, origin: tuple[str, ...]) -> str | None:
    path = origin[:-1]
    # Initial hidden objects all had incarnation zero. Their old normalized hashes lost
    # donor identity and cannot be safely recovered from a saved registry.
    if any(re.search(r"\.0(?:$|[^0-9])", part) for part in path):
        return None
    legacy = _scope_hash([re.sub(r"[a-zA-Z0-9_-]+\.(\d+)", r"object.\1", part) for part in path])
    source = plan.rules.object_id(borrower)
    old = f'{source}|borrowed:{legacy}'
    new = f'{source}|borrowed:{_scope_hash(path)}'
    if old in plan.rules.exiled_with and new not in plan.rules.exiled_with:
        return legacy
    return None


# -- lent abilities -- every reader of an exile link (607.2a), by where its key comes from. A lent ability is scoped as a whole (``scope_definition``:
# its scope opener sets the resolution context's ``borrowed_link_scope``; the trigger's intervening "if" gets it too, triggers._add), so a reader keyed
# by ``exiled_with.link_key(ctx)`` — directly or through ``exiled_with.cards(plan, ctx)`` — reads only the lending path's record (607.5):
#   "ctx"     the resolution / condition context of the ability (scoped with the ability);
#   "scoped"  a key built with the lent ability's own scope (mana abilities, announcement-time targets, X);
#   "source"  keyed on the source object alone: a lent ability whose definition carries the marker of such a reader is refused (``SOURCE_KEYED``);
#   "not lent" readers for abilities a borrower never borrows (static abilities, cost and cast rules, planes, cipher) or the records' writers.
# tests/test_rules_lent_abilities.py scans app/rules for exile-link reads and fails on a reader missing here.
LINK_READERS: dict[str, str] = {
    "abilities_of._lenders": "not lent", "cast_limits._same_name_as_exiled": "not lent", "casting._resolve_options": "scoped",
    "conditional_prevention_effects.source_matches": "ctx", "conditional_prevention_effects.run": "ctx", "cost_changes.static_delta": "not lent",
    "cost_payment._candidates": "scoped", "counter_outcomes42.return_linked_source": "ctx", "defined_activation_x.evaluate": "scoped",
    "effects._cards": "ctx", "engine.leave_stack": "not lent", "exile_outcomes42.linked_grant": "ctx", "exile_outcomes42.lobelia_packet": "ctx",
    "exile_permission_sequences.bind_linked": "ctx", "exiled_with.linked_cards": "ctx", "exiled_with.link_key": "ctx", "exiled_with.record": "ctx",
    "exiled_with.cards": "ctx", "knowledge_pool78.run": "ctx", "linked_aggregates.current_pool": "ctx", "linked_exile_look.refresh": "ctx",
    "linked_owner_cast77.run": "ctx", "linked_play_grants.grant_pool": "ctx", "mana_esper_profiles.paid_cast": "ctx",
    "mana_foundry_profiles.linked_packet": "ctx", "mana_linked_profiles.linked_colorless": "ctx", "mana_noted_profiles.actual_exile": "ctx",
    "mana_noted_profiles.note_payment": "ctx", "mana_noted_profiles.output": "ctx", "name_event_receipts.linked_types": "ctx",
    "name_event_receipts.execute": "ctx", "name_relation_continuations.execute": "ctx", "name_relation_continuations.event_linked_name": "ctx",
    "permissions.grants": "scoped", "permissions.grant_play": "ctx", "pile_groups.pile_top_hand": "ctx", "planar_more3._matrix": "not lent",
    "pooled_casting_authorities71.stamp": "ctx", "recursion.resume_cipher": "not lent", "selectors._same_name_now": "source",
    "source_qualities.lines": "not lent", "static_conditions.holds": "not lent", "targets._legal_targets": "scoped",
    "token_copy_continuations.run": "ctx", "token_copy_outcomes.run": "scoped", "token_copy_sources.other_tokens": "ctx",
    "token_copy_sources.replace_vat_pool": "ctx", "triggers._cond_matches": "source", "triggers.exiled_with_watcher": "source",
    "triggers.dealt_combat_damage_to_player": "not lent", "values.evaluate": "ctx", "wave110a_restart.restart": "ctx",
    "wave110b_cards.destroy_created": "ctx", "wave110b_cards._linked": "ctx", "wave110c_koh._pool": "ctx", "wave110c_valki.valki_copy": "ctx",
    "wave110c_visionary.holds": "source", "wave110d_noted.output": "ctx", "wave110g_cards.shares_with_exiled": "ctx",
    "wave110g_cards.idol_cast": "ctx", "wave110g_cards.bind_linked": "ctx", "wave110m_cards.ashiok": "ctx", "wave110o_cards.exiled_mv": "ctx",
    "wave110o_cards.lore_bind": "ctx",
}
# the definition markers of the "source" readers (selectors._same_name_now's "samename_exiled_with"; triggers._cond_matches's "played_linked_name";
# triggers.exiled_with_watcher's "exiled_with110a"; wave110c_visionary.holds's "exiled_with110c"), and of the object-keyed choice records a lent
# ability can't be scoped to (607.2d, 607.5a: "picked110a" / "pair110a" chosen objects, "chosen_n" / "chosen_cmp" a chosen number)
SOURCE_KEYED = re.compile(r"samename_exiled_with|played_linked_name|exiled_with110a|exiled_with110c|picked110a|pair110a|chosen_n|chosen_cmp")


def source_keyed(d: dict[str, Any] | None) -> bool:
    """-- lent abilities -- does a lent ability's definition use a record keyed on the borrower itself (``SOURCE_KEYED``)? Then it stays manual."""
    return d is not None and SOURCE_KEYED.search(json.dumps(d, default=str)) is not None


def scope_definition(d: dict[str, Any] | None, ability: AbilityText) -> dict[str, Any] | None:
    scope = link_scope(ability)
    # -- lent abilities -- 607.5: a lent triggered ability is linked only to an exiling ability lent by the same effect, like an activated one —
    # never to the borrower's own exile record (Koh with Fiend Hunter's "return the exiled card", Skyclave Apparition's token, Living Lore's "cast
    # the exiled card": a reader that keys the link inside its handler, ``LINK_READERS``). Every lent one is scoped; its opener is read into the
    # context before the ability's own first instruction (effects._begin_resolution), so gates that read that instruction see it.
    if d is None or scope is None or d.get('kind') not in ('activated', 'triggered'):
        return d

    def rewrite(value: Any) -> Any:
        if isinstance(value, dict):
            return {k: rewrite(v) for k, v in value.items()}
        if isinstance(value, list):
            return [rewrite(v) for v in value]
        return f'borrowed_exiled|{scope}|{value}' if isinstance(value, str) and (value in ('exiled_with', 'spell_name_exiled_with') or value.startswith('exiled_with:')) else value

    # Only selectors need an explicit scope before announcement. Resolution uses
    # a saved context instruction, including every modal branch independently.
    out = {**d}
    for k in ('target', 'targets'):
        if k in out:
            out[k] = rewrite(out[k])
    prefix = {'do': 'borrowed_link_scope', 'scope': scope}
    if d.get('modes'):
        out['modes'] = [{**m, 'target': rewrite(m.get('target')),
                         **({'groups': rewrite(m['groups'])} if m.get('groups') else {}),
                         'effects': [prefix, *m['effects']]} for m in d['modes']]
    else:
        out['effects'] = [prefix, *d.get('effects', [])]
    return out


def modal_definition(ability: AbilityText, ch: Characteristics) -> dict[str, Any] | None:
    if not ability.borrowed_origin or "\n• " not in ability.text:
        return None
    from app.rules import modal_abilities

    lines = parse_abilities(ability.text)
    if not lines:
        return None
    # Reuse the native modal grammar. Temporary small indices prevent its mode
    # stubs from overlapping another real inherited ability's public identity.
    virtual = replace(ch, abilities=tuple(lines))
    d = modal_abilities.definitions(lines[0], virtual).get(lines[0].index)
    if d is None or "modal" not in d:  # -- lent abilities -- (a reflexive "When you do, choose one —" reads its modes elsewhere: lent, it stays manual)
        return None
    return {**d, 'modal': {**d['modal'], 'index': ability.index}}  # (-- lent abilities -- scoped by scripts.define, once)


def _lent(plan: Plan, lender: CardInstance, no_mana: bool, loyalty: bool = False, triggered: bool = False) -> list[AbilityText]:
    from app.rules import scripts

    ch = plan.ch(lender)
    r = plan.state.rules
    assert r is not None

    def own(text: str) -> str:
        text = scripts.self_text(text, ch.name)
        return re.sub(r"(^|: |\. )~", r"\1This permanent", text).replace("~", "this permanent")

    out: list[AbilityText] = []
    for i, ab in enumerate(ch.abilities):
        keyword = ab.kind == "keywords" and len(ab.keywords) == 1 and ab.keywords[0] in _ACTIVATED_KEYWORDS
        if loyalty != (ab.kind == "loyalty") or not (ab.kind in ("activated", "loyalty") or (ab.kind == "mana" and not no_mana) or keyword or (triggered and ab.kind == "triggered")):  # (wave 110C: Koh, "activated and triggered")
            continue
        found = parse_abilities(ab.text if keyword else own(ab.text))
        if found and ab.kind == "mana" and found[0].kind == "activated":
            # -- lent abilities -- 605.1a: a mana ability by what it is, whatever the lent wording parses as ("For each color among the exiled cards
            # used to craft this permanent, add …", Sunbird Effigy): lent as the lender's mana ability, read by the mana grammar (or manual)
            found = [replace(found[0], kind="mana"), *found[1:]]
        if not found or found[0].kind != ab.kind or any(not x.text.startswith('• ') for x in found[1:]):
            continue
        tail = list(itertools.takewhile(lambda x: x.text.startswith('• '), ch.abilities[i + 1:])) if len(found) == 1 else []
        modes = [x.text for x in found[1:]] + [own(x.text) for x in tail]
        next_at = i + 1 + len(tail)
        if modes and len(found) == 1 and next_at < len(ch.abilities) and re.match(r'^(?:This ability|Activate\b|Do this only)', ch.abilities[next_at].text):
            modes.append(own(ch.abilities[next_at].text))  # retain an unsupported native trailer rather than dropping a restriction
        line = replace(found[0], text="\n".join([found[0].text, *modes])) if modes else found[0]
        out.append(replace(line, borrowed_origin=ab.borrowed_origin or (_origin_oid(plan, lender.id), str(ab.index))))
    return out


def _lenders(plan: Plan, st: Static) -> list[CardInstance]:
    """The abilities the static ``st`` lends ``borrower`` right now, numbered (``BORROWED``)."""
    d = st.definition["abilities_of"]
    state, r = plan.state, plan.state.rules
    if r is None:
        return []
    sel = selectors.from_key(d["sel"]) if d["sel"] else None
    if d.get("chosen110c"):  # -- wave 110C -- Koh: "the last chosen card", the object recorded as Koh's choice (400.7: a card that left exile is another object)
        from app.rules import wave110c_koh

        return [state.cards[c] for c in wave110c_koh.last_chosen(state, st.source)]
    if d.get("top"):
        # Re-read after every change of top card. A library position is not an
        # object reference that can stay bound to the former card (401.5, 611.3a).
        top = state.zones.get(f"{st.controller}:library", [])[:1]
        lenders = [state.cards[c] for c in top if sel is not None and
                   selectors.matches(plan, sel, state.cards[c], plan.ch(state.cards[c]), st.controller, st.source)]
    elif d.get("objects"):  # -- (wave 110D) -- a resolved effect's fixed lender (611.2c: the object chosen as it resolved), while it is still that battlefield object
        lenders = [c for c in state.cards.values() if c.zone.endswith(":battlefield") and r.object_id(c.id) in d["objects"]]
    elif d.get("crafted"):  # -- (wave 110D) -- "the exiled cards used to craft it" (702.167c, The Enigma Jewel): the materials still the exiled objects
        found = [state.cards[ref.card] for ref in r.crafted_materials.get(r.object_id(st.source), []) if ref.card in state.cards
                 and state.cards[ref.card].zone.endswith(":exile") and r.object_id(ref.card) == ref.object_id]
        lenders = [c for c in found if sel is None or selectors.matches(plan, sel, c, plan.ch(c), st.controller, st.source)]
    elif d["linked"]:
        found = [state.cards[cid] for oid in r.exiled_with.get(r.object_id(st.source), []) if (cid := oid.rsplit(".", 1)[0]) in state.cards
                 and state.cards[cid].zone.endswith(":exile") and r.object_id(cid) == oid]
        lenders = [c for c in found if sel is None or selectors.matches(plan, sel, c, plan.ch(c), st.controller, st.source)]
    else:
        assert sel is not None
        lenders = [state.cards[c] for c in selectors.candidates(plan, sel, st.controller, st.source)]
    return sorted(lenders, key=lambda c: r.objects.get(c.id, 0))


class _GraphView:
    def __init__(self, plan: Plan, chars: dict[str, Characteristics]) -> None:
        self.plan, self.chars = plan, chars

    def __getattr__(self, name: str) -> Any:
        return getattr(self.plan, name)

    def ch(self, card: CardInstance) -> Characteristics:
        return self.chars.get(card.id) or self.plan.ch(card)


def _dependency_order(deps: dict[int, set[int]], timestamps: dict[int, tuple]) -> list[int]:
    """613.8: dependencies first; within a dependency loop apply timestamp order once."""
    finished: list[int] = []
    visited: set[int] = set()
    for root in sorted(deps, key=timestamps.__getitem__):
        if root in visited:
            continue
        visited.add(root)
        stack = [(root, iter(sorted(deps[root], key=timestamps.__getitem__)))]
        while stack:
            v, children = stack[-1]
            w = next(children, None)
            if w is None:
                finished.append(v)
                stack.pop()
            elif w not in visited:
                visited.add(w)
                stack.append((w, iter(sorted(deps[w], key=timestamps.__getitem__))))
    reverse: dict[int, set[int]] = {v: set() for v in deps}
    for v, adjacent in deps.items():
        for w in adjacent:
            reverse[w].add(v)
    groups: list[list[int]] = []
    assigned: set[int] = set()
    for root in reversed(finished):
        if root in assigned:
            continue
        group, todo = [], [root]
        assigned.add(root)
        while todo:
            v = todo.pop()
            group.append(v)
            for w in reverse[v]:
                if w not in assigned:
                    assigned.add(w)
                    todo.append(w)
        groups.append(sorted(group, key=timestamps.__getitem__))
    return [v for group in reversed(groups) for v in group]


def _graph(plan: Plan) -> dict[tuple[str, int], list[AbilityText]]:
    from app.rules import layers

    r = plan.state.rules
    assert r is not None
    capture: dict[str, list[Static]] = {}
    old_depth, old_capture = layers._T.depth, layers._T.borrow_capture
    layers._T.depth, layers._T.borrow_capture = 0, capture
    try:
        # Each outer derivation includes normal static grants and losses. Borrowing
        # alone is suppressed while collecting the dependency graph's initial state.
        chars = {c.id: plan.ch(c) for c in plan.state.cards.values() if c.zone.endswith(':battlefield')}
        table = layers.statics(plan.state, plan.info)
        views = cast("Plan", _GraphView(plan, chars))
        nodes: list[tuple[str, Static, list[CardInstance], str]] = []
        source_slots: dict[str, int] = {}
        static_keys: dict[int, str] = {}
        for st in table:
            if st.definition.get('abilities_of'):
                slot = source_slots.get(st.source, 0)
                source_slots[st.source] = slot + 1
                static_keys[id(st)] = f'{_origin_oid(plan, st.source)}:{slot}'
        for cid, edges in list(capture.items()):
            for st in edges:
                key = static_keys.get(id(st)) or f'{_origin_oid(plan, st.source)}:{json.dumps(st.definition, sort_keys=True)}'
                lenders = [c for c in _lenders(views, st) if c.id != cid and (not c.face_down or c.zone.endswith(':battlefield'))]
                for lender in lenders:
                    if lender.id not in chars:
                        chars[lender.id] = plan.ch(lender)
                nodes.append((cid, st, lenders, key))
        dependencies = {i: {j for j, other in enumerate(nodes) if any(c.id == other[0] for c in node[2])}
                        for i, node in enumerate(nodes)}
        order = _dependency_order(dependencies, {i: (node[1].seq, node[3], r.object_id(node[0])) for i, node in enumerate(nodes)})
        result: dict[tuple[str, int], list[AbilityText]] = {}
        for i in order:
            cid, st, lenders, key = nodes[i]
            d = st.definition['abilities_of']
            lines = []
            for lender in lenders:
                lent = _keyword_lines(views, lender, d['keywords']) if d.get('keywords') else _lent(views, lender, d['no_mana'], bool(d.get('loyalty')), bool(d.get('triggered')))
                for k, ab in enumerate(lent):
                    origin = (_origin_oid(plan, cid), key, _origin_oid(plan, lender.id), *(ab.borrowed_origin or (str(ab.index),)))
                    # Preserve the original direct-slot representation where it cannot
                    # alias another lender. Richer paths use a separate JS-safe range.
                    direct = len(ab.borrowed_origin) <= 2 and k < STRIDE
                    idx = BORROWED + STRIDE * r.objects.get(lender.id, 0) + k if direct else _provenance_index(origin)
                    if d.get("once"):  # -- (wave 110D) -- "You may activate each of those abilities only once each turn." (602.5b: each is its own ability)
                        ab = replace(ab, text=f"{ab.text} Activate only once each turn.")
                    lines.append(replace(ab, index=idx, borrowed_origin=origin, borrowed_scope=_saved_scope(plan, cid, origin),
                                         borrowed_color=r.object_id(cid) if d.get('spend_color') else None))
            result[(cid, id(st))] = lines
            chars[cid] = replace(chars[cid], abilities=chars[cid].abilities + tuple(lines))
        # Never silently alias two different granting paths, including unusually
        # large ability sets. Allocation is deterministic and confined to one object.
        for cid in chars:
            allocated: dict[int, tuple[str, ...]] = {}
            for where in sorted((x for x in result if x[0] == cid), key=lambda x: tuple(a.borrowed_origin for a in result[x])):
                fixed = []
                for ab in result[where]:
                    idx = ab.index
                    if idx in allocated and allocated[idx] != ab.borrowed_origin:
                        idx = _provenance_index(ab.borrowed_origin)
                    while idx in allocated and allocated[idx] != ab.borrowed_origin:
                        idx = _PROVENANCE_BASE + (idx - _PROVENANCE_BASE + 1) % _PROVENANCE_SIZE
                    allocated[idx] = ab.borrowed_origin
                    fixed.append(replace(ab, index=idx))
                result[where] = fixed
        return result
    finally:
        layers._T.depth, layers._T.borrow_capture = old_depth, old_capture


_PROVENANCE_BASE = 1 << 40
_PROVENANCE_SIZE = (1 << 52) - _PROVENANCE_BASE


def _provenance_index(origin: tuple[str, ...]) -> int:
    raw = json.dumps(origin, separators=(',', ':'), ensure_ascii=True).encode()
    return _PROVENANCE_BASE + int.from_bytes(hashlib.sha256(raw).digest()[:8], 'big') % _PROVENANCE_SIZE


def collect(plan: Plan, st: Static, borrower: CardInstance) -> list[AbilityText]:
    from app.rules import layers

    if layers._T.borrow_graph is None:
        layers._T.borrow_graph = _graph(plan)
    return layers._T.borrow_graph.get((borrower.id, id(st)), [])

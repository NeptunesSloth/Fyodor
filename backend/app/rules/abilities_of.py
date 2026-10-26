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
* **Linked abilities (607.5).** A lender's ability that refers to a choice or to cards exiled with it (its linked half may be elsewhere),
  or to a card by name (201.5b vs "a card named …"), is lent but never automated (``manual``): it would link to the wrong thing. A modal
  ability is lent with its modes (shown) and is manual too. Characteristics are read as the lender has them without other statics (a lender's own
  borrowed abilities, an Aura's grants: ``layers._T.depth``), so a lender's abilities from other statics aren't lent either.
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
    """Refuse only unresolved prior choices, or unsupported modal forms."""
    if ability.index < BORROWED:
        return False
    if "\n• " in ability.text:
        return True  # supported forms are handled by modal_definition before this guard
    body = ability.text.partition(":")[2]
    prior_choice = re.search(r"\bchosen\b|\bnoted\b|\bthe named card\b", body, re.I)
    own_choice = re.search(r"\bchoose\b|\bnote\b|\bname a card\b", body, re.I)
    return bool(prior_choice and not own_choice)


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


def scope_definition(d: dict[str, Any] | None, ability: AbilityText) -> dict[str, Any] | None:
    scope = link_scope(ability)
    if d is None or scope is None or d.get('kind') != 'activated':
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
    if d is None:
        return None
    return scope_definition({**d, 'modal': {**d['modal'], 'index': ability.index}}, ability)


def _lent(plan: Plan, lender: CardInstance, no_mana: bool, loyalty: bool = False) -> list[AbilityText]:
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
        if loyalty != (ab.kind == "loyalty") or not (ab.kind in ("activated", "loyalty") or (ab.kind == "mana" and not no_mana) or keyword):
            continue
        found = parse_abilities(ab.text if keyword else own(ab.text))
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
    if d.get("top"):
        # Re-read after every change of top card. A library position is not an
        # object reference that can stay bound to the former card (401.5, 611.3a).
        top = state.zones.get(f"{st.controller}:library", [])[:1]
        lenders = [state.cards[c] for c in top if sel is not None and
                   selectors.matches(plan, sel, state.cards[c], plan.ch(state.cards[c]), st.controller, st.source)]
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
                lent = _keyword_lines(views, lender, d['keywords']) if d.get('keywords') else _lent(views, lender, d['no_mana'], bool(d.get('loyalty')))
                for k, ab in enumerate(lent):
                    origin = (_origin_oid(plan, cid), key, _origin_oid(plan, lender.id), *(ab.borrowed_origin or (str(ab.index),)))
                    # Preserve the original direct-slot representation where it cannot
                    # alias another lender. Richer paths use a separate JS-safe range.
                    direct = len(ab.borrowed_origin) <= 2 and k < STRIDE
                    idx = BORROWED + STRIDE * r.objects.get(lender.id, 0) + k if direct else _provenance_index(origin)
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

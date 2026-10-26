"""CR 702.22c-k: declared attacking bands, shared blocks, and damage-assignment control."""
from __future__ import annotations

import re
from functools import lru_cache
from typing import TYPE_CHECKING, Any

from app.game import actions as A
from app.game.errors import ActionError
from app.game.state import CardInstance, GameState

if TYPE_CHECKING:
    from app.rules.plan import Plan
    from app.rules.selectors import Selector


def validate(plan: Plan, a: A.DeclareAttackers, *, locked: bool = False) -> None:
    declared = {x.card_id: x.target for x in a.attackers}
    seen: set[str] = set()
    for band in a.bands:
        if not band or len(set(band)) != len(band) or any(c not in declared or c in seen for c in band):
            raise ActionError("Each band must contain distinct declared attackers, each in only one band")
        if len({declared[c] for c in band}) != 1:
            raise ActionError("Creatures in a band must attack the same player, planeswalker, or battle")
        # 508.1g-j: a declaration already validated before its attack-cost mana window
        # stays a band if a mana ability removes banding while those costs are paid.
        if not locked:
            count = sum("banding" in plan.ch(plan.state.cards[c]).keywords for c in band)
            ordinary = count > 0 and len(band) - count <= 1
            if not ordinary and not compatible(plan, [plan.state.cards[c] for c in band]):
                raise ActionError("A band needs compatible banding abilities and qualifying creatures")
        seen.update(band)


def remember(plan: Plan, bands: list[list[str]]) -> None:
    plan.rules.attacking_bands = [[plan.oid(c) for c in band] for band in bands]
    for band in bands:
        plan.note("Attacking band: " + ", ".join(plan.state.cards[c].name or "Creature" for c in band), band)


def live_bands(state: GameState) -> list[list[str]]:
    if state.rules is None:
        return []
    out = []
    for band in state.rules.attacking_bands:
        members = []
        for oid in band:
            cid = oid.rsplit(".", 1)[0]
            card = state.cards.get(cid)
            if (card is not None and card.zone.endswith(":battlefield") and card.is_attacking
                    and state.rules.object_id(cid) == oid):
                members.append(cid)
        if members:
            out.append(members)
    return out


def prune(state: GameState) -> None:
    if state.rules is not None:
        state.rules.attacking_bands = [[state.rules.object_id(c) for c in band] for band in live_bands(state)]


def members(state: GameState, card_id: str) -> list[str]:
    return next((band for band in live_bands(state) if card_id in band), [card_id])


def expand_blocks(plan: Plan, blocks: list[A.BlockDeclaration]) -> list[A.BlockDeclaration]:
    found: dict[tuple[str, str], A.BlockDeclaration] = {}
    for block in blocks:
        for cid in members(plan.state, block.attacker_id):
            key = (block.blocker_id, cid)
            found.setdefault(key, A.BlockDeclaration(blocker_id=block.blocker_id, attacker_id=cid))
    return list(found.values())


def damage_chooser(plan: Plan, source: CardInstance, opposing: list[CardInstance]) -> str:
    """702.22j-k: current banding changes the chooser, independently of declared bands."""
    from app.rules import (
        wave110j_final,  # -- Defensive Formation (wave 110J) -- the defender assigns everything
    )

    if (formation := wave110j_final.assigner(plan, source)) is not None:
        return formation
    bander = next((c for c in opposing if "banding" in plan.ch(c).keywords), None)
    if bander is not None:
        return bander.controller
    for holder in opposing:
        for q in qualities(plan, holder):
            if matches(plan, q, holder) and any(other.id != holder.id and matches(plan, q, other) for other in opposing):
                return holder.controller
    return source.controller


# A qualified form is its own keyword key. Different qualities remain independent
# when a later timestamp removes or grants one of them (CR 702.22m / 613.7).
OTHER = "bands with other"


@lru_cache(maxsize=512)
def quality(text: str) -> Selector | None:
    from app.rules import selectors

    value = text.strip().rstrip('.').casefold()
    if not value.startswith(OTHER + ' '):
        return None
    phrase = value[len(OTHER) + 1:]
    if phrase == 'legendary creatures':
        return selectors.parse(phrase)
    if phrase.startswith('creatures named ') and (name := phrase[len('creatures named '):].strip()):
        return selectors.Selector(types=("Creature",), extras=("name:" + name,))
    return None


@lru_cache(maxsize=1024)
def parameter_keywords(text: str) -> frozenset[str]:
    """The full qualified keyword keys in one quoted/granted ability text."""
    if OTHER not in text.casefold():
        return frozenset()
    from app.rules.oracle import parse_abilities

    return frozenset(k for ab in parse_abilities(text) for k in ab.keywords if quality(k) is not None)


def qualities(plan: Plan, card: CardInstance) -> list[Selector]:
    return [q for k in sorted(plan.ch(card).keywords) if (q := quality(k)) is not None]


def matches(plan: Plan, q: Selector, card: CardInstance) -> bool:
    from app.rules import selectors

    return selectors.matches(plan, q, card, plan.ch(card), card.controller, None)


def compatible(plan: Plan, creatures: list[CardInstance]) -> bool:
    return any(all(matches(plan, q, member) for member in creatures)
               for holder in creatures for q in qualities(plan, holder))


def declaration_options(plan: Plan, eligible: list[str]) -> dict[str, Any]:
    from app.rules import selectors

    qualified: dict[str, dict[str, Any]] = {}
    for cid in eligible:
        holder = plan.state.cards[cid]
        for q in qualities(plan, holder):
            if not matches(plan, q, holder):
                continue
            entry = qualified.setdefault(q.key(), {"holders": [], "members": [], "description": 'legendary creatures' if 'Legendary' in q.supertypes else 'creatures with the same name'})
            entry['holders'].append(cid)
    for key, entry in qualified.items():
        q = selectors.from_key(key)
        entry['members'] = [cid for cid in eligible if matches(plan, q, plan.state.cards[cid])]
    return {"kind": "attackers", "banding": [cid for cid in eligible if 'banding' in plan.ch(plan.state.cards[cid]).keywords],
            "band_qualities": list(qualified.values())}


def parse_loss(body: str) -> tuple[list[dict[str, Any]], str, bool] | None:

    m = re.fullmatch(r'target creature loses (?P<ordinary>banding and )?all "bands with other" abilities until end of turn\.', body.strip(), re.I)
    if m is None:
        return None
    return [{"do": "grant", "who": "target", "keywords": [],
             "remove": [*(['banding'] if m['ordinary'] else []), OTHER]}], 'creature', False


def companions(plan: Plan, ctx: dict[str, Any]) -> list[str]:
    """CR 608.2h: a source's current band, or its last known band if it left its expected zone."""
    cid, oid = ctx.get("source_card"), ctx.get("source_object")
    source = plan.state.cards.get(cid or "")
    if source is not None and source.zone.endswith(":battlefield") and plan.oid(source) == oid:
        return [c for c in members(plan.state, source.id) if c != source.id and plan.ch(plan.state.cards[c]).is_creature]
    snap = plan.rules.lki.get(oid or "")
    if snap is None:
        return []
    out = []
    for member_oid in snap.banded_with_ids:
        card = plan.state.cards.get(member_oid.rsplit(".", 1)[0])
        if (card is not None and card.zone.endswith(":battlefield") and card.is_attacking
                and plan.oid(card) == member_oid and plan.ch(card).is_creature):
            out.append(card.id)
    return out

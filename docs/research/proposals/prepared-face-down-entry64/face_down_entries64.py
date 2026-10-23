"""Native entry descriptors for cards an instruction puts onto the battlefield face down."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.game.errors import ActionError

if TYPE_CHECKING:
    from app.game.state import CardInstance
    from app.rules.plan import Plan

KEY = 'face_down_entry64'


def probe(plan: Plan, card: CardInstance, entry: dict[str, Any]) -> CardInstance:
    form = entry.get(KEY)
    if form is None:
        return card
    actual = plan.state.cards.get(card.id)
    if actual is None or plan.oid(actual) != form.get('object') or actual.zone != form.get('zone'):
        raise ActionError('A selected face-down entry is no longer its original object')
    return card.model_copy(update={'face_down': True, 'face_down_kind': form['kind'], 'face_down_as': form['spec']})


def validate(plan: Plan, entries: list[dict[str, Any]]) -> None:
    for entry in entries:
        if KEY not in entry:
            continue
        card = plan.state.cards.get(entry['card'])
        if card is not None and (card.owner not in plan.live() or entry['player'] not in plan.live()):
            entry['stays'] = True  # 800.4a: departed players' cards remain table records only.
            continue
        if card is None:
            raise ActionError('A selected face-down entry is no longer its original object')
        probe(plan, card, entry)


def payload(entries: list[dict[str, Any]], move: dict[str, Any]) -> None:
    forms = [entry.get(KEY) for entry in entries]
    if not any(forms):
        return
    if not all(forms) or len({(form['kind'], form['spec']) for form in forms if form}) != 1:
        raise ActionError('Mixed face-down entry forms require a prepared native move')
    form = forms[0]
    assert form is not None
    move.update(face_down=True, face_down_kind=form['kind'], face_down_as=form['spec'])


def prepare(plan: Plan, cards: list[str], controller: str, *, under_you: bool, spec: str | None = None, tapped: bool = False) -> list[dict[str, Any]]:
    return [{'card': cid, 'player': controller if under_you else plan.state.cards[cid].owner,
             'actor': controller, 'tapped': tapped,
             KEY: {'object': plan.oid(cid), 'zone': plan.state.cards[cid].zone,
                   'kind': 'generic', 'spec': spec}} for cid in cards]

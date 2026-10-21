"""CR 608.2c/h, 701.23: exile LKI, private searches, then one entry batch."""
from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan

_WINDS = re.compile(r'^(?P<exile>Exile (?:target|each) .+?)\. For each (?P<what>.+?) exiled this way, '
                    r'its controller searches their library for a basic land card\. '
                    r'Those players put those cards onto the battlefield tapped, then shuffle\.$')
_SETTLE = re.compile(r'^(?P<exile>Exile .+? target player controls)\. That player may search their library for that many '
                     r'basic land cards, put those cards onto the battlefield tapped, then shuffle\.$')
_KEY = 'exile_land_compensation'
_BIND = 'compensated_exile'


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    from app.rules import scripts, selectors

    text = ' '.join(body.split())
    m = _WINDS.fullmatch(text) or _SETTLE.fullmatch(text)
    if m is None:
        return None
    optional = _SETTLE.fullmatch(text) is not None
    exile = scripts.parse_effects(m['exile'] + '.')
    search = scripts.parse_effects('Search your library for a basic land card and put it onto the battlefield tapped.')
    selected = selectors.parse('creature' if optional else m['what'])
    if (exile is None or exile[2] or len(exile[0]) != 1 or exile[0][0].get('do') != 'exile'
            or search is None or len(search[0]) != 1 or search[0][0].get('do') != 'search'
            or selected is None or selected.card or selected.player or selected.zones != ('battlefield',)):
        return None
    return ([{**exile[0][0], 'as': _BIND},
             {'do': 'exile_land_compensation', 'count': {'this_way': 'exiled', 'of': selected.key(), 'ref_count': _BIND},
              'optional_player': 'target' if optional else None,
              'search': {**search[0][0], 'shuffle': False}}], exile[1], False)


def collect(plan: Plan, ctx: dict[str, Any], key: str, pid: str, entering: list[dict[str, Any]]) -> None:
    """Called after native search applied replacement and player-control effects."""
    job = ctx.setdefault('_deferred_searches', {}).setdefault(key, {'entries': [], 'searched': [], 'mandatory': []})
    if pid not in job['searched']:
        job['searched'].append(pid)
    job['entries'].extend({**entry, '_search_oid': plan.oid(entry['card'])} for entry in entering)


def begin(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import effects, this_way

    counts = this_way.by_controller(plan, ctx, e['count'])
    optional = e.get('optional_player') is not None
    if optional:
        counts = {pid: counts.get(pid, 0) for pid in effects._players(plan, ctx, e['optional_player'])}
    players = [pid for pid in plan.apnap() if pid in counts]
    ctx.setdefault('_deferred_searches', {})[_KEY] = {'entries': [], 'searched': [], 'mandatory': [] if optional else players}
    # A per-creature search is a separate search event (Ob Nixilis), whereas
    # 'search for that many cards' is one search. All entry/shuffle waits below.
    work = [{'do': 'prepare_compensation_search', 'key': _KEY,
             'search': {**e['search'], 'who': f'player:{pid}', 'max': counts[pid] if optional else 1, 'may': optional,
                        'label': 'basic land card' if not optional or counts[pid] == 1 else 'basic land cards',
                        'defer_entries': _KEY}}
            for pid in players for _ in range(1 if optional else counts[pid])]
    work += [{'do': 'enter_deferred_searches', 'key': _KEY}, {'do': 'shuffle_deferred_searches', 'key': _KEY}]
    at = ctx['next']
    ctx['effects'] = [*ctx['effects'][:at], *work, *ctx['effects'][at:]]
    return True


def prepare_search(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import selectors

    search = dict(e['search'])
    sel = selectors.from_key(search['sel'])
    reserved = ctx.get('_deferred_searches', {}).get(e['key'], {}).get('entries', [])
    # Found cards stay in their library until the later simultaneous put. They
    # cannot be found again, and still occupy their positions for Mindcensor.
    search['sel'] = selectors.replace(sel, extras=(*sel.extras, *(f"not_oid:{x['_search_oid']}" for x in reserved))).key()
    at = ctx['next']
    ctx['effects'] = [*ctx['effects'][:at], search, *ctx['effects'][at:]]
    return True


def enter(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import attachments

    job = ctx.get('_deferred_searches', {}).get(e['key'], {})
    entries = []
    for entry in job.get('entries', []):
        card = plan.state.cards.get(entry['card'])
        if (card is not None and plan.oid(card) == entry['_search_oid'] and card.zone.endswith(':library')
                and entry['player'] in plan.live()):
            entries.append({k: v for k, v in entry.items() if k != '_search_oid'})
    return not entries or attachments.enter(plan, entries, ctx)


def shuffle(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import effects

    job = ctx.get('_deferred_searches', {}).pop(e['key'], {})
    players = set(job.get('mandatory', [])) | set(job.get('searched', []))
    for pid in plan.apnap():
        if pid in players:
            effects.shuffle_library(plan, ctx, {'do': 'shuffle_library', 'who': f'player:{pid}'})
    return True


PRIMITIVES = {'exile_land_compensation': begin, 'prepare_compensation_search': prepare_search,
              'enter_deferred_searches': enter, 'shuffle_deferred_searches': shuffle}

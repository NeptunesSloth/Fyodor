"""-- untap choice (wave 7F) -- "You may choose not to untap ~ during your untap step." (Hollow Trees, Rubinia
Soulsinger, Vedalken Shackles, Amber Prison …).

502.3: the active player determines which permanents untap; a static ability can let them choose not to untap
some. The choice is made during the untap step, where no player receives priority (502.4), so it is a
decision asked of the new active player right after the turn changes and before anything untaps: the engine
keeps the permanents that have the ability and are tapped, controlled by that player, tapped for the turn
change, asks which to keep tapped (none picked: all untap) and untaps the rest. The static is the rule
``may_stay_tapped`` (app/rules/statics.py); a permanent that stays tapped for another reason (exerted, "doesn't
untap", a skipped untap step) isn't asked. 122.1d: a stunned permanent that would untap loses a stun counter
instead, so one that is kept tapped keeps its counter.
"""

from __future__ import annotations

import re
from typing import Any

from app.game.rules_state import DecisionOption
from app.rules import scripts
from app.rules.plan import Plan, decide

# "Tap target creature. It doesn't untap during its controller's untap step for as long as ~ remains tapped." (611.2b):
# a rule-modifying restriction (``doesnt_untap``, read by engine._keep_tapped) that lasts while the source stays tapped.
_HOLD = re.compile(r"^(?P<o>.+?) (?:doesn't untap during its controller's untap step|don't untap during their controllers' untap steps) for as long as "
                   r"(?P<d>~ remains tapped|you control ~|~ remains on the battlefield)$")  # (wave 25A: plural; "remains on the battlefield")
# -- as long as (wave 9B) -- "… for as long as you control ~" (Ty Lee, Icefall Regent, Dungeon Geists): 611.2b, ends when
# the source leaves the battlefield or another player controls it (delayed.py "source_controlled")
_DURATION = {"~ remains tapped": "source_tapped", "you control ~": "source_controlled", "~ remains on the battlefield": "source_on_battlefield"}


def _hold(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    from app.rules import language

    try:
        kind, key, group = language.ref(m["o"])
    except language._Fail:
        raise scripts._NoMatch from None
    if kind not in ("it", "them", "target", "self"):  # (a named object: 611.2c, a mass wording would be a set)
        raise scripts._NoMatch
    return [{"do": "until", "duration": _DURATION[m["d"]], "n": 1},
            {"do": "restrict", "who": language._who(kind, key), "rules": ["doesnt_untap"]}], language._one(group)


TEMPLATES: list[tuple[re.Pattern[str], Any]] = [(_HOLD, _hold)]

# -- untap restrictions (wave 13E) -- 502.3: "Players can't untap more than one creature during their untap steps." (Smoke,
# Stoic Angel, Winter Orb, Static Orb, Imi Statue, Winter Moon): each player (the active one) chooses which of their tapped
# permanents of that kind untap, up to the limit; the rest stay tapped. With several such statics the lowest limit of each
# kind rules, and kinds are asked one after another (a permanent of two kinds counts for the first it is asked about).
_LIMIT = re.compile(r"^(?:As long as (?:~|this artifact) is untapped, )?[Pp]layers can't untap more than (?P<n>one|two|three) "
                    r"(?P<w>[a-z ]+?)s? during their untap steps\.?$")
_NUMBERS = {"one": 1, "two": 2, "three": 3}


def static_definition(text: str) -> dict[str, Any] | None:
    from app.rules import selectors

    if text.strip() == "You can't untap more than one land during your untap step.":
        return {'kind': 'static', 'static': 'untap_limit', 'sel': selectors.Selector(types=('Land',)).key(),
                'n': 1, 'scope89': 'you', 'conditions': [], 'effects': []}
    if text.strip().replace('~', 'this artifact') == (
            'As long as this artifact is untapped, each player chooses artifact, creature, or land during their untap step. '
            'That player can untap only permanents of the chosen type this step.'):
        return {'kind': 'static', 'static': 'untap_category89',
                'conditions': [{'static': 'self', 'test': 'untapped'}], 'effects': []}
    m = _LIMIT.match(text.strip())
    sel = selectors.parse(f"{m['w']}s") if m else None
    if m is None or sel is None:
        return None
    return {"kind": "static", "static": "untap_limit", "sel": sel.key(), "n": _NUMBERS[m["n"]], "effects": [],
            "conditions": [{"static": "self", "test": "untapped"}] if text.startswith("As long as") else []}


def limited(plan: Plan, player: str, keep: list[str]) -> list[list[Any]]:
    """The kinds of permanent ``player``'s untap step limits where more of them would untap: [[their ids, the limit], ...]."""
    from app.rules import permissions, selectors, statics

    limits: dict[str, int] = {}
    categories: list[list[Any]] = []
    for src, _, d in permissions._table_statics(plan.state, plan.info, {"untap_limit", "untap_category89"}):
        if not statics.conditions_hold(plan, d, source=src, controller=src.controller) \
                or (d.get('scope89') == 'you' and player != src.controller):
            continue
        if d['static'] == 'untap_category89':
            ids = [c.id for c in plan.state.cards.values() if c.tapped and c.controller == player
                   and c.zone.endswith(':battlefield') and c.id not in keep and not plan.manual(c)]
            categories.append([ids, {'category89': True, 'source': src.id, 'object_id': plan.oid(src)}])
        else:
            limits[d["sel"]] = min(d["n"], limits.get(d["sel"], 99))
    out: list[list[Any]] = []
    for key, n in sorted(limits.items()):
        sel = selectors.from_key(key)
        ids = [c.id for c in plan.state.cards.values()
               if c.tapped and c.controller == player and c.zone.endswith(":battlefield") and c.id not in keep
               and not plan.manual(c) and selectors.matches(plan, sel, c, plan.ch(c), player)]
        if len(ids) > n:
            out.append([ids, n])
    return [*categories, *out]


def _limits(plan: Plan, r: dict[str, Any]) -> None:
    """Ask the next kind that still has too many; when none is left, finish the untap step (the held-back ones are
    ``r["denied"]``, the others untap; a stunned one loses its counter instead, 122.1d)."""
    from app.rules import effects, engine

    while r["groups"]:
        cands, n = r["groups"][0]
        r = {**r, "groups": r["groups"][1:]}
        live = [c for c in cands if c in plan.state.cards and c not in r["denied"]]
        if len(live) > n:
            decide(plan, player=plan.active, kind="choose_cards",
                   prompt=f"Untap step: choose {n} of these to untap (the others stay tapped)",
                   options=[DecisionOption(id=c, label=f"Untap {plan.state.cards[c].name or 'permanent'}", card_id=c) for c in live],
                   min_choices=n, max_choices=n, resume={**r, "step": "untap_limit", "live": live})
            return
    free = [c for c in r["held"] if c in plan.state.cards and c not in r["denied"]]
    stuck = effects.keyword_actions.stunned(plan, free)
    if plan.state.settings.auto_untap and (let_go := [c for c in free if c not in stuck]):
        plan.do({"type": "tap", "card_ids": let_go, "tapped": False}, actor=plan.active)
    f = r["fin"]
    engine.finish_turn_start(plan, [*f["stunned"], *stuck], (f["previous"][0], f["previous"][1]),
                             [(p, n) for p, n in f["skipped"]], f["plain"], [*r["keep"], *r["denied"], *stuck], same_turn=bool(f.get("same_turn")))


def resume_limit(plan: Plan, d: object, chosen: list[str]) -> None:
    r = d.resume  # type: ignore[attr-defined]
    for c in chosen:
        plan.note(f"{plan.state.cards[c].name or 'It'} untaps (the untap step lets only some untap)", [c], actor=plan.active)
    _limits(plan, {**r, "denied": [*r["denied"], *[c for c in r["live"] if c not in chosen]]})


def candidates(plan: Plan, player: str, keep: list[str]) -> list[str]:
    """Tapped permanents ``player`` controls that they may choose not to untap and that would untap otherwise."""
    return [c.id for c in plan.state.cards.values()
            if c.tapped and c.controller == player and c.zone.endswith(":battlefield") and c.id not in keep
            and not plan.manual(c) and "may_stay_tapped" in scripts.statics(plan.ch(c))]  # (wave 29C: not just the first 50)


def ask(plan: Plan, asked: list[str], then: dict[str, Any], groups: list[list[Any]] | None = None) -> bool:
    """Ask the active player which of ``asked`` stay tapped, then which of each limited kind untap (``groups``: the ids
    ``limited`` named are in ``then["keep"]`` for now); True when the untap step is handled here (waiting, or finished)."""
    asked = [c for c in asked if plan.state.cards[c].controller == plan.active]
    if any(isinstance(g[1], dict) and g[1].get('category89') for g in groups or []):
        _categories89(plan, {'asked': asked, 'then': then, 'groups': groups or [], 'denied': [], 'choices89': []})
        return True
    held = list(dict.fromkeys(c for g in groups or [] for c in g[0]))
    if not asked:
        if not held:
            return False
        keep = [c for c in then["keep"] if c not in held]
        _limits(plan, {"keep": keep, "held": held, "groups": groups, "denied": [], "fin": then})
        return True
    decide(plan, player=plan.active, kind="choose_cards",
           prompt="Untap step: choose the permanents to keep tapped (the others untap)",
           options=[DecisionOption(id=c, label=f"Keep {plan.state.cards[c].name or 'permanent'} tapped", card_id=c)
                    for c in asked],
           min_choices=0, max_choices=len(asked), resume={"step": "untap_keep", "asked": asked, "groups": groups or [], **then})
    return True


def resume(plan: Plan, d: object, chosen: list[str]) -> None:
    from app.rules import effects, engine

    r = d.resume  # type: ignore[attr-defined]
    asked: list[str] = r["asked"]
    let_go = [c for c in asked if c not in chosen and c in plan.state.cards]
    held = list(dict.fromkeys(c for g in r.get("groups", []) for c in g[0]))
    stuck = effects.keyword_actions.stunned(plan, [c for c in let_go if c not in held])
    keep = [c for c in r["keep"] if c not in asked and c not in held] + list(chosen) + stuck
    if plan.state.settings.auto_untap:
        free = [c for c in let_go if c not in stuck and c not in held]
        if free:
            plan.do({"type": "tap", "card_ids": free, "tapped": False}, actor=plan.active)
    for c in chosen:
        plan.note(f"{plan.state.cards[c].name or 'It'} stays tapped (it isn't untapped during the untap step)", [c], actor=plan.active)
    fin = {k: r[k] for k in ("previous", "skipped", "plain")} | {"same_turn": bool(r.get("same_turn"))} | {"stunned": [*r["stunned"], *stuck]}
    if held:  # -- untap restrictions (wave 13E) -- then the limited kinds
        _limits(plan, {"keep": keep, "held": held, "groups": r["groups"], "denied": list(chosen), "fin": fin})
        return
    engine.finish_turn_start(plan, fin["stunned"], (r["previous"][0], r["previous"][1]),
                             [(p, n) for p, n in r["skipped"]], r["plain"], keep, same_turn=bool(r.get("same_turn")))



def _categories89(plan: Plan, r: dict[str, Any]) -> None:
    """All category choices precede optional and numeric untap choices; no object untaps yet."""
    from app.rules import engine

    left = [g for g in r['groups'] if isinstance(g[1], dict) and g[1].get('category89')]
    if left:
        group = left[0]
        decide(plan, player=plan.active, kind='choose_one', prompt='Storage Matrix: choose the type that can untap',
               options=[DecisionOption(id=t, label=t) for t in ('Artifact', 'Creature', 'Land')],
               resume={'step': 'untap_category89', **r, 'current89': group})
        return
    denied = set(r['denied'])
    groups = [[[c for c in ids if c not in denied], n] for ids, n in r['groups']]
    eligible = list(dict.fromkeys(c for ids in r['choices89'] for c in ids if c not in denied))
    # A nonlimiting group retains all permitted objects until the native final
    # untap operation; intersecting numeric groups and optional keeps still apply.
    groups.append([eligible, len(eligible)])
    then = r['then']
    if ask(plan, [c for c in r['asked'] if c not in denied], then, groups):
        return
    engine.finish_turn_start(plan, then['stunned'], (then['previous'][0], then['previous'][1]),
                             [(p, n) for p, n in then['skipped']], then['plain'], then['keep'],
                             same_turn=bool(then.get('same_turn')))


def resume_category89(plan: Plan, d: Any, chosen: list[str]) -> None:
    r = dict(d.resume)
    ids, meta = r.pop('current89')
    r['groups'] = [g for g in r['groups'] if g[1] != meta]
    r['denied'] = list(dict.fromkeys([*r['denied'], *(cid for cid in ids if cid in plan.state.cards
                          and chosen[0] not in plan.ch(plan.state.cards[cid]).types)]))
    r['choices89'] = [*r['choices89'], ids]
    r.pop('step', None)
    _categories89(plan, r)

"""Grouped token-characteristic replacements (111.3, 614.5, 614.16, 616.1).

The planner keeps a player's whole heterogeneous creation event together. A choice
receipt contains ordinary exact object references and a copiable recipe, never a
selector with a physical identity embedded in its text.
"""
from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

from app.game.rules_state import CopyRecipe, ObjectRef

if TYPE_CHECKING:
    from app.rules.plan import Plan
    from app.rules.replace import Candidate


class TokenReplacementChoice(BaseModel):
    source: ObjectRef
    index: int
    player: str
    choice: str
    atom: str = "instruction"
    original: ObjectRef | None = None
    recipe: CopyRecipe | None = None


class TokenCreationGroup(BaseModel):
    player: str
    creation_id: str | None = None
    parts: list[dict[str, Any]] = Field(default_factory=list)
    applied: list[str] = Field(default_factory=list)
    declined: list[str] = Field(default_factory=list)
    choices: list[TokenReplacementChoice] = Field(default_factory=list)


def definition(text: str) -> dict[str, Any] | None:
    """Exact native replacement definitions; parser admission is a separate hook."""
    t = re.sub(r'\s+', ' ', text).strip().rstrip('.').lower()
    op: dict[str, Any] | None = None
    if t == "if you would create one or more tokens, you may instead create that many 2/2 green cat creature tokens with haste or that many 3/1 green dog creature tokens with vigilance":
        op = {'do': 'token_characteristics', 'mode': 'jinnie', 'optional': True}
    elif t == 'the first time you would create one or more tokens during each of your turns, you may instead choose a creature other than ~ and create that many tokens that are copies of that creature':
        op = {'do': 'token_characteristics', 'mode': 'other_creature', 'optional': True, 'first': True, 'your_turn': True}
    elif t == 'the first time you would create one or more tokens each turn, you may instead create that many tokens that are copies of enchanted permanent':
        op = {'do': 'token_characteristics', 'mode': 'host', 'optional': True, 'first': True}
    elif t == 'as long as ~ is attached to a creature, the first time you would create one or more tokens each turn, you may instead create that many tokens that are copies of equipped creature':
        op = {'do': 'token_characteristics', 'mode': 'host_creature', 'optional': True, 'first': True}
    else:
        match = re.fullmatch(r'if you would create a (fish|shark) token, create (a 3/3 blue shark|an 8/8 blue octopus) creature token instead', t)
        if match is not None:
            creature, power = ('Shark', '3') if match[1] == 'fish' else ('Octopus', '8')
            return {'kind': 'static', 'static': 'replace', 'event': 'tokens', 'effects': [],
                    'match': {'who': 'you', 'subtypes': [match[1].capitalize()]},
                    'op': {'do': 'replace', 'group_tokens': True, 'token': {
                        'name': creature, 'power': power, 'toughness': power, 'colors': ['U'],
                        'type_line': 'Token Creature — ' + creature, 'text': ''}}}
    if op is None:
        return None
    return {'kind': 'static', 'static': 'replace', 'event': 'tokens', 'match': {'who': 'you'},
            'op': {**op, 'group_tokens': True}, 'effects': []}


def prior_creators(plan: Plan) -> frozenset[str]:
    """Actual creations before this instruction, including uncollected events.

    Missing sources, declined replacements and departed tokens do not erase the
    history. Zero or redirected noncreations do not manufacture facts (701.7a).
    """
    from app.rules import history

    return frozenset(f.player for f in history.log_for(plan).facts if f.kind == 'token' and f.amount > 0)


def source_ref(plan: Plan, candidate: Candidate) -> ObjectRef | None:
    from app.rules import context

    if candidate.source_card is None or candidate.source_oid is None:
        return None
    ref = context.ref_of(plan, candidate.source_card)
    return ref if ref is not None and ref.object_id == candidate.source_oid else None


def eligible(plan: Plan, candidate: Candidate, group: TokenCreationGroup, prior: frozenset[str]) -> bool:
    """Source-dependent eligibility; the existing native matcher handles tokens."""
    if candidate.controller != group.player or not any(p.get('count', 0) > 0 for p in group.parts):
        return False
    if candidate.op.get('first') and group.player in prior:
        return False
    if candidate.op.get('your_turn') and group.player != plan.active:
        return False
    ref = source_ref(plan, candidate)
    if ref is None:
        return False
    if candidate.op.get('mode') == 'other_creature':
        from app.rules import selectors

        if not selectors.candidates(plan, selectors.Selector(types=('Creature',), other=True), group.player, candidate.source_card):
            return False
    if candidate.op.get('mode') in ('host', 'host_creature'):
        source = plan.state.cards[ref.card]
        host = plan.state.cards.get(source.attached_to or '')
        if host is None or not host.zone.endswith(':battlefield'):
            return False
        if candidate.op['mode'] == 'host_creature' and 'Creature' not in plan.ch(host).types:
            return False
    return True


def identity(group: TokenCreationGroup) -> str:
    return group.creation_id or group.player + ":" + str(group.parts[0].get("creation_atom", "instruction"))


def receipt_for(candidate: Candidate, group: TokenCreationGroup) -> TokenReplacementChoice | None:
    return next((r for r in group.choices if r.source.object_id == candidate.source_oid
                 and r.index == candidate.seq[-1] and r.player == group.player
                 and r.atom == identity(group)), None)


def token_spec(plan: Plan, candidate: Candidate, receipt: TokenReplacementChoice) -> dict[str, Any] | None:
    if candidate.op.get('mode') == 'fixed_mbc':  # -- Mystery Booster Commander (wave MBC-B) -- Flitwing: "that many Clue tokens" (one fixed token)
        return dict(candidate.op['token'])
    if receipt.choice in ('cat', 'dog'):
        name, power, toughness, keyword = ('Cat', '2', '2', 'Haste') if receipt.choice == 'cat' else ('Dog', '3', '1', 'Vigilance')
        return {'name': name, 'power': power, 'toughness': toughness, 'colors': ['G'],
                'type_line': 'Token Creature — ' + name, 'text': keyword}
    if receipt.recipe is None:
        raise ValueError('A copy replacement requires its original copiable recipe')
    from app.rules import copying

    ctx = {'controller': candidate.controller, 'source_card': candidate.source_card, 'source_object': candidate.source_oid}
    request = copying.token_copy_request(plan, ctx, receipt.player, receipt.recipe, 1)
    return dict(request[1]) if request is not None else None


def matching_parts(plan: Plan, candidate: Candidate, group: TokenCreationGroup) -> list[int]:
    from app.rules import replace

    # Group ancestry, rather than each satellite's presentation, determines
    # whether a fixed addition has already applied to this creation event.
    if candidate.op.get('do') == 'extra':
        return [i for i, part in enumerate(group.parts) if part.get('count', 0) > 0
                and replace._token_matches(candidate.match, part['token'])
                and (candidate.match.get('who') != 'you' or part['player'] == candidate.controller)
                and (candidate.match.get('who') != 'opponent' or part['player'] != candidate.controller)]
    return [i for i, part in enumerate(group.parts) if replace._tokens_applies(plan, candidate, part, {})]


def applicable(plan: Plan, candidates: list[Candidate], group: TokenCreationGroup,
               prior: frozenset[str]) -> list[Candidate]:
    found = []
    for candidate in candidates:
        if candidate.id in group.applied or candidate.id in group.declined:
            continue
        if candidate.op.get('do') == 'token_characteristics':
            if not eligible(plan, candidate, group, prior):
                continue
        elif not matching_parts(plan, candidate, group):
            continue
        found.append(candidate)
    self_replacements = [c for c in found if c.self_repl]
    creators = [c for c in found if c.op.get('do') == 'set_creator']
    return sorted(self_replacements or creators or found, key=lambda c: c.seq)


def apply(plan: Plan, candidate: Candidate, group: TokenCreationGroup,
          receipt: TokenReplacementChoice | None = None) -> TokenCreationGroup:
    """Pure transformation of one event, retaining every original part's ancestry."""
    from app.rules import replace

    if candidate.op.get('do') == 'add':
        # Xorn's printed additional Treasure is one token for the creation
        # event, with its normal characteristics; it does not clone each
        # separately described Treasure part of a heterogeneous instruction.
        from dataclasses import replace as replace_candidate

        from app.rules import token_grammar

        subtype = (candidate.match.get('subtypes') or [None])[0]
        parsed = token_grammar.parse('create a ' + str(subtype) + ' token')
        if parsed is None or len(parsed) != 1:
            raise ValueError('A grouped fixed token addition requires a native token definition')
        return apply(plan, replace_candidate(candidate, op={**candidate.op, 'do': 'extra', 'token': parsed[0]['token']}), group)
    out = group.model_copy(deep=True)
    out.applied.append(candidate.id)
    op = candidate.op
    if op.get('do') == 'token_characteristics':
        if receipt is None or receipt.choice == 'decline':
            raise ValueError('Applying an optional token replacement requires its choice')
        spec = token_spec(plan, candidate, receipt)
        out.parts = [{**part, 'token': dict(spec)} for part in out.parts] if spec is not None else []
        if receipt_for(candidate, out) is None:
            out.choices.append(receipt)
    else:
        indices = set(matching_parts(plan, candidate, out))
        if op.get('do') == 'extra' and op.get('n') != 'same':
            if indices:
                ancestry = [{k: v for k, v in out.parts[i].items() if k not in ('kind', 'player', 'token', 'count', 'applied', 'why', 'root', 'satellite')}
                            for i in sorted(indices)]
                common = {k: v for k, v in ancestry[0].items() if all(part.get(k) == v for part in ancestry[1:])}
                addition = {'kind': 'tokens', 'player': out.player, 'token': dict(op['token']),
                            'count': int(op.get('n') or 1), 'satellite': True, **common}
                if any(part != common for part in ancestry):
                    # Keep every possible original ancestry until the native
                    # site's recipient/entry planner resolves the association.
                    # Never choose the first original's defender/attachment.
                    addition['creation_ancestry'] = ancestry
                out.parts.append(addition)
        else:
            transformed = []
            for i, part in enumerate(out.parts):
                transformed.extend(replace._tokens_apply(plan, candidate, part, {}) if i in indices else [part])
            out.parts = transformed
        if op.get('do') == 'set_creator':
            out.player = candidate.controller
    for part in out.parts:
        part['applied'] = list(dict.fromkeys([*(part.get('applied') or []), candidate.id]))
        part['why'] = [*(part.get('why') or []), candidate.label]
    return out


def decline(group: TokenCreationGroup, candidate: Candidate) -> TokenCreationGroup:
    """614.5: an explicit decline spends this event's one opportunity, not a turn."""
    out = group.model_copy(deep=True)
    if candidate.id not in out.declined:
        out.declined.append(candidate.id)
    return out


def snapshot(plan: Plan, candidate: Candidate, group: TokenCreationGroup,
             choice: str, original: str | None = None) -> TokenReplacementChoice:
    """Record the recipe when the affected player actually applies a replacement."""
    from app.game.errors import ActionError
    from app.rules import context, copying

    source = source_ref(plan, candidate)
    if source is None:
        raise ActionError('That token replacement source is no longer present')
    if choice not in (('decline', 'cat', 'dog') if candidate.op.get('mode') == 'jinnie' else ('decline', 'apply')):
        raise ActionError('Choose an available token replacement option')
    receipt = TokenReplacementChoice(source=source, index=candidate.seq[-1], player=group.player, choice=choice,
                                     atom=identity(group))
    if choice in ('decline', 'cat', 'dog') or candidate.op.get('mode') == 'fixed_mbc':  # (wave MBC-B: a fixed token copies nothing)
        return receipt
    card = plan.state.cards.get(source.card)
    if candidate.op.get('mode') in ('host', 'host_creature'):
        original = card.attached_to if card is not None else None
    copied = plan.state.cards.get(original or '')
    ref = context.ref_of(plan, copied.id) if copied is not None else None
    if copied is None or ref is None or not copied.zone.endswith(':battlefield'):
        raise ActionError('The permanent to copy is no longer present')
    if candidate.op.get('mode') == 'other_creature' and (
            'Creature' not in plan.ch(copied).types or ref.object_id == candidate.source_oid):
        raise ActionError('Choose another creature to copy')
    receipt.original = ref
    receipt.recipe = copying.recipe_of(plan, copied)
    return receipt


def signature(group: TokenCreationGroup) -> tuple[tuple[str, int], ...]:
    """Final creation semantics, ignoring only replacement-planning bookkeeping."""
    import json

    amounts: dict[str, int] = {}
    for part in group.parts:
        key = json.dumps({k: v for k, v in part.items() if k not in ('count', 'applied', 'why', 'root', 'satellite')}, sort_keys=True)
        amounts[key] = amounts.get(key, 0) + int(part['count'])
    return tuple(sorted((key, n) for key, n in amounts.items() if n > 0))


def commuting(plan: Plan, candidates: list[Candidate], group: TokenCreationGroup, prior: frozenset[str]) -> bool:
    """Pure bounded exploration; optional decisions are never made by a preview."""
    budget = [80]
    outcomes: set[tuple[tuple[str, int], ...]] = set()

    def explore(current: TokenCreationGroup) -> bool:
        budget[0] -= 1
        if budget[0] < 0:
            return False
        found = applicable(plan, candidates, current, prior)
        if any(c.op.get('optional') for c in found):
            return False
        if not found:
            outcomes.add(signature(current))
            return len(outcomes) <= 1
        return all(explore(apply(plan, candidate, current)) for candidate in found)

    return explore(group)


class GroupQuestion(Exception):
    """A pure pending 616 or original choice, carried by the native token site."""

    def __init__(self, player: str, fingerprint: str, prompt: str, options: list[Any], commands: dict[str, str]) -> None:
        super().__init__(prompt)
        self.player, self.fingerprint, self.prompt = player, fingerprint, prompt
        self.options, self.commands = options, commands


def fingerprint(site: str, group: TokenCreationGroup, candidates: list[Candidate], phase: str = 'order') -> str:
    import hashlib
    import json

    payload = [site, phase, identity(group), group.player, group.parts, group.applied, group.declined, [c.id for c in candidates]]
    return 'token_group:' + hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:20]


def order_choice(plan: Plan, site: str, candidates: list[Candidate], group: TokenCreationGroup,
                 answers: dict[str, str]) -> tuple[Candidate, str]:
    """Ordering a mandatory replacement is distinct from declining an optional one."""
    from app.game.errors import ActionError
    from app.game.rules_state import DecisionOption

    fp = fingerprint(site, group, candidates)
    options: list[DecisionOption] = []
    commands: dict[str, str] = {}
    for candidate in candidates:
        modes = ['cat', 'dog', 'decline'] if candidate.op.get('mode') == 'jinnie' else ['apply', 'decline'] if candidate.op.get('optional') else ['apply']
        for mode in modes:
            option = 'o' + str(len(options))
            label = (f'{candidate.label}: create Cats' if mode == 'cat' else f'{candidate.label}: create Dogs' if mode == 'dog'
                     else f'Decline {candidate.label}' if mode == 'decline' else f'Apply {candidate.label}')
            options.append(DecisionOption(id=option, label=label, card_id=candidate.source_card))
            commands[option] = candidate.id + '|' + mode
    answer = answers.get(fp)
    if answer is None:
        raise GroupQuestion(group.player, fp, 'Choose a token replacement to apply, or decline one optional replacement', options, commands)
    if answer not in commands.values():
        raise ActionError('That token replacement choice is no longer available')
    candidate_id, mode = answer.rsplit('|', 1)
    return next(c for c in candidates if c.id == candidate_id), mode


def original_choice(plan: Plan, site: str, candidate: Candidate, group: TokenCreationGroup,
                    answers: dict[str, str]) -> TokenReplacementChoice:
    from app.game.errors import ActionError
    from app.game.rules_state import DecisionOption
    from app.rules import selectors, targets

    fp = fingerprint(site, group, [candidate], 'original')
    selector = selectors.Selector(types=('Creature',), other=True)
    ids = selectors.candidates(plan, selector, group.player, candidate.source_card)
    options = [DecisionOption(id=cid, label=targets.label(plan, cid), card_id=cid) for cid in ids]
    selected = answers.get(fp)
    if selected is None:
        raise GroupQuestion(group.player, fp, 'Choose another creature for the replacement token copies', options, {cid: cid for cid in ids})
    if selected not in ids:
        raise ActionError('That creature is no longer available to copy')
    return snapshot(plan, candidate, group, 'apply', selected)


def plan_group(plan: Plan, site: str, candidates: list[Candidate], group: TokenCreationGroup,
               prior: frozenset[str], answers: dict[str, str], receipts: list[TokenReplacementChoice]) -> TokenCreationGroup:
    """Plan, without performing, a whole creation event. Receipts survive later pauses."""
    current = group.model_copy(deep=True)
    current.choices = list(receipts)
    for _ in range(100):
        found = applicable(plan, candidates, current, prior)
        if not found:
            return current
        if len(found) == 1 and not found[0].op.get('optional') or commuting(plan, candidates, current, prior):
            chosen, mode = found[0], 'apply'
        else:
            chosen, mode = order_choice(plan, site, found, current, answers)
        if mode == 'decline':
            current = decline(current, chosen)
            continue
        receipt = None
        if chosen.op.get('do') == 'token_characteristics':
            receipt = receipt_for(chosen, current)
            if receipt is None:
                receipt = (original_choice(plan, site, chosen, current, answers)
                           if chosen.op.get('mode') == 'other_creature' else snapshot(plan, chosen, current, mode))
                receipts.append(receipt)
                current.choices.append(receipt)
        current = apply(plan, chosen, current, receipt)
    raise ValueError('Too many token replacement steps')


def initial_groups(plan: Plan, parts: list[dict[str, Any]]) -> list[TokenCreationGroup]:
    """Explicit creation actions within one simultaneous happening (608.2f/700.1).

    First-time eligibility is the shared history snapshot before this happening:
    planning one atom first does not make it occur before its simultaneous peers.
    Distinct atoms retain replacement ancestry and do not merge on creator change.
    This is a rules inference (also analogous to Tempt's repeated simultaneous
    opponent effects), not an additional card-specific published ruling.
    """
    by_player: dict[tuple[str, str], TokenCreationGroup] = {}
    for part in parts:
        if int(part.get('count') or 0) <= 0 or part['player'] not in plan.live():
            continue
        # Explicit instruction identity comes from the native creation site.
        # Defender/attachment metadata never defines an event boundary.
        key = (part['player'], str(part.get('creation_atom', 'instruction')))
        group = by_player.setdefault(key, TokenCreationGroup(player=part['player'], creation_id=repr(key)))
        group.parts.append(dict(part))
    return [group for p in plan.apnap() for (player, _), group in by_player.items() if player == p]


def creator_groups(plan: Plan, site: str, candidates: list[Candidate], groups: list[TokenCreationGroup],
                   answers: dict[str, str]) -> list[TokenCreationGroup]:
    """616.1a/b precede token-characteristic replacements and final-owner history.

    A changed creator does not merge distinct creation events. Keep every
    original event and its metadata, then use the affected players' APNAP order.
    """
    creators = [c for c in candidates if c.self_repl or c.op.get('do') == 'set_creator']
    finals = [plan_group(plan, site + ':creator:' + str(i), creators, group, frozenset(), answers, [])
              for i, group in enumerate(groups)]
    order = plan.apnap()
    return sorted(finals, key=lambda group: order.index(group.player) if group.player in order else len(order))


def parse(body: str) -> tuple[list[dict[str, Any]], None, bool] | None:
    """Fisher's actual optional public reveal follows a private exact top look."""
    if ' '.join(body.lower().split()).rstrip('.') != "look at the top card of your library. you may reveal it if it's a land card. create a 1/1 blue fish creature token if you revealed it this way. then draw a card":
        return None
    from app.rules import selectors

    land = selectors.parse('land card')
    assert land is not None
    return [
        {'do': 'look_top', 'n': 1, 'player': 'you', 'exact_look': True},
        {'do': 'pick_looked', 'n': 1, 'to': 'top', 'optional': True, 'reveal': True,
         'sel': land.key(), 'did': 'fisher_revealed', 'as': 'fisher_revealed_card'},
        {'do': 'only_if', 'cond': {'succeeded': 'fisher_revealed'}, 'skip': 1},
        {'do': 'create_token', 'who': 'you', 'n': 1, 'token': {'name': 'Fish', 'power': '1', 'toughness': '1',
         'colors': ['U'], 'type_line': 'Token Creature — Fish', 'text': ''}},
        {'do': 'look_reveal_cleanup', 'ref': 'ref:fisher_revealed_card'},
        {'do': 'draw', 'n': 1, 'who': 'you'},
    ], None, False

"""Resolution choices and exact paid-cost outcomes of activated abilities."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.rules import context, selectors

if TYPE_CHECKING:
    from app.rules.plan import Plan


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    text = body.strip().rstrip('.')
    text = text[:1].upper() + text[1:]
    if text == 'Put a +0/+1 counter or a +1/+0 counter on target creature':
        return [{'do': 'activated_outcome_choice', 'options': [
            {'label': '+0/+1 counter', 'effects': [{'do': 'add_counters', 'who': 'target', 'kind': '+0/+1', 'n': 1}]},
            {'label': '+1/+0 counter', 'effects': [{'do': 'add_counters', 'who': 'target', 'kind': '+1/+0', 'n': 1}]}]}], [{'what': selectors.Selector(types=('Creature',)).key()}], False
    if text == 'Put a +1/+1 counter on ~ or ~ gains flying, first strike, or trample':
        return [{'do': 'activated_outcome_choice', 'options': [
            {'label': '+1/+1 counter', 'effects': [{'do': 'add_counters', 'who': 'self', 'kind': '+1/+1', 'n': 1}]},
            *[{'label': word, 'effects': [{'do': 'grant', 'who': 'self', 'keywords': [word], 'duration': 'permanent'}]}
              for word in ('flying', 'first strike', 'trample')]]}], None, False
    if text == 'Until end of turn, ~ becomes the color of your choice and gains hexproof from that color':
        return [{'do': 'choose_value', 'who': 'you', 'what': 'color', 'as': 'activated_color'},
                {'do': 'activated_color_finish', 'who': 'ref:activated_color'}], None, False
    if text == '~ endures X':
        return [{'do': 'endure', 'who': 'self', 'n': {'x': 1}}], None, False
    if text == 'Draw three cards, then discard one of them':
        return [{'do': 'activated_draw_subset'}], None, False
    if text == 'You may put a creature card with mana value X from your hand onto the battlefield':
        return [{'do': 'activated_hand_exact_x'}], None, False
    if text == 'X target lands become Forests until end of turn':
        return [{'do': 'become', 'who': 'target', 'types': [], 'land_types': ['Forest'], 'duration': 'end_of_turn'}], [
            {'what': selectors.Selector(types=('Land',)).key(), 'min': 0, 'max': 250, 'x_count': 'exact'}], False
    if text == 'Draw a card. Then if there are no charge counters on ~, create a Treasure token and a 1/1 colorless Pilot creature token with "This token crews Vehicles as though its power were 2 greater."':
        return [{'do': 'draw', 'who': 'you', 'n': 1}, {'do': 'activated_empty_charge'}], None, False
    tokens = {
        'Create a 1/1 blue Faerie creature token named Cloud Sprite. It has flying and "This token can block only creatures with flying."':
            {'name': 'Cloud Sprite', 'power': '1', 'toughness': '1', 'colors': ['U'], 'type_line': 'Token Creature — Faerie',
             'text': 'Flying\nThis creature can block only creatures with flying.'},
        'Create a 3/1 red Elemental creature token named Spark Elemental. It has trample, haste, and "At the beginning of the end step, sacrifice this token."':
            {'name': 'Spark Elemental', 'power': '3', 'toughness': '1', 'colors': ['R'], 'type_line': 'Token Creature — Elemental',
             'text': 'Trample\nHaste\nAt the beginning of the end step, sacrifice this creature.'},
    }
    if text in tokens:
        return [{'do': 'create_token', 'who': 'you', 'n': 1, 'token': tokens[text]}], None, False
    # The native clauses already implement both instructions; only the printed
    # conjunction prevents the ordinary sentence grammar from composing them.
    if text == 'Put three +1/+1 counters on ~ and it becomes a black Demon in addition to its other colors and types':
        from app.rules import scripts

        return scripts.parse_effects('Put three +1/+1 counters on this creature. It becomes a black Demon in addition to its other colors and types.')
    return None


def insert(ctx: dict[str, Any], steps: list[dict[str, Any]]) -> bool:
    ctx['effects'][ctx['next']:ctx['next']] = steps
    return True


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from dataclasses import replace

    from app.rules import scripts

    if ability.kind != 'activated' or ':' not in ability.text:
        return None
    text = scripts.self_text(ability.text, ch.name)
    cost, body = text.split(':', 1)
    # These printed quotations are token rules text, rather than grants to a
    # preexisting object. Preserve them before the general quote protector.
    if 'token' not in body or '"' not in body:
        return None
    parsed = parse(body.strip())
    if parsed is None:
        return None
    native = scripts.define(replace(ability, text=cost + ': Draw a card.'), ch)
    if native is None:
        return None
    return {**native, 'effects': parsed[0]}


def choose(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.game.rules_state import DecisionOption
    from app.rules.plan import decide

    decide(plan, player=ctx['controller'], kind='choose_one', prompt=f"{ctx.get('name') or 'Choose'}: choose an effect",
           options=[DecisionOption(id=str(i), label=o['label']) for i, o in enumerate(e['options'])],
           resume={'step': 'activated_outcome_choice', 'ctx': ctx, 'e': e})
    return False


def resume(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import effects

    ctx = d.resume['ctx']
    insert(ctx, d.resume['e']['options'][int(chosen[0])]['effects'])
    effects.continue_effects(plan, ctx)


def color_finish(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    choice = context.refs(ctx).get(e['who'].removeprefix(context.PREFIX), {}).get('value')
    colors = {'White': 'W', 'Blue': 'U', 'Black': 'B', 'Red': 'R', 'Green': 'G'}
    if choice in colors:
        return insert(ctx, [{'do': 'become', 'who': 'self', 'types': [], 'colors': [colors[choice]], 'duration': 'end_of_turn'},
                            {'do': 'grant', 'who': 'self', 'keywords': [f'hexproof from {choice.lower()}'], 'duration': 'end_of_turn'}])
    return True


def draw_subset(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import history

    before = list(history.log_for(plan).drawn.get(ctx['controller'], []))
    return insert(ctx, [{'do': 'draw', 'who': 'you', 'n': 3}, {'do': 'activated_draw_subset_finish', 'before': before}])


def draw_finish(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import history

    log = history.log_for(plan)
    player = ctx['controller']
    excluded = set(e['before']) | set(log.drawn_replaced.get(player, [])) | set(log.drawn_counted.get(player, []))
    ids = [oid.rsplit('.', 1)[0] for oid in log.drawn.get(player, []) if oid not in excluded]
    ids = [cid for cid in ids if cid in plan.state.cards and plan.state.cards[cid].zone == f'{player}:hand'
           and plan.oid(cid) in log.drawn[player]]
    context.bind_objects(plan, ctx, 'activated_drawn', ids)
    return insert(ctx, [{'do': 'return_choice', 'who': 'ref:activated_drawn', 'n': 1, 'to': 'choose', 'as': 'activated_discard'},
                        {'do': 'discard_named', 'who': 'ref:activated_discard'}])


def hand_exact_x(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import values

    n = values.evaluate(plan, ctx, {'x': 1})
    sel = selectors.Selector(zones=('hand',), card=True, zone_owner='you', types=('Creature',), compare=(('mv', '==', n),))
    return insert(ctx, [{'do': 'return_choice', 'sel': sel.key(), 'n': 1, 'upto': True, 'to': 'battlefield', 'under': 'you'}])


def empty_charge(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import effects

    source = effects._cards(plan, ctx, 'self')
    counters = plan.state.cards[source[0]].counters if source else getattr(plan.rules.lki.get(ctx.get('source_object') or ''), 'counters', {})
    if counters.get('charge', 0):
        return True
    return insert(ctx, [
        {'do': 'create_token', 'who': 'you', 'n': 1, 'token': {'name': 'Treasure', 'type_line': 'Token Artifact — Treasure', 'colors': [],
         'text': '{T}, Sacrifice this artifact: Add one mana of any color.'},
         'more': [{'n': 1, 'token': {'name': 'Pilot', 'type_line': 'Token Creature — Pilot', 'colors': [],
         'power': '1', 'toughness': '1', 'text': 'This creature crews Vehicles as though its power were 2 greater.'}}]}])


PRIMITIVES = {'activated_outcome_choice': choose, 'activated_color_finish': color_finish,
              'activated_draw_subset': draw_subset, 'activated_draw_subset_finish': draw_finish,
              'activated_hand_exact_x': hand_exact_x, 'activated_empty_charge': empty_charge}
RESUME = {'activated_outcome_choice': resume}

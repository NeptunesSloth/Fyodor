"""A returned creature reaches its owner's hand, including the watching creature itself."""
from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.characteristics import AbilityText, Characteristics

ENTRY = "When this creature enters, return two creatures you control to their owner's hand."
TEXT = ('Whenever this creature or another creature is returned to your hand from the battlefield, '
        'create a 1/1 white Soldier creature token.')


def definition(ability: AbilityText, ch: Characteristics) -> dict[str, Any] | None:
    if ability.kind != 'triggered' or ability.text not in (ENTRY, TEXT):
        return None
    from app.rules import scripts, selectors

    if ability.text == ENTRY:
        native = scripts.define(replace(ability, text=ENTRY.replace('two creatures', 'two permanents')), ch)
        if native is None:
            return None
        choice, move = native['effects']
        if choice.get('do') != 'player_chooses' or move.get('do') != 'bounce':
            return None
        # The dedicated return_yours primitive moves chosen cards sequentially;
        # native player_chooses+bounce returns the entire chosen set in one batch.
        return {**native, 'effects': [{**choice, 'sel': selectors.Selector(types=('Creature',)).key(),
                                      'label': 'creatures'}, move]}
    native = scripts.define(replace(ability, text=TEXT.replace(
        'this creature or another creature is returned to your hand from the battlefield', 'a creature is returned to hand')), ch)
    if native is None:
        return None
    owner = selectors.Selector(zones=('battlefield', 'stack', 'graveyard', 'hand', 'library', 'exile', 'command'), owner='you')
    # CR201.5: 'this creature' names the source even if it is no longer a creature.
    # The native add-time predicate checks the frozen event object's owner, not
    # current source control or a later resolution-time condition.
    return {**native, 'cond': {**native['cond'], 'subject': 'self_or',
                              'sel': selectors.Selector(types=('Creature',)).key()},
            'if': {'object': 'event', 'is': owner.key()}}

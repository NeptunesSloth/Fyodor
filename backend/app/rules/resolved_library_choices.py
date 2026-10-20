"""Resolved choices composed from existing reveal, name, counter and parity primitives."""
from __future__ import annotations

import re
from typing import Any


def parse(body: str) -> tuple[list[dict[str,Any]],Any,bool] | None:
    from app.rules import scripts, selectors

    text=re.sub(r'\s+',' ',body.strip())
    if text.rstrip('.')=='Choose land or nonland. Reveal cards from the top of your library until you reveal a card of the chosen kind. Put that card into your hand and the rest on the bottom of your library in a random order':
        return [{'do':'choose_land_nonland'},{'do':'reveal_chosen_kind'},
                {'do':'pick_looked','which':'that','require_found':True,'to':'hand'},
                {'do':'rest_looked','to':'bottom_random'}],None,False
    arcanix=re.fullmatch(r'Target player chooses a card name, then reveals the top card of their library\. If that card has the chosen name, that player puts it into their hand\. Otherwise, they put it into their graveyard and (?:this artifact|~) deals 2 damage to them\.',text)
    if arcanix:
        native=scripts.parse_effects('Target player chooses a card name, then reveals the top card of their library. If that card has the chosen name, that player puts it into their hand. Otherwise, that player puts it into their graveyard.')
        assert native is not None
        es,target,may=native
        assert es[-2]['do']=='only_if'
        es[-2]['skip']=2
        return [*es,{'do':'damage','who':'target','n':2}],target,may
    if re.fullmatch(r"You may put a \+1/\+1 counter on a creature\. Then choose odd or even\. Return each creature with power of the chosen quality to its owner's hand\.(?: \(Zero is even\.\))?",text):
        native=scripts.parse_effects("Choose odd or even. Return each creature with power of the chosen quality to its owner's hand.")
        assert native is not None
        choice={'do':'player_chooses','who':'you','sel':selectors.Selector(types=('Creature',)).key(),
                'n':1,'label':'creature','any':True,'upto':True,'as':'counter_choice'}
        return [choice,{'do':'add_counters','who':'ref:counter_choice','kind':'+1/+1','n':1},*native[0]],None,False
    return None

"""Temporary attack/block requirements reuse native legality and exact-object references."""
from __future__ import annotations

import re
from typing import Any


def simple_clause(text: str) -> tuple[list[dict[str, Any]], Any] | None:
    """Extend target-only block wording to native exact antecedents and plural selectors."""
    from app.rules.combat_rules import _restrict

    m = re.fullmatch(r'(?P<o>.+?) blocks? this turn if able', text)
    if m:
        return _restrict(m['o'], ['must_block'])
    m = re.fullmatch(r"(?P<o>target [^,.]+?) can't block (?:this creature|~) this turn", text)
    if m:
        return _restrict(m['o'], ['cant_block_obj:@src'])
    m = re.fullmatch(r'(?P<o>(?:up to one )?target [^,.]+?) blocks (?:this creature|~) this turn if able', text)
    if m:
        return _restrict(m['o'], ['must_block_obj:@src'])
    return None


def compound_clause(text: str) -> tuple[list[dict[str, Any]], Any] | None:
    from app.rules import scripts

    m = re.fullmatch(r'(?P<a>.+? (?:gets? [+-]\d+/[+-]\d+ until end of turn|becomes? [a-z]+ until end of turn|deals \d+ damage to you)) and attacks? this turn if able', text)
    if not m:
        return None
    first = scripts._one_clause(m['a'])
    if first is None or len(first[0]) != 1 or first[0][0].get('do') not in ('pump','become','damage'):
        return None
    who = first[0][0].get('who')
    if first[0][0]['do'] == 'damage':
        who = first[0][0].get('src') or 'self'
        if isinstance(who,str) and who.startswith('each:'):
            who = who[len('each:'):]
    return ([*first[0], {'do':'restrict','who':who,'rules':['must_attack']}],first[1])


def normalize_compound(body: str) -> str:
    """Keep a targeted color change and its attack requirement as two bound instructions."""
    return re.sub(r"(?P<a>[Tt]arget creature becomes [a-z]+ until end of turn) and attacks this turn if able", r"\g<a>. It attacks this turn if able", body)


def paired_requirement(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    """A spell's first target and a distinct optional/mandatory blocker target.

    Requires scoped native block_effects.args extension: resolve @t0 using target_refs(ctx,
    'target:0') exactly as existing @t1 does. Keeps target-object identity even if illegal,
    so the second target never accidentally acquires a different forced attacker.
    """
    from app.rules import language, scripts

    m = re.fullmatch(r'(?P<first>(?:[Pp]ut a \+1/\+1 counter on target creature you control|[Tt]arget creature gets [+-]\d+/[+-]\d+ until end of turn))\. (?P<optional>[Uu]p to one other|[Aa]nother) target creature blocks it this turn if able\.', body.strip())
    if not m:
        return None
    first = scripts._clause(m['first'][:1].lower()+m['first'][1:])
    if first is None:
        return None
    groups = scripts.target_groups(scripts.target_fields(first[1]))
    if len(groups) != 1:
        return None
    blocker = language.target_group('target creature')
    if blocker is None:
        return None
    blocker = {**blocker, 'min':0 if m['optional'].lower().startswith('up') else 1,
               'max':1, 'distinct_from':[0]}
    effects = scripts._renumber(first[0], [0])
    return ([*effects, {'do':'restrict','who':'target:1','rules':['must_block_obj:@t0']}],
            [*groups,blocker],False)


def damage_followthrough(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    from app.rules import scripts

    m = re.fullmatch(r"(?P<damage>~ deals \d+ damage to each creature target player controls)\. Each creature dealt damage this way attacks this turn if able\.", body.strip())
    if not m:
        return None
    first = scripts._clause(m['damage'])
    if first is None or len(first[0]) != 1 or first[0][0].get('do') != 'damage':
        return None
    key = 'ref:declaration_damage'
    return ([{**first[0][0], 'dealt_as': key},
             {'do':'restrict','who':'union:','dealt':key,'rules':['must_attack']}],first[1],False)


def optional_reach(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    from app.rules import scripts

    m = re.fullmatch(r'(?P<first>[Tt]arget creature blocks this turn if able)\. You may have it gain reach until end of turn\.(?P<learn> Learn\.)?',body.strip())
    if not m:
        return None
    first = simple_clause(m['first'].lower())
    learned = scripts.parse_effects('Learn.') if m['learn'] else ([],None,False)
    if first is None or learned is None:
        return None
    return ([*first[0], {'do':'may_rest','skip':1,'label':'Give that creature reach until end of turn'},
             {'do':'grant','who':'target','keywords':['reach']}, *learned[0]],first[1],False)


def transfer_blockers(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    from app.rules import language

    m = re.fullmatch(r'(?P<p>[Tt]arget player|[Tt]arget opponent) gains control of (?P<c>up to (?:two|three|four|\d+) target nonattacking creatures) until end of turn\. Untap those creatures\. They block this turn if able\.',body.strip())
    if not m:
        return None
    player = language.target_group(m['p'].lower())
    creatures = language.target_group(m['c'])
    if player is None or creatures is None:
        return None
    return ([{'do':'gain_control','who':'target:1','to':'target:0','duration':'end_of_turn'},
             {'do':'untap','who':'target:1'},
             {'do':'restrict','who':'target:1','rules':['must_block']}], [player,creatures],False)


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    return paired_requirement(body) or damage_followthrough(body) or optional_reach(body) or transfer_blockers(body)

"""A single announced creature target remains bound through a native dice results table."""
from __future__ import annotations

import re
from typing import Any

_HEAD = re.compile(r'^Choose (?P<target>target creature(?: [^.]+?)?), then roll a d(?P<sides>\d+)\.', re.IGNORECASE)
_ROW = re.compile(r'^If (?P<condition>the result is \d+ to \d+), (?P<body>.+)\.$', re.IGNORECASE)


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    from app.rules import dice, language, oracle, scripts

    text = ' '.join(body.split())
    head = _HEAD.match(text)
    if head is None or not (2 <= int(head['sides']) <= 1000):
        return None
    rewritten = dice.rewrite(text)
    if rewritten == text:  # native validation requires exhaustive nonoverlapping rows
        return None
    try:
        target = language.target_group(head['target'].lower())
    except (ValueError, language._Fail):
        return None
    if target is None or target.get('min') != 1 or target.get('max') != 1:
        return None
    out: list[dict[str, Any]] = [{'do': 'roll', 'sides': int(head['sides']), 'count': 1}]
    for sentence in oracle.split_sentences(rewritten[head.end():].strip()):
        row = _ROW.fullmatch(sentence)
        if row is None or (condition := dice.condition(row['condition'])) is None:
            return None
        clause = row['body']
        if clause.lower() == 'its owner puts it on their choice of the top or bottom of their library':
            clause = 'The owner of target creature puts it on their choice of the top or bottom of their library'
        elif re.fullmatch(r"return it to its owner's hand|gain control of it until the end of your next turn", clause, re.I):
            clause = re.sub(r'\bit\b', 'target creature', clause, flags=re.I)
        else:
            return None
        read = scripts.parse_effects(clause[:1].upper() + clause[1:] + '.')
        if read is None or read[1] is None or read[2]:
            return None
        out += [{'do': 'only_if', 'cond': condition, 'skip': len(read[0])}, *read[0]]
    return (out, [target], False) if len(out) > 1 else None

"""CR 205.1a, 611.2a, 613.1d/f: replace types and abilities together."""
from __future__ import annotations

import re
from typing import Any

_WORDING = re.compile(r'^(?P<who>target .+?) becomes an? (?P<sub>[A-Z][a-z]+) artifact with "(?P<ability>[^"]+)" '
                      r'and loses all other card types and abilities$')


def definition(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    from app.rules import granted, language
    from app.rules.layers import ARTIFACT_TYPES
    from app.rules.scripts import _NoMatch

    try:
        kind, key, target = language.ref(m['who'])
    except language._Fail as exc:
        raise _NoMatch from exc
    ability = granted.quote(m['ability'])
    if kind != 'target' or target is None or m['sub'] not in ARTIFACT_TYPES or ability is None:
        raise _NoMatch
    return [{'do': 'become', 'who': language._who(kind, key), 'types': ['Artifact'],
             'artifact_types': [m['sub']], 'lose_abilities': True, 'abilities': [ability],
             'duration': 'permanent'}], target


TEMPLATES = [(_WORDING, definition)]

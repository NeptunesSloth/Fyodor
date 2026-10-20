"""CR 101.2 / 611.2c: keyword loss with a prohibition on gaining it again."""
from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from app.rules import oracle

if TYPE_CHECKING:
    from app.rules.plan import Plan

_KW = r"(?:flying|first strike|double strike|deathtouch|lifelink|vigilance|trample|haste|reach|menace|indestructible|hexproof|defender|shroud|flash|banding)"
_LIST = rf"{_KW}(?:(?:, |,? and |,? or ){_KW})*"
_PATTERN = re.compile(rf"^until end of turn, (?P<who>target creature|all creatures|creatures you control|creatures your opponents control) "
                      rf"lose(?:s)? (?P<loss>{_LIST}) and can't have (?P<deny>{_LIST})$")
PREFIX = 'cant_have_keyword:'


def _parse(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    from app.rules import language as L

    subject = m['who']
    if subject.startswith('creatures '):
        subject = 'all ' + subject
    kind, key, group = L.ref(subject)
    def split(text: str) -> list[str]:
        return re.split(r',? and |,? or |, ', text)

    return [{'do': 'grant', 'who': L._who(kind, key), 'keywords': [],
             'remove': split(m['loss']), 'deny': split(m['deny'])}], L._one(group)


def denied(keyword: str, prohibited: set[str]) -> bool:
    return keyword in prohibited or keyword == 'hexproof from' and 'hexproof' in prohibited or keyword.startswith('bands with other ') and 'banding' in prohibited


def filter_grants(keywords: list[str], abilities: list[str], prohibited: set[str]) -> tuple[list[str], list[str]]:
    """A prohibited ability's resolved grant isn't created; other parts still happen."""
    out = []
    for text in abilities:
        parsed = oracle.parse_abilities(text)
        if len(parsed) == 1 and parsed[0].kind == 'keywords':
            pieces = [piece for piece in oracle.keyword_pieces(oracle.strip_reminders(text))
                      if not denied(oracle.keyword_name(piece) or '', prohibited)]
            if pieces:
                out.append(', '.join(pieces))
        else:
            out.append(text)
    return [k for k in keywords if not denied(k, prohibited)], out


def capture(plan: Plan, affected: list[str]) -> dict[str, list[str]]:
    found = {}
    for oid in affected:
        card = plan.state.cards.get(oid.rsplit('.', 1)[0])
        if card is None or plan.oid(card) != oid:
            continue
        prohibited = sorted(rule[len(PREFIX):] for rule in plan.ch(card).imposed if rule.startswith(PREFIX))
        if prohibited:
            found[oid] = prohibited
    return found


TEMPLATES = [(_PATTERN, _parse)]

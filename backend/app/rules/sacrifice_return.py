"""-- if you do (wave 52A) -- "Each player sacrifices a creature of their choice. If you sacrificed a creature this way, you may return another permanent card from your graveyard to the
battlefield." (Rise of the Witch-king), "… a creature or planeswalker … If you sacrificed a permanent this way, you may return another permanent card from your graveyard to your
hand." (Deadly Brew).

CR 2026-09-25: 608.2c: the second sentence follows the first; 201.5 / 608.2h: "another" permanent card is a card other than the one just sacrificed (the permanent as it is now a card in the
graveyard, 400.7j), which the choice of the card to return leaves out (effects.return_choice ``exclude``). Read as the same sentence with "a permanent card", the sacrificed card then
excluded from the choice.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

_PAT = re.compile(r"^(?P<head>Each player sacrifices an? [^.]+? of their choice\. If you sacrificed an? (?:creature|permanent) this way, you may return) another "
                  r"(?P<tail>permanent card from your graveyard to (?:the battlefield|your hand)\.?)$")


def parse(body: str, read: Callable[[str], tuple[list[dict[str, Any]], Any, bool] | None]) -> tuple[list[dict[str, Any]], Any, bool] | None:
    m = _PAT.match(body.strip())
    if m is None:
        return None
    got = read(f"{m['head']} a {m['tail']}")
    if got is None or got[1] is not None or len(got[0]) != 3 or [e["do"] for e in got[0]] != ["edict", "only_if", "return_choice"] or not got[0][0].get("as"):
        return None
    effects = list(got[0])
    effects[2] = {**effects[2], "exclude": effects[0]["as"]}
    return effects, got[1], got[2]

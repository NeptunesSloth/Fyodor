"""-- out of the game -- the client keeps a copy of what a player who is out may still send (frontend/src/game/outOfGame.ts), so the table
stops offering the rest instead of sending what the server refuses. The two lists must stay the same."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.game.out_of_game import OUT_MAY

CLIENT = Path(__file__).resolve().parents[2] / "frontend" / "src" / "game" / "outOfGame.ts"


def test_the_client_mirrors_what_an_out_player_may_send():
    if not CLIENT.is_file():
        pytest.skip("no frontend checkout")
    source = CLIENT.read_text("utf-8")
    lists = {name: re.search(rf"const {name} = (?:new Set\()?\[(.*?)\]", source, re.S) for name in ("RULES_INTENTS", "OUT_MAY")}
    assert all(lists.values()), "the client's lists moved: update this test"
    client = {s for m in lists.values() if m for s in re.findall(r'"([a-z_0-9]+)"', m.group(1))}
    assert client == set(OUT_MAY)

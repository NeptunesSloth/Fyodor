"""A printed terminal name's exclamation mark still ends its sentence."""

from app.rules import coverage, scripts
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_look import settle
from tests.test_rules_life_sequences44 import cards as cards
from tests.test_rules_life_sequences44 import game


def test_terminal_punctuation_preserved_without_rewriting_named_cards():
    name = "Blood for the Blood God!"
    assert scripts.self_text("Exile " + name, name) == "Exile ~."
    assert scripts.self_text(name + " deals 8 damage to each opponent.", name) == "~ deals 8 damage to each opponent."
    named = "Search your library for a card named " + name
    assert scripts.self_text(named, name) == named
    assert scripts.self_text("Exile Example", "Example") == "Exile ~"


def test_complete_canonical_bloodgod(cards):
    assert coverage.of_card_data(cards.resolve("Blood for the Blood God!")).level == "FULL"


def setup(cards, deaths):
    s = game(cards, ["Blood for the Blood God!"])
    source = put(s, "Blood for the Blood God!", "hand")
    for pid in ["p1", "p2", "p3"][:deaths]:
        obj = put(s, "Grizzly Bears", "battlefield", pid)
        act(s, pid, type="move", card_ids=[obj.id], to={"player": pid, "zone": "graveyard"})
    spare = put(s, "Sol Ring", "hand")
    return s, source, spare


def resolve_bloodgod(s, source, spare, generic):
    mana(s, C=generic, B=2, R=1)
    before = {pid: s.state.players[pid].life for pid in ["p1", "p2", "p3"]}
    act(s, "p1", type="cast_spell", card_id=source.id, sources=[])
    settle(s)
    assert source.zone == "p1:exile" and spare.zone == "p1:graveyard"
    assert len(s.state.zones["p1:hand"]) == 8
    assert s.state.players["p1"].life == before["p1"]
    assert all(s.state.players[pid].life == before[pid] - 8 for pid in ["p2", "p3"])
    assert not s.state.players["p1"].mana
    roundtrip(s)


def test_paid_spell_discard_draw_damage_and_self_exile(cards):
    s, source, spare = setup(cards, 0)
    resolve_bloodgod(s, source, spare, 8)


def test_discount_counts_deaths_under_all_players_control(cards):
    s, source, spare = setup(cards, 3)
    resolve_bloodgod(s, source, spare, 5)


def test_true_cold_resolves_from_retained_death_history(cards, tmp_path):
    import subprocess
    import sys

    s, source, spare = setup(cards, 3)
    saved = tmp_path / "bloodgod49.json"
    saved.write_text(s.state.model_dump_json())
    code = r"""
import sys
from pathlib import Path
from app.cards.repository import CardRepository
from app.cards.images import ImageStore
from app.game.session import GameSession
from app.game.state import GameState
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana
from tests.test_rules_library_look import settle
from tests.test_rules_designations import roundtrip
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
mana(s,C=5,B=2,R=1)
before={p:s.state.players[p].life for p in ['p1','p2','p3']}
act(s,'p1',type='cast_spell',card_id=sys.argv[3],sources=[])
settle(s)
assert s.state.cards[sys.argv[3]].zone=='p1:exile'
assert s.state.cards[sys.argv[4]].zone=='p1:graveyard'
assert len(s.state.zones['p1:hand'])==8
assert all(s.state.players[p].life==before[p]-8 for p in ['p2','p3'])
assert not s.state.players['p1'].mana
roundtrip(s)
"""
    result = subprocess.run(
        [sys.executable, "-c", code, str(saved), str(cards.db_path), source.id, spare.id],
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert result.returncode == 0, result.stdout + result.stderr

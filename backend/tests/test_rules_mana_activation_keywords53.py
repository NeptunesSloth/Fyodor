"""Selected mana-ability provenance has explicit cold and legacy boundaries."""

import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

from app.rules import casting
from app.rules import mana as M
from app.rules.plan import Plan
from tests.game_helpers import act
from tests.test_rules_table_activation_modifiers52 import cards as cards
from tests.test_rules_table_activation_modifiers52_boundaries import setup_taxed_loot


def test_unknown_old_and_ordinary_profiles_never_inherit_source_exhaust(cards):
    s, source = setup_taxed_loot(cards)
    ch = Plan(s.state, "p1", cards, None).ch(source)
    ability = next(a for _, a in casting.mana_abilities(s.state, source, cards))
    assert ability.activation_keyword == "exhaust"
    assert casting.mana_activation_cost(s.state, source, ch, ability, cards).text() == "{1}{G}"
    old = asdict(ability)
    old.pop("activation_keyword")
    legacy = M.ManaAbility(**old)
    assert legacy.activation_keyword is None
    assert casting.mana_activation_cost(s.state, source, ch, legacy, cards).text() == "{3}{G}"
    ordinary = M.parse_mana_ability("{G}, {T}: Add three mana of any one color.")
    assert ordinary is not None and ordinary.activation_keyword is None
    assert casting.mana_activation_cost(s.state, source, ch, ordinary, cards).text() == "{3}{G}"


def test_opponents_boom_does_not_reduce_selected_mana_exhaust(cards):
    s, source = setup_taxed_loot(cards)
    boom = next(c for c in s.state.cards.values() if c.name == "Boom Scholar")
    act(s, "p1", type="set_controller", card_ids=[boom.id], player="p2")
    ch = Plan(s.state, "p1", cards, None).ch(source)
    ability = next(a for _, a in casting.mana_abilities(s.state, source, cards))
    assert casting.mana_activation_cost(s.state, source, ch, ability, cards).text() == "{3}{G}"


def test_actual_taxed_exhaust_mana_true_cold(cards, tmp_path):
    s, source = setup_taxed_loot(cards)
    act(s, "p1", type="add_mana", player="p1", mana={"C": 1, "G": 1})
    index = next(i for i, _ in casting.mana_abilities(s.state, source, cards))
    saved = tmp_path / "game.json"
    saved.write_text(s.state.model_dump_json())
    code = r"""
import sys
from pathlib import Path
from app.cards.repository import CardRepository
from app.cards.images import ImageStore
from app.game.session import GameSession
from app.game.state import GameState
from app.rules import mana_units
from tests.game_helpers import act
from tests.test_rules_activated_copy_family import answer
from tests.test_rules_designations import roundtrip
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
act(s,'p1',type='activate_ability',card_id=sys.argv[3],ability=int(sys.argv[4]),mana_choice='R',sources=[])
answer(s)
assert s.state.cards[sys.argv[3]].tapped and mana_units.visible_pool(s.state,'p1')=={'R':3}
roundtrip(s)
"""
    result = subprocess.run(
        [sys.executable, "-c", code, str(saved), str(cards.db_path), source.id, str(index)],
        cwd=Path(M.__file__).resolve().parents[2],
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert result.returncode == 0, result.stdout + result.stderr

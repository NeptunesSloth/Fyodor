"""Regression tests from the independent review of rules batch 2 (615.7 shields, 614.16 token copies)."""

from tests.test_rules_combat import attack, automate, creature, table
from tests.test_rules_suspend import until


def test_shield_on_p2_does_not_protect_p3(cards):
    s = table(cards, players=3)
    brute = creature(s, "p1", "Brute", "2/2")
    automate(s)
    s.state.rules.prevention["p2"] = 5
    attack(s, (brute, "p3"))
    until(s, lambda s: s.state.turn.phase == "main2")
    assert s.state.players["p3"].life == 38, s.state.players["p3"].life
    assert s.state.rules.prevention.get("p2") == 5


from tests.game_helpers import act  # noqa: E402
from tests.test_rules_attachments import build, to_hand, token  # noqa: E402
from tests.test_rules_copy import card_db, on_battlefield, pay  # noqa: F401,E402
from tests.test_rules_effects import pass_until_stack_empty  # noqa: E402
from tests.test_rules_replacements2 import OJER_TAQ  # noqa: E402


def test_ojer_taq_triples_a_token_copy_of_a_creature(cards):
    s = build(cards, "Grizzly Bears", "Cackling Counterpart")
    bear = on_battlefield(s, "Grizzly Bears")
    token(s, "p1", "Ojer Taq, Deepest Foundation", "6/6", "Vigilance\n" + OJER_TAQ)
    cc = to_hand(s, "Cackling Counterpart")
    pay(s, U=2, C=1)
    act(s, "p1", type="cast_spell", card_id=cc.id, targets=[bear.id])
    pass_until_stack_empty(s)
    toks = [c for c in s.state.cards.values() if c.is_token and c.name == "Grizzly Bears"]
    assert len(toks) == 3, len(toks)

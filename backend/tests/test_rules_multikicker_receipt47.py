"""Native colored-cost receipt boundary following the platform quantity repair."""
import pytest

from tests import test_rules_exile_cast_outcomes45_foundation as gameplay
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_look import settle

cards=gameplay.cards


@pytest.mark.xfail(strict=True,reason='Investigating native long colored-cost payment receipt within platform kicker range')
def test_colored_multikicker_actual_affordable_sixty_seven_count_retains_full_payment_receipt(cards):
    s=gameplay.setup(cards,'Gnarlid Pack')
    spell=put(s,'Gnarlid Pack','hand')
    mana(s,G=68,C=68)
    act(s,'p1',type='cast_spell',card_id=spell.id,kicker=67)
    settle(s)
    assert s.state.cards[spell.id].zone=='p1:battlefield'
    assert s.state.cards[spell.id].counters.get('+1/+1',0)==67
    roundtrip(s)

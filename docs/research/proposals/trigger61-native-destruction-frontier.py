"""Native existing Wrath confirms the replacement-choice frontier is preexisting."""
from tests.test_rules_trigger_shared_colors61 import cards  # noqa: F401
from tests.conftest import settings  # noqa: F401
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_declaration_requirements33 import start
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_trigger_library_win53 import cast
from tests.test_rules_library_look import settle
from tests.game_helpers import act


def test_native_existing_wrath_asks_owner_to_choose_between_two_umbra_replacements(cards):
    names=['Grizzly Bears','Hyena Umbra','Spider Umbra','Wrath of God','Island']
    s=table(cards,names,names,names)
    start(s)
    act(s,'p1',type='set_prefs',hold_priority=True)
    bear=put(s,'Grizzly Bears','battlefield')
    hyena=cast(s,'Hyena Umbra',{'W':1},[bear.id])
    spider=cast(s,'Spider Umbra',{'G':1},[bear.id])
    cast(s,'Wrath of God',{'C':2,'W':2})
    d=s.state.rules.decision
    assert d is not None and 'destruction replacement' in d.prompt
    chosen=next(o.id for o in d.options if 'Spider Umbra' in o.label)
    act(s,d.player,type='choose',decision_id=d.id,option_ids=[chosen])
    settle(s)
    assert spider.zone=='p1:graveyard' and bear.zone==hyena.zone=='p1:battlefield'
    roundtrip(s)

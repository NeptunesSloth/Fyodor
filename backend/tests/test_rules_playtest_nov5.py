"""-- playtest fixes (nov 5) -- Reports from a 2D-table game night, each reproduced with real Oracle text."""

from __future__ import annotations

import pytest

from app.game.session import GameSession
from app.game.state import GameState
from tests.game_helpers import act, mana_pool
from tests.pod_c_kit import ch, mana, put, settle, table, to_hand
from tests.test_rules_effects import replay_matches
from tests.test_rules_wave12a_counters_keywords import real

LANTERN = real('Chromatic Lantern', '{3}', 3, 'Artifact',
               'Lands you control have "{T}: Add one mana of any color."\n{T}: Add one mana of any color.')
SILVERQUILL = real('Silverquill, the Disputant', '{2}{W}{B}', 4, 'Legendary Creature — Elder Dragon',
                   'Flying, vigilance\nEach instant and sorcery spell you cast has casualty 1. (As you cast that spell, you may sacrifice a '
                   'creature with power 1 or greater. When you do, copy the spell and you may choose new targets for the copy.)',
                   ("4", "4"), "WB")
GINGERBRUTE = real('Gingerbrute', '{1}', 1, 'Artifact Creature — Food Golem',
                   "Haste (This creature can attack and {T} as soon as it comes under your control.)\n{1}: This creature can't be blocked "
                   "this turn except by creatures with haste.\n{2}, {T}, Sacrifice this creature: You gain 3 life.", ("1", "1"))
EXTRA = [LANTERN, SILVERQUILL, GINGERBRUTE]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database
    from tests.fixtures.cards import fixture_cards

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def saved(s):
    loaded = GameSession(GameState.model_validate_json(s.state.model_dump_json()), cards=s.cards)
    assert loaded.state.model_dump(mode="json") == s.state.model_dump(mode="json")
    return loaded


def lands(s, name, n, pid="p1"):
    """``n`` of the player's cards of that name (not yet on the battlefield) put onto the battlefield."""
    out = []
    for c in [c for c in s.state.cards.values() if c.name == name and c.owner == pid and not c.zone.endswith(":battlefield")][:n]:
        act(s, pid, type="move", card_ids=[c.id], to={"player": pid, "zone": "battlefield"})
        out.append(s.state.cards[c.id])
    assert len(out) == n
    return out


def any_color(s, c):
    return next(ab.index for ab in ch(s, c).abilities if ab.text == "{T}: Add one mana of any color.")


# -- Chromatic Lantern --------------------------------------------------------------------------------------------------------------------


def test_lantern_forest_taps_for_black_through_the_granted_ability(cards):
    s = table(cards, ["Chromatic Lantern"])
    put(s, "Chromatic Lantern")
    forest = put(s, "Forest")
    act(s, "p1", type="activate_ability", card_id=forest.id, ability=any_color(s, forest), mana_choice="B")
    settle(s)
    assert mana_pool(s) == {"B": 1}
    replay_matches(s)
    saved(s)


def self_pay(s):
    for prefs in s.state.rules.prefs.values():
        prefs.payment = "self"  # the table default: players tap their own mana


def tap(s, c, pid="p1"):
    """The table's tap gesture (double-click / T / a click in the payment prompt): the frontend's guess of the ability is the first one."""
    act(s, pid, type="activate_ability", card_id=c.id, ability=0, tap_for_mana=True)


def labels(s):
    return [o.label for o in s.state.rules.decision.options]


def pick(s, label):
    d = s.state.rules.decision
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[next(o.id for o in d.options if o.label == label)])


def test_tapping_a_forest_under_lantern_asks_which_mana(cards):
    """The playtest report: a Forest tapped from the table added {G} (its basic land type's ability) and never black. Tapped under Chromatic
    Lantern it has two mana abilities (305.6, 613.1f): the player picks the mana ({G} once: both abilities only tap for mana)."""
    s = table(cards, ["Chromatic Lantern"])
    put(s, "Chromatic Lantern")
    forest = put(s, "Forest")
    s = saved(s)
    tap(s, forest)
    assert s.state.rules.decision.prompt == "Which mana should Forest add?"
    assert labels(s) == ["{G}", "{W}", "{U}", "{B}", "{R}", "Cancel"]
    s = saved(s)
    pick(s, "{B}")
    assert mana_pool(s) == {"B": 1} and s.state.cards[forest.id].tapped
    replay_matches(s)
    saved(s)


def test_tapping_a_plain_forest_adds_green_without_asking(cards):
    s = table(cards)
    forest = put(s, "Forest")
    tap(s, forest)
    assert s.state.rules.decision is None and mana_pool(s) == {"G": 1}
    replay_matches(s)


def test_cancelling_the_question_taps_nothing(cards):
    s = table(cards, ["Chromatic Lantern"])
    put(s, "Chromatic Lantern")
    forest = put(s, "Forest")
    tap(s, forest)
    pick(s, "Cancel")
    assert s.state.rules.decision is None and not s.state.cards[forest.id].tapped and mana_pool(s) == {}
    replay_matches(s)


def test_forests_under_lantern_pay_for_murder_when_tapped_in_the_payment_prompt(cards):
    """At the table players tap their own mana: tapping Forests in Murder's payment prompt adds the black it needs (both abilities only tap
    for mana, so the one that helps the payment is used, as for an "any color" ability)."""
    s = table(cards, ["Chromatic Lantern", "Murder", "Grizzly Bears"])
    self_pay(s)
    put(s, "Chromatic Lantern")
    forests = lands(s, "Forest", 3)
    bears = put(s, "Grizzly Bears")
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Murder").id, targets=[bears.id])
    assert s.state.rules.decision.display["kind"] == "tap_mana"
    tap(s, forests[0])
    tap(s, forests[1])
    s = saved(s)
    assert s.state.rules.decision.display["remaining"] == "{1}"
    tap(s, forests[2])
    settle(s)
    assert s.state.cards[bears.id].zone == "p1:graveyard" and all(s.state.cards[f.id].tapped for f in forests)
    replay_matches(s)
    saved(s)


def test_a_pain_land_tapped_while_paying_asks_inside_the_payment(cards):
    """Shivan Reef: "{T}: Add {C}." and "{T}: Add {U} or {R}. Shivan Reef deals 1 damage to you." The damage is the player's call: the
    question is nested in the payment prompt, which comes back with the mana added."""
    s = table(cards, ["Shivan Reef", "Lightning Bolt"])
    self_pay(s)
    reef = put(s, "Shivan Reef")
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Lightning Bolt").id, targets=["p2"])
    tap(s, reef)
    d = s.state.rules.decision
    assert d.prompt == "Which mana should Shivan Reef add?"
    assert labels(s) == ["{C}", "{U} ({T}: Add {U} or {R}. Shivan Reef deals 1 damage to you.)",
                         "{R} ({T}: Add {U} or {R}. Shivan Reef deals 1 damage to you.)", "Cancel"]
    s = saved(s)
    life = s.state.players["p1"].life
    pick(s, "{R} ({T}: Add {U} or {R}. Shivan Reef deals 1 damage to you.)")
    settle(s)
    assert s.state.players["p2"].life == 37 and s.state.players["p1"].life == life - 1
    replay_matches(s)
    saved(s)


def test_cancelling_inside_the_payment_brings_the_payment_back(cards):
    s = table(cards, ["Shivan Reef", "Lightning Bolt"])
    self_pay(s)
    reef = put(s, "Shivan Reef")
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Lightning Bolt").id, targets=["p2"])
    tap(s, reef)
    pick(s, "Cancel")
    d = s.state.rules.decision
    assert d is not None and d.display["kind"] == "tap_mana" and not s.state.cards[reef.id].tapped
    replay_matches(s)


# -- Silverquill, the Disputant -------------------------------------------------------------------------------------------------------------


def silverquill(cards, *mine, theirs=()):
    s = table(cards, ["Silverquill, the Disputant", *mine], theirs)
    put(s, "Silverquill, the Disputant")
    return s


CASUALTY = "Casualty 1: sacrifice a creature with power 1 or greater"


def test_casting_from_the_table_asks_for_silverquills_casualty(cards):
    """The playtest report: "Silverquill not triggering on instant/sorcery cast". Casualty is an optional additional cost (702.153a) announced
    as the spell is cast (601.2b); the table's drag-to-cast never announced it (only the card menu's "Cast and sacrifice …" did), so it was
    never asked. Cast from the table (``ask_optional``), the caster is asked; the sacrifice is paid as a cost and the copy follows."""
    s = silverquill(cards, "Lightning Bolt", "Grizzly Bears", theirs=["Grizzly Bears", "Albino Troll"])
    put(s, "Grizzly Bears")
    bob_bears, troll = put(s, "Grizzly Bears", "p2"), put(s, "Albino Troll", "p2")
    mana(s, R=1)
    bolt = to_hand(s, "Lightning Bolt")
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=[bob_bears.id], ask_optional=True)
    d = s.state.rules.decision
    assert d is not None and d.player == "p1" and d.min_choices == 0
    assert labels(s) == [CASUALTY]
    s = saved(s)
    pick(s, CASUALTY)
    asked = settle(s, "Grizzly Bears", "Albino Troll")
    assert {s.state.cards[i].name for i in s.state.zones["p1:graveyard"]} >= {"Grizzly Bears", "Lightning Bolt"}, asked
    assert s.state.cards[bob_bears.id].zone == "p2:graveyard" and s.state.cards[troll.id].zone == "p2:graveyard", asked
    replay_matches(s)
    saved(s)


def test_declining_casualty_casts_the_spell_alone(cards):
    s = silverquill(cards, "Lightning Bolt", "Grizzly Bears")
    bears = put(s, "Grizzly Bears")
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Lightning Bolt").id, targets=["p2"], ask_optional=True)
    d = s.state.rules.decision
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[])
    settle(s)
    assert s.state.players["p2"].life == 37 and s.state.cards[bears.id].zone == "p1:battlefield"
    replay_matches(s)
    saved(s)


def test_a_spell_with_nothing_optional_is_cast_without_a_question(cards):
    s = table(cards, ["Lightning Bolt"])
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Lightning Bolt").id, targets=["p2"], ask_optional=True)
    settle(s)
    assert s.state.players["p2"].life == 37
    replay_matches(s)


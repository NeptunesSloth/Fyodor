"""Wave 6E: static and spell wordings from the catch-all gap family, researched against CR 2026-09-25.

* Ward written with other keywords on one line ("Vigilance, trample, ward {1}"): each keyword is its own ability (702.1),
  the ward piece triggers like a lone one (702.21a); "ward—Pay 3 life" stays manual.
* Anthems granting triggered keywords (613.1f): undying (702.93a), persist (702.79a), prowess (702.108a), exalted (702.83a,
  each instance separately, 702.83b): Mikaeus the Unhallowed, Sublime Archangel, Bria.
* A choice between additional costs (601.2b announced before targets, 601.2f in the total cost, 601.2h paid with the
  rest, 118.3): Demand Answers, Bitter Triumph, Eaten Alive, Annihilating Glare.
* Anthems over two groups ("Skeletons you control and other Zombies you control"): Death Baron, Caterwauling Boggart,
  Timber Protector.

Every scenario checks the replay; the longer ones also reload the game from its saved history.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.cards.importer import build_database
from app.config import Settings
from app.rules import coverage, statics
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditionals import settle, token_of, until
from tests.test_rules_effects import replay_matches
from tests.test_rules_wave6c_tokens_pumps import build, chars, mana, pt, put, reloaded, to_hand

# Real Oracle wording (the local card database, current).
EXTRA = [
    card('Eshki Dragonclaw', set_code='tst', number='E01', mana_cost='{1}{G}{U}{R}', cmc=4.0, type_line='Legendary Creature — Human Warrior', oracle_text="Vigilance, trample, ward {1}\nAt the beginning of combat on your turn, if you've cast both a creature spell and a noncreature spell this turn, draw a card and put two +1/+1 counters on Eshki Dragonclaw.", power='4', toughness='4', colors=['G', 'R', 'U'], color_identity=['G', 'R', 'U'], keywords=['Vigilance', 'Trample', 'Ward']),  # noqa: E501
    card('Sedgemoor Witch', set_code='tst', number='E02', mana_cost='{2}{B}', cmc=3.0, type_line='Creature — Human Warlock', oracle_text='Menace\nWard—Pay 3 life. (Whenever this creature becomes the target of a spell or ability an opponent controls, counter it unless that player pays 3 life.)\nMagecraft — Whenever you cast or copy an instant or sorcery spell, create a 1/1 black and green Pest creature token with "When this token dies, you gain 1 life."', power='3', toughness='2', colors=['B'], color_identity=['B'], keywords=['Magecraft', 'Menace', 'Ward']),  # noqa: E501
    card('Mikaeus, the Unhallowed', set_code='tst', number='E03', mana_cost='{3}{B}{B}{B}', cmc=6.0, type_line='Legendary Creature — Zombie Cleric', oracle_text="Intimidate (This creature can't be blocked except by artifact creatures and/or creatures that share a color with it.)\nWhenever a Human deals damage to you, destroy it.\nOther non-Human creatures you control get +1/+1 and have undying. (When a creature with undying dies, if it had no +1/+1 counters on it, return it to the battlefield under its owner's control with a +1/+1 counter on it.)", power='5', toughness='5', colors=['B'], color_identity=['B'], keywords=['Intimidate']),  # noqa: E501
    card('Death Baron', set_code='tst', number='E04', mana_cost='{1}{B}{B}', cmc=3.0, type_line='Creature — Zombie Wizard', oracle_text='Skeletons you control and other Zombies you control get +1/+1 and have deathtouch. (Any amount of damage they deal to a creature is enough to destroy it.)', power='2', toughness='2', colors=['B'], color_identity=['B'], keywords=[]),  # noqa: E501
    card('Sublime Archangel', set_code='tst', number='E05', mana_cost='{2}{W}{W}', cmc=4.0, type_line='Creature — Angel', oracle_text='Flying\nExalted (Whenever a creature you control attacks alone, that creature gets +1/+1 until end of turn.)\nOther creatures you control have exalted. (If a creature has multiple instances of exalted, each triggers separately.)', power='4', toughness='3', colors=['W'], color_identity=['W'], keywords=['Flying', 'Exalted']),  # noqa: E501
    card('Bria, Riptide Rogue', set_code='tst', number='E06', mana_cost='{2}{U}{R}', cmc=4.0, type_line='Legendary Creature — Otter Rogue', oracle_text="Prowess (Whenever you cast a noncreature spell, this creature gets +1/+1 until end of turn.)\nOther creatures you control have prowess. (If a creature has multiple instances of prowess, each triggers separately.)\nWhenever you cast a noncreature spell, target creature you control can't be blocked this turn.", power='3', toughness='3', colors=['R', 'U'], color_identity=['R', 'U'], keywords=['Prowess']),  # noqa: E501
    card('Caterwauling Boggart', set_code='tst', number='E07', mana_cost='{3}{R}', cmc=4.0, type_line='Creature — Goblin Shaman', oracle_text="Goblins you control and Elementals you control have menace. (They can't be blocked except by two or more creatures.)", power='2', toughness='2', colors=['R'], color_identity=['R'], keywords=[]),  # noqa: E501
    card('Timber Protector', set_code='tst', number='E08', mana_cost='{4}{G}', cmc=5.0, type_line='Creature — Treefolk Warrior', oracle_text='Other Treefolk creatures you control get +1/+1.\nOther Treefolk and Forests you control have indestructible.', power='4', toughness='6', colors=['G'], color_identity=['G'], keywords=[]),  # noqa: E501
    card('Demand Answers', set_code='tst', number='E09', mana_cost='{1}{R}', cmc=2.0, type_line='Instant', oracle_text='As an additional cost to cast this spell, sacrifice an artifact or discard a card.\nDraw two cards.', colors=['R'], color_identity=['R'], keywords=[]),  # noqa: E501
    card('Bitter Triumph', set_code='tst', number='E10', mana_cost='{1}{B}', cmc=2.0, type_line='Instant', oracle_text='As an additional cost to cast this spell, discard a card or pay 3 life.\nDestroy target creature or planeswalker.', colors=['B'], color_identity=['B'], keywords=[]),  # noqa: E501
    card('Eaten Alive', set_code='tst', number='E11', mana_cost='{B}', cmc=1.0, type_line='Sorcery', oracle_text='As an additional cost to cast this spell, sacrifice a creature or pay {3}{B}.\nExile target creature or planeswalker.', colors=['B'], color_identity=['B'], keywords=[]),  # noqa: E501
    card('Annihilating Glare', set_code='tst', number='E12', mana_cost='{B}', cmc=1.0, type_line='Sorcery', oracle_text='As an additional cost to cast this spell, pay {4} or sacrifice an artifact or creature.\nDestroy target creature or planeswalker.', colors=['B'], color_identity=['B'], keywords=[]),  # noqa: E501
    card('Silvergill Adept', set_code='tst', number='E13', mana_cost='{1}{U}', cmc=2.0, type_line='Creature — Merfolk Wizard', oracle_text='As an additional cost to cast this spell, reveal a Merfolk card from your hand or pay {3}.\nWhen this creature enters, draw a card.', power='2', toughness='1', colors=['U'], color_identity=['U'], keywords=[]),  # noqa: E501
]
FULL = ["Eshki Dragonclaw", "Mikaeus, the Unhallowed", "Death Baron", "Sublime Archangel", "Bria, Riptide Rogue",
        "Caterwauling Boggart", "Timber Protector", "Demand Answers", "Bitter Triumph", "Eaten Alive",
        "Annihilating Glare"]
STILL_MANUAL = {
    "Sedgemoor Witch": "Ward",  # (ward—Pay 3 life: a cost the ward trigger doesn't read)
    "Silvergill Adept": "reveal a Merfolk card",  # (revealing a card as a cost: not paid by the engine)
}


@pytest.fixture()
def card_db(settings: Settings) -> Path:
    settings.ensure_dirs()
    build_database(fixture_cards() + EXTRA, settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def gone(s, c):
    return c.id not in s.state.cards or not s.state.cards[c.id].zone.endswith(":battlefield")


def named(s, name, pid="p1"):
    return next(c for c in s.state.cards.values() if c.name == name and c.owner == pid)


# -- coverage ----------------------------------------------------------------------------------------------------
def test_definitions_of_the_full_cards():
    from tests.test_rules_scripts import ch as characteristics

    for c in EXTRA:
        if c["name"] in FULL:
            chs = characteristics(c["name"], c["type_line"], c["oracle_text"])
            assert coverage.of_characteristics(chs).level == "FULL", (c["name"], coverage.of_characteristics(chs).manual_parts)


def test_still_manual_lines():
    from tests.test_rules_scripts import ch as characteristics

    for c in EXTRA:
        if c["name"] not in STILL_MANUAL:
            continue
        chs = characteristics(c["name"], c["type_line"], c["oracle_text"])
        level = coverage.of_characteristics(chs)
        assert level.level != "FULL", c["name"]
        assert STILL_MANUAL[c["name"]] in " ".join(level.manual_parts), (c["name"], level.manual_parts)


# -- ward among other keywords (702.21a) ---------------------------------------------------------------------------
def test_ward_written_after_other_keywords_counters_unless_paid(cards):
    s = build(cards, "Lightning Bolt")
    eshki = token_of(s, "p2", "Eshki", "Token Creature — Human Warrior", "4/4", "Vigilance, trample, ward {1}")
    assert "ward" in chars(s, eshki).keywords and "trample" in chars(s, eshki).keywords
    bolt = to_hand(s, "Lightning Bolt")
    mana(s, R=1, C=1)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=[eshki.id])
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.player == "p1")
    d = s.state.rules.decision
    assert "{1}" in d.prompt
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["decline"])
    until(s, lambda s: not s.state.zones.get("stack"))
    assert s.state.cards[eshki.id].damage == 0 and s.state.cards[bolt.id].zone == "p1:graveyard"
    replay_matches(reloaded(s))


def test_ward_paid_lets_the_spell_resolve(cards):
    s = build(cards, "Lightning Bolt")
    eshki = token_of(s, "p2", "Eshki", "Token Creature — Human Warrior", "4/4", "Vigilance, trample, ward {1}")
    bolt = to_hand(s, "Lightning Bolt")
    mana(s, R=1, C=1)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=[eshki.id])
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.player == "p1")
    act(s, "p1", type="choose", decision_id=s.state.rules.decision.id, option_ids=["pay"])
    until(s, lambda s: not s.state.zones.get("stack"))
    assert s.state.cards[eshki.id].damage == 3
    replay_matches(s)


def test_ward_with_a_life_cost_in_a_keyword_line_stays_manual():
    assert not coverage._keyword_supported("ward", "Menace, ward—Pay 3 life")
    assert coverage._keyword_supported("ward", "Flying, ward {2}")
    assert not coverage._keyword_supported("ward", "Flying, ward {2}, ward—Discard a card")


# -- anthems granting triggered keywords (613.1f) ------------------------------------------------------------------
def test_anthem_parses_triggered_keyword_grants():
    mik = statics.parse("Other non-Human creatures you control get +1/+1 and have undying.")
    assert mik is not None and mik["p"] == 1 and mik["grants"] == ["Undying"]
    arch = statics.parse("Other creatures you control have exalted.")
    assert arch is not None and arch["grants"] == ["Exalted"]
    assert statics.parse("Other creatures you control have cascade.") is None  # (not a grant the engine reads)


def test_mikaeus_gives_undying_to_non_humans_only(cards):
    s = build(cards, "Mikaeus, the Unhallowed", "Grizzly Bears", "Murder")
    put(s, "Mikaeus, the Unhallowed")
    bears = put(s, "Grizzly Bears")
    human = token_of(s, "p1", "Villager", "Token Creature — Human", "1/1")
    assert pt(s, bears) == (3, 3) and pt(s, human) == (1, 1)
    assert "undying" in chars(s, bears).keywords and "undying" not in chars(s, human).keywords
    murder = to_hand(s, "Murder")
    mana(s, B=3)
    act(s, "p1", type="cast_spell", card_id=murder.id, targets=[bears.id])
    settle(s)
    back = s.state.cards[bears.id]
    assert back.zone == "p1:battlefield" and back.counters == {"+1/+1": 1} and pt(s, back) == (4, 4)
    s = reloaded(s)
    replay_matches(s)
    # with a +1/+1 counter on it, undying does nothing (702.93a)
    act(s, "p1", type="move", card_ids=[murder.id], to={"zone": "hand"})
    mana(s, B=3)
    act(s, "p1", type="cast_spell", card_id=murder.id, targets=[bears.id])
    settle(s)
    assert s.state.cards[bears.id].zone == "p1:graveyard"
    replay_matches(s)


def test_sublime_archangel_each_instance_of_exalted_triggers(cards):
    s = build(cards, "Sublime Archangel")
    put(s, "Sublime Archangel")
    bear = token_of(s, "p1", "Bear", "Token Creature — Bear", "2/2", "Haste")
    token_of(s, "p1", "Squire", "Token Creature — Human", "1/2")
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_attackers")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": bear.id, "target": "p2"}])
    until(s, lambda s: not s.state.zones.get("stack") and s.state.turn.phase != "declare_attackers")
    # the Archangel's own exalted, and the granted one on the Bear and on the Squire: three instances (702.83b)
    assert pt(s, bear) == (5, 5)
    replay_matches(reloaded(s))


def test_bria_gives_prowess_to_other_creatures(cards):
    s = build(cards, "Bria, Riptide Rogue", "Lightning Bolt")
    bria = put(s, "Bria, Riptide Rogue")
    bear = token_of(s, "p1", "Bear", "Token Creature — Bear", "2/2")
    target = token_of(s, "p2", "Target", "Token Creature — Wall", "0/9")
    bolt = to_hand(s, "Lightning Bolt")
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=[target.id])
    settle(s)
    assert pt(s, bear) == (3, 3) and pt(s, bria) == (4, 4)
    replay_matches(reloaded(s))


# -- anthems over two groups ---------------------------------------------------------------------------------------
def test_union_subjects_parse():
    baron = statics.parse("Skeletons you control and other Zombies you control get +1/+1 and have deathtouch.")
    assert baron is not None and baron["who"].startswith(statics.UNION) and baron["keywords"] == ["deathtouch"]
    assert statics.parse("Skeletons you control and other Zombies you control can't block.") is None  # (rules: not read)
    assert statics.parse("Goblins you control and Elementals you control have menace.") is not None


def test_death_baron_skeletons_and_other_zombies(cards):
    s = build(cards, "Death Baron")
    baron = put(s, "Death Baron")
    skel = token_of(s, "p1", "Skel", "Token Creature — Skeleton", "1/1")
    zomb = token_of(s, "p1", "Zomb", "Token Creature — Zombie", "2/2")
    elf = token_of(s, "p1", "Elfy", "Token Creature — Elf", "1/1")
    theirs = token_of(s, "p2", "Their Zombie", "Token Creature — Zombie", "2/2")
    assert pt(s, skel) == (2, 2) and "deathtouch" in chars(s, skel).keywords
    assert pt(s, zomb) == (3, 3) and "deathtouch" in chars(s, zomb).keywords
    assert pt(s, baron) == (2, 2) and "deathtouch" not in chars(s, baron).keywords  # ("other" Zombies)
    assert pt(s, elf) == (1, 1) and pt(s, theirs) == (2, 2)
    replay_matches(reloaded(s))


def test_a_skeleton_death_baron_pumps_itself(cards):
    s = build(cards, "Death Baron")
    baron = put(s, "Death Baron")
    act(s, "p1", type="move", card_ids=[baron.id], to={"zone": "hand"})
    skel_baron = token_of(s, "p1", "Skeleton Baron", "Token Creature — Skeleton Zombie", "2/2",
                          "Skeletons you control and other Zombies you control get +1/+1 and have deathtouch.")
    assert pt(s, skel_baron) == (3, 3)  # a Skeleton you control, though not an "other" Zombie
    replay_matches(s)


def test_timber_protector_treefolk_and_forests(cards):
    s = build(cards, "Timber Protector")
    prot = put(s, "Timber Protector")
    forest = put(s, "Forest")
    tree = token_of(s, "p1", "Tree", "Token Creature — Treefolk", "2/2")
    assert "indestructible" in chars(s, forest).keywords and "indestructible" in chars(s, tree).keywords
    assert pt(s, tree) == (3, 3) and "indestructible" not in chars(s, prot).keywords
    replay_matches(s)


def test_caterwauling_boggart_goblins_and_elementals(cards):
    s = build(cards, "Caterwauling Boggart")
    put(s, "Caterwauling Boggart")
    elem = token_of(s, "p1", "Elem", "Token Creature — Elemental", "1/1")
    elf = token_of(s, "p1", "Elfy", "Token Creature — Elf", "1/1")
    assert "menace" in chars(s, elem).keywords and "menace" not in chars(s, elf).keywords
    replay_matches(s)


# -- a choice between additional costs (601.2b, 601.2f, 601.2h) ---------------------------------------------------
def test_either_costs_parse():
    from app.rules import costs

    sides = costs.parse_additional_cost("pay {4} or sacrifice an artifact or creature")
    assert sides is not None and [costs.either_label(c) for c in sides.either] == ["Pay {4}", "Sacrifice an artifact or creature"]
    assert costs.parse_additional_cost("reveal a Merfolk card from your hand or pay {3}") is None
    assert costs.parse_additional_cost("forage or pay {B}") is None


def test_bitter_triumph_asks_which_cost_and_pays_life(cards):
    s = build(cards, "Bitter Triumph", "Grizzly Bears")
    to_hand(s, "Grizzly Bears")
    victim = token_of(s, "p2", "Victim", "Token Creature — Bear", "2/2")
    triumph = to_hand(s, "Bitter Triumph")
    mana(s, B=1, C=1)
    act(s, "p1", type="cast_spell", card_id=triumph.id, targets=[victim.id])
    d = s.state.rules.decision
    assert d is not None and d.player == "p1" and [o.label for o in d.options] == ["Discard a card", "Pay 3 life"]
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["either:1"])
    assert s.state.players["p1"].life == 37
    settle(s)
    assert gone(s, victim)
    assert named(s, "Grizzly Bears").zone == "p1:hand"
    s = reloaded(s)
    replay_matches(s)


def test_bitter_triumph_discards_a_card_when_chosen(cards):
    s = build(cards, "Bitter Triumph", "Grizzly Bears")
    bears = to_hand(s, "Grizzly Bears")
    victim = token_of(s, "p2", "Victim", "Token Creature — Bear", "2/2")
    triumph = to_hand(s, "Bitter Triumph")
    mana(s, B=1, C=1)
    act(s, "p1", type="cast_spell", card_id=triumph.id, targets=[victim.id])
    act(s, "p1", type="choose", decision_id=s.state.rules.decision.id, option_ids=["either:0"])
    settle(s)
    assert s.state.cards[bears.id].zone == "p1:graveyard" and s.state.players["p1"].life == 40
    assert gone(s, victim)
    replay_matches(s)


def test_bitter_triumph_with_an_empty_hand_pays_life_without_asking(cards):
    s = build(cards, "Bitter Triumph")
    victim = token_of(s, "p2", "Victim", "Token Creature — Bear", "2/2")
    triumph = to_hand(s, "Bitter Triumph")
    for c in list(s.state.zones["p1:hand"]):
        if c != triumph.id:
            act(s, "p1", type="move", card_ids=[c], to={"zone": "library"})
    mana(s, B=1, C=1)
    act(s, "p1", type="cast_spell", card_id=triumph.id, targets=[victim.id])
    settle(s)
    assert s.state.players["p1"].life == 37 and gone(s, victim)
    replay_matches(s)


def test_eaten_alive_without_a_creature_pays_the_extra_mana(cards):
    s = build(cards, "Eaten Alive")
    victim = token_of(s, "p2", "Victim", "Token Creature — Bear", "2/2")
    eaten = to_hand(s, "Eaten Alive")
    mana(s, B=2)
    with pytest.raises(Exception):  # ({B} plus {3}{B}: two black mana aren't enough)
        act(s, "p1", type="cast_spell", card_id=eaten.id, targets=[victim.id])
    if s.state.rules.decision is not None:  # (asked for the mana payment: cancelled)
        act(s, "p1", type="choose", decision_id=s.state.rules.decision.id, option_ids=[])
    assert s.state.cards[eaten.id].zone == "p1:hand"
    mana(s, C=3)
    act(s, "p1", type="cast_spell", card_id=eaten.id, targets=[victim.id])
    settle(s)
    assert gone(s, victim) and s.state.cards[eaten.id].zone == "p1:graveyard"
    assert not any(s.state.players["p1"].mana.values())  # ({B} + {3}{B}: all five spent)
    replay_matches(reloaded(s))


def test_annihilating_glare_sacrifices_a_creature_when_chosen(cards):
    s = build(cards, "Annihilating Glare")
    fodder = token_of(s, "p1", "Fodder", "Token Creature — Thrull", "1/1")
    victim = token_of(s, "p2", "Victim", "Token Creature — Bear", "2/2")
    glare = to_hand(s, "Annihilating Glare")
    mana(s, B=1, C=4)
    act(s, "p1", type="cast_spell", card_id=glare.id, targets=[victim.id])
    d = s.state.rules.decision
    assert [o.id for o in d.options] == ["either:0", "either:1"]
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["either:1"])
    settle(s)
    assert gone(s, fodder)
    assert gone(s, victim)
    replay_matches(s)


def test_demand_answers_sacrifices_an_artifact(cards):
    s = build(cards, "Demand Answers")
    relic = token_of(s, "p1", "Relic", "Token Artifact — Clue", "0/0")
    answers = to_hand(s, "Demand Answers")
    hand = len(s.state.zones["p1:hand"])
    mana(s, R=1, C=1)
    assert s.state.zones["p1:hand"] == [answers.id]  # (nothing to discard: the artifact is sacrificed, unasked)
    act(s, "p1", type="cast_spell", card_id=answers.id)
    settle(s)
    assert gone(s, relic)
    assert len(s.state.zones["p1:hand"]) == hand - 1 + 2
    replay_matches(reloaded(s))

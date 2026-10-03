"""Wave 6E: static and spell wordings from the catch-all gap family, researched against CR 2026-09-25.

* Ward written with other keywords on one line ("Vigilance, trample, ward {1}"): each keyword is its own ability (702.1),
  the ward piece triggers like a lone one (702.21a); "ward—Pay 3 life" stays manual.
* Anthems granting triggered keywords (613.1f): undying (702.93a), persist (702.79a), prowess (702.108a), exalted (702.83a,
  each instance separately, 702.83b): Mikaeus the Unhallowed, Sublime Archangel, Bria.
* A choice between additional costs (601.2b announced before targets, 601.2f in the total cost, 601.2h paid with the
  rest, 118.3): Demand Answers, Bitter Triumph, Eaten Alive, Annihilating Glare.
* "Regenerate each creature you control." (701.19a, the group read as it resolves, 608.2c): Golgari Charm, Wrap in Vigor.
* "You may exert this creature as it attacks. When you do, …" (701.43d: an optional cost to attack, 508.1g, linked to
  its reflexive trigger, 607.2h, 603.12; 701.43a: no untap next untap step): Hooded Brawler, Glorybringer, Tah-Crop Elite.
* Flavor words (207.2d) before a static ability or a trigger written with "!", "?" or "-" ("Devastating Charge — …",
  "Bring it Down! — Whenever …"): Bloodcrusher of Khorne, Inquisitor Greyfax, Ghost, Company Commander.
* "Creatures target player controls get +N/+N until end of turn." (608.2c, 611.2c): Arms of Hadar, How to Start a Riot,
  Neutralize the Guards. Irregular plurals in anthems ("Oxen you control"): Bruse Tarl.
* Triggered keywords read through their CR meaning: battle cry (702.91a), ingest (702.115a), poisonous N (702.70a),
  frenzy N (702.68a): Hero of Oxid Ridge, Mist Intruder.
* "Target creature becomes red [and gains haste] until end of turn." (layer 5, 613.1e; 105.3): the Wisps.
* Afterlife N (702.135a) and extort (702.101a) through their meaning: Orzhov Racketeers, Blind Obedience.
* "This land enters tapped unless a player has 13 or less life." / "… unless your opponents control eight or more lands."
  (614.1c, 614.12): Neglected Manor, Turbulent Moor.
* "Each creature [you control] assigns combat damage equal to its toughness rather than its power." (510.1a's amount):
  Doran, the Siege Tower, Belligerent Brontodon.
* Anthems over two groups ("Skeletons you control and other Zombies you control"): Death Baron, Caterwauling Boggart,
  Timber Protector.

Every scenario checks the replay; the longer ones also reload the game from its saved history.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.cards.importer import build_database
from app.config import Settings
from app.game.errors import ActionError
from app.rules import coverage, statics
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditionals import settle, through_combat, token_of, until
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
    card('Golgari Charm', set_code='tst', number='E14', mana_cost='{B}{G}', cmc=2.0, type_line='Instant', oracle_text='Choose one —\n• All creatures get -1/-1 until end of turn.\n• Destroy target enchantment.\n• Regenerate each creature you control.', colors=['B', 'G'], color_identity=['B', 'G'], keywords=['Regenerate']),  # noqa: E501
    card('Wrap in Vigor', set_code='tst', number='E15', mana_cost='{1}{G}', cmc=2.0, type_line='Instant', oracle_text='Regenerate each creature you control.', colors=['G'], color_identity=['G'], keywords=['Regenerate']),  # noqa: E501
    card('Hooded Brawler', set_code='tst', number='E16', mana_cost='{2}{G}', cmc=3.0, type_line='Creature — Snake Warrior', oracle_text="You may exert this creature as it attacks. When you do, it gets +2/+2 until end of turn. (An exerted creature won't untap during your next untap step.)", power='3', toughness='2', colors=['G'], color_identity=['G'], keywords=['Exert']),  # noqa: E501
    card('Glorybringer', set_code='tst', number='E17', mana_cost='{3}{R}{R}', cmc=5.0, type_line='Creature — Dragon', oracle_text="Flying, haste\nYou may exert this creature as it attacks. When you do, it deals 4 damage to target non-Dragon creature an opponent controls. (An exerted creature won't untap during your next untap step.)", power='4', toughness='4', colors=['R'], color_identity=['R'], keywords=['Flying', 'Haste', 'Exert']),  # noqa: E501
    card('Tah-Crop Elite', set_code='tst', number='E18', mana_cost='{3}{W}', cmc=4.0, type_line='Creature — Bird Warrior', oracle_text="Flying\nYou may exert this creature as it attacks. When you do, creatures you control get +1/+1 until end of turn. (An exerted creature won't untap during your next untap step.)", power='2', toughness='2', colors=['W'], color_identity=['W'], keywords=['Flying', 'Exert']),  # noqa: E501
    card("Oketra's Avenger", set_code='tst', number='E19', mana_cost='{1}{W}', cmc=2.0, type_line='Creature — Human Warrior', oracle_text="You may exert this creature as it attacks. When you do, prevent all combat damage that would be dealt to it this turn. (An exerted creature won't untap during your next untap step.)", power='3', toughness='1', colors=['W'], color_identity=['W'], keywords=['Exert']),  # noqa: E501
    card('Bloodcrusher of Khorne', set_code='tst', number='E20', mana_cost='{3}{R}', cmc=4.0, type_line='Creature — Demon Knight', oracle_text='Trample\nDevastating Charge — Other creatures you control have trample.', power='3', toughness='3', colors=['R'], color_identity=['R'], keywords=['Devastating Charge', 'Trample']),  # noqa: E501
    card('Inquisitor Greyfax', set_code='tst', number='E21', mana_cost='{1}{W}{U}{B}', cmc=4.0, type_line='Legendary Creature — Human Inquisitor', oracle_text='Vigilance\nUnquestionable Wisdom — Other creatures you control get +1/+0 and have vigilance.\nHunt for Heresy — {1}, {T}: Tap target creature an opponent controls. Investigate. (Create a Clue token. It\'s an artifact with "{2}, Sacrifice this token: Draw a card.")', power='3', toughness='3', colors=['B', 'U', 'W'], color_identity=['B', 'U', 'W'], keywords=['Investigate', 'Vigilance', 'Unquestionable Wisdom', 'Hunt for Heresy']),  # noqa: E501
    card('Ghost, Spectral Saboteur', set_code='tst', number='E22', mana_cost='{2}{U/B}', cmc=3.0, type_line='Legendary Creature — Human Rogue Villain', oracle_text="Flash\nIntangibility — Ghost can't be blocked.", power='2', toughness='2', colors=['B', 'U'], color_identity=['B', 'U'], keywords=['Intangibility', 'Flash']),  # noqa: E501
    card('Company Commander', set_code='tst', number='E23', mana_cost='{2}{W}{B}', cmc=4.0, type_line='Creature — Human Soldier', oracle_text='Command Section — When this creature enters, create a number of 1/1 white Soldier creature tokens equal to the number of opponents you have.\nBring it Down! — Whenever this creature attacks, creatures you control gain deathtouch until end of turn.', power='2', toughness='4', colors=['B', 'W'], color_identity=['B', 'W'], keywords=['Command Section', 'Bring it Down!']),  # noqa: E501
    card('Bruse Tarl, Roving Rancher', set_code='tst', number='E24', mana_cost='{2}{R}{W}', cmc=4.0, type_line='Legendary Creature — Human Warrior', oracle_text="Oxen you control have double strike.\nWhenever Bruse Tarl enters or attacks, exile the top card of your library. If it's a land card, create a 2/2 white Ox creature token. Otherwise, you may cast it until the end of your next turn.", power='4', toughness='3', colors=['R', 'W'], color_identity=['R', 'W'], keywords=[]),  # noqa: E501
    card('Arms of Hadar', set_code='tst', number='E25', mana_cost='{3}{B}', cmc=4.0, type_line='Sorcery', oracle_text='Creatures target player controls get -2/-2 until end of turn.', colors=['B'], color_identity=['B'], keywords=[]),  # noqa: E501
    card('How to Start a Riot', set_code='tst', number='E26', mana_cost='{2}{R}', cmc=3.0, type_line='Instant — Lesson', oracle_text="Target creature gains menace until end of turn. (It can't be blocked except by two or more creatures.)\nCreatures target player controls get +2/+0 until end of turn.", colors=['R'], color_identity=['R'], keywords=[]),  # noqa: E501
    card('Neutralize the Guards', set_code='tst', number='E27', mana_cost='{2}{B}', cmc=3.0, type_line='Instant', oracle_text='Creatures target opponent controls get -1/-1 until end of turn. Surveil 2. (Look at the top two cards of your library, then put any number of them into your graveyard and the rest on top of your library in any order.)', colors=['B'], color_identity=['B'], keywords=['Surveil']),  # noqa: E501
    card('Hero of Oxid Ridge', set_code='tst', number='E28', mana_cost='{2}{R}{R}', cmc=4.0, type_line='Creature — Human Knight', oracle_text="Haste\nBattle cry (Whenever this creature attacks, each other attacking creature gets +1/+0 until end of turn.)\nWhenever this creature attacks, creatures with power 1 or less can't block this turn.", power='4', toughness='2', colors=['R'], color_identity=['R'], keywords=['Battle Cry', 'Haste']),  # noqa: E501
    card('Mist Intruder', set_code='tst', number='E29', mana_cost='{1}{U}', cmc=2.0, type_line='Creature — Eldrazi Drone', oracle_text='Devoid (This card has no color.)\nFlying\nIngest (Whenever this creature deals combat damage to a player, that player exiles the top card of their library.)', power='1', toughness='2', colors=[], color_identity=['U'], keywords=['Flying', 'Devoid', 'Ingest']),  # noqa: E501
    card('Crimson Wisps', set_code='tst', number='E30', mana_cost='{R}', cmc=1.0, type_line='Instant', oracle_text='Target creature becomes red and gains haste until end of turn. (It can attack and {T} this turn.)\nDraw a card.', colors=['R'], color_identity=['R'], keywords=[]),  # noqa: E501
    card('Aphotic Wisps', set_code='tst', number='E31', mana_cost='{B}', cmc=1.0, type_line='Instant', oracle_text="Target creature becomes black and gains fear until end of turn. (It can't be blocked except by artifact creatures and/or black creatures.)\nDraw a card.", colors=['B'], color_identity=['B'], keywords=[]),  # noqa: E501
    card('Cerulean Wisps', set_code='tst', number='E32', mana_cost='{U}', cmc=1.0, type_line='Instant', oracle_text='Target creature becomes blue until end of turn. Untap that creature.\nDraw a card.', colors=['U'], color_identity=['U'], keywords=[]),  # noqa: E501
    card('Neglected Manor', set_code='tst', number='E33', mana_cost='', cmc=0.0, type_line='Land', oracle_text='This land enters tapped unless a player has 13 or less life.\n{T}: Add {W} or {B}.', colors=[], color_identity=['B', 'W'], keywords=[]),  # noqa: E501
    card('Turbulent Moor', set_code='tst', number='E34', mana_cost='', cmc=0.0, type_line='Land — Plains Swamp', oracle_text='({T}: Add {W} or {B}.)\nThis land enters tapped unless your opponents control eight or more lands.', colors=[], color_identity=['B', 'W'], keywords=[]),  # noqa: E501
    card('Orzhov Racketeers', set_code='tst', number='E35', mana_cost='{4}{B}', cmc=5.0, type_line='Creature — Human Rogue', oracle_text='Whenever this creature deals combat damage to a player, that player discards a card.\nAfterlife 2 (When this creature dies, create two 1/1 white and black Spirit creature tokens with flying.)', power='3', toughness='2', colors=['B'], color_identity=['B'], keywords=['Afterlife']),  # noqa: E501
    card('Doran, the Siege Tower', set_code='tst', number='E36', mana_cost='{W}{B}{G}', cmc=3.0, type_line='Legendary Creature — Treefolk Shaman', oracle_text='Each creature assigns combat damage equal to its toughness rather than its power.', power='0', toughness='5', colors=['B', 'G', 'W'], color_identity=['B', 'G', 'W'], keywords=[]),  # noqa: E501
    card('Belligerent Brontodon', set_code='tst', number='E37', mana_cost='{5}{G}{W}', cmc=7.0, type_line='Creature — Dinosaur', oracle_text='Each creature you control assigns combat damage equal to its toughness rather than its power.', power='4', toughness='6', colors=['G', 'W'], color_identity=['G', 'W'], keywords=[]),  # noqa: E501
    card('Blind Obedience', set_code='tst', number='E38', mana_cost='{1}{W}', cmc=2.0, type_line='Enchantment', oracle_text='Extort (Whenever you cast a spell, you may pay {W/B}. If you do, each opponent loses 1 life and you gain that much life.)\nArtifacts and creatures your opponents control enter tapped.', colors=['W'], color_identity=['W'], keywords=['Extort']),  # noqa: E501
]
FULL = ["Eshki Dragonclaw", "Mikaeus, the Unhallowed", "Death Baron", "Sublime Archangel", "Bria, Riptide Rogue",
        "Caterwauling Boggart", "Timber Protector", "Demand Answers", "Bitter Triumph", "Eaten Alive",
        "Annihilating Glare", "Golgari Charm", "Wrap in Vigor", "Hooded Brawler", "Glorybringer", "Tah-Crop Elite",
        "Bloodcrusher of Khorne", "Inquisitor Greyfax", "Ghost, Spectral Saboteur", "Company Commander",
        "Bruse Tarl, Roving Rancher", "Arms of Hadar", "How to Start a Riot", "Neutralize the Guards",
        "Hero of Oxid Ridge", "Mist Intruder", "Crimson Wisps", "Aphotic Wisps", "Cerulean Wisps", "Neglected Manor",
        "Turbulent Moor", "Orzhov Racketeers", "Doran, the Siege Tower", "Belligerent Brontodon",
        "Blind Obedience"]
STILL_MANUAL = {
    "Sedgemoor Witch": "Ward",  # (ward—Pay 3 life: a cost the ward trigger doesn't read)
    "Silvergill Adept": "reveal a Merfolk card",
    "Oketra's Avenger": "prevent all combat damage",  # (a prevention shield from a trigger: not read)  # (revealing a card as a cost: not paid by the engine)
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
    with pytest.raises(ActionError):  # ({B} plus {3}{B}: two black mana aren't enough)
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


# -- a regeneration shield for each creature of a group (701.19a) ------------------------------------------------
def test_golgari_charm_regenerates_each_creature_you_control(cards):
    s = build(cards, "Golgari Charm", "Murder")
    mine = token_of(s, "p1", "Mine", "Token Creature — Bear", "2/2")
    theirs = token_of(s, "p2", "Theirs", "Token Creature — Bear", "2/2")
    charm = to_hand(s, "Golgari Charm")
    mana(s, B=1, G=1)
    act(s, "p1", type="cast_spell", card_id=charm.id, modes=[2])
    settle(s)
    murder = to_hand(s, "Murder")
    mana(s, B=3)
    act(s, "p1", type="cast_spell", card_id=murder.id, targets=[mine.id])
    settle(s)
    assert s.state.cards[mine.id].zone == "p1:battlefield" and s.state.cards[mine.id].tapped  # regenerated
    act(s, "p1", type="move", card_ids=[murder.id], to={"zone": "hand"})
    mana(s, B=3)
    act(s, "p1", type="cast_spell", card_id=murder.id, targets=[theirs.id])
    settle(s)
    assert gone(s, theirs)  # (only creatures you control)
    replay_matches(reloaded(s))


# -- exert as it attacks (701.43d, 508.1g) -------------------------------------------------------------------------
BRAWLER = ("You may exert this creature as it attacks. When you do, it gets +2/+2 until end of turn. (An exerted creature "
           "won't untap during your next untap step.)")


def attack_with(s, *creatures):
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_attackers")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": c.id, "target": "p2"} for c in creatures])


def test_exerted_brawler_gets_the_bonus_and_stays_tapped(cards):
    s = build(cards)
    brawler = token_of(s, "p1", "Brawler", "Token Creature — Snake Warrior", "3/2", "Haste\n" + BRAWLER)
    attack_with(s, brawler)
    d = s.state.rules.decision
    assert d is not None and d.kind == "choose_cards" and [o.id for o in d.options] == [brawler.id]
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[brawler.id])
    settle(s)
    assert pt(s, brawler) == (5, 4)
    s = reloaded(s)
    replay_matches(s)
    until(s, lambda s: s.state.turn.number == 3 and s.state.turn.phase == "main1")
    assert s.state.cards[brawler.id].tapped  # 701.43a: it didn't untap during the next untap step
    replay_matches(s)


def test_brawler_not_exerted_gets_nothing_and_untaps(cards):
    s = build(cards)
    brawler = token_of(s, "p1", "Brawler", "Token Creature — Snake Warrior", "3/2", "Haste\n" + BRAWLER)
    attack_with(s, brawler)
    act(s, "p1", type="choose", decision_id=s.state.rules.decision.id, option_ids=[])
    settle(s)
    assert pt(s, brawler) == (3, 2)
    until(s, lambda s: s.state.turn.number == 3 and s.state.turn.phase == "main1")
    assert not s.state.cards[brawler.id].tapped
    replay_matches(s)


def test_glorybringer_exerted_deals_damage_to_a_non_dragon(cards):
    s = build(cards, "Glorybringer")
    glory = put(s, "Glorybringer")
    victim = token_of(s, "p2", "Victim", "Token Creature — Bear", "3/3")
    token_of(s, "p2", "Their Dragon", "Token Creature — Dragon", "3/3")
    attack_with(s, glory)
    act(s, "p1", type="choose", decision_id=s.state.rules.decision.id, option_ids=[glory.id])
    d = s.state.rules.decision
    if d is not None and d.kind != "declare_blockers":  # (the target: the Dragon isn't offered)
        assert [o.id for o in d.options] == [victim.id]
        act(s, "p1", type="choose", decision_id=d.id, option_ids=[victim.id])
    through_combat(s)
    assert gone(s, victim)
    replay_matches(reloaded(s))


def test_tah_crop_elite_pumps_the_team_when_exerted(cards):
    s = build(cards, "Tah-Crop Elite")
    elite = token_of(s, "p1", "Elite", "Token Creature — Bird Warrior", "2/2",
                     "Flying\nHaste\nYou may exert this creature as it attacks. When you do, creatures you control get "
                     "+1/+1 until end of turn.")
    other = token_of(s, "p1", "Other", "Token Creature — Bear", "2/2")
    attack_with(s, elite)
    act(s, "p1", type="choose", decision_id=s.state.rules.decision.id, option_ids=[elite.id])
    settle(s)
    assert pt(s, elite) == (3, 3) and pt(s, other) == (3, 3)
    replay_matches(s)


# -- flavor words (207.2d) --------------------------------------------------------------------------------------------
def test_flavor_words_are_read_past():
    from app.rules import oracle

    assert oracle.word_prefix("Devastating Charge — Other creatures you control have trample.") is not None
    assert oracle.word_prefix("Visit — Draw a card.") is None  # (an Attraction's visit ability: a rule, 702.159)
    assert oracle.word_prefix("Max speed — This creature has flying.") is None  # (702.178)
    assert oracle.word_prefix("Companion — Each creature card in your starting deck is a Cat.") is None


def test_bloodcrusher_gives_other_creatures_trample(cards):
    s = build(cards, "Bloodcrusher of Khorne")
    put(s, "Bloodcrusher of Khorne")
    bear = token_of(s, "p1", "Bear", "Token Creature — Bear", "2/2")
    theirs = token_of(s, "p2", "Theirs", "Token Creature — Bear", "2/2")
    assert "trample" in chars(s, bear).keywords and "trample" not in chars(s, theirs).keywords
    replay_matches(s)


def test_company_commander_bring_it_down_on_attack(cards):
    s = build(cards, "Company Commander")
    cmd = token_of(s, "p1", "Commander", "Token Creature — Human Soldier", "3/3",
                   "Haste\nBring it Down! — Whenever this creature attacks, creatures you control gain deathtouch until end "
                   "of turn.")
    bear = token_of(s, "p1", "Bear", "Token Creature — Bear", "2/2")
    attack_with(s, cmd)
    settle(s)
    assert "deathtouch" in chars(s, cmd).keywords and "deathtouch" in chars(s, bear).keywords
    replay_matches(reloaded(s))


def test_bruse_tarl_oxen_have_double_strike(cards):
    s = build(cards, "Bruse Tarl, Roving Rancher")
    put(s, "Bruse Tarl, Roving Rancher")
    ox = token_of(s, "p1", "Ox", "Token Creature — Ox", "2/2")
    assert "double strike" in chars(s, ox).keywords
    replay_matches(s)


# -- the creatures a target player controls (608.2c, 611.2c) ---------------------------------------------------------
def test_arms_of_hadar_shrinks_the_target_players_creatures(cards):
    s = build(cards, "Arms of Hadar")
    small = token_of(s, "p2", "Small", "Token Creature — Bear", "2/2")
    big = token_of(s, "p2", "Big", "Token Creature — Bear", "4/4")
    mine = token_of(s, "p1", "Mine", "Token Creature — Bear", "2/2")
    arms = to_hand(s, "Arms of Hadar")
    mana(s, B=1, C=3)
    act(s, "p1", type="cast_spell", card_id=arms.id, targets=["p2"])
    settle(s)
    assert gone(s, small) and pt(s, big) == (2, 2) and pt(s, mine) == (2, 2)
    late = token_of(s, "p2", "Late", "Token Creature — Bear", "2/2")
    assert pt(s, late) == (2, 2)  # (611.2c: the creatures it affected were locked in as it resolved)
    replay_matches(reloaded(s))


def test_how_to_start_a_riot_menace_on_one_target_and_pump_on_the_players(cards):
    s = build(cards, "How to Start a Riot")
    mine = token_of(s, "p1", "Mine", "Token Creature — Bear", "2/2")
    theirs = token_of(s, "p2", "Theirs", "Token Creature — Bear", "2/2")
    riot = to_hand(s, "How to Start a Riot")
    mana(s, R=1, C=2)
    act(s, "p1", type="cast_spell", card_id=riot.id, targets=[theirs.id, "p1"], target_counts=[1, 1])
    settle(s)
    assert "menace" in chars(s, theirs).keywords and pt(s, theirs) == (2, 2)
    assert pt(s, mine) == (4, 2) and "menace" not in chars(s, mine).keywords
    replay_matches(reloaded(s))


# -- triggered keywords through their meaning (702.91a, 702.115a, 702.70a, 702.68a) --------------------------------
def test_keyword_meanings_read():
    from app.rules import keyword_triggers

    assert keyword_triggers.supported("battle cry", "Haste, battle cry")
    assert keyword_triggers.supported("poisonous", "Poisonous 2")
    assert not keyword_triggers.supported("poisonous", "Poisonous")  # (no number)
    (d,) = keyword_triggers.definitions("frenzy", "Frenzy 1")
    assert d["effects"] == [{"do": "pump", "who": "self", "p": 1, "t": 0}]


def test_battle_cry_pumps_each_other_attacker(cards):
    s = build(cards)
    hero = token_of(s, "p1", "Hero", "Token Creature — Human Warrior", "4/2", "Haste\nBattle cry")
    pal = token_of(s, "p1", "Pal", "Token Creature — Bear", "2/2", "Haste")
    home = token_of(s, "p1", "Home", "Token Creature — Bear", "2/2", "Haste")
    attack_with(s, hero, pal)
    settle(s)
    assert pt(s, pal) == (3, 2) and pt(s, hero) == (4, 2) and pt(s, home) == (2, 2)
    replay_matches(reloaded(s))


def test_ingest_exiles_the_top_card_of_the_damaged_players_library(cards):
    s = build(cards)
    mist = token_of(s, "p1", "Mist", "Token Creature — Eldrazi Drone", "2/2", "Haste\nIngest")
    top = s.state.zones["p2:library"][0]
    attack_with(s, mist)
    through_combat(s)
    assert s.state.cards[top].zone == "p2:exile" and s.state.players["p2"].life == 38
    replay_matches(reloaded(s))


# -- a color for a turn (613.1e, 105.3) -------------------------------------------------------------------------------
def test_crimson_wisps_makes_it_red_with_haste_until_end_of_turn(cards):
    s = build(cards, "Crimson Wisps")
    bear = token_of(s, "p1", "Bear", "Token Creature — Bear", "2/2", colors=("G",))
    wisps = to_hand(s, "Crimson Wisps")
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=wisps.id, targets=[bear.id])
    settle(s)
    c = chars(s, bear)
    assert set(c.colors) == {"R"} and "haste" in c.keywords
    s = reloaded(s)
    replay_matches(s)
    assert {e.duration for e in s.state.rules.effects} == {"end_of_turn"}  # (gone at cleanup, 514.2)


def test_aphotic_wisps_black_with_fear_and_a_card(cards):
    s = build(cards, "Aphotic Wisps")
    bear = token_of(s, "p1", "Bear", "Token Creature — Bear", "2/2", colors=("W",))
    wisps = to_hand(s, "Aphotic Wisps")
    hand = len(s.state.zones["p1:hand"])
    mana(s, B=1)
    act(s, "p1", type="cast_spell", card_id=wisps.id, targets=[bear.id])
    settle(s)
    c = chars(s, bear)
    assert set(c.colors) == {"B"} and "fear" in c.keywords and len(s.state.zones["p1:hand"]) == hand  # (-1 cast, +1 drawn)
    replay_matches(s)


# -- afterlife (702.135a) ---------------------------------------------------------------------------------------------
def test_orzhov_racketeers_afterlife_makes_two_spirits(cards):
    s = build(cards, "Orzhov Racketeers", "Murder")
    rack = put(s, "Orzhov Racketeers")
    murder = to_hand(s, "Murder")
    mana(s, B=3)
    act(s, "p1", type="cast_spell", card_id=murder.id, targets=[rack.id])
    settle(s)
    spirits = [c for c in s.state.cards.values() if c.name == "Spirit" and c.zone == "p1:battlefield"]
    assert len(spirits) == 2 and all("flying" in chars(s, c).keywords and chars(s, c).pt == (1, 1) for c in spirits)
    assert set(chars(s, spirits[0]).colors) == {"W", "B"}
    replay_matches(reloaded(s))


# -- lands entering tapped unless … (614.1c) --------------------------------------------------------------------------
def test_neglected_manor_enters_tapped_while_every_player_is_above_13_life(cards):
    s = build(cards, "Neglected Manor")
    manor = to_hand(s, "Neglected Manor")
    act(s, "p1", type="play_land", card_id=manor.id)
    settle(s)
    assert s.state.cards[manor.id].tapped
    replay_matches(s)


def test_neglected_manor_enters_untapped_when_a_player_has_13_life(cards):
    s = build(cards, "Neglected Manor")
    act(s, "p1", type="set_life", player="p2", value=13)
    manor = to_hand(s, "Neglected Manor")
    act(s, "p1", type="play_land", card_id=manor.id)
    settle(s)
    assert not s.state.cards[manor.id].tapped
    replay_matches(reloaded(s))


def test_turbulent_moor_counts_the_opponents_lands(cards):
    s = build(cards, "Turbulent Moor")
    islands = [c for c in s.state.cards.values() if c.name == "Island" and c.owner == "p2"][:8]
    for c in islands[:7]:
        act(s, "p2", type="move", card_ids=[c.id], to={"player": "p2", "zone": "battlefield"})
    moor = to_hand(s, "Turbulent Moor")
    act(s, "p1", type="play_land", card_id=moor.id)
    settle(s)
    assert s.state.cards[moor.id].tapped  # (seven lands: not enough)
    act(s, "p1", type="move", card_ids=[moor.id], to={"zone": "hand"})
    act(s, "p2", type="move", card_ids=[islands[7].id], to={"player": "p2", "zone": "battlefield"})
    act(s, "p1", type="move", card_ids=[moor.id], to={"player": "p1", "zone": "battlefield"})
    settle(s)
    assert not s.state.cards[moor.id].tapped  # (614.1c: also when put onto the battlefield)
    replay_matches(s)


# -- combat damage from toughness (510.1a) ----------------------------------------------------------------------------
def test_brontodon_creatures_deal_damage_equal_to_toughness(cards):
    s = build(cards, "Belligerent Brontodon")
    put(s, "Belligerent Brontodon")
    wall = token_of(s, "p1", "Wall", "Token Creature — Wall", "1/4", "Haste")
    blocker = token_of(s, "p2", "Blocker", "Token Creature — Bear", "0/3")
    attacker = token_of(s, "p1", "Pup", "Token Creature — Wolf", "3/1", "Haste")
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_attackers")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": wall.id, "target": "p2"},
                                                      {"card_id": attacker.id, "target": "p2"}])
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_blockers")
    act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": blocker.id, "attacker_id": attacker.id}])
    through_combat(s)
    assert s.state.players["p2"].life == 36  # (the 1/4 Wall: 4)
    assert gone(s, blocker) is False and s.state.cards[blocker.id].damage == 1  # (the 3/1: its toughness, 1)
    assert gone(s, attacker) is False  # (the blocker isn't Alice's: it deals its power, 0)
    replay_matches(reloaded(s))


def test_doran_applies_to_every_creature(cards):
    s = build(cards, "Doran, the Siege Tower")
    put(s, "Doran, the Siege Tower")
    blocker = token_of(s, "p2", "Blocker", "Token Creature — Bear", "0/3")
    attacker = token_of(s, "p1", "Pup", "Token Creature — Wolf", "3/3", "Haste")
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_attackers")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": attacker.id, "target": "p2"}])
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_blockers")
    act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": blocker.id, "attacker_id": attacker.id}])
    through_combat(s)
    assert gone(s, blocker) and gone(s, attacker)  # (each deals 3: its toughness)
    replay_matches(s)


# -- extort (702.101a) ------------------------------------------------------------------------------------------------
def test_blind_obedience_extorts_when_paid(cards):
    s = build(cards, "Blind Obedience", "Opt")
    put(s, "Blind Obedience")
    opt = to_hand(s, "Opt")
    mana(s, U=1, W=1)
    act(s, "p1", type="cast_spell", card_id=opt.id)
    until(s, lambda s: s.state.rules.decision is not None and any(o.id == "pay" for o in s.state.rules.decision.options))
    d = s.state.rules.decision
    assert d.player == "p1"
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["pay"])
    settle(s)
    assert s.state.players["p2"].life == 39 and s.state.players["p1"].life == 41
    replay_matches(reloaded(s))


def test_extort_declined_does_nothing(cards):
    s = build(cards, "Blind Obedience", "Opt")
    put(s, "Blind Obedience")
    opt = to_hand(s, "Opt")
    mana(s, U=1, W=1)
    act(s, "p1", type="cast_spell", card_id=opt.id)
    until(s, lambda s: s.state.rules.decision is not None and any(o.id == "decline" for o in s.state.rules.decision.options))
    act(s, "p1", type="choose", decision_id=s.state.rules.decision.id, option_ids=["decline"])
    settle(s)
    assert s.state.players["p2"].life == 40 and s.state.players["p1"].life == 40
    replay_matches(s)

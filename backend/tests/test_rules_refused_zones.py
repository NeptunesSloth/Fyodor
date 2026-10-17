"""Forms the reanimation / tutor / sized-amount waves left manual (wave 3R4), read against CR
2026-09-25: 207.2c/207.2d (ability and flavor words have no rules meaning), 113.6m (an ability that
moves its own card out of the graveyard functions only there), 603.3a/603.10 (graveyard triggers;
objects that exist right after an event are checked), 122.1h (finality counters), 119.3 and 608.2c
("the life lost this way"). The cards are real Commander cards, their Oracle text transcribed from
the card database. Every scenario also checks that replaying the recorded history reproduces the
table exactly."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from app.rules import coverage
from app.rules.characteristics import printed_from_data
from app.rules.oracle import parse_abilities
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, deck, enable
from tests.test_rules_effects import pass_until_stack_empty, replay_matches, run_until

REAL = [
    card('Bloodsoaked Champion', set_code="tst", number="Z1", mana_cost='{B}', cmc=1.0, type_line='Creature — Human Warrior',
         oracle_text="This creature can't block.\nRaid — {1}{B}: Return this card from your graveyard to the battlefield. "
                     "Activate only if you attacked this turn.", power='2', toughness='1', colors=['B'], color_identity=['B']),
    card('Infected Vermin', set_code="tst", number="Z2", mana_cost='{2}{B}', cmc=3.0, type_line='Creature — Rat',
         oracle_text='{2}{B}: This creature deals 1 damage to each creature and each player.\nThreshold — {3}{B}: This creature '
                     'deals 3 damage to each creature and each player. Activate only if there are seven or more cards in your '
                     'graveyard.', power='1', toughness='1', colors=['B'], color_identity=['B']),
    card('Amarant Coral', set_code="tst", number="Z3", mana_cost='{2}{R}{G}', cmc=4.0, type_line='Legendary Creature — Human Monk',
         oracle_text='Trample\nAmarant Coral attacks each combat if able.\nNo Mercy — Whenever Amarant Coral deals combat damage '
                     'to an opponent, it deals that much damage to each other opponent.', power='5', toughness='4',
         colors=['G', 'R'], color_identity=['G', 'R']),
    card('Gray Merchant of Asphodel', set_code="tst", number="Z4", mana_cost='{3}{B}{B}', cmc=5.0, type_line='Creature — Zombie',
         oracle_text='When this creature enters, each opponent loses X life, where X is your devotion to black. You gain life '
                     'equal to the life lost this way. (Each {B} in the mana costs of permanents you control counts toward your '
                     'devotion to black.)', power='2', toughness='4', colors=['B'], color_identity=['B']),
    card('Kokusho, the Evening Star', set_code="tst", number="Z5", mana_cost='{4}{B}{B}', cmc=6.0,
         type_line='Legendary Creature — Dragon Spirit',
         oracle_text='Flying\nWhen Kokusho dies, each opponent loses 5 life. You gain life equal to the life lost this way.',
         power='5', toughness='5', colors=['B'], color_identity=['B']),
    card('Exsanguinate', set_code="tst", number="Z6", mana_cost='{X}{B}{B}', cmc=2.0, type_line='Sorcery',
         oracle_text='Each opponent loses X life. You gain life equal to the life lost this way.', colors=['B'], color_identity=['B']),
    card('Rite of the Moth', set_code="tst", number="Z7", mana_cost='{1}{W}{B}{B}', cmc=4.0, type_line='Sorcery',
         oracle_text='Return target creature card from your graveyard to the battlefield with a finality counter on it. (If a '
                     'creature with a finality counter on it would die, exile it instead.)\nFlashback {3}{W}{W}{B} (You may cast '
                     'this card from your graveyard for its flashback cost. Then exile it.)', colors=['B', 'W'],
         color_identity=['B', 'W']),
    card('Squee, Goblin Nabob', set_code="tst", number="Z8", mana_cost='{2}{R}', cmc=3.0, type_line='Legendary Creature — Goblin',
         oracle_text='At the beginning of your upkeep, you may return this card from your graveyard to your hand.', power='1',
         toughness='1', colors=['R'], color_identity=['R']),
    card('Bloodghast', set_code="tst", number="Z9", mana_cost='{B}{B}', cmc=2.0, type_line='Creature — Vampire Spirit',
         oracle_text="This creature can't block.\nThis creature has haste as long as an opponent has 10 or less life.\nLandfall — "
                     "Whenever a land you control enters, you may return this card from your graveyard to the battlefield.",
         power='2', toughness='1', colors=['B'], color_identity=['B']),
    card('Verdant Eidolon', set_code="tst", number="Z10", mana_cost='{3}{G}', cmc=4.0, type_line='Creature — Spirit',
         oracle_text='{G}, Sacrifice this creature: Add three mana of any one color.\nWhenever you cast a multicolored spell, you '
                     'may return this card from your graveyard to your hand.', power='2', toughness='2', colors=['G'],
         color_identity=['G']),
    card('Darklight Phoenix', set_code="tst", number="Z11", mana_cost='{3}{B}', cmc=4.0, type_line='Creature — Phoenix',
         oracle_text='Flying, haste\nAt the beginning of combat on your turn, if two or more creatures died this turn, return '
                     'this card from your graveyard to the battlefield.', power='3', toughness='2', colors=['B'],
         color_identity=['B']),
    card("Bladewing's Thrall", set_code="tst", number="Z12", mana_cost='{2}{B}{B}', cmc=4.0, type_line='Creature — Zombie',
         oracle_text='This creature has flying as long as you control a Dragon.\nWhen a Dragon enters, you may return this card '
                     'from your graveyard to the battlefield.', power='3', toughness='3', colors=['B'], color_identity=['B']),
    card('Boros Charm', set_code="tst", number="Z15", mana_cost='{R}{W}', cmc=2.0, type_line='Instant',
         oracle_text='Choose one —\n• Boros Charm deals 4 damage to target player or planeswalker.\n• Permanents you control gain '
                     'indestructible until end of turn.\n• Target creature gains double strike until end of turn.',
         colors=['R', 'W'], color_identity=['R', 'W']),
    card('Screams from Within', set_code="tst", number="Z16", mana_cost='{1}{B}{B}', cmc=3.0, type_line='Enchantment — Aura',
         oracle_text='Enchant creature\nEnchanted creature gets -1/-1.\nWhen enchanted creature dies, return this card from your '
                     'graveyard to the battlefield.', colors=['B'], color_identity=['B']),
    card('Tower Winder', set_code="tst", number="Z17", mana_cost='{1}{G}', cmc=2.0, type_line='Creature — Snake',
         oracle_text='Reach, deathtouch\nWhen this creature enters, search your library and/or graveyard for a card named Command '
                     'Tower, reveal it, and put it into your hand. If you search your library this way, shuffle.', power='1',
         toughness='1', colors=['G'], color_identity=['G']),
    card('Finale of Devastation', set_code="tst", number="Z18", mana_cost='{X}{G}{G}', cmc=2.0, type_line='Sorcery',
         oracle_text='Search your library and/or graveyard for a creature card with mana value X or less and put it onto the '
                     'battlefield. If you search your library this way, shuffle. If X is 10 or more, creatures you control get '
                     '+X/+X and gain haste until end of turn.', colors=['G'], color_identity=['G']),
    card("Gideon's Resolve", set_code="tst", number="Z19", mana_cost='{4}{W}', cmc=5.0, type_line='Enchantment',
         oracle_text='When this enchantment enters, you may search your library and/or graveyard for a card named Gideon, Martial '
                     'Paragon, reveal it, and put it into your hand. If you search your library this way, shuffle.\nCreatures '
                     'you control get +1/+1.', colors=['W'], color_identity=['W']),
    card('Yore-Tiller Nephilim', set_code="tst", number="Z20", mana_cost='{W}{U}{B}{R}', cmc=4.0, type_line='Creature — Nephilim',
         oracle_text='Whenever this creature attacks, return target creature card from your graveyard to the battlefield tapped '
                     'and attacking.', power='2', toughness='2', colors=['B', 'R', 'U', 'W'], color_identity=['B', 'R', 'U', 'W']),
    card('Dragon Breath', set_code="tst", number="Z21", mana_cost='{1}{R}', cmc=2.0, type_line='Enchantment — Aura',
         oracle_text='Enchant creature\nEnchanted creature has haste.\n{R}: Enchanted creature gets +1/+0 until end of turn.\nWhen '
                     'a creature with mana value 6 or greater enters, you may return this card from your graveyard to the '
                     'battlefield attached to that creature.', colors=['R'], color_identity=['R']),
    card('Iridescent Drake', set_code="tst", number="Z22", mana_cost='{3}{U}', cmc=4.0, type_line='Creature — Drake',
         oracle_text='Flying\nWhen this creature enters, put target Aura card from a graveyard onto the battlefield under your '
                     'control attached to this creature.', power='2', toughness='2', colors=['U'], color_identity=['U']),
    card('Magnetic Snuffler', set_code="tst", number="Z23", mana_cost='{5}', cmc=5.0, type_line='Artifact Creature — Construct',
         oracle_text='When this creature enters, return target Equipment card from your graveyard to the battlefield attached to '
                     'this creature.\nWhenever you sacrifice an artifact, put a +1/+1 counter on this creature.', power='4',
         toughness='4'),
    card('Bonesplitter', set_code="tst", number="Z24", mana_cost='{1}', cmc=1.0, type_line='Artifact — Equipment',
         oracle_text='Equipped creature gets +2/+0.\nEquip {1}'),
    card('Wild Growth', set_code="tst", number="Z25", mana_cost='{G}', cmc=1.0, type_line='Enchantment — Aura',
         oracle_text='Enchant land\nWhenever enchanted land is tapped for mana, its controller adds an additional {G}.',
         colors=['G'], color_identity=['G']),
    card('Gifts Ungiven', set_code="tst", number="Z26", mana_cost='{3}{U}', cmc=4.0, type_line='Instant',
         oracle_text='Search your library for up to four cards with different names and reveal them. Target opponent chooses two '
                     'of those cards. Put the chosen cards into your graveyard and the rest into your hand. Then shuffle.',
         colors=['U'], color_identity=['U']),
    card('Shared Summons', set_code="tst", number="Z27", mana_cost='{3}{G}{G}', cmc=5.0, type_line='Instant',
         oracle_text='Search your library for up to two creature cards with different names, reveal them, put them into your '
                     'hand, then shuffle.', colors=['G'], color_identity=['G']),
    card('Realms Uncharted', set_code="tst", number="Z28", mana_cost='{2}{G}', cmc=3.0, type_line='Instant',
         oracle_text='Search your library for up to four land cards with different names and reveal them. An opponent chooses two '
                     'of those cards. Put the chosen cards into your graveyard and the rest into your hand. Then shuffle.',
         colors=['G'], color_identity=['G']),
    card('Sudden Impact', set_code="tst", number="Z29", mana_cost='{3}{R}', cmc=4.0, type_line='Instant',
         oracle_text="Sudden Impact deals damage to target player equal to the number of cards in that player's hand.",
         colors=['R'], color_identity=['R']),
    card('Iron Maiden', set_code="tst", number="Z30", mana_cost='{3}', cmc=3.0, type_line='Artifact',
         oracle_text="At the beginning of each opponent's upkeep, this artifact deals X damage to that player, where X is the "
                     "number of cards in their hand minus 4."),
    card('Dark Suspicions', set_code="tst", number="Z31", mana_cost='{2}{B}{B}', cmc=4.0, type_line='Enchantment',
         oracle_text="At the beginning of each opponent's upkeep, that player loses X life, where X is the number of cards in "
                     "that player's hand minus the number of cards in your hand.", colors=['B'], color_identity=['B']),
    card('Ram Through', set_code="tst", number="Z32", mana_cost='{1}{G}', cmc=2.0, type_line='Instant',
         oracle_text="Target creature you control deals damage equal to its power to target creature you don't control. If the "
                     "creature you control has trample, excess damage is dealt to that creature's controller instead.",
         colors=['G'], color_identity=['G']),
    card('Flame Spill', set_code="tst", number="Z33", mana_cost='{2}{R}', cmc=3.0, type_line='Instant',
         oracle_text="Flame Spill deals 4 damage to target creature. Excess damage is dealt to that creature's controller instead.",
         colors=['R'], color_identity=['R']),
    card('Dimir House Guard', set_code="tst", number="Z34", mana_cost='{3}{B}', cmc=4.0, type_line='Creature — Skeleton',
         oracle_text="Fear (This creature can't be blocked except by artifact creatures and/or black creatures.)\nSacrifice a "
                     "creature: Regenerate this creature.\nTransmute {1}{B}{B} ({1}{B}{B}, Discard this card: Search your "
                     "library for a card with the same mana value as this card, reveal it, put it into your hand, then shuffle. "
                     "Transmute only as a sorcery.)", power='2', toughness='3', colors=['B'], color_identity=['B']),
    card('Hymn to Tourach', set_code="tst", number="Z35", mana_cost='{B}{B}', cmc=2.0, type_line='Sorcery',
         oracle_text='Target player discards two cards at random.', colors=['B'], color_identity=['B']),
    card('Gamble', set_code="tst", number="Z36", mana_cost='{R}', cmc=1.0, type_line='Sorcery',
         oracle_text='Search your library for a card, put that card into your hand, discard a card at random, then shuffle.',
         colors=['R'], color_identity=['R']),
    card('Congregation at Dawn', set_code="tst", number="Z37", mana_cost='{G}{G}{W}', cmc=3.0, type_line='Instant',
         oracle_text='Search your library for up to three creature cards, reveal them, then shuffle and put those cards on top '
                     'in any order.', colors=['G', 'W'], color_identity=['G', 'W']),
    card('Birthing Pod', set_code="tst", number="Z38", mana_cost='{3}{G/P}', cmc=4.0, type_line='Artifact',
         oracle_text="({G/P} can be paid with either {G} or 2 life.)\n{1}{G/P}, {T}, Sacrifice a creature: Search your library "
                     "for a creature card with mana value equal to 1 plus the sacrificed creature's mana value, put that card "
                     "onto the battlefield, then shuffle. Activate only as a sorcery.", colors=['G'], color_identity=['G']),
    card('Summon Undead', set_code="tst", number="Z39", mana_cost='{4}{B}', cmc=5.0, type_line='Sorcery',
         oracle_text='You may mill three cards. Then return a creature card from your graveyard to the battlefield. (To mill a '
                     'card, put the top card of your library into your graveyard.)', colors=['B'], color_identity=['B']),
    card('Glowspore Shaman', set_code="tst", number="Z40", mana_cost='{B}{G}', cmc=2.0, type_line='Creature — Elf Shaman',
         oracle_text='When this creature enters, mill three cards. You may put a land card from your graveyard on top of your '
                     'library. (To mill a card, put the top card of your library into your graveyard.)', power='3', toughness='1',
         colors=['B', 'G'], color_identity=['B', 'G']),
    card('Patch Up', set_code="tst", number="Z41", mana_cost='{2}{W}', cmc=3.0, type_line='Sorcery',
         oracle_text='Return up to three target creature cards with total mana value 3 or less from your graveyard to the '
                     'battlefield.', colors=['W'], color_identity=['W']),
    card('Behold the Sinister Six!', set_code="tst", number="Z42", mana_cost='{6}{B}', cmc=7.0, type_line='Sorcery',
         oracle_text='Return up to six target creature cards with different names from your graveyard to the battlefield.',
         colors=['B'], color_identity=['B']),
    card('Eerie Ultimatum', set_code="tst", number="Z43", mana_cost='{W}{W}{B}{B}{B}{G}{G}', cmc=7.0, type_line='Sorcery',
         oracle_text='Return any number of permanent cards with different names from your graveyard to the battlefield.',
         colors=['B', 'G', 'W'], color_identity=['B', 'G', 'W']),
    card('Gate Colossus', set_code="tst", number="Z44", mana_cost='{8}', cmc=8.0, type_line='Artifact Creature — Construct',
         oracle_text="Affinity for Gates (This spell costs {1} less to cast for each Gate you control.)\nThis creature can't be "
                     "blocked by creatures with power 2 or less.\nWhenever a Gate you control enters, you may put this card from "
                     "your graveyard on top of your library.", power='8', toughness='8'),
    card('Azorius Guildgate', set_code="tst", number="Z45", cmc=0.0, type_line='Land — Gate',
         oracle_text='This land enters tapped.\n{T}: Add {W} or {U}.', color_identity=['U', 'W']),
]

NAMES = [c["name"] for c in REAL] + ["Command Tower"]


@pytest.fixture()
def cards(settings) -> Iterator[CardRepository]:
    settings.ensure_dirs()
    build_database([*fixture_cards(), *REAL], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def build(cards, players=2):
    names = ["Alice", "Bob", "Carol"][:players]
    commanders = ["Krenko, Mob Boss", "Atraxa, Praetors' Voice", "Krenko, Mob Boss"][:players]
    decks = [deck(cards, commanders[0], [*((1, n) for n in NAMES if n not in ("Plains",)), (1, "Murder"), (1, "Lightning Bolt"),
                                         (2, "Grizzly Bears"), (20, "Swamp")])]
    decks += [deck(cards, c, [(2, "Grizzly Bears"), (20, "Island")]) for c in commanders[1:]]
    state = new_game([PlayerSetup(n, cards=d) for n, d in zip(names, decks, strict=True)], shuffle=False)
    s = GameSession(enable(state), cards=cards)
    act(s, "p1", type="pass_priority")  # → Alice's first main phase
    return s


def put(s, name, zone, pid="p1", nth=0):
    c = [c for c in s.state.cards.values() if c.name == name and c.owner == pid][nth]
    act(s, "p1", type="move", card_ids=[c.id], to={"zone": zone, "player": pid})
    return s.state.cards[c.id]


def mana(s, pid="p1", **m):
    act(s, pid, type="add_mana", player=pid, mana=m)


def life(s, pid):
    return s.state.players[pid].life


def decide(s, *ids):
    d = s.state.rules.decision
    assert d is not None, "no decision"
    act(s, d.player, type="choose", decision_id=d.id, option_ids=list(ids))
    pass_until_stack_empty(s)


def level(cards, name):
    return coverage.of_characteristics(printed_from_data(cards.resolve(name), 0)).level


# -- 207.2c / 207.2d: ability words and flavor words ------------------------------------------------
def test_ability_word_activated_abilities_are_classified_as_activated():
    abilities = parse_abilities("Threshold — {3}{B}: This creature deals 3 damage to each creature and each player. Activate "
                                "only if there are seven or more cards in your graveyard.")
    assert abilities[0].kind == "activated" and abilities[0].cost == "{3}{B}"
    # a flavor word before a cost (207.2d) …
    assert parse_abilities("Sleight of Hand — {8}: Draw two cards.")[0].cost == "{8}"
    # … but never a keyword written "Name — " (702.178 max speed; 702.177 exhaust and 702.193 power-up are read as what
    # they mean since waves 4F / 7C: "[Cost]: [Effect]. Activate only once.", app/rules/restrictions.py, power_up.py)
    assert parse_abilities("Exhaust — {3}{G}: Put two +1/+1 counters on this creature.")[0].cost == "{3}{G}"
    assert parse_abilities("Power-up — {4}{R}: Put a +1/+1 counter on this creature.")[0].cost == "{4}{R}"
    ab = parse_abilities("Max speed — {T}: Draw a card.")[0]
    assert ab.kind != "activated" or ab.cost is None or "—" in ab.cost


def test_the_new_wordings_are_covered(cards):
    for name in ("Bloodsoaked Champion", "Infected Vermin", "Amarant Coral", "Gray Merchant of Asphodel",
                 "Kokusho, the Evening Star", "Exsanguinate", "Squee, Goblin Nabob", "Verdant Eidolon", "Darklight Phoenix",
                 "Bladewing's Thrall"):
        assert level(cards, name) == "FULL", name
    # an enchanted creature's trigger returning the Aura from the graveyard: the Aura's own trigger (on the battlefield as it triggers), "this
    # card" its new object in the graveyard (wave 25D: 400.7f), not a graveyard trigger
    assert level(cards, "Screams from Within") == "FULL"


def test_raid_returns_bloodsoaked_champion_from_the_graveyard_only_after_an_attack(cards):
    s = build(cards)
    champ = put(s, "Bloodsoaked Champion", "graveyard")
    mana(s, B=1, C=1)
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=champ.id, ability=1)  # 602.5b: "Activate only if you attacked this turn"
    replay_matches(s)


def test_threshold_restriction_counts_the_graveyard(cards):
    s = build(cards)
    vermin = put(s, "Infected Vermin", "battlefield")
    mana(s, B=2, C=6)
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=vermin.id, ability=1)
    for i in range(7):
        put(s, "Swamp", "graveyard", nth=i)
    act(s, "p1", type="activate_ability", card_id=vermin.id, ability=1)
    pass_until_stack_empty(s)
    assert life(s, "p1") == 37 and life(s, "p2") == 37
    replay_matches(s)


# -- "You gain life equal to the life lost this way" (119.3, 608.2c) --------------------------------
def test_exsanguinate_gains_the_total_lost_by_every_opponent(cards):
    s = build(cards, players=3)
    mana(s, B=2, C=3)
    c = put(s, "Exsanguinate", "hand")
    act(s, "p1", type="cast_spell", card_id=c.id, x_value=3)
    pass_until_stack_empty(s)
    assert (life(s, "p2"), life(s, "p3"), life(s, "p1")) == (37, 37, 46)
    replay_matches(s)


def test_gray_merchant_drains_by_devotion(cards):
    s = build(cards, players=3)
    put(s, "Kokusho, the Evening Star", "battlefield")  # {4}{B}{B}: two more black symbols
    mana(s, B=2, C=3)
    c = put(s, "Gray Merchant of Asphodel", "hand")
    act(s, "p1", type="cast_spell", card_id=c.id)
    pass_until_stack_empty(s)
    assert (life(s, "p2"), life(s, "p3"), life(s, "p1")) == (36, 36, 48)  # devotion 4, two opponents
    replay_matches(s)


def test_kokusho_counts_only_opponents_still_in_the_game(cards):
    s = build(cards, players=3)
    kokusho = put(s, "Kokusho, the Evening Star", "battlefield")
    act(s, "p3", type="concede")
    mana(s, B=2, C=1)
    murder = put(s, "Murder", "hand")
    act(s, "p1", type="cast_spell", card_id=murder.id, targets=[kokusho.id])
    pass_until_stack_empty(s)
    assert life(s, "p2") == 35 and life(s, "p1") == 45  # 800.4a: Carol is gone, only Bob lost life
    replay_matches(s)


def test_the_life_lost_needs_the_loss_right_before_it():
    from app.rules.scripts import parse_effects

    assert parse_effects("You gain life equal to the life lost this way.", None) is None
    assert parse_effects("Each opponent loses 2 life. Draw a card. You gain life equal to the life lost this way.", None) is None


# -- 122.1h: finality counters -----------------------------------------------------------------------
def test_rite_of_the_moth_returns_with_a_finality_counter_and_it_is_exiled_instead_of_dying(cards):
    s = build(cards)
    bears = put(s, "Grizzly Bears", "graveyard")
    mana(s, W=1, B=2, C=1)
    rite = put(s, "Rite of the Moth", "hand")
    act(s, "p1", type="cast_spell", card_id=rite.id, targets=[bears.id])
    pass_until_stack_empty(s)
    back = s.state.cards[bears.id]
    assert back.zone == "p1:battlefield" and back.counters.get("finality") == 1
    mana(s, B=2, C=1)
    murder = put(s, "Murder", "hand")
    act(s, "p1", type="cast_spell", card_id=murder.id, targets=[bears.id])
    pass_until_stack_empty(s)
    assert s.state.cards[bears.id].zone == "p1:exile"
    replay_matches(s)


def test_a_finality_counter_does_not_stop_other_zone_changes(cards):
    s = build(cards)
    bears = put(s, "Grizzly Bears", "battlefield")
    act(s, "p1", type="counter", card_ids=[bears.id], kind="finality", delta=1)
    act(s, "p1", type="move", card_ids=[bears.id], to={"zone": "hand"})  # (only "into a graveyard from the battlefield")
    assert s.state.cards[bears.id].zone == "p1:hand"
    replay_matches(s)


# -- 113.6m: triggered abilities that return their card from the graveyard ----------------------------
def test_squee_returns_from_the_graveyard_at_your_upkeep_and_not_from_the_battlefield(cards):
    s = build(cards)
    squee = put(s, "Squee, Goblin Nabob", "graveyard")
    run_until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind != "declare_attackers"
              and s.state.turn.number == 3)
    d = s.state.rules.decision
    assert d.player == "p1"
    yes = next(o.id for o in d.options if o.id.startswith("yes") or o.label.lower().startswith("yes"))
    decide(s, yes)
    assert s.state.cards[squee.id].zone == "p1:hand"
    replay_matches(s)


def test_squee_on_the_battlefield_has_no_upkeep_trigger(cards):
    s = build(cards)
    put(s, "Squee, Goblin Nabob", "battlefield")
    run_until(s, lambda s: s.state.turn.number == 3 and s.state.turn.phase == "main1")
    assert not s.state.rules.pending_triggers and not s.state.zones.get("stack")
    replay_matches(s)


def test_bloodghast_returns_on_landfall(cards):
    s = build(cards)
    ghast = put(s, "Bloodghast", "graveyard")
    swamp = put(s, "Swamp", "hand")
    act(s, "p1", type="play_land", card_id=swamp.id)
    pass_until_stack_empty(s)
    d = s.state.rules.decision
    assert d is not None and d.player == "p1"
    decide(s, d.options[0].id)
    assert s.state.cards[ghast.id].zone == "p1:battlefield"
    replay_matches(s)


def test_an_opponents_land_does_not_return_bloodghast(cards):
    s = build(cards)
    ghast = put(s, "Bloodghast", "graveyard")
    island = [c for c in s.state.cards.values() if c.name == "Island" and c.owner == "p2"][0]
    act(s, "p2", type="move", card_ids=[island.id], to={"zone": "battlefield"})
    pass_until_stack_empty(s)
    assert s.state.rules.decision is None and s.state.cards[ghast.id].zone == "p1:graveyard"


def test_verdant_eidolon_returns_when_you_cast_a_multicolored_spell(cards):
    s = build(cards)
    eidolon = put(s, "Verdant Eidolon", "graveyard")
    mana(s, R=1, W=1)
    charm = put(s, "Boros Charm", "hand")
    act(s, "p1", type="cast_spell", card_id=charm.id, modes=[1])
    d = s.state.rules.decision
    for _ in range(6):
        d = s.state.rules.decision
        if d is not None:
            break
        act(s, s.state.rules.priority, type="pass_priority")
    assert d is not None and d.player == "p1"
    decide(s, d.options[0].id)
    pass_until_stack_empty(s)
    assert s.state.cards[eidolon.id].zone == "p1:hand"
    replay_matches(s)


@pytest.mark.parametrize("deaths", [1, 2])
def test_darklight_phoenix_needs_two_creatures_to_have_died(cards, deaths):
    s = build(cards)
    phoenix = put(s, "Darklight Phoenix", "graveyard")
    for i in range(deaths):
        victim = put(s, "Grizzly Bears", "battlefield", nth=i)
        mana(s, B=2, C=1)
        murder = [c for c in s.state.cards.values() if c.name == "Murder" and c.owner == "p1"][0]
        act(s, "p1", type="move", card_ids=[murder.id], to={"zone": "hand"})
        act(s, "p1", type="cast_spell", card_id=murder.id, targets=[victim.id])
        pass_until_stack_empty(s)
    act(s, "p1", type="pass_priority")  # → beginning of combat: the trigger (603.4: if two or more died)
    pass_until_stack_empty(s)
    assert s.state.cards[phoenix.id].zone == ("p1:battlefield" if deaths == 2 else "p1:graveyard")
    replay_matches(s)


def test_bladewings_thrall_returns_when_a_dragon_enters(cards):
    s = build(cards)
    thrall = put(s, "Bladewing's Thrall", "graveyard")
    mana(s, B=2, C=4)
    kokusho = put(s, "Kokusho, the Evening Star", "hand")  # a Dragon Spirit
    act(s, "p1", type="cast_spell", card_id=kokusho.id)
    pass_until_stack_empty(s)
    d = s.state.rules.decision
    assert d is not None and d.player == "p1"
    decide(s, d.options[0].id)
    assert s.state.cards[thrall.id].zone == "p1:battlefield"
    replay_matches(s)


def test_a_graveyard_trigger_is_not_seen_by_the_card_before_it_got_there(cards):
    """603.10: the Thrall put into the graveyard after the Dragon entered never saw it enter."""
    s = build(cards)
    mana(s, B=2, C=4)
    kokusho = put(s, "Kokusho, the Evening Star", "hand")
    act(s, "p1", type="cast_spell", card_id=kokusho.id)
    pass_until_stack_empty(s)
    thrall = put(s, "Bladewing's Thrall", "graveyard")
    act(s, "p1", type="pass_priority")
    assert s.state.rules.decision is None or s.state.rules.decision.kind != "choose_one"
    assert s.state.cards[thrall.id].zone == "p1:graveyard"


# -- "search your library and/or graveyard …. If you search your library this way, shuffle." -----------
def library_ids(s, pid="p1"):
    return list(s.state.zones[f"{pid}:library"])


def cast_tower_winder(s):
    mana(s, G=1, C=1)
    winder = next(c for c in s.state.cards.values() if c.name == "Tower Winder")
    act(s, "p1", type="cast_spell", card_id=winder.id)
    pass_until_stack_empty(s)
    d = s.state.rules.decision
    assert d is not None and d.kind == "choose_one" and {o.id for o in d.options} == {"both", "graveyard"}
    return d


def test_searching_only_the_graveyard_does_not_shuffle(cards):
    s = build(cards)
    tower = put(s, "Command Tower", "graveyard")
    put(s, "Tower Winder", "hand")
    before = library_ids(s)
    d = cast_tower_winder(s)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["graveyard"])
    d = s.state.rules.decision
    assert [o.id for o in d.options] == [tower.id]
    decide(s, tower.id)
    assert s.state.cards[tower.id].zone == "p1:hand"
    assert library_ids(s) == before  # 701.24: the library wasn't searched, so it isn't shuffled
    replay_matches(s)


def test_searching_both_zones_is_private_and_shuffles(cards):
    s = build(cards)
    tower = put(s, "Command Tower", "library")
    put(s, "Tower Winder", "hand")
    before = set(library_ids(s))
    d = cast_tower_winder(s)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["both"])
    d = s.state.rules.decision
    assert [o.id for o in d.options] == [tower.id] and d.player == "p1"
    bob = s.view("p2")
    assert bob["rules"]["decision"]["kind"] == "waiting" and "options" not in bob["rules"]["decision"]
    decide(s, tower.id)
    assert s.state.cards[tower.id].zone == "p1:hand"
    assert not (set(library_ids(s)) & before)  # shuffled: every library card is a new object (701.24)
    replay_matches(s)


def test_finale_of_devastation_puts_a_creature_from_the_graveyard_onto_the_battlefield(cards):
    s = build(cards)
    bears = put(s, "Grizzly Bears", "graveyard")
    put(s, "Kokusho, the Evening Star", "graveyard")  # (mana value 6: more than X)
    mana(s, G=2, C=2)
    finale = put(s, "Finale of Devastation", "hand")
    act(s, "p1", type="cast_spell", card_id=finale.id, x_value=2)
    pass_until_stack_empty(s)
    d = s.state.rules.decision
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["graveyard"])
    d = s.state.rules.decision
    assert [o.id for o in d.options] == [bears.id]
    decide(s, bears.id)
    assert s.state.cards[bears.id].zone == "p1:battlefield"
    replay_matches(s)


def test_a_may_search_can_be_declined_without_a_shuffle(cards):
    s = build(cards)
    resolve = put(s, "Gideon's Resolve", "hand")
    before = library_ids(s)
    mana(s, W=1, C=4)
    act(s, "p1", type="cast_spell", card_id=resolve.id)
    pass_until_stack_empty(s)
    for _ in range(3):  # (the trigger's own "may", then which zones)
        d = s.state.rules.decision
        if d is None:
            break
        no = next((o.id for o in d.options if o.id in ("none", "no")), None)
        if no is None:
            no = next(o.id for o in d.options if "don" in o.label.lower() or o.label.lower().startswith("no"))
        decide(s, no)
    assert s.state.rules.decision is None and library_ids(s) == before
    replay_matches(s)


def test_the_shuffle_sentence_alone_stays_manual():
    from app.rules.scripts import parse_effects

    assert parse_effects("Draw a card. If you search your library this way, shuffle.", None) is None
    assert parse_effects("Search your library for a card, put it into your hand. If you search your library this way, "
                         "shuffle.", None) is None


# -- "to the battlefield tapped and attacking" (508.4) --------------------------------------------------
def test_yore_tiller_returns_a_creature_tapped_and_attacking_the_player_chosen(cards):
    s = build(cards, players=3)
    tiller = put(s, "Yore-Tiller Nephilim", "battlefield")
    bears = put(s, "Grizzly Bears", "graveyard")
    run_until(s, lambda s: s.state.turn.number == 4 and s.state.rules.decision is not None
              and s.state.rules.decision.kind == "declare_attackers")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": tiller.id, "target": "p2"}])
    for _ in range(6):  # the trigger targets the only creature card; then Alice chooses whom it attacks
        d = s.state.rules.decision
        if d is not None and any(o.id == bears.id for o in d.options):
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[bears.id])
            continue
        if d is not None:
            break
        act(s, s.state.rules.priority, type="pass_priority")
    d = s.state.rules.decision
    assert d.player == "p1" and {"p2", "p3"} <= {o.id for o in d.options}
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["p3"])
    back = s.state.cards[bears.id]
    assert back.zone == "p1:battlefield" and back.tapped
    run_until(s, lambda s: s.state.turn.phase == "main2")
    assert life(s, "p3") == 38 and life(s, "p2") == 38  # unblocked: the Bears hit Carol, the Nephilim Bob
    replay_matches(s)


def test_tapped_and_attacking_outside_combat_only_enters_tapped(cards):
    from app.rules.language import parse_sentence

    found = parse_sentence("return target creature card from your graveyard to the battlefield tapped and attacking")
    assert found is not None and found[0][0]["attacking"] and found[0][0]["tapped"]
    # (under its owner's control: 506.3b, the owner isn't attacking — not read)
    assert parse_sentence("put target creature card from a graveyard onto the battlefield tapped and attacking under its "
                          "owner's control") is None


# -- "… to the battlefield attached to this creature / that creature" (303.4f, 303.4i, 301.5e) ----------
def resolve_with(s, choice=None):
    for _ in range(8):
        d = s.state.rules.decision
        if d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[choice or d.options[0].id])
            continue
        if not s.state.zones.get("stack"):
            return
        act(s, s.state.rules.priority, type="pass_priority")


def test_dragon_breath_returns_attached_to_the_big_creature_that_entered(cards):
    s = build(cards)
    breath = put(s, "Dragon Breath", "graveyard")
    mana(s, B=2, C=4)
    kokusho = put(s, "Kokusho, the Evening Star", "hand")
    act(s, "p1", type="cast_spell", card_id=kokusho.id)
    resolve_with(s)
    got = s.state.cards[breath.id]
    assert got.zone == "p1:battlefield" and got.attached_to == kokusho.id
    replay_matches(s)


def test_iridescent_drake_takes_an_aura_from_any_graveyard_attached_to_itself(cards):
    s = build(cards)
    breath = put(s, "Dragon Breath", "graveyard")
    mana(s, U=1, C=3)
    drake = put(s, "Iridescent Drake", "hand")
    act(s, "p1", type="cast_spell", card_id=drake.id)
    resolve_with(s, breath.id)
    got = s.state.cards[breath.id]
    assert got.zone == "p1:battlefield" and got.attached_to == drake.id and got.controller == "p1"
    replay_matches(s)


def test_an_aura_that_cannot_enchant_the_creature_stays_in_the_graveyard(cards):
    """303.4i: an "Enchant land" Aura can't be put onto the battlefield attached to the Drake."""
    s = build(cards)
    growth = put(s, "Wild Growth", "graveyard")
    mana(s, U=1, C=3)
    drake = put(s, "Iridescent Drake", "hand")
    act(s, "p1", type="cast_spell", card_id=drake.id)
    resolve_with(s, growth.id)
    assert s.state.cards[growth.id].zone == "p1:graveyard"
    replay_matches(s)


def test_magnetic_snuffler_returns_an_equipment_attached_to_itself(cards):
    s = build(cards)
    blade = put(s, "Bonesplitter", "graveyard")
    mana(s, C=5)
    snuffler = put(s, "Magnetic Snuffler", "hand")
    act(s, "p1", type="cast_spell", card_id=snuffler.id)
    resolve_with(s, blade.id)
    got = s.state.cards[blade.id]
    assert got.zone == "p1:battlefield" and got.attached_to == snuffler.id
    replay_matches(s)


# -- "… cards with different names" (201.2) and Gifts piles ---------------------------------------------
def library_card(s, name, pid="p1"):
    return next(c for c in s.state.cards.values() if c.name == name and c.owner == pid and c.zone == f"{pid}:library")


def test_shared_summons_needs_different_names(cards):
    s = build(cards)
    mana(s, G=2, C=3)
    summons = put(s, "Shared Summons", "hand")
    act(s, "p1", type="cast_spell", card_id=summons.id)
    pass_until_stack_empty(s)
    d = s.state.rules.decision
    bears = [c.id for c in s.state.cards.values() if c.name == "Grizzly Bears" and c.zone == "p1:library"]
    with pytest.raises(ActionError, match="different names"):
        act(s, "p1", type="choose", decision_id=d.id, option_ids=bears[:2])
    kokusho = library_card(s, "Kokusho, the Evening Star")
    decide(s, bears[0], kokusho.id)
    assert {s.state.cards[bears[0]].zone, s.state.cards[kokusho.id].zone} == {"p1:hand"}
    replay_matches(s)


def test_gifts_ungiven_the_target_opponent_splits_the_revealed_cards(cards):
    s = build(cards, players=3)
    mana(s, U=1, C=3)
    gifts = put(s, "Gifts Ungiven", "hand")
    act(s, "p1", type="cast_spell", card_id=gifts.id, targets=["p3"])
    pass_until_stack_empty(s)
    d = s.state.rules.decision
    assert d.player == "p1"
    bob = s.view("p2")["rules"]["decision"]
    assert bob["kind"] == "waiting" and "options" not in bob  # 401.2: Alice's library stays hidden while she searches
    found = [library_card(s, n).id for n in ("Kokusho, the Evening Star", "Squee, Goblin Nabob", "Murder", "Bloodghast")]
    act(s, "p1", type="choose", decision_id=d.id, option_ids=found)
    d = s.state.rules.decision
    assert d.player == "p3" and {o.id for o in d.options} == set(found) and d.min_choices == d.max_choices == 2
    decide(s, found[0], found[1])
    zones = [s.state.cards[c].zone for c in found]
    assert zones == ["p1:graveyard", "p1:graveyard", "p1:hand", "p1:hand"]
    replay_matches(s)


def test_gifts_with_two_cards_found_puts_both_in_the_graveyard(cards):
    s = build(cards)
    mana(s, U=1, C=3)
    gifts = put(s, "Gifts Ungiven", "hand")
    act(s, "p1", type="cast_spell", card_id=gifts.id, targets=["p2"])
    pass_until_stack_empty(s)
    found = [library_card(s, n).id for n in ("Murder", "Bloodghast")]
    decide(s, *found)
    assert [s.state.cards[c].zone for c in found] == ["p1:graveyard", "p1:graveyard"]
    replay_matches(s)


def test_realms_uncharted_the_caster_picks_which_opponent_chooses(cards):
    s = build(cards, players=3)
    for name in ("Command Tower", "Swamp"):
        put(s, name, "library")
    mana(s, G=1, C=2)
    realms = put(s, "Realms Uncharted", "hand")
    act(s, "p1", type="cast_spell", card_id=realms.id)
    pass_until_stack_empty(s)
    d = s.state.rules.decision
    lands = {o.id for o in d.options}
    assert all(s.state.cards[c].name in ("Command Tower", "Swamp", "Azorius Guildgate") for c in lands)
    swamps = [c for c in lands if s.state.cards[c].name == "Swamp"]
    with pytest.raises(ActionError, match="different names"):
        act(s, "p1", type="choose", decision_id=d.id, option_ids=swamps[:2])
    found = [library_card(s, n).id for n in ("Command Tower", "Swamp", "Azorius Guildgate")]
    act(s, "p1", type="choose", decision_id=d.id, option_ids=found)
    d = s.state.rules.decision
    assert d.player == "p1" and {o.id for o in d.options} == {"p2", "p3"}  # (the caster picks the opponent)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["p3"])
    d = s.state.rules.decision
    assert d.player == "p3" and d.min_choices == d.max_choices == 2
    decide(s, found[0], found[1])
    assert [s.state.cards[c].zone for c in found] == ["p1:graveyard", "p1:graveyard", "p1:hand"]
    replay_matches(s)


# -- hand sizes: "the number of cards in that player's hand [minus 4]" (402.3, 107.1b) -------------------
def hand_size(s, pid, n):
    """Leave ``pid`` with exactly ``n`` cards in hand (the rest back on top of the library)."""
    hand = list(s.state.zones[f"{pid}:hand"])
    while len(hand) < n:
        act(s, pid, type="draw", count=1)
        hand = list(s.state.zones[f"{pid}:hand"])
    if len(hand) > n:
        act(s, pid, type="move", card_ids=hand[n:], to={"zone": "library", "player": pid})


def test_sudden_impact_counts_the_target_players_hand(cards):
    s = build(cards)
    hand_size(s, "p2", 5)
    mana(s, R=1, C=3)
    impact = put(s, "Sudden Impact", "hand")
    act(s, "p1", type="cast_spell", card_id=impact.id, targets=["p2"])
    pass_until_stack_empty(s)
    assert life(s, "p2") == 35
    replay_matches(s)


@pytest.mark.parametrize(("cards_in_hand", "damage"), [(6, 2), (3, 0)])  # (107.1b: never less than 0)
def test_iron_maiden_deals_the_hand_size_minus_four_at_each_opponents_upkeep(cards, cards_in_hand, damage):
    s = build(cards)
    put(s, "Iron Maiden", "battlefield")
    hand_size(s, "p2", cards_in_hand)
    run_until(s, lambda s: s.state.turn.number == 2 and s.state.turn.phase == "main1")
    assert life(s, "p2") == 40 - damage and life(s, "p1") == 40
    replay_matches(s)


def test_dark_suspicions_subtracts_your_hand(cards):
    s = build(cards)
    put(s, "Dark Suspicions", "battlefield")
    hand_size(s, "p1", 2)
    hand_size(s, "p2", 7)
    run_until(s, lambda s: s.state.turn.number == 2 and s.state.turn.phase == "main1")
    assert life(s, "p2") == 35
    replay_matches(s)


def test_a_hand_size_with_no_player_to_bind_stays_manual():
    from app.rules.scripts import parse_effects

    # "each opponent … that player's hand": a different number for each recipient (not read)
    assert parse_effects("It deals damage to each opponent equal to the number of cards in that player's hand.", None) is None


# -- "excess damage is dealt to that creature's controller instead" (120.4a, 702.2c) --------------------
def bobs_bears(s):
    return [c for c in s.state.cards.values() if c.name == "Grizzly Bears" and c.owner == "p2"][0]


@pytest.mark.parametrize(("marked", "to_player"), [(0, 2), (1, 3)])
def test_flame_spill_sends_the_excess_to_the_controller(cards, marked, to_player):
    s = build(cards)
    bears = put(s, "Grizzly Bears", "battlefield", pid="p2")
    bears = bobs_bears(s)
    if marked:
        act(s, "p1", type="set_damage", card_ids=[bears.id], value=marked)
    mana(s, R=1, C=2)
    spill = put(s, "Flame Spill", "hand")
    act(s, "p1", type="cast_spell", card_id=spill.id, targets=[bears.id])
    pass_until_stack_empty(s)
    assert s.state.cards[bears.id].zone == "p2:graveyard" and life(s, "p2") == 40 - to_player
    replay_matches(s)


def ram_through(s, text):
    act(s, "p1", type="create_token", player="p1", token={"name": "Ram", "type_line": "Token Creature — Beast", "power": "5",
                                                          "toughness": "5", "text": text})
    ram = next(c for c in s.state.cards.values() if c.name == "Ram")
    put(s, "Grizzly Bears", "battlefield", pid="p2")
    bears = bobs_bears(s)
    mana(s, G=1, C=1)
    spell = put(s, "Ram Through", "hand")
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=[ram.id, bears.id], target_counts=[1, 1])
    pass_until_stack_empty(s)
    return bears


@pytest.mark.parametrize(("text", "to_player"), [("Trample", 3), ("", 0), ("Trample, deathtouch", 4)])
def test_ram_through_redirects_only_with_trample(cards, text, to_player):
    s = build(cards)
    bears = ram_through(s, text)
    assert s.state.cards[bears.id].zone == "p2:graveyard" and life(s, "p2") == 40 - to_player
    replay_matches(s)


def test_excess_needs_the_damage_right_before_it():
    from app.rules.scripts import parse_effects

    assert parse_effects("Draw a card. Excess damage is dealt to that creature's controller instead.", None) is None
    assert parse_effects("~ deals 4 damage to each creature. Excess damage is dealt to that creature's controller instead.",
                         None) is None


# -- 702.53a transmute -------------------------------------------------------------------------------
def test_transmute_finds_a_card_with_the_same_mana_value_privately(cards):
    s = build(cards)
    guard = put(s, "Dimir House Guard", "hand")
    library = set(s.state.zones["p1:library"])
    mana(s, B=2, C=1)
    act(s, "p1", type="activate_ability", card_id=guard.id, ability=2)
    assert s.state.cards[guard.id].zone == "p1:graveyard"  # discarded as the cost
    pass_until_stack_empty(s)
    d = s.state.rules.decision
    assert d.player == "p1" and d.options
    assert all(s.state.cards[o.id].zone == "p1:library" and level_mv(s, o.id) == 4 for o in d.options)
    bob = s.view("p2")["rules"]["decision"]
    assert bob["kind"] == "waiting" and "options" not in bob
    pick = d.options[0].id
    decide(s, pick)
    assert s.state.cards[pick].zone == "p1:hand"
    assert not (set(s.state.zones["p1:library"]) & library)  # shuffled (701.24)
    replay_matches(s)


def level_mv(s, cid):
    from app.rules.plan import Plan

    return Plan(s.state, "p1", s.cards, None).ch(s.state.cards[cid]).mana_value


def test_transmute_only_as_a_sorcery(cards):
    s = build(cards)
    guard = put(s, "Dimir House Guard", "hand")
    mana(s, B=2, C=1, R=1)
    bolt = put(s, "Lightning Bolt", "hand")
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"], )
    if s.state.zones.get("stack"):
        with pytest.raises(ActionError, match="sorcery"):
            act(s, "p1", type="activate_ability", card_id=guard.id, ability=2)
    pass_until_stack_empty(s)
    run_until(s, lambda s: s.state.turn.number == 2 and s.state.turn.phase == "main1")
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=guard.id, ability=2)


# -- "discards N cards at random" (701.9b) and Gamble -------------------------------------------------
def test_hymn_to_tourach_discards_two_random_cards_nobody_chooses(cards):
    s = build(cards)
    hand_size(s, "p2", 5)
    before = list(s.state.zones["p2:hand"])
    mana(s, B=2)
    hymn = put(s, "Hymn to Tourach", "hand")
    act(s, "p1", type="cast_spell", card_id=hymn.id, targets=["p2"])
    pass_until_stack_empty(s)
    assert s.state.rules.decision is None  # (at random: no choice for anyone)
    gone = [c for c in before if s.state.cards[c].zone == "p2:graveyard"]
    assert len(gone) == 2 and len(s.state.zones["p2:hand"]) == 3
    replay_matches(s)  # the recorded move says which cards: the replay is the same table


def test_a_random_discard_from_a_small_hand_takes_what_there_is(cards):
    s = build(cards)
    hand_size(s, "p2", 1)
    mana(s, B=2)
    hymn = put(s, "Hymn to Tourach", "hand")
    act(s, "p1", type="cast_spell", card_id=hymn.id, targets=["p2"])
    pass_until_stack_empty(s)
    assert s.state.zones["p2:hand"] == []
    replay_matches(s)


def test_gamble_tutors_then_discards_at_random_then_shuffles(cards):
    s = build(cards)
    hand_size(s, "p1", 0)
    gamble = put(s, "Gamble", "hand")
    library = set(s.state.zones["p1:library"])
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=gamble.id)
    pass_until_stack_empty(s)
    d = s.state.rules.decision
    assert d.player == "p1" and d.min_choices == 1
    kokusho = library_card(s, "Kokusho, the Evening Star")
    decide(s, kokusho.id)
    # the only card in hand was the one found: it is the one discarded at random
    assert s.state.cards[kokusho.id].zone == "p1:graveyard" and s.state.zones["p1:hand"] == []
    assert not (set(s.state.zones["p1:library"]) & library)  # shuffled (701.24)
    replay_matches(s)


# -- "then shuffle and put those cards on top in any order" (401.4) ----------------------------------
def test_congregation_at_dawn_stacks_the_found_cards_in_the_chosen_order(cards):
    s = build(cards)
    mana(s, G=2, W=1)
    spell = put(s, "Congregation at Dawn", "hand")
    act(s, "p1", type="cast_spell", card_id=spell.id)
    pass_until_stack_empty(s)
    names = ("Kokusho, the Evening Star", "Squee, Goblin Nabob", "Bloodghast")
    found = [library_card(s, n).id for n in names]
    act(s, "p1", type="choose", decision_id=s.state.rules.decision.id, option_ids=found)
    d = s.state.rules.decision
    assert d.kind == "order" and d.player == "p1" and len(d.options) == 3
    bob = s.view("p2")["rules"]["decision"]
    assert bob["kind"] == "waiting" and "options" not in bob  # 401.4: the order is the searcher's private choice
    order = [o.id for o in sorted(d.options, key=lambda o: o.label)]  # Bloodghast, Kokusho, Squee
    decide(s, *order)
    top = [s.state.cards[c].name for c in s.state.zones["p1:library"][:3]]
    assert top == ["Bloodghast", "Kokusho, the Evening Star", "Squee, Goblin Nabob"]
    replay_matches(s)


# -- "mana value equal to 1 plus the sacrificed creature's mana value" (Birthing Pod; 608.2h, 118.3) --------
def test_birthing_pod_finds_a_creature_one_mana_value_higher(cards):
    s = build(cards)
    pod = put(s, "Birthing Pod", "battlefield")
    bears = put(s, "Grizzly Bears", "battlefield")  # mana value 2
    mana(s, G=1, C=1)
    act(s, "p1", type="activate_ability", card_id=pod.id, ability=0, cost_choices=[{"component": 2, "cards": [bears.id]}], life_symbols=[])  # (wave 50B: the {G/P} is announced paid with mana)
    assert s.state.cards[bears.id].zone == "p1:graveyard"
    pass_until_stack_empty(s)
    d = s.state.rules.decision
    names = {s.state.cards[o.id].name for o in d.options}
    assert names and all(level_mv(s, o.id) == 3 for o in d.options) and "Squee, Goblin Nabob" in names
    squee = next(o.id for o in d.options if s.state.cards[o.id].name == "Squee, Goblin Nabob")
    decide(s, squee)
    assert s.state.cards[squee].zone == "p1:battlefield"
    replay_matches(s)


# -- "You may mill three cards. Then return …" and "… from your graveyard on top of your library" -------------
@pytest.mark.parametrize("mill", [True, False])
def test_summon_undead_returns_a_creature_whether_or_not_you_milled(cards, mill):
    s = build(cards)
    bears = put(s, "Grizzly Bears", "graveyard")
    library = len(s.state.zones["p1:library"])
    mana(s, B=1, C=4)
    spell = put(s, "Summon Undead", "hand")
    act(s, "p1", type="cast_spell", card_id=spell.id)
    pass_until_stack_empty(s)
    d = s.state.rules.decision
    assert d.kind == "confirm" and d.player == "p1"
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["yes" if mill else "no"])
    assert len(s.state.zones["p1:library"]) == library - 1 - (3 if mill else 0)  # (Summon Undead itself left the library)
    d = s.state.rules.decision
    if d is not None:  # (several creature cards to choose from after milling)
        decide(s, bears.id)
    assert s.state.cards[bears.id].zone == "p1:battlefield"
    replay_matches(s)


def test_glowspore_shaman_puts_a_land_from_the_graveyard_on_top(cards):
    s = build(cards)
    swamp = put(s, "Swamp", "graveyard")
    mana(s, B=1, G=1)
    shaman = put(s, "Glowspore Shaman", "hand")
    act(s, "p1", type="cast_spell", card_id=shaman.id)
    pass_until_stack_empty(s)
    d = s.state.rules.decision
    assert d is not None and d.player == "p1" and swamp.id in {o.id for o in d.options} and d.min_choices == 0
    decide(s, swamp.id)
    assert s.state.zones["p1:library"][0] == swamp.id
    replay_matches(s)


# -- "up to three target creature cards with total mana value 3 or less" (601.2c) ------------------------
def test_patch_up_targets_within_the_total_mana_value(cards):
    s = build(cards)
    a = put(s, "Grizzly Bears", "graveyard", nth=0)  # mana value 2
    b = put(s, "Grizzly Bears", "graveyard", nth=1)
    champ = put(s, "Bloodsoaked Champion", "graveyard")  # mana value 1
    mana(s, W=1, C=2)
    patch = put(s, "Patch Up", "hand")
    with pytest.raises(ActionError, match="total mana value"):
        act(s, "p1", type="cast_spell", card_id=patch.id, targets=[a.id, b.id], target_counts=[2])
    act(s, "p1", type="cast_spell", card_id=patch.id, targets=[a.id, champ.id], target_counts=[2])
    pass_until_stack_empty(s)
    assert {s.state.cards[c].zone for c in (a.id, champ.id)} == {"p1:battlefield"} and s.state.cards[b.id].zone == "p1:graveyard"
    replay_matches(s)


# -- "… cards with different names" as targets (601.2c) and as a choice on resolution (608.2d) -------------
def test_behold_the_sinister_six_targets_need_different_names(cards):
    s = build(cards)
    a = put(s, "Grizzly Bears", "graveyard", nth=0)
    b = put(s, "Grizzly Bears", "graveyard", nth=1)
    squee = put(s, "Squee, Goblin Nabob", "graveyard")
    mana(s, B=1, C=6)
    spell = put(s, "Behold the Sinister Six!", "hand")
    with pytest.raises(ActionError, match="different names"):
        act(s, "p1", type="cast_spell", card_id=spell.id, targets=[a.id, b.id], target_counts=[2])
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=[a.id, squee.id], target_counts=[2])
    pass_until_stack_empty(s)
    assert s.state.cards[a.id].zone == s.state.cards[squee.id].zone == "p1:battlefield"
    replay_matches(s)


def test_eerie_ultimatum_chooses_permanent_cards_with_different_names(cards):
    s = build(cards)
    a = put(s, "Grizzly Bears", "graveyard", nth=0)
    b = put(s, "Grizzly Bears", "graveyard", nth=1)
    swamp = put(s, "Swamp", "graveyard")
    mana(s, W=2, B=3, G=2)
    spell = put(s, "Eerie Ultimatum", "hand")
    act(s, "p1", type="cast_spell", card_id=spell.id)
    pass_until_stack_empty(s)
    d = s.state.rules.decision
    with pytest.raises(ActionError, match="different names"):
        act(s, "p1", type="choose", decision_id=d.id, option_ids=[a.id, b.id])
    decide(s, a.id, swamp.id)
    assert s.state.cards[a.id].zone == s.state.cards[swamp.id].zone == "p1:battlefield"
    assert s.state.cards[b.id].zone == "p1:graveyard"
    replay_matches(s)


def test_gate_colossus_goes_from_the_graveyard_to_the_top_of_the_library(cards):
    s = build(cards)
    colossus = put(s, "Gate Colossus", "graveyard")
    gate = put(s, "Azorius Guildgate", "hand")
    act(s, "p1", type="play_land", card_id=gate.id)
    pass_until_stack_empty(s)
    d = s.state.rules.decision
    assert d is not None and d.player == "p1"
    decide(s, next(o.id for o in d.options if o.id == "yes" or o.label.lower().startswith("yes")))
    assert s.state.zones["p1:library"][0] == colossus.id
    replay_matches(s)

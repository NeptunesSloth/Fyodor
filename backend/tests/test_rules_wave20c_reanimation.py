"""Wave 20C: reanimation / death-trigger wordings (CR 2026-09-25).

* "[A] and you may [B]" / "[A]. You may [B]." as the end of an ability (608.2c): only B is optional; it is asked as the resolution
  reaches it (unless_pays.may_rest) and nothing may follow it ("Sword of Light and Shadow"). B's target is chosen when the
  ability goes on the stack (603.3d) whatever the answer.
* "When this creature dies, you may exile it. When you do, …" (603.12): the card is the one now in the graveyard.
* "target card with cycling / mutate / awaken from your graveyard", "creatures you control with toxic" (702.29f: typecycling is
  cycling).
* "create Tuktuk the Returned, a legendary …" on Tuktuk the Explorer: the short name before "the Capital" is another name.

Real Oracle text; every scenario checks the replay and a save/load round trip."""

from __future__ import annotations

import pytest

from app.cards.importer import build_database
from app.game.errors import ActionError
from app.game.session import GameSession
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_attachments import build, named, to_hand, token
from tests.test_rules_conditionals import attack
from tests.test_rules_effects import mana, replay_matches
from tests.test_rules_wave4l_attached import equip, put, to_attack

EXTRA = [
    card('Sword of Light and Shadow', set_code='tst', number='X0', mana_cost='{3}', cmc=3.0, type_line='Artifact — Equipment',
         oracle_text='Equipped creature gets +2/+2 and has protection from white and from black.\nWhenever equipped creature deals combat damage to a player, you gain 3 life and you may return up to one target creature card from your graveyard to your hand.\nEquip {2}',
         power=None, toughness=None, colors=[], color_identity=[], keywords=['Equip']),
    card('Undead Butler', set_code='tst', number='X1', mana_cost='{2}{B}', cmc=3.0, type_line='Creature — Zombie',
         oracle_text='When this creature enters, mill three cards. (Put the top three cards of your library into your graveyard.)\nWhen this creature dies, you may exile it. When you do, return target creature card from your graveyard to your hand.',
         power='3', toughness='2', colors=['B'], color_identity=['B'], keywords=['Mill']),
    card('Sandbender Scavengers', set_code='tst', number='X2', mana_cost='{1}{B}', cmc=2.0, type_line='Creature — Human Rogue',
         oracle_text="Whenever you sacrifice another permanent, put a +1/+1 counter on this creature.\nWhen this creature dies, you may exile it. When you do, return target creature card with mana value less than or equal to this creature's power from your graveyard to the battlefield.",
         power='1', toughness='1', colors=['B'], color_identity=['B'], keywords=[]),
    card('Sacred Excavation', set_code='tst', number='X3', mana_cost='{1}{W}', cmc=2.0, type_line='Sorcery',
         oracle_text='Return up to two target cards with cycling from your graveyard to your hand.',
         power=None, toughness=None, colors=['W'], color_identity=['W'], keywords=[]),
    card('Tuktuk the Explorer', set_code='tst', number='X4', mana_cost='{1}{R}', cmc=2.0, type_line='Legendary Creature — Goblin',
         oracle_text='Haste\nWhen Tuktuk the Explorer dies, create Tuktuk the Returned, a legendary 5/5 colorless Goblin Golem artifact creature token.',
         power='2', toughness='2', colors=['R'], color_identity=['R'], keywords=['Haste']),
    card("Skrelv's Hive", set_code='tst', number='X5', mana_cost='{1}{W}', cmc=2.0, type_line='Enchantment',
         oracle_text='At the beginning of your upkeep, you lose 1 life and create a 1/1 colorless Phyrexian Mite artifact creature token with toxic 1 and "This token can\'t block."\nCorrupted — As long as an opponent has three or more poison counters, creatures you control with toxic have lifelink.',
         power=None, toughness=None, colors=['W'], color_identity=['W'], keywords=[]),
    card("Praetor's Counsel", set_code='tst', number='X7', mana_cost='{5}{G}{G}{G}', cmc=8.0, type_line='Sorcery',
         oracle_text="Return all cards from your graveyard to your hand. Exile Praetor's Counsel. You have no maximum hand size for the rest of the game.",
         power=None, toughness=None, colors=['G'], color_identity=['G'], keywords=[]),
    card('Wrenn and Seven', set_code='tst', number='X8', mana_cost='{3}{G}{G}', cmc=5.0, type_line='Legendary Planeswalker — Wrenn',
         oracle_text='+1: Reveal the top four cards of your library. Put all land cards revealed this way into your hand and the rest into your graveyard.\n0: Put any number of land cards from your hand onto the battlefield tapped.\n−3: Create a green Treefolk creature token with reach and "This token\'s power and toughness are each equal to the number of lands you control."\n−8: Return all permanent cards from your graveyard to your hand. You get an emblem with "You have no maximum hand size."',
         power=None, toughness=None, loyalty='5', colors=['G'], color_identity=['G'], keywords=[]),
    card('Smile at Death', set_code='tst', number='X9', mana_cost='{3}{W}', cmc=4.0, type_line='Enchantment',
         oracle_text='At the beginning of your upkeep, return up to two target creature cards with power 2 or less from your graveyard to the battlefield. Put a +1/+1 counter on each of those creatures.',
         power=None, toughness=None, colors=['W'], color_identity=['W'], keywords=[]),
    card('Monstrosity of the Lake', set_code='tst', number='XA', mana_cost='{4}{U}', cmc=5.0, type_line='Legendary Creature — Kraken',
         oracle_text='When Monstrosity of the Lake enters, you may pay {5}. If you do, tap all creatures your opponents control, then put a stun counter on each of those creatures. (If a permanent with a stun counter would become untapped, remove one from it instead.)\nIslandcycling {2} ({2}, Discard this card: Search your library for an Island card, reveal it, put it into your hand, then shuffle.)',
         power='4', toughness='6', colors=['U'], color_identity=['U'], keywords=['Islandcycling', 'Landcycling', 'Typecycling', 'Cycling']),
    card('Cycler Test Elf', set_code='tst', number='X6', mana_cost='{1}{G}', cmc=2.0, type_line='Creature — Elf',
         oracle_text='Forestcycling {1} ({1}, Discard this card: Search your library for a Forest card, reveal it, put it into your hand, then shuffle.)',
         power='1', toughness='1', colors=['G'], color_identity=['G'], keywords=['Forestcycling', 'Landcycling', 'Typecycling', 'Cycling']),
]
FULL = ['Sword of Light and Shadow', 'Undead Butler', 'Sandbender Scavengers', 'Sacred Excavation', 'Tuktuk the Explorer', "Skrelv's Hive",
        'Cycler Test Elf', "Praetor's Counsel", 'Wrenn and Seven', 'Smile at Death', 'Monstrosity of the Lake']


@pytest.fixture()
def card_db(settings):
    settings.ensure_dirs()
    build_database(fixture_cards() + EXTRA, settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def reloaded(s):
    return GameSession(s.history.rebuild(), cards=s.cards)


def life(s, pid="p1"):
    return s.state.players[pid].life


def to_gy(s, name, pid="p1"):
    c = next(c for c in s.state.cards.values() if c.name == name and c.owner == pid)
    act(s, pid, type="move", card_ids=[c.id], to={"player": pid, "zone": "graveyard"})
    return c


@pytest.mark.parametrize("name", FULL)
def test_coverage_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def play_on(s, answer, blockers=()):
    """Play on to the second main phase: a yes/no question gets ``answer``, ``blockers`` (attacker, blocker) pairs block, and anything
    else is answered with the first options."""
    for _ in range(80):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[{"blocker_id": b.id, "attacker_id": a.id} for a, b in blockers])
        elif d is not None:
            ids = [o.id for o in d.options]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[answer] if answer in ids else ids[: max(1, d.min_choices)])
        elif s.state.turn.phase == "main2" and not s.state.zones.get("stack"):
            return
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("combat never ended")


def die_in_combat(s, creature, answer="yes"):
    """``creature`` attacks Bob, whose 5/5 Ogre blocks and kills it."""
    act(s, "p2", type="create_token", player="p2", token={"name": "Ogre", "type_line": "Token Creature — Ogre", "power": "5",
                                                         "toughness": "5", "text": ""})
    s.state.rules.controlled_since[creature.id].turn = 0
    to_attack(s)
    attack(s, (creature, "p2"))
    play_on(s, answer, [(creature, named(s, "Ogre"))])


@pytest.mark.parametrize("answer", ["yes", "no"])
def test_sword_of_light_and_shadow_only_the_return_is_optional(cards, answer):
    s = build(cards, "Sword of Light and Shadow", "Llanowar Elves")
    bear = token(s, "p1", "Bear")
    equip(s, "Sword of Light and Shadow", bear)
    elves = to_gy(s, "Llanowar Elves")
    to_attack(s)
    before = life(s)
    attack(s, (bear, "p2"))
    play_on(s, answer)
    assert life(s) == before + 3  # "you gain 3 life" happens either way
    assert s.state.cards[elves.id].zone == ("p1:hand" if answer == "yes" else "p1:graveyard")
    replay_matches(s)
    replay_matches(reloaded(s))


def test_undead_butler_exiles_itself_and_the_reflexive_trigger_returns_a_creature(cards):
    s = build(cards, "Undead Butler", "Llanowar Elves")
    butler = put(s, "Undead Butler")
    elves = to_gy(s, "Llanowar Elves")
    die_in_combat(s, butler)
    assert s.state.cards[butler.id].zone == "p1:exile"  # "you may exile it"
    assert s.state.cards[elves.id].zone == "p1:hand"  # "When you do, return target creature card from your graveyard to your hand"
    replay_matches(s)
    replay_matches(reloaded(s))


def test_undead_butler_declined_keeps_the_card_and_nothing_returns(cards):
    s = build(cards, "Undead Butler", "Llanowar Elves")
    butler = put(s, "Undead Butler")
    elves = to_gy(s, "Llanowar Elves")
    die_in_combat(s, butler, answer="no")
    assert s.state.cards[butler.id].zone == "p1:graveyard" and s.state.cards[elves.id].zone == "p1:graveyard"
    replay_matches(s)


def test_sandbender_scavengers_uses_its_last_known_power(cards):
    """"mana value less than or equal to this creature's power": the 1/1 grew by two counters, so a 3-mana creature is legal."""
    s = build(cards, "Sandbender Scavengers", "Foundry Inspector")
    sand = put(s, "Sandbender Scavengers")
    act(s, "p1", type="counter", card_ids=[sand.id], kind="+1/+1", delta=2)
    inspector = to_gy(s, "Foundry Inspector")
    die_in_combat(s, sand)
    assert s.state.cards[sand.id].zone == "p1:exile"
    assert s.state.cards[inspector.id].zone == "p1:battlefield"
    replay_matches(s)
    replay_matches(reloaded(s))


def test_sacred_excavation_returns_cards_with_cycling_including_typecycling(cards):
    s = build(cards, "Sacred Excavation", "Cycler Test Elf", "Llanowar Elves")
    elf = to_gy(s, "Cycler Test Elf")
    plain = to_gy(s, "Llanowar Elves")
    spell = to_hand(s, "Sacred Excavation")
    mana(s, "p1", W=1, C=1)
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=[elf.id], target_counts=[1])
    from tests.test_rules_conditionals import settle

    settle(s)
    assert s.state.cards[elf.id].zone == "p1:hand" and s.state.cards[plain.id].zone == "p1:graveyard"
    replay_matches(s)
    replay_matches(reloaded(s))


def test_a_card_without_cycling_is_no_target_of_sacred_excavation(cards):
    s = build(cards, "Sacred Excavation", "Llanowar Elves")
    spell = to_hand(s, "Sacred Excavation")
    plain = to_gy(s, "Llanowar Elves")
    mana(s, "p1", W=1, C=1)
    with pytest.raises(ActionError, match="legal target|target"):
        act(s, "p1", type="cast_spell", card_id=spell.id, targets=[plain.id], target_counts=[1])


def test_tuktuk_the_explorer_leaves_tuktuk_the_returned(cards):
    s = build(cards, "Tuktuk the Explorer")
    tuk = put(s, "Tuktuk the Explorer")
    die_in_combat(s, tuk)
    back = named(s, "Tuktuk the Returned")
    assert back.zone == "p1:battlefield" and back.is_token and (back.token.power, back.token.toughness) == ("5", "5")
    assert "Legendary" in back.token.type_line and "Golem" in back.token.type_line
    replay_matches(s)
    replay_matches(reloaded(s))


def test_praetors_counsel_returns_the_graveyard_exiles_itself_and_ends_the_hand_limit_for_good(cards):
    """"You have no maximum hand size for the rest of the game.": the player has it (RulesState.no_max_hand) after the spell is gone."""
    from app.rules import hand_size
    from app.rules.plan import Plan
    from tests.test_rules_conditionals import settle

    s = build(cards, "Praetor's Counsel", "Llanowar Elves", "Lightning Bolt")
    elves, bolt = to_gy(s, "Llanowar Elves"), to_gy(s, "Lightning Bolt")
    spell = to_hand(s, "Praetor's Counsel")
    p = Plan(s.state, "p1", s.cards, None)
    assert hand_size.maximum(p, "p1") == 7 and hand_size.maximum(p, "p2") == 7
    mana(s, "p1", G=3, C=5)
    act(s, "p1", type="cast_spell", card_id=spell.id)
    settle(s)
    assert s.state.cards[elves.id].zone == "p1:hand" and s.state.cards[bolt.id].zone == "p1:hand"
    assert s.state.cards[spell.id].zone == "p1:exile"
    p = Plan(s.state, "p1", s.cards, None)
    assert hand_size.maximum(p, "p1") is None and hand_size.maximum(p, "p2") == 7
    replay_matches(s)
    replay_matches(reloaded(s))
    assert reloaded(s).state.rules.no_max_hand == ["p1"]  # (a save keeps it)


def test_smile_at_death_puts_a_counter_on_each_of_those_creatures(cards):
    """"Put a +1/+1 counter on each of those creatures." = each of the (up to two) creatures the sentence before returned."""
    from tests.test_rules_conditionals import settle, to_turn

    s = build(cards, "Smile at Death", "Llanowar Elves", "Abbot of Keral Keep", "Foundry Inspector")
    put(s, "Smile at Death")
    elves, birds, giant = to_gy(s, "Llanowar Elves"), to_gy(s, "Abbot of Keral Keep"), to_gy(s, "Foundry Inspector")
    to_turn(s, 3, "upkeep")
    d = s.state.rules.decision
    assert d is not None and giant.id not in [o.id for o in d.options]  # (power 3: not a legal target)
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[elves.id, birds.id])
    settle(s)
    zones ={c.name: s.state.cards[c.id].zone for c in (elves, birds, giant)}
    assert zones["Foundry Inspector"] == "p1:graveyard"  # (power 3: not a legal target)
    assert zones["Llanowar Elves"] == "p1:battlefield" and zones["Abbot of Keral Keep"] == "p1:battlefield"
    assert s.state.cards[elves.id].counters.get("+1/+1") == 1 and s.state.cards[birds.id].counters.get("+1/+1") == 1
    replay_matches(s)
    replay_matches(reloaded(s))


def test_vulture_counts_only_the_fliers_that_dealt_combat_damage(cards):
    from tests.test_rules_conditionals import token_of

    s = build(cards, "Llanowar Elves")
    text = ("Flying\nWhenever one or more creatures you control with flying deal combat damage to a player, put a +1/+1 counter on each of "
            "those creatures and draw a card.")
    vulture = token_of(s, "p1", "Vulture", "Token Legendary Creature — Human", "2/2", text)
    flier = token_of(s, "p1", "Flier", "Token Creature — Bird", "1/1", "Flying")
    ground = token_of(s, "p1", "Ground", "Token Creature — Bear", "2/2", "")
    for c in (vulture, flier, ground):
        s.state.rules.controlled_since[c.id].turn = 0
    to_attack(s)
    hand = len(s.state.zones["p1:hand"])
    attack(s, (vulture, "p2"), (flier, "p2"), (ground, "p2"))
    play_on(s, "yes")
    counters = {c.name: s.state.cards[c.id].counters.get("+1/+1", 0) for c in (vulture, flier, ground)}
    assert counters == {"Vulture": 1, "Flier": 1, "Ground": 0}
    assert len(s.state.zones["p1:hand"]) == hand + 1  # (one trigger for the damage dealt at once: one card)
    replay_matches(s)
    replay_matches(reloaded(s))


def test_monstrosity_of_the_lake_stuns_each_creature_it_tapped(cards):
    """"tap all creatures your opponents control, then put a stun counter on each of those creatures": the creatures tapped, not mine."""
    from tests.test_rules_conditionals import pick

    s = build(cards, "Monstrosity of the Lake")
    mine = token(s, "p1", "Mine")
    theirs = token(s, "p2", "Theirs")
    theirs2 = token(s, "p2", "Theirs Too")
    kraken = to_hand(s, "Monstrosity of the Lake")
    mana(s, "p1", U=1, C=9)
    act(s, "p1", type="cast_spell", card_id=kraken.id)
    for _ in range(20):
        d = s.state.rules.decision
        if d is not None:
            pick(s, "pay") if "pay" in [o.id for o in d.options] else pick(s, d.options[0].id)
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    assert s.state.cards[theirs.id].tapped and s.state.cards[theirs2.id].tapped and not s.state.cards[mine.id].tapped
    stun = {c.name: s.state.cards[c.id].counters.get("stun", 0) for c in (mine, theirs, theirs2)}
    assert stun == {"Mine": 0, "Theirs": 1, "Theirs Too": 1}
    replay_matches(s)
    replay_matches(reloaded(s))


def test_wrenn_and_seven_ultimate_returns_permanents_and_the_emblem_removes_the_hand_limit(cards):
    from app.rules import hand_size
    from app.rules.plan import Plan
    from tests.test_rules_conditionals import settle

    s = build(cards, "Wrenn and Seven", "Llanowar Elves", "Lightning Bolt")
    elves, bolt = to_gy(s, "Llanowar Elves"), to_gy(s, "Lightning Bolt")
    wrenn = put(s, "Wrenn and Seven")
    act(s, "p1", type="counter", card_ids=[wrenn.id], kind="loyalty", delta=8)
    act(s, "p1", type="activate_ability", card_id=wrenn.id, ability=3)  # −8
    settle(s)
    assert s.state.cards[elves.id].zone == "p1:hand" and s.state.cards[bolt.id].zone == "p1:graveyard"  # (permanent cards only)
    assert hand_size.maximum(Plan(s.state, "p1", s.cards, None), "p1") is None
    assert hand_size.maximum(Plan(s.state, "p1", s.cards, None), "p2") == 7
    replay_matches(s)
    replay_matches(reloaded(s))


def test_skrelvs_hive_gives_lifelink_to_toxic_creatures_once_an_opponent_is_corrupted(cards):
    from tests.test_rules_attachments import ch

    s = build(cards, "Skrelv's Hive")
    put(s, "Skrelv's Hive")
    plain = token(s, "p1", "Mite")  # (a creature without toxic gets nothing)
    act(s, "p1", type="create_token", player="p1", token={"name": "Toxic Mite", "type_line": "Token Artifact Creature — Phyrexian Mite",
                                                         "power": "1", "toughness": "1", "text": "Toxic 1"})
    toxic = named(s, "Toxic Mite")
    assert "lifelink" not in ch(s, toxic).keywords  # (no opponent has three poison counters yet)
    act(s, "p1", type="resource", player="p2", key="poison", delta=3)
    assert "lifelink" in ch(s, toxic).keywords and "lifelink" not in ch(s, plain).keywords
    replay_matches(s)
    replay_matches(reloaded(s))

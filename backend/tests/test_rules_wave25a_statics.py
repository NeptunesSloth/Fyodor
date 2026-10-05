"""Wave 25A: conditions of "as long as" statics: the source's own state and types, the object it is attached to (CR 604.2, 611.3a, 613.1d, 303.4).

* "~ gets +2/+0 as long as it isn't attacking or blocking." (Intrepid Ace), "As long as this creature is enchanted or equipped, it can attack as
  though it didn't have defender." (Novice Knight), "As long as this permanent is a creature, it has prowess." (Triton Wavebreaker), "~ has
  defender as long as it's a Wall." (Mistform Wall);
* "Enchanted creature gets +2/+2 as long as it's a Human. Otherwise, it can't attack or block." (Bonds of Faith), "As long as you control
  enchanted creature, it gets +2/+2. Otherwise, it can't block." (Mishra's Domination), "As long as enchanted creature isn't legendary, it
  doesn't untap during its controller's untap step." (Stunning Strike).
Every statement is a continuous effect that applies at any moment its condition is true (611.3a): it follows the object as it changes.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.cards.importer import build_database
from app.config import Settings
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_attachments import ch
from tests.test_rules_effects import mana, token
from tests.test_rules_wave9b_exile_permission import answer, build, find, put, roundtrip

EXTRA = [
    card('Intrepid Ace', set_code='tst', number='M01', mana_cost='{R}', cmc=1.0, type_line='Creature — Human Pilot', oracle_text="This creature gets +2/+0 as long as it isn't attacking or blocking.", power='2', toughness='1', colors=['R'], color_identity=['R'], keywords=[], layout='normal'),  # noqa: E501
    card('Bonds of Faith', set_code='tst', number='M02', mana_cost='{1}{W}', cmc=2.0, type_line='Enchantment — Aura', oracle_text="Enchant creature\nEnchanted creature gets +2/+2 as long as it's a Human. Otherwise, it can't attack or block.", colors=['W'], color_identity=['W'], keywords=['Enchant'], layout='normal'),  # noqa: E501
    card("Mishra's Domination", set_code='tst', number='M03', mana_cost='{1}{R}', cmc=2.0, type_line='Enchantment — Aura', oracle_text="Enchant creature\nAs long as you control enchanted creature, it gets +2/+2. Otherwise, it can't block.", colors=['R'], color_identity=['R'], keywords=['Enchant'], layout='normal'),  # noqa: E501
    card('Stunning Strike', set_code='tst', number='M04', mana_cost='{2}{U}', cmc=3.0, type_line='Enchantment — Aura', oracle_text="Flash\nEnchant creature\nWhen this Aura enters, tap enchanted creature and remove it from combat.\nAs long as enchanted creature isn't legendary, it doesn't untap during its controller's untap step.", colors=['U'], color_identity=['U'], keywords=['Enchant', 'Flash'], layout='normal'),  # noqa: E501
    card('Triton Wavebreaker', set_code='tst', number='M05', mana_cost='{U}', cmc=1.0, type_line='Enchantment Creature — Merfolk Wizard', oracle_text="Bestow {1}{U} (If you cast this card for its bestow cost, it's an Aura spell with enchant creature. It becomes a creature again if it's not attached.)\nAs long as this permanent is a creature, it has prowess. (Whenever you cast a noncreature spell, this creature gets +1/+1 until end of turn.)\nEnchanted creature gets +1/+1 and has prowess.", power='1', toughness='1', colors=['U'], color_identity=['U'], keywords=['Bestow'], layout='normal'),  # noqa: E501
    card('Mistform Wall', set_code='tst', number='M06', mana_cost='{2}{U}', cmc=3.0, type_line='Creature — Illusion Wall', oracle_text="This creature has defender as long as it's a Wall.\n{1}: This creature becomes the creature type of your choice until end of turn.", power='1', toughness='4', colors=['U'], color_identity=['U'], keywords=[], layout='normal'),  # noqa: E501
    card('Novice Knight', set_code='tst', number='M07', mana_cost='{W}', cmc=1.0, type_line='Creature — Human Knight', oracle_text="Defender (This creature can't attack.)\nAs long as this creature is enchanted or equipped, it can attack as though it didn't have defender.", power='2', toughness='3', colors=['W'], color_identity=['W'], keywords=['Defender'], layout='normal'),  # noqa: E501
    card('Elite Vanguard', set_code='tst', number='M08', mana_cost='{W}', cmc=1.0, type_line='Creature — Human Soldier', power='2', toughness='1', colors=['W'], color_identity=['W'], keywords=[], layout='normal'),  # noqa: E501
    card('Isamaru, Hound of Konda', set_code='tst', number='M09', mana_cost='{W}', cmc=1.0, type_line='Legendary Creature — Dog', power='2', toughness='2', colors=['W'], color_identity=['W'], keywords=[], layout='normal'),  # noqa: E501
    card('Yuffie, Materia Hunter', set_code='tst', number='M10', mana_cost='{2}{R}', cmc=3.0, type_line='Legendary Creature — Human Ninja', oracle_text='Ninjutsu {1}{R} ({1}{R}, Return an unblocked attacker you control to hand: Put this card onto the battlefield from your hand tapped and attacking.)\nWhen Yuffie enters, gain control of target noncreature artifact for as long as you control Yuffie. Then you may attach an Equipment you control to Yuffie.', power='3', toughness='3', colors=['R'], color_identity=['R'], keywords=['Ninjutsu'], layout='normal'),  # noqa: E501
    card('Short Sword', set_code='tst', number='M11', mana_cost='{1}', cmc=1.0, type_line='Artifact — Equipment', oracle_text='Equipped creature gets +1/+1.\nEquip {1} ({1}: Attach to target creature you control. Equip only as a sorcery.)', colors=[], color_identity=[], keywords=['Equip'], layout='normal'),  # noqa: E501
    card('Nahiri, Heir of the Ancients', set_code='tst', number='M12', mana_cost='{2}{R}{W}', cmc=4.0, type_line='Legendary Planeswalker — Nahiri', oracle_text='+1: Create a 1/1 white Kor Warrior creature token. You may attach an Equipment you control to it.\n−2: Look at the top six cards of your library. You may reveal a Warrior or Equipment card from among them and put it into your hand. Put the rest on the bottom of your library in a random order.\n−3: Nahiri deals damage to target creature or planeswalker equal to twice the number of Equipment you control.', colors=['R', 'W'], color_identity=['R', 'W'], keywords=[], layout='normal'),  # noqa: E501
    card('Cairn Wanderer', set_code='tst', number='M13', mana_cost='{4}{B}', cmc=5.0, type_line='Creature — Shapeshifter', oracle_text='Changeling (This card is every creature type.)\nAs long as a creature card with flying is in a graveyard, this creature has flying. The same is true for fear, first strike, double strike, deathtouch, haste, landwalk, lifelink, protection, reach, trample, shroud, and vigilance.', power='4', toughness='4', colors=['B'], color_identity=['B'], keywords=['Changeling'], layout='normal'),  # noqa: E501
    card('Urborg Scavengers', set_code='tst', number='M14', mana_cost='{2}{B}', cmc=3.0, type_line='Creature — Spirit', oracle_text='Whenever this creature enters or attacks, exile target card from a graveyard. Put a +1/+1 counter on this creature.\nThis creature has flying as long as a card exiled with it has flying. The same is true for first strike, double strike, deathtouch, haste, hexproof, indestructible, lifelink, menace, reach, trample, and vigilance.', power='2', toughness='2', colors=['B'], color_identity=['B'], keywords=[], layout='normal'),  # noqa: E501
    card('Wind Drake', set_code='tst', number='M15', mana_cost='{2}{U}', cmc=3.0, type_line='Creature — Drake', oracle_text='Flying', power='2', toughness='2', colors=['U'], color_identity=['U'], keywords=['Flying'], layout='normal'),  # noqa: E501
    card('Vampire Interloper', set_code='tst', number='M16', mana_cost='{1}{B}', cmc=2.0, type_line='Creature — Vampire Scout', oracle_text="Flying\nThis creature can't block.", power='2', toughness='1', colors=['B'], color_identity=['B'], keywords=['Flying'], layout='normal'),  # noqa: E501
    card('Keen-Eyed Curator', set_code='tst', number='M17', mana_cost='{G}{G}', cmc=2.0, type_line='Creature — Raccoon Scout', oracle_text='As long as there are four or more card types among cards exiled with this creature, it gets +4/+4 and has trample.\n{1}: Exile target card from a graveyard.', power='3', toughness='3', colors=['G'], color_identity=['G'], keywords=[], layout='normal'),  # noqa: E501
    card('Lightning Bolt', set_code='tst', number='M18', mana_cost='{R}', cmc=1.0, type_line='Instant', oracle_text='Lightning Bolt deals 3 damage to any target.', colors=['R'], color_identity=['R'], keywords=[], layout='normal'),  # noqa: E501
    card('Hooded Horror', set_code='tst', number='M19', mana_cost='{4}{B}', cmc=5.0, type_line='Creature — Horror', oracle_text="This creature can't be blocked as long as defending player controls the most creatures or is tied for the most.", power='4', toughness='4', colors=['B'], color_identity=['B'], keywords=[], layout='normal'),  # noqa: E501
    card('Nightkin Ambusher', set_code='tst', number='M20', mana_cost='{2}{U}{B}', cmc=4.0, type_line='Creature — Mutant Warrior', oracle_text="Ward {2} (Whenever this creature becomes the target of a spell or ability an opponent controls, counter it unless that player pays {2}.)\nWhen this creature enters, target player gets four rad counters.\nThis creature can't be blocked as long as defending player has a rad counter.", power='4', toughness='4', colors=['B', 'U'], color_identity=['B', 'U'], keywords=['Ward'], layout='normal'),  # noqa: E501
    card('Arctic Foxes', set_code='tst', number='M21', mana_cost='{1}{W}', cmc=2.0, type_line='Creature — Fox', oracle_text="This creature can't be blocked by creatures with power 2 or greater as long as defending player controls a snow land.", power='1', toughness='1', colors=['W'], color_identity=['W'], keywords=[], layout='normal'),  # noqa: E501
    card('Snow-Covered Island', set_code='tst', number='M22', cmc=0.0, type_line='Basic Snow Land — Island', oracle_text='({T}: Add {U}.)', colors=[], color_identity=['U'], keywords=[], layout='normal'),  # noqa: E501
    card('Test Bear', set_code='tst', number='M99', mana_cost='{2}{G}', cmc=3.0, type_line='Creature — Bear', power='2', toughness='2', colors=['G'], color_identity=['G'], oracle_text=''),
]


@pytest.fixture()
def card_db(settings: Settings) -> Path:
    settings.ensure_dirs()
    build_database(fixture_cards() + EXTRA, settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.mark.parametrize("name", ["Intrepid Ace", "Bonds of Faith", "Mishra's Domination", "Stunning Strike", "Triton Wavebreaker", "Mistform Wall",
                                  "Novice Knight"])
def test_coverage_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def enchant(s, aura, target):
    put(s, aura, "hand")
    mana(s, W=2, U=3, R=2)
    act(s, "p1", type="cast_spell", card_id=find(s, aura).id, targets=[target.id])
    answer(s)
    assert find(s, aura).zone == "p1:battlefield" and find(s, aura).attached_to == target.id


def test_it_isnt_attacking_or_blocking_follows_the_combat_state(cards):
    s = build(cards, p1=("Intrepid Ace",))
    ace = put(s, "Intrepid Ace", "battlefield")
    assert ch(s, ace).pt == (4, 1)  # 2/1 and +2/+0
    s.state.cards[ace.id].attacking = "p2"
    assert ch(s, ace).pt == (2, 1)
    s.state.cards[ace.id].attacking = None
    s.state.cards[ace.id].blocking = "x"
    assert ch(s, ace).pt == (2, 1)
    s.state.cards[ace.id].blocking = None
    roundtrip(s)


def test_a_creature_with_defender_attacks_only_while_enchanted_or_equipped(cards):
    s = build(cards, p1=("Novice Knight", "Bonds of Faith"))
    knight = put(s, "Novice Knight", "battlefield")
    assert "attack_despite_defender" not in ch(s, knight).imposed
    enchant(s, "Bonds of Faith", find(s, "Novice Knight"))
    assert "attack_despite_defender" in ch(s, find(s, "Novice Knight")).imposed
    roundtrip(s)


def test_a_wall_has_defender(cards):
    s = build(cards, p1=("Mistform Wall",))
    wall = put(s, "Mistform Wall", "battlefield")
    assert "defender" in ch(s, wall).keywords  # (Illusion Wall)
    roundtrip(s)


def test_bonds_of_faith_gives_a_human_the_bonus_and_anyone_else_cant_attack_or_block(cards):
    s = build(cards, p1=("Bonds of Faith", "Elite Vanguard", "Test Bear"))
    human = put(s, "Elite Vanguard", "battlefield")
    bear = put(s, "Test Bear", "battlefield")
    enchant(s, "Bonds of Faith", human)
    assert ch(s, human).pt == (4, 3) and "cant_attack_or_block" not in ch(s, human).imposed
    act(s, "p1", type="move", card_ids=[find(s, "Bonds of Faith").id], to={"zone": "hand"})
    enchant(s, "Bonds of Faith", bear)
    assert ch(s, bear).pt == (2, 2) and "cant_attack_or_block" in ch(s, bear).imposed  # Otherwise: it can't attack or block (611.3a)
    roundtrip(s)


def test_mishras_domination_depends_on_who_controls_the_enchanted_creature(cards):
    s = build(cards, p1=("Mishra's Domination", "Test Bear"))
    mine = put(s, "Test Bear", "battlefield")
    theirs = token(s, "p2", "Theirs", "2/2")
    enchant(s, "Mishra's Domination", mine)
    assert ch(s, mine).pt == (4, 4) and "cant_block" not in ch(s, mine).imposed
    act(s, "p1", type="move", card_ids=[find(s, "Mishra's Domination").id], to={"zone": "hand"})
    enchant(s, "Mishra's Domination", theirs)
    assert ch(s, theirs).pt == (2, 2) and "cant_block" in ch(s, theirs).imposed  # Otherwise, it can't block
    roundtrip(s)


def test_stunning_strike_holds_down_only_a_nonlegendary_creature(cards):
    s = build(cards, p1=("Stunning Strike", "Test Bear"))
    bear = put(s, "Test Bear", "battlefield")
    enchant(s, "Stunning Strike", bear)
    assert "doesnt_untap" in ch(s, bear).imposed
    roundtrip(s)


def test_stunning_strike_does_not_hold_down_a_legendary_creature(cards):
    s = build(cards, p1=("Stunning Strike", "Isamaru, Hound of Konda"))
    isamaru = put(s, "Isamaru, Hound of Konda", "battlefield")
    enchant(s, "Stunning Strike", isamaru)
    assert "doesnt_untap" not in ch(s, isamaru).imposed  # 611.3a: it applies only while the creature isn't legendary
    roundtrip(s)


def test_a_bestowed_triton_wavebreaker_is_no_creature_so_it_has_no_prowess_but_gives_it(cards):
    s = build(cards, p1=("Triton Wavebreaker", "Test Bear"))
    wave = put(s, "Triton Wavebreaker", "battlefield")
    assert "prowess" in ch(s, wave).keywords  # as long as this permanent is a creature
    put(s, "Triton Wavebreaker", "exile")
    wave = put(s, "Triton Wavebreaker", "hand")
    bear = put(s, "Test Bear", "battlefield")
    mana(s, U=2)
    act(s, "p1", type="cast_spell", card_id=wave.id, alt_cost=f"{wave.id}:0", targets=[bear.id])  # bestow {1}{U}
    answer(s)
    assert find(s, "Triton Wavebreaker").attached_to == bear.id
    assert not ch(s, find(s, "Triton Wavebreaker")).is_creature and "prowess" not in ch(s, find(s, "Triton Wavebreaker")).keywords
    assert "prowess" in ch(s, bear).keywords and ch(s, bear).pt == (3, 3)  # "Enchanted creature gets +1/+1 and has prowess"
    roundtrip(s)


def test_yuffie_takes_an_artifact_and_may_attach_an_equipment_to_herself(cards):
    s = build(cards, p1=("Yuffie, Materia Hunter", "Short Sword"), p2=("Short Sword",))
    mine = put(s, "Short Sword", "battlefield")
    theirs = put(s, "Short Sword", "battlefield", pid="p2")
    yuffie = put(s, "Yuffie, Materia Hunter", "hand")
    mana(s, R=1, C=2)
    act(s, "p1", type="cast_spell", card_id=yuffie.id)
    for _ in range(14):
        d = s.state.rules.decision
        if d is None:
            if not s.state.zones.get("stack"):
                break
            act(s, s.state.rules.priority, type="pass_priority")
            continue
        if d.kind == "choose_cards" and (d.resume or {}).get("step") == "attach_choose":
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[mine.id])  # "attach an Equipment you control to Yuffie"
        else:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options if o.id in ("yes", theirs.id)][:1] or [d.options[0].id])
    assert find(s, "Short Sword").controller == "p1"
    assert s.state.cards[mine.id].attached_to == find(s, "Yuffie, Materia Hunter").id  # 701.3a
    assert s.state.cards[theirs.id].controller == "p1" and s.state.cards[theirs.id].attached_to is None
    roundtrip(s)


def test_a_creature_with_a_keyword_in_a_graveyard_gives_it_to_cairn_wanderer(cards):
    s = build(cards, p1=("Cairn Wanderer", "Wind Drake"), p2=("Test Bear",))
    wanderer = put(s, "Cairn Wanderer", "battlefield")
    assert "flying" not in ch(s, wanderer).keywords
    put(s, "Test Bear", "graveyard", pid="p2")  # (no flying: nothing)
    assert "flying" not in ch(s, wanderer).keywords
    drake = put(s, "Wind Drake", "graveyard")  # a creature card with flying is in a graveyard
    assert "flying" in ch(s, wanderer).keywords
    put(s, "Wind Drake", "exile")  # and no longer: 611.3a
    assert "flying" not in ch(s, wanderer).keywords and drake.id
    roundtrip(s)


def test_urborg_scavengers_has_the_keywords_of_the_cards_it_exiled(cards):
    s = build(cards, p1=("Urborg Scavengers",), p2=("Wind Drake",))
    put(s, "Wind Drake", "graveyard", pid="p2")
    scav = put(s, "Urborg Scavengers", "hand")
    mana(s, B=1, C=2)
    act(s, "p1", type="cast_spell", card_id=scav.id)
    for _ in range(12):
        d = s.state.rules.decision
        if d is None:
            if not s.state.zones.get("stack"):
                break
            act(s, s.state.rules.priority, type="pass_priority")
            continue
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options if o.card_id == find(s, "Wind Drake", "p2").id][:1]
            or [d.options[0].id])
    assert find(s, "Wind Drake", "p2").zone == "p2:exile"
    assert "flying" in ch(s, find(s, "Urborg Scavengers")).keywords  # "a card exiled with it has flying"
    assert ch(s, find(s, "Urborg Scavengers")).pt == (3, 3)  # +1/+1 counter
    roundtrip(s)


def test_keen_eyed_curator_counts_the_card_types_among_the_cards_it_exiled(cards):
    s = build(cards, p1=("Keen-Eyed Curator",), p2=("Test Bear", "Lightning Bolt", "Short Sword"))
    curator = put(s, "Keen-Eyed Curator", "battlefield")
    for name in ("Test Bear", "Island", "Lightning Bolt", "Short Sword"):  # a creature, a land, an instant, an artifact
        put(s, name, "graveyard", pid="p2")
    for i, name in enumerate(("Test Bear", "Island", "Lightning Bolt", "Short Sword")):
        mana(s, C=1)
        act(s, "p1", type="activate_ability", card_id=curator.id, ability=1, targets=[find(s, name, "p2").id])  # {1}: Exile target card from a graveyard
        answer(s)
        want = (3, 3) if i < 3 else (7, 7)  # 611.3a: "four or more card types among cards exiled with this creature": +4/+4 and trample
        assert ch(s, find(s, "Keen-Eyed Curator")).pt == want
    assert "trample" in ch(s, find(s, "Keen-Eyed Curator")).keywords
    roundtrip(s)


def block_problem_of(s, attacker_card, blocker_card):
    from app.rules.combat import block_problem
    from app.rules.plan import Plan

    p = Plan(s.state, "p1", s.cards, None)
    return block_problem(s.state, s.state.cards[blocker_card.id], p.ch(s.state.cards[blocker_card.id]), s.state.cards[attacker_card.id],
                         p.ch(s.state.cards[attacker_card.id]), s.cards)


def test_defender_counts_and_counters_decide_whether_a_creature_can_be_blocked(cards):
    s = build(cards, p1=("Nightkin Ambusher", "Hooded Horror"))
    ambusher = put(s, "Nightkin Ambusher", "battlefield")
    horror = put(s, "Hooded Horror", "battlefield")
    blocker = token(s, "p2", "Blocker", "2/2")
    assert block_problem_of(s, ambusher, blocker) is None  # the defending player has no rad counter
    act(s, "p1", type="resource", player="p2", key="rad", delta=4)  # (When it enters: target player gets four rad counters)
    assert "can't be blocked" in block_problem_of(s, ambusher, blocker)
    # Hooded Horror: Alice controls 2 creatures, Bob 1: he doesn't control the most, so it can be blocked; with 2 each (tied) it can't
    assert block_problem_of(s, horror, blocker) is None
    token(s, "p2", "Second", "1/1")
    assert "can't be blocked" in block_problem_of(s, horror, blocker)
    roundtrip(s)


def test_a_snow_land_stops_creatures_with_power_two_or_more_from_blocking_arctic_foxes(cards):
    s = build(cards, p1=("Arctic Foxes",), p2=("Snow-Covered Island",))
    foxes = put(s, "Arctic Foxes", "battlefield")
    big, small = token(s, "p2", "Big", "2/2"), token(s, "p2", "Small", "1/1")
    assert block_problem_of(s, foxes, big) is None  # no snow land yet
    put(s, "Snow-Covered Island", "battlefield", pid="p2")
    assert "can't be blocked by" in block_problem_of(s, foxes, big)
    assert block_problem_of(s, foxes, small) is None  # power 1: it still can block
    roundtrip(s)

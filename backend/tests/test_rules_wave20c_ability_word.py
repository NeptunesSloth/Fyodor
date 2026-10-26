"""Wave 20C: ability-word wordings (CR 2026-09-25).

* Eerie — "Whenever an enchantment you control enters and whenever you fully unlock a Room, …" (603.2: it triggers on each of the
  two events; 709.5i: a player "fully unlocks" a Room when it has one of the two unlocked designations and gets the other, or when it
  has neither and gains both). Casting a Room enters an enchantment (the first trigger) and unlocks one door (no full unlock);
  unlocking the second door later is the second trigger. Real Oracle text, a replay and a save/load round trip each."""

from __future__ import annotations

import pytest

from app.cards.importer import build_database
from app.game.session import GameSession
from app.rules import coverage
from app.rules.mana_units import visible_pool
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_attachments import ch
from tests.test_rules_conditionals import build, on_field, settle, to_hand, token_of
from tests.test_rules_effects import mana, replay_matches
from tests.test_rules_wave18g_rooms import EXTRA as ROOMS

DAZZLING = "Dazzling Theater // Prop Room"

EXTRA = [
    *ROOMS,
    card('Gremlin Tamer', set_code='tst', number='Y0', mana_cost='{1}{R}', cmc=2.0, type_line='Creature — Human Scout',
         oracle_text='Eerie — Whenever an enchantment you control enters and whenever you fully unlock a Room, create a 1/1 red Gremlin creature token.',
         power='2', toughness='1', colors=['R'], color_identity=['R'], keywords=[]),
    card('Balemurk Leech', set_code='tst', number='Y1', mana_cost='{1}{B}', cmc=2.0, type_line='Creature — Leech',
         oracle_text='Eerie — Whenever an enchantment you control enters and whenever you fully unlock a Room, each opponent loses 1 life.',
         power='2', toughness='2', colors=['B'], color_identity=['B'], keywords=[]),
    card('Erratic Apparition', set_code='tst', number='Y2', mana_cost='{1}{U}', cmc=2.0, type_line='Creature — Spirit',
         oracle_text='Flying, vigilance\nEerie — Whenever an enchantment you control enters and whenever you fully unlock a Room, this creature gets +1/+1 until end of turn.',
         power='1', toughness='3', colors=['U'], color_identity=['U'], keywords=['Flying', 'Vigilance']),
]
EXTRA += [
    card('Omnath, Locus of Creation', set_code='tst', number='Y3', mana_cost='{R}{G}{W}{U}', cmc=4.0, type_line='Legendary Creature — Elemental',
         oracle_text="When Omnath enters, draw a card.\nLandfall — Whenever a land you control enters, you gain 4 life if this is the first time this ability has resolved this turn. If it's the second time, add {R}{G}{W}{U}. If it's the third time, Omnath deals 4 damage to each opponent and each planeswalker you don't control.",
         power='4', toughness='4', colors=['G', 'R', 'U', 'W'], color_identity=['G', 'R', 'U', 'W'], keywords=['Landfall']),
]
EXTRA.append(card('Azusa, Lost but Seeking', set_code='tst', number='Y4', mana_cost='{2}{G}', cmc=3.0, type_line='Legendary Creature — Human Monk',
                  oracle_text='You may play two additional lands on each of your turns.', power='1', toughness='2', colors=['G'],
                  color_identity=['G'], keywords=[]))
EXTRA += [
    card("Valgavoth's Onslaught", set_code='tst', number='Y5', mana_cost='{X}{X}{G}', cmc=1.0, type_line='Sorcery',
         oracle_text="Manifest dread X times, then put X +1/+1 counters on each of those creatures. (To manifest dread, look at the top two cards of your library, then put one onto the battlefield face down as a 2/2 creature and the other into your graveyard. Turn it face up any time for its mana cost if it's a creature card.)",
         power=None, toughness=None, colors=['G'], color_identity=['G'], keywords=['Manifest', 'Manifest dread']),
    card('Gorbag of Minas Morgul', set_code='tst', number='Y6', mana_cost='{1}{B}', cmc=2.0, type_line='Legendary Creature — Orc Soldier',
         oracle_text='Whenever a Goblin or Orc you control deals combat damage to a player, you may sacrifice it. When you do, choose one —\n• Draw a card.\n• Create a Treasure token. (It\'s an artifact with "{T}, Sacrifice this token: Add one mana of any color.")',
         power='2', toughness='2', colors=['B'], color_identity=['B'], keywords=['Treasure']),
    card('Kefnet the Mindful', set_code='tst', number='Y7', mana_cost='{2}{U}', cmc=3.0, type_line='Legendary Creature — God',
         oracle_text="Flying, indestructible\nKefnet can't attack or block unless you have seven or more cards in hand.\n{3}{U}: Draw a card, then you may return a land you control to its owner's hand.",
         power='5', toughness='5', colors=['U'], color_identity=['U'], keywords=['Flying', 'Indestructible']),
    card('Vile Manifestation', set_code='tst', number='Y8', mana_cost='{1}{B}', cmc=2.0, type_line='Creature — Horror',
         oracle_text='This creature gets +1/+0 for each card with cycling in your graveyard.\nCycling {2} ({2}, Discard this card: Draw a card.)',
         power='0', toughness='4', colors=['B'], color_identity=['B'], keywords=['Cycling']),
    card('Shed Weakness', set_code='tst', number='Y9', mana_cost='{G}', cmc=1.0, type_line='Instant',
         oracle_text='Target creature gets +2/+2 until end of turn. You may remove a -1/-1 counter from it.',
         power=None, toughness=None, colors=['G'], color_identity=['G'], keywords=[]),
    card('Cori-Steel Cutter', set_code='tst', number='YA', mana_cost='{1}{R}', cmc=2.0, type_line='Artifact — Equipment',
         oracle_text='Equipped creature gets +1/+1 and has trample and haste.\nFlurry — Whenever you cast your second spell each turn, create a 1/1 white Monk creature token with prowess. You may attach this Equipment to it. (Whenever you cast a noncreature spell, the token gets +1/+1 until end of turn.)\nEquip {1}{R}',
         power=None, toughness=None, colors=['R'], color_identity=['R'], keywords=['Flurry', 'Equip']),
]
EXTRA.append(card('Repentant Vampire', set_code='tst', number='YB', mana_cost='{3}{B}{B}', cmc=5.0, type_line='Creature — Vampire',
                  oracle_text='Flying\nWhenever a creature dealt damage by this creature this turn dies, put a +1/+1 counter on this creature.\nThreshold — As long as there are seven or more cards in your graveyard, this creature is white and has "{T}: Destroy target black creature."',
                  power='3', toughness='3', colors=['B'], color_identity=['B'], keywords=['Flying', 'Threshold']))
FULL = ['Repentant Vampire', 'Gremlin Tamer', 'Balemurk Leech', 'Erratic Apparition', 'Omnath, Locus of Creation', 'Azusa, Lost but Seeking',
        "Valgavoth's Onslaught", 'Gorbag of Minas Morgul', 'Kefnet the Mindful', 'Vile Manifestation', 'Shed Weakness', 'Cori-Steel Cutter']


@pytest.fixture()
def card_db(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def reloaded(s):
    return GameSession(s.history.rebuild(), cards=s.cards)


def gremlins(s):
    return [c for c in s.state.cards.values() if c.name == "Gremlin" and c.zone.endswith(":battlefield")]


@pytest.mark.parametrize("name", FULL)
def test_coverage_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def test_eerie_triggers_when_the_room_enters_and_again_when_it_is_fully_unlocked(cards):
    s = build(cards, "Gremlin Tamer", DAZZLING)
    on_field(s, "Gremlin Tamer")
    room = to_hand(s, DAZZLING)
    mana(s, "p1", W=1, C=3)
    act(s, "p1", type="cast_spell", card_id=room.id, face=0)
    settle(s)
    assert len(gremlins(s)) == 1  # the enchantment entered; one door is unlocked, nothing is fully unlocked yet
    mana(s, "p1", W=1, C=2)
    act(s, "p1", type="unlock_door", card_id=room.id, door=2)
    settle(s)
    assert len(gremlins(s)) == 2  # 709.5i: the second designation fully unlocks it
    replay_matches(s)
    replay_matches(reloaded(s))


def answer_all(s, prefs=(), limit=60):
    """Resolve the stack; a decision gets the first of ``prefs`` on offer, else the first option."""
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None:
            ids = [o.id for o in d.options]
            chosen = next((p for p in prefs if p in ids), None)
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[chosen] if chosen else ids[: max(1, d.min_choices)])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return
    raise AssertionError("never settled")


def mine(s, name, zone="battlefield", pid="p1"):
    return [c for c in s.state.cards.values() if c.name == name and c.zone == f"{pid}:{zone}"]


def test_valgavoths_onslaught_puts_the_counters_on_each_of_the_manifested_creatures(cards):
    """"Manifest dread X times, then put X +1/+1 counters on each of those creatures.": every one of the X face-down creatures."""
    s = build(cards, "Valgavoth's Onslaught")
    spell = to_hand(s, "Valgavoth's Onslaught")
    mana(s, "p1", G=1, C=4)
    act(s, "p1", type="cast_spell", card_id=spell.id, x_value=2)
    answer_all(s)
    down = [c for c in s.state.cards.values() if c.zone == "p1:battlefield" and c.face_down]
    assert len(down) == 2
    assert [s.state.cards[c.id].counters.get("+1/+1") for c in down] == [2, 2]
    replay_matches(s)
    replay_matches(reloaded(s))


@pytest.mark.parametrize("sacrifice", ["yes", "no"])
def test_gorbag_sacrifices_the_creature_and_then_the_reflexive_trigger_draws(cards, sacrifice):
    s = build(cards, "Gorbag of Minas Morgul")
    gorbag = on_field(s, "Gorbag of Minas Morgul")
    s.state.rules.controlled_since[gorbag.id].turn = 0
    from tests.test_rules_conditionals import attack
    from tests.test_rules_wave4l_attached import to_attack

    to_attack(s)
    hand = len(s.state.zones["p1:hand"])
    attack(s, (gorbag, "p2"))
    for _ in range(60):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
        elif d is not None:
            ids = [o.id for o in d.options]
            wanted = next((a for a in (sacrifice, "mode:0") if a in ids), None)
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[wanted] if wanted else ids[: max(1, d.min_choices)])
        elif s.state.turn.phase == "main2" and not s.state.zones.get("stack"):
            break
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    assert (s.state.cards[gorbag.id].zone == "p1:graveyard") is (sacrifice == "yes")
    assert len(s.state.zones["p1:hand"]) == hand + (1 if sacrifice == "yes" else 0)  # "Draw a card" is the first mode
    replay_matches(s)
    replay_matches(reloaded(s))


@pytest.mark.parametrize("answer", ["yes", "no"])
def test_kefnet_only_the_land_return_is_optional(cards, answer):
    s = build(cards, "Kefnet the Mindful")
    kefnet = on_field(s, "Kefnet the Mindful")
    land = on_field(s, "Forest")
    s.state.rules.controlled_since[kefnet.id].turn = 0
    hand = len(s.state.zones["p1:hand"])
    mana(s, "p1", U=1, C=3)
    act(s, "p1", type="activate_ability", card_id=kefnet.id, ability=2)
    answer_all(s, prefs=(answer, land.id))
    assert len(s.state.zones["p1:hand"]) == hand + (2 if answer == "yes" else 1)  # the draw happens either way
    assert (s.state.cards[land.id].zone == "p1:hand") is (answer == "yes")
    replay_matches(s)
    replay_matches(reloaded(s))


def test_vile_manifestation_counts_the_cards_with_cycling_in_its_owners_graveyard(cards):
    from app.rules.plan import Plan

    s = build(cards, "Vile Manifestation", "Vile Manifestation", "Llanowar Elves")
    copies = [c for c in s.state.cards.values() if c.name == "Vile Manifestation" and c.owner == "p1"]
    horror = copies[0]
    act(s, "p1", type="move", card_ids=[horror.id], to={"player": "p1", "zone": "battlefield"})
    assert Plan(s.state, "p1", s.cards, None).ch(s.state.cards[horror.id]).pt == (0, 4)
    elves = next(c for c in s.state.cards.values() if c.name == "Llanowar Elves" and c.owner == "p1")
    act(s, "p1", type="move", card_ids=[elves.id], to={"player": "p1", "zone": "graveyard"})  # (no cycling: no power)
    assert Plan(s.state, "p1", s.cards, None).ch(s.state.cards[horror.id]).pt == (0, 4)
    act(s, "p1", type="move", card_ids=[copies[1].id], to={"player": "p1", "zone": "graveyard"})  # (it has cycling: +1/+0)
    assert Plan(s.state, "p1", s.cards, None).ch(s.state.cards[horror.id]).pt == (1, 4)


def test_repentant_vampire_is_white_with_threshold(cards):
    """"As long as there are seven or more cards in your graveyard, this creature is white and has "{T}: Destroy target black
    creature."": its own color (layer 5) under a condition about the graveyard only."""
    s = build(cards, "Repentant Vampire")
    vamp = on_field(s, "Repentant Vampire")
    assert ch(s, vamp).colors == frozenset({"B"})
    forests = [c for c in s.state.cards.values() if c.name == "Forest" and c.owner == "p1" and c.zone == "p1:library"][:7]
    for i, f in enumerate(forests):
        act(s, "p1", type="move", card_ids=[f.id], to={"player": "p1", "zone": "graveyard"})
        assert (ch(s, vamp).colors == frozenset({"W"})) is (i == 6)  # (the seventh card)
    replay_matches(s)
    replay_matches(reloaded(s))


def test_shed_weakness_only_the_counter_removal_is_optional(cards):
    s = build(cards, "Shed Weakness")
    bear = token_of(s, "p1", "Bear", "Token Creature — Bear", "2/2")
    act(s, "p1", type="counter", card_ids=[bear.id], kind="-1/-1", delta=1)
    spell = to_hand(s, "Shed Weakness")
    mana(s, "p1", G=1)
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=[bear.id])
    answer_all(s, prefs=("yes",))
    assert s.state.cards[bear.id].counters.get("-1/-1", 0) == 0
    assert ch(s, bear).pt == (4, 4)  # +2/+2 until end of turn (the -1/-1 counter was removed)
    replay_matches(s)
    replay_matches(reloaded(s))


def test_cori_steel_cutter_attaches_to_the_monk_it_made(cards):
    s = build(cards, "Cori-Steel Cutter", "Lightning Bolt", "Lightning Bolt")
    cutter = on_field(s, "Cori-Steel Cutter")
    bolts = [c for c in s.state.cards.values() if c.name == "Lightning Bolt" and c.owner == "p1"]
    for b in bolts:
        act(s, "p1", type="move", card_ids=[b.id], to={"zone": "hand"})
    for b in bolts:
        mana(s, "p1", R=1)
        act(s, "p1", type="cast_spell", card_id=b.id, targets=["p2"])
        answer_all(s, prefs=("yes",))
    monks = mine(s, "Monk")
    assert len(monks) == 1  # only the second spell of the turn
    assert s.state.cards[cutter.id].attached_to == monks[0].id
    replay_matches(s)
    replay_matches(reloaded(s))


def test_omnath_reads_which_time_the_landfall_ability_resolves(cards):
    """"If it's the second time, …": the second resolution this turn, the third the next (history: resolution n)."""
    s = build(cards, "Omnath, Locus of Creation", "Azusa, Lost but Seeking")
    on_field(s, "Omnath, Locus of Creation")
    on_field(s, "Azusa, Lost but Seeking")
    settle(s)  # (Omnath's own enter trigger draws a card)
    lands = [c for c in s.state.cards.values() if c.name == "Forest" and c.owner == "p1" and c.zone == "p1:library"][:3]
    for land in lands:
        act(s, "p1", type="move", card_ids=[land.id], to={"player": "p1", "zone": "hand"})
    life = s.state.players["p1"].life
    opp = s.state.players["p2"].life
    act(s, "p1", type="play_land", card_id=lands[0].id)
    settle(s)
    assert s.state.players["p1"].life == life + 4 and s.state.players["p2"].life == opp  # the first time: gain 4 life
    act(s, "p1", type="play_land", card_id=lands[1].id)
    settle(s)
    assert s.state.players["p1"].life == life + 4  # the second time: the mana, no life
    assert {k: v for k, v in visible_pool(s.state, "p1").items() if v} == {"R": 1, "G": 1, "W": 1, "U": 1}
    act(s, "p1", type="play_land", card_id=lands[2].id)
    settle(s)
    assert s.state.players["p2"].life == opp - 4 and s.state.players["p1"].life == life + 4  # the third time: 4 damage
    replay_matches(s)
    replay_matches(reloaded(s))


def test_a_room_that_entered_without_doors_is_fully_unlocked_by_its_second_door_only(cards):
    s = build(cards, "Balemurk Leech", DAZZLING)
    on_field(s, "Balemurk Leech")
    room = on_field(s, DAZZLING)  # (not cast: it enters with neither door unlocked)
    settle(s)
    life = s.state.players["p2"].life
    mana(s, "p1", W=1, C=3)
    act(s, "p1", type="unlock_door", card_id=room.id, door=1)
    settle(s)
    assert s.state.players["p2"].life == life  # the first door: not fully unlocked
    mana(s, "p1", W=1, C=2)
    act(s, "p1", type="unlock_door", card_id=room.id, door=2)
    settle(s)
    assert s.state.players["p2"].life == life - 1  # the second door
    replay_matches(s)
    replay_matches(reloaded(s))

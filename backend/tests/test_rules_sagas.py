"""Sagas (CR 714, 702.155 read ahead; app/rules/sagas.py) and triggers on the events of the enchanted or
equipped permanent (603.10a, 400.7f; app/rules/triggers.py), researched against CR 2026-09-25.

* A Saga enters with a lore counter (714.3a) — through the counter choke point, so Doubling Season
  doubles it (614.16: the "enters with" replacement is an effect) — and gets one more as its
  controller's precombat main phase begins (714.3c, 505.4: a turn-based action, not an effect).
* "{rN}—" triggers when the lore counters go from below N to at least N (714.2b); "I, II —" is one
  ability per numeral (714.2c); proliferate puts lore counters too.
* 714.4: sacrificed once its lore counters reach its final chapter number and no chapter ability of
  it is waiting or on the stack.
* Read ahead (702.155): the number of lore counters is chosen as it enters; skipped chapters don't
  trigger that turn.
* "When enchanted creature dies" / "Whenever equipped creature dies" look back in time at what was
  attached (603.10a); "return this card" finds the Aura in its owner's graveyard (400.7f).

Every scenario checks that replaying the recorded history reproduces the table; some reload the game
from its saved history in the middle.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.cards.importer import build_database
from app.config import Settings
from app.game.session import GameSession
from app.rules import coverage, scripts
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_attachments import build, ch, mana, named, to_hand, token
from tests.test_rules_conditionals import attack, settle, through_combat, until
from tests.test_rules_effects import replay_matches
from tests.test_rules_scripts import ch as characteristics

REMINDER = "(As this Saga enters and after your draw step, add a lore counter. Sacrifice after III.)\n"
READ_AHEAD = ("Read ahead (Choose a chapter and start with that many lore counters. Add one after your draw step. "
              "Skipped chapters don't trigger. Sacrifice after III.)\n")

# Real Commander-legal cards, Oracle text as in the card database (reminder text included).
EXTRA = [
    card("History of Benalia", set_code="tst", number="S1", layout="saga", mana_cost="{1}{W}{W}", cmc=3.0,
         type_line="Enchantment — Saga", colors=["W"], color_identity=["W"],
         oracle_text=REMINDER + "I, II — Create a 2/2 white Knight creature token with vigilance.\n"
                                "III — Knights you control get +2/+1 until end of turn."),
    card("The Eldest Reborn", set_code="tst", number="S2", layout="saga", mana_cost="{4}{B}", cmc=5.0,
         type_line="Enchantment — Saga", colors=["B"], color_identity=["B"],
         oracle_text=REMINDER + "I — Each opponent sacrifices a creature or planeswalker of their choice.\n"
                                "II — Each opponent discards a card.\n"
                                "III — Put target creature or planeswalker card from a graveyard onto the battlefield "
                                "under your control."),
    card("The Weatherseed Treaty", set_code="tst", number="S3", layout="saga", mana_cost="{2}{G}", cmc=3.0,
         type_line="Enchantment — Saga", colors=["G"], color_identity=["G"], keywords=["Read Ahead", "Domain"],
         oracle_text=READ_AHEAD + "I — Search your library for a basic land card, put it onto the battlefield tapped, "
                                  "then shuffle.\nII — Create a 1/1 green Saproling creature token.\n"
                                  "III — Domain — Target creature you control gets +X/+X and gains trample until end of "
                                  "turn, where X is the number of basic land types among lands you control."),
    card("Elspeth Conquers Death", set_code="tst", number="S4", layout="saga", mana_cost="{3}{W}{W}", cmc=5.0,
         type_line="Enchantment — Saga", colors=["W"], color_identity=["W"],
         oracle_text=REMINDER + "I — Exile target permanent an opponent controls with mana value 3 or greater.\n"
                                "II — Noncreature spells your opponents cast cost {2} more to cast until your next turn.\n"
                                "III — Return target creature or planeswalker card from your graveyard to the battlefield. "
                                "Put a +1/+1 counter or a loyalty counter on it."),
    card("Fable of the Mirror-Breaker // Reflection of Kiki-Jiki", set_code="tst", number="S5", layout="transform",
         mana_cost="{2}{R}", cmc=3.0, type_line="Enchantment — Saga // Enchantment Creature — Goblin Shaman",
         colors=["R"], color_identity=["R"], image_uris=None,
         card_faces=[
             {"object": "card_face", "name": "Fable of the Mirror-Breaker", "mana_cost": "{2}{R}",
              "type_line": "Enchantment — Saga", "colors": ["R"],
              "oracle_text": "(As this Saga enters and after your draw step, add a lore counter.)\n"
                             "I — Create a 2/2 red Goblin Shaman creature token with \"Whenever this token attacks, "
                             "create a Treasure token.\"\nII — You may discard up to two cards. If you do, draw that many "
                             "cards.\nIII — Exile this Saga, then return it to the battlefield transformed under your control."},
             {"object": "card_face", "name": "Reflection of Kiki-Jiki", "mana_cost": "",
              "type_line": "Enchantment Creature — Goblin Shaman", "colors": ["R"], "power": "2", "toughness": "2",
              "oracle_text": "{1}, {T}: Create a token that's a copy of another target nonlegendary creature you control, "
                             "except it has haste. Sacrifice it at the beginning of the next end step."},
         ]),
    card("Doubling Season", set_code="tst", number="S6", mana_cost="{4}{G}", cmc=5.0, type_line="Enchantment",
         colors=["G"], color_identity=["G"],
         oracle_text="If an effect would create one or more tokens under your control, it creates twice that many of those "
                     "tokens instead.\nIf an effect would put one or more counters on a permanent you control, it puts "
                     "twice that many of those counters on that permanent instead."),
    card("Cankerbloom", set_code="tst", number="S7", mana_cost="{1}{G}", cmc=2.0, type_line="Creature — Phyrexian Fungus",
         oracle_text="{1}, Sacrifice this creature: Choose one —\n• Destroy target artifact.\n• Destroy target enchantment.\n"
                     "• Proliferate. (Choose any number of permanents and/or players, then give each another counter of each "
                     "kind already there.)",
         power="3", toughness="2", colors=["G"], color_identity=["G"]),
    # -- triggers on the events of the enchanted / equipped permanent --
    card("Skullclamp", set_code="tst", number="A1", mana_cost="{1}", cmc=1.0, type_line="Artifact — Equipment",
         oracle_text="Equipped creature gets +1/-1.\nWhenever equipped creature dies, draw two cards.\nEquip {1}"),
    card("Angelic Destiny", set_code="tst", number="A2", mana_cost="{2}{W}{W}", cmc=4.0, type_line="Enchantment — Aura",
         colors=["W"], color_identity=["W"],
         oracle_text="Enchant creature\nEnchanted creature gets +4/+4, has flying and first strike, and is an Angel in "
                     "addition to its other types.\nWhen enchanted creature dies, return this card to its owner's hand."),
    card("Demonic Vigor", set_code="tst", number="A3", mana_cost="{B}", cmc=1.0, type_line="Enchantment — Aura",
         colors=["B"], color_identity=["B"],
         oracle_text="Enchant creature\nEnchanted creature gets +1/+1.\n"
                     "When enchanted creature dies, return that card to its owner's hand."),
    card("Sword of Fire and Ice", set_code="tst", number="A4", mana_cost="{3}", cmc=3.0, type_line="Artifact — Equipment",
         oracle_text="Equipped creature gets +2/+2 and has protection from red and from blue.\nWhenever equipped creature "
                     "deals combat damage to a player, this Equipment deals 2 damage to any target and you draw a card.\n"
                     "Equip {2}"),
    card("Bear Umbra", set_code="tst", number="A5", mana_cost="{2}{G}{G}", cmc=4.0, type_line="Enchantment — Aura",
         colors=["G"], color_identity=["G"],
         oracle_text="Enchant creature\nEnchanted creature gets +2/+2 and has \"Whenever this creature attacks, untap all "
                     "lands you control.\"\nUmbra armor (If enchanted creature would be destroyed, instead remove all "
                     "damage from it and destroy this Aura.)"),
    card("Stab Wound", set_code="tst", number="A6", mana_cost="{2}{B}", cmc=3.0, type_line="Enchantment — Aura",
         colors=["B"], color_identity=["B"],
         oracle_text="Enchant creature\nEnchanted creature gets -2/-2.\nAt the beginning of the upkeep of enchanted "
                     "creature's controller, that player loses 2 life."),
    card("Unstable Mutation", set_code="tst", number="A7", mana_cost="{U}", cmc=1.0, type_line="Enchantment — Aura",
         colors=["U"], color_identity=["U"],
         oracle_text="Enchant creature\nEnchanted creature gets +3/+3.\nAt the beginning of the upkeep of enchanted "
                     "creature's controller, put a -1/-1 counter on that creature."),
    card("Curse of the Bloody Tome", set_code="tst", number="A8", mana_cost="{2}{U}", cmc=3.0,
         type_line="Enchantment — Aura Curse", colors=["U"], color_identity=["U"],
         oracle_text="Enchant player\nAt the beginning of enchanted player's upkeep, that player mills two cards."),
    card("Private Research", set_code="tst", number="A9", mana_cost="{U}", cmc=1.0, type_line="Enchantment — Aura",
         colors=["U"], color_identity=["U"],
         oracle_text="Enchant creature\nAt the beginning of your upkeep, you may put a page counter on this Aura.\n"
                     "When enchanted creature dies, draw a card for each page counter on this Aura."),
]


@pytest.fixture()
def card_db(settings: Settings) -> Path:
    settings.ensure_dirs()
    build_database(fixture_cards() + EXTRA, settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def rules(s):
    return s.state.rules


def reloaded(s):
    """The table as a fresh session rebuilt from the saved history (a save and a load)."""
    return GameSession(s.history.rebuild(), cards=s.cards)


def lore(s, c):
    return s.state.cards[c.id].counters.get("lore", 0)


def zone_of(s, c):
    return s.state.cards[c.id].zone


def knights(s):
    return [c for c in s.state.cards.values() if c.name == "Knight" and c.zone == "p1:battlefield"]


def cast(s, name, pid="p1", targets=None, **m):
    c = to_hand(s, name)
    mana(s, **m)
    act(s, pid, type="cast_spell", card_id=c.id, **({"targets": targets} if targets else {}))
    return c


def respond_on(s):
    for pid in s.state.players:
        act(s, pid, type="set_prefs", response="on")  # (everyone stops at each object on the stack)


def to_attack(s, number=3):
    """On to Alice's declaration of attackers in turn ``number`` (her creatures made in turn 1 can attack)."""
    until(s, lambda s: s.state.turn.number == number and rules(s).decision is not None
          and rules(s).decision.kind == "declare_attackers")


def main_phase(s, number):
    """Play on (nobody attacks, the first options answer anything asked) to turn ``number``'s first main
    phase, as it begins: its turn-based actions done, triggered abilities waiting to resolve."""
    until(s, lambda s: s.state.turn.number == number and s.state.turn.phase == "main1")


# -- definitions -------------------------------------------------------------------------------------
def test_chapter_lines_are_triggered_abilities():
    benalia = characteristics("History of Benalia", "Enchantment — Saga",
                              REMINDER + "I, II — Create a 2/2 white Knight creature token with vigilance.\n"
                              "III — Knights you control get +2/+1 until end of turn.")
    defs = scripts.definitions(benalia)
    assert [d["trigger"] for d in defs.values()] == ["chapter", "chapter"]
    assert [d["chapters"] for d in defs.values()] == [[1, 2], [3]]
    assert coverage.of_characteristics(benalia).level == "FULL"


def test_a_chapter_line_not_read_stays_manual():
    """A chapter III this engine doesn't read ("transformed" is read since wave 11A, so: a made-up wording) is refused: PARTIAL."""
    fable = characteristics("Fable of the Mirror-Breaker", "Enchantment — Saga",
                            "I — Create a 2/2 red Goblin Shaman creature token.\n"
                            "III — Exile this Saga, then return it to the battlefield transformed and attached to a creature.")
    defs = scripts.definitions(fable)
    assert list(defs) == [0] and coverage.of_characteristics(fable).level == "PARTIAL"
    # (a chapter line on a card that isn't a Saga is no chapter ability)
    plain = characteristics("Test Not A Saga", "Enchantment", "I — Draw a card.")
    assert scripts.definitions(plain) == {}


# -- lore counters, chapters, the sacrifice ------------------------------------------------------------
def test_history_of_benalia_through_its_three_chapters(cards):
    """714.3a: it enters with a lore counter (chapter I); 714.3c: one more as Alice's precombat main
    phase begins (chapter II, then III); 714.4: sacrificed once chapter III has left the stack."""
    s = build(cards, "History of Benalia")
    respond_on(s)
    saga = cast(s, "History of Benalia", W=2, C=1)
    settle(s)
    assert zone_of(s, saga) == "p1:battlefield" and lore(s, saga) == 1 and len(knights(s)) == 1
    main_phase(s, 3)  # (Bob's turn 2 adds nothing: only its controller's precombat main phase does)
    assert lore(s, saga) == 2 and rules(s).stack  # chapter II waits on the stack
    s = reloaded(s)  # (a save and a load with the chapter ability on the stack)
    settle(s)
    assert len(knights(s)) == 2 and zone_of(s, saga) == "p1:battlefield"
    main_phase(s, 5)
    assert lore(s, saga) == 3
    entry = next(iter(rules(s).stack.values()))
    assert entry.event is not None and entry.event.kind == "chapter" and entry.event.amount == 3
    assert zone_of(s, saga) == "p1:battlefield"  # 714.4: not while its chapter ability is on the stack
    settle(s)
    assert [ch(s, k).pt for k in knights(s)] == [(4, 3), (4, 3)]  # III: Knights you control get +2/+1
    assert zone_of(s, saga) == "p1:graveyard"  # then sacrificed (714.4)
    replay_matches(s)


def test_doubling_season_doubles_the_entering_lore_counter_not_the_turn_based_one(cards):
    """614.16: entering with a lore counter is an effect (two counters: I and II both trigger, 714.2c);
    the precombat main phase counter is a turn-based action (714.3c): one counter, chapter III."""
    s = build(cards, "History of Benalia", "Doubling Season")
    respond_on(s)
    act(s, "p1", type="move", card_ids=[named(s, "Doubling Season").id], to={"player": "p1", "zone": "battlefield"})
    saga = cast(s, "History of Benalia", W=2, C=1)
    settle(s)
    assert lore(s, saga) == 2
    assert len(knights(s)) == 4  # chapters I and II, each a Knight, doubled by Doubling Season
    main_phase(s, 3)
    assert lore(s, saga) == 3  # (not 4)
    settle(s)
    assert zone_of(s, saga) == "p1:graveyard" and {ch(s, k).pt for k in knights(s)} == {(4, 3)}
    replay_matches(s)


def test_the_eldest_reborn_chapter_one_makes_each_opponent_sacrifice(cards):
    s = build(cards, "The Eldest Reborn")
    bear = token(s, "p2", "Bear")
    saga = cast(s, "The Eldest Reborn", B=1, C=4)
    settle(s)
    assert lore(s, saga) == 1 and bear.id not in s.state.cards  # (Bob's only creature: sacrificed, gone)
    replay_matches(s)


def test_proliferate_puts_a_lore_counter_and_its_chapter_triggers(cards):
    """122.6 / 701.34: proliferate puts counters, so the next chapter triggers (714.2b)."""
    s = build(cards, "History of Benalia", "Cankerbloom")
    saga = cast(s, "History of Benalia", W=2, C=1)
    settle(s)
    bloom = named(s, "Cankerbloom")
    act(s, "p1", type="move", card_ids=[bloom.id], to={"player": "p1", "zone": "battlefield"})
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=bloom.id, ability=0)
    d = rules(s).decision
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["2:0"])  # Proliferate
    for _ in range(10):
        d = rules(s).decision
        if d is not None and saga.id in [o.id for o in d.options]:
            act(s, "p1", type="choose", decision_id=d.id, option_ids=[saga.id])
            break
        act(s, rules(s).priority, type="pass_priority")
    settle(s)
    assert lore(s, saga) == 2 and len(knights(s)) == 2
    replay_matches(s)


def test_a_partly_automated_saga_is_not_sacrificed_by_the_engine(cards):
    """Elspeth Conquers Death: chapter II isn't automated, so the table — not the engine — decides
    when it goes (never a guess): the lore counters still come, chapter I still triggers."""
    s = build(cards, "Elspeth Conquers Death")
    saga = cast(s, "Elspeth Conquers Death", W=2, C=3)
    settle(s)
    assert lore(s, saga) == 1
    act(s, "p1", type="counter", card_ids=[saga.id], kind="lore", delta=2)  # (by hand: three lore counters)
    settle(s)
    assert lore(s, saga) == 3 and zone_of(s, saga) == "p1:battlefield"
    replay_matches(s)


# -- read ahead (702.155) -------------------------------------------------------------------------------
def read_ahead(s, n):
    """Pass priority until the read-ahead number is asked (as the Saga spell resolves), then choose ``n``."""
    for _ in range(10):
        d = rules(s).decision
        if d is not None:
            assert [o.id for o in d.options] == ["1", "2", "3"] and "chapter number" in d.prompt
            act(s, "p1", type="choose", decision_id=d.id, option_ids=[n])
            return
        act(s, rules(s).priority, type="pass_priority")
    raise AssertionError("never asked")


def test_read_ahead_chooses_the_chapter_and_skips_the_earlier_ones(cards):
    """The Weatherseed Treaty with read ahead 2: it enters with two lore counters (714.3b); chapter I
    doesn't trigger that turn (702.155a), chapter II does (a Saproling)."""
    s = build(cards, "The Weatherseed Treaty")
    saga = cast(s, "The Weatherseed Treaty", G=1, C=2)
    read_ahead(s, "2")
    settle(s)
    assert lore(s, saga) == 2
    assert [c.name for c in s.state.cards.values() if c.zone == "p1:battlefield" and c.is_token] == ["Saproling"]
    assert not [e for e in s.state.cards.values() if e.zone == "p1:battlefield" and e.name == "Forest"]  # (no chapter I)
    replay_matches(s)


def test_read_ahead_three_triggers_only_the_final_chapter_then_is_sacrificed(cards):
    s = build(cards, "The Weatherseed Treaty")
    bear = token(s, "p1", "Bear")
    forest = next(c for c in s.state.cards.values() if c.name == "Forest" and c.owner == "p1")
    act(s, "p1", type="move", card_ids=[forest.id], to={"player": "p1", "zone": "battlefield"})
    saga = cast(s, "The Weatherseed Treaty", G=1, C=2)
    read_ahead(s, "3")
    settle(s)  # (III's target: the first option, the Bear)
    assert zone_of(s, saga) == "p1:graveyard"  # (III resolved: sacrificed, 714.4)
    assert ch(s, bear).pt == (3, 3)  # +X/+X, X = 1 (Forests: one basic land type)
    assert not [c for c in s.state.cards.values() if c.name == "Saproling"]
    replay_matches(s)


# -- the enchanted / equipped permanent's events ----------------------------------------------------------
def test_skullclamp_draws_when_the_equipped_creature_dies(cards):
    """603.10a: "Whenever equipped creature dies" looks back: the Equipment was attached as it died."""
    s = build(cards, "Skullclamp")
    clamp = named(s, "Skullclamp")
    act(s, "p1", type="move", card_ids=[clamp.id], to={"player": "p1", "zone": "battlefield"})
    elf = token(s, "p1", "Elf", "1/1")
    hand = len(s.state.zones["p1:hand"])
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=clamp.id, ability=2, targets=[elf.id])  # Equip {1}
    settle(s)  # (+1/-1: the Elf dies, state-based action; the trigger draws two)
    assert elf.id not in s.state.cards and zone_of(s, clamp) == "p1:battlefield"
    assert len(s.state.zones["p1:hand"]) == hand + 2
    replay_matches(s)


def test_an_equipped_creature_leaving_but_not_dying_does_not_trigger_dies(cards):
    s = build(cards, "Skullclamp", "Swords to Plowshares")
    clamp = named(s, "Skullclamp")
    act(s, "p1", type="move", card_ids=[clamp.id], to={"player": "p1", "zone": "battlefield"})
    bear = token(s, "p1", "Bear", "2/3")
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=clamp.id, ability=2, targets=[bear.id])
    settle(s)
    assert s.state.cards[clamp.id].attached_to == bear.id
    hand = len(s.state.zones["p1:hand"])
    cast(s, "Swords to Plowshares", W=1, targets=[bear.id])  # exiled: it doesn't die
    settle(s)
    assert bear.id not in s.state.cards and len(s.state.zones["p1:hand"]) == hand  # (no draw)
    replay_matches(s)


def test_angelic_destiny_returns_to_hand_when_the_creature_dies(cards):
    """400.7f: the trigger finds the Aura's new object in its owner's graveyard (put there by the
    state-based action for not being attached, 704.5m)."""
    s = build(cards, "Angelic Destiny", "Murder")
    respond_on(s)  # (the trigger resolves in a later intent: the Aura is bound as it triggers)
    bear = token(s, "p1", "Bear")
    aura = cast(s, "Angelic Destiny", targets=[bear.id], W=2, C=2)
    settle(s)
    assert s.state.cards[aura.id].attached_to == bear.id
    cast(s, "Murder", targets=[bear.id], B=2, C=1)
    settle(s)
    assert zone_of(s, aura) == "p1:hand"
    replay_matches(s)


def test_angelic_destiny_that_left_the_graveyard_is_a_new_object(cards):
    """400.7: once the Aura card leaves the graveyard before the ability resolves, it isn't found."""
    s = build(cards, "Angelic Destiny", "Murder")
    respond_on(s)
    bear = token(s, "p1", "Bear")
    aura = cast(s, "Angelic Destiny", targets=[bear.id], W=2, C=2)
    settle(s)
    cast(s, "Murder", targets=[bear.id], B=2, C=1)
    for _ in range(10):  # (Murder resolves; the Aura's trigger waits on the stack)
        if any(e.source_card == aura.id for e in rules(s).stack.values()):
            break
        act(s, rules(s).priority, type="pass_priority")
    assert zone_of(s, aura) == "p1:graveyard"
    act(s, "p1", type="move", card_ids=[aura.id], to={"player": "p1", "zone": "exile"})
    act(s, "p1", type="move", card_ids=[aura.id], to={"player": "p1", "zone": "graveyard"})  # (a new object, 400.7)
    settle(s)
    assert zone_of(s, aura) == "p1:graveyard"
    replay_matches(s)


def test_angelic_destiny_returns_when_both_die_at_once(cards):
    """400.7f: the Aura put into the graveyard at the same time as the creature (Wrath of God) is found too."""
    s = build(cards, "Angelic Destiny", "Wrath of God")
    respond_on(s)
    bear = token(s, "p1", "Bear")
    aura = cast(s, "Angelic Destiny", targets=[bear.id], W=2, C=2)
    settle(s)
    cast(s, "Wrath of God", W=2, C=2)
    settle(s)
    assert zone_of(s, aura) == "p1:hand"
    replay_matches(s)


def test_demonic_vigor_returns_the_creature_card(cards):
    s = build(cards, "Demonic Vigor", "Grizzly Bears", "Murder")
    bears = cast(s, "Grizzly Bears", G=1, C=1)
    settle(s)
    aura = cast(s, "Demonic Vigor", targets=[bears.id], B=1)
    settle(s)
    cast(s, "Murder", targets=[bears.id], B=2, C=1)
    settle(s)
    assert zone_of(s, bears) == "p1:hand" and zone_of(s, aura) == "p1:graveyard"
    replay_matches(s)


def test_sword_of_fire_and_ice_combat_damage_trigger(cards):
    s = build(cards, "Sword of Fire and Ice")
    sword = named(s, "Sword of Fire and Ice")
    act(s, "p1", type="move", card_ids=[sword.id], to={"player": "p1", "zone": "battlefield"})
    bear = token(s, "p1", "Bear")
    act(s, "p1", type="attach", card_ids=[sword.id], to=bear.id)
    to_attack(s)
    hand = len(s.state.zones["p1:hand"])
    life = s.state.players["p2"].life
    attack(s, (bear, "p2"))
    through_combat(s)  # (the Sword's 2 damage: the first target offered)
    assert s.state.players["p2"].life <= life - 2  # (2 combat damage at least)
    assert len(s.state.zones["p1:hand"]) == hand + 1  # "and you draw a card"
    replay_matches(s)


def test_bear_umbra_untaps_lands_when_the_creature_attacks(cards):
    s = build(cards, "Bear Umbra")
    bear = token(s, "p1", "Bear")
    aura = cast(s, "Bear Umbra", targets=[bear.id], G=2, C=2)
    settle(s)
    forest = next(c for c in s.state.cards.values() if c.name == "Forest" and c.owner == "p1")
    act(s, "p1", type="move", card_ids=[forest.id], to={"player": "p1", "zone": "battlefield"})
    assert s.state.cards[aura.id].attached_to == bear.id
    main_phase(s, 3)
    act(s, "p1", type="tap", card_ids=[forest.id], tapped=True)
    to_attack(s)
    attack(s, (bear, "p2"))
    settle(s)
    assert not s.state.cards[forest.id].tapped
    replay_matches(s)


def test_upkeep_of_enchanted_creatures_controller(cards):
    """Stab Wound on Bob's creature: at the beginning of Bob's upkeep (not Alice's), Bob loses 2 life;
    Unstable Mutation: a -1/-1 counter on that creature."""
    s = build(cards, "Stab Wound", "Unstable Mutation")
    ogre = token(s, "p2", "Ogre", "5/5")
    cast(s, "Stab Wound", targets=[ogre.id], B=1, C=2)
    settle(s)
    cast(s, "Unstable Mutation", targets=[ogre.id], U=1)
    settle(s)
    alice, bob = s.state.players["p1"].life, s.state.players["p2"].life
    main_phase(s, 2)
    assert s.state.players["p2"].life == bob - 2 and s.state.players["p1"].life == alice
    assert s.state.cards[ogre.id].counters.get("-1/-1") == 1
    s = reloaded(s)
    main_phase(s, 3)
    assert s.state.players["p2"].life == bob - 2  # (not on Alice's upkeep)
    replay_matches(s)


def test_enchanted_players_upkeep_that_player(cards):
    """Curse of the Bloody Tome on Bob: at the beginning of Bob's upkeep, Bob mills two cards."""
    s = build(cards, "Curse of the Bloody Tome")
    cast(s, "Curse of the Bloody Tome", targets=["p2"], U=1, C=2)
    settle(s)
    library = len(s.state.zones["p2:library"])
    main_phase(s, 2)
    assert len(s.state.zones["p2:graveyard"]) == 2 and len(s.state.zones["p2:library"]) == library - 1 - 2  # (a draw, two milled)
    replay_matches(s)


def test_this_auras_counters_are_read_as_it_last_existed(cards):
    """Private Research: the Aura is in the graveyard (704.5m) when the ability resolves; "each page
    counter on this Aura" reads it as it last existed on the battlefield (608.2h)."""
    s = build(cards, "Private Research", "Murder")
    bear = token(s, "p1", "Bear")
    aura = cast(s, "Private Research", targets=[bear.id], U=1)
    settle(s)
    act(s, "p1", type="counter", card_ids=[aura.id], kind="page", delta=2)  # (by hand: two page counters)
    hand = len(s.state.zones["p1:hand"])
    cast(s, "Murder", targets=[bear.id], B=2, C=1)
    settle(s)
    assert zone_of(s, aura) == "p1:graveyard" and len(s.state.zones["p1:hand"]) == hand + 2
    replay_matches(s)

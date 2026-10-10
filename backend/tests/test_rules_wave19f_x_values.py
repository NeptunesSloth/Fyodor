"""Wave 19F: X and "where X is" wordings (CR 2026-09-25).

* "where X is <value>" with a pronoun in the value ("that creature's power", "the milled card's mana value", "the exiled card's
  toughness", "that spell's mana value"): the pronoun is bound by what the ability did before (608.2h), as for "equal to".
* New counts: "the total number of cards in all players' hands", "the greatest power among A and B", "the total life lost by your
  opponents this turn", "the number of tokens you created this turn" / "permanents you've sacrificed this turn" (this turn's log).
* "Sacrifice another creature" (701.21a: one you control, not the source) and a sacrifice cost read as "that creature's power".
* "X target creatures …" as the subject of a sentence (601.2c), "target creature with power X or less" / "spell with mana value X".
* "Proliferate X times" / "it explores X times" / "Investigate X times": each time is a whole action (701.34a, 701.44a, 701.16a).
* "Monstrosity X" and the X of "When this creature becomes monstrous, …" (701.37c).
* "for each Dwarf, Equipment, and/or Vehicle you control", "draws two additional cards".

Real Oracle text; each scenario replays the history and survives a save/load round trip."""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.game.session import GameSession
from app.game.state import GameState
from app.rules import coverage
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_attachments import build, mana, named, to_hand, token
from tests.test_rules_effects import pass_until_stack_empty, replay_matches


def real(name, cost, cmc, types, text, pt=None, colors=()):
    extra = {"power": pt[0], "toughness": pt[1]} if pt else {}
    return card(name, set_code="tst", number=f"19F-{name[:7]}", mana_cost=cost, cmc=float(cmc), type_line=types, oracle_text=text,
                colors=list(colors), color_identity=list(colors), **extra)


EXTRA = [
    real("Realm Seekers", "{4}{G}{G}", 6, "Creature — Elf Scout",
         "This creature enters with X +1/+1 counters on it, where X is the total number of cards in all players' hands.\n"
         "{2}{G}, Remove a +1/+1 counter from this creature: Search your library for a land card, reveal it, put it into your hand, then shuffle.",
         ("0", "0"), "G"),
    real("Disciple of Bolas", "{3}{B}", 4, "Creature — Human Wizard",
         "When this creature enters, sacrifice another creature. You gain X life and draw X cards, where X is that creature's power.",
         ("2", "1"), "B"),
    real("Shadowheart, Dark Justiciar", "{3}{B}", 4, "Legendary Creature — Human Elf Cleric",
         "{1}{B}, {T}, Sacrifice another creature: Draw X cards, where X is that creature's power.\n"
         "Choose a Background (You can have a Background as a second commander.)", ("3", "4"), "B"),
    real("Spell Blast", "{X}{U}", 1, "Instant", "Counter target spell with mana value X. (For example, if that spell's mana cost is {3}{U}{U}, X is 5.)",
         None, "U"),
    real("Killing Glare", "{X}{B}", 1, "Instant", "Destroy target creature with power X or less.", None, "B"),
    real("Wave of Indifference", "{X}{R}", 1, "Sorcery", "X target creatures can't block this turn.", None, "R"),
    real("Jadelight Spelunker", "{X}{G}", 1, "Creature — Merfolk Scout",
         "When this creature enters, it explores X times. (To have it explore, reveal the top card of your library. Put that card into your "
         "hand if it's a land. Otherwise, put a +1/+1 counter on that creature, then put the card back or put it into your graveyard.)",
         ("1", "1"), "G"),
    real("Expansion Algorithm", "{X}{U}{U}", 2, "Sorcery",
         "Proliferate X times. (To proliferate, choose any number of permanents and/or players, then give each another counter of each kind "
         "already there.)", None, "U"),
    real("Hydra Broodmaster", "{4}{G}{G}", 6, "Creature — Hydra",
         "{X}{X}{G}: Monstrosity X. (If this creature isn't monstrous, put X +1/+1 counters on it and it becomes monstrous.)\n"
         "When this creature becomes monstrous, create X X/X green Hydra creature tokens.", ("7", "7"), "G"),
    real("Mindshrieker", "{1}{U}", 2, "Creature — Spirit Bird",
         "Flying\n{2}: Target player mills a card. This creature gets +X/+X until end of turn, where X is the milled card's mana value.",
         ("1", "1"), "U"),
    real("Scour the Desert", "{3}{W}{W}", 5, "Sorcery",
         "Exile target creature card from your graveyard. Create X 1/1 white Bird creature tokens with flying, where X is the exiled card's "
         "toughness.", None, "W"),
    real("Bearded Axe", "{2}{R}", 3, "Artifact — Equipment",
         "Equipped creature gets +1/+1 for each Dwarf, Equipment, and/or Vehicle you control.\nEquip {2}", None, "R"),
    real("Road Rage", "{R}", 1, "Instant",
         "Road Rage deals X damage to target creature or planeswalker, where X is 2 plus the number of Mounts and Vehicles you control.",
         None, "R"),
    real("Cryptborn Horror", "{1}{B/R}{B/R}", 3, "Creature — Horror",
         "Trample\nThis creature enters with X +1/+1 counters on it, where X is the total life lost by your opponents this turn.", ("0", "0"), "BR"),
    real("Curse of Obsession", "{4}{R}", 5, "Enchantment — Aura Curse",
         "Enchant player\nAt the beginning of enchanted player's draw step, that player draws two additional cards.\n"
         "At the beginning of enchanted player's end step, that player discards their hand.", None, "R"),
    real("Ambitious Dragonborn", "{3}{G}", 4, "Creature — Dragon Barbarian",
         "This creature enters with X +1/+1 counters on it, where X is the greatest power among creatures you control and creature cards in "
         "your graveyard.", ("0", "0"), "G"),
    real("Vitality Hunter", "{3}{W}", 4, "Creature — Nightmare",
         "Lifelink\n{X}{W}{W}: Monstrosity X. (If this creature isn't monstrous, put X +1/+1 counters on it and it becomes monstrous.)\n"
         "When this creature becomes monstrous, put a lifelink counter on each of up to X target creatures.", ("3", "4"), "W"),
    real("Aryel, Knight of Windgrace", "{2}{W}{B}", 4, "Legendary Creature — Human Knight",
         "Vigilance\n{2}{W}, {T}: Create a 2/2 white Knight creature token with vigilance.\n"
         "{B}, {T}, Tap X untapped Knights you control: Destroy target creature with power X or less.", ("4", "4"), "BW"),
    real("Ethereal Investigator", "{3}{U}", 4, "Creature — Spirit",
         "Flying\nWhen this creature enters, investigate X times, where X is the number of opponents you have.", ("2", "3"), "U"),
    real("Carnage Interpreter", "{1}{B/R}{B/R}", 3, "Creature — Devil Detective",
         "When this creature enters, discard your hand, then investigate four times.", ("3", "3"), "BR"),
    real("Korvold, Fae-Cursed King", "{2}{B}{R}{G}", 5, "Legendary Creature — Dragon Noble",
         "Flying\nWhenever Korvold enters or attacks, sacrifice another permanent.\n"
         "Whenever you sacrifice a permanent, put a +1/+1 counter on Korvold and draw a card.", ("4", "4"), "BGR"),
]
FULL = ["Realm Seekers", "Disciple of Bolas", "Shadowheart, Dark Justiciar", "Spell Blast", "Killing Glare", "Wave of Indifference",
        "Jadelight Spelunker", "Expansion Algorithm", "Hydra Broodmaster", "Mindshrieker", "Scour the Desert", "Bearded Axe", "Road Rage",
        "Cryptborn Horror", "Curse of Obsession", "Ambitious Dragonborn", "Vitality Hunter", "Aryel, Knight of Windgrace", "Ethereal Investigator", "Carnage Interpreter",
        "Korvold, Fae-Cursed King"]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def roundtrip(s):
    replay_matches(s)
    loaded = GameSession(GameState.model_validate_json(s.state.model_dump_json()), cards=s.cards)
    assert loaded.state.model_dump(mode="json") == s.state.model_dump(mode="json")


def hand(s, pid="p1"):
    return len(s.state.zones.get(f"{pid}:hand", []))


def chars(s, c):
    return Plan(s.state, "p1", s.cards, None).ch(s.state.cards[c.id])


def draw_to_hand(s, pid, n):
    ids = s.state.zones[f"{pid}:library"][:n]
    act(s, pid, type="move", card_ids=ids, to={"zone": "hand"})


def settle(s, pick=None, limit=40):
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None:
            ids = [pick] if pick and pick in [o.id for o in d.options] else [o.id for o in d.options][: max(1, d.min_choices)]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=ids)
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return
    raise AssertionError("the stack never emptied")


@pytest.mark.parametrize("name", FULL)
def test_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def test_enters_with_the_cards_in_all_hands(cards):
    s = build(cards, "Realm Seekers")
    seekers = to_hand(s, "Realm Seekers")
    draw_to_hand(s, "p1", 2)
    draw_to_hand(s, "p2", 3)
    mana(s, G=2, C=4)
    act(s, "p1", type="cast_spell", card_id=seekers.id)
    expected = hand(s, "p1") + hand(s, "p2")  # (read as it enters, 614.1c: the cast card has left the hand)
    pass_until_stack_empty(s)
    assert s.state.cards[seekers.id].counters.get("+1/+1") == expected and expected > 0
    roundtrip(s)


def test_sacrifice_another_creature_and_use_its_power(cards):
    s = build(cards, "Disciple of Bolas")
    victim = token(s, "p1", "Victim", "3/3")
    disciple = to_hand(s, "Disciple of Bolas")
    mana(s, B=1, C=3)
    life, cards_in_hand = s.state.players["p1"].life, hand(s) - 1
    act(s, "p1", type="cast_spell", card_id=disciple.id)
    settle(s)
    assert victim.id not in s.state.cards  # (another creature: never the Disciple itself, 701.21a)
    assert s.state.cards[disciple.id].zone == "p1:battlefield"
    assert s.state.players["p1"].life == life + 3 and hand(s) == cards_in_hand + 3  # its power as it last existed (608.2h)
    roundtrip(s)


def test_sacrifice_cost_then_that_creatures_power(cards):
    s = build(cards, "Shadowheart, Dark Justiciar")
    heart = named(s, "Shadowheart, Dark Justiciar")
    act(s, "p1", type="move", card_ids=[heart.id], to={"zone": "battlefield"})
    s.state.rules.controlled_since[heart.id].turn = 0
    victim = token(s, "p1", "Victim", "4/4")
    mana(s, B=2)
    before = hand(s)
    act(s, "p1", type="activate_ability", card_id=heart.id, ability=0)
    settle(s, pick=victim.id)
    assert victim.id not in s.state.cards and hand(s) == before + 4
    roundtrip(s)


def test_counter_target_spell_with_mana_value_x(cards):
    from app.game.factory import PlayerSetup, new_game
    from tests.game_helpers import deck, enable

    alice = deck(cards, "Krenko, Mob Boss", [(1, "Grizzly Bears"), (9, "Forest")])
    bob = deck(cards, "Atraxa, Praetors' Voice", [(1, "Spell Blast"), (9, "Island")])
    s = GameSession(enable(new_game([PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=bob)], shuffle=False)), cards=cards)
    act(s, "p1", type="pass_priority")  # → Alice's main phase
    bears = to_hand(s, "Grizzly Bears")
    blast = named(s, "Spell Blast")
    act(s, "p2", type="move", card_ids=[blast.id], to={"zone": "hand"})
    s.state.rules.prefs["p2"].response = "on"  # (the opponent stops with Bears on the stack)
    mana(s, G=1, C=1)
    act(s, "p1", type="cast_spell", card_id=bears.id)
    assert s.state.cards[bears.id].zone == "stack" and s.state.rules.priority == "p2"
    act(s, "p2", type="add_mana", player="p2", mana={"U": 1, "C": 2})
    with pytest.raises(ActionError):
        act(s, "p2", type="cast_spell", card_id=blast.id, targets=[bears.id], x_value=3)  # (its mana value is 2, not 3)
    act(s, "p2", type="cast_spell", card_id=blast.id, targets=[bears.id], x_value=2)
    pass_until_stack_empty(s)
    assert s.state.cards[bears.id].zone == "p1:graveyard"
    roundtrip(s)


def test_destroy_target_creature_with_power_x_or_less(cards):
    s = build(cards, "Killing Glare")
    small, big = token(s, "p2", "Small", "2/2"), token(s, "p2", "Big", "4/4")
    glare = to_hand(s, "Killing Glare")
    mana(s, B=1, C=3)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=glare.id, targets=[big.id], x_value=3)  # (power 4 is more than X)
    act(s, "p1", type="cast_spell", card_id=glare.id, targets=[small.id], x_value=3)
    pass_until_stack_empty(s)
    assert small.id not in s.state.cards and big.id in s.state.cards
    roundtrip(s)


def test_x_target_creatures_cant_block(cards):
    s = build(cards, "Wave of Indifference")
    a, b, c = (token(s, "p2", n, "1/1") for n in ("A", "B", "C"))
    wave = to_hand(s, "Wave of Indifference")
    mana(s, R=1, C=2)
    act(s, "p1", type="cast_spell", card_id=wave.id, x_value=2, targets=[a.id, b.id], target_counts=[2])
    pass_until_stack_empty(s)
    imposed = {i for e in s.state.rules.effects for i in e.affected if "cant_block" in e.imposes}
    plan = Plan(s.state, "p1", s.cards, None)
    assert imposed == {plan.oid(s.state.cards[a.id]), plan.oid(s.state.cards[b.id])}  # (exactly the two chosen, not C)
    roundtrip(s)


def test_it_explores_x_times(cards):
    s = build(cards, "Jadelight Spelunker")
    spelunker = to_hand(s, "Jadelight Spelunker")
    mana(s, G=1, C=2)
    act(s, "p1", type="cast_spell", card_id=spelunker.id, x_value=2)
    settle(s)
    # (the library is all Forests: each of the two explores revealed a land and put it into the hand, 701.44a)
    assert s.state.cards[spelunker.id].counters.get("+1/+1", 0) == 0
    assert sum(1 for c in s.state.cards.values() if c.name == "Forest" and c.zone == "p1:hand") >= 2
    roundtrip(s)


def test_proliferate_x_times(cards):
    s = build(cards, "Expansion Algorithm")
    bear = token(s, "p1", "Bear", "2/2")
    act(s, "p1", type="set_counter", card_id=bear.id, kind="+1/+1", value=1)
    algo = to_hand(s, "Expansion Algorithm")
    mana(s, U=2, C=3)
    act(s, "p1", type="cast_spell", card_id=algo.id, x_value=3)
    for _ in range(12):
        d = s.state.rules.decision
        if d is None:
            break
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[bear.id] if bear.id in [o.id for o in d.options] else [])
    pass_until_stack_empty(s)
    assert s.state.cards[bear.id].counters["+1/+1"] == 4  # (three proliferates, one after the other)
    roundtrip(s)


def test_investigate_x_times_is_x_investigations(cards):
    s = build(cards, "Ethereal Investigator")
    inv = to_hand(s, "Ethereal Investigator")
    mana(s, U=1, C=3)
    act(s, "p1", type="cast_spell", card_id=inv.id)
    pass_until_stack_empty(s)
    assert sum(1 for c in s.state.cards.values() if c.name == "Clue" and c.zone == "p1:battlefield") == 1  # (one opponent)
    roundtrip(s)


def test_monstrosity_x_and_the_trigger_reads_that_x(cards):
    s = build(cards, "Hydra Broodmaster")
    hydra = named(s, "Hydra Broodmaster")
    act(s, "p1", type="move", card_ids=[hydra.id], to={"zone": "battlefield"})
    mana(s, G=1, C=4)
    act(s, "p1", type="activate_ability", card_id=hydra.id, ability=0, x_value=2)
    pass_until_stack_empty(s)
    assert s.state.cards[hydra.id].counters.get("+1/+1") == 2
    tokens = [c for c in s.state.cards.values() if c.is_token and c.name == "Hydra" and c.zone == "p1:battlefield"]
    assert len(tokens) == 2 and all(chars(s, t).pt == (2, 2) for t in tokens)  # X creatures that are X/X (701.37c)
    roundtrip(s)


def test_the_milled_cards_mana_value(cards):
    s = build(cards, "Mindshrieker", "Grizzly Bears")
    bird = named(s, "Mindshrieker")
    act(s, "p1", type="move", card_ids=[bird.id], to={"zone": "battlefield"})
    top = s.state.zones["p1:library"][0]
    mana(s, C=2)
    act(s, "p1", type="activate_ability", card_id=bird.id, ability=1, targets=["p1"])
    pass_until_stack_empty(s)
    assert s.state.cards[top].zone == "p1:graveyard"
    assert chars(s, bird).pt == (3, 3)  # (the milled Grizzly Bears: mana value 2)
    roundtrip(s)


def test_the_exiled_cards_toughness(cards):
    s = build(cards, "Scour the Desert", "Grizzly Bears")
    bears = named(s, "Grizzly Bears")
    act(s, "p1", type="move", card_ids=[bears.id], to={"zone": "graveyard"})
    scour = to_hand(s, "Scour the Desert")
    mana(s, W=2, C=3)
    act(s, "p1", type="cast_spell", card_id=scour.id, targets=[bears.id])
    pass_until_stack_empty(s)
    birds = [c for c in s.state.cards.values() if c.is_token and c.name == "Bird" and c.zone == "p1:battlefield"]
    assert s.state.cards[bears.id].zone == "p1:exile" and len(birds) == 2  # toughness 2
    roundtrip(s)


def test_total_life_lost_by_opponents_this_turn(cards):
    s = build(cards, "Cryptborn Horror")
    horror = to_hand(s, "Cryptborn Horror")
    act(s, "p2", type="set_life", player="p2", value=37)  # (three life lost this turn, 120.3a)
    mana(s, B=3)
    act(s, "p1", type="cast_spell", card_id=horror.id)
    pass_until_stack_empty(s)
    assert s.state.cards[horror.id].zone == "p1:battlefield" and s.state.cards[horror.id].counters.get("+1/+1") == 3
    roundtrip(s)


def test_greatest_power_among_creatures_and_creature_cards_in_the_graveyard(cards):
    s = build(cards, "Ambitious Dragonborn", "Grizzly Bears")
    token(s, "p1", "Small", "1/1")
    bears = named(s, "Grizzly Bears")
    act(s, "p1", type="move", card_ids=[bears.id], to={"zone": "graveyard"})
    dragon = to_hand(s, "Ambitious Dragonborn")
    mana(s, G=1, C=3)
    act(s, "p1", type="cast_spell", card_id=dragon.id)
    pass_until_stack_empty(s)
    assert s.state.cards[dragon.id].counters.get("+1/+1") == 2  # (the Bears in the graveyard, not the 1/1 on the battlefield)
    roundtrip(s)


def test_monstrous_trigger_with_up_to_x_targets(cards):
    s = build(cards, "Vitality Hunter")
    hunter = named(s, "Vitality Hunter")
    act(s, "p1", type="move", card_ids=[hunter.id], to={"zone": "battlefield"})
    a, b, c = (token(s, "p1", n, "1/1") for n in ("A", "B", "C"))
    mana(s, W=2, C=2)
    act(s, "p1", type="activate_ability", card_id=hunter.id, ability=1, x_value=2)
    for _ in range(8):
        d = s.state.rules.decision
        if d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[a.id, b.id][: d.max_choices])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
    assert s.state.cards[hunter.id].counters.get("+1/+1") == 2
    got = {x.id for x in (a, b, c) if s.state.cards[x.id].counters.get("lifelink")}
    assert got == {a.id, b.id}  # (up to X = 2 creatures: 701.37c gives the trigger the X of the monstrosity)
    roundtrip(s)


def test_tap_x_knights_destroys_a_creature_with_power_x_or_less(cards):
    s = build(cards, "Aryel, Knight of Windgrace")
    aryel = named(s, "Aryel, Knight of Windgrace")
    act(s, "p1", type="move", card_ids=[aryel.id], to={"zone": "battlefield"})
    s.state.rules.controlled_since[aryel.id].turn = 0  # (there since before this turn began: 302.6)
    for i in range(2):
        act(s, "p1", type="create_token", player="p1", token={"name": f"Knight {i}", "type_line": "Token Creature — Knight",
                                                               "power": "2", "toughness": "2", "text": ""})
    for k in [c for c in s.state.cards.values() if c.name.startswith("Knight ")]:
        s.state.rules.controlled_since[k.id].turn = 0
    small, big = token(s, "p2", "Small", "2/2"), token(s, "p2", "Big", "4/4")
    mana(s, B=1)
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=aryel.id, ability=2, targets=[big.id], x_value=2)  # (power 4 is more than X)
    act(s, "p1", type="activate_ability", card_id=aryel.id, ability=2, targets=[small.id], x_value=2)
    settle(s)
    assert small.id not in s.state.cards and big.id in s.state.cards
    assert all(s.state.cards[k.id].tapped for k in s.state.cards.values() if k.name.startswith("Knight "))  # (X = 2 tapped)
    roundtrip(s)


def test_sacrifice_another_permanent(cards):
    s = build(cards, "Korvold, Fae-Cursed King")
    victim = token(s, "p1", "Victim", "1/1")
    korvold = to_hand(s, "Korvold, Fae-Cursed King")
    mana(s, B=1, R=1, G=1, C=2)
    before = hand(s)
    act(s, "p1", type="cast_spell", card_id=korvold.id)
    settle(s)
    assert victim.id not in s.state.cards and s.state.cards[korvold.id].zone == "p1:battlefield"  # (another permanent: not Korvold)
    assert s.state.cards[korvold.id].counters.get("+1/+1") == 1 and hand(s) == before  # (cast: -1, drawn: +1)
    roundtrip(s)


def test_draws_additional_cards_is_drawing_cards():
    from app.rules import scripts

    found = scripts.parse_effects("That player draws two additional cards.")
    assert found is not None and [(e["do"], e["n"]) for e in found[0]] == [("draw", 2)]

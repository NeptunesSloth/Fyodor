"""Review of wave 24B (speed, soulbond, dice, loops), real Oracle text (CR 2026-09-25); every scenario checks the replay and a save and a
load.

Regressions: speed is not a counter (702.179: proliferate, 701.34a, leaves it alone); the speed trigger's intervening "if" is checked again
as it resolves (603.4); a soulbond trigger whose creature left and came back pairs nothing (400.7, 702.95c). The rest are probes of the
wave's cards in multiplayer, after a save mid-decision and with two roll replacements."""

from __future__ import annotations

import pytest

from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_effects import replay_matches
from tests.test_rules_wave12a_counters_keywords import answer, rolls
from tests.wave9c_kit import build, card_named, check, life, mana, put, reloaded, to_hand

# (name, mana cost, type line, power, toughness, Oracle text): the real cards (2026-09-25 Oracle text)
REAL = [
    ('Nesting Bot', '{W}', 'Artifact Creature — Robot', '1', '1',
     'Start your engines! (If you have no speed, it starts at 1. It increases once on each of your turns when an opponent loses life. Max speed is 4.)\nWhen this creature dies, create a 1/1 colorless Servo artifact creature token.\nMax speed — This creature gets +1/+0.'),
    ('Deadeye Navigator', '{4}{U}{U}', 'Creature — Spirit', '5', '5',
     'Soulbond (You may pair this creature with another unpaired creature when either enters. They remain paired for as long as you control both of them.)\nAs long as Deadeye Navigator is paired with another creature, each of those creatures has "{1}{U}: Exile this creature, then return it to the battlefield under your control."'),
    ('Breathkeeper Seraph', '{4}{W}{W}', 'Creature — Angel', '4', '4',
     'Flying, soulbond (You may pair this creature with another unpaired creature when either enters. They remain paired for as long as you control both of them.)\nAs long as Breathkeeper Seraph is paired with another creature, each of those creatures has "When this creature dies, you may return it to the battlefield under its owner\'s control at the beginning of your next upkeep."'),
    ('Wolfir Silverheart', '{3}{G}{G}', 'Creature — Wolf Warrior', '4', '4',
     'Soulbond (You may pair this creature with another unpaired creature when either enters. They remain paired for as long as you control both of them.)\nAs long as this creature is paired with another creature, each of those creatures gets +4/+4.'),
    ('Balustrade Spy', '{3}{B}', 'Creature — Vampire Rogue', '2', '3',
     'Flying\nWhen this creature enters, target player reveals cards from the top of their library until they reveal a land card, then puts those cards into their graveyard.'),
    ('Clown Car', '{X}', 'Artifact — Vehicle', '1', '1',
     'When this Vehicle enters, roll X six-sided dice. For each odd result, create a 1/1 white Clown Robot artifact creature token. For each even result, put a +1/+1 counter on this Vehicle.\nCrew 2'),
    ('Wyll, Blade of Frontiers', '{1}{R}', 'Legendary Creature — Human Warlock', '1', '1',
     'If you would roll one or more dice, instead roll that many dice plus one and ignore the lowest roll.\nWhenever you roll one or more dice, put a +1/+1 counter on Wyll.\nChoose a Background (You can have a Background as a second commander.)'),
    ('Pixie Guide', '{1}{U}', 'Creature — Faerie', '1', '3',
     'Flying\nGrant an Advantage — If you would roll one or more dice, instead roll that many dice plus one and ignore the lowest roll.'),
    ('Resolute Veggiesaur', '{2}{G}', 'Creature — Dinosaur Employee', '3', '3',
     'Trample\nWhenever you roll your third die each turn, put a +1/+1 counter on this creature.'),
    ('Remorseless Punishment', '{3}{B}{B}', 'Sorcery', None, None,
     'Target opponent loses 5 life unless that player discards two cards or sacrifices a creature or planeswalker of their choice. Repeat this process once.'),
    ('Ad Nauseam', '{3}{B}{B}', 'Instant', None, None,
     'Reveal the top card of your library and put that card into your hand. You lose life equal to its mana value. You may repeat this process any number of times.'),
    ('Zimone and Dina', '{B}{G}{U}', 'Legendary Creature — Human Dryad', '3', '4',
     'Whenever you draw your second card each turn, target opponent loses 2 life and you gain 2 life.\n{T}, Sacrifice another creature: Draw a card. You may put a land card from your hand onto the battlefield tapped. If you control eight or more lands, repeat this process once.'),
    ('Countryside Crusher', '{1}{R}{R}', 'Creature — Giant Warrior', '3', '3',
     "At the beginning of your upkeep, reveal the top card of your library. If it's a land card, put it into your graveyard and repeat this process.\nWhenever a land card is put into your graveyard from anywhere, put a +1/+1 counter on this creature."),
    ("Hoarder's Greed", '{3}{B}', 'Sorcery', None, None,
     'You lose 2 life and draw two cards, then clash with an opponent. If you win, repeat this process. (Each clashing player reveals the top card of their library, then puts that card on their choice of the top or bottom. A player wins if their card had a greater mana value.)'),
    ('Kindle the Carnage', '{1}{R}{R}', 'Sorcery', None, None,
     "Discard a card at random. If you do, Kindle the Carnage deals damage equal to that card's mana value to each creature. You may repeat this process any number of times."),
    ("Diviner's Portent", '{X}{U}{U}{U}', 'Instant', None, None,
     'Roll a d20 and add the number of cards in your hand.\n1—14 | Draw X cards.\n15+ | Scry X, then draw X cards.'),
    ('Monoxa, Midway Manager', '{2}{B}{R}', 'Legendary Creature — Vampire Employee', '3', '3',
     'Whenever you roll a 3 or higher, Monoxa gains first strike until end of turn. If the roll was 4 or higher, it gains menace until end of turn. If the roll was 5 or higher, it gains lifelink until end of turn.\n{6}: Roll a six-sided die.'),
    ('Glitch Ghost Surveyor', '{2}{U}', 'Creature — Spirit Scout', '2', '2',
     'Flying\nStart your engines! (If you have no speed, it starts at 1. It increases once on each of your turns when an opponent loses life. Max speed is 4.)\nMax speed — {3}, Exile this card from your graveyard: Draw a card.'),
    ('Act of Treason', '{2}{R}', 'Sorcery', None, None,
     'Gain control of target creature until end of turn. Untap that creature. It gains haste until end of turn. (It can attack and {T} this turn.)'),
    ('Atomwheel Acrobats', '{3}{G}', 'Creature — Elf Performer', '3', '2',
     'Whenever you roll a 1 or 2, put that many +1/+1 counters on this creature.\n{2}{G}: Roll a six-sided die.'),
    ('Insatiable Frugivore', '{3}{B}', 'Creature — Rat Berserker', '2', '4',
     'When this creature enters, create a Food token, then you may exile three cards from your graveyard. If you do, repeat this process.\n{3}{B}, Sacrifice X Foods: Creatures you control get +X/+0 and gain menace until end of turn.'),
    ('Circuits Act', '{2}{R}', 'Sorcery', None, None,
     'Roll three six-sided dice. For each different result, create a 1/1 white Clown Robot artifact creature token.'),
    ('Attempted Murder', '{X}{B}{B}', 'Sorcery', None, None,
     'Choose target creature. Roll X six-sided dice. For each even result, put two -1/-1 counters on that creature. For each odd result, create a 1/2 blue Bird creature token with flying named Storm Crow.'),
]


EXTRA = [card(n, set_code="r24b", number=f"R{i:02d}", mana_cost=mc, cmc=0.0, type_line=tl, colors=[], color_identity=[], oracle_text=text,
              **({"power": p, "toughness": t} if p is not None else {})) for i, (n, mc, tl, p, t, text) in enumerate(REAL)] + [
    card("R24 Proliferator", set_code="r24b", number="X1", mana_cost="{1}", type_line="Sorcery", colors=[], color_identity=[],
         oracle_text="Proliferate."),
    card("R24 Bear", set_code="r24b", number="X2", mana_cost="{1}", type_line="Creature — Bear", colors=[], color_identity=[],
         oracle_text="", power="2", toughness="2"),
    card("R24 Blink", set_code="r24b", number="X3", mana_cost="{1}", type_line="Instant", colors=[], color_identity=[],
         oracle_text="Exile target creature you control, then return that card to the battlefield under its owner's control."),
]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def speed(s, pid="p1"):
    return s.state.players[pid].resources.get("speed")


def until_decision(s, limit=8):
    for _ in range(limit):
        if s.state.rules.decision is not None:
            return s.state.rules.decision
        if not s.state.zones.get("stack"):
            return None
        act(s, s.state.rules.priority, type="pass_priority")
    return s.state.rules.decision


def test_probe_proliferate_does_not_touch_speed(cards):
    s = build(cards, ["Nesting Bot", "R24 Proliferator"], [])
    put(s, "Nesting Bot")
    act(s, "p1", type="set_resource", player="p1", key="speed", value=1)
    assert speed(s) == 1
    c = to_hand(s, "R24 Proliferator")
    mana(s, C=1)
    act(s, "p1", type="cast_spell", card_id=c.id)
    d = until_decision(s)
    answer(s, ["p1"] if d and any(o.id == "p1" for o in d.options) else [])
    assert speed(s) == 1, "speed is not a counter (122.1, 702.179)"
    check(s)


def test_probe_soulbond_trigger_of_a_blinked_creature_does_not_pair_the_new_object(cards):
    s = build(cards, ["Wolfir Silverheart", "R24 Bear", "R24 Blink"], [])
    put(s, "R24 Bear")
    b = to_hand(s, "R24 Blink")
    w = to_hand(s, "Wolfir Silverheart")
    mana(s, G=5, C=1)
    act(s, "p1", type="cast_spell", card_id=w.id)
    for _ in range(3):
        if s.state.rules.decision is not None or w.id in s.state.zones.get("p1:battlefield", []):
            break
        act(s, s.state.rules.priority, type="pass_priority")
    act(s, "p1", type="cast_spell", card_id=b.id, targets=[w.id])
    answer(s, "no", "yes")
    assert not s.state.rules.pairs, "702.95c: the old trigger's creature left the battlefield"
    check(s)


def build3(cards, mine=(), theirs=(), third=()):
    from app.game.factory import PlayerSetup, new_game
    from app.game.session import GameSession
    from tests.game_helpers import deck, enable

    decks = [deck(cards, cmd, [*((1, n) for n in names), (10, "Forest")])
             for cmd, names in (("Krenko, Mob Boss", mine), ("Atraxa, Praetors' Voice", theirs), ("Krenko, Mob Boss", third))]
    s = GameSession(enable(new_game([PlayerSetup(n, cards=d) for n, d in zip(("Alice", "Bob", "Cara"), decks, strict=True)],
                                    shuffle=False)), cards=cards)
    act(s, "p1", type="pass_priority")
    return s


def test_probe_speed_multiplayer(cards):
    s = build3(cards, ["Nesting Bot", "Lightning Bolt"], [], [])
    act(s, "p1", type="set_resource", player="p1", key="speed", value=1)
    act(s, "p1", type="set_resource", player="p2", key="speed", value=1)
    b = to_hand(s, "Lightning Bolt")
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=b.id, targets=["p2"])
    answer(s)
    assert speed(s) == 2 and speed(s, "p2") == 1  # (Bob's speed: not his turn)
    check(s)


def test_probe_speed_trigger_rechecked_on_resolution(cards):
    """603.4: the intervening if is checked again as the speed trigger resolves."""
    s = build(cards, ["Nesting Bot", "Lightning Bolt", "R24 Blink"], [])
    put(s, "Nesting Bot")
    act(s, "p1", type="set_resource", player="p1", key="speed", value=3)
    b = to_hand(s, "Lightning Bolt")
    to_hand(s, "R24 Blink")
    mana(s, R=1, C=1)
    act(s, "p1", type="cast_spell", card_id=b.id, targets=["p2"])
    assert len(s.state.zones.get("stack", [])) == 1 and speed(s) == 3  # (the speed trigger waits on the stack)
    act(s, "p1", type="set_resource", player="p1", key="speed", value=4)
    answer(s)
    assert speed(s) == 4
    check(s)


def test_probe_speed_persists_when_the_engine_leaves(cards):
    s = build(cards, ["Nesting Bot", "Lightning Bolt"], [])
    nb = put(s, "Nesting Bot")
    act(s, "p1", type="set_resource", player="p1", key="speed", value=2)
    act(s, "p1", type="move", card_ids=[nb.id], to={"zone": "graveyard"})
    b = to_hand(s, "Lightning Bolt")
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=b.id, targets=["p2"])
    answer(s)
    assert speed(s) == 3
    check(s)


def test_probe_glitch_ghost_graveyard_ability_only_at_max_speed(cards):
    from app.game.errors import ActionError
    from app.rules.plan import Plan

    s = build(cards, ["Glitch Ghost Surveyor"], [])
    g = card_named(s, "Glitch Ghost Surveyor")
    act(s, "p1", type="move", card_ids=[g.id], to={"zone": "graveyard"})
    abil = [a.index for a in Plan(s.state, "p1", s.cards, None).ch(s.state.cards[g.id]).abilities if a.kind == "activated"]
    act(s, "p1", type="set_resource", player="p1", key="speed", value=3)
    mana(s, C=3)
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=g.id, ability=abil[-1])
    act(s, "p1", type="set_resource", player="p1", key="speed", value=4)
    hand = len(s.state.zones["p1:hand"])
    act(s, "p1", type="activate_ability", card_id=g.id, ability=abil[-1])
    answer(s)
    assert len(s.state.zones["p1:hand"]) == hand + 1 and s.state.cards[g.id].zone == "p1:exile"
    check(s)


def test_probe_deadeye_navigator_blink_repairs(cards):
    from app.rules.plan import Plan

    s = build(cards, ["Deadeye Navigator", "R24 Bear"], [])
    put(s, "R24 Bear")
    nav = to_hand(s, "Deadeye Navigator")
    mana(s, G=4, U=2)
    act(s, "p1", type="cast_spell", card_id=nav.id)
    answer(s, "yes")
    assert len(s.state.rules.pairs) == 2
    bear = card_named(s, "R24 Bear")
    abil = [a for a in Plan(s.state, "p1", s.cards, None).ch(s.state.cards[bear.id]).abilities if a.kind == "activated"]
    mana(s, U=1, G=1)
    act(s, "p1", type="activate_ability", card_id=bear.id, ability=abil[0].index)
    answer(s, "yes")
    assert len(s.state.rules.pairs) == 2 and s.state.cards[bear.id].zone == "p1:battlefield"
    check(s)


def test_probe_breathkeeper_seraph_returns_the_partner(cards):
    from tests.test_rules_conditionals import to_turn

    s = build(cards, ["Breathkeeper Seraph", "R24 Bear", "Lightning Bolt"], [])
    put(s, "R24 Bear")
    ser = to_hand(s, "Breathkeeper Seraph")
    mana(s, W=6)
    act(s, "p1", type="cast_spell", card_id=ser.id)
    answer(s, "yes")
    bear = card_named(s, "R24 Bear")
    b = to_hand(s, "Lightning Bolt")
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=b.id, targets=[bear.id])
    answer(s, "yes")
    assert s.state.cards[bear.id].zone == "p1:graveyard"
    to_turn(s, 3, phase="main1")
    answer(s, "yes")
    assert s.state.cards[bear.id].zone == "p1:battlefield"
    check(s)


def test_probe_balustrade_spy_third_player_no_land_mills_whole_library(cards):
    s = build3(cards, ["Balustrade Spy"], [], ["R24 Bear"])
    lands = [c.id for c in s.state.cards.values() if c.zone == "p3:library" and c.name == "Forest"]
    act(s, "p3", type="move", card_ids=lands, to={"zone": "exile"})
    n = len(s.state.zones["p3:library"])
    spy = to_hand(s, "Balustrade Spy")
    mana(s, B=1, G=3)
    act(s, "p1", type="cast_spell", card_id=spy.id, targets=[], target_counts=[1])
    answer(s, "p3")
    assert not s.state.zones["p3:library"] and len(s.state.zones["p3:graveyard"]) == n
    check(s)


def test_probe_pair_ends_before_state_based_actions(cards):
    """702.95e then 704.5g: the creature that lost the pair's bonus dies with the damage on it, before anyone gets priority."""
    from tests.test_rules_conditionals import to_turn

    s = build(cards, ["Wolfir Silverheart", "R24 Bear"], ["Lightning Bolt", "Act of Treason"])
    put(s, "R24 Bear")
    w = to_hand(s, "Wolfir Silverheart")
    mana(s, G=5)
    act(s, "p1", type="cast_spell", card_id=w.id)
    answer(s, "yes")
    bear = card_named(s, "R24 Bear")
    to_turn(s, 2)
    b = to_hand(s, "Lightning Bolt", "p2")
    mana(s, "p2", R=1)
    act(s, "p2", type="cast_spell", card_id=b.id, targets=[bear.id])
    answer(s)
    assert s.state.cards[bear.id].zone == "p1:battlefield"  # 6/6 with 3 damage
    t = to_hand(s, "Act of Treason", "p2")
    mana(s, "p2", R=3)
    act(s, "p2", type="cast_spell", card_id=t.id, targets=[bear.id])
    answer(s)
    assert s.state.cards[bear.id].zone == "p1:graveyard"
    check(s)


def test_probe_pair_choice_survives_save_mid_decision(cards):
    s = build(cards, ["Wolfir Silverheart", "R24 Bear", "Deadeye Navigator"], [])
    put(s, "R24 Bear")
    put(s, "Deadeye Navigator")
    w = to_hand(s, "Wolfir Silverheart")
    mana(s, G=5)
    act(s, "p1", type="cast_spell", card_id=w.id)
    for _ in range(6):
        d = s.state.rules.decision
        if d is not None and d.kind == "choose_cards":
            break
        if d is not None:
            ids = ["yes"] if any(o.id == "yes" for o in d.options) else [o.id for o in d.options][::-1][:max(1, d.min_choices)]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=ids)
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    d = s.state.rules.decision
    assert d is not None and d.kind == "choose_cards"
    replay_matches(s)
    s2 = reloaded(s)
    nav = card_named(s2, "Deadeye Navigator")
    act(s2, "p1", type="choose", decision_id=s2.state.rules.decision.id, option_ids=[nav.id])
    answer(s2)
    assert len(s2.state.rules.pairs) == 2
    check(s2)


def counters(s, name, kind="+1/+1"):
    return s.state.cards[card_named(s, name).id].counters.get(kind, 0)


def test_probe_two_advantage_effects_keep_one_die_and_count_only_kept_dice(cards, monkeypatch):
    rolls(monkeypatch, 2, 6, 1)  # one die asked for; Wyll and Pixie Guide: three rolled, the two lowest ignored (616.1, 706.6)
    s = build(cards, ["Atomwheel Acrobats", "Wyll, Blade of Frontiers", "Pixie Guide", "Resolute Veggiesaur"], [])
    for n in ("Atomwheel Acrobats", "Wyll, Blade of Frontiers", "Pixie Guide", "Resolute Veggiesaur"):
        put(s, n)
    mana(s, G=3)
    act(s, "p1", type="activate_ability", card_id=card_named(s, "Atomwheel Acrobats").id, ability=1)
    answer(s)
    assert counters(s, "Atomwheel Acrobats") == 0  # the 6 is kept; the 2 and the 1 never happened
    assert counters(s, "Resolute Veggiesaur") == 0  # (one die rolled this turn, not three)
    check(s)


def test_probe_diviners_portent_with_advantage(cards, monkeypatch):
    rolls(monkeypatch, 3, 12)
    s = build(cards, ["Diviner's Portent", "Pixie Guide"], [])
    put(s, "Pixie Guide")
    sp = to_hand(s, "Diviner's Portent")
    hand = len(s.state.zones["p1:hand"])  # 1 card (the Portent) → after cast 0 cards: 12 + 0 = 12 → "draw X"
    mana(s, U=5)
    act(s, "p1", type="cast_spell", card_id=sp.id, x_value=2)
    answer(s)
    assert len(s.state.zones["p1:hand"]) == hand - 1 + 2
    check(s)


def test_probe_kindle_the_carnage_save_mid_decision(cards, monkeypatch):
    s = build(cards, ["Kindle the Carnage", "R24 Bear", "Zimone and Dina", "Countryside Crusher"], [])
    put(s, "R24 Bear")
    for n in ("Zimone and Dina", "Countryside Crusher"):
        to_hand(s, n)
    sp = to_hand(s, "Kindle the Carnage")
    mana(s, R=3)
    act(s, "p1", type="cast_spell", card_id=sp.id)
    for _ in range(4):
        if s.state.rules.decision is not None:
            break
        act(s, s.state.rules.priority, type="pass_priority")
    d = s.state.rules.decision
    assert d is not None and "repeat" in d.prompt.lower(), d
    replay_matches(s)
    replay_matches(reloaded(s))
    s2 = reloaded(s)
    act(s2, "p1", type="choose", decision_id=s2.state.rules.decision.id, option_ids=["yes"])
    answer(s2, "no")
    assert len(s2.state.zones["p1:hand"]) == 0
    check(s2)


def test_probe_countryside_crusher_mills_lands_until_a_nonland(cards):
    from tests.test_rules_conditionals import to_turn

    s = build(cards, ["Countryside Crusher", "R24 Bear"], [])
    put(s, "Countryside Crusher")
    bear = card_named(s, "R24 Bear")
    # top of the library: four forests, then the bear
    act(s, "p1", type="move", card_ids=[bear.id], to={"player": "p1", "zone": "library"})
    forests = [c for c in s.state.cards.values() if c.name == "Forest" and c.zone == "p1:library"][:4]
    for f in forests:
        act(s, "p1", type="move", card_ids=[f.id], to={"player": "p1", "zone": "library"})
    to_turn(s, 3, phase="main1")
    yard = [s.state.cards[c].name for c in s.state.zones["p1:graveyard"]]
    assert yard.count("Forest") == 4 and counters(s, "Countryside Crusher") == 4  # (upkeep: before the draw)
    assert s.state.cards[bear.id].zone == "p1:hand"  # (revealed, not a land: stays on top, then drawn)
    check(s)


def test_probe_monoxa_life(cards, monkeypatch):
    rolls(monkeypatch, 4)
    s = build(cards, ["Monoxa, Midway Manager"], [])
    m = put(s, "Monoxa, Midway Manager")
    mana(s, C=6)
    act(s, "p1", type="activate_ability", card_id=m.id, ability=1)
    answer(s)
    from app.rules.plan import Plan

    kw = Plan(s.state, "p1", s.cards, None).ch(s.state.cards[m.id]).keywords
    assert "first strike" in kw and "menace" in kw and "lifelink" not in kw
    assert life(s) == 40
    check(s)

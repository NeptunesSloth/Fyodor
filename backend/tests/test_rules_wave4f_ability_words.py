"""Ability words (wave 4F): the italic word before the dash has no rules meaning (CR 207.2c; "corrupted", which the CR
doesn't list, is read the same way, 207.2d) — the text after it carries the condition. Mana abilities with an ability word
and an "Activate only if [condition]" restriction (605.1a, 605.3a, 602.5), channel abilities activated from the hand
by discarding the card (113.6m, 701.9a), "Descend 4 — Whenever …" triggers and "Corrupted — As long as …" statics.

Every scenario uses real Commander-legal cards with their current Oracle text (data/cards.sqlite), checks that
replaying the recorded history reproduces the table, and that a save/load round trip keeps it.
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.game.state import GameState
from app.rules import coverage
from app.rules.casting import activatable
from app.rules.characteristics import Characteristics, parse_type_line
from app.rules.mana import parse_mana_ability
from app.rules.oracle import parse_abilities
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, mana_pool
from tests.test_rules_effects import mana, pass_until_stack_empty, replay_matches
from tests.test_rules_permissions import build, put

EXTRA = [
    card('Mox Opal', set_code="tst", number="4F01", mana_cost='{0}', cmc=0.0, type_line='Legendary Artifact', oracle_text='Metalcraft — {T}: Add one mana of any color. Activate only if you control three or more artifacts.', keywords=['Metalcraft']),
    card('Whisperer of the Wilds', set_code="tst", number="4F02", mana_cost='{1}{G}', cmc=2.0, type_line='Creature — Human Shaman', oracle_text='{T}: Add {G}.\nFerocious — {T}: Add {G}{G}. Activate only if you control a creature with power 4 or greater.', power='0', toughness='2', colors=['G'], color_identity=['G'], keywords=['Ferocious']),
    card('Glistening Sphere', set_code="tst", number="4F03", mana_cost='{3}', cmc=3.0, type_line='Artifact', oracle_text='This artifact enters tapped.\nWhen this artifact enters, proliferate.\n{T}: Add one mana of any color.\nCorrupted — {T}: Add three mana of any one color. Activate only if an opponent has three or more poison counters.', keywords=['Corrupted', 'Proliferate']),
    card('Circle of Elders', set_code="tst", number="4F04", mana_cost='{2}{G}{G}', cmc=4.0, type_line='Creature — Human Shaman', oracle_text='Vigilance\nFormidable — {T}: Add {C}{C}{C}. Activate only if creatures you control have total power 8 or greater.', power='2', toughness='4', colors=['G'], color_identity=['G'], keywords=['Vigilance', 'Formidable']),
    card('Reinforced Ronin', set_code="tst", number="4F05", mana_cost='{R}', cmc=1.0, type_line='Artifact Creature — Human Samurai', oracle_text="Haste\nAt the beginning of your end step, return this creature to its owner's hand.\nChannel — {1}{R}, Discard this card: Draw a card.", power='2', toughness='2', colors=['R'], color_identity=['R'], keywords=['Haste', 'Channel']),
    card('Twinshot Sniper', set_code="tst", number="4F06", mana_cost='{3}{R}', cmc=4.0, type_line='Artifact Creature — Goblin Archer', oracle_text='Reach\nWhen this creature enters, it deals 2 damage to any target.\nChannel — {1}{R}, Discard this card: It deals 2 damage to any target.', power='2', toughness='3', colors=['R'], color_identity=['R'], keywords=['Reach', 'Channel']),
    card('Ghost-Lit Stalker', set_code="tst", number="4F07", mana_cost='{B}', cmc=1.0, type_line='Creature — Spirit', oracle_text='{4}{B}, {T}: Target player discards two cards. Activate only as a sorcery.\nChannel — {5}{B}{B}, Discard this card: Target player discards four cards. Activate only as a sorcery.', power='1', toughness='1', colors=['B'], color_identity=['B'], keywords=['Channel']),
    card('Stinging Cave Crawler', set_code="tst", number="4F08", mana_cost='{2}{B}', cmc=3.0, type_line='Creature — Insect Horror', oracle_text='Deathtouch\nDescend 4 — Whenever this creature attacks, if there are four or more permanent cards in your graveyard, you draw a card and you lose 1 life.', power='1', toughness='3', colors=['B'], color_identity=['B'], keywords=['Descend', 'Deathtouch']),
    card('Bonepicker Skirge', set_code="tst", number="4F09", mana_cost='{2}{B}', cmc=3.0, type_line='Creature — Phyrexian Imp', oracle_text='Flying\nCorrupted — As long as an opponent has three or more poison counters, this creature has deathtouch and lifelink.', power='2', toughness='2', colors=['B'], color_identity=['B'], keywords=['Flying', 'Corrupted']),
    card('Sinew Dancer', set_code="tst", number="4F10", mana_cost='{W}', cmc=1.0, type_line='Creature — Phyrexian Soldier', oracle_text='{3}{W}, {T}: Tap target creature.\nCorrupted — {W}, {T}: Tap target creature. Activate only if an opponent has three or more poison counters.', power='1', toughness='1', colors=['W'], color_identity=['W'], keywords=['Corrupted']),
    card('Greenbelt Guardian', set_code="tst", number="4F12", mana_cost='{1}{G}', cmc=2.0, type_line='Creature — Elf Ranger', oracle_text='{G}: Target creature gains trample until end of turn.\nExhaust — {3}{G}: Put three +1/+1 counters on this creature. (Activate each exhaust ability only once.)', power='2', toughness='2', colors=['G'], color_identity=['G'], keywords=['Exhaust']),
    card('Elvish Refueler', set_code="tst", number="4F13", mana_cost='{2}{G}', cmc=3.0, type_line='Creature — Elf Druid', oracle_text="During your turn, as long as you haven't activated an exhaust ability this turn, you may activate exhaust abilities as though they haven't been activated.\nExhaust — {1}{G}: Put a +1/+1 counter on this creature. (Activate each exhaust ability only once.)", power='2', toughness='3', colors=['G'], color_identity=['G'], keywords=['Exhaust']),
    card('Painful Truths', set_code="tst", number="4F14", mana_cost='{2}{B}', cmc=3.0, type_line='Sorcery', oracle_text='Converge — You draw X cards and lose X life, where X is the number of colors of mana spent to cast this spell.', colors=['B'], color_identity=['B'], keywords=['Converge']),
    card('Woodland Wanderer', set_code="tst", number="4F15", mana_cost='{3}{G}', cmc=4.0, type_line='Creature — Elemental', oracle_text='Vigilance, trample\nConverge — This creature enters with a +1/+1 counter on it for each color of mana spent to cast it.', power='2', toughness='2', colors=['G'], color_identity=['G'], keywords=['Vigilance', 'Converge', 'Trample']),
    card('Radiant Epicure', set_code="tst", number="4F16", mana_cost='{4}{B}', cmc=5.0, type_line='Creature — Vampire Wizard', oracle_text='Converge — When this creature enters, each opponent loses X life and you gain X life, where X is the number of colors of mana spent to cast this spell.', power='5', toughness='5', colors=['B'], color_identity=['B'], keywords=['Converge']),
]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def ch(s, c):
    return Plan(s.state, "p1", s.cards, None).ch(s.state.cards[c.id])


def tok(s, name, type_line="Token Creature — Test", pt="2/2", pid="p1"):
    p, t = pt.split("/")
    act(s, pid, type="create_token", player=pid, token={"name": name, "type_line": type_line, "power": p, "toughness": t,
                                                         "text": "", "colors": []})
    return next(c for c in s.state.cards.values() if c.name == name and c.owner == pid)


def roundtrip(s):
    """Replay rebuilds the same table, and a save/load round trip keeps it."""
    replay_matches(s)
    dumped = s.state.model_dump(mode="json")
    assert GameState.model_validate(dumped).model_dump(mode="json") == dumped


def ok(text, name="Card", type_line="Creature — Test"):
    """Is every ability line automated (coverage) on a card with that name and type?"""
    sup, types, sub = parse_type_line(type_line)
    feats = coverage.features_of(Characteristics(name=name, supertypes=sup, types=types, subtypes=sub, oracle_text=text,
                                                 abilities=tuple(parse_abilities(text))))
    return all(f.supported for f in feats if f.id.startswith(("text:", "mana:")))


def mana_index(s, c, needle):
    return next(ab.index for ab in ch(s, c).abilities if needle in ab.text)


# -- the wordings -------------------------------------------------------------------------------------------------
def test_mana_abilities_read_without_their_ability_word():
    opal = parse_mana_ability("Metalcraft — {T}: Add one mana of any color. Activate only if you control three or more artifacts.")
    assert opal is not None and opal.condition == "count:Artifact:3"  # 207.2c: the word is dropped, the restriction kept
    ferocious = parse_mana_ability("Ferocious — {T}: Add {G}{G}. Activate only if you control a creature with power 4 or greater.")
    assert ferocious is not None and ferocious.condition is not None and ferocious.condition.startswith("cond:")
    assert parse_mana_ability("Corrupted — {T}: Add three mana of any one color. Activate only if an opponent has three or more "
                              "poison counters.") is not None
    # a keyword written "Name —" is no ability word (702.177 exhaust: "Activate only once"; 702.178 max speed)
    assert parse_mana_ability("Exhaust — {G}, {T}: Add three mana of any one color.") is None
    assert parse_mana_ability("Max speed — {T}: Add {C}{C}.") is None
    # a condition the grammar doesn't read stays manual
    assert parse_mana_ability("{T}: Add {C}. Activate only if you've cast a spell with flurgle this turn.") is None


def test_coverage_of_the_lines():
    assert ok("Metalcraft — {T}: Add one mana of any color. Activate only if you control three or more artifacts.", "Mox Opal",
              "Legendary Artifact")
    assert ok("Channel — {1}{R}, Discard this card: Draw a card.", "Reinforced Ronin")
    assert ok("Descend 4 — Whenever this creature attacks, if there are four or more permanent cards in your graveyard, you draw "
              "a card and you lose 1 life.", "Stinging Cave Crawler")
    assert ok("Corrupted — As long as an opponent has three or more poison counters, this creature has deathtouch and lifelink.",
              "Bonepicker Skirge")
    assert ok("Exhaust — {3}{G}: Put three +1/+1 counters on this creature.")  # 702.177a: "… Activate only once."
    assert ok("Max speed — Whenever you draw a card, each opponent mills two cards.")  # (wave 24B: 702.178a, app/rules/speed.py)
    # (wave 28B: the draw replacement applies while its controller's speed is 4 — 702.178a, replace._draw_applies; review 28B: Vnwxt)
    assert ok("Max speed — If you would draw a card, draw two cards instead.")


# -- mana abilities: 605.3a, 602.5 --------------------------------------------------------------------------------
def test_mox_opal_needs_three_artifacts(cards):
    s = build(cards, [(1, "Mox Opal"), (5, "Forest")])
    opal = put(s, "Mox Opal", "battlefield")
    tok(s, "Thopter A", "Token Artifact Creature — Thopter", "1/1")
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=opal.id, ability=0, mana_choice="U")
    tok(s, "Thopter B", "Token Artifact Creature — Thopter", "1/1")  # Mox Opal itself is the third artifact
    act(s, "p1", type="activate_ability", card_id=opal.id, ability=0, mana_choice="U")
    assert mana_pool(s) == {"U": 1}
    roundtrip(s)


def test_whisperer_of_the_wilds_ferocious(cards):
    s = build(cards, [(1, "Whisperer of the Wilds"), (5, "Forest")])
    whisperer = put(s, "Whisperer of the Wilds", "battlefield")
    act(s, "p1", type="pass_priority")  # (summoning sickness: let a turn go by)
    for _ in range(40):
        if s.state.turn.active_player == "p1" and s.state.turn.phase == "main1":
            break
        act(s, s.state.rules.priority or s.state.turn.active_player, type="pass_priority")
    ferocious = mana_index(s, whisperer, "Ferocious")
    tok(s, "Small", pt="3/3")
    tok(s, "Theirs", pt="5/5", pid="p2")  # an opponent's creature doesn't count
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=whisperer.id, ability=ferocious)
    tok(s, "Big", pt="4/1")
    act(s, "p1", type="activate_ability", card_id=whisperer.id, ability=ferocious)
    assert mana_pool(s) == {"G": 2}
    roundtrip(s)


def test_glistening_sphere_corrupted(cards):
    from app.rules.casting import mana_abilities

    s = build(cards, [(1, "Glistening Sphere"), (5, "Forest")])
    sphere = put(s, "Glistening Sphere", "battlefield")
    corrupted = mana_index(s, sphere, "Corrupted")

    def usable():
        return [i for i, _ in mana_abilities(s.state, s.state.cards[sphere.id], s.cards)]

    act(s, "p1", type="resource", player="p2", key="poison", delta=2)
    assert corrupted not in usable()
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=sphere.id, ability=corrupted)
    act(s, "p1", type="resource", player="p2", key="poison", delta=1)  # one opponent with three (122.1f)
    assert corrupted in usable()
    act(s, "p1", type="resource", player="p1", key="poison", delta=5)  # your own counters don't count
    act(s, "p1", type="resource", player="p2", key="poison", delta=-1)
    assert corrupted not in usable()
    roundtrip(s)


def test_formidable_counts_total_power(cards):
    s = build(cards, [(1, "Circle of Elders"), (5, "Forest")])
    circle = put(s, "Circle of Elders", "battlefield")
    plan = Plan(s.state, "p1", s.cards, None)
    from app.rules.casting import mana_abilities

    assert mana_abilities(s.state, s.state.cards[circle.id], s.cards) == []  # 2 power: no
    tok(s, "Five", pt="5/5")
    assert mana_abilities(s.state, s.state.cards[circle.id], s.cards) == []  # 7
    tok(s, "One", pt="1/1")
    assert [i for i, _ in mana_abilities(s.state, s.state.cards[circle.id], s.cards)] == [1]  # 8 or greater
    assert plan is not None


# -- channel: 113.6m, 701.9a ----------------------------------------------------------------------------------------
def test_channel_draws_from_the_hand(cards):
    s = build(cards, [(1, "Reinforced Ronin"), (5, "Mountain")], [(10, "Island")])
    ronin = put(s, "Reinforced Ronin", "hand")
    hand_before = len(s.state.zones["p1:hand"])
    mana(s, R=2)
    assert {"card_id": ronin.id, "ability": 2} in activatable(s.state, "p1", s.cards)
    act(s, "p1", type="activate_ability", card_id=ronin.id, ability=2)
    assert s.state.cards[ronin.id].zone == "p1:graveyard"  # discarded as a cost
    pass_until_stack_empty(s)
    assert len(s.state.zones["p1:hand"]) == hand_before  # −1 discarded, +1 drawn
    assert s.state.players["p1"].mana == {}
    roundtrip(s)


def test_channel_only_from_the_hand(cards):
    s = build(cards, [(1, "Reinforced Ronin"), (5, "Mountain")])
    ronin = put(s, "Reinforced Ronin", "battlefield")
    mana(s, R=2)
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=ronin.id, ability=2)
    assert {"card_id": ronin.id, "ability": 2} not in activatable(s.state, "p1", s.cards)
    put(s, "Reinforced Ronin", "graveyard")
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=ronin.id, ability=2)
    roundtrip(s)


def test_channel_damage_from_the_discarded_card(cards):
    s = build(cards, [(1, "Twinshot Sniper"), (5, "Mountain")])
    sniper = put(s, "Twinshot Sniper", "hand")
    mana(s, R=2)
    act(s, "p1", type="activate_ability", card_id=sniper.id, ability=2, targets=["p2"])
    assert s.state.cards[sniper.id].zone == "p1:graveyard"
    pass_until_stack_empty(s)
    assert s.state.players["p2"].life == 38  # 608.2h: "It" is the card as it last existed in the hand
    roundtrip(s)


def test_channel_keeps_its_restriction(cards):
    s = build(cards, [(1, "Ghost-Lit Stalker"), (5, "Swamp")], [(10, "Island")])
    stalker = put(s, "Ghost-Lit Stalker", "hand")
    mana(s, B=7)
    act(s, "p1", type="pass_priority")  # → combat: no longer a time for sorceries (307.5)
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=stalker.id, ability=1, targets=["p2"])
    assert s.state.cards[stalker.id].zone == "p1:hand"  # nothing was paid
    roundtrip(s)


def test_opponent_cant_channel_your_card(cards):
    s = build(cards, [(1, "Reinforced Ronin"), (5, "Mountain")])
    ronin = put(s, "Reinforced Ronin", "hand")
    mana(s, pid="p2", R=2)
    with pytest.raises(ActionError):
        act(s, "p2", type="activate_ability", card_id=ronin.id, ability=2)


# -- statics, triggers and activated abilities after an ability word ---------------------------------------------
def test_corrupted_static(cards):
    s = build(cards, [(1, "Bonepicker Skirge"), (5, "Swamp")])
    skirge = put(s, "Bonepicker Skirge", "battlefield")
    assert not {"deathtouch", "lifelink"} & ch(s, skirge).keywords
    act(s, "p1", type="resource", player="p2", key="poison", delta=3)
    assert {"deathtouch", "lifelink"} <= ch(s, skirge).keywords
    roundtrip(s)


def test_corrupted_activated_restriction(cards):
    s = build(cards, [(1, "Sinew Dancer"), (5, "Forest")])
    dancer = put(s, "Sinew Dancer", "battlefield")
    act(s, "p1", type="pass_priority")
    for _ in range(40):
        if s.state.turn.active_player == "p1" and s.state.turn.phase == "main1":
            break
        act(s, s.state.rules.priority or s.state.turn.active_player, type="pass_priority")
    theirs = tok(s, "Theirs", pid="p2")
    mana(s, W=1)
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=dancer.id, ability=1, targets=[theirs.id])
    act(s, "p1", type="resource", player="p2", key="poison", delta=3)
    act(s, "p1", type="activate_ability", card_id=dancer.id, ability=1, targets=[theirs.id])
    pass_until_stack_empty(s)
    assert s.state.cards[theirs.id].tapped
    roundtrip(s)


def next_main(s):
    """Play on to Alice's next first main phase (her permanents are no longer summoning sick)."""
    act(s, "p1", type="pass_priority")
    for _ in range(60):
        if s.state.turn.active_player == "p1" and s.state.turn.phase == "main1" and s.state.turn.number > 1:
            return
        d = s.state.rules.decision
        if d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
            continue
        act(s, s.state.rules.priority or s.state.turn.active_player, type="pass_priority")


@pytest.mark.parametrize("in_graveyard", [3, 4])
def test_descend_4_attack_trigger(cards, in_graveyard):
    s = build(cards, [(1, "Stinging Cave Crawler"), (6, "Forest"), (10, "Island")])
    crawler = put(s, "Stinging Cave Crawler", "battlefield")
    forests = [c for c in s.state.cards.values() if c.name == "Forest" and c.owner == "p1"]
    for f in forests[:in_graveyard]:
        act(s, "p1", type="move", card_ids=[f.id], to={"player": "p1", "zone": "graveyard"})
    next_main(s)
    act(s, "p1", type="pass_priority")  # → declare attackers
    life, hand = s.state.players["p1"].life, len(s.state.zones["p1:hand"])
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": crawler.id, "target": "p2"}])
    pass_until_stack_empty(s)
    if in_graveyard >= 4:  # 603.4: "if there are four or more permanent cards in your graveyard"
        assert (s.state.players["p1"].life, len(s.state.zones["p1:hand"])) == (life - 1, hand + 1)
    else:
        assert (s.state.players["p1"].life, len(s.state.zones["p1:hand"])) == (life, hand)
    roundtrip(s)


# -- exhaust: 702.177a -------------------------------------------------------------------------------------------
def test_exhaust_only_once(cards):
    s = build(cards, [(1, "Greenbelt Guardian"), (5, "Forest")])
    guardian = put(s, "Greenbelt Guardian", "battlefield")
    mana(s, G=8)
    act(s, "p1", type="activate_ability", card_id=guardian.id, ability=1)
    pass_until_stack_empty(s)
    assert s.state.cards[guardian.id].counters.get("+1/+1") == 3
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=guardian.id, ability=1)
    put(s, "Greenbelt Guardian", "hand")  # 400.7: a new object, whose ability hasn't been activated
    put(s, "Greenbelt Guardian", "battlefield")
    act(s, "p1", type="activate_ability", card_id=guardian.id, ability=1)
    pass_until_stack_empty(s)
    assert s.state.cards[guardian.id].counters.get("+1/+1") == 3
    roundtrip(s)


def test_exhaust_with_elvish_refueler_is_left_to_the_player(cards):
    s = build(cards, [(1, "Greenbelt Guardian"), (1, "Elvish Refueler"), (5, "Forest")])
    guardian = put(s, "Greenbelt Guardian", "battlefield")
    put(s, "Elvish Refueler", "battlefield")
    mana(s, G=8)
    act(s, "p1", type="activate_ability", card_id=guardian.id, ability=1)
    pass_until_stack_empty(s)
    with pytest.raises(ActionError):  # -- turn state (wave 100H) -- 702.177b: not after an exhaust ability was activated this turn
        act(s, "p1", type="activate_ability", card_id=guardian.id, ability=1)
    assert s.state.cards[guardian.id].counters.get("+1/+1") == 3
    roundtrip(s)


# -- converge: the colors of mana spent to cast it (601.2h, 105.1) -------------------------------------------------
def test_painful_truths_counts_colors_spent(cards):
    s = build(cards, [(1, "Painful Truths"), (5, "Swamp"), (10, "Island")])
    truths = put(s, "Painful Truths", "hand")
    mana(s, B=1, U=1, C=1)  # two colors (colorless mana is no color)
    hand, life = len(s.state.zones["p1:hand"]), s.state.players["p1"].life
    act(s, "p1", type="cast_spell", card_id=truths.id)
    pass_until_stack_empty(s)
    assert len(s.state.zones["p1:hand"]) == hand - 1 + 2
    assert s.state.players["p1"].life == life - 2
    roundtrip(s)


def test_woodland_wanderer_enters_with_a_counter_per_color(cards):
    s = build(cards, [(1, "Woodland Wanderer"), (5, "Forest")])
    wanderer = put(s, "Woodland Wanderer", "hand")
    mana(s, G=1, R=1, W=1, B=1)
    act(s, "p1", type="cast_spell", card_id=wanderer.id)
    pass_until_stack_empty(s)
    assert s.state.cards[wanderer.id].zone == "p1:battlefield"
    assert s.state.cards[wanderer.id].counters.get("+1/+1") == 4
    roundtrip(s)


def test_woodland_wanderer_put_onto_the_battlefield_wasnt_cast(cards):
    s = build(cards, [(1, "Woodland Wanderer"), (5, "Forest")])
    wanderer = put(s, "Woodland Wanderer", "battlefield")
    assert not s.state.cards[wanderer.id].counters.get("+1/+1")  # no mana was spent to cast it
    roundtrip(s)


def test_radiant_epicure_trigger_reads_its_spell(cards):
    s = build(cards, [(1, "Radiant Epicure"), (5, "Swamp")])
    epicure = put(s, "Radiant Epicure", "hand")
    mana(s, B=2, G=1, C=2)
    life = s.state.players["p1"].life
    act(s, "p1", type="cast_spell", card_id=epicure.id)
    pass_until_stack_empty(s)
    pass_until_stack_empty(s)
    assert s.state.players["p2"].life == 38 and s.state.players["p1"].life == life + 2
    roundtrip(s)

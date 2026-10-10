"""Wave 29D: "can't lose life" (CR 2026-09-25), real Oracle text. Every scenario checks the replay and a save and a load.

* 119.8: a player who can't lose life can't make an exchange that would lower their life total, and a cost that has them pay life can't be paid;
  119.4b: 0 life can always be paid. 119.7 (can't gain life) is the other half of "your life total can't change".
* 614.17b-c: an event that can't happen can't be chosen as (part of) a cost, and no replacement or prevention effect (Bloodletter of Aclazotz) can modify it.
* 120.3a: damage dealt to the player is still dealt (it was dealt: "was dealt damage this turn", bloodthirst, damage triggers) - only the life
  loss doesn't happen. Poison and lifelink are not the life loss.
"""

from __future__ import annotations

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import coverage, scripts
from app.rules.casting import castable
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditionals import attack, through_combat, to_turn
from tests.test_rules_effects import pass_until_stack_empty, replay_matches
from tests.wave9c_kit import build, card_named, life, mana, put, reloaded, to_hand

REAL = [
    # -- real --
    card('Platinum Emperion', set_code='t29e', number='D1', mana_cost='{8}', cmc=8.0, type_line='Artifact Creature — Golem', power='8', toughness='8', colors=[], color_identity=[], oracle_text="Your life total can't change. (You can't gain or lose life. You can't pay any amount of life except 0.)"),
    card('Bloodletter of Aclazotz', set_code='t29e', number='D2', mana_cost='{1}{B}{B}{B}', cmc=4.0, type_line='Creature — Vampire Demon', power='2', toughness='4', colors=['B'], color_identity=['B'], keywords=['Flying'], oracle_text='Flying\nIf an opponent would lose life during your turn, they lose twice that much life instead. (Damage causes loss of life.)'),
    card('Necropotence', set_code='t29e', number='D3', mana_cost='{B}{B}{B}', cmc=3.0, type_line='Enchantment', colors=['B'], color_identity=['B'], oracle_text='Skip your draw step.\nWhenever you discard a card, exile that card from your graveyard.\nPay 1 life: Exile the top card of your library face down. Put that card into your hand at the beginning of your next end step.'),
    card('Horizon Canopy', set_code='t29e', number='D4', type_line='Land', colors=[], color_identity=['G', 'W'], oracle_text='{T}, Pay 1 life: Add {G} or {W}.\n{1}, {T}, Sacrifice this land: Draw a card.'),
    card('Blood Crypt', set_code='t29e', number='D5', type_line='Land — Swamp Mountain', colors=[], color_identity=['B', 'R'], oracle_text="({T}: Add {B} or {R}.)\nAs this land enters, you may pay 2 life. If you don't, it enters tapped."),
    card('Vault Skirge', set_code='t29e', number='D6', mana_cost='{1}{B/P}', cmc=2.0, type_line='Artifact Creature — Phyrexian Imp', power='1', toughness='1', colors=['B'], color_identity=['B'], keywords=['Flying', 'Lifelink'], oracle_text='({B/P} can be paid with either {B} or 2 life.)\nFlying\nLifelink (Damage dealt by this creature also causes you to gain that much life.)'),
    card('Gitaxian Probe', set_code='t29e', number='D7', mana_cost='{U/P}', cmc=1.0, type_line='Sorcery', colors=['U'], color_identity=['U'], oracle_text="({U/P} can be paid with either {U} or 2 life.)\nLook at target player's hand.\nDraw a card."),
    card('Toxic Deluge', set_code='t29e', number='D8', mana_cost='{2}{B}', cmc=3.0, type_line='Sorcery', colors=['B'], color_identity=['B'], oracle_text='As an additional cost to cast this spell, pay X life.\nAll creatures get -X/-X until end of turn.'),
    card('Flare of Fortitude', set_code='t29e', number='D9', mana_cost='{2}{W}{W}', cmc=4.0, type_line='Instant', colors=['W'], color_identity=['W'], oracle_text="You may sacrifice a nontoken white creature rather than pay this spell's mana cost.\nUntil end of turn, your life total can't change, and permanents you control gain hexproof and indestructible."),
    card("Teferi's Protection", set_code='t29e', number='D10', mana_cost='{2}{W}', cmc=3.0, type_line='Instant', colors=['W'], color_identity=['W'], oracle_text="Until your next turn, your life total can't change and you gain protection from everything. All permanents you control phase out. (While they're phased out, they're treated as though they don't exist. They phase in before you untap during your untap step.)\nExile Teferi's Protection."),
    card('Tree of Redemption', set_code='t29e', number='D11', mana_cost='{3}{G}', cmc=4.0, type_line='Creature — Plant', power='0', toughness='13', colors=['G'], color_identity=['G'], keywords=['Defender'], oracle_text="Defender\n{T}: Exchange your life total with this creature's toughness."),
    card('Vampire Nighthawk', set_code='t29e', number='D12', mana_cost='{1}{B}{B}', cmc=3.0, type_line='Creature — Vampire Shaman', power='2', toughness='3', colors=['B'], color_identity=['B'], keywords=['Deathtouch', 'Flying', 'Lifelink'], oracle_text='Flying\nDeathtouch (Any amount of damage this deals to a creature is enough to destroy it.)\nLifelink (Damage dealt by this creature also causes you to gain that much life.)'),
    card("Sovereign's Bite", set_code='t29e', number='D13', mana_cost='{1}{B}', cmc=2.0, type_line='Sorcery', colors=['B'], color_identity=['B'], oracle_text='Target player loses 3 life and you gain 3 life.'),
    card('Stormblood Berserker', set_code='t29e', number='D14', mana_cost='{1}{R}', cmc=2.0, type_line='Creature — Human Berserker', power='1', toughness='1', colors=['R'], color_identity=['R'], keywords=['Bloodthirst', 'Menace'], oracle_text="Bloodthirst 2 (If an opponent was dealt damage this turn, this creature enters with two +1/+1 counters on it.)\nMenace (This creature can't be blocked except by two or more creatures.)"),
    card('Exsanguinate', set_code='t29e', number='D15', mana_cost='{X}{B}{B}', cmc=2.0, type_line='Sorcery', colors=['B'], color_identity=['B'], oracle_text='Each opponent loses X life. You gain life equal to the life lost this way.'),
    card('Giant Growth', set_code='t29e', number='D16', mana_cost='{G}', cmc=1.0, type_line='Instant', colors=['G'], color_identity=['G'], oracle_text='Target creature gets +3/+3 until end of turn.'),
    card('Perch Protection', set_code='t29e', number='D17', mana_cost='{4}{W}{W}', cmc=6.0, type_line='Instant', colors=['W'], color_identity=['W'], keywords=['Gift'], oracle_text="Gift an extra turn (You may promise an opponent a gift as you cast this spell. If you do, they take an extra turn after this one.)\nCreate four 2/2 blue Bird creature tokens with flying. If the gift was promised, all permanents you control phase out, and until your next turn, your life total can't change and you gain protection from everything.\nExile Perch Protection."),
    card('Sedgemoor Witch', set_code='t29e', number='D18', mana_cost='{2}{B}', cmc=3.0, type_line='Creature — Human Warlock', power='3', toughness='2', colors=['B'], color_identity=['B'], keywords=['Magecraft', 'Menace', 'Ward'], oracle_text='Menace\nWard—Pay 3 life. (Whenever this creature becomes the target of a spell or ability an opponent controls, counter it unless that player pays 3 life.)\nMagecraft — Whenever you cast or copy an instant or sorcery spell, create a 1/1 black and green Pest creature token with "When this token dies, you gain 1 life."'),
    card('Polluted Delta', set_code='t29e', number='D19', type_line='Land', colors=[], color_identity=[], oracle_text='{T}, Pay 1 life, Sacrifice this land: Search your library for an Island or Swamp card, put it onto the battlefield, then shuffle.'),
    card('Adarkar Wastes', set_code='t29e', number='D20', type_line='Land', colors=[], color_identity=['U', 'W'], oracle_text='{T}: Add {C}.\n{T}: Add {W} or {U}. This land deals 1 damage to you.'),
    card('Necrodominance', set_code='t29e', number='D21', mana_cost='{B}{B}{B}', cmc=3.0, type_line='Legendary Enchantment', colors=['B'], color_identity=['B'], oracle_text='Skip your draw step.\nAt the beginning of your end step, you may pay any amount of life. If you do, draw that many cards.\nYour maximum hand size is five.\nIf a card or token would be put into your graveyard from anywhere, exile it instead.'),
    card('White Probe', set_code='t29e', number='E1', mana_cost='{W}', cmc=1.0, type_line='Creature — Soldier', colors=['W'], color_identity=['W'], power='1', toughness='1', oracle_text=''),
    card('Deep Analysis', set_code='t29e', number='D22', mana_cost='{3}{U}', cmc=4.0, type_line='Sorcery', colors=['U'], color_identity=['U'], keywords=['Flashback'], oracle_text='Target player draws two cards.\nFlashback—{1}{U}, Pay 3 life. (You may cast this card from your graveyard for its flashback cost. Then exile it.)'),
    card('Phyrexian Arena', set_code='t29e', number='D23', mana_cost='{1}{B}{B}', cmc=3.0, type_line='Enchantment', colors=['B'], color_identity=['B'], oracle_text='At the beginning of your upkeep, you draw a card and lose 1 life.'),
    # -- end real --
]
OURS = [c["name"] for c in REAL]
DECK = ("Platinum Emperion", "Bloodletter of Aclazotz", "Necropotence", "Horizon Canopy", "Blood Crypt", "Vault Skirge", "Gitaxian Probe",
        "Toxic Deluge", "Flare of Fortitude", "Teferi's Protection", "Tree of Redemption", "Vampire Nighthawk", "Sovereign's Bite",
        "Stormblood Berserker", "Exsanguinate", "Giant Growth", "Lightning Bolt", "Lightning Bolt", "Sedgemoor Witch", "Polluted Delta", "Adarkar Wastes", "Necrodominance", "White Probe", "Deep Analysis", "Phyrexian Arena")


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *REAL], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def table(cards):
    """Alice and Bob each with every card of the test in their library (one of each; two Bolts)."""
    return build(cards, DECK, DECK)


def check(s):
    replay_matches(s)
    replay_matches(reloaded(s))
    assert reloaded(s).state.model_dump(mode="json") == s.state.model_dump(mode="json")


def cast(s, name, pid="p1", **kw):
    """Put the card in hand and cast it (mana to pay it: ``mana={...}``), then let everything resolve."""
    pay = kw.pop("mana", None)
    c = to_hand(s, name, pid)
    if pay:
        mana(s, pid, **pay)
    act(s, pid, type="cast_spell", card_id=c.id, **kw)
    pass_until_stack_empty(s)
    return c


def lock(s, pid="p1"):
    """The player controls Platinum Emperion: "Your life total can't change." (the rest of the table is plain)."""
    return put(s, "Platinum Emperion", pid)


def remove(s, c):
    """Take the permanent off the battlefield (by hand)."""
    act(s, c.controller, type="move", card_ids=[c.id], to={"player": c.owner, "zone": "graveyard"})


def counters(s, name, pid="p1"):
    return s.state.cards[card_named(s, name, pid).id].counters


def swing(s, *names):
    """Alice attacks Bob with these (summoning sickness over); nobody blocks; plays on to the second main phase."""
    cs = [put(s, n) for n in names]
    for c in cs:
        s.state.rules.controlled_since[c.id].turn = 0
    act(s, "p1", type="pass_priority")  # → declare attackers
    attack(s, *((c, "p2") for c in cs))
    through_combat(s)


def test_the_wording_is_read():
    assert scripts.parse_effects("Until end of turn, your life total can't change.") is not None
    assert scripts.parse_effects("Until your next turn, your life total can't change.") is not None
    # only the controller's own total, for a stated time: anything else stays manual
    assert scripts.parse_effects("Your life total can't change.") is None  # (a static ability, not an instruction)
    assert scripts.parse_effects("Until end of turn, target player's life total can't change.") is None


def test_platinum_emperion_is_full(cards):
    assert coverage.of_card_data(cards.resolve("Platinum Emperion")).level == "FULL"


# -- the life total can't change: no life lost (119.8), none gained (119.7) -----------------------------------------------------------------------
def test_an_effect_that_makes_the_player_lose_life_does_nothing_and_the_gain_that_reads_it_is_zero(cards):
    s = table(cards)
    lock(s, "p2")
    cast(s, "Sovereign's Bite", targets=["p2"], mana={"B": 1, "C": 1})
    assert life(s, "p2") == 40 and life(s, "p1") == 43  # (Alice's own gain is hers; Bob's life total can't change)
    cast(s, "Exsanguinate", x_value=5, mana={"B": 2, "C": 5})  # X = 5: "You gain life equal to the life lost this way": none was lost
    assert life(s, "p2") == 40 and life(s, "p1") == 43
    check(s)


def test_in_a_three_player_game_only_the_locked_opponent_is_spared(cards):
    from app.game.factory import PlayerSetup, new_game
    from app.game.session import GameSession
    from tests.game_helpers import deck, enable

    alice = deck(cards, "Krenko, Mob Boss", [(1, "Exsanguinate"), (9, "Forest")])
    bob = deck(cards, "Atraxa, Praetors' Voice", [(1, "Platinum Emperion"), (10, "Island")])
    carol = deck(cards, "Krenko, Mob Boss", [(10, "Mountain")])
    s = GameSession(enable(new_game([PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=bob), PlayerSetup("Carol", cards=carol)],
                                    shuffle=False)), cards=cards)
    act(s, "p1", type="pass_priority")
    lock(s, "p2")
    cast(s, "Exsanguinate", x_value=4, mana={"B": 2, "C": 4})
    assert life(s, "p2") == 40 and life(s, "p3") == 36  # Bob's life total can't change; Carol loses 4
    assert life(s, "p1") == 44  # "gain life equal to the life lost this way": 4, not 8
    check(s)


def test_without_it_the_same_spells_work(cards):
    s = table(cards)
    cast(s, "Sovereign's Bite", targets=["p2"], mana={"B": 1, "C": 1})
    assert life(s, "p2") == 37 and life(s, "p1") == 43
    cast(s, "Exsanguinate", x_value=5, mana={"B": 2, "C": 5})
    assert life(s, "p2") == 32 and life(s, "p1") == 48
    check(s)


def test_the_controller_neither_loses_nor_gains_life_and_lifelink_gains_nothing(cards):
    s = table(cards)
    lock(s, "p1")
    cast(s, "Sovereign's Bite", targets=["p1"], mana={"B": 1, "C": 1})  # "Target player loses 3 life and you gain 3 life": Alice, on herself
    assert life(s, "p1") == 40
    swing(s, "Vampire Nighthawk")  # 2 lifelink damage to Bob: Bob loses 2, Alice's gain can't happen (119.7)
    assert life(s, "p2") == 38 and life(s, "p1") == 40
    check(s)


def test_damage_is_dealt_but_makes_no_life_lost(cards):
    s = table(cards)
    lock(s, "p2")
    cast(s, "Lightning Bolt", targets=["p2"], mana={"R": 1})
    assert life(s, "p2") == 40  # 120.3a: the damage was dealt, the life loss it causes can't happen
    cast(s, "Stormblood Berserker", mana={"R": 1, "C": 1})
    assert counters(s, "Stormblood Berserker") == {"+1/+1": 2}  # bloodthirst: an opponent was dealt damage this turn
    check(s)


def test_a_combat_damage_trigger_still_sees_the_damage(cards):
    s = table(cards)
    lock(s, "p2")
    swing(s, "Vampire Nighthawk")
    assert life(s, "p2") == 40 and life(s, "p1") == 42  # Alice gains (lifelink): the damage was dealt (120.3f)
    check(s)


# -- Bloodletter of Aclazotz (614.17c): the loss that can't happen is not doubled; the one that can is ----------------------------------------------------
def test_bloodletter_cannot_double_a_loss_that_cannot_happen(cards):
    s = table(cards)
    put(s, "Bloodletter of Aclazotz")
    emperion = lock(s, "p2")
    cast(s, "Lightning Bolt", targets=["p2"], mana={"R": 1})
    cast(s, "Sovereign's Bite", targets=["p2"], mana={"B": 1, "C": 1})
    assert life(s, "p2") == 40  # (nothing to double: 614.17c)
    check(s)
    remove(s, emperion)
    cast(s, "Lightning Bolt", targets=["p2"], mana={"R": 1})  # the second Bolt: 3 damage, doubled
    assert life(s, "p2") == 34
    cast(s, "Exsanguinate", x_value=1, mana={"B": 2, "C": 1})  # X = 1, doubled
    assert life(s, "p2") == 32
    check(s)


# -- paying life (119.4, 119.8): the cost can't be paid, only 0 life can ------------------------------------------------------------------------------------
def activatable(s, pid, c):
    return any(a == c.id or (isinstance(a, (list, tuple)) and a and a[0] == c.id) or (isinstance(a, dict) and a.get("card_id") == c.id)
               for a in s.view(pid)["rules"]["hints"].get("activatable", []))


def test_a_cost_of_paying_life_cant_be_paid_and_can_be_without_the_lock(cards):
    s = table(cards)
    necro = put(s, "Necropotence")
    emperion = lock(s)
    assert not activatable(s, "p1", necro)
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=necro.id, ability=2)
    assert life(s, "p1") == 40
    check(s)
    remove(s, emperion)
    assert activatable(s, "p1", necro)
    act(s, "p1", type="activate_ability", card_id=necro.id, ability=2)
    pass_until_stack_empty(s)
    assert life(s, "p1") == 39
    check(s)


def test_phyrexian_mana_cant_be_paid_with_life(cards):
    s = table(cards)
    emperion = lock(s)
    probe = to_hand(s, "Gitaxian Probe")
    assert not castable(s.state, "p1", probe, s.cards)  # {U/P}: no blue mana, and the 2 life can't be paid
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=probe.id, targets=["p2"])
    assert life(s, "p1") == 40
    check(s)
    remove(s, emperion)
    assert castable(s.state, "p1", probe, s.cards)
    act(s, "p1", type="cast_spell", card_id=probe.id, targets=["p2"])
    pass_until_stack_empty(s)
    assert life(s, "p1") == 38
    check(s)


def test_with_the_mana_in_the_pool_phyrexian_mana_is_just_mana(cards):
    s = table(cards)
    lock(s)
    cast(s, "Gitaxian Probe", targets=["p2"], mana={"U": 1})
    assert life(s, "p1") == 40
    check(s)


def test_a_mana_ability_that_costs_life_cant_be_used(cards):
    s = table(cards)
    canopy = put(s, "Horizon Canopy")
    bear = put(s, "Vampire Nighthawk")
    growth = to_hand(s, "Giant Growth")
    emperion = lock(s)
    assert not castable(s.state, "p1", growth, s.cards)  # {G} only from the Canopy: "{T}, Pay 1 life"
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=growth.id, targets=[bear.id])
    assert not canopy.tapped and life(s, "p1") == 40
    remove(s, emperion)
    assert castable(s.state, "p1", growth, s.cards)
    act(s, "p1", type="cast_spell", card_id=growth.id, targets=[bear.id])
    pass_until_stack_empty(s)
    assert canopy.tapped and life(s, "p1") == 39
    check(s)


def test_pay_x_life_is_payable_only_for_x_zero(cards):
    s = table(cards)
    lock(s)
    deluge = to_hand(s, "Toxic Deluge")
    mana(s, "p1", B=1, C=2)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=deluge.id, x_value=2)
    assert life(s, "p1") == 40
    act(s, "p1", type="cast_spell", card_id=deluge.id, x_value=0)  # 119.4b: 0 life can always be paid
    pass_until_stack_empty(s)
    assert life(s, "p1") == 40
    check(s)


def test_pay_x_life_without_the_lock(cards):
    s = table(cards)
    deluge = to_hand(s, "Toxic Deluge")
    mana(s, "p1", B=1, C=2)
    act(s, "p1", type="cast_spell", card_id=deluge.id, x_value=2)
    pass_until_stack_empty(s)
    assert life(s, "p1") == 38
    check(s)


def test_a_shock_land_enters_tapped_when_the_life_cant_be_paid(cards):
    s = table(cards)
    lock(s)
    crypt = to_hand(s, "Blood Crypt")
    act(s, "p1", type="play_land", card_id=crypt.id)
    pass_until_stack_empty(s)
    assert s.state.rules.decision is None  # (no question: 2 life can't be paid)
    assert crypt.zone == "p1:battlefield" and crypt.tapped and life(s, "p1") == 40
    check(s)


def test_a_shock_land_asks_without_the_lock(cards):
    s = table(cards)
    crypt = to_hand(s, "Blood Crypt")
    act(s, "p1", type="play_land", card_id=crypt.id)
    d = s.state.rules.decision
    assert d is not None
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[next(o.id for o in d.options if "pay" in o.id or "Pay" in o.label)])
    pass_until_stack_empty(s)
    assert not crypt.tapped and life(s, "p1") == 38
    check(s)


# -- exchanging life totals (119.8, 701.12) ------------------------------------------------------------------------------------------------------------------
def test_an_exchange_that_would_lower_the_life_total_does_not_happen(cards):
    s = table(cards)
    tree = put(s, "Tree of Redemption")
    s.state.rules.controlled_since[tree.id].turn = 0
    lock(s)
    act(s, "p1", type="activate_ability", card_id=tree.id, ability=1)
    pass_until_stack_empty(s)
    assert life(s, "p1") == 40  # 40 for 13: Alice would lose 27 life, and her life total can't change
    check(s)


def test_the_exchange_without_the_lock(cards):
    s = table(cards)
    tree = put(s, "Tree of Redemption")
    s.state.rules.controlled_since[tree.id].turn = 0
    act(s, "p1", type="activate_ability", card_id=tree.id, ability=1)
    pass_until_stack_empty(s)
    assert life(s, "p1") == 13
    check(s)


# -- the same words as an effect (Flare of Fortitude, Teferi's Protection) ---------------------------------------------------------------------------------
def test_flare_of_fortitude_locks_the_life_total_until_end_of_turn(cards):
    s = table(cards)
    necro = put(s, "Necropotence")
    cast(s, "Flare of Fortitude", mana={"W": 2, "C": 2})
    assert not activatable(s, "p1", necro)
    cast(s, "Sovereign's Bite", targets=["p1"], mana={"B": 1, "C": 1})
    assert life(s, "p1") == 40
    check(s)
    to_turn(s, 3)  # Alice's next turn: the lock ended at the cleanup step
    assert activatable(s, "p1", necro)
    act(s, "p1", type="activate_ability", card_id=necro.id, ability=2)
    pass_until_stack_empty(s)
    assert life(s, "p1") == 39
    check(s)


def keywords(s, c):
    from app.rules.plan import Plan

    return Plan(s.state, "p1", s.cards, None).ch(s.state.cards[c.id]).keywords


def test_flare_of_fortitude_also_gives_hexproof_and_indestructible_and_costs_a_white_creature_if_you_like(cards):
    from app.rules import casting

    s = table(cards)
    necro = put(s, "Necropotence")
    knight = put(s, "White Probe")
    flare = to_hand(s, "Flare of Fortitude")
    (alt,) = casting.alt_castable(s.state, "p1", flare, s.cards)
    act(s, "p1", type="cast_spell", card_id=flare.id, alt_cost=alt["id"])  # "You may sacrifice a nontoken white creature rather than pay …"
    d = s.state.rules.decision
    if d is not None:
        act(s, "p1", type="choose", decision_id=d.id, option_ids=[knight.id])
    pass_until_stack_empty(s)
    assert knight.zone == "p1:graveyard" and flare.zone == "p1:graveyard" and s.state.players["p1"].mana == {}
    assert {"hexproof", "indestructible"} <= keywords(s, necro)  # "permanents you control gain hexproof and indestructible"
    assert [x["until"] for x in s.state.rules.life_locks] == ["turn"]
    check(s)


def test_teferis_protection_locks_the_life_total_until_your_next_turn(cards):
    s = table(cards)
    necro = put(s, "Necropotence")
    cast(s, "Teferi's Protection", mana={"W": 1, "C": 2})
    assert [x["until"] for x in s.state.rules.life_locks] == ["next_turn"] and necro.zone == "p1:phased"  # 702.26: phased out
    assert any(x["shield"] == "protection" and x["quality"] == "everything" for x in s.state.rules.player_shields)
    to_turn(s, 2)  # Bob's turn: Alice's life total can't change, she has protection from everything, her permanents are phased out
    cast(s, "Exsanguinate", pid="p2", x_value=4, mana={"B": 2, "C": 4})
    assert life(s, "p1") == 40 and life(s, "p2") == 40  # (nobody lost or gained any: "the life lost this way" was 0)
    check(s)
    to_turn(s, 3)  # her next turn begins: the lock ends, her permanents phase in
    assert not s.state.rules.life_locks and necro.zone == "p1:battlefield"
    act(s, "p1", type="activate_ability", card_id=necro.id, ability=2)
    pass_until_stack_empty(s)
    assert life(s, "p1") == 39
    check(s)


def test_perch_protection_stays_partial_because_the_gift_of_an_extra_turn_is_manual(cards):
    assert coverage.of_card_data(cards.resolve("Perch Protection")).level != "FULL"  # 702.174g: "Gift an extra turn" is still manual (app/rules/gift.py)


# -- the costs of the cards that pay life as they work (119.8) ------------------------------------------------------------------------------------------
def test_ward_that_costs_life_cant_be_paid_so_the_spell_is_countered(cards):
    s = table(cards)
    witch = put(s, "Sedgemoor Witch", "p2")
    lock(s)
    bolt = to_hand(s, "Lightning Bolt")
    mana(s, "p1", R=1)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=[witch.id])
    pass_until_stack_empty(s)
    assert s.state.rules.decision is None  # (no question: 3 life can't be paid)
    assert bolt.zone == "p1:graveyard" and witch.zone == "p2:battlefield" and witch.damage == 0 and life(s, "p1") == 40  # Ward: countered
    check(s)


def test_the_same_ward_can_be_paid_without_the_lock(cards):
    s = table(cards)
    witch = put(s, "Sedgemoor Witch", "p2")
    bolt = to_hand(s, "Lightning Bolt")
    mana(s, "p1", R=1)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=[witch.id])
    pass_until_stack_empty(s)
    d = s.state.rules.decision
    assert d is not None
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["pay"])
    pass_until_stack_empty(s)
    assert life(s, "p1") == 37 and witch.zone == "p2:graveyard"
    check(s)


def test_a_painland_still_deals_its_damage_but_it_makes_the_player_lose_no_life(cards):
    for locked, left in ((True, 40), (False, 39)):
        s = table(cards)
        wastes = put(s, "Adarkar Wastes")
        if locked:
            lock(s)
        probe = to_hand(s, "Gitaxian Probe")
        act(s, "p1", type="cast_spell", card_id=probe.id, targets=["p2"])  # {U/P}: the blue mana from the Wastes, "This land deals 1 damage to you."
        pass_until_stack_empty(s)
        assert wastes.tapped and life(s, "p1") == left
        log = s.state.rules.turn_log
        assert any(f.kind == "damage" and f.player == "p1" and f.amount == 1 for f in log.facts)  # the 1 damage was dealt either way (120.3a)
        assert log.lost.get("p1", 0) == (0 if locked else 1)  # (and "life lost this turn" is what was lost)
        assert s.state.rules.damaged.get("p1") == s.state.turn.number  # (bloodthirst: "an opponent was dealt damage this turn", for Bob's creatures)
        check(s)


def test_a_flashback_cost_with_life_cant_be_paid(cards):
    for locked in (True, False):
        s = table(cards)
        analysis = to_hand(s, "Deep Analysis")
        act(s, "p1", type="move", card_ids=[analysis.id], to={"zone": "graveyard"})
        if locked:
            lock(s)
        mana(s, "p1", U=1, C=1)
        hand = len(s.state.zones["p1:hand"])
        assert castable(s.state, "p1", analysis, s.cards) is (not locked)  # (the hint agrees with the cast: "Pay 3 life" can't be paid, 119.8)
        if locked:
            with pytest.raises(ActionError):
                act(s, "p1", type="cast_spell", card_id=analysis.id, targets=["p1"])
            assert analysis.zone == "p1:graveyard" and life(s, "p1") == 40
        else:
            act(s, "p1", type="cast_spell", card_id=analysis.id, targets=["p1"])
            pass_until_stack_empty(s)
            assert analysis.zone == "p1:exile" and life(s, "p1") == 37 and len(s.state.zones["p1:hand"]) == hand + 2
        check(s)


def test_an_upkeep_trigger_that_draws_and_loses_life_still_draws(cards):
    for locked, left in ((True, 40), (False, 39)):
        s = table(cards)
        put(s, "Phyrexian Arena")
        if locked:
            lock(s)
        hand = len(s.state.zones["p1:hand"])
        to_turn(s, 3)  # Alice's next upkeep and draw step
        assert life(s, "p1") == left and len(s.state.zones["p1:hand"]) == hand + 2  # (the draw step's card and Phyrexian Arena's)
        check(s)


def test_pay_any_amount_of_life_offers_only_zero_to_a_player_who_cant_lose_life(cards):
    for locked in (True, False):
        s = table(cards)
        put(s, "Necrodominance")
        if locked:
            lock(s)
        for _ in range(30):  # on to her end step: "you may pay any amount of life"
            d = s.state.rules.decision
            if d is not None:
                break
            act(s, s.state.rules.priority, type="pass_priority")
        assert d is not None and d.player == "p1"
        labels = [o.label for o in d.options]
        assert ("Pay 1 life (X = 1)" in labels) is (not locked) and "Pay 0 life (X = 0)" in labels  # 119.4b: 0 can always be paid
        assert max(int(x.split("X = ")[1].rstrip(")")) for x in labels if "X = " in x) == (0 if locked else 40)
        check(s)


def test_a_fetch_land_cant_be_cracked_by_a_player_who_cant_lose_life(cards):
    s = table(cards)
    delta = put(s, "Polluted Delta")
    emperion = lock(s)
    assert not activatable(s, "p1", delta)
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=delta.id, ability=0)
    assert delta.zone == "p1:battlefield" and life(s, "p1") == 40
    check(s)
    remove(s, emperion)
    assert activatable(s, "p1", delta)
    check(s)


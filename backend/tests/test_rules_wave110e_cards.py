"""Wave 110E: single-card builds on real Oracle text; every scenario checks the replay and a save and a load.

* Garruk, Savage Herald: -7 grants the 510.1c permission to creatures for the turn (a quoted static the granting layer now reads).
* Storm, Windrider: 508.1c/509.1b flyers can't attack its controller or block its controller's creatures; 603.2 its cast trigger grants flying to the
  creatures the spell targets (115.9b), only when the spell has such a target.
* Blaze of Glory: 509.1c the target, which can block any number of creatures, must block each attacking creature it is able to.
* Vivien's Stampede: 603.7 "at the beginning of the next main phase this turn" (the postcombat main phase, never a later turn's), counted when it resolves.
* Spin into Myth: 701.29a fateseal 2 (look at the top two cards of an opponent's library, any to the bottom, the rest back on top in any order).
* Due Respect: 614.1d/611.2c every permanent entering this turn (a cast creature, either player's) enters tapped; the next turn it doesn't.
* Diminishing Returns: 701.24a shuffle, 121.2c/101.4 each player picks how many (0-7) to draw, then draws in APNAP order.
* Wild Shape: 700.2 the shared sentence applies to the chosen mode; 205.1a becoming "a 1/3 Turtle" replaces the creature types, sets base P/T, 611.2a for the turn.
* Hulk's Thunderclap: 701.4a/601.2b the optional "behold a Gamma creature" cost; 120.3 the first creature deals damage equal to its power; the destroy
  instruction (608.2h-style "if the additional cost was paid") happens only when it was paid.
* Phyrexian Purge: 118.8/601.2f 3 life per chosen target is added to the cost (paid with it, 119.4 never more than the life total).
"""
from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_designations import put as put3
from tests.test_rules_wave12a_counters_keywords import real
from tests.wave9c_kit import build, card_named, check, life, mana, put, to_hand

EXTRA = [
    real("Vivien's Stampede", "{4}{G}{G}", 6, "Sorcery",
         "Each creature you control gains vigilance, trample, and melee until end of turn. (Whenever a creature with melee attacks, it gets +1/+1 until end of turn for each opponent you attacked this combat.)\n"
         "At the beginning of the next main phase this turn, draw a card for each player who was dealt combat damage this turn.", None, "G"),
    real("Blaze of Glory", "{W}", 1, "Instant", "Cast this spell only during combat before blockers are declared.\n"
         "Target creature defending player controls can block any number of creatures this turn. It blocks each attacking creature this turn if able.", None, "W"),
    real("Storm, Windrider", "{1}{G}{W}{W}", 4, "Legendary Creature — Mutant Hero",
         "Flying\nCreatures with flying can't attack you or block creatures you control.\n"
         "Whenever you cast a spell that targets one or more creatures, those creatures gain flying until end of turn.", ("4", "4"), "GW"),
    real("Giant Growth", "{G}", 1, "Instant", "Target creature gets +3/+3 until end of turn.", None, "G"),
    real("Garruk, Savage Herald", "{4}{G}{G}", 6, "Legendary Planeswalker — Garruk",
         "+1: Reveal the top card of your library. If it's a creature card, put it into your hand. Otherwise, put it on the bottom of your library.\n"
         "−2: Target creature you control deals damage equal to its power to another target creature.\n"
         "−7: Until end of turn, creatures you control gain \"You may have this creature assign its combat damage as though it weren't blocked.\"", None, "G"),
    real("Due Respect", "{1}{W}", 2, "Instant", "Permanents enter tapped this turn.\nDraw a card.", None, "W"),
    real("Diminishing Returns", "{2}{U}{U}", 4, "Sorcery", "Each player shuffles their hand and graveyard into their library. You exile the top ten cards of your library. "
         "Then each player draws up to seven cards.", None, "U"),
    real("Wild Shape", "{1}{G}", 2, "Instant", "Choose one. Until end of turn, target creature you control has that base power and toughness, becomes that creature type, and gains that ability.\n"
         "• 1/3 Turtle with hexproof.\n• 1/5 Spider with reach.\n• 3/3 Elephant with trample.", None, "G"),
    real("Hulk's Thunderclap", "{1}{R}", 2, "Instant",
         "As an additional cost to cast this spell, you may behold a Gamma creature. (You may choose a Gamma creature you control or reveal a Gamma creature card from your hand.)\n"
         "Target creature you control deals damage equal to its power to another target creature. If this spell's additional cost was paid, destroy target noncreature artifact or noncreature enchantment.", None, "R"),
    real("Gamma Test", "{2}{G}", 3, "Creature — Mutant Gamma", "", ("3", "3"), "G"),
    real("Phyrexian Purge", "{2}{B}{B}", 4, "Sorcery", "This spell costs 3 life more to cast for each target.\nDestroy any number of target creatures.", None, "B"),
    real("Callous Oppressor", "{1}{U}{U}", 3, "Creature — Cephalid",
         "You may choose not to untap this creature during your untap step.\nAs this creature enters, an opponent chooses a creature type.\n"
         "{T}: Gain control of target creature that isn't of the chosen type for as long as this creature remains tapped.", ("1", "4"), "U"),
    real("Caller of the Hunt", "{2}{G}", 3, "Creature — Human",
         "As an additional cost to cast this spell, choose a creature type.\n"
         "Caller of the Hunt's power and toughness are each equal to the number of creatures of the chosen type on the battlefield.", ("*", "*"), "G"),
    real("Bear Cub", "{G}", 1, "Creature — Bear", "", ("1", "1"), "G"),
    real("Close Encounter", "{1}{R}", 2, "Instant",
         "As an additional cost to cast this spell, choose a creature you control or a warped creature card you own in exile.\n"
         "Close Encounter deals damage equal to the power of the chosen creature or card to target creature.", None, "R"),
    real("Thrill-Kill Disciple", "{2}{R}", 3, "Creature — Human Mercenary",
         "Squad—{1}, Discard a card. (As an additional cost to cast this spell, you may pay its squad cost any number of times. When this creature enters, create that many tokens that are copies of it.)\n"
         "When this creature dies, create a Junk token.", ("3", "2"), "R"),
    real("Lunar Hatchling", "{4}{G}{U}", 6, "Creature — Alien Beast",
         "Flying, trample\nBasic landcycling {2} ({2}, Discard this card: Search your library for a basic land card, reveal it, put it into your hand, then shuffle.)\n"
         "Escape—{4}{G}{U}, Exile a land you control, Exile five other cards from your graveyard. (You may cast this card from your graveyard for its escape cost.)",
         ("6", "6"), "GU"),
    real("Nettling Imp", "{2}{B}", 3, "Creature — Imp",
         "{T}: Choose target non-Wall creature the active player has controlled continuously since the beginning of the turn. That creature attacks this turn if able. Destroy it at the beginning of the next end step if it didn't attack this turn. Activate only during an opponent's turn, before attackers are declared.", ("1", "1"), "B"),
    real("Norritt", "{3}{B}", 4, "Creature — Imp",
         "{T}: Untap target blue creature.\n{T}: Choose target non-Wall creature the active player has controlled continuously since the beginning of the turn. That creature attacks this turn if able. Destroy it at the beginning of the next end step if it didn't attack this turn. Activate only before attackers are declared.", ("1", "1"), "B"),
    real("Wall of Test", "{1}", 1, "Creature — Wall", "Defender", ("0", "4"), ""),
    real("Covenant of Minds", "{4}{U}", 5, "Sorcery",
         "Reveal the top three cards of your library. Target opponent may choose to put those cards into your hand. If they don't, put those cards into your graveyard and draw five cards.",
         None, "U"),
    real("Viral Spawning", "{2}{G}", 3, "Sorcery",
         "Create a 3/3 green Phyrexian Beast creature token with toxic 1. (Players dealt combat damage by it also get a poison counter.)\n"
         "Corrupted — As long as an opponent has three or more poison counters and this card is in your graveyard, it has flashback {2}{G}. "
         "(You may cast this card from your graveyard for its flashback cost. Then exile it.)", None, "G"),
    real("Goblin Test", "{R}", 1, "Creature — Goblin", "", ("1", "1"), "R"),
    real("Spin into Myth", "{3}{U}", 4, "Instant",
         "Put target creature on top of its owner's library, then fateseal 2. (To fateseal 2, look at the top two cards of an opponent's library, then put any number of them on the bottom of that player's library and the rest on top in any order.)", None, "U"),
]
NAMES = [c["name"] for c in EXTRA]
EXTRA.append(real("Shivan Dragon", "{4}{R}{R}", 6, "Creature — Dragon", "Flying\n{R}: Shivan Dragon gets +1/+0 until end of turn.", ("5", "5"), "R"))


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database
    from tests.fixtures.cards import fixture_cards

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.mark.parametrize("name", NAMES)
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def answer(s, *picks, limit=60):
    """Resolve everything; decisions are answered from ``picks`` in turn (a list: several options), else with their first options."""
    picks = list(picks)
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None:
            pick = picks.pop(0) if picks else None
            ids = pick if isinstance(pick, list) else [pick] if pick else [o.id for o in d.options][: max(1, d.min_choices)]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=ids)
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return
    raise AssertionError("never settled")


def cast(s, name, targets=(), pid="p1", **kw):
    c = to_hand(s, name, pid)
    act(s, pid, type="cast_spell", card_id=c.id, targets=list(targets), **kw)
    return c


def test_spin_into_myth_fateseals_two(cards):
    s = build(cards, ["Spin into Myth", "Shivan Dragon"])
    elf = put(s, "Shivan Dragon")
    lib = list(s.state.zones["p2:library"])
    mana(s, U=1, C=3)
    cast(s, "Spin into Myth", [elf.id])
    seen = []
    for _ in range(12):
        d = s.state.rules.decision
        if d is None:
            if s.state.zones.get("stack"):
                act(s, s.state.rules.priority, type="pass_priority")
                continue
            break
        assert d.player == "p1"  # only the fatesealing player is asked (and sees the cards)
        ids = [o.id for o in d.options]
        seen.append(d.kind)
        pick = [lib[0]] if lib[0] in ids and "bottom" not in seen else ids[: max(1, d.min_choices)]
        act(s, "p1", type="choose", decision_id=d.id, option_ids=pick)
    assert s.state.cards[elf.id].zone == "p1:library" and s.state.zones["p1:library"][0] == elf.id  # 701.29a, top of its owner's library
    assert sorted(s.state.zones["p2:library"]) == sorted(lib)  # same cards, only reordered
    assert s.state.zones["p2:library"][-1] == lib[0]  # first card went to the bottom
    check(s)


@pytest.mark.parametrize("grant", [True, False])
def test_garruk_minus_seven_lets_blocked_creatures_assign_as_unblocked(cards, grant):
    from tests.test_rules_group_unblocked import finish_combat, start_combat
    from tests.test_rules_shared_damage_choices import table
    from tests.test_rules_wave30m_durations import to_phase

    s = table(cards, ["Garruk, Savage Herald", "Grizzly Bears"])
    to_phase(s, "main1", turn=1)
    bears = put3(s, "Grizzly Bears", "battlefield")
    to_phase(s, "main1", turn=4)  # (no longer summoning sick)
    garruk = put3(s, "Garruk, Savage Herald", "battlefield")
    act(s, "p1", type="set_counter", card_id=garruk.id, kind="loyalty", value=7)
    if grant:
        act(s, "p1", type="activate_ability", card_id=garruk.id, ability=2)
        while s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
    before = set(s.state.cards)
    act(s, "p2", type="create_token", player="p2", token={"name": "Wall", "type_line": "Token Creature — Wall", "power": "0", "toughness": "10"})
    wall = next(c for cid, c in s.state.cards.items() if cid not in before)
    start_combat(s, [bears], [wall])
    assert finish_combat(s) == ([bears.id] if grant else [])  # 510.1c: asked only while the grant lasts
    assert s.state.players["p2"].life == (38 if grant else 40)
    check(s)


def keywords(s, card):
    from app.rules.plan import Plan

    return Plan(s.state, "p1", s.cards, None).ch(s.state.cards[card.id]).keywords


@pytest.mark.parametrize("targeted", [True, False])
def test_storm_windrider_grants_flying_to_the_spells_targets(cards, targeted):
    s = build(cards, ["Storm, Windrider", "Giant Growth", "Grizzly Bears"])
    put(s, "Storm, Windrider")
    bears = put(s, "Grizzly Bears")
    mana(s, G=1)
    if targeted:
        cast(s, "Giant Growth", [bears.id])
        answer(s)
    assert ("flying" in {k.lower() for k in keywords(s, bears)}) is targeted  # 115.9b: only the spell's targets
    check(s)


def test_storm_windrider_flyers_cant_attack_its_controller(cards):
    from app.game.errors import ActionError
    from tests.test_rules_conditionals import until

    s = build(cards, ["Storm, Windrider"], ["Shivan Dragon"])
    put(s, "Storm, Windrider")
    dragon = put(s, "Shivan Dragon", "p2")
    until(s, lambda s: s.state.turn.number >= 2 and s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_attackers")
    assert s.state.turn.active_player == "p2"
    with pytest.raises(ActionError):
        act(s, "p2", type="declare_attackers", attackers=[{"card_id": dragon.id, "target": "p1"}])  # 508.1c


@pytest.mark.parametrize("blocks,legal", [(0, False), (1, False), (2, True)])
def test_blaze_of_glory_forces_the_target_to_block_every_attacker(cards, blocks, legal):
    from app.game.errors import ActionError
    from tests.test_rules_conditionals import until

    s = build(cards, ["Blaze of Glory", "Grizzly Bears", "Grizzly Bears"], ["Grizzly Bears"])
    bears = [c for c in s.state.cards.values() if c.name == "Grizzly Bears" and c.owner == "p1"]
    for c in bears:
        act(s, "p1", type="move", card_ids=[c.id], to={"player": "p1", "zone": "battlefield"})
    wall = put(s, "Grizzly Bears", "p2")
    act(s, "p1", type="set_prefs", full_control=True)
    until(s, lambda s: s.state.turn.number >= 3 and s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_attackers"
          and s.state.turn.active_player == "p1")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": c.id, "target": "p2"} for c in bears])
    mana(s, W=1)
    cast(s, "Blaze of Glory", [wall.id])
    while s.state.zones.get("stack"):
        act(s, s.state.rules.priority, type="pass_priority")
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_blockers")
    pairs = [{"blocker_id": wall.id, "attacker_id": c.id} for c in bears[:blocks]]
    if legal:
        act(s, "p2", type="declare_blockers", blocks=pairs)
        check(s)
    else:
        with pytest.raises(ActionError):
            act(s, "p2", type="declare_blockers", blocks=pairs)


@pytest.mark.parametrize("attack", [True, False])
def test_vivien_stampede_draws_in_the_next_main_phase_for_each_damaged_player(cards, attack):
    from tests.test_rules_conditionals import until

    s = build(cards, ["Vivien's Stampede", "Grizzly Bears"])
    bears = put(s, "Grizzly Bears")
    until(s, lambda s: s.state.turn.number >= 3 and s.state.turn.active_player == "p1" and s.state.turn.phase == "main1")
    mana(s, G=2, C=4)
    cast(s, "Vivien's Stampede")
    answer(s)
    hand = len(s.state.zones["p1:hand"])
    if attack:
        until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_attackers")
        act(s, "p1", type="declare_attackers", attackers=[{"card_id": bears.id, "target": "p2"}])
    until(s, lambda s: s.state.turn.phase == "main2" and not s.state.zones.get("stack") and s.state.rules.decision is None)
    assert len(s.state.zones["p1:hand"]) == hand + (1 if attack else 0)  # one player dealt combat damage / none
    check(s)


CHOKING = real("Choking Vines", "{X}{G}", 1, "Instant",
               "Cast this spell only during the declare blockers step.\n"
               "X target attacking creatures become blocked. Choking Vines deals 1 damage to each of those creatures. "
               "(This spell works on creatures that can't be blocked.)", None, "G")
LETHAL = real("Lethal Exploit", "{1}{B}", 2, "Instant",
              "Target creature gets -2/-2 until end of turn. It gets an additional -1/-1 until end of turn for each modified creature you controlled as you cast this spell. "
              "(Equipment, Auras you control, and counters are modifications.)", None, "B")
BEATDOWN = real("Beastie Beatdown", "{2}{G}", 3, "Sorcery",
                "Choose target creature you control and target creature an opponent controls.\n"
                "Delirium — If there are four or more card types among cards in your graveyard, put two +1/+1 counters on the creature you control.\n"
                "The creature you control deals damage equal to its power to the creature an opponent controls.", None, "G")
AVENGE = real("Avenge", "{4}{W}{W}", 6, "Sorcery",
              "This spell costs {2} less to cast if a player attacked you during their last turn.\n"
              "Destroy all creatures. You gain 1 life for each creature destroyed this way.", None, "W")
SURGE = real("Voltage Surge", "{1}{R}", 2, "Instant",
             "As an additional cost to cast this spell, you may sacrifice an artifact.\n"
             "Voltage Surge deals 2 damage to target creature or planeswalker. If this spell's additional cost was paid, Voltage Surge deals 4 damage instead.", None, "R")
EXTRA.extend([CHOKING, LETHAL, BEATDOWN, AVENGE, SURGE, real("Gy Rock", "{1}", 1, "Artifact", "", None)])
NAMES.extend(["Choking Vines", "Lethal Exploit", "Beastie Beatdown", "Avenge", "Voltage Surge"])


def test_choking_vines_blocks_unblocked_attackers_and_pings_each(cards):
    """509.1h/509.3c: targets become blocked (no damage to the player); 120.3: 1 damage to each of them."""
    from tests.wave53c_kit import (
        combat_step,
        creature,
        in_play,
        pool,
        priority_to,
        sandbox,
        settle,
        swing,
        to_postcombat,
    )

    s = sandbox(cards, "Choking Vines")
    a = creature(s, "p1", "Aaa", "5/5", text="Whenever this creature becomes blocked, you gain 1 life.")
    b = creature(s, "p1", "Bbb", "3/3")
    guard = creature(s, "p2", "Guard", "0/9")
    combat_step(s)
    swing(s, [a, b], [(guard, b)], before=None)

    vines = in_play(s, "Choking Vines")
    act(s, "p1", type="move", card_ids=[vines.id], to={"zone": "hand"})
    pool(s, "p1", G=1, C=2)
    priority_to(s, "p1")
    act(s, "p1", type="cast_spell", card_id=vines.id, targets=[a.id, b.id], target_counts=[2], x_value=2)
    settle(s)  # X=2: b is already blocked, still takes 1
    assert s.state.players["p1"].life == 41 and s.state.cards[a.id].damage == 1 and s.state.cards[b.id].damage == 1
    to_postcombat(s)
    assert s.state.players["p2"].life == 40  # a is blocked, no blocker, no trample: no damage (510.1c)
    check(s)


@pytest.mark.parametrize("modified", [0, 2])
def test_lethal_exploit_counts_modified_creatures_as_cast(cards, modified):
    """601.2i/700.9: -1/-1 more per creature with a counter or attachment when the spell was cast, none for later changes."""
    from tests.test_rules_conditionals import creature, sandbox
    from tests.wave53c_kit import pool, priority_to, settle

    s = sandbox(cards, "Lethal Exploit")
    victim = creature(s, "p2", "Victim", "6/6")
    for i in range(modified):
        c = creature(s, "p1", f"Mod{i}", "1/1")
        act(s, "p1", type="set_counter", card_id=c.id, kind="+1/+1", value=1)
    creature(s, "p1", "Plain", "1/1")
    from tests.wave53c_kit import main_step
    main_step(s)
    spell = next(c for c in s.state.cards.values() if c.name == "Lethal Exploit")
    act(s, "p1", type="move", card_ids=[spell.id], to={"zone": "hand"})
    pool(s, "p1", B=1, C=1)
    priority_to(s, "p1")
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=[victim.id])
    settle(s)
    from app.rules.plan import Plan
    assert Plan(s.state, "p1", s.cards, None).ch(s.state.cards[victim.id]).pt == (4 - modified, 4 - modified)
    check(s)


@pytest.mark.parametrize("delirium", [True, False])
def test_beastie_beatdown_delirium_counters_then_damage(cards, delirium):
    """700.2/608.2c: with four card types in your graveyard the creature gets two counters first, so it deals power 2+2; otherwise just 2."""
    s = build(cards, ["Beastie Beatdown", "Grizzly Bears", "Giant Growth", "Gy Rock", "Shivan Dragon"], ["Shivan Dragon"])
    mine = put(s, "Grizzly Bears")
    theirs = put(s, "Shivan Dragon", "p2")
    for name in ("Shivan Dragon", "Giant Growth", "Gy Rock", "Forest")[: 4 if delirium else 3]:
        c = next(c for c in s.state.cards.values() if c.name == name and c.owner == "p1" and c.zone == "p1:library")
        act(s, "p1", type="move", card_ids=[c.id], to={"player": "p1", "zone": "graveyard"})
    mana(s, G=1, C=2)
    cast(s, "Beastie Beatdown", [mine.id, theirs.id], target_counts=[1, 1])
    answer(s)
    assert s.state.cards[theirs.id].damage == (4 if delirium else 2)
    assert s.state.cards[mine.id].counters.get("+1/+1", 0) == (2 if delirium else 0)
    check(s)


@pytest.mark.parametrize("attacked", [True, False])
def test_avenge_is_cheaper_after_a_player_attacked_you_in_their_last_turn(cards, attacked):
    """508.1 + 601.2f: {2} less only when another player attacked you in their own previous turn; destroyed creatures give 1 life each."""
    from app.game.errors import ActionError
    from tests.test_rules_conditionals import until

    s = build(cards, ["Avenge", "Grizzly Bears"], ["Grizzly Bears"])
    bears = put(s, "Grizzly Bears", "p2")
    until(s, lambda s: s.state.turn.number >= 2 and s.state.turn.active_player == "p2" and s.state.rules.decision is not None
          and s.state.rules.decision.kind == "declare_attackers")
    act(s, "p2", type="declare_attackers", attackers=[{"card_id": bears.id, "target": "p1"}] if attacked else [])
    until(s, lambda s: s.state.turn.number >= 3 and s.state.turn.active_player == "p1" and s.state.turn.phase == "main1")
    mana(s, W=2, C=2)
    life = s.state.players["p1"].life
    if not attacked:
        with pytest.raises(ActionError):
            cast(s, "Avenge")
        return
    cast(s, "Avenge")
    answer(s)
    assert s.state.cards[bears.id].zone == "p2:graveyard" and s.state.players["p1"].life == life + 1  # 1 life per creature destroyed
    check(s)


@pytest.mark.parametrize("paid", [True, False])
def test_voltage_surge_deals_four_only_when_an_artifact_was_sacrificed(cards, paid):
    """601.2b/601.2h: the optional additional cost is announced and paid as it is cast; "instead" (608.2h) swaps 2 for 4 damage."""
    s = build(cards, ["Voltage Surge", "Gy Rock"], ["Shivan Dragon"])
    rock = put(s, "Gy Rock")
    dragon = put(s, "Shivan Dragon", "p2")
    mana(s, R=1, C=1)
    spell = to_hand(s, "Voltage Surge", "p1")
    extra = {"optional_costs": [f"{spell.id}:sacrifice110e"], "cost_choices": [{"component": 0, "cards": [rock.id]}]} if paid else {}
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=[dragon.id], **extra)
    answer(s)
    assert s.state.cards[dragon.id].damage == (4 if paid else 2)
    assert s.state.cards[rock.id].zone == ("p1:graveyard" if paid else "p1:battlefield")
    check(s)


@pytest.mark.parametrize("same_turn", [True, False])
def test_due_respect_taps_permanents_entering_this_turn(cards, same_turn):
    s = build(cards, ["Due Respect", "Grizzly Bears"], ["Grizzly Bears"])
    mana(s, W=1, C=1)
    cast(s, "Due Respect")
    answer(s)
    if not same_turn:
        from tests.test_rules_wave30m_durations import to_phase

        to_phase(s, "main1", turn=3)
    mana(s, G=1, C=1)
    bears = cast(s, "Grizzly Bears")
    answer(s)
    assert s.state.cards[bears.id].zone == "p1:battlefield" and s.state.cards[bears.id].tapped == same_turn
    check(s)


def test_diminishing_returns_each_player_chooses_how_many_to_draw(cards):
    s = build(cards, ["Diminishing Returns", *["Grizzly Bears"] * 20], ["Giant Growth"] * 20)
    for _ in range(2):
        to_hand(s, "Giant Growth", "p2")
    mana(s, U=2, C=2)
    cast(s, "Diminishing Returns")
    answer(s, "3", "7")  # p1 picks 3, p2 picks 7
    hand = lambda p: sum(1 for c in s.state.cards.values() if c.zone == f"{p}:hand")  # noqa: E731
    assert (hand("p1"), hand("p2")) == (3, 7)
    assert sum(1 for c in s.state.cards.values() if c.zone == "p1:exile") == 10
    check(s)


@pytest.mark.parametrize(("mode", "power", "toughness", "kw", "kind"), [(0, 1, 3, "hexproof", "Turtle"), (1, 1, 5, "reach", "Spider"), (2, 3, 3, "trample", "Elephant")])
def test_wild_shape_modes(cards, mode, power, toughness, kw, kind):
    s = build(cards, ["Wild Shape", "Grizzly Bears"])
    bears = put(s, "Grizzly Bears")
    mana(s, G=1, C=1)
    cast(s, "Wild Shape", [bears.id], modes=[mode])
    answer(s)
    from app.rules.plan import Plan

    ch = Plan(s.state, "p1", s.cards, None).ch(s.state.cards[bears.id])
    assert (ch.pt, kw in ch.keywords, set(ch.subtypes)) == ((power, toughness), True, {kind})
    check(s)


@pytest.mark.parametrize("paid", [True, False])
def test_hulks_thunderclap_destroys_only_when_beheld(cards, paid):
    s = build(cards, ["Hulk's Thunderclap", "Gamma Test", "Gy Rock"], ["Shivan Dragon"])
    gamma, rock, dragon = put(s, "Gamma Test"), put(s, "Gy Rock"), put(s, "Shivan Dragon", "p2")
    mana(s, R=1, C=1)
    spell = to_hand(s, "Hulk's Thunderclap", "p1")
    extra = {"optional_costs": [f"{spell.id}:behold"], "cost_choices": [{"component": 0, "cards": [gamma.id]}]} if paid else {}
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=[gamma.id, dragon.id, *([rock.id] if paid else [])], target_counts=[1, 1, 1] if paid else [1, 1], **extra)
    answer(s)
    assert s.state.cards[dragon.id].damage == 3
    assert s.state.cards[rock.id].zone == ("p1:graveyard" if paid else "p1:battlefield")
    check(s)


@pytest.mark.parametrize("life_total", [40, 5])
def test_phyrexian_purge_costs_three_life_per_target(cards, life_total):
    from app.game.errors import ActionError

    s = build(cards, ["Phyrexian Purge"], ["Shivan Dragon", "Grizzly Bears"])
    dragons = [put(s, "Shivan Dragon", "p2"), put(s, "Grizzly Bears", "p2")]
    act(s, "p1", type="set_life", player="p1", value=life_total)
    mana(s, B=2, C=2)
    if life_total < 6:
        with pytest.raises(ActionError):
            cast(s, "Phyrexian Purge", [d.id for d in dragons], target_counts=[2])
        return
    cast(s, "Phyrexian Purge", [d.id for d in dragons], target_counts=[2])
    answer(s)
    assert life(s, "p1") == 34 and all(s.state.cards[d.id].zone == "p2:graveyard" for d in dragons)
    check(s)


@pytest.mark.parametrize("target", ["Grizzly Bears", "Goblin Test"])
def test_callous_oppressor_opponent_names_the_type_it_cant_steal(cards, target):
    """614.12a: an opponent answers the entering choice (the type is public on the permanent); 108.3/613 control: only a creature not of that type can be stolen."""
    from app.game.errors import ActionError
    from tests.test_rules_wave30m_durations import to_phase

    s = build(cards, ["Callous Oppressor"], ["Grizzly Bears", "Goblin Test"])
    mana(s, U=2, C=1)
    op = cast(s, "Callous Oppressor")
    d = s.state.rules.decision
    assert d is not None and d.player == "p2"  # the opponent, not the caster, chooses
    act(s, "p2", type="choose", decision_id=d.id, option_ids=["Bear"])
    answer(s)
    assert "Bear" in s.state.cards[op.id].choices.values()
    bears, goblin = put(s, "Grizzly Bears", "p2"), put(s, "Goblin Test", "p2")
    to_phase(s, "main1", turn=3)
    victim = bears if target == "Grizzly Bears" else goblin
    if target == "Grizzly Bears":
        with pytest.raises(ActionError):
            act(s, "p1", type="activate_ability", card_id=op.id, ability=2, targets=[victim.id])
        return
    act(s, "p1", type="activate_ability", card_id=op.id, ability=2, targets=[victim.id])
    answer(s)
    assert s.state.cards[victim.id].controller == "p1"
    check(s)


@pytest.mark.parametrize(("kind", "size"), [("Bear", 2), ("Human", 1), ("Goblin", 1), ("Elf", 0)])
def test_caller_of_the_hunt_counts_the_type_chosen_as_it_was_cast(cards, kind, size):
    """601.2b the type is chosen as an additional cost and kept on the permanent (public "Chosen creature type"); its P/T counts creatures of that type (two Bears, a Goblin, itself a Human)."""
    from app.rules.plan import Plan

    s = build(cards, ["Caller of the Hunt"], ["Grizzly Bears", "Bear Cub", "Goblin Test"])
    put(s, "Grizzly Bears", "p2")
    put(s, "Bear Cub", "p2")
    put(s, "Goblin Test", "p2")
    c = to_hand(s, "Caller of the Hunt")
    mana(s, G=1, C=2)
    act(s, "p1", type="cast_spell", card_id=c.id)
    d = s.state.rules.decision
    assert d is not None and d.player == "p1" and "Bear" in [o.id for o in d.options]
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[kind])
    answer(s)
    if size == 0:  # 704.5f: a 0/0 dies
        assert s.state.cards[c.id].zone == "p1:graveyard"
        return
    assert s.state.cards[c.id].zone == "p1:battlefield" and s.state.cards[c.id].choices.get("Chosen creature type") == kind
    assert Plan(s.state, "p1", s.cards, None).ch(s.state.cards[c.id]).pt == (size, size)
    check(s)


@pytest.mark.parametrize(("chosen", "dies"), [("Shivan Dragon", True), ("Goblin Test", False)])
def test_close_encounter_uses_the_power_of_the_creature_chosen_as_cast(cards, chosen, dies):
    """601.2b/120.3: the creature is chosen as an additional cost (only creatures you control or warped cards you own in exile); damage equals its power."""
    s = build(cards, ["Close Encounter", "Shivan Dragon", "Goblin Test"], ["Grizzly Bears", "Shivan Dragon"])
    dragon, goblin, bears = put(s, "Shivan Dragon"), put(s, "Goblin Test"), put(s, "Grizzly Bears", "p2")
    mana(s, R=1, C=1)
    c = to_hand(s, "Close Encounter")
    act(s, "p1", type="cast_spell", card_id=c.id, targets=[bears.id])
    d = s.state.rules.decision
    assert d is not None and d.player == "p1" and sorted(o.id for o in d.options) == sorted([dragon.id, goblin.id])  # not the opponent's creature
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[dragon.id if chosen == "Shivan Dragon" else goblin.id])
    answer(s)
    assert (s.state.cards[bears.id].zone == "p2:graveyard") == dies
    check(s)


@pytest.mark.parametrize("opponent_agrees", [True, False])
def test_covenant_of_minds_the_opponent_decides_where_the_revealed_cards_go(cards, opponent_agrees):
    """608.2d: the target opponent alone answers; yes: the three revealed cards go to your hand; no: they go to your graveyard and you draw five."""
    s = build(cards, ["Covenant of Minds", *["Grizzly Bears"] * 12])
    spell = to_hand(s, "Covenant of Minds")
    top = list(s.state.zones["p1:library"][:3])  # the top of the library is index 0
    hand0, gy0 = len(s.state.zones["p1:hand"]) - 1, len(s.state.zones.get("p1:graveyard", []))
    mana(s, U=1, C=4)
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=["p2"])
    d = s.state.rules.decision
    for _ in range(5):
        if d is not None and d.player == "p2":
            break
        act(s, s.state.rules.priority, type="pass_priority")
        d = s.state.rules.decision
    assert d is not None and d.player == "p2"  # the opponent, not the caster, answers
    act(s, "p2", type="choose", decision_id=d.id, option_ids=["pay" if opponent_agrees else "decline"])
    answer(s)
    hand, gy = s.state.zones["p1:hand"], s.state.zones.get("p1:graveyard", [])
    if opponent_agrees:
        assert all(c in hand for c in top) and len(hand) == hand0 + 3
    else:
        assert all(c in gy for c in top) and len(gy) == gy0 + 4 and len(hand) == hand0 + 5  # + the sorcery itself
    check(s)


@pytest.mark.parametrize("poison", [3, 2])
def test_viral_spawning_has_flashback_only_while_an_opponent_is_corrupted(cards, poison):
    """702.34a/122.1f: from the graveyard it can be cast for {2}{G} only with an opponent at 3+ poison counters; then it is exiled instead of going back."""
    from app.game.errors import ActionError

    s = build(cards, ["Viral Spawning"])
    c = to_hand(s, "Viral Spawning")
    act(s, "p1", type="move", card_ids=[c.id], to={"player": "p1", "zone": "graveyard"})
    act(s, "p2", type="set_resource", player="p2", key="poison", value=poison)
    mana(s, G=1, C=2)
    if poison < 3:
        with pytest.raises(ActionError):
            act(s, "p1", type="cast_spell", card_id=c.id)
        return
    act(s, "p1", type="cast_spell", card_id=c.id)
    answer(s)
    assert s.state.cards[c.id].zone == "p1:exile"
    assert any(x.name.endswith("Beast Token") or "Beast" in x.name for x in s.state.cards.values() if x.zone == "p1:battlefield")
    check(s)


@pytest.mark.parametrize("warped", [True, False])
def test_close_encounter_may_choose_a_warped_card_in_exile_but_not_another_exiled_card(cards, warped):
    """601.2b/702.185a: a warped creature card you own in exile is a legal choice (damage = its power, 608.2h); an exiled card that was not warped is not offered."""
    import secrets

    from app.game.rules_state import Permission

    s = build(cards, ["Close Encounter", "Shivan Dragon", "Goblin Test"], ["Grizzly Bears"])
    dragon, goblin, bears = (to_hand(s, "Shivan Dragon"), put(s, "Goblin Test"), put(s, "Grizzly Bears", "p2"))
    act(s, "p1", type="move", card_ids=[dragon.id], to={"player": "p1", "zone": "exile"})
    if warped:
        s.state.rules.permissions.append(Permission(
            id=secrets.token_hex(4), player="p1", cast=True, zone="any", object_id=dragon.id, card=dragon.id, until="permanent",
            turn=s.state.turn.number, after_turn=s.state.turn.number, label="Shivan Dragon: cast it from exile (warped)"))
    mana(s, R=1, C=1)
    c = to_hand(s, "Close Encounter")
    act(s, "p1", type="cast_spell", card_id=c.id, targets=[bears.id])
    d = s.state.rules.decision
    assert d is not None and d.player == "p1" and sorted(o.id for o in d.options) == sorted([goblin.id, dragon.id] if warped else [goblin.id])
    if warped:
        act(s, "p1", type="choose", decision_id=d.id, option_ids=[dragon.id])
        answer(s)
        assert s.state.cards[bears.id].zone == "p2:graveyard"  # 5 damage from the exiled Dragon's power
        check(s)


def test_callous_oppressor_with_two_opponents_the_controller_picks_who_names_the_type(cards):
    """614.12a: "an opponent chooses" with 2+ opponents: the controller picks the opponent, then that opponent (not the others) names the type."""
    from tests.test_rules_wave33d_turn_state import build3

    s = build3(cards, ["Callous Oppressor"])
    mana(s, U=2, C=1)
    op = cast(s, "Callous Oppressor")
    d = s.state.rules.decision
    assert d is not None and d.player == "p1" and sorted(o.id for o in d.options) == ["p2", "p3"]
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["p3"])
    d = s.state.rules.decision
    assert d is not None and d.player == "p3"
    act(s, "p3", type="choose", decision_id=d.id, option_ids=["Goblin"])
    answer(s)
    assert "Goblin" in s.state.cards[op.id].choices.values()
    check(s)


@pytest.mark.parametrize("times", [0, 1, 2])
def test_thrill_kill_disciple_squad_discards_a_card_for_each_copy(cards, times):
    """702.157a: Squad—{1}, Discard a card. Each payment costs {1} and a discard (601.2h) and makes one token copy as the creature enters."""
    s = build(cards, ["Thrill-Kill Disciple", "Grizzly Bears", "Goblin Test"])
    to_hand(s, "Grizzly Bears"), to_hand(s, "Goblin Test")
    c = to_hand(s, "Thrill-Kill Disciple")
    mana(s, R=1, C=2 + times)
    act(s, "p1", type="cast_spell", card_id=c.id, kicker=times)
    answer(s)
    names = [x.name for x in s.state.cards.values() if x.zone == "p1:battlefield"]
    assert names.count("Thrill-Kill Disciple") == 1 + times
    assert sum(1 for x in s.state.cards.values() if x.zone == "p1:graveyard") == times
    check(s)


def test_thrill_kill_disciple_squad_needs_a_card_to_discard_for_each_payment(cards):
    """601.2h: two payments need two other cards in hand; one card is not enough."""
    from app.game.errors import ActionError

    s = build(cards, ["Thrill-Kill Disciple", "Grizzly Bears"])
    to_hand(s, "Grizzly Bears")
    c = to_hand(s, "Thrill-Kill Disciple")
    mana(s, R=1, C=4)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=c.id, kicker=2)
    assert s.state.cards[c.id].zone == "p1:hand"


@pytest.mark.parametrize("has_land", [True, False])
def test_lunar_hatchling_escape_also_exiles_a_land_you_control(cards, has_land):
    """702.138a: Escape—{4}{G}{U}, Exile a land you control, Exile five other cards from your graveyard: the land is exiled with the five cards (601.2h); no land, no cast."""
    from app.game.errors import ActionError

    s = build(cards, ["Lunar Hatchling", "Grizzly Bears", "Llanowar Elves", "Goblin Test", "Opt", "Giant Growth"])
    names = ["Lunar Hatchling", "Grizzly Bears", "Llanowar Elves", "Goblin Test", "Opt", "Giant Growth"]
    for n in names:
        act(s, "p1", type="move", card_ids=[card_named(s, n).id], to={"player": "p1", "zone": "graveyard"})
    if has_land:
        put(s, "Forest")
    mana(s, G=1, U=1, C=4)
    hatchling = card_named(s, "Lunar Hatchling")
    if not has_land:
        with pytest.raises(ActionError):
            act(s, "p1", type="cast_spell", card_id=hatchling.id)
        assert s.state.cards[hatchling.id].zone == "p1:graveyard"
        return
    act(s, "p1", type="cast_spell", card_id=hatchling.id)
    answer(s)
    assert s.state.cards[hatchling.id].zone == "p1:battlefield"
    assert len(s.state.zones["p1:exile"]) == 6 and sum(1 for x in s.state.cards.values() if x.zone == "p1:battlefield" and x.name == "Forest") == 0
    check(s)


def _imp_table(cards, imp, mine=()):
    """The imp is under Alice's control since turn 1; Bob's Bears and Wall are on the battlefield at turn 3 (so they have been Bob's since turn 4 began)."""
    from tests.test_rules_wave30m_durations import to_phase

    s = build(cards, [imp, *mine], ["Grizzly Bears", "Wall of Test"], forests=30, islands=30)
    i = put(s, imp)
    to_phase(s, "main1", turn=3)
    return s, i, put(s, "Grizzly Bears", "p2"), put(s, "Wall of Test", "p2")


def _bobs_beginning_of_combat(s):
    from tests.test_rules_wave30m_durations import stops, to_phase

    stops(s, "begin_combat")
    to_phase(s, "begin_combat", turn=4)
    for _ in range(3):
        if s.state.rules.priority == "p1":
            return
        act(s, s.state.rules.priority, type="pass_priority")


def _to_phase_stop(s, phase, turn):
    from tests.test_rules_conditionals import until

    if phase == "declare_attackers":  # (stop at the question itself: the helper would answer it with no attackers)
        for _ in range(40):
            d = s.state.rules.decision
            if d is not None and d.kind == "declare_attackers":
                return
            act(s, s.state.rules.priority, type="pass_priority")
        raise AssertionError("no attackers were asked for")
    until(s, lambda s: s.state.turn.number == turn and s.state.turn.phase == phase and s.state.rules.decision is None)


@pytest.mark.parametrize("attacks", [True, False])
def test_nettling_imp_forces_the_attack_and_destroys_the_creature_that_did_not(cards, attacks):
    """508.1/603.7: the target must attack if able; the end-step trigger destroys it only if it didn't attack (a tapped creature is unable)."""
    from app.game.errors import ActionError
    from tests.test_rules_conditionals import settle

    s, imp, bears, wall = _imp_table(cards, "Nettling Imp")
    _bobs_beginning_of_combat(s)
    act(s, "p1", type="activate_ability", card_id=imp.id, ability=0, targets=[bears.id])
    settle(s)
    if attacks:
        _to_phase_stop(s, "declare_attackers", 4)
        with pytest.raises(ActionError):
            act(s, "p2", type="declare_attackers", attackers=[])
        act(s, "p2", type="declare_attackers", attackers=[{"card_id": bears.id, "target": "p1"}])
    else:
        act(s, "p2", type="tap", card_ids=[bears.id])
    _to_phase_stop(s, "cleanup" if False else "end", 4)
    settle(s)
    assert (s.state.cards[bears.id].zone == "p2:battlefield") == attacks
    assert s.state.cards[wall.id].zone == "p2:battlefield"
    check(s)


def test_nettling_imp_targets_only_non_walls_the_active_player_controlled_since_the_turn_began(cards):
    """Wall: not a legal target; a creature that entered this turn: not legal; the imp's own side (not the active player): not legal; own turn: not activatable."""
    from app.game.errors import ActionError
    from tests.test_rules_wave30m_durations import to_phase

    s, imp, bears, wall = _imp_table(cards, "Nettling Imp", ["Grizzly Bears"])
    mine = put(s, "Grizzly Bears")
    _bobs_beginning_of_combat(s)
    fresh = card_named(s, "Grizzly Bears", "p2")
    for bad in (wall, mine):
        with pytest.raises(ActionError):
            act(s, "p1", type="activate_ability", card_id=imp.id, ability=0, targets=[bad.id])
    assert fresh.id == bears.id
    to_phase(s, "main1", turn=5)
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=imp.id, ability=0, targets=[mine.id])  # (it is Alice's own turn)


@pytest.mark.parametrize("attacks", [True, False])
def test_norritt_works_on_your_own_turn_too(cards, attacks):
    """Norritt has no "during an opponent's turn": the active player may be its controller. Same attack requirement and end-step destroy."""
    from tests.test_rules_conditionals import settle
    from tests.test_rules_wave30m_durations import to_phase

    s = build(cards, ["Norritt", "Grizzly Bears"], forests=30, islands=30)
    n, bears = put(s, "Norritt"), put(s, "Grizzly Bears")
    from tests.test_rules_wave30m_durations import stops

    stops(s, "end")
    to_phase(s, "main1", turn=3)
    act(s, "p1", type="activate_ability", card_id=n.id, ability=1, targets=[bears.id])
    settle(s)
    if attacks:
        _to_phase_stop(s, "declare_attackers", 3)
        act(s, "p1", type="declare_attackers", attackers=[{"card_id": bears.id, "target": "p2"}])
    else:
        act(s, "p1", type="tap", card_ids=[bears.id])
    _to_phase_stop(s, "end", 3)
    settle(s)
    assert (s.state.cards[bears.id].zone == "p1:battlefield") == attacks
    check(s)

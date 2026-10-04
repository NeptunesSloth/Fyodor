"""Wave 19A: the static_other long tail, first slice (CR 2026-09-25).

* 611.2c / 613.4b / 613.1f: "Until end of turn, creatures target player controls lose all abilities and have base power and toughness
  0/2" (Sudden Spoiling), "each creature target player controls loses all abilities and becomes a blue Frog …" (Polymorphist's Jest),
  "Until your next turn, creatures target player controls have base power and toughness 1/1" (Mass Diminish), "All lands you control become
  2/2 Elemental creatures … They're still lands." (Sylvan Awakening): the creatures / lands as the effect resolves, locked in.
* 508.1c: "This creature can't attack a player it has already attacked this turn." (Port Razer).
* 500.7 / 603.7: "Take an extra turn after this one. At the beginning of that turn's end step, you lose the game." (Final Fortune).
* 701.x choose + count: "Choose a creature type. Draw a card for each permanent you control of that type." (Distant Melody).
* 614.1d / 502.3: "Traxos enters tapped and doesn't untap during your untap step."
* 606.3: Oath of Teferi (twice each turn), Teferi, Master of Time (any player's turn at instant speed).
* 118.14 / 609.4b: Oath of Nissa, Vizier of the Menagerie (how the mana of some spells may be spent).

Real Oracle text; each scenario replays the history and survives a save/load round trip."""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.game.session import GameSession
from app.game.state import GameState
from app.rules import casting, coverage
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, zone
from tests.test_rules_conditionals import build, creature, on_field, settle, to_hand, until
from tests.test_rules_effects import mana, replay_matches


def real(name, cost, cmc, types, text, pt=None, colors="", **more):
    extra = {"power": pt[0], "toughness": pt[1]} if pt else {}
    return card(name, set_code="tst", number=f"19A-{name[:6]}", mana_cost=cost, cmc=float(cmc), type_line=types, oracle_text=text,
                colors=list(colors), color_identity=list(colors), **extra, **more)


EXTRA = [
    real('Sudden Spoiling', '{1}{B}{B}', 3, 'Instant',
         "Split second (As long as this spell is on the stack, players can't cast spells or activate abilities that aren't mana abilities.)\nUntil end of turn, creatures target player controls lose all abilities and have base power and toughness 0/2.",
         None, 'B'),
    real("Polymorphist's Jest", '{1}{U}{U}', 3, 'Instant',
         'Until end of turn, each creature target player controls loses all abilities and becomes a blue Frog with base power and toughness 1/1.',
         None, 'U'),
    real('Mass Diminish', '{1}{U}', 2, 'Sorcery',
         'Until your next turn, creatures target player controls have base power and toughness 1/1.\nFlashback {3}{U} (You may cast this card from your graveyard for its flashback cost. Then exile it.)',
         None, 'U'),
    real('Sylvan Awakening', '{2}{G}', 3, 'Sorcery',
         "Until your next turn, all lands you control become 2/2 Elemental creatures with reach, indestructible, and haste. They're still lands.",
         None, 'G'),
    real('Port Razer', '{3}{R}{R}', 5, 'Creature — Orc Pirate',
         "Whenever this creature deals combat damage to a player, untap each creature you control. After this phase, there is an additional combat phase.\nThis creature can't attack a player it has already attacked this turn.",
         ('4', '4'), 'R'),
    real('Final Fortune', '{R}{R}', 2, 'Instant',
         "Take an extra turn after this one. At the beginning of that turn's end step, you lose the game.",
         None, 'R'),
    real('Distant Melody', '{3}{U}', 4, 'Sorcery',
         'Choose a creature type. Draw a card for each permanent you control of that type.',
         None, 'U'),
    real('Traxos, Scourge of Kroog', '{4}', 4, 'Legendary Artifact Creature — Dragon Construct',
         "Trample\nTraxos enters tapped and doesn't untap during your untap step.\nWhenever you cast a historic spell, untap Traxos. (Artifacts, legendaries, and Sagas are historic.)",
         ('7', '7'), ''),
    real('Oath of Teferi', '{3}{W}{U}', 5, 'Legendary Enchantment',
         "When Oath of Teferi enters, exile another target permanent you control. Return it to the battlefield under its owner's control at the beginning of the next end step.\nYou may activate the loyalty abilities of planeswalkers you control twice each turn rather than only once.",
         None, 'UW'),
    real('Oath of Nissa', '{G}', 1, 'Legendary Enchantment',
         'When Oath of Nissa enters, look at the top three cards of your library. You may reveal a creature, land, or planeswalker card from among them and put it into your hand. Put the rest on the bottom of your library in any order.\nYou may spend mana as though it were mana of any color to cast planeswalker spells.',
         None, 'G'),
    real('Vizier of the Menagerie', '{3}{G}', 4, 'Creature — Snake Cleric',
         'You may look at the top card of your library any time.\nYou may cast creature spells from the top of your library.\nYou can spend mana of any type to cast creature spells.',
         ('3', '4'), 'G'),
    real('Teferi, Master of Time', '{2}{U}{U}', 4, 'Legendary Planeswalker — Teferi',
         "You may activate loyalty abilities of Teferi on any player's turn any time you could cast an instant.\n+1: Draw a card, then discard a card.\n−3: Target creature you don't control phases out. (Treat it and anything attached to it as though they don't exist until its controller's next turn.)\n−10: Take two extra turns after this one.",
         None, 'U', loyalty="3"),
]
FULL = [e["name"] for e in EXTRA]


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


def now(s, c, pid="p1"):
    return Plan(s.state, pid, s.cards, None).ch(s.state.cards[c.id])


def cast(s, name, *targets, **m):
    c = to_hand(s, name)
    mana(s, **m)
    act(s, "p1", type="cast_spell", card_id=c.id, targets=list(targets))
    settle(s)
    return c


@pytest.mark.parametrize("name", FULL)
def test_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def test_their_creatures_lose_abilities_and_get_base_pt_and_mine_are_untouched(cards):
    s = build(cards, "Sudden Spoiling", "Polymorphist's Jest", "Mass Diminish")
    flyer = creature(s, "p2", "Flyer", "3/3", text="Flying")
    other = creature(s, "p2", "Other", "4/4")
    mine = creature(s, "p1", "Mine", "2/2", text="Flying")
    cast(s, "Sudden Spoiling", "p2", B=3)
    assert now(s, flyer).pt == (0, 2) and "flying" not in now(s, flyer).keywords and now(s, other).pt == (0, 2)
    assert now(s, mine).pt == (2, 2) and "flying" in now(s, mine).keywords
    late = creature(s, "p2", "Late", "5/5")
    assert now(s, late).pt == (5, 5)  # (611.2c: the creatures as it resolved)
    cast(s, "Polymorphist's Jest", "p2", U=3)
    assert now(s, other).subtypes == {"Frog"} and now(s, other).colors == {"U"} and now(s, other).pt == (1, 1)
    assert now(s, mine).subtypes == {"Test"}
    cast(s, "Mass Diminish", "p2", U=2)
    assert now(s, late).pt == (1, 1)
    roundtrip(s)
    until(s, lambda s: s.state.turn.number == 2 and s.state.turn.phase == "main1")  # (until end of turn / until your next turn)
    assert now(s, flyer, "p2").pt == (1, 1) and "flying" in now(s, flyer, "p2").keywords and now(s, late, "p2").pt == (1, 1)
    until(s, lambda s: s.state.turn.number == 3 and s.state.turn.phase == "main1")
    assert now(s, late).pt == (5, 5)
    roundtrip(s)


def test_a_group_of_lands_becomes_creatures_and_is_still_lands(cards):
    s = build(cards, "Sylvan Awakening")
    forest = on_field(s, "Forest")
    cast(s, "Sylvan Awakening", G=3)
    ch = now(s, forest)
    assert {"Land", "Creature"} <= ch.types and ch.pt == (2, 2) and {"reach", "indestructible", "haste"} <= set(ch.keywords)
    assert "Elemental" in ch.subtypes and "Forest" in ch.subtypes
    roundtrip(s)


def test_port_razer_can_not_attack_a_player_it_already_attacked(cards):
    s = build(cards, "Port Razer")
    razer = on_field(s, "Port Razer")
    s.state.rules.controlled_since[razer.id].turn = 0
    while s.state.rules.decision is None or s.state.rules.decision.kind != "declare_attackers":
        act(s, s.state.rules.priority, type="pass_priority")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": razer.id, "target": "p2"}])
    for _ in range(40):  # (blockers: none; combat damage; the additional combat after this phase)
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_attackers":
            break
        if d is not None and d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
        elif d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    assert s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_attackers"
    with pytest.raises(ActionError):
        act(s, "p1", type="declare_attackers", attackers=[{"card_id": razer.id, "target": "p2"}])
    roundtrip(s)


def test_final_fortune_loses_the_game_at_the_end_step_of_the_extra_turn(cards):
    s = build(cards, "Final Fortune")
    cast(s, "Final Fortune", R=2)
    until(s, lambda s: s.state.turn.number == 2 and s.state.turn.phase == "main1")
    assert s.state.turn.active_player == "p1" and "p1" not in s.state.rules.lost  # (this turn's end step: nothing happened)
    roundtrip(s)
    until(s, lambda s: "p1" in s.state.rules.lost or s.state.turn.number > 2)
    assert "p1" in s.state.rules.lost and s.state.turn.number == 2
    roundtrip(s)


def test_distant_melody_draws_for_the_permanents_of_the_chosen_type(cards):
    s = build(cards, "Distant Melody", "Grizzly Bears", "Grizzly Bears", "Grizzly Bears", "Grizzly Bears")
    for n in ("Elf A", "Elf B"):
        creature(s, "p1", n, "1/1", type_line="Token Creature — Elf")
    creature(s, "p1", "Goblin", "1/1", type_line="Token Creature — Goblin")
    c = to_hand(s, "Distant Melody")
    mana(s, U=1, C=3)
    before = len(zone(s.state, "p1", "hand"))
    act(s, "p1", type="cast_spell", card_id=c.id)
    for _ in range(10):
        d = s.state.rules.decision
        if d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[next(o.id for o in d.options if o.label == "Elf")])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    assert len(zone(s.state, "p1", "hand")) == before - 1 + 2
    roundtrip(s)


def test_traxos_enters_tapped_and_does_not_untap(cards):
    s = build(cards, "Traxos, Scourge of Kroog")
    t = to_hand(s, "Traxos, Scourge of Kroog")
    mana(s, C=4)
    act(s, "p1", type="cast_spell", card_id=t.id)
    settle(s)
    assert s.state.cards[t.id].zone == "p1:battlefield" and s.state.cards[t.id].tapped
    until(s, lambda s: s.state.turn.number == 3 and s.state.turn.phase == "main1")
    assert s.state.cards[t.id].tapped
    roundtrip(s)


def activate(s, c, i):
    act(s, "p1", type="activate_ability", card_id=c.id, ability=i)
    settle(s)


def test_oath_of_teferi_allows_two_loyalty_abilities_each_turn(cards):
    s = build(cards, "Oath of Teferi", "Teferi, Master of Time", "Forest", "Forest", "Forest")
    teferi = on_field(s, "Teferi, Master of Time")
    plus = next(i for i, a in enumerate(s.cards.resolve("Teferi, Master of Time")["oracle_text"].split("\n")) if a.startswith("+1"))
    activate(s, teferi, plus)
    with pytest.raises(ActionError):  # (once: 606.3)
        activate(s, teferi, plus)
    on_field(s, "Oath of Teferi")
    settle(s)
    activate(s, teferi, plus)
    with pytest.raises(ActionError):
        activate(s, teferi, plus)
    roundtrip(s)


def test_teferi_master_of_time_activates_on_any_players_turn(cards):
    s = build(cards, "Teferi, Master of Time", "Forest", "Forest", "Forest")
    teferi = on_field(s, "Teferi, Master of Time")
    s.state.cards[teferi.id].counters["loyalty"] = 3
    plus = 1
    for pid in ("p1", "p2"):
        act(s, pid, type="set_prefs", response="on")  # (a response window for each player in every step)
    until(s, lambda s: s.state.turn.number == 2 and s.state.turn.phase == "main1")
    act(s, "p2", type="pass_priority")
    assert s.state.turn.active_player == "p2" and s.state.rules.priority == "p1"
    activate(s, teferi, plus)
    assert s.state.cards[teferi.id].counters.get("loyalty") == 4
    roundtrip(s)


def test_oath_of_nissa_and_vizier_widen_how_some_spells_are_paid(cards):
    s = build(cards, "Oath of Nissa", "Teferi, Master of Time", "Grizzly Bears", "Vizier of the Menagerie")
    tef = to_hand(s, "Teferi, Master of Time")
    bears = to_hand(s, "Grizzly Bears")
    mana(s, R=4)
    assert not casting.castable(s.state, "p1", tef, s.cards) and not casting.castable(s.state, "p1", bears, s.cards)
    on_field(s, "Oath of Nissa")
    settle(s)
    assert casting.castable(s.state, "p1", tef, s.cards) and not casting.castable(s.state, "p1", bears, s.cards)
    on_field(s, "Vizier of the Menagerie")
    assert casting.castable(s.state, "p1", bears, s.cards)
    act(s, "p1", type="cast_spell", card_id=tef.id)
    settle(s)
    assert s.state.cards[tef.id].zone == "p1:battlefield"
    roundtrip(s)

"""-- planechase statics (wave A) -- static abilities and the collector-only triggers of a face-up plane (CR 311.4, 113.6p, 901.7;
app/rules/planar_statics.py), each proven on its real Oracle text with the face-up plane as the rules object (its "you" is the planar
controller, 311.5), with automation off too where a collector was taught the plane (nothing happens by itself)."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.cards.importer import build_database
from app.config import Settings
from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from app.game.state import GameSettings, PlanarCard
from app.rules import coverage
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, deck, enable
from tests.test_planechase import script
from tests.test_rules_conditionals import settle, to_turn
from tests.test_rules_planechase_plumbing import PLANES as BASE
from tests.test_rules_wave12a_counters_keywords import real
from tests.wave9c_kit import check, life, mana, put

# Oracle text exactly as in the card database (data/cards.sqlite)
PLANES = {
    'Stormcage Containment Facility': ('Plane — Unknown Planet', "Each creature card in your graveyard has escape. The escape cost is equal to the card's mana cost plus exile three other cards from your graveyard. (You may cast cards from your graveyard for their escape cost.)\nWhenever chaos ensues, detain target creature an opponent controls. (Until your next turn, that creature can't attack or block and its activated abilities can't be activated.)"),  # noqa: E501
    'Bloodhill Bastion': ('Plane — Equilor', 'Whenever a creature enters, it gains double strike and haste until end of turn.\nWhenever chaos ensues, exile target nontoken creature you control, then return it to the battlefield under your control.'),  # noqa: E501
    'Immersturm': ('Plane — Valla', "Whenever a creature enters, that creature's controller may have it deal damage equal to its power to any target of their choice.\nWhenever chaos ensues, exile target creature, then return it to the battlefield under its owner's control."),  # noqa: E501
    'Aretopolis': ('Plane — Kephalai', 'When you planeswalk to Aretopolis and at the beginning of your upkeep, put a scroll counter on Aretopolis, then you gain life equal to the number of scroll counters on it.\nWhen Aretopolis has ten or more scroll counters on it, planeswalk.\nWhenever chaos ensues, put a scroll counter on Aretopolis, then draw cards equal to the number of scroll counters on it.'),  # noqa: E501
    'The Lux Foundation Library': ('Plane — The Library', 'Players have no maximum hand size.\nWhenever a creature you control deals combat damage to a player, you may draw a card.\nWhenever chaos ensues, put a shadow counter on target creature. (A creature with shadow can block or be blocked by only creatures with shadow.)'),  # noqa: E501
    'Stronghold Furnace': ('Plane — Rath', 'If a source would deal damage to a permanent or player, it deals double that damage instead.\nWhenever chaos ensues, Stronghold Furnace deals 1 damage to any target.'),  # noqa: E501
    'Selesnya Loft Gardens': ('Plane — Ravnica', 'If an effect would create one or more tokens, it creates twice that many of those tokens instead.\nIf an effect would put one or more counters on a permanent, it puts twice that many of those counters on that permanent instead.\nWhenever chaos ensues, until end of turn, whenever you tap a land for mana, add one mana of any type that land produced.'),  # noqa: E501
    'The Eon Fog': ('Plane — Equilor', 'Players skip their untap steps.\nWhenever chaos ensues, untap all permanents you control.'),
    'Astral Arena': ('Plane — Kolbahan', 'No more than one creature can attack each combat.\nNo more than one creature can block each combat.\nWhenever chaos ensues, Astral Arena deals 2 damage to each creature.'),  # noqa: E501
    'Mycosynthwave': ('Plane — Secret Lair', "All permanents are artifacts in addition to their other types.\nAll cards that aren't on the battlefield, spells, and permanents are colorless.\nPlayers may spend mana as though it were mana of any color.\nWhenever chaos ensues, the next spell you cast this turn has affinity for artifacts."),  # noqa: E501
    'The Cave of Skulls': ('Plane — Earth', "Each creature card in your graveyard has scavenge. The scavenge cost is equal to its mana cost. (Exile a creature card from your graveyard and pay its mana cost: Put a number of +1/+1 counters equal to that card's power on target creature. Scavenge only as a sorcery.)\nWhenever chaos ensues, create two 1/1 white Warrior creature tokens."),  # noqa: E501
    'Akoum': ('Plane — Zendikar', "Players may cast enchantment spells as though they had flash.\nWhenever chaos ensues, destroy target creature that isn't enchanted."),  # noqa: E501
    'Onakke Catacomb': ('Plane — Shandalar', 'All creatures are black and have deathtouch.\nWhenever chaos ensues, creatures you control get +1/+0 and gain first strike until end of turn.'),  # noqa: E501
}
FULL = [*PLANES, "Eloren Wilds", "The Western Cloud", "Kessig"]  # (their chaos lines: wave B, app/rules/planar_chaos.py)
# lines read now on planes still PARTIAL for another line (a chaos ability, or a static that needs grammar)
LINES = {
    'Skybreen': ('Plane — Kaldheim', "Players play with the top card of their libraries revealed.\nSpells that share a card type with the top card of a library can't be cast.\nWhenever chaos ensues, target player loses life equal to the number of cards in their hand."),  # noqa: E501
    'Eloren Wilds': ('Plane — Shandalar', "Whenever a player taps a permanent for mana, that player adds one mana of any type that permanent produced.\nWhenever chaos ensues, target player can't cast spells until a player planeswalks."),  # noqa: E501
    'The Western Cloud': ('Plane — Gobakhan', 'Prevent all damage that would be dealt to creatures and planeswalkers you control.\nWhenever chaos ensues, create three tapped Treasure tokens. They each deal 1 damage to each creature and each planeswalker.'),  # noqa: E501
    "The Doctor's Childhood Barn": ('Plane — Gallifrey', "Creatures enter tapped.\nWhenever chaos ensues, for each opponent, choose up to one target nonland permanent that opponent controls. Untap those permanents. They phase out. They can't phase in for as long as The Doctor's Childhood Barn remains face up. When a player planeswalks, those permanents phase in."),  # noqa: E501
    'The Fertile Lands of Saulvinia': ('Plane — Antausia', 'Whenever a player taps a land for mana, that player adds one mana of any type that land produced.\nWhenever chaos ensues, reveal cards from the top of your planar deck until you reveal a plane card. Chaos ensues on that plane. Then put all cards revealed this way on the bottom of your planar deck in any order.'),  # noqa: E501
    'Bicycle Rack': ('Plane — Amsterdam', 'Cards in each player\'s hand have cycling {2}.\nChaos: Until end of turn, creatures you control have "This creature gets +1/+1 for each card you\'ve discarded this turn."'),  # noqa: E501
    'Stairs to Infinity': ('Plane — Xerex', 'Players have no maximum hand size.\nWhenever you roll the planar die, draw a card.\nWhenever chaos ensues, reveal the top card of your planar deck. You may put it on the bottom of your planar deck.'),  # noqa: E501
    'Windriddle Palaces': ('Plane — Belenon', "Players play with the top card of their libraries revealed.\nYou may play lands and cast spells from the top of any player's library.\nWhenever chaos ensues, each player mills a card."),  # noqa: E501
    'Event Horizon': ('Plane — Blind Eternities', 'Nonbasic lands are Wastes.\nWhenever you tap a permanent for {C}, add an additional {C}.\nWhenever chaos ensues, choose one —\n• Draw four cards.\n• Destroy target permanent.\n• You may return target creature card from your graveyard to the battlefield.'),  # noqa: E501
    'The Matrix of Time': ('Plane — Gallifrey', "When you planeswalk to The Matrix of Time, each player exiles the top card of their library.\nDuring your turn, you may play lands and cast spells from among cards exiled with The Matrix of Time.\nWhenever you play a land or cast a spell from among cards exiled with The Matrix of Time, that card's owner loses 3 life and exiles the top card of their library.\nWhenever chaos ensues, create two Treasure tokens."),  # noqa: E501
    'The Moonbase': ('Plane — Moon', 'Low Gravity — All creatures have "{2}: This creature gains flying until end of turn. Activate only as a sorcery."\nWhenever chaos ensues, for each opponent, choose up to one target creature card in that player\'s graveyard. Put those cards onto the battlefield face down under your control. They\'re 2/2 Cyberman artifact creatures.'),  # noqa: E501
    'Kessig': ('Plane — Innistrad', 'Prevent all combat damage that would be dealt by non-Werewolf creatures.\nWhenever chaos ensues, each creature you control gets +2/+2, gains trample, and becomes a Werewolf in addition to its other types until end of turn.'),  # noqa: E501
}
ALL = {**PLANES, **LINES, "Krosa": BASE["Krosa"], "Lethe Lake": BASE["Lethe Lake"]}
EXTRA = [card(n, set_code="opca", number=f"PLA-{i}", layout="planar", type_line=t, oracle_text=o) for i, (n, (t, o)) in enumerate(ALL.items())]
EXTRA += [real("Runeclaw Bear", "{1}{G}", 2, "Creature — Bear", "", ("2", "2"), "G"),
          real("Battlegrowth", "{G}", 1, "Instant", "Put a +1/+1 counter on target creature.", None, "G"),
          real("Shock", "{R}", 1, "Instant", "Shock deals 2 damage to any target.", None, "R"),
          real("Glorious Anthem", "{1}{W}{W}", 3, "Enchantment", "Creatures you control get +1/+1.", None, "W")]
MORE = [(2, "Runeclaw Bear"), (1, "Grizzly Bears"), (1, "Battlegrowth"), (1, "Shock"), (1, "Raise the Alarm"), (1, "Glorious Anthem"),
        (9, "Forest")]


@pytest.fixture()
def card_db(settings: Settings) -> Path:
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


class _InOrder:
    def shuffle(self, items: list) -> None:
        pass

    def randint(self, lo: int, hi: int) -> int:
        return lo


def table(cards, planes: list[str], *, on: bool = True, bob=(("Island", 10),), mine=((1, "Runeclaw Bear"), (9, "Forest"))) -> GameSession:
    alice = deck(cards, "Krenko, Mob Boss", list(mine))
    bob_deck = deck(cards, "Atraxa, Praetors' Voice", [(n, name) for name, n in bob])
    pool = [PlanarCard(printing_id=cards.resolve(n)["id"], name=n, phenomenon=ALL[n][0] == "Phenomenon") for n in planes]
    settings = GameSettings(planechase=True, planar_deck_size=len(pool))
    state = new_game([PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=bob_deck)], shuffle=False, first_player=0,
                     settings=settings, planar_pool=lambda: pool, rng=_InOrder())
    if on:
        enable(state)
    s = GameSession(state, cards=cards)
    if on:
        act(s, "p1", type="pass_priority")  # → Alice's main phase
    return s


def face(s):
    pc = s.state.planechase
    return s.state.cards.get(pc.face_id) if pc.face_id else None


def named(s, name, pid="p1"):
    return next(c for c in s.state.cards.values() if c.name == name and c.owner == pid)


def keywords(s, c):
    return Plan(s.state, "p1", s.cards, None).ch(s.state.cards[c.id]).keywords


def to_graveyard(s, name, n, pid="p1"):
    ids = [c.id for c in s.state.cards.values() if c.name == name and c.owner == pid and c.zone == f"{pid}:library"][:n]
    assert len(ids) == n
    act(s, pid, type="move", card_ids=ids, to={"player": pid, "zone": "graveyard"})


def cast_bear(s, on: bool, pick=None):
    """Alice casts Runeclaw Bear and everything resolves (a decision: ``pick(decision)`` or its first options); by hand, it's put
    onto the battlefield."""
    bear = named(s, "Runeclaw Bear")
    if not on:
        act(s, "p1", type="move", card_ids=[bear.id], to={"player": "p1", "zone": "battlefield"})
        return bear
    act(s, "p1", type="move", card_ids=[bear.id], to={"zone": "hand"})
    mana(s, G=1, C=1)
    act(s, "p1", type="cast_spell", card_id=bear.id)
    for _ in range(30):
        d = s.state.rules.decision
        if d is not None:
            ids = pick(d) if pick else None
            act(s, d.player, type="choose", decision_id=d.id, option_ids=ids or [o.id for o in d.options][: max(1, d.min_choices)])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    return bear


@pytest.mark.parametrize("name", FULL)
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


# -- escape_grant: permissions._table_statics ------------------------------------------------------------------------------------
@pytest.mark.parametrize("on", [True, False])
def test_stormcage_creature_cards_in_your_graveyard_have_escape(cards, on):
    s = table(cards, ["Stormcage Containment Facility", "Krosa"], on=on)
    bear = named(s, "Runeclaw Bear")
    act(s, "p1", type="move", card_ids=[bear.id], to={"player": "p1", "zone": "graveyard"})
    to_graveyard(s, "Forest", 3)
    if not on:
        assert face(s) is None
        return
    mana(s, G=1, C=1)
    act(s, "p1", type="cast_spell", card_id=bear.id)  # 702.138a: {1}{G}, exile three other cards from your graveyard
    settle(s)
    assert s.state.cards[bear.id].zone == "p1:battlefield"
    assert s.state.rules.payments[s.state.rules.object_id(bear.id)].alternative == "escape"
    assert sum(1 for c in s.state.cards.values() if c.zone == "p1:exile") == 3
    check(s)


def test_stormcage_escape_needs_three_other_cards_and_ends_with_the_plane(cards):
    from app.game.errors import ActionError

    s = table(cards, ["Stormcage Containment Facility", "Krosa"])
    bear = named(s, "Runeclaw Bear")
    act(s, "p1", type="move", card_ids=[bear.id], to={"player": "p1", "zone": "graveyard"})
    to_graveyard(s, "Forest", 3)
    act(s, "p1", type="planeswalk")  # (to Krosa: the grant is gone)
    mana(s, G=1, C=1)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=bear.id)
    check(s)


# -- enters_other: triggers._watchers ----------------------------------------------------------------------------------------------
@pytest.mark.parametrize("on", [True, False])
def test_bloodhill_bastion_an_entering_creature_gains_double_strike_and_haste(cards, on):
    s = table(cards, ["Bloodhill Bastion", "Krosa"], on=on)
    bear = cast_bear(s, on)
    kw = keywords(s, bear) if on else set()
    assert ({"double strike", "haste"} <= kw) == on
    if on:
        to_turn(s, 2)  # until end of turn (Krosa: no; still Bloodhill Bastion on Bob's turn: the bear didn't enter again)
        assert not {"double strike", "haste"} & keywords(s, bear)
        check(s)


def test_immersturm_the_entering_creatures_controller_has_it_deal_damage(cards):
    s = table(cards, ["Immersturm", "Krosa"])
    asked = []

    def bob(d):
        asked.append((d.player, d.prompt))
        return [o.id for o in d.options if o.id == "p2" or "Bob" in (o.label or "")][:1] or None

    cast_bear(s, True, bob)  # Alice's creature: Alice (its controller) chooses Bob, and has it deal 2 damage to him
    assert asked and all(p == "p1" for p, _ in asked), asked
    assert life(s, "p2") == 38
    check(s)


# -- state: state_triggers.check (603.8) ---------------------------------------------------------------------------------------------
def test_aretopolis_planeswalks_at_ten_scroll_counters(cards, monkeypatch):
    s = table(cards, ["Aretopolis", "Lethe Lake"])
    plane = face(s)  # (Alice's first upkeep: one scroll counter, she gained 1)
    assert plane.counters == {"scroll": 1} and life(s, "p1") == 41
    act(s, "p1", type="counter", card_ids=[plane.id], kind="scroll", delta=8)
    settle(s)
    assert face(s).name == "Aretopolis"
    to_turn(s, 2)  # Bob's upkeep: the tenth counter (he gains 10), then the state trigger planeswalks (to Lethe Lake)
    assert life(s, "p2") == 50
    assert s.state.planechase.deck[0].name == "Lethe Lake" and face(s).name == "Lethe Lake"
    check(s)


def plan_of(s):
    return Plan(s.state, "p1", s.cards, None)


def run(s, pick=None, limit=40):
    """Resolve everything (a decision: ``pick(decision)`` or its first options)."""
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None:
            ids = pick(d) if pick else None
            act(s, d.player, type="choose", decision_id=d.id, option_ids=ids or [o.id for o in d.options][: max(1, d.min_choices)])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return


def cast(s, name, targets=(), pid="p1", **m):
    c = named(s, name, pid)
    act(s, pid, type="move", card_ids=[c.id], to={"zone": "hand"})
    mana(s, pid, **m)
    act(s, pid, type="cast_spell", card_id=c.id, targets=list(targets))
    run(s)
    return c


@pytest.mark.parametrize("name, line", [("Skybreen", 0), ("The Western Cloud", 0), ("The Doctor's Childhood Barn", 0),
                                        ("The Fertile Lands of Saulvinia", 0), ("Bicycle Rack", 0),
                                        ("Stairs to Infinity", 0), ("Windriddle Palaces", 0), ("Event Horizon", 1),
                                        ("The Matrix of Time", 1), ("The Moonbase", 0)])
def test_the_line_is_read_on_the_plane(cards, name, line):
    from app.game.state import CardInstance
    from app.rules import characteristics as chars
    from app.rules import planar, scripts

    c = cards.resolve(name)
    ch = chars.of(CardInstance(id="planar-9", card_id=c["id"], owner="p1", controller="p1", zone="p1:command"), {c["id"]: c})
    assert planar.ability_ok(scripts.definitions(ch).get(line))


# -- no_max_hand: hand_size.maximum ------------------------------------------------------------------------------------------------
def test_lux_foundation_library_players_have_no_maximum_hand_size(cards):
    from app.rules import hand_size

    s = table(cards, ["The Lux Foundation Library", "Krosa"])
    assert hand_size.maximum(plan_of(s), "p1") is None and hand_size.maximum(plan_of(s), "p2") is None
    act(s, "p1", type="planeswalk")
    assert hand_size.maximum(plan_of(s), "p1") == 7
    check(s)


# -- top_reveal: visibility.top_revealed (401.5) -------------------------------------------------------------------------------------
@pytest.mark.parametrize("on", [True, False])
def test_skybreen_players_play_with_the_top_card_of_their_libraries_revealed(cards, on):
    from app.game.visibility import top_revealed

    s = table(cards, ["Skybreen", "Krosa"], on=on)
    if on:
        act(s, "p1", type="pass_priority")  # (the engine refreshes what is revealed)
        run(s)
    tops = {p: s.state.cards[s.state.zones[f"{p}:library"][0]] for p in ("p1", "p2")}
    for viewer in ("p1", "p2"):
        assert all(top_revealed(s.state, top, viewer) == on for top in tops.values())
    if on:
        act(s, "p1", type="planeswalk")  # (Krosa: hidden again)
        assert not any(top_revealed(s.state, s.state.cards[s.state.zones["p1:library"][0]], v) for v in ("p1", "p2"))
        check(s)


# -- replace: replace.static_candidates (614) -------------------------------------------------------------------------------------
def test_stronghold_furnace_doubles_damage(cards):
    s = table(cards, ["Stronghold Furnace", "Krosa"], mine=MORE)
    cast(s, "Shock", ["p2"], R=1)
    assert life(s, "p2") == 36
    act(s, "p1", type="planeswalk")
    mana(s, R=1)
    act(s, "p1", type="move", card_ids=[named(s, "Shock").id], to={"zone": "hand"})
    act(s, "p1", type="cast_spell", card_id=named(s, "Shock").id, targets=["p2"])
    run(s)
    assert life(s, "p2") == 34
    check(s)


def test_selesnya_loft_gardens_doubles_tokens_and_counters(cards):
    s = table(cards, ["Selesnya Loft Gardens", "Krosa"], mine=MORE)
    cast(s, "Raise the Alarm", W=1, C=1)
    assert sum(1 for c in s.state.cards.values() if c.name == "Soldier" and c.zone == "p1:battlefield") == 4
    bear = put(s, "Grizzly Bears")
    cast(s, "Battlegrowth", [bear.id], G=1)
    assert s.state.cards[bear.id].counters.get("+1/+1") == 2
    check(s)


# -- prevent: replacements._static_records (615) ----------------------------------------------------------------------------------
def test_the_western_cloud_prevents_damage_to_your_creatures_only_while_you_are_planar_controller(cards):
    s = table(cards, ["The Western Cloud", "Lethe Lake"], mine=MORE)  # (not Krosa: its +2/+2)
    bear = put(s, "Grizzly Bears")
    cast(s, "Shock", [bear.id], R=1)
    assert s.state.cards[bear.id].zone == "p1:battlefield" and not s.state.cards[bear.id].damage
    act(s, "p1", type="planeswalk")
    mana(s, R=1)
    act(s, "p1", type="move", card_ids=[named(s, "Shock").id], to={"zone": "hand"})
    act(s, "p1", type="cast_spell", card_id=named(s, "Shock").id, targets=[bear.id])
    run(s)
    assert s.state.cards[bear.id].zone == "p1:graveyard"
    check(s)


# -- skip: skips._static (614.10) ----------------------------------------------------------------------------------------------------
def test_the_eon_fog_players_skip_their_untap_steps(cards):
    s = table(cards, ["The Eon Fog", "Krosa"])
    forest = put(s, "Forest")
    act(s, "p1", type="activate_ability", card_id=forest.id, ability=0)  # ({T}: Add {G}.)
    assert s.state.cards[forest.id].tapped
    to_turn(s, 3)
    assert s.state.cards[forest.id].tapped
    check(s)


# -- attack / block limits: combat_rules.limits (508.1c, 509.1c) ---------------------------------------------------------------------
def test_astral_arena_no_more_than_one_creature_can_attack_or_block_each_combat(cards):
    from app.game.errors import ActionError
    from app.rules import combat_rules

    s = table(cards, ["Astral Arena", "Krosa"], mine=MORE)
    assert combat_rules.limits(plan_of(s), combat_rules.LIMIT_ALL) == {"*": 1}
    assert combat_rules.limits(plan_of(s), combat_rules.BLOCK_LIMIT_ALL) == {"*": 1}
    one, two = put(s, "Runeclaw Bear"), put(s, "Grizzly Bears")
    to_turn(s, 3)
    until_attack(s)
    with pytest.raises(ActionError):
        act(s, "p1", type="declare_attackers", attackers=[{"card_id": one.id, "target": "p2"}, {"card_id": two.id, "target": "p2"}])
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": one.id, "target": "p2"}])
    run(s, limit=10)
    check(s)


def until_attack(s):
    from tests.test_rules_conditionals import until

    until(s, lambda s: (d := s.state.rules.decision) is not None and d.kind == "declare_attackers" or False, limit=60)


# -- enters_tapped_others: replacements.others_enter_tapped (614.1d) --------------------------------------------------------------------
def test_the_doctors_childhood_barn_creatures_enter_tapped(cards):
    s = table(cards, ["The Doctor's Childhood Barn", "Krosa"])
    bear = cast_bear(s, True)
    assert s.state.cards[bear.id].zone == "p1:battlefield" and s.state.cards[bear.id].tapped
    check(s)


# -- spend_as: cast_limits._statics (609.4b) ----------------------------------------------------------------------------------------
def test_mycosynthwave_players_may_spend_mana_as_though_it_were_any_color(cards):
    s = table(cards, ["Mycosynthwave", "Krosa"])
    bear = named(s, "Runeclaw Bear")
    act(s, "p1", type="move", card_ids=[bear.id], to={"zone": "hand"})
    mana(s, U=2)  # {1}{G} paid with {U}{U}
    act(s, "p1", type="cast_spell", card_id=bear.id)
    run(s)
    assert s.state.cards[bear.id].zone == "p1:battlefield"
    check(s)


# -- zone_grant: zone_grants (Varolz's scavenge, cycling) ----------------------------------------------------------------------------
def test_the_cave_of_skulls_creature_cards_in_your_graveyard_have_scavenge(cards):
    s = table(cards, ["The Cave of Skulls", "Krosa"], mine=MORE)
    dead = named(s, "Runeclaw Bear")
    act(s, "p1", type="move", card_ids=[dead.id], to={"player": "p1", "zone": "graveyard"})
    bears = put(s, "Grizzly Bears")
    ability = next(a.index for a in plan_of(s).ch(s.state.cards[dead.id]).abilities if "Exile this card from your graveyard" in a.text)
    mana(s, G=1, C=1)
    act(s, "p1", type="activate_ability", card_id=dead.id, ability=ability, targets=[bears.id])
    run(s)
    assert s.state.cards[dead.id].zone == "p1:exile" and s.state.cards[bears.id].counters.get("+1/+1") == 2
    check(s)


def test_bicycle_rack_cards_in_each_players_hand_have_cycling_two(cards):
    s = table(cards, ["Bicycle Rack", "Krosa"])
    bear = named(s, "Runeclaw Bear")
    act(s, "p1", type="move", card_ids=[bear.id], to={"zone": "hand"})
    assert "cycling" in plan_of(s).ch(s.state.cards[bear.id]).keywords or any(
        "Cycling" in a.text for a in plan_of(s).ch(s.state.cards[bear.id]).abilities)
    act(s, "p1", type="planeswalk")
    assert not any("Cycling" in a.text for a in plan_of(s).ch(s.state.cards[bear.id]).abilities)
    check(s)


# -- tap_for_mana: tap_mana._scan_triggers (605.1b) ------------------------------------------------------------------------------------
def test_eloren_wilds_a_permanent_tapped_for_mana_adds_one_more(cards):
    s = table(cards, ["Eloren Wilds", "Krosa"])
    forest = put(s, "Forest")
    act(s, "p1", type="activate_ability", card_id=forest.id, ability=0)
    run(s)
    assert sum(u.sym == "G" for u in s.state.players["p1"].mana_units) == 2
    check(s)


def test_kessig_prevents_combat_damage_by_non_werewolf_creatures(cards):
    s = table(cards, ["Kessig", "Krosa"])
    bear = put(s, "Runeclaw Bear")
    to_turn(s, 3)
    until_attack(s)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": bear.id, "target": "p2"}])
    from tests.test_rules_conditionals import until

    until(s, lambda s: s.state.turn.phase == "main2", limit=60)
    assert life(s, "p2") == 40
    check(s)


@pytest.mark.parametrize("planeswalked", [False, True])
def test_the_fertile_lands_of_saulvinia_a_land_tapped_for_mana_adds_one_more(cards, planeswalked):
    s = table(cards, ["The Fertile Lands of Saulvinia", "Krosa"])
    if planeswalked:
        act(s, "p1", type="planeswalk")
    forest = put(s, "Forest")
    act(s, "p1", type="activate_ability", card_id=forest.id, ability=0)
    run(s)
    assert sum(u.sym == "G" for u in s.state.players["p1"].mana_units) == (1 if planeswalked else 2)
    check(s)


# -- exact wordings: planar_statics.definition ------------------------------------------------------------------------------------------
@pytest.mark.parametrize("plane", ["Akoum", "Krosa"])
def test_akoum_players_may_cast_enchantment_spells_as_though_they_had_flash(cards, plane):
    from app.game.errors import ActionError

    s = table(cards, [plane, "Lethe Lake"], mine=MORE)
    shock, anthem = named(s, "Shock"), named(s, "Glorious Anthem")
    act(s, "p1", type="move", card_ids=[shock.id, anthem.id], to={"zone": "hand"})
    act(s, "p1", type="set_prefs", hold_priority=True)
    mana(s, R=1, W=2, C=1)
    act(s, "p1", type="cast_spell", card_id=shock.id, targets=["p2"])
    assert s.state.cards[shock.id].zone == "stack"  # (Alice holds priority, 117.3c: an enchantment now needs flash, 307.1)
    if plane == "Krosa":
        with pytest.raises(ActionError):
            act(s, "p1", type="cast_spell", card_id=anthem.id)
        return
    act(s, "p1", type="cast_spell", card_id=anthem.id)
    run(s)
    assert s.state.cards[anthem.id].zone == "p1:battlefield" and life(s, "p2") == 38
    check(s)


def test_onakke_catacomb_all_creatures_are_black_and_have_deathtouch(cards):
    s = table(cards, ["Onakke Catacomb", "Lethe Lake"])
    bear = put(s, "Runeclaw Bear")
    ch = plan_of(s).ch(s.state.cards[bear.id])
    assert ch.colors == frozenset({"B"}) or set(ch.colors) == {"B"}
    assert "deathtouch" in ch.keywords
    act(s, "p1", type="planeswalk")
    ch = plan_of(s).ch(s.state.cards[bear.id])
    assert set(ch.colors) == {"G"} and "deathtouch" not in ch.keywords
    check(s)


def test_the_matrix_of_time_you_may_play_the_cards_it_exiled_during_your_turn(cards, monkeypatch):
    s = table(cards, ["Krosa", "The Matrix of Time"])
    script(monkeypatch, [1])
    act(s, "p1", type="roll_planar_die")  # 901.8: planeswalk to The Matrix of Time: each player exiles the top card of their library
    run(s)
    assert face(s).name == "The Matrix of Time"
    exiled = [c for c in s.state.cards.values() if c.zone == "p1:exile" and c.owner == "p1"]
    assert len(exiled) == 1 and exiled[0].name == "Runeclaw Bear"
    mana(s, G=1, C=1)
    act(s, "p1", type="cast_spell", card_id=exiled[0].id)
    run(s)
    assert s.state.cards[exiled[0].id].zone == "p1:battlefield"
    check(s)


def test_the_moonbase_low_gravity_all_creatures_have_the_flying_ability(cards):
    s = table(cards, ["The Moonbase", "Krosa"])
    bear = put(s, "Runeclaw Bear")
    ability = next(a.index for a in plan_of(s).ch(s.state.cards[bear.id]).abilities if a.kind == "activated" and "gains flying" in a.text)
    mana(s, C=2)
    act(s, "p1", type="activate_ability", card_id=bear.id, ability=ability)
    run(s)
    assert "flying" in keywords(s, bear)
    act(s, "p1", type="planeswalk")
    assert not any("gains flying" in a.text for a in plan_of(s).ch(s.state.cards[bear.id]).abilities)
    check(s)

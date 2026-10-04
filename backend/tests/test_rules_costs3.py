"""Additional costs to cast a spell and cost modifiers for other spells (wave 3$).

CR 601.2b: an additional cost ("As an additional cost to cast this spell, sacrifice a creature") is
announced with the spell and, with the mana, is locked into the total cost (601.2f) and paid all at
once (601.2h, 118.3: no partial payments — an unpayable cost can't be paid, and a cast that is
cancelled or refused leaves the table exactly as it was). The object sacrificed can't also pay
mana; what was sacrificed is remembered (608.2h) so "the sacrificed creature's power" reads it.
Cost modifiers (601.2f, 118.7): see the second half. Real Commander cards' oracle text; every
scenario checks that replaying the history reproduces the table."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.cards.importer import build_database
from app.config import Settings
from app.game.errors import ActionError
from app.rules import casting, costs, permissions, scripts
from app.rules import characteristics as chars
from app.rules.characteristics import Characteristics
from app.rules.layers import derive
from app.rules.oracle import parse_abilities
from app.rules.view import hints
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_attachments import build, named, to_hand, token
from tests.test_rules_effects import pass_until_stack_empty, replay_matches
from tests.test_rules_permissions import build as pbuild
from tests.test_rules_permissions import cost_of, put

SPELLS = [
    ("Fling", "{1}{R}", "Instant", "As an additional cost to cast this spell, sacrifice a creature.\n"
     "Fling deals damage equal to the sacrificed creature's power to any target.", ["R"]),
    ("Village Rites", "{B}", "Instant", "As an additional cost to cast this spell, sacrifice a creature.\nDraw two cards.", ["B"]),
    ("Bone Splinters", "{B}", "Sorcery", "As an additional cost to cast this spell, sacrifice a creature.\nDestroy target creature.", ["B"]),
    ("Thrill of Possibility", "{1}{R}", "Instant", "As an additional cost to cast this spell, discard a card.\nDraw two cards.", ["R"]),
    ("Deadly Dispute", "{1}{B}", "Instant", "As an additional cost to cast this spell, sacrifice an artifact or creature.\n"
     "Draw two cards and create a Treasure token.", ["B"]),
]
MODIFIERS = [  # real Commander cards (name, mana cost, type line, oracle text, colors, power/toughness)
    ("Goblin Electromancer", "{U}{R}", "Creature — Goblin Wizard", "Instant and sorcery spells you cast cost {1} less to cast.", ["U", "R"], ("2", "2")),
    ("Thalia, Guardian of Thraben", "{1}{W}{W}", "Legendary Creature — Human Soldier", "First strike\nNoncreature spells cost {1} more to cast.", ["W"], ("2", "1")),
    ("Helm of Awakening", "{2}", "Artifact", "Spells cost {1} less to cast.", [], None),
    ("Jhoira's Familiar", "{4}", "Artifact Creature — Bird", "Flying\nHistoric spells you cast cost {1} less to cast.", [], ("2", "2")),
    ("Goreclaw, Terror of Qal Sisma", "{3}{G}", "Legendary Creature — Bear Warrior",
     "Creature spells you cast with power 4 or greater cost {2} less to cast.", ["G"], ("3", "3")),
    ("Danitha Capashen, Paragon", "{2}{W}", "Legendary Creature — Human Knight",
     "First strike, vigilance, lifelink\nAura and Equipment spells you cast cost {1} less to cast.", ["W"], ("2", "2")),
    ("Ballyrush Banneret", "{1}{W}", "Creature — Kithkin Soldier", "Kithkin spells and Soldier spells you cast cost {1} less to cast.", ["W"], ("2", "1")),
    ("Training Grounds", "{U}", "Enchantment", "Activated abilities of creatures you control cost {2} less to activate. "
     "This effect can't reduce the mana in that cost to less than one mana.", ["U"], None),
    ("Goblin Anarchomancer", "{R}{G}", "Creature — Goblin Shaman", "Each spell you cast that's red or green costs {1} less to cast.", ["R", "G"], ("2", "2")),
    ("Test Bear Four", "{3}{G}", "Creature — Bear", "", ["G"], ("4", "4")),
    ("Test Bear Two", "{2}{G}", "Creature — Bear", "", ["G"], ("2", "2")),
    ("Test Kithkin", "{1}{W}", "Creature — Kithkin", "", ["W"], ("1", "1")),
    ("Test Human", "{1}{W}", "Creature — Human", "", ["W"], ("1", "1")),
    ("Test Saber", "{3}", "Artifact — Equipment", "Equip {2}", [], None),
]
EXTRA = [card(n, set_code="tst", number=f"M{i}", mana_cost=mc, type_line=t, oracle_text=text, colors=col, color_identity=col,
              cmc=float(sum(int(c) if c.isdigit() else 1 for c in mc.replace("{", " ").replace("}", " ").split())),
              **({"power": pt[0], "toughness": pt[1]} if pt else {}))
         for i, (n, mc, t, text, col, pt) in enumerate(MODIFIERS)]
EXTRA += [card(n, set_code="tst", number=f"X{i}", mana_cost=mc, cmc=float(sum(int(c) if c.isdigit() else 1 for c in mc.replace("{", " ").replace("}", " ").split())),
              type_line=t, oracle_text=text, colors=col, color_identity=col) for i, (n, mc, t, text, col) in enumerate(SPELLS)]


@pytest.fixture()
def card_db(settings: Settings) -> Path:
    settings.ensure_dirs()
    build_database(fixture_cards() + EXTRA, settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def mana(s, **m):
    act(s, "p1", type="add_mana", player="p1", mana=m)


def decision(s):
    return s.state.rules.decision


def choose(s, *ids):
    act(s, decision(s).player, type="choose", decision_id=decision(s).id, option_ids=list(ids))
    pass_until_stack_empty(s)


def life(s, pid="p1"):
    return s.state.players[pid].life


def counters(s, c, n):
    act(s, "p1", type="counter", card_ids=[c.id], kind="+1/+1", delta=n)


def refused(s, match, **payload):
    """Refused, and the table is exactly as it was (118.3, 601.2h)."""
    before = s.state.model_dump(mode="json")
    with pytest.raises(ActionError, match=match):
        act(s, "p1", **payload)
    assert s.state.model_dump(mode="json") == before


def parse_cost(text):
    return costs.parse_additional_cost(text)


# -- the grammar ------------------------------------------------------------------------------
@pytest.mark.parametrize("text", [
    "sacrifice a creature", "discard a card", "pay 2 life", "sacrifice an artifact or creature", "sacrifice a land",
    "exile a creature card from your graveyard", "discard a card and sacrifice a creature",
    "reveal a Merfolk card from your hand or pay {3}", "behold an Elf or pay {2}", "blight 1 or pay {3}", "forage or pay {B}",  # (wave 17C)
])
def test_additional_costs_the_engine_pays(text):
    assert parse_cost(text) is not None


@pytest.mark.parametrize("text", [
    "you may sacrifice a creature", "discard X cards",  # ("pay X life": wave 4K; "A or B": read since wave 6E)
    "sacrifice this spell", "tap an untapped creature you control, discard a card",
])
def test_additional_costs_it_refuses(text):
    assert parse_cost(text) is None


def test_unreadable_additional_cost_leaves_the_spell_manual():
    # an optional / X additional cost can't be paid by the engine: no definition, never cast without its cost
    ab = parse_abilities("As an additional cost to cast this spell, you may sacrifice a creature.\nDraw a card.")
    ch = Characteristics(name="T", types=frozenset({"Instant"}), abilities=tuple(ab))
    assert scripts.spell_definition(ch) is None


# -- sacrifice (Fling, Village Rites, Bone Splinters) -----------------------------------------
def test_fling_reads_the_power_of_the_sacrificed_creature(cards):
    s = build(cards, "Fling")
    bear, wolf = token(s, "p1", "Bear", "1/1"), token(s, "p1", "Wolf", "2/2")
    counters(s, bear, 3)  # a 4/4 as it is sacrificed
    fling = to_hand(s, "Fling")
    mana(s, R=1, C=1)
    act(s, "p1", type="cast_spell", card_id=fling.id, targets=["p2"])
    d = decision(s)
    assert d.player == "p1" and d.kind == "choose_cards" and {o.id for o in d.options} == {bear.id, wolf.id}
    assert "options" not in s.view("p2")["rules"]["decision"]
    assert named(s, "Bear") and s.state.players["p1"].mana.get("R") == 1  # nothing paid or moved yet
    choose(s, bear.id)
    assert bear.id not in s.state.cards and wolf.id in s.state.cards
    assert life(s, "p2") == 36
    replay_matches(s)


def test_sacrifice_choice_given_up_front_and_a_single_creature_is_automatic(cards):
    s = build(cards, "Fling")
    bear, wolf = token(s, "p1", "Bear", "3/3"), token(s, "p1", "Wolf", "2/2")
    fling = to_hand(s, "Fling")
    mana(s, R=1, C=1)
    act(s, "p1", type="cast_spell", card_id=fling.id, targets=["p2"], cost_choices=[{"component": 0, "cards": [wolf.id]}])
    pass_until_stack_empty(s)
    assert wolf.id not in s.state.cards and bear.id in s.state.cards and life(s, "p2") == 38
    replay_matches(s)
    lone = build(cards, "Fling")
    token(lone, "p1", "Mouse", "1/1")
    f2 = to_hand(lone, "Fling")
    mana(lone, R=1, C=1)
    act(lone, "p1", type="cast_spell", card_id=f2.id, targets=["p2"])
    pass_until_stack_empty(lone)
    assert decision(lone) is None and life(lone, "p2") == 39


def test_no_creature_to_sacrifice_refuses_and_changes_nothing(cards):
    s = build(cards, "Village Rites")
    rites = to_hand(s, "Village Rites")
    mana(s, B=1)
    refused(s, "can't pay", type="cast_spell", card_id=rites.id)
    assert rites.zone.endswith(":hand")
    assert not s.state.zones.get("stack")


def test_castable_hint_knows_the_additional_cost(cards):
    s = build(cards, "Village Rites")
    rites = to_hand(s, "Village Rites")
    mana(s, B=1)
    assert rites.id not in hints(s.state, "p1", cards)["castable"]
    token(s, "p1", "Bear", "1/1")
    assert rites.id in hints(s.state, "p1", cards)["castable"]


def test_cancelling_the_choice_pays_nothing(cards):
    s = build(cards, "Village Rites")
    token(s, "p1", "Bear"), token(s, "p1", "Wolf")
    rites = to_hand(s, "Village Rites")
    mana(s, B=1)
    before = s.state.model_dump(mode="json")["players"]
    act(s, "p1", type="cast_spell", card_id=rites.id)
    act(s, "p1", type="choose", decision_id=decision(s).id, option_ids=[])
    assert s.state.model_dump(mode="json")["players"] == before and rites.zone.endswith(":hand")
    assert named(s, "Bear") and named(s, "Wolf")
    replay_matches(s)


def test_not_enough_mana_after_choosing_changes_nothing(cards):
    s = build(cards, "Village Rites")
    bear = token(s, "p1", "Bear")
    rites = to_hand(s, "Village Rites")  # {B} but no mana
    refused(s, "ana|pay|mana", type="cast_spell", card_id=rites.id, cost_choices=[{"component": 0, "cards": [bear.id]}])
    assert named(s, "Bear")


def test_village_rites_draws_two_after_the_sacrifice(cards):
    s = build(cards, "Village Rites")
    bear = token(s, "p1", "Bear")
    rites = to_hand(s, "Village Rites")
    mana(s, B=1)
    hand = len(s.state.zones["p1:hand"])
    act(s, "p1", type="cast_spell", card_id=rites.id)
    pass_until_stack_empty(s)
    assert bear.id not in s.state.cards and len(s.state.zones["p1:hand"]) == hand - 1 + 2
    replay_matches(s)


def test_the_sacrificed_creature_can_t_also_pay_the_mana(cards):
    s = build(cards, "Village Rites")
    elf = token(s, "p1", "Elf", "1/1", text="{T}: Add {B}.")
    rites = to_hand(s, "Village Rites")
    refused(s, "ana|pay|mana", type="cast_spell", card_id=rites.id, cost_choices=[{"component": 0, "cards": [elf.id]}])
    assert named(s, "Elf")


def test_bone_splinters_targets_first_then_the_sacrifice(cards):
    s = build(cards, "Bone Splinters")
    bear, wolf = token(s, "p1", "Bear"), token(s, "p1", "Wolf")
    victim = token(s, "p2", "Victim", "3/3")
    splinters = to_hand(s, "Bone Splinters")
    act(s, "p1", type="pass_priority")  # (the sandbox is fine at any time; keep priority below)
    mana(s, B=1)
    act(s, "p1", type="cast_spell", card_id=splinters.id, targets=[victim.id], cost_choices=[{"component": 0, "cards": [bear.id]}])
    pass_until_stack_empty(s)
    assert victim.id not in s.state.cards and bear.id not in s.state.cards and wolf.id in s.state.cards
    replay_matches(s)


def test_deadly_dispute_takes_a_creature_or_an_artifact(cards):
    s = build(cards, "Deadly Dispute")
    act(s, "p1", type="create_token", player="p1", token={"name": "Relic", "type_line": "Token Artifact — Test", "text": ""})
    bear = token(s, "p1", "Bear")
    dispute = to_hand(s, "Deadly Dispute")
    mana(s, B=1, C=1)
    act(s, "p1", type="cast_spell", card_id=dispute.id)
    d = decision(s)
    assert {o.id for o in d.options} == {named(s, "Relic").id, bear.id}


# -- discard (Thrill of Possibility) ---------------------------------------------------------------
def test_discard_a_card_is_private_and_never_the_spell_itself(cards):
    s = build(cards, "Thrill of Possibility", "Forest")
    thrill = to_hand(s, "Thrill of Possibility")
    refused(s, "can't pay", type="cast_spell", card_id=thrill.id)  # no other card in hand
    other, third = named(s, "Forest"), None
    act(s, "p1", type="move", card_ids=[other.id], to={"zone": "hand"})
    third = next(c for c in s.state.cards.values() if c.name == "Forest" and c.zone == "p1:library")
    act(s, "p1", type="move", card_ids=[third.id], to={"zone": "hand"})
    mana(s, R=1, C=1)
    act(s, "p1", type="cast_spell", card_id=thrill.id)
    d = decision(s)
    assert d.player == "p1" and {o.id for o in d.options} == {other.id, third.id}
    assert "options" not in s.view("p2")["rules"]["decision"]
    choose(s, other.id)
    assert other.zone == "p1:graveyard"
    replay_matches(s)


# -- cost modifiers for other spells (601.2f, 118.7) ----------------------------------------------------
def define(text):
    return permissions.define_static(text, "static")


@pytest.mark.parametrize("text", [m[3].split("\n")[-1] for m in MODIFIERS if "cost" in m[3]])
def test_modifier_wordings_of_real_cards(text):
    d = define(text)
    assert d is not None and d["static"] in ("cost_modifier", "ability_cost_modifier")


@pytest.mark.parametrize("text", [
    # (wave 4I: "Spells you cast from anywhere other than your hand cost {1} less" is read now: cost_changes.py)
    # (wave 4I: "The first creature spell you cast each turn costs {1} less" is read now: cost_changes.ORDINAL)
    "Red creature spells and green creature spells cost {1} more to cast.",  # (one selector can't say "red creature or green creature")
])
def test_modifier_wordings_still_refused(text):
    assert define(text) is None


def test_instant_and_sorcery_reduction_leaves_creatures_alone(cards):
    s = pbuild(cards, [(1, "Goblin Electromancer"), (1, "Opt"), (1, "Grizzly Bears")])
    put(s, "Goblin Electromancer", "battlefield")
    opt, bears = put(s, "Opt", "hand"), put(s, "Grizzly Bears", "hand")
    assert cost_of(s, opt, cards) == "{U}" and cost_of(s, bears, cards) == "{1}{G}"
    assert cost_of(s, opt, cards, pid="p2") == "{U}"  # (nothing generic to take)


def test_thalia_taxes_noncreature_spells_of_everyone(cards):
    s = pbuild(cards, [(1, "Thalia, Guardian of Thraben"), (1, "Opt"), (1, "Grizzly Bears")])
    put(s, "Thalia, Guardian of Thraben", "battlefield")
    opt, bears = put(s, "Opt", "hand"), put(s, "Grizzly Bears", "hand")
    assert cost_of(s, opt, cards) == "{1}{U}" and cost_of(s, bears, cards) == "{1}{G}"
    mana(s, U=1)
    refused(s, "ana", type="cast_spell", card_id=opt.id)  # {1}{U} with only {U}
    mana(s, C=1)
    act(s, "p1", type="cast_spell", card_id=opt.id)
    assert s.state.cards[opt.id].zone == "p1:graveyard" and not s.state.players["p1"].mana.get("C")
    replay_matches(s)


def test_increases_apply_before_reductions(cards):
    s = pbuild(cards, [(1, "Helm of Awakening"), (1, "Thalia, Guardian of Thraben"), (1, "Sol Ring"), (1, "Opt")])
    put(s, "Helm of Awakening", "battlefield")
    ring, opt = put(s, "Sol Ring", "hand"), put(s, "Opt", "hand")
    assert cost_of(s, ring, cards) == "{0}" and cost_of(s, opt, cards) == "{U}"
    put(s, "Thalia, Guardian of Thraben", "battlefield")  # both: {1} + {1} − {1}
    assert cost_of(s, ring, cards) == "{1}" and cost_of(s, opt, cards) == "{U}"
    assert cost_of(s, put(s, "Thalia, Guardian of Thraben", "hand", pid="p1"), cards) == "{W}{W}"  # a creature: Helm only


def test_historic_spells_cost_less_with_jhoiras_familiar(cards):
    s = pbuild(cards, [(1, "Jhoira's Familiar"), (1, "Test Saber"), (1, "Grizzly Bears"), (1, "Thalia, Guardian of Thraben")])
    put(s, "Jhoira's Familiar", "battlefield")
    saber, bears, thalia = (put(s, n, "hand") for n in ("Test Saber", "Grizzly Bears", "Thalia, Guardian of Thraben"))
    assert cost_of(s, saber, cards) == "{2}"  # an artifact is historic
    assert cost_of(s, thalia, cards) == "{W}{W}"  # a legendary creature is historic
    assert cost_of(s, bears, cards) == "{1}{G}"  # a plain creature isn't


def test_power_four_or_greater_creatures_cost_two_less_with_goreclaw(cards):
    s = pbuild(cards, [(1, "Goreclaw, Terror of Qal Sisma"), (1, "Test Bear Four"), (1, "Test Bear Two")])
    put(s, "Goreclaw, Terror of Qal Sisma", "battlefield")
    big, small = put(s, "Test Bear Four", "hand"), put(s, "Test Bear Two", "hand")
    assert cost_of(s, big, cards) == "{1}{G}" and cost_of(s, small, cards) == "{2}{G}"
    mana(s, G=1, C=1)
    act(s, "p1", type="cast_spell", card_id=big.id)
    assert s.state.cards[big.id].zone == "p1:battlefield" and not s.state.players["p1"].mana.get("C")
    replay_matches(s)


def test_capitalized_subtypes_lists_and_colors(cards):
    s = pbuild(cards, [(1, "Danitha Capashen, Paragon"), (1, "Ballyrush Banneret"), (1, "Goblin Anarchomancer"), (1, "Test Saber"),
                       (1, "Test Bear Four"), (1, "Opt"), (1, "Test Kithkin"), (1, "Test Human")])
    for n in ("Danitha Capashen, Paragon", "Goblin Anarchomancer"):
        put(s, n, "battlefield")
    saber, bear, opt = (put(s, n, "hand") for n in ("Test Saber", "Test Bear Four", "Opt"))
    assert cost_of(s, saber, cards) == "{2}"  # Equipment: Danitha ({3} − 1)
    assert cost_of(s, bear, cards) == "{2}{G}"  # green: Anarchomancer
    assert cost_of(s, opt, cards) == "{U}"
    put(s, "Ballyrush Banneret", "battlefield")
    kithkin, human = put(s, "Test Kithkin", "hand"), put(s, "Test Human", "hand")
    assert cost_of(s, kithkin, cards) == "{W}" and cost_of(s, human, cards) == "{1}{W}"  # Kithkin spells and Soldier spells


# -- activated abilities (602.2b, 118.7) -------------------------------------------------------------------
def activate_cost(s, cards, card):
    ch = derive(s.state, card, chars.of(card, cards), cards)
    return casting.ability_cost(ch, ch.abilities[0], state=s.state, card=card, info=cards).mana


def test_training_grounds_reduces_activated_abilities_but_not_below_one_mana(cards):
    s = pbuild(cards, [(1, "Training Grounds")])
    put(s, "Training Grounds", "battlefield")
    big = token(s, "p1", "Big", "2/2", text="{4}: You gain 1 life.")
    small = token(s, "p1", "Small", "2/2", text="{1}{G}: You gain 1 life.")
    tiny = token(s, "p1", "Tiny", "2/2", text="{1}: You gain 1 life.")
    theirs = token(s, "p2", "Theirs", "2/2", text="{4}: You gain 1 life.")
    assert activate_cost(s, cards, big) == "{2}"
    assert activate_cost(s, cards, small) == "{G}"  # only the generic part reduces (118.7a), and one mana stays
    assert activate_cost(s, cards, tiny) == "{1}"  # the floor: never less than one mana
    assert activate_cost(s, cards, theirs) == "{4}"  # "creatures you control"
    mana(s, C=2)
    act(s, "p1", type="activate_ability", card_id=big.id, ability=0)
    pass_until_stack_empty(s)
    assert life(s) == 41 and not s.state.players["p1"].mana.get("C")
    replay_matches(s)

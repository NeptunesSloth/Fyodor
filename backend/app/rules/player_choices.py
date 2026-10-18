"""-- player-relative selectors (wave 53A) -- a choice made for each player, among the objects that player controls or the cards in that player's graveyard: "For each
player, choose a creature or planeswalker card in that player's graveyard." (Breach the Multiverse), "For each player, choose a creature card in that player's graveyard."
(Ghouls' Night Out), "Each player puts a creature card from their graveyard onto the battlefield." (Exhume), "Each player returns two land cards from their graveyard to the
battlefield." (Fall of the Thran), "Each opponent chooses a creature card in their graveyard. Put those cards onto the battlefield under your control." (Dredge the Mire).

State: none beyond effects.player_chooses (wave 30K): the chosen objects are the binding the sentence after reads ("those cards", "that card"), recorded when the last choice is
made. ``zone`` ("graveyard") makes the set the cards the player owns in that zone instead of the permanents they control.

Decisions: 101.4 - every player makes their choice in APNAP order (the active player first), each knowing the earlier ones (101.4b: they are announced); "for each player, choose"
is the ability's controller's choice for each (``by: you``), "each player puts / returns / chooses" each player's own. A graveyard is public (404.2), so nobody is told
anything new by a skipped question; "up to" and "may" always ask. Nothing is moved until every choice is made, then all at once (the cards enter / return together).

Rules: 101.4, 101.4b, 404.1-404.2, 608.2c, 608.2d, 110.2a (an object put onto the battlefield by an instruction given to a player enters under that player's control unless
the instruction says otherwise).
"""

from __future__ import annotations

import re
from typing import Any

from app.rules import selectors

_NUM = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4}
_WHO = {"player": "each_player", "opponent": "each_opponent", "other player": "each_opponent"}


def _permanents(phrase: str) -> str:
    """A permanent selector (language._permanent_sel) or no reading at all."""
    from app.rules import language
    from app.rules.scripts import _NoMatch

    try:
        return language._permanent_sel(phrase)
    except language._Fail:
        raise _NoMatch from None


def _graveyard_selector(phrase: str) -> str:
    """"creature or planeswalker card" / "land cards" / "creature card with mana value 3 or less" -> the selector over a graveyard's cards."""
    from app.rules.scripts import _NoMatch  # (scripts imports this module)

    sel = selectors.parse(re.sub(r"\bcards\b", "card", phrase) + " from a graveyard")
    if sel is None or not sel.card or sel.player is not None or sel.controller is not None or sel.zone_owner is not None or sel.zones != ("graveyard",):
        raise _NoMatch
    return sel.key()


# "For each player, choose a creature card in that player's graveyard." / "For each opponent, choose a creature that player controls." - the controller chooses for each
_FOR_EACH = re.compile(r"^for each (?P<who>player|opponent), (?:you )?choose (?P<q>an?|up to one) (?P<sel>[a-z ,'-]+?) "
                       r"(?P<where>that (?:player|opponent) controls|in that (?:player|opponent)'s graveyard)$")


def _for_each(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    graveyard = m["where"].startswith("in ")
    sel = _graveyard_selector(m["sel"]) if graveyard else _permanents(m["sel"])
    upto = m["q"].startswith("up")
    return [{"do": "player_chooses", "who": _WHO[m["who"]], "by": "you", "sel": sel, "n": 1, "label": m["sel"], **({"upto": True, "optional": True} if upto else {}),
             **({"zone": "graveyard"} if graveyard else {})}], None


# "Each player puts a creature card from their graveyard onto the battlefield." / "Each player returns two land cards from their graveyard to the battlefield." / "… may return
# a creature card …" (Enslaved Horror) / "… returns up to three cards from their graveyard to their hand." (Ill-Gotten Gains): each chooses among their own graveyard, then all of
# them move at once, each under its owner's control
_EACH = re.compile(r"^(?P<who>each player|each opponent|each other player|that player) (?P<may>may )?(?:puts|returns|put|return) (?P<q>(?:up to )?(?:an?|one|two|three|four)) "
                   r"(?P<sel>[a-z ,]*?cards?(?: with mana value \d+ or less)?) from their graveyard (?P<to>onto the battlefield|to the battlefield|to their hand)$")


def _each(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    q = m["q"]
    upto = bool(m["may"]) or q.startswith("up to")
    n = _NUM[q.removeprefix("up to ")]
    kind = "battlefield" if "battlefield" in m["to"] else "hand"
    who = "that_player" if m["who"] == "that player" else _WHO[m["who"].removeprefix("each ")]  # (that player: Skullwinder, bound to the opponent chosen before)
    move = {"do": "return_card", "who": "it" if who == "that_player" and n == 1 else "them", "to": kind, "under": "owner", **({"tapped": False} if kind == "battlefield" else {})}
    return [{"do": "player_chooses", "who": who, "sel": _graveyard_selector(m["sel"]), "n": n, "label": m["sel"], "zone": "graveyard",
             **({"upto": True, "optional": True} if upto else {})}, move], None


# "Each opponent chooses a creature card in their graveyard." / "Target opponent chooses an artifact card in their graveyard." (Dredge the Mire, Scrounge): the sentence after puts
# what was chosen onto the battlefield under the controller's control
_CHOOSES = re.compile(r"^(?P<who>each opponent|each player|target opponent|target player) chooses (?P<q>an?|up to one) (?P<sel>[a-z ,]*?cards?) in their graveyard$")


def _chooses(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    target = m["who"].startswith("target")
    upto = m["q"].startswith("up")
    return [{"do": "player_chooses", "who": "target" if target else _WHO[m["who"].removeprefix("each ")], "sel": _graveyard_selector(m["sel"]), "n": 1, "label": m["sel"],
             "zone": "graveyard", **({"upto": True, "optional": True} if upto else {})}], (m["who"].removeprefix("target ") if target else None)


TEMPLATES: list[tuple[re.Pattern[str], Any]] = [(_FOR_EACH, _for_each), (_EACH, _each), (_CHOOSES, _chooses)]

# "Put those cards onto the battlefield under your control." / "Put that card onto the battlefield under your control." after a choice: what was chosen, moved from where it is (the
# pronoun is bound to the instruction before by scripts.resolve_it); read last, after every wording that names the cards in another way
_PUT = re.compile(r"^put (?P<p>those cards|that card|those creatures|them) onto the battlefield(?P<tapped> tapped)? under your control$")


def _put(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    return [{"do": "return_card", "who": "them" if m["p"] != "that card" else "it", "to": "battlefield", "tapped": bool(m["tapped"]), "under": "you"}], None


LATE: list[tuple[re.Pattern[str], Any]] = [(_PUT, _put)]

# "For each player, choose a creature that player controls. Each player sacrifices all creatures they control not chosen this way." (The Eternal Wanderer -4): one choice for each
# player (the controller's), then everything else of that kind goes at once (101.4, 701.21a): the wording player_chooses already has for "chooses ..., then sacrifices the rest"
_NOT_CHOSEN = re.compile(r"(For each (?:player|opponent), (?:you )?choose an? (?P<sel>[a-z ]+?) that (?:player|opponent) controls)\. "
                         r"Each (?:player|opponent) sacrifices all (?P=sel)s they control not chosen this way\.")


def rewrite(body: str) -> str:
    # "exile it and each player returns all creature cards from their graveyard to their hand" (Underworld Cerberus): two instructions, two subjects (608.2c)
    body = re.sub(r"(^|[.,] )([Ee])xile it and (each player returns )", lambda m: f"{m[1]}{m[2]}xile it. {m[3].capitalize()}", body)
    # "Each player discards their hand, then returns up to three cards from their graveyard to their hand." (Ill-Gotten Gains): the discard first, then the choice (608.2c)
    body = re.sub(r"\b(Each player discards their hand), then (returns up to \w+ cards from their graveyard)", r"\1. Each player \2", body)
    # "Exile all cards from that player's hand, then they draw that many cards." (Elder Brain): that many is the number of cards exiled this way (the this-way count, not an event's amount)
    body = re.sub(r"\b(Exile all cards from (?:that|target) player's hand), then (?:they|that player) draws? that many cards\b", r"\1. That player draws cards equal to the number of cards exiled this way", body)
    # "You may play lands and cast spells from among the exiled cards for as long as they remain exiled. If you cast a spell this way, you may spend mana as though it were mana of any color
    # to cast it." (Elder Brain): the permission to play the cards, with the mana rider the grammar has for "You may play those cards for as long as they remain exiled, and …"
    body = re.sub(r"\bYou may play lands and cast spells from among the exiled cards for as long as they remain exiled\. If you cast a spell this way, you may spend mana as though it were mana of "
                  r"any (color|type) to cast it\.", r"You may play those cards for as long as they remain exiled, and you may spend mana as though it were mana of any \1 to cast those spells.", body)
    # "For any number of opponents, destroy target nonland permanent that player controls." (Windgrace's Judgment): you choose the opponents as you cast it (601.2c) and a target for each - the
    # same as "for each opponent, destroy up to one target ... that player controls" (per_opponent): an opponent left out is one you chose no target for
    body = re.sub(r"\bFor any number of opponents, (destroy|exile) target ([a-z ]+?) that player controls\b", r"For each opponent, \1 up to one target \2 that player controls", body)
    body = re.sub(r"(\b[Ee]ach player may put \w+ [+-]\d+/[+-]\d+ counters? on a creature they control)\. If a player does, creatures that player controls (can't attack you or planeswalkers you control until your next turn)",
                  r"\1 and creatures a player who did controls \2", body)
    # "For each player, choose up to one target creature card in that player's graveyard. Put those cards onto the battlefield under your control. They're Zombies in addition to their
    # other types." (Afterlife from the Loam): a target for each player (601.2c, per_opponent), each put onto the battlefield under your control (the cards enter at the same time as far
    # as any trigger can tell, 603.6a), and each one a Zombie
    body = re.sub(r"\bFor each player, choose up to one target (creature card) in that player's graveyard\. Put those cards onto the battlefield under your control\. "
                  r"They're (Zombies) in addition to their other types\.",
                  lambda m: f"For each player, put up to one target {m[1]} from that player's graveyard onto the battlefield under your control. It's a Zombie in addition to its other types.", body)
    # "Target opponent exiles a creature they control and their graveyard." (Strategic Betrayal): the creature they choose (an edict, 701.21a), then every card of their graveyard
    body = re.sub(r"\b(Target (?:opponent|player)) exiles (an? [a-z]+ they control) and their graveyard\b", r"\1 exiles \2. That player exiles all cards from their graveyard", body)
    # "~ deals 3 damage to that player and 1 damage to each creature they control." (The Fall of Kroog): the player a target named, then the creatures that player controls (two damage
    # instructions, 608.2c: only a trigger that batches the damage of one instruction could tell them from one event)
    body = re.sub(r"(~) deals (\d+) damage to that player and (\d+) damage to each creature they control", r"\1 deals \2 damage to that player. \1 deals \3 damage to each creature that player controls", body)
    # "~ deals damage equal to the number of cards in target player's hand to that player." (Tibalt, the Fiend-Blooded -4): the damage to the target player, sized by their hand
    body = re.sub(r"(~) deals damage equal to the number of cards in (target player)'s hand to that player\b", r"\1 deals damage to \2 equal to the number of cards in their hand", body)
    # "You may look at the top card of target opponent's library. If you do, you may put that card on the bottom of that player's library." (Precognition): the first "may" is the whole
    # ability's (it looks or it doesn't), the second is the choice of moving the card it saw
    body = re.sub(r"(\b[Yy]ou may look at the top card of (?:target opponent|target player)'s library\.) If you do, you may put", r"\1 You may put", body)
    # "Target player creates X 2/2 black Zombie creature tokens, then up to one target creature gets -1/-1 until end of turn for each Zombie that player controls." (Dark Salvation): two
    # instructions of two targets (608.2c): the second is its own sentence
    body = re.sub(r"\b((?:[Tt]arget (?:player|opponent)|[Tt]hat player) creates [^.,]+? tokens?), then ((?:up to one )?target creature (?:gets|gains|deals))",
                  lambda m: f"{m[1]}. {m[2][0].upper()}{m[2][1:]}", body)
    # "Choose target creature that player controls. The player sacrifices that creature." (Ashling, the Extinguisher): "the player" is that player
    body = re.sub(r"(\b[Cc]hoose target [a-z ]+ that player controls\. )The player sacrifices that", r"\1That player sacrifices that", body)
    return _NOT_CHOSEN.sub(lambda m: m[1] + ", then each player sacrifices the rest.", body)


_FOR_EACH_REST = re.compile(r"^for each (?P<who>player|opponent), (?:you )?choose (?P<q>an?) (?P<sel>[a-z ,'-]+?) that (?:player|opponent) controls, then each (?:player|opponent) sacrifices the rest$")


def _for_each_rest(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    return [{"do": "player_chooses", "who": _WHO[m["who"]], "by": "you", "sel": _permanents(m["sel"]), "n": 1, "label": m["sel"], "rest": "sacrifice"}], None


TEMPLATES.append((_FOR_EACH_REST, _for_each_rest))


# "Destroy one of them chosen at random." (Chaos Defiler): the table picks one of the objects the choices before bound (recorded, so a replay or a load never draws again) and it is destroyed
_ONE_OF_THEM = re.compile(r"^destroy one of them chosen at random$")


def _one_of_them(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    return [{"do": "destroy_random", "who": "them"}], None


TEMPLATES.append((_ONE_OF_THEM, _one_of_them))


def destroy_random(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    import secrets

    from app.rules import effects

    found = sorted(effects._cards(plan, ctx, e["who"]))
    if not found:
        return True
    pick = (plan.rng or secrets.SystemRandom()).choice(found)
    plan.note(f"{ctx.get('name') or 'It'}: chosen at random ->", [pick], actor=ctx["controller"])
    return effects._destroy_cards(plan, ctx, {**e, "as": e.get("as")}, [pick])


PRIMITIVES: dict[str, Any] = {"destroy_random": destroy_random}


# "… then you may put any number of land cards that player owns from exile onto the battlefield under your control." (Oblivion Sower): the cards that player owns in exile - the ones just
# exiled and any other they own there (the card's ruling) - chosen as it resolves (608.2d); the player is tagged by scripts.resolve_it (``that``) and read when it is carried out
_FROM_EXILE = re.compile(r"^(?:you may )?put (?P<q>any number of|up to (?:one|two|three|four)|an?) (?P<sel>[a-z ]+?) cards? that player owns from exile onto the battlefield(?P<tapped> tapped)? under your control$")


def _from_exile(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    from dataclasses import replace

    from app.rules.scripts import _NoMatch

    sel = selectors.parse(m["sel"] + " card from exile")
    if sel is None or not sel.card or sel.zones != ("exile",) or sel.player is not None or sel.owner is not None or sel.zone_owner is not None or sel.controller is not None:
        raise _NoMatch
    q = m["q"]
    n = 999 if q == "any number of" else _NUM[q.removeprefix("up to ")]
    return [{"do": "return_choice", "to": "battlefield", "tapped": bool(m["tapped"]), "under": "you", "sel": replace(sel, zone_owner=selectors.THAT_PLAYER).key(), "n": n,
             "upto": q != "a" and q != "an", "random": False, "label": m["sel"] + " card"}], None


TEMPLATES.append((_FROM_EXILE, _from_exile))


# "…, then put a creature card from among them onto the battlefield under your control." (Lord of the Void) after "exile the top seven cards of that player's library": the controller
# chooses (608.2d) among the cards that instruction exiled (public, face up: 406.3), the one chosen entering under their control
_FROM_AMONG = re.compile(r"^(?:then )?put (?P<q>an?|up to one) (?P<sel>[a-z ]+?) card from among them onto the battlefield(?P<tapped> tapped)?(?: under your control)?$")


def _from_among(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    from dataclasses import replace

    from app.rules.scripts import _NoMatch

    sel = selectors.parse(m["sel"] + " card from a graveyard")
    if sel is None or not sel.card or sel.zones != ("graveyard",) or sel.player is not None or sel.owner is not None or sel.zone_owner is not None or sel.controller is not None:
        raise _NoMatch
    return [{"do": "return_choice", "who": "them:exiled|" + replace(sel, zones=("exile",)).key(), "to": "battlefield", "tapped": bool(m["tapped"]), "under": "you", "n": 1,
             "upto": m["q"] != "a" and m["q"] != "an", "random": False, "label": m["sel"] + " card"}], None


TEMPLATES.append((_FROM_AMONG, _from_among))


# "Choose a player with the most life or tied for most life." (The Black Gate): the controller chooses among the players whose life total is the greatest (a public number, 119.1); the
# sentence after names that player ("creatures that player controls", resolve_it binds it to the choice)
_MOST_LIFE = re.compile(r"^choose a player with the most life or tied for most life$")


def _most_life(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    return [{"do": "choose_value", "who": "you", "what": "player with the most life"}], None


TEMPLATES.append((_MOST_LIFE, _most_life))


# -- "Each player chooses a creature type. Each player returns all creature cards of a type chosen this way from their graveyard to the battlefield." (Patriarch's Bidding) -------------
# Every player names a creature type, in turn order (101.4), each knowing the earlier ones (101.4b: announced); the types together are the binding "chosen_types" the next sentence reads
# (``typed:chosen_types|<selector>``: effects._cards - the cards of the selector that have one of them, a changeling every one, 702.73a).
_EACH_TYPE = re.compile(r"^each player chooses a creature type$")
_TYPED = re.compile(r"^each player returns all creature cards of a type chosen this way from their graveyard to the battlefield$")
BINDING = "chosen_types"


def _each_type(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    return [{"do": "choose_each", "who": "each_player", "what": "creature type"}], None


def _typed(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    sel = _graveyard_selector("creature cards")
    return [{"do": "return_card", "who": f"typed:{BINDING}|{sel}", "to": "battlefield", "tapped": False, "under": "owner"}], None


TEMPLATES.extend([(_EACH_TYPE, _each_type), (_TYPED, _typed)])


def cards_of_types(plan: Any, ctx: dict[str, Any], who: str) -> list[str]:
    """``typed:<binding>|<selector key>``: the cards the selector finds that have a creature type among those chosen."""
    from app.rules import context

    name, _, key = who[len("typed:"):].partition("|")
    values = set((context.refs(ctx).get(name) or {}).get("values") or [])
    return [c for c in selectors.candidates(plan, selectors.from_key(key), ctx["controller"], ctx.get("source_card")) if plan.ch(plan.state.cards[c]).subtypes & values]


def choose_each(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import effects

    return _ask(plan, ctx, e, [p for p in plan.apnap() if p in effects._players(plan, ctx, e["who"])], [])


def _ask(plan: Any, ctx: dict[str, Any], e: dict[str, Any], order: list[str], values: list[str]) -> bool:
    from app.game.rules_state import DecisionOption  # noqa: F401  (the options come from effects._choice_options)
    from app.rules import context, effects
    from app.rules.plan import decide

    while order and order[0] not in plan.live():  # (a player who left the game chooses nothing, 800.4a)
        order = order[1:]
    if not order:
        context.refs(ctx)[e.get("as") or BINDING] = {"kind": "choice", "what": e["what"], "values": values}
        return True
    pid, rest = order[0], order[1:]
    decide(plan, player=pid, kind="choose_one", prompt=f"{ctx.get('name') or 'Choose'}: choose a {e['what']}" + (f" (already chosen: {', '.join(values)})" if values else ""),
           options=effects._choice_options(plan, ctx, e["what"]), resume={"step": "choose_each", "ctx": ctx, "e": e, "rest": rest, "values": values})
    return False


def resume_choose_each(plan: Any, d: Any, chosen: list[str]) -> None:
    from app.rules import effects

    r = d.resume
    plan.note(f"{plan.name(d.player)} chooses {chosen[0]} ({r['e']['what']})", actor=d.player)  # 101.4b
    if _ask(plan, r["ctx"], r["e"], r["rest"], [*r["values"], chosen[0]]):
        effects.continue_effects(plan, r["ctx"])


PRIMITIVES["choose_each"] = choose_each
RESUME: dict[str, Any] = {"choose_each": resume_choose_each}


# -- "Each player may put two +1/+1 counters on a creature they control. If a player does, creatures that player controls can't attack you or planeswalkers you control until your next turn."
# (Orzhov Advokist): every player, in turn order (101.4), may choose a creature they control and gets the counters; the players who did are the controllers of the creatures chosen
# (``ref:chosen_each.controller``), and the restriction is on every creature each of them controls (611.2c: a continuous effect of a resolving ability that changes no characteristic
# applies to the creatures there are, now and later). The two sentences are read as one (``rewrite``: "If a player does, creatures that player controls" is "creatures a player who did controls").
_EACH_MAY_COUNTERS = re.compile(r"^each player may put (?P<n>a|an|one|two|three) (?P<kind>[+-]\d+/[+-]\d+) counters? on a creature they control and creatures a player who did controls "
                                r"can't attack you or planeswalkers you control until your next turn$")
CHOSEN_EACH = "chosen_each"


def _each_may_counters(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    return [{"do": "player_chooses", "who": "each_player", "sel": _permanents("creature"), "n": 1, "label": "creature", "upto": True, "optional": True, "as": CHOSEN_EACH},
            {"do": "add_counters", "who": f"ref:{CHOSEN_EACH}", "kind": m["kind"], "n": _NUM.get(m["n"], 1) if m["n"] != "two" else 2},
            {"do": "until", "duration": "next_turn", "n": 1},
            {"do": "restrict", "who": f"controlled:ref:{CHOSEN_EACH}.controller|{_permanents('creature')}", "rules": ["cant_attack_player_pw:@you"]}], None


TEMPLATES.append((_EACH_MAY_COUNTERS, _each_may_counters))

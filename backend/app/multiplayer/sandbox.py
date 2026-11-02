"""The damage sandbox (docs/SPECTATOR_ACTIVITIES_MILESTONE.md §4): "was that attack actually lethal?", "what if they
had blocked differently?". For players who are out and spectators; informational only.

* **Public board** (``public_board``): the creatures on the battlefield and each player's life, poison and commander
  damage, read from the public (spectator) view and nothing else: a card that view hides stays a nameless face-down
  2/2, power, toughness and keywords are the ones the public view shows (``rules.stats``), and nothing comes from a
  hand, a library or a private choice. Building it never changes the live game.
* **What if** (``simulate``): a combat the person sets up (attackers and what they attack, blockers, power and
  toughness, a few damage keywords, life totals) worked out with the rules engine's own combat damage computation
  (``app.rules.combat.compute_combat_damage``: the first-strike and regular rounds, 510.1c-d's default division among
  blockers, trample over lethal, deathtouch, lifelink, infect and wither, commander damage). It runs on a throwaway
  table built from the scenario alone; the live game is never read, so nothing the person types can reach it. The
  state-based checks after each round are the plain ones (704.5a/c/f/g/h, 704.6c); no replacement, prevention or
  trigger is guessed.
"""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.game.factory import PlayerSetup, new_game
from app.game.resolve import NoCardInfo
from app.game.rules_state import start_rules
from app.game.state import AttackTarget, CardInstance, GameSettings, GameState
from app.rules import characteristics as chars
from app.rules.characteristics import CardInfo, Characteristics
from app.rules.plan import Plan

Keyword = Literal["first strike", "double strike", "trample", "deathtouch", "lifelink", "indestructible", "infect", "wither"]
KEYWORDS: tuple[str, ...] = ("first strike", "double strike", "trample", "deathtouch", "lifelink", "indestructible", "infect", "wither")
LETHAL_COMMANDER = 21  # 903.10a / 704.6c
LETHAL_POISON = 10  # 704.5c
_ID = r"^[A-Za-z0-9_:.#-]{1,64}$"


# --------------------------------------------------------------------------- the public board


def _num(value: str | None) -> int | None:
    try:
        return int(value) if value is not None else None
    except ValueError:
        return None


def public_board(view: dict[str, Any], state: GameState, info: CardInfo) -> dict[str, Any]:
    """The public creatures and players, from ``view`` (the SPECTATOR view of the live table). Only cards that view shows
    face up are looked up on the server, and only for their printed face (public: it is on the table); a hidden one is
    described from the view alone."""
    stats: dict[str, Any] = (view.get("rules") or {}).get("stats") or {}
    rules = view.get("rules") or {}
    out_of_game = set(rules.get("conceded") or []) | set(rules.get("lost") or {})
    creatures: list[dict[str, Any]] = []
    for cid, c in view["cards"].items():
        zone = c.get("zone", "")
        if not zone.endswith(":battlefield"):
            continue
        counters = c.get("counters") or {}
        shift = int(counters.get("+1/+1", 0)) - int(counters.get("-1/-1", 0))
        if c.get("hidden"):
            if not c.get("face_down"):
                continue
            what = c.get("face_down_as") or ""
            if what and "creature" not in what.lower():
                continue  # face down as something other than a creature ("Forest land")
            pt = re.search(r"(\d+)/(\d+)", what)
            power, toughness = (int(pt[1]), int(pt[2])) if pt else (2, 2)  # 708.2a
            entry = {"name": "Face-down creature", "power": power + shift, "toughness": toughness + shift, "keywords": [],
                     "commander": None}
        else:
            card = state.cards.get(cid)
            if card is None:
                continue
            printed = chars.of(card, info)
            stat = stats.get(cid) or {}
            if not (printed.is_creature or stat.get("creature")):
                continue
            if stat.get("pt"):
                power, toughness = int(stat["pt"][0]), int(stat["pt"][1])
            elif state.rules is not None and state.settings.automation != "off":
                power, toughness = _num(printed.power) or 0, _num(printed.toughness) or 0  # unchanged: as printed
            else:  # a manual table: printed plus the counters on it
                power, toughness = (_num(printed.power) or 0) + shift, (_num(printed.toughness) or 0) + shift
            keywords = (set(printed.keywords) | set(stat.get("gained") or [])) - set(stat.get("lost") or [])
            entry = {"name": c.get("name") or printed.name, "power": power, "toughness": toughness,
                     "keywords": [k for k in KEYWORDS if k in keywords], "commander": c.get("commander_key")}
        attacking = c.get("attacking") or {}
        creatures.append({"id": cid, "controller": c["controller"], **entry, "damage": int(c.get("damage") or 0),
                          "tapped": bool(c.get("tapped")),
                          "attacking": attacking.get("id") if attacking.get("kind") == "player" else None,
                          "blocking": c.get("blocking")})
    players = [{"id": p["id"], "name": p["name"], "color": p.get("color"), "life": p["life"],
                "poison": int((p.get("resources") or {}).get("poison", 0)),
                "commander_damage": {k: v for k, v in (p.get("commander_damage") or {}).items() if v},
                "out": bool(p.get("left")) or p["id"] in out_of_game}
               for p in view["players"]]
    commanders = {c["key"]: c["name"] for p in view["players"] for c in p.get("commanders") or [] if c.get("name")}
    return {"players": players, "creatures": creatures, "commanders": commanders}


# --------------------------------------------------------------------------- what if


class SandboxPlayer(BaseModel):
    id: str = Field(pattern=_ID)
    name: str = Field(default="", max_length=60)
    life: int = Field(default=40, ge=-9999, le=99999)
    poison: int = Field(default=0, ge=0, le=999)
    commander_damage: dict[str, int] = Field(default_factory=dict, max_length=24)


class SandboxCreature(BaseModel):
    id: str = Field(pattern=_ID)
    name: str = Field(default="Creature", max_length=80)
    controller: str = Field(pattern=_ID)
    power: int = Field(default=0, ge=-999, le=9999)
    toughness: int = Field(default=0, ge=-999, le=9999)
    damage: int = Field(default=0, ge=0, le=9999)
    keywords: list[Keyword] = Field(default_factory=list, max_length=len(KEYWORDS))
    commander: str | None = Field(default=None, max_length=64)
    attacking: str | None = Field(default=None, max_length=64)  # a player id
    blocking: str | None = Field(default=None, max_length=64)  # an attacking creature id


class Scenario(BaseModel):
    players: list[SandboxPlayer] = Field(min_length=1, max_length=6)
    creatures: list[SandboxCreature] = Field(default_factory=list, max_length=80)


class ScenarioError(ValueError):
    pass


class _SandboxPlan(Plan):
    """A read-only plan whose objects have exactly the characteristics the scenario gives them (no layers, no card data)."""

    sandbox: dict[str, Characteristics]

    def ch(self, card: CardInstance) -> Characteristics:
        return self.sandbox.get(card.id) or Characteristics(name=card.name)


def _characteristics(c: SandboxCreature, controller: str, power: int, toughness: int) -> Characteristics:
    return Characteristics(name=c.name, types=frozenset({"Creature"}), pt=(power, toughness), granted=frozenset(c.keywords),
                           on_battlefield=True, object_controller=controller, object_owner=controller)


def simulate(scn: Scenario) -> dict[str, Any]:
    """Work the scenario's combat out on a throwaway table; returns each round's damage and where everyone ends up."""
    from app.rules import combat

    seats = {p.id: f"p{i + 1}" for i, p in enumerate(scn.players)}
    if len(seats) != len(scn.players):
        raise ScenarioError("Each player appears once")
    back = {v: k for k, v in seats.items()}
    creatures = {c.id: c for c in scn.creatures}
    if len(creatures) != len(scn.creatures):
        raise ScenarioError("Each creature appears once")
    for c in scn.creatures:
        if c.controller not in seats:
            raise ScenarioError(f"{c.name}'s controller isn't at the table")
        if c.attacking is not None and c.blocking is not None:
            raise ScenarioError(f"{c.name} can't attack and block")
        if c.attacking is not None and (c.attacking not in seats or c.attacking == c.controller):
            raise ScenarioError(f"{c.name} must attack an opponent")
        if c.blocking is not None:
            att = creatures.get(c.blocking)
            if att is None or att.attacking is None:
                raise ScenarioError(f"{c.name} must block an attacking creature")
            if c.controller == att.controller:
                raise ScenarioError(f"{c.name} can't block its own controller's creature")

    state = new_game([PlayerSetup(name=p.name or p.id) for p in scn.players], settings=GameSettings(starting_life=40),
                     shuffle=False, first_player=0)
    for p in scn.players:
        ps = state.players[seats[p.id]]
        ps.life, ps.resources["poison"] = p.life, p.poison
        ps.commander_damage = {k[:64]: max(0, int(v)) for k, v in p.commander_damage.items()}
    rules = start_rules(state)
    state.rules = rules
    pt: dict[str, tuple[int, int]] = {}
    for c in scn.creatures:
        ctrl = seats[c.controller]
        card = CardInstance(id=c.id, name=c.name, owner=ctrl, controller=ctrl, zone=f"{ctrl}:battlefield", damage=c.damage,
                            commander_key=c.commander)
        if c.attacking is not None:
            card.attacking = AttackTarget(kind="player", id=seats[c.attacking])
        state.cards[c.id] = card
        state.zones.setdefault(f"{ctrl}:battlefield", []).append(c.id)
        pt[c.id] = (c.power, c.toughness)
    for c in scn.creatures:  # 509.1: listed in order, so the first blocker listed takes lethal damage first (510.1c)
        if c.blocking is not None:
            state.cards[c.id].blocking = c.blocking
            if c.blocking not in rules.blocked:
                rules.blocked.append(c.blocking)

    plan = _SandboxPlan.view(state, state.turn.active_player, NoCardInfo())
    assert isinstance(plan, _SandboxPlan)
    plan.sandbox = {cid: _characteristics(creatures[cid], state.cards[cid].controller, *pt[cid]) for cid in creatures}
    before = {pid: (state.players[s].life, state.players[s].resources.get("poison", 0), dict(state.players[s].commander_damage))
              for pid, s in seats.items()}
    rounds: list[dict[str, Any]] = []
    died: dict[str, str] = {}
    steps: list[combat.Round] = ["first", "second"] if combat.has_first_strike_round(plan) else ["only"]
    for rnd in steps:
        dmg = combat.compute_combat_damage(plan, rnd)
        dealt = [{"source": src, "target": back.get(tgt, tgt), "amount": n} for src, tgt, n in dmg.dealt]
        # 510.2: all of it at once. Damage to a creature is marked (wither and infect: -1/-1 counters, 702.80, 702.90)
        for cid, n in dmg.creatures.items():
            state.cards[cid].damage += n
        for cid, n in dmg.wither.items():
            power, toughness = pt[cid]
            pt[cid] = (power - n, toughness - n)
        for pid, n in dmg.players.items():
            state.players[pid].life -= n
        for pid, n in dmg.poison.items():
            state.players[pid].resources["poison"] = state.players[pid].resources.get("poison", 0) + n
        for (pid, key), n in dmg.commander.items():
            state.players[pid].commander_damage[key] = state.players[pid].commander_damage.get(key, 0) + n
        for src, n in dmg.lifelink.items():  # 702.15b: its controller gains that much life
            state.players[state.cards[src].controller].life += n
        # 704.5f-h: zero toughness, lethal damage, deathtouch damage (indestructible survives the last two)
        for cid in list(creatures):
            card = state.cards[cid]
            if cid in died:
                continue
            toughness = pt[cid][1]
            sturdy = "indestructible" in creatures[cid].keywords
            if toughness <= 0:
                died[cid] = "toughness 0 or less"
            elif not sturdy and card.damage >= toughness:
                died[cid] = "lethal damage"
            elif not sturdy and cid in dmg.deathtouched:
                died[cid] = "deathtouch"
            else:
                continue
            zone = f"{card.controller}:battlefield"  # it leaves combat (506.4): the next round goes on without it
            state.zones[zone] = [x for x in state.zones[zone] if x != cid]
            card.zone, card.attacking, card.blocking = f"{card.controller}:graveyard", None, None
        plan.sandbox.update({cid: _characteristics(creatures[cid], state.cards[cid].controller, *pt[cid]) for cid in creatures})
        rounds.append({"round": rnd, "dealt": dealt})

    players = []
    for p in scn.players:
        ps = state.players[seats[p.id]]
        life0, poison0, cmd0 = before[p.id]
        poison = ps.resources.get("poison", 0)
        reasons = []
        if ps.life <= 0:
            reasons.append("0 or less life")  # 704.5a
        if poison >= LETHAL_POISON:
            reasons.append("10 or more poison counters")  # 704.5c
        reasons += [f"21 or more commander damage ({key})" for key, n in ps.commander_damage.items() if n >= LETHAL_COMMANDER]  # 704.6c
        players.append({"id": p.id, "life_before": life0, "life": ps.life, "poison_before": poison0, "poison": poison,
                        "commander_damage": {k: n for k, n in ps.commander_damage.items() if n != cmd0.get(k, 0) or n >= LETHAL_COMMANDER},
                        "loses": reasons})
    out_creatures = [{"id": cid, "died": died.get(cid), "damage": state.cards[cid].damage, "power": pt[cid][0],
                      "toughness": pt[cid][1]} for cid in creatures]
    return {"rounds": rounds, "players": players, "creatures": out_creatures}

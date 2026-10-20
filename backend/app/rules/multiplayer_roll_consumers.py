"""Per-player roll actors and complete kept-result vectors feed native effects."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan

_CHAOS = "Each player rolls a d20. If one or more opponents had the highest result, ~ can't attack those players or planeswalkers they control this combat."
_CELEBR = "At the beginning of combat on your turn, roll two six-sided dice. For each result of 1, ~ gets +1/+1 until end of turn. For each other result, it gains the indicated ability until end of turn. If you rolled doubles, it also gains double strike until end of turn."
_ROWS = ["• 2 — menace", "• 3 — vigilance", "• 4 — lifelink", "• 5 — flying", "• 6 — indestructible"]


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    text = " ".join(body.split())
    text = text[:1].upper() + text[1:]
    if text == _CHAOS:
        return [{"do": "multiplayer_roll", "kind": "chaos_start"}], None, False
    if (
        text
        == "Roll a six-sided die. When you do, ~ deals 1 damage to each of up to X target creatures, where X is the result."
    ):
        from app.rules import scripts

        got = scripts.parse_effects("~ deals 1 damage to each of up to X target creatures.")
        assert got is not None
        ability = {
            "kind": "triggered",
            "trigger": "reflexive",
            "effects": got[0],
            "optional": False,
            **scripts.target_fields(got[1]),
            "x_event": True,
        }
        return (
            [
                {"do": "roll", "sides": 6, "count": 1},
                {"do": "reflexive", "cond": {}, "roll_result": True, "ability": ability},
            ],
            None,
            False,
        )
    return None


def merge_lines(ch: Any, out: dict[int, Any]) -> None:
    from app.rules import scripts

    for offset, ab in enumerate(ch.abilities):
        if not ab.text.startswith("At the beginning of combat on your turn, roll two six-sided dice."):
            continue
        if scripts.self_text(ab.text, ch.name) != _CELEBR:
            continue
        rows = ch.abilities[offset + 1 : offset + 6]
        if [a.text for a in rows] != _ROWS:
            continue
        out[ab.index] = {
            "kind": "triggered",
            "trigger": "step:begin_combat:you",
            "effects": [{"do": "roll", "sides": 6, "count": 2}, {"do": "multiplayer_roll", "kind": "celebr"}],
            "optional": False,
            "target": None,
        }
        for row in rows:
            out[row.index] = {"kind": "static", "static": "merged", "merged_into": ab.index}


def consume(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import coin_recipes

    kind = e["kind"]
    steps: list[dict[str, Any]] = []
    if kind == "celebr":
        results = [int(n) for n in ctx.get("dice") or []]
        ones = results.count(1)
        if ones:
            steps.append({"do": "pump", "who": "self", "p": ones, "t": ones})
        keywords = {2: "menace", 3: "vigilance", 4: "lifelink", 5: "flying", 6: "indestructible"}
        gained = [keywords[n] for n in results if n in keywords]
        if len(results) == 2 and results[0] == results[1]:
            gained.append("double strike")
        if gained:
            steps.append({"do": "grant", "who": "self", "keywords": gained})
    elif kind == "chaos_start":
        # The controller of the original trigger stays fixed; only the actor of
        # each roll changes. Native roll continuations serialize this context.
        ctx["chaos_controller"] = ctx["controller"]
        ctx["chaos_players"] = plan.apnap()
        ctx["chaos_results"] = {}
        steps = [{"do": "multiplayer_roll", "kind": "chaos_next"}]
    elif kind == "chaos_record":
        ctx["chaos_results"][ctx["controller"]] = int(ctx.get("die") or 0)
        ctx["controller"] = ctx["chaos_controller"]
        steps = [{"do": "multiplayer_roll", "kind": "chaos_next"}]
    elif kind == "chaos_next":
        players = ctx["chaos_players"]
        while players and players[0] not in plan.live():
            players.pop(0)
        if players:
            ctx["controller"] = players.pop(0)
            steps = [
                {"do": "roll", "sides": 20, "count": 1},
                {"do": "multiplayer_roll", "kind": "chaos_record"},
            ]
        else:
            ctx["controller"] = ctx["chaos_controller"]
            results = ctx["chaos_results"]
            highest = max(results.values(), default=0)
            steps = [
                {
                    "do": "restrict",
                    "who": "self",
                    "duration": "end_of_combat",
                    "rules": ["cant_attack_player_pw:" + pid],
                }
                for pid, result in results.items()
                if pid != ctx["controller"] and result == highest
            ]
    coin_recipes.insert(ctx, steps)
    return True


PRIMITIVES = {"multiplayer_roll": consume}

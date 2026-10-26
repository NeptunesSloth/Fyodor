p='app/rules/wave110c_misc.py'
t=open(p).read()
t=t.replace('''def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts
''','''PANDEMONIUM = "Whenever a creature enters, that creature's controller may have it deal damage equal to its power to any target of their choice."


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    if ability.kind == "triggered" and scripts.self_text(ability.text, ch.name) == PANDEMONIUM:  # Pandemonium ruling 2006-09-25: its controller controls the ability, the entering creature's controller chooses the target (target_choice) and whether it deals the damage
        d = scripts.define(replace(ability, text="Whenever a creature enters, that creature deals damage equal to its power to any target."), ch)
        return None if d is None else {**d, "target_choice": "event_player", "effects": [{"do": "pandemonium110c"}, *d["effects"]]}
''',1)
code='''def pandemonium(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Pandemonium: the entering creature's controller (not the trigger's controller) decides whether the creature deals the damage."""
    from app.game.rules_state import DecisionOption
    from app.rules import effects
    from app.rules.plan import decide

    who = effects._players(plan, ctx, "event_player")
    if len(who) != 1:
        ctx["next"] = len(ctx["effects"])
        return True
    decide(plan, player=who[0], kind="choose_one", prompt="Pandemonium: have the creature deal damage equal to its power to the target?",
           options=[DecisionOption(id="yes", label="Yes"), DecisionOption(id="no", label="No")], resume={"step": "pandemonium110c", "ctx": ctx},
           source=plan.state.cards.get(ctx.get("source_card") or ""))
    return False


def resume_pandemonium(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import effects

    ctx = d.resume["ctx"]
    if chosen[0] != "yes":
        ctx["next"] = len(ctx["effects"])
    effects.continue_effects(plan, ctx)


'''
i=t.index('WARP_WORLD = (')
t=t[:i]+code+t[i:]
t=t.replace('RESUME = {"prodder110c"','RESUME = {"pandemonium110c": resume_pandemonium, "prodder110c"',1)
t=t.replace('PRIMITIVES = {"shuffle_dead110c"','PRIMITIVES = {"pandemonium110c": pandemonium, "shuffle_dead110c"',1)
open(p,'w').write(t)

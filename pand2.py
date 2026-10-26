p='app/rules/triggers.py'
t=open(p).read()
old='''            if t.ability.get("target_choice") == "defending100j":'''
new='''            if t.ability.get("target_choice") == "entering110c":  # -- Pandemonium (wave 110C) -- the entering permanent's controller picks the target (ruling 2006-09-25)
                from app.rules import wave110c_misc

                if (entering := wave110c_misc.entering_controller(plan, t.event)) is None:
                    r.pending_triggers = [p for p in r.pending_triggers if p.id != t.id]
                    plan.note(f"{t.name}'s ability has no player to choose its target and is removed")
                    return True
                choice_player = entering
'''+old
assert t.count(old)==1
t=t.replace(old,new)
open(p,'w').write(t)
p='app/rules/wave110c_misc.py'
t=open(p).read()
t=t.replace('"target_choice": "event_player"','"target_choice": "entering110c"')
t=t.replace('''    who = effects._players(plan, ctx, "event_player")
    if len(who) != 1:
        ctx["next"] = len(ctx["effects"])
        return True
    decide(plan, player=who[0],''','''    who = entering_controller(plan, ctx.get("event"))
    if who is None:
        ctx["next"] = len(ctx["effects"])
        return True
    decide(plan, player=who,''')
t=t.replace('''def pandemonium(plan''','''def entering_controller(plan: Plan, event: Any) -> str | None:
    """The controller of the permanent an enter event is about (as it last existed if it already left, 608.2h)."""
    card_id = event.get("card") if isinstance(event, dict) else getattr(event, "card", None)
    card = plan.state.cards.get(card_id or "")
    pid = card.controller if card is not None and card.zone.endswith(":battlefield") else getattr(plan.rules.lki.get(
        (event.get("new_object_id") if isinstance(event, dict) else getattr(event, "new_object_id", None)) or ""), "controller", None)
    return pid if pid in plan.live() else None


def pandemonium(plan''',1)
open(p,'w').write(t)

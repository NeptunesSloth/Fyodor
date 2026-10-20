"""Explicit unimported untap-model descriptor and saved-callback staging."""
from app.rules import effects, scripts
from app.rules import untap_attempts45 as model


def install():
    original = scripts.define

    def define(ability, ch):
        return model.definition(ability.text) or original(ability, ch)

    scripts.define = define
    effects.RESUME.update(model.RESUME)
    from app.rules import engine

    engine.RESUME.update(model.RESUME)

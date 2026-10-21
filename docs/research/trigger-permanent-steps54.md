# Mask of Intolerance and Zealots en-Dal

These exact ability wrappers use existing native step events, selectors, count values, and intervening conditions at both triggering and resolution. No new runtime primitive or shared algorithm is introduced.

Mask evaluates the frozen upkeep player's current controlled lands and counts distinct basic land types. One land with all five types suffices; overlapping dual lands do not count duplicated types. The recipient remains the upkeep player after source control changes or departure. Zealots checks that no controlled nonland permanent lacks white: white multicolor permanents qualify, colorless nonlands fail, lands of any color or additional permanent type are excluded, and an empty nonland group qualifies.

Production validation passed24 native checks, including2 genuine fresh-process continuations, and64 related checks. Scoped mypy and Ruff pass. Native paid spells prove changing the condition before resolution, no retroactive triggering, opponent/control/owner boundaries, original-source departure, cleanup, a real Nylea's Presence granting all basic types to one land, white multicolor Watchwolf, Dryad Arbor, and artifact land exclusions.

Session evidence: `/tmp/trigger54-permanent-step-production.log`, `/tmp/trigger54-permanent-step-final-types.log`, `/tmp/trigger54-permanent-step-production-ruff.log`; full actual-database canonical and official-ruling responses `/tmp/trigger54-permanent-step-{canonical,rulings}.json`. Exact admissions are tracked in [the durable trigger manifest](trigger50-admitted-manifest.json), not a global catalog total.

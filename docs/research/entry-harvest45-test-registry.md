# Test-only scheduler continuation registration

The entry-harvest45 prototype fixture registered its continuation only in effects.RESUME. The engine copies those entries into its own dispatch registry when imported. If another test had already imported the engine, model decisions failed with KeyError despite the test fixture registering effects correctly.

The fixture now monkeypatches both registries explicitly, with normal pytest teardown. Production registration is unchanged; the prototype remains unimported and no card is admitted.

Reproduction with engine pre-imported: selected test failed before the repair (KeyError entry_harvest45); the complete eleven-test file passed after the repair. Ruff for the changed test passed. Logs are preserved beside this note.

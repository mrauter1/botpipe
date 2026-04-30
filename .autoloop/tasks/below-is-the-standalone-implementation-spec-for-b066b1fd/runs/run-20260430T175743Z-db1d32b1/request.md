Update the maintained simple-surface signature coverage to match the implemented scoped-state API without changing the shipped authoring behavior.

Required work:

- Fix `tests/unit/test_simple_surface.py::test_canonical_simple_signatures_expose_only_canonical_argument_names`.
- Preserve the current public simple authoring surface in `autoloop/simple.py`.
- The expected canonical signatures must include:

```python
step(
    prompt,
    *,
    name=None,
    reads=(),
    requires=(),
    writes=(),
    scope=None,
    item_state=None,
    routes=None,
    before=None,
    after=None,
    on_route=None,
    control_schema=None,
    retry=None,
    session=None,
    control_routes=True,
)
```

```python
produce_verify_step(
    *,
    producer_prompt,
    verifier_prompt,
    name=None,
    reads=(),
    requires=(),
    verifier_reads=(),
    verifier_requires=(),
    producer_writes=(),
    verifier_writes=(),
    scope=None,
    routes=None,
    state=None,
    item_state=None,
    before_producer=None,
    after_producer=None,
    before_verifier=None,
    after_verifier=None,
    on_route=None,
    control_schema=None,
    retry=None,
    session=None,
    verifier_session=None,
    control_routes=True,
)
```

- Keep `python_step(...)` signature coverage aligned with the existing implementation.
- Re-run the focused suite that previously reported one failure in `test_canonical_simple_signatures_expose_only_canonical_argument_names` and verify it is fully green.

Do not reopen the bridge-removal, hook-rerouting, state, scoped-state, required-write, or history implementations unless the signature test reveals another concrete mismatch.

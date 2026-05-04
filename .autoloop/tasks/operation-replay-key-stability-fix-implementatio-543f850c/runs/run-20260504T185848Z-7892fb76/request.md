## Operation Replay Key Stability Fix — Implementation Spec

### Problem Statement

The operation replay key in `autoloop/core/operations.py` currently includes the `callsite` string, which encodes `filename:function:lineno`. Any line number shift in source code — even an unrelated edit above the call — produces a different key, causing a silent cache miss with no observable signal. The `replay_mismatch_behavior` warn/fail path never fires because a miss produces `_MISSING` with no warning, not a fingerprint comparison.

The fix is to remove `callsite` from the replay key and the occurrence counter, while keeping it in the fingerprint. A line number shift then produces a key hit with a fingerprint mismatch, triggering the configured `warn` or `fail` behavior. Function renames and file moves gain the same improvement.

---

### Files to Modify

- `autoloop/core/schema_registry.py`
- `autoloop/core/operations.py`

No other files require changes.

---

### Change 1 — `autoloop/core/schema_registry.py`

Bump the operation replay schema version from `v1` to `v2`. The key structure is incompatible with v1 stores so existing cached values cannot be reused.

```python
# Before
OPERATION_REPLAY_SCHEMA = "autoloop.operation_replay/v1"

# After
OPERATION_REPLAY_SCHEMA = "autoloop.operation_replay/v2"
```

---

### Change 2 — `autoloop/core/operations.py`

#### 2a. `_next_occurrence` — remove `callsite` from signature and counter key

The occurrence counter must not include callsite. If it did, two different callsites in the same step would each produce occurrence=1, and their replay keys (which no longer include callsite) would collide.

```python
# Before
def _next_occurrence(runtime: OperationRuntime, operation_kind: str, callsite: str) -> int:
    key = json.dumps(
        {
            "workflow_name": runtime.workflow_name,
            "step_name": runtime.step_name,
            "step_visit": runtime.step_visit,
            "operation_kind": operation_kind,
            "callsite": callsite,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    next_value = runtime.occurrence_counts.get(key, 0) + 1
    runtime.occurrence_counts[key] = next_value
    return next_value

# After
def _next_occurrence(runtime: OperationRuntime, operation_kind: str) -> int:
    key = json.dumps(
        {
            "workflow_name": runtime.workflow_name,
            "step_name": runtime.step_name,
            "step_visit": runtime.step_visit,
            "operation_kind": operation_kind,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    next_value = runtime.occurrence_counts.get(key, 0) + 1
    runtime.occurrence_counts[key] = next_value
    return next_value
```

#### 2b. `_operation_replay_key` — remove `callsite` from signature and payload

```python
# Before
def _operation_replay_key(
    runtime: OperationRuntime,
    operation_kind: str,
    callsite: str,
    occurrence: int,
) -> str:
    payload = {
        "workflow_name": runtime.workflow_name,
        "step_name": runtime.step_name,
        "step_visit": runtime.step_visit,
        "operation_kind": operation_kind,
        "callsite": callsite,
        "occurrence_index": occurrence,
    }
    return _sha256_json(payload)

# After
def _operation_replay_key(
    runtime: OperationRuntime,
    operation_kind: str,
    occurrence: int,
) -> str:
    payload = {
        "workflow_name": runtime.workflow_name,
        "step_name": runtime.step_name,
        "step_visit": runtime.step_visit,
        "operation_kind": operation_kind,
        "occurrence_index": occurrence,
    }
    return _sha256_json(payload)
```

#### 2c. `_run_operation` — update the two call sites

`callsite_id` is still computed and still passed to `_operation_fingerprint` — that is unchanged. Only the calls to `_next_occurrence` and `_operation_replay_key` are updated.

```python
# Before
occurrence = _next_occurrence(runtime, spec.operation_kind, callsite_id)
replay_key = _operation_replay_key(runtime, spec.operation_kind, callsite_id, occurrence)

# After
occurrence = _next_occurrence(runtime, spec.operation_kind)
replay_key = _operation_replay_key(runtime, spec.operation_kind, occurrence)
```

The lines immediately before and after are untouched:

```python
callsite_id = callsite or _discover_callsite()          # unchanged
occurrence = _next_occurrence(runtime, spec.operation_kind)           # changed
replay_key = _operation_replay_key(runtime, spec.operation_kind, occurrence)  # changed
fingerprint = _operation_fingerprint(                   # unchanged
    runtime,
    spec=spec,
    prompt=resolved_prompt,
    session=session,
    callsite=callsite_id,                               # callsite still here
    occurrence=occurrence,
)
```

#### 2d. `_load_replay_store` — migrate v1 stores

Replace the inline lambda migrator with a named function that discards all records from v1 stores. Records cannot be migrated because the key format changed. Attempts history is preserved since it has diagnostic value only and does not affect correctness.

Add this function anywhere before `_load_replay_store` in the file:

```python
def _migrate_operation_replay_store(payload: dict[str, Any]) -> dict[str, Any]:
    """Migrate schemaless or v1 operation replay stores to v2.

    Records are discarded because v1 replay keys included the callsite string
    and are structurally incompatible with v2 keys. Attempts history is
    preserved for diagnostic purposes.
    """
    return {
        "schema": OPERATION_REPLAY_SCHEMA,
        "records": {},
        "attempts": payload.get("attempts", [])
        if isinstance(payload.get("attempts"), list)
        else [],
    }
```

Then update `_load_replay_store`:

```python
# Before
validate_persisted_schema(
    payload,
    expected=OPERATION_REPLAY_SCHEMA,
    artifact_name=str(path),
    legacy_migrator=lambda value: migrate_schemaless_payload(value, expected=OPERATION_REPLAY_SCHEMA),
)

# After
validate_persisted_schema(
    payload,
    expected=OPERATION_REPLAY_SCHEMA,
    artifact_name=str(path),
    legacy_migrator=_migrate_operation_replay_store,
)
```

---

### Correctness Proof — Occurrence Counter

The occurrence counter is the critical invariant. It must assign a unique integer to every operation call within a single step execution so that replay keys are collision-free.

**Before this fix**, the counter was keyed by `(workflow, step, visit, operation_kind, callsite)`. Two callsites A and B maintained independent counters, each starting at 1. Uniqueness was guaranteed by callsite being in the replay key.

**After this fix**, the counter is keyed by `(workflow, step, visit, operation_kind)`. All calls of the same operation kind within a step share one counter. Uniqueness is guaranteed by the counter always incrementing, so each call gets a distinct occurrence number regardless of which callsite generated it.

Worked example — one step, two `llm()` calls at different lines:

```python
def my_step(ctx):
    x = llm("first prompt")    # callsite A, file.py:fn:10
    y = llm("second prompt")   # callsite B, file.py:fn:11
```

| Call | Before | After |
|------|--------|-------|
| `x` | counter["...llm...callsite_A"] = 1, key = hash(step, llm, callsite_A, occ=1) | counter["...llm..."] = 1, key = hash(step, llm, occ=1) |
| `y` | counter["...llm...callsite_B"] = 1, key = hash(step, llm, callsite_B, occ=1) | counter["...llm..."] = 2, key = hash(step, llm, occ=2) |

Both produce two distinct keys. ✓

Loop case — same callsite, N iterations:

```python
for item in items:
    result = llm("process")    # same callsite every iteration
```

Before: counter["...llm...callsite_A"] increments each iteration → occurrences 1, 2, 3 → distinct keys.
After: counter["...llm..."] increments each iteration → occurrences 1, 2, 3 → distinct keys. ✓

On resume the loop runs again from the beginning of the step. Occurrences 1, 2, 3 are assigned in the same order. Keys match. Replay works. ✓

Mixed kinds — `llm()` and `classify()` in same step:

Both before and after, `llm` and `classify` have separate counters because `operation_kind` is in the counter key. No cross-kind collision is possible. ✓

Non-deterministic branching — two `llm()` callsites inside a conditional:

```python
for item in items:
    if condition:
        result = llm("path A")    # callsite A
    else:
        result = llm("path B")    # callsite B
```

Before: callsite A and callsite B had independent counters. Path A iteration 1 → `(step, llm, callsite_A, occ=1)`. Path B iteration 1 → `(step, llm, callsite_B, occ=1)`. Distinct keys. If the branch sequence changes on resume, the occurrence-to-callsite mapping changes but the keys still hit — wrong values could be replayed silently.

After: both share one counter. The occurrence sequence reflects the actual execution order. If the branch sequence changes on resume, occ=1 is reached by a different callsite than before. The key hits, but the fingerprint includes `callsite`, which changed — fingerprint mismatch fires and the configured behavior applies. This is correct. ✓

---

### Behavioral Change Table

| Scenario | Before | After |
|----------|--------|-------|
| Line number shifts, same prompt and config | Silent cache miss, fresh provider call, no signal | Key hit, fingerprint mismatch → `warn` event or `fail` exception per config |
| Function renamed, same prompt and config | Silent cache miss, fresh provider call, no signal | Key hit, fingerprint mismatch → `warn` event or `fail` exception per config |
| File moved, same prompt and config | Silent cache miss, fresh provider call, no signal | Key hit, fingerprint mismatch → `warn` event or `fail` exception per config |
| Prompt text changes | Key hit, fingerprint mismatch → configured behavior | Key hit, fingerprint mismatch → configured behavior (unchanged) |
| Model config changes | Key hit, fingerprint mismatch → configured behavior | Key hit, fingerprint mismatch → configured behavior (unchanged) |
| New `llm()` call inserted before existing sequential calls | Callsite line numbers of subsequent calls shift → their keys change → silent cache misses | Occurrence numbers of subsequent calls shift → their keys change → silent cache misses. Mechanism differs, outcome the same. |
| New `llm()` call inserted before a loop | All loop iteration keys shift → silent cache misses for all iterations | All loop iteration occurrence numbers shift → silent cache misses for all iterations. Mechanism differs, outcome the same. |
| Loop, same callsite N iterations, deterministic | N distinct occurrences via per-callsite counter, N distinct keys, correct replay | N distinct occurrences via shared counter, N distinct keys, correct replay |
| Two callsites A and B in same step, deterministic execution order | Each has own counter starting at 1; callsite in key ensures no collision | Shared counter; occurrence increments ensure no collision |
| Non-deterministic branching, branch sequence changes on resume | Wrong value may be replayed silently — occurrence-to-callsite mapping changes but keys still hit | Fingerprint mismatch fires — callsite in fingerprint detects the change, configured behavior applies |
| Existing v1 `operation_replay.json` on resume | Records used if keys match | Records discarded via migration; all operations run fresh, stored under v2 keys |

---

### Limitations

**Insertion before sequential calls or a loop.** If a new `llm()` or `classify()` call is inserted before existing calls in the same step, all subsequent calls shift their occurrence numbers. On resume those calls get silent cache misses rather than fingerprint mismatches, re-running the provider with no signal. This is the same behavior as before the fix — the fix does not make it worse, but does not solve it.

**The fundamental limit.** Stable replay across structural code changes within a step — reordering calls, inserting calls in the middle, removing calls — requires either explicit developer-supplied stable identifiers on each call, or content-addressed keying on prompt text alone. Neither is implemented here. This fix narrows the gap for the common case of incidental source changes that do not alter the step's call structure or execution order.

---

### What Is Explicitly Not Changed

- `_operation_fingerprint` — `callsite` stays in the fingerprint payload. This is correct: a callsite change triggers a fingerprint mismatch on the next resume, giving the configured signal.
- `_discover_callsite` — unchanged.
- `_run_operation` call to `_operation_fingerprint` — `callsite=callsite_id` argument unchanged.
- The record written to `replay_store["records"][replay_key]` still includes `"callsite": callsite_id` as a stored field for debuggability. That field is read only by humans inspecting the JSON, not by any code path.
- `llm_call`, `classify_call`, `execute_step_operation` public signatures — unchanged.
- `OPERATION_REPLAY_SCHEMA` constant name in `schema_registry.py` — unchanged, only the value changes.

---

### Verification Checklist for Codex

After implementing, verify:

1. `_next_occurrence` signature has two parameters: `runtime` and `operation_kind`.
2. `_operation_replay_key` signature has three parameters: `runtime`, `operation_kind`, and `occurrence`.
3. The `callsite` variable is still computed in `_run_operation` and still passed to `_operation_fingerprint`.
4. `OPERATION_REPLAY_SCHEMA` value in `schema_registry.py` is `"autoloop.operation_replay/v2"`.
5. `_migrate_operation_replay_store` is a named module-level function, not a lambda.
6. `_load_replay_store` passes `_migrate_operation_replay_store` to `validate_persisted_schema`, not the old lambda.
7. No other call sites for `_next_occurrence` or `_operation_replay_key` exist in the codebase — grep confirms they are only called from `_run_operation`.

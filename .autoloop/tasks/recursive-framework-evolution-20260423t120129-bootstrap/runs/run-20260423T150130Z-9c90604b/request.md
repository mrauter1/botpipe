The current codebase already implements the hard architectural pieces: internal `core/`, strict root `workflow` shim, repo-root workflow packages, task → workflow → runs workspace layout, message-first runs, `-wf`, class- and name-based `ctx.invoke_workflow(...)`, workflow-folder git scoping, and package-local `workflows/autoloop_v1/` parity. The remaining gaps are boundary/compatibility gaps: the public CLI still exposes `--provider-factory`, the runtime session payload still reads/writes `thread_id`, and the recursive wrapper plus templates still retain legacy CLI and legacy repo-shape assumptions. 

## Standalone remediation plan

### 0. Scope and governing rule

This remediation is **greenfield**. Do **not** preserve backward compatibility for CLI flags, environment-variable escape hatches, session payload aliases, or recursive-wrapper legacy paths. Preserve **feature compatibility only**:

* the CLI must still run, resume, answer, inspect, and scaffold workflows;
* provider resumability must still work;
* Autoloop-v1 parity must still work under the general runtime;
* the recursive wrapper must still be able to drive package-based runs. 

The only gaps to fix in this pass are:

1. remove the **public** `--provider-factory` surface and replace it with a strictly public provider-selection path;
2. remove `thread_id` as a framework/runtime compatibility field while preserving provider resumability through a canonical session identifier;
3. remove all remaining **legacy CLI mode** and **old repo layout** assumptions from the recursive wrapper and its templates;
4. update docs and tests so the repo enforces the cleaned-up contract. 

---

### 1. Gap 1 — remove the public `--provider-factory` escape hatch

#### 1.1 Target state

The public CLI must not expose any provider-construction escape hatch such as:

* `--provider-factory`
* `AUTOLOOP_PROVIDER_FACTORY`
* `module:function` provider loader strings
* any help text or docs that present provider factory injection as a user-facing option

Public provider selection must happen through **typed runtime config** and **generic provider flags** only. The public contract should support:

* provider selection by name, for example `codex` or `claude`;
* provider model override;
* provider effort/reasoning override. 

#### 1.2 Required implementation changes

##### A. `runtime/cli.py`

Make these changes:

* remove `--provider-factory` from the shared mutating-parser options;
* remove all help text mentioning provider factories;
* remove `AUTOLOOP_PROVIDER_FACTORY` fallback logic;
* stop importing or using `load_provider_factory` inside the normal public CLI path;
* add a public generic provider selector if you want a CLI-level override, for example:

  * `--provider`
  * keep `--model`
  * keep `--model-effort`

Keep the existing `provider_factory` **keyword argument** on `cli.main(...)` only as a **non-public test/programmatic injection seam**. It must not be reachable from the parser, docs, help text, env vars, or public contract. That seam is acceptable because it is not user-facing.

##### B. `runtime/config.py`

Extend the typed config merge path so provider choice is fully public without factories:

* add support for a CLI-level `--provider` override, merged into `ResolvedRuntimeConfig.provider.name`;
* keep `model` / `model_effort` overrides typed and public;
* do not add any “factory” field to public config.

##### C. Introduce a built-in provider backend resolver

Create a new module, for example:

* `runtime/provider_backends.py`

with a public internal function:

```python
def resolve_provider_backend(*, config: ResolvedRuntimeConfig) -> LLMProvider:
    ...
```

Required behavior:

* dispatch on `config.provider.name`;
* build the provider implementation for `codex` and `claude` through framework-owned adapters;
* do not accept `module:function` strings;
* if a selected provider backend is unavailable in the current environment, raise a precise `ConfigError`.

Important: if the repo does not yet contain real provider adapters, still implement the resolver boundary now and make it the only public CLI resolution path. The CLI contract fix must not be blocked on preserving the old factory escape hatch.

##### D. `runtime/runner.py`

* delete `load_provider_factory(...)` if it is no longer needed anywhere;
* do not reintroduce public factory-based provider resolution through helper functions;
* keep `run_workflow_package(..., provider=...)` as the programmatic execution surface; that is fine.

#### 1.3 Test updates

Update or replace these tests:

* `tests/runtime/test_package_cli.py::test_cli_mutating_commands_accept_public_provider_factory_flag`
* any tests that assert or rely on `--provider-factory`
* any tests that rely on `AUTOLOOP_PROVIDER_FACTORY`

Add these tests:

* help text does **not** contain `--provider-factory`;
* CLI rejects `--provider-factory` as an unknown argument;
* public provider selection works through typed config and/or `--provider`;
* `cli.main(..., provider_factory=...)` still works as a **non-public** test injection seam.

#### 1.4 Doc updates

Update:

* `docs/architecture.md`
* `docs/authoring.md`

Required doc changes:

* public CLI examples must not mention provider factories;
* provider selection must be documented only through typed config and generic flags;
* do not document the test-only injection seam. 

#### 1.5 Acceptance criteria

This gap is fixed when all of the following are true:

* `autoloop --help` and mutating subcommand help show no `--provider-factory`;
* there is no `AUTOLOOP_PROVIDER_FACTORY` public path;
* no public docs mention provider factories;
* provider construction happens only through typed provider selection;
* tests still have a non-public injected fake-provider path.

---

### 2. Gap 2 — remove `thread_id` from the framework/runtime model while preserving provider resumability

#### 2.1 Target state

Provider resumability is still required, but the framework must treat the resume identifier as a **canonical opaque session id**, not as a provider-specific `thread_id`.

The framework/runtime payload schema must use:

* `session_id` as the canonical continuation identifier;
* `provider_metadata` for optional provider-specific extra state.

The framework/runtime must no longer:

* read `thread_id` as a compatibility alias;
* write `thread_id` into persisted session payloads;
* expose `thread_id` in runtime metadata or docs. 

#### 2.2 Canonical session payload schema

Make `runtime/stores/filesystem.py` persist only this canonical shape:

```json
{
  "mode": "persistent",
  "provider": "codex",
  "session_id": "opaque-provider-session-id-or-null",
  "provider_metadata": {},
  "model_override": null,
  "effort_override": null,
  "pending_clarification_note": null,
  "created_at": "2026-04-23T00:00:00+00:00",
  "last_used_at": null
}
```

Rules:

* `session_id` is the only canonical cross-provider continuation field;
* if a provider internally calls its continuation handle a thread id, that name stays inside the provider adapter only;
* if provider-specific extra fields are needed, keep them under `provider_metadata`, not as framework-owned top-level keys.

#### 2.3 Required implementation changes

##### A. `runtime/stores/filesystem.py`

Make these exact changes:

* in `load_session_payload(...)`:

  * remove fallback `thread_id -> session_id`;
  * remove `thread_id` from returned metadata;
  * stop treating missing `provider` as a cue to infer Codex/thread compatibility;
* in `write_session_payload(...)` and `_session_payload_from_values(...)`:

  * stop writing `thread_id`;
  * stop mirroring `session_id` into `thread_id` for Codex;
* in `ensure_session_payload_placeholder(...)`:

  * emit the new canonical schema only.

##### B. Session binding semantics

Keep the framework contract as:

* `SessionBinding.session_id` is the single continuation id;
* providers update it through the provider protocol;
* checkpoints and session snapshots remain unchanged apart from removal of `thread_id` compatibility.

##### C. Provider adapters

In the provider backend layer introduced above:

* map provider continuation state to and from `SessionBinding.session_id`;
* if a provider has an internal thread identifier, translate it privately inside the adapter;
* do not surface provider-specific naming in the generic runtime.

##### D. `workflows/autoloop_v1/parity.py`

This file already reads `session_id` through `load_session_payload(...)`. Keep that behavior. The parity extension must continue to work unchanged after the schema cleanup. Do not add any new `thread_id` alias path. 

#### 2.4 Test updates

Update or replace any session-store/runtime tests that mention or assert `thread_id`.

Add these tests:

* placeholder session payload contains `session_id` and **does not** contain `thread_id`;
* roundtrip session persistence preserves `session_id` and `provider_metadata` only;
* provider resumability still works through `session_id`;
* active code/docs/tests no longer refer to `thread_id` except inside a provider adapter if one truly needs that term.

Strengthen strictness tests so active framework/runtime surfaces forbid `thread_id` in:

* runtime docs,
* runtime store schema,
* compatibility tests,
* user-facing help.

#### 2.5 Doc updates

Update:

* `docs/architecture.md`
* `docs/authoring.md`

Required doc language:

* resumability uses an opaque provider continuation token stored as `session_id`;
* the framework does not standardize on `thread_id`;
* do not document any backward-compatibility alias.

#### 2.6 Acceptance criteria

This gap is fixed when all of the following are true:

* no framework/runtime code reads or writes `thread_id`;
* session payloads use only `session_id`;
* provider resumability still works;
* docs describe provider resumability in terms of `session_id` / opaque continuation ids only. 

---

### 3. Gap 3 — remove legacy CLI compatibility and old repo assumptions from the recursive wrapper and templates

The current recursive wrapper still detects a legacy CLI mode and contains branches that emit old-style calls such as `--intent`, `--pairs`, `--task-id`, and legacy `--resume` handling. Its bootstrap/cycle templates still point to obsolete paths like `src/autoloop/...` and the old monolithic runner shape. That is incompatible with the current package-based, greenfield architecture. 

#### 3.1 Target state

The recursive wrapper must assume **package CLI only**.

It must not:

* detect legacy CLI mode,
* branch between “package” and “legacy” execution,
* emit old flags such as `--intent`, `--pairs`, or legacy raw-task invocation,
* reference `src/autoloop/...` repo structure in templates.

It must only drive the new package-based CLI:

* `autoloop run <workflow> <task-id> --root ... --message ...`
* `autoloop resume <workflow> <task-id> --root ...`

#### 3.2 Required implementation changes

##### A. `recursive_autoloop/run_recursive_autoloop.sh`

Remove all legacy-mode support:

* delete `AUTOLOOP_CLI_MODE`;
* delete `detect_autoloop_cli_mode`;
* delete the package-vs-legacy branching in:

  * `run_autoloop_start_cli`
  * `run_autoloop_resume_cli`
  * `emit_direct_resume_hint`
* remove all remaining references to:

  * `--intent`
  * `--intent-mode`
  * `--pairs`
  * legacy `--task-id` CLI mode
  * old raw compatibility behavior

After cleanup, `run_autoloop_start_cli` must always call:

```bash
autoloop run "$AUTOLOOP_WORKFLOW_NAME" "$task_id" --root "$WORKSPACE" --message "$message"
```

and `run_autoloop_resume_cli` must always call:

```bash
autoloop resume "$AUTOLOOP_WORKFLOW_NAME" "$task_id" --root "$WORKSPACE"
```

Keep the nested-git environment isolation if still needed; that is orthogonal and not a compatibility issue.

##### B. `recursive_autoloop/run_recursive_autoloop_templates/bootstrap_task.md.tmpl`

Replace outdated mandatory-reading paths such as:

* `src/autoloop/framework/...`
* `src/autoloop/main.py`
* `src/autoloop/workflows/...`

with the current repo layout, for example:

* `docs/architecture.md`
* `docs/authoring.md`
* `core/`
* `runtime/`
* `extensions/`
* `stdlib/`
* `workflows/`
* recursive memory files under `.autoloop_recursive/`

Update the wording so it describes:

* workflow packages,
* package CLI,
* workflow-as-building-block composition,
* task/workflow/run workspace layout,
* greenfield/no-backcompat stance.

##### C. `recursive_autoloop/run_recursive_autoloop_templates/cycle_task.md.tmpl`

Make the same repo-path cleanup and architecture cleanup as above.

Also update any instructions that still pressure future cycles toward the old monolithic `src/autoloop/main.py`-style runner assumptions.

##### D. Other templates

Review and update any remaining recursive templates that mention the old layout or old CLI semantics. At minimum:

* `workflow_examples.md.tmpl` — verify examples remain consistent with package workflows and reusable building blocks;
* `framework_evolution_charter.md.tmpl` — ensure it does not imply old runner ownership;
* `framework_roadmap.md.tmpl` — ensure it points at current seams.

#### 3.3 Test updates

Strengthen wrapper tests to assert **absence** of legacy behavior, not just presence of new behavior.

At minimum add tests that fail if the wrapper still contains:

* `--intent`
* `--pairs`
* `--task-id` legacy autoloop invocation
* legacy mode detection branches

Update existing wrapper tests in `tests/runtime/test_package_cli.py` accordingly. 

#### 3.4 Acceptance criteria

This gap is fixed when all of the following are true:

* the wrapper contains no legacy CLI detection logic;
* the wrapper always emits package-based `autoloop run/resume`;
* templates reference current repo structure only;
* no recursive template instructs readers to inspect `src/autoloop/...` or legacy runner files. 

---

### 4. Cross-cutting cleanup

#### 4.1 Docs

Update all active docs so they consistently say:

* greenfield, no backward compatibility requirement;
* feature compatibility only;
* public CLI has no provider-factory flag;
* session resumability uses `session_id`, not `thread_id`;
* recursive/autonomous operation assumes package CLI only.

Files to update at minimum:

* `docs/architecture.md`
* `docs/authoring.md`

#### 4.2 Strictness tests

Strengthen strictness tests so the repo actively forbids reintroduction of the removed compatibility surfaces.

Add or extend assertions for:

* no public `--provider-factory` in CLI help or docs;
* no `AUTOLOOP_PROVIDER_FACTORY` compatibility path in runtime sources;
* no `thread_id` in active runtime/framework docs and session payload code;
* no legacy CLI branches in the recursive wrapper.

#### 4.3 Naming cleanup

It is acceptable for test filenames such as `test_compatibility_runtime.py` to keep their current names if you do not want churn, but the **test contents** must reflect the greenfield contract, not compatibility preservation.

---

### 5. Implementation order

Do the work in this order so the repo stays coherent during the refactor:

1. **Introduce public provider resolution** through a built-in backend resolver.
2. **Remove public provider-factory surfaces** from `runtime/cli.py`.
3. **Remove `thread_id` compatibility** from runtime session payloads and provider metadata handling.
4. **Update provider-related docs and tests**.
5. **Remove legacy CLI mode from the recursive wrapper**.
6. **Rewrite recursive templates** to point at current layout and package CLI.
7. **Strengthen strictness tests and doc-baseline tests** so the removed compatibility surfaces cannot silently return.
8. Run the full test suite and fix any Autoloop-v1 parity fallout until the package-local parity path still passes cleanly. 

---

### 6. Definition of done

This remediation is complete only when all of the following are true:

* the public CLI exposes **no** `--provider-factory`;
* public provider selection happens through typed config and generic provider flags only;
* there is no public provider-factory env-var escape hatch;
* framework/runtime session payloads contain `session_id` and **not** `thread_id`;
* provider resumability still works correctly;
* the recursive wrapper contains no legacy CLI detection or old-style CLI calls;
* recursive templates reference the current package-based repo layout and workflow model;
* docs consistently describe the greenfield contract;
* strictness tests enforce the removal of these compatibility surfaces;
* all current passing capabilities still pass: package CLI, task/workflow/run layout, `-wf`, subworkflow invocation, Autoloop-v1 parity, tracing, and workflow-folder git scoping. 

That is the full standalone remediation plan for the remaining identified gaps.

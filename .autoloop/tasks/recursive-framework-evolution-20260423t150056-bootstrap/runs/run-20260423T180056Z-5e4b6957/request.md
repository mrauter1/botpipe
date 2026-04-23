This prompt is grounded in the current Autoloop framework shape and in the provider helper you uploaded. It also reflects the current official Claude Code headless CLI docs and the current public Codex documentation: Claude Code clearly documents `-p/--print`, `--output-format json`, `--resume`, `--model`, and permission controls; Codex public docs clearly confirm Codex Exec / Full Auto as the intended automation surface, but do not fully pin every exact `exec` sub-flag we need, so the uploaded helper should remain the command-surface baseline and tests should verify those expected flags explicitly.   ([docs.anthropic.com](https://docs.anthropic.com/en/docs/claude-code/cli-reference?utm_source=chatgpt.com)) ([openai.com](https://openai.com/index/unlocking-the-codex-harness/?utm_source=chatgpt.com))

````markdown id="lhm6vo"
Implement concrete built-in Codex and Claude providers for the current Autoloop framework.

Read this prompt as the authoritative spec. Implement exactly what it says.

# Objective

Implement real runtime-backed provider adapters for:

- Codex CLI
- Claude Code CLI

Each provider must live in its own Python file under a runtime-side providers folder.

The implementation must fit the **current Autoloop architecture**, not redesign it.

The result must satisfy the current framework provider protocol, current runtime config model, current canonical `session_id` resumability model, current package-first runtime, and current tests/docs direction.

This is a greenfield implementation task. Do not preserve old provider-factory or old `thread_id` compatibility surfaces.

---

# Key assumptions to follow

These assumptions are intentional and already approved:

1. Put the concrete adapters on the **runtime** side, not in `core/`.
2. Keep the current `LLMProvider` protocol unchanged.
3. Keep `session_id` as the canonical provider continuation handle.
4. Do not reintroduce `thread_id` into framework-owned state or payloads.
5. Use the uploaded provider helper as the **baseline command/reference behavior**, especially for Codex.
6. Do **not** probe Codex CLI help on every invocation.
7. Add dedicated verification helpers that tests can call to validate the expected Codex/Claude CLI surfaces.
8. For verifier and single-LLM turns, require strict JSON outcomes and validate them locally.
9. For Claude Code, use current documented headless CLI behavior.
10. Anthropic Structured Outputs are relevant as design guidance for robust JSON contracts, but do **not** build an Anthropic API provider here. This task is for the Claude Code CLI adapter, not the Claude API.

---

# Existing architecture constraints you must preserve

Do not change these architectural facts:

- `core/providers/*` is the strict provider protocol + models + test fake surface.
- `runtime/provider_backends.py` is the framework-owned backend dispatch point.
- `runtime/config.py` is the source of truth for public typed provider config.
- `runtime/stores/filesystem.py` already uses canonical `session_id` and must stay that way.
- The public CLI uses `--provider`, `--model`, and `--model-effort`.
- The provider-factory seam may remain only as a non-public test/programmatic injection seam.
- The framework session model must remain provider-agnostic.

Do not move provider implementation into `core/`.

Do not redesign the provider protocol.

Do not redesign session persistence.

---

# Files to create

Create this runtime package:

```text
runtime/
  providers/
    __init__.py
    codex.py
    claude.py
    _common.py
````

`_common.py` is allowed and recommended. If you decide to inline the shared helpers, keep the behavior identical.

---

# Files to modify

Modify exactly these framework files as needed:

* `runtime/provider_backends.py`
* `tests/runtime/test_provider_backends.py`
* add any additional focused provider tests if needed
* `docs/architecture.md`
* `docs/authoring.md`

Only modify other files if strictly necessary for correctness.

Do not change the core provider protocol or request/response dataclasses unless absolutely necessary. The current design should be sufficient.

---

# Current provider protocol to preserve

Use the current protocol exactly:

* `LLMProvider.run_producer(request: ProducerRequest) -> ProducerResponse`
* `LLMProvider.run_verifier(request: VerifierRequest) -> OutcomeResponse`
* `LLMProvider.run_llm(request: LLMRequest) -> OutcomeResponse`

The provider adapters must satisfy these methods without changing the interface.

Producer turns return raw provider output.

Verifier and LLM turns must return typed `Outcome` objects.

---

# High-level implementation design

## Runtime-side provider files

Implement:

* `runtime/providers/codex.py`
* `runtime/providers/claude.py`

and shared helpers in:

* `runtime/providers/_common.py`

These adapters must build concrete `LLMProvider` implementations using the current `ResolvedRuntimeConfig`.

## Backend dispatch

Update `runtime/provider_backends.py` so the built-in backend resolver dispatches to these concrete providers.

The backend resolver must remain the only public runtime-owned provider selection path.

---

# Shared helper behavior (`runtime/providers/_common.py`)

Implement the following shared helpers.

## 1. `require_prompt_text(...)`

Signature can vary slightly, but behavior must be:

* input: `ResolvedPrompt`, provider name, step name
* if prompt text is missing, raise `ProviderExecutionError`
* include provider name and step name in the error

This guarantees CLI providers are never asked to run a step without resolved prompt text.

## 2. `format_subprocess_streams(...)`

Build a readable combined raw output string for error/debug surfaces.

Rules:

* include stdout if non-empty
* include stderr if non-empty
* if both are empty, return a sentinel like `[empty stdout/stderr]`
* preserve ordering/readability
* do not use this formatted value as `Outcome.raw_output`
* use it only for raised error messages or attached debug metadata

## 3. `ensure_session_provider_match(...)`

Rules:

* if the incoming `SessionBinding` is `None`, do nothing
* if binding metadata contains a provider name and it does not match the current adapter’s provider name, raise `ProviderExecutionError`
* the error must clearly state that resuming across providers is forbidden and a new run is required

Do not silently cross-resume Codex sessions with Claude or vice versa.

## 4. `parse_outcome_json(...)`

This is the strict local validator for verifier and LLM output.

Required behavior:

* accept either:

  * a plain JSON object, or
  * a single fenced top-level ```json block containing a JSON object
* reject all other forms
* require `tag: str`
* accept optional:

  * `reason: str`
  * `clarification: str`
  * `question: str`
  * `payload: dict`
* default missing `payload` to `{}`

When building the `Outcome`, set:

* `Outcome.raw_output` to the original provider-returned text that was parsed
* `Outcome.tag` from parsed JSON
* optional fields from parsed JSON

Raise `ProviderExecutionError` on malformed or invalid outcome JSON.

This helper exists because the CLI providers do not give us a schema-validated `Outcome` object directly.

## 5. `render_verifier_input(...)`

Do not invent a new packet abstraction.

The verifier prompt text remains the main provider-facing contract.

Append the producer raw output in one explicit delimited appendix, e.g.:

```text
<verifier_prompt>
...resolved verifier prompt text...
</verifier_prompt>

<producer_raw_output>
...verbatim producer raw output...
</producer_raw_output>
```

The exact formatting can vary slightly, but it must be:

* explicit
* deterministic
* readable
* provider-facing
* minimal

## 6. `build_session_binding(...)`

Create a canonical session binding from:

* incoming session binding or slot metadata
* resolved `session_id`
* provider name
* provider metadata
* selected model
* selected effort/model_effort

Required metadata shape:

```python
{
    "provider": "codex" or "claude",
    "mode": "persistent",
    "provider_metadata": {...},
    "model_override": ... or None,
    "effort_override": ... or None,
}
```

Rules:

* `session_id` is the only canonical continuation handle
* do not create or persist `thread_id`
* provider-specific extra state stays under `provider_metadata`

---

# Implement `runtime/providers/codex.py`

Use the uploaded helper as the **reference design** for:

* Codex Exec help probing
* command construction
* start vs resume command modes
* JSONL parsing
* extraction of the Codex continuation handle
* fallback between bypass/full-auto modes

## Required symbols

Implement at least:

* `CodexCLICommand` dataclass
* `verify_codex_exec_capabilities()`
* `resolve_codex_cli_commands(config: ResolvedRuntimeConfig) -> CodexCLICommand`
* `parse_codex_exec_json(raw_stdout: str) -> tuple[str, str | None, dict[str, Any]]`
* `CodexProvider`
* `build_codex_provider(config: ResolvedRuntimeConfig) -> LLMProvider`

## Codex CLI capability rules

### Verification helper

Implement a dedicated test-callable helper:

```python
def verify_codex_exec_capabilities() -> None:
    ...
```

Behavior:

* run `codex exec --help`
* run `codex exec resume --help`
* verify the exact flags the adapter requires
* raise `ConfigError` with precise messages if the expected surface is missing

This function exists for tests and environment verification.

Do **not** call it on every provider turn.

### Command resolution

Implement a cached command resolver:

```python
def resolve_codex_cli_commands(config: ResolvedRuntimeConfig) -> CodexCLICommand:
    ...
```

Rules:

* read `config.provider.codex.model`
* read `config.provider.codex.model_effort`
* verify `codex` exists on `PATH`
* require:

  * `codex exec --json`
  * `codex exec resume --json`
* if `model_effort` is configured, require:

  * `--model-effort` support on both start and resume
* prefer `--dangerously-bypass-approvals-and-sandbox` if supported
* otherwise use `--full-auto` if supported
* if neither is supported, raise `ConfigError`

Use per-process caching so help probing happens once per process, not per invocation.

## Codex JSON parsing

Implement:

```python
def parse_codex_exec_json(raw_stdout: str) -> tuple[str, str | None, dict[str, Any]]:
    ...
```

Rules:

* treat stdout as JSONL
* ignore malformed lines silently unless the whole output is unusable
* capture assistant/user-facing text from `item.completed` events where:

  * `item` is a dict
  * `item.type == "agent_message"`
  * `item.text` is a string
* capture the continuation id from `thread.started.thread_id`
* return:

  * joined assistant text
  * canonical session id
  * provider metadata dict

Important:

* you may use a local variable called `thread_id` while parsing Codex output
* you must translate it immediately into canonical `session_id`
* do not expose or persist `thread_id` outside this file

## `CodexProvider` behavior

Implement `CodexProvider` as an `LLMProvider`.

Constructor should receive:

* `config: ResolvedRuntimeConfig`
* resolved `CodexCLICommand`

Internally keep:

* selected model
* selected model_effort
* resolved start/resume commands

### Shared turn runner

All three methods should delegate to a shared `_run_turn(...)`.

Shared rules:

* call `require_prompt_text(...)`
* if an incoming session exists, call `ensure_session_provider_match("codex", ...)`
* use resume command when incoming `session_id` exists
* use start command otherwise
* send prompt via stdin
* capture stdout/stderr
* non-zero exit -> raise `ProviderExecutionError`
* parse stdout through `parse_codex_exec_json(...)`
* if parser returns no new session id during resume, preserve the incoming `session_id`
* build canonical `SessionBinding` with provider metadata

### `run_producer(...)`

Return:

* `ProducerResponse(raw_output=<assistant text>, session=<binding>, metadata=...)`

Rules:

* `raw_output` is the parsed assistant text, not combined stdout/stderr
* keep useful parser/subprocess details in `metadata` if helpful

### `run_verifier(...)`

Behavior:

* build verifier input via `render_verifier_input(...)`
* run Codex
* parse assistant text into `Outcome` via `parse_outcome_json(...)`
* return `OutcomeResponse(outcome=..., session=..., metadata=...)`

### `run_llm(...)`

Behavior:

* use prompt text directly
* run Codex
* parse assistant text into `Outcome`
* return `OutcomeResponse(...)`

---

# Implement `runtime/providers/claude.py`

Use the uploaded helper and current Claude Code CLI docs as the reference design for:

* `claude -p`
* `--output-format json`
* `--resume`
* `--model`
* documented permission controls
* JSON parsing of outer CLI output

## Required symbols

Implement at least:

* `verify_claude_code_capabilities()`
* `claude_permission_args(config: ClaudeProviderConfig) -> list[str]`
* `parse_claude_exec_json(raw_stdout: str) -> tuple[str, str | None, dict[str, Any]]`
* `ClaudeProvider`
* `build_claude_provider(config: ResolvedRuntimeConfig) -> LLMProvider`

## Claude capability verification

Add a dedicated test-callable helper:

```python
def verify_claude_code_capabilities() -> None:
    ...
```

Behavior:

* inspect Claude Code help surface
* verify the flags this adapter uses
* raise `ConfigError` with precise messages if the expected CLI surface is missing

Check at minimum for:

* `-p` or `--print`
* `--output-format`
* `--resume`
* `--model`
* documented permission controls used by the adapter

Also handle `effort` carefully:

* if the installed Claude Code CLI clearly supports `--effort`, allow it
* if `config.provider.claude.effort` is set but the CLI does not support it, raise `ConfigError`
* do not assume `--effort` unconditionally

Do not run this helper on every turn.

## Permission strategy mapping

Implement `claude_permission_args(...)`.

Use this mapping:

* `inherit` -> `[]`
* `allow_core_tools` -> args that allow basic local tools, e.g.:

  * `--allowedTools Read,Write,Edit,Glob,Grep,Bash`
  * plus a documented permission mode if needed for compatibility
* `bypass` -> `--dangerously-skip-permissions`

If the current CLI surface requires slightly different flag names than expected, adapt to the verified surface, but keep the semantic mapping identical.

Unknown strategy -> `ConfigError`

## Claude JSON parsing

Implement:

```python
def parse_claude_exec_json(raw_stdout: str) -> tuple[str, str | None, dict[str, Any]]:
    ...
```

Rules:

* stdout must be valid JSON object
* require `result: str`
* optional `session_id: str`
* any remaining top-level keys go into `provider_metadata`
* invalid JSON -> `ProviderExecutionError`
* missing `result` -> `ProviderExecutionError`

## `ClaudeProvider` behavior

Implement `ClaudeProvider` as an `LLMProvider`.

Constructor should receive `ResolvedRuntimeConfig`.

Keep:

* selected model
* selected effort if supported
* permission strategy

### Shared turn runner

All three methods should delegate to `_run_turn(...)`.

Shared rules:

* call `require_prompt_text(...)`
* if incoming session exists, call `ensure_session_provider_match("claude", ...)`
* invoke Claude Code in headless mode using:

  * `claude`
  * `-p` or `--print`
  * prompt text
  * `--output-format json`
* add `--resume <session_id>` if resuming
* add `--model` when configured
* add `--effort` only if configured and supported
* add permission args from `claude_permission_args(...)`
* capture stdout/stderr
* non-zero exit -> `ProviderExecutionError`
* parse stdout with `parse_claude_exec_json(...)`
* if parsed session id is missing during resume, preserve incoming `session_id`
* build canonical `SessionBinding`

### `run_producer(...)`

Return `ProducerResponse` with:

* `raw_output = parsed result string`
* canonical session binding
* provider metadata

### `run_verifier(...)`

* build verifier prompt via `render_verifier_input(...)`
* run Claude Code
* parse the returned `result` text with `parse_outcome_json(...)`
* return `OutcomeResponse(...)`

### `run_llm(...)`

* use prompt text directly
* run Claude Code
* parse returned `result` text with `parse_outcome_json(...)`
* return `OutcomeResponse(...)`

---

# Do not implement API/SDK structured outputs here

Do not build an Anthropic API provider.

Do not change the CLI provider into an API provider.

Use strict local JSON validation for verifier/LLM turns.

Structured Outputs is only design guidance here: the provider-facing contract should be robustly JSON-shaped, and the framework should validate it locally.

---

# Update `runtime/provider_backends.py`

Replace the current placeholder backend builders with the new real builders.

Expected final pattern:

```python
from .providers.codex import build_codex_provider
from .providers.claude import build_claude_provider

_BACKEND_BUILDERS = {
    "codex": build_codex_provider,
    "claude": build_claude_provider,
}
```

Keep:

* rejection of `module:function` provider names
* clear `ConfigError` messages for unavailable binaries or unsupported CLI capability combinations

Do not reintroduce provider-factory loading.

---

# Do not change the session persistence schema

Do not modify the canonical session payload schema in the runtime store.

Rules:

* `session_id` stays canonical
* provider-specific extra state stays under `provider_metadata`
* no `thread_id`
* no provider-specific field naming leaks into the framework schema

The providers must adapt themselves to the existing session store, not the other way around.

---

# Tests to add or update

Update `tests/runtime/test_provider_backends.py` and add new focused tests if needed.

## A. Backend resolution tests

Add tests that:

* `resolve_provider_backend(config=codex)` returns a real `CodexProvider` when capability verification is monkeypatched as successful
* `resolve_provider_backend(config=claude)` returns a real `ClaudeProvider`
* module:function provider names are still rejected
* missing codex binary -> precise `ConfigError`
* missing claude binary -> precise `ConfigError`
* unsupported Codex CLI flags -> precise `ConfigError`
* configured Codex `model_effort` without support -> precise `ConfigError`
* configured Claude `effort` without support -> precise `ConfigError`

## B. Codex adapter tests

Monkeypatch subprocess and simulate:

* successful help probing
* start command
* resume command
* successful producer turn with JSONL stdout containing:

  * `thread.started`
  * `item.completed` / `agent_message`
* successful verifier turn where the assistant text is valid JSON outcome
* successful llm turn with valid JSON outcome
* malformed JSONL
* missing assistant text
* non-zero subprocess exit
* provider mismatch on resume

Assert:

* producer returns `ProducerResponse`
* verifier/llm return `OutcomeResponse`
* `session_id` is canonical
* metadata contains provider metadata but no `thread_id`

## C. Claude adapter tests

Monkeypatch subprocess and simulate:

* valid headless JSON stdout
* valid verifier result containing JSON outcome text
* valid llm result containing JSON outcome text
* malformed JSON
* missing `result`
* non-zero exit
* provider mismatch on resume

Assert:

* `ProducerResponse.raw_output` is the parsed result string
* verifier/llm parse strict JSON correctly
* `session_id` is canonical
* provider metadata preserved
* no `thread_id`

## D. Shared parser tests

Add focused tests for:

* plain JSON object outcome
* fenced ```json block outcome
* invalid JSON
* missing tag
* non-object payload
* default payload behavior
* `Outcome.raw_output` preserves original provider-returned text

## E. Capability verification tests

Add tests for:

* `verify_codex_exec_capabilities()` success and failure cases
* `verify_claude_code_capabilities()` success and failure cases

These are the only places where repeated help-surface probing is needed.

---

# Docs to update

Update:

* `docs/architecture.md`
* `docs/authoring.md`

Add or update sections describing:

* built-in runtime providers now exist under `runtime/providers/`
* provider selection remains public and typed through:

  * config
  * `--provider`
  * `--model`
  * `--model-effort`
* provider adapters satisfy the existing `LLMProvider` protocol
* provider resumability uses canonical `session_id`
* verifier and LLM turns must return strict JSON outcomes
* no `thread_id`
* no provider-factory public surface

Do not document provider factories or module:function loaders.

---

# Implementation constraints

Do not:

* redesign the provider protocol
* redesign session stores
* move providers into `core/`
* reintroduce `thread_id`
* add a new packet abstraction for verifier prompts
* add Anthropic API/SDK support in this task
* add per-invocation CLI help probing

Do:

* keep the implementation narrow
* reuse the uploaded helper’s reliable subprocess patterns
* fit them into the current framework boundaries
* keep provider-specific details localized to the runtime provider files

---

# Acceptance criteria

This implementation is complete only when all of the following are true:

1. `runtime/providers/codex.py` exists and implements a concrete `CodexProvider`
2. `runtime/providers/claude.py` exists and implements a concrete `ClaudeProvider`
3. `runtime/provider_backends.py` dispatches to those builders instead of placeholder errors
4. both adapters satisfy the current `LLMProvider` protocol without core protocol changes
5. producer turns return `ProducerResponse`
6. verifier and llm turns return `OutcomeResponse` with typed `Outcome`
7. Codex command resolution and JSONL parsing follow the uploaded helper behavior, adapted to canonical `session_id`
8. Claude headless JSON handling follows the current documented CLI behavior
9. provider resumability works through `session_id`
10. no framework-owned code reads or writes `thread_id`
11. capability verification helpers exist and are used by tests, not every invocation
12. docs describe the new built-in runtime providers correctly
13. tests cover success, parse failure, unsupported CLI surface, missing binaries, and provider mismatch on resume

Implement the feature fully and correctly, not partially.

```
```

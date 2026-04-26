Standalone implementation plan — Autoloop v3 runtime tracking and tracing prerequisites
Scope

Implement only the runtime tracking and tracing prerequisites needed for future workflow optimization.

This plan does not implement workflow optimization, prompt rewriting, LLM judges, adversarial case generation, ablation, step ranking, or workflow-level optimization. It only makes Autoloop v3 runs reproducible and evidence-rich.

The current codebase already has the relevant seams: workflow-declared tracing, workflow-declared git tracking, low-level git helpers, extension lifecycle events, raw producer/verifier outputs on StepFinish, provider request/response models, and compiled step metadata. The implementation must shift default observability ownership from workflow declarations to the runtime while keeping existing workflow extension behavior compatible.

1. Target outcome

After this change, a normal Autoloop v3 run in a clean git repository should, by default, produce:

.autoloop/tasks/<task_id>/wf_<workflow_name>/runs/<run_id>/
  run.json
  events.jsonl
  trace.jsonl
  git_tracking.jsonl
  static_step_graph.json
  raw/
    000001_<step>_producer.txt
    000001_<step>_verifier.txt
    000002_<step>_llm.txt

Every run should record:

git commit before run
git commits after run initialization, each step, and terminal/fatal completion
step start/finish/terminal trace events
raw producer/verifier/LLM output references
provider usage when available
static compiled workflow step graph
route/outcome data
run/resume sequence metadata

Git is the replay boundary. Do not classify changed files as runtime, workflow, prompt, config, lockfile, or artifact changes.

2. Non-goals

Do not implement:

producer prompt optimization
verifier/rubric optimization
token optimization
adversarial case generation
candidate ablation
step prioritization
workflow-level optimization
automatic source mutation
automatic prompt mutation
LLM-as-judge scoring

Do not introduce a second execution model, a generic plugin platform, or hidden optimization behavior in the engine.

3. Design decisions
3.1 Runtime owns git tracking

Git tracking must be runtime-owned and runtime-configured.

Workflows must not need to declare extensions.git.GitTracking to get git tracking. The default runtime path must provide git tracking automatically.

Existing workflow-declared git tracking modules should remain importable for compatibility, but runtime git tracking is authoritative.

3.2 Git commit-all is the default

When runtime git tracking is enabled, Autoloop must commit the full workspace state at configured runtime milestones:

git add --all
git commit -m "<message>"

Do not path-filter. Do not inspect which category of file changed.

3.3 Clean git workspace required before run

Because commit-all is default, the runtime must reject dirty repositories at run start.

A git-tracked run starts only if:

git status --porcelain=v1 --untracked-files=all

is empty.

Behavior:

failure_mode=raise:
  fail before creating or modifying run workspace files.

failure_mode=ignore:
  disable git tracking for this run, mark git_tracking.eligible=false, and continue.

Default is raise.

3.4 Runtime tracing is default

Runtime tracing must be enabled by runtime config and written by runtime code.

Workflows must not need to declare extensions.Tracing to get trace.jsonl.

Existing workflow-declared tracing should remain importable for compatibility.

3.5 Avoid self-referential commit metadata

Do not write commit_after_step into the same trace event that is included in commit_after_step.

Use this split:

trace.jsonl:
  execution evidence and commit_before_step

git_tracking.jsonl:
  git commit metadata, including commit_after_step and commit_after_run

run.json:
  aggregate/latest run metadata

commit_after_step may be appended to git_tracking.jsonl after the commit it names. It is guaranteed to be present in the final terminal/fatal commit, not necessarily inside the specific step commit it names.

3.6 Resume must append, not overwrite

On resume, runtime observability must append to existing run evidence:

trace.jsonl is appended
git_tracking.jsonl is appended
raw/ files use the next sequence number
existing raw files are never overwritten
run.json is updated with latest aggregate metadata
4. Required run-start ordering

This ordering is mandatory:

1. Resolve CLI/config.
2. Resolve workflow reference and load enough metadata to know workflow_name.
3. If runtime git tracking is enabled:
     discover git repo
     assert repo is clean before creating/modifying run files
     record commit_before_run
4. Create or open task/run workspace.
5. Write initial run.json metadata.
6. Write static_step_graph.json.
7. Initialize trace.jsonl and git_tracking.jsonl if missing.
8. Commit initial run workspace when git commit_policy is "run" or "step".
9. Start engine execution.

The cleanliness check must happen before Autoloop creates run.json, trace.jsonl, git_tracking.jsonl, static_step_graph.json, raw output directories, or any other run artifacts.

For resume, use the same clean-start rule before appending to the existing run. If git tracking is enabled and the repo is dirty before resume-created files are written, fail or disable git tracking according to failure_mode.

5. Runtime config changes

Modify runtime/config.py using the existing config module’s style. Do not rewrite the config system.

Add runtime config fields equivalent to:

GitCommitPolicy = Literal["off", "run", "step"]
FailureMode = Literal["raise", "ignore"]

class GitTrackingRuntimeConfig:
    enabled: bool = True
    commit_policy: GitCommitPolicy = "step"
    failure_mode: FailureMode = "raise"

class TracingRuntimeConfig:
    enabled: bool = True
    path: str = "trace.jsonl"
    failure_mode: FailureMode = "raise"
    include_state_snapshots: bool = True

Default resolved runtime config must behave as:

runtime:
  git_tracking:
    enabled: true
    commit_policy: step
    failure_mode: raise
  tracing:
    enabled: true
    path: trace.jsonl
    failure_mode: raise
    include_state_snapshots: true

Commit policy semantics:

off:
  disable runtime git tracking.

run:
  commit after initial run workspace setup and after terminal/fatal completion.

step:
  commit after initial run workspace setup, after each step, and after terminal/fatal completion.

step is intentionally verbose and optimized for replay/evaluation, not clean human git history.

6. CLI changes

Modify runtime/cli.py.

Add these flags to the run path:

--no-git
--git-commit-policy {off,run,step}
--no-trace

Behavior:

--no-git:
  runtime.git_tracking.enabled = false

--git-commit-policy off:
  runtime.git_tracking.enabled = false
  runtime.git_tracking.commit_policy = "off"

--git-commit-policy run:
  runtime.git_tracking.enabled = true
  runtime.git_tracking.commit_policy = "run"

--git-commit-policy step:
  runtime.git_tracking.enabled = true
  runtime.git_tracking.commit_policy = "step"

--no-trace:
  runtime.tracing.enabled = false

Do not add additional observability flags in this phase.

7. Git helper changes

Modify extensions/git/repo.py.

Keep the existing GitRepo abstraction, but add commit-all helpers:

def status_porcelain(self) -> str:
    return self._git("status", "--porcelain=v1", "--untracked-files=all")

def is_dirty(self) -> bool:
    return bool(self.status_porcelain().strip())

def add_all(self) -> None:
    self._git("add", "--all")

def commit_all(self, message: str) -> tuple[str, bool]:
    self.add_all()
    if not self.staged_paths():
        return self.head(), False
    self._git("commit", "-m", message)
    return self.head(), True

Rules:

commit_all returns (current_head, False) if nothing changed.
commit_all returns (new_head, True) if a commit was created.
commit_all never creates empty commits.
commit_all stages the full workspace.

Do not use pathspec filtering in runtime git tracking.

Existing pathspec and workflow-owned git-policy helpers can remain for compatibility, but runtime git tracking should not depend on workflow-owned GitPolicy.

8. Runtime git tracking module

Create:

runtime/git_tracking.py
8.1 Public API

Implement:

class RuntimeGitTracker:
    def __init__(
        self,
        *,
        root: Path,
        run_dir: Path | None,
        workflow_name: str,
        task_id: str,
        run_id: str,
        config: GitTrackingRuntimeConfig,
    ) -> None:
        ...

    def prepare_before_workspace_creation(self) -> dict[str, object]:
        ...

    def bind_run_dir(self, run_dir: Path) -> None:
        ...

    def commit_run_initialized(self) -> dict[str, object]:
        ...

    def before_step(self, *, sequence: int, step_name: str) -> dict[str, object]:
        ...

    def after_step(self, *, sequence: int, step_name: str, commit_before_step: str | None) -> dict[str, object]:
        ...

    def after_run(self, *, terminal: str | None) -> dict[str, object]:
        ...

    def on_fatal(self, *, step_name: str | None, error: BaseException) -> dict[str, object]:
        ...

prepare_before_workspace_creation() performs git discovery, clean-start check, and commit_before_run capture before the run directory is created or changed.

bind_run_dir() attaches the tracker to the final run directory after workspace creation.

8.2 Disabled behavior

If config is disabled or policy is off:

enabled=false
eligible=false
do not require a git repo
do not create commits
all public methods return metadata with enabled=false
8.3 Enabled behavior

If enabled:

discover repo from root
require repo exists unless failure_mode=ignore
require clean repo before workspace creation unless failure_mode=ignore
record commit_before_run

If no repo is found and failure_mode=raise, fail before run workspace creation.

If no repo is found and failure_mode=ignore, continue with git tracking disabled for the run and metadata:

{
  "enabled": false,
  "eligible": false,
  "error": "git tracking disabled because no git repository was found"
}

If dirty and failure_mode=raise, fail before run workspace creation.

If dirty and failure_mode=ignore, continue with git tracking disabled for the run and metadata:

{
  "enabled": false,
  "eligible": false,
  "error": "git tracking disabled because repository was dirty at run start"
}
8.4 Commit messages

Use deterministic messages:

autoloop: init <workflow_name> <run_id>
autoloop: step <workflow_name> <run_id> <sequence> <step_name>
autoloop: finish <workflow_name> <run_id> <terminal>
autoloop: fatal <workflow_name> <run_id>

Sanitize only if necessary for shell safety; messages are passed as subprocess arguments, not shell strings.

8.5 Commit behavior

commit_run_initialized():

if policy in {"run", "step"}:
  git add --all
  git commit -m "autoloop: init ..."
  append run_initialized metadata

before_step():

record commit_before_step = repo.head()
return it

after_step():

if policy == "step":
  git add --all
  git commit -m "autoloop: step ..."
  append step_committed record to git_tracking.jsonl
else:
  append step_observed record without committing

after_run():

if policy in {"run", "step"}:
  git add --all
  git commit -m "autoloop: finish ..."
  append run_finished record to git_tracking.jsonl

on_fatal():

write fatal metadata where possible
if policy in {"run", "step"}:
  git add --all
  git commit -m "autoloop: fatal ..."
  append fatal_committed record to git_tracking.jsonl
8.6 git_tracking.jsonl

Create or append to:

<run_dir>/git_tracking.jsonl

Example record:

{
  "schema": "autoloop.git_tracking/v1",
  "event_type": "step_committed",
  "workflow": "release_candidate_to_go_no_go",
  "task_id": "task-123",
  "run_id": "run-456",
  "sequence": 3,
  "step_name": "assessment",
  "commit_before_step": "abc123",
  "commit_after_step": "def456",
  "created_commit": true,
  "timestamp": "2026-04-26T00:00:00+00:00"
}

If no files changed:

{
  "created_commit": false,
  "commit_before_step": "abc123",
  "commit_after_step": "abc123"
}

Remember: the record containing commit_after_step is not guaranteed to be inside commit_after_step; it is guaranteed to be captured by a later commit, usually the terminal/fatal commit.

9. Runtime tracing module

Create:

runtime/tracing.py
9.1 Public API

Implement:

class RuntimeTraceWriter:
    def __init__(
        self,
        *,
        run_dir: Path,
        workflow_name: str,
        task_id: str,
        run_id: str,
        config: TracingRuntimeConfig,
        static_step_graph: Mapping[str, Any],
    ) -> None:
        ...

    def step_started(
        self,
        *,
        sequence: int,
        event: StepStart,
        commit_before_step: str | None,
    ) -> None:
        ...

    def step_finished(
        self,
        *,
        sequence: int,
        event: StepFinish,
        commit_before_step: str | None,
    ) -> None:
        ...

    def terminal(
        self,
        *,
        event: TerminalFinish,
    ) -> None:
        ...

    def fatal(
        self,
        *,
        event: TerminalFinish,
        error: BaseException,
    ) -> None:
        ...

If tracing is disabled, all methods are no-ops.

If writing fails:

failure_mode=raise:
  raise and fail the run

failure_mode=ignore:
  record best-effort warning in run metadata if possible and continue
9.2 Trace schema

Each record in trace.jsonl must include:

{
  "schema": "autoloop.runtime_trace/v1",
  "event_type": "step_finished",
  "timestamp": "2026-04-26T00:00:00+00:00",
  "workflow": "release_candidate_to_go_no_go",
  "task_id": "task-123",
  "run_id": "run-456",
  "sequence": 3,
  "step_name": "assessment",
  "step_kind": "pair",
  "git": {
    "commit_before_step": "abc123"
  }
}

Do not include commit_after_step in trace.jsonl.

9.3 step_started

Include:

schema
event_type = step_started
timestamp
workflow
task_id
run_id
sequence
step_name
step_kind
git.commit_before_step
state snapshot if include_state_snapshots=true

State snapshots should use model_dump(mode="json").

9.4 step_finished

Include:

schema
event_type = step_finished
timestamp
workflow
task_id
run_id
sequence
step_name
step_kind
git.commit_before_step
state_before/state_after if include_state_snapshots=true
event
outcome
raw_output_refs
provider_usage

Outcome should include only ordinary Outcome fields: tag, payload, reason, question where present. Do not store hidden/private reasoning.

9.5 terminal

Include:

schema
event_type = terminal
timestamp
workflow
task_id
run_id
terminal
step_name
event
outcome
state if include_state_snapshots=true
9.6 fatal

Include:

schema
event_type = fatal
timestamp
workflow
task_id
run_id
step_name if known
error_type
error_message
state if available and include_state_snapshots=true
10. Raw-output persistence

Runtime tracing must persist provider raw outputs independently of workflow-declared log artifacts.

10.1 File location

Create:

<run_dir>/raw/
10.2 File naming

Use:

raw/<sequence>_<safe_step_name>_<role>.txt

Examples:

raw/000001_assessment_producer.txt
raw/000001_assessment_verifier.txt
raw/000002_survey_llm.txt

Step name sanitization:

safe_step = re.sub(r"[^A-Za-z0-9_.-]+", "_", step_name).strip("_") or "step"
10.3 Role mapping

For PairStep:

event.producer_raw_output -> producer file
event.verifier_raw_output -> verifier file

For LLMStep:

event.producer_raw_output -> llm file

For SystemStep:

no raw output files
10.4 Trace references

Trace records should include references, not inline raw text:

{
  "raw_output_refs": {
    "producer": {
      "path": "raw/000001_assessment_producer.txt",
      "sha256": "...",
      "bytes": 1234
    },
    "verifier": {
      "path": "raw/000001_assessment_verifier.txt",
      "sha256": "...",
      "bytes": 812
    }
  }
}

Use SHA-256 for raw-output files only.

Do not implement general artifact digests in this phase.

10.5 Resume collision prevention

On run start/resume, determine the next sequence number by reading existing evidence:

max sequence across trace.jsonl and git_tracking.jsonl
next_sequence = max + 1

If files are missing or partially malformed, fall back to scanning raw/ filenames and choose the next unused sequence. Never overwrite an existing raw file.

11. Provider token usage

Modify:

core/providers/models.py

Add:

@dataclass(frozen=True, slots=True)
class TokenUsage:
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    cached_input_tokens: int | None = None
    reasoning_tokens: int | None = None
    source: str = "unavailable"
    provider_raw: dict[str, Any] = field(default_factory=dict)

Add:

@dataclass(frozen=True, slots=True)
class StepProviderUsage:
    producer: TokenUsage | None = None
    verifier: TokenUsage | None = None
    llm: TokenUsage | None = None

Extend:

@dataclass(frozen=True, slots=True)
class ProducerResponse:
    raw_output: str
    session: SessionBinding | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    usage: TokenUsage | None = None

Extend:

@dataclass(frozen=True, slots=True)
class OutcomeResponse:
    outcome: Outcome
    session: SessionBinding | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    usage: TokenUsage | None = None

Provider rules:

If provider usage exists, map it to TokenUsage.
If unavailable, usage=None.
Missing usage must never fail a run.
Fake provider must support optional usage for tests.

Update:

core/providers/fake.py
runtime/providers/codex.py
runtime/providers/claude.py
runtime/providers/_common.py
runtime/provider_backends.py
tests/runtime/test_provider_backends.py
tests/runtime/test_runtime_providers.py
12. Engine integration with provider usage

Modify:

core/extensions.py
core/engine.py

Extend StepFinish with:

provider_usage: StepProviderUsage | None = None

Do not add git fields to core events.

Do not add large static step contracts to core events.

In engine execution:

PairStep:
  StepProviderUsage(
    producer=producer_response.usage,
    verifier=verifier_response.usage,
    llm=None,
  )

LLMStep:
  StepProviderUsage(
    producer=None,
    verifier=None,
    llm=llm_response.usage,
  )

SystemStep:
  provider_usage=None

Preserve existing raw-output fields on StepFinish.

13. Static step graph

Write a static graph for every run.

Add a helper in one of:

core/workflow_capabilities.py
runtime/static_graph.py

Prefer core/workflow_capabilities.py if that module already owns workflow surface serialization.

Function:

def workflow_static_step_graph_payload(compiled: CompiledWorkflow) -> dict[str, Any]:
    ...

Persist to:

<run_dir>/static_step_graph.json

Payload:

{
  "schema": "autoloop.workflow_static_step_graph/v1",
  "workflow_name": "release_candidate_to_go_no_go",
  "steps": [
    {
      "name": "assessment",
      "kind": "pair",
      "producer_prompt": "prompts/assessment_producer.md",
      "verifier_prompt": "prompts/assessment_verifier.md",
      "requires": [],
      "produces": [],
      "log_artifacts": [],
      "available_routes": [],
      "route_contracts": {},
      "has_expected_output_schema": true
    }
  ],
  "transitions": {
    "steps": {},
    "global": {}
  }
}

Include every compiled step. For system steps, prompt fields should be null or omitted consistently.

14. Runtime observability binding

Modify:

runtime/runner.py
core/engine.py

Add runtime-owned observability without requiring workflow extensions.

14.1 Runtime extension factories

Add an engine constructor or run/resume parameter:

runtime_extension_factories: Sequence[Callable[[RunBinding], BoundExtension]] = ()

The engine should bind runtime extensions after it creates RunBinding.

Binding order:

runtime extensions first
workflow-declared extensions second

Preserve existing workflow extension behavior and tests.

14.2 Filter workflow-declared GitTracking

Runtime git tracking is authoritative.

If a workflow declares extensions.git.GitTracking, do not bind it.

Instead:

emit a deprecation warning event
record the warning in run.json metadata
continue using runtime git tracking

This prevents duplicate commits while preserving import compatibility.

Required warning payload:

{
  "event_type": "deprecated_workflow_git_tracking_ignored",
  "message": "Workflow-declared GitTracking is ignored; runtime git tracking is authoritative."
}

Do not reject such workflows in this phase.

14.3 Keep workflow-declared Tracing

Do not filter workflow-declared Tracing in this phase. Runtime tracing writes trace.jsonl; workflow-declared tracing may write its configured sidecar. Bundled workflows should not rely on workflow-declared tracing for normal observability.

14.4 Runtime observability class

Create:

runtime/observability.py

Implement:

class BoundRuntimeObservability:
    def before_step(self, event: StepStart) -> None:
        ...

    def after_step(self, event: StepFinish) -> None:
        ...

    def on_terminal(self, event: TerminalFinish) -> None:
        ...

Behavior:

before_step:
  increment or assign sequence
  commit_before_step = git_tracker.before_step(...)
  trace_writer.step_started(...)

after_step:
  trace_writer.step_finished(...)
  git_tracker.after_step(...)

on_terminal:
  trace_writer.terminal(...)
  git_tracker.after_run(...)

Fatal path:

attempt trace_writer.fatal(...)
attempt git_tracker.on_fatal(...)
then re-raise original exception unless failure handling already converts it

Runtime observability failures respect their configured failure modes.

15. Run metadata updates

Modify the run metadata utilities in:

runtime/workspace.py

or wherever run.json is created/updated.

Add centralized helpers:

def update_run_git_tracking(run_dir: Path, payload: Mapping[str, Any]) -> None:
    ...

def append_run_git_step(run_dir: Path, payload: Mapping[str, Any]) -> None:
    ...

def update_run_tracing(run_dir: Path, payload: Mapping[str, Any]) -> None:
    ...

def append_run_warning(run_dir: Path, payload: Mapping[str, Any]) -> None:
    ...

Avoid ad hoc writes to run.json.

At initialization, run.json must include:

{
  "git_tracking": {
    "enabled": true,
    "eligible": true,
    "commit_policy": "step",
    "repo_root": "/repo",
    "commit_before_run": "abc123",
    "git_tracking_file": "git_tracking.jsonl"
  },
  "tracing": {
    "enabled": true,
    "trace_file": "trace.jsonl",
    "raw_dir": "raw",
    "static_step_graph_file": "static_step_graph.json",
    "schema": "autoloop.runtime_trace/v1"
  }
}

At terminal/fatal completion, update:

{
  "git_tracking": {
    "commit_after_run": "def456"
  }
}
16. Resume behavior

On resume:

1. Resolve config and workflow.
2. If git tracking is enabled, assert repo clean before appending resume evidence.
3. Open existing run directory.
4. Load existing run.json if present.
5. Determine next sequence number from trace/git/raw files.
6. Append new trace and git_tracking records.
7. Never overwrite existing raw files.
8. Commit resume-created evidence according to the active commit policy.

If the previous run used git tracking but current config disables it, record a warning in run metadata and continue without git tracking.

If the previous run did not use git tracking but current config enables it, start recording git metadata from the resume point; do not attempt to backfill previous commits.

17. Backward compatibility rules
17.1 Keep extension imports

Do not delete:

extensions/git/declaration.py
extensions/git/runtime.py
extensions/git/policy.py
extensions/git/__init__.py
extensions/tracing.py

Existing imports must continue to work.

17.2 Runtime git tracking supersedes workflow GitTracking

Workflow-declared GitTracking must be ignored with a warning, not bound.

17.3 Workflow-declared tracing remains sidecar-compatible

Workflow-declared Tracing remains allowed. Runtime tracing is still written by default.

17.4 Preserve workflow extension semantics

Existing workflow extension binding, ordering relative to other workflow extensions, isolation, failure, and terminal behavior must remain valid. Runtime observability must not mutate execution state.

18. Tests

Add or update tests.

18.1 Runtime config tests

Add tests for:

default config enables git tracking
default config uses commit_policy=step
default config enables tracing
invalid git commit policy is rejected
--no-git disables git tracking
--git-commit-policy off disables git tracking
--git-commit-policy run sets run policy
--git-commit-policy step sets step policy
--no-trace disables tracing
18.2 Git tracking tests

Create:

tests/runtime/test_runtime_git_tracking.py

Required tests:

test_git_tracking_disabled_does_not_require_repo
test_git_tracking_enabled_requires_repo_by_default
test_git_tracking_enabled_requires_clean_repo_before_run_workspace_creation
test_git_tracking_dirty_repo_failure_mode_ignore_disables_tracking_for_run
test_git_tracking_run_policy_commits_at_run_boundaries
test_git_tracking_step_policy_commits_after_each_step
test_git_tracking_commit_all_tracks_untracked_files
test_git_tracking_noop_commit_returns_current_head
test_git_tracking_jsonl_records_step_commit_metadata
test_runtime_git_tracking_does_not_require_workflow_declared_GitTracking
test_workflow_declared_GitTracking_is_ignored_with_warning
test_git_tracking_resume_appends_without_overwriting

Use temporary git repos with configured user:

git init
git config user.email test@example.com
git config user.name Test
git add .
git commit -m init
18.3 Runtime tracing tests

Create:

tests/runtime/test_runtime_tracing.py

Required tests:

test_runtime_trace_enabled_by_default_writes_trace_jsonl
test_runtime_trace_records_step_started_and_finished
test_runtime_trace_does_not_require_workflow_declared_Tracing
test_runtime_trace_writes_pair_raw_producer_and_verifier_files
test_runtime_trace_writes_llm_raw_file
test_runtime_trace_records_raw_file_sha256_and_bytes
test_runtime_trace_records_outcome_route_tag
test_runtime_trace_records_provider_usage_when_available
test_runtime_trace_can_be_disabled
test_trace_events_include_commit_before_step_not_commit_after_step
test_trace_resume_uses_next_sequence_and_never_overwrites_raw_files
18.4 Provider usage tests

Add/update:

test_token_usage_model_accepts_partial_usage
test_producer_response_usage_defaults_to_none
test_outcome_response_usage_defaults_to_none
test_fake_provider_can_emit_usage
test_pair_step_finish_contains_producer_and_verifier_usage
test_llm_step_finish_contains_llm_usage
18.5 Static graph tests

Add:

test_static_step_graph_written_for_run
test_static_step_graph_includes_step_kind_prompts_routes_and_artifact_names
test_static_step_graph_includes_route_contracts_and_schema_presence
18.6 Integration tests

Add:

test_normal_run_writes_run_json_events_trace_git_tracking_static_graph_and_raw_dir
test_run_json_contains_git_tracking_and_tracing_sections
test_step_policy_run_can_be_replayed_by_recorded_commit
test_runtime_observability_preserves_workflow_extension_behavior
test_tests_that_do_not_initialize_git_disable_git_tracking_explicitly

Because git tracking is enabled by default, tests that execute runs outside a git repository must either initialize a temporary git repo or explicitly disable git tracking.

19. Documentation updates

Update:

docs/architecture.md
docs/authoring.md

Required documentation points:

Git tracking is runtime-owned and enabled by default.
Runtime git tracking uses git commit-all.
The repository must be clean before a git-tracked run starts.
Runtime tracing is enabled by default.
Workflows do not need GitTracking or Tracing declarations for normal observability.
Workflow-declared GitTracking is ignored with a deprecation warning.
Workflow-declared Tracing remains sidecar-compatible.
Git commits are the workspace replay boundary.
Autoloop does not classify changed paths for replay.
Future optimization workflows consume run.json, events.jsonl, trace.jsonl, git_tracking.jsonl, static_step_graph.json, and raw/.

Update tests in tests/test_architecture_baseline_docs.py if needed.

20. Implementation order

Implement in this order:

1. Add TokenUsage and StepProviderUsage models.
2. Extend ProducerResponse and OutcomeResponse with optional usage.
3. Extend StepFinish with optional provider_usage.
4. Propagate usage through PairStep and LLMStep execution.
5. Add GitRepo commit-all helpers.
6. Add runtime git tracking config and CLI overrides.
7. Add runtime tracing config and CLI overrides.
8. Implement runtime/git_tracking.py.
9. Implement runtime/tracing.py.
10. Implement static_step_graph.json serializer/writer.
11. Add runtime extension factory support in engine/runner.
12. Implement runtime/observability.py.
13. Filter workflow-declared GitTracking with warning.
14. Persist run.json git/tracing metadata through centralized helpers.
15. Write raw output files and raw refs.
16. Implement resume sequence handling.
17. Add tests.
18. Update docs.
21. Acceptance criteria

The implementation is complete when:

A normal run in a clean git repo creates git commits by default.
A normal run fails before workspace creation when git tracking is enabled and the repo is dirty.
--no-git disables git tracking.
--git-commit-policy run uses run-boundary commits.
--git-commit-policy step uses step-level commits.
Runtime git tracking uses git add --all.
Runtime git tracking does not path-filter.
Workflow-declared GitTracking is ignored with a warning.
A normal run writes trace.jsonl by default.
--no-trace disables trace writing.
A normal run writes git_tracking.jsonl.
A normal run writes static_step_graph.json.
A normal run writes raw producer/verifier/LLM output files independent of workflow-declared log artifacts.
trace.jsonl records commit_before_step, not commit_after_step.
git_tracking.jsonl records commit_after_step.
run.json summarizes git/tracing metadata.
Resume appends trace/git/raw evidence without overwriting.
Provider token usage is typed but optional.
Workflow-declared Tracing is not required for trace.jsonl.
Existing workflow extension behavior remains valid.
Existing run/resume/answer behavior remains valid.
All tests pass.
22. Final boundary statement

After this plan:

Runtime owns:
  git tracking
  commit-all replay snapshots
  trace.jsonl
  git_tracking.jsonl
  raw output files
  static_step_graph.json
  provider usage capture

Workflow owns:
  step semantics
  prompts
  route contracts
  artifact contracts
  domain behavior

Git owns:
  workspace replay

Future optimization workflows consume:
  run.json
  events.jsonl
  trace.jsonl
  git_tracking.jsonl
  static_step_graph.json
  raw/

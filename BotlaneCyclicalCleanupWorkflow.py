from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from botlane import (
    AWAIT_INPUT,
    FAIL,
    FINISH,
    SELF,
    Json,
    Md,
    Route,
    Session,
    Workflow,
    produce_verify_step,
)


# =============================================================================
# Input model
# =============================================================================


class CleanupScope(BaseModel):
    """Input for one cyclical Botlane cleanup run."""

    scope: str = Field(
        default="botlane",
        description=(
            "Cleanup scope, such as botlane/core, botlane/runtime, branch runtime, "
            "placeholder system, SDK, simple API, or botlane_optimizer."
        ),
    )
    cleanup_goal: str = Field(
        default=(
            "Reduce production LOC and conceptual bloat without changing public "
            "SDK/simple behavior."
        ),
    )
    max_cleanup_batch_size: Literal["small", "medium", "large"] = "small"
    require_production_loc_decrease: bool = True
    allow_test_loc_increase: bool = True
    allow_public_api_changes: bool = False
    require_no_new_technical_debt: bool = True
    require_taste_not_decrease: bool = True
    notes: str = ""


# =============================================================================
# Shared models
# =============================================================================


class CleanupIssue(BaseModel):
    id: str
    title: str
    files: list[str]
    symbols: list[str] = Field(default_factory=list)
    category: Literal[
        "dead_code",
        "compatibility_shim",
        "duplicate_logic",
        "optional_bag",
        "dict_runtime_payload",
        "single_use_abstraction",
        "engine_private_coupling",
        "placeholder_duplication",
        "route_duplication",
        "test_debt",
        "technical_debt",
        "taste_regression",
        "public_boundary_leak",
        "stale_identity",
        "other",
    ]
    evidence: str
    public_api_impact: Literal["none", "possible", "known"]
    recommended_action: Literal["delete", "inline", "merge", "replace", "keep", "defer"]
    behavior_lock_tests: list[str] = Field(default_factory=list)
    technical_debt_risk: str = ""
    taste_risk: str = ""
    estimated_production_loc_delta: int | None = None
    risk: Literal["low", "medium", "high"] = "medium"


class CleanupAnalysisPlan(BaseModel):
    """Combined measurement, issue inventory, and approved cleanup plan."""

    scope: str

    production_loc_by_area: dict[str, int] = Field(default_factory=dict)
    test_loc_by_area: dict[str, int] = Field(default_factory=dict)
    public_exports_snapshot: dict[str, list[str]] = Field(default_factory=dict)
    stale_symbol_counts: dict[str, int] = Field(default_factory=dict)
    engine_private_call_sites: list[str] = Field(default_factory=list)
    duplicate_logic_clusters: list[str] = Field(default_factory=list)
    large_or_complex_files: list[str] = Field(default_factory=list)

    issues: list[CleanupIssue] = Field(default_factory=list)
    selected_issue_ids: list[str] = Field(default_factory=list)

    plan_summary: str
    batch_size: Literal["small", "medium", "large"]
    files_to_touch: list[str] = Field(default_factory=list)
    behavior_preservation_strategy: str
    tests_to_add_or_update: list[str] = Field(default_factory=list)
    commands_to_run: list[str] = Field(default_factory=list)

    public_api_invariants: list[str] = Field(default_factory=list)
    sdk_simple_invariants: list[str] = Field(default_factory=list)
    botlane_identity_invariants: list[str] = Field(default_factory=list)
    no_new_technical_debt_invariants: list[str] = Field(default_factory=list)
    taste_preservation_invariants: list[str] = Field(default_factory=list)

    expected_production_loc_delta: int | None = None
    expected_test_loc_delta: int | None = None
    risk_level: Literal["low", "medium", "high"]
    approved_for_implementation: bool


class CleanupImplementationReport(BaseModel):
    """Implementation and verification report for one cleanup batch."""

    scope: str
    implemented_issue_ids: list[str]

    deleted_symbols: list[str] = Field(default_factory=list)
    inlined_symbols: list[str] = Field(default_factory=list)
    merged_duplicate_logic: list[str] = Field(default_factory=list)
    replaced_representations: list[str] = Field(default_factory=list)
    removed_files: list[str] = Field(default_factory=list)
    files_changed: list[str] = Field(default_factory=list)

    production_loc_delta: int | None = None
    test_loc_delta: int | None = None

    public_api_changed: bool = False
    sdk_simple_behavior_changed: bool = False
    botlane_identity_changed: bool = False
    technical_debt_introduced: bool = False
    architecture_taste_decreased: bool = False

    technical_debt_notes: list[str] = Field(default_factory=list)
    taste_notes: list[str] = Field(default_factory=list)
    commands_run: list[str] = Field(default_factory=list)
    test_results: dict[str, str] = Field(default_factory=dict)
    remaining_risks: list[str] = Field(default_factory=list)


class CleanupAuditDecision(BaseModel):
    """Independent final audit and routing decision."""

    scope: str

    public_api_unchanged: bool
    sdk_simple_behavior_unchanged: bool
    botlane_identity_unchanged: bool

    no_new_technical_debt: bool
    architecture_taste_unchanged_or_improved: bool

    no_new_compatibility_shims: bool
    no_new_duplicate_representations: bool
    no_new_engine_private_coupling: bool
    no_new_placeholder_duplication: bool
    no_new_route_duplication: bool
    no_new_optional_bags: bool
    no_new_god_objects: bool

    production_loc_decreased_or_old_representation_removed: bool
    tests_passed: bool
    strictness_strengthened_or_preserved: bool

    audit_findings: list[str] = Field(default_factory=list)
    technical_debt_findings: list[str] = Field(default_factory=list)
    taste_findings: list[str] = Field(default_factory=list)
    remaining_gap_ids: list[str] = Field(default_factory=list)

    route: Literal["complete", "repeat", "blocked", "fail"]
    reason: str
    next_scope: str | None = None
    blocking_question: str | None = None


# =============================================================================
# Artifacts
# =============================================================================


CLEANUP_ANALYSIS_PLAN = Json(
    "cleanup_analysis_plan",
    CleanupAnalysisPlan,
    path="{workflow_folder}/cleanup/analysis_plan.json",
    required=True,
)

IMPLEMENTATION_REPORT = Json(
    "cleanup_implementation_report",
    CleanupImplementationReport,
    path="{workflow_folder}/cleanup/implementation.json",
    required=True,
)

AUDIT_DECISION = Json(
    "cleanup_audit_decision",
    CleanupAuditDecision,
    path="{workflow_folder}/cleanup/audit_decision.json",
    required=True,
)

CLEANUP_NOTES = Md(
    "cleanup_notes",
    path="{workflow_folder}/cleanup/notes.md",
    required=True,
)

FINAL_SUMMARY = Md(
    "cleanup_cycle_summary",
    path="{workflow_folder}/cleanup/summary.md",
    required=True,
)


# =============================================================================
# Workflow
# =============================================================================


class BotlaneCyclicalCleanupWorkflow(Workflow):
    """Three produce/verify cleanup steps: analyze/plan, implement/verify, audit/decide."""

    Input = CleanupScope

    class State(BaseModel):
        cycle_count: int = 0
        completed_issue_ids: list[str] = Field(default_factory=list)
        remaining_gap_ids: list[str] = Field(default_factory=list)
        last_scope: str = ""
        last_route: str = ""

    audit_session = Session.fresh()
    audit_verifier_session = Session.fresh()

    analyze_and_plan = produce_verify_step(
        producer_prompt="""
You are running the analysis and planning phase for one Botlane cleanup cycle.

Scope:
{input.scope}

Goal:
{input.cleanup_goal}

Cycle constraints:
- Max batch size: {input.max_cleanup_batch_size}
- Require production LOC decrease: {input.require_production_loc_decrease}
- Allow test LOC increase: {input.allow_test_loc_increase}
- Allow public API changes: {input.allow_public_api_changes}
- Require no new technical debt: {input.require_no_new_technical_debt}
- Require architecture/code taste not to decrease: {input.require_taste_not_decrease}

User notes:
{input.notes}

Your job is to do all of the following in one merged step:

1. Measure
   - production LOC by area:
     - botlane/core
     - botlane/runtime
     - botlane/sdk.py
     - botlane/simple.py
     - botlane/stdlib
     - botlane/extensions
     - botlane_optimizer
   - test LOC separately
   - current botlane.__all__
   - current botlane.core.__all__
   - current botlane.core.branch_groups.__all__
   - top large or complex files
   - Engine private-method call sites from collaborators
   - duplicate parser/renderer/validator clusters
   - stale/bloat symbol counts

2. Identify bloat, stale code, technical debt, and taste risks
   Look for:
   - dead code
   - compatibility shims
   - old internal representations
   - duplicate parsers/renderers
   - duplicate validation paths
   - dict-shaped runtime data where typed data exists
   - optional-field bags
   - route metadata duplication
   - single-use abstractions
   - broad manager/god objects
   - Engine private-method coupling
   - tests preserving old internals instead of public behavior
   - stale Botlane identity strings
   - technical debt introduced by prior refactors
   - existing code that reduces architectural taste

3. Classify each issue
   Use:
   - delete
   - inline
   - merge
   - replace
   - keep
   - defer

4. Build the smallest safe cleanup plan
   The plan must:
   - preserve botlane.__all__
   - preserve botlane.core.__all__ unless explicitly allowed
   - preserve Botlane.run(...)
   - preserve Botlane.step(...)
   - preserve simple authoring behavior
   - preserve public route sentinels
   - preserve artifact helpers
   - preserve .botlane persistence identity and schema IDs
   - add or confirm behavior-lock tests
   - avoid introducing technical debt
   - avoid decreasing code or architecture taste

No-new-technical-debt criteria:
- no new compatibility wrappers
- no new TODO/FIXME without owner, removal condition, and test
- no new duplicate representation
- no new duplicate parser/renderer/validator
- no new broad manager/god object
- no hidden public API change
- no unexplained production LOC growth
- no test weakening
- no "temporary" bypass of production behavior
- no ambiguity around canonical ownership

Architecture/code taste criteria:
- data structures must become stronger, not weaker
- relationships between data structures must become clearer, not more implicit
- do not replace typed internal data with strings or loosely shaped dicts
- do not introduce new optional-field bags
- do not add special-case branches when a better representation would remove the special case
- do not duplicate canonical state across multiple objects
- do not create a new abstraction unless it removes complexity or clarifies ownership
- do not create a broad service, manager, or god object
- do not make core logic more nested or harder to follow
- do not add route/string dispatch where typed actions or variants should be used
- do not add indirection that only preserves old behavior without simplifying the model
- do not harm practical runtime locality or performance-sensitive data flow without a clear reason
- prefer simple, direct, typed representations over theoretical purity

Select only a small coherent batch unless the input explicitly allows a larger one.

Write:
- cleanup/analysis_plan.json
- cleanup/notes.md

The JSON plan must set approved_for_implementation=false if the cleanup is unsafe,
if it introduces technical debt, or if it decreases overall code/architecture taste.

Emit route:
- accepted if the plan is safe and approved
- needs_rework if the plan is unsafe, too broad, under-tested, debt-producing, or taste-regressing
""",
        verifier_prompt="""
You are verifying the analysis and cleanup plan.

Read:
- cleanup/analysis_plan.json
- cleanup/notes.md

Accept the plan only if:
- public SDK/simple behavior is preserved
- botlane.__all__ is preserved
- botlane.core.__all__ is preserved unless explicitly allowed
- .botlane identity and schema IDs are preserved
- the cleanup batch is small and coherent
- the plan reduces production LOC or removes a whole obsolete representation
- behavior-lock tests are identified
- strictness tests are preserved or strengthened
- no technical debt is introduced
- architecture/code taste is unchanged or improved

Reject the plan if it:
- introduces compatibility shims
- adds a new duplicate representation
- creates a broad manager/god object
- moves code without simplification
- increases production LOC without deleting a larger obsolete concept
- weakens tests
- hides uncertainty
- leaves no audit path
- introduces technical debt
- weakens data structures or makes data relationships less clear
- introduces stringly control flow where typed control flow is available
- introduces optional-field bags
- creates new special cases instead of eliminating them through representation
- makes core logic more nested, indirect, or harder to reason about
- decreases overall code or architecture taste

If accepted:
- ensure approved_for_implementation=true.
- ensure no_new_technical_debt_invariants are explicit and testable.
- ensure taste_preservation_invariants are explicit and testable.
- emit route accepted.

If rejected:
- set approved_for_implementation=false.
- explain what must be fixed.
- emit route needs_rework.

Write updated:
- cleanup/analysis_plan.json
- cleanup/notes.md
""",
        producer_writes=[CLEANUP_ANALYSIS_PLAN, CLEANUP_NOTES],
        verifier_reads=[CLEANUP_ANALYSIS_PLAN, CLEANUP_NOTES],
        verifier_writes=[CLEANUP_ANALYSIS_PLAN, CLEANUP_NOTES],
        routes={
            "accepted": Route(target="implement_and_verify"),
            "needs_rework": SELF,
        },
    )

    implement_and_verify = produce_verify_step(
        producer_prompt="""
You are implementing the approved Botlane cleanup batch.

Read:
- cleanup/analysis_plan.json
- cleanup/notes.md

Implement only the approved cleanup batch.

Implementation rules:
- preserve public SDK/simple behavior
- preserve botlane.__all__
- preserve botlane.core.__all__ unless explicitly allowed
- preserve .botlane persistence identity and schema IDs
- delete stale code rather than wrapping it
- inline single-use abstractions where appropriate
- merge duplicate logic into one canonical owner
- replace old representations directly with canonical typed data
- remove dead imports
- remove obsolete tests that preserve old internals
- add behavior-lock tests and strictness tests required by the plan
- do not introduce technical debt
- do not decrease code or architecture taste

Technical debt prevention checklist:
- no new compatibility layer
- no new duplicate parser/renderer/validator
- no new duplicate runtime representation
- no new public/private boundary leak
- no new stale alias
- no new "temporary" code without removal condition
- no unexplained TODO/FIXME
- no test weakening
- no unexplained production LOC growth
- no broad manager/god object

Taste preservation checklist:
- no weaker data structures
- no less clear data relationships
- no new optional-field bag
- no new stringly runtime control flow
- no new duplicate source of truth
- no new needless abstraction
- no new god object
- no new special-case branch that should be solved by representation
- no deeper nesting in core logic without clear necessity
- no compatibility wrapper disguised as cleanup
- no extra indirection without simplification
- no runtime performance/locality regression without justification

Run the targeted commands from the plan. Capture outputs.

Write:
- cleanup/implementation.json
- append implementation notes to cleanup/notes.md

Emit route:
- accepted if the implementation satisfies the plan and quality gates
- needs_rework if remediation is required
""",
        verifier_prompt="""
You are verifying the cleanup implementation.

Read:
- cleanup/analysis_plan.json
- cleanup/implementation.json
- cleanup/notes.md

Reject the implementation if:
- public SDK/simple behavior changed
- public exports changed unexpectedly
- .botlane identity or schema IDs changed unexpectedly
- new technical debt was introduced
- architecture/code taste decreased
- a compatibility shim was added
- stale internals were merely moved or renamed
- production LOC increased without removing a larger obsolete concept
- tests were weakened
- strictness coverage was not added or preserved
- files outside the approved scope were changed without justification
- data structures became weaker
- data relationships became less explicit
- new optional-field bags were introduced
- new stringly runtime control flow was introduced
- a new broad manager/god object was introduced
- special cases increased instead of decreasing

Accept only if:
- technical_debt_introduced=false
- architecture_taste_decreased=false
- public_api_changed=false unless explicitly approved
- sdk_simple_behavior_changed=false
- botlane_identity_changed=false
- tests and commands run are recorded
- cleanup actually deleted, inlined, merged, or replaced stale code
- no-new-technical-debt criteria are satisfied
- architecture/code taste is unchanged or improved

If accepted:
- emit route accepted.

If rejected:
- emit route needs_rework and add exact remediation notes.

Write updated:
- cleanup/implementation.json
- cleanup/notes.md
""",
        reads=[CLEANUP_ANALYSIS_PLAN, CLEANUP_NOTES],
        producer_writes=[IMPLEMENTATION_REPORT, CLEANUP_NOTES],
        verifier_reads=[CLEANUP_ANALYSIS_PLAN, IMPLEMENTATION_REPORT, CLEANUP_NOTES],
        verifier_writes=[IMPLEMENTATION_REPORT, CLEANUP_NOTES],
        routes={
            "accepted": Route(target="audit_and_decide"),
            "needs_rework": SELF,
        },
    )

    audit_and_decide = produce_verify_step(
        producer_prompt="""
You are auditing one completed Botlane cleanup cycle and deciding whether to repeat.

You are running in an independent fresh audit session.
Do not rely on prior conversational memory from analyze/plan or implement/verify.
Base the audit only on written artifacts, changed files, command outputs, tests, and explicit evidence.

Read:
- cleanup/analysis_plan.json
- cleanup/implementation.json
- cleanup/notes.md

Audit criteria:

1. Public API
   - botlane.__all__ unchanged
   - botlane.core.__all__ unchanged unless explicitly approved
   - botlane.core.branch_groups.__all__ changed only if explicitly approved
   - no internal plan objects exported publicly

2. SDK/simple behavior
   - Botlane.run unchanged
   - Botlane.step unchanged
   - simple Workflow / step / produce_verify_step / python_step / workflow_step authoring unchanged
   - public route sentinels unchanged
   - artifact helpers unchanged
   - provider_questions unchanged
   - on_input pause/resume unchanged
   - retention unchanged

3. Botlane identity
   - .botlane unchanged
   - .botlane-sdk-task.json unchanged
   - botlane.sdk_task/v1 unchanged
   - botlane.branch_results/v1 unchanged

4. Cleanup quality
   - production LOC decreased, or an entire obsolete representation was removed
   - no new compatibility shim
   - no new duplicate representation
   - no new duplicate parser/renderer/validator
   - no new Engine-private collaborator coupling
   - no new optional-field bag
   - no new broad manager/god object
   - no test weakening

5. Technical debt
   - no new technical debt introduced
   - no new TODO/FIXME without owner, removal condition, and test coverage
   - no new temporary branch without owner and deletion trigger
   - no new ambiguity around canonical ownership
   - no hidden behavior dependency on old internals
   - no "pass for now" workaround
   - no test-only bypass of production behavior

6. Architecture/code taste
   - overall architecture taste is unchanged or improved
   - data structures are stronger or simpler
   - relationships between data structures are clearer
   - special cases were removed or reduced, not increased
   - route/control flow is more typed, not more stringly
   - runtime values are more typed, not more dict-shaped
   - duplicated representations were removed, not renamed
   - no new optional-field bags were introduced
   - no broad manager/god object was introduced
   - core logic is flatter or simpler, not more nested or indirect
   - abstractions are pragmatic and pay for themselves
   - performance-sensitive paths were not made worse without justification

7. Remaining gaps
   - identify unresolved bloat
   - identify cleanup regressions
   - identify next cleanup scope if another cycle is warranted

Decision rules:
- route complete if no high-value cleanup gaps remain for this scope.
- route repeat if gaps remain and another cleanup cycle is safe.
- route blocked if human input is required.
- route fail if public behavior changed, tests failed, technical debt was introduced, or architecture/code taste decreased.

Write:
- cleanup/audit_decision.json
- cleanup/summary.md

The JSON must include:
- route
- reason
- remaining_gap_ids
- next_scope when route=repeat
- blocking_question when route=blocked

Emit the route tag exactly:
- complete
- repeat
- blocked
- fail
""",
        verifier_prompt="""
You are the independent audit verifier.

You are also running in the audit step's fresh session. Do not rely on any prior conversation outside the written artifacts and explicit evidence.

Read:
- cleanup/audit_decision.json
- cleanup/summary.md
- cleanup/analysis_plan.json
- cleanup/implementation.json
- cleanup/notes.md

Verify the audit itself.

Reject the audit decision if:
- it approves a cleanup that changed public SDK/simple behavior
- it approves a cleanup that changed public exports unexpectedly
- it approves a cleanup that introduced technical debt
- it approves a cleanup that decreased architecture/code taste
- it ignores failed or missing tests
- it ignores remaining high-risk gaps
- it routes complete while high-value unresolved bloat remains
- it routes repeat without a safe next_scope
- it routes blocked without a concrete blocking_question
- it routes fail without a concrete reason

Accept only if:
- the audit decision is evidence-based
- the route is one of complete, repeat, blocked, fail
- the route matches the audit findings
- remaining gaps are listed
- taste and technical-debt findings are explicit

If the audit decision is wrong, correct the JSON and summary.

Write updated:
- cleanup/audit_decision.json
- cleanup/summary.md

Emit the same route tag as the final JSON route.
""",
        session=audit_session,
        verifier_session=audit_verifier_session,
        reads=[CLEANUP_ANALYSIS_PLAN, IMPLEMENTATION_REPORT, CLEANUP_NOTES],
        producer_writes=[AUDIT_DECISION, FINAL_SUMMARY],
        verifier_reads=[
            AUDIT_DECISION,
            FINAL_SUMMARY,
            CLEANUP_ANALYSIS_PLAN,
            IMPLEMENTATION_REPORT,
            CLEANUP_NOTES,
        ],
        verifier_writes=[AUDIT_DECISION, FINAL_SUMMARY],
        routes={
            "complete": FINISH,
            "repeat": Route(
                target="analyze_and_plan",
                summary="Run another cleanup cycle on remaining gaps.",
            ),
            "blocked": AWAIT_INPUT,
            "fail": FAIL,
        },
    )

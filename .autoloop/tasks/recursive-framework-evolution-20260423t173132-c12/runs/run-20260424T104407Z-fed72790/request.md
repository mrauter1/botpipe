# Recursive Workflow + Framework Improvement (Cycle 12)

Standing memory files to read and update:
- `.autoloop_recursive/framework_evolution_charter.md`
- `.autoloop_recursive/framework_roadmap.md`
- `.autoloop_recursive/framework_gap_ledger.md`
- `.autoloop_recursive/workflow_candidate_ledger.md`

Mandatory inspection before changes:
- `docs/autoloop_workflow_framework_prd.md`
- `docs/autoloop_workflow_framework_adr.md`
- `src/autoloop/framework/workflows.py`
- `src/autoloop/framework/pairs.py`
- `src/autoloop/framework/store.py`
- `src/autoloop/main.py`
- current workflow definitions under `src/autoloop/workflows/`

Foundational observation:
- Before choosing another workflow or reusable workflow building block, assess whether the repository already has a strong workflow-builder capability for Autoloop.
- The workflow builder is itself a workflow or reusable workflow building block.
- Its job is to take a valuable problem statement, workflow idea, or reusable recipe concept and turn it into a high-quality Autoloop workflow or reusable workflow building block, including appropriate prompts, artifacts, interfaces, tests, and documentation.
- If such a capability does not yet exist, or is clearly inadequate, strongly consider making this cycle’s addition the workflow builder or a major improvement to it.
- Once the workflow-builder capability exists in strong form, later cycles may prioritize other problem areas more freely.
- If the repository lacks a credible workflow-builder capability and you do not choose it in this cycle, explicitly justify why another addition is the higher-priority move.

This cycle has two mandatory parts that must ship in the same change set.

Part 1: Create one new high-value workflow or reusable workflow building block

Choose and implement one addition that makes Autoloop more useful for real software work.

The addition may be either:
- a high-value end-to-end workflow that solves a meaningful problem for a software company, software shop, product organization, or engineering organization, or
- a reusable workflow recipe, pattern, or building block that captures a valuable repeatable unit of work and can be composed into larger workflows

Important domains include, but are not limited to:
- software development and delivery
- product discovery, product strategy, and product development
- business analysis, solution analysis, and requirements analysis
- architecture and technical planning
- modernization, migration, quality, reliability, security, and release operations
- customer or project intake, estimation, delivery planning, and execution management

Prefer additions that help organizations do real work such as:
- understanding users, markets, competitors, constraints, or opportunities
- shaping products, requirements, solution options, or delivery strategy
- planning, coordinating, or executing software delivery
- improving codebases, platforms, systems, or technical direction
- validating quality, release readiness, or operational safety
- responding to incidents, regressions, modernization needs, or execution risk
- capturing valuable repeatable patterns that should be easy to invoke and reuse inside larger workflows

For end-to-end workflows, prefer additions that help teams move from ambiguous or incomplete input to a useful terminal result.

For reusable building blocks, prefer additions that capture recurring and valuable patterns that should be easy to compose, inspect, and reuse across multiple workflows.

The chosen addition may take whatever form best fits the problem. It may be research-heavy, planning-heavy, implementation-heavy, remediation-heavy, delivery-heavy, or hybrid. It may also represent a materially different strategy for a problem area already represented in the repository.

Before choosing, explore a small set of strong candidates and compare them briefly.
- Explicitly include the workflow-builder workflow unless the repository already contains a strong version of it.
- Choose the candidate that best balances:
  - real-world usefulness
  - fit for long-running multi-turn execution when appropriate
  - fit for agentic harnesses such as Codex CLI or Claude Code when appropriate
  - clarity of terminal outcome or reusable value
  - potential to reveal reusable framework improvements

Do not choose an addition merely because it is awkward for the current framework. Choose it because it is genuinely worth having, then use the resulting pressure to improve the framework.

For the chosen addition, explain:
- what problem it solves
- why it matters
- who would use or sponsor it
- whether it is best understood as an end-to-end workflow or a reusable building block
- why Autoloop is a good fit
- why a one-shot interaction would be insufficient, if applicable
- what useful terminal outcome, reusable capability, or execution-ready result it should produce

Workflow authoring doctrine (must follow):

1. Global-vs-local boundary
- The workflow owns the global SOP.
- The provider owns the cognition inside the current step.
- The rendered prompt template is the provider-facing local execution contract for that step.
- The runtime stays narrow and mechanical.

2. Prompt-template doctrine
- Do not invent a separate provider-facing packet abstraction.
- The prompt template itself must tell the provider:
  - which role it is executing
  - the purpose of the current step
  - the current work item and why it exists
  - which artifacts to read
  - how to interpret those artifacts
  - which artifacts to create, update, or leave untouched
  - where to write them
  - how each artifact should be handled
  - what the expected outcome is
  - what evidence must be produced
  - how to decide among the legal routes
  - what is in scope, out of scope, and forbidden

3. Runtime-injected control contract
- The runtime may inject or enforce only narrow machine-readable control surfaces such as:
  - `expected_output_schema`
  - `available_routes`
  - `route_contracts`
- The runtime may validate returned routes and schemas, and enforce reserved-route behavior.
- Do not move provider-facing operational guidance into runtime-only abstractions.

4. Work-item boundary doctrine
- Do not optimize for small tasks.
- Work items may be ambitious and long-horizon.
- Work-item boundaries should be defined by coherence across:
  - role / specialization
  - artifact family
  - acceptance surface
  - verifier authority
  - local repairability
- `needs_rework` means the same work-item contract still holds.
- `needs_replan` means the work-item boundary, sequencing, specialization, or artifact graph changed materially.

5. Artifact-first design
- Prefer filesystem artifacts as the durable work product.
- Provider prose is control metadata, not the primary deliverable.
- For each step, specify:
  - required input artifacts
  - required output artifacts
  - exact names and paths or path templates
  - overwrite / append / patch handling
  - which artifacts are authoritative
  - which artifacts are evidence
  - which artifacts are consumed downstream

6. Verification doctrine
- For any non-trivial or quality-sensitive work, explicitly enforce producer/verifier behavior.
- Verification must have clear evidence requirements.
- Rework loops must be bounded.
- Replan must be explicit when local repair is no longer the right response.

7. Recursive self-improvement doctrine
- Candidate workflow, prompt, policy, or artifact changes may be proposed by the provider.
- Promotion must remain deterministic and evidence-gated.
- Baseline, candidate, evaluation, regression, promotion, and rollback artifacts should be explicit.

Workflow authoring requirements for Part 1:
- Treat the prompt template as the provider-facing local execution contract for each step.
- Do not introduce a separate provider-facing packet abstraction.
- Keep runtime/provider boundary crisp:
  - runtime injects or enforces only `expected_output_schema`, `available_routes`, and `route_contracts`
  - prompt templates carry the provider-facing operational guidance
- Work items may be ambitious and long-horizon; define boundaries by role/specialization coherence, artifact family coherence, and acceptance coherence.
- For every workflow or reusable building block, make explicit:
  - workflow objective
  - global deterministic workflow responsibilities
  - provider-owned cognitive responsibilities
  - work-item boundary doctrine for this workflow
  - role topology
  - control flow as explicit procedure
  - route grammar
  - artifact contract
  - runtime-injected control contract
  - step prompt templates for each role
  - verification and evidence contract
  - rework / replan / block / fail policy
  - recursive self-improvement policy, if applicable

Example workflow families for inspiration only (examples, not templates):

######
End-to-end workflow examples:
1. customer_request_to_delivery_plan

Input: “A customer wants SSO, audit logs, and SCIM this quarter.”
Output: scoped delivery plan, architecture options, dependency map, risk register, phased backlog, staffing recommendation, and a customer-safe commitment draft.
Flow: intake → clarify business outcome → map capability gaps → shape solution options → estimate delivery slices → identify delivery risks → recommend scope/sequence → produce commit-ready plan.
Why this is good: it is not “business analysis” in the abstract; it goes all the way from ambiguous deal pressure to an execution-ready delivery position.

2. product_idea_to_prd_and_release_slices

Input: “We should launch usage-based billing for mid-market customers.”
Output: PRD, user/problem framing, pricing/ops constraints, architecture implications, analytics plan, rollout plan, and release slices.
Flow: problem framing → stakeholder assumptions → user journeys → success metrics → solution shape → constraints → MVP/release slicing → decision memo.
Why this is good: it ends with something a product, engineering, and go-to-market team can actually run.

3. incident_to_hardening_program

Input: “Payments API returned 500s for 47 minutes last night.”
Output: incident summary, timeline, likely cause ranking, immediate mitigation plan, customer communication draft, hardening backlog, observability gaps, and follow-up owners.
Flow: evidence collection → blast-radius analysis → hypothesis ranking → mitigation options → verification plan → stakeholder comms → hardening recommendations → owner-ready backlog.
Why this is good: it is not just diagnosis; it closes the loop into prevention.

4. release_candidate_to_go_no_go

Input: “We want to ship release 2026.04 on Friday.”
Output: go/no-go decision, blocking issues list, rollback plan, test evidence pack, operational checklist, release communications, and a signed release recommendation.
Flow: gather release contents → check completeness → verify test evidence → assess operational readiness → assess rollback safety → assess customer impact → produce go/no-go package.
Why this is good: it ends in an operational decision, not a vague status report.

5. legacy_service_to_modernization_plan

Input: “Replace the monolith’s billing module without disrupting renewals.”
Output: current-state map, seam analysis, target-state architecture, migration strategy, phased cutover plan, dependency/risk ledger, and migration backlog.
Flow: inventory current behavior → identify seams and contracts → define target boundaries → compare migration strategies → recommend phased plan → identify proving milestones → produce execution package.
Why this is good: it is concrete modernization work, not generic “architecture.”

6. security_finding_to_verified_remediation

Input: “Pentest found privilege escalation in admin impersonation.”
Output: exploit summary, affected surface, remediation options, chosen fix, validation plan, rollout plan, and evidence of closure.
Flow: reproduce finding → bound impact → map code/config causes → design remediation options → choose fix → define verification evidence → prepare rollout and comms → produce closure packet.
Why this is good: it goes from finding to verified remediation, which is the actual business need.

7. failing_delivery_to_recovery_plan

Input: “This initiative is six weeks late and nobody trusts the plan.”
Output: reset status, root causes, scope triage, dependency cleanup, rebaselined milestones, owner/accountability map, and recovery narrative for leadership.
Flow: reality capture → missed-assumption analysis → backlog triage → dependency compression → milestone redesign → risk negotiation → recovery recommendation.
Why this is good: it handles delivery recovery as an end-to-end problem, not just replanning in the abstract.

8. customer_escalation_to_resolution_package

Input: “Strategic customer says reporting is unreliable and may churn.”
Output: issue brief, evidence pack, problem decomposition, response options, immediate stabilizing actions, customer communication draft, and long-term remediation plan.
Flow: intake escalation → gather evidence → separate symptom from root cause → rank response options → define immediate and durable actions → prepare internal/external comms → package executive recommendation.
Why this is good: it ends with both action and communication, which is how these cases are actually handled.

9. workflow_idea_to_workflow_package

Input: “We need a workflow for release-readiness reviews.”
Output: workflow package with topology, control flow, prompts, artifact contract, parameter model, tests, docs, and example usage.
Flow: clarify user job → decide if end-to-end workflow or reusable building block → define inputs/outputs → define role/step topology → define routes and control grammar → define artifacts → generate prompts → add tests/docs → publish package.
Why this is good: this is the workflow-builder as real infrastructure, not a side experiment. It directly matches the brief’s emphasis on making the framework able to design and refine its own workflows.

10. deal_to_solution_architecture_and_delivery_shape

Input: “Prospect needs regional data residency, SAML, and delegated admin in 90 days.”
Output: solution architecture, gaps vs current platform, delivery shape, sequencing options, commercial risk notes, and a recommended delivery posture.
Flow: extract requirements → classify hard constraints → map platform fit/gaps → propose solution variants → analyze delivery feasibility → identify commercial/operational risks → produce recommended shape.
Why this is good: it directly spans pre-sales, architecture, and delivery instead of splitting them into separate vague workflows.

Short naming rule

A strong end-to-end workflow name should read like:

<starting situation>_to_<terminal outcome>

Good:

incident_to_hardening_program
release_candidate_to_go_no_go
workflow_idea_to_workflow_package

Weak:

incident_analysis
release_review
business_analysis
product_discovery
Short quality rule

A workflow is truly end-to-end only if it has all three:

a concrete trigger,
a concrete terminal decision or output package,
clear artifacts that another team could immediately use.
####

###
The ultimate 10 workflows
1. task_to_workflow_strategy

The front door for all work.

Input: an arbitrary task, request, problem, or opportunity.
Output: a decision among:

run an existing workflow as-is,
compose several workflows,
adapt an existing workflow for this case,
create a new workflow because no suitable one exists.

Why it matters: this is the missing chooser/router layer you called out. Without it, the system keeps reinventing or misapplying workflows.

2. task_to_candidate_workflow_set

The workflow discovery engine.

Input: a task plus desired outcome, constraints, and evidence expectations.
Output: a ranked set of reusable candidate workflows and building blocks, with fit-gap analysis and confidence.

What it does end-to-end:

analyzes the task shape,
searches the workflow registry/library,
identifies reusable workflows and sub-workflows,
explains why each candidate is a fit or mismatch,
surfaces missing capabilities.

Why it matters: every high-performing system needs retrieval before creation.

3. candidate_workflow_to_adapted_execution_plan

The reuse-over-rebuild engine.

Input: a chosen existing workflow and a specific task context.
Output: an adapted execution plan: parameters, step overrides, artifact expectations, sub-workflow composition, escalation policy, and eval expectations.

What it does end-to-end:

compares generic workflow assumptions against the current task,
decides what can stay fixed,
decides what must be parameterized,
decides whether composition is needed,
produces a task-ready adapted run plan.

Why it matters: most valuable work should be adaptation, not greenfield authoring.

4. workflow_gap_to_new_workflow_package

The greenfield workflow authoring engine.

Input: a task for which no existing workflow is good enough.
Output: a new workflow package with:

topology,
routes,
prompts,
parameters,
artifacts,
tests,
docs,
composition contracts.

What it does end-to-end:

defines the job-to-be-done,
chooses end-to-end workflow vs reusable building block,
defines inputs/outputs,
defines step and role topology,
defines control flow and artifact contracts,
generates the package.

Why it matters: this is the true workflow-builder, which your brief explicitly treats as foundational infrastructure.

5. workflow_package_to_composable_building_blocks

The decomposition engine.

Input: an existing end-to-end workflow package.
Output: extracted reusable sub-workflows and building blocks with clear interfaces.

What it does end-to-end:

identifies repeated substructures,
extracts them into reusable workflow packages or sub-workflows,
defines invocation contracts,
rewrites the parent workflow to build on them.

Why it matters: this is how the ecosystem compounds instead of becoming a pile of monolith workflows.

6. workflow_to_eval_suite

The evaluation authoring engine.

Input: a workflow package or adapted workflow plan.
Output: a full evaluation suite:

benchmark tasks,
adversarial cases,
edge cases,
expected artifacts,
pass/fail criteria,
rubric and scoring logic.

What it does end-to-end:

derives what “good” means for the workflow,
creates representative and hard cases,
defines observable evidence,
creates reproducible evaluation inputs.

Why it matters: workflow authoring without eval authoring is incomplete.

7. workflow_run_history_to_failure_modes

The diagnostic evaluator.

Input: workflow run logs, artifacts, outputs, failures, human escalations, and downstream outcomes.
Output: failure-mode map, root-cause hypotheses, recurring weak points, and severity-ranked improvement opportunities.

What it does end-to-end:

clusters failures and near-misses,
distinguishes prompt problems from topology problems from artifact-contract problems,
identifies where humans had to intervene,
turns scattered experience into structured fault knowledge.

Why it matters: this is the missing self-healing layer.

8. workflow_and_eval_to_refined_workflow_package

The closed-loop refinement engine.

Input: a workflow package plus its eval results and observed failure modes.
Output: a revised workflow package with justified changes and measured improvement.

What it does end-to-end:

proposes multiple credible revisions,
chooses between prompt changes, route changes, artifact changes, step decomposition, or composition changes,
re-runs evals,
emits improved package plus before/after deltas.

Why it matters: this is the core recursive improvement loop.

9. workflow_portfolio_to_operating_system

The ecosystem architect.

Input: the full set of workflows, building blocks, evals, usage frequency, failure rates, and business demand.
Output: a recommended workflow portfolio architecture:

which workflows should exist,
which should be merged,
which should be decomposed,
which should be retired,
which missing workflows should be created next.

What it does end-to-end:

identifies duplication,
identifies coverage gaps,
identifies fragile single-use workflows,
optimizes the overall workflow graph.

Why it matters: this prevents workflow sprawl and keeps the system legible.

10. company_operation_to_recursive_improvement_cycle

The top-level autonomous company learner.

Input: company work history across product, engineering, support, incidents, releases, customer requests, and workflow telemetry.
Output: prioritized improvements to:

workflow portfolio,
workflow packages,
eval suites,
composition strategy,
escalation policies,
organization-level operating patterns.

What it does end-to-end:

asks where humans still bottleneck,
asks where workflows are missing or weak,
decides whether to reuse, adapt, author, decompose, or retire workflows,
triggers the next improvement cycle.

Why it matters: this is the system that makes the whole company recursively better over time.
#####

These are examples only. Let the problem determine the right shape. Some additions should be full workflows; others should be reusable building blocks that strengthen the workflow ecosystem.

Part 2: Improve the framework as needed

Based on the chosen addition and the broader workflow set, identify and implement the most valuable framework improvement for supporting high-value workflows and reusable building blocks cleanly and reliably.

Prefer framework improvements that:
- make valuable workflows or building blocks easier to express
- reduce hidden control flow or special-case logic
- improve resumability, inspectability, durability, and recovery
- generalize across multiple workflow types
- improve authoring quality while keeping workflow semantics visible
- keep prompt-template responsibilities distinct from runtime responsibilities
- keep runtime-injected control contracts narrow and mechanical
- support ambitious long-horizon but role/artifact/acceptance-coherent work items
- address repetitive workflow patterns without hiding important workflow meaning
- explicitly consider reserved routes, work-item effects, session scope, artifact locality, and other broadly repetitive workflow patterns

Do not add framework machinery unless it clearly improves the expression, execution, reuse, or reliability of valuable workflows or reusable building blocks.

When evaluating framework improvements:
- consider exactly 3 core framework improvements
- compare them briefly with explicit trade-offs
- for meaningful design decisions, consider 3 of the best candidate solutions and choose the best fit
- prefer explicit workflow contracts, reusable mechanisms, prompt-template doctrine, artifact-first design, and durable runtime behavior over hidden sequencing in `src/autoloop/main.py`

Acceptance gates:
- The chosen addition must solve a problem that is plausibly important in software development, product development, business analysis, delivery, architecture, operations, or a closely related software-business function.
- The chosen addition must have a clear purpose and a clear useful outcome.
- The chosen addition must be substantial enough to justify its existence in Autoloop.
- The chosen addition must plausibly benefit from multi-turn orchestration, agentic execution, reuse, composition, or a combination of these.
- If the chosen addition is an end-to-end workflow, it should have a clear terminal outcome.
- If the chosen addition is a reusable building block, it should have clear reusable value and composability.
- The implementation must improve the repository in a reusable, inspectable, and practical way.
- The workflow design must make deterministic-vs-provider-owned responsibilities explicit.
- The workflow design must not rely on provider guesses for role, artifact, route, or output handling.
- The cycle must explicitly identify broadly repetitive workflow patterns and analyze the best way to address them.
- Do not accept an addition whose primary purpose is only to pressure the framework.

Output requirements:
1. A short decision record describing the candidate additions considered and the chosen one.
2. The new workflow or reusable building block definition, invocation path, prompts/templates, declared artifacts/interfaces, and explicit route grammar.
3. Explicit step prompt templates for each major role or step, including artifact read/write handling and route instructions.
4. The narrow runtime-injected control contract for those steps.
5. Evidence in docs or tests showing the addition can be exercised.
6. A short decision record describing the framework improvement candidates considered and the chosen one.
7. A short design-decision record for each meaningful design choice, including alternatives considered and the selected approach.
8. A short decision record for the chosen implementation with at least 3 implementation candidates and the selected design.
9. Updated recursive memory files under `.autoloop_recursive/` so future cycles inherit the latest roadmap and gap history.

Outcome standard:
- The cycle must leave the repository more capable of supporting valuable workflows for real software work.
- Prefer work that strengthens both immediate usefulness and long-term workflow ecosystem quality.

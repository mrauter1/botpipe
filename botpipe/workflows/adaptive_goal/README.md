# Adaptive Goal

`adaptive_goal` is a goal-constrained, path-free orchestration workflow built on
Botpipe's existing public workflow API.

It deliberately keeps a tiny static Botpipe control graph while allowing the
semantic work graph to emerge at runtime:

```text
initialize
   ↓
orchestrate
   ↓
validate action
   ↓
dispatch child workflow
   ↓
reconcile state / invalidate stale verification
   ├──────────────→ orchestrate
   ├──────────────→ terminal unsatisfied
   ├──────────────→ blocked
   └──────────────→ final global audit
                         ├── reopen → orchestrate
                         ├── blocked
                         └── complete
```

## Verification philosophy

Most important real-world criteria are not accurately reducible to deterministic
scores. A visual-design LLM that invents `87/100` has not made the judgment more
objective. The useful information is *why* the design works or fails, against a
clear rubric and grounded evidence.

Adaptive Goal therefore supports three criterion modes:

- `judgment`: a designated verifier evaluates a descriptive rubric and emits an
  evidence-backed qualitative verdict.
- `deterministic`: the runtime evaluates objective observations against hard rules
  such as `broken_links == 0`.
- `hybrid`: qualitative judgment plus genuine hard checks.

Optional ratings such as 1-5 are diagnostic summaries only. They are never the
basis for subjective PASS/FAIL.

## Design invariants

1. **The mission is immutable.** `mission.json` is snapshotted from typed run
   input. The orchestrator never gets authority to change criteria, rubrics,
   hard checks, verifier assignments, or constraints.

2. **The designated verifier owns subjective judgment.** For a judgment criterion
   it must explicitly assess every authored rubric item, provide reasoning and
   evidence, and return `satisfied`, `not_satisfied`, or
   `insufficient_evidence`. The parent runtime does not manufacture a verdict by
   thresholding an LLM-produced score.

3. **The runtime still governs verification authority.** It verifies the correct
   designated verifier was used, complete rubric coverage, internal coherence,
   hard checks for deterministic/hybrid criteria, and evidence freshness. A
   verifier cannot silently skip a mandatory rubric item or contradict a `gate`
   finding with an overall `satisfied` verdict.

4. **PASS is freshness-bound.** A passing receipt records the exact filesystem
   patterns observed by the verifier and a SHA-256 subject fingerprint. Any later
   action that changes that subject automatically marks the criterion `STALE`.
   External/time-sensitive criteria can additionally use a TTL.

5. **Actions and criteria are separate.** Criteria describe what must be true.
   Capabilities describe work that may help make criteria true. The orchestrator
   chooses one next action from current state instead of executing a precomputed
   SOP.

6. **Verifier reasoning is operational state.** The blackboard carries the
   judgment summary, detailed reasoning, rubric findings, evidence and recommended
   corrective actions so the orchestrator can choose work that resolves concrete
   deficiencies rather than trying to increase a generic score.

7. **Unknown work does not generate trusted Botpipe Python on the fly.**
   `kind="ad_hoc"` dispatches the pre-authored `ad_hoc_executor` workflow. That
   workflow is sandboxed, workspace-write, no-network, and independently
   verified.

8. **External side effects require preapproval.** Any capability marked
   `external_reversible`, `external_irreversible`, or
   `preapproval_required=true` is rejected unless its id is listed in
   `preapproved_capabilities`.

9. **Final local PASS receipts are not enough.** A fresh global audit verifies the
   original objective/constraints using the substantive verifier reasoning and
   evidence. It may reopen existing criteria, but may not invent new mandatory
   criteria or weaken the mission.

10. **Child workflow output is durable.** Capabilities publish a standard protocol
    artifact in their own Botpipe workflow folder. The parent reads and validates
    that file after `ctx.invoke_workflow(...)`.

## Judgment verifier protocol

A qualitative verifier writes `verification_result.json` such as:

```json
{
  "schema": "botpipe.adaptive-goal.verifier-result/v2",
  "status": "evaluated",
  "verifier_id": "verify.visual",
  "summary": "Visual audit completed.",
  "judgments": {
    "visual_quality": {
      "verdict": "not_satisfied",
      "summary": "Strong structure, but the page still lacks professional visual hierarchy.",
      "reasoning": "The hero does not establish the business proposition quickly enough and the service cards compete equally for attention. Typography and spacing are otherwise coherent.",
      "findings": [
        {
          "rubric_item_id": "hierarchy",
          "status": "not_satisfied",
          "reasoning": "Hero headline, supporting copy and CTA have nearly equal visual weight.",
          "evidence": ["qa/desktop.png", "qa/mobile.png"]
        },
        {
          "rubric_item_id": "industry_appropriateness",
          "status": "satisfied",
          "reasoning": "The restrained visual language is appropriate for an industrial supplier.",
          "evidence": ["qa/desktop.png"]
        }
      ],
      "rating": 3,
      "confidence": "high",
      "recommended_actions": [
        "Strengthen hero headline/CTA hierarchy",
        "Reduce visual competition in the first service row"
      ]
    }
  },
  "observations": {},
  "evidence": ["qa/desktop.png", "qa/mobile.png"],
  "observed_paths": {
    "visual_quality": ["site/**"]
  }
}
```

The `rating` may help compare iterations, but it does not decide PASS. The
semantic verdict and its supporting reasoning do.

## Deterministic and hybrid criteria

Use hard rules only for properties that are actually mechanical:

```python
MissionCriterion(
    id="link_integrity",
    description="The generated site has no broken internal links.",
    verifier="verify.links",
    verification_mode="deterministic",
    deterministic_rules=[
        DeterministicRule(metric="broken_links", operator="eq", value=0)
    ],
    observed_paths=["site/**"],
)
```

A hybrid criterion can require both a qualitative judgment and an objective hard
condition.

## Minimal judgment mission

```python
from botpipe.workflows.adaptive_goal import (
    AdaptiveGoalInput,
    AdaptiveGoalWorkflow,
    CapabilityRegistry,
    CapabilitySpec,
    MissionCriterion,
    MissionSpec,
    RubricItem,
)

mission = MissionSpec(
    id="website-redesign",
    objective="Produce a demonstrably superior private redesign.",
    criteria=[
        MissionCriterion(
            id="visual_quality",
            description="The rendered redesign is visually strong and appropriate for the business.",
            verifier="verify.visual",
            verification_mode="judgment",
            rubric=[
                RubricItem(
                    id="hierarchy",
                    description="The page has clear visual hierarchy and immediate comprehension.",
                    importance="gate",
                ),
                RubricItem(
                    id="typography",
                    description="Typography is coherent, legible, and professionally composed.",
                ),
                RubricItem(
                    id="industry_appropriateness",
                    description="The visual language is credible for the actual business and audience.",
                    importance="gate",
                ),
                RubricItem(
                    id="mobile",
                    description="The design remains coherent and persuasive on mobile.",
                    importance="gate",
                ),
            ],
            observed_paths=["site/**"],
        )
    ],
)
```

## Action selection

The orchestrator receives the immutable mission, capability metadata, blackboard,
status report, and verification ledger. A failed criterion is represented by
specific findings rather than merely a score. An action can therefore say:

```json
{
  "kind": "capability",
  "capability_id": "design",
  "objective": "Repair the hero hierarchy and first service row.",
  "target_criteria": ["visual_quality"],
  "rationale": "The visual verifier found that the hero headline, copy and CTA have equal weight and the first service row competes with the hero.",
  "expected_evidence": ["new desktop/mobile renders resolving both findings"]
}
```

## Why `ad_hoc_executor` has no network

An arbitrary LLM-authored objective plus unrestricted network is not an
enforceable no-side-effect boundary. Networked research should therefore be a
pre-authored registered capability with an explicit policy and result contract.
The generic ad-hoc escape hatch is intentionally limited to the local workspace.

## Capability promotion

Dynamic actions are not dynamically generated Botpipe workflows. If repeated
ad-hoc traces reveal a stable useful pattern, an offline optimizer may generate a
**candidate** capability workflow. It should be compiled, tested, evaluated
against historical cases, independently reviewed, and only then added to the
trusted capability registry.

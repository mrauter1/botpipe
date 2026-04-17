from __future__ import annotations

from pathlib import Path


DOCS_ROOT = Path(__file__).resolve().parents[1] / "docs"
ADR_ROOT = DOCS_ROOT / "adr"

EXPECTED_DOCS = {
    "architecture.md",
    "authoring.md",
    "compatibility.md",
    "parity-matrix.md",
    "risk-register.md",
}

EXPECTED_ADRS = {
    "001-package-module-layout.md",
    "002-workflow-compilation-model.md",
    "003-topology-routing-representation.md",
    "004-artifact-registry-and-resolution.md",
    "005-checkpoint-persistence-model.md",
    "006-session-binding-model.md",
    "007-provider-protocol-design.md",
    "008-compatibility-strategy.md",
    "009-handler-dispatch-and-signature-adaptation.md",
    "010-resume-answer-injection.md",
    "011-validation-architecture.md",
    "012-event-and-logging-model.md",
    "013-cli-and-runtime-harness-layout.md",
    "014-testing-strategy.md",
}

MANDATED_EVALUATION_FIELDS = (
    "correctness:",
    "compatibility:",
    "simplicity:",
    "extensibility:",
    "observability:",
    "testability:",
    "failure handling:",
    "performance:",
    "migration risk:",
)


def _read_doc(name: str) -> str:
    return (DOCS_ROOT / name).read_text(encoding="utf-8")


def test_required_architecture_docs_exist() -> None:
    actual = {path.name for path in DOCS_ROOT.glob("*.md")}
    assert EXPECTED_DOCS <= actual


def test_required_adrs_exist_and_are_exactly_the_expected_set() -> None:
    actual = {path.name for path in ADR_ROOT.glob("*.md")}
    assert actual == EXPECTED_ADRS


def test_each_adr_has_exactly_three_candidates_and_mandated_fields() -> None:
    for path in sorted(ADR_ROOT.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        candidate_count = sum(1 for line in text.splitlines() if line.startswith("## Candidate "))
        assert candidate_count == 3, f"{path.name} must contain exactly three candidate sections"
        for field in MANDATED_EVALUATION_FIELDS:
            assert field in text, f"{path.name} is missing mandated field {field!r}"


def test_architecture_and_authoring_docs_freeze_public_surface() -> None:
    architecture = _read_doc("architecture.md")
    authoring = _read_doc("authoring.md")
    required_exports = (
        "Workflow",
        "Context",
        "Session",
        "SessionLifecycle",
        "Artifact",
        "Prompt",
        "PairStep",
        "LLMStep",
        "SystemStep",
        "SUCCESS",
        "PAUSE",
        "FAIL",
        "GLOBAL",
        "Event",
        "Outcome",
        "Verdict",
        "Checkpoint",
        "ResolvedArtifacts",
    )
    for symbol in required_exports:
        assert symbol in architecture or symbol in authoring


def test_docs_capture_concrete_legacy_behaviors_and_compatibility_risks() -> None:
    architecture = _read_doc("architecture.md")
    parity = _read_doc("parity-matrix.md")
    compatibility = _read_doc("compatibility.md")
    corpus = "\n".join((architecture, parity, compatibility))
    required_markers = (
        "autoloop_v1.py",
        "Ralph_loop.py",
        ".autoloop/tasks/{task_id}/runs/{run_id}",
        "plan.phase_plan",
        "implement.impl_notes",
        "on_verdict",
        "SessionLifecycle.ON_START",
        "phase-scoped sessions",
        "thread_id",
        "missing annotation imports",
        "config discovery",
    )
    for marker in required_markers:
        assert marker in corpus


def test_docs_capture_phase_local_and_resume_risk_inventory() -> None:
    parity = _read_doc("parity-matrix.md")
    risks = _read_doc("risk-register.md")
    assert "Clarification note stored in the active phase session only" in parity
    assert "Resume semantics" in parity
    assert "Session scope collisions across phases" in risks
    assert "Loader cannot import `Ralph_loop.py` as-is" in risks


def test_docs_match_shipped_runtime_module_layout_and_boundaries() -> None:
    architecture = _read_doc("architecture.md")
    compatibility = _read_doc("compatibility.md")
    parity = _read_doc("parity-matrix.md")
    authoring = _read_doc("authoring.md")
    corpus = "\n".join((architecture, compatibility, parity, authoring))

    for marker in ("events.py", "prompts.py", "filesystem.py", "provider factory", "checkpoint.json"):
        assert marker in corpus

    for stale_marker in ("runtime.logging", "`runtime.providers`", "logging.py"):
        assert stale_marker not in corpus

from __future__ import annotations

from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
DOCS_ROOT = PACKAGE_ROOT / "docs"
ADR_ROOT = DOCS_ROOT / "adr"

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


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_required_docs_exist() -> None:
    expected = {
        PACKAGE_ROOT / "README.md",
        PACKAGE_ROOT / "MIGRATION.md",
        PACKAGE_ROOT / "ARCHITECTURE_DECISIONS.md",
        DOCS_ROOT / "architecture.md",
        DOCS_ROOT / "authoring.md",
        DOCS_ROOT / "compatibility.md",
        DOCS_ROOT / "parity-matrix.md",
        DOCS_ROOT / "risk-register.md",
    }
    assert all(path.exists() for path in expected)


def test_architecture_decisions_uses_three_candidates_per_decision() -> None:
    text = _read(PACKAGE_ROOT / "ARCHITECTURE_DECISIONS.md")
    sections = [section for section in text.split("\n## ") if section.strip()]
    assert len(sections) >= 10
    for section in sections[1:]:
        if "### Candidate " not in section:
            continue
        assert section.count("### Candidate ") == 3
        assert "Decision:" in section
        assert "Book choice:" in section
        assert "Why the others lost:" in section


def test_adr_archive_is_final_form_and_points_back_to_the_authoritative_record() -> None:
    actual = {path.name for path in ADR_ROOT.glob("*.md")}
    assert actual == EXPECTED_ADRS

    for path in sorted(ADR_ROOT.glob("*.md")):
        text = _read(path)
        assert "Status: Final" in text
        assert "Authoritative record:" in text
        assert "Final decision:" in text
        assert "Rejected shape:" in text


def test_adr_archive_does_not_reintroduce_removed_authoring_surface() -> None:
    corpus = "\n".join(_read(path) for path in sorted(ADR_ROOT.glob("*.md")))
    for forbidden in (
        "workflow.compat",
        "SessionLifecycle",
        "Verdict",
        "on_verdict",
        "compatibility shim",
        "normalize once",
    ):
        assert forbidden not in corpus


def test_adr_archive_remains_summary_only_instead_of_duplicating_candidate_matrices() -> None:
    for path in sorted(ADR_ROOT.glob("*.md")):
        text = _read(path)
        for forbidden in (
            "## Candidate ",
            "### Candidate ",
            "## Selected Option",
            "## Why The Selected Option",
            "Book choice:",
        ):
            assert forbidden not in text


def test_docs_freeze_the_strict_public_surface() -> None:
    public_surface_docs = "\n".join(
        (
            _read(PACKAGE_ROOT / "README.md"),
            _read(DOCS_ROOT / "architecture.md"),
        )
    )
    for symbol in (
        "Workflow",
        "Context",
        "Session",
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
        "Checkpoint",
        "ResolvedArtifacts",
    ):
        assert symbol in public_surface_docs
    authoring = _read(DOCS_ROOT / "authoring.md")
    assert "from workflow.primitives import Event, Outcome, Checkpoint, ResolvedArtifacts" in authoring
    for forbidden in (
        "from workflow.primitives import Verdict",
        "SessionLifecycle,",
        "`workflow.compat`",
    ):
        assert forbidden not in public_surface_docs


def test_docs_capture_migration_boundary_and_parity_contract() -> None:
    corpus = "\n".join(
        (
            _read(PACKAGE_ROOT / "MIGRATION.md"),
            _read(PACKAGE_ROOT / "README.md"),
            _read(DOCS_ROOT / "architecture.md"),
            _read(DOCS_ROOT / "compatibility.md"),
            _read(DOCS_ROOT / "parity-matrix.md"),
            _read(DOCS_ROOT / "risk-register.md"),
        )
    )
    required_markers = (
        ".autoloop/tasks/{task_id}/runs/{run_id}",
        "run_autoloop_v1",
        "sessions/plan.json",
        "sessions/phases/{phase}.json",
        "raw_phase_log.md",
        "decisions.txt",
        "question",
        "blocked",
        "failed",
        "thread_id",
        "workflow-owned",
        "workflow.observers",
        "autoloop_v3.workflows.autoloop_v1_conventions",
        "autoloop_v3.workflows.autoloop_v1_parity",
        "compatibility layer",
        "workspace-hook",
        "loader-injected authoring symbols",
        "max_steps",
        "intent_mode",
    )
    for marker in required_markers:
        assert marker in corpus

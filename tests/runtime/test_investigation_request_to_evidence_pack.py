from __future__ import annotations

import importlib
import json
import shutil
import sys
from pathlib import Path

import pytest

from autoloop_v3.core.compiler import compile_workflow
from autoloop_v3.core.context import Context
from autoloop_v3.core.providers.fake import ScriptedLLMProvider
from autoloop_v3.core.stores import InMemorySessionStore
from autoloop_v3.runtime.config import GitTrackingRuntimeConfig, RuntimeConfig
from autoloop_v3.runtime.loader import (
    WorkflowParameterError,
    coerce_workflow_parameter_mapping,
    discover_workflow_packages,
    resolve_workflow_reference,
)
from autoloop_v3.runtime.runner import RunnerOptions, run_workflow_package
from core.primitives import Outcome


REPO_ROOT = Path(__file__).resolve().parents[2]
COMMON_PROMPT_CONTRACT_MARKERS = (
    "## Step Contract",
    "## Artifact Contract",
    "| Artifact | Direction | Notes |",
    "## Output Requirements",
    "## Routes",
    "## Forbidden",
)
LEGACY_PROMPT_SCAFFOLDING_MARKERS = ("Read these artifacts", "Write these artifacts")


def _assert_compact_prompt_contract(
    prompt_name: str,
    text: str,
    required_markers: tuple[str, ...],
) -> None:
    for marker in COMMON_PROMPT_CONTRACT_MARKERS:
        assert marker in text, f"{prompt_name} is missing required contract marker: {marker}"

    for marker in required_markers:
        assert marker in text, f"{prompt_name} is missing required contract marker: {marker}"

    for marker in LEGACY_PROMPT_SCAFFOLDING_MARKERS:
        assert marker not in text, f"{prompt_name} still contains legacy scaffolding marker: {marker}"


def _clear_workflow_modules() -> None:
    for name in list(sys.modules):
        if name == "workflows" or name.startswith("workflows."):
            sys.modules.pop(name, None)


@pytest.fixture(autouse=True)
def _isolate_workflow_modules():
    _clear_workflow_modules()
    yield
    _clear_workflow_modules()


def test_repo_workflows_namespace_discovers_investigation_evidence_pack_package() -> None:
    discovered = {package.workflow_name: package for package in discover_workflow_packages(REPO_ROOT)}

    assert "investigation_request_to_evidence_pack" in discovered
    package = discovered["investigation_request_to_evidence_pack"]
    assert package.package_name == "investigation_request_to_evidence_pack"
    assert "investigation-evidence-pack" in package.aliases
    assert package.manifest_path == (
        REPO_ROOT / "workflows" / "investigation_request_to_evidence_pack" / "workflow.toml"
    )


def test_investigation_evidence_pack_package_compiles_with_explicit_control_contracts(monkeypatch) -> None:
    monkeypatch.syspath_prepend(str(REPO_ROOT))
    importlib.invalidate_caches()
    _clear_workflow_modules()

    workflow_pkg = importlib.import_module("workflows.investigation_request_to_evidence_pack")
    resolved = resolve_workflow_reference(REPO_ROOT, workflow_pkg.InvestigationRequestToEvidencePack)
    compiled = compile_workflow(resolved.workflow_cls)

    assert resolved.parameters_cls is not None
    assert compiled.entry_step_name == "bootstrap"
    assert tuple(compiled.steps) == (
        "bootstrap",
        "frame_investigation",
        "assemble_evidence_pack",
        "publish_evidence_pack",
    )

    frame_step = compiled.steps["frame_investigation"]
    assert frame_step.available_routes == (
        "investigation_framed",
        "needs_rework",
        "needs_replan",
        "question",
        "blocked",
        "failed",
    )
    assert list(compiled.routes["frame_investigation"]["investigation_framed"].required_writes) == [
        "frame_investigation.investigation_scope_brief",
        "frame_investigation.investigation_objectives",
        "frame_investigation.evidence_intake_register",
    ]
    assert compiled.routes["frame_investigation"]["investigation_framed"].handoff == (
        "Locks the investigation framing so evidence assembly can proceed against a fixed boundary."
    )
    assert frame_step.expected_output_schema is not None

    evidence_step = compiled.steps["assemble_evidence_pack"]
    assert evidence_step.available_routes == (
        "evidence_pack_ready",
        "needs_rework",
        "needs_replan",
        "question",
        "blocked",
        "failed",
    )
    assert list(compiled.routes["assemble_evidence_pack"]["evidence_pack_ready"].required_writes) == [
        "assemble_evidence_pack.evidence_source_inventory",
        "assemble_evidence_pack.evidence_coverage_matrix",
        "assemble_evidence_pack.evidence_findings",
        "assemble_evidence_pack.evidence_gap_register",
        "assemble_evidence_pack.evidence_pack",
        "assemble_evidence_pack.evidence_pack_summary",
    ]
    assert evidence_step.expected_output_schema is not None


def test_investigation_evidence_pack_package_docs_capture_decision_records() -> None:
    text = (REPO_ROOT / "docs" / "workflows" / "investigation_request_to_evidence_pack.md").read_text(
        encoding="utf-8"
    )

    for required in (
        "Candidate additions considered",
        "Framework improvement candidates considered",
        "Meaningful design decisions",
        "Implementation candidates considered",
        "Route grammar",
        "Runtime-injected control contract",
        "tests/runtime/test_investigation_request_to_evidence_pack.py",
    ):
        assert required in text


def test_investigation_evidence_pack_prompt_readme_uses_shared_contract_sections() -> None:
    text = (
        REPO_ROOT / "workflows" / "investigation_request_to_evidence_pack" / "prompts" / "README.md"
    ).read_text(encoding="utf-8")

    for required in (
        "## Shared README Boundary",
        "## Keep In Each Prompt",
        "## Step Surface",
        "## Route Surface",
        "## Verifier Payloads",
        "Reserved routes:",
        "`question`",
        "`blocked`",
        "`failed`",
        "Application routes:",
        "`investigation_framed`",
        "`evidence_pack_ready`",
        "`needs_rework`",
        "`needs_replan`",
        "`frame_producer.md` / `frame_verifier.md`",
        "InvestigationEvidencePackPayload",
        "compact human-readable step contract",
        "Provider raw output is runtime telemetry",
    ):
        assert required in text


def test_investigation_evidence_pack_prompt_inventory_matches_expected_contract_surface() -> None:
    prompt_dir = REPO_ROOT / "workflows" / "investigation_request_to_evidence_pack" / "prompts"

    assert sorted(path.name for path in prompt_dir.glob("*.md")) == [
        "README.md",
        "evidence_producer.md",
        "evidence_verifier.md",
        "frame_producer.md",
        "frame_verifier.md",
    ]


@pytest.mark.parametrize(
    ("prompt_name", "required_markers"),
    (
        (
            "frame_producer.md",
            (
                "`investigation_scope_brief`",
                "`investigation_objectives`",
                "`evidence_intake_register`",
                "`investigation_framed`",
                "`source_constraints`",
            ),
        ),
        (
            "frame_verifier.md",
            (
                "Required outcome structure",
                "`investigation_framed`",
                "`needs_rework`",
                "`needs_replan`",
                "`authoritative_artifacts`",
            ),
        ),
        (
            "evidence_producer.md",
            (
                "`evidence_source_inventory`",
                "`evidence_coverage_matrix`",
                "`evidence_pack_summary`",
                "`evidence_pack_ready`",
                "`ready_for_downstream_assessment`",
            ),
        ),
        (
            "evidence_verifier.md",
            (
                "Required outcome structure",
                "`evidence_pack_ready`",
                "`needs_rework`",
                "`needs_replan`",
                "`source_count`",
            ),
        ),
    ),
)
def test_investigation_evidence_pack_prompts_keep_step_local_contracts_explicit(
    prompt_name: str,
    required_markers: tuple[str, ...],
) -> None:
    text = (
        REPO_ROOT / "workflows" / "investigation_request_to_evidence_pack" / "prompts" / prompt_name
    ).read_text(encoding="utf-8")

    _assert_compact_prompt_contract(prompt_name, text, required_markers)


def test_investigation_evidence_pack_package_rejects_blank_investigation_title(tmp_path: Path) -> None:
    _install_repo_investigation_package(tmp_path)
    parameters_cls = resolve_workflow_reference(tmp_path, "investigation_request_to_evidence_pack").parameters_cls

    with pytest.raises(WorkflowParameterError, match="investigation_title"):
        coerce_workflow_parameter_mapping(parameters_cls, {"investigation_title": "   "})


def test_investigation_evidence_pack_package_normalizes_repeatable_inputs(tmp_path: Path) -> None:
    _install_repo_investigation_package(tmp_path)
    parameters_cls = resolve_workflow_reference(tmp_path, "investigation_request_to_evidence_pack").parameters_cls

    normalized = coerce_workflow_parameter_mapping(
        parameters_cls,
        {
            "investigation_title": " Admin impersonation privilege escalation ",
            "investigation_kind": " security_remediation ",
            "sponsor_role": " Security Engineering ",
            "evidence_paths": [
                " pentest/findings/admin-impersonation.md ",
                "",
                "pentest/findings/admin-impersonation.md",
                "src/auth/impersonation.py",
            ],
            "source_constraints": [
                " use repo artifacts only ",
                "",
                "use repo artifacts only",
                "Treat missing audit evidence as a gap.",
            ],
        },
    )

    assert normalized == {
        "evidence_paths": [
            "pentest/findings/admin-impersonation.md",
            "src/auth/impersonation.py",
        ],
        "investigation_kind": "security_remediation",
        "investigation_title": "Admin impersonation privilege escalation",
        "source_constraints": [
            "use repo artifacts only",
            "Treat missing audit evidence as a gap.",
        ],
        "sponsor_role": "Security Engineering",
    }


def test_investigation_evidence_pack_bootstrap_reads_typed_ctx_params(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.syspath_prepend(str(REPO_ROOT))
    importlib.invalidate_caches()
    _clear_workflow_modules()

    workflow_pkg = importlib.import_module("workflows.investigation_request_to_evidence_pack")
    parameters_cls = resolve_workflow_reference(REPO_ROOT, "investigation_request_to_evidence_pack").parameters_cls
    assert parameters_cls is not None
    typed_params = parameters_cls.model_validate(
        coerce_workflow_parameter_mapping(
            parameters_cls,
            {
                "investigation_title": " Admin impersonation privilege escalation ",
                "investigation_kind": " security_remediation ",
                "sponsor_role": " Security Engineering ",
                "evidence_paths": [
                    " pentest/findings/admin-impersonation.md ",
                    "",
                    "pentest/findings/admin-impersonation.md",
                    "src/auth/impersonation.py",
                ],
                "source_constraints": [
                    " use repo artifacts only ",
                    "",
                    "use repo artifacts only",
                    "Treat missing audit evidence as a gap.",
                ],
            },
        )
    )

    task_folder = tmp_path / ".autoloop" / "tasks" / "typed-bootstrap-task"
    workflow_folder = task_folder / "wf_investigation_request_to_evidence_pack"
    run_folder = workflow_folder / "runs" / "run-1"
    run_folder.mkdir(parents=True, exist_ok=True)
    (run_folder / "request.md").write_text("Typed bootstrap request.\n", encoding="utf-8")

    ctx = Context(
        task_id="typed-bootstrap-task",
        run_id="run-1",
        workflow_name="investigation_request_to_evidence_pack",
        task_folder=task_folder,
        workflow_folder=workflow_folder,
        run_folder=run_folder,
        package_folder=REPO_ROOT / "workflows" / "investigation_request_to_evidence_pack",
        state=workflow_pkg.InvestigationRequestToEvidencePack.State(),
        session_store=InMemorySessionStore(),
        params=typed_params,
        workflow_params={
            "investigation_title": "wrong investigation",
            "investigation_kind": "general",
            "sponsor_role": "Wrong Sponsor",
            "evidence_paths": ["wrong/path.md"],
            "source_constraints": ["wrong constraint"],
        },
    )

    next_state, event = workflow_pkg.InvestigationRequestToEvidencePack.on_bootstrap(
        workflow_pkg.InvestigationRequestToEvidencePack.State(),
        ctx,
    )

    assert event.tag == "inputs_prepared"
    assert next_state.investigation_title == "Admin impersonation privilege escalation"
    assert next_state.investigation_kind == "security_remediation"
    assert next_state.sponsor_role == "Security Engineering"
    assert next_state.evidence_paths == [
        "pentest/findings/admin-impersonation.md",
        "src/auth/impersonation.py",
    ]
    assert next_state.source_constraints == [
        "use repo artifacts only",
        "Treat missing audit evidence as a gap.",
    ]
    assert ctx.get_session("frame_session") is not None
    assert ctx.get_session("evidence_session") is not None

    invocation_contract = json.loads((workflow_folder / "invocation_contract.json").read_text(encoding="utf-8"))
    assert invocation_contract["investigation_title"] == "Admin impersonation privilege escalation"
    assert invocation_contract["investigation_kind"] == "security_remediation"
    assert invocation_contract["sponsor_role"] == "Security Engineering"
    assert invocation_contract["evidence_paths"] == next_state.evidence_paths
    assert invocation_contract["source_constraints"] == next_state.source_constraints


def test_investigation_evidence_pack_package_runs_and_emits_terminal_receipt(tmp_path: Path) -> None:
    _install_repo_investigation_package(tmp_path)

    result = run_workflow_package(
        "investigation_request_to_evidence_pack",
        provider=_security_investigation_provider(),
        options=RunnerOptions(
            root=tmp_path,
            task_id="investigation-evidence-pack-task",
            message="Assemble the evidence pack for the admin impersonation privilege-escalation finding.",
            workflow_params={
                "investigation_title": "Admin impersonation privilege escalation",
                "investigation_kind": "security_remediation",
                "sponsor_role": "security engineering",
                "evidence_paths": [
                    "pentest/findings/admin-impersonation.md",
                    "src/auth/impersonation.py",
                ],
                "source_constraints": [
                    "Use repository artifacts and named pentest evidence only.",
                    "Treat missing production audit proof as a gap, not a pass.",
                ],
            },
            runtime_config=RuntimeConfig(git_tracking=GitTrackingRuntimeConfig(enabled=False)),
        ),
    )

    workflow_dir = (
        tmp_path / ".autoloop" / "tasks" / "investigation-evidence-pack-task" / "wf_investigation_request_to_evidence_pack"
    )
    run_dir = next((workflow_dir / "runs").iterdir())
    invocation_contract = json.loads((workflow_dir / "invocation_contract.json").read_text(encoding="utf-8"))
    evidence_pack_summary = json.loads((workflow_dir / "evidence_pack_summary.json").read_text(encoding="utf-8"))
    evidence_pack_receipt = json.loads((workflow_dir / "evidence_pack_receipt.json").read_text(encoding="utf-8"))

    assert result.terminal == "FINISH"
    assert (workflow_dir / "investigation_scope_brief.md").exists()
    assert (workflow_dir / "investigation_objectives.md").exists()
    assert (workflow_dir / "evidence_source_inventory.md").exists()
    assert (workflow_dir / "evidence_coverage_matrix.md").exists()
    assert (workflow_dir / "evidence_findings.md").exists()
    assert (workflow_dir / "evidence_gap_register.md").exists()
    assert (workflow_dir / "evidence_pack.md").exists()
    assert (workflow_dir / "evidence_pack_summary.json").exists()
    assert (workflow_dir / "evidence_pack_receipt.json").exists()
    assert invocation_contract == {
        "evidence_paths": [
            "pentest/findings/admin-impersonation.md",
            "src/auth/impersonation.py",
        ],
        "investigation_kind": "security_remediation",
        "investigation_title": "Admin impersonation privilege escalation",
        "message": "Assemble the evidence pack for the admin impersonation privilege-escalation finding.\n",
        "request_file": str(run_dir / "request.md"),
        "run_id": run_dir.name,
        "source_constraints": [
            "Use repository artifacts and named pentest evidence only.",
            "Treat missing production audit proof as a gap, not a pass.",
        ],
        "sponsor_role": "security engineering",
        "task_id": "investigation-evidence-pack-task",
        "workflow_name": "investigation_request_to_evidence_pack",
    }
    assert evidence_pack_summary == {
        "authoritative_artifacts": [
            "evidence_source_inventory",
            "evidence_coverage_matrix",
            "evidence_findings",
            "evidence_gap_register",
            "evidence_pack",
            "evidence_pack_summary",
        ],
        "finding_count": 3,
        "investigation_kind": "security_remediation",
        "key_findings": [
            "Admin impersonation checks diverge between the API handler and the role-enforcement helper.",
            "Audit logging does not capture delegated admin scope for impersonation sessions.",
        ],
        "ready_for_downstream_assessment": True,
        "source_count": 3,
        "unresolved_gap_count": 1,
    }
    assert evidence_pack_receipt == {
        "authoritative_artifacts": [
            "evidence_source_inventory",
            "evidence_coverage_matrix",
            "evidence_findings",
            "evidence_gap_register",
            "evidence_pack",
            "evidence_pack_summary",
        ],
        "evidence_coverage_matrix": str(workflow_dir / "evidence_coverage_matrix.md"),
        "evidence_findings": str(workflow_dir / "evidence_findings.md"),
        "evidence_gap_register": str(workflow_dir / "evidence_gap_register.md"),
        "evidence_intake_register": str(workflow_dir / "evidence_intake_register.md"),
        "evidence_pack": str(workflow_dir / "evidence_pack.md"),
        "evidence_pack_summary": str(workflow_dir / "evidence_pack_summary.json"),
        "evidence_paths": [
            "pentest/findings/admin-impersonation.md",
            "src/auth/impersonation.py",
        ],
        "evidence_source_inventory": str(workflow_dir / "evidence_source_inventory.md"),
        "finding_count": 3,
        "investigation_kind": "security_remediation",
        "investigation_objectives": str(workflow_dir / "investigation_objectives.md"),
        "investigation_scope_brief": str(workflow_dir / "investigation_scope_brief.md"),
        "investigation_title": "Admin impersonation privilege escalation",
        "key_findings": [
            "Admin impersonation checks diverge between the API handler and the role-enforcement helper.",
            "Audit logging does not capture delegated admin scope for impersonation sessions.",
        ],
        "published": True,
        "ready_for_downstream_assessment": True,
        "source_constraints": [
            "Use repository artifacts and named pentest evidence only.",
            "Treat missing production audit proof as a gap, not a pass.",
        ],
        "source_count": 3,
        "sponsor_role": "security engineering",
        "unresolved_gap_count": 1,
        "workflow_name": "investigation_request_to_evidence_pack",
    }


def test_investigation_evidence_pack_package_can_be_composed_through_helper_seam(tmp_path: Path) -> None:
    _install_repo_investigation_package(tmp_path)
    _write_parent_investigation_composer_workflow_package(tmp_path)

    result = run_workflow_package(
        "parent_investigation_composer",
        provider=_release_readiness_provider(),
        options=RunnerOptions(
            root=tmp_path,
            task_id="investigation-composition-task",
            message="Prepare the parent release evidence packet.",
            runtime_config=RuntimeConfig(git_tracking=GitTrackingRuntimeConfig(enabled=False)),
        ),
    )

    task_dir = tmp_path / ".autoloop" / "tasks" / "investigation-composition-task"
    parent_workflow_dir = task_dir / "wf_parent_investigation_composer"
    parent_run_dir = next((parent_workflow_dir / "runs").iterdir())
    child_workflow_dir = task_dir / "wf_investigation_request_to_evidence_pack"
    child_run_dir = next((child_workflow_dir / "runs").iterdir())
    adopted_scope = parent_workflow_dir / "adopted" / "release_scope_brief.md"
    adopted_pack = parent_workflow_dir / "adopted" / "release_evidence_pack.md"
    adopted_summary = parent_workflow_dir / "adopted" / "release_evidence_pack_summary.json"
    parent_payload = json.loads((parent_run_dir / "summary.json").read_text(encoding="utf-8"))
    child_records = [
        json.loads(line)
        for line in (parent_run_dir / "children.jsonl").read_text(encoding="utf-8").splitlines()
        if line
    ]

    assert result.terminal == "FINISH"
    assert parent_payload["child_workflow"] == "investigation_request_to_evidence_pack"
    assert parent_payload["child_status"] == "success"
    assert parent_payload["child_last_event"] == "evidence_pack_published"
    assert parent_payload["child_artifacts"]["evidence_pack_receipt"] == str(
        child_workflow_dir / "evidence_pack_receipt.json"
    )
    assert parent_payload["adopted_artifacts"] == {
        "evidence_pack": str(adopted_pack),
        "evidence_pack_summary": str(adopted_summary),
        "investigation_scope_brief": str(adopted_scope),
    }
    assert adopted_scope.read_text(encoding="utf-8") == (child_workflow_dir / "investigation_scope_brief.md").read_text(
        encoding="utf-8"
    )
    assert adopted_pack.read_text(encoding="utf-8") == (child_workflow_dir / "evidence_pack.md").read_text(
        encoding="utf-8"
    )
    assert json.loads(adopted_summary.read_text(encoding="utf-8")) == json.loads(
        (child_workflow_dir / "evidence_pack_summary.json").read_text(encoding="utf-8")
    )
    assert (task_dir / "request.md").read_text(encoding="utf-8") == "Prepare the parent release evidence packet.\n"
    assert (child_run_dir / "request.md").read_text(encoding="utf-8") == "Assemble the release readiness evidence pack.\n"
    assert child_records[0]["workflow_name"] == "investigation_request_to_evidence_pack"
    assert child_records[0]["status"] == "success"
    assert child_records[0]["output_artifacts"]["evidence_pack"] == str(child_workflow_dir / "evidence_pack.md")
    assert child_records[0]["output_artifacts"]["evidence_pack_summary"] == str(
        child_workflow_dir / "evidence_pack_summary.json"
    )
    assert child_records[0]["output_artifacts"]["evidence_pack_receipt"] == str(
        child_workflow_dir / "evidence_pack_receipt.json"
    )


@pytest.mark.parametrize(
    ("summary_payload", "match"),
    (
        (
            {
                "authoritative_artifacts": ["evidence_pack"],
                "finding_count": 1,
                "investigation_kind": "security_remediation",
                "key_findings": ["One finding"],
                "source_count": 1,
                "unresolved_gap_count": 0,
            },
            "ready_for_downstream_assessment",
        ),
        (
            {
                "authoritative_artifacts": ["evidence_pack"],
                "finding_count": 1,
                "investigation_kind": "release_readiness",
                "key_findings": ["One finding"],
                "ready_for_downstream_assessment": True,
                "source_count": 1,
                "unresolved_gap_count": 0,
            },
            "investigation_kind must match workflow state",
        ),
    ),
)
def test_investigation_evidence_pack_publish_rejects_invalid_machine_readable_summary(
    tmp_path: Path,
    summary_payload: dict[str, object],
    match: str,
) -> None:
    _install_repo_investigation_package(tmp_path)
    monkeypatch_root = tmp_path
    importlib.invalidate_caches()
    _clear_workflow_modules()
    sys.path.insert(0, str(monkeypatch_root))
    try:
        workflow_pkg = importlib.import_module("workflows.investigation_request_to_evidence_pack")
    finally:
        sys.path.remove(str(monkeypatch_root))
        _clear_workflow_modules()

    workflow_folder = tmp_path / "task" / "wf_investigation_request_to_evidence_pack"
    workflow_folder.mkdir(parents=True, exist_ok=True)
    (workflow_folder / "investigation_scope_brief.md").write_text("# Scope Brief\n", encoding="utf-8")
    (workflow_folder / "investigation_objectives.md").write_text("# Objectives\n", encoding="utf-8")
    (workflow_folder / "evidence_intake_register.md").write_text("# Intake Register\n", encoding="utf-8")
    (workflow_folder / "evidence_source_inventory.md").write_text("# Source Inventory\n", encoding="utf-8")
    (workflow_folder / "evidence_coverage_matrix.md").write_text("# Coverage Matrix\n", encoding="utf-8")
    (workflow_folder / "evidence_findings.md").write_text("# Findings\n", encoding="utf-8")
    (workflow_folder / "evidence_gap_register.md").write_text("# Gap Register\n", encoding="utf-8")
    (workflow_folder / "evidence_pack.md").write_text("# Evidence Pack\n", encoding="utf-8")
    (workflow_folder / "evidence_pack_summary.json").write_text(
        json.dumps(summary_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    state = workflow_pkg.InvestigationRequestToEvidencePack.State(
        investigation_title="Admin impersonation privilege escalation",
        investigation_kind="security_remediation",
        sponsor_role="security engineering",
        evidence_paths=["pentest/findings/admin-impersonation.md"],
        source_constraints=["Use repository artifacts only."],
    )
    ctx = Context(
        task_id="investigation-evidence-pack-task",
        run_id="run-1",
        workflow_name="investigation_request_to_evidence_pack",
        task_folder=tmp_path / "task",
        workflow_folder=workflow_folder,
        run_folder=tmp_path / "task" / "wf_investigation_request_to_evidence_pack" / "runs" / "run-1",
        package_folder=REPO_ROOT / "workflows" / "investigation_request_to_evidence_pack",
        state=state,
        session_store=InMemorySessionStore(),
    )

    with pytest.raises(ValueError, match=match):
        workflow_pkg.InvestigationRequestToEvidencePack.on_publish_evidence_pack(state, ctx)

    assert not (workflow_folder / "evidence_pack_receipt.json").exists()


def _security_investigation_provider() -> ScriptedLLMProvider:
    return ScriptedLLMProvider(
        producer_turns=[
            lambda request: (
                request.artifacts.investigation_scope_brief.write_text(
                    "\n".join(
                        (
                            "# Investigation Scope Brief",
                            "",
                            "Trigger: pentest evidence of privilege escalation in admin impersonation.",
                            "Sponsor: security engineering.",
                            "Scope: admin impersonation request path, role checks, and audit logging coverage.",
                            "Out of scope: unrelated reporting and billing behavior.",
                            "",
                        )
                    )
                    + "\n",
                ),
                request.artifacts.investigation_objectives.write_text(
                    "\n".join(
                        (
                            "# Investigation Objectives",
                            "",
                            "- Bound the affected impersonation surface.",
                            "- Capture what proof supports the finding and what proof is still missing.",
                            "- Produce an evidence pack a remediation workflow can consume directly.",
                            "",
                        )
                    )
                    + "\n",
                ),
                request.artifacts.evidence_intake_register.write_text(
                    "\n".join(
                        (
                            "# Evidence Intake Register",
                            "",
                            "- pentest/findings/admin-impersonation.md",
                            "- src/auth/impersonation.py",
                            "- docs/admin-impersonation-audit.md",
                            "- Missing: production audit excerpt for affected delegated-admin sessions.",
                            "",
                        )
                    )
                    + "\n",
                ),
                "framed investigation\n",
            )[3],
            lambda request: (
                request.artifacts.evidence_source_inventory.write_text(
                    "\n".join(
                        (
                            "# Evidence Source Inventory",
                            "",
                            "- `pentest/findings/admin-impersonation.md`: confirms a delegated-admin impersonation bypass path.",
                            "- `src/auth/impersonation.py`: shows API-side scope checks diverge from the shared role helper.",
                            "- `docs/admin-impersonation-audit.md`: documents missing delegated-admin audit fields.",
                            "",
                        )
                    )
                    + "\n",
                ),
                request.artifacts.evidence_coverage_matrix.write_text(
                    "\n".join(
                        (
                            "# Evidence Coverage Matrix",
                            "",
                            "| Objective | Supporting evidence | Gaps |",
                            "| --- | --- | --- |",
                            "| Bound affected surface | pentest finding, impersonation code path | production audit excerpt for affected sessions |",
                            "| Confirm auditability | audit doc and code review | no production sample with delegated-admin trace |",
                            "",
                        )
                    )
                    + "\n",
                ),
                request.artifacts.evidence_findings.write_text(
                    "\n".join(
                        (
                            "# Evidence Findings",
                            "",
                            "1. Admin impersonation checks diverge between the API handler and the shared role-enforcement helper.",
                            "2. The pentest finding and the code path point to the same delegated-admin bypass surface.",
                            "3. Audit logging does not capture delegated-admin scope for impersonation sessions.",
                            "",
                        )
                    )
                    + "\n",
                ),
                request.artifacts.evidence_gap_register.write_text(
                    "\n".join(
                        (
                            "# Evidence Gap Register",
                            "",
                            "- Missing production audit excerpt for affected delegated-admin sessions; this matters because blast radius cannot be fully bounded from repo evidence alone.",
                            "",
                        )
                    )
                    + "\n",
                ),
                request.artifacts.evidence_pack.write_text(
                    "\n".join(
                        (
                            "# Evidence Pack",
                            "",
                            "This evidence pack covers the admin impersonation privilege-escalation finding.",
                            "",
                            "## Sources reviewed",
                            "- pentest finding",
                            "- impersonation code path",
                            "- audit documentation",
                            "",
                            "## Key findings",
                            "- API and helper checks diverge.",
                            "- Audit logging is incomplete for delegated-admin impersonation.",
                            "",
                            "## Unresolved gaps",
                            "- Missing production audit excerpt for affected delegated-admin sessions.",
                            "",
                        )
                    )
                    + "\n",
                ),
                request.artifacts.evidence_pack_summary.write_text(
                    json.dumps(
                        {
                            "authoritative_artifacts": [
                                "evidence_source_inventory",
                                "evidence_coverage_matrix",
                                "evidence_findings",
                                "evidence_gap_register",
                                "evidence_pack",
                                "evidence_pack_summary",
                            ],
                            "finding_count": 3,
                            "investigation_kind": "security_remediation",
                            "key_findings": [
                                "Admin impersonation checks diverge between the API handler and the role-enforcement helper.",
                                "Audit logging does not capture delegated admin scope for impersonation sessions.",
                            ],
                            "ready_for_downstream_assessment": True,
                            "source_count": 3,
                            "unresolved_gap_count": 1,
                        },
                        indent=2,
                        sort_keys=True,
                    )
                    + "\n",
                ),
                "assembled evidence pack\n",
            )[6],
        ],
        verifier_turns=[
            Outcome(
                raw_output="framed investigation\n",
                tag="investigation_framed",
                payload={
                    "summary": "The security investigation boundary and evidence intake plan are explicit.",
                    "authoritative_artifacts": [
                        "investigation_scope_brief",
                        "investigation_objectives",
                        "evidence_intake_register",
                    ],
                    "evidence_focus": [
                        "impersonation authorization path",
                        "delegated-admin audit coverage",
                    ],
                },
            ),
            Outcome(
                raw_output="evidence pack ready\n",
                tag="evidence_pack_ready",
                payload={
                    "summary": "The evidence pack is source-traced, gap-aware, and ready for downstream security assessment.",
                    "evidence_artifacts": [
                        "evidence_source_inventory",
                        "evidence_coverage_matrix",
                        "evidence_findings",
                        "evidence_gap_register",
                        "evidence_pack",
                        "evidence_pack_summary",
                    ],
                    "source_count": 3,
                    "unresolved_gaps": [
                        "Missing production audit excerpt for affected delegated-admin sessions.",
                    ],
                    "key_findings": [
                        "Admin impersonation checks diverge between the API handler and the role-enforcement helper.",
                        "Audit logging does not capture delegated admin scope for impersonation sessions.",
                    ],
                    "ready_for_downstream_assessment": True,
                },
            ),
        ],
    )


def _release_readiness_provider() -> ScriptedLLMProvider:
    return ScriptedLLMProvider(
        producer_turns=[
            lambda request: (
                request.artifacts.investigation_scope_brief.write_text(
                    "\n".join(
                        (
                            "# Investigation Scope Brief",
                            "",
                            "Trigger: release-readiness review for 2026.04.",
                            "Sponsor: release management.",
                            "Scope: release notes, regression evidence, rollback notes, and operational readiness.",
                            "Out of scope: architecture redesign beyond the queued release work.",
                            "",
                        )
                    )
                    + "\n",
                ),
                request.artifacts.investigation_objectives.write_text(
                    "\n".join(
                        (
                            "# Investigation Objectives",
                            "",
                            "- Capture the release evidence another assessment workflow can consume directly.",
                            "- Make test and dashboard gaps explicit instead of hiding them in prose.",
                            "- Publish a machine-readable summary parent workflows can adopt.",
                            "",
                        )
                    )
                    + "\n",
                ),
                request.artifacts.evidence_intake_register.write_text(
                    "\n".join(
                        (
                            "# Evidence Intake Register",
                            "",
                            "- docs/releases/2026.04.md",
                            "- reports/test-summary-2026.04.md",
                            "- runbooks/prod-release-checklist.md",
                            "- Missing: dashboard screenshot proving the audit-log path in production.",
                            "",
                        )
                    )
                    + "\n",
                ),
                "framed investigation\n",
            )[3],
            lambda request: (
                request.artifacts.evidence_source_inventory.write_text(
                    "\n".join(
                        (
                            "# Evidence Source Inventory",
                            "",
                            "- `docs/releases/2026.04.md`: release contents and owner summary.",
                            "- `reports/test-summary-2026.04.md`: regression and smoke-test evidence.",
                            "- `runbooks/prod-release-checklist.md`: operational readiness and rollback checklist.",
                            "",
                        )
                    )
                    + "\n",
                ),
                request.artifacts.evidence_coverage_matrix.write_text(
                    "\n".join(
                        (
                            "# Evidence Coverage Matrix",
                            "",
                            "| Objective | Supporting evidence | Gaps |",
                            "| --- | --- | --- |",
                            "| Confirm release scope | release notes | none |",
                            "| Confirm test proof | regression report | audit-log dashboard proof missing |",
                            "| Confirm operational readiness | runbook checklist | dashboard screenshot not attached |",
                            "",
                        )
                    )
                    + "\n",
                ),
                request.artifacts.evidence_findings.write_text(
                    "\n".join(
                        (
                            "# Evidence Findings",
                            "",
                            "1. Release 2026.04 includes billing, SSO, and audit-log stabilization work.",
                            "2. Regression evidence covers billing and auth paths.",
                            "3. Operational readiness is documented, but dashboard proof for the audit-log path is still missing.",
                            "",
                        )
                    )
                    + "\n",
                ),
                request.artifacts.evidence_gap_register.write_text(
                    "\n".join(
                        (
                            "# Evidence Gap Register",
                            "",
                            "- Missing dashboard screenshot or equivalent production proof for the audit-log path; this matters because the release assessment cannot fully verify observability coverage without it.",
                            "",
                        )
                    )
                    + "\n",
                ),
                request.artifacts.evidence_pack.write_text(
                    "\n".join(
                        (
                            "# Evidence Pack",
                            "",
                            "This pack summarizes the release-readiness evidence for 2026.04.",
                            "",
                            "## Sources reviewed",
                            "- release notes",
                            "- test summary",
                            "- production release checklist",
                            "",
                            "## Key findings",
                            "- Release scope is explicit.",
                            "- Regression evidence exists for billing and auth.",
                            "- Dashboard proof for audit-log readiness is still missing.",
                            "",
                        )
                    )
                    + "\n",
                ),
                request.artifacts.evidence_pack_summary.write_text(
                    json.dumps(
                        {
                            "authoritative_artifacts": [
                                "evidence_source_inventory",
                                "evidence_coverage_matrix",
                                "evidence_findings",
                                "evidence_gap_register",
                                "evidence_pack",
                                "evidence_pack_summary",
                            ],
                            "finding_count": 3,
                            "investigation_kind": "release_readiness",
                            "key_findings": [
                                "Release scope is explicit and tied to named artifacts.",
                                "Dashboard proof for audit-log readiness is still missing.",
                            ],
                            "ready_for_downstream_assessment": True,
                            "source_count": 3,
                            "unresolved_gap_count": 1,
                        },
                        indent=2,
                        sort_keys=True,
                    )
                    + "\n",
                ),
                "assembled evidence pack\n",
            )[6],
        ],
        verifier_turns=[
            Outcome(
                raw_output="framed investigation\n",
                tag="investigation_framed",
                payload={
                    "summary": "The release-readiness evidence request has an explicit boundary and intake plan.",
                    "authoritative_artifacts": [
                        "investigation_scope_brief",
                        "investigation_objectives",
                        "evidence_intake_register",
                    ],
                    "evidence_focus": [
                        "release scope confirmation",
                        "dashboard proof gap",
                    ],
                },
            ),
            Outcome(
                raw_output="evidence pack ready\n",
                tag="evidence_pack_ready",
                payload={
                    "summary": "The release evidence pack is explicit about proof and gaps and is ready for downstream assessment.",
                    "evidence_artifacts": [
                        "evidence_source_inventory",
                        "evidence_coverage_matrix",
                        "evidence_findings",
                        "evidence_gap_register",
                        "evidence_pack",
                        "evidence_pack_summary",
                    ],
                    "source_count": 3,
                    "unresolved_gaps": [
                        "Missing dashboard screenshot or equivalent production proof for the audit-log path.",
                    ],
                    "key_findings": [
                        "Release scope is explicit and tied to named artifacts.",
                        "Dashboard proof for audit-log readiness is still missing.",
                    ],
                    "ready_for_downstream_assessment": True,
                },
            ),
        ],
    )


def _install_repo_investigation_package(root: Path) -> None:
    workflows_root = root / "workflows"
    workflows_root.mkdir(parents=True, exist_ok=True)
    (workflows_root / "__init__.py").write_text("__all__ = []\n", encoding="utf-8")
    _clear_workflow_modules()
    importlib.invalidate_caches()

    shutil.copytree(
        REPO_ROOT / "workflows" / "investigation_request_to_evidence_pack",
        workflows_root / "investigation_request_to_evidence_pack",
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    shutil.copytree(
        REPO_ROOT / "docs",
        root / "docs",
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    (root / "Workflow_Instructions.md").write_text(
        (REPO_ROOT / "Workflow_Instructions.md").read_text(encoding="utf-8"),
        encoding="utf-8",
    )


def _write_parent_investigation_composer_workflow_package(root: Path) -> None:
    package_dir = root / "workflows" / "parent_investigation_composer"
    package_dir.mkdir(parents=True, exist_ok=True)
    (root / "workflows" / "__init__.py").write_text("__all__ = []\n", encoding="utf-8")
    (package_dir / "__init__.py").write_text(
        "from .workflow import ParentInvestigationComposer\n__all__ = ['ParentInvestigationComposer']\n",
        encoding="utf-8",
    )
    (package_dir / "workflow.toml").write_text('name = "parent_investigation_composer"\n', encoding="utf-8")
    (package_dir / "prompts").mkdir(exist_ok=True)
    (package_dir / "assets").mkdir(exist_ok=True)
    (package_dir / "workflow.py").write_text(
        """
from __future__ import annotations

import json

from pydantic import BaseModel

from autoloop_v3.stdlib import adopt_child_artifacts, run_child_workflow
from autoloop import Workflow, python_step


class ParentInvestigationComposer(Workflow):
    name = "parent_investigation_composer"

    class State(BaseModel):
        finished: bool = False

    @python_step(name="launch")
    def launch(ctx):
        child = run_child_workflow(
            ctx,
            "investigation_request_to_evidence_pack",
            message="Assemble the release readiness evidence pack.",
            parameters={
                "investigation_title": "Release 2026.04 readiness",
                "investigation_kind": "release_readiness",
                "sponsor_role": "release management",
                "evidence_paths": [
                    "docs/releases/2026.04.md",
                    "reports/test-summary-2026.04.md",
                ],
                "source_constraints": [
                    "Use repo artifacts and named runbooks only.",
                    "Treat missing dashboard proof as a gap, not a pass.",
                ],
            },
        )
        adopted = adopt_child_artifacts(
            ctx,
            child,
            mapping={
                "investigation_scope_brief": "adopted/release_scope_brief.md",
                "evidence_pack": "adopted/release_evidence_pack.md",
                "evidence_pack_summary": "adopted/release_evidence_pack_summary.json",
            },
        )
        payload = {
            "child_workflow": child.workflow_name,
            "child_run_id": child.run_id,
            "child_status": child.status,
            "child_last_event": None if child.last_event is None else child.last_event.tag,
            "child_output_metadata": child.output_metadata,
            "child_artifacts": {name: str(path) for name, path in child.output_artifacts.items()},
            "adopted_artifacts": {name: str(path) for name, path in adopted.items()},
            "child_workflow_folder": str(child.workflow_folder),
        }
        (ctx.run_folder / "summary.json").write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\\n",
            encoding="utf-8",
        )
        return None
""".strip()
        + "\n",
        encoding="utf-8",
    )

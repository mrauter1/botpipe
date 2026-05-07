from __future__ import annotations

from tests.unit._stdlib_and_extensions_shared import (
    _build_child_result,
    _build_lifecycle_context,
    _capture_child_invocation,
)
from tests.unit._stdlib_and_extensions_shared import *

def test_composition_helpers_delegate_to_ctx_invoke_workflow_and_adopt_child_artifacts(tmp_path: Path) -> None:
    source_artifact = tmp_path / "child-run" / "evidence.md"
    source_artifact.parent.mkdir(parents=True, exist_ok=True)
    source_artifact.write_text("child evidence\n", encoding="utf-8")
    child_result = _build_child_result(tmp_path, {"evidence_pack": source_artifact})
    captured: dict[str, object] = {}
    ctx = _build_lifecycle_context(
        tmp_path,
        workflow_invoker=lambda workflow, *, message, parameters: _capture_child_invocation(
            captured,
            child_result,
            workflow=workflow,
            message=message,
            parameters=parameters,
        ),
    )

    result = run_child_workflow(
        ctx,
        "investigation_request_to_evidence_pack",
        message="Assemble the evidence pack",
        parameters={"mode": "strict"},
    )
    validated = require_child_workflow_result(
        result,
        status="success",
        last_event="evidence_pack_ready",
        required_artifacts=("evidence_pack",),
    )
    adopted = adopt_child_artifacts(ctx, result, mapping={"evidence_pack": "adopted/evidence-pack.md"})

    assert result is child_result
    assert validated is child_result
    assert captured == {
        "message": "Assemble the evidence pack",
        "parameters": {"mode": "strict"},
        "workflow": "investigation_request_to_evidence_pack",
    }
    assert adopted == {"evidence_pack": ctx.workflow_folder / "adopted" / "evidence-pack.md"}
    assert adopted["evidence_pack"].read_text(encoding="utf-8") == "child evidence\n"
def test_composition_helpers_reject_missing_child_artifacts_and_parent_path_escape(tmp_path: Path) -> None:
    source_artifact = tmp_path / "child-run" / "evidence.md"
    source_artifact.parent.mkdir(parents=True, exist_ok=True)
    source_artifact.write_text("child evidence\n", encoding="utf-8")
    child_result = _build_child_result(tmp_path, {"evidence_pack": source_artifact})
    ctx = _build_lifecycle_context(tmp_path)

    with pytest.raises(KeyError, match="did not produce artifact 'missing'"):
        adopt_child_artifacts(ctx, child_result, mapping={"missing": "adopted/missing.md"})
    with pytest.raises(ValueError, match="ctx.workflow_folder"):
        adopt_child_artifacts(ctx, child_result, mapping={"evidence_pack": "../escape.md"})
def test_require_child_workflow_result_rejects_wrong_status(tmp_path: Path) -> None:
    source_artifact = tmp_path / "child-run" / "evidence.md"
    source_artifact.parent.mkdir(parents=True, exist_ok=True)
    source_artifact.write_text("child evidence\n", encoding="utf-8")
    child_result = _build_child_result(tmp_path, {"evidence_pack": source_artifact})
    child_result = ChildWorkflowResult(
        workflow_name=child_result.workflow_name,
        run_id=child_result.run_id,
        terminal=child_result.terminal,
        status="awaiting_input",
        last_event=Event("question", question="Need more evidence?"),
        output_metadata=child_result.output_metadata,
        output_artifacts=child_result.output_artifacts,
        task_folder=child_result.task_folder,
        workflow_folder=child_result.workflow_folder,
        run_folder=child_result.run_folder,
        package_folder=child_result.package_folder,
        request_file=child_result.request_file,
        run_meta_file=child_result.run_meta_file,
        events_file=child_result.events_file,
        checkpoint_file=child_result.checkpoint_file,
        sessions_dir=child_result.sessions_dir,
        trace_file=child_result.trace_file,
        raw_dir=child_result.raw_dir,
        parent_file=child_result.parent_file,
    )

    with pytest.raises(ValueError, match="returned status 'awaiting_input', expected 'success'"):
        require_child_workflow_result(child_result)
def test_require_child_workflow_result_rejects_wrong_terminal_route(tmp_path: Path) -> None:
    source_artifact = tmp_path / "child-run" / "evidence.md"
    source_artifact.parent.mkdir(parents=True, exist_ok=True)
    source_artifact.write_text("child evidence\n", encoding="utf-8")
    child_result = _build_child_result(tmp_path, {"evidence_pack": source_artifact})

    with pytest.raises(ValueError, match="ended with route 'evidence_pack_ready', expected 'evidence_pack_published'"):
        require_child_workflow_result(child_result, last_event="evidence_pack_published")
def test_require_child_workflow_result_rejects_missing_required_artifacts(tmp_path: Path) -> None:
    source_artifact = tmp_path / "child-run" / "evidence.md"
    source_artifact.parent.mkdir(parents=True, exist_ok=True)
    source_artifact.write_text("child evidence\n", encoding="utf-8")
    child_result = _build_child_result(tmp_path, {"evidence_pack": source_artifact})

    with pytest.raises(KeyError, match="did not produce required artifact 'evidence_gap_register'"):
        require_child_workflow_result(child_result, required_artifacts=("evidence_gap_register",))
def test_composition_helpers_reject_declared_child_artifacts_with_missing_source_files(tmp_path: Path) -> None:
    missing_source = tmp_path / "child-run" / "missing-evidence.md"
    child_result = _build_child_result(tmp_path, {"evidence_pack": missing_source})
    ctx = _build_lifecycle_context(tmp_path)

    with pytest.raises(FileNotFoundError, match="missing at"):
        adopt_child_artifacts(ctx, child_result, mapping={"evidence_pack": "adopted/evidence-pack.md"})
    with pytest.raises(FileNotFoundError, match="reported required artifact 'evidence_pack'"):
        require_child_workflow_result(child_result, required_artifacts=("evidence_pack",))

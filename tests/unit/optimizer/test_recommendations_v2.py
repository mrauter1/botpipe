from __future__ import annotations
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from botpipe_optimizer.recommendations import build_empty_candidate_set,finalize_candidate_review_payload,finalize_candidate_set_payload,publish_recommendation,validate_candidate_review,validate_candidate_set
from labs.workflows.workflow_run_traces_to_optimization_candidates.params import Params
from labs.workflows.workflow_run_traces_to_optimization_candidates.workflow import _invocation_id

def _evidence():
    return SimpleNamespace(snapshot_id="evidence-1",baseline_surface_manifest_id="surface-1",shortlist=[],issues=[],recommendation_basis="current_verified",citable_observation_ids=lambda: frozenset({"obs-1"}))
def _draft(kind="producer_prompt",citation="obs-1"):
    payload={"prompt_paths":["wf/prompt.md"],"replacement_strategy":"Tighten evidence rules."}
    return {"schema":"botpipe.workflow_optimization.candidate_set/v2","selected_workflow":"wf","evidence_snapshot_id":"evidence-1","baseline_surface_manifest_id":"surface-1","candidates":[{"kind":kind,"title":"Tighten prompt","targets":["wf/prompt.md"],"cited_observation_ids":[citation],"proposed_change":"Require source references.","expected_effect":"Reduce observed rejection recurrence.","risks":["May reject terse valid output."],"validation_plan":{"description":"Replay frozen cases.","checks":["compile","evaluate"],"falsification":"No reliability improvement."},"payload":payload}],"next_action":"implement_candidate","no_candidate_reason":None}

def test_t13_rejects_forged_citation_duplicate_ids_and_disabled_kind():
    forged=finalize_candidate_set_payload(_draft(citation="invented"))
    with pytest.raises(ValueError,match="unknown"):
        validate_candidate_set(forged,evidence_snapshot=_evidence(),max_candidates=3,allowed_kinds={"producer_prompt"},expected_selected_workflow="wf")
    raw=_draft(); raw["candidates"].append(dict(raw["candidates"][0])); duplicate=finalize_candidate_set_payload(raw)
    with pytest.raises(ValueError,match="unique"):
        validate_candidate_set(duplicate,evidence_snapshot=_evidence(),max_candidates=3,allowed_kinds={"producer_prompt"},expected_selected_workflow="wf")
    with pytest.raises(ValueError,match="disabled"):
        validate_candidate_set(finalize_candidate_set_payload(_draft()),evidence_snapshot=_evidence(),max_candidates=3,allowed_kinds={"workflow"},expected_selected_workflow="wf")

def test_t14_empty_candidate_set_is_valid_and_requires_no_review():
    cs=build_empty_candidate_set(selected_workflow="wf",evidence_snapshot_id="evidence-1",baseline_surface_manifest_id="surface-1",next_action="collect_evidence",reason="No eligible failures.")
    validate_candidate_set(cs,evidence_snapshot=_evidence(),max_candidates=3,allowed_kinds=set(),expected_selected_workflow="wf")
    assert cs.candidates==[]

def test_t15_total_cap_and_review_anchor_are_hard_failures():
    raw=_draft(); second=json.loads(json.dumps(raw["candidates"][0])); second["title"]="Second"; raw["candidates"].append(second); cs=finalize_candidate_set_payload(raw)
    with pytest.raises(ValueError,match="max_candidates"):
        validate_candidate_set(cs,evidence_snapshot=_evidence(),max_candidates=1,allowed_kinds={"producer_prompt"},expected_selected_workflow="wf")
    review=finalize_candidate_review_payload({"schema":"botpipe.workflow_optimization.candidate_review/v2","candidate_set_id":cs.candidate_set_id,"evidence_snapshot_id":cs.evidence_snapshot_id,"baseline_surface_manifest_id":cs.baseline_surface_manifest_id,"accepted":True,"reviewed_candidate_ids":list(reversed([c.candidate_id for c in cs.candidates])),"findings":[]})
    with pytest.raises(ValueError,match="exactly"):
        validate_candidate_review(review,candidate_set=cs)

def test_failed_publication_replaces_stale_success_with_incomplete(tmp_path:Path):
    (tmp_path/"optimization_publication_receipt.json").write_text('{"status":"accepted"}')
    cs=finalize_candidate_set_payload(_draft())
    with pytest.raises(ValueError,match="accepted independent review"):
        publish_recommendation(output_dir=tmp_path,evidence_snapshot_path=tmp_path/"e.json",baseline_surface_manifest_path=tmp_path/"b.json",evidence_snapshot=_evidence(),candidate_set=cs,review=None,max_output_bytes=1024)
    assert json.loads((tmp_path/"optimization_publication_receipt.json").read_text())["status"]=="incomplete"

def test_t20_parameter_aliases_warn_and_conflicts_fail():
    with pytest.warns(FutureWarning,match="max_candidates_per_pass"):
        params=Params(selected_workflow="wf",task_title="Review",max_candidates_per_pass=2)
    assert params.max_candidates==2
    with pytest.raises(ValueError,match="conflicts"):
        Params(selected_workflow="wf",task_title="Review",max_candidates=3,max_candidates_per_pass=2)
    with pytest.warns(FutureWarning,match="optimization_depth"):
        standard=Params(selected_workflow="wf",task_title="Review",optimization_depth="standard")
    assert (standard.max_provider_turns,standard.max_analysis_seconds)==(12,3600)

def test_resume_invocation_identity_changes_with_effective_params(tmp_path:Path):
    request=tmp_path/"request.md"; request.write_text("diagnose")
    original=Params(selected_workflow="wf",task_title="Review",max_candidates=3)
    changed=Params(selected_workflow="wf",task_title="Review",max_candidates=2)
    assert _invocation_id(original,request,"wf") != _invocation_id(changed,request,"wf")

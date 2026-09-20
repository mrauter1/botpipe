from __future__ import annotations
import hashlib, json
from pathlib import Path
import pytest
from botpipe_optimizer.evidence import capture_evidence_snapshot, read_evidence_snapshot, write_evidence_snapshot

WF, SURFACE, TOPOLOGY = "demo", "surface-current", "topology-current"


def _step(seq, step, route, **extra):
    return {"event_type": "step_finished", "sequence": seq, "step_execution_id": f"exec-{seq}", "step_name": step, "step_kind": "pair", "scope": "root", "item_id": "one", "final_route": route, "outcome": {"tag": route}, **extra}


def _run(root: Path, run_id: str, records, *, surface=SURFACE, topology=TOPOLOGY, graph=True):
    d = root / ".botpipe" / "tasks" / f"task-{run_id}" / f"wf_{WF}" / "runs" / run_id
    d.mkdir(parents=True)
    provenance = {"workflow_identity": WF}
    if surface: provenance["workflow_surface_manifest_id"] = surface
    if topology: provenance["topology_id"] = topology
    (d / "run.json").write_text(json.dumps({"task_id": f"task-{run_id}", "run_id": run_id, "workflow_name": WF, "status": "failed", "updated_at": f"2026-01-{int(run_id[-1])+1:02d}T00:00:00+00:00", "provenance": provenance}))
    (d / "trace.jsonl").write_text("\n".join(json.dumps(r) for r in records) + "\n")
    if graph:
        (d / "static_step_graph.json").write_text(json.dumps({"steps": [{"name": "review", "kind": "pair"}], "transitions": {"steps": {"review": {"needs_rework": "review", "done": "FINISH"}}}}))
    return d


def _capture(root, runs, **kw):
    return capture_evidence_snapshot(root, WF, runs, root / "snapshot", current_workflow_identity=WF, current_surface_manifest_id=SURFACE, current_topology_id=TOPOLOGY, **kw)


@pytest.mark.parametrize("mutation,expected", [("tamper", "byte_count_mismatch"), ("digest", "digest_mismatch"), ("absolute", "invalid_path"), ("traversal", "invalid_path")])
def test_t05_raw_bytes_must_verify_before_content_citation(tmp_path, mutation, expected):
    data = b"evidence"; ref = {"path": "raw/out.txt", "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
    if mutation == "digest": ref["sha256"] = "0" * 64
    if mutation == "absolute": ref["path"] = "/tmp/out.txt"
    if mutation == "traversal": ref["path"] = "../out.txt"
    run = _run(tmp_path, "run1", [_step(1, "review", "needs_rework", raw_output_refs={"producer": ref})])
    (run / "raw").mkdir(); (run / "raw" / "out.txt").write_bytes(data + (b"x" if mutation == "tamper" else b""))
    snap = _capture(tmp_path, [run], explicit_run_refs=True)
    assert snap.observations[0].raw_references[0].verification == expected
    assert snap.observations[0].observation_id not in snap.citable_observation_ids(require_raw_content=True)
    assert snap.shortlist[0].step_id == "review"


def test_t06_missing_git_and_topology_are_visible_optional_gaps(tmp_path):
    run = _run(tmp_path, "run1", [_step(1, "review", "needs_rework")], graph=False)
    snap = _capture(tmp_path, [run], explicit_run_refs=True)
    assert len(snap.runs) == len(snap.observations) == 1
    assert {i.dimension for i in snap.issues} >= {"git", "topology"}


def test_t07_independent_rejections_are_recurrence_not_cycles(tmp_path):
    snap = _capture(tmp_path, [_run(tmp_path, f"run{i}", [_step(1, "review", "needs_rework")]) for i in (1, 2)], explicit_run_refs=True)
    m = snap.step_metrics[0]
    assert (m.rework_run_count, m.rework_rejection_count, m.rework_cycle_count) == (2, 2, 0)


def test_t08_interleaved_lanes_only_form_matched_cycles(tmp_path):
    records = [_step(1, "review", "needs_rework", step_execution_id="a1", visit=1, item_id="a"), _step(2, "review", "needs_rework", step_execution_id="b1", visit=1, item_id="b"), _step(3, "review", "needs_rework", step_execution_id="a2", visit=2, item_id="a"), _step(4, "review", "done", step_execution_id="b2", visit=2, item_id="b"), _step(5, "review", "done", step_execution_id="a3", visit=3, item_id="a")]
    snap = _capture(tmp_path, [_run(tmp_path, "run1", records)], explicit_run_refs=True)
    assert snap.step_metrics[0].rework_cycle_count == 3


def test_t09_attempt_usage_counts_repair_and_distinguishes_unknown_zero_partial(tmp_path):
    records = [
        {"event_type": "provider_dispatch_finished", "step_execution_id": "exec-1", "dispatch_id": "llm", "phase": "producer", "token_usage": {"total_tokens": 100}},
        {"event_type": "provider_dispatch_finished", "step_execution_id": "exec-1", "dispatch_id": "repair", "phase": "repair", "token_usage": {"input_tokens": 400, "output_tokens": 500, "cached_input_tokens": 20}}, _step(1, "review", "needs_rework"),
        {"event_type": "provider_dispatch_started", "step_execution_id": "exec-2", "dispatch_id": "unknown", "phase": "producer"}, _step(2, "unknown", "done"),
        {"event_type": "provider_dispatch_finished", "step_execution_id": "exec-3", "dispatch_id": "zero", "phase": "producer", "token_usage": {"total_tokens": 0}}, _step(3, "zero", "done"),
        {"event_type": "provider_dispatch_finished", "step_execution_id": "exec-4", "dispatch_id": "partial", "phase": "producer", "token_usage": {"input_tokens": 7}}, _step(4, "partial", "done")]
    by_step = {o.step_id: o for o in _capture(tmp_path, [_run(tmp_path, "run1", records)], explicit_run_refs=True).observations}
    assert by_step["review"].known_total_tokens == 1000
    assert by_step["unknown"].usage_availability == "unknown"
    assert (by_step["zero"].usage_availability, by_step["zero"].known_total_tokens) == ("known_total", 0)
    assert by_step["partial"].usage_availability == "partial"


def test_t09_legacy_missing_attempt_phase_prevents_false_complete_usage(tmp_path):
    record = _step(1, "review", "needs_rework", producer_attempted=True, verifier_attempted=True,
                   provider_usage={"producer": {"total_tokens": 10}})
    observation = _capture(tmp_path, [_run(tmp_path, "run1", [record])], explicit_run_refs=True).observations[0]
    assert observation.known_total_tokens == 10
    assert observation.usage_availability == "partial"
    assert [(a.phase, a.availability) for a in observation.attempts] == [("producer", "known_total"), ("verifier", "unknown")]


def test_t10_structural_groups_do_not_pool_unknown_or_changed_surfaces(tmp_path):
    current = _run(tmp_path, "run1", [_step(1, "review", "needs_rework")])
    old = _run(tmp_path, "run2", [_step(1, "review", "needs_rework")], surface="old")
    unknown = _run(tmp_path, "run3", [_step(1, "review", "needs_rework")], surface=None, topology=None, graph=False)
    snap = _capture(tmp_path, [old, unknown, current])
    assert len(snap.groups) == 2 and snap.recommendation_basis == "current_verified"
    assert snap.shortlist[0].distinct_run_count == 1
    assert next(r for r in snap.runs if r.run_id == "run3").structural_group_id is None


def test_t10_foreign_workflow_identity_with_same_surface_and_topology_is_not_current(tmp_path):
    old = _run(tmp_path, "run1", [_step(1, "review", "needs_rework")])
    payload = json.loads((old / "run.json").read_text())
    payload["provenance"]["workflow_identity"] = "foreign-origin"
    (old / "run.json").write_text(json.dumps(payload))
    snap = _capture(tmp_path, [old])
    assert snap.groups[0].current_match is False
    assert snap.recommendation_basis == "no_comparable_evidence"
    assert snap.shortlist == ()
    assert snap.next_action == "collect_evidence"


def test_t10_nested_start_end_provenance_detects_mixed_source(tmp_path):
    run = _run(tmp_path, "run1", [_step(1, "review", "needs_rework")])
    payload = json.loads((run / "run.json").read_text())
    base = payload["provenance"]
    payload["provenance"] = {"start": base, "end": {**base, "workflow_surface_manifest_id": "changed"}}
    (run / "run.json").write_text(json.dumps(payload))
    snap = _capture(tmp_path, [run], explicit_run_refs=True)
    assert snap.runs[0].provenance_state == "mixed"
    assert snap.runs[0].structural_group_id is None
    assert snap.next_action == "collect_evidence"


def test_t11_names_do_not_infer_provider_or_editable_surface(tmp_path):
    records = [
        _step(1, "model_sounding_python", "failed", step_kind="python", provider_attempted=False),
        _step(2, "publish_model_step", "failed", step_kind="pair", provider_attempted=True),
    ]
    snap = _capture(tmp_path, [_run(tmp_path, "run1", records)], explicit_run_refs=True, top_k_steps=2)
    assert [item.step_id for item in snap.shortlist] == ["model_sounding_python", "publish_model_step"]
    by_step = {item.step_id: item for item in snap.step_metrics}
    assert by_step["model_sounding_python"].complete_usage is True
    assert by_step["model_sounding_python"].attempted_dispatch_count == 0
    assert by_step["publish_model_step"].complete_usage is False


def test_t08_unscoped_ambiguous_legacy_lineage_stays_unknown(tmp_path):
    record = _step(1, "review", "needs_rework")
    record.pop("scope"); record.pop("item_id")
    run = _run(tmp_path, "run1", [record], graph=False)
    observation = _capture(tmp_path, [run], explicit_run_refs=True).observations[0]
    assert observation.lineage == "unknown"
    assert observation.rework_cycle is False


@pytest.mark.parametrize("objective,leader", [("reliability", "failure"), ("token_usage", "tokens"), ("latency", "latency")])
def test_t12_objective_order_and_one_total_top_k(tmp_path, objective, leader):
    records = [
        {"event_type": "provider_dispatch_finished", "step_execution_id": "e1", "dispatch_id": "a", "phase": "producer", "provider": "one", "token_usage": {"total_tokens": 5}}, _step(1, "failure", "failed", step_execution_id="e1", elapsed_seconds=1),
        {"event_type": "provider_dispatch_finished", "step_execution_id": "e2", "dispatch_id": "b", "phase": "producer", "provider": "two", "token_usage": {"total_tokens": 100}}, _step(2, "tokens", "done", step_execution_id="e2", elapsed_seconds=2),
        {"event_type": "provider_dispatch_finished", "step_execution_id": "e3", "dispatch_id": "c", "phase": "producer", "provider": "one", "token_usage": {"total_tokens": 10}}, _step(3, "latency", "done", step_execution_id="e3", elapsed_seconds=20)]
    snap = _capture(tmp_path, [_run(tmp_path, "run1", records)], explicit_run_refs=True, objective=objective, top_k_steps=1)
    assert [r.step_id for r in snap.shortlist] == [leader]
    path = write_evidence_snapshot(snap, tmp_path / "snapshot" / "evidence.json")
    assert read_evidence_snapshot(path) == snap


def test_t15_byte_admission_skips_large_then_admits_small(tmp_path):
    huge = _run(tmp_path, "run1", [_step(1, "review", "needs_rework", padding="x" * 5000)])
    small = _run(tmp_path, "run2", [_step(1, "review", "needs_rework")])
    budget = sum((small / n).stat().st_size for n in ("run.json", "trace.jsonl", "static_step_graph.json")) + 10
    snap = _capture(tmp_path, [huge, small], explicit_run_refs=True, max_evidence_bytes=budget)
    assert [r.run_id for r in snap.runs] == ["run2"]
    assert snap.excluded_runs[0].reason == "input_limit_exceeded" and snap.budget.budget_limited


def test_explicit_active_run_is_actionable_error(tmp_path):
    run = _run(tmp_path, "run1", [_step(1, "review", "done")])
    payload = json.loads((run / "run.json").read_text()); payload["status"] = "running"; (run / "run.json").write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="pause or complete"):
        _capture(tmp_path, [run], explicit_run_refs=True)

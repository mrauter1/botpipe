from __future__ import annotations

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from botpipe.surface_identity import SURFACE_MANIFEST_SCHEMA, canonical_surface_id
from botpipe_optimizer.evidence import baseline_surface_id, capture_evidence_snapshot
from botpipe_optimizer.optimization import (
    OperationObservation,
    RunObservation,
    capture_source_manifest,
)
from botpipe_optimizer.recommendations import (
    finalize_candidate_review_payload,
    finalize_candidate_set_payload,
    load_optimization_candidate,
    publish_recommendation,
    read_publication_receipt,
)


def _canonical_baseline():
    boundary = {"surface_kind": "workflow", "workflow_name": "example"}
    files = [
        {
            "relative_path": "example.py",
            "surface_sha256": "0" * 64,
            "size_bytes": 1,
            "executable": False,
        }
    ]
    mode_semantics = "posix-executable-bit"
    return {
        "schema": SURFACE_MANIFEST_SCHEMA,
        "surface_kind": "workflow",
        "root": "/example",
        "surface_root": "/example",
        "boundary": boundary,
        "mode_semantics": mode_semantics,
        "surface_id": canonical_surface_id(
            boundary=boundary, files=files, mode_semantics=mode_semantics
        ),
        "relative_paths": ["example.py"],
        "file_count": 1,
        "size_bytes": 1,
        "files": files,
    }


def _records(
    title: str = "Improve the failure path",
    baseline_manifest=None,
    *,
    max_evidence_bytes: int = 50 * 1024 * 1024,
    max_snapshot_bytes: int = 50 * 1024 * 1024,
):
    def example():
        return None

    example.workflow_name = "example"
    source = capture_source_manifest(example)
    operation = OperationObservation(
        "op",
        "run",
        "root",
        1,
        "activity",
        "draft",
        "failed",
        "rejected",
        1,
        1.0,
        {"total_tokens": 1},
        {},
        {},
        None,
    )
    run = RunObservation(
        "run",
        "run",
        None,
        "example",
        None,
        "workflow-example",
        "surface-example",
        "orchestration-example",
        "known",
        "failed",
        (operation,),
    )
    baseline = baseline_manifest or _canonical_baseline()
    baseline_id = baseline.get("surface_id") or baseline_surface_id(baseline)
    snapshot = capture_evidence_snapshot(
        "example",
        [run],
        source_manifest=source,
        baseline_surface_manifest_id=baseline_id,
        max_evidence_bytes=max_evidence_bytes,
        max_snapshot_bytes=max_snapshot_bytes,
    )
    candidate_set = finalize_candidate_set_payload(
        {
            "schema": "botpipe.workflow_optimization.candidate_set/v2",
            "selected_workflow": "example",
            "evidence_snapshot_id": snapshot.snapshot_id,
            "baseline_surface_manifest_id": baseline_id,
            "candidates": [
                {
                    "kind": "workflow",
                    "title": title,
                    "targets": ["example.py"],
                    "cited_observation_ids": [snapshot.observations[0].observation_id],
                    "proposed_change": "Handle the observed failure.",
                    "expected_effect": "Fewer failures.",
                    "risks": ["May reject an edge case."],
                    "validation_plan": {
                        "description": "Replay the failure.",
                        "checks": ["Run the regression case."],
                        "falsification": "The failure remains.",
                    },
                    "payload": {
                        "target_paths": ["example.py"],
                        "workflow_change": "Add a guard.",
                    },
                }
            ],
            "next_action": "implement_candidate",
            "no_candidate_reason": None,
        }
    )
    review = finalize_candidate_review_payload(
        {
            "schema": "botpipe.workflow_optimization.candidate_review/v2",
            "candidate_set_id": candidate_set.candidate_set_id,
            "evidence_snapshot_id": snapshot.snapshot_id,
            "baseline_surface_manifest_id": baseline_id,
            "accepted": True,
            "reviewed_candidate_ids": [candidate_set.candidates[0].candidate_id],
            "findings": [],
        }
    )
    return snapshot, candidate_set, review, baseline


def _publish(root: Path, title: str, **changes):
    snapshot, candidate_set, review, baseline = _records(title)
    receipt = publish_recommendation(
        output_dir=root,
        evidence_snapshot=snapshot,
        candidate_set=candidate_set,
        review=review,
        baseline_manifest=baseline,
        max_output_bytes=100_000,
        **changes,
    )
    return receipt, candidate_set


def _artifact_bytes(receipt):
    return {
        artifact.path: (
            Path(artifact.path).read_bytes(),
            hashlib.sha256(Path(artifact.path).read_bytes()).hexdigest(),
        )
        for artifact in receipt.supporting_artifacts
    }


def _rewrite_candidate_set(candidate_set, review, **changes):
    payload = candidate_set.model_dump(mode="json", by_alias=True)
    payload.update(changes)
    forged_set = finalize_candidate_set_payload(payload)
    review_payload = review.model_dump(mode="json", by_alias=True)
    review_payload.update(
        candidate_set_id=forged_set.candidate_set_id,
        reviewed_candidate_ids=[
            candidate.candidate_id for candidate in forged_set.candidates
        ],
    )
    forged_review = finalize_candidate_review_payload(review_payload)
    return forged_set, forged_review


def _candidate_with_unknown_citation(candidate_set, review):
    candidates = candidate_set.model_dump(mode="json", by_alias=True)["candidates"]
    candidates[0]["cited_observation_ids"] = ["observation_" + "f" * 64]
    return _rewrite_candidate_set(candidate_set, review, candidates=candidates)


def test_oversized_republication_does_not_mutate_accepted_generation(tmp_path):
    receipt_a, _ = _publish(tmp_path, "first")
    canonical = tmp_path / "optimization_publication_receipt.json"
    receipt_bytes = canonical.read_bytes()
    generation_bytes = _artifact_bytes(receipt_a)
    snapshot, candidate_b, review_b, baseline = _records("second")

    with pytest.raises(ValueError, match="published recommendation"):
        publish_recommendation(
            output_dir=tmp_path,
            evidence_snapshot=snapshot,
            candidate_set=candidate_b,
            review=review_b,
            baseline_manifest=baseline,
            max_output_bytes=2_000,
            supporting_content=b"x" * 5_000,
        )

    assert canonical.read_bytes() == receipt_bytes
    assert _artifact_bytes(receipt_a) == generation_bytes


def test_admitted_input_and_expanded_snapshot_use_same_publish_load_policy(tmp_path):
    input_limit = 1_000
    snapshot_limit = 10_000
    snapshot, candidate_set, review, baseline = _records(
        "separate evidence bounds",
        max_evidence_bytes=input_limit,
        max_snapshot_bytes=snapshot_limit,
    )
    assert snapshot.budget.max_bytes == input_limit
    baseline_size = len(
        (json.dumps(baseline, indent=2, sort_keys=True) + "\n").encode()
    )
    assert baseline_size < input_limit

    receipt = publish_recommendation(
        output_dir=tmp_path,
        evidence_snapshot=snapshot,
        candidate_set=candidate_set,
        review=review,
        baseline_manifest=baseline,
        max_output_bytes=100_000,
        max_evidence_bytes=input_limit,
        max_snapshot_bytes=snapshot_limit,
    )
    assert Path(receipt.evidence_snapshot_path).stat().st_size > input_limit

    selection = load_optimization_candidate(
        optimization_receipt_path=tmp_path / "optimization_publication_receipt.json",
        candidate_id=candidate_set.candidates[0].candidate_id,
        expected_selected_workflow="example",
        allowed_kinds=("workflow",),
        max_output_bytes=100_000,
        max_evidence_bytes=input_limit,
        max_snapshot_bytes=snapshot_limit,
    )
    assert selection.candidate == candidate_set.candidates[0]


def test_snapshot_bound_is_rechecked_before_receipt_switch(tmp_path, monkeypatch):
    from botpipe_optimizer import recommendations

    snapshot, candidate_set, review, baseline = _records("recheck snapshot")
    snapshot_size = len(
        (
            json.dumps(
                snapshot.model_dump(mode="json", by_alias=True),
                indent=2,
                sort_keys=True,
            )
            + "\n"
        ).encode()
    )
    install = recommendations._install_publication_generation

    def install_then_expand(path, contents):
        install(path, contents)
        evidence = path / "workflow_optimization_evidence.json"
        evidence.write_bytes(evidence.read_bytes() + b" ")

    monkeypatch.setattr(
        recommendations, "_install_publication_generation", install_then_expand
    )
    with pytest.raises(ValueError, match="bounded regular file"):
        publish_recommendation(
            output_dir=tmp_path,
            evidence_snapshot=snapshot,
            candidate_set=candidate_set,
            review=review,
            baseline_manifest=baseline,
            max_output_bytes=100_000,
            max_snapshot_bytes=snapshot_size,
        )
    assert not (tmp_path / "optimization_publication_receipt.json").exists()


def test_publisher_never_emits_receipt_larger_than_its_reader_limit(tmp_path):
    probe = tmp_path / "probe"
    receipt, _ = _publish(probe, "measure receipt")
    recommendation_names = {
        "workflow_optimization_candidates.json",
        "workflow_optimization_candidate_review.json",
        "workflow_optimization_report.md",
        "workflow_refinement_evidence.json",
        "workflow_optimization_supporting.md",
    }
    aggregate = sum(
        artifact.bytes
        for artifact in receipt.supporting_artifacts
        if Path(artifact.path).name in recommendation_names
    )
    receipt_bytes = len((probe / "optimization_publication_receipt.json").read_bytes())
    assert aggregate < receipt_bytes

    check = tmp_path / "check"
    snapshot, candidate_set, review, baseline = _records("measure receipt")
    with pytest.raises(ValueError, match="receipt exceeds max_output_bytes"):
        publish_recommendation(
            output_dir=check,
            evidence_snapshot=snapshot,
            candidate_set=candidate_set,
            review=review,
            baseline_manifest=baseline,
            max_output_bytes=receipt_bytes - 1,
        )
    assert not check.exists()


def test_baseline_without_surface_id_uses_same_fallback_on_publish_and_load(
    tmp_path,
):
    baseline = {
        "workflow_name": "example",
        "source_sha256": "a" * 64,
    }
    snapshot, candidate_set, review, _ = _records("fallback baseline", baseline)
    publish_recommendation(
        output_dir=tmp_path,
        evidence_snapshot=snapshot,
        candidate_set=candidate_set,
        review=review,
        baseline_manifest=baseline,
        max_output_bytes=100_000,
    )

    selection = load_optimization_candidate(
        optimization_receipt_path=(tmp_path / "optimization_publication_receipt.json"),
        candidate_id=candidate_set.candidates[0].candidate_id,
        expected_selected_workflow="example",
        allowed_kinds=("workflow",),
    )
    assert selection.receipt.baseline_surface_manifest_id == baseline_surface_id(
        baseline
    )


def test_publication_recomputes_asserted_canonical_baseline_identity(tmp_path):
    baseline = _canonical_baseline()
    snapshot, candidate_set, review, _ = _records("forged baseline", baseline)
    baseline["files"][0]["surface_sha256"] = "f" * 64

    with pytest.raises(ValueError, match="surface_id does not match"):
        publish_recommendation(
            output_dir=tmp_path,
            evidence_snapshot=snapshot,
            candidate_set=candidate_set,
            review=review,
            baseline_manifest=baseline,
            max_output_bytes=100_000,
        )
    assert not list(tmp_path.iterdir())


def test_loader_recomputes_asserted_baseline_in_fully_hashed_bundle(
    tmp_path, monkeypatch
):
    baseline = _canonical_baseline()
    snapshot, candidate_set, review, _ = _records("forged baseline", baseline)
    baseline["files"][0]["surface_sha256"] = "f" * 64

    from botpipe_optimizer import recommendations

    with monkeypatch.context() as patch:
        patch.setattr(
            recommendations,
            "_baseline_manifest_identity",
            lambda manifest: manifest["surface_id"],
        )
        publish_recommendation(
            output_dir=tmp_path,
            evidence_snapshot=snapshot,
            candidate_set=candidate_set,
            review=review,
            baseline_manifest=baseline,
            max_output_bytes=100_000,
        )

    with pytest.raises(ValueError, match="surface_id does not match"):
        load_optimization_candidate(
            optimization_receipt_path=(
                tmp_path / "optimization_publication_receipt.json"
            ),
            candidate_id=candidate_set.candidates[0].candidate_id,
            expected_selected_workflow="example",
            allowed_kinds=("workflow",),
        )


def test_commit_failure_preserves_previous_receipt_and_generation(
    tmp_path, monkeypatch
):
    receipt_a, _ = _publish(tmp_path, "first")
    canonical = tmp_path / "optimization_publication_receipt.json"
    receipt_bytes = canonical.read_bytes()
    generation_bytes = _artifact_bytes(receipt_a)

    from botpipe_optimizer import recommendations

    original = recommendations._atomic_bytes

    def crash_before_commit(path, content):
        if path == canonical:
            raise OSError("injected commit crash")
        return original(path, content)

    monkeypatch.setattr(recommendations, "_atomic_bytes", crash_before_commit)
    with pytest.raises(OSError, match="injected commit crash"):
        _publish(tmp_path, "second")

    assert canonical.read_bytes() == receipt_bytes
    assert _artifact_bytes(receipt_a) == generation_bytes


def test_generation_write_failure_preserves_previous_receipt_and_generation(
    tmp_path, monkeypatch
):
    receipt_a, _ = _publish(tmp_path, "first")
    canonical = tmp_path / "optimization_publication_receipt.json"
    receipt_bytes = canonical.read_bytes()
    generation_bytes = _artifact_bytes(receipt_a)

    from botpipe_optimizer import recommendations

    original = recommendations._write_new_file
    writes = 0

    def fail_during_generation(path, content):
        nonlocal writes
        writes += 1
        if writes == 2:
            raise OSError("injected generation write failure")
        return original(path, content)

    monkeypatch.setattr(recommendations, "_write_new_file", fail_during_generation)
    with pytest.raises(OSError, match="injected generation write failure"):
        _publish(tmp_path, "second")

    assert canonical.read_bytes() == receipt_bytes
    assert _artifact_bytes(receipt_a) == generation_bytes
    assert not list((tmp_path / "optimization_publications").glob(".publication-*"))


def test_successive_generations_remain_loadable_and_retry_is_idempotent(tmp_path):
    receipt_a, candidate_a = _publish(tmp_path, "first")
    generation_receipt_a = Path(receipt_a.candidate_set_path).parent / (
        "optimization_publication_receipt.json"
    )
    bytes_a = _artifact_bytes(receipt_a)

    receipt_b, candidate_b = _publish(tmp_path, "second")
    assert receipt_b.candidate_set_path != receipt_a.candidate_set_path
    assert _artifact_bytes(receipt_a) == bytes_a
    selection_a = load_optimization_candidate(
        optimization_receipt_path=generation_receipt_a,
        candidate_id=candidate_a.candidates[0].candidate_id,
        expected_selected_workflow="example",
        allowed_kinds=("workflow",),
    )
    assert selection_a.candidate == candidate_a.candidates[0]

    retried_a, _ = _publish(tmp_path, "first")
    assert retried_a == receipt_a
    assert len(list((tmp_path / "optimization_publications").iterdir())) == 2
    canonical = read_publication_receipt(
        tmp_path / "optimization_publication_receipt.json",
        max_output_bytes=100_000,
    )
    assert canonical == receipt_a
    assert candidate_b.candidates[0].candidate_id in receipt_b.reviewed_candidate_ids


def test_parallel_publications_commit_one_complete_generation(tmp_path):
    with ThreadPoolExecutor(max_workers=2) as executor:
        receipts = list(
            executor.map(lambda title: _publish(tmp_path, title)[0], ("one", "two"))
        )

    canonical = read_publication_receipt(
        tmp_path / "optimization_publication_receipt.json",
        max_output_bytes=100_000,
    )
    assert canonical in receipts
    for receipt in receipts:
        immutable_receipt = (
            Path(receipt.candidate_set_path).parent
            / "optimization_publication_receipt.json"
        )
        assert (
            read_publication_receipt(immutable_receipt, max_output_bytes=100_000)
            == receipt
        )
        assert _artifact_bytes(receipt)


@pytest.mark.parametrize("winerror", [5, 32, 33])
def test_receipt_switch_retries_windows_contention_without_touching_previous(
    tmp_path, monkeypatch, winerror
):
    import botpipe_optimizer.recommendations as recommendations

    previous, _ = _publish(tmp_path, "previous")
    canonical = tmp_path / "optimization_publication_receipt.json"
    previous_bytes = canonical.read_bytes()
    previous_artifacts = _artifact_bytes(previous)
    replace = recommendations.os.replace
    attempts, delays = [], []

    def contend(source, destination):
        attempts.append(destination)
        if len(attempts) <= 2:
            assert canonical.read_bytes() == previous_bytes
            failure = PermissionError("Windows handle contention")
            failure.winerror = winerror
            raise failure
        return replace(source, destination)

    monkeypatch.setattr(recommendations.os, "replace", contend)
    monkeypatch.setattr(recommendations.time, "sleep", delays.append)
    current, _ = _publish(tmp_path, "current")

    assert len(attempts) == 3
    assert delays == [0.01, 0.02]
    assert read_publication_receipt(canonical, max_output_bytes=100_000) == current
    assert _artifact_bytes(previous) == previous_artifacts


@pytest.mark.parametrize(
    "winerror,expected_attempts", [(5, 8), (32, 8), (33, 8), (None, 1)]
)
def test_failed_receipt_switch_preserves_bundle_and_cleans_staging(
    tmp_path, monkeypatch, winerror, expected_attempts
):
    import botpipe_optimizer.recommendations as recommendations

    previous, _ = _publish(tmp_path, "previous")
    canonical = tmp_path / "optimization_publication_receipt.json"
    previous_bytes = canonical.read_bytes()
    previous_artifacts = _artifact_bytes(previous)
    attempts = []

    def denied(source, destination):
        attempts.append(destination)
        failure = PermissionError("replacement denied")
        if winerror is not None:
            failure.winerror = winerror
        raise failure

    monkeypatch.setattr(recommendations.os, "replace", denied)
    monkeypatch.setattr(recommendations.time, "sleep", lambda _: None)
    with pytest.raises(PermissionError, match="replacement denied"):
        _publish(tmp_path, "current")

    assert len(attempts) == expected_attempts
    assert canonical.read_bytes() == previous_bytes
    assert _artifact_bytes(previous) == previous_artifacts
    assert not list(tmp_path.glob(".optimization_publication_receipt.json.*"))


def test_publication_rejects_symlinked_generation_root_before_writes(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (tmp_path / "optimization_publications").symlink_to(
        outside, target_is_directory=True
    )

    with pytest.raises(ValueError, match="publication directory"):
        _publish(tmp_path, "must stay inside output")

    assert not (tmp_path / "optimization_publication_receipt.json").exists()
    assert not list(outside.iterdir())


def test_publication_rejects_self_consistent_unknown_citation(tmp_path):
    snapshot, candidate_set, review, baseline = _records()
    forged_set, forged_review = _candidate_with_unknown_citation(candidate_set, review)

    with pytest.raises(ValueError, match="candidate cites unknown observations"):
        publish_recommendation(
            output_dir=tmp_path,
            evidence_snapshot=snapshot,
            candidate_set=forged_set,
            review=forged_review,
            baseline_manifest=baseline,
            max_output_bytes=100_000,
        )
    assert not list(tmp_path.iterdir())


def test_publication_requires_each_candidate_to_cite_evidence(tmp_path):
    snapshot, candidate_set, review, baseline = _records()
    candidate = candidate_set.candidates[0].model_copy(
        update={"cited_observation_ids": []}
    )
    candidate = candidate.model_copy(
        update={"candidate_id": candidate.expected_candidate_id()}
    )
    forged_set = candidate_set.model_copy(update={"candidates": [candidate]})
    forged_set = forged_set.model_copy(
        update={"candidate_set_id": forged_set.expected_candidate_set_id()}
    )
    review_payload = review.model_dump(mode="json", by_alias=True)
    review_payload.update(
        candidate_set_id=forged_set.candidate_set_id,
        reviewed_candidate_ids=[candidate.candidate_id],
    )
    forged_review = finalize_candidate_review_payload(review_payload)

    with pytest.raises(ValueError, match="(must cite|at least 1 item)"):
        publish_recommendation(
            output_dir=tmp_path,
            evidence_snapshot=snapshot,
            candidate_set=forged_set,
            review=forged_review,
            baseline_manifest=baseline,
            max_output_bytes=100_000,
        )
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize(
    ("candidates", "next_action", "reason", "message"),
    [
        ("keep", "collect_evidence", None, "non-empty CandidateSet"),
        ("keep", "implement_candidate", "No candidate.", "non-empty CandidateSet"),
        ([], "implement_candidate", None, "empty CandidateSet"),
        ([], "collect_evidence", None, "empty CandidateSet"),
    ],
)
def test_publication_rejects_candidate_action_invariant_violations(
    tmp_path, candidates, next_action, reason, message
):
    snapshot, candidate_set, review, baseline = _records()
    selected = (
        candidate_set.model_dump(mode="json", by_alias=True)["candidates"]
        if candidates == "keep"
        else candidates
    )
    forged_set, forged_review = _rewrite_candidate_set(
        candidate_set,
        review,
        candidates=selected,
        next_action=next_action,
        no_candidate_reason=reason,
    )

    with pytest.raises(ValueError, match=message):
        publish_recommendation(
            output_dir=tmp_path,
            evidence_snapshot=snapshot,
            candidate_set=forged_set,
            review=forged_review if selected else None,
            baseline_manifest=baseline,
            max_output_bytes=100_000,
        )
    assert not list(tmp_path.iterdir())


def test_publication_strictly_reparses_model_copy_updates(tmp_path):
    snapshot, candidate_set, review, baseline = _records()
    forged_set = candidate_set.model_copy(update={"no_candidate_reason": 123})
    with pytest.warns(UserWarning, match="serializer warnings"):
        forged_id = forged_set.expected_candidate_set_id()
    forged_set = forged_set.model_copy(update={"candidate_set_id": forged_id})
    review_payload = review.model_dump(mode="json", by_alias=True)
    review_payload["candidate_set_id"] = forged_set.candidate_set_id
    forged_review = finalize_candidate_review_payload(review_payload)

    with (
        pytest.warns(UserWarning, match="serializer warnings"),
        pytest.raises(ValueError, match="no_candidate_reason"),
    ):
        publish_recommendation(
            output_dir=tmp_path,
            evidence_snapshot=snapshot,
            candidate_set=forged_set,
            review=forged_review,
            baseline_manifest=baseline,
            max_output_bytes=100_000,
        )
    assert not list(tmp_path.iterdir())


def test_publication_strictly_reparses_review_model_copy_updates(tmp_path):
    snapshot, candidate_set, review, baseline = _records()
    forged_review = review.model_copy(update={"accepted": "yes"})
    with pytest.warns(UserWarning, match="serializer warnings"):
        forged_id = forged_review.expected_review_id()
    forged_review = forged_review.model_copy(update={"review_id": forged_id})

    with (
        pytest.warns(UserWarning, match="serializer warnings"),
        pytest.raises(ValueError, match="accepted"),
    ):
        publish_recommendation(
            output_dir=tmp_path,
            evidence_snapshot=snapshot,
            candidate_set=candidate_set,
            review=forged_review,
            baseline_manifest=baseline,
            max_output_bytes=100_000,
        )
    assert not list(tmp_path.iterdir())


def test_loader_rejects_fully_hashed_bundle_with_unknown_citation(
    tmp_path, monkeypatch
):
    snapshot, candidate_set, review, baseline = _records()
    forged_set, forged_review = _candidate_with_unknown_citation(candidate_set, review)

    from botpipe_optimizer import recommendations

    with monkeypatch.context() as patch:
        patch.setattr(
            recommendations,
            "_validate_candidate_semantics",
            lambda candidate_set, evidence_snapshot: None,
        )
        publish_recommendation(
            output_dir=tmp_path,
            evidence_snapshot=snapshot,
            candidate_set=forged_set,
            review=forged_review,
            baseline_manifest=baseline,
            max_output_bytes=100_000,
        )

    with pytest.raises(ValueError, match="candidate cites unknown observations"):
        load_optimization_candidate(
            optimization_receipt_path=(
                tmp_path / "optimization_publication_receipt.json"
            ),
            candidate_id=forged_set.candidates[0].candidate_id,
            expected_selected_workflow="example",
            allowed_kinds=("workflow",),
        )


@pytest.mark.parametrize("record", ["candidate", "review", "evidence"])
def test_publication_rejects_malformed_content_identity_before_writes(tmp_path, record):
    snapshot, candidate_set, review, baseline = _records()
    if record == "candidate":
        candidate_set = candidate_set.model_copy(
            update={"candidate_set_id": "candidate_set_" + "0" * 64}
        )
    elif record == "review":
        review = review.model_copy(update={"review_id": "candidate_review_" + "0" * 64})
    else:
        snapshot = snapshot.model_copy(update={"snapshot_id": "evidence_" + "0" * 64})

    with pytest.raises(ValueError, match="(identity|match)"):
        publish_recommendation(
            output_dir=tmp_path,
            evidence_snapshot=snapshot,
            candidate_set=candidate_set,
            review=review,
            baseline_manifest=baseline,
            max_output_bytes=100_000,
        )
    assert not list(tmp_path.iterdir())

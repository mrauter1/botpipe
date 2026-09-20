from __future__ import annotations

from types import SimpleNamespace

import pytest

from labs.workflows.workflow_package_to_composable_building_blocks.workflow import (
    _assert_decomposition_anchors,
)


def test_decomposition_checkpoint_anchors_bind_ids_and_authoritative_paths() -> None:
    state = SimpleNamespace(
        baseline_parent_surface_id="baseline-id",
        baseline_authoritative_sources={"workflow.py": "/repo/workflow.py"},
        candidate_decomposition_surface_id="candidate-id",
    )
    ctx = SimpleNamespace(state=state)
    baseline = {
        "surface_id": "baseline-id",
        "files": [
            {
                "relative_path": "workflow.py",
                "source_path": "/repo/workflow.py",
            }
        ],
    }
    candidate = {"surface_id": "candidate-id"}

    _assert_decomposition_anchors(ctx, baseline, candidate)

    for forged_baseline, forged_candidate, match in (
        ({**baseline, "surface_id": "other"}, candidate, "baseline surface"),
        (
            {
                **baseline,
                "files": [
                    {
                        "relative_path": "workflow.py",
                        "source_path": "/other/workflow.py",
                    }
                ],
            },
            candidate,
            "source paths",
        ),
        (baseline, {"surface_id": "other"}, "candidate decomposition surface"),
    ):
        with pytest.raises(ValueError, match=match):
            _assert_decomposition_anchors(ctx, forged_baseline, forged_candidate)


def test_decomposition_checkpoint_requires_independent_state_anchors() -> None:
    ctx = SimpleNamespace(
        state=SimpleNamespace(
            baseline_parent_surface_id=None,
            baseline_authoritative_sources={},
            candidate_decomposition_surface_id=None,
        )
    )

    with pytest.raises(ValueError, match="checkpoint lacks surface anchors"):
        _assert_decomposition_anchors(ctx, {}, {})

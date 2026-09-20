from __future__ import annotations

import warnings

import pytest
from pydantic import ValidationError

from botpipe import codec
from labs.workflows.workflow_run_traces_to_optimization_candidates.params import Params


def _params(**changes):
    values = {
        "selected_workflow": "example",
        "task_title": "Optimize example",
    }
    values.update(changes)
    return Params(**values)


def test_deprecated_candidate_alias_is_consumed_before_model_state():
    with pytest.warns(FutureWarning, match="max_candidates_per_pass"):
        params = _params(max_candidates_per_pass=5)

    assert params.max_candidates == 5
    assert "max_candidates_per_pass" not in type(params).model_fields
    assert "max_candidates_per_pass" not in params.model_dump()
    assert codec.decode(codec.encode(params)) == params


@pytest.mark.parametrize(
    ("depth", "turns", "seconds"),
    [("cheap", 6, 1800), ("standard", 12, 3600), ("ablation", 6, 1800)],
)
def test_deprecated_depth_alias_maps_limits_without_hidden_state(depth, turns, seconds):
    with pytest.warns(FutureWarning, match="optimization_depth"):
        params = _params(optimization_depth=depth)

    assert (params.max_provider_turns, params.max_analysis_seconds) == (
        turns,
        seconds,
    )
    assert "optimization_depth" not in type(params).model_fields
    assert "optimization_depth" not in params.model_dump()
    assert codec.decode(codec.encode(params)) == params


def test_deprecated_alias_none_is_accepted_and_discarded_without_warning():
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        params = _params(
            max_candidates_per_pass=None,
            optimization_depth=None,
            max_candidates=4,
        )

    assert params.max_candidates == 4
    assert params.max_provider_turns == 6
    assert params.max_analysis_seconds == 1800
    assert (
        not {
            "max_candidates_per_pass",
            "optimization_depth",
        }
        & params.model_fields_set
    )


def test_deprecated_alias_conflicts_and_invalid_depth_still_fail_explicitly():
    with pytest.raises(ValidationError, match="max_candidates conflicts"):
        _params(max_candidates=2, max_candidates_per_pass=3)

    with pytest.raises(ValidationError, match="optimization_depth must be"):
        _params(optimization_depth="deep")


def test_explicit_limits_override_deprecated_depth_defaults():
    with pytest.warns(FutureWarning, match="optimization_depth"):
        params = _params(
            optimization_depth="standard",
            max_provider_turns=9,
            max_analysis_seconds=900,
        )

    assert params.max_provider_turns == 9
    assert params.max_analysis_seconds == 900

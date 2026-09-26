from __future__ import annotations

import math

import pytest
from pydantic import ValidationError

from botpipe import codec
from labs.workflows.improve_workflow import ImproveWorkflowParams


def _params(**changes):
    values = {"selected_workflow": "example"}
    values.update(changes)
    return ImproveWorkflowParams(**values)


def test_improvement_parameters_preserve_selection_and_budgets_through_journal_codec():
    params = _params(
        objective="token_usage",
        metric_view="token_usage",
        run_refs=["task/run"],
        max_provider_turns=3,
        max_provider_seconds=30,
    )
    assert codec.decode(codec.encode(params)) == params


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"selected_workflow": " "}, "must not be blank"),
        ({"objective": " "}, "must not be blank"),
        ({"evaluation_spec_path": "\t"}, "must not be blank"),
        ({"run_refs": ["run", "run"]}, "run_refs must be unique"),
        ({"run_refs": ["task/group/run"]}, "run_refs must be unique"),
        ({"target_test_argv": []}, "nonempty argument list"),
        ({"target_test_argv": ["python", " "]}, "nonempty argument list"),
        ({"history_limit": 0}, "greater than 0"),
        ({"max_revisions": -1}, "greater than or equal to 0"),
        ({"max_provider_turns": 0}, "greater than 0"),
        ({"max_evidence_bytes": 0}, "greater than 0"),
    ],
)
def test_improve_workflow_params_reject_invalid_selection_and_bounds(changes, message):
    with pytest.raises(ValidationError, match=message):
        _params(**changes)


@pytest.mark.parametrize(
    "field",
    ["provider_timeout", "max_provider_seconds", "validation_timeout"],
)
@pytest.mark.parametrize("value", [0, -1, math.inf, math.nan])
def test_improve_workflow_params_require_finite_positive_time_budgets(field, value):
    with pytest.raises(ValidationError):
        _params(**{field: value})


def test_improve_workflow_params_accept_contextual_free_text_priority():
    assert _params(objective="Prioritize citation accuracy").objective == (
        "Prioritize citation accuracy"
    )


def test_improve_workflow_params_reject_unknown_optional_metric_view():
    with pytest.raises(ValidationError, match="reliability"):
        _params(metric_view="cost")

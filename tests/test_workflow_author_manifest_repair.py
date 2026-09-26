"""Manifest-shape failures participate in the author's bounded repair loop."""

from __future__ import annotations

import json

from botpipe import Botpipe
from botpipe.providers import FakeProvider
from botpipe.workflows.workflow_author import Params, workflow_author
from tests.test_workflow_author import _answer, _input


def test_conflicting_manifest_paths_are_repaired_on_next_build(tmp_path):
    builds = []

    def answer(request):
        result = _answer(request)
        if "workflow_package_manifest" not in request.artifacts:
            return result
        builds.append(_input(request))
        if len(builds) == 1:
            manifest_path = request.artifacts["workflow_package_manifest"]
            manifest = json.loads(manifest_path.read_text())
            root = ".botpipe/workflows/manifest_repair"
            manifest["files"].extend(
                [
                    {"path": f"{root}/prompts", "content": "not a directory"},
                    {"path": f"{root}/prompts/run.md", "content": "Run the task."},
                ]
            )
            manifest_path.write_text(json.dumps(manifest))
        return result

    provider = FakeProvider([answer] * 7)
    with Botpipe(tmp_path, provider=provider) as client:
        result = client.run(
            workflow_author,
            Params(package_name="manifest_repair"),
            request="Echo the request.",
        )

        assert result.ok, result.error
        assert len(builds) == 2
        feedback = builds[1]["runtime_validation_feedback"]
        assert feedback["manifest_validation"] == {
            "success": False,
            "error_type": "WorkflowManifestValidationError",
            "errors": [
                (
                    "generated file paths conflict: "
                    ".botpipe/workflows/manifest_repair/prompts and "
                    ".botpipe/workflows/manifest_repair/prompts/run.md"
                )
            ],
        }
        assert result.value.validation.success
        call_count = len(provider.calls)
        replayed = client.resume(result.run_id, workflow=workflow_author)
        assert replayed.ok, replayed.error
        assert replayed.value == result.value
        assert len(provider.calls) == call_count


def test_invalid_manifest_json_exhausts_the_existing_build_bound(tmp_path):
    builds = []

    def answer(request):
        result = _answer(request)
        if "workflow_package_manifest" in request.artifacts:
            builds.append(_input(request))
            request.artifacts["workflow_package_manifest"].write_text("{")
        return result

    result = Botpipe(tmp_path, provider=FakeProvider([answer] * 6)).run(
        workflow_author,
        Params(package_name="invalid_manifest"),
        request="Echo the request.",
    )

    assert result.status == "failed"
    assert len(builds) == 3
    assert "generated workflow did not validate after 3 build attempts" in result.error
    assert "workflow_package_manifest must contain a JSON object" in result.error
    for build in builds[1:]:
        feedback = build["runtime_validation_feedback"]
        assert feedback["manifest_validation"]["errors"] == [
            "workflow_package_manifest must contain a JSON object"
        ]

from __future__ import annotations

from pathlib import Path

import pytest

from botpipe.discovery import (
    WorkflowInputError,
    discover_workflows,
    resolve_workflow,
    validate_workflow_inputs,
)
from botpipe.inspection import inspect_workflow, observed_graph


def _write_workflow(root: Path, name: str = "greet") -> Path:
    package = root / ".botpipe" / "workflows" / name
    package.mkdir(parents=True)
    (package / "workflow.toml").write_text(
        f'name = "{name}"\nversion = "3"\ndescription = "Greeting workflow"\naliases = ["hello"]\n',
        encoding="utf-8",
    )
    source = package / "workflow.py"
    source.write_text(
        "from botpipe import workflow\n\n"
        f"@workflow(name={name!r}, version='3')\n"
        "def greet(count: int, label: str = 'item') -> str:\n"
        "    return f'{count} {label}'\n",
        encoding="utf-8",
    )
    return source


def test_discovers_workspace_metadata_and_resolves_catalog_file_and_module_references(
    tmp_path: Path,
) -> None:
    source = _write_workflow(tmp_path)
    entries = {
        entry.name: entry for entry in discover_workflows(tmp_path, include_labs=False)
    }

    entry = entries["greet"]
    assert entry.source_kind == "workspace"
    assert entry.source_path == source.resolve()
    assert entry.version == "3"
    assert entry.aliases == ("hello",)

    by_name = resolve_workflow("greet", tmp_path)
    by_file = resolve_workflow(f"{source}:greet", tmp_path)
    by_alias = resolve_workflow("hello", tmp_path)
    assert by_name.fn(2, "tests") == "2 tests"
    assert by_file.fn(1) == "1 item"
    assert by_alias.fn(3) == "3 item"

    package = tmp_path / "example"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "flows.py").write_text(
        "def plain(value: str): return value.upper()\n", encoding="utf-8"
    )
    assert resolve_workflow("example.flows:plain", tmp_path)("ok") == "OK"


def test_workspace_name_shadows_packaged_name(tmp_path: Path) -> None:
    _write_workflow(tmp_path, "ralph_loop")
    entry = next(
        item for item in discover_workflows(tmp_path) if item.name == "ralph_loop"
    )
    assert entry.source_kind == "workspace"


def test_input_binding_validates_and_converts_annotations(tmp_path: Path) -> None:
    workflow = resolve_workflow(f"{_write_workflow(tmp_path)}:greet", tmp_path)
    bound = validate_workflow_inputs(workflow, (), {"count": "4"})
    assert bound.args == (4, "item")
    assert bound.kwargs == {}

    with pytest.raises(WorkflowInputError, match="invalid input 'count'"):
        validate_workflow_inputs(workflow, (), {"count": "many"})
    with pytest.raises(WorkflowInputError, match="missing a required argument"):
        validate_workflow_inputs(workflow)


def test_declared_inspection_marks_topology_dynamic(tmp_path: Path) -> None:
    source = _write_workflow(tmp_path)
    report = inspect_workflow(f"{source}:greet", tmp_path)

    assert report["name"] == "greet"
    assert report["version"] == "3"
    assert report["contract"]["parameters"][0]["schema"]["type"] == "integer"
    assert report["source"]["sha256"]
    assert report["topology"] == {
        "dynamic": True,
        "complete": False,
        "message": "Branches, loops, nested workflows, and operations are observed during execution.",
    }


def test_observed_graph_contains_only_recorded_nodes_and_scope_order() -> None:
    graph = observed_graph(
        [
            {
                "id": "root-1",
                "scope": "root",
                "ordinal": 1,
                "kind": "provider",
                "status": "completed",
            },
            {
                "id": "root-0",
                "scope": "root",
                "ordinal": 0,
                "kind": "activity",
                "status": "completed",
            },
            {
                "id": "child-0",
                "scope": "root/child",
                "ordinal": 0,
                "kind": "provider",
                "status": "failed",
            },
        ]
    )
    assert {node["id"] for node in graph["nodes"]} == {"root-0", "root-1", "child-0"}
    assert {tuple(edge.values()) for edge in graph["edges"]} >= {
        ("root-0", "root-1", "observed_order")
    }
    assert graph["complete_static_topology"] is False


def test_client_inspection_links_nested_and_parallel_scopes_to_exact_parent_operations(
    tmp_path: Path,
) -> None:
    from botpipe import Botpipe, activity, parallel, workflow
    from botpipe.inspection import inspect_run
    from botpipe.providers import FakeProvider

    @activity(retry_safe=True)
    def mark(label: str) -> str:
        return label

    @workflow
    def child() -> str:
        return mark("child")

    @workflow
    def parent() -> list[str]:
        before = mark("before")
        nested = child()
        branches = parallel(lambda: mark("left"), lambda: mark("right"))
        after = mark("after")
        return [before, nested, *branches, after]

    with Botpipe(tmp_path, provider=FakeProvider([])) as client:
        result = client.run(
            parent, run_id="inspection-lineage", task_id="inspection-lineage"
        )
        raw = client.inspect(result.run_id)
        report = inspect_run(client, result.run_id)

    assert result.ok
    assert {operation["scope"] for operation in raw["operations"]} == {
        "root",
        "root/child-1",
        "root/parallel-2/0",
        "root/parallel-2/1",
    }
    child_edges = {
        (edge["from"], edge["to"])
        for edge in report["observed_graph"]["edges"]
        if edge["kind"] == "observed_child"
    }
    assert child_edges == {
        (f"{result.run_id}:root:1", f"{result.run_id}:root/child-1:0"),
        (f"{result.run_id}:root:2", f"{result.run_id}:root/parallel-2/0:0"),
        (f"{result.run_id}:root:2", f"{result.run_id}:root/parallel-2/1:0"),
    }
    assert (
        f"{result.run_id}:root:3",
        f"{result.run_id}:root/child-1:0",
    ) not in child_edges


def test_observed_graph_decodes_inputs_before_exposing_attempt_and_artifact_dependencies() -> (
    None
):
    from botpipe import codec

    graph = observed_graph(
        [
            {
                "id": "provider-0",
                "scope": "root",
                "ordinal": 0,
                "kind": "provider",
                "inputs": codec.encode(
                    {
                        "attempt": 2,
                        "reads": [{"name": "brief"}],
                        "writes": [{"name": "report"}],
                    }
                ),
            }
        ]
    )
    node = graph["nodes"][0]
    assert node["attempt"] == 2
    assert node["inputs"]["attempt"] == 2
    assert node["artifact_dependencies"] == {
        "reads": [{"name": "brief"}],
        "writes": [{"name": "report"}],
    }

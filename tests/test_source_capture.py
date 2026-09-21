from __future__ import annotations

import functools
import importlib.util
from _io import FileIO
from functools import partial
from pathlib import Path

import pytest
from pydantic_core import SchemaValidator

from botpipe._callables import describe_callable
from botpipe.provenance import (
    SourceCaptureError,
    capture_definition_sources,
    capture_orchestration_sources,
    source_context,
)


def _loaded_function(source: Path, text: str, name: str):
    source.write_text(text)
    namespace = {"__name__": source.stem}
    exec(compile(text, str(source), "exec"), namespace)  # noqa: S102
    return namespace[name]


def test_missing_identified_source_preserves_context_but_strict_capture_fails(tmp_path):
    source = tmp_path / "missing.py"
    source.write_text("def entry(): return 1\n")
    spec = importlib.util.spec_from_file_location("missing_source_module", source)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    source.unlink()

    context = source_context(module.entry)
    assert context.origin_source == source.resolve(strict=False)
    with pytest.raises(SourceCaptureError, match="read owned Python source"):
        capture_definition_sources(module.entry, context=context)


def test_missing_owned_helper_source_is_an_explicit_capture_error(tmp_path):
    helper_source = tmp_path / "helper.py"
    helper = _loaded_function(helper_source, "def helper(): return 1\n", "helper")
    root_source = tmp_path / "root.py"
    text = "def entry(): return helper()\n"
    root_source.write_text(text)
    namespace = {"__name__": "root", "helper": helper}
    exec(compile(text, str(root_source), "exec"), namespace)  # noqa: S102
    entry = namespace["entry"]
    graph = describe_callable(entry)
    context = source_context(entry, graph=graph)
    helper_source.unlink()

    with pytest.raises(SourceCaptureError, match="owned Python source"):
        capture_orchestration_sources(
            entry, boundary=tmp_path, graph=graph, context=context
        )


def test_unreadable_owned_python_source_does_not_block_workflow(tmp_path, monkeypatch):
    from botpipe.runtime import Workflow

    source = tmp_path / "unreadable.py"
    function = _loaded_function(source, "def entry(): return 1\n", "entry")
    real_read_bytes = Path.read_bytes

    def blocked_read(path):
        if path == source.resolve():
            raise PermissionError("blocked for test")
        return real_read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", blocked_read)
    definition = Workflow(function)
    assert definition._orchestration_sources_at_definition is None


def test_synthetic_source_free_callable_is_skipped():
    namespace = {"__name__": "synthetic"}
    exec(compile("def entry(): return 1\n", "<synthetic>", "exec"), namespace)  # noqa: S102

    context = source_context(namespace["entry"])
    assert context.origin_target is namespace["entry"]
    assert context.origin_source is None
    assert context.origin_boundary is None
    assert context.owned_boundaries == ()


def test_native_extension_class_is_source_free():
    context = source_context(SchemaValidator)
    assert context.origin_target is SchemaValidator
    assert context.origin_source is None
    assert context.origin_boundary is None
    assert context.owned_boundaries == ()


def test_uninspectable_first_graph_target_does_not_hide_later_source(tmp_path):
    source = tmp_path / "branch.py"
    branch = _loaded_function(
        source,
        "from functools import partial\n"
        "from _io import FileIO\n"
        "class Runner:\n"
        "    def run(self, callback): return callback\n"
        "branch = partial(Runner().run, FileIO)\n",
        "branch",
    )
    assert isinstance(branch, partial)
    graph = describe_callable(branch)
    assert graph.source_targets[0] is FileIO

    captured = capture_orchestration_sources(
        branch,
        boundary=tmp_path,
        graph=graph,
        context=source_context(branch, graph=graph),
    )
    assert captured is not None
    assert set(captured["files"]) == {"branch.py"}
    assert captured["bindings"]["<workflow>"]["qualname"] == "Runner.run"


def test_owned_class_discovers_shared_late_partial_tail_once(tmp_path, monkeypatch):
    target_source = tmp_path / "target.py"
    answer = _loaded_function(
        target_source, "def answer(): return 'answer'\n", "answer"
    )
    callback = partial(answer)
    invoke_source = tmp_path / "invoke.py"
    invoke = _loaded_function(
        invoke_source, "def invoke(callback): return callback()\n", "invoke"
    )
    branches = [partial(invoke, callback) for _ in range(25)]
    config_source = tmp_path / "config.py"
    config_text = "class Config:\n" + "".join(
        f"    def branch_{index}(self): return branch_{index}\n"
        for index in range(len(branches))
    )
    config_source.write_text(config_text)
    config_namespace = {
        "__name__": "config",
        **{f"branch_{index}": branch for index, branch in enumerate(branches)},
    }
    exec(  # noqa: S102
        compile(config_text, str(config_source), "exec"), config_namespace
    )
    workflow_source = tmp_path / "workflow.py"
    job = _loaded_function(
        workflow_source,
        "def job(): return Config().branch_0()()\n",
        "job",
    )
    job.__globals__["Config"] = config_namespace["Config"]

    from botpipe import provenance

    actual_describe = provenance.describe_callable
    actual_source_path = provenance._identified_source_path
    traversed: list[object] = []
    inspected: list[object] = []

    @functools.wraps(actual_describe)
    def counted_describe(value):
        traversed.append(value)
        return actual_describe(value)

    def counted_source_path(value):
        inspected.append(value)
        return actual_source_path(value)

    monkeypatch.setattr(provenance, "describe_callable", counted_describe)
    monkeypatch.setattr(provenance, "_identified_source_path", counted_source_path)
    captured = capture_orchestration_sources(job, boundary=tmp_path)

    assert captured is not None
    assert set(captured["files"]) == {
        "config.py",
        "invoke.py",
        "target.py",
        "workflow.py",
    }
    assert traversed == [job]
    assert inspected.count(answer) == 1
    assert inspected.count(invoke) == 1

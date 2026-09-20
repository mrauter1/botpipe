from __future__ import annotations

import importlib.util
from _io import FileIO
from functools import partial
from pathlib import Path

import pytest
from pydantic_core import SchemaValidator

from botpipe._callables import describe_callable
from botpipe.provenance import (
    SourceCaptureError,
    capture_orchestration_sources,
    source_context,
)


def _loaded_function(source: Path, text: str, name: str):
    source.write_text(text)
    namespace = {"__name__": source.stem}
    exec(compile(text, str(source), "exec"), namespace)  # noqa: S102
    return namespace[name]


def test_missing_identified_python_source_is_an_explicit_error(tmp_path):
    source = tmp_path / "missing.py"
    source.write_text("def entry(): return 1\n")
    spec = importlib.util.spec_from_file_location("missing_source_module", source)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    source.unlink()

    with pytest.raises(SourceCaptureError, match="identified Python source"):
        source_context(module.entry)


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


def test_unreadable_owned_python_source_is_an_explicit_error(tmp_path, monkeypatch):
    from botpipe.runtime import Workflow

    source = tmp_path / "unreadable.py"
    function = _loaded_function(source, "def entry(): return 1\n", "entry")
    real_read_bytes = Path.read_bytes

    def blocked_read(path):
        if path == source.resolve():
            raise PermissionError("blocked for test")
        return real_read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", blocked_read)
    with pytest.raises(SourceCaptureError, match="read owned Python source"):
        Workflow(function)


def test_synthetic_source_free_callable_is_skipped():
    namespace = {"__name__": "synthetic"}
    exec(compile("def entry(): return 1\n", "<synthetic>", "exec"), namespace)  # noqa: S102

    context = source_context(namespace["entry"])
    assert context.origin_target is namespace["entry"]
    assert context.origin_source is None
    assert context.origin_boundary is None
    assert context.owned_boundaries == ()
    assert context.ownership_anchor is None


def test_native_extension_class_is_source_free():
    context = source_context(SchemaValidator)
    assert context.origin_target is SchemaValidator
    assert context.origin_source is None
    assert context.origin_boundary is None
    assert context.owned_boundaries == ()
    assert context.ownership_anchor is None


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

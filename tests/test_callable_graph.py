from __future__ import annotations

import functools
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

from botpipe import Botpipe, parallel, workflow
from botpipe._callables import describe_callable
from botpipe.providers import FakeProvider
from botpipe.runtime import _function_version


def _write(path: Path, source: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source)
    return path


def _run(script: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(script)],
        cwd=script.parent,
        env=os.environ.copy(),
        text=True,
        capture_output=True,
        check=False,
    )


def _factory(value):
    def callback():
        return value

    return callback


def _execute(first, second):
    return first() + second()


def test_completed_parallel_returns_recorded_result_after_binding_change(tmp_path):
    original = functools.partial(_execute, _factory(1), _factory(2))
    changed = functools.partial(_execute, _factory(1), _factory(3))
    assert _function_version(original) != _function_version(changed)

    selected = [original]

    @workflow
    def job():
        return parallel(selected[0])

    with Botpipe(tmp_path, provider=FakeProvider([])) as client:
        first = client.run(job, run_id="duplicate-qualname")
        assert first.ok and first.value == [3], first.error
        before = client.journal.operations(first.run_id)
        selected[0] = changed
        resumed = client.resume(first.run_id, workflow=job)
        assert resumed.ok and resumed.value == [3]
        assert client.journal.operations(first.run_id) == before


def test_alias_topology_is_part_of_identity_but_receiver_state_is_not():
    shared = _factory(1)
    aliases = functools.partial(_execute, shared, shared)
    copies = functools.partial(_execute, _factory(1), _factory(1))
    assert aliases() == copies() == 2
    assert _function_version(aliases) != _function_version(copies)

    class Offset:
        def __init__(self, amount):
            self.amount = amount

        def add(self, value):
            return self.amount + value

    # Receiver state is deliberately outside callable identity.
    assert _function_version(Offset(1).add) == _function_version(Offset(99).add)


@dataclass
class _StatefulCallable:
    amount: int

    def __call__(self):
        return self.amount


@dataclass
class _OtherCallableContract:
    label: str


def test_explicit_partial_callable_binding_retains_durable_state():
    left = _StatefulCallable(amount=1)
    right = _StatefulCallable(amount=99)
    assert _function_version(left) == _function_version(right)
    first = functools.partial(_execute, left, left)
    changed_state = functools.partial(_execute, right, right)
    assert _function_version(first) != _function_version(changed_state)


def test_callable_default_durable_state_changes_identity():
    positional_default = _StatefulCallable(1)
    keyword_default = _StatefulCallable(1)

    def positional(callback=positional_default):
        return callback()

    def keyword(*, callback=keyword_default):
        return callback()

    positional_before = _function_version(positional)
    keyword_before = _function_version(keyword)
    positional.__defaults__ = (_StatefulCallable(2),)
    keyword.__kwdefaults__ = {"callback": _StatefulCallable(2)}
    assert _function_version(positional) != positional_before
    assert _function_version(keyword) != keyword_before


def test_class_defaults_remain_compact_type_bindings():
    default_type = _StatefulCallable

    def function(callback=default_type):
        return callback

    graph = describe_callable(function)
    assert len(graph.nodes) == 1
    assert graph.nodes[0].bindings[0].kind == "type"
    before = _function_version(function)
    function.__defaults__ = (_OtherCallableContract,)
    assert len(describe_callable(function).nodes) == 1
    assert _function_version(function) != before

    def use(value):
        return value

    explicit = describe_callable(functools.partial(use, default_type))
    assert any(node.value is default_type for node in explicit.nodes)


def test_completed_callable_default_state_change_returns_recorded_result(tmp_path):
    default = _StatefulCallable(1)

    @workflow
    def job(callback=default):
        return callback()

    with Botpipe(tmp_path, provider=FakeProvider([])) as client:
        first = client.run(job)
        assert first.value == 1
        job.fn.__defaults__ = (_StatefulCallable(2),)
        resumed = client.resume(first.run_id, workflow=job)
        assert resumed.ok and resumed.value == 1


def test_decorator_cycles_terminate_and_are_deterministic():
    def direct():
        return "direct"

    direct.__wrapped__ = direct
    first = _function_version(direct)
    assert first == _function_version(direct)

    def left():
        return "left"

    def right():
        return "right"

    left.__wrapped__ = right
    right.__wrapped__ = left
    second = _function_version(left)
    assert second == _function_version(left)
    assert first != second


def _decorator_chain(offset):
    def original():
        return 1

    @functools.wraps(original)
    def middle():
        return original() + offset

    @functools.wraps(middle)
    def outer():
        return middle()

    return outer


def test_same_qualname_decorator_layers_each_contribute_once():
    first = _decorator_chain(1)
    changed = _decorator_chain(2)
    assert first() == 2
    assert changed() == 3
    assert _function_version(first) != _function_version(changed)


def test_builtin_and_method_descriptor_references_remain_distinct():
    pairs = ((len, print), (str.upper, str.lower), ([].append, [].extend))
    for left, right in pairs:
        assert _function_version(left) != _function_version(right)


def _make_meta_tree(root: Path, *, helper_result: str = "old") -> None:
    _write(root / "metapkg/__init__.py", "")
    _write(
        root / "metapkg/helper.py",
        f"def result(): return {helper_result!r}\n",
    )
    _write(
        root / "metapkg/meta.py",
        "from .helper import result\n"
        "class Meta(type):\n"
        "    def __call__(cls): return result()\n",
    )
    _write(root / "branchpkg/__init__.py", "")
    _write(
        root / "branchpkg/branch.py",
        "from metapkg.meta import Meta\nclass Branch(metaclass=Meta): pass\n",
    )


def _meta_identity_script(root: Path) -> Path:
    return _write(
        root / "identity.py",
        "import json\n"
        "from pathlib import Path\n"
        "from branchpkg.branch import Branch\n"
        "from botpipe.provenance import capture_orchestration_sources\n"
        "from botpipe.runtime import _function_version\n"
        "manifest = capture_orchestration_sources(\n"
        "    Branch, boundary=(Path('branchpkg'), Path('metapkg'))\n"
        ")\n"
        "print(json.dumps({'version': _function_version(Branch), "
        "'manifest': manifest}, sort_keys=True))\n",
    )


def test_custom_metaclass_and_helper_have_relocatable_identity(tmp_path):
    first_root = tmp_path / "one"
    second_root = tmp_path / "two"
    _make_meta_tree(first_root)
    shutil.copytree(first_root / "metapkg", second_root / "metapkg")
    shutil.copytree(first_root / "branchpkg", second_root / "branchpkg")
    first_script = _meta_identity_script(first_root)
    second_script = _meta_identity_script(second_root)

    first = _run(first_script)
    relocated = _run(second_script)
    assert first.returncode == 0, first.stderr
    assert relocated.returncode == 0, relocated.stderr
    assert json.loads(first.stdout) == json.loads(relocated.stdout)
    record = json.loads(first.stdout)
    assert record["manifest"]["schema"] == "botpipe.orchestration-sources.v1"
    assert set(record["manifest"]["files"]) >= {
        "branchpkg/branch.py",
        "metapkg/meta.py",
        "metapkg/helper.py",
    }

    helper = second_root / "metapkg/helper.py"
    helper.write_text(helper.read_text().replace("'old'", "'changed'"))
    changed = _run(second_script)
    assert changed.returncode == 0, changed.stderr
    assert json.loads(changed.stdout)["version"] != record["version"]
    assert json.loads(changed.stdout)["manifest"] != record["manifest"]


@pytest.mark.parametrize("edited", ["meta", "helper"])
def test_paused_parallel_replays_result_after_metaclass_source_edit(tmp_path, edited):
    _make_meta_tree(tmp_path)
    _write(tmp_path / "rootpkg/__init__.py", "")
    _write(
        tmp_path / "rootpkg/workflow.py",
        "from botpipe import ask, parallel, workflow\n"
        "from branchpkg.branch import Branch\n"
        "@workflow\n"
        "def job():\n"
        "    answer = parallel(Branch)\n"
        "    ask('continue?')\n"
        "    return answer\n",
    )
    start = _write(
        tmp_path / "start.py",
        "from botpipe import Botpipe\n"
        "from botpipe.providers import FakeProvider\n"
        "from rootpkg.workflow import job\n"
        "with Botpipe('.', provider=FakeProvider([])) as client:\n"
        "    result = client.run(job, run_id='meta-drift')\n"
        "    assert result.status == 'awaiting_input', result.error\n"
        "    assert len(client.journal.operations(result.run_id)) == 2\n",
    )
    resume = _write(
        tmp_path / "resume.py",
        "from botpipe import Botpipe\n"
        "from botpipe.providers import FakeProvider\n"
        "from rootpkg.workflow import job\n"
        "with Botpipe('.', provider=FakeProvider([])) as client:\n"
        "    result = client.resume('meta-drift', workflow=job, answer='yes')\n"
        "    assert result.ok and result.value == ['old'], result.error\n",
    )
    initial = _run(start)
    assert initial.returncode == 0, initial.stderr
    if edited == "meta":
        path = tmp_path / "metapkg/meta.py"
        path.write_text(
            path.read_text().replace("return result()", "return result() + '!'")
        )
    else:
        path = tmp_path / "metapkg/helper.py"
        path.write_text(path.read_text().replace("'old'", "'changed'"))
    replay = _run(resume)
    assert replay.returncode == 0, replay.stderr


def test_shared_dag_and_cycles_have_linear_graphs():
    leaf = _factory(1)
    current = leaf
    for _ in range(16):
        current = _factory_pair(current, current)
    graph = describe_callable(current)
    assert len(graph.nodes) == 17
    assert sum(len(node.edges) for node in graph.nodes) == 32

    def direct():
        return direct

    def left():
        return right

    def right():
        return left

    direct_graph = describe_callable(direct)
    mutual_graph = describe_callable(left)
    assert len(direct_graph.nodes) == 1
    assert direct_graph.nodes[0].edges[0].target == 0
    assert len(mutual_graph.nodes) == 2
    assert {edge.target for node in mutual_graph.nodes for edge in node.edges} == {0, 1}


def _factory_pair(left, right):
    def call():
        return left() + right()

    return call


def test_nested_partial_dag_is_normalized_once():
    callback = _factory(1)
    inner = functools.partial(_execute, callback, callback)
    outer = functools.partial(_execute, inner, inner)
    graph = describe_callable(outer)
    assert len(graph.nodes) == 4
    outer_edges = [edge.target for edge in graph.nodes[0].edges]
    assert outer_edges[1] == outer_edges[2]
    assert outer_edges[0] != outer_edges[1]
    assert _function_version(outer) == _function_version(outer)


def test_deep_callable_chains_do_not_use_python_recursion():
    callback = _factory(1)
    for _ in range(600):
        wrapped = callback

        def callback(child=wrapped):
            return child()

        callback.__wrapped__ = wrapped

    graph = describe_callable(callback)
    assert len(graph.nodes) == 601
    assert len(graph.boundary_targets) == 601
    assert _function_version(callback) == _function_version(callback)


def test_global_helpers_do_not_become_ownership_roots():
    def helper():
        return 1

    def entry():
        return helper()

    graph = describe_callable(entry)
    assert graph.source_targets == (entry, helper)
    assert graph.boundary_targets == (entry,)

    explicit = describe_callable(functools.partial(_execute, helper, helper))
    assert helper in explicit.boundary_targets


def test_helper_only_opaque_defaults_are_not_workflow_arguments():
    opaque = object()

    def helper(value=opaque):
        return value

    def entry():
        return helper()

    graph = describe_callable(entry)
    helper_node = next(node for node in graph.nodes if node.value is helper)
    assert helper_node.bindings[0].label == "default:0"
    assert not helper_node.bindings[0].required
    assert _function_version(entry) == _function_version(entry)


def test_explicit_root_and_later_partial_reference_upgrade_default_strictness():
    opaque = object()

    def helper(value=opaque):
        return value

    with pytest.raises(TypeError, match="Callable defaults must be durable data"):
        _function_version(helper)

    explicit = functools.partial(_execute, helper, helper)

    # Closure-name ordering reaches the ordinary helper first. Encountering the
    # same object through the partial must still upgrade its default strictness.
    a_helper = helper
    z_explicit = explicit

    def entry():
        return a_helper, z_explicit

    graph = describe_callable(entry)
    helper_node = next(node for node in graph.nodes if node.value is helper)
    assert helper_node.bindings[0].required
    with pytest.raises(TypeError, match="Callable defaults must be durable data"):
        _function_version(entry)


@pytest.mark.parametrize("keyword_only", [False, True])
def test_later_explicit_reference_upgrades_callable_default_dependencies(
    keyword_only,
):
    opaque = object()

    def nested(value=opaque):
        return value

    if keyword_only:

        def outer(*, callback=nested):
            return callback()

    else:

        def outer(callback=nested):
            return callback()

    a_outer = outer
    z_explicit = functools.partial(_execute, outer, outer)

    def entry():
        return a_outer, z_explicit

    graph = describe_callable(entry)
    nested_node = next(node for node in graph.nodes if node.value is nested)
    assert nested_node.bindings[0].required
    with pytest.raises(TypeError, match="Callable defaults must be durable data"):
        _function_version(entry)


def test_alias_topology_is_stable_in_fresh_processes(tmp_path):
    script = _write(
        tmp_path / "identity.py",
        "import functools\n"
        "from botpipe.runtime import _function_version\n"
        "def factory(value):\n"
        "    def callback(): return value\n"
        "    return callback\n"
        "def execute(left, right): return left() + right()\n"
        "shared = factory(1)\n"
        "print(_function_version(functools.partial(execute, shared, shared)))\n"
        "print(_function_version(functools.partial(execute, factory(1), factory(1))))\n",
    )
    first = _run(script)
    second = _run(script)
    assert first.returncode == second.returncode == 0
    assert first.stdout == second.stdout
    shared, copies = first.stdout.splitlines()
    assert shared != copies

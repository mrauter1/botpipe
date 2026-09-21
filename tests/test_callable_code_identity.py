from __future__ import annotations

import pytest

from botpipe import Botpipe, parallel, workflow
from botpipe.providers import FakeProvider
from botpipe.runtime import _function_version


def _compiled(source: str):
    namespace = {"__name__": "owned.dynamic"}
    exec(compile(source, "<owned-dynamic>", "exec"), namespace)  # noqa: S102
    return namespace["branch"]


@pytest.mark.parametrize(
    ("before", "after"),
    [
        (
            "def branch(): return 1 + 2j\n",
            "def branch(): return 3 + 4j\n",
        ),
        (
            "def branch(): return ((1 + 2j,),)\n",
            "def branch(): return ((3 + 4j,),)\n",
        ),
        (
            "def branch(value): return value in {1 + 2j, 3 + 4j}\n",
            "def branch(value): return value in {5 + 6j, 7 + 8j}\n",
        ),
    ],
)
def test_source_free_nested_constants_contribute_values(before, after):
    original = _compiled(before)
    changed = _compiled(after)

    assert original.__module__ == changed.__module__ == "owned.dynamic"
    assert original.__qualname__ == changed.__qualname__ == "branch"
    assert original.__code__.co_code == changed.__code__.co_code
    assert _function_version(original) != _function_version(changed)


def test_source_free_nonfinite_float_and_ellipsis_identities_are_stable():
    positive_infinity = _compiled("def branch(): return 1e309\n")
    negative_infinity = _compiled("def branch(): return -1e309\n")
    ellipsis = _compiled("def branch(): return ...\n")

    assert positive_infinity() == float("inf")
    assert negative_infinity() == float("-inf")
    assert ellipsis() is Ellipsis
    identities = {
        _function_version(positive_infinity),
        _function_version(negative_infinity),
        _function_version(ellipsis),
    }
    assert len(identities) == 3
    assert _function_version(ellipsis) == _function_version(ellipsis)


@pytest.mark.parametrize(
    ("before", "after"),
    [
        (
            "def branch(left): return left\n",
            "def branch(right): return right\n",
        ),
        (
            "def branch(value, /): return value\n",
            "def branch(value): return value\n",
        ),
        (
            "def branch(value): return value\n",
            "def branch(*, value): return value\n",
        ),
        (
            "def branch(*values): return values\n",
            "def branch(values): return values\n",
        ),
    ],
)
def test_source_free_parameter_names_and_argument_layout_contribute(before, after):
    original = _compiled(before)
    changed = _compiled(after)

    assert original.__module__ == changed.__module__ == "owned.dynamic"
    assert original.__qualname__ == changed.__qualname__ == "branch"
    assert _function_version(original) != _function_version(changed)


def test_completed_parallel_returns_saved_value_after_complex_literal_change(tmp_path):
    original = _compiled("def branch(): return str(1 + 2j)\n")
    changed = _compiled("def branch(): return str(3 + 4j)\n")
    selected = [original]

    @workflow
    def job():
        return parallel(selected[0])

    with Botpipe(tmp_path, provider=FakeProvider([])) as client:
        first = client.run(job, run_id="source-free-complex")
        assert first.ok and first.value == ["(1+2j)"], first.error
        before = client.journal.operations(first.run_id)

        selected[0] = changed
        replay = client.resume(first.run_id, workflow=job)

        assert replay.ok, replay.error
        assert replay.value == ["(1+2j)"]
        assert client.journal.operations(first.run_id) == before

"""Measure callable identity separately from provider execution.

Run from a checkout with ``PYTHONPATH=. python benchmarks/callable_identity.py``.
The shared graphs check scaling; timings are observations, not flaky CI gates.
All workflow execution uses FakeProvider and temporary workspaces.
"""

from __future__ import annotations

import argparse
import json
import platform
from functools import partial
from pathlib import Path
from statistics import median
from tempfile import TemporaryDirectory
from time import perf_counter

import botpipe
from botpipe import Botpipe, Policy, Session, parallel, workflow
from botpipe._callables import describe_callable
from botpipe.discovery import discover_workflows, resolve_workflow
from botpipe.providers import FakeProvider
from botpipe.runtime import Workflow, _function_version


def leaf():
    return 1


def pair(left, right):
    def call():
        return left() + right()

    return call


def shared_graph(depth):
    call = leaf
    for _ in range(depth):
        call = pair(call, call)
    return call


def recursive_graph():
    def first(value):
        return second(value - 1) if value else 0

    def second(value):
        return first(value - 1) if value else 0

    return first


@workflow
def plain_job():
    return 7


@workflow
def session_job():
    session = Session()
    return parallel(
        partial(session.run, "review", policy=Policy(sandbox_mode="read_only"))
    )[0].value


def measure(call, iterations):
    call()  # Warm imports, schema initialization and Python's source line cache.
    samples = []
    for _ in range(iterations):
        started = perf_counter()
        call()
        samples.append(1000 * (perf_counter() - started))
    return {"median_ms": round(median(samples), 3), "min_ms": round(min(samples), 3)}


def measure_run(definition, iterations):
    execution, replay = [], []
    for _ in range(iterations):
        with TemporaryDirectory() as directory:
            provider = FakeProvider(["approved"])
            with Botpipe(directory, provider=provider) as client:
                started = perf_counter()
                result = client.run(definition)
                execution.append(1000 * (perf_counter() - started))
                assert result.ok, result.error
                calls = len(provider.calls)
                started = perf_counter()
                restored = client.resume(result.run_id, workflow=definition)
                replay.append(1000 * (perf_counter() - started))
                assert restored.ok, restored.error
                assert restored.value == result.value
                assert len(provider.calls) == calls
    return {
        "run_median_ms": round(median(execution), 3),
        "resume_median_ms": round(median(replay), 3),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iterations", type=int, default=5)
    args = parser.parse_args()
    if args.iterations < 1:
        parser.error("--iterations must be positive")

    # Only inspect the bound implementation: a live run owns Session state.
    session = object.__new__(Session)
    calls = {
        "plain": leaf,
        "recursive": recursive_graph(),
        "session_partial": partial(
            session.run, "review", policy=Policy(sandbox_mode="read_only")
        ),
        **{f"shared_depth_{depth}": shared_graph(depth) for depth in (8, 16, 32, 64)},
    }
    fingerprints = {}
    for name, call in calls.items():
        description = describe_callable(call)
        nodes = getattr(description, "nodes", None)
        fingerprints[name] = {
            **measure(lambda call=call: _function_version(call), args.iterations),
            "prepare_median_ms": measure(
                lambda call=call: Workflow(call), args.iterations
            )["median_ms"],
            "graph_nodes": len(nodes) if nodes is not None else None,
        }
    with TemporaryDirectory() as directory:
        definitions = [
            resolve_workflow(entry.reference, directory)
            for entry in discover_workflows(directory)
        ]
        catalog = measure(
            lambda: [definition.fingerprint for definition in definitions],
            args.iterations,
        )
    print(
        json.dumps(
            {
                "python": platform.python_version(),
                "package": str(Path(botpipe.__file__).resolve()),
                "iterations": args.iterations,
                "fingerprints": fingerprints,
                "catalog": {"workflows": len(definitions), **catalog},
                "execution": {
                    "plain": measure_run(plain_job, args.iterations),
                    "session_partial": measure_run(session_job, args.iterations),
                },
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

from __future__ import annotations

from copy import deepcopy

import pytest

from botpipe.artifacts import Artifact, ArtifactStore
from botpipe.worklists import Selector, Worklist


class RecordedRun:
    def __init__(self, folder, history=None):
        self.folder = self.task_folder = self.workspace = folder
        self.scope = "main"
        self.history = history if history is not None else []
        self.index = 0
        self.executions = []

    def operation(self, kind, inputs, execute, **kwargs):
        index = self.index
        self.index += 1
        if index < len(self.history):
            previous = self.history[index]
            assert previous[:2] == (kind, inputs)
            return deepcopy(previous[2])
        output = execute()
        self.executions.append(kind)
        self.history.append((kind, deepcopy(inputs), deepcopy(output)))
        return output


@pytest.fixture
def managed(tmp_path, monkeypatch):
    import botpipe.worklists as module

    run = RecordedRun(tmp_path)
    monkeypatch.setattr(module, "_run", lambda: run)
    document = {
        "extra": "preserve",
        "items": [
            {"id": "a", "title": "First", "status": "pending"},
            {"id": "b", "title": "Second", "status": "pending"},
            {"id": "c", "title": "Third", "status": "completed"},
        ],
    }
    artifact = ArtifactStore(tmp_path).publish(
        Artifact.json("plan.json"), document, "initial"
    )
    return run, artifact


def test_completion_publishes_versions_and_retains_historical_selection(managed):
    run, artifact = managed
    items = Worklist.from_artifact(artifact)
    first, second, third = items
    completed = items.complete(first)
    assert completed.read_json()["items"][0]["status"] == "completed"
    assert artifact.read_json()["items"][0]["status"] == "pending"
    assert completed.read_json()["extra"] == "preserve"
    assert [item.id for item in items] == ["a", "b", "c"]
    assert items.artifact == completed
    items.complete(second)
    assert [p["status"] for p in items.artifact.read_json()["items"]] == [
        "completed"
    ] * 3
    assert run.executions == [
        "worklist.select",
        "worklist.complete",
        "worklist.complete",
    ]


def test_replay_repeats_selection_and_does_not_repeat_completed_writes(
    managed, monkeypatch
):
    import botpipe.worklists as module

    run, artifact = managed
    items = Worklist.from_artifact(artifact)
    first = next(iter(items))
    completed = items.complete(first)
    # A live alias is deliberately unrelated to the original selected snapshot.
    artifact.source_path.write_text('{"items": []}')
    resumed = RecordedRun(run.folder, run.history)
    monkeypatch.setattr(module, "_run", lambda: resumed)
    replayed = Worklist.from_artifact(artifact)
    assert [item.id for item in replayed] == ["a", "b", "c"]
    replayed.complete(next(iter(replayed)))
    assert replayed.artifact == completed
    assert resumed.executions == []


@pytest.mark.parametrize(
    ("selection", "expected"),
    [
        (None, ["a", "b", "c"]),
        (Selector.single(), ["a"]),
        (Selector.single("b"), ["b"]),
        (Selector.up_to("b"), ["a", "b"]),
        (Selector.from_to("b", "c"), ["b", "c"]),
        ({"mode": "from_to", "end": "b"}, ["a", "b"]),
    ],
)
def test_selectors(managed, selection, expected):
    _, artifact = managed
    assert [
        item.id for item in Worklist.from_artifact(artifact, selection=selection)
    ] == expected


@pytest.mark.parametrize(
    "selection", [Selector.single("missing"), Selector.from_to("c", "a")]
)
def test_invalid_selection(managed, selection):
    _, artifact = managed
    with pytest.raises(ValueError):
        Worklist.from_artifact(artifact, selection=selection)


@pytest.mark.parametrize(
    "items",
    [
        [{"id": "a", "title": "one"}, {"id": "a", "title": "two"}],
        [{"id": "a", "title": "one", "dir_key": "../escape"}],
        [
            {"id": "a", "title": "one", "dir_key": "same"},
            {"id": "b", "title": "two", "dir_key": "same"},
        ],
        [{"id": 1, "title": "one"}],
    ],
)
def test_duplicate_ids_and_unsafe_directory_keys(managed, items):
    run, _ = managed
    handle = ArtifactStore(run.folder).publish(
        Artifact.json("bad.json"), {"items": items}, "bad"
    )
    with pytest.raises(ValueError):
        Worklist.from_artifact(handle)


def test_unsafe_identity_gets_safe_directory_key(managed):
    run, _ = managed
    handle = ArtifactStore(run.folder).publish(
        Artifact.json("special.json"),
        {"items": [{"id": "../my item", "title": "Title"}]},
        "special",
    )
    item = next(iter(Worklist.from_artifact(handle, name="tasks")))
    assert item.worklist == "tasks"
    assert item.dir_key.startswith("item-")
    assert "/" not in item.dir_key


def test_payload_mutation_cannot_change_completion_source(managed):
    _, artifact = managed
    items = Worklist.from_artifact(artifact)
    item = next(iter(items))
    item.payload["title"] = "mutated"
    assert next(iter(items)).title == "First"
    assert items.complete(item).read_json()["items"][0]["title"] == "First"


def test_interruption_after_alias_write_retries_same_immutable_version(
    managed, monkeypatch
):
    import botpipe.worklists as module

    run, artifact = managed
    items = Worklist.from_artifact(artifact)
    materialize = ArtifactStore.materialize

    def interrupt_after_alias(store, handle, destination=None):
        materialize(store, handle, destination)
        raise KeyboardInterrupt()

    monkeypatch.setattr(ArtifactStore, "materialize", interrupt_after_alias)
    with pytest.raises(KeyboardInterrupt):
        items.complete(next(iter(items)))
    assert '"completed"' in artifact.source_path.read_text()
    monkeypatch.setattr(ArtifactStore, "materialize", materialize)
    resumed = RecordedRun(run.folder, run.history)
    monkeypatch.setattr(module, "_run", lambda: resumed)
    replayed = Worklist.from_artifact(artifact)
    replayed.complete(next(iter(replayed)))
    assert replayed.artifact.read_json()["items"][0]["status"] == "completed"
    assert resumed.executions == ["worklist.complete"]


def test_replayed_earlier_completion_does_not_rewind_latest_alias(managed, monkeypatch):
    import botpipe.worklists as module

    run, artifact = managed
    items = Worklist.from_artifact(artifact)
    first, second, _ = items
    items.complete(first)
    items.complete(second)
    latest = artifact.source_path.read_bytes()
    resumed = RecordedRun(run.folder, run.history)
    monkeypatch.setattr(module, "_run", lambda: resumed)
    replayed = Worklist.from_artifact(artifact)
    replayed.complete(next(iter(replayed)))
    assert artifact.source_path.read_bytes() == latest
    assert replayed.artifact.read_json()["items"][1]["status"] == "pending"
